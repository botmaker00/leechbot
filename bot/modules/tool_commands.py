import asyncio
import contextlib
import os
from time import time

import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import DOWNLOAD_DIR, LOGGER
from bot.core.aeon_client import TgClient
from bot.helper.ext_utils.aiofiles_compat import makedirs
from bot.helper.ext_utils.aiofiles_compat import remove as aioremove
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.media_utils import get_media_info
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

# Image resize presets
RESIZE_PRESETS = {
    "1": {"name": "1:1 DP Square", "width": 512, "height": 512},
    "2": {"name": "16:9 Widescreen", "width": 1920, "height": 1080},
    "3": {"name": "9:16 Story", "width": 1080, "height": 1920},
    "4": {"name": "2:3 Portrait", "width": 1080, "height": 1620},
    "5": {"name": "1:2 Vertical", "width": 1080, "height": 2160},
    "6": {"name": "2:1 Horizontal", "width": 2160, "height": 1080},
    "7": {"name": "3:2 Standard", "width": 1920, "height": 1280},
    "8": {"name": "IG Post", "width": 1080, "height": 1080},
    "9": {"name": "YT Banner", "width": 2560, "height": 1440},
    "10": {"name": "YT Thumb", "width": 1280, "height": 720},
    "11": {"name": "X Header", "width": 1500, "height": 500},
    "12": {"name": "X Post", "width": 1200, "height": 675},
    "13": {"name": "LinkedIn Banner", "width": 1584, "height": 396},
    "14": {"name": "WhatsApp DP", "width": 640, "height": 640},
    "15": {"name": "Small Thumb", "width": 320, "height": 240},
    "16": {"name": "Medium Thumb", "width": 640, "height": 480},
    "17": {"name": "Wide Banner", "width": 1920, "height": 600},
}


def get_file_size(reply_msg) -> int:
    """Get file size from message media."""
    if reply_msg.document:
        return reply_msg.document.file_size or 0
    if reply_msg.video:
        return reply_msg.video.file_size or 0
    if reply_msg.audio:
        return reply_msg.audio.file_size or 0
    if reply_msg.voice:
        return reply_msg.voice.file_size or 0
    if reply_msg.video_note:
        return reply_msg.video_note.file_size or 0
    if reply_msg.sticker:
        return reply_msg.sticker.file_size or 0
    if reply_msg.animation:
        return reply_msg.animation.file_size or 0
    if reply_msg.photo:
        # In kurigram/pyrogram, photo is a single Photo object, not a list
        return reply_msg.photo.file_size or 0
    return 0


async def download_file_from_message(message: Message) -> str | None:
    """Download file from message and return the file path."""
    try:
        if not message.reply_to_message:
            await send_message(
                message, "<b>❌ Error:</b> Please reply to a file to use this tool."
            )
            return None

        reply_msg = message.reply_to_message

        # Check if the message has media
        if not (
            reply_msg.document
            or reply_msg.photo
            or reply_msg.video
            or reply_msg.audio
            or reply_msg.voice
            or reply_msg.video_note
            or reply_msg.sticker
            or reply_msg.animation
        ):
            await send_message(
                message, "<b>❌ Error:</b> Please reply to a media file."
            )
            return None

        # Get file size to determine which client to use
        file_size = get_file_size(reply_msg)
        file_size_mb = file_size / (1024 * 1024)  # Convert to MB

        # Determine which client to use based on file size
        # Bot client: up to 2GB, User client: 2GB to 4GB (if premium)
        use_user_client = False
        if file_size > 2 * 1024 * 1024 * 1024:  # > 2GB
            if TgClient.user and TgClient.IS_PREMIUM_USER:
                use_user_client = True
                LOGGER.info(
                    f"Using user client for large file: {file_size_mb:.1f}MB"
                )
            else:
                await send_message(
                    message,
                    f"<b>❌ Error:</b> File size ({file_size_mb:.1f}MB) exceeds bot limit (2GB). "
                    "Premium user session required for files larger than 2GB.",
                )
                return None
        else:
            pass

        # Create download directory
        download_dir = f"{DOWNLOAD_DIR}{message.from_user.id}_{int(time())}"
        await makedirs(download_dir, exist_ok=True)

        # Generate a unique filename
        file_extension = ""
        if reply_msg.document and reply_msg.document.file_name:
            file_extension = os.path.splitext(reply_msg.document.file_name)[1]
        elif reply_msg.photo:
            file_extension = ".jpg"
        elif reply_msg.video:
            file_extension = ".mp4"
        elif reply_msg.audio:
            file_extension = ".mp3"
        elif reply_msg.voice:
            file_extension = ".ogg"
        elif reply_msg.video_note:
            file_extension = ".mp4"
        elif reply_msg.sticker:
            file_extension = ".webp"
        elif reply_msg.animation:
            file_extension = ".gif"

        filename = f"file_{int(time())}{file_extension}"
        file_path = os.path.join(download_dir, filename)

        # Download the file with appropriate client

        if use_user_client:
            # Show status for large file download
            status_msg = await send_message(
                message,
                f"<b>📥 Large File Download:</b> Using premium session for {file_size_mb:.1f}MB file...",
            )

            # Get the message using user client
            user_message = await TgClient.user.get_messages(
                chat_id=reply_msg.chat.id, message_ids=reply_msg.id
            )
            downloaded_path = await user_message.download(file_name=file_path)

            # Delete status message
            await delete_message(status_msg)
        else:
            # Use bot client for smaller files
            try:
                downloaded_path = await reply_msg.download(file_name=file_path)
            except Exception as e:
                # If download fails with photo iteration error, try alternative approach
                if "not iterable" in str(e) and reply_msg.photo:
                    # For kurigram photo objects, try downloading using file_id
                    downloaded_path = await TgClient.bot.download_media(
                        reply_msg.photo.file_id, file_name=file_path
                    )
                else:
                    raise e

        # Verify the file was downloaded successfully
        if downloaded_path and os.path.exists(downloaded_path):
            return downloaded_path
        return None

    except Exception as e:
        LOGGER.error(f"Error downloading file: {e}")
        await send_message(
            message, f"<b>❌ Error:</b> Failed to download file: {e!s}"
        )
        return None


async def get_text_from_message(message: Message) -> str | None:
    """Get text from message or replied text file."""
    try:
        if message.reply_to_message:
            reply_msg = message.reply_to_message

            # If replying to a text message
            if reply_msg.text:
                return reply_msg.text

            # If replying to a text file
            if reply_msg.document and reply_msg.document.mime_type == "text/plain":
                file_path = await download_file_from_message(message)
                if file_path:
                    async with aiofiles.open(file_path, encoding="utf-8") as f:
                        content = await f.read()
                    await aioremove(file_path)
                    return content

        # Get text from command arguments
        if message.text:
            command_parts = message.text.split(maxsplit=2)
            if len(command_parts) > 2:
                return command_parts[2]

        await send_message(
            message,
            "<b>❌ Error:</b> Please provide text or reply to a text message/file.",
        )
        return None

    except Exception as e:
        LOGGER.error(f"Error getting text: {e}")
        await send_message(message, f"❌ Error processing text: {e!s}")
        return None


async def convert_video_to_gif(
    input_path: str, output_path: str
) -> tuple[bool, str]:
    """Convert video to GIF using FFmpeg."""
    try:
        # Get video info
        duration, _, _ = await get_media_info(input_path)

        # Limit GIF duration to 10 seconds for Telegram compatibility
        max_duration = min(duration, 10) if duration > 0 else 10

        # Create info message about duration limiting
        duration_info = ""
        if duration > 10:
            duration_info = f" (trimmed from {duration:.1f}s to 10s)"

        cmd = [
            "xtra",
            "-i",
            input_path,
            "-t",
            str(max_duration),
            "-vf",
            "fps=15,scale=512:-1:flags=lanczos,palettegen=reserve_transparent=0",
            "-y",
            f"{output_path}_palette.png",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        if process.returncode != 0:
            return False

        cmd = [
            "xtra",
            "-i",
            input_path,
            "-i",
            f"{output_path}_palette.png",
            "-t",
            str(max_duration),
            "-lavfi",
            "fps=15,scale=512:-1:flags=lanczos[x];[x][1:v]paletteuse",
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        # Clean up palette file
        await aioremove(f"{output_path}_palette.png")

        return process.returncode == 0, duration_info

    except Exception as e:
        LOGGER.error(f"Error converting video to GIF: {e}")
        return False, ""


async def create_sticker_from_media(
    input_path: str, output_path: str, media_type: str
) -> tuple[bool, str]:
    """Create a sticker from image, video, or text."""
    try:
        duration_info = ""

        if media_type == "image":
            # Convert image to WebP sticker format
            with Image.open(input_path) as img:
                # Convert to RGBA if not already
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                # Resize to 512x512 maintaining aspect ratio
                img.thumbnail((512, 512), Image.Resampling.LANCZOS)

                # Create a new 512x512 transparent image
                new_img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))

                # Center the image
                x = (512 - img.width) // 2
                y = (512 - img.height) // 2
                new_img.paste(img, (x, y), img)

                # Save as WebP
                new_img.save(output_path, "WEBP", quality=95)
                return True, duration_info

        elif media_type == "video":
            # Get video duration for info
            try:
                duration, _, _ = await get_media_info(input_path)
                if duration > 3:
                    duration_info = f" (trimmed from {duration:.1f}s to 3s)"
            except Exception:
                pass

            # Convert video to animated WebP sticker
            # Telegram animated stickers requirements:
            # - WebP format with animation
            # - 512x512 pixels maximum
            # - 3 seconds maximum duration
            # - Must be truly animated (not just a single frame)

            cmd = [
                "xtra",
                "-i",
                input_path,
                "-t",
                "3",  # Limit to 3 seconds for stickers
                "-vf",
                # Optimize for animated stickers with proper frame rate
                "fps=15,"  # 15 FPS for good animation while keeping file size reasonable
                "scale=512:512:force_original_aspect_ratio=decrease,"  # Scale to fit 512x512
                "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=white@0.0",  # Pad with transparent background
                "-c:v",
                "libwebp",
                "-lossless",
                "0",  # Use lossy compression for smaller file size
                "-quality",
                "75",  # Balanced quality for animated stickers
                "-method",
                "6",  # Best compression method
                "-preset",
                "default",
                "-loop",
                "0",  # Infinite loop - crucial for animation
                "-compression_level",
                "6",  # Good compression
                "-an",  # Remove audio (stickers don't need audio)
                "-y",
                output_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                # Try fallback with different settings
                return await create_animated_sticker_fallback(
                    input_path, output_path, duration_info
                )

            # Verify the output file exists and is a valid animated WebP
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                return False, duration_info

            # Check if the WebP is actually animated
            try:
                # Use ffprobe to check if it's animated
                probe_cmd = [
                    "xtra",
                    "-i",
                    output_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=nb_frames",
                    "-of",
                    "csv=p=0",
                ]
                probe_process = await asyncio.create_subprocess_exec(
                    *probe_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                probe_stdout, _ = await probe_process.communicate()
                frame_count = (
                    int(probe_stdout.decode().strip()) if probe_stdout else 0
                )

                if frame_count <= 1:
                    return await create_animated_sticker_fallback(
                        input_path, output_path, duration_info
                    )

            except Exception:
                pass

            return True, duration_info

        elif media_type == "text":
            # Create text sticker
            # Create a 512x512 transparent image
            img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Try to use a font, fallback to default
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
                )
            except Exception:
                font = ImageFont.load_default()

            # Get text from input_path (which is actually text in this case)
            text = input_path

            # Calculate text size and position
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            x = (512 - text_width) // 2
            y = (512 - text_height) // 2

            # Draw text with outline
            outline_width = 2
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text(
                            (x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255)
                        )

            # Draw main text
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

            # Save as WebP
            img.save(output_path, "WEBP", quality=95)
            return True, duration_info

        return False, ""

    except Exception as e:
        LOGGER.error(f"Error creating sticker: {e}")
        return False, ""


async def create_animated_sticker_fallback(
    input_path: str, output_path: str, duration_info: str
) -> tuple[bool, str]:
    """Fallback method for creating animated stickers with simpler settings."""
    try:
        cmd = [
            "xtra",
            "-i",
            input_path,
            "-t",
            "3",  # Limit to 3 seconds
            "-vf",
            # Simpler filter chain for better compatibility
            "fps=10,"  # Lower FPS for compatibility
            "scale=512:512:force_original_aspect_ratio=decrease,"
            "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=white@0.0",
            "-c:v",
            "libwebp",
            "-quality",
            "70",  # Lower quality for better compatibility
            "-loop",
            "0",  # Infinite loop
            "-an",  # No audio
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return False, duration_info

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, duration_info
        return False, duration_info

    except Exception as e:
        LOGGER.error(f"Error in fallback animated sticker creation: {e}")
        return False, duration_info


async def create_emoji_from_media(
    input_path: str, output_path: str, media_type: str
) -> bool:
    """Create an emoji from image or video."""
    try:
        if media_type == "image":
            # Convert image to emoji format (100x100 WebP)
            with Image.open(input_path) as img:
                # Convert to RGBA if not already
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                # Resize to 100x100 maintaining aspect ratio
                img.thumbnail((100, 100), Image.Resampling.LANCZOS)

                # Create a new 100x100 transparent image
                new_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))

                # Center the image
                x = (100 - img.width) // 2
                y = (100 - img.height) // 2
                new_img.paste(img, (x, y), img)

                # Save as WebP
                new_img.save(output_path, "WEBP", quality=95)
                return True

        elif media_type == "video":
            # Convert video to animated emoji (100x100 WebP)
            cmd = [
                "xtra",
                "-i",
                input_path,
                "-t",
                "3",  # Limit to 3 seconds for emojis
                "-vf",
                "fps=30,scale=100:100:force_original_aspect_ratio=decrease,pad=100:100:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
                "-c:v",
                "libwebp",
                "-quality",
                "95",
                "-preset",
                "default",
                "-loop",
                "0",
                "-y",
                output_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            return process.returncode == 0

        return False

    except Exception as e:
        LOGGER.error(f"Error creating emoji: {e}")
        return False


async def convert_audio_to_voice(
    input_path: str, output_path: str
) -> tuple[bool, str]:
    """Convert audio to Telegram voice message format (OGG Opus) with 1-minute limit."""
    try:
        # Get audio duration
        duration, _, _ = await get_media_info(input_path)

        # Voice notes should be limited to 1 minute (60 seconds)
        max_duration = min(duration, 60) if duration > 0 else 60

        # Create info message about duration limiting
        duration_info = ""
        if duration > 60:
            duration_info = f" (trimmed from {duration:.1f}s to 60s)"

        cmd = [
            "xtra",
            "-i",
            input_path,
            "-t",
            str(max_duration),  # Limit to 60 seconds
            "-c:a",
            "libopus",
            "-b:a",
            "64k",
            "-vbr",
            "on",
            "-compression_level",
            "10",
            "-frame_duration",
            "60",
            "-application",
            "voip",
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        return process.returncode == 0, duration_info

    except Exception as e:
        LOGGER.error(f"Error converting audio to voice: {e}")
        return False, ""


async def convert_video_to_video_note(input_path: str, output_path: str) -> bool:
    """Convert video to Telegram video note format (circular video like native recording)."""
    try:
        # Get video info
        duration, width, height = await get_media_info(input_path)

        # Telegram video notes requirements for circular appearance:
        # - Must be exactly square (1:1 aspect ratio)
        # - Specific encoding parameters for Telegram recognition
        # - Size should be 240x240 or 512x512
        # - Proper metadata for video note classification

        # Create a proper square video note that Telegram will render as circular
        # The key is to create a perfect square video with optimal settings
        cmd = [
            "xtra",
            "-i",
            input_path,
            "-vf",
            # Create perfect square video - Telegram handles the circular rendering
            "scale=240:240:force_original_aspect_ratio=increase,"
            "crop=240:240,"
            # Add a subtle vignette to enhance circular appearance
            "vignette=PI/4",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-profile:v",
            "main",
            "-level",
            "3.1",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # Fallback to simple approach
            return await convert_video_to_video_note_simple(input_path, output_path)

        # Verify the output file exists and has content
        return not (
            not os.path.exists(output_path) or os.path.getsize(output_path) == 0
        )

    except Exception as e:
        LOGGER.error(f"Error converting video to video note: {e}")
        return False


async def convert_video_to_video_note_simple(
    input_path: str, output_path: str
) -> bool:
    """Fallback simple video note conversion (square format)."""
    try:
        LOGGER.info("Using fallback simple video note conversion")

        cmd = [
            "xtra",
            "-i",
            input_path,
            "-vf",
            # Simple square crop and scale
            "scale=240:240:force_original_aspect_ratio=increase,crop=240:240",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "28",
            "-profile:v",
            "baseline",
            "-level",
            "3.0",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        return process.returncode == 0

    except Exception as e:
        LOGGER.error(f"Error in simple video note conversion: {e}")
        return False


async def remove_background_from_image(input_path: str, output_path: str) -> bool:
    """Remove background from image using simple edge detection and transparency."""
    try:
        with Image.open(input_path) as img:
            # Convert to RGBA if not already
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            # Simple background removal using color similarity
            # This is a basic implementation - for better results, you'd need rembg or similar
            data = img.getdata()
            new_data = []

            # Get corner pixels as background reference
            corners = [
                data[0],  # top-left
                data[img.width - 1],  # top-right
                data[img.width * (img.height - 1)],  # bottom-left
                data[img.width * img.height - 1],  # bottom-right
            ]

            # Calculate average background color
            bg_r = sum(pixel[0] for pixel in corners) // 4
            bg_g = sum(pixel[1] for pixel in corners) // 4
            bg_b = sum(pixel[2] for pixel in corners) // 4

            threshold = 30  # Color similarity threshold

            for pixel in data:
                r, g, b = pixel[:3]
                alpha = pixel[3] if len(pixel) == 4 else 255

                # Check if pixel is similar to background
                if (
                    abs(r - bg_r) < threshold
                    and abs(g - bg_g) < threshold
                    and abs(b - bg_b) < threshold
                ):
                    new_data.append((r, g, b, 0))  # Make transparent
                else:
                    new_data.append((r, g, b, alpha))  # Keep original

            img.putdata(new_data)
            img.save(output_path, "PNG")
            return True

    except Exception as e:
        LOGGER.error(f"Error removing background: {e}")
        return False


async def enhance_face_in_image(input_path: str, output_path: str) -> bool:
    """Enhance facial features in image using basic image processing."""
    try:
        with Image.open(input_path) as img:
            # Convert to RGB if not already
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Apply enhancements
            # Increase contrast slightly
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)

            # Increase sharpness
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.3)

            # Slight color enhancement
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.1)

            # Apply unsharp mask for better detail
            img = img.filter(
                ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3)
            )

            img.save(output_path, "JPEG", quality=95)
            return True

    except Exception as e:
        LOGGER.error(f"Error enhancing face: {e}")
        return False


async def resize_image(
    input_path: str, output_path: str, width: int, height: int
) -> bool:
    """Resize image to specified dimensions."""
    try:
        with Image.open(input_path) as img:
            # Resize image
            resized_img = img.resize((width, height), Image.Resampling.LANCZOS)

            # Save with appropriate format
            if output_path.lower().endswith(".png"):
                resized_img.save(output_path, "PNG", quality=95)
            else:
                # Convert to RGB if saving as JPEG
                if resized_img.mode in ("RGBA", "LA", "P"):
                    resized_img = resized_img.convert("RGB")
                resized_img.save(output_path, "JPEG", quality=95)

            return True

    except Exception as e:
        LOGGER.error(f"Error resizing image: {e}")
        return False


async def download_github_repo(repo_url: str, output_path: str) -> tuple[bool, str]:
    """Download GitHub repository as ZIP file."""
    try:
        repo_name = ""

        # Parse GitHub URL (HTTP/HTTPS or SSH)
        if repo_url.startswith("git@github.com:"):
            # SSH format: git@github.com:username/repository.git
            repo_path = repo_url.replace("git@github.com:", "").removesuffix(".git")
            repo_url = f"https://github.com/{repo_path}"
            repo_name = repo_path.split("/")[-1]
        elif repo_url.startswith(("https://github.com/", "http://github.com/")):
            # HTTP/HTTPS format
            repo_url = repo_url.removesuffix("/").removesuffix(".git")
            repo_name = repo_url.split("/")[-1]
        else:
            return False, ""

        zip_url = f"{repo_url}/archive/refs/heads/main.zip"

        # Try main branch first, then master
        async with aiohttp.ClientSession() as session:
            async with session.get(zip_url) as response:
                if response.status == 404:
                    # Try master branch
                    zip_url = f"{repo_url}/archive/refs/heads/master.zip"
                    async with session.get(zip_url) as response:
                        if response.status != 200:
                            return False
                        content = await response.read()
                elif response.status != 200:
                    return False
                else:
                    content = await response.read()

        # Save the ZIP file
        async with aiofiles.open(output_path, "wb") as f:
            await f.write(content)

        return True, repo_name

    except Exception as e:
        LOGGER.error(f"Error downloading GitHub repo: {e}")
        return False, ""


def count_words(text: str) -> int:
    """Count words in text."""
    # Split by whitespace and filter out empty strings
    words = [word for word in text.split() if word.strip()]
    return len(words)


def count_characters(text: str) -> int:
    """Count characters in text."""
    return len(text)


def reverse_text(text: str) -> str:
    """Reverse text."""
    return text[::-1]


def calculate_expression(expression: str) -> str:
    """Calculate mathematical expression safely."""
    import math
    import re

    # Remove any potentially dangerous characters/functions
    dangerous_patterns = [
        r"__.*__",  # Dunder methods
        r"import",  # Import statements
        r"exec",  # Exec function
        r"eval",  # Eval function (we'll use our own safe eval)
        r"open",  # File operations
        r"input",  # Input function
        r"print",  # Print function
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, expression, re.IGNORECASE):
            return "❌ Invalid expression: Contains restricted functions"

    # Define safe mathematical functions and constants
    safe_dict = {
        # Basic operations are handled by Python
        # Mathematical functions
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        # Math module functions
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "atan2": math.atan2,
        "sinh": math.sinh,
        "cosh": math.cosh,
        "tanh": math.tanh,
        "asinh": math.asinh,
        "acosh": math.acosh,
        "atanh": math.atanh,
        "sqrt": math.sqrt,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "exp": math.exp,
        "exp2": lambda x: 2**x,
        "ceil": math.ceil,
        "floor": math.floor,
        "trunc": math.trunc,
        "fabs": math.fabs,
        "factorial": math.factorial,
        "gcd": math.gcd,
        "degrees": math.degrees,
        "radians": math.radians,
        # Constants
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
        "inf": math.inf,
        "nan": math.nan,
        # Additional useful functions
        "bin": bin,
        "hex": hex,
        "oct": oct,
    }

    try:
        # Standard operators (* / + - ** %) are supported natively
        # Replace alternative mathematical notation for convenience
        expression = expression.replace("^", "**")  # Power operator (^ → **)
        expression = expression.replace("×", "*")  # Multiplication (× → *)
        expression = expression.replace("÷", "/")  # Division (÷ → /)

        # Handle common mathematical notation patterns
        import re

        # Convert function names without parentheses to proper function calls
        # e.g., "sin60" → "sin(60)", "log10" → "log(10)", etc.
        function_patterns = [
            (
                r"\b(sin|cos|tan|asin|acos|atan|sinh|cosh|tanh|asinh|acosh|atanh)(\d+(?:\.\d+)?)",
                r"\1(\2)",
            ),
            (
                r"\b(sqrt|log|log10|log2|exp|ceil|floor|abs|factorial)(\d+(?:\.\d+)?)",
                r"\1(\2)",
            ),
        ]

        for pattern, replacement in function_patterns:
            expression = re.sub(pattern, replacement, expression)

        # Handle degree to radian conversion for trig functions
        # Convert degrees to radians for sin, cos, tan functions
        trig_degree_pattern = r"\b(sin|cos|tan)\((\d+(?:\.\d+)?)\)"

        def convert_degrees(match):
            func = match.group(1)
            degrees = float(match.group(2))
            # Common angles - use exact values
            if degrees == 0:
                return f"{func}(0)"
            if degrees == 30:
                return f"{func}(pi/6)"
            if degrees == 45:
                return f"{func}(pi/4)"
            if degrees == 60:
                return f"{func}(pi/3)"
            if degrees == 90:
                return f"{func}(pi/2)"
            if degrees == 180:
                return f"{func}(pi)"
            if degrees == 270:
                return f"{func}(3*pi/2)"
            if degrees == 360:
                return f"{func}(2*pi)"
            # Convert degrees to radians
            return f"{func}({degrees}*pi/180)"

        expression = re.sub(trig_degree_pattern, convert_degrees, expression)

        # Evaluate the expression safely
        result = eval(expression, {"__builtins__": {}}, safe_dict)

        # Format the result nicely
        if isinstance(result, float):
            if result.is_integer():
                return str(int(result))
            # Round to 10 decimal places to avoid floating point errors
            return f"{result:.10g}"
        return str(result)

    except ZeroDivisionError:
        return "❌ Error: Division by zero"
    except ValueError as e:
        return f"❌ Math Error: {e!s}"
    except SyntaxError:
        return "❌ Syntax Error: Invalid mathematical expression\n💡 Tip: Use parentheses for functions (e.g., sin(60), sqrt(16))"
    except NameError as e:
        error_msg = str(e)
        if "is not defined" in error_msg:
            # Extract the undefined name
            undefined_name = (
                error_msg.split("'")[1] if "'" in error_msg else "unknown"
            )

            # Provide helpful suggestions
            suggestions = []
            if any(func in undefined_name.lower() for func in ["sin", "cos", "tan"]):
                suggestions.append("Use parentheses: sin(60), cos(45), tan(30)")
            if any(func in undefined_name.lower() for func in ["sqrt", "log"]):
                suggestions.append("Use parentheses: sqrt(16), log(100)")
            if undefined_name.lower() in ["e", "pi"]:
                suggestions.append(f"Use lowercase: {undefined_name.lower()}")

            suggestion_text = (
                "\n💡 Try: " + ", ".join(suggestions)
                if suggestions
                else "\n💡 Tip: Use parentheses for functions"
            )
            return f"❌ Error: '{undefined_name}' is not defined{suggestion_text}"
        return f"❌ Name Error: {e!s}"
    except Exception as e:
        return f"❌ Error: {e!s}"


async def create_sticker_pack_video(
    input_path: str, output_path: str, variation: int
) -> tuple[bool, str]:
    """Create animated sticker variation from video."""
    try:
        # Get video duration
        duration, _, _ = await get_media_info(input_path)

        # Calculate start time for variation (spread across video)
        start_time = variation * duration / 5 % (duration - 3) if duration > 3 else 0

        cmd = [
            "xtra",
            "-ss",
            str(start_time),  # Start time for variation
            "-i",
            input_path,
            "-t",
            "3",  # 3 seconds duration
            "-vf",
            "fps=15,scale=512:512:force_original_aspect_ratio=decrease,"
            "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=white@0.0",
            "-c:v",
            "libwebp",
            "-quality",
            "75",
            "-loop",
            "0",
            "-an",
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        return process.returncode == 0, ""

    except Exception as e:
        return False, str(e)


async def create_telegram_sticker_pack(
    user_id: int,
    pack_name: str,
    pack_title: str,
    sticker_paths: list,
    sticker_format: str,
    emoji: str,
) -> bool:
    """Create actual Telegram sticker pack using HTTP Bot API."""
    try:
        import json

        # Get bot token
        bot_token = TgClient.bot.bot_token
        url = f"https://api.telegram.org/bot{bot_token}/createNewStickerSet"

        # Prepare multipart form data
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()

            # Add basic fields
            data.add_field("user_id", str(user_id))
            data.add_field("name", pack_name)
            data.add_field("title", pack_title)
            data.add_field("sticker_format", sticker_format)

            # Prepare stickers data
            stickers_data = []
            for i, sticker_path in enumerate(sticker_paths):
                # Add file
                with open(sticker_path, "rb") as f:
                    data.add_field(
                        f"sticker_{i}",
                        f,
                        filename=f"sticker_{i}.webp",
                        content_type="image/webp",
                    )

                # Add sticker info
                stickers_data.append(
                    {"sticker": f"attach://sticker_{i}", "emoji_list": [emoji]}
                )

            # Add stickers JSON
            data.add_field("stickers", json.dumps(stickers_data))

            # Make the request
            async with session.post(url, data=data) as response:
                result = await response.json()

                if result.get("ok"):
                    LOGGER.info(f"Sticker pack created successfully: {pack_name}")
                    return True
                error_desc = result.get("description", "Unknown error")
                LOGGER.error(f"Sticker pack creation failed: {error_desc}")
                LOGGER.error(f"Full response: {result}")
                return False

    except Exception as e:
        LOGGER.error(f"Error creating sticker pack: {e}")
        LOGGER.error(
            f"Pack details - Name: {pack_name}, Title: {pack_title}, User: {user_id}"
        )
        return False


async def create_text_sticker(text: str, output_path: str) -> bool:
    """Create a text sticker from text content."""
    try:
        # Create a 512x512 transparent image
        img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Try to use a font, fallback to default
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
            )
        except Exception:
            font = ImageFont.load_default()

        # Calculate text size and position
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (512 - text_width) // 2
        y = (512 - text_height) // 2

        # Draw text with outline
        outline_width = 2
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))

        # Draw main text
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

        # Save as WebP
        img.save(output_path, "WEBP", quality=95)
        return True

    except Exception:
        return False


async def create_sticker_pack_image(
    input_path: str, output_path: str, variation: int
) -> bool:
    """Create static sticker variation from image."""
    try:
        from PIL import Image, ImageEnhance, ImageFilter

        with Image.open(input_path) as img:
            # Convert to RGBA
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            # Apply different effects based on variation
            if variation == 0:
                # Original - just resize
                pass
            elif variation == 1:
                # Brightness adjustment
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(1.2)
            elif variation == 2:
                # Contrast adjustment
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.3)
            elif variation == 3:
                # Color saturation
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(1.4)
            elif variation == 4:
                # Slight blur effect
                img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

            # Resize to sticker dimensions
            img.thumbnail((512, 512), Image.Resampling.LANCZOS)

            # Create new 512x512 image with transparent background
            new_img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))

            # Center the image
            x = (512 - img.width) // 2
            y = (512 - img.height) // 2
            new_img.paste(img, (x, y), img)

            # Save as WebP
            new_img.save(output_path, "WEBP", quality=95)
            return True

    except Exception:
        return False


async def create_resize_menu() -> InlineKeyboardMarkup:
    """Create resize options menu."""
    buttons = []

    # Create buttons in rows of 2
    for i in range(1, len(RESIZE_PRESETS) + 1, 2):
        row = []

        # First button in row
        preset1 = RESIZE_PRESETS[str(i)]
        row.append(
            InlineKeyboardButton(
                f"{i}. {preset1['name']}", callback_data=f"resize_{i}"
            )
        )

        # Second button in row (if exists)
        if i + 1 <= len(RESIZE_PRESETS):
            preset2 = RESIZE_PRESETS[str(i + 1)]
            row.append(
                InlineKeyboardButton(
                    f"{i + 1}. {preset2['name']}", callback_data=f"resize_{i + 1}"
                )
            )

        buttons.append(row)

    # Add cancel button
    buttons.append(
        [InlineKeyboardButton("❌ Cancel", callback_data="resize_cancel")]
    )

    return InlineKeyboardMarkup(buttons)


# Store user data for resize operations
resize_user_data = {}


from bot import user_data
from bot.core.config_manager import Config
from bot.helper.aeon_utils.send_file import add_watermark, send_file
from bot.helper.ext_utils.bot_utils import is_media_tool_enabled
from bot.helper.listeners.task_listener import TaskListener
from bot.modules.media_tools import add_media, get_watermark_settings


async def handle_watermark_tool(message: Message, client):
    if not message.reply_to_message:
        await send_message(message, "Please reply to a media file.")
        return

    if not is_media_tool_enabled("watermark"):
        await send_message(message, "The 'watermark' tool is disabled.")
        return

    status_msg = await send_message(message, "Processing watermark...")

    file_path = await download_file_from_message(message)
    if not file_path:
        await edit_message(status_msg, "Failed to download file.")
        return

    user_id = message.from_user.id
    (
        watermark_enabled,
        watermark_key,
        watermark_position,
        watermark_size,
        watermark_color,
        watermark_font,
        watermark_opacity,
        watermark_remove_original,
        watermark_threading,
        watermark_thread_number,
        audio_watermark_enabled,
        audio_watermark_text,
        audio_watermark_volume,
        subtitle_watermark_enabled,
        subtitle_watermark_text,
        subtitle_watermark_style,
        image_watermark_enabled,
        image_watermark_path,
        image_watermark_scale,
        image_watermark_position,
        image_watermark_opacity,
    ) = await get_watermark_settings(user_id)

    if not watermark_enabled:
        await edit_message(status_msg, "Watermark is not enabled.")
        await aioremove(file_path)
        return

    class DummyListener(TaskListener):
        def __init__(self, message, client):
            super().__init__(message, client)
            self.is_leech = False
            self.is_mirror = True
            self.extract = False
            self.compress = False
            self.name = os.path.basename(file_path)

    listener = DummyListener(message, client)

    success, output_path, error_message = await add_watermark(
        file_path,
        user_id,
        listener.mid,
        watermark_key,
        watermark_position,
        watermark_size,
        watermark_color,
        watermark_font,
        watermark_opacity,
        watermark_remove_original,
        watermark_threading,
        watermark_thread_number,
        audio_watermark_enabled,
        audio_watermark_text,
        audio_watermark_volume,
        subtitle_watermark_enabled,
        subtitle_watermark_text,
        subtitle_watermark_style,
        image_watermark_enabled,
        image_watermark_path,
        image_watermark_scale,
        image_watermark_position,
        image_watermark_opacity,
    )

    if success:
        await send_file(message, output_path)
        if output_path and os.path.exists(output_path):
            await aioremove(output_path)
    else:
        await send_message(message, f"Failed to add watermark: {error_message}")

    await delete_message(status_msg)
    if file_path and os.path.exists(file_path):
        await aioremove(file_path)


async def handle_merge_tool(message: Message, client):
    if not message.reply_to_message:
        await send_message(message, "Please reply to a media file.")
        return

    user_id = message.from_user.id
    merge_enabled = user_data.get(user_id, {}).get("MERGE_ENABLED", False)
    if not merge_enabled and not Config.MERGE_ENABLED:
        await send_message(message, "Merge is not enabled.")
        return

    ask_msg = await send_message(
        message, "How many files do you want to merge in total?"
    )

    try:
        count_msg = await client.listen(
            user_id=message.from_user.id, chat_id=message.chat.id, timeout=60
        )
        num_files = int(count_msg.text)
        await delete_message(count_msg)
        await delete_message(ask_msg)
    except (asyncio.TimeoutError, ValueError):
        await delete_message(ask_msg)
        await send_message(message, "Invalid input or timeout. Merge cancelled.")
        return

    if num_files < 2:
        await send_message(message, "You need to merge at least 2 files.")
        return

    files_to_merge = [message.reply_to_message]
    for i in range(1, num_files):
        prompt_msg = await send_message(
            message.chat.id, f"Please send file {i + 1}/{num_files}."
        )
        try:
            file_msg = await client.listen(
                user_id=message.from_user.id, chat_id=message.chat.id, timeout=300
            )
            if (
                file_msg.document
                or file_msg.video
                or file_msg.audio
                or file_msg.photo
            ):
                files_to_merge.append(file_msg)
                await delete_message(prompt_msg)
            else:
                await send_message(
                    message.chat.id, "This is not a valid file. Merge cancelled."
                )
                await delete_message(prompt_msg)
                return
        except asyncio.TimeoutError:
            await send_message(
                message.chat.id, "You took too long to send the file. Merge cancelled."
            )
            await delete_message(prompt_msg)
            return

    status_msg = await send_message(message, "Downloading files...")
    downloaded_paths = []
    download_dir = f"{DOWNLOAD_DIR}merge_{message.id}/"
    await makedirs(download_dir, exist_ok=True)

    for i, msg in enumerate(files_to_merge):
        await edit_message(status_msg, f"Downloading file {i + 1}/{num_files}...")
        try:
            path = await msg.download(file_name=download_dir)
            downloaded_paths.append(path)
        except Exception as e:
            await edit_message(status_msg, f"Failed to download a file: {e}")
            return

    await edit_message(status_msg, "Merging files...")
    success, output_path, error_message = await add_media(
        downloaded_paths[0], user_id, message.id, multi_files=downloaded_paths[1:]
    )

    if success:
        await send_file(message, output_path)
        if output_path and os.path.exists(output_path):
            await aioremove(output_path)
    else:
        await send_message(message, f"Failed to merge files: {error_message}")

    await delete_message(status_msg)
    for path in downloaded_paths:
        if await aiofiles.os.path.exists(path):
            await aioremove(path)
    if await aiofiles.os.path.exists(download_dir):
        await aioremove(download_dir)


@new_task
async def tool_command(client, message: Message):
    """Handle /tool command with various subcommands."""
    try:
        command_parts = message.text.split()

        if len(command_parts) < 2:
            help_text = """
<b>🛠️ Tool Commands Help</b>

<b>🎬 Media Conversion:</b>
• <code>/tool gif</code> - Convert video/animation to Telegram GIF (auto-trims to 10s)
• <code>/tool sticker [number]</code> - Create N stickers from media/text (supports GIF, videos → animated)
• <code>/tool emoji</code> - Convert image/video to emoji
• <code>/tool voice</code> - Convert audio/video to voice message (auto-trims to 60s)
• <code>/tool vnote</code> - Convert video/animation to video note (any duration)

<b>🖼️ Image Processing:</b>
• <code>/tool remBgImg</code> - Remove image background
• <code>/tool enhFace</code> - Enhance facial features
• <code>/tool resImg</code> - Resize image (shows menu)
• <code>/tool resImg &lt;width&gt; &lt;height&gt;</code> - Resize to specific dimensions

<b>📝 Text Processing:</b>
• <code>/tool countWord</code> - Count words in text
• <code>/tool countChar</code> - Count characters in text
• <code>/tool revText</code> - Reverse text

<b>🎨 Sticker Pack:</b>
• <code>/tool stickerpack [number]</code> - Create actual Telegram sticker pack (default: 10, max: 50)

<b>🧮 Calculator:</b>
• <code>/tool cal &lt;expression&gt;</code> - Calculate mathematical expressions (supports scientific functions)

<b>📦 GitHub Repository:</b>
• <code>/tool &lt;GitHub_URL&gt;</code> - Download GitHub repo as ZIP

<b>📱 Supported Media Types:</b>
• <b>Videos:</b> MP4, AVI, MOV, MKV, WebM, etc.
• <b>Images:</b> JPG, PNG, WebP, GIF, BMP, etc.
• <b>Audio:</b> MP3, OGG, WAV, M4A, FLAC, etc.
• <b>Animations:</b> GIF, WebP, MP4 animations
• <b>Documents:</b> Any video/audio/image file

<b>📊 File Size Limits:</b>
• <b>Standard:</b> Up to 2GB (bot client)
• <b>Large Files:</b> 2GB-4GB (requires premium user session)

<b>💡 Usage:</b> Reply to a file/message and use the appropriate tool command.

<b>📋 Examples:</b>
• <code>/tool https://github.com/username/repository</code>
• <code>/tool git@github.com:username/repository.git</code>
            """
            await send_message(message, help_text)
            return

        tool_type = command_parts[1].lower()

        # Check if it's a GitHub URL (HTTP/HTTPS or SSH)
        if tool_type.startswith(
            (
                "https://github.com/",
                "http://github.com/",
                "github.com/",
                "git@github.com:",
            )
        ):
            await handle_github_download(message)
            return

        # Handle different tool types
        if tool_type == "gif":
            await handle_gif_conversion(message)
        elif tool_type == "sticker" or tool_type.startswith("sticker"):
            await handle_sticker_creation(message)
        elif tool_type == "emoji":
            await handle_emoji_creation(message)
        elif tool_type == "voice":
            await handle_voice_conversion(message)
        elif tool_type == "vnote":
            await handle_video_note_conversion(message)
        elif tool_type == "rembgimg":
            await handle_background_removal(message)
        elif tool_type == "enhface":
            await handle_face_enhancement(message)
        elif tool_type == "resimg":
            await handle_image_resize(message)
        elif tool_type == "countword":
            await handle_word_count(message)
        elif tool_type == "countchar":
            await handle_char_count(message)
        elif tool_type == "revtext":
            await handle_text_reverse(message)
        elif tool_type == "stickerpack" or tool_type.startswith("stickerpack"):
            await handle_sticker_pack_creation(message)
        elif tool_type == "cal":
            await handle_calculator(message)
        elif tool_type == "watermark":
            await handle_watermark_tool(message, client)
        elif tool_type == "merge":
            await handle_merge_tool(message, client)
        else:
            await send_message(message, f"❌ Unknown tool: {tool_type}")

    except Exception as e:
        LOGGER.error(f"Error in tool command: {e}")
        await send_message(message, f"❌ Error: {e!s}")


async def handle_gif_conversion(message: Message):
    """Handle video to GIF conversion."""
    try:
        if not message.reply_to_message:
            await send_message(
                message,
                "<b>❌ Error:</b> Please reply to a video to convert to GIF.",
            )
            return

        reply_msg = message.reply_to_message
        if not (
            reply_msg.video
            or reply_msg.animation
            or reply_msg.video_note
            or (
                reply_msg.document
                and reply_msg.document.mime_type
                and reply_msg.document.mime_type.startswith("video")
            )
        ):
            await send_message(
                message, "<b>❌ Error:</b> Please reply to a video file."
            )
            return

        status_msg = await send_message(
            message, "<b>🔄 Processing:</b> Converting video to GIF..."
        )

        # Download video
        input_path = await download_file_from_message(message)
        if not input_path:
            await edit_message(
                status_msg, "<b>❌ Failed:</b> Could not download video file."
            )
            return

        # Convert to GIF
        output_path = f"{input_path}_converted.gif"
        success, duration_info = await convert_video_to_gif(input_path, output_path)

        if success and os.path.exists(output_path):
            # Send GIF
            await edit_message(
                status_msg, "<b>📤 Uploading:</b> Sending GIF file..."
            )

            caption = "<b>🎞️ Video to GIF</b>\n\n<i>✅ Conversion completed successfully!</i>"
            if duration_info:
                caption += f"\n<i>📏 Duration: {duration_info}</i>"

            await TgClient.bot.send_animation(
                chat_id=message.chat.id,
                animation=output_path,
                caption=caption,
                reply_to_message_id=message.id,
            )
            await delete_message(status_msg)
        else:
            await edit_message(
                status_msg, "<b>❌ Failed:</b> Could not convert video to GIF."
            )

        # Cleanup
        await aioremove(input_path)
        if os.path.exists(output_path):
            await aioremove(output_path)

    except Exception as e:
        LOGGER.error(f"Error in GIF conversion: {e}")
        await send_message(message, f"❌ Error converting to GIF: {e!s}")


async def handle_sticker_creation(message: Message):
    """Handle sticker creation from media or text with optional count."""
    try:
        # Parse command to get count
        command_parts = message.text.split()
        count = 1  # Default count
        text_content = None

        # Check if a number is specified (e.g., "/tool sticker 5")
        if len(command_parts) >= 3:
            if command_parts[2].isdigit():
                count = int(command_parts[2])
                count = min(max(count, 1), 20)  # Limit between 1-20
            else:
                # It's text content
                text_content = " ".join(command_parts[2:])

        if message.reply_to_message and not text_content:
            reply_msg = message.reply_to_message

            # Check if it's a text message
            if reply_msg.text:
                # Handle text sticker creation from replied text
                text_content = reply_msg.text
                status_msg = await send_message(
                    message,
                    f"<b>🏷️ Creating:</b> Processing {count} text sticker(s)...",
                )

                # Create multiple text stickers
                sticker_paths = []

                for i in range(count):
                    output_path = (
                        f"downloads/text_sticker_{int(time())}_{i + 1}.webp"
                    )
                    success = await create_text_sticker(text_content, output_path)

                    if success and os.path.exists(output_path):
                        sticker_paths.append(output_path)

                if not sticker_paths:
                    await edit_message(
                        status_msg,
                        "<b>❌ Failed:</b> Could not create text stickers.",
                    )
                    return

                # Send all text stickers
                await edit_message(
                    status_msg,
                    f"<b>📤 Uploading:</b> Sending {len(sticker_paths)} text sticker(s)...",
                )

                sent_count = 0
                for sticker_path in sticker_paths:
                    try:
                        await TgClient.bot.send_sticker(
                            chat_id=message.chat.id,
                            sticker=sticker_path,
                            reply_to_message_id=message.id,
                        )
                        sent_count += 1
                        await asyncio.sleep(0.3)
                    except Exception:
                        continue
                    finally:
                        with contextlib.suppress(Exception):
                            await aioremove(sticker_path)

                # Send completion message
                completion_text = "<b>🏷️ 🖼️ Text Stickers Created</b>\n\n"
                completion_text += f"<b>📊 Count:</b> {sent_count} stickers sent\n"
                completion_text += f"<b>📝 Text:</b> {text_content[:50]}{'...' if len(text_content) > 50 else ''}\n"
                completion_text += (
                    "<b>✅ Status:</b> All text stickers created successfully!"
                )

                await TgClient.bot.send_message(
                    chat_id=message.chat.id,
                    text=completion_text,
                    reply_to_message_id=message.id,
                )

                await delete_message(status_msg)
                return

            # Check if media is supported (including GIFs)
            if not (
                reply_msg.photo
                or reply_msg.video
                or reply_msg.animation
                or reply_msg.sticker
                or reply_msg.video_note
                or (
                    reply_msg.document
                    and reply_msg.document.mime_type
                    and (
                        reply_msg.document.mime_type.startswith("image")
                        or reply_msg.document.mime_type.startswith("video")
                        or reply_msg.document.mime_type == "image/gif"
                    )
                )
            ):
                await send_message(
                    message,
                    "<b>❌ Error:</b> Please reply to a supported media type (image, video, GIF, sticker, text).",
                )
                return

            status_msg = await send_message(
                message, f"<b>🏷️ Creating:</b> Processing {count} sticker(s)..."
            )

            # Download the file
            input_path = await download_file_from_message(message)
            if not input_path:
                await edit_message(
                    status_msg, "<b>❌ Failed:</b> Could not download file."
                )
                return

            # Determine media type - support all media types including GIFs
            if (
                reply_msg.video
                or reply_msg.animation
                or reply_msg.video_note
                or (
                    reply_msg.document
                    and reply_msg.document.mime_type
                    and (
                        reply_msg.document.mime_type.startswith("video")
                        or reply_msg.document.mime_type == "image/gif"
                    )
                )
            ):
                media_type = "video"
            else:
                media_type = "image"

            # Create multiple stickers
            sticker_paths = []

            try:
                for i in range(count):
                    output_path = f"{input_path}_sticker_{i + 1}.webp"

                    if media_type == "video":
                        # Create animated stickers with different start times
                        success, _ = await create_sticker_pack_video(
                            input_path, output_path, i
                        )
                    else:
                        # Create static stickers with different effects
                        success = await create_sticker_pack_image(
                            input_path, output_path, i
                        )

                    if success and os.path.exists(output_path):
                        sticker_paths.append(output_path)
            finally:
                # Cleanup input file
                await aioremove(input_path)

            if not sticker_paths:
                await edit_message(
                    status_msg, "<b>❌ Failed:</b> Could not create stickers."
                )
                return

            # Send all stickers
            await edit_message(
                status_msg,
                f"<b>📤 Uploading:</b> Sending {len(sticker_paths)} sticker(s)...",
            )

            sent_count = 0
            for i, sticker_path in enumerate(sticker_paths):
                try:
                    await TgClient.bot.send_sticker(
                        chat_id=message.chat.id,
                        sticker=sticker_path,
                        reply_to_message_id=message.id,
                    )
                    sent_count += 1
                    # Small delay between sends
                    await asyncio.sleep(0.3)
                except Exception:
                    continue  # Skip failed stickers
                finally:
                    # Cleanup sticker file
                    with contextlib.suppress(Exception):
                        await aioremove(sticker_path)

            # Send completion message
            sticker_type = "🎬 Animated" if media_type == "video" else "🖼️ Static"
            completion_text = f"<b>🏷️ {sticker_type} Stickers Created</b>\n\n"
            completion_text += f"<b>📊 Count:</b> {sent_count} stickers sent\n"
            completion_text += "<b>✅ Status:</b> All stickers created successfully!"

            await TgClient.bot.send_message(
                chat_id=message.chat.id,
                text=completion_text,
                reply_to_message_id=message.id,
            )

            await delete_message(status_msg)

        else:
            # Handle text sticker creation
            if not text_content:
                await send_message(
                    message,
                    "<b>❌ Error:</b> Please provide text or reply to media.\n\n"
                    "<b>📝 Usage:</b>\n"
                    "• <code>/tool sticker &lt;text&gt;</code> - Create text sticker\n"
                    "• <code>/tool sticker &lt;number&gt;</code> (reply to media) - Create N stickers\n"
                    "• <code>/tool sticker</code> (reply to media) - Create 1 sticker",
                )
                return

            status_msg = await send_message(
                message, "<b>🏷️ Creating:</b> Generating text sticker..."
            )

            # Create text sticker
            output_path = f"downloads/text_sticker_{int(time())}.webp"
            success, _ = await create_sticker_from_media(
                text_content, output_path, "text"
            )

            if success and os.path.exists(output_path):
                await edit_message(
                    status_msg, "<b>📤 Uploading:</b> Sending sticker..."
                )
                await TgClient.bot.send_sticker(
                    chat_id=message.chat.id,
                    sticker=output_path,
                    reply_to_message_id=message.id,
                )

                await TgClient.bot.send_message(
                    chat_id=message.chat.id,
                    text="<b>🏷️ 🖼️ Static Sticker Created</b>\n\n<i>✅ Text converted successfully!</i>",
                    reply_to_message_id=message.id,
                )

                await delete_message(status_msg)
                await aioremove(output_path)
            else:
                await edit_message(
                    status_msg, "<b>❌ Failed:</b> Could not create text sticker."
                )

    except Exception as e:
        LOGGER.error(f"Error in sticker creation: {e}")
        await send_message(message, f"❌ Error creating sticker: {e!s}")


async def handle_emoji_creation(message: Message):
    """Handle emoji creation from image or video."""
    try:
        if not message.reply_to_message:
            await send_message(
                message, "❌ Please reply to an image or video to create emoji."
            )
            return

        reply_msg = message.reply_to_message
        if not (reply_msg.photo or reply_msg.video or reply_msg.document):
            await send_message(message, "❌ Please reply to an image or video file.")
            return

        status_msg = await send_message(message, "🔄 Creating emoji...")

        # Download media
        input_path = await download_file_from_message(message)
        if not input_path:
            await edit_message(status_msg, "❌ Failed to download media.")
            return

        # Determine media type
        media_type = (
            "video"
            if (
                reply_msg.video
                or (
                    reply_msg.document
                    and reply_msg.document.mime_type.startswith("video")
                )
            )
            else "image"
        )

        output_path = f"{input_path}_emoji.webp"
        success = await create_emoji_from_media(input_path, output_path, media_type)

        if success and os.path.exists(output_path):
            # Send emoji as sticker
            await edit_message(status_msg, "📤 Uploading emoji...")
            await TgClient.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=output_path,
                reply_to_message_id=message.id,
            )
            await delete_message(status_msg)
        else:
            await edit_message(status_msg, "❌ Failed to create emoji.")

        # Cleanup
        await aioremove(input_path)
        if os.path.exists(output_path):
            await aioremove(output_path)

    except Exception as e:
        LOGGER.error(f"Error in emoji creation: {e}")
        await send_message(message, f"❌ Error creating emoji: {e!s}")


async def handle_voice_conversion(message: Message):
    """Handle audio to voice message conversion."""
    try:
        if not message.reply_to_message:
            await send_message(
                message,
                "❌ Please reply to an audio file to convert to voice message.",
            )
            return

        reply_msg = message.reply_to_message
        if not (
            reply_msg.audio
            or reply_msg.voice
            or reply_msg.video_note  # Video notes can be converted to voice
            or (reply_msg.video and reply_msg.video.duration)  # Videos with audio
            or (
                reply_msg.document
                and reply_msg.document.mime_type
                and (
                    reply_msg.document.mime_type.startswith("audio")
                    or reply_msg.document.mime_type.startswith("video")
                )
            )
        ):
            await send_message(
                message,
                "<b>❌ Error:</b> Please reply to an audio/video file to convert to voice message.",
            )
            return

        status_msg = await send_message(
            message, "<b>🔄 Processing:</b> Converting to voice message..."
        )

        # Download audio
        input_path = await download_file_from_message(message)
        if not input_path:
            await edit_message(
                status_msg, "<b>❌ Failed:</b> Could not download audio/video file."
            )
            return

        # Convert to voice
        output_path = f"{input_path}_voice.ogg"
        success, duration_info = await convert_audio_to_voice(
            input_path, output_path
        )

        if success and os.path.exists(output_path):
            # Send voice message
            await edit_message(
                status_msg, "<b>📤 Uploading:</b> Sending voice message..."
            )

            caption = "<b>🎵 Audio to Voice</b>\n\n<i>✅ Conversion completed successfully!</i>"
            if duration_info:
                caption += f"\n<i>📏 Duration: {duration_info}</i>"

            await TgClient.bot.send_voice(
                chat_id=message.chat.id,
                voice=output_path,
                caption=caption,
                reply_to_message_id=message.id,
            )
            await delete_message(status_msg)
        else:
            await edit_message(
                status_msg, "<b>❌ Failed:</b> Could not convert to voice message."
            )

        # Cleanup
        await aioremove(input_path)
        if os.path.exists(output_path):
            await aioremove(output_path)

    except Exception as e:
        LOGGER.error(f"Error in voice conversion: {e}")
        await send_message(message, f"❌ Error converting to voice: {e!s}")


async def handle_video_note_conversion(message: Message):
    """Handle video to video note conversion."""
    try:
        if not message.reply_to_message:
            await send_message(
                message,
                "<b>❌ Error:</b> Please reply to a video to convert to video note.",
            )
            return

        reply_msg = message.reply_to_message
        if not (
            reply_msg.video
            or reply_msg.video_note
            or reply_msg.animation  # GIFs can be converted to video notes
            or (
                reply_msg.document
                and reply_msg.document.mime_type
                and reply_msg.document.mime_type.startswith("video")
            )
        ):
            await send_message(
                message, "<b>❌ Error:</b> Please reply to a video file."
            )
            return

        # Video notes can be any duration according to Telegram API
        # No duration limit needed for video notes

        status_msg = await send_message(
            message, "<b>🔄 Processing:</b> Converting to video note..."
        )

        # Download video
        input_path = await download_file_from_message(message)
        if not input_path:
            await edit_message(
                status_msg, "<b>❌ Failed:</b> Could not download video file."
            )
            return

        # Convert to video note
        output_path = f"{input_path}_vnote.mp4"
        success = await convert_video_to_video_note(input_path, output_path)

        if success and os.path.exists(output_path):
            # Send video note
            await edit_message(
                status_msg, "<b>📤 Uploading:</b> Sending video note..."
            )

            try:
                # Get actual duration for proper video note metadata
                try:
                    final_duration, _, _ = await get_media_info(output_path)
                    duration = int(final_duration) if final_duration > 0 else None
                except Exception:
                    duration = None

                # Send as video note - Telegram should automatically apply circular mask
                send_kwargs = {
                    "chat_id": message.chat.id,
                    "video_note": output_path,
                    "reply_to_message_id": message.id,
                }

                if duration:
                    send_kwargs["duration"] = duration

                await TgClient.bot.send_video_note(**send_kwargs)
                await delete_message(status_msg)
            except Exception as e:
                await edit_message(
                    status_msg, f"<b>❌ Failed:</b> Could not send video note: {e!s}"
                )
        else:
            await edit_message(
                status_msg, "<b>❌ Failed:</b> Could not convert to video note."
            )

        # Cleanup
        await aioremove(input_path)
        if os.path.exists(output_path):
            await aioremove(output_path)

    except Exception as e:
        LOGGER.error(f"Error in video note conversion: {e}")
        await send_message(message, f"❌ Error converting to video note: {e!s}")


async def handle_background_removal(message: Message):
    """Handle background removal from image."""
    try:
        if not message.reply_to_message:
            await send_message(
                message, "❌ Please reply to an image to remove background."
            )
            return

        reply_msg = message.reply_to_message
        if not (
            reply_msg.photo
            or (
                reply_msg.document
                and reply_msg.document.mime_type.startswith("image")
            )
        ):
            await send_message(message, "❌ Please reply to an image file.")
            return

        status_msg = await send_message(message, "🔄 Removing background...")

        # Download image
        input_path = await download_file_from_message(message)
        if not input_path:
            await edit_message(status_msg, "❌ Failed to download image.")
            return

        # Remove background
        output_path = f"{input_path}_nobg.png"
        success = await remove_background_from_image(input_path, output_path)

        if success and os.path.exists(output_path):
            # Send processed image
            await edit_message(status_msg, "📤 Uploading processed image...")
            await TgClient.bot.send_photo(
                chat_id=message.chat.id,
                photo=output_path,
                caption="🖼️ Background removed",
                reply_to_message_id=message.id,
            )
            await delete_message(status_msg)
        else:
            await edit_message(status_msg, "❌ Failed to remove background.")

        # Cleanup
        await aioremove(input_path)
        if os.path.exists(output_path):
            await aioremove(output_path)

    except Exception as e:
        LOGGER.error(f"Error in background removal: {e}")
        await send_message(message, f"❌ Error removing background: {e!s}")


async def handle_face_enhancement(message: Message):
    """Handle face enhancement in image."""
    try:
        if not message.reply_to_message:
            await send_message(
                message, "❌ Please reply to an image to enhance facial features."
            )
            return

        reply_msg = message.reply_to_message
        if not (
            reply_msg.photo
            or (
                reply_msg.document
                and reply_msg.document.mime_type.startswith("image")
            )
        ):
            await send_message(message, "❌ Please reply to an image file.")
            return

        status_msg = await send_message(message, "🔄 Enhancing facial features...")

        # Download image
        input_path = await download_file_from_message(message)
        if not input_path:
            await edit_message(status_msg, "❌ Failed to download image.")
            return

        # Enhance face
        output_path = f"{input_path}_enhanced.jpg"
        success = await enhance_face_in_image(input_path, output_path)

        if success and os.path.exists(output_path):
            # Send enhanced image
            await edit_message(status_msg, "📤 Uploading enhanced image...")
            await TgClient.bot.send_photo(
                chat_id=message.chat.id,
                photo=output_path,
                caption="✨ Facial features enhanced",
                reply_to_message_id=message.id,
            )
            await delete_message(status_msg)
        else:
            await edit_message(status_msg, "❌ Failed to enhance facial features.")

        # Cleanup
        await aioremove(input_path)
        if os.path.exists(output_path):
            await aioremove(output_path)

    except Exception as e:
        LOGGER.error(f"Error in face enhancement: {e}")
        await send_message(message, f"❌ Error enhancing face: {e!s}")


async def handle_image_resize(message: Message):
    """Handle image resizing."""
    try:
        command_parts = message.text.split()

        # Check if specific dimensions are provided
        if len(command_parts) >= 4:
            try:
                width = int(command_parts[2])
                height = int(command_parts[3])
                await handle_custom_resize(message, width, height)
                return
            except ValueError:
                await send_message(
                    message,
                    "❌ Invalid dimensions. Use: /tool resImg <width> <height>",
                )
                return

        # Show resize menu
        if not message.reply_to_message:
            await send_message(message, "❌ Please reply to an image to resize.")
            return

        reply_msg = message.reply_to_message
        if not (
            reply_msg.photo
            or (
                reply_msg.document
                and reply_msg.document.mime_type.startswith("image")
            )
        ):
            await send_message(message, "❌ Please reply to an image file.")
            return

        # Store user data for callback
        user_id = message.from_user.id
        resize_user_data[user_id] = {"message": message, "reply_message": reply_msg}

        # Send resize menu
        menu = await create_resize_menu()
        menu_msg = await send_message(
            message,
            "📐 **Choose resize option:**\n\nSelect a preset size or use `/tool resImg <width> <height>` for custom dimensions.",
            menu,
        )

        # Auto-delete menu after 5 minutes
        await auto_delete_message(menu_msg, time=300)

    except Exception as e:
        LOGGER.error(f"Error in image resize: {e}")
        await send_message(message, f"❌ Error in resize: {e!s}")


async def handle_custom_resize(message: Message, width: int, height: int):
    """Handle custom image resize with specific dimensions."""
    try:
        if not message.reply_to_message:
            await send_message(message, "❌ Please reply to an image to resize.")
            return

        reply_msg = message.reply_to_message
        if not (
            reply_msg.photo
            or (
                reply_msg.document
                and reply_msg.document.mime_type.startswith("image")
            )
        ):
            await send_message(message, "❌ Please reply to an image file.")
            return

        status_msg = await send_message(
            message, f"🔄 Resizing image to {width}x{height}..."
        )

        # Download image
        input_path = await download_file_from_message(message)
        if not input_path:
            await edit_message(status_msg, "❌ Failed to download image.")
            return

        # Resize image
        output_path = f"{input_path}_resized.jpg"
        success = await resize_image(input_path, output_path, width, height)

        if success and os.path.exists(output_path):
            # Get file size
            file_size = get_readable_file_size(os.path.getsize(output_path))

            # Send resized image
            await edit_message(status_msg, "📤 Uploading resized image...")
            await TgClient.bot.send_photo(
                chat_id=message.chat.id,
                photo=output_path,
                caption=f"📐 Resized to {width}x{height} ({file_size})",
                reply_to_message_id=message.id,
            )
            await delete_message(status_msg)
        else:
            await edit_message(status_msg, "❌ Failed to resize image.")

        # Cleanup
        await aioremove(input_path)
        if os.path.exists(output_path):
            await aioremove(output_path)

    except Exception as e:
        LOGGER.error(f"Error in custom resize: {e}")
        await send_message(message, f"❌ Error resizing image: {e!s}")


async def handle_github_download(message: Message):
    """Handle GitHub repository download."""
    try:
        command_parts = message.text.split(maxsplit=2)

        if len(command_parts) < 2:
            await send_message(
                message,
                "❌ Please provide GitHub repository URL.\nUsage: `/tool <repository_url>`",
            )
            return

        # Get URL from command (could be in position 1 if it's the direct URL)
        repo_url = command_parts[1]

        # Ensure it's a valid GitHub URL (HTTP/HTTPS or SSH)
        if not repo_url.startswith(
            ("https://github.com/", "http://github.com/", "git@github.com:")
        ):
            if repo_url.startswith("github.com/"):
                repo_url = f"https://{repo_url}"
            else:
                await send_message(
                    message,
                    "<b>❌ Error:</b> Please provide a valid GitHub repository URL.\n\n"
                    "<b>📋 Supported formats:</b>\n"
                    "• <code>https://github.com/username/repository</code>\n"
                    "• <code>git@github.com:username/repository.git</code>",
                )
                return

        status_msg = await send_message(
            message, "<b>🔄 Processing:</b> Downloading GitHub repository..."
        )

        # Download repository
        temp_path = f"{DOWNLOAD_DIR}{message.from_user.id}_{int(time())}_repo.zip"
        success, repo_name = await download_github_repo(repo_url, temp_path)

        if success and os.path.exists(temp_path):
            # Get file size
            file_size = get_readable_file_size(os.path.getsize(temp_path))

            # Create final path with repo name
            final_path = (
                f"{DOWNLOAD_DIR}{message.from_user.id}_{int(time())}_{repo_name}.zip"
            )
            os.rename(temp_path, final_path)

            # Send ZIP file
            await edit_message(
                status_msg, "<b>📤 Uploading:</b> Sending repository file..."
            )
            await TgClient.bot.send_document(
                chat_id=message.chat.id,
                document=final_path,
                caption=f"<b>📦 Repository Downloaded</b>\n\n"
                f"<b>📁 Name:</b> <code>{repo_name}</code>\n"
                f"<b>💾 Size:</b> <code>{file_size}</code>\n"
                f"<b>🔗 Source:</b> <code>{repo_url}</code>",
                reply_to_message_id=message.id,
            )
            await delete_message(status_msg)

            # Clean up
            await aioremove(final_path)
        else:
            await edit_message(
                status_msg,
                "<b>❌ Download Failed</b>\n\n"
                "Please check the repository URL and try again.\n\n"
                "<b>📋 Supported formats:</b>\n"
                "• <code>https://github.com/username/repository</code>\n"
                "• <code>git@github.com:username/repository.git</code>",
            )

        # Cleanup temp file if it exists
        if os.path.exists(temp_path):
            await aioremove(temp_path)

    except Exception as e:
        LOGGER.error(f"Error in GitHub download: {e}")
        await send_message(message, f"❌ Error downloading repository: {e!s}")


async def handle_word_count(message: Message):
    """Handle word counting."""
    try:
        text = await get_text_from_message(message)
        if text is None:
            return

        word_count = count_words(text)

        result_text = "<b>📊 Word Count Result</b>\n\n"
        result_text += f"<b>📝 Words:</b> <code>{word_count:,}</code>\n"
        result_text += f"<b>🔤 Characters:</b> <code>{len(text):,}</code>\n"
        result_text += f"<b>🔤 Characters (no spaces):</b> <code>{len(text.replace(' ', '')):,}</code>\n"

        # Show preview of text if it's long
        if len(text) > 100:
            preview = text[:100] + "..."
            result_text += f"\n<b>📄 Text preview:</b>\n<code>{preview}</code>"
        else:
            result_text += f"\n<b>📄 Text:</b>\n<code>{text}</code>"

        await send_message(message, result_text)

    except Exception as e:
        LOGGER.error(f"Error in word count: {e}")
        await send_message(message, f"❌ Error counting words: {e!s}")


async def handle_char_count(message: Message):
    """Handle character counting."""
    try:
        text = await get_text_from_message(message)
        if text is None:
            return

        char_count = count_characters(text)
        char_count_no_spaces = len(text.replace(" ", ""))
        word_count = count_words(text)

        result_text = "<b>📊 Character Count Result</b>\n\n"
        result_text += f"<b>🔤 Characters:</b> <code>{char_count:,}</code>\n"
        result_text += f"<b>🔤 Characters (no spaces):</b> <code>{char_count_no_spaces:,}</code>\n"
        result_text += f"<b>📝 Words:</b> <code>{word_count:,}</code>\n"
        result_text += f"<b>📄 Lines:</b> <code>{text.count(chr(10)) + 1:,}</code>\n"

        # Show preview of text if it's long
        if len(text) > 100:
            preview = text[:100] + "..."
            result_text += f"\n<b>📄 Text preview:</b>\n<code>{preview}</code>"
        else:
            result_text += f"\n<b>📄 Text:</b>\n<code>{text}</code>"

        await send_message(message, result_text)

    except Exception as e:
        LOGGER.error(f"Error in character count: {e}")
        await send_message(message, f"❌ Error counting characters: {e!s}")


async def handle_text_reverse(message: Message):
    """Handle text reversal."""
    try:
        text = await get_text_from_message(message)
        if text is None:
            return

        reversed_text = reverse_text(text)

        result_text = "<b>🔄 Text Reversed</b>\n\n"
        result_text += f"<b>📝 Original:</b>\n<code>{text}</code>\n\n"
        result_text += f"<b>🔄 Reversed:</b>\n<code>{reversed_text}</code>"

        await send_message(message, result_text)

    except Exception as e:
        LOGGER.error(f"Error in text reverse: {e}")
        await send_message(message, f"❌ Error reversing text: {e!s}")


async def handle_sticker_pack_creation(message: Message):
    """Handle sticker pack creation from media with specified count."""
    try:
        # Parse command to get count
        command_parts = message.text.split()
        count = 10  # Default count for sticker packs

        # Check if a number is specified (e.g., "/tool stickerpack 5")
        if len(command_parts) >= 3 and command_parts[2].isdigit():
            count = int(command_parts[2])
            count = min(max(count, 1), 50)  # Limit between 1-50 for packs

        if not message.reply_to_message:
            await send_message(
                message,
                f"<b>❌ Error:</b> Please reply to a media file or text message.\n\n"
                f"<b>📝 Usage:</b> <code>/tool stickerpack {count}</code> (reply to media/text)",
            )
            return

        reply_msg = message.reply_to_message

        # Check if it's a text message
        if reply_msg.text:
            # Handle text sticker pack creation
            text_content = reply_msg.text
            status_msg = await send_message(
                message,
                f"<b>📦 Creating:</b> Generating {count} text stickers for pack...",
            )

            # Create multiple text stickers for the pack
            sticker_paths = []

            for i in range(count):
                output_path = (
                    f"downloads/pack_text_sticker_{int(time())}_{i + 1}.webp"
                )
                success = await create_text_sticker(text_content, output_path)

                if success and os.path.exists(output_path):
                    sticker_paths.append(output_path)

                # Update progress
                if (i + 1) % 5 == 0 or i == count - 1:
                    await edit_message(
                        status_msg,
                        f"<b>🎨 Processing:</b> Created {len(sticker_paths)}/{count} text stickers...",
                    )

            if not sticker_paths:
                await edit_message(
                    status_msg,
                    "<b>❌ Failed:</b> Could not create any text stickers.",
                )
                return

            # Try to create actual Telegram sticker pack
            await edit_message(
                status_msg,
                "<b>📦 Creating Pack:</b> Setting up Telegram sticker pack...",
            )

            try:
                # Generate unique pack name
                user_id = message.from_user.id
                pack_name = (
                    f"textpack_{user_id}_{int(time())}_by_{TgClient.bot.me.username}"
                )
                pack_title = f"{message.from_user.first_name}'s Text Pack ({len(sticker_paths)} stickers)"

                # Create sticker pack using Bot API

                # Create actual Telegram sticker pack
                success = await create_telegram_sticker_pack(
                    user_id=user_id,
                    pack_name=pack_name,
                    pack_title=pack_title,
                    sticker_paths=sticker_paths,
                    sticker_format="static",
                    emoji="📝",
                )

                if not success:
                    raise Exception("Failed to create text sticker pack")

                # Pack created successfully
                pack_link = f"https://t.me/addstickers/{pack_name}"

                # Send success message with pack button
                completion_text = "<b>🎨 Text Sticker Pack Created!</b>\n\n"
                completion_text += "<b>📦 Type:</b> 🖼️ Text Sticker Pack\n"
                completion_text += (
                    f"<b>📊 Count:</b> {len(sticker_paths)} stickers\n"
                )
                completion_text += f"<b>📝 Text:</b> {text_content[:30]}{'...' if len(text_content) > 30 else ''}\n"
                completion_text += "<b>✅ Status:</b> Pack ready to add!"

                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("➕ Add Sticker Pack", url=pack_link)]]
                )

                await TgClient.bot.send_message(
                    chat_id=message.chat.id,
                    text=completion_text,
                    reply_markup=keyboard,
                    reply_to_message_id=message.id,
                )

                await delete_message(status_msg)

                # Cleanup sticker files
                for sticker_path in sticker_paths:
                    with contextlib.suppress(Exception):
                        await aioremove(sticker_path)

                return

            except Exception as pack_error:
                LOGGER.error(f"Text pack creation failed: {pack_error}")
                LOGGER.error(f"Pack name: {pack_name}")
                LOGGER.error(f"Pack title: {pack_title}")
                LOGGER.error(f"Sticker count: {len(sticker_paths)}")
                # Fallback: send individual stickers
                await edit_message(
                    status_msg,
                    f"<b>📤 Uploading:</b> Sending {len(sticker_paths)} text stickers...",
                )

                sent_count = 0
                for sticker_path in sticker_paths:
                    try:
                        await TgClient.bot.send_sticker(
                            chat_id=message.chat.id,
                            sticker=sticker_path,
                            reply_to_message_id=message.id,
                        )
                        sent_count += 1
                        await asyncio.sleep(0.2)
                    except Exception:
                        continue
                    finally:
                        with contextlib.suppress(Exception):
                            await aioremove(sticker_path)

                await edit_message(
                    status_msg,
                    f"<b>✅ Complete:</b> {sent_count} text stickers sent! (Pack creation failed)",
                )
                return

        # Check if media is supported (including GIFs)
        elif not (
            reply_msg.photo
            or reply_msg.video
            or reply_msg.animation
            or reply_msg.sticker
            or reply_msg.video_note
            or (
                reply_msg.document
                and reply_msg.document.mime_type
                and (
                    reply_msg.document.mime_type.startswith("image")
                    or reply_msg.document.mime_type.startswith("video")
                    or reply_msg.document.mime_type == "image/gif"
                )
            )
        ):
            await send_message(
                message,
                "<b>❌ Error:</b> Please reply to a supported media type (image, video, GIF, sticker, text).",
            )
            return

        status_msg = await send_message(
            message, f"<b>📦 Creating:</b> Generating {count} stickers for pack..."
        )

        # Download the file
        input_path = await download_file_from_message(message)
        if not input_path:
            await edit_message(
                status_msg, "<b>❌ Failed:</b> Could not download file."
            )
            return

        # Determine media type (including GIFs)
        if (
            reply_msg.video
            or reply_msg.animation
            or reply_msg.video_note
            or (
                reply_msg.document
                and reply_msg.document.mime_type
                and (
                    reply_msg.document.mime_type.startswith("video")
                    or reply_msg.document.mime_type == "image/gif"
                )
            )
        ):
            media_type = "video"
        else:
            media_type = "image"

        # Create multiple stickers for the pack
        sticker_paths = []

        try:
            await edit_message(
                status_msg,
                f"<b>🎨 Processing:</b> Creating {count} sticker variations...",
            )

            for i in range(count):
                output_path = f"{input_path}_pack_{i + 1}.webp"

                if media_type == "video":
                    # Create animated stickers with different start times
                    success, _ = await create_sticker_pack_video(
                        input_path, output_path, i
                    )
                else:
                    # Create static stickers with different effects
                    success = await create_sticker_pack_image(
                        input_path, output_path, i
                    )

                if success and os.path.exists(output_path):
                    sticker_paths.append(output_path)

                # Update progress
                if (i + 1) % 5 == 0 or i == count - 1:
                    await edit_message(
                        status_msg,
                        f"<b>🎨 Processing:</b> Created {len(sticker_paths)}/{count} stickers...",
                    )
        finally:
            # Cleanup input file
            await aioremove(input_path)

        if not sticker_paths:
            await edit_message(
                status_msg, "<b>❌ Failed:</b> Could not create any stickers."
            )
            return

        # Try to create actual Telegram sticker pack
        await edit_message(
            status_msg, "<b>� Creating Pack:</b> Setting up Telegram sticker pack..."
        )

        try:
            # Generate unique pack name
            user_id = message.from_user.id
            pack_name = (
                f"mediapack_{user_id}_{int(time())}_by_{TgClient.bot.me.username}"
            )
            pack_type = "🎬 Animated" if media_type == "video" else "🖼️ Static"
            pack_title = f"{message.from_user.first_name}'s {pack_type} Pack ({len(sticker_paths)} stickers)"

            # Create actual Telegram sticker pack
            sticker_format = "video" if media_type == "video" else "static"
            emoji = "🎬" if media_type == "video" else "🖼️"

            success = await create_telegram_sticker_pack(
                user_id=user_id,
                pack_name=pack_name,
                pack_title=pack_title,
                sticker_paths=sticker_paths,
                sticker_format=sticker_format,
                emoji=emoji,
            )

            if not success:
                raise Exception("Failed to create sticker pack")

            # Pack created successfully
            pack_link = f"https://t.me/addstickers/{pack_name}"

            # Send success message with pack button
            completion_text = f"<b>🎨 {pack_type} Sticker Pack Created!</b>\n\n"
            completion_text += f"<b>📦 Type:</b> {pack_type} Sticker Pack\n"
            completion_text += f"<b>📊 Count:</b> {len(sticker_paths)} stickers\n"
            completion_text += "<b>✅ Status:</b> Pack ready to add!"

            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("+ Add Sticker Pack", url=pack_link)]]
            )

            await TgClient.bot.send_message(
                chat_id=message.chat.id,
                text=completion_text,
                reply_markup=keyboard,
                reply_to_message_id=message.id,
            )

            await delete_message(status_msg)

            # Cleanup sticker files
            for sticker_path in sticker_paths:
                with contextlib.suppress(Exception):
                    await aioremove(sticker_path)

        except Exception as pack_error:
            LOGGER.error(f"Media pack creation failed: {pack_error}")
            LOGGER.error(f"Pack name: {pack_name}")
            LOGGER.error(f"Pack title: {pack_title}")
            LOGGER.error(f"Media type: {media_type}")
            LOGGER.error(f"Sticker count: {len(sticker_paths)}")
            # Fallback: send individual stickers
            await edit_message(
                status_msg,
                f"<b>📤 Uploading:</b> Sending {len(sticker_paths)} stickers...",
            )

            sent_count = 0
            for sticker_path in sticker_paths:
                try:
                    await TgClient.bot.send_sticker(
                        chat_id=message.chat.id,
                        sticker=sticker_path,
                        reply_to_message_id=message.id,
                    )
                    sent_count += 1
                    await asyncio.sleep(0.2)
                except Exception:
                    continue
                finally:
                    with contextlib.suppress(Exception):
                        await aioremove(sticker_path)

            # Send fallback completion message
            pack_type = "🎬 Animated" if media_type == "video" else "🖼️ Static"
            completion_text = f"<b>🎨 {pack_type} Stickers Created!</b>\n\n"
            completion_text += f"<b>📦 Type:</b> {pack_type} Stickers\n"
            completion_text += f"<b>📊 Count:</b> {sent_count} stickers sent\n"
            completion_text += "<b>✅ Status:</b> Stickers ready!\n\n"
            completion_text += "<b>💡 To create official pack:</b>\n"
            completion_text += "1. Go to @Stickers bot\n"
            completion_text += "2. Use /newpack command\n"
            completion_text += f"3. Upload these {sent_count} stickers\n"
            completion_text += "4. Set emojis and publish your pack"

            await TgClient.bot.send_message(
                chat_id=message.chat.id,
                text=completion_text,
                reply_to_message_id=message.id,
            )

            await delete_message(status_msg)

    except Exception as e:
        LOGGER.error(f"Error in sticker pack creation: {e}")
        await send_message(message, f"❌ Error creating sticker pack: {e!s}")


async def handle_calculator(message: Message):
    """Handle mathematical calculations."""
    try:
        command_parts = message.text.split(maxsplit=2)

        if len(command_parts) < 3:
            await send_message(
                message,
                "<b>❌ Error:</b> Please provide a mathematical expression.\n\n"
                "<b>📝 Usage:</b> <code>/tool cal &lt;expression&gt;</code>\n\n"
                "<b>🧮 Examples:</b>\n"
                "• <code>/tool cal 2 + 2</code>\n"
                "• <code>/tool cal 15 * 8 / 4</code>\n"
                "• <code>/tool cal sqrt16 + 3^2</code> (auto-converts to sqrt(16))\n"
                "• <code>/tool cal sin60 * cos30</code> (auto-converts degrees)\n"
                "• <code>/tool cal log100 + factorial5</code>\n\n"
                "<b>🔢 Operators:</b> <code>+ - * / ^ ( )</code>\n"
                "<b>📐 Functions:</b> <code>sin cos tan sqrt log exp factorial</code>\n"
                "<b>📊 Constants:</b> <code>pi e</code>\n"
                "<b>💡 Smart Features:</b>\n"
                "• Auto-adds parentheses: <code>sin60</code> → <code>sin(60)</code>\n"
                "• Degree conversion: <code>sin60</code> → <code>sin(pi/3)</code>\n"
                "• Common angles: 30°, 45°, 60°, 90° use exact values",
            )
            return

        expression = command_parts[2].strip()

        if not expression:
            await send_message(
                message, "<b>❌ Error:</b> Empty expression provided."
            )
            return

        # Calculate the result
        result = calculate_expression(expression)

        # Format the response
        response_text = "<b>🧮 Calculator Result</b>\n\n"
        response_text += f"<b>📝 Expression:</b>\n<code>{expression}</code>\n\n"
        response_text += f"<b>🔢 Result:</b>\n<code>{result}</code>"

        # Add some helpful info for certain results
        if result.startswith("❌"):
            response_text += (
                "\n\n<b>💡 Tip:</b> Check your expression syntax and try again."
            )
        elif "." in result and not result.startswith("❌"):
            try:
                float_result = float(result)
                if abs(float_result) > 1000000:
                    response_text += (
                        f"\n\n<b>📊 Scientific:</b> <code>{float_result:.2e}</code>"
                    )
            except:
                pass

        await send_message(message, response_text)

    except Exception as e:
        LOGGER.error(f"Error in calculator: {e}")
        await send_message(message, f"❌ Error in calculation: {e!s}")


@new_task
async def handle_resize_callback(client, query):
    """Handle resize menu callback."""
    try:
        user_id = query.from_user.id
        data = query.data

        if data == "resize_cancel":
            await query.answer("❌ Resize cancelled")
            await delete_message(query.message)
            resize_user_data.pop(user_id, None)
            return

        if user_id not in resize_user_data:
            await query.answer("❌ Session expired. Please try again.")
            await delete_message(query.message)
            return

        # Extract preset number
        preset_num = data.split("_")[1]
        if preset_num not in RESIZE_PRESETS:
            await query.answer("❌ Invalid preset")
            return

        preset = RESIZE_PRESETS[preset_num]
        width = preset["width"]
        height = preset["height"]

        await query.answer(f"📐 Resizing to {preset['name']} ({width}x{height})")
        await delete_message(query.message)

        # Get stored message data
        user_data_entry = resize_user_data[user_id]
        message = user_data_entry["message"]

        # Perform resize
        await handle_custom_resize(message, width, height)

        # Cleanup
        resize_user_data.pop(user_id, None)

    except Exception as e:
        LOGGER.error(f"Error in resize callback: {e}")
        await query.answer("❌ Error processing resize")


# Register handlers
def register_tool_handlers():
    """Register tool command handlers."""
    # Register tool command handler
    TgClient.bot.add_handler(
        MessageHandler(
            tool_command,
            filters=filters.command(BotCommands.ToolCommand)
            & CustomFilters.authorized,
        )
    )

    # Register resize callback handler
    TgClient.bot.add_handler(
        CallbackQueryHandler(
            handle_resize_callback, filters=filters.regex(r"^resize_")
        )
    )


# Initialize handlers when module is imported
register_tool_handlers()
