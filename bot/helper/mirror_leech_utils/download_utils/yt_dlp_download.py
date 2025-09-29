# ruff: noqa: ARG005, B023
import contextlib
from asyncio import create_task
from logging import getLogger
from os import listdir
from os import path as ospath
from re import search as re_search
from secrets import token_hex

from yt_dlp import DownloadError, YoutubeDL

from bot import task_dict, task_dict_lock
from bot.helper.ext_utils.bot_utils import async_to_sync, sync_to_async
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
)

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.mirror_leech_utils.status_utils.yt_dlp_status import YtDlpStatus
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
    send_status_message,
)

LOGGER = getLogger(__name__)


class MyLogger:
    def __init__(self, obj, listener):
        self._obj = obj
        self._listener = listener

    def debug(self, msg):
        if not self._obj.is_playlist and (
            match := re_search(
                r".Merger..Merging formats into..(.*?).$",
                msg,
            )
            or re_search(r".ExtractAudio..Destination..(.*?)$", msg)
        ):
            LOGGER.info(msg)
            newname = match.group(1)
            newname = newname.rsplit("/", 1)[-1]
            self._listener.name = newname

    @staticmethod
    def warning(msg):
        LOGGER.warning(msg)

    @staticmethod
    def error(msg):
        if msg != "ERROR: Cancelling...":
            LOGGER.error(msg)


class YoutubeDLHelper:
    def __init__(self, listener):
        self._last_downloaded = 0
        self._progress = 0
        self._downloaded_bytes = 0
        self._download_speed = 0
        self._eta = "-"
        self._listener = listener
        self._gid = ""
        self._ext = ""
        self.is_playlist = False

        # Initialize with default cookies, will be updated in async_init
        self.user_cookies_list = []
        self.current_cookie_index = -1

        self.opts = {
            "progress_hooks": [self._on_download_progress],
            "logger": MyLogger(self, self._listener),
            "usenetrc": True,
            "cookiefile": "cookies.txt",
            "allow_multiple_video_streams": True,
            "allow_multiple_audio_streams": True,
            "noprogress": True,
            "allow_playlist_files": True,
            "overwrites": True,
            "writethumbnail": True,
            "trim_file_name": 220,
            "ffmpeg_location": "/bin/xtra",
            "fragment_retries": 10,
            "retries": 10,
            "retry_sleep_functions": {
                "http": lambda n: 3,
                "fragment": lambda n: 3,
                "file_access": lambda n: 3,
                "extractor": lambda n: 3,
            },
        }

    async def async_init(self):
        """Async initialization for cookie setup"""
        # Check for user-specific cookies (multiple cookies support)
        user_id = self._listener.user_id
        self.user_cookies_list = await self._get_user_cookies_list(user_id)

        # Use first available cookie or default
        if self.user_cookies_list:
            cookies_file = self.user_cookies_list[0]
            self.current_cookie_index = 0
        else:
            cookies_file = "cookies.txt"
            self.current_cookie_index = -1

        # Update the cookiefile in opts
        self.opts["cookiefile"] = cookies_file

        # Log which cookies file is being used
        if self.user_cookies_list:
            cookie_num = (
                ospath.basename(cookies_file)
                .replace(f"{user_id}_", "")
                .replace(".txt", "")
            )
            LOGGER.info(
                f"Using user cookie #{cookie_num} for user ID: {user_id} (Total: {len(self.user_cookies_list)} cookies)"
            )
        else:
            LOGGER.info("Using default cookies.txt file")

    async def _get_user_cookies_list(self, user_id):
        """Get list of all cookie files for a user (from both database and filesystem)"""
        cookies_list = []

        # First, try to get cookies from database and create temporary files
        try:
            from bot.helper.ext_utils.db_handler import database

            # Get cookies from database - properly await the coroutine
            db_cookies = await database.get_user_cookies(user_id)

            for cookie in db_cookies:
                cookie_num = cookie["number"]
                cookie_data = cookie["data"]

                # Create temporary file for this cookie
                temp_cookie_path = f"cookies/{user_id}_{cookie_num}.txt"

                # Ensure cookies directory exists
                import os

                os.makedirs("cookies", exist_ok=True)

                # Write cookie data to temporary file if it doesn't exist
                if not ospath.exists(temp_cookie_path):
                    try:
                        with open(temp_cookie_path, "wb") as f:
                            f.write(cookie_data)
                        LOGGER.info(
                            f"Created temporary cookie file #{cookie_num} for user {user_id}"
                        )
                    except Exception as e:
                        LOGGER.error(
                            f"Error creating temporary cookie file #{cookie_num}: {e}"
                        )
                        continue

                cookies_list.append(temp_cookie_path)

        except Exception as e:
            LOGGER.error(
                f"Error getting cookies from database for user {user_id}: {e}"
            )

        # Also check for existing files in filesystem
        cookies_dir = "cookies/"
        if ospath.exists(cookies_dir):
            try:
                import os

                for filename in os.listdir(cookies_dir):
                    if filename.startswith(f"{user_id}_") and filename.endswith(
                        ".txt"
                    ):
                        filepath = f"{cookies_dir}{filename}"
                        if ospath.exists(filepath) and filepath not in cookies_list:
                            cookies_list.append(filepath)
            except Exception as e:
                LOGGER.error(f"Error getting user cookies from filesystem: {e}")

        # Sort by cookie number
        try:
            cookies_list.sort(
                key=lambda x: int(
                    ospath.basename(x).replace(f"{user_id}_", "").replace(".txt", "")
                )
                if ospath.basename(x)
                .replace(f"{user_id}_", "")
                .replace(".txt", "")
                .isdigit()
                else 999
            )
        except Exception as e:
            LOGGER.error(f"Error sorting cookies list: {e}")

        return cookies_list

    def _try_next_cookie(self):
        """Try the next available cookie for the user"""
        if (
            not self.user_cookies_list
            or self.current_cookie_index >= len(self.user_cookies_list) - 1
        ):
            return False

        self.current_cookie_index += 1
        new_cookie = self.user_cookies_list[self.current_cookie_index]

        # Update the cookiefile in opts
        self.opts["cookiefile"] = new_cookie

        cookie_num = (
            ospath.basename(new_cookie)
            .replace(f"{self._listener.user_id}_", "")
            .replace(".txt", "")
        )
        LOGGER.info(
            f"Trying next cookie #{cookie_num} for user ID: {self._listener.user_id}"
        )

        return True

    def _should_try_next_cookie(self, error_str):
        """Check if the error indicates we should try the next cookie"""
        cookie_related_errors = [
            "sign in to confirm",
            "this video is unavailable",
            "private video",
            "members-only content",
            "requires authentication",
            "login required",
            "access denied",
            "forbidden",
            "unauthorized",
            "premium content",
            "subscription required",
            "age-restricted",
            "not available in your country",
            "geo-blocked",
            "region blocked",
            "unable to extract video data",
            "video unavailable",
            "cookies",
            "authentication",
            "401",
            "403",
        ]

        error_lower = error_str.lower()
        return any(
            error_phrase in error_lower for error_phrase in cookie_related_errors
        )

    @property
    def download_speed(self):
        return self._download_speed

    @property
    def downloaded_bytes(self):
        return self._downloaded_bytes

    @property
    def size(self):
        return self._listener.size

    @property
    def progress(self):
        return self._progress

    @property
    def eta(self):
        return self._eta

    def _on_download_progress(self, d):
        if self._listener.is_cancelled:
            raise ValueError("Cancelling...")
        if d["status"] == "finished":
            if self.is_playlist:
                self._last_downloaded = 0
        elif d["status"] == "downloading":
            self._download_speed = d["speed"] or 0
            if self.is_playlist:
                downloadedBytes = d["downloaded_bytes"] or 0
                chunk_size = downloadedBytes - self._last_downloaded
                self._last_downloaded = downloadedBytes
                self._downloaded_bytes += chunk_size
            else:
                if d.get("total_bytes"):
                    self._listener.size = d["total_bytes"] or 0
                elif d.get("total_bytes_estimate"):
                    self._listener.size = d["total_bytes_estimate"] or 0
                self._downloaded_bytes = d["downloaded_bytes"] or 0
                self._eta = d.get("eta", "-") or "-"
            with contextlib.suppress(Exception):
                self._progress = (self._downloaded_bytes / self._listener.size) * 100

    async def _on_download_start(self, from_queue=False):
        async with task_dict_lock:
            task_dict[self._listener.mid] = YtDlpStatus(
                self._listener,
                self,
                self._gid,
            )
        if not from_queue:
            await self._listener.on_download_start()
            if self._listener.multi <= 1:
                await send_status_message(self._listener.message)

    def _on_download_error(self, error):
        self._listener.is_cancelled = True
        try:
            async_to_sync(self._listener.on_download_error, error)
        except Exception as e:
            LOGGER.error(f"Failed to handle error through listener: {e!s}")
            # Fallback error handling
            error_msg = async_to_sync(
                send_message,
                self._listener.message,
                f"{self._listener.tag} Download: {error}",
            )
            create_task(auto_delete_message(error_msg, time=300))  # noqa: RUF006

    def _extract_meta_data(self):
        # Configure external downloader for specific protocols (keep existing functionality)
        if self._listener.link.startswith(("rtmp", "mms", "rstp", "rtmps")):
            self.opts["external_downloader"] = "xtra"

        with YoutubeDL(self.opts) as ydl:
            try:
                result = ydl.extract_info(self._listener.link, download=False)
                if result is None:
                    raise ValueError("Info result is None")

            except Exception as e:
                return self._on_download_error(str(e))
            if "entries" in result:
                for entry in result["entries"]:
                    if not entry:
                        continue
                    if "filesize_approx" in entry:
                        self._listener.size += entry.get("filesize_approx", 0) or 0
                    elif "filesize" in entry:
                        self._listener.size += entry.get("filesize", 0) or 0
                    if not self._listener.name:
                        outtmpl_ = "%(series,playlist_title,channel)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d.%(ext)s"
                        self._listener.name, ext = ospath.splitext(
                            ydl.prepare_filename(entry, outtmpl=outtmpl_),
                        )
                        if not self._ext:
                            self._ext = ext
                return None

            outtmpl_ = "%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s"
            realName = ydl.prepare_filename(result, outtmpl=outtmpl_)
            ext = ospath.splitext(realName)[-1]
            self._listener.name = (
                f"{self._listener.name}{ext}" if self._listener.name else realName
            )
            if not self._ext:
                self._ext = ext
                return None
            return None

    def _download(self, path):
        try:
            with YoutubeDL(self.opts) as ydl:
                try:
                    ydl.download([self._listener.link])
                except DownloadError as e:
                    if not self._listener.is_cancelled:
                        self._on_download_error(str(e))
                    return

            # Check if download was successful
            if self.is_playlist and (
                not ospath.exists(path) or len(listdir(path)) == 0
            ):
                self._on_download_error(
                    "No video available to download from this playlist. Check logs for more details",
                )
                return
            if self._listener.is_cancelled:
                return
            async_to_sync(self._listener.on_download_complete)
        except Exception:
            pass
        return

    async def add_download(self, path, qual, playlist, options):
        # Initialize async components first
        await self.async_init()

        if playlist:
            self.opts["ignoreerrors"] = True
            self.is_playlist = True

        self._gid = token_hex(4)

        await self._on_download_start()

        self.opts["postprocessors"] = [
            {
                "add_chapters": True,
                "add_infojson": "if_exists",
                "add_metadata": True,
                "key": "FFmpegMetadata",
            },
        ]

        # Handle specific audio format with quality
        if qual.startswith("ba/b-"):
            audio_info = qual.split("-")
            qual = audio_info[0]
            audio_format = audio_info[1]
            rate = audio_info[2]
            self.opts["postprocessors"].append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": rate,
                },
            )
            if audio_format == "vorbis":
                self._ext = ".ogg"
            elif audio_format == "alac":
                self._ext = ".m4a"
            else:
                self._ext = f".{audio_format}"
        # Handle bestaudio format - ensure it's audio only
        elif qual == "bestaudio":
            # Modify format to ensure audio-only download
            qual = "bestaudio[vcodec=none]"
            # Default to mp3 format for consistency
            self.opts["postprocessors"].append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
            )
            self._ext = ".mp3"

            # Downloading audio-only format (MP3)

            # Add audio format to the filename for clarity
            if self._listener.name and not self._listener.name.endswith(self._ext):
                if "." in self._listener.name:
                    base_name = self._listener.name.rsplit(".", 1)[0]
                    self._listener.name = f"{base_name} (Audio){self._ext}"
                else:
                    self._listener.name = f"{self._listener.name} (Audio){self._ext}"

        if options:
            self._set_options(options)

        self.opts["format"] = qual

        await sync_to_async(self._extract_meta_data)
        if self._listener.is_cancelled:
            return

        base_name, ext = ospath.splitext(self._listener.name)
        trim_name = self._listener.name if self.is_playlist else base_name
        if len(trim_name.encode()) > 200:
            self._listener.name = (
                self._listener.name[:200]
                if self.is_playlist
                else f"{base_name[:200]}{ext}"
            )
            base_name = ospath.splitext(self._listener.name)[0]

        if self.is_playlist:
            self.opts["outtmpl"] = {
                "default": f"{path}/{self._listener.name}/%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s",
                "thumbnail": f"{path}/yt-dlp-thumb/%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s",
            }
        elif "download_ranges" in options:
            self.opts["outtmpl"] = {
                "default": f"{path}/{base_name}/%(section_number|)s%(section_number&.|)s%(section_title|)s%(section_title&-|)s%(title,fulltitle,alt_title)s %(section_start)s to %(section_end)s.%(ext)s",
                "thumbnail": f"{path}/yt-dlp-thumb/%(section_number|)s%(section_number&.|)s%(section_title|)s%(section_title&-|)s%(title,fulltitle,alt_title)s %(section_start)s to %(section_end)s.%(ext)s",
            }
        elif any(
            key in options
            for key in [
                "writedescription",
                "writeinfojson",
                "writeannotations",
                "writedesktoplink",
                "writewebloclink",
                "writeurllink",
                "writesubtitles",
                "writeautomaticsub",
            ]
        ):
            self.opts["outtmpl"] = {
                "default": f"{path}/{base_name}/{self._listener.name}",
                "thumbnail": f"{path}/yt-dlp-thumb/{base_name}.%(ext)s",
            }
        else:
            self.opts["outtmpl"] = {
                "default": f"{path}/{self._listener.name}",
                "thumbnail": f"{path}/yt-dlp-thumb/{base_name}.%(ext)s",
            }

        # Set proper filename for audio formats
        if qual.startswith("ba/b") or qual in {
            "bestaudio",
            "bestaudio[vcodec=none]",
        }:
            self._listener.name = f"{base_name}{self._ext}"

        if self._listener.is_leech and not self._listener.thumbnail_layout:
            self.opts["postprocessors"].append(
                {
                    "format": "jpg",
                    "key": "FFmpegThumbnailsConvertor",
                    "when": "before_dl",
                },
            )
        if self._ext in [
            ".mp3",
            ".mkv",
            ".mka",
            ".ogg",
            ".opus",
            ".flac",
            ".m4a",
            ".mp4",
            ".mov",
            ".m4v",
        ]:
            self.opts["postprocessors"].append(
                {
                    "already_have_thumbnail": bool(
                        self._listener.is_leech
                        and not self._listener.thumbnail_layout,
                    ),
                    "key": "EmbedThumbnail",
                },
            )
        elif not self._listener.is_leech:
            self.opts["writethumbnail"] = False

        # Check size limits if size is available
        if self._listener.size > 0:
            limit_msg = await limit_checker(
                self._listener.size,
                self._listener,
                isYtdlp=True,
                isPlayList=self.is_playlist,
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
            LOGGER.info(f"Added to Queue/Download: {self._listener.name}")
            async with task_dict_lock:
                task_dict[self._listener.mid] = QueueStatus(
                    self._listener,
                    self._gid,
                    "dl",
                )
            await event.wait()
            if self._listener.is_cancelled:
                return
            LOGGER.info(f"Start Queued Download from YT_DLP: {self._listener.name}")
            await self._on_download_start(True)

        if not add_to_queue:
            LOGGER.info(f"Download with YT_DLP: {self._listener.name}")

        await sync_to_async(self._download, path)

    async def cancel_task(self):
        self._listener.is_cancelled = True
        LOGGER.info(f"Cancelling Download: {self._listener.name}")
        await self._listener.on_download_error("Stopped by User!")

    def _set_options(self, options):
        for key, value in options.items():
            if key == "postprocessors":
                if isinstance(value, list):
                    self.opts[key].extend(tuple(value))
                elif isinstance(value, dict):
                    self.opts[key].append(value)
            elif key == "download_ranges":
                if isinstance(value, list):
                    self.opts[key] = lambda info, ytdl: value
            else:
                self.opts[key] = value
