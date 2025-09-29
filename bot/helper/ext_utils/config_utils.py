from bot import user_data
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath
from bot.helper.ext_utils.aiofiles_compat import remove as aioremove


async def reset_mirror_configs(database):
    """Reset all mirror-related configurations to their default values when mirror is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific mirror configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Mirror-related keys to reset
        mirror_keys = [
            "GDRIVE_ID",
            "INDEX_URL",
            "STOP_DUPLICATE",
            "TOKEN_PICKLE",
            "RCLONE_PATH",
            "RCLONE_FLAGS",
            "RCLONE_CONFIG",
            "DEFAULT_UPLOAD",
        ]

        # Reset each mirror-related key
        for key in mirror_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Set DEFAULT_UPLOAD to first available service if it was "rc"
        if user_dict.get("DEFAULT_UPLOAD") == "rc":
            from bot.core.config_manager import Config

            # Find first available service as fallback
            if Config.GDRIVE_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "gd"
            elif Config.YOUTUBE_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "yt"
            elif Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "mg"
            elif Config.DDL_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "ddl"
            else:
                user_dict["DEFAULT_UPLOAD"] = (
                    "gd"  # Keep as gd if no other service available
                )
            user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)


async def reset_leech_configs(database):
    """Reset all leech-related configurations to their default values when leech is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific leech configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Leech-related keys to reset
        leech_keys = [
            "THUMBNAIL",
            "LEECH_SPLIT_SIZE",
            "EQUAL_SPLITS",
            "LEECH_FILENAME_PREFIX",
            "LEECH_SUFFIX",
            "LEECH_FONT",
            "LEECH_FILENAME",
            "LEECH_FILENAME_CAPTION",
            "THUMBNAIL_LAYOUT",
            "USER_DUMP",
            "USER_SESSION",
        ]

        # Reset each leech-related key
        for key in leech_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)


async def reset_ytdlp_configs(database):
    """Reset all YT-DLP-related configurations to their default values when YT-DLP is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific YT-DLP configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # YT-DLP-related keys to reset
        ytdlp_keys = ["YT_DLP_OPTIONS", "USER_COOKIES"]

        # Reset each YT-DLP-related key
        for key in ytdlp_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Delete user cookies file if it exists
        cookies_path = f"cookies/{user_id}.txt"
        if await aiopath.exists(cookies_path):
            try:
                await aioremove(cookies_path)
            except Exception as e:
                from bot import LOGGER

                LOGGER.error(f"Error deleting cookies file for user {user_id}: {e}")

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)


async def reset_rclone_configs(database):
    """Reset all Rclone-related configurations to their default values when Rclone is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific Rclone configurations
    from bot import LOGGER

    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Reset user's DEFAULT_UPLOAD to first available service
        if user_dict.get("DEFAULT_UPLOAD", "") == "rc":
            from bot.core.config_manager import Config

            # Find first available service as fallback
            if Config.GDRIVE_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "gd"
            elif Config.YOUTUBE_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "yt"
            elif Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "mg"
            elif Config.DDL_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "ddl"
            else:
                user_dict["DEFAULT_UPLOAD"] = (
                    "gd"  # Keep as gd if no other service available
                )
            user_configs_to_reset = True

        # Rclone-related keys to reset
        rclone_keys = ["RCLONE_FLAGS", "RCLONE_PATH", "RCLONE_CONFIG"]

        # Reset each Rclone-related key
        for key in rclone_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Remove the user's Rclone config file if it exists
        rclone_conf = f"rclone/{user_id}.conf"
        if await aiopath.exists(rclone_conf):
            try:
                await aioremove(rclone_conf)
            except Exception as e:
                LOGGER.error(f"Error removing Rclone config for user {user_id}: {e}")

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Rclone disabled without logging


async def reset_torrent_configs(database):
    """Reset all torrent-related configurations to their default values when torrent is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific torrent configurations

    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Torrent-related keys to reset
        torrent_keys = ["TORRENT_TIMEOUT"]

        # Reset each torrent-related key
        for key in torrent_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Torrent operations disabled without logging


async def reset_nzb_configs(database):
    """Reset all NZB-related configurations to their default values when NZB is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific NZB configurations

    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # NZB-related keys to reset - no user-specific NZB configs found in codebase
        nzb_keys = []

        # Reset each NZB-related key
        for key in nzb_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # NZB operations disabled without logging


async def reset_jd_configs(database):
    """Reset all JDownloader-related configurations to their default values when JD is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific JDownloader configurations

    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # JDownloader-related keys to reset - no user-specific JD configs found in codebase
        jd_keys = []

        # Reset each JDownloader-related key
        for key in jd_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # JDownloader operations disabled without logging


async def reset_gdrive_upload_configs(database):
    """Reset all Google Drive upload-related configurations to their default values when Gdrive upload is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific Google Drive upload configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Google Drive upload-related keys to reset
        gdrive_keys = [
            "GDRIVE_ID",
            "INDEX_URL",
            "TOKEN_PICKLE",
            "DEFAULT_UPLOAD",  # Reset if set to Google Drive
        ]

        # Reset each Google Drive-related key
        for key in gdrive_keys:
            if key in user_dict:
                # Special handling for DEFAULT_UPLOAD
                if key == "DEFAULT_UPLOAD" and user_dict[key] == "gd":
                    # Find first available service as fallback
                    from bot.core.config_manager import Config

                    if Config.RCLONE_ENABLED:
                        user_dict[key] = "rc"
                    elif Config.YOUTUBE_UPLOAD_ENABLED:
                        user_dict[key] = "yt"
                    elif Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED:
                        user_dict[key] = "mg"
                    elif Config.DDL_ENABLED:
                        user_dict[key] = "ddl"
                    else:
                        user_dict[key] = (
                            "gd"  # Keep as gd if no other service available
                        )
                    user_configs_to_reset = True
                elif key != "DEFAULT_UPLOAD":
                    user_dict.pop(key, None)
                    user_configs_to_reset = True

        # Remove the user's Google Drive token file if it exists
        token_path = f"tokens/{user_id}.pickle"
        if await aiopath.exists(token_path):
            try:
                await aioremove(token_path)
            except Exception as e:
                from bot import LOGGER

                LOGGER.error(
                    f"Error removing Google Drive token for user {user_id}: {e}"
                )

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)


async def reset_mega_configs(database):
    """Reset all MEGA-related configurations to their default values when MEGA is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific MEGA configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # MEGA-related keys to reset
        mega_keys = [
            "MEGA_EMAIL",
            "MEGA_PASSWORD",
            "MEGA_UPLOAD_ENABLED",
            "DEFAULT_UPLOAD",  # Reset if set to MEGA
        ]

        # Reset each MEGA-related key
        for key in mega_keys:
            if key in user_dict:
                # Special handling for DEFAULT_UPLOAD
                if key == "DEFAULT_UPLOAD" and user_dict[key] == "mg":
                    user_dict[key] = "gd"  # Reset to Google Drive
                    user_configs_to_reset = True
                elif key != "DEFAULT_UPLOAD":
                    user_dict.pop(key, None)
                    user_configs_to_reset = True

        # Reset user's DEFAULT_UPLOAD to first available service if it's set to MEGA
        if user_dict.get("DEFAULT_UPLOAD") == "mg":
            from bot.core.config_manager import Config

            # Find first available service as fallback
            if Config.GDRIVE_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "gd"
            elif Config.RCLONE_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "rc"
            elif Config.YOUTUBE_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "yt"
            elif Config.DDL_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "ddl"
            else:
                user_dict["DEFAULT_UPLOAD"] = (
                    "gd"  # Keep as gd if no other service available
                )
            user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Reset owner MEGA configurations to default values
    from bot.core.config_manager import Config

    # Get default values for MEGA settings
    default_values = {
        "MEGA_ENABLED": True,
        "MEGA_EMAIL": "",
        "MEGA_PASSWORD": "",
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

    # Reset owner configurations
    configs_to_reset = {}
    for key, default_value in default_values.items():
        if key != "MEGA_ENABLED":  # Don't reset the main toggle
            configs_to_reset[key] = default_value
            Config.set(key, default_value)

    # Update the database if there are configurations to reset
    if configs_to_reset:
        await database.update_config(configs_to_reset)


async def reset_bulk_configs(database):
    """Reset all bulk-related configurations to their default values when bulk is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific bulk configurations

    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Bulk-related keys to reset - no user-specific bulk configs found in codebase
        bulk_keys = []

        # Reset each bulk-related key
        for key in bulk_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Bulk operations disabled without logging


async def reset_multi_link_configs(database):
    """Reset all multi-link-related configurations to their default values when multi-link is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific multi-link configurations

    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Multi-link-related keys to reset - no user-specific multi-link configs found in codebase
        multi_link_keys = []

        # Reset each multi-link-related key
        for key in multi_link_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Multi-link operations disabled without logging


async def reset_same_dir_configs(database):
    """Reset all same-dir-related configurations to their default values when same-dir is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific same-dir configurations

    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Same-dir-related keys to reset - no user-specific same-dir configs found in codebase
        same_dir_keys = []

        # Reset each same-dir-related key
        for key in same_dir_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Same-dir operations disabled without logging


async def reset_streamrip_configs(database):
    """Reset all streamrip-related configurations to their default values when streamrip is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific streamrip configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Streamrip-related keys to reset
        streamrip_keys = [
            "STREAMRIP_DEFAULT_QUALITY",
            "STREAMRIP_FALLBACK_QUALITY",
            "STREAMRIP_DEFAULT_CODEC",
            "STREAMRIP_QUALITY_FALLBACK_ENABLED",
            "STREAMRIP_QOBUZ_EMAIL",
            "STREAMRIP_QOBUZ_PASSWORD",
            "STREAMRIP_QOBUZ_USE_AUTH_TOKEN",
            "STREAMRIP_QOBUZ_APP_ID",
            "STREAMRIP_QOBUZ_SECRETS",
            "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS",
            "STREAMRIP_TIDAL_EMAIL",
            "STREAMRIP_TIDAL_PASSWORD",
            "STREAMRIP_TIDAL_ACCESS_TOKEN",
            "STREAMRIP_TIDAL_REFRESH_TOKEN",
            "STREAMRIP_TIDAL_USER_ID",
            "STREAMRIP_TIDAL_COUNTRY_CODE",
            "STREAMRIP_TIDAL_TOKEN_EXPIRY",
            "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS",
            "STREAMRIP_DEEZER_ARL",
            "STREAMRIP_DEEZER_USE_DEEZLOADER",
            "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS",
            "STREAMRIP_SOUNDCLOUD_CLIENT_ID",
            "STREAMRIP_SOUNDCLOUD_APP_VERSION",
            "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS",
            "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER",
            "STREAMRIP_FILENAME_TEMPLATE",
            "STREAMRIP_FOLDER_TEMPLATE",
            "STREAMRIP_EMBED_COVER_ART",
            "STREAMRIP_SAVE_COVER_ART",
            "STREAMRIP_COVER_ART_SIZE",
            "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
            "STREAMRIP_FILEPATHS_TRACK_FORMAT",
            "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER",
            "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS",
            "STREAMRIP_FILEPATHS_TRUNCATE_TO",
            "STREAMRIP_CONVERSION_ENABLED",
            "STREAMRIP_CONVERSION_CODEC",
            "STREAMRIP_CONVERSION_SAMPLING_RATE",
            "STREAMRIP_CONVERSION_BIT_DEPTH",
            "STREAMRIP_CONVERSION_LOSSY_BITRATE",
            "STREAMRIP_DATABASE_DOWNLOADS_ENABLED",
            "STREAMRIP_DATABASE_DOWNLOADS_PATH",
            "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED",
            "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
            "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM",
            "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS",
            "STREAMRIP_METADATA_EXCLUDE",
            "STREAMRIP_LASTFM_SOURCE",
            "STREAMRIP_LASTFM_FALLBACK_SOURCE",
            "STREAMRIP_CLI_TEXT_OUTPUT",
            "STREAMRIP_CLI_PROGRESS_BARS",
            "STREAMRIP_CLI_MAX_SEARCH_RESULTS",
            "STREAMRIP_MISC_CHECK_FOR_UPDATES",
        ]

        # Reset each streamrip-related key
        for key in streamrip_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Reset global streamrip configurations to defaults
    streamrip_global_configs = {
        "STREAMRIP_ENABLED": False,
        "STREAMRIP_CONCURRENT_DOWNLOADS": 4,
        "STREAMRIP_MAX_SEARCH_RESULTS": 200,
        "STREAMRIP_ENABLE_DATABASE": True,
        "STREAMRIP_AUTO_CONVERT": True,
        "STREAMRIP_DEFAULT_QUALITY": 3,
        "STREAMRIP_FALLBACK_QUALITY": 2,
        "STREAMRIP_DEFAULT_CODEC": "flac",
        "STREAMRIP_QUALITY_FALLBACK_ENABLED": True,
        "STREAMRIP_QOBUZ_ENABLED": True,
        "STREAMRIP_QOBUZ_QUALITY": 3,
        "STREAMRIP_TIDAL_ENABLED": True,
        "STREAMRIP_TIDAL_QUALITY": 3,
        "STREAMRIP_DEEZER_ENABLED": True,
        "STREAMRIP_DEEZER_QUALITY": 2,
        "STREAMRIP_SOUNDCLOUD_ENABLED": True,
        "STREAMRIP_SOUNDCLOUD_QUALITY": 0,
        "STREAMRIP_LASTFM_ENABLED": True,
        "STREAMRIP_YOUTUBE_QUALITY": 0,
        "STREAMRIP_QOBUZ_EMAIL": "",
        "STREAMRIP_QOBUZ_PASSWORD": "",
        "STREAMRIP_QOBUZ_USE_AUTH_TOKEN": False,
        "STREAMRIP_QOBUZ_APP_ID": "",
        "STREAMRIP_QOBUZ_SECRETS": [],
        "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS": True,
        "STREAMRIP_TIDAL_EMAIL": "",
        "STREAMRIP_TIDAL_PASSWORD": "",
        "STREAMRIP_TIDAL_ACCESS_TOKEN": "",
        "STREAMRIP_TIDAL_REFRESH_TOKEN": "",
        "STREAMRIP_TIDAL_USER_ID": "",
        "STREAMRIP_TIDAL_COUNTRY_CODE": "",
        "STREAMRIP_TIDAL_TOKEN_EXPIRY": "0",
        "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS": True,
        "STREAMRIP_DEEZER_ARL": "",
        "STREAMRIP_DEEZER_USE_DEEZLOADER": True,
        "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS": True,
        "STREAMRIP_SOUNDCLOUD_CLIENT_ID": "",
        "STREAMRIP_SOUNDCLOUD_APP_VERSION": "",
        "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS": False,
        "STREAMRIP_FILENAME_TEMPLATE": "",
        "STREAMRIP_FOLDER_TEMPLATE": "",
        "STREAMRIP_EMBED_COVER_ART": True,
        "STREAMRIP_SAVE_COVER_ART": True,
        "STREAMRIP_COVER_ART_SIZE": "large",
        "STREAMRIP_MAX_CONNECTIONS": 6,
        "STREAMRIP_REQUESTS_PER_MINUTE": 60,
        "STREAMRIP_SOURCE_SUBDIRECTORIES": False,
        "STREAMRIP_DISC_SUBDIRECTORIES": True,
        "STREAMRIP_CONCURRENCY": True,
        "STREAMRIP_VERIFY_SSL": True,
        "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER": "",
        "STREAMRIP_MISC_VERSION": "2.0.6",
        "STREAMRIP_METADATA_EXCLUDE": [],
        "STREAMRIP_SUPPORTED_CODECS": ["flac", "mp3", "m4a", "ogg", "opus"],
        "STREAMRIP_QOBUZ_FILTERS_EXTRAS": False,
        "STREAMRIP_QOBUZ_FILTERS_REPEATS": False,
        "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS": False,
        "STREAMRIP_QOBUZ_FILTERS_FEATURES": False,
        "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS": False,
        "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER": False,
        "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH": -1,
        "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH": -1,
        # Database Configuration
        "STREAMRIP_DATABASE_DOWNLOADS_ENABLED": True,
        "STREAMRIP_DATABASE_DOWNLOADS_PATH": "./downloads.db",
        "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED": True,
        "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH": "./failed_downloads.db",
        # Conversion Configuration
        "STREAMRIP_CONVERSION_ENABLED": False,
        "STREAMRIP_CONVERSION_CODEC": "ALAC",
        "STREAMRIP_CONVERSION_SAMPLING_RATE": 48000,
        "STREAMRIP_CONVERSION_BIT_DEPTH": 24,
        "STREAMRIP_CONVERSION_LOSSY_BITRATE": 320,
        # Filepaths Configuration
        "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER": False,
        "STREAMRIP_FILEPATHS_FOLDER_FORMAT": "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]",
        "STREAMRIP_FILEPATHS_TRACK_FORMAT": "{tracknumber:02}. {artist} - {title}{explicit}",
        "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS": False,
        "STREAMRIP_FILEPATHS_TRUNCATE_TO": 120,
        # Metadata Configuration
        "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM": True,
        "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS": True,
        # Last.fm Configuration
        "STREAMRIP_LASTFM_SOURCE": "qobuz",
        "STREAMRIP_LASTFM_FALLBACK_SOURCE": "",
        # CLI Configuration
        "STREAMRIP_CLI_TEXT_OUTPUT": True,
        "STREAMRIP_CLI_PROGRESS_BARS": True,
        "STREAMRIP_CLI_MAX_SEARCH_RESULTS": 200,
        # Misc Configuration
        "STREAMRIP_MISC_CHECK_FOR_UPDATES": True,
    }

    # Update global configurations
    for key, default_value in streamrip_global_configs.items():
        Config.set(key, default_value)

    # Update the database with global configurations
    await database.update_config(streamrip_global_configs)

    # Remove streamrip config files if they exist
    from bot import LOGGER

    # Remove global streamrip config
    streamrip_config_path = "streamrip_config.toml"
    if await aiopath.exists(streamrip_config_path):
        try:
            await aioremove(streamrip_config_path)
            LOGGER.info("Removed global streamrip config file")
        except Exception as e:
            LOGGER.error(f"Error removing streamrip config file: {e}")

    # Remove user-specific streamrip configs
    for user_id in user_data:
        user_config_path = f"streamrip_configs/{user_id}.toml"
        if await aiopath.exists(user_config_path):
            try:
                await aioremove(user_config_path)
                LOGGER.info(f"Removed streamrip config for user {user_id}")
            except Exception as e:
                LOGGER.error(
                    f"Error removing streamrip config for user {user_id}: {e}"
                )


async def reset_tool_configs(tool_name, database):
    """Reset all configurations related to a specific tool to their default values.

    Args:
        tool_name (str): The name of the tool to reset configurations for
        database: The database instance to update configurations
    """
    # Define prefixes for each tool
    tool_prefixes = {
        "watermark": [
            "WATERMARK_",
            "AUDIO_WATERMARK_",
            "SUBTITLE_WATERMARK_",
            "IMAGE_WATERMARK_",
        ],
        "merge": ["MERGE_", "CONCAT_DEMUXER_", "FILTER_COMPLEX_"],
        "convert": ["CONVERT_"],
        "compression": ["COMPRESSION_"],
        "trim": ["TRIM_"],
        "extract": ["EXTRACT_"],
        "remove": ["REMOVE_"],
        "add": ["ADD_"],
        "swap": ["SWAP_"],
        "metadata": ["METADATA_"],
        "xtra": ["FFMPEG_CMDS"],  # Reset FFMPEG_CMDS for users
        "sample": [],  # No specific configs for sample
        "ai": [
            "AI_",
            "DEFAULT_AI_MODEL",
            "OPENAI_",
            "ANTHROPIC_",
            "GOOGLE_AI_",
            "GROQ_",
            "VERTEX_",
            "MISTRAL_",
            "DEEPSEEK_",
        ],  # AI-related configs
    }

    # Define default values for each tool
    default_values = {
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
        # Audio watermark settings
        "AUDIO_WATERMARK_ENABLED": False,
        "AUDIO_WATERMARK_VOLUME": 0.0,
        "AUDIO_WATERMARK_INTERVAL": 0,
        # Subtitle watermark settings
        "SUBTITLE_WATERMARK_ENABLED": False,
        "SUBTITLE_WATERMARK_STYLE": "none",
        "SUBTITLE_WATERMARK_INTERVAL": 0,
        # Image watermark settings
        "IMAGE_WATERMARK_ENABLED": False,
        "IMAGE_WATERMARK_OPACITY": 0.0,
        "IMAGE_WATERMARK_SCALE": "10",
        "IMAGE_WATERMARK_POSITION": "bottom_right",
        # Merge Settings
        "MERGE_ENABLED": False,
        "MERGE_PRIORITY": 1,
        "MERGE_THREADING": True,
        "MERGE_THREAD_NUMBER": 4,
        "CONCAT_DEMUXER_ENABLED": True,
        "FILTER_COMPLEX_ENABLED": False,
        "MERGE_REMOVE_ORIGINAL": True,
        "MERGE_DELETE_ORIGINAL": True,
        # Output formats
        "MERGE_OUTPUT_FORMAT_VIDEO": "none",
        "MERGE_OUTPUT_FORMAT_AUDIO": "none",
        "MERGE_OUTPUT_FORMAT_IMAGE": "none",
        "MERGE_OUTPUT_FORMAT_DOCUMENT": "none",
        "MERGE_OUTPUT_FORMAT_SUBTITLE": "none",
        # Video settings
        "MERGE_VIDEO_CODEC": "none",
        "MERGE_VIDEO_QUALITY": "none",
        "MERGE_VIDEO_PRESET": "none",
        "MERGE_VIDEO_CRF": "none",
        "MERGE_VIDEO_PIXEL_FORMAT": "none",
        "MERGE_VIDEO_TUNE": "none",
        "MERGE_VIDEO_FASTSTART": False,
        # Audio settings
        "MERGE_AUDIO_CODEC": "none",
        "MERGE_AUDIO_BITRATE": "none",
        "MERGE_AUDIO_CHANNELS": "none",
        "MERGE_AUDIO_SAMPLING": "none",
        "MERGE_AUDIO_VOLUME": "none",
        # Image settings
        "MERGE_IMAGE_MODE": "none",
        "MERGE_IMAGE_COLUMNS": "none",
        "MERGE_IMAGE_QUALITY": 0,
        "MERGE_IMAGE_DPI": "none",
        "MERGE_IMAGE_RESIZE": "none",
        "MERGE_IMAGE_BACKGROUND": "none",
        # Subtitle settings
        "MERGE_SUBTITLE_ENCODING": "none",
        "MERGE_SUBTITLE_FONT": "none",
        "MERGE_SUBTITLE_FONT_SIZE": "none",
        "MERGE_SUBTITLE_FONT_COLOR": "none",
        "MERGE_SUBTITLE_BACKGROUND": "none",
        # Document settings
        "MERGE_DOCUMENT_PAPER_SIZE": "none",
        "MERGE_DOCUMENT_ORIENTATION": "none",
        "MERGE_DOCUMENT_MARGIN": "none",
        # Metadata settings
        "MERGE_METADATA_TITLE": "none",
        "MERGE_METADATA_AUTHOR": "none",
        "MERGE_METADATA_COMMENT": "none",
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
        # Compression Settings
        "COMPRESSION_ENABLED": False,
        "COMPRESSION_PRIORITY": 4,
        "COMPRESSION_DELETE_ORIGINAL": True,
        "COMPRESSION_REMOVE_ORIGINAL": True,
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
        "COMPRESSION_VIDEO_FORMAT": "none",
        # Audio Compression Settings
        "COMPRESSION_AUDIO_ENABLED": False,
        "COMPRESSION_AUDIO_PRESET": "none",
        "COMPRESSION_AUDIO_CODEC": "none",
        "COMPRESSION_AUDIO_BITRATE": "none",
        "COMPRESSION_AUDIO_CHANNELS": "none",
        "COMPRESSION_AUDIO_BITDEPTH": "none",
        "COMPRESSION_AUDIO_FORMAT": "none",
        # Image Compression Settings
        "COMPRESSION_IMAGE_ENABLED": False,
        "COMPRESSION_IMAGE_PRESET": "none",
        "COMPRESSION_IMAGE_QUALITY": "none",
        "COMPRESSION_IMAGE_RESIZE": "none",
        # Document Compression Settings
        "COMPRESSION_DOCUMENT_ENABLED": False,
        "COMPRESSION_DOCUMENT_PRESET": "none",
        "COMPRESSION_DOCUMENT_DPI": "none",
        # Subtitle Compression Settings
        "COMPRESSION_SUBTITLE_ENABLED": False,
        "COMPRESSION_SUBTITLE_PRESET": "none",
        "COMPRESSION_SUBTITLE_ENCODING": "none",
        # Archive Compression Settings
        "COMPRESSION_ARCHIVE_ENABLED": False,
        "COMPRESSION_ARCHIVE_PRESET": "none",
        "COMPRESSION_ARCHIVE_LEVEL": "none",
        "COMPRESSION_ARCHIVE_METHOD": "none",
        "COMPRESSION_ARCHIVE_PASSWORD": "none",
        "COMPRESSION_ARCHIVE_ALGORITHM": "none",
        # Trim Settings
        "TRIM_ENABLED": False,
        "TRIM_PRIORITY": 5,
        "TRIM_START_TIME": "00:00:00",
        "TRIM_END_TIME": "",
        "TRIM_DELETE_ORIGINAL": False,
        "TRIM_REMOVE_ORIGINAL": False,
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
        "TRIM_IMAGE_QUALITY": 90,
        "TRIM_IMAGE_FORMAT": "none",
        # Document Trim Settings
        "TRIM_DOCUMENT_ENABLED": False,
        "TRIM_DOCUMENT_START_PAGE": "1",
        "TRIM_DOCUMENT_END_PAGE": "",
        "TRIM_DOCUMENT_QUALITY": 90,
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
        "EXTRACT_REMOVE_ORIGINAL": True,
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
        # Metadata Settings
        "METADATA_ENABLED": False,
        "METADATA_PRIORITY": 8,
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
        # FFmpeg Settings
        "FFMPEG_CMDS": {},  # Dictionary of FFmpeg commands
        # Remove Settings
        "REMOVE_ENABLED": False,
        "REMOVE_PRIORITY": 8,
        "REMOVE_DELETE_ORIGINAL": True,
        "REMOVE_REMOVE_ORIGINAL": True,
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
        # Add Settings - General
        "ADD_REMOVE_ORIGINAL": True,
        # Video Add Settings
        "ADD_VIDEO_ENABLED": False,
        # "ADD_VIDEO_PATH": "none", # Removed
        "ADD_VIDEO_CODEC": "none",
        "ADD_VIDEO_INDEX": None,
        "ADD_VIDEO_QUALITY": "none",
        "ADD_VIDEO_PRESET": "none",
        "ADD_VIDEO_BITRATE": "none",
        "ADD_VIDEO_RESOLUTION": "none",
        "ADD_VIDEO_FPS": "none",
        # Audio Add Settings
        "ADD_AUDIO_ENABLED": False,
        # "ADD_AUDIO_PATH": "none", # Removed
        "ADD_AUDIO_CODEC": "none",
        "ADD_AUDIO_INDEX": None,
        "ADD_AUDIO_BITRATE": "none",
        "ADD_AUDIO_CHANNELS": "none",
        "ADD_AUDIO_SAMPLING": "none",
        "ADD_AUDIO_VOLUME": "none",
        # Subtitle Add Settings
        "ADD_SUBTITLE_ENABLED": False,
        # "ADD_SUBTITLE_PATH": "none", # Removed
        "ADD_SUBTITLE_CODEC": "none",
        "ADD_SUBTITLE_INDEX": None,
        "ADD_SUBTITLE_LANGUAGE": "none",
        "ADD_SUBTITLE_ENCODING": "none",
        "ADD_SUBTITLE_FONT": "none",
        "ADD_SUBTITLE_FONT_SIZE": "none",
        "ADD_SUBTITLE_HARDSUB_ENABLED": False,
        # Attachment Add Settings
        "ADD_ATTACHMENT_ENABLED": False,
        # "ADD_ATTACHMENT_PATH": "none", # Removed
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
        # AI Settings - Core
        "DEFAULT_AI_MODEL": "gpt-4o-mini",
        "AI_CONVERSATION_MODE": "assistant",
        "AI_LANGUAGE": "en",
        # AI Feature Settings
        "AI_STREAMING_ENABLED": True,
        "AI_PLUGINS_ENABLED": True,
        "AI_MULTIMODAL_ENABLED": True,
        "AI_CONVERSATION_HISTORY": True,
        "AI_MAX_HISTORY_LENGTH": 50,
        "AI_QUESTION_PREDICTION": True,
        "AI_GROUP_TOPIC_MODE": True,
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
        # AI Plugin Settings
        "AI_WEB_SEARCH_ENABLED": True,
        "AI_URL_SUMMARIZATION_ENABLED": True,
        "AI_ARXIV_ENABLED": True,
        "AI_CODE_INTERPRETER_ENABLED": True,
        # AI Budget Settings
        "AI_DAILY_TOKEN_LIMIT": 0,  # 0 = unlimited
        "AI_MONTHLY_TOKEN_LIMIT": 0,  # 0 = unlimited
        "AI_DAILY_COST_LIMIT": 0.0,  # 0 = unlimited
        "AI_MONTHLY_COST_LIMIT": 0.0,  # 0 = unlimited
        # AI Performance Settings
        "AI_MAX_TOKENS": 4096,
        "AI_TEMPERATURE": 0.7,
        "AI_TIMEOUT": 600,
        "AI_RATE_LIMIT_PER_USER": 100,
        # AI API Keys (reset to empty)
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "GOOGLE_AI_API_KEY": "",
        "GROQ_API_KEY": "",
        "VERTEX_PROJECT_ID": "",
        "VERTEX_AI_LOCATION": "",
        # AI API URLs (reset to empty for default)
        "OPENAI_API_URL": "",
        "ANTHROPIC_API_URL": "",
        "GOOGLE_AI_API_URL": "",
        "GROQ_API_URL": "",
        "MISTRAL_API_URL": "",
        "DEEPSEEK_API_URL": "",
    }

    # Get prefixes for the specified tool
    prefixes = tool_prefixes.get(tool_name.lower(), [])
    if not prefixes:
        return

    # Step 1: Reset global (owner) configurations
    configs_to_reset = {}

    # Special handling for ffmpeg tool - don't reset owner's FFMPEG_CMDS
    if tool_name.lower() == "xtra":
        # Skip resetting owner configurations for ffmpeg
        pass
    else:
        # Get all current configurations
        all_configs = Config.get_all()

        # Find configurations that match the tool's prefixes
        for key in all_configs:
            for prefix in prefixes:
                if key.startswith(prefix):
                    # Get the default value if it exists, otherwise skip
                    default_value = default_values.get(key)
                    if default_value is not None:
                        configs_to_reset[key] = default_value
                        # Also update the Config class
                        Config.set(key, default_value)

        # Update the database if there are configurations to reset
        if configs_to_reset:
            await database.update_config(configs_to_reset)

    # Step 2: Reset user-specific configurations
    # Iterate through all users
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Find user configurations that match the tool's prefixes
        for key in list(user_dict):
            for prefix in prefixes:
                if key.startswith(prefix) or key == prefix:
                    # Remove the configuration from the user's data
                    user_dict.pop(key, None)
                    user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)


async def reset_youtube_configs(database):
    """Reset all YouTube-related configurations to their default values when YouTube upload is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific YouTube configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # YouTube-related keys to reset
        youtube_keys = [
            "YOUTUBE_UPLOAD_DEFAULT_PRIVACY",
            "YOUTUBE_UPLOAD_DEFAULT_CATEGORY",
            "YOUTUBE_UPLOAD_DEFAULT_TAGS",
            "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
        ]

        # Reset each YouTube-related key
        for key in youtube_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Remove user's YouTube token file if it exists
        youtube_token_path = f"tokens/{user_id}_youtube.pickle"
        if await aiopath.exists(youtube_token_path):
            try:
                await aioremove(youtube_token_path)
            except Exception as e:
                from bot import LOGGER

                LOGGER.error(f"Error removing YouTube token for user {user_id}: {e}")

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Reset global YouTube configurations to defaults
    youtube_global_configs = {
        "YOUTUBE_UPLOAD_ENABLED": False,
        "YOUTUBE_UPLOAD_DEFAULT_PRIVACY": "unlisted",
        "YOUTUBE_UPLOAD_DEFAULT_CATEGORY": "22",
        "YOUTUBE_UPLOAD_DEFAULT_TAGS": "",
        "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION": "Uploaded by AIM",
    }

    # Update global configurations
    for key, default_value in youtube_global_configs.items():
        Config.set(key, default_value)

    # Update the database with global configurations
    await database.update_config(youtube_global_configs)


async def reset_zotify_configs(database):
    """Reset all zotify-related configurations to their default values when zotify is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific zotify configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Zotify-related keys to reset
        zotify_keys = [
            "ZOTIFY_CREDENTIALS_PATH",
            "ZOTIFY_ALBUM_LIBRARY",
            "ZOTIFY_PODCAST_LIBRARY",
            "ZOTIFY_PLAYLIST_LIBRARY",
            "ZOTIFY_OUTPUT_ALBUM",
            "ZOTIFY_OUTPUT_PLAYLIST_TRACK",
            "ZOTIFY_OUTPUT_PLAYLIST_EPISODE",
            "ZOTIFY_OUTPUT_PODCAST",
            "ZOTIFY_OUTPUT_SINGLE",
            "ZOTIFY_DOWNLOAD_QUALITY",
            "ZOTIFY_AUDIO_FORMAT",
            "ZOTIFY_ARTWORK_SIZE",
            "ZOTIFY_TRANSCODE_BITRATE",
            "ZOTIFY_DOWNLOAD_REAL_TIME",
            "ZOTIFY_REPLACE_EXISTING",
            "ZOTIFY_SKIP_DUPLICATES",
            "ZOTIFY_SKIP_PREVIOUS",
            "ZOTIFY_SAVE_METADATA",
            "ZOTIFY_SAVE_GENRE",
            "ZOTIFY_ALL_ARTISTS",
            "ZOTIFY_LYRICS_FILE",
            "ZOTIFY_LYRICS_ONLY",
            "ZOTIFY_SAVE_SUBTITLES",
            "ZOTIFY_CREATE_PLAYLIST_FILE",
            "ZOTIFY_FFMPEG_PATH",
            "ZOTIFY_FFMPEG_ARGS",
            "ZOTIFY_LANGUAGE",
            "ZOTIFY_PRINT_PROGRESS",
            "ZOTIFY_PRINT_DOWNLOADS",
            "ZOTIFY_PRINT_ERRORS",
            "ZOTIFY_PRINT_WARNINGS",
            "ZOTIFY_PRINT_SKIPS",
            "ZOTIFY_MATCH_EXISTING",
        ]

        # Reset each zotify-related key
        for key in zotify_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Reset global zotify configurations to defaults (from config_manager.py)
    zotify_global_configs = {
        "ZOTIFY_ENABLED": False,
        "ZOTIFY_CREDENTIALS_PATH": "./zotify_credentials.json",
        "ZOTIFY_ALBUM_LIBRARY": "Music/Zotify Albums",
        "ZOTIFY_PODCAST_LIBRARY": "Music/Zotify Podcasts",
        "ZOTIFY_PLAYLIST_LIBRARY": "Music/Zotify Playlists",
        "ZOTIFY_OUTPUT_ALBUM": "{album_artist}/{album}/{track_number}. {artists} - {title}",
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
    }

    # Update global configurations
    for key, default_value in zotify_global_configs.items():
        Config.set(key, default_value)

    # Update the database with global configurations
    await database.update_config(zotify_global_configs)

    # Remove zotify config files if they exist
    from bot import LOGGER

    # Remove global zotify credentials file
    zotify_credentials_path = "zotify_credentials.json"
    if await aiopath.exists(zotify_credentials_path):
        try:
            await aioremove(zotify_credentials_path)
            LOGGER.info("Removed global zotify credentials file")
        except Exception as e:
            LOGGER.error(f"Error removing zotify credentials file: {e}")

    # Remove user-specific zotify configs
    for user_id in user_data:
        user_credentials_path = f"zotify_configs/{user_id}_credentials.json"
        if await aiopath.exists(user_credentials_path):
            try:
                await aioremove(user_credentials_path)
                LOGGER.info(f"Removed zotify credentials for user {user_id}")
            except Exception as e:
                LOGGER.error(
                    f"Error removing zotify credentials for user {user_id}: {e}"
                )


async def reset_gallery_dl_configs(database):
    """Reset all gallery-dl-related configurations to their default values when gallery-dl is disabled.

    Args:
        database: The database instance to update configurations
    """
    from bot import LOGGER

    # Reset user-specific gallery-dl configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Gallery-dl-related keys to reset
        gallery_dl_keys = [
            "gallery_dl_quality",
            "gallery_dl_format",
            "gallery_dl_archive",
            "gallery_dl_metadata",
            "gallery_dl_limit",
        ]

        for key in gallery_dl_keys:
            if key in user_dict:
                del user_dict[key]
                user_configs_to_reset = True

        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Reset global gallery-dl configurations to default values
    gallery_dl_global_configs = {
        "GALLERY_DL_ENABLED": False,
        "GALLERY_DL_QUALITY_SELECTION": True,
        "GALLERY_DL_MAX_DOWNLOADS": 50,
        "GALLERY_DL_RATE_LIMIT": "1/s",
        "GALLERY_DL_ARCHIVE_ENABLED": True,
        "GALLERY_DL_METADATA_ENABLED": True,
        "GALLERY_DL_LIMIT": 0,
        # Authentication configs
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

    # Update the global configurations in the database
    await database.update_config(gallery_dl_global_configs)

    # Update Config object with the reset values
    from bot.core.config_manager import Config

    for key, value in gallery_dl_global_configs.items():
        setattr(Config, key, value)

    # Gallery-dl operations disabled without logging
    LOGGER.info(
        "Gallery-dl has been disabled. All related configurations have been reset to default values."
    )


async def reset_ddl_configs(database):
    """Reset all DDL-related configurations to their default values when DDL is disabled.

    Args:
        database: The database instance to update configurations
    """
    from bot.core.config_manager import Config

    # Reset owner DDL configurations to default values
    ddl_configs = {
        "DDL_ENABLED": False,
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
    }

    # Update Config object
    for key, value in ddl_configs.items():
        setattr(Config, key, value)

    # Update database
    await database.update_config(ddl_configs)

    # Reset all user DDL configurations
    from bot import user_data

    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # DDL-related keys to reset
        ddl_keys = [
            "DDL_SERVER",
            "GOFILE_API_KEY",
            "GOFILE_FOLDER_NAME",
            "GOFILE_PUBLIC_LINKS",
            "GOFILE_PASSWORD_PROTECTION",
            "GOFILE_DEFAULT_PASSWORD",
            "GOFILE_LINK_EXPIRY_DAYS",
            "STREAMTAPE_API_USERNAME",
            "STREAMTAPE_API_PASSWORD",
            "STREAMTAPE_FOLDER_NAME",
            "DEVUPLOADS_API_KEY",
            "DEVUPLOADS_FOLDER_NAME",
            "DEVUPLOADS_PUBLIC_FILES",
            "MEDIAFIRE_EMAIL",
            "MEDIAFIRE_PASSWORD",
            "MEDIAFIRE_APP_ID",
            "MEDIAFIRE_API_KEY",
        ]

        # Reset each DDL-related key
        for key in ddl_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Reset user's DEFAULT_UPLOAD to first available service if it's set to DDL
        if user_dict.get("DEFAULT_UPLOAD") == "ddl":
            from bot.core.config_manager import Config

            # Find first available service as fallback
            if Config.GDRIVE_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "gd"
            elif Config.RCLONE_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "rc"
            elif Config.YOUTUBE_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "yt"
            elif Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED:
                user_dict["DEFAULT_UPLOAD"] = "mg"
            else:
                user_dict["DEFAULT_UPLOAD"] = (
                    "gd"  # Keep as gd if no other service available
                )
            user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # DDL operations disabled without logging


async def reset_ai_configs(database):
    """Reset all AI-related configurations to their default values when AI is disabled.

    Args:
        database: The database instance to update configurations
    """
    # Reset user-specific AI configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # AI-related keys to reset
        ai_keys = [
            # Core AI Settings
            "DEFAULT_AI_MODEL",
            "AI_CONVERSATION_MODE",
            "AI_LANGUAGE",
            # AI Feature Settings
            "AI_STREAMING_ENABLED",
            "AI_PLUGINS_ENABLED",
            "AI_MULTIMODAL_ENABLED",
            "AI_CONVERSATION_HISTORY",
            "AI_MAX_HISTORY_LENGTH",
            "AI_QUESTION_PREDICTION",
            "AI_GROUP_TOPIC_MODE",
            "AI_INLINE_MODE_ENABLED",
            "AI_AUTO_LANGUAGE_DETECTION",
            "AI_DEFAULT_LANGUAGE",
            # New ChatGPT-Telegram-Bot Features
            "AI_VOICE_TRANSCRIPTION_ENABLED",
            "AI_IMAGE_GENERATION_ENABLED",
            "AI_DOCUMENT_PROCESSING_ENABLED",
            "AI_FOLLOW_UP_QUESTIONS_ENABLED",
            "AI_CONVERSATION_EXPORT_ENABLED",
            "AI_TYPEWRITER_EFFECT_ENABLED",
            "AI_CONTEXT_PRUNING_ENABLED",
            # AI Plugin Settings
            "AI_WEB_SEARCH_ENABLED",
            "AI_URL_SUMMARIZATION_ENABLED",
            "AI_ARXIV_ENABLED",
            "AI_CODE_INTERPRETER_ENABLED",
            # AI Budget Settings
            "AI_DAILY_TOKEN_LIMIT",
            "AI_MONTHLY_TOKEN_LIMIT",
            "AI_DAILY_COST_LIMIT",
            "AI_MONTHLY_COST_LIMIT",
            # AI Performance Settings
            "AI_MAX_TOKENS",
            "AI_TEMPERATURE",
            "AI_TIMEOUT",
            "AI_RATE_LIMIT_PER_USER",
            # AI API Keys
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_AI_API_KEY",
            "GROQ_API_KEY",
            "VERTEX_PROJECT_ID",
            "VERTEX_AI_LOCATION",
            # AI API URLs
            "OPENAI_API_URL",
            "ANTHROPIC_API_URL",
            "GOOGLE_AI_API_URL",
            "GROQ_API_URL",
            "MISTRAL_API_URL",
            "DEEPSEEK_API_URL",
        ]

        # Reset each AI-related key
        for key in ai_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # AI operations disabled without logging


async def reset_ai_provider_configs(provider_name, database):
    """Reset AI provider-specific configurations when a provider is disabled.

    Args:
        provider_name: The name of the AI provider (openai, anthropic, google, groq, etc.)
        database: The database instance to update configurations
    """
    # Reset user-specific provider configurations
    for user_id, user_dict in list(user_data.items()):
        user_configs_to_reset = False

        # Provider-specific keys to reset based on provider name
        provider_keys = []

        if provider_name.lower() == "openai":
            provider_keys = [
                "OPENAI_API_KEY",
                "OPENAI_API_URL",
            ]
            # Reset model if it's an OpenAI model
            current_model = user_dict.get("DEFAULT_AI_MODEL", "")
            if current_model.startswith(("gpt-", "chatgpt")):
                user_dict.pop("DEFAULT_AI_MODEL", None)
                user_configs_to_reset = True

        elif provider_name.lower() == "anthropic":
            provider_keys = [
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_API_URL",
            ]
            # Reset model if it's an Anthropic model
            current_model = user_dict.get("DEFAULT_AI_MODEL", "")
            if current_model.startswith("claude"):
                user_dict.pop("DEFAULT_AI_MODEL", None)
                user_configs_to_reset = True

        elif provider_name.lower() == "google":
            provider_keys = [
                "GOOGLE_AI_API_KEY",
                "GOOGLE_AI_API_URL",
                "VERTEX_PROJECT_ID",
                "VERTEX_AI_LOCATION",
            ]
            # Reset model if it's a Google model
            current_model = user_dict.get("DEFAULT_AI_MODEL", "")
            if current_model.startswith(("gemini", "vertex")):
                user_dict.pop("DEFAULT_AI_MODEL", None)
                user_configs_to_reset = True

        elif provider_name.lower() == "groq":
            provider_keys = [
                "GROQ_API_KEY",
                "GROQ_API_URL",
            ]
            # Reset model if it's a Groq model
            current_model = user_dict.get("DEFAULT_AI_MODEL", "")
            if "groq" in current_model.lower() or current_model.startswith(
                ("mixtral", "llama")
            ):
                user_dict.pop("DEFAULT_AI_MODEL", None)
                user_configs_to_reset = True

        # Reset each provider-specific key
        for key in provider_keys:
            if key in user_dict:
                user_dict.pop(key, None)
                user_configs_to_reset = True

        # Update the database if there are user configurations to reset
        if user_configs_to_reset:
            await database.update_user_data(user_id)

    # Provider-specific AI operations disabled without logging
