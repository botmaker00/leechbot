import gc
import json
import os
from hashlib import md5

from langcodes import Language

from bot import LOGGER
from bot.helper.ext_utils.aiofiles_compat import aiopath
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.status_utils import (
    get_readable_file_size,
    get_readable_time,
)
from bot.helper.ext_utils.template_processor import process_template

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None


class DefaultDict(dict):
    """A dictionary that returns 'Unknown' for missing keys."""

    def __missing__(self, _):
        return "Unknown"


async def calculate_md5(file_path, block_size=8192):
    """Calculate MD5 hash of a file."""
    # Check if file exists before attempting to calculate MD5
    try:
        if not await aiopath.exists(file_path):
            LOGGER.error(f"File does not exist for MD5 calculation: {file_path}")
            return "Unknown"

        # Check if file has content
        file_size = await aiopath.getsize(file_path)
        if file_size == 0:
            LOGGER.error(
                f"File exists but has zero size for MD5 calculation: {file_path}"
            )
            return "Unknown"

        # Use async file operations when possible
        try:
            import aiofiles

            md5_hash = md5()
            async with aiofiles.open(file_path, "rb") as f:
                # Only read the first block for speed
                data = await f.read(block_size)
                md5_hash.update(data)
            # MD5 hash is already a string, so no conversion needed
            return md5_hash.hexdigest()[:10]  # Return first 10 chars for brevity
        except ImportError:
            # Fall back to synchronous operation if aiofiles is not available
            md5_hash = md5()
            with open(file_path, "rb") as f:
                # Only read the first block for speed
                data = f.read(block_size)
                md5_hash.update(data)
            # MD5 hash is already a string, so no conversion needed
            return md5_hash.hexdigest()[:10]  # Return first 10 chars for brevity
    except FileNotFoundError:
        # File might have been deleted between the existence check and now
        LOGGER.error(f"File disappeared during MD5 calculation: {file_path}")
        return "Unknown"
    except PermissionError:
        LOGGER.error(f"Permission denied when calculating MD5: {file_path}")
        return "Unknown"
    except Exception as e:
        LOGGER.error(f"Error calculating MD5: {e}")
        return "Unknown"


def clean_caption(caption):
    """Clean up the caption while preserving user-intended formatting and whitespace."""
    if not caption:
        return ""

    # Preserve all user formatting - only remove trailing whitespace from the entire caption
    # and ensure it doesn't end with excessive newlines
    cleaned = caption.rstrip()

    # Only remove excessive trailing newlines (more than 2)
    while cleaned.endswith("\n\n\n"):
        cleaned = cleaned[:-1]

    return cleaned


async def generate_caption(
    filename, directory, caption_template, html_prefix=None, html_suffix=None
):
    """
    Generate a caption for a file using a template.

    Args:
        filename (str): The name of the file
        directory (str): The directory containing the file
        caption_template (str): The template to use for the caption
        html_prefix (str, optional): HTML-formatted prefix to include in filename
        html_suffix (str, optional): HTML-formatted suffix to include in filename

    Returns:
        str: The generated caption
    """
    file_path = os.path.join(directory, filename)

    # Check if the file exists before proceeding
    try:
        if not await aiopath.exists(file_path):
            LOGGER.error(f"File does not exist for caption generation: {file_path}")
            return f"<code>{filename}</code>"  # Return a simple caption with just the filename

        # Also check if file has content
        file_size = await aiopath.getsize(file_path)
        if file_size == 0:
            LOGGER.error(
                f"File exists but has zero size for caption generation: {file_path}"
            )
            return f"<code>{filename}</code>"  # Return a simple caption with just the filename
    except Exception as e:
        LOGGER.error(f"Error checking file existence: {e}")
        return f"<code>{filename}</code>"  # Return a simple caption with just the filename

    # Use the original file path directly
    file_path_to_use = file_path

    try:
        # Check if file still exists before proceeding further
        try:
            # Use async file operations for better performance
            if not await aiopath.exists(file_path):
                LOGGER.error(
                    f"File disappeared during caption generation: {file_path}"
                )
                return f"<code>{filename}</code>"  # Return a simple caption with just the filename

            # Also check if we can access the file's modification time
            await aiopath.getmtime(file_path)

            # Check file size again
            file_size = await aiopath.getsize(file_path)
            if file_size == 0:
                LOGGER.error(
                    f"File exists but has zero size during processing: {file_path}"
                )
                return f"<code>{filename}</code>"  # Return a simple caption with just the filename
        except FileNotFoundError:
            # File might have been deleted between the existence check and now
            LOGGER.error(f"File disappeared during caption generation: {file_path}")
            return f"<code>{filename}</code>"  # Return a simple caption with just the filename
        except Exception as e:
            LOGGER.error(f"Error accessing file during caption generation: {e}")
            return f"<code>{filename}</code>"  # Return a simple caption with just the filename

        # cmd_exec with shell=False handles special characters properly, so we can use the original file path

        # Get media info using ffprobe command
        try:
            # Double-check file existence right before running ffprobe
            if not await aiopath.exists(file_path_to_use):
                LOGGER.error(
                    f"File does not exist before running ffprobe: {file_path_to_use}"
                )
                return f"<code>{filename}</code>"

            # Check if file is accessible and has size > 0
            try:
                file_size = await aiopath.getsize(file_path_to_use)
                if file_size == 0:
                    LOGGER.error(
                        f"File exists but has zero size: {file_path_to_use}"
                    )
                    return f"<code>{filename}</code>"
            except Exception as e:
                LOGGER.error(f"Error checking file size before ffprobe: {e}")
                return f"<code>{filename}</code>"

            # Run ffprobe command with absolute path
            abs_path = os.path.abspath(file_path_to_use)

            # Use ffprobe instead of mediainfo since it's more reliably available
            result = await cmd_exec(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    abs_path,
                ]
            )

            if not result[0]:
                LOGGER.error(f"ffprobe returned empty output for: {abs_path}")
                return f"<code>{filename}</code>"

            # Parse JSON output
            try:
                ffprobe_data = json.loads(result[0])
            except json.JSONDecodeError as e:
                LOGGER.error(f"Failed to parse ffprobe JSON output: {e}")
                return f"<code>{filename}</code>"

        except FileNotFoundError as error:
            LOGGER.error(f"File not found when running ffprobe: {error}")
            # Return a basic caption with just the filename
            return f"<code>{filename}</code>"
        except PermissionError as error:
            LOGGER.error(f"Permission denied when running ffprobe: {error}")
            # Return a basic caption with just the filename
            return f"<code>{filename}</code>"
        except Exception as error:
            LOGGER.error(f"Failed to retrieve media info: {error}")
            # Return a basic caption with just the filename
            return f"<code>{filename}</code>"

        # Extract media information from ffprobe format
        format_data = ffprobe_data.get("format", {})
        streams_data = ffprobe_data.get("streams", [])

        # Get video stream info
        video_stream = next(
            (
                stream
                for stream in streams_data
                if stream.get("codec_type") == "video"
            ),
            {},
        )

        # Get audio streams info
        audio_streams = [
            stream for stream in streams_data if stream.get("codec_type") == "audio"
        ]

        # Get subtitle streams info
        subtitle_streams = [
            stream
            for stream in streams_data
            if stream.get("codec_type") == "subtitle"
        ]

        # Extract video metadata
        video_duration = 0
        video_quality = ""
        video_codec = ""
        video_format = ""
        video_framerate = ""

        # Extract audio metadata
        audio_languages = []
        audio_codecs = []

        # Extract subtitle metadata
        subtitle_languages = []

        # Process format data (equivalent to general track in ffprobe)
        if format_data:
            # Get file format
            video_format = format_data.get("format_name", "")

            # Get duration
            if "duration" in format_data:
                try:
                    duration_str = format_data["duration"]
                    # Check if duration is in HH:MM:SS format
                    if ":" in duration_str:
                        # Split by colon and handle different formats
                        parts = duration_str.split(":")
                        if len(parts) == 3:
                            # HH:MM:SS format
                            hours, minutes, seconds = map(float, parts)
                            video_duration = int(
                                hours * 3600 + minutes * 60 + seconds
                            )
                        elif len(parts) == 2:
                            # MM:SS format
                            minutes, seconds = map(float, parts)
                            video_duration = int(minutes * 60 + seconds)
                        elif len(parts) == 1:
                            # SS format
                            seconds = float(parts[0])
                            video_duration = int(seconds)
                    else:
                        # Try to parse as a float directly (seconds)
                        video_duration = int(float(duration_str))
                except Exception as e:
                    LOGGER.error(f"Error parsing duration: {e}")

        # Process video stream
        if video_stream:
            # Get video codec
            video_codec = video_stream.get("codec_name", "")

            # Get video quality
            if "height" in video_stream:
                height = video_stream["height"]
                if isinstance(height, str) and " " in height:
                    height = height.split(" ")[0]
                try:
                    height = int(float(height))
                    if height >= 2160:
                        video_quality = "4K"
                    elif height >= 1440:
                        video_quality = "2K"
                    elif height >= 1080:
                        video_quality = "1080p"
                    elif height >= 720:
                        video_quality = "720p"
                    elif height >= 480:
                        video_quality = "480p"
                    elif height >= 360:
                        video_quality = "360p"
                    else:
                        video_quality = f"{height}p"
                except Exception as e:
                    LOGGER.error(f"Error parsing video height: {e}")
                    video_quality = "Unknown"

            # Get framerate
            if "r_frame_rate" in video_stream:
                try:
                    framerate_str = video_stream["r_frame_rate"]
                    if "/" in framerate_str:
                        num, den = framerate_str.split("/")
                        framerate = float(num) / float(den)
                    else:
                        framerate = float(framerate_str)
                    video_framerate = f"{framerate:.2f} fps"
                except Exception as e:
                    LOGGER.error(f"Error parsing framerate: {e}")
                    video_framerate = video_stream.get("r_frame_rate", "")

        # Process audio streams
        for audio_stream in audio_streams:
            # Get audio language
            language = "Unknown"
            if "tags" in audio_stream and "language" in audio_stream["tags"]:
                try:
                    lang_code = audio_stream["tags"]["language"]
                    language = Language.get(lang_code).display_name()
                except Exception:
                    language = audio_stream["tags"]["language"]

            # Get audio codec
            audio_codec = audio_stream.get("codec_name", "")

            # Add to lists
            audio_languages.append(language)
            audio_codecs.append(audio_codec)

        # Process subtitle streams
        for subtitle_stream in subtitle_streams:
            # Get subtitle language
            language = "Unknown"
            if "tags" in subtitle_stream and "language" in subtitle_stream["tags"]:
                try:
                    lang_code = subtitle_stream["tags"]["language"]
                    language = Language.get(lang_code).display_name()
                except Exception:
                    language = subtitle_stream["tags"]["language"]

            # Add to list
            subtitle_languages.append(language)

        # Format metadata for caption
        audio_languages_str = (
            ", ".join(audio_languages) if audio_languages else "Unknown"
        )
        subtitle_languages_str = (
            ", ".join(subtitle_languages) if subtitle_languages else "Unknown"
        )
        audio_codecs_str = ", ".join(audio_codecs) if audio_codecs else "Unknown"

        # Calculate MD5 hash for the file (first 10MB only for speed)
        try:
            file_md5_hash = await calculate_md5(file_path)
        except Exception as e:
            LOGGER.error(f"Error calculating MD5 hash: {e}")
            file_md5_hash = "Unknown"

        # Get file size safely
        try:
            file_size = await aiopath.getsize(file_path)
            readable_size = get_readable_file_size(file_size)
        except Exception as e:
            LOGGER.error(f"Error getting file size: {e}")
            readable_size = "Unknown"

        # Extract metadata from filename
        from bot.helper.ext_utils.template_processor import (
            extract_metadata_from_filename,
        )

        filename_metadata = await extract_metadata_from_filename(
            os.path.splitext(filename)[0]
        )

        # Count number of streams
        num_videos = 1 if video_stream else 0
        num_audios = len(audio_streams)
        num_subtitles = len(subtitle_streams)

        # Format track counts with leading zeros for single digits
        num_videos_str = f"{num_videos:02d}" if num_videos < 10 else str(num_videos)
        num_audios_str = f"{num_audios:02d}" if num_audios < 10 else str(num_audios)
        num_subtitles_str = (
            f"{num_subtitles:02d}" if num_subtitles < 10 else str(num_subtitles)
        )

        # Generate a unique ID for the file
        # MD5 hash is already a string, so no conversion needed
        file_id = file_md5_hash[:8]

        # Format extension in uppercase
        format_upper = os.path.splitext(filename)[1][1:].upper()

        # Create HTML-formatted filename with proper prefix/suffix spacing for captions
        os.path.splitext(filename)[0]
        os.path.splitext(filename)[1]  # Include the dot

        def create_html_filename_for_caption(
            clean_filename, html_prefix=None, html_suffix=None
        ):
            """
            Create HTML-formatted filename for captions with proper spacing.
            - Space after prefix
            - Space before suffix
            - Suffix applied before extension (handles split files correctly)
            """
            import re

            # Handle split files correctly (.ext.001, .part001.ext)
            if re.match(r"(.+)(\.\w+)(\.\d{3})$", clean_filename):
                # For .ext.001 files: name.ext.001 -> name, .ext.001
                match = re.match(r"(.+)(\.\w+)(\.\d{3})$", clean_filename)
                name_without_ext, ext, split_num = match.groups()
                full_ext = f"{ext}{split_num}"
            elif re.match(r"(.+)(\.part\d+)(\..+)$", clean_filename):
                # For .part001.ext files: name.part001.ext -> name, .part001.ext
                match = re.match(r"(.+)(\.part\d+)(\..+)$", clean_filename)
                name_without_ext, part_num, ext = match.groups()
                full_ext = f"{part_num}{ext}"
            else:
                # Regular files: name.ext -> name, .ext
                name_without_ext = os.path.splitext(clean_filename)[0]
                full_ext = os.path.splitext(clean_filename)[1]

            # Build the caption filename with proper spacing
            caption_filename = name_without_ext

            # Add HTML prefix with space after it (for captions)
            if html_prefix:
                caption_filename = f"{html_prefix} {caption_filename}"

            # Add HTML suffix with space before it and before extension (for captions)
            if html_suffix:
                caption_filename = f"{caption_filename} {html_suffix}"

            # Add extension back
            return f"{caption_filename}{full_ext}"

        html_filename = create_html_filename_for_caption(
            filename, html_prefix, html_suffix
        )

        # Create filename with prefix/suffix applied (for templates using {filename}.{ext})
        # The suffix should be applied before the extension, so we modify the filename
        # to include the suffix, and keep the extension separate
        import re

        # Handle split files correctly for template variables
        if re.match(r"(.+)(\.\w+)(\.\d{3})$", filename):
            # For .ext.001 files: name.ext.001 -> name, ext (without dot), 001
            match = re.match(r"(.+)(\.\w+)(\.\d{3})$", filename)
            base_name, ext_with_dot, split_num = match.groups()
            filename_with_prefix_suffix = base_name
            ext_without_dot = ext_with_dot[1:]  # Remove dot from extension
        elif re.match(r"(.+)(\.part\d+)(\..+)$", filename):
            # For .part001.ext files: name.part001.ext -> name, ext (without dot)
            match = re.match(r"(.+)(\.part\d+)(\..+)$", filename)
            base_name, part_num, ext_with_dot = match.groups()
            filename_with_prefix_suffix = base_name
            ext_without_dot = ext_with_dot[1:]  # Remove dot from extension
        else:
            # Regular files: name.ext -> name, ext (without dot)
            filename_with_prefix_suffix = os.path.splitext(filename)[0]
            ext_without_dot = os.path.splitext(filename)[1][
                1:
            ]  # Extension without dot

        if html_prefix or html_suffix:
            if html_prefix:
                filename_with_prefix_suffix = (
                    f"{html_prefix} {filename_with_prefix_suffix}"
                )
            if html_suffix:
                # Apply suffix to the filename part (before extension)
                filename_with_prefix_suffix = (
                    f"{filename_with_prefix_suffix} {html_suffix}"
                )

        # Create caption data dictionary
        caption_data = DefaultDict(
            # Basic variables
            filename=filename_with_prefix_suffix,  # Filename with prefix/suffix applied (without extension)
            html_filename=html_filename,  # HTML-formatted filename for captions (with prefix/suffix and proper spacing)
            size=readable_size,
            duration=get_readable_time(video_duration, True),
            quality=video_quality or filename_metadata.get("quality", ""),
            audios=audio_languages_str,
            audio_codecs=audio_codecs_str,
            subtitles=subtitle_languages_str,
            md5_hash=file_md5_hash,
            ext=ext_without_dot,  # Extension without dot (suffix is applied to filename)
            # TV Show variables
            season=filename_metadata.get("season", ""),
            episode=filename_metadata.get("episode", ""),
            year=filename_metadata.get("year", ""),
            # Media Information
            NumVideos=num_videos_str,
            NumAudios=num_audios_str,
            NumSubtitles=num_subtitles_str,
            formate=format_upper,  # Intentional spelling to match documentation
            format=video_format,
            id=file_id,
            framerate=video_framerate or filename_metadata.get("framerate", ""),
            codec=video_codec or filename_metadata.get("codec", ""),
        )

        # Create a cleaned version of the caption data for template processing
        # This ensures all values are strings and handles None values
        cleaned_caption_data = {}
        for key, value in caption_data.items():
            if value is None:
                cleaned_caption_data[key] = "Unknown"
            else:
                cleaned_caption_data[key] = str(value)

        # First try the advanced template processor for Google Fonts and nested variables
        try:
            processed_caption = await process_template(
                caption_template, cleaned_caption_data
            )
            # Clean up empty lines and format the caption
            processed_caption = clean_caption(processed_caption)

            # Force garbage collection after processing media info
            # This can create large objects in memory
            if smart_garbage_collection:
                # Use aggressive collection for media info processing
                smart_garbage_collection(aggressive=True)
            else:
                # Collect all generations for thorough cleanup
                gc.collect(0)
                gc.collect(1)
                gc.collect(2)
            return processed_caption
        except Exception as e:
            LOGGER.error(f"Error processing template with advanced processor: {e}")
            # Try to recover by removing problematic parts
            try:
                # Remove nested templates that might be causing issues
                simplified_template = re.sub(r"{{+.*?}+", "", caption_template)
                processed_caption = await process_template(
                    simplified_template, cleaned_caption_data
                )
                return clean_caption(processed_caption)

            except Exception as e2:
                LOGGER.error(f"Error recovering with simplified template: {e2}")
                # Fall back to the simple format_map method if advanced processing fails
                try:
                    # Create a custom format string that skips empty variables
                    custom_template = caption_template
                    for key, value in caption_data.items():
                        if not value or not str(value).strip():
                            # Replace the variable and its line if it's on its own line
                            pattern = rf"^.*{{{key}}}.*$\n?"
                            custom_template = re.sub(
                                pattern, "", custom_template, flags=re.MULTILINE
                            )
                            # Replace the variable if it's part of a line
                            custom_template = custom_template.replace(
                                f"{{{key}}}", ""
                            )

                    # Format the template with the data
                    processed_caption = custom_template.format_map(caption_data)
                    # Clean up empty lines and format the caption
                    return clean_caption(processed_caption)

                except Exception as e:
                    LOGGER.error(
                        f"Error processing template with simple processor: {e}"
                    )
                    # If all else fails, return a basic formatted caption
                    return f"<code>{filename}</code>\n<b>Size:</b> {cleaned_caption_data.get('size', 'Unknown')}"
    except Exception as e:
        LOGGER.error(f"Error generating caption: {e}")
        # Return a basic formatted caption instead of just the filename
        return f"<code>{filename}</code>"
    finally:
        # No cleanup needed since we're using the original file directly
        pass
