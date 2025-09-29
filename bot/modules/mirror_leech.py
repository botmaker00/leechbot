# ruff: noqa: RUF006
from asyncio import create_task
from base64 import b64encode
from re import match as re_match

from bot import DOWNLOAD_DIR, LOGGER, bot_loop, task_dict_lock
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.aeon_utils.access_check import error_check
from bot.helper.ext_utils.aiofiles_compat import aiopath
from bot.helper.ext_utils.bot_utils import (
    COMMAND_USAGE,
    arg_parser,
    get_content_type,
    sync_to_async,
)
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.links_utils import (
    is_gdrive_id,
    is_gdrive_link,
    is_magnet,
    is_mega_link,
    is_rclone_path,
    is_telegram_link,
    is_url,
)
from bot.helper.listeners.task_listener import TaskListener
from bot.helper.mirror_leech_utils.download_utils.aria2_download import (
    add_aria2_download,
)
from bot.helper.mirror_leech_utils.download_utils.direct_downloader import (
    add_direct_download,
)
from bot.helper.mirror_leech_utils.download_utils.direct_link_generator import (
    direct_link_generator,
)
from bot.helper.mirror_leech_utils.download_utils.gd_download import add_gd_download
from bot.helper.mirror_leech_utils.download_utils.jd_download import add_jd_download
from bot.helper.mirror_leech_utils.download_utils.mega_download import (
    add_mega_download,
)
from bot.helper.mirror_leech_utils.download_utils.nzb_downloader import add_nzb
from bot.helper.mirror_leech_utils.download_utils.qbit_download import add_qb_torrent
from bot.helper.mirror_leech_utils.download_utils.rclone_download import (
    add_rclone_download,
)
from bot.helper.mirror_leech_utils.download_utils.streamrip_download import (
    add_streamrip_download,
)
from bot.helper.mirror_leech_utils.download_utils.telegram_download import (
    TelegramDownloadHelper,
)
from bot.helper.mirror_leech_utils.download_utils.zotify_download import (
    add_zotify_download,
)
from bot.helper.mirror_leech_utils.streamrip_utils.url_parser import is_streamrip_url
from bot.helper.mirror_leech_utils.zotify_utils.url_parser import is_zotify_url
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    get_tg_link_message,
    send_message,
)
from bot.modules.media_tools import show_media_tools_for_task


class Mirror(TaskListener):
    def __init__(
        self,
        client,
        message,
        is_qbit=False,
        is_leech=False,
        is_jd=False,
        is_nzb=False,
        same_dir=None,
        bulk=None,
        multi_tag=None,
        options="",
    ):
        if same_dir is None:
            same_dir = {}
        if bulk is None:
            bulk = []
        self.message = message
        self.client = client
        self.multi_tag = multi_tag
        self.options = options
        self.same_dir = same_dir
        self.bulk = bulk
        super().__init__()
        self.is_qbit = is_qbit
        self.is_leech = is_leech
        self.is_jd = is_jd
        self.is_nzb = is_nzb

    async def new_event(self):
        # Ensure user_dict is never None to prevent AttributeError
        self._ensure_user_dict()

        # Check if message text exists before trying to split it
        if (
            not self.message
            or not hasattr(self.message, "text")
            or self.message.text is None
        ):
            LOGGER.error(
                "Message text is None or message doesn't have text attribute"
            )
            error_msg = "Invalid message format. Please make sure your message contains text."
            error = await send_message(self.message, error_msg)
            return await auto_delete_message(error, time=300)

        text = self.message.text.split("\n")
        input_list = text[0].split(" ")
        error_msg, error_button = await error_check(self.message)
        if error_msg:
            await delete_links(self.message)
            error = await send_message(self.message, error_msg, error_button)
            return await auto_delete_message(error, time=300)
        user_id = self.message.from_user.id if self.message.from_user else ""
        args = {
            "-doc": False,
            "-med": False,
            "-d": False,
            "-j": False,
            "-s": False,
            "-b": False,
            "-e": False,
            "-z": False,
            "-sv": False,
            "-ss": False,
            "-f": False,
            "-fd": False,
            "-fu": False,
            "-hl": False,
            "-bt": False,
            "-ut": False,
            "-mt": False,
            "-merge-video": False,
            "-merge-audio": False,
            "-merge-subtitle": False,
            "-merge-all": False,
            "-merge-image": False,
            "-merge-pdf": False,
            "-i": 0,
            "-sp": 0,
            "link": "",
            "-n": "",
            "-m": "",  # Same directory operation flag
            "-watermark": "",
            "-iwm": "",
            "-up": "",
            "-rcf": "",
            "-au": "",
            "-ap": "",
            "-h": [],
            "-t": "",
            "-ca": "",
            "-cv": "",
            "-ns": "",
            "-md": "",
            "-metadata-title": "",
            "-metadata-author": "",
            "-metadata-comment": "",
            "-metadata-all": "",
            "-metadata-video-title": "",
            "-metadata-video-author": "",
            "-metadata-video-comment": "",
            "-metadata-audio-title": "",
            "-metadata-audio-author": "",
            "-metadata-audio-comment": "",
            "-metadata-subtitle-title": "",
            "-metadata-subtitle-author": "",
            "-metadata-subtitle-comment": "",
            "-tl": "",
            "-ff": set(),
            "-compress": False,
            "-comp-video": False,
            "-comp-audio": False,
            "-comp-image": False,
            "-comp-document": False,
            "-comp-subtitle": False,
            "-comp-archive": False,
            "-video-fast": False,
            "-video-medium": False,
            "-video-slow": False,
            "-audio-fast": False,
            "-audio-medium": False,
            "-audio-slow": False,
            "-image-fast": False,
            "-image-medium": False,
            "-image-slow": False,
            "-document-fast": False,
            "-document-medium": False,
            "-document-slow": False,
            "-subtitle-fast": False,
            "-subtitle-medium": False,
            "-subtitle-slow": False,
            "-archive-fast": False,
            "-archive-medium": False,
            "-archive-slow": False,
            "-trim": "",
            "-extract": False,
            "-extract-video": False,
            "-extract-audio": False,
            "-extract-subtitle": False,
            "-extract-attachment": False,
            "-extract-video-index": "",
            "-extract-audio-index": "",
            "-extract-subtitle-index": "",
            "-extract-attachment-index": "",
            "-extract-video-codec": "",
            "-extract-audio-codec": "",
            "-extract-subtitle-codec": "",
            "-extract-maintain-quality": "",
            "-extract-priority": "",
            "-remove": False,
            "-remove-video": False,
            "-remove-audio": False,
            "-remove-subtitle": False,
            "-remove-attachment": False,
            "-remove-metadata": False,
            "-remove-video-index": "",
            "-remove-audio-index": "",
            "-remove-subtitle-index": "",
            "-remove-attachment-index": "",
            "-remove-priority": "",
            "-add": False,
            "-add-video": False,
            "-add-audio": False,
            "-add-subtitle": False,
            "-add-attachment": False,
            "-del": "",
            "-preserve": False,
            "-replace": False,
            # Shorter index flags
            "-vi": "",
            "-ai": "",
            "-si": "",
            "-ati": "",
            # Remove shorter index flags
            "-rvi": "",
            "-rai": "",
            "-rsi": "",
            "-rati": "",
            # Swap flags
            "-swap": False,
            "-swap-audio": False,
            "-swap-video": False,
            "-swap-subtitle": False,
        }

        # Parse arguments from the command
        arg_parser(input_list[1:], args)

        # Check if media tools flags are enabled
        from bot.helper.ext_utils.bot_utils import is_flag_enabled

        # Disable flags that depend on disabled media tools
        for flag in list(args.keys()):
            if flag.startswith("-") and not is_flag_enabled(flag):
                if isinstance(args[flag], bool):
                    args[flag] = False
                elif isinstance(args[flag], set):
                    args[flag] = set()
                elif isinstance(args[flag], str):
                    args[flag] = ""
                elif isinstance(args[flag], int):
                    args[flag] = 0

        self.select = args["-s"]
        self.seed = args["-d"]
        self.name = args["-n"]
        self.up_dest = args["-up"]

        # Handle DEFAULT_UPLOAD and -up flag for various upload destinations
        if not self.is_leech:
            # Check user's DEFAULT_UPLOAD setting first, then fall back to global setting
            user_default_upload = self.user_dict.get(
                "DEFAULT_UPLOAD", Config.DEFAULT_UPLOAD
            )
            if user_default_upload == "gd" and not self.up_dest:
                self.up_dest = "gd"
            elif user_default_upload == "mg" and not self.up_dest:
                self.up_dest = "mg"
            elif user_default_upload == "yt" and not self.up_dest:
                self.up_dest = "yt"
            elif user_default_upload == "ddl" and not self.up_dest:
                self.up_dest = "ddl"

            if self.up_dest == "gd":
                # Validate Google Drive configuration
                if not Config.GDRIVE_UPLOAD_ENABLED:
                    await send_message(
                        self.message,
                        "❌ Google Drive upload is disabled by the administrator.",
                    )
                    return None
            elif self.up_dest == "mg":
                # Validate MEGA configuration
                if not Config.MEGA_ENABLED:
                    await send_message(
                        self.message,
                        "❌ MEGA.nz operations are disabled by the administrator.",
                    )
                    return None
                if not Config.MEGA_UPLOAD_ENABLED:
                    await send_message(
                        self.message,
                        "❌ MEGA upload is disabled by the administrator.",
                    )
                    return None

                # Check for user MEGA credentials first, then fall back to owner credentials
                user_mega_email = self.user_dict.get("MEGA_EMAIL")
                user_mega_password = self.user_dict.get("MEGA_PASSWORD")

                has_user_credentials = user_mega_email and user_mega_password
                has_owner_credentials = Config.MEGA_EMAIL and Config.MEGA_PASSWORD

                if not has_user_credentials and not has_owner_credentials:
                    await send_message(
                        self.message,
                        "❌ MEGA credentials not configured. Please set your MEGA credentials in user settings or contact the administrator.",
                    )
                    return None

                # Determine which account will be used and check if folder selection is needed

                # Always show MEGA folder selection since we removed upload folder config
                show_folder_selection = True

                # Show MEGA folder selection for all MEGA uploads
                if show_folder_selection:
                    from bot.helper.mirror_leech_utils.mega_utils.folder_selector import (
                        MegaFolderSelector,
                    )

                    folder_selector = MegaFolderSelector(self)
                    selected_path = await folder_selector.get_mega_path()

                    if selected_path is None:
                        # User cancelled
                        await self.remove_from_same_dir()
                        return None
                    if isinstance(selected_path, str) and selected_path.startswith(
                        "❌"
                    ):
                        # Error occurred
                        await send_message(self.message, selected_path)
                        await self.remove_from_same_dir()
                        return None
                    # Store selected path for this upload
                    self.mega_upload_path = selected_path
            elif self.up_dest == "yt":
                # Validate YouTube configuration
                if not Config.YOUTUBE_UPLOAD_ENABLED:
                    await send_message(
                        self.message,
                        "❌ YouTube upload is disabled by the administrator.",
                    )
                    return None
            elif self.up_dest == "ddl":
                # Validate DDL configuration
                if not Config.DDL_ENABLED:
                    await send_message(
                        self.message,
                        "❌ DDL upload is disabled by the administrator.",
                    )
                    return None

                # Check DDL server configuration
                from bot.modules.users_settings import get_ddl_setting

                user_id = self.message.from_user.id
                default_server, _ = get_ddl_setting(user_id, "DDL_SERVER", "gofile")

        self.rc_flags = args["-rcf"]
        self.link = args["link"]
        self.compress = args["-z"]
        # Enable compression if -z flag is set and archive flags are enabled
        from bot.helper.ext_utils.bot_utils import is_flag_enabled

        if self.compress and is_flag_enabled("-z"):
            self.compression_enabled = True
        self.extract = args["-e"]
        # Enable extract_enabled if -e flag is set and archive flags are enabled
        if self.extract and is_flag_enabled("-e"):
            self.extract_enabled = True

        # Add settings
        self.add_enabled = args["-add"]
        self.add_video_enabled = args["-add-video"]
        self.add_audio_enabled = args["-add-audio"]
        self.add_subtitle_enabled = args["-add-subtitle"]
        self.add_attachment_enabled = args["-add-attachment"]
        self.preserve_flag = args["-preserve"]
        self.replace_flag = args["-replace"]

        # Remove settings
        self.remove_enabled = args["-remove"]
        self.remove_video_enabled = args["-remove-video"]
        self.remove_audio_enabled = args["-remove-audio"]
        self.remove_subtitle_enabled = args["-remove-subtitle"]
        self.remove_attachment_enabled = args["-remove-attachment"]
        self.remove_metadata = args["-remove-metadata"]

        # Handle remove index arguments
        self.remove_video_index = args["-remove-video-index"] or args["-rvi"]
        self.remove_audio_index = args["-remove-audio-index"] or args["-rai"]
        self.remove_subtitle_index = args["-remove-subtitle-index"] or args["-rsi"]
        self.remove_attachment_index = (
            args["-remove-attachment-index"] or args["-rati"]
        )

        # Enable remove if any specific remove flag is set
        if (
            self.remove_video_enabled
            or self.remove_audio_enabled
            or self.remove_subtitle_enabled
            or self.remove_attachment_enabled
            or self.remove_metadata
            or self.remove_video_index
            or self.remove_audio_index
            or self.remove_subtitle_index
            or self.remove_attachment_index
        ):
            self.remove_enabled = True
        self.join = args["-j"]
        self.thumb = args["-t"]
        self.split_size = args["-sp"]
        self.sample_video = args["-sv"]
        self.screen_shots = args["-ss"]
        self.force_run = args["-f"]
        self.force_download = args["-fd"]
        self.force_upload = args["-fu"]
        self.convert_audio = args["-ca"]
        self.convert_video = args["-cv"]
        self.name_sub = args["-ns"]
        self.hybrid_leech = args["-hl"]
        self.thumbnail_layout = args["-tl"]
        self.as_doc = args["-doc"]
        self.as_med = args["-med"]
        self.media_tools = args["-mt"]

        # Register user as pending task user if -mt flag is used
        if self.media_tools:
            from bot.modules.media_tools import register_pending_task_user

            register_pending_task_user(user_id)
        self.metadata = args["-md"]
        self.metadata_title = args["-metadata-title"]
        self.metadata_author = args["-metadata-author"]
        self.metadata_comment = args["-metadata-comment"]
        self.metadata_all = args["-metadata-all"]
        self.metadata_video_title = args["-metadata-video-title"]
        self.metadata_video_author = args["-metadata-video-author"]
        self.metadata_video_comment = args["-metadata-video-comment"]
        self.metadata_audio_title = args["-metadata-audio-title"]
        self.metadata_audio_author = args["-metadata-audio-author"]
        self.metadata_audio_comment = args["-metadata-audio-comment"]
        self.metadata_subtitle_title = args["-metadata-subtitle-title"]
        self.metadata_subtitle_author = args["-metadata-subtitle-author"]
        self.metadata_subtitle_comment = args["-metadata-subtitle-comment"]
        self.folder_name = (
            f"/{args['-m']}".rstrip("/") if len(args["-m"]) > 0 else ""
        )
        self.bot_trans = args["-bt"]
        self.user_trans = args["-ut"]
        self.merge_video = args["-merge-video"]
        self.merge_audio = args["-merge-audio"]
        self.merge_subtitle = args["-merge-subtitle"]
        self.merge_all = args["-merge-all"]
        self.merge_image = args["-merge-image"]
        self.merge_pdf = args["-merge-pdf"]
        self.watermark_text = args["-watermark"]
        self.watermark_image = args["-iwm"]
        self.trim = args["-trim"]
        self.ffmpeg_cmds = args["-ff"]

        # Swap flags - merge command line flags with configuration
        # Command line flags enable swap functionality, but detailed config comes from database/settings
        if args["-swap"]:
            self.swap_enabled = True
        if args["-swap-audio"]:
            self.swap_audio_enabled = True
        if args["-swap-video"]:
            self.swap_video_enabled = True
        if args["-swap-subtitle"]:
            self.swap_subtitle_enabled = True

        # Enable swap if any specific swap flag is set
        if (
            self.swap_audio_enabled
            or self.swap_video_enabled
            or self.swap_subtitle_enabled
        ):
            self.swap_enabled = True

        # Compression flags
        self.compression_enabled = args["-compress"]
        self.compress_video = args["-comp-video"]
        self.compress_audio = args["-comp-audio"]
        self.compress_image = args["-comp-image"]
        self.compress_document = args["-comp-document"]
        self.compress_subtitle = args["-comp-subtitle"]
        self.compress_archive = args["-comp-archive"]

        # Enable compression if any specific compression flag is set
        if (
            self.compress_video
            or self.compress_audio
            or self.compress_image
            or self.compress_document
            or self.compress_subtitle
            or self.compress_archive
        ):
            self.compression_enabled = True

        # Compression presets
        self.video_preset = None
        if args["-video-fast"]:
            self.video_preset = "fast"
        elif args["-video-medium"]:
            self.video_preset = "medium"
        elif args["-video-slow"]:
            self.video_preset = "slow"

        self.audio_preset = None
        if args["-audio-fast"]:
            self.audio_preset = "fast"
        elif args["-audio-medium"]:
            self.audio_preset = "medium"
        elif args["-audio-slow"]:
            self.audio_preset = "slow"

        self.image_preset = None
        if args["-image-fast"]:
            self.image_preset = "fast"
        elif args["-image-medium"]:
            self.image_preset = "medium"
        elif args["-image-slow"]:
            self.image_preset = "slow"

        self.document_preset = None
        if args["-document-fast"]:
            self.document_preset = "fast"
        elif args["-document-medium"]:
            self.document_preset = "medium"
        elif args["-document-slow"]:
            self.document_preset = "slow"

        self.subtitle_preset = None
        if args["-subtitle-fast"]:
            self.subtitle_preset = "fast"
        elif args["-subtitle-medium"]:
            self.subtitle_preset = "medium"
        elif args["-subtitle-slow"]:
            self.subtitle_preset = "slow"

        self.archive_preset = None
        if args["-archive-fast"]:
            self.archive_preset = "fast"
        elif args["-archive-medium"]:
            self.archive_preset = "medium"
        elif args["-archive-slow"]:
            self.archive_preset = "slow"

        headers = args["-h"]
        if headers:
            headers = headers.split("|")
        is_bulk = args["-b"]

        bulk_start = 0
        bulk_end = 0
        ratio = None
        seed_time = None
        reply_to = None
        file_ = None
        session = TgClient.bot

        try:
            # Check if multi-link operations are enabled in the configuration
            if not Config.MULTI_LINK_ENABLED and int(args["-i"]) > 0:
                await send_message(
                    self.message,
                    "❌ Multi-link operations are disabled by the administrator.",
                )
                self.multi = 0
            else:
                self.multi = int(args["-i"])
        except Exception:
            self.multi = 0

        # Check if same directory operations are enabled in the configuration
        if not Config.SAME_DIR_ENABLED and self.folder_name:
            await send_message(
                self.message,
                "❌ Same directory operations (-m flag) are disabled by the administrator.",
            )
            self.folder_name = None

        # Check if leech is disabled but leech-related flags are used
        if not Config.LEECH_ENABLED and (
            self.hybrid_leech
            or self.bot_trans
            or self.user_trans
            or self.thumbnail_layout
            or self.split_size
            or args["-es"]
            or self.as_doc
            or self.as_med
        ):
            leech_flags_used = []
            if self.hybrid_leech:
                leech_flags_used.append("-hl")
            if self.bot_trans:
                leech_flags_used.append("-bt")
            if self.user_trans:
                leech_flags_used.append("-ut")
            if self.thumbnail_layout:
                leech_flags_used.append("-tl")
            if self.split_size:
                leech_flags_used.append("-sp")
            if args["-es"]:
                leech_flags_used.append("-es")
            if self.as_doc:
                leech_flags_used.append("-doc")
            if self.as_med:
                leech_flags_used.append("-med")

            flags_str = ", ".join(leech_flags_used)
            await send_message(
                self.message,
                f"❌ Leech operations are disabled by the administrator. Cannot use leech-related flags: {flags_str}",
            )
            # Reset leech-related flags
            self.hybrid_leech = False
            self.bot_trans = False
            self.user_trans = False
            self.thumbnail_layout = ""
            self.split_size = 0
            args["-es"] = False
            self.as_doc = False
            self.as_med = False

        # Initialize ratio and seed_time variables
        ratio = None
        seed_time = None

        # Check if torrent operations are disabled but torrent seed flag is used
        if not Config.TORRENT_ENABLED and self.seed:
            await send_message(
                self.message,
                "❌ Torrent operations are disabled by the administrator. Cannot use torrent seed flag: -d",
            )
            # Reset torrent seed flag
            self.seed = False

        try:
            if args["-ff"]:
                # Process multiple commands or presets
                if isinstance(args["-ff"], str):
                    # Check if it contains multiple presets separated by spaces
                    if " " in args["-ff"]:
                        preset_names = args["-ff"].split()
                        self.ffmpeg_cmds = []
                        for preset_name in preset_names:
                            # Look for preset in config
                            if (
                                Config.FFMPEG_CMDS
                                and preset_name in Config.FFMPEG_CMDS
                            ):
                                self.ffmpeg_cmds.append(
                                    Config.FFMPEG_CMDS[preset_name]
                                )
                                LOGGER.info(
                                    f"Added FFmpeg command from owner config: {preset_name}"
                                )
                            elif (
                                self.user_dict.get("FFMPEG_CMDS")
                                and preset_name in self.user_dict["FFMPEG_CMDS"]
                            ):
                                self.ffmpeg_cmds.append(
                                    self.user_dict["FFMPEG_CMDS"][preset_name]
                                )
                                LOGGER.info(
                                    f"Added FFmpeg command from user config: {preset_name}"
                                )
                            else:
                                # If not found as preset, treat as direct command
                                import shlex

                                self.ffmpeg_cmds.append(shlex.split(preset_name))
                                LOGGER.info(
                                    f"Added direct FFmpeg command: {preset_name}"
                                )
                    # Single preset or command
                    # Check if it's a key in the FFmpeg commands dictionary
                    elif (
                        Config.FFMPEG_CMDS and args["-ff"] in Config.FFMPEG_CMDS
                    ) or (
                        self.user_dict.get("FFMPEG_CMDS")
                        and args["-ff"] in self.user_dict["FFMPEG_CMDS"]
                    ):
                        # If it's a key in the config, get the command from the config
                        if Config.FFMPEG_CMDS and args["-ff"] in Config.FFMPEG_CMDS:
                            self.ffmpeg_cmds = [Config.FFMPEG_CMDS[args["-ff"]]]
                            LOGGER.info(
                                f"Using FFmpeg command key from owner config: {self.ffmpeg_cmds}"
                            )
                        elif (
                            self.user_dict.get("FFMPEG_CMDS")
                            and args["-ff"] in self.user_dict["FFMPEG_CMDS"]
                        ):
                            self.ffmpeg_cmds = [
                                self.user_dict["FFMPEG_CMDS"][args["-ff"]]
                            ]
                            LOGGER.info(
                                f"Using FFmpeg command key from user config: {self.ffmpeg_cmds}"
                            )
                    else:
                        # If it's not a key, treat it as a direct command
                        import shlex

                        self.ffmpeg_cmds = [shlex.split(args["-ff"])]
                        LOGGER.info(
                            f"Using direct FFmpeg command: {self.ffmpeg_cmds}"
                        )
                elif isinstance(args["-ff"], set):
                    # If it's already a set, convert to list for sequential processing
                    self.ffmpeg_cmds = list(args["-ff"])
                    LOGGER.info(f"Using FFmpeg command keys: {self.ffmpeg_cmds}")
                else:
                    # For any other type, try to evaluate it
                    # This handles cases like: ["-i mltb.mkv -c copy mltb.mkv", "-i mltb.m4a -c:a libmp3lame mltb.mp3"]
                    # or [["cmd1", "arg1"], ["cmd2", "arg2"]]
                    try:
                        evaluated_cmds = eval(args["-ff"])
                        LOGGER.info(f"Evaluated FFmpeg commands: {evaluated_cmds}")
                    except Exception as e:
                        LOGGER.error(f"Error evaluating FFmpeg commands: {e}")
                        evaluated_cmds = []

                    # Handle different formats
                    if isinstance(evaluated_cmds, list):
                        # Check if it's a list of strings or a list of lists
                        if all(isinstance(item, str) for item in evaluated_cmds):
                            # List of command strings
                            import shlex

                            self.ffmpeg_cmds = [
                                shlex.split(cmd) for cmd in evaluated_cmds
                            ]
                        elif all(isinstance(item, list) for item in evaluated_cmds):
                            # List of command lists
                            self.ffmpeg_cmds = evaluated_cmds
                        else:
                            # Mixed list - try to handle each item appropriately
                            self.ffmpeg_cmds = []
                            for item in evaluated_cmds:
                                if isinstance(item, str):
                                    import shlex

                                    self.ffmpeg_cmds.append(shlex.split(item))
                                elif isinstance(item, list):
                                    self.ffmpeg_cmds.append(item)
                                else:
                                    # Try to convert to string and split
                                    import shlex

                                    self.ffmpeg_cmds.append(shlex.split(str(item)))
                    else:
                        # Single command
                        import shlex

                        self.ffmpeg_cmds = [shlex.split(str(evaluated_cmds))]

                    LOGGER.info(
                        f"Using evaluated FFmpeg commands: {self.ffmpeg_cmds}"
                    )
        except Exception as e:
            self.ffmpeg_cmds = None
            LOGGER.error(f"Error processing FFmpeg command: {e}")
        if not isinstance(self.seed, bool):
            dargs = self.seed.split(":")
            ratio = dargs[0] or None
            if len(dargs) == 2:
                seed_time = dargs[1] or None
            self.seed = True

        if not isinstance(is_bulk, bool):
            dargs = is_bulk.split(":")
            bulk_start = dargs[0] or 0
            if len(dargs) == 2:
                bulk_end = dargs[1] or 0
            is_bulk = True

        # Check if bulk operations are enabled in the configuration
        if is_bulk and not Config.BULK_ENABLED:
            await send_message(
                self.message, "❌ Bulk operations are disabled by the administrator."
            )
            is_bulk = False

        if not is_bulk:
            if self.multi > 0:
                if self.folder_name:
                    async with task_dict_lock:
                        if self.folder_name in self.same_dir:
                            self.same_dir[self.folder_name]["tasks"].add(self.mid)
                            for fd_name in self.same_dir:
                                if fd_name != self.folder_name:
                                    self.same_dir[fd_name]["total"] -= 1
                        elif self.same_dir:
                            self.same_dir[self.folder_name] = {
                                "total": self.multi,
                                "tasks": {self.mid},
                            }
                            for fd_name in self.same_dir:
                                if fd_name != self.folder_name:
                                    self.same_dir[fd_name]["total"] -= 1
                        else:
                            self.same_dir = {
                                self.folder_name: {
                                    "total": self.multi,
                                    "tasks": {self.mid},
                                },
                            }
                elif self.same_dir:
                    async with task_dict_lock:
                        for fd_name in self.same_dir:
                            self.same_dir[fd_name]["total"] -= 1
        else:
            await self.init_bulk(input_list, bulk_start, bulk_end, Mirror)
            return None

        if len(self.bulk) != 0:
            del self.bulk[0]

        await self.run_multi(input_list, Mirror)

        await self.get_tag(text)

        path = f"{DOWNLOAD_DIR}{self.mid}{self.folder_name}"

        if (
            not self.link
            and (reply_to := self.message.reply_to_message)
            and reply_to.text
        ):
            self.link = reply_to.text.split("\n", 1)[0].strip()
        if is_telegram_link(self.link):
            try:
                reply_to, session = await get_tg_link_message(self.link, user_id)
            except Exception as e:
                # Convert exception to string to avoid TypeError in send_message
                error_msg = (
                    f"ERROR: {e!s}"
                    if e
                    else "ERROR: Failed to process Telegram link"
                )
                x = await send_message(self.message, error_msg)
                await self.remove_from_same_dir()
                await delete_links(self.message)
                return await auto_delete_message(x, time=300)

        if isinstance(reply_to, list):
            self.bulk = reply_to
            b_msg = input_list[:1]
            self.options = " ".join(input_list[1:])
            b_msg.append(f"{self.bulk[0]} -i {len(self.bulk)} {self.options}")
            nextmsg = await send_message(self.message, " ".join(b_msg))
            nextmsg = await self.client.get_messages(
                chat_id=self.message.chat.id,
                message_ids=nextmsg.id,
            )
            if self.message.from_user:
                nextmsg.from_user = self.user
            else:
                nextmsg.sender_chat = self.user
            await Mirror(
                self.client,
                nextmsg,
                self.is_qbit,
                self.is_leech,
                self.is_jd,
                self.is_nzb,
                self.same_dir,
                self.bulk,
                self.multi_tag,
                self.options,
            ).new_event()
            return await delete_links(self.message)

        if reply_to:
            file_ = (
                reply_to.document
                or reply_to.photo
                or reply_to.video
                or reply_to.audio
                or reply_to.voice
                or reply_to.video_note
                or reply_to.sticker
                or reply_to.animation
                or None
            )

            if file_ is None:
                if reply_text := reply_to.text:
                    self.link = reply_text.split("\n", 1)[0].strip()
                else:
                    reply_to = None
            elif reply_to.document and (
                file_.mime_type == "application/x-bittorrent"
                or file_.file_name.endswith((".torrent", ".dlc", ".nzb"))
            ):
                self.link = await reply_to.download()
                file_ = None

        try:
            if (
                self.link
                and (is_magnet(self.link) or self.link.endswith(".torrent"))
            ) or (
                file_ and file_.file_name and file_.file_name.endswith(".torrent")
            ):
                # Check if torrent operations are enabled
                if not Config.TORRENT_ENABLED:
                    await self.on_download_error(
                        "❌ Torrent operations are disabled by the administrator."
                    )
                    return None
                self.is_qbit = True
        except Exception:
            pass

        if (
            (not self.link and file_ is None)
            or (is_telegram_link(self.link) and reply_to is None)
            or (
                file_ is None
                and not is_url(self.link)
                and not is_magnet(self.link)
                and not await aiopath.exists(self.link)
                and not is_rclone_path(self.link)
                and not is_gdrive_id(self.link)
                and not is_gdrive_link(self.link)
                and not is_mega_link(self.link)
                and not (
                    Config.STREAMRIP_ENABLED and await is_streamrip_url(self.link)
                )
            )
        ):
            x = await send_message(
                self.message,
                COMMAND_USAGE["mirror"][0],
                COMMAND_USAGE["mirror"][1],
            )
            await self.remove_from_same_dir()
            await delete_links(self.message)
            return await auto_delete_message(x, time=300)

        # Mega links are now supported natively, no need to force JDownloader

        # Check if media tools flag is set
        if self.media_tools:
            # Show media tools settings and wait for user to click Done or timeout
            proceed = await show_media_tools_for_task(
                self.client, self.message, self
            )
            if not proceed:
                # User cancelled or timeout occurred
                await self.remove_from_same_dir()
                await delete_links(self.message)
                return None
        else:
            # Check if user has a direct result stored (fallback for race condition)
            from bot.modules.media_tools import direct_task_results

            if user_id in direct_task_results:
                result = direct_task_results[user_id]
                del direct_task_results[user_id]
                if not result:
                    # User clicked Cancel
                    await self.remove_from_same_dir()
                    await delete_links(self.message)
                    return None
                # If result is True, continue with the task

        try:
            await self.before_start()
        except Exception as e:
            # Convert exception to string to avoid TypeError in send_message
            error_msg = (
                str(e) if e else "An unknown error occurred during initialization"
            )
            x = await send_message(self.message, error_msg)
            await self.remove_from_same_dir()
            await delete_links(self.message)
            return await auto_delete_message(x, time=300)

        # Get file size for limit checking
        size = 0
        if file_:
            size = file_.file_size

        # Check limits before proceeding
        if size > 0:
            limit_msg = await limit_checker(
                size,
                self,
                isTorrent=self.is_qbit
                or is_magnet(self.link)
                or (self.link and self.link.endswith(".torrent")),
                isMega=is_mega_link(self.link),
                isDriveLink=is_gdrive_link(self.link) or is_gdrive_id(self.link),
                isYtdlp=False,
            )
            if limit_msg:
                # limit_msg is already a tuple with (message_object, error_message)
                # and the message has already been sent with the tag
                await self.remove_from_same_dir()
                await delete_links(self.message)
                return None

        if (
            not self.is_jd
            and not self.is_qbit
            and not self.is_nzb
            and not is_magnet(self.link)
            and not is_rclone_path(self.link)
            and not is_gdrive_link(self.link)
            and not self.link.endswith(".torrent")
            and file_ is None
            and not is_gdrive_id(self.link)
            and not is_mega_link(self.link)
        ):
            content_type = await get_content_type(self.link)
            if content_type is None or re_match(
                r"text/html|text/plain",
                content_type,
            ):
                try:
                    self.link = await sync_to_async(
                        direct_link_generator, self.link, self.user_id
                    )
                    if isinstance(self.link, tuple):
                        self.link, headers = self.link
                    elif isinstance(self.link, str):
                        LOGGER.info(f"Generated link: {self.link}")
                except DirectDownloadLinkException as e:
                    e = str(e)
                    if "This link requires a password!" not in e:
                        # Improve error messaging for unsupported sites
                        if "No Direct link function found" in e:
                            LOGGER.info(
                                f"No direct link function found for {self.link}. Trying alternative download methods."
                            )
                        elif "ERROR: Invalid URL" in e:
                            LOGGER.warning(f"Invalid URL format: {self.link}")
                        else:
                            LOGGER.info(e)

                    if e.startswith("ERROR:"):
                        # Handle specific error types with better user messages
                        if "Resource not found" in e or "File not found" in e:
                            error_msg = (
                                "❌ File not found\n\n"
                                "The file you're trying to download is no longer available or has been removed. "
                                "Please check if the link is still valid."
                            )
                        elif "Download limit reached" in e or "limit" in e.lower():
                            error_msg = (
                                "❌ Download limit reached\n\n"
                                "The file hosting service has reached its download limit. "
                                "Please try again later or use a different link."
                            )
                        elif "password" in e.lower():
                            error_msg = (
                                "❌ Password required\n\n"
                                "This file requires a password. Please provide the password in the format:\n"
                                "<code>your_link::password</code>"
                            )
                        else:
                            error_msg = e

                        x = await send_message(self.message, error_msg)
                        await self.remove_from_same_dir()
                        await delete_links(self.message)
                        return await auto_delete_message(x, time=300)
                except Exception as e:
                    # Convert exception to string to avoid TypeError in send_message
                    error_msg = (
                        str(e)
                        if e
                        else "An unknown error occurred during link processing"
                    )
                    x = await send_message(self.message, error_msg)
                    await self.remove_from_same_dir()
                    await delete_links(self.message)
                    return await auto_delete_message(x, time=300)
            content_type = await get_content_type(self.link)  # recheck with new link
            if content_type and "x-bittorrent" in content_type:
                self.is_qbit = True

        if file_ is not None:
            create_task(
                TelegramDownloadHelper(self).add_download(
                    reply_to,
                    f"{path}/",
                    session,
                ),
            )
        elif isinstance(self.link, dict):
            create_task(add_direct_download(self, path))
        elif self.is_jd:
            create_task(add_jd_download(self, path))
        elif self.is_qbit:
            create_task(add_qb_torrent(self, path, ratio, seed_time))
        elif self.is_nzb:
            create_task(add_nzb(self, path))
        elif is_rclone_path(self.link):
            # Check if Rclone operations are enabled in the configuration
            if not Config.RCLONE_ENABLED:
                await self.on_download_error(
                    "❌ Rclone operations are disabled by the administrator."
                )
                return None
            create_task(add_rclone_download(self, f"{path}/"))
        elif is_gdrive_link(self.link) or is_gdrive_id(self.link):
            create_task(add_gd_download(self, path))
        elif is_mega_link(self.link):
            # MEGA downloads - megaclone functionality removed, use /mirror mega-link instead
            create_task(add_mega_download(self, path))
        elif Config.STREAMRIP_ENABLED and await is_streamrip_url(self.link):
            # Handle streamrip downloads with quality selection
            await self._handle_streamrip_download()

        elif Config.ZOTIFY_ENABLED and await is_zotify_url(self.link):
            # Handle zotify downloads
            create_task(add_zotify_download(self, self.link))
        else:
            ussr = args["-au"]
            pssw = args["-ap"]
            if ussr or pssw:
                auth = f"{ussr}:{pssw}"
                headers.extend(
                    [
                        f"authorization: Basic {b64encode(auth.encode()).decode('ascii')}"
                    ]
                )
            create_task(add_aria2_download(self, path, headers, ratio, seed_time))
        await delete_links(self.message)
        return None

    async def _handle_streamrip_download(self):
        """Handle streamrip downloads with quality selection"""
        from bot.helper.mirror_leech_utils.streamrip_utils.quality_selector import (
            show_quality_selector,
        )
        from bot.helper.mirror_leech_utils.streamrip_utils.url_parser import (
            parse_streamrip_url,
        )

        try:
            # Parse URL to get platform and media info
            parsed = await parse_streamrip_url(self.link)
            if not parsed:
                await self.on_download_error("❌ Failed to parse streamrip URL!")
                return

            platform, media_type, _ = parsed

            # Set platform and media_type attributes for quality selector
            self.platform = platform
            self.media_type = media_type

            # Show quality selector
            selection = await show_quality_selector(self, platform, media_type)

            if not selection:
                # User cancelled or timeout
                await self.remove_from_same_dir()
                return

            quality = selection["quality"]
            codec = selection["codec"]

            # Start streamrip download with selected quality and codec
            create_task(
                add_streamrip_download(self, self.link, quality, codec, False)
            )

        except Exception as e:
            LOGGER.error(f"Error in streamrip download handling: {e}")
            await self.on_download_error(f"❌ Streamrip download error: {e}")


async def mirror(client, message):
    # Check if any upload service is available
    if not (
        Config.GDRIVE_UPLOAD_ENABLED
        or Config.RCLONE_ENABLED
        or Config.YOUTUBE_UPLOAD_ENABLED
        or Config.DDL_ENABLED
        or (Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED)
    ):
        await send_message(
            message, "❌ All upload services are disabled by the administrator."
        )
        return
    bot_loop.create_task(Mirror(client, message).new_event())


async def leech(client, message):
    # Check if leech operations are enabled in the configuration
    if not Config.LEECH_ENABLED:
        await send_message(
            message, "❌ Leech operations are disabled by the administrator."
        )
        return
    bot_loop.create_task(Mirror(client, message, is_leech=True).new_event())


async def jd_mirror(client, message):
    # Check if any upload service is available
    if not (
        Config.GDRIVE_UPLOAD_ENABLED
        or Config.RCLONE_ENABLED
        or Config.YOUTUBE_UPLOAD_ENABLED
        or Config.DDL_ENABLED
        or (Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED)
    ):
        await send_message(
            message, "❌ All upload services are disabled by the administrator."
        )
        return
    # Check if JDownloader operations are enabled in the configuration
    if not Config.JD_ENABLED:
        await send_message(
            message, "❌ JDownloader operations are disabled by the administrator."
        )
        return
    bot_loop.create_task(Mirror(client, message, is_jd=True).new_event())


async def nzb_mirror(client, message):
    # Check if any upload service is available
    if not (
        Config.GDRIVE_UPLOAD_ENABLED
        or Config.RCLONE_ENABLED
        or Config.YOUTUBE_UPLOAD_ENABLED
        or Config.DDL_ENABLED
        or (Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED)
    ):
        await send_message(
            message, "❌ All upload services are disabled by the administrator."
        )
        return
    # Check if NZB operations are enabled in the configuration
    if not Config.NZB_ENABLED:
        await send_message(
            message, "❌ NZB operations are disabled by the administrator."
        )
        return
    bot_loop.create_task(Mirror(client, message, is_nzb=True).new_event())


async def jd_leech(client, message):
    # Check if leech operations are enabled in the configuration
    if not Config.LEECH_ENABLED:
        await send_message(
            message, "❌ Leech operations are disabled by the administrator."
        )
        return
    # Check if JDownloader operations are enabled in the configuration
    if not Config.JD_ENABLED:
        await send_message(
            message, "❌ JDownloader operations are disabled by the administrator."
        )
        return
    bot_loop.create_task(
        Mirror(client, message, is_leech=True, is_jd=True).new_event(),
    )


async def nzb_leech(client, message):
    # Check if leech operations are enabled in the configuration
    if not Config.LEECH_ENABLED:
        await send_message(
            message, "❌ Leech operations are disabled by the administrator."
        )
        return
    # Check if NZB operations are enabled in the configuration
    if not Config.NZB_ENABLED:
        await send_message(
            message, "❌ NZB operations are disabled by the administrator."
        )
        return
    bot_loop.create_task(
        Mirror(client, message, is_leech=True, is_nzb=True).new_event(),
    )
