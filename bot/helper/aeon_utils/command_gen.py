import asyncio
import contextlib
import json
import os
import os.path

import aiohttp

from bot import LOGGER, cpu_no
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.media_utils import get_streams


async def download_google_font(font_name):
    """Download a font from Google Fonts API.

    Args:
        font_name: Name of the Google Font to download

    Returns:
        str: Path to the downloaded font file or default font if download fails
    """
    try:
        # Create fonts directory if it doesn't exist
        os.makedirs("fonts", exist_ok=True)

        # Check if font already exists
        font_path = f"fonts/{font_name}.ttf"
        if os.path.exists(font_path):
            return font_path

        # Format the font name for the Google Fonts API URL
        api_font_name = font_name.replace(" ", "+")
        font_url = (
            f"https://fonts.googleapis.com/css2?family={api_font_name}&display=swap"
        )

        async with aiohttp.ClientSession() as session:
            # Get the CSS file which contains the font URL
            async with session.get(
                font_url, headers={"User-Agent": "Mozilla/5.0"}
            ) as response:
                if response.status != 200:
                    LOGGER.error(
                        f"Failed to fetch Google Font CSS for {font_name}: {response.status}"
                    )
                    return "default.otf"

                css = await response.text()

                # Extract the font URL from the CSS
                font_url_start = css.find("src: url(")
                if font_url_start == -1:
                    LOGGER.error(f"Could not find font URL in CSS for {font_name}")
                    return "default.otf"

                font_url_start += 9  # Length of "src: url("
                font_url_end = css.find(")", font_url_start)
                font_url = css[font_url_start:font_url_end]

                # Download the font file
                async with session.get(font_url) as font_response:
                    if font_response.status != 200:
                        LOGGER.error(
                            f"Failed to download font file for {font_name}: {font_response.status}"
                        )
                        return "default.otf"

                    with open(font_path, "wb") as f:
                        f.write(await font_response.read())

                    LOGGER.info(f"Successfully downloaded Google Font: {font_name}")
                    return font_path
    except Exception as e:
        LOGGER.error(f"Error downloading Google Font {font_name}: {e!s}")
        return "default.otf"


async def get_image_watermark_cmd(
    file,
    watermark_image_path,
    position="top_left",
    scale=10,  # Default scale is 10% of video width
    opacity=1.0,
    quality=None,
    speed=None,
    remove_original=False,
    watermark_type="image",  # Always "image" for this function, but included for compatibility
):
    """Generate FFmpeg command for adding image watermark to media files.

    Args:
        file: Path to the input file
        watermark_image_path: Path to the watermark image
        position: Position of watermark (top_left, top_right, bottom_left, bottom_right, center, etc.)
        scale: Scale of watermark as percentage of video width (1-100)
        opacity: Opacity of watermark (0.0-1.0)
        quality: Quality setting for encoding
        speed: Speed setting for encoding
        remove_original: Whether to remove original file after processing

    Returns:
        tuple: FFmpeg command and temporary output file path, or None, None if not supported
    """
    # Import the function to determine media type
    from bot.helper.ext_utils.bot_utils import cmd_exec
    from bot.helper.ext_utils.media_utils import get_media_type_for_watermark

    # Check if watermark image exists
    if not os.path.exists(watermark_image_path):
        LOGGER.error(f"Watermark image not found: {watermark_image_path}")
        return None, None

    # Determine the media type
    media_type = await get_media_type_for_watermark(file)
    if not media_type:
        return None, None

    # Handle "none" values for parameters
    if position and position.lower() == "none":
        position = "top_left"  # Default position

    if scale == 0 or (isinstance(scale, str) and scale.lower() == "none"):
        scale = 10  # Default scale (10% of video width)

    if opacity == 0.0 or (isinstance(opacity, str) and opacity.lower() == "none"):
        opacity = 1.0  # Default opacity

    # Determine output file extension based on input file first
    file_ext = os.path.splitext(file)[1].lower()

    # For videos, always use .mkv as temp extension for maximum compatibility
    if media_type == "video":
        temp_file = f"{file}.temp.mkv"
    elif media_type == "audio":
        # For audio files, preserve the original extension
        temp_file = f"{file}.temp{file_ext}"
    elif media_type == "subtitle":
        # For subtitle files, preserve the original extension
        temp_file = f"{file}.temp{file_ext}"
    else:
        # For images, preserve the original extension
        temp_file = f"{file}.temp{file_ext}"

    # Check if file dimensions are divisible by 2 for video files
    width = 0
    height = 0

    if media_type == "video":
        try:
            # Use ffprobe to get dimensions
            probe_cmd = [
                "ffprobe",  # Keep as ffprobe, not xtra
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                file,
            ]

            # Execute the command
            stdout, _, code = await cmd_exec(probe_cmd)

            if code == 0 and stdout.strip():
                try:
                    data = json.loads(stdout)
                    if data.get("streams"):
                        width = int(data["streams"][0].get("width", 0))
                        height = int(data["streams"][0].get("height", 0))
                except json.JSONDecodeError as e:
                    LOGGER.error(f"Failed to parse ffprobe JSON output: {e}")
                    # Continue with default dimensions (0, 0)

        except Exception:
            # Continue with default dimensions if probe fails
            pass

    # Set position coordinates based on position parameter
    # For overlay filter, we need to calculate the exact position
    if position == "top_left":
        overlay_position = "10:10"
    elif position == "top_right":
        overlay_position = "W-w-10:10"
    elif position == "bottom_left":
        overlay_position = "10:H-h-10"
    elif position == "bottom_right":
        overlay_position = "W-w-10:H-h-10"
    elif position == "center":
        overlay_position = "(W-w)/2:(H-h)/2"
    elif position == "top_center":
        overlay_position = "(W-w)/2:10"
    elif position == "bottom_center":
        overlay_position = "(W-w)/2:H-h-10"
    elif position == "left_center":
        overlay_position = "10:(H-h)/2"
    elif position == "right_center":
        overlay_position = "W-w-10:(H-h)/2"
    else:  # Default to top_left if invalid position
        overlay_position = "10:10"

    # Base command for all media types
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file,
        "-i",
        watermark_image_path,
        "-ignore_unknown",
    ]

    # Check if speed parameter is provided
    file_size = os.path.getsize(file)
    large_file_threshold = 100 * 1024 * 1024  # 100MB

    # If speed is provided as a numerical value, use it directly
    # Otherwise, use a default approach based on file size
    use_fast_mode = False
    if speed is not None and str(speed).lower() != "none":
        # Speed parameter provided - will be used directly in the command
        pass
    else:
        # No speed parameter - use default approach
        use_fast_mode = file_size > large_file_threshold

    # Use default thread count
    thread_count = max(1, cpu_no // 2)

    # Create the overlay filter with scaling and opacity
    # Scale the watermark image based on the scale parameter (percentage of video width)
    # We need to use different approaches for different media types
    if media_type == "video":
        # For videos, we can use scale2ref which is more accurate
        scale_filter = ""  # We'll use scale2ref in the complex filter
    else:
        # For images and animated images, we need to use a fixed scale
        # Get the dimensions of the input file using cached media info if possible
        try:
            # Use ffprobe to get dimensions - this will use the cache if available
            from bot.helper.ext_utils.media_utils import get_streams

            # Get streams using the cached function
            streams = await get_streams(file)

            if streams:
                # Find the first video stream
                for stream in streams:
                    if stream.get("codec_type") == "video":
                        width = int(stream.get("width", 0))
                        height = int(stream.get("height", 0))

                        if width > 0 and height > 0:
                            # Calculate the scale factor based on the width
                            scale_factor = max(1, int(width * scale / 100))
                            # Use lanczos scaling for better quality
                            scale_filter = (
                                f"[1:v]scale={scale_factor}:-1:flags=lanczos"
                            )
                            break
                else:
                    # No video stream found, use default
                    scale_filter = f"[1:v]scale=iw*{scale}/100:-1:flags=lanczos"
            else:
                # Fallback to a reasonable default
                scale_filter = f"[1:v]scale=iw*{scale}/100:-1:flags=lanczos"
        except Exception as e:
            LOGGER.error(f"Error getting dimensions: {e}")
            # Fallback to a reasonable default
            scale_filter = f"[1:v]scale=iw*{scale}/100:-1:flags=lanczos"

    # Add opacity if specified - combine with scale filter for better performance
    if opacity < 1.0 and scale_filter:
        scale_filter += f",format=rgba,colorchannelmixer=aa={opacity}"

    if scale_filter:
        scale_filter += "[watermark];"

    # Add media-specific parameters
    if media_type == "video":
        # For video files, use an optimized complex filter to overlay the watermark
        # Combine operations where possible to reduce filter chain complexity

        # Always ensure dimensions are even (required by some codecs)
        # Use a single filter chain with optimized operations
        if scale_filter:
            # If we already have a scale filter, use it
            complex_filter = (
                f"[0:v]scale=iw:ih,pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2[main];"
                f"{scale_filter}"
                f"[main][watermark]overlay={overlay_position}:format=auto[outv]"
            )
        else:
            # Otherwise, use scale2ref which is more accurate for videos
            # Use lanczos scaling for better quality and force even dimensions with -2
            complex_filter = (
                f"[0:v]scale=iw:ih,pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2[main];"
                f"[1:v]scale=iw*{scale}/100:-2:flags=lanczos"
            )

            # Add opacity if specified
            if opacity < 1.0:
                complex_filter += f",format=rgba,colorchannelmixer=aa={opacity}"

            complex_filter += "[watermark];"
            # Use format=auto for better performance
            complex_filter += (
                f"[main][watermark]overlay={overlay_position}:format=auto[outv]"
            )

        cmd.extend(
            [
                "-filter_complex",
                complex_filter,
                "-map",
                "[outv]",
                "-map",
                "0:a?",
                "-map",
                "0:s?",
                "-map",
                "0:t?",
                "-c:a",
                "copy",
                "-c:s",
                "copy",
            ]
        )  # Add quality settings based on quality parameter
        if quality is not None and str(quality).lower() != "none":
            # Check if quality is a string like "high", "medium", "low"
            if str(quality).lower() in ["high", "medium", "low"]:
                # Handle text-based quality values
                if str(quality).lower() == "high":
                    cmd.extend(["-crf", "18"])  # High quality
                elif str(quality).lower() == "medium":
                    cmd.extend(["-crf", "23"])  # Medium quality
                elif str(quality).lower() == "low":
                    cmd.extend(["-crf", "28"])  # Low quality
            else:
                try:
                    # Try to convert quality to integer (1-51 for x264/x265)
                    quality_val = int(quality)
                    # Ensure it's in valid range (lower is better quality)
                    quality_val = max(1, min(quality_val, 51))
                    cmd.extend(["-crf", str(quality_val)])
                except (ValueError, TypeError):
                    # If conversion fails, use a default high quality
                    cmd.extend(["-crf", "18"])  # High quality default
        else:
            # No quality specified, use a good default
            cmd.extend(["-crf", "23"])  # Default quality

        # Add speed settings based on speed parameter
        if speed is not None and str(speed).lower() != "none":
            # Valid presets: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
            valid_presets = [
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ]

            # Check if speed is a valid preset name
            if str(speed).lower() in valid_presets:
                cmd.extend(["-preset", str(speed).lower()])
            else:
                try:
                    # Try to convert speed to integer (1-9)
                    speed_val = int(speed)
                    # Map 1-9 to presets (1=ultrafast, 9=veryslow)
                    speed_val = max(1, min(speed_val, 9))
                    preset = valid_presets[speed_val - 1]
                    cmd.extend(["-preset", preset])
                except (ValueError, TypeError):
                    # If conversion fails and it's not a valid preset name, use default
                    if use_fast_mode:
                        cmd.extend(["-preset", "ultrafast"])
                    else:
                        cmd.extend(["-preset", "medium"])  # Default preset
        elif use_fast_mode:
            # No speed specified but fast mode is enabled
            cmd.extend(["-preset", "ultrafast"])

        # Add format-specific optimizations for Telegram compatibility
        temp_file_ext = os.path.splitext(temp_file)[1].lower()
        if temp_file_ext == ".mp4":
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
        elif temp_file_ext == ".mkv":
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
        elif temp_file_ext == ".webm":
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
        elif temp_file_ext == ".mov":
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

    elif media_type in ["image", "animated_image"]:
        # For images and animated images, use a simpler approach
        if scale_filter:
            # If we have a scale filter, use it
            complex_filter = (
                f"{scale_filter}[0:v][watermark]overlay={overlay_position}[outv]"
            )
        else:
            # Otherwise, create a simple filter
            complex_filter = (
                f"[1:v]scale={int(width * scale / 100) if width else 100}:-1"
            )

            # Add opacity if specified
            if opacity < 1.0:
                complex_filter += f",format=rgba,colorchannelmixer=aa={opacity}"

            complex_filter += "[watermark];"
            complex_filter += f"[0:v][watermark]overlay={overlay_position}[outv]"

        cmd.extend(
            [
                "-filter_complex",
                complex_filter,
                "-map",
                "[outv]",
            ]
        )

        # For animated images (GIFs), ensure we preserve animation
        if media_type == "animated_image":
            if file_ext.lower() == ".gif":
                # For GIF, we need a special approach to preserve transparency and animation
                # Use a different filter for GIFs
                if watermark_type == "image":
                    # For image watermarks on GIFs, we need a special approach
                    complex_filter = (
                        f"[1:v]scale={int(width * scale / 100) if width else 100}:-1"
                    )

                    # Add opacity if specified
                    if opacity < 1.0:
                        complex_filter += (
                            f",format=rgba,colorchannelmixer=aa={opacity}"
                        )

                    complex_filter += "[watermark];"
                    complex_filter += (
                        f"[0:v][watermark]overlay={overlay_position}[marked];"
                    )
                    complex_filter += "[marked]split[v1][v2];"
                    complex_filter += "[v1]palettegen=reserve_transparent=1[pal];"
                    complex_filter += "[v2][pal]paletteuse=alpha_threshold=128"

                    # Replace the previous complex filter
                    cmd = [
                        "xtra",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-progress",
                        "pipe:1",
                        "-i",
                        file,
                        "-i",
                        watermark_image_path,
                        "-ignore_unknown",
                        "-filter_complex",
                        complex_filter,
                        "-threads",
                        f"{thread_count}",
                        temp_file,
                    ]

                    # Return early since we've completely rebuilt the command
                    return cmd, temp_file
                # For regular GIFs, ensure we preserve transparency and animation
                cmd.extend(["-gifflags", "+transdiff"])

        # Add quality settings based on file type
        if file_ext in [".jpg", ".jpeg"]:
            # For JPEG, use quality parameter (1-31, lower is better)
            if quality is not None and str(quality).lower() != "none":
                try:
                    quality_val = int(quality)
                    quality_val = max(1, min(quality_val, 31))
                    cmd.extend(["-q:v", str(quality_val)])
                except (ValueError, TypeError):
                    cmd.extend(["-q:v", "2"])  # Good quality default
            else:
                cmd.extend(["-q:v", "2"])  # Good quality default
        elif file_ext in [".png", ".webp"]:
            # For PNG and WebP, use compression level
            if quality is not None and str(quality).lower() != "none":
                try:
                    quality_val = int(quality)
                    compression_val = 9 - min(9, max(0, quality_val - 1))
                    cmd.extend(["-compression_level", str(compression_val)])
                except (ValueError, TypeError):
                    cmd.extend(["-compression_level", "1"])  # Good quality default
            else:
                cmd.extend(["-compression_level", "1"])  # Good quality default
    else:
        # For audio and subtitle files, we can't add image watermarks
        LOGGER.error(
            f"Image watermarking not supported for media type: {media_type}"
        )
        return None, None

    # Add threads parameter if not already added
    if "-threads" not in cmd and media_type not in ["subtitle"]:
        cmd.extend(["-threads", f"{thread_count}", temp_file])

    return cmd, temp_file


async def get_watermark_cmd(
    file,
    key,
    position="top_left",
    size=20,
    color="white",  # Default color is white
    font="default.otf",
    maintain_quality=True,  # For backward compatibility
    opacity=1.0,
    quality=None,  # Numerical quality value instead of maintain_quality toggle
    speed=None,  # Numerical speed value instead of fast_mode toggle
    audio_watermark_enabled=False,  # Whether audio watermark is enabled
    audio_watermark_text=None,  # Text for audio watermark
    audio_watermark_interval=None,  # Interval for audio watermark
    audio_watermark_volume=None,  # Volume for audio watermark
    subtitle_watermark_enabled=False,  # Whether subtitle watermark is enabled
    subtitle_watermark_text=None,  # Text for subtitle watermark
    subtitle_watermark_interval=None,  # Interval for subtitle watermark
    subtitle_watermark_style=None,  # Style for subtitle watermark
    remove_original=False,  # Whether to remove original file after processing
    watermark_type="text",  # Type of watermark: "text" or "image"
    watermark_image_path=None,  # Path to watermark image for image watermarks
    watermark_scale=10,  # Scale of watermark image (percentage of video width)
):
    """Generate FFmpeg command for adding watermark to media files with improved handling.

    Args:
        file: Path to the input file
        key: Watermark text
        position: Position of watermark (top_left, top_right, bottom_left, bottom_right, center, etc.)
        size: Font size
        color: Font color
        font: Font file name or Google Font name
        speed: Speed setting for encoding (replaces fast_mode)
        maintain_quality: Whether to maintain original quality
        opacity: Opacity of watermark (0.0-1.0)
        watermark_type: Type of watermark: "text" or "image"
        watermark_image_path: Path to watermark image for image watermarks
        watermark_scale: Scale of watermark image (percentage of video width)

    Returns:
        tuple: FFmpeg command and temporary output file path, or None, None if not supported
    """
    # Import the function to determine media type
    # Resource manager removed
    from bot.helper.ext_utils.bot_utils import cmd_exec
    from bot.helper.ext_utils.media_utils import get_media_type_for_watermark

    # Check if we should use image watermark
    if watermark_type.lower() == "image" and watermark_image_path:
        # Use the image watermark function
        return await get_image_watermark_cmd(
            file=file,
            watermark_image_path=watermark_image_path,
            position=position,
            scale=watermark_scale,
            opacity=opacity,
            quality=quality,
            speed=speed,
            remove_original=remove_original,
        )

    # Continue with text watermark if not using image watermark
    # Determine the media type
    media_type = await get_media_type_for_watermark(file)
    if not media_type:
        return None, None

    # Handle "none" values for parameters
    if position and position.lower() == "none":
        position = "top_left"  # Default position

    if size == 0 or (isinstance(size, str) and size.lower() == "none"):
        size = 20  # Default size

    if color and color.lower() == "none":
        color = "white"  # Default color

    if font and font.lower() == "none":
        font = "default.otf"  # Default font

    if opacity == 0.0 or (isinstance(opacity, str) and opacity.lower() == "none"):
        opacity = 1.0  # Default opacity

    # Determine output file extension based on input file first
    file_ext = os.path.splitext(file)[1].lower()

    # For videos, always use .mkv as temp extension for maximum compatibility
    if media_type == "video":
        temp_file = f"{file}.temp.mkv"
    elif media_type == "audio":
        # For audio files, preserve the original extension
        temp_file = f"{file}.temp{file_ext}"
    elif media_type == "subtitle":
        # For subtitle files, preserve the original extension
        temp_file = f"{file}.temp{file_ext}"
    else:
        # For images, preserve the original extension
        temp_file = f"{file}.temp{file_ext}"

    # Check if file dimensions are divisible by 2 for video files
    needs_padding = True  # Always use padding for safety
    width = 0
    height = 0

    if media_type == "video":
        try:
            # Use ffprobe to get dimensions
            probe_cmd = [
                "ffprobe",  # Keep as ffprobe, not xtra
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                file,
            ]

            # Execute the command
            stdout, stderr, code = await cmd_exec(probe_cmd)

            if code == 0 and stdout.strip():
                try:
                    data = json.loads(stdout)
                    if data.get("streams"):
                        width = int(data["streams"][0].get("width", 0))
                        height = int(data["streams"][0].get("height", 0))

                        # Check if dimensions are divisible by 2
                        if width % 2 != 0 or height % 2 != 0:
                            needs_padding = True
                        else:
                            needs_padding = False
                except json.JSONDecodeError as e:
                    LOGGER.error(f"Failed to parse ffprobe JSON output: {e}")
                    # Continue with default padding
            else:
                LOGGER.warning(
                    f"Failed to get video dimensions for {file}: {stderr}"
                )

        except Exception as e:
            LOGGER.warning(f"Error getting video dimensions for {file}: {e}")

    # Check if font is a Google Font or a local file
    if font.endswith((".ttf", ".otf")):
        font_path = font
    else:
        # Assume it's a Google Font name and try to download it
        font_path = await download_google_font(font)

    # Set position coordinates based on position parameter
    if position == "top_left":
        x_pos, y_pos = "10", "10"
    elif position == "top_right":
        x_pos, y_pos = "w-tw-10", "10"
    elif position == "bottom_left":
        x_pos, y_pos = "10", "h-th-10"
    elif position == "bottom_right":
        x_pos, y_pos = "w-tw-10", "h-th-10"
    elif position == "center":
        x_pos, y_pos = "(w-tw)/2", "(h-th)/2"
    elif position == "top_center":
        x_pos, y_pos = "(w-tw)/2", "10"
    elif position == "bottom_center":
        x_pos, y_pos = "(w-tw)/2", "h-th-10"
    elif position == "left_center":
        x_pos, y_pos = "10", "(h-th)/2"
    elif position == "right_center":
        x_pos, y_pos = "w-tw-10", "(h-th)/2"
    else:  # Default to top_left if invalid position
        x_pos, y_pos = "10", "10"

    # Create the drawtext filter with shadow for better visibility
    # Add a shadow effect to make text more readable on any background

    # This is already handled above, so this check is redundant
    # Just ensure color is not None for the rest of the function
    if color is None:
        color = "white"

    shadow_color = "black" if color.lower() != "black" else "white"
    drawtext_filter = (
        f"drawtext=text='{key}':fontfile={font_path}:fontsize={size}:"
        f"fontcolor={color}:x={x_pos}:y={y_pos}:shadowcolor={shadow_color}:shadowx=1:shadowy=1"
    )

    # Add opacity if specified
    if opacity < 1.0:
        drawtext_filter += f":alpha={opacity}"

    # Base command for all media types
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file,
        "-ignore_unknown",
    ]

    # Check if speed parameter is provided
    file_size = os.path.getsize(file)
    large_file_threshold = 100 * 1024 * 1024  # 100MB

    # If speed is provided as a numerical value, use it directly
    # Otherwise, use a default approach based on file size
    use_fast_mode = False
    if speed is not None and str(speed).lower() != "none":
        # Speed parameter provided - will be used directly in the command
        pass
    else:
        # No speed parameter - use default approach
        use_fast_mode = file_size > large_file_threshold

    # Use default thread count
    thread_count = max(1, cpu_no // 2)

    # Add media-specific parameters
    if media_type == "video":
        # For video files - use a simpler approach that selects only the main video stream
        # This avoids issues with multiple video streams with odd dimensions

        # First, select only the main video stream (usually the first one)
        cmd.extend(["-map", "0:v:0"])

        # Add the watermark filter with padding if needed
        # Optimize filter chain by combining operations
        if needs_padding:
            # Use a single filter operation instead of multiple chained ones
            cmd.extend(
                [
                    "-vf",
                    f"scale=iw:ih,pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2,{drawtext_filter}",
                ]
            )
        else:
            cmd.extend(["-vf", drawtext_filter])

        # Map audio and subtitle streams
        cmd.extend(["-map", "0:a?", "-map", "0:s?", "-map", "0:t?"])

        # Copy audio and subtitle streams
        cmd.extend(
            ["-c:a", "copy", "-c:s", "copy"]
        )  # Add quality settings based on quality parameter
        if quality is not None and str(quality).lower() != "none":
            # Check if quality is a string like "high", "medium", "low"
            if str(quality).lower() in ["high", "medium", "low"]:
                # Handle text-based quality values
                if str(quality).lower() == "high":
                    cmd.extend(["-crf", "18"])  # High quality
                elif str(quality).lower() == "medium":
                    cmd.extend(["-crf", "23"])  # Medium quality
                elif str(quality).lower() == "low":
                    cmd.extend(["-crf", "28"])  # Low quality
            else:
                try:
                    # Try to convert quality to integer (1-51 for x264/x265)
                    quality_val = int(quality)
                    # Ensure it's in valid range (lower is better quality)
                    quality_val = max(1, min(quality_val, 51))
                    cmd.extend(["-crf", str(quality_val)])
                except (ValueError, TypeError):
                    # If conversion fails, use a default high quality
                    cmd.extend(["-crf", "18"])  # High quality default
        else:
            # No quality specified, use a good default
            cmd.extend(["-crf", "23"])  # Default quality

        # Add speed settings based on speed parameter
        if speed is not None and str(speed).lower() != "none":
            # Valid presets: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
            valid_presets = [
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ]

            # Check if speed is a valid preset name
            if str(speed).lower() in valid_presets:
                cmd.extend(["-preset", str(speed).lower()])
            else:
                try:
                    # Try to convert speed to integer (1-9)
                    speed_val = int(speed)
                    # Map 1-9 to presets (1=ultrafast, 9=veryslow)
                    speed_val = max(1, min(speed_val, 9))
                    preset = valid_presets[speed_val - 1]
                    cmd.extend(["-preset", preset])
                except (ValueError, TypeError):
                    # If conversion fails and it's not a valid preset name, use default
                    if use_fast_mode:
                        cmd.extend(["-preset", "ultrafast"])
                    else:
                        cmd.extend(["-preset", "medium"])  # Default preset
        elif use_fast_mode:
            # No speed specified but fast mode is enabled
            cmd.extend(["-preset", "ultrafast"])

        # Add format-specific optimizations for Telegram compatibility
        temp_file_ext = os.path.splitext(temp_file)[1].lower()
        if temp_file_ext == ".mp4":
            cmd.extend(
                [
                    "-c:v",
                    "libx264",  # Ensure H.264 codec
                    "-movflags",
                    "+faststart",  # Streaming optimization
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-profile:v",
                    "main",  # Compatible H.264 profile
                    "-level",
                    "4.0",  # Compatible H.264 level
                    "-crf",
                    "23",  # Good quality/size balance
                ]
            )
        elif temp_file_ext == ".mkv":
            cmd.extend(
                [
                    "-c:v",
                    "libx264",  # Ensure H.264 codec for compatibility
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-disposition:v:0",
                    "default",  # Set video as default
                    "-disposition:a:0",
                    "default",  # Set audio as default
                    "-crf",
                    "23",  # Good quality
                ]
            )
        elif temp_file_ext == ".webm":
            cmd.extend(
                [
                    "-c:v",
                    "libvpx-vp9",  # Use VP9 codec
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-deadline",
                    "good",  # VP9 optimization
                    "-cpu-used",
                    "2",  # VP9 speed/quality balance
                    "-row-mt",
                    "1",  # VP9 multithreading
                    "-crf",
                    "30",  # VP9 quality
                    "-b:v",
                    "0",  # Variable bitrate
                ]
            )
        elif temp_file_ext == ".mov":
            cmd.extend(
                [
                    "-c:v",
                    "libx264",  # Ensure H.264 codec
                    "-movflags",
                    "+faststart",  # Streaming optimization (MOV uses same structure as MP4)
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-profile:v",
                    "main",  # Compatible H.264 profile
                    "-level",
                    "4.0",  # Compatible H.264 level
                    "-crf",
                    "23",  # Good quality
                ]
            )
        else:
            # Universal compatibility for other formats
            cmd.extend(
                [
                    "-c:v",
                    "libx264",  # Use H.264 for maximum compatibility
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-crf",
                    "23",  # Good quality
                ]
            )

    elif media_type == "image":
        # For static images, use the drawtext filter with appropriate output format
        # Use quality parameter if provided
        if file_ext in [".jpg", ".jpeg"]:
            # For JPEG, use quality parameter (1-31, lower is better)
            if quality is not None and str(quality).lower() != "none":
                try:
                    # Try to convert quality to integer (1-31 for JPEG)
                    quality_val = int(quality)
                    # Ensure it's in valid range (lower is better quality for JPEG)
                    quality_val = max(1, min(quality_val, 31))
                    cmd.extend(
                        [
                            "-vf",
                            drawtext_filter,
                            "-q:v",
                            str(quality_val),
                            "-threads",
                            f"{thread_count}",
                            temp_file,
                        ]
                    )
                except (ValueError, TypeError):
                    # If conversion fails, use a default high quality
                    cmd.extend(
                        [
                            "-vf",
                            drawtext_filter,
                            "-q:v",
                            "1",  # Highest quality (1-31, lower is better)
                            "-threads",
                            f"{thread_count}",
                            temp_file,
                        ]
                    )
            else:
                # No quality specified, use a good default
                cmd.extend(
                    [
                        "-vf",
                        drawtext_filter,
                        "-q:v",
                        "2",  # Good quality default
                        "-threads",
                        f"{thread_count}",
                        temp_file,
                    ]
                )
        elif file_ext in [".png", ".webp"]:
            # For PNG and WebP, use compression level (0-9, lower is better quality)
            if quality is not None and str(quality).lower() != "none":
                try:
                    # Try to convert quality to integer (0-9 for PNG/WebP)
                    quality_val = int(quality)
                    # For PNG/WebP, map 1-10 quality to 0-9 compression (reverse scale)
                    # 1=highest quality (0 compression), 10=lowest quality (9 compression)
                    compression_val = 9 - min(9, max(0, quality_val - 1))
                    cmd.extend(
                        [
                            "-vf",
                            drawtext_filter,
                            "-compression_level",
                            str(compression_val),
                            "-threads",
                            f"{thread_count}",
                            temp_file,
                        ]
                    )
                except (ValueError, TypeError):
                    # If conversion fails, use a default high quality
                    cmd.extend(
                        [
                            "-vf",
                            drawtext_filter,
                            "-compression_level",
                            "0",  # Lossless compression
                            "-threads",
                            f"{thread_count}",
                            temp_file,
                        ]
                    )
            else:
                # No quality specified, use a good default
                cmd.extend(
                    [
                        "-vf",
                        drawtext_filter,
                        "-compression_level",
                        "1",  # Good quality default
                        "-threads",
                        f"{thread_count}",
                        temp_file,
                    ]
                )
        # For other image formats, use general quality settings
        elif quality is not None and str(quality).lower() != "none":
            try:
                # Try to convert quality to integer (1-31, lower is better)
                quality_val = int(quality)
                # Ensure it's in valid range
                quality_val = max(1, min(quality_val, 31))
                cmd.extend(
                    [
                        "-vf",
                        drawtext_filter,
                        "-q:v",
                        str(quality_val),
                        "-threads",
                        f"{thread_count}",
                        temp_file,
                    ]
                )
            except (ValueError, TypeError):
                # If conversion fails, use a default high quality
                cmd.extend(
                    [
                        "-vf",
                        drawtext_filter,
                        "-q:v",
                        "2",  # High quality
                        "-threads",
                        f"{thread_count}",
                        temp_file,
                    ]
                )
        else:
            # No quality specified, use a good default
            cmd.extend(
                [
                    "-vf",
                    drawtext_filter,
                    "-q:v",
                    "3",  # Good quality default
                    "-threads",
                    f"{thread_count}",
                    temp_file,
                ]
            )
    elif media_type == "animated_image":
        # For animated images (GIFs), we need to use a different approach
        # The issue with the previous approach was that we can't use both -vf and -lavfi
        # Instead, we'll incorporate the drawtext filter into the complex filtergraph

        # Create an optimized complex filtergraph that includes both the watermark and palette generation
        # Combine operations where possible to reduce filter chain complexity
        complex_filter = (
            f"[0:v]scale=iw:ih:flags=lanczos,pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2,{drawtext_filter}[marked];"
            f"[marked]split[v1][v2];"
            f"[v1]palettegen=reserve_transparent=1:max_colors=256[pal];"
            f"[v2][pal]paletteuse=dither=sierra2_4a:alpha_threshold=128"
        )

        cmd.extend(
            [
                "-lavfi",
                complex_filter,
                "-threads",
                f"{thread_count}",
                temp_file,
            ]
        )
    elif media_type == "audio":
        # For audio files, we'll add a voice watermark using FFmpeg's built-in sine tone
        # This adds a beep sound at specified intervals with the watermark text

        # Get audio duration
        try:
            audio_info_cmd = [
                "ffprobe",  # Keep as ffprobe, not xtra
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                file,
            ]
            stdout, stderr, code = await cmd_exec(audio_info_cmd)
            duration = 10  # Default duration if we can't determine

            if code == 0 and stdout.strip():
                try:
                    data = json.loads(stdout)
                    if data.get("format") and data["format"].get("duration"):
                        duration = float(data["format"]["duration"])
                except json.JSONDecodeError as e:
                    LOGGER.error(
                        f"Failed to parse ffprobe JSON output for duration: {e}"
                    )
                    # Keep default duration of 10
            else:
                LOGGER.warning(f"Failed to get audio duration for {file}: {stderr}")

            # Use the key as the watermark text
            watermark_text = key

            # Determine beep parameters based on position and color
            beep_frequency = 1000  # Default frequency in Hz
            beep_duration = 0.5  # Default duration in seconds

            # Use the audio_watermark_volume parameter if provided, otherwise use default
            from bot.core.config_manager import Config

            # Use provided audio_watermark_volume if available
            if (
                audio_watermark_volume is not None
                and str(audio_watermark_volume).lower() != "none"
            ):
                try:
                    # Try to convert to float (0.0-1.0)
                    volume_val = float(audio_watermark_volume)
                    # Ensure it's in valid range
                    beep_volume = max(0.1, min(volume_val, 1.0))
                except (ValueError, TypeError):
                    # If conversion fails, use a default volume
                    beep_volume = 0.3
            else:
                # Use config value if available, otherwise default
                beep_volume = (
                    Config.AUDIO_WATERMARK_VOLUME
                    if hasattr(Config, "AUDIO_WATERMARK_VOLUME")
                    else 0.3
                )

            # Adjust parameters based on position
            if position in ["top_left", "top_right", "top_center"]:
                beep_frequency = 1500  # Higher pitch for top positions
                beep_volume = beep_volume * 0.7  # Quieter for top positions
            elif position in ["bottom_left", "bottom_right", "bottom_center"]:
                beep_frequency = 800  # Lower pitch for bottom positions
                beep_volume = (
                    beep_volume * 1.2
                )  # Louder for bottom positions (but cap at 1.0)
                beep_volume = min(
                    beep_volume, 1.0
                )  # Ensure volume doesn't exceed 1.0
            elif position == "center":
                beep_frequency = 1200  # Medium pitch for center position
                beep_volume = (
                    beep_volume * 1.1
                )  # Slightly louder for center position
                beep_volume = min(
                    beep_volume, 1.0
                )  # Ensure volume doesn't exceed 1.0

            # Adjust parameters based on color
            if color.lower() == "red":
                beep_frequency = 1800  # Higher pitch for red
            elif color.lower() == "blue":
                beep_frequency = 600  # Lower pitch for blue
            elif color.lower() == "green":
                beep_frequency = 1200  # Medium pitch for green
            elif color.lower() == "yellow":
                beep_frequency = 1500  # Higher medium pitch for yellow

            # Calculate spacing for watermark insertion
            # We'll use duration to determine spacing of beeps

            # Create filter to add beep tones at intervals
            filter_complex = ""

            # Use size parameter to determine number of beeps (10=1, 20=2, 30=3, 40=4)
            num_beeps = max(1, min(size // 10, 4))

            # Use opacity to determine volume
            beep_volume = beep_volume * opacity

            # Determine interval for beeps based on audio_watermark_interval parameter
            # Use provided audio_watermark_interval if available
            if (
                audio_watermark_interval is not None
                and str(audio_watermark_interval).lower() != "none"
            ):
                try:
                    # Try to convert to integer (seconds)
                    interval_val = int(audio_watermark_interval)
                    # Ensure it's in valid range (minimum 5 seconds)
                    interval = max(5, interval_val)
                except (ValueError, TypeError):
                    # If conversion fails, use a default interval based on duration
                    if duration < 60:
                        # For short files, add beeps more frequently
                        interval = 10
                    elif duration > 300:
                        # For long files, add beeps less frequently
                        interval = 60
                    else:
                        # Default interval
                        interval = 30
            # Use default interval based on duration
            elif duration < 60:
                # For short files, add beeps more frequently
                interval = 10
            elif duration > 300:
                # For long files, add beeps less frequently
                interval = 60
            else:
                # Default interval
                interval = 30

            # Always enable audio watermarking when text is provided
            # Apply audio watermark
            if duration <= 30:
                # For short files, add beep at beginning and end
                filter_complex = (
                    f"[0:a]asetpts=PTS-STARTPTS[a];"
                    f"aevalsrc=0.1*sin({beep_frequency}*2*PI*t):d={beep_duration}:s=44100[beep];"
                    f"[a][beep]amix=inputs=2:duration=first:weights=1 {max(0.1, beep_volume)}[aout]"
                )
            else:
                # For longer files, add beeps at intervals based on the interval parameter
                beep_points = []

                # Calculate number of beeps based on duration and interval
                # Ensure we have at least num_beeps (from size parameter) beeps
                num_points = max(num_beeps, int(duration / interval))

                # Distribute beeps evenly
                for i in range(num_points):
                    point = i * interval
                    if point < duration:
                        beep_points.append(point)

                # Create a complex filter to insert beeps at intervals
                beep_parts = []
                for i, point in enumerate(beep_points):
                    beep_parts.append(
                        f"aevalsrc=0.1*sin({beep_frequency}*2*PI*t):d={beep_duration}:s=44100,adelay={int(point * 1000)}|{int(point * 1000)}[beep{i + 1}];"
                    )

                # Combine all beeps
                beep_inputs = "".join(
                    f"[beep{i + 1}]" for i in range(len(beep_points))
                )
                weights = " ".join(["1"] * len(beep_points))
                beep_volumes = " ".join([str(beep_volume)] * len(beep_points))

                filter_complex = (
                    f"[0:a]asetpts=PTS-STARTPTS[a];"
                    f"{''.join(beep_parts)}"
                    f"[a]{beep_inputs}amix=inputs={len(beep_points) + 1}:duration=first:weights={weights} {beep_volumes}[aout]"
                )

            # Determine input format and codec
            import subprocess

            # Get file info using ffprobe
            try:
                probe_cmd = [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    file,
                ]
                result = subprocess.run(
                    probe_cmd, capture_output=True, text=True, check=False
                )

                # Check if ffprobe command was successful and returned output
                if result.returncode != 0 or not result.stdout.strip():
                    LOGGER.warning(
                        f"ffprobe failed for file: {file}, return code: {result.returncode}"
                    )
                    if result.stderr:
                        LOGGER.warning(f"ffprobe stderr: {result.stderr.strip()}")
                    raise ValueError("ffprobe returned no valid output")

                # Try to parse JSON output
                try:
                    file_info = json.loads(result.stdout)
                except json.JSONDecodeError as json_err:
                    LOGGER.error(
                        f"Failed to parse ffprobe JSON output for file: {file}"
                    )
                    LOGGER.error(f"JSON error: {json_err}")
                    LOGGER.error(
                        f"Raw output: {result.stdout[:200]}..."
                    )  # Log first 200 chars
                    raise ValueError("Invalid JSON output from ffprobe")

                # Get format and codec information
                input_format = file_info.get("format", {}).get("format_name", "")
                audio_codec = None

                # Find the audio stream
                for stream in file_info.get("streams", []):
                    if stream.get("codec_type") == "audio":
                        audio_codec = stream.get("codec_name")
                        break

                # Extract file extension from temp_file
                output_ext = os.path.splitext(temp_file)[1].lower()
            except Exception as e:
                # Downgrade to warning since we can proceed with defaults and watermarking succeeded later
                LOGGER.warning(
                    f"Non-fatal: could not get file info for {file}: {e}. Proceeding with defaults."
                )
                input_format = ""
                audio_codec = None
                output_ext = os.path.splitext(temp_file)[1].lower()

            # Create command to add beep watermark
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                file,
                "-filter_complex",
                filter_complex,
                "-map",
                "[aout]",
            ]

            # Set output codec based on input format and codec
            if output_ext == ".mp3" or "mp3" in input_format.lower():
                cmd.extend(["-c:a", "libmp3lame"])
            elif output_ext == ".flac" or "flac" in input_format.lower():
                cmd.extend(["-c:a", "flac"])
            elif (
                output_ext == ".ogg"
                or "ogg" in input_format.lower()
                or audio_codec == "vorbis"
            ):
                cmd.extend(["-c:a", "libvorbis"])
            elif (
                output_ext == ".opus"
                or "opus" in input_format.lower()
                or audio_codec == "opus"
            ):
                cmd.extend(["-c:a", "libopus"])
            elif output_ext == ".wav" or "wav" in input_format.lower():
                cmd.extend(["-c:a", "pcm_s16le"])
            else:
                # Default to AAC for other formats
                cmd.extend(["-c:a", "aac"])

            # Set bitrate based on quality parameter
            bitrate = "128k"  # Default bitrate
            if quality:
                if str(quality).lower() == "high":
                    bitrate = "192k"
                elif str(quality).lower() == "medium":
                    bitrate = "128k"
                elif str(quality).lower() == "low":
                    bitrate = "96k"
                elif (
                    str(quality).lower() != "none"
                    and isinstance(quality, int | float)
                    and int(quality) < 20
                ):
                    bitrate = "192k"

            # Add bitrate parameter (skip for lossless formats)
            if not (
                output_ext in {".flac", ".wav"}
                or "flac" in input_format.lower()
                or "wav" in input_format.lower()
            ):
                cmd.extend(["-b:a", bitrate])

            # Add metadata and output file
            cmd.extend(
                [
                    "-metadata",
                    f"comment=Watermarked with: {watermark_text}",
                    "-metadata",
                    f"title=Original title + {watermark_text}",
                    "-threads",
                    f"{thread_count}",
                    temp_file,
                ]
            )

        except Exception as e:
            LOGGER.error(f"Error creating audio watermark command: {e}")
            return None, None

    elif media_type == "video_with_subtitle":
        # For videos with subtitle streams, we should handle them as regular videos
        # but skip the subtitle watermarking

        # Use the same code as for regular videos, but make sure we don't modify subtitle streams
        # First, select only the main video stream (usually the first one)
        cmd.extend(["-map", "0:v:0"])

        # Always ensure dimensions are even (required by some codecs)
        cmd.extend(
            [
                "-vf",
                f"scale=iw:ih,pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2,{drawtext_filter}",
            ]
        )

        # Map audio and subtitle streams, but copy subtitle streams without modification
        cmd.extend(["-map", "0:a?", "-map", "0:s?", "-map", "0:t?"])

        # Copy audio and subtitle streams
        cmd.extend(
            ["-c:a", "copy", "-c:s", "copy"]
        )  # Add quality settings based on quality parameter
        if quality is not None and str(quality).lower() != "none":
            # Check if quality is a string like "high", "medium", "low"
            if str(quality).lower() in ["high", "medium", "low"]:
                # Handle text-based quality values
                if str(quality).lower() == "high":
                    cmd.extend(["-crf", "18"])  # High quality
                elif str(quality).lower() == "medium":
                    cmd.extend(["-crf", "23"])  # Medium quality
                elif str(quality).lower() == "low":
                    cmd.extend(["-crf", "28"])  # Low quality
            else:
                try:
                    # Try to convert quality to integer (1-51 for x264/x265)
                    quality_val = int(quality)
                    # Ensure it's in valid range (lower is better quality)
                    quality_val = max(1, min(quality_val, 51))
                    cmd.extend(["-crf", str(quality_val)])
                except (ValueError, TypeError):
                    # If conversion fails, use a default high quality
                    cmd.extend(["-crf", "18"])  # High quality default
        else:
            # No quality specified, use a good default
            cmd.extend(["-crf", "23"])  # Default quality

        # Add speed settings based on speed parameter
        if speed is not None and str(speed).lower() != "none":
            # Valid presets: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
            valid_presets = [
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ]

            # Check if speed is a valid preset name
            if str(speed).lower() in valid_presets:
                cmd.extend(["-preset", str(speed).lower()])
            else:
                try:
                    # Try to convert speed to integer (1-9)
                    speed_val = int(speed)
                    # Map 1-9 to presets (1=ultrafast, 9=veryslow)
                    speed_val = max(1, min(speed_val, 9))
                    preset = valid_presets[speed_val - 1]
                    cmd.extend(["-preset", preset])
                except (ValueError, TypeError):
                    # If conversion fails and it's not a valid preset name, use default
                    if use_fast_mode:
                        cmd.extend(["-preset", "ultrafast"])
                    else:
                        cmd.extend(["-preset", "medium"])  # Default preset
        elif use_fast_mode:
            # No speed specified but fast mode is enabled
            cmd.extend(["-preset", "ultrafast"])

        # Add format-specific optimizations for Telegram compatibility
        temp_file_ext = os.path.splitext(temp_file)[1].lower()
        if temp_file_ext == ".mp4":
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
        elif temp_file_ext == ".mkv":
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
        elif temp_file_ext == ".webm":
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
        elif temp_file_ext == ".mov":
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

        return cmd, temp_file

    elif media_type == "subtitle":
        # For subtitle files, we'll add the watermark text to each subtitle entry
        # This requires parsing and modifying the subtitle file

        # Always enable subtitle watermarking when text is provided
        # No need to check for subtitle_watermark_enabled anymore

        try:
            # Read the subtitle file
            import aiofiles

            try:
                async with aiofiles.open(
                    file, encoding="utf-8", errors="ignore"
                ) as f:
                    content = await f.read()
            except ImportError:
                # Fallback to regular open if aiofiles is not available
                with open(file, encoding="utf-8", errors="ignore") as f:
                    content = f.read()

            # Create a temporary file for the modified subtitles
            # Use a unique name to avoid conflicts
            import uuid

            temp_file = (
                f"{os.path.splitext(file)[0]}_wm_{uuid.uuid4().hex[:8]}{file_ext}"
            )

            # Determine watermark style based on parameters
            # First check if we have a specific subtitle style provided as parameter
            if (
                subtitle_watermark_style
                and subtitle_watermark_style.lower() != "none"
            ):
                subtitle_style = subtitle_watermark_style
            else:
                # Otherwise, check if we have a specific subtitle style set in config
                from bot.core.config_manager import Config

                subtitle_style = (
                    Config.SUBTITLE_WATERMARK_STYLE
                    if hasattr(Config, "SUBTITLE_WATERMARK_STYLE")
                    else "normal"
                )

            # Set style based on subtitle_style parameter
            style_lower = subtitle_style.lower()

            # Text formatting styles
            if style_lower == "bold":
                watermark_style = "**"  # Bold style
            elif style_lower == "italic":
                watermark_style = "_"  # Italic style
            elif style_lower == "underline":
                watermark_style = "__"  # Underline style
            elif style_lower == "strikethrough":
                watermark_style = "~~"  # Strikethrough style
            elif style_lower == "bold_italic":
                watermark_style = "***"  # Bold italic style
            # Color-based styles using emoji
            elif style_lower == "yellow":
                watermark_style = "⭐"  # Yellow star
            elif style_lower == "red":
                watermark_style = "❤️"  # Red heart symbol
            elif style_lower == "green":
                watermark_style = "💚"  # Green heart symbol
            elif style_lower == "blue":
                watermark_style = "💙"  # Blue heart symbol
            elif style_lower == "purple":
                watermark_style = "💜"  # Purple heart symbol
            elif style_lower == "orange":
                watermark_style = "🧡"  # Orange heart symbol
            elif style_lower == "black":
                watermark_style = "⚫"  # Black circle
            elif style_lower == "white":
                watermark_style = "⚪"  # White circle
            # Default to no style for "normal" or unrecognized styles
            else:
                watermark_style = ""  # Default, no special styling

            # Use size parameter to determine frequency
            # 10 = every subtitle, 20 = every 2nd, 30 = every 3rd, 40 = every 4th
            frequency = max(1, size // 10)

            # Use opacity to determine visibility (1.0 = full text, lower = abbreviated)
            abbreviated = opacity < 0.7

            # Check if it's an SRT file (most common)
            if file_ext.lower() == ".srt":
                # Enhanced watermarking: add the watermark text with styling
                import re

                # Pattern to match SRT entries
                pattern = r"(\d+)\r?\n(\d{2}:\d{2}:\d{2},\d{3}\s-->\s\d{2}:\d{2}:\d{2},\d{3})\r?\n(.*?)(?=\r?\n\r?\n\d+|\Z)"

                # Function to add watermark to each subtitle entry
                def add_watermark(match):
                    index = int(match.group(1))
                    timing = match.group(2)
                    text = match.group(3).strip()

                    # Only add watermark based on frequency
                    if index % frequency != 0:
                        return f"{index}\n{timing}\n{text}\n\n"

                    # Prepare watermark text
                    watermark_text = key
                    if subtitle_watermark_interval is not None:
                        # Use the interval parameter as text
                        watermark_text = f"{key} ({subtitle_watermark_interval})"
                    if abbreviated and len(watermark_text) > 10:
                        # Use abbreviated version for lower opacity
                        words = watermark_text.split()
                        if len(words) > 1:
                            watermark_text = "".join(word[0] for word in words)
                        else:
                            watermark_text = watermark_text[:5] + "..."

                    # Format with style
                    formatted_watermark = (
                        f"{watermark_style}[{watermark_text}]{watermark_style}"
                    )

                    # Add watermark based on position
                    if position in [
                        "bottom_left",
                        "bottom_right",
                        "bottom_center",
                    ]:
                        # Add at the end
                        watermarked_text = f"{text}\n{formatted_watermark}"
                    elif position in ["top_left", "top_right", "top_center"]:
                        # Add at the beginning
                        watermarked_text = f"{formatted_watermark}\n{text}"
                    elif position == "center":
                        # Add in the middle of the text if possible
                        lines = text.split("\n")
                        if len(lines) > 1:
                            middle = len(lines) // 2
                            lines.insert(middle, formatted_watermark)
                            watermarked_text = "\n".join(lines)
                        else:
                            # If single line, add at the end
                            watermarked_text = f"{text} {formatted_watermark}"
                    else:
                        # For other positions, add inline
                        watermarked_text = f"{text} {formatted_watermark}"

                    return f"{index}\n{timing}\n{watermarked_text}\n\n"

                # Apply the watermark
                watermarked_content = re.sub(
                    pattern, add_watermark, content, flags=re.DOTALL
                )

                # Write the watermarked content to the temp file
                try:
                    import aiofiles

                    async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                        await f.write(watermarked_content)
                except ImportError:
                    # Fallback to regular open if aiofiles is not available
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(watermarked_content)

                # For SRT files, we don't use FFmpeg, so return None for the command
                # but keep the temp_file for the result
                return None, temp_file

            # Handle other subtitle formats
            if file_ext.lower() in [".ass", ".ssa"]:
                # For ASS/SSA files, add the watermark to the style or as a separate line
                # This is more complex and would require a proper ASS parser
                import re

                # Try to find the Events section
                events_match = re.search(
                    r"(\[Events\].*?)(?=\[|\Z)", content, re.DOTALL
                )
                if events_match:
                    events_section = events_match.group(1)
                    # Find the format line
                    format_match = re.search(
                        r"Format:(.*?)$", events_section, re.MULTILINE
                    )
                    if format_match:
                        # Get the format fields
                        format_fields = [
                            f.strip() for f in format_match.group(1).split(",")
                        ]

                        # Find the dialogue lines
                        dialogue_pattern = r"(Dialogue:.*?)$"

                        # Function to add watermark to dialogue lines
                        def add_ass_watermark(match):
                            line = match.group(1)
                            parts = line.split(",", len(format_fields))

                            # Get the text part (last part)
                            if len(parts) >= len(format_fields):
                                text = parts[-1]

                                # Add watermark based on position
                                if position in [
                                    "bottom_left",
                                    "bottom_right",
                                    "bottom_center",
                                ]:
                                    # Add at the end
                                    # Prepare watermark text
                                    watermark_text = key
                                    if subtitle_watermark_interval is not None:
                                        # Use the interval parameter as text
                                        watermark_text = (
                                            f"{key} ({subtitle_watermark_interval})"
                                        )
                                    watermarked_text = f"{text}\\N{watermark_style}[{watermark_text}]{watermark_style}"
                                else:
                                    # Add at the beginning
                                    # Prepare watermark text
                                    watermark_text = key
                                    if subtitle_watermark_interval is not None:
                                        # Use the interval parameter as text
                                        watermark_text = (
                                            f"{key} ({subtitle_watermark_interval})"
                                        )
                                    watermarked_text = f"{watermark_style}[{watermark_text}]{watermark_style}\\N{text}"

                                # Replace the text part
                                parts[-1] = watermarked_text
                                return ",".join(parts)
                            return line

                        # Apply watermark to every nth dialogue line based on frequency
                        lines = events_section.split("\n")
                        dialogue_count = 0
                        for i in range(len(lines)):
                            if lines[i].startswith("Dialogue:"):
                                dialogue_count += 1
                                if dialogue_count % frequency == 0:
                                    lines[i] = re.sub(
                                        dialogue_pattern,
                                        add_ass_watermark,
                                        lines[i],
                                    )

                        # Replace the events section in the content
                        modified_events = "\n".join(lines)
                        modified_content = content.replace(
                            events_match.group(1), modified_events
                        )

                        # Write the modified content to the temp file
                        try:
                            import aiofiles

                            async with aiofiles.open(
                                temp_file, "w", encoding="utf-8"
                            ) as f:
                                await f.write(modified_content)
                        except ImportError:
                            # Fallback to regular open if aiofiles is not available
                            with open(temp_file, "w", encoding="utf-8") as f:
                                f.write(modified_content)

                        return None, temp_file

                # If we couldn't parse the ASS file properly, just add a comment
                # Get subtitle_watermark_text from config if available
                from bot.core.config_manager import Config

                config_subtitle_text = (
                    Config.SUBTITLE_WATERMARK_TEXT
                    if hasattr(Config, "SUBTITLE_WATERMARK_TEXT")
                    else None
                )

                # Prepare watermark text - use parameter or config value
                watermark_text = key
                if subtitle_watermark_interval is not None:
                    # Use the interval parameter as text
                    watermark_text = f"{key} ({subtitle_watermark_interval})"
                elif config_subtitle_text:
                    watermark_text = config_subtitle_text

                # Write the modified content to the temp file
                try:
                    import aiofiles

                    async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                        await f.write(
                            f"; Watermarked with: {watermark_text}\n{content}"
                        )
                except ImportError:
                    # Fallback to regular open if aiofiles is not available
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(f"; Watermarked with: {watermark_text}\n{content}")

                return None, temp_file

            # For other subtitle formats, try to add watermark based on common patterns
            # WebVTT format
            if file_ext.lower() == ".vtt":
                import re

                # Pattern for WebVTT cues
                pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3}\s-->\s\d{2}:\d{2}:\d{2}\.\d{3}.*?\n)(.*?)(?=\n\n|\Z)"

                # Function to add watermark to WebVTT cues
                def add_vtt_watermark(match):
                    timing = match.group(1)
                    text = match.group(2).strip()

                    # Add watermark based on position
                    if position in [
                        "bottom_left",
                        "bottom_right",
                        "bottom_center",
                    ]:
                        # Add at the end
                        # Get subtitle_watermark_text from config if available
                        from bot.core.config_manager import Config

                        config_subtitle_text = (
                            Config.SUBTITLE_WATERMARK_TEXT
                            if hasattr(Config, "SUBTITLE_WATERMARK_TEXT")
                            else None
                        )

                        # Prepare watermark text - use parameter or config value
                        watermark_text = key
                        if subtitle_watermark_interval is not None:
                            # Use the interval parameter as text
                            watermark_text = f"{key} ({subtitle_watermark_interval})"
                        elif config_subtitle_text:
                            watermark_text = config_subtitle_text
                        watermarked_text = f"{text}\n{watermark_style}[{watermark_text}]{watermark_style}"
                    else:
                        # Add at the beginning
                        # Prepare watermark text
                        watermark_text = key
                        if subtitle_watermark_interval is not None:
                            # Use the interval parameter as text
                            watermark_text = f"{key} ({subtitle_watermark_interval})"
                        watermarked_text = f"{watermark_style}[{watermark_text}]{watermark_style}\n{text}"

                    return f"{timing}{watermarked_text}\n\n"

                # Apply the watermark
                watermarked_content = re.sub(
                    pattern, add_vtt_watermark, content, flags=re.DOTALL
                )

                # Write the modified content to the temp file
                try:
                    import aiofiles

                    async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                        await f.write(watermarked_content)
                except ImportError:
                    # Fallback to regular open if aiofiles is not available
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(watermarked_content)

                return None, temp_file

            # For other formats, just add a comment if possible
            # Prepare watermark text
            watermark_text = key
            if subtitle_watermark_interval is not None:
                # Use the interval parameter as text
                watermark_text = f"{key} ({subtitle_watermark_interval})"

            # Write the modified content to the temp file
            try:
                import aiofiles

                async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                    await f.write(f"# Watermarked with: {watermark_text}\n{content}")
            except ImportError:
                # Fallback to regular open if aiofiles is not available
                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write(f"# Watermarked with: {watermark_text}\n{content}")

            return None, temp_file

        except Exception as e:
            LOGGER.error(f"Error watermarking subtitle file: {e}")
            return None, None
    else:
        # This should not happen as we already checked media_type
        LOGGER.error(f"Unknown media type: {media_type}")
        return None, None

    # Add threads parameter if not already added
    if "-threads" not in cmd and media_type not in ["subtitle"]:
        cmd.extend(["-threads", f"{thread_count}", temp_file])

    # Log the generated command for debugging only

    return cmd, temp_file


async def get_metadata_cmd(
    file_path,
    key,
    title=None,
    author=None,
    comment=None,
    metadata_all=None,
    video_title=None,
    video_author=None,
    video_comment=None,
    audio_title=None,
    audio_author=None,
    audio_comment=None,
    subtitle_title=None,
    subtitle_author=None,
    subtitle_comment=None,
):
    """Processes a single file to update metadata with template variable support.

    Args:
        file_path: Path to the file to process
        key: Legacy metadata key (for backward compatibility)
        title: Global title metadata value (supports template variables)
        author: Global author metadata value (supports template variables)
        comment: Global comment metadata value (supports template variables)
        metadata_all: Value to use for all metadata fields (takes priority over all, supports template variables)
        video_title: Video track title metadata value (supports template variables)
        video_author: Video track author metadata value (supports template variables)
        video_comment: Video track comment metadata value (supports template variables)
        audio_title: Audio track title metadata value (supports template variables)
        audio_author: Audio track author metadata value (supports template variables)
        audio_comment: Audio track comment metadata value (supports template variables)
        subtitle_title: Subtitle track title metadata value (supports template variables)
        subtitle_author: Subtitle track author metadata value (supports template variables)
        subtitle_comment: Subtitle track comment metadata value (supports template variables)

    Returns:
        tuple: FFmpeg command and temporary output file path, or None, None if not supported
    """
    # Import template processing function
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

        from bot.helper.ext_utils.media_utils import get_media_info

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

    # Process template variables in all metadata fields (simple substitution only)
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
    if metadata_all:
        metadata_all = await process_metadata_template(metadata_all)
    if title:
        title = await process_metadata_template(title)
    if author:
        author = await process_metadata_template(author)
    if comment:
        comment = await process_metadata_template(comment)
    if video_title:
        video_title = await process_metadata_template(video_title)
    if video_author:
        video_author = await process_metadata_template(video_author)
    if video_comment:
        video_comment = await process_metadata_template(video_comment)
    if audio_title:
        audio_title = await process_metadata_template(audio_title)
    if audio_author:
        audio_author = await process_metadata_template(audio_author)
    if audio_comment:
        audio_comment = await process_metadata_template(audio_comment)
    if subtitle_title:
        subtitle_title = await process_metadata_template(subtitle_title)
    if subtitle_author:
        subtitle_author = await process_metadata_template(subtitle_author)
    if subtitle_comment:
        subtitle_comment = await process_metadata_template(subtitle_comment)
    if key:
        key = await process_metadata_template(key)

    # Resource manager removed

    # Get file extension
    file_ext = os.path.splitext(file_path)[1].lower()

    # For most files, use .mkv as temp extension for maximum metadata compatibility
    # For HEVC files, use .mp4 as temp extension for better compatibility
    # For MPEG files, use .mp4 as temp extension for better compatibility
    # For image files, use appropriate extensions
    # For subtitle files, use .srt for maximum compatibility
    if file_ext in [".hevc", ".mpeg"]:
        temp_file = f"{file_path}.temp.mp4"
    elif file_ext in [".jpg", ".jpeg", ".png", ".gif", ".tiff", ".tif", ".webp"]:
        # For image files, keep the same extension for better compatibility
        temp_file = f"{file_path}.temp{file_ext}"
    elif file_ext in [
        ".srt",
        ".ass",
        ".ssa",
        ".vtt",
        ".webvtt",
        ".sub",
        ".sbv",
        ".stl",
    ]:
        # For subtitle files, use .srt for maximum compatibility
        temp_file = f"{file_path}.temp.srt"
    else:
        temp_file = f"{file_path}.temp.mkv"

    # Get stream information
    # For subtitle files, we might not get proper stream info, so handle them specially
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext in [
        ".srt",
        ".ass",
        ".ssa",
        ".vtt",
        ".webvtt",
        ".sub",
        ".sbv",
        ".stl",
        ".scc",
        ".ttml",
        ".dfxp",
    ]:
        # For subtitle files, create a simple command that just copies the file and adds metadata
        # For some subtitle formats, we need to convert them to SRT for better compatibility

        # Create a temporary text file with metadata
        meta_file = f"{file_path}.meta"
        with open(meta_file, "w") as f:
            if title:
                f.write(f";TITLE={title}\n")
            if author:
                f.write(f";AUTHOR={author}\n")
            if comment:
                f.write(f";COMMENT={comment}\n")
            if subtitle_title:
                f.write(f";SUBTITLE_TITLE={subtitle_title}\n")
            if subtitle_author:
                f.write(f";SUBTITLE_AUTHOR={subtitle_author}\n")
            if subtitle_comment:
                f.write(f";SUBTITLE_COMMENT={subtitle_comment}\n")

        # For problematic formats, try to convert to SRT first
        if file_ext in [
            ".vtt",
            ".webvtt",
            ".sbv",
            ".stl",
            ".scc",
            ".ttml",
            ".dfxp",
            ".sub",
        ]:  # First, try to convert using FFmpeg
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                file_path,
                "-map_metadata",
                "-1",  # Remove existing metadata
            ]

            # Add global metadata
            if title:
                cmd.extend(["-metadata", f"title={title}"])
            if author:
                cmd.extend(
                    [
                        "-metadata",
                        f"artist={author}",
                        "-metadata",
                        f"author={author}",
                    ]
                )
            if comment:
                cmd.extend(["-metadata", f"comment={comment}"])

            # Add subtitle-specific metadata
            if subtitle_title:
                cmd.extend(["-metadata", f"subtitle_title={subtitle_title}"])
            if subtitle_author:
                cmd.extend(["-metadata", f"subtitle_author={subtitle_author}"])
            if subtitle_comment:
                cmd.extend(["-metadata", f"subtitle_comment={subtitle_comment}"])

            # Convert to SRT format
            cmd.extend(
                [
                    "-c:s",
                    "srt",  # Convert to SRT format
                    "-threads",
                    "8",
                    temp_file,
                ]
            )

            # If this is a .sub file, try a different approach as fallback
            if file_ext == ".sub":
                # For .sub files, we need to check if it's a SubRip or MicroDVD format
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        first_line = f.readline().strip()

                    # Check if it's MicroDVD format (starts with {number}{number})
                    if first_line.startswith("{") and "}" in first_line:
                        LOGGER.info(
                            f"Detected MicroDVD format for {file_path}, using special handling"
                        )
                        # For MicroDVD, we need to use a different approach
                        # Create a new command that handles MicroDVD format
                        cmd = [
                            "xtra",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-progress",
                            "pipe:1",
                            "-i",
                            file_path,
                            "-map_metadata",
                            "-1",  # Remove existing metadata
                            "-sub_charenc",
                            "UTF-8",  # Ensure UTF-8 encoding
                            "-f",
                            "srt",  # Force SRT output format
                        ]

                        # Add metadata
                        if title:
                            cmd.extend(["-metadata", f"title={title}"])
                        if author:
                            cmd.extend(
                                [
                                    "-metadata",
                                    f"artist={author}",
                                    "-metadata",
                                    f"author={author}",
                                ]
                            )
                        if comment:
                            cmd.extend(["-metadata", f"comment={comment}"])
                        if subtitle_title:
                            cmd.extend(
                                ["-metadata", f"subtitle_title={subtitle_title}"]
                            )
                        if subtitle_author:
                            cmd.extend(
                                ["-metadata", f"subtitle_author={subtitle_author}"]
                            )
                        if subtitle_comment:
                            cmd.extend(
                                ["-metadata", f"subtitle_comment={subtitle_comment}"]
                            )

                        cmd.append(temp_file)
                except Exception as e:
                    LOGGER.error(f"Error checking SUB format: {e}")
        else:
            # For SRT, ASS, SSA formats, just copy
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                file_path,
                "-map_metadata",
                "-1",  # Remove existing metadata
            ]

            # Add global metadata
            if title:
                cmd.extend(["-metadata", f"title={title}"])
            if author:
                cmd.extend(
                    [
                        "-metadata",
                        f"artist={author}",
                        "-metadata",
                        f"author={author}",
                    ]
                )
            if comment:
                cmd.extend(["-metadata", f"comment={comment}"])

            # Add subtitle-specific metadata
            if subtitle_title:
                cmd.extend(["-metadata", f"subtitle_title={subtitle_title}"])
            if subtitle_author:
                cmd.extend(["-metadata", f"subtitle_author={subtitle_author}"])
            if subtitle_comment:
                cmd.extend(["-metadata", f"subtitle_comment={subtitle_comment}"])

            # Finish the command
            cmd.extend(["-c", "copy", "-threads", "8", temp_file])

        # Add cleanup for the metadata file
        LOGGER.info(f"Created temporary metadata file: {meta_file}")

        return cmd, temp_file

    # Special handling for image and document files
    file_ext = os.path.splitext(file_path)[1].lower()
    image_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".tiff",
        ".tif",
        ".webp",
        ".bmp",
        ".heic",
        ".heif",
        ".avif",
        ".jfif",
        ".svg",
        ".ico",
        ".psd",
        ".eps",
        ".raw",
        ".cr2",
        ".nef",
        ".orf",
        ".sr2",
    ]

    document_extensions = [
        ".pdf",
        ".epub",
        ".mobi",
        ".azw",
        ".azw3",
        ".djvu",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".txt",
        ".rtf",
        ".md",
        ".csv",
    ]

    if file_ext in document_extensions:
        LOGGER.info(
            f"Detected document file: {file_path}, using special handling for metadata"
        )

        # For document files, use the document_utils module

        # Create a dummy command that will be replaced by the document_utils module
        cmd = ["echo", "Using document_utils module for metadata"]

        # The temp_file will be created by the document_utils module
        # Ensure the temp file path is valid by creating the directory if needed
        temp_file = f"{file_path}.temp{file_ext}"

        # Make sure the directory exists
        try:
            os.makedirs(os.path.dirname(temp_file), exist_ok=True)
        except Exception as e:
            LOGGER.warning(f"Error creating directory for temp file: {e}")

        # Return the dummy command and temp_file
        # The actual metadata application will be handled by the document_utils module
        # in the metadata_watermark_cmds method
        return cmd, temp_file

    if file_ext in image_extensions:
        LOGGER.info(
            f"Detected image file: {file_path}, using special handling for metadata"
        )

        # For image files, we'll use a different approach
        # First, create a temporary file with the same extension
        if ".temp" not in file_path:
            temp_file = f"{file_path}.temp{file_ext}"
        else:
            temp_file = file_path

        # Make sure the directory exists
        try:
            os.makedirs(os.path.dirname(temp_file), exist_ok=True)
        except Exception as e:
            LOGGER.warning(f"Error creating directory for temp file: {e}")

        # Create the command based on the image type
        if file_ext in [
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".bmp",
            ".tiff",
            ".tif",
        ]:
            # For common image formats, use FFmpeg
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                file_path,
                "-map_metadata",
                "-1",  # Remove existing metadata
            ]

            # Add global metadata
            if title:
                cmd.extend(["-metadata", f"title={title}"])
            if author:
                cmd.extend(
                    [
                        "-metadata",
                        f"artist={author}",
                        "-metadata",
                        f"author={author}",
                    ]
                )
            if comment:
                cmd.extend(["-metadata", f"comment={comment}"])

            # Finish the command
            cmd.extend(["-c", "copy", "-threads", "8", temp_file])

            return cmd, temp_file
        # For other image formats, try to use exiftool if available
        try:
            # Check if exiftool is available
            result = await cmd_exec(["which", "exiftool"])
            if result[0] and result[2] == 0:
                # exiftool is available, use it
                cmd = ["exiftool"]

                # Add metadata
                if title:
                    cmd.extend(["-Title=" + title])
                if author:
                    cmd.extend(["-Artist=" + author, "-Author=" + author])
                if comment:
                    cmd.extend(["-Comment=" + comment])

                # Add output file
                cmd.extend(["-o", temp_file, file_path])

                return cmd, temp_file
            # exiftool not available, fall back to FFmpeg
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                file_path,
                "-map_metadata",
                "-1",  # Remove existing metadata
            ]

            # Add global metadata
            if title:
                cmd.extend(["-metadata", f"title={title}"])
            if author:
                cmd.extend(
                    [
                        "-metadata",
                        f"artist={author}",
                        "-metadata",
                        f"author={author}",
                    ]
                )
            if comment:
                cmd.extend(["-metadata", f"comment={comment}"])

            # Finish the command
            cmd.extend(["-c", "copy", "-threads", "8", temp_file])

            return cmd, temp_file
        except Exception as e:
            LOGGER.error(f"Error checking for exiftool: {e}")
            # Fall back to FFmpeg
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                file_path,
                "-map_metadata",
                "-1",  # Remove existing metadata
            ]

            # Add global metadata
            if title:
                cmd.extend(["-metadata", f"title={title}"])
            if author:
                cmd.extend(
                    [
                        "-metadata",
                        f"artist={author}",
                        "-metadata",
                        f"author={author}",
                    ]
                )
            if comment:
                cmd.extend(["-metadata", f"comment={comment}"])

            # Finish the command
            cmd.extend(["-c", "copy", "-threads", "8", temp_file])

            return cmd, temp_file

    # For other files, get stream information
    streams = await get_streams(file_path)
    if not streams:
        LOGGER.error(f"Failed to get stream information for {file_path}")
        return None, None

    # Extract language information from streams
    languages = {}
    with contextlib.suppress(Exception):
        languages = {
            stream["index"]: stream["tags"]["language"]
            for stream in streams
            if "tags" in stream and "language" in stream["tags"]
        }

    # Use default thread count
    thread_count = max(1, cpu_no // 2)

    # Determine which metadata values to use
    # metadata_all takes priority over all other settings
    if metadata_all:
        # Use metadata_all for all fields
        global_title_value = global_author_value = global_comment_value = (
            metadata_all
        )
        video_title_value = video_author_value = video_comment_value = metadata_all
        audio_title_value = audio_author_value = audio_comment_value = metadata_all
        subtitle_title_value = subtitle_author_value = subtitle_comment_value = (
            metadata_all
        )
    else:
        # Global metadata (fallback to legacy key if not provided)
        global_title_value = title if title else key
        global_author_value = author if author else key
        global_comment_value = comment if comment else key

        # Video track metadata (fallback to global values if not provided)
        video_title_value = video_title if video_title else global_title_value
        video_author_value = video_author if video_author else global_author_value
        video_comment_value = (
            video_comment if video_comment else global_comment_value
        )

        # Audio track metadata (fallback to global values if not provided)
        audio_title_value = audio_title if audio_title else global_title_value
        audio_author_value = audio_author if audio_author else global_author_value
        audio_comment_value = (
            audio_comment if audio_comment else global_comment_value
        )

        # Subtitle track metadata (fallback to global values if not provided)
        subtitle_title_value = (
            subtitle_title if subtitle_title else global_title_value
        )
        subtitle_author_value = (
            subtitle_author if subtitle_author else global_author_value
        )
        subtitle_comment_value = (
            subtitle_comment if subtitle_comment else global_comment_value
        )

    # Start building the FFmpeg command
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file_path,
    ]

    # Add -map_metadata -1 to clear existing metadata
    cmd.extend(["-map_metadata", "-1"])

    # Always use copy codec to preserve quality
    cmd.extend(["-c", "copy"])

    # Add global metadata
    cmd.extend(["-metadata", f"title={global_title_value}"])

    # Add author and comment metadata if they exist
    if global_author_value:
        cmd.extend(["-metadata", f"artist={global_author_value}"])
        cmd.extend(["-metadata", f"author={global_author_value}"])

    if global_comment_value:
        cmd.extend(["-metadata", f"comment={global_comment_value}"])

    # Count stream types for proper indexing
    video_count = 0
    audio_count = 0
    subtitle_count = 0
    other_count = 0

    # First pass: count streams by type
    for stream in streams:
        stream_type = stream.get("codec_type", "unknown")
        if stream_type == "video":
            video_count += 1
        elif stream_type == "audio":
            audio_count += 1
        elif stream_type == "subtitle":
            subtitle_count += 1
        else:
            other_count += 1

    # Stream count logging removed for cleaner output

    # Second pass: map all streams and add metadata
    video_index = 0
    audio_index = 0
    subtitle_index = 0
    attachment_index = 0

    # Map all streams to preserve them
    cmd.extend(["-map", "0"])

    # Add stream-specific metadata
    for stream in streams:
        stream_index = stream["index"]
        stream_type = stream.get("codec_type", "unknown")

        if stream_type == "video":
            # Skip attached pictures (cover art)
            if stream.get("disposition", {}).get("attached_pic", 0) == 1:
                LOGGER.info(f"Skipping attached picture in stream {stream_index}")
                continue

            # Add video metadata
            cmd.extend(
                [f"-metadata:s:v:{video_index}", f"title={video_title_value}"]
            )

            if video_author_value:
                cmd.extend(
                    [f"-metadata:s:v:{video_index}", f"artist={video_author_value}"]
                )

            if video_comment_value:
                cmd.extend(
                    [
                        f"-metadata:s:v:{video_index}",
                        f"comment={video_comment_value}",
                    ]
                )

            # Preserve language tag if it exists
            if stream_index in languages:
                cmd.extend(
                    [
                        f"-metadata:s:v:{video_index}",
                        f"language={languages[stream_index]}",
                    ]
                )

            video_index += 1

        elif stream_type == "audio":
            # Add audio metadata
            cmd.extend(
                [f"-metadata:s:a:{audio_index}", f"title={audio_title_value}"]
            )

            if audio_author_value:
                cmd.extend(
                    [f"-metadata:s:a:{audio_index}", f"artist={audio_author_value}"]
                )

            if audio_comment_value:
                cmd.extend(
                    [
                        f"-metadata:s:a:{audio_index}",
                        f"comment={audio_comment_value}",
                    ]
                )

            # Preserve language tag if it exists
            if stream_index in languages:
                cmd.extend(
                    [
                        f"-metadata:s:a:{audio_index}",
                        f"language={languages[stream_index]}",
                    ]
                )

            audio_index += 1

        elif stream_type == "subtitle":
            codec_name = stream.get("codec_name", "unknown")

            # Some subtitle formats don't support metadata well
            if codec_name in ["webvtt", "unknown"]:
                pass

            # Add subtitle metadata
            cmd.extend(
                [f"-metadata:s:s:{subtitle_index}", f"title={subtitle_title_value}"]
            )

            if subtitle_author_value:
                cmd.extend(
                    [
                        f"-metadata:s:s:{subtitle_index}",
                        f"artist={subtitle_author_value}",
                    ]
                )

            if subtitle_comment_value:
                cmd.extend(
                    [
                        f"-metadata:s:s:{subtitle_index}",
                        f"comment={subtitle_comment_value}",
                    ]
                )

            # Preserve language tag if it exists
            if stream_index in languages:
                cmd.extend(
                    [
                        f"-metadata:s:s:{subtitle_index}",
                        f"language={languages[stream_index]}",
                    ]
                )

            subtitle_index += 1

        elif stream_type == "attachment":
            # Handle attachment streams
            # Check if the attachment has a filename tag
            if "tags" in stream and "filename" in stream["tags"]:
                # Preserve the original filename
                cmd.extend(
                    [
                        f"-metadata:s:t:{attachment_index}",
                        f"filename={stream['tags']['filename']}",
                    ]
                )
            else:
                # If no filename tag exists, add a default one
                LOGGER.info(
                    f"Adding default filename for attachment stream {stream_index}"
                )
                cmd.extend(
                    [
                        f"-metadata:s:t:{attachment_index}",
                        f"filename=attachment_{attachment_index}.bin",
                    ]
                )

            # Add mimetype if available, or use a default
            if "tags" in stream and "mimetype" in stream["tags"]:
                mimetype = stream["tags"]["mimetype"]
                cmd.extend(
                    [f"-metadata:s:t:{attachment_index}", f"mimetype={mimetype}"]
                )
            else:
                # Determine mimetype based on codec_name if available
                codec_name = stream.get("codec_name", "").lower()
                if codec_name in ["ttf"]:
                    mimetype = "application/x-truetype-font"
                elif codec_name in ["otf"]:
                    mimetype = "application/vnd.ms-opentype"
                elif codec_name in ["woff"]:
                    mimetype = "application/font-woff"
                elif codec_name in ["woff2"]:
                    mimetype = "application/font-woff2"
                else:
                    # Use a generic mimetype
                    mimetype = "application/octet-stream"

                cmd.extend(
                    [f"-metadata:s:t:{attachment_index}", f"mimetype={mimetype}"]
                )

            attachment_index += 1

    # Add thread count for better performance
    cmd.extend(["-threads", f"{thread_count}"])

    # Add output file
    cmd.append(temp_file)

    # Output file format logging removed for cleaner output

    # Log the command for debugging}")

    return cmd, temp_file


# TODO later
async def get_embed_thumb_cmd(file, attachment_path):
    # Resource manager removed

    temp_file = f"{file}.temp.mkv"

    # Make sure the directory exists
    try:
        os.makedirs(os.path.dirname(temp_file), exist_ok=True)
    except Exception as e:
        LOGGER.warning(f"Error creating directory for temp file: {e}")

    attachment_ext = attachment_path.split(".")[-1].lower()
    mime_type = "application/octet-stream"
    if attachment_ext in ["jpg", "jpeg"]:
        mime_type = "image/jpeg"
    elif attachment_ext == "png":
        mime_type = "image/png"

    # Use default thread count
    thread_count = max(1, cpu_no // 2)

    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file,
        "-ignore_unknown",
        "-attach",
        attachment_path,
        "-metadata:s:t",
        f"mimetype={mime_type}",
        "-c",
        "copy",
        "-map",
        "0",
        "-threads",
        f"{thread_count}",
        temp_file,
    ]

    return cmd, temp_file


async def get_media_type_internal(file_path):
    """Determine if a file is video, audio, or subtitle.

    Args:
        file_path: Path to the file

    Returns:
        str: 'video', 'audio', 'subtitle', or None if can't determine
    """
    streams = await get_streams(file_path)
    if not streams:
        return None

    # Check for video streams
    for stream in streams:
        if stream.get("codec_type") == "video":
            # Check if it's not just a cover art
            if not (
                stream.get("disposition")
                and stream.get("disposition").get("attached_pic") == 1
            ):
                return "video"

    # Check for audio streams
    for stream in streams:
        if stream.get("codec_type") == "audio":
            return "audio"

    # Check for subtitle streams
    for stream in streams:
        if stream.get("codec_type") == "subtitle":
            return "subtitle"

    return None


async def get_merge_concat_demuxer_cmd(
    files, output_format="mkv", media_type=None, folder_name=None
):
    """Generate FFmpeg command for merging files using concat demuxer.

    Args:
        files: List of file paths to merge
        output_format: Output file format (default: mkv)
                      If "none", will use the format of the first input file
        media_type: Type of media ('video', 'audio', 'subtitle', 'image') for specialized handling
        folder_name: Optional folder name to use for output filename (from -m flag or extracted folder name)

    Returns:
        tuple: FFmpeg command and output file path
    """
    # Resource manager removed

    if not files:
        return None, None

    # Use files in the order they were provided
    # (No sorting to preserve user's intended order)

    # If output_format is "none", use the format of the first input file
    if output_format == "none" and files:
        # Extract extension from the first file
        first_file_ext = os.path.splitext(files[0])[1].lower().lstrip(".")
        if first_file_ext:
            # Use the extension if it's valid
            if (
                (
                    media_type == "video"
                    and first_file_ext
                    in [
                        "mp4",
                        "mkv",
                        "avi",
                        "mov",
                        "webm",
                        "flv",
                    ]
                )
                or (
                    media_type == "audio"
                    and first_file_ext
                    in [
                        "mp3",
                        "aac",
                        "ogg",
                        "wav",
                        "flac",
                        "m4a",
                    ]
                )
                or (
                    media_type == "subtitle"
                    and first_file_ext
                    in [
                        "srt",
                        "ass",
                        "vtt",
                        "sub",
                    ]
                )
                or (
                    media_type == "image"
                    and first_file_ext
                    in [
                        "jpg",
                        "jpeg",
                        "png",
                        "gif",
                        "webp",
                    ]
                )
            ):
                output_format = first_file_ext
            # Default formats based on media type
            elif media_type == "video":
                output_format = "mkv"
            elif media_type == "audio":
                output_format = "mp3"
            elif media_type == "subtitle":
                output_format = "srt"
            elif media_type == "image":
                output_format = "jpg"
            else:
                output_format = "mkv"

    # Set default output format based on media type if not specified or empty
    elif not output_format or output_format == "none":
        if media_type == "video":
            output_format = "mkv"
        elif media_type == "audio":
            output_format = "mp3"
        elif media_type == "subtitle":
            output_format = "srt"
        elif media_type == "image":
            output_format = "jpg"
        else:
            output_format = "mkv"

    # Check if all files have the same codec for video and audio
    # This is important for concat demuxer to work properly
    if media_type in ["video", "audio"]:
        try:
            import json
            import subprocess

            # Get codec information for all files
            codecs = []
            for file_path in files:
                cmd = [
                    "ffprobe",  # Keep as ffprobe, not xtra
                    "-v",
                    "error",
                    "-select_streams",
                    "v" if media_type == "video" else "a",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "json",
                    file_path,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, check=False
                )
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        data = json.loads(result.stdout)
                        if data.get("streams"):
                            codecs.append(data["streams"][0].get("codec_name", ""))
                        else:
                            # If we can't determine codec, assume it's different
                            codecs.append(f"unknown_{len(codecs)}")
                    except json.JSONDecodeError as e:
                        LOGGER.error(
                            f"Failed to parse ffprobe JSON output for codec detection: {e}"
                        )
                        codecs.append(f"unknown_{len(codecs)}")
                else:
                    # If ffprobe fails, assume it's a different codec
                    codecs.append(f"unknown_{len(codecs)}")

            # Check if all codecs are the same
            if len(set(codecs)) > 1:
                pass
        except Exception:
            pass

    # Create a temporary file list for concat demuxer
    concat_list_path = "concat_list.txt"
    with open(concat_list_path, "w") as f:
        for file_path in files:
            # Escape single quotes in file paths
            escaped_path = file_path.replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")

    # Determine output path based on first file and media type
    base_dir = os.path.dirname(files[0])

    # Use folder name if provided, otherwise use generic names
    if folder_name:
        # Clean folder name for filename use
        clean_folder_name = folder_name.strip("/").replace("/", "_")
        output_file = os.path.join(base_dir, f"{clean_folder_name}.{output_format}")
    # Fallback to generic names
    elif media_type == "video":
        output_file = os.path.join(base_dir, f"merged_video.{output_format}")
    elif media_type == "audio":
        output_file = os.path.join(base_dir, f"merged_audio.{output_format}")
    elif media_type == "subtitle":
        output_file = os.path.join(base_dir, f"merged_subtitle.{output_format}")
    else:
        output_file = os.path.join(base_dir, f"merged.{output_format}")

    # Basic command for concat demuxer
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_list_path,
        "-ignore_unknown",
    ]

    # Add specialized options based on media type
    if media_type == "video":
        # For video files, we need to handle potential codec issues
        # Check if all files have the same codec
        streams_list = []
        for file_path in files:
            streams = await get_streams(file_path)
            if streams:
                streams_list.append(streams)

        # Check if all files have the same codecs
        same_codecs = True
        same_resolution = True
        reference_width = None
        reference_height = None

        # Always add -map 0 to preserve all streams from the input
        cmd.extend(["-map", "0"])

        if streams_list:
            reference_streams = streams_list[0]
            # Check for video dimensions in the first file
            for stream in reference_streams:
                if stream.get("codec_type") == "video" and not stream.get(
                    "disposition", {}
                ).get("attached_pic"):
                    reference_width = stream.get("width")
                    reference_height = stream.get("height")
                    break

            # Compare codecs and dimensions with other files
            for streams in streams_list[1:]:
                if len(streams) != len(reference_streams):
                    same_codecs = False

                # Check for resolution differences
                for stream in streams:
                    if stream.get("codec_type") == "video" and not stream.get(
                        "disposition", {}
                    ).get("attached_pic"):
                        if (
                            stream.get("width") != reference_width
                            or stream.get("height") != reference_height
                        ):
                            same_resolution = False
                        break

                # Check for codec differences
                for i, stream in enumerate(streams):
                    if i >= len(reference_streams):
                        break
                    if stream.get("codec_name") != reference_streams[i].get(
                        "codec_name"
                    ) or stream.get("codec_type") != reference_streams[i].get(
                        "codec_type"
                    ):
                        same_codecs = False
                        break

        LOGGER.info(
            f"Video merge analysis: same_codecs={same_codecs}, same_resolution={same_resolution}"
        )

        if same_codecs and same_resolution:
            # All files have the same codecs and resolution, we can use copy
            # Use -map 0 to preserve all streams including video, audio, and subtitles
            cmd.extend(["-c", "copy"])
            LOGGER.info(
                "Using direct stream copy for identical video files, preserving all streams"
            )
        else:
            # Files have different codecs or resolutions, we need to transcode
            # Use high-quality settings for video and audio, but preserve all streams
            if output_format in ["mp4", "mov"]:
                # For MP4 output, use H.264 for maximum compatibility
                cmd.extend(
                    [
                        # No need to add -map 0 again, it's already added above
                        "-c",
                        "copy",  # Start with copying all streams
                        "-c:v",  # Override video codec only
                        "libx264",
                        "-crf",
                        "18",  # High quality
                        "-preset",
                        "slow",  # Better compression
                        "-c:a",  # Override audio codec only if needed
                        "aac",
                        "-b:a",
                        "192k",
                        "-c:s",  # Override subtitle codec for MP4 compatibility
                        "mov_text",
                    ]
                )
                LOGGER.info(
                    "Using H.264/AAC encoding for MP4 output while preserving all streams"
                )
            elif output_format == "webm":
                # For WebM output, use VP9 and Opus
                cmd.extend(
                    [
                        # No need to add -map 0 again, it's already added above
                        "-c:v",
                        "libvpx-vp9",
                        "-crf",
                        "30",
                        "-b:v",
                        "0",
                        "-c:a",
                        "libopus",
                        "-b:a",
                        "128k",
                        # WebM doesn't support many subtitle formats, so we don't specify -c:s
                    ]
                )
                LOGGER.info(
                    "Using VP9/Opus encoding for WebM output while preserving compatible streams"
                )
            else:
                # For MKV and other formats, use H.264 with high quality
                # MKV supports virtually all codecs, so we can preserve more
                cmd.extend(
                    [
                        # No need to add -map 0 again, it's already added above
                        "-c",
                        "copy",  # Start with copying all streams
                        "-c:v",  # Override video codec only
                        "libx264",
                        "-crf",
                        "18",
                        "-preset",
                        "slow",
                        "-c:a",  # Override audio codec only if needed
                        "aac",
                        "-b:a",
                        "192k",
                        # Keep subtitle copying as is
                    ]
                )
                LOGGER.info(
                    "Using H.264/AAC encoding for MKV output while preserving all streams"
                )

            # If resolutions differ, we need to handle that in filter_complex instead
            if not same_resolution and not same_codecs:
                LOGGER.info(
                    "Videos have different resolutions and codecs, consider using filter_complex instead"
                )
    elif media_type == "audio":
        # For audio files, check if we need to transcode
        streams_list = []
        for file_path in files:
            streams = await get_streams(file_path)
            if streams:
                streams_list.append(streams)

        # Check if all files have the same audio codec
        same_codec = True
        audio_codec = None
        for streams in streams_list:
            for stream in streams:
                if stream.get("codec_type") == "audio":
                    if audio_codec is None:
                        audio_codec = stream.get("codec_name")
                    elif audio_codec != stream.get("codec_name"):
                        same_codec = False
                        break

        LOGGER.info(
            f"Audio merge analysis: same_codec={same_codec}, codec={audio_codec}"
        )

        if same_codec and audio_codec:
            # All files have the same audio codec, we can use copy
            cmd.extend(["-c", "copy"])
            LOGGER.info(
                f"Using direct stream copy for identical audio files with codec {audio_codec}"
            )
        # Files have different audio codecs, we need to transcode
        # Use high-quality settings for audio based on output format
        elif output_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-q:a", "0"])  # Highest quality MP3
            LOGGER.info("Using MP3 encoding with highest quality")
        elif output_format in {"aac", "m4a"}:
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])  # High bitrate AAC
            LOGGER.info("Using AAC encoding with 320k bitrate")
        elif output_format == "flac":
            cmd.extend(["-c:a", "flac"])  # Lossless FLAC
            LOGGER.info("Using lossless FLAC encoding")
        elif output_format == "opus":
            cmd.extend(["-c:a", "libopus", "-b:a", "256k"])  # High quality Opus
            LOGGER.info("Using Opus encoding with 256k bitrate")
        elif output_format == "ogg":
            cmd.extend(["-c:a", "libvorbis", "-q:a", "10"])  # High quality Vorbis
            LOGGER.info("Using Vorbis encoding with quality level 10")
        else:
            # Default to AAC for other formats
            cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            LOGGER.info("Using default AAC encoding with 320k bitrate")
    elif media_type == "subtitle":
        # For subtitle files, we need to handle different formats
        # Check the output format and set appropriate codec
        if output_format == "srt":
            cmd.extend(["-c:s", "srt"])
            LOGGER.info("Using SRT subtitle format")
        elif output_format in {"ass", "ssa"}:
            cmd.extend(["-c:s", "ass"])
            LOGGER.info("Using ASS/SSA subtitle format")
        elif output_format == "vtt":
            cmd.extend(["-c:s", "webvtt"])
            LOGGER.info("Using WebVTT subtitle format")
        else:
            # Default to copy for other formats
            cmd.extend(["-c:s", "copy"])
            LOGGER.info("Using copy for subtitle format")
    elif media_type == "image":
        # For image files, we need to use a different approach
        # This is just a placeholder as concat demuxer doesn't work well for images
        # The actual image merging will be handled by PIL in a separate function
        LOGGER.info(
            "Concat demuxer not suitable for images, use filter_complex or PIL instead"
        )
        return None, None
    else:
        # Default to copy for unknown media types
        cmd.extend(["-c", "copy"])
        LOGGER.info(f"Using copy for unknown media type: {media_type}")

    # Add format-specific optimizations for Telegram compatibility
    if media_type == "video":
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

    # Add threading and output file
    # Use default thread count
    thread_count = max(1, cpu_no // 2)
    cmd.extend(
        [
            "-threads",
            f"{thread_count}",
            output_file,
        ]
    )

    return cmd, output_file


async def get_merge_filter_complex_cmd(
    files, media_type, output_format=None, folder_name=None
):
    """Generate FFmpeg command for merging files using filter_complex.

    Args:
        files: List of file paths to merge
        media_type: Type of media ('video', 'audio', 'subtitle')
        output_format: Output file format (default: based on media_type)
                      If "none", will use the format of the first input file
        folder_name: Optional folder name to use for output filename (from -m flag or extracted folder name)

    Returns:
        tuple: FFmpeg command and output file path
    """
    # Resource manager removed

    if not files:
        return None, None

    # Use files in the order they were provided
    # (No sorting to preserve user's intended order)

    LOGGER.info(
        f"Using filter_complex approach for {media_type} merge with {len(files)} files"
    )

    # Handle "none" output format by using the format of the first input file
    if output_format == "none" and files:
        # Extract extension from the first file
        first_file_ext = os.path.splitext(files[0])[1].lower().lstrip(".")
        if first_file_ext:
            # Use the extension if it's valid
            if (
                (
                    media_type == "video"
                    and first_file_ext
                    in [
                        "mp4",
                        "mkv",
                        "avi",
                        "mov",
                        "webm",
                        "flv",
                    ]
                )
                or (
                    media_type == "audio"
                    and first_file_ext
                    in [
                        "mp3",
                        "aac",
                        "ogg",
                        "wav",
                        "flac",
                        "m4a",
                    ]
                )
                or (
                    media_type == "subtitle"
                    and first_file_ext
                    in [
                        "srt",
                        "ass",
                        "vtt",
                        "sub",
                    ]
                )
            ):
                output_format = first_file_ext
            # Default formats based on media type if extension is not valid
            elif media_type == "video":
                output_format = "mkv"
            elif media_type == "audio":
                output_format = "mp3"
            elif media_type == "subtitle":
                output_format = "srt"
            else:
                output_format = "mkv"
        # No extension found, use default formats based on media type
        elif media_type == "video":
            output_format = "mkv"
        elif media_type == "audio":
            output_format = "mp3"
        elif media_type == "subtitle":
            output_format = "srt"
        else:
            output_format = "mkv"

    # Set default output format based on media type if not specified or empty
    elif not output_format or output_format == "none":
        if media_type == "video":
            output_format = "mkv"
        elif media_type == "audio":
            output_format = "mp3"
        else:
            output_format = "srt"

    # For video and audio, check if we need to handle different resolutions or sample rates
    if media_type in ["video", "audio"]:
        try:
            import json
            import subprocess

            # Get media information for all files
            media_info = []
            for file_path in files:
                info = {}
                # Get codec information
                cmd = [
                    "ffprobe",  # Keep as ffprobe, not xtra
                    "-v",
                    "error",
                    "-select_streams",
                    "v" if media_type == "video" else "a",
                    "-show_entries",
                    "stream=codec_name,width,height,sample_rate,channels",
                    "-of",
                    "json",
                    file_path,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, check=False
                )
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        data = json.loads(result.stdout)
                        if data.get("streams"):
                            stream = data["streams"][0]
                            info["codec"] = stream.get("codec_name", "")
                            if media_type == "video":
                                info["width"] = int(stream.get("width", 0))
                                info["height"] = int(stream.get("height", 0))
                            else:  # audio
                                info["sample_rate"] = int(
                                    stream.get("sample_rate", 0)
                                )
                                info["channels"] = int(stream.get("channels", 0))
                    except json.JSONDecodeError as e:
                        LOGGER.error(
                            f"Failed to parse ffprobe JSON output for media info: {e}"
                        )
                        # Keep default empty info
                media_info.append(info)

            # Log the media information for debugging
            LOGGER.info(f"Media info for {media_type} files: {media_info}")
        except Exception:
            media_info = []

    # Determine output path based on first file and media type
    base_dir = os.path.dirname(files[0])

    # Use folder name if provided, otherwise use generic names
    if folder_name:
        # Clean folder name for filename use
        clean_folder_name = folder_name.strip("/").replace("/", "_")
        output_file = os.path.join(base_dir, f"{clean_folder_name}.{output_format}")
    # Fallback to generic names
    elif media_type == "video":
        output_file = os.path.join(base_dir, f"merged_video.{output_format}")
    elif media_type == "audio":
        output_file = os.path.join(base_dir, f"merged_audio.{output_format}")
    elif media_type == "subtitle":
        output_file = os.path.join(base_dir, f"merged_subtitle.{output_format}")
    else:
        output_file = os.path.join(base_dir, f"merged.{output_format}")

    # Build input arguments
    input_args = []
    for file_path in files:
        input_args.extend(["-i", file_path])

    # Build filter complex string based on media type
    if media_type == "video":
        # For video files, we need to check each file for video and audio streams
        filter_complex = ""
        video_inputs = []
        audio_inputs = []
        subtitle_streams = []  # Track subtitle streams for mapping

        # First, identify which files have video and audio streams
        for i, file_path in enumerate(files):
            streams = await get_streams(file_path)
            if not streams:
                continue

            # Find video, audio, and subtitle streams
            video_stream = None
            audio_stream = None
            for stream in streams:
                if stream.get("codec_type") == "video" and not stream.get(
                    "disposition", {}
                ).get("attached_pic"):
                    video_stream = stream
                elif stream.get("codec_type") == "audio":
                    audio_stream = stream
                elif stream.get("codec_type") == "subtitle":
                    # Track subtitle streams for mapping
                    subtitle_streams.append((i, stream.get("index", 0)))

            # Add video stream if found
            if video_stream:
                video_index = video_stream.get("index", 0)
                video_inputs.append((i, video_index))

            # Add audio stream if found
            if audio_stream:
                audio_index = audio_stream.get("index", 0)
                audio_inputs.append((i, audio_index))

        # If we have video streams, create a video concat filter
        if video_inputs:
            # Check if we need to scale videos to the same dimensions
            need_scaling = False
            target_width = None
            target_height = None

            # First check if all videos have audio streams
            all_have_audio = True

            # Get dimensions of all videos and check for audio streams
            video_dimensions = []
            for i, file_path in enumerate(files):
                streams = await get_streams(file_path)
                if not streams:
                    continue

                has_audio = False
                for stream in streams:
                    if stream.get("codec_type") == "audio":
                        has_audio = True
                        break

                if not has_audio:
                    all_have_audio = False
                    LOGGER.warning(f"Video file {file_path} has no audio stream")

                for stream in streams:
                    if stream.get("codec_type") == "video" and not stream.get(
                        "disposition", {}
                    ).get("attached_pic"):
                        width = stream.get("width")
                        height = stream.get("height")
                        if width and height:
                            video_dimensions.append((i, width, height))
                            if target_width is None or target_height is None:
                                target_width = width
                                target_height = height
                            elif width != target_width or height != target_height:
                                need_scaling = True

            LOGGER.info(f"Video dimensions: {video_dimensions}")
            LOGGER.info(f"All videos have audio: {all_have_audio}")

            # If videos have different dimensions, we need to scale them
            if need_scaling and target_width and target_height:
                LOGGER.info(
                    f"Videos have different dimensions, scaling to {target_width}x{target_height}"
                )
                # Create a new filter complex with scaling and SAR normalization
                scaled_inputs = []
                for i, width, height in video_dimensions:
                    if width != target_width or height != target_height:
                        filter_complex += (
                            f"[{i}:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                            f"setsar=1:1,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2[v{i}];"
                        )
                        scaled_inputs.append(f"[v{i}]")
                    else:
                        # Even if dimensions match, normalize SAR to avoid concat issues
                        filter_complex += f"[{i}:v]setsar=1:1[v{i}];"
                        scaled_inputs.append(f"[v{i}]")

                # Use scaled inputs for concat with appropriate audio handling
                if all_have_audio:
                    # All videos have audio, use video+audio concat
                    video_audio_inputs = []
                    for i, _, _ in video_dimensions:
                        video_audio_inputs.append(f"[v{i}][{i}:a:0]")

                    video_filter = (
                        "".join(video_audio_inputs)
                        + f"concat=n={len(video_dimensions)}:v=1:a=1[outv][outa]"
                    )
                else:
                    # Some videos don't have audio, use video-only concat
                    video_filter = (
                        "".join(scaled_inputs)
                        + f"concat=n={len(scaled_inputs)}:v=1:a=0[outv]"
                    )
            # All videos have the same dimensions, but still normalize SAR
            elif all(dim[0] < len(files) for dim in video_dimensions):
                # Create inputs with SAR normalization
                normalized_inputs = []
                for i, _, _ in video_dimensions:
                    filter_complex += f"[{i}:v]setsar=1:1[v{i}];"
                    normalized_inputs.append(f"[v{i}]")

                # Use normalized inputs for concat with appropriate audio handling
                if all_have_audio:
                    # All videos have audio, use video+audio concat
                    video_audio_inputs = []
                    for i, _, _ in video_dimensions:
                        video_audio_inputs.append(f"[v{i}][{i}:a:0]")

                    video_filter = (
                        "".join(video_audio_inputs)
                        + f"concat=n={len(video_dimensions)}:v=1:a=1[outv][outa]"
                    )
                else:
                    # Some videos don't have audio, use video-only concat
                    video_filter = (
                        "".join(normalized_inputs)
                        + f"concat=n={len(normalized_inputs)}:v=1:a=0[outv]"
                    )
            # Fallback to original approach if there's an issue with dimensions
            elif all_have_audio and not audio_inputs:
                # All videos have audio and no separate audio processing needed, use video+audio concat
                video_audio_inputs = []
                for i, idx in video_inputs:
                    video_audio_inputs.append(f"[{i}:v:{idx}][{i}:a:0]")

                video_filter = (
                    "".join(video_audio_inputs)
                    + f"concat=n={len(video_inputs)}:v=1:a=1[outv][outa]"
                )
            else:
                # Use video-only concat (either some videos don't have audio or we'll handle audio separately)
                video_filter = (
                    "".join([f"[{i}:v:{idx}]" for i, idx in video_inputs])
                    + f"concat=n={len(video_inputs)}:v=1:a=0[outv]"
                )

            if filter_complex and not filter_complex.endswith(";"):
                filter_complex += ";"
            filter_complex += video_filter

        # If we have audio streams, create an audio concat filter
        if audio_inputs:
            if filter_complex and not filter_complex.endswith(";"):
                filter_complex += ";"  # Separator for multiple filters

            # Use a safer approach for audio inputs
            # First check if the audio stream exists in each file
            valid_audio_inputs = []
            for i, file_path in enumerate(files):
                streams = await get_streams(file_path)
                if not streams:
                    continue

                # Find all audio streams in each file
                audio_stream_count = 0
                for stream in streams:
                    if stream.get("codec_type") == "audio":
                        # Use actual stream index for more reliable mapping
                        stream_index = stream.get("index", audio_stream_count)
                        valid_audio_inputs.append((i, stream_index))
                        audio_stream_count += 1
                        LOGGER.info(
                            f"Found audio stream in file {i}: index={stream_index}, codec={stream.get('codec_name')}"
                        )

            if valid_audio_inputs:
                # Group audio inputs by file to preserve all audio tracks
                audio_inputs_by_file = {}
                for i, idx in valid_audio_inputs:
                    if i not in audio_inputs_by_file:
                        audio_inputs_by_file[i] = []
                    audio_inputs_by_file[i].append(idx)

                # Create separate concat filters for each audio track position
                audio_track_count = max(
                    len(inputs) for inputs in audio_inputs_by_file.values()
                )
                LOGGER.info(
                    f"Found {audio_track_count} audio track positions across {len(audio_inputs_by_file)} files"
                )

                # If we have multiple audio tracks, create a separate concat filter for each position
                if audio_track_count > 0:
                    for track_pos in range(audio_track_count):
                        # Collect inputs for this track position from each file
                        track_inputs = []
                        for file_idx, track_indices in audio_inputs_by_file.items():
                            if track_pos < len(track_indices):
                                track_inputs.append(
                                    (file_idx, track_indices[track_pos])
                                )

                        if track_inputs:
                            # Create concat filter for this track position
                            if filter_complex and not filter_complex.endswith(";"):
                                filter_complex += ";"
                            audio_filter = (
                                "".join(
                                    [f"[{i}:a:{idx}]" for i, idx in track_inputs]
                                )
                                + f"concat=n={len(track_inputs)}:v=0:a=1[outa{track_pos}]"
                            )
                            filter_complex += audio_filter
                            LOGGER.info(
                                f"Created audio concat filter for track position {track_pos} with {len(track_inputs)} inputs"
                            )
                else:
                    pass
            else:
                pass

        # Set up mapping based on available streams
        map_args = []

        # First map the merged video stream
        if video_inputs:
            map_args.extend(["-map", "[outv]"])
            # Set video codec based on output format
            if output_format == "mp4":
                map_args.extend(["-c:v", "libx264", "-crf", "18"])
            elif output_format == "webm":
                map_args.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"])
            else:  # Default for mkv and others
                map_args.extend(["-c:v", "libx264", "-crf", "18"])

        # Map audio streams from filter_complex outputs
        # Check for [outaX] patterns in filter_complex
        import re

        outa_pattern = r"\[outa(\d*)\]"
        outa_matches = re.findall(outa_pattern, filter_complex)

        if outa_matches:
            # Map all audio outputs from filter_complex
            # Use set to avoid duplicate mappings
            mapped_tracks = set()
            for match in outa_matches:
                track_num = match if match else "0"
                track_label = f"[outa{track_num}]"
                if track_label not in mapped_tracks:
                    map_args.extend(["-map", track_label])
                    mapped_tracks.add(track_label)
                    LOGGER.info(
                        f"Mapping audio track from filter_complex: {track_label}"
                    )
        elif "[outa]" in filter_complex:
            # Single audio track from filter_complex
            map_args.extend(["-map", "[outa]"])
            LOGGER.info("Mapping single audio track from filter_complex: [outa]")
        # Check if we have videos without audio
        elif video_inputs and not all_have_audio:
            LOGGER.info(
                "Some videos don't have audio, mapping available audio streams"
            )
            # Map available audio streams with optional flag
            audio_track_count = 0
            for i, file_path in enumerate(files):
                streams = await get_streams(file_path)
                if not streams:
                    continue

                # Find and map all audio streams
                for stream in streams:
                    if stream.get("codec_type") == "audio":
                        audio_index = stream.get("index", 0)
                        map_args.extend(
                            ["-map", f"{i}:a:{audio_index}?"]
                        )  # Add ? to make it optional
                        audio_track_count += 1

            LOGGER.info(
                f"Directly mapping {audio_track_count} audio tracks from input files"
            )
        else:
            # Otherwise, map all audio streams from all input files directly
            audio_track_count = 0
            for i, file_path in enumerate(files):
                streams = await get_streams(file_path)
                if not streams:
                    continue

                # Find and map all audio streams
                for stream in streams:
                    if stream.get("codec_type") == "audio":
                        audio_index = stream.get("index", 0)
                        map_args.extend(
                            ["-map", f"{i}:a:{audio_index}?"]
                        )  # Add ? to make it optional
                        audio_track_count += 1

            LOGGER.info(
                f"Directly mapping {audio_track_count} audio tracks from input files"
            )

        # Set audio codec based on output format
        if output_format == "mp4":
            map_args.extend(["-c:a", "aac", "-b:a", "192k"])
        elif output_format == "webm":
            map_args.extend(["-c:a", "libopus", "-b:a", "128k"])
        else:  # Default for mkv and others
            map_args.extend(["-c:a", "aac", "-b:a", "192k"])

        # Now map all subtitle streams from all input files
        # This preserves all subtitle tracks in the merged output
        for i, file_path in enumerate(files):
            streams = await get_streams(file_path)
            if not streams:
                continue

            # Find and map all subtitle streams
            for stream in streams:
                if stream.get("codec_type") == "subtitle":
                    subtitle_index = stream.get("index", 0)
                    # Add a question mark to make the mapping optional
                    # This prevents errors when a subtitle stream doesn't exist
                    map_args.extend(["-map", f"{i}:s:{subtitle_index}?"])
                    LOGGER.info(
                        f"Mapping subtitle track from file {i}: index={subtitle_index}, codec={stream.get('codec_name')}"
                    )

        # Set subtitle codec based on output format
        if output_format == "mp4":
            map_args.extend(["-c:s", "mov_text"])  # MP4 compatible subtitles
        else:  # For MKV and other formats that support most subtitle formats
            map_args.extend(["-c:s", "copy"])  # Copy subtitle streams as is

        # Add metadata to indicate this is a merged file
        map_args.extend(["-metadata", "title=Merged Video"])

        # If no valid streams found, use a simpler approach
        if not filter_complex:
            return None, None

    elif media_type == "audio":
        # For audio files, check if we need to normalize audio levels
        normalize_audio = False  # Set to True to enable audio normalization

        if normalize_audio:
            # First pass: analyze audio levels
            filter_complex = ""
            for i, _ in enumerate(files):
                filter_complex += f"[{i}:a:0]loudnorm=print_format=json[a{i}];"

            # Second pass: normalize and concat
            for i, _ in enumerate(files):
                filter_complex += f"[a{i}]"
            filter_complex += f"concat=n={len(files)}:v=0:a=1[outa]"
        else:
            # Simple concat without normalization
            filter_complex = ""
            for i, _ in enumerate(files):
                filter_complex += f"[{i}:a:0]"
            filter_complex += f"concat=n={len(files)}:v=0:a=1[outa]"

        map_args = ["-map", "[outa]"]

        # Set audio codec based on output format
        if output_format == "mp3":
            map_args.extend(["-c:a", "libmp3lame", "-q:a", "0"])
        elif output_format in {"aac", "m4a"}:
            map_args.extend(["-c:a", "aac", "-b:a", "320k"])
        elif output_format == "flac":
            map_args.extend(["-c:a", "flac"])
        elif output_format == "opus":
            map_args.extend(["-c:a", "libopus", "-b:a", "256k"])
        else:
            # Default to AAC for other formats
            map_args.extend(["-c:a", "aac", "-b:a", "320k"])

    elif media_type == "subtitle":
        # For subtitle files, we'll use a custom approach for merging
        # This is a more advanced approach than just copying the first file

        # Check the subtitle formats
        subtitle_formats = [os.path.splitext(f)[1][1:].lower() for f in files]
        LOGGER.info(f"Merging subtitle files with formats: {subtitle_formats}")

        # Check if we need to convert formats
        need_conversion = len(set(subtitle_formats)) > 1
        if need_conversion:
            LOGGER.info(
                "Different subtitle formats detected, will convert to SRT before merging"
            )

            # For SRT files or if we need to convert to SRT
            # For SRT files, we can use a special approach to merge them
            # We'll create a temporary script to merge SRT files with proper timing
            # Use raw string to avoid escape sequence issues
            merge_script = r"""#!/usr/bin/env python3
import sys
import re

def parse_time(time_str):
    h, m, s = time_str.replace(',', '.').split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace('.', ',')

def parse_srt(content):
    pattern = r'(\\d+)\\s+(\\d{2}:\\d{2}:\\d{2},\\d{3}) --> (\\d{2}:\\d{2}:\\d{2},\\d{3})\\s+(.*?)(?=\\n\\d+\\s+\\d{2}:\\d{2}:\\d{2},\\d{3}|$)'
    matches = re.findall(pattern, content, re.DOTALL)
    return [(int(idx), start, end, text.strip()) for idx, start, end, text in matches]

def parse_vtt(content):
    # Remove WEBVTT header if present
    if content.startswith('WEBVTT'):
        content = '\n'.join(content.split('\n')[2:])

    # VTT format: HH:MM:SS.mmm --> HH:MM:SS.mmm
    pattern = r'(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\s+(.*?)(?=\n\n|$)'
    matches = re.findall(pattern, content, re.DOTALL)

    # Convert to SRT-like format with indices
    result = []
    for i, (start, end, text) in enumerate(matches, 1):
        # Convert VTT timestamp format to SRT format
        start_srt = start.replace('.', ',')
        end_srt = end.replace('.', ',')
        result.append((i, start_srt, end_srt, text.strip()))

    return result

def parse_ass(content):
    # Extract events section
    events_section = re.search(r'\[Events\].*?Format:.*?\n(.*)', content, re.DOTALL)
    if not events_section:
        return []

    events_text = events_section.group(1)

    # Extract dialogue lines
    dialogue_pattern = r'Dialogue: [^,]*,([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),(.*)'
    matches = re.findall(dialogue_pattern, events_text)

    result = []
    for i, match in enumerate(matches, 1):
        start_time = match[1].strip()
        end_time = match[2].strip()
        text = match[8].strip()

        # Convert ASS timestamp format (H:MM:SS.cc) to SRT format (HH:MM:SS,mmm)
        start_parts = start_time.split(':')
        if len(start_parts) == 2:  # MM:SS.cc
            start_srt = f"00:{start_parts[0]}:{start_parts[1]}".replace('.', ',')
        else:  # H:MM:SS.cc
            h = start_parts[0].zfill(2)
            start_srt = f"{h}:{start_parts[1]}:{start_parts[2]}".replace('.', ',')

        end_parts = end_time.split(':')
        if len(end_parts) == 2:  # MM:SS.cc
            end_srt = f"00:{end_parts[0]}:{end_parts[1]}".replace('.', ',')
        else:  # H:MM:SS.cc
            h = end_parts[0].zfill(2)
            end_srt = f"{h}:{end_parts[1]}:{end_parts[2]}".replace('.', ',')

        result.append((i, start_srt, end_srt, text))

    return result

def detect_subtitle_format(file_path):
    # Detect subtitle format based on file extension and content
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.srt':
        return 'srt'
    elif ext == '.vtt':
        return 'vtt'
    elif ext in ['.ass', '.ssa']:
        return 'ass'

    # If extension is not recognized, try to detect from content
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(1000)  # Read first 1000 chars

        if content.startswith('WEBVTT'):
            return 'vtt'
        elif '[Script Info]' in content and '[Events]' in content:
            return 'ass'
        elif re.search(r'\d+\s+\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', content):
            return 'srt'
    except Exception:
        pass

    # Default to SRT if we can't determine
    return 'srt'

def merge_subtitle_files(file_paths):
    all_subtitles = []
    current_offset = 0

    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # Detect format and parse accordingly
            format_type = detect_subtitle_format(file_path)
            if format_type == 'srt':
                subtitles = parse_srt(content)
            elif format_type == 'vtt':
                subtitles = parse_vtt(content)
            elif format_type == 'ass':
                subtitles = parse_ass(content)
            else:
                # Default to SRT parser
                subtitles = parse_srt(content)

            if not subtitles:
                continue

            # Get the last end time from previous file
            if all_subtitles:
                last_end_time = parse_time(all_subtitles[-1][2])
            else:
                last_end_time = 0

            # Adjust timing for current file
            for idx, start, end, text in subtitles:
                start_time = parse_time(start) + current_offset
                end_time = parse_time(end) + current_offset

                # Handle overlapping timestamps
                if all_subtitles and start_time < last_end_time:
                    # Option 1: Shift this subtitle to start after the last one
                    start_time = last_end_time + 0.1
                    end_time = max(end_time, start_time + 1.0)  # Ensure at least 1 second duration

                all_subtitles.append((len(all_subtitles) + 1, format_time(start_time), format_time(end_time), text))
                last_end_time = end_time

            # Update offset for next file
            if subtitles:
                current_offset = parse_time(all_subtitles[-1][2]) + 0.5  # Add a small gap between files
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            continue

    # Sort subtitles by start time to handle any potential overlaps
    all_subtitles.sort(key=lambda x: parse_time(x[1]))

    # Renumber subtitles after sorting
    all_subtitles = [(i+1, start, end, text) for i, (_, start, end, text) in enumerate(all_subtitles)]

    # Generate merged SRT content
    merged_content = ""
    for idx, start, end, text in all_subtitles:
        merged_content += f"{idx}\n{start} --> {end}\n{text}\n\n"

    return merged_content

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python merge_srt.py output.srt input1.srt input2.srt ...")
        sys.exit(1)

    output_file = sys.argv[1]
    input_files = sys.argv[2:]

    merged_content = merge_subtitle_files(input_files)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(merged_content)
"""

            # Save the merge script
            script_path = "merge_srt.py"
            with open(script_path, "w") as f:
                f.write(merge_script)

            # Create a command to run the script
            cmd = ["python3", script_path, output_file, *files]

            # Run the script to merge SRT files
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            await process.communicate()

            # Check if the output file was created
            if os.path.exists(output_file):
                return ["echo", "Subtitle merge completed"], output_file
            # Fallback to copying the first subtitle file
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                files[0],
                "-c",
                "copy",
                "-threads",
                f"{max(1, cpu_no // 2)}",
                output_file,
            ]
            return cmd, output_file
        # For other subtitle formats, just copy the first file as a placeholder
        cmd = [
            "xtra",
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            "-i",
            files[0],
            "-c",
            "copy",
            "-threads",
            f"{max(1, cpu_no // 2)}",
            output_file,
        ]
        return cmd, output_file
    else:
        return None, None

    # Use default thread count
    thread_count = max(1, cpu_no // 2)

    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        *input_args,
        "-ignore_unknown",
        "-filter_complex",
        filter_complex,
        *map_args,
        "-threads",
        f"{thread_count}",
        output_file,
    ]

    return cmd, output_file


async def get_merge_mixed_cmd(
    video_files,
    audio_files,
    subtitle_files,
    output_format="mkv",
    folder_name=None,
    # codec_groups parameter removed - will be added back when implemented
):
    import os

    # Resource manager removed

    """Generate FFmpeg command for merging mixed media types.

    Args:
        video_files: List of video file paths
        audio_files: List of audio file paths
        subtitle_files: List of subtitle file paths
        output_format: Output file format (default: mkv)
                      If "none", will use the format of the first input file

    Returns:
        tuple: FFmpeg command and output file path
    """
    # Note: codec_groups parameter is reserved for future use to optimize codec selection
    if not video_files and not audio_files:
        return None, None

    # Handle "none" output format by using the format of the first input file
    if output_format == "none":
        # Determine which files to use for format detection
        files_to_check = []
        if video_files:
            files_to_check = video_files
        elif audio_files:
            files_to_check = audio_files
        elif subtitle_files:
            files_to_check = subtitle_files

        if files_to_check:
            # Extract extension from the first file
            first_file_ext = (
                os.path.splitext(files_to_check[0])[1].lower().lstrip(".")
            )
            if first_file_ext:
                # Use the extension if it's valid
                if (
                    video_files
                    and first_file_ext
                    in [
                        "mp4",
                        "mkv",
                        "avi",
                        "mov",
                        "webm",
                        "flv",
                    ]
                ) or (
                    audio_files
                    and first_file_ext
                    in [
                        "mp3",
                        "aac",
                        "ogg",
                        "wav",
                        "flac",
                        "m4a",
                    ]
                ):
                    output_format = first_file_ext
                else:
                    # Default to mkv for mixed media
                    output_format = "mkv"
            else:
                output_format = "mkv"
        else:
            output_format = "mkv"

    # Use files in the order they were provided
    # (No sorting to preserve user's intended order)
    video_files = video_files if video_files else []
    audio_files = audio_files if audio_files else []
    subtitle_files = subtitle_files if subtitle_files else []

    # Determine output path based on first available file and media types
    base_files = video_files or audio_files or subtitle_files
    base_dir = os.path.dirname(base_files[0])

    # Determine appropriate output file name based on media types
    if folder_name:
        # Clean folder name for filename use
        clean_folder_name = folder_name.strip("/").replace("/", "_")
        output_file = os.path.join(base_dir, f"{clean_folder_name}.{output_format}")
    # Fallback to generic names
    elif video_files:
        output_file = os.path.join(base_dir, f"merged_video.{output_format}")
    elif audio_files:
        output_file = os.path.join(base_dir, f"merged_audio.{output_format}")
    elif subtitle_files:
        output_file = os.path.join(base_dir, f"merged_subtitle.{output_format}")
    else:
        output_file = os.path.join(base_dir, f"merged.{output_format}")

    # For mixed media types, we have several approaches:
    # 1. If we have multiple video files, merge them first, then add audio and subtitles
    # 2. If we have one video file and multiple audio files, use the video as base and add all audio tracks
    # 3. If we have multiple audio files only, merge them using filter_complex

    # Approach 1: Multiple video files with or without audio/subtitles
    if len(video_files) > 1:
        # First, merge all video files using concat demuxer
        # Create a temporary file list for concat demuxer
        concat_list_path = "concat_list.txt"
        with open(concat_list_path, "w") as f:
            for file_path in video_files:
                # Escape single quotes in file paths
                escaped_path = file_path.replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        # Create a temporary merged video file
        temp_video_output = os.path.join(
            base_dir, f"temp_merged_video.{output_format}"
        )
        video_cmd = [
            "xtra",
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-map",
            "0",  # Map all streams from input to preserve all video and audio tracks
            "-c",
            "copy",
            "-metadata",
            "title=Merged Video",
        ]

        # Add format-specific optimizations for Telegram compatibility
        temp_video_ext = os.path.splitext(temp_video_output)[1].lower()
        if temp_video_ext == ".mp4":
            video_cmd.extend(
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
        elif temp_video_ext == ".mkv":
            video_cmd.extend(
                [
                    "-pix_fmt",
                    "yuv420p",  # Compatible pixel format
                    "-disposition:v:0",
                    "default",  # Set video as default
                    "-disposition:a:0",
                    "default",  # Set audio as default
                ]
            )
        elif temp_video_ext == ".webm":
            video_cmd.extend(
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
        elif temp_video_ext == ".mov":
            video_cmd.extend(
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
            video_cmd.extend(["-pix_fmt", "yuv420p"])

        video_cmd.extend(
            [
                "-threads",
                f"{max(1, cpu_no // 2)}",
                temp_video_output,
            ]
        )

        # If we have audio files, add them to the merged video
        if audio_files:
            # Build input arguments
            input_args = ["-i", temp_video_output]  # Merged video as first input
            map_args = [
                "-map",
                "0",
            ]  # Map all streams from merged video to preserve all tracks

            # Add audio files
            for i, audio_file in enumerate(audio_files):
                input_args.extend(["-i", audio_file])
                map_args.extend(
                    [
                        "-map",
                        f"{i + 1}:a:0",
                        f"-metadata:s:a:{i}",
                        f"title=Audio Track {i + 1}",
                    ]
                )

            # Add subtitle files if supported by the output format
            if subtitle_files and output_format in ["mkv", "mp4"]:
                for i, sub_file in enumerate(subtitle_files):
                    input_args.extend(["-i", sub_file])
                    map_args.extend(
                        [
                            "-map",
                            f"{i + 1 + len(audio_files)}:s?",
                            f"-metadata:s:s:{i}",
                            f"title=Subtitle Track {i + 1}",
                        ]
                    )

            # Use default thread count
            thread_count = max(1, cpu_no // 2)

            # Create final command
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                *input_args,
                "-ignore_unknown",
                *map_args,  # Map all streams including video, audio, and subtitle streams
                "-c",
                "copy",
            ]

            # Add format-specific optimizations for Telegram compatibility
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
                    f"{thread_count}",
                    output_file,
                ]
            )

            return cmd, output_file
        # Just return the merged video command
        return video_cmd, temp_video_output

    # Approach 2: Single video file with multiple audio/subtitle tracks
    if len(video_files) == 1:
        # Use the video file as the base
        video_base = video_files[0]

        # Get video stream info
        video_streams = await get_streams(video_base)
        if not video_streams:
            return None, None

        # Log video stream info for debugging
        LOGGER.info(f"Using video file as base: {video_base}")
        video_info = {}
        for stream in video_streams:
            if stream.get("codec_type") == "video":
                video_info["codec"] = stream.get("codec_name")
                video_info["width"] = stream.get("width")
                video_info["height"] = stream.get("height")
                video_info["duration"] = stream.get("duration")
                break
        LOGGER.info(f"Video base info: {video_info}")

        # Build input arguments
        input_args = ["-i", video_base]
        map_args = [
            "-map",
            "0",
        ]  # Map all streams from the video file to preserve all tracks

        # Count audio tracks in video file for metadata
        audio_tracks_in_video = 0
        for stream in video_streams:
            if stream.get("codec_type") == "audio":
                audio_tracks_in_video += 1

        has_audio_in_video = audio_tracks_in_video > 0

        # Add external audio files
        audio_track_num = 1 if has_audio_in_video else 0
        for i, audio_file in enumerate(audio_files):
            input_args.extend(["-i", audio_file])
            map_args.extend(
                [
                    "-map",
                    f"{i + 1}:a:0",
                    f"-metadata:s:a:{audio_track_num}",
                    f"title=External Audio {i + 1}",
                ]
            )
            audio_track_num += 1

        # Add subtitle files if supported by the output format
        if subtitle_files and output_format in ["mkv", "mp4"]:
            sub_offset = len(audio_files) + 1
            for i, sub_file in enumerate(subtitle_files):
                # Get subtitle format
                sub_format = os.path.splitext(sub_file)[1].lower()

                # Handle subtitles differently based on format
                if sub_format in [".srt", ".vtt", ".ass", ".ssa"]:
                    # For text-based subtitles, we need to handle them specially to fix duration issues
                    # First, get video duration
                    video_duration = None
                    video_streams = await get_streams(video_base)
                    if video_streams:
                        for stream in video_streams:
                            if stream.get("codec_type") == "video":
                                # Try to get duration from stream or format info
                                try:
                                    import json
                                    import subprocess

                                    cmd = [
                                        "ffprobe",  # Keep as ffprobe, not xtra
                                        "-v",
                                        "error",
                                        "-show_entries",
                                        "format=duration",
                                        "-of",
                                        "json",
                                        video_base,
                                    ]
                                    result = subprocess.run(
                                        cmd,
                                        capture_output=True,
                                        text=True,
                                        check=False,
                                    )
                                    if result.returncode == 0:
                                        data = json.loads(result.stdout)
                                        if (
                                            "format" in data
                                            and "duration" in data["format"]
                                        ):
                                            video_duration = float(
                                                data["format"]["duration"]
                                            )
                                except Exception:
                                    pass

                    # If we have video duration, create a temporary subtitle file with correct duration
                    if video_duration:
                        LOGGER.info(
                            f"Using video duration {video_duration} for subtitle"
                        )
                        # Create a temporary subtitle file with adjusted timestamps
                        try:
                            import os
                            import re
                            import tempfile

                            # Create a temporary file for the adjusted subtitle
                            temp_sub_file = tempfile.NamedTemporaryFile(
                                suffix=".srt", delete=False
                            )
                            temp_sub_path = temp_sub_file.name
                            temp_sub_file.close()

                            # Read the original subtitle file
                            with open(sub_file, encoding="utf-8") as f:
                                content = f.read()

                            # Find the last timestamp in the subtitle file
                            last_timestamp_match = re.findall(
                                r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})",
                                content,
                            )
                            if last_timestamp_match:
                                # Get the last end timestamp
                                last_end_time = last_timestamp_match[-1][1]

                                # Convert timestamp to seconds
                                h, m, s = last_end_time.split(":")[0:3]
                                s, ms = s.split(",")
                                last_time_seconds = (
                                    int(h) * 3600
                                    + int(m) * 60
                                    + int(s)
                                    + int(ms) / 1000
                                )

                                # If the last subtitle timestamp is beyond video duration or too short, adjust all timestamps
                                if (
                                    last_time_seconds > video_duration
                                    or last_time_seconds < (video_duration * 0.5)
                                ):
                                    # If subtitle is too short, extend it. If too long, compress it.
                                    scale_factor = video_duration / last_time_seconds
                                    LOGGER.info(
                                        f"Adjusting subtitle timing with scale factor {scale_factor:.2f} (subtitle duration: {last_time_seconds:.2f}s, video duration: {video_duration:.2f}s)"
                                    )

                                    # Function to adjust timestamp
                                    def adjust_timestamp(timestamp, scale):
                                        h, m, s = timestamp.split(":")[0:3]
                                        s, ms = s.split(",")
                                        total_seconds = (
                                            int(h) * 3600
                                            + int(m) * 60
                                            + int(s)
                                            + int(ms) / 1000
                                        ) * scale

                                        new_h = int(total_seconds // 3600)
                                        new_m = int((total_seconds % 3600) // 60)
                                        new_s = int(total_seconds % 60)
                                        new_ms = int((total_seconds * 1000) % 1000)

                                        return f"{new_h:02d}:{new_m:02d}:{new_s:02d},{new_ms:03d}"

                                    # Adjust all timestamps in the subtitle file
                                    adjusted_content = re.sub(
                                        r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})",
                                        lambda m: f"{adjust_timestamp(m.group(1), scale_factor)} --> {adjust_timestamp(m.group(2), scale_factor)}",
                                        content,
                                    )

                                    # Write the adjusted subtitle to the temporary file
                                    with open(
                                        temp_sub_path, "w", encoding="utf-8"
                                    ) as f:
                                        f.write(adjusted_content)

                                    # Use the temporary subtitle file instead
                                    sub_file = temp_sub_path
                                    LOGGER.info(
                                        f"Created adjusted subtitle file with scale factor {scale_factor}"
                                    )
                        except Exception:
                            pass

                        # Add input with the adjusted subtitle file
                        input_args.extend(["-i", sub_file])
                        map_args.extend(
                            [
                                "-map",
                                f"{sub_offset + i}:s?",
                                f"-metadata:s:s:{i}",
                                f"title=External Subtitle {i + 1}",
                                # Force subtitle duration to match video
                                "-c:s",
                                "copy",
                            ]
                        )
                    else:
                        # Fallback to standard mapping
                        input_args.extend(["-i", sub_file])
                        map_args.extend(
                            [
                                "-map",
                                f"{sub_offset + i}:s?",
                                f"-metadata:s:s:{i}",
                                f"title=External Subtitle {i + 1}",
                                "-c:s",
                                "copy",
                            ]
                        )
                else:
                    # For other subtitle formats, use standard mapping
                    input_args.extend(["-i", sub_file])
                    map_args.extend(
                        [
                            "-map",
                            f"{sub_offset + i}:s?",
                            f"-metadata:s:s:{i}",
                            f"title=External Subtitle {i + 1}",
                        ]
                    )

        # Use default thread count
        thread_count = max(1, cpu_no // 2)

        # Create final command
        cmd = [
            "xtra",
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            *input_args,
            "-ignore_unknown",
            *map_args,  # Map all streams including video, audio, and subtitle streams
            "-c",
            "copy",
            "-threads",
            f"{thread_count}",
            output_file,
        ]

        return cmd, output_file

    # Approach 3: Audio files only
    if audio_files:
        # For audio-only merge, use filter_complex
        filter_complex = ""
        for i, _ in enumerate(audio_files):
            filter_complex += f"[{i}:a:0]"
        filter_complex += f"concat=n={len(audio_files)}:v=0:a=1[outa]"

        # Build input arguments
        input_args = []
        for file_path in audio_files:
            input_args.extend(["-i", file_path])

        # Set audio codec based on output format
        codec_args = []
        if output_format == "mp3":
            codec_args = ["-c:a", "libmp3lame", "-q:a", "0"]
        elif output_format in {"aac", "m4a"}:
            codec_args = ["-c:a", "aac", "-b:a", "320k"]
        elif output_format == "flac":
            codec_args = ["-c:a", "flac"]
        elif output_format == "opus":
            codec_args = ["-c:a", "libopus", "-b:a", "256k"]
        else:
            # Default to AAC for other formats
            codec_args = ["-c:a", "aac", "-b:a", "320k"]

        # Use default thread count
        thread_count = max(1, cpu_no // 2)

        cmd = [
            "xtra",
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            *input_args,
            "-filter_complex",
            filter_complex,
            "-map",
            "[outa]",
            *codec_args,
            "-threads",
            f"{thread_count}",
            output_file,
        ]

        return cmd, output_file

    # Fallback to a simpler approach if needed
    # This approach works for a single video file with a single audio file and optional subtitle
    if len(video_files) == 1 and len(audio_files) <= 1:
        # Build input arguments
        input_args = ["-i", video_files[0]]  # Video file
        map_args = [
            "-map",
            "0",
        ]  # Map all streams from video file to preserve all tracks

        # Add external audio file if available
        if audio_files:
            input_args.extend(["-i", audio_files[0]])
            map_args.extend(
                ["-map", "1:a:0", "-metadata:s:a:0", "title=External Audio"]
            )

        # Add subtitle file if available and supported by the output format
        if subtitle_files and output_format in ["mkv", "mp4"]:
            sub_file = subtitle_files[0]
            # Get subtitle format
            sub_format = os.path.splitext(sub_file)[1].lower()

            # Handle subtitles differently based on format
            if sub_format in [".srt", ".vtt", ".ass", ".ssa"]:
                # For text-based subtitles, we need to handle them specially to fix duration issues
                # First, get video duration
                video_duration = None
                video_streams = await get_streams(video_files[0])
                if video_streams:
                    try:
                        import json
                        import subprocess

                        cmd = [
                            "ffprobe",  # Keep as ffprobe, not xtra
                            "-v",
                            "error",
                            "-show_entries",
                            "format=duration",
                            "-of",
                            "json",
                            video_files[0],
                        ]
                        result = subprocess.run(
                            cmd, capture_output=True, text=True, check=False
                        )
                        if result.returncode == 0:
                            data = json.loads(result.stdout)
                            if "format" in data and "duration" in data["format"]:
                                video_duration = float(data["format"]["duration"])
                    except Exception:
                        pass

                # Create a temporary subtitle file with adjusted timestamps
                try:
                    # Read the original subtitle file
                    with open(sub_file, encoding="utf-8") as f:
                        content = f.read()

                    # Find the last timestamp in the subtitle file
                    last_timestamp_match = re.findall(
                        r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})",
                        content,
                    )
                    if last_timestamp_match:
                        # Get the last end timestamp
                        last_end_time = last_timestamp_match[-1][1]

                        # Convert timestamp to seconds
                        h, m, s = last_end_time.split(":")[0:3]
                        s, ms = s.split(",")
                        last_time_seconds = (
                            int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
                        )

                        # If the last subtitle timestamp is beyond video duration, adjust all timestamps
                        if last_time_seconds > video_duration:
                            scale_factor = video_duration / last_time_seconds

                            # Function to adjust timestamp
                            def adjust_timestamp(timestamp, scale):
                                h, m, s = timestamp.split(":")[0:3]
                                s, ms = s.split(",")
                                total_seconds = (
                                    int(h) * 3600
                                    + int(m) * 60
                                    + int(s)
                                    + int(ms) / 1000
                                ) * scale

                                new_h = int(total_seconds // 3600)
                                new_m = int((total_seconds % 3600) // 60)
                                new_s = int(total_seconds % 60)
                                new_ms = int((total_seconds * 1000) % 1000)

                                return f"{new_h:02d}:{new_m:02d}:{new_s:02d},{new_ms:03d}"

                            # Adjust all timestamps in the subtitle file
                            adjusted_content = re.sub(
                                r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})",
                                lambda m: f"{adjust_timestamp(m.group(1), scale_factor)} --> {adjust_timestamp(m.group(2), scale_factor)}",
                                content,
                            )

                            # Create a temporary file for the adjusted subtitle
                            temp_sub_file = tempfile.NamedTemporaryFile(
                                suffix=".srt", delete=False
                            )
                            temp_sub_path = temp_sub_file.name
                            temp_sub_file.close()

                            # Write the adjusted subtitle to the temporary file
                            with open(temp_sub_path, "w", encoding="utf-8") as f:
                                f.write(adjusted_content)

                            # Use the temporary subtitle file instead
                            sub_file = temp_sub_path

                except Exception:
                    pass

                # Add input with the adjusted subtitle file
                input_args.extend(["-i", sub_file])

                # Map subtitle with appropriate options
                map_args.extend(
                    [
                        "-map",
                        f"{1 + (1 if audio_files else 0)}:s?",
                        "-metadata:s:s:0",
                        "title=External Subtitle",
                        # Force subtitle duration to match video
                        "-c:s",
                        "copy",
                    ]
                )
            else:
                # For other subtitle formats, use standard mapping
                input_args.extend(["-i", sub_file])
                map_args.extend(
                    [
                        "-map",
                        f"{1 + (1 if audio_files else 0)}:s?",
                        "-metadata:s:s:0",
                        "title=External Subtitle",
                    ]
                )

        cmd = [
            "xtra",
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            *input_args,
            *map_args,
            "-c",
            "copy",
            "-threads",
            f"{max(1, cpu_no // 2)}",
            output_file,
        ]

        return cmd, output_file

    # If all else fails, use a very simple approach
    # Just use the first video file and preserve all its tracks
    if video_files:
        cmd = [
            "xtra",
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            "-i",
            video_files[0],
            "-map",
            "0",  # Map all streams to preserve all video, audio, and subtitle tracks
            "-c",
            "copy",
            "-threads",
            f"{max(1, cpu_no // 2)}",
            output_file,
        ]
        return cmd, output_file

    # If no video files, use the first audio file and preserve all its tracks
    if audio_files:
        cmd = [
            "xtra",
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            "-i",
            audio_files[0],
            "-map",
            "0",  # Map all streams to preserve all audio tracks
            "-c",
            "copy",
            "-threads",
            f"{max(1, cpu_no // 2)}",
            output_file,
        ]
        return cmd, output_file

    return None, None


async def analyze_media_for_merge(files):
    """Analyze media files and categorize them for merging.

    Args:
        files: List of file paths

    Returns:
        dict: Dictionary with categorized files and recommended merge approach
    """
    video_files = []
    audio_files = []
    subtitle_files = []
    image_files = []
    document_files = []
    unknown_files = []

    # Detailed media info for advanced analysis
    video_info = []
    audio_info = []
    subtitle_info = []
    image_info = []
    document_info = []

    # Categorize files by media type with detailed info
    for file_path in files:
        # Check file extension first for faster categorization
        ext = os.path.splitext(file_path)[1].lower()

        # Categorize images by extension
        if ext in [
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".webp",
            ".tiff",
            ".tif",
        ]:
            image_files.append(file_path)
            image_info.append(
                {
                    "path": file_path,
                    "format": ext[1:],  # Remove the dot
                    "size": os.path.getsize(file_path),
                }
            )
            continue

        # Categorize documents by extension
        if ext in [".pdf", ".doc", ".docx", ".odt", ".txt", ".rtf"]:
            document_files.append(file_path)
            document_info.append(
                {
                    "path": file_path,
                    "format": ext[1:],  # Remove the dot
                    "size": os.path.getsize(file_path),
                }
            )
            continue

        # For other files, use FFprobe to determine media type
        media_type = await get_media_type_internal(file_path)
        if media_type == "video":
            video_files.append(file_path)
            # Get detailed video info
            streams = await get_streams(file_path)
            if streams:
                video_info.append(
                    {
                        "path": file_path,
                        "streams": streams,
                        "format": os.path.splitext(file_path)[1][1:].lower(),
                        "size": os.path.getsize(file_path),
                    }
                )
        elif media_type == "audio":
            audio_files.append(file_path)
            # Get detailed audio info
            streams = await get_streams(file_path)
            if streams:
                audio_info.append(
                    {
                        "path": file_path,
                        "streams": streams,
                        "format": os.path.splitext(file_path)[1][1:].lower(),
                        "size": os.path.getsize(file_path),
                    }
                )
        elif media_type == "subtitle":
            subtitle_files.append(file_path)
            # Get subtitle format
            subtitle_info.append(
                {
                    "path": file_path,
                    "format": os.path.splitext(file_path)[1][1:].lower(),
                    "size": os.path.getsize(file_path),
                }
            )
        else:
            unknown_files.append(file_path)

    # Check for codec compatibility in video files
    video_codec_groups = {}
    video_resolution_groups = {}

    for info in video_info:
        video_codec = None
        audio_codec = None
        width = None
        height = None

        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video" and not stream.get(
                "disposition", {}
            ).get("attached_pic"):
                video_codec = stream.get("codec_name")
                width = stream.get("width")
                height = stream.get("height")
            elif stream.get("codec_type") == "audio":
                audio_codec = stream.get("codec_name")

        # Group by video codec for better merge strategy
        codec_key = f"{video_codec}_{audio_codec}"
        if codec_key not in video_codec_groups:
            video_codec_groups[codec_key] = []
        video_codec_groups[codec_key].append(info["path"])

        # Group by resolution for better scaling decisions
        if width and height:
            resolution_key = f"{width}x{height}"
            if resolution_key not in video_resolution_groups:
                video_resolution_groups[resolution_key] = []
            video_resolution_groups[resolution_key].append(info["path"])

    # Check for codec compatibility in audio files
    audio_codec_groups = {}
    for info in audio_info:
        audio_codec = None
        # Note: We collect these properties for future enhancements
        # sample_rate and channels could be used for advanced audio merging

        for stream in info.get("streams", []):
            if stream.get("codec_type") == "audio":
                audio_codec = stream.get("codec_name")
                # These properties are collected but not used yet
                # sample_rate = stream.get("sample_rate")
                # channels = stream.get("channels")
                break

        # Group by audio codec and properties for better merge strategy
        codec_key = audio_codec or "unknown"
        if codec_key not in audio_codec_groups:
            audio_codec_groups[codec_key] = []
        audio_codec_groups[codec_key].append(info["path"])

    # Group subtitle files by format
    subtitle_format_groups = {}
    for info in subtitle_info:
        subtitle_format = info["format"]
        if subtitle_format not in subtitle_format_groups:
            subtitle_format_groups[subtitle_format] = []
        subtitle_format_groups[subtitle_format].append(info["path"])

    # Group image files by format
    image_format_groups = {}
    for info in image_info:
        image_format = info["format"]
        if image_format not in image_format_groups:
            image_format_groups[image_format] = []
        image_format_groups[image_format].append(info["path"])

    # Group document files by format
    document_format_groups = {}
    for info in document_info:
        document_format = info["format"]
        if document_format not in document_format_groups:
            document_format_groups[document_format] = []
        document_format_groups[document_format].append(info["path"])

    # Determine recommended merge approach based on detailed analysis
    total_media_files = (
        len(video_files)
        + len(audio_files)
        + len(subtitle_files)
        + len(image_files)
        + len(document_files)
    )

    if total_media_files == 0:
        recommended_approach = None
    elif (
        len(video_files) > 0
        and len(audio_files) == 0
        and len(subtitle_files) == 0
        and len(image_files) == 0
        and len(document_files) == 0
    ):
        # All videos - check if we can use concat demuxer (same codec and resolution)
        if len(video_codec_groups) == 1 and len(video_resolution_groups) == 1:
            # All videos have same codec and resolution - can use concat demuxer
            recommended_approach = "concat_demuxer"
        elif len(video_resolution_groups) > 1:
            # Different resolutions - need to use filter_complex with scaling
            recommended_approach = "filter_complex"
        else:
            # Different codecs but same resolution - can try concat demuxer with transcoding
            recommended_approach = "concat_demuxer"
    elif (
        len(audio_files) > 0
        and len(video_files) == 0
        and len(subtitle_files) == 0
        and len(image_files) == 0
        and len(document_files) == 0
    ):
        # All audios - check if we can use concat demuxer (same codec)
        if len(audio_codec_groups) == 1:
            # All audios have same codec - can use concat demuxer
            recommended_approach = "concat_demuxer"
        else:
            # Different codecs - need to use filter_complex
            recommended_approach = "filter_complex"
    elif (
        len(subtitle_files) > 0
        and len(video_files) == 0
        and len(audio_files) == 0
        and len(image_files) == 0
        and len(document_files) == 0
    ):
        # All subtitles - check if we can use concat demuxer (same format)
        if len(subtitle_format_groups) == 1:
            # All subtitles have same format - can use concat demuxer
            recommended_approach = "concat_demuxer"
        else:
            # Different formats - need special handling
            recommended_approach = "subtitle_special"
    elif (
        len(image_files) > 0
        and len(video_files) == 0
        and len(audio_files) == 0
        and len(subtitle_files) == 0
        and len(document_files) == 0
    ):
        # All images - use PIL for merging
        recommended_approach = "image_merge"
    elif (
        len(document_files) > 0
        and len(video_files) == 0
        and len(audio_files) == 0
        and len(subtitle_files) == 0
        and len(image_files) == 0
    ):
        # All documents - use PDF merging
        recommended_approach = "document_merge"
    # Mixed media types - need to use filter_complex or mixed approach
    elif len(video_files) > 0 and (len(audio_files) > 0 or len(subtitle_files) > 0):
        recommended_approach = "mixed"
    elif len(video_files) > 0 and len(image_files) > 0:
        # Video and images - can create a slideshow
        recommended_approach = "slideshow"
    else:
        # Other combinations - use separate merges
        recommended_approach = "separate"

    return {
        "video_files": video_files,
        "audio_files": audio_files,
        "subtitle_files": subtitle_files,
        "image_files": image_files,
        "document_files": document_files,
        "unknown_files": unknown_files,
        "video_codec_groups": video_codec_groups,
        "video_resolution_groups": video_resolution_groups,
        "audio_codec_groups": audio_codec_groups,
        "subtitle_format_groups": subtitle_format_groups,
        "image_format_groups": image_format_groups,
        "document_format_groups": document_format_groups,
        "recommended_approach": recommended_approach,
    }


async def get_convert_cmd(
    file,
    output_format,
    media_type=None,
    video_codec="libx264",
    audio_codec="aac",
    video_preset="medium",
    video_crf=23,
    audio_bitrate="128k",
    # subtitle_encoding is not used but kept for API compatibility
    maintain_quality=True,
):
    """Generate FFmpeg command for converting media files to different formats.

    Args:
        file: Path to the input file
        output_format: Desired output format (e.g., mp4, mkv, mp3, etc.)
        media_type: Type of media (video, audio, subtitle, document, archive)
        video_codec: Video codec to use for video conversion
        audio_codec: Audio codec to use for audio conversion
        video_preset: Video encoding preset for video conversion
        video_crf: Constant Rate Factor for video quality (lower is better)
        audio_bitrate: Audio bitrate for audio conversion
        subtitle_encoding: Subtitle encoding for subtitle conversion
        maintain_quality: Whether to maintain original quality

    Returns:
        tuple: FFmpeg command and temporary output file path, or None, None if not supported
    """
    # Import necessary modules
    from bot import cpu_no
    from bot.helper.ext_utils.media_utils import get_media_type

    # Determine media type if not provided
    if not media_type:
        media_type = await get_media_type(file)
        if not media_type:
            return None, None

    # Determine output file extension based on output format
    output_ext = f".{output_format.lower()}"
    temp_file = f"{file}.temp{output_ext}"

    # Use default thread count
    thread_count = max(1, cpu_no // 2)

    # Base command for all media types
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file,
        "-ignore_unknown",
    ]

    # Add media-specific parameters
    if media_type == "video":
        # For video files
        if maintain_quality:
            video_crf = min(
                video_crf, 18
            )  # Use better quality if maintain_quality is enabled

        cmd.extend(
            [
                "-c:v",
                video_codec,
                "-preset",
                video_preset,
                "-crf",
                str(video_crf),
                "-c:a",
                audio_codec,
                "-b:a",
                audio_bitrate,
                "-map",
                "0:v?",
                "-map",
                "0:a?",
                "-map",
                "0:s?",
                "-map",
                "0:t?",
            ]
        )

        # Add format-specific optimizations for Telegram compatibility
        temp_file_ext = os.path.splitext(temp_file)[1].lower()
        if temp_file_ext == ".mp4":
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
        elif temp_file_ext == ".mkv":
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
        elif temp_file_ext == ".webm":
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
        elif temp_file_ext == ".mov":
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
                f"{thread_count}",
                temp_file,
            ]
        )

    elif media_type == "audio":
        # For audio files
        if output_format.lower() in ["mp3", "aac", "ogg", "opus", "flac", "wav"]:
            # Set codec based on output format
            if output_format.lower() == "mp3":
                audio_codec = "libmp3lame"
            elif output_format.lower() == "aac":
                audio_codec = "aac"
            elif output_format.lower() == "ogg":
                audio_codec = "libvorbis"
            elif output_format.lower() == "opus":
                audio_codec = "libopus"
            elif output_format.lower() == "flac":
                audio_codec = "flac"
            elif output_format.lower() == "wav":
                audio_codec = "pcm_s16le"

            # Set quality based on maintain_quality flag
            if maintain_quality:
                if output_format.lower() == "mp3":
                    audio_bitrate = "320k"
                elif (
                    output_format.lower() == "aac" or output_format.lower() == "ogg"
                ):
                    audio_bitrate = "256k"
                elif output_format.lower() == "opus":
                    audio_bitrate = "192k"
                # For lossless formats like FLAC and WAV, bitrate doesn't apply

            cmd.extend(
                [
                    "-c:a",
                    audio_codec,
                    "-b:a",
                    audio_bitrate
                    if audio_codec not in ["flac", "pcm_s16le"]
                    else "",
                    "-map",
                    "0:a",
                    "-threads",
                    f"{thread_count}",
                    temp_file,
                ]
            )
        else:
            return None, None

    elif media_type == "subtitle":
        # For subtitle files
        if output_format.lower() in ["srt", "ass", "ssa", "vtt", "sub"]:
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                file,
                "-c:s",
                "text" if output_format.lower() == "srt" else output_format.lower(),
                "-threads",
                f"{thread_count}",
                temp_file,
            ]
        else:
            return None, None

    elif media_type == "document":
        # For document files (PDF, DOCX, etc.)
        # Document conversion is complex and might require specialized tools
        # For now, we'll just return None for unsupported formats
        return None, None

    elif media_type == "archive":
        # For archive files (ZIP, RAR, etc.)
        # Archive conversion is complex and might require specialized tools
        # For now, we'll just return None for unsupported formats
        return None, None

    else:
        # For other media types
        return None, None

    return cmd, temp_file


async def get_trim_cmd(
    file,
    trim_params=None,
    video_codec="none",
    video_preset="none",
    video_format="none",
    audio_codec="none",
    audio_preset="none",  # audio_preset is not used but kept for API compatibility
    audio_format="none",
    image_quality="none",
    image_format="none",
    document_quality="none",  # document_quality is not used but kept for API compatibility
    document_format="none",
    subtitle_encoding="none",
    subtitle_format="none",
    archive_format="none",
    start_time=None,
    end_time=None,
    document_start_page=None,
    document_end_page=None,
    delete_original=False,
):
    """Generate FFmpeg command for trimming media files.

    Args:
        file: Path to the input file
        trim_params: String containing trim parameters in format "start_time-end_time" (deprecated)
        video_codec: Video codec to use for trimming
        video_preset: Video preset to use for trimming
        video_format: Output format for video trimming
        audio_codec: Audio codec to use for trimming
        audio_preset: Audio preset to use for trimming
        audio_format: Output format for audio trimming
        image_quality: Quality for image trimming
        image_format: Output format for image trimming
        document_quality: Quality for document trimming
        document_format: Output format for document trimming
        subtitle_encoding: Encoding for subtitle trimming
        subtitle_format: Output format for subtitle trimming
        archive_format: Output format for archive trimming
        start_time: Start time for trimming (overrides trim_params)
        end_time: End time for trimming (overrides trim_params)
        document_start_page: Starting page number for document trimming
        document_end_page: Ending page number for document trimming
        delete_original: Whether to delete the original file after trimming

    Returns:
        tuple: FFmpeg command and temporary output file path, or None, None if not supported
    """
    # Import necessary modules
    import os

    from bot import LOGGER
    from bot.helper.ext_utils.media_utils import get_media_type, get_streams

    # First try to determine media type using get_media_type
    media_type = await get_media_type(file)

    # If get_media_type fails, try to determine by file extension
    if not media_type:
        file_ext = os.path.splitext(file)[1].lower()
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
        ]:
            media_type = "video"
        # Audio extensions
        elif file_ext in [".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac"]:
            media_type = "audio"
        # Image extensions
        elif file_ext in [
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
            ".webp",
            ".tiff",
            ".tif",
            ".gif",
        ]:
            media_type = "image"
        # Subtitle extensions
        elif file_ext in [".srt", ".vtt", ".ass", ".ssa", ".sub"]:
            media_type = "subtitle"
        # Document extensions
        elif file_ext in [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"]:
            media_type = "document"
        # Archive extensions
        elif file_ext in [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"]:
            media_type = "archive"

    if not media_type:
        return None, None

    # Parse trim parameters
    try:
        # If start_time and end_time are provided directly, use them
        if start_time is None and end_time is None and trim_params:
            # Fallback to the old trim_params format for backward compatibility
            if "-" in trim_params:
                start_time, end_time = trim_params.split("-", 1)
            else:
                # If only one time is provided, assume it's the start time and trim to the end
                start_time = trim_params
                end_time = None

            LOGGER.info(
                f"Using deprecated trim_params format: {trim_params}, parsed to start_time={start_time}, end_time={end_time}"
            )

        # If start_time is empty or "00:00:00", set it to None (beginning of file)
        if start_time in {"", "00:00:00"}:
            start_time = "00:00:00"

        # If end_time is empty, set it to None (end of file)
        if end_time == "":
            end_time = None

    except ValueError:
        LOGGER.error(
            f"Invalid trim parameters: trim_params={trim_params}, start_time={start_time}, end_time={end_time}"
        )
        return None, None

    # Enhanced time format validation
    def validate_time(time_str):
        if time_str is None:
            return None

        # Check if it's in seconds format (e.g., "120")
        if time_str.isdigit():
            return time_str

        # Check if it's in HH:MM:SS format (e.g., "00:02:00")
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) <= 3 and all(part.isdigit() for part in parts):
                return time_str

        # Check if it's in HH:MM:SS.mmm format (e.g., "00:02:00.500")
        if ":" in time_str and "." in time_str:
            time_parts = time_str.split(".")
            if len(time_parts) == 2 and time_parts[1].isdigit():
                parts = time_parts[0].split(":")
                if len(parts) <= 3 and all(part.isdigit() for part in parts):
                    return time_str

        LOGGER.error(f"Invalid time format: {time_str}")
        return None

    # Skip time validation for documents since they use page parameters
    if media_type != "document":
        start_time = validate_time(start_time)
        end_time = validate_time(end_time)

        if start_time is None:
            LOGGER.error("Invalid start time for trimming")
            return None, None

    # Determine output file extension based on input file or specified format
    file_ext = os.path.splitext(file)[1].lower()

    # We already have the media type from earlier, no need to get it again

    # Determine output extension based on specified format
    if media_type == "video" and video_format and video_format != "none":
        output_ext = f".{video_format.lower()}"
    elif media_type == "audio" and audio_format and audio_format != "none":
        output_ext = f".{audio_format.lower()}"
    elif media_type == "image" and image_format and image_format != "none":
        output_ext = f".{image_format.lower()}"
    elif media_type == "document" and document_format and document_format != "none":
        output_ext = f".{document_format.lower()}"
    elif media_type == "subtitle" and subtitle_format and subtitle_format != "none":
        output_ext = f".{subtitle_format.lower()}"
    elif media_type == "archive" and archive_format and archive_format != "none":
        output_ext = f".{archive_format.lower()}"
    else:
        # Use the original extension if no format is specified
        output_ext = file_ext

    temp_file = f"{file}.trim{output_ext}"

    # Get file information for better handling (skip for documents as they don't have streams)
    streams = None
    if media_type != "document":
        streams = await get_streams(file)

    # Base command for all media types
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
    ]

    # Add trim parameters - for better accuracy, put -ss before -i for seeking
    if start_time:
        cmd.extend(["-ss", start_time])

    # Add input file
    cmd.extend(["-i", file])

    # Add end time parameter
    if end_time:
        cmd.extend(["-to", end_time])

    # Add media-specific parameters
    if media_type == "video":
        # Check if the file has video streams
        has_video = False
        has_audio = False
        # We don't need to track subtitle streams here as we always copy them

        if streams:
            for stream in streams:
                if stream.get("codec_type") == "video" and not stream.get(
                    "disposition", {}
                ).get("attached_pic"):
                    has_video = True
                elif stream.get("codec_type") == "audio":
                    has_audio = True
                # We don't need to check for subtitles here as we're always copying them

        # Add video codec parameters
        if has_video:
            # Check if this is a HEVC/10-bit MKV file
            is_hevc_10bit = file_ext.lower() == ".mkv" and (
                "10bit" in file.lower()
                or "10bi" in file.lower()
                or "hevc" in file.lower()
            )

            # For HEVC/10-bit MKV files, always use copy codec for better compatibility
            if is_hevc_10bit:
                LOGGER.info(
                    f"Detected HEVC/10-bit MKV file, using copy codec: {file}"
                )
                cmd.extend(["-c:v", "copy"])
            # Check if video_codec is "none" (case-insensitive) or None
            elif not video_codec or video_codec.lower() == "none":
                # Use copy codec as default when none is specified
                cmd.extend(["-c:v", "copy"])
            else:
                cmd.extend(["-c:v", video_codec])

                if video_codec != "copy":
                    # Check if video_preset is "none" (case-insensitive) or None
                    if video_preset and video_preset.lower() != "none":
                        cmd.extend(["-preset", video_preset])
                    # Ensure even dimensions for encoded video
                    cmd.extend(["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"])
                    # Ensure compatible pixel format
                    cmd.extend(["-pix_fmt", "yuv420p"])
                    # Add quality parameter for better results
                    cmd.extend(["-crf", "23"])

        # Add audio codec parameters
        if has_audio:
            # Check if audio_codec is "none" (case-insensitive) or None
            if not audio_codec or audio_codec.lower() == "none":
                # Use copy codec as default when none is specified
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", audio_codec])

                if audio_codec != "copy":
                    if audio_codec == "aac":
                        cmd.extend(["-b:a", "192k"])
                    elif audio_codec == "libmp3lame":
                        cmd.extend(["-q:a", "3"])
                    elif audio_codec == "libopus":
                        cmd.extend(["-b:a", "128k"])

        # Always copy subtitle tracks
        cmd.extend(["-c:s", "copy"])

        # Map all streams
        cmd.extend(["-map", "0"])

        # Add avoid_negative_ts to fix timestamp issues
        cmd.extend(["-avoid_negative_ts", "make_zero"])

        # Add container-specific parameters with format optimizations
        if file_ext == ".mp4":
            # For MP4, ensure compatibility and streaming
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
        elif file_ext == ".mkv":
            # For MKV, no special parameters needed
            pass
        elif file_ext == ".avi":
            # For AVI, ensure compatibility
            if video_codec != "copy":
                cmd.extend(["-c:v", "libx264"])
        elif file_ext == ".webm":
            # For WebM, use VP9 and Opus
            if video_codec != "copy":
                cmd.extend(["-c:v", "libvpx-vp9", "-b:v", "1M"])
            if audio_codec != "copy":
                cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
        elif file_ext == ".hevc":
            # For HEVC files, ensure we use a proper container
            # Change the output file extension to .mp4
            temp_file = f"{os.path.splitext(file)[0]}.trim.mp4"

            # For raw HEVC files, we need to specify the format
            cmd.extend(["-f", "hevc"])

            # Use H.265 codec
            if video_codec == "copy":
                cmd.extend(["-c:v", "copy"])
            else:
                cmd.extend(
                    ["-c:v", "libx265", "-crf", "28", "-preset", video_preset]
                )

            # Add MP4 container flags with optimizations
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

    elif media_type == "audio":
        # For audio files
        # Check if audio_codec is "none" (case-insensitive) or None
        if not audio_codec or audio_codec.lower() == "none":
            # Use copy codec as default when none is specified
            cmd.extend(["-c:a", "copy"])
        else:
            # Ensure codec is compatible with the container format
            output_ext = os.path.splitext(temp_file)[1].lower()

            # Match codec to appropriate container format
            if audio_codec != "copy":
                if file_ext == ".mp3" and audio_codec != "libmp3lame":
                    LOGGER.warning(
                        f"Codec {audio_codec} not compatible with MP3 container, using libmp3lame"
                    )
                    audio_codec = "libmp3lame"
                elif file_ext == ".m4a" and audio_codec != "aac":
                    LOGGER.warning(
                        f"Codec {audio_codec} not compatible with M4A container, using aac"
                    )
                    audio_codec = "aac"
                elif file_ext == ".opus" and audio_codec != "libopus":
                    LOGGER.warning(
                        f"Codec {audio_codec} not compatible with OPUS container, using libopus"
                    )
                    audio_codec = "libopus"
                elif file_ext == ".ogg" and audio_codec != "libvorbis":
                    LOGGER.warning(
                        f"Codec {audio_codec} not compatible with OGG container, using libvorbis"
                    )
                    audio_codec = "libvorbis"
                elif file_ext == ".flac" and audio_codec != "flac":
                    LOGGER.warning(
                        f"Codec {audio_codec} not compatible with FLAC container, using flac"
                    )
                    audio_codec = "flac"
                elif file_ext == ".wav" and not audio_codec.startswith("pcm_"):
                    LOGGER.warning(
                        f"Codec {audio_codec} not compatible with WAV container, using pcm_s16le"
                    )
                    audio_codec = "pcm_s16le"

            # Add the codec to the command
            cmd.extend(["-c:a", audio_codec])

            # Add appropriate quality parameters based on codec
            if audio_codec != "copy":
                if audio_codec == "aac":
                    cmd.extend(["-b:a", "192k"])
                elif audio_codec == "libmp3lame":
                    cmd.extend(["-q:a", "3"])
                elif audio_codec == "libopus":
                    cmd.extend(["-b:a", "128k"])
                elif audio_codec == "libvorbis":
                    cmd.extend(["-q:a", "6"])
                elif audio_codec == "flac":
                    cmd.extend(["-compression_level", "8"])

        # Map all audio streams
        cmd.extend(["-map", "0:a"])

        # Add avoid_negative_ts to fix timestamp issues
        cmd.extend(["-avoid_negative_ts", "make_zero"])

        # Add container-specific parameters for better compatibility
        if file_ext == ".mp3":
            # For MP3 files, ensure we use the right format
            cmd.extend(["-f", "mp3"])
            if audio_codec == "copy":
                # For MP3 files, sometimes copy doesn't work well with trimming
                # Use re-encoding with high quality
                cmd = [c for c in cmd if c not in ["-c:a", "copy"]]
                cmd.extend(["-c:a", "libmp3lame", "-q:a", "3"])
        elif file_ext == ".m4a":
            # For M4A files, ensure we use the right format
            cmd.extend(["-f", "mp4"])
            if audio_codec == "copy":
                # For M4A files, sometimes copy doesn't work well with trimming
                # Use re-encoding with high quality
                cmd = [c for c in cmd if c not in ["-c:a", "copy"]]
                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        elif file_ext == ".opus":
            # For Opus files, ensure we use the right format
            cmd.extend(["-f", "opus"])
            if audio_codec == "copy":
                # For Opus files, sometimes copy doesn't work well with trimming
                # Use re-encoding with high quality
                cmd = [c for c in cmd if c not in ["-c:a", "copy"]]
                cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
        elif file_ext == ".ogg":
            # For OGG files, ensure we use the right format
            cmd.extend(["-f", "ogg"])
            if audio_codec == "copy":
                # For OGG files, sometimes copy doesn't work well with trimming
                # Use re-encoding with high quality
                cmd = [c for c in cmd if c not in ["-c:a", "copy"]]
                cmd.extend(["-c:a", "libvorbis", "-q:a", "6"])
        elif file_ext == ".flac":
            # For FLAC files, ensure we use the right format
            cmd.extend(["-f", "flac"])
            if audio_codec == "copy":
                # No special parameters needed for FLAC copy
                pass
            else:
                # Use high quality for re-encoding
                cmd.extend(["-compression_level", "8"])
        elif file_ext == ".wav":
            # For WAV files, ensure we use the right format
            cmd.extend(["-f", "wav"])

    elif media_type == "image":
        # For image files, we need special handling since images don't have duration
        # We'll create a short video from the image

        # Remove any existing trim parameters since they don't apply to images
        cmd = [
            "xtra",
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            "-i",
            file,
        ]

        # For JPEG files
        if file_ext in [".jpg", ".jpeg"]:
            if (
                not image_quality
                or image_quality.lower() == "none"
                or image_quality == "0"
            ):
                cmd.extend(["-q:v", "1"])  # Best quality
            else:
                try:
                    quality_val = int(image_quality)
                    cmd.extend(["-q:v", str(min(31, 31 - int(quality_val * 0.31)))])
                except (ValueError, TypeError):
                    cmd.extend(["-q:v", "1"])  # Default to best quality
        # For PNG files
        elif file_ext in [".png"]:
            if (
                not image_quality
                or image_quality.lower() == "none"
                or image_quality == "0"
            ):
                cmd.extend(["-compression_level", "0"])  # Best quality
            else:
                try:
                    quality_val = int(image_quality)
                    cmd.extend(
                        [
                            "-compression_level",
                            str(min(9, 9 - int(quality_val * 0.09))),
                        ]
                    )
                except (ValueError, TypeError):
                    cmd.extend(
                        ["-compression_level", "0"]
                    )  # Default to best quality
        # For SVG files
        elif file_ext == ".svg":
            # SVG files need special handling - convert to PNG first
            return None, None
        # For PSD files
        elif file_ext == ".psd":
            # PSD files need special handling
            return None, None
        # For GIF files
        elif file_ext == ".gif":
            # For GIF, we need special handling
            # Check if it's an animated GIF by getting the number of frames
            streams = await get_streams(file)

            # Create a more robust approach for GIF files
            # Reset the command to ensure clean setup
            cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
            ]

            # Always put -ss before -i for accurate seeking with GIFs
            if start_time:
                cmd.extend(["-ss", start_time])

            cmd.extend(["-i", file])

            if end_time:
                cmd.extend(["-to", end_time])

            # Create a temporary output file with .mp4 extension for intermediate processing
            # This helps avoid issues with direct GIF output
            temp_mp4 = f"{file}.temp.mp4"

            # Use a two-step process:
            # 1. Convert GIF to MP4 with h264 encoding
            # 2. Convert MP4 back to GIF with proper palette

            # Step 1: Convert to MP4 with h264 encoding
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-vf",
                    "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
                    "-crf",
                    "18",  # High quality
                    "-preset",
                    "fast",
                    "-movflags",
                    "+faststart",  # Add faststart flag for MP4 videos
                    "-y",
                    temp_mp4,
                ]
            )

            # Return a special command format that will be recognized and handled
            # in the proceed_trim method to perform the second step
            return ["gif_trim", file, temp_mp4, temp_file], temp_file

    elif media_type == "subtitle":
        # For subtitle files

        # Determine subtitle format
        subtitle_format = "srt"  # Default format
        if file_ext == ".vtt":
            subtitle_format = "webvtt"
        elif file_ext in [".ass", ".ssa"]:
            subtitle_format = "ass"
        elif file_ext == ".sub":
            subtitle_format = "subviewer"

        # For subtitle files, we need a different approach
        # FFmpeg's subtitle trimming can be unreliable

        # We'll use a custom approach for SRT files
        if file_ext == ".srt":
            # For SRT files, we'll use a special approach
            # First, we'll read the file and parse it
            LOGGER.info(f"Using custom SRT trimming approach for {file}")

            # Create a temporary file with the same name but .trim extension
            temp_file = f"{file}.trim{file_ext}"

            # We'll handle SRT trimming in the proceed_trim method
            # For now, just return a special command that will be recognized
            cmd = [
                "srt_trim",
                file,
                start_time or "0",
                end_time or "999:59:59",
                temp_file,
            ]
            return cmd, temp_file
        if file_ext == ".vtt":
            # For VTT files, we'll use a similar approach to SRT
            # First convert to SRT, then trim, then convert back to VTT
            LOGGER.info(f"Using custom VTT trimming approach for {file}")

            # Create temporary files
            temp_srt = f"{file}.temp.srt"
            temp_file = f"{file}.trim{file_ext}"

            # First convert VTT to SRT for easier processing
            convert_cmd = [
                "xtra",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                file,
                "-f",
                "srt",
                temp_srt,
            ]

            # Execute the conversion command
            try:
                import subprocess

                result = subprocess.run(
                    convert_cmd, capture_output=True, text=True, check=False
                )
                if result.returncode != 0:
                    LOGGER.error(f"Failed to convert VTT to SRT: {result.stderr}")
                    # Fallback to standard approach
                    cmd.extend(["-c:s", "copy", "-f", subtitle_format])
                    return cmd, temp_file

                # Now use the SRT trimming approach
                cmd = [
                    "srt_trim",
                    temp_srt,
                    start_time or "0",
                    end_time or "999:59:59",
                    temp_srt + ".trim",
                ]

                # After trimming, we'll need to convert back to VTT
                # This will be handled in the proceed_trim method
                return cmd, temp_file
            except Exception as e:
                LOGGER.error(f"Error in VTT trimming: {e}")
                # Fallback to standard approach
                cmd.extend(["-c:s", "copy", "-f", subtitle_format])
        # For other subtitle formats, try the standard approach
        # Check if subtitle_encoding is "none" (case-insensitive) or None
        elif not subtitle_encoding or subtitle_encoding.lower() == "none":
            # Use copy codec as default when none is specified
            cmd.extend(["-c:s", "copy", "-f", subtitle_format])
        else:
            # For subtitle encoding, we typically use "copy" anyway
            cmd.extend(["-c:s", "copy", "-f", subtitle_format])

    elif media_type == "document":
        # For document files, we need to use a different approach
        if file_ext == ".pdf":
            # For PDF files, we can use a special approach to extract pages
            LOGGER.info(f"Using PDF trimming approach for {file}")

            # Create a temporary file with the same name but .trim extension
            temp_file = f"{file}.trim{file_ext}"

            # Use document page parameters if available, otherwise fall back to time parameters
            start_page = document_start_page or start_time or "1"
            end_page = document_end_page or end_time or ""

            # Convert empty string to None for end page (means last page)
            if end_page == "":
                end_page = None

            # We'll handle PDF trimming in the proceed_trim method
            # For now, just return a special command that will be recognized
            cmd = [
                "pdf_trim",
                file,
                str(start_page),  # Start page number
                (
                    str(end_page) if end_page else ""
                ),  # End page number (empty for last page)
                temp_file,
            ]
            return cmd, temp_file
        # For other document types, we can't use FFmpeg directly
        return None, None

    elif media_type == "archive":
        # For archive files, we can't use FFmpeg
        return None, None

    # Add format-specific optimizations for Telegram compatibility
    if media_type == "video":
        temp_file_ext = os.path.splitext(temp_file)[1].lower()
        if temp_file_ext == ".mp4":
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
        elif temp_file_ext == ".mkv":
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
        elif temp_file_ext == ".webm":
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
        elif temp_file_ext == ".mov":
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

    # Add output file
    cmd.append(temp_file)

    # Output file format logging removed for cleaner output

    # Add -y flag to force overwrite without prompting
    if "-y" not in cmd:
        cmd.append("-y")

    # Remove any -map options for GIF files to ensure our special handling works
    if file_ext == ".gif" and "-map" in cmd:
        map_index = cmd.index("-map")
        if map_index < len(cmd) - 1:
            # Remove the -map option and its argument
            cmd.pop(map_index)  # Remove -map
            cmd.pop(map_index)  # Remove the argument (e.g., 0)

    # Add delete_original flag to the command for handling in the proceed_trim method
    if delete_original:
        LOGGER.info(f"Original file will be deleted after trimming: {file}")
        # We'll handle this in the proceed_trim method, but we need to pass this information
        # Use -del flag which is recognized and handled by the proceed_trim method
        cmd.append("-del")

    return cmd, temp_file


async def get_compression_cmd(
    file_path,
    media_type=None,
    video_preset="medium",
    video_crf="none",
    video_codec="libx264",
    video_tune="film",
    video_pixel_format="yuv420p",
    video_bitdepth="none",
    video_bitrate="none",
    video_resolution="none",
    video_format="none",
    audio_preset="medium",
    audio_codec="aac",
    audio_bitrate="128k",
    audio_channels="none",
    audio_bitdepth="none",
    audio_format="none",
    image_preset="medium",
    image_quality="none",
    image_resize="none",
    image_format="none",
    document_preset="medium",
    document_dpi="none",
    document_format="none",
    subtitle_preset="medium",
    subtitle_encoding="utf-8",
    subtitle_format="none",
    archive_preset="medium",
    archive_level="none",
    archive_method="deflate",
    archive_format="none",
    # delete_original is not used here but kept for API compatibility
    # It's handled in the proceed_compression method
    delete_original=True,
):
    """Generate FFmpeg command for compressing media files.

    Args:
        file_path: Path to the input file
        media_type: Type of media (video, audio, image, document, subtitle, archive)
        video_preset: Compression preset for video (fast, medium, slow)
        video_crf: Constant Rate Factor for video quality (0-51, lower is better)
        video_codec: Video codec to use (libx264, libx265, etc.)
        video_tune: Video tuning parameter (film, animation, grain, etc.)
        video_pixel_format: Pixel format for video (yuv420p, yuv444p, etc.)
        video_format: Output format for video (mp4, mkv, etc.)
        audio_preset: Compression preset for audio (fast, medium, slow)
        audio_codec: Audio codec to use (aac, mp3, opus, etc.)
        audio_bitrate: Audio bitrate (64k, 128k, 192k, etc.)
        audio_channels: Number of audio channels (1=mono, 2=stereo)
        audio_format: Output format for audio (mp3, aac, etc.)
        image_preset: Compression preset for images (fast, medium, slow)
        image_quality: Quality for image compression (1-100)
        image_resize: Size to resize images to (e.g., 1280x720)
        image_format: Output format for images (jpg, png, etc.)
        document_preset: Compression preset for documents (fast, medium, slow)
        document_dpi: DPI for document compression
        document_format: Output format for documents (pdf, etc.)
        subtitle_preset: Compression preset for subtitles (fast, medium, slow)
        subtitle_encoding: Character encoding for subtitles
        subtitle_format: Output format for subtitles (srt, ass, etc.)
        archive_preset: Compression preset for archives (fast, medium, slow)
        archive_level: Compression level for archives (1-9)
        archive_method: Compression method for archives (deflate, lzma, etc.)
        archive_format: Output format for archives (zip, 7z, etc.)
        delete_original: Whether to delete the original file after compression

    Returns:
        tuple: FFmpeg command and temporary output file path, or None, None if not supported
    """
    # Import necessary modules
    from bot import LOGGER, cpu_no
    from bot.helper.ext_utils.media_utils import get_media_type, get_streams

    # Determine media type if not provided
    if not media_type:
        media_type = await get_media_type(file_path)
        if not media_type:
            return None, None

    # Get file extension
    file_ext = os.path.splitext(file_path)[1].lower()

    # Determine output file extension based on format settings
    if media_type == "video" and video_format and video_format.lower() != "none":
        output_ext = f".{video_format.lower()}"
    elif media_type == "audio" and audio_format and audio_format.lower() != "none":
        output_ext = f".{audio_format.lower()}"
    elif media_type == "audio" and audio_codec and audio_codec.lower() != "none":
        # Match codec to appropriate container for audio files
        if audio_codec == "libmp3lame":
            output_ext = ".mp3"
        elif audio_codec == "libvorbis":
            output_ext = ".ogg"
        elif audio_codec == "libopus":
            output_ext = ".opus"
        elif audio_codec == "aac":
            output_ext = ".m4a"
        elif audio_codec == "flac":
            output_ext = ".flac"
        elif audio_codec.startswith("pcm_"):
            output_ext = ".wav"
        else:
            # Keep original extension if no format specified
            output_ext = file_ext
    elif media_type == "image" and image_format and image_format.lower() != "none":
        output_ext = f".{image_format.lower()}"
    elif (
        media_type == "document"
        and document_format
        and document_format.lower() != "none"
    ):
        output_ext = f".{document_format.lower()}"
    elif (
        media_type == "subtitle"
        and subtitle_format
        and subtitle_format.lower() != "none"
    ):
        output_ext = f".{subtitle_format.lower()}"
    elif (
        media_type == "archive"
        and archive_format
        and archive_format.lower() != "none"
    ):
        output_ext = f".{archive_format.lower()}"
    else:
        # Keep original extension if no format specified
        output_ext = file_ext

    # Create temporary output file path
    temp_file = f"{file_path}.compressed{output_ext}"

    # Get stream information
    streams = await get_streams(file_path)

    # Use default thread count
    thread_count = max(1, cpu_no // 2)

    # Base command for all media types
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file_path,
        "-ignore_unknown",
    ]

    # Add media-specific parameters
    if media_type == "video":
        # Check if the file has video streams
        has_video = False
        has_audio = False
        has_subtitle = False

        if streams:
            for stream in streams:
                if stream.get("codec_type") == "video" and not stream.get(
                    "disposition", {}
                ).get("attached_pic"):
                    has_video = True
                elif stream.get("codec_type") == "audio":
                    has_audio = True
                elif stream.get("codec_type") == "subtitle":
                    has_subtitle = True

        # Add video codec parameters
        if has_video:
            # Check if this is a HEVC/10-bit MKV file
            is_hevc_10bit = file_ext.lower() == ".mkv" and (
                "10bit" in file_path.lower()
                or "10bi" in file_path.lower()
                or "hevc" in file_path.lower()
            )

            # For HEVC/10-bit MKV files, always use copy codec for better compatibility
            if is_hevc_10bit:
                LOGGER.info(
                    f"Detected HEVC/10-bit MKV file, using copy codec: {file_path}"
                )
                cmd.extend(["-c:v", "copy"])
            else:
                # Add video codec
                cmd.extend(["-c:v", video_codec])

                # Add video preset
                if video_preset and video_preset.lower() != "none":
                    if video_codec in ["libx264", "libx265"]:
                        cmd.extend(["-preset", video_preset])

                # Add CRF for quality control
                if video_crf and str(video_crf).lower() != "none":
                    try:
                        crf_val = int(video_crf)
                        if crf_val > 0:
                            cmd.extend(["-crf", str(crf_val)])
                    except (ValueError, TypeError):
                        # If conversion fails, don't add CRF parameter
                        pass

                # Add tune parameter
                if video_tune and video_tune.lower() != "none":
                    if video_codec in ["libx264", "libx265"]:
                        # Special handling for libx265
                        if video_codec == "libx265" and video_tune not in [
                            "psnr",
                            "ssim",
                            "grain",
                            "zerolatency",
                            "fastdecode",
                        ]:
                            LOGGER.info(
                                f"Removing unsupported tune parameter for libx265: {video_tune}"
                            )
                            # Skip adding the tune parameter for unsupported values
                        else:
                            cmd.extend(["-tune", video_tune])

                # Add pixel format
                if video_pixel_format and video_pixel_format.lower() != "none":
                    cmd.extend(["-pix_fmt", video_pixel_format])

                # Add video bitdepth if specified
                if video_bitdepth and str(video_bitdepth).lower() != "none":
                    # Bitdepth is typically handled via pixel format, so we'll need to adjust
                    # the pixel format based on the requested bit depth
                    try:
                        depth_val = int(video_bitdepth)
                        if depth_val == 10:
                            # For 10-bit, use appropriate pixel format based on codec
                            if video_codec in {"libx264", "libx265"}:
                                cmd.extend(["-pix_fmt", "yuv420p10le"])
                        elif depth_val == 12:
                            # For 12-bit, use appropriate pixel format
                            if (
                                video_codec == "libx265"
                            ):  # x264 doesn't support 12-bit
                                cmd.extend(["-pix_fmt", "yuv420p12le"])
                    except (ValueError, TypeError):
                        # If conversion fails, don't add bitdepth parameter
                        pass

                # Add video bitrate if specified
                if video_bitrate and str(video_bitrate).lower() != "none":
                    cmd.extend(["-b:v", video_bitrate])

                # Add video resolution if specified
                if video_resolution and str(video_resolution).lower() != "none":
                    cmd.extend(["-vf", f"scale={video_resolution}"])

        # Add audio codec parameters
        if has_audio:
            # Add audio codec
            cmd.extend(["-c:a", audio_codec])

            # Add audio bitrate
            if audio_bitrate and audio_bitrate.lower() != "none":
                cmd.extend(["-b:a", audio_bitrate])

            # Add audio channels
            if audio_channels and str(audio_channels).lower() != "none":
                try:
                    channels_val = int(audio_channels)
                    if channels_val > 0:
                        cmd.extend(["-ac", str(channels_val)])
                except (ValueError, TypeError):
                    # If conversion fails, don't add channels parameter
                    pass

            # Add audio bitdepth if specified
            if audio_bitdepth and str(audio_bitdepth).lower() != "none":
                try:
                    depth_val = int(audio_bitdepth)
                    if depth_val in [16, 24, 32]:
                        # For PCM audio formats
                        if audio_codec in ["pcm_s16le", "pcm_s24le", "pcm_s32le"]:
                            # The codec already specifies the bit depth
                            pass
                        elif audio_codec == "flac":
                            # FLAC supports different bit depths
                            cmd.extend(["-sample_fmt", f"s{depth_val}"])
                        # For other codecs, we might need to adjust based on the specific codec
                except (ValueError, TypeError):
                    # If conversion fails, don't add bitdepth parameter
                    pass

        # Add subtitle parameters
        if has_subtitle:
            # For subtitles, we typically use copy codec
            cmd.extend(["-c:s", "copy"])

        # Map all streams
        cmd.extend(["-map", "0"])

    elif media_type == "audio":
        # Check codec compatibility with container format
        output_ext = os.path.splitext(temp_file)[1].lower()

        # Ensure codec is compatible with the container format
        if output_ext == ".mp3" and audio_codec != "libmp3lame":
            LOGGER.warning(
                f"Codec {audio_codec} not compatible with MP3 container, using libmp3lame"
            )
            audio_codec = "libmp3lame"
        elif output_ext == ".ogg" and audio_codec != "libvorbis":
            LOGGER.warning(
                f"Codec {audio_codec} not compatible with OGG container, using libvorbis"
            )
            audio_codec = "libvorbis"
        elif output_ext == ".opus" and audio_codec != "libopus":
            LOGGER.warning(
                f"Codec {audio_codec} not compatible with OPUS container, using libopus"
            )
            audio_codec = "libopus"
        elif output_ext == ".m4a" and audio_codec != "aac":
            LOGGER.warning(
                f"Codec {audio_codec} not compatible with M4A container, using aac"
            )
            audio_codec = "aac"
        elif output_ext == ".flac" and audio_codec != "flac":
            LOGGER.warning(
                f"Codec {audio_codec} not compatible with FLAC container, using flac"
            )
            audio_codec = "flac"
        elif output_ext == ".wav" and not audio_codec.startswith("pcm_"):
            LOGGER.warning(
                f"Codec {audio_codec} not compatible with WAV container, using pcm_s16le"
            )
            audio_codec = "pcm_s16le"

        # Add audio codec
        cmd.extend(["-c:a", audio_codec])

        # Add audio preset
        if audio_preset and audio_preset.lower() != "none":
            if audio_codec == "libopus":
                cmd.extend(
                    [
                        "-compression_level",
                        (
                            "10"
                            if audio_preset == "slow"
                            else "5"
                            if audio_preset == "medium"
                            else "0"
                        ),
                    ]
                )

        # Add audio bitrate based on codec and preset
        if audio_bitrate and audio_bitrate.lower() != "none":
            cmd.extend(["-b:a", audio_bitrate])
        # Set default bitrate based on codec and preset
        elif audio_codec == "libmp3lame":
            if audio_preset == "slow":
                cmd.extend(["-b:a", "320k"])
            elif audio_preset == "fast":
                cmd.extend(["-b:a", "128k"])
            else:  # medium
                cmd.extend(["-b:a", "192k"])
        elif audio_codec == "aac":
            if audio_preset == "slow":
                cmd.extend(["-b:a", "256k"])
            elif audio_preset == "fast":
                cmd.extend(["-b:a", "128k"])
            else:  # medium
                cmd.extend(["-b:a", "192k"])
        elif audio_codec == "libvorbis":
            if audio_preset == "slow":
                cmd.extend(["-b:a", "192k"])
            elif audio_preset == "fast":
                cmd.extend(["-b:a", "96k"])
            else:  # medium
                cmd.extend(["-b:a", "128k"])
        elif audio_codec == "libopus":
            if audio_preset == "slow":
                cmd.extend(["-b:a", "128k"])
            elif audio_preset == "fast":
                cmd.extend(["-b:a", "64k"])
            else:  # medium
                cmd.extend(["-b:a", "96k"])
            # No bitrate for lossless formats (flac, pcm)

        # Add audio channels
        if audio_channels and str(audio_channels).lower() != "none":
            try:
                channels_val = int(audio_channels)
                if channels_val > 0:
                    cmd.extend(["-ac", str(channels_val)])
            except (ValueError, TypeError):
                # If conversion fails, don't add channels parameter
                pass

        # Map all audio streams
        cmd.extend(["-map", "0:a"])

    elif media_type == "image":
        # For image files
        if file_ext in [".jpg", ".jpeg"]:
            # For JPEG, use quality parameter
            if image_quality and str(image_quality).lower() != "none":
                try:
                    quality_val = int(image_quality)
                    if quality_val > 0:
                        quality_val = min(31, 31 - int(quality_val * 0.31))
                    else:
                        quality_val = 1
                    cmd.extend(["-q:v", str(quality_val)])
                except (ValueError, TypeError):
                    # If conversion fails, use default quality
                    cmd.extend(["-q:v", "1"])
            else:
                # Use default quality
                cmd.extend(["-q:v", "1"])
        elif file_ext in [".png", ".webp"]:
            # For PNG and WebP, use compression level
            if image_quality and str(image_quality).lower() != "none":
                try:
                    quality_val = int(image_quality)
                    if quality_val > 0:
                        compression_level = min(9, 9 - int(quality_val * 0.09))
                    else:
                        compression_level = 0
                    cmd.extend(["-compression_level", str(compression_level)])
                except (ValueError, TypeError):
                    # If conversion fails, use default compression
                    cmd.extend(["-compression_level", "0"])
            else:
                # Use default compression
                cmd.extend(["-compression_level", "0"])
        else:
            # For other image formats, use general quality settings
            cmd.extend(["-q:v", "2"])

        # Add resize filter if specified
        if image_resize and image_resize.lower() != "none":
            cmd.extend(["-vf", f"scale={image_resize}"])

    elif media_type == "document":
        # For document files (mainly PDF)
        if file_ext == ".pdf":
            # For PDF files, we'll use a special approach
            # This will be handled separately in the proceed_compression method
            # Just return a special command that will be recognized
            # Handle document_dpi as "none"
            dpi_value = "150"  # Default DPI value
            if document_dpi and str(document_dpi).lower() != "none":
                try:
                    dpi_val = int(document_dpi)
                    if dpi_val > 0:
                        dpi_value = str(dpi_val)
                except (ValueError, TypeError):
                    pass

            cmd = [
                "pdf_compress",
                file_path,
                dpi_value,
                document_preset,
                temp_file,
            ]
            return cmd, temp_file
        # For other document types, we can't use FFmpeg directly
        return None, None

    elif media_type == "subtitle":
        # For subtitle files
        if file_ext in [".srt", ".ass", ".ssa", ".vtt"]:
            # For text-based subtitles, we'll use a special approach
            # This will be handled separately in the proceed_compression method
            cmd = [
                "subtitle_compress",
                file_path,
                subtitle_encoding,
                subtitle_preset,
                temp_file,
            ]
            return cmd, temp_file
        # For other subtitle formats, try standard approach
        cmd.extend(["-c:s", "copy"])

    elif media_type == "archive":
        # For archive files, we'll use a special approach
        # This will be handled separately in the proceed_compression method
        # Handle archive_level as "none"
        level_value = "5"  # Default compression level
        if archive_level and str(archive_level).lower() != "none":
            try:
                level_val = int(archive_level)
                if 0 <= level_val <= 9:
                    level_value = str(level_val)
            except (ValueError, TypeError):
                pass

        cmd = [
            "archive_compress",
            file_path,
            level_value,
            archive_method,
            archive_preset,
            temp_file,
        ]
        return cmd, temp_file

    else:
        # For other media types
        return None, None

    # Add format-specific optimizations for Telegram compatibility
    if media_type == "video":
        temp_file_ext = os.path.splitext(temp_file)[1].lower()
        if temp_file_ext == ".mp4":
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
        elif temp_file_ext == ".mkv":
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
        elif temp_file_ext == ".webm":
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
        elif temp_file_ext == ".mov":
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

    # Add threads parameter
    cmd.extend(["-threads", f"{thread_count}"])

    # Add output file
    cmd.append(temp_file)

    # Output file format logging removed for cleaner output

    return cmd, temp_file


def find_next_available_index(existing_indices, target_idx):
    """Find the next available index for a track.

    If the target index is already occupied, find the next available index.

    Args:
        existing_indices (list): List of existing track indices
        target_idx (int): Target index to check

    Returns:
        int: Next available index
    """
    # If the target index is not in the existing indices, return it
    if target_idx not in existing_indices:
        return target_idx

    # Otherwise, find the next available index
    # Start from the target index and increment until we find an available index
    next_idx = target_idx
    while next_idx in existing_indices:
        next_idx += 1

    return next_idx


def find_first_available_index(existing_indices, target_idx=None):
    """Find the first available index for a track.

    If target_idx is provided and valid, use that index.
    If target_idx is beyond the existing tracks or not provided,
    find the first available index starting from 0.

    Args:
        existing_indices (list): List of existing track indices
        target_idx (int, optional): Preferred index to use

    Returns:
        int: First available index
    """
    # If target_idx is provided and valid, use it
    if target_idx is not None:
        # Check if the target index is beyond the current count of tracks
        # We consider it valid if it's not already occupied
        if target_idx not in existing_indices:
            return target_idx

        # If the target index is already occupied, try to find the next available index
        # starting from the target index
        next_idx = target_idx
        while next_idx in existing_indices:
            next_idx += 1
        return next_idx

    # Find the first available index starting from 0
    idx = 0
    while idx in existing_indices:
        idx += 1

    return idx


def resolve_track_index(
    target_idx, existing_indices, replace_mode=False, preserve_mode=False
):
    """
    Resolve the actual index to use for track placement based on mode and conflicts.

    Args:
        target_idx: The desired index
        existing_indices: List of currently occupied indices
        replace_mode: Whether to replace existing tracks
        preserve_mode: Whether to preserve existing tracks

    Returns:
        int: The actual index to use
    """
    if target_idx is None:
        # No specific index requested, find first available
        idx = 0
        while idx in existing_indices:
            idx += 1
        return idx

    target_idx = int(target_idx)

    if replace_mode:
        # In replace mode, use the specified index even if occupied
        return target_idx
    if preserve_mode or target_idx in existing_indices:
        # In preserve mode or if index is occupied, find next available
        idx = target_idx
        while idx in existing_indices:
            idx += 1
        return idx
    # Index is not occupied and not in replace mode, use as-is
    return target_idx


async def validate_and_get_stream_type(file_path, expected_type):
    """
    Validate file and get appropriate stream type.

    Args:
        file_path: Path to the file to validate
        expected_type: Expected stream type ('video', 'audio', 'subtitle', 'attachment')

    Returns:
        tuple: (has_expected_stream, actual_stream_type)
    """
    from bot.helper.ext_utils.media_utils import get_streams

    streams = await get_streams(file_path)
    if not streams:
        return False, None

    # Check for expected stream type
    type_map = {"video": "v", "audio": "a", "subtitle": "s", "attachment": "t"}

    expected_codec_type = expected_type
    expected_stream_type = type_map.get(expected_type, "v")

    has_expected = any(
        stream.get("codec_type") == expected_codec_type for stream in streams
    )

    if has_expected:
        return True, expected_stream_type

    # Fallback to other available stream types
    for codec_type, stream_type in [
        ("video", "v"),
        ("audio", "a"),
        ("subtitle", "s"),
        ("attachment", "t"),
    ]:
        if any(stream.get("codec_type") == codec_type for stream in streams):
            LOGGER.info(
                f"Using {codec_type} stream instead of {expected_type} stream from {file_path}"
            )
            return False, stream_type

    return False, None


class StreamCache:
    """Cache for stream information to avoid repeated calls to get_streams()"""

    def __init__(self):
        self._cache = {}

    async def get_streams(self, file_path):
        """Get streams for a file, using cache if available"""
        if file_path not in self._cache:
            from bot.helper.ext_utils.media_utils import get_streams

            self._cache[file_path] = await get_streams(file_path)
        return self._cache[file_path]

    def clear(self):
        """Clear the cache"""
        self._cache.clear()


async def get_add_cmd(
    file_path,
    add_video=False,
    add_audio=False,
    add_subtitle=False,
    add_attachment=False,
    video_index=None,
    audio_index=None,
    subtitle_index=None,
    attachment_index=None,
    video_codec="copy",
    audio_codec="copy",
    subtitle_codec="copy",
    video_quality=None,
    video_preset=None,
    video_bitrate=None,
    video_resolution=None,
    video_fps=None,
    audio_bitrate=None,
    audio_channels=None,
    audio_sampling=None,
    audio_volume=None,
    subtitle_language=None,
    subtitle_encoding=None,
    subtitle_font=None,
    subtitle_font_size=None,
    subtitle_hardsub_enabled=False,
    attachment_mimetype=None,
    delete_original=False,
    preserve_tracks=False,
    replace_tracks=False,
    multi_files=None,
):
    """Generate FFmpeg command for adding tracks to a media file.

    Args:
        file_path: Path to the input file
        add_video: Whether to add video track
        add_audio: Whether to add audio track
        add_subtitle: Whether to add subtitle track
        add_attachment: Whether to add attachment
        video_index: Index to place video track (None = append)
        audio_index: Index to place audio track (None = append)
        subtitle_index: Index to place subtitle track (None = append)
        attachment_index: Index to place attachment (None = append)
        video_codec: Video codec to use
        audio_codec: Audio codec to use
        subtitle_codec: Subtitle codec to use
        video_quality: Video quality/CRF value
        video_preset: Video encoding preset
        video_bitrate: Video bitrate
        video_resolution: Video resolution
        video_fps: Video frame rate
        audio_bitrate: Audio bitrate
        audio_channels: Audio channels
        audio_sampling: Audio sampling rate
        audio_volume: Audio volume adjustment
        subtitle_language: Subtitle language code
        subtitle_encoding: Subtitle character encoding
        subtitle_font: Subtitle font
        subtitle_font_size: Subtitle font size
        attachment_mimetype: MIME type for attachment
        delete_original: Whether to delete the original file after processing (-del flag)
        preserve_tracks: Whether to preserve existing tracks when adding new ones (-preserve flag)
        replace_tracks: Whether to replace existing tracks when adding new ones (-replace flag)
        multi_files: List of additional files to use as sources (for multi-input mode)

    Returns:
        tuple: FFmpeg command and temporary output file path, or None, None if not supported
    """
    # Import necessary modules
    from bot import cpu_no
    from bot.helper.ext_utils.media_utils import get_media_type, get_track_info

    # Determine media type of the input file
    media_type = await get_media_type(file_path)
    if not media_type:
        return None, None

    # Get information about existing tracks in the target file
    # This will help us make informed decisions about where to place new tracks
    existing_tracks = await get_track_info(file_path)

    # Check if we're in multi-input mode
    if multi_files:
        # In multi-input mode, we don't need to check for specific track types
        # The first file is the target and subsequent files are sources

        # In multi-input mode, we'll enable track types based on the number of files
        # First additional file is treated as video, second as audio, third as subtitle, etc.
        if len(multi_files) >= 1:
            add_video = True
        if len(multi_files) >= 2:
            add_audio = True
        if len(multi_files) >= 3:
            add_subtitle = True
        if len(multi_files) >= 4:
            add_attachment = True
    # Legacy mode - check if at least one track is being added
    elif not any([add_video, add_audio, add_subtitle, add_attachment]):
        return None, None

    # Determine output file extension based on input file
    file_ext = os.path.splitext(file_path)[1].lower()

    # For videos, always use .mkv as temp extension for maximum compatibility
    if media_type == "video":
        temp_file = f"{file_path}.temp.mkv"
    # For MP3 files with audio tracks being added, use MKV format
    elif file_ext == ".mp3" and add_audio:
        # Check if we're adding audio tracks
        if multi_files:
            has_audio = False
            for additional_file in multi_files:
                from bot.helper.ext_utils.media_utils import get_streams

                streams = await get_streams(additional_file)
                if streams and any(
                    stream.get("codec_type") == "audio" for stream in streams
                ):
                    has_audio = True
                    break

            if has_audio:
                LOGGER.warning(
                    "MP3 files can only contain one audio stream. Converting to MKV format."
                )
                temp_file = f"{file_path}.temp.mkv"
            else:
                # For other files, preserve the original extension
                temp_file = f"{file_path}.temp{file_ext}"
        else:
            # If we're not using multi-input mode, we're definitely adding audio
            LOGGER.warning(
                "MP3 files can only contain one audio stream. Converting to MKV format."
            )
            temp_file = f"{file_path}.temp.mkv"
    # For subtitle files with video tracks being added, use MKV format
    elif file_ext in [".srt", ".ass", ".vtt", ".sub"] and (add_video or multi_files):
        # Check if we're adding video tracks or using multi-input mode
        if multi_files:
            has_video = False
            for additional_file in multi_files:
                from bot.helper.ext_utils.media_utils import get_streams

                streams = await get_streams(additional_file)
                if streams and any(
                    stream.get("codec_type") == "video" for stream in streams
                ):
                    has_video = True
                    break

            if has_video:
                LOGGER.warning(
                    "Subtitle files cannot contain video streams. Converting to MKV format."
                )
                temp_file = f"{file_path}.temp.mkv"
            else:
                # For other files, preserve the original extension
                temp_file = f"{file_path}.temp{file_ext}"
        # If we're not using multi-input mode but adding video to subtitle
        elif add_video:
            LOGGER.warning(
                "Subtitle files cannot contain video streams. Converting to MKV format."
            )
            temp_file = f"{file_path}.temp.mkv"
        else:
            # For other files, preserve the original extension
            temp_file = f"{file_path}.temp{file_ext}"
    else:
        # For other files, preserve the original extension
        temp_file = f"{file_path}.temp{file_ext}"

    # Base command for all media types
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file_path,
    ]

    # Add input files for tracks to be added

    # Track the input indices for mapping
    video_input_idx = None
    audio_input_idx = None
    subtitle_input_idx = None
    attachment_input_idx = None

    if multi_files:
        # In multi-input mode, add all additional files as inputs
        for i, additional_file in enumerate(multi_files):
            cmd.extend(["-i", additional_file])
            # The first additional file is input 1, second is input 2, etc.
            if i == 0:
                video_input_idx = 1
            elif i == 1:
                audio_input_idx = 2
            elif i == 2:
                subtitle_input_idx = 3
            elif i == 3:
                attachment_input_idx = 4
    else:
        # Legacy mode - no specific files for each track type in this mode
        pass

    # Add mapping for the original file streams
    map_args = []

    # Handle the track mapping based on flags
    if replace_tracks:
        # If -replace flag is present, we need to map all streams except the ones we're replacing
        # We'll handle the mapping for each track type separately in the track-specific sections below
        # Don't add a general -map 0 here
        pass
    else:
        # Map all streams from the original file
        map_args.extend(["-map", "0"])

    # Determine stream types for each input file
    # This is important for correct mapping
    video_stream_type = "v"  # Default stream type for video files
    audio_stream_type = "a"  # Default stream type for audio files
    subtitle_stream_type = "s"  # Default stream type for subtitle files
    attachment_stream_type = "t"  # Default stream type for attachment files

    # Determine stream types based on file content
    if multi_files:
        from bot.helper.ext_utils.media_utils import get_streams

        # Check each input file for stream types
        for i, additional_file in enumerate(multi_files):
            streams = await get_streams(additional_file)
            if not streams:
                LOGGER.warning(f"No streams found in file: {additional_file}")
                continue

            # Determine the primary stream type for this file
            has_video = any(
                stream.get("codec_type") == "video" for stream in streams
            )
            has_audio = any(
                stream.get("codec_type") == "audio" for stream in streams
            )
            has_subtitle = any(
                stream.get("codec_type") == "subtitle" for stream in streams
            )
            has_attachment = any(
                stream.get("codec_type") == "attachment" for stream in streams
            )

            # Update the stream type for this input index
            if i == 0 and video_input_idx is not None:
                if has_video:
                    video_stream_type = "v"
                elif has_audio:
                    video_stream_type = "a"
                    LOGGER.info(
                        f"Using audio stream from file {additional_file} as video input"
                    )
                elif has_subtitle:
                    video_stream_type = "s"
                    LOGGER.info(
                        f"Using subtitle stream from file {additional_file} as video input"
                    )
                elif has_attachment:
                    video_stream_type = "t"
                    LOGGER.info(
                        f"Using attachment stream from file {additional_file} as video input"
                    )

            if i == 1 and audio_input_idx is not None:
                if has_audio:
                    audio_stream_type = "a"
                elif has_video:
                    audio_stream_type = "v"
                    LOGGER.info(
                        f"Using video stream from file {additional_file} as audio input"
                    )
                elif has_subtitle:
                    audio_stream_type = "s"
                    LOGGER.info(
                        f"Using subtitle stream from file {additional_file} as audio input"
                    )
                elif has_attachment:
                    audio_stream_type = "t"
                    LOGGER.info(
                        f"Using attachment stream from file {additional_file} as audio input"
                    )

            if i == 2 and subtitle_input_idx is not None:
                if has_subtitle:
                    subtitle_stream_type = "s"
                elif has_video:
                    subtitle_stream_type = "v"
                    LOGGER.info(
                        f"Using video stream from file {additional_file} as subtitle input"
                    )
                elif has_audio:
                    subtitle_stream_type = "a"
                    LOGGER.info(
                        f"Using audio stream from file {additional_file} as subtitle input"
                    )
                elif has_attachment:
                    subtitle_stream_type = "t"
                    LOGGER.info(
                        f"Using attachment stream from file {additional_file} as subtitle input"
                    )

            if i == 3 and attachment_input_idx is not None:
                if has_attachment:
                    attachment_stream_type = "t"
                elif has_video:
                    attachment_stream_type = "v"
                    LOGGER.info(
                        f"Using video stream from file {additional_file} as attachment input"
                    )
                elif has_audio:
                    attachment_stream_type = "a"
                    LOGGER.info(
                        f"Using audio stream from file {additional_file} as attachment input"
                    )
                elif has_subtitle:
                    attachment_stream_type = "s"
                    LOGGER.info(
                        f"Using subtitle stream from file {additional_file} as attachment input"
                    )

    # Stream types for mapping
    # video_stream_type, audio_stream_type, subtitle_stream_type, attachment_stream_type are defined above

    # Map additional tracks
    # For multi-input mode with multiple files, we need to handle mapping differently
    if multi_files:
        # In multi-input mode, we need to map each file to the correct index
        # The indices in the comma-separated list correspond to the order of input files

        # Handle video tracks
        # Check if the input file has video streams
        from bot.helper.ext_utils.media_utils import get_streams

        if video_input_idx is not None:
            # Check if the input file has video streams
            video_file = (
                multi_files[0] if multi_files and len(multi_files) > 0 else file_path
            )
            video_streams = await get_streams(video_file)
            has_video_stream = (
                any(stream.get("codec_type") == "video" for stream in video_streams)
                if video_streams
                else False
            )

            if not has_video_stream:
                LOGGER.warning(f"No video streams found in input file {video_file}")
                # Use audio stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in video_streams
                    )
                    if video_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of video stream from {video_file}"
                    )
                    video_stream_type = "a"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in video_streams
                    )
                    if video_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of video stream from {video_file}"
                    )
                    video_stream_type = "s"
                else:
                    # Skip this input file
                    video_input_idx = None
            if video_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(video_index):
                    # Handle multiple indices
                    indices = str(video_index).split(",")
                    # In multi-input mode, we need to map each file to its corresponding index
                    # The first index corresponds to the first file, second index to second file, etc.
                    for i, idx in enumerate(indices):
                        if idx.strip().isdigit():
                            # Calculate the correct input index based on the position in multi_files
                            # video_input_idx is 1 for the first file, but we need to adjust for multiple files
                            if i < len(multi_files):
                                current_input_idx = (
                                    i + 1
                                )  # +1 because the main file is input 0

                                # Check if the specified index is already occupied by an existing video track
                                target_idx = int(idx.strip())
                                existing_video_indices = [
                                    track["index"]
                                    for track in existing_tracks["video"]
                                ]

                                # Use the new helper function to resolve the index
                                actual_idx = resolve_track_index(
                                    target_idx,
                                    existing_video_indices,
                                    replace_mode=replace_tracks,
                                    preserve_mode=preserve_tracks,
                                )

                                if actual_idx != target_idx:
                                    LOGGER.info(
                                        f"Index {target_idx} adjusted to {actual_idx} based on mode and conflicts."
                                    )

                                # Log the existing indices and target index
                                LOGGER.info(
                                    f"Adding video track from input {current_input_idx} to index {actual_idx}"
                                )
                                LOGGER.info(
                                    f"Existing video indices: {existing_video_indices}"
                                )

                                # Add the mapping
                                map_args.extend(
                                    [
                                        "-map",
                                        f"{current_input_idx}:{video_stream_type}",
                                    ]
                                )
                elif str(video_index).isdigit():
                    # Insert at specific index
                    target_idx = int(video_index)
                    existing_video_indices = [
                        track["index"] for track in existing_tracks["video"]
                    ]

                    # Check if the target index is beyond the current count of tracks
                    # If so, use the first available index
                    if target_idx >= len(existing_video_indices):
                        actual_idx = find_first_available_index(
                            existing_video_indices, target_idx
                        )
                        LOGGER.info(
                            f"Specified video index {target_idx} is beyond existing tracks. Using index {actual_idx} instead."
                        )
                    # Check if the index is already occupied
                    elif target_idx in existing_video_indices:
                        if replace_tracks:
                            # If replace flag is set, use the specified index
                            actual_idx = target_idx

                        else:
                            # Find the next available index
                            actual_idx = find_next_available_index(
                                existing_video_indices, target_idx
                            )

                    else:
                        actual_idx = target_idx

                    map_args.extend(
                        ["-map", f"{video_input_idx}:{video_stream_type}"]
                    )
                else:
                    # Append to the end

                    map_args.extend(
                        ["-map", f"{video_input_idx}:{video_stream_type}"]
                    )
            else:
                # Append to the end

                map_args.extend(["-map", f"{video_input_idx}:{video_stream_type}"])

        # Handle audio tracks
        # Check if the input file has audio streams
        from bot.helper.ext_utils.media_utils import get_streams

        if audio_input_idx is not None:
            # Check if the input file has audio streams
            audio_file = (
                multi_files[1] if multi_files and len(multi_files) > 1 else file_path
            )
            audio_streams = await get_streams(audio_file)
            has_audio_stream = (
                any(stream.get("codec_type") == "audio" for stream in audio_streams)
                if audio_streams
                else False
            )

            if not has_audio_stream:
                LOGGER.warning(f"No audio streams found in input file {audio_file}")
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in audio_streams
                    )
                    if audio_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of audio stream from {audio_file}"
                    )
                    audio_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in audio_streams
                    )
                    if audio_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of audio stream from {audio_file}"
                    )
                    audio_stream_type = "s"
                else:
                    # Skip this input file
                    audio_input_idx = None
            if audio_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(audio_index):
                    # Handle multiple indices
                    indices = str(audio_index).split(",")
                    for i, idx in enumerate(indices):
                        if idx.strip().isdigit():
                            # For audio, we need to offset by the number of video files
                            # The first audio file is after all video files
                            video_count = (
                                len(str(video_index).split(","))
                                if video_index and "," in str(video_index)
                                else (1 if video_input_idx is not None else 0)
                            )
                            if i < len(multi_files) - video_count:
                                current_input_idx = (
                                    video_count + i + 1
                                )  # +1 because the main file is input 0

                                # Check if the specified index is already occupied by an existing audio track
                                target_idx = int(idx.strip())
                                existing_audio_indices = [
                                    track["index"]
                                    for track in existing_tracks["audio"]
                                ]

                                # Check if the target index is beyond the current count of tracks
                                # If so, use the first available index
                                if target_idx >= len(existing_audio_indices) + i:
                                    actual_idx = find_first_available_index(
                                        existing_audio_indices, target_idx
                                    )

                                # Check if the index is already occupied
                                elif target_idx in existing_audio_indices:
                                    if replace_tracks:
                                        # If replace flag is set, use the specified index
                                        actual_idx = target_idx

                                    else:
                                        # Find the next available index
                                        actual_idx = find_next_available_index(
                                            existing_audio_indices, target_idx
                                        )
                                        LOGGER.info(
                                            f"Index {target_idx} is already occupied. Using next available index {actual_idx} instead."
                                        )
                                else:
                                    actual_idx = target_idx

                                # Log the existing indices and target index
                                LOGGER.info(
                                    f"Adding audio track from input {current_input_idx} to index {actual_idx}"
                                )
                                LOGGER.info(
                                    f"Existing audio indices: {existing_audio_indices}"
                                )

                                # Add the mapping
                                map_args.extend(
                                    [
                                        "-map",
                                        f"{current_input_idx}:{audio_stream_type}",
                                    ]
                                )
                elif str(audio_index).isdigit():
                    # Insert at specific index
                    target_idx = int(audio_index)
                    existing_audio_indices = [
                        track["index"] for track in existing_tracks["audio"]
                    ]

                    # Check if the target index is beyond the current count of tracks
                    # If so, use the first available index
                    if target_idx >= len(existing_audio_indices):
                        actual_idx = find_first_available_index(
                            existing_audio_indices, target_idx
                        )
                        LOGGER.info(
                            f"Specified audio index {target_idx} is beyond existing tracks. Using index {actual_idx} instead."
                        )
                    # Check if the index is already occupied
                    elif target_idx in existing_audio_indices:
                        if replace_tracks:
                            # If replace flag is set, use the specified index
                            actual_idx = target_idx

                        else:
                            # Find the next available index
                            actual_idx = find_next_available_index(
                                existing_audio_indices, target_idx
                            )

                    else:
                        actual_idx = target_idx

                    map_args.extend(
                        ["-map", f"{audio_input_idx}:{audio_stream_type}"]
                    )
                else:
                    # Append to the end

                    map_args.extend(
                        ["-map", f"{audio_input_idx}:{audio_stream_type}"]
                    )
            else:
                # Append to the end

                map_args.extend(["-map", f"{audio_input_idx}:{audio_stream_type}"])

        # Handle subtitle tracks
        # Check if the input file has subtitle streams
        from bot.helper.ext_utils.media_utils import get_streams

        if subtitle_input_idx is not None:
            # Check if the input file has subtitle streams
            subtitle_file = (
                multi_files[2] if multi_files and len(multi_files) > 2 else file_path
            )
            subtitle_streams = await get_streams(subtitle_file)
            has_subtitle_stream = (
                any(
                    stream.get("codec_type") == "subtitle"
                    for stream in subtitle_streams
                )
                if subtitle_streams
                else False
            )

            if not has_subtitle_stream:
                LOGGER.warning(
                    f"No subtitle streams found in input file {subtitle_file}"
                )
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in subtitle_streams
                    )
                    if subtitle_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of subtitle stream from {subtitle_file}"
                    )
                    subtitle_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in subtitle_streams
                    )
                    if subtitle_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of subtitle stream from {subtitle_file}"
                    )
                    subtitle_stream_type = "a"
                else:
                    # Skip this input file
                    subtitle_input_idx = None
            if subtitle_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(subtitle_index):
                    # Handle multiple indices
                    indices = str(subtitle_index).split(",")
                    for i, idx in enumerate(indices):
                        if idx.strip().isdigit():
                            # For subtitles, we need to offset by the number of video and audio files
                            video_count = (
                                len(str(video_index).split(","))
                                if video_index and "," in str(video_index)
                                else (1 if video_input_idx is not None else 0)
                            )
                            audio_count = (
                                len(str(audio_index).split(","))
                                if audio_index and "," in str(audio_index)
                                else (1 if audio_input_idx is not None else 0)
                            )
                            if i < len(multi_files) - video_count - audio_count:
                                current_input_idx = (
                                    video_count + audio_count + i + 1
                                )  # +1 because the main file is input 0

                                # Check if the specified index is already occupied by an existing subtitle track
                                target_idx = int(idx.strip())
                                existing_subtitle_indices = [
                                    track["index"]
                                    for track in existing_tracks["subtitle"]
                                ]

                                # Check if the target index is beyond the current count of tracks
                                # If so, use the first available index
                                if target_idx >= len(existing_subtitle_indices) + i:
                                    actual_idx = find_first_available_index(
                                        existing_subtitle_indices, target_idx
                                    )

                                # Check if the index is already occupied
                                elif target_idx in existing_subtitle_indices:
                                    if replace_tracks:
                                        # If replace flag is set, use the specified index
                                        actual_idx = target_idx

                                    else:
                                        # Find the next available index
                                        actual_idx = find_next_available_index(
                                            existing_subtitle_indices, target_idx
                                        )
                                        LOGGER.info(
                                            f"Index {target_idx} is already occupied. Using next available index {actual_idx} instead."
                                        )
                                else:
                                    actual_idx = target_idx

                                # Log the existing indices and target index
                                LOGGER.info(
                                    f"Adding subtitle track from input {current_input_idx} to index {actual_idx}"
                                )
                                LOGGER.info(
                                    f"Existing subtitle indices: {existing_subtitle_indices}"
                                )

                                # Add the mapping
                                map_args.extend(
                                    [
                                        "-map",
                                        f"{current_input_idx}:{subtitle_stream_type}",
                                    ]
                                )
                elif str(subtitle_index).isdigit():
                    # Insert at specific index
                    target_idx = int(subtitle_index)
                    existing_subtitle_indices = [
                        track["index"] for track in existing_tracks["subtitle"]
                    ]

                    # Check if the target index is beyond the current count of tracks
                    # If so, use the first available index
                    if target_idx >= len(existing_subtitle_indices):
                        actual_idx = find_first_available_index(
                            existing_subtitle_indices, target_idx
                        )
                        LOGGER.info(
                            f"Specified subtitle index {target_idx} is beyond existing tracks. Using index {actual_idx} instead."
                        )
                    # Check if the index is already occupied
                    elif target_idx in existing_subtitle_indices:
                        if replace_tracks:
                            # If replace flag is set, use the specified index
                            actual_idx = target_idx

                        else:
                            # Find the next available index
                            actual_idx = find_next_available_index(
                                existing_subtitle_indices, target_idx
                            )

                    else:
                        actual_idx = target_idx

                    map_args.extend(
                        ["-map", f"{subtitle_input_idx}:{subtitle_stream_type}"]
                    )
                else:
                    # Append to the end

                    map_args.extend(
                        ["-map", f"{subtitle_input_idx}:{subtitle_stream_type}"]
                    )
            else:
                # Append to the end

                map_args.extend(
                    ["-map", f"{subtitle_input_idx}:{subtitle_stream_type}"]
                )

        # Handle attachment tracks
        # Check if the input file has attachment streams
        from bot.helper.ext_utils.media_utils import get_streams

        if attachment_input_idx is not None:
            # Check if the input file has attachment streams
            attachment_file = (
                multi_files[3] if multi_files and len(multi_files) > 3 else file_path
            )
            attachment_streams = await get_streams(attachment_file)
            has_attachment_stream = (
                any(
                    stream.get("codec_type") == "attachment"
                    for stream in attachment_streams
                )
                if attachment_streams
                else False
            )

            if not has_attachment_stream:
                LOGGER.warning(
                    f"No attachment streams found in input file {attachment_file}"
                )
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "a"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "s"
                else:
                    # Skip this input file
                    attachment_input_idx = None
            if attachment_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(attachment_index):
                    # Handle multiple indices
                    indices = str(attachment_index).split(",")
                    for i, idx in enumerate(indices):
                        if idx.strip().isdigit():
                            # For attachments, we need to offset by the number of video, audio, and subtitle files
                            video_count = (
                                len(str(video_index).split(","))
                                if video_index and "," in str(video_index)
                                else (1 if video_input_idx is not None else 0)
                            )
                            audio_count = (
                                len(str(audio_index).split(","))
                                if audio_index and "," in str(audio_index)
                                else (1 if audio_input_idx is not None else 0)
                            )
                            subtitle_count = (
                                len(str(subtitle_index).split(","))
                                if subtitle_index and "," in str(subtitle_index)
                                else (1 if subtitle_input_idx is not None else 0)
                            )
                            if (
                                i
                                < len(multi_files)
                                - video_count
                                - audio_count
                                - subtitle_count
                            ):
                                current_input_idx = (
                                    video_count
                                    + audio_count
                                    + subtitle_count
                                    + i
                                    + 1
                                )  # +1 because the main file is input 0

                                # Check if the specified index is already occupied by an existing attachment
                                target_idx = int(idx.strip())
                                existing_attachment_indices = [
                                    track["index"]
                                    for track in existing_tracks["attachment"]
                                ]

                                # Check if the target index is beyond the current count of tracks
                                # If so, use the first available index
                                if (
                                    target_idx
                                    >= len(existing_attachment_indices) + i
                                ):
                                    actual_idx = find_first_available_index(
                                        existing_attachment_indices, target_idx
                                    )

                                # Check if the index is already occupied
                                elif target_idx in existing_attachment_indices:
                                    if replace_tracks:
                                        # If replace flag is set, use the specified index
                                        actual_idx = target_idx

                                    else:
                                        # Find the next available index
                                        actual_idx = find_next_available_index(
                                            existing_attachment_indices,
                                            target_idx,
                                        )
                                        LOGGER.info(
                                            f"Index {target_idx} is already occupied. Using next available index {actual_idx} instead."
                                        )
                                else:
                                    actual_idx = target_idx

                                # Log the existing indices and target index
                                LOGGER.info(
                                    f"Adding attachment from input {current_input_idx} to index {actual_idx}"
                                )
                                LOGGER.info(
                                    f"Existing attachment indices: {existing_attachment_indices}"
                                )

                                # Add the mapping
                                map_args.extend(
                                    [
                                        "-map",
                                        f"{current_input_idx}:{attachment_stream_type}",
                                    ]
                                )
                elif str(attachment_index).isdigit():
                    # Insert at specific index
                    target_idx = int(attachment_index)
                    existing_attachment_indices = [
                        track["index"] for track in existing_tracks["attachment"]
                    ]

                    # Check if the target index is beyond the current count of tracks
                    # If so, use the first available index
                    if target_idx >= len(existing_attachment_indices):
                        actual_idx = find_first_available_index(
                            existing_attachment_indices, target_idx
                        )

                    # Check if the index is already occupied
                    elif target_idx in existing_attachment_indices:
                        if replace_tracks:
                            # If replace flag is set, use the specified index
                            actual_idx = target_idx

                        else:
                            # Find the next available index
                            actual_idx = find_next_available_index(
                                existing_attachment_indices, target_idx
                            )

                    else:
                        actual_idx = target_idx

                    map_args.extend(
                        ["-map", f"{attachment_input_idx}:{attachment_stream_type}"]
                    )
                else:
                    # Append to the end

                    map_args.extend(
                        ["-map", f"{attachment_input_idx}:{attachment_stream_type}"]
                    )
            else:
                # Append to the end

                map_args.extend(
                    ["-map", f"{attachment_input_idx}:{attachment_stream_type}"]
                )
    else:
        # Legacy mode - simpler mapping
        # Check if the input file has video streams
        from bot.helper.ext_utils.media_utils import get_streams

        if video_input_idx is not None:
            # Check if the input file has video streams
            video_file = (
                multi_files[0] if multi_files and len(multi_files) > 0 else file_path
            )
            video_streams = await get_streams(video_file)
            has_video_stream = (
                any(stream.get("codec_type") == "video" for stream in video_streams)
                if video_streams
                else False
            )

            if not has_video_stream:
                LOGGER.warning(f"No video streams found in input file {video_file}")
                # Use audio stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in video_streams
                    )
                    if video_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of video stream from {video_file}"
                    )
                    video_stream_type = "a"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in video_streams
                    )
                    if video_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of video stream from {video_file}"
                    )
                    video_stream_type = "s"
                else:
                    # Skip this input file
                    video_input_idx = None
            if video_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(video_index):
                    # Handle multiple indices
                    indices = str(video_index).split(",")
                    for idx in indices:
                        if idx.strip().isdigit():
                            map_args.extend(
                                ["-map", f"{video_input_idx}:{video_stream_type}"]
                            )
                elif str(video_index).isdigit():
                    # Insert at specific index
                    map_args.extend(
                        ["-map", f"{video_input_idx}:{video_stream_type}"]
                    )
                else:
                    # Append to the end
                    map_args.extend(
                        ["-map", f"{video_input_idx}:{video_stream_type}"]
                    )
            else:
                # Append to the end
                map_args.extend(["-map", f"{video_input_idx}:{video_stream_type}"])

        # Check if the input file has audio streams
        from bot.helper.ext_utils.media_utils import get_streams

        if audio_input_idx is not None:
            # Check if the input file has audio streams
            audio_file = (
                multi_files[1] if multi_files and len(multi_files) > 1 else file_path
            )
            audio_streams = await get_streams(audio_file)
            has_audio_stream = (
                any(stream.get("codec_type") == "audio" for stream in audio_streams)
                if audio_streams
                else False
            )

            if not has_audio_stream:
                LOGGER.warning(f"No audio streams found in input file {audio_file}")
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in audio_streams
                    )
                    if audio_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of audio stream from {audio_file}"
                    )
                    audio_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in audio_streams
                    )
                    if audio_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of audio stream from {audio_file}"
                    )
                    audio_stream_type = "s"
                else:
                    # Skip this input file
                    audio_input_idx = None
            if audio_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(audio_index):
                    # Handle multiple indices
                    indices = str(audio_index).split(",")
                    for idx in indices:
                        if idx.strip().isdigit():
                            map_args.extend(
                                ["-map", f"{audio_input_idx}:{audio_stream_type}"]
                            )
                elif str(audio_index).isdigit():
                    # Insert at specific index
                    map_args.extend(
                        ["-map", f"{audio_input_idx}:{audio_stream_type}"]
                    )
                else:
                    # Append to the end
                    map_args.extend(
                        ["-map", f"{audio_input_idx}:{audio_stream_type}"]
                    )
            else:
                # Append to the end
                map_args.extend(["-map", f"{audio_input_idx}:{audio_stream_type}"])

        # Check if the input file has subtitle streams
        from bot.helper.ext_utils.media_utils import get_streams

        if subtitle_input_idx is not None:
            # Check if the input file has subtitle streams
            subtitle_file = (
                multi_files[2] if multi_files and len(multi_files) > 2 else file_path
            )
            subtitle_streams = await get_streams(subtitle_file)
            has_subtitle_stream = (
                any(
                    stream.get("codec_type") == "subtitle"
                    for stream in subtitle_streams
                )
                if subtitle_streams
                else False
            )

            if not has_subtitle_stream:
                LOGGER.warning(
                    f"No subtitle streams found in input file {subtitle_file}"
                )
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in subtitle_streams
                    )
                    if subtitle_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of subtitle stream from {subtitle_file}"
                    )
                    subtitle_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in subtitle_streams
                    )
                    if subtitle_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of subtitle stream from {subtitle_file}"
                    )
                    subtitle_stream_type = "a"
                else:
                    # Skip this input file
                    subtitle_input_idx = None

            # Handle hardsub vs soft subtitle
            if subtitle_hardsub_enabled:
                # For hardsub, we need to use a video filter to burn subtitles into video
                # This requires modifying the video codec and adding a filter
                LOGGER.info("Hardsub enabled: burning subtitles into video")
                # We'll handle this in the codec section below
                # Don't add subtitle mapping for hardsub
            # Regular soft subtitle mapping
            elif subtitle_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(subtitle_index):
                    # Handle multiple indices
                    indices = str(subtitle_index).split(",")
                    for idx in indices:
                        if idx.strip().isdigit():
                            map_args.extend(
                                [
                                    "-map",
                                    f"{subtitle_input_idx}:{subtitle_stream_type}",
                                ]
                            )
                elif str(subtitle_index).isdigit():
                    # Insert at specific index
                    map_args.extend(
                        ["-map", f"{subtitle_input_idx}:{subtitle_stream_type}"]
                    )
                else:
                    # Append to the end
                    map_args.extend(
                        ["-map", f"{subtitle_input_idx}:{subtitle_stream_type}"]
                    )
            else:
                # Append to the end
                map_args.extend(
                    ["-map", f"{subtitle_input_idx}:{subtitle_stream_type}"]
                )

        # Check if the input file has attachment streams
        from bot.helper.ext_utils.media_utils import get_streams

        if attachment_input_idx is not None:
            # Check if the input file has attachment streams
            attachment_file = (
                multi_files[3] if multi_files and len(multi_files) > 3 else file_path
            )
            attachment_streams = await get_streams(attachment_file)
            has_attachment_stream = (
                any(
                    stream.get("codec_type") == "attachment"
                    for stream in attachment_streams
                )
                if attachment_streams
                else False
            )

            if not has_attachment_stream:
                LOGGER.warning(
                    f"No attachment streams found in input file {attachment_file}"
                )
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "a"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "s"
                else:
                    # Skip this input file
                    attachment_input_idx = None
            if attachment_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(attachment_index):
                    # Handle multiple indices
                    indices = str(attachment_index).split(",")
                    for idx in indices:
                        if idx.strip().isdigit():
                            map_args.extend(
                                [
                                    "-map",
                                    f"{attachment_input_idx}:{attachment_stream_type}",
                                ]
                            )
                elif str(attachment_index).isdigit():
                    # Insert at specific index
                    map_args.extend(
                        ["-map", f"{attachment_input_idx}:{attachment_stream_type}"]
                    )
                else:
                    # Append to the end
                    map_args.extend(
                        ["-map", f"{attachment_input_idx}:{attachment_stream_type}"]
                    )
            else:
                # Append to the end
                map_args.extend(
                    ["-map", f"{attachment_input_idx}:{attachment_stream_type}"]
                )

    # Add the mapping arguments to the command
    cmd.extend(map_args)

    # Add codec settings
    codec_args = []

    # Set default to copy for all streams
    codec_args.extend(["-c", "copy"])

    # Add metadata for each track type
    metadata_args = []

    # For multi-input mode with multiple files, we need to handle metadata differently
    if multi_files:
        # In multi-input mode, we need to add metadata for each file based on its index

        # Add metadata for video tracks
        # Check if the input file has video streams
        from bot.helper.ext_utils.media_utils import get_streams

        if video_input_idx is not None:
            # Check if the input file has video streams
            video_file = (
                multi_files[0] if multi_files and len(multi_files) > 0 else file_path
            )
            video_streams = await get_streams(video_file)
            has_video_stream = (
                any(stream.get("codec_type") == "video" for stream in video_streams)
                if video_streams
                else False
            )

            if not has_video_stream:
                LOGGER.warning(f"No video streams found in input file {video_file}")
                # Use audio stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in video_streams
                    )
                    if video_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of video stream from {video_file}"
                    )
                    video_stream_type = "a"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in video_streams
                    )
                    if video_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of video stream from {video_file}"
                    )
                    video_stream_type = "s"
                else:
                    # Skip this input file
                    video_input_idx = None
            if video_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(video_index):
                    # Handle multiple indices
                    indices = str(video_index).split(",")
                    for i, idx in enumerate(indices):
                        if idx.strip().isdigit():
                            # Use the actual index that was determined during mapping
                            # We need to recalculate it here
                            target_idx = int(idx.strip())
                            existing_video_indices = [
                                track["index"] for track in existing_tracks["video"]
                            ]

                            if target_idx >= len(existing_video_indices) + i:
                                actual_idx = find_first_available_index(
                                    existing_video_indices
                                )
                            else:
                                actual_idx = target_idx

                            metadata_args.extend(
                                [
                                    f"-metadata:s:v:{actual_idx}",
                                    "title=Added Video Track",
                                ]
                            )
                elif str(video_index).isdigit():
                    # Insert at specific index
                    # Use the actual index that was determined during mapping
                    target_idx = int(video_index)
                    existing_video_indices = [
                        track["index"] for track in existing_tracks["video"]
                    ]

                    if target_idx >= len(existing_video_indices):
                        actual_idx = find_first_available_index(
                            existing_video_indices
                        )

                    else:
                        actual_idx = target_idx

                    metadata_args.extend(
                        [f"-metadata:s:v:{actual_idx}", "title=Added Video Track"]
                    )
                else:
                    # Append to the end - we don't know the index, so we can't add metadata
                    pass
            else:
                # Append to the end - we don't know the index, so we can't add metadata
                pass

        # Add metadata for audio tracks
        # Check if the input file has audio streams
        from bot.helper.ext_utils.media_utils import get_streams

        if audio_input_idx is not None:
            # Check if the input file has audio streams
            audio_file = (
                multi_files[1] if multi_files and len(multi_files) > 1 else file_path
            )
            audio_streams = await get_streams(audio_file)
            has_audio_stream = (
                any(stream.get("codec_type") == "audio" for stream in audio_streams)
                if audio_streams
                else False
            )

            if not has_audio_stream:
                LOGGER.warning(f"No audio streams found in input file {audio_file}")
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in audio_streams
                    )
                    if audio_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of audio stream from {audio_file}"
                    )
                    audio_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in audio_streams
                    )
                    if audio_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of audio stream from {audio_file}"
                    )
                    audio_stream_type = "s"
                else:
                    # Skip this input file
                    audio_input_idx = None
            if audio_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(audio_index):
                    # Handle multiple indices
                    indices = str(audio_index).split(",")
                    for i, idx in enumerate(indices):
                        if idx.strip().isdigit():
                            # Use the actual index that was determined during mapping
                            # We need to recalculate it here
                            target_idx = int(idx.strip())
                            existing_audio_indices = [
                                track["index"] for track in existing_tracks["audio"]
                            ]

                            if target_idx >= len(existing_audio_indices) + i:
                                actual_idx = find_first_available_index(
                                    existing_audio_indices
                                )

                            else:
                                actual_idx = target_idx

                            metadata_args.extend(
                                [
                                    f"-metadata:s:a:{actual_idx}",
                                    "title=Added Audio Track",
                                ]
                            )
                elif str(audio_index).isdigit():
                    # Insert at specific index
                    # Use the actual index that was determined during mapping
                    target_idx = int(audio_index)
                    existing_audio_indices = [
                        track["index"] for track in existing_tracks["audio"]
                    ]

                    if target_idx >= len(existing_audio_indices):
                        actual_idx = find_first_available_index(
                            existing_audio_indices
                        )

                    else:
                        actual_idx = target_idx

                    metadata_args.extend(
                        [f"-metadata:s:a:{actual_idx}", "title=Added Audio Track"]
                    )
                else:
                    # Append to the end - we don't know the index, so we can't add metadata
                    pass
            else:
                # Append to the end - we don't know the index, so we can't add metadata
                pass

        # Add metadata for subtitle tracks
        # Check if the input file has subtitle streams
        from bot.helper.ext_utils.media_utils import get_streams

        if subtitle_input_idx is not None:
            # Check if the input file has subtitle streams
            subtitle_file = (
                multi_files[2] if multi_files and len(multi_files) > 2 else file_path
            )
            subtitle_streams = await get_streams(subtitle_file)
            has_subtitle_stream = (
                any(
                    stream.get("codec_type") == "subtitle"
                    for stream in subtitle_streams
                )
                if subtitle_streams
                else False
            )

            if not has_subtitle_stream:
                LOGGER.warning(
                    f"No subtitle streams found in input file {subtitle_file}"
                )
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in subtitle_streams
                    )
                    if subtitle_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of subtitle stream from {subtitle_file}"
                    )
                    subtitle_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in subtitle_streams
                    )
                    if subtitle_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of subtitle stream from {subtitle_file}"
                    )
                    subtitle_stream_type = "a"
                else:
                    # Skip this input file
                    subtitle_input_idx = None
            if subtitle_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(subtitle_index):
                    # Handle multiple indices
                    indices = str(subtitle_index).split(",")
                    for i, idx in enumerate(indices):
                        if idx.strip().isdigit():
                            # Use the actual index that was determined during mapping
                            # We need to recalculate it here
                            target_idx = int(idx.strip())
                            existing_subtitle_indices = [
                                track["index"]
                                for track in existing_tracks["subtitle"]
                            ]

                            if target_idx >= len(existing_subtitle_indices) + i:
                                actual_idx = find_first_available_index(
                                    existing_subtitle_indices
                                )

                            else:
                                actual_idx = target_idx

                            metadata_args.extend(
                                [
                                    f"-metadata:s:s:{actual_idx}",
                                    "title=Added Subtitle Track",
                                ]
                            )
                elif str(subtitle_index).isdigit():
                    # Insert at specific index
                    # Use the actual index that was determined during mapping
                    target_idx = int(subtitle_index)
                    existing_subtitle_indices = [
                        track["index"] for track in existing_tracks["subtitle"]
                    ]

                    if target_idx >= len(existing_subtitle_indices):
                        actual_idx = find_first_available_index(
                            existing_subtitle_indices
                        )

                    else:
                        actual_idx = target_idx

                    metadata_args.extend(
                        [f"-metadata:s:s:{actual_idx}", "title=Added Subtitle Track"]
                    )
                else:
                    # Append to the end - we don't know the index, so we can't add metadata
                    pass
            else:
                # Append to the end - we don't know the index, so we can't add metadata
                pass

        # Add metadata for attachment tracks
        # Check if the input file has attachment streams
        from bot.helper.ext_utils.media_utils import get_streams

        if attachment_input_idx is not None:
            # Check if the input file has attachment streams
            attachment_file = (
                multi_files[3] if multi_files and len(multi_files) > 3 else file_path
            )
            attachment_streams = await get_streams(attachment_file)
            has_attachment_stream = (
                any(
                    stream.get("codec_type") == "attachment"
                    for stream in attachment_streams
                )
                if attachment_streams
                else False
            )

            if not has_attachment_stream:
                LOGGER.warning(
                    f"No attachment streams found in input file {attachment_file}"
                )
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "a"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "s"
                else:
                    # Skip this input file
                    attachment_input_idx = None
            if attachment_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(attachment_index):
                    # Handle multiple indices
                    indices = str(attachment_index).split(",")
                    for i, idx in enumerate(indices):
                        if idx.strip().isdigit():
                            # Use the actual index that was determined during mapping
                            # We need to recalculate it here
                            target_idx = int(idx.strip())
                            existing_attachment_indices = [
                                track["index"]
                                for track in existing_tracks["attachment"]
                            ]

                            if target_idx >= len(existing_attachment_indices) + i:
                                actual_idx = find_first_available_index(
                                    existing_attachment_indices
                                )
                                LOGGER.info(
                                    f"Specified attachment index {target_idx} is beyond existing tracks. Using index {actual_idx} instead for metadata."
                                )
                            else:
                                actual_idx = target_idx

                            metadata_args.extend(
                                [
                                    f"-metadata:s:t:{actual_idx}",
                                    "title=Added Attachment",
                                ]
                            )
                elif str(attachment_index).isdigit():
                    # Insert at specific index
                    # Use the actual index that was determined during mapping
                    target_idx = int(attachment_index)
                    existing_attachment_indices = [
                        track["index"] for track in existing_tracks["attachment"]
                    ]

                    if target_idx >= len(existing_attachment_indices):
                        actual_idx = find_first_available_index(
                            existing_attachment_indices
                        )

                    else:
                        actual_idx = target_idx

                    metadata_args.extend(
                        [f"-metadata:s:t:{actual_idx}", "title=Added Attachment"]
                    )
                else:
                    # Append to the end - we don't know the index, so we can't add metadata
                    pass
            else:
                # Append to the end - we don't know the index, so we can't add metadata
                pass
    else:
        # Legacy mode - simpler metadata handling
        # Add metadata for video tracks
        # Check if the input file has video streams
        from bot.helper.ext_utils.media_utils import get_streams

        if video_input_idx is not None:
            # Check if the input file has video streams
            video_file = (
                multi_files[0] if multi_files and len(multi_files) > 0 else file_path
            )
            video_streams = await get_streams(video_file)
            has_video_stream = (
                any(stream.get("codec_type") == "video" for stream in video_streams)
                if video_streams
                else False
            )

            if not has_video_stream:
                LOGGER.warning(f"No video streams found in input file {video_file}")
                # Use audio stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in video_streams
                    )
                    if video_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of video stream from {video_file}"
                    )
                    video_stream_type = "a"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in video_streams
                    )
                    if video_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of video stream from {video_file}"
                    )
                    video_stream_type = "s"
                else:
                    # Skip this input file
                    video_input_idx = None
            if video_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(video_index):
                    # Handle multiple indices
                    indices = str(video_index).split(",")
                    for idx in indices:
                        if idx.strip().isdigit():
                            # Use the actual index that was determined during mapping
                            target_idx = int(idx.strip())
                            existing_video_indices = [
                                track["index"] for track in existing_tracks["video"]
                            ]

                            if target_idx >= len(existing_video_indices):
                                actual_idx = find_first_available_index(
                                    existing_video_indices
                                )

                            else:
                                actual_idx = target_idx

                            metadata_args.extend(
                                [
                                    f"-metadata:s:v:{actual_idx}",
                                    "title=Added Video Track",
                                ]
                            )
                elif str(video_index).isdigit():
                    # Insert at specific index
                    # Use the actual index that was determined during mapping
                    target_idx = int(video_index)
                    existing_video_indices = [
                        track["index"] for track in existing_tracks["video"]
                    ]

                    if target_idx >= len(existing_video_indices):
                        actual_idx = find_first_available_index(
                            existing_video_indices
                        )

                    else:
                        actual_idx = target_idx

                    metadata_args.extend(
                        [f"-metadata:s:v:{actual_idx}", "title=Added Video Track"]
                    )
                else:
                    # Append to the end - we don't know the index, so we can't add metadata
                    pass
            else:
                # Append to the end - we don't know the index, so we can't add metadata
                pass

        # Add metadata for audio tracks
        # Check if the input file has audio streams
        from bot.helper.ext_utils.media_utils import get_streams

        if audio_input_idx is not None:
            # Check if the input file has audio streams
            audio_file = (
                multi_files[1] if multi_files and len(multi_files) > 1 else file_path
            )
            audio_streams = await get_streams(audio_file)
            has_audio_stream = (
                any(stream.get("codec_type") == "audio" for stream in audio_streams)
                if audio_streams
                else False
            )

            if not has_audio_stream:
                LOGGER.warning(f"No audio streams found in input file {audio_file}")
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in audio_streams
                    )
                    if audio_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of audio stream from {audio_file}"
                    )
                    audio_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in audio_streams
                    )
                    if audio_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of audio stream from {audio_file}"
                    )
                    audio_stream_type = "s"
                else:
                    # Skip this input file
                    audio_input_idx = None
            if audio_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(audio_index):
                    # Handle multiple indices
                    indices = str(audio_index).split(",")
                    for idx in indices:
                        if idx.strip().isdigit():
                            # Use the actual index that was determined during mapping
                            target_idx = int(idx.strip())
                            existing_audio_indices = [
                                track["index"] for track in existing_tracks["audio"]
                            ]

                            if target_idx >= len(existing_audio_indices):
                                actual_idx = find_first_available_index(
                                    existing_audio_indices
                                )

                            else:
                                actual_idx = target_idx

                            metadata_args.extend(
                                [
                                    f"-metadata:s:a:{actual_idx}",
                                    "title=Added Audio Track",
                                ]
                            )
                elif str(audio_index).isdigit():
                    # Insert at specific index
                    # Use the actual index that was determined during mapping
                    target_idx = int(audio_index)
                    existing_audio_indices = [
                        track["index"] for track in existing_tracks["audio"]
                    ]

                    if target_idx >= len(existing_audio_indices):
                        actual_idx = find_first_available_index(
                            existing_audio_indices
                        )

                    else:
                        actual_idx = target_idx

                    metadata_args.extend(
                        [f"-metadata:s:a:{actual_idx}", "title=Added Audio Track"]
                    )
                else:
                    # Append to the end - we don't know the index, so we can't add metadata
                    pass
            else:
                # Append to the end - we don't know the index, so we can't add metadata
                pass

        # Add metadata for subtitle tracks
        # Check if the input file has subtitle streams
        from bot.helper.ext_utils.media_utils import get_streams

        if subtitle_input_idx is not None:
            # Check if the input file has subtitle streams
            subtitle_file = (
                multi_files[2] if multi_files and len(multi_files) > 2 else file_path
            )
            subtitle_streams = await get_streams(subtitle_file)
            has_subtitle_stream = (
                any(
                    stream.get("codec_type") == "subtitle"
                    for stream in subtitle_streams
                )
                if subtitle_streams
                else False
            )

            if not has_subtitle_stream:
                LOGGER.warning(
                    f"No subtitle streams found in input file {subtitle_file}"
                )
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in subtitle_streams
                    )
                    if subtitle_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of subtitle stream from {subtitle_file}"
                    )
                    subtitle_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in subtitle_streams
                    )
                    if subtitle_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of subtitle stream from {subtitle_file}"
                    )
                    subtitle_stream_type = "a"
                else:
                    # Skip this input file
                    subtitle_input_idx = None
            if subtitle_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(subtitle_index):
                    # Handle multiple indices
                    indices = str(subtitle_index).split(",")
                    for idx in indices:
                        if idx.strip().isdigit():
                            # Use the actual index that was determined during mapping
                            target_idx = int(idx.strip())
                            existing_subtitle_indices = [
                                track["index"]
                                for track in existing_tracks["subtitle"]
                            ]

                            if target_idx >= len(existing_subtitle_indices):
                                actual_idx = find_first_available_index(
                                    existing_subtitle_indices
                                )

                            else:
                                actual_idx = target_idx

                            metadata_args.extend(
                                [
                                    f"-metadata:s:s:{actual_idx}",
                                    "title=Added Subtitle Track",
                                ]
                            )
                elif str(subtitle_index).isdigit():
                    # Insert at specific index
                    # Use the actual index that was determined during mapping
                    target_idx = int(subtitle_index)
                    existing_subtitle_indices = [
                        track["index"] for track in existing_tracks["subtitle"]
                    ]

                    if target_idx >= len(existing_subtitle_indices):
                        actual_idx = find_first_available_index(
                            existing_subtitle_indices
                        )

                    else:
                        actual_idx = target_idx

                    metadata_args.extend(
                        [f"-metadata:s:s:{actual_idx}", "title=Added Subtitle Track"]
                    )
                else:
                    # Append to the end - we don't know the index, so we can't add metadata
                    pass
            else:
                # Append to the end - we don't know the index, so we can't add metadata
                pass

        # Add metadata for attachment tracks
        # Check if the input file has attachment streams
        from bot.helper.ext_utils.media_utils import get_streams

        if attachment_input_idx is not None:
            # Check if the input file has attachment streams
            attachment_file = (
                multi_files[3] if multi_files and len(multi_files) > 3 else file_path
            )
            attachment_streams = await get_streams(attachment_file)
            has_attachment_stream = (
                any(
                    stream.get("codec_type") == "attachment"
                    for stream in attachment_streams
                )
                if attachment_streams
                else False
            )

            if not has_attachment_stream:
                LOGGER.warning(
                    f"No attachment streams found in input file {attachment_file}"
                )
                # Use video stream instead if available
                if (
                    any(
                        stream.get("codec_type") == "video"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using video stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "v"
                elif (
                    any(
                        stream.get("codec_type") == "audio"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using audio stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "a"
                elif (
                    any(
                        stream.get("codec_type") == "subtitle"
                        for stream in attachment_streams
                    )
                    if attachment_streams
                    else False
                ):
                    LOGGER.info(
                        f"Using subtitle stream instead of attachment stream from {attachment_file}"
                    )
                    attachment_stream_type = "s"
                else:
                    # Skip this input file
                    attachment_input_idx = None
            if attachment_index is not None:
                # Check if it's a comma-separated list of indices
                if "," in str(attachment_index):
                    # Handle multiple indices
                    indices = str(attachment_index).split(",")
                    for idx in indices:
                        if idx.strip().isdigit():
                            # Use the actual index that was determined during mapping
                            target_idx = int(idx.strip())
                            existing_attachment_indices = [
                                track["index"]
                                for track in existing_tracks["attachment"]
                            ]

                            if target_idx >= len(existing_attachment_indices):
                                actual_idx = find_first_available_index(
                                    existing_attachment_indices
                                )

                            else:
                                actual_idx = target_idx

                            metadata_args.extend(
                                [
                                    f"-metadata:s:t:{actual_idx}",
                                    "title=Added Attachment",
                                ]
                            )
                elif str(attachment_index).isdigit():
                    # Insert at specific index
                    # Use the actual index that was determined during mapping
                    target_idx = int(attachment_index)
                    existing_attachment_indices = [
                        track["index"] for track in existing_tracks["attachment"]
                    ]

                    if target_idx >= len(existing_attachment_indices):
                        actual_idx = find_first_available_index(
                            existing_attachment_indices
                        )

                    else:
                        actual_idx = target_idx

                    metadata_args.extend(
                        [f"-metadata:s:t:{actual_idx}", "title=Added Attachment"]
                    )
                else:
                    # Append to the end - we don't know the index, so we can't add metadata
                    pass
            else:
                # Append to the end - we don't know the index, so we can't add metadata
                pass

    # Handle hardsub (burning subtitles into video)
    if add_subtitle and subtitle_hardsub_enabled and subtitle_input_idx is not None:
        LOGGER.info("Processing hardsub: burning subtitles into video")
        # For hardsub, we need to use video filters and re-encode the video
        # Force video codec to libx264 if it's copy (can't use copy with filters)
        if not video_codec or video_codec.lower() in ["none", "copy"]:
            codec_args.extend(["-c:v", "libx264"])
            # Add reasonable quality settings for hardsub
            codec_args.extend(["-crf", "23", "-preset", "medium"])
        else:
            codec_args.extend(["-c:v", video_codec])

        # Get subtitle file path
        subtitle_file = (
            multi_files[2] if multi_files and len(multi_files) > 2 else file_path
        )

        # Validate subtitle file for hardsub
        if multi_files and len(multi_files) > 2 and multi_files[2]:
            if not os.path.exists(subtitle_file):
                LOGGER.error(f"Subtitle file not found for hardsub: {subtitle_file}")
                raise FileNotFoundError(f"Subtitle file not found: {subtitle_file}")

            # Check subtitle format
            subtitle_ext = (
                subtitle_file.split(".")[-1].lower() if "." in subtitle_file else ""
            )
            supported_formats = [
                "srt",
                "ass",
                "ssa",
                "vtt",
                "webvtt",
                "sub",
                "sbv",
                "stl",
            ]

            if subtitle_ext not in supported_formats:
                LOGGER.warning(
                    f"Subtitle format '{subtitle_ext}' may not be fully supported for hardsub"
                )
            else:
                LOGGER.info(f"Using subtitle format for hardsub: {subtitle_ext}")

        # Build subtitle filter
        # Use subtitles filter for external subtitle files
        if multi_files and len(multi_files) > 2 and multi_files[2]:
            # External subtitle file - escape path properly for different platforms
            escaped_path = subtitle_file.replace("'", "\\'").replace(":", "\\:")
            # Handle Windows paths
            if os.name == "nt":
                escaped_path = escaped_path.replace("\\", "/")

            subtitle_filter = f"subtitles='{escaped_path}'"
            LOGGER.info(f"Using external subtitle file: {subtitle_file}")
        else:
            # Embedded subtitle stream - use stream index 0 by default
            escaped_path = file_path.replace("'", "\\'").replace(":", "\\:")
            if os.name == "nt":
                escaped_path = escaped_path.replace("\\", "/")

            subtitle_filter = f"subtitles='{escaped_path}':si=0"
            LOGGER.info(f"Using embedded subtitle stream from: {file_path}")

        # Add subtitle styling if specified
        if subtitle_font and subtitle_font.lower() != "none":
            subtitle_filter += f":force_style='FontName={subtitle_font}"
            if subtitle_font_size and subtitle_font_size.lower() != "none":
                subtitle_filter += f",FontSize={subtitle_font_size}"
            # Add additional styling for better appearance
            subtitle_filter += ",Outline=1,Shadow=1"
            subtitle_filter += "'"
            LOGGER.info(
                f"Applied custom font styling: {subtitle_font}, size {subtitle_font_size}"
            )
        elif subtitle_font_size and subtitle_font_size.lower() != "none":
            subtitle_filter += (
                f":force_style='FontSize={subtitle_font_size},Outline=1,Shadow=1'"
            )
            LOGGER.info(f"Applied custom font size: {subtitle_font_size}")

        # Add video filter
        codec_args.extend(["-vf", subtitle_filter])

        # Add container-specific optimizations
        output_ext = temp_file.split(".")[-1].lower() if "." in temp_file else "mp4"

        if output_ext in ["mp4", "mov", "m4v"]:
            # MP4/MOV optimizations for better streaming (especially Telegram)
            codec_args.extend(["-movflags", "+faststart"])
            codec_args.extend(["-pix_fmt", "yuv420p"])  # Ensure compatibility
            LOGGER.info("Applied MP4 streaming optimizations")
        elif output_ext == "webm":
            # WebM optimizations
            codec_args.extend(["-deadline", "good"])  # Better quality/speed balance
        elif output_ext == "mkv":
            # MKV optimizations
            codec_args.extend(
                ["-avoid_negative_ts", "make_zero"]
            )  # Fix timestamp issues

    elif (
        (add_video or multi_files)
        and video_codec
        and video_codec.lower() != "none"
        and video_codec.lower() != "copy"
    ):
        codec_args.extend(["-c:v", video_codec])

        # Add video quality settings if specified
        if video_quality and video_quality.lower() != "none":
            try:
                quality_val = int(video_quality)
                if video_codec in ["libx264", "libx265"]:
                    codec_args.extend(["-crf", str(quality_val)])
                elif video_codec in ["libvpx", "libvpx-vp9"]:
                    codec_args.extend(["-crf", str(quality_val), "-b:v", "0"])
            except (ValueError, TypeError):
                pass

        # Add video preset if specified
        if video_preset and video_preset.lower() != "none":
            if video_codec in ["libx264", "libx265"]:
                codec_args.extend(["-preset", video_preset])

        # Add video bitrate if specified
        if video_bitrate and video_bitrate.lower() != "none":
            codec_args.extend(["-b:v", video_bitrate])

        # Add video resolution if specified
        if video_resolution and video_resolution.lower() != "none":
            codec_args.extend(["-s", video_resolution])

        # Add video frame rate if specified
        if video_fps and video_fps.lower() != "none":
            codec_args.extend(["-r", video_fps])

    if (
        (add_audio or multi_files)
        and audio_codec
        and audio_codec.lower() != "none"
        and audio_codec.lower() != "copy"
    ):
        codec_args.extend(["-c:a", audio_codec])

        # Add audio bitrate if specified
        if audio_bitrate and audio_bitrate.lower() != "none":
            codec_args.extend(["-b:a", audio_bitrate])

        # Add audio channels if specified
        if audio_channels and audio_channels.lower() != "none":
            codec_args.extend(["-ac", audio_channels])

        # Add audio sampling rate if specified
        if audio_sampling and audio_sampling.lower() != "none":
            codec_args.extend(["-ar", audio_sampling])

        # Add audio volume if specified
        if audio_volume and audio_volume.lower() != "none":
            # Use volume filter
            codec_args.extend(["-af", f"volume={audio_volume}"])

    # Handle subtitle codec settings (only for soft subtitles, not hardsub)
    if (
        (add_subtitle or multi_files)
        and subtitle_codec
        and subtitle_codec.lower() != "none"
        and not subtitle_hardsub_enabled  # Don't apply subtitle codec for hardsub
    ):
        if subtitle_codec.lower() == "copy":
            # Smart codec selection based on container and subtitle format
            output_ext = temp_file.split(".")[-1].lower() if "." in temp_file else ""

            # Check if we have external subtitle file
            if multi_files and len(multi_files) > 2 and multi_files[2]:
                subtitle_ext = (
                    multi_files[2].split(".")[-1].lower()
                    if "." in multi_files[2]
                    else ""
                )

                # Container-specific codec selection for better compatibility
                if output_ext in ["mp4", "mov", "m4v"]:
                    # MP4/MOV containers: use mov_text for text-based subtitles
                    if subtitle_ext in ["srt", "vtt", "webvtt", "sub"]:
                        codec_args.extend(["-c:s", "mov_text"])
                        LOGGER.info(
                            f"Converting {subtitle_ext.upper()} to mov_text for MP4/MOV compatibility"
                        )
                    elif subtitle_ext in ["ass", "ssa"]:
                        # ASS/SSA can be copied in MP4 if supported
                        codec_args.extend(["-c:s", "copy"])
                    else:
                        codec_args.extend(
                            ["-c:s", "mov_text"]
                        )  # Fallback to mov_text
                        LOGGER.info(
                            "Using mov_text fallback for MP4/MOV compatibility"
                        )
                elif output_ext == "avi":
                    # AVI container: very limited subtitle support
                    LOGGER.warning(
                        "AVI container has very limited subtitle support."
                    )
                    LOGGER.info(
                        "Recommendation: Use MKV container or enable hardsub for better subtitle support."
                    )

                    # Try to use a compatible format, but expect potential issues
                    if subtitle_ext in ["srt"]:
                        # Try SRT codec, but it may still fail
                        codec_args.extend(["-c:s", "srt"])
                        LOGGER.info("Attempting SRT codec for AVI (may fail)")
                    else:
                        # For non-SRT, recommend hardsub
                        LOGGER.warning(
                            f"Subtitle format '{subtitle_ext}' not recommended for AVI."
                        )
                        LOGGER.info(
                            "Consider enabling hardsub or using MKV container instead."
                        )
                        # Skip subtitle for AVI with incompatible formats
                        return None
                elif output_ext in ["mkv", "webm"]:
                    # MKV/WebM: excellent subtitle support, use copy
                    codec_args.extend(["-c:s", "copy"])
                elif output_ext in ["3gp", "flv"]:
                    # Limited containers: use mov_text if possible
                    codec_args.extend(["-c:s", "mov_text"])
                    LOGGER.info(
                        f"Using mov_text codec for {output_ext.upper()} compatibility"
                    )
                else:
                    # Default: try copy first
                    codec_args.extend(["-c:s", "copy"])
            else:
                codec_args.extend(["-c:s", "copy"])
        else:
            # Use specified codec
            codec_args.extend(["-c:s", subtitle_codec])

        # Add subtitle language if specified
        if subtitle_language and subtitle_language.lower() != "none":
            codec_args.extend(["-metadata:s:s", f"language={subtitle_language}"])

        # Add subtitle encoding if specified
        if subtitle_encoding and subtitle_encoding.lower() != "none":
            codec_args.extend(["-sub_charenc", subtitle_encoding])

        # Add subtitle font if specified (only for certain codecs)
        if subtitle_font and subtitle_font.lower() != "none":
            codec_args.extend(["-sub_font", subtitle_font])

        # Add subtitle font size if specified (only for certain codecs)
        if subtitle_font_size and subtitle_font_size.lower() != "none":
            codec_args.extend(["-sub_font_size", subtitle_font_size])

    # Add attachment MIME type if specified
    if (
        (add_attachment or multi_files)
        and attachment_mimetype
        and attachment_mimetype.lower() != "none"
    ):
        codec_args.extend(["-metadata:s:t", f"mimetype={attachment_mimetype}"])

    # Add the codec arguments to the command
    cmd.extend(codec_args)

    # Add the metadata arguments to the command
    cmd.extend(metadata_args)

    # Add threads parameter
    cmd.extend(["-threads", f"{max(1, cpu_no // 2)}"])

    # Add output file
    cmd.append(temp_file)

    # Output file format logging removed for cleaner output

    # Add -del flag if delete_original is True
    if delete_original:
        cmd.append("-del")

    # Note: preserve_tracks and replace_tracks are internal flags used for mapping logic
    # They should NOT be passed as command line arguments to FFmpeg
    # The preserve/replace behavior is already handled in the mapping logic above

    return cmd, temp_file


async def get_remove_cmd(
    file_path,
    remove_video=False,
    remove_audio=False,
    remove_subtitle=False,
    remove_attachment=False,
    remove_metadata=False,
    video_index=None,
    audio_index=None,
    subtitle_index=None,
    attachment_index=None,
    video_codec="none",
    audio_codec="none",
    subtitle_codec="none",
    video_format="none",
    audio_format="none",
    subtitle_format="none",
    attachment_format="none",
    video_quality="none",
    video_preset="none",
    video_bitrate="none",
    video_resolution="none",
    video_fps="none",
    audio_bitrate="none",
    audio_channels="none",
    audio_sampling="none",
    audio_volume="none",
    subtitle_language="none",
    subtitle_encoding="none",
    subtitle_font="none",
    subtitle_font_size="none",
    attachment_filter="none",
    maintain_quality=True,
    delete_original=False,
):
    """Generate FFmpeg command for removing tracks from a media file.

    Args:
        file_path: Path to the input media file
        remove_video: Whether to remove video tracks
        remove_audio: Whether to remove audio tracks
        remove_subtitle: Whether to remove subtitle tracks
        remove_attachment: Whether to remove attachments
        remove_metadata: Whether to remove metadata
        video_index: Video track index to remove (None for all)
        audio_index: Audio track index to remove (None for all)
        subtitle_index: Subtitle track index to remove (None for all)
        attachment_index: Attachment index to remove (None for all)
        video_codec: Video codec for remaining tracks
        audio_codec: Audio codec for remaining tracks
        subtitle_codec: Subtitle codec for remaining tracks
        video_format: Video output format
        audio_format: Audio output format
        subtitle_format: Subtitle output format
        attachment_format: Attachment output format
        video_quality: Video quality setting
        video_preset: Video encoding preset
        video_bitrate: Video bitrate
        video_resolution: Video resolution
        video_fps: Video frame rate
        audio_bitrate: Audio bitrate
        audio_channels: Audio channel count
        audio_sampling: Audio sampling rate
        audio_volume: Audio volume adjustment
        subtitle_language: Subtitle language
        subtitle_encoding: Subtitle encoding
        subtitle_font: Subtitle font
        subtitle_font_size: Subtitle font size
        attachment_filter: Attachment filter pattern
        maintain_quality: Whether to maintain quality
        delete_original: Whether to delete original file

    Returns:
        tuple: FFmpeg command and output file path
    """
    import os

    from bot.core.config_manager import Config
    from bot.helper.ext_utils.media_utils import get_streams

    # Check if any removal is enabled
    if not (
        remove_video
        or remove_audio
        or remove_subtitle
        or remove_attachment
        or remove_metadata
    ):
        return None, None

    # Validate input file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")

    # Get stream information for validation
    try:
        streams = await get_streams(file_path)
        if not streams:
            # If we can't get stream info, proceed anyway but log warning
            from bot import LOGGER

            LOGGER.warning(
                f"Could not get stream information for {file_path}, proceeding anyway"
            )
            streams = []
    except Exception as e:
        from bot import LOGGER

        LOGGER.warning(
            f"Error getting stream info for {file_path}: {e}, proceeding anyway"
        )
        streams = []

    # Categorize streams for validation
    video_streams = []
    audio_streams = []
    subtitle_streams = []
    attachment_streams = []

    for i, stream in enumerate(streams):
        codec_type = stream.get("codec_type", "unknown")
        if codec_type == "video":
            video_streams.append(i)
        elif codec_type == "audio":
            audio_streams.append(i)
        elif codec_type == "subtitle":
            subtitle_streams.append(i)
        elif codec_type == "attachment":
            attachment_streams.append(i)

    # Validate removal requests against available streams and prevent empty outputs
    if remove_video and video_index is not None and streams:
        # Parse video indices and validate
        if isinstance(video_index, str):
            try:
                video_indices = [
                    int(x.strip())
                    for x in video_index.split(",")
                    if x.strip().isdigit()
                ]
                # Check if requested indices exist
                for idx in video_indices:
                    if idx not in video_streams:
                        from bot import LOGGER

                        LOGGER.warning(
                            f"Video stream index {idx} not found in {file_path}"
                        )
            except ValueError:
                from bot import LOGGER

                LOGGER.warning(f"Invalid video index format: {video_index}")

    if remove_audio and audio_index is not None and streams:
        # Parse audio indices and validate
        if isinstance(audio_index, str):
            try:
                audio_indices = [
                    int(x.strip())
                    for x in audio_index.split(",")
                    if x.strip().isdigit()
                ]
                # Check if requested indices exist
                for idx in audio_indices:
                    if idx not in audio_streams:
                        from bot import LOGGER

                        LOGGER.warning(
                            f"Audio stream index {idx} not found in {file_path}"
                        )
            except ValueError:
                from bot import LOGGER

                LOGGER.warning(f"Invalid audio index format: {audio_index}")

    # Prevent creating empty output files
    remaining_streams = 0

    # Count remaining video streams
    if not remove_video:
        remaining_streams += len(video_streams)
    elif video_index is not None and isinstance(video_index, str):
        # Partial video removal
        try:
            video_indices = [
                int(x.strip()) for x in video_index.split(",") if x.strip().isdigit()
            ]
            remaining_streams += len(video_streams) - len(video_indices)
        except ValueError:
            remaining_streams += len(video_streams)

    # Count remaining audio streams
    if not remove_audio:
        remaining_streams += len(audio_streams)
    elif audio_index is not None and isinstance(audio_index, str):
        # Partial audio removal
        try:
            audio_indices = [
                int(x.strip()) for x in audio_index.split(",") if x.strip().isdigit()
            ]
            remaining_streams += len(audio_streams) - len(audio_indices)
        except ValueError:
            remaining_streams += len(audio_streams)

    # Count remaining subtitle streams
    if not remove_subtitle:
        remaining_streams += len(subtitle_streams)
    elif subtitle_index is not None and isinstance(subtitle_index, str):
        try:
            subtitle_indices = [
                int(x.strip())
                for x in subtitle_index.split(",")
                if x.strip().isdigit()
            ]
            remaining_streams += len(subtitle_streams) - len(subtitle_indices)
        except ValueError:
            remaining_streams += len(subtitle_streams)

    # Count remaining attachment streams
    if not remove_attachment:
        remaining_streams += len(attachment_streams)
    elif attachment_index is not None and isinstance(attachment_index, str):
        try:
            attachment_indices = [
                int(x.strip())
                for x in attachment_index.split(",")
                if x.strip().isdigit()
            ]
            remaining_streams += len(attachment_streams) - len(attachment_indices)
        except ValueError:
            remaining_streams += len(attachment_streams)

    # If no streams would remain, return error
    if remaining_streams == 0 and not remove_metadata:
        from bot import LOGGER

        LOGGER.error(
            f"Cannot remove all streams from {file_path} - would result in empty file"
        )
        return None, None
    if remaining_streams == 0 and remove_metadata:
        # Special case: only metadata removal on a file that would have no streams
        # This is not a valid operation for most containers
        from bot import LOGGER

        LOGGER.warning(
            f"Metadata-only removal on file with no remaining streams: {file_path}"
        )
        return None, None

    # Get file info
    file_name = os.path.basename(file_path)
    _name, ext = os.path.splitext(file_name)

    # Determine output format based on settings and content
    output_ext = ext

    # Smart format selection based on what's being removed and what remains
    if video_format != "none":
        output_ext = f".{video_format}"
    elif audio_format != "none":
        output_ext = f".{audio_format}"
    elif subtitle_format != "none":
        output_ext = f".{subtitle_format}"
    elif attachment_format != "none":
        output_ext = f".{attachment_format}"
    # Smart format selection based on remaining content
    elif remove_video and not remove_audio and audio_streams:
        # Only audio remains, use audio-friendly format
        if ext.lower() in [".mkv", ".mp4", ".avi"]:
            output_ext = ".m4a" if ext.lower() == ".mp4" else ".mka"
    elif remove_audio and not remove_video and video_streams:
        # Only video remains, keep video format
        if ext.lower() in [".m4a", ".mp3", ".flac"]:
            output_ext = ".mp4"  # Convert audio-only to video container
        # For other cases, keep original extension

    # Generate output file path with descriptive naming
    operation_desc = []
    if remove_video:
        if video_index:
            operation_desc.append(f"rv{video_index}")
        else:
            operation_desc.append("rv")
    if remove_audio:
        if audio_index:
            operation_desc.append(f"ra{audio_index}")
        else:
            operation_desc.append("ra")
    if remove_subtitle:
        if subtitle_index:
            operation_desc.append(f"rs{subtitle_index}")
        else:
            operation_desc.append("rs")
    if remove_attachment:
        if attachment_index:
            operation_desc.append(f"rt{attachment_index}")
        else:
            operation_desc.append("rt")
    if remove_metadata:
        operation_desc.append("rm")

    operation_suffix = "_".join(operation_desc) if operation_desc else "removed"
    temp_file = f"{file_path.rsplit('.', 1)[0]}_{operation_suffix}{output_ext}"

    # Ensure output file doesn't overwrite input
    if temp_file == file_path:
        temp_file = f"{file_path.rsplit('.', 1)[0]}_processed{output_ext}"

    # Start building FFmpeg command
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file_path,
        "-y",  # Overwrite output files
    ]

    # Build mapping arguments to exclude specified tracks
    map_args = []
    codec_args = []

    # If removing specific tracks by index
    if remove_video and video_index is not None:
        # Parse video indices (can be comma-separated)
        if isinstance(video_index, str):
            video_indices = [
                int(x.strip()) for x in video_index.split(",") if x.strip().isdigit()
            ]
        else:
            video_indices = [int(video_index)]

        # Map all streams first, then exclude specific video tracks
        map_args.extend(["-map", "0"])
        for idx in video_indices:
            map_args.extend(["-map", f"-0:v:{idx}"])
    elif remove_video:
        # Remove all video tracks
        map_args.extend(["-map", "0", "-map", "-0:v"])

    if remove_audio and audio_index is not None:
        # Parse audio indices
        if isinstance(audio_index, str):
            audio_indices = [
                int(x.strip()) for x in audio_index.split(",") if x.strip().isdigit()
            ]
        else:
            audio_indices = [int(audio_index)]

        if not map_args:
            map_args.extend(["-map", "0"])
        for idx in audio_indices:
            map_args.extend(["-map", f"-0:a:{idx}"])
    elif remove_audio:
        # Remove all audio tracks
        if not map_args:
            map_args.extend(["-map", "0"])
        map_args.extend(["-map", "-0:a"])

    if remove_subtitle and subtitle_index is not None:
        # Parse subtitle indices
        if isinstance(subtitle_index, str):
            subtitle_indices = [
                int(x.strip())
                for x in subtitle_index.split(",")
                if x.strip().isdigit()
            ]
        else:
            subtitle_indices = [int(subtitle_index)]

        if not map_args:
            map_args.extend(["-map", "0"])
        for idx in subtitle_indices:
            map_args.extend(["-map", f"-0:s:{idx}"])
    elif remove_subtitle:
        # Remove all subtitle tracks
        if not map_args:
            map_args.extend(["-map", "0"])
        map_args.extend(["-map", "-0:s"])

    if remove_attachment and attachment_index is not None:
        # Parse attachment indices
        if isinstance(attachment_index, str):
            attachment_indices = [
                int(x.strip())
                for x in attachment_index.split(",")
                if x.strip().isdigit()
            ]
        else:
            attachment_indices = [int(attachment_index)]

        if not map_args:
            map_args.extend(["-map", "0"])
        for idx in attachment_indices:
            map_args.extend(["-map", f"-0:t:{idx}"])
    elif remove_attachment:
        # Remove all attachments
        if not map_args:
            map_args.extend(["-map", "0"])
        map_args.extend(["-map", "-0:t"])

    # If no specific mapping was done, map all streams
    if not map_args:
        map_args.extend(["-map", "0"])

    # Add mapping arguments to command
    cmd.extend(map_args)

    # Add codec settings for remaining tracks with smart defaults
    if not remove_video and video_streams:
        if video_codec != "none":
            codec_args.extend(["-c:v", video_codec])
        else:
            # Use copy by default to maintain quality
            codec_args.extend(["-c:v", "copy"])

        # Add video quality settings only if not using copy codec
        if video_codec not in ["none", "copy"]:
            if video_quality != "none":
                if video_quality in ["high", "medium", "low"]:
                    quality_map = {"high": "18", "medium": "23", "low": "28"}
                    codec_args.extend(["-crf", quality_map[video_quality]])
                else:
                    codec_args.extend(["-crf", str(video_quality)])

            if video_preset != "none":
                codec_args.extend(["-preset", video_preset])

            if video_bitrate != "none":
                codec_args.extend(["-b:v", video_bitrate])

            if video_resolution != "none":
                codec_args.extend(["-s", video_resolution])

            if video_fps != "none":
                codec_args.extend(["-r", str(video_fps)])

    if not remove_audio and audio_streams:
        if audio_codec != "none":
            codec_args.extend(["-c:a", audio_codec])
        else:
            # Use copy by default to maintain quality
            codec_args.extend(["-c:a", "copy"])

        # Add audio quality settings only if not using copy codec
        if audio_codec not in ["none", "copy"]:
            if audio_bitrate != "none":
                codec_args.extend(["-b:a", audio_bitrate])

            if audio_channels != "none":
                codec_args.extend(["-ac", str(audio_channels)])

            if audio_sampling != "none":
                codec_args.extend(["-ar", str(audio_sampling)])

        # Audio volume can be applied even with copy codec
        if audio_volume not in {"none", "1.0"}:
            codec_args.extend(["-af", f"volume={audio_volume}"])

    if not remove_subtitle and subtitle_streams:
        if subtitle_codec != "none":
            codec_args.extend(["-c:s", subtitle_codec])
        else:
            # Use copy by default
            codec_args.extend(["-c:s", "copy"])

        # Add subtitle settings only if not using copy codec
        if subtitle_codec not in ["none", "copy"]:
            if subtitle_encoding != "none":
                codec_args.extend(["-sub_charenc", subtitle_encoding])

            if subtitle_language != "none":
                codec_args.extend(
                    ["-metadata:s:s:0", f"language={subtitle_language}"]
                )

    # Remove metadata if requested
    if remove_metadata:
        codec_args.extend(["-map_metadata", "-1"])

    # Add codec arguments to command
    cmd.extend(codec_args)

    # Add thread count for better performance
    thread_count = max(1, getattr(Config, "CPU_COUNT", 2) // 2)
    cmd.extend(["-threads", str(thread_count)])

    # Add output file
    cmd.append(temp_file)

    # Add delete original flag if requested
    if delete_original:
        cmd.append("-del")

    return cmd, temp_file


async def get_extract_cmd(
    file_path,
    extract_video=False,
    extract_audio=False,
    extract_subtitle=False,
    extract_attachment=False,
    video_index=None,
    audio_index=None,
    subtitle_index=None,
    attachment_index=None,
    video_codec="copy",
    audio_codec="copy",
    subtitle_codec="copy",
    maintain_quality=True,
):
    """Generate FFmpeg command for extracting tracks from a media file.

    Args:
        file_path: Path to the input file
        extract_video: Whether to extract video tracks
        extract_audio: Whether to extract audio tracks
        extract_subtitle: Whether to extract subtitle tracks
        extract_attachment: Whether to extract attachments
        video_index: Specific video track index to extract (None for all)
        audio_index: Specific audio track index to extract (None for all)
        subtitle_index: Specific subtitle track index to extract (None for all)
        attachment_index: Specific attachment index to extract (None for all)
        video_codec: Codec to use for video extraction
        audio_codec: Codec to use for audio extraction
        subtitle_codec: Codec to use for subtitle extraction
        maintain_quality: Whether to maintain high quality during extraction

    Returns:
        Tuple containing the FFmpeg command and the temporary output file path
    """
    # Check if file exists
    if not os.path.exists(file_path):
        LOGGER.error(f"File not found for extraction: {file_path}")
        return [], ""

    # Get file information
    file_name = os.path.basename(file_path)
    file_dir = os.path.dirname(file_path)
    file_base, file_ext = os.path.splitext(file_name)

    # Create a temporary output file path
    temp_file = os.path.join(file_dir, f"{file_base}.extract.temp{file_ext}")

    # Check if any extraction option is enabled
    if not (
        extract_video or extract_audio or extract_subtitle or extract_attachment
    ):
        return [], temp_file

    # Get track information
    streams = await get_streams(file_path)
    if not streams:
        LOGGER.error(f"Failed to get stream information for {file_path}")
        return [], temp_file

    # Group streams by type
    video_streams = []
    audio_streams = []
    subtitle_streams = []
    attachment_streams = []

    for i, stream in enumerate(streams):
        stream_type = stream.get("codec_type")
        if stream_type == "video":
            video_streams.append((i, stream))
        elif stream_type == "audio":
            audio_streams.append((i, stream))
        elif stream_type == "subtitle":
            subtitle_streams.append((i, stream))
        elif stream_type == "attachment":
            attachment_streams.append((i, stream))

    # Check if we have any streams to extract
    if (
        (extract_video and not video_streams)
        and (extract_audio and not audio_streams)
        and (extract_subtitle and not subtitle_streams)
        and (extract_attachment and not attachment_streams)
    ):
        LOGGER.error(f"No streams found to extract from {file_path}")
        return [], temp_file

    # Handle attachment extraction separately
    if extract_attachment and attachment_streams:
        # For attachments, we need to use a different approach
        if attachment_index is not None:
            # Extract specific attachment
            try:
                attachment_index = int(attachment_index)
                if 0 <= attachment_index < len(attachment_streams):
                    stream_index, stream = attachment_streams[attachment_index]
                    filename = stream.get("tags", {}).get(
                        "filename", f"attachment_{attachment_index}"
                    )
                    output_path = os.path.join(file_dir, filename)
                    return [
                        "EXTRACT_ATTACHMENTS_ONLY",
                        file_path,
                        f"EXTRACT_ATTACHMENT:{stream_index}:{output_path}",
                    ], temp_file
            except ValueError:
                LOGGER.error(f"Invalid attachment index: {attachment_index}")
        else:
            # Extract all attachments
            commands = ["EXTRACT_ATTACHMENTS_ONLY", file_path]
            for i, (stream_index, stream) in enumerate(attachment_streams):
                filename = stream.get("tags", {}).get("filename", f"attachment_{i}")
                output_path = os.path.join(file_dir, filename)
                commands.append(f"EXTRACT_ATTACHMENT:{stream_index}:{output_path}")
            return commands, temp_file

    # For media tracks, we'll use multiple FFmpeg commands if needed
    commands = []

    # Extract video streams
    if extract_video and video_streams:
        if video_index is not None:
            # Extract specific video track by index
            try:
                video_index = int(video_index)
                if 0 <= video_index < len(video_streams):
                    stream_index, stream = video_streams[video_index]
                    codec_name = stream.get("codec_name", "unknown")
                    # We don't need width and height for extraction
                    # but we could use them for logging or future enhancements

                    # Determine output extension based on codec
                    output_ext = (
                        "mp4" if video_codec in ["h264", "libx264"] else "mkv"
                    )
                    output_file = os.path.join(
                        file_dir,
                        f"{file_base}.video.{stream.get('tags', {}).get('language', 'und')}.{stream_index}.{output_ext}",
                    )

                    cmd = [
                        "xtra",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        file_path,
                        "-map",
                        f"0:{stream_index}",
                        "-c:v",
                        video_codec,
                        "-y",  # Always overwrite output files
                    ]

                    # Add quality settings if not using copy codec
                    if video_codec != "copy" and maintain_quality:
                        if video_codec in ["h264", "libx264"]:
                            cmd.extend(["-crf", "18", "-preset", "slow"])
                        elif video_codec in ["h265", "libx265"]:
                            cmd.extend(["-crf", "22", "-preset", "slow"])
                        elif video_codec in ["vp9", "libvpx-vp9"]:
                            cmd.extend(["-crf", "30", "-b:v", "0"])

                    # Add format-specific optimizations for Telegram compatibility
                    if output_ext == "mp4":
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
                    elif output_ext == "mkv":
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
                    elif output_ext == "webm":
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
                    elif output_ext == "mov":
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

                    cmd.append(output_file)
                    commands.append(" ".join(cmd))
                else:
                    pass
            except ValueError:
                LOGGER.error(f"Invalid video index: {video_index}")
        else:
            # Extract all video tracks
            for i, (stream_index, stream) in enumerate(video_streams):
                # Skip attached pictures (cover art)
                if stream.get("disposition", {}).get("attached_pic", 0) == 1:
                    continue

                # Determine output extension based on codec
                output_ext = "mp4" if video_codec in ["h264", "libx264"] else "mkv"
                output_file = os.path.join(
                    file_dir,
                    f"{file_base}.video.{stream.get('tags', {}).get('language', 'und')}.{stream_index}.{output_ext}",
                )

                cmd = [
                    "xtra",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    file_path,
                    "-map",
                    f"0:{stream_index}",
                    "-c:v",
                    video_codec,
                    "-y",  # Always overwrite output files
                ]

                # Add quality settings if not using copy codec
                if video_codec != "copy" and maintain_quality:
                    if video_codec in ["h264", "libx264"]:
                        cmd.extend(["-crf", "18", "-preset", "slow"])
                    elif video_codec in ["h265", "libx265"]:
                        cmd.extend(["-crf", "22", "-preset", "slow"])
                    elif video_codec in ["vp9", "libvpx-vp9"]:
                        cmd.extend(["-crf", "30", "-b:v", "0"])

                # Add format-specific optimizations for Telegram compatibility
                if output_ext == "mp4":
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
                elif output_ext == "mkv":
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
                elif output_ext == "webm":
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
                elif output_ext == "mov":
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

                cmd.append(output_file)
                commands.append(" ".join(cmd))

    # Extract audio streams
    if extract_audio and audio_streams:
        if audio_index is not None:
            # Extract specific audio track by indexbut by default all the configs should be none and none means none and those configs should not be used for command generation. global settings will use that settings by default
            try:
                audio_index = int(audio_index)
                if 0 <= audio_index < len(audio_streams):
                    stream_index, stream = audio_streams[audio_index]
                    codec_name = stream.get("codec_name", "unknown")

                    # Determine output extension based on codec
                    if audio_codec == "copy":
                        # When using copy, use a proper extension based on the input codec
                        input_codec = codec_name.lower()
                        if input_codec in ["aac", "libfdk_aac"]:
                            output_ext = "m4a"
                        elif input_codec in ["mp3", "libmp3lame"]:
                            output_ext = "mp3"
                        elif input_codec in ["opus", "libopus"]:
                            output_ext = "opus"
                        elif input_codec in ["flac", "libflac"]:
                            output_ext = "flac"
                        elif input_codec in ["vorbis", "libvorbis"]:
                            output_ext = "ogg"
                        elif input_codec in ["pcm_s16le", "pcm_s24le", "pcm_f32le"]:
                            output_ext = "wav"
                        else:
                            # Default to Matroska Audio for other codecs
                            output_ext = "mka"
                    # For non-copy codecs, use appropriate extension
                    elif audio_codec in ["aac", "libfdk_aac"]:
                        output_ext = "m4a"
                    elif audio_codec in ["mp3", "libmp3lame"]:
                        output_ext = "mp3"
                    elif audio_codec in ["opus", "libopus"]:
                        output_ext = "opus"
                    elif audio_codec in ["flac", "libflac"]:
                        output_ext = "flac"
                    elif audio_codec in ["vorbis", "libvorbis"]:
                        output_ext = "ogg"
                    else:
                        # Default to Matroska Audio for other codecs
                        output_ext = "mka"

                    output_file = os.path.join(
                        file_dir,
                        f"{file_base}.audio.{stream.get('tags', {}).get('language', 'und')}.{stream_index}.{output_ext}",
                    )

                    cmd = [
                        "xtra",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        file_path,
                        "-map",
                        f"0:{stream_index}",
                        "-c:a",
                        audio_codec,
                        "-y",  # Always overwrite output files
                    ]

                    # Add quality settings if not using copy codec
                    if audio_codec != "copy" and maintain_quality:
                        if (
                            audio_codec in ["aac", "libfdk_aac"]
                            or audio_codec == "mp3"
                        ):
                            cmd.extend(["-b:a", "320k"])
                        elif audio_codec in ["opus", "libopus"]:
                            cmd.extend(["-b:a", "192k"])
                        elif audio_codec in ["flac", "libflac"]:
                            cmd.extend(["-compression_level", "8"])

                    cmd.append(output_file)
                    commands.append(" ".join(cmd))
                else:
                    pass
            except ValueError:
                LOGGER.error(f"Invalid audio index: {audio_index}")
        else:
            # Extract all audio tracks
            for i, (stream_index, stream) in enumerate(audio_streams):
                # Determine output extension based on codec
                codec_name = stream.get("codec_name", "unknown")
                if audio_codec == "copy":
                    # When using copy, use a proper extension based on the input codec
                    input_codec = codec_name.lower()
                    if input_codec in ["aac", "libfdk_aac"]:
                        output_ext = "m4a"
                    elif input_codec in ["mp3", "libmp3lame"]:
                        output_ext = "mp3"
                    elif input_codec in ["opus", "libopus"]:
                        output_ext = "opus"
                    elif input_codec in ["flac", "libflac"]:
                        output_ext = "flac"
                    elif input_codec in ["vorbis", "libvorbis"]:
                        output_ext = "ogg"
                    elif input_codec in ["pcm_s16le", "pcm_s24le", "pcm_f32le"]:
                        output_ext = "wav"
                    else:
                        # Default to Matroska Audio for other codecs
                        output_ext = "mka"
                elif audio_codec in ["aac", "libfdk_aac"]:
                    output_ext = "m4a"
                elif audio_codec in ["mp3", "libmp3lame"]:
                    output_ext = "mp3"
                elif audio_codec in ["opus", "libopus"]:
                    output_ext = "opus"
                elif audio_codec in ["flac", "libflac"]:
                    output_ext = "flac"
                elif audio_codec in ["vorbis", "libvorbis"]:
                    output_ext = "ogg"
                else:
                    # Default to Matroska Audio for other codecs
                    output_ext = "mka"

                output_file = os.path.join(
                    file_dir,
                    f"{file_base}.audio.{stream.get('tags', {}).get('language', 'und')}.{stream_index}.{output_ext}",
                )

                cmd = [
                    "xtra",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    file_path,
                    "-map",
                    f"0:{stream_index}",
                    "-c:a",
                    audio_codec,
                    "-y",  # Always overwrite output files
                ]

                # Add quality settings if not using copy codec
                if audio_codec != "copy" and maintain_quality:
                    if audio_codec in ["aac", "libfdk_aac"] or audio_codec == "mp3":
                        cmd.extend(["-b:a", "320k"])
                    elif audio_codec in ["opus", "libopus"]:
                        cmd.extend(["-b:a", "192k"])
                    elif audio_codec in ["flac", "libflac"]:
                        cmd.extend(["-compression_level", "8"])

                cmd.append(output_file)
                commands.append(" ".join(cmd))

    # Extract subtitle streams
    if extract_subtitle and subtitle_streams:
        if subtitle_index is not None:
            # Extract specific subtitle track by index
            try:
                subtitle_index = int(subtitle_index)
                if 0 <= subtitle_index < len(subtitle_streams):
                    stream_index, stream = subtitle_streams[subtitle_index]
                    codec_name = stream.get("codec_name", "unknown")

                    # Determine output extension based on codec
                    if codec_name in ["subrip", "srt"]:
                        output_ext = "srt"
                    elif codec_name in ["ass", "ssa"]:
                        output_ext = "ass"
                    elif codec_name in ["webvtt", "vtt"]:
                        output_ext = "vtt"
                    else:
                        output_ext = "srt"  # Default format

                    output_file = os.path.join(
                        file_dir,
                        f"{file_base}.subtitle.{stream.get('tags', {}).get('language', 'und')}.{stream_index}.{output_ext}",
                    )

                    cmd = [
                        "xtra",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        file_path,
                        "-map",
                        f"0:{stream_index}",
                        "-c:s",
                        subtitle_codec,
                        "-y",  # Always overwrite output files
                    ]
                    cmd.append(output_file)
                    commands.append(" ".join(cmd))
                else:
                    pass
            except ValueError:
                LOGGER.error(f"Invalid subtitle index: {subtitle_index}")
        else:
            # Extract all subtitle tracks
            for i, (stream_index, stream) in enumerate(subtitle_streams):
                codec_name = stream.get("codec_name", "unknown")

                # Determine output extension based on codec
                if codec_name in ["subrip", "srt"]:
                    output_ext = "srt"
                elif codec_name in ["ass", "ssa"]:
                    output_ext = "ass"
                elif codec_name in ["webvtt", "vtt"]:
                    output_ext = "vtt"
                else:
                    output_ext = "srt"  # Default format

                output_file = os.path.join(
                    file_dir,
                    f"{file_base}.subtitle.{stream.get('tags', {}).get('language', 'und')}.{stream_index}.{output_ext}",
                )

                cmd = [
                    "xtra",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    file_path,
                    "-map",
                    f"0:{stream_index}",
                    "-c:s",
                    subtitle_codec,
                    "-y",  # Always overwrite output files
                ]
                cmd.append(output_file)
                commands.append(" ".join(cmd))

    # Return the commands
    if len(commands) == 1:
        # If there's only one command, return it directly
        return commands[0].split(), temp_file
    if len(commands) > 1:
        # If there are multiple commands, return them as a special format
        return ["EXTRACT_MULTI_COMMAND", *commands], temp_file
    # No commands were generated
    return [], temp_file


async def get_swap_cmd(
    file_path,
    swap_audio=False,
    swap_video=False,
    swap_subtitle=False,
    audio_use_language=True,
    video_use_language=True,
    subtitle_use_language=True,
    audio_language_order="eng,hin",
    video_language_order="eng,hin",
    subtitle_language_order="eng,hin",
    audio_index_order="0,1",
    video_index_order="0,1",
    subtitle_index_order="0,1",
    delete_original=False,
):
    """Generate FFmpeg command for swapping audio/video/subtitle tracks.

    Args:
        file_path: Path to the input file
        swap_audio: Whether to swap audio tracks
        swap_video: Whether to swap video tracks
        swap_subtitle: Whether to swap subtitle tracks
        audio_use_language: Whether to use language-based swapping for audio
        video_use_language: Whether to use language-based swapping for video
        subtitle_use_language: Whether to use language-based swapping for subtitle
        audio_language_order: Comma-separated language order for audio (e.g., "eng,hin")
        video_language_order: Comma-separated language order for video
        subtitle_language_order: Comma-separated language order for subtitle
        audio_index_order: Comma-separated index order for audio (e.g., "0,1")
        video_index_order: Comma-separated index order for video
        subtitle_index_order: Comma-separated index order for subtitle
        delete_original: Whether to delete the original file

    Returns:
        tuple: (command_list, output_file_path)
    """
    import os

    from bot.core.config_manager import Config
    from bot.helper.ext_utils.media_utils import get_streams

    # Get stream info
    try:
        streams = await get_streams(file_path)
        if not streams:
            LOGGER.error(f"No streams found in {file_path}")
            return [], None

    except Exception as e:
        LOGGER.error(f"Error getting stream info: {e}")
        return [], None

    # Check if any swap is enabled
    if not any([swap_audio, swap_video, swap_subtitle]):
        LOGGER.info("No swap operations enabled")
        return [], None

    # Generate output file path
    file_dir = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    file_base, file_ext = os.path.splitext(file_name)
    temp_file = os.path.join(file_dir, f"{file_base}.swapped{file_ext}")

    # Get CPU count for threading
    cpu_no = getattr(Config, "CPU_COUNT", 2)
    thread_count = max(1, cpu_no // 2)

    # Build the command
    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file_path,
    ]

    # Build mapping arguments
    map_args = []

    # Process video streams
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    if swap_video and video_streams:
        if video_use_language:
            # Language-based swapping
            video_map_order = _get_language_based_order(
                video_streams, video_language_order
            )
        else:
            # Index-based swapping
            video_map_order = _get_index_based_order(
                video_streams, video_index_order
            )

        for _new_idx, original_idx in enumerate(video_map_order):
            if original_idx is not None:
                map_args.extend(["-map", f"0:v:{original_idx}"])
    else:
        # Map all video streams in original order
        for i, _ in enumerate(video_streams):
            map_args.extend(["-map", f"0:v:{i}"])

    # Process audio streams
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if swap_audio and audio_streams:
        if audio_use_language:
            # Language-based swapping
            audio_map_order = _get_language_based_order(
                audio_streams, audio_language_order
            )
        else:
            # Index-based swapping
            audio_map_order = _get_index_based_order(
                audio_streams, audio_index_order
            )

        for _new_idx, original_idx in enumerate(audio_map_order):
            if original_idx is not None:
                map_args.extend(["-map", f"0:a:{original_idx}"])
    else:
        # Map all audio streams in original order
        for i, _ in enumerate(audio_streams):
            map_args.extend(["-map", f"0:a:{i}"])

    # Process subtitle streams
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    if swap_subtitle and subtitle_streams:
        if subtitle_use_language:
            # Language-based swapping
            subtitle_map_order = _get_language_based_order(
                subtitle_streams, subtitle_language_order
            )
        else:
            # Index-based swapping
            subtitle_map_order = _get_index_based_order(
                subtitle_streams, subtitle_index_order
            )

        for _new_idx, original_idx in enumerate(subtitle_map_order):
            if original_idx is not None:
                map_args.extend(["-map", f"0:s:{original_idx}"])
    else:
        # Map all subtitle streams in original order
        for i, _ in enumerate(subtitle_streams):
            map_args.extend(["-map", f"0:s:{i}"])

    # Add mapping arguments to command
    cmd.extend(map_args)

    # Copy all streams without re-encoding
    cmd.extend(["-c", "copy"])

    # Add threading
    cmd.extend(["-threads", str(thread_count)])

    # Add output file
    cmd.append(temp_file)

    # Add delete original flag if requested
    if delete_original:
        cmd.append("-del")

    return cmd, temp_file


def _get_language_based_order(streams, language_order):
    """Get stream order based on language priority.

    Args:
        streams: List of stream dictionaries
        language_order: Comma-separated language codes (e.g., "eng,hin")

    Returns:
        list: List of original stream indices in the desired order
    """
    if not language_order or language_order == "none":
        return list(range(len(streams)))

    languages = [lang.strip().lower() for lang in language_order.split(",")]
    ordered_indices = []
    used_indices = set()

    # First, add streams matching the language order
    for lang in languages:
        for i, stream in enumerate(streams):
            if i in used_indices:
                continue

            stream_lang = stream.get("tags", {}).get("language", "und").lower()
            if stream_lang == lang:
                ordered_indices.append(i)
                used_indices.add(i)
                break  # Only take the first match for each language

    # Then add remaining streams
    for i, stream in enumerate(streams):
        if i not in used_indices:
            ordered_indices.append(i)

    return ordered_indices


def _get_index_based_order(streams, index_order):
    """Get stream order based on index swapping.

    Args:
        streams: List of stream dictionaries
        index_order: Comma-separated indices (e.g., "1,0" to swap first two)

    Returns:
        list: List of original stream indices in the desired order
    """
    if not index_order or index_order == "none":
        return list(range(len(streams)))

    try:
        indices = [int(idx.strip()) for idx in index_order.split(",")]
    except ValueError:
        LOGGER.error(f"Invalid index order: {index_order}")
        return list(range(len(streams)))

    # Start with original order
    ordered_indices = list(range(len(streams)))

    # Apply swapping based on the provided indices
    # If only one index is provided, no swapping occurs
    if len(indices) >= 2:
        # Swap the streams at the specified indices
        for i in range(0, len(indices) - 1, 2):
            if i + 1 < len(indices):
                idx1, idx2 = indices[i], indices[i + 1]
                if 0 <= idx1 < len(streams) and 0 <= idx2 < len(streams):
                    ordered_indices[idx1], ordered_indices[idx2] = (
                        ordered_indices[idx2],
                        ordered_indices[idx1],
                    )

    return ordered_indices
