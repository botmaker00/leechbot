"""
Trace.moe module for anime scene identification
Supports images, videos, GIFs, and URLs with multi-language anime title display
"""

import asyncio
import logging
import os
import re
import tempfile

from aiohttp import ClientSession, ClientTimeout
from pyrogram.types import Message

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import is_privileged_user
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)

# Module logger
TRACE_LOGGER = logging.getLogger(__name__)

# Constants
TRACE_MOE_API_URL = "https://api.trace.moe/search"
TRACE_MOE_TIMEOUT = 30
MAX_RETRIES = 5
RETRY_DELAY = 2

# Supported media types for trace.moe
SUPPORTED_MEDIA_TYPES = ["image", "video", "animated_image"]
SUPPORTED_EXTENSIONS = {
    "image": [".jpg", ".jpeg", ".png", ".webp", ".bmp"],
    "video": [".mp4", ".mkv", ".avi", ".mov", ".webm", ".gif"],
    "animated_image": [".gif", ".webp"],
}


class TraceMoeError(Exception):
    """Custom exception for trace.moe related errors"""


class TraceMoeClient:
    """Async client for trace.moe API"""

    def __init__(self):
        self.api_key = Config.TRACE_MOE_API_KEY
        self.timeout = ClientTimeout(total=TRACE_MOE_TIMEOUT)

    async def search_anime_by_url(
        self, image_url: str, cut_borders: bool = True
    ) -> dict:
        """
        Search anime using trace.moe API with image URL

        Args:
            image_url: URL of the image to search
            cut_borders: Whether to cut borders for better accuracy

        Returns:
            dict: Search result from trace.moe API

        Raises:
            TraceMoeError: If API request fails
        """
        params = {
            "anilistInfo": "1",
            "url": image_url,
        }

        if cut_borders:
            params["cutBorders"] = "1"

        headers = {}
        if self.api_key:
            headers["x-trace-key"] = self.api_key

        return await self._make_request("GET", params=params, headers=headers)

    async def search_anime_by_file(
        self, file_path: str, cut_borders: bool = True
    ) -> dict:
        """
        Search anime using trace.moe API with direct file upload

        Args:
            file_path: Path to the image/video file to search
            cut_borders: Whether to cut borders for better accuracy

        Returns:
            dict: Search result from trace.moe API

        Raises:
            TraceMoeError: If API request fails
        """
        params = {
            "anilistInfo": "1",
        }

        if cut_borders:
            params["cutBorders"] = "1"

        headers = {}
        if self.api_key:
            headers["x-trace-key"] = self.api_key

        # Read file content
        try:
            with open(file_path, "rb") as f:
                file_data = f.read()
        except Exception as e:
            raise TraceMoeError(f"Failed to read file: {e!s}")

        return await self._make_request(
            "POST", params=params, headers=headers, data=file_data
        )

    async def _make_request(
        self,
        method: str,
        params: dict | None = None,
        headers: dict | None = None,
        data: bytes | None = None,
    ) -> dict:
        """
        Make HTTP request to trace.moe API with retry logic

        Args:
            method: HTTP method (GET or POST)
            params: Query parameters
            headers: HTTP headers
            data: File data for POST requests

        Returns:
            dict: API response

        Raises:
            TraceMoeError: If request fails
        """

        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                async with ClientSession(timeout=self.timeout) as session:
                    if method == "GET":
                        async with session.get(
                            TRACE_MOE_API_URL, params=params, headers=headers
                        ) as response:
                            return await self._handle_response(response, retry_count)
                    else:  # POST
                        # Set content type for binary data
                        if headers is None:
                            headers = {}
                        headers["Content-Type"] = "application/octet-stream"

                        async with session.post(
                            TRACE_MOE_API_URL,
                            params=params,
                            headers=headers,
                            data=data,
                        ) as response:
                            return await self._handle_response(response, retry_count)

            except TimeoutError:
                if retry_count < MAX_RETRIES - 1:
                    retry_count += 1
                    await asyncio.sleep(RETRY_DELAY * retry_count)
                    continue
                raise TraceMoeError("Request timeout. Please try again later.")

            except Exception as e:
                if retry_count < MAX_RETRIES - 1:
                    retry_count += 1
                    await asyncio.sleep(RETRY_DELAY * retry_count)
                    continue
                raise TraceMoeError(f"Network error: {e!s}")

        raise TraceMoeError("Maximum retries exceeded.")

    async def _handle_response(self, response, retry_count: int) -> dict:
        """Handle API response with proper error handling"""
        # Handle rate limiting and server errors with retry
        if response.status in [503, 402] and retry_count < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
            raise Exception("Retry needed")  # Will be caught by outer try-catch

        # Handle specific error codes
        if response.status == 429:
            raise TraceMoeError("Rate limit exceeded. Please try again later.")
        if response.status == 413:
            raise TraceMoeError("File too large. Maximum size is 25MB.")
        if response.status == 403:
            raise TraceMoeError("Invalid API key.")
        if response.status == 400:
            raise TraceMoeError("Invalid image or request format.")
        if response.status in [502, 503, 504]:
            raise TraceMoeError("trace.moe server is busy. Please try again later.")
        if response.status >= 400:
            raise TraceMoeError(f"API error: HTTP {response.status}")

        # Parse JSON response
        try:
            result = await response.json()
        except Exception:
            raise TraceMoeError("Invalid response format from trace.moe API.")

        # Check for API errors
        if result.get("error"):
            raise TraceMoeError(f"API error: {result['error']}")

        # Check for empty results
        if not result.get("result") or len(result["result"]) == 0:
            raise TraceMoeError("No anime found for this image.")

        return result


def format_time(seconds: float) -> str:
    """Format time in seconds to MM:SS format"""
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"


def format_anime_result(result: dict) -> tuple[str, str | None, bool]:
    """
    Format trace.moe search result into beautiful HTML text

    Args:
        result: Search result from trace.moe API

    Returns:
        tuple: (formatted_text, video_url, is_adult)
    """
    if not result.get("result") or len(result["result"]) == 0:
        return (
            "<blockquote>❌ <b>No anime found</b>\n\n"
            "The image doesn't match any anime in the database. "
            "Try a clearer screenshot or different frame.</blockquote>",
            None,
            False,
        )

    match = result["result"][0]
    anilist = match.get("anilist", {})

    # Extract anime titles in different languages
    title_info = anilist.get("title", {})
    native = title_info.get("native", "")
    chinese = title_info.get("chinese", "")
    romaji = title_info.get("romaji", "")
    english = title_info.get("english", "")

    # Deduplicate titles (case-insensitive)
    titles = []
    seen_titles = set()

    for title in [native, chinese, romaji, english]:
        if title and title.lower() not in seen_titles:
            titles.append(title)
            seen_titles.add(title.lower())

    # Get additional info
    filename = match.get("filename", "Unknown")
    from_time = match.get("from", 0)
    similarity = match.get("similarity", 0)
    episode = match.get("episode")

    # Determine similarity emoji and status based on trace.moe official guidelines
    # According to trace.moe docs: "Similarity lower than 90% are most likely incorrect results"
    if similarity >= 0.95:
        sim_emoji = "🎯"
        sim_status = "Excellent"
    elif similarity >= 0.9:
        sim_emoji = "✅"
        sim_status = "Good"
    elif similarity >= 0.8:
        sim_emoji = "⚠️"
        sim_status = "Likely Incorrect"
    elif similarity >= 0.7:
        sim_emoji = "❌"
        sim_status = "Probably Wrong"
    else:
        sim_emoji = "🚫"
        sim_status = "Almost Certainly Wrong"

    # Format the beautiful response
    formatted_parts = []

    # Header with anime icon
    formatted_parts.append("🎌 <b>Anime Identified</b>")
    formatted_parts.append("")

    # Anime titles section
    if titles:
        formatted_parts.append("📺 <b>Titles:</b>")
        for i, title in enumerate(titles):
            if i == 0:
                # Primary title (usually native)
                formatted_parts.append(f"   🔸 <b>{title}</b>")
            else:
                # Alternative titles
                formatted_parts.append(f"   ▫️ <i>{title}</i>")
    else:
        formatted_parts.append("📺 <b>Title:</b> <i>Unknown Anime</i>")

    formatted_parts.append("")

    # Episode and file info
    formatted_parts.append("📁 <b>Source Info:</b>")
    if episode:
        formatted_parts.append(f"   📺 Episode: <code>{episode}</code>")
    formatted_parts.append(f"   📄 File: <code>{filename}</code>")
    formatted_parts.append(f"   ⏰ Time: <code>{format_time(from_time)}</code>")

    formatted_parts.append("")

    # Accuracy section
    formatted_parts.append("🎯 <b>Match Accuracy:</b>")
    formatted_parts.append(
        f"   {sim_emoji} <b>{similarity * 100:.1f}%</b> ({sim_status})"
    )

    # Add confidence warnings based on trace.moe official guidelines
    if similarity < 0.9:
        formatted_parts.append("")
        if similarity >= 0.8:
            formatted_parts.append(
                "⚠️ <b>Warning:</b> <i>Below 90% - likely incorrect result</i>"
            )
            formatted_parts.append(
                "💡 <i>According to trace.moe: results under 90% are usually wrong</i>"
            )
        elif similarity >= 0.7:
            formatted_parts.append(
                "❌ <b>Caution:</b> <i>Very low confidence - probably wrong</i>"
            )
            formatted_parts.append(
                "🔍 <i>Try a clearer image or different frame</i>"
            )
        else:
            formatted_parts.append(
                "🚫 <b>Unreliable:</b> <i>Extremely low confidence</i>"
            )
            formatted_parts.append(
                "❓ <i>This result is almost certainly incorrect</i>"
            )

    formatted_text = "\n".join(formatted_parts)

    # Get video URL if available
    video_url = match.get("video")
    if video_url:
        video_url = f"{video_url}&size=l"

    # Check if content is adult
    is_adult = anilist.get("isAdult", False)

    return formatted_text, video_url, is_adult


async def get_media_for_trace(
    message: Message,
) -> tuple[str | None, str | None, bool]:
    """
    Get media from message for trace.moe processing

    Args:
        message: Telegram message object

    Returns:
        tuple: (file_path_or_url, media_type, is_url)
               - file_path_or_url: Local file path or URL
               - media_type: Type of media
               - is_url: True if it's a URL, False if it's a local file
    """
    # Check if message contains a URL to an image
    if message.text:
        # Look for image URLs in the text
        url_pattern = (
            r"https?://[^\s]+\.(?:jpg|jpeg|png|gif|webp|bmp|mp4|mkv|avi|mov|webm)"
        )
        urls = re.findall(url_pattern, message.text, re.IGNORECASE)

        if urls:
            # Return the first found URL for direct API usage
            image_url = urls[0]
            url_lower = image_url.lower()
            if any(
                ext in url_lower
                for ext in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]
            ):
                media_type = "image"
            elif any(ext in url_lower for ext in [".gif"]):
                media_type = "animated_image"
            elif any(
                ext in url_lower for ext in [".mp4", ".mkv", ".avi", ".mov", ".webm"]
            ):
                media_type = "video"
            else:
                media_type = "image"

            return image_url, media_type, True

    # Check for photo
    if message.photo:
        try:
            # Download photo to temporary file
            with tempfile.NamedTemporaryFile(
                suffix=".jpg", delete=False
            ) as temp_file:
                await message.download(file_name=temp_file.name)
                return temp_file.name, "image", False
        except Exception as e:
            TRACE_LOGGER.error(f"Failed to download photo: {e}")
            return None, None, False

    # Check for document (images, videos, GIFs)
    if message.document:
        doc = message.document
        file_name = doc.file_name or ""
        file_ext = os.path.splitext(file_name)[1].lower()

        # Check if it's a supported format
        for media_type, extensions in SUPPORTED_EXTENSIONS.items():
            if file_ext in extensions:
                # Check file size (trace.moe has limits)
                if doc.file_size > Config.TRACE_MOE_MAX_FILE_SIZE:
                    return (
                        None,
                        f"file_too_large:{get_readable_file_size(doc.file_size)}",
                        False,
                    )

                try:
                    # Download document to temporary file
                    with tempfile.NamedTemporaryFile(
                        suffix=file_ext, delete=False
                    ) as temp_file:
                        await message.download(file_name=temp_file.name)
                        return temp_file.name, media_type, False
                except Exception as e:
                    TRACE_LOGGER.error(f"Failed to download document: {e}")
                    return None, None, False

    # Check for video
    if message.video:
        video = message.video
        if video.file_size > Config.TRACE_MOE_MAX_FILE_SIZE:
            return (
                None,
                f"file_too_large:{get_readable_file_size(video.file_size)}",
                False,
            )

        try:
            # Download video to temporary file
            with tempfile.NamedTemporaryFile(
                suffix=".mp4", delete=False
            ) as temp_file:
                await message.download(file_name=temp_file.name)
                return temp_file.name, "video", False
        except Exception as e:
            TRACE_LOGGER.error(f"Failed to download video: {e}")
            return None, None, False

    # Check for animation (GIF)
    if message.animation:
        animation = message.animation
        if animation.file_size > Config.TRACE_MOE_MAX_FILE_SIZE:
            return (
                None,
                f"file_too_large:{get_readable_file_size(animation.file_size)}",
                False,
            )

        try:
            # Download animation to temporary file
            with tempfile.NamedTemporaryFile(
                suffix=".gif", delete=False
            ) as temp_file:
                await message.download(file_name=temp_file.name)
                return temp_file.name, "animated_image", False
        except Exception as e:
            TRACE_LOGGER.error(f"Failed to download animation: {e}")
            return None, None, False

    return None, None, False


async def trace_command(client, message: Message):
    """
    Handle /trace command for anime scene identification

    Args:
        client: Telegram client
        message: Message object
    """
    if not Config.TRACE_MOE_ENABLED:
        await send_message(
            message,
            "<blockquote>🚫 <b>Service Unavailable</b>\n\n"
            "Trace.moe anime identification is currently disabled. "
            "Please contact the administrator.</blockquote>",
        )
        return

    user_id = message.from_user.id

    # Check if user is authorized
    if not is_privileged_user(user_id):
        await send_message(
            message,
            "<blockquote>🔐 <b>Access Denied</b>\n\n"
            "You need authorization to use the anime identification feature. "
            "Please contact an administrator to get access.</blockquote>",
        )
        return

    # Get the message to process (reply or current)
    target_message = (
        message.reply_to_message if message.reply_to_message else message
    )

    # Get media from message
    file_path_or_url, media_type, is_url = await get_media_for_trace(target_message)

    if not file_path_or_url:
        if media_type and media_type.startswith("file_too_large:"):
            size = media_type.split(":", 1)[1]
            error_msg = await send_message(
                message,
                f"<blockquote>📏 <b>File Size Limit Exceeded</b>\n\n"
                f"📊 <b>Your file:</b> <code>{size}</code>\n"
                f"📋 <b>Maximum allowed:</b> <code>{get_readable_file_size(Config.TRACE_MOE_MAX_FILE_SIZE)}</code>\n\n"
                f"💡 <b>Tip:</b> Compress your file or try a smaller image/video.</blockquote>",
            )
        else:
            error_msg = await send_message(
                message,
                "<blockquote>🔍 <b>No Media Found</b>\n\n"
                "Please send or reply to supported media:\n\n"
                "📸 <b>Images:</b> JPG, PNG, WebP, BMP\n"
                "🎥 <b>Videos:</b> MP4, MKV, AVI, MOV, WebM\n"
                "🎞️ <b>Animations:</b> GIF, animated WebP\n"
                "🔗 <b>URLs:</b> Direct links to media files\n\n"
                "💡 <b>Tip:</b> Use clear anime screenshots for best results!</blockquote>",
            )
        await auto_delete_message(error_msg, time=10)
        return

    # Send processing message
    status_msg = await send_message(
        message,
        "<blockquote>🔍 <b>Analyzing Anime Scene...</b>\n\n"
        "🤖 Processing your media through trace.moe AI\n"
        "⏳ This may take a few seconds...\n\n"
        "🎯 Searching through millions of anime frames!</blockquote>",
    )

    try:
        # Initialize trace.moe client
        client_trace = TraceMoeClient()

        # Search anime using appropriate method
        if is_url:
            result = await client_trace.search_anime_by_url(
                file_path_or_url, cut_borders=Config.TRACE_MOE_CUT_BORDERS
            )
        else:
            result = await client_trace.search_anime_by_file(
                file_path_or_url, cut_borders=Config.TRACE_MOE_CUT_BORDERS
            )

        # Format result
        formatted_text, video_url, is_adult = format_anime_result(result)

        # Delete status message
        await delete_message(status_msg)

        # Check for adult content in groups
        if is_adult and message.chat.type in ["group", "supergroup"]:
            await send_message(
                target_message,
                "<blockquote>🔞 <b>Adult Content Detected</b>\n\n"
                "🚫 This anime contains adult content and cannot be displayed in groups.\n\n"
                "💬 <b>To see results:</b> Forward this media to me in a private chat.\n\n"
                "🔒 <b>Privacy:</b> Results will only be shown privately.</blockquote>",
            )
            return

        # Check if result has very low confidence and add extra warning
        similarity = result["result"][0].get("similarity", 0)
        if similarity < 0.8:
            # Prepend a strong warning for very unreliable results
            warning_header = (
                "<blockquote>⚠️ <b>UNRELIABLE RESULT WARNING</b>\n\n"
                f"🎯 <b>Confidence:</b> {similarity * 100:.1f}%\n"
                "❌ <b>Status:</b> Likely incorrect (trace.moe recommends 90%+ for accuracy)\n\n"
                "🔍 <b>This result is probably wrong.</b> Consider:\n"
                "• Using a clearer, unedited screenshot\n"
                "• Trying a different frame from the scene\n"
                "• Checking if this is actually from an anime\n\n"
                "📋 <b>Showing result anyway for reference:</b></blockquote>\n\n"
            )
            formatted_text = warning_header + formatted_text

        # Send result with video preview if available
        if (
            video_url
            and Config.TRACE_MOE_VIDEO_PREVIEW
            and not Config.TRACE_MOE_SKIP_PREVIEW
        ):
            try:
                # Add mute parameter if configured
                if Config.TRACE_MOE_MUTE_PREVIEW:
                    video_url += "&mute"

                # Try to send video preview
                await client.send_video(
                    chat_id=message.chat.id,
                    video=video_url,
                    caption=formatted_text,
                    reply_to_message_id=target_message.id,
                )
                return

            except Exception as e:
                TRACE_LOGGER.warning(f"Failed to send video preview: {e}")
                # Fall back to text message

        # Send text result
        await send_message(target_message, formatted_text)

    except TraceMoeError as e:
        await delete_message(status_msg)

        # Format error message based on error type
        error_text = str(e)
        if "Rate limit exceeded" in error_text:
            formatted_error = (
                "<blockquote>⏰ <b>Rate Limit Reached</b>\n\n"
                "🚫 Too many requests to trace.moe API\n"
                "⏳ Please wait a few minutes and try again\n\n"
                "💡 <b>Tip:</b> Consider getting a trace.moe API key for higher limits</blockquote>"
            )
        elif "File too large" in error_text:
            formatted_error = (
                "<blockquote>📏 <b>File Size Error</b>\n\n"
                "🚫 Your file exceeds the 25MB limit\n"
                "💡 <b>Solution:</b> Compress your file or use a smaller image\n\n"
                "📋 <b>Supported:</b> Up to 25MB for images/videos</blockquote>"
            )
        elif "No anime found" in error_text:
            formatted_error = (
                "<blockquote>🔍 <b>No Match Found</b>\n\n"
                "❓ This image doesn't match any anime in the database\n\n"
                "💡 <b>Tips for better results:</b>\n"
                "• Use clear, unedited screenshots\n"
                "• Avoid heavily compressed images\n"
                "• Try different frames from the same scene\n"
                "• Make sure it's from an actual anime (not fan art)</blockquote>"
            )
        elif "server is busy" in error_text.lower():
            formatted_error = (
                "<blockquote>🔧 <b>Server Busy</b>\n\n"
                "⚠️ trace.moe servers are currently overloaded\n"
                "⏳ Please try again in a few minutes\n\n"
                "📊 <b>Status:</b> High traffic detected</blockquote>"
            )
        else:
            formatted_error = (
                f"<blockquote>❌ <b>Search Failed</b>\n\n"
                f"🔧 <b>Error:</b> {error_text}\n\n"
                f"💡 <b>Try:</b> Different image or wait a moment</blockquote>"
            )

        error_msg = await send_message(message, formatted_error)
        await auto_delete_message(error_msg, time=15)

    except Exception as e:
        await delete_message(status_msg)
        TRACE_LOGGER.error(f"Unexpected error in trace command: {e}")
        error_msg = await send_message(
            message,
            "<blockquote>💥 <b>Unexpected Error</b>\n\n"
            "🔧 Something went wrong while processing your request\n"
            "⏳ Please try again in a moment\n\n"
            "📞 <b>If this persists:</b> Contact the administrator</blockquote>",
        )
        await auto_delete_message(error_msg, time=10)

    finally:
        # Clean up temporary file (only if it's a local file, not a URL)
        if not is_url and file_path_or_url and os.path.exists(file_path_or_url):
            try:
                os.unlink(file_path_or_url)
            except Exception as e:
                TRACE_LOGGER.warning(
                    f"Failed to delete temporary file {file_path_or_url}: {e}"
                )
