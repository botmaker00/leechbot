"""
Gallery-dl module for aimleechbot
Following the exact pattern of ytdlp.py
"""

from asyncio import Lock, create_task

from bot import LOGGER, task_dict, task_dict_lock
from bot.helper.ext_utils.bot_utils import (
    COMMAND_USAGE,
    arg_parser,
    new_task,
)
from bot.helper.ext_utils.links_utils import is_url
from bot.helper.ext_utils.task_manager import check_running_tasks
from bot.helper.listeners.task_listener import TaskListener
from bot.helper.mirror_leech_utils.download_utils.gallery_dl_download import (
    GalleryDLHelper,
)
from bot.helper.mirror_leech_utils.gallery_dl_utils.quality_selector import (
    get_gallery_dl_quality_selector,
    get_platform_from_url,
    get_platform_info,
    is_platform_supported,
    show_gallery_dl_quality_selector,
)
from bot.helper.mirror_leech_utils.gallery_dl_utils.url_parser import (
    get_gallery_dl_info,
    is_gallery_dl_url,
)
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    send_message,
    send_status_message,
)

try:
    import gallery_dl
except ImportError:
    gallery_dl = None
    LOGGER.error("gallery-dl not installed. Install with: pip install gallery-dl")


class GdlSelection:
    """Gallery-dl selection class following YtSelection pattern"""

    def __init__(self, listener):
        self.listener = listener

    async def get_quality(self, result):
        """Get quality selection from user"""
        try:
            platform_info = result.get("platform_info", {})
            platform = platform_info.get("extractor", "unknown")
            content_type = platform_info.get("subcategory", "media")

            # Show quality selection interface
            quality_config = await show_gallery_dl_quality_selector(
                self.listener, platform, content_type
            )

            if not quality_config:
                return None, None

            return quality_config, platform_info

        except Exception as e:
            LOGGER.error(f"Error in gallery-dl quality selection: {e}")
            return None, None


class Gdl(TaskListener):
    """Gallery-dl downloader class following YtDlp pattern"""

    def __init__(
        self,
        client,
        message,
        _=None,  # Placeholder for compatibility with Mirror class
        is_leech=False,
        # These parameters are unused but required for compatibility with Mirror class
        **kwargs,
    ):
        # Import Config here to avoid import issues (needed throughout the class)
        try:
            from bot.core.config_manager import Config

            self.Config = Config
        except ImportError:
            self.Config = None

        # Extract parameters from kwargs with defaults
        same_dir = kwargs.get("same_dir", {})
        bulk = kwargs.get("bulk", [])
        multi_tag = kwargs.get("multi_tag")
        options = kwargs.get("options", "")
        if same_dir is None:
            same_dir = {}
        if bulk is None:
            bulk = []

        # Set required attributes BEFORE calling super().__init__()
        self.message = message
        self.client = client
        self.multi_tag = multi_tag
        self.options = options
        self.same_dir = same_dir
        self.bulk = bulk

        # Initialize TaskListener which handles all the standard setup
        super().__init__()

        # Set gallery-dl specific attributes AFTER super().__init__()
        self.is_gallery_dl = True
        self.is_leech = is_leech
        self.gallery_dl_helper = None
        self.platform = None

        # CRITICAL FIX: Override is_super_chat for Gallery-dl to enable file links generation
        # This bypasses the TelegramUploader _is_private check for PM operations
        # Gallery-dl needs file links for completion messages regardless of chat type
        self.is_super_chat = True

        # Set tool for limit checking
        self.tool = "gallery-dl"

        # Set tag for user mention in completion messages (same logic as other listeners)

        if hasattr(self, "user") and self.user:
            if username := getattr(self.user, "username", None):
                self.tag = f"@{username}"
            elif hasattr(self.user, "mention"):
                self.tag = self.user.mention
            else:
                self.tag = getattr(
                    self.user,
                    "title",
                    f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>",
                )
        else:
            self.tag = f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>"

        # Add missing attributes required by TaskListener
        self.status_lock = Lock()
        self.gid = None  # Will be set when download starts

    def get_id(self):
        """Get unique identifier for this task"""
        return self.mid

    @new_task
    async def new_event(self):
        """Main entry point following YtDlp.new_event pattern"""
        try:
            # Check if gallery-dl is available
            if not gallery_dl:
                await send_message(
                    self.message,
                    "❌ Gallery-dl is not installed. Please install it first.",
                )
                return

            # Check if gallery-dl is enabled
            if not (
                self.Config
                and hasattr(self.Config, "GALLERY_DL_ENABLED")
                and self.Config.GALLERY_DL_ENABLED
            ):
                await send_message(
                    self.message, "❌ Gallery-dl downloads are disabled."
                )
                return

            # Parse arguments
            text = self.message.text.split("\n")
            input_list = text[0].split(" ")

            args = {
                "link": "",
                "folder_name": "",
                "headers": "",
                "bulk_start": 0,
                "bulk_end": 0,
                "join": False,
                "extract": False,
                "compress": False,
                "select": False,
                "seed": False,
                "multi": 0,
                "options": self.options,
            }

            arg_parser(input_list[1:], args)

            # Get URL
            try:
                self.link = args["link"] or ""
                if not self.link and self.message.reply_to_message:
                    self.link = self.message.reply_to_message.text.split("\n")[
                        0
                    ].split(" ")[0]
            except Exception:
                self.link = ""

            if not self.link:
                # Show usage help like ytdl does
                await delete_links(self.message)
                usage_msg = await send_message(
                    self.message,
                    COMMAND_USAGE["gdl"][0],
                    COMMAND_USAGE["gdl"][1],
                )
                create_task(auto_delete_message(usage_msg, time=300))  # noqa: RUF006
                await self.remove_from_same_dir()
                return

            if not is_url(self.link):
                await send_message(self.message, "❌ Invalid URL!")
                return

            # Check if URL is supported by gallery-dl
            if not await is_gallery_dl_url(self.link):
                await send_message(
                    self.message, "❌ This URL is not supported by gallery-dl!"
                )
                return

            # Get platform information
            platform_info = await get_gallery_dl_info(self.link)
            if not platform_info:
                await send_message(
                    self.message, "❌ Failed to get platform information!"
                )
                return

            self.platform = platform_info.get("extractor")

            # Set up listener properties
            self.name = args.get("folder_name") or f"Gallery-dl_{self.platform}"
            self.up_dest = args.get("up_dest", "")
            self.rc_flags = args.get("rc_flags", "")
            self.tag = args.get("tag", "")

            # Handle DEFAULT_UPLOAD for mirror operations (same logic as mirror_leech.py)
            if not self.is_leech and not self.up_dest:
                # Check user's DEFAULT_UPLOAD setting first, then fall back to global setting
                default_upload = (
                    self.Config.DEFAULT_UPLOAD
                    if self.Config and hasattr(self.Config, "DEFAULT_UPLOAD")
                    else "gd"
                )
                user_default_upload = self.user_dict.get(
                    "DEFAULT_UPLOAD", default_upload
                )
                if user_default_upload == "gd":
                    self.up_dest = "gd"
                elif user_default_upload == "mg":
                    self.up_dest = "mg"
                elif user_default_upload == "yt":
                    self.up_dest = "yt"
                elif user_default_upload == "ddl":
                    self.up_dest = "ddl"
                elif user_default_upload == "rc":
                    # For rclone, we need a valid path - if none configured, fall back to gd
                    if (
                        self.Config
                        and hasattr(self.Config, "RCLONE_ENABLED")
                        and self.Config.RCLONE_ENABLED
                        and hasattr(self.Config, "RCLONE_PATH")
                        and self.Config.RCLONE_PATH
                    ):
                        self.up_dest = self.Config.RCLONE_PATH
                    else:
                        # Fall back to Google Drive if rclone not properly configured
                        self.up_dest = "gd"
            self.extract = args.get("extract", False)
            self.compress = args.get("compress", False)
            self.select = args.get("select", False)
            self.seed = args.get("seed", False)
            self.join = args.get("join", False)
            self.bulk_start = args.get("bulk_start", 0)
            self.bulk_end = args.get("bulk_end", 0)
            self.multi = args.get("multi", 0)

            # Add missing attributes expected by TaskListener
            self.compression_enabled = args.get("compression_enabled", False)
            self.extract_enabled = args.get("extract_enabled", False)
            self.watermark_enabled = args.get("watermark_enabled", False)
            self.trim_enabled = args.get("trim_enabled", False)

            # Add priority attributes
            self.compression_priority = args.get("compression_priority", 1)
            self.extract_priority = args.get("extract_priority", 2)
            self.watermark_priority = args.get("watermark_priority", 3)
            self.trim_priority = args.get("trim_priority", 4)

            # Add media processing attributes
            self.watermark = args.get("watermark", "")
            self.trim = args.get("trim", "")
            self.metadata = args.get("metadata", False)
            self.metadata_title = args.get("metadata_title", "")
            self.metadata_author = args.get("metadata_author", "")
            self.metadata_comment = args.get("metadata_comment", "")
            self.metadata_all = args.get("metadata_all", False)
            self.metadata_video_title = args.get("metadata_video_title", "")
            self.metadata_video_author = args.get("metadata_video_author", "")
            self.metadata_video_comment = args.get("metadata_video_comment", "")
            self.metadata_audio_title = args.get("metadata_audio_title", "")
            self.metadata_audio_author = args.get("metadata_audio_author", "")
            self.metadata_audio_comment = args.get("metadata_audio_comment", "")
            self.metadata_subtitle_title = args.get("metadata_subtitle_title", "")
            self.metadata_subtitle_author = args.get("metadata_subtitle_author", "")
            self.metadata_subtitle_comment = args.get(
                "metadata_subtitle_comment", ""
            )

            # Listener is already initialized by super().__init__()

            # CRITICAL FIX: Restore properties that get overwritten by argument parsing

            # Fix 1: Restore tag property (gets overwritten by args.get("tag", ""))
            if not self.tag:
                if hasattr(self, "user") and self.user:
                    if username := getattr(self.user, "username", None):
                        self.tag = f"@{username}"
                    elif hasattr(self.user, "mention"):
                        self.tag = self.user.mention
                    else:
                        self.tag = getattr(
                            self.user,
                            "title",
                            f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>",
                        )
                else:
                    self.tag = (
                        f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>"
                    )

            # Fix 2: Implement correct leech destination logic
            # For BOTH PM and Group operations: Primary destination = Dump chats, Secondary = User's PM
            # This ensures consistent behavior and file links generation from dump chats
            if self.is_leech and not self.up_dest:
                # Both PM and Group operations: Set up_dest to dump chats (primary destination)
                # Files will be sent to dump chats first, then copied to user's PM
                if (
                    self.Config
                    and hasattr(self.Config, "LEECH_DUMP_CHAT")
                    and self.Config.LEECH_DUMP_CHAT
                    and len(self.Config.LEECH_DUMP_CHAT) > 0
                ):
                    # Use the first dump chat as primary destination
                    if isinstance(self.Config.LEECH_DUMP_CHAT, list):
                        dump_chat = self.Config.LEECH_DUMP_CHAT[0]
                        # Process the chat ID format (handle prefixes like b:, u:, h:)
                        if isinstance(dump_chat, str) and ":" in dump_chat:
                            dump_chat = dump_chat.split(":", 1)[1]
                        if isinstance(dump_chat, str) and "|" in dump_chat:
                            dump_chat = dump_chat.split("|", 1)[0]
                        self.up_dest = str(dump_chat)
                    else:
                        self.up_dest = str(self.Config.LEECH_DUMP_CHAT)

                else:
                    # Fallback: If no dump chat configured, use user's PM
                    self.up_dest = str(self.user_id)

            # Check quality selection with enhanced platform detection
            quality_config = None
            detected_platform = "default"

            if (
                self.Config
                and hasattr(self.Config, "GALLERY_DL_QUALITY_SELECTION")
                and self.Config.GALLERY_DL_QUALITY_SELECTION
            ):
                # Detect platform from URL for better quality options
                detected_platform = get_platform_from_url(self.link)
                get_platform_info(detected_platform)

                # Store detected platform in listener for filename template
                self.platform = detected_platform

                # Only show quality selection if platform is supported
                if is_platform_supported(detected_platform):
                    quality_config = await show_gallery_dl_quality_selector(
                        self, detected_platform, "media", self.link
                    )

                    if quality_config is None:
                        # User cancelled or error occurred
                        return

                    # Add platform info to quality config
                    if quality_config:
                        quality_config["platform"] = detected_platform
                else:
                    quality_config = {
                        "quality": "original",
                        "format": "best",
                        "platform": detected_platform,
                    }
            else:
                # Even without quality selection, detect platform for proper configuration
                detected_platform = get_platform_from_url(self.link)
                quality_config = {
                    "quality": "original",
                    "format": "best",
                    "platform": detected_platform,
                }

            # Store platform for use in download helper
            self.platform = detected_platform

            # Start download
            await self._start_download(quality_config)

        except Exception as e:
            LOGGER.error(f"Error in gallery-dl new_event: {e}")
            await self.on_download_error(str(e))

    async def _start_download(self, quality_config):
        """Start the gallery-dl download"""
        try:
            # Create download path
            path = f"{self.dir}{self.name}"

            # Update the listener's directory to point to the actual download location
            # This is crucial for Gallery-dl since it downloads to a subdirectory
            self.dir = path

            # Check running tasks and queue management
            add_to_queue, event = await check_running_tasks(self)
            gid = "".join(__import__("os").urandom(12).hex())
            self.gid = gid

            if add_to_queue:
                LOGGER.info(f"Added to Queue/Download: {self.name}")
                async with task_dict_lock:
                    task_dict[self.mid] = QueueStatus(self, gid, "dl")
                await self.on_download_start()
                if self.multi <= 1:
                    await send_status_message(self.message)
                await event.wait()
                if self.is_cancelled:
                    return

            # Initialize gallery-dl helper
            self.gallery_dl_helper = GalleryDLHelper(self)

            # Start download with proper status tracking
            await self.on_download_start()
            if self.multi <= 1:
                await send_status_message(self.message)

            # Start the actual download
            await self.gallery_dl_helper.add_download(
                path=path,
                quality_config=quality_config,
                options=self.options,
            )

        except Exception as e:
            LOGGER.error(f"Error starting gallery-dl download: {e}")
            await self.on_download_error(str(e))

    async def on_download_start(self):
        """Handle download start - required by TaskListener"""
        await super().on_download_start()

    async def on_download_complete(self):
        """Handle download complete - required by TaskListener"""
        await super().on_download_complete()

    async def on_upload_complete(
        self, link, files, total_files, corrupted, rclone_path="", dir_id=""
    ):
        """Handle upload complete - required by TaskListener"""
        # For leech operations, call the parent method with proper parameters
        # The parent method expects: link, files, folders, mime_type, rclone_path, dir_id
        # But telegram uploader calls with: link, files, total_files, corrupted

        # Map the parameters correctly for the parent method
        folders = total_files  # Total files count
        mime_type = corrupted  # Corrupted files count

        # CRITICAL FIX: Ensure tag and up_dest properties are preserved
        # These properties get overwritten somewhere, so we need to restore them

        # Restore tag property
        if not hasattr(self, "tag") or not self.tag:
            if hasattr(self, "user") and self.user:
                if username := getattr(self.user, "username", None):
                    self.tag = f"@{username}"
                elif hasattr(self.user, "mention"):
                    self.tag = self.user.mention
                else:
                    self.tag = getattr(
                        self.user,
                        "title",
                        f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>",
                    )
            else:
                self.tag = (
                    f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>"
                )

        # Restore up_dest property if it gets cleared during upload process
        if self.is_leech and (not hasattr(self, "up_dest") or not self.up_dest):
            # Both PM and Group operations: Restore to dump chats (primary destination)
            if (
                self.Config
                and hasattr(self.Config, "LEECH_DUMP_CHAT")
                and self.Config.LEECH_DUMP_CHAT
                and len(self.Config.LEECH_DUMP_CHAT) > 0
            ):
                if isinstance(self.Config.LEECH_DUMP_CHAT, list):
                    dump_chat = self.Config.LEECH_DUMP_CHAT[0]
                    if isinstance(dump_chat, str) and ":" in dump_chat:
                        dump_chat = dump_chat.split(":", 1)[1]
                    if isinstance(dump_chat, str) and "|" in dump_chat:
                        dump_chat = dump_chat.split("|", 1)[0]
                    self.up_dest = str(dump_chat)
                else:
                    self.up_dest = str(self.Config.LEECH_DUMP_CHAT)

            else:
                # Fallback: If no dump chat configured, use user's PM
                self.up_dest = str(self.user_id)

        await super().on_upload_complete(
            link, files, folders, mime_type, rclone_path, dir_id
        )

    async def on_upload_error(self, error):
        """Handle upload error - required by TaskListener"""
        await super().on_upload_error(error)

    async def on_download_error(self, error, button=None):
        """Handle download error"""
        async with self.status_lock:
            try:
                await send_message(
                    self.message,
                    f"❌ <b>Gallery-dl Download Error:</b>\n<code>{error}</code>",
                    button,
                )
            except Exception as e:
                LOGGER.error(f"Error sending error message: {e}")

        self.is_cancelled = True
        await self.remove_from_same_dir()

    async def cancel_task(self):
        """Cancel the download task"""
        self.is_cancelled = True
        LOGGER.info(f"Cancelling gallery-dl download: {self.name}")

        if self.gallery_dl_helper:
            await self.gallery_dl_helper.cancel_task()


# Command handlers following ytdlp.py pattern


async def gdl_mirror(client, message):
    """Gallery-dl mirror command handler"""
    await Gdl(client, message).new_event()


async def gdl_leech(client, message):
    """Gallery-dl leech command handler"""
    await Gdl(client, message, is_leech=True).new_event()


async def gdl_callback(_, callback_query):
    """Handle gallery-dl callback queries"""
    try:
        data = callback_query.data.split()
        user_id = callback_query.from_user.id

        if data[0] == "gdlq":
            # Quality selection callback
            selector = get_gallery_dl_quality_selector(user_id)
            if selector:
                await selector.handle_callback(data)
            else:
                await callback_query.answer("Selection expired!", show_alert=True)

        await callback_query.answer()

    except Exception as e:
        LOGGER.error(f"Error in gallery-dl callback: {e}")
        await callback_query.answer("An error occurred!", show_alert=True)


# Handlers are registered in bot/core/handlers.py
