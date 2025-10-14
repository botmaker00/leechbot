import asyncio
import math
from collections.abc import AsyncGenerator
import logging
from typing import Dict, Tuple

from pyrogram import Client, raw
from pyrogram.errors import AuthBytesInvalid
from pyrogram.file_id import FileId
from pyrogram.session import Auth, Session

# Configure logging
logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for detailed logs
logger = logging.getLogger(__name__)

class RawByteStreamer:
    """
    Raw API streaming implementation based on File-To-Link
    Features:
    - Raw Telegram API for maximum efficiency
    - File property caching
    - Load balancing
    - Range request support
    - FastAPI compatible
    """

    def __init__(self, clients: Dict[int, Client], chat_id: int):
        """
        Initialize with client pool and storage channel

        Args:
            clients: Dictionary of {client_id: client} for load balancing
            chat_id: Storage channel ID
        """
        self.clients = clients
        self.chat_id = chat_id
        self.cached_file_properties: Dict[int, dict] = {}
        self.cached_media_sessions: Dict[Tuple[int, int], Session] = {}  # (client_id, dc_id) -> Session
        self.client_loads: Dict[int, int] = dict.fromkeys(clients, 0)

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_cache())

    async def _cleanup_cache(self):
        """Cleanup cache periodically"""
        while True:
            try:
                await asyncio.sleep(30 * 60)  # 30 minutes
                # Clear file properties cache
                if len(self.cached_file_properties) > 100:
                    items = list(self.cached_file_properties.items())
                    self.cached_file_properties = dict(items[-50:])
                # Clear media sessions cache
                if len(self.cached_media_sessions) > 100:
                    self.cached_media_sessions = dict(list(self.cached_media_sessions.items())[-50:])

            except Exception as e:
                logger.error(f"Cache cleanup failed: {e}")

    def _get_optimal_client(self) -> Tuple[Client, int]:
        """Get client with minimum load"""
        if not self.clients:
            raise RuntimeError("No clients available")

        min_client_id = min(self.client_loads, key=self.client_loads.get)
        return self.clients[min_client_id], min_client_id

    def _increment_load(self, client_id: int):
        """Increment client load"""
        if client_id in self.client_loads:
            self.client_loads[client_id] += 1

    def _decrement_load(self, client_id: int):
        """Decrement client load"""
        if client_id in self.client_loads:
            self.client_loads[client_id] = max(0, self.client_loads[client_id] - 1)

    async def get_file_properties(self, message_id: int) -> dict:
        """Get file properties with caching"""
        if message_id in self.cached_file_properties:
            return self.cached_file_properties[message_id]

        client, client_id = self._get_optimal_client()

        try:
            message = await client.get_messages(self.chat_id, message_id)
            if not message or not message.media:
                raise FileNotFoundError(f"Message {message_id} not found or has no media")

            file_info = {}
            file_id = None

            if message.document:
                file_info = {
                    "file_size": message.document.file_size,
                    "file_name": message.document.file_name or "document",
                    "mime_type": message.document.mime_type or "application/octet-stream",
                    "media_type": "document",
                }
                file_id = FileId.decode(message.document.file_id)
            elif message.video:
                file_info = {
                    "file_size": message.video.file_size,
                    "file_name": message.video.file_name or f"video.{message.video.mime_type.split('/')[-1] if message.video.mime_type else 'mp4'}",
                    "mime_type": message.video.mime_type or "video/mp4",
                    "media_type": "video",
                }
                file_id = FileId.decode(message.video.file_id)
            elif message.audio:
                file_info = {
                    "file_size": message.audio.file_size,
                    "file_name": message.audio.file_name or f"audio.{message.audio.mime_type.split('/')[-1] if message.audio.mime_type else 'mp3'}",
                    "mime_type": message.audio.mime_type or "audio/mpeg",
                    "media_type": "audio",
                }
                file_id = FileId.decode(message.audio.file_id)
            elif message.photo:
                photo_size = message.photo.sizes[-1]
                file_info = {
                    "file_size": photo_size.file_size,
                    "file_name": f"photo_{message_id}.jpg",
                    "mime_type": "image/jpeg",
                    "media_type": "photo",
                }
                file_id = FileId.decode(message.photo.file_id)
            elif message.animation:
                file_info = {
                    "file_size": message.animation.file_size,
                    "file_name": message.animation.file_name or f"animation.{message.animation.mime_type.split('/')[-1] if message.animation.mime_type else 'gif'}",
                    "mime_type": message.animation.mime_type or "image/gif",
                    "media_type": "animation",
                }
                file_id = FileId.decode(message.animation.file_id)
            elif message.voice:
                file_info = {
                    "file_size": message.voice.file_size,
                    "file_name": f"voice_{message_id}.ogg",
                    "mime_type": message.voice.mime_type or "audio/ogg",
                    "media_type": "voice",
                }
                file_id = FileId.decode(message.voice.file_id)
            elif message.video_note:
                file_info = {
                    "file_size": message.video_note.file_size,
                    "file_name": f"video_note_{message_id}.mp4",
                    "mime_type": "video/mp4",
                    "media_type": "video_note",
                }
                file_id = FileId.decode(message.video_note.file_id)
            elif message.sticker:
                file_info = {
                    "file_size": message.sticker.file_size,
                    "file_name": f"sticker_{message_id}.webp",
                    "mime_type": "image/webp",
                    "media_type": "sticker",
                }
                file_id = FileId.decode(message.sticker.file_id)

            if not file_id or not file_info:
                raise ValueError(f"Unsupported media type in message {message_id}")

            file_info["_file_id"] = file_id
            self.cached_file_properties[message_id] = file_info
            return file_info

        except Exception as e:
            logger.error(f"Failed to get file properties for message {message_id}: {e}")
            raise

    async def _get_media_session(self, client: Client, client_id: int, file_id: FileId) -> Session:
        """Get or create media session for specific DC"""
        session_key = (client_id, file_id.dc_id)

        if session_key in self.cached_media_sessions:
            return self.cached_media_sessions[session_key]

        try:
            media_session = client.media_sessions.get(file_id.dc_id, None)

            if media_session is None:
                test_mode = await client.storage.test_mode()
                if test_mode is None:
                    logger.warning("Test mode not set, defaulting to False")
                    test_mode = False

                # Try to resolve DC dynamically
                try:
                    if hasattr(client, 'get_dc'):
                        dc_config = await client.get_dc(file_id.dc_id)
                        server_address, port = dc_config.ip_address, dc_config.port
                    else:
                        # Fallback to known Telegram DCs
                        dc_list = {
                            1: ("149.154.175.50", 443),
                            2: ("149.154.167.51", 443),
                            3: ("149.154.175.100", 443),
                            4: ("149.154.167.91", 443),
                            5: ("91.108.56.130", 443),
                        }
                        dc_config = dc_list.get(file_id.dc_id, ("149.154.175.50", 443))
                        server_address, port = dc_config
                except Exception as e:
                    logger.warning(f"Failed to get DC config for DC {file_id.dc_id}: {e}, using fallback")
                    server_address, port = "149.154.175.50", 443

                logger.debug(f"Creating session for DC {file_id.dc_id} with server {server_address}:{port}")

                if file_id.dc_id != await client.storage.dc_id():
                    try:
                        auth_key = await Auth(client, file_id.dc_id, port, test_mode).create()
                    except Exception as e:
                        logger.error(f"Failed to create auth key for DC {file_id.dc_id}: {e}")
                        raise

                    media_session = Session(
                        client=client,
                        dc_id=file_id.dc_id,
                        auth_key=auth_key,
                        test_mode=test_mode,
                        server_address=server_address,
                        port=port,
                        is_media=True,
                    )
                    await media_session.start()

                    for _ in range(6):
                        try:
                            exported_auth = await client.invoke(raw.functions.auth.ExportAuthorization(dc_id=file_id.dc_id))
                            await media_session.send(raw.functions.auth.ImportAuthorization(id=exported_auth.id, bytes=exported_auth.bytes))
                            break
                        except AuthBytesInvalid as e:
                            logger.warning(f"AuthBytesInvalid, retrying: {e}")
                            continue
                    else:
                        await media_session.stop()
                        logger.error("Failed to import authorization after retries")
                        raise AuthBytesInvalid
                else:
                    auth_key = await client.storage.auth_key()
                    if auth_key is None:
                        logger.error("Auth key not found in client storage")
                        raise ValueError("Auth key is required but not found in client storage")

                    media_session = Session(
                        client=client,
                        dc_id=file_id.dc_id,
                        auth_key=auth_key,
                        test_mode=test_mode,
                        server_address=server_address,
                        port=port,
                        is_media=True,
                    )
                    await media_session.start()

                client.media_sessions[file_id.dc_id] = media_session

            self.cached_media_sessions[session_key] = media_session
            return media_session

        except Exception as e:
            logger.error(f"Failed to create media session for DC {file_id.dc_id}: {e}")
            raise

    async def _get_file_location(self, file_id: FileId):
        """Get file location for raw API"""
        return raw.types.InputDocumentFileLocation(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
            thumb_size="",
        )

    async def stream_file(self, message_id: int, offset: int = 0, limit: int = 0) -> AsyncGenerator[bytes]:
        """
        Stream file using raw API (like File-To-Link)

        Args:
            message_id: Message ID in storage channel
            offset: Start byte offset
            limit: Maximum bytes to stream (0 = no limit)
        """
        client, client_id = self._get_optimal_client()
        self._increment_load(client_id)

        try:
            file_info = await self.get_file_properties(message_id)
            file_id = file_info["_file_id"]
            file_size = file_info["file_size"]

            chunk_size = 1024 * 1024  # 1MB chunks
            if limit > 0:
                end_byte = min(offset + limit - 1, file_size - 1)
            else:
                end_byte = file_size - 1

            aligned_offset = offset - (offset % chunk_size)
            first_part_cut = offset - aligned_offset
            last_part_cut = (end_byte % chunk_size) + 1
            part_count = math.ceil((end_byte + 1) / chunk_size) - math.floor(aligned_offset / chunk_size)

            media_session = await self._get_media_session(client, client_id, file_id)
            location = await self._get_file_location(file_id)

            current_part = 1
            current_offset = aligned_offset
            bytes_streamed = 0

            while current_part <= part_count:
                for attempt in range(5):  # Increased retries to 5
                    try:
                        async with asyncio.timeout(30):  # Increased to 30 seconds
                            r = await media_session.send(raw.functions.upload.GetFile(location=location, offset=current_offset, limit=chunk_size))

                            if isinstance(r, raw.types.upload.File):
                                chunk = r.bytes
                                if not chunk:
                                    logger.warning(f"Empty chunk received for message {message_id}, part {current_part}")
                                    break

                                if part_count == 1:
                                    chunk = chunk[first_part_cut:last_part_cut]
                                elif current_part == 1:
                                    chunk = chunk[first_part_cut:]
                                elif current_part == part_count:
                                    chunk = chunk[:last_part_cut]

                                if chunk:
                                    yield chunk
                                    bytes_streamed += len(chunk)

                                    if limit > 0 and bytes_streamed >= limit:
                                        return

                            current_part += 1
                            current_offset += chunk_size
                            break

                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout on chunk {current_part} for message {message_id}, attempt {attempt + 1}")
                        if attempt == 4:
                            logger.error(f"Failed to stream chunk {current_part} for message {message_id} after retries")
                            raise
                        try:
                            await media_session.stop()
                            media_session = await self._get_media_session(client, client_id, file_id)
                        except Exception as e:
                            logger.error(f"Failed to reinitialize session for DC {file_id.dc_id}: {e}")
                            raise
                    except Exception as e:
                        logger.error(f"Error streaming chunk {current_part} for message {message_id}: {e}")
                        break

        except Exception as e:
            logger.error(f"Error streaming file for message {message_id}: {e}")
            raise
        finally:
            self._decrement_load(client_id)

    async def get_message(self, message_id: int):
        """Get message from storage channel (for web server compatibility)"""
        try:
            client, client_id = self._get_optimal_client()
            message = await client.get_messages(self.chat_id, message_id)

            if not message or not message.media:
                raise FileNotFoundError(f"Message {message_id} not found or has no media")

            return message

        except Exception as e:
            logger.error(f"Failed to get message {message_id}: {e}")
            raise

    def get_file_info(self, message_id: int) -> dict:
        """Get file info for web server (sync wrapper)"""
        try:
            return {"error": "Use get_file_properties async method instead"}
        except Exception as e:
            return {"error": str(e)}

    def is_parallel(self) -> bool:
        """Check if this is a parallel streamer (for compatibility)"""
        return len(self.clients) > 1


def create_raw_streamer(chat_id: int) -> RawByteStreamer | None:
    """
    Factory function to create RawByteStreamer with available clients

    Args:
        chat_id: Storage channel ID

    Returns:
        RawByteStreamer instance or None if no clients available
    """
    try:
        from bot.core.aeon_client import TgClient

        clients = {}
        if hasattr(TgClient, "bot") and TgClient.bot is not None:
            clients[0] = TgClient.bot

        if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
            for client_id, client in TgClient.helper_bots.items():
                if client is not None:
                    clients[client_id] = client

        if not clients:
            logger.error("No clients available for RawByteStreamer")
            return None

        return RawByteStreamer(clients, chat_id)

    except Exception as e:
        logger.error(f"Failed to create RawByteStreamer: {e}")
        return None
