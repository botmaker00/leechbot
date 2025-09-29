from asyncio import (
    CancelledError,
    Event,
    TimeoutError,
    create_task,
    gather,
    sleep,
    wait_for,
)
from datetime import datetime
from math import ceil, floor
from mimetypes import guess_extension
from os import path as ospath
from pathlib import Path
from re import sub
from sys import argv
from time import time

from aiofiles import open as aiopen
from aioshutil import move

from bot.helper.ext_utils.aiofiles_compat import makedirs, remove

try:
    # Fall back to pyrogram
    from pyrogram import raw, utils

    try:
        # Try to import from pyrogram directly (older versions)
        from pyrogram import StopTransmission
    except ImportError:
        try:
            # In newer versions, it's called StopTransmissionError
            from pyrogram.errors import StopTransmissionError as StopTransmission
        except ImportError:
            # If neither is available, define a custom exception
            class StopTransmission(Exception):
                """Custom exception to handle stop transmission"""

    from pyrogram.errors import AuthBytesInvalid, FloodWait
    from pyrogram.file_id import PHOTO_TYPES, FileId, FileType, ThumbnailSource
    from pyrogram.session import Auth, Session
    from pyrogram.session.internals import MsgId
except ImportError:
    # If all imports fail, raise a clear error
    raise ImportError(
        "Failed to import required modules from either electrogram or pyrogram. Please check your installation."
    )


import builtins
import contextlib

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config


class HyperTGDownload:
    """
    HyperDL Workflow:
    1. Main bot copies message to dump chat (safer than forwarding)
    2. Helper bots download different parts from dump chat simultaneously
    3. Parts are combined into final file

    Requirements:
    - Main bot must have copy permissions in dump chat
    - Helper bots must have access to dump chat (or original chat as fallback)
    """

    def __init__(self):
        self.clients = TgClient.helper_bots
        if not self.clients:
            LOGGER.error("❌ No helper bots available for hyper download")
            raise ValueError("No helper bots available for hyper download")

        # helper_bots is a dict with integer keys, not a list
        for client_id, client in self.clients.items():
            if hasattr(client, "me") and client.me:
                getattr(client.me, "username", f"client_{client_id}")

        self.work_loads = TgClient.helper_loads
        self.message = None
        self.dump_chat = None
        self.download_dir = "downloads/"
        self.directory = None
        self.num_parts = Config.HYPER_THREADS or max(8, len(self.clients))
        self.cache_file_ref = {}
        self.cache_last_access = {}
        self.cache_max_size = 100
        self._processed_bytes = 0
        self.file_size = 0
        self.chunk_size = 1024 * 1024
        self.file_name = ""
        self._cancel_event = Event()
        self.session_pool = {}
        self._clean_task = create_task(self._clean_cache())

    def __del__(self):
        if hasattr(self, "_clean_task") and not self._clean_task.done():
            self._clean_task.cancel()

    async def _check_helper_bot_access(self, chat_id):
        """Check if at least one helper bot has access to the specified chat"""
        accessible_bots = 0

        for client_id, client in self.clients.items():
            try:
                # Try to get chat info to verify access
                await client.get_chat(chat_id)
                try:
                    username = (
                        getattr(client.me, "username", f"client_{client_id}")
                        if hasattr(client, "me") and client.me
                        else f"client_{client_id}"
                    )
                except:
                    username = f"client_{client_id}"
                accessible_bots += 1
            except Exception as e:
                try:
                    username = (
                        getattr(client.me, "username", f"client_{client_id}")
                        if hasattr(client, "me") and client.me
                        else f"client_{client_id}"
                    )
                except:
                    username = f"client_{client_id}"
                LOGGER.warning(
                    f"❌ Helper bot {client_id} (@{username}) cannot access chat {chat_id}: {e!s}"
                )
                continue

        return accessible_bots > 0

    async def _refresh_bot_session(self):
        """Refresh bot session to ensure latest permissions"""
        try:
            # Get bot info to refresh session
            await TgClient.bot.get_me()

            # Also try to get chat info to refresh chat-specific permissions
            try:
                if hasattr(self, "dump_chat") and self.dump_chat:
                    dump_chat_id = (
                        self.dump_chat[0]
                        if isinstance(self.dump_chat, list)
                        else self.dump_chat
                    )
                    await TgClient.bot.get_chat(dump_chat_id)
            except Exception:
                pass

            return True
        except Exception:
            return False

    @staticmethod
    async def get_media_type(message):
        if not message:
            raise ValueError("Message is None")

        # Use the same media detection logic as telegram_download.py (Kurigram compatible)
        media = (
            message.document
            or message.photo
            or message.video
            or message.audio
            or message.voice
            or message.video_note
            or message.sticker
            or message.animation
            or None
        )

        if media is not None:
            return media

        # If we get here, no media was found
        raise ValueError("This message doesn't contain any downloadable media")

    def _update_cache(self, client_id, file_ref):
        self.cache_file_ref[client_id] = file_ref
        self.cache_last_access[client_id] = time()

        if len(self.cache_file_ref) > self.cache_max_size:
            oldest = sorted(self.cache_last_access.items(), key=lambda x: x[1])[0][0]
            del self.cache_file_ref[oldest]
            del self.cache_last_access[oldest]

    async def get_specific_file_ref(self, mid, client, max_retries=3):
        retries = 0
        last_error = None

        # Handle case where dump_chat is a list - use the first item
        chat_id = (
            self.dump_chat[0] if isinstance(self.dump_chat, list) else self.dump_chat
        )

        while retries < max_retries:
            try:
                # Adapt for electrogram API
                try:
                    media = await client.get_messages(
                        chat_id=chat_id,
                        message_ids=mid,
                    )
                except TypeError as e:
                    # Handle case where get_messages has different parameters in Electrogram
                    if "unexpected keyword argument" in str(e):
                        # Try alternative approach for Electrogram
                        media = await client.get_messages(
                            chat_id,  # chat_id as positional argument
                            mid,  # message_ids as positional argument
                        )
                    else:
                        raise

                file_id_str = getattr(
                    await self.get_media_type(media), "file_id", ""
                )
                return FileId.decode(file_id_str)

            except Exception as e:
                last_error = e
                retries += 1
                if retries < max_retries:
                    await sleep(1 * retries)

        raise ValueError(
            f"Bot needs Admin access in Chat or message may be deleted. Error: {last_error}"
        )

    async def get_file_id(self, client, client_id) -> FileId:
        if client_id not in self.cache_file_ref:
            file_ref = await self.get_specific_file_ref(self.message.id, client)
            self._update_cache(client_id, file_ref)
        else:
            self.cache_last_access[client_id] = time()

        return self.cache_file_ref[client_id]

    async def _clean_cache(self):
        while True:
            await sleep(15 * 60)  # Clean every 15 minutes

            current_time = time()
            expired_keys = [
                k
                for k, v in self.cache_last_access.items()
                if current_time - v > 45 * 60  # Remove entries older than 45 minutes
            ]

            if expired_keys:
                for key in expired_keys:
                    if key in self.cache_file_ref:
                        del self.cache_file_ref[key]
                    if key in self.cache_last_access:
                        del self.cache_last_access[key]

    async def generate_media_session(
        self, client, file_id, client_id, max_retries=3
    ):
        session_key = (client_id, file_id.dc_id)

        if session_key in self.session_pool:
            return self.session_pool[session_key]

        retries = 0
        while retries < max_retries:
            try:
                client_dc_id = await client.storage.dc_id()

                if file_id.dc_id != client_dc_id:
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

                    for _attempt in range(6):
                        exported_auth = await client.invoke(
                            raw.functions.auth.ExportAuthorization(
                                dc_id=file_id.dc_id
                            )
                        )

                        try:
                            await media_session.invoke(
                                raw.functions.auth.ImportAuthorization(
                                    id=exported_auth.id, bytes=exported_auth.bytes
                                )
                            )
                            break
                        except AuthBytesInvalid:
                            await sleep(1)
                    else:
                        LOGGER.error(
                            "Failed to import authorization after 6 attempts"
                        )
                        await media_session.stop()
                        raise AuthBytesInvalid
                else:
                    media_session = Session(
                        client,
                        file_id.dc_id,
                        await client.storage.auth_key(),
                        await client.storage.test_mode(),
                        is_media=True,
                    )
                    await media_session.start()

                self.session_pool[session_key] = media_session
                return media_session

            except Exception:
                retries += 1
                if retries < max_retries:
                    await sleep(1)

        raise ValueError(
            f"Failed to create media session after {max_retries} attempts"
        )

    @staticmethod
    async def get_location(file_id: FileId):
        file_type = file_id.file_type

        if file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id, access_hash=file_id.chat_access_hash
                )
            else:
                peer = (
                    raw.types.InputPeerChat(chat_id=-file_id.chat_id)
                    if file_id.chat_access_hash == 0
                    else raw.types.InputPeerChannel(
                        channel_id=utils.get_channel_id(file_id.chat_id),
                        access_hash=file_id.chat_access_hash,
                    )
                )
            return raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )

        if file_type == FileType.PHOTO:
            return raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )

        return raw.types.InputDocumentFileLocation(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
            thumb_size=file_id.thumbnail_size,
        )

    async def get_file(
        self,
        offset_bytes: int,
        first_part_cut: int,
        last_part_cut: int,
        part_count: int,
        max_retries=5,
    ):
        # Select client with minimum workload
        client_id = min(self.work_loads, key=self.work_loads.get)
        client = self.clients[client_id]
        with contextlib.suppress(builtins.BaseException):
            getattr(client.me, "username", f"client_{client_id}") if hasattr(
                client, "me"
            ) and client.me else f"client_{client_id}"

        self.work_loads[client_id] += 1
        current_retry = 0

        try:
            while current_retry < max_retries:
                try:
                    if self._cancel_event.is_set():
                        raise CancelledError("Download cancelled")

                    file_id = await self.get_file_id(client, client_id)
                    media_session, location = await gather(
                        self.generate_media_session(client, file_id, client_id),
                        self.get_location(file_id),
                    )

                    current_part = 1
                    current_offset = offset_bytes
                    total_bytes_downloaded = 0

                    while current_part <= part_count:
                        if self._cancel_event.is_set():
                            LOGGER.info("Download cancelled during part download")
                            raise CancelledError("Download cancelled")

                        try:
                            r = await wait_for(
                                media_session.invoke(
                                    raw.functions.upload.GetFile(
                                        location=location,
                                        offset=current_offset,
                                        limit=self.chunk_size,
                                    ),
                                ),
                                timeout=30,
                            )

                            if isinstance(r, raw.types.upload.File):
                                chunk = r.bytes
                                chunk_size = len(chunk)
                                total_bytes_downloaded += chunk_size

                                if not chunk:
                                    break

                                if part_count == 1:
                                    yield chunk[first_part_cut:last_part_cut]
                                elif current_part == 1:
                                    yield chunk[first_part_cut:]
                                elif current_part == part_count:
                                    yield chunk[:last_part_cut]
                                else:
                                    yield chunk

                                current_part += 1
                                current_offset += self.chunk_size
                                self._processed_bytes += chunk_size
                            else:
                                LOGGER.error(f"Unexpected response type: {type(r)}")
                                raise ValueError(f"Unexpected response: {r}")

                        except FloodWait as e:
                            await sleep(e.value + 1)
                            continue
                        except (TimeoutError, ConnectionError):
                            await sleep(1)
                            continue

                    if current_part <= part_count:
                        error_msg = f"Incomplete download: got {current_part - 1} of {part_count} parts"
                        LOGGER.error(error_msg)
                        raise ValueError(error_msg)

                    break

                except (TimeoutError, ConnectionError, AttributeError):
                    current_retry += 1
                    if current_retry >= max_retries:
                        raise
                    sleep_time = current_retry * 2
                    await sleep(sleep_time)

        finally:
            self.work_loads[client_id] -= 1

    async def progress_callback(self, progress, progress_args):
        if not progress:
            return

        progress_count = 0

        while not self._cancel_event.is_set():
            try:
                if callable(progress):
                    progress_count += 1
                    await progress(
                        self._processed_bytes, self.file_size, *progress_args
                    )
                await sleep(1)
            except (CancelledError, StopTransmission):
                # Download was cancelled, stop progress callback silently
                break
            except Exception:
                # If there's an error and cancellation is set, stop silently
                if self._cancel_event.is_set():
                    break
                # Otherwise continue with a short delay
                await sleep(1)

    async def single_part(self, start, end, part_index, max_retries=3):
        until_bytes, from_bytes = min(end, self.file_size - 1), start
        until_bytes - from_bytes + 1

        offset = from_bytes - (from_bytes % self.chunk_size)
        first_part_cut = from_bytes - offset
        last_part_cut = until_bytes % self.chunk_size + 1

        part_count = ceil(until_bytes / self.chunk_size) - floor(
            offset / self.chunk_size
        )
        part_file_path = ospath.join(
            self.directory, f"{self.file_name}.temp.{part_index:02d}"
        )

        for attempt in range(max_retries):
            try:
                bytes_written = 0

                async with aiopen(part_file_path, "wb") as f:
                    async for chunk in self.get_file(
                        offset, first_part_cut, last_part_cut, part_count
                    ):
                        if self._cancel_event.is_set():
                            raise CancelledError("Download cancelled")
                        await f.write(chunk)
                        bytes_written += len(chunk)

                return part_index, part_file_path

            except (TimeoutError, ConnectionError):
                if attempt == max_retries - 1:
                    raise
                sleep_time = (attempt + 1) * 2
                await sleep(sleep_time)
                self._processed_bytes = 0

        # If we reach here, all attempts failed
        raise ValueError(
            f"Failed to download part {part_index} after {max_retries} attempts"
        )

    async def handle_download(self, progress, progress_args):
        download_start_time = time()
        LOGGER.info(f"Starting HyperDL download for file: {self.file_name}")

        self._cancel_event.clear()
        await makedirs(self.directory, exist_ok=True)

        temp_file_path = (
            ospath.abspath(
                sub("\\\\", "/", ospath.join(self.directory, self.file_name))
            )
            + ".temp"
        )

        # Calculate optimal number of parts
        num_parts = min(self.num_parts, max(1, self.file_size // (10 * 1024 * 1024)))

        if self.file_size < 10 * 1024 * 1024:
            num_parts = 1

        part_size = self.file_size // num_parts if num_parts > 0 else self.file_size
        ranges = [
            (i * part_size, min((i + 1) * part_size - 1, self.file_size - 1))
            for i in range(num_parts)
        ]

        tasks = []
        prog_task = None

        try:
            for i, (start, end) in enumerate(ranges):
                task = create_task(self.single_part(start, end, i))
                tasks.append(task)

            if progress:
                prog_task = create_task(
                    self.progress_callback(progress, progress_args)
                )

            results = await gather(*tasks)

            total_bytes_combined = 0

            async with aiopen(temp_file_path, "wb") as temp_file:
                for _part_index, part_file_path in sorted(
                    results, key=lambda x: x[0]
                ):
                    try:
                        part_bytes = 0

                        async with aiopen(part_file_path, "rb") as part_file:
                            while True:
                                chunk = await part_file.read(8 * 1024 * 1024)
                                if not chunk:
                                    break
                                await temp_file.write(chunk)
                                part_bytes += len(chunk)
                                total_bytes_combined += len(chunk)

                        await remove(part_file_path)

                    except Exception:
                        raise

            if prog_task and not prog_task.done():
                prog_task.cancel()

            file_path = ospath.splitext(temp_file_path)[0]
            await move(temp_file_path, file_path)

            download_time = time() - download_start_time
            speed = (
                (total_bytes_combined / (1024 * 1024)) / download_time
                if download_time > 0
                else 0
            )
            LOGGER.info("HyperDL download completed successfully!")

            return file_path

        except FloodWait as fw:
            LOGGER.warning(f"FloodWait encountered: {fw.value}s")
            raise fw
        except (CancelledError, StopTransmission):
            LOGGER.info("Download cancelled by user")
            return None
        except Exception:
            return None
        finally:
            self._cancel_event.set()

            if prog_task and not prog_task.done():
                prog_task.cancel()

            for task in tasks:
                if not task.done():
                    task.cancel()

            # Clean up temporary part files
            for i in range(len(ranges) if "ranges" in locals() else 0):
                part_path = ospath.join(
                    self.directory, f"{self.file_name}.temp.{i:02d}"
                )
                try:
                    if ospath.exists(part_path):
                        await remove(part_path)
                except Exception:
                    pass

    @staticmethod
    async def get_extension(file_type, mime_type):
        if file_type in PHOTO_TYPES:
            return ".jpg"

        if mime_type:
            extension = guess_extension(mime_type)
            if extension:
                return extension

        # Fallback based on file type
        extension_map = {
            FileType.VOICE: ".ogg",
            FileType.VIDEO: ".mp4",
            FileType.ANIMATION: ".mp4",
            FileType.VIDEO_NOTE: ".mp4",
            FileType.DOCUMENT: ".bin",
            FileType.STICKER: ".webp",
            FileType.AUDIO: ".mp3",
        }

        return extension_map.get(file_type, ".bin")

    async def download_media(
        self,
        message,
        file_name="downloads/",
        progress=None,
        progress_args=(),
        dump_chat=None,
    ):
        try:
            # First, verify that the original message has downloadable media
            try:
                # Check if message is a valid message object
                if not message:
                    LOGGER.error("❌ Message is None")
                    raise ValueError("Message is None")

                # Check if message has basic attributes we expect
                if not hasattr(message, "chat") or not hasattr(message, "id"):
                    LOGGER.error("❌ Message object is missing required attributes")
                    raise ValueError("Message object is missing required attributes")

                # Try to get media from the message
                original_media = await self.get_media_type(message)
                if not original_media:
                    # This should never happen as get_media_type should raise an exception if no media is found
                    LOGGER.error(
                        "❌ Original message doesn't contain any downloadable media"
                    )
                    raise ValueError(
                        "Original message doesn't contain any downloadable media"
                    )

            except ValueError:
                # This is a specific error we're expecting
                raise
            except Exception as e:
                # This is an unexpected error
                LOGGER.error(f"❌ Failed to verify original message media: {e!s}")
                raise ValueError("Failed to verify original message media") from e

            if dump_chat:
                message_copied = False

                # Try multiple times to ensure successful copy
                max_attempts = 3

                try:
                    for attempt in range(max_attempts):
                        # Handle case where dump_chat is a list - use the first item
                        chat_id = (
                            dump_chat[0]
                            if isinstance(dump_chat, list)
                            else dump_chat
                        )

                        # Check bot permissions in dump chat first
                        try:
                            await TgClient.bot.get_chat(chat_id)

                            # Check if bot is admin or has necessary permissions
                            try:
                                await TgClient.bot.get_chat_member(
                                    chat_id, TgClient.bot.me.id
                                )
                            except Exception as perm_error:
                                LOGGER.warning(
                                    f"⚠️ Could not check bot permissions: {perm_error!s}"
                                )

                        except Exception as e:
                            LOGGER.error(
                                f"❌ Bot cannot access dump chat {chat_id}: {e!s}"
                            )
                            if attempt == max_attempts - 1:
                                break
                            continue

                        # Add small delay and session refresh between attempts
                        if attempt > 0:
                            await sleep(1)
                            # Refresh bot session to get latest permissions
                            await self._refresh_bot_session()

                        # Use main bot to copy message to dump chat
                        try:
                            # Use the original message object directly (don't retrieve again)
                            # Check what type of media it has using Kurigram's approach
                            try:
                                # Use the same media detection as telegram_download.py on the original message
                                media = (
                                    message.document
                                    or message.photo
                                    or message.video
                                    or message.audio
                                    or message.voice
                                    or message.video_note
                                    or message.sticker
                                    or message.animation
                                    or None
                                )

                                if media:
                                    type(media).__name__
                                else:
                                    LOGGER.warning(
                                        "⚠️ No media found in original message"
                                    )
                                    if attempt == max_attempts - 1:
                                        break
                                    continue
                            except Exception as media_error:
                                LOGGER.warning(
                                    f"⚠️ Could not get media info: {media_error!s}"
                                )
                                if attempt == max_attempts - 1:
                                    break
                                continue

                            # Now copy the message using Kurigram's approach
                            try:
                                # Method 1: Try using message.copy() method (Kurigram specific)
                                try:
                                    copied_msg = await message.copy(
                                        chat_id=chat_id,
                                        disable_notification=True,
                                    )
                                except Exception as copy_method_error:
                                    LOGGER.warning(
                                        f"⚠️ Message.copy() failed: {copy_method_error!s}"
                                    )
                                    # Method 2: Fallback to Client.copy_message
                                    copied_msg = await TgClient.bot.copy_message(
                                        chat_id=chat_id,
                                        from_chat_id=message.chat.id,
                                        message_id=message.id,
                                        disable_notification=True,
                                    )

                            except Exception as copy_api_error:
                                LOGGER.error(
                                    f"❌ All copy methods failed: {copy_api_error!s}"
                                )
                                if attempt == max_attempts - 1:
                                    break
                                continue

                            # Check if copy was successful
                            if copied_msg and hasattr(copied_msg, "id"):
                                # Verify the copied message has media using Kurigram approach
                                try:
                                    # Get the copied message to verify it has media
                                    copied_message_obj = (
                                        await TgClient.bot.get_messages(
                                            chat_id, copied_msg.id
                                        )
                                    )
                                    if copied_message_obj:
                                        # Check media using the same logic
                                        copied_media = (
                                            copied_message_obj.document
                                            or copied_message_obj.photo
                                            or copied_message_obj.video
                                            or copied_message_obj.audio
                                            or copied_message_obj.voice
                                            or copied_message_obj.video_note
                                            or copied_message_obj.sticker
                                            or copied_message_obj.animation
                                            or None
                                        )

                                        if copied_media:
                                            self.message = copied_message_obj
                                            message_copied = True
                                            break
                                        LOGGER.warning(
                                            "Copied message doesn't have media"
                                        )
                                        if attempt == max_attempts - 1:
                                            break
                                        continue
                                    LOGGER.warning(
                                        "Could not retrieve copied message"
                                    )
                                    if attempt == max_attempts - 1:
                                        break
                                    continue
                                except Exception as verify_error:
                                    LOGGER.warning(
                                        f"Failed to verify copied message: {verify_error!s}"
                                    )
                                    if attempt == max_attempts - 1:
                                        break
                                    continue
                            else:
                                LOGGER.warning(
                                    f"Copy operation returned invalid result: {copied_msg}"
                                )
                                if attempt == max_attempts - 1:
                                    LOGGER.error("All copy attempts failed")
                                    break
                                # Continue to next attempt
                                continue

                        except Exception as copy_error:
                            LOGGER.warning(
                                f"Copy attempt {attempt + 1} failed: {copy_error!s}"
                            )
                            if attempt == max_attempts - 1:
                                LOGGER.error("All copy attempts failed")
                                break
                            # Continue to next attempt
                            continue

                    # Verify that the copied message has downloadable media
                    if message_copied:
                        try:
                            await self.get_media_type(self.message)
                        except Exception as e:
                            # Fall back to using the original message
                            LOGGER.warning(
                                f"⚠️ Copied message verification failed: {e!s}"
                            )
                            self.message = message
                            message_copied = False

                except Exception as e:
                    # Fall back to using the original message
                    LOGGER.warning(f"⚠️ Copy process failed: {e!s}")
                    self.message = message
                    message_copied = False

                # If we couldn't copy the message, check if we can still use HyperDL
                if not message_copied:
                    # Check if helper bots have access to the original chat
                    try:
                        has_access = await self._check_helper_bot_access(
                            message.chat.id
                        )
                        if not has_access:
                            LOGGER.error(
                                "HyperDL cannot work: Copy to dump chat failed AND helper bots can't access original chat"
                            )
                            LOGGER.warning("Falling back to regular download method")
                            raise ValueError(
                                "HyperDL requires either: 1) Successful copy to dump chat, OR 2) Helper bots access to source chat. "
                                "Currently neither is working."
                            )
                    except Exception as access_check_error:
                        LOGGER.error(
                            f"Error checking helper bot access: {access_check_error!s}"
                        )
                        # Fall back to regular download
                        raise ValueError(
                            f"Failed to check helper bot access: {access_check_error!s}"
                        )

            else:
                self.message = message
                message_copied = False

            # Handle case where dump_chat is a list
            if dump_chat and message_copied:
                # Only use dump_chat if we successfully copied the message
                self.dump_chat = dump_chat
            else:
                # Use original chat if no dump chat or if we're using original message
                self.dump_chat = message.chat.id

            media = await self.get_media_type(self.message)

            file_id_str = media if isinstance(media, str) else media.file_id
            file_id_obj = FileId.decode(file_id_str)

            file_type = file_id_obj.file_type
            media_file_name = getattr(media, "file_name", "")
            self.file_size = getattr(media, "file_size", 0)
            mime_type = getattr(media, "mime_type", "image/jpeg")
            date = getattr(media, "date", None)

            self.directory, self.file_name = ospath.split(file_name)
            self.file_name = self.file_name or media_file_name or ""

            if not ospath.isabs(self.file_name):
                self.directory = Path(argv[0]).parent / (
                    self.directory or self.download_dir
                )

            if not self.file_name:
                extension = await self.get_extension(file_type, mime_type)
                self.file_name = f"{FileType(file_id_obj.file_type).name.lower()}_{(date or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}_{MsgId()}{extension}"

            return await self.handle_download(progress, progress_args)

        except Exception as e:
            LOGGER.error(f"HyperDL download_media failed: {e!s}")
            raise
