"""
Zotify configuration management
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from zotify.utils import AudioFormat, ImageSize, Quality

from bot import LOGGER
from bot.core.config_manager import Config


class ZotifyConfigManager:
    """Manages Zotify configuration and settings"""

    def __init__(self):
        self._config_cache = None
        self._credentials_path = Path(Config.ZOTIFY_CREDENTIALS_PATH).expanduser()
        self._initialization_attempted = False

    async def lazy_initialize(self, user_id: int | None = None) -> bool:
        """Lazy initialization - only initialize when needed"""
        if self._initialization_attempted:
            return Config.ZOTIFY_ENABLED

        self._initialization_attempted = True

        # Zotify enabled/disabled status is controlled only by configuration
        # Don't auto-disable based on credentials - let users handle missing credentials
        return Config.ZOTIFY_ENABLED

    def get_quality(self) -> Quality:
        """Get configured quality setting"""
        quality_map = {
            "auto": Quality.AUTO,
            "normal": Quality.NORMAL,
            "high": Quality.HIGH,
            "very_high": Quality.VERY_HIGH,
        }
        return quality_map.get(Config.ZOTIFY_DOWNLOAD_QUALITY.lower(), Quality.AUTO)

    def set_quality(self, quality: Quality):
        """Set quality setting"""
        quality_map = {
            Quality.AUTO: "auto",
            Quality.NORMAL: "normal",
            Quality.HIGH: "high",
            Quality.VERY_HIGH: "very_high",
        }
        Config.ZOTIFY_DOWNLOAD_QUALITY = quality_map.get(quality, "auto")

    def set_audio_format(self, audio_format: AudioFormat):
        """Set audio format setting"""
        format_map = {
            AudioFormat.VORBIS: "vorbis",
            AudioFormat.MP3: "mp3",
            AudioFormat.FLAC: "flac",
            AudioFormat.AAC: "aac",
            AudioFormat.WAV: "wav",
        }
        Config.ZOTIFY_AUDIO_FORMAT = format_map.get(audio_format, "vorbis")

    def get_audio_format(self) -> AudioFormat:
        """Get configured audio format"""
        format_map = {
            "vorbis": AudioFormat.VORBIS,
            "mp3": AudioFormat.MP3,
            "flac": AudioFormat.FLAC,
            "aac": AudioFormat.AAC,
            "fdk_aac": AudioFormat.FDK_AAC,
            "opus": AudioFormat.OPUS,
            "wav": AudioFormat.WAV,
            "wavpack": AudioFormat.WAVPACK,
        }
        return format_map.get(Config.ZOTIFY_AUDIO_FORMAT.lower(), AudioFormat.VORBIS)

    def get_image_size(self) -> ImageSize:
        """Get configured cover art size"""
        size_map = {
            "small": ImageSize.SMALL,
            "medium": ImageSize.MEDIUM,
            "large": ImageSize.LARGE,
        }
        return size_map.get(Config.ZOTIFY_ARTWORK_SIZE.lower(), ImageSize.LARGE)

    def get_credentials_path(self) -> Path:
        """Get credentials file path"""
        return self._credentials_path

    async def has_credentials(self, user_id: int | None = None) -> bool:
        """Check if credentials exist in database or file"""
        try:
            # Check database first
            if user_id:
                from bot.helper.ext_utils.db_handler import database

                if database.db is not None:
                    user_data = await database.db.users.find_one({"_id": user_id})
                    if user_data and "ZOTIFY_CREDENTIALS" in user_data:
                        return True

            # If no user_id provided or user doesn't have credentials, check for any credentials
            # This handles cases where OWNER_ID is not set or credentials were uploaded by different user
            if not user_id or user_id == 0:
                from bot.helper.ext_utils.db_handler import database

                if database.db is not None:
                    # Check if any user has credentials
                    any_user_data = await database.db.users.find_one(
                        {"ZOTIFY_CREDENTIALS": {"$exists": True}}
                    )
                    if any_user_data:
                        return True

            # Fallback to file check
            return self._credentials_path.exists()
        except Exception as e:
            LOGGER.error(f"Error checking Zotify credentials: {e}")
            return self._credentials_path.exists()

    def has_credentials_sync(self) -> bool:
        """Synchronous check for credentials file (for backward compatibility)"""
        return self._credentials_path.exists()

    def get_auth_method(self) -> str:
        """Determine the best authentication method to use"""
        if self._credentials_path.exists():
            return "file"
        return "interactive"

    def get_language(self) -> str:
        """Get configured language"""
        return Config.ZOTIFY_LANGUAGE

    def create_zotify_config(self) -> "Config":
        """Create a Zotify Config object from our settings"""
        from argparse import Namespace

        from zotify.config import Config as ZotifyConfig

        # Create a namespace with our config values
        args = Namespace()

        # Set all the config values
        args.credentials_path = self.get_credentials_path()
        args.album_library = Path(Config.ZOTIFY_ALBUM_LIBRARY).expanduser()
        args.podcast_library = Path(Config.ZOTIFY_PODCAST_LIBRARY).expanduser()
        args.playlist_library = Path(Config.ZOTIFY_PLAYLIST_LIBRARY).expanduser()
        args.output_album = Config.ZOTIFY_OUTPUT_ALBUM
        args.output_playlist_track = Config.ZOTIFY_OUTPUT_PLAYLIST_TRACK
        args.output_playlist_episode = Config.ZOTIFY_OUTPUT_PLAYLIST_EPISODE
        args.output_podcast = Config.ZOTIFY_OUTPUT_PODCAST
        args.output_single = Config.ZOTIFY_OUTPUT_SINGLE
        args.download_quality = Config.ZOTIFY_DOWNLOAD_QUALITY
        args.download_real_time = Config.ZOTIFY_DOWNLOAD_REAL_TIME
        args.artwork_size = Config.ZOTIFY_ARTWORK_SIZE
        args.audio_format = Config.ZOTIFY_AUDIO_FORMAT
        args.transcode_bitrate = Config.ZOTIFY_TRANSCODE_BITRATE
        args.ffmpeg_path = Config.ZOTIFY_FFMPEG_PATH or "xtra"
        args.ffmpeg_args = Config.ZOTIFY_FFMPEG_ARGS
        args.save_subtitles = Config.ZOTIFY_SAVE_SUBTITLES
        args.language = Config.ZOTIFY_LANGUAGE
        args.lyrics_file = Config.ZOTIFY_LYRICS_FILE
        args.lyrics_only = Config.ZOTIFY_LYRICS_ONLY
        args.create_playlist_file = Config.ZOTIFY_CREATE_PLAYLIST_FILE
        args.save_metadata = Config.ZOTIFY_SAVE_METADATA
        args.save_genre = Config.ZOTIFY_SAVE_GENRE
        args.all_artists = Config.ZOTIFY_ALL_ARTISTS
        args.replace_existing = Config.ZOTIFY_REPLACE_EXISTING
        args.skip_previous = Config.ZOTIFY_SKIP_PREVIOUS
        args.skip_duplicates = Config.ZOTIFY_SKIP_DUPLICATES
        args.print_downloads = Config.ZOTIFY_PRINT_DOWNLOADS
        args.print_progress = Config.ZOTIFY_PRINT_PROGRESS
        args.print_skips = Config.ZOTIFY_PRINT_SKIPS
        args.print_warnings = Config.ZOTIFY_PRINT_WARNINGS
        args.print_errors = Config.ZOTIFY_PRINT_ERRORS
        args.match = Config.ZOTIFY_MATCH_EXISTING

        # Additional args that Zotify expects
        args.config = None
        args.library = None
        args.output = None
        args.username = ""
        args.token = ""

        return ZotifyConfig(args)

    def get_download_config(self) -> dict[str, Any]:
        """Get download configuration dictionary matching Zotify's Config class"""
        return {
            # Core settings matching Zotify CONFIG_VALUES
            "credentials_path": self.get_credentials_path(),
            "album_library": Path(Config.ZOTIFY_ALBUM_LIBRARY).expanduser(),
            "podcast_library": Path(Config.ZOTIFY_PODCAST_LIBRARY).expanduser(),
            "playlist_library": Path(Config.ZOTIFY_PLAYLIST_LIBRARY).expanduser(),
            "output_album": Config.ZOTIFY_OUTPUT_ALBUM,
            "output_playlist_track": Config.ZOTIFY_OUTPUT_PLAYLIST_TRACK,
            "output_playlist_episode": Config.ZOTIFY_OUTPUT_PLAYLIST_EPISODE,
            "output_podcast": Config.ZOTIFY_OUTPUT_PODCAST,
            "output_single": Config.ZOTIFY_OUTPUT_SINGLE,
            "download_quality": self.get_quality(),
            "download_real_time": Config.ZOTIFY_DOWNLOAD_REAL_TIME,
            "artwork_size": self.get_image_size(),
            "audio_format": self.get_audio_format(),
            "transcode_bitrate": Config.ZOTIFY_TRANSCODE_BITRATE,
            "ffmpeg_path": Config.ZOTIFY_FFMPEG_PATH or "xtra",
            "ffmpeg_args": Config.ZOTIFY_FFMPEG_ARGS,
            "save_subtitles": Config.ZOTIFY_SAVE_SUBTITLES,
            "language": Config.ZOTIFY_LANGUAGE,
            "lyrics_file": Config.ZOTIFY_LYRICS_FILE,
            "lyrics_only": Config.ZOTIFY_LYRICS_ONLY,
            "create_playlist_file": Config.ZOTIFY_CREATE_PLAYLIST_FILE,
            "save_metadata": Config.ZOTIFY_SAVE_METADATA,
            "save_genre": Config.ZOTIFY_SAVE_GENRE,
            "all_artists": Config.ZOTIFY_ALL_ARTISTS,
            "replace_existing": Config.ZOTIFY_REPLACE_EXISTING,
            "skip_previous": Config.ZOTIFY_SKIP_PREVIOUS,
            "skip_duplicates": Config.ZOTIFY_SKIP_DUPLICATES,
            "print_downloads": Config.ZOTIFY_PRINT_DOWNLOADS,
            "print_progress": Config.ZOTIFY_PRINT_PROGRESS,
            "print_skips": Config.ZOTIFY_PRINT_SKIPS,
            "print_warnings": Config.ZOTIFY_PRINT_WARNINGS,
            "print_errors": Config.ZOTIFY_PRINT_ERRORS,
            "match": Config.ZOTIFY_MATCH_EXISTING,
        }

    async def save_credentials(
        self, credentials: dict[str, Any], user_id: int | None = None
    ) -> bool:
        """Save credentials to database and optionally to file with enhanced logging"""
        try:
            # Save to database for persistence across restarts
            if user_id:
                from bot.helper.ext_utils.db_handler import database

                if database.db is not None:
                    # First, check if user already has credentials
                    existing_user = await database.db.users.find_one(
                        {"_id": user_id}
                    )
                    if existing_user and "ZOTIFY_CREDENTIALS" in existing_user:
                        existing_user["ZOTIFY_CREDENTIALS"].get(
                            "username", "unknown"
                        )

                    # Force update using multiple approaches to ensure success
                    new_username = credentials.get("username", "unknown")

                    try:
                        # Method 1: Use replace_one for complete document replacement
                        user_doc = {
                            "_id": user_id,
                            "ZOTIFY_CREDENTIALS": credentials,
                        }
                        await database.db.users.replace_one(
                            {"_id": user_id},
                            user_doc,
                            upsert=True,
                        )

                    except Exception as replace_error:
                        LOGGER.warning(
                            f"Replace method failed: {replace_error}, trying update method"
                        )

                        # Method 2: Fallback to unset + set approach
                        await database.db.users.update_one(
                            {"_id": user_id},
                            {"$unset": {"ZOTIFY_CREDENTIALS": ""}},
                            upsert=True,
                        )

                        await database.db.users.update_one(
                            {"_id": user_id},
                            {"$set": {"ZOTIFY_CREDENTIALS": credentials}},
                            upsert=True,
                        )

                    # Always verify the save by reading back (regardless of update result)
                    verification = await database.db.users.find_one({"_id": user_id})
                    if verification and "ZOTIFY_CREDENTIALS" in verification:
                        saved_username = verification["ZOTIFY_CREDENTIALS"].get(
                            "username", "unknown"
                        )
                        if saved_username == new_username:
                            pass
                        else:
                            LOGGER.error(
                                f"❌ Database save mismatch: expected {new_username}, got {saved_username}"
                            )
                            return False
                    else:
                        LOGGER.error(
                            f"❌ Could not verify database save for user {user_id}"
                        )
                        return False

            # Also save to file for immediate use (will be recreated from DB on restart)
            self._credentials_path.parent.mkdir(parents=True, exist_ok=True)
            # Wrap file I/O in thread to prevent blocking
            await asyncio.to_thread(self._write_credentials_file, credentials)

            # Clear any cached sessions to force reload
            try:
                from bot.helper.mirror_leech_utils.zotify_utils.improved_session_manager import (
                    improved_session_manager,
                )

                await improved_session_manager.clear_session_cache()

            except Exception as cache_error:
                LOGGER.warning(f"Could not clear session cache: {cache_error}")

            return True
        except Exception as e:
            LOGGER.error(f"❌ Failed to save Zotify credentials: {e}")
            return False

    async def load_credentials(
        self, user_id: int | None = None
    ) -> dict[str, Any] | None:
        """Load credentials from database first, then file as fallback with enhanced debugging"""
        try:
            # Try to load from database first (persistent across restarts)
            if user_id:
                from bot.helper.ext_utils.db_handler import database

                if database.db is not None:
                    user_data = await database.db.users.find_one({"_id": user_id})
                    if user_data and "ZOTIFY_CREDENTIALS" in user_data:
                        credentials = user_data["ZOTIFY_CREDENTIALS"]
                        credentials.get("username", "unknown")

                        # Also save to file for immediate use
                        self.save_credentials_to_file(credentials)
                        return credentials

            # If no user_id provided or user doesn't have credentials, check for any credentials
            # This handles cases where OWNER_ID is not set or credentials were uploaded by different user
            if not user_id or user_id == 0:
                from bot.helper.ext_utils.db_handler import database

                if database.db is not None:
                    # Check if any user has credentials
                    any_user_data = await database.db.users.find_one(
                        {"ZOTIFY_CREDENTIALS": {"$exists": True}}
                    )
                    if any_user_data:
                        credentials = any_user_data["ZOTIFY_CREDENTIALS"]
                        credentials.get("username", "unknown")

                        # Also save to file for immediate use
                        self.save_credentials_to_file(credentials)
                        return credentials

            # Fallback to file if database doesn't have credentials
            if self._credentials_path.exists():
                # Wrap file I/O in thread to prevent blocking
                return await asyncio.to_thread(self._read_credentials_file)

        except Exception as e:
            LOGGER.error(f"❌ Failed to load Zotify credentials: {e}")

        LOGGER.warning(f"⚠️ No Zotify credentials found for user {user_id}")
        return None

    def _write_credentials_file(self, credentials: dict[str, Any]) -> None:
        """Helper method for writing credentials file (synchronous for thread use)"""
        with open(self._credentials_path, "w") as f:
            json.dump(credentials, f, indent=2)

    def _read_credentials_file(self) -> dict[str, Any]:
        """Helper method for reading credentials file (synchronous for thread use)"""
        with open(self._credentials_path) as f:
            return json.load(f)

    def save_credentials_to_file(self, credentials: dict[str, Any]) -> bool:
        """Save credentials to file only (helper method)"""
        try:
            self._credentials_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_credentials_file(credentials)
            return True
        except Exception as e:
            LOGGER.error(f"Failed to save Zotify credentials to file: {e}")
            return False

    def is_enabled(self) -> bool:
        """Check if Zotify is enabled"""
        return Config.ZOTIFY_ENABLED

    def get_supported_audio_formats(self) -> list:
        """Get list of supported audio formats"""
        return Config.ZOTIFY_SUPPORTED_AUDIO_FORMATS.copy()

    def get_supported_qualities(self) -> list:
        """Get list of supported qualities"""
        return Config.ZOTIFY_SUPPORTED_QUALITIES.copy()

    def get_supported_artwork_sizes(self) -> list:
        """Get list of supported artwork sizes"""
        return Config.ZOTIFY_SUPPORTED_ARTWORK_SIZES.copy()

    def validate_audio_format(self, format_name: str) -> bool:
        """Validate if audio format is supported"""
        return format_name.lower() in [
            f.lower() for f in Config.ZOTIFY_SUPPORTED_AUDIO_FORMATS
        ]

    def validate_quality(self, quality: str) -> bool:
        """Validate if quality is supported"""
        return quality.lower() in [
            q.lower() for q in Config.ZOTIFY_SUPPORTED_QUALITIES
        ]

    def validate_artwork_size(self, size: str) -> bool:
        """Validate if artwork size is supported"""
        return size.lower() in [
            s.lower() for s in Config.ZOTIFY_SUPPORTED_ARTWORK_SIZES
        ]


# Global instance
zotify_config = ZotifyConfigManager()


# Convenience functions
def get_zotify_config() -> ZotifyConfigManager:
    """Get global Zotify config instance"""
    return zotify_config


def is_zotify_enabled() -> bool:
    """Check if Zotify is enabled"""
    return zotify_config.is_enabled()


async def has_zotify_credentials(user_id: int | None = None) -> bool:
    """Check if Zotify credentials are available"""
    return await zotify_config.has_credentials(user_id)


def has_zotify_credentials_sync() -> bool:
    """Synchronous check for Zotify credentials (for backward compatibility)"""
    return zotify_config.has_credentials_sync()


async def ensure_zotify_initialized(user_id: int | None = None) -> bool:
    """Ensure Zotify is initialized and enabled when needed"""
    return await zotify_config.lazy_initialize(user_id)
