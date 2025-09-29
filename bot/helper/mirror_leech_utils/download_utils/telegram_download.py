from asyncio import Lock, create_task, sleep
from secrets import token_hex
from time import time

# Import errors from kurigram/pyrofork with compatibility
try:
    from pyrogram.errors import FloodPremiumWait, FloodWait, StopTransmissionError
except ImportError:
    # FloodPremiumWait not available in pyrofork 2.2.11
    try:
        from pyrogram.errors import FloodWait, StopTransmissionError

        FloodPremiumWait = FloodWait  # Use FloodWait as fallback
    except ImportError:
        from pyrogram.errors import FloodWait

        FloodPremiumWait = FloodWait  # Use FloodWait as fallback
        StopTransmissionError = None

try:
    from bot import LOGGER, task_dict, task_dict_lock
except ImportError:
    # Fallback logger in case of import issues
    from asyncio import Lock
    from logging import getLogger

    LOGGER = getLogger(__name__)
    task_dict = {}
    task_dict_lock = Lock()
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.hyperdl_utils import HyperTGDownload
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
)
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.mirror_leech_utils.status_utils.telegram_status import TelegramStatus
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
    send_status_message,
)

global_lock = Lock()
GLOBAL_GID = set()


class TelegramDownloadHelper:
    def __init__(self, listener):
        self._processed_bytes = 0
        self._start_time = 1
        self._listener = listener
        self._id = ""
        self.session = ""
        self._hyper_dl = (
            Config.HYPERDL_ENABLED
            and TgClient.are_helper_bots_available()
            and Config.LEECH_DUMP_CHAT
        )

    @property
    def speed(self):
        return self._processed_bytes / (time() - self._start_time)

    @property
    def processed_bytes(self):
        return self._processed_bytes

    async def _on_download_start(self, file_id, from_queue):
        global LOGGER  # Ensure LOGGER is treated as global
        async with global_lock:
            GLOBAL_GID.add(file_id)
        self._id = file_id
        async with task_dict_lock:
            # Convert file_id to string before slicing
            file_id_str = str(file_id)
            task_dict[self._listener.mid] = TelegramStatus(
                self._listener,
                self,
                file_id_str[:12],
                "dl",
            )
        if not from_queue:
            await self._listener.on_download_start()
            if self._listener.multi <= 1:
                await send_status_message(self._listener.message)
            LOGGER.info(f"Download from Telegram: {self._listener.name}")
        else:
            LOGGER.info(
                f"Start Queued Download from Telegram: {self._listener.name}",
            )

    async def _on_download_progress(self, current, total=None):
        if self._listener.is_cancelled:
            # Handle different client implementations
            if hasattr(self.session, "stop_transmission"):
                self.session.stop_transmission()
            elif hasattr(self.session, "cancel"):
                self.session.cancel()
        self._processed_bytes = current

    async def _on_download_error(self, error):
        global LOGGER  # Ensure LOGGER is treated as global
        async with global_lock:
            GLOBAL_GID.discard(self._id)
        try:
            await self._listener.on_download_error(error)
        except Exception as e:
            LOGGER.error(f"Failed to handle error through listener: {e!s}")
            # Fallback error handling
            error_msg = await send_message(
                self._listener.message,
                f"{self._listener.tag} {error}",
            )
            create_task(auto_delete_message(error_msg, time=300))  # noqa: RUF006

    async def _on_download_complete(self):
        global LOGGER  # Ensure LOGGER is treated as global
        async with global_lock:
            # Safely remove ID from GLOBAL_GID if it exists
            GLOBAL_GID.discard(self._id)
        try:
            await self._listener.on_download_complete()
        except Exception as e:
            LOGGER.error(f"Error in download complete handler: {e}")
            # Try to handle the error gracefully
            try:
                await self._listener.on_download_error(
                    f"Post-download processing error: {e}"
                )
            except Exception as inner_e:
                LOGGER.error(f"Failed to handle download complete error: {inner_e}")

    async def _download(self, message, path):
        global LOGGER  # Ensure LOGGER is treated as global
        try:
            if self._hyper_dl:
                try:
                    # First check if the message has downloadable media
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

                    if not media:
                        raise ValueError(
                            "Message doesn't contain any downloadable media"
                        )

                    download = await HyperTGDownload().download_media(
                        message,
                        file_name=path,
                        progress=self._on_download_progress,
                        dump_chat=Config.LEECH_DUMP_CHAT,
                    )

                except ValueError:
                    # This is a configuration or media error, fall back to normal download
                    self._hyper_dl = False
                    download = await message.download(
                        file_name=path,
                        progress=self._on_download_progress,
                    )
                except Exception:
                    # This is an unexpected error, fall back to normal download
                    download = await message.download(
                        file_name=path,
                        progress=self._on_download_progress,
                    )
            else:
                download = await message.download(
                    file_name=path,
                    progress=self._on_download_progress,
                )

            if self._listener.is_cancelled:
                return
        except (FloodWait, FloodPremiumWait) as f:
            await sleep(f.value)
            await self._download(message, path)
            return
        except OSError as e:
            # Check specifically for "No space left on device" error
            if e.errno == 28:  # errno 28 is "No space left on device"
                error_msg = "No space left on device. Please free up some disk space and try again."
                LOGGER.error(f"{error_msg} Path: {path}")
                await self._on_download_error(error_msg)
            else:
                LOGGER.error(f"OSError: {e}")
                await self._on_download_error(str(e))
            return
        except Exception as e:
            LOGGER.error(str(e))
            await self._on_download_error(str(e))
            return
        if download is not None:
            try:
                await self._on_download_complete()
            except Exception as e:
                LOGGER.error(f"Critical error in download complete: {e}")
                # Ensure we don't leave the task in an inconsistent state
                try:
                    await self._on_download_error(f"Download completion failed: {e}")
                except Exception as inner_e:
                    LOGGER.error(
                        f"Failed to handle critical download error: {inner_e}"
                    )
        elif not self._listener.is_cancelled:
            await self._on_download_error("Internal error occurred")

    async def add_download(self, message, path, session):
        global LOGGER  # Ensure LOGGER is treated as global
        self.session = session
        if not self.session:
            if self._hyper_dl:
                self.session = "hbots"
            elif (
                self._listener.user_transmission
                and hasattr(self._listener, "is_super_chat")
                and callable(getattr(self._listener, "is_super_chat", None)) is False
                and self._listener.is_super_chat
            ):
                self.session = TgClient.user
                try:
                    # Get the message by its ID with Electrogram compatibility
                    try:
                        message = await self.session.get_messages(
                            chat_id=message.chat.id,
                            message_ids=message.id,
                        )
                    except TypeError as e:
                        # Handle case where get_messages has different parameters in Electrogram
                        if "unexpected keyword argument" in str(e):
                            # Try alternative approach for Electrogram
                            message = await self.session.get_messages(
                                message.chat.id,  # chat_id as positional argument
                                message.id,  # message_ids as positional argument
                            )
                        else:
                            raise
                except Exception as e:
                    LOGGER.warning(
                        f"User session error: {e!s}, falling back to bot session"
                    )
                    self.session = TgClient.bot
            else:
                self.session = TgClient.bot
        elif self.session != TgClient.bot:
            # Get the message by its ID with Electrogram compatibility
            try:
                message = await self.session.get_messages(
                    chat_id=message.chat.id,
                    message_ids=message.id,
                )
            except TypeError as e:
                # Handle case where get_messages has different parameters in Electrogram
                if "unexpected keyword argument" in str(e):
                    # Try alternative approach for Electrogram
                    message = await self.session.get_messages(
                        message.chat.id,  # chat_id as positional argument
                        message.id,  # message_ids as positional argument
                    )
                else:
                    raise

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
            async with global_lock:
                download = media.file_unique_id not in GLOBAL_GID

            if download:
                if not self._listener.name:
                    if hasattr(media, "file_name") and media.file_name:
                        if "/" in media.file_name:
                            self._listener.name = media.file_name.rsplit("/", 1)[-1]
                            path = path + self._listener.name
                        else:
                            self._listener.name = media.file_name
                    else:
                        self._listener.name = "None"
                else:
                    path = path + self._listener.name
                self._listener.size = media.file_size
                gid = token_hex(4)

                # Check size limits
                if self._listener.size > 0:
                    limit_msg = await limit_checker(
                        self._listener.size,
                        self._listener,
                        isTorrent=False,
                        isMega=False,
                        isDriveLink=False,
                        isYtdlp=False,
                    )
                    if limit_msg:
                        await self._listener.on_download_error(limit_msg)
                        return

                msg, button = await stop_duplicate_check(self._listener)
                if msg:
                    await self._listener.on_download_error(msg, button)
                    return

                add_to_queue, event = await check_running_tasks(self._listener)
                if add_to_queue:
                    async with task_dict_lock:
                        task_dict[self._listener.mid] = QueueStatus(
                            self._listener,
                            gid,
                            "dl",
                        )
                    await self._listener.on_download_start()
                    if self._listener.multi <= 1:
                        await send_status_message(self._listener.message)
                    await event.wait()
                    if self._listener.is_cancelled:
                        async with global_lock:
                            # Safely remove ID from GLOBAL_GID if it exists
                            if self._id in GLOBAL_GID:
                                GLOBAL_GID.remove(self._id)
                            elif self._id:  # Only log if _id is not empty
                                pass
                            return

                self._start_time = time()
                await self._on_download_start(gid, add_to_queue)

                # Check if helper bots are available and LEECH_DUMP_CHAT is set before starting download
                if self._hyper_dl and (
                    not TgClient.are_helper_bots_available()
                    or not Config.LEECH_DUMP_CHAT
                    or len(Config.LEECH_DUMP_CHAT) == 0
                ):
                    self._hyper_dl = False

                await self._download(message, path)
            else:
                await self._on_download_error("File already being downloaded!")
        else:
            await self._on_download_error(
                "No document in the replied message! Use SuperGroup incase you are trying to download with User session!",
            )

    async def cancel_task(self):
        self._listener.is_cancelled = True
        await self._on_download_error("Stopped by user!")
