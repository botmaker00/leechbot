"""
Streaming handler for File2Link functionality

"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from bot import LOGGER
from bot.core.config_manager import Config

from .file_processor import get_media


class ByteStreamer:
    """Handles file streaming from Telegram"""

    __slots__ = ("chat_id", "client", "client_id")

    def __init__(
        self, client: Client, client_id: int = 0, chat_id: int | None = None
    ) -> None:
        if client is None:
            raise ValueError(
                "Client cannot be None - bot may not be initialized yet"
            )
        self.client = client
        self.client_id = client_id

        # Use provided chat_id or get from config
        if chat_id:
            self.chat_id = chat_id
        else:
            self.chat_id = Config.FILE2LINK_BIN_CHANNEL

        # Validate channel configuration
        if not self.chat_id:
            raise ValueError("FILE2LINK_BIN_CHANNEL not configured")

    def is_parallel(self) -> bool:
        """Return False to identify this as a single-client streamer"""
        return False

    async def get_message(self, message_id: int) -> Message:
        """Get message from storage channel with flood wait handling"""
        while True:
            try:
                message = await self.client.get_messages(self.chat_id, message_id)
                break
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                # Enhanced error handling for channel access issues
                error_msg = str(e).lower()
                if "invalid chat_id" in error_msg:
                    LOGGER.error(
                        f"Invalid chat_id {self.chat_id}. Bot may not have access to FILE2LINK_BIN_CHANNEL"
                    )
                    raise FileNotFoundError(
                        f"Bot cannot access storage channel {self.chat_id}. Please check if bot is added to the channel with proper permissions."
                    ) from e
                if "chat not found" in error_msg:
                    LOGGER.error(
                        f"Chat {self.chat_id} not found. FILE2LINK_BIN_CHANNEL may be incorrect"
                    )
                    raise FileNotFoundError(
                        f"Storage channel {self.chat_id} not found. Please verify FILE2LINK_BIN_CHANNEL configuration."
                    ) from e
                if "forbidden" in error_msg:
                    LOGGER.error(
                        f"Access forbidden to chat {self.chat_id}. Bot needs admin permissions"
                    )
                    raise FileNotFoundError(
                        f"Bot lacks permissions for storage channel {self.chat_id}. Please add bot as admin."
                    ) from e
                LOGGER.error(
                    f"Error fetching message {message_id} from chat {self.chat_id}: {e}"
                )
                raise FileNotFoundError(
                    f"Message {message_id} not found in storage channel"
                ) from e

        if not message or not message.media:
            raise FileNotFoundError(
                f"Message {message_id} not found or has no media"
            )
        return message

    async def stream_file(
        self, message_id: int, offset: int = 0, limit: int = 0
    ) -> AsyncGenerator[bytes]:
        """Stream file content with range support"""
        try:
            message = await self.get_message(message_id)

            if limit > 0:
                # Calculate chunk parameters for range requests
                chunk_offset = offset // (1024 * 1024)
                chunk_limit = (limit + 1024 * 1024 - 1) // (1024 * 1024)

                while True:
                    try:
                        async for chunk in self.client.stream_media(
                            message, offset=chunk_offset, limit=chunk_limit
                        ):
                            yield chunk
                        break
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        # Handle authentication and other errors
                        error_msg = str(e).lower()
                        if (
                            "unauthorized" in error_msg
                            or "auth" in error_msg
                            or "auth_key_unregistered" in error_msg
                        ):
                            LOGGER.error(f"Authentication error in streaming: {e}")
                            LOGGER.error(
                                "Telegram session expired - bot needs to re-authenticate"
                            )
                            raise ConnectionError(
                                f"Telegram authentication failed: {e}"
                            )
                        else:
                            LOGGER.error(f"Streaming error: {e}")
                            raise
            else:
                # Stream entire file
                while True:
                    try:
                        async for chunk in self.client.stream_media(message):
                            yield chunk
                        break
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        # Handle authentication and other errors
                        error_msg = str(e).lower()
                        if (
                            "unauthorized" in error_msg
                            or "auth" in error_msg
                            or "auth_key_unregistered" in error_msg
                        ):
                            LOGGER.error(f"Authentication error in streaming: {e}")
                            LOGGER.error(
                                "Telegram session expired - bot needs to re-authenticate"
                            )
                            raise ConnectionError(
                                f"Telegram authentication failed: {e}"
                            )
                        else:
                            LOGGER.error(f"Streaming error: {e}")
                            raise

        except Exception as e:
            LOGGER.error(f"Error streaming file {message_id}: {e}")
            raise

    def get_file_info_sync(self, message: Message) -> dict[str, Any]:
        """Get file information synchronously"""
        try:
            media = get_media(message)
            if not media:
                return {"message_id": message.id, "error": "No media"}

            return {
                "message_id": message.id,
                "file_size": getattr(media, "file_size", 0) or 0,
                "file_name": getattr(media, "file_name", None),
                "mime_type": getattr(media, "mime_type", None),
                "unique_id": getattr(media, "file_unique_id", None),
                "media_type": type(media).__name__.lower(),
                "duration": getattr(media, "duration", None),
                "width": getattr(media, "width", None),
                "height": getattr(media, "height", None),
            }
        except Exception as e:
            LOGGER.error(f"Error getting file info: {e}")
            return {"message_id": message.id, "error": str(e)}

    async def get_file_info(self, message_id: int) -> dict[str, Any]:
        """Get file information asynchronously"""
        try:
            message = await self.get_message(message_id)
            return self.get_file_info_sync(message)
        except Exception as e:
            LOGGER.error(f"Error getting file info for message {message_id}: {e}")
            return {"message_id": message_id, "error": str(e)}


class StreamingException(Exception):
    """Custom exception for streaming errors"""


class FileNotFoundError(StreamingException):
    """Exception raised when file is not found"""


class InvalidHashError(StreamingException):
    """Exception raised when hash validation fails"""


def validate_stream_request(hash_id: str, message_id: int) -> bool:
    """Validate streaming request parameters"""
    try:
        # Basic validation
        if not hash_id or len(hash_id) != 6:
            return False

        if not message_id or message_id <= 0:
            return False

        # Hash should contain only alphanumeric characters, hyphens, and underscores
        return hash_id.replace("-", "").replace("_", "").isalnum()
    except Exception as e:
        LOGGER.error(f"Error validating stream request: {e}")
        return False


def get_mime_type(filename: str) -> str:
    """Get MIME type based on file extension"""
    try:
        extension = filename.lower().split(".")[-1] if "." in filename else ""

        mime_types = {
            # Video formats
            "mp4": "video/mp4",
            "avi": "video/x-msvideo",
            "mov": "video/quicktime",
            "wmv": "video/x-ms-wmv",
            "flv": "video/x-flv",
            "webm": "video/webm",
            "mkv": "video/x-matroska",
            "3gp": "video/3gpp",
            # Audio formats
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "flac": "audio/flac",
            "aac": "audio/aac",
            "ogg": "audio/ogg",
            "m4a": "audio/mp4",
            "wma": "audio/x-ms-wma",
            # Image formats
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
            "bmp": "image/bmp",
            "svg": "image/svg+xml",
            # Document formats
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain",
            "zip": "application/zip",
            "rar": "application/x-rar-compressed",
        }

        return mime_types.get(extension, "application/octet-stream")
    except Exception:
        return "application/octet-stream"
