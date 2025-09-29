"""
File processing utilities for File2Link functionality
"""

from datetime import datetime as dt
from typing import Any

from pyrogram.client import Client
from pyrogram.file_id import FileId
from pyrogram.types import Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.helper.ext_utils.status_utils import get_readable_file_size


def get_media(message: Message) -> Any | None:
    """Extract media object from message"""
    for attr in (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    ):
        media = getattr(message, attr, None)
        if media:
            return media
    return None


def get_uniqid(message: Message) -> str | None:
    """Get unique file ID from message"""
    media = get_media(message)
    return getattr(media, "file_unique_id", None)


def get_hash(media_msg: Message) -> str:
    """Generate secure hash from file unique ID"""
    uniq_id = get_uniqid(media_msg)
    return uniq_id[:6] if uniq_id else ""


def get_fsize(message: Message) -> int:
    """Get file size from message"""
    media = get_media(message)
    return getattr(media, "file_size", 0) if media else 0


def get_fname(msg: Message) -> str:
    """Get filename with fallback generation"""
    media = get_media(msg)
    fname = None

    if media:
        fname = getattr(media, "file_name", None)

    if not fname:
        if msg.media:
            media_type_value = msg.media.value
            if media_type_value:
                str(media_type_value)

        ext = "bin"
        if media and hasattr(media, "_file_type"):
            file_type = media._file_type
            if file_type == "photo":
                ext = "jpg"
            elif file_type == "audio":
                ext = "mp3"
            elif file_type == "voice":
                ext = "ogg"
            elif file_type in ["video", "animation", "video_note"]:
                ext = "mp4"
            elif file_type == "sticker":
                ext = "webp"
            else:
                ext = "bin"
        timestamp = dt.now().strftime("%Y%m%d%H%M%S")
        fname = f"File2Link_{timestamp}.{ext}"

    return fname


def parse_fid(message: Message) -> FileId | None:
    """Parse file ID from message"""
    media = get_media(message)
    if media and hasattr(media, "file_id"):
        try:
            return FileId.decode(media.file_id)
        except Exception:
            return None
    return None


def get_file_info(message: Message) -> dict[str, Any]:
    """Get comprehensive file information"""
    media = get_media(message)
    if not media:
        return {"message_id": message.id, "error": "No media"}

    return {
        "message_id": message.id,
        "file_size": getattr(media, "file_size", 0) or 0,
        "file_name": get_fname(message),
        "mime_type": getattr(media, "mime_type", None),
        "unique_id": getattr(media, "file_unique_id", None),
        "media_type": type(media).__name__.lower(),
        "hash": get_hash(message),
        "duration": getattr(media, "duration", None),
        "width": getattr(media, "width", None),
        "height": getattr(media, "height", None),
    }


async def get_file_from_storage(
    client: Client, chat_id: int, message_id: int
) -> Message | None:
    """Get file message from storage channel"""
    try:
        msg = await client.get_messages(chat_id, message_id)

        if not msg or getattr(msg, "empty", False):
            LOGGER.error(f"Message {message_id} not found in storage")
            return None

        media = get_media(msg)
        if not media:
            LOGGER.error(f"No media found in message {message_id}")
            return None

        return msg

    except Exception as e:
        LOGGER.error(f"Error getting file from storage: {e}")
        return None


def get_max_file_size() -> int:
    """Get maximum file size based on user session and transmission settings"""
    try:
        # Use TgClient's MAX_SPLIT_SIZE which is already set based on premium status
        # This automatically switches between 2GB (non-premium) and 4GB (premium)
        return TgClient.MAX_SPLIT_SIZE
    except Exception as e:
        LOGGER.error(f"Error getting max file size: {e}")
        # Fallback to 2GB for non-premium
        return 2097152000


def validate_media_type(message: Message) -> tuple[bool, str]:
    """
    Validate if message contains supported media type and size

    Returns:
        tuple: (is_valid, error_message)
    """
    media = get_media(message)
    if not media:
        return False, "No media found in message"

    # Check file size limit based on user session
    file_size = get_fsize(message)
    max_size = get_max_file_size()

    if file_size > max_size:
        max_size_hr = get_readable_file_size(max_size)
        file_size_hr = get_readable_file_size(file_size)
        premium_status = "premium" if TgClient.IS_PREMIUM_USER else "non-premium"

        error_msg = (
            f"File size {file_size_hr} exceeds {max_size_hr} limit "
            f"({premium_status} account)"
        )
        return False, error_msg

    return True, ""


def validate_file2link_media(message: Message) -> tuple[bool, str]:
    """
    Validate media for File2Link functionality (no file size limit)
    File2Link only copies files to storage channel, so size limits don't apply

    Returns:
        tuple: (is_valid, error_message)
    """
    media = get_media(message)
    if not media:
        return False, "No media found in message"

    # Check if media type is supported for streaming
    # Determine media type by checking which attribute is present in the message
    media_type = None
    for attr in (
        "video",
        "animation",
        "audio",
        "voice",
        "video_note",
        "document",
        "photo",
    ):
        if hasattr(message, attr) and getattr(message, attr) is not None:
            media_type = attr
            break

    if not media_type:
        return False, "Unable to determine media type"

    # Get allowed types from config
    from bot.core.config_manager import Config

    allowed_types = [
        t.strip().lower() for t in Config.FILE2LINK_ALLOWED_TYPES.split(",")
    ]

    if media_type not in allowed_types:
        supported_types = ", ".join(allowed_types)
        return (
            False,
            f"Media type '{media_type}' not supported. Supported: {supported_types}",
        )

    # For File2Link, we don't enforce file size limits since files are just copied to storage
    # The actual streaming will be handled by Telegram's servers
    file_size = get_fsize(message)
    if file_size == 0:
        return False, "Unable to determine file size"

    return True, ""


def get_media_type_tag(message: Message) -> str:
    """Get HTML tag for media type (video/audio)"""
    media = get_media(message)
    if not media:
        return "video"

    media_type = type(media).__name__.lower()
    if media_type in ["audio", "voice"]:
        return "audio"
    return "video"


def is_streamable_file(message: Message) -> bool:
    """
    Check if a file is streamable in browser

    Returns:
        bool: True if file can be streamed in browser, False otherwise
    """
    media = get_media(message)
    if not media:
        return False

    # Get media type from message attributes
    media_type = None
    for attr in ("video", "animation", "audio", "voice", "video_note"):
        if hasattr(message, attr) and getattr(message, attr) is not None:
            media_type = attr
            break

    # These types are generally streamable
    if media_type in ["video", "animation", "audio", "voice", "video_note"]:
        return True

    # For documents, check MIME type and file extension
    if hasattr(message, "document") and message.document:
        file_name = get_fname(message)
        if not file_name:
            return False

        # Get file extension
        ext = file_name.lower().split(".")[-1] if "." in file_name else ""

        # Streamable video extensions
        streamable_video_exts = {
            "mp4",
            "webm",
            "ogg",
            "ogv",
            "avi",
            "mov",
            "mkv",
            "m4v",
            "3gp",
            "flv",
            "wmv",
            "mpg",
            "mpeg",
        }

        # Streamable audio extensions
        streamable_audio_exts = {
            "mp3",
            "ogg",
            "oga",
            "wav",
            "flac",
            "m4a",
            "aac",
            "opus",
            "weba",
            "webm",
        }

        # Check if extension is streamable
        if ext in streamable_video_exts or ext in streamable_audio_exts:
            return True

        # Check MIME type if available
        if hasattr(message.document, "mime_type") and message.document.mime_type:
            mime_type = message.document.mime_type.lower()
            if mime_type.startswith(("video/", "audio/")):
                # Additional check for common streamable formats
                streamable_mimes = {
                    "video/mp4",
                    "video/webm",
                    "video/ogg",
                    "video/avi",
                    "video/quicktime",
                    "video/x-msvideo",
                    "video/3gpp",
                    "audio/mpeg",
                    "audio/ogg",
                    "audio/wav",
                    "audio/flac",
                    "audio/mp4",
                    "audio/aac",
                    "audio/opus",
                    "audio/webm",
                }
                return mime_type in streamable_mimes

    # Photos are not streamable (they're viewable but not "streamed")
    return False
