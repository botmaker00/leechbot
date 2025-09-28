import contextlib
import gc
import os
import re
from asyncio import sleep
from logging import getLogger
from os import listdir, walk
from os import path as ospath
from re import match as re_match
from re import sub as re_sub
from time import time

import psutil
from aiofiles.os import path as aiopath
from aioshutil import rmtree
from natsort import natsorted
from PIL import Image
from pyrogram import enums

# Smart import for FloodPremiumWait compatibility
try:
    from pyrogram.errors import BadRequest, FloodPremiumWait, FloodWait, RPCError
except ImportError:
    # FloodPremiumWait not available in pyrofork 2.2.11, use FloodWait as fallback
    from pyrogram.errors import BadRequest, FloodWait, RPCError

    FloodPremiumWait = FloodWait  # Use FloodWait as fallback
from pyrogram.types import InputMediaDocument, InputMediaPhoto, InputMediaVideo
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot import excluded_extensions, user_data
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.aeon_utils.caption_gen import generate_caption
from bot.helper.ext_utils.aiofiles_compat import path as aiopath
from bot.helper.ext_utils.aiofiles_compat import remove, rename
from bot.helper.ext_utils.auto_thumbnail import AutoThumbnailHelper
from bot.helper.ext_utils.bot_utils import sync_to_async
from bot.helper.ext_utils.files_utils import get_base_name, is_archive
from bot.helper.ext_utils.font_utils import apply_font_style
from bot.helper.ext_utils.media_utils import (
    get_audio_thumbnail,
    get_document_type,
    get_media_info,
    get_multiple_frames_thumbnail,
    get_video_thumbnail,
)
from bot.helper.ext_utils.template_processor import (
    extract_metadata_from_filename,
    process_template,
)
from bot.helper.telegram_helper.message_utils import delete_message

LOGGER = getLogger(__name__)


def get_memory_usage():
    """Get current memory usage percentage"""
    try:
        return psutil.virtual_memory().percent
    except Exception:
        return 0


async def wait_for_memory_availability(max_memory_percent=80, max_wait_time=60):
    """Wait for memory usage to drop below threshold"""
    start_time = time()
    while time() - start_time < max_wait_time:
        memory_percent = get_memory_usage()
        if memory_percent < max_memory_percent:
            return True
        LOGGER.warning(
            f"Memory usage high ({memory_percent}%). Waiting for memory to free up..."
        )
        gc.collect()
        await sleep(2)
    return False


class TelegramUploader:
    def __init__(self, listener, path):
        self._last_uploaded = 0
        self._processed_bytes = 0
        self._listener = listener
        self._user_id = listener.user_id
        self._path = path
        self._start_time = time()
        self._total_files = 0
        self._thumb = self._listener.thumb or f"thumbnails/{listener.user_id}.jpg"
        self._msgs_dict = {}
        self._corrupted = 0
        self._is_corrupted = False
        self._media_dict = {"videos": {}, "documents": {}}
        self._last_msg_in_group = False
        self._up_path = ""
        self._lprefix = ""
        self._lsuffix = ""
        self._lfont = ""
        self._user_dump = ""
        self._lcaption = ""
        self._media_group = False
        self._is_private = False
        self._sent_msg = None
        self.log_msg = None

        # Smart client selection with automatic hybrid leech management
        from bot.core.aeon_client import TgClient

        # Auto-disable hybrid leech if user session is not available or user transmission is off
        effective_hybrid_leech = (
            self._listener.hybrid_leech
            and self._listener.user_transmission
            and TgClient.user is not None
        )

        if self._listener.hybrid_leech and not effective_hybrid_leech:
            LOGGER.info(
                "🔧 Auto-disabling hybrid leech: User session unavailable or user transmission disabled"
            )

        # Set initial user session based on user transmission setting
        # User transmission works independently of hybrid leech
        self._user_session = (
            self._listener.user_transmission and TgClient.user is not None
        )

        # Store effective hybrid leech setting for later use
        self._effective_hybrid_leech = effective_hybrid_leech

        self._error = ""

        # Streamrip-specific attributes
        self._is_streamrip = hasattr(listener, "url") and hasattr(
            listener, "quality"
        )
        self._streamrip_platform = getattr(listener, "platform", None)
        self._streamrip_media_type = getattr(listener, "media_type", None)

        # Zotify-specific attributes
        self._is_zotify = hasattr(listener, "tool") and listener.tool == "zotify"
        self._zotify_platform = "spotify"  # Zotify is always Spotify

        # Flag to prevent multiple stop_transmission calls
        self._transmission_stopped = False

    def _apply_prefix_suffix_simple(self, filename):
        """Apply prefix and suffix to filename - Old Aeon-MLTB style"""
        if not self._lprefix and not self._lsuffix:
            return filename

        result = filename

        # Apply prefix (like old Aeon-MLTB)
        if self._lprefix:
            clean_prefix = re_sub("<.*?>", "", self._lprefix)
            if clean_prefix and not result.startswith(clean_prefix):
                # Add space if prefix doesn't end with one
                if not clean_prefix.endswith(" "):
                    clean_prefix = f"{clean_prefix} "
                result = f"{clean_prefix}{result}"

        # Apply suffix (like old Aeon-MLTB)
        if self._lsuffix:
            clean_suffix = re_sub("<.*?>", "", self._lsuffix)
            if clean_suffix:
                # Handle split files correctly
                if re.match(r"(.+)(\.\w+)(\.\d{3})$", result):
                    # For .ext.001 files: name.ext.001 -> name suffix.ext.001
                    match = re.match(r"(.+)(\.\w+)(\.\d{3})$", result)
                    base_name, ext, split_num = match.groups()
                    if not clean_suffix.startswith(" "):
                        clean_suffix = f" {clean_suffix}"
                    result = f"{base_name}{clean_suffix}{ext}{split_num}"
                elif re.match(r"(.+)(\.part\d+)(\..+)$", result):
                    # For .part001.ext files: name.part001.ext -> name suffix.part001.ext
                    match = re.match(r"(.+)(\.part\d+)(\..+)$", result)
                    base_name, part_num, ext = match.groups()
                    if not clean_suffix.startswith(" "):
                        clean_suffix = f" {clean_suffix}"
                    result = f"{base_name}{clean_suffix}{part_num}{ext}"
                # Regular files: name.ext -> name suffix.ext
                elif "." in result:
                    name, ext = ospath.splitext(result)
                    if not clean_suffix.startswith(" "):
                        clean_suffix = f" {clean_suffix}"
                    result = f"{name}{clean_suffix}{ext}"
                # Files without extension: name -> name suffix
                else:
                    if not clean_suffix.startswith(" "):
                        clean_suffix = f" {clean_suffix}"
                    result = f"{result}{clean_suffix}"

        return result

    def _get_original_filename_for_thumbnail(self, filename):
        """
        Get the original filename for auto thumbnail generation.
        For split files (e.g., movie.mkv.001, movie.mkv.002), returns the original filename (movie.mkv).
        For regular files, returns the filename as-is.
        """

        # Check for split file patterns
        # Pattern 1: filename.ext.001, filename.ext.002, etc.
        match = re.match(r"(.+\.\w+)\.(\d{3})$", filename)
        if match:
            return match.group(1)  # Return filename.ext without the .001 part

        # Pattern 2: filename.part001.ext, filename.part002.ext, etc.
        match = re.match(r"(.+)\.part\d+(\.\w+)$", filename)
        if match:
            return f"{match.group(1)}{match.group(2)}"  # Return filename.ext without the .part001 part

        # Pattern 3: filename.001, filename.002 (no extension before split number)
        match = re.match(r"(.+)\.(\d{3})$", filename)
        if match:
            # This is trickier - we need to guess the original extension
            # For now, return the base name and let the auto thumbnail helper handle it
            return match.group(1)

        # Not a split file, return as-is
        return filename

    def _build_caption_with_html_prefix_suffix(self, core_content):
        """
        Build caption with HTML prefix and suffix around core content - Old Aeon-MLTB style.
        HTML tags are preserved for Telegram rendering.
        """
        caption = core_content

        # Add HTML prefix if available (preserve HTML tags for caption)
        if self._lprefix:
            # Add space after prefix if it doesn't end with one and doesn't end with HTML tag
            if not self._lprefix.endswith(" ") and not self._lprefix.endswith(">"):
                caption = f"{self._lprefix} {caption}"
            else:
                caption = f"{self._lprefix}{caption}"

        # Add HTML suffix if available (preserve HTML tags for caption)
        if self._lsuffix:
            # Add space before suffix if it doesn't start with one and doesn't start with HTML tag
            if not self._lsuffix.startswith(" ") and not self._lsuffix.startswith(
                "<"
            ):
                caption = f"{caption} {self._lsuffix}"
            else:
                caption = f"{caption}{self._lsuffix}"

        return caption

    def _is_bot_pm_enabled(self):
        """Check if BOT_PM is enabled with user priority over owner config"""
        user_dict = user_data.get(self._user_id, {})
        bot_pm_enabled = user_dict.get("BOT_PM", None)
        if bot_pm_enabled is None:
            bot_pm_enabled = Config.BOT_PM
        return bot_pm_enabled

    async def _upload_progress(self, current, _):
        if self._listener.is_cancelled and not self._transmission_stopped:
            try:
                if self._user_session and TgClient.user:
                    TgClient.user.stop_transmission()
                elif self._listener.client:
                    self._listener.client.stop_transmission()
                self._transmission_stopped = (
                    True  # Set flag to prevent further calls
                )
            except Exception:
                self._transmission_stopped = (
                    True  # Set flag even on error to prevent spam
                )
            return  # Exit early when cancelled to prevent further progress monitoring

        # Skip progress monitoring if already cancelled
        if self._listener.is_cancelled:
            return

        chunk_size = current - self._last_uploaded
        self._last_uploaded = current
        self._processed_bytes += chunk_size

    async def _user_settings(self):
        self._media_group = self._listener.user_dict.get("MEDIA_GROUP") or (
            Config.MEDIA_GROUP
            if "MEDIA_GROUP" not in self._listener.user_dict
            else False
        )

        # Use the same logic as old Aeon-MLTB for consistency
        self._lprefix = self._listener.user_dict.get("LEECH_FILENAME_PREFIX") or (
            Config.LEECH_FILENAME_PREFIX
            if "LEECH_FILENAME_PREFIX" not in self._listener.user_dict
            else ""
        )
        self._lsuffix = self._listener.user_dict.get("LEECH_SUFFIX") or (
            Config.LEECH_SUFFIX
            if "LEECH_SUFFIX" not in self._listener.user_dict
            else ""
        )

        self._lfont = self._listener.user_dict.get("LEECH_FONT") or (
            Config.LEECH_FONT if "LEECH_FONT" not in self._listener.user_dict else ""
        )
        self._lfilename = self._listener.user_dict.get("LEECH_FILENAME") or (
            Config.LEECH_FILENAME
            if "LEECH_FILENAME" not in self._listener.user_dict
            else ""
        )
        # Universal filename template (lower priority than leech filename)
        self._universal_filename = self._listener.user_dict.get(
            "UNIVERSAL_FILENAME"
        ) or (
            Config.UNIVERSAL_FILENAME
            if "UNIVERSAL_FILENAME" not in self._listener.user_dict
            else ""
        )
        self._user_dump = self._listener.user_dict.get("USER_DUMP")
        self._lcaption = self._listener.user_dict.get("LEECH_FILENAME_CAPTION") or (
            Config.LEECH_FILENAME_CAPTION
            if "LEECH_FILENAME_CAPTION" not in self._listener.user_dict
            else ""
        )
        if self._thumb != "none" and not await aiopath.exists(self._thumb):
            self._thumb = None

    def _build_caption_with_prefix_suffix(self, core_content):
        """
        Build caption with HTML prefix and suffix around core content - Old Aeon-MLTB style.
        Uses the new HTML-aware method for consistent behavior.
        """
        return self._build_caption_with_html_prefix_suffix(core_content)

    async def _msg_to_reply(self):
        if self._listener.up_dest:
            msg = self._listener.message.text.lstrip("/")
            try:
                if self._user_session:
                    self._sent_msg = await TgClient.user.send_message(
                        chat_id=self._listener.up_dest,
                        text=msg,
                        disable_web_page_preview=True,
                        message_thread_id=self._listener.chat_thread_id,
                        disable_notification=True,
                    )
                else:
                    self._sent_msg = await self._listener.client.send_message(
                        chat_id=self._listener.up_dest,
                        text=msg,
                        disable_web_page_preview=True,
                        message_thread_id=self._listener.chat_thread_id,
                        disable_notification=True,
                    )
                    self._is_private = self._sent_msg.chat.type.name == "PRIVATE"
                self.log_msg = self._sent_msg
            except Exception as e:
                await self._listener.on_upload_error(str(e))
                return False
        elif self._user_session:
            self._sent_msg = await TgClient.user.get_messages(
                chat_id=self._listener.message.chat.id,
                message_ids=self._listener.mid,
            )
            if self._sent_msg is None:
                self._sent_msg = await TgClient.user.send_message(
                    chat_id=self._listener.message.chat.id,
                    text="Deleted Cmd Message! Don't delete the cmd message again!",
                    disable_web_page_preview=True,
                    disable_notification=True,
                )
        else:
            self._sent_msg = self._listener.message
        return True

    async def _prepare_file(self, file_, dirpath):
        import gc

        # re module is already imported at the top of the file
        # re_match and re_sub are already imported at the top of the file
        # font_utils and template_processor are already imported at the top of the file
        # Initialize caption
        cap_mono = None
        final_filename = file_

        try:
            # Extract file metadata for template variables
            file_metadata = {}
            # Extract basic file info
            name, ext = ospath.splitext(file_)
            if ext:
                ext = ext[1:]  # Remove the dot

            # Extract metadata from filename using our helper function
            metadata = await extract_metadata_from_filename(name)

            # Populate metadata dictionary
            file_metadata = {
                "filename": name,
                "ext": ext,
                **metadata,  # Include all extracted metadata
            }

            # We'll generate caption after file renaming to ensure we use the correct file path
            cap_mono = None

            # Process filename modifications with correct priority order:
            # 1. Apply leech filename template first
            # 2. Apply leech caption second (uses changed filename)
            # 3. Apply prefix and suffix last (independent from caption)

            # Initialize working filename
            working_filename = file_
            core_filename = file_  # For caption processing

            # Step 1: Apply filename template with priority: LEECH_FILENAME > UNIVERSAL_FILENAME
            filename_template = None
            template_type = None

            if self._lfilename:
                filename_template = self._lfilename
                template_type = "leech"
            elif self._universal_filename:
                filename_template = self._universal_filename
                template_type = "universal"

            if filename_template:
                try:
                    # Process the template with file metadata
                    processed_filename = await process_template(
                        filename_template, file_metadata
                    )
                    if processed_filename:
                        # Strip HTML tags from the processed filename for file system compatibility
                        clean_filename = re_sub(r"<[^>]+>", "", processed_filename)

                        # Keep the original extension if not included in the template
                        if ext and not clean_filename.endswith(f".{ext}"):
                            working_filename = f"{clean_filename}.{ext}"
                            core_filename = f"{clean_filename}.{ext}"
                        else:
                            working_filename = clean_filename
                            core_filename = clean_filename
                        LOGGER.info(
                            f"Applied {template_type} filename template: {working_filename}"
                        )
                except Exception as e:
                    LOGGER.error(
                        f"Error applying {template_type} filename template: {e}"
                    )
                    # Continue with the current working_filename

            # Step 2: Generate leech caption BEFORE applying prefix/suffix
            # This ensures leech caption gets the changed filename but NOT prefix/suffix
            has_leech_caption = bool(self._lcaption)
            if self._lcaption:
                # Rename the file first so caption generation uses the correct filename
                if working_filename != file_:
                    new_path = ospath.join(dirpath, working_filename)
                    LOGGER.info(
                        f"Renaming for caption: {self._up_path} -> {new_path}"
                    )
                    await rename(self._up_path, new_path)
                    self._up_path = new_path

                # Use the current file path (which reflects leech filename changes)
                current_filename = ospath.basename(self._up_path)
                current_dirpath = ospath.dirname(self._up_path)

                # Generate caption using the changed filename
                cap_mono = await generate_caption(
                    current_filename,
                    current_dirpath,
                    self._lcaption,
                    self._lprefix,  # Pass HTML prefix directly
                    self._lsuffix,  # Pass HTML suffix directly
                )

                # Set final filename for further processing
                final_filename = working_filename
            else:
                # No leech caption - generate default caption
                # Apply font style if specified (for caption display)
                if self._lfont:
                    # Apply the font style to the core filename only
                    try:
                        styled_core = await apply_font_style(
                            core_filename, self._lfont
                        )
                        # Set caption to styled core (prefix/suffix will be added later)
                        cap_mono = styled_core
                        LOGGER.info(
                            f"Applied font style '{self._lfont}' to filename"
                        )
                    except Exception as e:
                        LOGGER.error(f"Error applying font style: {e}")
                        # If font styling fails, use the core filename with HTML formatting
                        cap_mono = f"<code>{core_filename}</code>"
                    # Force garbage collection after font styling
                    gc.collect()
                else:
                    # Build default caption with <code>core</code>
                    styled_core = f"<code>{core_filename}</code>"

                    # Enhanced caption for streamrip downloads
                    if self._is_streamrip and self._streamrip_platform:
                        # Add streamrip platform info to caption
                        platform_emoji = {
                            "deezer": "🎵",
                            "qobuz": "🎼",
                            "tidal": "🌊",
                            "soundcloud": "☁️",
                            "spotify": "🎧",
                            "apple_music": "🍎",
                        }.get(self._streamrip_platform.lower(), "🎶")

                        styled_core = f"<code>{platform_emoji} {self._streamrip_platform.title()}\n{core_filename}</code>"

                    # Enhanced caption for zotify downloads
                    elif self._is_zotify:
                        # Add zotify platform info to caption
                        styled_core = f"<code>🎧 Spotify\n{core_filename}</code>"

                    cap_mono = styled_core

                # Set final filename for file operations
                final_filename = working_filename

            # Step 3: Apply prefix and suffix to filename - Old Aeon-MLTB style
            original_filename = final_filename
            final_filename = self._apply_prefix_suffix_simple(final_filename)

            # Log only if filename actually changed
            if final_filename != original_filename:
                LOGGER.info(
                    f"Applied prefix/suffix: {original_filename} -> {final_filename}"
                )

            # Add HTML prefix/suffix to caption for default captions - Old Aeon-MLTB style
            if cap_mono and not has_leech_caption:
                cap_mono = self._build_caption_with_html_prefix_suffix(cap_mono)

            # Rename the file with the final filename (if not already renamed for caption)
            current_basename = ospath.basename(self._up_path)
            if final_filename != current_basename:
                new_path = ospath.join(dirpath, final_filename)
                try:
                    # Check if source file actually exists before attempting rename
                    if await aiopath.exists(self._up_path):
                        await rename(self._up_path, new_path)
                        self._up_path = new_path
                        LOGGER.info(f"File renamed to: {final_filename}")
                    else:
                        # Source file doesn't exist at expected path, try to find the actual file
                        LOGGER.warning(f"Source file not found: {self._up_path}")

                        # Try to find the file with current basename in the directory
                        potential_path = ospath.join(dirpath, current_basename)

                        if await aiopath.exists(potential_path):
                            self._up_path = potential_path
                            await rename(self._up_path, new_path)
                            # Update path to the actual renamed file (may be truncated)
                            self._up_path = new_path
                            # Update final_filename to match the actual file (in case it was truncated)
                            final_filename = ospath.basename(self._up_path)
                            LOGGER.info(f"File renamed to: {final_filename}")
                        else:
                            # Still can't find the file, keep original filename
                            LOGGER.warning(
                                f"File not found at potential path either, keeping original filename: {current_basename}"
                            )
                            final_filename = current_basename
                except Exception as e:
                    LOGGER.error(f"Failed to rename file: {e}")
                    # Update final_filename to match the actual file
                    final_filename = current_basename

                # Immediately add renamed filename to processed list to prevent double processing
                if hasattr(self, "_processed_files"):
                    self._processed_files.add(final_filename)

                # Also add to the main loop's processed_files set if it exists
                if hasattr(self, "_main_processed_files"):
                    self._main_processed_files.add(final_filename)

            # Handle extremely long filenames (>240 chars) - Telegram has a limit around 255 chars
            # Only truncate if absolutely necessary
            if len(final_filename) > 240:
                if is_archive(final_filename):
                    name = get_base_name(final_filename)
                    ext = final_filename.split(name, 1)[1]
                elif match := re_match(
                    r".+(?=\..+\.0*\d+$)|.+(?=\.part\d+\..+$)",
                    final_filename,
                ):
                    name = match.group(0)
                    ext = final_filename.split(name, 1)[1]
                elif len(fsplit := ospath.splitext(final_filename)) > 1:
                    name = fsplit[0]
                    ext = fsplit[1]
                else:
                    name = final_filename
                    ext = ""
                extn = len(ext)
                remain = 240 - extn
                name = name[:remain]
                new_path = ospath.join(dirpath, f"{name}{ext}")
                await rename(self._up_path, new_path)
                self._up_path = new_path
                # Update core filename for caption (without prefix/suffix)
                core_filename = f"{name}{ext}"
                # Update caption if it's based on the filename
                if not self._lcaption and cap_mono:
                    if self._lfont:
                        try:
                            styled_core = await apply_font_style(
                                core_filename, self._lfont
                            )
                            cap_mono = self._build_caption_with_prefix_suffix(
                                styled_core
                            )
                        except Exception:
                            cap_mono = self._build_caption_with_prefix_suffix(
                                f"<code>{core_filename}</code>"
                            )
                    else:
                        cap_mono = self._build_caption_with_prefix_suffix(
                            f"<code>{core_filename}</code>"
                        )

            # We'll generate MediaInfo during the upload process instead of here
            # This is to avoid issues with files being deleted after MediaInfo generation
        except Exception as e:
            LOGGER.error(f"Error in _prepare_file: {e}")
            if not cap_mono:
                cap_mono = f"<code>{file_}</code>"

        return cap_mono

    def _get_input_media(self, subkey, key):
        rlist = []

        # Validate media_dict structure
        if (
            not self._media_dict
            or key not in self._media_dict
            or subkey not in self._media_dict[key]
        ):
            LOGGER.error(
                f"Invalid media_dict structure for key: {key}, subkey: {subkey}"
            )
            return rlist

        for msg in self._media_dict[key][subkey]:
            # Validate message object
            if msg is None:
                LOGGER.error("Skipping None message in media group")
                continue

            if key == "videos":
                if not hasattr(msg, "video") or msg.video is None:
                    LOGGER.error("Skipping message without video attribute")
                    continue
                if not hasattr(msg.video, "file_id"):
                    LOGGER.error("Skipping video message without file_id")
                    continue
                input_media = InputMediaVideo(
                    media=msg.video.file_id, caption=getattr(msg, "caption", None)
                )
            else:
                if not hasattr(msg, "document") or msg.document is None:
                    LOGGER.error("Skipping message without document attribute")
                    continue
                if not hasattr(msg.document, "file_id"):
                    LOGGER.error("Skipping document message without file_id")
                    continue
                input_media = InputMediaDocument(
                    media=msg.document.file_id, caption=getattr(msg, "caption", None)
                )
            rlist.append(input_media)
        return rlist

    async def _send_screenshots(self, dirpath, outputs):
        inputs = [
            InputMediaPhoto(ospath.join(dirpath, p), p.rsplit("/", 1)[-1])
            for p in outputs
        ]

        for i in range(0, len(inputs), 10):
            batch = inputs[i : i + 10]

            # Get the reply message details
            reply_to_message = self._sent_msg

            # Safety check for reply_to_message
            if reply_to_message is None:
                LOGGER.error("Cannot send screenshots: reply_to_message is None")
                return

            if (
                not hasattr(reply_to_message, "chat")
                or reply_to_message.chat is None
            ):
                LOGGER.error(
                    "Cannot send screenshots: reply_to_message has no chat attribute or chat is None"
                )
                return

            if not hasattr(reply_to_message.chat, "id") or not hasattr(
                reply_to_message, "id"
            ):
                LOGGER.error(
                    "Cannot send screenshots: reply_to_message.chat or reply_to_message has no id attribute"
                )
                return

            target_chat_id = reply_to_message.chat.id
            reply_to_message_id = reply_to_message.id

            # Send screenshots using direct client method (bypassing kurigram's buggy reply_media_group)
            if self._listener.hybrid_leech or not self._user_session:
                msgs_list = await self._listener.client.send_media_group(
                    chat_id=target_chat_id,
                    media=batch,
                    reply_to_message_id=reply_to_message_id,
                    disable_notification=True,
                )
            else:
                msgs_list = await TgClient.user.send_media_group(
                    chat_id=target_chat_id,
                    media=batch,
                    reply_to_message_id=reply_to_message_id,
                    disable_notification=True,
                )

            self._sent_msg = msgs_list[-1]

            # Copy the screenshots to additional destinations (USER_DUMP, PM, etc.)
            await self._copy_media_group(msgs_list)

    async def _send_media_group(self, subkey, key, msgs):
        # Get message objects from chat_id and message_id pairs
        for index, msg in enumerate(msgs):
            if self._listener.hybrid_leech or not self._user_session:
                msgs[index] = await self._listener.client.get_messages(
                    chat_id=msg[0], message_ids=msg[1]
                )
            else:
                msgs[index] = await TgClient.user.get_messages(
                    chat_id=msg[0], message_ids=msg[1]
                )

        # Get the original message to reply to
        reply_to_message = msgs[0].reply_to_message

        # Create InputMedia objects
        input_media = self._get_input_media(subkey, key)

        # Determine the target chat and reply message ID
        if reply_to_message:
            # If there's a reply_to_message, use its chat and reply to it
            if (
                not hasattr(reply_to_message, "chat")
                or reply_to_message.chat is None
            ):
                LOGGER.error(
                    "Cannot send media group: reply_to_message has no chat attribute or chat is None"
                )
                return
            if not hasattr(reply_to_message.chat, "id") or not hasattr(
                reply_to_message, "id"
            ):
                LOGGER.error(
                    "Cannot send media group: reply_to_message.chat or reply_to_message has no id attribute"
                )
                return
            target_chat_id = reply_to_message.chat.id
            reply_to_message_id = reply_to_message.id
        else:
            # If no reply_to_message, use the original message's chat
            if not msgs or len(msgs) == 0:
                LOGGER.error("Cannot send media group: msgs list is empty")
                return
            if not hasattr(msgs[0], "chat") or msgs[0].chat is None:
                LOGGER.error(
                    "Cannot send media group: msgs[0] has no chat attribute or chat is None"
                )
                return
            if not hasattr(msgs[0].chat, "id"):
                LOGGER.error(
                    "Cannot send media group: msgs[0].chat has no id attribute"
                )
                return
            target_chat_id = msgs[0].chat.id
            reply_to_message_id = None

        # Send media group using direct client method (bypassing kurigram's buggy reply_media_group)
        if self._listener.hybrid_leech or not self._user_session:
            msgs_list = await self._listener.client.send_media_group(
                chat_id=target_chat_id,
                media=input_media,
                reply_to_message_id=reply_to_message_id,
                disable_notification=True,
            )
        else:
            msgs_list = await TgClient.user.send_media_group(
                chat_id=target_chat_id,
                media=input_media,
                reply_to_message_id=reply_to_message_id,
                disable_notification=True,
            )

        # Log successful media group creation
        LOGGER.info(
            f"Leech media group successfully created with {len(msgs_list)} files for: {subkey}"
        )

        # Clean up original messages
        for msg in msgs:
            if msg.link in self._msgs_dict:
                del self._msgs_dict[msg.link]
            await delete_message(msg)
        del self._media_dict[key][subkey]

        # Update message dictionary for additional destinations
        if self._listener.is_super_chat or self._listener.up_dest:
            for m in msgs_list:
                self._msgs_dict[m.link] = m.caption
        self._sent_msg = msgs_list[-1]

        # Copy media group to additional destinations (USER_DUMP, PM, etc.)
        await self._copy_media_group(msgs_list)

    async def upload(self):
        await self._user_settings()

        # Log streamrip-specific information
        if self._is_streamrip:
            LOGGER.info(
                f"Starting streamrip upload - Platform: {self._streamrip_platform}, Media Type: {self._streamrip_media_type}"
            )

        res = await self._msg_to_reply()
        if not res:
            return
        for dirpath, _, files in natsorted(await sync_to_async(walk, self._path)):
            if dirpath.strip().endswith("/yt-dlp-thumb"):
                continue
            if dirpath.strip().endswith("_ss"):
                await self._send_screenshots(dirpath, files)
                await rmtree(dirpath, ignore_errors=True)
                continue

            # Process files with dynamic file list refresh to handle renames during upload
            processed_files = set()  # Track processed files to avoid duplicates

            while True:
                # Refresh file list to account for renamed files during upload process
                current_files = await sync_to_async(listdir, dirpath)
                current_files = natsorted(
                    [
                        f
                        for f in current_files
                        if await aiopath.isfile(ospath.join(dirpath, f))
                    ]
                )

                # Find next unprocessed file
                next_file = None
                for file_ in current_files:
                    if file_ not in processed_files:
                        # Check if file should be excluded based on EXCLUDED_EXTENSIONS
                        file_ext = ospath.splitext(file_)[1].lower().lstrip(".")
                        if file_ext in excluded_extensions:
                            LOGGER.info(
                                f"Skipping file due to excluded extension: {file_}"
                            )
                            processed_files.add(
                                file_
                            )  # Mark as processed to avoid checking again
                            continue

                        next_file = file_
                        break

                if next_file is None:
                    # No more files to process
                    break

                original_filename = next_file
                processed_files.add(original_filename)

                # Store processed_files as instance variable for access in upload functions
                self._processed_files = processed_files
                self._main_processed_files = (
                    processed_files  # Reference to main loop's set
                )

                self._error = ""
                self._up_path = ospath.join(dirpath, next_file)
                if not await aiopath.exists(self._up_path):
                    LOGGER.error(f"{self._up_path} not exists! Continue uploading!")
                    continue
                try:
                    f_size = await aiopath.getsize(self._up_path)
                    self._total_files += 1
                    if f_size == 0:
                        # Check if this is from a failed extraction
                        parent_dir = ospath.dirname(self._up_path)
                        if any(
                            keyword in parent_dir.lower()
                            for keyword in ["extract", "archive", "rar", "zip", "7z"]
                        ):
                            LOGGER.error(
                                f"Zero-size file detected from failed extraction: {self._up_path}. "
                                f"This indicates archive extraction failed. Skipping file."
                            )
                        else:
                            LOGGER.error(
                                f"{self._up_path} size is zero, telegram don't upload zero size files",
                            )
                        self._corrupted += 1
                        continue

                    # Pre-check file size against Telegram's limit (based on premium status and client type)
                    from bot.core.aeon_client import TgClient

                    # Determine the appropriate limit based on client type and premium status
                    if (
                        self._user_session
                        and TgClient.user
                        and TgClient.IS_PREMIUM_USER
                    ):
                        # User client with premium: up to 4GB
                        telegram_limit = TgClient.MAX_SPLIT_SIZE  # 4GB for premium
                        client_type = "premium user"
                    else:
                        # Bot client or non-premium: up to 2GB
                        telegram_limit = 2097152000  # 2GB for bot/non-premium
                        client_type = (
                            "bot" if not self._user_session else "non-premium user"
                        )

                    limit_in_gb = telegram_limit / (1024 * 1024 * 1024)

                    # Check if this is a split file (has .001, .002, etc. extension)
                    current_filename = ospath.basename(self._up_path)
                    is_split_file = bool(re.search(r"\.\d{3}$", current_filename))

                    if f_size > telegram_limit:
                        if is_split_file:
                            # For split files, this indicates a splitting error - log as warning and continue
                            LOGGER.warning(
                                f"Split file {current_filename} is {f_size / (1024 * 1024 * 1024):.2f} GiB, exceeding {limit_in_gb:.1f} GiB limit ({client_type} client). "
                                f"This indicates a splitting error. Attempting upload anyway..."
                            )
                        else:
                            # For regular files that exceed Telegram's limit, check if they should be split
                            from bot.helper.ext_utils.bot_utils import (
                                get_user_split_size,
                            )

                            # Get user's split size setting to determine if file should be split
                            user_split_size, skip_splitting = get_user_split_size(
                                self._listener.user_id,
                                getattr(self._listener, "args", None),
                                f_size,
                                equal_splits=getattr(
                                    self._listener, "equal_splits_enabled", False
                                ),
                            )

                            if not skip_splitting and user_split_size > 0:
                                # File should be split but wasn't - this indicates the splitting process failed or was skipped
                                LOGGER.error(
                                    f"File {current_filename} ({f_size / (1024 * 1024 * 1024):.2f} GiB) exceeds {limit_in_gb:.1f} GiB {client_type} limit "
                                    f"and should have been split into {user_split_size / (1024 * 1024):.1f} MiB parts. "
                                    f"The file splitting process may have failed. Skipping file."
                                )
                                self._error = f"File size exceeds Telegram's {limit_in_gb:.1f} GiB {client_type} limit and splitting failed"
                                self._corrupted += 1
                                continue
                            # File splitting is disabled - provide clear guidance
                            LOGGER.warning(
                                f"⚠️ File {current_filename} ({f_size / (1024 * 1024 * 1024):.2f} GiB) exceeds {limit_in_gb:.1f} GiB {client_type} limit. "
                                f"File splitting is disabled (LEECH_SPLIT_SIZE = 0). "
                                f"Large files CANNOT be uploaded to Telegram without splitting."
                            )

                            LOGGER.info(
                                "💡 Solution: Enable file splitting by setting LEECH_SPLIT_SIZE > 0. "
                                "After enabling, re-download the file to have it automatically split into uploadable parts."
                            )

                            self._error = f"File size exceeds Telegram's {limit_in_gb:.1f} GiB {client_type} limit. File splitting is disabled."
                            self._corrupted += 1
                            continue
                    if self._listener.is_cancelled:
                        return
                    # Prepare the file (apply prefix, suffix, font style, etc.)
                    # Use the current filename from the path
                    current_filename = ospath.basename(self._up_path)
                    cap_mono = await self._prepare_file(current_filename, dirpath)

                    # Update current_filename after _prepare_file (which may have renamed the file)
                    current_filename = ospath.basename(self._up_path)

                    # Use the current file path (after renaming) for media group pattern matching
                    original_file_path = self._up_path
                    if self._last_msg_in_group:
                        group_lists = [
                            x for v in self._media_dict.values() for x in v
                        ]
                        match = re_match(
                            r".+(?=\.0*\d+$)|.+(?=\.part\d+\..+$)",
                            original_file_path,
                        )
                        if not match or (
                            match and match.group(0) not in group_lists
                        ):
                            for key, value in list(self._media_dict.items()):
                                for subkey, msgs in list(value.items()):
                                    if len(msgs) > 1:
                                        await self._send_media_group(
                                            subkey,
                                            key,
                                            msgs,
                                        )
                    # Client selection logic based on user transmission and hybrid leech settings
                    if (
                        not self._listener.is_cancelled
                        and self._sent_msg is not None
                        and hasattr(self._sent_msg, "chat")
                        and self._sent_msg.chat is not None
                    ):
                        if self._effective_hybrid_leech:
                            # HYBRID LEECH ENABLED: Dynamic client selection based on file size
                            bot_limit = 2097152000  # 2GB for bot client

                            if f_size > bot_limit:
                                # Large file - try to use user client if available
                                if TgClient.user:
                                    self._user_session = True
                                    client_type = (
                                        "premium user"
                                        if TgClient.IS_PREMIUM_USER
                                        else "non-premium user"
                                    )
                                    LOGGER.info(
                                        f"Hybrid leech: Using {client_type} client for {f_size / (1024 * 1024 * 1024):.2f} GB file"
                                    )
                                else:
                                    LOGGER.warning(
                                        f"Hybrid leech: File {f_size / (1024 * 1024 * 1024):.2f} GB exceeds bot limit but no user session available"
                                    )
                                    self._user_session = False  # Force bot client, will be handled by size check below
                            else:
                                # Small file - use bot client for optimal performance
                                self._user_session = False
                                LOGGER.info(
                                    f"Hybrid leech: Using bot client for {f_size / (1024 * 1024 * 1024):.2f} GB file"
                                )
                        # HYBRID LEECH DISABLED: Use user transmission setting consistently
                        # If user transmission is enabled, always use user client (no dynamic switching)
                        elif self._listener.user_transmission and TgClient.user:
                            self._user_session = True
                            client_type = (
                                "premium user"
                                if TgClient.IS_PREMIUM_USER
                                else "non-premium user"
                            )
                            LOGGER.info(
                                f"User transmission: Using {client_type} client for {f_size / (1024 * 1024 * 1024):.2f} GB file (hybrid leech disabled)"
                            )
                        else:
                            self._user_session = False
                            LOGGER.info(
                                f"Using bot client for {f_size / (1024 * 1024 * 1024):.2f} GB file (user transmission disabled)"
                            )

                        # Check if _sent_msg is valid before refreshing
                        if (
                            self._sent_msg is not None
                            and hasattr(self._sent_msg, "chat")
                            and self._sent_msg.chat is not None
                            and hasattr(self._sent_msg.chat, "id")
                            and hasattr(self._sent_msg, "id")
                        ):
                            if self._user_session:
                                self._sent_msg = await TgClient.user.get_messages(
                                    chat_id=self._sent_msg.chat.id,
                                    message_ids=self._sent_msg.id,
                                )
                            else:
                                self._sent_msg = (
                                    await self._listener.client.get_messages(
                                        chat_id=self._sent_msg.chat.id,
                                        message_ids=self._sent_msg.id,
                                    )
                                )

                            # Validate _sent_msg after refresh - get_messages can return None
                            if (
                                self._sent_msg is None
                                or not hasattr(self._sent_msg, "chat")
                                or self._sent_msg.chat is None
                                or not hasattr(self._sent_msg.chat, "id")
                                or not hasattr(self._sent_msg, "id")
                            ):
                                # Try to re-establish a valid _sent_msg
                                try:
                                    res = await self._msg_to_reply()
                                    if not res or self._sent_msg is None:
                                        LOGGER.error(
                                            f"Failed to re-establish valid message. Skipping file: {self._up_path}"
                                        )
                                        self._corrupted += 1
                                        continue
                                    LOGGER.info(
                                        f"Successfully re-established message for file: {self._up_path}"
                                    )
                                except Exception as e:
                                    LOGGER.error(
                                        f"Exception while re-establishing message: {e}. Skipping file: {self._up_path}"
                                    )
                                    self._corrupted += 1
                                    continue
                        else:
                            LOGGER.error(
                                f"Cannot refresh message: _sent_msg is invalid. Skipping file: {self._up_path}"
                            )
                            self._corrupted += 1
                            continue
                    self._last_msg_in_group = False
                    self._last_uploaded = 0

                    upload_result = await self._upload_file(
                        cap_mono, current_filename, original_file_path
                    )
                    if self._listener.is_cancelled:
                        return

                    # Check if upload was successful and _sent_msg is valid
                    if upload_result is None or self._sent_msg is None:
                        LOGGER.error(
                            f"Upload failed or returned None for file: {self._up_path}"
                        )
                        self._corrupted += 1
                        continue

                    # Enhanced memory cleanup after each file upload for memory-constrained environments
                    try:
                        from bot.helper.ext_utils.gc_utils import (
                            smart_garbage_collection,
                        )

                        # More aggressive cleanup for streamrip uploads due to thumbnail processing
                        if self._is_streamrip:
                            smart_garbage_collection(
                                aggressive=True, for_music_download=True
                            )
                        else:
                            smart_garbage_collection(aggressive=False)
                    except ImportError:
                        import gc

                        gc.collect()
                        # Additional cleanup for streamrip
                        if self._is_streamrip:
                            gc.collect()  # Run twice for better cleanup

                    # Store the actual filename (which may have been modified by leech filename)
                    actual_filename = ospath.basename(self._up_path)

                    if (
                        not self._is_corrupted
                        and (self._listener.is_super_chat or self._listener.up_dest)
                        and not self._is_private
                        and self._sent_msg is not None
                        and hasattr(self._sent_msg, "link")
                    ):
                        # Map message link to filename for final summary
                        self._msgs_dict[self._sent_msg.link] = actual_filename

                        # Also map per-file MediaInfo link to this message URL so each file gets its own link
                        try:
                            if (
                                hasattr(self._listener, "mediainfo_link")
                                and self._listener.mediainfo_link
                            ):
                                if (
                                    not hasattr(self._listener, "mediainfo_links")
                                    or self._listener.mediainfo_links is None
                                ):
                                    self._listener.mediainfo_links = {}
                                self._listener.mediainfo_links[
                                    self._sent_msg.link
                                ] = self._listener.mediainfo_link
                        except Exception as e:
                            LOGGER.warning(
                                f"Failed to map MediaInfo link to message: {e}"
                            )
                    await sleep(1)
                except Exception as err:
                    if isinstance(err, RetryError):
                        LOGGER.info(
                            f"Total Attempts: {err.last_attempt.attempt_number}",
                        )
                        err = err.last_attempt.exception()
                    LOGGER.error(f"{err}. Path: {self._up_path}")
                    self._error = str(err)
                    self._corrupted += 1
                    if self._listener.is_cancelled:
                        return
                if not self._listener.is_cancelled and await aiopath.exists(
                    self._up_path,
                ):
                    try:
                        await remove(self._up_path)
                    except FileNotFoundError:
                        # File was already deleted, ignore
                        pass
                    except Exception as e:
                        LOGGER.error(f"Error removing file {self._up_path}: {e}")
        for key, value in list(self._media_dict.items()):
            for subkey, msgs in list(value.items()):
                if len(msgs) > 1:
                    try:
                        await self._send_media_group(subkey, key, msgs)
                    except Exception as e:
                        LOGGER.info(
                            f"While sending media group at the end of task. Error: {e}"
                        )
        if self._listener.is_cancelled:
            return
        if self._total_files == 0:
            await self._listener.on_upload_error(
                "No files to upload. In case you have filled EXCLUDED_EXTENSIONS, then check if all files have those extensions or not.",
            )
            return
        if self._total_files <= self._corrupted:
            await self._listener.on_upload_error(
                f"Files Corrupted or unable to upload. {self._error or 'Check logs!'}",
            )
            return
        await self._listener.on_upload_complete(
            None,
            self._msgs_dict,
            self._total_files,
            self._corrupted,
        )
        return

    @retry(
        wait=wait_exponential(multiplier=2, min=4, max=8),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
    )
    def _should_generate_mediainfo(self, file_path: str) -> bool:
        """Check if MediaInfo should be generated for this file type"""
        if not file_path:
            return False

        filename = os.path.basename(file_path).lower()

        # Exclude gallery-dl archive files
        if filename == "gallery_dl_archive.db":
            return False

        # Exclude other database and metadata files
        excluded_files = {
            "gallery_dl_archive.db",
            "archive.db",
            "metadata.json",
            "info.json",
            ".DS_Store",
            "Thumbs.db",
            "desktop.ini",
        }

        if filename in excluded_files:
            return False

        # Exclude by extension - non-media files
        excluded_extensions = {
            ".db",
            ".sqlite",
            ".sqlite3",  # Database files
            ".json",
            ".xml",
            ".txt",
            ".log",  # Metadata/text files
            ".nfo",
            ".sfv",
            ".md5",
            ".sha1",
            ".sha256",  # Info/checksum files
            ".torrent",
            ".magnet",  # Torrent files
            ".ini",
            ".cfg",
            ".conf",  # Config files
            ".tmp",
            ".temp",
            ".cache",  # Temporary files
            ".part",
            ".crdownload",  # Partial downloads
            ".url",
            ".lnk",
            ".desktop",  # Shortcuts/links
        }

        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext in excluded_extensions:
            return False

        # Only generate MediaInfo for actual media files
        media_extensions = {
            # Video
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
            ".3gp",
            ".3g2",
            ".asf",
            ".rm",
            ".rmvb",
            ".vob",
            ".ts",
            ".mts",
            ".m2ts",
            ".divx",
            ".xvid",
            ".ogv",
            ".f4v",
            ".mpg",
            ".mpeg",
            ".m1v",
            ".m2v",
            ".mpe",
            ".mpv",
            ".mp2",
            ".mpa",
            ".mpg2",
            # Audio
            ".mp3",
            ".flac",
            ".wav",
            ".aac",
            ".ogg",
            ".wma",
            ".m4a",
            ".opus",
            ".ape",
            ".ac3",
            ".dts",
            ".amr",
            ".au",
            ".ra",
            ".aiff",
            ".aif",
            ".aifc",
            ".caf",
            ".sd2",
            ".snd",
            ".m1a",
            ".m2a",
            # Images (for size/dimension info)
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".tiff",
            ".tif",
            ".webp",
            ".svg",
            ".ico",
            ".psd",
            ".raw",
            ".cr2",
            ".nef",
            ".arw",
            ".dng",
            ".heic",
            ".heif",
            ".avif",
            ".jxl",
        }

        return file_ext in media_extensions

    async def _upload_file(self, cap_mono, file, o_path, force_document=False):
        # Validate _sent_msg before proceeding with upload
        if self._sent_msg is None:
            LOGGER.error(
                f"Cannot upload file: _sent_msg is None. Path: {self._up_path}"
            )
            return None

        if (
            not hasattr(self._sent_msg, "reply_document")
            or not hasattr(self._sent_msg, "reply_video")
            or not hasattr(self._sent_msg, "reply_audio")
            or not hasattr(self._sent_msg, "reply_photo")
        ):
            LOGGER.error(
                f"Cannot upload file: _sent_msg missing required reply methods. Path: {self._up_path}"
            )
            return None

        # Generate MediaInfo only for media files
        if (
            hasattr(self._listener, "user_dict")
            and self._listener.user_dict.get(
                "MEDIAINFO_ENABLED", Config.MEDIAINFO_ENABLED
            )
            and self._should_generate_mediainfo(self._up_path)
        ):
            try:
                from bot.modules.mediainfo import gen_mediainfo

                # Use the current file path (self._up_path) which may have been modified by _prepare_file
                # Verify the file exists before generating MediaInfo
                if await aiopath.exists(self._up_path):
                    self._listener.mediainfo_link = await gen_mediainfo(
                        None, media_path=self._up_path, silent=True
                    )
                else:
                    LOGGER.error(
                        f"File not found for MediaInfo generation: {self._up_path}"
                    )
                    self._listener.mediainfo_link = None

                if (
                    self._listener.mediainfo_link
                    and self._listener.mediainfo_link.strip()
                ):
                    LOGGER.info(
                        f"MediaInfo generated successfully for: {self._up_path}"
                    )
                else:
                    self._listener.mediainfo_link = None
                    LOGGER.info("MediaInfo generation returned empty result")

            except Exception as e:
                self._listener.mediainfo_link = None
                LOGGER.warning(f"Could not generate MediaInfo: {e}")
        else:
            # Skip MediaInfo for non-media files
            self._listener.mediainfo_link = None
        if (
            self._thumb is not None
            and not await aiopath.exists(self._thumb)
            and self._thumb != "none"
        ):
            self._thumb = None
        thumb = self._thumb
        self._is_corrupted = False
        try:
            is_video, is_audio, is_image = await get_document_type(self._up_path)

            if not is_image and thumb is None:
                file_name = ospath.splitext(file)[0]
                thumb_path = f"{self._path}/yt-dlp-thumb/{file_name}.jpg"
                if await aiopath.isfile(thumb_path):
                    thumb = thumb_path
                else:
                    # Try auto thumbnail if enabled and no yt-dlp thumbnail found
                    user_dict = user_data.get(self._listener.user_id, {})
                    auto_thumb_enabled = user_dict.get("AUTO_THUMBNAIL")
                    if auto_thumb_enabled is None:
                        auto_thumb_enabled = Config.AUTO_THUMBNAIL

                    if auto_thumb_enabled and (is_video or is_audio):
                        try:
                            # Handle split files by using original filename for auto thumbnail
                            original_filename = (
                                self._get_original_filename_for_thumbnail(file)
                            )
                            # Pass the enabled status to override config check
                            auto_thumb = (
                                await AutoThumbnailHelper.get_auto_thumbnail(
                                    original_filename,
                                    self._listener.user_id,
                                    enabled=True,
                                )
                            )
                            if auto_thumb:
                                thumb = auto_thumb
                                LOGGER.info(
                                    f"✅ Using auto thumbnail for: {file} (original: {original_filename})"
                                )
                            else:
                                LOGGER.info(
                                    f"❌ No auto thumbnail found for: {file}"
                                )
                        except Exception as e:
                            LOGGER.error(f"Error getting auto thumbnail: {e}")
                    elif not auto_thumb_enabled:
                        LOGGER.info(f"Auto thumbnail disabled for: {file}")
                    else:
                        LOGGER.info(
                            f"Auto thumbnail skipped - not video/audio: {file}"
                        )

                if thumb is None and is_audio and not is_video:
                    # Enhanced thumbnail handling for streamrip audio files with memory safety
                    if self._is_streamrip:
                        # Check memory before thumbnail extraction
                        memory_percent = get_memory_usage()
                        if memory_percent > 80:
                            LOGGER.warning(
                                f"High memory usage ({memory_percent}%), skipping thumbnail extraction for streamrip"
                            )
                        else:
                            # For streamrip, try to extract embedded album art first
                            thumb = await get_audio_thumbnail(self._up_path)
                            if thumb:
                                LOGGER.info(
                                    f"Leech audio thumbnail (embedded album art) successfully extracted for streamrip: {file}"
                                )

                            # If no embedded thumbnail found, check for cover art files in the same directory
                            if thumb is None:
                                try:
                                    audio_dir = ospath.dirname(self._up_path)
                                    cover_files = [
                                        "cover.jpg",
                                        "cover.jpeg",
                                        "cover.png",
                                        "folder.jpg",
                                        "folder.jpeg",
                                        "folder.png",
                                        "album.jpg",
                                        "album.jpeg",
                                        "album.png",
                                    ]

                                    for cover_file in cover_files:
                                        cover_path = ospath.join(
                                            audio_dir, cover_file
                                        )
                                        if await aiopath.isfile(cover_path):
                                            # Check cover file size before using
                                            cover_size_mb = (
                                                await aiopath.getsize(cover_path)
                                            ) / (1024 * 1024)
                                            if (
                                                cover_size_mb > 10
                                            ):  # Skip very large cover files
                                                LOGGER.warning(
                                                    f"Skipping large cover file ({cover_size_mb:.1f}MB): {cover_file}"
                                                )
                                                continue
                                            thumb = cover_path
                                            LOGGER.info(
                                                f"Leech audio thumbnail (cover art file) successfully applied for streamrip: {cover_file}"
                                            )
                                            break
                                except Exception as e:
                                    LOGGER.error(
                                        f"Could not find cover art for streamrip audio: {e}"
                                    )
                    # Enhanced thumbnail handling for Zotify audio files
                    elif self._is_zotify:
                        # For Zotify, try to extract embedded album art first
                        thumb = await get_audio_thumbnail(self._up_path)
                        if thumb:
                            LOGGER.info(
                                f"Leech audio thumbnail (embedded album art) successfully extracted for Zotify: {file}"
                            )

                        # If no embedded thumbnail found, check for cover art files in the same directory
                        if thumb is None:
                            try:
                                audio_dir = ospath.dirname(self._up_path)
                                cover_files = [
                                    "cover.jpg",
                                    "cover.jpeg",
                                    "cover.png",
                                    "folder.jpg",
                                    "folder.jpeg",
                                    "folder.png",
                                    "album.jpg",
                                    "album.jpeg",
                                    "album.png",
                                    "artwork.jpg",
                                    "artwork.jpeg",
                                    "artwork.png",
                                ]

                                for cover_file in cover_files:
                                    cover_path = ospath.join(audio_dir, cover_file)
                                    if await aiopath.isfile(cover_path):
                                        thumb = cover_path
                                        LOGGER.info(
                                            f"Leech audio thumbnail (cover art file) successfully applied for Zotify: {cover_file}"
                                        )
                                        break
                            except Exception as e:
                                LOGGER.error(
                                    f"Could not find cover art for Zotify audio: {e}"
                                )
                    else:
                        thumb = await get_audio_thumbnail(self._up_path)
                        if thumb:
                            LOGGER.info(
                                f"Leech audio thumbnail (embedded album art) successfully extracted for: {file}"
                            )

                # Log when user-provided thumbnail is being used for audio
                if thumb and thumb != "none" and thumb == self._thumb and is_audio:
                    LOGGER.info(
                        f"Leech user thumbnail successfully applied to audio: {file}"
                    )

            if (
                self._listener.as_doc
                or force_document
                or (not is_video and not is_audio and not is_image)
            ):
                key = "documents"
                if is_video and thumb is None:
                    thumb = await get_video_thumbnail(self._up_path, None)
                    if thumb:
                        LOGGER.info(
                            f"Leech document video thumbnail successfully generated for: {file}"
                        )

                # Log when user-provided thumbnail is being used for documents
                if thumb and thumb != "none" and thumb == self._thumb:
                    LOGGER.info(
                        f"Leech user thumbnail successfully applied to document: {file}"
                    )

                if self._listener.is_cancelled:
                    return None
                if thumb == "none":
                    thumb = None

                # Additional validation before document upload
                if self._sent_msg is None:
                    LOGGER.error(
                        f"Cannot upload document: _sent_msg is None. Path: {self._up_path}"
                    )
                    return None

                self._sent_msg = await self._sent_msg.reply_document(
                    document=self._up_path,
                    quote=True,
                    thumb=thumb,
                    caption=cap_mono,
                    force_document=True,
                    disable_notification=True,
                    progress=self._upload_progress,
                    parse_mode=enums.ParseMode.HTML,
                )

                # Validate that reply_document returned a valid message
                if self._sent_msg is None:
                    LOGGER.error(
                        f"reply_document returned None for file: {self._up_path}"
                    )
                    return None

                LOGGER.info(f"Leech document successfully uploaded: {file}")
            elif is_video:
                key = "videos"
                try:
                    duration = (await get_media_info(self._up_path))[0]
                except Exception as e:
                    LOGGER.error(f"Error getting video duration: {e}")
                    duration = 0

                if thumb is None and self._listener.thumbnail_layout:
                    thumb = await get_multiple_frames_thumbnail(
                        self._up_path,
                        self._listener.thumbnail_layout,
                        self._listener.screen_shots,
                    )
                    if thumb:
                        LOGGER.info(
                            f"Leech thumbnail layout ({self._listener.thumbnail_layout}) successfully applied to: {file}"
                        )
                if thumb is None:
                    thumb = await get_video_thumbnail(self._up_path, duration)
                    if thumb:
                        LOGGER.info(
                            f"Leech video thumbnail successfully generated for: {file}"
                        )

                # Log when user-provided thumbnail is being used
                if thumb and thumb != "none" and thumb == self._thumb:
                    LOGGER.info(
                        f"Leech user thumbnail successfully applied to: {file}"
                    )

                if thumb is not None and thumb != "none":
                    with Image.open(thumb) as img:
                        width, height = img.size
                else:
                    width = 480
                    height = 320

                if self._listener.is_cancelled:
                    return None
                if thumb == "none":
                    thumb = None

                # Additional validation before video upload
                if self._sent_msg is None:
                    LOGGER.error(
                        f"Cannot upload video: _sent_msg is None. Path: {self._up_path}"
                    )
                    return None

                self._sent_msg = await self._sent_msg.reply_video(
                    video=self._up_path,
                    quote=True,
                    caption=cap_mono,
                    duration=duration,
                    width=width,
                    height=height,
                    thumb=thumb,
                    supports_streaming=True,
                    disable_notification=True,
                    progress=self._upload_progress,
                    parse_mode=enums.ParseMode.HTML,
                )

                # Validate that reply_video returned a valid message
                if self._sent_msg is None:
                    LOGGER.error(
                        f"reply_video returned None for file: {self._up_path}"
                    )
                    return None

                LOGGER.info(f"Leech video successfully uploaded: {file}")
            elif is_audio:
                key = "audios"
                duration, artist, title = await get_media_info(self._up_path)

                # Debug logging for Zotify downloads
                if self._is_zotify:
                    if not artist or not title:
                        # For Zotify files, try a small delay and retry metadata extraction
                        # Sometimes metadata isn't immediately available after download
                        try:
                            import asyncio

                            await asyncio.sleep(0.5)  # Small delay
                            (
                                _duration_retry,
                                artist_retry,
                                title_retry,
                            ) = await get_media_info(self._up_path)
                            if artist_retry and not artist:
                                artist = artist_retry
                            if title_retry and not title:
                                title = title_retry
                        except Exception as e:
                            LOGGER.error(f"Zotify metadata retry failed: {e}")

                # Enhanced audio handling for streamrip downloads
                if self._is_streamrip:
                    # For streamrip, try to extract better metadata from filename if available
                    if not artist or not title:
                        try:
                            # Extract artist and title from filename pattern: "Artist - Title.ext"
                            filename_without_ext = ospath.splitext(
                                ospath.basename(self._up_path)
                            )[0]
                            if " - " in filename_without_ext:
                                parts = filename_without_ext.split(" - ", 1)
                                if len(parts) == 2:
                                    if not artist:
                                        artist = parts[0].strip()
                                    if not title:
                                        title = parts[1].strip()
                        except Exception as e:
                            LOGGER.error(
                                f"Could not extract metadata from filename: {e}"
                            )

                    # Set default values for streamrip if still empty
                    if not artist:
                        artist = self._streamrip_platform or "Unknown Artist"
                    if not title:
                        title = ospath.splitext(ospath.basename(self._up_path))[0]

                # Enhanced audio handling for Zotify downloads
                elif self._is_zotify:
                    # For Zotify, try to extract better metadata from filename if available
                    if not artist or not title:
                        try:
                            # Extract artist and title from Zotify filename patterns:
                            # Pattern 1: "01. Artist - Title.ext" (track number prefix)
                            # Pattern 2: "Artist - Title.ext" (simple format)
                            filename_without_ext = ospath.splitext(
                                ospath.basename(self._up_path)
                            )[0]

                            # Remove track number prefix if present (e.g., "01. ")
                            if (
                                ". " in filename_without_ext
                                and filename_without_ext.split(". ")[0].isdigit()
                            ):
                                filename_without_ext = filename_without_ext.split(
                                    ". ", 1
                                )[1]

                            if " - " in filename_without_ext:
                                parts = filename_without_ext.split(" - ", 1)
                                if len(parts) == 2:
                                    if not artist:
                                        artist = parts[0].strip()
                                    if not title:
                                        title = parts[1].strip()
                        except Exception as e:
                            LOGGER.error(
                                f"Could not extract Zotify metadata from filename: {e}"
                            )

                    # Set default values for Zotify if still empty
                    if not artist:
                        artist = self._zotify_platform or "Unknown Artist"
                    if not title:
                        title = ospath.splitext(ospath.basename(self._up_path))[0]
                        # Remove track number prefix from title if present
                        if ". " in title and title.split(". ")[0].isdigit():
                            title = title.split(". ", 1)[1]

                if self._listener.is_cancelled:
                    return None

                # Additional validation before audio upload
                if self._sent_msg is None:
                    LOGGER.error(
                        f"Cannot upload audio: _sent_msg is None. Path: {self._up_path}"
                    )
                    return None

                # For streamrip uploads, proactively wait for memory to be available before starting upload
                if self._is_streamrip:
                    await wait_for_memory_availability(
                        max_memory_percent=80, max_wait_time=30
                    )

                self._sent_msg = await self._sent_msg.reply_audio(
                    audio=self._up_path,
                    quote=True,
                    caption=cap_mono,
                    duration=duration,
                    performer=artist,
                    title=title,
                    thumb=thumb,
                    disable_notification=True,
                    progress=self._upload_progress,
                    parse_mode=enums.ParseMode.HTML,
                )

                # Validate that reply_audio returned a valid message
                if self._sent_msg is None:
                    LOGGER.error(
                        f"reply_audio returned None for file: {self._up_path}"
                    )
                    return None

                LOGGER.info(f"Leech audio successfully uploaded: {file}")
            else:
                key = "photos"
                if self._listener.is_cancelled:
                    return None

                # Check if the file has a valid photo extension that Telegram supports
                valid_photo_extensions = [".jpg", ".jpeg", ".png", ".webp"]
                file_ext = ospath.splitext(self._up_path)[1].lower()

                # If the file extension is not supported by Telegram for photos, send as document
                if file_ext not in valid_photo_extensions:
                    LOGGER.info(
                        f"File has image type but unsupported extension for Telegram photos: {file_ext}. Sending as document."
                    )
                    key = "documents"

                    # Additional validation before document upload (for unsupported image extensions)
                    if self._sent_msg is None:
                        LOGGER.error(
                            f"Cannot upload document (unsupported image): _sent_msg is None. Path: {self._up_path}"
                        )
                        return None

                    self._sent_msg = await self._sent_msg.reply_document(
                        document=self._up_path,
                        quote=True,
                        thumb=thumb,
                        caption=cap_mono,
                        force_document=True,
                        disable_notification=True,
                        progress=self._upload_progress,
                        parse_mode=enums.ParseMode.HTML,
                    )

                    # Validate that reply_document returned a valid message
                    if self._sent_msg is None:
                        LOGGER.error(
                            f"reply_document returned None for unsupported image file: {self._up_path}"
                        )
                        return None
                else:
                    # Try to send as photo, but be prepared to fall back to document
                    try:
                        # Additional validation before photo upload
                        if self._sent_msg is None:
                            LOGGER.error(
                                f"Cannot upload photo: _sent_msg is None. Path: {self._up_path}"
                            )
                            return None

                        self._sent_msg = await self._sent_msg.reply_photo(
                            photo=self._up_path,
                            quote=True,
                            caption=cap_mono,
                            disable_notification=True,
                            progress=self._upload_progress,
                            parse_mode=enums.ParseMode.HTML,
                        )

                        # Validate that reply_photo returned a valid message
                        if self._sent_msg is None:
                            LOGGER.error(
                                f"reply_photo returned None for file: {self._up_path}"
                            )
                            return None

                        LOGGER.info(f"Leech image successfully uploaded: {file}")
                    except BadRequest as e:
                        if "PHOTO_EXT_INVALID" in str(e):
                            LOGGER.info(
                                f"Failed to send as photo due to invalid extension. Sending as document: {self._up_path}"
                            )
                            key = "documents"

                            # Additional validation before fallback document upload
                            if self._sent_msg is None:
                                LOGGER.error(
                                    f"Cannot upload fallback document: _sent_msg is None. Path: {self._up_path}"
                                )
                                return None

                            self._sent_msg = await self._sent_msg.reply_document(
                                document=self._up_path,
                                quote=True,
                                thumb=thumb,
                                caption=cap_mono,
                                force_document=True,
                                disable_notification=True,
                                progress=self._upload_progress,
                                parse_mode=enums.ParseMode.HTML,
                            )

                            # Validate that reply_document returned a valid message
                            if self._sent_msg is None:
                                LOGGER.error(
                                    f"reply_document (fallback) returned None for file: {self._up_path}"
                                )
                                return None
                        else:
                            raise

            # Check if task is cancelled before copying message
            if not self._listener.is_cancelled and self._sent_msg is not None:
                await self._copy_message()

            if (
                not self._listener.is_cancelled
                and self._media_group
                and self._sent_msg is not None
                and hasattr(self._sent_msg, "chat")
                and self._sent_msg.chat is not None
                and hasattr(self._sent_msg.chat, "id")
                and hasattr(self._sent_msg, "id")
                and (
                    (hasattr(self._sent_msg, "video") and self._sent_msg.video)
                    or (
                        hasattr(self._sent_msg, "document")
                        and self._sent_msg.document
                    )
                )
            ):
                key = "documents" if self._sent_msg.document else "videos"
                if match := re_match(r".+(?=\.0*\d+$)|.+(?=\.part\d+\..+$)", o_path):
                    pname = match.group(0)
                    if pname in self._media_dict[key]:
                        self._media_dict[key][pname].append(
                            [self._sent_msg.chat.id, self._sent_msg.id]
                        )
                    else:
                        self._media_dict[key][pname] = [
                            [self._sent_msg.chat.id, self._sent_msg.id]
                        ]
                    msgs = self._media_dict[key][pname]
                    if len(msgs) == 10:
                        await self._send_media_group(pname, key, msgs)
                    else:
                        self._last_msg_in_group = True

            if (
                self._thumb is None
                and thumb is not None
                and await aiopath.exists(thumb)
            ):
                await remove(thumb)

            # Return the uploaded message on successful upload
            return self._sent_msg
        except (FloodWait, FloodPremiumWait) as f:
            await sleep(f.value * 1.3)
            if (
                self._thumb is None
                and thumb is not None
                and await aiopath.exists(thumb)
            ):
                await remove(thumb)
            return await self._upload_file(cap_mono, file, o_path)
        except Exception as err:
            if (
                self._thumb is None
                and thumb is not None
                and await aiopath.exists(thumb)
            ):
                await remove(thumb)
            err_type = "RPCError: " if isinstance(err, RPCError) else ""
            err_name = type(err).__name__
            LOGGER.error(f"{err_type}{err_name}: {err}. Path: {self._up_path}")

            # Handle memory errors and cancellation-related errors specifically
            if (
                isinstance(err, MemoryError)
                or err_name == "MemoryError"
                or "MemoryError" in str(err)
                or "'NoneType' object has no attribute 'write'" in str(err)
                or "'NoneType' object has no attribute 'chat'" in str(err)
                or "out of memory" in str(err).lower()
                or "cannot allocate memory" in str(err).lower()
            ):
                if "'NoneType' object has no attribute 'chat'" in str(err):
                    LOGGER.error(
                        f"Cancellation race condition detected during upload. Path: {self._up_path}"
                    )
                    # This is likely due to task cancellation, just return without retrying
                    return None

                LOGGER.error(
                    f"Memory error detected during upload. Path: {self._up_path}, Error: {str(err)[:200]}"
                )

                # Enhanced memory cleanup for memory errors
                try:
                    from bot.helper.ext_utils.gc_utils import (
                        smart_garbage_collection,
                    )

                    # Aggressive memory cleanup
                    smart_garbage_collection(aggressive=True, memory_error=True)

                    # Wait a moment for memory to be freed
                    await sleep(2)

                    # Check if we have enough memory now
                    memory_percent = get_memory_usage()
                    if memory_percent > 90:
                        LOGGER.error(
                            f"Memory usage still high ({memory_percent}%) after cleanup"
                        )
                        # Try waiting for memory to free up
                        if not await wait_for_memory_availability(
                            max_memory_percent=85, max_wait_time=30
                        ):
                            LOGGER.error(
                                "Unable to free enough memory for upload retry"
                            )
                            self._is_corrupted = True
                            return None

                except ImportError:
                    # Fallback to basic garbage collection
                    gc.collect()
                    gc.collect()  # Run twice for better cleanup
                    await sleep(2)

                # For streamrip uploads, try without thumbnail first to save memory
                if self._is_streamrip and not force_document:
                    LOGGER.info(
                        f"Retrying streamrip upload without thumbnail to save memory. Path: {self._up_path}"
                    )
                    # Temporarily disable thumbnail for this upload
                    original_thumb = self._thumb
                    self._thumb = "none"
                    try:
                        result = await self._upload_file(
                            cap_mono, file, o_path, False
                        )
                        if result is not None:
                            return result
                    except Exception as retry_err:
                        LOGGER.error(
                            f"Retry without thumbnail also failed: {retry_err}"
                        )
                    finally:
                        self._thumb = original_thumb

                # Try uploading as document if not already attempted
                if not force_document:
                    LOGGER.info(
                        f"Retrying upload as document after memory cleanup. Path: {self._up_path}"
                    )
                    return await self._upload_file(cap_mono, file, o_path, True)

                LOGGER.error(
                    f"Unable to upload file after memory cleanup and retries. Skipping file. Path: {self._up_path}"
                )
                self._is_corrupted = True
                return None

            if isinstance(err, BadRequest) and key != "documents":
                LOGGER.error(f"Retrying As Document. Path: {self._up_path}")
                return await self._upload_file(cap_mono, file, o_path, True)
            raise err

    async def _copy_media_group(self, msgs_list):
        """Copy a media group to additional destinations based on user settings"""
        # Check if task is cancelled before proceeding
        if self._listener.is_cancelled:
            return

        if not msgs_list:
            return

        # Check if the first message exists and has a chat attribute
        if (
            not msgs_list[0]
            or not hasattr(msgs_list[0], "chat")
            or msgs_list[0].chat is None
        ):
            LOGGER.error(
                "Cannot copy media group: First message is None or has no chat attribute"
            )
            return

        # Check if the chat has an id attribute
        if not hasattr(msgs_list[0].chat, "id"):
            LOGGER.error(
                "Cannot copy media group: First message's chat has no id attribute"
            )
            return

        source_chat_id = msgs_list[0].chat.id

        # Skip copying if we're already in the user's PM and no other destinations are needed
        if (
            source_chat_id == self._user_id
            and not self._user_dump
            and (not Config.LEECH_DUMP_CHAT or len(Config.LEECH_DUMP_CHAT) == 0)
        ):
            return

        # Determine the destinations based on user settings
        destinations = []

        # If user specified a destination with -up flag, it takes precedence
        # The primary message is already sent to the specified destination
        if self._listener.up_dest:
            # Add USER_DUMP if configured and different from source
            if self._user_dump and source_chat_id != int(self._user_dump):
                destinations.append(int(self._user_dump))

            # Add user's PM if it's not already the source and BOT_PM is enabled
            if source_chat_id != self._user_id and self._is_bot_pm_enabled():
                destinations.append(self._user_id)
        else:
            # No specific destination was specified
            # Follow the standard destination logic based on old Aeon-MLTB requirements

            # Check if user has set their own dump
            user_dump = self._user_dump

            # Case 1: If user set their own dump and owner has set leech dump chat
            if (
                user_dump
                and Config.LEECH_DUMP_CHAT
                and len(Config.LEECH_DUMP_CHAT) > 0
            ):
                # Send to user dump, leech dump chat, and bot PM
                if source_chat_id != int(user_dump):
                    destinations.append(int(user_dump))

                # Handle LEECH_DUMP_CHAT as a list
                if isinstance(Config.LEECH_DUMP_CHAT, list):
                    for chat_id in Config.LEECH_DUMP_CHAT:
                        # Process the chat ID format (handle prefixes like b:, u:, h:)
                        if isinstance(chat_id, str):
                            # Remove any prefixes like "b:", "u:", "h:" if present
                            if ":" in chat_id:
                                chat_id = chat_id.split(":", 1)[1]

                            # Remove any suffixes after | if present (for hybrid format)
                            if "|" in chat_id:
                                chat_id = chat_id.split("|", 1)[0]

                        # Add to destinations if not the source chat
                        if source_chat_id != int(chat_id):
                            destinations.append(int(chat_id))
                # For backward compatibility with single chat ID
                elif source_chat_id != Config.LEECH_DUMP_CHAT:
                    destinations.append(Config.LEECH_DUMP_CHAT)

                # Add user's PM if not already there and BOT_PM is enabled
                if source_chat_id != self._user_id and self._is_bot_pm_enabled():
                    destinations.append(self._user_id)

            # Case 2: If user set their own dump and owner didn't set leech dump chat
            elif user_dump and (
                not Config.LEECH_DUMP_CHAT or len(Config.LEECH_DUMP_CHAT) == 0
            ):
                # Send to user dump and bot PM
                try:
                    user_dump_int = int(user_dump)
                    if source_chat_id != user_dump_int:
                        destinations.append(user_dump_int)
                except (ValueError, TypeError) as e:
                    LOGGER.error(
                        f"Failed to convert user_dump '{user_dump}' to int: {e}"
                    )

                # Add user's PM if not already there and BOT_PM is enabled
                if source_chat_id != self._user_id and self._is_bot_pm_enabled():
                    destinations.append(self._user_id)

            # Case 3: If user didn't set their own dump and owner set leech dump chat
            elif (
                not user_dump
                and Config.LEECH_DUMP_CHAT
                and len(Config.LEECH_DUMP_CHAT) > 0
            ):
                # Send to leech dump chat and bot PM
                # Handle LEECH_DUMP_CHAT as a list
                if isinstance(Config.LEECH_DUMP_CHAT, list):
                    for chat_id in Config.LEECH_DUMP_CHAT:
                        # Process the chat ID format (handle prefixes like b:, u:, h:)
                        if isinstance(chat_id, str):
                            # Remove any prefixes like "b:", "u:", "h:" if present
                            if ":" in chat_id:
                                chat_id = chat_id.split(":", 1)[1]

                            # Remove any suffixes after | if present (for hybrid format)
                            if "|" in chat_id:
                                chat_id = chat_id.split("|", 1)[0]

                        # Add to destinations if not the source chat
                        if source_chat_id != int(chat_id):
                            destinations.append(int(chat_id))
                # For backward compatibility with single chat ID
                elif source_chat_id != Config.LEECH_DUMP_CHAT:
                    destinations.append(Config.LEECH_DUMP_CHAT)

                # Add user's PM if not already there and BOT_PM is enabled
                if source_chat_id != self._user_id and self._is_bot_pm_enabled():
                    destinations.append(self._user_id)

            # Case 4: If user didn't set their own dump and owner didn't set leech dump chat
            # Only send to user's PM if BOT_PM is enabled
            elif source_chat_id != self._user_id and self._is_bot_pm_enabled():
                destinations.append(self._user_id)

        # Remove duplicates while preserving order
        seen = set()
        destinations = [x for x in destinations if not (x in seen or seen.add(x))]

        if not destinations:
            return

        # Helper function to send media group to a destination
        async def _send_media_group_to_dest(dest):
            # Check if task is cancelled before sending media group
            if self._listener.is_cancelled:
                LOGGER.info(
                    f"Task is cancelled, skipping media group copy to {dest}"
                )
                return

            try:
                # Get the media IDs from the original messages
                media_ids = []
                for msg in msgs_list:
                    if hasattr(msg, "video") and msg.video:
                        media_ids.append(
                            InputMediaVideo(
                                media=msg.video.file_id,
                                parse_mode=enums.ParseMode.HTML,
                            )
                        )
                    elif hasattr(msg, "document") and msg.document:
                        media_ids.append(
                            InputMediaDocument(
                                media=msg.document.file_id,
                                parse_mode=enums.ParseMode.HTML,
                            )
                        )
                    elif hasattr(msg, "photo") and msg.photo:
                        media_ids.append(
                            InputMediaPhoto(
                                media=msg.photo.file_id,
                                parse_mode=enums.ParseMode.HTML,
                            )
                        )

                # Add caption to the first media item only
                if media_ids and msgs_list[0].caption:
                    media_ids[0].caption = msgs_list[0].caption
                    media_ids[0].parse_mode = enums.ParseMode.HTML

                # Check if we have a stored command message for this destination
                dest_str = str(dest)

                # For LEECH_DUMP_CHAT as a list, we need to check if the destination is in the list
                # and find the corresponding command message
                found_cmd_msg = None

                if hasattr(self, "dump_chat_msgs") and self.dump_chat_msgs:
                    # First, try direct lookup
                    if dest_str in self.dump_chat_msgs:
                        found_cmd_msg = self.dump_chat_msgs[dest_str]
                    else:
                        # If not found, try to match with processed chat IDs
                        for original_chat_id, cmd_msg in self.dump_chat_msgs.items():
                            processed_chat_id = original_chat_id

                            # Process the chat ID format (handle prefixes like b:, u:, h:)
                            if isinstance(processed_chat_id, str):
                                # Remove any prefixes like "b:", "u:", "h:" if present
                                if ":" in processed_chat_id:
                                    processed_chat_id = processed_chat_id.split(
                                        ":", 1
                                    )[1]

                                # Remove any suffixes after | if present (for hybrid format)
                                if "|" in processed_chat_id:
                                    processed_chat_id = processed_chat_id.split(
                                        "|", 1
                                    )[0]

                            # Check if the processed chat ID matches the destination
                            if str(processed_chat_id) == dest_str:
                                found_cmd_msg = cmd_msg
                                break

                # If we found a command message for this destination, reply to it
                if found_cmd_msg and hasattr(found_cmd_msg, "id"):
                    # Reply to the command message with the media group
                    if self._user_session:
                        await TgClient.user.send_media_group(
                            chat_id=dest,
                            media=media_ids,
                            disable_notification=True,
                            reply_to_message_id=found_cmd_msg.id,
                        )
                    else:
                        await self._listener.client.send_media_group(
                            chat_id=dest,
                            media=media_ids,
                            disable_notification=True,
                            reply_to_message_id=found_cmd_msg.id,
                        )
                # Send the media group to the destination without replying to a command message
                elif self._user_session:
                    await TgClient.user.send_media_group(
                        chat_id=dest,
                        media=media_ids,
                        disable_notification=True,
                    )
                else:
                    await self._listener.client.send_media_group(
                        chat_id=dest,
                        media=media_ids,
                        disable_notification=True,
                    )

            except Exception as e:
                error_str = str(e).lower()
                # Check for PEER_ID_INVALID error which means the bot is not in the chat
                if "peer_id_invalid" in error_str:
                    LOGGER.error(
                        f"Cannot send media group to {dest}: Bot is not a member of this chat or doesn't have permission to post"
                    )
                else:
                    LOGGER.error(
                        f"Failed to copy media group to destination {dest}: {e}"
                    )
                # Continue with other destinations even if one fails

        # Log the destinations for debugging
        if destinations:
            # Copy the media group to each destination
            for dest in destinations:
                # Check if task is cancelled before copying to each destination
                if self._listener.is_cancelled:
                    LOGGER.info(
                        "Task is cancelled, stopping media group copy to destinations"
                    )
                    break

                await _send_media_group_to_dest(dest)

        # We don't need this section anymore since we're already handling all chat IDs in the destinations list
        # The duplicate messages were happening because we were processing the chat IDs twice

    async def _copy_message(self):
        await sleep(0.5)

        # Check if task is cancelled or _sent_msg is None (due to cancellation)
        if self._listener.is_cancelled or self._sent_msg is None:
            LOGGER.info(
                "Task is cancelled or _sent_msg is None, skipping message copy"
            )
            return

        # Additional safety check for _sent_msg.chat
        if not hasattr(self._sent_msg, "chat") or self._sent_msg.chat is None:
            LOGGER.error(
                "Cannot copy message: _sent_msg has no chat attribute or chat is None"
            )
            return

        async def _copy(target, retries=3):
            for attempt in range(retries):
                try:
                    # Double-check _sent_msg is still valid before each copy attempt
                    if self._listener.is_cancelled or self._sent_msg is None:
                        LOGGER.info("Task cancelled during copy attempt, aborting")
                        return

                    # Additional safety check for _sent_msg attributes
                    if (
                        not hasattr(self._sent_msg, "chat")
                        or self._sent_msg.chat is None
                    ):
                        LOGGER.error(
                            "Cannot copy message: _sent_msg has no chat attribute or chat is None"
                        )
                        return

                    if not hasattr(self._sent_msg.chat, "id") or not hasattr(
                        self._sent_msg, "id"
                    ):
                        LOGGER.error(
                            "Cannot copy message: _sent_msg.chat or _sent_msg has no id attribute"
                        )
                        return

                    msg = await TgClient.bot.get_messages(
                        self._sent_msg.chat.id,
                        self._sent_msg.id,
                    )
                    await msg.copy(target)
                    LOGGER.info(
                        f"Leech media store: Successfully copied to destination {target}"
                    )
                    return
                except Exception as e:
                    error_str = str(e)
                    LOGGER.error(f"Attempt {attempt + 1} failed: {e}")

                    # Handle timeout errors with exponential backoff
                    if (
                        "Request timed out" in error_str
                        or "timeout" in error_str.lower()
                    ):
                        if attempt < retries - 1:
                            backoff_time = (2**attempt) * 2  # 2, 4, 8 seconds
                            LOGGER.info(
                                f"Timeout detected, waiting {backoff_time}s before retry..."
                            )
                            await sleep(backoff_time)
                            continue
                    elif attempt < retries - 1:
                        await sleep(1)  # Standard retry delay for other errors

            LOGGER.error(f"Failed to copy message after {retries} attempts")

        # Follow the same destination logic as _copy_media_group for consistency
        # Additional safety check for _sent_msg and its attributes
        if self._sent_msg is None:
            LOGGER.error("Cannot copy message: _sent_msg is None")
            return

        if not hasattr(self._sent_msg, "chat") or self._sent_msg.chat is None:
            LOGGER.error(
                "Cannot copy message: _sent_msg has no chat attribute or chat is None"
            )
            return

        if not hasattr(self._sent_msg.chat, "id"):
            LOGGER.error("Cannot copy message: _sent_msg.chat has no id attribute")
            return

        source_chat_id = self._sent_msg.chat.id
        destinations = []

        # If user specified a destination with -up flag, it takes precedence
        if self._listener.up_dest:
            # Even with -up flag, we should still respect USER_DUMP setting
            user_dump = self._user_dump
            if user_dump:
                try:
                    user_dump_int = int(user_dump)
                    if source_chat_id != user_dump_int:
                        destinations.append(user_dump_int)
                except (ValueError, TypeError) as e:
                    LOGGER.error(
                        f"Failed to convert user_dump '{user_dump}' to int (with -up flag): {e}"
                    )

            # We only need to copy to user's PM if it's not already there and BOT_PM is enabled
            if source_chat_id != self._user_id and self._is_bot_pm_enabled():
                destinations.append(self._user_id)
        else:
            # No specific destination was specified
            # Follow the standard destination logic based on old Aeon-MLTB requirements

            # Check if user has set their own dump
            user_dump = self._user_dump

            # Case 1: If user set their own dump and owner has set leech dump chat
            if (
                user_dump
                and Config.LEECH_DUMP_CHAT
                and len(Config.LEECH_DUMP_CHAT) > 0
            ):
                # Send to user dump, leech dump chat, and bot PM
                if source_chat_id != int(user_dump):
                    destinations.append(int(user_dump))

                # Handle LEECH_DUMP_CHAT as a list
                if isinstance(Config.LEECH_DUMP_CHAT, list):
                    for chat_id in Config.LEECH_DUMP_CHAT:
                        # Process the chat ID format (handle prefixes like b:, u:, h:)
                        if isinstance(chat_id, str):
                            # Remove any prefixes like "b:", "u:", "h:" if present
                            if ":" in chat_id:
                                chat_id = chat_id.split(":", 1)[1]

                            # Remove any suffixes after | if present (for hybrid format)
                            if "|" in chat_id:
                                chat_id = chat_id.split("|", 1)[0]

                        # Add to destinations if not the source chat
                        if source_chat_id != int(chat_id):
                            destinations.append(int(chat_id))
                # For backward compatibility with single chat ID
                elif source_chat_id != Config.LEECH_DUMP_CHAT:
                    destinations.append(Config.LEECH_DUMP_CHAT)

                # Add user's PM if not already there and BOT_PM is enabled
                if source_chat_id != self._user_id and self._is_bot_pm_enabled():
                    destinations.append(self._user_id)

            # Case 2: If user set their own dump and owner didn't set leech dump chat
            elif user_dump and (
                not Config.LEECH_DUMP_CHAT or len(Config.LEECH_DUMP_CHAT) == 0
            ):
                # Send to user dump and bot PM
                try:
                    user_dump_int = int(user_dump)
                    if source_chat_id != user_dump_int:
                        destinations.append(user_dump_int)
                except (ValueError, TypeError) as e:
                    LOGGER.error(
                        f"Failed to convert user_dump '{user_dump}' to int in _copy_message: {e}"
                    )

                # Add user's PM if not already there and BOT_PM is enabled
                if source_chat_id != self._user_id and self._is_bot_pm_enabled():
                    destinations.append(self._user_id)

            # Case 3: If user didn't set their own dump and owner set leech dump chat
            elif (
                not user_dump
                and Config.LEECH_DUMP_CHAT
                and len(Config.LEECH_DUMP_CHAT) > 0
            ):
                # Send to leech dump chat and bot PM
                # Handle LEECH_DUMP_CHAT as a list
                if isinstance(Config.LEECH_DUMP_CHAT, list):
                    for chat_id in Config.LEECH_DUMP_CHAT:
                        # Process the chat ID format (handle prefixes like b:, u:, h:)
                        if isinstance(chat_id, str):
                            # Remove any prefixes like "b:", "u:", "h:" if present
                            if ":" in chat_id:
                                chat_id = chat_id.split(":", 1)[1]

                            # Remove any suffixes after | if present (for hybrid format)
                            if "|" in chat_id:
                                chat_id = chat_id.split("|", 1)[0]

                        # Add to destinations if not the source chat
                        if source_chat_id != int(chat_id):
                            destinations.append(int(chat_id))
                # For backward compatibility with single chat ID
                elif source_chat_id != Config.LEECH_DUMP_CHAT:
                    destinations.append(Config.LEECH_DUMP_CHAT)

                # Add user's PM if not already there and BOT_PM is enabled
                if source_chat_id != self._user_id and self._is_bot_pm_enabled():
                    destinations.append(self._user_id)

            # Case 4: If user didn't set their own dump and owner didn't set leech dump chat
            # Only send to user's PM if BOT_PM is enabled
            elif source_chat_id != self._user_id and self._is_bot_pm_enabled():
                destinations.append(self._user_id)

        # Remove duplicates while preserving order
        seen = set()
        destinations = [x for x in destinations if not (x in seen or seen.add(x))]

        # Copy to all destinations
        for dest in destinations:
            # Check cancellation status before each copy
            if self._listener.is_cancelled or self._sent_msg is None:
                LOGGER.info("Task cancelled during message copy, aborting")
                break

            with contextlib.suppress(Exception):
                await _copy(dest)

    @property
    def speed(self):
        try:
            return self._processed_bytes / (time() - self._start_time)
        except Exception:
            return 0

    @property
    def processed_bytes(self):
        return self._processed_bytes

    async def cancel_task(self):
        self._listener.is_cancelled = True

        # Check if upload has actually started by looking for upload-specific attributes
        upload_started = (
            (hasattr(self, "_processed_bytes") and self._processed_bytes > 0)
            or (hasattr(self, "_sent_msg") and self._sent_msg is not None)
            or (hasattr(self, "_media_dict") and len(self._media_dict) > 0)
        )

        if upload_started:
            LOGGER.info(f"Cancelling Upload: {self._listener.name}")
        else:
            LOGGER.info(f"Cancelling Upload preparation: {self._listener.name}")

        # Safely handle cancellation to prevent race conditions
        try:
            # Stop any ongoing transmissions (only if not already stopped)
            if not self._transmission_stopped:
                if self._user_session and TgClient.user:
                    try:
                        TgClient.user.stop_transmission()
                        self._transmission_stopped = True
                    except Exception:
                        self._transmission_stopped = True
                elif self._listener.client:
                    try:
                        self._listener.client.stop_transmission()
                        self._transmission_stopped = True
                    except Exception:
                        self._transmission_stopped = True

            # Clear media dictionaries to prevent further processing
            if hasattr(self, "_media_dict"):
                self._media_dict.clear()
            if hasattr(self, "_msgs_dict"):
                self._msgs_dict.clear()

            # Set self._sent_msg to None to prevent any further attempts to copy it
            # This will prevent the "Cannot copy message: self._sent_msg is None" error
            if hasattr(self, "_sent_msg"):
                self._sent_msg = None
        except Exception as e:
            LOGGER.error(f"Error during upload cancellation cleanup: {e}")

        # Only show upload cancellation message if upload actually started
        if upload_started:
            await self._listener.on_upload_error("your upload has been stopped!")
