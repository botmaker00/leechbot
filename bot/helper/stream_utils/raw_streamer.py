"""
Raw API Streaming Implementation
Based on File-To-Link's efficient approach but adapted for FastAPI
"""

import asyncio
import math
from collections.abc import AsyncGenerator

from pyrogram import Client, raw
from pyrogram.errors import AuthBytesInvalid
from pyrogram.file_id import FileId
from pyrogram.session import Auth, Session


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

    def __init__(self, clients: dict[int, Client], chat_id: int):
        """
        Initialize with client pool and storage channel

        Args:
            clients: Dictionary of {client_id: client} for load balancing
            chat_id: Storage channel ID
        """
        self.clients = clients
        self.chat_id = chat_id
        self.cached_file_properties: dict[int, dict] = {}
        self.cached_media_sessions: dict[
            tuple[int, int], Session
        ] = {}  # (client_id, dc_id) -> Session
        self.client_loads: dict[int, int] = dict.fromkeys(clients, 0)

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_cache())

    async def _cleanup_cache(self):
        """Cleanup cache periodically"""
        while True:
            try:
                await asyncio.sleep(30 * 60)  # 30 minutes
                # Clear file properties cache
                if len(self.cached_file_properties) > 100:
                    # Keep only recent 50 entries
                    items = list(self.cached_file_properties.items())
                    self.cached_file_properties = dict(items[-50:])

            except Exception:
                pass

    def _get_optimal_client(self) -> tuple[Client, int]:
        """Get client with minimum load"""
        if not self.clients:
            raise RuntimeError("No clients available")

        # Find client with minimum load
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

        # Get optimal client for file property retrieval
        client, client_id = self._get_optimal_client()

        try:
            # Get message from storage channel
            message = await client.get_messages(self.chat_id, message_id)
            if not message or not message.media:
                raise FileNotFoundError(
                    f"Message {message_id} not found or has no media"
                )

            # Extract file properties from message
            file_info = {}
            file_id = None

            if message.document:
                file_info = {
                    "file_size": message.document.file_size,
                    "file_name": message.document.file_name or "document",
                    "mime_type": message.document.mime_type
                    or "application/octet-stream",
                    "media_type": "document",
                }
                file_id = FileId.decode(message.document.file_id)
            elif message.video:
                file_info = {
                    "file_size": message.video.file_size,
                    "file_name": message.video.file_name
                    or f"video.{message.video.mime_type.split('/')[-1] if message.video.mime_type else 'mp4'}",
                    "mime_type": message.video.mime_type or "video/mp4",
                    "media_type": "video",
                }
                file_id = FileId.decode(message.video.file_id)
            elif message.audio:
                file_info = {
                    "file_size": message.audio.file_size,
                    "file_name": message.audio.file_name
                    or f"audio.{message.audio.mime_type.split('/')[-1] if message.audio.mime_type else 'mp3'}",
                    "mime_type": message.audio.mime_type or "audio/mpeg",
                    "media_type": "audio",
                }
                file_id = FileId.decode(message.audio.file_id)
            elif message.photo:
                # For photos, we need to get the largest size
                photo_size = message.photo.sizes[-1]  # Get largest size
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
                    "file_name": message.animation.file_name
                    or f"animation.{message.animation.mime_type.split('/')[-1] if message.animation.mime_type else 'gif'}",
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

            # Add FileId to the info for internal use
            file_info["_file_id"] = file_id

            # Cache the result
            self.cached_file_properties[message_id] = file_info

            return file_info

        except Exception:
            raise

    async def _get_media_session(
        self, client: Client, client_id: int, file_id: FileId
    ) -> Session:
        """Get or create media session for specific DC"""
        session_key = (client_id, file_id.dc_id)

        if session_key in self.cached_media_sessions:
            return self.cached_media_sessions[session_key]

        try:
            media_session = client.media_sessions.get(file_id.dc_id, None)

            if media_session is None:
                if file_id.dc_id != await client.storage.dc_id():
                    # Create session for different DC
                    media_session = Session(
                        client,
                        file_id.dc_id,
                        await Auth(
                            client, file_id.dc_id, await client.storage.test_mode()
                        ).create(),
                        await client.storage.test_mode(),
                        is_media=True,
                    )
                    await media_session.start()

                    # Export and import authorization
                    for _ in range(6):
                        exported_auth = await client.invoke(
                            raw.functions.auth.ExportAuthorization(
                                dc_id=file_id.dc_id
                            )
                        )

                        try:
                            await media_session.send(
                                raw.functions.auth.ImportAuthorization(
                                    id=exported_auth.id, bytes=exported_auth.bytes
                                )
                            )
                            break
                        except AuthBytesInvalid:
                            continue
                    else:
                        await media_session.stop()
                        raise AuthBytesInvalid
                else:
                    # Same DC as client
                    media_session = Session(
                        client,
                        file_id.dc_id,
                        await client.storage.auth_key(),
                        await client.storage.test_mode(),
                        is_media=True,
                    )
                    await media_session.start()

                # Cache the session
                client.media_sessions[file_id.dc_id] = media_session

            # Cache our reference
            self.cached_media_sessions[session_key] = media_session
            return media_session

        except Exception:
            raise

    async def _get_file_location(self, file_id: FileId):
        """Get file location for raw API"""
        # For most media files, use InputDocumentFileLocation
        return raw.types.InputDocumentFileLocation(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
            thumb_size="",  # Empty string for full file
        )

    async def stream_file(
        self, message_id: int, offset: int = 0, limit: int = 0
    ) -> AsyncGenerator[bytes]:
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
            # Get file properties
            file_info = await self.get_file_properties(message_id)
            file_id = file_info["_file_id"]
            file_size = file_info["file_size"]

            # Calculate streaming parameters (like File-To-Link)
            chunk_size = 1024 * 1024  # 1MB chunks

            # Determine end byte
            if limit > 0:
                end_byte = min(offset + limit - 1, file_size - 1)
            else:
                end_byte = file_size - 1

            # Align offset to chunk boundary
            aligned_offset = offset - (offset % chunk_size)
            first_part_cut = offset - aligned_offset
            last_part_cut = (end_byte % chunk_size) + 1

            # Calculate part count
            part_count = math.ceil((end_byte + 1) / chunk_size) - math.floor(
                aligned_offset / chunk_size
            )

            # Get media session and location
            media_session = await self._get_media_session(client, client_id, file_id)
            location = await self._get_file_location(file_id)

            # Stream chunks using raw API
            current_part = 1
            current_offset = aligned_offset
            bytes_streamed = 0

            while current_part <= part_count:
                try:
                    # Get chunk from Telegram
                    r = await media_session.send(
                        raw.functions.upload.GetFile(
                            location=location,
                            offset=current_offset,
                            limit=chunk_size,
                        )
                    )

                    if isinstance(r, raw.types.upload.File):
                        chunk = r.bytes
                        if not chunk:
                            break

                        # Apply cuts for range requests (like File-To-Link)
                        if part_count == 1:
                            # Single part - cut both ends
                            chunk = chunk[first_part_cut:last_part_cut]
                        elif current_part == 1:
                            # First part - cut beginning
                            chunk = chunk[first_part_cut:]
                        elif current_part == part_count:
                            # Last part - cut end
                            chunk = chunk[:last_part_cut]
                        # Middle parts - no cutting needed

                        if chunk:
                            yield chunk
                            bytes_streamed += len(chunk)

                            # Check if we've streamed enough
                            if limit > 0 and bytes_streamed >= limit:
                                break

                    current_part += 1
                    current_offset += chunk_size

                except Exception:
                    break

        except Exception:
            raise
        finally:
            self._decrement_load(client_id)

    async def get_message(self, message_id: int):
        """Get message from storage channel (for web server compatibility)"""
        try:
            # Get optimal client for message retrieval
            client, client_id = self._get_optimal_client()
            message = await client.get_messages(self.chat_id, message_id)

            if not message or not message.media:
                raise FileNotFoundError(
                    f"Message {message_id} not found or has no media"
                )

            return message

        except Exception:
            raise

    def get_file_info(self, message_id: int) -> dict:
        """Get file info for web server (sync wrapper)"""
        try:
            # This is a sync method for compatibility, but we need async
            # The web server should call get_file_properties directly
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

        # Build client pool
        clients = {}

        # Add main bot
        if hasattr(TgClient, "bot") and TgClient.bot is not None:
            clients[0] = TgClient.bot

        # Add helper bots
        if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
            for client_id, client in TgClient.helper_bots.items():
                if client is not None:
                    clients[client_id] = client

        if not clients:
            return None

        return RawByteStreamer(clients, chat_id)

    except Exception:
        return None
