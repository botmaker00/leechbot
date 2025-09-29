"""
Gallery-dl authentication manager for aimleechbot
Supports OAuth, API keys, cookies, and session management
"""

import json
import os
from typing import Any

from bot import LOGGER
from bot.helper.ext_utils.aiofiles_compat import aiofiles, aiopath

# Import database with error handling
try:
    from bot.helper.ext_utils.db_handler import database

    DATABASE_AVAILABLE = True
except Exception:
    DATABASE_AVAILABLE = False
    database = None


class GalleryDLAuthManager:
    """Advanced authentication manager for gallery-dl"""

    def __init__(self):
        self.auth_cache = {}
        self.session_cache = {}
        self.oauth_tokens = {}
        self.api_keys = {}
        self.cookies = {}

    async def setup_authentication(
        self, platform: str, config: dict[str, Any], user_id: int | None = None
    ) -> dict[str, Any]:
        """Setup authentication for a specific platform"""
        try:
            # Validate inputs
            if not platform:
                platform = "default"
            if not isinstance(config, dict):
                config = {}

            auth_config = {}

            # Setup user cookies first (higher priority), then global cookies
            await self._setup_user_cookies(auth_config, user_id)
            await self._setup_global_cookies(auth_config)

            # Get user-specific authentication settings
            user_auth_config = await self._get_user_auth_config(platform, user_id)
            if user_auth_config:
                config.update(user_auth_config)

            # Check for stored credentials
            stored_auth = await self._get_stored_auth(platform)
            if stored_auth:
                auth_config.update(stored_auth)

            # Platform-specific authentication setup
            if platform == "instagram":
                auth_config.update(await self._setup_instagram_auth(config))
            elif platform == "twitter":
                auth_config.update(await self._setup_twitter_auth(config))
            elif platform == "reddit":
                auth_config.update(await self._setup_reddit_auth(config))
            elif platform == "pixiv":
                auth_config.update(await self._setup_pixiv_auth(config))
            elif platform == "deviantart":
                auth_config.update(await self._setup_deviantart_auth(config))
            elif platform == "patreon":
                auth_config.update(await self._setup_patreon_auth(config))
            elif platform == "discord":
                auth_config.update(await self._setup_discord_auth(config))
            elif platform == "mastodon":
                auth_config.update(await self._setup_mastodon_auth(config))
            elif platform == "bluesky":
                auth_config.update(await self._setup_bluesky_auth(config))
            elif platform in ["danbooru", "gelbooru", "e621"]:
                auth_config.update(await self._setup_booru_auth(platform, config))
            elif platform in ["gofile", "catbox"]:
                auth_config.update(await self._setup_filehost_auth(platform, config))

            return auth_config

        except Exception as e:
            LOGGER.error(f"Error setting up authentication for {platform}: {e}")
            return {}

    async def _setup_user_cookies(
        self, auth_config: dict, user_id: int | None
    ) -> None:
        """Setup user-specific cookies for gallery-dl (higher priority than global cookies)"""
        try:
            if not user_id:
                return

            # Import user cookies functions
            from bot.modules.users_settings import get_user_cookies_list

            # Get user's cookies
            user_cookies = await get_user_cookies_list(user_id)

            if user_cookies:
                # Try each user cookie until one works
                # For now, use the first available cookie
                # In the future, we could implement cookie rotation/fallback
                first_cookie = user_cookies[0]

                # Check if cookie file exists
                cookie_path = first_cookie["filepath"]
                if await aiopath.exists(cookie_path):
                    auth_config["cookies"] = cookie_path

                    return

                # If file doesn't exist, try to get from database
                try:
                    from bot.helper.ext_utils.db_handler import database

                    db_cookies = await database.get_user_cookies(user_id)
                    if db_cookies:
                        # Use the first available cookie from database
                        first_db_cookie = db_cookies[0]

                        # Create temporary cookie file
                        temp_cookie_path = (
                            f"temp_cookies/{user_id}_{first_db_cookie['number']}.txt"
                        )

                        # Ensure temp directory exists
                        temp_dir = os.path.dirname(temp_cookie_path)
                        os.makedirs(temp_dir, exist_ok=True)

                        # Write cookie data to temporary file
                        async with aiofiles.open(temp_cookie_path, "wb") as f:
                            await f.write(first_db_cookie["data"])

                        auth_config["cookies"] = temp_cookie_path

                        return

                except Exception as e:
                    LOGGER.error(
                        f"Error setting up user cookies from database for user {user_id}: {e}"
                    )

        except Exception as e:
            LOGGER.error(f"Error setting up user cookies for user {user_id}: {e}")

    async def _setup_global_cookies(self, auth_config: dict) -> None:
        """Setup global cookies.txt file for all platforms (only if user cookies not set)"""
        try:
            # Only set global cookies if user cookies weren't already set
            if "cookies" in auth_config:
                return

            # Check if cookies.txt exists in private files
            if DATABASE_AVAILABLE and database:
                cookies_files = await database.get_private_files()
                cookies_file = cookies_files.get("cookies.txt")
            else:
                cookies_file = None
            if cookies_file:
                # Set global cookies file path for gallery-dl
                auth_config["cookies"] = "cookies.txt"

        except Exception as e:
            LOGGER.error(f"Error setting up global cookies: {e}")

    async def _get_user_auth_config(
        self, platform: str, user_id: int | None
    ) -> dict[str, Any]:
        """Get user-specific authentication configuration for platform"""
        try:
            if not user_id:
                return {}

            # Import user data
            from bot.core.config_manager import Config
            from bot.helper.ext_utils.bot_utils import user_data

            user_dict = user_data.get(user_id, {})
            auth_config = {}

            # Platform-specific user settings mapping
            if platform == "reddit":
                auth_config = {
                    "client_id": user_dict.get("GALLERY_DL_REDDIT_CLIENT_ID")
                    or getattr(Config, "GALLERY_DL_REDDIT_CLIENT_ID", ""),
                    "client_secret": user_dict.get("GALLERY_DL_REDDIT_CLIENT_SECRET")
                    or getattr(Config, "GALLERY_DL_REDDIT_CLIENT_SECRET", ""),
                    "username": user_dict.get("GALLERY_DL_REDDIT_USERNAME")
                    or getattr(Config, "GALLERY_DL_REDDIT_USERNAME", ""),
                    "password": user_dict.get("GALLERY_DL_REDDIT_PASSWORD")
                    or getattr(Config, "GALLERY_DL_REDDIT_PASSWORD", ""),
                    "refresh_token": user_dict.get("GALLERY_DL_REDDIT_REFRESH_TOKEN")
                    or getattr(Config, "GALLERY_DL_REDDIT_REFRESH_TOKEN", ""),
                }
            elif platform == "instagram":
                auth_config = {
                    "username": user_dict.get("GALLERY_DL_INSTAGRAM_USERNAME")
                    or getattr(Config, "GALLERY_DL_INSTAGRAM_USERNAME", ""),
                    "password": user_dict.get("GALLERY_DL_INSTAGRAM_PASSWORD")
                    or getattr(Config, "GALLERY_DL_INSTAGRAM_PASSWORD", ""),
                }
            elif platform == "twitter":
                auth_config = {
                    "username": user_dict.get("GALLERY_DL_TWITTER_USERNAME")
                    or getattr(Config, "GALLERY_DL_TWITTER_USERNAME", ""),
                    "password": user_dict.get("GALLERY_DL_TWITTER_PASSWORD")
                    or getattr(Config, "GALLERY_DL_TWITTER_PASSWORD", ""),
                }
            elif platform == "pixiv":
                auth_config = {
                    "username": user_dict.get("GALLERY_DL_PIXIV_USERNAME")
                    or getattr(Config, "GALLERY_DL_PIXIV_USERNAME", ""),
                    "password": user_dict.get("GALLERY_DL_PIXIV_PASSWORD")
                    or getattr(Config, "GALLERY_DL_PIXIV_PASSWORD", ""),
                    "refresh_token": user_dict.get("GALLERY_DL_PIXIV_REFRESH_TOKEN")
                    or getattr(Config, "GALLERY_DL_PIXIV_REFRESH_TOKEN", ""),
                }
            elif platform == "deviantart":
                auth_config = {
                    "client_id": user_dict.get("GALLERY_DL_DEVIANTART_CLIENT_ID")
                    or getattr(Config, "GALLERY_DL_DEVIANTART_CLIENT_ID", ""),
                    "client_secret": user_dict.get(
                        "GALLERY_DL_DEVIANTART_CLIENT_SECRET"
                    )
                    or getattr(Config, "GALLERY_DL_DEVIANTART_CLIENT_SECRET", ""),
                    "username": user_dict.get("GALLERY_DL_DEVIANTART_USERNAME")
                    or getattr(Config, "GALLERY_DL_DEVIANTART_USERNAME", ""),
                    "password": user_dict.get("GALLERY_DL_DEVIANTART_PASSWORD")
                    or getattr(Config, "GALLERY_DL_DEVIANTART_PASSWORD", ""),
                }
            elif platform == "discord":
                auth_config = {
                    "token": user_dict.get("GALLERY_DL_DISCORD_TOKEN")
                    or getattr(Config, "GALLERY_DL_DISCORD_TOKEN", ""),
                }

            # Filter out empty values
            auth_config = {k: v for k, v in auth_config.items() if v}

            if auth_config:
                LOGGER.info(
                    f"Using user authentication settings for {platform} (user {user_id})"
                )

            return auth_config

        except Exception as e:
            LOGGER.error(
                f"Error getting user auth config for {platform} (user {user_id}): {e}"
            )
            return {}

    async def _setup_instagram_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup Instagram authentication (cookies/session)"""
        auth_config = {
            "cookies": config.get("cookies", {}),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
            "session-file": config.get("session_file", ""),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _setup_twitter_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup Twitter/X authentication (OAuth/cookies)"""
        auth_config = {
            "cookies": config.get("cookies", {}),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
            "api-key": config.get("api_key", ""),
            "api-secret": config.get("api_secret", ""),
            "access-token": config.get("access_token", ""),
            "access-token-secret": config.get("access_token_secret", ""),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _setup_reddit_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup Reddit authentication (OAuth)"""
        auth_config = {
            "client-id": config.get("client_id", ""),
            "client-secret": config.get("client_secret", ""),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
            "user-agent": config.get("user_agent", "gallery-dl"),
            "refresh-token": config.get("refresh_token", ""),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _setup_pixiv_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup Pixiv authentication (username/password)"""
        auth_config = {
            "username": config.get("username", ""),
            "password": config.get("password", ""),
            "refresh-token": config.get("refresh_token", ""),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _setup_deviantart_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup DeviantArt authentication (OAuth)"""
        auth_config = {
            "client-id": config.get("client_id", ""),
            "client-secret": config.get("client_secret", ""),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
            "refresh-token": config.get("refresh_token", ""),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _setup_patreon_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup Patreon authentication (cookies/session)"""
        auth_config = {
            "cookies": config.get("cookies", {}),
            "session-key": config.get("session_key", ""),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _setup_discord_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup Discord authentication (token)"""
        return {
            "token": config.get("token", ""),
        }

    async def _setup_mastodon_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup Mastodon authentication (OAuth)"""
        auth_config = {
            "access-token": config.get("access_token", ""),
            "client-id": config.get("client_id", ""),
            "client-secret": config.get("client_secret", ""),
            "instance": config.get("instance", "mastodon.social"),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _setup_bluesky_auth(self, config: dict[str, Any]) -> dict[str, Any]:
        """Setup Bluesky authentication (username/password)"""
        return {
            "username": config.get("username", ""),
            "password": config.get("password", ""),
        }

    async def _setup_booru_auth(
        self, platform: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Setup Booru site authentication (API key/user ID)"""
        auth_config = {
            "api-key": config.get("api_key", ""),
            "user-id": config.get("user_id", ""),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _setup_filehost_auth(
        self, platform: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Setup file host authentication (API token)"""
        auth_config = {
            "api-token": config.get("api_token", ""),
            "api-key": config.get("api_key", ""),
        }

        # Filter out empty values
        return {k: v for k, v in auth_config.items() if v}

    async def _get_stored_auth(self, platform: str) -> dict[str, Any] | None:
        """Get stored authentication for platform"""
        try:
            auth_file = os.path.join(
                os.path.expanduser("~"), ".gallery_dl_auth", f"{platform}_auth.json"
            )
            if os.path.exists(auth_file):
                async with aiofiles.open(auth_file, "r") as f:
                    content = await f.read()
                    return json.loads(content)
            return None

        except Exception as e:
            LOGGER.error(f"Error loading stored auth for {platform}: {e}")
            return None

    async def store_auth(self, platform: str, auth_data: dict[str, Any]):
        """Store authentication data for platform"""
        try:
            auth_dir = os.path.join(os.path.expanduser("~"), ".gallery_dl_auth")
            os.makedirs(auth_dir, exist_ok=True)

            auth_file = os.path.join(auth_dir, f"{platform}_auth.json")
            async with aiofiles.open(auth_file, "w") as f:
                await f.write(json.dumps(auth_data, indent=2))

        except Exception as e:
            LOGGER.error(f"Error storing auth for {platform}: {e}")

    async def validate_auth(
        self, platform: str, auth_config: dict[str, Any]
    ) -> bool:
        """Validate authentication for platform"""
        try:
            # Platform-specific validation
            if platform == "instagram":
                return await self._validate_instagram_auth(auth_config)
            if platform == "twitter":
                return await self._validate_twitter_auth(auth_config)
            if platform == "reddit":
                return await self._validate_reddit_auth(auth_config)
            if platform == "pixiv":
                return await self._validate_pixiv_auth(auth_config)
            if platform == "discord":
                return await self._validate_discord_auth(auth_config)

            # Generic validation
            return bool(
                auth_config.get("username")
                or auth_config.get("api_key")
                or auth_config.get("token")
            )

        except Exception as e:
            LOGGER.error(f"Error validating auth for {platform}: {e}")
            return False

    async def _validate_instagram_auth(self, auth_config: dict[str, Any]) -> bool:
        """Validate Instagram authentication"""
        return bool(
            auth_config.get("cookies")
            or (auth_config.get("username") and auth_config.get("password"))
        )

    async def _validate_twitter_auth(self, auth_config: dict[str, Any]) -> bool:
        """Validate Twitter authentication"""
        return bool(
            auth_config.get("cookies")
            or (auth_config.get("api_key") and auth_config.get("api_secret"))
            or (auth_config.get("username") and auth_config.get("password"))
        )

    async def _validate_reddit_auth(self, auth_config: dict[str, Any]) -> bool:
        """Validate Reddit authentication"""
        return bool(
            auth_config.get("refresh_token")
            or (auth_config.get("client_id") and auth_config.get("client_secret"))
        )

    async def _validate_pixiv_auth(self, auth_config: dict[str, Any]) -> bool:
        """Validate Pixiv authentication"""
        return bool(
            auth_config.get("refresh_token")
            or (auth_config.get("username") and auth_config.get("password"))
        )

    async def _validate_discord_auth(self, auth_config: dict[str, Any]) -> bool:
        """Validate Discord authentication"""
        return bool(auth_config.get("token"))

    async def refresh_token(
        self, platform: str, auth_config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Refresh authentication token for platform"""
        try:
            if platform == "reddit":
                return await self._refresh_reddit_token(auth_config)
            if platform == "pixiv":
                return await self._refresh_pixiv_token(auth_config)
            if platform == "deviantart":
                return await self._refresh_deviantart_token(auth_config)

            return None

        except Exception as e:
            LOGGER.error(f"Error refreshing token for {platform}: {e}")
            return None

    async def _refresh_reddit_token(
        self, auth_config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Refresh Reddit OAuth token"""
        # Implementation would make API call to refresh token
        return None

    async def _refresh_pixiv_token(
        self, auth_config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Refresh Pixiv token"""
        # Implementation would make API call to refresh token
        return None

    async def _refresh_deviantart_token(
        self, auth_config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Refresh DeviantArt OAuth token"""
        # Implementation would make API call to refresh token
        return None

    async def get_auth_instructions(self, platform: str) -> str:
        """Get authentication instructions for platform"""
        instructions = {
            "instagram": "Set cookies from browser or provide username/password",
            "twitter": "Provide API keys or cookies from browser session",
            "reddit": "Set up OAuth app and provide client credentials",
            "pixiv": "Provide username/password or refresh token",
            "deviantart": "Set up OAuth app and provide client credentials",
            "discord": "Provide bot token or user token",
            "patreon": "Provide session cookies from browser",
            "mastodon": "Set up OAuth app on your instance",
            "bluesky": "Provide username/password for your account",
            "danbooru": "Provide API key and user ID from account settings",
            "gelbooru": "Provide API key and user ID (optional)",
            "e621": "Provide username and API key from account settings",
        }

        return instructions.get(
            platform, "Check platform documentation for authentication requirements"
        )

    def get_supported_auth_methods(self, platform: str) -> list[str]:
        """Get supported authentication methods for platform"""
        methods = {
            "instagram": ["cookies", "username_password"],
            "twitter": ["oauth", "cookies", "username_password"],
            "reddit": ["oauth", "username_password"],
            "pixiv": ["username_password", "refresh_token"],
            "deviantart": ["oauth", "username_password"],
            "discord": ["token"],
            "patreon": ["cookies"],
            "mastodon": ["oauth"],
            "bluesky": ["username_password"],
            "danbooru": ["api_key"],
            "gelbooru": ["api_key"],
            "e621": ["api_key"],
        }

        return methods.get(platform, ["username_password"])

    async def cleanup(self):
        """Cleanup authentication manager"""
        try:
            # Clear sensitive data from memory
            self.auth_cache.clear()
            self.session_cache.clear()
            self.oauth_tokens.clear()
            self.api_keys.clear()
            self.cookies.clear()

        except Exception as e:
            LOGGER.error(f"Error during auth manager cleanup: {e}")
