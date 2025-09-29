import shutil
from pathlib import Path

from bot import DOWNLOAD_DIR, LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.db_handler import database

try:
    from streamrip.config import Config as StreamripConfig

    # Check if the Config class has the expected methods
    if not hasattr(StreamripConfig, "defaults"):
        LOGGER.error(
            "StreamripConfig.defaults method not found - incompatible streamrip version"
        )
        STREAMRIP_AVAILABLE = False
    else:
        STREAMRIP_AVAILABLE = True

except ImportError as e:
    STREAMRIP_AVAILABLE = False
    LOGGER.warning(
        f"Streamrip not installed: {e}. Streamrip features will be disabled."
    )


class StreamripConfigHelper:
    """
    Redesigned streamrip configuration system that follows your requirements:
    1. Bot settings → streamrip_config.toml in bot directory
    2. Custom config upload → direct replacement of config file
    3. Single source of truth: the config file
    """

    def __init__(self):
        self.config: StreamripConfig | None = None
        # Use bot's working directory for config file (as per your requirement)
        self.config_path = Path.cwd() / "streamrip_config.toml"
        # Streamrip's expected location - fix for Docker container
        # In Docker, Path.home() might return /usr/src/app instead of /root
        # So we explicitly use /root/.config/streamrip/config.toml
        import os

        home_dir = os.path.expanduser("~")
        if home_dir == "/usr/src/app":
            # We're in Docker container, use /root instead
            home_dir = "/root"
        self.streamrip_config_path = (
            Path(home_dir) / ".config" / "streamrip" / "config.toml"
        )
        self._initialized = False
        self._initialization_attempted = False

    async def lazy_initialize(self) -> bool:
        """Lazy initialization - only initialize when needed"""
        if self._initialized:
            return True

        if self._initialization_attempted:
            return False

        success = await self.initialize()
        self._initialization_attempted = True

        if success:
            Config.STREAMRIP_ENABLED = True
        else:
            Config.STREAMRIP_ENABLED = False
            LOGGER.warning("Streamrip disabled due to initialization failure")

        return success

    async def initialize(self) -> bool:
        """Initialize streamrip configuration according to new design"""
        if not STREAMRIP_AVAILABLE:
            LOGGER.error("Streamrip is not available")
            return False

        try:
            # Check if we have any credentials in bot settings
            has_credentials = self._has_any_credentials()

            # Step 1: Check if custom config exists in bot directory
            if self.config_path.exists():
                # If we have credentials in bot settings, always update the config
                if has_credentials:
                    await self._create_config_from_bot_settings()

                # Load the config (either existing or updated)
                self.config = StreamripConfig(str(self.config_path))
            else:
                # Step 2: Create default config from bot settings
                await self._create_config_from_bot_settings()
                self.config = StreamripConfig(str(self.config_path))

            # Step 4: Always copy to streamrip's expected location
            await self._deploy_config_to_streamrip()

            self._initialized = True

            return True

        except Exception as e:
            LOGGER.error(f"Failed to initialize streamrip config: {e}")
            Config.STREAMRIP_ENABLED = False
            self._initialized = False
            self.config = None
            return False

    def _has_any_credentials(self) -> bool:
        """Check if bot settings have any streamrip credentials configured"""
        # Check Qobuz credentials
        qobuz_email = getattr(Config, "STREAMRIP_QOBUZ_EMAIL", "") or ""
        qobuz_password = getattr(Config, "STREAMRIP_QOBUZ_PASSWORD", "") or ""

        # Check Tidal credentials
        tidal_access_token = (
            getattr(Config, "STREAMRIP_TIDAL_ACCESS_TOKEN", "") or ""
        )

        # Check Deezer credentials
        deezer_arl = getattr(Config, "STREAMRIP_DEEZER_ARL", "") or ""

        # Check SoundCloud credentials
        soundcloud_client_id = (
            getattr(Config, "STREAMRIP_SOUNDCLOUD_CLIENT_ID", "") or ""
        )

        return bool(
            (qobuz_email.strip() and qobuz_password.strip())
            or tidal_access_token.strip()
            or deezer_arl.strip()
            or soundcloud_client_id.strip()
        )

    async def _create_config_from_bot_settings(self) -> None:
        """Create config file from bot settings"""
        config_content = self._generate_config_from_settings()
        await self._save_config_to_file(config_content)

    def _generate_config_from_settings(self) -> str:
        """Generate comprehensive TOML config content from bot settings"""
        # Get all credentials with proper defaults
        qobuz_email = getattr(Config, "STREAMRIP_QOBUZ_EMAIL", "") or ""
        qobuz_password = getattr(Config, "STREAMRIP_QOBUZ_PASSWORD", "") or ""
        qobuz_app_id = getattr(Config, "STREAMRIP_QOBUZ_APP_ID", "") or ""
        qobuz_secrets = getattr(Config, "STREAMRIP_QOBUZ_SECRETS", []) or []

        tidal_access_token = (
            getattr(Config, "STREAMRIP_TIDAL_ACCESS_TOKEN", "") or ""
        )
        tidal_refresh_token = (
            getattr(Config, "STREAMRIP_TIDAL_REFRESH_TOKEN", "") or ""
        )
        tidal_user_id = getattr(Config, "STREAMRIP_TIDAL_USER_ID", "") or ""
        tidal_country_code = (
            getattr(Config, "STREAMRIP_TIDAL_COUNTRY_CODE", "US") or "US"
        )
        tidal_token_expiry = (
            getattr(Config, "STREAMRIP_TIDAL_TOKEN_EXPIRY", "1748842786")
            or "1748842786"
        )

        deezer_arl = getattr(Config, "STREAMRIP_DEEZER_ARL", "") or ""

        soundcloud_client_id = (
            getattr(Config, "STREAMRIP_SOUNDCLOUD_CLIENT_ID", "") or ""
        )
        soundcloud_app_version = (
            getattr(Config, "STREAMRIP_SOUNDCLOUD_APP_VERSION", "") or ""
        )

        # Format secrets as TOML array
        secrets_str = str(qobuz_secrets).replace("'", '"') if qobuz_secrets else "[]"

        return f"""# Streamrip Configuration
# Generated from bot settings

[downloads]
folder = "{DOWNLOAD_DIR}"
source_subdirectories = {str(getattr(Config, "STREAMRIP_SOURCE_SUBDIRECTORIES", False)).lower()}
disc_subdirectories = {str(getattr(Config, "STREAMRIP_DISC_SUBDIRECTORIES", True)).lower()}
concurrency = {str(getattr(Config, "STREAMRIP_CONCURRENCY", True)).lower()}
max_connections = {getattr(Config, "STREAMRIP_MAX_CONNECTIONS", 6)}
requests_per_minute = {getattr(Config, "STREAMRIP_REQUESTS_PER_MINUTE", 60)}
verify_ssl = {str(getattr(Config, "STREAMRIP_VERIFY_SSL", True)).lower()}

[qobuz]
quality = {getattr(Config, "STREAMRIP_QOBUZ_QUALITY", 3)}
download_booklets = {str(getattr(Config, "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS", True)).lower()}
use_auth_token = {str(getattr(Config, "STREAMRIP_QOBUZ_USE_AUTH_TOKEN", False)).lower()}
email_or_userid = "{qobuz_email}"
password_or_token = "{qobuz_password}"
app_id = "{qobuz_app_id}"
secrets = {secrets_str}

[tidal]
quality = {getattr(Config, "STREAMRIP_TIDAL_QUALITY", 3)}
download_videos = {str(getattr(Config, "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS", True)).lower()}
user_id = "{tidal_user_id}"
country_code = "{tidal_country_code}"
access_token = "{tidal_access_token}"
refresh_token = "{tidal_refresh_token}"
token_expiry = "{tidal_token_expiry}"

[deezer]
quality = {getattr(Config, "STREAMRIP_DEEZER_QUALITY", 2)}
arl = "{deezer_arl}"
use_deezloader = {str(getattr(Config, "STREAMRIP_DEEZER_USE_DEEZLOADER", True)).lower()}
deezloader_warnings = {str(getattr(Config, "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS", True)).lower()}

[soundcloud]
quality = {getattr(Config, "STREAMRIP_SOUNDCLOUD_QUALITY", 0)}
client_id = "{soundcloud_client_id}"
app_version = "{soundcloud_app_version}"

[youtube]
quality = {getattr(Config, "STREAMRIP_YOUTUBE_QUALITY", 0)}
download_videos = {str(getattr(Config, "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS", False)).lower()}
video_downloads_folder = "{getattr(Config, "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER", "")}"

[database]
downloads_enabled = {str(getattr(Config, "STREAMRIP_DATABASE_DOWNLOADS_ENABLED", True)).lower()}
downloads_path = "{getattr(Config, "STREAMRIP_DATABASE_DOWNLOADS_PATH", "./downloads.db")}"
failed_downloads_enabled = {str(getattr(Config, "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED", True)).lower()}
failed_downloads_path = "{getattr(Config, "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH", "./failed_downloads.db")}"

[conversion]
enabled = {str(getattr(Config, "STREAMRIP_CONVERSION_ENABLED", False)).lower()}
codec = "{getattr(Config, "STREAMRIP_CONVERSION_CODEC", "ALAC")}"
sampling_rate = {getattr(Config, "STREAMRIP_CONVERSION_SAMPLING_RATE", 48000)}
bit_depth = {getattr(Config, "STREAMRIP_CONVERSION_BIT_DEPTH", 24)}
lossy_bitrate = {getattr(Config, "STREAMRIP_CONVERSION_LOSSY_BITRATE", 320)}

[qobuz_filters]
extras = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_EXTRAS", False)).lower()}
repeats = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_REPEATS", False)).lower()}
non_albums = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS", False)).lower()}
features = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_FEATURES", False)).lower()}
non_studio_albums = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS", False)).lower()}
non_remaster = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER", False)).lower()}

[artwork]
embed = {str(getattr(Config, "STREAMRIP_EMBED_COVER_ART", True)).lower()}
embed_size = "{getattr(Config, "STREAMRIP_COVER_ART_SIZE", "large")}"
embed_max_width = {getattr(Config, "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH", -1)}
save_artwork = {str(getattr(Config, "STREAMRIP_SAVE_COVER_ART", True)).lower()}
saved_max_width = {getattr(Config, "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH", -1)}

[metadata]
set_playlist_to_album = {str(getattr(Config, "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM", True)).lower()}
renumber_playlist_tracks = {str(getattr(Config, "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS", True)).lower()}
exclude = {str(getattr(Config, "STREAMRIP_METADATA_EXCLUDE", [])).replace("'", '"')}

[filepaths]
add_singles_to_folder = {str(getattr(Config, "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER", False)).lower()}
folder_format = "{getattr(Config, "STREAMRIP_FILEPATHS_FOLDER_FORMAT", "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]")}"
track_format = "{getattr(Config, "STREAMRIP_FILEPATHS_TRACK_FORMAT", "{tracknumber:02}. {artist} - {title}{explicit}")}"
restrict_characters = {str(getattr(Config, "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS", False)).lower()}
truncate_to = {getattr(Config, "STREAMRIP_FILEPATHS_TRUNCATE_TO", 120)}

[lastfm]
source = "{getattr(Config, "STREAMRIP_LASTFM_SOURCE", "qobuz")}"
fallback_source = "{getattr(Config, "STREAMRIP_LASTFM_FALLBACK_SOURCE", "")}"

[cli]
text_output = {str(getattr(Config, "STREAMRIP_CLI_TEXT_OUTPUT", True)).lower()}
progress_bars = {str(getattr(Config, "STREAMRIP_CLI_PROGRESS_BARS", False)).lower()}
max_search_results = {getattr(Config, "STREAMRIP_CLI_MAX_SEARCH_RESULTS", 100)}

[misc]
version = "{getattr(Config, "STREAMRIP_MISC_VERSION", "2.1.0")}"
check_for_updates = {str(getattr(Config, "STREAMRIP_MISC_CHECK_FOR_UPDATES", False)).lower()}
"""

    async def _save_config_to_file(self, content: str) -> None:
        """Save config content to file and backup to database"""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Write config file
            import aiofiles

            async with aiofiles.open(self.config_path, "w") as f:
                await f.write(content)

            # Backup to database for redundancy
            await self._backup_config_to_database(content)

        except Exception as e:
            LOGGER.error(f"Failed to save config file: {e}")
            raise

    async def _deploy_config_to_streamrip(self) -> None:
        """Copy config file to streamrip's expected location"""
        try:
            # Ensure streamrip config directory exists
            self.streamrip_config_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy config file
            shutil.copy2(self.config_path, self.streamrip_config_path)

        except Exception as e:
            LOGGER.error(f"Failed to deploy config to streamrip location: {e}")
            raise

    # ===== BOT SETTINGS INTEGRATION =====

    async def update_config_from_bot_settings(self) -> bool:
        """Update config file when bot settings change"""
        try:
            # Generate new config from current bot settings
            config_content = self._generate_config_from_settings()

            # Save to file
            await self._save_config_to_file(config_content)

            # Deploy to streamrip location
            await self._deploy_config_to_streamrip()

            # Reload config object
            self.config = StreamripConfig(str(self.config_path))

            return True

        except Exception as e:
            LOGGER.error(f"Failed to update config from bot settings: {e}")
            return False

    # ===== CUSTOM CONFIG MANAGEMENT =====

    async def upload_custom_config(self, config_content: str) -> bool:
        """Upload and deploy custom config file"""
        try:
            # Validate config by trying to parse it
            try:
                # Save to temporary location first
                temp_path = self.config_path.with_suffix(".tmp")
                await self._save_config_to_file_path(config_content, temp_path)

                # Try to load it to validate
                test_config = StreamripConfig(str(temp_path))

                # If successful, replace the main config
                temp_path.replace(self.config_path)

                # Deploy to streamrip location
                await self._deploy_config_to_streamrip()

                # Backup to database
                await self._backup_config_to_database(config_content)

                # Reload config object
                self.config = test_config

                return True

            except Exception as e:
                # Clean up temp file if it exists
                temp_path = self.config_path.with_suffix(".tmp")
                if temp_path.exists():
                    temp_path.unlink()
                raise e

        except Exception as e:
            LOGGER.error(f"Failed to upload custom config: {e}")
            return False

    async def _save_config_to_file_path(self, content: str, path: Path) -> None:
        """Save config content to specific file path"""
        try:
            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write config file
            import aiofiles

            async with aiofiles.open(path, "w") as f:
                await f.write(content)

        except Exception as e:
            LOGGER.error(f"Failed to save config to {path}: {e}")
            raise

    async def get_current_config_content(self) -> str | None:
        """Get current config file content"""
        try:
            if self.config_path.exists():
                import aiofiles

                async with aiofiles.open(self.config_path) as f:
                    return await f.read()
            return None
        except Exception as e:
            LOGGER.error(f"Failed to read config file: {e}")
            return None

    async def reset_to_default_config(self) -> bool:
        """Reset config to default based on bot settings"""
        try:
            # Remove existing config file
            if self.config_path.exists():
                self.config_path.unlink()

            # Create new config from bot settings
            await self._create_config_from_bot_settings()

            # Deploy to streamrip location
            await self._deploy_config_to_streamrip()

            # Reload config object
            self.config = StreamripConfig(str(self.config_path))

            return True

        except Exception as e:
            LOGGER.error(f"Failed to reset config: {e}")
            return False

    # ===== UTILITY METHODS =====

    def get_config(self) -> StreamripConfig | None:
        """Get the streamrip configuration"""
        return self.config if self._initialized else None

    def is_initialized(self) -> bool:
        """Check if config helper is initialized"""
        return self._initialized

    def get_platform_status(self) -> dict[str, bool]:
        """Get simplified platform status"""
        qobuz_enabled = bool(
            Config.STREAMRIP_QOBUZ_ENABLED and Config.STREAMRIP_QOBUZ_EMAIL
        )
        tidal_enabled = bool(
            Config.STREAMRIP_TIDAL_ENABLED and Config.STREAMRIP_TIDAL_ACCESS_TOKEN
        )
        deezer_enabled = bool(
            Config.STREAMRIP_DEEZER_ENABLED and Config.STREAMRIP_DEEZER_ARL
        )
        soundcloud_enabled = Config.STREAMRIP_SOUNDCLOUD_ENABLED
        lastfm_enabled = Config.STREAMRIP_LASTFM_ENABLED

        return {
            "qobuz": qobuz_enabled,
            "tidal": tidal_enabled,
            "deezer": deezer_enabled,
            "soundcloud": soundcloud_enabled,
            "lastfm": lastfm_enabled,
        }

    def get_config_file_path(self) -> Path:
        """Get the path to the config file"""
        return self.config_path

    def get_config_path(self) -> str:
        """Get the path to the streamrip config file as string"""
        return str(self.streamrip_config_path)

    def is_database_enabled(self) -> bool:
        """Check if streamrip database is enabled"""
        return getattr(Config, "STREAMRIP_DATABASE_DOWNLOADS_ENABLED", True)

    async def _backup_config_to_database(self, content: str) -> None:
        """Backup config content to database for redundancy"""
        try:
            if database.db is not None:
                from bot.core.aeon_client import TgClient

                # Store config as binary data in database
                config_bytes = content.encode("utf-8")

                await database.db.settings.files.update_one(
                    {"_id": TgClient.ID},
                    {"$set": {"streamrip_config__toml": config_bytes}},
                    upsert=True,
                )

            else:
                LOGGER.warning("Database not available for config backup")
        except Exception as e:
            LOGGER.warning(f"Failed to backup config to database: {e}")
            # Don't raise - backup failure shouldn't stop the main operation


# Global config helper instance
streamrip_config = StreamripConfigHelper()


async def ensure_streamrip_initialized() -> bool:
    """Ensure streamrip is initialized and enabled when needed"""
    return await streamrip_config.lazy_initialize()


async def force_streamrip_config_update() -> bool:
    """Force update streamrip config from current bot settings"""
    try:
        if streamrip_config._initialized:
            return await streamrip_config.update_config_from_bot_settings()
        # If not initialized, initialize it (which will use current bot settings)
        return await streamrip_config.lazy_initialize()
    except Exception as e:
        LOGGER.error(f"Failed to force update streamrip config: {e}")
        return False
