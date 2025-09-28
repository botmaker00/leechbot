import contextlib
import gc
import json
import os
import resource
import shutil
from asyncio import create_subprocess_exec, gather, sleep, wait_for
from asyncio.subprocess import PIPE
from os import path as ospath
from pathlib import Path
from re import compile, escape
from re import match as re_match
from re import search as re_search
from time import time

import aiofiles
import fitz  # PyMuPDF
from aioshutil import rmtree
from PIL import Image

from bot import DOWNLOAD_DIR, LOGGER, cpu_no
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath, makedirs, remove

from .bot_utils import cmd_exec, sync_to_async
from .files_utils import get_mime_type, get_path_size, is_archive, is_archive_split
from .status_utils import time_to_seconds

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None

# Optimized media information cache with reduced memory footprint
# This cache stores information about media files to avoid repeated ffprobe calls
# The key is the file path and modification time, and the value is the media information
MEDIA_INFO_CACHE = {}
MEDIA_STREAMS_CACHE = {}
MEDIA_TYPE_CACHE = {}

# Reduced maximum cache size to save memory
MAX_CACHE_SIZE = 50  # Reduced from 100 to 50


def limit_memory_for_pil():
    """Apply memory limits for PIL operations based on config with enhanced safety."""
    try:
        # Get memory limit from config
        memory_limit = Config.PIL_MEMORY_LIMIT

        if memory_limit > 0:
            # Get current memory usage to determine safe limits
            try:
                import psutil

                available_memory = psutil.virtual_memory().available / (
                    1024 * 1024
                )  # MB

                # Use the smaller of configured limit or 80% of available memory
                safe_limit = min(memory_limit, int(available_memory * 0.8))

                # Ensure minimum limit of 256MB for basic operations
                safe_limit = max(safe_limit, 256)

            except ImportError:
                # Fallback if psutil not available - use conservative limit
                safe_limit = min(memory_limit, 512)

            # Convert MB to bytes for resource limit
            memory_limit_bytes = safe_limit * 1024 * 1024

            # Set soft limit (warning) and hard limit (error)
            resource.setrlimit(
                resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes)
            )

        return True
    except Exception as e:
        LOGGER.error(f"Error setting memory limit for PIL: {e}")
        return False


async def get_streams(file):
    """Get stream information from a media file using ffprobe with enhanced error handling.

    Args:
        file: Path to the media file

    Returns:
        list: List of stream dictionaries, or None if an error occurs
    """
    # Check if file exists
    if not await aiopath.exists(file):
        LOGGER.error(f"File not found: {file}")
        return None

    # Check file size - skip very small files that are likely corrupted
    try:
        file_size = os.path.getsize(file)
        if file_size < 1024:  # Less than 1KB
            LOGGER.warning(
                f"File too small ({file_size} bytes), likely corrupted: {file}"
            )
            return None
    except Exception as e:
        LOGGER.warning(f"Could not get file size for {file}: {e}")

    # Get file modification time for cache key
    try:
        mtime = os.path.getmtime(file)
        cache_key = f"{file}_{mtime}"

        # Check if we have this in cache
        if cache_key in MEDIA_STREAMS_CACHE:
            return MEDIA_STREAMS_CACHE[cache_key]
    except Exception:
        cache_key = None

    # Enhanced ffprobe command with better error handling
    # Use ffprobe for stream analysis (xtra is ffmpeg, not ffprobe)
    ffprobe_binary = "ffprobe"

    cmd = [
        ffprobe_binary,
        "-hide_banner",
        "-loglevel",
        "warning",  # Changed from "error" to "warning" for better diagnostics
        "-analyzeduration",
        "10000000",  # 10 seconds max analysis
        "-probesize",
        "50000000",  # 50MB max probe size
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",  # Also get format info for better validation
        file,
    ]

    # Execute the command
    try:
        stdout, stderr, code = await cmd_exec(cmd)
    except Exception as e:
        LOGGER.warning(f"ffprobe execution failed for {file}: {e}")
        return None

    # Enhanced error handling for common media file issues
    if code != 0:
        error_msg = stderr.lower() if stderr else ""

        # Handle specific common errors gracefully
        if "moov atom not found" in error_msg:
            LOGGER.warning(f"⚠️ Incomplete MP4 file (missing moov atom): {file}")
            return None
        if "ebml header parsing failed" in error_msg:
            LOGGER.warning(
                f"⚠️ Corrupted Matroska/WebM file (EBML header issue): {file}"
            )
            return None
        if "invalid data found when processing input" in error_msg:
            LOGGER.warning(f"⚠️ Corrupted media file detected: {file}")
            return None
        if "no such file or directory" in error_msg:
            LOGGER.warning(f"⚠️ File disappeared during analysis: {file}")
            return None
        LOGGER.warning(f"⚠️ ffprobe failed for {file}: {stderr}")
        return None

    # Validate stdout is not empty
    if not stdout or not stdout.strip():
        LOGGER.warning(f"ffprobe returned empty output for {file}")
        return None

    try:
        data = json.loads(stdout)
        streams = data.get("streams", [])

        # Validate we have actual streams
        if not streams:
            LOGGER.warning(f"No streams found in media file: {file}")
            return None

        # Additional validation - check if streams have required fields
        valid_streams = []
        for stream in streams:
            if "codec_type" in stream and "index" in stream:
                valid_streams.append(stream)
            else:
                LOGGER.warning(f"Invalid stream data in {file}: {stream}")

        if not valid_streams:
            LOGGER.warning(f"No valid streams found in {file}")
            return None

        # Cache the result if we have a valid cache key
        if cache_key and valid_streams:
            # If cache is too large, remove oldest entries
            if len(MEDIA_STREAMS_CACHE) >= MAX_CACHE_SIZE:
                # Remove the first item (oldest)
                MEDIA_STREAMS_CACHE.pop(next(iter(MEDIA_STREAMS_CACHE)))

            MEDIA_STREAMS_CACHE[cache_key] = valid_streams

        LOGGER.info(
            f"✅ Successfully analyzed {len(valid_streams)} streams in {file}"
        )
        return valid_streams

    except KeyError as e:
        LOGGER.warning(f"Missing expected data in ffprobe output for {file}: {e}")
        return None
    except json.JSONDecodeError as e:
        LOGGER.warning(f"Invalid JSON in ffprobe output for {file}: {e}")
        return None
    except Exception as e:
        LOGGER.error(f"Unexpected error processing ffprobe output for {file}: {e}")
        return None


async def validate_media_file(file_path: str) -> tuple[bool, str]:
    """Validate media file integrity and detect common corruption issues.

    Args:
        file_path: Path to the media file

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        # Check if file exists
        if not await aiopath.exists(file_path):
            return False, "File not found"

        # Check file size
        try:
            file_size = os.path.getsize(file_path)
            if file_size < 1024:  # Less than 1KB
                return False, f"File too small ({file_size} bytes), likely corrupted"
        except Exception as e:
            return False, f"Cannot access file: {e}"

        # Quick validation using ffprobe with minimal analysis
        cmd = [
            "ffprobe",  # Use ffprobe for stream analysis
            "-hide_banner",
            "-loglevel",
            "error",
            "-analyzeduration",
            "1000000",  # 1 second max
            "-probesize",
            "5000000",  # 5MB max
            "-print_format",
            "json",
            "-show_format",
            file_path,
        ]

        try:
            stdout, stderr, code = await cmd_exec(cmd)
        except Exception as e:
            return False, f"Validation failed: {e}"

        if code != 0:
            error_msg = stderr.lower() if stderr else ""

            # Detect specific corruption patterns
            if "moov atom not found" in error_msg:
                return False, "Incomplete MP4 file (missing moov atom)"
            if "ebml header parsing failed" in error_msg:
                return False, "Corrupted Matroska/WebM file (EBML header issue)"
            if "invalid data found when processing input" in error_msg:
                return False, "Corrupted media file detected"
            if "no such file or directory" in error_msg:
                return False, "File disappeared during validation"
            return False, f"Media validation failed: {stderr}"

        # Check if we got valid format info
        if stdout:
            try:
                data = json.loads(stdout)
                format_info = data.get("format", {})
                if not format_info:
                    return False, "No format information found"

                # Check if duration is reasonable (not 0 or negative)
                duration = float(format_info.get("duration", 0))
                if duration <= 0:
                    return False, "Invalid or zero duration"

                return True, "Valid media file"

            except json.JSONDecodeError:
                return False, "Invalid ffprobe output"
        else:
            return False, "Empty ffprobe output"

    except Exception as e:
        return False, f"Validation error: {e}"


async def create_thumb(msg, _id=""):
    if not _id:
        _id = time()
        path = f"{DOWNLOAD_DIR}thumbnails"
    else:
        path = "thumbnails"
    await makedirs(path, exist_ok=True)
    photo_dir = await msg.download()
    output = ospath.join(path, f"{_id}.jpg")

    # Use PIL to convert and save the image
    try:
        # Apply memory limits for PIL operations
        limit_memory_for_pil()

        img = await sync_to_async(Image.open, photo_dir)
        img_rgb = await sync_to_async(img.convert, "RGB")
        await sync_to_async(img_rgb.save, output, "JPEG")

        # Close the images to free up memory
        await sync_to_async(img_rgb.close)
        await sync_to_async(img.close)
    except Exception as e:
        LOGGER.error(f"Error processing thumbnail: {e}")
        if await aiopath.exists(output):
            await remove(output)
        raise
    finally:
        # Clean up the downloaded file
        if await aiopath.exists(photo_dir):
            await remove(photo_dir)

    return output


async def get_media_info(path):
    """Get media information (duration, artist, title) from a media file.

    Args:
        path: Path to the media file

    Returns:
        tuple: (duration, artist, title)
    """
    # Check if file exists
    if not await aiopath.exists(path):
        LOGGER.error(f"File not found: {path}")
        return 0, None, None

    # Get file modification time for cache key
    try:
        mtime = os.path.getmtime(path)
        cache_key = f"{path}_{mtime}"

        # Check if we have this in cache
        if cache_key in MEDIA_INFO_CACHE:
            return MEDIA_INFO_CACHE[cache_key]
    except Exception:
        cache_key = None

    # If not in cache or couldn't get mtime, run ffprobe
    try:
        result = await cmd_exec(
            [
                "ffprobe",  # Use ffprobe for stream analysis
                "-hide_banner",
                "-loglevel",
                "error",
                "-print_format",
                "json",
                "-show_format",
                path,
            ],
        )
    except Exception as e:
        LOGGER.error(f"Get Media Info: {e}. Mostly File not found! - File: {path}")
        return 0, None, None

    if result[0] and result[2] == 0:
        try:
            # Use json.loads instead of eval for better security and performance
            data = json.loads(result[0])
            fields = data.get("format")

            if fields is None:
                LOGGER.error(f"get_media_info: {result}")
                return 0, None, None

            duration = round(float(fields.get("duration", 0)))
            tags = fields.get("tags", {})
            artist = tags.get("artist") or tags.get("ARTIST") or tags.get("Artist")
            title = tags.get("title") or tags.get("TITLE") or tags.get("Title")

            # Cache the result if we have a valid cache key
            if cache_key:
                # If cache is too large, remove oldest entries
                if len(MEDIA_INFO_CACHE) >= MAX_CACHE_SIZE:
                    # Remove the first item (oldest)
                    MEDIA_INFO_CACHE.pop(next(iter(MEDIA_INFO_CACHE)))

                MEDIA_INFO_CACHE[cache_key] = (duration, artist, title)

            return duration, artist, title
        except json.JSONDecodeError:
            LOGGER.error(f"Invalid JSON in ffprobe output: {result[0]}")
            return 0, None, None

    return 0, None, None


def _get_original_filename_for_media_detection(filename):
    """
    Get the original filename for media type detection.
    For split files (e.g., movie.mkv.001, movie.mkv.002), returns the original filename (movie.mkv).
    For regular files, returns the filename as-is.
    """

    # Check for split file patterns
    # Pattern 1: filename.ext.001, filename.ext.002, etc.
    match = re_match(r"(.+\.\w+)\.(\d{3})$", filename)
    if match:
        return match.group(1)  # Return filename.ext without the .001 part

    # Pattern 2: filename.part001.ext, filename.part002.ext, etc.
    match = re_match(r"(.+)\.part\d+(\.\w+)$", filename)
    if match:
        return f"{match.group(1)}{match.group(2)}"  # Return filename.ext without the .part001 part

    # Pattern 3: filename.001, filename.002 (no extension before split number)
    match = re_match(r"(.+)\.(\d{3})$", filename)
    if match:
        # This is trickier - we need to guess the original extension
        # For now, return the base name and let the extension-based detection handle it
        return match.group(1)

    # Not a split file, return as-is
    return filename


async def _get_document_type_from_extension(filename):
    """
    Determine document type based on file extension.
    Returns (is_video, is_audio, is_image) tuple.
    """
    is_video, is_audio, is_image = False, False, False

    # Get file extension
    file_ext = ospath.splitext(filename)[1].lower()

    # Video extensions
    video_extensions = {
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".3gp",
        ".3g2",
        ".asf",
        ".rm",
        ".rmvb",
        ".vob",
        ".ts",
        ".mts",
        ".m2ts",
        ".divx",
        ".xvid",
        ".ogv",
        ".f4v",
        ".mpg",
        ".mpeg",
        ".m1v",
        ".m2v",
        ".mpe",
        ".mpv",
        ".mp2",
        ".mpa",
        ".mpg2",
    }

    # Audio extensions
    audio_extensions = {
        ".mp3",
        ".flac",
        ".wav",
        ".aac",
        ".ogg",
        ".wma",
        ".m4a",
        ".opus",
        ".ape",
        ".ac3",
        ".dts",
        ".amr",
        ".au",
        ".ra",
        ".aiff",
        ".aif",
        ".aifc",
        ".caf",
        ".sd2",
        ".snd",
        ".m1a",
        ".m2a",
    }

    # Image extensions
    image_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
        ".svg",
        ".ico",
        ".psd",
        ".raw",
        ".cr2",
        ".nef",
        ".arw",
        ".dng",
        ".heic",
        ".heif",
        ".avif",
        ".jxl",
    }

    if file_ext in video_extensions:
        is_video = True
    elif file_ext in audio_extensions:
        is_audio = True
    elif file_ext in image_extensions:
        is_image = True

    return is_video, is_audio, is_image


async def get_document_type(path):
    is_video, is_audio, is_image = False, False, False

    # Check if it's an archive first
    if (
        is_archive(path)
        or is_archive_split(path)
        or re_search(r".+(\.|_)(rar|7z|zip|bin)(\.0*\d+)?$", path)
    ):
        return is_video, is_audio, is_image

    # Handle split files specially - determine type from original filename
    filename = ospath.basename(path)
    original_filename = _get_original_filename_for_media_detection(filename)
    if original_filename != filename:
        # This is a split file, determine type from original extension
        return await _get_document_type_from_extension(original_filename)

    # Check file extension for known types that might cause issues with Telegram
    file_ext = ospath.splitext(path)[1].lower()

    # Lists of extensions for different file types

    # List of extensions that Telegram supports as photos
    valid_photo_extensions = [".jpg", ".jpeg", ".png", ".webp"]

    # List of extensions that should always be treated as documents
    document_extensions = [
        ".psd",
        ".ai",
        ".eps",
        ".pdf",
        ".xd",
        ".ico",
        ".icns",
        ".svg",
        ".tiff",
        ".tif",
        ".raw",
        ".cr2",
        ".nef",
        ".arw",
        ".dng",
        ".heic",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".txt",
        ".rtf",
        ".epub",
        ".mobi",
        ".cbz",
        ".cbr",
    ]

    # If the file has a document extension, don't treat it as an image
    if file_ext in document_extensions:
        return False, False, False

    # Get the mime type for further analysis
    mime_type = await get_mime_type(path)

    # If it's an image mime type but not a valid Telegram photo extension,
    # don't mark it as an image to avoid PHOTO_EXT_INVALID errors
    if mime_type.startswith("image"):
        if file_ext in valid_photo_extensions:
            is_image = True
        return is_video, is_audio, is_image

    # Handle audio files
    if mime_type.startswith("audio"):
        is_audio = True
        return is_video, is_audio, is_image

    # For text files, subtitles, and other document types
    if mime_type.startswith(
        ("text/", "application/pdf", "application/msword", "application/vnd.ms")
    ):
        return is_video, is_audio, is_image

    # For video and more complex media files, use ffprobe for detailed analysis
    try:
        result = await cmd_exec(
            [
                "ffprobe",  # Use ffprobe for stream analysis
                "-hide_banner",
                "-loglevel",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                path,
            ],
        )
        if result[0] and result[2] == 0 and mime_type.startswith("video"):
            is_video = True
    except Exception as e:
        LOGGER.error(
            f"Get Document Type: {e}. Mostly File not found! - File: {path}",
        )
        if mime_type.startswith("audio"):
            return False, True, False
        if not mime_type.startswith("video") and not mime_type.endswith(
            "octet-stream",
        ):
            return is_video, is_audio, is_image
        if mime_type.startswith("video"):
            is_video = True
        return is_video, is_audio, is_image
    if result[0] and result[2] == 0:
        fields = eval(result[0]).get("streams")
        if fields is None:
            LOGGER.error(f"get_document_type: {result}")
            return is_video, is_audio, is_image
        is_video = False
        for stream in fields:
            if stream.get("codec_type") == "video":
                codec_name = stream.get("codec_name", "").lower()
                if codec_name not in {"mjpeg", "png", "bmp"}:
                    is_video = True
            elif stream.get("codec_type") == "audio":
                is_audio = True
    return is_video, is_audio, is_image


async def get_media_type(file_path):
    """Determine if a file is video, audio, or subtitle.

    Args:
        file_path: Path to the file

    Returns:
        str: 'video', 'audio', 'subtitle', 'image', 'document', 'archive', or None if can't determine
    """
    # Check if file exists
    if not await aiopath.exists(file_path):
        LOGGER.error(f"File not found: {file_path}")
        return None

    # Get file modification time for cache key
    try:
        mtime = os.path.getmtime(file_path)
        cache_key = f"{file_path}_{mtime}"

        # Check if we have this in cache
        if cache_key in MEDIA_TYPE_CACHE:
            return MEDIA_TYPE_CACHE[cache_key]
    except Exception:
        cache_key = None

    # First try to determine by extension
    file_ext = os.path.splitext(file_path)[1].lower()

    # Video extensions
    if file_ext in [
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".webm",
        ".flv",
        ".wmv",
        ".m4v",
        ".ts",
        ".3gp",
        ".mpg",
        ".mpeg",
        ".hevc",
    ]:
        media_type = "video"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # Audio extensions
    if file_ext in [
        ".mp3",
        ".m4a",
        ".wav",
        ".flac",
        ".ogg",
        ".opus",
        ".aac",
        ".ac3",
    ]:
        media_type = "audio"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # Image extensions
    if file_ext in [
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
        ".gif",
        ".svg",
        ".psd",
    ]:
        media_type = "image"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # Subtitle extensions
    if file_ext in [".srt", ".vtt", ".ass", ".ssa", ".sub"]:
        media_type = "subtitle"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # Document extensions
    if file_ext in [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".epub"]:
        media_type = "document"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # Archive extensions
    if file_ext in [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"]:
        media_type = "archive"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # If extension doesn't match, try to determine by file content
    try:
        # Use ffprobe to get streams
        streams = await get_streams(file_path)
        if streams:
            # Check for video streams
            for stream in streams:
                # Check if it's a video stream and not just a cover art
                is_video_stream = stream.get("codec_type") == "video" and not (
                    stream.get("disposition")
                    and stream.get("disposition").get("attached_pic") == 1
                )
                if is_video_stream:
                    media_type = "video"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type

            # Check for audio streams
            for stream in streams:
                if stream.get("codec_type") == "audio":
                    media_type = "audio"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type

            # Check for subtitle streams
            for stream in streams:
                if stream.get("codec_type") == "subtitle":
                    media_type = "subtitle"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type
    except Exception as e:
        LOGGER.error(f"Error determining media type: {e}")

    # If all else fails, try to determine by mime type
    try:
        mime_type = await get_mime_type(file_path)
        if mime_type:
            if mime_type.startswith("video/"):
                media_type = "video"
                if cache_key:
                    MEDIA_TYPE_CACHE[cache_key] = media_type
                return media_type

            if mime_type.startswith("image/"):
                media_type = "image"
                if cache_key:
                    MEDIA_TYPE_CACHE[cache_key] = media_type
                return media_type

            if mime_type.startswith("audio/"):
                media_type = "audio"
                if cache_key:
                    MEDIA_TYPE_CACHE[cache_key] = media_type
                return media_type

            if mime_type in ["text/plain", "application/x-subrip"]:
                # Check if it's a subtitle file by examining content
                async with aiofiles.open(file_path, errors="ignore") as f:
                    content = await f.read(1000)  # Read first 1000 chars
                    if "-->" in content and content[0].isdigit():
                        media_type = "subtitle"
                        if cache_key:
                            MEDIA_TYPE_CACHE[cache_key] = media_type
                        return media_type

            elif mime_type.startswith(("application/pdf", "application/msword")):
                media_type = "document"
                if cache_key:
                    MEDIA_TYPE_CACHE[cache_key] = media_type
                return media_type

            elif mime_type.startswith(("application/zip", "application/x-rar")):
                media_type = "archive"
                if cache_key:
                    MEDIA_TYPE_CACHE[cache_key] = media_type
                return media_type
    except Exception as e:
        LOGGER.error(f"Error getting mime type: {e}")

    # If cache is too large, remove oldest entries
    if cache_key and len(MEDIA_TYPE_CACHE) >= MAX_CACHE_SIZE:
        # Remove the first item (oldest)
        MEDIA_TYPE_CACHE.pop(next(iter(MEDIA_TYPE_CACHE)))

    # Cache the result (None) if we have a valid cache key
    if cache_key:
        MEDIA_TYPE_CACHE[cache_key] = None

    return None


async def take_ss(video_file, ss_nb) -> bool:
    """Take screenshots from video using simple approach like old Aeon"""
    duration = (await get_media_info(video_file))[0]
    if duration != 0:
        dirpath, name = video_file.rsplit("/", 1)
        name, _ = ospath.splitext(name)
        dirpath = f"{dirpath}/{name}_ss"
        await makedirs(dirpath, exist_ok=True)
        interval = duration // (ss_nb + 1)
        cap_time = interval
        cmds = []
        for i in range(ss_nb):
            output = f"{dirpath}/SS.{name}_{i:02}.png"
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{cap_time}",
                "-i",
                video_file,
                "-q:v",
                "1",
                "-frames:v",
                "1",
                "-y",  # Overwrite output
                output,
            ]
            cap_time += interval
            cmds.append(cmd_exec(cmd))
        try:
            results = await wait_for(gather(*cmds), timeout=30)
            if results[0][2] != 0:
                await rmtree(dirpath, ignore_errors=True)
                return False
        except Exception:
            await rmtree(dirpath, ignore_errors=True)
            return False
        return dirpath
    return False


async def extract_album_art_with_pil(audio_file, output_path):
    """Extract album art from audio file using PIL/Pillow with memory optimization.

    This function attempts to extract embedded album art from audio files using the
    mutagen library and PIL. It works with MP3, FLAC, M4A, and other audio formats.

    Args:
        audio_file: Path to the audio file
        output_path: Path where the extracted album art should be saved

    Returns:
        bool: True if extraction was successful, False otherwise
    """
    img = None
    try:
        # Import necessary libraries
        import io

        import mutagen
        from PIL import Image

        # Apply memory limits for PIL operations
        limit_memory_for_pil()

        # Load the audio file with mutagen
        audio = mutagen.File(audio_file)
        if audio is None:
            return False

        # Extract album art based on file format
        picture_data = None

        # FLAC
        if hasattr(audio, "pictures") and audio.pictures:
            picture_data = audio.pictures[0].data
        # MP3 (ID3)
        elif hasattr(audio, "tags"):
            # ID3 APIC tag
            if hasattr(audio.tags, "getall") and callable(audio.tags.getall):
                apic_frames = audio.tags.getall("APIC")
                if apic_frames:
                    picture_data = apic_frames[0].data
            # MP4/M4A cover art
            elif hasattr(audio, "tags") and "covr" in audio.tags:
                picture_data = audio.tags["covr"][0]

        # If we found picture data, save it with memory optimization
        if picture_data:
            # Check picture data size to prevent memory issues
            picture_size_mb = len(picture_data) / (1024 * 1024)
            if picture_size_mb > 50:  # Skip very large images (>50MB)
                LOGGER.warning(
                    f"Skipping large album art ({picture_size_mb:.1f}MB) to prevent memory issues"
                )
                return False

            # Open the image data with PIL
            img = Image.open(io.BytesIO(picture_data))

            # Convert to RGB if needed (for PNG with transparency)
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Resize if too large to save memory
            if img.width > 800 or img.height > 800:
                img.thumbnail((800, 800), Image.Resampling.LANCZOS)

            # Save as JPEG with optimized quality
            img.save(output_path, "JPEG", quality=85, optimize=True)

            # Explicitly close the image to free memory
            img.close()
            return True

        return False

    except Exception as e:
        LOGGER.error(f"Error extracting album art with PIL: {e}")
        return False
    finally:
        # Ensure image is closed even if an exception occurs
        if img is not None:
            with contextlib.suppress(Exception):
                img.close()

        # Force garbage collection after image processing
        if smart_garbage_collection is not None:
            smart_garbage_collection(aggressive=False, for_music_download=True)


async def get_audio_thumbnail(audio_file):
    """Extract thumbnail from audio file using memory-efficient approach"""
    output_dir = f"{DOWNLOAD_DIR}thumbnails"
    await makedirs(output_dir, exist_ok=True)
    output = ospath.join(output_dir, f"{time()}.jpg")

    # Check file size first to avoid processing very large files
    try:
        file_size_mb = (await aiopath.getsize(audio_file)) / (1024 * 1024)
        if (
            file_size_mb > 500
        ):  # Skip very large files (>500MB) to prevent memory issues
            LOGGER.warning(
                f"Skipping thumbnail extraction for large audio file ({file_size_mb:.1f}MB)"
            )
            return None
    except Exception:
        pass

    # Simple approach - try to extract embedded album art without audio processing
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        audio_file,
        "-an",  # Disable audio processing
        "-vcodec",
        "copy",
        "-y",  # Overwrite output
        output,
    ]

    try:
        _, _err, code = await wait_for(cmd_exec(cmd), timeout=30)
        if code == 0 and await aiopath.exists(output):
            output_size = await aiopath.getsize(output)
            if output_size > 0:
                # Verify the extracted thumbnail isn't too large
                if output_size > 10 * 1024 * 1024:  # 10MB limit for thumbnails
                    LOGGER.warning(
                        f"Extracted thumbnail too large ({output_size / (1024 * 1024):.1f}MB), removing"
                    )
                    await remove(output)
                else:
                    return output
            else:
                await remove(output)
    except Exception as e:
        LOGGER.error(f"FFmpeg thumbnail extraction failed: {e}")

    # If extraction fails, try PIL method for embedded album art with memory safety
    try:
        # Force garbage collection before PIL operations
        if smart_garbage_collection is not None:
            smart_garbage_collection(aggressive=False, for_music_download=True)

        if await extract_album_art_with_pil(audio_file, output):
            return output
    except Exception as e:
        LOGGER.error(f"PIL thumbnail extraction failed: {e}")

    # If all methods fail, return None to trigger default thumbnail creation
    return None


# Output extension mappings for different track types and codecs
TRACK_OUTPUT_EXTENSIONS = {
    "video": {
        "copy": "mkv",
        "h264": "mp4",
        "libx264": "mp4",
        "h265": "mp4",
        "libx265": "mp4",
        "vp9": "webm",
        "libvpx-vp9": "webm",
        "av1": "mp4",
        "libaom-av1": "mp4",
    },
    "audio": {
        "copy": "mka",
        "aac": "m4a",
        "libfdk_aac": "m4a",
        "mp3": "mp3",
        "libmp3lame": "mp3",
        "opus": "opus",
        "libopus": "opus",
        "flac": "flac",
        "libflac": "flac",
    },
    "subtitle": {
        "copy": "srt",
        "srt": "srt",
        "ass": "ass",
        "ssa": "ssa",
        "vtt": "vtt",
        "webvtt": "vtt",
    },
}


def get_output_extension(track_type, codec, input_codec=None):
    """Get the appropriate output file extension based on track type and codec.

    Args:
        track_type: Type of track (video, audio, subtitle)
        codec: Codec to use for the track (can be None)
        input_codec: Original codec of the track (can be None)

    Returns:
        Appropriate file extension for the track type and codec
    """
    # Normalize codec and input_codec to lowercase if they're strings
    if isinstance(codec, str):
        codec = codec.lower()
    if isinstance(input_codec, str):
        input_codec = input_codec.lower()

    # If codec is None or "None", use default extension for the track type
    if codec is None or codec == "none":
        if track_type == "video":
            return "mkv"
        if track_type == "audio":
            return "mka"
        if track_type == "subtitle":
            # For subtitles, if no codec is specified, preserve the original format
            if input_codec:
                # Handle common subtitle formats
                if input_codec in ["ass", "ssa"]:
                    return "ass"
                if input_codec in ["srt", "subrip"]:
                    return "srt"
                if input_codec in ["vtt", "webvtt"]:
                    return "vtt"
                if input_codec in ["sub", "microdvd"]:
                    return "sub"
                if input_codec in ["idx", "vobsub"]:
                    return "idx"
            # Default to srt if input_codec is unknown or not provided
            return "srt"
        return "bin"  # Generic binary extension

    # If codec is specified, check if it's in the extensions dictionary
    if (
        track_type in TRACK_OUTPUT_EXTENSIONS
        and codec in TRACK_OUTPUT_EXTENSIONS[track_type]
    ):
        return TRACK_OUTPUT_EXTENSIONS[track_type][codec]

    # Special case for subtitle codecs not in the dictionary
    if track_type == "subtitle":
        if codec in ["srt", "subrip"]:
            return "srt"
        if codec in ["ass", "ssa"]:
            return "ass"
        if codec in ["vtt", "webvtt"]:
            return "vtt"
        if codec in ["sub", "microdvd"]:
            return "sub"
        if codec in ["idx", "vobsub"]:
            return "idx"

    # Default extensions if codec not found in the dictionary
    if track_type == "video":
        return "mkv"
    if track_type == "audio":
        return "mka"
    if track_type == "subtitle":
        return "srt"
    return "bin"  # Generic binary extension


async def get_track_info(file_path: str) -> dict[str, list[dict]]:
    """Get information about all tracks in the file using ffprobe.

    Args:
        file_path: Path to the media file

    Returns:
        Dictionary with track types as keys and lists of track info as values
    """
    tracks = {
        "video": [],
        "audio": [],
        "subtitle": [],
        "attachment": [],
    }

    try:
        # Get streams using the existing get_streams function
        streams = await get_streams(file_path)

        if not streams:
            LOGGER.error(f"No streams found in {file_path}")
            return tracks

        # Log all streams for debugging

        for i, stream in enumerate(streams):
            codec_type = stream.get("codec_type", "unknown")
            codec_name = stream.get("codec_name", "unknown")

            if codec_type == "video":
                # Skip attached pictures (cover art) for video tracks
                if stream.get("disposition", {}).get("attached_pic", 0) == 1:
                    continue

                tracks["video"].append(
                    {
                        "index": i,
                        "codec": codec_name,
                        "width": stream.get("width", 0),
                        "height": stream.get("height", 0),
                        "fps": eval(stream.get("r_frame_rate", "0/1")),
                        "language": stream.get("tags", {}).get("language", "und"),
                        "title": stream.get("tags", {}).get(
                            "title", f"Video Track {i}"
                        ),
                        "disposition": stream.get("disposition", {}),
                    }
                )
            elif codec_type == "audio":
                tracks["audio"].append(
                    {
                        "index": i,
                        "codec": codec_name,
                        "channels": stream.get("channels", 0),
                        "sample_rate": stream.get("sample_rate", 0),
                        "language": stream.get("tags", {}).get("language", "und"),
                        "title": stream.get("tags", {}).get(
                            "title", f"Audio Track {i}"
                        ),
                    }
                )
            elif codec_type == "subtitle":
                tracks["subtitle"].append(
                    {
                        "index": i,
                        "codec": codec_name,
                        "language": stream.get("tags", {}).get("language", "und"),
                        "title": stream.get("tags", {}).get(
                            "title", f"Subtitle Track {i}"
                        ),
                    }
                )
            elif codec_type == "attachment":
                tracks["attachment"].append(
                    {
                        "index": i,
                        "filename": stream.get("tags", {}).get(
                            "filename", f"Attachment {i}"
                        ),
                        "mimetype": stream.get("tags", {}).get(
                            "mimetype", "application/octet-stream"
                        ),
                    }
                )
            else:
                pass

        # Log summary of found tracks
    except Exception as e:
        LOGGER.error(f"Error getting track info: {e}")
        # Log the full exception traceback for debugging

    return tracks


async def extract_track(
    file_path: str,
    output_dir: str,
    track_type: str,
    track_indices: int | list[int] | None = None,
    codec: str | None = None,
    maintain_quality: bool = True,
) -> list[str]:
    """Extract specific track(s) from a media file.

    Args:
        file_path: Path to the input file
        output_dir: Directory to save extracted tracks
        track_type: Type of track to extract ('video', 'audio', 'subtitle', 'attachment')
        track_indices: Specific track index or list of indices to extract (None = all tracks of the type)
        codec: Codec to use for extraction
        maintain_quality: Whether to maintain high quality during extraction

    Returns:
        List of paths to extracted files
    """
    try:
        # Create output directory if it doesn't exist
        await makedirs(output_dir, exist_ok=True)

        # Get stream information directly using ffprobe
        streams = await get_streams(file_path)
        if not streams:
            LOGGER.error(f"No streams found in {file_path}")
            return []

        # Get track information
        tracks = await get_track_info(file_path)

        # Skip verbose track logging

        if not tracks[track_type]:
            return []

        # Determine which tracks to extract
        tracks_to_extract = []

        # Check if we should extract all tracks
        extract_all = False

        # Convert single index to list for uniform processing
        indices_list = []
        if track_indices is not None:
            if isinstance(track_indices, list):
                # Check if the list contains the special "all" value
                if any(
                    isinstance(idx, str) and str(idx).lower() == "all"
                    for idx in track_indices
                ):
                    extract_all = True
                else:
                    # Filter valid indices and convert strings to integers
                    for idx in track_indices:
                        if isinstance(idx, int):
                            indices_list.append(idx)
                        elif isinstance(idx, str):
                            if idx.strip().lower() == "all":
                                extract_all = True
                                break
                            if idx.strip().isdigit():
                                indices_list.append(int(idx.strip()))
                            else:
                                pass
            elif isinstance(track_indices, str):
                # Check if it's the special "all" value
                if track_indices.strip().lower() == "all":
                    extract_all = True
                # Check if it's a comma-separated list
                elif "," in track_indices:
                    for idx in track_indices.split(","):
                        if idx.strip().lower() == "all":
                            extract_all = True
                            break
                        if idx.strip().isdigit():
                            indices_list.append(int(idx.strip()))
                        else:
                            pass
                # Check if it's a single digit
                elif track_indices.strip().isdigit():
                    indices_list.append(int(track_indices.strip()))
                else:
                    pass
            elif isinstance(track_indices, int):
                indices_list.append(track_indices)

        # Log the indices we're looking for
        if indices_list or extract_all:
            pass
        else:
            pass

        if indices_list and not extract_all:
            # Extract specific tracks by indices
            tracks_to_extract.extend(
                [
                    track
                    for track in tracks[track_type]
                    if track["index"] in indices_list
                ]
            )

            # Log if no matching tracks were found
            if not tracks_to_extract:
                pass
        else:
            # Extract all tracks of the specified type
            tracks_to_extract = tracks[track_type]

        if not tracks_to_extract:
            return []

        # Extract each track
        extracted_files = []
        for track in tracks_to_extract:
            # Generate output filename
            file_name = os.path.splitext(os.path.basename(file_path))[0]
            language = track.get("language", "und")

            if track_type == "attachment":
                # For attachments, use the original filename if available
                output_file = os.path.join(
                    output_dir,
                    track.get(
                        "filename", f"{file_name}.attachment.{track['index']}"
                    ),
                )
            else:
                # For media tracks, use a descriptive name with track type and index
                input_codec = track.get("codec", "")
                extension = get_output_extension(track_type, codec, input_codec)
                output_file = os.path.join(
                    output_dir,
                    f"{file_name}.{track_type}.{language}.{track['index']}.{extension}",
                )

            # Build FFmpeg command
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                file_path,
                "-y",  # Always overwrite output files
            ]

            if track_type == "attachment":
                # For attachments, use the attachment muxer
                cmd.extend(["-dump_attachment", str(track["index"]), output_file])
            else:
                # For media tracks, map the specific stream
                cmd.extend(["-map", f"0:{track['index']}"])

                # Set codec if specified and not None
                if codec is not None and codec not in {"None", "none"}:
                    if track_type == "video":
                        cmd.extend(["-c:v", codec])
                        if codec != "copy" and maintain_quality:
                            if codec in ["h264", "libx264"]:
                                cmd.extend(
                                    ["-crf", "18", "-preset", "medium"]
                                )  # Changed from slow to medium for better performance
                            elif codec in ["h265", "libx265"]:
                                cmd.extend(
                                    ["-crf", "22", "-preset", "medium"]
                                )  # Changed from slow to medium for better performance
                            elif codec in ["vp9", "libvpx-vp9"]:
                                cmd.extend(["-crf", "30", "-b:v", "0"])
                    elif track_type == "audio":
                        cmd.extend(["-c:a", codec])
                        if codec != "copy" and maintain_quality:
                            if codec in ["aac", "libfdk_aac"] or codec == "mp3":
                                cmd.extend(["-b:a", "320k"])
                            elif codec in ["opus", "libopus"]:
                                cmd.extend(["-b:a", "192k"])
                            elif codec in ["flac", "libflac"]:
                                cmd.extend(
                                    ["-compression_level", "5"]
                                )  # Changed from 8 to 5 for better performance
                    elif track_type == "subtitle":
                        cmd.extend(["-c:s", codec])
                        # Add special handling for ASS to SRT conversion if needed
                        input_codec = track.get("codec", "").lower()
                        if codec == "srt" and input_codec in ["ass", "ssa"]:
                            # Add extra parameters to help with ASS to SRT conversion
                            cmd.extend(["-scodec", "srt"])
                # If no codec is specified, use copy for subtitles
                elif track_type == "subtitle":
                    cmd.extend(["-c:s", "copy"])

                # Add thread count for better performance
                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

                # Add output file
                cmd.append(output_file)

            # Run FFmpeg command
            LOGGER.info(
                f"Extracting {track_type} track {track['index']} from {file_path}"
            )

            try:
                _stdout, stderr, code = await cmd_exec(cmd)
                if (
                    code == 0
                    and await aiopath.exists(output_file)
                    and (await aiopath.getsize(output_file)) > 0
                ):
                    extracted_files.append(output_file)
                    LOGGER.info(f"Successfully extracted to {output_file}")
                else:
                    LOGGER.error(
                        f"Failed to extract {track_type} track {track['index']}: {stderr}"
                    )

                    # Try alternative approach for subtitles if the first attempt failed
                    if track_type == "subtitle":
                        # Handle WebVTT subtitles specially
                        if track.get("codec") == "webvtt":
                            LOGGER.info(
                                f"Detected WebVTT subtitle, trying specialized approach for track {track['index']}"
                            )
                            # For WebVTT, we should keep the original format
                            alt_output_file = os.path.join(
                                output_dir,
                                f"{file_name}.{track_type}.{language}.{track['index']}.vtt",
                            )

                            # Simple file copy for WebVTT files
                            if file_path.lower().endswith(".vtt"):
                                import asyncio
                                import shutil

                                try:
                                    await asyncio.to_thread(
                                        shutil.copy2, file_path, alt_output_file
                                    )
                                    if await aiopath.exists(alt_output_file):
                                        extracted_files.append(alt_output_file)
                                        LOGGER.info(
                                            f"Successfully copied WebVTT file to {alt_output_file}"
                                        )
                                    else:
                                        LOGGER.error(
                                            f"Failed to copy WebVTT file to {alt_output_file}"
                                        )
                                except Exception as e:
                                    LOGGER.error(f"Error copying WebVTT file: {e}")
                            else:
                                # Extract WebVTT from container
                                alt_cmd = [
                                    "xtra",  # Use xtra for WebVTT
                                    "-hide_banner",
                                    "-loglevel",
                                    "error",
                                    "-i",
                                    file_path,
                                    "-map",
                                    f"0:{track['index']}",
                                    "-c:s",
                                    "copy",  # Copy the WebVTT subtitle
                                    "-y",  # Overwrite output file
                                    alt_output_file,
                                ]

                                alt_stdout, alt_stderr, alt_code = await cmd_exec(
                                    alt_cmd
                                )
                                if (
                                    alt_code == 0
                                    and await aiopath.exists(alt_output_file)
                                    and (await aiopath.getsize(alt_output_file)) > 0
                                ):
                                    extracted_files.append(alt_output_file)
                                    LOGGER.info(
                                        f"Successfully extracted WebVTT to {alt_output_file}"
                                    )
                                else:
                                    LOGGER.error(
                                        f"WebVTT extraction failed: {alt_stderr}"
                                    )
                        # For other subtitle formats, try converting to SRT
                        elif codec != "srt":
                            LOGGER.info(
                                f"Trying alternative approach with srt codec for track {track['index']}"
                            )
                            alt_output_file = os.path.join(
                                output_dir,
                                f"{file_name}.{track_type}.{language}.{track['index']}.srt",
                            )

                            alt_cmd = [
                                "xtra",  # Use xtra directly
                                "-hide_banner",
                                "-loglevel",
                                "error",
                                "-i",
                                file_path,
                                "-map",
                                f"0:{track['index']}",
                                "-c:s",
                                "srt",
                                "-y",  # Overwrite output file
                                alt_output_file,
                            ]

                            _alt_stdout, alt_stderr, alt_code = await cmd_exec(
                                alt_cmd
                            )
                            if (
                                alt_code == 0
                                and await aiopath.exists(alt_output_file)
                                and (await aiopath.getsize(alt_output_file)) > 0
                            ):
                                extracted_files.append(alt_output_file)
                                LOGGER.info(
                                    f"Successfully extracted to {alt_output_file} using alternative approach"
                                )
                            else:
                                LOGGER.error(
                                    f"Alternative approach also failed: {alt_stderr}"
                                )
            except Exception as e:
                LOGGER.error(f"Error running FFmpeg: {e}")

        return extracted_files
    except Exception as e:
        LOGGER.error(f"Error extracting {track_type} track: {e}")
        return []


async def extract_all_tracks(
    file_path: str,
    output_dir: str,
    extract_video: bool = True,
    extract_audio: bool = True,
    extract_subtitle: bool = True,
    extract_attachment: bool = True,
    video_codec: str | None = None,
    audio_codec: str | None = None,
    subtitle_codec: str | None = None,
    video_indices: int | list[int] | None = None,
    audio_indices: int | list[int] | None = None,
    subtitle_indices: int | list[int] | None = None,
    attachment_indices: int | list[int] | None = None,
    # Keep single index parameters for backward compatibility
    video_index: int | None = None,
    audio_index: int | None = None,
    subtitle_index: int | None = None,
    attachment_index: int | None = None,
    maintain_quality: bool = True,
) -> list[str]:
    """Extract all specified tracks from a media file.

    Args:
        file_path: Path to the input file
        output_dir: Directory to save extracted tracks
        extract_video: Whether to extract video tracks
        extract_audio: Whether to extract audio tracks
        extract_subtitle: Whether to extract subtitle tracks
        extract_attachment: Whether to extract attachments
        video_codec: Codec to use for video extraction
        audio_codec: Codec to use for audio extraction
        subtitle_codec: Codec to use for subtitle extraction
        video_indices: List of video track indices to extract (None = all)
        audio_indices: List of audio track indices to extract (None = all)
        subtitle_indices: List of subtitle track indices to extract (None = all)
        attachment_indices: List of attachment indices to extract (None = all)
        video_index: Specific video track index to extract (deprecated, use video_indices)
        audio_index: Specific audio track index to extract (deprecated, use audio_indices)
        subtitle_index: Specific subtitle track index to extract (deprecated, use subtitle_indices)
        attachment_index: Specific attachment index to extract (deprecated, use attachment_indices)
        maintain_quality: Whether to maintain high quality during extraction

    Returns:
        List of paths to extracted files
    """
    extracted_files = []

    # Handle backward compatibility - convert single indices to lists if provided
    if video_indices is None and video_index is not None:
        # Check if video_index is a string with comma-separated values
        if isinstance(video_index, str) and "," in video_index:
            video_indices = [
                int(idx.strip())
                for idx in video_index.split(",")
                if idx.strip().isdigit()
            ]
        else:
            video_indices = [video_index]

    if audio_indices is None and audio_index is not None:
        # Check if audio_index is a string with comma-separated values
        if isinstance(audio_index, str) and "," in audio_index:
            audio_indices = [
                int(idx.strip())
                for idx in audio_index.split(",")
                if idx.strip().isdigit()
            ]
        else:
            audio_indices = [audio_index]

    if subtitle_indices is None and subtitle_index is not None:
        # Check if subtitle_index is a string with comma-separated values
        if isinstance(subtitle_index, str) and "," in subtitle_index:
            subtitle_indices = [
                int(idx.strip())
                for idx in subtitle_index.split(",")
                if idx.strip().isdigit()
            ]
        else:
            subtitle_indices = [subtitle_index]

    if attachment_indices is None and attachment_index is not None:
        # Check if attachment_index is a string with comma-separated values
        if isinstance(attachment_index, str) and "," in attachment_index:
            attachment_indices = [
                int(idx.strip())
                for idx in attachment_index.split(",")
                if idx.strip().isdigit()
            ]
        else:
            attachment_indices = [attachment_index]

    if extract_video:
        video_files = await extract_track(
            file_path,
            output_dir,
            "video",
            video_indices,
            video_codec,
            maintain_quality,
        )
        extracted_files.extend(video_files)

    if extract_audio:
        audio_files = await extract_track(
            file_path,
            output_dir,
            "audio",
            audio_indices,
            audio_codec,
            maintain_quality,
        )
        extracted_files.extend(audio_files)

    if extract_subtitle:
        subtitle_files = await extract_track(
            file_path,
            output_dir,
            "subtitle",
            subtitle_indices,
            subtitle_codec,
            maintain_quality,
        )
        extracted_files.extend(subtitle_files)

    if extract_attachment:
        attachment_files = await extract_track(
            file_path,
            output_dir,
            "attachment",
            attachment_indices,
            "copy",  # Codec is ignored for attachments
            maintain_quality,
        )
        extracted_files.extend(attachment_files)

    return extracted_files


async def remove_track(
    file_path: str,
    output_path: str,
    track_type: str,
    track_indices: int | list[int] | None = None,
    remove_metadata: bool = False,
) -> bool:
    """Remove specific track(s) from a media file.

    Args:
        file_path: Path to the input file
        output_path: Path for the output file
        track_type: Type of track to remove ('video', 'audio', 'subtitle', 'attachment')
        track_indices: Specific track index or list of indices to remove (None = all tracks of the type)
        remove_metadata: Whether to remove metadata from the file

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get media info to understand the file structure
        media_info = await get_media_info(file_path)
        if not media_info:
            LOGGER.error(f"Could not get media info for {file_path}")
            return False

        # Build FFmpeg command
        cmd = [
            "xtra",  # Using xtra instead of ffmpeg
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            file_path,
        ]

        # Map all streams first, then remove specific ones
        stream_maps = []

        # Get all streams from media info
        all_streams = media_info[1].get("streams", [])

        for stream in all_streams:
            stream_index = stream.get("index", 0)
            codec_type = stream.get("codec_type", "")

            # Determine if this stream should be included
            should_include = True

            if track_type == "video" and codec_type == "video":
                if track_indices is None:
                    # Remove all video tracks
                    should_include = False
                elif isinstance(track_indices, int):
                    if stream_index == track_indices:
                        should_include = False
                elif isinstance(track_indices, list):
                    if stream_index in track_indices:
                        should_include = False
            elif track_type == "audio" and codec_type == "audio":
                if track_indices is None:
                    # Remove all audio tracks
                    should_include = False
                elif isinstance(track_indices, int):
                    if stream_index == track_indices:
                        should_include = False
                elif isinstance(track_indices, list):
                    if stream_index in track_indices:
                        should_include = False
            elif track_type == "subtitle" and codec_type == "subtitle":
                if track_indices is None:
                    # Remove all subtitle tracks
                    should_include = False
                elif isinstance(track_indices, int):
                    if stream_index == track_indices:
                        should_include = False
                elif isinstance(track_indices, list):
                    if stream_index in track_indices:
                        should_include = False
            elif track_type == "attachment" and codec_type == "attachment":
                if track_indices is None:
                    # Remove all attachment tracks
                    should_include = False
                elif isinstance(track_indices, int):
                    if stream_index == track_indices:
                        should_include = False
                elif isinstance(track_indices, list):
                    if stream_index in track_indices:
                        should_include = False

            # Add stream to map if it should be included
            if should_include:
                stream_maps.extend(["-map", f"0:{stream_index}"])

        # If no streams to keep, return False
        if not stream_maps:
            LOGGER.error("No streams would remain after removal")
            return False

        # Add stream maps to command
        cmd.extend(stream_maps)

        # Copy all streams by default
        cmd.extend(["-c", "copy"])

        # Remove metadata if requested
        if remove_metadata:
            cmd.extend(["-map_metadata", "-1"])

        # Add output file
        cmd.extend(["-y", output_path])

        LOGGER.info(f"Removing {track_type} tracks from {file_path}")
        LOGGER.info(f"Command: {' '.join(cmd)}")

        # Execute the command
        _stdout, stderr, code = await cmd_exec(cmd)

        if code == 0 and await aiopath.exists(output_path):
            file_size = await aiopath.getsize(output_path)
            if file_size > 0:
                LOGGER.info(
                    f"Successfully removed {track_type} tracks to {output_path}"
                )
                return True
            LOGGER.error(f"Output file {output_path} is empty")
            return False
        LOGGER.error(f"FFmpeg failed with code {code}: {stderr}")
        return False

    except Exception as e:
        LOGGER.error(f"Error removing {track_type} track: {e}")
        return False


async def remove_all_tracks(
    file_path: str,
    output_path: str,
    remove_video: bool = False,
    remove_audio: bool = False,
    remove_subtitle: bool = False,
    remove_attachment: bool = False,
    remove_metadata: bool = False,
    video_indices: int | list[int] | None = None,
    audio_indices: int | list[int] | None = None,
    subtitle_indices: int | list[int] | None = None,
    attachment_indices: int | list[int] | None = None,
    # Keep single index parameters for backward compatibility
    video_index: int | None = None,
    audio_index: int | None = None,
    subtitle_index: int | None = None,
    attachment_index: int | None = None,
) -> bool:
    """Remove all specified tracks from a media file.

    Args:
        file_path: Path to the input file
        output_path: Path for the output file
        remove_video: Whether to remove video tracks
        remove_audio: Whether to remove audio tracks
        remove_subtitle: Whether to remove subtitle tracks
        remove_attachment: Whether to remove attachment tracks
        remove_metadata: Whether to remove metadata
        video_indices: List of video track indices to remove
        audio_indices: List of audio track indices to remove
        subtitle_indices: List of subtitle track indices to remove
        attachment_indices: List of attachment track indices to remove
        video_index: Single video track index to remove (backward compatibility)
        audio_index: Single audio track index to remove (backward compatibility)
        subtitle_index: Single subtitle track index to remove (backward compatibility)
        attachment_index: Single attachment track index to remove (backward compatibility)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Handle backward compatibility for single indices
        if video_index is not None:
            video_indices = [video_index] if video_indices is None else video_indices
        if audio_index is not None:
            audio_indices = [audio_index] if audio_indices is None else audio_indices
        if subtitle_index is not None:
            subtitle_indices = (
                [subtitle_index] if subtitle_indices is None else subtitle_indices
            )
        if attachment_index is not None:
            attachment_indices = (
                [attachment_index]
                if attachment_indices is None
                else attachment_indices
            )

        # Get media info to understand the file structure
        media_info = await get_media_info(file_path)
        if not media_info:
            LOGGER.error(f"Could not get media info for {file_path}")
            return False

        # Build FFmpeg command
        cmd = [
            "xtra",  # Using xtra instead of ffmpeg
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            file_path,
        ]

        # Map all streams first, then remove specific ones
        stream_maps = []

        # Get all streams from media info
        all_streams = media_info[1].get("streams", [])

        for stream in all_streams:
            stream_index = stream.get("index", 0)
            codec_type = stream.get("codec_type", "")

            # Determine if this stream should be included
            should_include = True

            if remove_video and codec_type == "video":
                if video_indices is None:
                    # Remove all video tracks
                    should_include = False
                elif stream_index in video_indices:
                    should_include = False
            elif remove_audio and codec_type == "audio":
                if audio_indices is None:
                    # Remove all audio tracks
                    should_include = False
                elif stream_index in audio_indices:
                    should_include = False
            elif remove_subtitle and codec_type == "subtitle":
                if subtitle_indices is None:
                    # Remove all subtitle tracks
                    should_include = False
                elif stream_index in subtitle_indices:
                    should_include = False
            elif remove_attachment and codec_type == "attachment":
                if attachment_indices is None:
                    # Remove all attachment tracks
                    should_include = False
                elif stream_index in attachment_indices:
                    should_include = False

            # Add stream to map if it should be included
            if should_include:
                stream_maps.extend(["-map", f"0:{stream_index}"])

        # If no streams to keep, return False
        if not stream_maps:
            LOGGER.error("No streams would remain after removal")
            return False

        # Add stream maps to command
        cmd.extend(stream_maps)

        # Copy all streams by default
        cmd.extend(["-c", "copy"])

        # Remove metadata if requested
        if remove_metadata:
            cmd.extend(["-map_metadata", "-1"])

        # Add output file
        cmd.extend(["-y", output_path])

        LOGGER.info(f"Removing tracks from {file_path}")
        LOGGER.info(f"Command: {' '.join(cmd)}")

        # Execute the command
        _stdout, stderr, code = await cmd_exec(cmd)

        if code == 0 and await aiopath.exists(output_path):
            file_size = await aiopath.getsize(output_path)
            if file_size > 0:
                LOGGER.info(f"Successfully removed tracks to {output_path}")
                return True
            LOGGER.error(f"Output file {output_path} is empty")
            return False
        LOGGER.error(f"FFmpeg failed with code {code}: {stderr}")
        return False

    except Exception as e:
        LOGGER.error(f"Error removing tracks: {e}")
        return False


async def proceed_remove(
    file_path: str,
    output_dir: str,
    remove_video: bool = False,
    remove_audio: bool = False,
    remove_subtitle: bool = False,
    remove_attachment: bool = False,
    remove_metadata: bool = False,
    video_index: int | None = None,
    audio_index: int | None = None,
    subtitle_index: int | None = None,
    attachment_index: int | None = None,
    ffmpeg_path: str = "xtra",  # Using xtra instead of ffmpeg
    delete_original: bool = False,
    # Parameters for multiple indices
    video_indices: list[int] | None = None,
    audio_indices: list[int] | None = None,
    subtitle_indices: list[int] | None = None,
    attachment_indices: list[int] | None = None,
) -> str | None:
    """Remove tracks from a media file and save to output directory.

    Args:
        file_path: Path to the input file
        output_dir: Directory to save the processed file
        remove_video: Whether to remove video tracks
        remove_audio: Whether to remove audio tracks
        remove_subtitle: Whether to remove subtitle tracks
        remove_attachment: Whether to remove attachment tracks
        remove_metadata: Whether to remove metadata
        video_index: Single video track index to remove (backward compatibility)
        audio_index: Single audio track index to remove (backward compatibility)
        subtitle_index: Single subtitle track index to remove (backward compatibility)
        attachment_index: Single attachment track index to remove (backward compatibility)
        ffmpeg_path: Path to FFmpeg executable
        delete_original: Whether to delete the original file after processing
        video_indices: List of video track indices to remove
        audio_indices: List of audio track indices to remove
        subtitle_indices: List of subtitle track indices to remove
        attachment_indices: List of attachment track indices to remove

    Returns:
        str: Path to the processed file if successful, None otherwise
    """
    try:
        # Ensure output directory exists
        await makedirs(output_dir, exist_ok=True)

        # Generate output filename
        base_name = await aiopath.basename(file_path)
        name, ext = await aiopath.splitext(base_name)
        output_path = await aiopath.join(output_dir, f"{name}_removed{ext}")

        # Handle backward compatibility for single indices
        if video_index is not None:
            video_indices = [video_index] if video_indices is None else video_indices
        if audio_index is not None:
            audio_indices = [audio_index] if audio_indices is None else audio_indices
        if subtitle_index is not None:
            subtitle_indices = (
                [subtitle_index] if subtitle_indices is None else subtitle_indices
            )
        if attachment_index is not None:
            attachment_indices = (
                [attachment_index]
                if attachment_indices is None
                else attachment_indices
            )

        # Remove tracks from the file
        success = await remove_all_tracks(
            file_path,
            output_path,
            remove_video=remove_video,
            remove_audio=remove_audio,
            remove_subtitle=remove_subtitle,
            remove_attachment=remove_attachment,
            remove_metadata=remove_metadata,
            video_indices=video_indices,
            audio_indices=audio_indices,
            subtitle_indices=subtitle_indices,
            attachment_indices=attachment_indices,
        )

        if success:
            # Delete original file if requested
            if delete_original and await aiopath.exists(file_path):
                try:
                    await remove(file_path)
                    LOGGER.info(f"Deleted original file: {file_path}")
                except Exception as e:
                    LOGGER.error(f"Failed to delete original file {file_path}: {e}")

            return output_path
        # Clean up failed output file
        if await aiopath.exists(output_path):
            with contextlib.suppress(Exception):
                await remove(output_path)
        return None

    except Exception as e:
        LOGGER.error(f"Error in proceed_remove: {e}")
        return None


async def remove_tracks(
    file_path: str,
    output_dir: str,
    remove_video: bool = False,
    remove_audio: bool = False,
    remove_subtitle: bool = False,
    remove_attachment: bool = False,
    remove_metadata: bool = False,
    video_indices: list[int] | None = None,
    audio_indices: list[int] | None = None,
    subtitle_indices: list[int] | None = None,
    attachment_indices: list[int] | None = None,
    video_codec: str = "copy",
    audio_codec: str = "copy",
    subtitle_codec: str = "copy",
    delete_original: bool = False,
) -> list[str]:
    """Remove tracks from a media file and save to output directory.

    Args:
        file_path: Path to the input file
        output_dir: Directory to save the processed file
        remove_video: Whether to remove video tracks
        remove_audio: Whether to remove audio tracks
        remove_subtitle: Whether to remove subtitle tracks
        remove_attachment: Whether to remove attachment tracks
        remove_metadata: Whether to remove metadata
        video_indices: List of video track indices to remove
        audio_indices: List of audio track indices to remove
        subtitle_indices: List of subtitle track indices to remove
        attachment_indices: List of attachment track indices to remove
        video_codec: Codec for video tracks (not used in removal)
        audio_codec: Codec for audio tracks (not used in removal)
        subtitle_codec: Codec for subtitle tracks (not used in removal)
        delete_original: Whether to delete the original file after processing

    Returns:
        list[str]: List of paths to processed files
    """
    try:
        # Ensure output directory exists
        await makedirs(output_dir, exist_ok=True)

        # Generate output filename
        base_name = await aiopath.basename(file_path)
        name, ext = await aiopath.splitext(base_name)
        await aiopath.join(output_dir, f"{name}_removed{ext}")

        # Use proceed_remove function to process the file
        result_path = await proceed_remove(
            file_path,
            output_dir,
            remove_video=remove_video,
            remove_audio=remove_audio,
            remove_subtitle=remove_subtitle,
            remove_attachment=remove_attachment,
            remove_metadata=remove_metadata,
            video_indices=video_indices,
            audio_indices=audio_indices,
            subtitle_indices=subtitle_indices,
            attachment_indices=attachment_indices,
            delete_original=delete_original,
        )

        if result_path:
            return [result_path]
        return []

    except Exception as e:
        LOGGER.error(f"Error in remove_tracks: {e}")
        return []


async def proceed_extract(
    file_path: str,
    output_dir: str,
    extract_video: bool = True,
    extract_audio: bool = True,
    extract_subtitle: bool = True,
    extract_attachment: bool = True,
    video_codec: str | None = None,
    audio_codec: str | None = None,
    subtitle_codec: str | None = None,
    video_index: int | None = None,
    audio_index: int | None = None,
    subtitle_index: int | None = None,
    attachment_index: int | None = None,
    maintain_quality: bool = True,
    ffmpeg_path: str = "xtra",  # Using xtra instead of ffmpeg
    delete_original: bool = False,
    # Parameters for multiple indices
    video_indices: list[int] | None = None,
    audio_indices: list[int] | None = None,
    subtitle_indices: list[int] | None = None,
    attachment_indices: list[int] | None = None,
    # Format settings
    video_format: str | None = None,
    audio_format: str | None = None,
    subtitle_format: str | None = None,
    attachment_format: str | None = None,
    # Additional video settings
    video_quality: str | None = None,
    video_preset: str | None = None,
    video_bitrate: str | None = None,
    video_resolution: str | None = None,
    video_fps: str | None = None,
    # Additional audio settings
    audio_bitrate: str | None = None,
    audio_channels: str | None = None,
    audio_sampling: str | None = None,
    audio_volume: str | None = None,
    # Additional subtitle settings
    subtitle_language: str | None = None,
    subtitle_encoding: str | None = None,
    subtitle_font: str | None = None,
    subtitle_font_size: str | None = None,
    # Attachment settings
    attachment_filter: str | None = None,
) -> list[str]:
    """Process extraction of tracks from a media file using FFmpeg asynchronously.

    Args:
        file_path: Path to the input file
        output_dir: Directory to save extracted tracks
        extract_video: Whether to extract video tracks
        extract_audio: Whether to extract audio tracks
        extract_subtitle: Whether to extract subtitle tracks
        extract_attachment: Whether to extract attachments
        video_codec: Codec to use for video extraction
        audio_codec: Codec to use for audio extraction
        subtitle_codec: Codec to use for subtitle extraction
        video_index: Specific video track index to extract (deprecated, use video_indices)
        audio_index: Specific audio track index to extract (deprecated, use audio_indices)
        subtitle_index: Specific subtitle track index to extract (deprecated, use subtitle_indices)
        attachment_index: Specific attachment index to extract (deprecated, use attachment_indices)
        maintain_quality: Whether to maintain high quality during extraction
        ffmpeg_path: Path to the FFmpeg executable
        delete_original: Whether to delete the original file after extraction
        video_indices: List of video track indices to extract (None = all)
        audio_indices: List of audio track indices to extract (None = all)
        subtitle_indices: List of subtitle track indices to extract (None = all)
        attachment_indices: List of attachment indices to extract (None = all)
        video_format: Output format for video extraction (e.g., mp4, mkv)
        audio_format: Output format for audio extraction (e.g., mp3, aac)
        subtitle_format: Output format for subtitle extraction (e.g., srt, ass)
        attachment_format: Output format for attachment extraction
        video_quality: Quality setting for video extraction (e.g., crf value)
        video_preset: Preset for video encoding (e.g., medium, slow)
        video_bitrate: Bitrate for video encoding (e.g., 5M)
        video_resolution: Resolution for video extraction (e.g., 1920x1080)
        video_fps: Frame rate for video extraction (e.g., 30)
        audio_bitrate: Bitrate for audio encoding (e.g., 320k)
        audio_channels: Number of audio channels (e.g., 2)
        audio_sampling: Sampling rate for audio (e.g., 48000)
        audio_volume: Volume adjustment for audio (e.g., 1.5)
        subtitle_language: Language code for subtitle extraction (e.g., eng)
        subtitle_encoding: Character encoding for subtitles (e.g., UTF-8)
        subtitle_font: Font for subtitles (for formats that support it)
        subtitle_font_size: Font size for subtitles
        attachment_filter: Filter for attachment extraction (e.g., *.ttf)

    Returns:
        List of paths to extracted files
    """
    import asyncio
    import os
    from re import IGNORECASE
    from re import search as re_search

    # Check if file exists
    if not os.path.exists(file_path):
        LOGGER.error(f"File not found for extraction: {file_path}")
        return []

    # Check if the file is a split file
    file_name = os.path.basename(file_path)
    if re_search(r"\.part\d+\.(mkv|mp4|avi|mov|ts|webm)$", file_name, IGNORECASE):
        return []

    # Check if file is a valid media file
    try:
        media_type = await get_media_type(file_path)
        if not media_type:
            LOGGER.error(
                f"Unable to determine media type for extraction: {file_path}"
            )
            return []

        # Check if the requested extraction is compatible with the media type
        if extract_video and media_type not in ["video"]:
            extract_video = False

        if extract_audio and media_type not in ["video", "audio"]:
            extract_audio = False

        if extract_subtitle and media_type not in ["video", "subtitle"]:
            extract_subtitle = False

        if extract_attachment and media_type not in ["video"]:
            extract_attachment = False

        # Check if any extraction type is still enabled
        if not any(
            [extract_video, extract_audio, extract_subtitle, extract_attachment]
        ):
            LOGGER.error(
                f"No compatible extraction types for this file: {file_path} (type: {media_type})"
            )
            return []
    except Exception as e:
        LOGGER.error(f"Error determining media type for extraction: {e}")
        return []

    # Create output directory if it doesn't exist
    await makedirs(output_dir, exist_ok=True)

    # Get track information
    tracks = await get_track_info(file_path)

    # Check if we have any tracks to extract
    if not any(tracks.values()):
        return []

    # Prepare extraction commands
    extracted_files = []

    # Process string indices to integers
    # Handle video_index
    if isinstance(video_index, str) and "," in video_index:
        try:
            video_indices = [
                int(idx.strip())
                for idx in video_index.split(",")
                if idx.strip().isdigit()
            ]
        except Exception as e:
            LOGGER.error(f"Error converting video_index string to indices: {e}")

    # Handle audio_index
    if isinstance(audio_index, str) and "," in audio_index:
        try:
            audio_indices = [
                int(idx.strip())
                for idx in audio_index.split(",")
                if idx.strip().isdigit()
            ]
        except Exception as e:
            LOGGER.error(f"Error converting audio_index string to indices: {e}")

    # Handle subtitle_index
    if isinstance(subtitle_index, str) and "," in subtitle_index:
        try:
            subtitle_indices = [
                int(idx.strip())
                for idx in subtitle_index.split(",")
                if idx.strip().isdigit()
            ]
        except Exception as e:
            LOGGER.error(f"Error converting subtitle_index string to indices: {e}")

    # Handle attachment_index
    if isinstance(attachment_index, str) and "," in attachment_index:
        try:
            attachment_indices = [
                int(idx.strip())
                for idx in attachment_index.split(",")
                if idx.strip().isdigit()
            ]
        except Exception as e:
            LOGGER.error(f"Error converting attachment_index string to indices: {e}")

    # Handle attachment extraction separately
    if extract_attachment and tracks["attachment"]:
        # Convert attachment_indices to a list if it's None but attachment_index is provided
        if attachment_indices is None and attachment_index is not None:
            try:
                # Check if attachment_index is a string with comma-separated values
                if isinstance(attachment_index, str) and "," in attachment_index:
                    attachment_indices = [
                        int(idx.strip())
                        for idx in attachment_index.split(",")
                        if idx.strip().isdigit()
                    ]
                else:
                    attachment_indices = (
                        [int(attachment_index)]
                        if isinstance(attachment_index, int | str)
                        and str(attachment_index).isdigit()
                        else None
                    )
            except Exception as e:
                LOGGER.error(f"Error converting attachment_index to integer: {e}")

        # Check if attachment_indices contains the special value "all"
        extract_all_attachments = False

        # If attachment_indices is None, extract all attachments
        if attachment_indices is None:
            extract_all_attachments = True
        # Check for "all" in various formats
        elif isinstance(attachment_indices, list):
            # If it's an empty list, extract all
            if not attachment_indices:
                extract_all_attachments = True
            else:
                # Check for "all" in the list
                for idx in attachment_indices:
                    if isinstance(idx, str) and idx.lower() == "all":
                        extract_all_attachments = True
                        break
        # Check if it's a string equal to "all"
        elif (
            isinstance(attachment_indices, str)
            and attachment_indices.lower() == "all"
        ):
            extract_all_attachments = True

        # Also check attachment_index for "all"
        if (
            not extract_all_attachments
            and attachment_index is not None
            and (
                isinstance(attachment_index, str)
                and attachment_index.lower() == "all"
            )
        ):
            extract_all_attachments = True

        if attachment_indices and not extract_all_attachments:
            # Extract specific attachments by indices
            LOGGER.info(
                f"Extracting only attachment files with indices: {attachment_indices}"
            )
            found_tracks = []
            for track in tracks["attachment"]:
                if track["index"] in attachment_indices:
                    found_tracks.append(track["index"])
                    filename = track.get("filename", f"attachment_{track['index']}")
                    output_path = os.path.join(output_dir, filename)

                    # Try to extract the attachment using multiple methods

                    # Get attachment filename from track info
                    attachment_filename = track.get(
                        "filename", f"attachment_{track['index']}"
                    )

                    # Create a more descriptive output path if possible
                    if attachment_filename:
                        # Ensure the filename is safe for the filesystem
                        safe_filename = "".join(
                            c
                            for c in attachment_filename
                            if c.isalnum() or c in "._- "
                        )
                        output_path = os.path.join(output_dir, safe_filename)

                        # If the filename already exists, add the index to make it unique
                        if await aiopath.exists(output_path):
                            base_name, ext = os.path.splitext(safe_filename)
                            output_path = os.path.join(
                                output_dir, f"{base_name}_{track['index']}{ext}"
                            )

                    # Create a temporary directory for extraction attempts
                    temp_dir = os.path.join(output_dir, "temp_attachments")
                    await makedirs(temp_dir, exist_ok=True)

                    # Method 1: Use -dump_attachment option (works in some FFmpeg versions)
                    cmd = [
                        ffmpeg_path,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-dump_attachment",
                        str(track["index"]),
                        "-i",
                        file_path,
                        output_path,
                    ]

                    extraction_success = False

                    try:
                        proc = await create_subprocess_exec(
                            *cmd, stdout=PIPE, stderr=PIPE
                        )

                        _, stderr = await proc.communicate()

                        if (
                            proc.returncode == 0
                            and await aiopath.exists(output_path)
                            and await get_path_size(output_path) > 0
                        ):
                            extracted_files.append(output_path)
                            LOGGER.info(
                                f"Successfully extracted attachment to {output_path} using method 1"
                            )
                            extraction_success = True
                        else:
                            stderr_text = (
                                stderr.decode() if stderr else "Unknown error"
                            )
                    except Exception:
                        pass

                    # Method 2: Try using -map option with data format
                    if not extraction_success:
                        temp_file = os.path.join(
                            temp_dir, f"attachment_{track['index']}.bin"
                        )

                        alt_cmd = [
                            ffmpeg_path,
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-i",
                            file_path,
                            "-map",
                            f"0:{track['index']}",
                            "-c",
                            "copy",
                            "-f",
                            "data",
                            temp_file,
                        ]

                        try:
                            alt_proc = await create_subprocess_exec(
                                *alt_cmd, stdout=PIPE, stderr=PIPE
                            )

                            _, alt_stderr = await alt_proc.communicate()

                            if (
                                alt_proc.returncode == 0
                                and await aiopath.exists(temp_file)
                                and await get_path_size(temp_file) > 0
                            ):
                                # Copy the temporary file to the output path
                                await aiofiles.os.rename(temp_file, output_path)
                                extracted_files.append(output_path)
                                LOGGER.info(
                                    f"Successfully extracted attachment to {output_path} using method 2"
                                )
                                extraction_success = True
                            else:
                                alt_stderr_text = (
                                    alt_stderr.decode()
                                    if alt_stderr
                                    else "Unknown error"
                                )
                        except Exception:
                            pass

                    # Method 3: Try using -c:t copy for attachments
                    if not extraction_success:
                        temp_file = os.path.join(
                            temp_dir, f"attachment_{track['index']}_method3.bin"
                        )

                        alt_cmd = [
                            ffmpeg_path,
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-i",
                            file_path,
                            "-map",
                            f"0:{track['index']}",
                            "-c:t",
                            "copy",
                            temp_file,
                        ]

                        try:
                            alt_proc = await create_subprocess_exec(
                                *alt_cmd, stdout=PIPE, stderr=PIPE
                            )

                            _, alt_stderr = await alt_proc.communicate()

                            if (
                                alt_proc.returncode == 0
                                and await aiopath.exists(temp_file)
                                and await get_path_size(temp_file) > 0
                            ):
                                # Copy the temporary file to the output path
                                await aiofiles.os.rename(temp_file, output_path)
                                extracted_files.append(output_path)
                                LOGGER.info(
                                    f"Successfully extracted attachment to {output_path} using method 3"
                                )
                                extraction_success = True
                            else:
                                alt_stderr_text = (
                                    alt_stderr.decode()
                                    if alt_stderr
                                    else "Unknown error"
                                )
                        except Exception:
                            pass

                    # If all methods failed, create a placeholder file
                    if not extraction_success:
                        try:
                            # Create an empty file with a note about the failure
                            async with aiofiles.open(output_path, "w") as f:
                                await f.write(
                                    f"Failed to extract attachment {track['index']} - {track.get('filename', '')}"
                                )
                        except Exception as write_e:
                            LOGGER.error(
                                f"Error creating placeholder file: {write_e}"
                            )

            # Check if any tracks were found
            if not found_tracks:
                pass
        elif extract_all_attachments:
            # Extract all attachments
            LOGGER.info(f"Extracting all attachment files from {file_path}")
            for track in tracks["attachment"]:
                filename = track.get("filename", f"attachment_{track['index']}")
                output_path = os.path.join(output_dir, filename)

                # Try to extract the attachment using multiple methods

                # Get attachment filename from track info
                attachment_filename = track.get(
                    "filename", f"attachment_{track['index']}"
                )

                # Create a more descriptive output path if possible
                if attachment_filename:
                    # Ensure the filename is safe for the filesystem
                    safe_filename = "".join(
                        c for c in attachment_filename if c.isalnum() or c in "._- "
                    )
                    output_path = os.path.join(output_dir, safe_filename)

                    # If the filename already exists, add the index to make it unique
                    if await aiopath.exists(output_path):
                        base_name, ext = os.path.splitext(safe_filename)
                        output_path = os.path.join(
                            output_dir, f"{base_name}_{track['index']}{ext}"
                        )

                # Create a temporary directory for extraction attempts
                temp_dir = os.path.join(output_dir, "temp_attachments")
                await makedirs(temp_dir, exist_ok=True)

                # Method 1: Use -dump_attachment option (works in some FFmpeg versions)
                cmd = [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-dump_attachment",
                    str(track["index"]),
                    "-i",
                    file_path,
                    output_path,
                ]

                extraction_success = False

                try:
                    proc = await create_subprocess_exec(
                        *cmd, stdout=PIPE, stderr=PIPE
                    )

                    _, stderr = await proc.communicate()

                    if (
                        proc.returncode == 0
                        and await aiopath.exists(output_path)
                        and await get_path_size(output_path) > 0
                    ):
                        extracted_files.append(output_path)
                        LOGGER.info(
                            f"Successfully extracted attachment to {output_path} using method 1"
                        )
                        extraction_success = True
                    else:
                        stderr_text = stderr.decode() if stderr else "Unknown error"
                except Exception:
                    pass

                # Method 2: Try using -map option with data format
                if not extraction_success:
                    temp_file = os.path.join(
                        temp_dir, f"attachment_{track['index']}.bin"
                    )

                    alt_cmd = [
                        ffmpeg_path,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        file_path,
                        "-map",
                        f"0:{track['index']}",
                        "-c",
                        "copy",
                        "-f",
                        "data",
                        temp_file,
                    ]

                    try:
                        alt_proc = await create_subprocess_exec(
                            *alt_cmd, stdout=PIPE, stderr=PIPE
                        )

                        _, alt_stderr = await alt_proc.communicate()

                        if (
                            alt_proc.returncode == 0
                            and await aiopath.exists(temp_file)
                            and await get_path_size(temp_file) > 0
                        ):
                            # Copy the temporary file to the output path
                            await aiofiles.os.rename(temp_file, output_path)
                            extracted_files.append(output_path)
                            LOGGER.info(
                                f"Successfully extracted attachment to {output_path} using method 2"
                            )
                            extraction_success = True
                        else:
                            alt_stderr_text = (
                                alt_stderr.decode()
                                if alt_stderr
                                else "Unknown error"
                            )
                    except Exception:
                        pass

                # Method 3: Try using -c:t copy for attachments
                if not extraction_success:
                    temp_file = os.path.join(
                        temp_dir, f"attachment_{track['index']}_method3.bin"
                    )

                    alt_cmd = [
                        ffmpeg_path,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        file_path,
                        "-map",
                        f"0:{track['index']}",
                        "-c:t",
                        "copy",
                        temp_file,
                    ]

                    try:
                        alt_proc = await create_subprocess_exec(
                            *alt_cmd, stdout=PIPE, stderr=PIPE
                        )

                        _, alt_stderr = await alt_proc.communicate()

                        if (
                            alt_proc.returncode == 0
                            and await aiopath.exists(temp_file)
                            and await get_path_size(temp_file) > 0
                        ):
                            # Copy the temporary file to the output path
                            await aiofiles.os.rename(temp_file, output_path)
                            extracted_files.append(output_path)
                            LOGGER.info(
                                f"Successfully extracted attachment to {output_path} using method 3"
                            )
                            extraction_success = True
                        else:
                            alt_stderr_text = (
                                alt_stderr.decode()
                                if alt_stderr
                                else "Unknown error"
                            )
                    except Exception:
                        pass

                # If all methods failed, create a placeholder file
                if not extraction_success:
                    try:
                        # Create an empty file with a note about the failure
                        async with aiofiles.open(output_path, "w") as f:
                            await f.write(
                                f"Failed to extract attachment {track['index']} - {track.get('filename', '')}"
                            )
                    except Exception as write_e:
                        LOGGER.error(f"Error creating placeholder file: {write_e}")

    # Extract video tracks
    if extract_video and tracks["video"]:
        # Convert video_indices to a list if it's None but video_index is provided
        if video_indices is None and video_index is not None:
            try:
                # Check if video_index is a string with comma-separated values
                if isinstance(video_index, str) and "," in video_index:
                    video_indices = [
                        int(idx.strip())
                        for idx in video_index.split(",")
                        if idx.strip().isdigit()
                    ]
                else:
                    video_indices = (
                        [int(video_index)]
                        if isinstance(video_index, int | str)
                        and str(video_index).isdigit()
                        else None
                    )
            except Exception as e:
                LOGGER.error(f"Error converting video_index to integer: {e}")

        # Check if video_indices contains the special value "all"
        extract_all_videos = False

        # If video_indices is None, extract all videos
        if video_indices is None:
            extract_all_videos = True
        # Check for "all" in various formats
        elif isinstance(video_indices, list):
            # If it's an empty list, extract all
            if not video_indices:
                extract_all_videos = True
            else:
                # Check for "all" in the list
                for idx in video_indices:
                    if isinstance(idx, str) and idx.lower() == "all":
                        extract_all_videos = True
                        break
        # Check if it's a string equal to "all"
        elif isinstance(video_indices, str) and video_indices.lower() == "all":
            extract_all_videos = True

        # Also check video_index for "all"
        if (
            not extract_all_videos
            and video_index is not None
            and isinstance(video_index, str)
            and video_index.lower() == "all"
        ):
            extract_all_videos = True

        if video_indices and not extract_all_videos:
            # Extract specific video tracks by indices
            LOGGER.info(
                f"Extracting only video tracks with indices: {video_indices}"
            )
            found_tracks = []
            for track in tracks["video"]:
                if track["index"] in video_indices:
                    found_tracks.append(track["index"])
                    # Skip attached pictures (cover art)
                    if (
                        "disposition" in track
                        and track["disposition"].get("attached_pic", 0) == 1
                    ):
                        continue

                    # Determine output extension based on format config if available
                    # Use the video_format parameter passed to the function
                    if (
                        "video_format" in locals()
                        and video_format
                        and video_format.lower() != "none"
                    ):
                        output_ext = video_format
                    else:
                        # Otherwise use the codec-based extension
                        output_ext = get_output_extension("video", video_codec)

                    output_file = os.path.join(
                        output_dir,
                        f"{os.path.splitext(os.path.basename(file_path))[0]}.video.{track.get('language', 'und')}.{track['index']}.{output_ext}",
                    )

                    # Build FFmpeg command
                    cmd = [
                        ffmpeg_path,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        file_path,
                        "-map",
                        f"0:{track['index']}",
                    ]

                    # Add video codec only if specified and not None
                    if video_codec is not None and video_codec not in {
                        "None",
                        "none",
                    }:
                        cmd.extend(["-c:v", video_codec])

                        # Add quality settings if not using copy codec
                        if video_codec != "copy":
                            # Use custom quality settings if provided
                            if video_quality:
                                cmd.extend(["-crf", video_quality])
                            elif maintain_quality:
                                if video_codec in ["h264", "libx264"]:
                                    cmd.extend(["-crf", "18"])
                                elif video_codec in ["h265", "libx265"]:
                                    cmd.extend(["-crf", "22"])
                                elif video_codec in ["vp9", "libvpx-vp9"]:
                                    cmd.extend(["-crf", "30"])

                            # Use custom preset if provided
                            if video_preset:
                                cmd.extend(["-preset", video_preset])
                            elif maintain_quality:
                                cmd.extend(["-preset", "medium"])  # Default preset

                            # Use custom bitrate if provided
                            if video_bitrate:
                                cmd.extend(["-b:v", video_bitrate])
                            elif (
                                video_codec in ["vp9", "libvpx-vp9"]
                                and maintain_quality
                            ):
                                cmd.extend(["-b:v", "0"])

                            # Use custom resolution if provided
                            if video_resolution:
                                cmd.extend(["-s", video_resolution])

                            # Use custom fps if provided
                            if video_fps:
                                cmd.extend(["-r", video_fps])

                    # Add thread count for better performance
                    cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

                    cmd.append(output_file)

                    # Run the command
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )

                        _, stderr = await proc.communicate()

                        if proc.returncode == 0 and os.path.exists(output_file):
                            extracted_files.append(output_file)
                        else:
                            stderr_text = (
                                stderr.decode() if stderr else "Unknown error"
                            )
                            LOGGER.error(f"Failed to extract video: {stderr_text}")
                            # Log the command that failed
                    except Exception as e:
                        LOGGER.error(
                            f"Error running FFmpeg for video extraction: {e}"
                        )
                        # Log the command that failed

            # Check if any tracks were found
            if not found_tracks:
                pass
        elif extract_all_videos:
            # Extract all video tracks
            LOGGER.info(f"Extracting all video tracks from {file_path}")
            for track in tracks["video"]:
                # Skip attached pictures (cover art)
                if (
                    "disposition" in track
                    and track["disposition"].get("attached_pic", 0) == 1
                ):
                    continue

                # Determine output extension based on format config if available
                # Use the video_format parameter passed to the function
                if (
                    "video_format" in locals()
                    and video_format
                    and video_format.lower() != "none"
                ):
                    output_ext = video_format
                else:
                    # Otherwise use the codec-based extension
                    output_ext = get_output_extension("video", video_codec)

                output_file = os.path.join(
                    output_dir,
                    f"{os.path.splitext(os.path.basename(file_path))[0]}.video.{track.get('language', 'und')}.{track['index']}.{output_ext}",
                )

                # Build FFmpeg command
                cmd = [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    file_path,
                    "-map",
                    f"0:{track['index']}",
                ]

                # Add video codec only if specified and not None
                if video_codec is not None and video_codec not in {"None", "none"}:
                    cmd.extend(["-c:v", video_codec])

                    # Add quality settings if not using copy codec
                    if video_codec != "copy":
                        # Use custom quality settings if provided
                        if video_quality:
                            cmd.extend(["-crf", video_quality])
                        elif maintain_quality:
                            if video_codec in ["h264", "libx264"]:
                                cmd.extend(["-crf", "18"])
                            elif video_codec in ["h265", "libx265"]:
                                cmd.extend(["-crf", "22"])
                            elif video_codec in ["vp9", "libvpx-vp9"]:
                                cmd.extend(["-crf", "30"])

                        # Use custom preset if provided
                        if video_preset:
                            cmd.extend(["-preset", video_preset])
                        elif maintain_quality:
                            cmd.extend(["-preset", "medium"])  # Default preset

                        # Use custom bitrate if provided
                        if video_bitrate:
                            cmd.extend(["-b:v", video_bitrate])
                        elif (
                            video_codec in ["vp9", "libvpx-vp9"] and maintain_quality
                        ):
                            cmd.extend(["-b:v", "0"])

                        # Use custom resolution if provided
                        if video_resolution:
                            cmd.extend(["-s", video_resolution])

                        # Use custom fps if provided
                        if video_fps:
                            cmd.extend(["-r", video_fps])

                # Add thread count for better performance
                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

                cmd.append(output_file)

                # Run the command
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    _, stderr = await proc.communicate()

                    if proc.returncode == 0 and os.path.exists(output_file):
                        extracted_files.append(output_file)
                        LOGGER.info(f"Successfully extracted video to {output_file}")
                    else:
                        stderr_text = stderr.decode() if stderr else "Unknown error"
                        LOGGER.error(f"Failed to extract video: {stderr_text}")
                        # Log the command that failed
                except Exception as e:
                    LOGGER.error(f"Error running FFmpeg for video extraction: {e}")
                    # Log the command that failed

    # Extract audio tracks
    if extract_audio and tracks["audio"]:
        # Convert audio_indices to a list if it's None but audio_index is provided
        if audio_indices is None and audio_index is not None:
            try:
                # Check if audio_index is a string with comma-separated values
                if isinstance(audio_index, str) and "," in audio_index:
                    audio_indices = [
                        int(idx.strip())
                        for idx in audio_index.split(",")
                        if idx.strip().isdigit()
                    ]
                else:
                    audio_indices = (
                        [int(audio_index)]
                        if isinstance(audio_index, int | str)
                        and str(audio_index).isdigit()
                        else None
                    )
            except Exception as e:
                LOGGER.error(f"Error converting audio_index to integer: {e}")

        # Check if audio_indices contains the special value "all"
        extract_all_audios = False

        # If audio_indices is None, extract all audios
        if audio_indices is None:
            extract_all_audios = True
        # Check for "all" in various formats
        elif isinstance(audio_indices, list):
            # If it's an empty list, extract all
            if not audio_indices:
                extract_all_audios = True
            else:
                # Check for "all" in the list
                for idx in audio_indices:
                    if isinstance(idx, str) and idx.lower() == "all":
                        extract_all_audios = True
                        break
        # Check if it's a string equal to "all"
        elif isinstance(audio_indices, str) and audio_indices.lower() == "all":
            extract_all_audios = True

        # Also check audio_index for "all"
        if (
            not extract_all_audios
            and audio_index is not None
            and isinstance(audio_index, str)
            and audio_index.lower() == "all"
        ):
            extract_all_audios = True

        if audio_indices and not extract_all_audios:
            # Extract specific audio tracks by indices
            LOGGER.info(
                f"Extracting only audio tracks with indices: {audio_indices}"
            )
            found_tracks = []
            for track in tracks["audio"]:
                if track["index"] in audio_indices:
                    found_tracks.append(track["index"])
                    # Determine output extension based on format config if available
                    # Use the audio_format parameter passed to the function
                    if (
                        "audio_format" in locals()
                        and audio_format
                        and audio_format.lower() != "none"
                    ):
                        output_ext = audio_format
                    else:
                        # Otherwise use the codec-based extension
                        output_ext = get_output_extension("audio", audio_codec)

                    output_file = os.path.join(
                        output_dir,
                        f"{os.path.splitext(os.path.basename(file_path))[0]}.audio.{track.get('language', 'und')}.{track['index']}.{output_ext}",
                    )

                    # Build FFmpeg command
                    cmd = [
                        ffmpeg_path,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        file_path,
                        "-map",
                        f"0:{track['index']}",
                    ]

                    # Add audio codec only if specified and not None
                    if audio_codec is not None and audio_codec not in {
                        "None",
                        "none",
                    }:
                        cmd.extend(["-c:a", audio_codec])

                        # Add quality settings if not using copy codec
                        if audio_codec != "copy":
                            # Use custom bitrate if provided
                            if audio_bitrate:
                                cmd.extend(["-b:a", audio_bitrate])
                            elif maintain_quality:
                                if audio_codec in ["aac", "libfdk_aac", "mp3"]:
                                    cmd.extend(["-b:a", "320k"])
                                elif audio_codec in ["opus", "libopus"]:
                                    cmd.extend(["-b:a", "192k"])

                            # Use custom channels if provided
                            if audio_channels:
                                cmd.extend(["-ac", audio_channels])

                            # Use custom sampling rate if provided
                            if audio_sampling:
                                cmd.extend(["-ar", audio_sampling])

                            # Use custom volume if provided
                            if audio_volume:
                                cmd.extend(["-filter:a", f"volume={audio_volume}"])

                            # Add compression level for FLAC
                            if (
                                audio_codec in ["flac", "libflac"]
                                and maintain_quality
                            ):
                                cmd.extend(
                                    ["-compression_level", "5"]
                                )  # Changed from 8 to 5 for better performance

                    # Add thread count for better performance
                    cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

                    cmd.append(output_file)

                    # Run the command
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )

                        _, stderr = await proc.communicate()

                        if proc.returncode == 0 and os.path.exists(output_file):
                            extracted_files.append(output_file)
                        else:
                            stderr_text = (
                                stderr.decode() if stderr else "Unknown error"
                            )
                            LOGGER.error(f"Failed to extract audio: {stderr_text}")
                            # Log the command that failed
                    except Exception as e:
                        LOGGER.error(
                            f"Error running FFmpeg for audio extraction: {e}"
                        )
                        # Log the command that failed

            # Check if any tracks were found
            if not found_tracks:
                pass
        elif extract_all_audios:
            # Extract all audio tracks
            LOGGER.info(f"Extracting all audio tracks from {file_path}")
            for track in tracks["audio"]:
                # Determine output extension based on format config if available
                # Use the audio_format parameter passed to the function
                if (
                    "audio_format" in locals()
                    and audio_format
                    and audio_format.lower() != "none"
                ):
                    output_ext = audio_format
                else:
                    # Otherwise use the codec-based extension
                    output_ext = get_output_extension("audio", audio_codec)

                output_file = os.path.join(
                    output_dir,
                    f"{os.path.splitext(os.path.basename(file_path))[0]}.audio.{track.get('language', 'und')}.{track['index']}.{output_ext}",
                )

                # Build FFmpeg command
                cmd = [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    file_path,
                    "-map",
                    f"0:{track['index']}",
                ]

                # Add audio codec only if specified and not None
                if audio_codec is not None and audio_codec not in {"None", "none"}:
                    cmd.extend(["-c:a", audio_codec])

                    # Add quality settings if not using copy codec and maintain_quality is True
                    if audio_codec != "copy":
                        # Use custom bitrate if provided
                        if audio_bitrate:
                            cmd.extend(["-b:a", audio_bitrate])
                        elif maintain_quality:
                            if audio_codec in ["aac", "libfdk_aac", "mp3"]:
                                cmd.extend(["-b:a", "320k"])
                            elif audio_codec in ["opus", "libopus"]:
                                cmd.extend(["-b:a", "192k"])

                        # Use custom channels if provided
                        if audio_channels:
                            cmd.extend(["-ac", audio_channels])

                        # Use custom sampling rate if provided
                        if audio_sampling:
                            cmd.extend(["-ar", audio_sampling])

                        # Use custom volume if provided
                        if audio_volume:
                            cmd.extend(["-filter:a", f"volume={audio_volume}"])

                        # Add compression level for FLAC
                        if audio_codec in ["flac", "libflac"] and maintain_quality:
                            cmd.extend(
                                ["-compression_level", "5"]
                            )  # Changed from 8 to 5 for better performance

                # Add thread count for better performance
                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

                cmd.append(output_file)

                # Run the command
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    _, stderr = await proc.communicate()

                    if proc.returncode == 0 and os.path.exists(output_file):
                        extracted_files.append(output_file)
                        LOGGER.info(f"Successfully extracted audio to {output_file}")
                    else:
                        stderr_text = stderr.decode() if stderr else "Unknown error"
                        LOGGER.error(f"Failed to extract audio: {stderr_text}")
                        # Log the command that failed
                except Exception as e:
                    LOGGER.error(f"Error running FFmpeg for audio extraction: {e}")
                    # Log the command that failed

    # Extract subtitle tracks
    if extract_subtitle and tracks["subtitle"]:
        # Skip verbose track logging

        # Convert subtitle_indices to a list if it's None but subtitle_index is provided
        if subtitle_indices is None and subtitle_index is not None:
            try:
                # Check if subtitle_index is a string with comma-separated values
                if isinstance(subtitle_index, str) and "," in subtitle_index:
                    subtitle_indices = [
                        int(idx.strip())
                        for idx in subtitle_index.split(",")
                        if idx.strip().isdigit()
                    ]
                    LOGGER.info(
                        f"Converted subtitle_index string '{subtitle_index}' to indices: {subtitle_indices}"
                    )
                elif (
                    isinstance(subtitle_index, str)
                    and subtitle_index.strip().lower() == "all"
                ):
                    subtitle_indices = "all"
                    LOGGER.info(
                        "Subtitle index is 'all', will extract all subtitle tracks"
                    )
                elif (
                    isinstance(subtitle_index, int | str)
                    and str(subtitle_index).isdigit()
                ):
                    subtitle_indices = [int(subtitle_index)]
                    LOGGER.info(f"Using single subtitle index: {subtitle_indices}")
                else:
                    subtitle_indices = None
                    LOGGER.info(
                        "No valid subtitle index provided, will extract all subtitle tracks"
                    )
            except Exception as e:
                LOGGER.error(f"Error converting subtitle_index to integer: {e}")
                # Log the full exception traceback for debugging

        # Check if subtitle_indices contains the special value "all"
        extract_all_subtitles = False

        # If subtitle_indices is None, extract all subtitles
        if subtitle_indices is None:
            extract_all_subtitles = True
        # Check for "all" in various formats
        elif isinstance(subtitle_indices, list):
            # If it's an empty list, extract all
            if not subtitle_indices:
                extract_all_subtitles = True
            else:
                # Check for "all" in the list
                for idx in subtitle_indices:
                    if isinstance(idx, str) and idx.lower() == "all":
                        extract_all_subtitles = True
                        break
        # Check if it's a string equal to "all"
        elif isinstance(subtitle_indices, str) and subtitle_indices.lower() == "all":
            extract_all_subtitles = True

        # Also check subtitle_index for "all"
        if (
            not extract_all_subtitles
            and subtitle_index is not None
            and isinstance(subtitle_index, str)
            and subtitle_index.lower() == "all"
        ):
            extract_all_subtitles = True

        # If no indices are specified, extract all
        if (
            subtitle_indices is None
            or (isinstance(subtitle_indices, list) and not subtitle_indices)
        ) and subtitle_index is None:
            extract_all_subtitles = True

        if (
            subtitle_indices is not None
            and not isinstance(subtitle_indices, str)
            and not extract_all_subtitles
        ):
            # Extract specific subtitle tracks by indices
            LOGGER.info(
                f"Extracting only subtitle tracks with indices: {subtitle_indices}"
            )
            found_tracks = []
            for track in tracks["subtitle"]:
                if subtitle_indices and track["index"] in subtitle_indices:
                    found_tracks.append(track["index"])
                    LOGGER.info(
                        f"Found subtitle track with index {track['index']} to extract"
                    )

                    # Determine output extension based on format config if available
                    # Use the subtitle_format parameter passed to the function

                    # Get the input codec
                    input_codec = track.get("codec", "").lower()

                    # Determine the output codec based on settings
                    output_codec = (
                        subtitle_codec.lower()
                        if subtitle_codec and subtitle_codec.lower() != "none"
                        else "copy"
                    )

                    # Determine the output extension based on the codec
                    if output_codec == "copy":
                        # When using copy, use the same extension as the input
                        if input_codec in ["ass", "ssa"]:
                            output_ext = "ass"
                        elif input_codec in {"srt", "subrip"}:
                            output_ext = "srt"
                        elif input_codec in {"vtt", "webvtt"}:
                            output_ext = "vtt"
                        else:
                            # Default to a generic extension
                            output_ext = "sub"
                    elif output_codec == "srt":
                        output_ext = "srt"
                    elif output_codec == "ass":
                        output_ext = "ass"
                    elif output_codec in {"webvtt", "vtt"}:
                        output_ext = "vtt"
                    else:
                        # Use the output codec as the extension
                        output_ext = output_codec

                    # Override with format if specified
                    if subtitle_format and subtitle_format.lower() != "none":
                        output_ext = subtitle_format

                    output_file = os.path.join(
                        output_dir,
                        f"{os.path.splitext(os.path.basename(file_path))[0]}.subtitle.{track.get('language', 'und')}.{track['index']}.{output_ext}",
                    )

                    # Build FFmpeg command
                    cmd = [
                        ffmpeg_path,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        file_path,
                        "-map",
                        f"0:{track['index']}",
                    ]

                    # Handle subtitle codec based on input and output formats
                    input_codec = track.get("codec", "").lower()

                    # Normalize input codec names
                    if input_codec == "subrip":
                        input_codec = "srt"
                    elif input_codec in ["ass", "ssa"]:
                        input_codec = "ass"

                    # Determine output format based on subtitle_format or codec
                    output_format = None
                    if subtitle_format and subtitle_format.lower() != "none":
                        output_format = subtitle_format.lower()
                    elif subtitle_codec and subtitle_codec.lower() != "none":
                        if subtitle_codec.lower() == "copy":
                            output_format = input_codec
                        else:
                            output_format = subtitle_codec.lower()
                    else:
                        # Default to SRT if no format/codec specified
                        output_format = "srt"

                    # Handle format conversion
                    if output_format and output_format != input_codec:
                        # Converting between formats
                        if output_format == "srt" and input_codec in ["ass", "ssa"]:
                            # Converting from ASS/SSA to SRT
                            cmd.extend(["-c:s", "srt"])
                        elif output_format == "ass" and input_codec == "srt":
                            # Converting from SRT to ASS
                            cmd.extend(["-c:s", "ass"])
                        elif output_format == "vtt" and input_codec in [
                            "srt",
                            "ass",
                            "ssa",
                        ]:
                            # Converting to WebVTT
                            cmd.extend(["-c:s", "webvtt"])
                        # For other conversions, let FFmpeg choose the appropriate codec
                        elif subtitle_codec and subtitle_codec.lower() != "none":
                            cmd.extend(["-c:s", subtitle_codec])
                    # No conversion needed, use copy if possible
                    elif input_codec in ["ass", "ssa", "srt", "vtt", "webvtt"]:
                        cmd.extend(["-c:s", "copy"])
                    # For other formats, let FFmpeg choose the appropriate codec
                    elif subtitle_codec and subtitle_codec.lower() != "none":
                        cmd.extend(["-c:s", subtitle_codec])
                    else:
                        # Default to SRT for unknown formats
                        cmd.extend(["-c:s", "srt"])

                    # For ASS/SSA subtitles, make sure the output format matches the codec
                    if input_codec in ["ass", "ssa"] and output_format == "srt":
                        # Force output format to match the codec
                        cmd.extend(["-f", "srt"])

                        # Make sure the output file has the correct extension
                        output_file = os.path.splitext(output_file)[0] + ".srt"

                    # Add subtitle language if specified
                    if subtitle_language:
                        cmd.extend(
                            ["-metadata:s:s:0", f"language={subtitle_language}"]
                        )

                    # Add subtitle encoding if specified
                    if subtitle_encoding:
                        cmd.extend(["-sub_charenc", subtitle_encoding])

                    # Add subtitle font if specified
                    if subtitle_font and subtitle_codec in ["ass", "ssa"]:
                        cmd.extend(["-metadata:s:s:0", f"font={subtitle_font}"])

                    # Add subtitle font size if specified
                    if subtitle_font_size and subtitle_codec in ["ass", "ssa"]:
                        cmd.extend(
                            ["-metadata:s:s:0", f"fontsize={subtitle_font_size}"]
                        )

                    cmd.append(output_file)

                    LOGGER.info(
                        f"Extracting subtitle track {track['index']} from {file_path}"
                    )

                    # Run the command
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )

                        _, stderr = await proc.communicate()

                        if (
                            proc.returncode == 0
                            and os.path.exists(output_file)
                            and os.path.getsize(output_file) > 0
                        ):
                            extracted_files.append(output_file)
                            LOGGER.info(
                                f"Successfully extracted subtitle to {output_file}"
                            )
                        else:
                            stderr_text = (
                                stderr.decode() if stderr else "Unknown error"
                            )
                            LOGGER.error(
                                f"Failed to extract subtitle: {stderr_text}"
                            )

                            # Try alternative approaches for subtitle extraction
                            input_codec = track.get("codec", "").lower()

                            # First try: Use the same codec as input for output (copy)
                            LOGGER.info(
                                f"Trying first alternative approach: copy codec for track {track['index']}"
                            )

                            # For ASS/SSA subtitles, use .ass extension
                            ext = "ass" if input_codec in ["ass", "ssa"] else "srt"

                            alt_output_file = os.path.join(
                                output_dir,
                                f"{os.path.splitext(os.path.basename(file_path))[0]}.subtitle.{track.get('language', 'und')}.{track['index']}.{ext}",
                            )

                            alt_cmd = [
                                ffmpeg_path,
                                "-hide_banner",
                                "-loglevel",
                                "error",
                                "-i",
                                file_path,
                                "-map",
                                f"0:{track['index']}",
                                "-c:s",
                                "copy",
                                alt_output_file,
                            ]

                            # Skip logging the full command

                            alt_proc = await asyncio.create_subprocess_exec(
                                *alt_cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )

                            _, alt_stderr = await alt_proc.communicate()

                            if (
                                alt_proc.returncode == 0
                                and os.path.exists(alt_output_file)
                                and os.path.getsize(alt_output_file) > 0
                            ):
                                extracted_files.append(alt_output_file)
                                LOGGER.info(
                                    f"Successfully extracted subtitle to {alt_output_file} using copy codec"
                                )
                            else:
                                alt_stderr_text = (
                                    alt_stderr.decode()
                                    if alt_stderr
                                    else "Unknown error"
                                )
                                LOGGER.error(
                                    f"First alternative approach failed: {alt_stderr_text}"
                                )

                                # Second try: For ASS/SSA, try extracting to SRT with explicit conversion
                                if input_codec in ["ass", "ssa"]:
                                    LOGGER.info(
                                        f"Trying second alternative approach: ASS to SRT conversion for track {track['index']}"
                                    )
                                    alt_output_file2 = os.path.join(
                                        output_dir,
                                        f"{os.path.splitext(os.path.basename(file_path))[0]}.subtitle.{track.get('language', 'und')}.{track['index']}.srt",
                                    )

                                    # Use more explicit conversion parameters
                                    alt_cmd2 = [
                                        ffmpeg_path,
                                        "-hide_banner",
                                        "-loglevel",
                                        "error",
                                        "-i",
                                        file_path,
                                        "-map",
                                        f"0:{track['index']}",
                                        "-f",
                                        "srt",  # Force SRT format
                                        alt_output_file2,
                                    ]

                                    LOGGER.info(
                                        f"Second alternative FFmpeg command: {' '.join(alt_cmd2)}"
                                    )

                                    alt_proc2 = await asyncio.create_subprocess_exec(
                                        *alt_cmd2,
                                        stdout=asyncio.subprocess.PIPE,
                                        stderr=asyncio.subprocess.PIPE,
                                    )

                                    _, alt_stderr2 = await alt_proc2.communicate()

                                    if (
                                        alt_proc2.returncode == 0
                                        and os.path.exists(alt_output_file2)
                                        and os.path.getsize(alt_output_file2) > 0
                                    ):
                                        extracted_files.append(alt_output_file2)
                                        LOGGER.info(
                                            f"Successfully extracted subtitle to {alt_output_file2} using ASS to SRT conversion"
                                        )
                                    else:
                                        alt_stderr_text2 = (
                                            alt_stderr2.decode()
                                            if alt_stderr2
                                            else "Unknown error"
                                        )
                                        LOGGER.error(
                                            f"Second alternative approach also failed: {alt_stderr_text2}"
                                        )
                                else:
                                    LOGGER.error(
                                        f"All extraction attempts failed for track {track['index']}"
                                    )
                    except Exception as e:
                        LOGGER.error(
                            f"Error running FFmpeg for subtitle extraction: {e}"
                        )
                        # Log the full exception traceback for debugging

            # Check if any tracks were found
            if not found_tracks:
                pass
        elif extract_all_subtitles:
            # Extract all subtitle tracks
            LOGGER.info(f"Extracting all subtitle tracks from {file_path}")
            for track in tracks["subtitle"]:
                # Determine output extension based on format config if available
                # Use the subtitle_format parameter passed to the function

                # Get the input codec
                input_codec = track.get("codec", "").lower()

                # Normalize input codec names
                if input_codec == "subrip":
                    input_codec = "srt"
                elif input_codec in ["ass", "ssa"]:
                    input_codec = "ass"

                # If format is specified and not 'none', use it directly
                if subtitle_format and subtitle_format.lower() != "none":
                    output_ext = subtitle_format
                else:
                    # Otherwise use the codec-based extension
                    output_ext = get_output_extension(
                        "subtitle", subtitle_codec, input_codec
                    )

                # Determine output format based on subtitle_format or codec
                output_format = None
                if subtitle_format and subtitle_format.lower() != "none":
                    output_format = subtitle_format.lower()
                elif subtitle_codec and subtitle_codec.lower() != "none":
                    if subtitle_codec.lower() == "copy":
                        output_format = input_codec
                    else:
                        output_format = subtitle_codec.lower()
                # For ASS/SSA subtitles, preserve the format when using copy
                elif input_codec in ["ass", "ssa"]:
                    output_format = "ass"
                else:
                    # Default to SRT if no format/codec specified
                    output_format = "srt"

                # For ASS/SSA subtitles, make sure the extension matches the codec
                if input_codec in ["ass", "ssa"] and output_format == "srt":
                    # Force output format to match the codec
                    output_ext = "srt"
                elif input_codec in ["ass", "ssa"] and (
                    output_format in {"ass", "copy"}
                ):
                    # Use ASS extension for ASS/SSA subtitles when copying
                    output_ext = "ass"

                output_file = os.path.join(
                    output_dir,
                    f"{os.path.splitext(os.path.basename(file_path))[0]}.subtitle.{track.get('language', 'und')}.{track['index']}.{output_ext}",
                )

                # Build FFmpeg command
                cmd = [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    file_path,
                    "-map",
                    f"0:{track['index']}",
                ]

                # Handle subtitle codec based on input and output formats
                input_codec = track.get("codec", "").lower()

                # Normalize input codec names
                if input_codec == "subrip":
                    input_codec = "srt"
                elif input_codec in ["ass", "ssa"]:
                    input_codec = "ass"

                # Determine output format based on subtitle_format or codec
                output_format = None
                if subtitle_format and subtitle_format.lower() != "none":
                    output_format = subtitle_format.lower()
                elif subtitle_codec and subtitle_codec.lower() != "none":
                    if subtitle_codec.lower() == "copy":
                        output_format = input_codec
                    else:
                        output_format = subtitle_codec.lower()
                # For ASS/SSA subtitles, preserve the format when using copy
                elif input_codec in ["ass", "ssa"]:
                    output_format = "ass"
                else:
                    # Default to SRT if no format/codec specified
                    output_format = "srt"

                # Handle format conversion
                if output_format and output_format != input_codec:
                    # Converting between formats
                    if output_format == "srt" and input_codec in ["ass", "ssa"]:
                        # Converting from ASS/SSA to SRT
                        cmd.extend(["-c:s", "srt"])
                        # Force SRT format for output
                        cmd.extend(["-f", "srt"])
                    elif output_format == "ass" and input_codec == "srt":
                        # Converting from SRT to ASS
                        cmd.extend(["-c:s", "ass"])
                    elif output_format == "vtt" and input_codec in [
                        "srt",
                        "ass",
                        "ssa",
                    ]:
                        # Converting to WebVTT
                        cmd.extend(["-c:s", "webvtt"])
                    # For other conversions, let FFmpeg choose the appropriate codec
                    elif subtitle_codec and subtitle_codec.lower() != "none":
                        cmd.extend(["-c:s", subtitle_codec])
                # No conversion needed, use copy if possible
                elif input_codec in ["ass", "ssa", "srt", "vtt", "webvtt"]:
                    cmd.extend(["-c:s", "copy"])
                # For other formats, let FFmpeg choose the appropriate codec
                elif subtitle_codec and subtitle_codec.lower() != "none":
                    cmd.extend(["-c:s", subtitle_codec])
                else:
                    # Default to SRT for unknown formats
                    cmd.extend(["-c:s", "srt"])

                # Add subtitle language if specified
                if subtitle_language:
                    cmd.extend(["-metadata:s:s:0", f"language={subtitle_language}"])

                # Add subtitle encoding if specified
                if subtitle_encoding:
                    cmd.extend(["-sub_charenc", subtitle_encoding])

                # Add subtitle font if specified
                if subtitle_font and subtitle_codec in ["ass", "ssa"]:
                    cmd.extend(["-metadata:s:s:0", f"font={subtitle_font}"])

                # Add subtitle font size if specified
                if subtitle_font_size and subtitle_codec in ["ass", "ssa"]:
                    cmd.extend(["-metadata:s:s:0", f"fontsize={subtitle_font_size}"])

                cmd.append(output_file)

                # Run the command
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    _, stderr = await proc.communicate()

                    if proc.returncode == 0 and os.path.exists(output_file):
                        extracted_files.append(output_file)
                        LOGGER.info(
                            f"Successfully extracted subtitle to {output_file}"
                        )
                    else:
                        stderr_text = stderr.decode() if stderr else "Unknown error"
                        LOGGER.error(f"Failed to extract subtitle: {stderr_text}")
                        # Log the command that failed
                except Exception as e:
                    LOGGER.error(
                        f"Error running FFmpeg for subtitle extraction: {e}"
                    )
                    # Log the command that failed

    # Delete original file if requested
    if delete_original and extracted_files:
        try:
            LOGGER.info(f"Deleting original file after extraction: {file_path}")
            await remove(file_path)
        except Exception as e:
            LOGGER.error(f"Error deleting original file: {e}")
            # Try again with a different approach
            try:
                import os

                os.remove(file_path)
            except Exception as e2:
                LOGGER.error(f"Second attempt to delete file failed: {e2}")
    elif delete_original and not extracted_files:
        pass

    return extracted_files


async def remove_tracks(
    file_path: str,
    output_dir: str,
    remove_video: bool = False,
    remove_audio: bool = False,
    remove_subtitle: bool = False,
    remove_attachment: bool = False,
    remove_metadata: bool = False,
    video_indices: list[int] | None = None,
    audio_indices: list[int] | None = None,
    subtitle_indices: list[int] | None = None,
    attachment_indices: list[int] | None = None,
    video_codec: str = "copy",
    audio_codec: str = "copy",
    subtitle_codec: str = "copy",
    delete_original: bool = True,
) -> list[str]:
    """Remove specific tracks from media files using FFmpeg.

    Args:
        file_path: Path to the input media file
        output_dir: Directory to save the output file
        remove_video: Whether to remove video tracks
        remove_audio: Whether to remove audio tracks
        remove_subtitle: Whether to remove subtitle tracks
        remove_attachment: Whether to remove attachment tracks
        remove_metadata: Whether to remove metadata
        video_indices: List of video track indices to remove (None = remove all)
        audio_indices: List of audio track indices to remove (None = remove all)
        subtitle_indices: List of subtitle track indices to remove (None = remove all)
        attachment_indices: List of attachment track indices to remove (None = remove all)
        video_codec: Video codec for remaining tracks
        audio_codec: Audio codec for remaining tracks
        subtitle_codec: Subtitle codec for remaining tracks
        delete_original: Whether to delete the original file after processing

    Returns:
        List of output file paths
    """
    import asyncio

    # Check if file exists
    if not await aiopath.exists(file_path):
        LOGGER.error(f"File not found: {file_path}")
        return []

    # Check if any removal options are enabled
    if not (
        remove_video
        or remove_audio
        or remove_subtitle
        or remove_attachment
        or remove_metadata
    ):
        LOGGER.info("No removal options enabled, returning original file")
        return [file_path]

    # Get track information
    tracks = await get_track_info(file_path)
    if not tracks:
        LOGGER.error(f"Could not get track information for: {file_path}")
        return []

    # Determine FFmpeg path
    ffmpeg_path = "xtra"  # Use xtra alias for FFmpeg

    # Create output filename
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    file_ext = os.path.splitext(file_path)[1]
    output_file = os.path.join(output_dir, f"{base_name}_removed{file_ext}")

    # Ensure output file doesn't overwrite input
    if output_file == file_path:
        output_file = os.path.join(
            output_dir, f"{base_name}_removed_tracks{file_ext}"
        )

    # Build FFmpeg command
    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        file_path,
        "-y",  # Overwrite output file
    ]

    # Build map arguments to include/exclude tracks
    map_args = []

    # Handle video tracks
    if tracks["video"]:
        for track in tracks["video"]:
            track_index = track["index"]
            should_remove = False

            if remove_video:
                if video_indices is None:
                    # Remove all video tracks
                    should_remove = True
                elif track_index in video_indices:
                    # Remove specific video track
                    should_remove = True

            if not should_remove:
                # Keep this video track
                map_args.extend(["-map", f"0:{track_index}"])

    # Handle audio tracks
    if tracks["audio"]:
        for track in tracks["audio"]:
            track_index = track["index"]
            should_remove = False

            if remove_audio:
                if audio_indices is None:
                    # Remove all audio tracks
                    should_remove = True
                elif track_index in audio_indices:
                    # Remove specific audio track
                    should_remove = True

            if not should_remove:
                # Keep this audio track
                map_args.extend(["-map", f"0:{track_index}"])

    # Handle subtitle tracks
    if tracks["subtitle"]:
        for track in tracks["subtitle"]:
            track_index = track["index"]
            should_remove = False

            if remove_subtitle:
                if subtitle_indices is None:
                    # Remove all subtitle tracks
                    should_remove = True
                elif track_index in subtitle_indices:
                    # Remove specific subtitle track
                    should_remove = True

            if not should_remove:
                # Keep this subtitle track
                map_args.extend(["-map", f"0:{track_index}"])

    # Handle attachment tracks
    if tracks["attachment"]:
        for track in tracks["attachment"]:
            track_index = track["index"]
            should_remove = False

            if remove_attachment:
                if attachment_indices is None:
                    # Remove all attachment tracks
                    should_remove = True
                elif track_index in attachment_indices:
                    # Remove specific attachment track
                    should_remove = True

            if not should_remove:
                # Keep this attachment track
                map_args.extend(["-map", f"0:{track_index}"])

    # If no tracks are mapped, map everything except what we want to remove
    if not map_args:
        # Start with mapping all streams
        cmd.extend(["-map", "0"])

        # Then exclude specific tracks
        if remove_video and video_indices is None:
            cmd.extend(["-map", "-0:v"])  # Remove all video
        elif remove_video and video_indices:
            for idx in video_indices:
                cmd.extend(["-map", f"-0:{idx}"])  # Remove specific video tracks

        if remove_audio and audio_indices is None:
            cmd.extend(["-map", "-0:a"])  # Remove all audio
        elif remove_audio and audio_indices:
            for idx in audio_indices:
                cmd.extend(["-map", f"-0:{idx}"])  # Remove specific audio tracks

        if remove_subtitle and subtitle_indices is None:
            cmd.extend(["-map", "-0:s"])  # Remove all subtitles
        elif remove_subtitle and subtitle_indices:
            for idx in subtitle_indices:
                cmd.extend(["-map", f"-0:{idx}"])  # Remove specific subtitle tracks

        if remove_attachment and attachment_indices is None:
            cmd.extend(["-map", "-0:t"])  # Remove all attachments
        elif remove_attachment and attachment_indices:
            for idx in attachment_indices:
                cmd.extend(
                    ["-map", f"-0:{idx}"]
                )  # Remove specific attachment tracks
    else:
        # Add the mapped tracks
        cmd.extend(map_args)

    # Add codec settings
    if video_codec and video_codec.lower() != "none":
        cmd.extend(["-c:v", video_codec])
    if audio_codec and audio_codec.lower() != "none":
        cmd.extend(["-c:a", audio_codec])
    if subtitle_codec and subtitle_codec.lower() != "none":
        cmd.extend(["-c:s", subtitle_codec])

    # Handle metadata removal
    if remove_metadata:
        cmd.extend(["-map_metadata", "-1"])  # Remove all metadata
        cmd.extend(["-map_chapters", "-1"])  # Remove chapters

    # Add thread count for better performance
    cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

    # Add output file
    cmd.append(output_file)

    LOGGER.info(f"Removing tracks from: {file_path}")
    LOGGER.info(f"Output file: {output_file}")

    try:
        # Run FFmpeg command
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode == 0 and await aiopath.exists(output_file):
            LOGGER.info(f"Successfully removed tracks from: {file_path}")

            # Delete original file if requested
            if delete_original and output_file != file_path:
                try:
                    await remove(file_path)
                    LOGGER.info(f"Deleted original file: {file_path}")
                except Exception as e:
                    LOGGER.error(f"Failed to delete original file: {e}")

            return [output_file]
        stderr_text = stderr.decode() if stderr else "Unknown error"
        LOGGER.error(f"Failed to remove tracks: {stderr_text}")

        # Clean up failed output file
        if await aiopath.exists(output_file):
            with contextlib.suppress(Exception):
                await remove(output_file)

        return []

    except Exception as e:
        LOGGER.error(f"Error running FFmpeg for track removal: {e}")

        # Clean up failed output file
        if await aiopath.exists(output_file):
            with contextlib.suppress(Exception):
                await remove(output_file)

        return []


async def get_video_thumbnail(video_file, duration):
    """Extract a thumbnail from a video file using memory-efficient approach"""
    output_dir = f"{DOWNLOAD_DIR}thumbnails"
    await makedirs(output_dir, exist_ok=True)
    output = ospath.join(output_dir, f"{time()}.jpg")

    # Check file size first to avoid processing very large files
    try:
        file_size_mb = (await aiopath.getsize(video_file)) / (1024 * 1024)
        if (
            file_size_mb > 2000
        ):  # Skip very large files (>2GB) to prevent memory issues
            LOGGER.warning(
                f"Skipping thumbnail extraction for large video file ({file_size_mb:.1f}MB)"
            )
            return None
    except Exception:
        pass

    if duration is None:
        duration = (await get_media_info(video_file))[0]
    if duration == 0:
        duration = 3
    duration = duration // 2

    # Memory-efficient approach - extract small thumbnail from middle of video
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{duration}",
        "-i",
        video_file,
        "-vf",
        "scale=480:-1",  # Smaller scale to reduce memory usage
        "-q:v",
        "8",  # Lower quality to reduce memory usage
        "-vframes",
        "1",
        "-threads",
        "1",  # Limit threads to reduce memory usage
        "-y",  # Overwrite output
        output,
    ]

    try:
        # Force garbage collection before thumbnail extraction
        if smart_garbage_collection is not None:
            smart_garbage_collection(aggressive=False)

        _, _, code = await wait_for(cmd_exec(cmd), timeout=30)
        if code == 0 and await aiopath.exists(output):
            output_size = await aiopath.getsize(output)
            if output_size > 0:
                # Verify the extracted thumbnail isn't too large
                if output_size > 5 * 1024 * 1024:  # 5MB limit for video thumbnails
                    LOGGER.warning(
                        f"Extracted video thumbnail too large ({output_size / (1024 * 1024):.1f}MB), removing"
                    )
                    await remove(output)
                else:
                    return output
            else:
                await remove(output)
    except Exception as e:
        LOGGER.error(f"Video thumbnail extraction failed: {e}")

    # If extraction fails, return None to trigger default thumbnail creation
    return None


async def get_multiple_frames_thumbnail(video_file, layout, keep_screenshots):
    ss_nb = layout.split("x")
    ss_nb = int(ss_nb[0]) * int(ss_nb[1])
    dirpath = await take_ss(video_file, ss_nb)
    if not dirpath:
        return None
    output_dir = f"{DOWNLOAD_DIR}thumbnails"
    await makedirs(output_dir, exist_ok=True)
    output = ospath.join(output_dir, f"{time()}.jpg")
    cmd = [
        "xtra",  # Using xtra instead of ffmpeg
        "-hide_banner",
        "-loglevel",
        "error",
        "-pattern_type",
        "glob",
        "-i",
        f"{escape(dirpath)}/*.png",
        "-vf",
        f"tile={layout}, thumbnail",
        "-q:v",
        "1",
        "-frames:v",
        "1",
        "-f",
        "mjpeg",
        "-threads",
        f"{max(1, cpu_no // 2)}",
        output,
    ]
    output_result = None  # Initialize result variable

    try:
        _, err, code = await wait_for(cmd_exec(cmd), timeout=60)
        if code == 0 and await aiopath.exists(output):
            # Check if the created thumbnail is valid and not empty
            if await aiopath.getsize(output) > 0:
                output_result = output
            else:
                await remove(output)
                LOGGER.warning(
                    f"Created empty grid thumbnail from video: {video_file}"
                )
        else:
            LOGGER.warning(
                f"Failed to create grid thumbnail: {video_file} stderr: {err}",
            )

        # If first method failed, try alternative method with PIL
        if not output_result:
            try:
                alt_output = ospath.join(
                    output_dir, f"grid_thumb_alt_{int(time())}.jpg"
                )
                # Check if we have screenshots
                screenshots = list(Path(dirpath).glob("*.png"))
                if screenshots:
                    # Use PIL to create a grid
                    from PIL import Image

                    # Apply memory limits for PIL operations
                    limit_memory_for_pil()

                    # Determine grid dimensions
                    cols, rows = map(int, layout.split("x"))
                    # Get the first image to determine dimensions
                    with Image.open(screenshots[0]) as img:
                        img_width, img_height = img.size

                    # Create a new image with the grid dimensions
                    grid_width = cols * img_width
                    grid_height = rows * img_height
                    grid_img = Image.new("RGB", (grid_width, grid_height))

                    # Place images in the grid
                    for i, screenshot in enumerate(screenshots[:ss_nb]):
                        if i >= ss_nb:
                            break
                        with Image.open(screenshot) as img:
                            x = (i % cols) * img_width
                            y = (i // cols) * img_height
                            grid_img.paste(img, (x, y))

                    # Save the grid
                    grid_img.save(alt_output, quality=90)
                    output_result = alt_output
            except Exception as e:
                LOGGER.error(f"Failed to create grid with PIL: {e}")

    except Exception:
        LOGGER.error(
            f"Error while combining thumbnails from video. Name: {video_file}. Error: Timeout some issues with xtra with specific arch!",
        )
    finally:
        # Clean up screenshots if not keeping them
        if not keep_screenshots and "dirpath" in locals() and dirpath:
            await rmtree(dirpath, ignore_errors=True)

    return output_result


def is_mkv(file):
    """Legacy function name, now checks if file is a supported media format for metadata and watermarking.

    Args:
        file: Path to the file

    Returns:
        bool: True if the file is a supported media format for metadata or watermarking
    """
    # Video formats (expanded list for better compatibility)
    video_extensions = [
        ".mkv",
        ".mp4",
        ".avi",
        ".mov",
        ".webm",
        ".flv",
        ".wmv",
        ".m4v",
        ".ts",
        ".3gp",
        ".mpg",
        ".mpeg",
        ".vob",
        ".divx",
        ".asf",
        ".m2ts",
        ".mts",
    ]
    # Audio formats (expanded list for better compatibility)
    audio_extensions = [
        ".mp3",
        ".m4a",
        ".flac",
        ".wav",
        ".ogg",
        ".opus",
        ".aac",
        ".wma",
        ".alac",
        ".ape",
    ]
    # Image formats (expanded list for better compatibility)
    image_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
        ".svg",
        ".heic",
        ".heif",
        ".gif",
        ".apng",
        ".mng",
    ]
    # Subtitle formats that support metadata
    subtitle_extensions = [
        ".srt",
        ".ass",
        ".ssa",
        ".sub",
        ".idx",
    ]

    # Check if the file has a supported extension
    file_lower = file.lower()
    return any(
        file_lower.endswith(ext)
        for ext in video_extensions
        + audio_extensions
        + image_extensions
        + subtitle_extensions
    )


async def get_media_type_for_watermark(file):
    """Determine the media type for watermarking purposes.

    Args:
        file: Path to the file

    Returns:
        str: 'image', 'video', 'animated_image', 'audio', 'subtitle', or None if not supported
    """
    # Check if file exists
    if not await aiopath.exists(file):
        LOGGER.error(f"File not found for watermarking: {file}")
        return None

    # Force None for tar files regardless of content
    # This is a critical override to prevent misidentification
    if file.lower().endswith(".tar"):
        # We don't have cache_key yet at this point, so we can't cache the result
        return None

    # Get file modification time for cache key
    try:
        mtime = os.path.getmtime(file)
        cache_key = f"{file}_{mtime}_watermark"

        # Check if we have this in cache
        if cache_key in MEDIA_TYPE_CACHE:
            return MEDIA_TYPE_CACHE[cache_key]
    except Exception:
        cache_key = None

    # Video formats (expanded list for better compatibility)
    video_extensions = [
        ".mkv",
        ".mp4",
        ".avi",
        ".mov",
        ".webm",
        ".flv",
        ".wmv",
        ".m4v",
        ".ts",
        ".3gp",
        ".mpg",
        ".mpeg",
        ".vob",
        ".divx",
        ".asf",
        ".m2ts",
        ".mts",
        ".ogv",
        ".m2v",
        ".mp2",
        ".rm",
        ".rmvb",
        ".f4v",
        ".mpv",
    ]
    # Image formats (expanded list for better compatibility)
    image_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
        ".svg",
        ".heic",
        ".heif",
        ".psd",
        ".xcf",
        ".ai",
        ".eps",
        ".raw",
        ".cr2",
        ".nef",
        ".arw",
        ".dng",
    ]
    # Animated image formats (special handling)
    animated_extensions = [
        ".gif",
        ".apng",
        ".mng",
    ]
    # Audio formats
    audio_extensions = [
        ".mp3",
        ".m4a",
        ".flac",
        ".wav",
        ".ogg",
        ".opus",
        ".aac",
        ".wma",
        ".alac",
        ".ape",
    ]
    # Subtitle formats
    subtitle_extensions = [
        ".srt",
        ".ass",
        ".ssa",
        ".sub",
        ".idx",
        ".vtt",
        ".stl",
        ".webvtt",
        ".ttml",
        ".dfxp",
        ".sami",
        ".sbv",
    ]

    file_lower = file.lower()

    # First try to determine type by extension
    # Special cases for file types which are sometimes not detected correctly
    if file_lower.endswith((".3gp", ".mpeg", ".mpg", ".ts")):
        media_type = "video"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # Special case for STL subtitle files
    if file_lower.endswith(".stl"):
        media_type = "subtitle"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # Special case for SVG, EPS, TIFF, and PSD files
    if file_lower.endswith((".svg", ".eps", ".tiff", ".tif", ".psd")):
        media_type = "image"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # Special case for archive files that might be misidentified
    if file_lower.endswith((".tar", ".zip", ".rar", ".7z", ".gz", ".bz2", ".epub")):
        # Force None for archive files regardless of content
        # This is a critical override to prevent misidentification
        media_type = None
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = None
        return None

    if any(file_lower.endswith(ext) for ext in video_extensions):
        media_type = "video"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    if any(file_lower.endswith(ext) for ext in image_extensions):
        media_type = "image"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    if any(file_lower.endswith(ext) for ext in animated_extensions):
        media_type = "animated_image"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    if any(file_lower.endswith(ext) for ext in audio_extensions):
        media_type = "audio"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    if any(file_lower.endswith(ext) for ext in subtitle_extensions):
        media_type = "subtitle"
        if cache_key:
            MEDIA_TYPE_CACHE[cache_key] = media_type
        return media_type

    # This check is now redundant as we check for tar files at the beginning of the function
    # Keeping this comment as a reminder

    # If extension doesn't match, try to determine by file content using ffprobe
    try:
        import json

        from .bot_utils import cmd_exec

        # Use ffprobe to get file information
        cmd = [
            "ffprobe",  # Use ffprobe for stream analysis
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            file,
        ]

        # Execute the command
        stdout, _, code = await cmd_exec(cmd)

        if code == 0:
            data = json.loads(stdout)
            if data.get("streams"):
                # First check if there's a video stream - if so, it's a video file
                # This ensures that files with both video and audio are treated as videos
                has_video = False
                has_audio = False
                has_subtitle = False

                for stream in data["streams"]:
                    codec_type = stream.get("codec_type")
                    codec_name = stream.get("codec_name")
                    avg_frame_rate = stream.get("avg_frame_rate", "")

                    if codec_type == "video":
                        # Check if it's an animated image
                        if codec_name in ["gif", "apng"]:
                            media_type = "animated_image"
                            if cache_key:
                                MEDIA_TYPE_CACHE[cache_key] = media_type
                            return media_type

                        # Check if it's a single frame (likely an image)
                        if avg_frame_rate in {"0/0", "1/1"}:
                            media_type = "image"
                            if cache_key:
                                MEDIA_TYPE_CACHE[cache_key] = media_type
                            return media_type

                        has_video = True
                    elif codec_type == "audio":
                        has_audio = True
                    elif codec_type == "subtitle":
                        has_subtitle = True

                # Prioritize video over audio over subtitle
                if has_video:
                    if has_subtitle:
                        media_type = "video_with_subtitle"
                        if cache_key:
                            MEDIA_TYPE_CACHE[cache_key] = media_type
                        return media_type

                    media_type = "video"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type

                if has_audio:
                    media_type = "audio"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type

                if has_subtitle:
                    media_type = "subtitle"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type

                # Special case for STL files that might be misidentified
                if file_lower.endswith(".stl"):
                    media_type = "subtitle"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type
    except Exception as e:
        LOGGER.error(f"Error determining media type with ffprobe: {e}")

    # If all else fails, try to determine by mime type
    try:
        from .files_utils import get_mime_type

        mime_type = await get_mime_type(file)
        if mime_type:
            if mime_type.startswith("video/"):
                media_type = "video"
                if cache_key:
                    MEDIA_TYPE_CACHE[cache_key] = media_type
                return media_type

            if mime_type.startswith("image/"):
                if mime_type in ["image/gif", "image/apng"]:
                    media_type = "animated_image"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type

                media_type = "image"
                if cache_key:
                    MEDIA_TYPE_CACHE[cache_key] = media_type
                return media_type

            if mime_type.startswith("audio/"):
                media_type = "audio"
                if cache_key:
                    MEDIA_TYPE_CACHE[cache_key] = media_type
                return media_type

            if mime_type.startswith("application/"):
                # Check for image formats with application mime types
                if any(
                    x in mime_type
                    for x in ["photoshop", "psd", "tiff", "illustrator", "ai", "eps"]
                ):
                    media_type = "image"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type
                # Check for video formats with application mime types
                if any(
                    x in mime_type
                    for x in [
                        "mp4",
                        "mkv",
                        "avi",
                        "mov",
                        "webm",
                        "flv",
                        "wmv",
                        "mpeg",
                        "3gp",
                        "ts",
                        "video",
                    ]
                ):
                    media_type = "video"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type
                # Check for raw image formats
                if any(x in mime_type for x in ["raw", "cr2", "nef", "arw", "dng"]):
                    media_type = "image"
                    if cache_key:
                        MEDIA_TYPE_CACHE[cache_key] = media_type
                    return media_type

            if mime_type in [
                "text/plain",
                "application/x-subrip",
                "text/vtt",
                "application/xml",
                "text/xml",
            ]:
                # Check if it's a subtitle file by examining content
                async with aiofiles.open(file, errors="ignore") as f:
                    content = await f.read(1000)  # Read first 1000 chars
                    # SRT format check
                    if "-->" in content and content[0].isdigit():
                        media_type = "subtitle"
                        if cache_key:
                            MEDIA_TYPE_CACHE[cache_key] = media_type
                        return media_type
                    # WebVTT format check
                    if "WEBVTT" in content:
                        media_type = "subtitle"
                        if cache_key:
                            MEDIA_TYPE_CACHE[cache_key] = media_type
                        return media_type
                    # ASS/SSA format check
                    if "[Script Info]" in content or "[V4+ Styles]" in content:
                        media_type = "subtitle"
                        if cache_key:
                            MEDIA_TYPE_CACHE[cache_key] = media_type
                        return media_type
                    # STL format check
                    if "$STL" in content:
                        media_type = "subtitle"
                        if cache_key:
                            MEDIA_TYPE_CACHE[cache_key] = media_type
                        return media_type
    except Exception as e:
        LOGGER.error(f"Error determining media type with mime type: {e}")

    # If cache is too large, remove oldest entries
    if cache_key and len(MEDIA_TYPE_CACHE) >= MAX_CACHE_SIZE:
        # Remove the first item (oldest)
        MEDIA_TYPE_CACHE.pop(next(iter(MEDIA_TYPE_CACHE)))

    # Cache the result (None) if we have a valid cache key
    if cache_key:
        MEDIA_TYPE_CACHE[cache_key] = None

    # If all else fails, return None
    return None


class FFMpeg:
    def __init__(self, listener):
        self._listener = listener
        self._processed_bytes = 0
        self._last_processed_bytes = 0
        self._processed_time = 0
        self._last_processed_time = 0
        self._speed_raw = 0
        self._progress_raw = 0
        self._total_time = 0
        self._eta_raw = 0
        self._time_rate = 0.1
        self._start_time = 0

    @property
    def processed_bytes(self):
        return self._processed_bytes

    @property
    def speed_raw(self):
        return self._speed_raw

    @property
    def progress_raw(self):
        return self._progress_raw

    @property
    def eta_raw(self):
        return self._eta_raw

    def clear(self):
        self._start_time = time()
        self._processed_bytes = 0
        self._processed_time = 0
        self._speed_raw = 0
        self._progress_raw = 0
        self._eta_raw = 0
        self._time_rate = 0.1
        self._last_processed_time = 0
        self._last_processed_bytes = 0

    async def _ffmpeg_progress(self):
        while not (
            self._listener.subproc.returncode is not None
            or self._listener.is_cancelled
            or self._listener.subproc.stdout.at_eof()
        ):
            try:
                line = await wait_for(self._listener.subproc.stdout.readline(), 60)
            except Exception:
                break
            line = line.decode().strip()
            if not line:
                break
            if "=" in line:
                key, value = line.split("=", 1)
                if value != "N/A":
                    if key == "total_size":
                        self._processed_bytes = (
                            int(value) + self._last_processed_bytes
                        )
                        self._speed_raw = self._processed_bytes / (
                            time() - self._start_time
                        )
                    elif key == "codec_name":
                        # Store codec information for status display
                        self.codec = value
                    elif key == "bitrate":
                        # Store bitrate information
                        try:
                            # Convert to readable format (e.g., "5.2Mbps")
                            bitrate_value = float(value) / 1000000
                            self.bitrate = f"{bitrate_value:.1f}Mbps"
                        except (ValueError, TypeError):
                            self.bitrate = value

                        # If this is a trim operation and we have a valid total_time,
                        # update progress based on processed bytes
                        if (
                            hasattr(self._listener, "subsize")
                            and self._listener.subsize > 0
                        ):
                            try:
                                # For trim operations, we need to handle progress differently
                                # based on the media type
                                if (
                                    hasattr(self._listener, "cstatus")
                                    and self._listener.cstatus == "Trim"
                                ):
                                    # For trim operations, use a combination of time and bytes for more accurate progress
                                    if (
                                        self._total_time > 0
                                        and self._processed_time > 0
                                    ):
                                        # Calculate progress based on processed time
                                        time_progress = (
                                            self._processed_time / self._total_time
                                        ) * 100

                                        # Calculate progress based on processed bytes
                                        byte_progress = (
                                            self._processed_bytes
                                            / self._listener.subsize
                                        ) * 100

                                        # Use the average of both methods for more accurate progress
                                        self._progress_raw = min(
                                            (time_progress + byte_progress) / 2, 99.9
                                        )

                                        # Calculate ETA based on current speed and remaining bytes/time
                                        if self._speed_raw > 0:
                                            remaining_bytes = max(
                                                0,
                                                self._listener.subsize
                                                - self._processed_bytes,
                                            )
                                            eta_bytes = (
                                                remaining_bytes / self._speed_raw
                                            )

                                            remaining_time = max(
                                                0,
                                                self._total_time
                                                - self._processed_time,
                                            )
                                            eta_time = (
                                                remaining_time / self._time_rate
                                                if self._time_rate > 0
                                                else 0
                                            )

                                            # Use the average of both methods for more accurate ETA
                                            self._eta_raw = (
                                                eta_bytes + eta_time
                                            ) / 2
                                        else:
                                            self._eta_raw = 0
                                    else:
                                        # Fallback to byte-based progress if time is not available
                                        self._progress_raw = min(
                                            (
                                                self._processed_bytes
                                                / self._listener.subsize
                                            )
                                            * 100,
                                            99.9,
                                        )
                                        # Calculate ETA based on current speed and remaining bytes
                                        remaining_bytes = max(
                                            0,
                                            self._listener.subsize
                                            - self._processed_bytes,
                                        )
                                        if self._speed_raw > 0:
                                            self._eta_raw = (
                                                remaining_bytes / self._speed_raw
                                            )
                                        else:
                                            self._eta_raw = 0
                                else:
                                    # For non-trim operations, use the original byte-based progress
                                    self._progress_raw = min(
                                        (
                                            self._processed_bytes
                                            / self._listener.subsize
                                        )
                                        * 100,
                                        99.9,
                                    )
                                    # Calculate ETA based on current speed and remaining bytes
                                    remaining_bytes = max(
                                        0,
                                        self._listener.subsize
                                        - self._processed_bytes,
                                    )
                                    if self._speed_raw > 0:
                                        self._eta_raw = (
                                            remaining_bytes / self._speed_raw
                                        )
                                    else:
                                        self._eta_raw = 0
                            except Exception:
                                pass

                    elif key == "speed":
                        self._time_rate = max(0.1, float(value.strip("x")))
                    elif key == "out_time":
                        self._processed_time = (
                            time_to_seconds(value) + self._last_processed_time
                        )
                        try:
                            # Only use time-based progress if we don't have a better byte-based calculation
                            if not (
                                hasattr(self._listener, "subsize")
                                and self._listener.subsize > 0
                            ):
                                self._progress_raw = (
                                    self._processed_time / self._total_time * 100
                                )
                                self._eta_raw = (
                                    self._total_time - self._processed_time
                                ) / self._time_rate
                        except Exception:
                            self._progress_raw = 0
                            self._eta_raw = 0
            await sleep(0.05)

    async def _get_stream_info(self, file_path, stream_type):
        """
        Get information about streams of a specific type in a media file.

        Args:
            file_path: Path to the media file
            stream_type: Type of stream to get info for ('video', 'audio', 'subtitle', 'attachment')

        Returns:
            list: A list of stream indices
        """
        from bot.helper.ext_utils.bot_utils import cmd_exec

        # Map stream type to ffprobe stream specifier
        stream_specifier = {
            "video": "v",
            "audio": "a",
            "subtitle": "s",
            "attachment": "t",
        }.get(stream_type, "v")

        try:
            # Use ffprobe to get stream information
            result = await cmd_exec(
                [
                    "ffprobe",  # Use ffprobe for stream analysis
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-select_streams",
                    stream_specifier,
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    file_path,
                ]
            )

            if result[0] and result[2] == 0:
                # Parse the output to get stream indices
                return [
                    int(idx) for idx in result[0].strip().split("\n") if idx.strip()
                ]
            LOGGER.error(f"Error getting {stream_type} stream info: {result[1]}")
            return []
        except Exception as e:
            LOGGER.error(f"Exception getting {stream_type} stream info: {e}")
            return []

    async def _get_detailed_stream_info(self, file_path, stream_type):
        """
        Get detailed information about streams of a specific type in a media file.

        Args:
            file_path: Path to the media file
            stream_type: Type of stream to get info for ('video', 'audio', 'subtitle', 'attachment')

        Returns:
            list: A list of dictionaries with stream information
        """
        from bot.helper.ext_utils.bot_utils import cmd_exec

        # Map stream type to ffprobe stream specifier
        stream_specifier = {
            "video": "v",
            "audio": "a",
            "subtitle": "s",
            "attachment": "t",
        }.get(stream_type, "v")

        try:
            # Use ffprobe to get detailed stream information
            result = await cmd_exec(
                [
                    "ffprobe",  # Use ffprobe for stream analysis
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-select_streams",
                    stream_specifier,
                    "-show_entries",
                    "stream=index,codec_name,codec_type:stream_tags=language,title",
                    "-of",
                    "json",
                    file_path,
                ]
            )

            if result[0] and result[2] == 0:
                import json

                # Parse the output to get stream information
                data = json.loads(result[0])
                streams = []
                if "streams" in data:
                    for stream in data["streams"]:
                        stream_info = {
                            "index": stream.get("index", 0),
                            "codec_name": stream.get("codec_name", "unknown"),
                            "codec_type": stream.get("codec_type", stream_type),
                        }
                        if "tags" in stream:
                            if "language" in stream["tags"]:
                                stream_info["language"] = stream["tags"]["language"]
                            if "title" in stream["tags"]:
                                stream_info["title"] = stream["tags"]["title"]
                        streams.append(stream_info)
                return streams
            LOGGER.error(
                f"Error getting detailed {stream_type} stream info: {result[1]}"
            )
            return []
        except Exception as e:
            LOGGER.error(
                f"Exception getting detailed {stream_type} stream info: {e}"
            )
            return []

    async def ffmpeg_cmds(self, ffmpeg, f_path, user_provided_files=None):
        """Process one or more FFmpeg commands.

        Args:
            ffmpeg: A single FFmpeg command or a list of commands to run sequentially
            f_path: The input file path
            user_provided_files: Dictionary of user-provided file paths for variable replacement

        Returns:
            list: List of output files or False if the command failed
        """
        self.clear()
        self._total_time = (await get_media_info(f_path))[0]
        base_name, _ext = ospath.splitext(f_path)
        _dir, base_name = base_name.rsplit("/", 1)

        # Check if ffmpeg is a list of commands to run sequentially
        if isinstance(ffmpeg, list) and ffmpeg:
            # Check if this is a list of lists (multiple commands)
            if isinstance(ffmpeg[0], list):
                LOGGER.info(
                    f"Processing multiple FFmpeg commands sequentially: {len(ffmpeg)} commands"
                )

                # Track the current input file (starts with the original file)
                current_input = f_path
                outputs = []

                # Process each command in sequence
                for i, cmd in enumerate(ffmpeg):
                    LOGGER.info(
                        f"Running FFmpeg command {i + 1}/{len(ffmpeg)}: {cmd}"
                    )

                    # For each command after the first one, use the output of the previous command as input
                    if i > 0:
                        # Find the input file argument in the command
                        for j, arg in enumerate(cmd):
                            # Check if this is an input flag followed by a placeholder
                            if (
                                arg == "-i"
                                and j + 1 < len(cmd)
                                and cmd[j + 1]
                                in [
                                    "mltb",
                                    "input.mp4",
                                    "mltb.video",
                                    "mltb.audio",
                                    "mltb.mkv",
                                ]
                            ):
                                # Replace the input file with the output from the previous command
                                cmd[j + 1] = current_input
                                LOGGER.info(
                                    f"Using output from previous command as input: {current_input}"
                                )
                                break

                    # Process this command
                    result = await self._process_ffmpeg_cmd(
                        cmd, current_input, user_provided_files
                    )

                    # If the command failed, stop the sequence
                    if not result:
                        LOGGER.error(
                            f"FFmpeg command {i + 1}/{len(ffmpeg)} failed, stopping sequence"
                        )
                        return False

                    # If the command succeeded, use its output as input for the next command
                    if isinstance(result, list) and result:
                        current_input = result[0]  # Use the first output file
                        outputs.extend(
                            result
                        )  # Add all outputs to the final output list
                        LOGGER.info(
                            f"Command {i + 1}/{len(ffmpeg)} succeeded, output: {current_input}"
                        )
                    else:
                        LOGGER.error(
                            f"Command {i + 1}/{len(ffmpeg)} did not produce valid output"
                        )
                        return False

                # Return all outputs from all commands
                return outputs

            # Check if this is a list of strings that might be a JSON array of commands
            if (
                len(ffmpeg) > 0
                and isinstance(ffmpeg[0], str)
                and ffmpeg[0].startswith("[")
                and ffmpeg[0].endswith("]")
            ):
                # This might be a JSON array of commands, try to parse it
                try:
                    import json
                    import shlex

                    # Try to parse the JSON array
                    cmd_str = ffmpeg[0]
                    cmd_list = json.loads(cmd_str)

                    if isinstance(cmd_list, list) and cmd_list:
                        # Convert each command string to a list of arguments
                        processed_cmds = []
                        for cmd in cmd_list:
                            if isinstance(cmd, str):
                                processed_cmds.append(shlex.split(cmd))
                            elif isinstance(cmd, list):
                                processed_cmds.append(cmd)

                        if processed_cmds:
                            # Recursively call ffmpeg_cmds with the processed commands
                            LOGGER.info(
                                f"Parsed JSON array of commands: {processed_cmds}"
                            )
                            return await self.ffmpeg_cmds(
                                processed_cmds, f_path, user_provided_files
                            )
                except Exception as e:
                    LOGGER.error(f"Error parsing JSON array of commands: {e}")

        # Process a single command
        return await self._process_ffmpeg_cmd(ffmpeg, f_path, user_provided_files)

    async def _process_ffmpeg_cmd(self, ffmpeg, f_path, user_provided_files=None):
        """Process a single FFmpeg command"""
        base_name, ext = ospath.splitext(f_path)
        dir, base_name = base_name.rsplit("/", 1)

        # Process FFmpeg command if it's a string or a list containing a string
        if (
            ffmpeg
            and isinstance(ffmpeg, list)
            and len(ffmpeg) > 0
            and isinstance(ffmpeg[0], str)
            and ffmpeg[0].startswith("[")
            and ffmpeg[0].endswith("]")
        ):
            # This is a string representation of a list, likely from config
            try:
                # Remove the outer brackets and parse the inner string
                cmd_str = ffmpeg[0][1:-1].strip("\"'")
                # Use shlex to properly split the command respecting quotes
                import shlex

                ffmpeg = shlex.split(cmd_str)
                LOGGER.info(f"Parsed FFmpeg command from string: {ffmpeg}")
            except Exception as e:
                LOGGER.error(f"Error parsing FFmpeg command string: {e}")

        # Process user-provided files for variable replacement
        if user_provided_files:
            LOGGER.info(
                f"Processing user-provided files for variable replacement: {user_provided_files}"
            )
            # Create a copy of the command to avoid modifying the original during iteration
            ffmpeg_copy = ffmpeg.copy() if hasattr(ffmpeg, "copy") else ffmpeg[:]

            # Replace variables in the command with actual file paths
            for i, arg in enumerate(ffmpeg_copy):
                if isinstance(arg, str):
                    # Direct variable replacement
                    if arg in user_provided_files:
                        ffmpeg[i] = user_provided_files[arg]
                        LOGGER.info(
                            f"Replaced variable '{arg}' with '{user_provided_files[arg]}'"
                        )
                    else:
                        # Check for variables within the argument string
                        modified_arg = arg
                        replaced = False

                        # Sort variables by length (longest first) to avoid partial replacements
                        sorted_vars = sorted(
                            user_provided_files.items(),
                            key=lambda x: len(x[0]),
                            reverse=True,
                        )

                        for var_name, var_value in sorted_vars:
                            # Only replace whole words or variables with clear boundaries
                            # This prevents partial replacements like replacing "X" in "X_OFFSET"
                            if var_name in modified_arg:
                                # Handle special characters in the replacement value
                                if "'" in modified_arg or '"' in modified_arg:
                                    # For arguments with quotes, we need to be careful with the replacement
                                    if "text=" in modified_arg and (
                                        var_name in modified_arg.split("text=")[1]
                                    ):
                                        # For text parameters, escape special characters
                                        escaped_value = var_value.replace(
                                            '"', '\\"'
                                        ).replace("'", "\\'")
                                        # Replace the variable in the text parameter
                                        parts = modified_arg.split("text=")
                                        text_part = parts[1]
                                        # Find the end of the text parameter (next colon or end of string)
                                        if ":" in text_part:
                                            text_value, rest = text_part.split(
                                                ":", 1
                                            )
                                            # Replace in the text value
                                            text_value = text_value.replace(
                                                var_name, escaped_value
                                            )
                                            modified_arg = (
                                                f"{parts[0]}text={text_value}:{rest}"
                                            )
                                        else:
                                            # Text is the last parameter
                                            modified_arg = f"{parts[0]}text={text_part.replace(var_name, escaped_value)}"
                                    else:
                                        # For other parameters with quotes, do a simple replacement
                                        modified_arg = modified_arg.replace(
                                            var_name, var_value
                                        )
                                else:
                                    # For arguments without quotes, do a simple replacement
                                    modified_arg = modified_arg.replace(
                                        var_name, var_value
                                    )

                                replaced = True
                                LOGGER.info(
                                    f"Replaced variable '{var_name}' with '{var_value}' in argument: {arg} -> {modified_arg}"
                                )

                        # Update the argument if it was modified
                        if replaced:
                            ffmpeg[i] = modified_arg

            # Special handling for filter_complex arguments
            for i, arg in enumerate(ffmpeg):
                if arg == "-filter_complex" and i + 1 < len(ffmpeg):
                    # Make sure filter_complex arguments are properly formatted
                    filter_complex = ffmpeg[i + 1]

                    # Check if the filter_complex contains semicolons without proper escaping
                    if ";" in filter_complex and not filter_complex.startswith("["):
                        # Split the filter_complex by semicolons and ensure proper formatting
                        filter_parts = filter_complex.split(";")
                        formatted_parts = []

                        for part in filter_parts:
                            part = part.strip()
                            if part:
                                formatted_parts.append(part)

                        # Rejoin the parts with semicolons
                        ffmpeg[i + 1] = ";".join(formatted_parts)

                    LOGGER.info(f"Processed filter_complex: {ffmpeg[i + 1]}")

            # Special handling for map arguments
            map_indices = [i for i, arg in enumerate(ffmpeg) if arg == "-map"]
            for idx in map_indices:
                if idx + 1 < len(ffmpeg):
                    map_arg = ffmpeg[idx + 1]
                    # Ensure map arguments with output labels are properly formatted
                    if "[" in map_arg and "]" in map_arg:
                        # The map argument is already properly formatted
                        pass
                    elif ":" in map_arg:
                        # This is a stream specifier like "0:v" or "1:a"
                        pass
                    else:
                        # This might be a variable that needs to be properly formatted
                        LOGGER.info(f"Processed map argument: {map_arg}")

            # Add -y flag to overwrite output files if not already present
            if "-y" not in ffmpeg:
                ffmpeg.append("-y")
                LOGGER.info("Added -y flag to overwrite output files")

            # Log the modified command
            LOGGER.info(f"Command after variable replacement: {ffmpeg}")

        # Check for -del flag to delete original files after processing
        delete_files = False
        if "-del" in ffmpeg:
            ffmpeg.remove("-del")
            delete_files = True

        # Replace 'ffmpeg' with 'xtra' as the command name
        if ffmpeg and ffmpeg[0] == "xtra":
            ffmpeg[0] = "xtra"

        # Determine the media type of the input file
        media_type = await get_media_type_for_watermark(f_path)
        LOGGER.info(f"Detected media type for {f_path}: {media_type}")

        # Find all input file indices in the command
        input_indices = []
        for i, item in enumerate(ffmpeg):
            if item == "-i" and i + 1 < len(ffmpeg):
                input_indices.append(i + 1)

        # If no input parameters are found, add the provided file path as input
        if not input_indices:
            ffmpeg.extend(["-i", f_path])
            input_indices.append(len(ffmpeg) - 1)  # Index of the newly added input
        else:
            # Check if we need to replace any input placeholders with the actual file path
            # This is for backward compatibility with existing commands

            # Keep track of which input files have been used for each media type
            # This helps when we have multiple inputs of the same type
            used_inputs = {
                "video": [],
                "audio": [],
                "image": [],
                "subtitle": [],
                "document": [],
                "archive": [],
                "generic": [],
            }

            # Initialize additional_files dictionary
            additional_files = {
                "video": [],
                "audio": [],
                "image": [],
                "subtitle": [],
                "document": [],
                "archive": [],
            }

            # First, prioritize user-provided files if available
            if user_provided_files:
                LOGGER.info(f"Using user-provided files: {user_provided_files}")

                # Categorize user-provided files by media type
                for file in user_provided_files:
                    if file == f_path:  # Skip the main input file
                        continue

                    try:
                        file_media_type = await get_media_type_for_watermark(file)
                        if file_media_type:
                            if file_media_type in ["image", "animated_image"]:
                                file_media_type = (
                                    "image"  # Treat both as "image" for simplicity
                                )

                            if file_media_type in additional_files:
                                additional_files[file_media_type].append(file)
                                LOGGER.info(
                                    f"Using user-provided {file_media_type} file: {file}"
                                )
                    except Exception as e:
                        LOGGER.warning(
                            f"Error determining media type for user-provided file {file}: {e}"
                        )

            # Then, try to find additional input files in the same directory
            input_dir = os.path.dirname(f_path)

            # Only scan directory if it exists and is accessible
            if os.path.exists(input_dir) and os.path.isdir(input_dir):
                try:
                    # Get all files in the same directory
                    dir_files = [
                        os.path.join(input_dir, f)
                        for f in os.listdir(input_dir)
                        if os.path.isfile(os.path.join(input_dir, f))
                    ]

                    # Categorize files by media type
                    for file in dir_files:
                        if file == f_path:  # Skip the main input file
                            continue

                        # Skip files that are already in the user-provided files
                        if user_provided_files and file in user_provided_files:
                            continue

                        try:
                            file_media_type = await get_media_type_for_watermark(
                                file
                            )
                            if file_media_type:
                                if file_media_type in ["image", "animated_image"]:
                                    file_media_type = "image"  # Treat both as "image" for simplicity

                                if file_media_type in additional_files:
                                    additional_files[file_media_type].append(file)
                                    LOGGER.info(
                                        f"Found additional {file_media_type} file: {file}"
                                    )
                        except Exception as e:
                            LOGGER.warning(
                                f"Error determining media type for {file}: {e}"
                            )
                except Exception as e:
                    LOGGER.warning(
                        f"Error scanning directory for additional files: {e}"
                    )

            # Process each input placeholder
            for idx in input_indices:
                # If the input is a placeholder, replace it with the appropriate file
                if (
                    ffmpeg[idx] == "input.mp4"
                    or ffmpeg[idx] == "mltb"
                    or ffmpeg[idx].startswith("mltb.")
                ):
                    # Determine the media type requested by the placeholder
                    requested_type = None
                    if ffmpeg[idx] == "mltb.video":
                        requested_type = "video"
                    elif ffmpeg[idx] == "mltb.audio":
                        requested_type = "audio"
                    elif ffmpeg[idx] == "mltb.image":
                        requested_type = "image"
                    elif ffmpeg[idx] == "mltb.subtitle":
                        requested_type = "subtitle"
                    elif ffmpeg[idx] == "mltb.document":
                        requested_type = "document"
                    elif ffmpeg[idx] == "mltb.archive":
                        requested_type = "archive"
                    else:
                        requested_type = "generic"

                    # If this is a specific media type placeholder
                    if requested_type != "generic":
                        # First, check if we have additional files of the requested type
                        if additional_files.get(requested_type):
                            # Get the next unused file of this type
                            for file in additional_files[requested_type]:
                                if file not in used_inputs[requested_type]:
                                    ffmpeg[idx] = file
                                    used_inputs[requested_type].append(file)
                                    LOGGER.info(
                                        f"Using additional file {file} for placeholder mltb.{requested_type}"
                                    )
                                    break

                            # If we found a file, continue to the next placeholder
                            if ffmpeg[idx] != "mltb." + requested_type:
                                continue

                        # Special case for audio extraction from video files
                        if requested_type == "audio" and media_type == "video":
                            # Check if the video file has an audio stream
                            has_audio = False
                            try:
                                # Use ffprobe to check for audio streams
                                process = await create_subprocess_exec(
                                    "xtra",
                                    "-v",
                                    "error",
                                    "-select_streams",
                                    "a",
                                    "-show_entries",
                                    "stream=codec_type",
                                    "-of",
                                    "csv=p=0",
                                    f_path,
                                    stdout=PIPE,
                                    stderr=PIPE,
                                )
                                stdout, stderr = await process.communicate()

                                if stdout and b"audio" in stdout:
                                    has_audio = True
                                    LOGGER.info(
                                        f"Video file {f_path} has audio stream, can be used for audio extraction"
                                    )
                            except Exception as e:
                                LOGGER.warning(
                                    f"Error checking for audio stream: {e}"
                                )

                            if (
                                has_audio
                                and f_path not in used_inputs[requested_type]
                            ):
                                # If we haven't used the main file for this type yet, use it
                                ffmpeg[idx] = f_path
                                used_inputs[requested_type].append(f_path)
                                LOGGER.info(
                                    f"Using main video file with audio stream {f_path} for placeholder mltb.{requested_type}"
                                )
                                continue

                        # If no additional file was found, check if the main input file matches the requested type
                        is_matching_type = (
                            requested_type == "image"
                            and media_type in ["image", "animated_image"]
                        ) or requested_type == media_type

                        # If we haven't used the main file for this type yet, use it
                        if (
                            is_matching_type
                            and f_path not in used_inputs[requested_type]
                        ):
                            ffmpeg[idx] = f_path
                            used_inputs[requested_type].append(f_path)
                            LOGGER.info(
                                f"Using main file {f_path} for placeholder mltb.{requested_type}"
                            )
                            continue

                        # If we still haven't found a file, log a warning and use the main file
                        if requested_type != media_type:
                            LOGGER.warning(
                                f"Placeholder mltb.{requested_type} used but no matching file found. Using main input file."
                            )

                        ffmpeg[idx] = f_path
                        used_inputs["generic"].append(f_path)
                    else:
                        # For generic placeholders (mltb or input.mp4), just use the main file
                        ffmpeg[idx] = f_path
                        used_inputs["generic"].append(f_path)

                # Handle generic media type placeholders (like something.video)
                elif any(
                    ffmpeg[idx].endswith(f".{ext}")
                    for ext in [
                        "video",
                        "audio",
                        "image",
                        "subtitle",
                        "document",
                        "archive",
                    ]
                ):
                    # Extract the requested type from the placeholder
                    for ext in [
                        "video",
                        "audio",
                        "image",
                        "subtitle",
                        "document",
                        "archive",
                    ]:
                        if ffmpeg[idx].endswith(f".{ext}"):
                            requested_type = ext
                            break

                    # First, check if we have additional files of the requested type
                    if additional_files.get(requested_type):
                        for file in additional_files[requested_type]:
                            if file not in used_inputs[requested_type]:
                                ffmpeg[idx] = file
                                used_inputs[requested_type].append(file)
                                LOGGER.info(
                                    f"Using additional file {file} for placeholder ending with .{requested_type}"
                                )
                                break

                        if not ffmpeg[idx].endswith(f".{requested_type}"):
                            continue

                    # If no additional file was found, check if the main input file matches the requested type
                    is_matching_type = (
                        requested_type == "image"
                        and media_type in ["image", "animated_image"]
                    ) or requested_type == media_type

                    if (
                        is_matching_type
                        and f_path not in used_inputs[requested_type]
                    ):
                        ffmpeg[idx] = f_path
                        used_inputs[requested_type].append(f_path)
                        LOGGER.info(
                            f"Using main file {f_path} for placeholder ending with .{requested_type}"
                        )
                        continue

                    # If we still haven't found a file, log a warning and use the main file
                    if requested_type != media_type:
                        LOGGER.warning(
                            f"Placeholder ending with .{requested_type} used but no matching file found. Using main input file."
                        )

                    ffmpeg[idx] = f_path
                    used_inputs["generic"].append(f_path)

        # Check if this is a trim command (which typically has a .trim extension in the output)
        is_trim_command = False
        for item in ffmpeg:
            if isinstance(item, str) and ".trim" in item:
                is_trim_command = True
                break

        # Find all output files in the command
        indices = [
            index
            for index, item in enumerate(ffmpeg)
            if item.startswith("mltb") or item == "mltb"
        ]

        # If no mltb placeholders are found and this is a trim command,
        # we need to find the output file in the command
        if not indices and is_trim_command and len(ffmpeg) > 2:
            # For trim commands, the output file is typically after the input file
            # and before any options that start with "-"
            output_file = None

            # First, try to find a file with .trim. in the name
            for arg in ffmpeg:
                if (
                    isinstance(arg, str)
                    and ".trim." in arg
                    and not arg.startswith("-")
                ):
                    output_file = arg
                    break

            # If that didn't work, look for the last argument that doesn't start with "-"
            # and is after the input file
            if not output_file:
                input_index = -1
                for i, arg in enumerate(ffmpeg):
                    if arg == "-i" and i + 1 < len(ffmpeg):
                        input_index = i + 1
                        break

                if input_index >= 0:
                    for i in range(input_index + 1, len(ffmpeg)):
                        if not ffmpeg[i].startswith("-") and "." in ffmpeg[i]:
                            output_file = ffmpeg[i]

                    if output_file:
                        pass

            # If we still don't have an output file, check if the second-to-last argument
            # looks like a file path (before the -y flag)
            is_valid_output = (
                not output_file
                and len(ffmpeg) >= 2
                and ffmpeg[-1] == "-y"
                and not ffmpeg[-2].startswith("-")
                and "." in ffmpeg[-2]
            )
            if is_valid_output:
                output_file = ffmpeg[-2]

            # If we found an output file, add it to the outputs list
            outputs = [output_file] if output_file else []
        else:
            # Process mltb placeholders
            outputs = []
            for index in indices:
                output_file = ffmpeg[index]

                # Check for dynamic output placeholders like mltb-%d, mltb-%3d, etc.
                dynamic_pattern = compile(r"mltb-%(0?\d*)d")
                dynamic_match = dynamic_pattern.search(output_file)

                # Pass the user_provided_files to the dynamic output processing
                # This allows us to use the correct base name for each input file

                if dynamic_match:
                    # This is a dynamic output placeholder
                    LOGGER.info(f"Found dynamic output placeholder: {output_file}")
                    LOGGER.info(f"Dynamic match: {dynamic_match.group(0)}")
                    LOGGER.info(
                        f"Format width: {dynamic_match.group(1) if dynamic_match.group(1) else 'default'}"
                    )

                    # Extract the format specifier (e.g., %d, %3d, %03d)
                    format_width = dynamic_match.group(1)
                    if format_width and "0" in format_width:
                        # Zero-padded format like %03d
                        format_spec = f"%{format_width}d"
                    elif format_width:
                        # Non-zero-padded format like %3d
                        format_spec = f"%{format_width}d"
                    else:
                        # Simple %d format
                        format_spec = "%d"

                    # Get the base name and extension
                    bo, oext = ospath.splitext(output_file)

                    # Find all map statements to determine how many outputs we need
                    map_count = 0
                    map_indices = []
                    for i, arg in enumerate(ffmpeg):
                        if arg == "-map" and i + 1 < len(ffmpeg):
                            map_count += 1
                            map_indices.append(i)

                    # Check if this is an image sequence output (for frame extraction)
                    is_image_sequence = False
                    for i, arg in enumerate(ffmpeg):
                        if (
                            arg == "-vf"
                            and i + 1 < len(ffmpeg)
                            and "fps=" in ffmpeg[i + 1]
                        ):
                            is_image_sequence = True
                            break

                    # Check if this is a subtitle extraction
                    is_subtitle_extraction = False
                    for i, arg in enumerate(ffmpeg):
                        if arg == "-c:s" or (
                            arg.startswith("-map")
                            and i + 1 < len(ffmpeg)
                            and "s" in ffmpeg[i + 1]
                        ):
                            is_subtitle_extraction = True
                            break

                    # For image sequences, we need to use a different approach
                    if is_image_sequence:
                        LOGGER.info(f"Detected image sequence output: {output_file}")
                        # For image sequences, we need to keep the %d format in the output
                        # FFmpeg requires a pattern like %03d for image sequences

                        # Get the directory and filename parts
                        output_dir = ospath.dirname(output_file)
                        output_filename = ospath.basename(output_file)

                        # Find the closest map statement before this output to determine which input file to use
                        input_index = 0
                        closest_map_index = -1
                        for i in range(index - 1, -1, -1):
                            if ffmpeg[i] == "-map" and i + 1 < len(ffmpeg):
                                closest_map_index = i
                                break

                        # If we found a map statement, check which input file it refers to
                        if closest_map_index >= 0 and closest_map_index + 1 < len(
                            ffmpeg
                        ):
                            map_arg = ffmpeg[closest_map_index + 1]
                            if map_arg.startswith("0:"):
                                input_index = 0
                            elif map_arg.startswith("1:"):
                                input_index = 1
                            elif map_arg.startswith("2:"):
                                input_index = 2
                            elif map_arg.startswith("3:"):
                                input_index = 3
                            elif map_arg.startswith("4:"):
                                input_index = 4
                            # Add more cases if needed
                            LOGGER.info(
                                f"Found map statement {map_arg} for image sequence output at index {index}, using input file {input_index}"
                            )

                        # Use the base name from the appropriate input file if available
                        if user_provided_files:
                            # For bulk processing, user_provided_files might be a list of files
                            if isinstance(
                                user_provided_files, list
                            ) and input_index < len(user_provided_files):
                                # Use the base name from the specified input file
                                input_file = user_provided_files[input_index]
                                input_base_name = ospath.splitext(
                                    ospath.basename(input_file)
                                )[0]
                                LOGGER.info(
                                    f"Using base name from input file {input_index} for image sequence: {input_base_name}"
                                )
                            # For multi-link feature, user_provided_files might be a dictionary with indices as keys
                            elif (
                                isinstance(user_provided_files, dict)
                                and str(input_index) in user_provided_files
                            ):
                                # Use the base name from the specified input file
                                input_file = user_provided_files[str(input_index)]
                                input_base_name = ospath.splitext(
                                    ospath.basename(input_file)
                                )[0]
                                LOGGER.info(
                                    f"Using base name from input file {input_index} for image sequence: {input_base_name}"
                                )
                            # For single file processing with multiple inputs (e.g., adding subtitles)
                            elif (
                                input_index > 0
                                and input_index * 2 + 1 < len(ffmpeg)
                                and ffmpeg[input_index * 2] == "-i"
                            ):
                                # Try to extract the filename from the command
                                input_file = ffmpeg[input_index * 2 + 1]
                                if isinstance(input_file, str) and ospath.exists(
                                    input_file
                                ):
                                    input_base_name = ospath.splitext(
                                        ospath.basename(input_file)
                                    )[0]
                                    LOGGER.info(
                                        f"Using base name from command input file {input_index} for image sequence: {input_base_name}"
                                    )
                                else:
                                    # Use the base name from the primary input file
                                    input_base_name = base_name
                                    LOGGER.info(
                                        f"Using base name from primary input file for image sequence: {input_base_name}"
                                    )
                            else:
                                # Use the base name from the primary input file
                                input_base_name = base_name
                                LOGGER.info(
                                    f"Using base name from primary input file for image sequence: {input_base_name}"
                                )
                        else:
                            # Use the base name from the primary input file
                            input_base_name = base_name
                            LOGGER.info(
                                f"Using base name from primary input file for image sequence: {input_base_name}"
                            )

                        # Replace mltb- with the actual base name but keep the %d format
                        if format_width:
                            # For zero-padded formats like %03d
                            image_output = output_filename.replace(
                                f"mltb-{format_spec}",
                                f"{input_base_name}-%{format_width}d",
                            )
                        else:
                            # For simple %d format
                            image_output = output_filename.replace(
                                f"mltb-{format_spec}", f"{input_base_name}-%d"
                            )

                        # Combine the directory and modified filename
                        if output_dir:
                            image_output = f"{output_dir}/{image_output}"

                        ffmpeg[index] = image_output
                        LOGGER.info(
                            f"Modified image sequence output: {image_output}"
                        )

                        # For testing purposes, add the first expected output file
                        first_frame = image_output.replace(
                            "%d" if not format_width else f"%{format_width}d",
                            "1" if not format_width else "001",
                        )
                        outputs.append(first_frame)

                        # Skip the rest of the processing for this output
                        continue

                    # Check if this is a stream extraction operation (video, audio, subtitle, attachment)
                    is_stream_extraction = False
                    stream_type = None

                    # Check for subtitle extraction
                    if is_subtitle_extraction:
                        is_stream_extraction = True
                        stream_type = "subtitle"
                        LOGGER.info(f"Detected subtitle extraction: {output_file}")

                    # Check for video extraction
                    for i, arg in enumerate(ffmpeg):
                        if arg == "-map" and i + 1 < len(ffmpeg):
                            if ffmpeg[i + 1] == "0:v":
                                is_stream_extraction = True
                                stream_type = "video"
                                LOGGER.info(
                                    f"Detected video extraction: {output_file}"
                                )
                                break
                            if ffmpeg[i + 1] == "0:a":
                                is_stream_extraction = True
                                stream_type = "audio"
                                LOGGER.info(
                                    f"Detected audio extraction: {output_file}"
                                )
                                break
                            if ffmpeg[i + 1] == "0:t":
                                is_stream_extraction = True
                                stream_type = "attachment"
                                LOGGER.info(
                                    f"Detected attachment extraction: {output_file}"
                                )
                                break

                    if is_stream_extraction:
                        # Check if we're trying to extract all streams of a type with a single output file
                        map_all = False
                        for i, arg in enumerate(ffmpeg):
                            if arg == "-map" and i + 1 < len(ffmpeg):
                                map_arg = ffmpeg[i + 1]
                                if (
                                    map_arg in ["0:v", "0:a", "0:s", "0:t"]
                                    and ":" not in map_arg[2:]
                                ):
                                    map_all = True
                                    break

                        if map_all:
                            LOGGER.info(
                                f"Detected command to extract all {stream_type} streams to a single output file"
                            )
                            LOGGER.info(
                                f"Using enhanced stream extraction for {stream_type} streams..."
                            )

                            # Get stream information from the input file
                            streams = await self._get_stream_info(
                                f_path, stream_type
                            )

                            if not streams:
                                LOGGER.warning(
                                    f"No {stream_type} streams found in {f_path}"
                                )
                            else:
                                LOGGER.info(
                                    f"Found {len(streams)} {stream_type} streams in {f_path}"
                                )

                                # Create a separate command for each stream
                                modified_commands = []

                                # Get detailed stream info to determine codec types
                                detailed_streams = (
                                    await self._get_detailed_stream_info(
                                        f_path, stream_type
                                    )
                                )

                                if not detailed_streams and streams:
                                    # If detailed info failed but we have basic stream indices, use those
                                    detailed_streams = [
                                        {"index": idx} for idx in streams
                                    ]

                                LOGGER.info(
                                    f"Found {len(detailed_streams)} {stream_type} streams with details: {detailed_streams}"
                                )

                                for i, stream in enumerate(detailed_streams):
                                    # Create a copy of the original command
                                    cmd = ffmpeg.copy()

                                    # Find the map statement in the command
                                    map_index = -1
                                    for j, arg in enumerate(cmd):
                                        if arg == "-map" and j + 1 < len(cmd):
                                            map_index = j
                                            break

                                    if map_index != -1:
                                        # Replace the map statement to target a specific stream
                                        stream_specifier = {
                                            "video": "v",
                                            "audio": "a",
                                            "subtitle": "s",
                                            "attachment": "t",
                                        }.get(stream_type, "v")

                                        # Use the loop index for mapping, not the stream index
                                        # This ensures we extract streams in the correct order
                                        stream_idx = i
                                        cmd[map_index + 1] = (
                                            f"0:{stream_specifier}:{stream_idx}"
                                        )

                                        # For subtitles, check if we need to modify the codec and extension
                                        if stream_type == "subtitle":
                                            codec = stream.get(
                                                "codec_name", ""
                                            ).lower()
                                            LOGGER.info(f"Stream {i} codec: {codec}")

                                        # Get the extension
                                        _, ext = ospath.splitext(
                                            ospath.basename(f_path)
                                        )

                                        # Format the number according to the format specifier
                                        formatted_num = format_spec % (i + 1)

                                        # Get language tag if available
                                        lang_tag = ""
                                        if "language" in stream:
                                            lang_tag = f"-{stream['language']}"

                                        # Replace the output placeholder with a specific output file
                                        output_idx = index
                                        output_base = output_file.replace(
                                            f"mltb-{format_spec}",
                                            f"{base_name}-{formatted_num}{lang_tag}",
                                        )

                                        # For subtitles, check the codec and use appropriate extension
                                        if stream_type == "subtitle":
                                            codec = stream.get(
                                                "codec_name", ""
                                            ).lower()

                                            # Find the codec specification in the command
                                            codec_index = -1
                                            for j, arg in enumerate(cmd):
                                                if arg in {
                                                    "-c",
                                                    "-c:s",
                                                } and j + 1 < len(cmd):
                                                    codec_index = j + 1
                                                    break

                                            # Determine appropriate extension and codec based on the input codec
                                            LOGGER.info(
                                                f"Processing subtitle stream with codec: {codec}"
                                            )

                                            # Default to copy codec for all subtitle formats
                                            if codec_index != -1:
                                                cmd[codec_index] = "copy"
                                            else:
                                                # Add codec specification if not present
                                                cmd.insert(map_index + 2, "-c:s")
                                                cmd.insert(map_index + 3, "copy")

                                            # Set appropriate file extension based on codec
                                            if codec in ["ass", "ssa"]:
                                                # For ASS/SSA subtitles, use .ass extension
                                                if ".srt" in output_base:
                                                    output_base = (
                                                        output_base.replace(
                                                            ".srt", ".ass"
                                                        )
                                                    )
                                                elif not output_base.endswith(
                                                    ".ass"
                                                ):
                                                    output_base = (
                                                        f"{output_base}.ass"
                                                    )

                                            elif codec in [
                                                "hdmv_pgs_subtitle",
                                                "dvd_subtitle",
                                            ]:
                                                # For PGS/VOB subtitles, use .sup extension
                                                if ".srt" in output_base:
                                                    output_base = (
                                                        output_base.replace(
                                                            ".srt", ".sup"
                                                        )
                                                    )
                                                elif not output_base.endswith(
                                                    ".sup"
                                                ):
                                                    output_base = (
                                                        f"{output_base}.sup"
                                                    )

                                            elif codec in ["subrip", "srt"]:
                                                # For SRT subtitles, ensure .srt extension
                                                if not output_base.endswith(".srt"):
                                                    output_base = (
                                                        f"{output_base}.srt"
                                                    )

                                            elif codec in ["webvtt", "vtt"]:
                                                # For WebVTT subtitles, use .vtt extension
                                                if ".srt" in output_base:
                                                    output_base = (
                                                        output_base.replace(
                                                            ".srt", ".vtt"
                                                        )
                                                    )
                                                elif not output_base.endswith(
                                                    ".vtt"
                                                ):
                                                    output_base = (
                                                        f"{output_base}.vtt"
                                                    )

                                            # For other subtitle formats, keep the original extension or use .srt as fallback
                                            elif not any(
                                                output_base.endswith(ext)
                                                for ext in [
                                                    ".srt",
                                                    ".ass",
                                                    ".sup",
                                                    ".vtt",
                                                ]
                                            ):
                                                output_base = f"{output_base}.srt"

                                            LOGGER.info(
                                                f"Using output file: {output_base} for subtitle codec: {codec}"
                                            )

                                        # Ensure we don't duplicate the directory path
                                        if not output_base.startswith(dir):
                                            dynamic_output = f"{dir}/{output_base}"
                                        else:
                                            dynamic_output = output_base

                                        cmd[output_idx] = dynamic_output

                                        # Add the command to the list
                                        modified_commands.append(cmd)

                                if modified_commands:
                                    LOGGER.info(
                                        f"Generated {len(modified_commands)} separate commands for {stream_type} extraction"
                                    )

                                    # Execute each command separately
                                    all_outputs = []

                                    # Execute all commands individually for consistent handling
                                    for i, cmd in enumerate(modified_commands):
                                        LOGGER.info(
                                            f"Executing command for {stream_type} stream {i + 1}"
                                        )

                                        # Execute the command
                                        try:
                                            process = await create_subprocess_exec(
                                                *cmd, stdout=PIPE, stderr=PIPE
                                            )

                                            _, stderr = await process.communicate()
                                            code = process.returncode

                                            if code == 0:
                                                # Check if the output file exists and has content
                                                output_file = cmd[index]
                                                if (
                                                    await aiopath.exists(output_file)
                                                    and await aiopath.getsize(
                                                        output_file
                                                    )
                                                    > 0
                                                ):
                                                    all_outputs.append(output_file)
                                                    # Also add to the main outputs list
                                                    if output_file not in outputs:
                                                        outputs.append(output_file)
                                                    LOGGER.info(
                                                        f"Successfully extracted {stream_type} stream to {output_file}"
                                                    )
                                                else:
                                                    LOGGER.error(
                                                        f"Output file {output_file} does not exist or is empty"
                                                    )
                                            else:
                                                stderr_text = (
                                                    stderr.decode()
                                                    if stderr
                                                    else "Unknown error"
                                                )
                                                LOGGER.error(
                                                    f"Failed to extract {stream_type} stream: {stderr_text}"
                                                )
                                        except Exception as e:
                                            LOGGER.error(
                                                f"Error executing FFmpeg command: {e}"
                                            )

                                    # Add all outputs to the outputs list
                                    outputs.extend(all_outputs)

                                    # Skip the normal processing since we've already handled all streams
                                    LOGGER.info(
                                        f"All {stream_type} streams have been processed individually, skipping the main command"
                                    )
                                    return outputs

                            # Continue with the first command in the normal processing flow
                            LOGGER.info(
                                f"Continuing with the first {stream_type} extraction command"
                            )

                        # Continue with normal processing

                    # If no map statements found, default to 1 output
                    if map_count == 0:
                        map_count = 1

                    # In reality, FFmpeg only creates one output file per format specifier
                    # So we only generate one output file per format specifier
                    actual_map_count = 1

                    LOGGER.info(
                        f"Generating {actual_map_count} dynamic output(s) with format: {format_spec}"
                    )

                    # Generate output files
                    dynamic_outputs = []

                    # For multiple inputs, we need to handle each input separately
                    # The primary input file is used for the base name
                    # But we need to keep track of which input file is being processed

                    # Get the input file index from the map statement if available
                    # We need to check which map statement corresponds to this output
                    input_index = 0

                    # Find the closest map statement before this output
                    closest_map_index = -1
                    for i in range(index - 1, -1, -1):
                        if ffmpeg[i] == "-map" and i + 1 < len(ffmpeg):
                            closest_map_index = i
                            break

                    # If we found a map statement, check which input file it refers to
                    if closest_map_index >= 0 and closest_map_index + 1 < len(
                        ffmpeg
                    ):
                        map_arg = ffmpeg[closest_map_index + 1]
                        if map_arg.startswith("0:"):
                            input_index = 0
                        elif map_arg.startswith("1:"):
                            input_index = 1
                        elif map_arg.startswith("2:"):
                            input_index = 2
                        elif map_arg.startswith("3:"):
                            input_index = 3
                        elif map_arg.startswith("4:"):
                            input_index = 4
                        # Add more cases if needed
                        LOGGER.info(
                            f"Found map statement {map_arg} for output at index {index}, using input file {input_index}"
                        )

                        # For subtitle files, we always want to use the video file (input 0) as the base name
                        # This is because subtitle files are typically named differently from the video
                        if (
                            "s:" in map_arg
                            or map_arg.endswith(":s")
                            or (
                                closest_map_index + 3 < len(ffmpeg)
                                and ffmpeg[closest_map_index + 2] == "-c:s"
                            )
                        ):
                            LOGGER.info(
                                "Detected subtitle stream, using video file (input 0) as base name"
                            )
                            input_index = 0

                    # Use the base name from the appropriate input file if available
                    # Check if user_provided_files is available and has multiple files
                    if user_provided_files:
                        # For bulk processing, user_provided_files might be a list of files
                        if isinstance(
                            user_provided_files, list
                        ) and input_index < len(user_provided_files):
                            # Use the base name from the specified input file
                            input_file = user_provided_files[input_index]
                            input_base_name = ospath.splitext(
                                ospath.basename(input_file)
                            )[0]
                            LOGGER.info(
                                f"Using base name from input file {input_index}: {input_base_name}"
                            )
                        # For multi-link feature, user_provided_files might be a dictionary with indices as keys
                        elif (
                            isinstance(user_provided_files, dict)
                            and str(input_index) in user_provided_files
                        ):
                            # Use the base name from the specified input file
                            input_file = user_provided_files[str(input_index)]
                            input_base_name = ospath.splitext(
                                ospath.basename(input_file)
                            )[0]
                            LOGGER.info(
                                f"Using base name from input file {input_index}: {input_base_name}"
                            )
                        # For single file processing with multiple inputs (e.g., adding subtitles)
                        elif (
                            input_index > 0
                            and input_index < len(ffmpeg)
                            and ffmpeg[input_index * 2] == "-i"
                        ):
                            # Try to extract the filename from the command
                            input_file = ffmpeg[input_index * 2 + 1]
                            if isinstance(input_file, str) and ospath.exists(
                                input_file
                            ):
                                input_base_name = ospath.splitext(
                                    ospath.basename(input_file)
                                )[0]
                                LOGGER.info(
                                    f"Using base name from command input file {input_index}: {input_base_name}"
                                )
                            else:
                                # Use the base name from the primary input file
                                input_base_name = base_name
                        else:
                            # Use the base name from the primary input file
                            input_base_name = base_name
                    else:
                        # Use the base name from the primary input file
                        input_base_name = base_name

                    for i in range(actual_map_count):
                        # Format the number according to the format specifier
                        formatted_num = format_spec % (i + 1)

                        # Replace the placeholder with the formatted number
                        dynamic_output = output_file.replace(
                            f"mltb-{format_spec}",
                            f"{input_base_name}-{formatted_num}",
                        )

                        # Add to outputs list - ensure we don't duplicate the directory path
                        if dynamic_output.startswith(dir):
                            dynamic_outputs.append(dynamic_output)
                        else:
                            dynamic_outputs.append(f"{dir}/{dynamic_output}")

                    # Replace the placeholder in the command with the first output
                    # FFmpeg will automatically create the other outputs based on the -map statements
                    ffmpeg[index] = dynamic_outputs[0]

                    # Log the final command for debugging
                    LOGGER.info(
                        f"Final FFmpeg command with dynamic output: {' '.join(str(x) for x in ffmpeg)}"
                    )

                    # Add all dynamic outputs to the outputs list
                    outputs.extend(dynamic_outputs)

                    LOGGER.info(f"Dynamic outputs: {dynamic_outputs}")
                elif output_file != "mltb" and output_file.startswith("mltb"):
                    bo, oext = ospath.splitext(output_file)
                    if oext:
                        if ext == oext:
                            prefix = f"ffmpeg{index}." if bo == "mltb" else ""
                        else:
                            prefix = ""
                        ext = ""
                    else:
                        prefix = ""

                    # Create the output path, ensuring we don't duplicate the directory
                    processed_output = (
                        f"{prefix}{output_file.replace('mltb', base_name)}{ext}"
                    )
                    if processed_output.startswith(dir):
                        output = processed_output
                    else:
                        output = f"{dir}/{processed_output}"

                    outputs.append(output)
                    ffmpeg[index] = output
                    LOGGER.info(f"Regular output path: {output}")
                else:
                    prefix = f"ffmpeg{index}."

                    # Create the output path, ensuring we don't duplicate the directory
                    processed_output = (
                        f"{prefix}{output_file.replace('mltb', base_name)}{ext}"
                    )
                    if processed_output.startswith(dir):
                        output = processed_output
                    else:
                        output = f"{dir}/{processed_output}"

                    outputs.append(output)
                    ffmpeg[index] = output
                    LOGGER.info(f"Default output path: {output}")

            # If no outputs were found, try to find output files based on common patterns
            if not outputs:
                # First, look for arguments after -map that don't start with "[" (not filter references)
                # and don't start with "-" (not options)
                map_indices = [i for i, arg in enumerate(ffmpeg) if arg == "-map"]
                for idx in map_indices:
                    if (
                        idx + 1 < len(ffmpeg)
                        and not ffmpeg[idx + 1].startswith("[")
                        and not ffmpeg[idx + 1].startswith("-")
                    ):
                        # This might be an output file specification
                        continue

                # Next, try to find the last non-option argument as the output
                for i in range(len(ffmpeg) - 1, -1, -1):
                    if (
                        not ffmpeg[i].startswith("-")
                        and i not in input_indices
                        and "." in ffmpeg[i]
                    ):
                        # Check if this is likely an output file (not a filter or other parameter)
                        # Output files typically come after all input files and have an extension
                        is_after_inputs = True
                        for input_idx in input_indices:
                            if i < input_idx:
                                is_after_inputs = False
                                break

                        if is_after_inputs:
                            outputs.append(ffmpeg[i])
                            break

                # If still no outputs found, look for common output file extensions
                if not outputs:
                    common_extensions = [
                        ".mp4",
                        ".mkv",
                        ".avi",
                        ".mov",
                        ".mp3",
                        ".m4a",
                        ".wav",
                        ".jpg",
                        ".png",
                        ".webp",
                    ]
                    for i in range(len(ffmpeg) - 1, -1, -1):
                        if i not in input_indices and isinstance(ffmpeg[i], str):
                            for ext in common_extensions:
                                if ffmpeg[i].lower().endswith(ext):
                                    outputs.append(ffmpeg[i])
                                    break
                            if outputs:
                                break

        if self._listener.is_cancelled:
            return False

        # Save the original file size for comparison
        original_file_size = 0
        try:
            if await aiopath.exists(f_path):
                original_file_size = await aiopath.getsize(f_path)
        except Exception as e:
            LOGGER.error(f"Error getting original file size: {e}")

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *ffmpeg,
            stdout=PIPE,
            stderr=PIPE,
        )

        await self._ffmpeg_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if self._listener.is_cancelled:
            return False

        # Check if the command was successful
        if code == 0:
            # Check if all output files exist and have valid content before deleting the original
            all_outputs_valid = True
            total_output_size = 0

            # First check if any output files exist
            any_outputs_exist = False
            for output in outputs:
                if await aiopath.exists(output):
                    any_outputs_exist = True
                    break

            if not any_outputs_exist:
                LOGGER.error(
                    "FFmpeg command completed successfully but no output files were created"
                )
                return False

            # Now check if all output files are valid
            for output in outputs:
                if not await aiopath.exists(output):
                    all_outputs_valid = False
                    LOGGER.error(f"Output file does not exist: {output}")
                    break

                # Check if the output file has valid content (non-zero size)
                try:
                    output_size = await aiopath.getsize(output)
                    total_output_size += output_size

                    if output_size == 0:
                        all_outputs_valid = False
                        LOGGER.error(
                            f"Output file exists but has zero size: {output}"
                        )
                        break

                    # Verify the output file is a valid media file if it has a media extension
                    output_ext = ospath.splitext(output)[1].lower()
                    if output_ext in [
                        ".mp4",
                        ".mkv",
                        ".avi",
                        ".mov",
                        ".webm",
                        ".mp3",
                        ".m4a",
                        ".wav",
                        ".ogg",
                        ".flac",
                    ]:
                        try:
                            # Try to get media info to verify it's a valid media file
                            media_info = await get_media_info(output)
                            if media_info[0] <= 0 and media_info[1] <= 0:
                                LOGGER.warning(
                                    f"Output file {output} appears to be a valid file but may not be a valid media file. Continuing anyway."
                                )
                        except Exception as e:
                            LOGGER.warning(
                                f"Could not verify if {output} is a valid media file: {e}. Continuing anyway."
                            )

                except Exception as e:
                    all_outputs_valid = False
                    LOGGER.error(f"Error checking output file size: {e}")
                    break

            # Additional check: make sure the total output size is reasonable
            # (at least 1% of the original file size for most operations)
            if (
                all_outputs_valid
                and original_file_size > 0
                and total_output_size < (original_file_size * 0.01)
            ):
                # For certain operations, the output can be much smaller than the original
                # Check if this is a known operation that produces small outputs
                small_output_operation = False

                # Check for common operations that produce small outputs
                for cmd in ffmpeg:
                    if any(
                        x in str(cmd)
                        for x in [
                            "extract",
                            "trim",
                            "thumbnail",
                            "screenshot",
                            "sample",
                        ]
                    ):
                        small_output_operation = True
                        break

                if small_output_operation:
                    LOGGER.info(
                        f"Output size is small ({total_output_size} bytes) compared to input ({original_file_size} bytes), but this appears to be a valid operation that produces small outputs."
                    )
                else:
                    LOGGER.warning(
                        f"Output size is suspiciously small: {total_output_size} bytes (input: {original_file_size} bytes). This might indicate a problem with the FFmpeg command."
                    )

            # If -del flag was used and all outputs are valid, delete original files
            if delete_files and all_outputs_valid and await aiopath.exists(f_path):
                try:
                    await remove(f_path)
                    LOGGER.info(f"Deleted original file after processing: {f_path}")
                except Exception as e:
                    LOGGER.error(f"Error deleting original file: {e}")

            # Only return the outputs if they are valid
            if all_outputs_valid:
                return outputs
            LOGGER.error("FFmpeg command completed but output files are not valid")
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(
            f"{stderr}. Something went wrong while running xtra cmd, mostly file requires different/specific arguments. Path: {f_path}",
        )
        for op in outputs:
            if await aiopath.exists(op):
                await remove(op)
        return False

    async def metadata_watermark_cmds(self, ffmpeg, f_path):
        self.clear()

        # Check for any temporary metadata files that might have been created
        meta_file = f"{f_path}.meta"

        # Special case for document files - check if the command is a dummy command
        if (
            ffmpeg
            and len(ffmpeg) >= 2
            and ffmpeg[0] == "echo"
            and "apply_document_metadata" in ffmpeg[1]
        ):
            # This is a document file that should be processed with apply_document_metadata
            LOGGER.info(
                f"Processing document file with apply_document_metadata: {f_path}"
            )

            # Get the original file path (remove .temp extension if present)
            original_file = f_path
            if ".temp" in original_file:
                original_file = original_file.replace(".temp", "")

            # Use the apply_document_metadata function from this module

            # Get metadata from listener
            try:
                title = self._listener.user_dict.get("metadata-title", "")
                author = self._listener.user_dict.get("metadata-author", "")
                comment = self._listener.user_dict.get("metadata-comment", "")
            except AttributeError:
                # For testing purposes, use default values
                LOGGER.info("Using default metadata values for testing")
                title = "Test Title"
                author = "Test Author"
                comment = "Test Comment"

            # Apply metadata
            success = await apply_document_metadata(
                original_file, title, author, comment
            )

            if success:
                LOGGER.info(
                    f"Successfully applied metadata to document file: {original_file}"
                )
                return True
            LOGGER.error(
                f"Failed to apply metadata to document file: {original_file}"
            )
            return False

        # Special case for subtitle watermarking - xtra will be None
        if ffmpeg is None:
            # This is a subtitle file that was processed directly without FFmpeg
            # The temp_file is in f_path, and we need to replace the original file with it
            temp_file = f_path
            original_file = temp_file.replace(".temp", "")

            try:
                # Check if the temp file exists
                if await aiopath.exists(temp_file):
                    # Replace the original file with the watermarked version
                    import shutil

                    shutil.move(temp_file, original_file)
                    LOGGER.info(
                        f"Replaced original subtitle file with watermarked version: {original_file}"
                    )

                    # Clean up any temporary metadata files
                    if await aiopath.exists(meta_file):
                        try:
                            await remove(meta_file)
                            LOGGER.info(
                                f"Removed temporary metadata file: {meta_file}"
                            )
                        except Exception:
                            pass

                    return True
                LOGGER.error(f"Temp subtitle file not found: {temp_file}")
                return False
            except Exception as e:
                LOGGER.error(f"Error replacing subtitle file: {e}")

                # Clean up any temporary metadata files even if there was an error
                if await aiopath.exists(meta_file):
                    try:
                        await remove(meta_file)
                        LOGGER.info(
                            f"Removed temporary metadata file after error: {meta_file}"
                        )
                    except Exception:
                        pass

                return False

        # Normal case with FFmpeg command
        self._total_time = (await get_media_info(f_path))[0]
        if self._listener.is_cancelled:
            return False

        # Check for -del flag to delete original files after processing
        delete_files = False
        if "-del" in ffmpeg:
            ffmpeg.remove("-del")
            delete_files = True

        # Replace 'ffmpeg' with 'xtra' as the command name
        if ffmpeg and ffmpeg[0] == "xtra":
            ffmpeg[0] = "xtra"

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *ffmpeg,
            stdout=PIPE,
            stderr=PIPE,
        )

        await self._ffmpeg_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        # Clean up any temporary metadata files
        if await aiopath.exists(meta_file):
            try:
                await remove(meta_file)
                LOGGER.info(f"Removed temporary metadata file: {meta_file}")
            except Exception:
                pass

        if self._listener.is_cancelled:
            return False
        if code == 0:
            # Save the original file size for comparison
            original_file_size = 0
            try:
                if await aiopath.exists(f_path):
                    original_file_size = await aiopath.getsize(f_path)
            except Exception as e:
                LOGGER.error(f"Error getting original file size: {e}")

            # Check if the operation produced valid output files
            # For metadata operations, we need to check if the output file exists and has valid content
            output_valid = True

            # For most metadata operations, the output is written back to the original file
            # So we need to check if the original file still exists and has valid content
            if await aiopath.exists(f_path):
                try:
                    output_size = await aiopath.getsize(f_path)
                    if output_size == 0:
                        output_valid = False
                        LOGGER.error(
                            f"Output file exists but has zero size: {f_path}"
                        )

                    # Additional check: make sure the output size is reasonable
                    # (at least 1% of the original file size for most operations)
                    elif original_file_size > 0 and output_size < (
                        original_file_size * 0.01
                    ):
                        # For some operations, the output can be much smaller than the original
                        # So we'll only log a warning but still consider it valid
                        pass
                except Exception as e:
                    output_valid = False
                    LOGGER.error(f"Error checking output file size: {e}")
            else:
                output_valid = False
                LOGGER.error(f"Output file does not exist: {f_path}")

            # Handle -del flag if needed, but only if the operation was successful and produced valid output
            if delete_files and output_valid and await aiopath.exists(f_path):
                try:
                    await remove(f_path)
                    LOGGER.info(f"Deleted original file after processing: {f_path}")
                except Exception as e:
                    LOGGER.error(f"Error deleting original file: {e}")

            # Return success only if the output is valid
            return output_valid
        if code == -9:
            self._listener.is_cancelled = True
            return False
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(
            f"{stderr}. Something went wrong while running xtra cmd, mostly file requires different/specific arguments. Path: {f_path}",
        )
        return False

    async def convert_video(
        self, video_file, ext, retry=False, second_retry=False, delete_original=False
    ):
        self.clear()

        # Ensure video_file is an absolute path
        video_file = ospath.abspath(video_file)

        # Check if the file exists
        if not await aiopath.exists(video_file):
            LOGGER.error(f"Video file does not exist: {video_file}")
            return False

        self._total_time = (await get_media_info(video_file))[0]

        # For settings-based configs, check if ext is None or "none" (case-insensitive)
        # This check is only for settings-based configs, not for command-line flags
        # Command-line flags are already validated before calling this function
        if not ext or ext.lower() == "none":
            LOGGER.info(
                f"Video conversion format is empty or 'none', skipping conversion for: {video_file}"
            )
            return video_file

        base_name = ospath.splitext(video_file)[0]
        output = f"{base_name}.{ext}"

        # Check if the output file already exists and is the same as input
        if output == video_file:
            LOGGER.info(f"Output file is the same as input file: {video_file}")
            return video_file

        # Log if we're going to delete the original file after conversion
        if delete_original:
            pass

        # Get custom video settings from listener if available
        video_codec = getattr(self._listener, "convert_video_codec", None)
        # Removed unused variable: video_quality
        video_crf = getattr(self._listener, "convert_video_crf", None)
        video_preset = getattr(self._listener, "convert_video_preset", None)
        # Removed unused variable: maintain_quality

        # Check if custom settings are valid (not None or "none")
        has_custom_codec = video_codec and video_codec.lower() != "none"
        # Removed unused variable: has_custom_quality
        has_custom_crf = video_crf and video_crf != 0
        has_custom_preset = video_preset and video_preset.lower() != "none"

        # Special handling for WebM format
        if ext == "webm":
            # Base command
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_file,
                "-map",
                "0:v:0",  # Take only the first video stream
                "-map",
                "0:a:0?",  # Take the first audio stream if it exists
            ]

            # Add video codec
            if has_custom_codec:
                cmd.extend(["-c:v", video_codec])
            else:
                cmd.extend(["-c:v", "libvpx-vp9"])  # Use VP9 codec for video

            # Add audio codec
            cmd.extend(["-c:a", "libopus"])  # Use Opus codec for audio

            # Add video bitrate
            cmd.extend(["-b:v", "1M"])  # Video bitrate

            # Add audio bitrate
            cmd.extend(["-b:a", "128k"])  # Audio bitrate

            # Add pixel format
            cmd.extend(["-pix_fmt", "yuv420p"])  # Pixel format

            # Add scale filter
            cmd.extend(
                ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
            )  # Ensure even dimensions

            # Add CRF if specified
            if has_custom_crf:
                cmd.extend(["-crf", str(video_crf)])

            # Add preset if specified
            if has_custom_preset:
                cmd.extend(["-preset", video_preset])

            # Add threads
            cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

            # Add output file
            cmd.append(output)
        elif second_retry:
            # For complex files with multiple streams, use only video and audio streams
            # Special handling for anime files with multiple streams
            if ext == "mp4":
                # Base command
                cmd = [
                    "xtra",  # Using xtra instead of ffmpeg
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-progress",
                    "pipe:1",
                    "-i",
                    video_file,
                    "-map",
                    "0:v:0",  # Take only the first video stream
                    "-map",
                    "0:a:0?",  # Take the first audio stream if it exists
                ]

                # Add video codec
                if has_custom_codec:
                    cmd.extend(["-c:v", video_codec])
                else:
                    cmd.extend(["-c:v", "libx264"])

                # Add audio codec
                cmd.extend(["-c:a", "aac"])

                # Add pixel format
                cmd.extend(["-pix_fmt", "yuv420p"])  # Ensure compatible pixel format

                # Add scale filter
                cmd.extend(
                    ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
                )  # Ensure even dimensions

                # Add preset
                if has_custom_preset:
                    cmd.extend(["-preset", video_preset])
                else:
                    cmd.extend(
                        ["-preset", "medium"]
                    )  # Balance between speed and quality

                # Add CRF
                if has_custom_crf:
                    cmd.extend(["-crf", str(video_crf)])
                else:
                    cmd.extend(["-crf", "23"])  # Quality level (lower is better)

                # Add threads
                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

                # Add output file
                cmd.append(output)
            else:
                # For MKV, we can include subtitles
                # Base command
                cmd = [
                    "xtra",  # Using xtra instead of ffmpeg
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-progress",
                    "pipe:1",
                    "-i",
                    video_file,
                    "-map",
                    "0:v:0",  # Take only the first video stream
                    "-map",
                    "0:a:0?",  # Take the first audio stream if it exists
                    "-map",
                    "0:s:0?",  # Take the first subtitle stream if it exists
                ]

                # Add video codec
                if has_custom_codec:
                    cmd.extend(["-c:v", video_codec])
                else:
                    cmd.extend(["-c:v", "libx264"])

                # Add audio codec
                cmd.extend(["-c:a", "aac"])

                # Add subtitle codec
                cmd.extend(["-c:s", "copy"])  # Copy subtitles

                # Add pixel format
                cmd.extend(["-pix_fmt", "yuv420p"])  # Ensure compatible pixel format

                # Add scale filter
                cmd.extend(
                    ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
                )  # Ensure even dimensions

                # Add preset
                if has_custom_preset:
                    cmd.extend(["-preset", video_preset])
                else:
                    cmd.extend(
                        ["-preset", "medium"]
                    )  # Balance between speed and quality

                # Add CRF
                if has_custom_crf:
                    cmd.extend(["-crf", str(video_crf)])
                else:
                    cmd.extend(["-crf", "23"])  # Quality level (lower is better)

                # Add format-specific optimizations for Telegram compatibility
                if ext == "mp4":
                    cmd.extend(
                        [
                            "-movflags",
                            "+faststart",  # Streaming optimization
                            "-pix_fmt",
                            "yuv420p",  # Compatible pixel format
                            "-profile:v",
                            "main",  # Compatible H.264 profile
                            "-level",
                            "4.0",  # Compatible H.264 level
                        ]
                    )
                elif ext == "mkv":
                    cmd.extend(
                        [
                            "-pix_fmt",
                            "yuv420p",  # Compatible pixel format
                            "-disposition:v:0",
                            "default",  # Set video as default
                            "-disposition:a:0",
                            "default",  # Set audio as default
                        ]
                    )
                elif ext == "webm":
                    cmd.extend(
                        [
                            "-pix_fmt",
                            "yuv420p",  # Compatible pixel format
                            "-deadline",
                            "good",  # VP9 optimization
                            "-cpu-used",
                            "2",  # VP9 speed/quality balance
                            "-row-mt",
                            "1",  # VP9 multithreading
                        ]
                    )
                elif ext == "mov":
                    cmd.extend(
                        [
                            "-movflags",
                            "+faststart",  # Streaming optimization (MOV uses same structure as MP4)
                            "-pix_fmt",
                            "yuv420p",  # Compatible pixel format
                            "-profile:v",
                            "main",  # Compatible H.264 profile
                            "-level",
                            "4.0",  # Compatible H.264 level
                        ]
                    )
                else:
                    # Universal compatibility for other formats
                    cmd.extend(["-pix_fmt", "yuv420p"])

                # Add threads
                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

                # Add output file
                cmd.append(output)
        elif retry:
            # Base command
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_file,
                "-map",
                "0",
                "-ignore_unknown",
            ]

            # Add video codec
            if has_custom_codec:
                cmd.extend(["-c:v", video_codec])
            else:
                cmd.extend(["-c:v", "libx264"])

            # Add audio codec
            cmd.extend(["-c:a", "aac"])

            # Add pixel format
            cmd.extend(["-pix_fmt", "yuv420p"])  # Ensure compatible pixel format

            # Add scale filter
            cmd.extend(
                ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
            )  # Ensure even dimensions

            # Add CRF if specified
            if has_custom_crf:
                cmd.extend(["-crf", str(video_crf)])
            else:
                cmd.extend(["-crf", "23"])  # Default CRF

            # Add preset if specified
            if has_custom_preset:
                cmd.extend(["-preset", video_preset])
            else:
                cmd.extend(["-preset", "medium"])  # Default preset

            # Add format-specific optimizations for Telegram compatibility
            if ext == "mp4":
                cmd.extend(
                    [
                        "-movflags",
                        "+faststart",  # Streaming optimization
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-profile:v",
                        "main",  # Compatible H.264 profile
                        "-level",
                        "4.0",  # Compatible H.264 level
                    ]
                )
            elif ext == "mkv":
                cmd.extend(
                    [
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-disposition:v:0",
                        "default",  # Set video as default
                        "-disposition:a:0",
                        "default",  # Set audio as default
                    ]
                )
            elif ext == "webm":
                cmd.extend(
                    [
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-deadline",
                        "good",  # VP9 optimization
                        "-cpu-used",
                        "2",  # VP9 speed/quality balance
                        "-row-mt",
                        "1",  # VP9 multithreading
                    ]
                )
            elif ext == "mov":
                cmd.extend(
                    [
                        "-movflags",
                        "+faststart",  # Streaming optimization (MOV uses same structure as MP4)
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-profile:v",
                        "main",  # Compatible H.264 profile
                        "-level",
                        "4.0",  # Compatible H.264 level
                    ]
                )
            else:
                # Universal compatibility for other formats
                cmd.extend(["-pix_fmt", "yuv420p"])

            # Add threads
            cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

            # Add output file
            cmd.append(output)

            # Add subtitle codec based on output format
            if ext == "mp4":
                cmd[21:21] = ["-c:s", "mov_text"]
            elif ext == "mkv":
                cmd[21:21] = ["-c:s", "ass"]
            else:
                cmd[21:21] = ["-c:s", "copy"]
        # First try with simple copy (faster if format is compatible)
        # But if user has specified custom settings, we'll use them instead of copy
        elif has_custom_codec or has_custom_crf or has_custom_preset:
            # Base command
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_file,
                "-map",
                "0",
                "-ignore_unknown",
            ]

            # Add video codec
            if has_custom_codec:
                cmd.extend(["-c:v", video_codec])
            else:
                cmd.extend(["-c:v", "copy"])

            # Add audio codec (always copy in first attempt)
            cmd.extend(["-c:a", "copy"])

            # Add subtitle codec (always copy in first attempt)
            cmd.extend(["-c:s", "copy"])

            # Add CRF if specified and not using copy codec
            if has_custom_crf and has_custom_codec and video_codec.lower() != "copy":
                cmd.extend(["-crf", str(video_crf)])

            # Add preset if specified and not using copy codec
            if (
                has_custom_preset
                and has_custom_codec
                and video_codec.lower() != "copy"
            ):
                cmd.extend(["-preset", video_preset])

            # Add format-specific optimizations for Telegram compatibility
            if ext == "mp4":
                cmd.extend(
                    [
                        "-movflags",
                        "+faststart",  # Streaming optimization
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-profile:v",
                        "main",  # Compatible H.264 profile
                        "-level",
                        "4.0",  # Compatible H.264 level
                    ]
                )
            elif ext == "mkv":
                cmd.extend(
                    [
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-disposition:v:0",
                        "default",  # Set video as default
                        "-disposition:a:0",
                        "default",  # Set audio as default
                    ]
                )
            elif ext == "webm":
                cmd.extend(
                    [
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-deadline",
                        "good",  # VP9 optimization
                        "-cpu-used",
                        "2",  # VP9 speed/quality balance
                        "-row-mt",
                        "1",  # VP9 multithreading
                    ]
                )
            elif ext == "mov":
                cmd.extend(
                    [
                        "-movflags",
                        "+faststart",  # Streaming optimization (MOV uses same structure as MP4)
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-profile:v",
                        "main",  # Compatible H.264 profile
                        "-level",
                        "4.0",  # Compatible H.264 level
                    ]
                )
            else:
                # Universal compatibility for other formats
                cmd.extend(["-pix_fmt", "yuv420p"])

            # Add threads
            cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

            # Add output file
            cmd.append(output)
        else:
            # Use simple copy for all streams
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_file,
                "-map",
                "0",
                "-ignore_unknown",
                "-c",
                "copy",
            ]

            # Add format-specific optimizations for Telegram compatibility
            if ext == "mp4":
                cmd.extend(
                    [
                        "-movflags",
                        "+faststart",  # Streaming optimization
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-profile:v",
                        "main",  # Compatible H.264 profile
                        "-level",
                        "4.0",  # Compatible H.264 level
                    ]
                )
            elif ext == "mkv":
                cmd.extend(
                    [
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-disposition:v:0",
                        "default",  # Set video as default
                        "-disposition:a:0",
                        "default",  # Set audio as default
                    ]
                )
            elif ext == "webm":
                cmd.extend(
                    [
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-deadline",
                        "good",  # VP9 optimization
                        "-cpu-used",
                        "2",  # VP9 speed/quality balance
                        "-row-mt",
                        "1",  # VP9 multithreading
                    ]
                )
            elif ext == "mov":
                cmd.extend(
                    [
                        "-movflags",
                        "+faststart",  # Streaming optimization (MOV uses same structure as MP4)
                        "-pix_fmt",
                        "yuv420p",  # Compatible pixel format
                        "-profile:v",
                        "main",  # Compatible H.264 profile
                        "-level",
                        "4.0",  # Compatible H.264 level
                    ]
                )
            else:
                # Universal compatibility for other formats
                cmd.extend(["-pix_fmt", "yuv420p"])

            cmd.extend(
                [
                    "-threads",
                    f"{max(1, cpu_no // 2)}",
                    output,
                ]
            )

        if self._listener.is_cancelled:
            return False

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )

        await self._ffmpeg_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if self._listener.is_cancelled:
            return False
        if code == 0:
            # If delete_original is True, delete the original file after successful conversion
            if (
                delete_original
                and await aiopath.exists(video_file)
                and video_file != output
            ):
                try:
                    await remove(video_file)
                    LOGGER.info(f"Successfully deleted original file: {video_file}")
                except Exception as e:
                    LOGGER.error(
                        f"Error deleting original file in convert_video: {e}"
                    )
                    # Try again with a different approach
                    try:
                        import os

                        os.remove(video_file)
                        LOGGER.info(
                            f"Successfully deleted original file using os.remove: {video_file}"
                        )
                    except Exception as e2:
                        LOGGER.error(f"Second attempt to delete file failed: {e2}")
            return output
        if code == -9:
            self._listener.is_cancelled = True
            return False
        if await aiopath.exists(output):
            await remove(output)

        # If first attempt failed and we're not in retry mode, try with transcoding
        if not retry:
            LOGGER.info(
                f"Copy codec failed for {video_file}, trying with transcoding"
            )
            return await self.convert_video(
                video_file, ext, True, False, delete_original
            )

        # If first retry failed, try with only video and audio streams
        if retry and not second_retry:
            LOGGER.info(
                f"Full stream transcoding failed for {video_file}, trying with only video and audio streams"
            )
            return await self.convert_video(
                video_file, ext, True, True, delete_original
            )

        # Special handling for WebM format
        if ext == "webm" and not second_retry:
            LOGGER.info(f"Using VP9 codec for WebM conversion: {video_file}")
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_file,
                "-map",
                "0:v:0",  # Take only the first video stream
                "-map",
                "0:a:0?",  # Take the first audio stream if it exists
                "-c:v",
                "libvpx-vp9",  # Use VP9 codec for video
                "-c:a",
                "libopus",  # Use Opus codec for audio (better than Vorbis for WebM)
                "-crf",
                "30",  # Default CRF for VP9
                "-b:v",
                "0",  # Use CRF mode
                "-cpu-used",
                "2",  # Balance between quality and speed
                "-deadline",
                "good",
                "-pix_fmt",
                "yuv420p",  # Pixel format
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
                "-threads",
                f"{max(1, cpu_no // 2)}",
                output,
            ]

            self._listener.subproc = await create_subprocess_exec(
                *cmd,
                stdout=PIPE,
                stderr=PIPE,
            )

            await self._ffmpeg_progress()
            _, stderr = await self._listener.subproc.communicate()
            code = self._listener.subproc.returncode

            if self._listener.is_cancelled:
                return False
            if code == 0:
                # If delete_original is True, delete the original file after successful conversion
                if (
                    delete_original
                    and await aiopath.exists(video_file)
                    and video_file != output
                ):
                    try:
                        await remove(video_file)
                        LOGGER.info(
                            f"Deleted original file after WebM VP9 conversion: {video_file}"
                        )
                    except Exception as e:
                        LOGGER.error(
                            f"Error deleting original file after WebM VP9 conversion: {e}"
                        )
                return output
            if code == -9:
                self._listener.is_cancelled = True
                return False
            if await aiopath.exists(output):
                await remove(output)

            # If VP9 failed, set second_retry to True to try with VP8 in the fallback code
            second_retry = True

        # If we're in second retry mode and it's a WebM conversion that failed, try with VP8
        if second_retry and ext == "webm":
            LOGGER.info(f"VP9 codec failed for {video_file}, trying with VP8")
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_file,
                "-map",
                "0:v:0",  # Take only the first video stream
                "-map",
                "0:a:0?",  # Take the first audio stream if it exists
                "-c:v",
                "libvpx",  # Use VP8 codec for video
                "-c:a",
                "libvorbis",  # Use Vorbis codec for audio
                "-b:v",
                "1M",  # Video bitrate
                "-b:a",
                "128k",  # Audio bitrate
                "-pix_fmt",
                "yuv420p",  # Pixel format
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
                "-threads",
                f"{max(1, cpu_no // 2)}",
                output,
            ]

            self._listener.subproc = await create_subprocess_exec(
                *cmd,
                stdout=PIPE,
                stderr=PIPE,
            )

            await self._ffmpeg_progress()
            _, stderr = await self._listener.subproc.communicate()
            code = self._listener.subproc.returncode

            if self._listener.is_cancelled:
                return False
            if code == 0:
                # If delete_original is True, delete the original file after successful conversion
                if (
                    delete_original
                    and await aiopath.exists(video_file)
                    and video_file != output
                ):
                    try:
                        await remove(video_file)
                        LOGGER.info(
                            f"Deleted original file after WebM VP8 conversion: {video_file}"
                        )
                    except Exception as e:
                        LOGGER.error(
                            f"Error deleting original file after WebM VP8 conversion: {e}"
                        )
                return output
            if code == -9:
                self._listener.is_cancelled = True
                return False
            if await aiopath.exists(output):
                await remove(output)

        # If all attempts failed, log the error and return False
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(
            f"{stderr}. Something went wrong while converting video, mostly file need specific codec. Path: {video_file}",
        )
        return False

    async def convert_audio(
        self, audio_file, ext, retry=False, delete_original=False
    ):
        self.clear()

        # Ensure audio_file is an absolute path
        audio_file = ospath.abspath(audio_file)

        # Check if the file exists
        if not await aiopath.exists(audio_file):
            LOGGER.error(f"Audio file does not exist: {audio_file}")
            return False

        self._total_time = (await get_media_info(audio_file))[0]

        # For settings-based configs, check if ext is None or "none" (case-insensitive)
        # This check is only for settings-based configs, not for command-line flags
        # Command-line flags are already validated before calling this function
        if not ext or ext.lower() == "none":
            LOGGER.info(
                f"Audio conversion format is empty or 'none', skipping conversion for: {audio_file}"
            )
            return audio_file

        base_name = ospath.splitext(audio_file)[0]
        output = f"{base_name}.{ext}"

        # Check if the output file already exists and is the same as input
        if output == audio_file:
            LOGGER.info(f"Output file is the same as input file: {audio_file}")
            return audio_file

        # Get custom audio settings from listener if available
        audio_codec = getattr(self._listener, "convert_audio_codec", None)
        audio_bitrate = getattr(self._listener, "convert_audio_bitrate", None)
        audio_channels = getattr(self._listener, "convert_audio_channels", None)
        audio_sampling = getattr(self._listener, "convert_audio_sampling", None)
        audio_volume = getattr(self._listener, "convert_audio_volume", None)

        # Check if custom settings are valid (not None or "none")
        has_custom_codec = audio_codec and audio_codec.lower() != "none"
        has_custom_bitrate = audio_bitrate and audio_bitrate.lower() != "none"
        has_custom_channels = audio_channels and audio_channels != 0
        has_custom_sampling = audio_sampling and audio_sampling != 0
        has_custom_volume = audio_volume and audio_volume != 0.0

        # Configure codec based on output format or custom settings
        if has_custom_codec:
            codec = ["-c:a", audio_codec]
        elif ext == "mp3":
            codec = ["-c:a", "libmp3lame", "-q:a", "2"]
        elif ext == "m4a":
            codec = ["-c:a", "aac", "-b:a", "192k"]
        elif ext == "opus":
            codec = ["-c:a", "libopus", "-b:a", "128k"]
        elif ext == "ogg":
            codec = ["-c:a", "libvorbis", "-q:a", "4"]
        elif ext == "flac":
            codec = [
                "-c:a",
                "flac",
                "-compression_level",
                "8",  # High compression level (0-12)
                "-sample_fmt",
                "s16",  # 16-bit samples
            ]
        elif ext == "wav":
            codec = ["-c:a", "pcm_s16le"]
        else:
            # Default to AAC for unknown formats
            codec = ["-c:a", "aac", "-b:a", "192k"]

        # Add custom bitrate if specified
        if has_custom_bitrate:
            # Remove any existing bitrate settings
            for i in range(len(codec) - 1):
                if codec[i] == "-b:a":
                    codec.pop(i)
                    codec.pop(i)  # Remove the value too
                    break
            codec.extend(["-b:a", audio_bitrate])

        # Add custom channels if specified
        if has_custom_channels:
            codec.extend(["-ac", str(audio_channels)])

        # Add custom sampling rate if specified
        if has_custom_sampling:
            codec.extend(["-ar", str(audio_sampling)])

        # Add custom volume if specified
        if has_custom_volume:
            codec.extend(["-filter:a", f"volume={audio_volume}"])

        if retry:
            # If we're retrying, use the codec with more options
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                audio_file,
                "-map",
                "0:a:0",  # Take only the first audio stream
                "-threads",
                f"{max(1, cpu_no // 2)}",
            ]
            cmd.extend(codec)
            cmd.append(output)
        else:
            # First try with simple copy (faster if format is compatible)
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                audio_file,
                "-c:a",
                "copy",
                "-threads",
                f"{max(1, cpu_no // 2)}",
                output,
            ]

        if self._listener.is_cancelled:
            return False

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )

        await self._ffmpeg_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if self._listener.is_cancelled:
            return False
        if code == 0:
            # If delete_original is True, delete the original file after successful conversion
            if (
                delete_original
                and await aiopath.exists(audio_file)
                and audio_file != output
            ):
                try:
                    await remove(audio_file)
                    LOGGER.info(f"Successfully deleted original file: {audio_file}")
                except Exception as e:
                    LOGGER.error(
                        f"Error deleting original file in convert_audio: {e}"
                    )
                    # Try again with a different approach
                    try:
                        import os

                        os.remove(audio_file)
                        LOGGER.info(
                            f"Successfully deleted original file using os.remove: {audio_file}"
                        )
                    except Exception as e2:
                        LOGGER.error(f"Second attempt to delete file failed: {e2}")
            return output
        if code == -9:
            self._listener.is_cancelled = True
            return False

        # If copy failed and we're not in retry mode, try with transcoding
        if not retry:
            if await aiopath.exists(output):
                await remove(output)
            LOGGER.info(
                f"Copy codec failed for {audio_file}, trying with transcoding"
            )
            return await self.convert_audio(audio_file, ext, True, delete_original)

        # If all attempts failed, log the error and return False
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(
            f"{stderr}. Something went wrong while converting audio, mostly file need specific codec. Path: {audio_file}",
        )
        if await aiopath.exists(output):
            await remove(output)
        return False

    async def convert_subtitle(self, subtitle_file, ext, delete_original=False):
        self.clear()

        # Ensure subtitle_file is an absolute path
        subtitle_file = ospath.abspath(subtitle_file)

        # Check if the file exists
        if not await aiopath.exists(subtitle_file):
            LOGGER.error(f"Subtitle file does not exist: {subtitle_file}")
            return False

        # For settings-based configs, check if ext is None or "none" (case-insensitive)
        if not ext or ext.lower() == "none":
            LOGGER.info(
                f"Subtitle conversion format is empty or 'none', skipping conversion for: {subtitle_file}"
            )
            return subtitle_file

        # Get file extension and base name
        file_ext = ospath.splitext(subtitle_file)[1].lower()
        output = f"{ospath.splitext(subtitle_file)[0]}.{ext}"

        # Get custom subtitle settings from listener if available
        subtitle_encoding = getattr(
            self._listener, "convert_subtitle_encoding", None
        )
        subtitle_language = getattr(
            self._listener, "convert_subtitle_language", None
        )

        # Check if custom settings are valid (not None or "none")
        has_custom_encoding = (
            subtitle_encoding and subtitle_encoding.lower() != "none"
        )
        has_custom_language = (
            subtitle_language and subtitle_language.lower() != "none"
        )

        # Handle subtitle conversion based on file type
        if file_ext in [".srt", ".vtt", ".ass", ".ssa", ".sub"]:
            # Determine output format
            if ext == "srt":
                # Convert to SRT format
                cmd = [
                    "xtra",  # Using xtra instead of ffmpeg
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-progress",
                    "pipe:1",
                ]

                # Add subtitle encoding if specified
                if has_custom_encoding:
                    cmd.extend(["-sub_charenc", subtitle_encoding])

                cmd.extend(
                    [
                        "-i",
                        subtitle_file,
                        "-c:s",
                        "text",  # Use text codec for SRT
                    ]
                )

                # Add subtitle language if specified
                if has_custom_language:
                    cmd.extend(["-metadata:s:s:0", f"language={subtitle_language}"])

                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}", output])
            elif ext == "vtt":
                # Convert to WebVTT format
                cmd = [
                    "xtra",  # Using xtra instead of ffmpeg
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-progress",
                    "pipe:1",
                ]

                # Add subtitle encoding if specified
                if has_custom_encoding:
                    cmd.extend(["-sub_charenc", subtitle_encoding])

                cmd.extend(
                    [
                        "-i",
                        subtitle_file,
                        "-c:s",
                        "webvtt",  # Use WebVTT codec
                    ]
                )

                # Add subtitle language if specified
                if has_custom_language:
                    cmd.extend(["-metadata:s:s:0", f"language={subtitle_language}"])

                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}", output])
            elif ext in {"ass", "ssa"}:
                # Convert to ASS/SSA format
                cmd = [
                    "xtra",  # Using xtra instead of ffmpeg
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-progress",
                    "pipe:1",
                ]

                # Add subtitle encoding if specified
                if has_custom_encoding:
                    cmd.extend(["-sub_charenc", subtitle_encoding])

                cmd.extend(
                    [
                        "-i",
                        subtitle_file,
                        "-c:s",
                        "ass",  # Use ASS codec
                    ]
                )

                # Add subtitle language if specified
                if has_custom_language:
                    cmd.extend(["-metadata:s:s:0", f"language={subtitle_language}"])

                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}", output])
            else:
                # Default conversion
                cmd = [
                    "xtra",  # Using xtra instead of ffmpeg
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-progress",
                    "pipe:1",
                ]

                # Add subtitle encoding if specified
                if has_custom_encoding:
                    cmd.extend(["-sub_charenc", subtitle_encoding])

                cmd.extend(
                    [
                        "-i",
                        subtitle_file,
                    ]
                )

                # Add subtitle language if specified
                if has_custom_language:
                    cmd.extend(["-metadata:s:s:0", f"language={subtitle_language}"])

                cmd.extend(["-threads", f"{max(1, cpu_no // 2)}", output])
        else:
            # For unknown subtitle formats, use a generic approach
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
            ]

            # Add subtitle encoding if specified
            if has_custom_encoding:
                cmd.extend(["-sub_charenc", subtitle_encoding])

            # Add input file
            cmd.extend(["-i", subtitle_file])

            # Determine output format and codec
            if ext == "srt":
                cmd.extend(["-c:s", "text"])
            elif ext in {"ass", "ssa"}:
                cmd.extend(["-c:s", "ass"])
            elif ext in {"vtt", "webvtt"}:
                cmd.extend(["-c:s", "webvtt"])
            else:
                # For other formats, let FFmpeg choose the appropriate codec
                cmd.extend(["-c:s", "copy"])

            # Add subtitle language if specified
            if has_custom_language:
                cmd.extend(["-metadata:s:s:0", f"language={subtitle_language}"])

            # Add threads and output file
            cmd.extend(["-threads", f"{max(1, cpu_no // 2)}", output])

        if self._listener.is_cancelled:
            return False

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )

        await self._ffmpeg_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if code == 0:
            if delete_original and await aiopath.exists(output):
                try:
                    await remove(subtitle_file)
                    LOGGER.info(
                        f"Successfully deleted original file: {subtitle_file}"
                    )
                except Exception as e:
                    LOGGER.error(
                        f"Error deleting original file in convert_subtitle: {e}"
                    )
                    # Try again with a different approach
                    try:
                        os.remove(subtitle_file)
                        LOGGER.info(
                            f"Successfully deleted original file using os.remove: {subtitle_file}"
                        )
                    except Exception as e2:
                        LOGGER.error(f"Second attempt to delete file failed: {e2}")
            return output
        if code == -9:
            self._listener.is_cancelled = True
            return False

        # If conversion failed, log the error and return False
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(
            f"{stderr}. Something went wrong while converting subtitle. Path: {subtitle_file}",
        )
        if await aiopath.exists(output):
            await remove(output)
        return False

    async def convert_document(self, document_file, ext, delete_original=False):
        self.clear()

        # Ensure document_file is an absolute path
        document_file = ospath.abspath(document_file)

        # Check if the file exists
        if not await aiopath.exists(document_file):
            LOGGER.error(f"Document file does not exist: {document_file}")
            return False

        # For settings-based configs, check if ext is None or "none" (case-insensitive)
        if not ext or ext.lower() == "none":
            LOGGER.info(
                f"Document conversion format is empty or 'none', skipping conversion for: {document_file}"
            )
            return document_file

        # Get base name and output path
        output = f"{ospath.splitext(document_file)[0]}.{ext}"

        # Check if the output file already exists and is the same as input
        if output == document_file:
            LOGGER.info(f"Output file is the same as input file: {document_file}")
            return document_file

        # Check if we have libreoffice or unoconv for document conversion
        import shutil

        libreoffice_path = shutil.which("libreoffice")
        unoconv_path = shutil.which("unoconv")

        if not libreoffice_path and not unoconv_path:
            LOGGER.error(
                "Neither LibreOffice nor unoconv found for document conversion"
            )
            return document_file

        # Build conversion command
        if libreoffice_path:
            # Use LibreOffice for conversion
            cmd = [
                libreoffice_path,
                "--headless",
                "--convert-to",
                ext,
                "--outdir",
                ospath.dirname(document_file),
                document_file,
            ]

            # Execute the command
            try:
                process = await create_subprocess_exec(
                    *cmd,
                    stdout=PIPE,
                    stderr=PIPE,
                )
                _, stderr = await process.communicate()
                code = process.returncode

                if code == 0:
                    # LibreOffice creates the output file with the same name but different extension
                    if await aiopath.exists(output):
                        if delete_original:
                            try:
                                await remove(document_file)
                                LOGGER.info(
                                    f"Successfully deleted original file: {document_file}"
                                )
                            except Exception as e:
                                LOGGER.error(
                                    f"Error deleting original file in convert_document: {e}"
                                )
                                # Try again with a different approach
                                try:
                                    os.remove(document_file)
                                    LOGGER.info(
                                        f"Successfully deleted original file using os.remove: {document_file}"
                                    )
                                except Exception as e2:
                                    LOGGER.error(
                                        f"Second attempt to delete file failed: {e2}"
                                    )
                        return output
                    LOGGER.error(f"Output file not found after conversion: {output}")
                    return document_file
                LOGGER.error(
                    f"LibreOffice conversion failed with code {code}: {stderr.decode()}"
                )
                return document_file
            except Exception as e:
                LOGGER.error(f"Error during LibreOffice conversion: {e}")
                return document_file
        elif unoconv_path:
            # Use unoconv for conversion
            cmd = [unoconv_path, "-f", ext, document_file]

            # Execute the command
            try:
                process = await create_subprocess_exec(
                    *cmd,
                    stdout=PIPE,
                    stderr=PIPE,
                )
                _, stderr = await process.communicate()
                code = process.returncode

                if code == 0:
                    # unoconv creates the output file with the same name but different extension
                    if await aiopath.exists(output):
                        if delete_original:
                            try:
                                await remove(document_file)
                                LOGGER.info(
                                    f"Successfully deleted original file: {document_file}"
                                )
                            except Exception as e:
                                LOGGER.error(
                                    f"Error deleting original file in convert_document: {e}"
                                )
                                # Try again with a different approach
                                try:
                                    os.remove(document_file)
                                    LOGGER.info(
                                        f"Successfully deleted original file using os.remove: {document_file}"
                                    )
                                except Exception as e2:
                                    LOGGER.error(
                                        f"Second attempt to delete file failed: {e2}"
                                    )
                        return output
                    LOGGER.error(f"Output file not found after conversion: {output}")
                    return document_file
                LOGGER.error(
                    f"unoconv conversion failed with code {code}: {stderr.decode()}"
                )
                return document_file
            except Exception as e:
                LOGGER.error(f"Error during unoconv conversion: {e}")
                return document_file

        # If we reach here, conversion failed
        return document_file

    async def convert_archive(self, archive_file, ext, delete_original=False):
        self.clear()

        # Ensure archive_file is an absolute path
        archive_file = ospath.abspath(archive_file)

        # Check if the file exists
        if not await aiopath.exists(archive_file):
            LOGGER.error(f"Archive file does not exist: {archive_file}")
            return False

        # For settings-based configs, check if ext is None or "none" (case-insensitive)
        if not ext or ext.lower() == "none":
            LOGGER.info(
                f"Archive conversion format is empty or 'none', skipping conversion for: {archive_file}"
            )
            return archive_file

        # Get output path
        output = f"{ospath.splitext(archive_file)[0]}.{ext}"

        # Check if the output file already exists and is the same as input
        if output == archive_file:
            LOGGER.info(f"Output file is the same as input file: {archive_file}")
            return archive_file

        # Get custom archive settings from listener if available
        archive_level = getattr(self._listener, "convert_archive_level", None)
        archive_method = getattr(self._listener, "convert_archive_method", None)

        # Check if we have 7z for archive conversion
        import shutil

        sevenzip_path = shutil.which("7z")

        if not sevenzip_path:
            LOGGER.error("7z not found for archive conversion")
            return archive_file

        # Create a temporary directory for extraction
        temp_dir = f"{ospath.splitext(archive_file)[0]}_temp"
        await makedirs(temp_dir, exist_ok=True)

        try:
            # Step 1: Extract the archive to the temporary directory
            extract_cmd = [
                sevenzip_path,
                "x",  # Extract with full paths
                "-y",  # Yes to all prompts
                f"-o{temp_dir}",  # Output directory
                archive_file,
            ]

            extract_process = await create_subprocess_exec(
                *extract_cmd,
                stdout=PIPE,
                stderr=PIPE,
            )
            _, stderr = await extract_process.communicate()
            extract_code = extract_process.returncode

            if extract_code != 0:
                LOGGER.error(f"Failed to extract archive: {stderr.decode()}")
                # Clean up temp directory
                await rmtree(temp_dir, ignore_errors=True)
                return archive_file

            # Step 2: Create a new archive in the desired format
            archive_cmd = [
                sevenzip_path,
                "a",  # Add to archive
                "-y",  # Yes to all prompts
            ]

            # Add compression level if specified
            if archive_level and archive_level.isdigit():
                archive_cmd.append(f"-mx={archive_level}")
            else:
                archive_cmd.append("-mx=5")  # Default compression level

            # Add compression method if specified
            if archive_method and archive_method.lower() != "none":
                archive_cmd.append(f"-m0={archive_method}")

            # Add output file and input directory
            archive_cmd.extend([output, f"{temp_dir}/*"])

            archive_process = await create_subprocess_exec(
                *archive_cmd,
                stdout=PIPE,
                stderr=PIPE,
            )
            _, stderr = await archive_process.communicate()
            archive_code = archive_process.returncode

            # Clean up temp directory
            await rmtree(temp_dir, ignore_errors=True)

            if archive_code != 0:
                LOGGER.error(f"Failed to create new archive: {stderr.decode()}")
                return archive_file

            # If successful and delete_original is True, delete the original file
            if delete_original and await aiopath.exists(output):
                try:
                    await remove(archive_file)
                    LOGGER.info(
                        f"Successfully deleted original file: {archive_file}"
                    )
                except Exception as e:
                    LOGGER.error(
                        f"Error deleting original file in convert_archive: {e}"
                    )
                    # Try again with a different approach
                    try:
                        import os

                        os.remove(archive_file)
                        LOGGER.info(
                            f"Successfully deleted original file using os.remove: {archive_file}"
                        )
                    except Exception as e2:
                        LOGGER.error(f"Second attempt to delete file failed: {e2}")

            return output

        except Exception as e:
            LOGGER.error(f"Error during archive conversion: {e}")
            # Clean up temp directory
            await rmtree(temp_dir, ignore_errors=True)
            return archive_file

    async def sample_video(self, video_file, sample_duration, part_duration):
        self.clear()
        self._total_time = sample_duration
        dir, name = video_file.rsplit("/", 1)
        output_file = f"{dir}/SAMPLE.{name}"
        segments = [(0, part_duration)]
        duration = (await get_media_info(video_file))[0]
        remaining_duration = duration - (part_duration * 2)
        parts = (sample_duration - (part_duration * 2)) // part_duration
        time_interval = remaining_duration // parts
        next_segment = time_interval
        for _ in range(parts):
            segments.append((next_segment, next_segment + part_duration))
            next_segment += time_interval
        segments.append((duration - part_duration, duration))

        filter_complex = ""
        for i, (start, end) in enumerate(segments):
            filter_complex += (
                f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]; "
            )
            filter_complex += (
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]; "
            )

        for i in range(len(segments)):
            filter_complex += f"[v{i}][a{i}]"

        filter_complex += f"concat=n={len(segments)}:v=1:a=1[vout][aout]"

        cmd = [
            "xtra",  # Using xtra instead of ffmpeg
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            "-i",
            video_file,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
        ]

        # Add format-specific optimizations for Telegram compatibility
        # Check output file format for optimization
        output_ext = os.path.splitext(output_file)[1].lower()
        if output_ext == ".mp4":
            cmd.extend(
                [
                    "-movflags",
                    "+faststart",  # Streaming optimization
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-profile:v",
                    "main",  # Compatible H.264 profile
                    "-level",
                    "4.0",  # Compatible H.264 level
                ]
            )
        elif output_ext == ".mkv":
            cmd.extend(
                [
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-disposition:v:0",
                    "default",  # Set video as default
                    "-disposition:a:0",
                    "default",  # Set audio as default
                ]
            )
        elif output_ext == ".webm":
            cmd.extend(
                [
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-deadline",
                    "good",  # VP9 optimization
                    "-cpu-used",
                    "2",  # VP9 speed/quality balance
                    "-row-mt",
                    "1",  # VP9 multithreading
                ]
            )
        elif output_ext == ".mov":
            cmd.extend(
                [
                    "-movflags",
                    "+faststart",  # Streaming optimization (MOV uses same structure as MP4)
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-profile:v",
                    "main",  # Compatible H.264 profile
                    "-level",
                    "4.0",  # Compatible H.264 level
                ]
            )
        else:
            # Universal compatibility for other formats
            cmd.extend(["-pix_fmt", "yuv420p"])

        cmd.extend(
            [
                "-threads",
                f"{max(1, cpu_no // 2)}",
                output_file,
            ]
        )

        if self._listener.is_cancelled:
            return False

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )

        await self._ffmpeg_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if self._listener.is_cancelled:
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        if code == 0:
            return output_file
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(
            f"{stderr}. Something went wrong while creating sample video, mostly file is corrupted. Path: {video_file}",
        )
        if await aiopath.exists(output_file):
            await remove(output_file)
        return False

    async def split(self, f_path, file_, parts, split_size):
        self.clear()
        multi_streams = True
        self._total_time = duration = (await get_media_info(f_path))[0]
        base_name, extension = ospath.splitext(file_)

        # Check if equal splits is enabled - ONLY use the explicit setting from proceed_split
        # Do NOT use heuristics as they can be wrong
        is_equal_splits = (
            hasattr(self._listener, "equal_splits_enabled")
            and self._listener.equal_splits_enabled
        )

        # For equal splits, calculate the exact duration for each part
        if is_equal_splits and duration > 0:
            # Calculate duration per part (in seconds)
            duration_per_part = duration / parts
            # Reserve some buffer for each part (3 seconds)
            duration_per_part -= 3

            # Process each part with exact duration
            for i in range(1, parts + 1):
                start_time = (i - 1) * (duration_per_part + 3)
                # For the last part, use the remaining duration
                end_time = duration if i == parts else i * (duration_per_part + 3)

                out_path = f_path.replace(
                    file_, f"{base_name}.part{i:03}{extension}"
                )

                # Use duration parameter instead of file size for equal splits
                cmd = [
                    "xtra",  # Using xtra instead of ffmpeg
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-progress",
                    "pipe:1",
                    "-ss",
                    str(start_time),
                    "-i",
                    f_path,
                    "-to",
                    str(end_time - start_time),  # Duration of this segment
                    "-map",
                    "0",
                    "-map_chapters",
                    "-1",
                    "-async",
                    "1",
                    "-strict",
                    "-2",
                    "-c",
                    "copy",
                ]

                # Add format-specific optimizations for Telegram compatibility
                # When using -c copy, we can only add container-level options, not encoding options
                out_ext = os.path.splitext(out_path)[1].lower()
                if out_ext == ".mp4":
                    cmd.extend(
                        [
                            "-movflags",
                            "+faststart",  # Streaming optimization
                        ]
                    )
                elif out_ext == ".mkv":
                    cmd.extend(
                        [
                            "-disposition:v:0",
                            "default",  # Set video as default
                            "-disposition:a:0",
                            "default",  # Set audio as default
                        ]
                    )
                elif out_ext == ".mov":
                    cmd.extend(
                        [
                            "-movflags",
                            "+faststart",  # Streaming optimization (MOV uses same structure as MP4)
                        ]
                    )
                # For other formats (.webm, etc.) and when using -c copy, no additional options needed

                cmd.extend(
                    [
                        "-threads",
                        f"{max(1, cpu_no // 2)}",
                        out_path,
                    ]
                )

                # Process this part
                if self._listener.is_cancelled:
                    return False

                # Execute the command
                self._listener.subproc = await create_subprocess_exec(
                    *cmd,
                    stdout=PIPE,
                    stderr=PIPE,
                )

                await self._ffmpeg_progress()
                _, stderr = await self._listener.subproc.communicate()
                code = self._listener.subproc.returncode

                if self._listener.is_cancelled:
                    return False
                if code == -9:
                    self._listener.is_cancelled = True
                    return False
                if code != 0:
                    try:
                        stderr = stderr.decode().strip()
                    except Exception:
                        stderr = "Unable to decode the error!"
                    with contextlib.suppress(Exception):
                        await remove(out_path)
                    continue

                # Update progress
                self._last_processed_time += end_time - start_time
                self._last_processed_bytes += await get_path_size(out_path)

            return True

        # Use traditional file size-based splitting (Old Aeon-MLTB proven approach)
        # Apply the proven 3MB buffer from old implementation
        split_size -= 3000000
        start_time = 0
        i = 1
        while i <= parts or start_time < duration - 4:
            out_path = f_path.replace(file_, f"{base_name}.part{i:03}{extension}")
            cmd = [
                "xtra",  # Using xtra instead of ffmpeg
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-ss",
                str(start_time),
                "-i",
                f_path,
                "-fs",
                str(split_size),
                "-map",
                "0",
                "-map_chapters",
                "-1",
                "-async",
                "1",
                "-strict",
                "-2",
                "-c",
                "copy",
                "-threads",
                f"{max(1, cpu_no // 2)}",
                out_path,
            ]
            if not multi_streams:
                # Remove the mapping arguments (2 entries) - same as old implementation
                del cmd[12]
                del cmd[12]
            if self._listener.is_cancelled:
                return False

            # Execute the command
            self._listener.subproc = await create_subprocess_exec(
                *cmd,
                stdout=PIPE,
                stderr=PIPE,
            )

            await self._ffmpeg_progress()
            _, stderr = await self._listener.subproc.communicate()
            code = self._listener.subproc.returncode
            if self._listener.is_cancelled:
                return False
            if code == -9:
                self._listener.is_cancelled = True
                return False
            if code != 0:
                try:
                    stderr = stderr.decode().strip()
                except Exception:
                    stderr = "Unable to decode the error!"
                with contextlib.suppress(Exception):
                    await remove(out_path)
                if multi_streams:
                    LOGGER.warning(
                        f"{stderr}. Retrying without map, -map 0 not working in all situations. Path: {f_path}",
                    )
                    multi_streams = False
                    continue
                LOGGER.warning(
                    f"{stderr}. Unable to split this video, if it's size less than {self._listener.max_split_size} will be uploaded as it is. Path: {f_path}",
                )
                return False
            out_size = await aiopath.getsize(out_path)
            if out_size > self._listener.max_split_size:
                split_size -= (out_size - self._listener.max_split_size) + 5000000
                LOGGER.warning(
                    f"Part size is {out_size}. Trying again with lower split size!. Path: {f_path}",
                )
                await remove(out_path)
                continue
            lpd = (await get_media_info(out_path))[0]
            if lpd == 0:
                LOGGER.error(
                    f"Something went wrong while splitting, mostly file is corrupted. Path: {f_path}",
                )
                break
            if duration == lpd:
                LOGGER.warning(
                    f"This file has been splitted with default stream and audio, so you will only see one part with less size from orginal one because it doesn't have all streams and audios. This happens mostly with MKV videos. Path: {f_path}",
                )
                break
            if lpd <= 3:
                await remove(out_path)
                break
            self._last_processed_time += lpd
            self._last_processed_bytes += out_size
            start_time += lpd - 3
            i += 1

        return True


async def apply_document_metadata(file_path, title=None, author=None, comment=None):
    """Apply metadata to document files like PDF using appropriate tools with template variable support.

    Args:
        file_path: Path to the document file
        title: Title metadata to apply (supports template variables)
        author: Author metadata to apply (supports template variables)
        comment: Comment metadata to apply (supports template variables)

    Returns:
        bool: True if metadata was successfully applied, False otherwise
    """
    if not file_path or not await aiopath.exists(file_path):
        LOGGER.error(f"File not found: {file_path}")
        return False

    # Process template variables in metadata values
    from bot.helper.ext_utils.template_processor import (
        extract_metadata_from_filename,
    )

    # Extract file metadata for template variables
    filename_without_ext = os.path.splitext(os.path.basename(file_path))[0]
    file_metadata = await extract_metadata_from_filename(filename_without_ext)

    # Add basic file information to metadata
    file_metadata.update(
        {
            "filename": filename_without_ext,
            "ext": (
                os.path.splitext(file_path)[1][1:]
                if os.path.splitext(file_path)[1]
                else ""
            ),
            "filepath": file_path,
            "basename": os.path.basename(file_path),
        }
    )

    # Add additional template variables for comprehensive support
    try:
        import hashlib
        import os

        # Get file size
        try:
            file_size = os.path.getsize(file_path)
            if file_size >= 1024**3:  # GB
                size_str = f"{file_size / (1024**3):.2f}GB"
            elif file_size >= 1024**2:  # MB
                size_str = f"{file_size / (1024**2):.2f}MB"
            elif file_size >= 1024:  # KB
                size_str = f"{file_size / 1024:.2f}KB"
            else:
                size_str = f"{file_size}B"
            file_metadata["size"] = size_str
        except:
            file_metadata["size"] = "Unknown"

        # Get MD5 hash (first 8 characters for performance)
        try:
            with open(file_path, "rb") as f:
                file_hash = hashlib.md5(f.read(8192)).hexdigest()[
                    :8
                ]  # Quick hash of first 8KB
            file_metadata["md5_hash"] = file_hash
            file_metadata["id"] = file_hash
        except:
            file_metadata["md5_hash"] = "Unknown"
            file_metadata["id"] = "Unknown"

        # Get media information if it's a media file
        try:
            duration, _artist, title = await get_media_info(file_path)
            if duration and duration > 0:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                seconds = duration % 60
                if hours > 0:
                    duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    duration_str = f"{minutes:02d}:{seconds:02d}"
                file_metadata["duration"] = duration_str
            else:
                file_metadata["duration"] = ""
        except:
            file_metadata["duration"] = ""

        # Set default values for media-specific variables
        file_metadata.update(
            {
                "audios": "",
                "audio_codecs": "",
                "subtitles": "",
                "NumVideos": "00",
                "NumAudios": "00",
                "NumSubtitles": "00",
                "formate": file_metadata["ext"].upper()
                if file_metadata["ext"]
                else "",
                "format": "Unknown",
            }
        )

    except Exception as e:
        LOGGER.warning(f"Error extracting additional metadata for {file_path}: {e}")
        # Set default values if extraction fails
        file_metadata.update(
            {
                "size": "Unknown",
                "duration": "",
                "audios": "",
                "audio_codecs": "",
                "subtitles": "",
                "md5_hash": "Unknown",
                "NumVideos": "00",
                "NumAudios": "00",
                "NumSubtitles": "00",
                "formate": file_metadata["ext"].upper()
                if file_metadata["ext"]
                else "",
                "format": "Unknown",
                "id": "Unknown",
            }
        )

    # Process template variables in metadata fields (simple substitution only)
    async def process_metadata_template(template_value):
        """Process template variables in metadata values - simple substitution only"""
        if not template_value:
            return template_value
        try:
            result = str(template_value)
            # Simple template variable substitution using {variable} format
            for key, value in file_metadata.items():
                if value is not None:
                    result = result.replace(f"{{{key}}}", str(value))
            return result
        except Exception as e:
            LOGGER.warning(
                f"Error processing metadata template '{template_value}': {e}"
            )
            return str(
                template_value
            )  # Return original value if template processing fails

    # Process all metadata values through template processor
    if title:
        title = await process_metadata_template(title)
    if author:
        author = await process_metadata_template(author)
    if comment:
        comment = await process_metadata_template(comment)

    # Skip if no metadata to apply after processing
    if not title and not author and not comment:
        return True

    # Get file extension
    ext = os.path.splitext(file_path)[1].lower()

    # Create a temporary file for output
    temp_file = f"{file_path}.temp{ext}"

    # Handle different document types
    if ext == ".pdf":
        return await apply_pdf_metadata(file_path, temp_file, title, author, comment)
    if ext in [".epub", ".mobi", ".azw", ".azw3"]:
        return await apply_ebook_metadata(
            file_path, temp_file, title, author, comment
        )
    if ext in [
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
    ]:
        return await apply_office_metadata(
            file_path, temp_file, title, author, comment
        )
    if ext in [".txt", ".md", ".csv", ".rtf"]:
        return await apply_text_metadata(
            file_path, temp_file, title, author, comment
        )
    # Try exiftool for other document types
    return await apply_exiftool_metadata(
        file_path, temp_file, title, author, comment
    )


async def apply_pdf_metadata(
    file_path, temp_file, title=None, author=None, comment=None
):
    """Apply metadata to PDF files using PyMuPDF or exiftool.

    Args:
        file_path: Path to the PDF file
        temp_file: Path to the temporary file
        title: Title metadata to apply
        author: Author metadata to apply
        comment: Comment metadata to apply

    Returns:
        bool: True if metadata was successfully applied, False otherwise
    """
    try:
        # Try using PyMuPDF first for better performance and reliability
        try:
            LOGGER.info(f"Using PyMuPDF to apply metadata to {file_path}")

            # Open the PDF document
            doc = fitz.open(file_path)

            # Get current metadata
            metadata = doc.metadata

            # Update metadata with new values
            if title:
                metadata["title"] = title
            if author:
                metadata["author"] = author
            if comment:
                metadata["subject"] = comment

            # Set the updated metadata
            doc.set_metadata(metadata)

            # Save to temporary file
            doc.save(temp_file)
            doc.close()

            # Replace original file with updated file
            if await aiopath.exists(temp_file):
                os.replace(temp_file, file_path)
                LOGGER.info("Successfully applied PDF metadata using PyMuPDF")
                return True

            LOGGER.error(f"Failed to save PDF with metadata: {temp_file}")
            return False

        except Exception as pymupdf_error:
            LOGGER.warning(f"PyMuPDF metadata application failed: {pymupdf_error}")
            # Fall back to exiftool
            return await apply_exiftool_metadata(
                file_path, temp_file, title, author, comment
            )

    except Exception as e:
        LOGGER.error(f"Error applying PDF metadata: {e}")
        # Fall back to exiftool
        return await apply_exiftool_metadata(
            file_path, temp_file, title, author, comment
        )


async def apply_ebook_metadata(
    file_path, temp_file, title=None, author=None, comment=None
):
    """Apply metadata to ebook files using ebook-meta or exiftool.

    Args:
        file_path: Path to the ebook file
        temp_file: Path to the temporary file
        title: Title metadata to apply
        author: Author metadata to apply
        comment: Comment metadata to apply

    Returns:
        bool: True if metadata was successfully applied, False otherwise
    """
    try:
        # Check if ebook-meta (from Calibre) is available
        ebook_meta_check = await cmd_exec(["which", "ebook-meta"])

        if ebook_meta_check[0]:  # ebook-meta is available
            LOGGER.info(f"Using ebook-meta to apply metadata to {file_path}")

            # Create a copy of the file first
            shutil.copy2(file_path, temp_file)

            # Build the command
            cmd = ["ebook-meta", temp_file]
            if title:
                cmd.extend(["--title", title])
            if author:
                cmd.extend(["--author", author])
            if comment:
                cmd.extend(["--comments", comment])

            result = await cmd_exec(cmd)

            if result[2] == 0:
                os.replace(temp_file, file_path)
                return True
            if await aiopath.exists(temp_file):
                await remove(temp_file)
            LOGGER.error(f"ebook-meta failed: {result[1]}")
            # Fall back to exiftool
            return await apply_exiftool_metadata(
                file_path, temp_file, title, author, comment
            )
        # Fall back to exiftool
        return await apply_exiftool_metadata(
            file_path, temp_file, title, author, comment
        )

    except Exception as e:
        LOGGER.error(f"Error applying ebook metadata: {e}")
        # Fall back to exiftool
        return await apply_exiftool_metadata(
            file_path, temp_file, title, author, comment
        )


async def apply_office_metadata(
    file_path, temp_file, title=None, author=None, comment=None
):
    """Apply metadata to office document files.

    Args:
        file_path: Path to the office document file
        temp_file: Path to the temporary file
        title: Title metadata to apply
        author: Author metadata to apply
        comment: Comment metadata to apply

    Returns:
        bool: True if metadata was successfully applied, False otherwise
    """
    # For office documents, use exiftool
    return await apply_exiftool_metadata(
        file_path, temp_file, title, author, comment
    )


async def apply_text_metadata(
    file_path, temp_file, title=None, author=None, comment=None
):
    """Apply metadata to text files by adding comments at the top.

    Args:
        file_path: Path to the text file
        temp_file: Path to the temporary file
        title: Title metadata to apply
        author: Author metadata to apply
        comment: Comment metadata to apply

    Returns:
        bool: True if metadata was successfully applied, False otherwise
    """
    try:
        # For text files, we can add metadata as comments at the top of the file
        with open(file_path, encoding="utf-8", errors="ignore") as f_in:
            content = f_in.read()

        with open(temp_file, "w", encoding="utf-8") as f_out:
            # Add metadata as comments
            if title or author or comment:
                f_out.write("/*\n")
                if title:
                    f_out.write(f"Title: {title}\n")
                if author:
                    f_out.write(f"Author: {author}\n")
                if comment:
                    f_out.write(f"Comment: {comment}\n")
                f_out.write("*/\n\n")

            # Write the original content
            f_out.write(content)

        # Replace the original file
        os.replace(temp_file, file_path)
        return True

    except Exception as e:
        LOGGER.error(f"Error applying text metadata: {e}")
        return False


async def apply_exiftool_metadata(
    file_path, temp_file, title=None, author=None, comment=None
):
    """Apply metadata to files using exiftool.

    Args:
        file_path: Path to the file
        temp_file: Path to the temporary file
        title: Title metadata to apply
        author: Author metadata to apply
        comment: Comment metadata to apply

    Returns:
        bool: True if metadata was successfully applied, False otherwise
    """
    try:
        # Check if exiftool is available
        exiftool_check = await cmd_exec(["which", "exiftool"])

        if exiftool_check[0]:  # exiftool is available
            LOGGER.info(f"Using exiftool to apply metadata to {file_path}")

            cmd = ["exiftool"]
            if title:
                cmd.extend(["-Title=" + title])
            if author:
                cmd.extend(["-Author=" + author, "-Creator=" + author])
            if comment:
                cmd.extend(["-Subject=" + comment, "-Description=" + comment])

            # Add output file
            cmd.extend(["-o", temp_file, file_path])

            result = await cmd_exec(cmd)

            if result[2] == 0 and await aiopath.exists(temp_file):
                os.replace(temp_file, file_path)
                return True
            if await aiopath.exists(temp_file):
                await remove(temp_file)
            LOGGER.error(f"exiftool failed: {result[1]}")
            return False
        return False

    except Exception as e:
        LOGGER.error(f"Error applying metadata with exiftool: {e}")
        return False


async def merge_pdfs(files, output_filename="merged.pdf"):
    """
    Merge multiple PDF files into a single PDF.

    Args:
        files: List of PDF file paths
        output_filename: Name of the output PDF file

    Returns:
        str: Path to the merged PDF file
    """
    if not files:
        LOGGER.error("No PDF files provided for merging")
        return None

    try:
        # Use files in the order they were provided
        # (No sorting to preserve user's intended order)

        # Create a new PDF document for the merged output
        merged_doc = fitz.open()

        # Add each PDF to the merged document with error handling
        valid_pdfs = 0
        for pdf in files:
            try:
                # Open the PDF document
                doc = fitz.open(pdf)

                # Check if the PDF is password-protected
                if doc.needs_pass:
                    LOGGER.warning(f"Skipping password-protected PDF: {pdf}")
                    doc.close()
                    continue

                # Insert all pages from this PDF
                merged_doc.insert_pdf(doc)
                doc.close()
                valid_pdfs += 1

            except Exception as pdf_error:
                LOGGER.error(f"Error processing PDF {pdf}: {pdf_error}")
                continue

        if valid_pdfs == 0:
            LOGGER.error("No valid PDFs found for merging")
            merged_doc.close()
            return None

        # Determine output path
        base_dir = os.path.dirname(files[0])
        output_file = os.path.join(base_dir, output_filename)

        # Save the merged PDF
        merged_doc.save(output_file)
        merged_doc.close()

        LOGGER.info(f"Successfully merged {valid_pdfs} PDFs into {output_file}")

        # Force garbage collection after PDF merging
        # This can create large objects in memory
        if smart_garbage_collection:
            smart_garbage_collection(aggressive=True)
        else:
            gc.collect()

        return output_file

    except Exception as e:
        LOGGER.error(f"Error merging PDFs: {e}")
        return None


async def create_pdf_from_images(
    image_files, output_file="merged.pdf", page_size=None
):
    """
    Create a PDF from multiple image files.

    Args:
        image_files: List of image file paths
        output_file: Path to the output PDF file
        page_size: Size of the PDF pages (default: letter size)

    Returns:
        str: Path to the created PDF file
    """
    # Default to letter size if not specified
    if page_size is None:
        page_size = (612, 792)  # Standard letter size
    if not image_files:
        LOGGER.error("No image files provided for PDF creation")
        return None

    # Apply memory limits for PIL operations
    limit_memory_for_pil()

    try:
        # Use files in the order they were provided
        # (No sorting to preserve user's intended order)

        # Create a new PDF document
        doc = fitz.open()

        # Process each image
        valid_images = 0
        for img_path in image_files:
            try:
                # Try to open as an image
                img = Image.open(img_path)

                # Convert to RGB if needed (handle more color modes)
                if img.mode == "RGBA":
                    # Create white background for transparent images
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(
                        img, mask=img.split()[3]
                    )  # Use alpha channel as mask
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Convert PIL image to bytes
                import io

                img_bytes = io.BytesIO()
                img.save(img_bytes, format="JPEG", quality=95)
                img_bytes.seek(0)

                # Create a new page with appropriate size
                # Calculate page size based on image dimensions and DPI
                img_width, img_height = img.size
                # Use 72 DPI as default for PDF (standard)
                page_width = img_width * 72 / 300  # Assuming 300 DPI source
                page_height = img_height * 72 / 300

                # Create page with calculated dimensions
                page = doc.new_page(width=page_width, height=page_height)
                img_rect = page.rect
                page.insert_image(img_rect, stream=img_bytes.getvalue())

                valid_images += 1

            except Exception as e:
                LOGGER.error(f"Error processing image {img_path}: {e}")
                continue

        if valid_images == 0:
            LOGGER.error("No valid images could be processed for PDF creation")
            doc.close()
            return None

        # Save the output PDF
        doc.save(output_file)
        doc.close()

        LOGGER.info(
            f"Successfully created PDF with {valid_images} images: {output_file}"
        )
        return output_file

    except Exception as e:
        LOGGER.error(f"Error creating PDF from images: {e}")
        return None


async def merge_images(
    files, output_format="jpg", mode="collage", columns=None, quality=85, dpi=None
):
    """
    Merge multiple image files into a single image.

    Args:
        files: List of image file paths
        output_format: Output format (jpg, png, etc.)
                      If "none", will use the format of the first input file
        mode: 'collage' or 'vertical' or 'horizontal'
        columns: Number of columns for collage mode (auto-calculated if None or "none")
        quality: Output image quality (1-100, only for jpg)
        dpi: DPI for the output image (only used for certain formats)

    Returns:
        str: Path to the merged image file
    """
    if not files:
        LOGGER.error("No image files provided for merging")
        return None

    # Handle "none" output format by using the format of the first input file
    if output_format == "none" and files:
        # Extract extension from the first file
        first_file_ext = os.path.splitext(files[0])[1].lower().lstrip(".")
        if first_file_ext in ["jpg", "jpeg", "png", "gif", "webp", "bmp"]:
            # Use the extension if it's a valid image format
            output_format = "jpg" if first_file_ext == "jpeg" else first_file_ext
        else:
            # Default to jpg if not a recognized image format
            output_format = "jpg"

    # Handle "none" or string values for numeric parameters
    if columns == "none" or columns is None:
        columns = None  # Will be auto-calculated based on number of images

    # Convert quality to int if it's a string or "none"
    if quality == "none" or quality is None:
        quality = 85  # Default quality
    elif isinstance(quality, str):
        try:
            quality = int(quality)
        except ValueError:
            quality = 85  # Default if conversion fails

    # Handle DPI parameter
    if dpi == "none" or dpi is None:
        dpi = 300  # Default DPI
    elif isinstance(dpi, str):
        try:
            dpi = int(dpi)
        except ValueError:
            dpi = 300  # Default if conversion fails

    # Apply memory limits for PIL operations
    limit_memory_for_pil()

    try:
        # Filter valid image files
        valid_files = []
        for f in files:
            if os.path.exists(f) and os.path.getsize(f) > 0:
                valid_files.append(f)
            else:
                pass

        if not valid_files:
            LOGGER.error("No valid image files found for merging")
            return None

        # Normalize output format
        output_format = output_format.lower().strip(".")
        if output_format not in ["jpg", "jpeg", "png", "webp", "tiff", "bmp", "gif"]:
            output_format = "jpg"

        # Determine base directory for output
        base_dir = os.path.dirname(valid_files[0])
        output_file = os.path.join(base_dir, f"merged.{int(time())}.{output_format}")

        # Open all valid images
        images = []
        for f in valid_files:
            try:
                # Skip the merged output file if it exists in the input list
                if os.path.basename(f) == f"merged.{output_format}":
                    LOGGER.info(f"Skipping previous merged output file: {f}")
                    continue

                # Skip any extremely large images (potential memory issues)
                file_size = os.path.getsize(f)
                if file_size > 50 * 1024 * 1024:  # 50 MB limit
                    continue

                img = Image.open(f)

                # Skip images with extreme dimensions
                if img.width > 5000 or img.height > 5000:
                    continue

                # Convert to RGB if needed (handle more color modes)
                if img.mode == "RGBA" and output_format.lower() in ["jpg", "jpeg"]:
                    # Create white background for transparent images
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(
                        img, mask=img.split()[3]
                    )  # Use alpha channel as mask
                    img = background
                elif img.mode != "RGB" and output_format.lower() in ["jpg", "jpeg"]:
                    img = img.convert("RGB")

                images.append(img)
            except Exception as e:
                LOGGER.error(f"Error opening image {f}: {e}")
                # Skip invalid images
                continue

        if not images:
            LOGGER.error("No valid images found for merging")
            return None

        # Determine merge mode
        if mode not in ["collage", "vertical", "horizontal"]:
            mode = "collage"

        # For collage mode, determine number of columns
        if mode == "collage":
            if columns is None:
                # Auto-calculate columns based on number of images
                if len(images) <= 2:
                    columns = 1
                elif len(images) <= 6:
                    columns = 2
                elif len(images) <= 12:
                    columns = 3
                else:
                    columns = 4

            columns = max(1, min(columns, len(images)))  # Ensure valid column count
            rows = (len(images) + columns - 1) // columns  # Ceiling division

            # Find the average dimensions for better proportions
            avg_width = sum(img.width for img in images) // len(images)
            avg_height = sum(img.height for img in images) // len(images)

            # Decide on cell dimensions - can use average or maximum
            # Using average dimensions with a margin for better aesthetics
            cell_width = int(avg_width * 1.1)  # 10% margin
            cell_height = int(avg_height * 1.1)  # 10% margin

            # Check if the total dimensions would be too large
            MAX_DIMENSION = 10000  # Maximum dimension in pixels
            total_width = cell_width * columns
            total_height = cell_height * rows

            if total_width > MAX_DIMENSION or total_height > MAX_DIMENSION:
                # Scale down to fit within limits
                scale_factor = min(
                    MAX_DIMENSION / total_width, MAX_DIMENSION / total_height
                )
                cell_width = int(cell_width * scale_factor)
                cell_height = int(cell_height * scale_factor)
                total_width = cell_width * columns
                total_height = cell_height * rows

            # Create a new image with the calculated dimensions
            if output_format.lower() in ["jpg", "jpeg"]:
                merged_image = Image.new(
                    "RGB", (total_width, total_height), (255, 255, 255)
                )
            else:
                merged_image = Image.new(
                    "RGBA", (total_width, total_height), (255, 255, 255, 0)
                )

            # Paste each image into the grid
            for i, img in enumerate(images):
                if i >= rows * columns:  # Skip if we've filled all cells
                    break

                row = i // columns
                col = i % columns

                # Calculate position
                x = col * cell_width
                y = row * cell_height

                # Resize image to fit cell (preserving aspect ratio)
                img_aspect = img.width / img.height
                cell_aspect = cell_width / cell_height

                if img_aspect > cell_aspect:  # Image is wider than cell
                    new_width = cell_width
                    new_height = int(cell_width / img_aspect)
                else:  # Image is taller than cell
                    new_height = cell_height
                    new_width = int(cell_height * img_aspect)

                # Resize with high quality
                resized_img = img.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )

                # Center in cell
                paste_x = x + (cell_width - new_width) // 2
                paste_y = y + (cell_height - new_height) // 2

                # Paste the image
                if resized_img.mode == "RGBA" and merged_image.mode == "RGB":
                    # Handle transparency for RGB output
                    background = Image.new("RGB", resized_img.size, (255, 255, 255))
                    background.paste(
                        resized_img, mask=resized_img.split()[3]
                    )  # Use alpha channel as mask
                    merged_image.paste(background, (paste_x, paste_y))
                else:
                    # Direct paste for compatible modes
                    merged_image.paste(resized_img, (paste_x, paste_y))

        elif mode == "vertical":
            # Stack images vertically
            total_width = max(img.width for img in images)
            total_height = sum(img.height for img in images)

            # Check if the total dimensions would be too large
            MAX_DIMENSION = 10000  # Maximum dimension in pixels
            if total_height > MAX_DIMENSION:
                # Scale down to fit within limits
                scale_factor = MAX_DIMENSION / total_height
                total_width = int(total_width * scale_factor)
                total_height = MAX_DIMENSION

                # Resize all images proportionally
                scaled_images = []
                for img in images:
                    new_width = int(img.width * scale_factor)
                    new_height = int(img.height * scale_factor)
                    scaled_img = img.resize(
                        (new_width, new_height), Image.Resampling.LANCZOS
                    )
                    scaled_images.append(scaled_img)
                images = scaled_images

            # Create a new image
            if output_format.lower() in ["jpg", "jpeg"]:
                merged_image = Image.new(
                    "RGB", (total_width, total_height), (255, 255, 255)
                )
            else:
                merged_image = Image.new(
                    "RGBA", (total_width, total_height), (255, 255, 255, 0)
                )

            # Paste each image
            y_offset = 0
            for img in images:
                # Center horizontally
                x_offset = (total_width - img.width) // 2

                # Paste the image
                if img.mode == "RGBA" and merged_image.mode == "RGB":
                    # Handle transparency for RGB output
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(
                        img, mask=img.split()[3]
                    )  # Use alpha channel as mask
                    merged_image.paste(background, (x_offset, y_offset))
                else:
                    # Direct paste for compatible modes
                    merged_image.paste(img, (x_offset, y_offset))

                y_offset += img.height

        elif mode == "horizontal":
            # Place images side by side
            total_width = sum(img.width for img in images)
            total_height = max(img.height for img in images)

            # Check if the total dimensions would be too large
            MAX_DIMENSION = 10000  # Maximum dimension in pixels
            if total_width > MAX_DIMENSION:
                # Scale down to fit within limits
                scale_factor = MAX_DIMENSION / total_width
                total_width = MAX_DIMENSION
                total_height = int(total_height * scale_factor)

                # Resize all images proportionally
                scaled_images = []
                for img in images:
                    new_width = int(img.width * scale_factor)
                    new_height = int(img.height * scale_factor)
                    scaled_img = img.resize(
                        (new_width, new_height), Image.Resampling.LANCZOS
                    )
                    scaled_images.append(scaled_img)
                images = scaled_images

            # Create a new image
            if output_format.lower() in ["jpg", "jpeg"]:
                merged_image = Image.new(
                    "RGB", (total_width, total_height), (255, 255, 255)
                )
            else:
                merged_image = Image.new(
                    "RGBA", (total_width, total_height), (255, 255, 255, 0)
                )

            # Paste each image
            x_offset = 0
            for img in images:
                # Center vertically
                y_offset = (total_height - img.height) // 2

                # Paste the image
                if img.mode == "RGBA" and merged_image.mode == "RGB":
                    # Handle transparency for RGB output
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(
                        img, mask=img.split()[3]
                    )  # Use alpha channel as mask
                    merged_image.paste(background, (x_offset, y_offset))
                else:
                    # Direct paste for compatible modes
                    merged_image.paste(img, (x_offset, y_offset))

                x_offset += img.width

        # Save the merged image with appropriate parameters
        save_kwargs = {}

        # Handle quality parameter for formats that support it
        supports_quality = output_format.lower() in ["jpg", "jpeg", "webp"]
        if supports_quality and quality is not None:
            try:
                quality_value = int(quality) if isinstance(quality, str) else quality
                quality_value = max(1, min(100, quality_value))  # Ensure valid range
                save_kwargs["quality"] = quality_value
            except (ValueError, TypeError):
                # If conversion fails, use default quality
                save_kwargs["quality"] = 85

        # Handle DPI parameter for formats that support it
        if dpi is not None and dpi != "none":
            try:
                dpi_value = int(dpi) if isinstance(dpi, str) else dpi
                supports_dpi = output_format.lower() in [
                    "jpg",
                    "jpeg",
                    "tiff",
                    "png",
                ]
                if dpi_value > 0 and supports_dpi:
                    save_kwargs["dpi"] = (dpi_value, dpi_value)
            except (ValueError, TypeError):
                # If conversion fails, don't set DPI
                LOGGER.warning(f"Invalid DPI value: {dpi}, using default")

        # Format-specific settings
        if output_format.lower() in ["jpg", "jpeg"]:
            save_kwargs.update({"optimize": True})
            LOGGER.info(f"Saving JPEG with parameters: {save_kwargs}")
            merged_image.save(output_file, format="JPEG", **save_kwargs)
        elif output_format.lower() == "png":
            save_kwargs.update({"optimize": True})
            LOGGER.info(f"Saving PNG with parameters: {save_kwargs}")
            merged_image.save(output_file, format="PNG", **save_kwargs)
        elif output_format.lower() == "webp":
            save_kwargs.update({"method": 4})
            LOGGER.info(f"Saving WebP with parameters: {save_kwargs}")
            merged_image.save(output_file, format="WEBP", **save_kwargs)
        elif output_format.lower() == "tiff":
            save_kwargs.update({"compression": "tiff_lzw"})
            LOGGER.info(f"Saving TIFF with parameters: {save_kwargs}")
            merged_image.save(output_file, format="TIFF", **save_kwargs)
        elif output_format.lower() == "gif":
            if merged_image.mode == "RGBA":
                # Use transparency mask for GIF
                try:
                    mask = Image.eval(
                        merged_image.split()[3], lambda a: 255 if a <= 128 else 0
                    )
                    save_kwargs.update(
                        {"optimize": True, "transparency": 255, "mask": mask}
                    )
                except Exception as e:
                    LOGGER.error(f"Error creating transparency mask for GIF: {e}")
                    # Fall back to simpler approach
                    save_kwargs.update({"optimize": True})
            else:
                save_kwargs.update({"optimize": True})

            LOGGER.info(f"Saving GIF with parameters: {save_kwargs}")
            merged_image.save(output_file, format="GIF", **save_kwargs)
        elif output_format.lower() == "bmp":
            LOGGER.info(f"Saving BMP with parameters: {save_kwargs}")
            merged_image.save(output_file, format="BMP", **save_kwargs)
        else:
            # Default save for other formats
            LOGGER.info(
                f"Saving image in {output_format} format with parameters: {save_kwargs}"
            )
            merged_image.save(output_file, **save_kwargs)

        LOGGER.info(f"Successfully merged {len(images)} images into {output_file}")

        # Force garbage collection after image merging
        # This can create large objects in memory
        if smart_garbage_collection:
            smart_garbage_collection(aggressive=True)
        else:
            gc.collect()

        return output_file

    except Exception as e:
        LOGGER.error(f"Error merging images: {e}")
        return None


async def merge_documents(files, output_format="pdf"):
    """
    Merge multiple document files into a single document.
    Supports PDF merging and converting images to PDF.

    Args:
        files: List of document file paths
        output_format: Output format (currently only 'pdf' is supported)

    Returns:
        str: Path to the merged document file
    """
    if not files:
        LOGGER.error("No document files provided for merging")
        return None

    if output_format.lower() != "pdf":
        LOGGER.error(
            f"Unsupported output format: {output_format}. Only PDF is supported."
        )
        return None

    # Apply memory limits for PIL operations (for image processing)
    limit_memory_for_pil()

    # Group files by extension with validation
    file_groups = {}
    valid_files = []

    for file_path in files:
        # Check if file exists
        if not os.path.exists(file_path):
            LOGGER.error(f"Document file not found: {file_path}")
            continue

        # Get file extension
        ext = Path(file_path).suffix.lower()[1:]  # Remove the dot
        if not ext:
            LOGGER.error(f"File has no extension: {file_path}")
            continue

        # Group by extension
        if ext not in file_groups:
            file_groups[ext] = []
        file_groups[ext].append(file_path)
        valid_files.append(file_path)

    if not valid_files:
        LOGGER.error("No valid files found for merging")
        return None

    # Determine base directory for output
    base_dir = os.path.dirname(valid_files[0])
    output_file = os.path.join(base_dir, f"merged.{int(time())}.pdf")

    # Case 1: Only PDF files
    if len(file_groups) == 1 and "pdf" in file_groups:
        LOGGER.info("Merging PDF files only")
        return await merge_pdfs(file_groups["pdf"], output_file)

    # Case 2: Only image files
    image_extensions = ["jpg", "jpeg", "png", "bmp", "gif", "tiff", "webp"]
    image_files = []
    for ext in image_extensions:
        if ext in file_groups:
            image_files.extend(file_groups[ext])

    if len(image_files) == len(valid_files):
        LOGGER.info("Converting and merging image files to PDF")
        return await create_pdf_from_images(image_files, output_file)

    # Case 3: Mixed file types (PDFs and images)
    LOGGER.info("Processing mixed file types (PDFs and images)")

    # Create a new PDF document for the final output
    merged_doc = fitz.open()

    # Process PDF files first
    pdf_count = 0
    if "pdf" in file_groups:
        for pdf_path in file_groups["pdf"]:
            try:
                # Open the PDF document
                doc = fitz.open(pdf_path)

                # Check if the PDF is password-protected
                if doc.needs_pass:
                    LOGGER.warning(f"Skipping password-protected PDF: {pdf_path}")
                    doc.close()
                    continue

                # Insert all pages from this PDF
                merged_doc.insert_pdf(doc)
                doc.close()
                pdf_count += 1

            except Exception as e:
                LOGGER.error(f"Error processing PDF {pdf_path}: {e}")
                continue

    # Process image files
    image_count = 0
    for img_path in image_files:
        try:
            # Try to open as an image
            img = Image.open(img_path)

            # Convert to RGB if needed
            if img.mode == "RGBA":
                # Create white background for transparent images
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(
                    img, mask=img.split()[3]
                )  # Use alpha channel as mask
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Convert PIL image to bytes
            import io

            img_bytes = io.BytesIO()
            img.save(img_bytes, format="JPEG", quality=95)
            img_bytes.seek(0)

            # Create a new page with appropriate size
            # Calculate page size based on image dimensions and DPI
            img_width, img_height = img.size
            # Use 72 DPI as default for PDF (standard)
            page_width = img_width * 72 / 300  # Assuming 300 DPI source
            page_height = img_height * 72 / 300

            # Create page with calculated dimensions
            page = merged_doc.new_page(width=page_width, height=page_height)
            img_rect = page.rect
            page.insert_image(img_rect, stream=img_bytes.getvalue())

            image_count += 1

        except Exception as e:
            LOGGER.error(f"Error processing image {img_path}: {e}")
            continue

    # Check if we have any valid files to merge
    if pdf_count == 0 and image_count == 0:
        LOGGER.error("No valid files found for merging")
        merged_doc.close()
        return None

    # Save the merged PDF
    try:
        merged_doc.save(output_file)
        merged_doc.close()

        LOGGER.info(
            f"Successfully merged {pdf_count} PDFs and {image_count} images into {output_file}"
        )

        # Force garbage collection after document merging
        # This can create large objects in memory
        if smart_garbage_collection:
            smart_garbage_collection(aggressive=True)
        else:
            gc.collect()

        return output_file
    except Exception as e:
        LOGGER.error(f"Error writing merged PDF: {e}")
        return None


async def get_pdf_info(pdf_path):
    """
    Get detailed information about a PDF file using PyMuPDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        dict: Dictionary containing PDF information or None if error
    """
    try:
        doc = fitz.open(pdf_path)

        info = {
            "page_count": doc.page_count,
            "is_encrypted": doc.needs_pass,
            "metadata": doc.metadata,
            "file_size": os.path.getsize(pdf_path),
            "pages_info": [],
        }

        # Get information about each page
        for page_num in range(
            min(doc.page_count, 10)
        ):  # Limit to first 10 pages for performance
            page = doc[page_num]
            page_info = {
                "page_number": page_num + 1,
                "width": page.rect.width,
                "height": page.rect.height,
                "rotation": page.rotation,
                "has_images": len(page.get_images()) > 0,
                "has_text": len(page.get_text().strip()) > 0,
            }
            info["pages_info"].append(page_info)

        doc.close()
        return info

    except Exception as e:
        LOGGER.error(f"Error getting PDF info for {pdf_path}: {e}")
        return None
