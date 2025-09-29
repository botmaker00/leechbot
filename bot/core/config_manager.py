import ast
import logging
import os
import time
from functools import lru_cache
from importlib import import_module
from typing import Any, ClassVar

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ConfigCache:
    """High-performance configuration caching system"""

    def __init__(self):
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 300  # 5 minutes default TTL
        self._access_count = {}
        self._hit_count = 0
        self._miss_count = 0
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # Cleanup every minute

    def get(self, key: str, default: Any = None) -> Any:
        """Get cached configuration value with performance tracking"""
        current_time = time.time()

        # Track access patterns
        self._access_count[key] = self._access_count.get(key, 0) + 1

        # Periodic cleanup of expired entries
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired()
            self._last_cleanup = current_time

        # Check if cached value exists and is still valid
        if (
            key in self._cache
            and key in self._cache_timestamps
            and current_time - self._cache_timestamps[key] < self._cache_ttl
        ):
            self._hit_count += 1
            return self._cache[key]

        # Cache miss - get fresh value
        self._miss_count += 1
        try:
            value = getattr(Config, key, default)
        except AttributeError:
            value = default

        # Cache the value
        self._cache[key] = value
        self._cache_timestamps[key] = current_time
        return value

    def set(self, key: str, value: Any):
        """Set configuration value and update cache"""
        # Update the actual Config class
        if hasattr(Config, key):
            setattr(Config, key, value)

        # Update cache
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()

    def invalidate(self, key: str | None = None):
        """Invalidate cache entries"""
        if key:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()

    def _cleanup_expired(self):
        """Remove expired cache entries"""
        current_time = time.time()
        expired_keys = [
            key
            for key, timestamp in self._cache_timestamps.items()
            if current_time - timestamp > self._cache_ttl
        ]
        for key in expired_keys:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)

    def get_stats(self) -> dict:
        """Get cache performance statistics"""
        total_requests = self._hit_count + self._miss_count
        hit_rate = (
            (self._hit_count / total_requests * 100) if total_requests > 0 else 0
        )

        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": f"{hit_rate:.1f}%",
            "cache_size": len(self._cache),
            "most_accessed": sorted(
                self._access_count.items(), key=lambda x: x[1], reverse=True
            )[:10],
        }

    def log_stats(self):
        """Log cache performance statistics"""
        stats = self.get_stats()
        logger.info(
            f"Config Cache Stats: {stats['hit_rate']} hit rate, "
            f"{stats['cache_size']} entries, "
            f"{stats['hit_count']} hits, {stats['miss_count']} misses"
        )


# Global cache instance
_config_cache = ConfigCache()


class Config:
    AS_DOCUMENT: bool = False
    AUTHORIZED_CHATS: str = ""
    BASE_URL: str = ""
    BASE_URL_PORT: int = 80
    BOT_TOKEN: str = ""
    CMD_SUFFIX: str = ""
    DATABASE_URL: str = ""
    DEFAULT_UPLOAD: str = "gd"
    # Debrid-Link Authentication Settings
    DEBRID_LINK_API = ""  # Legacy API key or OAuth2 access_token
    DEBRID_LINK_ACCESS_TOKEN = ""  # OAuth2 access_token (recommended)
    DEBRID_LINK_REFRESH_TOKEN = ""  # OAuth2 refresh_token for token renewal
    DEBRID_LINK_CLIENT_ID = ""  # OAuth2 client_id from Debrid-Link app
    DEBRID_LINK_CLIENT_SECRET = ""  # OAuth2 client_secret (keep secure)
    DEBRID_LINK_TOKEN_EXPIRES = 0  # Token expiration timestamp

    # TorBox API Settings
    TORBOX_API_KEY: str = ""  # TorBox API key for premium downloads

    # Mega-Debrid API Settings
    MEGA_DEBRID_API_TOKEN: str = ""  # Mega-Debrid API token for premium downloads
    MEGA_DEBRID_LOGIN: str = ""  # Mega-Debrid login username
    MEGA_DEBRID_PASSWORD: str = ""  # Mega-Debrid login password

    # AllDebrid API Settings
    ALLDEBRID_API_KEY: str = ""  # AllDebrid API key for premium downloads

    # Real-Debrid API Settings
    REAL_DEBRID_API_KEY: str = ""  # Real-Debrid API key for premium downloads
    REAL_DEBRID_ACCESS_TOKEN: str = ""  # OAuth2 access token (recommended)
    REAL_DEBRID_REFRESH_TOKEN: str = ""  # OAuth2 refresh token for automatic renewal
    REAL_DEBRID_CLIENT_ID: str = ""  # OAuth2 client ID from Real-Debrid app
    REAL_DEBRID_CLIENT_SECRET: str = ""  # OAuth2 client secret (keep secure)
    REAL_DEBRID_TOKEN_EXPIRES: int = 0  # Token expiration timestamp

    EXCLUDED_EXTENSIONS: str = ""
    FFMPEG_CMDS: ClassVar[dict[str, list[str]]] = {}
    FILELION_API: str = ""
    GDRIVE_ID: str = ""

    # Google Drive Upload Settings
    GDRIVE_UPLOAD_ENABLED: bool = True  # Enable/disable Google Drive upload feature

    HELPER_TOKENS: str = ""
    HYPER_THREADS: int = 0
    INCOMPLETE_TASK_NOTIFIER: bool = False
    INDEX_URL: str = ""
    IMDB_TEMPLATE: str = ""
    JD_EMAIL: str = ""
    JD_PASS: str = ""

    # Mega.nz Settings
    MEGA_ENABLED: bool = True
    MEGA_EMAIL: str = ""
    MEGA_PASSWORD: str = ""

    # MEGA Upload Settings
    MEGA_UPLOAD_ENABLED: bool = True
    MEGA_UPLOAD_PUBLIC: bool = True  # Generate public links by default
    MEGA_UPLOAD_THUMBNAIL: bool = True  # Generate thumbnails for videos using FFmpeg

    # MEGA Search Settings
    MEGA_SEARCH_ENABLED: bool = True  # Enable/disable MEGA search functionality

    IS_TEAM_DRIVE: bool = False
    LEECH_DUMP_CHAT: ClassVar[list[str]] = []
    BOT_PM: bool = True  # Enable/disable sending media to user's bot PM

    # Forwarding Settings
    FORWARD_SOURCE: ClassVar[
        list[str]
    ] = []  # Source chat IDs/usernames for automatic forwarding (comma-separated)
    FORWARD_DESTINATION: ClassVar[
        list[str]
    ] = []  # Destination chat IDs/usernames for automatic forwarding (comma-separated)

    LEECH_FILENAME_PREFIX: str = ""
    LEECH_SUFFIX: str = ""
    LEECH_FONT: str = ""
    LEECH_FILENAME: str = ""
    UNIVERSAL_FILENAME: str = (
        ""  # Universal filename template for both mirror and leech
    )
    LEECH_SPLIT_SIZE: int = 2097152000
    EQUAL_SPLITS: bool = False
    LOGIN_PASS: str = ""
    MEDIA_GROUP: bool = False
    HYBRID_LEECH: bool = False
    MEDIA_SEARCH_CHATS: ClassVar[list] = []
    HYDRA_IP: str = ""
    HYDRA_API_KEY: str = ""
    NAME_SUBSTITUTE: str = r""
    OWNER_ID: int = 0
    QUEUE_ALL: int = 0
    QUEUE_DOWNLOAD: int = 0
    QUEUE_UPLOAD: int = 0
    RCLONE_FLAGS: str = ""
    RCLONE_PATH: str = ""
    RCLONE_SERVE_URL: str = ""
    RCLONE_SERVE_USER: str = ""
    RCLONE_SERVE_PASS: str = ""
    RCLONE_SERVE_PORT: int = 8080
    RSS_CHAT: str = ""
    RSS_DELAY: int = 600
    RSS_SIZE_LIMIT: int = 0
    RSS_ENABLED: bool = True  # Enable/disable RSS functionality completely
    RSS_JOB_INTERVAL: int = 600  # RSS job periodic runtime interval in seconds
    SCHEDULED_DELETION_ENABLED: bool = (
        True  # Enable/disable scheduled deletion functionality
    )
    STOP_DUPLICATE: bool = False
    STREAMWISH_API: str = ""
    SUDO_USERS: str = ""
    TELEGRAM_API: int = 0
    TELEGRAM_HASH: str = ""
    TG_PROXY: ClassVar[dict[str, str]] = {}
    THUMBNAIL_LAYOUT: str = ""
    TORRENT_TIMEOUT: int = 0
    UPLOAD_PATHS: ClassVar[dict[str, str]] = {}
    UPSTREAM_REPO: str = ""
    USENET_SERVERS: ClassVar[list[dict[str, object]]] = []
    UPSTREAM_BRANCH: str = "main"
    USER_SESSION_STRING: str = ""
    USER_TRANSMISSION: bool = False
    USE_SERVICE_ACCOUNTS: bool = False
    WEB_PINCODE: bool = False
    YT_DLP_OPTIONS: ClassVar[dict[str, Any]] = {}

    # Gallery-dl Settings
    GALLERY_DL_ENABLED: bool = True
    GALLERY_DL_OPTIONS: ClassVar[dict[str, Any]] = {}
    GALLERY_DL_QUALITY_SELECTION: bool = True
    GALLERY_DL_ARCHIVE_ENABLED: bool = True
    GALLERY_DL_METADATA_ENABLED: bool = True
    GALLERY_DL_MAX_DOWNLOADS: int = 50
    GALLERY_DL_RATE_LIMIT: str = "1/s"

    # Gallery-dl Authentication Settings
    # Instagram
    GALLERY_DL_INSTAGRAM_USERNAME: str = ""
    GALLERY_DL_INSTAGRAM_PASSWORD: str = ""

    # Twitter/X
    GALLERY_DL_TWITTER_USERNAME: str = ""
    GALLERY_DL_TWITTER_PASSWORD: str = ""

    # Reddit
    GALLERY_DL_REDDIT_CLIENT_ID: str = ""
    GALLERY_DL_REDDIT_CLIENT_SECRET: str = ""
    GALLERY_DL_REDDIT_USERNAME: str = ""
    GALLERY_DL_REDDIT_PASSWORD: str = ""
    GALLERY_DL_REDDIT_REFRESH_TOKEN: str = ""

    # Pixiv
    GALLERY_DL_PIXIV_USERNAME: str = ""
    GALLERY_DL_PIXIV_PASSWORD: str = ""
    GALLERY_DL_PIXIV_REFRESH_TOKEN: str = ""

    # DeviantArt
    GALLERY_DL_DEVIANTART_CLIENT_ID: str = ""
    GALLERY_DL_DEVIANTART_CLIENT_SECRET: str = ""
    GALLERY_DL_DEVIANTART_USERNAME: str = ""
    GALLERY_DL_DEVIANTART_PASSWORD: str = ""

    # Tumblr
    GALLERY_DL_TUMBLR_API_KEY: str = ""
    GALLERY_DL_TUMBLR_API_SECRET: str = ""
    GALLERY_DL_TUMBLR_TOKEN: str = ""
    GALLERY_DL_TUMBLR_TOKEN_SECRET: str = ""

    # Discord
    GALLERY_DL_DISCORD_TOKEN: str = ""

    # Streamrip Settings
    STREAMRIP_ENABLED: bool = True
    STREAMRIP_CONCURRENT_DOWNLOADS: int = 4
    STREAMRIP_MAX_SEARCH_RESULTS: int = 200
    STREAMRIP_ENABLE_DATABASE: bool = True
    STREAMRIP_AUTO_CONVERT: bool = True

    # Streamrip Quality and Format Settings
    STREAMRIP_DEFAULT_QUALITY: int = 3
    STREAMRIP_FALLBACK_QUALITY: int = 2
    STREAMRIP_DEFAULT_CODEC: str = "flac"
    STREAMRIP_SUPPORTED_CODECS: ClassVar[list[str]] = [
        "flac",
        "mp3",
        "m4a",
        "ogg",
        "opus",
    ]
    STREAMRIP_QUALITY_FALLBACK_ENABLED: bool = True

    # Streamrip Platform Settings
    STREAMRIP_QOBUZ_ENABLED: bool = True
    STREAMRIP_QOBUZ_QUALITY: int = 3
    STREAMRIP_TIDAL_ENABLED: bool = True
    STREAMRIP_TIDAL_QUALITY: int = 3
    STREAMRIP_DEEZER_ENABLED: bool = True
    STREAMRIP_DEEZER_QUALITY: int = 2
    STREAMRIP_SOUNDCLOUD_ENABLED: bool = True
    STREAMRIP_SOUNDCLOUD_QUALITY: int = 0
    STREAMRIP_LASTFM_ENABLED: bool = True
    STREAMRIP_YOUTUBE_QUALITY: int = 0

    # Streamrip Authentication
    STREAMRIP_QOBUZ_EMAIL: str = ""
    STREAMRIP_QOBUZ_PASSWORD: str = ""
    STREAMRIP_TIDAL_EMAIL: str = ""
    STREAMRIP_TIDAL_PASSWORD: str = ""
    STREAMRIP_TIDAL_ACCESS_TOKEN: str = ""
    STREAMRIP_TIDAL_REFRESH_TOKEN: str = ""
    STREAMRIP_TIDAL_USER_ID: str = ""
    STREAMRIP_TIDAL_COUNTRY_CODE: str = ""
    STREAMRIP_DEEZER_ARL: str = ""
    STREAMRIP_SOUNDCLOUD_CLIENT_ID: str = ""
    STREAMRIP_SOUNDCLOUD_APP_VERSION: str = ""

    # Streamrip Advanced Features
    STREAMRIP_FILENAME_TEMPLATE: str = ""
    STREAMRIP_FOLDER_TEMPLATE: str = ""
    STREAMRIP_EMBED_COVER_ART: bool = True
    STREAMRIP_SAVE_COVER_ART: bool = True
    STREAMRIP_COVER_ART_SIZE: str = "large"

    # Streamrip Downloads Configuration
    STREAMRIP_MAX_CONNECTIONS: int = 6
    STREAMRIP_REQUESTS_PER_MINUTE: int = 60
    STREAMRIP_SOURCE_SUBDIRECTORIES: bool = False
    STREAMRIP_DISC_SUBDIRECTORIES: bool = True
    STREAMRIP_CONCURRENCY: bool = True
    STREAMRIP_VERIFY_SSL: bool = True

    # Streamrip Qobuz Configuration
    STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS: bool = True
    STREAMRIP_QOBUZ_USE_AUTH_TOKEN: bool = False
    STREAMRIP_QOBUZ_APP_ID: str = ""
    STREAMRIP_QOBUZ_SECRETS: ClassVar[list[str]] = []

    # Streamrip Tidal Configuration
    STREAMRIP_TIDAL_DOWNLOAD_VIDEOS: bool = True
    STREAMRIP_TIDAL_TOKEN_EXPIRY: str = "0"

    # Streamrip Deezer Configuration
    STREAMRIP_DEEZER_USE_DEEZLOADER: bool = True
    STREAMRIP_DEEZER_DEEZLOADER_WARNINGS: bool = True

    # Streamrip SoundCloud Configuration
    # STREAMRIP_SOUNDCLOUD_APP_VERSION already defined above

    # Streamrip YouTube Configuration
    STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS: bool = False
    STREAMRIP_YOUTUBE_VIDEO_FOLDER: str = ""
    STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER: str = ""

    # Streamrip Database Configuration
    STREAMRIP_DATABASE_DOWNLOADS_ENABLED: bool = False
    STREAMRIP_DATABASE_DOWNLOADS_PATH: str = "./downloads.db"
    STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED: bool = True
    STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH: str = "./failed_downloads.db"

    # Zotify Settings - Based on official Zotify CONFIG_VALUES
    ZOTIFY_ENABLED: bool = True

    # Zotify Authentication
    ZOTIFY_CREDENTIALS_PATH: str = "./zotify_credentials.json"

    # Zotify Library Paths (from LIBRARY_PATHS)
    ZOTIFY_ALBUM_LIBRARY: str = "Music/Zotify Albums"
    ZOTIFY_PODCAST_LIBRARY: str = "Music/Zotify Podcasts"
    ZOTIFY_PLAYLIST_LIBRARY: str = "Music/Zotify Playlists"

    # Zotify Output Templates (from OUTPUT_PATHS and CONFIG_VALUES)
    ZOTIFY_OUTPUT_ALBUM: str = (
        "{album_artist}/{album}/{track_number}. {artists} - {title}"
    )
    ZOTIFY_OUTPUT_PLAYLIST_TRACK: str = "{playlist}/{artists} - {title}"
    ZOTIFY_OUTPUT_PLAYLIST_EPISODE: str = "{playlist}/{episode_number} - {title}"
    ZOTIFY_OUTPUT_PODCAST: str = "{podcast}/{episode_number} - {title}"
    ZOTIFY_OUTPUT_SINGLE: str = (
        "{artists} - {title}"  # For single tracks not in albums
    )

    # Zotify Quality and Format Settings (Optimized for free accounts)
    ZOTIFY_DOWNLOAD_QUALITY: str = (
        "normal"  # auto, normal, high, very_high (normal=160kbps max for free)
    )
    ZOTIFY_AUDIO_FORMAT: str = "mp3"  # vorbis, mp3, flac, aac, fdk_aac, opus, wav, wavpack (mp3 most compatible)
    ZOTIFY_ARTWORK_SIZE: str = "medium"  # small, medium, large (medium to reduce bandwidth for free accounts)
    ZOTIFY_TRANSCODE_BITRATE: int = -1  # -1 to use download rate

    # Zotify Download Settings
    ZOTIFY_DOWNLOAD_REAL_TIME: bool = False
    ZOTIFY_REPLACE_EXISTING: bool = False
    ZOTIFY_SKIP_DUPLICATES: bool = True  # Default True in Zotify
    ZOTIFY_SKIP_PREVIOUS: bool = True  # Default True in Zotify

    # Zotify Metadata and Files
    ZOTIFY_SAVE_METADATA: bool = True
    ZOTIFY_SAVE_GENRE: bool = False
    ZOTIFY_ALL_ARTISTS: bool = True  # Default True in Zotify
    ZOTIFY_LYRICS_FILE: bool = False
    ZOTIFY_LYRICS_ONLY: bool = False
    ZOTIFY_SAVE_SUBTITLES: bool = False
    ZOTIFY_CREATE_PLAYLIST_FILE: bool = True

    # Zotify FFmpeg Settings
    ZOTIFY_FFMPEG_PATH: str = ""
    ZOTIFY_FFMPEG_ARGS: str = ""

    # Zotify Language and Locale
    ZOTIFY_LANGUAGE: str = "en"

    # Zotify Print/Logging Settings (from CONFIG_VALUES)
    ZOTIFY_PRINT_PROGRESS: bool = True
    ZOTIFY_PRINT_DOWNLOADS: bool = False  # Default False in Zotify
    ZOTIFY_PRINT_ERRORS: bool = True
    ZOTIFY_PRINT_WARNINGS: bool = True
    ZOTIFY_PRINT_SKIPS: bool = False  # Default False in Zotify

    # Zotify Match Functionality (from CONFIG_VALUES)
    ZOTIFY_MATCH_EXISTING: bool = (
        False  # Match existing files for skip functionality
    )

    # Missing CONFIG_VALUES from Zotify (exact 25 total)
    # Note: We already have most, but these were missing or incorrectly named

    # Zotify Supported Formats (for validation)
    ZOTIFY_SUPPORTED_AUDIO_FORMATS: ClassVar[list[str]] = [
        "vorbis",
        "mp3",
        "flac",
        "aac",
        "fdk_aac",
        "opus",
        "wav",
        "wavpack",
    ]
    ZOTIFY_SUPPORTED_QUALITIES: ClassVar[list[str]] = [
        "auto",
        "normal",
        "high",
        "very_high",
    ]
    ZOTIFY_SUPPORTED_ARTWORK_SIZES: ClassVar[list[str]] = [
        "small",
        "medium",
        "large",
    ]

    # Streamrip Conversion Configuration
    STREAMRIP_CONVERSION_ENABLED: bool = False
    STREAMRIP_CONVERSION_CODEC: str = "ALAC"
    STREAMRIP_CONVERSION_SAMPLING_RATE: int = 48000
    STREAMRIP_CONVERSION_BIT_DEPTH: int = 24
    STREAMRIP_CONVERSION_LOSSY_BITRATE: int = 320

    # Streamrip Qobuz Filters Configuration
    STREAMRIP_QOBUZ_FILTERS_EXTRAS: bool = False
    STREAMRIP_QOBUZ_FILTERS_REPEATS: bool = False
    STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS: bool = False
    STREAMRIP_QOBUZ_FILTERS_FEATURES: bool = False
    STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS: bool = False
    STREAMRIP_QOBUZ_FILTERS_NON_REMASTER: bool = False

    # Streamrip Artwork Configuration
    STREAMRIP_ARTWORK_EMBED_MAX_WIDTH: int = -1
    STREAMRIP_ARTWORK_SAVED_MAX_WIDTH: int = -1

    # Streamrip Metadata Configuration
    STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM: bool = True
    STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS: bool = True
    STREAMRIP_METADATA_EXCLUDE: ClassVar[list[str]] = []

    # Streamrip Filepaths Configuration
    STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER: bool = False
    STREAMRIP_FILEPATHS_FOLDER_FORMAT: str = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
    STREAMRIP_FILEPATHS_TRACK_FORMAT: str = (
        "{tracknumber:02}. {artist} - {title}{explicit}"
    )
    STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS: bool = False
    STREAMRIP_FILEPATHS_TRUNCATE_TO: int = 120

    # Streamrip Last.fm Configuration
    STREAMRIP_LASTFM_SOURCE: str = "qobuz"
    STREAMRIP_LASTFM_FALLBACK_SOURCE: str = ""

    # Streamrip CLI Configuration
    STREAMRIP_CLI_TEXT_OUTPUT: bool = True
    STREAMRIP_CLI_PROGRESS_BARS: bool = True
    STREAMRIP_CLI_MAX_SEARCH_RESULTS: int = 200

    # Streamrip Misc Configuration
    STREAMRIP_MISC_CHECK_FOR_UPDATES: bool = True
    STREAMRIP_MISC_VERSION: str = "2.0.6"

    # INKYPINKY
    # Global metadata settings
    METADATA_KEY: str = ""  # Legacy metadata key
    METADATA_ALL: str = ""  # Global metadata for all fields
    METADATA_TITLE: str = ""  # Global title metadata
    METADATA_AUTHOR: str = ""  # Global author metadata
    METADATA_COMMENT: str = ""  # Global comment metadata

    # Video track metadata
    METADATA_VIDEO_TITLE: str = ""  # Video track title metadata
    METADATA_VIDEO_AUTHOR: str = ""  # Video track author metadata
    METADATA_VIDEO_COMMENT: str = ""  # Video track comment metadata

    # Audio track metadata
    METADATA_AUDIO_TITLE: str = ""  # Audio track title metadata
    METADATA_AUDIO_AUTHOR: str = ""  # Audio track author metadata
    METADATA_AUDIO_COMMENT: str = ""  # Audio track comment metadata

    # Subtitle track metadata
    METADATA_SUBTITLE_TITLE: str = ""  # Subtitle track title metadata
    METADATA_SUBTITLE_AUTHOR: str = ""  # Subtitle track author metadata
    METADATA_SUBTITLE_COMMENT: str = ""  # Subtitle track comment metadata
    SET_COMMANDS: bool = True
    TOKEN_TIMEOUT: int = 0
    PAID_CHANNEL_ID: int = 0
    PAID_CHANNEL_LINK: str = ""
    DELETE_LINKS: bool = False
    FSUB_IDS: str = ""
    AD_KEYWORDS: str = ""  # Custom keywords for ad detection, separated by comma
    AD_BROADCASTER_ENABLED: bool = False  # Enable/disable ad broadcaster module
    LOG_CHAT_ID: int = 0
    LEECH_FILENAME_CAPTION: str = ""
    INSTADL_API: str = ""
    MEDIA_STORE: bool = False

    # Media Tools Settings
    MEDIA_TOOLS_ENABLED: bool = True
    MEDIAINFO_ENABLED: bool = False

    # DDL (Direct Download Link) Upload Settings
    DDL_ENABLED: bool = True  # Enable/disable DDL upload feature
    DDL_DEFAULT_SERVER: str = (
        "gofile"  # Default DDL server: gofile, streamtape, devuploads, mediafire
    )

    # Gofile Settings
    GOFILE_API_KEY: str = ""  # Default Gofile API key (can be overridden per user)
    GOFILE_FOLDER_NAME: str = (
        ""  # Default folder name for uploads (empty = use filename)
    )
    GOFILE_PUBLIC_LINKS: bool = True  # Generate public links by default
    GOFILE_PASSWORD_PROTECTION: bool = False  # Enable password protection
    GOFILE_DEFAULT_PASSWORD: str = ""  # Default password for protected uploads
    GOFILE_LINK_EXPIRY_DAYS: int = 0  # Link expiry in days (0 = no expiry)

    # Streamtape Settings
    STREAMTAPE_API_USERNAME: str = (
        ""  # Streamtape API/FTP Username (from account panel)
    )
    STREAMTAPE_API_PASSWORD: str = (
        ""  # Streamtape API/FTP Password (from account panel)
    )
    STREAMTAPE_FOLDER_NAME: str = ""  # Default folder name for uploads

    # DevUploads Settings
    DEVUPLOADS_API_KEY: str = ""  # Default DevUploads API key
    DEVUPLOADS_FOLDER_NAME: str = ""  # Default folder name for uploads
    DEVUPLOADS_PUBLIC_FILES: bool = (
        True  # Default public/private setting for uploads
    )

    # MediaFire API Settings
    MEDIAFIRE_API_KEY: str = ""  # MediaFire API key for authenticated access
    MEDIAFIRE_EMAIL: str = (
        ""  # MediaFire account email for session-based authentication
    )
    MEDIAFIRE_PASSWORD: str = (
        ""  # MediaFire account password for session-based authentication
    )
    MEDIAFIRE_APP_ID: str = (
        ""  # MediaFire application ID (optional, for higher rate limits)
    )

    STREAMTAPE_ALLOWED_EXTENSIONS: ClassVar[list[str]] = [
        ".avi",
        ".mkv",
        ".mpg",
        ".mpeg",
        ".vob",
        ".wmv",
        ".flv",
        ".mp4",
        ".mov",
        ".m4v",
        ".m2v",
        ".divx",
        ".3gp",
        ".webm",
        ".ogv",
        ".ogg",
        ".ts",
        ".ogm",
    ]  # Allowed video extensions for Streamtape

    # YouTube Upload Settings
    YOUTUBE_UPLOAD_ENABLED: bool = True  # Enable/disable YouTube upload feature
    YOUTUBE_UPLOAD_DEFAULT_PRIVACY: str = (
        "unlisted"  # Default privacy setting: public, unlisted, private
    )
    YOUTUBE_UPLOAD_DEFAULT_CATEGORY: str = (
        "22"  # Default category ID (22 = People & Blogs)
    )
    YOUTUBE_UPLOAD_DEFAULT_TAGS: str = (
        ""  # Default tags for uploaded videos, separated by comma
    )
    YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION: str = (
        "Uploaded by AIM"  # Default description for uploaded videos
    )
    YOUTUBE_UPLOAD_DEFAULT_TITLE: str = (
        ""  # Default title template (empty = use filename)
    )

    # Advanced YouTube API Settings
    YOUTUBE_UPLOAD_DEFAULT_LANGUAGE: str = (
        "en"  # Default language for video metadata (ISO 639-1 code)
    )
    YOUTUBE_UPLOAD_DEFAULT_LICENSE: str = (
        "youtube"  # License: youtube (standard) or creativeCommon
    )
    YOUTUBE_UPLOAD_EMBEDDABLE: bool = (
        True  # Allow video to be embedded on other websites
    )
    YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE: bool = (
        True  # Allow public to see video statistics
    )
    YOUTUBE_UPLOAD_MADE_FOR_KIDS: bool = (
        False  # Mark videos as made for kids (COPPA compliance)
    )
    YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS: bool = (
        True  # Notify subscribers when video is uploaded
    )
    YOUTUBE_UPLOAD_LOCATION_DESCRIPTION: str = ""  # Location description for videos
    YOUTUBE_UPLOAD_RECORDING_DATE: str = (
        ""  # Recording date (YYYY-MM-DD format, empty = upload date)
    )

    YOUTUBE_UPLOAD_AUTO_LEVELS: bool = False  # Auto-enhance video levels
    YOUTUBE_UPLOAD_STABILIZE: bool = False  # Auto-stabilize shaky videos

    # Compression Settings
    COMPRESSION_ENABLED: bool = False
    COMPRESSION_PRIORITY: int = 4
    COMPRESSION_DELETE_ORIGINAL: bool = True

    # Video Compression Settings
    COMPRESSION_VIDEO_ENABLED: bool = False
    COMPRESSION_VIDEO_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_VIDEO_CRF: str = "none"
    COMPRESSION_VIDEO_CODEC: str = "none"
    COMPRESSION_VIDEO_TUNE: str = "none"
    COMPRESSION_VIDEO_PIXEL_FORMAT: str = "none"
    COMPRESSION_VIDEO_BITDEPTH: str = "none"
    COMPRESSION_VIDEO_BITRATE: str = "none"
    COMPRESSION_VIDEO_RESOLUTION: str = "none"
    COMPRESSION_VIDEO_FORMAT: str = (
        "none"  # Output format for video compression (e.g., mp4, mkv)
    )

    # Audio Compression Settings
    COMPRESSION_AUDIO_ENABLED: bool = False
    COMPRESSION_AUDIO_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_AUDIO_CODEC: str = "none"
    COMPRESSION_AUDIO_BITRATE: str = "none"
    COMPRESSION_AUDIO_CHANNELS: str = "none"
    COMPRESSION_AUDIO_BITDEPTH: str = "none"
    COMPRESSION_AUDIO_FORMAT: str = (
        "none"  # Output format for audio compression (e.g., mp3, aac)
    )

    # Image Compression Settings
    COMPRESSION_IMAGE_ENABLED: bool = False
    COMPRESSION_IMAGE_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_IMAGE_QUALITY: str = "none"
    COMPRESSION_IMAGE_RESIZE: str = "none"
    COMPRESSION_IMAGE_FORMAT: str = (
        "none"  # Output format for image compression (e.g., jpg, png)
    )

    # Document Compression Settings
    COMPRESSION_DOCUMENT_ENABLED: bool = False
    COMPRESSION_DOCUMENT_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_DOCUMENT_DPI: str = "none"
    COMPRESSION_DOCUMENT_FORMAT: str = (
        "none"  # Output format for document compression (e.g., pdf)
    )

    # Subtitle Compression Settings
    COMPRESSION_SUBTITLE_ENABLED: bool = False
    COMPRESSION_SUBTITLE_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_SUBTITLE_ENCODING: str = "none"
    COMPRESSION_SUBTITLE_FORMAT: str = (
        "none"  # Output format for subtitle compression (e.g., srt)
    )

    # Archive Compression Settings
    COMPRESSION_ARCHIVE_ENABLED: bool = False
    COMPRESSION_ARCHIVE_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_ARCHIVE_LEVEL: str = "none"
    COMPRESSION_ARCHIVE_METHOD: str = "none"
    COMPRESSION_ARCHIVE_FORMAT: str = (
        "none"  # Output format for archive compression (e.g., zip, 7z)
    )
    COMPRESSION_ARCHIVE_PASSWORD: str = "none"  # Password for archive protection
    COMPRESSION_ARCHIVE_ALGORITHM: str = "none"  # Archive algorithm (e.g., 7z, zip)

    # Trim Settings
    TRIM_ENABLED: bool = False
    TRIM_PRIORITY: int = 5
    TRIM_START_TIME: str = "00:00:00"
    TRIM_END_TIME: str = ""
    TRIM_DELETE_ORIGINAL: bool = False

    # Video Trim Settings
    TRIM_VIDEO_ENABLED: bool = False
    TRIM_VIDEO_CODEC: str = "none"  # none, copy, libx264, etc.
    TRIM_VIDEO_PRESET: str = "none"  # none, fast, medium, slow
    TRIM_VIDEO_FORMAT: str = (
        "none"  # Output format for video trimming (e.g., mp4, mkv)
    )

    # Audio Trim Settings
    TRIM_AUDIO_ENABLED: bool = False
    TRIM_AUDIO_CODEC: str = "none"  # none, copy, aac, etc.
    TRIM_AUDIO_PRESET: str = "none"  # none, fast, medium, slow
    TRIM_AUDIO_FORMAT: str = (
        "none"  # Output format for audio trimming (e.g., mp3, aac)
    )

    # Image Trim Settings
    TRIM_IMAGE_ENABLED: bool = False
    TRIM_IMAGE_QUALITY: int = 90
    TRIM_IMAGE_FORMAT: str = (
        "none"  # Output format for image trimming (e.g., jpg, png)
    )

    # Document Trim Settings
    TRIM_DOCUMENT_ENABLED: bool = False
    TRIM_DOCUMENT_START_PAGE: str = "1"  # Starting page number for document trimming
    TRIM_DOCUMENT_END_PAGE: str = (
        ""  # Ending page number for document trimming (empty for last page)
    )
    TRIM_DOCUMENT_QUALITY: int = 90
    TRIM_DOCUMENT_FORMAT: str = (
        "none"  # Output format for document trimming (e.g., pdf)
    )

    # Subtitle Trim Settings
    TRIM_SUBTITLE_ENABLED: bool = False
    TRIM_SUBTITLE_ENCODING: str = "none"
    TRIM_SUBTITLE_FORMAT: str = (
        "none"  # Output format for subtitle trimming (e.g., srt)
    )

    # Archive Trim Settings
    TRIM_ARCHIVE_ENABLED: bool = False
    TRIM_ARCHIVE_FORMAT: str = (
        "none"  # Output format for archive trimming (e.g., zip, 7z)
    )

    # Extract Settings
    EXTRACT_ENABLED: bool = False
    EXTRACT_PRIORITY: int = 6
    EXTRACT_DELETE_ORIGINAL: bool = True

    # Video Extract Settings
    EXTRACT_VIDEO_ENABLED: bool = False
    EXTRACT_VIDEO_CODEC: str = "none"
    EXTRACT_VIDEO_FORMAT: str = (
        "none"  # Output format for video extraction (e.g., mp4, mkv)
    )
    EXTRACT_VIDEO_INDEX: int | None = None
    EXTRACT_VIDEO_QUALITY: str = (
        "none"  # Quality setting for video extraction (e.g., crf value)
    )
    EXTRACT_VIDEO_PRESET: str = (
        "none"  # Preset for video encoding (e.g., medium, slow)
    )
    EXTRACT_VIDEO_BITRATE: str = "none"  # Bitrate for video encoding (e.g., 5M)
    EXTRACT_VIDEO_RESOLUTION: str = (
        "none"  # Resolution for video extraction (e.g., 1920x1080)
    )
    EXTRACT_VIDEO_FPS: str = "none"  # Frame rate for video extraction (e.g., 30)

    # Audio Extract Settings
    EXTRACT_AUDIO_ENABLED: bool = False
    EXTRACT_AUDIO_CODEC: str = "none"
    EXTRACT_AUDIO_FORMAT: str = (
        "none"  # Output format for audio extraction (e.g., mp3, aac)
    )
    EXTRACT_AUDIO_INDEX: int | None = None
    EXTRACT_AUDIO_BITRATE: str = "none"  # Bitrate for audio encoding (e.g., 320k)
    EXTRACT_AUDIO_CHANNELS: str = "none"  # Number of audio channels (e.g., 2)
    EXTRACT_AUDIO_SAMPLING: str = "none"  # Sampling rate for audio (e.g., 48000)
    EXTRACT_AUDIO_VOLUME: str = "none"  # Volume adjustment for audio (e.g., 1.5)

    # Subtitle Extract Settings
    EXTRACT_SUBTITLE_ENABLED: bool = False
    EXTRACT_SUBTITLE_CODEC: str = "none"
    EXTRACT_SUBTITLE_FORMAT: str = (
        "none"  # Output format for subtitle extraction (e.g., srt, ass)
    )
    EXTRACT_SUBTITLE_INDEX: int | None = None
    EXTRACT_SUBTITLE_LANGUAGE: str = (
        "none"  # Language code for subtitle extraction (e.g., eng)
    )
    EXTRACT_SUBTITLE_ENCODING: str = (
        "none"  # Character encoding for subtitles (e.g., UTF-8)
    )
    EXTRACT_SUBTITLE_FONT: str = (
        "none"  # Font for subtitles (for formats that support it)
    )
    EXTRACT_SUBTITLE_FONT_SIZE: str = "none"  # Font size for subtitles

    # Attachment Extract Settings
    EXTRACT_ATTACHMENT_ENABLED: bool = False
    EXTRACT_ATTACHMENT_FORMAT: str = (
        "none"  # Output format for attachment extraction (e.g., png, jpg)
    )
    EXTRACT_ATTACHMENT_INDEX: int | None = None
    EXTRACT_ATTACHMENT_FILTER: str = (
        "none"  # Filter for attachment extraction (e.g., *.ttf)
    )

    # Extract Quality Settings
    EXTRACT_MAINTAIN_QUALITY: bool = True

    # Remove Settings
    REMOVE_ENABLED: bool = False
    REMOVE_PRIORITY: int = 8
    REMOVE_DELETE_ORIGINAL: bool = True
    REMOVE_METADATA: bool = False
    REMOVE_MAINTAIN_QUALITY: bool = True

    # Video Remove Settings
    REMOVE_VIDEO_ENABLED: bool = False
    REMOVE_VIDEO_CODEC: str = "none"
    REMOVE_VIDEO_FORMAT: str = "none"
    REMOVE_VIDEO_INDEX: int | None = None
    REMOVE_VIDEO_QUALITY: str = "none"
    REMOVE_VIDEO_PRESET: str = "none"
    REMOVE_VIDEO_BITRATE: str = "none"
    REMOVE_VIDEO_RESOLUTION: str = "none"
    REMOVE_VIDEO_FPS: str = "none"

    # Audio Remove Settings
    REMOVE_AUDIO_ENABLED: bool = False
    REMOVE_AUDIO_CODEC: str = "none"
    REMOVE_AUDIO_FORMAT: str = "none"
    REMOVE_AUDIO_INDEX: int | None = None
    REMOVE_AUDIO_BITRATE: str = "none"
    REMOVE_AUDIO_CHANNELS: str = "none"
    REMOVE_AUDIO_SAMPLING: str = "none"
    REMOVE_AUDIO_VOLUME: str = "none"

    # Subtitle Remove Settings
    REMOVE_SUBTITLE_ENABLED: bool = False
    REMOVE_SUBTITLE_CODEC: str = "none"
    REMOVE_SUBTITLE_FORMAT: str = "none"
    REMOVE_SUBTITLE_INDEX: int | None = None
    REMOVE_SUBTITLE_LANGUAGE: str = "none"
    REMOVE_SUBTITLE_ENCODING: str = "none"
    REMOVE_SUBTITLE_FONT: str = "none"
    REMOVE_SUBTITLE_FONT_SIZE: str = "none"

    # Attachment Remove Settings
    REMOVE_ATTACHMENT_ENABLED: bool = False
    REMOVE_ATTACHMENT_FORMAT: str = "none"
    REMOVE_ATTACHMENT_INDEX: int | None = None
    REMOVE_ATTACHMENT_FILTER: str = "none"

    # Add Settings
    ADD_ENABLED: bool = False
    ADD_PRIORITY: int = 7
    ADD_DELETE_ORIGINAL: bool = True
    ADD_PRESERVE_TRACKS: bool = False
    ADD_REPLACE_TRACKS: bool = False

    # Video Add Settings
    ADD_VIDEO_ENABLED: bool = False
    ADD_VIDEO_CODEC: str = "copy"
    ADD_VIDEO_INDEX: int | None = None
    ADD_VIDEO_QUALITY: str = "none"
    ADD_VIDEO_PRESET: str = "none"
    ADD_VIDEO_BITRATE: str = "none"
    ADD_VIDEO_RESOLUTION: str = "none"
    ADD_VIDEO_FPS: str = "none"

    # Audio Add Settings
    ADD_AUDIO_ENABLED: bool = False
    ADD_AUDIO_CODEC: str = "copy"
    ADD_AUDIO_INDEX: int | None = None
    ADD_AUDIO_BITRATE: str = "none"
    ADD_AUDIO_CHANNELS: str = "none"
    ADD_AUDIO_SAMPLING: str = "none"
    ADD_AUDIO_VOLUME: str = "none"

    # Subtitle Add Settings
    ADD_SUBTITLE_ENABLED: bool = False
    ADD_SUBTITLE_CODEC: str = "copy"
    ADD_SUBTITLE_INDEX: int | None = None
    ADD_SUBTITLE_LANGUAGE: str = "none"
    ADD_SUBTITLE_ENCODING: str = "none"
    ADD_SUBTITLE_FONT: str = "none"
    ADD_SUBTITLE_FONT_SIZE: str = "none"
    ADD_SUBTITLE_HARDSUB_ENABLED: bool = False

    # Attachment Add Settings
    ADD_ATTACHMENT_ENABLED: bool = False
    ADD_ATTACHMENT_INDEX: int | None = None
    ADD_ATTACHMENT_MIMETYPE: str = "none"

    # Swap Settings
    SWAP_ENABLED: bool = False
    SWAP_PRIORITY: int = 6
    SWAP_REMOVE_ORIGINAL: bool = False

    # Audio Swap Settings
    SWAP_AUDIO_ENABLED: bool = False
    SWAP_AUDIO_USE_LANGUAGE: bool = True
    SWAP_AUDIO_LANGUAGE_ORDER: str = "eng,hin"
    SWAP_AUDIO_INDEX_ORDER: str = "0,1"

    # Video Swap Settings
    SWAP_VIDEO_ENABLED: bool = False
    SWAP_VIDEO_USE_LANGUAGE: bool = True
    SWAP_VIDEO_LANGUAGE_ORDER: str = "eng,hin"
    SWAP_VIDEO_INDEX_ORDER: str = "0,1"

    # Subtitle Swap Settings
    SWAP_SUBTITLE_ENABLED: bool = False
    SWAP_SUBTITLE_USE_LANGUAGE: bool = True
    SWAP_SUBTITLE_LANGUAGE_ORDER: str = "eng,hin"
    SWAP_SUBTITLE_INDEX_ORDER: str = "0,1"

    # Convert Settings
    CONVERT_ENABLED: bool = False
    CONVERT_PRIORITY: int = 3
    CONVERT_DELETE_ORIGINAL: bool = True

    # Video Convert Settings
    CONVERT_VIDEO_ENABLED: bool = False
    CONVERT_VIDEO_FORMAT: str = "none"
    CONVERT_VIDEO_CODEC: str = "none"
    CONVERT_VIDEO_QUALITY: str = "none"
    CONVERT_VIDEO_CRF: int = 0
    CONVERT_VIDEO_PRESET: str = "none"
    CONVERT_VIDEO_MAINTAIN_QUALITY: bool = True
    CONVERT_VIDEO_RESOLUTION: str = "none"
    CONVERT_VIDEO_FPS: str = "none"

    # Audio Convert Settings
    CONVERT_AUDIO_ENABLED: bool = False
    CONVERT_AUDIO_FORMAT: str = "none"
    CONVERT_AUDIO_CODEC: str = "none"
    CONVERT_AUDIO_BITRATE: str = "none"
    CONVERT_AUDIO_CHANNELS: int = 0
    CONVERT_AUDIO_SAMPLING: int = 0
    CONVERT_AUDIO_VOLUME: float = 0.0

    # Subtitle Convert Settings
    CONVERT_SUBTITLE_ENABLED: bool = False
    CONVERT_SUBTITLE_FORMAT: str = "none"
    CONVERT_SUBTITLE_ENCODING: str = "none"
    CONVERT_SUBTITLE_LANGUAGE: str = "none"

    # Document Convert Settings
    CONVERT_DOCUMENT_ENABLED: bool = False
    CONVERT_DOCUMENT_FORMAT: str = "none"
    CONVERT_DOCUMENT_QUALITY: int = 0
    CONVERT_DOCUMENT_DPI: int = 0

    # Archive Convert Settings
    CONVERT_ARCHIVE_ENABLED: bool = False
    CONVERT_ARCHIVE_FORMAT: str = "none"
    CONVERT_ARCHIVE_LEVEL: int = 0
    CONVERT_ARCHIVE_METHOD: str = "none"

    # Watermark Settings
    WATERMARK_ENABLED: bool = False
    WATERMARK_KEY: str = ""
    WATERMARK_POSITION: str = "none"
    WATERMARK_SIZE: int = 0
    WATERMARK_COLOR: str = "none"
    WATERMARK_FONT: str = "none"
    WATERMARK_PRIORITY: int = 2
    WATERMARK_THREADING: bool = True
    WATERMARK_THREAD_NUMBER: int = 4
    WATERMARK_QUALITY: str = "none"
    WATERMARK_SPEED: str = "none"
    WATERMARK_OPACITY: float = 0.0
    WATERMARK_REMOVE_ORIGINAL: bool = True

    # Audio Watermark Settings
    AUDIO_WATERMARK_VOLUME: float = 0.0
    AUDIO_WATERMARK_INTERVAL: int = 0

    # Subtitle Watermark Settings
    SUBTITLE_WATERMARK_STYLE: str = "none"
    SUBTITLE_WATERMARK_INTERVAL: int = 0

    # Image Watermark Settings
    IMAGE_WATERMARK_ENABLED: bool = False
    IMAGE_WATERMARK_PATH: str = ""
    IMAGE_WATERMARK_SCALE: int = 10
    IMAGE_WATERMARK_OPACITY: float = 1.0
    IMAGE_WATERMARK_POSITION: str = "bottom_right"

    # Merge Settings
    MERGE_ENABLED: bool = False
    MERGE_PRIORITY: int = 1
    MERGE_THREADING: bool = True
    MERGE_THREAD_NUMBER: int = 4
    CONCAT_DEMUXER_ENABLED: bool = True
    FILTER_COMPLEX_ENABLED: bool = False

    # Output formats
    MERGE_OUTPUT_FORMAT_VIDEO: str = "none"
    MERGE_OUTPUT_FORMAT_AUDIO: str = "none"
    MERGE_OUTPUT_FORMAT_IMAGE: str = "none"
    MERGE_OUTPUT_FORMAT_DOCUMENT: str = "none"
    MERGE_OUTPUT_FORMAT_SUBTITLE: str = "none"

    # Video settings
    MERGE_VIDEO_CODEC: str = "none"
    MERGE_VIDEO_QUALITY: str = "none"
    MERGE_VIDEO_PRESET: str = "none"
    MERGE_VIDEO_CRF: str = "none"
    MERGE_VIDEO_PIXEL_FORMAT: str = "none"
    MERGE_VIDEO_TUNE: str = "none"
    MERGE_VIDEO_FASTSTART: bool = False

    # Audio settings
    MERGE_AUDIO_CODEC: str = "none"
    MERGE_AUDIO_BITRATE: str = "none"
    MERGE_AUDIO_CHANNELS: str = "none"
    MERGE_AUDIO_SAMPLING: str = "none"
    MERGE_AUDIO_VOLUME: str = "none"

    # Image settings
    MERGE_IMAGE_MODE: str = "none"
    MERGE_IMAGE_COLUMNS: str = "none"
    MERGE_IMAGE_QUALITY: int = 0
    MERGE_IMAGE_DPI: str = "none"
    MERGE_IMAGE_RESIZE: str = "none"
    MERGE_IMAGE_BACKGROUND: str = "none"

    # Subtitle settings
    MERGE_SUBTITLE_ENCODING: str = "none"
    MERGE_SUBTITLE_FONT: str = "none"
    MERGE_SUBTITLE_FONT_SIZE: str = "none"
    MERGE_SUBTITLE_FONT_COLOR: str = "none"
    MERGE_SUBTITLE_BACKGROUND: str = "none"

    # Document settings
    MERGE_DOCUMENT_PAPER_SIZE: str = "none"
    MERGE_DOCUMENT_ORIENTATION: str = "none"
    MERGE_DOCUMENT_MARGIN: str = "none"

    # General settings
    MERGE_REMOVE_ORIGINAL: bool = True
    MERGE_METADATA_TITLE: str = "none"
    MERGE_METADATA_AUTHOR: str = "none"
    MERGE_METADATA_COMMENT: str = "none"

    # Resource Management Settings
    PIL_MEMORY_LIMIT: int = (
        1024  # Reduced from 2048MB to 1024MB for better memory management
    )

    # Auto Restart Settings - Optimized for better resource management
    AUTO_RESTART_ENABLED: bool = False  # Disabled by default for better stability
    AUTO_RESTART_INTERVAL: int = (
        48  # Increased to 48 hours to reduce restart frequency
    )

    # Garbage Collection Settings
    GC_ENABLED: bool = False  # Enable/disable garbage collection completely
    GC_INTERVAL: int = 60  # Minimum interval between GC operations in seconds
    GC_THRESHOLD_MB: int = 150  # Memory threshold in MB to trigger GC
    GC_AGGRESSIVE_MODE: bool = False  # Enable aggressive GC by default

    # Bulk Operation Settings
    BULK_ENABLED: bool = True  # Enable/disable bulk operations (-b flag)

    # Task Monitoring Settings - Optimized for reduced resource usage
    TASK_MONITOR_ENABLED: bool = False  # Disabled by default for better performance
    TASK_MONITOR_INTERVAL: int = 120  # Increased to 2 minutes to reduce CPU usage
    TASK_MONITOR_CONSECUTIVE_CHECKS: int = 10  # Reduced from 20 to save memory
    TASK_MONITOR_SPEED_THRESHOLD: int = 50  # in KB/s
    TASK_MONITOR_ELAPSED_THRESHOLD: int = 3600  # in seconds (1 hour)
    TASK_MONITOR_ETA_THRESHOLD: int = 86400  # in seconds (24 hours)
    TASK_MONITOR_WAIT_TIME: int = 900  # Increased to 15 minutes to reduce overhead
    TASK_MONITOR_COMPLETION_THRESHOLD: int = 86400  # in seconds (24 hours)
    TASK_MONITOR_CPU_HIGH: int = 85  # Reduced threshold for better responsiveness
    TASK_MONITOR_CPU_LOW: int = 50  # Reduced threshold
    TASK_MONITOR_MEMORY_HIGH: int = (
        70  # Reduced threshold for better memory management
    )
    TASK_MONITOR_MEMORY_LOW: int = 50  # Reduced threshold

    # Limits Settings
    STORAGE_THRESHOLD: float = 0  # GB
    TORRENT_LIMIT: float = 0  # GB
    DIRECT_LIMIT: float = 0  # GB
    YTDLP_LIMIT: float = 0  # GB
    GDRIVE_LIMIT: float = 0  # GB
    CLONE_LIMIT: float = 0  # GB
    MEGA_LIMIT: float = 0  # GB
    LEECH_LIMIT: float = 0  # GB
    JD_LIMIT: float = 0  # GB
    NZB_LIMIT: float = 0  # GB
    ZOTIFY_LIMIT: float = 0  # GB
    GALLERY_DL_LIMIT: float = 0  # GB
    PLAYLIST_LIMIT: int = 0  # Number of videos
    DAILY_TASK_LIMIT: int = 0  # Number of tasks per day
    DAILY_MIRROR_LIMIT: float = 0  # GB per day
    DAILY_LEECH_LIMIT: float = 0  # GB per day
    USER_MAX_TASKS: int = 0  # Maximum concurrent tasks per user
    USER_TIME_INTERVAL: int = 0  # Seconds between tasks
    BOT_MAX_TASKS: int = (
        0  # Maximum number of concurrent tasks the bot can handle (0 = unlimited)
    )
    STATUS_UPDATE_INTERVAL: int = 3  # Status update interval in seconds (minimum 2)
    STATUS_LIMIT: int = 10  # Number of tasks to display in status message
    SEARCH_LIMIT: int = (
        0  # Maximum number of search results to display (0 = unlimited)
    )
    SHOW_CLOUD_LINK: bool = True  # Show cloud links in upload completion message

    # Truecaller API Settings
    TRUECALLER_API_URL: str = ""

    # Multi-link Settings
    MULTI_LINK_ENABLED: bool = True

    # Same Directory Settings
    SAME_DIR_ENABLED: bool = True

    # Mirror Settings
    MIRROR_ENABLED: bool = True

    # Leech Settings
    LEECH_ENABLED: bool = True

    # YT-DLP Settings
    YTDLP_ENABLED: bool = True

    # Torrent Settings
    TORRENT_ENABLED: bool = True
    TORRENT_SEARCH_ENABLED: bool = True

    # NZB Settings
    NZB_ENABLED: bool = True
    NZB_SEARCH_ENABLED: bool = True

    # JDownloader Settings
    JD_ENABLED: bool = True

    # Hyper Download Settings
    HYPERDL_ENABLED: bool = True

    # Media Search Settings
    MEDIA_SEARCH_ENABLED: bool = True

    # TMDB API Settings
    TMDB_API_KEY: str = ""
    TMDB_ENABLED: bool = True
    TMDB_LANGUAGE: str = "en-US"
    TMDB_REGION: str = "US"

    # Cat API Settings
    CAT_API_KEY: str = ""  # The Cat API key for enhanced features

    # Auto Thumbnail Settings
    AUTO_THUMBNAIL: bool = False  # Enable/disable auto thumbnail from IMDB/TMDB

    # Rclone Settings
    RCLONE_ENABLED: bool = True

    # Archive Operation Settings
    ARCHIVE_FLAGS_ENABLED: bool = True

    # AI Settings
    AI_ENABLED: bool = True  # Master toggle for AI functionality

    # Default AI Model (replaces separate provider and model configs)
    DEFAULT_AI_MODEL: str = "gpt-4o-mini"  # Use most reliable model as default - All supported models: gpt-4o, gpt-4o-mini, gpt-4, gpt-3.5-turbo, o1-preview, o1-mini, claude-3.5-sonnet, claude-3-sonnet, claude-3-haiku, claude-3-opus, claude-2.1, gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash-exp, mixtral-8x7b-32768, llama-3.1-70b-versatile, llama-3.1-8b-instant, llama2-70b-4096, vertex-gemini-1.5-pro, vertex-gemini-1.5-flash, vertex-claude-3-sonnet, vertex-claude-3-haiku, whisper-1, mistral, deepseek

    # GPT/OpenAI Settings
    OPENAI_API_KEY: str = ""
    OPENAI_API_URL: str = "https://api.openai.com/v1/chat/completions"
    OPENAI_MODELS: str = (
        "gpt-3.5-turbo,gpt-4,gpt-4-turbo,gpt-4o,gpt-4o-mini,o1-preview,o1-mini"
    )

    # Claude/Anthropic Settings
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_API_URL: str = "https://api.anthropic.com/v1/messages"
    CLAUDE_MODELS: str = (
        "claude-2.1,claude-3-haiku,claude-3-sonnet,claude-3.5-sonnet,claude-3-opus"
    )

    # Gemini/Google AI Settings
    GOOGLE_AI_API_KEY: str = ""
    GOOGLE_AI_API_URL: str = (
        "https://generativelanguage.googleapis.com/v1beta/models"
    )
    GEMINI_MODELS: str = "gemini-1.5-pro,gemini-1.5-flash,gemini-2.0-flash-exp"

    # Vertex AI Settings
    VERTEX_PROJECT_ID: str = ""
    VERTEX_LOCATION: str = "us-central1"
    VERTEX_MODELS: str = (
        "gemini-1.5-pro,gemini-1.5-flash,claude-3-sonnet,claude-3-haiku"
    )

    # Groq Settings
    GROQ_API_KEY: str = ""
    GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_MODELS: str = "mixtral-8x7b-32768,llama2-70b-4096,llama-3.1-70b-versatile,llama-3.1-8b-instant"

    # Legacy AI Settings (for backward compatibility)
    MISTRAL_API_URL: str = ""
    DEEPSEEK_API_URL: str = ""

    # AI Feature Settings
    AI_STREAMING_ENABLED: bool = False  # Enable streaming responses
    AI_PLUGINS_ENABLED: bool = True  # Enable plugin system
    AI_MULTIMODAL_ENABLED: bool = True  # Enable image/voice/document processing
    AI_CONVERSATION_HISTORY: bool = True  # Enable conversation history
    AI_MAX_HISTORY_LENGTH: int = 50  # Maximum conversation history length
    AI_QUESTION_PREDICTION: bool = True  # Enable follow-up question generation
    AI_GROUP_TOPIC_MODE: bool = True  # Enable topic-based conversations in groups
    AI_INLINE_MODE_ENABLED: bool = True  # Enable inline mode support
    AI_AUTO_LANGUAGE_DETECTION: bool = True  # Auto-detect user language
    AI_DEFAULT_LANGUAGE: str = "en"  # Default language (en, zh, ru)
    AI_CONVERSATION_MODE: str = "assistant"  # Default conversation mode
    AI_LANGUAGE: str = "en"  # User's preferred AI language

    # AI Plugin Settings
    AI_WEB_SEARCH_ENABLED: bool = True  # Enable web search plugin
    AI_URL_SUMMARIZATION_ENABLED: bool = True  # Enable URL summarization
    AI_ARXIV_ENABLED: bool = True  # Enable ArXiv paper plugin
    AI_CODE_INTERPRETER_ENABLED: bool = True  # Enable code execution
    AI_IMAGE_GENERATION_ENABLED: bool = True  # Enable DALL-E image generation
    AI_VOICE_TRANSCRIPTION_ENABLED: bool = True  # Enable Whisper voice transcription

    # New ChatGPT-Telegram-Bot Features
    AI_DOCUMENT_PROCESSING_ENABLED: bool = (
        True  # Enable document processing (PDF, text)
    )
    AI_FOLLOW_UP_QUESTIONS_ENABLED: bool = (
        True  # Enable automatic follow-up questions
    )
    AI_CONVERSATION_EXPORT_ENABLED: bool = True  # Enable conversation export
    AI_TYPEWRITER_EFFECT_ENABLED: bool = (
        True  # Enable typewriter effect for streaming
    )
    AI_CONTEXT_PRUNING_ENABLED: bool = True  # Enable intelligent context pruning

    # AI Performance Settings
    AI_MAX_TOKENS: int = 4096  # Maximum tokens per response
    AI_TEMPERATURE: float = 0.7  # Response creativity (0.0-2.0)
    AI_TIMEOUT: int = 60  # Request timeout in seconds
    AI_MAX_CONCURRENT_REQUESTS: int = 10  # Max concurrent AI requests
    AI_RATE_LIMIT_PER_USER: int = 50  # Max requests per user per hour

    # AI Budget Settings
    AI_DAILY_TOKEN_LIMIT: int = 0  # Daily token limit per user (0 = unlimited)
    AI_MONTHLY_TOKEN_LIMIT: int = 0  # Monthly token limit per user (0 = unlimited)
    AI_DAILY_COST_LIMIT: float = 0.0  # Daily cost limit per user (0.0 = unlimited)
    AI_MONTHLY_COST_LIMIT: float = (
        0.0  # Monthly cost limit per user (0.0 = unlimited)
    )

    # AI Model Grouping
    AI_MODEL_GROUPS: str = "GPT:gpt-3.5-turbo,gpt-4,gpt-4o|Claude:claude-3-haiku,claude-3-sonnet|Gemini:gemini-1.5-pro,gemini-1.5-flash|Groq:mixtral-8x7b-32768,llama2-70b-4096|Others:mistral,deepseek"

    # Shortener Settings
    SHORTENER_MIN_TIME: int = 10  # Minimum time in seconds for shortener to process

    # File2Link Settings
    FILE2LINK_ENABLED: bool = True
    FILE2LINK_BIN_CHANNEL: int = 0  # Channel to store files for File2Link streaming
    FILE2LINK_BASE_URL: str = (
        ""  # Base URL for File2Link streaming (separate from main BASE_URL)
    )
    FILE2LINK_ALLOWED_TYPES: str = (
        "video,audio,document,photo,animation,voice,video_note"
    )

    # Command Suffix Settings
    CORRECT_CMD_SUFFIX: str = ""  # Comma-separated list of allowed command suffixes
    WRONG_CMD_WARNINGS_ENABLED: bool = (
        False  # Enable/disable warnings for wrong command suffixes
    )

    # QuickInfo Settings
    QUICKINFO_ENABLED: bool = False  # Enable/disable QuickInfo feature

    # Extra Modules Settings
    IMDB_ENABLED: bool = True  # Enable/disable IMDB functionality
    TRUECALLER_ENABLED: bool = True  # Enable/disable Truecaller functionality

    # Encoding/Decoding Settings
    ENCODING_ENABLED: bool = True  # Enable/disable encoding functionality
    DECODING_ENABLED: bool = True  # Enable/disable decoding functionality

    # VirusTotal Settings
    VT_API_KEY: str = ""
    VT_API_TIMEOUT: int = 500
    VT_ENABLED: bool = False
    VT_MAX_FILE_SIZE: int = 32 * 1024 * 1024  # 32MB default limit

    # Phish Directory Settings
    PHISH_DIRECTORY_API_URL: str = "https://api.phish.directory"
    PHISH_DIRECTORY_ENABLED: bool = True
    PHISH_DIRECTORY_TIMEOUT: int = 30
    PHISH_DIRECTORY_API_KEY: str = ""

    # WOT (Web of Trust) Settings
    WOT_API_URL: str = "https://scorecard.api.mywot.com"
    WOT_ENABLED: bool = True
    WOT_TIMEOUT: int = 30
    WOT_API_KEY: str = ""
    WOT_USER_ID: str = ""

    # AbuseIPDB Settings
    ABUSEIPDB_API_URL: str = "https://api.abuseipdb.com/api/v2"
    ABUSEIPDB_ENABLED: bool = True
    ABUSEIPDB_TIMEOUT: int = 30
    ABUSEIPDB_API_KEY: str = ""
    ABUSEIPDB_MAX_AGE_DAYS: int = 90

    # Trace.moe Settings
    TRACE_MOE_API_KEY: str = ""  # trace.moe API key for enhanced search quota
    TRACE_MOE_ENABLED: bool = True  # Enable/disable trace.moe functionality
    TRACE_MOE_CUT_BORDERS: bool = True  # Enable border cutting for better accuracy
    TRACE_MOE_VIDEO_PREVIEW: bool = True  # Enable video preview in results
    TRACE_MOE_MUTE_PREVIEW: bool = False  # Mute video previews by default
    TRACE_MOE_SKIP_PREVIEW: bool = False  # Skip video preview entirely
    TRACE_MOE_MAX_FILE_SIZE: int = (
        25 * 1024 * 1024
    )  # 25MB max file size for trace.moe (API limit)

    # Weather Settings - OpenWeatherMap API
    WEATHER_ENABLED: bool = True  # Enable/disable weather functionality
    OPENWEATHER_API_KEY: str = ""  # OpenWeatherMap API key
    WEATHER_PLACE: str = "London,UK"  # Default weather location
    AUTO_WEATHER: bool = True  # Enable/disable automatic daily weather updates
    WEATHER_RISK_NOTIFICATIONS: bool = (
        True  # Enable/disable weather risk notifications to owner
    )
    WEATHER_UNITS: str = "metric"  # Units: standard, metric, imperial
    WEATHER_LANGUAGE: str = "en"  # Language code for weather descriptions
    WEATHER_UPDATE_TIME: str = (
        "08:00"  # Time for daily weather updates (HH:MM format)
    )
    WEATHER_TIMEZONE: str = "UTC"  # Timezone for weather updates

    # Advanced Weather Features
    WEATHER_SHOW_MAPS: bool = True  # Enable/disable weather maps
    WEATHER_SHOW_AIR_QUALITY: bool = True  # Enable/disable air quality data
    WEATHER_SHOW_FIRE_INDEX: bool = (
        False  # Enable/disable fire weather index (requires special access)
    )
    WEATHER_HISTORICAL_DAYS: int = (
        7  # Days of historical data to show (requires paid plan)
    )
    WEATHER_FORECAST_DAYS: int = 5  # Days of forecast to show (max 5 for free plan)
    WEATHER_MAP_ZOOM: int = 10  # Default zoom level for weather maps
    WEATHER_IMAGE_QUALITY: str = "high"  # Image quality: low, medium, high
    WEATHER_CACHE_DURATION: int = 600  # Cache duration in seconds (10 minutes)

    # Weather Alert Settings
    WEATHER_ALERT_TEMPERATURE_HIGH: float = (
        35.0  # High temperature alert threshold (Celsius)
    )
    WEATHER_ALERT_TEMPERATURE_LOW: float = (
        -10.0
    )  # Low temperature alert threshold (Celsius)
    WEATHER_ALERT_WIND_SPEED: float = 15.0  # High wind speed alert threshold (m/s)
    WEATHER_ALERT_VISIBILITY: int = 1000  # Low visibility alert threshold (meters)
    WEATHER_ALERT_AQI: int = 3  # Air quality alert threshold (1-5 scale)
    WEATHER_ALERT_FIRE_DANGER: int = (
        3  # Fire weather index alert threshold (0-5 scale)
    )

    # Weather Map Settings
    WEATHER_MAP_LAYERS: list = [
        "temp_new",  # Temperature
        "precipitation_new",  # Precipitation
        "pressure_new",  # Pressure
        "wind_new",  # Wind
        "clouds_new",  # Clouds
    ]  # Available weather map layers
    WEATHER_MAP_OPACITY: float = 0.6  # Map layer opacity (0.0-1.0)
    WEATHER_USE_ADVANCED_MAPS: bool = (
        False  # Use Weather Maps 2.0 (requires paid plan)
    )
    WEATHER_USE_HOURLY_MAPS: bool = (
        False  # Use Weather Maps 2.0 with 1-hour step (requires paid plan)
    )

    # Air Quality Settings
    WEATHER_AQI_FORECAST_DAYS: int = 4  # Days of air quality forecast (max 4)
    WEATHER_AQI_HISTORICAL_DAYS: int = 7  # Days of historical air quality data
    WEATHER_SHOW_POLLUTANTS: list = [
        "co",
        "no",
        "no2",
        "o3",
        "so2",
        "pm2_5",
        "pm10",
        "nh3",
    ]  # Pollutants to display

    # Premium Features Settings
    WEATHER_HOURLY_FORECAST_HOURS: int = (
        96  # Hours of hourly forecast (max 96 for 4 days)
    )
    WEATHER_STATISTICAL_DATA: bool = (
        False  # Enable statistical weather data (requires paid plan)
    )
    WEATHER_ROAD_RISK_API: bool = False  # Enable road risk API (requires paid plan)
    WEATHER_SOLAR_IRRADIANCE: bool = (
        False  # Enable solar irradiance data (requires paid plan)
    )

    # Weather Data Sources
    WEATHER_BACKUP_SOURCES: bool = (
        True  # Use backup weather data sources if primary fails
    )
    WEATHER_DATA_VALIDATION: bool = True  # Validate weather data before displaying
    WEATHER_METRIC_CONVERSION: bool = (
        True  # Auto-convert units based on user location
    )

    # Enhanced NSFW Detection Settings
    NSFW_DETECTION_ENABLED: bool = True  # Master toggle for NSFW detection
    NSFW_DETECTION_SENSITIVITY: str = "moderate"  # strict, moderate, permissive
    NSFW_KEYWORD_DETECTION: bool = True  # Enable enhanced keyword detection
    NSFW_VISUAL_DETECTION: bool = False  # Enable AI-powered visual analysis
    NSFW_AUDIO_DETECTION: bool = False  # Enable audio content analysis
    NSFW_FUZZY_MATCHING: bool = False  # Enable fuzzy keyword matching (disabled by default to reduce false positives)
    NSFW_LEETSPEAK_DETECTION: bool = True  # Enable leetspeak detection
    NSFW_MULTI_LANGUAGE: bool = (
        False  # Enable multi-language keyword support (disabled by default)
    )
    NSFW_CONFIDENCE_THRESHOLD: float = (
        0.7  # Minimum confidence for NSFW detection (0.0-1.0)
    )
    NSFW_CACHE_DURATION: int = 3600  # Cache detection results for 1 hour
    NSFW_CONTEXT_CHECKING: bool = (
        True  # Enable context-aware detection to reduce false positives
    )
    NSFW_MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB max file size for analysis
    NSFW_VIDEO_ANALYSIS: bool = True  # Enable video frame analysis
    NSFW_VIDEO_FRAME_COUNT: int = 5  # Number of frames to extract for analysis
    NSFW_FRAME_QUALITY: int = (
        2  # Frame extraction quality (1-5, higher = better quality)
    )
    NSFW_AUDIO_ANALYSIS: bool = True  # Enable audio content analysis
    NSFW_SUBTITLE_ANALYSIS: bool = True  # Enable subtitle text analysis

    # NSFW Visual Analysis API Settings
    NSFW_GOOGLE_VISION_API_KEY: str = ""  # Google Cloud Vision API key
    NSFW_AWS_ACCESS_KEY: str = ""  # AWS Rekognition access key
    NSFW_AWS_SECRET_KEY: str = ""  # AWS Rekognition secret key
    NSFW_AWS_REGION: str = "us-east-1"  # AWS region
    NSFW_AZURE_ENDPOINT: str = ""  # Azure Content Moderator endpoint
    NSFW_AZURE_KEY: str = ""  # Azure Content Moderator key
    NSFW_OPENAI_API_KEY: str = ""  # OpenAI API key for vision analysis

    # NSFW Text Analysis API Settings
    NSFW_PERSPECTIVE_API_KEY: str = ""  # Google Perspective API key
    NSFW_OPENAI_MODERATION: bool = False  # Use OpenAI moderation API

    # NSFW Behavior and Logging
    NSFW_LOG_DETECTIONS: bool = True  # Log NSFW detections for analysis
    NSFW_STORE_METADATA: bool = True  # Store detection metadata in database
    NSFW_AUTO_DELETE: bool = False  # Auto-delete detected NSFW content
    NSFW_NOTIFY_ADMINS: bool = True  # Notify admins of NSFW detections

    # Terabox Proxy Settings
    TERABOX_PROXY: str = "https://wdzone-terabox-api.vercel.app/"

    # Pastebin API Settings
    PASTEBIN_API_KEY: str = ""  # Pastebin Developer API Key
    PASTEBIN_ENABLED: bool = False  # Enable/disable Pastebin functionality

    # Bitly API Settings
    BITLY_ACCESS_TOKEN: str = ""  # Bitly API access token for link shortening
    BITLY_GROUP_GUID: str = ""  # Optional Bitly group GUID for organization

    # TinyURL API Settings
    TINYURL_API_TOKEN: str = ""  # TinyURL API token for link shortening

    HEROKU_APP_NAME: str = ""
    HEROKU_API_KEY: str = ""

    # Branding Settings
    CREDIT: str = (
        "Powered by @aimmirror"  # Credit text shown in status messages and RSS feeds
    )
    OWNER_THUMB: str = "https://graph.org/file/80b7fb095063a18f9e232.jpg"  # Default thumbnail URL for owner

    @classmethod
    def _convert(cls, key, value):
        expected_type = type(getattr(cls, key))
        if value is None:
            return None

        if key in ("LEECH_DUMP_CHAT", "FORWARD_SOURCE", "FORWARD_DESTINATION"):
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]

            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return []
                try:
                    evaluated = ast.literal_eval(value)
                    if isinstance(evaluated, list):
                        return [str(v).strip() for v in evaluated if str(v).strip()]
                except (ValueError, SyntaxError):
                    pass
                return [value] if value else []

            raise TypeError(f"{key} should be list[str], got {type(value).__name__}")

        # Special handling for MEDIA_TOOLS_ENABLED
        if key == "MEDIA_TOOLS_ENABLED":
            # If it's a string with commas, it's a list of enabled tools
            if isinstance(value, str) and "," in value:
                return value  # Keep it as a comma-separated string
            # If it's a single tool name as a string
            if (
                isinstance(value, str)
                and value.strip()
                and value.strip().lower()
                not in {"true", "1", "yes", "false", "0", "no"}
            ):
                return value  # Keep it as a string
            # If it's a boolean True or string that evaluates to True
            if value is True or (
                isinstance(value, str)
                and str(value).strip().lower() in {"true", "1", "yes"}
            ):
                # List of all available media tools
                all_tools = [
                    "watermark",
                    "merge",
                    "convert",
                    "compression",
                    "trim",
                    "extract",
                    "remove",
                    "add",
                    "swap",
                    "metadata",
                    "xtra",
                    "sample",
                    "screenshot",
                ]
                # Sort the tools to maintain consistent order
                all_tools.sort()
                return ",".join(all_tools)
            # If it's False or any other falsy value
            return False

        # Special handling for MEDIA_SEARCH_CHATS
        if key == "MEDIA_SEARCH_CHATS":
            # If value is None, return an empty list
            if value is None:
                return []

            # If it's already a list, check if all elements are integers
            if isinstance(value, list):
                # Convert all elements to integers if possible
                try:
                    return [
                        int(chat_id)
                        for chat_id in value
                        if str(chat_id).lstrip("-").isdigit()
                    ]
                except (ValueError, TypeError):
                    # If conversion fails, return the original list
                    return value

            # If it's a string, split by comma and convert to integers
            if isinstance(value, str):
                if not value.strip():
                    return []
                try:
                    # Split by comma and convert each value to integer
                    chat_ids = value.split(",")
                    return [
                        int(chat_id.strip())
                        for chat_id in chat_ids
                        if chat_id.strip().lstrip("-").isdigit()
                    ]
                except (ValueError, TypeError):
                    # If conversion fails, return an empty list
                    return []

            # For any other type, return an empty list
            return []

        if isinstance(value, expected_type):
            return value

        if expected_type is bool:
            return str(value).strip().lower() in {"true", "1", "yes"}

        if expected_type in [list, dict]:
            # Handle empty values for list and dict types
            if value == "" or value is None:
                # Return empty list or dict based on expected type
                return [] if expected_type is list else {}

            if not isinstance(value, str):
                raise TypeError(
                    f"{key} should be {expected_type.__name__}, got {type(value).__name__}"
                )

            if not value:
                return expected_type()

            try:
                evaluated = ast.literal_eval(value)
                if isinstance(evaluated, expected_type):
                    return evaluated
                raise TypeError
            except (ValueError, SyntaxError, TypeError) as e:
                # For list-type configs, return an empty list on error
                if key in (
                    "LEECH_DUMP_CHAT",
                    "FORWARD_SOURCE",
                    "FORWARD_DESTINATION",
                ):
                    return []
                raise TypeError(
                    f"{key} should be {expected_type.__name__}, got invalid string: {value}"
                ) from e

        # Special handling for "none" or empty string values in numeric fields
        if isinstance(value, str) and expected_type in (int, float):
            # Convert string values to appropriate numeric types
            value_lower = value.lower()
            if value_lower == "none" or value == "":
                # For numeric types, return a default value (0) when "none" or empty string is specified
                return 0

            # Try to convert the string to the expected numeric type
            try:
                return expected_type(value)
            except (ValueError, TypeError):
                # If conversion fails, log a warning and return a default value
                logger.warning(
                    f"Failed to convert '{value}' to {expected_type.__name__} for {key}, using default value 0"
                )
                return 0

        try:
            return expected_type(value)
        except (ValueError, TypeError) as exc:
            raise TypeError(
                f"Invalid type for {key}: expected {expected_type}, got {type(value)}"
            ) from exc

    @classmethod
    def _normalize_value(cls, key: str, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()

        if key == "DEFAULT_UPLOAD" and value not in ["gd", "yt", "mg", "rc", "ddl"]:
            return "gd"

        if key in {"BASE_URL", "RCLONE_SERVE_URL", "INDEX_URL"}:
            return value.strip("/")

        if key == "USENET_SERVERS" and (
            not isinstance(value, list)
            or not value
            or not isinstance(value[0], dict)
            or not value[0].get("host")
        ):
            return []

        return value

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get configuration value with caching for improved performance"""
        return _config_cache.get(key, default)

    @classmethod
    def set(cls, key: str, value: Any):
        if not hasattr(cls, key):
            raise KeyError(f"{key} is not a valid configuration key.")
        converted = cls._convert(key, value)
        normalized = cls._normalize_value(key, converted)
        setattr(cls, key, normalized)

        # Update cache when config is changed
        _config_cache.set(key, normalized)

    @classmethod
    @lru_cache(maxsize=512)
    def get_cached(cls, key: str) -> Any:
        """Get configuration value with LRU caching (for frequently accessed configs)"""
        return getattr(cls, key, None)

    @classmethod
    def get_with_fallback(cls, key: str, *fallback_keys, default: Any = None) -> Any:
        """Get configuration with fallback keys and caching"""
        # Try primary key first
        value = _config_cache.get(key, None)
        if value is not None:
            return value

        # Try fallback keys
        for fallback_key in fallback_keys:
            value = _config_cache.get(fallback_key, None)
            if value is not None:
                return value

        return default

    @classmethod
    def get_all(cls) -> dict:
        return {key: getattr(cls, key) for key in sorted(cls.__annotations__)}

    @classmethod
    def load(cls):
        try:
            settings = import_module("config")
        except ModuleNotFoundError:
            return

        # Clear cache before loading new configuration
        _config_cache.invalidate()

        for attr in dir(settings):
            if not cls._is_valid_config_attr(settings, attr):
                continue

            value = getattr(settings, attr)
            if not value:
                continue

            try:
                cls.set(attr, value)
            except Exception as e:
                logger.warning(f"Skipping config '{attr}' due to error: {e}")

        logger.info("Configuration loaded and cached successfully")

    @classmethod
    def load_dict(cls, config_dict: dict[str, Any]):
        for key, value in config_dict.items():
            try:
                cls.set(key, value)
            except Exception as e:
                logger.warning(f"Skipping config '{key}' due to error: {e}")

    @classmethod
    def invalidate_cache(cls, key: str | None = None):
        """Invalidate configuration cache"""
        _config_cache.invalidate(key)
        if key is None:
            # Also clear LRU cache
            cls.get_cached.cache_clear()

    @classmethod
    def get_cache_stats(cls) -> dict:
        """Get configuration cache performance statistics"""
        return _config_cache.get_stats()

    @classmethod
    def log_cache_stats(cls):
        """Log configuration cache performance statistics"""
        _config_cache.log_stats()

    @classmethod
    def _is_valid_config_attr(cls, module, attr: str) -> bool:
        return (
            not attr.startswith("__")
            and not callable(getattr(module, attr))
            and attr in cls.__annotations__
        )


class SystemEnv:
    @classmethod
    def load(cls):
        env_overrides = 0
        for key in Config.__annotations__:
            env_value = os.getenv(key)
            if env_value is not None:
                try:
                    Config.set(key, env_value)
                    env_overrides += 1
                except Exception as e:
                    logger.warning(f"Env override failed for '{key}': {e}")

        if env_overrides > 0:
            logger.info(f"Applied {env_overrides} environment variable overrides")


# Optimized configuration access functions for frequently used configs
def get_config_cached(key: str, default: Any = None) -> Any:
    """
    High-performance configuration access function.
    Use this for frequently accessed configuration values.
    """
    return Config.get(key, default)


def get_config_bool(key: str, default: bool = False) -> bool:
    """Get boolean configuration with caching"""
    value = Config.get(key, default)
    return bool(value) if value is not None else default


def get_config_int(key: str, default: int = 0) -> int:
    """Get integer configuration with caching"""
    value = Config.get(key, default)
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def get_config_str(key: str, default: str = "") -> str:
    """Get string configuration with caching"""
    value = Config.get(key, default)
    return str(value) if value is not None else default


def get_config_list(key: str, default: list | None = None) -> list:
    """Get list configuration with caching"""
    if default is None:
        default = []
    value = Config.get(key, default)
    return value if isinstance(value, list) else default


def get_config_dict(key: str, default: dict | None = None) -> dict:
    """Get dictionary configuration with caching"""
    if default is None:
        default = {}
    value = Config.get(key, default)
    return value if isinstance(value, dict) else default


# Performance monitoring function
def log_config_performance():
    """Log configuration cache performance statistics"""
    Config.log_cache_stats()


# Cache warming function for startup optimization
def warm_config_cache():
    """Pre-load frequently accessed configurations into cache"""
    # Most frequently accessed configs based on codebase analysis
    frequently_accessed = [
        "BOT_TOKEN",
        "DATABASE_URL",
        "OWNER_ID",
        "TELEGRAM_API",
        "TELEGRAM_HASH",
        "RSS_ENABLED",
        "RSS_JOB_INTERVAL",
        "GC_ENABLED",
        "GC_INTERVAL",
        "SCHEDULED_DELETION_ENABLED",
        "TASK_MONITOR_ENABLED",
        "DEFAULT_UPLOAD",
        "QUEUE_ALL",
        "QUEUE_DOWNLOAD",
        "QUEUE_UPLOAD",
        "LEECH_SPLIT_SIZE",
        "TORRENT_TIMEOUT",
        "CMD_SUFFIX",
        "AUTHORIZED_CHATS",
        "SUDO_USERS",
        "LOG_CHAT_ID",
        "INCOMPLETE_TASK_NOTIFIER",
    ]

    # Pre-load these configs into cache
    for config_key in frequently_accessed:
        Config.get(config_key)

    logger.info(
        f"Warmed configuration cache with {len(frequently_accessed)} frequently accessed configs"
    )
