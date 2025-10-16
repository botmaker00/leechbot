import contextlib
import inspect
import json
import os
from asyncio import (
    create_subprocess_exec,
    create_subprocess_shell,
    create_task,
    gather,
    sleep,
)
from datetime import datetime
from functools import partial
from io import BytesIO
from os import getcwd, path
from time import time

import aiofiles
import toml
from aiofiles import open as aiopen
from aioshutil import rmtree
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler

# Optional imports
try:
    from PIL import Image

    from bot.helper.ext_utils.media_utils import limit_memory_for_pil

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    limit_memory_for_pil = None

# Import LOGGER and other commonly used modules
try:
    from bot import LOGGER
except ImportError:
    LOGGER = None

# Import auto_restart function
try:
    from bot.helper.ext_utils.auto_restart import schedule_auto_restart
except ImportError:
    schedule_auto_restart = None

# Import streamrip and zotify config helpers
try:
    from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
        streamrip_config,
    )
except ImportError:
    streamrip_config = None

try:
    from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import (
        zotify_config,
    )
except ImportError:
    zotify_config = None

# Import config_utils functions
try:
    from bot.helper.ext_utils.config_utils import (
        reset_bulk_configs,
        reset_ddl_configs,
        reset_gallery_dl_configs,
        reset_gdrive_upload_configs,
        reset_jd_configs,
        reset_leech_configs,
        reset_mega_configs,
        reset_mirror_configs,
        reset_multi_link_configs,
        reset_nzb_configs,
        reset_rclone_configs,
        reset_same_dir_configs,
        reset_streamrip_configs,
        reset_tool_configs,
        reset_torrent_configs,
        reset_youtube_configs,
        reset_ytdlp_configs,
        reset_zotify_configs,
    )
except ImportError:
    # Set all to None if import fails
    reset_tool_configs = None
    reset_rclone_configs = None
    reset_mirror_configs = None
    reset_leech_configs = None
    reset_ytdlp_configs = None
    reset_torrent_configs = None
    reset_nzb_configs = None
    reset_jd_configs = None
    reset_bulk_configs = None
    reset_multi_link_configs = None
    reset_same_dir_configs = None
    reset_streamrip_configs = None
    reset_gallery_dl_configs = None
    reset_zotify_configs = None
    reset_gdrive_upload_configs = None
    reset_youtube_configs = None
    reset_ddl_configs = None
    reset_mega_configs = None

from bot import (
    DOWNLOAD_DIR,
    aria2_options,
    auth_chats,
    drives_ids,
    drives_names,
    excluded_extensions,
    index_urls,
    intervals,
    jd_listener_lock,
    nzb_options,
    qbit_options,
    sabnzbd_client,
    sudo_users,
    task_dict,
    user_data,
)
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.core.jdownloader_booter import jdownloader
from bot.core.startup import (
    update_aria2_options,
    update_nzb_options,
    update_qb_options,
    update_variables,
)
from bot.core.torrent_manager import TorrentManager
from bot.helper.ext_utils.aiofiles_compat import aiopath, makedirs, remove, rename
from bot.helper.ext_utils.bot_utils import (
    SetInterval,
    is_media_tool_enabled,
    new_task,
)
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.ext_utils.task_manager import start_from_queued
from bot.helper.mirror_leech_utils.rclone_utils.serve import rclone_serve_booter
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_file,
    send_message,
    update_status_message,
)

from .rss import add_job

# Import ai_manager for AI-related functionality
ai_manager = None
with contextlib.suppress(ImportError):
    from bot.modules.ai import ai_manager

start = 0
state = "view"
merge_page = 0  # Track current page for merge menu
merge_config_page = 0  # Track current page for merge config menu
watermark_text_page = 0  # Track current page for watermark text menu
handler_dict = {}


def update_user_ldata(user_id, key, value):
    """Update user data with the provided key and value."""
    if user_id in user_data:
        user_data[user_id][key] = value
    else:
        user_data[user_id] = {key: value}


DEFAULT_VALUES = {
    # Set default leech split size to max split size based on owner session premium status
    "LEECH_SPLIT_SIZE": (
        TgClient.MAX_SPLIT_SIZE
        if hasattr(Config, "USER_SESSION_STRING") and Config.USER_SESSION_STRING
        else 2097152000
    ),
    "RSS_DELAY": 600,
    "UPSTREAM_BRANCH": "main",
    "DEFAULT_UPLOAD": "rc",
    "PIL_MEMORY_LIMIT": 2048,
    "AUTO_RESTART_ENABLED": False,
    "AUTO_RESTART_INTERVAL": 24,
    "EQUAL_SPLITS": False,
    "AI_ENABLED": True,
    "IMDB_ENABLED": True,
    "TRUECALLER_ENABLED": True,
    "MEDIA_TOOLS_ENABLED": True,
    "BULK_ENABLED": True,
    "MULTI_LINK_ENABLED": True,
    "SAME_DIR_ENABLED": True,
    "MIRROR_ENABLED": True,
    "LEECH_ENABLED": True,
    "TORRENT_ENABLED": True,
    "TORRENT_SEARCH_ENABLED": True,
    "YTDLP_ENABLED": True,
    "NZB_ENABLED": True,
    "NZB_SEARCH_ENABLED": True,
    "JD_ENABLED": True,
    "VT_ENABLED": False,
    "VT_API_TIMEOUT": 500,
    "VT_MAX_FILE_SIZE": 32 * 1024 * 1024,  # 32MB in bytes,
    "CORRECT_CMD_SUFFIX": "",
    "WRONG_CMD_WARNINGS_ENABLED": True,
    "HYPERDL_ENABLED": True,
    "MEDIA_SEARCH_ENABLED": True,
    "RCLONE_ENABLED": True,
    "ARCHIVE_FLAGS_ENABLED": True,
    "AD_BROADCASTER_ENABLED": False,
    "STREAMRIP_ENABLED": True,
    "MEGA_SEARCH_ENABLED": True,
    # API Settings
    "DEBRID_LINK_API": "",
    # Streamrip Settings
    "STREAMRIP_CONCURRENT_DOWNLOADS": 4,
    "STREAMRIP_MAX_SEARCH_RESULTS": 20,
    "STREAMRIP_ENABLE_DATABASE": False,
    "STREAMRIP_AUTO_CONVERT": False,
    "STREAMRIP_DEFAULT_QUALITY": 3,
    "STREAMRIP_FALLBACK_QUALITY": 2,
    "STREAMRIP_DEFAULT_CODEC": "flac",
    "STREAMRIP_QUALITY_FALLBACK_ENABLED": False,
    "STREAMRIP_QOBUZ_ENABLED": False,
    "STREAMRIP_QOBUZ_QUALITY": 3,
    "STREAMRIP_QOBUZ_EMAIL": "",
    "STREAMRIP_QOBUZ_PASSWORD": "",
    "STREAMRIP_TIDAL_ENABLED": False,
    "STREAMRIP_TIDAL_QUALITY": 3,
    "STREAMRIP_TIDAL_EMAIL": "",
    "STREAMRIP_TIDAL_PASSWORD": "",
    "STREAMRIP_TIDAL_ACCESS_TOKEN": "",
    "STREAMRIP_TIDAL_REFRESH_TOKEN": "",
    "STREAMRIP_TIDAL_USER_ID": "",
    "STREAMRIP_TIDAL_COUNTRY_CODE": "",
    "STREAMRIP_DEEZER_ENABLED": False,
    "STREAMRIP_DEEZER_QUALITY": 2,
    "STREAMRIP_DEEZER_ARL": "",
    "STREAMRIP_SOUNDCLOUD_ENABLED": False,
    "STREAMRIP_SOUNDCLOUD_QUALITY": 0,
    "STREAMRIP_SOUNDCLOUD_CLIENT_ID": "",
    "STREAMRIP_FILENAME_TEMPLATE": "",
    "STREAMRIP_FOLDER_TEMPLATE": "",
    "STREAMRIP_EMBED_COVER_ART": False,
    "STREAMRIP_SAVE_COVER_ART": False,
    "STREAMRIP_COVER_ART_SIZE": "large",
    # Missing Streamrip Settings
    "STREAMRIP_MAX_CONNECTIONS": 6,
    "STREAMRIP_REQUESTS_PER_MINUTE": 60,
    "STREAMRIP_SOURCE_SUBDIRECTORIES": False,
    "STREAMRIP_DISC_SUBDIRECTORIES": True,
    "STREAMRIP_CONCURRENCY": True,
    "STREAMRIP_VERIFY_SSL": True,
    "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS": False,
    "STREAMRIP_QOBUZ_USE_AUTH_TOKEN": False,
    "STREAMRIP_QOBUZ_APP_ID": "",
    "STREAMRIP_QOBUZ_SECRETS": [],
    "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS": False,
    "STREAMRIP_TIDAL_TOKEN_EXPIRY": "",
    "STREAMRIP_DEEZER_USE_DEEZLOADER": False,
    "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS": True,
    "STREAMRIP_SOUNDCLOUD_APP_VERSION": "",
    "STREAMRIP_YOUTUBE_QUALITY": 0,
    "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS": False,
    "STREAMRIP_YOUTUBE_VIDEO_FOLDER": "",
    "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER": "",
    "STREAMRIP_DATABASE_DOWNLOADS_ENABLED": False,
    "STREAMRIP_DATABASE_DOWNLOADS_PATH": "./downloads.db",
    "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED": True,
    "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH": "./failed_downloads.db",
    "STREAMRIP_CONVERSION_ENABLED": False,
    "STREAMRIP_CONVERSION_CODEC": "ALAC",
    "STREAMRIP_CONVERSION_SAMPLING_RATE": 48000,
    "STREAMRIP_CONVERSION_BIT_DEPTH": 24,
    "STREAMRIP_CONVERSION_LOSSY_BITRATE": 320,
    "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM": True,
    "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS": True,
    "STREAMRIP_METADATA_EXCLUDE": [],
    "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER": False,
    "STREAMRIP_FILEPATHS_FOLDER_FORMAT": "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]",
    "STREAMRIP_FILEPATHS_TRACK_FORMAT": "{tracknumber:02}. {artist} - {title}{explicit}",
    "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS": False,
    "STREAMRIP_FILEPATHS_TRUNCATE_TO": 120,
    "STREAMRIP_LASTFM_SOURCE": "qobuz",
    "STREAMRIP_LASTFM_FALLBACK_SOURCE": "",
    "STREAMRIP_CLI_TEXT_OUTPUT": True,
    "STREAMRIP_CLI_PROGRESS_BARS": True,
    "STREAMRIP_CLI_MAX_SEARCH_RESULTS": 100,
    "STREAMRIP_MISC_CHECK_FOR_UPDATES": True,
    "STREAMRIP_MISC_VERSION": "2.0.6",
    # Missing Streamrip Configurations
    "STREAMRIP_SUPPORTED_CODECS": ["flac", "mp3", "m4a", "ogg", "opus"],
    "STREAMRIP_LASTFM_ENABLED": True,
    "STREAMRIP_QOBUZ_FILTERS_EXTRAS": False,
    "STREAMRIP_QOBUZ_FILTERS_REPEATS": False,
    "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS": False,
    "STREAMRIP_QOBUZ_FILTERS_FEATURES": False,
    "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS": False,
    "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER": False,
    "STREAMRIP_ARTWORK_EMBED": True,
    "STREAMRIP_ARTWORK_EMBED_SIZE": "large",
    "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH": -1,
    "STREAMRIP_ARTWORK_SAVE_ARTWORK": True,
    "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH": -1,
    # Zotify Settings - Based on official Zotify CONFIG_VALUES
    "ZOTIFY_ENABLED": True,
    "ZOTIFY_CREDENTIALS_PATH": "./zotify_credentials.json",
    "ZOTIFY_ALBUM_LIBRARY": "Music/Zotify Albums",
    "ZOTIFY_PODCAST_LIBRARY": "Music/Zotify Podcasts",
    "ZOTIFY_PLAYLIST_LIBRARY": "Music/Zotify Playlists",
    "ZOTIFY_OUTPUT_ALBUM": "{album_artist}/{album}/Disc {discnumber}/{track_number}. {artists} - {title}",
    "ZOTIFY_OUTPUT_PLAYLIST_TRACK": "{playlist}/{artists} - {title}",
    "ZOTIFY_OUTPUT_PLAYLIST_EPISODE": "{playlist}/{episode_number} - {title}",
    "ZOTIFY_OUTPUT_PODCAST": "{podcast}/{episode_number} - {title}",
    "ZOTIFY_OUTPUT_SINGLE": "{artists} - {title}",
    "ZOTIFY_DOWNLOAD_QUALITY": "auto",
    "ZOTIFY_AUDIO_FORMAT": "vorbis",
    "ZOTIFY_ARTWORK_SIZE": "large",
    "ZOTIFY_TRANSCODE_BITRATE": -1,
    "ZOTIFY_DOWNLOAD_REAL_TIME": False,
    "ZOTIFY_REPLACE_EXISTING": False,
    "ZOTIFY_SKIP_DUPLICATES": True,
    "ZOTIFY_SKIP_PREVIOUS": True,
    "ZOTIFY_SAVE_METADATA": True,
    "ZOTIFY_SAVE_GENRE": False,
    "ZOTIFY_ALL_ARTISTS": True,
    "ZOTIFY_LYRICS_FILE": False,
    "ZOTIFY_LYRICS_ONLY": False,
    "ZOTIFY_SAVE_SUBTITLES": False,
    "ZOTIFY_CREATE_PLAYLIST_FILE": True,
    "ZOTIFY_FFMPEG_PATH": "",
    "ZOTIFY_FFMPEG_ARGS": "",
    "ZOTIFY_LANGUAGE": "en",
    "ZOTIFY_PRINT_PROGRESS": True,
    "ZOTIFY_PRINT_DOWNLOADS": False,
    "ZOTIFY_PRINT_ERRORS": True,
    "ZOTIFY_PRINT_WARNINGS": True,
    "ZOTIFY_PRINT_SKIPS": False,
    "ZOTIFY_MATCH_EXISTING": False,
    # DDL (Direct Download Link) Upload Settings
    "DDL_ENABLED": True,
    "DDL_DEFAULT_SERVER": "gofile",
    "GOFILE_API_KEY": "",
    "GOFILE_FOLDER_NAME": "",
    "GOFILE_PUBLIC_LINKS": True,
    "GOFILE_PASSWORD_PROTECTION": False,
    "GOFILE_DEFAULT_PASSWORD": "",
    "GOFILE_LINK_EXPIRY_DAYS": 0,
    "STREAMTAPE_API_USERNAME": "",
    "STREAMTAPE_API_PASSWORD": "",
    "STREAMTAPE_FOLDER_NAME": "",
    "DEVUPLOADS_API_KEY": "",
    "DEVUPLOADS_FOLDER_NAME": "",
    "DEVUPLOADS_PUBLIC_FILES": True,
    "MEDIAFIRE_EMAIL": "",
    "MEDIAFIRE_PASSWORD": "",
    "MEDIAFIRE_APP_ID": "",
    "MEDIAFIRE_API_KEY": "",
    # Google Drive Upload Settings
    "GDRIVE_UPLOAD_ENABLED": True,
    # MEGA Settings
    "MEGA_ENABLED": True,
    "MEGA_UPLOAD_ENABLED": True,
    # YouTube Upload Settings
    "YOUTUBE_UPLOAD_ENABLED": True,
    "YOUTUBE_UPLOAD_DEFAULT_PRIVACY": "unlisted",
    "YOUTUBE_UPLOAD_DEFAULT_CATEGORY": "22",
    "YOUTUBE_UPLOAD_DEFAULT_TAGS": "",
    "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION": "Uploaded by AIM",
    # Watermark Settings
    "WATERMARK_ENABLED": False,
    "WATERMARK_KEY": "",
    "WATERMARK_POSITION": "none",
    "WATERMARK_SIZE": 0,
    "WATERMARK_COLOR": "none",
    "WATERMARK_FONT": "none",
    "WATERMARK_PRIORITY": 2,
    "WATERMARK_THREADING": True,
    "WATERMARK_THREAD_NUMBER": 4,
    "WATERMARK_QUALITY": "none",
    "WATERMARK_SPEED": "none",
    "WATERMARK_OPACITY": 0.0,
    "WATERMARK_REMOVE_ORIGINAL": True,
    # Audio Watermark Settings
    "AUDIO_WATERMARK_VOLUME": 0.0,
    # Branding Settings
    "CREDIT": Config.CREDIT,
    "OWNER_THUMB": "https://graph.org/file/80b7fb095063a18f9e232.jpg",
    "AUDIO_WATERMARK_INTERVAL": 0,
    # Subtitle Watermark Settings
    "SUBTITLE_WATERMARK_STYLE": "none",
    "SUBTITLE_WATERMARK_INTERVAL": 0,
    # Image Watermark Settings
    "IMAGE_WATERMARK_ENABLED": False,
    "IMAGE_WATERMARK_PATH": "",
    "IMAGE_WATERMARK_SCALE": 10,
    "IMAGE_WATERMARK_OPACITY": 1.0,
    "IMAGE_WATERMARK_POSITION": "bottom_right",
    # Merge Settings
    "MERGE_ENABLED": False,
    "MERGE_PRIORITY": 1,
    "MERGE_THREADING": True,
    "MERGE_THREAD_NUMBER": 4,
    "MERGE_REMOVE_ORIGINAL": True,
    "CONCAT_DEMUXER_ENABLED": True,
    "FILTER_COMPLEX_ENABLED": False,
    # Merge Output Formats
    "MERGE_OUTPUT_FORMAT_VIDEO": "none",
    "MERGE_OUTPUT_FORMAT_AUDIO": "none",
    "MERGE_OUTPUT_FORMAT_IMAGE": "none",
    "MERGE_OUTPUT_FORMAT_DOCUMENT": "none",
    "MERGE_OUTPUT_FORMAT_SUBTITLE": "none",
    # Merge Video Settings
    "MERGE_VIDEO_CODEC": "none",
    "MERGE_VIDEO_QUALITY": "none",
    "MERGE_VIDEO_PRESET": "none",
    "MERGE_VIDEO_CRF": "none",
    "MERGE_VIDEO_PIXEL_FORMAT": "none",
    "MERGE_VIDEO_TUNE": "none",
    "MERGE_VIDEO_FASTSTART": False,
    # Merge Audio Settings
    "MERGE_AUDIO_CODEC": "none",
    "MERGE_AUDIO_BITRATE": "none",
    "MERGE_AUDIO_CHANNELS": "none",
    "MERGE_AUDIO_SAMPLING": "none",
    "MERGE_AUDIO_VOLUME": "none",
    # Merge Image Settings
    "MERGE_IMAGE_MODE": "none",
    "MERGE_IMAGE_COLUMNS": "none",
    "MERGE_IMAGE_QUALITY": 90,
    "MERGE_IMAGE_DPI": "none",
    "MERGE_IMAGE_RESIZE": "none",
    "MERGE_IMAGE_BACKGROUND": "none",
    # Merge Subtitle Settings
    "MERGE_SUBTITLE_ENCODING": "none",
    "MERGE_SUBTITLE_FONT": "none",
    "MERGE_SUBTITLE_FONT_SIZE": "none",
    "MERGE_SUBTITLE_FONT_COLOR": "none",
    "MERGE_SUBTITLE_BACKGROUND": "none",
    # Merge Document Settings
    "MERGE_DOCUMENT_PAPER_SIZE": "none",
    "MERGE_DOCUMENT_ORIENTATION": "none",
    "MERGE_DOCUMENT_MARGIN": "none",
    # Merge Metadata Settings
    "MERGE_METADATA_TITLE": "none",
    "MERGE_METADATA_AUTHOR": "none",
    "MERGE_METADATA_COMMENT": "none",
    # Compression Settings
    "COMPRESSION_ENABLED": False,
    "COMPRESSION_PRIORITY": 4,
    "COMPRESSION_DELETE_ORIGINAL": True,
    # Video Compression Settings
    "COMPRESSION_VIDEO_ENABLED": False,
    "COMPRESSION_VIDEO_PRESET": "none",
    "COMPRESSION_VIDEO_CRF": "none",
    "COMPRESSION_VIDEO_CODEC": "none",
    "COMPRESSION_VIDEO_TUNE": "none",
    "COMPRESSION_VIDEO_PIXEL_FORMAT": "none",
    "COMPRESSION_VIDEO_BITDEPTH": "none",
    "COMPRESSION_VIDEO_BITRATE": "none",
    "COMPRESSION_VIDEO_RESOLUTION": "none",
    "COMPRESSION_VIDEO_DELETE_ORIGINAL": True,
    # Audio Compression Settings
    "COMPRESSION_AUDIO_ENABLED": False,
    "COMPRESSION_AUDIO_PRESET": "none",
    "COMPRESSION_AUDIO_CODEC": "none",
    "COMPRESSION_AUDIO_BITRATE": "none",
    "COMPRESSION_AUDIO_CHANNELS": "none",
    "COMPRESSION_AUDIO_BITDEPTH": "none",
    "COMPRESSION_AUDIO_DELETE_ORIGINAL": True,
    # Image Compression Settings
    "COMPRESSION_IMAGE_ENABLED": False,
    "COMPRESSION_IMAGE_PRESET": "none",
    "COMPRESSION_IMAGE_QUALITY": "none",
    "COMPRESSION_IMAGE_RESIZE": "none",
    "COMPRESSION_IMAGE_DELETE_ORIGINAL": True,
    # Document Compression Settings
    "COMPRESSION_DOCUMENT_ENABLED": False,
    "COMPRESSION_DOCUMENT_PRESET": "none",
    "COMPRESSION_DOCUMENT_DPI": "none",
    "COMPRESSION_DOCUMENT_DELETE_ORIGINAL": True,
    # Subtitle Compression Settings
    "COMPRESSION_SUBTITLE_ENABLED": False,
    "COMPRESSION_SUBTITLE_PRESET": "none",
    "COMPRESSION_SUBTITLE_ENCODING": "none",
    "COMPRESSION_SUBTITLE_DELETE_ORIGINAL": True,
    # Archive Compression Settings
    "COMPRESSION_ARCHIVE_ENABLED": False,
    "COMPRESSION_ARCHIVE_PRESET": "none",
    "COMPRESSION_ARCHIVE_LEVEL": "none",
    "COMPRESSION_ARCHIVE_METHOD": "none",
    "COMPRESSION_ARCHIVE_PASSWORD": "none",
    "COMPRESSION_ARCHIVE_ALGORITHM": "none",
    "COMPRESSION_ARCHIVE_DELETE_ORIGINAL": True,
    # Trim Settings
    "TRIM_ENABLED": False,
    "TRIM_PRIORITY": 5,
    "TRIM_START_TIME": "00:00:00",
    "TRIM_END_TIME": "",
    "TRIM_DELETE_ORIGINAL": True,
    # Video Trim Settings
    "TRIM_VIDEO_ENABLED": False,
    "TRIM_VIDEO_CODEC": "none",
    "TRIM_VIDEO_PRESET": "none",
    "TRIM_VIDEO_FORMAT": "none",
    # Audio Trim Settings
    "TRIM_AUDIO_ENABLED": False,
    "TRIM_AUDIO_CODEC": "none",
    "TRIM_AUDIO_PRESET": "none",
    "TRIM_AUDIO_FORMAT": "none",
    # Image Trim Settings
    "TRIM_IMAGE_ENABLED": False,
    "TRIM_IMAGE_QUALITY": "none",
    "TRIM_IMAGE_FORMAT": "none",
    # Document Trim Settings
    "TRIM_DOCUMENT_ENABLED": False,
    "TRIM_DOCUMENT_START_PAGE": "1",
    "TRIM_DOCUMENT_END_PAGE": "",
    "TRIM_DOCUMENT_QUALITY": "none",
    "TRIM_DOCUMENT_FORMAT": "none",
    # Subtitle Trim Settings
    "TRIM_SUBTITLE_ENABLED": False,
    "TRIM_SUBTITLE_ENCODING": "none",
    "TRIM_SUBTITLE_FORMAT": "none",
    # Archive Trim Settings
    "TRIM_ARCHIVE_ENABLED": False,
    "TRIM_ARCHIVE_FORMAT": "none",
    # Extract Settings
    "EXTRACT_ENABLED": False,
    "EXTRACT_PRIORITY": 6,
    "EXTRACT_DELETE_ORIGINAL": True,
    # Video Extract Settings
    "EXTRACT_VIDEO_ENABLED": False,
    "EXTRACT_VIDEO_CODEC": "none",
    "EXTRACT_VIDEO_FORMAT": "none",
    "EXTRACT_VIDEO_INDEX": None,
    "EXTRACT_VIDEO_QUALITY": "none",
    "EXTRACT_VIDEO_PRESET": "none",
    "EXTRACT_VIDEO_BITRATE": "none",
    "EXTRACT_VIDEO_RESOLUTION": "none",
    "EXTRACT_VIDEO_FPS": "none",
    # Audio Extract Settings
    "EXTRACT_AUDIO_ENABLED": False,
    "EXTRACT_AUDIO_CODEC": "none",
    "EXTRACT_AUDIO_FORMAT": "none",
    "EXTRACT_AUDIO_INDEX": None,
    "EXTRACT_AUDIO_BITRATE": "none",
    "EXTRACT_AUDIO_CHANNELS": "none",
    "EXTRACT_AUDIO_SAMPLING": "none",
    "EXTRACT_AUDIO_VOLUME": "none",
    # Subtitle Extract Settings
    "EXTRACT_SUBTITLE_ENABLED": False,
    "EXTRACT_SUBTITLE_CODEC": "none",
    "EXTRACT_SUBTITLE_FORMAT": "none",
    "EXTRACT_SUBTITLE_INDEX": None,
    "EXTRACT_SUBTITLE_LANGUAGE": "none",
    "EXTRACT_SUBTITLE_ENCODING": "none",
    "EXTRACT_SUBTITLE_FONT": "none",
    "EXTRACT_SUBTITLE_FONT_SIZE": "none",
    # Attachment Extract Settings
    "EXTRACT_ATTACHMENT_ENABLED": False,
    "EXTRACT_ATTACHMENT_FORMAT": "none",
    "EXTRACT_ATTACHMENT_INDEX": None,
    "EXTRACT_ATTACHMENT_FILTER": "none",
    "EXTRACT_MAINTAIN_QUALITY": True,
    # Remove Settings
    "REMOVE_ENABLED": False,
    "REMOVE_PRIORITY": 8,
    "REMOVE_DELETE_ORIGINAL": True,
    "REMOVE_METADATA": False,
    "REMOVE_MAINTAIN_QUALITY": True,
    # Video Remove Settings
    "REMOVE_VIDEO_ENABLED": False,
    "REMOVE_VIDEO_CODEC": "none",
    "REMOVE_VIDEO_FORMAT": "none",
    "REMOVE_VIDEO_INDEX": None,
    "REMOVE_VIDEO_QUALITY": "none",
    "REMOVE_VIDEO_PRESET": "none",
    "REMOVE_VIDEO_BITRATE": "none",
    "REMOVE_VIDEO_RESOLUTION": "none",
    "REMOVE_VIDEO_FPS": "none",
    # Audio Remove Settings
    "REMOVE_AUDIO_ENABLED": False,
    "REMOVE_AUDIO_CODEC": "none",
    "REMOVE_AUDIO_FORMAT": "none",
    "REMOVE_AUDIO_INDEX": None,
    "REMOVE_AUDIO_BITRATE": "none",
    "REMOVE_AUDIO_CHANNELS": "none",
    "REMOVE_AUDIO_SAMPLING": "none",
    "REMOVE_AUDIO_VOLUME": "none",
    # Subtitle Remove Settings
    "REMOVE_SUBTITLE_ENABLED": False,
    "REMOVE_SUBTITLE_CODEC": "none",
    "REMOVE_SUBTITLE_FORMAT": "none",
    "REMOVE_SUBTITLE_INDEX": None,
    "REMOVE_SUBTITLE_LANGUAGE": "none",
    "REMOVE_SUBTITLE_ENCODING": "none",
    "REMOVE_SUBTITLE_FONT": "none",
    "REMOVE_SUBTITLE_FONT_SIZE": "none",
    # Attachment Remove Settings
    "REMOVE_ATTACHMENT_ENABLED": False,
    "REMOVE_ATTACHMENT_FORMAT": "none",
    "REMOVE_ATTACHMENT_INDEX": None,
    "REMOVE_ATTACHMENT_FILTER": "none",
    # Add Settings
    "ADD_ENABLED": False,
    "ADD_PRIORITY": 7,
    "ADD_DELETE_ORIGINAL": True,
    "ADD_PRESERVE_TRACKS": False,
    "ADD_REPLACE_TRACKS": False,
    # Video Add Settings
    "ADD_VIDEO_ENABLED": False,
    "ADD_VIDEO_CODEC": "none",
    "ADD_VIDEO_INDEX": None,
    "ADD_VIDEO_QUALITY": "none",
    "ADD_VIDEO_PRESET": "none",
    "ADD_VIDEO_BITRATE": "none",
    "ADD_VIDEO_RESOLUTION": "none",
    "ADD_VIDEO_FPS": "none",
    # Audio Add Settings
    "ADD_AUDIO_ENABLED": False,
    "ADD_AUDIO_CODEC": "none",
    "ADD_AUDIO_INDEX": None,
    "ADD_AUDIO_BITRATE": "none",
    "ADD_AUDIO_CHANNELS": "none",
    "ADD_AUDIO_SAMPLING": "none",
    "ADD_AUDIO_VOLUME": "none",
    # Subtitle Add Settings
    "ADD_SUBTITLE_ENABLED": False,
    "ADD_SUBTITLE_CODEC": "none",
    "ADD_SUBTITLE_INDEX": None,
    "ADD_SUBTITLE_LANGUAGE": "none",
    "ADD_SUBTITLE_ENCODING": "none",
    "ADD_SUBTITLE_FONT": "none",
    "ADD_SUBTITLE_FONT_SIZE": "none",
    "ADD_SUBTITLE_HARDSUB_ENABLED": False,
    # Attachment Add Settings
    "ADD_ATTACHMENT_ENABLED": False,
    "ADD_ATTACHMENT_INDEX": None,
    "ADD_ATTACHMENT_MIMETYPE": "none",
    # Swap Settings
    "SWAP_ENABLED": False,
    "SWAP_PRIORITY": 6,
    "SWAP_REMOVE_ORIGINAL": False,
    # Audio Swap Settings
    "SWAP_AUDIO_ENABLED": False,
    "SWAP_AUDIO_USE_LANGUAGE": True,
    "SWAP_AUDIO_LANGUAGE_ORDER": "eng,hin",
    "SWAP_AUDIO_INDEX_ORDER": "0,1",
    # Video Swap Settings
    "SWAP_VIDEO_ENABLED": False,
    "SWAP_VIDEO_USE_LANGUAGE": True,
    "SWAP_VIDEO_LANGUAGE_ORDER": "eng,hin",
    "SWAP_VIDEO_INDEX_ORDER": "0,1",
    # Subtitle Swap Settings
    "SWAP_SUBTITLE_ENABLED": False,
    "SWAP_SUBTITLE_USE_LANGUAGE": True,
    "SWAP_SUBTITLE_LANGUAGE_ORDER": "eng,hin",
    "SWAP_SUBTITLE_INDEX_ORDER": "0,1",
    # Convert Settings
    "CONVERT_ENABLED": False,
    "CONVERT_PRIORITY": 3,
    "CONVERT_DELETE_ORIGINAL": True,
    # Video Convert Settings
    "CONVERT_VIDEO_ENABLED": False,
    "CONVERT_VIDEO_FORMAT": "none",
    "CONVERT_VIDEO_CODEC": "none",
    "CONVERT_VIDEO_QUALITY": "none",
    "CONVERT_VIDEO_CRF": 0,
    "CONVERT_VIDEO_PRESET": "none",
    "CONVERT_VIDEO_MAINTAIN_QUALITY": True,
    "CONVERT_VIDEO_RESOLUTION": "none",
    "CONVERT_VIDEO_FPS": "none",
    "CONVERT_VIDEO_DELETE_ORIGINAL": True,
    # Audio Convert Settings
    "CONVERT_AUDIO_ENABLED": False,
    "CONVERT_AUDIO_FORMAT": "none",
    "CONVERT_AUDIO_CODEC": "none",
    "CONVERT_AUDIO_BITRATE": "none",
    "CONVERT_AUDIO_CHANNELS": 0,
    "CONVERT_AUDIO_SAMPLING": 0,
    "CONVERT_AUDIO_VOLUME": 0.0,
    "CONVERT_AUDIO_DELETE_ORIGINAL": True,
    # Subtitle Convert Settings
    "CONVERT_SUBTITLE_ENABLED": False,
    "CONVERT_SUBTITLE_FORMAT": "none",
    "CONVERT_SUBTITLE_ENCODING": "none",
    "CONVERT_SUBTITLE_LANGUAGE": "none",
    "CONVERT_SUBTITLE_DELETE_ORIGINAL": True,
    # Document Convert Settings
    "CONVERT_DOCUMENT_ENABLED": False,
    "CONVERT_DOCUMENT_FORMAT": "none",
    "CONVERT_DOCUMENT_QUALITY": 0,
    "CONVERT_DOCUMENT_DPI": 0,
    "CONVERT_DOCUMENT_DELETE_ORIGINAL": True,
    # Archive Convert Settings
    "CONVERT_ARCHIVE_ENABLED": False,
    "CONVERT_ARCHIVE_FORMAT": "none",
    "CONVERT_ARCHIVE_LEVEL": 0,
    "CONVERT_ARCHIVE_METHOD": "none",
    "CONVERT_ARCHIVE_DELETE_ORIGINAL": True,
    # Media Tools Settings
    "MEDIAINFO_ENABLED": False,
    # Task Monitoring Settings
    "TASK_MONITOR_ENABLED": False,
    "TASK_MONITOR_INTERVAL": 60,
    "TASK_MONITOR_CONSECUTIVE_CHECKS": 3,
    "TASK_MONITOR_SPEED_THRESHOLD": 50,
    "TASK_MONITOR_ELAPSED_THRESHOLD": 3600,
    "TASK_MONITOR_ETA_THRESHOLD": 86400,
    "TASK_MONITOR_WAIT_TIME": 600,
    "TASK_MONITOR_COMPLETION_THRESHOLD": 14400,
    "TASK_MONITOR_CPU_HIGH": 90,
    "TASK_MONITOR_CPU_LOW": 40,
    "TASK_MONITOR_MEMORY_HIGH": 75,
    "TASK_MONITOR_MEMORY_LOW": 60,
}


async def get_image_watermark(user_id):
    """Get the image watermark for a user.

    This function checks if the user has an image watermark in the database.
    If not, it falls back to the owner's image watermark.

    Args:
        user_id: The user ID to get the image watermark for.

    Returns:
        The image watermark data as bytes, or None if no watermark is found.
    """
    # First, try to get the user's image watermark
    user_doc = await database.get_user_doc(user_id)
    if user_doc and "IMAGE_WATERMARK" in user_doc and user_doc["IMAGE_WATERMARK"]:
        return user_doc["IMAGE_WATERMARK"]

    # If the user doesn't have an image watermark, try to get the owner's
    if hasattr(Config, "OWNER_ID"):
        owner_doc = await database.get_user_doc(Config.OWNER_ID)
        if (
            owner_doc
            and "IMAGE_WATERMARK" in owner_doc
            and owner_doc["IMAGE_WATERMARK"]
        ):
            return owner_doc["IMAGE_WATERMARK"]

    # If no image watermark is found, return None
    return None


async def get_buttons(key=None, edit_type=None, page=0, user_id=None):
    buttons = ButtonMaker()
    msg = ""  # Initialize msg with a default value
    if key is None:
        # Group buttons by category for better organization
        # Core Settings
        buttons.data_button("⚙️ Config Variables", "botset var")
        buttons.data_button("🔒 Private Files", "botset private")

        # Download Clients
        buttons.data_button("🔄 qBittorrent", "botset qbit")
        buttons.data_button("📥 Aria2c", "botset aria")
        buttons.data_button("📦 Sabnzbd", "botset nzb")
        buttons.data_button("🔄 JD Sync", "botset syncjd")

        # Monitoring & Tools
        buttons.data_button("📊 Task Monitor", "botset taskmonitor")
        buttons.data_button("🔄 Operations", "botset operations")

        # Always show Media Tools button, regardless of whether tools are enabled
        buttons.data_button("🎬 Media Tools", "botset mediatools")

        # Only show AI Settings button if AI is enabled
        if Config.AI_ENABLED:
            buttons.data_button("🤖 AI Settings", "botset ai")

        # Only show Streamrip Settings button if Streamrip is enabled
        if Config.STREAMRIP_ENABLED:
            buttons.data_button("🎵 Streamrip", "botset streamrip")

        # Only show Gallery-dl Settings button if Gallery-dl is enabled
        if Config.GALLERY_DL_ENABLED:
            buttons.data_button("🖼️ Gallery-dl", "botset gallerydl")

        # Only show Zotify Settings button if Zotify is enabled
        if Config.ZOTIFY_ENABLED:
            buttons.data_button("🎧 Zotify", "botset zotify")

        # Only show YouTube API Settings button if YouTube upload is enabled
        if Config.YOUTUBE_UPLOAD_ENABLED:
            buttons.data_button("📺 YouTube API", "botset youtube")

        # Only show MEGA Settings button if MEGA is enabled
        if Config.MEGA_ENABLED:
            buttons.data_button("☁️ MEGA", "botset mega")

        # Only show DDL Settings button if DDL is enabled
        if Config.DDL_ENABLED:
            buttons.data_button("📤 DDL", "botset ddl")

        buttons.data_button("❌ Close", "botset close")
        msg = "<b>Bot Settings</b>\nSelect a category to configure:"
    elif edit_type is not None:
        if edit_type == "editvar" and (
            key.startswith(
                (
                    "WATERMARK_",
                    "AUDIO_WATERMARK_",
                    "SUBTITLE_WATERMARK_",
                    "IMAGE_WATERMARK_",
                    "MERGE_",
                    "METADATA_",
                    "TASK_MONITOR_",
                    "CONVERT_",
                    "COMPRESSION_",
                    "TRIM_",
                    "EXTRACT_",
                    "MISTRAL_",
                    "DEEPSEEK_",
                )
            )
            or key
            in [
                "CONCAT_DEMUXER_ENABLED",
                "FILTER_COMPLEX_ENABLED",
            ]
        ):
            msg = ""
            if key.startswith(
                (
                    "WATERMARK_",
                    "AUDIO_WATERMARK_",
                    "SUBTITLE_WATERMARK_",
                    "IMAGE_WATERMARK_",
                )
            ):
                # Check if we're in the watermark text menu
                if key in [
                    "WATERMARK_POSITION",
                    "WATERMARK_SIZE",
                    "WATERMARK_COLOR",
                    "WATERMARK_FONT",
                    "WATERMARK_OPACITY",
                    "WATERMARK_QUALITY",
                    "WATERMARK_SPEED",
                    "AUDIO_WATERMARK_VOLUME",
                    "AUDIO_WATERMARK_INTERVAL",
                    "SUBTITLE_WATERMARK_STYLE",
                    "SUBTITLE_WATERMARK_INTERVAL",
                    "WATERMARK_KEY",
                    "AUDIO_WATERMARK_TEXT",
                    "SUBTITLE_WATERMARK_TEXT",
                    "IMAGE_WATERMARK_SCALE",
                    "IMAGE_WATERMARK_POSITION",
                    "IMAGE_WATERMARK_OPACITY",
                ]:
                    # If we're in the watermark text menu, include the current page in the back button
                    current_page = globals().get("watermark_text_page", 0)
                    buttons.data_button(
                        "Back", f"botset back_to_watermark_text_page {current_page}"
                    )
                else:
                    buttons.data_button("Back", "botset mediatools_watermark")
            elif key.startswith("METADATA_"):
                buttons.data_button("Back", "botset mediatools_metadata")
            elif key.startswith("TRIM_"):
                buttons.data_button("Back", "botset mediatools_trim")
            elif key.startswith("COMPRESSION_"):
                buttons.data_button("Back", "botset mediatools_compression")
            elif key.startswith("CONVERT_"):
                buttons.data_button("Back", "botset mediatools_convert")
            elif key.startswith("EXTRACT_"):
                buttons.data_button("Back", "botset mediatools_extract")
            elif key.startswith("REMOVE_"):
                buttons.data_button("Back", "botset mediatools_remove")
            elif key.startswith("ADD_"):
                buttons.data_button("Back", "botset mediatools_add")
            elif key.startswith("TASK_MONITOR_"):
                buttons.data_button("⬅️ Back", "botset taskmonitor")
            elif key.startswith(("MISTRAL_", "DEEPSEEK_")):
                buttons.data_button("Back", "botset ai")
            elif key.startswith("MERGE_") and any(
                x in key
                for x in [
                    "OUTPUT_FORMAT",
                    "VIDEO_",
                    "AUDIO_",
                    "IMAGE_",
                    "SUBTITLE_",
                    "DOCUMENT_",
                    "METADATA_",
                ]
            ):
                # If it's a format setting, it's from the merge_config menu
                # Store the current page in the callback data to ensure we return to the correct page
                if "merge_config_page" in globals():
                    page = globals()["merge_config_page"]
                    buttons.data_button(
                        "Back", f"botset back_to_merge_config {page}"
                    )
                else:
                    buttons.data_button("Back", "botset mediatools_merge_config")
            elif key in [
                "MERGE_ENABLED",
                "MERGE_PRIORITY",
                "MERGE_THREADING",
                "MERGE_THREAD_NUMBER",
                "MERGE_REMOVE_ORIGINAL",
                "CONCAT_DEMUXER_ENABLED",
                "FILTER_COMPLEX_ENABLED",
            ]:
                # These are from the main merge menu
                # Store the current page in the callback data to ensure we return to the correct page
                if "merge_page" in globals():
                    page = globals()["merge_page"]
                    buttons.data_button("Back", f"botset back_to_merge {page}")
                else:
                    buttons.data_button("Back", "botset mediatools_merge")
            # Default to merge menu for any other merge settings
            # Store the current page in the callback data to ensure we return to the correct page
            elif "merge_page" in globals():
                page = globals()["merge_page"]
                buttons.data_button("Back", f"botset back_to_merge {page}")
            else:
                buttons.data_button("Back", "botset mediatools_merge")
            buttons.data_button("Close", "botset close")

            # Get help text for settings
            if key in {
                "WATERMARK_ENABLED",
                "WATERMARK_THREADING",
                "MERGE_ENABLED",
                "CONCAT_DEMUXER_ENABLED",
                "FILTER_COMPLEX_ENABLED",
                "MERGE_THREADING",
                "MERGE_REMOVE_ORIGINAL",
                "MERGE_VIDEO_FASTSTART",
                "CONVERT_ENABLED",
                "CONVERT_VIDEO_ENABLED",
                "CONVERT_AUDIO_ENABLED",
                "CONVERT_SUBTITLE_ENABLED",
                "CONVERT_DOCUMENT_ENABLED",
                "CONVERT_ARCHIVE_ENABLED",
                "CONVERT_VIDEO_MAINTAIN_QUALITY",
                "CONVERT_DELETE_ORIGINAL",
                "COMPRESSION_ENABLED",
                "COMPRESSION_VIDEO_ENABLED",
                "COMPRESSION_AUDIO_ENABLED",
                "COMPRESSION_IMAGE_ENABLED",
                "COMPRESSION_DOCUMENT_ENABLED",
                "COMPRESSION_SUBTITLE_ENABLED",
                "COMPRESSION_ARCHIVE_ENABLED",
                "TASK_MONITOR_ENABLED",
                "TORRENT_ENABLED",
            }:
                help_text = (
                    "Send 'true' to enable or 'false' to disable this feature."
                )
            elif key == "WATERMARK_KEY":
                help_text = """<b>Watermark Text Configuration</b>

Send the text you want to add as watermark to all media files.

<b>Examples:</b>
• Your channel name: <code>@YourChannel</code>
• Copyright text: <code>© 2023 Your Name</code>
• Custom message: <code>Exclusive Content</code>

<b>Note:</b> This text will be applied to videos, images, and other media files."""
            elif key == "AUDIO_WATERMARK_TEXT":
                help_text = """<b>Audio Watermark Text</b>

Send the text to be used specifically for audio watermarks.

<b>Note:</b> If left empty, the main watermark text will be used instead.

<b>Examples:</b>
• <code>Audio by @YourChannel</code>
• <code>Voice recording - Do not share</code>"""
            elif key == "SUBTITLE_WATERMARK_TEXT":
                help_text = """<b>Subtitle Watermark Text</b>

Send the text to be used specifically for subtitle watermarks.

<b>Note:</b> If left empty, the main watermark text will be used instead.

<b>Examples:</b>
• <code>Subtitles by @YourChannel</code>
• <code>Translated by Your Name</code>"""
            elif key == "WATERMARK_POSITION":
                help_text = """<b>Watermark Position</b>

Send one of the following position options:
• <code>top_left</code> - Place watermark in the top left corner
• <code>top_right</code> - Place watermark in the top right corner
• <code>bottom_left</code> - Place watermark in the bottom left corner
• <code>bottom_right</code> - Place watermark in the bottom right corner
• <code>center</code> - Place watermark in the center of the media

<b>Example:</b> <code>bottom_right</code>"""
            elif key == "WATERMARK_SIZE":
                help_text = """<b>Watermark Size</b>

Send an integer value to set the font size for text watermarks.

<b>Recommended values:</b>
• Small: <code>12</code> to <code>18</code>
• Medium: <code>20</code> to <code>30</code>
• Large: <code>32</code> to <code>48</code>

<b>Example:</b> <code>24</code>"""
            elif key == "WATERMARK_COLOR":
                help_text = """<b>Watermark Color</b>

Send a color name or hex code for the watermark text.

<b>Common colors:</b>
• <code>white</code> - Good for dark backgrounds
• <code>black</code> - Good for light backgrounds
• <code>red</code>, <code>blue</code>, <code>green</code>, <code>yellow</code>
• <code>#FF0000</code> - Red in hex format
• <code>#FFFFFF</code> - White in hex format

<b>Example:</b> <code>white</code> or <code>#FFFFFF</code>"""
            elif key == "WATERMARK_FONT":
                help_text = """<b>Watermark Font</b>

Send the font filename to use for text watermarks.
The font file must exist in the bot's fonts directory.

<b>Default fonts:</b>
• <code>default.otf</code> - Standard font
• <code>arial.ttf</code> - Arial font (if available)
• <code>times.ttf</code> - Times New Roman (if available)

<b>Example:</b> <code>default.otf</code>"""
            elif key == "WATERMARK_OPACITY":
                help_text = """<b>Watermark Opacity</b>

Send a float value between 0.0 (completely transparent) and 1.0 (completely opaque).

<b>Recommended values:</b>
• <code>0.3</code> - Subtle watermark
• <code>0.5</code> - Medium visibility
• <code>0.8</code> - High visibility
• <code>1.0</code> - Fully opaque

<b>Example:</b> <code>0.8</code>"""
            elif key == "WATERMARK_QUALITY":
                help_text = """<b>Watermark Quality</b>

Send a quality setting for the watermark. Higher values mean better quality but larger file size.

<b>Options:</b>
• <code>high</code> - Best quality, larger file size
• <code>medium</code> - Balanced quality and size
• <code>low</code> - Lower quality, smaller file size

<b>Example:</b> <code>medium</code>"""
            elif key == "WATERMARK_SPEED":
                help_text = """<b>Watermark Processing Speed</b>

Send a speed setting for watermark processing. Faster speeds may reduce quality.

<b>Options:</b>
• <code>fast</code> - Quick processing, may reduce quality
• <code>medium</code> - Balanced speed and quality
• <code>slow</code> - Slower processing for better quality

<b>Example:</b> <code>medium</code>"""
            elif key == "AUDIO_WATERMARK_VOLUME":
                help_text = """<b>Audio Watermark Volume</b>

Send a float value between 0.0 (silent) and 1.0 (full volume) for audio watermarks.

<b>Recommended values:</b>
• <code>0.1</code> - Very quiet
• <code>0.3</code> - Subtle background
• <code>0.5</code> - Medium volume
• <code>0.8</code> - Prominent

<b>Example:</b> <code>0.3</code>"""
            elif key == "AUDIO_WATERMARK_INTERVAL":
                help_text = """<b>Audio Watermark Interval</b>

Send an integer value in seconds to set the interval between audio watermarks.
Set to 0 to disable interval (watermark will be applied once).

<b>Examples:</b>
• <code>30</code> - Apply every 30 seconds
• <code>60</code> - Apply every minute
• <code>300</code> - Apply every 5 minutes

<b>Example:</b> <code>60</code>"""
            elif key == "SUBTITLE_WATERMARK_STYLE":
                help_text = """<b>Subtitle Watermark Style</b>

Send a style option for subtitle watermarks.

<b>Options:</b>
• <code>normal</code> - Regular text
• <code>bold</code> - Bold text
• <code>italic</code> - Italic text
• <code>underline</code> - Underlined text

<b>Example:</b> <code>italic</code>"""
            elif key == "SUBTITLE_WATERMARK_INTERVAL":
                help_text = """<b>Subtitle Watermark Interval</b>

Send an integer value in seconds to set the interval between subtitle watermarks.
Set to 0 to disable interval (watermark will be applied once).

<b>Examples:</b>
• <code>60</code> - Apply every minute
• <code>300</code> - Apply every 5 minutes
• <code>600</code> - Apply every 10 minutes

<b>Example:</b> <code>300</code>"""
            elif key in {
                "WATERMARK_THREAD_NUMBER",
                "MERGE_THREAD_NUMBER",
                "MERGE_PRIORITY",
                "MERGE_VIDEO_CRF",
                "MERGE_IMAGE_COLUMNS",
                "MERGE_IMAGE_QUALITY",
                "MERGE_IMAGE_DPI",
                "MERGE_SUBTITLE_FONT_SIZE",
                "MERGE_DOCUMENT_MARGIN",
                "MERGE_AUDIO_CHANNELS",
                "CONVERT_PRIORITY",
                "CONVERT_VIDEO_CRF",
                "CONVERT_AUDIO_CHANNELS",
                "CONVERT_AUDIO_SAMPLING",
                "CONVERT_DOCUMENT_QUALITY",
                "CONVERT_DOCUMENT_DPI",
                "CONVERT_ARCHIVE_LEVEL",
                "COMPRESSION_PRIORITY",
                "COMPRESSION_VIDEO_CRF",
                "COMPRESSION_AUDIO_CHANNELS",
                "COMPRESSION_IMAGE_QUALITY",
                "COMPRESSION_DOCUMENT_DPI",
                "COMPRESSION_ARCHIVE_LEVEL",
            }:
                help_text = (
                    "Send an integer value.\n\n<b>Example:</b> <code>4</code>"
                )
            elif key in {
                "WATERMARK_COLOR",
                "MERGE_VIDEO_PIXEL_FORMAT",
                "MERGE_VIDEO_TUNE",
                "MERGE_IMAGE_BACKGROUND",
                "MERGE_SUBTITLE_FONT_COLOR",
                "MERGE_SUBTITLE_BACKGROUND",
            }:
                help_text = "Send a color name.\n\n<b>Examples:</b> <code>white</code>, <code>black</code>, <code>red</code>, <code>green</code>, <code>blue</code>, <code>yellow</code>"
            elif key == "COMPRESSION_VIDEO_PIXEL_FORMAT":
                help_text = "Send a pixel format.\n\n<b>Examples:</b> <code>yuv420p</code>, <code>yuv444p</code>, <code>rgb24</code>"
            elif key == "COMPRESSION_VIDEO_TUNE":
                help_text = "Send a tune option.\n\n<b>Examples:</b> <code>film</code>, <code>animation</code>, <code>grain</code>, <code>stillimage</code>, <code>fastdecode</code>, <code>zerolatency</code>"
            elif key in {"COMPRESSION_ARCHIVE_METHOD", "CONVERT_ARCHIVE_METHOD"}:
                help_text = "Send a compression method.\n\n<b>Examples:</b> <code>deflate</code>, <code>store</code>, <code>bzip2</code>, <code>lzma</code>"
            elif key == "COMPRESSION_ARCHIVE_PASSWORD":
                help_text = "Set a password to protect the archive. Leave as 'none' for no password protection.\nNote: Password protection only works with 7z, zip, and rar formats.\n\n<b>Examples:</b> <code>mySecurePassword123</code>, <code>none</code>"
            elif key == "COMPRESSION_ARCHIVE_ALGORITHM":
                help_text = "Set the archive algorithm. Options: 7z, zip, tar, rar, etc.\n\n<b>Examples:</b> <code>7z</code> - best compression, supports password protection\n<code>zip</code> - more compatible, supports password protection\n<code>tar</code> - good for preserving file permissions (no password support)"
            elif key == "CONVERT_ARCHIVE_LEVEL":
                help_text = "Send the compression level (0-9). Higher values mean better compression but slower speed.\n\n<b>Examples:</b> <code>6</code>, <code>9</code>"
            elif key in {"WATERMARK_FONT", "MERGE_SUBTITLE_FONT"}:
                help_text = "Send font file name. The font file should be available in the bot's directory.\n\n<b>Examples:</b> <code>Arial.ttf</code>, <code>default.otf</code>"
            elif key in {
                "MERGE_OUTPUT_FORMAT_VIDEO",
                "CONVERT_VIDEO_FORMAT",
                "EXTRACT_VIDEO_FORMAT",
            }:
                help_text = "Send video output format.\n\n<b>Examples:</b> <code>mp4</code>, <code>mkv</code>, <code>avi</code>"
            elif key in {
                "MERGE_OUTPUT_FORMAT_AUDIO",
                "CONVERT_AUDIO_FORMAT",
                "EXTRACT_AUDIO_FORMAT",
            }:
                help_text = "Send audio output format.\n\n<b>Examples:</b> <code>mp3</code>, <code>aac</code>, <code>flac</code>"
            elif key in {"EXTRACT_SUBTITLE_FORMAT", "CONVERT_SUBTITLE_FORMAT"}:
                help_text = "Send subtitle output format.\n\n<b>Examples:</b> <code>srt</code>, <code>ass</code>, <code>vtt</code>"
            elif key == "CONVERT_DOCUMENT_FORMAT":
                help_text = "Send document output format.\n\n<b>Examples:</b> <code>pdf</code>, <code>docx</code>, <code>txt</code>"
            elif key == "CONVERT_ARCHIVE_FORMAT":
                help_text = "Send archive output format.\n\n<b>Examples:</b> <code>zip</code>, <code>rar</code>, <code>7z</code>, <code>tar</code>"
            elif key == "EXTRACT_ATTACHMENT_FORMAT":
                help_text = "Send attachment output format.\n\n<b>Examples:</b> <code>png</code>, <code>jpg</code>, <code>pdf</code>"
            elif key == "EXTRACT_PRIORITY":
                help_text = "Send an integer value for extract priority. Lower values mean higher priority.\n\n<b>Example:</b> <code>6</code>"
            elif key in {"EXTRACT_DELETE_ORIGINAL", "CONVERT_DELETE_ORIGINAL"}:
                help_text = "Send 'true' to delete original files after processing or 'false' to keep them.\n\n<b>Examples:</b> <code>true</code> or <code>false</code>"
            elif key == "EXTRACT_VIDEO_INDEX":
                help_text = "Send the video track index to extract. Use comma-separated values for multiple tracks or 'all' for all tracks.\n\n<b>Examples:</b> <code>0</code>, <code>0,1,2</code>, or <code>all</code>"
            elif key == "EXTRACT_AUDIO_INDEX":
                help_text = "Send the audio track index to extract. Use comma-separated values for multiple tracks or 'all' for all tracks.\n\n<b>Examples:</b> <code>0</code>, <code>0,1,2</code>, or <code>all</code>"
            elif key == "EXTRACT_SUBTITLE_INDEX":
                help_text = "Send the subtitle track index to extract. Use comma-separated values for multiple tracks or 'all' for all tracks.\n\n<b>Examples:</b> <code>0</code>, <code>0,1,2</code>, or <code>all</code>"
            elif key == "EXTRACT_ATTACHMENT_INDEX":
                help_text = "Send the attachment index to extract. Use comma-separated values for multiple indices or 'all' for all attachments.\n\n<b>Examples:</b> <code>0</code>, <code>0,1,2</code>, or <code>all</code>"
            elif key == "EXTRACT_VIDEO_CODEC":
                help_text = "Send the video codec to use for extraction.\n\n<b>Examples:</b> <code>copy</code>, <code>h264</code>, <code>libx264</code>"
            elif key == "EXTRACT_AUDIO_CODEC":
                help_text = "Send the audio codec to use for extraction.\n\n<b>Examples:</b> <code>copy</code>, <code>aac</code>, <code>mp3</code>"
            elif key == "EXTRACT_SUBTITLE_CODEC":
                help_text = "Send the subtitle codec to use for extraction.\n\n<b>Examples:</b> <code>copy</code>, <code>srt</code>, <code>ass</code>"
            elif key == "EXTRACT_VIDEO_QUALITY":
                help_text = "Send the video quality setting for extraction.\n\n<b>Examples:</b> <code>high</code>, <code>medium</code>, <code>low</code>"
            elif key == "EXTRACT_VIDEO_PRESET":
                help_text = "Send the video preset for extraction.\n\n<b>Examples:</b> <code>ultrafast</code>, <code>veryfast</code>, <code>medium</code>, <code>slow</code>, <code>veryslow</code>"
            elif key == "EXTRACT_VIDEO_BITRATE":
                help_text = "Send the video bitrate for extraction.\n\n<b>Examples:</b> <code>5M</code>, <code>10M</code>, <code>20M</code>"
            elif key in {"EXTRACT_VIDEO_RESOLUTION", "CONVERT_VIDEO_RESOLUTION"}:
                help_text = "Send the video resolution for processing.\n\n<b>Examples:</b> <code>1920x1080</code>, <code>1280x720</code>, <code>720p</code>, <code>1080p</code>"
            elif key in {"EXTRACT_VIDEO_FPS", "CONVERT_VIDEO_FPS"}:
                help_text = "Send the video frame rate for processing.\n\n<b>Examples:</b> <code>30</code>, <code>60</code>, <code>24</code>"
            elif key == "CONVERT_DOCUMENT_QUALITY":
                help_text = "Send the document quality for conversion (1-100). Higher values mean better quality.\n\n<b>Examples:</b> <code>90</code>, <code>75</code>"
            elif key in {"COMPRESSION_DOCUMENT_DPI", "CONVERT_DOCUMENT_DPI"}:
                help_text = "Send the document DPI (dots per inch) for processing. Higher values mean better quality.\n\n<b>Examples:</b> <code>300</code>, <code>600</code>"
            elif key == "EXTRACT_AUDIO_BITRATE":
                help_text = "Send the audio bitrate for extraction.\n\n<b>Examples:</b> <code>128k</code>, <code>192k</code>, <code>320k</code>"
            elif key == "EXTRACT_AUDIO_CHANNELS":
                help_text = "Send the number of audio channels for extraction.\n\n<b>Examples:</b> <code>2</code> (stereo), <code>6</code> (5.1 surround)"
            elif key == "EXTRACT_AUDIO_SAMPLING":
                help_text = "Send the audio sampling rate for extraction.\n\n<b>Examples:</b> <code>44100</code> (CD quality), <code>48000</code> (DVD quality)"
            elif key == "EXTRACT_AUDIO_VOLUME":
                help_text = "Send the audio volume adjustment for extraction.\n\n<b>Examples:</b> <code>1.0</code> (normal), <code>1.5</code> (louder), <code>0.5</code> (quieter)"
            elif key == "EXTRACT_SUBTITLE_LANGUAGE":
                help_text = "Send the subtitle language code for extraction.\n\n<b>Examples:</b> <code>eng</code> (English), <code>spa</code> (Spanish), <code>fre</code> (French)"
            elif key == "EXTRACT_SUBTITLE_ENCODING":
                help_text = "Send the subtitle character encoding for extraction.\n\n<b>Examples:</b> <code>utf-8</code>, <code>ascii</code>, <code>latin1</code>"
            elif key == "EXTRACT_SUBTITLE_FONT":
                help_text = "Send the subtitle font for extraction (for formats that support it).\n\n<b>Examples:</b> <code>Arial</code>, <code>Times New Roman</code>, <code>Helvetica</code>"
            elif key == "EXTRACT_SUBTITLE_FONT_SIZE":
                help_text = "Send the subtitle font size for extraction.\n\n<b>Examples:</b> <code>24</code>, <code>32</code>, <code>18</code>"
            elif key == "EXTRACT_ATTACHMENT_FILTER":
                help_text = "Send a filter pattern for attachment extraction.\n\n<b>Examples:</b> <code>*.jpg</code>, <code>*.pdf</code>, <code>image*</code>"
            elif key == "EXTRACT_MAINTAIN_QUALITY":
                help_text = "Send 'true' to maintain high quality during extraction or 'false' to optimize for size.\n\n<b>Examples:</b> <code>true</code> or <code>false</code>"
            # Remove Settings Help Text
            elif key == "REMOVE_PRIORITY":
                help_text = "Send an integer value for remove priority. Lower values mean higher priority.\n\n<b>Example:</b> <code>8</code>"
            elif key in {
                "REMOVE_DELETE_ORIGINAL",
                "REMOVE_METADATA",
                "REMOVE_MAINTAIN_QUALITY",
            }:
                if key == "REMOVE_DELETE_ORIGINAL":
                    help_text = "Send 'true' to delete original files after processing or 'false' to keep them.\n\n<b>Examples:</b> <code>true</code> or <code>false</code>"
                elif key == "REMOVE_METADATA":
                    help_text = "Send 'true' to remove metadata from media files or 'false' to keep metadata.\n\n<b>Examples:</b> <code>true</code> or <code>false</code>"
                elif key == "REMOVE_MAINTAIN_QUALITY":
                    help_text = "Send 'true' to maintain high quality during removal or 'false' to optimize for size.\n\n<b>Examples:</b> <code>true</code> or <code>false</code>"
            elif key == "REMOVE_VIDEO_INDEX":
                help_text = "Send the video track index to remove. Use comma-separated values for multiple tracks or 'all' for all tracks.\n\n<b>Examples:</b> <code>0</code>, <code>0,1,2</code>, or <code>all</code>"
            elif key == "REMOVE_AUDIO_INDEX":
                help_text = "Send the audio track index to remove. Use comma-separated values for multiple tracks or 'all' for all tracks.\n\n<b>Examples:</b> <code>0</code>, <code>0,1,2</code>, or <code>all</code>"
            elif key == "REMOVE_SUBTITLE_INDEX":
                help_text = "Send the subtitle track index to remove. Use comma-separated values for multiple tracks or 'all' for all tracks.\n\n<b>Examples:</b> <code>0</code>, <code>0,1,2</code>, or <code>all</code>"
            elif key == "REMOVE_ATTACHMENT_INDEX":
                help_text = "Send the attachment index to remove. Use comma-separated values for multiple indices or 'all' for all attachments.\n\n<b>Examples:</b> <code>0</code>, <code>0,1,2</code>, or <code>all</code>"
            elif key == "REMOVE_VIDEO_CODEC":
                help_text = "Send the video codec to use for removal processing.\n\n<b>Examples:</b> <code>copy</code>, <code>h264</code>, <code>libx264</code>"
            elif key == "REMOVE_AUDIO_CODEC":
                help_text = "Send the audio codec to use for removal processing.\n\n<b>Examples:</b> <code>copy</code>, <code>aac</code>, <code>mp3</code>"
            elif key == "REMOVE_SUBTITLE_CODEC":
                help_text = "Send the subtitle codec to use for removal processing.\n\n<b>Examples:</b> <code>copy</code>, <code>srt</code>, <code>ass</code>"
            elif key in {
                "REMOVE_VIDEO_FORMAT",
                "REMOVE_AUDIO_FORMAT",
                "REMOVE_SUBTITLE_FORMAT",
                "REMOVE_ATTACHMENT_FORMAT",
            }:
                if key == "REMOVE_VIDEO_FORMAT":
                    help_text = "Send video output format for removal processing.\n\n<b>Examples:</b> <code>mp4</code>, <code>mkv</code>, <code>avi</code>"
                elif key == "REMOVE_AUDIO_FORMAT":
                    help_text = "Send audio output format for removal processing.\n\n<b>Examples:</b> <code>mp3</code>, <code>aac</code>, <code>flac</code>"
                elif key == "REMOVE_SUBTITLE_FORMAT":
                    help_text = "Send subtitle output format for removal processing.\n\n<b>Examples:</b> <code>srt</code>, <code>ass</code>, <code>vtt</code>"
                elif key == "REMOVE_ATTACHMENT_FORMAT":
                    help_text = "Send attachment output format for removal processing.\n\n<b>Examples:</b> <code>png</code>, <code>jpg</code>, <code>pdf</code>"
            elif key == "REMOVE_VIDEO_QUALITY":
                help_text = "Send the video quality setting for removal processing.\n\n<b>Examples:</b> <code>high</code>, <code>medium</code>, <code>low</code>"
            elif key == "REMOVE_VIDEO_PRESET":
                help_text = "Send the video preset for removal processing.\n\n<b>Examples:</b> <code>ultrafast</code>, <code>veryfast</code>, <code>medium</code>, <code>slow</code>, <code>veryslow</code>"
            elif key == "REMOVE_VIDEO_BITRATE":
                help_text = "Send the video bitrate for removal processing.\n\n<b>Examples:</b> <code>5M</code>, <code>10M</code>, <code>20M</code>"
            elif key in {"REMOVE_VIDEO_RESOLUTION", "REMOVE_VIDEO_FPS"}:
                if key == "REMOVE_VIDEO_RESOLUTION":
                    help_text = "Send the video resolution for removal processing.\n\n<b>Examples:</b> <code>1920x1080</code>, <code>1280x720</code>, <code>720p</code>, <code>1080p</code>"
                elif key == "REMOVE_VIDEO_FPS":
                    help_text = "Send the video frame rate for removal processing.\n\n<b>Examples:</b> <code>30</code>, <code>60</code>, <code>24</code>"
            elif key == "REMOVE_AUDIO_BITRATE":
                help_text = "Send the audio bitrate for removal processing.\n\n<b>Examples:</b> <code>128k</code>, <code>192k</code>, <code>320k</code>"
            elif key == "REMOVE_AUDIO_CHANNELS":
                help_text = "Send the number of audio channels for removal processing.\n\n<b>Examples:</b> <code>2</code> (stereo), <code>6</code> (5.1 surround)"
            elif key == "REMOVE_AUDIO_SAMPLING":
                help_text = "Send the audio sampling rate for removal processing.\n\n<b>Examples:</b> <code>44100</code> (CD quality), <code>48000</code> (DVD quality)"
            elif key == "REMOVE_AUDIO_VOLUME":
                help_text = "Send the audio volume adjustment for removal processing.\n\n<b>Examples:</b> <code>1.0</code> (normal), <code>1.5</code> (louder), <code>0.5</code> (quieter)"
            elif key == "REMOVE_SUBTITLE_LANGUAGE":
                help_text = "Send the subtitle language code for removal processing.\n\n<b>Examples:</b> <code>eng</code> (English), <code>spa</code> (Spanish), <code>fre</code> (French)"
            elif key == "REMOVE_SUBTITLE_ENCODING":
                help_text = "Send the subtitle character encoding for removal processing.\n\n<b>Examples:</b> <code>utf-8</code>, <code>ascii</code>, <code>latin1</code>"
            elif key == "REMOVE_SUBTITLE_FONT":
                help_text = "Send the subtitle font for removal processing (for formats that support it).\n\n<b>Examples:</b> <code>Arial</code>, <code>Times New Roman</code>, <code>Helvetica</code>"
            elif key == "REMOVE_SUBTITLE_FONT_SIZE":
                help_text = "Send the subtitle font size for removal processing.\n\n<b>Examples:</b> <code>24</code>, <code>32</code>, <code>18</code>"
            elif key == "REMOVE_ATTACHMENT_FILTER":
                help_text = "Send a filter pattern for attachment removal processing.\n\n<b>Examples:</b> <code>*.jpg</code>, <code>*.pdf</code>, <code>image*</code>"
            elif key == "MERGE_OUTPUT_FORMAT_IMAGE":
                help_text = "Send image output format.\n\n<b>Examples:</b> <code>jpg</code>, <code>png</code>, <code>webp</code>"
            elif key == "MERGE_OUTPUT_FORMAT_DOCUMENT":
                help_text = "Send document output format.\n\n<b>Examples:</b> <code>pdf</code>, <code>docx</code>, <code>txt</code>"
            elif key == "MERGE_OUTPUT_FORMAT_SUBTITLE":
                help_text = "Send subtitle output format.\n\n<b>Examples:</b> <code>srt</code>, <code>ass</code>, <code>vtt</code>"
            elif key in {
                "MERGE_VIDEO_CODEC",
                "CONVERT_VIDEO_CODEC",
                "COMPRESSION_VIDEO_CODEC",
            }:
                help_text = "Send video codec.\n\n<b>Examples:</b> <code>h264</code>, <code>h265</code>, <code>libx264</code>, <code>libx265</code>, <code>copy</code>"
            elif key in {"MERGE_VIDEO_QUALITY", "CONVERT_VIDEO_QUALITY"}:
                help_text = "Send video quality.\n\n<b>Examples:</b> <code>high</code>, <code>medium</code>, <code>low</code>"
            elif key in {
                "MERGE_VIDEO_PRESET",
                "CONVERT_VIDEO_PRESET",
                "COMPRESSION_VIDEO_PRESET",
                "COMPRESSION_AUDIO_PRESET",
                "COMPRESSION_IMAGE_PRESET",
                "COMPRESSION_DOCUMENT_PRESET",
                "COMPRESSION_SUBTITLE_PRESET",
                "COMPRESSION_ARCHIVE_PRESET",
            }:
                help_text = "Send preset.\n\n<b>Examples for video:</b> <code>ultrafast</code>, <code>veryfast</code>, <code>medium</code>, <code>slow</code>, <code>veryslow</code>\n\n<b>Examples for other formats:</b> <code>fast</code>, <code>medium</code>, <code>slow</code>"
            elif key in {
                "MERGE_AUDIO_CODEC",
                "CONVERT_AUDIO_CODEC",
                "COMPRESSION_AUDIO_CODEC",
            }:
                help_text = "Send audio codec.\n\n<b>Examples:</b> <code>aac</code>, <code>mp3</code>, <code>libmp3lame</code>, <code>libvorbis</code>, <code>copy</code>"
            elif key in {
                "MERGE_AUDIO_BITRATE",
                "CONVERT_AUDIO_BITRATE",
                "COMPRESSION_AUDIO_BITRATE",
            }:
                help_text = "Send audio bitrate.\n\n<b>Examples:</b> <code>128k</code>, <code>192k</code>, <code>320k</code>"
            elif key in {"MERGE_AUDIO_SAMPLING", "CONVERT_AUDIO_SAMPLING"}:
                help_text = "Send audio sampling rate.\n\n<b>Examples:</b> <code>44100</code> (CD quality), <code>48000</code> (DVD quality)"
            elif key == "WATERMARK_OPACITY":
                help_text = """<b>Watermark Opacity</b>

Send a float value between 0.0 (completely transparent) and 1.0 (completely opaque).

<b>Recommended values:</b>
• <code>0.3</code> - Subtle watermark
• <code>0.5</code> - Medium visibility
• <code>0.8</code> - High visibility
• <code>1.0</code> - Fully opaque"""
            elif key == "AUDIO_WATERMARK_VOLUME":
                help_text = """<b>Audio Watermark Volume</b>

Send a float value between 0.0 (silent) and 1.0 (full volume) for audio watermarks.

<b>Recommended values:</b>
• <code>0.1</code> - Very quiet
• <code>0.3</code> - Subtle background
• <code>0.5</code> - Medium volume
• <code>0.8</code> - Prominent"""
            elif key == "SUBTITLE_WATERMARK_STYLE":
                help_text = """<b>Subtitle Watermark Style</b>

Send a style option for subtitle watermarks.

<b>Options:</b>
• <code>normal</code> - Regular text
• <code>bold</code> - Bold text
• <code>italic</code> - Italic text
• <code>underline</code> - Underlined text"""
            elif key == "IMAGE_WATERMARK_SCALE":
                help_text = """<b>Image Watermark Scale</b>

Send a scale percentage value (1-100) for the image watermark.
Higher values make the watermark larger relative to the original media.

<b>Recommended values:</b>
• <code>5</code> - Small, subtle watermark (5% of original size)
• <code>10</code> - Medium size watermark (10% of original size)
• <code>20</code> - Large, prominent watermark (20% of original size)

<b>Example:</b> <code>10</code>

<b>Note:</b> This applies when using an image file as watermark."""
            elif key == "IMAGE_WATERMARK_OPACITY":
                help_text = """<b>Image Watermark Opacity</b>

Send a float value between 0.0 (completely transparent) and 1.0 (completely opaque).

<b>Recommended values:</b>
• <code>0.3</code> - Very subtle, barely visible
• <code>0.5</code> - Semi-transparent
• <code>0.8</code> - Mostly opaque
• <code>1.0</code> - Fully opaque

<b>Example:</b> <code>0.8</code>

<b>Note:</b> This applies when using an image file as watermark."""
            elif key == "IMAGE_WATERMARK_POSITION":
                help_text = """<b>Image Watermark Position</b>

Send one of the following position options:
• <code>top_left</code> - Place watermark in the top left corner
• <code>top_right</code> - Place watermark in the top right corner
• <code>bottom_left</code> - Place watermark in the bottom left corner
• <code>bottom_right</code> - Place watermark in the bottom right corner (recommended)
• <code>center</code> - Place watermark in the center of the media

<b>Example:</b> <code>bottom_right</code>

<b>Note:</b> This applies when using an image file as watermark."""
            elif key in {"MERGE_AUDIO_VOLUME", "CONVERT_AUDIO_VOLUME"}:
                help_text = "Send audio volume multiplier.\n\n<b>Examples:</b> <code>1.0</code> (normal), <code>1.5</code> (louder), <code>0.5</code> (quieter)"
            elif key == "MERGE_IMAGE_MODE":
                help_text = "Send image mode.\n\n<b>Examples:</b> <code>auto</code>, <code>grid</code>, <code>horizontal</code>, <code>vertical</code>"
            elif key in {"MERGE_IMAGE_RESIZE", "COMPRESSION_IMAGE_RESIZE"}:
                help_text = "Send image resize option.\n\n<b>Examples:</b> <code>none</code>, <code>1080p</code>, <code>720p</code>, <code>480p</code>"
            elif key in {
                "MERGE_SUBTITLE_ENCODING",
                "COMPRESSION_SUBTITLE_ENCODING",
                "CONVERT_SUBTITLE_ENCODING",
            }:
                help_text = "Send subtitle encoding.\n\n<b>Examples:</b> <code>utf-8</code>, <code>ascii</code>, <code>latin1</code>"
            elif key == "CONVERT_SUBTITLE_LANGUAGE":
                help_text = "Send subtitle language code.\n\n<b>Examples:</b> <code>eng</code> (English), <code>spa</code> (Spanish), <code>fre</code> (French)"
            elif key == "MERGE_DOCUMENT_PAPER_SIZE":
                help_text = "Send document paper size.\n\n<b>Examples:</b> <code>a4</code>, <code>letter</code>, <code>legal</code>"
            elif key == "MERGE_DOCUMENT_ORIENTATION":
                help_text = "Send document orientation.\n\n<b>Examples:</b> <code>portrait</code>, <code>landscape</code>"
            elif key in {
                "MERGE_METADATA_TITLE",
                "MERGE_METADATA_AUTHOR",
                "MERGE_METADATA_COMMENT",
                "METADATA_TITLE",
                "METADATA_AUTHOR",
                "METADATA_COMMENT",
            }:
                help_text = "Send metadata text.\n\n<b>Examples:</b> <code>My Video</code>, <code>John Doe</code>, <code>Created with Telegram Bot</code>"
            elif key == "METADATA_KEY":
                help_text = "Send legacy metadata key for backward compatibility.\n\n<b>Example:</b> <code>title=My Video,author=John Doe</code>"
            elif key == "METADATA_ALL":
                help_text = "Send metadata text to apply to all metadata fields.\n\n<b>Example:</b> <code>Created by Telegram Bot</code>"
            elif key == "TASK_MONITOR_INTERVAL":
                help_text = "Send the interval in seconds between task monitoring checks.\n\n<b>Example:</b> <code>60</code> (1 minute)\n\n<b>Default:</b> 60"
            elif key == "TASK_MONITOR_CONSECUTIVE_CHECKS":
                help_text = "Send the number of consecutive checks required to confirm an issue.\n\n<b>Example:</b> <code>3</code>\n\n<b>Default:</b> 3"
            elif key == "TASK_MONITOR_SPEED_THRESHOLD":
                help_text = "Send the download speed threshold in KB/s. Downloads below this speed are considered slow.\n\n<b>Example:</b> <code>50</code>\n\n<b>Default:</b> 50"
            elif key == "TASK_MONITOR_ELAPSED_THRESHOLD":
                help_text = "Send the elapsed time threshold in seconds.\n\n<b>Example:</b> <code>3600</code> (1 hour)\n\n<b>Default:</b> 3600"
            elif key == "TASK_MONITOR_ETA_THRESHOLD":
                help_text = "Send the ETA threshold in seconds.\n\n<b>Example:</b> <code>86400</code> (24 hours)\n\n<b>Default:</b> 86400"
            elif key == "TASK_MONITOR_WAIT_TIME":
                help_text = "Send the wait time in seconds before cancelling a task after warning.\n\n<b>Example:</b> <code>600</code> (10 minutes)\n\n<b>Default:</b> 600"
            elif key == "TASK_MONITOR_COMPLETION_THRESHOLD":
                help_text = "Send the completion time threshold in seconds.\n\n<b>Example:</b> <code>14400</code> (4 hours)\n\n<b>Default:</b> 14400"
            elif key == "TASK_MONITOR_CPU_HIGH":
                help_text = "Send the high CPU threshold percentage.\n\n<b>Example:</b> <code>90</code>\n\n<b>Default:</b> 90"
            elif key == "TASK_MONITOR_CPU_LOW":
                help_text = "Send the low CPU threshold percentage.\n\n<b>Example:</b> <code>40</code>\n\n<b>Default:</b> 40"
            elif key == "TASK_MONITOR_MEMORY_HIGH":
                help_text = "Send the high memory threshold percentage.\n\n<b>Example:</b> <code>75</code>\n\n<b>Default:</b> 75"
            elif key == "TASK_MONITOR_MEMORY_LOW":
                help_text = "Send the low memory threshold percentage.\n\n<b>Example:</b> <code>60</code>\n\n<b>Default:</b> 60"
            elif key == "TRIM_START_TIME":
                help_text = "Send the start time for trimming in HH:MM:SS format.\n\n<b>Example:</b> <code>00:05:30</code> (5 minutes and 30 seconds from start)\n\n<b>Default:</b> <code>00:00:00</code> (beginning of file)"
            elif key == "TRIM_END_TIME":
                help_text = "Send the end time for trimming in HH:MM:SS format. Leave empty for end of file.\n\n<b>Example:</b> <code>00:10:00</code> (10 minutes from start)\n\n<b>Default:</b> Empty (end of file)"
            elif key == "TRIM_DOCUMENT_START_PAGE":
                help_text = "Send the starting page number for document trimming.\n\n<b>Example:</b> <code>5</code> (start from page 5)\n\n<b>Default:</b> <code>1</code> (first page)"
            elif key == "TRIM_DOCUMENT_END_PAGE":
                help_text = "Send the ending page number for document trimming. Leave empty for last page.\n\n<b>Example:</b> <code>10</code> (end at page 10)\n\n<b>Default:</b> Empty (last page)"
            else:
                help_text = f"Send a valid value for <code>{key}</code>."

            msg += f"{help_text}\n\n<b>Current value:</b> <code>{Config.get(key)}</code>\n\n<i>Timeout: 60 seconds</i>"
        elif edit_type == "botvar":
            msg = ""
            buttons.data_button("⬅️ Back", "botset var", "footer")
            if key not in ["TELEGRAM_HASH", "TELEGRAM_API", "OWNER_ID", "BOT_TOKEN"]:
                buttons.data_button("🔄 Default", f"botset resetvar {key}")
            buttons.data_button("❌ Close", "botset close", "footer")
            if key in [
                "CMD_SUFFIX",
                "OWNER_ID",
                "USER_SESSION_STRING",
                "TELEGRAM_HASH",
                "TELEGRAM_API",
                "BOT_TOKEN",
                "TG_PROXY",
            ]:
                msg += "<b>⚠️ Warning:</b> Restart required for this edit to take effect! You will not see the changes in bot vars, the edit will be in database only!\n\n"

            # Add help text for resource management settings
            if key == "PIL_MEMORY_LIMIT":
                msg += "<b>Memory Limit for PIL Operations</b>\n\n"
                msg += "Set the memory limit for PIL (Python Imaging Library) operations in MB. Use 0 for no limit.\n\n"
                msg += "<b>Example:</b> <code>2048</code> (for 2GB limit)\n\n"
                msg += "<b>Note:</b> Setting a reasonable limit can prevent memory issues when processing large images.\n\n"
            elif key == "AUTO_RESTART_ENABLED":
                msg += "<b>Automatic Bot Restart</b>\n\n"
                msg += "Enable or disable automatic bot restart at specified intervals.\n\n"
                msg += "<b>Options:</b>\n"
                msg += "• <code>true</code> - Enable automatic restarts\n"
                msg += "• <code>false</code> - Disable automatic restarts\n\n"
                msg += "<b>Note:</b> Changes will take effect after saving.\n\n"
            elif key == "AUTO_RESTART_INTERVAL":
                msg += "<b>Automatic Restart Interval</b>\n\n"
                msg += (
                    "Set the interval in hours between automatic bot restarts.\n\n"
                )
                msg += "<b>Example:</b> <code>24</code> (for daily restart)\n\n"
                msg += "<b>Note:</b> Minimum value is 1 hour. Regular restarts can help maintain bot stability.\n\n"
            elif key == "STATUS_UPDATE_INTERVAL":
                msg += "<b>Status Update Interval</b>\n\n"
                msg += (
                    "Set how frequently status messages are updated in seconds.\n\n"
                )
                msg += "<b>Examples:</b>\n"
                msg += "• <code>2</code> - Fast updates (may cause FloodWait)\n"
                msg += "• <code>3</code> - Balanced (recommended)\n"
                msg += (
                    "• <code>5</code> - Slower updates (for high-traffic bots)\n\n"
                )
                msg += "<b>Note:</b> Minimum value is 2 seconds. Lower values may trigger Telegram rate limits.\n\n"
            elif key == "TRUECALLER_API_URL":
                msg += "<b>Truecaller API URL</b>\n\n"
                msg += "Set the API URL for Truecaller phone number lookup.\n\n"
                msg += "<b>Example:</b> <code>https://api.example.com/truecaller</code>\n\n"
                msg += "<b>Note:</b> No default URL is provided. You must set your own API endpoint. The Truecaller module will not work until this is configured.\n\n"
            elif key == "DEBRID_LINK_API":
                msg += "<b>Debrid Link API Key</b>\n\n"
                msg += "Set your Debrid Link API key to enable premium link generation for 400+ supported file hosting sites.\n\n"
                msg += "<b>How to get API key:</b>\n"
                msg += "1. Visit https://debrid-link.com\n"
                msg += "2. Register/login to your account\n"
                msg += "3. Go to API section in your account settings\n"
                msg += "4. Generate and copy your API key\n\n"
                msg += (
                    "<b>Example:</b> <code>your_debrid_link_api_key_here</code>\n\n"
                )
                msg += "<b>Supported sites include:</b> 1fichier, Rapidgator, Uploaded, Turbobit, Nitroflare, and 400+ more\n\n"
                msg += "<b>Note:</b> This enables premium direct downloads from supported file hosting services.\n\n"
            # No special handling for MEDIA_TOOLS_ENABLED - it's now managed through the Media Tools menu

            msg += f"Send a valid value for <code>{key}</code>.\n\n<b>Current value:</b> <code>{Config.get(key)}</code>\n\n<i>Timeout: 60 seconds</i>"
        elif edit_type == "ariavar":
            buttons.data_button("⬅️ Back", "botset aria", "footer")
            if key != "newkey":
                buttons.data_button("🗑️ Empty String", f"botset emptyaria {key}")
            buttons.data_button("❌ Close", "botset close", "footer")
            if key == "newkey":
                msg = "Send a key with value.\n\n<b>Example:</b> <code>https-proxy-user:value</code>\n\n<i>Timeout: 60 seconds</i>"
            else:
                msg = f"Send a valid value for <code>{key}</code>.\n\n<b>Current value:</b> <code>{aria2_options[key]}</code>\n\n<i>Timeout: 60 seconds</i>"
        elif edit_type == "qbitvar":
            buttons.data_button("⬅️ Back", "botset qbit", "footer")
            buttons.data_button("🗑️ Empty", f"botset emptyqbit {key}")
            buttons.data_button("❌ Close", "botset close", "footer")
            msg = f"Send a valid value for <code>{key}</code>.\n\n<b>Current value:</b> <code>{qbit_options[key]}</code>\n\n<i>Timeout: 60 seconds</i>"
        elif edit_type == "nzbvar":
            buttons.data_button("⬅️ Back", "botset nzb", "footer")
            buttons.data_button("🔄 Default", f"botset resetnzb {key}")
            buttons.data_button("🗑️ Empty String", f"botset emptynzb {key}")
            buttons.data_button("❌ Close", "botset close", "footer")
            msg = f"Send a valid value for <code>{key}</code>.\n\n<b>Current value:</b> <code>{nzb_options[key]}</code>\n\nIf the value is a list, separate items by space or comma.\n\n<b>Examples:</b> <code>.exe,info</code> or <code>.exe .info</code>\n\n<i>Timeout: 60 seconds</i>"
        elif edit_type.startswith("nzbsevar"):
            index = 0 if key == "newser" else int(edit_type.replace("nzbsevar", ""))
            if key == "newser":
                msg = "Send one server as dictionary {}, like in config.py without []. Timeout: 60 sec"
            else:
                msg = f"Send a valid value for {key} in server {Config.USENET_SERVERS[index]['name']}. Current value is {Config.USENET_SERVERS[index][key]}. Timeout: 60 sec"
    elif key == "var":
        conf_dict = Config.get_all()
        # Filter out watermark, merge configs, metadata, convert, add, task monitor, AI settings, and streamrip settings
        filtered_keys = [
            k
            for k in list(conf_dict.keys())
            if not (
                k.startswith(
                    (
                        "WATERMARK_",
                        "AUDIO_WATERMARK_",
                        "SUBTITLE_WATERMARK_",
                        "IMAGE_WATERMARK_",  # Added IMAGE_WATERMARK_ to exclude image watermark configs
                        "MERGE_",
                        "METADATA_",
                        "CONVERT_",
                        "COMPRESSION_",
                        "TRIM_",
                        "EXTRACT_",
                        "REMOVE_",
                        "ADD_",
                        "SWAP_",  # Added SWAP_ to exclude swap configs from main config menu
                        "SCREENSHOT_",
                        "TASK_MONITOR_",
                        # AI Settings - exclude all AI-related configs from main config menu
                        "MISTRAL_",
                        "DEEPSEEK_",
                        "OPENAI_",
                        "ANTHROPIC_",
                        "GOOGLE_AI_",
                        "GROQ_",
                        "VERTEX_",
                        "AI_",  # Covers all AI_ prefixed settings
                        "STREAMRIP_",  # Added STREAMRIP_ to exclude streamrip configs from main config menu
                        "GALLERY_DL_",  # Added GALLERY_DL_ to exclude gallery-dl configs from main config menu
                        "ZOTIFY_",  # Added ZOTIFY_ to exclude zotify configs from main config menu
                        "YOUTUBE_UPLOAD_",  # Added YOUTUBE_UPLOAD_ to exclude youtube upload configs from main config menu
                        "MEGA_",  # Added MEGA_ to exclude mega configs from main config menu
                        "GOFILE_",  # Added GOFILE_ to exclude gofile configs from main config menu
                        "STREAMTAPE_",  # Added STREAMTAPE_ to exclude streamtape configs from main config menu
                    )
                )
                or k
                in [
                    "CONCAT_DEMUXER_ENABLED",
                    "FILTER_COMPLEX_ENABLED",
                    # AI Settings - exclude individual AI configs from main config menu
                    "DEFAULT_AI_MODEL",
                    "MEDIA_TOOLS_ENABLED",  # Added MEDIA_TOOLS_ENABLED to exclude it from Config menu
                    "YOUTUBE_UPLOAD_ENABLED",  # Keep only the enabled toggle in operations menu
                    "MEGA_ENABLED",  # Keep only the enabled toggle in operations menu
                    "MEGA_UPLOAD_ENABLED",  # Keep only the enabled toggle in operations menu
                    "MEGA_SEARCH_ENABLED",  # Keep only the enabled toggle in mega menu
                    "DDL_DEFAULT_SERVER",  # Keep only in DDL section
                ]
            )
        ]

        # Add resource management settings to the config menu
        resource_keys = [
            "PIL_MEMORY_LIMIT",
            "AUTO_RESTART_ENABLED",
            "AUTO_RESTART_INTERVAL",
            "STATUS_UPDATE_INTERVAL",
        ]

        # Add API settings to the config menu
        api_keys = [
            "TRUECALLER_API_URL",
            "DEBRID_LINK_API",
        ]

        # Add module control settings to the config menu
        module_keys = [
            "AI_ENABLED",
            "IMDB_ENABLED",
            "TRUECALLER_ENABLED",
            "BULK_ENABLED",
            "MULTI_LINK_ENABLED",
            "SAME_DIR_ENABLED",
            "MIRROR_ENABLED",
            "LEECH_ENABLED",
            "TORRENT_ENABLED",
            "YTDLP_ENABLED",
            "NZB_ENABLED",
            "JD_ENABLED",
            "RCLONE_ENABLED",
            # Removed MEDIA_TOOLS_ENABLED from config menu
        ]

        # Add descriptions for module settings
        module_descriptions = {
            "AI_ENABLED": "Enable AI functionality",
            "IMDB_ENABLED": "Enable IMDB functionality",
            "TRUECALLER_ENABLED": "Enable Truecaller functionality",
            "BULK_ENABLED": "Enable Bulk Operations (-b flag)",
            "MULTI_LINK_ENABLED": "Enable Multi-Link Operations",
            "SAME_DIR_ENABLED": "Enable Same Directory Operations (-m flag)",
            "MIRROR_ENABLED": "Enable Mirror Operations",
            "LEECH_ENABLED": "Enable Leech Operations",
            "TORRENT_ENABLED": "Enable Torrent Operations",
            "YTDLP_ENABLED": "Enable YT-DLP Operations",
            "NZB_ENABLED": "Enable NZB Operations",
            "JD_ENABLED": "Enable JDownloader Operations",
            "RCLONE_ENABLED": "Enable Rclone Operations",
            # Removed MEDIA_TOOLS_ENABLED description
        }

        # Ensure resource keys are in the filtered keys list
        for rk in resource_keys:
            if rk not in filtered_keys:
                filtered_keys.append(rk)

        # Ensure API keys are in the filtered keys list
        for ak in api_keys:
            if ak not in filtered_keys:
                filtered_keys.append(ak)

        # Ensure module keys are in the filtered keys list
        for mk in module_keys:
            if mk not in filtered_keys:
                filtered_keys.append(mk)

        # Sort the keys alphabetically
        filtered_keys.sort()

        for k in filtered_keys[start : 10 + start]:
            if False:
                continue

            # Always use editvar for Config variables to ensure consistent behavior
            callback = f"botset editvar {k}"

            # Highlight resource management settings
            if k in resource_keys:
                buttons.data_button(f"⚙️ {k}", callback)
            # Highlight API settings
            elif k in api_keys:
                buttons.data_button(f"🔌 {k}", callback)
            # Highlight module control settings
            elif k in module_keys:
                # Use the module descriptions for better display
                description = module_descriptions.get(k, k)
                Config.get(k)

                buttons.data_button(f"🧩 {k}", callback)
            else:
                buttons.data_button(k, callback)
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit var")
        else:
            buttons.data_button("👁️ View", "botset view var")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        for x in range(0, len(filtered_keys), 10):
            buttons.data_button(
                f"{int(x / 10) + 1}",
                f"botset start var {x}",
                position="footer",
            )

        msg = (
            f"<b>Config Variables</b> | Page: {int(start / 10) + 1} | State: {state}"
        )
    elif key == "private":
        # Get available private files
        available_files = await database.get_private_files()

        # Create universal buttons for private files management
        buttons.data_button("📤 Set Files", "botset private_set")
        buttons.data_button("👁️ View Files", "botset private_view")
        buttons.data_button("🗑️ Delete Files", "botset private_delete")
        buttons.data_button("🔄 Sync to DB", "botset private_sync_db")
        buttons.data_button("💾 Sync to FS", "botset private_sync_fs")

        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Create status message showing which files exist
        file_status = []
        files_need_sync_to_db = 0
        files_need_sync_to_fs = 0
        known_files = [
            ("config.py", "🔧 Config"),
            ("token.pickle", "🔑 Token"),
            ("token_sa.pickle", "🔑 SA Token"),
            ("youtube_token.pickle", "📺 YouTube Token"),
            ("rclone.conf", "☁️ Rclone Config"),
            ("accounts.zip", "📁 Service Accounts"),
            ("list_drives.txt", "📋 Drive List"),
            ("cookies.txt", "🍪 Cookies"),
            (".netrc", "🔐 Netrc"),
            ("shorteners.txt", "🔗 Shorteners"),
            ("streamrip_config.toml", "🎵 Streamrip Config"),
            ("zotify_credentials.json", "🎧 Zotify Credentials"),
            ("spotify_credentials.json", "🎵 Spotify Credentials"),
        ]

        for file_name, display_name in known_files:
            # All files should be in available_files now
            file_info = available_files.get(
                file_name,
                {
                    "exists_db": False,
                    "exists_fs": False,
                    "accounts_dir_exists": False,
                },
            )

            # Determine base status
            if file_info["exists_db"] and file_info["exists_fs"]:
                status = "✅ DB+FS"
            elif file_info["exists_db"]:
                status = "⚠️ DB"  # Highlight files that need syncing to FS
                files_need_sync_to_fs += 1
            elif file_info["exists_fs"]:
                status = "⚠️ FS"  # Highlight files that need syncing to DB
                files_need_sync_to_db += 1
            else:
                status = "❌"

            # Special handling for accounts.zip - also check accounts directory
            if file_name == "accounts.zip":
                accounts_dir_exists = file_info.get("accounts_dir_exists", False)
                if accounts_dir_exists:
                    if status == "❌":
                        status = "✅ DIR"  # Only directory exists
                    else:
                        status += "+DIR"  # File + directory exists

            file_status.append(f"• {display_name}: {status}")

        sync_warnings = []
        if files_need_sync_to_db > 0:
            sync_warnings.append(
                f"⚠️ <b>{files_need_sync_to_db} file(s) need syncing to database!</b>"
            )
        if files_need_sync_to_fs > 0:
            sync_warnings.append(
                f"⚠️ <b>{files_need_sync_to_fs} file(s) need syncing to filesystem!</b>"
            )

        sync_warning = "\n" + "\n".join(sync_warnings) if sync_warnings else ""

        msg = f"""<b>🔒 Private Files Management</b>

<b>File Status:</b>
{chr(10).join(file_status)}{sync_warning}

<b>Actions:</b>
• <b>📤 Set Files:</b> Upload new private files
• <b>👁️ View Files:</b> Download existing files
• <b>🗑️ Delete Files:</b> Remove private files
• <b>🔄 Sync to DB:</b> Backup filesystem files to database
• <b>💾 Sync to FS:</b> Restore database files to filesystem

<b>Legend:</b>
• ✅ DB+FS: Available in database and filesystem
• ⚠️ DB: Available in database only (⚠️ Not in filesystem)
• ⚠️ FS: Available in filesystem only (⚠️ Not backed up)
• ✅ DIR: Directory exists (accounts.zip)
• ❌: Not available

<b>Note:</b>
• Changing .netrc will not take effect for aria2c until restart
• streamrip_config.toml will be used for custom streamrip configuration
• zotify_credentials.json will be used for Spotify authentication
• youtube_token.pickle will be used for YouTube uploads
• Files showing ⚠️ should be synced for complete backup/restore"""
    elif key == "aria":
        for k in list(aria2_options.keys())[start : 10 + start]:
            buttons.data_button(k, f"botset ariavar {k}")
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit aria")
        else:
            buttons.data_button("👁️ View", "botset view aria")
        buttons.data_button("➕ Add Option", "botset ariavar newkey")
        buttons.data_button("🔄 Sync Aria2c", "botset syncaria")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        for x in range(0, len(aria2_options), 10):
            buttons.data_button(
                f"{int(x / 10) + 1}",
                f"botset start aria {x}",
                position="footer",
            )
        msg = f"<b>Aria2c Options</b> | Page: {int(start / 10) + 1}/{(len(aria2_options) + 9) // 10} | State: {state}"
    elif key == "qbit":
        for k in list(qbit_options.keys())[start : 10 + start]:
            buttons.data_button(k, f"botset qbitvar {k}")
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit qbit")
        else:
            buttons.data_button("👁️ View", "botset view qbit")
        buttons.data_button("🔄 Sync qBittorrent", "botset syncqbit")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        for x in range(0, len(qbit_options), 10):
            buttons.data_button(
                f"{int(x / 10) + 1}",
                f"botset start qbit {x}",
                position="footer",
            )
        msg = f"<b>qBittorrent Options</b> | Page: {int(start / 10) + 1}/{(len(qbit_options) + 9) // 10} | State: {state}"
    elif key == "nzb":
        for k in list(nzb_options.keys())[start : 10 + start]:
            buttons.data_button(k, f"botset nzbvar {k}")
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit nzb")
        else:
            buttons.data_button("👁️ View", "botset view nzb")
        buttons.data_button("🖥️ Servers", "botset nzbserver")
        buttons.data_button("🔄 Sync Sabnzbd", "botset syncnzb")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        for x in range(0, len(nzb_options), 10):
            buttons.data_button(
                f"{int(x / 10) + 1}",
                f"botset start nzb {x}",
                position="footer",
            )
        msg = f"<b>Sabnzbd Options</b> | Page: {int(start / 10) + 1}/{(len(nzb_options) + 9) // 10} | State: {state}"

    elif key == "nzbserver":
        if len(Config.USENET_SERVERS) > 0:
            for index, k in enumerate(Config.USENET_SERVERS[start : 10 + start]):
                buttons.data_button(f"🖥️ {k['name']}", f"botset nzbser{index}")
        buttons.data_button("➕ Add New Server", "botset nzbsevar newser")
        buttons.data_button("⬅️ Back", "botset nzb", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        if len(Config.USENET_SERVERS) > 10:
            for x in range(0, len(Config.USENET_SERVERS), 10):
                buttons.data_button(
                    f"{int(x / 10) + 1}",
                    f"botset start nzbser {x}",
                    position="footer",
                )
        msg = f"<b>Usenet Servers</b> | Page: {int(start / 10) + 1}/{(len(Config.USENET_SERVERS) + 9) // 10} | State: {state}"
    elif key.startswith("nzbser"):
        index = int(key.replace("nzbser", ""))
        # Check if index is valid before accessing Config.USENET_SERVERS
        if 0 <= index < len(Config.USENET_SERVERS):
            server_name = Config.USENET_SERVERS[index].get("name", f"Server {index}")
            for k in list(Config.USENET_SERVERS[index].keys())[start : 10 + start]:
                buttons.data_button(k, f"botset nzbsevar{index} {k}")
            if state == "view":
                buttons.data_button("✏️ Edit", f"botset edit {key}")
            else:
                buttons.data_button("👁️ View", f"botset view {key}")
            buttons.data_button("🗑️ Remove Server", f"botset remser {index}")
            buttons.data_button("⬅️ Back", "botset nzbserver", "footer")
            buttons.data_button("❌ Close", "botset close", "footer")
            if len(Config.USENET_SERVERS[index].keys()) > 10:
                for x in range(0, len(Config.USENET_SERVERS[index]), 10):
                    buttons.data_button(
                        f"{int(x / 10) + 1}",
                        f"botset start {key} {x}",
                        position="footer",
                    )
            msg = f"<b>Server: {server_name}</b> | Page: {int(start / 10) + 1}/{(len(Config.USENET_SERVERS[index].keys()) + 9) // 10} | State: {state}"
        else:
            # Handle invalid index
            buttons.data_button("⬅️ Back", "botset nzbserver", "footer")
            buttons.data_button("❌ Close", "botset close", "footer")
            msg = "<b>Error:</b> Invalid server index. Please go back and try again."
    elif key == "mediatools":
        # Force refresh Config.MEDIA_TOOLS_ENABLED from database to ensure accurate status
        if hasattr(Config, "MEDIA_TOOLS_ENABLED"):
            try:
                # Check if database is connected and db attribute exists
                if (
                    database.db is not None
                    and hasattr(database, "db")
                    and hasattr(database.db, "settings")
                ):
                    db_config = await database.db.settings.config.find_one(
                        {"_id": TgClient.ID},
                        {"MEDIA_TOOLS_ENABLED": 1, "_id": 0},
                    )
                    if db_config and "MEDIA_TOOLS_ENABLED" in db_config:
                        # Update the Config object with the current value from database
                        db_value = db_config["MEDIA_TOOLS_ENABLED"]
                        if db_value != Config.MEDIA_TOOLS_ENABLED:
                            Config.MEDIA_TOOLS_ENABLED = db_value
                else:
                    pass

            except Exception:
                pass

        # Create a new ButtonMaker instance to avoid duplicate buttons
        buttons = ButtonMaker()

        # Always show the Configure Tools button, regardless of whether tools are enabled
        buttons.data_button("⚙️ Configure Tools", "botset configure_tools")

        # Get list of enabled tools
        enabled_tools = []
        if isinstance(Config.MEDIA_TOOLS_ENABLED, str):
            if "," in Config.MEDIA_TOOLS_ENABLED:
                enabled_tools = [
                    t.strip()
                    for t in Config.MEDIA_TOOLS_ENABLED.split(",")
                    if t.strip()
                ]
            elif Config.MEDIA_TOOLS_ENABLED.strip():
                enabled_tools = [Config.MEDIA_TOOLS_ENABLED.strip()]
        elif Config.MEDIA_TOOLS_ENABLED is True:
            enabled_tools = [
                "watermark",
                "merge",
                "convert",
                "compression",
                "trim",
                "extract",
                "add",
                "swap",
                "metadata",
                "xtra",
                "sample",
                "screenshot",
            ]

        # Count enabled tools for display
        total_tools = 11  # Total number of possible tools
        enabled_count = len(enabled_tools)

        # Add navigation buttons at the bottom
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # If no tools are enabled, show a simplified menu
        if not enabled_tools:
            msg = f"<b>Media Tools Settings</b> (0/{total_tools} Enabled)\n\nMedia Tools are currently disabled. Click the Configure Tools button above to enable specific tools."
            return msg, buttons.build_menu(1)

        # Group tools by category for better organization
        # Media Editing Tools
        if is_media_tool_enabled("watermark"):
            buttons.data_button("💧 Watermark", "botset mediatools_watermark")
        if is_media_tool_enabled("merge"):
            buttons.data_button("🔄 Merge", "botset mediatools_merge")
        if is_media_tool_enabled("convert"):
            buttons.data_button("🔄 Convert", "botset mediatools_convert")

        # Media Processing Tools
        if is_media_tool_enabled("compression"):
            buttons.data_button("🗜️ Compression", "botset mediatools_compression")
        if is_media_tool_enabled("trim"):
            buttons.data_button("✂️ Trim", "botset mediatools_trim")
        if is_media_tool_enabled("extract"):
            buttons.data_button("📤 Extract", "botset mediatools_extract")
        if is_media_tool_enabled("remove"):
            buttons.data_button("🗑️ Remove", "botset mediatools_remove")

        # Media Enhancement Tools
        if is_media_tool_enabled("add"):
            buttons.data_button("➕ Add", "botset mediatools_add")
        if is_media_tool_enabled("swap"):
            buttons.data_button("⌬ Swap", "botset mediatools_swap")
        if is_media_tool_enabled("metadata"):
            buttons.data_button("📝 Metadata", "botset mediatools_metadata")

        # Count enabled tools for display
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
        enabled_count = len(enabled_tools)
        total_count = len(all_tools)

        msg = f"""<b>Media Tools Settings</b>

Configure global settings for media processing tools.

<b>Enabled Tools:</b> {enabled_count}/{total_count}

<b>How to Enable/Disable Tools:</b>
• Click the <b>⚙️ Configure Tools</b> button above
• Use the toggle buttons to enable or disable specific tools
• You can also use the Enable All or Disable All buttons

<b>Available Categories:</b>
• <b>Watermark</b> - Add text or image watermarks to media files
• <b>Merge</b> - Combine multiple files into a single output
• <b>Convert</b> - Change file formats (video, audio, images, etc.)
• <b>Compression</b> - Reduce file sizes while preserving quality
• <b>Trim</b> - Cut sections from media files
• <b>Extract</b> - Extract components from media files
• <b>Remove</b> - Remove tracks or metadata from media files
• <b>Add</b> - Add elements to media files
• <b>Screenshot</b> - Take screenshots from videos (enabled via -ss flag)
• <b>Metadata</b> - Modify file metadata

Select a tool category to configure its settings."""
    elif key == "ai":
        # Enhanced AI Settings Menu with categorized options

        # Main AI Settings Categories - Always show like other settings
        buttons.data_button("🤖 Model Selection", "botset ai_models")
        buttons.data_button("⚙️ Provider Settings", "botset ai_providers")
        buttons.data_button("🔌 Plugin Settings", "botset ai_plugins")
        buttons.data_button("💬 Conversation Settings", "botset ai_conversation")
        buttons.data_button("🎛️ Advanced Settings", "botset ai_advanced")

        # Edit/View mode toggle
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ai")
        else:
            buttons.data_button("👁️ View", "botset view ai")

        buttons.data_button("🔄 Reset All AI Settings", "botset default_ai")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current AI settings status
        default_model = getattr(Config, "DEFAULT_AI_MODEL", "gpt-4o")
        ai_enabled = getattr(Config, "AI_ENABLED", True)

        # Get model info
        model_info = ai_manager.get_model_info(default_model) if ai_manager else None
        (model_info.get("provider", "unknown").upper() if model_info else "UNKNOWN")

        # Get provider status
        providers_status = []
        if getattr(Config, "OPENAI_API_KEY", ""):
            providers_status.append("✅ OpenAI")
        if getattr(Config, "ANTHROPIC_API_KEY", ""):
            providers_status.append("✅ Anthropic")
        if getattr(Config, "GOOGLE_AI_API_KEY", ""):
            providers_status.append("✅ Google AI")
        if getattr(Config, "GROQ_API_KEY", ""):
            providers_status.append("✅ Groq")
        if getattr(Config, "MISTRAL_API_URL", ""):
            providers_status.append("✅ Mistral")
        if getattr(Config, "DEEPSEEK_API_URL", ""):
            providers_status.append("✅ DeepSeek")

        # Get feature status
        plugins_enabled = getattr(Config, "AI_PLUGINS_ENABLED", True)
        multimodal_enabled = getattr(Config, "AI_MULTIMODAL_ENABLED", True)
        streaming_enabled = getattr(Config, "AI_STREAMING_ENABLED", True)
        history_enabled = getattr(Config, "AI_CONVERSATION_HISTORY", True)

        # Get provider info from model
        if ai_manager:
            model_info = ai_manager.get_model_info(default_model)
            default_provider = model_info.get("provider", "unknown").upper()
        else:
            default_provider = "unknown"

        msg = f"""<u><b>🧠 Enhanced AI Settings</b></u>

🎯 <b>Current Configuration:</b>
• Provider: <code>{default_provider}</code>
• Model: <code>{default_model}</code>
• Status: {"✅ Enabled" if ai_enabled else "❌ Disabled"}

🤖 <b>Available Providers:</b>
{chr(10).join(providers_status)}

✨ <b>Features Status:</b>
• 🔌 Plugins: {"✅" if plugins_enabled else "❌"}
• 🎭 Multimodal: {"✅" if multimodal_enabled else "❌"}
• ⚡ Streaming: {"✅" if streaming_enabled else "❌"}
• 💬 History: {"✅" if history_enabled else "❌"}

📝 <b>Configuration:</b>
Select a category above to configure AI settings. Each category contains related options for easy management.

<i>Note: Users can override these settings in their personal settings.</i>"""

    elif key == "ai_models":
        # AI Model Selection Settings - Always show like other settings

        # Core model settings with current values
        default_model = getattr(Config, "DEFAULT_AI_MODEL", "gpt-4o")
        ai_enabled = getattr(Config, "AI_ENABLED", True)

        # Get model info
        model_info = ai_manager.get_model_info(default_model)
        display_name = (
            model_info.get("display_name", default_model)
            if model_info
            else default_model
        )

        # Show settings with current status
        buttons.data_button(
            f"🤖 AI Model: {display_name}", "botset editvar DEFAULT_AI_MODEL"
        )
        ai_status = "✅ ON" if ai_enabled else "❌ OFF"
        buttons.data_button(
            f"🔄 AI Enabled: {ai_status}",
            f"botset toggle AI_ENABLED {not ai_enabled}",
        )

        # Edit/View mode toggle
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ai_models")
        else:
            buttons.data_button("👁️ View", "botset view ai_models")

        buttons.data_button("⬅️ Back", "botset ai", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get provider info from model
        if ai_manager:
            model_info = ai_manager.get_model_info(default_model)
            current_provider = model_info.get("provider", "unknown").upper()
        else:
            current_provider = "unknown"

        msg = f"""<u><b>🤖 AI Model Selection</b></u>

<b>Current Configuration:</b>
• Provider: <code>{current_provider}</code>
• Model: <code>{default_model}</code>
• Status: {"✅ Enabled" if ai_enabled else "❌ Disabled"}

<b>Available Providers:</b>
• GPT (OpenAI) - gpt-3.5-turbo, gpt-4, gpt-4o, o1-preview
• Claude (Anthropic) - claude-3-haiku, claude-3-sonnet, claude-3.5-sonnet
• Gemini (Google) - gemini-1.5-pro, gemini-1.5-flash
• Groq - mixtral-8x7b, llama-3.1-70b

• Mistral/DeepSeek - Legacy providers

<i>Configure your preferred AI provider and model above.</i>"""

    elif key == "ai_providers":
        # AI Provider Settings - Always show like other settings

        # Provider API Keys with status
        openai_key = getattr(Config, "OPENAI_API_KEY", "")
        openai_status = "✅ SET" if openai_key else "❌ NOT SET"
        buttons.data_button(
            f"🔑 OpenAI API Key: {openai_status}", "botset editvar OPENAI_API_KEY"
        )

        anthropic_key = getattr(Config, "ANTHROPIC_API_KEY", "")
        anthropic_status = "✅ SET" if anthropic_key else "❌ NOT SET"
        buttons.data_button(
            f"🔑 Anthropic API Key: {anthropic_status}",
            "botset editvar ANTHROPIC_API_KEY",
        )

        google_key = getattr(Config, "GOOGLE_AI_API_KEY", "")
        google_status = "✅ SET" if google_key else "❌ NOT SET"
        buttons.data_button(
            f"🔑 Google AI API Key: {google_status}",
            "botset editvar GOOGLE_AI_API_KEY",
        )

        groq_key = getattr(Config, "GROQ_API_KEY", "")
        groq_status = "✅ SET" if groq_key else "❌ NOT SET"
        buttons.data_button(
            f"🔑 Groq API Key: {groq_status}", "botset editvar GROQ_API_KEY"
        )

        vertex_project = getattr(Config, "VERTEX_PROJECT_ID", "")
        vertex_status = "✅ SET" if vertex_project else "❌ NOT SET"
        buttons.data_button(
            f"🔑 Vertex Project ID: {vertex_status}",
            "botset editvar VERTEX_PROJECT_ID",
        )

        # Provider API URLs
        buttons.data_button("🌐 OpenAI API URL", "botset editvar OPENAI_API_URL")
        buttons.data_button(
            "🌐 Anthropic API URL", "botset editvar ANTHROPIC_API_URL"
        )
        buttons.data_button(
            "🌐 Google AI API URL", "botset editvar GOOGLE_AI_API_URL"
        )
        buttons.data_button("🌐 Groq API URL", "botset editvar GROQ_API_URL")

        # Legacy providers
        buttons.data_button("🔗 Mistral API URL", "botset editvar MISTRAL_API_URL")
        buttons.data_button("🔗 DeepSeek API URL", "botset editvar DEEPSEEK_API_URL")

        # Edit/View mode toggle
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ai_providers")
        else:
            buttons.data_button("👁️ View", "botset view ai_providers")

        buttons.data_button("⬅️ Back", "botset ai", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get provider status
        openai_key = (
            "✅ Set" if getattr(Config, "OPENAI_API_KEY", "") else "❌ Not Set"
        )
        anthropic_key = (
            "✅ Set" if getattr(Config, "ANTHROPIC_API_KEY", "") else "❌ Not Set"
        )
        google_key = (
            "✅ Set" if getattr(Config, "GOOGLE_AI_API_KEY", "") else "❌ Not Set"
        )
        groq_key = "✅ Set" if getattr(Config, "GROQ_API_KEY", "") else "❌ Not Set"
        vertex_id = (
            "✅ Set" if getattr(Config, "VERTEX_PROJECT_ID", "") else "❌ Not Set"
        )

        msg = f"""<u><b>⚙️ AI Provider Settings</b></u>

<b>API Keys Status:</b>
• OpenAI: {openai_key}
• Anthropic: {anthropic_key}
• Google AI: {google_key}
• Groq: {groq_key}
• Vertex AI: {vertex_id}

<b>Legacy Providers:</b>
• Mistral: {"✅ Set" if getattr(Config, "MISTRAL_API_URL", "") else "❌ Not Set"}
• DeepSeek: {"✅ Set" if getattr(Config, "DEEPSEEK_API_URL", "") else "❌ Not Set"}



<i>Configure your API keys and URLs above. Keep your API keys secure!</i>"""

    elif key == "ai_plugins":
        # AI Plugin Settings - Always show like other settings

        # Main plugin toggle with status
        plugins_enabled = getattr(Config, "AI_PLUGINS_ENABLED", True)
        plugins_status = "✅ ON" if plugins_enabled else "❌ OFF"
        buttons.data_button(
            f"🔌 Plugins Enabled: {plugins_status}",
            f"botset toggle AI_PLUGINS_ENABLED {not plugins_enabled}",
        )

        # Individual plugin settings with status
        web_search = getattr(Config, "AI_WEB_SEARCH_ENABLED", True)
        web_status = "✅ ON" if web_search else "❌ OFF"
        buttons.data_button(
            f"🔍 Web Search: {web_status}",
            f"botset toggle AI_WEB_SEARCH_ENABLED {not web_search}",
        )

        url_summary = getattr(Config, "AI_URL_SUMMARIZATION_ENABLED", True)
        url_status = "✅ ON" if url_summary else "❌ OFF"
        buttons.data_button(
            f"📄 URL Summarization: {url_status}",
            f"botset toggle AI_URL_SUMMARIZATION_ENABLED {not url_summary}",
        )

        arxiv = getattr(Config, "AI_ARXIV_ENABLED", True)
        arxiv_status = "✅ ON" if arxiv else "❌ OFF"
        buttons.data_button(
            f"📚 ArXiv Papers: {arxiv_status}",
            f"botset toggle AI_ARXIV_ENABLED {not arxiv}",
        )

        code_interpreter = getattr(Config, "AI_CODE_INTERPRETER_ENABLED", True)
        code_status = "✅ ON" if code_interpreter else "❌ OFF"
        buttons.data_button(
            f"💻 Code Interpreter: {code_status}",
            f"botset toggle AI_CODE_INTERPRETER_ENABLED {not code_interpreter}",
        )

        image_gen = getattr(Config, "AI_IMAGE_GENERATION_ENABLED", True)
        image_status = "✅ ON" if image_gen else "❌ OFF"
        buttons.data_button(
            f"🎨 Image Generation: {image_status}",
            f"botset toggle AI_IMAGE_GENERATION_ENABLED {not image_gen}",
        )

        voice_transcription = getattr(Config, "AI_VOICE_TRANSCRIPTION_ENABLED", True)
        voice_status = "✅ ON" if voice_transcription else "❌ OFF"
        buttons.data_button(
            f"🎵 Voice Transcription: {voice_status}",
            f"botset toggle AI_VOICE_TRANSCRIPTION_ENABLED {not voice_transcription}",
        )

        # Edit/View mode toggle
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ai_plugins")
        else:
            buttons.data_button("👁️ View", "botset view ai_plugins")

        buttons.data_button("⬅️ Back", "botset ai", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get plugin status
        plugins_enabled = getattr(Config, "AI_PLUGINS_ENABLED", True)
        web_search = getattr(Config, "AI_WEB_SEARCH_ENABLED", True)
        url_summary = getattr(Config, "AI_URL_SUMMARIZATION_ENABLED", True)
        arxiv = getattr(Config, "AI_ARXIV_ENABLED", True)
        code_interpreter = getattr(Config, "AI_CODE_INTERPRETER_ENABLED", True)
        image_gen = getattr(Config, "AI_IMAGE_GENERATION_ENABLED", True)
        voice_transcription = getattr(Config, "AI_VOICE_TRANSCRIPTION_ENABLED", True)

        msg = f"""<u><b>🔌 AI Plugin Settings</b></u>

<b>Plugin System:</b>
• Status: {"✅ Enabled" if plugins_enabled else "❌ Disabled"}

<b>Available Plugins:</b>
• 🔍 Web Search: {"✅" if web_search else "❌"}
• 📄 URL Summarization: {"✅" if url_summary else "❌"}
• 📚 ArXiv Papers: {"✅" if arxiv else "❌"}
• 💻 Code Interpreter: {"✅" if code_interpreter else "❌"}
• 🎨 Image Generation: {"✅" if image_gen else "❌"}
• 🎵 Voice Transcription: {"✅" if voice_transcription else "❌"}

<i>Enable or disable AI plugins above. Plugins extend AI capabilities with external tools.</i>"""

    elif key == "ai_conversation":
        # AI Conversation Settings - Always show like other settings

        # Conversation settings with status
        history_enabled = getattr(Config, "AI_CONVERSATION_HISTORY", True)
        history_status = "✅ ON" if history_enabled else "❌ OFF"
        buttons.data_button(
            f"💬 Conversation History: {history_status}",
            f"botset toggle AI_CONVERSATION_HISTORY {not history_enabled}",
        )

        max_history = getattr(Config, "AI_MAX_HISTORY_LENGTH", 10)
        buttons.data_button(
            f"📝 Max History Length: {max_history}",
            "botset editvar AI_MAX_HISTORY_LENGTH",
        )

        question_prediction = getattr(Config, "AI_QUESTION_PREDICTION", True)
        prediction_status = "✅ ON" if question_prediction else "❌ OFF"
        buttons.data_button(
            f"🔮 Question Prediction: {prediction_status}",
            f"botset toggle AI_QUESTION_PREDICTION {not question_prediction}",
        )

        group_topic = getattr(Config, "AI_GROUP_TOPIC_MODE", False)
        topic_status = "✅ ON" if group_topic else "❌ OFF"
        buttons.data_button(
            f"🎯 Group Topic Mode: {topic_status}",
            f"botset toggle AI_GROUP_TOPIC_MODE {not group_topic}",
        )

        auto_language = getattr(Config, "AI_AUTO_LANGUAGE_DETECTION", True)
        auto_lang_status = "✅ ON" if auto_language else "❌ OFF"
        buttons.data_button(
            f"🌐 Auto Language Detection: {auto_lang_status}",
            f"botset toggle AI_AUTO_LANGUAGE_DETECTION {not auto_language}",
        )

        default_language = getattr(Config, "AI_DEFAULT_LANGUAGE", "en")
        buttons.data_button(
            f"🗣️ Default Language: {default_language}",
            "botset editvar AI_DEFAULT_LANGUAGE",
        )

        # Edit/View mode toggle
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ai_conversation")
        else:
            buttons.data_button("👁️ View", "botset view ai_conversation")

        buttons.data_button("⬅️ Back", "botset ai", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get conversation settings
        history_enabled = getattr(Config, "AI_CONVERSATION_HISTORY", True)
        max_history = getattr(Config, "AI_MAX_HISTORY_LENGTH", 10)
        question_prediction = getattr(Config, "AI_QUESTION_PREDICTION", True)
        group_topic_mode = getattr(Config, "AI_GROUP_TOPIC_MODE", False)
        auto_language = getattr(Config, "AI_AUTO_LANGUAGE_DETECTION", True)
        default_language = getattr(Config, "AI_DEFAULT_LANGUAGE", "en")

        msg = f"""<u><b>💬 AI Conversation Settings</b></u>

<b>Conversation Management:</b>
• History: {"✅ Enabled" if history_enabled else "❌ Disabled"}
• Max History: <code>{max_history}</code> messages
• Question Prediction: {"✅ Enabled" if question_prediction else "❌ Disabled"}
• Group Topic Mode: {"✅ Enabled" if group_topic_mode else "❌ Disabled"}

<b>Language Settings:</b>
• Auto Detection: {"✅ Enabled" if auto_language else "❌ Disabled"}
• Default Language: <code>{default_language}</code>

<i>Configure how AI handles conversations and maintains context.</i>"""

    elif key == "ai_advanced":
        # AI Advanced Settings - Always show like other settings

        # Advanced settings with status
        streaming = getattr(Config, "AI_STREAMING_ENABLED", True)
        streaming_status = "✅ ON" if streaming else "❌ OFF"
        buttons.data_button(
            f"⚡ Streaming Enabled: {streaming_status}",
            f"botset toggle AI_STREAMING_ENABLED {not streaming}",
        )

        multimodal = getattr(Config, "AI_MULTIMODAL_ENABLED", True)
        multimodal_status = "✅ ON" if multimodal else "❌ OFF"
        buttons.data_button(
            f"🎭 Multimodal Enabled: {multimodal_status}",
            f"botset toggle AI_MULTIMODAL_ENABLED {not multimodal}",
        )

        inline_mode = getattr(Config, "AI_INLINE_MODE_ENABLED", True)
        inline_status = "✅ ON" if inline_mode else "❌ OFF"
        buttons.data_button(
            f"📱 Inline Mode Enabled: {inline_status}",
            f"botset toggle AI_INLINE_MODE_ENABLED {not inline_mode}",
        )

        # New ChatGPT-Telegram-Bot Features
        voice_transcription = getattr(Config, "AI_VOICE_TRANSCRIPTION_ENABLED", True)
        voice_status = "✅ ON" if voice_transcription else "❌ OFF"
        buttons.data_button(
            f"🎵 Voice Transcription: {voice_status}",
            f"botset toggle AI_VOICE_TRANSCRIPTION_ENABLED {not voice_transcription}",
        )

        image_generation = getattr(Config, "AI_IMAGE_GENERATION_ENABLED", True)
        image_status = "✅ ON" if image_generation else "❌ OFF"
        buttons.data_button(
            f"🎨 Image Generation: {image_status}",
            f"botset toggle AI_IMAGE_GENERATION_ENABLED {not image_generation}",
        )

        document_processing = getattr(Config, "AI_DOCUMENT_PROCESSING_ENABLED", True)
        doc_status = "✅ ON" if document_processing else "❌ OFF"
        buttons.data_button(
            f"📄 Document Processing: {doc_status}",
            f"botset toggle AI_DOCUMENT_PROCESSING_ENABLED {not document_processing}",
        )

        follow_up_questions = getattr(Config, "AI_FOLLOW_UP_QUESTIONS_ENABLED", True)
        follow_up_status = "✅ ON" if follow_up_questions else "❌ OFF"
        buttons.data_button(
            f"❓ Follow-up Questions: {follow_up_status}",
            f"botset toggle AI_FOLLOW_UP_QUESTIONS_ENABLED {not follow_up_questions}",
        )

        typewriter_effect = getattr(Config, "AI_TYPEWRITER_EFFECT_ENABLED", True)
        typewriter_status = "✅ ON" if typewriter_effect else "❌ OFF"
        buttons.data_button(
            f"⌨️ Typewriter Effect: {typewriter_status}",
            f"botset toggle AI_TYPEWRITER_EFFECT_ENABLED {not typewriter_effect}",
        )

        context_pruning = getattr(Config, "AI_CONTEXT_PRUNING_ENABLED", True)
        pruning_status = "✅ ON" if context_pruning else "❌ OFF"
        buttons.data_button(
            f"🧹 Context Pruning: {pruning_status}",
            f"botset toggle AI_CONTEXT_PRUNING_ENABLED {not context_pruning}",
        )

        max_tokens = getattr(Config, "AI_MAX_TOKENS", 4000)
        buttons.data_button(
            f"🔢 Max Tokens: {max_tokens}", "botset editvar AI_MAX_TOKENS"
        )

        temperature = getattr(Config, "AI_TEMPERATURE", 0.7)
        buttons.data_button(
            f"🌡️ Temperature: {temperature}", "botset editvar AI_TEMPERATURE"
        )

        timeout = getattr(Config, "AI_TIMEOUT", 60)
        buttons.data_button(f"⏱️ Timeout: {timeout}s", "botset editvar AI_TIMEOUT")

        rate_limit = getattr(Config, "AI_RATE_LIMIT_PER_USER", 50)
        buttons.data_button(
            f"⏰ Rate Limit Per User: {rate_limit}/hr",
            "botset editvar AI_RATE_LIMIT_PER_USER",
        )

        # Edit/View mode toggle
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ai_advanced")
        else:
            buttons.data_button("👁️ View", "botset view ai_advanced")

        buttons.data_button("⬅️ Back", "botset ai", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get advanced settings
        streaming_enabled = getattr(Config, "AI_STREAMING_ENABLED", True)
        multimodal_enabled = getattr(Config, "AI_MULTIMODAL_ENABLED", True)
        inline_mode_enabled = getattr(Config, "AI_INLINE_MODE_ENABLED", True)
        voice_transcription_enabled = getattr(
            Config, "AI_VOICE_TRANSCRIPTION_ENABLED", True
        )
        image_generation_enabled = getattr(
            Config, "AI_IMAGE_GENERATION_ENABLED", True
        )
        document_processing_enabled = getattr(
            Config, "AI_DOCUMENT_PROCESSING_ENABLED", True
        )
        follow_up_questions_enabled = getattr(
            Config, "AI_FOLLOW_UP_QUESTIONS_ENABLED", True
        )
        typewriter_effect_enabled = getattr(
            Config, "AI_TYPEWRITER_EFFECT_ENABLED", True
        )
        context_pruning_enabled = getattr(Config, "AI_CONTEXT_PRUNING_ENABLED", True)
        max_tokens = getattr(Config, "AI_MAX_TOKENS", 4096)
        temperature = getattr(Config, "AI_TEMPERATURE", 0.7)
        timeout = getattr(Config, "AI_TIMEOUT", 600)
        rate_limit = getattr(Config, "AI_RATE_LIMIT_PER_USER", 100)

        msg = f"""<u><b>🎛️ AI Advanced Settings</b></u>

<b>Core Features:</b>
• Streaming: {"✅ Enabled" if streaming_enabled else "❌ Disabled"}
• Multimodal: {"✅ Enabled" if multimodal_enabled else "❌ Disabled"}
• Inline Mode: {"✅ Enabled" if inline_mode_enabled else "❌ Disabled"}

<b>New ChatGPT-Telegram-Bot Features:</b>
• Voice Transcription: {"✅ Enabled" if voice_transcription_enabled else "❌ Disabled"}
• Image Generation: {"✅ Enabled" if image_generation_enabled else "❌ Disabled"}
• Document Processing: {"✅ Enabled" if document_processing_enabled else "❌ Disabled"}
• Follow-up Questions: {"✅ Enabled" if follow_up_questions_enabled else "❌ Disabled"}
• Typewriter Effect: {"✅ Enabled" if typewriter_effect_enabled else "❌ Disabled"}
• Context Pruning: {"✅ Enabled" if context_pruning_enabled else "❌ Disabled"}

<b>Performance Settings:</b>
• Max Tokens: <code>{max_tokens}</code>
• Temperature: <code>{temperature}</code>
• Timeout: <code>{timeout}</code> seconds
• Rate Limit: <code>{rate_limit}</code> requests/hour

<i>Advanced settings for fine-tuning AI behavior and performance with ChatGPT-Telegram-Bot features.</i>"""

    elif key == "streamrip":
        # Streamrip Settings section
        buttons.data_button("⚙️ General Settings", "botset streamrip_general")
        buttons.data_button("🎵 Quality & Codec", "botset streamrip_quality")
        buttons.data_button(
            "🔐 Platform Credentials", "botset streamrip_credentials"
        )
        buttons.data_button("📁 Download Settings", "botset streamrip_download")
        buttons.data_button("🎛️ Platform Settings", "botset streamrip_platforms")
        buttons.data_button("🗄️ Database Settings", "botset streamrip_database")
        buttons.data_button("🔄 Conversion Settings", "botset streamrip_conversion")
        buttons.data_button("🏷️ Metadata Settings", "botset streamrip_metadata")
        buttons.data_button("🖥️ CLI Settings", "botset streamrip_cli")
        buttons.data_button("🔧 Advanced Settings", "botset streamrip_advanced")
        buttons.data_button("📄 Config File", "botset streamrip_config")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        msg = "<b>🎵 Streamrip Settings</b>\nSelect a category to configure:"

    elif key == "streamrip_general":
        # General Streamrip Settings
        general_settings = [
            "STREAMRIP_ENABLED",
            "STREAMRIP_AUTO_CONVERT",
        ]

        for setting in general_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in ["STREAMRIP_ENABLED", "STREAMRIP_AUTO_CONVERT"]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit streamrip_general", "footer")
        else:
            buttons.data_button("👁️ View", "botset view streamrip_general", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_general", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current general settings
        enabled = "✅ Enabled" if Config.STREAMRIP_ENABLED else "❌ Disabled"
        auto_convert = (
            "✅ Enabled" if Config.STREAMRIP_AUTO_CONVERT else "❌ Disabled"
        )

        msg = f"""<b>🎵 Streamrip General Settings</b> | State: {state}

<b>Status:</b> {enabled}
<b>Auto Convert:</b> {auto_convert}

<b>Description:</b>
• <b>Enabled:</b> Master toggle for streamrip functionality
• <b>Auto Convert:</b> Automatically convert downloaded files after download

<b>Note:</b>
Other settings like concurrent downloads, search results, and database tracking have been moved to their dedicated sections for better organization."""

    elif key == "streamrip_quality":
        # Quality & Codec Settings
        quality_settings = [
            "STREAMRIP_DEFAULT_QUALITY",
            "STREAMRIP_FALLBACK_QUALITY",
            "STREAMRIP_DEFAULT_CODEC",
            "STREAMRIP_SUPPORTED_CODECS",
            "STREAMRIP_QUALITY_FALLBACK_ENABLED",
        ]

        for setting in quality_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in ["STREAMRIP_QUALITY_FALLBACK_ENABLED"]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit streamrip_quality", "footer")
        else:
            buttons.data_button("👁️ View", "botset view streamrip_quality", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_quality", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current quality settings
        default_quality = Config.STREAMRIP_DEFAULT_QUALITY or "3 (Default)"
        fallback_quality = Config.STREAMRIP_FALLBACK_QUALITY or "2 (Default)"
        default_codec = Config.STREAMRIP_DEFAULT_CODEC or "flac (Default)"
        quality_fallback = (
            "✅ Enabled"
            if Config.STREAMRIP_QUALITY_FALLBACK_ENABLED
            else "❌ Disabled"
        )

        msg = f"""<b>🎵 Streamrip Quality & Codec Settings</b> | State: {state}

<b>Default Quality:</b> <code>{default_quality}</code>
<b>Fallback Quality:</b> <code>{fallback_quality}</code>
<b>Default Codec:</b> <code>{default_codec}</code>
<b>Quality Fallback:</b> {quality_fallback}

<b>Quality Levels:</b>
• <b>0:</b> MP3 320kbps
• <b>1:</b> FLAC 16bit/44.1kHz
• <b>2:</b> FLAC 24bit/96kHz
• <b>3:</b> FLAC 24bit/192kHz (Highest)

<b>Supported Codecs:</b>
• <b>flac:</b> Lossless compression
• <b>mp3:</b> Lossy compression (320kbps)
• <b>m4a:</b> AAC format
• <b>ogg:</b> Ogg Vorbis
• <b>opus:</b> Opus codec"""

    elif key == "streamrip_credentials":
        # Platform Credentials Settings
        credential_settings = [
            "STREAMRIP_QOBUZ_ENABLED",
            "STREAMRIP_QOBUZ_QUALITY",
            "STREAMRIP_QOBUZ_EMAIL",
            "STREAMRIP_QOBUZ_PASSWORD",
            "STREAMRIP_QOBUZ_USE_AUTH_TOKEN",
            "STREAMRIP_QOBUZ_APP_ID",
            "STREAMRIP_QOBUZ_SECRETS",
            "STREAMRIP_TIDAL_ENABLED",
            "STREAMRIP_TIDAL_QUALITY",
            "STREAMRIP_TIDAL_EMAIL",
            "STREAMRIP_TIDAL_PASSWORD",
            "STREAMRIP_TIDAL_ACCESS_TOKEN",
            "STREAMRIP_TIDAL_REFRESH_TOKEN",
            "STREAMRIP_TIDAL_USER_ID",
            "STREAMRIP_TIDAL_COUNTRY_CODE",
            "STREAMRIP_DEEZER_ENABLED",
            "STREAMRIP_DEEZER_QUALITY",
            "STREAMRIP_DEEZER_ARL",
            "STREAMRIP_SOUNDCLOUD_ENABLED",
            "STREAMRIP_SOUNDCLOUD_QUALITY",
            "STREAMRIP_SOUNDCLOUD_CLIENT_ID",
        ]

        for setting in credential_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting.endswith("_ENABLED") or setting in [
                "STREAMRIP_QOBUZ_USE_AUTH_TOKEN"
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For credential settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button(
                "✏️ Edit", "botset edit streamrip_credentials", "footer"
            )
        else:
            buttons.data_button(
                "👁️ View", "botset view streamrip_credentials", "footer"
            )

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_credentials", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current platform status
        qobuz_enabled = (
            "✅ Enabled" if Config.STREAMRIP_QOBUZ_ENABLED else "❌ Disabled"
        )
        qobuz_quality = Config.STREAMRIP_QOBUZ_QUALITY or 3
        tidal_enabled = (
            "✅ Enabled" if Config.STREAMRIP_TIDAL_ENABLED else "❌ Disabled"
        )
        tidal_quality = Config.STREAMRIP_TIDAL_QUALITY or 3
        deezer_enabled = (
            "✅ Enabled" if Config.STREAMRIP_DEEZER_ENABLED else "❌ Disabled"
        )
        deezer_quality = Config.STREAMRIP_DEEZER_QUALITY or 2
        soundcloud_enabled = (
            "✅ Enabled" if Config.STREAMRIP_SOUNDCLOUD_ENABLED else "❌ Disabled"
        )
        soundcloud_quality = Config.STREAMRIP_SOUNDCLOUD_QUALITY or 0

        # Quality descriptions
        quality_map = {
            0: "128 kbps MP3/AAC",
            1: "320 kbps MP3/AAC",
            2: "16/44.1 kHz FLAC",
            3: "24/≤96 kHz FLAC",
            4: "24/≤192 kHz FLAC",
        }

        msg = f"""<b>🎵 Streamrip Platform Credentials</b> | State: {state}

<b>Platform Status & Quality:</b>
• <b>Qobuz:</b> {qobuz_enabled} | Quality: {qobuz_quality} ({quality_map.get(qobuz_quality, "Unknown")})
• <b>Tidal:</b> {tidal_enabled} | Quality: {tidal_quality} ({quality_map.get(tidal_quality, "Unknown")})
• <b>Deezer:</b> {deezer_enabled} | Quality: {deezer_quality} ({quality_map.get(deezer_quality, "Unknown")})
• <b>SoundCloud:</b> {soundcloud_enabled} | Quality: {soundcloud_quality} ({quality_map.get(soundcloud_quality, "Unknown")})

<b>Setup Instructions:</b>
• <b>Qobuz:</b> Enter email and password
• <b>Tidal:</b> Enter username and password
• <b>Deezer:</b> Enter ARL token from browser cookies
• <b>SoundCloud:</b> Enter client ID (optional)

<b>Quality Levels:</b>
• <b>0:</b> 128 kbps MP3/AAC (Basic)
• <b>1:</b> 320 kbps MP3/AAC (High)
• <b>2:</b> 16/44.1 kHz FLAC (CD Quality)
• <b>3:</b> 24/≤96 kHz FLAC (Hi-Res)
• <b>4:</b> 24/≤192 kHz FLAC (Ultra Hi-Res)

<b>Security Note:</b>
All credentials are stored securely in the database and encrypted."""

    elif key == "streamrip_download":
        # Download Settings
        download_settings = [
            "STREAMRIP_CONCURRENT_DOWNLOADS",
            "STREAMRIP_MAX_SEARCH_RESULTS",
            "STREAMRIP_MAX_CONNECTIONS",
            "STREAMRIP_REQUESTS_PER_MINUTE",
            "STREAMRIP_SOURCE_SUBDIRECTORIES",
            "STREAMRIP_DISC_SUBDIRECTORIES",
            "STREAMRIP_CONCURRENCY",
            "STREAMRIP_VERIFY_SSL",
        ]

        for setting in download_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "STREAMRIP_SOURCE_SUBDIRECTORIES",
                "STREAMRIP_DISC_SUBDIRECTORIES",
                "STREAMRIP_CONCURRENCY",
                "STREAMRIP_VERIFY_SSL",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit streamrip_download", "footer")
        else:
            buttons.data_button("👁️ View", "botset view streamrip_download", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_download", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current download settings
        concurrent = Config.STREAMRIP_CONCURRENT_DOWNLOADS or "4 (Default)"
        max_results = Config.STREAMRIP_MAX_SEARCH_RESULTS or "20 (Default)"
        max_connections = Config.STREAMRIP_MAX_CONNECTIONS or "6 (Default)"
        requests_per_minute = Config.STREAMRIP_REQUESTS_PER_MINUTE or "60 (Default)"
        source_subdirs = (
            "✅ Enabled" if Config.STREAMRIP_SOURCE_SUBDIRECTORIES else "❌ Disabled"
        )
        disc_subdirs = (
            "✅ Enabled" if Config.STREAMRIP_DISC_SUBDIRECTORIES else "❌ Disabled"
        )
        concurrency = "✅ Enabled" if Config.STREAMRIP_CONCURRENCY else "❌ Disabled"
        verify_ssl = "✅ Enabled" if Config.STREAMRIP_VERIFY_SSL else "❌ Disabled"

        msg = f"""<b>🎵 Streamrip Download Settings</b> | State: {state}

<b>Performance Settings:</b>
• <b>Concurrent Downloads:</b> <code>{concurrent}</code>
• <b>Max Search Results:</b> <code>{max_results}</code>
• <b>Max Connections:</b> <code>{max_connections}</code>
• <b>Requests Per Minute:</b> <code>{requests_per_minute}</code>

<b>Organization Settings:</b>
• <b>Source Subdirectories:</b> {source_subdirs}
• <b>Disc Subdirectories:</b> {disc_subdirs}

<b>Technical Settings:</b>
• <b>Concurrency:</b> {concurrency}
• <b>Verify SSL:</b> {verify_ssl}

<b>Description:</b>
• <b>Source Subdirectories:</b> Put albums in platform-specific folders (Qobuz, Tidal, etc.)
• <b>Disc Subdirectories:</b> Put multi-disc albums in separate disc folders
• <b>Concurrency:</b> Download tracks simultaneously vs sequentially
• <b>Verify SSL:</b> Verify SSL certificates for secure connections"""

    elif key == "streamrip_advanced":
        # Advanced Settings
        advanced_settings = [
            "STREAMRIP_FILENAME_TEMPLATE",
            "STREAMRIP_FOLDER_TEMPLATE",
            "STREAMRIP_EMBED_COVER_ART",
            "STREAMRIP_SAVE_COVER_ART",
            "STREAMRIP_COVER_ART_SIZE",
            "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH",
            "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH",
            "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER",
            "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
            "STREAMRIP_FILEPATHS_TRACK_FORMAT",
            "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS",
            "STREAMRIP_FILEPATHS_TRUNCATE_TO",
        ]

        for setting in advanced_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "STREAMRIP_EMBED_COVER_ART",
                "STREAMRIP_SAVE_COVER_ART",
                "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER",
                "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit streamrip_advanced", "footer")
        else:
            buttons.data_button("👁️ View", "botset view streamrip_advanced", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_advanced", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current advanced settings
        filename_template = Config.STREAMRIP_FILENAME_TEMPLATE or "Default Template"
        folder_template = Config.STREAMRIP_FOLDER_TEMPLATE or "Default Template"
        embed_cover = (
            "✅ Enabled" if Config.STREAMRIP_EMBED_COVER_ART else "❌ Disabled"
        )
        save_cover = (
            "✅ Enabled" if Config.STREAMRIP_SAVE_COVER_ART else "❌ Disabled"
        )
        cover_size = Config.STREAMRIP_COVER_ART_SIZE or "large (Default)"
        embed_max_width = (
            Config.STREAMRIP_ARTWORK_EMBED_MAX_WIDTH
            if Config.STREAMRIP_ARTWORK_EMBED_MAX_WIDTH != -1
            else "No limit"
        )
        saved_max_width = (
            Config.STREAMRIP_ARTWORK_SAVED_MAX_WIDTH
            if Config.STREAMRIP_ARTWORK_SAVED_MAX_WIDTH != -1
            else "No limit"
        )

        msg = f"""<b>🎵 Streamrip Advanced Settings</b> | State: {state}

<b>Filename Template:</b> <code>{filename_template}</code>
<b>Folder Template:</b> <code>{folder_template}</code>
<b>Embed Cover Art:</b> {embed_cover}
<b>Save Cover Art:</b> {save_cover}
<b>Cover Art Size:</b> <code>{cover_size}</code>
<b>Embed Max Width:</b> <code>{embed_max_width}</code>
<b>Saved Max Width:</b> <code>{saved_max_width}</code>

<b>Template Variables:</b>
• <code>{{artist}}</code> - Artist name
• <code>{{album}}</code> - Album title
• <code>{{title}}</code> - Track title
• <code>{{track}}</code> - Track number
• <code>{{year}}</code> - Release year

<b>Cover Art Sizes:</b>
• <b>small:</b> 300x300px
• <b>large:</b> 1200x1200px (recommended)"""

    elif key == "streamrip_config":
        # Config File Management
        buttons.data_button("📄 View Current Config", "botset view_streamrip_config")
        buttons.data_button(
            "📤 Upload Custom Config", "botset upload_streamrip_config"
        )
        buttons.data_button("🔄 Reset to Default", "botset reset_streamrip_config")

        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        msg = """<b>🎵 Streamrip Config File Management</b>

<b>Current Config:</b> Click "View Current Config" to see the active configuration

<b>Upload Custom Config:</b>
• Upload a custom streamrip_config.toml file
• Will override bot settings with your custom configuration
• Useful for advanced users with specific requirements

<b>Reset to Default:</b>
• Removes any custom configuration
• Reverts to bot's default streamrip settings
• All platform credentials will be preserved

<b>Note:</b>
Custom config files take precedence over bot settings. If you upload a custom config, the individual setting menus will show the custom values."""

    elif key == "gallerydl":
        # Gallery-dl Settings section
        buttons.data_button("⚙️ General Settings", "botset gallerydl_general")
        buttons.data_button("🔐 Authentication & Platforms", "botset gallerydl_auth")
        buttons.data_button("📁 Download Settings", "botset gallerydl_download")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        msg = "<b>🖼️ Gallery-dl Settings</b>\nSelect a category to configure:"

    elif key == "gallerydl_general":
        # General Gallery-dl Settings
        general_settings = [
            "GALLERY_DL_ENABLED",
            "GALLERY_DL_QUALITY_SELECTION",
            "GALLERY_DL_ARCHIVE_ENABLED",
            "GALLERY_DL_METADATA_ENABLED",
        ]

        for setting in general_settings:
            display_name = (
                setting.replace("GALLERY_DL_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "GALLERY_DL_ENABLED",
                "GALLERY_DL_QUALITY_SELECTION",
                "GALLERY_DL_ARCHIVE_ENABLED",
                "GALLERY_DL_METADATA_ENABLED",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit gallerydl_general", "footer")
        else:
            buttons.data_button("👁️ View", "botset view gallerydl_general", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_gallerydl_general", "footer"
        )
        buttons.data_button("⬅️ Back", "botset gallerydl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current general settings
        enabled = "✅ Enabled" if Config.GALLERY_DL_ENABLED else "❌ Disabled"
        quality_selection = (
            "✅ Enabled" if Config.GALLERY_DL_QUALITY_SELECTION else "❌ Disabled"
        )
        archive_enabled = (
            "✅ Enabled" if Config.GALLERY_DL_ARCHIVE_ENABLED else "❌ Disabled"
        )
        metadata_enabled = (
            "✅ Enabled" if Config.GALLERY_DL_METADATA_ENABLED else "❌ Disabled"
        )

        msg = f"""<b>🖼️ Gallery-dl General Settings</b> | State: {state}

<b>Status:</b> {enabled}
<b>Quality Selection:</b> {quality_selection}
<b>Archive:</b> {archive_enabled}
<b>Metadata:</b> {metadata_enabled}

<b>Description:</b>
• <b>Enabled:</b> Master toggle for gallery-dl functionality
• <b>Quality Selection:</b> Show quality selection interface for downloads
• <b>Archive:</b> Keep track of downloaded files to avoid duplicates
• <b>Metadata:</b> Save metadata files (JSON, YAML, TXT) with downloads

<b>Note:</b>
Gallery-dl supports 200+ platforms including Instagram, Twitter, Reddit, Pixiv, DeviantArt, and many more."""

    elif key == "gallerydl_auth":
        # Authentication Settings
        auth_settings = [
            "GALLERY_DL_INSTAGRAM_USERNAME",
            "GALLERY_DL_INSTAGRAM_PASSWORD",
            "GALLERY_DL_TWITTER_USERNAME",
            "GALLERY_DL_TWITTER_PASSWORD",
            "GALLERY_DL_REDDIT_CLIENT_ID",
            "GALLERY_DL_REDDIT_CLIENT_SECRET",
            "GALLERY_DL_REDDIT_USERNAME",
            "GALLERY_DL_REDDIT_PASSWORD",
            "GALLERY_DL_REDDIT_REFRESH_TOKEN",
            "GALLERY_DL_PIXIV_USERNAME",
            "GALLERY_DL_PIXIV_PASSWORD",
            "GALLERY_DL_PIXIV_REFRESH_TOKEN",
            "GALLERY_DL_DEVIANTART_CLIENT_ID",
            "GALLERY_DL_DEVIANTART_CLIENT_SECRET",
            "GALLERY_DL_DEVIANTART_USERNAME",
            "GALLERY_DL_DEVIANTART_PASSWORD",
            "GALLERY_DL_TUMBLR_API_KEY",
            "GALLERY_DL_TUMBLR_API_SECRET",
            "GALLERY_DL_TUMBLR_TOKEN",
            "GALLERY_DL_TUMBLR_TOKEN_SECRET",
            "GALLERY_DL_DISCORD_TOKEN",
        ]

        for setting in auth_settings:
            display_name = (
                setting.replace("GALLERY_DL_", "").replace("_", " ").title()
            )
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit gallerydl_auth", "footer")
        else:
            buttons.data_button("👁️ View", "botset view gallerydl_auth", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_gallerydl_auth", "footer"
        )
        buttons.data_button("⬅️ Back", "botset gallerydl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        msg = f"""<b>🖼️ Gallery-dl Authentication Settings</b> | State: {state}

<b>Platform Authentication:</b>
Configure credentials for accessing private content and higher quality downloads.

<b>Supported Platforms:</b>
• <b>Instagram:</b> Username/password for private accounts and stories
• <b>Twitter/X:</b> Username/password for private accounts and higher quality
• <b>Reddit:</b> OAuth credentials for NSFW content and private subreddits
• <b>Pixiv:</b> Username/password for R-18 content and following artists
• <b>DeviantArt:</b> OAuth credentials for mature content and Eclipse features
• <b>Tumblr:</b> API credentials for NSFW content
• <b>Discord:</b> Bot token for server content

<b>Cookies Support:</b>
Upload cookies.txt file via Private Files for universal authentication.

<b>Security Note:</b>
All credentials are stored securely in the database and encrypted."""

    elif key == "gallerydl_download":
        # Download Settings
        download_settings = [
            "GALLERY_DL_MAX_DOWNLOADS",
            "GALLERY_DL_RATE_LIMIT",
            "GALLERY_DL_LIMIT",
        ]

        for setting in download_settings:
            display_name = (
                setting.replace("GALLERY_DL_", "").replace("_", " ").title()
            )
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit gallerydl_download", "footer")
        else:
            buttons.data_button("👁️ View", "botset view gallerydl_download", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_gallerydl_download", "footer"
        )
        buttons.data_button("⬅️ Back", "botset gallerydl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current download settings
        max_downloads = Config.GALLERY_DL_MAX_DOWNLOADS or "50 (Default)"
        rate_limit = Config.GALLERY_DL_RATE_LIMIT or "1/s (Default)"
        limit = Config.GALLERY_DL_LIMIT or "0 (Unlimited)"

        msg = f"""<b>🖼️ Gallery-dl Download Settings</b> | State: {state}

<b>Performance Settings:</b>
• <b>Max Downloads:</b> <code>{max_downloads}</code>
• <b>Rate Limit:</b> <code>{rate_limit}</code>
• <b>Limit:</b> <code>{limit}</code>

<b>Description:</b>
• <b>Max Downloads:</b> Maximum concurrent downloads
• <b>Rate Limit:</b> Delay between requests to avoid rate limiting
• <b>Limit:</b> Maximum number of files to download (0 = unlimited)

<b>Recommended Settings:</b>
• For Instagram: 1/s or slower
• For Twitter: 2/s
• For Reddit: 1/s
• For Pixiv: 1/2s (slower)"""

    elif key == "gallerydl_platforms":
        # Platform-specific Settings - Note: These are duplicates of auth settings, redirecting to auth
        buttons.data_button("⚠️ Platform Settings Moved", "botset gallerydl_auth")
        buttons.data_button("⬅️ Back", "botset gallerydl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        msg = f"""<b>🖼️ Gallery-dl Platform Settings</b> | State: {state}

<b>⚠️ Settings Moved</b>
Platform-specific authentication settings have been moved to the <b>Authentication</b> section to avoid duplicates.

<b>Click "Platform Settings Moved" to access:</b>
• Instagram credentials
• Twitter credentials
• Reddit API settings
• Pixiv credentials
• DeviantArt API settings
• Tumblr API settings
• Discord token

<b>Note:</b> All platform credentials are now managed in one place under Authentication."""

    elif key == "streamrip_platforms":
        # Platform-specific Settings
        platform_settings = [
            "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS",
            "STREAMRIP_QOBUZ_FILTERS_EXTRAS",
            "STREAMRIP_QOBUZ_FILTERS_REPEATS",
            "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS",
            "STREAMRIP_QOBUZ_FILTERS_FEATURES",
            "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS",
            "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER",
            "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS",
            "STREAMRIP_TIDAL_TOKEN_EXPIRY",
            "STREAMRIP_DEEZER_USE_DEEZLOADER",
            "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS",
            "STREAMRIP_SOUNDCLOUD_APP_VERSION",
            "STREAMRIP_YOUTUBE_QUALITY",
            "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS",
            "STREAMRIP_YOUTUBE_VIDEO_FOLDER",
            "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER",
            "STREAMRIP_LASTFM_ENABLED",
            "STREAMRIP_LASTFM_SOURCE",
            "STREAMRIP_LASTFM_FALLBACK_SOURCE",
        ]

        for setting in platform_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS",
                "STREAMRIP_QOBUZ_FILTERS_EXTRAS",
                "STREAMRIP_QOBUZ_FILTERS_REPEATS",
                "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS",
                "STREAMRIP_QOBUZ_FILTERS_FEATURES",
                "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS",
                "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER",
                "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS",
                "STREAMRIP_DEEZER_USE_DEEZLOADER",
                "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS",
                "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS",
                "STREAMRIP_LASTFM_ENABLED",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button(
                "✏️ Edit", "botset edit streamrip_platforms", "footer"
            )
        else:
            buttons.data_button(
                "👁️ View", "botset view streamrip_platforms", "footer"
            )

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_platforms", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current platform settings
        qobuz_booklets = (
            "✅ Enabled"
            if Config.STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS
            else "❌ Disabled"
        )
        tidal_videos = (
            "✅ Enabled" if Config.STREAMRIP_TIDAL_DOWNLOAD_VIDEOS else "❌ Disabled"
        )
        tidal_token_expiry = Config.STREAMRIP_TIDAL_TOKEN_EXPIRY or "Not Set"
        deezer_deezloader = (
            "✅ Enabled" if Config.STREAMRIP_DEEZER_USE_DEEZLOADER else "❌ Disabled"
        )
        deezer_warnings = (
            "✅ Enabled"
            if Config.STREAMRIP_DEEZER_DEEZLOADER_WARNINGS
            else "❌ Disabled"
        )
        soundcloud_app_version = (
            Config.STREAMRIP_SOUNDCLOUD_APP_VERSION or "Auto-detect"
        )
        youtube_quality = Config.STREAMRIP_YOUTUBE_QUALITY or 0
        youtube_videos = (
            "✅ Enabled"
            if Config.STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS
            else "❌ Disabled"
        )
        youtube_folder = Config.STREAMRIP_YOUTUBE_VIDEO_FOLDER or "Default"
        youtube_downloads_folder = (
            Config.STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER or "Default"
        )
        lastfm_source = Config.STREAMRIP_LASTFM_SOURCE or "qobuz (Default)"
        lastfm_fallback = Config.STREAMRIP_LASTFM_FALLBACK_SOURCE or "None"

        msg = f"""<b>🎵 Streamrip Platform Settings</b> | State: {state}

<b>Qobuz Settings:</b>
• <b>Download Booklets:</b> {qobuz_booklets}

<b>Tidal Settings:</b>
• <b>Download Videos:</b> {tidal_videos}
• <b>Token Expiry:</b> <code>{tidal_token_expiry}</code>

<b>Deezer Settings:</b>
• <b>Use Deezloader:</b> {deezer_deezloader}
• <b>Deezloader Warnings:</b> {deezer_warnings}

<b>SoundCloud Settings:</b>
• <b>App Version:</b> <code>{soundcloud_app_version}</code>

<b>YouTube Settings:</b>
• <b>Quality:</b> <code>{youtube_quality}</code> (0: Basic quality only)
• <b>Download Videos:</b> {youtube_videos}
• <b>Video Folder:</b> <code>{youtube_folder}</code>
• <b>Video Downloads Folder:</b> <code>{youtube_downloads_folder}</code>

<b>Last.fm Settings:</b>
• <b>Primary Source:</b> <code>{lastfm_source}</code>
• <b>Fallback Source:</b> <code>{lastfm_fallback}</code>

<b>Description:</b>
Platform-specific settings for enhanced functionality and compatibility with different streaming services."""

    elif key == "streamrip_database":
        # Database Settings
        database_settings = [
            "STREAMRIP_ENABLE_DATABASE",
            "STREAMRIP_DATABASE_DOWNLOADS_ENABLED",
            "STREAMRIP_DATABASE_DOWNLOADS_PATH",
            "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED",
            "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
        ]

        for setting in database_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "STREAMRIP_ENABLE_DATABASE",
                "STREAMRIP_DATABASE_DOWNLOADS_ENABLED",
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit streamrip_database", "footer")
        else:
            buttons.data_button("👁️ View", "botset view streamrip_database", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_database", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current database settings
        main_database = (
            "✅ Enabled" if Config.STREAMRIP_ENABLE_DATABASE else "❌ Disabled"
        )
        downloads_enabled = (
            "✅ Enabled"
            if Config.STREAMRIP_DATABASE_DOWNLOADS_ENABLED
            else "❌ Disabled"
        )
        downloads_path = (
            Config.STREAMRIP_DATABASE_DOWNLOADS_PATH or "./downloads.db (Default)"
        )
        failed_enabled = (
            "✅ Enabled"
            if Config.STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED
            else "❌ Disabled"
        )
        failed_path = (
            Config.STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH
            or "./failed_downloads.db (Default)"
        )

        msg = f"""<b>🗄️ Streamrip Database Settings</b> | State: {state}

<b>Main Database Toggle:</b> {main_database}

<b>Downloads Database:</b>
• <b>Enabled:</b> {downloads_enabled}
• <b>Path:</b> <code>{downloads_path}</code>

<b>Failed Downloads Database:</b>
• <b>Enabled:</b> {failed_enabled}
• <b>Path:</b> <code>{failed_path}</code>

<b>Description:</b>
• <b>Main Database Toggle:</b> Master control for all streamrip database features (controls --no-db flag)
• <b>Downloads Database:</b> Track successfully downloaded files to avoid duplicates
• <b>Failed Downloads Database:</b> Track failed downloads for retry functionality
• <b>Database Paths:</b> File paths where the SQLite databases are stored

<b>Benefits:</b>
• Prevents duplicate downloads
• Enables smart retry functionality
• Provides download history tracking
• Controls streamrip CLI database usage"""

    elif key == "streamrip_conversion":
        # Conversion Settings
        conversion_settings = [
            "STREAMRIP_CONVERSION_ENABLED",
            "STREAMRIP_CONVERSION_CODEC",
            "STREAMRIP_CONVERSION_SAMPLING_RATE",
            "STREAMRIP_CONVERSION_BIT_DEPTH",
            "STREAMRIP_CONVERSION_LOSSY_BITRATE",
        ]

        for setting in conversion_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in ["STREAMRIP_CONVERSION_ENABLED"]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button(
                "✏️ Edit", "botset edit streamrip_conversion", "footer"
            )
        else:
            buttons.data_button(
                "👁️ View", "botset view streamrip_conversion", "footer"
            )

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_conversion", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current conversion settings
        conversion_enabled = (
            "✅ Enabled" if Config.STREAMRIP_CONVERSION_ENABLED else "❌ Disabled"
        )
        conversion_codec = Config.STREAMRIP_CONVERSION_CODEC or "ALAC (Default)"
        sampling_rate = (
            f"{Config.STREAMRIP_CONVERSION_SAMPLING_RATE} Hz"
            if Config.STREAMRIP_CONVERSION_SAMPLING_RATE
            else "48000 Hz (Default)"
        )
        bit_depth = (
            f"{Config.STREAMRIP_CONVERSION_BIT_DEPTH} bit"
            if Config.STREAMRIP_CONVERSION_BIT_DEPTH
            else "24 bit (Default)"
        )
        lossy_bitrate = (
            f"{Config.STREAMRIP_CONVERSION_LOSSY_BITRATE} kbps"
            if Config.STREAMRIP_CONVERSION_LOSSY_BITRATE
            else "320 kbps (Default)"
        )

        msg = f"""<b>🔄 Streamrip Conversion Settings</b> | State: {state}

<b>Conversion Status:</b> {conversion_enabled}
<b>Target Codec:</b> <code>{conversion_codec}</code>
<b>Sampling Rate:</b> <code>{sampling_rate}</code>
<b>Bit Depth:</b> <code>{bit_depth}</code>
<b>Lossy Bitrate:</b> <code>{lossy_bitrate}</code>

<b>Available Codecs:</b>
• <b>ALAC:</b> Apple Lossless (recommended for Apple devices)
• <b>FLAC:</b> Free Lossless Audio Codec
• <b>MP3:</b> MPEG Audio Layer III (lossy)
• <b>AAC:</b> Advanced Audio Coding (lossy)
• <b>OGG:</b> Ogg Vorbis (lossy)

<b>Description:</b>
Convert downloaded audio files to different formats and quality settings. Useful for device compatibility and storage optimization."""

    elif key == "streamrip_metadata":
        # Metadata Settings
        metadata_settings = [
            "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM",
            "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS",
            "STREAMRIP_METADATA_EXCLUDE",
        ]

        for setting in metadata_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM",
                "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For list settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit streamrip_metadata", "footer")
        else:
            buttons.data_button("👁️ View", "botset view streamrip_metadata", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_metadata", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current metadata settings
        set_playlist_to_album = (
            "✅ Enabled"
            if Config.STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM
            else "❌ Disabled"
        )
        renumber_playlist_tracks = (
            "✅ Enabled"
            if Config.STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS
            else "❌ Disabled"
        )
        exclude_list = Config.STREAMRIP_METADATA_EXCLUDE or []
        exclude_display = ", ".join(exclude_list) if exclude_list else "None"

        msg = f"""<b>🏷️ Streamrip Metadata Settings</b> | State: {state}

<b>Set Playlist to Album:</b> {set_playlist_to_album}
<b>Renumber Playlist Tracks:</b> {renumber_playlist_tracks}
<b>Exclude Metadata Fields:</b> <code>{exclude_display}</code>

<b>Description:</b>
• <b>Set Playlist to Album:</b> When downloading playlists, set the album metadata to the playlist name
• <b>Renumber Playlist Tracks:</b> Renumber tracks in playlists starting from 1
• <b>Exclude Metadata Fields:</b> List of metadata fields to exclude from downloaded files

<b>Common Exclude Fields:</b>
• <b>comment:</b> Remove comment metadata
• <b>description:</b> Remove description metadata
• <b>synopsis:</b> Remove synopsis metadata
• <b>lyrics:</b> Remove embedded lyrics

<b>Note:</b>
Metadata settings help customize how track information is handled during downloads and can improve compatibility with different music players."""

    elif key == "streamrip_cli":
        # CLI Settings
        cli_settings = [
            "STREAMRIP_CLI_TEXT_OUTPUT",
            "STREAMRIP_CLI_PROGRESS_BARS",
            "STREAMRIP_CLI_MAX_SEARCH_RESULTS",
            "STREAMRIP_MISC_CHECK_FOR_UPDATES",
            "STREAMRIP_MISC_VERSION",
        ]

        for setting in cli_settings:
            display_name = (
                setting.replace("STREAMRIP_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "STREAMRIP_CLI_TEXT_OUTPUT",
                "STREAMRIP_CLI_PROGRESS_BARS",
                "STREAMRIP_MISC_CHECK_FOR_UPDATES",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit streamrip_cli", "footer")
        else:
            buttons.data_button("👁️ View", "botset view streamrip_cli", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_streamrip_cli", "footer"
        )
        buttons.data_button("⬅️ Back", "botset streamrip", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current CLI settings
        text_output = (
            "✅ Enabled" if Config.STREAMRIP_CLI_TEXT_OUTPUT else "❌ Disabled"
        )
        progress_bars = (
            "✅ Enabled" if Config.STREAMRIP_CLI_PROGRESS_BARS else "❌ Disabled"
        )
        max_search_results = (
            Config.STREAMRIP_CLI_MAX_SEARCH_RESULTS or "100 (Default)"
        )
        check_updates = (
            "✅ Enabled"
            if Config.STREAMRIP_MISC_CHECK_FOR_UPDATES
            else "❌ Disabled"
        )
        version = Config.STREAMRIP_MISC_VERSION or "2.0.6 (Default)"

        msg = f"""<b>🖥️ Streamrip CLI Settings</b> | State: {state}

<b>Text Output:</b> {text_output}
<b>Progress Bars:</b> {progress_bars}
<b>Max Search Results:</b> <code>{max_search_results}</code>
<b>Check for Updates:</b> {check_updates}
<b>Config Version:</b> <code>{version}</code>

<b>Description:</b>
• <b>Text Output:</b> Enable detailed text output during downloads
• <b>Progress Bars:</b> Show progress bars for download operations
• <b>Max Search Results:</b> Maximum results returned from CLI searches
• <b>Check for Updates:</b> Automatically check for streamrip updates
• <b>Config Version:</b> Streamrip configuration file version identifier

<b>Note:</b>
These settings primarily affect the streamrip CLI behavior and may not directly impact bot functionality."""

    elif key == "zotify":
        # Zotify Settings section
        buttons.data_button("⚙️ General Settings", "botset zotify_general")
        buttons.data_button("🎵 Quality & Format", "botset zotify_quality")
        buttons.data_button("🔐 Authentication", "botset zotify_auth")
        buttons.data_button("📁 Library Paths", "botset zotify_paths")
        buttons.data_button("📝 Output Templates", "botset zotify_templates")
        buttons.data_button("🎛️ Download Settings", "botset zotify_download")
        buttons.data_button("🏷️ Metadata Settings", "botset zotify_metadata")
        buttons.data_button("🔧 Advanced Settings", "botset zotify_advanced")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        msg = "<b>🎧 Zotify Settings</b>\nSelect a category to configure:"

    elif key == "zotify_general":
        # General Zotify Settings
        general_settings = [
            "ZOTIFY_ENABLED",
            "ZOTIFY_DOWNLOAD_REAL_TIME",
            "ZOTIFY_REPLACE_EXISTING",
            "ZOTIFY_SKIP_DUPLICATES",
            "ZOTIFY_SKIP_PREVIOUS",
        ]

        for setting in general_settings:
            display_name = setting.replace("ZOTIFY_", "").replace("_", " ").title()

            # For boolean settings, add toggle buttons with status
            if setting in [
                "ZOTIFY_ENABLED",
                "ZOTIFY_DOWNLOAD_REAL_TIME",
                "ZOTIFY_REPLACE_EXISTING",
                "ZOTIFY_SKIP_DUPLICATES",
                "ZOTIFY_SKIP_PREVIOUS",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit zotify_general", "footer")
        else:
            buttons.data_button("👁️ View", "botset view zotify_general", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_zotify_general", "footer"
        )
        buttons.data_button("⬅️ Back", "botset zotify", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current general settings
        enabled = "✅ Enabled" if Config.ZOTIFY_ENABLED else "❌ Disabled"
        real_time = (
            "✅ Enabled" if Config.ZOTIFY_DOWNLOAD_REAL_TIME else "❌ Disabled"
        )
        replace_existing = (
            "✅ Enabled" if Config.ZOTIFY_REPLACE_EXISTING else "❌ Disabled"
        )
        skip_duplicates = (
            "✅ Enabled" if Config.ZOTIFY_SKIP_DUPLICATES else "❌ Disabled"
        )
        skip_previous = (
            "✅ Enabled" if Config.ZOTIFY_SKIP_PREVIOUS else "❌ Disabled"
        )

        msg = f"""<b>🎧 Zotify General Settings</b> | State: {state}

<b>Status:</b> {enabled}
<b>Real-Time Download:</b> {real_time}
<b>Replace Existing:</b> {replace_existing}
<b>Skip Duplicates:</b> {skip_duplicates}
<b>Skip Previous:</b> {skip_previous}

<b>Description:</b>
• <b>Enabled:</b> Master toggle for Zotify functionality
• <b>Real-Time Download:</b> Download tracks in real-time (slower but more stable)
• <b>Replace Existing:</b> Overwrite existing files instead of skipping
• <b>Skip Duplicates:</b> Skip tracks that have already been downloaded
• <b>Skip Previous:</b> Skip tracks that were previously downloaded (uses database)

<b>Note:</b>
These are core Zotify settings that control the basic download behavior."""

    elif key == "zotify_quality":
        # Quality & Format Settings
        quality_settings = [
            "ZOTIFY_DOWNLOAD_QUALITY",
            "ZOTIFY_AUDIO_FORMAT",
            "ZOTIFY_ARTWORK_SIZE",
            "ZOTIFY_TRANSCODE_BITRATE",
        ]

        for setting in quality_settings:
            display_name = setting.replace("ZOTIFY_", "").replace("_", " ").title()
            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit zotify_quality", "footer")
        else:
            buttons.data_button("👁️ View", "botset view zotify_quality", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_zotify_quality", "footer"
        )
        buttons.data_button("⬅️ Back", "botset zotify", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current quality settings
        download_quality = Config.ZOTIFY_DOWNLOAD_QUALITY or "auto (Default)"
        audio_format = Config.ZOTIFY_AUDIO_FORMAT or "vorbis (Default)"
        artwork_size = Config.ZOTIFY_ARTWORK_SIZE or "large (Default)"
        transcode_bitrate = (
            Config.ZOTIFY_TRANSCODE_BITRATE
            if Config.ZOTIFY_TRANSCODE_BITRATE != -1
            else "Use download rate (Default)"
        )

        msg = f"""<b>🎧 Zotify Quality & Format Settings</b> | State: {state}

<b>Download Quality:</b> <code>{download_quality}</code>
<b>Audio Format:</b> <code>{audio_format}</code>
<b>Artwork Size:</b> <code>{artwork_size}</code>
<b>Transcode Bitrate:</b> <code>{transcode_bitrate}</code>

<b>Quality Options:</b>
• <b>auto:</b> Automatic quality selection
• <b>normal:</b> 96 kbps OGG Vorbis
• <b>high:</b> 160 kbps OGG Vorbis
• <b>very_high:</b> 320 kbps OGG Vorbis (Premium required)

<b>Format Options:</b>
• <b>vorbis:</b> OGG Vorbis (native, no transcoding)
• <b>mp3:</b> MP3 (transcoded from OGG)
• <b>flac:</b> FLAC (transcoded from OGG)
• <b>aac:</b> AAC (transcoded from OGG)
• <b>wav:</b> WAV (transcoded from OGG)

<b>Artwork Sizes:</b>
• <b>small:</b> 300x300px
• <b>medium:</b> 640x640px
• <b>large:</b> 1200x1200px (recommended)"""

    elif key == "zotify_auth":
        # Authentication Settings
        auth_settings = [
            "ZOTIFY_CREDENTIALS_PATH",
        ]

        for setting in auth_settings:
            display_name = setting.replace("ZOTIFY_", "").replace("_", " ").title()
            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Add credential management buttons
        buttons.data_button(
            "📤 Upload Credentials", "botset upload_zotify_credentials"
        )
        buttons.data_button("🗑️ Clear Credentials", "botset clear_zotify_credentials")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit zotify_auth", "footer")
        else:
            buttons.data_button("👁️ View", "botset view zotify_auth", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_zotify_auth", "footer"
        )
        buttons.data_button("⬅️ Back", "botset zotify", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current auth settings
        credentials_path = (
            Config.ZOTIFY_CREDENTIALS_PATH or "./zotify_credentials.json (Default)"
        )

        # Check if credentials exist (database first, then file)
        if not zotify_config:
            creds_exist = False
        else:
            # Use the user_id parameter passed to get_buttons function
            creds_exist = await zotify_config.has_credentials(user_id)
        creds_status = "✅ Available" if creds_exist else "❌ Not Found"

        msg = f"""<b>🎧 Zotify Authentication Settings</b> | State: {state}

<b>Credentials Path:</b> <code>{credentials_path}</code>
<b>Credentials Status:</b> {creds_status}

<b>Authentication Methods:</b>
• <b>File-based:</b> Upload a credentials.json file with saved login
• <b>Interactive:</b> Login interactively when needed (fallback)

<b>Credential Management:</b>
• <b>Upload Credentials:</b> Upload a pre-saved credentials file
• <b>Clear Credentials:</b> Remove existing credentials (will require re-login)

<b>Note:</b>
Zotify requires Spotify Premium for high-quality downloads. The bot will handle authentication automatically using the configured method."""

    elif key == "zotify_paths":
        # Library Paths Settings
        path_settings = [
            "ZOTIFY_ALBUM_LIBRARY",
            "ZOTIFY_PODCAST_LIBRARY",
            "ZOTIFY_PLAYLIST_LIBRARY",
        ]

        for setting in path_settings:
            display_name = setting.replace("ZOTIFY_", "").replace("_", " ").title()
            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit zotify_paths", "footer")
        else:
            buttons.data_button("👁️ View", "botset view zotify_paths", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_zotify_paths", "footer"
        )
        buttons.data_button("⬅️ Back", "botset zotify", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current path settings
        album_library = (
            Config.ZOTIFY_ALBUM_LIBRARY or "Music/Zotify Albums (Default)"
        )
        podcast_library = (
            Config.ZOTIFY_PODCAST_LIBRARY or "Music/Zotify Podcasts (Default)"
        )
        playlist_library = (
            Config.ZOTIFY_PLAYLIST_LIBRARY or "Music/Zotify Playlists (Default)"
        )

        msg = f"""<b>🎧 Zotify Library Paths</b> | State: {state}

<b>Album Library:</b> <code>{album_library}</code>
<b>Podcast Library:</b> <code>{podcast_library}</code>
<b>Playlist Library:</b> <code>{playlist_library}</code>

<b>Description:</b>
• <b>Album Library:</b> Root directory for downloaded albums
• <b>Podcast Library:</b> Root directory for downloaded podcasts
• <b>Playlist Library:</b> Root directory for downloaded playlists

<b>Note:</b>
These paths are relative to the bot's download directory. Each content type will be organized in its respective library folder."""

    elif key == "zotify_templates":
        # Output Templates Settings
        template_settings = [
            "ZOTIFY_OUTPUT_ALBUM",
            "ZOTIFY_OUTPUT_PLAYLIST_TRACK",
            "ZOTIFY_OUTPUT_PLAYLIST_EPISODE",
            "ZOTIFY_OUTPUT_PODCAST",
            "ZOTIFY_OUTPUT_SINGLE",
        ]

        for setting in template_settings:
            display_name = (
                setting.replace("ZOTIFY_OUTPUT_", "").replace("_", " ").title()
            )
            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit zotify_templates", "footer")
        else:
            buttons.data_button("👁️ View", "botset view zotify_templates", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_zotify_templates", "footer"
        )
        buttons.data_button("⬅️ Back", "botset zotify", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current template settings
        album_template = (
            Config.ZOTIFY_OUTPUT_ALBUM
            or "{album_artist}/{album}/Disc {discnumber}/{track_number}. {artists} - {title} (Default)"
        )
        playlist_track_template = (
            Config.ZOTIFY_OUTPUT_PLAYLIST_TRACK
            or "{playlist}/{artists} - {title} (Default)"
        )
        playlist_episode_template = (
            Config.ZOTIFY_OUTPUT_PLAYLIST_EPISODE
            or "{playlist}/{episode_number} - {title} (Default)"
        )
        podcast_template = (
            Config.ZOTIFY_OUTPUT_PODCAST
            or "{podcast}/{episode_number} - {title} (Default)"
        )
        single_template = (
            Config.ZOTIFY_OUTPUT_SINGLE or "{artists} - {title} (Default)"
        )

        msg = f"""<b>🎧 Zotify Output Templates</b> | State: {state}

<b>Album:</b> <code>{album_template}</code>
<b>Playlist Track:</b> <code>{playlist_track_template}</code>
<b>Playlist Episode:</b> <code>{playlist_episode_template}</code>
<b>Podcast:</b> <code>{podcast_template}</code>
<b>Single:</b> <code>{single_template}</code>

<b>Available Variables:</b>
• <b>{{album_artist}}</b> - Album artist name
• <b>{{album}}</b> - Album title
• <b>{{artists}}</b> - Track artist(s)
• <b>{{title}}</b> - Track/episode title
• <b>{{track_number}}</b> - Track number
• <b>{{discnumber}}</b> - Disc number
• <b>{{playlist}}</b> - Playlist name
• <b>{{podcast}}</b> - Podcast name
• <b>{{episode_number}}</b> - Episode number

<b>Note:</b>
These templates control how files are named and organized within their respective library folders."""

    elif key == "zotify_download":
        # Download Settings
        download_settings = [
            "ZOTIFY_PRINT_PROGRESS",
            "ZOTIFY_PRINT_DOWNLOADS",
            "ZOTIFY_PRINT_ERRORS",
            "ZOTIFY_PRINT_WARNINGS",
            "ZOTIFY_PRINT_SKIPS",
        ]

        for setting in download_settings:
            display_name = (
                setting.replace("ZOTIFY_PRINT_", "Print ").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            setting_value = getattr(Config, setting, False)
            status = "✅ ON" if setting_value else "❌ OFF"
            display_name = f"{display_name}: {status}"
            buttons.data_button(
                display_name, f"botset toggle {setting} {not setting_value}"
            )

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit zotify_download", "footer")
        else:
            buttons.data_button("👁️ View", "botset view zotify_download", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_zotify_download", "footer"
        )
        buttons.data_button("⬅️ Back", "botset zotify", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current download settings
        print_progress = (
            "✅ Enabled" if Config.ZOTIFY_PRINT_PROGRESS else "❌ Disabled"
        )
        print_downloads = (
            "✅ Enabled" if Config.ZOTIFY_PRINT_DOWNLOADS else "❌ Disabled"
        )
        print_errors = "✅ Enabled" if Config.ZOTIFY_PRINT_ERRORS else "❌ Disabled"
        print_warnings = (
            "✅ Enabled" if Config.ZOTIFY_PRINT_WARNINGS else "❌ Disabled"
        )
        print_skips = "✅ Enabled" if Config.ZOTIFY_PRINT_SKIPS else "❌ Disabled"

        msg = f"""<b>🎧 Zotify Download Settings</b> | State: {state}

<b>Print Progress:</b> {print_progress}
<b>Print Downloads:</b> {print_downloads}
<b>Print Errors:</b> {print_errors}
<b>Print Warnings:</b> {print_warnings}
<b>Print Skips:</b> {print_skips}

<b>Description:</b>
• <b>Print Progress:</b> Show download progress information
• <b>Print Downloads:</b> Log successful downloads
• <b>Print Errors:</b> Log error messages
• <b>Print Warnings:</b> Log warning messages
• <b>Print Skips:</b> Log skipped files

<b>Note:</b>
These settings control the verbosity of Zotify's logging output during downloads."""

    elif key == "zotify_metadata":
        # Metadata Settings
        metadata_settings = [
            "ZOTIFY_SAVE_METADATA",
            "ZOTIFY_SAVE_GENRE",
            "ZOTIFY_ALL_ARTISTS",
            "ZOTIFY_LYRICS_FILE",
            "ZOTIFY_LYRICS_ONLY",
            "ZOTIFY_SAVE_SUBTITLES",
            "ZOTIFY_CREATE_PLAYLIST_FILE",
        ]

        for setting in metadata_settings:
            display_name = setting.replace("ZOTIFY_", "").replace("_", " ").title()

            # For boolean settings, add toggle buttons with status
            setting_value = getattr(Config, setting, False)
            status = "✅ ON" if setting_value else "❌ OFF"
            display_name = f"{display_name}: {status}"
            buttons.data_button(
                display_name, f"botset toggle {setting} {not setting_value}"
            )

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit zotify_metadata", "footer")
        else:
            buttons.data_button("👁️ View", "botset view zotify_metadata", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_zotify_metadata", "footer"
        )
        buttons.data_button("⬅️ Back", "botset zotify", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current metadata settings
        save_metadata = (
            "✅ Enabled" if Config.ZOTIFY_SAVE_METADATA else "❌ Disabled"
        )
        save_genre = "✅ Enabled" if Config.ZOTIFY_SAVE_GENRE else "❌ Disabled"
        all_artists = "✅ Enabled" if Config.ZOTIFY_ALL_ARTISTS else "❌ Disabled"
        lyrics_file = "✅ Enabled" if Config.ZOTIFY_LYRICS_FILE else "❌ Disabled"
        lyrics_only = "✅ Enabled" if Config.ZOTIFY_LYRICS_ONLY else "❌ Disabled"
        save_subtitles = (
            "✅ Enabled" if Config.ZOTIFY_SAVE_SUBTITLES else "❌ Disabled"
        )
        create_playlist_file = (
            "✅ Enabled" if Config.ZOTIFY_CREATE_PLAYLIST_FILE else "❌ Disabled"
        )

        msg = f"""<b>🎧 Zotify Metadata Settings</b> | State: {state}

<b>Save Metadata:</b> {save_metadata}
<b>Save Genre:</b> {save_genre}
<b>All Artists:</b> {all_artists}
<b>Lyrics File:</b> {lyrics_file}
<b>Lyrics Only:</b> {lyrics_only}
<b>Save Subtitles:</b> {save_subtitles}
<b>Create Playlist File:</b> {create_playlist_file}

<b>Description:</b>
• <b>Save Metadata:</b> Embed metadata tags in downloaded files
• <b>Save Genre:</b> Include genre information in metadata
• <b>All Artists:</b> Include all contributing artists in metadata
• <b>Lyrics File:</b> Save lyrics as separate .lrc files
• <b>Lyrics Only:</b> Download only lyrics without audio
• <b>Save Subtitles:</b> Save podcast subtitles when available
• <b>Create Playlist File:</b> Create .m3u playlist files for playlists

<b>Note:</b>
These settings control what additional information is saved with downloaded content."""

    elif key == "zotify_advanced":
        # Advanced Settings
        advanced_settings = [
            "ZOTIFY_FFMPEG_PATH",
            "ZOTIFY_FFMPEG_ARGS",
            "ZOTIFY_LANGUAGE",
            "ZOTIFY_MATCH_EXISTING",
        ]

        for setting in advanced_settings:
            display_name = setting.replace("ZOTIFY_", "").replace("_", " ").title()

            # For boolean settings, add toggle buttons with status
            if setting in ["ZOTIFY_MATCH_EXISTING"]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit zotify_advanced", "footer")
        else:
            buttons.data_button("👁️ View", "botset view zotify_advanced", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_zotify_advanced", "footer"
        )
        buttons.data_button("⬅️ Back", "botset zotify", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current advanced settings
        ffmpeg_path = Config.ZOTIFY_FFMPEG_PATH or "xtra (Default)"
        ffmpeg_args = Config.ZOTIFY_FFMPEG_ARGS or "None (Default)"
        language = Config.ZOTIFY_LANGUAGE or "en (Default)"
        match_existing = (
            "✅ Enabled" if Config.ZOTIFY_MATCH_EXISTING else "❌ Disabled"
        )

        msg = f"""<b>🎧 Zotify Advanced Settings</b> | State: {state}

<b>FFmpeg Path:</b> <code>{ffmpeg_path}</code>
<b>FFmpeg Args:</b> <code>{ffmpeg_args}</code>
<b>Language:</b> <code>{language}</code>
<b>Match Existing:</b> {match_existing}

<b>Description:</b>
• <b>FFmpeg Path:</b> Custom path to FFmpeg binary (leave empty for auto-detection)
• <b>FFmpeg Args:</b> Additional arguments to pass to FFmpeg during transcoding
• <b>Language:</b> Language code for metadata and interface (ISO 639-1)
• <b>Match Existing:</b> Match existing files for skip functionality

<b>Note:</b>
These are advanced settings that should only be modified if you understand their implications. The default values work for most users."""

    elif key == "youtube":
        # YouTube API Settings section
        buttons.data_button("⚙️ General Settings", "botset youtube_general")
        buttons.data_button("📹 Upload Settings", "botset youtube_upload")
        buttons.data_button("🔐 Authentication", "botset youtube_auth")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        msg = "<b>📺 YouTube API Settings</b>\nSelect a category to configure:"

    elif key == "youtube_general":
        # YouTube General Settings
        general_settings = [
            "YOUTUBE_UPLOAD_DEFAULT_PRIVACY",
            "YOUTUBE_UPLOAD_DEFAULT_CATEGORY",
            "YOUTUBE_UPLOAD_DEFAULT_TAGS",
            "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
        ]

        for setting in general_settings:
            display_name = (
                setting.replace("YOUTUBE_UPLOAD_DEFAULT_", "")
                .replace("_", " ")
                .title()
            )
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit youtube_general", "footer")
        else:
            buttons.data_button("👁️ View", "botset view youtube_general", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_youtube_general", "footer"
        )
        buttons.data_button("⬅️ Back", "botset youtube", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current general settings
        privacy = Config.YOUTUBE_UPLOAD_DEFAULT_PRIVACY or "unlisted (Default)"
        category = Config.YOUTUBE_UPLOAD_DEFAULT_CATEGORY or "22 (Default)"
        tags = Config.YOUTUBE_UPLOAD_DEFAULT_TAGS or "None (Default)"
        description = (
            Config.YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION or "Uploaded by AIM (Default)"
        )

        msg = f"""<b>📺 YouTube General Settings</b> | State: {state}

<b>Default Privacy:</b> <code>{privacy}</code>
<b>Default Category:</b> <code>{category}</code>
<b>Default Tags:</b> <code>{tags}</code>
<b>Default Description:</b> <code>{description}</code>

<b>Description:</b>
• <b>Privacy:</b> Default privacy setting for uploads (public, unlisted, private)
• <b>Category:</b> Default YouTube category ID for uploads
• <b>Tags:</b> Default tags to add to uploads (comma-separated)
• <b>Description:</b> Default description text for uploads

<b>Note:</b>
These are the basic YouTube upload settings that will be used by default."""

    elif key == "youtube_upload":
        # YouTube Upload Settings (Advanced)
        upload_settings = [
            "YOUTUBE_UPLOAD_DEFAULT_TITLE",
            "YOUTUBE_UPLOAD_DEFAULT_LANGUAGE",
            "YOUTUBE_UPLOAD_DEFAULT_LICENSE",
            "YOUTUBE_UPLOAD_EMBEDDABLE",
            "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
            "YOUTUBE_UPLOAD_MADE_FOR_KIDS",
            "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
            "YOUTUBE_UPLOAD_LOCATION_DESCRIPTION",
            "YOUTUBE_UPLOAD_RECORDING_DATE",
            "YOUTUBE_UPLOAD_AUTO_LEVELS",
            "YOUTUBE_UPLOAD_STABILIZE",
        ]

        for setting in upload_settings:
            display_name = (
                setting.replace("YOUTUBE_UPLOAD_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "YOUTUBE_UPLOAD_EMBEDDABLE",
                "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
                "YOUTUBE_UPLOAD_MADE_FOR_KIDS",
                "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
                "YOUTUBE_UPLOAD_AUTO_LEVELS",
                "YOUTUBE_UPLOAD_STABILIZE",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit youtube_upload", "footer")
        else:
            buttons.data_button("👁️ View", "botset view youtube_upload", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_youtube_upload", "footer"
        )
        buttons.data_button("⬅️ Back", "botset youtube", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current upload settings
        title = Config.YOUTUBE_UPLOAD_DEFAULT_TITLE or "Auto-generated (Default)"
        language = Config.YOUTUBE_UPLOAD_DEFAULT_LANGUAGE or "en (Default)"
        license_type = Config.YOUTUBE_UPLOAD_DEFAULT_LICENSE or "youtube (Default)"
        embeddable = (
            "✅ Enabled"
            if getattr(Config, "YOUTUBE_UPLOAD_EMBEDDABLE", True)
            else "❌ Disabled"
        )
        public_stats = (
            "✅ Enabled"
            if getattr(Config, "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE", True)
            else "❌ Disabled"
        )
        made_for_kids = (
            "✅ Enabled"
            if getattr(Config, "YOUTUBE_UPLOAD_MADE_FOR_KIDS", False)
            else "❌ Disabled"
        )
        notify_subscribers = (
            "✅ Enabled"
            if getattr(Config, "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS", True)
            else "❌ Disabled"
        )
        location = Config.YOUTUBE_UPLOAD_LOCATION_DESCRIPTION or "None (Default)"
        recording_date = Config.YOUTUBE_UPLOAD_RECORDING_DATE or "Auto (Default)"
        auto_levels = (
            "✅ Enabled"
            if getattr(Config, "YOUTUBE_UPLOAD_AUTO_LEVELS", False)
            else "❌ Disabled"
        )
        stabilize = (
            "✅ Enabled"
            if getattr(Config, "YOUTUBE_UPLOAD_STABILIZE", False)
            else "❌ Disabled"
        )

        msg = f"""<b>📺 YouTube Upload Settings</b> | State: {state}

<b>Default Title:</b> <code>{title}</code>
<b>Default Language:</b> <code>{language}</code>
<b>Default License:</b> <code>{license_type}</code>
<b>Embeddable:</b> {embeddable}
<b>Public Stats Viewable:</b> {public_stats}
<b>Made For Kids:</b> {made_for_kids}
<b>Notify Subscribers:</b> {notify_subscribers}
<b>Location Description:</b> <code>{location}</code>
<b>Recording Date:</b> <code>{recording_date}</code>
<b>Auto Levels:</b> {auto_levels}
<b>Stabilize:</b> {stabilize}

<b>Description:</b>
• <b>Title:</b> Default title template for uploads
• <b>Language:</b> Default language code for uploads
• <b>License:</b> Default license type for uploads
• <b>Embeddable:</b> Allow videos to be embedded on other websites
• <b>Public Stats Viewable:</b> Allow public viewing of video statistics
• <b>Made For Kids:</b> Mark videos as made for kids (COPPA compliance)
• <b>Notify Subscribers:</b> Send notifications to subscribers when uploading
• <b>Location:</b> Default location description for uploads
• <b>Recording Date:</b> Default recording date for uploads
• <b>Auto Levels:</b> Apply automatic color correction
• <b>Stabilize:</b> Apply automatic video stabilization

<b>Note:</b>
These are advanced YouTube upload settings for fine-tuning video properties."""

    elif key == "youtube_auth":
        # YouTube Authentication Settings
        auth_settings = []

        # Add authentication management buttons
        buttons.data_button("📤 Upload Token", "botset upload_youtube_token")
        buttons.data_button("🗑️ Clear Token", "botset clear_youtube_token")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit youtube_auth", "footer")
        else:
            buttons.data_button("👁️ View", "botset view youtube_auth", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_youtube_auth", "footer"
        )
        buttons.data_button("⬅️ Back", "botset youtube", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Check if YouTube token exists
        youtube_token_path = "youtube_token.pickle"
        token_exists = os.path.exists(youtube_token_path)
        token_status = "✅ Available" if token_exists else "❌ Not Found"

        msg = f"""<b>📺 YouTube Authentication Settings</b> | State: {state}

<b>Token Status:</b> {token_status}

<b>Authentication Methods:</b>
• <b>OAuth2 Token:</b> Upload a pre-generated youtube_token.pickle file
• <b>Interactive:</b> Generate token interactively when needed (fallback)

<b>Token Management:</b>
• <b>Upload Token:</b> Upload a pre-saved YouTube OAuth2 token file
• <b>Clear Token:</b> Remove existing token (will require re-authentication)

<b>Note:</b>
YouTube uploads require OAuth2 authentication. The bot will handle authentication automatically using the configured method.
To generate a token, use the /dev/generate_yt_drive_token.py script."""

    elif key == "mega":
        # MEGA Settings section
        buttons.data_button("⚙️ General Settings", "botset mega_general")
        buttons.data_button("📤 Upload Settings", "botset mega_upload")

        buttons.data_button("🔐 Security Settings", "botset mega_security")

        # Add MEGA Search toggle
        search_enabled = (
            "✅ Enabled" if Config.MEGA_SEARCH_ENABLED else "❌ Disabled"
        )
        buttons.data_button(
            f"🔍 MEGA Search: {search_enabled}",
            f"botset toggle MEGA_SEARCH_ENABLED {not Config.MEGA_SEARCH_ENABLED}",
        )

        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")
        msg = "<b>☁️ MEGA Settings</b>\nSelect a category to configure:"

    elif key == "operations":
        # Operations settings

        # Force refresh all operations settings from database to ensure accurate status
        operations_settings = [
            "BULK_ENABLED",
            "MULTI_LINK_ENABLED",
            "SAME_DIR_ENABLED",
            "MIRROR_ENABLED",
            "LEECH_ENABLED",
            "TORRENT_ENABLED",
            "TORRENT_SEARCH_ENABLED",
            "YTDLP_ENABLED",
            "NZB_ENABLED",
            "NZB_SEARCH_ENABLED",
            "JD_ENABLED",
            "HYPERDL_ENABLED",
            "MEDIA_SEARCH_ENABLED",
            "RCLONE_ENABLED",
            "STREAMRIP_ENABLED",
            "GALLERY_DL_ENABLED",
            "ZOTIFY_ENABLED",
            "GDRIVE_UPLOAD_ENABLED",
            "YOUTUBE_UPLOAD_ENABLED",
            "MEGA_ENABLED",
            "DDL_ENABLED",
            "FILE2LINK_ENABLED",
            "WRONG_CMD_WARNINGS_ENABLED",
            "VT_ENABLED",
            "AD_BROADCASTER_ENABLED",
        ]

        try:
            # Check if database is connected and db attribute exists
            if (
                database.db is not None
                and hasattr(database, "db")
                and hasattr(database.db, "settings")
            ):
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    dict.fromkeys(operations_settings, 1),
                )
                if db_config:
                    # Update the Config object with the current values from database
                    for setting in operations_settings:
                        if setting in db_config:
                            db_value = db_config[setting]
                            if db_value != getattr(Config, setting, None):
                                setattr(Config, setting, db_value)
        except Exception:
            pass

        # Get current operations settings after refresh
        bulk_enabled = "✅ Enabled" if Config.BULK_ENABLED else "❌ Disabled"
        multi_link_enabled = (
            "✅ Enabled" if Config.MULTI_LINK_ENABLED else "❌ Disabled"
        )
        same_dir_enabled = "✅ Enabled" if Config.SAME_DIR_ENABLED else "❌ Disabled"
        mirror_enabled = "✅ Enabled" if Config.MIRROR_ENABLED else "❌ Disabled"
        leech_enabled = "✅ Enabled" if Config.LEECH_ENABLED else "❌ Disabled"
        torrent_enabled = "✅ Enabled" if Config.TORRENT_ENABLED else "❌ Disabled"
        torrent_search_enabled = (
            "✅ Enabled" if Config.TORRENT_SEARCH_ENABLED else "❌ Disabled"
        )
        ytdlp_enabled = "✅ Enabled" if Config.YTDLP_ENABLED else "❌ Disabled"
        nzb_enabled = "✅ Enabled" if Config.NZB_ENABLED else "❌ Disabled"
        nzb_search_enabled = (
            "✅ Enabled" if Config.NZB_SEARCH_ENABLED else "❌ Disabled"
        )
        jd_enabled = "✅ Enabled" if Config.JD_ENABLED else "❌ Disabled"
        hyperdl_enabled = "✅ Enabled" if Config.HYPERDL_ENABLED else "❌ Disabled"
        media_search_enabled = (
            "✅ Enabled" if Config.MEDIA_SEARCH_ENABLED else "❌ Disabled"
        )
        rclone_enabled = "✅ Enabled" if Config.RCLONE_ENABLED else "❌ Disabled"
        streamrip_enabled = (
            "✅ Enabled" if Config.STREAMRIP_ENABLED else "❌ Disabled"
        )
        gallery_dl_enabled = (
            "✅ Enabled" if Config.GALLERY_DL_ENABLED else "❌ Disabled"
        )
        zotify_enabled = "✅ Enabled" if Config.ZOTIFY_ENABLED else "❌ Disabled"
        gdrive_upload_enabled = (
            "✅ Enabled" if Config.GDRIVE_UPLOAD_ENABLED else "❌ Disabled"
        )
        youtube_upload_enabled = (
            "✅ Enabled" if Config.YOUTUBE_UPLOAD_ENABLED else "❌ Disabled"
        )
        mega_enabled = "✅ Enabled" if Config.MEGA_ENABLED else "❌ Disabled"
        ddl_enabled = "✅ Enabled" if Config.DDL_ENABLED else "❌ Disabled"
        file2link_enabled = (
            "✅ Enabled" if Config.FILE2LINK_ENABLED else "❌ Disabled"
        )
        wrong_cmd_warnings_enabled = (
            "✅ Enabled" if Config.WRONG_CMD_WARNINGS_ENABLED else "❌ Disabled"
        )
        virustotal_enabled = "✅ Enabled" if Config.VT_ENABLED else "❌ Disabled"
        ad_broadcaster_enabled = (
            "✅ Enabled" if Config.AD_BROADCASTER_ENABLED else "❌ Disabled"
        )

        # Create toggle buttons for operations
        buttons.data_button(
            f"📦 Bulk Operations: {bulk_enabled}",
            f"botset toggle BULK_ENABLED {not Config.BULK_ENABLED}",
        )
        buttons.data_button(
            f"🔗 Multi-Link Operations: {multi_link_enabled}",
            f"botset toggle MULTI_LINK_ENABLED {not Config.MULTI_LINK_ENABLED}",
        )
        buttons.data_button(
            f"📁 Same Directory Operations: {same_dir_enabled}",
            f"botset toggle SAME_DIR_ENABLED {not Config.SAME_DIR_ENABLED}",
        )
        buttons.data_button(
            f"🪞 Mirror Operations: {mirror_enabled}",
            f"botset toggle MIRROR_ENABLED {not Config.MIRROR_ENABLED}",
        )
        buttons.data_button(
            f"📥 Leech Operations: {leech_enabled}",
            f"botset toggle LEECH_ENABLED {not Config.LEECH_ENABLED}",
        )
        buttons.data_button(
            f"🧲 Torrent Operations: {torrent_enabled}",
            f"botset toggle TORRENT_ENABLED {not Config.TORRENT_ENABLED}",
        )
        buttons.data_button(
            f"🔍 Torrent Search: {torrent_search_enabled}",
            f"botset toggle TORRENT_SEARCH_ENABLED {not Config.TORRENT_SEARCH_ENABLED}",
        )
        buttons.data_button(
            f"📹 YT-DLP Operations: {ytdlp_enabled}",
            f"botset toggle YTDLP_ENABLED {not Config.YTDLP_ENABLED}",
        )
        buttons.data_button(
            f"📦 NZB Operations: {nzb_enabled}",
            f"botset toggle NZB_ENABLED {not Config.NZB_ENABLED}",
        )
        buttons.data_button(
            f"🔍 NZB Search: {nzb_search_enabled}",
            f"botset toggle NZB_SEARCH_ENABLED {not Config.NZB_SEARCH_ENABLED}",
        )
        buttons.data_button(
            f"📥 JDownloader Operations: {jd_enabled}",
            f"botset toggle JD_ENABLED {not Config.JD_ENABLED}",
        )
        buttons.data_button(
            f"⚡ Hyper Download: {hyperdl_enabled}",
            f"botset toggle HYPERDL_ENABLED {not Config.HYPERDL_ENABLED}",
        )
        buttons.data_button(
            f"🔍 Media Search: {media_search_enabled}",
            f"botset toggle MEDIA_SEARCH_ENABLED {not Config.MEDIA_SEARCH_ENABLED}",
        )
        buttons.data_button(
            f"☁️ Rclone Operations: {rclone_enabled}",
            f"botset toggle RCLONE_ENABLED {not Config.RCLONE_ENABLED}",
        )
        buttons.data_button(
            f"🎵 Streamrip Downloads: {streamrip_enabled}",
            f"botset toggle STREAMRIP_ENABLED {not Config.STREAMRIP_ENABLED}",
        )
        buttons.data_button(
            f"🖼️ Gallery-dl Downloads: {gallery_dl_enabled}",
            f"botset toggle GALLERY_DL_ENABLED {not Config.GALLERY_DL_ENABLED}",
        )
        buttons.data_button(
            f"🎧 Zotify Downloads: {zotify_enabled}",
            f"botset toggle ZOTIFY_ENABLED {not Config.ZOTIFY_ENABLED}",
        )
        buttons.data_button(
            f"🗂️ Gdrive Upload: {gdrive_upload_enabled}",
            f"botset toggle GDRIVE_UPLOAD_ENABLED {not Config.GDRIVE_UPLOAD_ENABLED}",
        )
        buttons.data_button(
            f"📺 YouTube Upload: {youtube_upload_enabled}",
            f"botset toggle YOUTUBE_UPLOAD_ENABLED {not Config.YOUTUBE_UPLOAD_ENABLED}",
        )
        buttons.data_button(
            f"☁️ MEGA Operations: {mega_enabled}",
            f"botset toggle MEGA_ENABLED {not Config.MEGA_ENABLED}",
        )
        buttons.data_button(
            f"📤 DDL Operations: {ddl_enabled}",
            f"botset toggle DDL_ENABLED {not Config.DDL_ENABLED}",
        )
        buttons.data_button(
            f"🔗 File2Link: {file2link_enabled}",
            f"botset toggle FILE2LINK_ENABLED {not Config.FILE2LINK_ENABLED}",
        )
        buttons.data_button(
            f"⚠️ Command Warnings: {wrong_cmd_warnings_enabled}",
            f"botset toggle WRONG_CMD_WARNINGS_ENABLED {not Config.WRONG_CMD_WARNINGS_ENABLED}",
        )
        buttons.data_button(
            f"🦠 VirusTotal Scan: {virustotal_enabled}",
            f"botset toggle VT_ENABLED {not Config.VT_ENABLED}",
        )
        buttons.data_button(
            f"📢 Ad Broadcaster: {ad_broadcaster_enabled}",
            f"botset toggle AD_BROADCASTER_ENABLED {not Config.AD_BROADCASTER_ENABLED}",
        )

        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        msg = f"""<b>🔄 Operations Settings</b> | State: {state}

<b>Bulk Operations:</b> {bulk_enabled}
<b>Multi-Link Operations:</b> {multi_link_enabled}
<b>Same Directory Operations:</b> {same_dir_enabled}
<b>Mirror Operations:</b> {mirror_enabled}
<b>Leech Operations:</b> {leech_enabled}
<b>Torrent Operations:</b> {torrent_enabled}
<b>Torrent Search:</b> {torrent_search_enabled}
<b>YT-DLP Operations:</b> {ytdlp_enabled}
<b>NZB Operations:</b> {nzb_enabled}
<b>NZB Search:</b> {nzb_search_enabled}
<b>JDownloader Operations:</b> {jd_enabled}
<b>Hyper Download:</b> {hyperdl_enabled}
<b>Media Search:</b> {media_search_enabled}
<b>Rclone Operations:</b> {rclone_enabled}
<b>Streamrip Downloads:</b> {streamrip_enabled}
<b>Gallery-dl Downloads:</b> {gallery_dl_enabled}
<b>Zotify Downloads:</b> {zotify_enabled}
<b>Gdrive Upload:</b> {gdrive_upload_enabled}
<b>YouTube Upload:</b> {youtube_upload_enabled}
<b>MEGA Operations:</b> {mega_enabled}
<b>DDL Operations:</b> {ddl_enabled}
<b>File2Link:</b> {file2link_enabled}
<b>Command Warnings:</b> {wrong_cmd_warnings_enabled}
<b>VirusTotal Scan:</b> {virustotal_enabled}
<b>Ad Broadcaster:</b> {ad_broadcaster_enabled}

<blockquote expandable><b>📋 Operations Description:</b>
• <b>Bulk Operations:</b> Controls whether users can use the -b flag for bulk operations
• <b>Multi-Link Operations:</b> Controls whether users can process multiple links with the -i flag
• <b>Same Directory Operations:</b> Controls whether users can use the -m flag to save files in the same directory
• <b>Mirror Operations:</b> Controls whether users can use mirror commands
• <b>Leech Operations:</b> Controls whether users can use leech commands
• <b>Torrent Operations:</b> Controls whether users can process torrent files and magnet links
• <b>Torrent Search:</b> Controls whether users can search for torrents
• <b>YT-DLP Operations:</b> Controls whether users can use YT-DLP commands for downloading videos
• <b>NZB Operations:</b> Controls whether users can use NZB commands for downloading from Usenet
• <b>NZB Search:</b> Controls whether users can search for NZB files
• <b>JDownloader Operations:</b> Controls whether users can use JDownloader commands
• <b>Hyper Download:</b> Controls whether users can use Hyper Download for faster Telegram downloads
• <b>Media Search:</b> Controls whether users can search for media in configured channels
• <b>Rclone Operations:</b> Controls whether users can use Rclone for cloud storage operations
• <b>Streamrip Downloads:</b> Controls whether users can download music from streaming platforms (Qobuz, Tidal, Deezer, SoundCloud)
• <b>Gallery-dl Downloads:</b> Controls whether users can download media from 200+ platforms (Instagram, Twitter, Reddit, Pixiv, DeviantArt, etc.)
• <b>Zotify Downloads:</b> Controls whether users can download music from Spotify using Zotify
• <b>YouTube Upload:</b> Controls whether users can upload videos directly to YouTube after downloading
• <b>DDL Operations:</b> Controls whether users can upload files to Direct Download Link servers (Gofile, Streamtape, DevUploads, MediaFire)
• <b>File2Link:</b> Controls whether users can generate streaming and download links for Telegram files with web player support
• <b>Command Warnings:</b> Controls whether warnings are shown for wrong command suffixes
• <b>VirusTotal Scan:</b> Controls whether users can scan files and URLs for viruses using VirusTotal
• <b>Ad Broadcaster:</b> Controls whether the bot automatically broadcasts ads from FSUB channels to users</blockquote>"""

    elif key == "taskmonitor":
        # Group task monitoring settings by category

        # Always use editvar for Task Monitor settings regardless of state
        callback_prefix = "botset editvar"

        # Main settings
        buttons.data_button(
            "⚙️ Enable/Disable", f"{callback_prefix} TASK_MONITOR_ENABLED"
        )
        buttons.data_button(
            "⏱️ Check Interval", f"{callback_prefix} TASK_MONITOR_INTERVAL"
        )
        buttons.data_button(
            "🔄 Consecutive Checks",
            f"{callback_prefix} TASK_MONITOR_CONSECUTIVE_CHECKS",
        )

        # Performance thresholds
        buttons.data_button(
            "⚡ Speed Threshold", f"{callback_prefix} TASK_MONITOR_SPEED_THRESHOLD"
        )
        buttons.data_button(
            "⏳ Elapsed Threshold",
            f"{callback_prefix} TASK_MONITOR_ELAPSED_THRESHOLD",
        )
        buttons.data_button(
            "⏰ ETA Threshold", f"{callback_prefix} TASK_MONITOR_ETA_THRESHOLD"
        )
        buttons.data_button(
            "⌛ Completion Threshold",
            f"{callback_prefix} TASK_MONITOR_COMPLETION_THRESHOLD",
        )
        buttons.data_button(
            "⏲️ Wait Time", f"{callback_prefix} TASK_MONITOR_WAIT_TIME"
        )

        # System resource thresholds
        buttons.data_button(
            "📈 CPU High", f"{callback_prefix} TASK_MONITOR_CPU_HIGH"
        )
        buttons.data_button("📉 CPU Low", f"{callback_prefix} TASK_MONITOR_CPU_LOW")
        buttons.data_button(
            "📊 Memory High", f"{callback_prefix} TASK_MONITOR_MEMORY_HIGH"
        )
        buttons.data_button(
            "📊 Memory Low", f"{callback_prefix} TASK_MONITOR_MEMORY_LOW"
        )

        # No edit/view state for Task Monitor

        buttons.data_button("🔄 Reset to Default", "botset default_taskmonitor")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current task monitoring settings
        monitor_enabled = (
            "✅ Enabled" if Config.TASK_MONITOR_ENABLED else "❌ Disabled"
        )
        monitor_interval = f"{Config.TASK_MONITOR_INTERVAL} seconds"
        monitor_checks = str(Config.TASK_MONITOR_CONSECUTIVE_CHECKS)
        monitor_speed = f"{Config.TASK_MONITOR_SPEED_THRESHOLD} KB/s"
        monitor_elapsed = f"{Config.TASK_MONITOR_ELAPSED_THRESHOLD // 60} minutes"
        monitor_eta = f"{Config.TASK_MONITOR_ETA_THRESHOLD // 3600} hours"
        monitor_wait = f"{Config.TASK_MONITOR_WAIT_TIME // 60} minutes"
        monitor_completion = (
            f"{Config.TASK_MONITOR_COMPLETION_THRESHOLD // 3600} hours"
        )
        monitor_cpu_high = f"{Config.TASK_MONITOR_CPU_HIGH}%"
        monitor_cpu_low = f"{Config.TASK_MONITOR_CPU_LOW}%"
        monitor_memory_high = f"{Config.TASK_MONITOR_MEMORY_HIGH}%"
        monitor_memory_low = f"{Config.TASK_MONITOR_MEMORY_LOW}%"

        msg = f"""<b>Task Monitoring Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {monitor_enabled}
• <b>Check Interval:</b> {monitor_interval}
• <b>Consecutive Checks:</b> {monitor_checks}

<b>Performance Thresholds:</b>
• <b>Speed Threshold:</b> {monitor_speed}
• <b>Elapsed Time Threshold:</b> {monitor_elapsed}
• <b>ETA Threshold:</b> {monitor_eta}
• <b>Completion Time Threshold:</b> {monitor_completion}
• <b>Wait Time Before Cancel:</b> {monitor_wait}

<b>System Resource Thresholds:</b>
• <b>CPU High Threshold:</b> {monitor_cpu_high}
• <b>CPU Low Threshold:</b> {monitor_cpu_low}
• <b>Memory High Threshold:</b> {monitor_memory_high}
• <b>Memory Low Threshold:</b> {monitor_memory_low}

<b>How It Works:</b>
Task Monitor automatically manages downloads based on performance metrics.
• Slow downloads below speed threshold will be warned and potentially cancelled
• Tasks exceeding time thresholds will be flagged for attention
• System resource monitoring helps prevent overloading"""

    elif key == "mega_general":
        # MEGA General Settings
        general_settings = [
            "MEGA_EMAIL",
            "MEGA_PASSWORD",
            "MEGA_LIMIT",
        ]

        for setting in general_settings:
            display_name = setting.replace("MEGA_", "").replace("_", " ").title()
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit mega_general", "footer")
        else:
            buttons.data_button("👁️ View", "botset view mega_general", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_mega_general", "footer"
        )
        buttons.data_button("⬅️ Back", "botset mega", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current general settings
        email = Config.MEGA_EMAIL or "Not configured"
        password = "Configured" if Config.MEGA_PASSWORD else "Not configured"
        limit = f"{Config.MEGA_LIMIT} GB" if Config.MEGA_LIMIT > 0 else "No limit"

        msg = f"""<b>☁️ MEGA General Settings</b> | State: {state}

<b>Email:</b> <code>{email}</code>
<b>Password:</b> <code>{password}</code>
<b>Download Limit:</b> <code>{limit}</code>

<b>Description:</b>
• <b>Email:</b> Your MEGA.nz account email address
• <b>Password:</b> Your MEGA.nz account password
• <b>Download Limit:</b> Maximum size for MEGA downloads in GB (0 = unlimited)

<b>Note:</b>
These credentials are required for MEGA upload and clone operations."""

    elif key == "mega_upload":
        # MEGA Upload Settings
        upload_settings = [
            "MEGA_UPLOAD_ENABLED",
            # "MEGA_UPLOAD_FOLDER" removed - using folder selector instead
            "MEGA_UPLOAD_PUBLIC",
            # "MEGA_UPLOAD_PRIVATE" removed - not supported by MEGA SDK v4.8.0
            # "MEGA_UPLOAD_UNLISTED" removed - not supported by MEGA SDK v4.8.0
            # "MEGA_UPLOAD_EXPIRY_DAYS" removed - premium feature not implemented
            # "MEGA_UPLOAD_PASSWORD" removed - premium feature not implemented
            # "MEGA_UPLOAD_ENCRYPTION_KEY" removed - not supported by MEGA SDK v4.8.0
            "MEGA_UPLOAD_THUMBNAIL",
            # "MEGA_UPLOAD_DELETE_AFTER" removed - always delete after upload
        ]

        for setting in upload_settings:
            display_name = (
                setting.replace("MEGA_UPLOAD_", "").replace("_", " ").title()
            )

            # For boolean settings, add toggle buttons with status
            if setting in [
                "MEGA_UPLOAD_ENABLED",
                "MEGA_UPLOAD_PUBLIC",
                # "MEGA_UPLOAD_PRIVATE" removed - not supported by MEGA SDK v4.8.0
                # "MEGA_UPLOAD_UNLISTED" removed - not supported by MEGA SDK v4.8.0
                "MEGA_UPLOAD_THUMBNAIL",
                # "MEGA_UPLOAD_DELETE_AFTER" removed - always delete after upload
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit mega_upload", "footer")
        else:
            buttons.data_button("👁️ View", "botset view mega_upload", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_mega_upload", "footer"
        )
        buttons.data_button("⬅️ Back", "botset mega", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current upload settings
        enabled = "✅ Enabled" if Config.MEGA_UPLOAD_ENABLED else "❌ Disabled"
        # folder removed - using folder selector instead
        public = "✅ Enabled" if Config.MEGA_UPLOAD_PUBLIC else "❌ Disabled"
        # private, unlisted, expiry, password, encryption removed - not supported by MEGA SDK v4.8.0
        thumbnail = "✅ Enabled" if Config.MEGA_UPLOAD_THUMBNAIL else "❌ Disabled"
        # delete_after removed - always delete after upload

        msg = f"""<b>☁️ MEGA Upload Settings</b> | State: {state}

<b>Status:</b> {enabled}
<b>Upload Folder:</b> <code>📁 Using Folder Selector</code>
<b>Generate Public Links:</b> {public}
<b>Generate Thumbnails:</b> {thumbnail}
<b>Delete After Upload:</b> <code>🗑️ Always Delete</code>

<b>Description:</b>
• <b>Enabled:</b> Master toggle for MEGA upload functionality
• <b>Upload Folder:</b> Interactive folder selection for each upload
• <b>Public Links:</b> Generate public MEGA links with decryption keys
• <b>Generate Thumbnails:</b> Create video thumbnails using FFmpeg
• <b>Delete After Upload:</b> Always delete local files after successful upload

<b>ℹ️ Note:</b> Private/Unlisted links, Password protection, Link expiry, and Custom encryption are not supported by MEGA SDK v4.8.0
• <b>Delete After Upload:</b> Remove local files after successful upload"""

    elif key == "mega_security":
        # MEGA Security Settings - NOT SUPPORTED by MEGA SDK v4.8.0
        buttons.data_button("⬅️ Back", "botset mega", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        msg = f"""<b>☁️ MEGA Security Settings</b> | State: {state}

<b>❌ Advanced Security Features Not Supported</b>

The following MEGA security features are <b>not supported</b> by MEGA SDK v4.8.0:

• <b>❌ Password Protection:</b> Cannot add password protection to uploads
• <b>❌ Custom Encryption Key:</b> MEGA handles encryption automatically
• <b>❌ Link Expiry:</b> Cannot set automatic link expiration
• <b>❌ Private Links:</b> Only public links are supported
• <b>❌ Unlisted Links:</b> Only public links are supported

<b>✅ What IS Supported:</b>
• <b>Public Links:</b> Generate public MEGA links with decryption keys
• <b>Default Encryption:</b> MEGA's built-in end-to-end encryption
• <b>Folder Selection:</b> Interactive folder selection for uploads
• <b>Thumbnails:</b> Video thumbnail generation

<b>ℹ️ Note:</b> These limitations are due to MEGA SDK v4.8.0 capabilities. All uploads still use MEGA's secure end-to-end encryption by default."""

    elif key == "ddl":
        # DDL main menu with subsections for each server
        buttons.data_button("📤 General Settings", "botset ddl_general")
        buttons.data_button("📁 Gofile Settings", "botset ddl_gofile")
        buttons.data_button("🎬 Streamtape Settings", "botset ddl_streamtape")
        buttons.data_button("🚀 DevUploads Settings", "botset ddl_devuploads")
        buttons.data_button("🔥 MediaFire Settings", "botset ddl_mediafire")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ddl")
        else:
            buttons.data_button("👁️ View", "botset view ddl")

        buttons.data_button("🔄 Reset to Default", "botset default_ddl")
        buttons.data_button("⬅️ Back", "botset back", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current DDL settings
        ddl_enabled = "✅ Enabled" if Config.DDL_ENABLED else "❌ Disabled"
        ddl_default_server = Config.DDL_DEFAULT_SERVER or "gofile (Default)"

        # Get API key status
        gofile_api_status = "✅ Set" if Config.GOFILE_API_KEY else "❌ Not Set"
        streamtape_api_status = (
            "✅ Set"
            if (Config.STREAMTAPE_API_USERNAME and Config.STREAMTAPE_API_PASSWORD)
            else "❌ Not Set"
        )
        devuploads_api_status = (
            "✅ Set" if Config.DEVUPLOADS_API_KEY else "❌ Not Set"
        )
        mediafire_api_status = (
            "✅ Set"
            if (
                Config.MEDIAFIRE_EMAIL
                and Config.MEDIAFIRE_PASSWORD
                and Config.MEDIAFIRE_APP_ID
            )
            else "❌ Not Set"
        )

        msg = f"""<b>📤 DDL (Direct Download Link) Settings</b> | State: {state}

<b>General Settings:</b>
• <b>DDL Status:</b> {ddl_enabled}
• <b>Default Server:</b> <code>{ddl_default_server}</code>

<b>Gofile Server:</b>
• <b>API Key:</b> {gofile_api_status}
• <b>Public Links:</b> {"✅ Enabled" if Config.GOFILE_PUBLIC_LINKS else "❌ Disabled"}
• <b>Password Protection:</b> {"✅ Enabled" if Config.GOFILE_PASSWORD_PROTECTION else "❌ Disabled"}

<b>Streamtape Server:</b>
• <b>API Credentials:</b> {streamtape_api_status}

<b>DevUploads Server:</b>
• <b>API Key:</b> {devuploads_api_status}

<b>MediaFire Server:</b>
• <b>API Credentials:</b> {mediafire_api_status}



<b>Usage:</b>
• Use <code>-up ddl</code> to upload to default DDL server
• Use <code>-up ddl:gofile</code> to upload specifically to Gofile
• Use <code>-up ddl:streamtape</code> to upload specifically to Streamtape
• Use <code>-up ddl:devuploads</code> to upload specifically to DevUploads
• Use <code>-up ddl:mediafire</code> to upload specifically to MediaFire


<b>Supported Formats:</b>
• <b>Gofile:</b> All file types supported
• <b>Streamtape:</b> Video files only (.mp4, .mkv, .avi, .mov, .wmv, .flv, .webm, .m4v)
• <b>DevUploads:</b> All file types supported (up to 5GB)
• <b>MediaFire:</b> All file types supported (up to ~50GB)


<i>Configure each server's settings using the buttons above.</i>"""

    elif key == "ddl_general":
        # DDL General Settings
        general_settings = [
            "DDL_DEFAULT_SERVER",
        ]

        for setting in general_settings:
            display_name = setting.replace("DDL_", "").replace("_", " ").title()
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ddl_general")
        else:
            buttons.data_button("👁️ View", "botset view ddl_general")

        buttons.data_button("🔄 Reset to Default", "botset default_ddl_general")
        buttons.data_button("⬅️ Back", "botset ddl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        ddl_default_server = Config.DDL_DEFAULT_SERVER or "gofile (Default)"

        msg = f"""<b>📤 DDL General Settings</b> | State: {state}

<b>Server Configuration:</b>
• <b>Default Server:</b> <code>{ddl_default_server}</code>

<b>Available Servers:</b>
• <b>gofile</b> - Supports all file types, free tier available
• <b>streamtape</b> - Video files only, requires account
• <b>devuploads</b> - Supports all file types, requires API key
• <b>mediafire</b> - Supports all file types, requires account


<b>Note:</b>
The default server will be used when users specify <code>-up ddl</code> without a specific server."""

    elif key == "ddl_gofile":
        # Gofile Settings
        gofile_settings = [
            "GOFILE_API_KEY",
            "GOFILE_FOLDER_NAME",
            "GOFILE_DEFAULT_PASSWORD",
            "GOFILE_LINK_EXPIRY_DAYS",
        ]

        for setting in gofile_settings:
            display_name = setting.replace("GOFILE_", "").replace("_", " ").title()
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Add toggle buttons for boolean settings

        public_links_status = "✅ ON" if Config.GOFILE_PUBLIC_LINKS else "❌ OFF"
        buttons.data_button(
            f"🔗 Public Links: {public_links_status}",
            f"botset toggle GOFILE_PUBLIC_LINKS {not Config.GOFILE_PUBLIC_LINKS}",
        )

        password_protection_status = (
            "✅ ON" if Config.GOFILE_PASSWORD_PROTECTION else "❌ OFF"
        )
        buttons.data_button(
            f"🔒 Password Protection: {password_protection_status}",
            f"botset toggle GOFILE_PASSWORD_PROTECTION {not Config.GOFILE_PASSWORD_PROTECTION}",
        )

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ddl_gofile")
        else:
            buttons.data_button("👁️ View", "botset view ddl_gofile")

        buttons.data_button("🔄 Reset to Default", "botset default_ddl_gofile")
        buttons.data_button("⬅️ Back", "botset ddl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current Gofile settings
        gofile_api_key = "✅ Set" if Config.GOFILE_API_KEY else "❌ Not Set"
        gofile_folder = Config.GOFILE_FOLDER_NAME or "None (Use filename)"
        gofile_public = "✅ Enabled" if Config.GOFILE_PUBLIC_LINKS else "❌ Disabled"
        gofile_password_protection = (
            "✅ Enabled" if Config.GOFILE_PASSWORD_PROTECTION else "❌ Disabled"
        )
        gofile_default_password = Config.GOFILE_DEFAULT_PASSWORD or "None"
        gofile_expiry = Config.GOFILE_LINK_EXPIRY_DAYS or "0 (No expiry)"

        msg = f"""<b>📁 Gofile Server Settings</b> | State: {state}

<b>Authentication:</b>
• <b>API Key:</b> {gofile_api_key}

<b>Upload Settings:</b>
• <b>Folder Name:</b> <code>{gofile_folder}</code>
• <b>Public Links:</b> {gofile_public}
• <b>Password Protection:</b> {gofile_password_protection}
• <b>Default Password:</b> <code>{gofile_default_password}</code>
• <b>Link Expiry (Days):</b> <code>{gofile_expiry}</code>

<b>Features:</b>
• Supports all file types
• Free tier available (with limitations)
• Premium accounts get better speeds and storage
• Password protection available
• Custom expiry dates

<b>Note:</b>
Get your API key from <a href="https://gofile.io/myProfile">Gofile Profile</a>"""

    elif key == "ddl_streamtape":
        # Streamtape Settings
        streamtape_settings = [
            "STREAMTAPE_API_USERNAME",
            "STREAMTAPE_API_PASSWORD",
            "STREAMTAPE_FOLDER_NAME",
        ]

        for setting in streamtape_settings:
            display_name = (
                setting.replace("STREAMTAPE_", "").replace("_", " ").title()
            )
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ddl_streamtape")
        else:
            buttons.data_button("👁️ View", "botset view ddl_streamtape")

        buttons.data_button("🔄 Reset to Default", "botset default_ddl_streamtape")
        buttons.data_button("⬅️ Back", "botset ddl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current Streamtape settings
        streamtape_api_username = (
            "✅ Set" if Config.STREAMTAPE_API_USERNAME else "❌ Not Set"
        )
        streamtape_api_password = (
            "✅ Set" if Config.STREAMTAPE_API_PASSWORD else "❌ Not Set"
        )
        streamtape_folder = Config.STREAMTAPE_FOLDER_NAME or "None (Root folder)"

        msg = f"""<b>🎬 Streamtape Server Settings</b> | State: {state}

<b>Authentication:</b>
• <b>API Username:</b> {streamtape_api_username}
• <b>API Password:</b> {streamtape_api_password}

<b>Upload Settings:</b>
• <b>Folder Name:</b> <code>{streamtape_folder}</code>

<b>Supported Formats:</b>
• Video files only: .mp4, .mkv, .avi, .mov, .wmv, .flv, .webm, .m4v
• Maximum file size depends on account type

<b>Features:</b>
• Fast video streaming
• Direct download links
• Folder organization
• Account required for uploads

<b>Note:</b>
Get your API credentials from <a href="https://streamtape.com/accpanel">Streamtape Account Panel</a>"""

    elif key == "ddl_devuploads":
        # DevUploads Settings
        devuploads_settings = [
            "DEVUPLOADS_API_KEY",
            "DEVUPLOADS_FOLDER_NAME",
        ]

        for setting in devuploads_settings:
            display_name = (
                setting.replace("DEVUPLOADS_", "").replace("_", " ").title()
            )
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Toggle button for public files
        public_files_status = (
            "✅ Public" if Config.DEVUPLOADS_PUBLIC_FILES else "🔒 Private"
        )
        buttons.data_button(
            f"📂 Public Files: {public_files_status}",
            f"botset toggle DEVUPLOADS_PUBLIC_FILES {not Config.DEVUPLOADS_PUBLIC_FILES}",
        )

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ddl_devuploads")
        else:
            buttons.data_button("👁️ View", "botset view ddl_devuploads")

        buttons.data_button("🔄 Reset to Default", "botset default_ddl_devuploads")
        buttons.data_button("⬅️ Back", "botset ddl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current DevUploads settings
        devuploads_api_key = "✅ Set" if Config.DEVUPLOADS_API_KEY else "❌ Not Set"
        devuploads_folder = Config.DEVUPLOADS_FOLDER_NAME or "None (Root folder)"
        devuploads_public = (
            "✅ Public" if Config.DEVUPLOADS_PUBLIC_FILES else "🔒 Private"
        )

        msg = f"""<b>🚀 DevUploads Settings</b> | State: {state}

<b>Authentication:</b>
• <b>API Key:</b> {devuploads_api_key}

<b>Upload Settings:</b>
• <b>Folder Name:</b> <code>{devuploads_folder}</code>
• <b>Public Files:</b> {devuploads_public}

<b>Supported Formats:</b>
• All file types supported
• Maximum file size: 5 GB
• Files expire after 30 days

<b>Features:</b>
• Fast download speeds
• Direct download links
• Folder organization
• Public/Private file settings
• API key required for uploads

<b>Note:</b>
Get your API key from <a href="https://devuploads.com/api">DevUploads API</a>"""

    elif key == "ddl_mediafire":
        # MediaFire Settings
        mediafire_settings = [
            "MEDIAFIRE_EMAIL",
            "MEDIAFIRE_PASSWORD",
            "MEDIAFIRE_APP_ID",
            "MEDIAFIRE_API_KEY",
        ]

        for setting in mediafire_settings:
            display_name = (
                setting.replace("MEDIAFIRE_", "").replace("_", " ").title()
            )
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit ddl_mediafire")
        else:
            buttons.data_button("👁️ View", "botset view ddl_mediafire")

        buttons.data_button("🔄 Reset to Default", "botset default_ddl_mediafire")
        buttons.data_button("⬅️ Back", "botset ddl", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current MediaFire settings
        mediafire_email = "✅ Set" if Config.MEDIAFIRE_EMAIL else "❌ Not Set"
        mediafire_password = "✅ Set" if Config.MEDIAFIRE_PASSWORD else "❌ Not Set"
        mediafire_app_id = "✅ Set" if Config.MEDIAFIRE_APP_ID else "❌ Not Set"
        mediafire_api_key = "✅ Set" if Config.MEDIAFIRE_API_KEY else "❌ Not Set"

        msg = f"""<b>🔥 MediaFire Server Settings</b> | State: {state}

<b>Authentication:</b>
• <b>Email:</b> {mediafire_email}
• <b>Password:</b> {mediafire_password}
• <b>App ID:</b> {mediafire_app_id}
• <b>API Key:</b> {mediafire_api_key}

<b>Supported Formats:</b>
• All file types supported
• Maximum file size: ~50 GB
• Files stored permanently
• Instant upload for duplicate files

<b>Features:</b>
• Large file support (up to 50GB)
• Official API integration
• Instant upload detection
• Hash verification
• Folder organization
• Account required for uploads

<b>Note:</b>
Get your credentials from <a href="https://www.mediafire.com/developers/">MediaFire Developers</a>
Email, Password, and App ID are required. API Key is optional for enhanced features."""

    elif key == "mediatools_watermark":
        # Add buttons for each watermark setting in a 2-column layout
        # Main watermark settings
        main_settings = [
            "WATERMARK_ENABLED",
            "WATERMARK_KEY",  # Renamed to "Text" in the UI
            "WATERMARK_REMOVE_ORIGINAL",  # Renamed to "RO" in the UI
            "WATERMARK_THREADING",
            "WATERMARK_THREAD_NUMBER",
            "WATERMARK_PRIORITY",
            "IMAGE_WATERMARK_ENABLED",
            "IMAGE_WATERMARK_PATH",
        ]

        # Text menu settings (will be in pagination)
        watermark_text_settings = [
            "WATERMARK_POSITION",
            "WATERMARK_SIZE",
            "WATERMARK_COLOR",
            "WATERMARK_FONT",
            "WATERMARK_OPACITY",
            "WATERMARK_QUALITY",  # New numerical value instead of toggle
            "WATERMARK_SPEED",  # New numerical value instead of toggle
            "IMAGE_WATERMARK_SCALE",
            "IMAGE_WATERMARK_POSITION",
            "IMAGE_WATERMARK_OPACITY",
            "AUDIO_WATERMARK_INTERVAL",  # New setting
            "SUBTITLE_WATERMARK_INTERVAL",  # New setting
            "AUDIO_WATERMARK_VOLUME",  # Keeping this as it's useful
            "SUBTITLE_WATERMARK_STYLE",  # Keeping this as it's useful
        ]

        # Create pagination for text menu settings
        watermark_text_page = globals().get("watermark_text_page", 0)
        items_per_page = 10  # 5 rows * 2 columns
        total_pages = (
            len(watermark_text_settings) + items_per_page - 1
        ) // items_per_page

        # Ensure page is valid
        if watermark_text_page >= total_pages:
            watermark_text_page = 0
            globals()["watermark_text_page"] = 0
        elif watermark_text_page < 0:
            watermark_text_page = total_pages - 1
            globals()["watermark_text_page"] = total_pages - 1

        # Combine all settings for the main menu
        watermark_settings = main_settings
        for setting in watermark_settings:
            # Format display names for better readability
            if setting == "WATERMARK_KEY":
                display_name = "Configure"
                # Change the action to open the configure menu instead of editing directly
                buttons.data_button(display_name, "botset watermark_text")
                continue

            # For other settings
            if setting == "WATERMARK_REMOVE_ORIGINAL":
                display_name = "RO"
            elif setting == "IMAGE_WATERMARK_PATH":
                display_name = "Upload Image 🖼️"
                # Change the action to upload an image instead of editing the path
                buttons.data_button(display_name, "botset upload_watermark_image")
                continue
            else:
                display_name = (
                    setting.replace("WATERMARK_", "")
                    .replace("IMAGE_WATERMARK_", "")
                    .replace("_", " ")
                    .title()
                )

            # For boolean settings, add toggle buttons
            if setting == "WATERMARK_ENABLED":
                status = "✅ ON" if Config.WATERMARK_ENABLED else "❌ OFF"
                display_name = f"⚙️ Enabled: {status}"
                buttons.data_button(
                    display_name,
                    f"botset toggle {setting} {not Config.WATERMARK_ENABLED}",
                )
                continue

            if setting == "IMAGE_WATERMARK_ENABLED":
                status = (
                    "✅ ON"
                    if getattr(Config, "IMAGE_WATERMARK_ENABLED", False)
                    else "❌ OFF"
                )
                display_name = f"🖼️ Image Enabled: {status}"
                buttons.data_button(
                    display_name,
                    f"botset toggle {setting} {not getattr(Config, 'IMAGE_WATERMARK_ENABLED', False)}",
                )
                continue

            if setting == "WATERMARK_THREADING":
                # Get the current value
                current_value = getattr(Config, setting)
                status = "✅ ON" if current_value else "❌ OFF"
                display_name = f"⚡ Threading: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not current_value}"
                )
                continue

            if setting == "WATERMARK_REMOVE_ORIGINAL":
                # Get the current value
                current_value = getattr(Config, setting)
                status = "✅ ON" if current_value else "❌ OFF"
                display_name = f"🗑️ Delete Original: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not current_value}"
                )
                continue

            # For all non-boolean settings, add regular edit buttons
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit mediatools_watermark")
        else:
            buttons.data_button("👁️ View", "botset view mediatools_watermark")

        buttons.data_button("🔄 Reset to Default", "botset default_watermark")

        buttons.data_button("⬅️ Back", "botset mediatools", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current watermark settings
        watermark_enabled = (
            "✅ Enabled" if Config.WATERMARK_ENABLED else "❌ Disabled"
        )
        watermark_text = Config.WATERMARK_KEY or "None"
        watermark_position = Config.WATERMARK_POSITION or "top_left (Default)"
        watermark_size = Config.WATERMARK_SIZE or "20 (Default)"
        watermark_color = Config.WATERMARK_COLOR or "white (Default)"
        watermark_font = Config.WATERMARK_FONT or "default.otf (Default)"
        watermark_priority = Config.WATERMARK_PRIORITY or "2 (Default)"
        watermark_threading = (
            "✅ Enabled" if Config.WATERMARK_THREADING else "❌ Disabled"
        )

        # Get image watermark status
        image_watermark_enabled = (
            "✅ Enabled" if Config.IMAGE_WATERMARK_ENABLED else "❌ Disabled"
        )

        # Check if an image watermark exists in the database
        image_watermark_exists = False
        if user_id:
            image_watermark = await get_image_watermark(user_id)
            if image_watermark:
                image_watermark_exists = True

        # Get image watermark path status
        image_watermark_path = "Added" if image_watermark_exists else "None"

        # Update Config.IMAGE_WATERMARK_PATH to match the actual state
        Config.IMAGE_WATERMARK_PATH = "Added" if image_watermark_exists else ""
        watermark_thread_number = Config.WATERMARK_THREAD_NUMBER or "4 (Default)"
        watermark_opacity = Config.WATERMARK_OPACITY or "1.0 (Default)"
        watermark_remove_original = (
            "✅ Enabled" if Config.WATERMARK_REMOVE_ORIGINAL else "❌ Disabled"
        )

        # Get audio volume
        audio_watermark_volume = Config.AUDIO_WATERMARK_VOLUME or "0.3 (Default)"

        # Get quality and speed values
        watermark_quality = getattr(Config, "WATERMARK_QUALITY", "None (Default)")
        watermark_speed = getattr(Config, "WATERMARK_SPEED", "None (Default)")

        # Get audio and subtitle interval values
        audio_interval = getattr(
            Config, "AUDIO_WATERMARK_INTERVAL", "None (Default)"
        )
        subtitle_interval = getattr(
            Config, "SUBTITLE_WATERMARK_INTERVAL", "None (Default)"
        )

        # Get subtitle style
        subtitle_style = getattr(
            Config, "SUBTITLE_WATERMARK_STYLE", "None (Default)"
        )

        # Get image watermark settings
        image_watermark_enabled = (
            "✅ Enabled"
            if getattr(Config, "IMAGE_WATERMARK_ENABLED", False)
            else "❌ Disabled"
        )
        image_watermark_path = getattr(Config, "IMAGE_WATERMARK_PATH", "None")
        image_watermark_scale = getattr(
            Config, "IMAGE_WATERMARK_SCALE", "10 (Default)"
        )
        image_watermark_opacity = getattr(
            Config, "IMAGE_WATERMARK_OPACITY", "1.0 (Default)"
        )
        image_watermark_position = getattr(
            Config, "IMAGE_WATERMARK_POSITION", "bottom_right (Default)"
        )

        # Format the image path display
        image_path_display = image_watermark_path

        msg = f"""<b>Watermark Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {watermark_enabled}
• <b>Text:</b> <code>{watermark_text}</code>
• <b>Priority:</b> <code>{watermark_priority}</code>
• <b>Delete Original:</b> {watermark_remove_original}

<b>Performance:</b>
• <b>Threading:</b> {watermark_threading}
• <b>Thread Number:</b> <code>{watermark_thread_number}</code>
• <b>Quality:</b> <code>{watermark_quality}</code>
• <b>Speed:</b> <code>{watermark_speed}</code>

<b>Image Watermark:</b>
• <b>Status:</b> {image_watermark_enabled}
• <b>Image:</b> <code>{image_path_display}</code>
• <b>Scale:</b> <code>{image_watermark_scale}</code>
• <b>Position:</b> <code>{image_watermark_position}</code>
• <b>Opacity:</b> <code>{image_watermark_opacity}</code>

<b>Text Appearance:</b>
• <b>Position:</b> <code>{watermark_position}</code>
• <b>Size:</b> <code>{watermark_size}</code>
• <b>Color:</b> <code>{watermark_color}</code>
• <b>Font:</b> <code>{watermark_font}</code>
• <b>Opacity:</b> <code>{watermark_opacity}</code>

<b>Audio & Subtitle:</b>
• <b>Audio Volume:</b> <code>{audio_watermark_volume}</code>
• <b>Audio Interval:</b> <code>{audio_interval}</code>
• <b>Subtitle Style:</b> <code>{subtitle_style}</code>
• <b>Subtitle Interval:</b> <code>{subtitle_interval}</code>

<b>Usage:</b>
• Use <code>-watermark</code> flag to apply watermark to media files
• Click <b>Configure</b> button for detailed appearance settings
• Upload an image using <b>Upload Image</b> button for image watermark

<i>These settings will be used when user-specific settings are not available.</i>"""

    elif key == "mediatools_watermark_text":
        # Get all watermark text settings
        watermark_text_settings = [
            # Visual settings
            "WATERMARK_POSITION",
            "WATERMARK_SIZE",
            "WATERMARK_COLOR",
            "WATERMARK_FONT",
            "WATERMARK_OPACITY",
            # Performance settings
            "WATERMARK_QUALITY",
            "WATERMARK_SPEED",
            # Image watermark settings
            "IMAGE_WATERMARK_SCALE",
            "IMAGE_WATERMARK_POSITION",
            "IMAGE_WATERMARK_OPACITY",
            # Audio watermark settings
            "AUDIO_WATERMARK_VOLUME",
            "AUDIO_WATERMARK_INTERVAL",
            # Subtitle watermark settings
            "SUBTITLE_WATERMARK_STYLE",
            "SUBTITLE_WATERMARK_INTERVAL",
        ]

        # Create pagination
        # Use the provided page parameter if available, otherwise use the global variable
        if page != 0:
            watermark_text_page = page
            globals()["watermark_text_page"] = page
        else:
            watermark_text_page = globals().get("watermark_text_page", 0)

        items_per_page = 10  # 5 rows * 2 columns
        total_pages = (
            len(watermark_text_settings) + items_per_page - 1
        ) // items_per_page

        # Ensure page is valid
        if watermark_text_page >= total_pages:
            watermark_text_page = 0
            globals()["watermark_text_page"] = 0
        elif watermark_text_page < 0:
            watermark_text_page = total_pages - 1
            globals()["watermark_text_page"] = total_pages - 1

        # Store the current page in handler_dict for backup
        if user_id:
            handler_dict[f"{user_id}_watermark_page"] = watermark_text_page

        # Get settings for current page
        start_idx = watermark_text_page * items_per_page
        end_idx = min(start_idx + items_per_page, len(watermark_text_settings))
        current_page_settings = watermark_text_settings[start_idx:end_idx]

        # Add buttons for each setting on current page
        for setting in current_page_settings:
            # Format display names for better readability
            if setting.startswith("AUDIO_WATERMARK_"):
                display_name = (
                    "Audio "
                    + setting.replace("AUDIO_WATERMARK_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("SUBTITLE_WATERMARK_"):
                display_name = (
                    "Subtitle "
                    + setting.replace("SUBTITLE_WATERMARK_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("IMAGE_WATERMARK_"):
                display_name = (
                    "Image "
                    + setting.replace("IMAGE_WATERMARK_", "")
                    .replace("_", " ")
                    .title()
                )
            else:
                display_name = (
                    setting.replace("WATERMARK_", "").replace("_", " ").title()
                )

            # For all non-boolean settings, add regular edit buttons
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Add action buttons in a separate row
        if state == "view":
            buttons.data_button(
                "Edit", "botset edit mediatools_watermark_text", "footer"
            )
        else:
            buttons.data_button(
                "View", "botset view mediatools_watermark_text", "footer"
            )

        # Add Default button to reset all watermark text settings to default
        buttons.data_button("Default", "botset default_watermark_text", "footer")

        # Add navigation buttons - back button should always go to the main watermark menu
        # Store the current page to ensure it's preserved when going back
        current_page = globals().get("watermark_text_page", 0)

        # Store the current page in handler_dict for backup if not already done
        if user_id and f"{user_id}_watermark_page" not in handler_dict:
            handler_dict[f"{user_id}_watermark_page"] = current_page

        # Back button should go to the main watermark menu
        buttons.data_button("Back", "botset mediatools_watermark", "footer")
        buttons.data_button("Close", "botset close", "footer")

        # Add pagination buttons in a separate row below action buttons
        if total_pages > 1:
            for i in range(total_pages):
                # Make the current page button different
                if i == watermark_text_page:
                    buttons.data_button(
                        f"[{i + 1}]", f"botset start_watermark_text {i}", "page"
                    )
                else:
                    buttons.data_button(
                        str(i + 1), f"botset start_watermark_text {i}", "page"
                    )

        # Get current watermark settings for display
        watermark_position = Config.WATERMARK_POSITION or "top_left (Default)"
        watermark_size = Config.WATERMARK_SIZE or "20 (Default)"
        watermark_color = Config.WATERMARK_COLOR or "white (Default)"
        watermark_font = Config.WATERMARK_FONT or "default.otf (Default)"
        watermark_opacity = Config.WATERMARK_OPACITY or "1.0 (Default)"
        watermark_quality = getattr(Config, "WATERMARK_QUALITY", "None (Default)")
        watermark_speed = getattr(Config, "WATERMARK_SPEED", "None (Default)")

        # Image watermark settings
        image_watermark_scale = getattr(
            Config, "IMAGE_WATERMARK_SCALE", "10 (Default)"
        )
        image_watermark_position = getattr(
            Config, "IMAGE_WATERMARK_POSITION", "bottom_right (Default)"
        )
        image_watermark_opacity = getattr(
            Config, "IMAGE_WATERMARK_OPACITY", "1.0 (Default)"
        )

        # Audio watermark settings
        audio_watermark_volume = getattr(
            Config, "AUDIO_WATERMARK_VOLUME", "0.3 (Default)"
        )
        audio_watermark_interval = getattr(
            Config, "AUDIO_WATERMARK_INTERVAL", "None (Default)"
        )

        # Subtitle watermark settings
        subtitle_watermark_style = getattr(
            Config, "SUBTITLE_WATERMARK_STYLE", "None (Default)"
        )
        subtitle_watermark_interval = getattr(
            Config, "SUBTITLE_WATERMARK_INTERVAL", "None (Default)"
        )

        # Determine which category is shown on the current page
        categories = []
        if any(
            setting
            in [
                "WATERMARK_POSITION",
                "WATERMARK_SIZE",
                "WATERMARK_COLOR",
                "WATERMARK_FONT",
                "WATERMARK_OPACITY",
            ]
            for setting in current_page_settings
        ):
            categories.append("Visual")
        if any(
            setting in ["WATERMARK_QUALITY", "WATERMARK_SPEED"]
            for setting in current_page_settings
        ):
            categories.append("Performance")
        if any(
            setting.startswith("IMAGE_WATERMARK_")
            for setting in current_page_settings
        ):
            categories.append("Image")
        if any(
            setting.startswith("AUDIO_WATERMARK_")
            for setting in current_page_settings
        ):
            categories.append("Audio")
        if any(
            setting.startswith("SUBTITLE_WATERMARK_")
            for setting in current_page_settings
        ):
            categories.append("Subtitle")

        category_text = ", ".join(categories)

        msg = f"""<b>Watermark Configure Settings</b> | State: {state}

<b>Visual Settings:</b>
• <b>Position:</b> <code>{watermark_position}</code>
• <b>Size:</b> <code>{watermark_size}</code>
• <b>Color:</b> <code>{watermark_color}</code>
• <b>Font:</b> <code>{watermark_font}</code>
• <b>Opacity:</b> <code>{watermark_opacity}</code>

<b>Performance Settings:</b>
• <b>Quality:</b> <code>{watermark_quality}</code>
• <b>Speed:</b> <code>{watermark_speed}</code>

<b>Image Watermark:</b>
• <b>Scale:</b> <code>{image_watermark_scale}</code>
• <b>Position:</b> <code>{image_watermark_position}</code>
• <b>Opacity:</b> <code>{image_watermark_opacity}</code>

<b>Audio Watermark:</b>
• <b>Volume:</b> <code>{audio_watermark_volume}</code>
• <b>Interval:</b> <code>{audio_watermark_interval}</code>

<b>Subtitle Watermark:</b>
• <b>Style:</b> <code>{subtitle_watermark_style}</code>
• <b>Interval:</b> <code>{subtitle_watermark_interval}</code>

Current page shows: {category_text} settings."""

        # Add page info to message
        if total_pages > 1:
            msg += f"\n\n<b>Page:</b> {watermark_text_page + 1}/{total_pages}"

        # Build the menu with 2 columns for settings, 4 columns for action buttons, and 8 columns for pagination
        btns = buttons.build_menu(2, 8, 4, 8)
        return msg, btns

    elif key in {"mediatools_merge", "mediatools_merge_config"}:
        # Get all merge settings and organize them by category
        general_settings = [
            "MERGE_ENABLED",
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
            "MERGE_PRIORITY",
            "MERGE_THREADING",
            "MERGE_THREAD_NUMBER",
            "MERGE_REMOVE_ORIGINAL",
        ]

        # Output formats
        formats = [
            "MERGE_OUTPUT_FORMAT_VIDEO",
            "MERGE_OUTPUT_FORMAT_AUDIO",
            "MERGE_OUTPUT_FORMAT_IMAGE",
            "MERGE_OUTPUT_FORMAT_DOCUMENT",
            "MERGE_OUTPUT_FORMAT_SUBTITLE",
        ]

        # Video settings
        video_settings = [
            "MERGE_VIDEO_CODEC",
            "MERGE_VIDEO_QUALITY",
            "MERGE_VIDEO_PRESET",
            "MERGE_VIDEO_CRF",
            "MERGE_VIDEO_PIXEL_FORMAT",
            "MERGE_VIDEO_TUNE",
            "MERGE_VIDEO_FASTSTART",
        ]

        # Audio settings
        audio_settings = [
            "MERGE_AUDIO_CODEC",
            "MERGE_AUDIO_BITRATE",
            "MERGE_AUDIO_CHANNELS",
            "MERGE_AUDIO_SAMPLING",
            "MERGE_AUDIO_VOLUME",
        ]

        # Image settings
        image_settings = [
            "MERGE_IMAGE_MODE",
            "MERGE_IMAGE_COLUMNS",
            "MERGE_IMAGE_QUALITY",
            "MERGE_IMAGE_DPI",
            "MERGE_IMAGE_RESIZE",
            "MERGE_IMAGE_BACKGROUND",
        ]

        # Subtitle settings
        subtitle_settings = [
            "MERGE_SUBTITLE_ENCODING",
            "MERGE_SUBTITLE_FONT",
            "MERGE_SUBTITLE_FONT_SIZE",
            "MERGE_SUBTITLE_FONT_COLOR",
            "MERGE_SUBTITLE_BACKGROUND",
        ]

        # Document settings
        document_settings = [
            "MERGE_DOCUMENT_PAPER_SIZE",
            "MERGE_DOCUMENT_ORIENTATION",
            "MERGE_DOCUMENT_MARGIN",
        ]

        # Metadata settings
        metadata_settings = [
            "MERGE_METADATA_TITLE",
            "MERGE_METADATA_AUTHOR",
            "MERGE_METADATA_COMMENT",
        ]

        # Combine all settings in a logical order
        merge_settings = (
            general_settings
            + formats
            + video_settings
            + audio_settings
            + image_settings
            + subtitle_settings
            + document_settings
            + metadata_settings
        )

        # 5 rows per page, 2 columns = 10 items per page
        items_per_page = 10  # 5 rows * 2 columns
        total_pages = (len(merge_settings) + items_per_page - 1) // items_per_page

        # Ensure page is valid
        # Use the global merge_page variable if page is not provided
        if key == "mediatools_merge_config" and globals()["merge_config_page"] != 0:
            current_page = globals()["merge_config_page"]
        elif page == 0 and globals()["merge_page"] != 0:
            current_page = globals()["merge_page"]
        else:
            current_page = page
            # Update both global page variables to keep them in sync
            globals()["merge_page"] = current_page
            globals()["merge_config_page"] = current_page

        # Validate page number
        if current_page >= total_pages:
            current_page = 0
            globals()["merge_page"] = 0
            globals()["merge_config_page"] = 0
        elif current_page < 0:
            current_page = total_pages - 1
            globals()["merge_page"] = total_pages - 1
            globals()["merge_config_page"] = total_pages - 1

        # Get settings for current page
        start_idx = current_page * items_per_page
        end_idx = min(start_idx + items_per_page, len(merge_settings))
        current_page_settings = merge_settings[start_idx:end_idx]

        # Add buttons for each setting on current page
        for setting in current_page_settings:
            # Format display names with appropriate emoji prefixes for better UI
            if setting.startswith("MERGE_OUTPUT_FORMAT"):
                prefix = "📄"
                display_name = (
                    setting.replace("MERGE_OUTPUT_FORMAT_", "")
                    .replace("_", " ")
                    .title()
                )
                display_name = f"{prefix} {display_name} Format"
            elif setting.startswith("MERGE_VIDEO_"):
                prefix = "🎬"
                display_name = (
                    setting.replace("MERGE_VIDEO_", "").replace("_", " ").title()
                )
                display_name = f"{prefix} {display_name}"
            elif setting.startswith("MERGE_AUDIO_"):
                prefix = "🔊"
                display_name = (
                    setting.replace("MERGE_AUDIO_", "").replace("_", " ").title()
                )
                display_name = f"{prefix} {display_name}"
            elif setting.startswith("MERGE_IMAGE_"):
                prefix = "🖼️"
                display_name = (
                    setting.replace("MERGE_IMAGE_", "").replace("_", " ").title()
                )
                display_name = f"{prefix} {display_name}"
            elif setting.startswith("MERGE_SUBTITLE_"):
                prefix = "💬"
                display_name = (
                    setting.replace("MERGE_SUBTITLE_", "").replace("_", " ").title()
                )
                display_name = f"{prefix} {display_name}"
            elif setting.startswith("MERGE_DOCUMENT_"):
                prefix = "📑"
                display_name = (
                    setting.replace("MERGE_DOCUMENT_", "").replace("_", " ").title()
                )
                display_name = f"{prefix} {display_name}"
            elif setting.startswith("MERGE_METADATA_"):
                prefix = "📝"
                display_name = (
                    setting.replace("MERGE_METADATA_", "").replace("_", " ").title()
                )
                display_name = f"{prefix} {display_name}"
            elif setting.startswith(("CONCAT", "FILTER")):
                prefix = "🔄"
                display_name = setting.replace("_ENABLED", "").title()
                display_name = f"{prefix} {display_name}"
            elif setting == "MERGE_ENABLED":
                # Skip this as it's handled separately
                continue
            elif setting == "MERGE_PRIORITY":
                prefix = "🔢"
                display_name = f"{prefix} Priority"
            elif setting == "MERGE_THREADING":
                prefix = "⚡"
                display_name = f"{prefix} Threading"
            elif setting == "MERGE_THREAD_NUMBER":
                prefix = "🧵"
                display_name = f"{prefix} Thread Number"
            elif setting == "MERGE_REMOVE_ORIGINAL":
                prefix = "🗑️"
                display_name = f"{prefix} Remove Original"
            else:
                prefix = "⚙️"
                display_name = (
                    setting.replace("MERGE_", "").replace("_", " ").title()
                )
                display_name = f"{prefix} {display_name}"

            # For boolean settings, add toggle buttons with status
            if setting in [
                "MERGE_THREADING",
                "MERGE_REMOVE_ORIGINAL",
                "MERGE_VIDEO_FASTSTART",
                "CONCAT_DEMUXER_ENABLED",
                "FILTER_COMPLEX_ENABLED",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        # Add action buttons in a separate row
        # Add Edit/View button with consistent styling
        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit mediatools_merge", "footer")
        else:
            buttons.data_button("👁️ View", "botset view mediatools_merge", "footer")

        # Add Default button with consistent styling
        buttons.data_button("🔄 Reset to Default", "botset default_merge", "footer")

        # Add navigation buttons with consistent styling
        buttons.data_button("⬅️ Back", "botset mediatools", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Add pagination buttons in a separate row below action buttons
        if total_pages > 1:
            for i in range(total_pages):
                # Make the current page button different
                if i == current_page:
                    buttons.data_button(
                        f"[{i + 1}]", f"botset start_merge {i}", "page"
                    )
                else:
                    buttons.data_button(
                        str(i + 1), f"botset start_merge {i}", "page"
                    )

            # Add a debug log message# Get current merge settings
        merge_enabled = "✅ Enabled" if Config.MERGE_ENABLED else "❌ Disabled"
        concat_demuxer = (
            "✅ Enabled" if Config.CONCAT_DEMUXER_ENABLED else "❌ Disabled"
        )
        filter_complex = (
            "✅ Enabled" if Config.FILTER_COMPLEX_ENABLED else "❌ Disabled"
        )
        video_format = Config.MERGE_OUTPUT_FORMAT_VIDEO or "mkv (Default)"
        audio_format = Config.MERGE_OUTPUT_FORMAT_AUDIO or "mp3 (Default)"
        merge_priority = Config.MERGE_PRIORITY or "1 (Default)"
        merge_threading = "✅ Enabled" if Config.MERGE_THREADING else "❌ Disabled"
        merge_thread_number = Config.MERGE_THREAD_NUMBER or "4 (Default)"
        merge_remove_original = (
            "✅ Enabled" if Config.MERGE_REMOVE_ORIGINAL else "❌ Disabled"
        )

        # Determine which category is shown on the current page
        start_idx = current_page * items_per_page
        end_idx = min(start_idx + items_per_page, len(merge_settings))

        # Get the categories shown on the current page
        categories = []
        if any(
            setting in general_settings
            for setting in merge_settings[start_idx:end_idx]
        ):
            categories.append("General")
        if any(setting in formats for setting in merge_settings[start_idx:end_idx]):
            categories.append("Formats")
        if any(
            setting in video_settings
            for setting in merge_settings[start_idx:end_idx]
        ):
            categories.append("Video")
        if any(
            setting in audio_settings
            for setting in merge_settings[start_idx:end_idx]
        ):
            categories.append("Audio")
        if any(
            setting in image_settings
            for setting in merge_settings[start_idx:end_idx]
        ):
            categories.append("Image")
        if any(
            setting in subtitle_settings
            for setting in merge_settings[start_idx:end_idx]
        ):
            categories.append("Subtitle")
        if any(
            setting in document_settings
            for setting in merge_settings[start_idx:end_idx]
        ):
            categories.append("Document")
        if any(
            setting in metadata_settings
            for setting in merge_settings[start_idx:end_idx]
        ):
            categories.append("Metadata")

        category_text = ", ".join(categories)

        msg = f"""<b>Merge Settings</b> | State: {state}

<b>Status:</b> {merge_enabled}
<b>Concat Demuxer:</b> {concat_demuxer}
<b>Filter Complex:</b> {filter_complex}
<b>Video Format:</b> <code>{video_format}</code>
<b>Audio Format:</b> <code>{audio_format}</code>
<b>Priority:</b> <code>{merge_priority}</code>
<b>Threading:</b> {merge_threading}
<b>Thread Number:</b> <code>{merge_thread_number}</code>
<b>RO:</b> {merge_remove_original}

Configure global merge settings that will be used when user settings are not available.
Current page shows: {category_text} settings."""

        # Add page info to message
        if total_pages > 1:
            msg += f"\n\n<b>Page:</b> {current_page + 1}/{total_pages}"

        # Build the menu with 2 columns for settings, 4 columns for action buttons, and 8 columns for pagination
        btns = buttons.build_menu(2, 8, 4, 8)
        return msg, btns

    elif key == "mediatools_extract":
        # Add buttons for extract settings
        # General extract settings
        general_settings = [
            "EXTRACT_ENABLED",
            "EXTRACT_PRIORITY",
            "EXTRACT_DELETE_ORIGINAL",
        ]

        # Video extract settings
        video_settings = [
            "EXTRACT_VIDEO_ENABLED",
            "EXTRACT_VIDEO_CODEC",
            "EXTRACT_VIDEO_FORMAT",
            "EXTRACT_VIDEO_INDEX",
            "EXTRACT_VIDEO_QUALITY",
            "EXTRACT_VIDEO_PRESET",
            "EXTRACT_VIDEO_BITRATE",
            "EXTRACT_VIDEO_RESOLUTION",
            "EXTRACT_VIDEO_FPS",
        ]

        # Audio extract settings
        audio_settings = [
            "EXTRACT_AUDIO_ENABLED",
            "EXTRACT_AUDIO_CODEC",
            "EXTRACT_AUDIO_FORMAT",
            "EXTRACT_AUDIO_INDEX",
            "EXTRACT_AUDIO_BITRATE",
            "EXTRACT_AUDIO_CHANNELS",
            "EXTRACT_AUDIO_SAMPLING",
            "EXTRACT_AUDIO_VOLUME",
        ]

        # Subtitle extract settings
        subtitle_settings = [
            "EXTRACT_SUBTITLE_ENABLED",
            "EXTRACT_SUBTITLE_CODEC",
            "EXTRACT_SUBTITLE_FORMAT",
            "EXTRACT_SUBTITLE_INDEX",
            "EXTRACT_SUBTITLE_LANGUAGE",
            "EXTRACT_SUBTITLE_ENCODING",
            "EXTRACT_SUBTITLE_FONT",
            "EXTRACT_SUBTITLE_FONT_SIZE",
        ]

        # Attachment extract settings
        attachment_settings = [
            "EXTRACT_ATTACHMENT_ENABLED",
            "EXTRACT_ATTACHMENT_FORMAT",
            "EXTRACT_ATTACHMENT_INDEX",
            "EXTRACT_ATTACHMENT_FILTER",
        ]

        # Quality settings
        quality_settings = [
            "EXTRACT_MAINTAIN_QUALITY",
        ]

        # Combine all settings
        extract_settings = (
            general_settings
            + video_settings
            + audio_settings
            + subtitle_settings
            + attachment_settings
            + quality_settings
        )

        for setting in extract_settings:
            # Create display name based on setting type with emojis for better UI
            if setting.startswith("EXTRACT_VIDEO_"):
                prefix = "🎬"
                display_name = (
                    f"{prefix} Video "
                    + setting.replace("EXTRACT_VIDEO_", "").replace("_", " ").title()
                )
            elif setting.startswith("EXTRACT_AUDIO_"):
                prefix = "🔊"
                display_name = (
                    f"{prefix} Audio "
                    + setting.replace("EXTRACT_AUDIO_", "").replace("_", " ").title()
                )
            elif setting.startswith("EXTRACT_SUBTITLE_"):
                prefix = "💬"
                display_name = (
                    f"{prefix} Subtitle "
                    + setting.replace("EXTRACT_SUBTITLE_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("EXTRACT_ATTACHMENT_"):
                prefix = "📎"
                display_name = (
                    f"{prefix} Attachment "
                    + setting.replace("EXTRACT_ATTACHMENT_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting == "EXTRACT_PRIORITY":
                display_name = "🔢 Priority"
            elif setting == "EXTRACT_DELETE_ORIGINAL":
                display_name = "🗑️ Delete Original"
            else:
                prefix = "⚙️"
                display_name = (
                    f"{prefix} "
                    + setting.replace("EXTRACT_", "").replace("_", " ").title()
                )

            # For boolean settings, add toggle buttons
            if setting in [
                "EXTRACT_ENABLED",
                "EXTRACT_VIDEO_ENABLED",
                "EXTRACT_AUDIO_ENABLED",
                "EXTRACT_SUBTITLE_ENABLED",
                "EXTRACT_ATTACHMENT_ENABLED",
                "EXTRACT_MAINTAIN_QUALITY",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"

                # Format display name with status and emojis for better UI
                if setting == "EXTRACT_ENABLED":
                    display_name = f"⚙️ Enabled: {status}"
                elif setting == "EXTRACT_VIDEO_ENABLED":
                    display_name = f"🎬 Video Enabled: {status}"
                elif setting == "EXTRACT_AUDIO_ENABLED":
                    display_name = f"🔊 Audio Enabled: {status}"
                elif setting == "EXTRACT_SUBTITLE_ENABLED":
                    display_name = f"💬 Subtitle Enabled: {status}"
                elif setting == "EXTRACT_ATTACHMENT_ENABLED":
                    display_name = f"📎 Attachment Enabled: {status}"
                elif setting == "EXTRACT_MAINTAIN_QUALITY":
                    display_name = f"✨ Maintain Quality: {status}"
                elif setting == "EXTRACT_DELETE_ORIGINAL":
                    display_name = f"🗑️ Delete Original: {status}"
                else:
                    display_name = f"{display_name}: {status}"

                # Create toggle button
                buttons.data_button(
                    display_name,
                    f"botset toggle {setting} {not setting_value}",
                )
                continue

            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit mediatools_extract", "footer")
        else:
            buttons.data_button("👁️ View", "botset view mediatools_extract", "footer")

        buttons.data_button(
            "🔄 Reset to Default", "botset default_extract", "footer"
        )

        buttons.data_button("⬅️ Back", "botset mediatools", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current extract settings
        extract_enabled = "✅ Enabled" if Config.EXTRACT_ENABLED else "❌ Disabled"
        extract_priority = f"{Config.EXTRACT_PRIORITY}"
        extract_delete_original = (
            "✅ Enabled" if Config.EXTRACT_DELETE_ORIGINAL else "❌ Disabled"
        )

        # Video settings
        video_enabled = (
            "✅ Enabled" if Config.EXTRACT_VIDEO_ENABLED else "❌ Disabled"
        )
        video_codec = Config.EXTRACT_VIDEO_CODEC or "None"
        video_format = Config.EXTRACT_VIDEO_FORMAT or "None"
        video_index = Config.EXTRACT_VIDEO_INDEX or "All"
        video_quality = Config.EXTRACT_VIDEO_QUALITY or "None"
        video_preset = Config.EXTRACT_VIDEO_PRESET or "None"
        video_bitrate = Config.EXTRACT_VIDEO_BITRATE or "None"
        video_resolution = Config.EXTRACT_VIDEO_RESOLUTION or "None"
        video_fps = Config.EXTRACT_VIDEO_FPS or "None"

        # Audio settings
        audio_enabled = (
            "✅ Enabled" if Config.EXTRACT_AUDIO_ENABLED else "❌ Disabled"
        )
        audio_codec = Config.EXTRACT_AUDIO_CODEC or "None"
        audio_format = Config.EXTRACT_AUDIO_FORMAT or "None"
        audio_index = Config.EXTRACT_AUDIO_INDEX or "All"
        audio_bitrate = Config.EXTRACT_AUDIO_BITRATE or "None"
        audio_channels = Config.EXTRACT_AUDIO_CHANNELS or "None"
        audio_sampling = Config.EXTRACT_AUDIO_SAMPLING or "None"
        audio_volume = Config.EXTRACT_AUDIO_VOLUME or "None"

        # Subtitle settings
        subtitle_enabled = (
            "✅ Enabled" if Config.EXTRACT_SUBTITLE_ENABLED else "❌ Disabled"
        )
        subtitle_codec = Config.EXTRACT_SUBTITLE_CODEC or "None"
        subtitle_format = Config.EXTRACT_SUBTITLE_FORMAT or "None"
        subtitle_index = Config.EXTRACT_SUBTITLE_INDEX or "All"
        subtitle_language = Config.EXTRACT_SUBTITLE_LANGUAGE or "None"
        subtitle_encoding = Config.EXTRACT_SUBTITLE_ENCODING or "None"
        subtitle_font = Config.EXTRACT_SUBTITLE_FONT or "None"
        subtitle_font_size = Config.EXTRACT_SUBTITLE_FONT_SIZE or "None"

        # Attachment settings
        attachment_enabled = (
            "✅ Enabled" if Config.EXTRACT_ATTACHMENT_ENABLED else "❌ Disabled"
        )
        attachment_format = Config.EXTRACT_ATTACHMENT_FORMAT or "None"
        attachment_index = Config.EXTRACT_ATTACHMENT_INDEX or "All"
        attachment_filter = Config.EXTRACT_ATTACHMENT_FILTER or "None"

        # Quality settings
        maintain_quality = (
            "✅ Enabled" if Config.EXTRACT_MAINTAIN_QUALITY else "❌ Disabled"
        )

        msg = f"""<b>Extract Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {extract_enabled}
• <b>Priority:</b> <code>{extract_priority}</code>
• <b>RO:</b> {extract_delete_original}

<b>Video Extract Settings:</b>
• <b>Status:</b> {video_enabled}
• <b>Codec:</b> <code>{video_codec}</code>
• <b>Format:</b> <code>{video_format}</code>
• <b>Index:</b> <code>{video_index}</code>
• <b>Quality:</b> <code>{video_quality}</code>
• <b>Preset:</b> <code>{video_preset}</code>
• <b>Bitrate:</b> <code>{video_bitrate}</code>
• <b>Resolution:</b> <code>{video_resolution}</code>
• <b>FPS:</b> <code>{video_fps}</code>

<b>Audio Extract Settings:</b>
• <b>Status:</b> {audio_enabled}
• <b>Codec:</b> <code>{audio_codec}</code>
• <b>Format:</b> <code>{audio_format}</code>
• <b>Index:</b> <code>{audio_index}</code>
• <b>Bitrate:</b> <code>{audio_bitrate}</code>
• <b>Channels:</b> <code>{audio_channels}</code>
• <b>Sampling:</b> <code>{audio_sampling}</code>
• <b>Volume:</b> <code>{audio_volume}</code>

<b>Subtitle Extract Settings:</b>
• <b>Status:</b> {subtitle_enabled}
• <b>Codec:</b> <code>{subtitle_codec}</code>
• <b>Format:</b> <code>{subtitle_format}</code>
• <b>Index:</b> <code>{subtitle_index}</code>
• <b>Language:</b> <code>{subtitle_language}</code>
• <b>Encoding:</b> <code>{subtitle_encoding}</code>
• <b>Font:</b> <code>{subtitle_font}</code>
• <b>Font Size:</b> <code>{subtitle_font_size}</code>

<b>Attachment Extract Settings:</b>
• <b>Status:</b> {attachment_enabled}
• <b>Format:</b> <code>{attachment_format}</code>
• <b>Index:</b> <code>{attachment_index}</code>
• <b>Filter:</b> <code>{attachment_filter}</code>

<b>Quality Settings:</b>
• <b>Maintain Quality:</b> {maintain_quality}

<b>Usage:</b>
• Main Extract toggle must be enabled
• Media type specific toggles must be enabled for respective extractions
• Use <code>-extract</code> to enable extraction
• Use <code>-extract-video</code>, <code>-extract-audio</code>, etc. for specific track types
• Use <code>-extract-video-index 0</code> to extract specific track by index
• Add <code>-del</code> to delete original files after extraction
• Settings with value 'None' will not be used in command generation

Configure global extract settings that will be used when user settings are not available."""

    elif key == "mediatools_remove":
        # Add buttons for remove settings
        # General remove settings
        general_settings = [
            "REMOVE_ENABLED",
            "REMOVE_PRIORITY",
            "REMOVE_DELETE_ORIGINAL",
            "REMOVE_METADATA",
            "REMOVE_MAINTAIN_QUALITY",
        ]

        # Video remove settings
        video_settings = [
            "REMOVE_VIDEO_ENABLED",
            "REMOVE_VIDEO_CODEC",
            "REMOVE_VIDEO_FORMAT",
            "REMOVE_VIDEO_INDEX",
            "REMOVE_VIDEO_QUALITY",
            "REMOVE_VIDEO_PRESET",
            "REMOVE_VIDEO_BITRATE",
            "REMOVE_VIDEO_RESOLUTION",
            "REMOVE_VIDEO_FPS",
        ]

        # Audio remove settings
        audio_settings = [
            "REMOVE_AUDIO_ENABLED",
            "REMOVE_AUDIO_CODEC",
            "REMOVE_AUDIO_FORMAT",
            "REMOVE_AUDIO_INDEX",
            "REMOVE_AUDIO_BITRATE",
            "REMOVE_AUDIO_CHANNELS",
            "REMOVE_AUDIO_SAMPLING",
            "REMOVE_AUDIO_VOLUME",
        ]

        # Subtitle remove settings
        subtitle_settings = [
            "REMOVE_SUBTITLE_ENABLED",
            "REMOVE_SUBTITLE_CODEC",
            "REMOVE_SUBTITLE_FORMAT",
            "REMOVE_SUBTITLE_INDEX",
            "REMOVE_SUBTITLE_LANGUAGE",
            "REMOVE_SUBTITLE_ENCODING",
            "REMOVE_SUBTITLE_FONT",
            "REMOVE_SUBTITLE_FONT_SIZE",
        ]

        # Attachment remove settings
        attachment_settings = [
            "REMOVE_ATTACHMENT_ENABLED",
            "REMOVE_ATTACHMENT_FORMAT",
            "REMOVE_ATTACHMENT_INDEX",
            "REMOVE_ATTACHMENT_FILTER",
        ]

        # Combine all settings
        remove_settings = (
            general_settings
            + video_settings
            + audio_settings
            + subtitle_settings
            + attachment_settings
        )

        for setting in remove_settings:
            # Create display name based on setting type with emojis for better UI
            if setting.startswith("REMOVE_VIDEO_"):
                prefix = "🎬"
                display_name = (
                    f"{prefix} Video "
                    + setting.replace("REMOVE_VIDEO_", "").replace("_", " ").title()
                )
            elif setting.startswith("REMOVE_AUDIO_"):
                prefix = "🎵"
                display_name = (
                    f"{prefix} Audio "
                    + setting.replace("REMOVE_AUDIO_", "").replace("_", " ").title()
                )
            elif setting.startswith("REMOVE_SUBTITLE_"):
                prefix = "📝"
                display_name = (
                    f"{prefix} Subtitle "
                    + setting.replace("REMOVE_SUBTITLE_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("REMOVE_ATTACHMENT_"):
                prefix = "📎"
                display_name = (
                    f"{prefix} Attachment "
                    + setting.replace("REMOVE_ATTACHMENT_", "")
                    .replace("_", " ")
                    .title()
                )
            else:
                # General settings
                display_name = (
                    setting.replace("REMOVE_", "").replace("_", " ").title()
                )

            # For boolean settings, add toggle buttons with status
            if setting.endswith("_ENABLED") or setting in [
                "REMOVE_DELETE_ORIGINAL",
                "REMOVE_METADATA",
                "REMOVE_MAINTAIN_QUALITY",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"
                display_name = f"{display_name}: {status}"
                buttons.data_button(
                    display_name, f"botset toggle {setting} {not setting_value}"
                )
            else:
                # For non-boolean settings, use editvar
                buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit mediatools_remove")
        else:
            buttons.data_button("👁️ View", "botset view mediatools_remove")

        buttons.data_button("🔄 Reset to Default", "botset default_remove")

        buttons.data_button("⬅️ Back", "botset mediatools", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current remove settings
        remove_enabled = "✅ Enabled" if Config.REMOVE_ENABLED else "❌ Disabled"
        remove_priority = f"{Config.REMOVE_PRIORITY}"
        remove_delete_original = (
            "✅ Enabled" if Config.REMOVE_DELETE_ORIGINAL else "❌ Disabled"
        )
        remove_metadata = "✅ Enabled" if Config.REMOVE_METADATA else "❌ Disabled"
        maintain_quality = (
            "✅ Enabled" if Config.REMOVE_MAINTAIN_QUALITY else "❌ Disabled"
        )

        # Video remove settings
        video_enabled = (
            "✅ Enabled" if Config.REMOVE_VIDEO_ENABLED else "❌ Disabled"
        )
        video_codec = Config.REMOVE_VIDEO_CODEC or "None"
        video_format = Config.REMOVE_VIDEO_FORMAT or "None"
        video_index = Config.REMOVE_VIDEO_INDEX or "All"
        video_quality = Config.REMOVE_VIDEO_QUALITY or "None"
        video_preset = Config.REMOVE_VIDEO_PRESET or "None"
        video_bitrate = Config.REMOVE_VIDEO_BITRATE or "None"
        video_resolution = Config.REMOVE_VIDEO_RESOLUTION or "None"
        video_fps = Config.REMOVE_VIDEO_FPS or "None"

        # Audio remove settings
        audio_enabled = (
            "✅ Enabled" if Config.REMOVE_AUDIO_ENABLED else "❌ Disabled"
        )
        audio_codec = Config.REMOVE_AUDIO_CODEC or "None"
        audio_format = Config.REMOVE_AUDIO_FORMAT or "None"
        audio_index = Config.REMOVE_AUDIO_INDEX or "All"
        audio_bitrate = Config.REMOVE_AUDIO_BITRATE or "None"
        audio_channels = Config.REMOVE_AUDIO_CHANNELS or "None"
        audio_sampling = Config.REMOVE_AUDIO_SAMPLING or "None"
        audio_volume = Config.REMOVE_AUDIO_VOLUME or "None"

        # Subtitle remove settings
        subtitle_enabled = (
            "✅ Enabled" if Config.REMOVE_SUBTITLE_ENABLED else "❌ Disabled"
        )
        subtitle_codec = Config.REMOVE_SUBTITLE_CODEC or "None"
        subtitle_format = Config.REMOVE_SUBTITLE_FORMAT or "None"
        subtitle_index = Config.REMOVE_SUBTITLE_INDEX or "All"
        subtitle_language = Config.REMOVE_SUBTITLE_LANGUAGE or "None"
        subtitle_encoding = Config.REMOVE_SUBTITLE_ENCODING or "None"
        subtitle_font = Config.REMOVE_SUBTITLE_FONT or "None"
        subtitle_font_size = Config.REMOVE_SUBTITLE_FONT_SIZE or "None"

        # Attachment remove settings
        attachment_enabled = (
            "✅ Enabled" if Config.REMOVE_ATTACHMENT_ENABLED else "❌ Disabled"
        )
        attachment_format = Config.REMOVE_ATTACHMENT_FORMAT or "None"
        attachment_index = Config.REMOVE_ATTACHMENT_INDEX or "All"
        attachment_filter = Config.REMOVE_ATTACHMENT_FILTER or "None"

        msg = f"""<b>Remove Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {remove_enabled}
• <b>Priority:</b> <code>{remove_priority}</code>
• <b>RO:</b> {remove_delete_original}
• <b>Metadata:</b> {remove_metadata}
• <b>Quality:</b> {maintain_quality}

<b>Video Remove Settings:</b>
• <b>Status:</b> {video_enabled}
• <b>Codec:</b> <code>{video_codec}</code>
• <b>Format:</b> <code>{video_format}</code>
• <b>Index:</b> <code>{video_index}</code>
• <b>Quality:</b> <code>{video_quality}</code>
• <b>Preset:</b> <code>{video_preset}</code>
• <b>Bitrate:</b> <code>{video_bitrate}</code>
• <b>Resolution:</b> <code>{video_resolution}</code>
• <b>FPS:</b> <code>{video_fps}</code>

<b>Audio Remove Settings:</b>
• <b>Status:</b> {audio_enabled}
• <b>Codec:</b> <code>{audio_codec}</code>
• <b>Format:</b> <code>{audio_format}</code>
• <b>Index:</b> <code>{audio_index}</code>
• <b>Bitrate:</b> <code>{audio_bitrate}</code>
• <b>Channels:</b> <code>{audio_channels}</code>
• <b>Sampling:</b> <code>{audio_sampling}</code>
• <b>Volume:</b> <code>{audio_volume}</code>

<b>Subtitle Remove Settings:</b>
• <b>Status:</b> {subtitle_enabled}
• <b>Codec:</b> <code>{subtitle_codec}</code>
• <b>Format:</b> <code>{subtitle_format}</code>
• <b>Index:</b> <code>{subtitle_index}</code>
• <b>Language:</b> <code>{subtitle_language}</code>
• <b>Encoding:</b> <code>{subtitle_encoding}</code>
• <b>Font:</b> <code>{subtitle_font}</code>
• <b>Font Size:</b> <code>{subtitle_font_size}</code>

<b>Attachment Remove Settings:</b>
• <b>Status:</b> {attachment_enabled}
• <b>Format:</b> <code>{attachment_format}</code>
• <b>Index:</b> <code>{attachment_index}</code>
• <b>Filter:</b> <code>{attachment_filter}</code>

<b>Usage:</b>
• Main Remove toggle must be enabled
• Enable specific track types to remove them
• Use <code>-remove</code> to enable removal
• Use <code>-remove-video</code>, <code>-remove-audio</code>, etc. for specific track types
• Use <code>-remove-video-index 0</code> to remove specific track by index
• Use <code>-remove-metadata</code> to remove metadata
• Add <code>-del</code> to delete original files after removal
• Settings with value 'None' will not be used in command generation

Configure global remove settings that will be used when user settings are not available."""

    elif key == "mediatools_add":
        # Add buttons for add settings
        # General add settings
        general_settings = [
            "ADD_ENABLED",
            "ADD_PRIORITY",
            "ADD_DELETE_ORIGINAL",
            "ADD_PRESERVE_TRACKS",
            "ADD_REPLACE_TRACKS",
        ]

        # Add special handling for preserve and replace toggles
        # We'll implement the toggle behavior in the toggle handler

        # Video add settings
        video_settings = [
            "ADD_VIDEO_ENABLED",
            "ADD_VIDEO_CODEC",
            "ADD_VIDEO_INDEX",
            "ADD_VIDEO_QUALITY",
            "ADD_VIDEO_PRESET",
            "ADD_VIDEO_BITRATE",
            "ADD_VIDEO_RESOLUTION",
            "ADD_VIDEO_FPS",
        ]

        # Audio add settings
        audio_settings = [
            "ADD_AUDIO_ENABLED",
            "ADD_AUDIO_CODEC",
            "ADD_AUDIO_INDEX",
            "ADD_AUDIO_BITRATE",
            "ADD_AUDIO_CHANNELS",
            "ADD_AUDIO_SAMPLING",
            "ADD_AUDIO_VOLUME",
        ]

        # Subtitle add settings
        subtitle_settings = [
            "ADD_SUBTITLE_ENABLED",
            "ADD_SUBTITLE_CODEC",
            "ADD_SUBTITLE_INDEX",
            "ADD_SUBTITLE_LANGUAGE",
            "ADD_SUBTITLE_ENCODING",
            "ADD_SUBTITLE_FONT",
            "ADD_SUBTITLE_FONT_SIZE",
            "ADD_SUBTITLE_HARDSUB_ENABLED",
        ]

        # Attachment add settings
        attachment_settings = [
            "ADD_ATTACHMENT_ENABLED",
            "ADD_ATTACHMENT_INDEX",
            "ADD_ATTACHMENT_MIMETYPE",
        ]

        # Combine all settings
        add_settings = (
            general_settings
            + video_settings
            + audio_settings
            + subtitle_settings
            + attachment_settings
        )

        for setting in add_settings:
            # Create display name based on setting type
            if setting.startswith("ADD_VIDEO_"):
                display_name = (
                    "Video "
                    + setting.replace("ADD_VIDEO_", "").replace("_", " ").title()
                )
            elif setting.startswith("ADD_AUDIO_"):
                display_name = (
                    "Audio "
                    + setting.replace("ADD_AUDIO_", "").replace("_", " ").title()
                )
            elif setting.startswith("ADD_SUBTITLE_"):
                display_name = (
                    "Subtitle "
                    + setting.replace("ADD_SUBTITLE_", "").replace("_", " ").title()
                )
            elif setting.startswith("ADD_ATTACHMENT_"):
                display_name = (
                    "Attachment "
                    + setting.replace("ADD_ATTACHMENT_", "")
                    .replace("_", " ")
                    .title()
                )
            else:
                display_name = setting.replace("ADD_", "").replace("_", " ").title()

            # For boolean settings, add toggle buttons
            if setting in [
                "ADD_ENABLED",
                "ADD_VIDEO_ENABLED",
                "ADD_AUDIO_ENABLED",
                "ADD_SUBTITLE_ENABLED",
                "ADD_SUBTITLE_HARDSUB_ENABLED",
                "ADD_ATTACHMENT_ENABLED",
                "ADD_DELETE_ORIGINAL",
                "ADD_PRESERVE_TRACKS",
                "ADD_REPLACE_TRACKS",
            ]:
                # Get the setting value directly from Config class for consistency
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"

                # Format display name with status
                if setting == "ADD_ENABLED":
                    display_name = f"⚙️ Enabled: {status}"
                elif setting == "ADD_VIDEO_ENABLED":
                    display_name = f"🎬 Video Enabled: {status}"
                elif setting == "ADD_AUDIO_ENABLED":
                    display_name = f"🔊 Audio Enabled: {status}"
                elif setting == "ADD_SUBTITLE_ENABLED":
                    display_name = f"💬 Subtitle Enabled: {status}"
                elif setting == "ADD_SUBTITLE_HARDSUB_ENABLED":
                    display_name = f"🔥 Hardsub Enabled: {status}"
                elif setting == "ADD_ATTACHMENT_ENABLED":
                    display_name = f"📎 Attachment Enabled: {status}"
                elif setting == "ADD_DELETE_ORIGINAL":
                    display_name = f"🗑️ Delete Original: {status}"
                elif setting == "ADD_PRESERVE_TRACKS":
                    display_name = f"🔒 Preserve Tracks: {status}"
                elif setting == "ADD_REPLACE_TRACKS":
                    display_name = f"🔄 Replace Tracks: {status}"
                else:
                    display_name = f"{display_name}: {status}"

                # Create toggle button with the correct current value
                buttons.data_button(
                    display_name,
                    f"botset toggle {setting} {not setting_value}",
                )
                continue

            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit mediatools_add")
        else:
            buttons.data_button("👁️ View", "botset view mediatools_add")

        buttons.data_button("🔄 Reset to Default", "botset default_add")

        buttons.data_button("⬅️ Back", "botset mediatools", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current add settings directly from Config class for consistency
        # General settings
        add_enabled = "✅ Enabled" if Config.ADD_ENABLED else "❌ Disabled"
        add_priority = Config.ADD_PRIORITY or DEFAULT_VALUES.get("ADD_PRIORITY", 7)
        add_delete_original = (
            "✅ Enabled" if Config.ADD_DELETE_ORIGINAL else "❌ Disabled"
        )

        # Video settings
        video_enabled = "✅ Enabled" if Config.ADD_VIDEO_ENABLED else "❌ Disabled"
        video_codec = Config.ADD_VIDEO_CODEC or "None"
        video_index = Config.ADD_VIDEO_INDEX or "All"
        video_quality = Config.ADD_VIDEO_QUALITY or "None"
        video_preset = Config.ADD_VIDEO_PRESET or "None"
        video_bitrate = Config.ADD_VIDEO_BITRATE or "None"
        video_resolution = Config.ADD_VIDEO_RESOLUTION or "None"
        video_fps = Config.ADD_VIDEO_FPS or "None"

        # Audio settings
        audio_enabled = "✅ Enabled" if Config.ADD_AUDIO_ENABLED else "❌ Disabled"
        audio_codec = Config.ADD_AUDIO_CODEC or "None"
        audio_index = Config.ADD_AUDIO_INDEX or "All"
        audio_bitrate = Config.ADD_AUDIO_BITRATE or "None"
        audio_channels = Config.ADD_AUDIO_CHANNELS or "None"
        audio_sampling = Config.ADD_AUDIO_SAMPLING or "None"
        audio_volume = Config.ADD_AUDIO_VOLUME or "None"

        # Subtitle settings
        subtitle_enabled = (
            "✅ Enabled" if Config.ADD_SUBTITLE_ENABLED else "❌ Disabled"
        )
        subtitle_codec = Config.ADD_SUBTITLE_CODEC or "None"
        subtitle_index = Config.ADD_SUBTITLE_INDEX or "All"
        subtitle_language = Config.ADD_SUBTITLE_LANGUAGE or "None"
        subtitle_encoding = Config.ADD_SUBTITLE_ENCODING or "None"
        subtitle_font = Config.ADD_SUBTITLE_FONT or "None"
        subtitle_font_size = Config.ADD_SUBTITLE_FONT_SIZE or "None"
        subtitle_hardsub_enabled = (
            "✅ Enabled" if Config.ADD_SUBTITLE_HARDSUB_ENABLED else "❌ Disabled"
        )

        # Attachment settings
        attachment_enabled = (
            "✅ Enabled" if Config.ADD_ATTACHMENT_ENABLED else "❌ Disabled"
        )
        attachment_index = Config.ADD_ATTACHMENT_INDEX or "All"
        attachment_mimetype = Config.ADD_ATTACHMENT_MIMETYPE or "None"

        msg = f"""<b>Add Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {add_enabled}
• <b>Priority:</b> <code>{add_priority}</code>
• <b>RO (Remove Original):</b> {add_delete_original}
• <b>Preserve Tracks:</b> {"✅ Enabled" if Config.ADD_PRESERVE_TRACKS else "❌ Disabled"}
• <b>Replace Tracks:</b> {"✅ Enabled" if Config.ADD_REPLACE_TRACKS else "❌ Disabled"}

<b>Video Add Settings:</b>
• <b>Status:</b> {video_enabled}
• <b>Codec:</b> <code>{video_codec}</code>
• <b>Index:</b> <code>{video_index}</code>
• <b>Quality:</b> <code>{video_quality}</code>
• <b>Preset:</b> <code>{video_preset}</code>
• <b>Bitrate:</b> <code>{video_bitrate}</code>
• <b>Resolution:</b> <code>{video_resolution}</code>
• <b>FPS:</b> <code>{video_fps}</code>

<b>Audio Add Settings:</b>
• <b>Status:</b> {audio_enabled}
• <b>Codec:</b> <code>{audio_codec}</code>
• <b>Index:</b> <code>{audio_index}</code>
• <b>Bitrate:</b> <code>{audio_bitrate}</code>
• <b>Channels:</b> <code>{audio_channels}</code>
• <b>Sampling:</b> <code>{audio_sampling}</code>
• <b>Volume:</b> <code>{audio_volume}</code>

<b>Subtitle Add Settings:</b>
• <b>Status:</b> {subtitle_enabled}
• <b>Codec:</b> <code>{subtitle_codec}</code>
• <b>Index:</b> <code>{subtitle_index}</code>
• <b>Hardsub:</b> {subtitle_hardsub_enabled}
• <b>Language:</b> <code>{subtitle_language}</code>
• <b>Encoding:</b> <code>{subtitle_encoding}</code>
• <b>Font:</b> <code>{subtitle_font}</code>
• <b>Font Size:</b> <code>{subtitle_font_size}</code>

<b>Attachment Add Settings:</b>
• <b>Status:</b> {attachment_enabled}
• <b>Index:</b> <code>{attachment_index}</code>
• <b>Mimetype:</b> <code>{attachment_mimetype}</code>

<b>Usage:</b>
• Main Add toggle must be enabled
• Media type specific toggles must be enabled for respective additions
• Use <code>-add</code> to enable adding tracks
• Use <code>-add-video</code>, <code>-add-audio</code>, etc. for specific track types
• Use <code>-m</code> flag to specify multiple input files
  Example: <code>/leech https://example.com/video.mp4 -add -m folder_name</code>
• Use <code>-add-video-index 0</code> to add at specific index
• Add <code>-del</code> to delete original files after adding
• Use <code>-preserve</code> to keep existing tracks
• Use <code>-replace</code> to replace existing tracks
• Settings with value 'None' will not be used in command generation

Configure global add settings that will be used when user settings are not available."""

    elif key == "mediatools_swap":
        # Add buttons for swap settings
        # General swap settings
        general_settings = [
            ("SWAP_ENABLED", "Enabled"),
            ("SWAP_PRIORITY", "Priority"),
            ("SWAP_REMOVE_ORIGINAL", "Remove Original"),
        ]

        # Audio swap settings
        audio_settings = [
            ("SWAP_AUDIO_ENABLED", "Audio: Enabled"),
            ("SWAP_AUDIO_USE_LANGUAGE", "Audio: Use Language"),
            ("SWAP_AUDIO_LANGUAGE_ORDER", "Audio: Language Order"),
            ("SWAP_AUDIO_INDEX_ORDER", "Audio: Index Order"),
        ]

        # Video swap settings
        video_settings = [
            ("SWAP_VIDEO_ENABLED", "Video: Enabled"),
            ("SWAP_VIDEO_USE_LANGUAGE", "Video: Use Language"),
            ("SWAP_VIDEO_LANGUAGE_ORDER", "Video: Language Order"),
            ("SWAP_VIDEO_INDEX_ORDER", "Video: Index Order"),
        ]

        # Subtitle swap settings
        subtitle_settings = [
            ("SWAP_SUBTITLE_ENABLED", "Subtitle: Enabled"),
            ("SWAP_SUBTITLE_USE_LANGUAGE", "Subtitle: Use Language"),
            ("SWAP_SUBTITLE_LANGUAGE_ORDER", "Subtitle: Language Order"),
            ("SWAP_SUBTITLE_INDEX_ORDER", "Subtitle: Index Order"),
        ]

        # Add buttons for general settings
        for setting, display_name in general_settings:
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Add audio settings
        for setting, display_name in audio_settings:
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Add video settings
        for setting, display_name in video_settings:
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Add subtitle settings
        for setting, display_name in subtitle_settings:
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Add view/edit state toggle like other media tools
        if state == "view":
            buttons.data_button("Edit", "botset edit mediatools_swap")
        else:
            buttons.data_button("View", "botset view mediatools_swap")

        # Add reset to default button
        buttons.data_button("Default", "botset default_swap")

        # Add navigation buttons
        buttons.data_button("⬅️ Back", "botset mediatools", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        msg = """<b>⌬ Swap Settings</b>

<b>General Settings:</b>
• <b>Enabled:</b> Master switch for swap functionality
• <b>Priority:</b> Processing order in pipeline (lower = earlier)
• <b>Remove Original:</b> Delete original files after swapping

<b>Audio Swap Settings:</b>
• <b>Enabled:</b> Enable/disable audio track swapping
• <b>Use Language:</b> Language-based (True) or index-based (False) swapping
• <b>Language Order:</b> Priority order for languages (e.g., "eng,hin,jpn")
• <b>Index Order:</b> Index swap pattern (e.g., "0,1" to swap first two)

<b>Video Swap Settings:</b>
• <b>Enabled:</b> Enable/disable video track swapping
• <b>Use Language:</b> Language-based (True) or index-based (False) swapping
• <b>Language Order:</b> Priority order for languages (e.g., "eng,hin,jpn")
• <b>Index Order:</b> Index swap pattern (e.g., "0,1" to swap first two)

<b>Subtitle Swap Settings:</b>
• <b>Enabled:</b> Enable/disable subtitle track swapping
• <b>Use Language:</b> Language-based (True) or index-based (False) swapping
• <b>Language Order:</b> Priority order for languages (e.g., "eng,hin,jpn")
• <b>Index Order:</b> Index swap pattern (e.g., "0,1" to swap first two)

<b>Usage:</b>
• Add <code>-swap</code> to any download command to apply swapping
• Language mode reorders tracks by language priority
• Index mode swaps tracks at specific positions
• Settings with value 'None' will not be used in command generation

Configure global swap settings that will be used when user settings are not available."""

    elif key == "mediatools_trim":
        # Add buttons for trim settings
        # General trim settings
        general_settings = [
            "TRIM_ENABLED",
            "TRIM_PRIORITY",
            "TRIM_START_TIME",
            "TRIM_END_TIME",
            "TRIM_DELETE_ORIGINAL",
        ]

        # Video trim settings
        video_settings = [
            "TRIM_VIDEO_ENABLED",
            "TRIM_VIDEO_CODEC",
            "TRIM_VIDEO_PRESET",
            "TRIM_VIDEO_FORMAT",
        ]

        # Audio trim settings
        audio_settings = [
            "TRIM_AUDIO_ENABLED",
            "TRIM_AUDIO_CODEC",
            "TRIM_AUDIO_PRESET",
            "TRIM_AUDIO_FORMAT",
        ]

        # Image trim settings
        image_settings = [
            "TRIM_IMAGE_ENABLED",
            "TRIM_IMAGE_QUALITY",
            "TRIM_IMAGE_FORMAT",
        ]

        # Document trim settings
        document_settings = [
            "TRIM_DOCUMENT_ENABLED",
            "TRIM_DOCUMENT_START_PAGE",
            "TRIM_DOCUMENT_END_PAGE",
            "TRIM_DOCUMENT_QUALITY",
            "TRIM_DOCUMENT_FORMAT",
        ]

        # Subtitle trim settings
        subtitle_settings = [
            "TRIM_SUBTITLE_ENABLED",
            "TRIM_SUBTITLE_ENCODING",
            "TRIM_SUBTITLE_FORMAT",
        ]

        # Archive trim settings
        archive_settings = [
            "TRIM_ARCHIVE_ENABLED",
            "TRIM_ARCHIVE_FORMAT",
        ]

        # Combine all settings
        trim_settings = (
            general_settings
            + video_settings
            + audio_settings
            + image_settings
            + document_settings
            + subtitle_settings
            + archive_settings
        )

        for setting in trim_settings:
            # Create display name based on setting type with emojis for better UI
            if setting.startswith("TRIM_VIDEO_"):
                prefix = "🎬"
                display_name = (
                    f"{prefix} Video "
                    + setting.replace("TRIM_VIDEO_", "").replace("_", " ").title()
                )
            elif setting.startswith("TRIM_AUDIO_"):
                prefix = "🔊"
                display_name = (
                    f"{prefix} Audio "
                    + setting.replace("TRIM_AUDIO_", "").replace("_", " ").title()
                )
            elif setting.startswith("TRIM_IMAGE_"):
                prefix = "🖼️"
                display_name = (
                    f"{prefix} Image "
                    + setting.replace("TRIM_IMAGE_", "").replace("_", " ").title()
                )
            elif setting.startswith("TRIM_DOCUMENT_"):
                prefix = "📄"
                if setting == "TRIM_DOCUMENT_START_PAGE":
                    display_name = f"{prefix} Document Start Page"
                elif setting == "TRIM_DOCUMENT_END_PAGE":
                    display_name = f"{prefix} Document End Page"
                else:
                    display_name = (
                        f"{prefix} Document "
                        + setting.replace("TRIM_DOCUMENT_", "")
                        .replace("_", " ")
                        .title()
                    )
            elif setting.startswith("TRIM_SUBTITLE_"):
                prefix = "💬"
                display_name = (
                    f"{prefix} Subtitle "
                    + setting.replace("TRIM_SUBTITLE_", "").replace("_", " ").title()
                )
            elif setting.startswith("TRIM_ARCHIVE_"):
                prefix = "📦"
                display_name = (
                    f"{prefix} Archive "
                    + setting.replace("TRIM_ARCHIVE_", "").replace("_", " ").title()
                )
            elif setting == "TRIM_PRIORITY":
                display_name = "🔢 Priority"
            elif setting == "TRIM_START_TIME":
                display_name = "⏱️ Start Time"
            elif setting == "TRIM_END_TIME":
                display_name = "⏱️ End Time"
            elif setting == "TRIM_DELETE_ORIGINAL":
                display_name = "🗑️ Delete Original"
            else:
                prefix = "⚙️"
                display_name = (
                    f"{prefix} "
                    + setting.replace("TRIM_", "").replace("_", " ").title()
                )

            # For boolean settings, add toggle buttons
            if setting in [
                "TRIM_ENABLED",
                "TRIM_VIDEO_ENABLED",
                "TRIM_AUDIO_ENABLED",
                "TRIM_IMAGE_ENABLED",
                "TRIM_DOCUMENT_ENABLED",
                "TRIM_SUBTITLE_ENABLED",
                "TRIM_ARCHIVE_ENABLED",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"

                # Format display name with status and emojis for better UI
                if setting == "TRIM_ENABLED":
                    display_name = f"⚙️ Enabled: {status}"
                elif setting == "TRIM_VIDEO_ENABLED":
                    display_name = f"🎬 Video Enabled: {status}"
                elif setting == "TRIM_AUDIO_ENABLED":
                    display_name = f"🔊 Audio Enabled: {status}"
                elif setting == "TRIM_IMAGE_ENABLED":
                    display_name = f"🖼️ Image Enabled: {status}"
                elif setting == "TRIM_DOCUMENT_ENABLED":
                    display_name = f"📄 Document Enabled: {status}"
                elif setting == "TRIM_SUBTITLE_ENABLED":
                    display_name = f"💬 Subtitle Enabled: {status}"
                elif setting == "TRIM_ARCHIVE_ENABLED":
                    display_name = f"📦 Archive Enabled: {status}"
                elif setting == "TRIM_DELETE_ORIGINAL":
                    display_name = f"🗑️ Delete Original: {status}"
                else:
                    display_name = f"{display_name}: {status}"

                # Create toggle button
                buttons.data_button(
                    display_name,
                    f"botset toggle {setting} {not setting_value}",
                )
                continue

            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("✏️ Edit", "botset edit mediatools_trim", "footer")
        else:
            buttons.data_button("👁️ View", "botset view mediatools_trim", "footer")

        buttons.data_button("🔄 Reset to Default", "botset default_trim", "footer")

        buttons.data_button("⬅️ Back", "botset mediatools", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        # Get current trim settings
        trim_enabled = "✅ Enabled" if Config.TRIM_ENABLED else "❌ Disabled"
        trim_priority = Config.TRIM_PRIORITY or "5 (Default)"
        trim_start_time = Config.TRIM_START_TIME or "00:00:00 (Default)"
        trim_end_time = Config.TRIM_END_TIME or "None (End of file)"

        # Video settings
        video_enabled = "✅ Enabled" if Config.TRIM_VIDEO_ENABLED else "❌ Disabled"
        video_codec = Config.TRIM_VIDEO_CODEC or "None"
        video_preset = Config.TRIM_VIDEO_PRESET or "None"
        video_format = Config.TRIM_VIDEO_FORMAT or "None"

        # Audio settings
        audio_enabled = "✅ Enabled" if Config.TRIM_AUDIO_ENABLED else "❌ Disabled"
        audio_codec = Config.TRIM_AUDIO_CODEC or "None"
        audio_preset = Config.TRIM_AUDIO_PRESET or "None"
        audio_format = Config.TRIM_AUDIO_FORMAT or "None"

        # Image settings
        image_enabled = "✅ Enabled" if Config.TRIM_IMAGE_ENABLED else "❌ Disabled"
        image_quality = Config.TRIM_IMAGE_QUALITY or "90 (Default)"
        image_format = Config.TRIM_IMAGE_FORMAT or "None"

        # Document settings
        document_enabled = (
            "✅ Enabled" if Config.TRIM_DOCUMENT_ENABLED else "❌ Disabled"
        )
        document_start_page = Config.TRIM_DOCUMENT_START_PAGE or "1 (Default)"
        document_end_page = Config.TRIM_DOCUMENT_END_PAGE or "Last page (Default)"
        document_quality = Config.TRIM_DOCUMENT_QUALITY or "90 (Default)"
        document_format = Config.TRIM_DOCUMENT_FORMAT or "None"

        # Subtitle settings
        subtitle_enabled = (
            "✅ Enabled" if Config.TRIM_SUBTITLE_ENABLED else "❌ Disabled"
        )
        subtitle_encoding = Config.TRIM_SUBTITLE_ENCODING or "None"
        subtitle_format = Config.TRIM_SUBTITLE_FORMAT or "None"

        # Archive settings
        archive_enabled = (
            "✅ Enabled" if Config.TRIM_ARCHIVE_ENABLED else "❌ Disabled"
        )
        archive_format = Config.TRIM_ARCHIVE_FORMAT or "None"

        msg = f"""<b>Trim Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {trim_enabled}
• <b>Priority:</b> <code>{trim_priority}</code>
• <b>Start Time:</b> <code>{trim_start_time}</code>
• <b>End Time:</b> <code>{trim_end_time}</code>

<b>Video Trim Settings:</b>
• <b>Status:</b> {video_enabled}
• <b>Codec:</b> <code>{video_codec}</code>
• <b>Preset:</b> <code>{video_preset}</code>
• <b>Format:</b> <code>{video_format}</code>

<b>Audio Trim Settings:</b>
• <b>Status:</b> {audio_enabled}
• <b>Codec:</b> <code>{audio_codec}</code>
• <b>Preset:</b> <code>{audio_preset}</code>
• <b>Format:</b> <code>{audio_format}</code>

<b>Image Trim Settings:</b>
• <b>Status:</b> {image_enabled}
• <b>Quality:</b> <code>{image_quality}</code>
• <b>Format:</b> <code>{image_format}</code>

<b>Document Trim Settings:</b>
• <b>Status:</b> {document_enabled}
• <b>Start Page:</b> <code>{document_start_page}</code>
• <b>End Page:</b> <code>{document_end_page}</code>
• <b>Quality:</b> <code>{document_quality}</code>
• <b>Format:</b> <code>{document_format}</code>

<b>Subtitle Trim Settings:</b>
• <b>Status:</b> {subtitle_enabled}
• <b>Encoding:</b> <code>{subtitle_encoding}</code>
• <b>Format:</b> <code>{subtitle_format}</code>

<b>Archive Trim Settings:</b>
• <b>Status:</b> {archive_enabled}
• <b>Format:</b> <code>{archive_format}</code>

<b>Usage:</b>
• Main Trim toggle must be enabled
• Media type specific toggles must be enabled for respective trims
• Use <code>-trim</code> to enable trimming
• Use <code>-trim-start HH:MM:SS</code> to set start time for media
• Use <code>-trim-end HH:MM:SS</code> to set end time for media
• Use <code>-trim start-page end-page</code> for documents
• Add <code>-del</code> to delete original files after trimming

Configure global trim settings that will be used when user settings are not available."""

    elif key == "mediatools_extract":
        # Add buttons for extract settings
        # General extract settings
        general_settings = [
            "EXTRACT_ENABLED",
            "EXTRACT_PRIORITY",
            "EXTRACT_DELETE_ORIGINAL",
        ]

        # Video extract settings
        video_settings = [
            "EXTRACT_VIDEO_ENABLED",
            "EXTRACT_VIDEO_CODEC",
            "EXTRACT_VIDEO_INDEX",
            "EXTRACT_VIDEO_QUALITY",
            "EXTRACT_VIDEO_PRESET",
            "EXTRACT_VIDEO_BITRATE",
            "EXTRACT_VIDEO_RESOLUTION",
            "EXTRACT_VIDEO_FPS",
            "EXTRACT_VIDEO_FORMAT",
        ]

        # Audio extract settings
        audio_settings = [
            "EXTRACT_AUDIO_ENABLED",
            "EXTRACT_AUDIO_CODEC",
            "EXTRACT_AUDIO_INDEX",
            "EXTRACT_AUDIO_BITRATE",
            "EXTRACT_AUDIO_CHANNELS",
            "EXTRACT_AUDIO_SAMPLING",
            "EXTRACT_AUDIO_VOLUME",
            "EXTRACT_AUDIO_FORMAT",
        ]

        # Subtitle extract settings
        subtitle_settings = [
            "EXTRACT_SUBTITLE_ENABLED",
            "EXTRACT_SUBTITLE_CODEC",
            "EXTRACT_SUBTITLE_INDEX",
            "EXTRACT_SUBTITLE_LANGUAGE",
            "EXTRACT_SUBTITLE_ENCODING",
            "EXTRACT_SUBTITLE_FONT",
            "EXTRACT_SUBTITLE_FONT_SIZE",
            "EXTRACT_SUBTITLE_FORMAT",
        ]

        # Attachment extract settings
        attachment_settings = [
            "EXTRACT_ATTACHMENT_ENABLED",
            "EXTRACT_ATTACHMENT_INDEX",
            "EXTRACT_ATTACHMENT_FILTER",
            "EXTRACT_ATTACHMENT_FORMAT",
        ]

        # Quality settings
        quality_settings = [
            "EXTRACT_MAINTAIN_QUALITY",
        ]

        # Combine all settings
        extract_settings = (
            general_settings
            + video_settings
            + audio_settings
            + subtitle_settings
            + attachment_settings
            + quality_settings
        )

        for setting in extract_settings:
            # Create display name based on setting type
            if setting.startswith("EXTRACT_VIDEO_"):
                display_name = (
                    "Video "
                    + setting.replace("EXTRACT_VIDEO_", "").replace("_", " ").title()
                )
            elif setting.startswith("EXTRACT_AUDIO_"):
                display_name = (
                    "Audio "
                    + setting.replace("EXTRACT_AUDIO_", "").replace("_", " ").title()
                )
            elif setting.startswith("EXTRACT_SUBTITLE_"):
                display_name = (
                    "Subtitle "
                    + setting.replace("EXTRACT_SUBTITLE_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("EXTRACT_ATTACHMENT_"):
                display_name = (
                    "Attachment "
                    + setting.replace("EXTRACT_ATTACHMENT_", "")
                    .replace("_", " ")
                    .title()
                )
            else:
                display_name = (
                    setting.replace("EXTRACT_", "").replace("_", " ").title()
                )

            # For boolean settings, add toggle buttons
            if setting in [
                "EXTRACT_ENABLED",
                "EXTRACT_VIDEO_ENABLED",
                "EXTRACT_AUDIO_ENABLED",
                "EXTRACT_SUBTITLE_ENABLED",
                "EXTRACT_ATTACHMENT_ENABLED",
                "EXTRACT_MAINTAIN_QUALITY",
                "EXTRACT_DELETE_ORIGINAL",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"

                # Format display name with status
                if setting == "EXTRACT_ENABLED":
                    display_name = f"Enabled: {status}"
                elif setting == "EXTRACT_VIDEO_ENABLED":
                    display_name = f"Video Enabled: {status}"
                elif setting == "EXTRACT_AUDIO_ENABLED":
                    display_name = f"Audio Enabled: {status}"
                elif setting == "EXTRACT_SUBTITLE_ENABLED":
                    display_name = f"Subtitle Enabled: {status}"
                elif setting == "EXTRACT_ATTACHMENT_ENABLED":
                    display_name = f"Attachment Enabled: {status}"
                elif setting == "EXTRACT_MAINTAIN_QUALITY":
                    display_name = f"Maintain Quality: {status}"
                elif setting == "EXTRACT_DELETE_ORIGINAL":
                    display_name = f"RO: {status}"
                else:
                    display_name = f"{display_name}: {status}"

                # Create toggle button
                buttons.data_button(
                    display_name,
                    f"botset toggle {setting} {not setting_value}",
                )
                continue

            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("Edit", "botset edit mediatools_extract")
        else:
            buttons.data_button("View", "botset view mediatools_extract")

        buttons.data_button("Default", "botset default_extract")

        buttons.data_button("Back", "botset mediatools", "footer")
        buttons.data_button("Close", "botset close", "footer")

        # Get current extract settings
        extract_enabled = "✅ Enabled" if Config.EXTRACT_ENABLED else "❌ Disabled"
        extract_priority = f"{Config.EXTRACT_PRIORITY}"
        delete_original = (
            "✅ Enabled" if Config.EXTRACT_DELETE_ORIGINAL else "❌ Disabled"
        )

        # Video settings
        video_enabled = (
            "✅ Enabled" if Config.EXTRACT_VIDEO_ENABLED else "❌ Disabled"
        )
        video_codec = Config.EXTRACT_VIDEO_CODEC or "None"
        video_format = Config.EXTRACT_VIDEO_FORMAT or "None"
        video_index = Config.EXTRACT_VIDEO_INDEX or "All"
        video_quality = Config.EXTRACT_VIDEO_QUALITY or "None"
        video_preset = Config.EXTRACT_VIDEO_PRESET or "None"
        video_bitrate = Config.EXTRACT_VIDEO_BITRATE or "None"
        video_resolution = Config.EXTRACT_VIDEO_RESOLUTION or "None"
        video_fps = Config.EXTRACT_VIDEO_FPS or "None"

        # Audio settings
        audio_enabled = (
            "✅ Enabled" if Config.EXTRACT_AUDIO_ENABLED else "❌ Disabled"
        )
        audio_codec = Config.EXTRACT_AUDIO_CODEC or "None"
        audio_format = Config.EXTRACT_AUDIO_FORMAT or "None"
        audio_index = Config.EXTRACT_AUDIO_INDEX or "All"
        audio_bitrate = Config.EXTRACT_AUDIO_BITRATE or "None"
        audio_channels = Config.EXTRACT_AUDIO_CHANNELS or "None"
        audio_sampling = Config.EXTRACT_AUDIO_SAMPLING or "None"
        audio_volume = Config.EXTRACT_AUDIO_VOLUME or "None"

        # Subtitle settings
        subtitle_enabled = (
            "✅ Enabled" if Config.EXTRACT_SUBTITLE_ENABLED else "❌ Disabled"
        )
        subtitle_codec = Config.EXTRACT_SUBTITLE_CODEC or "None"
        subtitle_format = Config.EXTRACT_SUBTITLE_FORMAT or "None"
        subtitle_index = Config.EXTRACT_SUBTITLE_INDEX or "All"
        subtitle_language = Config.EXTRACT_SUBTITLE_LANGUAGE or "None"
        subtitle_encoding = Config.EXTRACT_SUBTITLE_ENCODING or "None"
        subtitle_font = Config.EXTRACT_SUBTITLE_FONT or "None"
        subtitle_font_size = Config.EXTRACT_SUBTITLE_FONT_SIZE or "None"

        # Attachment settings
        attachment_enabled = (
            "✅ Enabled" if Config.EXTRACT_ATTACHMENT_ENABLED else "❌ Disabled"
        )
        attachment_format = Config.EXTRACT_ATTACHMENT_FORMAT or "None"
        attachment_index = Config.EXTRACT_ATTACHMENT_INDEX or "All"
        attachment_filter = Config.EXTRACT_ATTACHMENT_FILTER or "None"

        # Quality settings
        maintain_quality = (
            "✅ Enabled" if Config.EXTRACT_MAINTAIN_QUALITY else "❌ Disabled"
        )

        msg = f"""<b>Extract Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {extract_enabled}
• <b>Priority:</b> <code>{extract_priority}</code>
• <b>RO:</b> {delete_original}

<b>Video Extract Settings:</b>
• <b>Status:</b> {video_enabled}
• <b>Codec:</b> <code>{video_codec}</code>
• <b>Format:</b> <code>{video_format}</code>
• <b>Index:</b> <code>{video_index}</code>
• <b>Quality:</b> <code>{video_quality}</code>
• <b>Preset:</b> <code>{video_preset}</code>
• <b>Bitrate:</b> <code>{video_bitrate}</code>
• <b>Resolution:</b> <code>{video_resolution}</code>
• <b>FPS:</b> <code>{video_fps}</code>

<b>Audio Extract Settings:</b>
• <b>Status:</b> {audio_enabled}
• <b>Codec:</b> <code>{audio_codec}</code>
• <b>Format:</b> <code>{audio_format}</code>
• <b>Index:</b> <code>{audio_index}</code>
• <b>Bitrate:</b> <code>{audio_bitrate}</code>
• <b>Channels:</b> <code>{audio_channels}</code>
• <b>Sampling:</b> <code>{audio_sampling}</code>
• <b>Volume:</b> <code>{audio_volume}</code>

<b>Subtitle Extract Settings:</b>
• <b>Status:</b> {subtitle_enabled}
• <b>Codec:</b> <code>{subtitle_codec}</code>
• <b>Format:</b> <code>{subtitle_format}</code>
• <b>Index:</b> <code>{subtitle_index}</code>
• <b>Language:</b> <code>{subtitle_language}</code>
• <b>Encoding:</b> <code>{subtitle_encoding}</code>
• <b>Font:</b> <code>{subtitle_font}</code>
• <b>Font Size:</b> <code>{subtitle_font_size}</code>

<b>Attachment Extract Settings:</b>
• <b>Status:</b> {attachment_enabled}
• <b>Format:</b> <code>{attachment_format}</code>
• <b>Index:</b> <code>{attachment_index}</code>
• <b>Filter:</b> <code>{attachment_filter}</code>

<b>Quality Settings:</b>
• <b>Maintain Quality:</b> {maintain_quality}

<b>Usage:</b>
• Main Extract toggle must be enabled
• Media type specific toggles must be enabled for respective extractions
• Use <code>-extract</code> to enable extraction
• Use <code>-extract-video</code>, <code>-extract-audio</code>, etc. for specific track types
• Use <code>-extract-video-index 0</code> to extract specific track by index
• Add <code>-del</code> to delete original files after extraction

Configure global extract settings that will be used when user settings are not available."""

    elif key == "mediatools_compression":
        # Add buttons for compression settings
        # General compression settings
        general_settings = [
            "COMPRESSION_ENABLED",
            "COMPRESSION_PRIORITY",
            "COMPRESSION_DELETE_ORIGINAL",
        ]

        # Video compression settings
        video_settings = [
            "COMPRESSION_VIDEO_ENABLED",
            "COMPRESSION_VIDEO_PRESET",
            "COMPRESSION_VIDEO_CRF",
            "COMPRESSION_VIDEO_CODEC",
            "COMPRESSION_VIDEO_TUNE",
            "COMPRESSION_VIDEO_PIXEL_FORMAT",
            "COMPRESSION_VIDEO_BITDEPTH",
            "COMPRESSION_VIDEO_BITRATE",
            "COMPRESSION_VIDEO_RESOLUTION",
            "COMPRESSION_VIDEO_FORMAT",
        ]

        # Audio compression settings
        audio_settings = [
            "COMPRESSION_AUDIO_ENABLED",
            "COMPRESSION_AUDIO_PRESET",
            "COMPRESSION_AUDIO_CODEC",
            "COMPRESSION_AUDIO_BITRATE",
            "COMPRESSION_AUDIO_CHANNELS",
            "COMPRESSION_AUDIO_BITDEPTH",
            "COMPRESSION_AUDIO_FORMAT",
        ]

        # Image compression settings
        image_settings = [
            "COMPRESSION_IMAGE_ENABLED",
            "COMPRESSION_IMAGE_PRESET",
            "COMPRESSION_IMAGE_QUALITY",
            "COMPRESSION_IMAGE_RESIZE",
            "COMPRESSION_IMAGE_FORMAT",
        ]

        # Document compression settings
        document_settings = [
            "COMPRESSION_DOCUMENT_ENABLED",
            "COMPRESSION_DOCUMENT_PRESET",
            "COMPRESSION_DOCUMENT_DPI",
            "COMPRESSION_DOCUMENT_FORMAT",
        ]

        # Subtitle compression settings
        subtitle_settings = [
            "COMPRESSION_SUBTITLE_ENABLED",
            "COMPRESSION_SUBTITLE_PRESET",
            "COMPRESSION_SUBTITLE_ENCODING",
            "COMPRESSION_SUBTITLE_FORMAT",
        ]

        # Archive compression settings
        archive_settings = [
            "COMPRESSION_ARCHIVE_ENABLED",
            "COMPRESSION_ARCHIVE_PRESET",
            "COMPRESSION_ARCHIVE_LEVEL",
            "COMPRESSION_ARCHIVE_METHOD",
            "COMPRESSION_ARCHIVE_FORMAT",
            "COMPRESSION_ARCHIVE_PASSWORD",
            "COMPRESSION_ARCHIVE_ALGORITHM",
        ]

        # Combine all settings
        compression_settings = (
            general_settings
            + video_settings
            + audio_settings
            + image_settings
            + document_settings
            + subtitle_settings
            + archive_settings
        )

        for setting in compression_settings:
            # Create display name based on setting type
            if setting.startswith("COMPRESSION_VIDEO_"):
                display_name = (
                    "Video "
                    + setting.replace("COMPRESSION_VIDEO_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("COMPRESSION_AUDIO_"):
                display_name = (
                    "Audio "
                    + setting.replace("COMPRESSION_AUDIO_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("COMPRESSION_IMAGE_"):
                display_name = (
                    "Image "
                    + setting.replace("COMPRESSION_IMAGE_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("COMPRESSION_DOCUMENT_"):
                display_name = (
                    "Document "
                    + setting.replace("COMPRESSION_DOCUMENT_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("COMPRESSION_SUBTITLE_"):
                display_name = (
                    "Subtitle "
                    + setting.replace("COMPRESSION_SUBTITLE_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("COMPRESSION_ARCHIVE_"):
                display_name = (
                    "Archive "
                    + setting.replace("COMPRESSION_ARCHIVE_", "")
                    .replace("_", " ")
                    .title()
                )
            else:
                display_name = (
                    setting.replace("COMPRESSION_", "").replace("_", " ").title()
                )

            # For boolean settings, add toggle buttons
            if setting in [
                "COMPRESSION_ENABLED",
                "COMPRESSION_DELETE_ORIGINAL",
                "COMPRESSION_VIDEO_ENABLED",
                "COMPRESSION_AUDIO_ENABLED",
                "COMPRESSION_IMAGE_ENABLED",
                "COMPRESSION_DOCUMENT_ENABLED",
                "COMPRESSION_SUBTITLE_ENABLED",
                "COMPRESSION_ARCHIVE_ENABLED",
                "BULK_ENABLED",
            ]:
                # Use True as default for COMPRESSION_DELETE_ORIGINAL, False for others
                default_value = setting == "COMPRESSION_DELETE_ORIGINAL"

                # Make sure COMPRESSION_DELETE_ORIGINAL exists in Config with the correct default
                if setting == "COMPRESSION_DELETE_ORIGINAL" and not hasattr(
                    Config, setting
                ):
                    Config.COMPRESSION_DELETE_ORIGINAL = True

                setting_value = getattr(Config, setting, default_value)
                status = "✅ ON" if setting_value else "❌ OFF"

                # Format display name with status
                if setting == "COMPRESSION_ENABLED":
                    display_name = f"Enabled: {status}"
                elif setting == "COMPRESSION_DELETE_ORIGINAL":
                    display_name = f"RO: {status}"
                elif setting == "COMPRESSION_VIDEO_ENABLED":
                    display_name = f"Video Enabled: {status}"
                elif setting == "COMPRESSION_AUDIO_ENABLED":
                    display_name = f"Audio Enabled: {status}"
                elif setting == "COMPRESSION_IMAGE_ENABLED":
                    display_name = f"Image Enabled: {status}"
                elif setting == "COMPRESSION_DOCUMENT_ENABLED":
                    display_name = f"Document Enabled: {status}"
                elif setting == "COMPRESSION_SUBTITLE_ENABLED":
                    display_name = f"Subtitle Enabled: {status}"
                elif setting == "COMPRESSION_ARCHIVE_ENABLED":
                    display_name = f"Archive Enabled: {status}"
                else:
                    display_name = f"{display_name}: {status}"

                # Create toggle button
                buttons.data_button(
                    display_name,
                    f"botset toggle {setting} {not setting_value}",
                )
                continue

            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("Edit", "botset edit mediatools_compression")
        else:
            buttons.data_button("View", "botset view mediatools_compression")

        buttons.data_button("Default", "botset default_compression")

        buttons.data_button("Back", "botset mediatools", "footer")
        buttons.data_button("Close", "botset close", "footer")

        # Get current compression settings
        compression_enabled = (
            "✅ Enabled" if Config.COMPRESSION_ENABLED else "❌ Disabled"
        )
        compression_priority = f"{Config.COMPRESSION_PRIORITY}"
        compression_delete_original = (
            "✅ Enabled" if Config.COMPRESSION_DELETE_ORIGINAL else "❌ Disabled"
        )

        # Video settings
        video_enabled = (
            "✅ Enabled" if Config.COMPRESSION_VIDEO_ENABLED else "❌ Disabled"
        )
        video_preset = Config.COMPRESSION_VIDEO_PRESET
        video_crf = Config.COMPRESSION_VIDEO_CRF
        video_codec = Config.COMPRESSION_VIDEO_CODEC
        video_tune = Config.COMPRESSION_VIDEO_TUNE
        video_pixel_format = Config.COMPRESSION_VIDEO_PIXEL_FORMAT
        video_bitdepth = Config.COMPRESSION_VIDEO_BITDEPTH
        video_bitrate = Config.COMPRESSION_VIDEO_BITRATE
        video_resolution = Config.COMPRESSION_VIDEO_RESOLUTION
        video_format = Config.COMPRESSION_VIDEO_FORMAT

        # Audio settings
        audio_enabled = (
            "✅ Enabled" if Config.COMPRESSION_AUDIO_ENABLED else "❌ Disabled"
        )
        audio_preset = Config.COMPRESSION_AUDIO_PRESET
        audio_codec = Config.COMPRESSION_AUDIO_CODEC
        audio_bitrate = Config.COMPRESSION_AUDIO_BITRATE
        audio_channels = Config.COMPRESSION_AUDIO_CHANNELS
        audio_bitdepth = Config.COMPRESSION_AUDIO_BITDEPTH
        audio_format = Config.COMPRESSION_AUDIO_FORMAT

        # Image settings
        image_enabled = (
            "✅ Enabled" if Config.COMPRESSION_IMAGE_ENABLED else "❌ Disabled"
        )
        image_preset = Config.COMPRESSION_IMAGE_PRESET
        image_quality = Config.COMPRESSION_IMAGE_QUALITY
        image_resize = Config.COMPRESSION_IMAGE_RESIZE
        image_format = Config.COMPRESSION_IMAGE_FORMAT

        # Document settings
        document_enabled = (
            "✅ Enabled" if Config.COMPRESSION_DOCUMENT_ENABLED else "❌ Disabled"
        )
        document_preset = Config.COMPRESSION_DOCUMENT_PRESET
        document_dpi = Config.COMPRESSION_DOCUMENT_DPI
        document_format = Config.COMPRESSION_DOCUMENT_FORMAT

        # Subtitle settings
        subtitle_enabled = (
            "✅ Enabled" if Config.COMPRESSION_SUBTITLE_ENABLED else "❌ Disabled"
        )
        subtitle_preset = Config.COMPRESSION_SUBTITLE_PRESET
        subtitle_encoding = Config.COMPRESSION_SUBTITLE_ENCODING
        subtitle_format = Config.COMPRESSION_SUBTITLE_FORMAT

        # Archive settings
        archive_enabled = (
            "✅ Enabled" if Config.COMPRESSION_ARCHIVE_ENABLED else "❌ Disabled"
        )
        archive_preset = Config.COMPRESSION_ARCHIVE_PRESET
        archive_level = Config.COMPRESSION_ARCHIVE_LEVEL
        archive_method = Config.COMPRESSION_ARCHIVE_METHOD
        archive_format = Config.COMPRESSION_ARCHIVE_FORMAT
        archive_password = (
            "Set"
            if hasattr(Config, "COMPRESSION_ARCHIVE_PASSWORD")
            and Config.COMPRESSION_ARCHIVE_PASSWORD
            and Config.COMPRESSION_ARCHIVE_PASSWORD.lower() != "none"
            else "none"
        )
        archive_algorithm = Config.COMPRESSION_ARCHIVE_ALGORITHM

        msg = f"""<b>Compression Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {compression_enabled}
• <b>Priority:</b> <code>{compression_priority}</code>
• <b>RO:</b> {compression_delete_original}

<b>Video Compression Settings:</b>
• <b>Status:</b> {video_enabled}
• <b>Preset:</b> <code>{video_preset}</code>
• <b>CRF:</b> <code>{video_crf}</code>
• <b>Codec:</b> <code>{video_codec}</code>
• <b>Tune:</b> <code>{video_tune}</code>
• <b>Pixel Format:</b> <code>{video_pixel_format}</code>
• <b>Bitdepth:</b> <code>{video_bitdepth}</code>
• <b>Bitrate:</b> <code>{video_bitrate}</code>
• <b>Resolution:</b> <code>{video_resolution}</code>
• <b>Format:</b> <code>{video_format}</code>

<b>Audio Compression Settings:</b>
• <b>Status:</b> {audio_enabled}
• <b>Preset:</b> <code>{audio_preset}</code>
• <b>Codec:</b> <code>{audio_codec}</code>
• <b>Bitrate:</b> <code>{audio_bitrate}</code>
• <b>Channels:</b> <code>{audio_channels}</code>
• <b>Bitdepth:</b> <code>{audio_bitdepth}</code>
• <b>Format:</b> <code>{audio_format}</code>

<b>Image Compression Settings:</b>
• <b>Status:</b> {image_enabled}
• <b>Preset:</b> <code>{image_preset}</code>
• <b>Quality:</b> <code>{image_quality}</code>
• <b>Resize:</b> <code>{image_resize}</code>
• <b>Format:</b> <code>{image_format}</code>

<b>Document Compression Settings:</b>
• <b>Status:</b> {document_enabled}
• <b>Preset:</b> <code>{document_preset}</code>
• <b>DPI:</b> <code>{document_dpi}</code>
• <b>Format:</b> <code>{document_format}</code>

<b>Subtitle Compression Settings:</b>
• <b>Status:</b> {subtitle_enabled}
• <b>Preset:</b> <code>{subtitle_preset}</code>
• <b>Encoding:</b> <code>{subtitle_encoding}</code>
• <b>Format:</b> <code>{subtitle_format}</code>

<b>Archive Compression Settings:</b>
• <b>Status:</b> {archive_enabled}
• <b>Preset:</b> <code>{archive_preset}</code>
• <b>Level:</b> <code>{archive_level}</code>
• <b>Method:</b> <code>{archive_method}</code>
• <b>Format:</b> <code>{archive_format}</code>
• <b>Password:</b> <code>{archive_password}</code>
• <b>Algorithm:</b> <code>{archive_algorithm}</code>

<b>Usage:</b>
• Main Compression toggle must be enabled
• Media type specific toggles must be enabled for respective compressions
• Use <code>-video-fast</code>, <code>-audio-medium</code>, etc. for preset flags
• Add <code>-del</code> to delete original files after compression

Configure global compression settings that will be used when user settings are not available."""

    elif key == "mediatools_convert":
        # Add buttons for convert settings
        # General convert settings
        general_settings = [
            "CONVERT_ENABLED",
            "CONVERT_PRIORITY",
            "CONVERT_DELETE_ORIGINAL",
        ]

        # Video convert settings
        video_settings = [
            "CONVERT_VIDEO_ENABLED",
            "CONVERT_VIDEO_FORMAT",
            "CONVERT_VIDEO_CODEC",
            "CONVERT_VIDEO_QUALITY",
            "CONVERT_VIDEO_CRF",
            "CONVERT_VIDEO_PRESET",
            "CONVERT_VIDEO_MAINTAIN_QUALITY",
            "CONVERT_VIDEO_RESOLUTION",
            "CONVERT_VIDEO_FPS",
        ]

        # Audio convert settings
        audio_settings = [
            "CONVERT_AUDIO_ENABLED",
            "CONVERT_AUDIO_FORMAT",
            "CONVERT_AUDIO_CODEC",
            "CONVERT_AUDIO_BITRATE",
            "CONVERT_AUDIO_CHANNELS",
            "CONVERT_AUDIO_SAMPLING",
            "CONVERT_AUDIO_VOLUME",
        ]

        # Subtitle convert settings
        subtitle_settings = [
            "CONVERT_SUBTITLE_ENABLED",
            "CONVERT_SUBTITLE_FORMAT",
            "CONVERT_SUBTITLE_ENCODING",
            "CONVERT_SUBTITLE_LANGUAGE",
        ]

        # Document convert settings
        document_settings = [
            "CONVERT_DOCUMENT_ENABLED",
            "CONVERT_DOCUMENT_FORMAT",
            "CONVERT_DOCUMENT_QUALITY",
            "CONVERT_DOCUMENT_DPI",
        ]

        # Archive convert settings
        archive_settings = [
            "CONVERT_ARCHIVE_ENABLED",
            "CONVERT_ARCHIVE_FORMAT",
            "CONVERT_ARCHIVE_LEVEL",
            "CONVERT_ARCHIVE_METHOD",
        ]

        # Combine all settings
        convert_settings = (
            general_settings
            + video_settings
            + audio_settings
            + subtitle_settings
            + document_settings
            + archive_settings
        )

        for setting in convert_settings:
            # Create display name based on setting type
            if setting.startswith("CONVERT_VIDEO_"):
                display_name = (
                    "Video "
                    + setting.replace("CONVERT_VIDEO_", "").replace("_", " ").title()
                )
            elif setting.startswith("CONVERT_AUDIO_"):
                display_name = (
                    "Audio "
                    + setting.replace("CONVERT_AUDIO_", "").replace("_", " ").title()
                )
            elif setting.startswith("CONVERT_SUBTITLE_"):
                display_name = (
                    "Subtitle "
                    + setting.replace("CONVERT_SUBTITLE_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("CONVERT_DOCUMENT_"):
                display_name = (
                    "Document "
                    + setting.replace("CONVERT_DOCUMENT_", "")
                    .replace("_", " ")
                    .title()
                )
            elif setting.startswith("CONVERT_ARCHIVE_"):
                display_name = (
                    "Archive "
                    + setting.replace("CONVERT_ARCHIVE_", "")
                    .replace("_", " ")
                    .title()
                )
            else:
                display_name = (
                    setting.replace("CONVERT_", "").replace("_", " ").title()
                )

            # For boolean settings, add toggle buttons
            if setting in [
                "CONVERT_ENABLED",
                "CONVERT_DELETE_ORIGINAL",
                "CONVERT_VIDEO_ENABLED",
                "CONVERT_VIDEO_MAINTAIN_QUALITY",
                "CONVERT_AUDIO_ENABLED",
                "CONVERT_SUBTITLE_ENABLED",
                "CONVERT_DOCUMENT_ENABLED",
                "CONVERT_ARCHIVE_ENABLED",
            ]:
                setting_value = getattr(Config, setting, False)
                status = "✅ ON" if setting_value else "❌ OFF"

                # Format display name with status
                if setting == "CONVERT_ENABLED":
                    display_name = f"Enabled: {status}"
                elif setting == "CONVERT_DELETE_ORIGINAL":
                    display_name = f"RO: {status}"
                elif setting == "CONVERT_VIDEO_ENABLED":
                    display_name = f"Video Enabled: {status}"
                elif setting == "CONVERT_AUDIO_ENABLED":
                    display_name = f"Audio Enabled: {status}"
                elif setting == "CONVERT_SUBTITLE_ENABLED":
                    display_name = f"Subtitle Enabled: {status}"
                elif setting == "CONVERT_DOCUMENT_ENABLED":
                    display_name = f"Document Enabled: {status}"
                elif setting == "CONVERT_ARCHIVE_ENABLED":
                    display_name = f"Archive Enabled: {status}"
                else:
                    display_name = f"{display_name}: {status}"

                # Create toggle button
                buttons.data_button(
                    display_name,
                    f"botset toggle {setting} {not setting_value}",
                )
                continue

            # For non-boolean settings, use editvar
            buttons.data_button(display_name, f"botset editvar {setting}")

        if state == "view":
            buttons.data_button("Edit", "botset edit mediatools_convert")
        else:
            buttons.data_button("View", "botset view mediatools_convert")

        buttons.data_button("Default", "botset default_convert")

        buttons.data_button("Back", "botset mediatools", "footer")
        buttons.data_button("Close", "botset close", "footer")

        # Get current convert settings
        convert_enabled = "✅ Enabled" if Config.CONVERT_ENABLED else "❌ Disabled"
        convert_priority = f"{Config.CONVERT_PRIORITY}"
        convert_delete_original = (
            "✅ Enabled" if Config.CONVERT_DELETE_ORIGINAL else "❌ Disabled"
        )

        # Video settings
        video_enabled = (
            "✅ Enabled" if Config.CONVERT_VIDEO_ENABLED else "❌ Disabled"
        )
        video_format = Config.CONVERT_VIDEO_FORMAT
        video_codec = Config.CONVERT_VIDEO_CODEC
        video_quality = Config.CONVERT_VIDEO_QUALITY
        video_crf = Config.CONVERT_VIDEO_CRF
        video_preset = Config.CONVERT_VIDEO_PRESET
        video_maintain_quality = (
            "✅ Enabled" if Config.CONVERT_VIDEO_MAINTAIN_QUALITY else "❌ Disabled"
        )
        video_resolution = Config.CONVERT_VIDEO_RESOLUTION
        video_fps = Config.CONVERT_VIDEO_FPS

        # Audio settings
        audio_enabled = (
            "✅ Enabled" if Config.CONVERT_AUDIO_ENABLED else "❌ Disabled"
        )
        audio_format = Config.CONVERT_AUDIO_FORMAT
        audio_codec = Config.CONVERT_AUDIO_CODEC
        audio_bitrate = Config.CONVERT_AUDIO_BITRATE
        audio_channels = Config.CONVERT_AUDIO_CHANNELS
        audio_sampling = Config.CONVERT_AUDIO_SAMPLING
        audio_volume = Config.CONVERT_AUDIO_VOLUME

        # Subtitle settings
        subtitle_enabled = (
            "✅ Enabled" if Config.CONVERT_SUBTITLE_ENABLED else "❌ Disabled"
        )
        subtitle_format = Config.CONVERT_SUBTITLE_FORMAT
        subtitle_encoding = Config.CONVERT_SUBTITLE_ENCODING
        subtitle_language = Config.CONVERT_SUBTITLE_LANGUAGE

        # Document settings
        document_enabled = (
            "✅ Enabled" if Config.CONVERT_DOCUMENT_ENABLED else "❌ Disabled"
        )
        document_format = Config.CONVERT_DOCUMENT_FORMAT
        document_quality = Config.CONVERT_DOCUMENT_QUALITY
        document_dpi = Config.CONVERT_DOCUMENT_DPI

        # Archive settings
        archive_enabled = (
            "✅ Enabled" if Config.CONVERT_ARCHIVE_ENABLED else "❌ Disabled"
        )
        archive_format = Config.CONVERT_ARCHIVE_FORMAT
        archive_level = Config.CONVERT_ARCHIVE_LEVEL
        archive_method = Config.CONVERT_ARCHIVE_METHOD

        msg = f"""<b>Convert Settings</b> | State: {state}

<b>General Settings:</b>
• <b>Status:</b> {convert_enabled}
• <b>Priority:</b> <code>{convert_priority}</code>
• <b>RO:</b> {convert_delete_original}

<b>Video Convert Settings:</b>
• <b>Status:</b> {video_enabled}
• <b>Format:</b> <code>{video_format}</code>
• <b>Codec:</b> <code>{video_codec}</code>
• <b>Quality:</b> <code>{video_quality}</code>
• <b>CRF:</b> <code>{video_crf}</code>
• <b>Preset:</b> <code>{video_preset}</code>
• <b>Maintain Quality:</b> {video_maintain_quality}
• <b>Resolution:</b> <code>{video_resolution}</code>
• <b>FPS:</b> <code>{video_fps}</code>

<b>Audio Convert Settings:</b>
• <b>Status:</b> {audio_enabled}
• <b>Format:</b> <code>{audio_format}</code>
• <b>Codec:</b> <code>{audio_codec}</code>
• <b>Bitrate:</b> <code>{audio_bitrate}</code>
• <b>Channels:</b> <code>{audio_channels}</code>
• <b>Sampling:</b> <code>{audio_sampling}</code>
• <b>Volume:</b> <code>{audio_volume}</code>

<b>Subtitle Convert Settings:</b>
• <b>Status:</b> {subtitle_enabled}
• <b>Format:</b> <code>{subtitle_format}</code>
• <b>Encoding:</b> <code>{subtitle_encoding}</code>
• <b>Language:</b> <code>{subtitle_language}</code>

<b>Document Convert Settings:</b>
• <b>Status:</b> {document_enabled}
• <b>Format:</b> <code>{document_format}</code>
• <b>Quality:</b> <code>{document_quality}</code>
• <b>DPI:</b> <code>{document_dpi}</code>

<b>Archive Convert Settings:</b>
• <b>Status:</b> {archive_enabled}
• <b>Format:</b> <code>{archive_format}</code>
• <b>Level:</b> <code>{archive_level}</code>
• <b>Method:</b> <code>{archive_method}</code>

<b>Usage:</b>
• Main Convert toggle must be enabled
• Media type specific toggles must be enabled for respective conversions
• Use <code>-cv format</code> for video conversion (e.g., <code>-cv mp4</code>)
• Use <code>-ca format</code> for audio conversion (e.g., <code>-ca mp3</code>)
• Use <code>-cs format</code> for subtitle conversion (e.g., <code>-cs srt</code>)
• Use <code>-cd format</code> for document conversion (e.g., <code>-cd pdf</code>)
• Use <code>-cr format</code> for archive conversion (e.g., <code>-cr zip</code>)
• Add <code>-del</code> to delete original files after conversion

Configure global convert settings that will be used when user settings are not available."""

    elif key == "mediatools_metadata":
        # Add buttons for each metadata setting in a 2-column layout
        # Global metadata settings
        global_settings = [
            "METADATA_ALL",
            "METADATA_TITLE",
            "METADATA_AUTHOR",
            "METADATA_COMMENT",
        ]

        # Video metadata settings
        video_settings = [
            "METADATA_VIDEO_TITLE",
            "METADATA_VIDEO_AUTHOR",
            "METADATA_VIDEO_COMMENT",
        ]

        # Audio metadata settings
        audio_settings = [
            "METADATA_AUDIO_TITLE",
            "METADATA_AUDIO_AUTHOR",
            "METADATA_AUDIO_COMMENT",
        ]

        # Subtitle metadata settings
        subtitle_settings = [
            "METADATA_SUBTITLE_TITLE",
            "METADATA_SUBTITLE_AUTHOR",
            "METADATA_SUBTITLE_COMMENT",
        ]

        # Combine all settings
        metadata_settings = (
            global_settings + video_settings + audio_settings + subtitle_settings
        )

        for setting in metadata_settings:
            # Skip the legacy key
            if setting == "METADATA_KEY":
                continue

            # Create a more user-friendly display name
            if setting == "METADATA_ALL":
                display_name = "All Fields"
            elif setting.startswith("METADATA_VIDEO_"):
                display_name = (
                    "Video " + setting.replace("METADATA_VIDEO_", "").title()
                )
            elif setting.startswith("METADATA_AUDIO_"):
                display_name = (
                    "Audio " + setting.replace("METADATA_AUDIO_", "").title()
                )
            elif setting.startswith("METADATA_SUBTITLE_"):
                display_name = (
                    "Subtitle " + setting.replace("METADATA_SUBTITLE_", "").title()
                )
            else:
                display_name = "Global " + setting.replace("METADATA_", "").title()

            # Always use editvar in both view and edit states to ensure consistent behavior
            callback_data = f"botset editvar {setting}"
            buttons.data_button(display_name, callback_data)

        if state == "view":
            buttons.data_button("Edit", "botset edit mediatools_metadata")
        else:
            buttons.data_button("View", "botset view mediatools_metadata")

        buttons.data_button("Default", "botset default_metadata")

        buttons.data_button("Back", "botset mediatools", "footer")
        buttons.data_button("Close", "botset close", "footer")

        # Get current global metadata settings
        metadata_all = Config.METADATA_ALL or "None"
        metadata_title = Config.METADATA_TITLE or "None"
        metadata_author = Config.METADATA_AUTHOR or "None"
        metadata_comment = Config.METADATA_COMMENT or "None"

        # Get current video metadata settings
        metadata_video_title = Config.METADATA_VIDEO_TITLE or "None"
        metadata_video_author = Config.METADATA_VIDEO_AUTHOR or "None"
        metadata_video_comment = Config.METADATA_VIDEO_COMMENT or "None"

        # Get current audio metadata settings
        metadata_audio_title = Config.METADATA_AUDIO_TITLE or "None"
        metadata_audio_author = Config.METADATA_AUDIO_AUTHOR or "None"
        metadata_audio_comment = Config.METADATA_AUDIO_COMMENT or "None"

        # Get current subtitle metadata settings
        metadata_subtitle_title = Config.METADATA_SUBTITLE_TITLE or "None"
        metadata_subtitle_author = Config.METADATA_SUBTITLE_AUTHOR or "None"
        metadata_subtitle_comment = Config.METADATA_SUBTITLE_COMMENT or "None"

        msg = f"""<b>Metadata Settings</b> | State: {state}

<b>Global Settings:</b>
<b>All Fields:</b> <code>{metadata_all}</code>
<b>Global Title:</b> <code>{metadata_title}</code>
<b>Global Author:</b> <code>{metadata_author}</code>
<b>Global Comment:</b> <code>{metadata_comment}</code>

<b>Video Track Settings:</b>
<b>Video Title:</b> <code>{metadata_video_title}</code>
<b>Video Author:</b> <code>{metadata_video_author}</code>
<b>Video Comment:</b> <code>{metadata_video_comment}</code>

<b>Audio Track Settings:</b>
<b>Audio Title:</b> <code>{metadata_audio_title}</code>
<b>Audio Author:</b> <code>{metadata_audio_author}</code>
<b>Audio Comment:</b> <code>{metadata_audio_comment}</code>

<b>Subtitle Track Settings:</b>
<b>Subtitle Title:</b> <code>{metadata_subtitle_title}</code>
<b>Subtitle Author:</b> <code>{metadata_subtitle_author}</code>
<b>Subtitle Comment:</b> <code>{metadata_subtitle_comment}</code>

<b>Note:</b> 'All Fields' takes priority over all other settings when set.

Configure global metadata settings that will be used when user settings are not available."""

    elif key == "mediatools_merge_config":
        # Add buttons for each merge configuration setting in a 2-column layout
        # Group settings by category
        formats = [
            "MERGE_OUTPUT_FORMAT_VIDEO",
            "MERGE_OUTPUT_FORMAT_AUDIO",
            "MERGE_OUTPUT_FORMAT_IMAGE",
            "MERGE_OUTPUT_FORMAT_DOCUMENT",
            "MERGE_OUTPUT_FORMAT_SUBTITLE",
        ]

        video_settings = [
            "MERGE_VIDEO_CODEC",
            "MERGE_VIDEO_QUALITY",
            "MERGE_VIDEO_PRESET",
            "MERGE_VIDEO_CRF",
            "MERGE_VIDEO_PIXEL_FORMAT",
            "MERGE_VIDEO_TUNE",
            "MERGE_VIDEO_FASTSTART",
        ]

        audio_settings = [
            "MERGE_AUDIO_CODEC",
            "MERGE_AUDIO_BITRATE",
            "MERGE_AUDIO_CHANNELS",
            "MERGE_AUDIO_SAMPLING",
            "MERGE_AUDIO_VOLUME",
        ]

        image_settings = [
            "MERGE_IMAGE_MODE",
            "MERGE_IMAGE_COLUMNS",
            "MERGE_IMAGE_QUALITY",
            "MERGE_IMAGE_DPI",
            "MERGE_IMAGE_RESIZE",
            "MERGE_IMAGE_BACKGROUND",
        ]

        subtitle_settings = [
            "MERGE_SUBTITLE_ENCODING",
            "MERGE_SUBTITLE_FONT",
            "MERGE_SUBTITLE_FONT_SIZE",
            "MERGE_SUBTITLE_FONT_COLOR",
            "MERGE_SUBTITLE_BACKGROUND",
        ]

        document_settings = [
            "MERGE_DOCUMENT_PAPER_SIZE",
            "MERGE_DOCUMENT_ORIENTATION",
            "MERGE_DOCUMENT_MARGIN",
        ]

        metadata_settings = [
            "MERGE_METADATA_TITLE",
            "MERGE_METADATA_AUTHOR",
            "MERGE_METADATA_COMMENT",
        ]

        # Combine all settings
        merge_config_settings = (
            formats
            + video_settings
            + audio_settings
            + image_settings
            + subtitle_settings
            + document_settings
            + metadata_settings
        )

        # 5 rows per page, 2 columns = 10 items per page
        items_per_page = 10  # 5 rows * 2 columns
        total_pages = (
            len(merge_config_settings) + items_per_page - 1
        ) // items_per_page

        # Ensure page is valid
        # Use the global merge_config_page variable if page is not provided
        if page == 0 and globals()["merge_config_page"] != 0:
            current_page = globals()["merge_config_page"]
        else:
            current_page = page
            # Update the global merge_config_page variable
            globals()["merge_config_page"] = current_page

        # Validate page number
        if current_page >= total_pages:
            current_page = 0
            globals()["merge_config_page"] = 0
        elif current_page < 0:
            current_page = total_pages - 1
            globals()["merge_config_page"] = total_pages - 1

        # Get settings for current page
        start_idx = current_page * items_per_page
        end_idx = min(start_idx + items_per_page, len(merge_config_settings))
        current_page_settings = merge_config_settings[start_idx:end_idx]

        # Add buttons for each setting on current page
        for setting in current_page_settings:
            display_name = setting.replace("MERGE_", "").replace("_", " ").title()
            buttons.data_button(display_name, f"botset editvar {setting}")

        # Add action buttons in a separate row
        if state == "view":
            buttons.data_button(
                "Edit", "botset edit mediatools_merge_config", "footer"
            )
        else:
            buttons.data_button(
                "View", "botset view mediatools_merge_config", "footer"
            )

        # Add Default button
        buttons.data_button("Default", "botset default_merge_config", "footer")

        # Add navigation buttons
        buttons.data_button("Back", "botset mediatools_merge", "footer")
        buttons.data_button("Close", "botset close", "footer")

        # Add pagination buttons in a separate row below action buttons
        if total_pages > 1:
            for i in range(total_pages):
                # Make the current page button different
                if i == current_page:
                    buttons.data_button(
                        f"[{i + 1}]", f"botset start_merge_config {i}", "page"
                    )
                else:
                    buttons.data_button(
                        str(i + 1), f"botset start_merge_config {i}", "page"
                    )

            # Add a debug log message# Get current merge configuration settings - Output formats
        video_format = (
            Config.MERGE_OUTPUT_FORMAT_VIDEO
            or DEFAULT_VALUES["MERGE_OUTPUT_FORMAT_VIDEO"] + " (Default)"
        )
        audio_format = (
            Config.MERGE_OUTPUT_FORMAT_AUDIO
            or DEFAULT_VALUES["MERGE_OUTPUT_FORMAT_AUDIO"] + " (Default)"
        )
        image_format = (
            Config.MERGE_OUTPUT_FORMAT_IMAGE
            or DEFAULT_VALUES["MERGE_OUTPUT_FORMAT_IMAGE"] + " (Default)"
        )
        document_format = (
            Config.MERGE_OUTPUT_FORMAT_DOCUMENT
            or DEFAULT_VALUES["MERGE_OUTPUT_FORMAT_DOCUMENT"] + " (Default)"
        )
        subtitle_format = (
            Config.MERGE_OUTPUT_FORMAT_SUBTITLE
            or DEFAULT_VALUES["MERGE_OUTPUT_FORMAT_SUBTITLE"] + " (Default)"
        )

        # Video settings
        video_codec = (
            Config.MERGE_VIDEO_CODEC
            or DEFAULT_VALUES["MERGE_VIDEO_CODEC"] + " (Default)"
        )
        video_quality = (
            Config.MERGE_VIDEO_QUALITY
            or DEFAULT_VALUES["MERGE_VIDEO_QUALITY"] + " (Default)"
        )
        video_preset = (
            Config.MERGE_VIDEO_PRESET
            or DEFAULT_VALUES["MERGE_VIDEO_PRESET"] + " (Default)"
        )
        video_crf = (
            Config.MERGE_VIDEO_CRF
            or DEFAULT_VALUES["MERGE_VIDEO_CRF"] + " (Default)"
        )
        video_pixel_format = (
            Config.MERGE_VIDEO_PIXEL_FORMAT
            or DEFAULT_VALUES["MERGE_VIDEO_PIXEL_FORMAT"] + " (Default)"
        )
        video_tune = (
            Config.MERGE_VIDEO_TUNE
            or DEFAULT_VALUES["MERGE_VIDEO_TUNE"] + " (Default)"
        )
        video_faststart = "Enabled" if Config.MERGE_VIDEO_FASTSTART else "Disabled"

        # Audio settings
        audio_codec = (
            Config.MERGE_AUDIO_CODEC
            or DEFAULT_VALUES["MERGE_AUDIO_CODEC"] + " (Default)"
        )
        audio_bitrate = (
            Config.MERGE_AUDIO_BITRATE
            or DEFAULT_VALUES["MERGE_AUDIO_BITRATE"] + " (Default)"
        )
        audio_channels = (
            Config.MERGE_AUDIO_CHANNELS
            or DEFAULT_VALUES["MERGE_AUDIO_CHANNELS"] + " (Default)"
        )
        audio_sampling = (
            Config.MERGE_AUDIO_SAMPLING
            or DEFAULT_VALUES["MERGE_AUDIO_SAMPLING"] + " (Default)"
        )
        audio_volume = (
            Config.MERGE_AUDIO_VOLUME
            or DEFAULT_VALUES["MERGE_AUDIO_VOLUME"] + " (Default)"
        )

        # Image settings
        image_mode = (
            Config.MERGE_IMAGE_MODE
            or DEFAULT_VALUES["MERGE_IMAGE_MODE"] + " (Default)"
        )
        image_columns = (
            Config.MERGE_IMAGE_COLUMNS
            or DEFAULT_VALUES["MERGE_IMAGE_COLUMNS"] + " (Default)"
        )
        image_quality = (
            Config.MERGE_IMAGE_QUALITY
            or str(DEFAULT_VALUES["MERGE_IMAGE_QUALITY"]) + " (Default)"
        )
        image_dpi = (
            Config.MERGE_IMAGE_DPI
            or DEFAULT_VALUES["MERGE_IMAGE_DPI"] + " (Default)"
        )
        image_resize = (
            Config.MERGE_IMAGE_RESIZE
            or DEFAULT_VALUES["MERGE_IMAGE_RESIZE"] + " (Default)"
        )
        image_background = (
            Config.MERGE_IMAGE_BACKGROUND
            or DEFAULT_VALUES["MERGE_IMAGE_BACKGROUND"] + " (Default)"
        )

        # Subtitle settings
        subtitle_encoding = (
            Config.MERGE_SUBTITLE_ENCODING
            or DEFAULT_VALUES["MERGE_SUBTITLE_ENCODING"] + " (Default)"
        )
        subtitle_font = (
            Config.MERGE_SUBTITLE_FONT
            or DEFAULT_VALUES["MERGE_SUBTITLE_FONT"] + " (Default)"
        )
        subtitle_font_size = (
            Config.MERGE_SUBTITLE_FONT_SIZE
            or DEFAULT_VALUES["MERGE_SUBTITLE_FONT_SIZE"] + " (Default)"
        )
        subtitle_font_color = (
            Config.MERGE_SUBTITLE_FONT_COLOR
            or DEFAULT_VALUES["MERGE_SUBTITLE_FONT_COLOR"] + " (Default)"
        )
        subtitle_background = (
            Config.MERGE_SUBTITLE_BACKGROUND
            or DEFAULT_VALUES["MERGE_SUBTITLE_BACKGROUND"] + " (Default)"
        )

        # Document settings
        document_paper_size = (
            Config.MERGE_DOCUMENT_PAPER_SIZE
            or DEFAULT_VALUES["MERGE_DOCUMENT_PAPER_SIZE"] + " (Default)"
        )
        document_orientation = (
            Config.MERGE_DOCUMENT_ORIENTATION
            or DEFAULT_VALUES["MERGE_DOCUMENT_ORIENTATION"] + " (Default)"
        )
        document_margin = (
            Config.MERGE_DOCUMENT_MARGIN
            or DEFAULT_VALUES["MERGE_DOCUMENT_MARGIN"] + " (Default)"
        )

        # Metadata settings
        metadata_title = (
            Config.MERGE_METADATA_TITLE
            or DEFAULT_VALUES["MERGE_METADATA_TITLE"] + " (Default)"
        )
        metadata_author = (
            Config.MERGE_METADATA_AUTHOR
            or DEFAULT_VALUES["MERGE_METADATA_AUTHOR"] + " (Default)"
        )
        metadata_comment = (
            Config.MERGE_METADATA_COMMENT
            or DEFAULT_VALUES["MERGE_METADATA_COMMENT"] + " (Default)"
        )

        msg = f"""<b>Merge Configuration</b> | State: {state}

<b>Output Formats:</b>
• <b>Video:</b> <code>{video_format}</code>
• <b>Audio:</b> <code>{audio_format}</code>
• <b>Image:</b> <code>{image_format}</code>
• <b>Document:</b> <code>{document_format}</code>
• <b>Subtitle:</b> <code>{subtitle_format}</code>

<b>Video Settings:</b>
• <b>Codec:</b> <code>{video_codec}</code>
• <b>Quality:</b> <code>{video_quality}</code>
• <b>Preset:</b> <code>{video_preset}</code>
• <b>CRF:</b> <code>{video_crf}</code>
• <b>Pixel Format:</b> <code>{video_pixel_format}</code>
• <b>Tune:</b> <code>{video_tune}</code>
• <b>Faststart:</b> <code>{video_faststart}</code>

<b>Audio Settings:</b>
• <b>Codec:</b> <code>{audio_codec}</code>
• <b>Bitrate:</b> <code>{audio_bitrate}</code>
• <b>Channels:</b> <code>{audio_channels}</code>
• <b>Sampling:</b> <code>{audio_sampling}</code>
• <b>Volume:</b> <code>{audio_volume}</code>

<b>Image Settings:</b>
• <b>Mode:</b> <code>{image_mode}</code>
• <b>Columns:</b> <code>{image_columns}</code>
• <b>Quality:</b> <code>{image_quality}</code>
• <b>DPI:</b> <code>{image_dpi}</code>
• <b>Resize:</b> <code>{image_resize}</code>
• <b>Background:</b> <code>{image_background}</code>

<b>Subtitle Settings:</b>
• <b>Encoding:</b> <code>{subtitle_encoding}</code>
• <b>Font:</b> <code>{subtitle_font}</code>
• <b>Font Size:</b> <code>{subtitle_font_size}</code>
• <b>Font Color:</b> <code>{subtitle_font_color}</code>
• <b>Background:</b> <code>{subtitle_background}</code>

<b>Document Settings:</b>
• <b>Paper Size:</b> <code>{document_paper_size}</code>
• <b>Orientation:</b> <code>{document_orientation}</code>
• <b>Margin:</b> <code>{document_margin}</code>

<b>Metadata:</b>
• <b>Title:</b> <code>{metadata_title}</code>
• <b>Author:</b> <code>{metadata_author}</code>
• <b>Comment:</b> <code>{metadata_comment}</code>

Configure advanced merge settings that will be used when user settings are not available."""

        # Determine which category is shown on the current page
        start_idx = current_page * items_per_page
        end_idx = min(start_idx + items_per_page, len(merge_config_settings))

        # Get the categories shown on the current page
        categories = []
        if any(
            setting in formats
            for setting in merge_config_settings[start_idx:end_idx]
        ):
            categories.append("Formats")
        if any(
            setting in video_settings
            for setting in merge_config_settings[start_idx:end_idx]
        ):
            categories.append("Video")
        if any(
            setting in audio_settings
            for setting in merge_config_settings[start_idx:end_idx]
        ):
            categories.append("Audio")
        if any(
            setting in image_settings
            for setting in merge_config_settings[start_idx:end_idx]
        ):
            categories.append("Image")
        if any(
            setting in subtitle_settings
            for setting in merge_config_settings[start_idx:end_idx]
        ):
            categories.append("Subtitle")
        if any(
            setting in document_settings
            for setting in merge_config_settings[start_idx:end_idx]
        ):
            categories.append("Document")
        if any(
            setting in metadata_settings
            for setting in merge_config_settings[start_idx:end_idx]
        ):
            categories.append("Metadata")

        category_text = ", ".join(categories)

        # Add category and page info to message
        msg += f"\n\nCurrent page shows: {category_text} settings."
        if total_pages > 1:
            msg += f"\n<b>Page:</b> {current_page + 1}/{total_pages}"

    if key is None:
        button = buttons.build_menu(2)
    elif key in {
        "mediatools_merge",
        "mediatools_merge_config",
        "mediatools_watermark_text",
    }:
        # Build the menu with 2 columns for settings, 4 columns for action buttons, and 8 columns for pagination
        button = buttons.build_menu(2, 8, 4, 8)
    elif key in {"mediatools_watermark", "mediatools_convert"}:
        # Build the menu with 2 columns for settings
        button = buttons.build_menu(2)
    else:
        button = buttons.build_menu(2)
    return msg, button


async def update_buttons(message, key=None, edit_type=None, page=0):
    user_id = message.chat.id

    # If edit_type is provided, update the state
    if edit_type:
        globals()["state"] = edit_type

    # Special handling for mediatools_add to ensure all ADD_ settings are initialized
    if key == "mediatools_add":
        # Initialize all ADD_ settings with their default values in the database
        add_settings = {
            k: value for k, value in DEFAULT_VALUES.items() if k.startswith("ADD_")
        }
        # Update the database with all ADD_ settings
        await database.update_config(add_settings)

    # Special handling for mediatools_swap to ensure all SWAP_ settings are initialized
    if key == "mediatools_swap":
        # Initialize all SWAP_ settings with their default values in the database
        swap_settings = {
            k: value for k, value in DEFAULT_VALUES.items() if k.startswith("SWAP_")
        }
        # Update the database with all SWAP_ settings
        await database.update_config(swap_settings)

    # Get the buttons and message for the current state and key
    msg, button = await get_buttons(key, edit_type, page, user_id)

    # Update the message with the new buttons
    await edit_message(message, msg, button)


async def _process_zotify_credentials_upload(
    credentials_content: str,
    user_id: int,
    file_name: str = "zotify_credentials.json",
) -> tuple[bool, str]:
    """
    Process zotify credentials upload with validation and database storage.

    Args:
        credentials_content: The JSON credentials content as string
        user_id: The user ID for database storage
        file_name: The original file name (for logging)

    Returns:
        tuple[bool, str]: (success, error_message)
    """
    try:
        # Validate JSON format
        try:
            credentials_data = json.loads(credentials_content)

            # Basic validation - check if it looks like Spotify credentials
            if not isinstance(credentials_data, dict):
                raise ValueError("Credentials must be a JSON object")

        except Exception as e:
            return False, f"Invalid JSON format: {e}"

        # Save credentials to database and file using the zotify config helper
        if not zotify_config:
            return False, "Zotify config helper not available"

        success = await zotify_config.save_credentials(credentials_data, user_id)

        if success:
            LOGGER.info(
                f"Zotify credentials from {file_name} uploaded and applied successfully for user {user_id}"
            )
            return True, ""

        error_msg = "Failed to save Zotify credentials to database"
        LOGGER.error(error_msg)
        return False, error_msg

    except Exception as e:
        error_msg = f"Error processing Zotify credentials: {e}"
        LOGGER.error(error_msg)
        return False, error_msg


async def _process_streamrip_config_upload(
    config_content: str, file_name: str = "streamrip_config.toml"
) -> tuple[bool, str]:
    """
    Process streamrip config upload with validation and database storage.

    Args:
        config_content: The TOML config content as string
        file_name: The original file name (for logging)

    Returns:
        tuple[bool, str]: (success, error_message)
    """
    try:
        # Validate TOML format
        try:
            toml.loads(config_content)
        except Exception as e:
            return False, f"Invalid TOML format: {e}"

        # Save to database using streamrip config helper
        if not streamrip_config:
            return False, "Streamrip config helper not available"

        success = await streamrip_config.save_custom_config_to_db(config_content)

        if success:
            # Reinitialize streamrip config to use the new custom config
            await streamrip_config.initialize()
            LOGGER.info(
                f"Streamrip custom config from {file_name} uploaded and applied successfully"
            )
            return True, ""

        error_msg = "Failed to save streamrip config to database"
        LOGGER.error(error_msg)
        return False, error_msg

    except Exception as e:
        error_msg = f"Error processing streamrip config: {e}"
        LOGGER.error(error_msg)
        return False, error_msg


async def _generate_current_config_content() -> str:
    """Generate current streamrip config content based on bot settings"""
    try:
        # Helper function to safely get config attributes
        def get_config_attr(attr_name, default_value=""):
            return getattr(Config, attr_name, default_value)

        # Generate TOML config based on current bot settings
        return f"""# Streamrip Configuration Generated from Bot Settings
# Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

[session]
[session.downloads]
folder = "{DOWNLOAD_DIR}"
concurrency = {get_config_attr("STREAMRIP_CONCURRENT_DOWNLOADS", 4)}
max_connections = {get_config_attr("STREAMRIP_MAX_CONNECTIONS", 6)}
requests_per_minute = {get_config_attr("STREAMRIP_REQUESTS_PER_MINUTE", 60)}
source_subdirectories = {str(get_config_attr("STREAMRIP_SOURCE_SUBDIRECTORIES", False)).lower()}
disc_subdirectories = {str(get_config_attr("STREAMRIP_DISC_SUBDIRECTORIES", True)).lower()}
verify_ssl = {str(get_config_attr("STREAMRIP_VERIFY_SSL", True)).lower()}

[session.qobuz]
enabled = {str(get_config_attr("STREAMRIP_QOBUZ_ENABLED", True)).lower()}
quality = {get_config_attr("STREAMRIP_QOBUZ_QUALITY", 3)}
email_or_userid = "{get_config_attr("STREAMRIP_QOBUZ_EMAIL", "")}"
password_or_token = "{get_config_attr("STREAMRIP_QOBUZ_PASSWORD", "")}"
use_auth_token = {str(get_config_attr("STREAMRIP_QOBUZ_USE_AUTH_TOKEN", False)).lower()}
app_id = "{get_config_attr("STREAMRIP_QOBUZ_APP_ID", "")}"
secrets = ["{get_config_attr("STREAMRIP_QOBUZ_SECRETS", "")}"]
download_booklets = {str(get_config_attr("STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS", True)).lower()}

[session.qobuz.filters]
extras = {str(get_config_attr("STREAMRIP_QOBUZ_FILTERS_EXTRAS", False)).lower()}
repeats = {str(get_config_attr("STREAMRIP_QOBUZ_FILTERS_REPEATS", False)).lower()}
non_albums = {str(get_config_attr("STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS", False)).lower()}
features = {str(get_config_attr("STREAMRIP_QOBUZ_FILTERS_FEATURES", False)).lower()}
non_studio_albums = {str(get_config_attr("STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS", False)).lower()}
non_remaster = {str(get_config_attr("STREAMRIP_QOBUZ_FILTERS_NON_REMASTER", False)).lower()}

[session.tidal]
enabled = {str(get_config_attr("STREAMRIP_TIDAL_ENABLED", True)).lower()}
quality = {get_config_attr("STREAMRIP_TIDAL_QUALITY", 3)}
username = "{get_config_attr("STREAMRIP_TIDAL_EMAIL", "")}"
password = "{get_config_attr("STREAMRIP_TIDAL_PASSWORD", "")}"
access_token = "{get_config_attr("STREAMRIP_TIDAL_ACCESS_TOKEN", "")}"
refresh_token = "{get_config_attr("STREAMRIP_TIDAL_REFRESH_TOKEN", "")}"
user_id = "{get_config_attr("STREAMRIP_TIDAL_USER_ID", "")}"
country_code = "{get_config_attr("STREAMRIP_TIDAL_COUNTRY_CODE", "")}"
download_videos = {str(get_config_attr("STREAMRIP_TIDAL_DOWNLOAD_VIDEOS", True)).lower()}

[session.deezer]
enabled = {str(get_config_attr("STREAMRIP_DEEZER_ENABLED", True)).lower()}
quality = {get_config_attr("STREAMRIP_DEEZER_QUALITY", 2)}
arl = "{get_config_attr("STREAMRIP_DEEZER_ARL", "")}"
use_deezloader = {str(get_config_attr("STREAMRIP_DEEZER_USE_DEEZLOADER", True)).lower()}
deezloader_warnings = {str(get_config_attr("STREAMRIP_DEEZER_DEEZLOADER_WARNINGS", True)).lower()}

[session.soundcloud]
enabled = {str(get_config_attr("STREAMRIP_SOUNDCLOUD_ENABLED", True)).lower()}
quality = {get_config_attr("STREAMRIP_SOUNDCLOUD_QUALITY", 0)}
client_id = "{get_config_attr("STREAMRIP_SOUNDCLOUD_CLIENT_ID", "")}"
app_version = "{get_config_attr("STREAMRIP_SOUNDCLOUD_APP_VERSION", "")}"

[session.youtube]
enabled = {str(get_config_attr("STREAMRIP_YOUTUBE_ENABLED", True)).lower()}
quality = {get_config_attr("STREAMRIP_YOUTUBE_QUALITY", 0)}
download_videos = {str(get_config_attr("STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS", False)).lower()}
video_folder = "{get_config_attr("STREAMRIP_YOUTUBE_VIDEO_FOLDER", "")}"
video_downloads_folder = "{get_config_attr("STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER", "")}"

[session.lastfm]
enabled = {str(get_config_attr("STREAMRIP_LASTFM_ENABLED", True)).lower()}
source = "{get_config_attr("STREAMRIP_LASTFM_SOURCE", "qobuz")}"
fallback_source = "{get_config_attr("STREAMRIP_LASTFM_FALLBACK_SOURCE", "")}"

[session.conversion]
enabled = {str(get_config_attr("STREAMRIP_CONVERSION_ENABLED", False)).lower()}
codec = "{get_config_attr("STREAMRIP_CONVERSION_CODEC", "ALAC")}"
sampling_rate = {get_config_attr("STREAMRIP_CONVERSION_SAMPLING_RATE", 48000)}
bit_depth = {get_config_attr("STREAMRIP_CONVERSION_BIT_DEPTH", 24)}
lossy_bitrate = {get_config_attr("STREAMRIP_CONVERSION_LOSSY_BITRATE", 320)}

[session.database]
downloads_enabled = {str(get_config_attr("STREAMRIP_DATABASE_DOWNLOADS_ENABLED", True)).lower()}
downloads_path = "{get_config_attr("STREAMRIP_DATABASE_DOWNLOADS_PATH", "./downloads.db")}"
failed_downloads_enabled = {str(get_config_attr("STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED", True)).lower()}
failed_downloads_path = "{get_config_attr("STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH", "./failed_downloads.db")}"

[session.filepaths]
track_format = "{get_config_attr("STREAMRIP_FILEPATHS_TRACK_FORMAT", get_config_attr("STREAMRIP_FILENAME_TEMPLATE", "{tracknumber:02}. {artist} - {title}{explicit}"))}"
folder_format = "{get_config_attr("STREAMRIP_FILEPATHS_FOLDER_FORMAT", get_config_attr("STREAMRIP_FOLDER_TEMPLATE", "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"))}"
add_singles_to_folder = {str(get_config_attr("STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER", False)).lower()}
restrict_characters = {str(get_config_attr("STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS", False)).lower()}
truncate_to = {get_config_attr("STREAMRIP_FILEPATHS_TRUNCATE_TO", 120)}

[session.artwork]
embed = {str(get_config_attr("STREAMRIP_EMBED_COVER_ART", True)).lower()}
save_artwork = {str(get_config_attr("STREAMRIP_SAVE_COVER_ART", True)).lower()}
embed_size = {get_config_attr("STREAMRIP_ARTWORK_EMBED_MAX_WIDTH", 1200)}
saved_max_width = {get_config_attr("STREAMRIP_ARTWORK_SAVED_MAX_WIDTH", 1200)}

[session.metadata]
set_playlist_to_album = {str(get_config_attr("STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM", True)).lower()}
renumber_playlist_tracks = {str(get_config_attr("STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS", True)).lower()}
exclude = {get_config_attr("STREAMRIP_METADATA_EXCLUDE", [])}

[session.cli]
text_output = {str(get_config_attr("STREAMRIP_CLI_TEXT_OUTPUT", True)).lower()}
progress_bars = {str(get_config_attr("STREAMRIP_CLI_PROGRESS_BARS", True)).lower()}
max_search_results = {get_config_attr("STREAMRIP_CLI_MAX_SEARCH_RESULTS", 100)}

[session.misc]
check_for_updates = {str(get_config_attr("STREAMRIP_MISC_CHECK_FOR_UPDATES", True)).lower()}
version = "{get_config_attr("STREAMRIP_MISC_VERSION", "2.0.6")}"
"""
    except Exception as e:
        if LOGGER:
            LOGGER.error(f"Error generating config content: {e}")
        return ""


@new_task
async def handle_streamrip_config_upload(_, message, pre_message):
    """Handle the upload of a streamrip config file from bot settings."""
    user_id = message.from_user.id
    handler_dict[user_id] = False

    # Check if the message contains a document
    if not message.document:
        await send_message(message, "Please send a config file for streamrip.")
        return

    # Check file extension
    file_name = message.document.file_name
    if not file_name or not file_name.lower().endswith(".toml"):
        await send_message(
            message,
            "<b>❌ Invalid File</b>\n\n"
            "Please send a valid TOML configuration file (must end with .toml).",
        )
        return

    # Check file size (5MB limit)
    if message.document.file_size > 5 * 1024 * 1024:
        await send_message(
            message,
            "<b>❌ File Too Large</b>\n\nConfig file must be smaller than 5MB.",
        )
        return

    temp_path = None
    try:
        # Download the file
        temp_path = await message.download()

        # Read the config content using aiofiles
        async with aiopen(temp_path, encoding="utf-8") as f:
            config_content = await f.read()

        # Use the unified processing function
        success, error_msg = await _process_streamrip_config_upload(
            config_content, file_name
        )

        if success:
            await send_message(
                message,
                "<b>✅ Config Upload Successful</b>\n\n"
                "Streamrip configuration has been uploaded and applied successfully.\n\n"
                "<b>Changes:</b>\n"
                "• Custom config file saved to database\n"
                "• Streamrip will now use your custom configuration\n"
                "• Individual setting menus will show custom values\n\n"
                "<i>The bot will now use your uploaded configuration for streamrip operations.</i>",
            )
        else:
            await send_message(
                message,
                "<b>❌ Upload Failed</b>\n\n"
                f"Failed to process streamrip configuration: {error_msg}",
            )

    except Exception as e:
        if LOGGER:
            LOGGER.error(f"Error handling streamrip config upload: {e}")
        await send_message(
            message,
            f"<b>❌ Error</b>\n\nFailed to process streamrip configuration: {e}",
        )
    finally:
        # Clean up temporary file
        if temp_path:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    # Return to streamrip config menu
    await update_buttons(pre_message, "streamrip_config")


@new_task
async def handle_zotify_credentials_upload(_, message, pre_message):
    """Handle the upload of a Zotify credentials file from bot settings."""
    user_id = message.from_user.id
    handler_dict[user_id] = False

    # Check if the message contains a document
    if not message.document:
        await send_message(message, "Please send a credentials file for Zotify.")
        return

    # Check file extension
    file_name = message.document.file_name
    if not file_name or not file_name.lower().endswith(".json"):
        await send_message(
            message,
            "<b>❌ Invalid File</b>\n\n"
            "Please send a valid JSON credentials file (must end with .json).",
        )
        return

    # Check file size (5MB limit)
    if message.document.file_size > 5 * 1024 * 1024:
        await send_message(
            message,
            "<b>❌ File Too Large</b>\n\nCredentials file must be smaller than 5MB.",
        )
        return

    temp_path = None
    try:
        # Download the file
        temp_path = await message.download()

        # Read the credentials content using aiofiles
        async with aiopen(temp_path, encoding="utf-8") as f:
            credentials_content = await f.read()

        # Use the unified processing function
        success, error_msg = await _process_zotify_credentials_upload(
            credentials_content, user_id, file_name
        )

        if success:
            await send_message(
                message,
                "<b>✅ Credentials Upload Successful</b>\n\n"
                "Zotify credentials have been uploaded and saved successfully.\n\n"
                "<b>Changes:</b>\n"
                "• Credentials saved to database (persistent across restarts)\n"
                "• Credentials file created for immediate use\n"
                "• Zotify will now use your uploaded credentials\n"
                "• Authentication will be automatic for downloads\n\n"
                "<i>Your credentials are now safely stored and will persist across bot restarts.</i>",
            )
        else:
            await send_message(
                message,
                "<b>❌ Upload Failed</b>\n\n"
                f"Failed to process Zotify credentials: {error_msg}",
            )

    except Exception as e:
        if LOGGER:
            LOGGER.error(f"Error handling Zotify credentials upload: {e}")
        await send_message(
            message,
            f"<b>❌ Error</b>\n\nFailed to process Zotify credentials: {e}",
        )
    finally:
        # Clean up temporary file
        if temp_path:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    # Return to zotify auth menu
    await update_buttons(pre_message, "zotify_auth")


@new_task
async def handle_image_upload(_, message, pre_message):
    """Handle the upload of a watermark image from bot settings.

    This function is similar to the thumbnail upload in users_settings.py.
    It stores the image in the database and enables image watermarking.
    """
    user_id = message.from_user.id
    handler_dict[user_id] = False

    # Check if the message contains a photo
    if not message.photo:
        await send_message(message, "Please send an image file for the watermark.")
        return

    # For photos, get the largest photo (last in the list)
    temp_path = await message.download()

    try:
        # Check file size before processing
        file_size = path.getsize(temp_path)
        if file_size > 5 * 1024 * 1024:  # 5MB limit
            # If image is too large, resize it
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")

                # Apply memory limits for PIL operations
                if limit_memory_for_pil:
                    limit_memory_for_pil()

                img = Image.open(temp_path)

                # Get original dimensions
                width, height = img.size

                # Calculate new dimensions while maintaining aspect ratio
                max_size = 1024  # Maximum dimension
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))

                # Resize the image
                img = img.resize((new_width, new_height), Image.LANCZOS)

                # Save the resized image
                img.save(temp_path, optimize=True, quality=85)

                # Get new file size
                file_size = path.getsize(temp_path)

                # Update dimensions for the message
                width, height = new_width, new_height
                img_info = f"Dimensions: {width}x{height} (resized)"
            except Exception:
                await send_message(
                    message,
                    f"❌ Error: Image is too large ({get_readable_file_size(file_size)}) and could not be resized. Please upload a smaller image (< 5MB).",
                )
                return
        else:
            # Get image dimensions for smaller images
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")

                # Apply memory limits for PIL operations
                if limit_memory_for_pil:
                    limit_memory_for_pil()

                img = Image.open(temp_path)
                width, height = img.size
                img_info = f"Dimensions: {width}x{height}"
            except Exception:
                img_info = ""

        # Read the image file into binary data
        async with aiopen(temp_path, "rb") as img_file:
            img_data = await img_file.read()

        # Determine if this is an owner upload
        is_owner = hasattr(Config, "OWNER_ID") and user_id == Config.OWNER_ID

        # Store the image in the database
        if is_owner:
            # If this is an owner upload, update the owner's document
            # This will be used as a fallback for all users
            await database.update_user_doc(
                user_id, "IMAGE_WATERMARK", None, img_data
            )

            # Also update the Config.IMAGE_WATERMARK_PATH to indicate we have an owner watermark
            Config.IMAGE_WATERMARK_PATH = "Added"

            # Update the database config
            await database.update_config({"IMAGE_WATERMARK_PATH": "Added"})

            # Enable image watermark for the owner
            Config.IMAGE_WATERMARK_ENABLED = True

            # Update the database
            await database.update_config({"IMAGE_WATERMARK_ENABLED": True})

            # Create confirmation message for owner
            msg = (
                f"✅ <b>Owner watermark image uploaded successfully!</b>\n\n"
                f"<b>Size:</b> {get_readable_file_size(file_size)}\n"
                f"{img_info}\n\n"
                f"<i>This watermark will be used as a fallback for all users who don't have their own watermark.</i>"
            )
        else:
            # Regular user upload through bot settings is not supported
            # This should not happen, but just in case
            msg = "❌ <b>Error:</b> Only the bot owner can upload watermark images through bot settings."

        # Send confirmation message
        await send_message(message, msg)

    except Exception as e:
        await send_message(message, f"❌ Error uploading watermark image: {e!s}")
    finally:
        # Clean up the temporary file
        if path.exists(temp_path):
            await remove(temp_path)

    # Return to the watermark settings menu
    await update_buttons(pre_message, "mediatools_watermark")


@new_task
async def edit_variable(_, message, pre_message, key):
    handler_dict[message.chat.id] = False
    value = message.text
    if value.lower() == "true":
        value = True
    elif value.lower() == "false":
        value = False
        if key == "INCOMPLETE_TASK_NOTIFIER" and Config.DATABASE_URL:
            await database.trunc_table("tasks")
    elif key == "TORRENT_TIMEOUT":
        await TorrentManager.change_aria2_option("bt-stop-timeout", value)
        value = int(value)
    elif key == "LEECH_SPLIT_SIZE":
        # Always use owner's session for max split size calculation
        max_split_size = (
            TgClient.MAX_SPLIT_SIZE
            if hasattr(Config, "USER_SESSION_STRING") and Config.USER_SESSION_STRING
            else 2097152000
        )
        value = min(int(value), max_split_size)
    elif key == "LEECH_FILENAME_CAPTION":
        # Check if caption exceeds Telegram's limit (1024 characters)
        if len(value) > 1024:
            error_msg = await send_message(
                message,
                "❌ Error: Caption exceeds Telegram's limit of 1024 characters. Please use a shorter caption.",
            )
            # Auto-delete error message after 5 minutes
            create_task(auto_delete_message(error_msg, time=300))
            return
    elif key == "LEECH_FILENAME":
        # No specific validation needed for LEECH_FILENAME
        pass
    elif key in {
        "WATERMARK_SIZE",
        "WATERMARK_THREAD_NUMBER",
        "MERGE_THREAD_NUMBER",
        "MERGE_PRIORITY",
        "MERGE_VIDEO_CRF",
        "MERGE_IMAGE_COLUMNS",
        "MERGE_IMAGE_QUALITY",
        "MERGE_IMAGE_DPI",
        "MERGE_SUBTITLE_FONT_SIZE",
        "MERGE_DOCUMENT_MARGIN",
        "MERGE_AUDIO_CHANNELS",
        "CONVERT_PRIORITY",
        "CONVERT_VIDEO_CRF",
        "CONVERT_AUDIO_CHANNELS",
        "CONVERT_AUDIO_SAMPLING",
        "TASK_MONITOR_INTERVAL",
        "TASK_MONITOR_CONSECUTIVE_CHECKS",
        "TASK_MONITOR_SPEED_THRESHOLD",
        "TASK_MONITOR_ELAPSED_THRESHOLD",
        "TASK_MONITOR_ETA_THRESHOLD",
        "TASK_MONITOR_WAIT_TIME",
        "TASK_MONITOR_COMPLETION_THRESHOLD",
        "TASK_MONITOR_CPU_HIGH",
        "TASK_MONITOR_CPU_LOW",
        "TASK_MONITOR_MEMORY_HIGH",
        "TASK_MONITOR_MEMORY_LOW",
    }:
        try:
            value = int(value)
        except ValueError:
            # Use appropriate default values based on the key
            if key == "WATERMARK_SIZE":
                value = 20
            elif key in {"WATERMARK_THREAD_NUMBER", "MERGE_THREAD_NUMBER"}:
                value = 4
            elif key == "MERGE_PRIORITY":
                value = 1
            elif key == "MERGE_VIDEO_CRF":
                value = DEFAULT_VALUES["MERGE_VIDEO_CRF"]
            elif key == "MERGE_IMAGE_COLUMNS":
                value = DEFAULT_VALUES["MERGE_IMAGE_COLUMNS"]
            elif key == "MERGE_IMAGE_QUALITY":
                value = DEFAULT_VALUES["MERGE_IMAGE_QUALITY"]
            elif key == "MERGE_IMAGE_DPI":
                value = DEFAULT_VALUES["MERGE_IMAGE_DPI"]
            elif key == "MERGE_SUBTITLE_FONT_SIZE":
                value = DEFAULT_VALUES["MERGE_SUBTITLE_FONT_SIZE"]
            elif key == "MERGE_DOCUMENT_MARGIN":
                value = DEFAULT_VALUES["MERGE_DOCUMENT_MARGIN"]
            elif key == "MERGE_AUDIO_CHANNELS":
                value = DEFAULT_VALUES["MERGE_AUDIO_CHANNELS"]
            elif key == "CONVERT_PRIORITY":
                value = 3
            elif key == "CONVERT_VIDEO_CRF":
                value = 23
            elif key == "CONVERT_AUDIO_CHANNELS":
                value = 2
            elif key == "CONVERT_AUDIO_SAMPLING":
                value = 44100
            elif key == "TASK_MONITOR_INTERVAL":
                value = 60
            elif key == "TASK_MONITOR_CONSECUTIVE_CHECKS":
                value = 3
            elif key == "TASK_MONITOR_SPEED_THRESHOLD":
                value = 50
            elif key == "TASK_MONITOR_ELAPSED_THRESHOLD":
                value = 3600
            elif key == "TASK_MONITOR_ETA_THRESHOLD":
                value = 86400
            elif key == "TASK_MONITOR_WAIT_TIME":
                value = 600
            elif key == "TASK_MONITOR_COMPLETION_THRESHOLD":
                value = 14400
            elif key == "TASK_MONITOR_CPU_HIGH":
                value = 90
            elif key == "TASK_MONITOR_CPU_LOW":
                value = 40
            elif key == "TASK_MONITOR_MEMORY_HIGH":
                value = 75
            elif key == "TASK_MONITOR_MEMORY_LOW":
                value = 60
            elif key == "FILE2LINK_BIN_CHANNEL":
                value = 0  # Default to 0 if invalid channel ID
    elif key == "WATERMARK_OPACITY":
        try:
            value = float(value)
            # Ensure opacity is between 0.0 and 1.0
            value = max(0.0, min(1.0, value))
        except ValueError:
            value = 1.0  # Default opacity if invalid input
    elif key == "AUDIO_WATERMARK_VOLUME":
        try:
            value = float(value)
            # Ensure volume is between 0.0 and 1.0
            value = max(0.0, min(1.0, value))
        except ValueError:
            value = 0.3  # Default volume if invalid input
    elif key in {"MERGE_AUDIO_VOLUME", "CONVERT_AUDIO_VOLUME"}:
        try:
            value = float(value)
        except ValueError:
            if key == "MERGE_AUDIO_VOLUME":
                value = DEFAULT_VALUES["MERGE_AUDIO_VOLUME"]
            else:
                value = 1.0  # Default volume if invalid input
    elif key == "WATERMARK_POSITION" and value not in [
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
        "center",
    ]:
        value = "top_left"  # Default position if invalid input
    elif key == "SUBTITLE_WATERMARK_STYLE" and value not in [
        "normal",
        "bold",
        "italic",
        "underline",
    ]:
        value = "normal"  # Default style if invalid input
    elif key == "SUBTITLE_WATERMARK_INTERVAL":
        try:
            value = int(value)
            # Ensure interval is non-negative
            value = max(0, value)
        except ValueError:
            value = 0  # Default interval if invalid input
    elif key == "EXCLUDED_EXTENSIONS":
        fx = value.split()
        excluded_extensions.clear()
        excluded_extensions.extend(["aria2", "!qB"])
        for x in fx:
            x = x.lstrip(".")
            excluded_extensions.append(x.strip().lower())
    elif key == "GDRIVE_ID":
        if drives_names and drives_names[0] == "Main":
            drives_ids[0] = value
        else:
            drives_ids.insert(0, value)
    elif key == "INDEX_URL":
        if drives_names and drives_names[0] == "Main":
            index_urls[0] = value.strip("/")
        else:
            index_urls.insert(0, value.strip("/"))
    elif key == "AUTHORIZED_CHATS":
        aid = value.split()
        auth_chats.clear()
        for id_ in aid:
            chat_id, *thread_ids = id_.split("|")
            chat_id = int(chat_id.strip())
            if thread_ids:
                thread_ids = [int(x.strip()) for x in thread_ids]
                auth_chats[chat_id] = thread_ids
            else:
                auth_chats[chat_id] = []
    elif key == "SUDO_USERS":
        sudo_users.clear()
        aid = value.split()
        for id_ in aid:
            sudo_users.append(int(id_.strip()))
    elif key == "PIL_MEMORY_LIMIT":
        try:
            value = int(value)
        except ValueError:
            value = 2048  # Default to 2GB if invalid input

    elif key == "AUTO_RESTART_ENABLED":
        value = value.lower() in ("true", "1", "yes")
        # Always schedule or cancel auto-restart when this setting is changed
        if schedule_auto_restart:
            create_task(schedule_auto_restart())
    elif key == "AUTO_RESTART_INTERVAL":
        try:
            value = max(1, int(value))  # Minimum 1 hour
            # Schedule the next auto-restart with the new interval if enabled
            if Config.AUTO_RESTART_ENABLED and schedule_auto_restart:
                create_task(schedule_auto_restart())
        except ValueError:
            value = 24  # Default to 24 hours if invalid input
    elif key == "STATUS_UPDATE_INTERVAL":
        try:
            value = max(2, int(value))  # Minimum 2 seconds to prevent FloodWait
        except ValueError:
            value = 3  # Default to 3 seconds if invalid input
    elif key in {"LOGIN_PASS", "DEBRID_LINK_API"}:
            value = str(value)
        elif value.isdigit():
            value = int(value)
        elif (value.startswith("[") and value.endswith("]")) or (
            value.startswith("{") and value.endswith("}")
        ):
            value = eval(value)
    Config.set(key, value)

    # Determine which menu to return to based on the key
    if key.startswith(("WATERMARK_", "AUDIO_WATERMARK_", "SUBTITLE_WATERMARK_")):
        # Check if we're in the watermark text menu
        if pre_message.text and "Watermark Text Settings" in pre_message.text:
            return_menu = "mediatools_watermark_text"
            # Check if we need to return to a specific page in watermark_text
            if pre_message.text and "Page:" in pre_message.text:
                try:
                    page_info = (
                        pre_message.text.split("Page:")[1].strip().split("/")[0]
                    )
                    page_no = int(page_info) - 1
                    # Set the global watermark_text_page variable to ensure we return to the correct page
                    globals()["watermark_text_page"] = page_no
                    # Store the page in handler_dict for backup
                    handler_dict[f"{pre_message.chat.id}_watermark_page"] = page_no

                except (ValueError, IndexError):
                    # Keep the current page if there's an error
                    pass
            else:
                # If no page info in the message, use the global variable
                pass
        else:
            return_menu = "mediatools_watermark"
    elif key.startswith("METADATA_"):
        return_menu = "mediatools_metadata"
    elif key.startswith("CONVERT_"):
        return_menu = "mediatools_convert"
    elif key.startswith("COMPRESSION_"):
        return_menu = "mediatools_compression"
    elif key.startswith("TRIM_"):
        return_menu = "mediatools_trim"
    elif key.startswith("EXTRACT_"):
        return_menu = "mediatools_extract"
    elif key.startswith("REMOVE_"):
        return_menu = "mediatools_remove"
    elif key.startswith("TASK_MONITOR_"):
        return_menu = "taskmonitor"
    elif key.startswith(("MISTRAL_", "DEEPSEEK_")):
        return_menu = "ai"
    elif key.startswith("MERGE_") or key in [
        "CONCAT_DEMUXER_ENABLED",
        "FILTER_COMPLEX_ENABLED",
    ]:
        # Check if the key is from the merge_config menu
        if key.startswith("MERGE_") and any(
            x in key
            for x in [
                "OUTPUT_FORMAT",
                "VIDEO_",
                "AUDIO_",
                "IMAGE_",
                "SUBTITLE_",
                "DOCUMENT_",
                "METADATA_",
            ]
        ):
            # This is a merge_config setting
            return_menu = "mediatools_merge_config"

            # Check if we need to return to a specific page in mediatools_merge_config
            if pre_message.text and "Page:" in pre_message.text:
                try:
                    page_info = (
                        pre_message.text.split("Page:")[1].strip().split("/")[0]
                    )
                    page_no = int(page_info) - 1
                    # Set the global merge_config_page variable to ensure we return to the correct page
                    globals()["merge_config_page"] = page_no
                except (ValueError, IndexError):
                    pass
        elif key in [
            "MERGE_ENABLED",
            "MERGE_PRIORITY",
            "MERGE_THREADING",
            "MERGE_THREAD_NUMBER",
            "MERGE_REMOVE_ORIGINAL",
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
        ]:
            # These are from the main merge menu
            return_menu = "mediatools_merge"

            # Check if we need to return to a specific page in mediatools_merge
            if pre_message.text and "Page:" in pre_message.text:
                try:
                    page_info = (
                        pre_message.text.split("Page:")[1].strip().split("/")[0]
                    )
                    page_no = int(page_info) - 1
                    # Set the global merge_page variable to ensure we return to the correct page
                    globals()["merge_page"] = page_no
                except (ValueError, IndexError):
                    pass
        else:
            # Default to merge menu for any other merge settings
            return_menu = "mediatools_merge"

            # Check if we need to return to a specific page in mediatools_merge
            if pre_message.text and "Page:" in pre_message.text:
                try:
                    page_info = (
                        pre_message.text.split("Page:")[1].strip().split("/")[0]
                    )
                    page_no = int(page_info) - 1
                    # Set the global merge_page variable to ensure we return to the correct page
                    globals()["merge_page"] = page_no
                except (ValueError, IndexError):
                    pass
    elif key == "MEDIA_TOOLS_PRIORITY":
        return_menu = "mediatools"
    elif key.startswith("STREAMRIP_"):
        # For streamrip settings, determine which submenu to return to based on the key
        if key in [
            "STREAMRIP_ENABLED",
            "STREAMRIP_CONCURRENT_DOWNLOADS",
            "STREAMRIP_MAX_SEARCH_RESULTS",
            "STREAMRIP_ENABLE_DATABASE",
            "STREAMRIP_AUTO_CONVERT",
        ]:
            return_menu = "streamrip_general"
        elif key in [
            "STREAMRIP_DEFAULT_QUALITY",
            "STREAMRIP_FALLBACK_QUALITY",
            "STREAMRIP_DEFAULT_CODEC",
            "STREAMRIP_SUPPORTED_CODECS",
            "STREAMRIP_QUALITY_FALLBACK_ENABLED",
        ]:
            return_menu = "streamrip_quality"
        elif (
            (
                key.endswith("_ENABLED")
                and any(
                    platform in key
                    for platform in ["QOBUZ", "TIDAL", "DEEZER", "SOUNDCLOUD"]
                )
            )
            or key.endswith(
                (
                    "_EMAIL",
                    "_PASSWORD",
                    "_ARL",
                    "_CLIENT_ID",
                    "_ACCESS_TOKEN",
                    "_REFRESH_TOKEN",
                    "_USER_ID",
                    "_COUNTRY_CODE",
                )
            )
            or key
            in [
                "STREAMRIP_QOBUZ_USE_AUTH_TOKEN",
                "STREAMRIP_QOBUZ_APP_ID",
                "STREAMRIP_QOBUZ_QUALITY",
                "STREAMRIP_TIDAL_QUALITY",
                "STREAMRIP_DEEZER_QUALITY",
                "STREAMRIP_SOUNDCLOUD_QUALITY",
            ]
        ):
            return_menu = "streamrip_credentials"
        elif key in [
            "STREAMRIP_MAX_CONNECTIONS",
            "STREAMRIP_REQUESTS_PER_MINUTE",
            "STREAMRIP_SOURCE_SUBDIRECTORIES",
            "STREAMRIP_DISC_SUBDIRECTORIES",
            "STREAMRIP_CONCURRENCY",
            "STREAMRIP_VERIFY_SSL",
        ]:
            return_menu = "streamrip_download"
        elif key in [
            "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS",
            "STREAMRIP_QOBUZ_FILTERS_EXTRAS",
            "STREAMRIP_QOBUZ_FILTERS_REPEATS",
            "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS",
            "STREAMRIP_QOBUZ_FILTERS_FEATURES",
            "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS",
            "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER",
            "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS",
            "STREAMRIP_TIDAL_TOKEN_EXPIRY",
            "STREAMRIP_DEEZER_USE_DEEZLOADER",
            "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS",
            "STREAMRIP_SOUNDCLOUD_APP_VERSION",
            "STREAMRIP_YOUTUBE_QUALITY",
            "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS",
            "STREAMRIP_YOUTUBE_VIDEO_FOLDER",
            "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER",
            "STREAMRIP_LASTFM_ENABLED",
            "STREAMRIP_LASTFM_SOURCE",
            "STREAMRIP_LASTFM_FALLBACK_SOURCE",
        ]:
            return_menu = "streamrip_platforms"
        elif key in [
            "STREAMRIP_DATABASE_DOWNLOADS_ENABLED",
            "STREAMRIP_DATABASE_DOWNLOADS_PATH",
            "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED",
            "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
        ]:
            return_menu = "streamrip_database"
        elif key in [
            "STREAMRIP_CONVERSION_ENABLED",
            "STREAMRIP_CONVERSION_CODEC",
            "STREAMRIP_CONVERSION_SAMPLING_RATE",
            "STREAMRIP_CONVERSION_BIT_DEPTH",
            "STREAMRIP_CONVERSION_LOSSY_BITRATE",
        ]:
            return_menu = "streamrip_conversion"
        elif key in [
            "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM",
            "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS",
            "STREAMRIP_METADATA_EXCLUDE",
        ]:
            return_menu = "streamrip_metadata"
        elif key in [
            "STREAMRIP_CLI_TEXT_OUTPUT",
            "STREAMRIP_CLI_PROGRESS_BARS",
            "STREAMRIP_CLI_MAX_SEARCH_RESULTS",
            "STREAMRIP_MISC_CHECK_FOR_UPDATES",
            "STREAMRIP_MISC_VERSION",
        ]:
            return_menu = "streamrip_cli"
        elif key in [
            "STREAMRIP_FILENAME_TEMPLATE",
            "STREAMRIP_FOLDER_TEMPLATE",
            "STREAMRIP_EMBED_COVER_ART",
            "STREAMRIP_SAVE_COVER_ART",
            "STREAMRIP_COVER_ART_SIZE",
            "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH",
            "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH",
            "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER",
            "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
            "STREAMRIP_FILEPATHS_TRACK_FORMAT",
            "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS",
            "STREAMRIP_FILEPATHS_TRUNCATE_TO",
        ]:
            return_menu = "streamrip_advanced"
        else:
            # For any other streamrip settings, default to main streamrip menu
            return_menu = "streamrip"
    else:
        return_menu = "var"

    # Get the current state before updating the UI
    current_state = globals()["state"]
    # Set the state back to what it was
    globals()["state"] = current_state

    # Handle special cases for pages
    if return_menu == "mediatools_merge" and "merge_page" in globals():
        await update_buttons(pre_message, return_menu, page=globals()["merge_page"])
    elif return_menu == "mediatools_merge_config":
        # Redirect to mediatools_merge with the appropriate page
        if pre_message.text and "Page:" in pre_message.text:
            try:
                page_info = pre_message.text.split("Page:")[1].strip().split("/")[0]
                page_no = int(page_info) - 1
                # Set both global page variables to ensure we return to the correct page
                globals()["merge_page"] = page_no
                globals()["merge_config_page"] = page_no
                await update_buttons(pre_message, "mediatools_merge", page=page_no)
            except (ValueError, IndexError):
                # If there's an error parsing the page number, use the stored page
                await update_buttons(
                    pre_message, "mediatools_merge", page=globals()["merge_page"]
                )
        else:
            # Use the stored page
            await update_buttons(
                pre_message, "mediatools_merge", page=globals()["merge_page"]
            )
    elif return_menu == "mediatools_watermark_text":
        # Return to the watermark text menu with the correct page
        # First check if we have a stored page in handler_dict
        stored_page = handler_dict.get(f"{pre_message.chat.id}_watermark_page")
        if stored_page is not None:
            await update_buttons(pre_message, return_menu, page=stored_page)
        # Then check if we have a global page
        elif "watermark_text_page" in globals():
            await update_buttons(
                pre_message, return_menu, page=globals()["watermark_text_page"]
            )
        # If all else fails, use page 0
        else:
            await update_buttons(pre_message, return_menu, page=0)
    else:
        await update_buttons(pre_message, return_menu)

    await delete_message(message)
    await database.update_config({key: value})

    if key in ["QUEUE_ALL", "QUEUE_DOWNLOAD", "QUEUE_UPLOAD"]:
        await start_from_queued()
    elif key == "BASE_URL_PORT":
        # Kill any running web server
        with contextlib.suppress(Exception):
            await (
                await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
            ).wait()

        # Only start web server if port is not 0
        if value != 0:
            await create_subprocess_shell(
                f"gunicorn -k uvicorn.workers.UvicornWorker -w 1 web.wserver:app --bind 0.0.0.0:{value}",
            )
        else:
            # Double-check to make sure no web server is running
            try:
                # Use pgrep to check if any gunicorn processes are still running
                process = await create_subprocess_exec(
                    "pgrep", "-f", "gunicorn", stdout=-1
                )
                stdout, _ = await process.communicate()
                if stdout:
                    await (
                        await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
                    ).wait()
            except Exception:
                pass

    elif key in [
        "RCLONE_SERVE_URL",
        "RCLONE_SERVE_PORT",
        "RCLONE_SERVE_USER",
        "RCLONE_SERVE_PASS",
    ]:
        await rclone_serve_booter()
    elif key in ["JD_EMAIL", "JD_PASS"]:
        await jdownloader.boot()
    elif key == "RSS_DELAY":
        add_job()
    elif key == "USET_SERVERS":
        for s in value:
            await sabnzbd_client.set_special_config("servers", s)


@new_task
async def edit_aria(_, message, pre_message, key):
    handler_dict[message.chat.id] = False
    value = message.text
    if key == "newkey":
        key, value = [x.strip() for x in value.split(":", 1)]
    elif value.lower() == "true":
        value = "true"
    elif value.lower() == "false":
        value = "false"
    await TorrentManager.change_aria2_option(key, value)

    # Get the current state before updating the UI
    current_state = globals()["state"]
    # Set the state back to what it was
    globals()["state"] = current_state
    await update_buttons(pre_message, "aria")

    await delete_message(message)
    await database.update_aria2(key, value)


@new_task
async def edit_qbit(_, message, pre_message, key):
    handler_dict[message.chat.id] = False
    value = message.text
    if value.lower() == "true":
        value = True
    elif value.lower() == "false":
        value = False
    elif key == "max_ratio":
        value = float(value)
    elif value.isdigit():
        value = int(value)
    await TorrentManager.qbittorrent.app.set_preferences({key: value})
    qbit_options[key] = value

    # Get the current state before updating the UI
    current_state = globals()["state"]
    # Set the state back to what it was
    globals()["state"] = current_state
    await update_buttons(pre_message, "qbit")

    await delete_message(message)
    await database.update_qbittorrent(key, value)


@new_task
async def edit_nzb(_, message, pre_message, key):
    handler_dict[message.chat.id] = False
    value = message.text
    if value.isdigit():
        value = int(value)
    elif value.startswith("[") and value.endswith("]"):
        try:
            value = ",".join(eval(value))
        except Exception as e:
            LOGGER.error(e)
            await update_buttons(pre_message, "nzb")
            return
    res = await sabnzbd_client.set_config("misc", key, value)
    nzb_options[key] = res["config"]["misc"][key]
    await update_buttons(pre_message, "nzb")
    await delete_message(message)
    await database.update_nzb_config()


@new_task
async def edit_nzb_server(_, message, pre_message, key, index=0):
    handler_dict[message.chat.id] = False
    value = message.text
    if key == "newser":
        if value.startswith("{") and value.endswith("}"):
            try:
                value = eval(value)
            except Exception:
                await send_message(message, "Invalid dict format!")
                await update_buttons(pre_message, "nzbserver")
                return
            res = await sabnzbd_client.add_server(value)
            if not res["config"]["servers"][0]["host"]:
                await send_message(message, "Invalid server!")
                await update_buttons(pre_message, "nzbserver")
                return
            Config.USENET_SERVERS.append(value)
            await update_buttons(pre_message, "nzbserver")
        else:
            await send_message(message, "Invalid dict format!")
            await update_buttons(pre_message, "nzbserver")
            return
    else:
        if value.isdigit():
            value = int(value)
        res = await sabnzbd_client.add_server(
            {"name": Config.USENET_SERVERS[index]["name"], key: value},
        )
        if res["config"]["servers"][0][key] == "":
            await send_message(message, "Invalid value")
            return
        Config.USENET_SERVERS[index][key] = value
        await update_buttons(pre_message, f"nzbser{index}")
    await delete_message(message)
    await database.update_config({"USENET_SERVERS": Config.USENET_SERVERS})


async def sync_jdownloader():
    async with jd_listener_lock:
        if not Config.DATABASE_URL or not jdownloader.is_connected:
            return
        await jdownloader.device.system.exit_jd()
    if await aiopath.exists("cfg.zip"):
        await remove("cfg.zip")
    await (
        await create_subprocess_exec("7z", "a", "cfg.zip", "/JDownloader/cfg")
    ).wait()
    await database.update_private_file("cfg.zip")


@new_task
async def handle_watermark_image_upload(_, message):
    """Handle the upload of a watermark image"""
    user_id = message.from_user.id
    handler_dict[user_id] = False

    # Check if this upload was initiated from bot_settings
    from_bot_settings = handler_dict.get(f"{user_id}_from_bot_settings", False)

    # Get the original message for returning to the menu later
    original_message = handler_dict.get(f"{user_id}_original_message", None)

    # Create a temporary directory if it doesn't exist
    temp_dir = f"{getcwd()}/temp/watermarks"
    try:
        await makedirs(temp_dir, exist_ok=True)
    except Exception:
        # Fallback to current directory if temp dir creation fails
        temp_dir = getcwd()

    # Create a temporary file to store the image with a unique name
    temp_path = f"{temp_dir}/temp_watermark_{user_id}_{int(time())}.png"

    try:
        # Download the image
        if message.photo:
            # For photos sent directly
            await message.download(file_name=temp_path)
            file_size = await aiopath.getsize(temp_path)
            img_info = ""

            # Check if the image is too large
            if file_size > 5 * 1024 * 1024:  # 5MB limit
                # If image is too large, resize it
                try:
                    # Try to use PIL if available
                    try:
                        if not PIL_AVAILABLE:
                            raise ImportError("PIL not available")
                    except ImportError:
                        error_msg = await send_message(
                            message,
                            "❌ Error: PIL/Pillow library is not installed. Cannot process image.",
                        )
                        # Auto-delete error message after 5 minutes
                        _ = create_task(auto_delete_message(error_msg, time=300))
                        # Delete the uploaded image message
                        await delete_message(message)
                        return

                    # Apply memory limits for PIL operations
                    limit_memory_for_pil()

                    img = Image.open(temp_path)
                    width, height = img.size

                    # Calculate new dimensions to keep aspect ratio
                    max_size = 500
                    if width > height:
                        new_width = max_size
                        new_height = int(height * (max_size / width))
                    else:
                        new_height = max_size
                        new_width = int(width * (max_size / height))

                    # Resize the image
                    img = img.resize((new_width, new_height), Image.LANCZOS)
                    img.save(temp_path, optimize=True)

                    # Update dimensions for the message
                    width, height = new_width, new_height
                    img_info = f"Dimensions: {width}x{height} (resized)"
                except Exception:
                    error_msg = await send_message(
                        message,
                        f"❌ Error: Image is too large ({get_readable_file_size(file_size)}) and could not be resized. Please upload a smaller image (< 5MB).",
                    )
                    # Auto-delete error message after 5 minutes
                    _ = create_task(auto_delete_message(error_msg, time=300))
                    # Delete the uploaded image message
                    await delete_message(message)
                    return
            else:
                # Get image dimensions for smaller images
                try:
                    # Try to use PIL if available
                    if PIL_AVAILABLE:
                        img = Image.open(temp_path)
                        width, height = img.size
                        img_info = f"Dimensions: {width}x{height}"
                except Exception:
                    img_info = ""

            # Read the image file into binary data
            async with aiofiles.open(temp_path, "rb") as f:
                image_data = await f.read()

            # Determine if this is an owner upload
            is_owner = hasattr(Config, "OWNER_ID") and user_id == Config.OWNER_ID

            # Store the image in the database
            if is_owner:
                # If this is an owner upload, update the owner's document
                # This will be used as a fallback for all users
                await database.update_user_doc(
                    user_id, "IMAGE_WATERMARK", None, image_data
                )

                # Also update the Config.IMAGE_WATERMARK_PATH to indicate we have an owner watermark
                Config.IMAGE_WATERMARK_PATH = "Added"

                # Update the database config
                await database.update_config({"IMAGE_WATERMARK_PATH": "Added"})

                # Enable image watermark for the owner
                Config.IMAGE_WATERMARK_ENABLED = True

                # Update the database
                await database.update_config({"IMAGE_WATERMARK_ENABLED": True})

                # Create confirmation message for owner
                file_size_str = get_readable_file_size(len(image_data))
                msg = f"✅ <b>Owner watermark image uploaded successfully!</b>\n\n<b>Size:</b> {file_size_str}\n{img_info}\n\n<i>This watermark will be used as a fallback for all users who don't have their own watermark.</i>"
            else:
                # Regular user upload
                await database.update_user_doc(
                    user_id, "IMAGE_WATERMARK", None, image_data
                )

                # Enable image watermark for the user
                # Set user data in the user_data dictionary first
                update_user_ldata(user_id, "IMAGE_WATERMARK_ENABLED", True)
                update_user_ldata(user_id, "IMAGE_WATERMARK_PATH", "Added")
                # Then update the database
                await database.update_user_data(user_id)

                # Create confirmation message for user
                file_size_str = get_readable_file_size(len(image_data))
                msg = f"✅ <b>Watermark image uploaded successfully!</b>\n\n<b>Size:</b> {file_size_str}\n{img_info}\n\n<i>Your watermark will be used for all your tasks with image watermarking enabled.</i>"

            # Send a simple confirmation message that will auto-delete
            success_msg = await send_message(message, msg)

            # Auto-delete success message after 5 minutes
            _ = create_task(auto_delete_message(success_msg, time=300))

            # Delete the uploaded image message immediately
            await delete_message(message)

            # Return to the watermark settings menu
            if from_bot_settings and original_message:
                # Use the original message stored in handler_dict
                await update_buttons(original_message, "mediatools_watermark")
            elif message.reply_to_message:
                # Fallback to reply_to_message if available
                await update_buttons(
                    message.reply_to_message, "mediatools_watermark"
                )

        elif doc := message.document:
            # For document uploads (files)
            mime_type = doc.mime_type
            if not mime_type or not mime_type.startswith("image/"):
                error_msg = await send_message(
                    message,
                    "❌ Error: Please upload an image file (JPEG, PNG, etc.)",
                )
                # Auto-delete error message after 5 minutes
                _ = create_task(auto_delete_message(error_msg, time=300))
                # Delete the uploaded document message
                await delete_message(message)
                return

            # Download the document
            await message.download(file_name=temp_path)
            file_size = await aiopath.getsize(temp_path)

            # Check if the file is too large
            if file_size > 5 * 1024 * 1024:  # 5MB limit
                error_msg = await send_message(
                    message,
                    f"❌ Error: Image is too large ({get_readable_file_size(file_size)}). Please upload a smaller image (< 5MB).",
                )
                # Auto-delete error message after 5 minutes
                _ = create_task(auto_delete_message(error_msg, time=300))
                # Delete the uploaded document message
                await delete_message(message)
                return

            # Get image dimensions
            try:
                # Try to use PIL if available
                if PIL_AVAILABLE and limit_memory_for_pil:
                    # Apply memory limits for PIL operations
                    limit_memory_for_pil()

                    img = Image.open(temp_path)
                    width, height = img.size
                    img_info = f"Dimensions: {width}x{height}"
            except Exception:
                img_info = ""

            # Read the image file into binary data
            async with aiofiles.open(temp_path, "rb") as f:
                image_data = await f.read()

            # Determine if this is an owner upload
            is_owner = hasattr(Config, "OWNER_ID") and user_id == Config.OWNER_ID

            # Store the image in the database
            if is_owner:
                # If this is an owner upload, update the owner's document
                # This will be used as a fallback for all users
                await database.update_user_doc(
                    user_id, "IMAGE_WATERMARK", None, image_data
                )

                # Also update the Config.IMAGE_WATERMARK_PATH to indicate we have an owner watermark
                Config.IMAGE_WATERMARK_PATH = "Added"

                # Update the database config
                await database.update_config({"IMAGE_WATERMARK_PATH": "Added"})

                # Enable image watermark for the owner
                Config.IMAGE_WATERMARK_ENABLED = True

                # Update the database
                await database.update_config({"IMAGE_WATERMARK_ENABLED": True})

                # Create confirmation message for owner
                file_size_str = get_readable_file_size(len(image_data))
                msg = f"✅ <b>Owner watermark image uploaded successfully!</b>\n\n<b>Size:</b> {file_size_str}\n{img_info}\n\n<i>This watermark will be used as a fallback for all users who don't have their own watermark.</i>"
            else:
                # Regular user upload
                await database.update_user_doc(
                    user_id, "IMAGE_WATERMARK", None, image_data
                )

                # Enable image watermark for the user
                Config.IMAGE_WATERMARK_ENABLED = True
                await database.update_config({"IMAGE_WATERMARK_ENABLED": True})

                # Create confirmation message for user
                file_size_str = get_readable_file_size(len(image_data))
                msg = f"✅ <b>Watermark image uploaded successfully!</b>\n\n<b>Size:</b> {file_size_str}\n{img_info}\n\n<i>Your watermark will be used for all your tasks with image watermarking enabled.</i>"

            # Send a simple confirmation message that will auto-delete
            success_msg = await send_message(message, msg)

            # Auto-delete success message after 5 minutes
            _ = create_task(auto_delete_message(success_msg, time=300))

            # Delete the uploaded image message immediately
            await delete_message(message)

            # Return to the watermark settings menu
            if from_bot_settings and original_message:
                # Use the original message stored in handler_dict
                await update_buttons(original_message, "mediatools_watermark")
            elif message.reply_to_message:
                # Fallback to reply_to_message if available
                await update_buttons(
                    message.reply_to_message, "mediatools_watermark"
                )

    except Exception as e:
        error_msg = await send_message(
            message, f"❌ Error uploading watermark image: {e}"
        )
        # Auto-delete error message after 5 minutes
        _ = create_task(auto_delete_message(error_msg, time=300))
        # Delete the uploaded image message if it exists
        await delete_message(message)

        # Return to the watermark settings menu after error
        if from_bot_settings and original_message:
            # Use the original message stored in handler_dict
            await update_buttons(original_message, "mediatools_watermark")
        elif message.reply_to_message:
            # Fallback to reply_to_message if available
            await update_buttons(message.reply_to_message, "mediatools_watermark")
    finally:
        # Clean up the temporary file
        try:
            if await aiopath.exists(temp_path):
                await remove(temp_path)
        except Exception:
            pass

        # Clean up handler_dict entries
        if f"{user_id}_from_bot_settings" in handler_dict:
            del handler_dict[f"{user_id}_from_bot_settings"]
        if f"{user_id}_original_message" in handler_dict:
            del handler_dict[f"{user_id}_original_message"]


async def update_private_file(_, message, pre_message):
    handler_dict[message.chat.id] = False
    if not message.media and (file_name := message.text):
        if await aiopath.isfile(file_name) and file_name != "config.py":
            await remove(file_name)
        if file_name == "accounts.zip":
            if await aiopath.exists("accounts"):
                await rmtree("accounts", ignore_errors=True)
            if await aiopath.exists("rclone_sa"):
                await rmtree("rclone_sa", ignore_errors=True)
            Config.USE_SERVICE_ACCOUNTS = False
            await database.update_config({"USE_SERVICE_ACCOUNTS": False})
        elif file_name in [".netrc", "netrc"]:
            await (await create_subprocess_exec("touch", ".netrc")).wait()
            await (await create_subprocess_exec("chmod", "600", ".netrc")).wait()
            await (
                await create_subprocess_exec("cp", ".netrc", "/root/.netrc")
            ).wait()
        elif file_name == "streamrip_config.toml":
            # Handle streamrip config deletion - use same logic as dedicated streamrip config reset
            try:
                from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                    streamrip_config,
                )

                success = await streamrip_config.delete_custom_config_from_db()

                if success:
                    # Reinitialize streamrip config to use default settings
                    await streamrip_config.initialize()
                    LOGGER.info(
                        "Streamrip custom config deleted, reverted to default"
                    )
                else:
                    LOGGER.error("Failed to delete streamrip config from database")

            except Exception as e:
                LOGGER.error(f"Error handling streamrip config deletion: {e}")
        elif file_name == "zotify_credentials.json":
            # Handle zotify credentials deletion - use same logic as dedicated clear credentials
            try:
                from pathlib import Path

                # Get user_id (use owner ID for private files)
                user_id = getattr(Config, "OWNER_ID", 0)
                credentials_cleared = False

                # Clear credentials from database
                if database.db is not None:
                    try:
                        result = await database.db.users.update_one(
                            {"_id": user_id},
                            {"$unset": {"ZOTIFY_CREDENTIALS": ""}},
                        )
                        if result.modified_count > 0:
                            credentials_cleared = True
                    except Exception as e:
                        LOGGER.error(
                            f"Error clearing Zotify credentials from database: {e}"
                        )

                # Clear credentials file
                credentials_path = (
                    Config.ZOTIFY_CREDENTIALS_PATH or "./zotify_credentials.json"
                )
                creds_file = Path(credentials_path)

                if creds_file.exists():
                    creds_file.unlink()
                    credentials_cleared = True

                if credentials_cleared:
                    LOGGER.info(
                        "Zotify credentials deleted successfully (database and file)"
                    )
                else:
                    LOGGER.info("No Zotify credentials found to delete")

            except Exception as e:
                LOGGER.error(f"Error handling Zotify credentials deletion: {e}")
        await delete_message(message)
    elif doc := message.document:
        file_name = doc.file_name
        fpath = f"{getcwd()}/{file_name}"
        if await aiopath.exists(fpath):
            await remove(fpath)
        await message.download(file_name=fpath)
        if file_name == "accounts.zip":
            if await aiopath.exists("accounts"):
                await rmtree("accounts", ignore_errors=True)
            if await aiopath.exists("rclone_sa"):
                await rmtree("rclone_sa", ignore_errors=True)
            await (
                await create_subprocess_exec(
                    "7z",
                    "x",
                    "-o.",
                    "-aoa",
                    "accounts.zip",
                    "accounts/*.json",
                )
            ).wait()
            await (
                await create_subprocess_exec("chmod", "-R", "777", "accounts")
            ).wait()
        elif file_name == "list_drives.txt":
            drives_ids.clear()
            drives_names.clear()
            index_urls.clear()
            if Config.GDRIVE_ID:
                drives_names.append("Main")
                drives_ids.append(Config.GDRIVE_ID)
                index_urls.append(Config.INDEX_URL)
            async with aiopen("list_drives.txt", "r+") as f:
                lines = await f.readlines()
                for line in lines:
                    temp = line.strip().split()
                    drives_ids.append(temp[1])
                    drives_names.append(temp[0].replace("_", " "))
                    if len(temp) > 2:
                        index_urls.append(temp[2].strip("/"))
                    else:
                        index_urls.append("")
        elif file_name in [".netrc", "netrc"]:
            if file_name == "netrc":
                await rename("netrc", ".netrc")
                file_name = ".netrc"
            await (await create_subprocess_exec("chmod", "600", ".netrc")).wait()
            await (
                await create_subprocess_exec("cp", ".netrc", "/root/.netrc")
            ).wait()
        elif file_name == "config.py":
            await load_config()
        elif file_name == "streamrip_config.toml":
            # Handle streamrip config upload - use same logic as dedicated streamrip config upload
            try:
                # Validate file extension (should already be .toml but double-check)
                if not file_name.lower().endswith(".toml"):
                    LOGGER.error("Invalid streamrip config file extension")
                    if await aiopath.exists(file_name):
                        await remove(file_name)
                    return

                # Check file size (5MB limit)
                if await aiopath.exists(file_name):
                    file_size = await aiopath.getsize(file_name)
                    if file_size > 5 * 1024 * 1024:
                        LOGGER.error("Streamrip config file too large (>5MB)")
                        await remove(file_name)
                        return

                # Read the uploaded config file
                async with aiopen(file_name, encoding="utf-8") as f:
                    config_content = await f.read()

                # Use the unified processing function
                success, error_msg = await _process_streamrip_config_upload(
                    config_content, file_name
                )

                if not success:
                    LOGGER.error(f"Streamrip config upload failed: {error_msg}")

                # Clean up the temporary file
                if await aiopath.exists(file_name):
                    await remove(file_name)

            except Exception as e:
                LOGGER.error(f"Error handling streamrip config upload: {e}")
                if await aiopath.exists(file_name):
                    await remove(file_name)
        elif file_name == "zotify_credentials.json":
            # Handle zotify credentials upload - use same logic as dedicated zotify credentials upload
            try:
                # Validate file extension (should already be .json but double-check)
                if not file_name.lower().endswith(".json"):
                    LOGGER.error("Invalid zotify credentials file extension")
                    if await aiopath.exists(file_name):
                        await remove(file_name)
                    return

                # Check file size (5MB limit)
                if await aiopath.exists(file_name):
                    file_size = await aiopath.getsize(file_name)
                    if file_size > 5 * 1024 * 1024:
                        LOGGER.error("Zotify credentials file too large (>5MB)")
                        await remove(file_name)
                        return

                # Read the uploaded credentials file
                async with aiopen(file_name, encoding="utf-8") as f:
                    credentials_content = await f.read()

                # Get user_id from the message context (use owner ID for private files)
                user_id = getattr(Config, "OWNER_ID", 0)

                # Use the unified processing function
                success, error_msg = await _process_zotify_credentials_upload(
                    credentials_content, user_id, file_name
                )

                if not success:
                    LOGGER.error(f"Zotify credentials upload failed: {error_msg}")

                # Clean up the temporary file
                if await aiopath.exists(file_name):
                    await remove(file_name)

            except Exception as e:
                LOGGER.error(f"Error handling Zotify credentials upload: {e}")
                if await aiopath.exists(file_name):
                    await remove(file_name)
        await delete_message(message)
    if file_name == "rclone.conf":
        await rclone_serve_booter()

    # Get the current state before updating the UI
    current_state = globals()["state"]
    # Set the state back to what it was
    globals()["state"] = current_state
    await update_buttons(pre_message)

    await database.update_private_file(file_name)


async def event_handler(client, query, pfunc, rfunc, document=False, photo=False):
    chat_id = query.message.chat.id
    handler_dict[chat_id] = True
    start_time = time()  # pylint: disable=unused-argument
    pre_message = query.message  # Store the pre_message for handlers that need it

    async def event_filter(_, *args):
        event = args[1]  # The event is the second argument
        user = event.from_user or event.sender_chat
        query_user = query.from_user

        # Check if both user and query_user are not None before comparing IDs
        if user is None or query_user is None:
            return False

        # Check for the appropriate message type based on parameters
        if photo:
            mtype = event.photo
        elif document:
            mtype = event.document
        else:
            mtype = event.text

        return bool(user.id == query_user.id and event.chat.id == chat_id and mtype)

    # Create a wrapper function that passes the pre_message as the third parameter
    async def pfunc_wrapper(client, message):
        # Check if the function expects 3 parameters (client, message, pre_message)
        from functools import partial

        # Handle partial functions specially
        if isinstance(pfunc, partial):
            # For partial functions, check if pre_message is already bound
            if "pre_message" in pfunc.keywords:
                # pre_message is already bound as keyword argument, just call with 2 params
                await pfunc(client, message)
            else:
                # pre_message not bound, check the original function signature
                original_func = pfunc.func
                sig = inspect.signature(original_func)
                param_names = list(sig.parameters.keys())

                if len(param_names) >= 3 and param_names[2] == "pre_message":
                    # Original function expects pre_message as third parameter
                    await pfunc(client, message, pre_message)
                else:
                    # Original function doesn't expect pre_message as third parameter
                    await pfunc(client, message)
        else:
            # Regular function (not partial)
            sig = inspect.signature(pfunc)
            param_names = list(sig.parameters.keys())

            if len(sig.parameters) >= 3:
                # Check if the third parameter is named 'pre_message'
                if len(param_names) >= 3 and param_names[2] == "pre_message":
                    # Function expects pre_message as third parameter
                    await pfunc(client, message, pre_message)
                else:
                    # Function has 3+ parameters but third is not 'pre_message'
                    # This shouldn't happen with current handlers, but fallback to 2 params
                    await pfunc(client, message)
            else:
                # Function only expects client and message
                await pfunc(client, message)

    handler = client.add_handler(
        MessageHandler(pfunc_wrapper, filters=create(event_filter)),
        group=-1,
    )
    while handler_dict[chat_id]:
        await sleep(0.5)
        if time() - start_time > 60:
            handler_dict[chat_id] = False
            await rfunc()

    # Safely remove the handler
    try:
        if isinstance(handler, tuple) and len(handler) >= 2:
            client.remove_handler(handler[0], handler[1])
        else:
            # Fallback: try to remove with just the handler
            client.remove_handler(handler)
    except Exception as e:
        from bot import LOGGER

        LOGGER.error(f"Error removing handler: {e}")


@new_task
async def edit_bot_settings(client, query):
    # Import database at the beginning to ensure it's available throughout the function
    from bot.helper.ext_utils.db_handler import database

    data = query.data.split()
    message = query.message
    user_id = message.chat.id

    # Safety check for callback data
    if len(data) < 2:
        from bot import LOGGER

        LOGGER.error(f"Invalid callback data: {query.data}")
        await query.answer("Invalid callback data", show_alert=True)
        return

    # Helper function to safely answer queries
    async def safe_answer(text=None, show_alert=False):
        try:
            await query.answer(text, show_alert=show_alert)
        except Exception:
            # Continue execution even if query.answer() fails
            pass

    handler_dict[user_id] = False
    if data[1] == "close":
        await safe_answer()
        # Only delete the menu message, not the command that triggered it
        await delete_message(message)
    elif data[1] == "back":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        globals()["start"] = 0

        # Determine which menu to return to based on the current message content
        return_menu = None

        # Check if we're in a main menu (Config Variables, Task Monitor, Private Files, qBittorrent, Aria2c, Sabnzbd, Media Tools, AI Settings, Streamrip Settings)
        if message.text:
            if any(
                x in message.text
                for x in [
                    "Config Variables",
                    "Task Monitoring Settings",
                    "Private Files Management",
                    "qBittorrent Options",
                    "Aria2c Options",
                    "Sabnzbd Options",
                    "Media Tools Settings",
                    "AI Settings",
                    "Bot Settings",
                    "Streamrip Settings",
                    "Zotify Settings",
                    "DDL (Direct Download Link) Settings",
                    "YouTube API Settings",
                    "MEGA Settings",
                    "Operations Settings",
                ]
            ):
                # If we're in a main menu, return to the main settings menu
                return_menu = None
            # Check if we're editing a Task Monitor setting
            elif (
                "Send a valid value for" in message.text
                and "TASK_MONITOR_" in message.text
            ):
                return_menu = "taskmonitor"
            # Check for Streamrip submenu detection
            elif any(
                x in message.text
                for x in [
                    "Streamrip General Settings",
                    "Streamrip Quality & Codec Settings",
                    "Streamrip Platform Credentials",
                    "Streamrip Download Settings",
                    "Streamrip Platform Settings",
                    "Streamrip Database Settings",
                    "Streamrip Conversion Settings",
                    "Streamrip CLI Settings",
                    "Streamrip Advanced Settings",
                    "Streamrip Config File Management",
                ]
            ):
                return_menu = "streamrip"
            # Check for Zotify submenu detection
            elif any(
                x in message.text
                for x in [
                    "Zotify General Settings",
                    "Zotify Quality & Format Settings",
                    "Zotify Authentication Settings",
                    "Zotify Library Paths",
                    "Zotify Output Templates",
                    "Zotify Download Settings",
                    "Zotify Metadata Settings",
                    "Zotify Advanced Settings",
                ]
            ):
                return_menu = "zotify"
            # Check for DDL submenu detection
            elif any(
                x in message.text
                for x in [
                    "DDL General Settings",
                    "Gofile Settings",
                    "Streamtape Settings",
                    "DevUploads Settings",
                    "MediaFire Settings",
                ]
            ):
                return_menu = "ddl"
            # Check for YouTube submenu detection
            elif any(
                x in message.text
                for x in [
                    "YouTube General Settings",
                    "YouTube Upload Settings",
                    "YouTube Authentication Settings",
                ]
            ):
                return_menu = "youtube"
            # Check for MEGA submenu detection
            elif any(
                x in message.text
                for x in [
                    "MEGA General Settings",
                    "MEGA Upload Settings",
                    "MEGA Clone Settings",
                    "MEGA Security Settings",
                ]
            ):
                return_menu = "mega"
            # Check for AI submenu detection
            elif any(
                x in message.text
                for x in [
                    "AI Model Selection",
                    "AI Provider Settings",
                    "AI Plugin Settings",
                    "AI Conversation Settings",
                    "Advanced AI Settings",
                ]
            ):
                return_menu = "ai"
            # Otherwise check the message title for submenu detection
            elif "Watermark" in message.text:
                return_menu = "mediatools_watermark"
            elif "Merge" in message.text:
                return_menu = "mediatools_merge"
            elif "Convert" in message.text:
                return_menu = "mediatools_convert"
            elif "Compression" in message.text:
                return_menu = "mediatools_compression"
            elif "Trim" in message.text:
                return_menu = "mediatools_trim"
            elif "Extract" in message.text:
                return_menu = "mediatools_extract"
            elif "Add" in message.text:
                return_menu = "mediatools_add"

            elif "Usenet Servers" in message.text:
                return_menu = "nzbserver"

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, return_menu)
    elif data[1] == "syncjd":
        if not Config.JD_EMAIL or not Config.JD_PASS:
            await query.answer(
                "No JDownloader Email or Password provided! Please set JD_EMAIL and JD_PASS in Config first.",
                show_alert=True,
            )
            return
        # Get the current state before making changes
        current_state = globals()["state"]

        await query.answer(
            "JD Sync Started. JDownloader will be restarted. This process takes up to 10 seconds!",
            show_alert=True,
        )

        # Show a status message to the user
        await edit_message(
            message,
            "<b>JD Sync</b>\n\n⏳ Syncing JDownloader configuration...\n\n<i>Please wait, this may take up to 10 seconds.</i>",
        )

        # Perform the sync operation
        await sync_jdownloader()

        # Update the status message
        await edit_message(
            message,
            "<b>JD Sync</b>\n\n✅ JDownloader configuration has been successfully synchronized!\n\n<i>JDownloader has been restarted with the updated configuration.</i>",
        )

        # Auto-delete the status message after 5 seconds
        await sleep(5)

        # Set the state back to what it was
        globals()["state"] = current_state

        # Return to the main settings menu
        await update_buttons(message, None)
    elif data[1] == "streamrip":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            await query.answer(
                "Streamrip is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "streamrip")

    elif data[1] == "gallerydl":
        await query.answer()
        await update_buttons(message, "gallerydl")

    elif data[1] == "gallerydl_general":
        await query.answer()
        await update_buttons(message, "gallerydl_general")

    elif data[1] == "gallerydl_auth":
        await query.answer()
        await update_buttons(message, "gallerydl_auth")

    elif data[1] == "gallerydl_download":
        await query.answer()
        await update_buttons(message, "gallerydl_download")

    elif data[1] == "gallerydl_platforms":
        await query.answer("Platform settings moved to Authentication section!")
        await update_buttons(message, "gallerydl_auth")

    elif data[1] == "zotify":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if zotify is enabled
        if not Config.ZOTIFY_ENABLED:
            await query.answer(
                "Zotify is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "zotify")

    elif data[1] == "youtube":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if YouTube upload is enabled
        if not Config.YOUTUBE_UPLOAD_ENABLED:
            await query.answer(
                "YouTube upload is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "youtube")

    elif data[1] == "mega":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if MEGA is enabled
        if not Config.MEGA_ENABLED:
            await query.answer("MEGA is disabled by the bot owner.", show_alert=True)
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mega")

    elif data[1] == "ddl":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if DDL is enabled
        if not Config.DDL_ENABLED:
            await query.answer("DDL is disabled by the bot owner.", show_alert=True)
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "ddl")

    elif data[1] in [
        "streamrip_general",
        "streamrip_quality",
        "streamrip_credentials",
        "streamrip_download",
        "streamrip_platforms",
        "streamrip_database",
        "streamrip_conversion",
        "streamrip_metadata",
        "streamrip_cli",
        "streamrip_advanced",
        "streamrip_config",
    ]:
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            await query.answer(
                "Streamrip is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[1])

    elif data[1] in [
        "zotify_general",
        "zotify_quality",
        "zotify_auth",
        "zotify_paths",
        "zotify_templates",
        "zotify_download",
        "zotify_metadata",
        "zotify_advanced",
    ]:
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if zotify is enabled
        if not Config.ZOTIFY_ENABLED:
            await query.answer(
                "Zotify is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[1])

    elif data[1] in [
        "youtube_general",
        "youtube_upload",
        "youtube_auth",
    ]:
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if YouTube upload is enabled
        if not Config.YOUTUBE_UPLOAD_ENABLED:
            await query.answer(
                "YouTube upload is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[1])

    elif data[1] in [
        "mega_general",
        "mega_upload",
        "mega_security",
    ]:
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if MEGA is enabled
        if not Config.MEGA_ENABLED:
            await query.answer("MEGA is disabled by the bot owner.", show_alert=True)
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[1])

    elif data[1] in [
        "ddl_general",
        "ddl_gofile",
        "ddl_streamtape",
        "ddl_devuploads",
        "ddl_mediafire",
    ]:
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if DDL is enabled
        if not Config.DDL_ENABLED:
            await query.answer("DDL is disabled by the bot owner.", show_alert=True)
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[1])

    elif data[1] == "view_streamrip_config":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            await query.answer(
                "Streamrip is disabled by the bot owner.", show_alert=True
            )
            return

        try:
            # Import streamrip config helper
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            # Try to get custom config from database first
            config_content = await streamrip_config.get_custom_config_from_db()

            if not config_content:
                # If no custom config, generate current config based on bot settings
                config_content = await _generate_current_config_content()

            if config_content:
                # Create a temporary file to send
                import os
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".toml", delete=False
                ) as temp_file:
                    temp_file.write(config_content)
                    temp_file_path = temp_file.name

                try:
                    # Send the config file
                    await send_file(
                        message, temp_file_path, "current_streamrip_config.toml"
                    )

                    # Send info message
                    config_type = (
                        "custom"
                        if await streamrip_config.get_custom_config_from_db()
                        else "generated from bot settings"
                    )
                    await send_message(
                        message,
                        f"<b>📄 Current Streamrip Configuration</b>\n\n"
                        f"The current streamrip configuration file has been sent above.\n\n"
                        f"<b>Config Type:</b> {config_type}\n"
                        f"<b>Note:</b> This shows the active configuration being used by the bot.",
                    )
                finally:
                    # Clean up temporary file
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
            else:
                await send_message(
                    message,
                    "<b>❌ Error</b>\n\n"
                    "Could not retrieve the current streamrip configuration.",
                )

        except Exception as e:
            from bot import LOGGER

            LOGGER.error(f"Error viewing streamrip config: {e}")
            await send_message(
                message,
                f"<b>❌ Error</b>\n\nFailed to view streamrip configuration: {e!s}",
            )

        # Set the state back to what it was
        globals()["state"] = current_state

    elif data[1] == "upload_streamrip_config":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            await query.answer(
                "Streamrip is disabled by the bot owner.", show_alert=True
            )
            return

        # Set up handler for config file upload
        handler_dict[message.chat.id] = True

        # Send instructions to the user
        buttons = ButtonMaker()
        buttons.data_button("❌ Cancel", "botset cancel_streamrip_upload")
        button_markup = buttons.build_menu(1)

        # Update the current message with upload instructions
        await edit_message(
            message,
            "<b>📤 Upload Streamrip Config</b>\n\n"
            "Please send a <code>config.toml</code> file for streamrip.\n\n"
            "<b>Requirements:</b>\n"
            "• File must be a valid TOML format\n"
            "• File should contain streamrip configuration sections\n"
            "• Maximum file size: 5MB\n\n"
            "<b>Note:</b> The uploaded config will override bot settings and be stored in the database.\n\n"
            "Click Cancel to abort.",
            button_markup,
        )

        # Set up event handler for the config file upload
        await event_handler(
            client,
            query,
            handle_streamrip_config_upload,
            lambda: update_buttons(message, "streamrip_config"),
            document=True,
        )

        # Set the state back to what it was
        globals()["state"] = current_state

    elif data[1] == "reset_streamrip_config":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            await query.answer(
                "Streamrip is disabled by the bot owner.", show_alert=True
            )
            return

        try:
            # Import streamrip config helper
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            # Delete custom config from database
            success = await streamrip_config.delete_custom_config_from_db()

            if success:
                # Reinitialize streamrip config to use default settings
                await streamrip_config.initialize()

                await send_message(
                    message,
                    "<b>✅ Config Reset Successful</b>\n\n"
                    "Streamrip configuration has been reset to default bot settings.\n\n"
                    "<b>Changes:</b>\n"
                    "• Custom config file removed from database\n"
                    "• Reverted to bot's default streamrip settings\n"
                    "• All platform credentials preserved\n\n"
                    "<i>The bot will now use the configured settings from the individual menus.</i>",
                )
            else:
                await send_message(
                    message,
                    "<b>❌ Reset Failed</b>\n\n"
                    "Failed to reset streamrip configuration. Please try again.",
                )

        except Exception as e:
            from bot import LOGGER

            LOGGER.error(f"Error resetting streamrip config: {e}")
            await send_message(
                message,
                f"<b>❌ Error</b>\n\nFailed to reset streamrip configuration: {e!s}",
            )

        # Set the state back to what it was
        globals()["state"] = current_state

    elif data[1] == "cancel_streamrip_upload":
        await query.answer("Upload cancelled.")
        # Get the current state before making changes
        current_state = globals()["state"]

        # Disable the handler
        handler_dict[message.chat.id] = False

        # Set the state back to what it was
        globals()["state"] = current_state

        # Return to streamrip config menu
        await update_buttons(message, "streamrip_config")

    elif data[1] == "upload_zotify_credentials":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if zotify is enabled
        if not Config.ZOTIFY_ENABLED:
            await query.answer(
                "Zotify is disabled by the bot owner.", show_alert=True
            )
            return

        # Set up handler for credentials file upload
        handler_dict[message.chat.id] = True

        # Send instructions to the user
        buttons = ButtonMaker()
        buttons.data_button("❌ Cancel", "botset cancel_zotify_upload")
        button_markup = buttons.build_menu(1)

        # Update the current message with upload instructions
        await edit_message(
            message,
            "<b>📤 Upload Zotify Credentials</b>\n\n"
            "Please send a <code>credentials.json</code> file for Zotify.\n\n"
            "<b>Requirements:</b>\n"
            "• File must be a valid JSON format\n"
            "• File should contain Spotify authentication data\n"
            "• Maximum file size: 5MB\n\n"
            "<b>Note:</b> The uploaded credentials will be stored securely and used for Spotify authentication.\n\n"
            "Click Cancel to abort.",
            button_markup,
        )

        # Set up event handler for the credentials file upload
        await event_handler(
            client,
            query,
            handle_zotify_credentials_upload,
            lambda: update_buttons(message, "zotify_auth"),
            document=True,
        )

        # Set the state back to what it was
        globals()["state"] = current_state

    elif data[1] == "clear_zotify_credentials":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if zotify is enabled
        if not Config.ZOTIFY_ENABLED:
            await query.answer(
                "Zotify is disabled by the bot owner.", show_alert=True
            )
            return

        try:
            # Import required modules
            from pathlib import Path

            user_id = message.chat.id
            credentials_cleared = False

            # Clear credentials from database
            if database.db is not None:
                try:
                    result = await database.db.users.update_one(
                        {"_id": user_id},
                        {"$unset": {"ZOTIFY_CREDENTIALS": ""}},
                    )
                    if result.modified_count > 0:
                        credentials_cleared = True
                except Exception as e:
                    from bot import LOGGER

                    LOGGER.error(
                        f"Error clearing Zotify credentials from database: {e}"
                    )

            # Clear credentials file
            credentials_path = (
                Config.ZOTIFY_CREDENTIALS_PATH or "./zotify_credentials.json"
            )
            creds_file = Path(credentials_path)

            if creds_file.exists():
                # Remove the credentials file
                creds_file.unlink()
                credentials_cleared = True

            if credentials_cleared:
                await send_message(
                    message,
                    "<b>✅ Credentials Cleared</b>\n\n"
                    "Zotify credentials have been successfully removed.\n\n"
                    "<b>Changes:</b>\n"
                    "• Credentials removed from database\n"
                    "• Credentials file deleted (if existed)\n"
                    "• Zotify will require re-authentication on next use\n\n"
                    "<i>You can upload new credentials or let Zotify authenticate interactively.</i>",
                )
            else:
                await send_message(
                    message,
                    "<b>ℹ️ No Credentials Found</b>\n\n"
                    "No credentials were found to clear.\n\n"
                    "Zotify will authenticate interactively when needed.",
                )

        except Exception as e:
            from bot import LOGGER

            LOGGER.error(f"Error clearing Zotify credentials: {e}")
            await send_message(
                message,
                f"<b>❌ Error</b>\n\nFailed to clear Zotify credentials: {e!s}",
            )

        # Set the state back to what it was
        globals()["state"] = current_state

    elif data[1] == "cancel_zotify_upload":
        await query.answer("Upload cancelled.")
        # Get the current state before making changes
        current_state = globals()["state"]

        # Disable the handler
        handler_dict[message.chat.id] = False

        # Set the state back to what it was
        globals()["state"] = current_state

        # Return to zotify auth menu
        await update_buttons(message, "zotify_auth")

    elif data[1] == "operations":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "operations")

    elif data[1] == "mediatools":
        await query.answer()
        # No need to track state for media tools

        # Always show the media tools menu, regardless of whether tools are enabled
        await update_buttons(message, "mediatools")

    elif data[1] == "configure_media_tools":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Get current value
        key = "MEDIA_TOOLS_ENABLED"
        current_value = Config.get(key)

        # List of all available tools with descriptions
        all_tools_info = [
            {
                "name": "watermark",
                "icon": "💧",
                "desc": "Add text or image watermarks to media",
            },
            {
                "name": "merge",
                "icon": "🔄",
                "desc": "Combine multiple files into one",
            },
            {"name": "convert", "icon": "🔄", "desc": "Change file formats"},
            {"name": "compression", "icon": "🗜️", "desc": "Reduce file sizes"},
            {"name": "trim", "icon": "✂️", "desc": "Cut sections from media files"},
            {
                "name": "extract",
                "icon": "📤",
                "desc": "Extract components from media",
            },
            {"name": "add", "icon": "➕", "desc": "Add elements to media files"},
            {
                "name": "swap",
                "icon": "⌬",
                "desc": "Reorder tracks by language or index",
            },
            {"name": "metadata", "icon": "📝", "desc": "Modify file metadata"},
            {"name": "xtra", "icon": "🎬", "desc": "Use custom FFmpeg commands"},
            {"name": "sample", "icon": "🎞️", "desc": "Create sample clips"},
            {
                "name": "screenshot",
                "icon": "📸",
                "desc": "Take screenshots from videos",
            },
            {
                "name": "archive",
                "icon": "🗜️",
                "desc": "Enable archive flags (-z, -e) for compression/extraction",
            },
        ]

        # Get list of tool names only
        all_tools = [tool["name"] for tool in all_tools_info]

        # Parse current enabled tools
        enabled_tools = []
        if isinstance(current_value, str):
            # Handle both comma-separated and single values
            if "," in current_value:
                enabled_tools = [
                    t.strip().lower() for t in current_value.split(",") if t.strip()
                ]
            elif current_value.strip():  # Single non-empty value
                enabled_tools = [current_value.strip().lower()]
        elif current_value is True:  # If it's True (boolean), all tools are enabled
            enabled_tools = all_tools.copy()

        # Create buttons for each tool
        buttons = ButtonMaker()
        for tool_info in all_tools_info:
            tool = tool_info["name"]
            icon = tool_info["icon"]
            status = "✅" if tool in enabled_tools else "❌"
            tool_name = tool.capitalize()
            buttons.data_button(
                f"{icon} {tool_name}: {status}",
                f"botset toggle_tool {key} {tool}",
            )

        # Add buttons to enable/disable all tools
        buttons.data_button("✅ Enable All", f"botset enable_all_tools {key}")
        buttons.data_button("❌ Disable All", f"botset disable_all_tools {key}")

        # Add done button
        buttons.data_button("✅ Done", "botset mediatools")

        # Set the state back to what it was
        globals()["state"] = current_state

        # Create a more informative message
        tool_status_msg = f"<b>Configure Media Tools</b> ({len(enabled_tools)}/{len(all_tools)} Enabled)\n\n"
        tool_status_msg += "Select which media tools to enable:\n\n"

        # Add a brief description of each tool
        for tool_info in all_tools_info:
            tool = tool_info["name"]
            icon = tool_info["icon"]
            desc = tool_info["desc"]
            status = "✅ Enabled" if tool in enabled_tools else "❌ Disabled"
            tool_status_msg += (
                f"{icon} <b>{tool.capitalize()}</b>: {status}\n<i>{desc}</i>\n\n"
            )

        # Show the message with tool descriptions and buttons
        await edit_message(
            message,
            tool_status_msg,
            buttons.build_menu(2),
        )
    elif data[1] == "mediatools_watermark":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if watermark is enabled
        if not is_media_tool_enabled("watermark"):
            await query.answer(
                "Watermark tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_watermark")

    elif data[1] == "upload_watermark_image":
        await safe_answer()

        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if watermark is enabled
        if not is_media_tool_enabled("watermark"):
            await safe_answer(
                "Watermark tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set up handler for image upload
        handler_dict[message.chat.id] = True

        # Set a flag to indicate this upload is from bot_settings
        # This is used in handle_watermark_image_upload to determine the return path
        handler_dict[f"{message.chat.id}_from_bot_settings"] = True

        # Store the original message for returning to the menu later
        handler_dict[f"{message.chat.id}_original_message"] = message

        # Send instructions to the user
        buttons = ButtonMaker()
        buttons.data_button("Cancel", "botset cancel_image_upload")
        button_markup = buttons.build_menu(1)

        # Update the current message instead of sending a new one
        await edit_message(
            message,
            "Please send an image to use as a watermark. The image will be stored in the database.\n\n"
            "• Recommended size: Less than 500x500 pixels\n"
            "• Transparent PNG images work best\n"
            "• Maximum file size: 5MB\n\n"
            "Click Cancel to abort.",
            button_markup,
        )

        # Set up event handler for the image upload
        await event_handler(
            client,
            query,
            handle_watermark_image_upload,
            lambda: update_buttons(message, "mediatools_watermark"),
            photo=True,
            document=True,
        )

    elif data[1] == "watermark_text":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if watermark is enabled
        if not is_media_tool_enabled("watermark"):
            await query.answer(
                "Watermark tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        # Reset the page when first entering the menu
        globals()["watermark_text_page"] = 0
        await update_buttons(message, "mediatools_watermark_text", page=0)

    elif data[1] == "back_to_watermark_text":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Always go back to the watermark menu
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_watermark")
        return

    elif data[1] == "back_to_watermark_text_page":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        try:
            # Check if we have a page number in the callback data
            if len(data) > 2:
                # Update the global watermark_text_page variable with the page from the button
                globals()["watermark_text_page"] = int(data[2])
            # If no page number is provided, try to extract it from the message text
            elif message.text and "Page:" in message.text:
                try:
                    page_info = message.text.split("Page:")[1].strip().split("/")[0]
                    page_no = int(page_info) - 1
                    globals()["watermark_text_page"] = page_no
                except (ValueError, IndexError):
                    # Keep the current page if there's an error
                    pass

            # Set the state back to what it was
            globals()["state"] = current_state
            # Return to the watermark text menu with the correct page
            await update_buttons(
                message,
                "mediatools_watermark_text",
                page=globals()["watermark_text_page"],
            )
            return
        except Exception:
            # If there's an error, just go back to the watermark menu
            globals()["state"] = current_state
            await update_buttons(message, "mediatools_watermark")
            return

    # Default watermark text handler removed as requested

    elif data[1] == "start_watermark_text":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        try:
            if len(data) > 2:
                # Update the global watermark_text_page variable
                globals()["watermark_text_page"] = int(data[2])

                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(
                    message,
                    "mediatools_watermark_text",
                    page=globals()["watermark_text_page"],
                )
            else:
                # If no page number is provided, stay on the current page
                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(
                    message,
                    "mediatools_watermark_text",
                    page=globals()["watermark_text_page"],
                )
        except (ValueError, IndexError):
            # In case of any error, stay on the current page

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(
                message,
                "mediatools_watermark_text",
                page=globals()["watermark_text_page"],
            )
    elif data[1] == "mediatools_merge":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if merge is enabled
        if not is_media_tool_enabled("merge"):
            await query.answer(
                "Merge tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        # Always start at page 0 when first entering merge settings
        await update_buttons(message, "mediatools_merge", page=0)
    elif data[1] == "mediatools_merge_config":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if merge is enabled
        if not is_media_tool_enabled("merge"):
            await query.answer(
                "Merge tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state

        # Check if we're coming from a specific config setting
        # If so, maintain the current page, otherwise start at page 0
        if message.text and "Page:" in message.text:
            try:
                page_info = message.text.split("Page:")[1].strip().split("/")[0]
                page_no = int(page_info) - 1
                # Set both global page variables to ensure we return to the correct page
                globals()["merge_page"] = page_no
                globals()["merge_config_page"] = page_no
                await update_buttons(message, "mediatools_merge", page=page_no)
            except (ValueError, IndexError):
                # If there's an error parsing the page number, use the stored page
                await update_buttons(
                    message, "mediatools_merge", page=globals()["merge_page"]
                )
        else:
            # Reset the page when first entering the menu
            globals()["merge_page"] = 0
            globals()["merge_config_page"] = 0
            await update_buttons(message, "mediatools_merge", page=0)
    elif data[1] == "mediatools_metadata":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_metadata")
    elif data[1] == "mediatools_convert":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if convert is enabled
        if not is_media_tool_enabled("convert"):
            await query.answer(
                "Convert tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_convert")
    elif data[1] == "mediatools_trim":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if trim is enabled
        if not is_media_tool_enabled("trim"):
            await query.answer(
                "Trim tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_trim")

    elif data[1] == "mediatools_extract":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if extract is enabled
        if not is_media_tool_enabled("extract"):
            await query.answer(
                "Extract tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_extract")

    elif data[1] == "mediatools_add":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if add is enabled
        if not is_media_tool_enabled("add"):
            await query.answer(
                "Add tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_add")

    elif data[1] == "mediatools_swap":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if swap is enabled
        if not is_media_tool_enabled("swap"):
            await query.answer(
                "Swap tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_swap")

    elif data[1] == "mediatools_compression":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if compression is enabled
        if not is_media_tool_enabled("compression"):
            await query.answer(
                "Compression tool is disabled by the bot owner.", show_alert=True
            )
            return

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_compression")

    elif data[1] == "ai":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "ai")

    elif data[1] == "cancel_image_upload":
        await safe_answer("Image upload cancelled")

        # Cancel the image upload handler
        handler_dict[message.chat.id] = False

        # Clean up handler_dict entries
        if f"{message.chat.id}_from_bot_settings" in handler_dict:
            del handler_dict[f"{message.chat.id}_from_bot_settings"]
        if f"{message.chat.id}_original_message" in handler_dict:
            del handler_dict[f"{message.chat.id}_original_message"]

        # Return to the watermark settings menu
        await update_buttons(message, "mediatools_watermark")

    elif data[1] == "default_watermark_text":
        await query.answer(
            "Resetting watermark configure settings to default values..."
        )
        # Reset all watermark text settings to default
        Config.WATERMARK_POSITION = "top_left"
        Config.WATERMARK_SIZE = 20
        Config.WATERMARK_COLOR = "white"
        Config.WATERMARK_FONT = "default.otf"
        Config.WATERMARK_OPACITY = 1.0
        Config.WATERMARK_QUALITY = None
        Config.WATERMARK_SPEED = None

        # Reset image watermark settings
        Config.IMAGE_WATERMARK_SCALE = 10
        Config.IMAGE_WATERMARK_POSITION = "bottom_right"
        Config.IMAGE_WATERMARK_OPACITY = 1.0

        # Reset audio watermark settings
        Config.AUDIO_WATERMARK_VOLUME = 0.3
        Config.AUDIO_WATERMARK_INTERVAL = None

        # Reset subtitle watermark settings
        Config.SUBTITLE_WATERMARK_STYLE = "default"
        Config.SUBTITLE_WATERMARK_INTERVAL = None

        # Update the database
        await database.update_config(
            {
                "WATERMARK_POSITION": "top_left",
                "WATERMARK_SIZE": 20,
                "WATERMARK_COLOR": "white",
                "WATERMARK_FONT": "default.otf",
                "WATERMARK_OPACITY": 1.0,
                "WATERMARK_QUALITY": None,
                "WATERMARK_SPEED": None,
                # Image watermark settings
                "IMAGE_WATERMARK_SCALE": 10,
                "IMAGE_WATERMARK_POSITION": "bottom_right",
                "IMAGE_WATERMARK_OPACITY": 1.0,
                # Audio watermark settings
                "AUDIO_WATERMARK_VOLUME": 0.3,
                "AUDIO_WATERMARK_INTERVAL": None,
                # Subtitle watermark settings
                "SUBTITLE_WATERMARK_STYLE": "default",
                "SUBTITLE_WATERMARK_INTERVAL": None,
            }
        )

        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state

        # Use the stored page if available
        if message.chat.id and f"{message.chat.id}_watermark_page" in handler_dict:
            page = handler_dict[f"{message.chat.id}_watermark_page"]
            await update_buttons(message, "mediatools_watermark_text", page=page)
        else:
            # Otherwise use the global variable or default to page 0
            page = globals().get("watermark_text_page", 0)
            await update_buttons(message, "mediatools_watermark_text", page=page)

    elif data[1] == "default_watermark":
        await query.answer("Resetting all watermark settings to default...")
        # Reset all watermark settings to default
        Config.WATERMARK_ENABLED = False
        Config.WATERMARK_KEY = ""
        Config.WATERMARK_POSITION = "none"
        Config.WATERMARK_SIZE = 0
        Config.WATERMARK_COLOR = "none"
        Config.WATERMARK_FONT = "none"
        Config.WATERMARK_PRIORITY = 2
        Config.WATERMARK_THREADING = True
        Config.WATERMARK_THREAD_NUMBER = 4
        Config.WATERMARK_QUALITY = "none"
        Config.WATERMARK_SPEED = "none"
        Config.WATERMARK_OPACITY = 0.0
        Config.WATERMARK_REMOVE_ORIGINAL = True

        # Reset image watermark settings
        Config.IMAGE_WATERMARK_ENABLED = False
        Config.IMAGE_WATERMARK_PATH = ""
        Config.IMAGE_WATERMARK_SCALE = 10
        Config.IMAGE_WATERMARK_OPACITY = 1.0
        Config.IMAGE_WATERMARK_POSITION = "bottom_right"

        # Remove the image watermark from the database for this user and owner
        try:
            # Remove user's watermark if this is a user
            if message.chat.id:
                await database.update_user_doc(
                    message.chat.id, "IMAGE_WATERMARK", None, None
                )

            # Also remove owner's watermark if this is the owner or we're resetting global settings
            if hasattr(Config, "OWNER_ID"):
                await database.update_user_doc(
                    Config.OWNER_ID, "IMAGE_WATERMARK", None, None
                )

        except Exception:
            pass

        # Reset audio watermark settings
        Config.AUDIO_WATERMARK_VOLUME = 0.3
        Config.AUDIO_WATERMARK_INTERVAL = 0

        # Reset subtitle watermark settings
        Config.SUBTITLE_WATERMARK_STYLE = "none"
        Config.SUBTITLE_WATERMARK_INTERVAL = 0

        # Update the database
        await database.update_config(
            {
                "WATERMARK_ENABLED": False,
                "WATERMARK_KEY": "",
                "WATERMARK_POSITION": "none",
                "WATERMARK_SIZE": 0,
                "WATERMARK_COLOR": "none",
                "WATERMARK_FONT": "none",
                "WATERMARK_PRIORITY": 2,
                "WATERMARK_THREADING": True,
                "WATERMARK_THREAD_NUMBER": 4,
                "WATERMARK_QUALITY": "none",
                "WATERMARK_SPEED": "none",
                "WATERMARK_OPACITY": 0.0,
                "WATERMARK_REMOVE_ORIGINAL": True,
                # Image watermark settings
                "IMAGE_WATERMARK_ENABLED": False,
                "IMAGE_WATERMARK_PATH": "",
                "IMAGE_WATERMARK_SCALE": 10,
                "IMAGE_WATERMARK_OPACITY": 1.0,
                "IMAGE_WATERMARK_POSITION": "bottom_right",
                # Audio watermark settings
                "AUDIO_WATERMARK_VOLUME": 0.3,
                "AUDIO_WATERMARK_INTERVAL": 0,
                # Subtitle watermark settings
                "SUBTITLE_WATERMARK_STYLE": "none",
                "SUBTITLE_WATERMARK_INTERVAL": 0,
            }
        )
        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_watermark")

    elif data[1] == "default_compression":
        await query.answer("Resetting all compression settings to default...")
        # Reset all compression settings to default using DEFAULT_VALUES

        # General compression settings
        Config.COMPRESSION_ENABLED = DEFAULT_VALUES["COMPRESSION_ENABLED"]
        Config.COMPRESSION_PRIORITY = DEFAULT_VALUES["COMPRESSION_PRIORITY"]
        Config.COMPRESSION_DELETE_ORIGINAL = DEFAULT_VALUES[
            "COMPRESSION_DELETE_ORIGINAL"
        ]  # This is True by default

        # Video compression settings
        Config.COMPRESSION_VIDEO_ENABLED = DEFAULT_VALUES[
            "COMPRESSION_VIDEO_ENABLED"
        ]
        Config.COMPRESSION_VIDEO_PRESET = DEFAULT_VALUES["COMPRESSION_VIDEO_PRESET"]
        Config.COMPRESSION_VIDEO_CRF = DEFAULT_VALUES["COMPRESSION_VIDEO_CRF"]
        Config.COMPRESSION_VIDEO_CODEC = DEFAULT_VALUES["COMPRESSION_VIDEO_CODEC"]
        Config.COMPRESSION_VIDEO_TUNE = DEFAULT_VALUES["COMPRESSION_VIDEO_TUNE"]
        Config.COMPRESSION_VIDEO_PIXEL_FORMAT = DEFAULT_VALUES[
            "COMPRESSION_VIDEO_PIXEL_FORMAT"
        ]

        # Audio compression settings
        Config.COMPRESSION_AUDIO_ENABLED = DEFAULT_VALUES[
            "COMPRESSION_AUDIO_ENABLED"
        ]
        Config.COMPRESSION_AUDIO_PRESET = DEFAULT_VALUES["COMPRESSION_AUDIO_PRESET"]
        Config.COMPRESSION_AUDIO_CODEC = DEFAULT_VALUES["COMPRESSION_AUDIO_CODEC"]
        Config.COMPRESSION_AUDIO_BITRATE = DEFAULT_VALUES[
            "COMPRESSION_AUDIO_BITRATE"
        ]
        Config.COMPRESSION_AUDIO_CHANNELS = DEFAULT_VALUES[
            "COMPRESSION_AUDIO_CHANNELS"
        ]

        # Image compression settings
        Config.COMPRESSION_IMAGE_ENABLED = DEFAULT_VALUES[
            "COMPRESSION_IMAGE_ENABLED"
        ]
        Config.COMPRESSION_IMAGE_PRESET = DEFAULT_VALUES["COMPRESSION_IMAGE_PRESET"]
        Config.COMPRESSION_IMAGE_QUALITY = DEFAULT_VALUES[
            "COMPRESSION_IMAGE_QUALITY"
        ]
        Config.COMPRESSION_IMAGE_RESIZE = DEFAULT_VALUES["COMPRESSION_IMAGE_RESIZE"]

        # Document compression settings
        Config.COMPRESSION_DOCUMENT_ENABLED = DEFAULT_VALUES[
            "COMPRESSION_DOCUMENT_ENABLED"
        ]
        Config.COMPRESSION_DOCUMENT_PRESET = DEFAULT_VALUES[
            "COMPRESSION_DOCUMENT_PRESET"
        ]
        Config.COMPRESSION_DOCUMENT_DPI = DEFAULT_VALUES["COMPRESSION_DOCUMENT_DPI"]

        # Subtitle compression settings
        Config.COMPRESSION_SUBTITLE_ENABLED = DEFAULT_VALUES[
            "COMPRESSION_SUBTITLE_ENABLED"
        ]
        Config.COMPRESSION_SUBTITLE_PRESET = DEFAULT_VALUES[
            "COMPRESSION_SUBTITLE_PRESET"
        ]
        Config.COMPRESSION_SUBTITLE_ENCODING = DEFAULT_VALUES[
            "COMPRESSION_SUBTITLE_ENCODING"
        ]

        # Archive compression settings
        Config.COMPRESSION_ARCHIVE_ENABLED = DEFAULT_VALUES[
            "COMPRESSION_ARCHIVE_ENABLED"
        ]
        Config.COMPRESSION_ARCHIVE_PRESET = DEFAULT_VALUES[
            "COMPRESSION_ARCHIVE_PRESET"
        ]
        Config.COMPRESSION_ARCHIVE_LEVEL = DEFAULT_VALUES[
            "COMPRESSION_ARCHIVE_LEVEL"
        ]
        Config.COMPRESSION_ARCHIVE_METHOD = DEFAULT_VALUES[
            "COMPRESSION_ARCHIVE_METHOD"
        ]
        Config.COMPRESSION_ARCHIVE_PASSWORD = DEFAULT_VALUES[
            "COMPRESSION_ARCHIVE_PASSWORD"
        ]
        Config.COMPRESSION_ARCHIVE_ALGORITHM = DEFAULT_VALUES[
            "COMPRESSION_ARCHIVE_ALGORITHM"
        ]

        # Update the database
        await database.update_config(
            {
                # General compression settings
                "COMPRESSION_ENABLED": DEFAULT_VALUES["COMPRESSION_ENABLED"],
                "COMPRESSION_PRIORITY": DEFAULT_VALUES["COMPRESSION_PRIORITY"],
                "COMPRESSION_DELETE_ORIGINAL": DEFAULT_VALUES[
                    "COMPRESSION_DELETE_ORIGINAL"
                ],
                # Video compression settings
                "COMPRESSION_VIDEO_ENABLED": DEFAULT_VALUES[
                    "COMPRESSION_VIDEO_ENABLED"
                ],
                "COMPRESSION_VIDEO_PRESET": DEFAULT_VALUES[
                    "COMPRESSION_VIDEO_PRESET"
                ],
                "COMPRESSION_VIDEO_CRF": DEFAULT_VALUES["COMPRESSION_VIDEO_CRF"],
                "COMPRESSION_VIDEO_CODEC": DEFAULT_VALUES["COMPRESSION_VIDEO_CODEC"],
                "COMPRESSION_VIDEO_TUNE": DEFAULT_VALUES["COMPRESSION_VIDEO_TUNE"],
                "COMPRESSION_VIDEO_PIXEL_FORMAT": DEFAULT_VALUES[
                    "COMPRESSION_VIDEO_PIXEL_FORMAT"
                ],
                # Audio compression settings
                "COMPRESSION_AUDIO_ENABLED": DEFAULT_VALUES[
                    "COMPRESSION_AUDIO_ENABLED"
                ],
                "COMPRESSION_AUDIO_PRESET": DEFAULT_VALUES[
                    "COMPRESSION_AUDIO_PRESET"
                ],
                "COMPRESSION_AUDIO_CODEC": DEFAULT_VALUES["COMPRESSION_AUDIO_CODEC"],
                "COMPRESSION_AUDIO_BITRATE": DEFAULT_VALUES[
                    "COMPRESSION_AUDIO_BITRATE"
                ],
                "COMPRESSION_AUDIO_CHANNELS": DEFAULT_VALUES[
                    "COMPRESSION_AUDIO_CHANNELS"
                ],
                # Image compression settings
                "COMPRESSION_IMAGE_ENABLED": DEFAULT_VALUES[
                    "COMPRESSION_IMAGE_ENABLED"
                ],
                "COMPRESSION_IMAGE_PRESET": DEFAULT_VALUES[
                    "COMPRESSION_IMAGE_PRESET"
                ],
                "COMPRESSION_IMAGE_QUALITY": DEFAULT_VALUES[
                    "COMPRESSION_IMAGE_QUALITY"
                ],
                "COMPRESSION_IMAGE_RESIZE": DEFAULT_VALUES[
                    "COMPRESSION_IMAGE_RESIZE"
                ],
                # Document compression settings
                "COMPRESSION_DOCUMENT_ENABLED": DEFAULT_VALUES[
                    "COMPRESSION_DOCUMENT_ENABLED"
                ],
                "COMPRESSION_DOCUMENT_PRESET": DEFAULT_VALUES[
                    "COMPRESSION_DOCUMENT_PRESET"
                ],
                "COMPRESSION_DOCUMENT_DPI": DEFAULT_VALUES[
                    "COMPRESSION_DOCUMENT_DPI"
                ],
                # Subtitle compression settings
                "COMPRESSION_SUBTITLE_ENABLED": DEFAULT_VALUES[
                    "COMPRESSION_SUBTITLE_ENABLED"
                ],
                "COMPRESSION_SUBTITLE_PRESET": DEFAULT_VALUES[
                    "COMPRESSION_SUBTITLE_PRESET"
                ],
                "COMPRESSION_SUBTITLE_ENCODING": DEFAULT_VALUES[
                    "COMPRESSION_SUBTITLE_ENCODING"
                ],
                # Archive compression settings
                "COMPRESSION_ARCHIVE_ENABLED": DEFAULT_VALUES[
                    "COMPRESSION_ARCHIVE_ENABLED"
                ],
                "COMPRESSION_ARCHIVE_PRESET": DEFAULT_VALUES[
                    "COMPRESSION_ARCHIVE_PRESET"
                ],
                "COMPRESSION_ARCHIVE_LEVEL": DEFAULT_VALUES[
                    "COMPRESSION_ARCHIVE_LEVEL"
                ],
                "COMPRESSION_ARCHIVE_METHOD": DEFAULT_VALUES[
                    "COMPRESSION_ARCHIVE_METHOD"
                ],
                "COMPRESSION_ARCHIVE_PASSWORD": DEFAULT_VALUES[
                    "COMPRESSION_ARCHIVE_PASSWORD"
                ],
                "COMPRESSION_ARCHIVE_ALGORITHM": DEFAULT_VALUES[
                    "COMPRESSION_ARCHIVE_ALGORITHM"
                ],
            }
        )
        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_compression")

    # default_add handler moved to line 7057

    elif data[1] == "default_extract":
        await query.answer("Resetting all extract settings to default...")
        # Reset all extract settings to default using DEFAULT_VALUES

        # General extract settings
        Config.EXTRACT_ENABLED = DEFAULT_VALUES["EXTRACT_ENABLED"]
        Config.EXTRACT_PRIORITY = DEFAULT_VALUES["EXTRACT_PRIORITY"]
        Config.EXTRACT_DELETE_ORIGINAL = DEFAULT_VALUES["EXTRACT_DELETE_ORIGINAL"]

        # Video extract settings
        Config.EXTRACT_VIDEO_ENABLED = DEFAULT_VALUES["EXTRACT_VIDEO_ENABLED"]
        Config.EXTRACT_VIDEO_CODEC = DEFAULT_VALUES["EXTRACT_VIDEO_CODEC"]
        Config.EXTRACT_VIDEO_FORMAT = DEFAULT_VALUES.get(
            "EXTRACT_VIDEO_FORMAT", "none"
        )
        Config.EXTRACT_VIDEO_INDEX = DEFAULT_VALUES["EXTRACT_VIDEO_INDEX"]
        Config.EXTRACT_VIDEO_QUALITY = DEFAULT_VALUES["EXTRACT_VIDEO_QUALITY"]
        Config.EXTRACT_VIDEO_PRESET = DEFAULT_VALUES["EXTRACT_VIDEO_PRESET"]
        Config.EXTRACT_VIDEO_BITRATE = DEFAULT_VALUES["EXTRACT_VIDEO_BITRATE"]
        Config.EXTRACT_VIDEO_RESOLUTION = DEFAULT_VALUES["EXTRACT_VIDEO_RESOLUTION"]
        Config.EXTRACT_VIDEO_FPS = DEFAULT_VALUES["EXTRACT_VIDEO_FPS"]

        # Audio extract settings
        Config.EXTRACT_AUDIO_ENABLED = DEFAULT_VALUES["EXTRACT_AUDIO_ENABLED"]
        Config.EXTRACT_AUDIO_CODEC = DEFAULT_VALUES["EXTRACT_AUDIO_CODEC"]
        Config.EXTRACT_AUDIO_FORMAT = DEFAULT_VALUES.get(
            "EXTRACT_AUDIO_FORMAT", "none"
        )
        Config.EXTRACT_AUDIO_INDEX = DEFAULT_VALUES["EXTRACT_AUDIO_INDEX"]
        Config.EXTRACT_AUDIO_BITRATE = DEFAULT_VALUES["EXTRACT_AUDIO_BITRATE"]
        Config.EXTRACT_AUDIO_CHANNELS = DEFAULT_VALUES["EXTRACT_AUDIO_CHANNELS"]
        Config.EXTRACT_AUDIO_SAMPLING = DEFAULT_VALUES["EXTRACT_AUDIO_SAMPLING"]
        Config.EXTRACT_AUDIO_VOLUME = DEFAULT_VALUES["EXTRACT_AUDIO_VOLUME"]

        # Subtitle extract settings
        Config.EXTRACT_SUBTITLE_ENABLED = DEFAULT_VALUES["EXTRACT_SUBTITLE_ENABLED"]
        Config.EXTRACT_SUBTITLE_CODEC = DEFAULT_VALUES["EXTRACT_SUBTITLE_CODEC"]
        Config.EXTRACT_SUBTITLE_FORMAT = DEFAULT_VALUES.get(
            "EXTRACT_SUBTITLE_FORMAT", "none"
        )
        Config.EXTRACT_SUBTITLE_INDEX = DEFAULT_VALUES["EXTRACT_SUBTITLE_INDEX"]
        Config.EXTRACT_SUBTITLE_LANGUAGE = DEFAULT_VALUES[
            "EXTRACT_SUBTITLE_LANGUAGE"
        ]
        Config.EXTRACT_SUBTITLE_ENCODING = DEFAULT_VALUES[
            "EXTRACT_SUBTITLE_ENCODING"
        ]
        Config.EXTRACT_SUBTITLE_FONT = DEFAULT_VALUES["EXTRACT_SUBTITLE_FONT"]
        Config.EXTRACT_SUBTITLE_FONT_SIZE = DEFAULT_VALUES[
            "EXTRACT_SUBTITLE_FONT_SIZE"
        ]

        # Attachment extract settings
        Config.EXTRACT_ATTACHMENT_ENABLED = DEFAULT_VALUES[
            "EXTRACT_ATTACHMENT_ENABLED"
        ]
        Config.EXTRACT_ATTACHMENT_FORMAT = DEFAULT_VALUES.get(
            "EXTRACT_ATTACHMENT_FORMAT", "none"
        )
        Config.EXTRACT_ATTACHMENT_INDEX = DEFAULT_VALUES["EXTRACT_ATTACHMENT_INDEX"]
        Config.EXTRACT_ATTACHMENT_FILTER = DEFAULT_VALUES[
            "EXTRACT_ATTACHMENT_FILTER"
        ]

        # Quality settings
        Config.EXTRACT_MAINTAIN_QUALITY = DEFAULT_VALUES["EXTRACT_MAINTAIN_QUALITY"]

        # Update the database
        await database.update_config(
            {
                # General extract settings
                "EXTRACT_ENABLED": DEFAULT_VALUES["EXTRACT_ENABLED"],
                "EXTRACT_PRIORITY": DEFAULT_VALUES["EXTRACT_PRIORITY"],
                "EXTRACT_DELETE_ORIGINAL": DEFAULT_VALUES["EXTRACT_DELETE_ORIGINAL"],
                # Video extract settings
                "EXTRACT_VIDEO_ENABLED": DEFAULT_VALUES["EXTRACT_VIDEO_ENABLED"],
                "EXTRACT_VIDEO_CODEC": DEFAULT_VALUES["EXTRACT_VIDEO_CODEC"],
                "EXTRACT_VIDEO_FORMAT": DEFAULT_VALUES.get(
                    "EXTRACT_VIDEO_FORMAT", "none"
                ),
                "EXTRACT_VIDEO_INDEX": DEFAULT_VALUES["EXTRACT_VIDEO_INDEX"],
                "EXTRACT_VIDEO_QUALITY": DEFAULT_VALUES["EXTRACT_VIDEO_QUALITY"],
                "EXTRACT_VIDEO_PRESET": DEFAULT_VALUES["EXTRACT_VIDEO_PRESET"],
                "EXTRACT_VIDEO_BITRATE": DEFAULT_VALUES["EXTRACT_VIDEO_BITRATE"],
                "EXTRACT_VIDEO_RESOLUTION": DEFAULT_VALUES[
                    "EXTRACT_VIDEO_RESOLUTION"
                ],
                "EXTRACT_VIDEO_FPS": DEFAULT_VALUES["EXTRACT_VIDEO_FPS"],
                # Audio extract settings
                "EXTRACT_AUDIO_ENABLED": DEFAULT_VALUES["EXTRACT_AUDIO_ENABLED"],
                "EXTRACT_AUDIO_CODEC": DEFAULT_VALUES["EXTRACT_AUDIO_CODEC"],
                "EXTRACT_AUDIO_FORMAT": DEFAULT_VALUES.get(
                    "EXTRACT_AUDIO_FORMAT", "none"
                ),
                "EXTRACT_AUDIO_INDEX": DEFAULT_VALUES["EXTRACT_AUDIO_INDEX"],
                "EXTRACT_AUDIO_BITRATE": DEFAULT_VALUES["EXTRACT_AUDIO_BITRATE"],
                "EXTRACT_AUDIO_CHANNELS": DEFAULT_VALUES["EXTRACT_AUDIO_CHANNELS"],
                "EXTRACT_AUDIO_SAMPLING": DEFAULT_VALUES["EXTRACT_AUDIO_SAMPLING"],
                "EXTRACT_AUDIO_VOLUME": DEFAULT_VALUES["EXTRACT_AUDIO_VOLUME"],
                # Subtitle extract settings
                "EXTRACT_SUBTITLE_ENABLED": DEFAULT_VALUES[
                    "EXTRACT_SUBTITLE_ENABLED"
                ],
                "EXTRACT_SUBTITLE_CODEC": DEFAULT_VALUES["EXTRACT_SUBTITLE_CODEC"],
                "EXTRACT_SUBTITLE_FORMAT": DEFAULT_VALUES.get(
                    "EXTRACT_SUBTITLE_FORMAT", "none"
                ),
                "EXTRACT_SUBTITLE_INDEX": DEFAULT_VALUES["EXTRACT_SUBTITLE_INDEX"],
                "EXTRACT_SUBTITLE_LANGUAGE": DEFAULT_VALUES[
                    "EXTRACT_SUBTITLE_LANGUAGE"
                ],
                "EXTRACT_SUBTITLE_ENCODING": DEFAULT_VALUES[
                    "EXTRACT_SUBTITLE_ENCODING"
                ],
                "EXTRACT_SUBTITLE_FONT": DEFAULT_VALUES["EXTRACT_SUBTITLE_FONT"],
                "EXTRACT_SUBTITLE_FONT_SIZE": DEFAULT_VALUES[
                    "EXTRACT_SUBTITLE_FONT_SIZE"
                ],
                # Attachment extract settings
                "EXTRACT_ATTACHMENT_ENABLED": DEFAULT_VALUES[
                    "EXTRACT_ATTACHMENT_ENABLED"
                ],
                "EXTRACT_ATTACHMENT_FORMAT": DEFAULT_VALUES.get(
                    "EXTRACT_ATTACHMENT_FORMAT", "none"
                ),
                "EXTRACT_ATTACHMENT_INDEX": DEFAULT_VALUES[
                    "EXTRACT_ATTACHMENT_INDEX"
                ],
                "EXTRACT_ATTACHMENT_FILTER": DEFAULT_VALUES[
                    "EXTRACT_ATTACHMENT_FILTER"
                ],
                # Quality settings
                "EXTRACT_MAINTAIN_QUALITY": DEFAULT_VALUES[
                    "EXTRACT_MAINTAIN_QUALITY"
                ],
            }
        )
        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_extract")

    elif data[1] == "default_trim":
        await query.answer("Resetting all trim settings to default...")
        # Reset all trim settings to default using DEFAULT_VALUES

        # General trim settings
        Config.TRIM_ENABLED = DEFAULT_VALUES["TRIM_ENABLED"]
        Config.TRIM_PRIORITY = DEFAULT_VALUES["TRIM_PRIORITY"]
        Config.TRIM_START_TIME = DEFAULT_VALUES.get("TRIM_START_TIME", "00:00:00")
        Config.TRIM_END_TIME = DEFAULT_VALUES.get("TRIM_END_TIME", "")
        Config.TRIM_DELETE_ORIGINAL = DEFAULT_VALUES["TRIM_DELETE_ORIGINAL"]

        # Video trim settings
        Config.TRIM_VIDEO_ENABLED = DEFAULT_VALUES["TRIM_VIDEO_ENABLED"]
        Config.TRIM_VIDEO_CODEC = DEFAULT_VALUES["TRIM_VIDEO_CODEC"]
        Config.TRIM_VIDEO_PRESET = DEFAULT_VALUES["TRIM_VIDEO_PRESET"]
        Config.TRIM_VIDEO_FORMAT = DEFAULT_VALUES["TRIM_VIDEO_FORMAT"]

        # Audio trim settings
        Config.TRIM_AUDIO_ENABLED = DEFAULT_VALUES["TRIM_AUDIO_ENABLED"]
        Config.TRIM_AUDIO_CODEC = DEFAULT_VALUES["TRIM_AUDIO_CODEC"]
        Config.TRIM_AUDIO_PRESET = DEFAULT_VALUES["TRIM_AUDIO_PRESET"]
        Config.TRIM_AUDIO_FORMAT = DEFAULT_VALUES["TRIM_AUDIO_FORMAT"]

        # Image trim settings
        Config.TRIM_IMAGE_ENABLED = DEFAULT_VALUES["TRIM_IMAGE_ENABLED"]
        Config.TRIM_IMAGE_QUALITY = DEFAULT_VALUES["TRIM_IMAGE_QUALITY"]
        Config.TRIM_IMAGE_FORMAT = DEFAULT_VALUES["TRIM_IMAGE_FORMAT"]

        # Document trim settings
        Config.TRIM_DOCUMENT_ENABLED = DEFAULT_VALUES["TRIM_DOCUMENT_ENABLED"]
        Config.TRIM_DOCUMENT_START_PAGE = DEFAULT_VALUES["TRIM_DOCUMENT_START_PAGE"]
        Config.TRIM_DOCUMENT_END_PAGE = DEFAULT_VALUES["TRIM_DOCUMENT_END_PAGE"]
        Config.TRIM_DOCUMENT_QUALITY = DEFAULT_VALUES["TRIM_DOCUMENT_QUALITY"]
        Config.TRIM_DOCUMENT_FORMAT = DEFAULT_VALUES["TRIM_DOCUMENT_FORMAT"]

        # Subtitle trim settings
        Config.TRIM_SUBTITLE_ENABLED = DEFAULT_VALUES["TRIM_SUBTITLE_ENABLED"]
        Config.TRIM_SUBTITLE_ENCODING = DEFAULT_VALUES["TRIM_SUBTITLE_ENCODING"]
        Config.TRIM_SUBTITLE_FORMAT = DEFAULT_VALUES["TRIM_SUBTITLE_FORMAT"]

        # Archive trim settings
        Config.TRIM_ARCHIVE_ENABLED = DEFAULT_VALUES["TRIM_ARCHIVE_ENABLED"]
        Config.TRIM_ARCHIVE_FORMAT = DEFAULT_VALUES["TRIM_ARCHIVE_FORMAT"]

        # Update the database
        await database.update_config(
            {
                # General trim settings
                "TRIM_ENABLED": DEFAULT_VALUES["TRIM_ENABLED"],
                "TRIM_PRIORITY": DEFAULT_VALUES["TRIM_PRIORITY"],
                "TRIM_START_TIME": DEFAULT_VALUES.get("TRIM_START_TIME", "00:00:00"),
                "TRIM_END_TIME": DEFAULT_VALUES.get("TRIM_END_TIME", ""),
                "TRIM_DELETE_ORIGINAL": DEFAULT_VALUES["TRIM_DELETE_ORIGINAL"],
                # Video trim settings
                "TRIM_VIDEO_ENABLED": DEFAULT_VALUES["TRIM_VIDEO_ENABLED"],
                "TRIM_VIDEO_CODEC": DEFAULT_VALUES["TRIM_VIDEO_CODEC"],
                "TRIM_VIDEO_PRESET": DEFAULT_VALUES["TRIM_VIDEO_PRESET"],
                "TRIM_VIDEO_FORMAT": DEFAULT_VALUES["TRIM_VIDEO_FORMAT"],
                # Audio trim settings
                "TRIM_AUDIO_ENABLED": DEFAULT_VALUES["TRIM_AUDIO_ENABLED"],
                "TRIM_AUDIO_CODEC": DEFAULT_VALUES["TRIM_AUDIO_CODEC"],
                "TRIM_AUDIO_PRESET": DEFAULT_VALUES["TRIM_AUDIO_PRESET"],
                "TRIM_AUDIO_FORMAT": DEFAULT_VALUES["TRIM_AUDIO_FORMAT"],
                # Image trim settings
                "TRIM_IMAGE_ENABLED": DEFAULT_VALUES["TRIM_IMAGE_ENABLED"],
                "TRIM_IMAGE_QUALITY": DEFAULT_VALUES["TRIM_IMAGE_QUALITY"],
                "TRIM_IMAGE_FORMAT": DEFAULT_VALUES["TRIM_IMAGE_FORMAT"],
                # Document trim settings
                "TRIM_DOCUMENT_ENABLED": DEFAULT_VALUES["TRIM_DOCUMENT_ENABLED"],
                "TRIM_DOCUMENT_START_PAGE": DEFAULT_VALUES[
                    "TRIM_DOCUMENT_START_PAGE"
                ],
                "TRIM_DOCUMENT_END_PAGE": DEFAULT_VALUES["TRIM_DOCUMENT_END_PAGE"],
                "TRIM_DOCUMENT_QUALITY": DEFAULT_VALUES["TRIM_DOCUMENT_QUALITY"],
                "TRIM_DOCUMENT_FORMAT": DEFAULT_VALUES["TRIM_DOCUMENT_FORMAT"],
                # Subtitle trim settings
                "TRIM_SUBTITLE_ENABLED": DEFAULT_VALUES["TRIM_SUBTITLE_ENABLED"],
                "TRIM_SUBTITLE_ENCODING": DEFAULT_VALUES["TRIM_SUBTITLE_ENCODING"],
                "TRIM_SUBTITLE_FORMAT": DEFAULT_VALUES["TRIM_SUBTITLE_FORMAT"],
                # Archive trim settings
                "TRIM_ARCHIVE_ENABLED": DEFAULT_VALUES["TRIM_ARCHIVE_ENABLED"],
                "TRIM_ARCHIVE_FORMAT": DEFAULT_VALUES["TRIM_ARCHIVE_FORMAT"],
            }
        )
        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_trim")

    elif data[1] == "default_convert":
        await query.answer("Resetting all convert settings to default...")
        # Reset all convert settings to default using DEFAULT_VALUES

        # General convert settings
        Config.CONVERT_ENABLED = DEFAULT_VALUES["CONVERT_ENABLED"]
        Config.CONVERT_PRIORITY = DEFAULT_VALUES["CONVERT_PRIORITY"]
        Config.CONVERT_DELETE_ORIGINAL = DEFAULT_VALUES["CONVERT_DELETE_ORIGINAL"]

        # Video convert settings
        Config.CONVERT_VIDEO_ENABLED = DEFAULT_VALUES["CONVERT_VIDEO_ENABLED"]
        Config.CONVERT_VIDEO_FORMAT = DEFAULT_VALUES["CONVERT_VIDEO_FORMAT"]
        Config.CONVERT_VIDEO_CODEC = DEFAULT_VALUES["CONVERT_VIDEO_CODEC"]
        Config.CONVERT_VIDEO_QUALITY = DEFAULT_VALUES["CONVERT_VIDEO_QUALITY"]
        Config.CONVERT_VIDEO_CRF = DEFAULT_VALUES["CONVERT_VIDEO_CRF"]
        Config.CONVERT_VIDEO_PRESET = DEFAULT_VALUES["CONVERT_VIDEO_PRESET"]
        Config.CONVERT_VIDEO_MAINTAIN_QUALITY = DEFAULT_VALUES[
            "CONVERT_VIDEO_MAINTAIN_QUALITY"
        ]
        Config.CONVERT_VIDEO_RESOLUTION = DEFAULT_VALUES["CONVERT_VIDEO_RESOLUTION"]
        Config.CONVERT_VIDEO_FPS = DEFAULT_VALUES["CONVERT_VIDEO_FPS"]
        Config.CONVERT_VIDEO_DELETE_ORIGINAL = DEFAULT_VALUES[
            "CONVERT_VIDEO_DELETE_ORIGINAL"
        ]

        # Audio convert settings
        Config.CONVERT_AUDIO_ENABLED = DEFAULT_VALUES["CONVERT_AUDIO_ENABLED"]
        Config.CONVERT_AUDIO_FORMAT = DEFAULT_VALUES["CONVERT_AUDIO_FORMAT"]
        Config.CONVERT_AUDIO_CODEC = DEFAULT_VALUES["CONVERT_AUDIO_CODEC"]
        Config.CONVERT_AUDIO_BITRATE = DEFAULT_VALUES["CONVERT_AUDIO_BITRATE"]
        Config.CONVERT_AUDIO_CHANNELS = DEFAULT_VALUES["CONVERT_AUDIO_CHANNELS"]
        Config.CONVERT_AUDIO_SAMPLING = DEFAULT_VALUES["CONVERT_AUDIO_SAMPLING"]
        Config.CONVERT_AUDIO_VOLUME = DEFAULT_VALUES["CONVERT_AUDIO_VOLUME"]
        Config.CONVERT_AUDIO_DELETE_ORIGINAL = DEFAULT_VALUES[
            "CONVERT_AUDIO_DELETE_ORIGINAL"
        ]

        # Subtitle convert settings
        Config.CONVERT_SUBTITLE_ENABLED = DEFAULT_VALUES["CONVERT_SUBTITLE_ENABLED"]
        Config.CONVERT_SUBTITLE_FORMAT = DEFAULT_VALUES["CONVERT_SUBTITLE_FORMAT"]
        Config.CONVERT_SUBTITLE_ENCODING = DEFAULT_VALUES[
            "CONVERT_SUBTITLE_ENCODING"
        ]
        Config.CONVERT_SUBTITLE_LANGUAGE = DEFAULT_VALUES[
            "CONVERT_SUBTITLE_LANGUAGE"
        ]
        Config.CONVERT_SUBTITLE_DELETE_ORIGINAL = DEFAULT_VALUES[
            "CONVERT_SUBTITLE_DELETE_ORIGINAL"
        ]

        # Document convert settings
        Config.CONVERT_DOCUMENT_ENABLED = DEFAULT_VALUES["CONVERT_DOCUMENT_ENABLED"]
        Config.CONVERT_DOCUMENT_FORMAT = DEFAULT_VALUES["CONVERT_DOCUMENT_FORMAT"]
        Config.CONVERT_DOCUMENT_QUALITY = DEFAULT_VALUES["CONVERT_DOCUMENT_QUALITY"]
        Config.CONVERT_DOCUMENT_DPI = DEFAULT_VALUES["CONVERT_DOCUMENT_DPI"]
        Config.CONVERT_DOCUMENT_DELETE_ORIGINAL = DEFAULT_VALUES[
            "CONVERT_DOCUMENT_DELETE_ORIGINAL"
        ]

        # Archive convert settings
        Config.CONVERT_ARCHIVE_ENABLED = DEFAULT_VALUES["CONVERT_ARCHIVE_ENABLED"]
        Config.CONVERT_ARCHIVE_FORMAT = DEFAULT_VALUES["CONVERT_ARCHIVE_FORMAT"]
        Config.CONVERT_ARCHIVE_LEVEL = DEFAULT_VALUES["CONVERT_ARCHIVE_LEVEL"]
        Config.CONVERT_ARCHIVE_METHOD = DEFAULT_VALUES["CONVERT_ARCHIVE_METHOD"]
        Config.CONVERT_ARCHIVE_DELETE_ORIGINAL = DEFAULT_VALUES[
            "CONVERT_ARCHIVE_DELETE_ORIGINAL"
        ]

        # Update the database
        await database.update_config(
            {
                # General convert settings
                "CONVERT_ENABLED": DEFAULT_VALUES["CONVERT_ENABLED"],
                "CONVERT_PRIORITY": DEFAULT_VALUES["CONVERT_PRIORITY"],
                "CONVERT_DELETE_ORIGINAL": DEFAULT_VALUES["CONVERT_DELETE_ORIGINAL"],
                # Video convert settings
                "CONVERT_VIDEO_ENABLED": DEFAULT_VALUES["CONVERT_VIDEO_ENABLED"],
                "CONVERT_VIDEO_FORMAT": DEFAULT_VALUES["CONVERT_VIDEO_FORMAT"],
                "CONVERT_VIDEO_CODEC": DEFAULT_VALUES["CONVERT_VIDEO_CODEC"],
                "CONVERT_VIDEO_QUALITY": DEFAULT_VALUES["CONVERT_VIDEO_QUALITY"],
                "CONVERT_VIDEO_CRF": DEFAULT_VALUES["CONVERT_VIDEO_CRF"],
                "CONVERT_VIDEO_PRESET": DEFAULT_VALUES["CONVERT_VIDEO_PRESET"],
                "CONVERT_VIDEO_MAINTAIN_QUALITY": DEFAULT_VALUES[
                    "CONVERT_VIDEO_MAINTAIN_QUALITY"
                ],
                "CONVERT_VIDEO_RESOLUTION": DEFAULT_VALUES[
                    "CONVERT_VIDEO_RESOLUTION"
                ],
                "CONVERT_VIDEO_FPS": DEFAULT_VALUES["CONVERT_VIDEO_FPS"],
                "CONVERT_VIDEO_DELETE_ORIGINAL": DEFAULT_VALUES[
                    "CONVERT_VIDEO_DELETE_ORIGINAL"
                ],
                # Audio convert settings
                "CONVERT_AUDIO_ENABLED": DEFAULT_VALUES["CONVERT_AUDIO_ENABLED"],
                "CONVERT_AUDIO_FORMAT": DEFAULT_VALUES["CONVERT_AUDIO_FORMAT"],
                "CONVERT_AUDIO_CODEC": DEFAULT_VALUES["CONVERT_AUDIO_CODEC"],
                "CONVERT_AUDIO_BITRATE": DEFAULT_VALUES["CONVERT_AUDIO_BITRATE"],
                "CONVERT_AUDIO_CHANNELS": DEFAULT_VALUES["CONVERT_AUDIO_CHANNELS"],
                "CONVERT_AUDIO_SAMPLING": DEFAULT_VALUES["CONVERT_AUDIO_SAMPLING"],
                "CONVERT_AUDIO_VOLUME": DEFAULT_VALUES["CONVERT_AUDIO_VOLUME"],
                "CONVERT_AUDIO_DELETE_ORIGINAL": DEFAULT_VALUES[
                    "CONVERT_AUDIO_DELETE_ORIGINAL"
                ],
                # Subtitle convert settings
                "CONVERT_SUBTITLE_ENABLED": DEFAULT_VALUES[
                    "CONVERT_SUBTITLE_ENABLED"
                ],
                "CONVERT_SUBTITLE_FORMAT": DEFAULT_VALUES["CONVERT_SUBTITLE_FORMAT"],
                "CONVERT_SUBTITLE_ENCODING": DEFAULT_VALUES[
                    "CONVERT_SUBTITLE_ENCODING"
                ],
                "CONVERT_SUBTITLE_LANGUAGE": DEFAULT_VALUES[
                    "CONVERT_SUBTITLE_LANGUAGE"
                ],
                "CONVERT_SUBTITLE_DELETE_ORIGINAL": DEFAULT_VALUES[
                    "CONVERT_SUBTITLE_DELETE_ORIGINAL"
                ],
                # Document convert settings
                "CONVERT_DOCUMENT_ENABLED": DEFAULT_VALUES[
                    "CONVERT_DOCUMENT_ENABLED"
                ],
                "CONVERT_DOCUMENT_FORMAT": DEFAULT_VALUES["CONVERT_DOCUMENT_FORMAT"],
                "CONVERT_DOCUMENT_QUALITY": DEFAULT_VALUES[
                    "CONVERT_DOCUMENT_QUALITY"
                ],
                "CONVERT_DOCUMENT_DPI": DEFAULT_VALUES["CONVERT_DOCUMENT_DPI"],
                "CONVERT_DOCUMENT_DELETE_ORIGINAL": DEFAULT_VALUES[
                    "CONVERT_DOCUMENT_DELETE_ORIGINAL"
                ],
                # Archive convert settings
                "CONVERT_ARCHIVE_ENABLED": DEFAULT_VALUES["CONVERT_ARCHIVE_ENABLED"],
                "CONVERT_ARCHIVE_FORMAT": DEFAULT_VALUES["CONVERT_ARCHIVE_FORMAT"],
                "CONVERT_ARCHIVE_LEVEL": DEFAULT_VALUES["CONVERT_ARCHIVE_LEVEL"],
                "CONVERT_ARCHIVE_METHOD": DEFAULT_VALUES["CONVERT_ARCHIVE_METHOD"],
                "CONVERT_ARCHIVE_DELETE_ORIGINAL": DEFAULT_VALUES[
                    "CONVERT_ARCHIVE_DELETE_ORIGINAL"
                ],
            }
        )
        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_convert")

    elif data[1] == "default_add":
        await query.answer("Resetting all add settings to default...")
        # Reset all add settings to default using DEFAULT_VALUES

        # Create a dictionary of all ADD_ settings from DEFAULT_VALUES
        add_settings = {
            key: value
            for key, value in DEFAULT_VALUES.items()
            if key.startswith("ADD_")
        }

        # Reset general add settings
        Config.ADD_ENABLED = DEFAULT_VALUES["ADD_ENABLED"]
        Config.ADD_PRIORITY = DEFAULT_VALUES["ADD_PRIORITY"]
        Config.ADD_DELETE_ORIGINAL = DEFAULT_VALUES["ADD_DELETE_ORIGINAL"]
        Config.ADD_PRESERVE_TRACKS = DEFAULT_VALUES["ADD_PRESERVE_TRACKS"]
        Config.ADD_REPLACE_TRACKS = DEFAULT_VALUES["ADD_REPLACE_TRACKS"]

    elif data[1] == "default_remove":
        await query.answer("Resetting all remove settings to default...")
        # Reset all remove settings to default using DEFAULT_VALUES

        # General remove settings
        Config.REMOVE_ENABLED = DEFAULT_VALUES["REMOVE_ENABLED"]
        Config.REMOVE_PRIORITY = DEFAULT_VALUES["REMOVE_PRIORITY"]
        Config.REMOVE_DELETE_ORIGINAL = DEFAULT_VALUES["REMOVE_DELETE_ORIGINAL"]
        Config.REMOVE_METADATA = DEFAULT_VALUES["REMOVE_METADATA"]
        Config.REMOVE_MAINTAIN_QUALITY = DEFAULT_VALUES["REMOVE_MAINTAIN_QUALITY"]

        # Video remove settings
        Config.REMOVE_VIDEO_ENABLED = DEFAULT_VALUES["REMOVE_VIDEO_ENABLED"]
        Config.REMOVE_VIDEO_CODEC = DEFAULT_VALUES["REMOVE_VIDEO_CODEC"]
        Config.REMOVE_VIDEO_FORMAT = DEFAULT_VALUES["REMOVE_VIDEO_FORMAT"]
        Config.REMOVE_VIDEO_INDEX = DEFAULT_VALUES["REMOVE_VIDEO_INDEX"]
        Config.REMOVE_VIDEO_QUALITY = DEFAULT_VALUES["REMOVE_VIDEO_QUALITY"]
        Config.REMOVE_VIDEO_PRESET = DEFAULT_VALUES["REMOVE_VIDEO_PRESET"]
        Config.REMOVE_VIDEO_BITRATE = DEFAULT_VALUES["REMOVE_VIDEO_BITRATE"]
        Config.REMOVE_VIDEO_RESOLUTION = DEFAULT_VALUES["REMOVE_VIDEO_RESOLUTION"]
        Config.REMOVE_VIDEO_FPS = DEFAULT_VALUES["REMOVE_VIDEO_FPS"]

        # Audio remove settings
        Config.REMOVE_AUDIO_ENABLED = DEFAULT_VALUES["REMOVE_AUDIO_ENABLED"]
        Config.REMOVE_AUDIO_CODEC = DEFAULT_VALUES["REMOVE_AUDIO_CODEC"]
        Config.REMOVE_AUDIO_FORMAT = DEFAULT_VALUES["REMOVE_AUDIO_FORMAT"]
        Config.REMOVE_AUDIO_INDEX = DEFAULT_VALUES["REMOVE_AUDIO_INDEX"]
        Config.REMOVE_AUDIO_BITRATE = DEFAULT_VALUES["REMOVE_AUDIO_BITRATE"]
        Config.REMOVE_AUDIO_CHANNELS = DEFAULT_VALUES["REMOVE_AUDIO_CHANNELS"]
        Config.REMOVE_AUDIO_SAMPLING = DEFAULT_VALUES["REMOVE_AUDIO_SAMPLING"]
        Config.REMOVE_AUDIO_VOLUME = DEFAULT_VALUES["REMOVE_AUDIO_VOLUME"]

        # Subtitle remove settings
        Config.REMOVE_SUBTITLE_ENABLED = DEFAULT_VALUES["REMOVE_SUBTITLE_ENABLED"]
        Config.REMOVE_SUBTITLE_CODEC = DEFAULT_VALUES["REMOVE_SUBTITLE_CODEC"]
        Config.REMOVE_SUBTITLE_FORMAT = DEFAULT_VALUES["REMOVE_SUBTITLE_FORMAT"]
        Config.REMOVE_SUBTITLE_INDEX = DEFAULT_VALUES["REMOVE_SUBTITLE_INDEX"]
        Config.REMOVE_SUBTITLE_LANGUAGE = DEFAULT_VALUES["REMOVE_SUBTITLE_LANGUAGE"]
        Config.REMOVE_SUBTITLE_ENCODING = DEFAULT_VALUES["REMOVE_SUBTITLE_ENCODING"]
        Config.REMOVE_SUBTITLE_FONT = DEFAULT_VALUES["REMOVE_SUBTITLE_FONT"]
        Config.REMOVE_SUBTITLE_FONT_SIZE = DEFAULT_VALUES[
            "REMOVE_SUBTITLE_FONT_SIZE"
        ]

        # Attachment remove settings
        Config.REMOVE_ATTACHMENT_ENABLED = DEFAULT_VALUES[
            "REMOVE_ATTACHMENT_ENABLED"
        ]
        Config.REMOVE_ATTACHMENT_FORMAT = DEFAULT_VALUES["REMOVE_ATTACHMENT_FORMAT"]
        Config.REMOVE_ATTACHMENT_INDEX = DEFAULT_VALUES["REMOVE_ATTACHMENT_INDEX"]
        Config.REMOVE_ATTACHMENT_FILTER = DEFAULT_VALUES["REMOVE_ATTACHMENT_FILTER"]

        # Update the database with all remove settings
        await database.update_config(
            {
                # General remove settings
                "REMOVE_ENABLED": DEFAULT_VALUES["REMOVE_ENABLED"],
                "REMOVE_PRIORITY": DEFAULT_VALUES["REMOVE_PRIORITY"],
                "REMOVE_DELETE_ORIGINAL": DEFAULT_VALUES["REMOVE_DELETE_ORIGINAL"],
                "REMOVE_METADATA": DEFAULT_VALUES["REMOVE_METADATA"],
                "REMOVE_MAINTAIN_QUALITY": DEFAULT_VALUES["REMOVE_MAINTAIN_QUALITY"],
                # Video remove settings
                "REMOVE_VIDEO_ENABLED": DEFAULT_VALUES["REMOVE_VIDEO_ENABLED"],
                "REMOVE_VIDEO_CODEC": DEFAULT_VALUES["REMOVE_VIDEO_CODEC"],
                "REMOVE_VIDEO_FORMAT": DEFAULT_VALUES["REMOVE_VIDEO_FORMAT"],
                "REMOVE_VIDEO_INDEX": DEFAULT_VALUES["REMOVE_VIDEO_INDEX"],
                "REMOVE_VIDEO_QUALITY": DEFAULT_VALUES["REMOVE_VIDEO_QUALITY"],
                "REMOVE_VIDEO_PRESET": DEFAULT_VALUES["REMOVE_VIDEO_PRESET"],
                "REMOVE_VIDEO_BITRATE": DEFAULT_VALUES["REMOVE_VIDEO_BITRATE"],
                "REMOVE_VIDEO_RESOLUTION": DEFAULT_VALUES["REMOVE_VIDEO_RESOLUTION"],
                "REMOVE_VIDEO_FPS": DEFAULT_VALUES["REMOVE_VIDEO_FPS"],
                # Audio remove settings
                "REMOVE_AUDIO_ENABLED": DEFAULT_VALUES["REMOVE_AUDIO_ENABLED"],
                "REMOVE_AUDIO_CODEC": DEFAULT_VALUES["REMOVE_AUDIO_CODEC"],
                "REMOVE_AUDIO_FORMAT": DEFAULT_VALUES["REMOVE_AUDIO_FORMAT"],
                "REMOVE_AUDIO_INDEX": DEFAULT_VALUES["REMOVE_AUDIO_INDEX"],
                "REMOVE_AUDIO_BITRATE": DEFAULT_VALUES["REMOVE_AUDIO_BITRATE"],
                "REMOVE_AUDIO_CHANNELS": DEFAULT_VALUES["REMOVE_AUDIO_CHANNELS"],
                "REMOVE_AUDIO_SAMPLING": DEFAULT_VALUES["REMOVE_AUDIO_SAMPLING"],
                "REMOVE_AUDIO_VOLUME": DEFAULT_VALUES["REMOVE_AUDIO_VOLUME"],
                # Subtitle remove settings
                "REMOVE_SUBTITLE_ENABLED": DEFAULT_VALUES["REMOVE_SUBTITLE_ENABLED"],
                "REMOVE_SUBTITLE_CODEC": DEFAULT_VALUES["REMOVE_SUBTITLE_CODEC"],
                "REMOVE_SUBTITLE_FORMAT": DEFAULT_VALUES["REMOVE_SUBTITLE_FORMAT"],
                "REMOVE_SUBTITLE_INDEX": DEFAULT_VALUES["REMOVE_SUBTITLE_INDEX"],
                "REMOVE_SUBTITLE_LANGUAGE": DEFAULT_VALUES[
                    "REMOVE_SUBTITLE_LANGUAGE"
                ],
                "REMOVE_SUBTITLE_ENCODING": DEFAULT_VALUES[
                    "REMOVE_SUBTITLE_ENCODING"
                ],
                "REMOVE_SUBTITLE_FONT": DEFAULT_VALUES["REMOVE_SUBTITLE_FONT"],
                "REMOVE_SUBTITLE_FONT_SIZE": DEFAULT_VALUES[
                    "REMOVE_SUBTITLE_FONT_SIZE"
                ],
                # Attachment remove settings
                "REMOVE_ATTACHMENT_ENABLED": DEFAULT_VALUES[
                    "REMOVE_ATTACHMENT_ENABLED"
                ],
                "REMOVE_ATTACHMENT_FORMAT": DEFAULT_VALUES[
                    "REMOVE_ATTACHMENT_FORMAT"
                ],
                "REMOVE_ATTACHMENT_INDEX": DEFAULT_VALUES["REMOVE_ATTACHMENT_INDEX"],
                "REMOVE_ATTACHMENT_FILTER": DEFAULT_VALUES[
                    "REMOVE_ATTACHMENT_FILTER"
                ],
            }
        )

        # Get the current state before making changes
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_remove")

    elif data[1] == "default_add_setting":
        # Get the current state before making changes
        current_state = globals()["state"]

        # Reset the specific ADD_ setting to its default value
        setting_key = data[2]
        default_value = DEFAULT_VALUES.get(setting_key)

        if default_value is not None:
            # Update the Config class
            Config.set(setting_key, default_value)

            # Update the database
            await database.update_config({setting_key: default_value})

            # Show a success message
            await query.answer(
                f"Reset {setting_key} to default value: {default_value}",
                show_alert=True,
            )

        # Return to the Add settings menu - maintain the edit state
        globals()["state"] = "edit"
        await update_buttons(message, "mediatools_add")

        # Reset video add settings
        Config.ADD_VIDEO_ENABLED = DEFAULT_VALUES["ADD_VIDEO_ENABLED"]
        Config.ADD_VIDEO_CODEC = DEFAULT_VALUES["ADD_VIDEO_CODEC"]
        Config.ADD_VIDEO_INDEX = DEFAULT_VALUES["ADD_VIDEO_INDEX"]
        Config.ADD_VIDEO_QUALITY = DEFAULT_VALUES["ADD_VIDEO_QUALITY"]
        Config.ADD_VIDEO_PRESET = DEFAULT_VALUES["ADD_VIDEO_PRESET"]
        Config.ADD_VIDEO_BITRATE = DEFAULT_VALUES["ADD_VIDEO_BITRATE"]
        Config.ADD_VIDEO_RESOLUTION = DEFAULT_VALUES["ADD_VIDEO_RESOLUTION"]
        Config.ADD_VIDEO_FPS = DEFAULT_VALUES["ADD_VIDEO_FPS"]

        # Reset audio add settings
        Config.ADD_AUDIO_ENABLED = DEFAULT_VALUES["ADD_AUDIO_ENABLED"]
        Config.ADD_AUDIO_CODEC = DEFAULT_VALUES["ADD_AUDIO_CODEC"]
        Config.ADD_AUDIO_INDEX = DEFAULT_VALUES["ADD_AUDIO_INDEX"]
        Config.ADD_AUDIO_BITRATE = DEFAULT_VALUES["ADD_AUDIO_BITRATE"]
        Config.ADD_AUDIO_CHANNELS = DEFAULT_VALUES["ADD_AUDIO_CHANNELS"]
        Config.ADD_AUDIO_SAMPLING = DEFAULT_VALUES["ADD_AUDIO_SAMPLING"]
        Config.ADD_AUDIO_VOLUME = DEFAULT_VALUES["ADD_AUDIO_VOLUME"]

        # Reset subtitle add settings
        Config.ADD_SUBTITLE_ENABLED = DEFAULT_VALUES["ADD_SUBTITLE_ENABLED"]
        Config.ADD_SUBTITLE_CODEC = DEFAULT_VALUES["ADD_SUBTITLE_CODEC"]
        Config.ADD_SUBTITLE_INDEX = DEFAULT_VALUES["ADD_SUBTITLE_INDEX"]
        Config.ADD_SUBTITLE_LANGUAGE = DEFAULT_VALUES["ADD_SUBTITLE_LANGUAGE"]
        Config.ADD_SUBTITLE_ENCODING = DEFAULT_VALUES["ADD_SUBTITLE_ENCODING"]
        Config.ADD_SUBTITLE_FONT = DEFAULT_VALUES["ADD_SUBTITLE_FONT"]
        Config.ADD_SUBTITLE_FONT_SIZE = DEFAULT_VALUES["ADD_SUBTITLE_FONT_SIZE"]
        Config.ADD_SUBTITLE_HARDSUB_ENABLED = DEFAULT_VALUES[
            "ADD_SUBTITLE_HARDSUB_ENABLED"
        ]

        # Reset attachment add settings
        Config.ADD_ATTACHMENT_ENABLED = DEFAULT_VALUES["ADD_ATTACHMENT_ENABLED"]
        Config.ADD_ATTACHMENT_INDEX = DEFAULT_VALUES["ADD_ATTACHMENT_INDEX"]
        Config.ADD_ATTACHMENT_MIMETYPE = DEFAULT_VALUES["ADD_ATTACHMENT_MIMETYPE"]

        # Log the settings being reset

        # Update the database with all ADD_ settings
        await database.update_config(add_settings)

        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state

        # Force a refresh of the UI to ensure the toggle buttons show the correct state
        await update_buttons(message, "mediatools_add")

    elif data[1] == "default_swap":
        await query.answer("Resetting all swap settings to default...")
        # Reset all swap settings to default using DEFAULT_VALUES

        # General swap settings
        Config.SWAP_ENABLED = DEFAULT_VALUES["SWAP_ENABLED"]
        Config.SWAP_PRIORITY = DEFAULT_VALUES["SWAP_PRIORITY"]
        Config.SWAP_REMOVE_ORIGINAL = DEFAULT_VALUES["SWAP_REMOVE_ORIGINAL"]

        # Audio swap settings
        Config.SWAP_AUDIO_ENABLED = DEFAULT_VALUES["SWAP_AUDIO_ENABLED"]
        Config.SWAP_AUDIO_USE_LANGUAGE = DEFAULT_VALUES["SWAP_AUDIO_USE_LANGUAGE"]
        Config.SWAP_AUDIO_LANGUAGE_ORDER = DEFAULT_VALUES[
            "SWAP_AUDIO_LANGUAGE_ORDER"
        ]
        Config.SWAP_AUDIO_INDEX_ORDER = DEFAULT_VALUES["SWAP_AUDIO_INDEX_ORDER"]

        # Video swap settings
        Config.SWAP_VIDEO_ENABLED = DEFAULT_VALUES["SWAP_VIDEO_ENABLED"]
        Config.SWAP_VIDEO_USE_LANGUAGE = DEFAULT_VALUES["SWAP_VIDEO_USE_LANGUAGE"]
        Config.SWAP_VIDEO_LANGUAGE_ORDER = DEFAULT_VALUES[
            "SWAP_VIDEO_LANGUAGE_ORDER"
        ]
        Config.SWAP_VIDEO_INDEX_ORDER = DEFAULT_VALUES["SWAP_VIDEO_INDEX_ORDER"]

        # Subtitle swap settings
        Config.SWAP_SUBTITLE_ENABLED = DEFAULT_VALUES["SWAP_SUBTITLE_ENABLED"]
        Config.SWAP_SUBTITLE_USE_LANGUAGE = DEFAULT_VALUES[
            "SWAP_SUBTITLE_USE_LANGUAGE"
        ]
        Config.SWAP_SUBTITLE_LANGUAGE_ORDER = DEFAULT_VALUES[
            "SWAP_SUBTITLE_LANGUAGE_ORDER"
        ]
        Config.SWAP_SUBTITLE_INDEX_ORDER = DEFAULT_VALUES[
            "SWAP_SUBTITLE_INDEX_ORDER"
        ]

        # Create a dictionary of all SWAP_ settings from DEFAULT_VALUES
        swap_settings = {
            key: value
            for key, value in DEFAULT_VALUES.items()
            if key.startswith("SWAP_")
        }

        # Update the database with all SWAP_ settings
        await database.update_config(swap_settings)

        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_swap")

    elif data[1] == "default_metadata":
        await query.answer("Resetting all metadata settings to default...")
        # Reset all metadata settings to default
        Config.METADATA_KEY = ""
        Config.METADATA_ALL = ""
        Config.METADATA_TITLE = ""
        Config.METADATA_AUTHOR = ""
        Config.METADATA_COMMENT = ""

        # Reset video metadata settings
        Config.METADATA_VIDEO_TITLE = ""
        Config.METADATA_VIDEO_AUTHOR = ""
        Config.METADATA_VIDEO_COMMENT = ""

        # Reset audio metadata settings
        Config.METADATA_AUDIO_TITLE = ""
        Config.METADATA_AUDIO_AUTHOR = ""
        Config.METADATA_AUDIO_COMMENT = ""

        # Reset subtitle metadata settings
        Config.METADATA_SUBTITLE_TITLE = ""
        Config.METADATA_SUBTITLE_AUTHOR = ""
        Config.METADATA_SUBTITLE_COMMENT = ""

        # Update the database
        await database.update_config(
            {
                "METADATA_KEY": "",
                "METADATA_ALL": "",
                "METADATA_TITLE": "",
                "METADATA_AUTHOR": "",
                "METADATA_COMMENT": "",
                "METADATA_VIDEO_TITLE": "",
                "METADATA_VIDEO_AUTHOR": "",
                "METADATA_VIDEO_COMMENT": "",
                "METADATA_AUDIO_TITLE": "",
                "METADATA_AUDIO_AUTHOR": "",
                "METADATA_AUDIO_COMMENT": "",
                "METADATA_SUBTITLE_TITLE": "",
                "METADATA_SUBTITLE_AUTHOR": "",
                "METADATA_SUBTITLE_COMMENT": "",
            }
        )
        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "mediatools_metadata")

    elif data[1] == "default_streamrip_general":
        await query.answer("Resetting streamrip general settings to default...")
        # Reset streamrip general settings to default
        Config.STREAMRIP_ENABLED = DEFAULT_VALUES.get("STREAMRIP_ENABLED", True)
        Config.STREAMRIP_CONCURRENT_DOWNLOADS = DEFAULT_VALUES.get(
            "STREAMRIP_CONCURRENT_DOWNLOADS", 4
        )
        Config.STREAMRIP_MAX_SEARCH_RESULTS = DEFAULT_VALUES.get(
            "STREAMRIP_MAX_SEARCH_RESULTS", 20
        )
        Config.STREAMRIP_ENABLE_DATABASE = DEFAULT_VALUES.get(
            "STREAMRIP_ENABLE_DATABASE", False
        )
        Config.STREAMRIP_AUTO_CONVERT = DEFAULT_VALUES.get(
            "STREAMRIP_AUTO_CONVERT", False
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_ENABLED": Config.STREAMRIP_ENABLED,
                "STREAMRIP_CONCURRENT_DOWNLOADS": Config.STREAMRIP_CONCURRENT_DOWNLOADS,
                "STREAMRIP_MAX_SEARCH_RESULTS": Config.STREAMRIP_MAX_SEARCH_RESULTS,
                "STREAMRIP_ENABLE_DATABASE": Config.STREAMRIP_ENABLE_DATABASE,
                "STREAMRIP_AUTO_CONVERT": Config.STREAMRIP_AUTO_CONVERT,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_general")

    elif data[1] == "default_streamrip_quality":
        await query.answer("Resetting streamrip quality settings to default...")
        # Reset streamrip quality settings to default
        Config.STREAMRIP_DEFAULT_QUALITY = DEFAULT_VALUES.get(
            "STREAMRIP_DEFAULT_QUALITY", 3
        )
        Config.STREAMRIP_FALLBACK_QUALITY = DEFAULT_VALUES.get(
            "STREAMRIP_FALLBACK_QUALITY", 2
        )
        Config.STREAMRIP_DEFAULT_CODEC = DEFAULT_VALUES.get(
            "STREAMRIP_DEFAULT_CODEC", "flac"
        )
        Config.STREAMRIP_QUALITY_FALLBACK_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_QUALITY_FALLBACK_ENABLED", False
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_DEFAULT_QUALITY": Config.STREAMRIP_DEFAULT_QUALITY,
                "STREAMRIP_FALLBACK_QUALITY": Config.STREAMRIP_FALLBACK_QUALITY,
                "STREAMRIP_DEFAULT_CODEC": Config.STREAMRIP_DEFAULT_CODEC,
                "STREAMRIP_QUALITY_FALLBACK_ENABLED": Config.STREAMRIP_QUALITY_FALLBACK_ENABLED,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_quality")

    elif data[1] == "default_streamrip_credentials":
        await query.answer("Resetting streamrip credentials to default...")
        # Reset streamrip credentials to default
        Config.STREAMRIP_QOBUZ_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_ENABLED", False
        )
        Config.STREAMRIP_QOBUZ_EMAIL = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_EMAIL", ""
        )
        Config.STREAMRIP_QOBUZ_PASSWORD = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_PASSWORD", ""
        )
        Config.STREAMRIP_QOBUZ_USE_AUTH_TOKEN = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_USE_AUTH_TOKEN", False
        )
        Config.STREAMRIP_QOBUZ_APP_ID = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_APP_ID", ""
        )
        Config.STREAMRIP_QOBUZ_SECRETS = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_SECRETS", []
        )
        Config.STREAMRIP_QOBUZ_QUALITY = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_QUALITY", 3
        )
        Config.STREAMRIP_TIDAL_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_ENABLED", False
        )
        Config.STREAMRIP_TIDAL_EMAIL = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_EMAIL", ""
        )
        Config.STREAMRIP_TIDAL_PASSWORD = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_PASSWORD", ""
        )
        Config.STREAMRIP_TIDAL_ACCESS_TOKEN = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_ACCESS_TOKEN", ""
        )
        Config.STREAMRIP_TIDAL_REFRESH_TOKEN = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_REFRESH_TOKEN", ""
        )
        Config.STREAMRIP_TIDAL_USER_ID = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_USER_ID", ""
        )
        Config.STREAMRIP_TIDAL_COUNTRY_CODE = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_COUNTRY_CODE", ""
        )
        Config.STREAMRIP_TIDAL_QUALITY = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_QUALITY", 3
        )
        Config.STREAMRIP_DEEZER_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_DEEZER_ENABLED", False
        )
        Config.STREAMRIP_DEEZER_ARL = DEFAULT_VALUES.get("STREAMRIP_DEEZER_ARL", "")
        Config.STREAMRIP_DEEZER_QUALITY = DEFAULT_VALUES.get(
            "STREAMRIP_DEEZER_QUALITY", 2
        )
        Config.STREAMRIP_SOUNDCLOUD_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_SOUNDCLOUD_ENABLED", False
        )
        Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID = DEFAULT_VALUES.get(
            "STREAMRIP_SOUNDCLOUD_CLIENT_ID", ""
        )
        Config.STREAMRIP_SOUNDCLOUD_QUALITY = DEFAULT_VALUES.get(
            "STREAMRIP_SOUNDCLOUD_QUALITY", 0
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_QOBUZ_ENABLED": Config.STREAMRIP_QOBUZ_ENABLED,
                "STREAMRIP_QOBUZ_EMAIL": Config.STREAMRIP_QOBUZ_EMAIL,
                "STREAMRIP_QOBUZ_PASSWORD": Config.STREAMRIP_QOBUZ_PASSWORD,
                "STREAMRIP_QOBUZ_USE_AUTH_TOKEN": Config.STREAMRIP_QOBUZ_USE_AUTH_TOKEN,
                "STREAMRIP_QOBUZ_APP_ID": Config.STREAMRIP_QOBUZ_APP_ID,
                "STREAMRIP_QOBUZ_SECRETS": Config.STREAMRIP_QOBUZ_SECRETS,
                "STREAMRIP_QOBUZ_QUALITY": Config.STREAMRIP_QOBUZ_QUALITY,
                "STREAMRIP_TIDAL_ENABLED": Config.STREAMRIP_TIDAL_ENABLED,
                "STREAMRIP_TIDAL_EMAIL": Config.STREAMRIP_TIDAL_EMAIL,
                "STREAMRIP_TIDAL_PASSWORD": Config.STREAMRIP_TIDAL_PASSWORD,
                "STREAMRIP_TIDAL_ACCESS_TOKEN": Config.STREAMRIP_TIDAL_ACCESS_TOKEN,
                "STREAMRIP_TIDAL_REFRESH_TOKEN": Config.STREAMRIP_TIDAL_REFRESH_TOKEN,
                "STREAMRIP_TIDAL_USER_ID": Config.STREAMRIP_TIDAL_USER_ID,
                "STREAMRIP_TIDAL_COUNTRY_CODE": Config.STREAMRIP_TIDAL_COUNTRY_CODE,
                "STREAMRIP_TIDAL_QUALITY": Config.STREAMRIP_TIDAL_QUALITY,
                "STREAMRIP_DEEZER_ENABLED": Config.STREAMRIP_DEEZER_ENABLED,
                "STREAMRIP_DEEZER_ARL": Config.STREAMRIP_DEEZER_ARL,
                "STREAMRIP_DEEZER_QUALITY": Config.STREAMRIP_DEEZER_QUALITY,
                "STREAMRIP_SOUNDCLOUD_ENABLED": Config.STREAMRIP_SOUNDCLOUD_ENABLED,
                "STREAMRIP_SOUNDCLOUD_CLIENT_ID": Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID,
                "STREAMRIP_SOUNDCLOUD_QUALITY": Config.STREAMRIP_SOUNDCLOUD_QUALITY,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_credentials")

    elif data[1] == "default_streamrip_download":
        await query.answer("Resetting streamrip download settings to default...")
        # Reset streamrip download settings to default
        Config.STREAMRIP_CONCURRENT_DOWNLOADS = DEFAULT_VALUES.get(
            "STREAMRIP_CONCURRENT_DOWNLOADS", 4
        )
        Config.STREAMRIP_MAX_SEARCH_RESULTS = DEFAULT_VALUES.get(
            "STREAMRIP_MAX_SEARCH_RESULTS", 20
        )
        Config.STREAMRIP_MAX_CONNECTIONS = DEFAULT_VALUES.get(
            "STREAMRIP_MAX_CONNECTIONS", 6
        )
        Config.STREAMRIP_REQUESTS_PER_MINUTE = DEFAULT_VALUES.get(
            "STREAMRIP_REQUESTS_PER_MINUTE", 60
        )
        Config.STREAMRIP_SOURCE_SUBDIRECTORIES = DEFAULT_VALUES.get(
            "STREAMRIP_SOURCE_SUBDIRECTORIES", False
        )
        Config.STREAMRIP_DISC_SUBDIRECTORIES = DEFAULT_VALUES.get(
            "STREAMRIP_DISC_SUBDIRECTORIES", True
        )
        Config.STREAMRIP_CONCURRENCY = DEFAULT_VALUES.get("STREAMRIP_CONCURRENCY", 1)
        Config.STREAMRIP_VERIFY_SSL = DEFAULT_VALUES.get(
            "STREAMRIP_VERIFY_SSL", True
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_CONCURRENT_DOWNLOADS": Config.STREAMRIP_CONCURRENT_DOWNLOADS,
                "STREAMRIP_MAX_SEARCH_RESULTS": Config.STREAMRIP_MAX_SEARCH_RESULTS,
                "STREAMRIP_MAX_CONNECTIONS": Config.STREAMRIP_MAX_CONNECTIONS,
                "STREAMRIP_REQUESTS_PER_MINUTE": Config.STREAMRIP_REQUESTS_PER_MINUTE,
                "STREAMRIP_SOURCE_SUBDIRECTORIES": Config.STREAMRIP_SOURCE_SUBDIRECTORIES,
                "STREAMRIP_DISC_SUBDIRECTORIES": Config.STREAMRIP_DISC_SUBDIRECTORIES,
                "STREAMRIP_CONCURRENCY": Config.STREAMRIP_CONCURRENCY,
                "STREAMRIP_VERIFY_SSL": Config.STREAMRIP_VERIFY_SSL,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_download")

    elif data[1] == "default_streamrip_platforms":
        await query.answer("Resetting streamrip platform settings to default...")
        # Reset streamrip platform settings to default
        Config.STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS", True
        )
        Config.STREAMRIP_QOBUZ_FILTERS_EXTRAS = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_FILTERS_EXTRAS", True
        )
        Config.STREAMRIP_QOBUZ_FILTERS_REPEATS = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_FILTERS_REPEATS", True
        )
        Config.STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS", True
        )
        Config.STREAMRIP_QOBUZ_FILTERS_FEATURES = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_FILTERS_FEATURES", True
        )
        Config.STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS", True
        )
        Config.STREAMRIP_QOBUZ_FILTERS_NON_REMASTER = DEFAULT_VALUES.get(
            "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER", True
        )
        Config.STREAMRIP_TIDAL_DOWNLOAD_VIDEOS = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS", True
        )
        Config.STREAMRIP_TIDAL_TOKEN_EXPIRY = DEFAULT_VALUES.get(
            "STREAMRIP_TIDAL_TOKEN_EXPIRY", ""
        )
        Config.STREAMRIP_DEEZER_USE_DEEZLOADER = DEFAULT_VALUES.get(
            "STREAMRIP_DEEZER_USE_DEEZLOADER", True
        )
        Config.STREAMRIP_DEEZER_DEEZLOADER_WARNINGS = DEFAULT_VALUES.get(
            "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS", True
        )
        Config.STREAMRIP_SOUNDCLOUD_APP_VERSION = DEFAULT_VALUES.get(
            "STREAMRIP_SOUNDCLOUD_APP_VERSION", ""
        )
        Config.STREAMRIP_YOUTUBE_QUALITY = DEFAULT_VALUES.get(
            "STREAMRIP_YOUTUBE_QUALITY", 0
        )
        Config.STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS = DEFAULT_VALUES.get(
            "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS", False
        )
        Config.STREAMRIP_YOUTUBE_VIDEO_FOLDER = DEFAULT_VALUES.get(
            "STREAMRIP_YOUTUBE_VIDEO_FOLDER", ""
        )
        Config.STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER = DEFAULT_VALUES.get(
            "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER", ""
        )
        Config.STREAMRIP_LASTFM_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_LASTFM_ENABLED", True
        )
        Config.STREAMRIP_LASTFM_SOURCE = DEFAULT_VALUES.get(
            "STREAMRIP_LASTFM_SOURCE", "qobuz"
        )
        Config.STREAMRIP_LASTFM_FALLBACK_SOURCE = DEFAULT_VALUES.get(
            "STREAMRIP_LASTFM_FALLBACK_SOURCE", ""
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS": Config.STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS,
                "STREAMRIP_QOBUZ_FILTERS_EXTRAS": Config.STREAMRIP_QOBUZ_FILTERS_EXTRAS,
                "STREAMRIP_QOBUZ_FILTERS_REPEATS": Config.STREAMRIP_QOBUZ_FILTERS_REPEATS,
                "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS": Config.STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS,
                "STREAMRIP_QOBUZ_FILTERS_FEATURES": Config.STREAMRIP_QOBUZ_FILTERS_FEATURES,
                "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS": Config.STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS,
                "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER": Config.STREAMRIP_QOBUZ_FILTERS_NON_REMASTER,
                "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS": Config.STREAMRIP_TIDAL_DOWNLOAD_VIDEOS,
                "STREAMRIP_TIDAL_TOKEN_EXPIRY": Config.STREAMRIP_TIDAL_TOKEN_EXPIRY,
                "STREAMRIP_DEEZER_USE_DEEZLOADER": Config.STREAMRIP_DEEZER_USE_DEEZLOADER,
                "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS": Config.STREAMRIP_DEEZER_DEEZLOADER_WARNINGS,
                "STREAMRIP_SOUNDCLOUD_APP_VERSION": Config.STREAMRIP_SOUNDCLOUD_APP_VERSION,
                "STREAMRIP_YOUTUBE_QUALITY": Config.STREAMRIP_YOUTUBE_QUALITY,
                "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS": Config.STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS,
                "STREAMRIP_YOUTUBE_VIDEO_FOLDER": Config.STREAMRIP_YOUTUBE_VIDEO_FOLDER,
                "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER": Config.STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER,
                "STREAMRIP_LASTFM_ENABLED": Config.STREAMRIP_LASTFM_ENABLED,
                "STREAMRIP_LASTFM_SOURCE": Config.STREAMRIP_LASTFM_SOURCE,
                "STREAMRIP_LASTFM_FALLBACK_SOURCE": Config.STREAMRIP_LASTFM_FALLBACK_SOURCE,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_platforms")

    elif data[1] == "default_streamrip_database":
        await query.answer("Resetting streamrip database settings to default...")
        # Reset streamrip database settings to default
        Config.STREAMRIP_DATABASE_DOWNLOADS_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_DATABASE_DOWNLOADS_ENABLED", True
        )
        Config.STREAMRIP_DATABASE_DOWNLOADS_PATH = DEFAULT_VALUES.get(
            "STREAMRIP_DATABASE_DOWNLOADS_PATH", "./downloads.db"
        )
        Config.STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED", True
        )
        Config.STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH = DEFAULT_VALUES.get(
            "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH", "./failed_downloads.db"
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_DATABASE_DOWNLOADS_ENABLED": Config.STREAMRIP_DATABASE_DOWNLOADS_ENABLED,
                "STREAMRIP_DATABASE_DOWNLOADS_PATH": Config.STREAMRIP_DATABASE_DOWNLOADS_PATH,
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED": Config.STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED,
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH": Config.STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_database")

    elif data[1] == "default_streamrip_conversion":
        await query.answer("Resetting streamrip conversion settings to default...")
        # Reset streamrip conversion settings to default
        Config.STREAMRIP_CONVERSION_ENABLED = DEFAULT_VALUES.get(
            "STREAMRIP_CONVERSION_ENABLED", False
        )
        Config.STREAMRIP_CONVERSION_CODEC = DEFAULT_VALUES.get(
            "STREAMRIP_CONVERSION_CODEC", "ALAC"
        )
        Config.STREAMRIP_CONVERSION_SAMPLING_RATE = DEFAULT_VALUES.get(
            "STREAMRIP_CONVERSION_SAMPLING_RATE", 48000
        )
        Config.STREAMRIP_CONVERSION_BIT_DEPTH = DEFAULT_VALUES.get(
            "STREAMRIP_CONVERSION_BIT_DEPTH", 24
        )
        Config.STREAMRIP_CONVERSION_LOSSY_BITRATE = DEFAULT_VALUES.get(
            "STREAMRIP_CONVERSION_LOSSY_BITRATE", 320
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_CONVERSION_ENABLED": Config.STREAMRIP_CONVERSION_ENABLED,
                "STREAMRIP_CONVERSION_CODEC": Config.STREAMRIP_CONVERSION_CODEC,
                "STREAMRIP_CONVERSION_SAMPLING_RATE": Config.STREAMRIP_CONVERSION_SAMPLING_RATE,
                "STREAMRIP_CONVERSION_BIT_DEPTH": Config.STREAMRIP_CONVERSION_BIT_DEPTH,
                "STREAMRIP_CONVERSION_LOSSY_BITRATE": Config.STREAMRIP_CONVERSION_LOSSY_BITRATE,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_conversion")

    elif data[1] == "default_streamrip_cli":
        await query.answer("Resetting streamrip CLI settings to default...")
        # Reset streamrip CLI settings to default
        Config.STREAMRIP_CLI_TEXT_OUTPUT = DEFAULT_VALUES.get(
            "STREAMRIP_CLI_TEXT_OUTPUT", True
        )
        Config.STREAMRIP_CLI_PROGRESS_BARS = DEFAULT_VALUES.get(
            "STREAMRIP_CLI_PROGRESS_BARS", True
        )
        Config.STREAMRIP_CLI_MAX_SEARCH_RESULTS = DEFAULT_VALUES.get(
            "STREAMRIP_CLI_MAX_SEARCH_RESULTS", 100
        )
        Config.STREAMRIP_MISC_CHECK_FOR_UPDATES = DEFAULT_VALUES.get(
            "STREAMRIP_MISC_CHECK_FOR_UPDATES", True
        )
        Config.STREAMRIP_MISC_VERSION = DEFAULT_VALUES.get(
            "STREAMRIP_MISC_VERSION", "2.0.6"
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_CLI_TEXT_OUTPUT": Config.STREAMRIP_CLI_TEXT_OUTPUT,
                "STREAMRIP_CLI_PROGRESS_BARS": Config.STREAMRIP_CLI_PROGRESS_BARS,
                "STREAMRIP_CLI_MAX_SEARCH_RESULTS": Config.STREAMRIP_CLI_MAX_SEARCH_RESULTS,
                "STREAMRIP_MISC_CHECK_FOR_UPDATES": Config.STREAMRIP_MISC_CHECK_FOR_UPDATES,
                "STREAMRIP_MISC_VERSION": Config.STREAMRIP_MISC_VERSION,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_cli")

    elif data[1] == "default_streamrip_metadata":
        await query.answer("Resetting streamrip metadata settings to default...")
        # Reset streamrip metadata settings to default
        Config.STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM = DEFAULT_VALUES.get(
            "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM", True
        )
        Config.STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS = DEFAULT_VALUES.get(
            "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS", True
        )
        Config.STREAMRIP_METADATA_EXCLUDE = DEFAULT_VALUES.get(
            "STREAMRIP_METADATA_EXCLUDE", []
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM": Config.STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM,
                "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS": Config.STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS,
                "STREAMRIP_METADATA_EXCLUDE": Config.STREAMRIP_METADATA_EXCLUDE,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_metadata")

    elif data[1] == "default_streamrip_advanced":
        await query.answer("Resetting streamrip advanced settings to default...")
        # Reset streamrip advanced settings to default
        Config.STREAMRIP_FILENAME_TEMPLATE = DEFAULT_VALUES.get(
            "STREAMRIP_FILENAME_TEMPLATE", ""
        )
        Config.STREAMRIP_FOLDER_TEMPLATE = DEFAULT_VALUES.get(
            "STREAMRIP_FOLDER_TEMPLATE", ""
        )
        Config.STREAMRIP_EMBED_COVER_ART = DEFAULT_VALUES.get(
            "STREAMRIP_EMBED_COVER_ART", False
        )
        Config.STREAMRIP_SAVE_COVER_ART = DEFAULT_VALUES.get(
            "STREAMRIP_SAVE_COVER_ART", False
        )
        Config.STREAMRIP_COVER_ART_SIZE = DEFAULT_VALUES.get(
            "STREAMRIP_COVER_ART_SIZE", "large"
        )
        Config.STREAMRIP_ARTWORK_EMBED_MAX_WIDTH = DEFAULT_VALUES.get(
            "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH", -1
        )
        Config.STREAMRIP_ARTWORK_SAVED_MAX_WIDTH = DEFAULT_VALUES.get(
            "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH", -1
        )
        Config.STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER = DEFAULT_VALUES.get(
            "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER", False
        )
        Config.STREAMRIP_FILEPATHS_FOLDER_FORMAT = DEFAULT_VALUES.get(
            "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
            "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]",
        )
        Config.STREAMRIP_FILEPATHS_TRACK_FORMAT = DEFAULT_VALUES.get(
            "STREAMRIP_FILEPATHS_TRACK_FORMAT",
            "{tracknumber:02}. {artist} - {title}{explicit}",
        )
        Config.STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS = DEFAULT_VALUES.get(
            "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS", False
        )
        Config.STREAMRIP_FILEPATHS_TRUNCATE_TO = DEFAULT_VALUES.get(
            "STREAMRIP_FILEPATHS_TRUNCATE_TO", 120
        )

        # Update the database
        await database.update_config(
            {
                "STREAMRIP_FILENAME_TEMPLATE": Config.STREAMRIP_FILENAME_TEMPLATE,
                "STREAMRIP_FOLDER_TEMPLATE": Config.STREAMRIP_FOLDER_TEMPLATE,
                "STREAMRIP_EMBED_COVER_ART": Config.STREAMRIP_EMBED_COVER_ART,
                "STREAMRIP_SAVE_COVER_ART": Config.STREAMRIP_SAVE_COVER_ART,
                "STREAMRIP_COVER_ART_SIZE": Config.STREAMRIP_COVER_ART_SIZE,
                "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH": Config.STREAMRIP_ARTWORK_EMBED_MAX_WIDTH,
                "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH": Config.STREAMRIP_ARTWORK_SAVED_MAX_WIDTH,
                "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER": Config.STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER,
                "STREAMRIP_FILEPATHS_FOLDER_FORMAT": Config.STREAMRIP_FILEPATHS_FOLDER_FORMAT,
                "STREAMRIP_FILEPATHS_TRACK_FORMAT": Config.STREAMRIP_FILEPATHS_TRACK_FORMAT,
                "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS": Config.STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS,
                "STREAMRIP_FILEPATHS_TRUNCATE_TO": Config.STREAMRIP_FILEPATHS_TRUNCATE_TO,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "streamrip_advanced")

    elif data[1] == "default_zotify_general":
        await query.answer("Resetting Zotify general settings to default...")
        # Reset Zotify general settings to default
        Config.ZOTIFY_ENABLED = DEFAULT_VALUES.get("ZOTIFY_ENABLED", True)
        Config.ZOTIFY_DOWNLOAD_REAL_TIME = DEFAULT_VALUES.get(
            "ZOTIFY_DOWNLOAD_REAL_TIME", False
        )
        Config.ZOTIFY_REPLACE_EXISTING = DEFAULT_VALUES.get(
            "ZOTIFY_REPLACE_EXISTING", False
        )
        Config.ZOTIFY_SKIP_DUPLICATES = DEFAULT_VALUES.get(
            "ZOTIFY_SKIP_DUPLICATES", True
        )
        Config.ZOTIFY_SKIP_PREVIOUS = DEFAULT_VALUES.get(
            "ZOTIFY_SKIP_PREVIOUS", True
        )

        # Update the database
        await database.update_config(
            {
                "ZOTIFY_ENABLED": Config.ZOTIFY_ENABLED,
                "ZOTIFY_DOWNLOAD_REAL_TIME": Config.ZOTIFY_DOWNLOAD_REAL_TIME,
                "ZOTIFY_REPLACE_EXISTING": Config.ZOTIFY_REPLACE_EXISTING,
                "ZOTIFY_SKIP_DUPLICATES": Config.ZOTIFY_SKIP_DUPLICATES,
                "ZOTIFY_SKIP_PREVIOUS": Config.ZOTIFY_SKIP_PREVIOUS,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "zotify_general")

    elif data[1] == "default_zotify_quality":
        await query.answer("Resetting Zotify quality settings to default...")
        # Reset Zotify quality settings to default
        Config.ZOTIFY_DOWNLOAD_QUALITY = DEFAULT_VALUES.get(
            "ZOTIFY_DOWNLOAD_QUALITY", "auto"
        )
        Config.ZOTIFY_AUDIO_FORMAT = DEFAULT_VALUES.get(
            "ZOTIFY_AUDIO_FORMAT", "vorbis"
        )
        Config.ZOTIFY_ARTWORK_SIZE = DEFAULT_VALUES.get(
            "ZOTIFY_ARTWORK_SIZE", "large"
        )
        Config.ZOTIFY_TRANSCODE_BITRATE = DEFAULT_VALUES.get(
            "ZOTIFY_TRANSCODE_BITRATE", -1
        )

        # Update the database
        await database.update_config(
            {
                "ZOTIFY_DOWNLOAD_QUALITY": Config.ZOTIFY_DOWNLOAD_QUALITY,
                "ZOTIFY_AUDIO_FORMAT": Config.ZOTIFY_AUDIO_FORMAT,
                "ZOTIFY_ARTWORK_SIZE": Config.ZOTIFY_ARTWORK_SIZE,
                "ZOTIFY_TRANSCODE_BITRATE": Config.ZOTIFY_TRANSCODE_BITRATE,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "zotify_quality")

    elif data[1] == "default_zotify_auth":
        await query.answer("Resetting Zotify authentication settings to default...")
        # Reset Zotify auth settings to default
        Config.ZOTIFY_CREDENTIALS_PATH = DEFAULT_VALUES.get(
            "ZOTIFY_CREDENTIALS_PATH", "./zotify_credentials.json"
        )

        # Update the database
        await database.update_config(
            {
                "ZOTIFY_CREDENTIALS_PATH": Config.ZOTIFY_CREDENTIALS_PATH,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "zotify_auth")

    elif data[1] == "default_zotify_paths":
        await query.answer("Resetting Zotify path settings to default...")
        # Reset Zotify path settings to default
        Config.ZOTIFY_ALBUM_LIBRARY = DEFAULT_VALUES.get(
            "ZOTIFY_ALBUM_LIBRARY", "Music/Zotify Albums"
        )
        Config.ZOTIFY_PODCAST_LIBRARY = DEFAULT_VALUES.get(
            "ZOTIFY_PODCAST_LIBRARY", "Music/Zotify Podcasts"
        )
        Config.ZOTIFY_PLAYLIST_LIBRARY = DEFAULT_VALUES.get(
            "ZOTIFY_PLAYLIST_LIBRARY", "Music/Zotify Playlists"
        )

        # Update the database
        await database.update_config(
            {
                "ZOTIFY_ALBUM_LIBRARY": Config.ZOTIFY_ALBUM_LIBRARY,
                "ZOTIFY_PODCAST_LIBRARY": Config.ZOTIFY_PODCAST_LIBRARY,
                "ZOTIFY_PLAYLIST_LIBRARY": Config.ZOTIFY_PLAYLIST_LIBRARY,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "zotify_paths")

    elif data[1] == "default_zotify_templates":
        await query.answer("Resetting Zotify template settings to default...")
        # Reset Zotify template settings to default
        Config.ZOTIFY_OUTPUT_ALBUM = DEFAULT_VALUES.get(
            "ZOTIFY_OUTPUT_ALBUM",
            "{album_artist}/{album}/Disc {discnumber}/{track_number}. {artists} - {title}",
        )
        Config.ZOTIFY_OUTPUT_PLAYLIST_TRACK = DEFAULT_VALUES.get(
            "ZOTIFY_OUTPUT_PLAYLIST_TRACK", "{playlist}/{artists} - {title}"
        )
        Config.ZOTIFY_OUTPUT_PLAYLIST_EPISODE = DEFAULT_VALUES.get(
            "ZOTIFY_OUTPUT_PLAYLIST_EPISODE", "{playlist}/{episode_number} - {title}"
        )
        Config.ZOTIFY_OUTPUT_PODCAST = DEFAULT_VALUES.get(
            "ZOTIFY_OUTPUT_PODCAST", "{podcast}/{episode_number} - {title}"
        )
        Config.ZOTIFY_OUTPUT_SINGLE = DEFAULT_VALUES.get(
            "ZOTIFY_OUTPUT_SINGLE", "{artists} - {title}"
        )

        # Update the database
        await database.update_config(
            {
                "ZOTIFY_OUTPUT_ALBUM": Config.ZOTIFY_OUTPUT_ALBUM,
                "ZOTIFY_OUTPUT_PLAYLIST_TRACK": Config.ZOTIFY_OUTPUT_PLAYLIST_TRACK,
                "ZOTIFY_OUTPUT_PLAYLIST_EPISODE": Config.ZOTIFY_OUTPUT_PLAYLIST_EPISODE,
                "ZOTIFY_OUTPUT_PODCAST": Config.ZOTIFY_OUTPUT_PODCAST,
                "ZOTIFY_OUTPUT_SINGLE": Config.ZOTIFY_OUTPUT_SINGLE,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "zotify_templates")

    elif data[1] == "default_zotify_download":
        await query.answer("Resetting Zotify download settings to default...")
        # Reset Zotify download settings to default
        Config.ZOTIFY_PRINT_PROGRESS = DEFAULT_VALUES.get(
            "ZOTIFY_PRINT_PROGRESS", True
        )
        Config.ZOTIFY_PRINT_DOWNLOADS = DEFAULT_VALUES.get(
            "ZOTIFY_PRINT_DOWNLOADS", False
        )
        Config.ZOTIFY_PRINT_ERRORS = DEFAULT_VALUES.get("ZOTIFY_PRINT_ERRORS", True)
        Config.ZOTIFY_PRINT_WARNINGS = DEFAULT_VALUES.get(
            "ZOTIFY_PRINT_WARNINGS", True
        )
        Config.ZOTIFY_PRINT_SKIPS = DEFAULT_VALUES.get("ZOTIFY_PRINT_SKIPS", False)

        # Update the database
        await database.update_config(
            {
                "ZOTIFY_PRINT_PROGRESS": Config.ZOTIFY_PRINT_PROGRESS,
                "ZOTIFY_PRINT_DOWNLOADS": Config.ZOTIFY_PRINT_DOWNLOADS,
                "ZOTIFY_PRINT_ERRORS": Config.ZOTIFY_PRINT_ERRORS,
                "ZOTIFY_PRINT_WARNINGS": Config.ZOTIFY_PRINT_WARNINGS,
                "ZOTIFY_PRINT_SKIPS": Config.ZOTIFY_PRINT_SKIPS,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "zotify_download")

    elif data[1] == "default_zotify_metadata":
        await query.answer("Resetting Zotify metadata settings to default...")
        # Reset Zotify metadata settings to default
        Config.ZOTIFY_SAVE_METADATA = DEFAULT_VALUES.get(
            "ZOTIFY_SAVE_METADATA", True
        )
        Config.ZOTIFY_SAVE_GENRE = DEFAULT_VALUES.get("ZOTIFY_SAVE_GENRE", False)
        Config.ZOTIFY_ALL_ARTISTS = DEFAULT_VALUES.get("ZOTIFY_ALL_ARTISTS", True)
        Config.ZOTIFY_LYRICS_FILE = DEFAULT_VALUES.get("ZOTIFY_LYRICS_FILE", False)
        Config.ZOTIFY_LYRICS_ONLY = DEFAULT_VALUES.get("ZOTIFY_LYRICS_ONLY", False)
        Config.ZOTIFY_SAVE_SUBTITLES = DEFAULT_VALUES.get(
            "ZOTIFY_SAVE_SUBTITLES", False
        )
        Config.ZOTIFY_CREATE_PLAYLIST_FILE = DEFAULT_VALUES.get(
            "ZOTIFY_CREATE_PLAYLIST_FILE", True
        )

        # Update the database
        await database.update_config(
            {
                "ZOTIFY_SAVE_METADATA": Config.ZOTIFY_SAVE_METADATA,
                "ZOTIFY_SAVE_GENRE": Config.ZOTIFY_SAVE_GENRE,
                "ZOTIFY_ALL_ARTISTS": Config.ZOTIFY_ALL_ARTISTS,
                "ZOTIFY_LYRICS_FILE": Config.ZOTIFY_LYRICS_FILE,
                "ZOTIFY_LYRICS_ONLY": Config.ZOTIFY_LYRICS_ONLY,
                "ZOTIFY_SAVE_SUBTITLES": Config.ZOTIFY_SAVE_SUBTITLES,
                "ZOTIFY_CREATE_PLAYLIST_FILE": Config.ZOTIFY_CREATE_PLAYLIST_FILE,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "zotify_metadata")

    elif data[1] == "default_zotify_advanced":
        await query.answer("Resetting Zotify advanced settings to default...")
        # Reset Zotify advanced settings to default
        Config.ZOTIFY_FFMPEG_PATH = DEFAULT_VALUES.get("ZOTIFY_FFMPEG_PATH", "")
        Config.ZOTIFY_FFMPEG_ARGS = DEFAULT_VALUES.get("ZOTIFY_FFMPEG_ARGS", "")
        Config.ZOTIFY_LANGUAGE = DEFAULT_VALUES.get("ZOTIFY_LANGUAGE", "en")
        Config.ZOTIFY_MATCH_EXISTING = DEFAULT_VALUES.get(
            "ZOTIFY_MATCH_EXISTING", False
        )

        # Update the database
        await database.update_config(
            {
                "ZOTIFY_FFMPEG_PATH": Config.ZOTIFY_FFMPEG_PATH,
                "ZOTIFY_FFMPEG_ARGS": Config.ZOTIFY_FFMPEG_ARGS,
                "ZOTIFY_LANGUAGE": Config.ZOTIFY_LANGUAGE,
                "ZOTIFY_MATCH_EXISTING": Config.ZOTIFY_MATCH_EXISTING,
            }
        )

        # Update the UI - maintain the current state
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "zotify_advanced")

    elif data[1] == "default_gallerydl_platforms":
        # Redirect to auth section since platforms section is now merged with auth
        await query.answer("Platform settings moved to Authentication section!")
        await update_buttons(message, "gallerydl_auth")

    elif data[1] == "default_gallerydl_general":
        await query.answer("Resetting gallery-dl general settings to default...")
        # Reset gallery-dl general settings to default
        Config.GALLERY_DL_QUALITY_SELECTION = True
        Config.GALLERY_DL_ARCHIVE_ENABLED = True
        Config.GALLERY_DL_METADATA_ENABLED = True

        # Update the database
        await database.update_config(
            {
                "GALLERY_DL_QUALITY_SELECTION": True,
                "GALLERY_DL_ARCHIVE_ENABLED": True,
                "GALLERY_DL_METADATA_ENABLED": True,
            }
        )
        # Get the current state before making changes
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "gallerydl_general")

    elif data[1] == "default_gallerydl_auth":
        await query.answer(
            "Resetting gallery-dl authentication settings to default..."
        )
        # Reset gallery-dl auth settings to default
        Config.GALLERY_DL_INSTAGRAM_USERNAME = ""
        Config.GALLERY_DL_INSTAGRAM_PASSWORD = ""
        Config.GALLERY_DL_TWITTER_USERNAME = ""
        Config.GALLERY_DL_TWITTER_PASSWORD = ""
        Config.GALLERY_DL_REDDIT_CLIENT_ID = ""
        Config.GALLERY_DL_REDDIT_CLIENT_SECRET = ""
        Config.GALLERY_DL_REDDIT_USERNAME = ""
        Config.GALLERY_DL_REDDIT_PASSWORD = ""
        Config.GALLERY_DL_REDDIT_REFRESH_TOKEN = ""
        Config.GALLERY_DL_PIXIV_USERNAME = ""
        Config.GALLERY_DL_PIXIV_PASSWORD = ""
        Config.GALLERY_DL_PIXIV_REFRESH_TOKEN = ""
        Config.GALLERY_DL_DEVIANTART_CLIENT_ID = ""
        Config.GALLERY_DL_DEVIANTART_CLIENT_SECRET = ""
        Config.GALLERY_DL_DEVIANTART_USERNAME = ""
        Config.GALLERY_DL_DEVIANTART_PASSWORD = ""
        Config.GALLERY_DL_TUMBLR_API_KEY = ""
        Config.GALLERY_DL_TUMBLR_API_SECRET = ""
        Config.GALLERY_DL_TUMBLR_TOKEN = ""
        Config.GALLERY_DL_TUMBLR_TOKEN_SECRET = ""
        Config.GALLERY_DL_DISCORD_TOKEN = ""

        # Update the database
        await database.update_config(
            {
                "GALLERY_DL_INSTAGRAM_USERNAME": "",
                "GALLERY_DL_INSTAGRAM_PASSWORD": "",
                "GALLERY_DL_TWITTER_USERNAME": "",
                "GALLERY_DL_TWITTER_PASSWORD": "",
                "GALLERY_DL_REDDIT_CLIENT_ID": "",
                "GALLERY_DL_REDDIT_CLIENT_SECRET": "",
                "GALLERY_DL_REDDIT_USERNAME": "",
                "GALLERY_DL_REDDIT_PASSWORD": "",
                "GALLERY_DL_REDDIT_REFRESH_TOKEN": "",
                "GALLERY_DL_PIXIV_USERNAME": "",
                "GALLERY_DL_PIXIV_PASSWORD": "",
                "GALLERY_DL_PIXIV_REFRESH_TOKEN": "",
                "GALLERY_DL_DEVIANTART_CLIENT_ID": "",
                "GALLERY_DL_DEVIANTART_CLIENT_SECRET": "",
                "GALLERY_DL_DEVIANTART_USERNAME": "",
                "GALLERY_DL_DEVIANTART_PASSWORD": "",
                "GALLERY_DL_TUMBLR_API_KEY": "",
                "GALLERY_DL_TUMBLR_API_SECRET": "",
                "GALLERY_DL_TUMBLR_TOKEN": "",
                "GALLERY_DL_TUMBLR_TOKEN_SECRET": "",
                "GALLERY_DL_DISCORD_TOKEN": "",
            }
        )
        # Get the current state before making changes
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "gallerydl_auth")

    elif data[1] == "default_gallerydl_download":
        await query.answer("Resetting gallery-dl download settings to default...")
        # Reset gallery-dl download settings to default
        Config.GALLERY_DL_MAX_DOWNLOADS = 50
        Config.GALLERY_DL_RATE_LIMIT = "1/s"
        Config.GALLERY_DL_LIMIT = 0

        # Update the database
        await database.update_config(
            {
                "GALLERY_DL_MAX_DOWNLOADS": 50,
                "GALLERY_DL_RATE_LIMIT": "1/s",
                "GALLERY_DL_LIMIT": 0,
            }
        )
        # Get the current state before making changes
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "gallerydl_download")

    elif data[1] == "default_ai":
        await query.answer("Resetting all AI settings to default...")
        # Reset all AI settings to default

        # Core AI settings
        Config.AI_ENABLED = True
        Config.DEFAULT_AI_MODEL = "gpt-4o"

        # Provider API Keys (clear for security)
        Config.OPENAI_API_KEY = ""
        Config.ANTHROPIC_API_KEY = ""
        Config.GOOGLE_AI_API_KEY = ""
        Config.GROQ_API_KEY = ""
        Config.VERTEX_PROJECT_ID = ""

        # Provider API URLs
        Config.OPENAI_API_URL = ""
        Config.ANTHROPIC_API_URL = ""
        Config.GOOGLE_AI_API_URL = ""
        Config.GROQ_API_URL = ""

        # Legacy providers
        Config.MISTRAL_API_URL = ""
        Config.DEEPSEEK_API_URL = ""

        # AI Features
        Config.AI_PLUGINS_ENABLED = True
        Config.AI_MULTIMODAL_ENABLED = True
        Config.AI_STREAMING_ENABLED = True
        Config.AI_CONVERSATION_HISTORY = True
        Config.AI_MAX_HISTORY_LENGTH = 10
        Config.AI_QUESTION_PREDICTION = True
        Config.AI_GROUP_TOPIC_MODE = False
        Config.AI_INLINE_MODE_ENABLED = True
        Config.AI_AUTO_LANGUAGE_DETECTION = True
        Config.AI_DEFAULT_LANGUAGE = "en"
        # New ChatGPT-Telegram-Bot Features
        Config.AI_VOICE_TRANSCRIPTION_ENABLED = True
        Config.AI_IMAGE_GENERATION_ENABLED = True
        Config.AI_DOCUMENT_PROCESSING_ENABLED = True
        Config.AI_FOLLOW_UP_QUESTIONS_ENABLED = True
        Config.AI_CONVERSATION_EXPORT_ENABLED = True
        Config.AI_TYPEWRITER_EFFECT_ENABLED = True
        Config.AI_CONTEXT_PRUNING_ENABLED = True

        # AI Plugins
        Config.AI_WEB_SEARCH_ENABLED = True
        Config.AI_URL_SUMMARIZATION_ENABLED = True
        Config.AI_ARXIV_ENABLED = True
        Config.AI_CODE_INTERPRETER_ENABLED = True
        Config.AI_IMAGE_GENERATION_ENABLED = True
        Config.AI_VOICE_TRANSCRIPTION_ENABLED = True

        # AI Performance
        Config.AI_MAX_TOKENS = 4096
        Config.AI_TEMPERATURE = 0.7
        Config.AI_TIMEOUT = 600
        Config.AI_RATE_LIMIT_PER_USER = 100

        # Update the database with all AI settings
        ai_settings = {
            # Core settings
            "AI_ENABLED": True,
            "DEFAULT_AI_MODEL": "gpt-4o",
            # Provider credentials (cleared)
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_AI_API_KEY": "",
            "GROQ_API_KEY": "",
            "VERTEX_PROJECT_ID": "",
            # Provider URLs
            "OPENAI_API_URL": "",
            "ANTHROPIC_API_URL": "",
            "GOOGLE_AI_API_URL": "",
            "GROQ_API_URL": "",
            "MISTRAL_API_URL": "",
            "DEEPSEEK_API_URL": "",
            # Features
            "AI_PLUGINS_ENABLED": True,
            "AI_MULTIMODAL_ENABLED": True,
            "AI_STREAMING_ENABLED": True,
            "AI_CONVERSATION_HISTORY": True,
            "AI_MAX_HISTORY_LENGTH": 10,
            "AI_QUESTION_PREDICTION": True,
            "AI_GROUP_TOPIC_MODE": False,
            "AI_INLINE_MODE_ENABLED": True,
            "AI_AUTO_LANGUAGE_DETECTION": True,
            "AI_DEFAULT_LANGUAGE": "en",
            # New ChatGPT-Telegram-Bot Features
            "AI_VOICE_TRANSCRIPTION_ENABLED": True,
            "AI_IMAGE_GENERATION_ENABLED": True,
            "AI_DOCUMENT_PROCESSING_ENABLED": True,
            "AI_FOLLOW_UP_QUESTIONS_ENABLED": True,
            "AI_CONVERSATION_EXPORT_ENABLED": True,
            "AI_TYPEWRITER_EFFECT_ENABLED": True,
            "AI_CONTEXT_PRUNING_ENABLED": True,
            # Plugins
            "AI_WEB_SEARCH_ENABLED": True,
            "AI_URL_SUMMARIZATION_ENABLED": True,
            "AI_ARXIV_ENABLED": True,
            "AI_CODE_INTERPRETER_ENABLED": True,
            # Performance
            "AI_MAX_TOKENS": 4096,
            "AI_TEMPERATURE": 0.7,
            "AI_TIMEOUT": 600,
            "AI_RATE_LIMIT_PER_USER": 100,
        }

        await database.update_config(ai_settings)
        # Get the current state before making changes
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "ai")

    elif data[1] == "default_youtube_general":
        await query.answer("Resetting YouTube general settings to default...")
        # Reset YouTube general settings to default
        Config.YOUTUBE_UPLOAD_DEFAULT_PRIVACY = "unlisted"
        Config.YOUTUBE_UPLOAD_DEFAULT_CATEGORY = "22"
        Config.YOUTUBE_UPLOAD_DEFAULT_TAGS = ""
        Config.YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION = "Uploaded by AIM"

        # Update the database
        await database.update_config(
            {
                "YOUTUBE_UPLOAD_DEFAULT_PRIVACY": "unlisted",
                "YOUTUBE_UPLOAD_DEFAULT_CATEGORY": "22",
                "YOUTUBE_UPLOAD_DEFAULT_TAGS": "",
                "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION": "Uploaded by AIM",
            }
        )
        # Update the UI - go back to YouTube main menu
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "youtube")

    elif data[1] == "default_youtube_upload":
        await query.answer("Resetting YouTube upload settings to default...")
        # Reset YouTube upload settings to default
        Config.YOUTUBE_UPLOAD_DEFAULT_TITLE = ""
        Config.YOUTUBE_UPLOAD_DEFAULT_LANGUAGE = "en"
        Config.YOUTUBE_UPLOAD_DEFAULT_LICENSE = "youtube"
        Config.YOUTUBE_UPLOAD_EMBEDDABLE = True
        Config.YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE = True
        Config.YOUTUBE_UPLOAD_MADE_FOR_KIDS = False
        Config.YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS = True
        Config.YOUTUBE_UPLOAD_LOCATION_DESCRIPTION = ""
        Config.YOUTUBE_UPLOAD_RECORDING_DATE = ""
        Config.YOUTUBE_UPLOAD_AUTO_LEVELS = False
        Config.YOUTUBE_UPLOAD_STABILIZE = False

        # Update the database
        await database.update_config(
            {
                "YOUTUBE_UPLOAD_DEFAULT_TITLE": "",
                "YOUTUBE_UPLOAD_DEFAULT_LANGUAGE": "en",
                "YOUTUBE_UPLOAD_DEFAULT_LICENSE": "youtube",
                "YOUTUBE_UPLOAD_EMBEDDABLE": True,
                "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE": True,
                "YOUTUBE_UPLOAD_MADE_FOR_KIDS": False,
                "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS": True,
                "YOUTUBE_UPLOAD_LOCATION_DESCRIPTION": "",
                "YOUTUBE_UPLOAD_RECORDING_DATE": "",
                "YOUTUBE_UPLOAD_AUTO_LEVELS": False,
                "YOUTUBE_UPLOAD_STABILIZE": False,
            }
        )
        # Update the UI - go back to YouTube main menu
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "youtube")

    elif data[1] == "default_youtube_auth":
        await query.answer("Resetting YouTube authentication settings to default...")
        # Reset YouTube authentication settings to default
        # Note: We don't reset the actual token file, just clear any config references
        # The token file management is handled separately

        # Update the UI - go back to YouTube main menu
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "youtube")

    elif data[1] == "default_mega_general":
        await query.answer("Resetting MEGA general settings to default...")
        # Reset MEGA general settings to default
        Config.MEGA_EMAIL = ""
        Config.MEGA_PASSWORD = ""

        # Update the database
        await database.update_config(
            {
                "MEGA_EMAIL": "",
                "MEGA_PASSWORD": "",
            }
        )
        # Update the UI - go back to MEGA main menu
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "mega")

    elif data[1] == "default_mega_upload":
        await query.answer("Resetting MEGA upload settings to default...")
        # Reset MEGA upload settings to default
        Config.MEGA_UPLOAD_ENABLED = True
        # Config.MEGA_UPLOAD_FOLDER removed - using folder selector instead
        Config.MEGA_UPLOAD_PUBLIC = True
        # Config.MEGA_UPLOAD_PRIVATE removed - not supported by MEGA SDK v4.8.0
        # Config.MEGA_UPLOAD_UNLISTED removed - not supported by MEGA SDK v4.8.0
        # Config.MEGA_UPLOAD_EXPIRY_DAYS removed - premium feature not implemented
        # Config.MEGA_UPLOAD_PASSWORD removed - premium feature not implemented
        # Config.MEGA_UPLOAD_ENCRYPTION_KEY removed - not supported by MEGA SDK v4.8.0
        Config.MEGA_UPLOAD_THUMBNAIL = True
        # Config.MEGA_UPLOAD_DELETE_AFTER removed - always delete after upload

        # Update the database
        await database.update_config(
            {
                "MEGA_UPLOAD_ENABLED": True,
                # "MEGA_UPLOAD_FOLDER" removed - using folder selector instead
                "MEGA_UPLOAD_PUBLIC": True,
                # "MEGA_UPLOAD_PRIVATE" removed - not supported by MEGA SDK v4.8.0
                # "MEGA_UPLOAD_UNLISTED" removed - not supported by MEGA SDK v4.8.0
                # "MEGA_UPLOAD_EXPIRY_DAYS" removed - premium feature not implemented
                # "MEGA_UPLOAD_PASSWORD" removed - premium feature not implemented
                # "MEGA_UPLOAD_ENCRYPTION_KEY" removed - not supported by MEGA SDK v4.8.0
                "MEGA_UPLOAD_THUMBNAIL": True,
                # "MEGA_UPLOAD_DELETE_AFTER" removed - always delete after upload
            }
        )
        # Update the UI - go back to MEGA main menu
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "mega")

    elif data[1] == "default_mega_security":
        await query.answer(
            "MEGA security features are not supported by MEGA SDK v4.8.0"
        )
        # MEGA security settings removed - not supported by MEGA SDK v4.8.0
        # Redirect back to MEGA main menu
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "mega")

    elif data[1] == "default_ddl":
        await query.answer("Resetting all DDL settings to default...")
        # Reset all DDL settings to default
        Config.DDL_ENABLED = DEFAULT_VALUES["DDL_ENABLED"]
        Config.DDL_DEFAULT_SERVER = DEFAULT_VALUES["DDL_DEFAULT_SERVER"]
        Config.GOFILE_API_KEY = DEFAULT_VALUES["GOFILE_API_KEY"]
        Config.GOFILE_FOLDER_NAME = DEFAULT_VALUES["GOFILE_FOLDER_NAME"]
        Config.GOFILE_PUBLIC_LINKS = DEFAULT_VALUES["GOFILE_PUBLIC_LINKS"]
        Config.GOFILE_PASSWORD_PROTECTION = DEFAULT_VALUES[
            "GOFILE_PASSWORD_PROTECTION"
        ]
        Config.GOFILE_DEFAULT_PASSWORD = DEFAULT_VALUES["GOFILE_DEFAULT_PASSWORD"]
        Config.GOFILE_LINK_EXPIRY_DAYS = DEFAULT_VALUES["GOFILE_LINK_EXPIRY_DAYS"]
        Config.STREAMTAPE_API_USERNAME = DEFAULT_VALUES["STREAMTAPE_API_USERNAME"]
        Config.STREAMTAPE_API_PASSWORD = DEFAULT_VALUES["STREAMTAPE_API_PASSWORD"]
        Config.STREAMTAPE_FOLDER_NAME = DEFAULT_VALUES["STREAMTAPE_FOLDER_NAME"]
        Config.DEVUPLOADS_API_KEY = DEFAULT_VALUES["DEVUPLOADS_API_KEY"]
        Config.DEVUPLOADS_FOLDER_NAME = DEFAULT_VALUES["DEVUPLOADS_FOLDER_NAME"]
        Config.DEVUPLOADS_PUBLIC_FILES = DEFAULT_VALUES["DEVUPLOADS_PUBLIC_FILES"]
        Config.MEDIAFIRE_EMAIL = DEFAULT_VALUES["MEDIAFIRE_EMAIL"]
        Config.MEDIAFIRE_PASSWORD = DEFAULT_VALUES["MEDIAFIRE_PASSWORD"]
        Config.MEDIAFIRE_APP_ID = DEFAULT_VALUES["MEDIAFIRE_APP_ID"]
        Config.MEDIAFIRE_API_KEY = DEFAULT_VALUES["MEDIAFIRE_API_KEY"]

        # Update database
        await database.update_config(
            {
                "DDL_ENABLED": Config.DDL_ENABLED,
                "DDL_DEFAULT_SERVER": Config.DDL_DEFAULT_SERVER,
                "GOFILE_API_KEY": Config.GOFILE_API_KEY,
                "GOFILE_FOLDER_NAME": Config.GOFILE_FOLDER_NAME,
                "GOFILE_PUBLIC_LINKS": Config.GOFILE_PUBLIC_LINKS,
                "GOFILE_PASSWORD_PROTECTION": Config.GOFILE_PASSWORD_PROTECTION,
                "GOFILE_DEFAULT_PASSWORD": Config.GOFILE_DEFAULT_PASSWORD,
                "GOFILE_LINK_EXPIRY_DAYS": Config.GOFILE_LINK_EXPIRY_DAYS,
                "STREAMTAPE_API_USERNAME": Config.STREAMTAPE_API_USERNAME,
                "STREAMTAPE_API_PASSWORD": Config.STREAMTAPE_API_PASSWORD,
                "STREAMTAPE_FOLDER_NAME": Config.STREAMTAPE_FOLDER_NAME,
                "DEVUPLOADS_API_KEY": Config.DEVUPLOADS_API_KEY,
                "DEVUPLOADS_FOLDER_NAME": Config.DEVUPLOADS_FOLDER_NAME,
                "DEVUPLOADS_PUBLIC_FILES": Config.DEVUPLOADS_PUBLIC_FILES,
                "MEDIAFIRE_EMAIL": Config.MEDIAFIRE_EMAIL,
                "MEDIAFIRE_PASSWORD": Config.MEDIAFIRE_PASSWORD,
                "MEDIAFIRE_APP_ID": Config.MEDIAFIRE_APP_ID,
                "MEDIAFIRE_API_KEY": Config.MEDIAFIRE_API_KEY,
            }
        )

        # Update the UI - go back to DDL main menu
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "ddl")

    elif data[1] == "default_ddl_general":
        await query.answer("Resetting DDL general settings to default...")
        # Reset DDL general settings to default
        Config.DDL_DEFAULT_SERVER = DEFAULT_VALUES["DDL_DEFAULT_SERVER"]

        # Update database
        await database.update_config(
            {"DDL_DEFAULT_SERVER": Config.DDL_DEFAULT_SERVER}
        )

        # Update the UI - stay in DDL general section
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "ddl_general")

    elif data[1] == "default_ddl_gofile":
        await query.answer("Resetting Gofile settings to default...")
        # Reset Gofile settings to default
        Config.GOFILE_API_KEY = DEFAULT_VALUES["GOFILE_API_KEY"]
        Config.GOFILE_FOLDER_NAME = DEFAULT_VALUES["GOFILE_FOLDER_NAME"]
        Config.GOFILE_PUBLIC_LINKS = DEFAULT_VALUES["GOFILE_PUBLIC_LINKS"]
        Config.GOFILE_PASSWORD_PROTECTION = DEFAULT_VALUES[
            "GOFILE_PASSWORD_PROTECTION"
        ]
        Config.GOFILE_DEFAULT_PASSWORD = DEFAULT_VALUES["GOFILE_DEFAULT_PASSWORD"]
        Config.GOFILE_LINK_EXPIRY_DAYS = DEFAULT_VALUES["GOFILE_LINK_EXPIRY_DAYS"]

        # Update database
        await database.update_config(
            {
                "GOFILE_API_KEY": Config.GOFILE_API_KEY,
                "GOFILE_FOLDER_NAME": Config.GOFILE_FOLDER_NAME,
                "GOFILE_PUBLIC_LINKS": Config.GOFILE_PUBLIC_LINKS,
                "GOFILE_PASSWORD_PROTECTION": Config.GOFILE_PASSWORD_PROTECTION,
                "GOFILE_DEFAULT_PASSWORD": Config.GOFILE_DEFAULT_PASSWORD,
                "GOFILE_LINK_EXPIRY_DAYS": Config.GOFILE_LINK_EXPIRY_DAYS,
            }
        )

        # Update the UI - stay in DDL gofile section
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "ddl_gofile")

    elif data[1] == "default_ddl_streamtape":
        await query.answer("Resetting Streamtape settings to default...")
        # Reset Streamtape settings to default
        Config.STREAMTAPE_API_USERNAME = DEFAULT_VALUES["STREAMTAPE_API_USERNAME"]
        Config.STREAMTAPE_API_PASSWORD = DEFAULT_VALUES["STREAMTAPE_API_PASSWORD"]
        Config.STREAMTAPE_FOLDER_NAME = DEFAULT_VALUES["STREAMTAPE_FOLDER_NAME"]

        # Update database
        await database.update_config(
            {
                "STREAMTAPE_API_USERNAME": Config.STREAMTAPE_API_USERNAME,
                "STREAMTAPE_API_PASSWORD": Config.STREAMTAPE_API_PASSWORD,
                "STREAMTAPE_FOLDER_NAME": Config.STREAMTAPE_FOLDER_NAME,
            }
        )

        # Update the UI - stay in DDL streamtape section
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "ddl_streamtape")

    elif data[1] == "default_ddl_devuploads":
        await query.answer("Resetting DevUploads settings to default...")
        # Reset DevUploads settings to default
        Config.DEVUPLOADS_API_KEY = DEFAULT_VALUES["DEVUPLOADS_API_KEY"]
        Config.DEVUPLOADS_FOLDER_NAME = DEFAULT_VALUES["DEVUPLOADS_FOLDER_NAME"]
        Config.DEVUPLOADS_PUBLIC_FILES = DEFAULT_VALUES["DEVUPLOADS_PUBLIC_FILES"]

        # Update database
        await database.update_config(
            {
                "DEVUPLOADS_API_KEY": Config.DEVUPLOADS_API_KEY,
                "DEVUPLOADS_FOLDER_NAME": Config.DEVUPLOADS_FOLDER_NAME,
                "DEVUPLOADS_PUBLIC_FILES": Config.DEVUPLOADS_PUBLIC_FILES,
            }
        )

        # Update the UI - stay in DDL devuploads section
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "ddl_devuploads")

    elif data[1] == "default_ddl_mediafire":
        await query.answer("Resetting MediaFire settings to default...")
        # Reset MediaFire settings to default
        Config.MEDIAFIRE_EMAIL = DEFAULT_VALUES["MEDIAFIRE_EMAIL"]
        Config.MEDIAFIRE_PASSWORD = DEFAULT_VALUES["MEDIAFIRE_PASSWORD"]
        Config.MEDIAFIRE_APP_ID = DEFAULT_VALUES["MEDIAFIRE_APP_ID"]
        Config.MEDIAFIRE_API_KEY = DEFAULT_VALUES["MEDIAFIRE_API_KEY"]

        # Update database
        await database.update_config(
            {
                "MEDIAFIRE_EMAIL": Config.MEDIAFIRE_EMAIL,
                "MEDIAFIRE_PASSWORD": Config.MEDIAFIRE_PASSWORD,
                "MEDIAFIRE_APP_ID": Config.MEDIAFIRE_APP_ID,
                "MEDIAFIRE_API_KEY": Config.MEDIAFIRE_API_KEY,
            }
        )

        # Update the UI - stay in DDL mediafire section
        current_state = globals()["state"]
        globals()["state"] = current_state
        await update_buttons(message, "ddl_mediafire")

    elif data[1] == "default_taskmonitor":
        await query.answer("Resetting all task monitoring settings to default...")
        # Reset all task monitoring settings to default
        Config.TASK_MONITOR_ENABLED = DEFAULT_VALUES["TASK_MONITOR_ENABLED"]
        Config.TASK_MONITOR_INTERVAL = DEFAULT_VALUES["TASK_MONITOR_INTERVAL"]
        Config.TASK_MONITOR_CONSECUTIVE_CHECKS = DEFAULT_VALUES[
            "TASK_MONITOR_CONSECUTIVE_CHECKS"
        ]
        Config.TASK_MONITOR_SPEED_THRESHOLD = DEFAULT_VALUES[
            "TASK_MONITOR_SPEED_THRESHOLD"
        ]
        Config.TASK_MONITOR_ELAPSED_THRESHOLD = DEFAULT_VALUES[
            "TASK_MONITOR_ELAPSED_THRESHOLD"
        ]
        Config.TASK_MONITOR_ETA_THRESHOLD = DEFAULT_VALUES[
            "TASK_MONITOR_ETA_THRESHOLD"
        ]
        Config.TASK_MONITOR_WAIT_TIME = DEFAULT_VALUES["TASK_MONITOR_WAIT_TIME"]
        Config.TASK_MONITOR_COMPLETION_THRESHOLD = DEFAULT_VALUES[
            "TASK_MONITOR_COMPLETION_THRESHOLD"
        ]
        Config.TASK_MONITOR_CPU_HIGH = DEFAULT_VALUES["TASK_MONITOR_CPU_HIGH"]
        Config.TASK_MONITOR_CPU_LOW = DEFAULT_VALUES["TASK_MONITOR_CPU_LOW"]
        Config.TASK_MONITOR_MEMORY_HIGH = DEFAULT_VALUES["TASK_MONITOR_MEMORY_HIGH"]
        Config.TASK_MONITOR_MEMORY_LOW = DEFAULT_VALUES["TASK_MONITOR_MEMORY_LOW"]
        # Update the database
        await database.update_config(
            {
                "TASK_MONITOR_ENABLED": DEFAULT_VALUES["TASK_MONITOR_ENABLED"],
                "TASK_MONITOR_INTERVAL": DEFAULT_VALUES["TASK_MONITOR_INTERVAL"],
                "TASK_MONITOR_CONSECUTIVE_CHECKS": DEFAULT_VALUES[
                    "TASK_MONITOR_CONSECUTIVE_CHECKS"
                ],
                "TASK_MONITOR_SPEED_THRESHOLD": DEFAULT_VALUES[
                    "TASK_MONITOR_SPEED_THRESHOLD"
                ],
                "TASK_MONITOR_ELAPSED_THRESHOLD": DEFAULT_VALUES[
                    "TASK_MONITOR_ELAPSED_THRESHOLD"
                ],
                "TASK_MONITOR_ETA_THRESHOLD": DEFAULT_VALUES[
                    "TASK_MONITOR_ETA_THRESHOLD"
                ],
                "TASK_MONITOR_WAIT_TIME": DEFAULT_VALUES["TASK_MONITOR_WAIT_TIME"],
                "TASK_MONITOR_COMPLETION_THRESHOLD": DEFAULT_VALUES[
                    "TASK_MONITOR_COMPLETION_THRESHOLD"
                ],
                "TASK_MONITOR_CPU_HIGH": DEFAULT_VALUES["TASK_MONITOR_CPU_HIGH"],
                "TASK_MONITOR_CPU_LOW": DEFAULT_VALUES["TASK_MONITOR_CPU_LOW"],
                "TASK_MONITOR_MEMORY_HIGH": DEFAULT_VALUES[
                    "TASK_MONITOR_MEMORY_HIGH"
                ],
                "TASK_MONITOR_MEMORY_LOW": DEFAULT_VALUES["TASK_MONITOR_MEMORY_LOW"],
            }
        )
        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "taskmonitor")
    elif data[1] == "default_merge":
        await query.answer("Resetting all merge settings to default...")
        # Reset all merge settings to default
        Config.MERGE_ENABLED = False
        Config.CONCAT_DEMUXER_ENABLED = True
        Config.FILTER_COMPLEX_ENABLED = False
        # Reset output formats
        Config.MERGE_OUTPUT_FORMAT_VIDEO = "mkv"
        Config.MERGE_OUTPUT_FORMAT_AUDIO = "mp3"
        Config.MERGE_OUTPUT_FORMAT_IMAGE = "jpg"
        Config.MERGE_OUTPUT_FORMAT_DOCUMENT = "pdf"
        Config.MERGE_OUTPUT_FORMAT_SUBTITLE = "srt"

        # Reset video settings
        Config.MERGE_VIDEO_CODEC = "none"
        Config.MERGE_VIDEO_QUALITY = "none"
        Config.MERGE_VIDEO_PRESET = "none"
        Config.MERGE_VIDEO_CRF = 0
        Config.MERGE_VIDEO_PIXEL_FORMAT = "none"
        Config.MERGE_VIDEO_TUNE = "none"
        Config.MERGE_VIDEO_FASTSTART = False

        # Reset audio settings
        Config.MERGE_AUDIO_CODEC = "none"
        Config.MERGE_AUDIO_BITRATE = "none"
        Config.MERGE_AUDIO_CHANNELS = 0
        Config.MERGE_AUDIO_SAMPLING = "none"
        Config.MERGE_AUDIO_VOLUME = 0.0

        # Reset image settings
        Config.MERGE_IMAGE_MODE = "none"
        Config.MERGE_IMAGE_COLUMNS = 0
        Config.MERGE_IMAGE_QUALITY = 0
        Config.MERGE_IMAGE_DPI = 0
        Config.MERGE_IMAGE_RESIZE = "none"
        Config.MERGE_IMAGE_BACKGROUND = "none"

        # Reset subtitle settings
        Config.MERGE_SUBTITLE_ENCODING = "none"
        Config.MERGE_SUBTITLE_FONT = "none"
        Config.MERGE_SUBTITLE_FONT_SIZE = 0
        Config.MERGE_SUBTITLE_FONT_COLOR = "none"
        Config.MERGE_SUBTITLE_BACKGROUND = "none"

        # Reset document settings
        Config.MERGE_DOCUMENT_PAPER_SIZE = "none"
        Config.MERGE_DOCUMENT_ORIENTATION = "none"
        Config.MERGE_DOCUMENT_MARGIN = 0

        # Reset general settings
        Config.MERGE_METADATA_TITLE = "none"
        Config.MERGE_METADATA_AUTHOR = "none"
        Config.MERGE_METADATA_COMMENT = "none"
        Config.MERGE_PRIORITY = 1
        Config.MERGE_THREADING = True
        Config.MERGE_THREAD_NUMBER = 4
        Config.MERGE_REMOVE_ORIGINAL = True
        # Update the database
        await database.update_config(
            {
                "MERGE_ENABLED": False,
                "CONCAT_DEMUXER_ENABLED": True,
                "FILTER_COMPLEX_ENABLED": False,
                # Output formats
                "MERGE_OUTPUT_FORMAT_VIDEO": "mkv",
                "MERGE_OUTPUT_FORMAT_AUDIO": "mp3",
                "MERGE_OUTPUT_FORMAT_IMAGE": "jpg",
                "MERGE_OUTPUT_FORMAT_DOCUMENT": "pdf",
                "MERGE_OUTPUT_FORMAT_SUBTITLE": "srt",
                # Video settings
                "MERGE_VIDEO_CODEC": "none",
                "MERGE_VIDEO_QUALITY": "none",
                "MERGE_VIDEO_PRESET": "none",
                "MERGE_VIDEO_CRF": 0,
                "MERGE_VIDEO_PIXEL_FORMAT": "none",
                "MERGE_VIDEO_TUNE": "none",
                "MERGE_VIDEO_FASTSTART": False,
                # Audio settings
                "MERGE_AUDIO_CODEC": "none",
                "MERGE_AUDIO_BITRATE": "none",
                "MERGE_AUDIO_CHANNELS": 0,
                "MERGE_AUDIO_SAMPLING": "none",
                "MERGE_AUDIO_VOLUME": 0.0,
                # Image settings
                "MERGE_IMAGE_MODE": "none",
                "MERGE_IMAGE_COLUMNS": 0,
                "MERGE_IMAGE_QUALITY": 0,
                "MERGE_IMAGE_DPI": 0,
                "MERGE_IMAGE_RESIZE": "none",
                "MERGE_IMAGE_BACKGROUND": "none",
                # Subtitle settings
                "MERGE_SUBTITLE_ENCODING": "none",
                "MERGE_SUBTITLE_FONT": "none",
                "MERGE_SUBTITLE_FONT_SIZE": 0,
                "MERGE_SUBTITLE_FONT_COLOR": "none",
                "MERGE_SUBTITLE_BACKGROUND": "none",
                # Document settings
                "MERGE_DOCUMENT_PAPER_SIZE": "none",
                "MERGE_DOCUMENT_ORIENTATION": "none",
                "MERGE_DOCUMENT_MARGIN": 0,
                # General settings
                "MERGE_METADATA_TITLE": "none",
                "MERGE_METADATA_AUTHOR": "none",
                "MERGE_METADATA_COMMENT": "none",
                "MERGE_PRIORITY": 1,
                "MERGE_THREADING": True,
                "MERGE_THREAD_NUMBER": 4,
                "MERGE_REMOVE_ORIGINAL": True,
            }
        )
        # Keep the current page and state
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state

        # Maintain the current page when returning to the merge menu
        if "merge_page" in globals():
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
        else:
            await update_buttons(message, "mediatools_merge", page=0)
    # This is a duplicate handler, removed to avoid confusion
    elif data[1] == "edit" and data[2] in [
        "mediatools_watermark",
        "mediatools_merge",
        "mediatools_merge_config",
        "mediatools_metadata",
        "mediatools_convert",
        "mediatools_compression",
        "mediatools_trim",
        "mediatools_extract",
        "mediatools_add",
        "mediatools_swap",
        "ai",
        "mega",
        "youtube",
        "youtube_general",
        "youtube_upload",
        "youtube_auth",
        "mega_general",
        "mega_upload",
        "mega_security",
        "ddl",
        "ddl_general",
        "ddl_gofile",
        "ddl_streamtape",
        "ddl_devuploads",
        "ddl_mediafire",
    ]:
        await query.answer()
        # Set the global state to edit mode
        globals()["state"] = "edit"
        # For merge settings, maintain the current page
        if data[2] == "mediatools_merge":
            # Just update the state, the page is maintained by the global merge_page variable
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
        elif data[2] == "mediatools_metadata":
            await update_buttons(message, "mediatools_metadata")
        elif data[2] == "mediatools_convert":
            await update_buttons(message, "mediatools_convert")
        elif data[2] == "mediatools_compression":
            await update_buttons(message, "mediatools_compression")
        elif data[2] == "mediatools_trim":
            await update_buttons(message, "mediatools_trim")
        elif data[2] == "mediatools_extract":
            await update_buttons(message, "mediatools_extract")
        elif data[2] == "mediatools_add":
            # Force a refresh of the UI to ensure the toggle buttons show the correct state
            await update_buttons(message, "mediatools_add")
        elif data[2] == "ai":
            await update_buttons(message, "ai")
        elif data[2] == "taskmonitor":
            await update_buttons(message, "taskmonitor")
        elif data[2] in [
            "youtube",
            "youtube_general",
            "youtube_upload",
            "youtube_auth",
        ] or data[2] in [
            "mega",
            "mega_general",
            "mega_upload",
            "mega_security",
        ]:
            await update_buttons(message, data[2])
        else:
            await update_buttons(message, data[2])
    elif data[1] == "view" and data[2] in [
        "mediatools_watermark",
        "mediatools_merge",
        "mediatools_merge_config",
        "mediatools_metadata",
        "mediatools_convert",
        "mediatools_compression",
        "mediatools_trim",
        "mediatools_extract",
        "mediatools_add",
        "mediatools_swap",
        "ai",
        "youtube",
        "youtube_general",
        "youtube_upload",
        "youtube_auth",
        "mega",
        "mega_general",
        "mega_upload",
        "mega_security",
        "ddl",
        "ddl_general",
        "ddl_gofile",
        "ddl_streamtape",
        "ddl_devuploads",
        "ddl_mediafire",
    ]:
        await query.answer()
        # Set the global state to view mode
        globals()["state"] = "view"
        # For merge settings, maintain the current page
        if data[2] == "mediatools_merge":
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
        elif data[2] == "mediatools_metadata":
            await update_buttons(message, "mediatools_metadata")
        elif data[2] == "mediatools_convert":
            await update_buttons(message, "mediatools_convert")
        elif data[2] == "mediatools_compression":
            await update_buttons(message, "mediatools_compression")
        elif data[2] == "mediatools_trim":
            await update_buttons(message, "mediatools_trim")
        elif data[2] == "mediatools_extract":
            await update_buttons(message, "mediatools_extract")
        elif data[2] == "mediatools_add":
            # Force a refresh of the UI to ensure the toggle buttons show the correct state
            await update_buttons(message, "mediatools_add")
        elif data[2] == "ai":
            await update_buttons(message, "ai")
        elif data[2] in [
            "youtube",
            "youtube_general",
            "youtube_upload",
            "youtube_auth",
        ] or data[2] in [
            "mega",
            "mega_general",
            "mega_upload",
            "mega_security",
        ]:
            await update_buttons(message, data[2])
        else:
            await update_buttons(message, data[2])

        # This section is now handled above
    elif data[1] == "editvar":
        # Handle view mode for all other settings
        if (
            state == "view"
            and data[2]
            not in [
                "TASK_MONITOR_ENABLED",
                "TASK_MONITOR_INTERVAL",
                "TASK_MONITOR_CONSECUTIVE_CHECKS",
                "TASK_MONITOR_SPEED_THRESHOLD",
                "TASK_MONITOR_ELAPSED_THRESHOLD",
                "TASK_MONITOR_ETA_THRESHOLD",
                "TASK_MONITOR_COMPLETION_THRESHOLD",
                "TASK_MONITOR_WAIT_TIME",
                "TASK_MONITOR_CPU_HIGH",
                "TASK_MONITOR_CPU_LOW",
                "TASK_MONITOR_MEMORY_HIGH",
                "TASK_MONITOR_MEMORY_LOW",
            ]
            and not data[2].startswith("STREAMRIP_")
            and not data[2].startswith("ZOTIFY_")
            and not data[2].startswith("YOUTUBE_UPLOAD_")
            and not data[2].startswith("MEGA_")
            and not data[2].startswith("AI_")
            and data[2] not in ["DEFAULT_AI_MODEL"]
        ):
            # In view mode, show the current value in a popup
            value = f"{Config.get(data[2])}"
            if len(value) > 200:
                await query.answer()
                with BytesIO(str.encode(value)) as out_file:
                    out_file.name = f"{data[2]}.txt"
                    await send_file(message, out_file)
                return
            if value == "":
                value = None
            await query.answer(f"{value}", show_alert=True)

            # Stay in view mode - don't switch to edit mode automatically
            # This ensures the view state is maintained when viewing configs
            return

        # Handle edit mode for all settings
        await query.answer()
        # Make sure we're in edit mode
        globals()["state"] = "edit"

        # For regular Config variables in the var section, directly set up the edit flow
        # This ensures the correct edit flow is used for Config variables in edit state
        if (
            (
                not data[2].startswith(
                    (
                        "WATERMARK_",
                        "AUDIO_WATERMARK_",
                        "SUBTITLE_WATERMARK_",
                        "IMAGE_WATERMARK_",
                        "MERGE_",
                        "METADATA_",
                        "TASK_MONITOR_",
                        "CONVERT_",
                        "COMPRESSION_",
                        "TRIM_",
                        "EXTRACT_",
                        "MISTRAL_",
                        "DEEPSEEK_",
                        "DEFAULT_AI_",
                    )
                )
                and data[2]
                not in ["CONCAT_DEMUXER_ENABLED", "FILTER_COMPLEX_ENABLED"]
            )
            or data[2].startswith("STREAMRIP_")
            or data[2].startswith("ZOTIFY_")
            or data[2].startswith("YOUTUBE_UPLOAD_")
            or data[2].startswith("MEGA_")
        ):
            # Get the current state before making changes
            current_state = globals()["state"]

            # Show the edit message with the current value
            msg = f"Send a valid value for <code>{data[2]}</code>.\n\n<b>Current value:</b> <code>{Config.get(data[2])}</code>\n\n<i>Timeout: 60 seconds</i>"
            buttons = ButtonMaker()

            # Determine the correct back button based on the variable type
            back_menu = "var"  # Default
            if data[2].startswith("STREAMRIP_"):
                # For streamrip settings, determine which submenu to return to
                if data[2] in [
                    "STREAMRIP_ENABLED",
                    "STREAMRIP_CONCURRENT_DOWNLOADS",
                    "STREAMRIP_MAX_SEARCH_RESULTS",
                    "STREAMRIP_ENABLE_DATABASE",
                    "STREAMRIP_AUTO_CONVERT",
                ]:
                    back_menu = "streamrip_general"
                elif data[2] in [
                    "STREAMRIP_DEFAULT_QUALITY",
                    "STREAMRIP_FALLBACK_QUALITY",
                    "STREAMRIP_DEFAULT_CODEC",
                    "STREAMRIP_SUPPORTED_CODECS",
                    "STREAMRIP_QUALITY_FALLBACK_ENABLED",
                ]:
                    back_menu = "streamrip_quality"
                elif (
                    (
                        data[2].endswith("_ENABLED")
                        and any(
                            platform in data[2]
                            for platform in [
                                "QOBUZ",
                                "TIDAL",
                                "DEEZER",
                                "SOUNDCLOUD",
                            ]
                        )
                    )
                    or data[2].endswith(
                        (
                            "_EMAIL",
                            "_PASSWORD",
                            "_ARL",
                            "_CLIENT_ID",
                            "_ACCESS_TOKEN",
                            "_REFRESH_TOKEN",
                            "_USER_ID",
                            "_COUNTRY_CODE",
                        )
                    )
                    or data[2]
                    in [
                        "STREAMRIP_QOBUZ_USE_AUTH_TOKEN",
                        "STREAMRIP_QOBUZ_APP_ID",
                        "STREAMRIP_QOBUZ_SECRETS",
                        "STREAMRIP_QOBUZ_QUALITY",
                        "STREAMRIP_TIDAL_QUALITY",
                        "STREAMRIP_DEEZER_QUALITY",
                        "STREAMRIP_SOUNDCLOUD_QUALITY",
                    ]
                ):
                    back_menu = "streamrip_credentials"
                elif data[2] in [
                    "STREAMRIP_MAX_CONNECTIONS",
                    "STREAMRIP_REQUESTS_PER_MINUTE",
                    "STREAMRIP_SOURCE_SUBDIRECTORIES",
                    "STREAMRIP_DISC_SUBDIRECTORIES",
                    "STREAMRIP_CONCURRENCY",
                    "STREAMRIP_VERIFY_SSL",
                ]:
                    back_menu = "streamrip_download"
                elif data[2] in [
                    "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS",
                    "STREAMRIP_QOBUZ_FILTERS_EXTRAS",
                    "STREAMRIP_QOBUZ_FILTERS_REPEATS",
                    "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS",
                    "STREAMRIP_QOBUZ_FILTERS_FEATURES",
                    "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS",
                    "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER",
                    "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS",
                    "STREAMRIP_TIDAL_TOKEN_EXPIRY",
                    "STREAMRIP_DEEZER_USE_DEEZLOADER",
                    "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS",
                    "STREAMRIP_SOUNDCLOUD_APP_VERSION",
                    "STREAMRIP_YOUTUBE_QUALITY",
                    "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS",
                    "STREAMRIP_YOUTUBE_VIDEO_FOLDER",
                    "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER",
                    "STREAMRIP_LASTFM_ENABLED",
                    "STREAMRIP_LASTFM_SOURCE",
                    "STREAMRIP_LASTFM_FALLBACK_SOURCE",
                ]:
                    back_menu = "streamrip_platforms"
                elif data[2] in [
                    "STREAMRIP_DATABASE_DOWNLOADS_ENABLED",
                    "STREAMRIP_DATABASE_DOWNLOADS_PATH",
                    "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED",
                    "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
                ]:
                    back_menu = "streamrip_database"
                elif data[2] in [
                    "STREAMRIP_CONVERSION_ENABLED",
                    "STREAMRIP_CONVERSION_CODEC",
                    "STREAMRIP_CONVERSION_SAMPLING_RATE",
                    "STREAMRIP_CONVERSION_BIT_DEPTH",
                    "STREAMRIP_CONVERSION_LOSSY_BITRATE",
                ]:
                    back_menu = "streamrip_conversion"
                elif data[2] in [
                    "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM",
                    "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS",
                    "STREAMRIP_METADATA_EXCLUDE",
                ]:
                    back_menu = "streamrip_metadata"
                elif data[2] in [
                    "STREAMRIP_CLI_TEXT_OUTPUT",
                    "STREAMRIP_CLI_PROGRESS_BARS",
                    "STREAMRIP_CLI_MAX_SEARCH_RESULTS",
                    "STREAMRIP_MISC_CHECK_FOR_UPDATES",
                    "STREAMRIP_MISC_VERSION",
                ]:
                    back_menu = "streamrip_cli"
                elif data[2] in [
                    "STREAMRIP_FILENAME_TEMPLATE",
                    "STREAMRIP_FOLDER_TEMPLATE",
                    "STREAMRIP_EMBED_COVER_ART",
                    "STREAMRIP_SAVE_COVER_ART",
                    "STREAMRIP_COVER_ART_SIZE",
                    "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH",
                    "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH",
                    "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER",
                    "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
                    "STREAMRIP_FILEPATHS_TRACK_FORMAT",
                    "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS",
                    "STREAMRIP_FILEPATHS_TRUNCATE_TO",
                ]:
                    back_menu = "streamrip_advanced"
                else:
                    back_menu = "streamrip"
            elif data[2].startswith("ZOTIFY_"):
                # For zotify settings, determine which submenu to return to
                if data[2] in [
                    "ZOTIFY_ENABLED",
                    "ZOTIFY_DOWNLOAD_REAL_TIME",
                    "ZOTIFY_REPLACE_EXISTING",
                    "ZOTIFY_SKIP_DUPLICATES",
                    "ZOTIFY_SKIP_PREVIOUS",
                ]:
                    back_menu = "zotify_general"
                elif data[2] in [
                    "ZOTIFY_DOWNLOAD_QUALITY",
                    "ZOTIFY_AUDIO_FORMAT",
                    "ZOTIFY_ARTWORK_SIZE",
                    "ZOTIFY_TRANSCODE_BITRATE",
                ]:
                    back_menu = "zotify_quality"
                elif data[2] in [
                    "ZOTIFY_CREDENTIALS_PATH",
                ]:
                    back_menu = "zotify_auth"
                elif data[2] in [
                    "ZOTIFY_ALBUM_LIBRARY",
                    "ZOTIFY_PODCAST_LIBRARY",
                    "ZOTIFY_PLAYLIST_LIBRARY",
                ]:
                    back_menu = "zotify_paths"
                elif data[2] in [
                    "ZOTIFY_OUTPUT_ALBUM",
                    "ZOTIFY_OUTPUT_PLAYLIST_TRACK",
                    "ZOTIFY_OUTPUT_PLAYLIST_EPISODE",
                    "ZOTIFY_OUTPUT_PODCAST",
                    "ZOTIFY_OUTPUT_SINGLE",
                ]:
                    back_menu = "zotify_templates"
                elif data[2] in [
                    "ZOTIFY_PRINT_PROGRESS",
                    "ZOTIFY_PRINT_DOWNLOADS",
                    "ZOTIFY_PRINT_ERRORS",
                    "ZOTIFY_PRINT_WARNINGS",
                    "ZOTIFY_PRINT_SKIPS",
                ]:
                    back_menu = "zotify_download"
                elif data[2] in [
                    "ZOTIFY_SAVE_METADATA",
                    "ZOTIFY_SAVE_GENRE",
                    "ZOTIFY_ALL_ARTISTS",
                    "ZOTIFY_LYRICS_FILE",
                    "ZOTIFY_LYRICS_ONLY",
                    "ZOTIFY_SAVE_SUBTITLES",
                    "ZOTIFY_CREATE_PLAYLIST_FILE",
                ]:
                    back_menu = "zotify_metadata"
                elif data[2] in [
                    "ZOTIFY_FFMPEG_PATH",
                    "ZOTIFY_FFMPEG_ARGS",
                    "ZOTIFY_LANGUAGE",
                    "ZOTIFY_MATCH_EXISTING",
                ]:
                    back_menu = "zotify_advanced"
                else:
                    back_menu = "zotify"
            elif data[2].startswith("YOUTUBE_UPLOAD_"):
                # For YouTube upload settings, determine which submenu to return to
                if data[2] in [
                    "YOUTUBE_UPLOAD_DEFAULT_PRIVACY",
                    "YOUTUBE_UPLOAD_DEFAULT_CATEGORY",
                    "YOUTUBE_UPLOAD_DEFAULT_TAGS",
                    "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
                ]:
                    back_menu = "youtube_general"
                elif data[2] in [
                    "YOUTUBE_UPLOAD_DEFAULT_TITLE",
                    "YOUTUBE_UPLOAD_DEFAULT_LANGUAGE",
                    "YOUTUBE_UPLOAD_DEFAULT_LICENSE",
                    "YOUTUBE_UPLOAD_EMBEDDABLE",
                    "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
                    "YOUTUBE_UPLOAD_MADE_FOR_KIDS",
                    "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
                    "YOUTUBE_UPLOAD_LOCATION_DESCRIPTION",
                    "YOUTUBE_UPLOAD_RECORDING_DATE",
                    "YOUTUBE_UPLOAD_AUTO_LEVELS",
                    "YOUTUBE_UPLOAD_STABILIZE",
                ]:
                    back_menu = "youtube_upload"
                else:
                    back_menu = "youtube"
            elif data[2].startswith("MEGA_"):
                # For MEGA settings, determine which submenu to return to
                if data[2] in ["MEGA_EMAIL", "MEGA_PASSWORD", "MEGA_LIMIT"]:
                    back_menu = "mega_general"
                elif data[2] in [
                    "MEGA_UPLOAD_ENABLED",
                    # "MEGA_UPLOAD_FOLDER" removed - using folder selector instead
                    "MEGA_UPLOAD_PUBLIC",
                    # "MEGA_UPLOAD_PRIVATE" removed - not supported by MEGA SDK v4.8.0
                    # "MEGA_UPLOAD_UNLISTED" removed - not supported by MEGA SDK v4.8.0
                    # "MEGA_UPLOAD_EXPIRY_DAYS" removed - premium feature not implemented
                    # "MEGA_UPLOAD_PASSWORD" removed - premium feature not implemented
                    # "MEGA_UPLOAD_ENCRYPTION_KEY" removed - not supported by MEGA SDK v4.8.0
                    "MEGA_UPLOAD_THUMBNAIL",
                    # "MEGA_UPLOAD_DELETE_AFTER" removed - always delete after upload
                ]:
                    back_menu = "mega_upload"

                # mega_security settings removed - not supported by MEGA SDK v4.8.0
                elif data[2] == "MEGA_SEARCH_ENABLED":
                    back_menu = "mega"
                else:
                    back_menu = "mega"

            buttons.data_button("⬅️ Back", f"botset {back_menu}", "footer")
            if data[2] not in [
                "TELEGRAM_HASH",
                "TELEGRAM_API",
                "OWNER_ID",
                "BOT_TOKEN",
            ]:
                buttons.data_button("🔄 Default", f"botset resetvar {data[2]}")
            buttons.data_button("❌ Close", "botset close", "footer")

            # Add warning for sensitive settings
            if data[2] in [
                "CMD_SUFFIX",
                "OWNER_ID",
                "USER_SESSION_STRING",
                "TELEGRAM_HASH",
                "TELEGRAM_API",
                "BOT_TOKEN",
                "TG_PROXY",
            ]:
                msg = (
                    "<b>⚠️ Warning:</b> Restart required for this edit to take effect! You will not see the changes in bot vars, the edit will be in database only!\n\n"
                    + msg
                )

            await edit_message(message, msg, buttons.build_menu(1))

            # Set up the edit function
            pfunc = partial(edit_variable, pre_message=message, key=data[2])

            # Set up the return function to preserve the edit state
            rfunc = partial(update_buttons, message, "var", "edit")

            # Launch the event handler to capture user input
            handler_dict[message.chat.id] = True
            await event_handler(client, query, pfunc, rfunc)
            return

        # Special handling for DEFAULT_AI_PROVIDER
        # Removed: DEFAULT_AI_PROVIDER special handling - use DEFAULT_AI_MODEL instead

        # Special handling for DEFAULT_AI_MODEL
        if data[2] == "DEFAULT_AI_MODEL":
            buttons = ButtonMaker()

            # Get available models grouped by provider
            if ai_manager:
                available_models = ai_manager.get_available_models()
            else:
                available_models = {}
            current_model = getattr(Config, "DEFAULT_AI_MODEL", "gpt-4o")

            # Add models grouped by provider (limit to avoid too many buttons)
            model_count = 0
            for models in available_models.values():
                if model_count >= 20:  # Limit total models shown
                    break

                # Add a few models from each group
                for model_id in models[:4]:  # Max 4 models per group
                    if model_count >= 20:
                        break

                    model_info = ai_manager.get_model_info(model_id)
                    display_name = model_info.get("display_name", model_id)

                    # Shorten display name if too long
                    if len(display_name) > 25:
                        display_name = display_name[:22] + "..."

                    # Mark current model
                    if model_id == current_model:
                        display_name = f"🎯 {display_name}"

                    # Add status indicator
                    status = ai_manager.get_model_status(model_id)
                    status_icon = "✅" if status.startswith("✅") else "❌"

                    buttons.data_button(
                        f"{status_icon} {display_name}",
                        f"botset setmodel {model_id}",
                    )
                    model_count += 1

            # Add utility options
            buttons.data_button("🔄 Reset to Default", "botset setmodel default")
            buttons.data_button("Cancel", "botset cancel")

            # Get the current state before updating the UI
            current_state = globals()["state"]
            # Set the state back to what it was
            globals()["state"] = current_state

            await edit_message(
                message,
                f"<b>🤖 Select AI Model</b>\n\n"
                f"🎯 <b>Current:</b> {current_model}\n"
                f"📊 <b>Status:</b> {ai_manager.get_model_status(current_model)}\n\n"
                f"Choose from available models:",
                buttons.build_menu(2),
            )
            return

        # Special handling for IMAGE_WATERMARK_PATH
        if data[2] == "IMAGE_WATERMARK_PATH" and state == "edit":
            # Show a message explaining how to upload an image watermark
            await query.answer(
                "Image watermarks are stored in the database. Please use the 'Upload Image 🖼️' button in the Media Tools > Watermark menu to upload an image watermark.",
                show_alert=True,
            )
            return

        # Handle all other IMAGE_WATERMARK_ settings like normal settings
        if (
            data[2].startswith("IMAGE_WATERMARK_")
            and data[2] != "IMAGE_WATERMARK_PATH"
        ):
            # Use the standard editvar flow for these settings
            await update_buttons(message, data[2], "editvar")
            return

        # Special handling for ADD_ settings
        if data[2].startswith("ADD_"):
            # Get the current state before making changes
            current_state = globals()["state"]

            # Add help text based on the setting
            help_text = ""
            if data[2] == "ADD_PRIORITY":
                help_text = "Send a number between 1-10 to set the priority level for add operations.\n\n<b>Example:</b> <code>7</code>\n\n<b>Default:</b> <code>7</code>\n\n"
            elif data[2] == "ADD_VIDEO_CODEC":
                help_text = "Send the video codec to use for adding video tracks.\n\n<b>Examples:</b> <code>copy</code>, <code>libx264</code>, <code>libx265</code>\n\n<b>Default:</b> <code>copy</code>\n\n"
            elif data[2] == "ADD_VIDEO_INDEX":
                help_text = "Send the index position to add the video track at. Leave empty to append.\n\n<b>Examples:</b> <code>0</code> (first position), <code>1</code> (second position)\n\n<b>Default:</b> Empty (append)\n\n"
            elif data[2] == "ADD_VIDEO_QUALITY":
                help_text = "Send the quality setting for video encoding.\n\n<b>Examples:</b> <code>23</code> (for CRF value), <code>high</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_VIDEO_PRESET":
                help_text = "Send the encoding preset for video.\n\n<b>Examples:</b> <code>medium</code>, <code>slow</code>, <code>fast</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_VIDEO_BITRATE":
                help_text = "Send the bitrate for video encoding.\n\n<b>Examples:</b> <code>5M</code>, <code>10M</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_VIDEO_RESOLUTION":
                help_text = "Send the resolution for video encoding.\n\n<b>Examples:</b> <code>1920x1080</code>, <code>1280x720</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_VIDEO_FPS":
                help_text = "Send the frames per second for video encoding.\n\n<b>Examples:</b> <code>30</code>, <code>60</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_AUDIO_CODEC":
                help_text = "Send the audio codec to use for adding audio tracks.\n\n<b>Examples:</b> <code>copy</code>, <code>aac</code>, <code>libmp3lame</code>\n\n<b>Default:</b> <code>copy</code>\n\n"
            elif data[2] == "ADD_AUDIO_INDEX":
                help_text = "Send the index position to add the audio track at. Leave empty to append.\n\n<b>Examples:</b> <code>0</code> (first position), <code>1</code> (second position)\n\n<b>Default:</b> Empty (append)\n\n"
            elif data[2] == "ADD_AUDIO_BITRATE":
                help_text = "Send the bitrate for audio encoding.\n\n<b>Examples:</b> <code>128k</code>, <code>192k</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_AUDIO_CHANNELS":
                help_text = "Send the number of audio channels.\n\n<b>Examples:</b> <code>2</code> (stereo), <code>1</code> (mono), <code>6</code> (5.1)\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_AUDIO_SAMPLING":
                help_text = "Send the audio sampling rate in Hz.\n\n<b>Examples:</b> <code>44100</code>, <code>48000</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_AUDIO_VOLUME":
                help_text = "Send the volume adjustment factor.\n\n<b>Examples:</b> <code>1.0</code> (normal), <code>0.5</code> (half), <code>2.0</code> (double)\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_SUBTITLE_CODEC":
                help_text = "Send the subtitle codec to use for adding subtitle tracks.\n\n<b>Examples:</b> <code>copy</code>, <code>srt</code>, <code>ass</code>, <code>vtt</code>\n\n<b>Default:</b> <code>copy</code>\n\n"
            elif data[2] == "ADD_SUBTITLE_INDEX":
                help_text = "Send the index position to add the subtitle track at. Leave empty to append.\n\n<b>Examples:</b> <code>0</code> (first position), <code>1</code> (second position)\n\n<b>Default:</b> Empty (append)\n\n"
            elif data[2] == "ADD_SUBTITLE_LANGUAGE":
                help_text = "Send the language code for the subtitle track.\n\n<b>Examples:</b> <code>eng</code>, <code>spa</code>, <code>fre</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_SUBTITLE_ENCODING":
                help_text = "Send the character encoding for subtitle files.\n\n<b>Examples:</b> <code>UTF-8</code>, <code>latin1</code>, <code>cp1252</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_SUBTITLE_FONT":
                help_text = "Send the font name for ASS/SSA subtitles.\n\n<b>Examples:</b> <code>Arial</code>, <code>Times New Roman</code>, <code>DejaVu Sans</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_SUBTITLE_FONT_SIZE":
                help_text = "Send the font size for ASS/SSA subtitles.\n\n<b>Examples:</b> <code>24</code>, <code>18</code>, <code>32</code>\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2] == "ADD_SUBTITLE_HARDSUB_ENABLED":
                help_text = "Enable or disable hardsub (burning subtitles into video).\n\n<b>Hardsub:</b> Subtitles are permanently burned into the video (cannot be turned off)\n<b>Soft subtitles:</b> Subtitles are separate tracks (can be toggled on/off)\n\n<b>Note:</b> Hardsub requires video re-encoding and may reduce quality.\n\n<b>Default:</b> <code>False</code>\n\n"
            elif data[2].startswith("ADD_SUBTITLE_"):
                help_text = "Send a valid value for subtitle settings.\n\n<b>Default:</b> <code>none</code>\n\n"
            elif data[2].startswith("ADD_ATTACHMENT_"):
                help_text = "Send a valid value for attachment settings.\n\n<b>Default:</b> <code>none</code>\n\n"
            else:
                help_text = "Send a valid value for this setting.\n\n"

            # Show the edit message with the current value and help text
            msg = f"{help_text}Send a valid value for <code>{data[2]}</code>.\n\n<b>Current value:</b> <code>{Config.get(data[2])}</code>\n\n<i>Timeout: 60 seconds</i>"
            buttons = ButtonMaker()
            buttons.data_button("⬅️ Back", "botset mediatools_add", "footer")
            buttons.data_button(
                "🔄 Default", f"botset default_add_setting {data[2]}"
            )
            buttons.data_button("❌ Close", "botset close", "footer")

            await edit_message(message, msg, buttons.build_menu(1))

            # Set up the edit function
            pfunc = partial(edit_variable, pre_message=message, key=data[2])

            # Set up the return function to preserve the edit state
            rfunc = partial(update_buttons, message, "mediatools_add", "edit")

            # Launch the event handler to capture user input
            handler_dict[message.chat.id] = True
            await event_handler(client, query, pfunc, rfunc)
            return

        # For settings that have their own menu, we need to use editvar as edit_type
        if data[2].startswith(
            (
                "WATERMARK_",
                "AUDIO_WATERMARK_",
                "SUBTITLE_WATERMARK_",
                "IMAGE_WATERMARK_",
                "MERGE_",
                "METADATA_",
                "TASK_MONITOR_",
                "CONVERT_",
                "COMPRESSION_",
                "TRIM_",
                "EXTRACT_",
                "MISTRAL_",
                "DEEPSEEK_",
                "DEFAULT_AI_",
            )
        ) or data[2] in ["CONCAT_DEMUXER_ENABLED", "FILTER_COMPLEX_ENABLED"]:
            # For all settings
            await update_buttons(message, data[2], "editvar")
        else:
            await update_buttons(message, data[2], data[1])

        # Determine which menu to return to based on the key
        return_menu = "var"  # Default return menu
        if data[2].startswith(
            (
                "WATERMARK_",
                "AUDIO_WATERMARK_",
                "SUBTITLE_WATERMARK_",
                "IMAGE_WATERMARK_",
            )
        ):
            return_menu = "mediatools_watermark"
        elif data[2].startswith("METADATA_"):
            return_menu = "mediatools_metadata"
        elif data[2].startswith("CONVERT_"):
            return_menu = "mediatools_convert"
        elif data[2].startswith("COMPRESSION_"):
            return_menu = "mediatools_compression"
        elif data[2].startswith("TRIM_"):
            return_menu = "mediatools_trim"
        elif data[2].startswith("EXTRACT_"):
            return_menu = "mediatools_extract"
        elif data[2].startswith("REMOVE_"):
            return_menu = "mediatools_remove"
        elif data[2].startswith("ADD_"):
            return_menu = "mediatools_add"
        elif data[2].startswith("TASK_MONITOR_"):
            return_menu = "taskmonitor"
        elif data[2].startswith(("MISTRAL_", "DEEPSEEK_", "DEFAULT_AI_")):
            return_menu = "ai"
        elif data[2].startswith("STREAMRIP_"):
            # For streamrip settings, determine which submenu to return to based on the key
            if data[2] in [
                "STREAMRIP_ENABLED",
                "STREAMRIP_CONCURRENT_DOWNLOADS",
                "STREAMRIP_MAX_SEARCH_RESULTS",
                "STREAMRIP_ENABLE_DATABASE",
                "STREAMRIP_AUTO_CONVERT",
            ]:
                return_menu = "streamrip_general"
            elif data[2] in [
                "STREAMRIP_DEFAULT_QUALITY",
                "STREAMRIP_FALLBACK_QUALITY",
                "STREAMRIP_DEFAULT_CODEC",
                "STREAMRIP_SUPPORTED_CODECS",
                "STREAMRIP_QUALITY_FALLBACK_ENABLED",
            ]:
                return_menu = "streamrip_quality"
            elif (
                (
                    data[2].endswith("_ENABLED")
                    and any(
                        platform in data[2]
                        for platform in ["QOBUZ", "TIDAL", "DEEZER", "SOUNDCLOUD"]
                    )
                )
                or data[2].endswith(
                    (
                        "_EMAIL",
                        "_PASSWORD",
                        "_ARL",
                        "_CLIENT_ID",
                        "_ACCESS_TOKEN",
                        "_REFRESH_TOKEN",
                        "_USER_ID",
                        "_COUNTRY_CODE",
                    )
                )
                or data[2]
                in [
                    "STREAMRIP_QOBUZ_USE_AUTH_TOKEN",
                    "STREAMRIP_QOBUZ_APP_ID",
                    "STREAMRIP_QOBUZ_SECRETS",
                    "STREAMRIP_QOBUZ_QUALITY",
                    "STREAMRIP_TIDAL_QUALITY",
                    "STREAMRIP_DEEZER_QUALITY",
                    "STREAMRIP_SOUNDCLOUD_QUALITY",
                ]
            ):
                return_menu = "streamrip_credentials"
            elif data[2] in [
                "STREAMRIP_MAX_CONNECTIONS",
                "STREAMRIP_REQUESTS_PER_MINUTE",
                "STREAMRIP_SOURCE_SUBDIRECTORIES",
                "STREAMRIP_DISC_SUBDIRECTORIES",
                "STREAMRIP_CONCURRENCY",
                "STREAMRIP_VERIFY_SSL",
            ]:
                return_menu = "streamrip_download"
            elif data[2] in [
                "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS",
                "STREAMRIP_QOBUZ_FILTERS_EXTRAS",
                "STREAMRIP_QOBUZ_FILTERS_REPEATS",
                "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS",
                "STREAMRIP_QOBUZ_FILTERS_FEATURES",
                "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS",
                "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER",
                "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS",
                "STREAMRIP_TIDAL_TOKEN_EXPIRY",
                "STREAMRIP_DEEZER_USE_DEEZLOADER",
                "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS",
                "STREAMRIP_SOUNDCLOUD_APP_VERSION",
                "STREAMRIP_YOUTUBE_QUALITY",
                "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS",
                "STREAMRIP_YOUTUBE_VIDEO_FOLDER",
                "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER",
                "STREAMRIP_LASTFM_ENABLED",
                "STREAMRIP_LASTFM_SOURCE",
                "STREAMRIP_LASTFM_FALLBACK_SOURCE",
            ]:
                return_menu = "streamrip_platforms"
            elif data[2] in [
                "STREAMRIP_DATABASE_DOWNLOADS_ENABLED",
                "STREAMRIP_DATABASE_DOWNLOADS_PATH",
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED",
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
            ]:
                return_menu = "streamrip_database"
            elif data[2] in [
                "STREAMRIP_CONVERSION_ENABLED",
                "STREAMRIP_CONVERSION_CODEC",
                "STREAMRIP_CONVERSION_SAMPLING_RATE",
                "STREAMRIP_CONVERSION_BIT_DEPTH",
                "STREAMRIP_CONVERSION_LOSSY_BITRATE",
            ]:
                return_menu = "streamrip_conversion"
            elif data[2] in [
                "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM",
                "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS",
                "STREAMRIP_METADATA_EXCLUDE",
            ]:
                return_menu = "streamrip_metadata"
            elif data[2] in [
                "STREAMRIP_CLI_TEXT_OUTPUT",
                "STREAMRIP_CLI_PROGRESS_BARS",
                "STREAMRIP_CLI_MAX_SEARCH_RESULTS",
                "STREAMRIP_MISC_CHECK_FOR_UPDATES",
                "STREAMRIP_MISC_VERSION",
            ]:
                return_menu = "streamrip_cli"
            elif data[2] in [
                "STREAMRIP_FILENAME_TEMPLATE",
                "STREAMRIP_FOLDER_TEMPLATE",
                "STREAMRIP_EMBED_COVER_ART",
                "STREAMRIP_SAVE_COVER_ART",
                "STREAMRIP_COVER_ART_SIZE",
                "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH",
                "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH",
                "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER",
                "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
                "STREAMRIP_FILEPATHS_TRACK_FORMAT",
                "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS",
                "STREAMRIP_FILEPATHS_TRUNCATE_TO",
            ]:
                return_menu = "streamrip_advanced"
            else:
                # For any other streamrip settings, default to main streamrip menu
                return_menu = "streamrip"
        elif data[2].startswith("ZOTIFY_"):
            # For zotify settings, determine which submenu to return to based on the key
            if data[2] in [
                "ZOTIFY_ENABLED",
                "ZOTIFY_DOWNLOAD_REAL_TIME",
                "ZOTIFY_REPLACE_EXISTING",
                "ZOTIFY_SKIP_DUPLICATES",
                "ZOTIFY_SKIP_PREVIOUS",
            ]:
                return_menu = "zotify_general"
            elif data[2] in [
                "ZOTIFY_DOWNLOAD_QUALITY",
                "ZOTIFY_AUDIO_FORMAT",
                "ZOTIFY_ARTWORK_SIZE",
                "ZOTIFY_TRANSCODE_BITRATE",
            ]:
                return_menu = "zotify_quality"
            elif data[2] in [
                "ZOTIFY_CREDENTIALS_PATH",
            ]:
                return_menu = "zotify_auth"
            elif data[2] in [
                "ZOTIFY_ALBUM_LIBRARY",
                "ZOTIFY_PODCAST_LIBRARY",
                "ZOTIFY_PLAYLIST_LIBRARY",
            ]:
                return_menu = "zotify_paths"
            elif data[2] in [
                "ZOTIFY_OUTPUT_ALBUM",
                "ZOTIFY_OUTPUT_PLAYLIST_TRACK",
                "ZOTIFY_OUTPUT_PLAYLIST_EPISODE",
                "ZOTIFY_OUTPUT_PODCAST",
                "ZOTIFY_OUTPUT_SINGLE",
            ]:
                return_menu = "zotify_templates"
            elif data[2] in [
                "ZOTIFY_PRINT_PROGRESS",
                "ZOTIFY_PRINT_DOWNLOADS",
                "ZOTIFY_PRINT_ERRORS",
                "ZOTIFY_PRINT_WARNINGS",
                "ZOTIFY_PRINT_SKIPS",
            ]:
                return_menu = "zotify_download"
            elif data[2] in [
                "ZOTIFY_SAVE_METADATA",
                "ZOTIFY_SAVE_GENRE",
                "ZOTIFY_ALL_ARTISTS",
                "ZOTIFY_LYRICS_FILE",
                "ZOTIFY_LYRICS_ONLY",
                "ZOTIFY_SAVE_SUBTITLES",
                "ZOTIFY_CREATE_PLAYLIST_FILE",
            ]:
                return_menu = "zotify_metadata"
            elif data[2] in [
                "ZOTIFY_FFMPEG_PATH",
                "ZOTIFY_FFMPEG_ARGS",
                "ZOTIFY_LANGUAGE",
                "ZOTIFY_MATCH_EXISTING",
            ]:
                return_menu = "zotify_advanced"
            else:
                # For any other zotify settings, default to main zotify menu
                return_menu = "zotify"
        elif data[2].startswith("MERGE_") or data[2] in [
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
        ]:
            # Check if the key is from the merge_config menu
            if data[2].startswith("MERGE_") and any(
                x in data[2]
                for x in [
                    "OUTPUT_FORMAT",
                    "VIDEO_",
                    "AUDIO_",
                    "IMAGE_",
                    "SUBTITLE_",
                    "DOCUMENT_",
                    "METADATA_",
                ]
            ):
                # This is a merge_config setting
                return_menu = "mediatools_merge_config"

                # Check if we need to return to a specific page in mediatools_merge_config
                if message.text and "Page:" in message.text:
                    try:
                        page_info = (
                            message.text.split("Page:")[1].strip().split("/")[0]
                        )
                        page_no = int(page_info) - 1
                        # Set the global merge_config_page variable to ensure we return to the correct page
                        globals()["merge_config_page"] = page_no
                    except (ValueError, IndexError):
                        pass
            elif data[2] in [
                "MERGE_ENABLED",
                "MERGE_PRIORITY",
                "MERGE_THREADING",
                "MERGE_THREAD_NUMBER",
                "MERGE_REMOVE_ORIGINAL",
                "CONCAT_DEMUXER_ENABLED",
                "FILTER_COMPLEX_ENABLED",
            ]:
                # These are from the main merge menu
                return_menu = "mediatools_merge"
                # Check if we need to return to a specific page in mediatools_merge
                if message.text and "Page:" in message.text:
                    try:
                        page_info = (
                            message.text.split("Page:")[1].strip().split("/")[0]
                        )
                        page_no = int(page_info) - 1
                        # Set the global merge_page variable to ensure we return to the correct page
                        globals()["merge_page"] = page_no
                    except (ValueError, IndexError):
                        pass
            else:
                # Default to merge menu for any other merge settings
                return_menu = "mediatools_merge"
                # Check if we need to return to a specific page in mediatools_merge
                if message.text and "Page:" in message.text:
                    try:
                        page_info = (
                            message.text.split("Page:")[1].strip().split("/")[0]
                        )
                        page_no = int(page_info) - 1
                        # Set the global merge_page variable to ensure we return to the correct page
                        globals()["merge_page"] = page_no
                    except (ValueError, IndexError):
                        pass

        # Removed: DEFAULT_AI_PROVIDER special handling

        # For all other settings, proceed with normal edit flow
        pfunc = partial(edit_variable, pre_message=message, key=data[2])

        # Get the current state before making changes
        current_state = globals()["state"]

        # Set up the return function based on the return menu
        # Always preserve the current state
        globals()["state"] = current_state

        # Handle special case for mediatools_merge with pagination
        if (
            return_menu == "mediatools_merge"
            and message.text
            and "Page:" in message.text
        ):
            try:
                page_info = message.text.split("Page:")[1].strip().split("/")[0]
                page_no = int(page_info) - 1
                # Set the global merge_page variable to ensure we return to the correct page
                globals()["merge_page"] = page_no
            except (ValueError, IndexError):
                pass

        # Create the return function with the appropriate menu
        # Make sure we preserve the edit state when returning to the var menu
        rfunc = partial(
            update_buttons,
            message,
            return_menu,
            "edit" if current_state == "edit" else None,
        )

        await event_handler(client, query, pfunc, rfunc)
    # The default_taskmonitor handler is defined elsewhere in the file

    elif data[1] == "default_merge_config":
        await query.answer("Resetting all merge config settings to default...")
        # Reset all merge config settings to default using DEFAULT_VALUES

        # Reset output formats
        Config.MERGE_OUTPUT_FORMAT_VIDEO = DEFAULT_VALUES[
            "MERGE_OUTPUT_FORMAT_VIDEO"
        ]
        Config.MERGE_OUTPUT_FORMAT_AUDIO = DEFAULT_VALUES[
            "MERGE_OUTPUT_FORMAT_AUDIO"
        ]
        Config.MERGE_OUTPUT_FORMAT_IMAGE = DEFAULT_VALUES[
            "MERGE_OUTPUT_FORMAT_IMAGE"
        ]
        Config.MERGE_OUTPUT_FORMAT_DOCUMENT = DEFAULT_VALUES[
            "MERGE_OUTPUT_FORMAT_DOCUMENT"
        ]
        Config.MERGE_OUTPUT_FORMAT_SUBTITLE = DEFAULT_VALUES[
            "MERGE_OUTPUT_FORMAT_SUBTITLE"
        ]

        # Reset video settings
        Config.MERGE_VIDEO_CODEC = DEFAULT_VALUES["MERGE_VIDEO_CODEC"]
        Config.MERGE_VIDEO_QUALITY = DEFAULT_VALUES["MERGE_VIDEO_QUALITY"]
        Config.MERGE_VIDEO_PRESET = DEFAULT_VALUES["MERGE_VIDEO_PRESET"]
        Config.MERGE_VIDEO_CRF = DEFAULT_VALUES["MERGE_VIDEO_CRF"]
        Config.MERGE_VIDEO_PIXEL_FORMAT = DEFAULT_VALUES["MERGE_VIDEO_PIXEL_FORMAT"]
        Config.MERGE_VIDEO_TUNE = DEFAULT_VALUES["MERGE_VIDEO_TUNE"]
        Config.MERGE_VIDEO_FASTSTART = DEFAULT_VALUES["MERGE_VIDEO_FASTSTART"]

        # Reset audio settings
        Config.MERGE_AUDIO_CODEC = DEFAULT_VALUES["MERGE_AUDIO_CODEC"]
        Config.MERGE_AUDIO_BITRATE = DEFAULT_VALUES["MERGE_AUDIO_BITRATE"]
        Config.MERGE_AUDIO_CHANNELS = DEFAULT_VALUES["MERGE_AUDIO_CHANNELS"]
        Config.MERGE_AUDIO_SAMPLING = DEFAULT_VALUES["MERGE_AUDIO_SAMPLING"]
        Config.MERGE_AUDIO_VOLUME = DEFAULT_VALUES["MERGE_AUDIO_VOLUME"]

        # Reset image settings
        Config.MERGE_IMAGE_MODE = DEFAULT_VALUES["MERGE_IMAGE_MODE"]
        Config.MERGE_IMAGE_COLUMNS = DEFAULT_VALUES["MERGE_IMAGE_COLUMNS"]
        Config.MERGE_IMAGE_QUALITY = DEFAULT_VALUES["MERGE_IMAGE_QUALITY"]
        Config.MERGE_IMAGE_DPI = DEFAULT_VALUES["MERGE_IMAGE_DPI"]
        Config.MERGE_IMAGE_RESIZE = DEFAULT_VALUES["MERGE_IMAGE_RESIZE"]
        Config.MERGE_IMAGE_BACKGROUND = DEFAULT_VALUES["MERGE_IMAGE_BACKGROUND"]

        # Reset subtitle settings
        Config.MERGE_SUBTITLE_ENCODING = DEFAULT_VALUES["MERGE_SUBTITLE_ENCODING"]
        Config.MERGE_SUBTITLE_FONT = DEFAULT_VALUES["MERGE_SUBTITLE_FONT"]
        Config.MERGE_SUBTITLE_FONT_SIZE = DEFAULT_VALUES["MERGE_SUBTITLE_FONT_SIZE"]
        Config.MERGE_SUBTITLE_FONT_COLOR = DEFAULT_VALUES[
            "MERGE_SUBTITLE_FONT_COLOR"
        ]
        Config.MERGE_SUBTITLE_BACKGROUND = DEFAULT_VALUES[
            "MERGE_SUBTITLE_BACKGROUND"
        ]

        # Reset document settings
        Config.MERGE_DOCUMENT_PAPER_SIZE = DEFAULT_VALUES[
            "MERGE_DOCUMENT_PAPER_SIZE"
        ]
        Config.MERGE_DOCUMENT_ORIENTATION = DEFAULT_VALUES[
            "MERGE_DOCUMENT_ORIENTATION"
        ]
        Config.MERGE_DOCUMENT_MARGIN = DEFAULT_VALUES["MERGE_DOCUMENT_MARGIN"]

        # Reset metadata settings
        Config.MERGE_METADATA_TITLE = DEFAULT_VALUES["MERGE_METADATA_TITLE"]
        Config.MERGE_METADATA_AUTHOR = DEFAULT_VALUES["MERGE_METADATA_AUTHOR"]
        Config.MERGE_METADATA_COMMENT = DEFAULT_VALUES["MERGE_METADATA_COMMENT"]

        # Update the database with the default values
        await database.update_config(
            {
                # Output formats
                "MERGE_OUTPUT_FORMAT_VIDEO": DEFAULT_VALUES[
                    "MERGE_OUTPUT_FORMAT_VIDEO"
                ],
                "MERGE_OUTPUT_FORMAT_AUDIO": DEFAULT_VALUES[
                    "MERGE_OUTPUT_FORMAT_AUDIO"
                ],
                "MERGE_OUTPUT_FORMAT_IMAGE": DEFAULT_VALUES[
                    "MERGE_OUTPUT_FORMAT_IMAGE"
                ],
                "MERGE_OUTPUT_FORMAT_DOCUMENT": DEFAULT_VALUES[
                    "MERGE_OUTPUT_FORMAT_DOCUMENT"
                ],
                "MERGE_OUTPUT_FORMAT_SUBTITLE": DEFAULT_VALUES[
                    "MERGE_OUTPUT_FORMAT_SUBTITLE"
                ],
                # Video settings
                "MERGE_VIDEO_CODEC": DEFAULT_VALUES["MERGE_VIDEO_CODEC"],
                "MERGE_VIDEO_QUALITY": DEFAULT_VALUES["MERGE_VIDEO_QUALITY"],
                "MERGE_VIDEO_PRESET": DEFAULT_VALUES["MERGE_VIDEO_PRESET"],
                "MERGE_VIDEO_CRF": DEFAULT_VALUES["MERGE_VIDEO_CRF"],
                "MERGE_VIDEO_PIXEL_FORMAT": DEFAULT_VALUES[
                    "MERGE_VIDEO_PIXEL_FORMAT"
                ],
                "MERGE_VIDEO_TUNE": DEFAULT_VALUES["MERGE_VIDEO_TUNE"],
                "MERGE_VIDEO_FASTSTART": DEFAULT_VALUES["MERGE_VIDEO_FASTSTART"],
                # Audio settings
                "MERGE_AUDIO_CODEC": DEFAULT_VALUES["MERGE_AUDIO_CODEC"],
                "MERGE_AUDIO_BITRATE": DEFAULT_VALUES["MERGE_AUDIO_BITRATE"],
                "MERGE_AUDIO_CHANNELS": DEFAULT_VALUES["MERGE_AUDIO_CHANNELS"],
                "MERGE_AUDIO_SAMPLING": DEFAULT_VALUES["MERGE_AUDIO_SAMPLING"],
                "MERGE_AUDIO_VOLUME": DEFAULT_VALUES["MERGE_AUDIO_VOLUME"],
                # Image settings
                "MERGE_IMAGE_MODE": DEFAULT_VALUES["MERGE_IMAGE_MODE"],
                "MERGE_IMAGE_COLUMNS": DEFAULT_VALUES["MERGE_IMAGE_COLUMNS"],
                "MERGE_IMAGE_QUALITY": DEFAULT_VALUES["MERGE_IMAGE_QUALITY"],
                "MERGE_IMAGE_DPI": DEFAULT_VALUES["MERGE_IMAGE_DPI"],
                "MERGE_IMAGE_RESIZE": DEFAULT_VALUES["MERGE_IMAGE_RESIZE"],
                "MERGE_IMAGE_BACKGROUND": DEFAULT_VALUES["MERGE_IMAGE_BACKGROUND"],
                # Subtitle settings
                "MERGE_SUBTITLE_ENCODING": DEFAULT_VALUES["MERGE_SUBTITLE_ENCODING"],
                "MERGE_SUBTITLE_FONT": DEFAULT_VALUES["MERGE_SUBTITLE_FONT"],
                "MERGE_SUBTITLE_FONT_SIZE": DEFAULT_VALUES[
                    "MERGE_SUBTITLE_FONT_SIZE"
                ],
                "MERGE_SUBTITLE_FONT_COLOR": DEFAULT_VALUES[
                    "MERGE_SUBTITLE_FONT_COLOR"
                ],
                "MERGE_SUBTITLE_BACKGROUND": DEFAULT_VALUES[
                    "MERGE_SUBTITLE_BACKGROUND"
                ],
                # Document settings
                "MERGE_DOCUMENT_PAPER_SIZE": DEFAULT_VALUES[
                    "MERGE_DOCUMENT_PAPER_SIZE"
                ],
                "MERGE_DOCUMENT_ORIENTATION": DEFAULT_VALUES[
                    "MERGE_DOCUMENT_ORIENTATION"
                ],
                "MERGE_DOCUMENT_MARGIN": DEFAULT_VALUES["MERGE_DOCUMENT_MARGIN"],
                # Metadata settings
                "MERGE_METADATA_TITLE": DEFAULT_VALUES["MERGE_METADATA_TITLE"],
                "MERGE_METADATA_AUTHOR": DEFAULT_VALUES["MERGE_METADATA_AUTHOR"],
                "MERGE_METADATA_COMMENT": DEFAULT_VALUES["MERGE_METADATA_COMMENT"],
            }
        )
        # Keep the current page and state
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state

        # Maintain the current page when returning to the merge menu
        if "merge_page" in globals():
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
        else:
            await update_buttons(message, "mediatools_merge", page=0)
    elif data[1] in [
        "var",
        "aria",
        "qbit",
        "nzb",
        "nzbserver",
        "mediatools",
        "mediatools_watermark",
        "mediatools_merge",
        "mediatools_merge_config",
        "mediatools_metadata",
        "mediatools_convert",
        "mediatools_compression",
        "mediatools_trim",
        "mediatools_extract",
        "mediatools_remove",
        "mediatools_add",
        "ai",
        "ai_models",
        "ai_providers",
        "ai_plugins",
        "ai_conversation",
        "ai_advanced",
        "taskmonitor",
        "operations",
        "streamrip",
        "streamrip_general",
        "streamrip_quality",
        "streamrip_credentials",
        "streamrip_download",
        "streamrip_platforms",
        "streamrip_database",
        "streamrip_conversion",
        "streamrip_cli",
        "streamrip_advanced",
        "streamrip_config",
        "gallerydl",
        "gallerydl_general",
        "gallerydl_auth",
        "gallerydl_download",
        "zotify",
        "zotify_general",
        "zotify_quality",
        "zotify_auth",
        "zotify_paths",
        "zotify_templates",
        "zotify_download",
        "zotify_metadata",
        "zotify_advanced",
    ] or data[1].startswith(
        "nzbser",
    ):
        if data[1] == "nzbserver":
            globals()["start"] = 0
        await query.answer()
        # Force refresh of Config.MEDIA_TOOLS_ENABLED from database before updating UI
        if hasattr(Config, "MEDIA_TOOLS_ENABLED"):
            try:
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    {"MEDIA_TOOLS_ENABLED": 1, "_id": 0},
                )
                if db_config and "MEDIA_TOOLS_ENABLED" in db_config:
                    # Update the Config object with the current value from database
                    db_value = db_config["MEDIA_TOOLS_ENABLED"]
                    if db_value != Config.MEDIA_TOOLS_ENABLED:
                        Config.MEDIA_TOOLS_ENABLED = db_value
            except Exception:
                pass

        await update_buttons(message, data[1])
    elif data[1] == "resetvar":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        value = ""
        if data[2] in DEFAULT_VALUES:
            value = DEFAULT_VALUES[data[2]]
        elif (
            data[2] == "PAID_CHANNEL_ID"
            or data[2] == "TOKEN_TIMEOUT"
            or data[2] == "LOG_CHAT_ID"
            or data[2] == "OWNER_ID"
            or data[2] == "TELEGRAM_API"
            or data[2] in ["QUEUE_ALL", "QUEUE_DOWNLOAD", "QUEUE_UPLOAD"]
        ):
            value = 0
        elif data[2] == "EXCLUDED_EXTENSIONS":
            excluded_extensions.clear()
            excluded_extensions.extend(["aria2", "!qB"])
        elif data[2] == "TORRENT_TIMEOUT":
            await TorrentManager.change_aria2_option("bt-stop-timeout", "0")
            await database.update_aria2("bt-stop-timeout", "0")
        elif data[2] == "PIL_MEMORY_LIMIT":
            value = 2048  # Default to 2GB
        elif data[2] == "BASE_URL":
            await (
                await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
            ).wait()
        elif data[2] == "BASE_URL_PORT":
            value = 80
            # Kill any running web server
            with contextlib.suppress(Exception):
                await (
                    await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
                ).wait()

            # Update Config.BASE_URL_PORT first
            Config.BASE_URL_PORT = value

            # Only start web server if port is not 0
            if value != 0:
                await create_subprocess_shell(
                    f"gunicorn -k uvicorn.workers.UvicornWorker -w 1 web.wserver:app --bind 0.0.0.0:{value}",
                )
            else:
                # Double-check to make sure no web server is running
                try:
                    # Use pgrep to check if any gunicorn processes are still running
                    process = await create_subprocess_exec(
                        "pgrep", "-f", "gunicorn", stdout=-1
                    )
                    stdout, _ = await process.communicate()
                    if stdout:
                        await (
                            await create_subprocess_exec(
                                "pkill", "-9", "-f", "gunicorn"
                            )
                        ).wait()
                except Exception:
                    pass

        elif data[2] == "RCLONE_SERVE_PORT":
            value = 8080
            # Update Config.RCLONE_SERVE_PORT first
            Config.RCLONE_SERVE_PORT = value
            # Restart rclone serve
            await rclone_serve_booter()
        elif data[2] == "GDRIVE_ID":
            if drives_names and drives_names[0] == "Main":
                drives_names.pop(0)
                drives_ids.pop(0)
                index_urls.pop(0)
        elif data[2] == "INDEX_URL":
            if drives_names and drives_names[0] == "Main":
                index_urls[0] = ""
        elif data[2] == "INCOMPLETE_TASK_NOTIFIER":
            await database.trunc_table("tasks")
        elif data[2] in ["JD_EMAIL", "JD_PASS"]:
            await create_subprocess_exec("pkill", "-9", "-f", "java")
        elif data[2] == "USENET_SERVERS":
            for s in Config.USENET_SERVERS:
                await sabnzbd_client.delete_config("servers", s["name"])
        elif data[2] == "AUTHORIZED_CHATS":
            auth_chats.clear()
        elif data[2] == "SUDO_USERS":
            sudo_users.clear()
        Config.set(data[2], value)

        # Set the state back to what it was
        globals()["state"] = current_state

        # Return to the previous menu instead of always going to "var"
        # This makes the Default button behavior consistent with setting a value

        # First, try to determine the menu based on the key prefix
        previous_menu = "var"  # Default to var menu

        # Determine which menu to return to based on the key prefix
        if data[2].startswith(
            (
                "WATERMARK_",
                "AUDIO_WATERMARK_",
                "SUBTITLE_WATERMARK_",
                "IMAGE_WATERMARK_",
            )
        ):
            previous_menu = "mediatools_watermark"
        elif data[2].startswith("METADATA_"):
            previous_menu = "mediatools_metadata"
        elif data[2].startswith("CONVERT_"):
            previous_menu = "mediatools_convert"
        elif data[2].startswith("COMPRESSION_"):
            previous_menu = "mediatools_compression"
        elif data[2].startswith("TRIM_"):
            previous_menu = "mediatools_trim"
        elif data[2].startswith("EXTRACT_"):
            previous_menu = "mediatools_extract"
        elif data[2].startswith("REMOVE_"):
            previous_menu = "mediatools_remove"
        elif data[2].startswith("ADD_"):
            previous_menu = "mediatools_add"
        elif data[2].startswith("SWAP_"):
            previous_menu = "mediatools_swap"
        elif data[2].startswith("TASK_MONITOR_"):
            previous_menu = "taskmonitor"
        elif data[2].startswith(("MISTRAL_", "DEEPSEEK_", "DEFAULT_AI_")):
            previous_menu = "ai"
        elif data[2].startswith("STREAMRIP_"):
            # For streamrip settings, determine which submenu to return to based on the key
            if data[2] in [
                "STREAMRIP_ENABLED",
                "STREAMRIP_CONCURRENT_DOWNLOADS",
                "STREAMRIP_MAX_SEARCH_RESULTS",
                "STREAMRIP_ENABLE_DATABASE",
                "STREAMRIP_AUTO_CONVERT",
            ]:
                previous_menu = "streamrip_general"
            elif data[2] in [
                "STREAMRIP_DEFAULT_QUALITY",
                "STREAMRIP_FALLBACK_QUALITY",
                "STREAMRIP_DEFAULT_CODEC",
                "STREAMRIP_SUPPORTED_CODECS",
                "STREAMRIP_QUALITY_FALLBACK_ENABLED",
            ]:
                previous_menu = "streamrip_quality"
            elif (
                (
                    data[2].endswith("_ENABLED")
                    and any(
                        platform in data[2]
                        for platform in ["QOBUZ", "TIDAL", "DEEZER", "SOUNDCLOUD"]
                    )
                )
                or data[2].endswith(
                    (
                        "_EMAIL",
                        "_PASSWORD",
                        "_ARL",
                        "_CLIENT_ID",
                        "_ACCESS_TOKEN",
                        "_REFRESH_TOKEN",
                        "_USER_ID",
                        "_COUNTRY_CODE",
                    )
                )
                or data[2]
                in [
                    "STREAMRIP_QOBUZ_USE_AUTH_TOKEN",
                    "STREAMRIP_QOBUZ_APP_ID",
                    "STREAMRIP_QOBUZ_SECRETS",
                    "STREAMRIP_QOBUZ_QUALITY",
                    "STREAMRIP_TIDAL_QUALITY",
                    "STREAMRIP_DEEZER_QUALITY",
                    "STREAMRIP_SOUNDCLOUD_QUALITY",
                ]
            ):
                previous_menu = "streamrip_credentials"
            elif data[2] in [
                "STREAMRIP_MAX_CONNECTIONS",
                "STREAMRIP_REQUESTS_PER_MINUTE",
                "STREAMRIP_SOURCE_SUBDIRECTORIES",
                "STREAMRIP_DISC_SUBDIRECTORIES",
                "STREAMRIP_CONCURRENCY",
                "STREAMRIP_VERIFY_SSL",
            ]:
                previous_menu = "streamrip_download"
            elif data[2] in [
                "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS",
                "STREAMRIP_QOBUZ_FILTERS_EXTRAS",
                "STREAMRIP_QOBUZ_FILTERS_REPEATS",
                "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS",
                "STREAMRIP_QOBUZ_FILTERS_FEATURES",
                "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS",
                "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER",
                "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS",
                "STREAMRIP_TIDAL_TOKEN_EXPIRY",
                "STREAMRIP_DEEZER_USE_DEEZLOADER",
                "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS",
                "STREAMRIP_SOUNDCLOUD_APP_VERSION",
                "STREAMRIP_YOUTUBE_QUALITY",
                "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS",
                "STREAMRIP_YOUTUBE_VIDEO_FOLDER",
                "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER",
                "STREAMRIP_LASTFM_ENABLED",
                "STREAMRIP_LASTFM_SOURCE",
                "STREAMRIP_LASTFM_FALLBACK_SOURCE",
            ]:
                previous_menu = "streamrip_platforms"
            elif data[2] in [
                "STREAMRIP_DATABASE_DOWNLOADS_ENABLED",
                "STREAMRIP_DATABASE_DOWNLOADS_PATH",
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED",
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
            ]:
                previous_menu = "streamrip_database"
            elif data[2] in [
                "STREAMRIP_CONVERSION_ENABLED",
                "STREAMRIP_CONVERSION_CODEC",
                "STREAMRIP_CONVERSION_SAMPLING_RATE",
                "STREAMRIP_CONVERSION_BIT_DEPTH",
                "STREAMRIP_CONVERSION_LOSSY_BITRATE",
            ]:
                previous_menu = "streamrip_conversion"
            elif data[2] in [
                "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM",
                "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS",
                "STREAMRIP_METADATA_EXCLUDE",
            ]:
                previous_menu = "streamrip_metadata"
            elif data[2] in [
                "STREAMRIP_CLI_TEXT_OUTPUT",
                "STREAMRIP_CLI_PROGRESS_BARS",
                "STREAMRIP_CLI_MAX_SEARCH_RESULTS",
                "STREAMRIP_MISC_CHECK_FOR_UPDATES",
                "STREAMRIP_MISC_VERSION",
            ]:
                previous_menu = "streamrip_cli"
            elif data[2] in [
                "STREAMRIP_FILENAME_TEMPLATE",
                "STREAMRIP_FOLDER_TEMPLATE",
                "STREAMRIP_EMBED_COVER_ART",
                "STREAMRIP_SAVE_COVER_ART",
                "STREAMRIP_COVER_ART_SIZE",
                "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH",
                "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH",
                "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER",
                "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
                "STREAMRIP_FILEPATHS_TRACK_FORMAT",
                "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS",
                "STREAMRIP_FILEPATHS_TRUNCATE_TO",
            ]:
                previous_menu = "streamrip_advanced"
            else:
                # For any other streamrip settings, default to main streamrip menu
                previous_menu = "streamrip"
        elif data[2].startswith("MERGE_") or data[2] in [
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
        ]:
            # Check if the key is from the merge_config menu
            if data[2].startswith("MERGE_") and any(
                x in data[2]
                for x in [
                    "OUTPUT_FORMAT",
                    "VIDEO_",
                    "AUDIO_",
                    "IMAGE_",
                    "SUBTITLE_",
                    "DOCUMENT_",
                    "METADATA_",
                ]
            ):
                previous_menu = "mediatools_merge_config"
            else:
                previous_menu = "mediatools_merge"

        # If we couldn't determine the menu from the key, try to determine it from the message text
        elif message.text:
            if "Media Tools" in message.text:
                previous_menu = "mediatools"
            elif "Watermark" in message.text:
                previous_menu = "mediatools_watermark"
            elif "Merge" in message.text:
                previous_menu = "mediatools_merge"
            elif "Convert" in message.text:
                previous_menu = "mediatools_convert"
            elif "Compression" in message.text:
                previous_menu = "mediatools_compression"
            elif "Trim" in message.text:
                previous_menu = "mediatools_trim"
            elif "Extract" in message.text:
                previous_menu = "mediatools_extract"
            elif "Remove" in message.text:
                previous_menu = "mediatools_remove"
            elif "Add" in message.text:
                previous_menu = "mediatools_add"
            elif "Task Monitor" in message.text:
                previous_menu = "taskmonitor"
            elif "qBittorrent" in message.text:
                previous_menu = "qbit"
            elif "Aria2c" in message.text:
                previous_menu = "aria"
            elif "Sabnzbd" in message.text:
                previous_menu = "nzb"
            elif "AI Settings" in message.text:
                previous_menu = "ai"
            elif "JD Sync" in message.text:
                previous_menu = "syncjd"
            elif "Private Files" in message.text:
                previous_menu = "private"

        # Return to the previous menu without preserving edit state
        # This makes the Default button behavior exactly like when setting a value
        await update_buttons(message, previous_menu)

        if data[2] == "DATABASE_URL":
            await database.disconnect()
        await database.update_config({data[2]: value})
        if data[2] in ["QUEUE_ALL", "QUEUE_DOWNLOAD", "QUEUE_UPLOAD"]:
            await start_from_queued()
        elif data[2] in [
            "RCLONE_SERVE_URL",
            "RCLONE_SERVE_PORT",
            "RCLONE_SERVE_USER",
            "RCLONE_SERVE_PASS",
        ]:
            await rclone_serve_booter()
    elif data[1] == "syncaria":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        aria2_options.clear()
        await update_aria2_options()

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "aria")
    elif data[1] == "syncqbit":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        qbit_options.clear()
        await update_qb_options()

        # Set the state back to what it was
        globals()["state"] = current_state
        await database.save_qbit_settings()
    elif data[1] == "resetnzb":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        res = await sabnzbd_client.set_config_default(data[2])
        nzb_options[data[2]] = res["config"]["misc"][data[2]]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "nzb")

        await database.update_nzb_config()
    elif data[1] == "syncnzb":
        await query.answer(
            "Syncronization Started. It takes up to 2 sec!",
            show_alert=True,
        )
        # Get the current state before making changes
        current_state = globals()["state"]

        nzb_options.clear()
        await update_nzb_options()

        # Set the state back to what it was
        globals()["state"] = current_state
        await database.update_nzb_config()
    elif data[1] == "emptyaria":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        aria2_options[data[2]] = ""

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "aria")

        await TorrentManager.change_aria2_option(data[2], "")
        await database.update_aria2(data[2], "")
    elif data[1] == "emptyqbit":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        value = ""
        if isinstance(qbit_options[data[2]], bool):
            value = False
        elif isinstance(qbit_options[data[2]], int):
            value = 0
        elif isinstance(qbit_options[data[2]], float):
            value = 0.0
        await TorrentManager.qbittorrent.app.set_preferences({data[2]: value})
        qbit_options[data[2]] = value

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "qbit")

        await database.update_qbittorrent(data[2], value)
    elif data[1] == "emptynzb":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        res = await sabnzbd_client.set_config("misc", data[2], "")
        nzb_options[data[2]] = res["config"]["misc"][data[2]]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "nzb")

        await database.update_nzb_config()
    elif data[1] == "remser":
        # Get the current state before making changes
        current_state = globals()["state"]

        index = int(data[2])
        # Check if index is valid before accessing Config.USENET_SERVERS
        if 0 <= index < len(Config.USENET_SERVERS):
            await sabnzbd_client.delete_config(
                "servers",
                Config.USENET_SERVERS[index]["name"],
            )
            del Config.USENET_SERVERS[index]
            await database.update_config({"USENET_SERVERS": Config.USENET_SERVERS})
        else:
            # Handle invalid index
            await query.answer(
                "Invalid server index. Please go back and try again.",
                show_alert=True,
            )
        # Always update the UI
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "nzbserver")
    elif data[1] == "watermark_text":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state

        # Use the stored page if available
        if message.chat.id and f"{message.chat.id}_watermark_page" in handler_dict:
            page = handler_dict[f"{message.chat.id}_watermark_page"]
            # Use stored page for watermark_text menu
            await update_buttons(message, "mediatools_watermark_text", page=page)
        else:
            # Otherwise use the global variable or default to page 0
            page = globals().get("watermark_text_page", 0)
            # Store the page in handler_dict for future reference
            if message.chat.id:
                handler_dict[f"{message.chat.id}_watermark_page"] = page
            await update_buttons(message, "mediatools_watermark_text", page=page)

    elif data[1] == "private":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[1])
    elif data[1] == "private_set":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state

        # Create a message for file upload
        buttons = ButtonMaker()
        buttons.data_button("❌ Cancel", "botset private")

        await edit_message(
            message,
            """<b>📤 Upload Private Files</b>

<b>Send any of these files:</b>
• config.py
• token.pickle
• token_sa.pickle
• youtube_token.pickle
• rclone.conf
• accounts.zip
• list_drives.txt
• cookies.txt
• .netrc
• shorteners.txt
• streamrip_config.toml
• zotify_credentials.json
• spotify_credentials.json
• Any other private file

<b>Note:</b>
• Changing .netrc will not take effect for aria2c until restart
• streamrip_config.toml will be used for custom streamrip configuration
• zotify_credentials.json will be used for Spotify authentication
• youtube_token.pickle will be used for YouTube uploads
• shorteners.txt will be used for URL shortening services

<i>Timeout: 60 seconds</i>""",
            buttons.build_menu(1),
        )

        pfunc = partial(update_private_file, pre_message=message)
        rfunc = partial(update_buttons, message, "private")
        await event_handler(client, query, pfunc, rfunc, True)
    elif data[1] == "private_view":
        await query.answer()
        # Get available private files
        available_files = await database.get_private_files()

        # Filter to only show files that actually exist somewhere
        existing_files = {}
        for file_name, file_info in available_files.items():
            if (
                file_info["exists_db"]
                or file_info["exists_fs"]
                or (
                    file_name == "accounts.zip"
                    and file_info.get("accounts_dir_exists", False)
                )
            ):
                existing_files[file_name] = file_info

        if not existing_files:
            await query.answer("No private files available!", show_alert=True)
            return

        # Create buttons for each available file
        buttons = ButtonMaker()
        for file_name in existing_files:
            display_name = file_name.replace("_", " ").title()
            if file_name == ".netrc":
                display_name = "Netrc"
            elif file_name == "config.py":
                display_name = "Config"
            elif file_name == "token_sa.pickle":
                display_name = "SA Token"
            elif file_name == "shorteners.txt":
                display_name = "Shorteners"
            elif file_name == "streamrip_config.toml":
                display_name = "Streamrip Config"
            elif file_name == "zotify_credentials.json":
                display_name = "Zotify Credentials"
            elif file_name == "spotify_credentials.json":
                display_name = "Spotify Credentials"
            buttons.data_button(
                f"📄 {display_name}", f"botset private_send {file_name}"
            )

        buttons.data_button("⬅️ Back", "botset private", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        await edit_message(
            message,
            f"""<b>👁️ View Private Files</b>

<b>Available Files ({len(existing_files)}):</b>
Click on any file to download it.

<b>Note:</b> Files will be sent as documents in this chat.""",
            buttons.build_menu(2),
        )
    elif data[1] == "private_delete":
        await query.answer()
        # Get available private files
        available_files = await database.get_private_files()

        # Filter to only show files that actually exist somewhere
        existing_files = {}
        for file_name, file_info in available_files.items():
            if (
                file_info["exists_db"]
                or file_info["exists_fs"]
                or (
                    file_name == "accounts.zip"
                    and file_info.get("accounts_dir_exists", False)
                )
            ):
                existing_files[file_name] = file_info

        if not existing_files:
            await query.answer(
                "No private files available to delete!", show_alert=True
            )
            return

        # Create buttons for each available file
        buttons = ButtonMaker()
        for file_name in existing_files:
            display_name = file_name.replace("_", " ").title()
            if file_name == ".netrc":
                display_name = "Netrc"
            elif file_name == "config.py":
                display_name = "Config"
            elif file_name == "token_sa.pickle":
                display_name = "SA Token"
            elif file_name == "shorteners.txt":
                display_name = "Shorteners"
            elif file_name == "streamrip_config.toml":
                display_name = "Streamrip Config"
            elif file_name == "zotify_credentials.json":
                display_name = "Zotify Credentials"
            elif file_name == "spotify_credentials.json":
                display_name = "Spotify Credentials"
            buttons.data_button(
                f"🗑️ {display_name}", f"botset private_confirm_delete {file_name}"
            )

        # Add "Delete All" button
        buttons.data_button("🗑️ Delete All", "botset private_confirm_delete_all")
        buttons.data_button("⬅️ Back", "botset private", "footer")
        buttons.data_button("❌ Close", "botset close", "footer")

        await edit_message(
            message,
            f"""<b>🗑️ Delete Private Files</b>

<b>Available Files ({len(existing_files)}):</b>
Click on any file to delete it.

<b>⚠️ Warning:</b> This action cannot be undone!""",
            buttons.build_menu(2),
        )
    elif data[1] == "private_send":
        await query.answer()
        file_name = data[2]

        try:
            # Check if file exists in filesystem first
            if await aiopath.exists(file_name):
                await send_file(message, file_name, f"📄 {file_name}")
            # Special handling for accounts.zip - create from accounts directory if it exists
            elif file_name == "accounts.zip" and await aiopath.exists("accounts"):
                # Create accounts.zip from accounts directory
                await (
                    await create_subprocess_exec(
                        "7z", "a", "accounts.zip", "accounts/*.json"
                    )
                ).wait()
                if await aiopath.exists("accounts.zip"):
                    await send_file(message, file_name, f"📄 {file_name}")
                    # Update database with the newly created file
                    await database.update_private_file("accounts.zip")
                else:
                    await query.answer(
                        "Failed to create accounts.zip from directory!",
                        show_alert=True,
                    )
                    return
            else:
                # Try to get from database
                db_files = await database.db.settings.files.find_one(
                    {"_id": TgClient.ID}
                )
                if db_files:
                    db_key = file_name.replace(".", "__")
                    if db_files.get(db_key):
                        # Write file from database to filesystem temporarily
                        async with aiopen(file_name, "wb") as f:
                            await f.write(db_files[db_key])
                        await send_file(message, file_name, f"📄 {file_name}")
                        # Clean up temporary file
                        await remove(file_name)
                    else:
                        await query.answer(
                            f"File {file_name} not found!", show_alert=True
                        )
                        return
                else:
                    await query.answer(
                        f"File {file_name} not found!", show_alert=True
                    )
                    return

            await query.answer(f"File {file_name} sent successfully!")

        except Exception as e:
            LOGGER.error(f"Error sending private file {file_name}: {e}")
            await query.answer(f"Error sending file {file_name}!", show_alert=True)
    elif data[1] == "private_confirm_delete":
        await query.answer()

        if data[2] == "all":
            # Confirm delete all
            buttons = ButtonMaker()
            buttons.data_button(
                "✅ Yes, Delete All", "botset private_delete_all_confirmed"
            )
            buttons.data_button("❌ Cancel", "botset private_delete")

            await edit_message(
                message,
                """<b>⚠️ Confirm Delete All Private Files</b>

Are you sure you want to delete ALL private files?

<b>This will remove:</b>
• All files from the database
• All files from the filesystem
• This action cannot be undone!

<b>Files that will be deleted:</b>
• config.py, token.pickle, token_sa.pickle, youtube_token.pickle
• rclone.conf, accounts.zip, list_drives.txt
• cookies.txt, .netrc, shorteners.txt
• streamrip_config.toml, zotify_credentials.json, spotify_credentials.json
• Any other private files""",
                buttons.build_menu(1),
            )
        else:
            # Confirm delete single file
            file_name = data[2]
            display_name = file_name.replace("_", " ").title()
            if file_name == ".netrc":
                display_name = "Netrc"
            elif file_name == "config.py":
                display_name = "Config"
            elif file_name == "token_sa.pickle":
                display_name = "SA Token"
            elif file_name == "shorteners.txt":
                display_name = "Shorteners"
            elif file_name == "streamrip_config.toml":
                display_name = "Streamrip Config"
            elif file_name == "zotify_credentials.json":
                display_name = "Zotify Credentials"
            elif file_name == "spotify_credentials.json":
                display_name = "Spotify Credentials"

            buttons = ButtonMaker()
            buttons.data_button(
                "✅ Yes, Delete", f"botset private_delete_confirmed {file_name}"
            )
            buttons.data_button("❌ Cancel", "botset private_delete")

            await edit_message(
                message,
                f"""<b>⚠️ Confirm Delete File</b>

Are you sure you want to delete <b>{display_name}</b>?

<b>File:</b> <code>{file_name}</code>

<b>This will remove:</b>
• File from the database
• File from the filesystem
• This action cannot be undone!""",
                buttons.build_menu(1),
            )
    elif data[1] == "private_delete_confirmed":
        await query.answer()
        file_name = data[2]

        try:
            # Delete from filesystem if exists
            if await aiopath.exists(file_name):
                await remove(file_name)

            # Delete from database
            db_path = file_name.replace(".", "__")
            await database.db.settings.files.update_one(
                {"_id": TgClient.ID},
                {"$unset": {db_path: ""}},
                upsert=True,
            )

            # Handle special file deletions (same logic as update_private_file)
            if file_name == "accounts.zip":
                if await aiopath.exists("accounts"):
                    await rmtree("accounts", ignore_errors=True)
                if await aiopath.exists("rclone_sa"):
                    await rmtree("rclone_sa", ignore_errors=True)
                Config.USE_SERVICE_ACCOUNTS = False
                await database.update_config({"USE_SERVICE_ACCOUNTS": False})
            elif file_name in [".netrc", "netrc"]:
                await (await create_subprocess_exec("touch", ".netrc")).wait()
                await (await create_subprocess_exec("chmod", "600", ".netrc")).wait()
                await (
                    await create_subprocess_exec("cp", ".netrc", "/root/.netrc")
                ).wait()
            elif file_name == "streamrip_config.toml":
                try:
                    from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                        streamrip_config,
                    )

                    success = await streamrip_config.delete_custom_config_from_db()
                    if success:
                        await streamrip_config.initialize()
                        LOGGER.info(
                            "Streamrip custom config deleted, reverted to default"
                        )
                except Exception as e:
                    LOGGER.error(f"Error handling streamrip config deletion: {e}")
            elif file_name == "zotify_credentials.json":
                try:
                    from pathlib import Path

                    user_id = getattr(Config, "OWNER_ID", 0)

                    if database.db is not None:
                        try:
                            await database.db.users.update_one(
                                {"_id": user_id},
                                {"$unset": {"ZOTIFY_CREDENTIALS": ""}},
                            )
                        except Exception as e:
                            LOGGER.error(
                                f"Error clearing Zotify credentials from database: {e}"
                            )

                    credentials_path = (
                        Config.ZOTIFY_CREDENTIALS_PATH or "./zotify_credentials.json"
                    )
                    creds_file = Path(credentials_path)
                    if creds_file.exists():
                        creds_file.unlink()
                except Exception as e:
                    LOGGER.error(f"Error handling Zotify credentials deletion: {e}")

            await query.answer(f"File {file_name} deleted successfully!")
            # Return to private files menu
            await update_buttons(message, "private")

        except Exception as e:
            LOGGER.error(f"Error deleting private file {file_name}: {e}")
            await query.answer(f"Error deleting file {file_name}!", show_alert=True)
    elif data[1] == "private_delete_all_confirmed":
        await query.answer()

        try:
            # Get all available files first
            available_files = await database.get_private_files()

            # Filter to only delete files that actually exist somewhere
            existing_files = {}
            for file_name, file_info in available_files.items():
                if (
                    file_info["exists_db"]
                    or file_info["exists_fs"]
                    or (
                        file_name == "accounts.zip"
                        and file_info.get("accounts_dir_exists", False)
                    )
                ):
                    existing_files[file_name] = file_info

            deleted_count = 0

            # Delete each existing file
            for file_name in existing_files:
                try:
                    # Delete from filesystem if exists
                    if await aiopath.exists(file_name):
                        await remove(file_name)

                    # Delete from database
                    db_path = file_name.replace(".", "__")
                    await database.db.settings.files.update_one(
                        {"_id": TgClient.ID},
                        {"$unset": {db_path: ""}},
                        upsert=True,
                    )
                    deleted_count += 1

                except Exception as e:
                    LOGGER.error(f"Error deleting file {file_name}: {e}")

            # Handle special cleanup
            try:
                # Clean up accounts and rclone_sa directories
                if await aiopath.exists("accounts"):
                    await rmtree("accounts", ignore_errors=True)
                if await aiopath.exists("rclone_sa"):
                    await rmtree("rclone_sa", ignore_errors=True)

                # Reset service accounts config
                Config.USE_SERVICE_ACCOUNTS = False
                await database.update_config({"USE_SERVICE_ACCOUNTS": False})

                # Reset netrc
                await (await create_subprocess_exec("touch", ".netrc")).wait()
                await (await create_subprocess_exec("chmod", "600", ".netrc")).wait()
                await (
                    await create_subprocess_exec("cp", ".netrc", "/root/.netrc")
                ).wait()

                # Reset streamrip config
                try:
                    from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                        streamrip_config,
                    )

                    await streamrip_config.delete_custom_config_from_db()
                    await streamrip_config.initialize()
                except Exception as e:
                    LOGGER.error(f"Error resetting streamrip config: {e}")

                # Clear zotify credentials
                try:
                    user_id = getattr(Config, "OWNER_ID", 0)
                    if database.db is not None:
                        await database.db.users.update_one(
                            {"_id": user_id},
                            {"$unset": {"ZOTIFY_CREDENTIALS": ""}},
                        )
                except Exception as e:
                    LOGGER.error(f"Error clearing Zotify credentials: {e}")

            except Exception as e:
                LOGGER.error(f"Error during special cleanup: {e}")

            await query.answer(
                f"Successfully deleted {deleted_count} private files!"
            )
            # Return to private files menu
            await update_buttons(message, "private")

        except Exception as e:
            LOGGER.error(f"Error deleting all private files: {e}")
            await query.answer("Error deleting files!", show_alert=True)
    elif data[1] == "private_sync_db":
        await query.answer()

        try:
            # Show syncing message
            await edit_message(
                message,
                """<b>🔄 Syncing Private Files to Database</b>

⏳ Checking filesystem files and syncing to database...

<i>Please wait, this may take a few seconds.</i>""",
            )

            # Perform the sync
            sync_result = await database.sync_private_files_to_db()

            # Prepare result message
            if sync_result["synced"] > 0:
                result_msg = f"""<b>✅ Sync to Database Completed</b>

<b>Files Synced:</b> {sync_result["synced"]} files backed up to database

<b>Status:</b> All filesystem files are now properly backed up in the database."""

                if sync_result["errors"]:
                    result_msg += "\n\n<b>⚠️ Warnings:</b>\n"
                    for error in sync_result["errors"][:3]:  # Show max 3 errors
                        result_msg += f"• {error}\n"
                    if len(sync_result["errors"]) > 3:
                        result_msg += (
                            f"• ... and {len(sync_result['errors']) - 3} more errors"
                        )
            elif sync_result["errors"]:
                result_msg = f"""<b>❌ Sync to Database Failed</b>

<b>Errors encountered:</b>
{chr(10).join(f"• {error}" for error in sync_result["errors"][:5])}"""
            else:
                result_msg = """<b>✅ Sync to Database Completed</b>

<b>Status:</b> All files are already synced to database.
No filesystem-only files found."""

            # Show result for 3 seconds then return to private files menu
            await edit_message(message, result_msg)
            await sleep(3)
            await update_buttons(message, "private")

        except Exception as e:
            LOGGER.error(f"Error syncing private files to database: {e}")
            await edit_message(
                message,
                f"""<b>❌ Sync to Database Failed</b>

<b>Error:</b> {e!s}

<i>Please try again or check the logs for more details.</i>""",
            )
            await sleep(3)
            await update_buttons(message, "private")
    elif data[1] == "private_sync_fs":
        await query.answer()

        try:
            # Show syncing message
            await edit_message(
                message,
                """<b>💾 Syncing Private Files to Filesystem</b>

⏳ Checking database files and syncing to filesystem...

<i>Please wait, this may take a few seconds.</i>""",
            )

            # Perform the sync
            sync_result = await database.sync_private_files_to_fs()

            # Prepare result message
            if sync_result["synced"] > 0:
                result_msg = f"""<b>✅ Sync to Filesystem Completed</b>

<b>Files Synced:</b> {sync_result["synced"]} files restored to filesystem

<b>Status:</b> All database files are now properly restored in the filesystem."""

                if sync_result["errors"]:
                    result_msg += "\n\n<b>⚠️ Warnings:</b>\n"
                    for error in sync_result["errors"][:3]:  # Show max 3 errors
                        result_msg += f"• {error}\n"
                    if len(sync_result["errors"]) > 3:
                        result_msg += (
                            f"• ... and {len(sync_result['errors']) - 3} more errors"
                        )
            elif sync_result["errors"]:
                result_msg = f"""<b>❌ Sync to Filesystem Failed</b>

<b>Errors encountered:</b>
{chr(10).join(f"• {error}" for error in sync_result["errors"][:5])}"""
            else:
                result_msg = """<b>✅ Sync to Filesystem Completed</b>

<b>Status:</b> All files are already synced to filesystem.
No database-only files found."""

            # Show result for 3 seconds then return to private files menu
            await edit_message(message, result_msg)
            await sleep(3)
            await update_buttons(message, "private")

        except Exception as e:
            LOGGER.error(f"Error syncing private files to filesystem: {e}")
            await edit_message(
                message,
                f"""<b>❌ Sync to Filesystem Failed</b>

<b>Error:</b> {e!s}

<i>Please try again or check the logs for more details.</i>""",
            )
            await sleep(3)
            await update_buttons(message, "private")
    elif data[1] == "configure_tools":
        await query.answer()
        # This handler is for the "Configure Tools" button in the Media Tools menu
        # It should always show the configuration menu, regardless of view/edit state

        # Create a special menu for selecting media tools
        buttons = ButtonMaker()

        # Force refresh Config.MEDIA_TOOLS_ENABLED from database to ensure accurate status
        try:
            # Check if database is connected and db attribute exists
            if (
                database.db is not None
                and hasattr(database, "db")
                and hasattr(database.db, "settings")
            ):
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    {"MEDIA_TOOLS_ENABLED": 1, "_id": 0},
                )
                if db_config and "MEDIA_TOOLS_ENABLED" in db_config:
                    # Update the Config object with the current value from database
                    db_value = db_config["MEDIA_TOOLS_ENABLED"]
                    if db_value != Config.MEDIA_TOOLS_ENABLED:
                        Config.MEDIA_TOOLS_ENABLED = db_value
            else:
                # Database not connected or settings collection not available, skip refresh
                pass
        except Exception:
            pass

        # Get current value after refresh
        current_value = Config.get("MEDIA_TOOLS_ENABLED")

        # List of all available tools with descriptions and icons
        all_tools_info = [
            {
                "name": "watermark",
                "icon": "💧",
                "desc": "Add text or image watermarks to media",
            },
            {
                "name": "merge",
                "icon": "🔄",
                "desc": "Combine multiple files into one",
            },
            {"name": "convert", "icon": "🔄", "desc": "Change file formats"},
            {"name": "compression", "icon": "🗜️", "desc": "Reduce file sizes"},
            {"name": "trim", "icon": "✂️", "desc": "Cut sections from media files"},
            {
                "name": "extract",
                "icon": "📤",
                "desc": "Extract components from media",
            },
            {
                "name": "remove",
                "icon": "🗑️",
                "desc": "Remove tracks or metadata from media files",
            },
            {"name": "add", "icon": "➕", "desc": "Add elements to media files"},
            {
                "name": "swap",
                "icon": "⌬",
                "desc": "Reorder tracks by language or index",
            },
            {"name": "metadata", "icon": "📝", "desc": "Modify file metadata"},
            {"name": "xtra", "icon": "🎬", "desc": "Use custom FFmpeg commands"},
            {"name": "sample", "icon": "🎞️", "desc": "Create sample clips"},
            {
                "name": "screenshot",
                "icon": "📸",
                "desc": "Take screenshots from videos",
            },
            {
                "name": "archive",
                "icon": "🗜️",
                "desc": "Enable archive flags (-z, -e) for compression/extraction",
            },
        ]

        # Get list of tool names only
        all_tools = [tool_info["name"] for tool_info in all_tools_info]

        # Parse enabled tools from the configuration
        enabled_tools = []
        if isinstance(current_value, str):
            # Handle both comma-separated and single values
            if "," in current_value:
                enabled_tools = [
                    t.strip().lower() for t in current_value.split(",") if t.strip()
                ]
            elif current_value.strip():  # Single non-empty value
                # Make sure to properly handle a single tool name
                single_tool = current_value.strip().lower()
                if single_tool in all_tools:
                    enabled_tools = [single_tool]
                # If the single tool is not in all_tools, it might be a comma-separated string without spaces
                elif any(t in single_tool for t in all_tools):
                    # Try to split by comma without spaces
                    potential_tools = single_tool.split(",")
                    enabled_tools = [t for t in potential_tools if t in all_tools]

                    # If we couldn't find any valid tools, try the original value again
                    if not enabled_tools and single_tool:
                        # Check if it's a valid tool name (might be misspelled or have extra characters)
                        for t in all_tools:
                            if t in single_tool:
                                enabled_tools = [t]
                                break
        elif current_value is True:  # If it's True (boolean), all tools are enabled
            enabled_tools = all_tools.copy()
        elif current_value:  # Any other truthy value
            if isinstance(current_value, list | tuple | set):
                enabled_tools = [str(t).strip().lower() for t in current_value if t]
            else:
                # Try to convert to string and use as a single value
                try:
                    val = str(current_value).strip().lower()
                    if val:
                        if val in all_tools:
                            enabled_tools = [val]
                        else:
                            # Check if it contains a valid tool name
                            for t in all_tools:
                                if t in val:
                                    enabled_tools = [t]
                                    break
                except Exception:
                    pass

        # Add toggle buttons for each tool with icons
        for tool_info in all_tools_info:
            tool_name = tool_info["name"]
            icon = tool_info["icon"]
            status = "✅" if tool_name in enabled_tools else "❌"
            display_name = tool_name.capitalize()
            buttons.data_button(
                f"{icon} {display_name}: {status}",
                f"botset toggle_tool MEDIA_TOOLS_ENABLED {tool_name}",
            )

        # Add buttons to enable/disable all tools
        buttons.data_button(
            "✅ Enable All", "botset enable_all_tools MEDIA_TOOLS_ENABLED"
        )
        buttons.data_button(
            "❌ Disable All", "botset disable_all_tools MEDIA_TOOLS_ENABLED"
        )

        # Add done button - always return to mediatools menu
        buttons.data_button("✅ Done", "botset mediatools")

        # Create a more informative message
        tool_status_msg = f"<b>Configure Media Tools</b> ({len(enabled_tools)}/{len(all_tools)} Enabled)\n\n"
        tool_status_msg += "Select which media tools to enable:\n\n"

        # Add a brief description of each tool
        for tool_info in all_tools_info:
            tool_name = tool_info["name"]
            icon = tool_info["icon"]
            desc = tool_info["desc"]
            status = "✅ Enabled" if tool_name in enabled_tools else "❌ Disabled"
            tool_status_msg += f"{icon} <b>{tool_name.capitalize()}</b>: {status}\n<i>{desc}</i>\n\n"

        # Show the message with tool descriptions and buttons
        await edit_message(
            message,
            tool_status_msg,
            buttons.build_menu(2),
        )
        return

    elif data[1] == "botvar":
        await query.answer()

        # No need to track state for media tools configuration

        # For other settings, proceed with normal botvar handling
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[2], data[1])

        # Default return menu to "var" - will be overridden if needed
        return_menu = "var"

        pfunc = partial(edit_variable, pre_message=message, key=data[2])

        # Special case for DEFAULT_AI_PROVIDER - create a special menu for selecting the AI provider
        # Removed: DEFAULT_AI_PROVIDER special case - use DEFAULT_AI_MODEL instead

        # For merge settings, check if we need to return to a specific page
        if (
            return_menu == "mediatools_merge"
            and message.text
            and "Page:" in message.text
        ):
            try:
                page_info = message.text.split("Page:")[1].strip().split("/")[0]
                page_no = int(page_info) - 1
                # Set the global merge_page variable to ensure we return to the correct page
                globals()["merge_page"] = page_no
            except (ValueError, IndexError):
                pass

        # Set the state back to what it was
        globals()["state"] = current_state
        # Make sure we preserve the edit state when returning to the var menu
        rfunc = partial(
            update_buttons,
            message,
            return_menu,
            "edit" if current_state == "edit" else None,
        )

        await event_handler(client, query, pfunc, rfunc)
    elif data[1] == "botvar" and state == "view":
        # In view mode, show the value
        # Note: MEDIA_TOOLS_ENABLED is now handled in the botvar handler above
        value = f"{Config.get(data[2])}"

        # Show the value
        if len(value) > 200:
            await query.answer()
            with BytesIO(str.encode(value)) as out_file:
                out_file.name = f"{data[2]}.txt"
                await send_file(message, out_file)
            return
        if value == "":
            value = None
        await query.answer(f"{value}", show_alert=True)
    elif data[1] == "ariavar" and (state == "edit" or data[2] == "newkey"):
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[2], data[1])

        pfunc = partial(edit_aria, pre_message=message, key=data[2])

        # Set the state back to what it was
        globals()["state"] = current_state
        rfunc = partial(update_buttons, message, "aria")

        await event_handler(client, query, pfunc, rfunc)
    elif data[1] == "ariavar" and state == "view":
        value = f"{aria2_options[data[2]]}"
        if len(value) > 200:
            await query.answer()
            with BytesIO(str.encode(value)) as out_file:
                out_file.name = f"{data[2]}.txt"
                await send_file(message, out_file)
            return
        if value == "":
            value = None
        await query.answer(f"{value}", show_alert=True)
    elif data[1] == "qbitvar" and state == "edit":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[2], data[1])

        pfunc = partial(edit_qbit, pre_message=message, key=data[2])

        # Set the state back to what it was
        globals()["state"] = current_state
        rfunc = partial(update_buttons, message, "qbit")

        await event_handler(client, query, pfunc, rfunc)
    elif data[1] == "qbitvar" and state == "view":
        value = f"{qbit_options[data[2]]}"
        if len(value) > 200:
            await query.answer()
            with BytesIO(str.encode(value)) as out_file:
                out_file.name = f"{data[2]}.txt"
                await send_file(message, out_file)
            return
        if value == "":
            value = None
        await query.answer(f"{value}", show_alert=True)
    elif data[1] == "nzbvar" and state == "edit":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, data[2], data[1])

        pfunc = partial(edit_nzb, pre_message=message, key=data[2])

        # Set the state back to what it was
        globals()["state"] = current_state
        rfunc = partial(update_buttons, message, "nzb")

        await event_handler(client, query, pfunc, rfunc)
    elif data[1] == "nzbvar" and state == "view":
        value = f"{nzb_options[data[2]]}"
        if len(value) > 200:
            await query.answer()
            with BytesIO(str.encode(value)) as out_file:
                out_file.name = f"{data[2]}.txt"
                await send_file(message, out_file)
            return
        if value == "":
            value = None
        await query.answer(f"{value}", show_alert=True)
    elif data[1] == "emptyserkey":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        index = int(data[2])
        # Check if data[3] exists and index is valid before accessing Config.USENET_SERVERS
        if len(data) <= 3:
            await query.answer("Invalid server data", show_alert=True)
            return
        if 0 <= index < len(Config.USENET_SERVERS):
            res = await sabnzbd_client.add_server(
                {"name": Config.USENET_SERVERS[index]["name"], data[3]: ""},
            )
            Config.USENET_SERVERS[index][data[3]] = res["config"]["servers"][0][
                data[3]
            ]
            await database.update_config({"USENET_SERVERS": Config.USENET_SERVERS})

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(message, f"nzbser{data[2]}")
        else:
            # Handle invalid index
            await query.answer(
                "Invalid server index. Please go back and try again.",
                show_alert=True,
            )

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(message, "nzbserver")
    elif data[1].startswith("nzbsevar") and (state == "edit" or data[2] == "newser"):
        index = 0 if data[2] == "newser" else int(data[1].replace("nzbsevar", ""))
        await query.answer()
        await update_buttons(message, data[2], data[1])
        pfunc = partial(
            edit_nzb_server,
            pre_message=message,
            key=data[2],
            index=index,
        )
        rfunc = partial(update_buttons, message, data[1])
        await event_handler(client, query, pfunc, rfunc)
    elif data[1].startswith("nzbsevar") and state == "view":
        index = int(data[1].replace("nzbsevar", ""))
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if index is valid before accessing Config.USENET_SERVERS
        if 0 <= index < len(Config.USENET_SERVERS):
            value = f"{Config.USENET_SERVERS[index][data[2]]}"
            if len(value) > 200:
                await query.answer()
                with BytesIO(str.encode(value)) as out_file:
                    out_file.name = f"{data[2]}.txt"
                    await send_file(message, out_file)
                return
            if value == "":
                value = None
            await query.answer(f"{value}", show_alert=True)
        else:
            # Handle invalid index
            await query.answer(
                "Invalid server index. Please go back and try again.",
                show_alert=True,
            )

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(message, "nzbserver")
    elif data[1] == "toggle_tool":
        await query.answer()
        key = data[2]  # MEDIA_TOOLS_ENABLED
        # Check if data[3] exists before accessing it
        if len(data) <= 3:
            await query.answer("Invalid toggle tool data", show_alert=True)
            return
        tool = data[3]  # The tool to toggle

        # No need to track state for media tools configuration

        # Get current value
        current_value = Config.get(key)

        # List of all available tools with descriptions and icons
        all_tools_info = [
            {
                "name": "watermark",
                "icon": "💧",
                "desc": "Add text or image watermarks to media",
            },
            {
                "name": "merge",
                "icon": "🔄",
                "desc": "Combine multiple files into one",
            },
            {"name": "convert", "icon": "🔄", "desc": "Change file formats"},
            {"name": "compression", "icon": "🗜️", "desc": "Reduce file sizes"},
            {"name": "trim", "icon": "✂️", "desc": "Cut sections from media files"},
            {
                "name": "extract",
                "icon": "📤",
                "desc": "Extract components from media",
            },
            {
                "name": "remove",
                "icon": "🗑️",
                "desc": "Remove tracks or metadata from media files",
            },
            {"name": "add", "icon": "➕", "desc": "Add elements to media files"},
            {
                "name": "swap",
                "icon": "⌬",
                "desc": "Reorder tracks by language or index",
            },
            {"name": "metadata", "icon": "📝", "desc": "Modify file metadata"},
            {"name": "xtra", "icon": "🎬", "desc": "Use custom FFmpeg commands"},
            {"name": "sample", "icon": "🎞️", "desc": "Create sample clips"},
            {
                "name": "screenshot",
                "icon": "📸",
                "desc": "Take screenshots from videos",
            },
            {
                "name": "archive",
                "icon": "🗜️",
                "desc": "Enable archive flags (-z, -e) for compression/extraction",
            },
        ]

        # Get list of tool names only
        all_tools = [tool_info["name"] for tool_info in all_tools_info]

        # Parse current enabled tools
        enabled_tools = []
        if isinstance(current_value, str):
            # Handle both comma-separated and single values
            if "," in current_value:
                enabled_tools = [
                    t.strip().lower() for t in current_value.split(",") if t.strip()
                ]
            elif current_value.strip():  # Single non-empty value
                single_tool = current_value.strip().lower()
                if single_tool in all_tools:
                    enabled_tools = [single_tool]
                # If the single tool is not in all_tools, it might be a comma-separated string without spaces
                elif any(t in single_tool for t in all_tools):
                    # Try to split by comma without spaces
                    potential_tools = single_tool.split(",")
                    enabled_tools = [t for t in potential_tools if t in all_tools]

                    # If we couldn't find any valid tools, try the original value again
                    if not enabled_tools and single_tool:
                        # Check if it's a valid tool name (might be misspelled or have extra characters)
                        for t in all_tools:
                            if t in single_tool:
                                enabled_tools = [t]
                                break
        elif current_value is True:  # If it's True (boolean), all tools are enabled
            enabled_tools = all_tools.copy()
        elif current_value:  # Any other truthy value
            if isinstance(current_value, list | tuple | set):
                enabled_tools = [str(t).strip().lower() for t in current_value if t]
            else:
                # Try to convert to string and use as a single value
                try:
                    val = str(current_value).strip().lower()
                    if val:
                        if val in all_tools:
                            enabled_tools = [val]
                        else:
                            # Check if it contains a valid tool name
                            for t in all_tools:
                                if t in val:
                                    enabled_tools = [t]
                                    break
                except Exception:
                    pass

        # Check if we're disabling a tool
        is_disabling = tool in enabled_tools

        # Toggle the tool
        if is_disabling:
            enabled_tools.remove(tool)
            # Import the reset function here to avoid circular imports
            from bot.helper.ext_utils.config_utils import reset_tool_configs

            # Reset tool-specific configurations when disabling a tool
            await reset_tool_configs(tool, database)
            # Show a message to the user
            await query.answer(f"Disabled {tool.capitalize()} tool")
        else:
            enabled_tools.append(tool)
            # Show a message to the user
            await query.answer(f"Enabled {tool.capitalize()} tool")

        # Update the config
        if enabled_tools:
            # Sort the tools to maintain consistent order
            enabled_tools.sort()
            new_value = ",".join(enabled_tools)
            Config.set(key, new_value)
        else:
            Config.set(key, False)

        # Update the database with the new setting
        await database.update_config({key: Config.get(key)})

        # Force reload the current value after database update to ensure consistency
        try:
            # Check if database is connected and db attribute exists
            if (
                database.db is not None
                and hasattr(database, "db")
                and hasattr(database.db, "settings")
            ):
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    {key: 1, "_id": 0},
                )
                if db_config and key in db_config:
                    # Update the Config object with the current value from database
                    db_value = db_config[key]
                    if db_value != Config.get(key):
                        Config.set(key, db_value)
                    current_value = db_value
                else:
                    current_value = Config.get(key)
            else:
                current_value = Config.get(key)
        except Exception:
            current_value = Config.get(key)

        # Re-parse enabled tools after the update
        enabled_tools = []
        if isinstance(current_value, str):
            # Handle both comma-separated and single values
            if "," in current_value:
                enabled_tools = [
                    t.strip().lower() for t in current_value.split(",") if t.strip()
                ]
            elif current_value.strip():  # Single non-empty value
                single_tool = current_value.strip().lower()
                if single_tool in all_tools:
                    enabled_tools = [single_tool]
                # If the single tool is not in all_tools, it might be a comma-separated string without spaces
                elif any(t in single_tool for t in all_tools):
                    # Try to split by comma without spaces
                    potential_tools = single_tool.split(",")
                    enabled_tools = [t for t in potential_tools if t in all_tools]

                    # If we couldn't find any valid tools, try the original value again
                    if not enabled_tools and single_tool:
                        # Check if it's a valid tool name (might be misspelled or have extra characters)
                        for t in all_tools:
                            if t in single_tool:
                                enabled_tools = [t]
                                break
        elif current_value is True:  # If it's True (boolean), all tools are enabled
            enabled_tools = all_tools.copy()
        elif current_value:  # Any other truthy value
            if isinstance(current_value, list | tuple | set):
                enabled_tools = [str(t).strip().lower() for t in current_value if t]
            else:
                # Try to convert to string and use as a single value
                try:
                    val = str(current_value).strip().lower()
                    if val:
                        if val in all_tools:
                            enabled_tools = [val]
                        else:
                            # Check if it contains a valid tool name
                            for t in all_tools:
                                if t in val:
                                    enabled_tools = [t]
                                    break
                except Exception:
                    pass

        # Refresh the menu
        buttons = ButtonMaker()

        # Add toggle buttons for each tool with icons
        for tool_info in all_tools_info:
            tool_name = tool_info["name"]
            icon = tool_info["icon"]
            status = "✅" if tool_name in enabled_tools else "❌"
            display_name = tool_name.capitalize()
            buttons.data_button(
                f"{icon} {display_name}: {status}",
                f"botset toggle_tool {key} {tool_name}",
            )

        # Add buttons to enable/disable all tools
        buttons.data_button("✅ Enable All", f"botset enable_all_tools {key}")
        buttons.data_button("❌ Disable All", f"botset disable_all_tools {key}")

        # Add done button - always return to the mediatools menu
        buttons.data_button("✅ Done", "botset mediatools")

        # No need to restore state for media tools configuration

        # Create a more informative message
        tool_status_msg = f"<b>Configure Media Tools</b> ({len(enabled_tools)}/{len(all_tools)} Enabled)\n\n"
        tool_status_msg += "Select which media tools to enable:\n\n"

        # Add a brief description of each tool
        for tool_info in all_tools_info:
            tool_name = tool_info["name"]
            icon = tool_info["icon"]
            desc = tool_info["desc"]
            status = "✅ Enabled" if tool_name in enabled_tools else "❌ Disabled"
            tool_status_msg += f"{icon} <b>{tool_name.capitalize()}</b>: {status}\n<i>{desc}</i>\n\n"

        # Show the message with tool descriptions and buttons
        await edit_message(
            message,
            tool_status_msg,
            buttons.build_menu(2),
        )

    elif data[1] == "enable_all_tools":
        await query.answer("Enabling all media tools")
        key = data[2]  # MEDIA_TOOLS_ENABLED

        # No need to track state for media tools configuration

        # List of all available tools with descriptions and icons
        all_tools_info = [
            {
                "name": "watermark",
                "icon": "💧",
                "desc": "Add text or image watermarks to media",
            },
            {
                "name": "merge",
                "icon": "🔄",
                "desc": "Combine multiple files into one",
            },
            {"name": "convert", "icon": "🔄", "desc": "Change file formats"},
            {"name": "compression", "icon": "🗜️", "desc": "Reduce file sizes"},
            {"name": "trim", "icon": "✂️", "desc": "Cut sections from media files"},
            {
                "name": "extract",
                "icon": "📤",
                "desc": "Extract components from media",
            },
            {
                "name": "remove",
                "icon": "🗑️",
                "desc": "Remove tracks or metadata from media files",
            },
            {"name": "add", "icon": "➕", "desc": "Add elements to media files"},
            {
                "name": "swap",
                "icon": "⌬",
                "desc": "Reorder tracks by language or index",
            },
            {"name": "metadata", "icon": "📝", "desc": "Modify file metadata"},
            {"name": "xtra", "icon": "🎬", "desc": "Use custom FFmpeg commands"},
            {"name": "sample", "icon": "🎞️", "desc": "Create sample clips"},
            {
                "name": "screenshot",
                "icon": "📸",
                "desc": "Take screenshots from videos",
            },
            {
                "name": "archive",
                "icon": "🗜️",
                "desc": "Enable archive flags (-z, -e) for compression/extraction",
            },
        ]

        # Get list of tool names only
        all_tools = [tool_info["name"] for tool_info in all_tools_info]

        # Update the config - sort the tools to maintain consistent order
        all_tools.sort()
        new_value = ",".join(all_tools)
        Config.set(key, new_value)

        # Update the database with the new setting
        await database.update_config({key: new_value})

        # Force reload the current value after database update to ensure consistency
        try:
            # Check if database is connected and db attribute exists
            if (
                database.db is not None
                and hasattr(database, "db")
                and hasattr(database.db, "settings")
            ):
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    {key: 1, "_id": 0},
                )
                if db_config and key in db_config:
                    # Update the Config object with the current value from database
                    db_value = db_config[key]
                    if db_value != Config.get(key):
                        Config.set(key, db_value)
            else:
                pass

        except Exception:
            pass

        # Refresh the menu
        buttons = ButtonMaker()

        # Add toggle buttons for each tool with icons
        for tool_info in all_tools_info:
            tool_name = tool_info["name"]
            icon = tool_info["icon"]
            display_name = tool_name.capitalize()
            buttons.data_button(
                f"{icon} {display_name}: ✅",
                f"botset toggle_tool {key} {tool_name}",
            )

        # Add buttons to enable/disable all tools
        buttons.data_button("✅ Enable All", f"botset enable_all_tools {key}")
        buttons.data_button("❌ Disable All", f"botset disable_all_tools {key}")

        # Add done button - always return to the mediatools menu when all tools are enabled
        buttons.data_button("✅ Done", "botset mediatools")

        # No need to restore state for media tools configuration

        # Create a more informative message
        tool_status_msg = f"<b>Configure Media Tools</b> ({len(all_tools)}/{len(all_tools)} Enabled)\n\n"
        tool_status_msg += (
            "All tools have been enabled. Click on a tool to disable it:\n\n"
        )

        # Add a brief description of each tool
        for tool_info in all_tools_info:
            tool_name = tool_info["name"]
            icon = tool_info["icon"]
            desc = tool_info["desc"]
            tool_status_msg += f"{icon} <b>{tool_name.capitalize()}</b>: ✅ Enabled\n<i>{desc}</i>\n\n"

        # Show the message with tool descriptions and buttons
        await edit_message(
            message,
            tool_status_msg,
            buttons.build_menu(2),
        )

    elif data[1] == "disable_all_tools":
        await query.answer("Disabling all media tools")
        key = data[2]  # MEDIA_TOOLS_ENABLED

        # No need to track state for media tools configuration

        # List of all available tools with descriptions and icons
        all_tools_info = [
            {
                "name": "watermark",
                "icon": "💧",
                "desc": "Add text or image watermarks to media",
            },
            {
                "name": "merge",
                "icon": "🔄",
                "desc": "Combine multiple files into one",
            },
            {"name": "convert", "icon": "🔄", "desc": "Change file formats"},
            {"name": "compression", "icon": "🗜️", "desc": "Reduce file sizes"},
            {"name": "trim", "icon": "✂️", "desc": "Cut sections from media files"},
            {
                "name": "extract",
                "icon": "📤",
                "desc": "Extract components from media",
            },
            {
                "name": "remove",
                "icon": "🗑️",
                "desc": "Remove tracks or metadata from media files",
            },
            {"name": "add", "icon": "➕", "desc": "Add elements to media files"},
            {
                "name": "swap",
                "icon": "⌬",
                "desc": "Reorder tracks by language or index",
            },
            {"name": "metadata", "icon": "📝", "desc": "Modify file metadata"},
            {"name": "xtra", "icon": "🎬", "desc": "Use custom FFmpeg commands"},
            {"name": "sample", "icon": "🎞️", "desc": "Create sample clips"},
            {
                "name": "screenshot",
                "icon": "📸",
                "desc": "Take screenshots from videos",
            },
            {
                "name": "archive",
                "icon": "🗜️",
                "desc": "Enable archive flags (-z, -e) for compression/extraction",
            },
        ]

        # Get list of tool names only
        all_tools = [tool_info["name"] for tool_info in all_tools_info]

        # Reset configurations for all tools
        from bot.helper.ext_utils.config_utils import reset_tool_configs

        for tool in all_tools:
            await reset_tool_configs(tool, database)

        # Update the config
        Config.set(key, False)

        # Update the database with the new setting
        await database.update_config({key: False})

        # Force reload the current value after database update to ensure consistency
        try:
            # Check if database is connected and db attribute exists
            if (
                database.db is not None
                and hasattr(database, "db")
                and hasattr(database.db, "settings")
            ):
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    {key: 1, "_id": 0},
                )
                if db_config and key in db_config:
                    # Update the Config object with the current value from database
                    db_value = db_config[key]
                    if db_value != Config.get(key):
                        Config.set(key, db_value)
            else:
                pass

        except Exception:
            pass

        # After disabling all tools, directly return to the Media Tools menu
        # This will show the Media Tools Settings menu with only the Configure Tools button
        await update_buttons(message, "mediatools")

    # Removed: setprovider handler - use setmodel instead

    elif data[1] == "setmodel":
        if data[2] == "default":
            # Set to default model
            model = "gpt-4o"
        else:
            model = data[2]

        # Validate the model exists
        model_info = ai_manager.get_model_info(model)
        if not model_info:
            await query.answer(f"❌ Invalid model: {model}", show_alert=True)
            return

        display_name = model_info.get("display_name", model)
        await query.answer(f"✅ Setting AI model to {display_name}")

        # Update the default AI model
        Config.DEFAULT_AI_MODEL = model
        # Update the database
        await database.update_config({"DEFAULT_AI_MODEL": model})
        # Update the UI - maintain the current state (edit/view)
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Set the state back to what it was
        globals()["state"] = current_state
        await update_buttons(message, "ai")

    elif data[1] == "cancel_image_upload":
        await query.answer("Upload cancelled")
        # Reset the handler_dict for this user
        handler_dict[message.chat.id] = False
        # Return to the watermark settings menu
        await update_buttons(message, "mediatools_watermark")
    elif data[1] == "cancel":
        await query.answer()
        # Get the current state before updating the UI
        current_state = globals()["state"]
        # Check if we're in the AI settings menu
        if message.text and "Select Default AI Provider" in message.text:
            # Return to AI settings menu - maintain the current state (edit/view)
            globals()["state"] = current_state
            await update_buttons(message, "ai")
        else:
            # Return to Config menu - maintain the current state (edit/view)
            globals()["state"] = current_state
            await update_buttons(message, "var")
    elif data[1] == "edit":
        await query.answer()
        globals()["state"] = "edit"
        # Handle pagination for watermark text menu
        if (
            data[2] == "mediatools_watermark_text"
            and "watermark_text_page" in globals()
        ):
            await update_buttons(
                message, data[2], page=globals()["watermark_text_page"]
            )
        # Handle pagination for merge menu
        elif data[2] == "mediatools_merge" and "merge_page" in globals():
            await update_buttons(message, data[2], page=globals()["merge_page"])
        else:
            await update_buttons(message, data[2])
    elif data[1] == "view":
        await query.answer()
        globals()["state"] = "view"
        # Handle pagination for watermark text menu
        if (
            data[2] == "mediatools_watermark_text"
            and "watermark_text_page" in globals()
        ):
            await update_buttons(
                message, data[2], page=globals()["watermark_text_page"]
            )
        # Handle pagination for merge menu
        elif data[2] == "mediatools_merge" and "merge_page" in globals():
            await update_buttons(message, data[2], page=globals()["merge_page"])
        else:
            await update_buttons(message, data[2])
    elif data[1] == "start":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        # Check if data[3] exists before accessing it
        if len(data) > 3 and start != int(data[3]):
            globals()["start"] = int(data[3])

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(message, data[2])
    elif data[1] == "start_merge":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        try:
            if len(data) > 2:
                # Update the global merge_page variable
                globals()["merge_page"] = int(data[2])

                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(
                    message, "mediatools_merge", page=globals()["merge_page"]
                )
            else:
                # If no page number is provided, stay on the current page
                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(
                    message, "mediatools_merge", page=globals()["merge_page"]
                )
        except (ValueError, IndexError):
            # In case of any error, stay on the current page

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
    elif data[1] == "start_merge_config":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        try:
            if len(data) > 2:
                # Update both global page variables to keep them in sync
                page_no = int(data[2])
                globals()["merge_page"] = page_no
                globals()["merge_config_page"] = page_no

                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(message, "mediatools_merge", page=page_no)
            else:
                # If no page number is provided, stay on the current page
                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(
                    message, "mediatools_merge", page=globals()["merge_page"]
                )
        except (ValueError, IndexError):
            # In case of any error, stay on the current page

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
    elif data[1] == "back_to_merge":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        try:
            if len(data) > 2:
                # Update the global merge_page variable
                globals()["merge_page"] = int(data[2])

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
        except (ValueError, IndexError):
            # In case of any error, stay on the current page

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
    elif data[1] == "back_to_merge_config":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        try:
            if len(data) > 2:
                # Update both global page variables to keep them in sync
                page_no = int(data[2])
                globals()["merge_page"] = page_no
                globals()["merge_config_page"] = page_no

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
        except (ValueError, IndexError):
            # In case of any error, stay on the current page

            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(
                message, "mediatools_merge", page=globals()["merge_page"]
            )
    elif data[1] == "start_watermark_text":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        try:
            if len(data) > 2:
                page = int(data[2])
                # Update the global watermark_text_page variable
                globals()["watermark_text_page"] = page
                # Store the page in handler_dict for backup
                if message.chat.id:
                    handler_dict[f"{message.chat.id}_watermark_page"] = page

                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(message, "mediatools_watermark_text", page=page)
            else:
                # If no page number is provided, use the stored page if available
                if (
                    message.chat.id
                    and f"{message.chat.id}_watermark_page" in handler_dict
                ):
                    page = handler_dict[f"{message.chat.id}_watermark_page"]
                else:
                    # Otherwise use the global variable or default to page 0
                    page = globals().get("watermark_text_page", 0)
                    # Store the page in handler_dict for future reference
                    if message.chat.id:
                        handler_dict[f"{message.chat.id}_watermark_page"] = page

                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(message, "mediatools_watermark_text", page=page)
        except (ValueError, IndexError):
            # In case of any error, stay on the current page

            # Set the state back to what it was
            globals()["state"] = current_state

            # Try to use the stored page if available
            if (
                message.chat.id
                and f"{message.chat.id}_watermark_page" in handler_dict
            ):
                page = handler_dict[f"{message.chat.id}_watermark_page"]
            else:
                page = globals().get("watermark_text_page", 0)

            await update_buttons(message, "mediatools_watermark_text", page=page)

    elif data[1] == "start_convert":
        await query.answer()
        # Get the current state before making changes
        current_state = globals()["state"]

        try:
            if len(data) > 2:
                page = int(data[2])

                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(message, "mediatools_convert", page=page)
            else:
                # If no page number is provided, stay on the current page
                # Set the state back to what it was
                globals()["state"] = current_state
                await update_buttons(message, "mediatools_convert")
        except (ValueError, IndexError):
            # In case of any error, stay on the current page
            # Set the state back to what it was
            globals()["state"] = current_state
            await update_buttons(message, "mediatools_convert")
    elif data[1] == "toggle":
        await query.answer()
        key = data[2]
        # Check if data[3] exists before accessing it
        if len(data) <= 3:
            await query.answer("Invalid toggle data", show_alert=True)
            return
        value = data[3].lower() == "true"

        # Force refresh the setting from database before toggling to ensure accurate status
        try:
            # Check if database is connected and db attribute exists
            if (
                database.db is not None
                and hasattr(database, "db")
                and hasattr(database.db, "settings")
            ):
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    {key: 1},
                )
                if db_config and key in db_config:
                    # Update the Config object with the current value from database
                    db_value = db_config[key]
                    if db_value != getattr(Config, key, None):
                        setattr(Config, key, db_value)
                        # If the database value is different from what we're trying to toggle,
                        # update the value to toggle based on the current database value
                        value = not db_value
        except Exception:
            pass

        # Special handling for ADD_PRESERVE_TRACKS and ADD_REPLACE_TRACKS
        # When one is turned on, the other should be turned off
        if key == "ADD_PRESERVE_TRACKS" and value:
            # If preserve is being turned on, turn off replace
            Config.set("ADD_PRESERVE_TRACKS", True)
            Config.set("ADD_REPLACE_TRACKS", False)
            # Update both settings in the database
            await database.update_config(
                {"ADD_PRESERVE_TRACKS": True, "ADD_REPLACE_TRACKS": False}
            )

        elif key == "ADD_REPLACE_TRACKS" and value:
            # If replace is being turned on, turn off preserve
            Config.set("ADD_REPLACE_TRACKS", True)
            Config.set("ADD_PRESERVE_TRACKS", False)
            # Update both settings in the database
            await database.update_config(
                {"ADD_REPLACE_TRACKS": True, "ADD_PRESERVE_TRACKS": False}
            )

        # Special handling for RCLONE_ENABLED
        elif key == "RCLONE_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Rclone is being disabled, reset all user Rclone configs
                from bot.helper.ext_utils.config_utils import reset_rclone_configs

                await reset_rclone_configs(database)
            else:
                # If Rclone is being enabled, log it
                from bot import LOGGER

                LOGGER.info("Rclone operations have been enabled.")

        # Special handling for MIRROR_ENABLED
        elif key == "MIRROR_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Mirror is being disabled, reset all user mirror-related configs
                from bot.helper.ext_utils.config_utils import reset_mirror_configs

                await reset_mirror_configs(database)
            else:
                # Mirror enabled without logging
                pass

        # Special handling for LEECH_ENABLED
        elif key == "LEECH_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Leech is being disabled, reset all user leech-related configs
                from bot.helper.ext_utils.config_utils import reset_leech_configs

                await reset_leech_configs(database)
            else:
                # Leech operations enabled without logging
                pass

        # Special handling for YTDLP_ENABLED
        elif key == "YTDLP_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If YT-DLP is being disabled, reset all user YT-DLP-related configs
                from bot.helper.ext_utils.config_utils import reset_ytdlp_configs

                await reset_ytdlp_configs(database)
            else:
                # YT-DLP operations enabled without logging
                pass

        # Special handling for TORRENT_ENABLED
        elif key == "TORRENT_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Torrent is being disabled, reset all user torrent-related configs
                from bot.helper.ext_utils.config_utils import reset_torrent_configs

                await reset_torrent_configs(database)
            else:
                # Torrent operations enabled without logging
                pass

        # Special handling for NZB_ENABLED
        elif key == "NZB_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If NZB is being disabled, reset all user NZB-related configs
                from bot.helper.ext_utils.config_utils import reset_nzb_configs

                await reset_nzb_configs(database)
            else:
                # NZB operations enabled without logging
                pass

        # Special handling for JD_ENABLED
        elif key == "JD_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If JDownloader is being disabled, reset all user JD-related configs
                from bot.helper.ext_utils.config_utils import reset_jd_configs

                await reset_jd_configs(database)
            else:
                # JDownloader operations enabled without logging
                pass

        # Special handling for BULK_ENABLED
        elif key == "BULK_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Bulk is being disabled, reset all user bulk-related configs
                from bot.helper.ext_utils.config_utils import reset_bulk_configs

                await reset_bulk_configs(database)
            else:
                # Bulk operations enabled without logging
                pass

        # Special handling for MULTI_LINK_ENABLED
        elif key == "MULTI_LINK_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Multi-link is being disabled, reset all user multi-link-related configs
                from bot.helper.ext_utils.config_utils import (
                    reset_multi_link_configs,
                )

                await reset_multi_link_configs(database)
            else:
                # Multi-link operations enabled without logging
                pass

        # Special handling for SAME_DIR_ENABLED
        elif key == "SAME_DIR_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Same-dir is being disabled, reset all user same-dir-related configs
                from bot.helper.ext_utils.config_utils import reset_same_dir_configs

                await reset_same_dir_configs(database)
            else:
                # Same-dir operations enabled without logging
                pass

        # Special handling for STREAMRIP_ENABLED
        elif key == "STREAMRIP_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Streamrip is being disabled, reset all streamrip-related configs
                from bot.helper.ext_utils.config_utils import reset_streamrip_configs

                await reset_streamrip_configs(database)
            else:
                # Streamrip operations enabled without logging
                pass

        # Special handling for GALLERY_DL_ENABLED
        elif key == "GALLERY_DL_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Gallery-dl is being disabled, reset all gallery-dl-related configs
                from bot.helper.ext_utils.config_utils import (
                    reset_gallery_dl_configs,
                )

                await reset_gallery_dl_configs(database)
            else:
                # Gallery-dl operations enabled without logging
                pass

        # Special handling for ZOTIFY_ENABLED
        elif key == "ZOTIFY_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            if not value:
                # If Zotify is being disabled, reset all zotify-related configs
                from bot.helper.ext_utils.config_utils import reset_zotify_configs

                await reset_zotify_configs(database)
            else:
                # Zotify operations enabled without logging
                pass

        # Special handling for GDRIVE_UPLOAD_ENABLED
        elif key == "GDRIVE_UPLOAD_ENABLED":
            # Update the config first
            Config.set(key, value)
            await database.update_config({key: value})
            if not value:
                # If Google Drive upload is being disabled, reset all Google Drive-related configs
                from bot.helper.ext_utils.config_utils import (
                    reset_gdrive_upload_configs,
                )

                await reset_gdrive_upload_configs(database)
            else:
                # Google Drive upload operations enabled without logging
                pass

        # Special handling for YOUTUBE_UPLOAD_ENABLED
        elif key == "YOUTUBE_UPLOAD_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})
            if not value:
                # If YouTube upload is being disabled, reset all YouTube-related configs
                from bot.helper.ext_utils.config_utils import reset_youtube_configs

                await reset_youtube_configs(database)
            else:
                # YouTube upload operations enabled without logging
                pass

        # Special handling for DDL_ENABLED
        elif key == "DDL_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database
            await database.update_config({key: value})
            if not value:
                # If DDL is being disabled, reset all DDL-related configs
                from bot.helper.ext_utils.config_utils import reset_ddl_configs

                await reset_ddl_configs(database)
            else:
                # DDL operations enabled without logging
                pass

        # Special handling for MEGA_ENABLED
        elif key == "MEGA_ENABLED":
            # Set the value in Config
            Config.set(key, value)
            # Update the database
            await database.update_config({key: value})
            if not value:
                # If MEGA is being disabled, reset all MEGA-related configs
                from bot.helper.ext_utils.config_utils import reset_mega_configs

                await reset_mega_configs(database)
            else:
                # MEGA operations enabled without logging
                pass

        # Special handling for MEGA upload public setting
        elif key == "MEGA_UPLOAD_PUBLIC" and value:
            # Set public links to true (only supported option)
            Config.set("MEGA_UPLOAD_PUBLIC", True)
            # Update the database
            await database.update_config(
                {
                    "MEGA_UPLOAD_PUBLIC": True,
                }
            )

        # MEGA_UPLOAD_PRIVATE and MEGA_UPLOAD_UNLISTED removed - not supported by MEGA SDK v4.8.0

        # Special handling for TORRENT_SEARCH_ENABLED
        elif key in {"TORRENT_SEARCH_ENABLED", "NZB_SEARCH_ENABLED"} or key in {
            "HYPERDL_ENABLED",
            "MEDIA_SEARCH_ENABLED",
            "MEGA_SEARCH_ENABLED",
        }:
            # Set the value in Config
            Config.set(key, value)
            # Update the database with the new setting
            await database.update_config({key: value})

            # Search toggle without logging

        else:
            # For all other toggles, just set the value directly
            Config.set(key, value)
            # Database update will be done later in the function

        # Special handling for MEDIA_TOOLS_ENABLED
        if key == "MEDIA_TOOLS_ENABLED":
            # If toggling to True, set to a comma-separated list of all media tools
            if value:
                # List of all available media tools
                all_tools = [
                    "watermark",
                    "merge",
                    "convert",
                    "compression",
                    "trim",
                    "extract",
                    "add",
                    "metadata",
                    "xtra",
                    "sample",
                ]
                # Sort the tools to maintain consistent order
                all_tools.sort()
                value = ",".join(all_tools)
            # If toggling to False, set to False (boolean)
            else:
                value = False

        # Set the value on the Config class for all settings
        Config.set(key, value)

        # Determine which menu to return to based on the key
        return_menu = "mediatools"
        if key.startswith(
            (
                "WATERMARK_",
                "AUDIO_WATERMARK_",
                "SUBTITLE_WATERMARK_",
                "IMAGE_WATERMARK_",
            )
        ):
            return_menu = "mediatools_watermark"
        elif key.startswith("METADATA_"):
            return_menu = "mediatools_metadata"
        elif key.startswith("CONVERT_"):
            return_menu = "mediatools_convert"
        elif key.startswith("COMPRESSION_"):
            return_menu = "mediatools_compression"
        elif key.startswith("TRIM_"):
            return_menu = "mediatools_trim"
        elif key.startswith("EXTRACT_"):
            return_menu = "mediatools_extract"
        elif key.startswith("REMOVE_"):
            return_menu = "mediatools_remove"
        elif key.startswith("ADD_"):
            # For ADD_ settings, return to the mediatools_add menu
            return_menu = "mediatools_add"
        elif key.startswith("TASK_MONITOR_"):
            return_menu = "taskmonitor"
        elif key == "ARCHIVE_FLAGS_ENABLED":
            return_menu = "archiveflags"
        elif key.startswith("STREAMRIP_") and key != "STREAMRIP_ENABLED":
            # For streamrip settings (except STREAMRIP_ENABLED which is handled in operations), determine which submenu to return to
            if key in ["STREAMRIP_AUTO_CONVERT"]:
                return_menu = "streamrip_general"
            elif key in [
                "STREAMRIP_DEFAULT_QUALITY",
                "STREAMRIP_FALLBACK_QUALITY",
                "STREAMRIP_DEFAULT_CODEC",
                "STREAMRIP_SUPPORTED_CODECS",
                "STREAMRIP_QUALITY_FALLBACK_ENABLED",
            ]:
                return_menu = "streamrip_quality"
            elif (
                key.endswith("_ENABLED")
                and any(
                    platform in key
                    for platform in ["QOBUZ", "TIDAL", "DEEZER", "SOUNDCLOUD"]
                )
            ) or key.endswith(
                (
                    "_EMAIL",
                    "_PASSWORD",
                    "_ARL",
                    "_CLIENT_ID",
                    "_ACCESS_TOKEN",
                    "_REFRESH_TOKEN",
                    "_USER_ID",
                    "_COUNTRY_CODE",
                )
            ):
                return_menu = "streamrip_credentials"
            elif key in [
                "STREAMRIP_CONCURRENT_DOWNLOADS",
                "STREAMRIP_MAX_SEARCH_RESULTS",
                "STREAMRIP_MAX_CONNECTIONS",
                "STREAMRIP_REQUESTS_PER_MINUTE",
                "STREAMRIP_SOURCE_SUBDIRECTORIES",
                "STREAMRIP_DISC_SUBDIRECTORIES",
                "STREAMRIP_CONCURRENCY",
                "STREAMRIP_VERIFY_SSL",
            ]:
                return_menu = "streamrip_download"
            elif key in [
                "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS",
                "STREAMRIP_QOBUZ_FILTERS_EXTRAS",
                "STREAMRIP_QOBUZ_FILTERS_REPEATS",
                "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS",
                "STREAMRIP_QOBUZ_FILTERS_FEATURES",
                "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS",
                "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER",
                "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS",
                "STREAMRIP_TIDAL_TOKEN_EXPIRY",
                "STREAMRIP_DEEZER_USE_DEEZLOADER",
                "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS",
                "STREAMRIP_SOUNDCLOUD_APP_VERSION",
                "STREAMRIP_YOUTUBE_QUALITY",
                "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS",
                "STREAMRIP_YOUTUBE_VIDEO_FOLDER",
                "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER",
                "STREAMRIP_LASTFM_ENABLED",
                "STREAMRIP_LASTFM_SOURCE",
                "STREAMRIP_LASTFM_FALLBACK_SOURCE",
            ]:
                return_menu = "streamrip_platforms"
            elif key in [
                "STREAMRIP_ENABLE_DATABASE",
                "STREAMRIP_DATABASE_DOWNLOADS_ENABLED",
                "STREAMRIP_DATABASE_DOWNLOADS_PATH",
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED",
                "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
            ]:
                return_menu = "streamrip_database"
            elif key in [
                "STREAMRIP_CONVERSION_ENABLED",
                "STREAMRIP_CONVERSION_CODEC",
                "STREAMRIP_CONVERSION_SAMPLING_RATE",
                "STREAMRIP_CONVERSION_BIT_DEPTH",
                "STREAMRIP_CONVERSION_LOSSY_BITRATE",
            ]:
                return_menu = "streamrip_conversion"
            elif key in [
                "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM",
                "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS",
                "STREAMRIP_METADATA_EXCLUDE",
            ]:
                return_menu = "streamrip_metadata"
            elif key in [
                "STREAMRIP_CLI_TEXT_OUTPUT",
                "STREAMRIP_CLI_PROGRESS_BARS",
                "STREAMRIP_CLI_MAX_SEARCH_RESULTS",
                "STREAMRIP_MISC_CHECK_FOR_UPDATES",
                "STREAMRIP_MISC_VERSION",
            ]:
                return_menu = "streamrip_cli"
            elif key in [
                "STREAMRIP_FILENAME_TEMPLATE",
                "STREAMRIP_FOLDER_TEMPLATE",
                "STREAMRIP_EMBED_COVER_ART",
                "STREAMRIP_SAVE_COVER_ART",
                "STREAMRIP_COVER_ART_SIZE",
                "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH",
                "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH",
                "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER",
                "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
                "STREAMRIP_FILEPATHS_TRACK_FORMAT",
                "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS",
                "STREAMRIP_FILEPATHS_TRUNCATE_TO",
            ]:
                return_menu = "streamrip_advanced"
            else:
                return_menu = "streamrip"
        elif key.startswith("GALLERY_DL_") and key != "GALLERY_DL_ENABLED":
            # For gallery-dl settings (except GALLERY_DL_ENABLED which is handled in operations), determine which submenu to return to
            if key in [
                "GALLERY_DL_QUALITY_SELECTION",
                "GALLERY_DL_ARCHIVE_ENABLED",
                "GALLERY_DL_METADATA_ENABLED",
            ]:
                return_menu = "gallerydl_general"
            elif key in [
                "GALLERY_DL_INSTAGRAM_USERNAME",
                "GALLERY_DL_INSTAGRAM_PASSWORD",
                "GALLERY_DL_TWITTER_USERNAME",
                "GALLERY_DL_TWITTER_PASSWORD",
                "GALLERY_DL_REDDIT_CLIENT_ID",
                "GALLERY_DL_REDDIT_CLIENT_SECRET",
                "GALLERY_DL_REDDIT_USERNAME",
                "GALLERY_DL_REDDIT_PASSWORD",
                "GALLERY_DL_REDDIT_REFRESH_TOKEN",
                "GALLERY_DL_PIXIV_USERNAME",
                "GALLERY_DL_PIXIV_PASSWORD",
                "GALLERY_DL_PIXIV_REFRESH_TOKEN",
                "GALLERY_DL_DEVIANTART_CLIENT_ID",
                "GALLERY_DL_DEVIANTART_CLIENT_SECRET",
                "GALLERY_DL_DEVIANTART_USERNAME",
                "GALLERY_DL_DEVIANTART_PASSWORD",
                "GALLERY_DL_TUMBLR_API_KEY",
                "GALLERY_DL_TUMBLR_API_SECRET",
                "GALLERY_DL_TUMBLR_TOKEN",
                "GALLERY_DL_TUMBLR_TOKEN_SECRET",
                "GALLERY_DL_DISCORD_TOKEN",
            ]:
                return_menu = "gallerydl_auth"
            elif key in [
                "GALLERY_DL_MAX_DOWNLOADS",
                "GALLERY_DL_RATE_LIMIT",
                "GALLERY_DL_LIMIT",
            ]:
                return_menu = "gallerydl_download"
            else:
                return_menu = "gallerydl"
        elif key.startswith("YOUTUBE_UPLOAD_") and key != "YOUTUBE_UPLOAD_ENABLED":
            # For YouTube upload settings (except YOUTUBE_UPLOAD_ENABLED which is handled in operations), determine which submenu to return to
            if key in [
                "YOUTUBE_UPLOAD_DEFAULT_PRIVACY",
                "YOUTUBE_UPLOAD_DEFAULT_CATEGORY",
                "YOUTUBE_UPLOAD_DEFAULT_TAGS",
                "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
            ]:
                return_menu = "youtube_general"
            elif key in [
                "YOUTUBE_UPLOAD_DEFAULT_TITLE",
                "YOUTUBE_UPLOAD_DEFAULT_LANGUAGE",
                "YOUTUBE_UPLOAD_DEFAULT_LICENSE",
                "YOUTUBE_UPLOAD_EMBEDDABLE",
                "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
                "YOUTUBE_UPLOAD_MADE_FOR_KIDS",
                "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
                "YOUTUBE_UPLOAD_LOCATION_DESCRIPTION",
                "YOUTUBE_UPLOAD_RECORDING_DATE",
                "YOUTUBE_UPLOAD_AUTO_LEVELS",
                "YOUTUBE_UPLOAD_STABILIZE",
            ]:
                return_menu = "youtube_upload"
            else:
                return_menu = "youtube"
        elif key.startswith("MEGA_") and key != "MEGA_ENABLED":
            # For MEGA settings (except MEGA_ENABLED which is handled in operations), determine which submenu to return to
            if key in ["MEGA_EMAIL", "MEGA_PASSWORD", "MEGA_LIMIT"]:
                return_menu = "mega_general"
            elif key in [
                "MEGA_UPLOAD_ENABLED",
                # "MEGA_UPLOAD_FOLDER" removed - using folder selector instead
                "MEGA_UPLOAD_PUBLIC",
                # "MEGA_UPLOAD_PRIVATE" removed - not supported by MEGA SDK v4.8.0
                # "MEGA_UPLOAD_UNLISTED" removed - not supported by MEGA SDK v4.8.0
                # "MEGA_UPLOAD_EXPIRY_DAYS" removed - premium feature not implemented
                # "MEGA_UPLOAD_PASSWORD" removed - premium feature not implemented
                # "MEGA_UPLOAD_ENCRYPTION_KEY" removed - not supported by MEGA SDK v4.8.0
                "MEGA_UPLOAD_THUMBNAIL",
                # "MEGA_UPLOAD_DELETE_AFTER" removed - always delete after upload
            ]:
                return_menu = "mega_upload"

            # mega_security settings removed - not supported by MEGA SDK v4.8.0
            elif key == "MEGA_SEARCH_ENABLED":
                return_menu = "mega"
            else:
                return_menu = "mega"
        elif key in {
            "BULK_ENABLED",
            "MULTI_LINK_ENABLED",
            "SAME_DIR_ENABLED",
            "MIRROR_ENABLED",
            "LEECH_ENABLED",
            "TORRENT_ENABLED",
            "TORRENT_SEARCH_ENABLED",
            "YTDLP_ENABLED",
            "NZB_ENABLED",
            "NZB_SEARCH_ENABLED",
            "JD_ENABLED",
            "HYPERDL_ENABLED",
            "MEDIA_SEARCH_ENABLED",
            "RCLONE_ENABLED",
            "STREAMRIP_ENABLED",
            "GALLERY_DL_ENABLED",
            "ZOTIFY_ENABLED",
            "YOUTUBE_UPLOAD_ENABLED",
            "MEGA_ENABLED",
            "DDL_ENABLED",
            "FILE2LINK_ENABLED",
            "WRONG_CMD_WARNINGS_ENABLED",
            "VT_ENABLED",
            "AD_BROADCASTER_ENABLED",
        }:
            return_menu = "operations"
        elif (
            key.startswith(("GOFILE_", "STREAMTAPE_", "DEVUPLOADS_", "MEDIAFIRE_"))
            or key == "DDL_DEFAULT_SERVER"
        ):
            # For DDL settings, determine which submenu to return to
            if key == "DDL_DEFAULT_SERVER":
                return_menu = "ddl_general"
            elif key.startswith("GOFILE_"):
                return_menu = "ddl_gofile"
            elif key.startswith("STREAMTAPE_"):
                return_menu = "ddl_streamtape"
            elif key.startswith("DEVUPLOADS_"):
                return_menu = "ddl_devuploads"
            elif key.startswith("MEDIAFIRE_"):
                return_menu = "ddl_mediafire"

            else:
                return_menu = "ddl"
        elif key in {
            "IMDB_ENABLED",
            "TRUECALLER_ENABLED",
            "MEDIA_TOOLS_ENABLED",
        }:
            return_menu = "var"
        elif key in {"AI_ENABLED", "DEFAULT_AI_MODEL"} or key.startswith(
            ("MISTRAL_", "DEEPSEEK_")
        ):
            return_menu = "ai"
        elif key.startswith("AI_") and key in {
            "AI_PLUGINS_ENABLED",
            "AI_WEB_SEARCH_ENABLED",
            "AI_URL_SUMMARIZATION_ENABLED",
            "AI_ARXIV_ENABLED",
            "AI_CODE_INTERPRETER_ENABLED",
            "AI_IMAGE_GENERATION_ENABLED",
            "AI_VOICE_TRANSCRIPTION_ENABLED",
        }:
            return_menu = "ai_plugins"
        elif key.startswith("AI_") and key in {
            "AI_CONVERSATION_HISTORY",
            "AI_QUESTION_PREDICTION",
            "AI_GROUP_TOPIC_MODE",
            "AI_AUTO_LANGUAGE_DETECTION",
        }:
            return_menu = "ai_conversation"
        elif key.startswith("AI_") and key in {
            "AI_STREAMING_ENABLED",
            "AI_MULTIMODAL_ENABLED",
            "AI_INLINE_MODE_ENABLED",
            "AI_VOICE_TRANSCRIPTION_ENABLED",
            "AI_IMAGE_GENERATION_ENABLED",
            "AI_DOCUMENT_PROCESSING_ENABLED",
            "AI_FOLLOW_UP_QUESTIONS_ENABLED",
            "AI_CONVERSATION_EXPORT_ENABLED",
            "AI_TYPEWRITER_EFFECT_ENABLED",
            "AI_CONTEXT_PRUNING_ENABLED",
        }:
            return_menu = "ai_advanced"
        elif key.startswith("AI_"):
            # For any other AI settings, return to main AI menu
            return_menu = "ai"
        elif key.startswith("MERGE_") or key in [
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
        ]:
            # Check if we're in the merge_config menu
            if (message.text and "Merge Configuration" in message.text) or (
                key.startswith("MERGE_")
                and any(
                    x in key
                    for x in [
                        "OUTPUT_FORMAT",
                        "VIDEO_",
                        "AUDIO_",
                        "IMAGE_",
                        "SUBTITLE_",
                        "DOCUMENT_",
                        "METADATA_",
                    ]
                )
            ):
                return_menu = "mediatools_merge_config"
            # Check if we need to return to a specific page in mediatools_merge
            elif message.text and "Page:" in message.text:
                try:
                    page_info = message.text.split("Page:")[1].strip().split("/")[0]
                    page_no = int(page_info) - 1
                    # Set the global merge_page variable to ensure we return to the correct page
                    globals()["merge_page"] = page_no
                    return_menu = "mediatools_merge"
                except (ValueError, IndexError):
                    return_menu = "mediatools_merge"
            else:
                # Use the global merge_page variable
                return_menu = "mediatools_merge"

        # Get the current state before updating the database
        current_state = globals()["state"]
        # Update the database
        await database.update_config({key: value})

        # Force reload the current value after database update to ensure consistency
        try:
            # Check if database is connected and db attribute exists
            if (
                database.db is not None
                and hasattr(database, "db")
                and hasattr(database.db, "settings")
            ):
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    {key: 1, "_id": 0},
                )
                if db_config and key in db_config:
                    # Update the Config object with the current value from database
                    # For all settings including ADD_ settings
                    db_value = db_config[key]
                    if db_value != value:
                        Config.set(key, db_value)
                        # If the database value is different from what we tried to set,
                        # make sure we use the database value for the UI update
                        value = db_value
            else:
                pass

        except Exception:
            pass

        # For ADD_ settings, make sure we immediately update the UI to reflect the change
        # This ensures the toggle buttons show the correct state
        if key.startswith("ADD_"):
            # Force a refresh of the UI to ensure the toggle buttons show the correct state
            await update_buttons(message, "mediatools_add")

        # Update the UI - restore the state
        globals()["state"] = current_state
        await update_buttons(message, return_menu)
    # Handle redirects for mediatools callbacks
    elif data[0] == "mediatools" and len(data) >= 3 and data[2] == "merge_config":
        # This is a callback from the pagination buttons in mediatools_merge_config
        # Redirect it to the media_tools module
        from bot.modules.media_tools import media_tools_callback

        await media_tools_callback(client, query)


@new_task
async def send_bot_settings(_, message):
    user_id = message.chat.id
    handler_dict[user_id] = False
    msg, button = await get_buttons(user_id=user_id)
    globals()["start"] = 0
    # Don't auto-delete the bot settings message
    await send_message(message, msg, button)


async def load_config():
    Config.load()
    drives_ids.clear()
    drives_names.clear()
    index_urls.clear()

    # Ensure COMPRESSION_DELETE_ORIGINAL is set with the correct default value
    if not hasattr(Config, "COMPRESSION_DELETE_ORIGINAL"):
        Config.COMPRESSION_DELETE_ORIGINAL = True

    # Ensure ADD_ settings are properly initialized in the database
    # We'll handle this when the database is connected
    # This is done in the database.connect() call below

    await update_variables()

    if not await aiopath.exists("accounts"):
        Config.USE_SERVICE_ACCOUNTS = False

    if len(task_dict) != 0 and (st := intervals["status"]):
        for key, intvl in list(st.items()):
            intvl.cancel()
            intervals["status"][key] = SetInterval(
                1,
                update_status_message,
                key,
            )

    if Config.TORRENT_TIMEOUT:
        await TorrentManager.change_aria2_option(
            "bt-stop-timeout",
            f"{Config.TORRENT_TIMEOUT}",
        )
        await database.update_aria2("bt-stop-timeout", f"{Config.TORRENT_TIMEOUT}")

    if not Config.INCOMPLETE_TASK_NOTIFIER:
        await database.trunc_table("tasks")

    # First, kill any running web server processes
    with contextlib.suppress(Exception):
        await (await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")).wait()

    # Only start web server if BASE_URL_PORT is not 0
    if Config.BASE_URL_PORT == 0:
        # Double-check to make sure no web server is running
        try:
            # Use ps to check if any gunicorn processes are still running
            process = await create_subprocess_exec(
                "ps",
                "-ef",
                "|",
                "grep",
                "gunicorn",
                "|",
                "grep",
                "-v",
                "grep",
                stdout=-1,
            )
            stdout, _ = await process.communicate()
            if stdout:
                await (
                    await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
                ).wait()
        except Exception:
            pass

    else:
        await create_subprocess_shell(
            f"gunicorn -k uvicorn.workers.UvicornWorker -w 1 web.wserver:app --bind 0.0.0.0:{Config.BASE_URL_PORT}",
        )

    if Config.DATABASE_URL:
        await database.connect()
        # Start the database heartbeat task to keep the connection alive
        await database.start_heartbeat()

        config_dict = Config.get_all()

        # Add ADD_ settings from DEFAULT_VALUES to the database
        add_settings = {
            key: value
            for key, value in DEFAULT_VALUES.items()
            if key.startswith("ADD_")
        }
        config_dict.update(add_settings)

        await database.update_config(config_dict)
    else:
        # Stop the heartbeat task if it's running
        await database.stop_heartbeat()
        await database.disconnect()
    await gather(start_from_queued(), rclone_serve_booter())
    add_job()
