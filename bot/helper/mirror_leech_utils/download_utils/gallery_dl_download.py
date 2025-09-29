"""
Gallery-dl download helper
Following the pattern of yt_dlp_download.py
"""

import asyncio
import os
from time import time
from typing import Any

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.files_utils import get_path_size
from bot.helper.mirror_leech_utils.gallery_dl_utils.auth_manager import (
    GalleryDLAuthManager,
)
from bot.helper.mirror_leech_utils.gallery_dl_utils.post_processor import (
    GalleryDLPostProcessor,
)
from bot.helper.mirror_leech_utils.status_utils.gallery_dl_status import (
    GalleryDLStatus,
)

try:
    import gallery_dl
except ImportError:
    gallery_dl = None
    LOGGER.error("gallery-dl not installed. Install with: pip install gallery-dl")


class GalleryDLHelper:
    """Gallery-dl download helper following YoutubeDLHelper pattern"""

    def __init__(self, listener):
        self.listener = listener
        self.listener.tool = "gallery-dl"  # Set tool for limit checking
        self._last_downloaded = 0
        self._count = 0
        self._size = 0
        self._start_time = time()
        self._is_cancelled = False
        self._downloading = False
        self._download_path = ""
        self._archive_path = ""
        self._config = {}
        self._job = None

        # Initialize advanced components
        self.auth_manager = GalleryDLAuthManager()
        self.post_processor = GalleryDLPostProcessor(listener.dir, listener)
        self.platform = getattr(listener, "platform", "unknown")
        self._quality_config = {}

    def _get_filename_template(self):
        """Get smart filename template based on platform capabilities (no IDs in filenames)"""
        # Platform-specific filename templates based on actual capabilities from log.txt
        # Focused on meaningful content without exposing IDs
        platform_templates = {
            # Social Media Platforms - using ID + meaningful identifiers
            "twitter": "{user[name]}_{id}_{filename}.{extension}",  # Timelines, Tweets, User Profiles
            "instagram": "{user[username]}_{id}_{filename}.{extension}",  # Posts, Stories, User Profiles
            "reddit": "{subreddit}_{id}_{filename}.{extension}",  # Submissions, Subreddits, User Profiles
            "tumblr": "{user[name]}_{id}_{filename}.{extension}",  # Posts, User Profiles
            "facebook": "{user[name]}_{id}_{filename}.{extension}",  # Posts, User Profiles
            "youtube": "{id}_{title}_{filename}.{extension}",  # Videos, Playlists
            "tiktok": "{user[username]}_{id}_{filename}.{extension}",  # Videos, User Profiles
            # Art & Photography Platforms - using ID + meaningful identifiers
            "pixiv": "{user[name]}_{id}_{title}_{filename}.{extension}",  # Artworks, User Profiles, individual Images
            "artstation": "{user[username]}_{id}_{title}_{filename}.{extension}",  # Artwork Listings, User Profiles, individual Images
            "deviantart": "{author[username]}_{id}_{title}_{filename}.{extension}",  # Deviations, Galleries, User Profiles
            "500px": "{user[username]}_{id}_{name}_{filename}.{extension}",  # individual Images, User Profiles, Galleries
            "flickr": "{user[username]}_{id}_{title}_{filename}.{extension}",  # Albums, individual Images, User Profiles
            "unsplash": "{user[username]}_{id}_{description}_{filename}.{extension}",  # individual Images, Search Results
            "behance": "{user[username]}_{id}_{title}_{filename}.{extension}",  # Projects, User Profiles
            "pinterest": "{user[username]}_{id}_{description}_{filename}.{extension}",  # Pins, Boards, User Profiles
            # Image Hosting & Sharing
            "imgur": "{title}.{extension}",  # Albums, individual Images, Galleries
            "catbox": "{filename}.{extension}",  # Direct file hosting
            "gofile": "{filename}.{extension}",  # File sharing
            "postimg": "{filename}.{extension}",  # Image hosting
            "turboimagehost": "{filename}.{extension}",  # Image hosting
            "acidimg": "{filename}.{extension}",  # Image hosting
            # Booru Sites (SFW) - using ID + filename for meaningful names
            "danbooru": "{id}_{filename}.{extension}",  # Posts, Tag Searches, Pools
            "safebooru": "{id}_{filename}.{extension}",  # Posts, Tag Searches, Pools
            "gelbooru": "{id}_{filename}.{extension}",  # Posts, Tag Searches, Pools
            "twibooru": "{id}_{filename}.{extension}",  # Posts, Tag Searches
            "zerochan": "{id}_{filename}.{extension}",  # Posts, Tag Searches
            # Manga/Comics Platforms
            "dynastyscans": "{title}_{chapter}.{extension}",  # Chapters, Series
            "batoto": "{title}_{chapter}.{extension}",  # Manga chapters
            "mangadex": "{title}_{chapter}.{extension}",  # Manga, Chapters
            "tcbscans": "{title}_{chapter}.{extension}",  # Manga chapters
            "webtoons": "{title}_{episode}.{extension}",  # Episodes, Series
            "tapas": "{title}_{episode}.{extension}",  # Episodes, Series
            # Video Platforms
            "bilibili": "{title}.{extension}",  # Articles, User Articles
            "vimeo": "{title}.{extension}",  # Videos, User Profiles
            "twitch": "{user[name]}_{title}.{extension}",  # Streams, User Profiles
            "tenor": "{title}.{extension}",  # GIFs, Search Results
            # Professional Platforms
            "patreon": "{user[name]}_{title}.{extension}",  # Posts, User Profiles
            "fanbox": "{user[name]}_{title}.{extension}",  # Posts, Creators
            "fantia": "{user[name]}_{title}.{extension}",  # Posts, Creators
            "boosty": "{user[name]}_{title}.{extension}",  # Posts, Creators
            # News & Media
            "bbc": "{title}.{extension}",  # Articles, Media
            "telegraph": "{title}.{extension}",  # Articles
            "slideshare": "{title}.{extension}",  # Presentations
            "speakerdeck": "{title}.{extension}",  # Presentations
            # Gaming Platforms
            "newgrounds": "{user[name]}_{title}.{extension}",  # Art, Games, Movies, User Profiles
            "steamgriddb": "{title}.{extension}",  # Game assets
            "civitai": "{title}.{extension}",  # AI models, Images
            # Wallpaper Sites
            "wallhaven": "{category}_{purity}.{extension}",  # Wallpapers, Categories
            "wallpapercave": "{title}.{extension}",  # Wallpapers
            "desktopography": "{title}.{extension}",  # Wallpapers, Exhibitions
            # Forums
            "4chan": "{board}_{thread}.{extension}",  # Boards, Threads
            "2ch": "{board}_{thread}.{extension}",  # Boards, Threads
            "8chan": "{board}_{thread}.{extension}",  # Boards, Threads
            "warosu": "{board}_{thread}.{extension}",  # Archive, Threads
            # File Sharing
            "cyberdrop": "{filename}.{extension}",  # Albums, Files
            "bunkr": "{filename}.{extension}",  # Albums, Files
            "saint": "{filename}.{extension}",  # Media files
            "uploadir": "{filename}.{extension}",  # File uploads
            # Alternative Social
            "bluesky": "{user[handle]}_{date:%Y%m%d}.{extension}",  # Posts, User Profiles
            "discord": "{channel[name]}_{date:%Y%m%d_%H%M}.{extension}",  # Messages, Channels
            "mastodon": "{user[username]}_{date:%Y%m%d}.{extension}",  # Posts, User Profiles
            # Other Popular Platforms
            "ao3": "{title}.{extension}",  # Works, Stories
            "weibo": "{user[name]}_{date:%Y%m%d}.{extension}",  # Posts, User Profiles
            "vk": "{user[name]}_{title}.{extension}",  # Posts, Albums, User Profiles
            "wikiart": "{artist}_{title}.{extension}",  # Artworks, Artists
            "vsco": "{user[username]}_{date:%Y%m%d}.{extension}",  # Photos, User Profiles
            "arcalive": "{board}_{title}.{extension}",  # Board posts
            "architizer": "{title}.{extension}",  # Architecture projects
            "toyhouse": "{character}_{title}.{extension}",  # Character art
        }

        # Use platform-specific template or smart fallback
        if self.platform in platform_templates:
            return platform_templates[self.platform]

        # Smart fallback template that prioritizes meaningful content
        return "{title}.{extension}"

    async def add_download(
        self,
        path: str,
        quality_config: dict[str, Any] | None = None,
        options: str = "",
    ):
        """
        Add gallery-dl download
        Following YoutubeDLHelper.add_download pattern
        """
        if not gallery_dl:
            await self.listener.on_download_error("Gallery-dl not installed")
            return

        try:
            self._download_path = path
            self._downloading = True

            # Setup gallery-dl configuration
            await self._setup_config(quality_config, options)

            # Use the gid that was already set in the main flow
            gid = self.listener.gid

            # Import task management
            from bot import task_dict, task_dict_lock

            # Create and register status
            download_status = GalleryDLStatus(self.listener, self, gid)
            async with task_dict_lock:
                task_dict[self.listener.mid] = download_status

            # Start download
            await self._start_download()

        except Exception as e:
            LOGGER.error(f"Gallery-dl download error: {e}")
            await self.listener.on_download_error(str(e))

    async def _setup_config(
        self, quality_config: dict[str, Any] | None = None, options: str = ""
    ):
        """Setup gallery-dl configuration"""
        try:
            # Store quality config and update platform if available
            self._quality_config = quality_config or {}
            if "platform" in self._quality_config:
                self.platform = self._quality_config["platform"]

            # Base configuration
            self._config = {
                "base-directory": self._download_path,
                "directory": ["{category}", "{subcategory}"],
                "filename": self._get_filename_template(),
                "extractor": {
                    "archive": None,  # Will be set if archive enabled
                    "sleep-request": [0.5, 1.5],  # Rate limiting
                    "retries": 3,
                    "timeout": 30,
                    "verify": True,
                },
                "output": {
                    "mode": "terminal",
                    "progress": True,
                    "log": {
                        "level": "info",
                        "format": {
                            "debug": "[{name}] {message}",
                            "info": "[{name}] {message}",
                            "warning": "[{name}] {message}",
                            "error": "[{name}] {message}",
                        },
                    },
                },
                "downloader": {
                    "part": True,
                    "part-directory": os.path.join(self._download_path, ".tmp"),
                    "progress": 0.1,  # Progress update interval
                },
            }

            # Apply quality configuration
            if quality_config:
                await self._apply_quality_config(quality_config)

            # Apply user options from Config
            if Config.GALLERY_DL_OPTIONS:
                self._config.update(Config.GALLERY_DL_OPTIONS)

            # Setup authentication (pass user_id for user-specific cookies)
            user_id = getattr(self.listener, "user_id", None)
            auth_config = await self.auth_manager.setup_authentication(
                self.platform, {}, user_id
            )
            if auth_config:
                if self.platform not in self._config["extractor"]:
                    self._config["extractor"][self.platform] = {}
                self._config["extractor"][self.platform].update(auth_config)

            # Setup archive if enabled
            if Config.GALLERY_DL_ARCHIVE_ENABLED:
                archive_dir = os.path.join(self._download_path, ".archive")
                os.makedirs(archive_dir, exist_ok=True)
                self._archive_path = os.path.join(
                    archive_dir, "gallery_dl_archive.db"
                )
                self._config["archive"] = self._archive_path

            # Setup post-processors
            post_processor_config = {
                "metadata": {"enabled": Config.GALLERY_DL_METADATA_ENABLED},
                "archive": {"enabled": Config.GALLERY_DL_ARCHIVE_ENABLED},
                "convert": {"enabled": False},
                "hooks": {"enabled": False},
            }
            processors = await self.post_processor.setup_post_processors(
                post_processor_config
            )
            if processors:
                self._config["postprocessor"] = processors

            # Apply rate limiting
            if Config.GALLERY_DL_RATE_LIMIT:
                # Parse rate limit string (e.g., "1/s" -> 1.0 seconds)
                try:
                    rate_limit = Config.GALLERY_DL_RATE_LIMIT
                    if isinstance(rate_limit, str):
                        if "/" in rate_limit:
                            # Parse "1/s" format
                            parts = rate_limit.split("/")
                            if len(parts) == 2:
                                num = float(parts[0])
                                unit = parts[1].lower()
                                if unit == "s":
                                    self._config["extractor"]["sleep-request"] = num
                                elif unit == "m":
                                    self._config["extractor"]["sleep-request"] = (
                                        num * 60
                                    )
                                else:
                                    self._config["extractor"]["sleep-request"] = num
                            else:
                                self._config["extractor"]["sleep-request"] = float(
                                    rate_limit
                                )
                        else:
                            self._config["extractor"]["sleep-request"] = float(
                                rate_limit
                            )
                    else:
                        self._config["extractor"]["sleep-request"] = rate_limit
                except (ValueError, TypeError):
                    # Use default rate limiting
                    self._config["extractor"]["sleep-request"] = [0.5, 1.5]

            # Parse additional options
            if options:
                await self._parse_options(options)

        except Exception as e:
            LOGGER.error(f"Error setting up gallery-dl config: {e}")
            raise

    async def _apply_quality_config(self, quality_config: dict):
        """Apply quality configuration to gallery-dl config"""
        try:
            quality = quality_config.get("quality", "original")
            format_type = quality_config.get("format", "best")

            # Platform-specific quality settings
            platform = getattr(self.listener, "platform", "default")

            if platform == "instagram":
                self._config["extractor"]["instagram"] = {
                    "videos": quality == "original",
                    "video-thumbnails": False,
                    "highlights": True,
                    "stories": True,
                    "tagged": False,
                }

            elif platform == "twitter":
                self._config["extractor"]["twitter"] = {
                    "videos": True,
                    "cards": False,
                    "quoted": False,
                    "replies": False,
                    "retweets": False,
                    "size": quality,
                }

            elif platform == "deviantart":
                self._config["extractor"]["deviantart"] = {
                    "original": quality == "original",
                    "comments": False,
                    "journals": False,
                    "mature": False,
                }

            elif platform == "pixiv":
                self._config["extractor"]["pixiv"] = {
                    "ugoira": True,
                    "ugoira-conv": format_type in ["mp4", "webm"],
                    "ugoira-conv-lossless": quality == "original",
                }

            elif platform == "reddit":
                self._config["extractor"]["reddit"] = {
                    "comments": 0,
                    "morecomments": False,
                    "videos": True,
                }

            # Comprehensive platform configurations (60+ platforms)
            elif platform == "500px":
                self._config["extractor"]["500px"] = {
                    "videos": True,
                    "metadata": True,
                }

            elif platform == "artstation":
                self._config["extractor"]["artstation"] = {
                    "external": True,
                    "metadata": True,
                }

            elif platform == "unsplash":
                self._config["extractor"]["unsplash"] = {
                    "format": quality if quality != "original" else "full",
                }

            elif platform == "flickr":
                self._config["extractor"]["flickr"] = {
                    "videos": True,
                    "metadata": True,
                }

            elif platform == "behance":
                self._config["extractor"]["behance"] = {
                    "videos": True,
                    "metadata": True,
                }

            elif platform == "pinterest":
                self._config["extractor"]["pinterest"] = {
                    "videos": True,
                    "metadata": True,
                }

            elif platform == "imgur":
                self._config["extractor"]["imgur"] = {
                    "mp4": True,
                    "metadata": True,
                }

            elif platform == "catbox":
                self._config["extractor"]["catbox"] = {}

            elif platform == "gofile":
                self._config["extractor"]["gofile"] = {}

            elif platform == "postimg":
                self._config["extractor"]["postimg"] = {}

            elif platform == "turboimagehost":
                self._config["extractor"]["turboimagehost"] = {}

            elif platform == "acidimg":
                self._config["extractor"]["acidimg"] = {}

            # Booru Sites (SFW)
            elif platform == "danbooru":
                self._config["extractor"]["danbooru"] = {
                    "metadata": True,
                }

            elif platform == "safebooru":
                self._config["extractor"]["safebooru"] = {
                    "metadata": True,
                }

            elif platform == "gelbooru":
                self._config["extractor"]["gelbooru"] = {
                    "metadata": True,
                }

            elif platform == "twibooru":
                self._config["extractor"]["twibooru"] = {
                    "metadata": True,
                }

            elif platform == "zerochan":
                self._config["extractor"]["zerochan"] = {
                    "metadata": True,
                }

            # Manga/Comics
            elif platform == "dynastyscans":
                self._config["extractor"]["dynastyscans"] = {}

            elif platform == "batoto":
                self._config["extractor"]["batoto"] = {}

            elif platform == "mangadex":
                self._config["extractor"]["mangadex"] = {}

            elif platform == "tcbscans":
                self._config["extractor"]["tcbscans"] = {}

            elif platform == "webtoons":
                self._config["extractor"]["webtoons"] = {}

            elif platform == "tapas":
                self._config["extractor"]["tapas"] = {}

            # Video Platforms
            elif platform == "bilibili":
                self._config["extractor"]["bilibili"] = {
                    "videos": True,
                    "metadata": True,
                }

            elif platform == "vimeo":
                self._config["extractor"]["vimeo"] = {
                    "videos": True,
                    "metadata": True,
                }

            elif platform == "twitch":
                self._config["extractor"]["twitch"] = {
                    "videos": True,
                    "metadata": True,
                }

            elif platform == "tenor":
                self._config["extractor"]["tenor"] = {
                    "videos": True,
                }

            # Professional Platforms
            elif platform == "patreon":
                self._config["extractor"]["patreon"] = {
                    "videos": True,
                    "metadata": True,
                }

            elif platform == "fanbox":
                self._config["extractor"]["fanbox"] = {
                    "metadata": True,
                }

            elif platform == "fantia":
                self._config["extractor"]["fantia"] = {
                    "metadata": True,
                }

            elif platform == "boosty":
                self._config["extractor"]["boosty"] = {
                    "metadata": True,
                }

            # News & Media
            elif platform == "bbc":
                self._config["extractor"]["bbc"] = {}

            elif platform == "telegraph":
                self._config["extractor"]["telegraph"] = {}

            elif platform == "slideshare":
                self._config["extractor"]["slideshare"] = {}

            elif platform == "speakerdeck":
                self._config["extractor"]["speakerdeck"] = {}

            # Gaming
            elif platform == "newgrounds":
                self._config["extractor"]["newgrounds"] = {}

            elif platform == "steamgriddb":
                self._config["extractor"]["steamgriddb"] = {}

            elif platform == "civitai":
                self._config["extractor"]["civitai"] = {}

            # Wallpapers
            elif platform == "wallhaven":
                self._config["extractor"]["wallhaven"] = {
                    "format": "original",
                }

            elif platform == "wallpapercave":
                self._config["extractor"]["wallpapercave"] = {}

            elif platform == "desktopography":
                self._config["extractor"]["desktopography"] = {}

            # Forums
            elif platform == "4chan":
                self._config["extractor"]["4chan"] = {}

            elif platform == "2ch":
                self._config["extractor"]["2ch"] = {}

            elif platform == "8chan":
                self._config["extractor"]["8chan"] = {}

            elif platform == "warosu":
                self._config["extractor"]["warosu"] = {}

            # File Sharing
            elif platform == "cyberdrop":
                self._config["extractor"]["cyberdrop"] = {}

            elif platform == "bunkr":
                self._config["extractor"]["bunkr"] = {}

            elif platform == "saint":
                self._config["extractor"]["saint"] = {}

            elif platform == "uploadir":
                self._config["extractor"]["uploadir"] = {}

            # Alternative Social
            elif platform == "bluesky":
                self._config["extractor"]["bluesky"] = {}

            elif platform == "discord":
                self._config["extractor"]["discord"] = {}

            elif platform == "mastodon":
                self._config["extractor"]["mastodon"] = {}

            # Other Popular
            elif platform == "ao3":
                self._config["extractor"]["ao3"] = {}

            elif platform == "weibo":
                self._config["extractor"]["weibo"] = {}

            elif platform == "vk":
                self._config["extractor"]["vk"] = {}

            elif platform == "wikiart":
                self._config["extractor"]["wikiart"] = {}

            elif platform == "vsco":
                self._config["extractor"]["vsco"] = {}

            elif platform == "arcalive":
                self._config["extractor"]["arcalive"] = {}

            elif platform == "architizer":
                self._config["extractor"]["architizer"] = {}

            elif platform == "toyhouse":
                self._config["extractor"]["toyhouse"] = {}

            # General format settings - simple extension replacement approach
            if format_type in ["png", "jpg", "jpeg", "webp"]:
                # Replace extension in filename template to force desired format
                current_filename = self._config.get(
                    "filename", "{id}_{title!s:50.50}.{extension}"
                )
                self._config["filename"] = current_filename.replace(
                    "{extension}", format_type
                )

            elif format_type != "best":
                # For other format types
                current_filename = self._config.get(
                    "filename", "{id}_{title!s:50.50}.{extension}"
                )
                self._config["filename"] = current_filename.replace(
                    "{extension}", format_type
                )

        except Exception as e:
            LOGGER.error(f"Error applying quality config: {e}")

    async def _parse_options(self, options: str):
        """Parse additional options string"""
        try:
            # Simple option parsing (can be enhanced)
            if "--archive" in options:
                # Force enable archive
                if not self._archive_path:
                    archive_dir = os.path.join(self._download_path, ".archive")
                    os.makedirs(archive_dir, exist_ok=True)
                    self._archive_path = os.path.join(
                        archive_dir, "gallery_dl_archive.db"
                    )
                    self._config["archive"] = self._archive_path

            if "--no-archive" in options:
                # Disable archive
                self._config["archive"] = None

            if "--metadata" in options:
                # Enable metadata extraction
                self._config["extractor"]["postprocessors"] = [
                    {
                        "name": "metadata",
                        "mode": "json",
                    }
                ]

        except Exception as e:
            LOGGER.error(f"Error parsing options: {e}")

    async def _start_download(self):
        """Start the gallery-dl download process"""
        try:
            # Create download directory
            os.makedirs(self._download_path, exist_ok=True)

            # Setup progress hooks
            self._config["output"]["progress"] = self._progress_hook

            # Create gallery-dl job
            urls = [self.listener.link]

            # Run download in executor to avoid blocking
            LOGGER.info("Starting gallery-dl download process...")
            await asyncio.get_event_loop().run_in_executor(
                None, self._run_gallery_dl, urls
            )

            # Check for cancellation from both sources
            if self._is_cancelled or self.listener.is_cancelled:
                await self.listener.on_download_error("Download cancelled")
                return

            # Check if download was successful by counting files in download directory
            downloaded_files = await self._count_downloaded_files()

            # Final cancellation check before processing results
            if self._is_cancelled or self.listener.is_cancelled:
                await self.listener.on_download_error("Download cancelled")
                return

            if downloaded_files == 0:
                LOGGER.warning("No files found in download directory")
                await self.listener.on_download_error("No files downloaded")
                return

            # Update count for status display
            self._count = downloaded_files

            # Calculate final size
            self._size = await get_path_size(self._download_path)

            # Final cancellation check before completing
            if self._is_cancelled or self.listener.is_cancelled:
                await self.listener.on_download_error("Download cancelled")
                return

            # Complete download
            await self.listener.on_download_complete()

        except Exception as e:
            LOGGER.error(f"Gallery-dl download failed: {e}")
            await self.listener.on_download_error(str(e))

    def _run_gallery_dl(self, urls: list):
        """Run gallery-dl in synchronous context"""
        try:
            # Check for cancellation before starting
            if self._is_cancelled or self.listener.is_cancelled:
                return

            # Import gallery-dl modules
            from gallery_dl import config as gdl_config
            from gallery_dl import job

            # Apply configuration using correct API
            gdl_config.clear()

            # Set configuration values
            for section, values in self._config.items():
                if isinstance(values, dict):
                    for key, value in values.items():
                        config_path = f"{section}.{key}"
                        gdl_config.set((), config_path, value)
                else:
                    gdl_config.set((), section, values)

            # Create and run job with proper API
            self._job = job.DownloadJob(urls[0])

            # Register hooks with the job
            self._job.hooks = {
                "pre": [self._pre_hook],
                "post": [self._post_hook],
                "skip": [self._skip_hook],
                "failure": [self._failure_hook],
            }

            # Check for cancellation before running job
            if self._is_cancelled or self.listener.is_cancelled:
                return

            # Run the job
            self._job.run()

        except Exception as e:
            # Check if this is a cancellation-related error
            if self._is_cancelled or self.listener.is_cancelled:
                return
            LOGGER.error(f"Gallery-dl job failed: {e}")
            raise

    def _progress_hook(self, info_dict: dict[str, Any]):
        """Progress hook for gallery-dl"""
        try:
            if self._is_cancelled:
                return

            # Update progress information
            if "downloaded_bytes" in info_dict:
                self._last_downloaded = info_dict["downloaded_bytes"]

            if "total_bytes" in info_dict:
                self._size = info_dict["total_bytes"]

        except Exception as e:
            LOGGER.info(f"Progress hook error: {e}")

    def _pre_hook(self, pathfmt):
        """Pre-download hook"""
        try:
            # Check for cancellation from both sources
            if self._is_cancelled or self.listener.is_cancelled:
                # Try to stop the job if possible
                if self._job:
                    try:
                        # Gallery-dl doesn't have a direct stop method, but we can raise an exception
                        raise KeyboardInterrupt("Download cancelled")
                    except Exception:
                        pass
                return

        except Exception as e:
            LOGGER.info(f"Pre-hook error: {e}")

    def _post_hook(self, pathfmt):
        """Post-download hook"""
        try:
            # Check for cancellation from both sources
            if self._is_cancelled or self.listener.is_cancelled:
                return

            # Increment file count
            self._count += 1

            # Update size
            if os.path.exists(pathfmt.realpath):
                file_size = os.path.getsize(pathfmt.realpath)
                self._last_downloaded += file_size

        except Exception as e:
            LOGGER.info(f"Post-hook error: {e}")

    def _skip_hook(self, pathfmt):
        """Skip hook for already downloaded files"""
        try:
            LOGGER.info(f"Skipped (already exists): {pathfmt.filename}")
        except Exception as e:
            LOGGER.info(f"Skip-hook error: {e}")

    def _failure_hook(self, pathfmt):
        """Failure hook for failed downloads"""
        try:
            LOGGER.warning(f"Failed to download: {pathfmt.filename}")
        except Exception as e:
            LOGGER.info(f"Failure-hook error: {e}")

    async def _count_downloaded_files(self):
        """Count the number of files downloaded in the download directory"""
        try:
            file_count = 0
            search_paths = [self._download_path]

            # Also check the current working directory where gallery-dl might download
            # This is a fallback in case base-directory config doesn't work
            cwd_gallery_path = os.path.join(os.getcwd(), "gallery-dl")
            if os.path.exists(cwd_gallery_path):
                search_paths.append(cwd_gallery_path)

            for search_path in search_paths:
                if os.path.exists(search_path):
                    for root, dirs, files in os.walk(search_path):
                        # Skip hidden directories and archive directories
                        dirs[:] = [d for d in dirs if not d.startswith(".")]

                        for file in files:
                            file_path = os.path.join(root, file)

                            # Skip hidden files and very small files (likely metadata)
                            if file.startswith("."):
                                continue

                            # Skip common metadata file extensions
                            if file.endswith(
                                (".json", ".yaml", ".yml", ".txt", ".db", ".log")
                            ):
                                continue

                            # Only count files that actually exist and have content
                            if (
                                os.path.exists(file_path)
                                and os.path.getsize(file_path) > 100
                            ):  # At least 100 bytes
                                file_count += 1

                                # If file is not in our target directory, move it there
                                if not file_path.startswith(self._download_path):
                                    await self._move_file_to_target(file_path, file)

            return file_count

        except Exception as e:
            LOGGER.error(f"Error counting downloaded files: {e}")
            return 0

    async def _move_file_to_target(self, source_path: str, filename: str):
        """Move a file from gallery-dl's default location to our target directory"""
        try:
            import shutil

            # Create target path
            target_path = os.path.join(self._download_path, filename)

            # Create target directory if it doesn't exist
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # Move the file
            shutil.move(source_path, target_path)

        except Exception as e:
            LOGGER.error(f"Error moving file {source_path}: {e}")

    async def cancel_task(self):
        """Cancel the download task"""
        self._is_cancelled = True

        # Also ensure listener cancellation is set
        if hasattr(self.listener, "is_cancelled"):
            self.listener.is_cancelled = True

        if self._job:
            # Gallery-dl doesn't have a direct cancel method
            # We rely on the _is_cancelled flag in hooks
            # The hooks will check both _is_cancelled and listener.is_cancelled
            pass

        LOGGER.info("Gallery-dl download cancelled")

        # Cleanup components
        await self._cleanup()

    async def _cleanup(self):
        """Cleanup download helper resources"""
        try:
            if hasattr(self, "auth_manager"):
                await self.auth_manager.cleanup()
            if hasattr(self, "post_processor"):
                await self.post_processor.cleanup()

            # Run gallery-dl specific garbage collection
            try:
                from bot.helper.ext_utils.gc_utils import gallery_dl_cleanup

                gallery_dl_cleanup()
            except Exception as e:
                LOGGER.info(f"Gallery-dl GC cleanup error: {e}")

        except Exception as e:
            LOGGER.error(f"Error during gallery-dl cleanup: {e}")

    @property
    def speed(self) -> float:
        """Get download speed"""
        try:
            elapsed = time() - self._start_time
            if elapsed > 0:
                return self._last_downloaded / elapsed
            return 0
        except Exception:
            return 0

    @property
    def downloaded_bytes(self) -> int:
        """Get downloaded bytes"""
        return self._last_downloaded

    @property
    def size(self) -> int:
        """Get total size"""
        return self._size

    @property
    def progress(self) -> float:
        """Get download progress percentage"""
        try:
            if self._size > 0:
                return (self._last_downloaded / self._size) * 100
            return 0
        except Exception:
            return 0
