import asyncio
import contextlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from pyrogram import enums

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

"""
Sox module for generating spectrograms from audio and video files.

This module provides a simplified implementation for SoX spectrogram generation
while maintaining the ability to extract audio from video files using FFmpeg.

Commands:
    /sox [ffmpeg|sox] - Generate a spectrogram from an audio or video file
        - Reply to an audio or video file with this command
        - Optional parameter to choose between FFmpeg or Sox for generation
        - Example: /sox ffmpeg or /sox sox
        - Defaults to FFmpeg if no parameter is provided
        - SoX implementation is simplified for cleaner code
"""

# Comprehensive list of supported audio and video formats
SUPPORTED_EXTS = {
    # Audio formats
    ".wav",  # Waveform Audio File Format
    ".mp3",  # MPEG Audio Layer III
    ".flac",  # Free Lossless Audio Codec
    ".ogg",  # Ogg Vorbis
    ".oga",  # Ogg Audio
    ".aiff",  # Audio Interchange File Format
    ".aif",  # Audio Interchange Format (short)
    ".aifc",  # Compressed Audio Interchange Format
    ".au",  # Sun/NeXT Audio File
    ".snd",  # Sound File
    ".raw",  # Raw PCM Audio
    ".gsm",  # GSM 06.10 Audio
    ".m4a",  # MPEG-4 Audio
    ".aac",  # Advanced Audio Coding
    ".wma",  # Windows Media Audio
    ".opus",  # Opus Audio Format
    ".mka",  # Matroska Audio
    ".ape",  # Monkey's Audio
    ".wv",  # WavPack
    ".mpc",  # Musepack
    ".amr",  # Adaptive Multi-Rate
    ".ac3",  # Dolby Digital Audio
    # Video formats (with audio tracks)
    ".mp4",  # MPEG-4 Video
    ".mkv",  # Matroska Video
    ".webm",  # WebM Video
    ".avi",  # Audio Video Interleave
    ".mov",  # QuickTime Movie
    ".wmv",  # Windows Media Video
    ".flv",  # Flash Video
    ".3gp",  # 3GPP Video
    ".ts",  # MPEG Transport Stream
    ".m4v",  # MPEG-4 Video
    ".mpg",  # MPEG Video
    ".mpeg",  # MPEG Video
    ".ogv",  # Ogg Video
    ".vob",  # DVD Video Object
    ".divx",  # DivX Video
    ".hevc",  # High Efficiency Video Coding
}


def is_supported(filename: str) -> bool:
    """Check if the file extension is supported for spectrogram generation."""
    if not filename:
        return False
    return Path(filename).suffix.lower() in SUPPORTED_EXTS


# Telegraph upload functionality has been removed


async def is_video_file(file_path):
    """
    Check if the file is a video file by examining its mime type using ffprobe.

    Args:
        file_path: Path to the file to check

    Returns:
        bool: True if the file is a video, False otherwise
    """
    ext = Path(file_path).suffix.lower()

    # Quick check based on extension - first check if it's a known audio extension
    audio_extensions = {
        ".wav",
        ".mp3",
        ".flac",
        ".ogg",
        ".oga",
        ".aiff",
        ".aif",
        ".aifc",
        ".au",
        ".snd",
        ".raw",
        ".gsm",
        ".m4a",
        ".aac",
        ".wma",
        ".opus",
        ".mka",
        ".ape",
        ".wv",
        ".mpc",
        ".amr",
        ".ac3",
    }

    # If it's a known audio extension, it's definitely not a video
    if ext in audio_extensions:
        LOGGER.info(f"File {file_path} identified as audio based on extension {ext}")
        return False

    # Check if it's a known video extension
    video_extensions = {
        ".mp4",
        ".mkv",
        ".webm",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".3gp",
        ".ts",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".ogv",
        ".vob",
        ".divx",
        ".hevc",
    }

    if ext in video_extensions:
        LOGGER.info(f"File {file_path} identified as video based on extension {ext}")
        return True

    # For ambiguous extensions, use ffprobe to check
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        file_path,
    ]

    stdout, _stderr, return_code = await cmd_exec(cmd)

    if return_code == 0:
        try:
            data = json.loads(stdout)
            streams = data.get("streams", [])
            for stream in streams:
                if stream.get("codec_type") == "video":
                    LOGGER.info(
                        f"File {file_path} identified as video based on ffprobe detection"
                    )
                    return True
        except json.JSONDecodeError:
            pass

    LOGGER.info(f"File {file_path} identified as non-video")
    return False


async def get_audio_streams(file_path):
    """
    Get information about all audio streams in a file.

    Args:
        file_path: Path to the file to check

    Returns:
        list: List of dictionaries containing information about each audio stream
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index,codec_name,channels,sample_rate:stream_tags=language,title",
        "-of",
        "json",
        file_path,
    ]

    stdout, _stderr, return_code = await cmd_exec(cmd)

    if return_code == 0:
        try:
            data = json.loads(stdout)
            streams = data.get("streams", [])

            # Enhance stream info with more readable descriptions
            for stream in streams:
                # Add stream number for display (1-based for user-friendly display)
                stream["stream_number"] = stream.get("index", 0) + 1

                # Get language if available
                tags = stream.get("tags", {})
                language = tags.get("language", "und")
                title = tags.get("title", "")

                # Create a display name for the stream
                display_name = f"Stream {stream['stream_number']}"
                if language != "und":
                    display_name += f" ({language.upper()})"
                if title:
                    display_name += f": {title}"

                stream["display_name"] = display_name

            return streams
        except json.JSONDecodeError:
            LOGGER.error("Failed to parse ffprobe output as JSON")

    return []


async def get_audio_info_for_display(file_path):
    """
    Get formatted audio information for display.

    Args:
        file_path: Path to the audio file

    Returns:
        str: Formatted audio information string
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,channels,sample_rate:format=duration",
        "-of",
        "json",
        file_path,
    ]

    stdout, _stderr, return_code = await cmd_exec(cmd)

    if return_code == 0:
        try:
            data = json.loads(stdout)
            streams = data.get("streams", [])
            format_info = data.get("format", {})

            # Check if there are any audio streams
            if not streams:
                # Try to get just the duration from the format
                duration_str = format_info.get("duration", "Unknown")
                try:
                    duration = float(duration_str)
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    duration_formatted = f"{minutes}m {seconds}s"
                except (ValueError, TypeError):
                    duration_formatted = "Unknown"

                return f"No audio stream detected, Duration: {duration_formatted}"

            # If we have audio streams, get the info from the first one
            stream_info = streams[0]
            codec = stream_info.get("codec_name", "Unknown")
            channels = stream_info.get("channels", "Unknown")
            sample_rate = stream_info.get("sample_rate", "Unknown")
            duration_str = format_info.get("duration", "Unknown")

            try:
                duration = float(duration_str)
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                duration_formatted = f"{minutes}m {seconds}s"
            except (ValueError, TypeError):
                duration_formatted = "Unknown"

            return f"Codec: {codec}, Channels: {channels}, Sample rate: {sample_rate} Hz, Duration: {duration_formatted}"
        except Exception as e:
            LOGGER.error(f"Error parsing audio info: {e}")

    return "Unknown format"


async def extract_audio_from_video(
    input_file, temp_dir, stream_index=None, stream_info=None
):
    """
    Extract audio from a video file.

    Args:
        input_file: Path to the input video file
        temp_dir: Directory to store the extracted audio
        stream_index: Index of the audio stream to extract (0-based)
        stream_info: Dictionary with stream information (optional)

    Returns:
        Tuple of (path to extracted audio file, success status)
    """
    # Create a descriptive filename based on stream info if available
    if stream_info:
        stream_desc = f"_stream{stream_info.get('stream_number', stream_index + 1)}"
        if stream_info.get("tags", {}).get("language"):
            stream_desc += f"_{stream_info['tags']['language']}"
        filename = f"{Path(input_file).stem}{stream_desc}.flac"
    else:
        # If no specific stream info, use a generic name or include stream index if provided
        stream_desc = (
            f"_stream{stream_index + 1}" if stream_index is not None else ""
        )
        filename = f"{Path(input_file).stem}{stream_desc}_audio.flac"

    output_file = os.path.join(temp_dir, filename)

    # Log what we're extracting
    if stream_index is not None:
        LOGGER.info(
            f"Extracting audio stream {stream_index} from video file: {input_file}"
        )
    else:
        LOGGER.info(f"Extracting all audio from video file: {input_file}")

    # Base command
    cmd = [
        "xtra",
        "-i",
        input_file,
        "-vn",  # No video
        "-c:a",
        "flac",  # Convert to FLAC
        "-q:a",
        "8",  # High quality
    ]

    # Add stream mapping if a specific stream is requested
    if stream_index is not None:
        # Use direct stream index (0:1, 0:2, etc.) instead of stream type index (0:a:0, 0:a:1)
        cmd.extend(["-map", f"0:{stream_index}"])

    # Add output file
    cmd.extend(["-y", output_file])

    stdout, stderr, return_code = await cmd_exec(cmd)

    # If xtra fails, try with ffmpeg as fallback
    if return_code != 0:
        LOGGER.info(
            "xtra command failed for audio extraction, trying with ffmpeg as fallback"
        )
        cmd[0] = "ffmpeg"
        _stdout, stderr, return_code = await cmd_exec(cmd)

    if return_code == 0:
        LOGGER.info(f"Audio extraction successful: {output_file}")
        return output_file, True

    LOGGER.error(f"Audio extraction failed: {stderr}")
    return input_file, False


async def convert_to_compatible_format(
    input_file, temp_dir, stream_index=None, stream_info=None
):
    """
    Convert audio to a format compatible with both FFmpeg and Sox if needed.
    For video files, extract the audio track first.

    Args:
        input_file: Path to the input audio or video file
        temp_dir: Directory to store the converted file
        stream_index: Index of the audio stream to extract (0-based)
        stream_info: Dictionary with stream information (optional)

    Returns:
        Tuple of (path to compatible file, whether conversion was performed)
    """
    ext = Path(input_file).suffix.lower()

    # Check if it's a video file
    is_video = await is_video_file(input_file)

    # If it's a video file, extract the audio first
    if is_video:
        LOGGER.info(f"Detected video file: {input_file}")
        extracted_audio, success = await extract_audio_from_video(
            input_file, temp_dir, stream_index, stream_info
        )
        if success:
            return extracted_audio, True
        LOGGER.warning(
            "Failed to extract audio, will try to process the original file"
        )

    # If the format is already well-supported by both, return the original
    if ext in [".wav", ".mp3", ".flac"]:
        return input_file, False

    # For other formats, convert to FLAC for better compatibility
    LOGGER.info(f"Converting {ext} file to FLAC for better compatibility")

    # Create output filename
    if stream_index is not None:
        stream_desc = f"_stream{stream_index + 1}"
        if stream_info and stream_info.get("tags", {}).get("language"):
            stream_desc += f"_{stream_info['tags']['language']}"
        output_file = os.path.join(
            temp_dir, f"{Path(input_file).stem}{stream_desc}.flac"
        )
    else:
        output_file = os.path.join(temp_dir, f"{Path(input_file).stem}.flac")

    # Base command
    cmd = ["xtra", "-i", input_file]

    # Add stream mapping if a specific stream is requested
    if stream_index is not None and is_video:
        cmd.extend(["-map", f"0:a:{stream_index}"])

    # Add output format and file
    cmd.extend(["-c:a", "flac", "-y", output_file])

    stdout, stderr, return_code = await cmd_exec(cmd)

    # If xtra fails, try with ffmpeg as fallback
    if return_code != 0:
        LOGGER.info(
            "xtra command failed for conversion, trying with ffmpeg as fallback"
        )
        cmd[0] = "ffmpeg"
        _stdout, stderr, return_code = await cmd_exec(cmd)

    if return_code == 0:
        LOGGER.info("Conversion to FLAC successful")
        return output_file, True
    LOGGER.error(f"Conversion to FLAC failed: {stderr}")
    return input_file, False


async def generate_spectrogram_with_ffmpeg(input_file, output_file, is_video=False):
    """
    Generate a spectrogram using FFmpeg (or xtra which is the renamed ffmpeg in the container).
    This is more reliable as FFmpeg is more commonly available.

    Args:
        input_file: Path to the input audio or video file
        output_file: Path to save the output spectrogram image
        is_video: Whether the input file is a video file

    Returns:
        Tuple of (success status, error message if any)
    """
    # Check if the file has audio streams
    has_audio_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        input_file,
    ]

    stdout, stderr, return_code = await cmd_exec(has_audio_cmd)
    has_audio = False

    if return_code == 0:
        try:
            data = json.loads(stdout)
            has_audio = len(data.get("streams", [])) > 0
        except json.JSONDecodeError:
            pass

    # Get duration to optimize spectrogram settings
    duration_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        input_file,
    ]

    stdout, stderr, return_code = await cmd_exec(duration_cmd)

    # Default duration if we can't determine it
    duration = 300  # 5 minutes default

    if return_code == 0:
        try:
            data = json.loads(stdout)
            duration_str = data.get("format", {}).get("duration", "300")
            duration = float(duration_str)
        except (json.JSONDecodeError, ValueError):
            pass

    # Adjust spectrogram settings based on duration
    width = 1500
    if duration > 600:  # For files longer than 10 minutes
        width = 2000
    elif duration < 60:  # For files shorter than 1 minute
        width = 1200

    # If the file has no audio but is a video, generate a visual representation instead
    if not has_audio and is_video:
        LOGGER.info(
            "No audio stream detected, generating visual representation from video frames"
        )

        # Generate a visual representation using frame thumbnails
        cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-vf",
            f"fps=1/{max(1, int(duration / 30))},scale=1500:-1,tile={min(int(duration), 30)}x1",
            "-frames:v",
            "1",
            "-y",
            output_file,
        ]

        stdout, stderr, return_code = await cmd_exec(cmd)

        if return_code == 0:
            LOGGER.info("Generated visual representation from video frames")
            return True, ""

        # If that fails, try a simpler approach with just a few frames
        LOGGER.info("First approach failed, trying simpler visual representation")
        cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-vf",
            "fps=1/5,scale=320:-1,tile=5x1",
            "-frames:v",
            "1",
            "-y",
            output_file,
        ]

        stdout, stderr, return_code = await cmd_exec(cmd)

        return return_code == 0, stderr

    # For audio files or videos with audio, generate a spectrogram

    # Enhanced filter settings for better visualization
    filter_complex = (
        f"showspectrumpic=s={width}x800:mode=combined:color=rainbow:gain=25:"
        f"saturation=10:fscale=log:legend=1:stop=22050:scale=log:win_func=hann"
    )

    # For very long files, use a different approach to avoid memory issues
    if duration > 1800:  # For files longer than 30 minutes
        LOGGER.info("Long audio detected, using optimized spectrogram generation")
        filter_complex = (
            f"showspectrumpic=s={width}x800:mode=separate:color=rainbow:gain=20:"
            f"saturation=5:fscale=log:legend=1:stop=20000:scale=log"
        )

    # Try with xtra first (the renamed ffmpeg in the container)
    cmd = [
        "xtra",  # Using xtra instead of ffmpeg
        "-i",
        input_file,
        "-lavfi",
        filter_complex,
        "-y",
        output_file,
    ]

    stdout, stderr, return_code = await cmd_exec(cmd)

    # If xtra fails, try with ffmpeg as fallback
    if return_code != 0:
        LOGGER.info("xtra command failed, trying with ffmpeg as fallback")
        cmd[0] = "ffmpeg"
        stdout, stderr, return_code = await cmd_exec(cmd)

    # If still failing and it's a video file with audio, try extracting audio first
    if return_code != 0 and is_video and has_audio:
        LOGGER.info(
            "Direct spectrogram generation failed, trying to extract audio first"
        )
        temp_audio = f"{os.path.splitext(output_file)[0]}_temp.wav"

        extract_cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-y",
            temp_audio,
        ]

        stdout, stderr, return_code = await cmd_exec(extract_cmd)

        if return_code == 0:
            # Now try generating spectrogram from the extracted audio
            cmd = [
                "ffmpeg",
                "-i",
                temp_audio,
                "-lavfi",
                filter_complex,
                "-y",
                output_file,
            ]

            stdout, stderr, return_code = await cmd_exec(cmd)

            # Clean up temporary audio file
            with contextlib.suppress(OSError):
                os.remove(temp_audio)

    return return_code == 0, stderr


async def generate_spectrogram_with_sox(input_file, output_file):
    """
    Generate a spectrogram using Sox.
    This is a simplified implementation similar to the example provided.

    Args:
        input_file: Path to the input audio file
        output_file: Path to save the output spectrogram image

    Returns:
        Tuple of (success status, error message if any)
    """
    # Simple Sox command for spectrogram generation
    process = await asyncio.create_subprocess_exec(
        "sox",
        input_file,
        "-n",
        "spectrogram",
        "-o",
        output_file,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()
    return_code = process.returncode

    if return_code != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        LOGGER.error(f"Sox spectrogram generation failed: {error_msg}")
        return False, error_msg

    return True, ""


async def spectrum_handler(_, message):
    """
    Handle the /sox command to generate a spectrogram from an audio file.

    Usage: /sox [ffmpeg|sox]

    Args:
        _: Client instance (unused)
        message: Message object containing the command
    """
    # Check if the message exists and is a reply
    if not message:
        LOGGER.error("Message object is None in spectrum_handler")
        return

    # Parse command arguments to check if user specified a tool
    command_text = message.text.strip() if hasattr(message, "text") else ""
    command_parts = command_text.split(maxsplit=1)

    # Default to FFmpeg as it's more reliable
    tool_choice = "ffmpeg"

    # Check if user specified a tool
    if len(command_parts) > 1:
        arg = command_parts[1].lower()
        if arg == "sox":
            tool_choice = "sox"
        elif arg == "ffmpeg":
            tool_choice = "ffmpeg"
        else:
            # Invalid argument provided
            error_msg = await send_message(
                message, "Invalid option. Usage: /sox [ffmpeg|sox]"
            )
            await auto_delete_message(error_msg, time=300)
            return

    LOGGER.info(f"Using {tool_choice} for spectrogram generation")

    # Check if the message is a reply
    replied = getattr(message, "reply_to_message", None)
    if not replied:
        error_msg = await send_message(
            message,
            "Reply to an audio, video, or document message with /sox [ffmpeg|sox].",
        )
        await auto_delete_message(error_msg, time=300)
        return

    # Get the media from the replied message
    # Use getattr to safely access attributes that might not exist
    document = getattr(replied, "document", None)
    audio = getattr(replied, "audio", None)
    video = getattr(replied, "video", None)
    media = document or audio or video

    if not media:
        error_msg = await send_message(
            message,
            "Reply to an audio, video, or document message with /sox [ffmpeg|sox].",
        )
        await auto_delete_message(error_msg, time=300)
        return

    # Check if it's a document but not an audio or video file
    mime_type = getattr(media, "mime_type", "")
    is_document = document is not None

    if (
        mime_type
        and "audio" not in mime_type
        and "video" not in mime_type
        and is_document
    ):
        error_msg = await send_message(
            message,
            "The document doesn't appear to be an audio or video file. Only audio and video files are supported.",
        )
        await auto_delete_message(error_msg, time=300)
        return

    # Get the filename safely
    file_name = getattr(media, "file_name", None)

    # Check if the file format is supported
    if not file_name or not is_supported(file_name):
        supported_formats = ", ".join(sorted(SUPPORTED_EXTS))
        error_msg = await send_message(
            message,
            f"Unsupported file format. Supported formats: {supported_formats}",
        )
        await auto_delete_message(error_msg, time=300)
        return

    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp(prefix="spectrum_")
    file_path = os.path.join(temp_dir, file_name or "input")
    output_path = os.path.join(
        temp_dir, f"{os.path.splitext(file_name or 'spectrum')[0]}.png"
    )

    # Send initial progress message
    progress_message = await send_message(message, "Downloading... 0%")
    last_update = 0

    # Progress callback for download
    async def progress(current, total):
        nonlocal last_update
        now = time.time()
        if now - last_update > 2:
            percent = current * 100 / total
            downloaded_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            # Pass empty buttons explicitly to avoid None
            await edit_message(
                progress_message,
                f"Downloading... {downloaded_mb:.2f}MB / {total_mb:.2f}MB {percent:.1f}%",
                buttons={},
            )
            last_update = now

    try:
        # Download the file
        await replied.download(file_path, progress=progress)

        # Check if it's a video file
        is_video = await is_video_file(file_path)

        if is_video:
            await edit_message(
                progress_message, "Processing video file...", buttons={}
            )
            LOGGER.info(f"Processing video file: {file_path}")

            # Check for multiple audio streams
            audio_streams = await get_audio_streams(file_path)

            if len(audio_streams) > 1:
                LOGGER.info(f"Found {len(audio_streams)} audio streams in the video")
                await edit_message(
                    progress_message,
                    f"Found {len(audio_streams)} audio streams in the video. Processing each stream...",
                    buttons={},
                )

                # Process each audio stream
                all_spectrograms = []
                all_audio_info = []

                for i, stream in enumerate(audio_streams):
                    stream_index = stream.get("index", i)
                    stream_display = stream.get("display_name", f"Stream {i + 1}")

                    await edit_message(
                        progress_message,
                        f"Processing audio stream {i + 1}/{len(audio_streams)}: {stream_display}",
                        buttons={},
                    )

                    # Create a unique output path for this stream
                    stream_output_path = os.path.join(
                        temp_dir,
                        f"{os.path.splitext(file_name or 'spectrum')[0]}_stream{i + 1}.png",
                    )

                    # Convert to a compatible format if needed
                    (
                        compatible_file,
                        was_converted,
                    ) = await convert_to_compatible_format(
                        file_path, temp_dir, stream_index, stream
                    )

                    if was_converted:
                        await edit_message(
                            progress_message,
                            f"Extracted audio stream {i + 1}/{len(audio_streams)} from video for processing.",
                            buttons={},
                        )

                    # Generate spectrogram with the user's chosen tool
                    if tool_choice == "sox":
                        await edit_message(
                            progress_message,
                            f"Generating spectrogram for audio stream {i + 1}/{len(audio_streams)} with SoX...",
                            buttons={},
                        )
                        # Simple check if sox is available
                        try:
                            process = await asyncio.create_subprocess_exec(
                                "which",
                                "sox",
                                stdout=asyncio.subprocess.DEVNULL,
                                stderr=asyncio.subprocess.DEVNULL,
                            )
                            sox_return_code = await process.wait()

                            if sox_return_code == 0:  # Sox is available
                                success, error = await generate_spectrogram_with_sox(
                                    compatible_file, stream_output_path
                                )
                            else:
                                await edit_message(
                                    progress_message,
                                    f"SoX is not installed. Falling back to FFmpeg for stream {i + 1}/{len(audio_streams)}...",
                                    buttons={},
                                )
                                # Update tool_choice to reflect the actual tool being used
                                tool_choice = "ffmpeg"
                                (
                                    success,
                                    error,
                                ) = await generate_spectrogram_with_ffmpeg(
                                    compatible_file, stream_output_path, is_video
                                )
                        except Exception as e:
                            LOGGER.error(f"Error checking for sox: {e}")
                            await edit_message(
                                progress_message,
                                f"Error checking for SoX. Falling back to FFmpeg for stream {i + 1}/{len(audio_streams)}...",
                                buttons={},
                            )
                            # Update tool_choice to reflect the actual tool being used
                            tool_choice = "ffmpeg"
                            success, error = await generate_spectrogram_with_ffmpeg(
                                compatible_file, stream_output_path, is_video
                            )
                    else:  # Default to FFmpeg
                        await edit_message(
                            progress_message,
                            f"Generating spectrogram for audio stream {i + 1}/{len(audio_streams)} with FFmpeg...",
                            buttons={},
                        )
                        success, error = await generate_spectrogram_with_ffmpeg(
                            compatible_file, stream_output_path, is_video
                        )

                    if success:
                        # Get audio information for this stream
                        audio_info = await get_audio_info_for_display(
                            compatible_file
                        )

                        # Add stream information to the audio info
                        audio_info = f"Stream {i + 1}/{len(audio_streams)} - {stream_display}: {audio_info}"

                        all_spectrograms.append(stream_output_path)
                        all_audio_info.append(audio_info)
                    else:
                        LOGGER.error(
                            f"Failed to generate spectrogram for stream {i + 1}: {error}"
                        )

                # If we have at least one successful spectrogram, continue with the first one
                # but we'll send all of them later
                if all_spectrograms:
                    output_path = all_spectrograms[0]
                    success = True
                else:
                    success = False
                    error = "Failed to generate spectrograms for any audio stream"

                # Skip the regular processing below since we've already done it for each stream
                multiple_audio_streams = True
            else:
                multiple_audio_streams = False
                # Single audio stream or no audio stream, proceed normally
                if audio_streams:
                    LOGGER.info("Found a single audio stream in the video")
                    stream = audio_streams[0]
                    stream_index = stream.get("index", 0)

                    # Convert to a compatible format if needed
                    (
                        compatible_file,
                        was_converted,
                    ) = await convert_to_compatible_format(
                        file_path, temp_dir, stream_index, stream
                    )
                else:
                    LOGGER.info("No audio streams found in the video")
                    # Convert to a compatible format if needed
                    (
                        compatible_file,
                        was_converted,
                    ) = await convert_to_compatible_format(file_path, temp_dir)

                if was_converted:
                    await edit_message(
                        progress_message,
                        "Extracted audio from video for processing.",
                        buttons={},
                    )

                # Generate spectrogram with the user's chosen tool
                if tool_choice == "sox":
                    await edit_message(
                        progress_message,
                        "Generating high-quality spectrogram with SoX...",
                        buttons={},
                    )
                    # Check if sox is available
                    sox_check_cmd = ["which", "sox"]
                    _, _, sox_return_code = await cmd_exec(sox_check_cmd)

                    if sox_return_code == 0:  # Sox is available
                        success, error = await generate_spectrogram_with_sox(
                            compatible_file, output_path
                        )
                    else:
                        await edit_message(
                            progress_message,
                            "SoX is not installed. Falling back to FFmpeg...",
                            buttons={},
                        )
                        # Update tool_choice to reflect the actual tool being used
                        tool_choice = "ffmpeg"
                        success, error = await generate_spectrogram_with_ffmpeg(
                            compatible_file, output_path, is_video
                        )
                else:  # Default to FFmpeg
                    await edit_message(
                        progress_message,
                        "Generating high-quality spectrogram with FFmpeg...",
                        buttons={},
                    )
                    success, error = await generate_spectrogram_with_ffmpeg(
                        compatible_file, output_path, is_video
                    )
        else:
            # Regular audio file processing
            multiple_audio_streams = False
            await edit_message(
                progress_message, "Processing audio file...", buttons={}
            )
            LOGGER.info(f"Processing audio file: {file_path}")

            # Convert to a compatible format if needed
            compatible_file, was_converted = await convert_to_compatible_format(
                file_path, temp_dir
            )

            if was_converted:
                await edit_message(
                    progress_message,
                    "Converted audio to a compatible format for processing.",
                    buttons={},
                )

            # Generate spectrogram with the user's chosen tool
            if tool_choice == "sox":
                await edit_message(
                    progress_message,
                    "Generating spectrogram with SoX...",
                    buttons={},
                )
                # Simple check if sox is available
                try:
                    process = await asyncio.create_subprocess_exec(
                        "which",
                        "sox",
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    sox_return_code = await process.wait()

                    if sox_return_code == 0:  # Sox is available
                        success, error = await generate_spectrogram_with_sox(
                            compatible_file, output_path
                        )
                    else:
                        await edit_message(
                            progress_message,
                            "SoX is not installed. Falling back to FFmpeg...",
                            buttons={},
                        )
                        # Update tool_choice to reflect the actual tool being used
                        tool_choice = "ffmpeg"
                        success, error = await generate_spectrogram_with_ffmpeg(
                            compatible_file, output_path, is_video
                        )
                except Exception as e:
                    LOGGER.error(f"Error checking for sox: {e}")
                    await edit_message(
                        progress_message,
                        "Error checking for SoX. Falling back to FFmpeg...",
                        buttons={},
                    )
                    # Update tool_choice to reflect the actual tool being used
                    tool_choice = "ffmpeg"
                    success, error = await generate_spectrogram_with_ffmpeg(
                        compatible_file, output_path, is_video
                    )
            else:  # Default to FFmpeg
                await edit_message(
                    progress_message,
                    "Generating spectrogram with FFmpeg...",
                    buttons={},
                )
                success, error = await generate_spectrogram_with_ffmpeg(
                    compatible_file, output_path, is_video
                )

        # If the chosen method fails, try with the alternative method as fallback
        if not success:
            # Check if we need to try the alternative method
            if tool_choice == "ffmpeg":
                # Simple check if sox is available for fallback
                try:
                    process = await asyncio.create_subprocess_exec(
                        "which",
                        "sox",
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    sox_return_code = await process.wait()

                    if sox_return_code == 0:  # Sox is available
                        await edit_message(
                            progress_message,
                            "FFmpeg method failed, trying with Sox as fallback...",
                            buttons={},
                        )
                        # Update tool_choice to reflect the actual tool being used
                        tool_choice = "sox"
                        success, error = await generate_spectrogram_with_sox(
                            compatible_file, output_path
                        )

                        if not success:
                            await edit_message(
                                progress_message,
                                f"Failed to generate spectrum with both FFmpeg and Sox. Error: {error}",
                                buttons={},
                            )
                            await auto_delete_message(progress_message, time=300)
                            return
                    else:  # Sox is not available
                        await edit_message(
                            progress_message,
                            f"Failed to generate spectrum with FFmpeg. Sox is not installed for fallback. Error: {error}",
                            buttons={},
                        )
                        await auto_delete_message(progress_message, time=300)
                        return
                except Exception as e:
                    LOGGER.error(f"Error checking for sox: {e}")
                    await edit_message(
                        progress_message,
                        f"Failed to generate spectrum with FFmpeg and couldn't check for Sox. Error: {error}",
                        buttons={},
                    )
                    await auto_delete_message(progress_message, time=300)
                    return
            else:  # tool_choice was "sox" but it failed
                await edit_message(
                    progress_message,
                    "Sox method failed, trying with FFmpeg as fallback...",
                    buttons={},
                )
                # Update tool_choice to reflect the actual tool being used
                tool_choice = "ffmpeg"
                success, error = await generate_spectrogram_with_ffmpeg(
                    compatible_file, output_path, is_video
                )

                if not success:
                    await edit_message(
                        progress_message,
                        f"Failed to generate spectrum with both Sox and FFmpeg. Error: {error}",
                        buttons={},
                    )
                    await auto_delete_message(progress_message, time=300)
                    return

        # Verify the output file exists and is not empty
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            await edit_message(
                progress_message,
                "Failed to generate a valid spectrogram image.",
                buttons={},
            )
            await auto_delete_message(progress_message, time=300)
            return

        # Handle multiple audio streams case
        if (
            "multiple_audio_streams" in locals()
            and multiple_audio_streams
            and "all_spectrograms" in locals()
            and all_spectrograms
        ):
            display_name = os.path.basename(file_name) if file_name else "Video"

            # For multiple audio streams, we're always processing a video file
            # Create a clear description
            file_description = "Audio streams extracted from video file"

            # Send a summary message with HTML formatting
            tool_used = "SoX" if tool_choice == "sox" else "FFmpeg"
            summary_text = (
                f"<b>Audio Spectrograms:</b> <code>{display_name}</code>\n"
                f"<blockquote>Source: {file_description}</blockquote>\n"
                f"<blockquote>Generated with: {tool_used}</blockquote>\n\n"
                f"<i>Sending {len(all_spectrograms)} spectrograms as photos...</i>"
            )

            try:
                # Send with HTML parse mode
                info_msg = await message.reply_text(
                    summary_text,
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as e:
                # Fallback to plain text if HTML fails
                LOGGER.error(
                    f"HTML formatting failed: {e}. Falling back to plain text."
                )
                tool_used = "SoX" if tool_choice == "sox" else "FFmpeg"
                plain_text = f"Audio Spectrograms: {display_name}\nSource: {file_description}\nGenerated with: {tool_used}\n\nSending {len(all_spectrograms)} spectrograms as photos..."
                info_msg = await message.reply_text(plain_text)
            # Auto-delete the info message after 5 minutes
            await auto_delete_message(info_msg, time=300)

            # Send all spectrograms as photos
            for i, spectrogram_path in enumerate(all_spectrograms):
                info = (
                    all_audio_info[i]
                    if i < len(all_audio_info)
                    else f"Stream {i + 1}"
                )
                # Format caption with HTML tags
                tool_used = "SoX" if tool_choice == "sox" else "FFmpeg"
                caption = (
                    f"<b>Audio Spectrogram {i + 1}:</b> <code>{display_name}</code>\n"
                    f"<blockquote>Source: {file_description}</blockquote>\n"
                    f"<blockquote>Generated with: {tool_used}</blockquote>\n"
                    f"<pre>{info}</pre>"
                )

                try:
                    # Send with HTML parse mode
                    photo_msg = await message.reply_photo(
                        spectrogram_path,
                        caption=caption,
                        parse_mode=enums.ParseMode.HTML,
                    )
                except Exception as e:
                    # Fallback to plain text if HTML fails
                    LOGGER.error(
                        f"HTML formatting failed: {e}. Falling back to plain text."
                    )
                    tool_used = "SoX" if tool_choice == "sox" else "FFmpeg"
                    plain_caption = f"Audio Spectrogram {i + 1}: {display_name}\nSource: {file_description}\nGenerated with: {tool_used}\n{info}"
                    photo_msg = await message.reply_photo(
                        spectrogram_path,
                        caption=plain_caption,
                    )
                # Auto-delete the photo message after 5 minutes
                await auto_delete_message(photo_msg, time=300)
        else:
            # Single audio stream case - get audio information for display
            audio_info = await get_audio_info_for_display(compatible_file)

            await edit_message(
                progress_message, "Preparing to send spectrogram...", buttons={}
            )

            display_name = os.path.basename(file_name) if file_name else "Audio"

            # Create a clear message that accurately describes the content
            if is_video:
                # For video files, we're showing audio extracted from the video
                file_description = "Audio extracted from video file"
            else:
                # For audio files, we're showing the audio directly
                file_description = "Audio file"

            # Format the caption with HTML tags
            tool_used = "SoX" if tool_choice == "sox" else "FFmpeg"
            caption = (
                f"<b>Audio Spectrogram:</b> <code>{display_name}</code>\n"
                f"<blockquote>Source: {file_description}</blockquote>\n"
                f"<blockquote>Generated with: {tool_used}</blockquote>\n"
                f"<pre>Audio Details: {audio_info}</pre>"
            )

            try:
                # Send with HTML parse mode
                reply_msg = await message.reply_photo(
                    output_path,
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as e:
                # Fallback to plain text if HTML fails
                LOGGER.error(
                    f"HTML formatting failed: {e}. Falling back to plain text."
                )
                tool_used = "SoX" if tool_choice == "sox" else "FFmpeg"
                plain_caption = f"Audio Spectrogram: {display_name}\nSource: {file_description}\nGenerated with: {tool_used}\nAudio Details: {audio_info}"
                reply_msg = await message.reply_photo(
                    output_path,
                    caption=plain_caption,
                )
            # Auto-delete the reply message after 5 minutes
            await auto_delete_message(reply_msg, time=300)

        # Auto-delete the command message and the replied message after 5 minutes
        await auto_delete_message(message, time=300)
        await auto_delete_message(replied, time=300)

        await delete_message(progress_message)

    except Exception as e:
        LOGGER.error(f"Error generating spectrogram: {e!s}")
        error_msg = await edit_message(
            progress_message, f"Unexpected error: {e}", buttons={}
        )
        await auto_delete_message(error_msg, time=300)

        # Make sure to auto-delete the command message and replied message even in case of error
        await auto_delete_message(message, time=300)
        await auto_delete_message(replied, time=300)
    finally:
        # Clean up temporary files
        shutil.rmtree(temp_dir, ignore_errors=True)
