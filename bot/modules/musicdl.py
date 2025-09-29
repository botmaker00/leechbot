#!/usr/bin/env python3
"""
🎵 Minimal MusicDL - Clean implementation using CLI methods
Supports Tidal (tidal-dl-ng), Qobuz (qobuz-dl), and Apple Music (gamdl) with proper integration

Features:
- CLI-based downloads (minimal complexity)
- Format conversion support (-fm flag)
- Quality selection (-q flag)
- Lyrics and cover art download
- Task manager integration
- Status tracking
- Inline search support
- Multi-platform support (Tidal, Qobuz, Apple Music)
"""

import asyncio
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from aiofiles.os import path as aiopath

# Add deezspot to path for proper imports
DEEZSPOT_PATH = os.path.join(os.getcwd(), 'deezspot')
if DEEZSPOT_PATH not in sys.path:
    sys.path.append(DEEZSPOT_PATH)

# Import qobuz-dl components for module-based usage
try:
    from qobuz_dl.bundle import Bundle
    from qobuz_dl.core import QobuzDL

    QOBUZ_MODULE_AVAILABLE = True
except ImportError:
    QOBUZ_MODULE_AVAILABLE = False

# Import deezspot components for Spotify and Deezer downloads
try:
    from deezspot.deezloader import DeeLogin
    from deezspot.deezloader.deezer_settings import qualities as deezer_qualities
    from deezspot.exceptions import (
        AlbumNotFound,
        BadCredentials,
        InvalidLink,
        NoDataApi,
        NoRightOnMedia,
        QualityNotFound,
        QuotaExceeded,
        TrackNotFound,
    )
    from deezspot.libutils.utils import get_ids, link_is_valid, what_kind
    from deezspot.spotloader import SpoLogin
    from deezspot.spotloader.spotify_settings import qualities as spotify_qualities

    DEEZSPOT_AVAILABLE = True
except ImportError:
    DEEZSPOT_AVAILABLE = False

import contextlib
from pyrogram.enums import ParseMode


from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath
from bot.helper.ext_utils.status_utils import (
    get_readable_file_size,
    get_readable_time,
)

# Bot imports
from bot.helper.listeners.task_listener import TaskListener
from bot.helper.telegram_helper.message_utils import send_message

# Global session cache to avoid re-authentication (NO TIMEOUT - persistent until restart)
_qobuz_dl_session_cache = None  # QobuzDL instance cache
_qobuz_streamrip_session_cache = None  # Streamrip QobuzClient cache
_tidal_session_cache = None  # Tidal session cache
_zotify_session_cache = None  # Zotify session cache
_apple_session_cache = None  # Apple Music session cache (if needed)

# Session cache status tracking (no timeout, persistent until restart)
_session_cache_status = {
    'qobuz_dl': False,
    'qobuz_streamrip': False,
    'tidal': False,
    'zotify': False,
    'apple': False
}


class MusicDownloadStatus:
    """Fallback status class for music downloads"""

    def __init__(self, listener):
        self.listener = listener
        self._size = getattr(listener, "size", 0)

    def gid(self):
        """Return task GID"""
        return getattr(self.listener, "gid", "")

    def name(self):
        """Return task name"""
        return getattr(self.listener, "name", "Music Download")

    def size(self):
        """Return task size"""
        return self._size

    def status(self):
        """Return task status"""
        if hasattr(self.listener, "is_completed") and self.listener.is_completed:
            return "Completed"
        if hasattr(self.listener, "is_failed") and self.listener.is_failed:
            return "Failed"
        return "Downloading"

    def progress(self):
        """Return progress percentage"""
        if hasattr(self.listener, "is_completed") and self.listener.is_completed:
            return "100%"
        if hasattr(self.listener, "is_failed") and self.listener.is_failed:
            return "0%"
        return "50%"  # Assume 50% during download

    def speed(self):
        """Return download speed"""
        return "0B/s"  # Music downloads don't track speed

    def eta(self):
        """Return estimated time of arrival"""
        return "-"

    def downloaded_bytes(self):
        """Return downloaded bytes"""
        return (
            getattr(self.listener, "size", 0)
            if hasattr(self.listener, "is_completed") and self.listener.is_completed
            else 0
        )

    def task(self):
        """Return task reference"""
        return self

    async def cancel_task(self):
        """Cancel the task"""
        self.listener.is_cancelled = True
        LOGGER.info(
            f"Music download task cancelled: {getattr(self.listener, 'uid', 'unknown')}"
        )


class DownloadConfig:
    """Download configuration for music downloads with platform-specific options"""

    def __init__(self, flags: dict | None = None):
        # Basic settings with flag overrides
        self.format = flags.get("format", "flac") if flags else "flac"
        self.quality = flags.get("quality", "27") if flags else "27"  # Max quality
        self.lyric_file = True
        self.embed_art = flags.get("embed_art", True) if flags else True
        self.output_dir = None

        # Dolby Atmos support (Tidal only)
        self.dolby_atmos = (
            flags.get("dolby_atmos", Config.TIDAL_DOLBY_ATMOS_ENABLED)
            if flags
            else Config.TIDAL_DOLBY_ATMOS_ENABLED
        )

        # Qobuz-specific options with flag overrides (priority: flags > config > defaults)
        if flags:
            # Use flags first, then config defaults
            self.qobuz_no_fallback = flags.get("no_fallback", Config.QOBUZ_NO_FALLBACK)
            self.qobuz_albums_only = flags.get("albums_only", Config.QOBUZ_ALBUMS_ONLY)
            self.qobuz_smart_discography = flags.get(
                "smart_discography", Config.QOBUZ_SMART_DISCOGRAPHY
            )
            self.qobuz_og_cover = flags.get("og_cover", Config.QOBUZ_OG_COVER)
            self.qobuz_no_cover = flags.get("no_cover", Config.QOBUZ_NO_COVER)
            self.qobuz_no_m3u = flags.get("no_m3u", Config.QOBUZ_NO_M3U)
            self.qobuz_no_db = flags.get("no_database", Config.QOBUZ_NO_DATABASE)
            self.qobuz_folder_format = flags.get(
                "folder_format", Config.QOBUZ_FOLDER_FORMAT
            )
            self.qobuz_track_format = flags.get(
                "track_format", Config.QOBUZ_TRACK_FORMAT
            )
            self.qobuz_limit = flags.get("limit", Config.QOBUZ_DEFAULT_LIMIT)
        else:
            # Use config defaults
            self.qobuz_no_fallback = Config.QOBUZ_NO_FALLBACK
            self.qobuz_albums_only = Config.QOBUZ_ALBUMS_ONLY
            self.qobuz_smart_discography = Config.QOBUZ_SMART_DISCOGRAPHY
            self.qobuz_og_cover = Config.QOBUZ_OG_COVER
            self.qobuz_no_cover = Config.QOBUZ_NO_COVER
            self.qobuz_no_m3u = Config.QOBUZ_NO_M3U
            self.qobuz_no_db = Config.QOBUZ_NO_DATABASE
            self.qobuz_folder_format = Config.QOBUZ_FOLDER_FORMAT
            self.qobuz_track_format = Config.QOBUZ_TRACK_FORMAT
            self.qobuz_limit = Config.QOBUZ_DEFAULT_LIMIT

        # Additional qobuz-dl modes and options from documentation
        self.qobuz_mode = (
            "dl"  # Mode: dl (download), fun (interactive), lucky (search)
        )
        self.qobuz_lucky_limit = 1  # -n: Number of results for lucky mode
        self.qobuz_lucky_type = (
            "album"  # --type: Type for lucky mode (album/track/artist)
        )
        self.qobuz_interactive_limit = 20  # -l: Limit for interactive mode results
        self.qobuz_reset_config = False  # -r: Reset config file
        self.qobuz_purge_db = False  # -p: Purge downloaded-IDs database

        # Tidal-specific options with flag overrides (priority: flags > config > defaults)
        if flags:
            # Use flags first, then config defaults
            self.tidal_extract_flac = flags.get(
                "tidal_extract_flac", Config.TIDAL_EXTRACT_FLAC
            )
            self.tidal_lyrics_embed = flags.get(
                "tidal_lyrics_embed", Config.TIDAL_LYRICS_EMBED
            )
            self.tidal_lyrics_file = flags.get(
                "tidal_lyrics_file", Config.TIDAL_LYRICS_FILE
            )
            self.tidal_metadata_cover_embed = flags.get(
                "tidal_metadata_cover_embed", Config.TIDAL_METADATA_COVER_EMBED
            )
            self.tidal_cover_album_file = flags.get(
                "tidal_cover_album_file", Config.TIDAL_COVER_ALBUM_FILE
            )
            self.tidal_metadata_replay_gain = flags.get(
                "tidal_metadata_replay_gain", Config.TIDAL_METADATA_REPLAY_GAIN
            )
            self.tidal_skip_existing = flags.get(
                "tidal_skip_existing", Config.TIDAL_SKIP_EXISTING
            )
            self.tidal_playlist_create = flags.get(
                "tidal_playlist_create", Config.TIDAL_PLAYLIST_CREATE
            )
            self.tidal_video_download = flags.get(
                "tidal_video_download", Config.TIDAL_VIDEO_DOWNLOAD
            )
            self.tidal_downloads_concurrent_max = flags.get(
                "tidal_downloads_concurrent_max",
                Config.TIDAL_DOWNLOADS_CONCURRENT_MAX,
            )
            self.tidal_downloads_simultaneous_per_track_max = flags.get(
                "tidal_downloads_simultaneous_per_track_max",
                Config.TIDAL_DOWNLOADS_SIMULTANEOUS_PER_TRACK_MAX,
            )
            self.tidal_download_delay = flags.get(
                "tidal_download_delay", Config.TIDAL_DOWNLOAD_DELAY
            )
            self.tidal_download_delay_sec_min = flags.get(
                "tidal_download_delay_sec_min", Config.TIDAL_DOWNLOAD_DELAY_SEC_MIN
            )
            self.tidal_download_delay_sec_max = flags.get(
                "tidal_download_delay_sec_max", Config.TIDAL_DOWNLOAD_DELAY_SEC_MAX
            )
            self.tidal_symlink_to_track = flags.get(
                "tidal_symlink_to_track", Config.TIDAL_SYMLINK_TO_TRACK
            )
            self.tidal_video_convert_mp4 = flags.get(
                "tidal_video_convert_mp4", Config.TIDAL_VIDEO_CONVERT_MP4
            )
            self.tidal_metadata_cover_dimension = flags.get(
                "tidal_metadata_cover_dimension",
                Config.TIDAL_METADATA_COVER_DIMENSION,
            )
            self.tidal_quality_audio = flags.get(
                "tidal_quality_audio", Config.TIDAL_QUALITY_AUDIO
            )
            self.tidal_quality_video = flags.get(
                "tidal_quality_video", Config.TIDAL_QUALITY_VIDEO
            )
            self.tidal_format_album = flags.get(
                "tidal_format_album", Config.TIDAL_FORMAT_ALBUM
            )
            self.tidal_format_track = flags.get(
                "tidal_format_track", Config.TIDAL_FORMAT_TRACK
            )
            self.tidal_format_playlist = flags.get(
                "tidal_format_playlist", Config.TIDAL_FORMAT_PLAYLIST
            )
            self.tidal_format_mix = flags.get(
                "tidal_format_mix", Config.TIDAL_FORMAT_MIX
            )
            self.tidal_format_video = flags.get(
                "tidal_format_video", Config.TIDAL_FORMAT_VIDEO
            )
        else:
            # Use config defaults
            self.tidal_extract_flac = Config.TIDAL_EXTRACT_FLAC
            self.tidal_lyrics_embed = Config.TIDAL_LYRICS_EMBED
            self.tidal_lyrics_file = Config.TIDAL_LYRICS_FILE
            self.tidal_metadata_cover_embed = Config.TIDAL_METADATA_COVER_EMBED
            self.tidal_cover_album_file = Config.TIDAL_COVER_ALBUM_FILE
            self.tidal_metadata_replay_gain = Config.TIDAL_METADATA_REPLAY_GAIN
            self.tidal_skip_existing = Config.TIDAL_SKIP_EXISTING
            self.tidal_playlist_create = Config.TIDAL_PLAYLIST_CREATE
            self.tidal_video_download = Config.TIDAL_VIDEO_DOWNLOAD
            self.tidal_downloads_concurrent_max = (
                Config.TIDAL_DOWNLOADS_CONCURRENT_MAX
            )
            self.tidal_downloads_simultaneous_per_track_max = (
                Config.TIDAL_DOWNLOADS_SIMULTANEOUS_PER_TRACK_MAX
            )
            self.tidal_download_delay = Config.TIDAL_DOWNLOAD_DELAY
            self.tidal_download_delay_sec_min = Config.TIDAL_DOWNLOAD_DELAY_SEC_MIN
            self.tidal_download_delay_sec_max = Config.TIDAL_DOWNLOAD_DELAY_SEC_MAX
            self.tidal_symlink_to_track = Config.TIDAL_SYMLINK_TO_TRACK
            self.tidal_video_convert_mp4 = Config.TIDAL_VIDEO_CONVERT_MP4
            self.tidal_metadata_cover_dimension = (
                Config.TIDAL_METADATA_COVER_DIMENSION
            )
            self.tidal_quality_audio = Config.TIDAL_QUALITY_AUDIO
            self.tidal_quality_video = Config.TIDAL_QUALITY_VIDEO
            self.tidal_format_album = Config.TIDAL_FORMAT_ALBUM
            self.tidal_format_track = Config.TIDAL_FORMAT_TRACK
            self.tidal_format_playlist = Config.TIDAL_FORMAT_PLAYLIST
            self.tidal_format_mix = Config.TIDAL_FORMAT_MIX
            self.tidal_format_video = Config.TIDAL_FORMAT_VIDEO

        # Additional tidal-dl-ng options
        self.tidal_album_track_num_pad_min = (
            flags.get(
                "tidal_album_track_num_pad_min", Config.TIDAL_ALBUM_TRACK_NUM_PAD_MIN
            )
            if flags
            else Config.TIDAL_ALBUM_TRACK_NUM_PAD_MIN
        )

        # Tidal-dl-ng command modes from documentation
        self.tidal_command = "dl"  # Command: dl, dl_fav, login, logout, cfg, gui
        self.tidal_fav_type = (
            "tracks"  # dl_fav type: tracks, artists, albums, videos
        )

        # Apple Music (gamdl) options with flag overrides (priority: flags > config > defaults)
        if flags:
            # Use flags first, then config defaults
            self.apple_cookies_path = flags.get(
                "apple_cookies_path", Config.APPLE_COOKIES_PATH
            )
            self.apple_output_path = flags.get(
                "apple_output_path", Config.APPLE_OUTPUT_PATH
            )
            self.apple_temp_path = flags.get(
                "apple_temp_path", Config.APPLE_TEMP_PATH
            )
            self.apple_language = flags.get("apple_language", Config.APPLE_LANGUAGE)
            self.apple_log_level = flags.get(
                "apple_log_level", Config.APPLE_LOG_LEVEL
            )
            self.apple_disable_music_video_skip = flags.get(
                "apple_disable_music_video_skip", Config.APPLE_DISABLE_MUSIC_VIDEO_SKIP
            )
            self.apple_save_cover = flags.get(
                "apple_save_cover", Config.APPLE_SAVE_COVER
            )
            self.apple_overwrite = flags.get("apple_overwrite", Config.APPLE_OVERWRITE)
            self.apple_save_playlist = flags.get(
                "apple_save_playlist", Config.APPLE_SAVE_PLAYLIST
            )
            self.apple_synced_lyrics_only = flags.get(
                "apple_synced_lyrics_only", Config.APPLE_SYNCED_LYRICS_ONLY
            )
            self.apple_no_synced_lyrics = flags.get(
                "apple_no_synced_lyrics", Config.APPLE_NO_SYNCED_LYRICS
            )
            self.apple_no_exceptions = flags.get(
                "apple_no_exceptions", Config.APPLE_NO_EXCEPTIONS
            )
            self.apple_read_urls_as_txt = flags.get(
                "apple_read_urls_as_txt", Config.APPLE_READ_URLS_AS_TXT
            )
            self.apple_no_config_file = flags.get(
                "apple_no_config_file", Config.APPLE_NO_CONFIG_FILE
            )
            self.apple_codec_song = flags.get(
                "apple_codec_song", Config.APPLE_CODEC_SONG
            )
            self.apple_codec_music_video = flags.get(
                "apple_codec_music_video", Config.APPLE_CODEC_MUSIC_VIDEO
            )
            self.apple_synced_lyrics_format = flags.get(
                "apple_synced_lyrics_format", Config.APPLE_SYNCED_LYRICS_FORMAT
            )
            self.apple_cover_format = flags.get(
                "apple_cover_format", Config.APPLE_COVER_FORMAT
            )
            self.apple_cover_size = flags.get(
                "apple_cover_size", Config.APPLE_COVER_SIZE
            )
            self.apple_quality_post = flags.get(
                "apple_quality_post", Config.APPLE_QUALITY_POST
            )
            self.apple_download_mode = flags.get(
                "apple_download_mode", Config.APPLE_DOWNLOAD_MODE
            )
            self.apple_remux_mode = flags.get(
                "apple_remux_mode", Config.APPLE_REMUX_MODE
            )
            self.apple_remux_format_music_video = flags.get(
                "apple_remux_format_music_video",
                Config.APPLE_REMUX_FORMAT_MUSIC_VIDEO,
            )
        else:
            # Use config defaults
            self.apple_cookies_path = Config.APPLE_COOKIES_PATH
            self.apple_output_path = Config.APPLE_OUTPUT_PATH
            self.apple_temp_path = Config.APPLE_TEMP_PATH
            self.apple_language = Config.APPLE_LANGUAGE
            self.apple_log_level = Config.APPLE_LOG_LEVEL
            self.apple_disable_music_video_skip = Config.APPLE_DISABLE_MUSIC_VIDEO_SKIP
            self.apple_save_cover = Config.APPLE_SAVE_COVER
            self.apple_overwrite = Config.APPLE_OVERWRITE
            self.apple_save_playlist = Config.APPLE_SAVE_PLAYLIST
            self.apple_synced_lyrics_only = Config.APPLE_SYNCED_LYRICS_ONLY
            self.apple_no_synced_lyrics = Config.APPLE_NO_SYNCED_LYRICS
            self.apple_no_exceptions = Config.APPLE_NO_EXCEPTIONS
            self.apple_read_urls_as_txt = Config.APPLE_READ_URLS_AS_TXT
            self.apple_no_config_file = Config.APPLE_NO_CONFIG_FILE
            self.apple_codec_song = Config.APPLE_CODEC_SONG
            self.apple_codec_music_video = Config.APPLE_CODEC_MUSIC_VIDEO
            self.apple_synced_lyrics_format = Config.APPLE_SYNCED_LYRICS_FORMAT
            self.apple_cover_format = Config.APPLE_COVER_FORMAT
            self.apple_cover_size = Config.APPLE_COVER_SIZE
            self.apple_quality_post = Config.APPLE_QUALITY_POST
            self.apple_download_mode = Config.APPLE_DOWNLOAD_MODE
            self.apple_remux_mode = Config.APPLE_REMUX_MODE
            self.apple_remux_format_music_video = (
                Config.APPLE_REMUX_FORMAT_MUSIC_VIDEO
            )

        # Apple Music template settings
        self.apple_template_folder_album = (
            flags.get(
                "apple_template_folder_album", Config.APPLE_TEMPLATE_FOLDER_ALBUM
            )
            if flags
            else Config.APPLE_TEMPLATE_FOLDER_ALBUM
        )
        self.apple_template_folder_compilation = (
            flags.get(
                "apple_template_folder_compilation",
                Config.APPLE_TEMPLATE_FOLDER_COMPILATION,
            )
            if flags
            else Config.APPLE_TEMPLATE_FOLDER_COMPILATION
        )
        self.apple_template_file_single_disc = (
            flags.get(
                "apple_template_file_single_disc",
                Config.APPLE_TEMPLATE_FILE_SINGLE_DISC,
            )
            if flags
            else Config.APPLE_TEMPLATE_FILE_SINGLE_DISC
        )
        self.apple_template_file_multi_disc = (
            flags.get(
                "apple_template_file_multi_disc",
                Config.APPLE_TEMPLATE_FILE_MULTI_DISC,
            )
            if flags
            else Config.APPLE_TEMPLATE_FILE_MULTI_DISC
        )
        self.apple_template_folder_no_album = (
            flags.get(
                "apple_template_folder_no_album",
                Config.APPLE_TEMPLATE_FOLDER_NO_ALBUM,
            )
            if flags
            else Config.APPLE_TEMPLATE_FOLDER_NO_ALBUM
        )
        self.apple_template_file_no_album = (
            flags.get(
                "apple_template_file_no_album", Config.APPLE_TEMPLATE_FILE_NO_ALBUM
            )
            if flags
            else Config.APPLE_TEMPLATE_FILE_NO_ALBUM
        )
        self.apple_template_file_playlist = (
            flags.get(
                "apple_template_file_playlist", Config.APPLE_TEMPLATE_FILE_PLAYLIST
            )
            if flags
            else Config.APPLE_TEMPLATE_FILE_PLAYLIST
        )
        self.apple_template_date = (
            flags.get("apple_template_date", Config.APPLE_TEMPLATE_DATE)
            if flags
            else Config.APPLE_TEMPLATE_DATE
        )

        # Apple Music binary paths
        self.apple_ffmpeg_path = (
            flags.get("apple_ffmpeg_path", Config.APPLE_FFMPEG_PATH)
            if flags
            else Config.APPLE_FFMPEG_PATH
        )
        self.apple_mp4decrypt_path = (
            flags.get("apple_mp4decrypt_path", Config.APPLE_MP4DECRYPT_PATH)
            if flags
            else Config.APPLE_MP4DECRYPT_PATH
        )
        self.apple_mp4box_path = (
            flags.get("apple_mp4box_path", Config.APPLE_MP4BOX_PATH)
            if flags
            else Config.APPLE_MP4BOX_PATH
        )
        self.apple_nm3u8dlre_path = (
            flags.get("apple_nm3u8dlre_path", Config.APPLE_NM3U8DLRE_PATH)
            if flags
            else Config.APPLE_NM3U8DLRE_PATH
        )
        self.apple_wvd_path = (
            flags.get("apple_wvd_path", Config.APPLE_WVD_PATH)
            if flags
            else Config.APPLE_WVD_PATH
        )

        # Apple Music advanced settings
        self.apple_exclude_tags = (
            flags.get("apple_exclude_tags", Config.APPLE_EXCLUDE_TAGS)
            if flags
            else Config.APPLE_EXCLUDE_TAGS
        )
        self.apple_truncate = (
            flags.get("apple_truncate", Config.APPLE_TRUNCATE)
            if flags
            else Config.APPLE_TRUNCATE
        )

        # DeezSpot (Spotify & Deezer) options with flag overrides (priority: flags > config > defaults)
        if flags:
            # Deezer settings
            self.deezer_arl = flags.get(
                "deezer_arl", ""
            )  # Will be set from config if not in flags
            self.deezer_email = flags.get("deezer_email", "")
            self.deezer_password = flags.get("deezer_password", "")
            self.deezer_quality = flags.get(
                "deezer_quality", "FLAC"
            )  # MP3_128, MP3_320, FLAC
            self.deezer_tags_separator = flags.get("deezer_tags_separator", " / ")
            self.deezer_recursive_quality = flags.get(
                "deezer_recursive_quality", True
            )
            self.deezer_recursive_download = flags.get(
                "deezer_recursive_download", False
            )

            # Spotify settings
            self.spotify_credentials_path = flags.get(
                "spotify_credentials_path", "./credentials.json"
            )
            self.spotify_client_id = flags.get("spotify_client_id", "")
            self.spotify_client_secret = flags.get("spotify_client_secret", "")
            self.spotify_quality = flags.get(
                "spotify_quality", "VERY_HIGH"
            )  # NORMAL, HIGH, VERY_HIGH
            self.spotify_recursive_quality = flags.get(
                "spotify_recursive_quality", True
            )
            self.spotify_recursive_download = flags.get(
                "spotify_recursive_download", False
            )
            self.spotify_not_interface = flags.get("spotify_not_interface", False)
            self.spotify_method_save = flags.get("spotify_method_save", 1)
            self.spotify_make_zip = flags.get("spotify_make_zip", False)
        else:
            # Use config defaults from Config
            self.deezer_arl = Config.DEEZER_ARL
            self.deezer_email = Config.DEEZER_EMAIL
            self.deezer_password = Config.DEEZER_PASSWORD
            self.deezer_quality = Config.DEEZER_QUALITY
            self.deezer_tags_separator = Config.DEEZER_TAGS_SEPARATOR
            self.deezer_recursive_quality = Config.DEEZER_RECURSIVE_QUALITY
            self.deezer_recursive_download = Config.DEEZER_RECURSIVE_DOWNLOAD

            self.spotify_credentials_path = Config.SPOTIFY_CREDENTIALS_PATH
            self.spotify_client_id = Config.SPOTIFY_CLIENT_ID
            self.spotify_client_secret = Config.SPOTIFY_CLIENT_SECRET
            self.spotify_quality = Config.SPOTIFY_QUALITY
            self.spotify_recursive_quality = Config.SPOTIFY_RECURSIVE_QUALITY
            self.spotify_recursive_download = Config.SPOTIFY_RECURSIVE_DOWNLOAD
            self.spotify_not_interface = Config.SPOTIFY_NOT_INTERFACE
            self.spotify_method_save = Config.SPOTIFY_METHOD_SAVE
            self.spotify_make_zip = Config.SPOTIFY_MAKE_ZIP


class InlineMusicDownloadListener(TaskListener):
    """Special listener for inline downloads with real-time progress updates"""

    def __init__(
        self,
        message,
        config: DownloadConfig,
        platform: str,
        download_dir: str,
        is_leech: bool = True,
        inline_message=None,
        inline_query_id=None,
    ):
        # Initialize parent class
        super().__init__(message, is_leech)

        self.config = config
        self.platform = platform
        self.download_dir = download_dir
        self.inline_message = inline_message
        self.inline_query_id = inline_query_id
        self.start_time = time.time()
        self.last_update_time = 0

        # Set tool name for TaskListener
        self.tool = "musicdl_inline"

        # Set excluded_extensions for TaskListener
        excluded_extensions_str = Config.EXCLUDED_EXTENSIONS
        self.excluded_extensions = set()
        if excluded_extensions_str:
            self.excluded_extensions = {
                ext.strip().lower() for ext in excluded_extensions_str.split(",")
            }

    async def update_inline_progress(self, status_text: str, progress: float = 0):
        """Update inline message with progress"""
        try:
            from pyrogram.enums import ParseMode

            current_time = time.time()
            # Only update every 2 seconds to avoid rate limits
            if current_time - self.last_update_time < 2:
                return

            self.last_update_time = current_time

            if self.inline_message:
                await self.inline_message.edit_text(
                    status_text,
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            LOGGER.error(f"Error updating inline progress: {e}")


class MusicDownloadListener(TaskListener):
    """Unified listener for both Tidal and Qobuz downloads"""

    def __init__(
        self,
        message,
        config: DownloadConfig,
        platform: str,
        download_dir: str,
        is_leech: bool | None = None,
        inline_message=None,  # For inline message updates
    ):
        # Set message BEFORE calling super().__init__() because TaskConfig.__init__() needs it
        self.message = message
        super().__init__()

        self.config = config
        self.platform = platform.lower()
        self.download_dir = download_dir
        self.inline_message = inline_message  # Store inline message for progress updates

        # Override TaskConfig defaults with our specific values
        self.dir = download_dir  # Override default download directory
        self.name = f"MusicDL-{platform.upper()}"
        self.uid = f"{message.id}_{platform}_{int(time.time())}"

        # IMPORTANT: Set is_leech AFTER super().__init__() because TaskConfig.__init__()
        # sets self.is_leech = False by default, overriding our value
        # Default behavior: leech (upload to Telegram) for music downloads
        if is_leech is None:
            self.is_leech = True  # Default: leech to Telegram
        else:
            self.is_leech = is_leech  # Use specified value

        # Set up user tag for completion message "cc:" (following other listeners pattern)
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
        # Fallback: create tag from message user info
        elif message.from_user:
            if message.from_user.username:
                self.tag = f"@{message.from_user.username}"
            else:
                self.tag = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name or message.from_user.id}</a>"
        else:
            self.tag = (
                f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>"
            )

        # Set up_dest for leech (Telegram upload) following TaskConfig logic
        # This will be called asynchronously in on_download_complete
        self._upload_destination_setup_needed = True

        # Set additional properties that TaskListener might expect
        self.folder_name = ""  # No folder grouping for music downloads
        self.same_dir = {}  # No same directory handling
        self.seed = False  # No seeding for music downloads
        self.join = False  # No file joining needed
        self.excluded_extensions = []  # No excluded extensions
        self.size = 0  # Will be set after download
        self.is_file = False  # Will be determined later

        # Add all the missing attributes that TaskListener expects
        self.compression_enabled = False
        self.extract = False
        self.compress = False
        self.screen_shots = False
        self.convert_audio = False
        self.convert_video = False
        self.sample_video = False
        self.name_sub = ""
        self.ffmpeg_cmds = None
        self.up_dir = ""

        # Add all metadata attributes
        self.metadata_video_title = False
        self.metadata_video_author = False
        self.metadata_video_comment = False
        self.metadata_audio_title = False
        self.metadata_audio_author = False
        self.metadata_audio_comment = False
        self.metadata_subtitle_title = False
        self.metadata_subtitle_author = False
        self.metadata_subtitle_comment = False

        # Add more TaskConfig attributes
        self.select = False
        self.private_link = False
        self.stop_duplicate = False
        self.force_run = False
        self.force_download = False
        self.force_upload = False
        self.is_torrent = False
        self.as_med = False
        self.as_doc = False
        self.bot_trans = False
        self.user_trans = False
        self.progress = True
        self.chat_thread_id = None
        self.user_transmission = False
        self.hybrid_leech = False
        self.is_super_chat = False  # Music downloads don't use super chat
        self.thumbnail_layout = None  # No custom thumbnail layout for music
        self.screen_shots = 0  # No screenshots for music files
        self.subproc = None
        self.thumb = None
        self.files_to_proceed = []
        self.multi = 0
        self.max_split_size = 0
        self.proceed_count = 0

        # Status tracking
        self.processed_bytes = 0
        self.total_size = 0
        self.speed = 0
        self.eta = "N/A"
        self.status = "Initializing..."
        self.start_time = time.time()

        # Process tracking
        self.process = None
        self.is_completed = False
        self.is_failed = False
        self.downloaded_files = []

        # Status message for real-time updates
        self.status_message = None

        # Initialize all TaskConfig defaults to prevent AttributeError
        self._initialize_taskconfig_defaults()

    async def _setup_upload_destination(self):
        """Setup upload destination for both leech (Telegram) and mirror (rclone) operations"""
        try:
            from pyrogram.enums import ChatAction

            from bot.core.aeon_client import TgClient


            LOGGER.info(
                f"[DEBUG] Setting up upload destination for is_leech={self.is_leech}"
            )

            if self.is_leech:
                # LEECH MODE: Upload to Telegram
                # Start with empty up_dest and apply leech-specific logic
                self.up_dest = ""

                # Check for upload path mappings first
                if self.user_dict.get("UPLOAD_PATHS", False):
                    if self.up_dest in self.user_dict["UPLOAD_PATHS"]:
                        self.up_dest = self.user_dict["UPLOAD_PATHS"][self.up_dest]
                elif (
                    "UPLOAD_PATHS" not in self.user_dict
                    and Config.UPLOAD_PATHS
                    and self.up_dest in Config.UPLOAD_PATHS
                ):
                    self.up_dest = Config.UPLOAD_PATHS[self.up_dest]

                # For leech operations, set up_dest to leech dump chat
                if not self.up_dest:
                    leech_dump = Config.LEECH_DUMP_CHAT
                    if isinstance(leech_dump, list) and leech_dump:
                        self.up_dest = leech_dump[0]  # Use first dump chat
                    elif leech_dump:
                        self.up_dest = leech_dump
                    else:
                        # Fallback to current chat if no dump chat configured
                        self.up_dest = self.message.chat.id

                # Set transmission modes for leech
                self.user_transmission = (
                    Config.USER_TRANSMISSION and TgClient.IS_PREMIUM_USER
                )

                LOGGER.info(f"[DEBUG] Leech mode - up_dest set to: {self.up_dest}")

            else:
                # MIRROR MODE: Upload to cloud service
                # Follow the same logic as mirror_leech.py to respect DEFAULT_UPLOAD setting

                # Check user's DEFAULT_UPLOAD setting first, then fall back to global setting
                user_default_upload = self.user_dict.get(
                    "DEFAULT_UPLOAD", Config.DEFAULT_UPLOAD
                )

                LOGGER.info(
                    f"[DEBUG] User DEFAULT_UPLOAD setting: {user_default_upload}"
                )

                if user_default_upload == "gd":
                    self.up_dest = "gd"
                    LOGGER.info(
                        f"[DEBUG] Mirror mode - using Google Drive: {self.up_dest}"
                    )
                elif user_default_upload == "mg":
                    self.up_dest = "mg"
                    LOGGER.info(f"[DEBUG] Mirror mode - using Mega: {self.up_dest}")
                elif user_default_upload == "yt":
                    self.up_dest = "yt"
                    LOGGER.info(
                        f"[DEBUG] Mirror mode - using YouTube: {self.up_dest}"
                    )
                elif user_default_upload == "ddl":
                    self.up_dest = "ddl"
                    LOGGER.info(f"[DEBUG] Mirror mode - using DDL: {self.up_dest}")
                elif user_default_upload == "rc":
                    # For rclone, use the configured rclone path
                    rclone_path = Config.RCLONE_PATH
                    if rclone_path:
                        self.up_dest = rclone_path
                        LOGGER.info(
                            f"[DEBUG] Mirror mode - using rclone path: {self.up_dest}"
                        )
                    else:
                        # Fallback to Google Drive if rclone not configured
                        self.up_dest = "gd"
                        LOGGER.warning(
                            f"[DEBUG] Rclone not configured, falling back to Google Drive: {self.up_dest}"
                        )
                else:
                    # Default fallback to Google Drive
                    self.up_dest = "gd"
                    LOGGER.info(
                        f"[DEBUG] Mirror mode - using default Google Drive: {self.up_dest}"
                    )

                # For mirror operations, disable transmission modes
                self.user_transmission = False
                self.hybrid_leech = False

            # Process up_dest format (handle prefixes and special formats)
            # Only process these for leech mode (Telegram uploads)
            if self.is_leech and self.up_dest and not isinstance(self.up_dest, int):
                # Handle transmission mode prefixes
                if self.up_dest.startswith("b:"):
                    self.up_dest = self.up_dest.replace("b:", "", 1)
                    self.user_transmission = False
                    self.hybrid_leech = False
                elif self.up_dest.startswith("u:"):
                    self.up_dest = self.up_dest.replace("u:", "", 1)
                    self.user_transmission = TgClient.IS_PREMIUM_USER
                elif self.up_dest.startswith("h:"):
                    self.up_dest = self.up_dest.replace("h:", "", 1)
                    self.user_transmission = TgClient.IS_PREMIUM_USER
                    self.hybrid_leech = self.user_transmission

                # Handle chat thread format (chat_id|thread_id)
                if "|" in self.up_dest:
                    self.up_dest, self.chat_thread_id = [
                        int(x) if x.lstrip("-").isdigit() else x
                        for x in self.up_dest.split("|", 1)
                    ]
                elif self.up_dest.lstrip("-").isdigit():
                    self.up_dest = int(self.up_dest)
                elif self.up_dest.lower() == "pm":
                    self.up_dest = self.user_id

            # Validate chat access only for leech mode (Telegram uploads)
            if self.is_leech:
                # Validate chat access for user transmission
                if self.user_transmission:
                    try:
                        chat = await TgClient.user.get_chat(self.up_dest)
                    except Exception:
                        chat = None
                    if chat is None:
                        self.user_transmission = False
                        self.hybrid_leech = False
                        LOGGER.warning(
                            f"User transmission disabled - cannot access chat {self.up_dest}"
                        )

                # Validate chat access for bot transmission
                if not self.user_transmission or self.hybrid_leech:
                    try:
                        chat = await self.client.get_chat(self.up_dest)
                    except Exception:
                        chat = None
                    if chat is None:
                        if self.user_transmission:
                            self.hybrid_leech = False
                            LOGGER.warning(
                                f"Hybrid leech disabled - bot cannot access chat {self.up_dest}"
                            )
                        else:
                            # Fallback to user's PM if chat is not accessible
                            LOGGER.warning(
                                f"Chat {self.up_dest} not accessible, falling back to user PM"
                            )
                            self.up_dest = self.user_id
                    else:
                        # Test bot permissions by sending typing action
                        try:
                            await self.client.send_chat_action(
                                self.up_dest,
                                ChatAction.TYPING,
                            )
                        except Exception as e:
                            LOGGER.warning(
                                f"Bot lacks permissions in chat {self.up_dest}: {e}"
                            )
                            # Fallback to user's PM
                            self.up_dest = self.user_id

            # Final validation - ensure up_dest is correct format for each mode
            if self.is_leech:
                # For leech mode, ensure up_dest is a valid chat ID (integer)
                if not isinstance(self.up_dest, int):
                    try:
                        self.up_dest = int(self.up_dest)
                    except (ValueError, TypeError):
                        LOGGER.warning(
                            f"Invalid up_dest format: {self.up_dest}, falling back to user PM"
                        )
                        self.up_dest = self.user_id
            # For mirror mode, ensure up_dest is a valid upload destination (string)
            elif not isinstance(self.up_dest, str) or not self.up_dest:
                LOGGER.warning(
                    f"Invalid upload destination: {self.up_dest}, using default Google Drive"
                )
                self.up_dest = "gd"

            LOGGER.info(f"[DEBUG] Upload destination set to: {self.up_dest}")
            LOGGER.info(f"[DEBUG] User transmission: {self.user_transmission}")
            LOGGER.info(
                f"[DEBUG] Hybrid leech: {getattr(self, 'hybrid_leech', False)}"
            )

        except Exception as e:
            LOGGER.error(f"[DEBUG] Error setting up upload destination: {e}")
            # Fallback based on mode
            if self.is_leech:
                # Fallback to user's PM for leech mode
                self.up_dest = self.user_id
                self.user_transmission = False
                self.hybrid_leech = False
            else:
                # Fallback to default Google Drive for mirror mode
                self.up_dest = "gd"
                self.user_transmission = False
                self.hybrid_leech = False

    async def on_download_complete(self):
        """Override to add debug logging, upload progress tracking, and ensure upload works"""
        # Check for cancellation first
        if self.is_cancelled:
            LOGGER.info(
                f"[DEBUG] Download was cancelled, skipping upload for UID: {self.uid}"
            )
            # Update status message for cancellation
            if self.status_message:
                try:
                    from pyrogram.enums import ParseMode

                    await self.status_message.edit_text(
                        "❌ <b>Download Cancelled</b>", parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass
            return

        LOGGER.info(
            f"[DEBUG] MusicDownloadListener.on_download_complete() called for UID: {self.uid}"
        )
        LOGGER.info(f"[DEBUG] is_leech: {self.is_leech}, dir: {self.dir}")
        LOGGER.info(
            f"[DEBUG] folder_name: {getattr(self, 'folder_name', 'NOT_SET')}"
        )
        LOGGER.info(f"[DEBUG] same_dir: {getattr(self, 'same_dir', 'NOT_SET')}")

        # Setup upload destination if needed
        if getattr(self, "_upload_destination_setup_needed", False):
            await self._setup_upload_destination()
            self._upload_destination_setup_needed = False

        # Set required properties that TaskListener expects
        self.size = await self._get_size_of_download_dir()
        self.name = await self._get_name_from_download_dir()

        # Set tool identifier for TaskListener integration
        self.tool = "musicdl"

        # Set excluded_extensions for TaskListener
        excluded_extensions_str = Config.EXCLUDED_EXTENSIONS
        self.excluded_extensions = set()
        if excluded_extensions_str:
            # Parse comma-separated extensions and normalize them
            self.excluded_extensions = {
                ext.strip().lower()
                for ext in excluded_extensions_str.split(",")
                if ext.strip()
            }
            # Ensure extensions start with dot
            self.excluded_extensions = {
                ext if ext.startswith(".") else f".{ext}"
                for ext in self.excluded_extensions
            }

        LOGGER.info(f"[DEBUG] Set size: {self.size}, name: {self.name}")

        # Update status message to show upload starting
        await self.update_progress(status="🚀 Starting upload...")

        # Check for cancellation before proceeding
        if self.is_cancelled:
            LOGGER.info(
                f"[DEBUG] Download was cancelled during setup, aborting upload for UID: {self.uid}"
            )
            return

        # Register in task_dict before calling parent method
        await self._register_in_task_dict_async()

        # Integrate with task manager for proper queue handling
        await self._integrate_with_task_manager()

        # Check for cancellation after queue integration
        if self.is_cancelled:
            LOGGER.info(
                f"[DEBUG] Download was cancelled during queue integration, aborting upload for UID: {self.uid}"
            )
            return

        # Try parent method with real-time status monitoring
        try:
            LOGGER.info(f"[DEBUG] Before parent method: is_leech={self.is_leech}")
            LOGGER.info(
                f"[DEBUG] up_dest: {self.up_dest}, type: {type(self.up_dest)}"
            )

            # Start monitoring task_dict for upload status creation
            import asyncio

            monitor_task = asyncio.create_task(
                self._monitor_and_wrap_upload_status()
            )

            # Now that we've properly set up_dest based on mode, call parent method
            # For leech mode: up_dest is integer (chat ID)
            # For mirror mode: up_dest is string (rclone path)
            await super().on_download_complete()

            # Stop monitoring (upload should be complete)
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task

            LOGGER.info(f"[DEBUG] After parent method: is_leech={self.is_leech}")
            LOGGER.info(
                "[DEBUG] Parent on_download_complete() finished successfully"
            )

            # Delete status message after successful upload
            await self.delete_status_message()

        except Exception as e:
            LOGGER.error(f"[DEBUG] Parent on_download_complete() failed: {e}")
            # Update status message with error
            if self.status_message:
                try:
                    from pyrogram.enums import ParseMode

                    await self.status_message.edit_text(
                        f"❌ <b>Upload Failed</b>\n\n<b>Error:</b> {e!s}",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            # Log the error but don't try manual upload since we want proper integration
            import traceback

            traceback.print_exc()

        LOGGER.info(
            f"[DEBUG] MusicDownloadListener.on_download_complete() finished for UID: {self.uid}"
        )

    async def _register_in_task_dict_async(self):
        """Register this task in the global task_dict for TaskListener integration"""
        try:
            from bot import task_dict, task_dict_lock

            # Create a proper status object compatible with the status interface
            class MusicDownloadStatus:
                def __init__(self, listener):
                    self.listener = listener
                    self._gid = f"music_{listener.uid}"
                    self.tool = "musicdl"  # Required for task manager integration

                def name(self):
                    return self.listener.name

                def gid(self):
                    return self._gid

                def status(self):
                    if (
                        hasattr(self.listener, "is_completed")
                        and self.listener.is_completed
                    ):
                        return "Upload"
                    if (
                        hasattr(self.listener, "is_failed")
                        and self.listener.is_failed
                    ):
                        return "Failed"
                    return "Downloading"

                def size(self):
                    """Return readable file size"""
                    try:
                        from bot.helper.ext_utils.status_utils import (
                            get_readable_file_size,
                        )

                        return get_readable_file_size(
                            getattr(self.listener, "size", 0)
                        )
                    except:
                        return "0B"

                def processed_bytes(self):
                    """Return processed bytes (for progress calculation)"""
                    return (
                        getattr(self.listener, "size", 0)
                        if hasattr(self.listener, "is_completed")
                        and self.listener.is_completed
                        else 0
                    )

                def progress(self):
                    """Return progress percentage"""
                    if (
                        hasattr(self.listener, "is_completed")
                        and self.listener.is_completed
                    ):
                        return "100%"
                    if (
                        hasattr(self.listener, "is_failed")
                        and self.listener.is_failed
                    ):
                        return "0%"
                    return "50%"  # Assume 50% during download

                def speed(self):
                    """Return download speed"""
                    return "0B/s"  # Music downloads don't track speed

                def eta(self):
                    """Return estimated time of arrival"""
                    return "-"

                def task(self):
                    """Return task reference"""
                    return self

                async def cancel_task(self):
                    """Cancel the task"""
                    self.listener.is_cancelled = True
                    LOGGER.info(
                        f"Music download task cancelled: {self.listener.uid}"
                    )

            # Register in task_dict
            async with task_dict_lock:
                task_dict[self.mid] = MusicDownloadStatus(self)

            LOGGER.info(f"[DEBUG] Registered task {self.mid} in task_dict")

        except Exception as e:
            LOGGER.error(f"[DEBUG] Failed to register in task_dict: {e}")
            # Continue anyway - we'll handle this in the fallback upload

    def _create_status_wrapper(self, original_status):
        """Create a wrapper around the original status to intercept progress updates"""

        class MusicStatusWrapper:
            def __init__(self, original_status, music_listener):
                self._original = original_status
                self._music_listener = music_listener
                self._last_progress = 0
                self._last_update_time = 0

            def __getattr__(self, name):
                # Delegate all other attributes to the original status
                return getattr(self._original, name)

            def progress(self):
                """Override progress to update our status message"""
                try:
                    # Get progress from original status
                    progress_str = self._original.progress()

                    # Extract percentage (e.g., "45.2%" -> 45.2)
                    progress_percentage = float(progress_str.replace("%", ""))

                    # Only update if progress changed significantly (every 5%) or enough time passed
                    import time

                    current_time = time.time()

                    if (
                        abs(progress_percentage - self._last_progress) >= 5.0
                        or current_time - self._last_update_time >= 10
                    ):  # Update every 10 seconds minimum
                        self._last_progress = progress_percentage
                        self._last_update_time = current_time

                        # Calculate upload stats
                        try:
                            processed_bytes = self._original._obj.processed_bytes
                            total_bytes = self._original._size
                            speed = (
                                self._original._obj.speed
                                if hasattr(self._original._obj, "speed")
                                else 0
                            )

                            # Schedule status message update (non-blocking)
                            import asyncio

                            asyncio.create_task(
                                self._music_listener.update_upload_progress(
                                    progress_percentage,
                                    processed_bytes,
                                    total_bytes,
                                    speed,
                                )
                            )
                        except Exception as e:
                            LOGGER.warning(
                                f"Failed to update music status progress: {e}"
                            )

                    return progress_str

                except Exception as e:
                    LOGGER.warning(f"Error in music status wrapper progress: {e}")
                    return self._original.progress()

        return MusicStatusWrapper(original_status, self)

    async def _monitor_and_wrap_upload_status(self):
        """Monitor task_dict in real-time and wrap upload status as soon as it appears"""
        try:
            import asyncio

            from bot import task_dict, task_dict_lock

            LOGGER.info(
                f"[DEBUG] Starting real-time upload status monitoring for {self.mid}"
            )

            # Monitor for up to 30 seconds with 0.1 second intervals
            for attempt in range(300):  # 30 seconds / 0.1 = 300 attempts
                try:
                    async with task_dict_lock:
                        if self.mid in task_dict:
                            current_status = task_dict[self.mid]

                            # Check if this is an upload status that needs wrapping
                            if (
                                hasattr(current_status, "_status")
                                and current_status._status == "up"
                                and not hasattr(current_status, "_music_listener")
                            ):  # Not already wrapped
                                LOGGER.info(
                                    f"[DEBUG] Found upload status to wrap: {type(current_status).__name__}"
                                )
                                wrapped_status = self._create_status_wrapper(
                                    current_status
                                )
                                task_dict[self.mid] = wrapped_status
                                LOGGER.info(
                                    f"[DEBUG] Successfully wrapped upload status for {self.mid}"
                                )
                                return  # Success - stop monitoring

                            if hasattr(current_status, "_music_listener"):
                                LOGGER.info(
                                    f"[DEBUG] Upload status already wrapped for {self.mid}"
                                )
                                return  # Already wrapped - stop monitoring

                        # Task not found or not an upload status yet - continue monitoring
                        await asyncio.sleep(0.1)  # Check every 100ms

                except asyncio.CancelledError:
                    LOGGER.info(
                        f"[DEBUG] Upload status monitoring cancelled for {self.mid}"
                    )
                    return
                except Exception as e:
                    LOGGER.warning(
                        f"[DEBUG] Error during status monitoring attempt {attempt}: {e}"
                    )
                    await asyncio.sleep(0.1)

            LOGGER.warning(
                f"[DEBUG] Upload status monitoring timed out for {self.mid} after 30 seconds"
            )

        except asyncio.CancelledError:
            LOGGER.info(f"[DEBUG] Upload status monitoring cancelled for {self.mid}")
        except Exception as e:
            LOGGER.warning(f"[DEBUG] Failed to monitor upload status: {e}")
            # Register in task_dict
            async with task_dict_lock:
                task_dict[self.mid] = MusicDownloadStatus(self)
                # OPTIMIZATION Phase 1c: Update O(1) lookup indices
                try:
                    from bot.helper.ext_utils.status_utils import (
                        _update_task_indices,
                    )

                    _update_task_indices(task_dict[self.mid])
                except ImportError:
                    pass  # Index update functions not available yet

            # Continue anyway - upload will still work, just without progress updates

    async def _cleanup_task_dict(self):
        """Clean up task from task_dict and queue system when download completes"""
        try:
            from bot import non_queued_dl, queue_dict_lock, task_dict, task_dict_lock

            # Clean up from task_dict
            async with task_dict_lock:
                if self.mid in task_dict:
                    # OPTIMIZATION Phase 1c: Remove from O(1) lookup indices
                    try:
                        from bot.helper.ext_utils.status_utils import (
                            _remove_from_task_indices,
                        )

                        if self.mid in task_dict:
                            _remove_from_task_indices(task_dict[self.mid])
                    except ImportError:
                        pass  # Index update functions not available yet
                    del task_dict[self.mid]
                    LOGGER.info(f"[DEBUG] Cleaned up task {self.mid} from task_dict")
                else:
                    LOGGER.warning(
                        f"[DEBUG] Task {self.mid} not found in task_dict for cleanup"
                    )

            # Clean up from queue system
            async with queue_dict_lock:
                if self.mid in non_queued_dl:
                    non_queued_dl.remove(self.mid)
                    LOGGER.info(
                        f"[DEBUG] Removed task {self.mid} from non_queued_dl"
                    )

        except Exception as e:
            LOGGER.error(f"[DEBUG] Failed to cleanup task_dict: {e}")

    async def _integrate_with_task_manager(self):
        """Integrate with task manager for proper queue handling"""
        try:
            from bot.helper.ext_utils.task_manager import check_running_tasks

            # Check if we need to queue this download based on limits
            is_over_limit, event = await check_running_tasks(self, "dl")

            if is_over_limit:
                LOGGER.info(
                    f"[DEBUG] Download queued due to limits for UID: {self.uid}"
                )
                # Wait for our turn in the queue
                await event.wait()
                LOGGER.info(
                    f"[DEBUG] Download started from queue for UID: {self.uid}"
                )
            else:
                LOGGER.info(
                    f"[DEBUG] Download started immediately for UID: {self.uid}"
                )

        except Exception as e:
            LOGGER.error(f"[DEBUG] Failed to integrate with task manager: {e}")
            # Continue anyway - download can proceed without queue integration

    def _initialize_taskconfig_defaults(self):
        """Initialize all TaskConfig default values to prevent AttributeError"""
        # This ensures we have all attributes that TaskListener might access
        # Based on TaskConfig.__init__() in bot/helper/common.py

        # Core attributes (already set by super().__init__() but ensure they exist)
        if not hasattr(self, "metadata"):
            self.metadata = ""
        if not hasattr(self, "metadata_title"):
            self.metadata_title = ""
        if not hasattr(self, "metadata_author"):
            self.metadata_author = ""
        if not hasattr(self, "metadata_comment"):
            self.metadata_comment = ""
        if not hasattr(self, "metadata_all"):
            self.metadata_all = ""

        # Watermark attributes
        if not hasattr(self, "watermark"):
            self.watermark = ""
        if not hasattr(self, "watermark_enabled"):
            self.watermark_enabled = False
        if not hasattr(self, "watermark_position"):
            self.watermark_position = ""
        if not hasattr(self, "watermark_size"):
            self.watermark_size = 0
        if not hasattr(self, "watermark_color"):
            self.watermark_color = ""
        if not hasattr(self, "watermark_font"):
            self.watermark_font = ""
        if not hasattr(self, "watermark_priority"):
            self.watermark_priority = 0
        if not hasattr(self, "watermark_threading"):
            self.watermark_threading = False
        if not hasattr(self, "watermark_fast_mode"):
            self.watermark_fast_mode = True
        if not hasattr(self, "watermark_maintain_quality"):
            self.watermark_maintain_quality = True
        if not hasattr(self, "watermark_opacity"):
            self.watermark_opacity = 1.0
        if not hasattr(self, "audio_watermark_enabled"):
            self.audio_watermark_enabled = False
        if not hasattr(self, "audio_watermark_text"):
            self.audio_watermark_text = ""
        if not hasattr(self, "subtitle_watermark_enabled"):
            self.subtitle_watermark_enabled = False
        if not hasattr(self, "subtitle_watermark_text"):
            self.subtitle_watermark_text = ""

        # Image watermark attributes
        if not hasattr(self, "image_watermark_enabled"):
            self.image_watermark_enabled = False
        if not hasattr(self, "image_watermark_path"):
            self.image_watermark_path = ""
        if not hasattr(self, "image_watermark_scale"):
            self.image_watermark_scale = 10

        # All the boolean flags and processing attributes
        if not hasattr(self, "merge_enabled"):
            self.merge_enabled = False
        if not hasattr(self, "merge_priority"):
            self.merge_priority = 0
        if not hasattr(self, "trim"):
            self.trim = ""
        if not hasattr(self, "trim_enabled"):
            self.trim_enabled = False
        if not hasattr(self, "trim_priority"):
            self.trim_priority = 0
        if not hasattr(self, "trim_start_time"):
            self.trim_start_time = None
        if not hasattr(self, "trim_end_time"):
            self.trim_end_time = None
        if not hasattr(self, "trim_video_enabled"):
            self.trim_video_enabled = False
        if not hasattr(self, "trim_video_codec"):
            self.trim_video_codec = ""
        if not hasattr(self, "trim_video_preset"):
            self.trim_video_preset = ""
        if not hasattr(self, "trim_audio_enabled"):
            self.trim_audio_enabled = False
        if not hasattr(self, "trim_audio_codec"):
            self.trim_audio_codec = ""
        if not hasattr(self, "trim_audio_preset"):
            self.trim_audio_preset = ""
        if not hasattr(self, "trim_image_enabled"):
            self.trim_image_enabled = False
        if not hasattr(self, "trim_image_quality"):
            self.trim_image_quality = "none"
        if not hasattr(self, "trim_document_enabled"):
            self.trim_document_enabled = False
        if not hasattr(self, "trim_document_start_page"):
            self.trim_document_start_page = "1"
        if not hasattr(self, "trim_document_end_page"):
            self.trim_document_end_page = ""
        if not hasattr(self, "trim_document_quality"):
            self.trim_document_quality = "none"
        if not hasattr(self, "trim_subtitle_enabled"):
            self.trim_subtitle_enabled = False
        if not hasattr(self, "trim_subtitle_encoding"):
            self.trim_subtitle_encoding = ""
        if not hasattr(self, "trim_subtitle_format"):
            self.trim_subtitle_format = ""
        if not hasattr(self, "trim_archive_enabled"):
            self.trim_archive_enabled = False
        if not hasattr(self, "trim_archive_format"):
            self.trim_archive_format = ""
        if not hasattr(self, "trim_video_format"):
            self.trim_video_format = ""
        if not hasattr(self, "trim_audio_format"):
            self.trim_audio_format = ""
        if not hasattr(self, "trim_image_format"):
            self.trim_image_format = ""
        if not hasattr(self, "trim_document_format"):
            self.trim_document_format = ""
        if not hasattr(self, "trim_delete_original"):
            self.trim_delete_original = True
        if not hasattr(self, "merge_threading"):
            self.merge_threading = False
        if not hasattr(self, "concat_demuxer_enabled"):
            self.concat_demuxer_enabled = False
        if not hasattr(self, "filter_complex_enabled"):
            self.filter_complex_enabled = False

    async def _get_size_of_download_dir(self):
        """Get total size of downloaded files"""
        try:
            from bot.helper.ext_utils.files_utils import get_path_size

            size = await get_path_size(self.dir)
            LOGGER.info(f"[DEBUG] Calculated download size: {size} bytes")
            return size
        except Exception as e:
            LOGGER.error(f"[DEBUG] Error calculating size: {e}")
            return 0

    async def _get_name_from_download_dir(self):
        """Get the name from downloaded content"""
        try:
            from bot.helper.ext_utils.aiofiles_compat import listdir

            items = await listdir(self.dir)
            if items:
                # Use the first item as the name (usually the album/track folder)
                name = items[0]
                LOGGER.info(f"[DEBUG] Found download name: {name}")
                return name
            LOGGER.warning("[DEBUG] No items found in download directory")
            return f"MusicDL-{self.platform.upper()}"
        except Exception as e:
            LOGGER.error(f"[DEBUG] Error getting name: {e}")
            return f"MusicDL-{self.platform.upper()}"

    async def update_progress(self, **kwargs):
        """Update download progress and status message"""
        # Update internal status
        if "status" in kwargs:
            self.status = kwargs["status"]

        # Update status message if available
        if self.status_message:
            try:
                platform_emoji = {
                    "tidal": "🌊",
                    "qobuz": "🎼",
                    "apple": "🍎",
                    "spotify": "🎵",
                    "deezer": "🎶",
                }.get(self.platform, "🎵")

                mode_text = (
                    "Leech to Telegram" if self.is_leech else "Mirror to Cloud"
                )

                from pyrogram.enums import ParseMode

                await self.status_message.edit_text(
                    f"{platform_emoji} <b>{'Leech' if self.is_leech else 'Mirror'} Started</b>\n\n"
                    f"<b>Platform:</b> {self.platform.title()}\n"
                    f"<b>Status:</b> {self.status}\n"
                    f"<b>Mode:</b> {mode_text}\n\n"
                    f"<b>URL:</b> <code>{self.url if hasattr(self, 'url') else 'Processing...'}</code>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                LOGGER.warning(f"Failed to update status message: {e}")

    async def update_upload_progress(
        self, progress_percentage, uploaded_bytes, total_bytes, speed=None
    ):
        """Update status message and inline message with upload progress"""
        try:
            from pyrogram.enums import ParseMode

            from bot.helper.ext_utils.status_utils import get_readable_file_size

            platform_emoji = {
                "tidal": "🌊",
                "qobuz": "🎼",
                "apple": "🍎",
                "spotify": "🎵",
                "deezer": "🎶",
            }.get(self.platform, "🎵")

            mode_text = "Leech to Telegram" if self.is_leech else "Mirror to Cloud"

            # Create progress bar
            progress_bar = self._create_progress_bar(progress_percentage)

            # Format speed
            speed_text = f"{get_readable_file_size(speed)}/s" if speed else "N/A"

            progress_text = (
                f"{platform_emoji} <b>{'Uploading' if self.is_leech else 'Mirroring'}</b>\n\n"
                f"<b>Platform:</b> {self.platform.title()}\n"
                f"<b>Status:</b> Uploading... {progress_percentage:.1f}%\n"
                f"<b>Mode:</b> {mode_text}\n\n"
                f"<b>Progress:</b>\n{progress_bar}\n"
                f"<b>Size:</b> {get_readable_file_size(uploaded_bytes)} / {get_readable_file_size(total_bytes)}\n"
                f"<b>Speed:</b> {speed_text}"
            )

            # Update status message if available
            if self.status_message:
                await self.status_message.edit_text(
                    progress_text,
                    parse_mode=ParseMode.HTML,
                )

            # Update inline message if available
            if self.inline_message:
                try:
                    await self.inline_message.edit_text(
                        progress_text,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    LOGGER.warning(f"Failed to update inline message: {e}")

        except Exception as e:
            LOGGER.warning(f"Failed to update upload progress: {e}")

    def _create_progress_bar(self, percentage, length=20):
        """Create a visual progress bar"""
        filled = int(length * percentage / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}] {percentage:.1f}%"

    async def delete_status_message(self):
        """Delete the status message when upload completes"""
        if self.status_message:
            try:
                await self.status_message.delete()
                self.status_message = None
                LOGGER.info("Status message deleted after upload completion")
            except Exception as e:
                LOGGER.warning(f"Failed to delete status message: {e}")

    def get_readable_message(self) -> str:
        """Get formatted status message"""
        elapsed = time.time() - self.start_time

        msg = f"<b>📱 Name:</b> <code>{self.name}</code>\n"
        msg += f"<b>🎵 Platform:</b> {self.platform.title()}\n"
        msg += f"<b>📊 Status:</b> {self.status}\n"

        if self.total_size > 0:
            progress = (self.processed_bytes / self.total_size) * 100
            msg += f"<b>📈 Progress:</b> {progress:.1f}%\n"
            msg += f"<b>💾 Size:</b> {get_readable_file_size(self.processed_bytes)} / {get_readable_file_size(self.total_size)}\n"

        if self.speed > 0:
            msg += f"<b>⚡ Speed:</b> {get_readable_file_size(self.speed)}/s\n"
            msg += f"<b>⏱️ ETA:</b> {self.eta}\n"

        msg += f"<b>🕐 Elapsed:</b> {get_readable_time(elapsed)}\n"

        if self.downloaded_files:
            msg += f"<b>📁 Files:</b> {len(self.downloaded_files)}\n"

        return msg


class TidalDownloader:
    """Tidal downloader using tidal-dl-ng CLI"""

    def __init__(self, listener: MusicDownloadListener):
        self.listener = listener
        self.config = listener.config
        LOGGER.info(f"TidalDownloader initialized for {listener.uid}")

    async def download(self, url: str) -> bool:
        """Download from Tidal with comprehensive options and logging"""
        LOGGER.info(f"Starting Tidal download for URL: {url}")
        try:
            # Status updates disabled for musicdl

            # Setup authentication
            LOGGER.info("Setting up Tidal authentication...")
            auth_success = await setup_tidal_auth()
            if not auth_success:
                LOGGER.error("Tidal authentication failed")
                return False
            LOGGER.info("Tidal authentication successful")

            # Configure device authentication for Dolby Atmos
            if self.config.dolby_atmos:
                LOGGER.info(
                    "🎵 Dolby Atmos enabled - configuring Fire TV device authentication"
                )
                await self._setup_fire_tv_authentication()
            else:
                LOGGER.info("Dolby Atmos disabled - using standard authentication")

            # Build command (tidal-dl-ng only supports basic dl command)
            cmd = ["tidal-dl-ng", "dl", url]

            LOGGER.info(
                "Note: tidal-dl-ng uses config file for all options, not CLI flags"
            )
            LOGGER.info("Configuring tidal-dl-ng via settings.json...")

            # Configure all options via config file (tidal-dl-ng approach)
            await self._configure_tidal_settings()

            LOGGER.info(f"Tidal command: {' '.join(cmd)}")

            # Execute download
            await self.listener.update_progress(
                status="🌊 Downloading from Tidal..."
            )

            # Set environment variables to ensure tidal-dl-ng uses our config
            import os

            env = os.environ.copy()
            env["HOME"] = str(Path.home())  # Ensure HOME is set correctly
            env["XDG_CONFIG_HOME"] = str(
                Path.home() / ".config"
            )  # Set XDG config directory

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.listener.download_dir,
                env=env,  # Pass our environment variables
            )

            self.listener.process = process
            LOGGER.info(f"Tidal process started with PID: {process.pid}")

            stdout, stderr = await process.communicate()

            LOGGER.info(
                f"Tidal process completed with return code: {process.returncode}"
            )

            # DEBUG: Log tidal-dl-ng output to understand what it's doing
            if stdout:
                stdout_text = stdout.decode()
                LOGGER.info(
                    f"DEBUG: Tidal stdout (first 1000 chars): {stdout_text[:1000]}"
                )
                # Look for format information in the output
                if "FLAC" in stdout_text.upper():
                    LOGGER.info("DEBUG: FLAC mentioned in tidal-dl-ng output")
                if "M4A" in stdout_text.upper():
                    LOGGER.info("DEBUG: M4A mentioned in tidal-dl-ng output")
                if "extract" in stdout_text.lower():
                    LOGGER.info("DEBUG: Extract mentioned in tidal-dl-ng output")

            if stderr:
                stderr_text = stderr.decode()
                LOGGER.info(
                    f"DEBUG: Tidal stderr (first 500 chars): {stderr_text[:500]}"
                )

            if process.returncode == 0:
                LOGGER.info("Tidal download successful, processing output...")
                await self._process_tidal_output(stdout.decode())

                # Convert format if needed (post-download conversion)
                if self.config.format != "flac":
                    await self._convert_audio_format()

                return True
            error = stderr.decode() if stderr else "Unknown error"
            LOGGER.error(f"Tidal download failed: {error}")
            return False

        except Exception as e:
            LOGGER.error(f"Tidal download error: {e}", exc_info=True)
            return False

    async def _setup_fire_tv_authentication(self):
        """Setup Fire TV device authentication for Dolby Atmos access"""
        try:
            LOGGER.info(
                "🔥 Configuring Fire TV device authentication for Dolby Atmos..."
            )

            # ISSUE IDENTIFIED: Monkey patching doesn't work because tidal-dl-ng runs as separate subprocess
            # SOLUTION: Directly modify tidal-dl-ng source files to use Fire TV API key (index 1)

            LOGGER.info(
                "🔧 Directly modifying tidal-dl-ng source to use Fire TV API key..."
            )

            from pathlib import Path

            import tidal_dl_ng.config as tidal_config_module

            # Get the actual tidal-dl-ng config.py file path
            config_file = Path(tidal_config_module.__file__)

            LOGGER.info(f"🔍 Found tidal-dl-ng config file: {config_file}")

            if not config_file.exists():
                LOGGER.error(f"❌ tidal-dl-ng config file not found: {config_file}")
                return

            # Read the current config file
            with open(config_file) as f:
                content = f.read()

            # Check if already patched
            if "# DOLBY_ATMOS_PATCH_APPLIED" in content:
                LOGGER.info("✅ Fire TV patch already applied to tidal-dl-ng")
                return

            # Find the line where tidalapi.Config is created and modify it
            lines = content.split("\n")
            modified = False

            for i, line in enumerate(lines):
                # Look for the line: tidal_config: tidalapi.Config = tidalapi.Config(item_limit=10000)
                if "tidal_config: tidalapi.Config = tidalapi.Config" in line:
                    LOGGER.info(f"Found tidalapi.Config creation at line {i + 1}")

                    # Insert Fire TV API key configuration after the config creation
                    insert_lines = [
                        "        # DOLBY_ATMOS_PATCH_APPLIED - Fire TV API key for Dolby Atmos",
                        "        # Based on discovery: API key index 1 = Fire TV 'Master-Only(Else Error)'",
                        "        import tidal_dl_ng.api as tidal_api_patch",
                        "        fire_tv_key = tidal_api_patch.getItem(1)  # Fire TV Master-Only",
                        "        if fire_tv_key and 'clientId' in fire_tv_key:",
                        "            tidal_config.client_id = fire_tv_key['clientId']",
                        "            tidal_config.client_secret = fire_tv_key['clientSecret']",
                        "            # Fire TV credentials applied for Dolby Atmos access",
                    ]

                    # Insert the patch after the config line
                    lines[i + 1 : i + 1] = insert_lines
                    modified = True
                    break

            if modified:
                # Write the modified content back
                modified_content = "\n".join(lines)
                with open(config_file, "w") as f:
                    f.write(modified_content)

                LOGGER.info("✅ tidal-dl-ng source successfully patched!")
                LOGGER.info(
                    "🎵 Fire TV API key (index 1) will be used for Dolby Atmos access"
                )
                LOGGER.info("Platform: Fire TV | Formats: Master-Only(Else Error)")
                LOGGER.info("This enables EAC3/EAC4 Dolby Atmos downloads")
            else:
                LOGGER.error("❌ Failed to find tidalapi.Config creation line")
                LOGGER.warning("Falling back to standard authentication")

        except Exception as e:
            LOGGER.error(f"❌ Failed to patch tidal-dl-ng source: {e}")
            LOGGER.warning(
                "Falling back to standard authentication - Dolby Atmos may not be available"
            )

    async def _configure_tidal_settings(self):
        """Configure tidal-dl-ng settings using cfg commands (working approach)"""
        LOGGER.info("Configuring tidal-dl-ng settings using cfg commands...")

        # Apply quality setting (flags override config)
        quality_map = {
            "27": "HI_RES_LOSSLESS",  # 24-bit/192kHz
            "7": "LOSSLESS",  # 16-bit/44.1kHz FLAC
            "6": "LOSSLESS",  # 16-bit/44.1kHz FLAC (same as 7)
            "5": "HIGH",  # 320kbps AAC
            "0": "LOW",  # 96kbps (lowest quality)
        }

        # Quality setting (flags override config, -q flag maps to quality_audio)
        if hasattr(self.config, "quality") and self.config.quality in quality_map:
            tidal_quality = quality_map[self.config.quality]
            LOGGER.info(
                f"Using user-specified quality: -q {self.config.quality} -> {tidal_quality}"
            )
        else:
            tidal_quality = Config.TIDAL_QUALITY_AUDIO
            LOGGER.info(f"Using config quality: {tidal_quality}")

        LOGGER.info(f"Tidal audio quality configured: {tidal_quality}")

        # Set download directory (user override or config default)
        download_path = Config.TIDAL_DOWNLOAD_BASE_PATH or self.listener.download_dir
        LOGGER.info(f"Download path set to: {download_path}")

        # Enable lyrics if configured globally
        lyrics_enabled = Config.MUSICDL_LYRICS_ENABLED
        if lyrics_enabled:
            LOGGER.info(
                "Lyrics embedding and file creation enabled via global config"
            )

        # Format conversion handling (tidal-dl-ng only extracts FLAC, conversion done post-download)
        extract_flac = Config.TIDAL_EXTRACT_FLAC
        if self.config.format != "flac":
            extract_flac = True
            LOGGER.info(
                f"FLAC extraction enabled for post-download conversion to: {self.config.format}"
            )

        # WORKING APPROACH: Use cfg commands to configure tidal-dl-ng
        # This approach works reliably and bypasses settings.json compatibility issues
        try:
            LOGGER.info("Applying tidal-dl-ng settings using cfg commands...")

            # Set quality_audio using async subprocess
            quality_cmd = ["tidal-dl-ng", "cfg", "quality_audio", tidal_quality]
            quality_process = await asyncio.create_subprocess_exec(
                *quality_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await quality_process.communicate()
            LOGGER.info(f"Quality set - return code: {quality_process.returncode}")

            # Set extract_flac using async subprocess
            extract_cmd = [
                "tidal-dl-ng",
                "cfg",
                "extract_flac",
                "true" if extract_flac else "false",
            ]
            extract_process = await asyncio.create_subprocess_exec(
                *extract_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await extract_process.communicate()
            LOGGER.info(
                f"Extract FLAC set - return code: {extract_process.returncode}"
            )

            # Set lyrics settings using async subprocess
            lyrics_embed_cmd = [
                "tidal-dl-ng",
                "cfg",
                "lyrics_embed",
                "true" if (lyrics_enabled or Config.TIDAL_LYRICS_EMBED) else "false",
            ]
            lyrics_embed_process = await asyncio.create_subprocess_exec(
                *lyrics_embed_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await lyrics_embed_process.communicate()
            LOGGER.info(
                f"Lyrics embed set - return code: {lyrics_embed_process.returncode}"
            )

            lyrics_file_cmd = [
                "tidal-dl-ng",
                "cfg",
                "lyrics_file",
                "true" if (lyrics_enabled or Config.TIDAL_LYRICS_FILE) else "false",
            ]
            lyrics_file_process = await asyncio.create_subprocess_exec(
                *lyrics_file_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await lyrics_file_process.communicate()
            LOGGER.info(
                f"Lyrics file set - return code: {lyrics_file_process.returncode}"
            )

            # Set FFmpeg path for FLAC extraction (use xtra for production)
            ffmpeg_path = Config.TIDAL_PATH_BINARY_FFMPEG
            ffmpeg_cmd = ["tidal-dl-ng", "cfg", "path_binary_ffmpeg", ffmpeg_path]
            ffmpeg_process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await ffmpeg_process.communicate()
            LOGGER.info(
                f"FFmpeg path set to {ffmpeg_path} - return code: {ffmpeg_process.returncode}"
            )

            # Set FFprobe path
            ffprobe_path = Config.TIDAL_PATH_BINARY_FFPROBE
            ffprobe_cmd = ["tidal-dl-ng", "cfg", "path_binary_ffprobe", ffprobe_path]
            ffprobe_process = await asyncio.create_subprocess_exec(
                *ffprobe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await ffprobe_process.communicate()
            LOGGER.info(
                f"FFprobe path set to {ffprobe_path} - return code: {ffprobe_process.returncode}"
            )

            # Configure ALL additional tidal settings using flag-aware variables

            # Download behavior settings
            skip_existing_cmd = [
                "tidal-dl-ng",
                "cfg",
                "skip_existing",
                "true" if Config.TIDAL_SKIP_EXISTING else "false",
            ]
            skip_process = await asyncio.create_subprocess_exec(
                *skip_existing_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await skip_process.communicate()

            download_delay_cmd = [
                "tidal-dl-ng",
                "cfg",
                "download_delay",
                "true" if Config.TIDAL_DOWNLOAD_DELAY else "false",
            ]
            delay_process = await asyncio.create_subprocess_exec(
                *download_delay_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await delay_process.communicate()

            concurrent_cmd = [
                "tidal-dl-ng",
                "cfg",
                "downloads_concurrent_max",
                str(Config.TIDAL_DOWNLOADS_CONCURRENT_MAX),
            ]
            concurrent_process = await asyncio.create_subprocess_exec(
                *concurrent_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await concurrent_process.communicate()

            simultaneous_cmd = [
                "tidal-dl-ng",
                "cfg",
                "downloads_simultaneous_per_track_max",
                str(Config.TIDAL_DOWNLOADS_SIMULTANEOUS_PER_TRACK_MAX),
            ]
            simultaneous_process = await asyncio.create_subprocess_exec(
                *simultaneous_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await simultaneous_process.communicate()

            delay_min_cmd = [
                "tidal-dl-ng",
                "cfg",
                "download_delay_sec_min",
                str(Config.TIDAL_DOWNLOAD_DELAY_SEC_MIN),
            ]
            delay_min_process = await asyncio.create_subprocess_exec(
                *delay_min_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await delay_min_process.communicate()

            delay_max_cmd = [
                "tidal-dl-ng",
                "cfg",
                "download_delay_sec_max",
                str(Config.TIDAL_DOWNLOAD_DELAY_SEC_MAX),
            ]
            delay_max_process = await asyncio.create_subprocess_exec(
                *delay_max_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await delay_max_process.communicate()

            # Metadata and cover settings
            cover_embed_cmd = [
                "tidal-dl-ng",
                "cfg",
                "metadata_cover_embed",
                "true" if Config.TIDAL_METADATA_COVER_EMBED else "false",
            ]
            cover_embed_process = await asyncio.create_subprocess_exec(
                *cover_embed_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await cover_embed_process.communicate()

            cover_file_cmd = [
                "tidal-dl-ng",
                "cfg",
                "cover_album_file",
                "true" if Config.TIDAL_COVER_ALBUM_FILE else "false",
            ]
            cover_file_process = await asyncio.create_subprocess_exec(
                *cover_file_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await cover_file_process.communicate()

            replay_gain_cmd = [
                "tidal-dl-ng",
                "cfg",
                "metadata_replay_gain",
                "true" if Config.TIDAL_METADATA_REPLAY_GAIN else "false",
            ]
            replay_gain_process = await asyncio.create_subprocess_exec(
                *replay_gain_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await replay_gain_process.communicate()

            cover_dimension_cmd = [
                "tidal-dl-ng",
                "cfg",
                "metadata_cover_dimension",
                str(Config.TIDAL_METADATA_COVER_DIMENSION),
            ]
            cover_dimension_process = await asyncio.create_subprocess_exec(
                *cover_dimension_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await cover_dimension_process.communicate()

            # Advanced settings
            symlink_cmd = [
                "tidal-dl-ng",
                "cfg",
                "symlink_to_track",
                "true" if Config.TIDAL_SYMLINK_TO_TRACK else "false",
            ]
            symlink_process = await asyncio.create_subprocess_exec(
                *symlink_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await symlink_process.communicate()

            playlist_cmd = [
                "tidal-dl-ng",
                "cfg",
                "playlist_create",
                "true" if Config.TIDAL_PLAYLIST_CREATE else "false",
            ]
            playlist_process = await asyncio.create_subprocess_exec(
                *playlist_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await playlist_process.communicate()

            video_download_cmd = [
                "tidal-dl-ng",
                "cfg",
                "video_download",
                "true" if Config.TIDAL_VIDEO_DOWNLOAD else "false",
            ]
            video_download_process = await asyncio.create_subprocess_exec(
                *video_download_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await video_download_process.communicate()

            video_convert_cmd = [
                "tidal-dl-ng",
                "cfg",
                "video_convert_mp4",
                "true" if Config.TIDAL_VIDEO_CONVERT_MP4 else "false",
            ]
            video_convert_process = await asyncio.create_subprocess_exec(
                *video_convert_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await video_convert_process.communicate()

            track_pad_cmd = [
                "tidal-dl-ng",
                "cfg",
                "album_track_num_pad_min",
                str(Config.TIDAL_ALBUM_TRACK_NUM_PAD_MIN),
            ]
            track_pad_process = await asyncio.create_subprocess_exec(
                *track_pad_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await track_pad_process.communicate()

            # Format templates
            format_album_cmd = [
                "tidal-dl-ng",
                "cfg",
                "format_album",
                Config.TIDAL_FORMAT_ALBUM,
            ]
            format_album_process = await asyncio.create_subprocess_exec(
                *format_album_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await format_album_process.communicate()

            format_track_cmd = [
                "tidal-dl-ng",
                "cfg",
                "format_track",
                Config.TIDAL_FORMAT_TRACK,
            ]
            format_track_process = await asyncio.create_subprocess_exec(
                *format_track_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await format_track_process.communicate()

            format_playlist_cmd = [
                "tidal-dl-ng",
                "cfg",
                "format_playlist",
                Config.TIDAL_FORMAT_PLAYLIST,
            ]
            format_playlist_process = await asyncio.create_subprocess_exec(
                *format_playlist_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await format_playlist_process.communicate()

            format_mix_cmd = [
                "tidal-dl-ng",
                "cfg",
                "format_mix",
                Config.TIDAL_FORMAT_MIX,
            ]
            format_mix_process = await asyncio.create_subprocess_exec(
                *format_mix_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await format_mix_process.communicate()

            format_video_cmd = [
                "tidal-dl-ng",
                "cfg",
                "format_video",
                Config.TIDAL_FORMAT_VIDEO,
            ]
            format_video_process = await asyncio.create_subprocess_exec(
                *format_video_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await format_video_process.communicate()

            LOGGER.info(
                "Tidal-dl-ng settings configured successfully using cfg commands - ALL settings applied from config_manager.py"
            )

        except Exception as e:
            LOGGER.error(f"Failed to configure tidal-dl-ng settings: {e}")
            raise

    async def _convert_audio_format(self):
        """Convert downloaded audio files to specified format using xtra (ffmpeg)"""
        try:
            download_path = Path(self.listener.download_dir)
            audio_files = []

            # Find all audio files
            for ext in [".flac", ".mp3", ".m4a", ".wav"]:
                audio_files.extend(download_path.rglob(f"*{ext}"))

            if not audio_files:
                LOGGER.warning("No audio files found for format conversion")
                return

            LOGGER.info(
                f"Converting {len(audio_files)} files to {self.config.format}"
            )

            for audio_file in audio_files:
                if audio_file.suffix.lower() == f".{self.config.format}":
                    LOGGER.info(
                        f"Skipping {audio_file.name} - already in target format"
                    )
                    continue

                output_file = audio_file.with_suffix(f".{self.config.format}")

                # Build conversion command using xtra (ffmpeg)
                cmd = [
                    "xtra",  # Renamed ffmpeg binary
                    "-i",
                    str(audio_file),
                    "-y",  # Overwrite output file
                ]

                # Add format-specific options
                if self.config.format == "mp3":
                    cmd.extend(
                        ["-c:a", "libmp3lame", "-q:a", "0"]
                    )  # Highest quality MP3
                elif self.config.format in ["m4a", "aac"]:
                    cmd.extend(["-c:a", "aac", "-b:a", "320k"])  # High bitrate AAC
                elif self.config.format == "flac":
                    cmd.extend(["-c:a", "flac"])  # Lossless FLAC
                elif self.config.format == "opus":
                    cmd.extend(
                        ["-c:a", "libopus", "-b:a", "256k"]
                    )  # High quality Opus

                cmd.append(str(output_file))

                LOGGER.info(f"Converting {audio_file.name} to {self.config.format}")

                # Execute conversion
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    # Remove original file and rename converted file
                    audio_file.unlink()
                    LOGGER.info(
                        f"Successfully converted {audio_file.name} to {output_file.name}"
                    )
                else:
                    error = stderr.decode() if stderr else "Unknown conversion error"
                    LOGGER.error(f"Failed to convert {audio_file.name}: {error}")
                    # Keep original file if conversion fails
                    if output_file.exists():
                        output_file.unlink()

            LOGGER.info(f"Format conversion to {self.config.format} completed")

        except Exception as e:
            LOGGER.error(f"Format conversion error: {e}", exc_info=True)

    async def _process_tidal_output(self, output: str):
        """Process Tidal CLI output"""
        # Find downloaded files (upload ALL files except excluded extensions from config)
        download_path = Path(self.listener.download_dir)
        downloaded_files = []

        # Get excluded extensions from config_manager.py
        excluded_extensions_str = Config.EXCLUDED_EXTENSIONS
        excluded_extensions = set()
        if excluded_extensions_str:
            # Parse comma-separated extensions and normalize them
            excluded_extensions = {
                ext.strip().lower()
                for ext in excluded_extensions_str.split(",")
                if ext.strip()
            }
            # Ensure extensions start with dot
            excluded_extensions = {
                ext if ext.startswith(".") else f".{ext}"
                for ext in excluded_extensions
            }

        # Get all files in download directory (excluding configured extensions)
        for file_path in download_path.rglob("*"):
            if (
                file_path.is_file()
                and file_path.suffix.lower() not in excluded_extensions
            ):
                downloaded_files.append(file_path)

        # Check if files were downloaded to tidal-dl-ng's default location
        if not downloaded_files:
            # Check home/download directory (tidal-dl-ng default)
            home_download = Path.home() / "download"
            if home_download.exists():
                home_files = []
                for file_path in home_download.rglob("*"):
                    if (
                        file_path.is_file()
                        and file_path.suffix.lower() not in excluded_extensions
                    ):
                        home_files.append(file_path)

                if home_files:
                    LOGGER.info(
                        f"Moving {len(home_files)} files from default location to download directory"
                    )
                    # Move files to our expected directory
                    import shutil

                    for file in home_files:
                        dest_file = download_path / file.name
                        shutil.move(str(file), str(dest_file))
                        downloaded_files.append(dest_file)

        if downloaded_files:
            sum(f.stat().st_size for f in downloaded_files)
            self.listener.downloaded_files = [str(f) for f in downloaded_files]

            # Update listener name with the first file or folder name
            if len(downloaded_files) == 1:
                # Single file - use the file name (without extension for cleaner display)
                self.listener.name = downloaded_files[0].stem
            else:
                # Multiple files - use the parent folder name or a descriptive name
                parent_folder = downloaded_files[0].parent.name
                if parent_folder != self.listener.download_dir:
                    self.listener.name = parent_folder
                else:
                    self.listener.name = (
                        f"Tidal_Download_{len(downloaded_files)}_files"
                    )

            LOGGER.info(f"Found {len(downloaded_files)} files to upload")

            # Download completed - status updates disabled


class QobuzDownloader:
    """Qobuz downloader using qobuz-dl CLI with Tidal lyrics integration"""

    def __init__(self, listener: MusicDownloadListener):
        self.listener = listener
        self.config = listener.config
        LOGGER.info(f"QobuzDownloader initialized for {listener.uid}")

    async def download(self, url: str) -> bool:
        """Download from Qobuz using module-based approach with comprehensive options and Tidal lyrics"""
        LOGGER.info(f"Starting Qobuz download for URL: {url}")
        try:
            # Status updates disabled for musicdl

            # Use module-based approach only (no CLI, no config files, no interactive prompts)
            LOGGER.info("Starting module-based Qobuz download...")
            return await self._download_with_module(url)

        except Exception as e:
            LOGGER.error(f"Qobuz download error: {e}", exc_info=True)
            return False

    async def _download_with_module(self, url: str) -> bool:
        """Download using qobuz-dl as Python module (no CLI, no config files)"""
        try:
            # Check if qobuz-dl module is available
            if not QOBUZ_MODULE_AVAILABLE:
                LOGGER.error(
                    "qobuz-dl module not available - cannot use module-based approach"
                )
                return False

            LOGGER.info("Setting up Qobuz module authentication...")
            email, password = await setup_qobuz_module_auth()

            if not email or not password:
                LOGGER.error(
                    "Qobuz module authentication failed - missing credentials"
                )
                return False

            LOGGER.info("Qobuz module authentication successful")

            # Configure QobuzDL with flag-aware settings (flags override config)
            # Map our config to actual QobuzDL constructor parameters
            quality = (
                int(self.config.quality)
                if self.config.quality != "27"
                else Config.QOBUZ_DEFAULT_QUALITY
            )

            qobuz = QobuzDL(
                directory=self.listener.download_dir,  # 'directory' not 'download_folder'
                quality=quality,  # Must be int, not string
                embed_art=self.config.embed_art,
                interactive_limit=self.config.qobuz_limit,  # For search results
                ignore_singles_eps=self.config.qobuz_albums_only,  # 'ignore_singles_eps' not 'albums_only'
                no_m3u_for_playlists=self.config.qobuz_no_m3u,  # 'no_m3u_for_playlists' not 'no_m3u'
                quality_fallback=not self.config.qobuz_no_fallback,  # Inverted logic: quality_fallback=True means fallback enabled
                cover_og_quality=self.config.qobuz_og_cover,  # 'cover_og_quality' not 'og_cover'
                no_cover=self.config.qobuz_no_cover,
                downloads_db=(
                    None if self.config.qobuz_no_db else "qobuz_downloads.db"
                ),  # 'downloads_db' not 'no_database'
                folder_format=self.config.qobuz_folder_format
                or "{artist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]",
                track_format=self.config.qobuz_track_format
                or "{tracknumber}. {tracktitle}",
                smart_discography=self.config.qobuz_smart_discography,
            )

            # Get tokens using QobuzDL's own method
            qobuz.get_tokens()

            # Initialize client with authentication
            qobuz.initialize_client(email, password, qobuz.app_id, qobuz.secrets)

            # Status updates disabled for musicdl

            # Handle the URL download
            LOGGER.info(f"Starting Qobuz module download for: {url}")
            qobuz.handle_url(url)

            LOGGER.info("Qobuz module download completed successfully")
            await self._process_qobuz_output("")  # Process downloaded files

            # Add Tidal lyrics if enabled
            if Config.MUSICDL_LYRICS_ENABLED:
                LOGGER.info("Lyrics enabled, fetching from Tidal...")
                await self._fetch_tidal_lyrics_for_qobuz()

            # Convert format if needed (post-download conversion)
            if self.config.format != "flac":
                await self._convert_audio_format()

            return True

        except Exception as e:
            LOGGER.error(f"Qobuz module download failed: {e}", exc_info=True)
            return False

    async def _convert_audio_format(self):
        """Convert downloaded audio files to specified format using xtra (ffmpeg)"""
        try:
            download_path = Path(self.listener.download_dir)
            audio_files = []

            # Find all audio files
            for ext in [".flac", ".mp3", ".m4a", ".wav"]:
                audio_files.extend(download_path.rglob(f"*{ext}"))

            if not audio_files:
                LOGGER.warning("No audio files found for format conversion")
                return

            LOGGER.info(
                f"Converting {len(audio_files)} files to {self.config.format}"
            )

            for audio_file in audio_files:
                if audio_file.suffix.lower() == f".{self.config.format}":
                    LOGGER.info(
                        f"Skipping {audio_file.name} - already in target format"
                    )
                    continue

                output_file = audio_file.with_suffix(f".{self.config.format}")

                # Build conversion command using xtra (ffmpeg)
                cmd = [
                    "xtra",  # Renamed ffmpeg binary
                    "-i",
                    str(audio_file),
                    "-y",  # Overwrite output file
                ]

                # Add format-specific options
                if self.config.format == "mp3":
                    cmd.extend(
                        ["-c:a", "libmp3lame", "-q:a", "0"]
                    )  # Highest quality MP3
                elif self.config.format in ["m4a", "aac"]:
                    cmd.extend(["-c:a", "aac", "-b:a", "320k"])  # High bitrate AAC
                elif self.config.format == "flac":
                    cmd.extend(["-c:a", "flac"])  # Lossless FLAC
                elif self.config.format == "opus":
                    cmd.extend(
                        ["-c:a", "libopus", "-b:a", "256k"]
                    )  # High quality Opus

                cmd.append(str(output_file))

                LOGGER.info(f"Converting {audio_file.name} to {self.config.format}")

                # Execute conversion
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    # Remove original file and rename converted file
                    audio_file.unlink()
                    LOGGER.info(
                        f"Successfully converted {audio_file.name} to {output_file.name}"
                    )
                else:
                    error = stderr.decode() if stderr else "Unknown conversion error"
                    LOGGER.error(f"Failed to convert {audio_file.name}: {error}")
                    # Keep original file if conversion fails
                    if output_file.exists():
                        output_file.unlink()

            LOGGER.info(f"Format conversion to {self.config.format} completed")

        except Exception as e:
            LOGGER.error(f"Format conversion error: {e}", exc_info=True)

    async def _process_qobuz_output(self, output: str):
        """Process Qobuz CLI output"""
        # Find downloaded files (upload ALL files except excluded extensions from config)
        download_path = Path(self.listener.download_dir)
        downloaded_files = []

        # Get excluded extensions from config_manager.py
        excluded_extensions_str = Config.EXCLUDED_EXTENSIONS
        excluded_extensions = set()
        if excluded_extensions_str:
            # Parse comma-separated extensions and normalize them
            excluded_extensions = {
                ext.strip().lower()
                for ext in excluded_extensions_str.split(",")
                if ext.strip()
            }
            # Ensure extensions start with dot
            excluded_extensions = {
                ext if ext.startswith(".") else f".{ext}"
                for ext in excluded_extensions
            }

        # Get all files in download directory (excluding configured extensions)
        for file_path in download_path.rglob("*"):
            if (
                file_path.is_file()
                and file_path.suffix.lower() not in excluded_extensions
            ):
                downloaded_files.append(file_path)

        if downloaded_files:
            sum(f.stat().st_size for f in downloaded_files)
            self.listener.downloaded_files = [str(f) for f in downloaded_files]

            # Update listener name with the first file or folder name
            if len(downloaded_files) == 1:
                # Single file - use the file name (without extension for cleaner display)
                self.listener.name = downloaded_files[0].stem
            else:
                # Multiple files - use the parent folder name or a descriptive name
                parent_folder = downloaded_files[0].parent.name
                if parent_folder != self.listener.download_dir:
                    self.listener.name = parent_folder
                else:
                    self.listener.name = (
                        f"Qobuz_Download_{len(downloaded_files)}_files"
                    )

            LOGGER.info(f"Found {len(downloaded_files)} files to upload")

            # Download completed - status updates disabled

    async def _fetch_tidal_lyrics_for_qobuz(self):
        """Fetch Tidal lyrics for Qobuz downloads using metadata matching"""
        LOGGER.info("Starting Tidal lyrics fetching for Qobuz tracks...")
        try:
            # Status updates disabled for musicdl

            # Find downloaded audio files
            download_path = Path(self.listener.download_dir)
            audio_files = []
            for ext in [".flac", ".mp3", ".m4a", ".aac"]:
                audio_files.extend(download_path.rglob(f"*{ext}"))

            if not audio_files:
                LOGGER.warning("No audio files found for lyrics processing")
                return

            LOGGER.info(
                f"Found {len(audio_files)} audio files for lyrics processing"
            )

            # Process each audio file
            for audio_file in audio_files:
                try:
                    LOGGER.info(f"Processing lyrics for: {audio_file.name}")

                    # Extract metadata
                    metadata = await self._extract_audio_metadata(audio_file)
                    if not metadata:
                        LOGGER.warning(
                            f"Could not extract metadata from: {audio_file.name}"
                        )
                        continue

                    # Fetch lyrics from Tidal API
                    lyrics_content = await self._fetch_tidal_lyrics(metadata)

                    if lyrics_content:
                        # Embed lyrics in the audio file
                        await self._embed_lyrics_with_xtra(
                            audio_file, lyrics_content
                        )
                        LOGGER.info(
                            f"Successfully embedded lyrics for: {audio_file.name}"
                        )

                        # Create separate .lrc file (since we're not using tidal-dl-ng for download)
                        await self._create_lrc_file(audio_file, lyrics_content)
                        LOGGER.info(
                            f"Successfully created .lrc file for: {audio_file.name}"
                        )
                    else:
                        LOGGER.info(
                            f"No lyrics found for: {metadata.get('artist', 'Unknown')} - {metadata.get('title', 'Unknown')}"
                        )

                    LOGGER.info(
                        f"Successfully processed lyrics for: {audio_file.name}"
                    )

                except Exception as file_error:
                    LOGGER.error(
                        f"Error processing lyrics for {audio_file.name}: {file_error}"
                    )
                    continue

            # Since we're skipping placeholder lyrics, just log completion
            LOGGER.info(
                f"Lyrics processing completed: {len(audio_files)} files processed (placeholder lyrics skipped)"
            )

        except Exception as e:
            LOGGER.error(f"Tidal lyrics fetching failed: {e}", exc_info=True)

    async def _fetch_tidal_lyrics(self, metadata: dict) -> str:
        """Fetch lyrics from Tidal using module-based approach"""
        try:
            artist = metadata.get("artist", "").strip()
            title = metadata.get("title", "").strip()

            if not artist or not title:
                LOGGER.warning("Missing artist or title for lyrics search")
                return None

            LOGGER.info(f"Searching Tidal for lyrics: {artist} - {title}")

            # Use proper tidalapi authentication with config_cache
            try:
                from datetime import datetime

                import tidalapi

                # Get Tidal credentials from config_cache (optimized)
                access_token = Config.TIDAL_ACCESS_TOKEN
                refresh_token = Config.TIDAL_REFRESH_TOKEN
                expiry_time = Config.TIDAL_EXPIRY_TIME

                if not access_token:
                    LOGGER.warning("No Tidal access token found in config")
                    return None

                LOGGER.info("Using Tidal credentials from config_cache")

                # Create tidalapi session
                session = tidalapi.Session()

                # Convert expiry time to datetime if provided
                expiry_datetime = None
                if expiry_time and expiry_time > 0:
                    expiry_datetime = datetime.fromtimestamp(expiry_time)

                # Load OAuth session with config credentials
                auth_success = session.load_oauth_session(
                    token_type="Bearer",
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expiry_time=expiry_datetime,
                )

                if not auth_success:
                    LOGGER.warning(
                        "Failed to authenticate with Tidal using config credentials"
                    )

                    # Try to refresh token if refresh_token is available
                    if refresh_token:
                        LOGGER.info("Attempting to refresh Tidal token...")
                        refresh_success = session.token_refresh(refresh_token)
                        if refresh_success:
                            LOGGER.info("Successfully refreshed Tidal token")
                            # Update config with new tokens (optional - could save back to config)
                        else:
                            LOGGER.warning("Failed to refresh Tidal token")
                            return None
                    else:
                        return None

                # Verify authentication
                if not session.check_login():
                    LOGGER.warning("Tidal authentication verification failed")
                    return None

                LOGGER.info("Successfully authenticated with Tidal")

                # Search for the track
                search_query = f"{artist} {title}"
                LOGGER.info(f"Searching Tidal for: {search_query}")

                search_results = session.search(
                    search_query, models=[tidalapi.Track], limit=5
                )

                if not search_results or not search_results.get("tracks"):
                    LOGGER.info(f"No tracks found on Tidal for: {search_query}")
                    return None

                tracks = search_results["tracks"]

                # Find the best match
                best_match = None
                for track in tracks:
                    track_title = track.name.lower() if track.name else ""
                    track_artist = (
                        track.artist.name.lower()
                        if track.artist and track.artist.name
                        else ""
                    )

                    # Simple matching logic
                    if (
                        title.lower() in track_title or track_title in title.lower()
                    ) and (
                        artist.lower() in track_artist
                        or track_artist in artist.lower()
                    ):
                        best_match = track
                        break

                if not best_match:
                    # Fallback to first result
                    best_match = tracks[0]

                LOGGER.info(
                    f"Found Tidal track: {best_match.name} by {best_match.artist.name} (ID: {best_match.id})"
                )

                # Fetch lyrics
                try:
                    lyrics = best_match.lyrics()
                    if lyrics:
                        # Prioritize time-synced lyrics (subtitles) over plain text
                        if lyrics.subtitles and lyrics.subtitles.strip():
                            # Time-synced lyrics are available
                            lyrics_content = lyrics.subtitles.strip()
                            LOGGER.info(
                                f"Successfully fetched time-synced lyrics from Tidal ({len(lyrics_content)} chars)"
                            )
                            return lyrics_content

                        # Fallback to plain text lyrics if no time-sync available
                        if lyrics.text and lyrics.text.strip():
                            lyrics_content = lyrics.text.strip()
                            LOGGER.info(
                                f"Successfully fetched plain text lyrics from Tidal ({len(lyrics_content)} chars)"
                            )
                            return lyrics_content

                    LOGGER.info("No lyrics available for this track on Tidal")
                    return None
                except Exception as e:
                    LOGGER.info(f"No lyrics available for this track: {e}")
                    return None

            except ImportError as e:
                LOGGER.warning(f"tidalapi not available: {e}")
                return None
            except Exception as e:
                LOGGER.warning(f"Tidal lyrics fetch failed: {e}")
                return None

        except Exception as e:
            LOGGER.error(f"Error fetching Tidal lyrics: {e}", exc_info=True)
            return None

    async def _extract_audio_metadata(self, audio_file: Path) -> dict:
        """Extract metadata from audio file using mutagen"""
        try:
            LOGGER.info(f"Extracting metadata from: {audio_file.name}")
            import mutagen

            metadata_file = mutagen.File(audio_file)
            if not metadata_file:
                LOGGER.warning(f"Mutagen could not read file: {audio_file.name}")
                return None

            # Extract common metadata fields
            metadata = {
                "title": self._get_metadata_value(
                    metadata_file, ["TIT2", "TITLE", "\xa9nam"]
                ),
                "artist": self._get_metadata_value(
                    metadata_file, ["TPE1", "ARTIST", "\xa9ART"]
                ),
                "album": self._get_metadata_value(
                    metadata_file, ["TALB", "ALBUM", "\xa9alb"]
                ),
                "duration": getattr(metadata_file.info, "length", 0),
            }

            LOGGER.info(f"Extracted metadata: {metadata}")
            return metadata

        except Exception as e:
            LOGGER.error(f"Metadata extraction failed for {audio_file.name}: {e}")
            return None

    def _get_metadata_value(self, metadata, keys):
        """Extract metadata value using multiple possible keys"""
        for key in keys:
            if key in metadata:
                value = metadata[key]
                if isinstance(value, list) and value:
                    return str(value[0])
                if value:
                    return str(value)
        return None

    async def _embed_lyrics_with_xtra(self, audio_file: Path, lyrics_content: str):
        """Embed lyrics in audio file using xtra (ffmpeg)"""
        try:
            LOGGER.info(f"Embedding lyrics in: {audio_file.name}")

            # Use xtra (ffmpeg) to embed lyrics as metadata only
            output_file = (
                audio_file.parent
                / f"{audio_file.stem}_with_lyrics{audio_file.suffix}"
            )

            cmd = [
                "xtra",  # Renamed ffmpeg binary
                "-i",
                str(audio_file),
                "-c",
                "copy",
                "-metadata",
                f"lyrics={lyrics_content}",
                str(output_file),
            ]

            LOGGER.info(f"Xtra command: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # Replace original file with lyrics-embedded version
                audio_file.unlink()
                output_file.rename(audio_file)
                LOGGER.info(f"Successfully embedded lyrics in: {audio_file.name}")
            else:
                LOGGER.error(f"Xtra embedding failed: {stderr.decode()}")

        except Exception as e:
            LOGGER.error(f"Lyrics embedding failed for {audio_file.name}: {e}")

    async def _create_lrc_file(self, audio_file: Path, lyrics_content: str):
        """Create separate .lrc file for Qobuz downloads with Tidal lyrics"""
        try:
            # Create .lrc file with same name as audio file
            lrc_file = audio_file.parent / f"{audio_file.stem}.lrc"

            LOGGER.info(f"Creating .lrc file: {lrc_file.name}")

            # Check if lyrics are already in LRC format (time-synced)
            is_time_synced = self._is_lrc_format(lyrics_content)

            if is_time_synced:
                LOGGER.info("Lyrics are time-synced (LRC format)")
            else:
                LOGGER.info("Lyrics are plain text (no time sync)")

            # Write lyrics content to .lrc file with UTF-8 encoding
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(lyrics_content)

            LOGGER.info(f"Successfully created .lrc file: {lrc_file.name}")

        except Exception as e:
            LOGGER.error(f"Failed to create .lrc file for {audio_file.name}: {e}")

    def _is_lrc_format(self, lyrics_content: str) -> bool:
        """Check if lyrics content is in LRC format (time-synced)"""
        try:
            # LRC format contains timestamps like [00:12.34] or [01:23.45]
            import re

            lrc_pattern = r"\[\d{2}:\d{2}\.\d{2}\]"
            return bool(re.search(lrc_pattern, lyrics_content))
        except Exception:
            return False


class AppleDownloader:
    """Apple Music downloader using gamdl CLI with comprehensive validation and format detection"""

    def __init__(self, listener: MusicDownloadListener):
        self.listener = listener
        self.config = listener.config
        LOGGER.info(f"AppleDownloader initialized for {listener.uid}")

    async def download(self, url: str) -> bool:
        """Download from Apple Music with comprehensive options and validation"""
        LOGGER.info(f"Starting Apple Music download for URL: {url}")
        try:
            # Validate configuration
            if not await self._validate_config():
                return False

            # Check for cookies file - prioritize uploaded private file over config path
            cookies_path = await self._get_cookies_file_path()
            if not cookies_path:
                LOGGER.error("Apple Music cookies file not found!")
                LOGGER.error(
                    "Please upload cookies.txt via Bot Settings > Private Files"
                )
                LOGGER.error(
                    "Or export cookies from your Apple Music browser session:"
                )
                LOGGER.error("Firefox: Use 'Export Cookies' extension")
                LOGGER.error("Chrome/Edge: Use 'Get cookies.txt LOCALLY' extension")
                return False

            LOGGER.info(f"Using cookies file: {cookies_path}")

            # Verify cookies file exists and is accessible
            if not await aiopath.exists(cookies_path):
                LOGGER.error(f"Cookies file not found at path: {cookies_path}")
                return False

            # Log cookies file size for debugging
            try:
                cookies_size = await aiopath.getsize(cookies_path)
                LOGGER.info(f"Cookies file size: {cookies_size} bytes")
                LOGGER.info(
                    f"Cookies file absolute path: {Path(cookies_path).resolve()}"
                )
            except Exception as e:
                LOGGER.warning(f"Could not get cookies file size: {e}")

            # Ensure we have absolute path for gamdl (since it runs from download_dir)
            cookies_path = str(Path(cookies_path).resolve())

            # Handle batch URL processing if enabled
            if self.config.apple_read_urls_as_txt:
                url = await self._handle_batch_urls(url)

            # Build gamdl command with validated configuration options
            cmd = await self._build_gamdl_command(url, cookies_path)

            LOGGER.info(f"Apple Music command: {' '.join(cmd)}")

            # Execute download
            await self.listener.update_progress(
                status="🍎 Downloading from Apple Music..."
            )

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.listener.download_dir,
            )

            self.listener.process = process
            LOGGER.info(f"Apple Music process started with PID: {process.pid}")

            stdout, stderr = await process.communicate()

            LOGGER.info(
                f"Apple Music process completed with return code: {process.returncode}"
            )

            # Log output for debugging
            if stdout:
                stdout_text = stdout.decode()
                LOGGER.info(
                    f"DEBUG: Apple Music stdout (first 1000 chars): {stdout_text[:1000]}"
                )

            if stderr:
                stderr_text = stderr.decode()
                LOGGER.info(
                    f"DEBUG: Apple Music stderr (first 500 chars): {stderr_text[:500]}"
                )

            if process.returncode == 0:
                LOGGER.info("Apple Music download successful, processing output...")
                await self._process_apple_output(stdout.decode())

                # Convert format if needed (intelligent format detection)
                await self._handle_format_conversion()

                return True
            error_msg = await self._parse_gamdl_error(
                stderr.decode() if stderr else "Unknown error"
            )
            LOGGER.error(f"Apple Music download failed: {error_msg}")
            return False

        except Exception as e:
            LOGGER.error(f"Apple Music download error: {e}", exc_info=True)
            return False

    async def _validate_config(self) -> bool:
        """Validate Apple Music configuration options"""
        try:
            # Validate codec choices
            valid_song_codecs = [
                "aac-legacy",
                "aac-he-legacy",
                "aac",
                "aac-he",
                "aac-binaural",
                "aac-downmix",
                "aac-he-binaural",
                "aac-he-downmix",
                "atmos",
                "ac3",
                "alac",
                "ask",
            ]
            if self.config.apple_codec_song not in valid_song_codecs:
                LOGGER.error(f"Invalid song codec: {self.config.apple_codec_song}")
                LOGGER.error(f"Valid codecs: {', '.join(valid_song_codecs)}")
                return False

            valid_video_codecs = ["h264", "h265", "ask"]
            if self.config.apple_codec_music_video not in valid_video_codecs:
                LOGGER.error(
                    f"Invalid video codec: {self.config.apple_codec_music_video}"
                )
                LOGGER.error(f"Valid codecs: {', '.join(valid_video_codecs)}")
                return False

            # Validate formats
            valid_lyrics_formats = ["lrc", "srt", "ttml"]
            if self.config.apple_synced_lyrics_format not in valid_lyrics_formats:
                LOGGER.error(
                    f"Invalid lyrics format: {self.config.apple_synced_lyrics_format}"
                )
                return False

            valid_cover_formats = ["jpg", "png", "raw"]
            if self.config.apple_cover_format not in valid_cover_formats:
                LOGGER.error(
                    f"Invalid cover format: {self.config.apple_cover_format}"
                )
                return False

            # Validate modes
            valid_download_modes = ["ytdlp", "nm3u8dlre"]
            if self.config.apple_download_mode not in valid_download_modes:
                LOGGER.error(
                    f"Invalid download mode: {self.config.apple_download_mode}"
                )
                return False

            valid_remux_modes = ["ffmpeg", "mp4box"]
            if self.config.apple_remux_mode not in valid_remux_modes:
                LOGGER.error(f"Invalid remux mode: {self.config.apple_remux_mode}")
                return False

            # Validate dependencies
            if (
                self.config.apple_cover_format == "raw"
                and not self.config.apple_save_cover
            ):
                LOGGER.warning("Raw cover format requires save_cover to be enabled")
                self.config.apple_save_cover = True

            # Warn about experimental codecs
            experimental_codecs = [
                "aac",
                "aac-he",
                "aac-binaural",
                "aac-downmix",
                "aac-he-binaural",
                "aac-he-downmix",
                "atmos",
                "ac3",
                "alac",
            ]
            if self.config.apple_codec_song in experimental_codecs:
                LOGGER.warning(
                    f"⚠️ Using experimental codec: {self.config.apple_codec_song}"
                )
                LOGGER.warning(
                    "Experimental codecs are not guaranteed to work due to API limitations"
                )

            return True

        except Exception as e:
            LOGGER.error(f"Configuration validation failed: {e}")
            return False

    async def _build_gamdl_command(self, url: str, cookies_path: str) -> list:
        """Build gamdl command with all validated options"""
        cmd = ["gamdl"]

        # Add URL first
        cmd.append(url)

        # Authentication and basic settings
        cmd.extend(["--cookies-path", str(cookies_path)])
        cmd.extend(["--output-path", self.listener.download_dir])
        cmd.extend(["--temp-path", self.config.apple_temp_path])
        cmd.extend(["--language", self.config.apple_language])
        cmd.extend(["--log-level", self.config.apple_log_level])

        # Quality and format settings
        cmd.extend(["--codec-song", self.config.apple_codec_song])
        cmd.extend(["--codec-music-video", self.config.apple_codec_music_video])
        cmd.extend(
            ["--synced-lyrics-format", self.config.apple_synced_lyrics_format]
        )
        cmd.extend(["--cover-format", self.config.apple_cover_format])
        cmd.extend(["--cover-size", str(self.config.apple_cover_size)])
        cmd.extend(["--quality-post", self.config.apple_quality_post])
        cmd.extend(["--download-mode", self.config.apple_download_mode])
        cmd.extend(["--remux-mode", self.config.apple_remux_mode])
        cmd.extend(
            [
                "--remux-format-music-video",
                self.config.apple_remux_format_music_video,
            ]
        )

        # Template settings (only add non-empty templates)
        if self.config.apple_template_folder_album:
            cmd.extend(
                ["--template-folder-album", self.config.apple_template_folder_album]
            )
        if self.config.apple_template_folder_compilation:
            cmd.extend(
                [
                    "--template-folder-compilation",
                    self.config.apple_template_folder_compilation,
                ]
            )
        if self.config.apple_template_file_single_disc:
            cmd.extend(
                [
                    "--template-file-single-disc",
                    self.config.apple_template_file_single_disc,
                ]
            )
        if self.config.apple_template_file_multi_disc:
            cmd.extend(
                [
                    "--template-file-multi-disc",
                    self.config.apple_template_file_multi_disc,
                ]
            )
        if self.config.apple_template_folder_no_album:
            cmd.extend(
                [
                    "--template-folder-no-album",
                    self.config.apple_template_folder_no_album,
                ]
            )
        if self.config.apple_template_file_no_album:
            cmd.extend(
                [
                    "--template-file-no-album",
                    self.config.apple_template_file_no_album,
                ]
            )
        if self.config.apple_template_file_playlist:
            cmd.extend(
                [
                    "--template-file-playlist",
                    self.config.apple_template_file_playlist,
                ]
            )
        if self.config.apple_template_date:
            cmd.extend(["--template-date", self.config.apple_template_date])

        # Binary paths (use bot's renamed binaries)
        cmd.extend(["--ffmpeg-path", self.config.apple_ffmpeg_path])
        cmd.extend(["--mp4decrypt-path", self.config.apple_mp4decrypt_path])
        cmd.extend(["--mp4box-path", self.config.apple_mp4box_path])
        cmd.extend(["--nm3u8dlre-path", self.config.apple_nm3u8dlre_path])

        # Optional settings
        if self.config.apple_wvd_path:
            cmd.extend(["--wvd-path", self.config.apple_wvd_path])
        if self.config.apple_exclude_tags:
            cmd.extend(["--exclude-tags", self.config.apple_exclude_tags])
        if self.config.apple_truncate > 0:
            cmd.extend(["--truncate", str(self.config.apple_truncate)])

        # Boolean flags
        if self.config.apple_disable_music_video_skip:
            cmd.append("--disable-music-video-skip")
        if self.config.apple_save_cover:
            cmd.append("--save-cover")
        if self.config.apple_overwrite:
            cmd.append("--overwrite")
        if self.config.apple_save_playlist:
            cmd.append("--save-playlist")
        if self.config.apple_synced_lyrics_only:
            cmd.append("--synced-lyrics-only")
        if self.config.apple_no_synced_lyrics:
            cmd.append("--no-synced-lyrics")
        if self.config.apple_no_exceptions:
            cmd.append("--no-exceptions")
        if self.config.apple_read_urls_as_txt:
            cmd.append("--read-urls-as-txt")
        if self.config.apple_no_config_file:
            cmd.append("--no-config-file")

        return cmd

    async def _handle_batch_urls(self, url: str) -> str:
        """Handle batch URL processing if enabled"""
        # For now, just return the original URL
        # This could be extended to handle text files with multiple URLs
        return url

    async def _parse_gamdl_error(self, error_text: str) -> str:
        """Parse gamdl error messages for better user feedback"""
        error_lower = error_text.lower()

        if "cookies" in error_lower or "authentication" in error_lower:
            return "Authentication failed - please check your cookies file"
        if "network" in error_lower or "connection" in error_lower:
            return "Network error - please check your internet connection"
        if "not found" in error_lower:
            return "Content not found - the URL may be invalid or region-locked"
        if "subscription" in error_lower:
            return "Subscription required - please ensure you have an active Apple Music subscription"
        if "codec" in error_lower:
            return "Codec error - the selected codec may not be available for this content"
        return error_text

    async def _handle_format_conversion(self):
        """Handle format conversion with intelligent format detection"""
        try:
            # Detect actual output format based on codec
            expected_format = self._get_expected_format_from_codec()

            # Only convert if target format differs from expected output
            if (
                self.config.format
                and self.config.format.lower() != expected_format.lower()
            ):
                LOGGER.info(
                    f"Converting from {expected_format} to {self.config.format}"
                )
                await self._convert_audio_format()
            else:
                LOGGER.info(
                    f"No conversion needed - output format matches target: {expected_format}"
                )

        except Exception as e:
            LOGGER.error(f"Format conversion handling failed: {e}")

    def _get_expected_format_from_codec(self) -> str:
        """Get expected output format based on selected codec"""
        codec_format_map = {
            "aac-legacy": "m4a",
            "aac-he-legacy": "m4a",
            "aac": "m4a",
            "aac-he": "m4a",
            "aac-binaural": "m4a",
            "aac-downmix": "m4a",
            "aac-he-binaural": "m4a",
            "aac-he-downmix": "m4a",
            "atmos": "m4a",
            "ac3": "m4a",
            "alac": "m4a",  # ALAC is in M4A container
        }
        return codec_format_map.get(self.config.apple_codec_song, "m4a")

    async def _get_cookies_file_path(self) -> str | None:
        """Get cookies file path - prioritize uploaded private file over config path"""
        try:
            # First, check for uploaded cookies.txt in private files
            from bot.helper.ext_utils.db_handler import database

            if database.db is not None:
                # Check if cookies.txt exists in private files
                private_files = await database.get_private_files()
                if "cookies.txt" in private_files:
                    file_info = private_files["cookies.txt"]

                    # Check if file exists in filesystem
                    if file_info.get("fs_exists", False):
                        cookies_path = "cookies.txt"
                        if await aiopath.exists(cookies_path):
                            LOGGER.info(
                                "Using uploaded cookies.txt from Private Files"
                            )
                            # Return absolute path for gamdl
                            return str(Path(cookies_path).resolve())

                    # If not in filesystem but in database, sync it
                    if file_info.get("db_exists", False):
                        LOGGER.info(
                            "Syncing cookies.txt from database to filesystem..."
                        )
                        try:
                            sync_result = await database.sync_private_files_to_fs()
                            if sync_result.get("synced", 0) > 0:
                                cookies_path = "cookies.txt"
                                if await aiopath.exists(cookies_path):
                                    LOGGER.info(
                                        "Successfully synced and using cookies.txt from Private Files"
                                    )
                                    # Return absolute path for gamdl
                                    return str(Path(cookies_path).resolve())
                        except Exception as e:
                            LOGGER.error(
                                f"Failed to sync cookies.txt from database: {e}"
                            )

            # Fallback to config path
            config_cookies_path = Path(self.config.apple_cookies_path)
            if config_cookies_path.exists():
                LOGGER.info(
                    f"Using cookies file from config path: {config_cookies_path}"
                )
                # Return absolute path for gamdl
                return str(config_cookies_path.resolve())

            # No cookies file found
            return None

        except Exception as e:
            LOGGER.error(f"Error getting cookies file path: {e}")
            # Fallback to config path
            config_cookies_path = Path(self.config.apple_cookies_path)
            if config_cookies_path.exists():
                # Return absolute path for gamdl
                return str(config_cookies_path.resolve())
            return None

    async def _process_apple_output(self, output: str):
        """Process gamdl output and update listener"""
        try:
            LOGGER.info("Processing Apple Music download output...")

            # Parse output for downloaded files
            lines = output.split("\n")

            for line in lines:
                # Look for download completion indicators in gamdl output
                if "Downloaded:" in line or "Saved:" in line:
                    # Extract file path if possible
                    LOGGER.info(f"Apple Music: {line.strip()}")

            # Update listener with download info
            self.listener.status = "✅ Apple Music download completed"
            self.listener.is_completed = True

            LOGGER.info("Apple Music output processing completed")

        except Exception as e:
            LOGGER.error(f"Error processing Apple Music output: {e}")

    async def _convert_audio_format(self):
        """Convert audio format with intelligent format detection"""
        try:
            target_format = self.config.format.lower()
            expected_format = self._get_expected_format_from_codec()

            LOGGER.info(
                f"Converting Apple Music files from {expected_format.upper()} to {target_format.upper()}"
            )

            # Find audio files in download directory with broader extension support
            download_path = Path(self.listener.download_dir)
            audio_extensions = [".m4a", ".aac", ".mp4", ".flac", ".alac"]
            audio_files = []

            for ext in audio_extensions:
                audio_files.extend(download_path.rglob(f"*{ext}"))

            if not audio_files:
                LOGGER.warning("No audio files found for conversion")
                return

            LOGGER.info(f"Found {len(audio_files)} audio files to convert")

            for audio_file in audio_files:
                # Skip if already in target format
                if audio_file.suffix.lower() == f".{target_format}":
                    LOGGER.info(
                        f"Skipping {audio_file.name} - already in target format"
                    )
                    continue

                await self._convert_single_file(audio_file)

        except Exception as e:
            LOGGER.error(f"Audio format conversion failed: {e}")

    async def _convert_single_file(self, audio_file: Path):
        """Convert a single audio file to target format"""
        try:
            output_file = (
                audio_file.parent / f"{audio_file.stem}.{self.config.format}"
            )

            # Use xtra (renamed ffmpeg) for conversion
            cmd = [
                "xtra",
                "-i",
                str(audio_file),
                "-c:a",
                self._get_codec_for_format(self.config.format),
                "-b:a",
                "320k",  # High quality bitrate
                str(output_file),
            ]

            LOGGER.info(f"Converting: {audio_file.name} -> {output_file.name}")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # Remove original file and keep converted one
                audio_file.unlink()
                LOGGER.info(f"Successfully converted: {output_file.name}")
            else:
                LOGGER.error(
                    f"Conversion failed for {audio_file.name}: {stderr.decode()}"
                )

        except Exception as e:
            LOGGER.error(f"Failed to convert {audio_file.name}: {e}")

    def _get_codec_for_format(self, format_name: str) -> str:
        """Get appropriate codec for target format"""
        codec_map = {
            "mp3": "libmp3lame",
            "flac": "flac",
            "ogg": "libvorbis",
            "wav": "pcm_s16le",
            "aac": "aac",
        }
        return codec_map.get(format_name.lower(), "libmp3lame")


class SpotifyDownloader:
    """Spotify downloader using deezspot library"""

    def __init__(self, listener: MusicDownloadListener):
        self.listener = listener
        self.config = listener.config
        LOGGER.info(f"SpotifyDownloader initialized for {listener.uid}")

        # Load configuration from cache
        # Note: spotify_credentials_path will be set async in _setup_spotify_auth
        self.spotify_credentials_path = None
        self.spotify_client_id = Config.SPOTIFY_CLIENT_ID
        self.spotify_client_secret = Config.SPOTIFY_CLIENT_SECRET
        self.spotify_quality = Config.SPOTIFY_QUALITY
        self.spotify_recursive_quality = Config.SPOTIFY_RECURSIVE_QUALITY
        self.spotify_recursive_download = Config.SPOTIFY_RECURSIVE_DOWNLOAD
        self.spotify_not_interface = Config.SPOTIFY_NOT_INTERFACE
        self.spotify_method_save = Config.SPOTIFY_METHOD_SAVE
        self.spotify_make_zip = Config.SPOTIFY_MAKE_ZIP
        self.spotify_is_thread = Config.SPOTIFY_IS_THREAD

    async def download(self, url: str) -> bool:
        """Download from Spotify using deezspot library"""
        LOGGER.info(f"Starting Spotify download for URL: {url}")
        try:
            if not DEEZSPOT_AVAILABLE:
                LOGGER.error("DeezSpot library not available")
                return False

            # Validate URL using deezspot utilities
            try:
                link_is_valid(url)
                LOGGER.info("Spotify URL validation successful")
            except InvalidLink as e:
                LOGGER.error(f"Invalid Spotify URL: {e}")
                return False

            # Validate quality setting
            if self.spotify_quality not in spotify_qualities:
                LOGGER.error(
                    f"Invalid Spotify quality: {self.spotify_quality}. Valid options: {list(spotify_qualities.keys())}"
                )
                return False

            # Setup authentication
            LOGGER.info("Setting up Spotify authentication...")
            auth_success = await self._setup_spotify_auth()
            if not auth_success:
                LOGGER.error("Spotify authentication failed")
                return False
            LOGGER.info("Spotify authentication successful")

            # Create SpoLogin instance with retry logic
            spotify = None
            max_retries = 3
            retry_delay = 2

            for attempt in range(max_retries):
                try:
                    LOGGER.info(
                        f"Initializing Spotify connection (attempt {attempt + 1}/{max_retries})..."
                    )
                    spotify = SpoLogin(
                        credentials_path=self.spotify_credentials_path,
                        client_id=self.spotify_client_id,
                        client_secret=self.spotify_client_secret,
                    )
                    LOGGER.info("Spotify connection initialized successfully")
                    break
                except ConnectionRefusedError as e:
                    LOGGER.warning(
                        f"Spotify connection attempt {attempt + 1}/{max_retries} failed: {e}"
                    )
                    if attempt < max_retries - 1:
                        LOGGER.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        LOGGER.error("All Spotify connection attempts failed")
                        raise ConnectionRefusedError(
                            "Unable to connect to Spotify servers. This could be due to:\n"
                            "1. Network connectivity issues\n"
                            "2. Spotify server maintenance\n"
                            "3. Firewall/proxy blocking the connection\n"
                            "Please check your network connection and try again later."
                        )
                except Exception as e:
                    LOGGER.error(
                        f"Spotify connection error (attempt {attempt + 1}): {e}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise

            if not spotify:
                raise ConnectionRefusedError(
                    "Failed to initialize Spotify connection after all retries"
                )

            # Determine download type from URL using deezspot utilities
            download_type = self._detect_spotify_url_type(url)
            LOGGER.info(f"Detected Spotify URL type: {download_type}")

            # Execute download based on type
            success = await self._execute_spotify_download(
                spotify, url, download_type
            )

            if success:
                LOGGER.info("Spotify download completed successfully")
                return True
            LOGGER.error("Spotify download failed")
            return False

        except BadCredentials as e:
            LOGGER.error(f"Spotify authentication failed: {e}")
            return False
        except QuotaExceeded as e:
            LOGGER.error(f"Spotify quota exceeded: {e}")
            return False
        except TrackNotFound as e:
            LOGGER.error(f"Spotify track not found: {e}")
            return False
        except ConnectionRefusedError as e:
            LOGGER.error(f"Spotify connection refused: {e}")
            return False
        except Exception as e:
            # Check for Spotify OAuth errors (invalid API credentials)
            if "SpotifyOauthError" in str(type(e)) or "invalid_client" in str(e):
                LOGGER.error(f"Spotify API credentials error: {e}")
                LOGGER.error(
                    "This error occurs because you need valid Spotify API credentials."
                )
                LOGGER.error("To fix this:")
                LOGGER.error("1. Go to https://developer.spotify.com/dashboard")
                LOGGER.error("2. Create a new app")
                LOGGER.error("3. Get your client_id and client_secret")
                LOGGER.error("4. Add them to your credentials.json file")
                return False
            LOGGER.error(f"Spotify download error: {e}", exc_info=True)
            return False

    async def _get_spotify_credentials_path_from_private_files(self) -> str:
        """Get Spotify credentials path from private files or config"""
        try:
            from bot.helper.ext_utils.db_handler import database

            if database.db is not None:
                # Check if spotify_credentials.json exists in private files
                private_files = await database.get_private_files()
                if "spotify_credentials.json" in private_files:
                    file_info = private_files["spotify_credentials.json"]

                    # Check if file exists in filesystem
                    if file_info.get("fs_exists", False):
                        credentials_path = "spotify_credentials.json"
                        if await aiopath.exists(credentials_path):
                            LOGGER.info(
                                "Using uploaded spotify_credentials.json from Private Files"
                            )
                            return str(Path(credentials_path).resolve())

                    # If not in filesystem but in database, sync it
                    if file_info.get("db_exists", False):
                        LOGGER.info(
                            "Syncing spotify_credentials.json from database to filesystem..."
                        )
                        try:
                            sync_result = await database.sync_private_files_to_fs()
                            if sync_result.get("synced", 0) > 0:
                                credentials_path = "spotify_credentials.json"
                                if await aiopath.exists(credentials_path):
                                    LOGGER.info(
                                        "Successfully synced and using spotify_credentials.json from Private Files"
                                    )
                                    return str(Path(credentials_path).resolve())
                        except Exception as e:
                            LOGGER.error(
                                f"Failed to sync spotify_credentials.json from database: {e}"
                            )

            # Fallback to config path
            config_credentials_path = Path(Config.SPOTIFY_CREDENTIALS_PATH)
            if config_credentials_path.exists():
                LOGGER.info(
                    f"Using credentials file from config path: {config_credentials_path}"
                )
                return str(config_credentials_path.resolve())

            # Return config path even if it doesn't exist (for error handling)
            return Config.SPOTIFY_CREDENTIALS_PATH

        except Exception as e:
            LOGGER.error(f"Error getting Spotify credentials file path: {e}")
            return Config.SPOTIFY_CREDENTIALS_PATH

    async def _setup_spotify_auth(self) -> bool:
        """Setup Spotify authentication"""
        try:
            # Get credentials path from Private Files first, then fallback to config
            self.spotify_credentials_path = (
                await self._get_spotify_credentials_path_from_private_files()
            )

            # Check if credentials file exists
            credentials_path = Path(self.spotify_credentials_path)
            if not credentials_path.exists():
                LOGGER.error(
                    f"Spotify credentials file not found: {credentials_path}"
                )
                LOGGER.info(
                    "Upload credentials.json via Bot Settings > Private Files or use librespot-auth"
                )
                return False

            # Validate credentials file format
            try:
                import json

                with open(credentials_path) as f:
                    creds = json.load(f)

                required_fields = ["username", "credentials", "type"]
                if not all(field in creds for field in required_fields):
                    LOGGER.error(
                        "Invalid credentials file format. Required fields: username, credentials, type"
                    )
                    return False

                # Additional validation for credentials type
                if creds.get("type") != "AUTHENTICATION_STORED_SPOTIFY_CREDENTIALS":
                    LOGGER.warning(
                        f"Unexpected credentials type: {creds.get('type')}"
                    )

                LOGGER.info("Spotify credentials file validated successfully")
                return True

            except json.JSONDecodeError:
                LOGGER.error("Invalid JSON in credentials file")
                return False

        except Exception as e:
            LOGGER.error(f"Spotify authentication setup failed: {e}")
            return False

    def _detect_spotify_url_type(self, url: str) -> str:
        """Detect Spotify URL type (track, album, playlist, episode)"""
        url_lower = url.lower()
        if "/track/" in url_lower:
            return "track"
        if "/album/" in url_lower:
            return "album"
        if "/playlist/" in url_lower:
            return "playlist"
        if "/episode/" in url_lower:
            return "episode"
        return "track"  # Default fallback

    async def _execute_spotify_download(
        self, spotify, url: str, download_type: str
    ) -> bool:
        """Execute Spotify download based on type"""
        try:
            output_dir = self.listener.download_dir

            LOGGER.info(
                f"Downloading {download_type} with quality {self.spotify_quality}"
            )
            LOGGER.info(f"Output directory: {output_dir}")

            # Run the synchronous deezspot methods in a thread pool to avoid blocking
            import asyncio

            loop = asyncio.get_event_loop()

            if download_type == "track":
                await loop.run_in_executor(
                    None,
                    lambda: spotify.download_track(
                        link_track=url,
                        output_dir=output_dir,
                        quality_download=self.spotify_quality,
                        recursive_quality=self.spotify_recursive_quality,
                        recursive_download=self.spotify_recursive_download,
                        not_interface=self.spotify_not_interface,
                        method_save=self.spotify_method_save,
                        is_thread=self.spotify_is_thread,
                    ),
                )
            elif download_type == "album":
                await loop.run_in_executor(
                    None,
                    lambda: spotify.download_album(
                        link_album=url,
                        output_dir=output_dir,
                        quality_download=self.spotify_quality,
                        recursive_quality=self.spotify_recursive_quality,
                        recursive_download=self.spotify_recursive_download,
                        not_interface=self.spotify_not_interface,
                        method_save=self.spotify_method_save,
                        make_zip=self.spotify_make_zip,
                        is_thread=self.spotify_is_thread,
                    ),
                )
            elif download_type == "playlist":
                await loop.run_in_executor(
                    None,
                    lambda: spotify.download_playlist(
                        link_playlist=url,
                        output_dir=output_dir,
                        quality_download=self.spotify_quality,
                        recursive_quality=self.spotify_recursive_quality,
                        recursive_download=self.spotify_recursive_download,
                        not_interface=self.spotify_not_interface,
                        method_save=self.spotify_method_save,
                        make_zip=self.spotify_make_zip,
                        is_thread=self.spotify_is_thread,
                    ),
                )
            elif download_type == "episode":
                await loop.run_in_executor(
                    None,
                    lambda: spotify.download_episode(
                        link_episode=url,
                        output_dir=output_dir,
                        quality_download=self.spotify_quality,
                        recursive_quality=self.spotify_recursive_quality,
                        recursive_download=self.spotify_recursive_download,
                        not_interface=self.spotify_not_interface,
                        method_save=self.spotify_method_save,
                        is_thread=self.spotify_is_thread,
                    ),
                )
            else:
                LOGGER.error(f"Unsupported Spotify download type: {download_type}")
                return False

            LOGGER.info(f"Spotify {download_type} download completed")
            return True

        except Exception as e:
            LOGGER.error(f"Spotify download execution failed: {e}", exc_info=True)
            return False


class DeezerDownloader:
    """Deezer downloader using deezspot library"""

    def __init__(self, listener: MusicDownloadListener):
        self.listener = listener
        self.config = listener.config
        LOGGER.info(f"DeezerDownloader initialized for {listener.uid}")

        # Load configuration from cache
        self.deezer_arl = Config.DEEZER_ARL
        self.deezer_email = Config.DEEZER_EMAIL
        self.deezer_password = Config.DEEZER_PASSWORD
        self.deezer_quality = Config.DEEZER_QUALITY
        self.deezer_tags_separator = Config.DEEZER_TAGS_SEPARATOR
        self.deezer_recursive_quality = Config.DEEZER_RECURSIVE_QUALITY
        self.deezer_recursive_download = Config.DEEZER_RECURSIVE_DOWNLOAD
        self.deezer_ensure_premium = Config.DEEZER_ENSURE_PREMIUM

        # Additional Deezer settings (using defaults from deezspot library)
        self.deezer_not_interface = False  # Default from deezspot
        self.deezer_method_save = 3  # Default from deezspot (recommended)

    async def download(self, url: str) -> bool:
        """Download from Deezer using deezspot library"""
        LOGGER.info(f"Starting Deezer download for URL: {url}")
        try:
            if not DEEZSPOT_AVAILABLE:
                LOGGER.error("DeezSpot library not available")
                return False

            # Validate URL using deezspot utilities
            try:
                link_is_valid(url)
                LOGGER.info("Deezer URL validation successful")
            except InvalidLink as e:
                LOGGER.error(f"Invalid Deezer URL: {e}")
                return False

            # Validate quality setting
            if self.deezer_quality not in deezer_qualities:
                LOGGER.error(
                    f"Invalid Deezer quality: {self.deezer_quality}. Valid options: {list(deezer_qualities.keys())}"
                )
                return False

            # Check premium requirement for FLAC
            if self.deezer_quality == "FLAC" and not self.deezer_ensure_premium:
                LOGGER.warning(
                    "FLAC quality requires premium account. Set DEEZER_ENSURE_PREMIUM=True to enforce premium check."
                )

            # Setup authentication
            LOGGER.info("Setting up Deezer authentication...")
            auth_success = await self._setup_deezer_auth()
            if not auth_success:
                LOGGER.error("Deezer authentication failed")
                return False
            LOGGER.info("Deezer authentication successful")

            # Create DeeLogin instance with ensure_premium parameter
            deezer = DeeLogin(
                arl=self.deezer_arl,
                email=self.deezer_email,
                password=self.deezer_password,
                ensure_premium=self.deezer_ensure_premium,
                tags_separator=self.deezer_tags_separator,
            )

            # Determine download type from URL
            download_type = self._detect_deezer_url_type(url)
            LOGGER.info(f"Detected Deezer URL type: {download_type}")

            # Execute download based on type
            success = await self._execute_deezer_download(deezer, url, download_type)

            if success:
                LOGGER.info("Deezer download completed successfully")
                return True
            LOGGER.error("Deezer download failed")
            return False

        except BadCredentials as e:
            LOGGER.error(f"Deezer authentication failed: {e}")
            return False
        except NoRightOnMedia as e:
            LOGGER.error(f"No rights to download this media: {e}")
            return False
        except QualityNotFound as e:
            LOGGER.error(f"Quality not available: {e}")
            return False
        except TrackNotFound as e:
            LOGGER.error(f"Deezer track not found: {e}")
            return False
        except AlbumNotFound as e:
            LOGGER.error(f"Deezer album not found: {e}")
            return False
        except Exception as e:
            LOGGER.error(f"Deezer download error: {e}", exc_info=True)
            return False

    async def _setup_deezer_auth(self) -> bool:
        """Setup Deezer authentication"""
        try:
            # Check if ARL token is provided
            if not self.deezer_arl:
                LOGGER.error("Deezer ARL token not provided")
                LOGGER.info(
                    "Get your ARL token from browser cookies after logging in to Deezer"
                )
                return False

            # Basic ARL validation (should be a long string)
            if len(self.deezer_arl) < 100:
                LOGGER.error("Invalid Deezer ARL token (too short)")
                LOGGER.info("ARL token should be a long string from browser cookies")
                return False

            # Additional validation - ARL should be alphanumeric
            if not self.deezer_arl.replace("-", "").replace("_", "").isalnum():
                LOGGER.error("Invalid Deezer ARL token format")
                return False

            LOGGER.info("Deezer ARL token validated successfully")
            return True

        except Exception as e:
            LOGGER.error(f"Deezer authentication setup failed: {e}")
            return False

    def _detect_deezer_url_type(self, url: str) -> str:
        """Detect Deezer URL type (track, album, playlist, artist, episode)"""
        url_lower = url.lower()
        if "/track/" in url_lower:
            return "track"
        if "/album/" in url_lower:
            return "album"
        if "/playlist/" in url_lower:
            return "playlist"
        if "/artist/" in url_lower:
            return "artist"
        if "/episode/" in url_lower:
            return "episode"
        return "track"  # Default fallback

    async def _execute_deezer_download(
        self, deezer, url: str, download_type: str
    ) -> bool:
        """Execute Deezer download based on type"""
        try:
            output_dir = self.listener.download_dir
            quality = self.config.deezer_quality
            recursive_quality = self.config.deezer_recursive_quality
            recursive_download = self.config.deezer_recursive_download

            LOGGER.info(f"Downloading {download_type} with quality {quality}")

            # Run the synchronous deezspot methods in a thread pool to avoid blocking
            import asyncio

            loop = asyncio.get_event_loop()

            if download_type == "track":
                await loop.run_in_executor(
                    None,
                    lambda: deezer.download_trackdee(
                        link_track=url,
                        output_dir=output_dir,
                        quality_download=quality,
                        recursive_quality=recursive_quality,
                        recursive_download=recursive_download,
                        not_interface=self.deezer_not_interface,
                        method_save=self.deezer_method_save,
                    ),
                )
            elif download_type == "album":
                await loop.run_in_executor(
                    None,
                    lambda: deezer.download_albumdee(
                        link_album=url,
                        output_dir=output_dir,
                        quality_download=quality,
                        recursive_quality=recursive_quality,
                        recursive_download=recursive_download,
                        not_interface=self.deezer_not_interface,
                        make_zip=False,  # Default from deezspot
                        method_save=self.deezer_method_save,
                    ),
                )
            elif download_type == "playlist":
                await loop.run_in_executor(
                    None,
                    lambda: deezer.download_playlistdee(
                        link_playlist=url,
                        output_dir=output_dir,
                        quality_download=quality,
                        recursive_quality=recursive_quality,
                        recursive_download=recursive_download,
                        not_interface=self.deezer_not_interface,
                        make_zip=False,  # Default from deezspot
                        method_save=self.deezer_method_save,
                    ),
                )
            elif download_type == "artist":
                await loop.run_in_executor(
                    None,
                    lambda: deezer.download_artisttopdee(
                        link_artist=url,
                        output_dir=output_dir,
                        quality_download=quality,
                        recursive_quality=recursive_quality,
                        recursive_download=recursive_download,
                        not_interface=self.deezer_not_interface,
                    ),
                )
            elif download_type == "episode":
                await loop.run_in_executor(
                    None,
                    lambda: deezer.download_episode(
                        link_episode=url,
                        output_dir=output_dir,
                        quality_download=quality,
                        recursive_quality=recursive_quality,
                        recursive_download=recursive_download,
                        not_interface=self.deezer_not_interface,
                        method_save=self.deezer_method_save,
                    ),
                )
            else:
                LOGGER.error(f"Unsupported Deezer download type: {download_type}")
                return False

            LOGGER.info(f"Deezer {download_type} download completed")
            return True

        except Exception as e:
            LOGGER.error(f"Deezer download execution failed: {e}", exc_info=True)
            return False


async def _check_apple_cookies_availability() -> bool:
    """Check if Apple Music cookies file is available (private files or config path)"""
    try:
        # First, check for uploaded cookies.txt in private files
        from bot.helper.ext_utils.db_handler import database

        if database.db is not None:
            # Check if cookies.txt exists in private files
            private_files = await database.get_private_files()
            if "cookies.txt" in private_files:
                file_info = private_files["cookies.txt"]

                # Check if file exists in filesystem
                if file_info.get("fs_exists", False):
                    cookies_path = "cookies.txt"
                    if await aiopath.exists(cookies_path):
                        LOGGER.info(
                            "Found cookies.txt in Private Files (filesystem)"
                        )
                        return True

                # If not in filesystem but in database, it can be synced
                if file_info.get("db_exists", False):
                    LOGGER.info("Found cookies.txt in Private Files (database)")
                    return True

        # Fallback to config path
        config_cookies_path = Path(Config.APPLE_COOKIES_PATH)
        if config_cookies_path.exists():
            LOGGER.info(f"Found cookies file at config path: {config_cookies_path}")
            return True

        # No cookies file found
        return False

    except Exception as e:
        LOGGER.error(f"Error checking Apple Music cookies availability: {e}")
        # Fallback to config path
        config_cookies_path = Path(Config.APPLE_COOKIES_PATH)
        return config_cookies_path.exists()


# Utility functions
def detect_platform(url: str) -> str | None:
    """Detect platform from URL"""
    url_lower = url.lower()
    if "tidal.com" in url_lower:
        return "tidal"
    if "qobuz.com" in url_lower:
        return "qobuz"
    if "music.apple.com" in url_lower:
        return "apple"
    if "open.spotify.com" in url_lower or "spotify.com" in url_lower:
        return "spotify"
    if "deezer.com" in url_lower:
        return "deezer"
    return None


def parse_musicdl_flags(query: str) -> dict:
    """Parse musicdl command flags (excluding quality/format which are now menu-based)"""
    flags = {}

    # Note: Quality (-q) and Format (-fm) flags are now handled by the selection menu
    # This function only parses other flags for backward compatibility

    # Extract quality and format from menu-generated queries (for internal use)
    quality_match = re.search(r"-q\s+(\w+)", query)
    if quality_match:
        flags["quality"] = quality_match.group(1)

    format_match = re.search(r"-fm\s+(\w+)", query)
    if format_match:
        flags["format"] = format_match.group(1)

    # -dolby flag: For Tidal only (enable Dolby Atmos downloads)
    if re.search(r"-dolby\b", query):
        flags["dolby_atmos"] = True

    # Qobuz-specific boolean flags
    if re.search(r"--no-fallback\b", query):
        flags["no_fallback"] = True
    if re.search(r"--fallback\b", query):
        flags["no_fallback"] = False

    if re.search(r"--albums-only\b", query):
        flags["albums_only"] = True
    if re.search(r"--no-albums-only\b", query):
        flags["albums_only"] = False

    if re.search(r"--smart-discography\b", query):
        flags["smart_discography"] = True
    if re.search(r"--no-smart-discography\b", query):
        flags["smart_discography"] = False

    if re.search(r"--og-cover\b", query):
        flags["og_cover"] = True
    if re.search(r"--no-og-cover\b", query):
        flags["og_cover"] = False

    if re.search(r"--embed-art\b", query):
        flags["embed_art"] = True
    if re.search(r"--no-embed-art\b", query):
        flags["embed_art"] = False

    if re.search(r"--no-cover\b", query):
        flags["no_cover"] = True
    if re.search(r"--cover\b", query):
        flags["no_cover"] = False

    if re.search(r"--no-m3u\b", query):
        flags["no_m3u"] = True
    if re.search(r"--m3u\b", query):
        flags["no_m3u"] = False

    if re.search(r"--no-db\b", query):
        flags["no_database"] = True
    if re.search(r"--db\b", query):
        flags["no_database"] = False

    # Tidal-specific boolean flags
    if re.search(r"--cover-album-file\b", query):
        flags["tidal_cover_album_file"] = True
    if re.search(r"--no-cover-album-file\b", query):
        flags["tidal_cover_album_file"] = False

    if re.search(r"--download-delay\b", query):
        flags["tidal_download_delay"] = True
    if re.search(r"--no-download-delay\b", query):
        flags["tidal_download_delay"] = False

    if re.search(r"--extract-flac\b", query):
        flags["tidal_extract_flac"] = True
    if re.search(r"--no-extract-flac\b", query):
        flags["tidal_extract_flac"] = False

    if re.search(r"--lyrics-embed\b", query):
        flags["tidal_lyrics_embed"] = True
    if re.search(r"--no-lyrics-embed\b", query):
        flags["tidal_lyrics_embed"] = False

    if re.search(r"--lyrics-file\b", query):
        flags["tidal_lyrics_file"] = True
    if re.search(r"--no-lyrics-file\b", query):
        flags["tidal_lyrics_file"] = False

    if re.search(r"--metadata-cover-embed\b", query):
        flags["tidal_metadata_cover_embed"] = True
    if re.search(r"--no-metadata-cover-embed\b", query):
        flags["tidal_metadata_cover_embed"] = False

    if re.search(r"--metadata-replay-gain\b", query):
        flags["tidal_metadata_replay_gain"] = True
    if re.search(r"--no-metadata-replay-gain\b", query):
        flags["tidal_metadata_replay_gain"] = False

    if re.search(r"--playlist-create\b", query):
        flags["tidal_playlist_create"] = True
    if re.search(r"--no-playlist-create\b", query):
        flags["tidal_playlist_create"] = False

    if re.search(r"--skip-existing\b", query):
        flags["tidal_skip_existing"] = True
    if re.search(r"--no-skip-existing\b", query):
        flags["tidal_skip_existing"] = False

    if re.search(r"--symlink-to-track\b", query):
        flags["tidal_symlink_to_track"] = True
    if re.search(r"--no-symlink-to-track\b", query):
        flags["tidal_symlink_to_track"] = False

    if re.search(r"--video-convert-mp4\b", query):
        flags["tidal_video_convert_mp4"] = True
    if re.search(r"--no-video-convert-mp4\b", query):
        flags["tidal_video_convert_mp4"] = False

    if re.search(r"--video-download\b", query):
        flags["tidal_video_download"] = True
    if re.search(r"--no-video-download\b", query):
        flags["tidal_video_download"] = False

    # Tidal-specific numeric flags
    album_track_pad_match = re.search(r"--album-track-num-pad-min\s+(\d+)", query)
    if album_track_pad_match:
        flags["tidal_album_track_num_pad_min"] = int(album_track_pad_match.group(1))

    download_delay_min_match = re.search(
        r"--download-delay-sec-min\s+([\d.]+)", query
    )
    if download_delay_min_match:
        flags["tidal_download_delay_sec_min"] = float(
            download_delay_min_match.group(1)
        )

    download_delay_max_match = re.search(
        r"--download-delay-sec-max\s+([\d.]+)", query
    )
    if download_delay_max_match:
        flags["tidal_download_delay_sec_max"] = float(
            download_delay_max_match.group(1)
        )

    concurrent_max_match = re.search(r"--downloads-concurrent-max\s+(\d+)", query)
    if concurrent_max_match:
        flags["tidal_downloads_concurrent_max"] = int(concurrent_max_match.group(1))

    simultaneous_max_match = re.search(
        r"--downloads-simultaneous-per-track-max\s+(\d+)", query
    )
    if simultaneous_max_match:
        flags["tidal_downloads_simultaneous_per_track_max"] = int(
            simultaneous_max_match.group(1)
        )

    cover_dimension_match = re.search(r"--metadata-cover-dimension\s+(\d+)", query)
    if cover_dimension_match:
        flags["tidal_metadata_cover_dimension"] = int(cover_dimension_match.group(1))

    # Tidal-specific string flags
    quality_audio_match = re.search(r"--quality-audio\s+(\w+)", query)
    if quality_audio_match:
        flags["tidal_quality_audio"] = quality_audio_match.group(1)

    quality_video_match = re.search(r"--quality-video\s+(\w+)", query)
    if quality_video_match:
        flags["tidal_quality_video"] = quality_video_match.group(1)

    # Tidal format template flags (quoted strings)
    format_album_match = re.search(r'--format-album\s+"([^"]+)"', query)
    if not format_album_match:
        format_album_match = re.search(r"--format-album\s+'([^']+)'", query)
    if format_album_match:
        flags["tidal_format_album"] = format_album_match.group(1)

    format_track_match = re.search(r'--format-track\s+"([^"]+)"', query)
    if not format_track_match:
        format_track_match = re.search(r"--format-track\s+'([^']+)'", query)
    if format_track_match:
        flags["tidal_format_track"] = format_track_match.group(1)

    format_playlist_match = re.search(r'--format-playlist\s+"([^"]+)"', query)
    if not format_playlist_match:
        format_playlist_match = re.search(r"--format-playlist\s+'([^']+)'", query)
    if format_playlist_match:
        flags["tidal_format_playlist"] = format_playlist_match.group(1)

    format_mix_match = re.search(r'--format-mix\s+"([^"]+)"', query)
    if not format_mix_match:
        format_mix_match = re.search(r"--format-mix\s+'([^']+)'", query)
    if format_mix_match:
        flags["tidal_format_mix"] = format_mix_match.group(1)

    format_video_match = re.search(r'--format-video\s+"([^"]+)"', query)
    if not format_video_match:
        format_video_match = re.search(r"--format-video\s+'([^']+)'", query)
    if format_video_match:
        flags["tidal_format_video"] = format_video_match.group(1)

    # Qobuz format template flags (quoted strings)
    folder_format_match = re.search(r'--folder-format\s+"([^"]+)"', query)
    if not folder_format_match:
        folder_format_match = re.search(r"--folder-format\s+'([^']+)'", query)
    if folder_format_match:
        flags["folder_format"] = folder_format_match.group(1)

    track_format_match = re.search(r'--track-format\s+"([^"]+)"', query)
    if not track_format_match:
        track_format_match = re.search(r"--track-format\s+'([^']+)'", query)
    if track_format_match:
        flags["track_format"] = track_format_match.group(1)

    # Limit flag
    limit_match = re.search(r"--limit\s+(\d+)", query)
    if limit_match:
        flags["limit"] = int(limit_match.group(1))

    # Apple Music specific flags
    # -codec flag: For Apple Music song codec selection (support both -codec and --codec-song)
    codec_match = re.search(r"(?:-codec|--codec-song)\s+([\w-]+)", query)
    if codec_match:
        flags["apple_codec_song"] = codec_match.group(1)

    # Short flags support
    cookies_match = re.search(r"-c\s+([\w./]+)", query)
    if cookies_match:
        flags["apple_cookies_path"] = cookies_match.group(1)

    language_match = re.search(r"-l\s+([a-z]{2}-[A-Z]{2})", query)
    if language_match:
        flags["apple_language"] = language_match.group(1)

    # Apple Music boolean flags (only real gamdl flags)
    if re.search(r"--disable-music-video-skip\b", query):
        flags["apple_disable_music_video_skip"] = True

    if re.search(r"--save-cover\b", query):
        flags["apple_save_cover"] = True

    if re.search(r"--overwrite\b", query):
        flags["apple_overwrite"] = True

    if re.search(r"--save-playlist\b", query):
        flags["apple_save_playlist"] = True

    if re.search(r"--synced-lyrics-only\b", query):
        flags["apple_synced_lyrics_only"] = True

    if re.search(r"--no-synced-lyrics\b", query):
        flags["apple_no_synced_lyrics"] = True

    if re.search(r"--no-exceptions\b", query):
        flags["apple_no_exceptions"] = True

    if re.search(r"--read-urls-as-txt\b", query):
        flags["apple_read_urls_as_txt"] = True

    if re.search(r"--no-config-file\b", query):
        flags["apple_no_config_file"] = True

    # Apple Music string flags
    language_long_match = re.search(r"--language\s+([a-z]{2}-[A-Z]{2})", query)
    if language_long_match:
        flags["apple_language"] = language_long_match.group(1)

    cover_size_match = re.search(r"--cover-size\s+(\d+)", query)
    if cover_size_match:
        flags["apple_cover_size"] = int(cover_size_match.group(1))

    truncate_match = re.search(r"--truncate\s+(\d+)", query)
    if truncate_match:
        flags["apple_truncate"] = int(truncate_match.group(1))

    # Apple Music format flags
    cover_format_match = re.search(r"--cover-format\s+(\w+)", query)
    if cover_format_match:
        flags["apple_cover_format"] = cover_format_match.group(1)

    lyrics_format_match = re.search(r"--synced-lyrics-format\s+(\w+)", query)
    if lyrics_format_match:
        flags["apple_synced_lyrics_format"] = lyrics_format_match.group(1)

    video_codec_match = re.search(r"--codec-music-video\s+([\w-]+)", query)
    if video_codec_match:
        flags["apple_codec_music_video"] = video_codec_match.group(1)

    download_mode_match = re.search(r"--download-mode\s+(\w+)", query)
    if download_mode_match:
        flags["apple_download_mode"] = download_mode_match.group(1)

    remux_mode_match = re.search(r"--remux-mode\s+(\w+)", query)
    if remux_mode_match:
        flags["apple_remux_mode"] = remux_mode_match.group(1)

    # Additional Apple Music flags
    quality_post_match = re.search(r"--quality-post\s+(\w+)", query)
    if quality_post_match:
        flags["apple_quality_post"] = quality_post_match.group(1)

    remux_format_match = re.search(r"--remux-format-music-video\s+(\w+)", query)
    if remux_format_match:
        flags["apple_remux_format_music_video"] = remux_format_match.group(1)

    exclude_tags_match = re.search(r"--exclude-tags\s+([\w,]+)", query)
    if exclude_tags_match:
        flags["apple_exclude_tags"] = exclude_tags_match.group(1)

    wvd_path_match = re.search(r"--wvd-path\s+([\w./]+)", query)
    if wvd_path_match:
        flags["apple_wvd_path"] = wvd_path_match.group(1)

    # DeezSpot (Spotify & Deezer) specific flags
    # Deezer quality flag
    deezer_quality_match = re.search(
        r"--deezer-quality\s+(MP3_128|MP3_320|FLAC)", query
    )
    if deezer_quality_match:
        flags["deezer_quality"] = deezer_quality_match.group(1)

    # Spotify quality flag
    spotify_quality_match = re.search(
        r"--spotify-quality\s+(NORMAL|HIGH|VERY_HIGH)", query
    )
    if spotify_quality_match:
        flags["spotify_quality"] = spotify_quality_match.group(1)

    # Deezer ARL token flag
    deezer_arl_match = re.search(r"--deezer-arl\s+([a-zA-Z0-9]+)", query)
    if deezer_arl_match:
        flags["deezer_arl"] = deezer_arl_match.group(1)

    # Spotify credentials path flag
    spotify_creds_match = re.search(r"--spotify-credentials\s+([\w./]+)", query)
    if spotify_creds_match:
        flags["spotify_credentials_path"] = spotify_creds_match.group(1)

    # Boolean flags for DeezSpot
    if re.search(r"--spotify-make-zip\b", query):
        flags["spotify_make_zip"] = True

    if re.search(r"--no-recursive-quality\b", query):
        flags["deezer_recursive_quality"] = False
        flags["spotify_recursive_quality"] = False

    return flags


# Paginated help system
def get_musicdl_help_pages() -> list:
    """Get paginated help text for musicdl"""
    return [
        # Page 1: Overview & Quick Start
        (
            "🎵 <b>Music Download Help</b> (1/7)\n\n"
            "<b>Usage:</b> <code>/musicdl [URL] [options]</code>\n\n"
            "<b>🚀 Quick Start:</b>\n"
            "• Basic: <code>/musicdl [URL]</code>\n"
            "• With format: <code>/musicdl [URL] -fm mp3</code>\n"
            "• High quality: <code>/musicdl [URL] -q 27</code> (Qobuz)\n"
            "• Custom: <code>/musicdl [URL] --quality-audio LOSSLESS</code> (Tidal)\n\n"
            "<b>🎯 Supported Platforms:</b>\n"
            "• 🌊 <b>Tidal</b> - High-quality streaming (tidal-dl-ng)\n"
            "• 🎼 <b>Qobuz</b> - Hi-Res audio streaming (qobuz-dl)\n"
            "• 🍎 <b>Apple Music</b> - AAC/ALAC streaming (gamdl)\n"
            "• 🎵 <b>Spotify</b> - Popular streaming (deezspot)\n"
            "• 🎶 <b>Deezer</b> - FLAC/MP3 streaming (deezspot)\n\n"
            "<b>🎛️ Format Options (-fm):</b>\n"
            "• <code>flac</code> - FLAC (lossless, default)\n"
            "• <code>mp3</code> - MP3 320kbps\n"
            "• <code>m4a</code> - AAC format\n"
            "• <code>opus</code> - Opus format\n\n"
            "💡 <b>Tip:</b> All downloads are automatically uploaded to Telegram!"
        ),
        # Page 2: Tidal Configuration
        (
            "🌊 <b>TIDAL Configuration</b> (2/7)\n\n"
            "<b>📊 Quality & Performance:</b>\n"
            "• <code>--quality-audio QUALITY</code> - Audio quality\n"
            "  (LOW, HIGH, LOSSLESS, HI_RES_LOSSLESS)\n"
            "• <code>--downloads-concurrent-max N</code> - Max downloads (1-10)\n"
            "• <code>--download-delay</code> - Add delays (avoid rate limits)\n\n"
            "<b>🎵 Audio Processing:</b>\n"
            "• <code>--extract-flac</code> - Extract FLAC from MP4\n"
            "• <code>--lyrics-embed</code> - Embed lyrics in files\n"
            "• <code>--lyrics-file</code> - Save separate .lrc files\n"
            "• <code>--metadata-cover-embed</code> - Embed covers\n\n"
            "<b>📁 File Management:</b>\n"
            "• <code>--skip-existing</code> - Skip existing files\n"
            "• <code>--playlist-create</code> - Create .m3u8 files\n"
            "• <code>--cover-album-file</code> - Save cover.jpg\n\n"
            "<b>🎬 Video Options:</b>\n"
            "• <code>--video-download</code> - Enable video downloads\n"
            "• <code>--video-convert-mp4</code> - Convert TS→MP4"
        ),
        # Page 3: Qobuz Configuration
        (
            "🎼 <b>QOBUZ Configuration</b> (3/7)\n\n"
            "<b>📊 Quality Options:</b>\n"
            "• <code>-q 27</code> - Hi-Res (24-bit >96kHz)\n"
            "• <code>-q 7</code> - Hi-Res (24-bit ≤96kHz)\n"
            "• <code>-q 6</code> - LOSSLESS (16-bit/44.1kHz) [default]\n"
            "• <code>-q 5</code> - 320kbps MP3\n\n"
            "<b>🎵 Download Control:</b>\n"
            "• <code>--no-fallback</code> - Disable quality fallback\n"
            "• <code>--albums-only</code> - Albums only mode\n"
            "• <code>--smart-discography</code> - Filter spam releases\n"
            "• <code>--limit N</code> - Search results limit (default: 20)\n\n"
            "<b>🖼️ Cover Art Options:</b>\n"
            "• <code>--og-cover</code> - Original quality covers\n"
            "• <code>--embed-art</code> - Embed cover art\n"
            "• <code>--no-cover</code> - Disable cover download\n\n"
            "<b>📁 File Organization:</b>\n"
            '• <code>--folder-format "template"</code> - Custom folder naming\n'
            '• <code>--track-format "template"</code> - Custom track naming\n'
            "• <code>--no-m3u</code> - Disable M3U playlist creation"
        ),
        # Page 4: Apple Music Configuration
        (
            "🍎 <b>APPLE MUSIC Configuration</b> (4/7)\n\n"
            "<b>🔑 Authentication:</b>\n"
            "• Requires Apple Music cookies file (Netscape format)\n"
            "• <b>Method 1:</b> Upload via Bot Settings > Private Files > cookies.txt\n"
            "• <b>Method 2:</b> Export from browser and place as <code>cookies.txt</code>\n"
            "• Firefox: Use 'Export Cookies' extension\n"
            "• Chrome/Edge: Use 'Get cookies.txt LOCALLY' extension\n\n"
            "<b>🎵 Codec Options:</b>\n"
            "• <code>-codec aac-legacy</code> - AAC 256kbps 44.1kHz (default)\n"
            "• <code>-codec aac-he-legacy</code> - AAC-HE 64kbps 44.1kHz\n"
            "• <code>-codec alac</code> - ALAC up to 24-bit/192kHz (experimental)\n"
            "• <code>-codec atmos</code> - Dolby Atmos 768kbps (experimental)\n\n"
            "<b>📁 Download Options:</b>\n"
            "• <code>--save-cover</code> - Save cover as separate file\n"
            "• <code>--overwrite</code> - Overwrite existing files\n"
            "• <code>--save-playlist</code> - Save M3U8 playlist files\n"
            "• <code>--disable-music-video-skip</code> - Include music videos\n"
            "• <code>--read-urls-as-txt</code> - Read URLs from text file\n"
            "• <code>--no-config-file</code> - Don't use gamdl config file\n"
            "• <code>--no-exceptions</code> - Don't print exceptions\n\n"
            "<b>🎤 Lyrics Options:</b>\n"
            "• <code>--synced-lyrics-format lrc</code> - LRC format (default)\n"
            "• <code>--synced-lyrics-format srt</code> - SubRip format\n"
            "• <code>--synced-lyrics-format ttml</code> - Native Apple format\n"
            "• <code>--synced-lyrics-only</code> - Download only synced lyrics\n"
            "• <code>--no-synced-lyrics</code> - Disable lyrics download\n\n"
            "<b>🖼️ Cover Art Options:</b>\n"
            "• <code>--cover-format jpg</code> - JPEG format (default)\n"
            "• <code>--cover-format png</code> - PNG format (lossless)\n"
            "• <code>--cover-format raw</code> - Raw format (requires --save-cover)\n"
            "• <code>--cover-size 1200</code> - Cover size in pixels\n\n"
            "<b>🔧 Advanced Options:</b>\n"
            "• <code>--download-mode ytdlp</code> - Download mode (ytdlp, nm3u8dlre)\n"
            "• <code>--remux-mode ffmpeg</code> - Remux mode (ffmpeg, mp4box)\n"
            "• <code>--quality-post best</code> - Post video quality (best, ask)\n"
            "• <code>--exclude-tags tag1,tag2</code> - Exclude metadata tags\n"
            "• <code>--truncate 100</code> - Max filename length\n"
            "• <code>--wvd-path /path/to/file.wvd</code> - Widevine key file\n\n"
            "<b>📱 Short Flags:</b>\n"
            "• <code>-c /path/to/cookies.txt</code> - Cookies file path\n"
            "• <code>-l en-US</code> - Language code\n"
            "• <code>-codec alac</code> - Song codec (same as --codec-song)\n\n"
            "<b>⚠️ Experimental Codecs:</b>\n"
            "• aac, aac-he, aac-binaural, atmos, ac3, alac\n"
            "• Not guaranteed to work due to API limitations"
        ),
        # Page 5: Examples
        (
            "📚 <b>Usage Examples</b> (5/7)\n\n"
            "<b>🌊 Tidal Examples:</b>\n"
            "• <code>/musicdl https://tidal.com/browse/album/123456</code>\n"
            "• <code>/musicdl https://tidal.com/browse/track/789012 -fm mp3</code>\n"
            "• <code>/musicdl [URL] --quality-audio LOSSLESS</code>\n"
            "• <code>/musicdl [URL] --no-lyrics-embed --downloads-concurrent-max 3</code>\n\n"
            "<b>🎼 Qobuz Examples:</b>\n"
            "• <code>/musicdl https://play.qobuz.com/album/abc123</code>\n"
            "• <code>/musicdl https://play.qobuz.com/track/def456 -q 27 -fm flac</code>\n"
            "• <code>/musicdl [URL] --albums-only --smart-discography</code>\n"
            "• <code>/musicdl [URL] --embed-art --limit 50</code>\n\n"
            "<b>🍎 Apple Music Examples:</b>\n"
            "• <code>/musicdl https://music.apple.com/us/album/album-name/123456</code>\n"
            "• <code>/musicdl https://music.apple.com/us/song/song-name/789012 -codec alac</code>\n"
            "• <code>/musicdl [URL] --save-cover --synced-lyrics-format srt</code>\n"
            "• <code>/musicdl [URL] --disable-music-video-skip --cover-size 1400</code>\n"
            "• <code>/musicdl [URL] -c /path/cookies.txt -l en-US --cover-format png</code>\n"
            "• <code>/musicdl [URL] --codec-music-video h265 --quality-post best</code>\n\n"
            "<b>🔧 Advanced Examples:</b>\n"
            "• Custom album format:\n"
            '  <code>/musicdl [URL] --format-album "Music/{artist} - {album} ({year})"</code>\n'
            "• Custom folder format:\n"
            '  <code>/musicdl [URL] --folder-format "{artist} - {album} [{bit_depth}B-{sampling_rate}kHz]"</code>'
        ),
        # Page 5: Template Variables
        (
            "🔧 <b>Template Variables</b> (6/7)\n\n"
            "<b>🌊 Tidal Template Variables:</b>\n"
            "• <code>{album_artist}</code> - Album artist name\n"
            "• <code>{album_title}</code> - Album title\n"
            "• <code>{track_num}</code> - Track number\n"
            "• <code>{artist_name}</code> - Track artist name\n"
            "• <code>{track_title}</code> - Track title\n"
            "• <code>{track_explicit}</code> - Explicit flag\n"
            "• <code>{playlist_name}</code> - Playlist name\n"
            "• <code>{list_pos}</code> - Position in list\n"
            "• <code>{mix_name}</code> - Mix name\n\n"
            "<b>🎼 Qobuz Template Variables:</b>\n"
            "• <code>{artist}</code> - Artist name\n"
            "• <code>{album}</code> - Album title\n"
            "• <code>{year}</code> - Release year\n"
            "• <code>{bit_depth}</code> - Bit depth (16, 24)\n"
            "• <code>{sampling_rate}</code> - Sample rate (44.1, 96, 192)\n"
            "• <code>{tracknumber}</code> - Track number\n"
            "• <code>{tracktitle}</code> - Track title\n\n"
            "<b>💡 Template Tips:</b>\n"
            "• Use quotes for templates with spaces\n"
            "• Variables are case-sensitive\n"
            "• Invalid variables are ignored"
        ),
        # Page 6: Important Notes
        (
            "⚠️ <b>Important Notes & Tips</b> (7/7)\n\n"
            "<b>🔑 Authentication:</b>\n"
            "• <b>Tidal:</b> Requires valid subscription and login\n"
            "• <b>Qobuz:</b> Configured via bot settings\n"
            "  (QOBUZ_EMAIL, QOBUZ_PASSWORD)\n"
            "• <b>Apple Music:</b> Requires cookies.txt file\n"
            "  Upload via Bot Settings > Private Files or export from browser\n\n"
            "<b>⚡ Performance Tips:</b>\n"
            "• Use <code>--downloads-concurrent-max 1-3</code> to avoid rate limiting\n"
            "• Enable <code>--download-delay</code> for large downloads\n"
            "• Use <code>--skip-existing</code> to resume interrupted downloads\n\n"
            "<b>🎵 Quality Notes:</b>\n"
            "• Tidal MAX requires HI_RES_LOSSLESS subscription\n"
            "• Qobuz Hi-Res requires Studio subscription\n"
            "• Format conversion preserves maximum quality\n\n"
            "<b>🔧 Configuration Priority:</b>\n"
            "• 1st: Command flags (highest priority)\n"
            "• 2nd: Bot configuration settings\n"
            "• 3rd: Library defaults\n\n"
            "<b>� Navigation:</b>\n"
            "Use the buttons below to navigate between help pages!"
        ),
    ]


def get_musicdl_help_text(page: int = 0) -> str:
    """Get specific page of help text"""
    pages = get_musicdl_help_pages()
    if 0 <= page < len(pages):
        return pages[page]
    return pages[0]  # Default to first page


async def show_musicdl_help(message, page: int = 0):
    """Show paginated help with navigation buttons"""
    from bot.helper.telegram_helper.button_build import ButtonMaker

    pages = get_musicdl_help_pages()
    total_pages = len(pages)

    # Ensure page is within bounds
    page = max(0, min(page, total_pages - 1))

    # Get help text for current page
    help_text = pages[page]

    # Create navigation buttons
    buttons = ButtonMaker()

    # Navigation row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(("◀️ Previous", f"musicdl_help:{page - 1}"))

    nav_buttons.append((f"{page + 1}/{total_pages}", "musicdl_help:current"))

    if page < total_pages - 1:
        nav_buttons.append(("Next ▶️", f"musicdl_help:{page + 1}"))

    # Add navigation buttons
    for text, data in nav_buttons:
        buttons.data_button(text, data)

    # Quick jump buttons (show 3 pages at a time)
    start_page = max(0, page - 1)
    end_page = min(total_pages, start_page + 3)

    jump_buttons = []
    for p in range(start_page, end_page):
        if p != page:  # Don't show current page
            jump_buttons.append((f"{p + 1}", f"musicdl_help:{p}"))

    # Add jump buttons
    for text, data in jump_buttons:
        buttons.data_button(text, data)

    # Close button
    buttons.data_button("❌ Close", "musicdl_help:close")

    await send_message(message, help_text, buttons.build_menu(1))


async def musicdl_help_callback(client, callback_query):
    """Handle help pagination callbacks"""
    data = callback_query.data.split(":")
    if len(data) != 2:
        return

    action = data[1]

    if action == "close":
        await callback_query.message.delete()
        return
    if action == "current":
        await callback_query.answer("You're viewing this page", show_alert=False)
        return

    try:
        page = int(action)
        pages = get_musicdl_help_pages()
        total_pages = len(pages)

        # Ensure page is within bounds
        page = max(0, min(page, total_pages - 1))

        # Get help text for new page
        help_text = pages[page]

        # Create navigation buttons
        from bot.helper.telegram_helper.button_build import ButtonMaker

        buttons = ButtonMaker()

        # Navigation row
        nav_buttons = []
        if page > 0:
            nav_buttons.append(("◀️ Previous", f"musicdl_help:{page - 1}"))

        nav_buttons.append((f"{page + 1}/{total_pages}", "musicdl_help:current"))

        if page < total_pages - 1:
            nav_buttons.append(("Next ▶️", f"musicdl_help:{page + 1}"))

        # Add navigation buttons
        for text, data in nav_buttons:
            buttons.data_button(text, data)

        # Quick jump buttons
        start_page = max(0, page - 1)
        end_page = min(total_pages, start_page + 3)

        jump_buttons = []
        for p in range(start_page, end_page):
            if p != page:
                jump_buttons.append((f"{p + 1}", f"musicdl_help:{p}"))

        # Add jump buttons
        for text, data in jump_buttons:
            buttons.data_button(text, data)

        # Close button
        buttons.data_button("❌ Close", "musicdl_help:close")

        await callback_query.message.edit_text(
            help_text, reply_markup=buttons.build_menu(1)
        )
        await callback_query.answer()

    except (ValueError, IndexError):
        await callback_query.answer("Invalid page", show_alert=True)


# Authentication functions
async def setup_tidal_auth():
    """Setup Tidal authentication using config values"""
    try:
        import json
        from pathlib import Path

        # Get config values
        access_token = Config.TIDAL_ACCESS_TOKEN
        refresh_token = Config.TIDAL_REFRESH_TOKEN
        expiry_time = Config.TIDAL_EXPIRY_TIME

        if not access_token or not refresh_token:
            LOGGER.warning("Tidal authentication not configured in config")
            return False

        # Setup tidal-dl-ng config directory
        config_dir = Path.home() / ".config" / "tidal_dl_ng"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create token.json
        token_data = {
            "token_type": "Bearer",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expiry_time": expiry_time,
        }

        token_file = config_dir / "token.json"
        with open(token_file, "w") as f:
            json.dump(token_data, f, indent=4)

        LOGGER.info("Tidal authentication configured successfully")
        return True

    except Exception as e:
        LOGGER.error(f"Failed to setup Tidal authentication: {e}")
        return False


async def setup_qobuz_module_auth():
    """Setup Qobuz authentication for module usage (no config file needed)"""
    try:
        # Check if qobuz-dl module is available
        if not QOBUZ_MODULE_AVAILABLE:
            LOGGER.error("qobuz-dl module not available")
            return None, None

        # Get config values
        email = Config.QOBUZ_EMAIL
        password = Config.QOBUZ_PASSWORD

        if not email or not password:
            LOGGER.warning("Qobuz authentication not configured in config")
            return None, None

        LOGGER.info("Qobuz module authentication configured successfully")
        return email, password

    except Exception as e:
        LOGGER.error(f"Failed to setup Qobuz module authentication: {e}")
        return None, None


async def verify_authentication(platform: str) -> bool:
    """Verify authentication for a platform"""
    try:
        if platform == "tidal":
            # Quick check for Tidal credentials without subprocess call
            access_token = Config.TIDAL_ACCESS_TOKEN
            refresh_token = Config.TIDAL_REFRESH_TOKEN
            return bool(access_token and refresh_token)

        if platform == "qobuz":
            # Quick check for Qobuz credentials without full setup
            email = Config.QOBUZ_EMAIL
            password = Config.QOBUZ_PASSWORD
            return bool(email and password)

        if platform == "apple":
            # Check if cookies file exists (prioritize uploaded private file)
            cookies_found = await _check_apple_cookies_availability()
            if not cookies_found:
                LOGGER.error("Apple Music cookies file not found")
                return False

            # Check if gamdl is available
            result = await asyncio.create_subprocess_exec(
                "gamdl",
                "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
            return result.returncode == 0

        if platform == "spotify":
            # Check if Zotify credentials are available
            username = getattr(Config, 'ZOTIFY_USERNAME', None)
            password = getattr(Config, 'ZOTIFY_PASSWORD', None)
            if username and password:
                LOGGER.info(f"✅ [SPOTIFY] Zotify credentials available")
                return True

            # Fallback: Check if deezspot is available for Spotify search
            try:
                import sys
                import os
                deezspot_path = os.path.join(os.getcwd(), 'deezspot')
                if deezspot_path not in sys.path:
                    sys.path.append(deezspot_path)
                from deezspot.easy_spoty import Spo
                LOGGER.info("✅ [SPOTIFY] Deezspot library available for search")
                return True
            except (ImportError, ModuleNotFoundError) as e:
                LOGGER.warning(f"❌ [SPOTIFY] Neither Zotify credentials nor deezspot available: {e}")
                return False

        if platform == "deezer":
            # Check if Deezer credentials are available
            arl = getattr(Config, 'DEEZER_ARL', None)
            if arl:
                LOGGER.info(f"✅ [DEEZER] ARL credentials available")
                return True

            # Fallback: Check if deezspot is available for Deezer search
            try:
                import sys
                import os
                deezspot_path = os.path.join(os.getcwd(), 'deezspot')
                if deezspot_path not in sys.path:
                    sys.path.append(deezspot_path)
                from deezspot.deezloader.dee_api import API
                LOGGER.info("✅ [DEEZER] Deezspot library available for search")
                return True
            except (ImportError, ModuleNotFoundError) as e:
                LOGGER.warning(f"❌ [DEEZER] Neither ARL credentials nor deezspot available: {e}")
                return False

        return False

    except Exception as e:
        LOGGER.error(f"Authentication verification failed for {platform}: {e}")
        return False


async def show_quality_format_menu(message, url: str, query: str = "", is_leech: bool = True) -> bool:
    """Show quality and format selection menu for MusicDL"""
    try:
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from pyrogram.enums import ParseMode

        # Detect platform
        platform = detect_platform(url)
        if not platform:
            await send_message(message, "❌ Unsupported URL. Please provide a valid music platform URL.")
            return False

        # Get platform-specific quality and format options
        quality_options, format_options = _get_platform_quality_format_options(platform)

        # Create menu text
        menu_text = f"🎵 <b>Quality & Format Selection</b>\n\n"
        menu_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
        menu_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
        menu_text += f"📊 <b>Available Qualities:</b> {len(quality_options)}\n"
        menu_text += f"📁 <b>Available Formats:</b> {len(format_options)}\n\n"
        menu_text += "⏱️ <b>Timeout:</b> 5 minutes\n\n"
        menu_text += "Please select your preferred quality and format:"

        # Create keyboard with quality options
        keyboard_rows = []

        # Add quality selection header
        keyboard_rows.append([InlineKeyboardButton("🔊 Quality Selection", callback_data="musicdl_header_quality")])

        # Add quality options (2 per row)
        quality_row = []
        for i, (quality_id, quality_info) in enumerate(quality_options.items()):
            quality_row.append(InlineKeyboardButton(
                f"{quality_info['emoji']} {quality_info['name']}",
                callback_data=f"musicdl_quality_{platform}_{quality_id}_{hash(url)}"
            ))
            if len(quality_row) == 2 or i == len(quality_options) - 1:
                keyboard_rows.append(quality_row)
                quality_row = []

        # Add format selection header
        keyboard_rows.append([InlineKeyboardButton("📁 Format Selection", callback_data="musicdl_header_format")])

        # Add format options (3 per row)
        format_row = []
        for i, (format_id, format_info) in enumerate(format_options.items()):
            format_row.append(InlineKeyboardButton(
                f"{format_info['emoji']} {format_info['name']}",
                callback_data=f"musicdl_format_{platform}_{format_id}_{hash(url)}"
            ))
            if len(format_row) == 3 or i == len(format_options) - 1:
                keyboard_rows.append(format_row)
                format_row = []

        # Add quick download options
        keyboard_rows.append([InlineKeyboardButton("⚡ Quick Download", callback_data="musicdl_header_quick")])
        keyboard_rows.append([
            InlineKeyboardButton(
                "🎵 Best FLAC",
                callback_data=f"musicdl_quick_{platform}_best_flac_{hash(url)}"
            ),
            InlineKeyboardButton(
                "🎶 Best MP3",
                callback_data=f"musicdl_quick_{platform}_best_mp3_{hash(url)}"
            )
        ])

        # Add cancel button
        keyboard_rows.append([InlineKeyboardButton("❌ Cancel", callback_data="musicdl_cancel")])

        keyboard = InlineKeyboardMarkup(keyboard_rows)

        # Store the URL and query for later use
        user_id = message.from_user.id
        await _store_musicdl_session_data(user_id, {
            "url": url,
            "query": query,
            "is_leech": is_leech,
            "platform": platform,
            "selected_quality": None,
            "selected_format": None,
            "timestamp": time.time()
        })

        # Send menu
        await send_message(message, menu_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return True

    except Exception as e:
        LOGGER.error(f"Failed to show quality/format menu: {e}")
        await send_message(message, f"❌ Failed to show selection menu: {e}")
        return False


def _get_platform_quality_format_options(platform: str) -> tuple[dict, dict]:
    """Get platform-specific quality and format options based on library capabilities"""

    if platform == "qobuz":
        # Qobuz-dl quality levels: 5=MP3_320, 6=FLAC_CD, 7=FLAC_24B96, 27=FLAC_24B192
        quality_options = {
            "5": {"name": "MP3 320kbps", "emoji": "🎶", "description": "High quality MP3"},
            "6": {"name": "FLAC CD", "emoji": "💿", "description": "16-bit/44.1kHz FLAC"},
            "7": {"name": "Hi-Res 96kHz", "emoji": "🎵", "description": "24-bit/96kHz FLAC"},
            "27": {"name": "Hi-Res 192kHz", "emoji": "💎", "description": "24-bit/192kHz FLAC (Best)"}
        }
        format_options = {
            "flac": {"name": "FLAC", "emoji": "🎵", "description": "Lossless audio"},
            "mp3": {"name": "MP3", "emoji": "🎶", "description": "Compressed audio"},
            "alac": {"name": "ALAC", "emoji": "🍎", "description": "Apple Lossless"}
        }

    elif platform == "tidal":
        # Tidal-dl-ng quality levels: LOW, HIGH, LOSSLESS, HI_RES
        quality_options = {
            "LOW": {"name": "96kbps AAC", "emoji": "🎶", "description": "Basic quality"},
            "HIGH": {"name": "320kbps AAC", "emoji": "🎵", "description": "High quality"},
            "LOSSLESS": {"name": "FLAC CD", "emoji": "💿", "description": "16-bit/44.1kHz FLAC"},
            "HI_RES": {"name": "Hi-Res MQA", "emoji": "💎", "description": "24-bit/192kHz FLAC (Best)"}
        }
        format_options = {
            "flac": {"name": "FLAC", "emoji": "🎵", "description": "Lossless audio"},
            "m4a": {"name": "M4A", "emoji": "📱", "description": "AAC in M4A container"},
            "mp3": {"name": "MP3", "emoji": "🎶", "description": "Converted from FLAC"}
        }

    elif platform == "apple":
        # GAMDL codec options: aac-legacy, aac-he, aac-he-v2, alac
        quality_options = {
            "aac-legacy": {"name": "AAC 256kbps", "emoji": "🎶", "description": "Standard AAC"},
            "aac-he": {"name": "AAC HE", "emoji": "🎵", "description": "High Efficiency AAC"},
            "aac-he-v2": {"name": "AAC HE v2", "emoji": "💿", "description": "Advanced HE AAC"},
            "alac": {"name": "Apple Lossless", "emoji": "💎", "description": "ALAC (Best)"}
        }
        format_options = {
            "m4a": {"name": "M4A", "emoji": "🍎", "description": "Native Apple format"},
            "mp3": {"name": "MP3", "emoji": "🎶", "description": "Converted from M4A"},
            "flac": {"name": "FLAC", "emoji": "🎵", "description": "Converted from ALAC"}
        }

    elif platform == "spotify":
        # Zotify/Deezspot quality options: NORMAL, HIGH, VERY_HIGH
        quality_options = {
            "NORMAL": {"name": "96kbps OGG", "emoji": "🎶", "description": "Basic quality"},
            "HIGH": {"name": "160kbps OGG", "emoji": "🎵", "description": "High quality (Free)"},
            "VERY_HIGH": {"name": "320kbps OGG", "emoji": "💎", "description": "Premium quality (Best)"}
        }
        format_options = {
            "ogg": {"name": "OGG Vorbis", "emoji": "🎵", "description": "Native Spotify format"},
            "mp3": {"name": "MP3", "emoji": "🎶", "description": "Converted from OGG"},
            "flac": {"name": "FLAC", "emoji": "💿", "description": "Converted from OGG"}
        }

    elif platform == "deezer":
        # Deezspot quality options: MP3_128, MP3_320, FLAC
        quality_options = {
            "MP3_128": {"name": "MP3 128kbps", "emoji": "🎶", "description": "Basic quality"},
            "MP3_320": {"name": "MP3 320kbps", "emoji": "🎵", "description": "High quality"},
            "FLAC": {"name": "FLAC", "emoji": "💎", "description": "Lossless (Premium only)"}
        }
        format_options = {
            "flac": {"name": "FLAC", "emoji": "🎵", "description": "Lossless audio"},
            "mp3": {"name": "MP3", "emoji": "🎶", "description": "Compressed audio"},
            "m4a": {"name": "M4A", "emoji": "📱", "description": "AAC in M4A container"}
        }

    else:
        # Default/fallback options
        quality_options = {
            "high": {"name": "High Quality", "emoji": "🎵", "description": "Best available"},
            "medium": {"name": "Medium Quality", "emoji": "🎶", "description": "Balanced"},
            "low": {"name": "Low Quality", "emoji": "📻", "description": "Basic"}
        }
        format_options = {
            "flac": {"name": "FLAC", "emoji": "🎵", "description": "Lossless audio"},
            "mp3": {"name": "MP3", "emoji": "🎶", "description": "Compressed audio"}
        }

    return quality_options, format_options


async def _store_musicdl_session_data(user_id: int, data: dict) -> None:
    """Store session data for quality/format selection"""
    try:
        # Use a simple in-memory cache for now
        if not hasattr(_store_musicdl_session_data, 'cache'):
            _store_musicdl_session_data.cache = {}

        _store_musicdl_session_data.cache[user_id] = data

        # Clean up old sessions (older than 10 minutes)
        current_time = time.time()
        expired_users = [
            uid for uid, session_data in _store_musicdl_session_data.cache.items()
            if current_time - session_data.get('timestamp', 0) > 600
        ]
        for uid in expired_users:
            del _store_musicdl_session_data.cache[uid]

    except Exception as e:
        LOGGER.error(f"Failed to store session data: {e}")


async def _handle_quality_selection(callback_query, data: str) -> None:
    """Handle quality selection from menu"""
    try:
        from pyrogram.enums import ParseMode

        # Parse callback data: musicdl_quality_{platform}_{quality_id}_{url_hash}
        parts = data.split("_", 4)
        if len(parts) < 4:
            await callback_query.answer("❌ Invalid selection", show_alert=True)
            return

        platform = parts[2]
        quality_id = parts[3]

        # Get session data
        user_id = callback_query.from_user.id
        session_data = await _get_musicdl_session_data(user_id)
        if not session_data:
            await callback_query.answer("❌ Session expired. Please start again.", show_alert=True)
            return

        # Update session with selected quality
        session_data['selected_quality'] = quality_id
        await _store_musicdl_session_data(user_id, session_data)

        # Get quality info
        quality_options, _ = _get_platform_quality_format_options(platform)
        quality_info = quality_options.get(quality_id, {"name": quality_id, "description": ""})

        # Update message to show selection
        await callback_query.answer(f"✅ Quality selected: {quality_info['name']}", show_alert=False)

        # Check if both quality and format are selected
        if session_data.get('selected_format'):
            await _finalize_download_selection(callback_query, session_data)
        else:
            # Update message to highlight selection
            await _update_selection_message(callback_query, session_data, f"Quality: {quality_info['name']}")

    except Exception as e:
        LOGGER.error(f"Error handling quality selection: {e}")
        await callback_query.answer("❌ Error processing selection", show_alert=True)


async def _handle_format_selection(callback_query, data: str) -> None:
    """Handle format selection from menu"""
    try:
        from pyrogram.enums import ParseMode

        # Parse callback data: musicdl_format_{platform}_{format_id}_{url_hash}
        parts = data.split("_", 4)
        if len(parts) < 4:
            await callback_query.answer("❌ Invalid selection", show_alert=True)
            return

        platform = parts[2]
        format_id = parts[3]

        # Get session data
        user_id = callback_query.from_user.id
        session_data = await _get_musicdl_session_data(user_id)
        if not session_data:
            await callback_query.answer("❌ Session expired. Please start again.", show_alert=True)
            return

        # Update session with selected format
        session_data['selected_format'] = format_id
        await _store_musicdl_session_data(user_id, session_data)

        # Get format info
        _, format_options = _get_platform_quality_format_options(platform)
        format_info = format_options.get(format_id, {"name": format_id, "description": ""})

        # Update message to show selection
        await callback_query.answer(f"✅ Format selected: {format_info['name']}", show_alert=False)

        # Check if both quality and format are selected
        if session_data.get('selected_quality'):
            await _finalize_download_selection(callback_query, session_data)
        else:
            # Update message to highlight selection
            await _update_selection_message(callback_query, session_data, f"Format: {format_info['name']}")

    except Exception as e:
        LOGGER.error(f"Error handling format selection: {e}")
        await callback_query.answer("❌ Error processing selection", show_alert=True)


async def _handle_quick_download(callback_query, data: str) -> None:
    """Handle quick download selection"""
    try:
        # Parse callback data: musicdl_quick_{platform}_{quality}_{format}_{url_hash}
        parts = data.split("_", 5)
        if len(parts) < 5:
            await callback_query.answer("❌ Invalid selection", show_alert=True)
            return

        platform = parts[2]
        quality_type = parts[3]  # "best"
        format_type = parts[4]   # "flac" or "mp3"

        # Get session data
        user_id = callback_query.from_user.id
        session_data = await _get_musicdl_session_data(user_id)
        if not session_data:
            await callback_query.answer("❌ Session expired. Please start again.", show_alert=True)
            return

        # Set best quality for platform
        quality_options, _ = _get_platform_quality_format_options(platform)
        best_quality = list(quality_options.keys())[-1]  # Last option is usually best

        # Update session with selections
        session_data['selected_quality'] = best_quality
        session_data['selected_format'] = format_type
        await _store_musicdl_session_data(user_id, session_data)

        await callback_query.answer(f"✅ Quick download: Best {format_type.upper()}", show_alert=False)
        await _finalize_download_selection(callback_query, session_data)

    except Exception as e:
        LOGGER.error(f"Error handling quick download: {e}")
        await callback_query.answer("❌ Error processing selection", show_alert=True)


async def _finalize_download_selection(callback_query, session_data: dict) -> None:
    """Finalize download with selected quality and format"""
    try:
        from pyrogram.enums import ParseMode

        url = session_data['url']
        query = session_data['query']
        is_leech = session_data['is_leech']
        platform = session_data['platform']
        quality = session_data['selected_quality']
        format_type = session_data['selected_format']

        # Create query with selected options
        final_query = f"{query} -q {quality} -fm {format_type}"

        # Update message to show download starting
        download_text = f"🎵 <b>Download Starting...</b>\n\n"
        download_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
        download_text += f"🔊 <b>Quality:</b> {quality}\n"
        download_text += f"📁 <b>Format:</b> {format_type.upper()}\n"
        download_text += f"📤 <b>Mode:</b> {'Leech to Telegram' if is_leech else 'Mirror to Cloud'}\n\n"
        download_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
        download_text += "⏳ <b>Status:</b> Initializing download..."

        await callback_query.edit_message_text(
            download_text,
            parse_mode=ParseMode.HTML
        )

        # Start the actual download
        listener = await start_music_download(
            callback_query.message, url, final_query, is_leech=is_leech
        )

        if listener:
            # Update with success message
            success_text = f"✅ <b>Download Started Successfully</b>\n\n"
            success_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
            success_text += f"🔊 <b>Quality:</b> {quality}\n"
            success_text += f"📁 <b>Format:</b> {format_type.upper()}\n"
            success_text += f"📤 <b>Mode:</b> {'Leech to Telegram' if is_leech else 'Mirror to Cloud'}\n\n"
            success_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
            success_text += f"⏳ <b>Status:</b> {listener.status}\n"
            success_text += "💡 <b>Note:</b> Download progress will be shown in real-time."

            await callback_query.edit_message_text(
                success_text,
                parse_mode=ParseMode.HTML
            )
        else:
            # Download failed
            error_text = f"❌ <b>Download Failed</b>\n\n"
            error_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
            error_text += f"🔊 <b>Quality:</b> {quality}\n"
            error_text += f"📁 <b>Format:</b> {format_type.upper()}\n\n"
            error_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
            error_text += "💡 Please try again or check if the URL is valid."

            await callback_query.edit_message_text(
                error_text,
                parse_mode=ParseMode.HTML
            )

        # Clean up session data
        user_id = callback_query.from_user.id
        if hasattr(_store_musicdl_session_data, 'cache') and user_id in _store_musicdl_session_data.cache:
            del _store_musicdl_session_data.cache[user_id]

    except Exception as e:
        LOGGER.error(f"Error finalizing download: {e}")
        await callback_query.edit_message_text(
            f"❌ <b>Download Error</b>\n\n{str(e)}",
            parse_mode=ParseMode.HTML
        )


async def _update_selection_message(callback_query, session_data: dict, selection_info: str) -> None:
    """Update selection message with current selections"""
    try:
        from pyrogram.enums import ParseMode

        platform = session_data['platform']
        url = session_data['url']

        # Create updated message
        menu_text = f"🎵 <b>Quality & Format Selection</b>\n\n"
        menu_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
        menu_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
        menu_text += f"✅ <b>Selected:</b> {selection_info}\n\n"

        if session_data.get('selected_quality') and session_data.get('selected_format'):
            menu_text += "🎯 <b>Ready to download!</b> Processing..."
        else:
            menu_text += "Please select both quality and format to continue."

        await callback_query.edit_message_text(
            menu_text,
            parse_mode=ParseMode.HTML,
            reply_markup=callback_query.message.reply_markup
        )

    except Exception as e:
        LOGGER.error(f"Error updating selection message: {e}")


async def _handle_quality_selection(callback_query, data: str) -> None:
    """Handle quality selection from menu"""
    try:
        # Parse callback data: musicdl_quality_{platform}_{quality_id}_{url_hash}
        parts = data.split("_", 4)
        if len(parts) < 4:
            await callback_query.answer("❌ Invalid selection", show_alert=True)
            return

        platform = parts[2]
        quality_id = parts[3]

        # Get session data
        user_id = callback_query.from_user.id
        session_data = await _get_musicdl_session_data(user_id)
        if not session_data:
            await callback_query.answer("❌ Session expired. Please start again.", show_alert=True)
            return

        # Update session with selected quality
        session_data['selected_quality'] = quality_id
        await _store_musicdl_session_data(user_id, session_data)

        # Get quality info
        quality_options, _ = _get_platform_quality_format_options(platform)
        quality_info = quality_options.get(quality_id, {"name": quality_id, "description": ""})

        # Update message to show selection
        await callback_query.answer(f"✅ Quality selected: {quality_info['name']}", show_alert=False)

        # Check if both quality and format are selected
        if session_data.get('selected_format'):
            await _finalize_download_selection(callback_query, session_data)
        else:
            # Update message to highlight selection
            await _update_selection_message(callback_query, session_data, f"Quality: {quality_info['name']}")

    except Exception as e:
        LOGGER.error(f"Error handling quality selection: {e}")
        await callback_query.answer("❌ Error processing selection", show_alert=True)


async def _handle_format_selection(callback_query, data: str) -> None:
    """Handle format selection from menu"""
    try:
        # Parse callback data: musicdl_format_{platform}_{format_id}_{url_hash}
        parts = data.split("_", 4)
        if len(parts) < 4:
            await callback_query.answer("❌ Invalid selection", show_alert=True)
            return

        platform = parts[2]
        format_id = parts[3]

        # Get session data
        user_id = callback_query.from_user.id
        session_data = await _get_musicdl_session_data(user_id)
        if not session_data:
            await callback_query.answer("❌ Session expired. Please start again.", show_alert=True)
            return

        # Update session with selected format
        session_data['selected_format'] = format_id
        await _store_musicdl_session_data(user_id, session_data)

        # Get format info
        _, format_options = _get_platform_quality_format_options(platform)
        format_info = format_options.get(format_id, {"name": format_id, "description": ""})

        # Update message to show selection
        await callback_query.answer(f"✅ Format selected: {format_info['name']}", show_alert=False)

        # Check if both quality and format are selected
        if session_data.get('selected_quality'):
            await _finalize_download_selection(callback_query, session_data)
        else:
            # Update message to highlight selection
            await _update_selection_message(callback_query, session_data, f"Format: {format_info['name']}")

    except Exception as e:
        LOGGER.error(f"Error handling format selection: {e}")
        await callback_query.answer("❌ Error processing selection", show_alert=True)


async def _handle_quick_download(callback_query, data: str) -> None:
    """Handle quick download selection"""
    try:
        # Parse callback data: musicdl_quick_{platform}_{quality}_{format}_{url_hash}
        parts = data.split("_", 5)
        if len(parts) < 5:
            await callback_query.answer("❌ Invalid selection", show_alert=True)
            return

        platform = parts[2]
        quality_type = parts[3]  # "best"
        format_type = parts[4]   # "flac" or "mp3"

        # Get session data
        user_id = callback_query.from_user.id
        session_data = await _get_musicdl_session_data(user_id)
        if not session_data:
            await callback_query.answer("❌ Session expired. Please start again.", show_alert=True)
            return

        # Set best quality for platform
        quality_options, _ = _get_platform_quality_format_options(platform)
        best_quality = list(quality_options.keys())[-1]  # Last option is usually best

        # Update session with selections
        session_data['selected_quality'] = best_quality
        session_data['selected_format'] = format_type
        await _store_musicdl_session_data(user_id, session_data)

        await callback_query.answer(f"✅ Quick download: Best {format_type.upper()}", show_alert=False)
        await _finalize_download_selection(callback_query, session_data)

    except Exception as e:
        LOGGER.error(f"Error handling quick download: {e}")
        await callback_query.answer("❌ Error processing selection", show_alert=True)


async def _finalize_download_selection(callback_query, session_data: dict) -> None:
    """Finalize download with selected quality and format"""
    try:
        url = session_data['url']
        query = session_data['query']
        is_leech = session_data['is_leech']
        platform = session_data['platform']
        quality = session_data['selected_quality']
        format_type = session_data['selected_format']

        # Create query with selected options (remove flags, use configs as fallback)
        final_query = f"-q {quality} -fm {format_type}"

        # Update message to show download starting
        download_text = f"🎵 <b>Download Starting...</b>\n\n"
        download_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
        download_text += f"🔊 <b>Quality:</b> {quality}\n"
        download_text += f"📁 <b>Format:</b> {format_type.upper()}\n"
        download_text += f"📤 <b>Mode:</b> {'Leech to Telegram' if is_leech else 'Mirror to Cloud'}\n\n"
        download_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
        download_text += "⏳ <b>Status:</b> Initializing download..."

        await callback_query.edit_message_text(
            download_text,
            parse_mode=ParseMode.HTML
        )

        # Start the actual download
        listener = await start_music_download(
            callback_query.message, url, final_query, is_leech=is_leech
        )

        if listener:
            # Update with success message
            success_text = f"✅ <b>Download Started Successfully</b>\n\n"
            success_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
            success_text += f"🔊 <b>Quality:</b> {quality}\n"
            success_text += f"📁 <b>Format:</b> {format_type.upper()}\n"
            success_text += f"📤 <b>Mode:</b> {'Leech to Telegram' if is_leech else 'Mirror to Cloud'}\n\n"
            success_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
            success_text += f"⏳ <b>Status:</b> {listener.status}\n"
            success_text += "💡 <b>Note:</b> Download progress will be shown in real-time."

            await callback_query.edit_message_text(
                success_text,
                parse_mode=ParseMode.HTML
            )
        else:
            # Download failed
            error_text = f"❌ <b>Download Failed</b>\n\n"
            error_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
            error_text += f"🔊 <b>Quality:</b> {quality}\n"
            error_text += f"📁 <b>Format:</b> {format_type.upper()}\n\n"
            error_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
            error_text += "💡 Please try again or check if the URL is valid."

            await callback_query.edit_message_text(
                error_text,
                parse_mode=ParseMode.HTML
            )

        # Clean up session data
        user_id = callback_query.from_user.id
        if hasattr(_store_musicdl_session_data, 'cache') and user_id in _store_musicdl_session_data.cache:
            del _store_musicdl_session_data.cache[user_id]

    except Exception as e:
        LOGGER.error(f"Error finalizing download: {e}")
        await callback_query.edit_message_text(
            f"❌ <b>Download Error</b>\n\n{str(e)}",
            parse_mode=ParseMode.HTML
        )


async def _update_selection_message(callback_query, session_data: dict, selection_info: str) -> None:
    """Update selection message with current selections"""
    try:
        from pyrogram.enums import ParseMode

        platform = session_data['platform']
        url = session_data['url']

        # Create updated message
        menu_text = f"🎵 <b>Quality & Format Selection</b>\n\n"
        menu_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
        menu_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
        menu_text += f"✅ <b>Selected:</b> {selection_info}\n\n"

        if session_data.get('selected_quality') and session_data.get('selected_format'):
            menu_text += "🎯 <b>Ready to download!</b> Processing..."
        else:
            menu_text += "Please select both quality and format to continue."

        await callback_query.edit_message_text(
            menu_text,
            parse_mode=ParseMode.HTML,
            reply_markup=callback_query.message.reply_markup
        )

    except Exception as e:
        LOGGER.error(f"Error updating selection message: {e}")


async def _get_musicdl_session_data(user_id: int) -> dict | None:
    """Get session data for quality/format selection"""
    try:
        if hasattr(_store_musicdl_session_data, 'cache'):
            session_data = _store_musicdl_session_data.cache.get(user_id)
            if session_data:
                # Check if session is still valid (5 minutes)
                if time.time() - session_data.get('timestamp', 0) < 300:
                    return session_data
                else:
                    # Session expired
                    del _store_musicdl_session_data.cache[user_id]
        return None
    except Exception as e:
        LOGGER.error(f"Failed to get session data: {e}")
        return None


async def start_music_download(
    message, url: str, query: str = "", is_leech: bool | None = None, inline_message=None
) -> MusicDownloadListener | None:
    """Start music download process with comprehensive logging

    Args:
        message: Telegram message object
        url: URL to download from
        query: Command query with flags
        is_leech: True for leech (Telegram), False for mirror (cloud), None for default behavior
    """
    LOGGER.info(f"Starting music download for message {message.id}")
    LOGGER.info(f"URL: {url}")
    LOGGER.info(f"Query: {query}")

    try:
        # Detect platform
        LOGGER.info("Detecting platform from URL...")
        platform = detect_platform(url)
        if not platform:
            LOGGER.error(f"Unsupported URL: {url}")
            await send_message(
                message,
                "❌ Unsupported URL. Please provide a Tidal, Qobuz, Apple Music, Spotify, or Deezer URL.",
            )
            return None

        LOGGER.info(f"Platform detected: {platform}")

        # Parse flags with priority over config
        LOGGER.info("Parsing command flags and options...")
        flags = parse_musicdl_flags(query)
        LOGGER.info(f"Parsed flags: {flags}")

        # Create config with flag overrides
        LOGGER.info("Creating download configuration with flag overrides...")
        config = DownloadConfig(flags)
        LOGGER.info(
            f"Configuration created: quality={config.quality}, format={config.format}"
        )
        LOGGER.info(
            f"Qobuz settings: no_fallback={config.qobuz_no_fallback}, albums_only={config.qobuz_albums_only}, smart_discography={config.qobuz_smart_discography}"
        )

        # Create download directory
        LOGGER.info("Creating download directory...")
        download_dir = tempfile.mkdtemp(prefix=f"{platform}_download_")
        LOGGER.info(f"Download directory created: {download_dir}")

        # Create listener
        LOGGER.info("Creating music download listener...")
        listener = MusicDownloadListener(
            message, config, platform, download_dir, is_leech, inline_message
        )
        LOGGER.info(f"Listener created with UID: {listener.uid}")
        LOGGER.info(
            f"Listener mode: {'Leech (Telegram)' if listener.is_leech else 'Mirror (Cloud)'}"
        )

        # Note: No status tracking needed for musicdl as requested
        LOGGER.info("Music download listener created (no status tracking)")

        # Start download
        LOGGER.info("Starting download task in background...")
        asyncio.create_task(_execute_download(listener, url))

        LOGGER.info("Music download started successfully")
        return listener

    except Exception as e:
        LOGGER.error(f"Failed to start music download: {e}", exc_info=True)
        await send_message(message, f"❌ Failed to start download: {e!s}")
        return None


async def _execute_download(listener: MusicDownloadListener, url: str):
    """Execute download in background with comprehensive logging"""
    LOGGER.info(f"Executing download for {listener.platform} - UID: {listener.uid}")
    LOGGER.info(f"Download URL: {url}")

    try:
        # Create downloader
        LOGGER.info(f"Initializing {listener.platform} downloader...")
        if listener.platform == "tidal":
            downloader = TidalDownloader(listener)
        elif listener.platform == "qobuz":
            downloader = QobuzDownloader(listener)
        elif listener.platform == "apple":
            downloader = AppleDownloader(listener)
        elif listener.platform == "spotify":
            downloader = SpotifyDownloader(listener)
        elif listener.platform == "deezer":
            downloader = DeezerDownloader(listener)
        else:
            raise ValueError(f"Unsupported platform: {listener.platform}")

        LOGGER.info(f"Downloader initialized successfully for {listener.platform}")

        # Download
        LOGGER.info("Starting download process...")
        success = await downloader.download(url)

        if success:
            LOGGER.info(f"Download completed successfully for UID: {listener.uid}")
            listener.is_completed = True

            # Debug logging for upload trigger
            LOGGER.info(f"Triggering upload for UID: {listener.uid}")
            LOGGER.info(
                f"Upload settings: is_leech={listener.is_leech}, dir={listener.dir}"
            )
            LOGGER.info(
                f"Download directory exists: {await aiopath.exists(listener.dir)}"
            )

            # Trigger upload process by calling on_download_complete
            await listener.on_download_complete()
        else:
            LOGGER.error(f"Download failed for UID: {listener.uid}")
            listener.is_failed = True

    except Exception as e:
        LOGGER.error(
            f"Download execution error for UID {listener.uid}: {e}", exc_info=True
        )
        listener.is_failed = True

    finally:
        LOGGER.info(f"Download execution completed for UID: {listener.uid}")
        # Clean up task from task_dict
        await listener._cleanup_task_dict()


# Platform-specific search functions
async def search_qobuz_content(query: str, content_types: list[str] = None, limit: int = 10) -> list[dict]:
    """Search Qobuz for tracks, albums, playlists with persistent session caching"""
    try:
        global _qobuz_dl_session_cache, _session_cache_status

        if not content_types:
            content_types = ["track", "album", "playlist"]

        # Check if we have a valid cached session (persistent, no timeout)
        if (_qobuz_dl_session_cache is not None and
            _session_cache_status['qobuz_dl'] and
            hasattr(_qobuz_dl_session_cache, 'client') and
            _qobuz_dl_session_cache.client is not None):
            LOGGER.info("🔍 [QOBUZ-DL] Using persistent cached session for search")
            qobuz = _qobuz_dl_session_cache
            # Session is already authenticated, no need to re-authenticate
        else:
            # Setup new authentication session
            LOGGER.info("🔍 [QOBUZ-DL] Setting up new persistent authentication session")
            email, password = await setup_qobuz_module_auth()
            if not email or not password:
                LOGGER.warning("Qobuz authentication not available for search")
                return []

            from qobuz_dl.core import QobuzDL

            # Create QobuzDL instance for search
            qobuz = QobuzDL(
                directory="/tmp",  # Temporary directory for search
                quality=6,  # CD quality for search
                interactive_limit=limit,
            )

            # Initialize the client and authenticate
            try:
                qobuz.get_tokens()  # This authenticates and sets up the client
                qobuz.initialize_client(email, password, qobuz.app_id, qobuz.secrets)

                # Cache the session persistently (no timeout)
                _qobuz_dl_session_cache = qobuz
                _session_cache_status['qobuz_dl'] = True
                LOGGER.info("🔍 [QOBUZ-DL] Authentication session cached persistently (no timeout)")
            except Exception as auth_error:
                LOGGER.error(f"❌ [QOBUZ-DL] Authentication failed: {auth_error}")
                _session_cache_status['qobuz_dl'] = False
                return []

        results = []

        # Search for each content type using the correct qobuz-dl client methods
        for content_type in content_types:
            try:
                # Map content types to the correct client search methods
                search_method_map = {
                    "track": qobuz.client.search_tracks,
                    "album": qobuz.client.search_albums,
                    "playlist": qobuz.client.search_playlists,
                    "artist": qobuz.client.search_artists,
                }

                if content_type not in search_method_map:
                    LOGGER.warning(f"Unsupported Qobuz search type: {content_type}")
                    continue

                # Use the appropriate search method
                search_method = search_method_map[content_type]
                search_results = search_method(query, limit)

                # Extract items from the search results
                if search_results and content_type + "s" in search_results:
                    # Note: qobuz-dl returns plural keys (tracks, albums, playlists, artists)
                    items = search_results[content_type + "s"]["items"]

                    for item in items:
                        # Debug: Log the first item structure to understand the API response
                        if len(results) == 0:
                            LOGGER.info(f"🔍 [QOBUZ] Sample {content_type} item structure: {list(item.keys())}")
                            if "image" in item:
                                LOGGER.info(f"🔍 [QOBUZ] Image field structure: {item.get('image', {})}")

                        result = await _format_qobuz_search_result(item, content_type)
                        if result:
                            results.append(result)

            except Exception as e:
                LOGGER.error(f"Error searching Qobuz {content_type}: {e}")
                continue

        return results[:limit]

    except Exception as e:
        LOGGER.error(f"Qobuz search error: {e}")
        return []


async def search_tidal_content(query: str, content_types: list[str] = None, limit: int = 10) -> list[dict]:
    """Search Tidal for tracks, albums, playlists with persistent session caching"""
    try:
        # Import tidalapi at function level to ensure it's available
        try:
            import tidalapi
        except ImportError as e:
            LOGGER.error(f"❌ [TIDAL] Failed to import tidalapi: {e}")
            return []

        global _tidal_session_cache, _session_cache_status

        if not content_types:
            content_types = ["track", "album", "playlist"]

        # Check if we have a valid cached session (persistent, no timeout)
        if (_tidal_session_cache is not None and
            _session_cache_status['tidal'] and
            hasattr(_tidal_session_cache, 'check_login') and
            _tidal_session_cache.check_login()):
            LOGGER.info("🔍 [TIDAL] Using persistent cached session for search")
            session = _tidal_session_cache
        else:
            # Setup new Tidal authentication session
            LOGGER.info("🔍 [TIDAL] Setting up new persistent authentication session")
            session = tidalapi.Session()

            # Load existing credentials if available
            access_token = Config.TIDAL_ACCESS_TOKEN
            refresh_token = Config.TIDAL_REFRESH_TOKEN
            expiry_time = Config.TIDAL_EXPIRY_TIME

            if access_token and refresh_token:
                try:
                    # Convert expiry time to datetime if provided
                    expiry_datetime = None
                    if expiry_time:
                        try:
                            import datetime as dt
                            expiry_datetime = dt.datetime.fromtimestamp(float(expiry_time))
                        except (ValueError, TypeError):
                            LOGGER.warning("Invalid expiry time format, proceeding without expiry check")

                    # Load OAuth session with proper parameters (same as download functionality)
                    try:
                        auth_success = session.load_oauth_session(
                            token_type="Bearer",
                            access_token=access_token,
                            refresh_token=refresh_token,
                            expiry_time=expiry_datetime,
                        )
                    except Exception as load_error:
                        LOGGER.warning(f"❌ [TIDAL] OAuth session load failed: {load_error}")
                        auth_success = False

                    if not auth_success:
                        LOGGER.warning("❌ [TIDAL] Failed to authenticate with config credentials")

                        # Try to refresh token if refresh_token is available (same as download)
                        if refresh_token:
                            LOGGER.info("🔄 [TIDAL] Attempting to refresh token...")
                            refresh_success = session.token_refresh(refresh_token)
                            if refresh_success:
                                LOGGER.info("✅ [TIDAL] Successfully refreshed token")
                                # Token refreshed, try authentication again
                                auth_success = True
                            else:
                                LOGGER.warning("❌ [TIDAL] Failed to refresh token")
                                _session_cache_status['tidal'] = False
                                _tidal_session_cache = None
                                return []
                        else:
                            _session_cache_status['tidal'] = False
                            _tidal_session_cache = None
                            return []

                    # Verify authentication (same as download functionality)
                    if not session.check_login():
                        LOGGER.warning("❌ [TIDAL] Authentication verification failed")
                        _session_cache_status['tidal'] = False
                        _tidal_session_cache = None
                        return []

                    # Cache the session persistently (no timeout)
                    _tidal_session_cache = session
                    _session_cache_status['tidal'] = True
                    LOGGER.info("🔍 [TIDAL] Authentication session cached persistently (no timeout)")
                except Exception as e:
                    LOGGER.warning(f"❌ [TIDAL] Authentication failed: {e}")
                    # Clear cache on authentication failure
                    _session_cache_status['tidal'] = False
                    _tidal_session_cache = None
                    return []
            else:
                LOGGER.warning("❌ [TIDAL] Authentication not available - missing tokens in config")
                return []

        # Verify session is still valid
        try:
            if not session.check_login():
                LOGGER.warning("❌ [TIDAL] Authentication verification failed - clearing cache")
                # Clear cache if session is invalid
                _session_cache_status['tidal'] = False
                _tidal_session_cache = None
                return []
        except Exception as e:
            LOGGER.warning(f"❌ [TIDAL] Session verification error: {e} - clearing cache")
            _session_cache_status['tidal'] = False
            _tidal_session_cache = None
            return []

        results = []

        # Map content types to Tidal models
        model_mapping = {
            "track": tidalapi.Track,
            "album": tidalapi.Album,
            "playlist": tidalapi.Playlist,
            "artist": tidalapi.Artist
        }

        # Search for each content type
        for content_type in content_types:
            if content_type not in model_mapping:
                continue

            try:
                search_results = session.search(
                    query,
                    models=[model_mapping[content_type]],
                    limit=limit
                )

                if search_results and f"{content_type}s" in search_results:
                    items = search_results[f"{content_type}s"]

                    for item in items:
                        result = await _format_tidal_search_result(item, content_type)
                        if result:
                            results.append(result)

            except Exception as e:
                LOGGER.error(f"Error searching Tidal {content_type}: {e}")
                continue

        return results[:limit]

    except Exception as e:
        LOGGER.error(f"Tidal search error: {e}")
        return []


async def search_spotify_content(query: str, content_types: list[str] = None, limit: int = 10) -> list[dict]:
    """Search Spotify for tracks, albums, playlists using enhanced deezspot integration"""
    try:
        if not content_types:
            content_types = ["track", "album", "playlist"]

        results = []

        # Try enhanced deezspot search first for better metadata
        try:
            import sys
            import os
            deezspot_path = os.path.join(os.getcwd(), 'deezspot')
            if deezspot_path not in sys.path:
                sys.path.append(deezspot_path)
            from deezspot.easy_spoty import Spo

            LOGGER.info(f"🎧 [SPOTIFY] Using enhanced deezspot search for: {query}")

            # Use Spotify search API through deezspot
            search_results = Spo.search(query)

            for content_type in content_types:
                try:
                    if content_type == "track" and "tracks" in search_results:
                        track_items = search_results["tracks"]["items"][:limit]
                        for track in track_items:
                            formatted_result = await _format_spotify_deezspot_result(track, "track")
                            if formatted_result:
                                results.append(formatted_result)

                    elif content_type == "album" and "albums" in search_results:
                        album_items = search_results["albums"]["items"][:limit]
                        for album in album_items:
                            formatted_result = await _format_spotify_deezspot_result(album, "album")
                            if formatted_result:
                                results.append(formatted_result)

                    elif content_type == "playlist" and "playlists" in search_results:
                        playlist_items = search_results["playlists"]["items"][:limit]
                        for playlist in playlist_items:
                            formatted_result = await _format_spotify_deezspot_result(playlist, "playlist")
                            if formatted_result:
                                results.append(formatted_result)

                except Exception as search_error:
                    LOGGER.info(f"Deezspot {content_type} search failed: {search_error}")
                    continue

            if results:
                LOGGER.info(f"🎧 [SPOTIFY] Enhanced deezspot search found {len(results)} results")
                return results[:limit]

        except Exception as deezspot_error:
            LOGGER.warning(f"🎧 [SPOTIFY] Enhanced deezspot search failed: {deezspot_error}")

        # Fallback to existing Zotify search if available
        try:
            from bot.helper.mirror_leech_utils.zotify_utils.search_handler import zotify_search

            results = []
            for content_type in content_types:
                zotify_results = await zotify_search(query, content_type, limit)
                for result in zotify_results:
                    formatted_result = await _format_spotify_search_result(result, content_type)
                    if formatted_result:
                        results.append(formatted_result)

            if results:
                LOGGER.info(f"🎧 [SPOTIFY] Zotify fallback search found {len(results)} results")
                return results[:limit]

        except Exception as zotify_error:
            LOGGER.warning(f"🎧 [SPOTIFY] Zotify fallback search failed: {zotify_error}")

        LOGGER.info("🎧 [SPOTIFY] All search methods failed")
        return []

    except Exception as e:
        LOGGER.error(f"Spotify search error: {e}")
        return []


async def search_deezer_content(query: str, content_types: list[str] = None, limit: int = 10) -> list[dict]:
    """Search Deezer for tracks, albums, playlists using enhanced deezspot integration"""
    try:
        if not content_types:
            content_types = ["track", "album", "playlist"]

        results = []

        # Try enhanced deezspot search first for better metadata
        try:
            import sys
            import os
            deezspot_path = os.path.join(os.getcwd(), 'deezspot')
            if deezspot_path not in sys.path:
                sys.path.append(deezspot_path)
            from deezspot.deezloader.dee_api import API

            LOGGER.info(f"🎵 [DEEZER] Using enhanced deezspot search for: {query}")

            for content_type in content_types:
                try:
                    if content_type == "track":
                        # Use deezspot track search with enhanced metadata
                        track_results = API.search_track(query)
                        if track_results and "data" in track_results:
                            for track in track_results["data"][:limit]:
                                formatted_result = await _format_deezer_deezspot_result(track, "track")
                                if formatted_result:
                                    results.append(formatted_result)

                    elif content_type == "album":
                        # Use deezspot album search with enhanced metadata
                        album_results = API.search_album(query)
                        if album_results and "data" in album_results:
                            for album in album_results["data"][:limit]:
                                formatted_result = await _format_deezer_deezspot_result(album, "album")
                                if formatted_result:
                                    results.append(formatted_result)

                    elif content_type == "playlist":
                        # Use deezspot playlist search with enhanced metadata
                        playlist_results = API.search_playlist(query)
                        if playlist_results and "data" in playlist_results:
                            for playlist in playlist_results["data"][:limit]:
                                formatted_result = await _format_deezer_deezspot_result(playlist, "playlist")
                                if formatted_result:
                                    results.append(formatted_result)

                except Exception as search_error:
                    LOGGER.info(f"Deezspot {content_type} search failed: {search_error}")
                    continue

            if results:
                LOGGER.info(f"🎵 [DEEZER] Enhanced deezspot search found {len(results)} results")
                return results[:limit]

        except Exception as deezspot_error:
            LOGGER.warning(f"🎵 [DEEZER] Enhanced deezspot search failed: {deezspot_error}")

        # Fallback to Deezer API directly for search
        import aiohttp

        results = []

        async with aiohttp.ClientSession() as session:
            for content_type in content_types:
                try:
                    # Deezer API search endpoint
                    search_url = f"https://api.deezer.com/search/{content_type}"
                    params = {"q": query, "limit": limit}

                    async with session.get(search_url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()

                            if "data" in data:
                                for item in data["data"]:
                                    result = await _format_deezer_search_result(item, content_type)
                                    if result:
                                        results.append(result)

                except Exception as e:
                    LOGGER.error(f"Error searching Deezer {content_type}: {e}")
                    continue

        return results[:limit]

    except Exception as e:
        LOGGER.error(f"Deezer search error: {e}")
        return []


async def search_apple_content(query: str, content_types: list[str] = None, limit: int = 10) -> list[dict]:
    """Search Apple Music using iTunes Search API"""
    try:
        import aiohttp
        import urllib.parse

        # Skip very short queries that cause iTunes API issues
        if len(query.strip()) < 2:
            LOGGER.info("Apple Music search skipped - query too short")
            return []

        if not content_types:
            content_types = ["song", "album"]

        results = []

        # Try GAMDL Apple Music API first (requires cookies.txt)
        try:
            from gamdl.apple_music_api import AppleMusicApi
            from pathlib import Path

            # Check for cookies.txt file
            cookies_path = Path("cookies.txt")
            if cookies_path.exists():
                LOGGER.info("🍎 [APPLE] Using GAMDL Apple Music API for search")

                # Create Apple Music API instance
                api = AppleMusicApi.from_netscape_cookies(cookies_path)

                # Map content types to GAMDL search types
                type_mapping = {
                    "track": "songs",
                    "song": "songs",
                    "album": "albums",
                    "playlist": "playlists",
                    "artist": "artists"
                }

                # Build search types string
                search_types = ",".join([type_mapping[ct] for ct in content_types if ct in type_mapping])

                # Perform search using GAMDL
                search_results = api.search(term=query, types=search_types, limit=limit)

                LOGGER.info(f"🍎 [APPLE] GAMDL search returned: {list(search_results.keys()) if isinstance(search_results, dict) else type(search_results)}")

                # Process results from each content type
                for content_type in content_types:
                    if content_type not in type_mapping:
                        continue

                    gamdl_type = type_mapping[content_type]
                    if gamdl_type in search_results and search_results[gamdl_type]:
                        items = search_results[gamdl_type].get('data', [])

                        for item in items:
                            formatted_result = await _format_apple_gamdl_result(item, content_type)
                            if formatted_result:
                                results.append(formatted_result)

                if results:
                    LOGGER.info(f"🍎 [APPLE] GAMDL search found {len(results)} results")
                    return results[:limit]
                else:
                    LOGGER.info("🍎 [APPLE] GAMDL search returned no results, falling back to iTunes API")
            else:
                LOGGER.info("🍎 [APPLE] cookies.txt not found, using iTunes API fallback")

        except Exception as gamdl_error:
            LOGGER.warning(f"🍎 [APPLE] GAMDL search failed: {gamdl_error}, falling back to iTunes API")

        # Fallback to iTunes Search API
        LOGGER.info("🍎 [APPLE] Using iTunes Search API fallback")

        for content_type in content_types:
            # Map content types to iTunes API entities
            entity_map = {
                "track": "song",
                "song": "song",
                "album": "album",
                "playlist": "album"  # iTunes doesn't have playlist search
            }
            entity = entity_map.get(content_type, "song")

            # Clean and encode query
            clean_query = query.strip().replace('"', '').replace("'", "")
            encoded_query = urllib.parse.quote(clean_query)

            # Build iTunes Search API URL with proper headers
            url = f"https://itunes.apple.com/search?term={encoded_query}&entity={entity}&limit={limit}&media=music&country=US"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        content_type_header = response.headers.get('content-type', '')
                        if 'application/json' in content_type_header:
                            data = await response.json()

                            for item in data.get("results", []):
                                formatted_result = await _format_apple_search_result(item, content_type)
                                if formatted_result:
                                    results.append(formatted_result)
                        else:
                            LOGGER.warning(f"❌ [APPLE] iTunes API returned non-JSON content: {content_type_header} - likely rate limited")
                            # Add delay to avoid rate limiting
                            await asyncio.sleep(1)
                    elif response.status == 429:
                        LOGGER.warning(f"❌ [APPLE] iTunes API rate limited (429) - adding delay")
                        await asyncio.sleep(2)
                    elif response.status == 403:
                        LOGGER.warning(f"❌ [APPLE] iTunes API access forbidden (403) - possible IP blocking")
                    else:
                        LOGGER.warning(f"❌ [APPLE] iTunes Search API returned status {response.status}")

        LOGGER.info(f"Apple Music search found {len(results)} results")
        return results[:limit]

    except Exception as e:
        LOGGER.error(f"Apple Music search error: {e}")
        return []


async def _format_spotify_deezspot_result(item: dict, content_type: str) -> dict:
    """Format Spotify search result from enhanced deezspot API"""
    try:
        # Extract basic information from deezspot result
        result = {
            "id": f"spotify_{content_type}_{item.get('id', '')}",
            "title": item.get("name", "Unknown"),
            "platform": "spotify",
            "type": content_type,
            "url": item.get("external_urls", {}).get("spotify", ""),
            "thumbnail": "",
            "has_lyrics": False,
        }

        # Extract artist information
        if content_type in ["track", "song"]:
            artists = item.get("artists", [])
            result["artist"] = artists[0].get("name", "Unknown Artist") if artists else "Unknown Artist"

            album = item.get("album", {})
            result["album"] = album.get("name", "Unknown Album")
            result["duration"] = item.get("duration_ms", 0) // 1000

            # Extract thumbnail from album
            images = album.get("images", [])
            if images:
                # Get highest resolution image
                result["thumbnail"] = images[0].get("url", "")

            # Check for explicit content
            result["has_lyrics"] = not item.get("explicit", False)  # Approximate

        elif content_type == "album":
            artists = item.get("artists", [])
            result["artist"] = artists[0].get("name", "Unknown Artist") if artists else "Unknown Artist"
            result["track_count"] = item.get("total_tracks", 0)
            result["release_date"] = item.get("release_date", "")

            # Extract thumbnail
            images = item.get("images", [])
            if images:
                result["thumbnail"] = images[0].get("url", "")

        elif content_type == "playlist":
            owner = item.get("owner", {})
            result["artist"] = owner.get("display_name", "Spotify")

            tracks = item.get("tracks", {})
            result["track_count"] = tracks.get("total", 0)
            result["description"] = item.get("description", "")

            # Extract thumbnail
            images = item.get("images", [])
            if images:
                result["thumbnail"] = images[0].get("url", "")

        # Determine quality based on Spotify capabilities
        if content_type in ["track", "song"]:
            # Spotify quality depends on account type
            result["quality"] = "OGG Vorbis (320kbps Premium)"
            result["bitrate"] = "320kbps"
            result["sample_rate"] = 44100
            result["bit_depth"] = 16

        return result

    except Exception as e:
        LOGGER.error(f"Error formatting Spotify deezspot result: {e}")
        return None


async def _format_deezer_deezspot_result(item: dict, content_type: str) -> dict:
    """Format Deezer search result from enhanced deezspot API"""
    try:
        # Extract basic information from deezspot result
        result = {
            "id": f"deezer_{content_type}_{item.get('id', '')}",
            "title": item.get("title", "Unknown"),
            "platform": "deezer",
            "type": content_type,
            "url": item.get("link", ""),
            "thumbnail": "",
            "has_lyrics": False,
        }

        # Extract artist information
        if content_type in ["track", "song"]:
            artist = item.get("artist", {})
            result["artist"] = artist.get("name", "Unknown Artist")

            album = item.get("album", {})
            result["album"] = album.get("title", "Unknown Album")
            result["duration"] = item.get("duration", 0)

            # Extract thumbnail
            result["thumbnail"] = album.get("cover_xl", "") or album.get("cover_big", "")

            # Check for lyrics
            result["has_lyrics"] = item.get("lyrics", {}).get("id") is not None

        elif content_type == "album":
            artist = item.get("artist", {})
            result["artist"] = artist.get("name", "Unknown Artist")
            result["track_count"] = item.get("nb_tracks", 0)
            result["release_date"] = item.get("release_date", "")

            # Extract thumbnail
            result["thumbnail"] = item.get("cover_xl", "") or item.get("cover_big", "")

        elif content_type == "playlist":
            creator = item.get("creator", {})
            result["artist"] = creator.get("name", "Deezer")
            result["track_count"] = item.get("nb_tracks", 0)
            result["description"] = item.get("description", "")

            # Extract thumbnail
            result["thumbnail"] = item.get("picture_xl", "") or item.get("picture_big", "")

        # Determine quality based on Deezer capabilities
        if content_type in ["track", "song"]:
            # Deezer quality depends on account type
            result["quality"] = "FLAC/MP3 320kbps"
            result["bitrate"] = "1411kbps/320kbps"
            result["sample_rate"] = 44100
            result["bit_depth"] = 16

        return result

    except Exception as e:
        LOGGER.error(f"Error formatting Deezer deezspot result: {e}")
        return None


async def _format_apple_gamdl_result(item: dict, content_type: str) -> dict:
    """Format Apple Music search result from GAMDL API"""
    try:
        # Extract basic information from GAMDL result
        result = {
            "id": f"apple_{content_type}_{item.get('id', '')}",
            "title": item.get("attributes", {}).get("name", "Unknown"),
            "platform": "apple",
            "type": content_type,
            "url": item.get("attributes", {}).get("url", ""),
            "thumbnail": "",
            "has_lyrics": False,
        }

        # Extract artist information
        if content_type in ["track", "song"]:
            result["artist"] = item.get("attributes", {}).get("artistName", "Unknown Artist")
            result["album"] = item.get("attributes", {}).get("albumName", "Unknown Album")
            result["duration"] = item.get("attributes", {}).get("durationInMillis", 0) // 1000

            # Check for lyrics
            result["has_lyrics"] = item.get("attributes", {}).get("hasLyrics", False)

        elif content_type == "album":
            result["artist"] = item.get("attributes", {}).get("artistName", "Unknown Artist")
            result["track_count"] = item.get("attributes", {}).get("trackCount", 0)
            result["release_date"] = item.get("attributes", {}).get("releaseDate", "")

        elif content_type == "playlist":
            result["artist"] = item.get("attributes", {}).get("curatorName", "Apple Music")
            result["track_count"] = item.get("attributes", {}).get("trackCount", 0)
            result["description"] = item.get("attributes", {}).get("description", {}).get("standard", "")

        # Extract thumbnail (Apple Music artwork)
        artwork = item.get("attributes", {}).get("artwork", {})
        if artwork:
            # Apple Music artwork URL template
            url_template = artwork.get("url", "")
            if url_template:
                # Replace placeholders with high resolution
                result["thumbnail"] = url_template.replace("{w}", "600").replace("{h}", "600")

        # Determine quality based on Apple Music capabilities
        if content_type in ["track", "song"]:
            # Check for lossless/hi-res indicators
            audio_traits = item.get("attributes", {}).get("audioTraits", [])
            if "hi-res-lossless" in audio_traits:
                result["quality"] = "Hi-Res Lossless (ALAC)"
                result["bitrate"] = "24-bit/192kHz"
                result["sample_rate"] = 192000
                result["bit_depth"] = 24
            elif "lossless" in audio_traits:
                result["quality"] = "Apple Lossless (ALAC)"
                result["bitrate"] = "16-bit/44.1kHz"
                result["sample_rate"] = 44100
                result["bit_depth"] = 16
            elif "spatial" in audio_traits or "atmos" in audio_traits:
                result["quality"] = "Spatial Audio (Dolby Atmos)"
                result["bitrate"] = "Spatial Audio"
                result["sample_rate"] = 48000
                result["bit_depth"] = 24
            else:
                result["quality"] = "AAC 256kbps"
                result["bitrate"] = "256kbps"
                result["sample_rate"] = 44100
                result["bit_depth"] = 16

        return result

    except Exception as e:
        LOGGER.error(f"Error formatting Apple Music GAMDL result: {e}")
        return None


async def _format_apple_search_result(item: dict, content_type: str) -> dict:
    """Format Apple Music/iTunes search result to standardized format"""
    try:
        result = {
            "id": f"apple_{content_type}_{item.get('trackId', item.get('collectionId', ''))}",
            "title": item.get("trackName", item.get("collectionName", "Unknown")),
            "platform": "apple",
            "type": content_type,
            "url": item.get("trackViewUrl", item.get("collectionViewUrl", "")),
            "thumbnail": item.get("artworkUrl100", "").replace("100x100", "600x600"),  # Get higher res
            "has_lyrics": False,  # iTunes API doesn't provide lyrics info
        }

        if content_type in ["track", "song"]:
            result["artist"] = item.get("artistName", "Unknown Artist")
            result["duration"] = item.get("trackTimeMillis", 0) // 1000  # Convert to seconds
            result["album"] = item.get("collectionName", "")

            # GAMDL quality detection based on Apple Music capabilities
            # Check if track supports lossless/hi-res (based on collection type or explicit indicators)
            collection_type = item.get("collectionType", "").lower()
            track_explicit = item.get("trackExplicitness", "").lower()

            # Apple Music Lossless/Hi-Res detection
            if "lossless" in str(item.get("longDescription", "")).lower() or "hi-res" in str(item.get("longDescription", "")).lower():
                result["quality"] = "Hi-Res Lossless (ALAC)"
                result["bitrate"] = "24-bit/192kHz"
                result["sample_rate"] = 192000
                result["bit_depth"] = 24
            elif "spatial" in str(item.get("longDescription", "")).lower() or "atmos" in str(item.get("longDescription", "")).lower():
                result["quality"] = "Spatial Audio (Dolby Atmos)"
                result["bitrate"] = "Spatial Audio"
                result["sample_rate"] = 48000
                result["bit_depth"] = 24
            elif collection_type and "lossless" in collection_type:
                result["quality"] = "Apple Lossless (ALAC)"
                result["bitrate"] = "16-bit/44.1kHz"
                result["sample_rate"] = 44100
                result["bit_depth"] = 16
            else:
                # Default AAC quality that GAMDL downloads
                result["quality"] = "AAC 256kbps"
                result["bitrate"] = "256kbps"
                result["sample_rate"] = 44100
                result["bit_depth"] = 16

        elif content_type == "album":
            result["artist"] = item.get("artistName", "Unknown Artist")
            result["track_count"] = item.get("trackCount", 0)
            result["release_date"] = item.get("releaseDate", "")

            # Album quality based on collection info
            collection_type = item.get("collectionType", "").lower()
            if "lossless" in str(item.get("longDescription", "")).lower():
                result["quality"] = "Apple Lossless (ALAC)"
                result["bitrate"] = "Up to 24-bit/192kHz"
            else:
                result["quality"] = "AAC 256kbps"
                result["bitrate"] = "256kbps"

        elif content_type == "artist":
            result["artist"] = item.get("artistName", "Unknown Artist")
            result["track_count"] = 0  # Artists don't have direct track count
            result["duration"] = 0
            result["quality"] = "Various"
            result["bitrate"] = "Various"

        return result

    except Exception as e:
        LOGGER.error(f"Error formatting Apple Music result: {e}")
        return None


# Result formatting functions
async def _format_qobuz_search_result(item: dict, content_type: str) -> dict:
    """Format Qobuz search result to standardized format with proper metadata extraction"""
    try:
        # Extract thumbnail from Qobuz API response structure
        thumbnail = ""

        # Qobuz API structure: item.image.large/medium/small or direct URL
        if "image" in item and item["image"]:
            image_data = item["image"]
            if isinstance(image_data, dict):
                # Qobuz returns: {"thumbnail": "url", "small": "url", "large": "url"}
                thumbnail = (image_data.get("large") or
                           image_data.get("medium") or
                           image_data.get("small") or
                           image_data.get("thumbnail") or "")
            elif isinstance(image_data, str):
                thumbnail = image_data

        # For tracks, also check album artwork
        if not thumbnail and content_type == "track" and "album" in item and item["album"]:
            album_data = item["album"]
            if "image" in album_data and album_data["image"]:
                album_image = album_data["image"]
                if isinstance(album_image, dict):
                    thumbnail = (album_image.get("large") or
                               album_image.get("medium") or
                               album_image.get("small") or "")
                elif isinstance(album_image, str):
                    thumbnail = album_image

        result = {
            "id": f"qobuz_{content_type}_{item.get('id', '')}",
            "title": item.get("title", "Unknown"),
            "platform": "qobuz",
            "type": content_type,
            "url": f"https://play.qobuz.com/{content_type}/{item.get('id', '')}",
            "thumbnail": thumbnail,
            "has_lyrics": False,  # Qobuz doesn't provide lyrics in search API
        }

        if content_type == "track":
            # Extract artist with proper Qobuz API structure
            artist = "Unknown Artist"
            if "performer" in item and item["performer"]:
                artist = item["performer"].get("name", "Unknown Artist")
            elif "artist" in item and item["artist"]:
                artist = item["artist"].get("name", "Unknown Artist")
            elif "album" in item and item["album"] and "artist" in item["album"]:
                artist = item["album"]["artist"].get("name", "Unknown Artist")

            result["artist"] = artist
            result["duration"] = item.get("duration", 0)
            result["album"] = item.get("album", {}).get("title", "")

            # Extract actual quality from Qobuz API response
            max_sampling_rate = item.get("maximum_sampling_rate", 44100)
            max_bit_depth = item.get("maximum_bit_depth", 16)

            # Determine quality based on actual track specifications
            if max_sampling_rate >= 192000 and max_bit_depth >= 24:
                result["quality"] = "Hi-Res FLAC 24-bit/192kHz"
                result["bitrate"] = "24-bit/192kHz"
            elif max_sampling_rate >= 96000 and max_bit_depth >= 24:
                result["quality"] = "Hi-Res FLAC 24-bit/96kHz"
                result["bitrate"] = "24-bit/96kHz"
            elif max_sampling_rate >= 48000 and max_bit_depth >= 24:
                result["quality"] = "Hi-Res FLAC 24-bit/48kHz"
                result["bitrate"] = "24-bit/48kHz"
            elif max_bit_depth >= 16 and max_sampling_rate >= 44100:
                result["quality"] = "CD FLAC 16-bit/44.1kHz"
                result["bitrate"] = "16-bit/44.1kHz"
            else:
                result["quality"] = "FLAC"
                result["bitrate"] = f"{max_bit_depth}bit/{max_sampling_rate}Hz"

            result["sample_rate"] = max_sampling_rate
            result["bit_depth"] = max_bit_depth

        elif content_type == "album":
            result["artist"] = item.get("artist", {}).get("name", "Unknown Artist")
            result["track_count"] = item.get("tracks_count", 0)
            result["duration"] = item.get("duration", 0)
            result["release_date"] = item.get("released_at", "")

            # Extract highest quality available in album
            max_sampling_rate = item.get("maximum_sampling_rate", 44100)
            max_bit_depth = item.get("maximum_bit_depth", 16)

            # Determine album quality based on highest track quality
            if max_sampling_rate >= 192000 and max_bit_depth >= 24:
                result["quality"] = "Hi-Res FLAC 24-bit/192kHz"
                result["bitrate"] = "Up to 24-bit/192kHz"
            elif max_sampling_rate >= 96000 and max_bit_depth >= 24:
                result["quality"] = "Hi-Res FLAC 24-bit/96kHz"
                result["bitrate"] = "Up to 24-bit/96kHz"
            elif max_bit_depth >= 16:
                result["quality"] = "CD FLAC 16-bit/44.1kHz"
                result["bitrate"] = "16-bit/44.1kHz"
            else:
                result["quality"] = "FLAC"
                result["bitrate"] = f"{max_bit_depth}bit/{max_sampling_rate}Hz"

        elif content_type == "playlist":
            result["artist"] = item.get("owner", {}).get("name", "Unknown User")
            result["track_count"] = item.get("tracks_count", 0)
            result["duration"] = item.get("duration", 0)
            result["quality"] = "Mixed Quality"
            result["bitrate"] = "Various"

        elif content_type == "artist":
            result["artist"] = item.get("name", "Unknown Artist")
            result["track_count"] = item.get("albums_count", 0)  # Show album count for artists
            result["duration"] = 0  # Artists don't have duration
            result["quality"] = "Various"
            result["bitrate"] = "Various"

        return result

    except Exception as e:
        LOGGER.error(f"Error formatting Qobuz result: {e}")
        return None


async def _format_tidal_search_result(item, content_type: str) -> dict:
    """Format Tidal search result to standardized format with proper quality detection"""
    try:
        # Extract thumbnail from Tidal API response using proper tidalapi methods
        thumbnail = ""
        try:
            if content_type in ["track", "song"] and hasattr(item, 'album') and item.album:
                # For tracks, get thumbnail from album
                thumbnail = item.album.image(640)  # 640x640 resolution
            elif content_type == "album" and hasattr(item, 'image'):
                # For albums, use the album's image method
                thumbnail = item.image(640)  # 640x640 resolution
            elif content_type == "playlist" and hasattr(item, 'image'):
                # For playlists, use the playlist's image method if available
                thumbnail = item.image(640)
            elif hasattr(item, 'cover') and item.cover:
                # Fallback: construct image URL from cover ID
                if hasattr(item, 'session') and hasattr(item.session, 'config'):
                    thumbnail = item.session.config.image_url % (
                        item.cover.replace("-", "/"), 640, 640
                    )
        except Exception as thumb_error:
            LOGGER.debug(f"Failed to extract Tidal thumbnail: {thumb_error}")
            thumbnail = ""

        result = {
            "id": f"tidal_{content_type}_{item.id}",
            "title": item.name,
            "platform": "tidal",
            "type": content_type,
            "url": f"https://tidal.com/browse/{content_type}/{item.id}",
            "thumbnail": thumbnail,
            "has_lyrics": False,
        }

        if content_type == "track":
            result["artist"] = item.artist.name if item.artist else "Unknown Artist"
            result["duration"] = item.duration if hasattr(item, 'duration') else 0
            result["album"] = item.album.name if item.album else ""

            # Determine quality based on Tidal's actual API attributes
            # Based on library analysis: audio_quality, is_hi_res_lossless, is_lossless
            if hasattr(item, 'is_hi_res_lossless') and getattr(item, 'is_hi_res_lossless', False):
                result["quality"] = "Hi-Res FLAC 24-bit/192kHz"
                result["bitrate"] = "24-bit/192kHz"
                result["sample_rate"] = 192000
                result["bit_depth"] = 24
            elif hasattr(item, 'is_lossless') and getattr(item, 'is_lossless', False):
                result["quality"] = "Lossless FLAC 16-bit/44.1kHz"
                result["bitrate"] = "16-bit/44.1kHz"
                result["sample_rate"] = 44100
                result["bit_depth"] = 16
            elif hasattr(item, 'audio_quality'):
                # Check audio_quality attribute for quality level
                audio_quality = getattr(item, 'audio_quality', '')
                if 'HI_RES' in str(audio_quality):
                    result["quality"] = "Hi-Res FLAC 24-bit/96kHz"
                    result["bitrate"] = "24-bit/96kHz"
                    result["sample_rate"] = 96000
                    result["bit_depth"] = 24
                elif 'LOSSLESS' in str(audio_quality):
                    result["quality"] = "Lossless FLAC 16-bit/44.1kHz"
                    result["bitrate"] = "16-bit/44.1kHz"
                    result["sample_rate"] = 44100
                    result["bit_depth"] = 16
                else:
                    result["quality"] = "Hi-Fi"
                    result["bitrate"] = "320kbps"
                    result["sample_rate"] = 44100
                    result["bit_depth"] = 16
            else:
                # Default to high quality
                result["quality"] = "Hi-Fi"
                result["bitrate"] = "320kbps"
                result["sample_rate"] = 44100
                result["bit_depth"] = 16

            # Check for lyrics availability
            result["has_lyrics"] = hasattr(item, 'lyrics') and item.lyrics is not None

        elif content_type == "album":
            result["artist"] = item.artist.name if item.artist else "Unknown Artist"
            result["track_count"] = item.num_tracks if hasattr(item, 'num_tracks') else 0
            result["duration"] = item.duration if hasattr(item, 'duration') else 0
            result["release_date"] = str(item.release_date) if hasattr(item, 'release_date') else ""

            # Determine album quality based on audio resolution
            if hasattr(item, 'get_audio_resolution'):
                try:
                    audio_res = item.get_audio_resolution()
                    if audio_res and 'HI_RES' in str(audio_res):
                        result["quality"] = "Hi-Res FLAC"
                        result["bitrate"] = "Up to 24-bit/192kHz"
                    elif audio_res and 'LOSSLESS' in str(audio_res):
                        result["quality"] = "Lossless FLAC"
                        result["bitrate"] = "16-bit/44.1kHz"
                    else:
                        result["quality"] = "Hi-Fi"
                        result["bitrate"] = "320kbps"
                except:
                    result["quality"] = "Hi-Fi"
                    result["bitrate"] = "Up to 24-bit/96kHz"
            else:
                result["quality"] = "Hi-Fi"
                result["bitrate"] = "Up to 24-bit/96kHz"

        elif content_type == "playlist":
            result["artist"] = "Tidal Playlist"
            result["track_count"] = item.num_tracks if hasattr(item, 'num_tracks') else 0
            result["duration"] = item.duration if hasattr(item, 'duration') else 0
            result["quality"] = "Mixed Quality"
            result["bitrate"] = "Various"

        elif content_type == "artist":
            result["artist"] = item.name
            result["track_count"] = 0  # Artists don't have direct track count
            result["duration"] = 0
            result["quality"] = "Various"
            result["bitrate"] = "Various"

        # Extract thumbnail from Tidal API based on actual structure
        # From library analysis: Albums have 'cover', 'image', 'video_cover'
        if hasattr(item, 'image') and getattr(item, 'image', None):
            result["thumbnail"] = item.image
        elif hasattr(item, 'cover') and getattr(item, 'cover', None):
            result["thumbnail"] = item.cover
        elif hasattr(item, 'picture') and getattr(item, 'picture', None):
            # Tidal picture format: UUID that needs to be converted to URL
            picture_id = str(item.picture).replace('-', '/')
            result["thumbnail"] = f"https://resources.tidal.com/images/{picture_id}/640x640.jpg"
        elif content_type == "track" and hasattr(item, 'album') and item.album:
            # For tracks, try to get album artwork
            album = item.album
            if hasattr(album, 'cover') and getattr(album, 'cover', None):
                result["thumbnail"] = album.cover
            elif hasattr(album, 'image') and getattr(album, 'image', None):
                result["thumbnail"] = album.image

        return result

    except Exception as e:
        LOGGER.error(f"Error formatting Tidal result: {e}")
        return None


async def _format_spotify_search_result(item: dict, content_type: str) -> dict:
    """Format Spotify search result to standardized format"""
    try:
        result = {
            "id": f"spotify_{content_type}_{item.get('id', '')}",
            "title": item.get("name", "Unknown"),
            "platform": "spotify",
            "type": content_type,
            "url": item.get("external_urls", {}).get("spotify", ""),
            "thumbnail": "",
            "has_lyrics": False,  # Spotify doesn't provide lyrics info in search
        }

        if content_type == "track":
            artists = item.get("artists", [])
            result["artist"] = artists[0].get("name", "Unknown Artist") if artists else "Unknown Artist"
            result["duration"] = item.get("duration_ms", 0) // 1000  # Convert to seconds
            result["album"] = item.get("album", {}).get("name", "")
            result["quality"] = "OGG Vorbis"
            result["bitrate"] = "Up to 320kbps"
            result["sample_rate"] = 44100  # Spotify standard

        elif content_type == "album":
            artists = item.get("artists", [])
            result["artist"] = artists[0].get("name", "Unknown Artist") if artists else "Unknown Artist"
            result["track_count"] = item.get("total_tracks", 0)
            result["release_date"] = item.get("release_date", "")
            result["quality"] = "OGG Vorbis"
            result["bitrate"] = "Up to 320kbps"

        elif content_type == "playlist":
            result["artist"] = item.get("owner", {}).get("display_name", "Unknown User")
            result["track_count"] = item.get("tracks", {}).get("total", 0)

        # Get thumbnail
        images = item.get("images", [])
        if images:
            result["thumbnail"] = images[0].get("url", "")

        return result

    except Exception as e:
        LOGGER.error(f"Error formatting Spotify result: {e}")
        return None


async def _format_deezer_search_result(item: dict, content_type: str) -> dict:
    """Format Deezer search result to standardized format"""
    try:
        result = {
            "id": f"deezer_{content_type}_{item.get('id', '')}",
            "title": item.get("title", "Unknown"),
            "platform": "deezer",
            "type": content_type,
            "url": item.get("link", ""),
            "thumbnail": "",
            "has_lyrics": False,  # Deezer doesn't provide lyrics info in search
        }

        if content_type == "track":
            artist_info = item.get("artist", {})
            result["artist"] = artist_info.get("name", "Unknown Artist")
            result["duration"] = item.get("duration", 0)
            album_info = item.get("album", {})
            result["album"] = album_info.get("title", "")
            result["quality"] = "FLAC/MP3"
            result["bitrate"] = "Up to 1411kbps"
            result["sample_rate"] = 44100  # Deezer standard

        elif content_type == "album":
            artist_info = item.get("artist", {})
            result["artist"] = artist_info.get("name", "Unknown Artist")
            result["track_count"] = item.get("nb_tracks", 0)
            result["release_date"] = item.get("release_date", "")
            result["quality"] = "FLAC/MP3"
            result["bitrate"] = "Up to 1411kbps"

        elif content_type == "playlist":
            user_info = item.get("user", {})
            result["artist"] = user_info.get("name", "Unknown User")
            result["track_count"] = item.get("nb_tracks", 0)

        # Get thumbnail
        if "picture_medium" in item:
            result["thumbnail"] = item["picture_medium"]
        elif "cover_medium" in item:
            result["thumbnail"] = item["cover_medium"]

        return result

    except Exception as e:
        LOGGER.error(f"Error formatting Deezer result: {e}")
        return None


# Unified search coordinator
async def unified_musicdl_search(query: str, platform_prefix: str = None, limit: int = 20) -> list[dict]:
    """
    Unified search across all musicdl platforms with prioritization and deduplication

    Args:
        query: Search query string
        platform_prefix: Platform filter (qb, td, am, sp, dz, mdl, or None for all)
        limit: Maximum number of results to return

    Returns:
        List of standardized search results sorted by platform priority
    """
    try:
        LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Starting unified search for: '{query}' | Prefix: {platform_prefix} | Limit: {limit}")
        all_results = []

        # Define platform priority order: Qobuz > Tidal > Apple Music > Spotify > Deezer
        platform_order = ["qobuz", "tidal", "apple", "spotify", "deezer"]

        # Map platform prefixes to platform names
        prefix_mapping = {
            "qb": "qobuz",
            "td": "tidal",
            "am": "apple",
            "sp": "spotify",
            "dz": "deezer",
            "mdl": None,  # All platforms
        }

        # Determine which platforms to search
        if platform_prefix and platform_prefix in prefix_mapping:
            target_platform = prefix_mapping[platform_prefix]
            platforms_to_search = [target_platform] if target_platform else platform_order
            LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Using platform filter: {platform_prefix} -> {platforms_to_search}")
        else:
            platforms_to_search = platform_order
            LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Searching all platforms in priority order: {platforms_to_search}")

        # Search each platform
        search_tasks = []
        authenticated_platforms = []

        for platform in platforms_to_search:
            # Check authentication before searching
            auth_status = await verify_authentication(platform)
            if not auth_status:
                LOGGER.info(f"❌ [MUSICDL-UNIFIED] Skipping {platform} search - authentication not available")
                continue

            authenticated_platforms.append(platform)
            platform_limit = limit//len(platforms_to_search) + 5
            LOGGER.info(f"✅ [MUSICDL-UNIFIED] {platform.upper()} authenticated, creating search task with limit {platform_limit}")

            # Create search task for platform
            if platform == "qobuz":
                search_tasks.append(asyncio.create_task(
                    search_qobuz_content(query, limit=platform_limit)
                ))
            elif platform == "tidal":
                search_tasks.append(asyncio.create_task(
                    search_tidal_content(query, limit=platform_limit)
                ))
            elif platform == "apple":
                search_tasks.append(asyncio.create_task(
                    search_apple_content(query, limit=platform_limit)
                ))
            elif platform == "spotify":
                search_tasks.append(asyncio.create_task(
                    search_spotify_content(query, limit=platform_limit)
                ))
            elif platform == "deezer":
                search_tasks.append(asyncio.create_task(
                    search_deezer_content(query, limit=platform_limit)
                ))
            else:
                continue

        LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Created {len(search_tasks)} search tasks for platforms: {authenticated_platforms}")

        # Execute all searches concurrently
        if search_tasks:
            LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Executing {len(search_tasks)} search tasks concurrently...")
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            # Combine results from all platforms
            for i, results in enumerate(search_results):
                platform = authenticated_platforms[i] if i < len(authenticated_platforms) else "unknown"
                if isinstance(results, list):
                    all_results.extend(results)
                    LOGGER.info(f"✅ [MUSICDL-UNIFIED] {platform.upper()} returned {len(results)} results")
                    if results:
                        LOGGER.info(f"🔍 [MUSICDL-UNIFIED] {platform} first result: {results[0].get('title', 'Unknown')} by {results[0].get('artist', 'Unknown')}")
                elif isinstance(results, Exception):
                    LOGGER.error(f"❌ [MUSICDL-UNIFIED] {platform.upper()} search task failed: {results}")
                else:
                    LOGGER.warning(f"⚠️ [MUSICDL-UNIFIED] {platform.upper()} returned unexpected result type: {type(results)}")
        else:
            LOGGER.warning(f"⚠️ [MUSICDL-UNIFIED] No search tasks created - no authenticated platforms available")

        LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Total raw results collected: {len(all_results)}")

        # Remove duplicates based on title + artist combination
        seen_tracks = set()
        deduplicated_results = []

        # Sort by platform priority first
        platform_priority = {platform: i for i, platform in enumerate(platform_order)}
        all_results.sort(key=lambda x: platform_priority.get(x.get("platform", ""), 999))
        LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Sorted results by platform priority: {[r.get('platform') for r in all_results[:5]]}")

        for result in all_results:
            # Create unique identifier for deduplication
            title = result.get("title", "").lower().strip()
            artist = result.get("artist", "").lower().strip()
            track_key = f"{title}|{artist}"

            # Skip duplicates, keeping the higher priority platform
            if track_key not in seen_tracks:
                seen_tracks.add(track_key)
                deduplicated_results.append(result)
                LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Added unique result: {result.get('title')} by {result.get('artist')} from {result.get('platform')}")
            else:
                LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Skipped duplicate: {result.get('title')} by {result.get('artist')} from {result.get('platform')}")

        LOGGER.info(f"🔍 [MUSICDL-UNIFIED] After deduplication: {len(deduplicated_results)} unique results")

        # Return limited results
        final_results = deduplicated_results[:limit]
        LOGGER.info(f"🔍 [MUSICDL-UNIFIED] Returning {len(final_results)} results (limited from {len(deduplicated_results)})")
        return final_results

    except Exception as e:
        LOGGER.error(f"Unified search error: {e}")
        return []


# Helper functions for inline search
# Global cache for callback data to avoid Telegram's 64-byte limit
_callback_data_cache = {}

async def _store_musicdl_callback_data(data: dict) -> str:
    """Store callback data and return a short ID"""
    try:
        import hashlib
        import time

        # Create a short unique ID based on data content and timestamp
        data_str = str(sorted(data.items()))
        timestamp = str(int(time.time()))
        unique_id = hashlib.md5(f"{data_str}_{timestamp}".encode()).hexdigest()[:12]

        # Store in cache
        _callback_data_cache[unique_id] = data

        # Clean old entries (keep only last 1000 entries)
        if len(_callback_data_cache) > 1000:
            # Remove oldest 200 entries
            old_keys = list(_callback_data_cache.keys())[:-800]
            for key in old_keys:
                _callback_data_cache.pop(key, None)

        return unique_id

    except Exception as e:
        LOGGER.error(f"Error storing callback data: {e}")
        return "error"


async def _get_musicdl_callback_data(callback_id: str) -> dict:
    """Retrieve callback data by ID"""
    try:
        return _callback_data_cache.get(callback_id, {})
    except Exception as e:
        LOGGER.error(f"Error retrieving callback data: {e}")
        return {}


# Legacy functions for backward compatibility
async def _encrypt_musicdl_callback_data(data: dict) -> str:
    """Legacy function - now uses storage instead of encryption"""
    return await _store_musicdl_callback_data(data)


async def _decrypt_musicdl_callback_data(encrypted_data: str) -> dict:
    """Legacy function - now uses retrieval instead of decryption"""
    return await _get_musicdl_callback_data(encrypted_data)


async def _fetch_url_metadata(url: str, platform: str) -> dict | None:
    """Fetch actual metadata from a music platform URL"""
    try:
        if platform == "tidal":
            return await _fetch_tidal_url_metadata(url)
        elif platform == "qobuz":
            return await _fetch_qobuz_url_metadata(url)
        elif platform == "apple":
            return await _fetch_apple_url_metadata(url)
        elif platform == "spotify":
            return await _fetch_spotify_url_metadata(url)
        elif platform == "deezer":
            return await _fetch_deezer_url_metadata(url)
        else:
            return None
    except Exception as e:
        LOGGER.warning(f"Failed to fetch {platform} metadata for {url}: {e}")
        return None


async def _fetch_tidal_url_metadata(url: str) -> dict | None:
    """Fetch metadata from Tidal URL using tidalapi"""
    try:
        import tidalapi

        # Use cached session if available
        global _tidal_session_cache, _session_cache_status
        session = _tidal_session_cache if _session_cache_status.get('tidal', False) else None

        if not session:
            # Try to create a new session
            session = tidalapi.Session()
            access_token = Config.TIDAL_ACCESS_TOKEN
            refresh_token = Config.TIDAL_REFRESH_TOKEN

            if access_token and refresh_token:
                session.load_oauth_session(
                    token_type="Bearer",
                    access_token=access_token,
                    refresh_token=refresh_token
                )
                if session.check_login():
                    _tidal_session_cache = session
                    _session_cache_status['tidal'] = True
                else:
                    return None
            else:
                return None

        # Extract ID from URL
        import re
        track_match = re.search(r'/track/(\d+)', url)
        album_match = re.search(r'/album/(\d+)', url)
        playlist_match = re.search(r'/playlist/([a-f0-9-]+)', url)

        if track_match:
            track_id = track_match.group(1)
            track = session.track(track_id)
            if track:
                return {
                    "id": f"tidal_track_{track_id}",
                    "title": track.name,
                    "artist": track.artist.name if track.artist else "Unknown Artist",
                    "album": track.album.name if track.album else "Unknown Album",
                    "duration": track.duration or 0,
                    "platform": "tidal",
                    "type": "track",
                    "url": url,
                    "thumbnail": track.album.image if track.album else "",
                    "has_lyrics": False,  # Tidal doesn't expose this easily
                    "quality": "Hi-Fi/MQA",
                    "bitrate": "1411kbps",
                    "sample_rate": 44100,
                    "bit_depth": 16
                }
        elif album_match:
            album_id = album_match.group(1)
            album = session.album(album_id)
            if album:
                return {
                    "id": f"tidal_album_{album_id}",
                    "title": album.name,
                    "artist": album.artist.name if album.artist else "Unknown Artist",
                    "platform": "tidal",
                    "type": "album",
                    "url": url,
                    "thumbnail": album.image or "",
                    "track_count": album.num_tracks or 0,
                    "release_date": str(album.release_date) if album.release_date else "",
                    "quality": "Hi-Fi/MQA",
                    "bitrate": "1411kbps"
                }
        elif playlist_match:
            playlist_id = playlist_match.group(1)
            playlist = session.playlist(playlist_id)
            if playlist:
                return {
                    "id": f"tidal_playlist_{playlist_id}",
                    "title": playlist.name,
                    "artist": playlist.creator.name if playlist.creator else "Tidal",
                    "platform": "tidal",
                    "type": "playlist",
                    "url": url,
                    "thumbnail": playlist.image or "",
                    "track_count": playlist.num_tracks or 0,
                    "description": playlist.description or "",
                    "quality": "Hi-Fi/MQA"
                }

        return None
    except Exception as e:
        LOGGER.warning(f"Failed to fetch Tidal metadata: {e}")
        return None


async def _fetch_qobuz_url_metadata(url: str) -> dict | None:
    """Fetch metadata from Qobuz URL using qobuz-dl"""
    try:
        # Use cached session if available
        global _qobuz_session_cache, _session_cache_status
        if _session_cache_status.get('qobuz', False) and _qobuz_session_cache:
            qobuz = _qobuz_session_cache
        else:
            return None

        # Extract ID from URL
        import re
        track_match = re.search(r'/track/(\d+)', url)
        album_match = re.search(r'/album/([a-zA-Z0-9]+)', url)
        playlist_match = re.search(r'/playlist/(\d+)', url)

        if track_match:
            track_id = track_match.group(1)
            track_info = qobuz.get_track_meta(track_id)
            if track_info:
                return {
                    "id": f"qobuz_track_{track_id}",
                    "title": track_info.get("title", "Unknown Title"),
                    "artist": track_info.get("performer", {}).get("name", "Unknown Artist"),
                    "album": track_info.get("album", {}).get("title", "Unknown Album"),
                    "duration": track_info.get("duration", 0),
                    "platform": "qobuz",
                    "type": "track",
                    "url": url,
                    "thumbnail": track_info.get("album", {}).get("image", {}).get("large", ""),
                    "has_lyrics": False,
                    "quality": "Hi-Res FLAC",
                    "bitrate": f"{track_info.get('maximum_bit_depth', 24)}-bit/{track_info.get('maximum_sampling_rate', 192)}kHz",
                    "sample_rate": track_info.get('maximum_sampling_rate', 192000),
                    "bit_depth": track_info.get('maximum_bit_depth', 24)
                }
        elif album_match:
            album_id = album_match.group(1)
            album_info = qobuz.get_album_meta(album_id)
            if album_info:
                return {
                    "id": f"qobuz_album_{album_id}",
                    "title": album_info.get("title", "Unknown Album"),
                    "artist": album_info.get("artist", {}).get("name", "Unknown Artist"),
                    "platform": "qobuz",
                    "type": "album",
                    "url": url,
                    "thumbnail": album_info.get("image", {}).get("large", ""),
                    "track_count": album_info.get("tracks_count", 0),
                    "release_date": album_info.get("release_date_original", ""),
                    "quality": "Hi-Res FLAC",
                    "bitrate": f"{album_info.get('maximum_bit_depth', 24)}-bit/{album_info.get('maximum_sampling_rate', 192)}kHz"
                }

        return None
    except Exception as e:
        LOGGER.warning(f"Failed to fetch Qobuz metadata: {e}")
        return None


async def _fetch_apple_url_metadata(url: str) -> dict | None:
    """Fetch metadata from Apple Music URL using GAMDL or iTunes API"""
    try:
        # Try GAMDL first if cookies.txt exists
        from pathlib import Path
        cookies_path = Path("cookies.txt")

        if cookies_path.exists():
            try:
                from gamdl.apple_music_api import AppleMusicApi
                api = AppleMusicApi.from_netscape_cookies(cookies_path)

                # Extract ID from URL
                import re
                track_match = re.search(r'/song/[^/]+/(\d+)', url)
                album_match = re.search(r'/album/[^/]+/(\d+)', url)
                playlist_match = re.search(r'/playlist/[^/]+/([a-zA-Z0-9.]+)', url)

                if track_match:
                    track_id = track_match.group(1)
                    # Use GAMDL to get track info
                    # This would require implementing GAMDL track lookup
                    pass
                elif album_match:
                    album_id = album_match.group(1)
                    # Use GAMDL to get album info
                    pass
                elif playlist_match:
                    playlist_id = playlist_match.group(1)
                    # Use GAMDL to get playlist info
                    pass

            except Exception as gamdl_error:
                LOGGER.info(f"GAMDL metadata fetch failed: {gamdl_error}")

        # Fallback to iTunes Search API for basic info
        import aiohttp
        import re

        # Extract search terms from URL
        url_parts = url.split('/')
        if len(url_parts) > 2:
            search_term = url_parts[-2].replace('-', ' ')

            async with aiohttp.ClientSession() as session:
                search_url = "https://itunes.apple.com/search"
                params = {
                    "term": search_term,
                    "entity": "song",
                    "media": "music",
                    "limit": 1,
                    "country": "US"
                }

                async with session.get(search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        if results:
                            item = results[0]
                            return {
                                "id": f"apple_track_{item.get('trackId', '')}",
                                "title": item.get("trackName", "Unknown Title"),
                                "artist": item.get("artistName", "Unknown Artist"),
                                "album": item.get("collectionName", "Unknown Album"),
                                "duration": (item.get("trackTimeMillis", 0) // 1000),
                                "platform": "apple",
                                "type": "track",
                                "url": url,
                                "thumbnail": item.get("artworkUrl100", "").replace("100x100", "600x600"),
                                "has_lyrics": False,
                                "quality": "AAC 256kbps",
                                "bitrate": "256kbps"
                            }

        return None
    except Exception as e:
        LOGGER.warning(f"Failed to fetch Apple Music metadata: {e}")
        return None


async def _fetch_spotify_url_metadata(url: str) -> dict | None:
    """Fetch metadata from Spotify URL using deezspot"""
    try:
        # Import deezspot modules
        import sys
        import os
        deezspot_path = os.path.join(os.getcwd(), 'deezspot')
        if deezspot_path not in sys.path:
            sys.path.append(deezspot_path)
        from deezspot.spotloader.__spo_api__ import tracking
        from deezspot.easy_spoty import Spo

        # Extract ID from URL
        import re
        track_match = re.search(r'/track/([a-zA-Z0-9]+)', url)
        album_match = re.search(r'/album/([a-zA-Z0-9]+)', url)
        playlist_match = re.search(r'/playlist/([a-zA-Z0-9]+)', url)

        if track_match:
            track_id = track_match.group(1)
            track_data = tracking(track_id)
            if track_data:
                return {
                    "id": f"spotify_track_{track_id}",
                    "title": track_data.get("music", "Unknown Title"),
                    "artist": track_data.get("artist", "Unknown Artist"),
                    "album": track_data.get("album", "Unknown Album"),
                    "platform": "spotify",
                    "type": "track",
                    "url": url,
                    "thumbnail": track_data.get("image", ""),
                    "has_lyrics": False,
                    "quality": "OGG Vorbis 320kbps",
                    "bitrate": "320kbps"
                }
        elif album_match:
            album_id = album_match.group(1)
            album_data = Spo.get_album(album_id)
            if album_data:
                return {
                    "id": f"spotify_album_{album_id}",
                    "title": album_data.get("name", "Unknown Album"),
                    "artist": album_data.get("artists", [{}])[0].get("name", "Unknown Artist"),
                    "platform": "spotify",
                    "type": "album",
                    "url": url,
                    "thumbnail": album_data.get("images", [{}])[0].get("url", ""),
                    "track_count": album_data.get("total_tracks", 0),
                    "release_date": album_data.get("release_date", ""),
                    "quality": "OGG Vorbis 320kbps"
                }
        elif playlist_match:
            playlist_id = playlist_match.group(1)
            playlist_data = Spo.get_playlist(playlist_id)
            if playlist_data:
                return {
                    "id": f"spotify_playlist_{playlist_id}",
                    "title": playlist_data.get("name", "Unknown Playlist"),
                    "artist": playlist_data.get("owner", {}).get("display_name", "Spotify"),
                    "platform": "spotify",
                    "type": "playlist",
                    "url": url,
                    "thumbnail": playlist_data.get("images", [{}])[0].get("url", ""),
                    "track_count": playlist_data.get("tracks", {}).get("total", 0),
                    "description": playlist_data.get("description", ""),
                    "quality": "OGG Vorbis 320kbps"
                }

        return None
    except Exception as e:
        LOGGER.warning(f"Failed to fetch Spotify metadata: {e}")
        return None


async def _fetch_deezer_url_metadata(url: str) -> dict | None:
    """Fetch metadata from Deezer URL using deezspot"""
    try:
        # Import deezspot modules
        import sys
        import os
        deezspot_path = os.path.join(os.getcwd(), 'deezspot')
        if deezspot_path not in sys.path:
            sys.path.append(deezspot_path)
        from deezspot.deezloader.dee_api import API

        # Extract ID from URL
        import re
        track_match = re.search(r'/track/(\d+)', url)
        album_match = re.search(r'/album/(\d+)', url)
        playlist_match = re.search(r'/playlist/(\d+)', url)

        if track_match:
            track_id = track_match.group(1)
            track_data = API.get_track(track_id)
            if track_data:
                return {
                    "id": f"deezer_track_{track_id}",
                    "title": track_data.get("title", "Unknown Title"),
                    "artist": track_data.get("artist", {}).get("name", "Unknown Artist"),
                    "album": track_data.get("album", {}).get("title", "Unknown Album"),
                    "duration": track_data.get("duration", 0),
                    "platform": "deezer",
                    "type": "track",
                    "url": url,
                    "thumbnail": track_data.get("album", {}).get("cover_xl", ""),
                    "has_lyrics": track_data.get("lyrics", {}).get("id") is not None,
                    "quality": "FLAC/MP3 320kbps",
                    "bitrate": "1411kbps/320kbps"
                }
        elif album_match:
            album_id = album_match.group(1)
            album_data = API.get_album(album_id)
            if album_data:
                return {
                    "id": f"deezer_album_{album_id}",
                    "title": album_data.get("title", "Unknown Album"),
                    "artist": album_data.get("artist", {}).get("name", "Unknown Artist"),
                    "platform": "deezer",
                    "type": "album",
                    "url": url,
                    "thumbnail": album_data.get("cover_xl", ""),
                    "track_count": album_data.get("nb_tracks", 0),
                    "release_date": album_data.get("release_date", ""),
                    "quality": "FLAC/MP3 320kbps"
                }
        elif playlist_match:
            playlist_id = playlist_match.group(1)
            playlist_data = API.get_playlist(playlist_id)
            if playlist_data:
                return {
                    "id": f"deezer_playlist_{playlist_id}",
                    "title": playlist_data.get("title", "Unknown Playlist"),
                    "artist": playlist_data.get("creator", {}).get("name", "Deezer"),
                    "platform": "deezer",
                    "type": "playlist",
                    "url": url,
                    "thumbnail": playlist_data.get("picture_xl", ""),
                    "track_count": playlist_data.get("nb_tracks", 0),
                    "description": playlist_data.get("description", ""),
                    "quality": "FLAC/MP3 320kbps"
                }

        return None
    except Exception as e:
        LOGGER.warning(f"Failed to fetch Deezer metadata: {e}")
        return None


async def _create_generic_url_result(url: str, platform: str, query: str):
    """Create a generic download result when metadata fetch fails"""
    try:
        from pyrogram.types import (
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            InlineQueryResultArticle,
            InputTextMessageContent,
        )
        from pyrogram.enums import ParseMode

        # Parse flags from query
        flags = parse_musicdl_flags(query)
        quality = flags.get("quality", "27")
        format_type = flags.get("format", "flac")

        # Create download result
        title = f"🎵 Download from {platform.title()}"
        description = f"Quality: {quality} • Format: {format_type.upper()}"

        # Create message content
        message_text = f"🎵 <b>{platform.title()} Download</b>\n\n"
        message_text += f"<b>Quality:</b> {quality}\n"
        message_text += f"<b>Format:</b> {format_type.upper()}\n\n"
        message_text += f"<b>URL:</b> <code>{url}</code>\n\n"
        message_text += "Click download to start the process..."

        # Create compact callback data
        base_download_data = {
            "action": "download",
            "platform": platform,
            "quality": quality,
            "url": url,
            "flags": {k: v for k, v in flags.items() if k in ['lyrics', 'cover', 'zip']}
        }

        # Store callback data and get short IDs
        main_id = await _store_musicdl_callback_data({**base_download_data, "format": format_type})
        flac_id = await _store_musicdl_callback_data({**base_download_data, "format": "flac"})
        mp3_id = await _store_musicdl_callback_data({**base_download_data, "format": "mp3"})

        # Create keyboard
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"⬇️ Download {format_type.upper()}",
                callback_data=f"musicdl_dl_{main_id}"
            )],
            [
                InlineKeyboardButton(
                    "🎵 FLAC",
                    callback_data=f"musicdl_dl_{flac_id}"
                ),
                InlineKeyboardButton(
                    "🎶 MP3",
                    callback_data=f"musicdl_dl_{mp3_id}"
                ),
            ],
        ])

        return InlineQueryResultArticle(
            id=f"musicdl_url_{platform}_{hash(url)}",
            title=title,
            description=description,
            input_message_content=InputTextMessageContent(
                message_text=message_text, parse_mode=ParseMode.HTML
            ),
            reply_markup=keyboard,
            thumb_url=await _get_platform_thumbnail(platform),
        )
    except Exception as e:
        LOGGER.error(f"Failed to create generic URL result: {e}")
        return None


async def _get_platform_thumbnail(platform: str) -> str:
    """Get thumbnail URL for platform"""
    thumbnails = {
        "qobuz": "https://static.qobuz.com/images/qobuz-logo-square.png",
        "tidal": "https://tidal.com/favicon.ico",
        "apple": "https://music.apple.com/favicon.ico",
        "spotify": "https://open.spotify.com/favicon.ico",
        "deezer": "https://www.deezer.com/favicon.ico"
    }
    return thumbnails.get(platform, "")


async def _remove_duplicate_search_results(results: list[dict]) -> list[dict]:
    """Remove duplicate search results based on title, artist, and URL similarity"""
    if not results:
        return results

    seen_combinations = set()
    unique_results = []

    for result in results:
        title = result.get("title", "").lower().strip()
        artist = result.get("artist", "").lower().strip()
        url = result.get("url", "")
        platform = result.get("platform", "")

        # Create a unique identifier
        identifier = f"{title}|{artist}|{platform}"

        # Also check URL similarity for exact duplicates
        url_identifier = url.lower() if url else ""

        if identifier not in seen_combinations and url_identifier not in [r.get("url", "").lower() for r in unique_results]:
            seen_combinations.add(identifier)
            unique_results.append(result)

    return unique_results


async def _format_enhanced_inline_search_result(search_result: dict, original_query: str, user_id: int):
    """Format search result for enhanced inline display with detailed metadata"""
    try:
        from pyrogram.types import (
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            InlineQueryResultArticle,
            InputTextMessageContent,
        )
        from pyrogram.enums import ParseMode

        title = search_result.get("title", "Unknown Title")
        artist = search_result.get("artist", "")
        album = search_result.get("album", "")
        platform = search_result.get("platform", "unknown")
        content_type = search_result.get("type", "track")
        url = search_result.get("url", "")
        thumbnail = search_result.get("thumbnail", "")
        duration = search_result.get("duration", 0)
        quality = search_result.get("quality", "")
        bitrate = search_result.get("bitrate", "")
        sample_rate = search_result.get("sample_rate", "")
        bit_depth = search_result.get("bit_depth", "")
        has_lyrics = search_result.get("has_lyrics", False)
        release_date = search_result.get("release_date", "")

        # Platform emoji and priority mapping
        platform_info = {
            "qobuz": {"emoji": "🟦", "name": "Qobuz", "priority": 1},
            "tidal": {"emoji": "🌊", "name": "Tidal", "priority": 2},
            "apple": {"emoji": "🍎", "name": "Apple Music", "priority": 3},
            "spotify": {"emoji": "🎵", "name": "Spotify", "priority": 4},
            "deezer": {"emoji": "🎶", "name": "Deezer", "priority": 5}
        }

        # Content type emoji mapping
        type_emojis = {
            "track": "🎵",
            "album": "💿",
            "playlist": "📋",
            "artist": "👤"
        }

        platform_data = platform_info.get(platform, {"emoji": "🎵", "name": platform.title(), "priority": 99})
        platform_emoji = platform_data["emoji"]
        platform_name = platform_data["name"]
        type_emoji = type_emojis.get(content_type, "🎵")

        # Format quality information
        quality_info = []
        if quality:
            quality_info.append(quality)
        if bitrate:
            quality_info.append(f"{bitrate}")
        if sample_rate and bit_depth:
            quality_info.append(f"{bit_depth}bit/{sample_rate}")
        elif sample_rate:
            quality_info.append(f"{sample_rate}")

        quality_text = " • ".join(quality_info) if quality_info else "Standard"

        # Format display title with enhanced info
        display_title = f"{platform_emoji} {title}"
        if artist and artist != "Unknown Artist":
            # Truncate long artist names
            artist_display = artist[:30] + "..." if len(artist) > 30 else artist
            display_title += f" - {artist_display}"

        # Format description with comprehensive metadata based on content type
        content_type_names = {
            "track": "Track",
            "song": "Track",
            "album": "Album",
            "playlist": "Playlist",
            "artist": "Artist",
            "mix": "Mix"
        }
        type_name = content_type_names.get(content_type, "Track")

        description_parts = [f"{type_emoji} {type_name}"]

        # Add duration/count based on content type
        if content_type in ["track", "song"]:
            if duration > 0:
                minutes = duration // 60
                seconds = duration % 60
                description_parts.append(f"{minutes}:{seconds:02d}")
        elif content_type in ["album", "playlist", "mix"]:
            track_count = search_result.get("track_count", 0)
            if track_count > 0:
                if duration > 0:
                    total_minutes = duration // 60
                    description_parts.append(f"{track_count} tracks • {total_minutes}min")
                else:
                    description_parts.append(f"{track_count} tracks")
        elif content_type == "artist":
            album_count = search_result.get("track_count", 0)  # For artists, this represents album count
            if album_count > 0:
                description_parts.append(f"{album_count} albums")

        # Add quality for tracks and albums
        if content_type in ["track", "song", "album"] and quality_text != "Standard":
            description_parts.append(quality_text)

        # Add lyrics indicator
        if has_lyrics:
            description_parts.append("🎤")  # Lyrics indicator

        description = f"{platform_name} • " + " • ".join(description_parts)

        # Create enhanced message content
        message_text = f"🎵 <b>{title}</b>\n"
        if artist and artist != "Unknown Artist":
            message_text += f"👤 <b>Artist:</b> {artist}\n"
        if album:
            message_text += f"💿 <b>Album:</b> {album}\n"
        message_text += f"🎧 <b>Platform:</b> {platform_name}\n"
        message_text += f"📀 <b>Type:</b> {content_type.title()}\n"

        if duration > 0:
            minutes = duration // 60
            seconds = duration % 60
            message_text += f"⏱️ <b>Duration:</b> {minutes}:{seconds:02d}\n"

        if quality_text != "Standard":
            message_text += f"🔊 <b>Quality:</b> {quality_text}\n"

        if has_lyrics:
            message_text += f"📝 <b>Lyrics:</b> Available\n"

        if release_date:
            message_text += f"📅 <b>Released:</b> {release_date}\n"

        message_text += f"\n<b>URL:</b> <code>{url}</code>\n\n"
        message_text += "Choose download options below:"

        # Create callback data for different download options
        base_download_data = {
            "action": "inline_download",
            "platform": platform,
            "url": url,
            "title": title[:50],  # Truncate for storage
            "artist": artist[:30] if artist else "",
            "user_id": user_id,
            "inline_message_id": "placeholder"  # Will be updated when download starts
        }

        # Store callback data for different quality options
        flac_id = await _store_musicdl_callback_data({**base_download_data, "format": "flac", "quality": "best"})
        mp3_id = await _store_musicdl_callback_data({**base_download_data, "format": "mp3", "quality": "320"})

        # Platform-specific quality options
        if platform == "qobuz":
            hires_id = await _store_musicdl_callback_data({**base_download_data, "format": "flac", "quality": "27"})
        elif platform == "tidal":
            hires_id = await _store_musicdl_callback_data({**base_download_data, "format": "flac", "quality": "HI_RES_LOSSLESS"})
        else:
            hires_id = flac_id  # Fallback to FLAC

        # Create enhanced keyboard with quality options
        keyboard_rows = []

        # Primary download row
        if platform in ["qobuz", "tidal"]:
            keyboard_rows.append([
                InlineKeyboardButton(
                    f"⬇️ Hi-Res FLAC",
                    callback_data=f"musicdl_dl_{hires_id}"
                )
            ])

        # Standard quality options
        keyboard_rows.append([
            InlineKeyboardButton(
                "🎵 FLAC",
                callback_data=f"musicdl_dl_{flac_id}"
            ),
            InlineKeyboardButton(
                "🎶 MP3 320k",
                callback_data=f"musicdl_dl_{mp3_id}"
            )
        ])

        keyboard = InlineKeyboardMarkup(keyboard_rows)

        # Get platform-specific thumbnail
        thumb_url = thumbnail or await _get_platform_thumbnail(platform)

        return InlineQueryResultArticle(
            id=f"musicdl_{platform}_{hash(f'{title}_{artist}_{url}')}",
            title=display_title,
            description=description,
            input_message_content=InputTextMessageContent(
                message_text=message_text,
                parse_mode=ParseMode.HTML
            ),
            reply_markup=keyboard,
            thumb_url=thumb_url,
        )

    except Exception as e:
        LOGGER.error(f"Error formatting enhanced inline search result: {e}")
        return None


async def _format_inline_search_result(search_result: dict, original_query: str):
    """Format search result for inline display"""
    try:
        from pyrogram.types import (
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            InlineQueryResultArticle,
            InputTextMessageContent,
        )
        from pyrogram.enums import ParseMode

        # Extract result data
        title = search_result.get("title", "Unknown")
        artist = search_result.get("artist", "Unknown Artist")
        platform = search_result.get("platform", "unknown")
        content_type = search_result.get("type", "track")
        url = search_result.get("url", "")
        thumbnail = search_result.get("thumbnail", "")
        duration = search_result.get("duration", 0)
        quality = search_result.get("quality", "")
        bitrate = search_result.get("bitrate", "")
        has_lyrics = search_result.get("has_lyrics", False)

        # Platform emoji mapping
        platform_emojis = {
            "qobuz": "🟦",
            "tidal": "⚫",
            "apple": "🍎",
            "spotify": "🟢",
            "deezer": "🟣"
        }

        # Content type emoji mapping
        type_emojis = {
            "track": "🎵",
            "album": "💿",
            "playlist": "📋",
            "artist": "👤"
        }

        platform_emoji = platform_emojis.get(platform, "🎵")
        type_emoji = type_emojis.get(content_type, "🎵")

        # Format display title
        display_title = f"{platform_emoji} {title}"
        if artist and artist != "Unknown Artist":
            display_title += f" - {artist}"

        # Format description with metadata
        description_parts = [f"{type_emoji} {content_type.title()} on {platform.title()}"]

        if duration > 0:
            minutes = duration // 60
            seconds = duration % 60
            description_parts.append(f" • {minutes}:{seconds:02d}")

        if quality:
            description_parts.append(f" • {quality}")

        if has_lyrics:
            description_parts.append(" • L")  # Lyrics indicator

        description = "".join(description_parts)

        # Create message content
        message_text = f"🎵 <b>{title}</b>\n"
        if artist and artist != "Unknown Artist":
            message_text += f"👤 <b>Artist:</b> {artist}\n"
        message_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
        message_text += f"📀 <b>Type:</b> {content_type.title()}\n"

        if duration > 0:
            minutes = duration // 60
            seconds = duration % 60
            message_text += f"⏱️ <b>Duration:</b> {minutes}:{seconds:02d}\n"

        if quality:
            message_text += f"🎚️ <b>Quality:</b> {quality}\n"
        if bitrate:
            message_text += f"📊 <b>Bitrate:</b> {bitrate}\n"
        if has_lyrics:
            message_text += f"📝 <b>Lyrics:</b> Available\n"

        message_text += f"\n<b>URL:</b> <code>{url}</code>"

        # Create compact callback data for download
        base_data = {
            "action": "download",
            "platform": platform,
            "url": url,
            "title": title[:50],  # Truncate long titles
            "artist": artist[:30] if artist != "Unknown Artist" else "",  # Truncate long artist names
            "type": content_type
        }

        # Store callback data and get short IDs
        flac_id = await _store_musicdl_callback_data({**base_data, "format": "flac", "quality": "27"})
        mp3_id = await _store_musicdl_callback_data({**base_data, "format": "mp3", "quality": "27"})
        search_id = await _store_musicdl_callback_data({"action": "search_again", "query": original_query[:100]})

        # Create keyboard with download options using short callback data
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"⬇️ Download FLAC",
                callback_data=f"musicdl_dl_{flac_id}"
            )],
            [
                InlineKeyboardButton(
                    "🎵 FLAC",
                    callback_data=f"musicdl_dl_{flac_id}"
                ),
                InlineKeyboardButton(
                    "🎶 MP3",
                    callback_data=f"musicdl_dl_{mp3_id}"
                ),
            ],
            [InlineKeyboardButton(
                "🔍 Search Again",
                callback_data=f"musicdl_search_{search_id}"
            )]
        ])

        return InlineQueryResultArticle(
            id=search_result.get("id", f"musicdl_search_{hash(url)}"),
            title=display_title,
            description=description,
            input_message_content=InputTextMessageContent(
                message_text=message_text,
                parse_mode=ParseMode.HTML
            ),
            reply_markup=keyboard,
            thumb_url=thumbnail or await _get_platform_thumbnail(platform),
        )

    except Exception as e:
        LOGGER.error(f"Error formatting inline search result: {e}")
        return None


async def perform_inline_musicdl_search(query: str, platform_filter=None, quality_filter=None, user_id=None):
    """Perform MusicDL search and return dictionary results for unified search"""
    try:
        LOGGER.info(f"🔍 [MUSICDL] Starting inline search for query: '{query}' | Platform filter: {platform_filter} | User: {user_id}")

        # Perform the search
        # Convert platform_filter to platform_prefix format for unified_musicdl_search
        platform_prefix = None
        if platform_filter:
            platform_mapping = {
                "qobuz": "qb",
                "tidal": "td",
                "apple": "am",
                "spotify": "sp",
                "deezer": "dz"
            }
            platform_prefix = platform_mapping.get(platform_filter.lower())

        search_results = await unified_musicdl_search(query, platform_prefix, limit=10)

        LOGGER.info(f"🔍 [MUSICDL] Raw search returned {len(search_results)} results")

        if search_results:
            LOGGER.info(f"🔍 [MUSICDL] First result sample: {search_results[0] if search_results else 'None'}")

        # Return raw search results as dictionaries for unified search processing
        # The inline search router will handle the formatting
        formatted_results = []
        for i, search_result in enumerate(search_results):
            # Convert to dictionary format expected by unified search
            result_dict = {
                "title": search_result.get("title", "Unknown Title"),
                "artist": search_result.get("artist", ""),
                "album": search_result.get("album", ""),
                "url": search_result.get("url", ""),
                "platform": search_result.get("platform", "musicdl"),
                "type": search_result.get("type", "track"),
                "duration": search_result.get("duration", 0),
                "quality": search_result.get("quality", ""),
                "thumbnail": search_result.get("thumbnail", ""),
                "has_lyrics": search_result.get("has_lyrics", False),
                "source": "musicdl"  # Identify source for result processing
            }
            formatted_results.append(result_dict)
            LOGGER.info(f"🔍 [MUSICDL] Result {i+1}: {result_dict['title']} by {result_dict['artist']} | Platform: {result_dict['platform']} | Quality: {result_dict['quality']}")

        LOGGER.info(f"🔍 [MUSICDL] Successfully formatted {len(formatted_results)} results for unified search")
        return formatted_results

    except Exception as e:
        LOGGER.error(f"❌ [MUSICDL] Error in perform_inline_musicdl_search: {e}", exc_info=True)
        return []


# Inline search integration
async def musicdl_inline_search(client, inline_query, platform_filter=None):
    """Enhanced inline search for music downloads supporting both URLs and search queries

    Args:
        client: Pyrogram client
        inline_query: Inline query object
        platform_filter: Specific platform to search (qobuz, tidal, apple, spotify, deezer)
    """
    try:
        from pyrogram.enums import ParseMode
        from pyrogram.types import (
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            InlineQueryResultArticle,
            InputTextMessageContent,
        )

        query = inline_query.query.strip()
        results = []

        if not query:
            # Empty query - let inline_search_router handle help
            return

        # Check if query contains a music URL
        import re
        url_pattern = r"https?://[^\s]+"
        urls = re.findall(url_pattern, query)

        if urls:
            # Handle URL downloads - fetch actual metadata instead of generic results
            for url in urls:
                platform = detect_platform(url)
                if platform:
                    try:
                        # Fetch actual metadata from the URL
                        metadata = await _fetch_url_metadata(url, platform)
                        if metadata:
                            # Create enhanced result with actual track/album info
                            result = await _format_enhanced_inline_search_result(
                                metadata, query, inline_query.from_user.id
                            )
                            if result:
                                results.append(result)
                        else:
                            # Fallback to generic download result if metadata fetch fails
                            result = await _create_generic_url_result(url, platform, query)
                            if result:
                                results.append(result)
                    except Exception as e:
                        LOGGER.warning(f"Failed to fetch metadata for {url}: {e}")
                        # Fallback to generic download result
                        result = await _create_generic_url_result(url, platform, query)
                        if result:
                            results.append(result)
        else:
            # Handle search queries with enhanced functionality
            LOGGER.info(f"MusicDL inline search: '{query}' (platform: {platform_filter or 'all'})")

            # Perform search with platform filtering
            # Convert platform_filter to platform_prefix format
            platform_prefix = None
            if platform_filter == "qobuz":
                platform_prefix = "qb"
            elif platform_filter == "tidal":
                platform_prefix = "td"
            elif platform_filter == "apple":
                platform_prefix = "am"
            elif platform_filter == "spotify":
                platform_prefix = "sp"
            elif platform_filter == "deezer":
                platform_prefix = "dz"

            search_results = await unified_musicdl_search(query, platform_prefix, limit=15)

            if search_results:
                # Remove duplicates and sort by platform priority
                unique_results = await _remove_duplicate_search_results(search_results)

                # Format results for inline display
                for search_result in unique_results[:10]:  # Limit to top 10 results
                    result = await _format_enhanced_inline_search_result(search_result, query, inline_query.from_user.id)
                    if result:
                        results.append(result)

            # Add "Search Again" button if we have results
            if results:
                search_again_data = await _store_musicdl_callback_data({
                    "action": "search_again",
                    "query": query[:100],  # Truncate long queries
                    "platform_filter": platform_filter,
                    "user_id": inline_query.from_user.id
                })

                search_again_result = InlineQueryResultArticle(
                    id="musicdl_search_again",
                    title="🔍 Search Again",
                    description="Perform a new search with different query",
                    input_message_content=InputTextMessageContent(
                        message_text=f"🔍 <b>Search Again</b>\n\nClick the button below to search for different music.",
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "🔍 New Search",
                            callback_data=f"musicdl_search_{search_again_data}"
                        )
                    ]]),
                )
                results.append(search_again_result)

        await inline_query.answer(results, cache_time=30)

    except Exception as e:
        LOGGER.error(f"Error in musicdl inline search: {e}")
        # Provide error result
        error_result = InlineQueryResultArticle(
            id="musicdl_error",
            title="❌ MusicDL Search Error",
            description="An error occurred during search",
            input_message_content=InputTextMessageContent(
                message_text=f"❌ <b>MusicDL Search Error</b>\n\nAn error occurred: {e!s}",
                parse_mode=ParseMode.HTML,
            ),
        )
        await inline_query.answer([error_result], cache_time=0)


async def _start_inline_musicdl_download(url: str, platform: str, config: DownloadConfig, listener: InlineMusicDownloadListener):
    """Start inline MusicDL download with real-time progress updates"""
    try:
        import asyncio
        import os
        from pathlib import Path

        # Create download directory
        os.makedirs(listener.download_dir, exist_ok=True)

        # Update status to downloading
        await listener.update_inline_progress(
            f"🎵 <b>Downloading...</b>\n\n"
            f"🎧 <b>Platform:</b> {platform.title()}\n"
            f"🎛️ <b>Format:</b> {config.format.upper()}\n"
            f"🔊 <b>Quality:</b> {config.quality}\n\n"
            f"⏳ <b>Status:</b> Initializing download...\n"
            f"📊 <b>Progress:</b> 5%"
        )

        # Create appropriate downloader based on platform
        if platform == "tidal":
            downloader = TidalDownloader(listener)
        elif platform == "qobuz":
            downloader = QobuzDownloader(listener)
        elif platform == "apple":
            downloader = AppleDownloader(listener)
        elif platform == "spotify":
            downloader = SpotifyDownloader(listener)
        elif platform == "deezer":
            downloader = DeezerDownloader(listener)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        # Update status to processing
        await listener.update_inline_progress(
            f"🎵 <b>Downloading...</b>\n\n"
            f"🎧 <b>Platform:</b> {platform.title()}\n"
            f"🎛️ <b>Format:</b> {config.format.upper()}\n"
            f"🔊 <b>Quality:</b> {config.quality}\n\n"
            f"⏳ <b>Status:</b> Processing {platform.title()} download...\n"
            f"📊 <b>Progress:</b> 25%"
        )

        # Start the download
        await downloader.download(url)

        # Update status to uploading
        await listener.update_inline_progress(
            f"🎵 <b>Upload Starting...</b>\n\n"
            f"🎧 <b>Platform:</b> {platform.title()}\n"
            f"🎛️ <b>Format:</b> {config.format.upper()}\n"
            f"🔊 <b>Quality:</b> {config.quality}\n\n"
            f"⏳ <b>Status:</b> Preparing upload to Telegram...\n"
            f"📊 <b>Progress:</b> 75%"
        )

        # The actual upload will be handled by the TaskListener's upload process
        # which will automatically start after download completion

    except Exception as e:
        LOGGER.error(f"Error in inline download: {e}")
        await listener.update_inline_progress(
            f"❌ <b>Download Failed</b>\n\n"
            f"🎧 <b>Platform:</b> {platform.title()}\n"
            f"🎛️ <b>Format:</b> {config.format.upper()}\n\n"
            f"<b>Error:</b> {str(e)}\n\n"
            f"Please try again or contact support."
        )


async def _handle_inline_download_menu(client, callback_query, callback_info: dict) -> None:
    """Handle inline download by showing quality/format selection menu first"""
    try:
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from pyrogram.enums import ParseMode

        url = callback_info.get("url", "")
        platform = callback_info.get("platform", "")

        if not url or not platform:
            await callback_query.answer("❌ Invalid download data", show_alert=True)
            return

        # Get platform-specific quality and format options
        quality_options, format_options = _get_platform_quality_format_options(platform)

        # Create menu text
        menu_text = f"🎵 <b>Quality & Format Selection</b>\n\n"
        menu_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
        menu_text += f"🔗 <b>URL:</b> <code>{url}</code>\n\n"
        menu_text += f"📊 <b>Available Qualities:</b> {len(quality_options)}\n"
        menu_text += f"📁 <b>Available Formats:</b> {len(format_options)}\n\n"
        menu_text += "⏱️ <b>Timeout:</b> 5 minutes (auto-download with best quality after timeout)\n\n"
        menu_text += "Please select your preferred quality and format:"

        # Create keyboard with quality options
        keyboard_rows = []

        # Add quality selection header
        keyboard_rows.append([InlineKeyboardButton("🔊 Quality Selection", callback_data="musicdl_header_quality")])

        # Add quality options (2 per row)
        quality_row = []
        for i, (quality_id, quality_info) in enumerate(quality_options.items()):
            quality_row.append(InlineKeyboardButton(
                f"{quality_info['emoji']} {quality_info['name']}",
                callback_data=f"musicdl_quality_{platform}_{quality_id}_{hash(url)}"
            ))
            if len(quality_row) == 2 or i == len(quality_options) - 1:
                keyboard_rows.append(quality_row)
                quality_row = []

        # Add format selection header
        keyboard_rows.append([InlineKeyboardButton("📁 Format Selection", callback_data="musicdl_header_format")])

        # Add format options (3 per row)
        format_row = []
        for i, (format_id, format_info) in enumerate(format_options.items()):
            format_row.append(InlineKeyboardButton(
                f"{format_info['emoji']} {format_info['name']}",
                callback_data=f"musicdl_format_{platform}_{format_id}_{hash(url)}"
            ))
            if len(format_row) == 3 or i == len(format_options) - 1:
                keyboard_rows.append(format_row)
                format_row = []

        # Add quick download options
        keyboard_rows.append([InlineKeyboardButton("⚡ Quick Download", callback_data="musicdl_header_quick")])
        keyboard_rows.append([
            InlineKeyboardButton(
                "🎵 Best FLAC",
                callback_data=f"musicdl_quick_{platform}_best_flac_{hash(url)}"
            ),
            InlineKeyboardButton(
                "🎶 Best MP3",
                callback_data=f"musicdl_quick_{platform}_best_mp3_{hash(url)}"
            )
        ])

        # Add cancel button
        keyboard_rows.append([InlineKeyboardButton("❌ Cancel", callback_data="musicdl_cancel")])

        keyboard = InlineKeyboardMarkup(keyboard_rows)

        # Store the callback info for later use
        user_id = callback_query.from_user.id
        await _store_musicdl_session_data(user_id, {
            "url": url,
            "query": "",
            "is_leech": callback_info.get("is_leech", True),
            "platform": platform,
            "selected_quality": None,
            "selected_format": None,
            "timestamp": time.time(),
            "original_callback_info": callback_info
        })

        # Update the inline message with the menu
        await callback_query.edit_message_text(
            menu_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

        # Schedule auto-download after 5 minutes
        asyncio.create_task(_auto_download_after_timeout(callback_query, user_id, 300))  # 5 minutes

    except Exception as e:
        LOGGER.error(f"Error showing inline download menu: {e}")
        await callback_query.answer("❌ Error showing selection menu", show_alert=True)


async def _auto_download_after_timeout(callback_query, user_id: int, timeout_seconds: int) -> None:
    """Auto-start download with best quality after timeout"""
    try:
        await asyncio.sleep(timeout_seconds)

        # Check if user still has an active session
        session_data = await _get_musicdl_session_data(user_id)
        if not session_data:
            return  # Session expired or completed

        # Check if user hasn't made selections yet
        if not session_data.get('selected_quality') or not session_data.get('selected_format'):
            # Auto-select best quality and FLAC format
            platform = session_data['platform']
            quality_options, _ = _get_platform_quality_format_options(platform)
            best_quality = list(quality_options.keys())[-1]  # Last option is usually best

            session_data['selected_quality'] = best_quality
            session_data['selected_format'] = 'flac'

            # Update message to show auto-selection
            timeout_text = f"⏰ <b>Timeout Reached - Auto Download</b>\n\n"
            timeout_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
            timeout_text += f"🔊 <b>Quality:</b> {best_quality} (Auto-selected)\n"
            timeout_text += f"📁 <b>Format:</b> FLAC (Auto-selected)\n\n"
            timeout_text += f"🔗 <b>URL:</b> <code>{session_data['url']}</code>\n\n"
            timeout_text += "⏳ <b>Status:</b> Starting download with best available quality..."

            await callback_query.edit_message_text(
                timeout_text,
                parse_mode=ParseMode.HTML
            )

            # Start the download
            await _finalize_download_selection(callback_query, session_data)

    except Exception as e:
        LOGGER.error(f"Error in auto-download timeout: {e}")


async def _handle_inline_download_callback(client, callback_query, callback_info):
    """Handle inline download callbacks with real-time progress updates"""
    try:
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from pyrogram.enums import ParseMode

        # Extract download parameters
        platform = callback_info.get("platform", "")
        url = callback_info.get("url", "")
        format_type = callback_info.get("format", "flac")
        quality = callback_info.get("quality", "best")
        title = callback_info.get("title", "Unknown")
        artist = callback_info.get("artist", "")
        user_id = callback_info.get("user_id")

        if not url or not platform:
            await callback_query.answer("❌ Invalid download data", show_alert=True)
            return

        # Check if user is authorized
        if not user_id or user_id != callback_query.from_user.id:
            await callback_query.answer("❌ Unauthorized", show_alert=True)
            return

        # Update inline message to show download starting
        download_text = f"🎵 <b>{title}</b>\n"
        if artist:
            download_text += f"👤 <b>Artist:</b> {artist}\n"
        download_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
        download_text += f"🎛️ <b>Format:</b> {format_type.upper()}\n"
        download_text += f"🔊 <b>Quality:</b> {quality}\n\n"
        download_text += "⏳ <b>Status:</b> Starting download...\n"
        download_text += "📊 <b>Progress:</b> 0%"

        # Create cancel button
        cancel_data = await _store_musicdl_callback_data({
            "action": "cancel_inline_download",
            "user_id": user_id
        })

        cancel_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"musicdl_dl_{cancel_data}")]
        ])

        # Update the inline message
        await callback_query.edit_message_text(
            download_text,
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard
        )

        await callback_query.answer("🎵 Download started!")

        # Create download configuration
        flags = {
            "format": format_type,
            "quality": quality,
            "lyrics": True,  # Always try to get lyrics
            "cover": True,   # Always try to get cover art
        }

        config = DownloadConfig(
            quality=quality,
            format=format_type,
            lyrics_enabled=True,
            cover_enabled=True,
            flags=flags
        )

        # Create a special inline listener for progress updates
        inline_listener = InlineMusicDownloadListener(
            callback_query.message,
            config,
            platform,
            f"downloads/musicdl_{user_id}_{int(time.time())}",
            is_leech=True,  # Always leech for inline downloads
            inline_message=callback_query.message,
            inline_query_id=callback_query.inline_message_id
        )

        # Start the download process
        await _start_inline_musicdl_download(url, platform, config, inline_listener)

    except Exception as e:
        LOGGER.error(f"Error in inline download callback: {e}")
        with contextlib.suppress(Exception):
            await callback_query.edit_message_text(
                f"❌ <b>Download Error</b>\n\n{str(e)}",
                parse_mode=ParseMode.HTML
            )


# Enhanced callback handler for music download buttons
async def handle_musicdl_callback(client, callback_query):
    """Handle music download callback buttons with encrypted data support"""
    try:
        from pyrogram.enums import ParseMode
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        data = callback_query.data

        # Handle new encrypted callback format
        if data.startswith("musicdl_dl_"):
            # Download action with encrypted data
            encrypted_data = data[11:]  # Remove "musicdl_dl_" prefix
            callback_info = await _decrypt_musicdl_callback_data(encrypted_data)

            if not callback_info:
                await callback_query.answer("❌ Invalid callback data", show_alert=True)
                return

            # Check if this is an inline download - show quality/format menu first
            if callback_info.get("action") == "inline_download":
                await _handle_inline_download_menu(client, callback_query, callback_info)
                return

            # Extract download parameters for regular downloads
            platform = callback_info.get("platform", "")
            quality = callback_info.get("quality", "27")
            format_type = callback_info.get("format", "flac")
            url = callback_info.get("url", "")
            title = callback_info.get("title", "Unknown")
            artist = callback_info.get("artist", "Unknown Artist")

            if not url:
                await callback_query.answer("❌ Missing URL in callback data", show_alert=True)
                return

            # Create query string for parsing
            query = f"-q {quality} -fm {format_type}"

            # Start download
            await callback_query.answer("🎵 Starting download...", show_alert=False)

            # Update message to show download starting
            progress_text = "🎵 <b>Download Starting...</b>\n\n"
            progress_text += f"📀 <b>Title:</b> {title}\n"
            if artist != "Unknown Artist":
                progress_text += f"👤 <b>Artist:</b> {artist}\n"
            progress_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
            progress_text += f"🎚️ <b>Quality:</b> {quality}\n"
            progress_text += f"📁 <b>Format:</b> {format_type.upper()}\n"
            progress_text += "📊 <b>Status:</b> Initializing...\n\n"
            progress_text += f"<b>URL:</b> <code>{url}</code>"

            # Create progress keyboard with search again option
            search_query = f"{title} {artist}".strip()[:100]  # Truncate long queries
            search_again_id = await _store_musicdl_callback_data({'action': 'search_again', 'query': search_query})

            progress_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔍 Search Again",
                    callback_data=f"musicdl_search_{search_again_id}"
                )
            ]])

            await callback_query.edit_message_text(
                progress_text,
                parse_mode=ParseMode.HTML,
                reply_markup=progress_keyboard
            )

            # Start the actual download with inline message support
            listener = await start_music_download(callback_query.message, url, query, inline_message=callback_query.message)

            if listener:
                # Update with download started status
                success_text = "✅ <b>Download Started Successfully</b>\n\n"
                success_text += f"📀 <b>Title:</b> {title}\n"
                if artist != "Unknown Artist":
                    success_text += f"👤 <b>Artist:</b> {artist}\n"
                success_text += f"🎧 <b>Platform:</b> {platform.title()}\n"
                success_text += f"🎚️ <b>Quality:</b> {quality}\n"
                success_text += f"📁 <b>Format:</b> {format_type.upper()}\n"
                success_text += f"📊 <b>Status:</b> {listener.status}\n\n"
                success_text += "💡 <b>Note:</b> Download progress will be shown in real-time.\n\n"
                success_text += f"<b>URL:</b> <code>{url}</code>"

                await callback_query.edit_message_text(
                    success_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=progress_keyboard
                )
            else:
                # Download failed
                error_text = "❌ <b>Download Failed</b>\n\n"
                error_text += f"📀 <b>Title:</b> {title}\n"
                if artist != "Unknown Artist":
                    error_text += f"👤 <b>Artist:</b> {artist}\n"
                error_text += f"🎧 <b>Platform:</b> {platform.title()}\n\n"
                error_text += "💡 Please try again or check if the URL is valid.\n\n"
                error_text += f"<b>URL:</b> <code>{url}</code>"

                await callback_query.edit_message_text(
                    error_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=progress_keyboard
                )

        elif data.startswith("musicdl_search_"):
            # Search again action
            encrypted_data = data[15:]  # Remove "musicdl_search_" prefix
            callback_info = await _decrypt_musicdl_callback_data(encrypted_data)

            if not callback_info:
                await callback_query.answer("❌ Invalid search data", show_alert=True)
                return

            query = callback_info.get("query", "")

            await callback_query.answer(f"🔍 Search for: {query}", show_alert=True)

            # Update message to show search instruction
            search_text = f"🔍 <b>Search Again</b>\n\n"
            search_text += f"To search for music, use the inline mode:\n\n"

            # Get bot username safely
            try:
                bot_username = client.me.username if hasattr(client, 'me') and client.me else "bot_username"
            except Exception:
                bot_username = "bot_username"

            search_text += f"<code>@{bot_username} {query}</code>\n\n"
            search_text += "💡 You can also try different search terms or platform prefixes:\n"
            search_text += f"• <code>@{bot_username} qb:{query}</code> (Qobuz only)\n"
            search_text += f"• <code>@{bot_username} td:{query}</code> (Tidal only)\n"
            search_text += f"• <code>@{bot_username} sp:{query}</code> (Spotify only)"

            await callback_query.edit_message_text(
                search_text,
                parse_mode=ParseMode.HTML
            )

        elif data.startswith("musicdl_quality_"):
            # Handle quality selection
            await _handle_quality_selection(callback_query, data)

        elif data.startswith("musicdl_format_"):
            # Handle format selection
            await _handle_format_selection(callback_query, data)

        elif data.startswith("musicdl_quick_"):
            # Handle quick download selection
            await _handle_quick_download(callback_query, data)

        elif data == "musicdl_cancel":
            # Handle cancel selection
            await callback_query.edit_message_text(
                "❌ <b>Selection Cancelled</b>\n\nMusic download cancelled by user.",
                parse_mode=ParseMode.HTML
            )

        elif data.startswith("musicdl_header_"):
            # Handle header buttons (do nothing, just acknowledge)
            await callback_query.answer("Please select an option below", show_alert=False)

        elif data.startswith("musicdl:"):
            # Legacy callback format support
            parts = data.split(":", 4)
            if len(parts) != 5:
                await callback_query.answer("❌ Invalid callback data", show_alert=True)
                return

            _, platform, quality, format_type, url = parts
            query = f"-q {quality} -fm {format_type}"

            await callback_query.answer("🎵 Starting download...", show_alert=False)
            listener = await start_music_download(callback_query.message, url, query)

            if listener:
                await callback_query.edit_message_text(
                    f"🎵 <b>Download Started</b>\n\n"
                    f"<b>Platform:</b> {platform.title()}\n"
                    f"<b>Quality:</b> {quality}\n"
                    f"<b>Format:</b> {format_type.upper()}\n"
                    f"<b>Status:</b> {listener.status}\n\n"
                    f"<b>URL:</b> <code>{url}</code>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await callback_query.edit_message_text(
                    "❌ Failed to start download. Please try again.",
                    parse_mode=ParseMode.HTML,
                )

    except Exception as e:
        LOGGER.error(f"Error handling music callback: {e}")
        await callback_query.answer("❌ Error processing request", show_alert=True)


# Command handler for /musicmirror
async def musicmirror_command(client, message):
    """Handle /musicmirror command - Mirror music to cloud services"""
    try:
        # Import required functions
        from bot.helper.ext_utils.bot_utils import COMMAND_USAGE
        from bot.helper.telegram_helper.message_utils import send_message

        # Check if musicdl is enabled
        if not Config.MUSICDL_ENABLED:
            await send_message(
                message, "❌ Music download functionality is disabled."
            )
            return

        # Parse command arguments
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []

        if not args:
            # Show help using the standard help system
            if "musicdl" in COMMAND_USAGE:
                await send_message(message, COMMAND_USAGE["musicdl"][0], COMMAND_USAGE["musicdl"][1])
            else:
                # Fallback to custom help if standard help not available
                await show_musicdl_help(message, page=0)
            return

        # Extract URL and options
        url = args[0]
        query = " ".join(args)

        # Validate URL
        platform = detect_platform(url)
        if not platform:
            await send_message(
                message,
                "❌ Unsupported URL. Please provide a Tidal, Qobuz, Apple Music, Spotify, or Deezer URL.",
            )
            return

        # Send initial status message
        status_msg = await send_message(
            message,
            f"🎵 <b>Mirror Started</b>\n\n"
            f"<b>Platform:</b> {platform.title()}\n"
            f"<b>Status:</b> Initializing...\n"
            f"<b>Mode:</b> Mirror to Cloud\n\n"
            f"<b>URL:</b> <code>{url}</code>",
        )

        # Show quality/format selection menu instead of direct download
        success = await show_quality_format_menu(message, url, query, is_leech=False)
        if not success:
            await send_message(message, "❌ Failed to show quality/format selection menu.")
            return

        # Update status message to show menu was sent
        if status_msg:
            await status_msg.edit_text(
                f"🎵 <b>Quality & Format Selection</b>\n\n"
                f"<b>Platform:</b> {platform.title()}\n"
                f"<b>Mode:</b> Mirror to Cloud\n\n"
                f"<b>URL:</b> <code>{url}</code>\n\n"
                f"Please select your preferred quality and format from the menu below."
            )
        return  # Don't proceed with direct download

    except Exception as e:
        LOGGER.error(f"Error in musicmirror command: {e}")
        await send_message(message, f"❌ Error: {e!s}")


# Command handler for /musicleech
async def musicleech_command(client, message):
    """Handle /musicleech command - Leech music to Telegram"""
    try:
        # Import required functions
        from bot.helper.ext_utils.bot_utils import COMMAND_USAGE
        from bot.helper.telegram_helper.message_utils import send_message

        # Check if musicdl is enabled
        if not Config.MUSICDL_ENABLED:
            await send_message(
                message, "❌ Music download functionality is disabled."
            )
            return

        # Parse command arguments
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []

        if not args:
            # Show help using the standard help system
            if "musicdl" in COMMAND_USAGE:
                await send_message(message, COMMAND_USAGE["musicdl"][0], COMMAND_USAGE["musicdl"][1])
            else:
                # Fallback to custom help if standard help not available
                await show_musicdl_help(message, page=0)
            return

        # Extract URL and options
        url = args[0]
        query = " ".join(args)

        # Validate URL
        platform = detect_platform(url)
        if not platform:
            await send_message(
                message,
                "❌ Unsupported URL. Please provide a Tidal, Qobuz, Apple Music, Spotify, or Deezer URL.",
            )
            return

        # Send initial status message
        status_msg = await send_message(
            message,
            f"🎵 <b>Leech Started</b>\n\n"
            f"<b>Platform:</b> {platform.title()}\n"
            f"<b>Status:</b> Initializing...\n"
            f"<b>Mode:</b> Leech to Telegram\n\n"
            f"<b>URL:</b> <code>{url}</code>",
        )

        # Show quality/format selection menu instead of direct download
        success = await show_quality_format_menu(message, url, query, is_leech=True)
        if not success:
            await send_message(message, "❌ Failed to show quality/format selection menu.")
            return

        # Update status message to show menu was sent
        if status_msg:
            await status_msg.edit_text(
                f"🎵 <b>Quality & Format Selection</b>\n\n"
                f"<b>Platform:</b> {platform.title()}\n"
                f"<b>Mode:</b> Leech to Telegram\n\n"
                f"<b>URL:</b> <code>{url}</code>\n\n"
                f"Please select your preferred quality and format from the menu below."
            )
        return  # Don't proceed with direct download

    except Exception as e:
        LOGGER.error(f"Error in musicleech command: {e}")
        await send_message(message, f"❌ Error: {e!s}")


# Quality menu callback (for compatibility)
async def quality_menu_callback(client, callback_query):
    """Handle quality menu callbacks (legacy compatibility)"""
    try:
        # For CLI-based approach, we don't need complex quality menus
        # Just redirect to the main callback handler
        await handle_musicdl_callback(client, callback_query)
    except Exception as e:
        LOGGER.error(f"Error in quality menu callback: {e}")
        await callback_query.answer("❌ Error processing request", show_alert=True)


# Export for integration
__all__ = [
    "DownloadConfig",
    "MusicDownloadListener",
    "detect_platform",
    "get_musicdl_help_text",
    "handle_musicdl_callback",
    "musicdl_help_callback",
    "musicdl_inline_search",
    "musicleech_command",
    "musicmirror_command",
    "parse_musicdl_flags",
    "perform_inline_musicdl_search",
    "quality_menu_callback",
    "setup_qobuz_module_auth",
    "setup_tidal_auth",
    "show_musicdl_help",
    "show_quality_format_menu",
    "start_music_download",
    "verify_authentication",
]