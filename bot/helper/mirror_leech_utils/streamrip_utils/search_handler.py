import asyncio
import contextlib
import hashlib
import time as time_module
from functools import partial
from time import time
from typing import Any

from pyrogram.filters import regex, user
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

try:
    from streamrip.client import (
        DeezerClient,
        QobuzClient,
        SoundcloudClient,
        TidalClient,
    )

    STREAMRIP_AVAILABLE = True
except ImportError:
    STREAMRIP_AVAILABLE = False

    # Create dummy classes to prevent import errors
    class QobuzClient:
        pass

    class TidalClient:
        pass

    class DeezerClient:
        pass

    class SoundcloudClient:
        pass


class StreamripSearchHandler:
    """Ultra-optimized multi-platform search handler for streamrip with minimal complexity"""

    # Class-level constants for O(1) lookups and memory efficiency
    PLATFORM_SEARCH_TYPES = {
        "qobuz": ("track", "album", "artist", "playlist"),
        "deezer": ("track", "album", "artist", "playlist"),
        "tidal": ("track", "album", "artist", "playlist"),
        "soundcloud": ("track",),  # SoundCloud mainly supports tracks
    }

    URL_TEMPLATES = {
        "qobuz": {
            "track": "https://www.qobuz.com/track/{}",
            "album": "https://www.qobuz.com/album/{}",
            "artist": "https://www.qobuz.com/artist/{}",
            "playlist": "https://www.qobuz.com/playlist/{}",
        },
        "tidal": {
            "track": "https://listen.tidal.com/track/{}",
            "album": "https://listen.tidal.com/album/{}",
            "artist": "https://listen.tidal.com/artist/{}",
            "playlist": "https://listen.tidal.com/playlist/{}",
        },
        "deezer": {
            "track": "https://www.deezer.com/track/{}",
            "album": "https://www.deezer.com/album/{}",
            "artist": "https://www.deezer.com/artist/{}",
            "playlist": "https://www.deezer.com/playlist/{}",
        },
        "soundcloud": {
            "track": "https://soundcloud.com/user/{}",  # Note: SoundCloud uses permalink_url in practice
            "playlist": "https://soundcloud.com/user/sets/{}",
        },
    }

    # Pre-computed platform emojis and quality info for O(1) access
    PLATFORM_EMOJIS = {
        "qobuz": "🟦",
        "tidal": "⚫",
        "deezer": "🟣",
        "soundcloud": "🟠",
    }
    TYPE_EMOJIS = {"track": "🎵", "album": "💿", "playlist": "📋", "artist": "👤"}
    QUALITY_MAP = {
        "qobuz": "Hi-Res FLAC",
        "tidal": "MQA/Hi-Res",
        "deezer": "CD Quality",
        "soundcloud": "MP3 320kbps",
    }

    # Client class mapping for efficient initialization
    CLIENT_CLASSES = {
        "qobuz": QobuzClient,
        "tidal": TidalClient,
        "deezer": DeezerClient,
        "soundcloud": SoundcloudClient,
    }

    __slots__ = (
        "_cached_all_results",
        "_config",
        "_enabled_platforms",
        "_reply_to",
        "_time",
        "_timeout",
        "clients",
        "current_page",
        "event",
        "failed_platforms",
        "initial_platforms",
        "listener",
        "media_type_filter",
        "platform",
        "query",
        "result_limit",
        "results_per_page",
        "search_results",
        "selected_result",
    )

    def __init__(
        self,
        listener,
        query: str,
        platform: str | None = None,
        media_type_filter: str | None = None,
        result_limit: int = 200,
    ):
        self.listener = listener
        self.query = query
        self.platform = platform
        self.media_type_filter = media_type_filter
        self.result_limit = result_limit
        self.search_results = {}
        self.current_page = 0
        self.results_per_page = 5
        self._reply_to = None
        self._time = time()
        self._timeout = 300  # 5 minutes for search
        self.event = asyncio.Event()
        self.selected_result = None
        self.clients = {}
        self.initial_platforms = []  # Track initial platforms for comparison
        self.failed_platforms = set()  # Track platforms that failed authentication
        self._cached_all_results = None  # Cache flattened results for O(1) access

    async def initialize_clients(self):
        """Initialize platform clients with lazy loading and reduced resource usage"""
        if not STREAMRIP_AVAILABLE:
            return False

        try:
            # Ensure streamrip is initialized first
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                ensure_streamrip_initialized,
                streamrip_config,
            )

            if not await ensure_streamrip_initialized():
                return False

            config = streamrip_config.get_config()
            if not config:
                return False

            platform_status = streamrip_config.get_platform_status()

            # Check if any platforms are available
            enabled_platforms = [
                p for p, enabled in platform_status.items() if enabled
            ]
            if not enabled_platforms:
                return False

            # Use lazy initialization - only store config and platform info
            # Actual client creation will happen when needed to reduce startup overhead
            self._config = config
            self._enabled_platforms = enabled_platforms

            # Initialize clients efficiently without delays to reduce CPU overhead
            initialized_count = 0
            for platform in enabled_platforms:
                if platform in self.CLIENT_CLASSES:
                    try:
                        # Remove sleep delays to reduce CPU overhead and improve performance
                        self.clients[platform] = self.CLIENT_CLASSES[platform](
                            config
                        )
                        initialized_count += 1
                    except Exception as e:
                        LOGGER.error(
                            f"Failed to initialize {platform.title()} client: {e}"
                        )

            # Store initial platform list for comparison later
            self.initial_platforms = list(self.clients.keys())

            if initialized_count > 0:
                LOGGER.info(
                    f"Successfully initialized {initialized_count}/{len(enabled_platforms)} streamrip clients"
                )

            return len(self.clients) > 0

        except Exception as e:
            LOGGER.error(f"Failed to initialize search clients: {e}")
            return False

    async def _cleanup_clients(self):
        """Cleanup streamrip clients to prevent unclosed sessions"""
        try:
            for platform, client in self.clients.items():
                try:
                    # Try to properly close aiohttp sessions in streamrip clients with timeout
                    cleanup_tasks = []

                    if hasattr(client, "_session") and client._session:
                        if not client._session.closed:
                            cleanup_tasks.append(client._session.close())
                    elif hasattr(client, "session") and client.session:
                        if not client.session.closed:
                            cleanup_tasks.append(client.session.close())
                    elif hasattr(client, "_http_session") and client._http_session:
                        if not client._http_session.closed:
                            cleanup_tasks.append(client._http_session.close())

                    # Also try to close any connector
                    if hasattr(client, "_connector") and client._connector:
                        cleanup_tasks.append(client._connector.close())
                    elif hasattr(client, "connector") and client.connector:
                        cleanup_tasks.append(client.connector.close())

                    # Execute cleanup tasks with timeout
                    if cleanup_tasks:
                        await asyncio.wait_for(
                            asyncio.gather(*cleanup_tasks, return_exceptions=True),
                            timeout=5.0,
                        )

                except TimeoutError:
                    LOGGER.warning(
                        f"Cleanup timeout for {platform} client - forcing cleanup"
                    )
                except Exception as cleanup_error:
                    LOGGER.warning(
                        f"Failed to cleanup {platform} client: {cleanup_error}"
                    )

            # Clear clients dict
            self.clients.clear()

            # Force garbage collection to help with cleanup
            import gc

            gc.collect()

        except Exception as e:
            LOGGER.error(f"Error during client cleanup: {e}")

    def _log_search_summary(self):
        """Log summary of search results and platform status"""
        try:
            initial_platforms = getattr(self, "initial_platforms", [])
            failed_platforms = getattr(self, "failed_platforms", set())
            [p for p in initial_platforms if p not in failed_platforms]

            # Only log if there are failures or no results
            total_results = sum(
                len(results) for results in self.search_results.values()
            )

            if failed_platforms:
                LOGGER.warning(
                    f"{len(failed_platforms)} platforms failed: {', '.join(failed_platforms)}"
                )

            if total_results == 0:
                LOGGER.warning("No search results found on any platform")

        except Exception as e:
            LOGGER.error(f"Error logging search summary: {e}")

    def _extract_results_from_containers(
        self, search_response, platform: str, search_type: str
    ):
        """Extract actual results from platform-specific response containers"""
        actual_results = []

        try:
            if platform == "qobuz":
                # Qobuz: {'query': '...', 'tracks': {'items': [...]}}
                for result_container in search_response:
                    if search_type + "s" in result_container:
                        items = result_container[search_type + "s"]
                        if isinstance(items, dict) and "items" in items:
                            actual_results.extend(items["items"])
                        elif isinstance(items, list):
                            actual_results.extend(items)
            elif platform == "deezer":
                # Deezer: {'data': [...], 'total': ..., 'next': ...}
                for result_container in search_response:
                    if "data" in result_container:
                        actual_results.extend(result_container["data"])
            elif platform == "soundcloud":
                # SoundCloud: {'collection': [...], 'total_results': ..., ...}
                for result_container in search_response:
                    if "collection" in result_container:
                        actual_results.extend(result_container["collection"])
            elif platform == "tidal":
                # Tidal: {'limit': 50, 'offset': 0, 'totalNumberOfItems': 123, 'items': [...]}
                for result_container in search_response:
                    if (
                        isinstance(result_container, dict)
                        and "items" in result_container
                    ):
                        actual_results.extend(result_container["items"])
                    elif isinstance(result_container, list):
                        actual_results.extend(result_container)
                    else:
                        # Fallback: treat as single item
                        actual_results.append(result_container)
            # Fallback: assume direct list
            elif isinstance(search_response, list):
                actual_results = search_response
            else:
                actual_results = [search_response]

        except Exception as e:
            LOGGER.warning(
                f"Failed to extract results from {platform} containers: {e}"
            )
            # Fallback to treating response as direct results
            if isinstance(search_response, list):
                actual_results = search_response
            else:
                actual_results = [search_response]

        return actual_results

    async def search(self) -> dict[str, Any] | None:
        """Perform multi-platform search"""
        try:
            if not await self.initialize_clients():
                await send_message(
                    self.listener.message,
                    f"{self.listener.tag} ❌ <b>No streamrip platforms are configured!</b>\n\n"
                    f"🎵 <b>Available platforms:</b>\n"
                    f"🟦 <code>Qobuz</code> - Hi-Res FLAC\n"
                    f"⚫ <code>Tidal</code> - MQA/Hi-Res\n"
                    f"🟣 <code>Deezer</code> - CD Quality\n"
                    f"🟠 <code>SoundCloud</code> - MP3 320kbps\n\n"
                    f"💡 <i>Configure credentials in bot settings to enable search.</i>",
                )
                return None

            # Show beautiful searching message
            platform_info = ""
            if self.platform:
                platform_emoji = {
                    "qobuz": "🟦",
                    "tidal": "⚫",
                    "deezer": "🟣",
                    "soundcloud": "🟠",
                }.get(self.platform, "🔵")
                platform_info = f"\n🎯 <b>Platform:</b> {platform_emoji} <code>{self.platform.title()}</code>"
            else:
                platform_count = len(self.clients)
                platform_info = (
                    f"\n🎯 <b>Platforms:</b> <code>{platform_count}</code> platforms"
                )

            search_msg = await send_message(
                self.listener.message,
                f"🔍 <b>Streamrip Search</b>\n\n"
                f"🎵 <b>Query:</b> <code>{self.query}</code>{platform_info}\n\n"
                f"⏳ <i>Searching across music platforms...</i>\n"
                f"🎶 <i>This may take a few seconds</i>",
            )

            # Perform search on all platforms or specific platform
            if self.platform and self.platform in self.clients:
                await self._search_platform(self.platform)
            else:
                # Search all available platforms
                search_tasks = []
                for platform_name in self.clients:
                    search_tasks.append(self._search_platform(platform_name))

                await asyncio.gather(*search_tasks, return_exceptions=True)

            # Delete searching message
            await delete_message(search_msg)

            # Log search completion summary
            self._log_search_summary()

            # Check if we have results
            total_results = sum(
                len(results) for results in self.search_results.values()
            )

            if total_results == 0:
                # Check if any platforms were disabled
                failed_platforms = getattr(self, "failed_platforms", set())

                error_msg = f"{self.listener.tag} ❌ <b>No results found for:</b> <code>{self.query}</code>"
                if failed_platforms:
                    error_msg += "\n\n⚠️ <b>Some platforms were disabled due to authentication issues:</b>\n"
                    error_msg += f"<pre>{', '.join(failed_platforms)}</pre>\n"
                    error_msg += "💡 <i>Check your credentials in bot settings and try again.</i>"

                no_results_msg = await send_message(self.listener.message, error_msg)
                asyncio.create_task(auto_delete_message(no_results_msg, time=300))
                return None

            # Show search results
            await self._show_search_results()

            # Start event handler
            asyncio.create_task(self._event_handler())

            # Wait for selection
            await self.event.wait()

            return self.selected_result

        except Exception as e:
            LOGGER.error(f"Search error: {e}")
            await delete_message(search_msg)
            error_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} ❌ <b>Search failed:</b>\n\n"
                f"🔍 <i>Query:</i> <code>{self.query}</code>\n"
                f"⚠️ <i>Error:</i> <pre>{e!s}</pre>\n"
                f"💡 <i>Try again or check platform availability.</i>",
            )
            asyncio.create_task(auto_delete_message(error_msg, time=300))
            return None
        finally:
            # Always cleanup clients to prevent unclosed sessions
            await self._cleanup_clients()

    async def _perform_search(self):
        """Perform search without UI - used for auto-first functionality"""
        if not await self.initialize_clients():
            return

        # Perform search on all platforms or specific platform
        if self.platform and self.platform in self.clients:
            await self._search_platform(self.platform)
        else:
            # Search all available platforms
            search_tasks = []
            for platform_name in self.clients:
                search_tasks.append(self._search_platform(platform_name))

            await asyncio.gather(*search_tasks, return_exceptions=True)

    async def _search_platform(self, platform: str):
        """Search on a specific platform"""
        try:
            client = self.clients[platform]

            # Perform search (this is a simplified example - actual implementation depends on streamrip API)
            # Note: The actual search API may differ, this is based on typical patterns
            results = await self._perform_platform_search(client, platform)

            if results:
                # Apply result limit
                limited_results = results[: self.result_limit]
                self.search_results[platform] = limited_results

        except Exception as e:
            LOGGER.error(f"Search failed on {platform}: {e}")

    async def _perform_platform_search(
        self, client, platform: str
    ) -> list[dict[str, Any]]:
        """Perform actual search on platform"""
        results = []

        try:
            # Login to client first with better session management
            if hasattr(client, "login"):
                try:
                    # Check if session is still valid before login
                    if (
                        hasattr(client, "session")
                        and client.session
                        and client.session.closed
                    ):
                        LOGGER.warning(
                            f"{platform.title()} session is closed, recreating client"
                        )
                        # Recreate client if session is closed
                        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                            streamrip_config,
                        )

                        config = streamrip_config.get_config()
                        client = self.CLIENT_CLASSES[platform](config)
                        self.clients[platform] = client

                    await client.login()
                except Exception as auth_error:
                    # Handle authentication failures consistently for all platforms
                    LOGGER.warning(
                        f"{platform.title()} authentication failed: {str(auth_error)[:100]}"
                    )

                    # Mark platform as failed but don't remove from clients during search
                    # (we'll track failed platforms separately)
                    if not hasattr(self, "failed_platforms"):
                        self.failed_platforms = set()
                    self.failed_platforms.add(platform)

                    # Return empty results for this platform, but don't stop the search
                    return results

            # Perform search using correct API methods
            if hasattr(client, "search"):
                # Determine search types based on media_type_filter using class constants
                if self.media_type_filter:
                    # Use only the specified media type
                    search_types = [self.media_type_filter]
                else:
                    # Use pre-defined platform search types for better performance
                    search_types = list(
                        self.PLATFORM_SEARCH_TYPES.get(platform, ("track",))
                    )

                for search_type in search_types:
                    try:
                        # Correct API signature: search(media_type, query, limit)
                        search_response = await client.search(
                            search_type,  # Use singular forms for all platforms
                            self.query,
                            limit=self.result_limit,
                        )

                        # Extract actual results from platform-specific containers
                        if search_response:
                            actual_results = self._extract_results_from_containers(
                                search_response, platform, search_type
                            )

                            # Process results in batches to reduce CPU overhead
                            batch_size = 10  # Process 10 items at a time
                            for i in range(0, len(actual_results), batch_size):
                                batch = actual_results[i : i + batch_size]
                                for item in batch:
                                    # Extract metadata based on platform and type
                                    result = await self._extract_search_result(
                                        item, platform, search_type
                                    )
                                    if result:
                                        results.append(result)

                                # Yield control to prevent CPU blocking
                                if i + batch_size < len(actual_results):
                                    await asyncio.sleep(0)  # Yield to event loop

                    except Exception as search_error:
                        error_msg = str(search_error)

                        # Handle specific connection errors
                        if (
                            "Connector is closed" in error_msg
                            or "Session is closed" in error_msg
                        ):
                            LOGGER.warning(
                                f"Connection closed for {platform}, recreating client"
                            )
                            try:
                                # Recreate client and retry once
                                from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                                    streamrip_config,
                                )

                                config = streamrip_config.get_config()
                                client = self.CLIENT_CLASSES[platform](config)
                                self.clients[platform] = client

                                # Login and retry search
                                if hasattr(client, "login"):
                                    await client.login()

                                # Retry the search once
                                search_response = await client.search(
                                    search_type,
                                    self.query,
                                    limit=self.result_limit,
                                )

                                if search_response:
                                    actual_results = (
                                        self._extract_results_from_containers(
                                            search_response, platform, search_type
                                        )
                                    )

                                    # Process retry results in batches to reduce CPU overhead
                                    batch_size = 10  # Process 10 items at a time
                                    for i in range(
                                        0, len(actual_results), batch_size
                                    ):
                                        batch = actual_results[i : i + batch_size]
                                        for item in batch:
                                            result = (
                                                await self._extract_search_result(
                                                    item, platform, search_type
                                                )
                                            )
                                            if result:
                                                results.append(result)

                                        # Yield control to prevent CPU blocking
                                        if i + batch_size < len(actual_results):
                                            await asyncio.sleep(
                                                0
                                            )  # Yield to event loop

                                LOGGER.info(f"Recovered {platform} connection")
                                continue

                            except Exception as retry_error:
                                LOGGER.error(
                                    f"Failed to recover {platform} connection: {str(retry_error)[:100]}"
                                )

                        LOGGER.warning(
                            f"Search '{search_type}' failed on {platform}: {str(search_error)[:100]}"
                        )
                        continue

            else:
                LOGGER.warning(
                    f"Platform {platform} does not support search functionality"
                )

        except Exception as e:
            LOGGER.error(f"Platform search error for {platform}: {str(e)[:100]}")
            if "authentication" in str(e).lower() or "login" in str(e).lower():
                LOGGER.warning(
                    f"{platform.title()} authentication required - check credentials"
                )

        return results

    async def _extract_search_result(
        self, item, platform: str, search_type: str
    ) -> dict[str, Any] | None:
        """Extract search result metadata with comprehensive thumbnail and metadata extraction"""
        try:
            result = {
                "platform": platform,
                "type": search_type,
                "title": "Unknown",
                "artist": "Unknown Artist",
                "album": "",
                "duration": 0,
                "url": "",
                "id": "",
                "quality": "Unknown",
                "cover_url": "",
                "thumbnail_url": "",  # Add thumbnail_url for compatibility
            }

            # Extract metadata from dict structure (all platforms return dicts)
            if isinstance(item, dict):
                # Extract title
                result["title"] = item.get("title", item.get("name", "Unknown"))

                # Platform-specific artist extraction
                if platform == "qobuz":
                    if "performer" in item:
                        if isinstance(item["performer"], dict):
                            result["artist"] = item["performer"].get(
                                "name", str(item["performer"])
                            )
                        else:
                            result["artist"] = str(item["performer"])
                    elif "artist" in item:
                        if isinstance(item["artist"], dict):
                            result["artist"] = item["artist"].get(
                                "name", str(item["artist"])
                            )
                        else:
                            result["artist"] = str(item["artist"])
                elif platform == "deezer":
                    # Deezer can have multiple artist field formats
                    if "artist" in item:
                        if isinstance(item["artist"], dict):
                            result["artist"] = item["artist"].get(
                                "name", str(item["artist"])
                            )
                        else:
                            result["artist"] = str(item["artist"])
                    elif item.get("artists"):
                        if isinstance(item["artists"], list) and item["artists"]:
                            first_artist = item["artists"][0]
                            if isinstance(first_artist, dict):
                                result["artist"] = first_artist.get(
                                    "name", str(first_artist)
                                )
                            else:
                                result["artist"] = str(first_artist)
                        elif isinstance(item["artists"], dict):
                            result["artist"] = item["artists"].get(
                                "name", str(item["artists"])
                            )
                    elif item.get("contributors"):
                        # Deezer sometimes uses 'contributors' field
                        if (
                            isinstance(item["contributors"], list)
                            and item["contributors"]
                        ):
                            first_contributor = item["contributors"][0]
                            if isinstance(first_contributor, dict):
                                result["artist"] = first_contributor.get(
                                    "name", str(first_contributor)
                                )
                            else:
                                result["artist"] = str(first_contributor)
                elif platform == "soundcloud":
                    # Enhanced SoundCloud metadata extraction
                    # Try multiple SoundCloud artist field patterns with more robust handling
                    artist_found = False

                    # Method 1: Try user object (most common)
                    if "user" in item and not artist_found:
                        user_obj = item["user"]

                        if isinstance(user_obj, dict):
                            # Try different user fields in order of preference
                            for field in [
                                "username",
                                "display_name",
                                "full_name",
                                "name",
                            ]:
                                if user_obj.get(field):
                                    result["artist"] = str(user_obj[field]).strip()
                                    artist_found = True
                                    break

                            # If no specific field found, try to extract from user object
                            if not artist_found:
                                result["artist"] = str(user_obj)
                                artist_found = True
                        elif isinstance(user_obj, str) and user_obj.strip():
                            result["artist"] = str(user_obj).strip()
                            artist_found = True

                    # Method 2: Try uploader field
                    if "uploader" in item and not artist_found:
                        uploader = item["uploader"]
                        if uploader and str(uploader).strip():
                            result["artist"] = str(uploader).strip()
                            artist_found = True

                    # Method 3: Try publisher metadata
                    if "publisher_metadata" in item and not artist_found:
                        pub_meta = item["publisher_metadata"]

                        if isinstance(pub_meta, dict):
                            for field in [
                                "artist",
                                "performer",
                                "creator",
                                "author",
                            ]:
                                if pub_meta.get(field):
                                    result["artist"] = str(pub_meta[field]).strip()
                                    artist_found = True
                                    break

                    # Method 4: Try other common fields
                    if not artist_found:
                        for field in [
                            "artist",
                            "performer",
                            "creator",
                            "author",
                            "channel",
                        ]:
                            if item.get(field):
                                field_value = item[field]
                                if (
                                    isinstance(field_value, dict)
                                    and "name" in field_value
                                ):
                                    result["artist"] = str(
                                        field_value["name"]
                                    ).strip()
                                elif (
                                    isinstance(field_value, str)
                                    and field_value.strip()
                                ):
                                    result["artist"] = str(field_value).strip()
                                else:
                                    continue
                                artist_found = True
                                break

                    if not artist_found:
                        pass  # No artist found, continue with default
                elif platform == "tidal":
                    if "artist" in item:
                        if isinstance(item["artist"], dict):
                            result["artist"] = item["artist"].get(
                                "name", str(item["artist"])
                            )
                        else:
                            result["artist"] = str(item["artist"])
                    elif item.get("artists"):
                        if isinstance(item["artists"], list) and item["artists"]:
                            first_artist = item["artists"][0]
                            if isinstance(first_artist, dict):
                                result["artist"] = first_artist.get(
                                    "name", str(first_artist)
                                )
                            else:
                                result["artist"] = str(first_artist)

                # Enhanced generic fallbacks for artist
                if result["artist"] == "Unknown Artist":
                    # Try different artist field variations
                    for artist_field in [
                        "artists",
                        "performer",
                        "artist",
                        "albumartist",
                        "composer",
                    ]:
                        if item.get(artist_field):
                            field_value = item[artist_field]
                            if isinstance(field_value, list) and field_value:
                                first_item = field_value[0]
                                if isinstance(first_item, dict):
                                    result["artist"] = first_item.get(
                                        "name", str(first_item)
                                    )
                                else:
                                    result["artist"] = str(first_item)
                                break
                            if isinstance(field_value, dict):
                                result["artist"] = field_value.get(
                                    "name", str(field_value)
                                )
                                break
                            if isinstance(field_value, str):
                                result["artist"] = field_value
                                break

                # Special handling for artist and playlist search types
                if search_type in ["artist", "playlist"]:
                    if search_type == "artist":
                        # For artist searches, the title IS the artist name
                        result["artist"] = result["title"]
                    elif search_type == "playlist":
                        # For playlist searches, try to get the creator/owner
                        if "owner" in item:
                            if isinstance(item["owner"], dict):
                                result["artist"] = item["owner"].get(
                                    "name", item["owner"].get("username", "Unknown")
                                )
                            else:
                                result["artist"] = str(item["owner"])
                        elif "user" in item:
                            if isinstance(item["user"], dict):
                                result["artist"] = item["user"].get(
                                    "name", item["user"].get("username", "Unknown")
                                )
                            else:
                                result["artist"] = str(item["user"])
                        elif "creator" in item:
                            if isinstance(item["creator"], dict):
                                result["artist"] = item["creator"].get(
                                    "name",
                                    item["creator"].get("username", "Unknown"),
                                )
                            else:
                                result["artist"] = str(item["creator"])

                # Extract album with platform-specific handling
                if "album" in item:
                    if isinstance(item["album"], dict):
                        result["album"] = item["album"].get(
                            "title", item["album"].get("name", "")
                        )
                    else:
                        result["album"] = str(item["album"])
                elif platform == "soundcloud":
                    # SoundCloud doesn't typically have albums, but check for playlist or publisher info
                    if "publisher_metadata" in item and isinstance(
                        item["publisher_metadata"], dict
                    ):
                        album_title = item["publisher_metadata"].get("album_title")
                        if album_title:
                            result["album"] = str(album_title)
                    elif "playlist" in item and isinstance(item["playlist"], dict):
                        playlist_title = item["playlist"].get("title")
                        if playlist_title:
                            result["album"] = str(playlist_title)

                # Extract duration with platform-specific handling
                if "duration" in item:
                    duration = item["duration"]
                    if isinstance(duration, int | float):
                        # SoundCloud duration is in milliseconds, others in seconds
                        if (
                            platform == "soundcloud" and duration > 10000
                        ):  # Likely milliseconds
                            result["duration"] = int(duration / 1000)
                        else:
                            result["duration"] = int(duration)
                    else:
                        result["duration"] = 0
                else:
                    result["duration"] = 0

                # Extract ID
                result["id"] = str(item.get("id", ""))

                # Extract cover/thumbnail URLs with platform-specific logic
                cover_url = self._extract_cover_url(item, platform, search_type)
                if cover_url:
                    result["cover_url"] = cover_url
                    result["thumbnail_url"] = cover_url  # For compatibility

            else:
                # Fallback for object attributes (shouldn't happen with current API)
                result["title"] = getattr(
                    item, "title", getattr(item, "name", "Unknown")
                )
                if hasattr(item, "artist"):
                    if hasattr(item.artist, "name"):
                        result["artist"] = item.artist.name
                    else:
                        result["artist"] = str(item.artist)

            # Generate URL based on platform and ID
            if result["id"]:
                # For SoundCloud, use permalink_url if available, otherwise generate URL
                if platform == "soundcloud" and "permalink_url" in item:
                    result["url"] = str(item["permalink_url"])
                else:
                    result["url"] = self._generate_platform_url(
                        platform, search_type, result["id"]
                    )

            # Set quality info
            quality_map = {
                "qobuz": "Hi-Res FLAC",
                "tidal": "MQA/Hi-Res",
                "deezer": "CD Quality",
                "soundcloud": "MP3 320kbps",
            }
            result["quality"] = quality_map.get(platform, "Unknown")

            return result

        except Exception as e:
            LOGGER.warning(
                f"Failed to extract search result from {platform}: {str(e)[:100]}"
            )
            return None

    def _extract_cover_url(self, item: dict, platform: str, search_type: str) -> str:
        """Extract cover/thumbnail URL from API response with platform-specific logic"""
        try:
            cover_url = ""

            if platform == "qobuz":
                # Qobuz cover URL patterns
                if "image" in item:
                    if isinstance(item["image"], dict):
                        # Try different size variants (prefer larger sizes)
                        for size in ["large", "medium", "small", "thumbnail"]:
                            if size in item["image"] and item["image"][size]:
                                cover_url = item["image"][size]
                                break
                        # Fallback to any available image URL
                        if not cover_url:
                            for value in item["image"].values():
                                if isinstance(value, str) and value.startswith(
                                    "http"
                                ):
                                    cover_url = value
                                    break
                    elif isinstance(item["image"], str):
                        cover_url = item["image"]

                # Alternative Qobuz fields
                if not cover_url:
                    for field in ["cover", "cover_url", "artwork_url", "picture"]:
                        if item.get(field):
                            cover_url = str(item[field])
                            break

                # For albums, try album image
                if (
                    not cover_url
                    and "album" in item
                    and isinstance(item["album"], dict)
                ):
                    album_image = item["album"].get("image")
                    if isinstance(album_image, dict):
                        for size in ["large", "medium", "small"]:
                            if album_image.get(size):
                                cover_url = album_image[size]
                                break
                    elif isinstance(album_image, str):
                        cover_url = album_image

            elif platform == "tidal":
                # Tidal cover URL patterns
                if "cover" in item:
                    cover_id = item["cover"]
                    if cover_id:
                        # Tidal cover URL format: https://resources.tidal.com/images/{cover_id}/1280x1280.jpg
                        cover_url = f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/1280x1280.jpg"

                # Alternative Tidal fields
                if not cover_url:
                    for field in ["image", "picture", "artwork_url", "cover_url"]:
                        if item.get(field):
                            cover_url = str(item[field])
                            break

                # For albums, try album cover
                if (
                    not cover_url
                    and "album" in item
                    and isinstance(item["album"], dict)
                ):
                    album_cover = item["album"].get("cover")
                    if album_cover:
                        cover_url = f"https://resources.tidal.com/images/{album_cover.replace('-', '/')}/1280x1280.jpg"

            elif platform == "deezer":
                # Deezer cover URL patterns
                for field in [
                    "picture",
                    "picture_medium",
                    "picture_big",
                    "picture_small",
                    "cover",
                    "cover_medium",
                    "cover_big",
                ]:
                    if item.get(field):
                        cover_url = str(item[field])
                        break

                # For albums, try album picture
                if (
                    not cover_url
                    and "album" in item
                    and isinstance(item["album"], dict)
                ):
                    for field in [
                        "picture",
                        "picture_medium",
                        "picture_big",
                        "cover",
                    ]:
                        if item["album"].get(field):
                            cover_url = str(item["album"][field])
                            break

                # For artists, try artist picture
                if not cover_url and search_type == "artist" and "picture" in item:
                    cover_url = str(item["picture"])

            elif platform == "soundcloud":
                # Enhanced SoundCloud artwork URL patterns
                # Method 1: Direct artwork_url field
                if item.get("artwork_url"):
                    cover_url = str(item["artwork_url"])

                # Method 2: Try user avatar if no artwork
                if (
                    not cover_url
                    and "user" in item
                    and isinstance(item["user"], dict)
                ):
                    user_obj = item["user"]

                    for avatar_field in ["avatar_url", "avatar", "picture", "image"]:
                        if user_obj.get(avatar_field):
                            cover_url = str(user_obj[avatar_field])
                            break

                # Method 3: Try other image fields
                if not cover_url:
                    for field in [
                        "avatar_url",
                        "picture",
                        "image",
                        "thumbnail",
                        "waveform_url",
                    ]:
                        if item.get(field):
                            cover_url = str(item[field])
                            break

                # Method 4: Try nested fields
                if not cover_url:
                    nested_fields = [
                        "user.avatar_url",
                        "user.picture",
                        "media.artwork_url",
                    ]
                    for nested_field in nested_fields:
                        parts = nested_field.split(".")
                        value = item
                        for part in parts:
                            if isinstance(value, dict) and part in value:
                                value = value[part]
                            else:
                                value = None
                                break
                        if (
                            value
                            and isinstance(value, str)
                            and value.startswith("http")
                        ):
                            cover_url = value
                            break

                # SoundCloud URL quality enhancement
                if cover_url:
                    # Upgrade to higher quality variants
                    if "large.jpg" in cover_url:
                        cover_url = cover_url.replace("large.jpg", "t500x500.jpg")
                    elif "t300x300" in cover_url:
                        cover_url = cover_url.replace("t300x300", "t500x500")
                    elif "small.jpg" in cover_url:
                        cover_url = cover_url.replace("small.jpg", "t500x500.jpg")
                    elif "tiny.jpg" in cover_url:
                        cover_url = cover_url.replace("tiny.jpg", "t500x500.jpg")

            # Generic fallback for any platform
            if not cover_url:
                for field in [
                    "image",
                    "picture",
                    "cover",
                    "artwork",
                    "thumbnail",
                    "avatar",
                    "photo",
                ]:
                    if item.get(field):
                        field_value = item[field]
                        if isinstance(field_value, str) and field_value.startswith(
                            "http"
                        ):
                            cover_url = field_value
                            break
                        if isinstance(field_value, dict):
                            # Try to find URL in nested object
                            for value in field_value.values():
                                if isinstance(value, str) and value.startswith(
                                    "http"
                                ):
                                    cover_url = value
                                    break
                            if cover_url:
                                break

            # Log the extraction result

            return cover_url

        except Exception as e:
            LOGGER.warning(f"Failed to extract cover URL from {platform}: {e}")
            return ""

    def _generate_platform_url(
        self, platform: str, media_type: str, media_id: str
    ) -> str:
        """Generate platform URL from ID using class constants for better performance"""
        # Use class-level URL templates to avoid recreating the dictionary each time
        template = self.URL_TEMPLATES.get(platform, {}).get(media_type)
        if template:
            return template.format(media_id)
        return f"https://{platform}.com/{media_type}/{media_id}"

    async def _show_search_results(self):
        """Show search results with pagination"""
        buttons = ButtonMaker()

        # Get all results flattened with caching for O(1) subsequent access
        if self._cached_all_results is None:
            self._cached_all_results = []
            for results in self.search_results.values():
                self._cached_all_results.extend(results)

            # Sort by relevance (same algorithm as inline search)
            query_lower = self.query.lower()

            def relevance_score(result):
                score = 0
                title = result.get("title", "").lower()
                artist = result.get("artist", "").lower()
                platform = result.get("platform", "").lower()

                # Text relevance scoring
                if query_lower in title:
                    score += 10
                if query_lower in artist:
                    score += 5
                if any(word in title for word in query_lower.split()):
                    score += 3
                if any(word in artist for word in query_lower.split()):
                    score += 2

                # Platform quality bias (prefer higher quality platforms)
                platform_quality_bonus = {
                    "qobuz": 3,  # Hi-Res FLAC - highest quality
                    "tidal": 2,  # MQA/Hi-Res - high quality
                    "deezer": 1,  # CD Quality - good quality
                    "soundcloud": 0,  # MP3 320kbps - lowest quality
                }
                score += platform_quality_bonus.get(platform, 0)

                return score

            self._cached_all_results.sort(key=relevance_score, reverse=True)
        all_results = self._cached_all_results

        # Check if we have any results
        total_results = len(all_results)
        if total_results == 0:
            # No results found - show error message instead of empty button menu
            error_msg = f"{self.listener.tag} ❌ <b>No results found for:</b> <code>{self.query}</code>\n\n"
            error_msg += "💡 <i>Try a different search query or check platform availability.</i>"

            no_results_msg = await send_message(self.listener.message, error_msg)
            asyncio.create_task(auto_delete_message(no_results_msg, time=300))

            # Set event to stop waiting
            self.event.set()
            return

        # Calculate pagination
        total_pages = (
            total_results + self.results_per_page - 1
        ) // self.results_per_page
        start_idx = self.current_page * self.results_per_page
        end_idx = min(start_idx + self.results_per_page, total_results)

        # Build message with beautiful HTML formatting
        msg = f"🔍 <b>Search Results for:</b> <code>{self.query}</code>\n"
        msg += f"📊 Found <b>{total_results}</b> results across <b>{len(self.search_results)}</b> platforms\n"
        msg += f"📄 Page <b>{self.current_page + 1}</b>/<b>{total_pages}</b>\n\n"

        # Show results for current page
        for i in range(start_idx, end_idx):
            result = all_results[i]
            result_num = i + 1

            # Format result display with proper truncation
            title = (
                result["title"][:45] + "..."
                if len(result["title"]) > 45
                else result["title"]
            )
            artist = (
                result["artist"][:35] + "..."
                if len(result["artist"]) > 35
                else result["artist"]
            )

            platform_emoji = {
                "qobuz": "🟦",
                "tidal": "⚫",
                "deezer": "🟣",
                "soundcloud": "🟠",
            }.get(result["platform"], "🔵")

            type_emoji = {
                "track": "🎵",
                "album": "💿",
                "playlist": "📋",
                "artist": "👤",
            }.get(result["type"], "🎵")

            # Beautiful formatted result with HTML tags
            msg += f"<b>{result_num}.</b> {platform_emoji} {type_emoji} <b>{title}</b>\n"
            msg += f"   👤 <i>{artist}</i>"

            if result["album"]:
                album = (
                    result["album"][:35] + "..."
                    if len(result["album"]) > 35
                    else result["album"]
                )
                msg += f" • 💿 <code>{album}</code>"

            if result["duration"]:
                duration_str = self._format_duration(result["duration"])
                msg += f" • ⏱️ <code>{duration_str}</code>"

            # Platform and quality info
            quality_info = result.get("quality", "")
            if quality_info:
                msg += f" • 🎯 <b>{result['platform'].title()}</b> <pre>{quality_info}</pre>\n\n"
            else:
                msg += f" • 🎯 <b>{result['platform'].title()}</b>\n\n"

            # Add download button
            buttons.data_button(
                f"{result_num}. {type_emoji} {title[:25]}...",
                f"srs select {i}",
                "header",
            )

        # Add pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if self.current_page > 0:
                nav_buttons.append(
                    ("⬅️ Previous", f"srs page {self.current_page - 1}")
                )

            nav_buttons.append(
                (f"📄 {self.current_page + 1}/{total_pages}", "srs noop")
            )

            if self.current_page < total_pages - 1:
                nav_buttons.append(("Next ➡️", f"srs page {self.current_page + 1}"))

            for text, data in nav_buttons:
                buttons.data_button(text, data, "footer")

        # Add cancel button
        buttons.data_button("❌ Cancel", "srs cancel", "footer")

        msg += f"⏱️ <b>Timeout:</b> <code>{get_readable_time(self._timeout - (time() - self._time))}</code>"

        # Send or edit message
        if self._reply_to:
            await edit_message(self._reply_to, msg, buttons.build_menu(1))
        else:
            self._reply_to = await send_message(
                self.listener.message, msg, buttons.build_menu(1)
            )

    async def _event_handler(self):
        """Handle callback query events"""
        pfunc = partial(self._handle_callback, obj=self)
        handler = self.listener.client.add_handler(
            CallbackQueryHandler(
                pfunc,
                filters=regex("^srs") & user(self.listener.user_id),
            ),
            group=-1,
        )
        try:
            await asyncio.wait_for(self.event.wait(), timeout=self._timeout)
        except TimeoutError:
            # Send timeout message with beautiful formatting
            timeout_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} ⏰ <b>Search selection timed out.</b>\n\n"
                f"🔍 <i>Search query:</i> <code>{self.query}</code>\n"
                f"💡 <i>Use</i> <code>/srsearch {self.query}</code> <i>to search again.</i>",
            )

            # Delete the search results
            if self._reply_to:
                await delete_message(self._reply_to)

            # Auto-delete timeout message
            asyncio.create_task(auto_delete_message(timeout_msg, time=300))

            self.event.set()
        finally:
            self.listener.client.remove_handler(*handler)

    @staticmethod
    async def _handle_callback(_, query, obj):
        """Handle callback query"""
        data = query.data.split()
        await query.answer()

        if data[1] == "select":
            # Get selected result using cached results for O(1) access
            result_idx = int(data[2])
            if obj._cached_all_results is None:
                obj._cached_all_results = []
                for results in obj.search_results.values():
                    obj._cached_all_results.extend(results)

                # Sort by relevance (same algorithm as inline search)
                query_lower = obj.query.lower()

                def relevance_score(result):
                    score = 0
                    title = result.get("title", "").lower()
                    artist = result.get("artist", "").lower()
                    platform = result.get("platform", "").lower()

                    # Text relevance scoring
                    if query_lower in title:
                        score += 10
                    if query_lower in artist:
                        score += 5
                    if any(word in title for word in query_lower.split()):
                        score += 3
                    if any(word in artist for word in query_lower.split()):
                        score += 2

                    # Platform quality bias (prefer higher quality platforms)
                    platform_quality_bonus = {
                        "qobuz": 3,  # Hi-Res FLAC - highest quality
                        "tidal": 2,  # MQA/Hi-Res - high quality
                        "deezer": 1,  # CD Quality - good quality
                        "soundcloud": 0,  # MP3 320kbps - lowest quality
                    }
                    score += platform_quality_bonus.get(platform, 0)

                    return score

                obj._cached_all_results.sort(key=relevance_score, reverse=True)
            all_results = obj._cached_all_results

            if 0 <= result_idx < len(all_results):
                obj.selected_result = all_results[result_idx]

                # Show selection confirmation with beautiful HTML formatting
                result = obj.selected_result
                msg = "✅ <b>Selected:</b>\n\n"
                msg += f"🎵 <b>{result['title']}</b>\n"
                msg += f"👤 Artist: <i>{result['artist']}</i>\n"

                if result["album"]:
                    msg += f"💿 Album: <code>{result['album']}</code>\n"

                if result["duration"]:
                    duration_str = obj._format_duration(result["duration"])
                    msg += f"⏱️ Duration: <code>{duration_str}</code>\n"

                quality_info = result.get("quality", "")
                if quality_info:
                    msg += f"🎯 Platform: <b>{result['platform'].title()}</b> <pre>{quality_info}</pre>\n"
                else:
                    msg += f"🎯 Platform: <b>{result['platform'].title()}</b>\n"

                msg += f"📁 Type: <b>{result['type'].title()}</b>\n\n"
                msg += "🚀 <b>Starting download...</b>"

                await edit_message(obj._reply_to, msg)

                # Auto-delete after 10 seconds
                asyncio.create_task(auto_delete_message(obj._reply_to, time=10))

                obj.event.set()

        elif data[1] == "page":
            # Change page
            new_page = int(data[2])
            obj.current_page = new_page
            await obj._show_search_results()

        elif data[1] == "cancel":
            # Send cancellation message with beautiful formatting
            cancel_msg = await send_message(
                obj.listener.message,
                f"{obj.listener.tag} ❌ <b>Search cancelled!</b>\n\n"
                f"🔍 <i>Search query:</i> <code>{obj.query}</code>\n"
                f"💡 <i>Use</i> <code>/srsearch {obj.query}</code> <i>to search again.</i>",
            )

            # Delete the search results
            if obj._reply_to:
                await delete_message(obj._reply_to)

            # Auto-delete cancellation message
            asyncio.create_task(auto_delete_message(cancel_msg, time=300))

            obj.listener.is_cancelled = True
            obj.event.set()

        elif data[1] == "noop":
            # No operation (for page indicator)
            pass

    def _format_duration(self, duration: int) -> str:
        """Format duration in seconds to MM:SS"""
        if not duration:
            return "Unknown"

        minutes = duration // 60
        seconds = duration % 60
        return f"{minutes}:{seconds:02d}"


async def search_music(
    listener,
    query: str,
    platform: str | None = None,
    media_type_filter: str | None = None,
    result_limit: int = 20,
) -> dict[str, Any] | None:
    """Search for music across platforms"""
    search_handler = StreamripSearchHandler(
        listener, query, platform, media_type_filter, result_limit
    )
    return await search_handler.search()


async def search_music_auto_first(
    listener,
    query: str,
    platform: str | None = None,
    media_type_filter: str | None = None,
    result_limit: int = 20,
) -> dict[str, Any] | None:
    """Search for music and automatically return first result"""
    search_handler = StreamripSearchHandler(
        listener, query, platform, media_type_filter, result_limit
    )

    try:
        # Perform search without showing interactive results
        await search_handler._perform_search()

        # Get all results
        all_results = []
        for platform_results in search_handler.search_results.values():
            all_results.extend(platform_results)

        if not all_results:
            no_results_msg = await send_message(
                listener.message,
                f"{listener.tag} ❌ <b>No results found for:</b> <code>{query}</code>\n\n"
                f"💡 <i>Try a different search query or check platform availability.</i>",
            )
            asyncio.create_task(auto_delete_message(no_results_msg, time=300))
            return None

        # Sort by relevance (same algorithm as inline search) to get the best first result
        query_lower = query.lower()

        def relevance_score(result):
            score = 0
            title = result.get("title", "").lower()
            artist = result.get("artist", "").lower()
            platform = result.get("platform", "").lower()

            # Text relevance scoring
            if query_lower in title:
                score += 10
            if query_lower in artist:
                score += 5
            if any(word in title for word in query_lower.split()):
                score += 3
            if any(word in artist for word in query_lower.split()):
                score += 2

            # Platform quality bias (prefer higher quality platforms)
            platform_quality_bonus = {
                "qobuz": 3,  # Hi-Res FLAC - highest quality
                "tidal": 2,  # MQA/Hi-Res - high quality
                "deezer": 1,  # CD Quality - good quality
                "soundcloud": 0,  # MP3 320kbps - lowest quality
            }
            score += platform_quality_bonus.get(platform, 0)

            return score

        all_results.sort(key=relevance_score, reverse=True)

        # Return first result (now the most relevant)
        first_result = all_results[0]

        # Show auto-selection message with beautiful HTML formatting
        msg = "⚡ <b>Auto-selected first result:</b>\n\n"
        msg += f"🎵 <b>{first_result['title']}</b>\n"
        msg += f"👤 Artist: <i>{first_result['artist']}</i>\n"

        if first_result["album"]:
            msg += f"💿 Album: <code>{first_result['album']}</code>\n"

        if first_result["duration"]:
            duration_str = search_handler._format_duration(first_result["duration"])
            msg += f"⏱️ Duration: <code>{duration_str}</code>\n"

        quality_info = first_result.get("quality", "")
        if quality_info:
            msg += f"🎯 Platform: <b>{first_result['platform'].title()}</b> <pre>{quality_info}</pre>\n"
        else:
            msg += f"🎯 Platform: <b>{first_result['platform'].title()}</b>\n"

        msg += f"📁 Type: <b>{first_result['type'].title()}</b>\n\n"
        msg += "🚀 <b>Starting download...</b>"

        auto_msg = await send_message(listener.message, msg)
        asyncio.create_task(auto_delete_message(auto_msg, time=10))

        return first_result

    finally:
        # Always cleanup clients to prevent unclosed sessions
        await search_handler._cleanup_clients()


# Global cleanup function for emergency session cleanup
async def cleanup_all_streamrip_sessions():
    """Emergency cleanup function to close any remaining aiohttp sessions"""
    try:
        import gc

        import aiohttp

        # Force garbage collection to identify unclosed sessions
        gc.collect()

        # Look for any remaining aiohttp sessions in garbage
        for obj in gc.get_objects():
            if isinstance(obj, aiohttp.ClientSession):
                try:
                    if not obj.closed:
                        await obj.close()
                except Exception as e:
                    LOGGER.warning(f"Failed to close orphaned session: {e}")

        # Final garbage collection
        gc.collect()

    except Exception as e:
        LOGGER.error(f"Error during emergency cleanup: {e}")


# ===== INLINE SEARCH FUNCTIONALITY =====

# Cache for streamrip search results to avoid redundant searches
STREAMRIP_SEARCH_CACHE = {}
STREAMRIP_CACHE_COUNTER = 0

# Cache for streamrip result info (for start command access)
STREAMRIP_RESULT_CACHE = {}

# Global cache for authenticated clients with activity tracking
STREAMRIP_CLIENT_CACHE = {}
CLIENT_CACHE_EXPIRY = (
    3600  # 1 hour max age - but will be cleaned based on inactivity
)
CLIENT_INACTIVITY_TIMEOUT = 60  # 1 minute of inactivity before cleanup
CLIENT_LAST_ACTIVITY = {}  # Track last activity per client
_cleanup_task = None  # Background cleanup task

# Circuit breaker for failed platforms
PLATFORM_FAILURE_TRACKER = {}
FAILURE_THRESHOLD = 3  # Number of consecutive failures before circuit opens
CIRCUIT_RESET_TIME = 60  # Time in seconds before trying failed platform again


def generate_streamrip_cache_key(query, platform, media_type, user_id):
    """Generate a unique key for caching streamrip search results."""
    key = f"{user_id}_{query}_{platform}_{media_type}"
    return hashlib.md5(key.encode()).hexdigest()


def is_platform_circuit_open(platform_name):
    """Check if circuit breaker is open for a platform."""
    if platform_name not in PLATFORM_FAILURE_TRACKER:
        return False

    failure_data = PLATFORM_FAILURE_TRACKER[platform_name]
    current_time = time_module.time()

    # If enough time has passed, reset the circuit
    if current_time - failure_data["last_failure"] > CIRCUIT_RESET_TIME:
        del PLATFORM_FAILURE_TRACKER[platform_name]
        return False

    # Check if failure threshold exceeded
    return failure_data["count"] >= FAILURE_THRESHOLD


def record_platform_failure(platform_name):
    """Record a platform failure for circuit breaker."""
    current_time = time_module.time()

    if platform_name not in PLATFORM_FAILURE_TRACKER:
        PLATFORM_FAILURE_TRACKER[platform_name] = {
            "count": 1,
            "last_failure": current_time,
        }
    else:
        PLATFORM_FAILURE_TRACKER[platform_name]["count"] += 1
        PLATFORM_FAILURE_TRACKER[platform_name]["last_failure"] = current_time


def record_platform_success(platform_name):
    """Record a platform success, resetting circuit breaker."""
    PLATFORM_FAILURE_TRACKER.pop(platform_name, None)


def encrypt_streamrip_data(data_string):
    """Create a compact token for streamrip result data."""
    global STREAMRIP_CACHE_COUNTER
    try:
        # Use hash-based lookup instead of linear search to reduce CPU overhead
        import hashlib

        data_hash = hashlib.md5(data_string.encode()).hexdigest()[:16]

        # Check if this hash is already in the cache (more efficient lookup)
        for key in STREAMRIP_RESULT_CACHE:
            if key.endswith(data_hash):
                return key

        # Generate a new short ID
        STREAMRIP_CACHE_COUNTER += 1
        short_id = f"sr{STREAMRIP_CACHE_COUNTER}"

        # Store in cache
        STREAMRIP_RESULT_CACHE[short_id] = data_string

        # Clean up cache if it gets too large (keep last 500 entries)
        if len(STREAMRIP_RESULT_CACHE) > 500:
            # Get oldest keys (first 50)
            oldest_keys = list(STREAMRIP_RESULT_CACHE.keys())[:50]
            for key in oldest_keys:
                del STREAMRIP_RESULT_CACHE[key]

        return short_id
    except Exception as e:
        LOGGER.error(f"Streamrip ID generation error: {e}")
        return f"sr{int(time_module.time())}"


def decrypt_streamrip_data(short_id):
    """Get the original data from the short ID."""
    try:
        if short_id in STREAMRIP_RESULT_CACHE:
            return STREAMRIP_RESULT_CACHE[short_id]
        LOGGER.warning(f"Streamrip ID not found in cache: {short_id}")
        return short_id
    except Exception as e:
        LOGGER.error(f"Streamrip ID lookup error: {e}")
        return short_id


def _update_client_activity(platform_name):
    """Update last activity time for a client"""
    CLIENT_LAST_ACTIVITY[platform_name] = time_module.time()


async def _cleanup_inactive_clients():
    """Clean up clients that have been inactive for more than CLIENT_INACTIVITY_TIMEOUT"""
    current_time = time_module.time()
    clients_to_remove = []

    for platform_name in list(CLIENT_LAST_ACTIVITY.keys()):
        last_activity = CLIENT_LAST_ACTIVITY.get(platform_name, 0)
        if current_time - last_activity > CLIENT_INACTIVITY_TIMEOUT:
            clients_to_remove.append(platform_name)

    for platform_name in clients_to_remove:
        cache_key = f"{platform_name}_client"
        if cache_key in STREAMRIP_CLIENT_CACHE:
            try:
                _cached_time, cached_client = STREAMRIP_CLIENT_CACHE[cache_key]
                # Clean up client session
                if (
                    hasattr(cached_client, "session")
                    and cached_client.session
                    and not cached_client.session.closed
                ):
                    await cached_client.session.close()

            except Exception as e:
                LOGGER.warning(
                    f"Error cleaning up inactive {platform_name} client: {e}"
                )
            finally:
                del STREAMRIP_CLIENT_CACHE[cache_key]
                CLIENT_LAST_ACTIVITY.pop(platform_name, None)


async def _start_cleanup_task():
    """Start background cleanup task if not already running"""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_background_cleanup_loop())


async def _background_cleanup_loop():
    """Background loop to clean up inactive clients every 30 seconds"""
    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            await _cleanup_inactive_clients()
        except asyncio.CancelledError:
            break
        except Exception as e:
            LOGGER.warning(f"Error in background cleanup: {e}")
            await asyncio.sleep(30)  # Continue after error


async def _get_or_create_cached_client(platform_name, config):
    """Get cached client or create new one with authentication."""
    try:
        # Check circuit breaker first
        if is_platform_circuit_open(platform_name):
            LOGGER.warning(f"Circuit breaker open for {platform_name}, skipping")
            return None

        current_time = time_module.time()
        cache_key = f"{platform_name}_client"

        # Start background cleanup task if needed
        await _start_cleanup_task()

        # Clean up inactive clients first
        await _cleanup_inactive_clients()

        # Check if we have a valid cached client
        if cache_key in STREAMRIP_CLIENT_CACHE:
            cached_time, cached_client = STREAMRIP_CLIENT_CACHE[cache_key]
            # Check both max age and inactivity
            last_activity = CLIENT_LAST_ACTIVITY.get(platform_name, cached_time)
            if (
                current_time - cached_time < CLIENT_CACHE_EXPIRY
                and current_time - last_activity < CLIENT_INACTIVITY_TIMEOUT
            ):
                # Verify client is still valid
                if (
                    hasattr(cached_client, "session")
                    and cached_client.session
                    and not cached_client.session.closed
                ):
                    # Update activity and reset circuit breaker
                    _update_client_activity(platform_name)
                    record_platform_success(platform_name)

                    return cached_client
            # Remove invalid or inactive cached client

            STREAMRIP_CLIENT_CACHE.pop(cache_key, None)
            CLIENT_LAST_ACTIVITY.pop(platform_name, None)
        # Create new client with timeout
        client = None
        try:
            if platform_name == "qobuz":
                client = QobuzClient(config)
            elif platform_name == "tidal":
                client = TidalClient(config)
            elif platform_name == "deezer":
                client = DeezerClient(config)
            elif platform_name == "soundcloud":
                client = SoundcloudClient(config)
            else:
                LOGGER.warning(f"Unsupported platform for caching: {platform_name}")
                return None

            # Authenticate with reasonable timeout for inline queries
            if hasattr(client, "login"):
                await asyncio.wait_for(
                    client.login(), timeout=10.0
                )  # Increased auth timeout to 10 seconds for better reliability

            # Cache the authenticated client and track activity
            STREAMRIP_CLIENT_CACHE[cache_key] = (current_time, client)
            _update_client_activity(platform_name)
            record_platform_success(
                platform_name
            )  # Reset circuit breaker on success

            # Clean up old cache entries
            if len(STREAMRIP_CLIENT_CACHE) > 10:
                oldest_key = min(
                    STREAMRIP_CLIENT_CACHE.keys(),
                    key=lambda k: STREAMRIP_CLIENT_CACHE[k][0],
                )
                _old_time, old_client = STREAMRIP_CLIENT_CACHE[oldest_key]
                # Clean up old client session
                if (
                    hasattr(old_client, "session")
                    and old_client.session
                    and not old_client.session.closed
                ):
                    with contextlib.suppress(Exception):
                        await old_client.session.close()
                del STREAMRIP_CLIENT_CACHE[oldest_key]

            return client

        except TimeoutError:
            LOGGER.warning(f"Authentication timeout for {platform_name} (10s)")
            record_platform_failure(
                platform_name
            )  # Record failure for circuit breaker
            if (
                client
                and hasattr(client, "session")
                and client.session
                and not client.session.closed
            ):
                with contextlib.suppress(Exception):
                    await client.session.close()
            return None
        except Exception as auth_error:
            error_msg = str(auth_error).strip()
            if not error_msg:
                # Silent authentication failure - provide more context
                if platform_name == "qobuz":
                    LOGGER.warning(
                        "Qobuz authentication failed: missing app_id/secrets or invalid credentials"
                    )
                else:
                    LOGGER.warning(
                        f"{platform_name.title()} authentication failed: check credentials"
                    )
            else:
                LOGGER.warning(
                    f"{platform_name.title()} authentication failed: {error_msg[:100]}"
                )
            record_platform_failure(
                platform_name
            )  # Record failure for circuit breaker
            if (
                client
                and hasattr(client, "session")
                and client.session
                and not client.session.closed
            ):
                with contextlib.suppress(Exception):
                    await client.session.close()
            return None

    except Exception as e:
        LOGGER.error(f"Error creating cached client for {platform_name}: {e}")
        return None


async def perform_inline_streamrip_search(query, platform, media_type, user_id):
    """Perform streamrip search for inline queries with optimized timeouts and connection management."""
    time_module.time()

    try:
        # Check cache first
        cache_key = generate_streamrip_cache_key(
            query, platform, media_type, user_id
        )
        if cache_key in STREAMRIP_SEARCH_CACHE:
            cached_time, cached_results = STREAMRIP_SEARCH_CACHE[cache_key]
            # Use cached results if less than 5 minutes old
            if time_module.time() - cached_time < 300:
                return cached_results

        # Initialize streamrip clients directly for inline search
        clients = {}

        # Initialize streamrip on-demand
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            ensure_streamrip_initialized,
        )

        if not await ensure_streamrip_initialized():
            LOGGER.warning("Streamrip initialization failed for inline search")
            return []

        # Import streamrip configuration
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            streamrip_config,
        )

        config = streamrip_config.get_config()
        if not config:
            LOGGER.warning("Streamrip config not available for inline search")
            return []

        # Initialize clients based on available credentials
        if platform:
            # Search specific platform
            platforms_to_search = [platform]
        else:
            # Search all configured platforms based on streamrip config
            platforms_to_search = []
            platform_status = streamrip_config.get_platform_status()

            # Only include platforms that are enabled, have credentials, and circuit breaker is closed
            for platform_name, enabled in platform_status.items():
                if (
                    enabled
                    and platform_name
                    in [
                        "qobuz",
                        "tidal",
                        "deezer",
                        "soundcloud",
                    ]
                    and not is_platform_circuit_open(platform_name)
                ):
                    platforms_to_search.append(platform_name)

        if not platforms_to_search:
            LOGGER.warning("No streamrip platforms configured for inline search")
            return []

        # Initialize clients with caching and parallel authentication
        auth_tasks = []
        for platform_name in platforms_to_search:
            auth_tasks.append(_get_or_create_cached_client(platform_name, config))

        # Remove aggressive time check - let authentication complete naturally
        # Authentication is important for search quality

        # Execute authentication in parallel with individual timeouts
        auth_results = await asyncio.gather(*auth_tasks, return_exceptions=True)

        # Process authentication results
        for i, result in enumerate(auth_results):
            platform_name = platforms_to_search[i]
            if isinstance(result, Exception):
                LOGGER.warning(
                    f"Failed to authenticate {platform_name} for inline search: {str(result)[:100]}"
                )
                continue
            if result:
                clients[platform_name] = result

        if not clients:
            LOGGER.warning(
                "No streamrip clients could be initialized for inline search"
            )
            return []

        # Remove aggressive time check - let searches complete naturally
        # Search completion is more important than arbitrary time limits

        # Perform searches on all available platforms
        all_results = []
        search_tasks = []

        for platform_name, client in clients.items():
            search_tasks.append(
                _search_platform_inline(client, platform_name, query, media_type)
            )

        # Execute searches concurrently
        platform_results = await asyncio.gather(
            *search_tasks, return_exceptions=True
        )

        # Process results
        for i, result in enumerate(platform_results):
            platform_name = list(clients.keys())[i]
            if isinstance(result, Exception):
                LOGGER.warning(
                    f"Search failed for platform {platform_name}: {str(result)[:100]}"
                )
                record_platform_failure(
                    platform_name
                )  # Record failure for circuit breaker
                continue
            if result:
                all_results.extend(result)
                # Update activity for successful searches
                _update_client_activity(platform_name)
                record_platform_success(platform_name)  # Record success

        # Sort by relevance (title match first, then artist match)
        query_lower = query.lower()

        def relevance_score(result):
            score = 0
            title = result.get("title", "").lower()
            artist = result.get("artist", "").lower()
            platform = result.get("platform", "").lower()

            # Text relevance scoring
            if query_lower in title:
                score += 10
            if query_lower in artist:
                score += 5
            if any(word in title for word in query_lower.split()):
                score += 3
            if any(word in artist for word in query_lower.split()):
                score += 2

            # Platform quality bias (prefer higher quality platforms)
            platform_quality_bonus = {
                "qobuz": 3,  # Hi-Res FLAC - highest quality
                "tidal": 2,  # MQA/Hi-Res - high quality
                "deezer": 1,  # CD Quality - good quality
                "soundcloud": 0,  # MP3 320kbps - lowest quality
            }
            score += platform_quality_bonus.get(platform, 0)

            return score

        all_results.sort(key=relevance_score, reverse=True)

        # Cache results
        STREAMRIP_SEARCH_CACHE[cache_key] = (time_module.time(), all_results)

        # Clean up cache if too large (increased for more results)
        if len(STREAMRIP_SEARCH_CACHE) > 50:
            oldest_key = min(
                STREAMRIP_SEARCH_CACHE.keys(),
                key=lambda k: STREAMRIP_SEARCH_CACHE[k][0],
            )
            del STREAMRIP_SEARCH_CACHE[oldest_key]

        return all_results

    except Exception as e:
        LOGGER.error(f"Error in inline streamrip search: {e}")
        return []
    # Note: We don't cleanup clients here anymore - they're kept alive for 1 minute of inactivity


async def _cleanup_inline_clients(clients):
    """Cleanup inline search clients to prevent session leaks"""
    for platform_name, client in clients.items():
        try:
            # Try multiple session cleanup approaches
            cleanup_tasks = []

            if (
                hasattr(client, "session")
                and client.session
                and not client.session.closed
            ):
                cleanup_tasks.append(client.session.close())
            elif (
                hasattr(client, "_session")
                and client._session
                and not client._session.closed
            ):
                cleanup_tasks.append(client._session.close())
            elif (
                hasattr(client, "_http_session")
                and client._http_session
                and not client._http_session.closed
            ):
                cleanup_tasks.append(client._http_session.close())

            # Also try to close any connector
            if hasattr(client, "connector") and client.connector:
                cleanup_tasks.append(client.connector.close())
            elif hasattr(client, "_connector") and client._connector:
                cleanup_tasks.append(client._connector.close())

            # Execute cleanup with timeout
            if cleanup_tasks:
                await asyncio.wait_for(
                    asyncio.gather(*cleanup_tasks, return_exceptions=True),
                    timeout=3.0,
                )

        except TimeoutError:
            LOGGER.warning(f"Cleanup timeout for {platform_name} inline client")
        except Exception as cleanup_error:
            LOGGER.warning(
                f"Failed to cleanup {platform_name} inline client: {str(cleanup_error)[:100]}"
            )


async def _search_platform_inline(client, platform_name, query, media_type):
    """Perform search on a specific platform for inline queries."""
    try:
        results = []

        # Determine search types based on media_type filter
        if media_type:
            search_types = [media_type]
        else:
            # Use platform-specific search types (prioritize tracks and albums for better results)
            platform_types = {
                "qobuz": ["track", "album", "artist", "playlist"],
                "deezer": ["track", "album", "artist", "playlist"],
                "tidal": ["track", "album", "artist", "playlist"],
                "soundcloud": ["track"],  # SoundCloud mainly supports tracks
            }
            search_types = platform_types.get(platform_name, ["track"])

        # Perform search for each type with timeout and limit
        for search_type in search_types:
            try:
                # Search using streamrip client API without timeout - let it complete
                search_response = await client.search(
                    search_type, query, limit=15
                )  # No timeout - let search complete naturally

                if search_response:
                    # Extract results from platform-specific containers
                    actual_results = _extract_results_from_containers_inline(
                        search_response, platform_name, search_type
                    )

                    for item in actual_results:
                        # Extract metadata without excessive logging
                        result = _extract_search_result_inline(
                            item, platform_name, search_type
                        )
                        if result:
                            results.append(result)
                            # Limit results per platform to avoid overwhelming the response
                            if len(results) >= 25:  # Max 25 results per platform
                                break

                    # If we have enough results, break early
                    if len(results) >= 25:
                        break

            except TimeoutError:
                LOGGER.warning(
                    f"Search timeout for {search_type} on {platform_name} (8s)"
                )
                continue
            except Exception as search_error:
                error_msg = str(search_error)

                # Handle specific connection errors for inline search
                if (
                    "Connector is closed" in error_msg
                    or "Session is closed" in error_msg
                ):
                    LOGGER.warning(
                        f"Connection closed for {platform_name} (inline), recreating client"
                    )
                    try:
                        # Recreate client and retry once for inline search
                        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                            streamrip_config,
                        )

                        config = streamrip_config.get_config()

                        # Import and get the appropriate client class
                        from streamrip.client import (
                            DeezerClient,
                            QobuzClient,
                            SoundcloudClient,
                            TidalClient,
                        )

                        client_classes = {
                            "qobuz": QobuzClient,
                            "tidal": TidalClient,
                            "deezer": DeezerClient,
                            "soundcloud": SoundcloudClient,
                        }

                        if platform_name in client_classes:
                            client = client_classes[platform_name](config)

                            # Login and retry search
                            if hasattr(client, "login"):
                                await client.login()

                            # Retry the search once without timeout
                            search_response = await client.search(
                                search_type, query, limit=15
                            )

                            if search_response:
                                actual_results = (
                                    _extract_results_from_containers_inline(
                                        search_response, platform_name, search_type
                                    )
                                )

                                for item in actual_results:
                                    result = _extract_search_result_inline(
                                        item, platform_name, search_type
                                    )
                                    if result:
                                        results.append(result)
                                        if len(results) >= 25:
                                            break

                                LOGGER.info(
                                    f"Recovered {platform_name} connection (inline)"
                                )
                                continue

                    except Exception as retry_error:
                        LOGGER.error(
                            f"Failed to recover {platform_name} connection (inline): {retry_error}"
                        )

                LOGGER.warning(
                    f"Search type '{search_type}' failed on {platform_name}: {search_error}"
                )
                continue

        return results  # Return all results, no limit per platform

    except Exception as e:
        LOGGER.error(f"Platform search failed for {platform_name}: {e}")
        return []


def _extract_results_from_containers_inline(search_response, platform, search_type):
    """Extract actual results from platform-specific response containers for inline search."""
    actual_results = []

    try:
        if isinstance(search_response, dict):
            # Handle different response structures
            if "items" in search_response:
                result_container = search_response["items"]
            elif "data" in search_response:
                result_container = search_response["data"]
            elif "results" in search_response:
                result_container = search_response["results"]
            elif "collection" in search_response:
                # SoundCloud uses 'collection' to wrap results
                result_container = search_response["collection"]
            elif search_type in search_response:
                result_container = search_response[search_type]
            else:
                # Fallback: treat as single item
                actual_results.append(search_response)
                return actual_results

            # Extract from container
            if isinstance(result_container, list):
                actual_results = result_container
            elif isinstance(result_container, dict):
                if "items" in result_container:
                    actual_results = result_container["items"]
                elif "data" in result_container:
                    actual_results = result_container["data"]
                else:
                    # Fallback: treat as single item
                    actual_results.append(result_container)
        elif isinstance(search_response, list):
            # Handle list responses - check if it contains dictionaries with 'items'
            actual_results = []
            for list_item in search_response:
                if isinstance(list_item, dict):
                    # Check for nested structures like Qobuz: {'tracks': {'items': [...]}}
                    extracted_from_nested = False

                    # Check all possible nested containers
                    for container_type in [
                        "tracks",
                        "albums",
                        "artists",
                        "playlists",
                        "collection",  # SoundCloud uses 'collection'
                    ]:
                        if container_type in list_item:
                            container_value = list_item[container_type]
                            if (
                                isinstance(container_value, dict)
                                and "items" in container_value
                            ):
                                # Standard nested structure: {'tracks': {'items': [...]}}
                                items_to_add = container_value["items"]
                                actual_results.extend(items_to_add)
                                extracted_from_nested = True
                                break
                            if (
                                isinstance(container_value, list)
                                and container_type == "collection"
                            ):
                                # SoundCloud direct collection: {'collection': [...]}
                                actual_results.extend(container_value)
                                extracted_from_nested = True
                                break

                    # If no nested container found, check for direct 'items'
                    if not extracted_from_nested and "items" in list_item:
                        # This is a paginated response wrapped in a list (Tidal format)
                        actual_results.extend(list_item["items"])
                        extracted_from_nested = True

                    # If still no extraction, treat as direct item
                    if not extracted_from_nested:
                        actual_results.append(list_item)
                else:
                    # Direct item in list
                    actual_results.append(list_item)
        else:
            # Single item response
            actual_results = [search_response]

    except Exception as e:
        LOGGER.warning(f"Failed to extract results from {platform} response: {e}")
        actual_results = []

    return actual_results


def _extract_search_result_inline(item, platform, search_type):
    """Extract search result metadata for inline search with thumbnail support."""
    try:
        result = {
            "platform": platform,
            "type": search_type,
            "title": "Unknown",
            "artist": "Unknown Artist",
            "album": "",
            "duration": 0,
            "url": "",
            "id": "",
            "cover_url": "",
            "thumbnail_url": "",
        }

        # Handle platform-specific nested data structures
        if platform == "deezer" and isinstance(item, dict) and "data" in item:
            # Deezer wraps results in a 'data' array, extract the first item
            if isinstance(item["data"], list) and item["data"]:
                actual_item = item["data"][0]  # Get first track from the data array
            else:
                actual_item = item
        else:
            actual_item = item

        # Extract title - handle multiple possible field names
        if actual_item.get("title"):
            result["title"] = str(actual_item["title"])
        elif actual_item.get("name"):
            result["title"] = str(actual_item["name"])
        elif actual_item.get("track_title"):
            result["title"] = str(actual_item["track_title"])
        elif actual_item.get("song_title"):
            result["title"] = str(actual_item["song_title"])

        # Platform-specific artist extraction with enhanced Deezer support
        if platform == "deezer":
            # Deezer-specific artist extraction - handle multiple possible field structures
            if "artist" in actual_item:
                if isinstance(actual_item["artist"], dict):
                    result["artist"] = actual_item["artist"].get(
                        "name", str(actual_item["artist"])
                    )
                elif isinstance(actual_item["artist"], str):
                    result["artist"] = actual_item["artist"]
                else:
                    result["artist"] = str(actual_item["artist"])
            elif actual_item.get("artists"):
                if (
                    isinstance(actual_item["artists"], list)
                    and actual_item["artists"]
                ):
                    first_artist = actual_item["artists"][0]
                    if isinstance(first_artist, dict):
                        result["artist"] = first_artist.get(
                            "name", str(first_artist)
                        )
                    else:
                        result["artist"] = str(first_artist)
                elif isinstance(actual_item["artists"], dict):
                    result["artist"] = actual_item["artists"].get(
                        "name", str(actual_item["artists"])
                    )
                elif isinstance(actual_item["artists"], str):
                    result["artist"] = actual_item["artists"]
            elif actual_item.get("contributors"):
                # Deezer sometimes uses 'contributors' field
                if (
                    isinstance(actual_item["contributors"], list)
                    and actual_item["contributors"]
                ):
                    first_contributor = actual_item["contributors"][0]
                    if isinstance(first_contributor, dict):
                        result["artist"] = first_contributor.get(
                            "name", str(first_contributor)
                        )
                    else:
                        result["artist"] = str(first_contributor)
            # Try alternative Deezer field names
            elif "artist_name" in actual_item:
                result["artist"] = str(actual_item["artist_name"])
            elif "performer" in actual_item:
                if isinstance(actual_item["performer"], dict):
                    result["artist"] = actual_item["performer"].get(
                        "name", str(actual_item["performer"])
                    )
                else:
                    result["artist"] = str(actual_item["performer"])
            # Special handling for artist and playlist search types
            elif search_type == "artist":
                # For artist searches, the title IS the artist name
                result["artist"] = result["title"]
            elif search_type == "playlist":
                # For playlist searches, try to get the creator/owner
                if "creator" in actual_item:
                    if isinstance(actual_item["creator"], dict):
                        result["artist"] = actual_item["creator"].get(
                            "name", actual_item["creator"].get("username", "Unknown")
                        )
                    else:
                        result["artist"] = str(actual_item["creator"])
                elif "user" in actual_item:
                    if isinstance(actual_item["user"], dict):
                        result["artist"] = actual_item["user"].get(
                            "name", actual_item["user"].get("username", "Unknown")
                        )
                    else:
                        result["artist"] = str(actual_item["user"])
                elif "owner" in actual_item:
                    if isinstance(actual_item["owner"], dict):
                        result["artist"] = actual_item["owner"].get(
                            "name", actual_item["owner"].get("username", "Unknown")
                        )
                    else:
                        result["artist"] = str(actual_item["owner"])
        # Generic artist extraction for other platforms
        elif "artist" in item:
            if isinstance(item["artist"], dict):
                result["artist"] = item["artist"].get("name", str(item["artist"]))
            else:
                result["artist"] = str(item["artist"])
        elif "performer" in item:
            # Qobuz uses 'performer' instead of 'artist'
            if isinstance(item["performer"], dict):
                result["artist"] = item["performer"].get(
                    "name", str(item["performer"])
                )
            else:
                result["artist"] = str(item["performer"])
        elif item.get("artists"):
            if isinstance(item["artists"], list) and item["artists"]:
                first_artist = item["artists"][0]
                if isinstance(first_artist, dict):
                    result["artist"] = first_artist.get("name", str(first_artist))
                else:
                    result["artist"] = str(first_artist)
            elif isinstance(item["artists"], dict):
                result["artist"] = item["artists"].get("name", str(item["artists"]))
        elif item.get("contributors"):
            # Deezer sometimes uses 'contributors' field
            if isinstance(item["contributors"], list) and item["contributors"]:
                first_contributor = item["contributors"][0]
                if isinstance(first_contributor, dict):
                    result["artist"] = first_contributor.get(
                        "name", str(first_contributor)
                    )
                else:
                    result["artist"] = str(first_contributor)
        elif platform == "soundcloud":
            # Enhanced SoundCloud metadata extraction for inline search
            # Try multiple SoundCloud artist field patterns with more robust handling
            artist_found = False

            # Method 1: Try user object (most common)
            if "user" in actual_item and not artist_found:
                user_obj = actual_item["user"]

                if isinstance(user_obj, dict):
                    # Try different user fields in order of preference
                    for field in ["username", "display_name", "full_name", "name"]:
                        if user_obj.get(field):
                            result["artist"] = str(user_obj[field]).strip()
                            artist_found = True
                            break

                    # If no specific field found, try to extract from user object
                    if not artist_found:
                        result["artist"] = str(user_obj)
                        artist_found = True
                elif isinstance(user_obj, str) and user_obj.strip():
                    result["artist"] = str(user_obj).strip()
                    artist_found = True

            # Method 2: Try uploader field
            if "uploader" in actual_item and not artist_found:
                uploader = actual_item["uploader"]
                if uploader and str(uploader).strip():
                    result["artist"] = str(uploader).strip()
                    artist_found = True

            # Method 3: Try publisher metadata
            if "publisher_metadata" in actual_item and not artist_found:
                pub_meta = actual_item["publisher_metadata"]

                if isinstance(pub_meta, dict):
                    for field in ["artist", "performer", "creator", "author"]:
                        if pub_meta.get(field):
                            result["artist"] = str(pub_meta[field]).strip()
                            artist_found = True
                            break

            # Method 4: Try other common fields
            if not artist_found:
                for field in ["artist", "performer", "creator", "author", "channel"]:
                    if actual_item.get(field):
                        field_value = actual_item[field]
                        if isinstance(field_value, dict) and "name" in field_value:
                            result["artist"] = str(field_value["name"]).strip()
                        elif isinstance(field_value, str) and field_value.strip():
                            result["artist"] = str(field_value).strip()
                        else:
                            continue
                        artist_found = True
                        break

            if not artist_found:
                LOGGER.warning(
                    f"INLINE-SOUNDCLOUD: No artist field found, keeping default: {result['artist']}"
                )
        elif "user" in item:
            # Generic user field handling for other platforms
            if isinstance(item["user"], dict):
                result["artist"] = item["user"].get(
                    "username", item["user"].get("name", str(item["user"]))
                )
            else:
                result["artist"] = str(item["user"])
        elif "uploader" in item:
            # Alternative uploader field
            result["artist"] = str(item["uploader"])

        # Extract album with platform-specific handling
        if "album" in actual_item:
            if isinstance(actual_item["album"], dict):
                result["album"] = actual_item["album"].get(
                    "title",
                    actual_item["album"].get("name", str(actual_item["album"])),
                )
            else:
                result["album"] = str(actual_item["album"])
        elif platform == "soundcloud":
            # SoundCloud doesn't typically have albums, but check for playlist or publisher info
            if "publisher_metadata" in actual_item and isinstance(
                actual_item["publisher_metadata"], dict
            ):
                album_title = actual_item["publisher_metadata"].get("album_title")
                if album_title:
                    result["album"] = str(album_title)
            elif "playlist" in actual_item and isinstance(
                actual_item["playlist"], dict
            ):
                playlist_title = actual_item["playlist"].get("title")
                if playlist_title:
                    result["album"] = str(playlist_title)

        # Extract duration with platform-specific handling
        if "duration" in actual_item:
            duration = actual_item["duration"]
            if isinstance(duration, int | float):
                # SoundCloud duration is in milliseconds, others in seconds
                if (
                    platform == "soundcloud" and duration > 10000
                ):  # Likely milliseconds
                    result["duration"] = int(duration / 1000)
                else:
                    result["duration"] = int(duration)
            else:
                result["duration"] = 0
        else:
            result["duration"] = 0

        # Extract ID and generate URL
        if "id" in actual_item:
            result["id"] = str(actual_item["id"])

            # For SoundCloud, use permalink_url if available, otherwise generate URL
            if platform == "soundcloud" and "permalink_url" in actual_item:
                result["url"] = str(actual_item["permalink_url"])
            else:
                result["url"] = _generate_platform_url_inline(
                    platform, search_type, result["id"]
                )

        # Extract cover/thumbnail URLs for inline search
        cover_url = _extract_cover_url_inline(actual_item, platform, search_type)
        if cover_url:
            result["cover_url"] = cover_url
            result["thumbnail_url"] = cover_url

        # Enhanced fallback for missing metadata
        if result["title"] == "Unknown":
            # Try alternative title fields
            for title_field in ["name", "track_title", "song_title"]:
                if actual_item.get(title_field):
                    result["title"] = str(actual_item[title_field])
                    break

            # If still unknown, try any field that might contain a title
            if result["title"] == "Unknown":
                for key, value in actual_item.items():
                    if key.lower() in ["title", "name", "track", "song"] and value:
                        result["title"] = str(value)
                        break

        if result["artist"] == "Unknown Artist":
            # Try alternative artist fields
            for artist_field in ["artist_name", "performer_name", "creator_name"]:
                if actual_item.get(artist_field):
                    result["artist"] = str(actual_item[artist_field])
                    break

            # If still unknown, try any field that might contain an artist
            if result["artist"] == "Unknown Artist":
                for key, value in actual_item.items():
                    if (
                        key.lower()
                        in ["artist", "performer", "creator", "author", "singer"]
                        and value
                    ):
                        if isinstance(value, dict) and "name" in value:
                            result["artist"] = str(value["name"])
                        elif isinstance(value, str):
                            result["artist"] = str(value)
                        break

        return result

    except Exception as e:
        LOGGER.warning(f"Failed to extract result from {platform}: {e}")
        return None


def _extract_cover_url_inline(item, platform, search_type):
    """Extract cover/thumbnail URL from API response for inline search."""
    try:
        cover_url = ""

        if platform == "qobuz":
            # Qobuz cover URL patterns
            if "image" in item:
                if isinstance(item["image"], dict):
                    # Try different size variants (prefer larger sizes)
                    for size in ["large", "medium", "small", "thumbnail"]:
                        if size in item["image"] and item["image"][size]:
                            cover_url = item["image"][size]
                            break
                    # Fallback to any available image URL
                    if not cover_url:
                        for value in item["image"].values():
                            if isinstance(value, str) and value.startswith("http"):
                                cover_url = value
                                break
                elif isinstance(item["image"], str):
                    cover_url = item["image"]

            # Alternative Qobuz fields
            if not cover_url:
                for field in ["cover", "cover_url", "artwork_url", "picture"]:
                    if item.get(field):
                        cover_url = str(item[field])
                        break

            # For albums, try album image
            if not cover_url and "album" in item and isinstance(item["album"], dict):
                album_image = item["album"].get("image")
                if isinstance(album_image, dict):
                    for size in ["large", "medium", "small"]:
                        if album_image.get(size):
                            cover_url = album_image[size]
                            break
                elif isinstance(album_image, str):
                    cover_url = album_image

        elif platform == "tidal":
            # Tidal cover URL patterns
            if "cover" in item:
                cover_id = item["cover"]
                if cover_id:
                    # Tidal cover URL format: https://resources.tidal.com/images/{cover_id}/1280x1280.jpg
                    cover_url = f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/1280x1280.jpg"

            # Alternative Tidal fields
            if not cover_url:
                for field in ["image", "picture", "artwork_url", "cover_url"]:
                    if item.get(field):
                        cover_url = str(item[field])
                        break

            # For albums, try album cover
            if not cover_url and "album" in item and isinstance(item["album"], dict):
                album_cover = item["album"].get("cover")
                if album_cover:
                    cover_url = f"https://resources.tidal.com/images/{album_cover.replace('-', '/')}/1280x1280.jpg"

        elif platform == "deezer":
            # Deezer cover URL patterns
            for field in [
                "picture",
                "picture_medium",
                "picture_big",
                "picture_small",
                "cover",
                "cover_medium",
                "cover_big",
            ]:
                if item.get(field):
                    cover_url = str(item[field])
                    break

            # For albums, try album picture
            if not cover_url and "album" in item and isinstance(item["album"], dict):
                for field in ["picture", "picture_medium", "picture_big", "cover"]:
                    if item["album"].get(field):
                        cover_url = str(item["album"][field])
                        break

            # For artists, try artist picture
            if not cover_url and search_type == "artist" and "picture" in item:
                cover_url = str(item["picture"])

        elif platform == "soundcloud":
            # Enhanced SoundCloud artwork URL patterns for inline search
            # Method 1: Direct artwork_url field
            if item.get("artwork_url"):
                cover_url = str(item["artwork_url"])

            # Method 2: Try user avatar if no artwork
            if not cover_url and "user" in item and isinstance(item["user"], dict):
                user_obj = item["user"]

                for avatar_field in ["avatar_url", "avatar", "picture", "image"]:
                    if user_obj.get(avatar_field):
                        cover_url = str(user_obj[avatar_field])
                        break

            # Method 3: Try other image fields
            if not cover_url:
                for field in [
                    "avatar_url",
                    "picture",
                    "image",
                    "thumbnail",
                    "waveform_url",
                ]:
                    if item.get(field):
                        cover_url = str(item[field])
                        break

            # Method 4: Try nested fields
            if not cover_url:
                nested_fields = [
                    "user.avatar_url",
                    "user.picture",
                    "media.artwork_url",
                ]
                for nested_field in nested_fields:
                    parts = nested_field.split(".")
                    value = item
                    for part in parts:
                        if isinstance(value, dict) and part in value:
                            value = value[part]
                        else:
                            value = None
                            break
                    if value and isinstance(value, str) and value.startswith("http"):
                        cover_url = value
                        break

            # SoundCloud URL quality enhancement
            if cover_url:
                # Upgrade to higher quality variants
                if "large.jpg" in cover_url:
                    cover_url = cover_url.replace("large.jpg", "t500x500.jpg")
                elif "t300x300" in cover_url:
                    cover_url = cover_url.replace("t300x300", "t500x500")
                elif "small.jpg" in cover_url:
                    cover_url = cover_url.replace("small.jpg", "t500x500.jpg")
                elif "tiny.jpg" in cover_url:
                    cover_url = cover_url.replace("tiny.jpg", "t500x500.jpg")

        # Generic fallback for any platform
        if not cover_url:
            for field in [
                "image",
                "picture",
                "cover",
                "artwork",
                "thumbnail",
                "avatar",
                "photo",
            ]:
                if item.get(field):
                    field_value = item[field]
                    if isinstance(field_value, str) and field_value.startswith(
                        "http"
                    ):
                        cover_url = field_value
                        break
                    if isinstance(field_value, dict):
                        # Try to find URL in nested object
                        for value in field_value.values():
                            if isinstance(value, str) and value.startswith("http"):
                                cover_url = value
                                break
                        if cover_url:
                            break

        return cover_url

    except Exception as e:
        LOGGER.warning(f"Failed to extract cover URL from {platform} (inline): {e}")
        return ""


def _generate_platform_url_inline(platform, media_type, media_id):
    """Generate platform URL for inline search results."""
    url_templates = {
        "qobuz": {
            "track": f"https://www.qobuz.com/track/{media_id}",
            "album": f"https://www.qobuz.com/album/{media_id}",
            "artist": f"https://www.qobuz.com/artist/{media_id}",
            "playlist": f"https://www.qobuz.com/playlist/{media_id}",
        },
        "tidal": {
            "track": f"https://listen.tidal.com/track/{media_id}",
            "album": f"https://listen.tidal.com/album/{media_id}",
            "artist": f"https://listen.tidal.com/artist/{media_id}",
            "playlist": f"https://listen.tidal.com/playlist/{media_id}",
        },
        "deezer": {
            "track": f"https://www.deezer.com/track/{media_id}",
            "album": f"https://www.deezer.com/album/{media_id}",
            "artist": f"https://www.deezer.com/artist/{media_id}",
            "playlist": f"https://www.deezer.com/playlist/{media_id}",
        },
        "soundcloud": {
            "track": f"https://soundcloud.com/user/{media_id}",  # Note: SoundCloud uses permalink_url in practice
            "playlist": f"https://soundcloud.com/user/sets/{media_id}",
        },
    }

    return url_templates.get(platform, {}).get(
        media_type, f"https://{platform}.com/{media_type}/{media_id}"
    )


async def inline_streamrip_search(_, inline_query: InlineQuery):
    """Handle inline queries for streamrip search."""
    # Initialize streamrip on-demand
    from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
        ensure_streamrip_initialized,
    )

    if not await ensure_streamrip_initialized():
        LOGGER.warning("Streamrip initialization failed")
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="disabled",
                    title="Streamrip search is unavailable",
                    description="Streamrip could not be initialized or is not configured",
                    input_message_content=InputTextMessageContent(
                        "🎵 Streamrip search is currently unavailable. Please check configuration."
                    ),
                )
            ],
            cache_time=300,
        )
        return

    # Skip empty queries
    if not inline_query.query:
        # Import and use the comprehensive help guide
        from bot.helper.inline_search_router import get_comprehensive_help_text

        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="help",
                    title="🎵 Search music on streaming platforms",
                    description="Type a search query to find music",
                    input_message_content=InputTextMessageContent(
                        get_comprehensive_help_text()
                    ),
                )
            ],
            cache_time=300,
        )
        return

    # Parse query for platform and media type filters
    query = inline_query.query.strip()
    platform = None
    media_type = None

    # Implement debouncing: require minimum query length to prevent searches on every character
    if len(query) < 3:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="short_query",
                    title="⏳ Keep typing...",
                    description=f"Type at least 3 characters to search (current: {len(query)})",
                    input_message_content=InputTextMessageContent(
                        f"⏳ **Keep typing...**\n\nType at least 3 characters to search.\n\nCurrent query: `{query}` ({len(query)} characters)"
                    ),
                )
            ],
            cache_time=1,  # Very short cache for typing feedback
        )
        return

    # Import debouncing function from inline search router
    from bot.helper.inline_search_router import should_debounce_query

    # Check for query debouncing to prevent rapid-fire requests
    if should_debounce_query(query):
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="debounce",
                    title="⏳ Please wait...",
                    description="Searching too fast. Please wait a moment.",
                    input_message_content=InputTextMessageContent(
                        "⏳ **Please wait...**\n\nYou're searching too fast. Please wait a moment before trying again."
                    ),
                )
            ],
            cache_time=1,
        )
        return

    # Check for multiple filters (platform:type:query or type:platform:query)
    platform = None
    media_type = None
    if ":" in query:
        parts = query.split(":", 2)  # Split into max 3 parts

        for part in parts[
            :-1
        ]:  # Check all parts except the last (which is the query)
            part = part.lower().strip()

            if part in ["qobuz", "tidal", "deezer", "soundcloud"] and not platform:
                platform = part
            elif part in ["track", "album", "playlist", "artist"] and not media_type:
                media_type = part

        # The remaining part is the actual query
        if len(parts) >= 2:
            query = parts[-1].strip()  # Last part is always the query

    # If query is empty after parsing, show help
    if not query:
        LOGGER.warning(
            f"Empty query after parsing. Platform: {platform}, Type: {media_type}"
        )
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="empty_query",
                    title="Please provide a search query",
                    description=f"Type your search query after {platform or media_type}:",
                    input_message_content=InputTextMessageContent(
                        f"Please provide a search query after {platform or media_type}:"
                    ),
                )
            ],
            cache_time=5,
        )
        return

    try:
        # Note: Removed blocking "Please wait while we search music platforms" message
        # Streamrip platform-specific search now sends results directly

        # Perform search without timeout - let it complete naturally
        # Use asyncio.shield to prevent cancellation and ensure completion
        results = await asyncio.shield(
            perform_inline_streamrip_search(
                query, platform, media_type, inline_query.from_user.id
            )
        )

        if not results:
            LOGGER.warning(f"No results found for query '{query}'")
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="no_results",
                        title="No music found",
                        description=f"No results found for: {query}",
                        input_message_content=InputTextMessageContent(
                            f"🎵 No music found matching: <code>{query}</code>\n\n"
                            "💡 Try different keywords or check spelling."
                        ),
                    )
                ],
                cache_time=30,
            )
            return

        # Format results for inline query (Telegram limit: 50 results)
        min(len(results), 50)  # Telegram's inline result limit
        inline_results = []

        # Add info result if we have more than 50 results
        if len(results) > 50:
            inline_results.append(
                InlineQueryResultArticle(
                    id="info_limit",
                    title=f"📊 Found {len(results)} results",
                    description="Showing top 50 results (Telegram limit). Refine your search for better results.",
                    input_message_content=InputTextMessageContent(
                        f"🔍 <b>Search Results</b>\n\n"
                        f"📊 Found <b>{len(results)}</b> total results\n"
                        f"📋 Showing top <b>50</b> results (Telegram limit)\n\n"
                        f"💡 <i>Tip: Use more specific keywords to get better results</i>"
                    ),
                )
            )

        for i, result in enumerate(
            results[: 49 if len(results) > 50 else 50]
        ):  # Reserve 1 slot for info if needed
            # Create result ID
            result_id = f"sr_{i}_{int(time_module.time())}"

            # Format title and description
            title = result.get("title", "Unknown")
            artist = result.get("artist", "")
            platform_name = result.get("platform", "").title()
            media_type_name = result.get("type", "track").title()

            # Platform emoji
            platform_emoji = {
                "qobuz": "🟦",
                "tidal": "⚫",
                "deezer": "🟣",
                "soundcloud": "🟠",
            }.get(result.get("platform", ""), "🎵")

            # Type emoji
            type_emoji = {
                "track": "🎵",
                "album": "💿",
                "playlist": "📋",
                "artist": "👤",
            }.get(result.get("type", "track"), "🎵")

            display_title = f"{platform_emoji} {title}"
            if artist:
                display_title += f" - {artist}"

            description = f"{type_emoji} {media_type_name} on {platform_name}"
            if result.get("duration"):
                minutes = result["duration"] // 60
                seconds = result["duration"] % 60
                description += f" • {minutes}:{seconds:02d}"

            # Store result data for retrieval
            result_data = {
                "url": result.get("url", ""),
                "platform": result.get("platform", ""),
                "type": result.get("type", "track"),
                "title": title,
                "artist": artist,
                "query": query,
            }

            # Create encrypted ID for callback data
            encrypted_id = encrypt_streamrip_data(str(result_data))
            callback_data = f"streamrip_dl_{encrypted_id}"

            # Check callback data length (Telegram limit is 64 bytes)
            if len(callback_data) > 64:
                LOGGER.warning(
                    f"Callback data too long ({len(callback_data)} bytes): {callback_data}"
                )
                # Truncate if necessary (this shouldn't happen with our short IDs)
                callback_data = callback_data[:64]

            # Create message content - this will be sent when user clicks the inline result
            message_text = f"🎵 <b>{title}</b>\n"
            if artist:
                message_text += f"👤 <b>Artist:</b> {artist}\n"
            if result.get("album"):
                message_text += f"💿 <b>Album:</b> {result['album']}\n"
            message_text += f"🎧 <b>Platform:</b> {platform_name}\n"
            message_text += f"📁 <b>Type:</b> {media_type_name}\n\n"
            message_text += "⏳ <i>Preparing quality selection...</i>"

            # Create reply markup with URL button that will trigger quality selector in private message
            # This ensures users get quality selection in private message instead of spamming groups
            start_command = f"streamrip_{encrypted_id}"

            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=f"🎵 Download {media_type_name}",
                            url=f"https://t.me/{TgClient.NAME}?start={start_command}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔍 Search Again",
                            switch_inline_query_current_chat="",
                        )
                    ],
                ]
            )

            # Add thumbnail support for streamrip inline results
            thumbnail_url = result.get("cover_url") or result.get("thumbnail_url")

            # Create inline result with thumbnail if available
            inline_result_params = {
                "id": result_id,
                "title": display_title,
                "description": description,
                "input_message_content": InputTextMessageContent(message_text),
                "reply_markup": reply_markup,
            }

            # Add thumbnail if available (Pyrogram uses 'thumb_url')
            if thumbnail_url and thumbnail_url.startswith("http"):
                inline_result_params["thumb_url"] = thumbnail_url

            inline_results.append(InlineQueryResultArticle(**inline_result_params))

        # Answer the inline query with timeout protection
        try:
            await asyncio.wait_for(
                inline_query.answer(
                    results=inline_results,
                    cache_time=300,  # Cache for 5 minutes
                    is_personal=True,
                ),
                timeout=10.0,  # 10 second timeout for sending results
            )
        except TimeoutError:
            LOGGER.warning("Timeout while sending inline query results")
            # Try to send a simple timeout message
            try:
                await asyncio.wait_for(
                    inline_query.answer(
                        results=[
                            InlineQueryResultArticle(
                                id="send_timeout",
                                title="⏰ Response Timeout",
                                description="Results took too long to send. Please try again.",
                                input_message_content=InputTextMessageContent(
                                    "⏰ **Response Timeout**\n\nResults took too long to send. Please try searching again."
                                ),
                            )
                        ],
                        cache_time=5,
                    ),
                    timeout=5.0,
                )
            except Exception:
                pass  # If we can't even send timeout message, just give up
            return

    except TimeoutError:
        LOGGER.warning("Search timed out")
        # Send timeout message with suggestion to use regular search
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="timeout",
                    title="⏰ Search Timeout",
                    description=f"Search for '{query}' took too long. Try a more specific query or use /srs command.",
                    input_message_content=InputTextMessageContent(
                        f"⏰ **Search Timeout**\n\nSearch for '{query}' took too long for inline mode.\n\n💡 **Try:**\n• More specific search terms\n• Use `/srs {query}` command instead\n• Search for specific artists or albums"
                    ),
                )
            ],
            cache_time=0,
        )

    except Exception as e:
        error_msg = str(e)
        LOGGER.error(f"Error in inline streamrip search: {error_msg}")

        # Handle specific Telegram errors
        if (
            "QUERY_ID_INVALID" in error_msg
            or "query id is invalid" in error_msg.lower()
        ):
            LOGGER.warning("Query ID invalid - user typed too fast or query expired")
            # Don't try to answer an invalid query - it will just cause more errors
            return
        if "QUERY_TOO_OLD" in error_msg or "query too old" in error_msg.lower():
            LOGGER.warning("Query too old - search took too long")
            return
        if "Connection lost" in error_msg or "SSL shutdown timed out" in error_msg:
            LOGGER.warning("Connection lost during search - network issue")
            return
        if "Connector is closed" in error_msg or "Session is closed" in error_msg:
            LOGGER.warning("Session closed during search - connection issue")
            return

        # Try to answer with error message for other errors (with timeout protection)
        try:
            await asyncio.wait_for(
                inline_query.answer(
                    results=[
                        InlineQueryResultArticle(
                            id="error",
                            title="🔍 Search Error",
                            description="An error occurred while searching",
                            input_message_content=InputTextMessageContent(
                                f"❌ **Search Error**\n\n{error_msg}\n\n💡 Please try again with different keywords."
                            ),
                        )
                    ],
                    cache_time=5,
                ),
                timeout=5.0,  # 5 second timeout for error response
            )
        except TimeoutError:
            LOGGER.warning("Timeout while sending error response to inline query")
            return
        except Exception as answer_error:
            LOGGER.warning(f"Failed to answer error query: {answer_error}")
            # If we can't answer the query, just log and return
            return


async def handle_streamrip_callback(_, callback_query):
    """Handle callback queries for streamrip inline search results."""
    try:
        # Check if this is a quality selector callback
        callback_data = callback_query.data
        if callback_data.startswith("srq"):
            # Check if there's an active quality selector for this user
            from bot.helper.mirror_leech_utils.streamrip_utils.quality_selector import (
                get_active_quality_selector,
            )

            quality_selector = get_active_quality_selector(
                callback_query.from_user.id
            )

            if quality_selector:
                # Process the callback through the quality selector
                await quality_selector._handle_callback(
                    _, callback_query, quality_selector
                )
                return

            LOGGER.warning(
                f"No active quality selector found for user {callback_query.from_user.id}"
            )
            await callback_query.answer(
                "❌ Quality selection session expired. Please try again.",
                show_alert=True,
            )
            return

        # Extract callback data for streamrip downloads
        if not callback_data.startswith("streamrip_dl_"):
            LOGGER.warning(f"Invalid callback data format: {callback_data}")
            return

        # Get the encrypted ID
        encrypted_id = callback_data.replace("streamrip_dl_", "")

        # Decrypt the result data
        result_data_str = decrypt_streamrip_data(encrypted_id)

        if result_data_str == encrypted_id:  # Decryption failed
            LOGGER.error("Decryption failed for callback data")
            await callback_query.answer(
                "❌ Invalid or expired link. Please search again.", show_alert=True
            )
            return

        # Parse the result data
        try:
            import ast

            result_data = ast.literal_eval(result_data_str)
        except (ValueError, SyntaxError) as e:
            LOGGER.error(f"Failed to parse streamrip result data: {e}")
            await callback_query.answer(
                "❌ Invalid result data. Please search again.", show_alert=True
            )
            return

        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            await callback_query.answer(
                "❌ Streamrip downloads are disabled!", show_alert=True
            )
            return

        # Extract data
        url = result_data.get("url", "")
        platform = result_data.get("platform", "")
        media_type = result_data.get("type", "track")

        if not url:
            await callback_query.answer(
                "❌ Invalid download URL. Please search again.", show_alert=True
            )
            return

        # Answer the callback query silently (no popup message)
        await callback_query.answer()

        # For inline callbacks, we need to create a fake message object
        # since callback_query.message is None for inline results
        if not callback_query.message:
            # Create a minimal message-like object for the listener
            from types import SimpleNamespace

            fake_message = SimpleNamespace()
            fake_message.from_user = callback_query.from_user
            fake_message.chat = SimpleNamespace()
            fake_message.chat.id = (
                callback_query.from_user.id
            )  # Use user's private chat

            # Create a proper chat type object with .name attribute
            fake_chat_type = SimpleNamespace()
            fake_chat_type.name = "PRIVATE"
            fake_message.chat.type = fake_chat_type

            fake_message.id = 0  # Dummy message ID
            fake_message.reply_to_message = None
            fake_message.sender_chat = None  # Required by StreamripListener

            # Add missing attributes for streamrip listener compatibility
            from datetime import datetime

            fake_message.date = (
                datetime.now()
            )  # Required for elapsed time calculation
            fake_message.text = "🎵 Streamrip download from inline search"  # Required for message text access

            # Add delete method to prevent errors in error handler
            async def fake_delete():
                """Fake delete method that does nothing"""
                return True

            fake_message.delete = fake_delete

            # Add reply method to fake message so quality selector can send messages
            async def fake_reply(
                text,
                quote=None,
                disable_web_page_preview=True,
                disable_notification=True,
                reply_markup=None,
                parse_mode=None,
            ):
                """Fake reply method that sends message to user's private chat"""
                return await TgClient.bot.send_message(
                    chat_id=callback_query.from_user.id,
                    text=text,
                    disable_web_page_preview=disable_web_page_preview,
                    disable_notification=disable_notification,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )

            fake_message.reply = fake_reply

            # Add media reply methods for telegram uploader compatibility
            async def fake_reply_audio(
                audio,
                quote=None,
                caption=None,
                duration=None,
                performer=None,
                title=None,
                thumb=None,
                disable_notification=True,
                progress=None,
                parse_mode=None,
            ):
                """Fake reply_audio method that sends audio to user's private chat"""
                return await TgClient.bot.send_audio(
                    chat_id=callback_query.from_user.id,
                    audio=audio,
                    caption=caption,
                    duration=duration,
                    performer=performer,
                    title=title,
                    thumb=thumb,
                    disable_notification=disable_notification,
                    progress=progress,
                    parse_mode=parse_mode,
                )

            async def fake_reply_video(
                video,
                quote=None,
                caption=None,
                duration=None,
                width=None,
                height=None,
                thumb=None,
                supports_streaming=True,
                disable_notification=True,
                progress=None,
                parse_mode=None,
            ):
                """Fake reply_video method that sends video to user's private chat"""
                return await TgClient.bot.send_video(
                    chat_id=callback_query.from_user.id,
                    video=video,
                    caption=caption,
                    duration=duration,
                    width=width,
                    height=height,
                    thumb=thumb,
                    supports_streaming=supports_streaming,
                    disable_notification=disable_notification,
                    progress=progress,
                    parse_mode=parse_mode,
                )

            async def fake_reply_document(
                document,
                quote=None,
                thumb=None,
                caption=None,
                force_document=True,
                disable_notification=True,
                progress=None,
                parse_mode=None,
            ):
                """Fake reply_document method that sends document to user's private chat"""
                return await TgClient.bot.send_document(
                    chat_id=callback_query.from_user.id,
                    document=document,
                    thumb=thumb,
                    caption=caption,
                    force_document=force_document,
                    disable_notification=disable_notification,
                    progress=progress,
                    parse_mode=parse_mode,
                )

            async def fake_reply_photo(
                photo,
                quote=None,
                caption=None,
                disable_notification=True,
                progress=None,
                parse_mode=None,
            ):
                """Fake reply_photo method that sends photo to user's private chat"""
                return await TgClient.bot.send_photo(
                    chat_id=callback_query.from_user.id,
                    photo=photo,
                    caption=caption,
                    disable_notification=disable_notification,
                    progress=progress,
                    parse_mode=parse_mode,
                )

            fake_message.reply_audio = fake_reply_audio
            fake_message.reply_video = fake_reply_video
            fake_message.reply_document = fake_reply_document
            fake_message.reply_photo = fake_reply_photo
            message_for_listener = fake_message

        else:
            # Use the callback query message but ensure it has the right user
            message_for_listener = callback_query.message
            # Set the from_user to the callback query user (the person who clicked)
            message_for_listener.from_user = callback_query.from_user

        # Create listener for download
        from bot.helper.listeners.streamrip_listener import StreamripListener

        listener = StreamripListener(message_for_listener, isLeech=True)

        # Set platform and media_type attributes for telegram uploader
        listener.platform = platform
        listener.media_type = media_type

        # Show quality selector
        from bot.helper.mirror_leech_utils.streamrip_utils.quality_selector import (
            show_quality_selector,
        )

        selection = await show_quality_selector(listener, platform, media_type)

        if not selection:
            return

        quality = selection["quality"]
        codec = selection["codec"]

        # Start download
        from bot.helper.mirror_leech_utils.download_utils.streamrip_download import (
            add_streamrip_download,
        )

        await add_streamrip_download(listener, url, quality, codec, False)

    except Exception as e:
        LOGGER.error(f"Error in streamrip callback handler: {e}")
        with contextlib.suppress(Exception):
            await callback_query.answer(f"❌ Error: {e!s}", show_alert=True)


async def handle_streamrip_start_command(client, message):
    """Handle start commands for streamrip downloads from inline search results."""
    try:
        # Initialize streamrip on-demand
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            ensure_streamrip_initialized,
        )

        if not await ensure_streamrip_initialized():
            await send_message(
                message,
                "❌ Streamrip is not available or not configured properly.",
            )
            return

        # Extract the encrypted ID from the start command
        if len(message.command) < 2 or not message.command[1].startswith(
            "streamrip_"
        ):
            await send_message(
                message,
                "❌ Invalid streamrip start command format.",
            )
            return

        # Get the encrypted ID
        encrypted_id = message.command[1].replace("streamrip_", "")

        # Decrypt the result data
        result_data_str = decrypt_streamrip_data(encrypted_id)

        if result_data_str == encrypted_id:  # Decryption failed
            LOGGER.error("Decryption failed for start command data")
            await send_message(
                message,
                "❌ Invalid or expired link. Please search again.",
            )
            return

        # Parse the result data
        try:
            import ast

            result_data = ast.literal_eval(result_data_str)
        except (ValueError, SyntaxError) as e:
            LOGGER.error(f"Failed to parse streamrip result data: {e}")
            await send_message(
                message,
                "❌ Invalid result data. Please search again.",
            )
            return

        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            await send_message(
                message,
                "❌ Streamrip downloads are disabled!",
            )
            return

        # Extract data
        url = result_data.get("url", "")
        platform = result_data.get("platform", "")
        media_type = result_data.get("type", "track")
        title = result_data.get("title", "Unknown")
        artist = result_data.get("artist", "Unknown")

        if not url:
            await send_message(
                message,
                "❌ Invalid download URL. Please search again.",
            )
            return

        # Send initial message with track info and start command
        start_command = f"/start streamrip_{encrypted_id}"
        info_msg = "<b>🎵 Streamrip Download</b>\n\n"
        info_msg += f"<code>{start_command}</code>\n\n"
        info_msg += f"🎵 <b>{title}</b>\n"
        if artist:
            info_msg += f"👤 <b>Artist:</b> {artist}\n"
        info_msg += f"🎧 <b>Platform:</b> {platform.title()}\n"
        info_msg += f"📁 <b>Type:</b> {media_type.title()}\n\n"
        info_msg += "⏳ <i>Preparing quality selection...</i>"

        status_msg = await send_message(message, info_msg)

        # Create listener for download
        from bot.helper.listeners.streamrip_listener import StreamripListener

        listener = StreamripListener(message, isLeech=True)

        # Set platform and media_type attributes for telegram uploader
        listener.platform = platform
        listener.media_type = media_type

        # Show quality selector
        from bot.helper.mirror_leech_utils.streamrip_utils.quality_selector import (
            show_quality_selector,
        )

        selection = await show_quality_selector(listener, platform, media_type)

        if not selection:
            # Update status message to show cancellation
            cancel_msg = "<b>🎵 Streamrip Download</b>\n\n"
            cancel_msg += f"<code>{start_command}</code>\n\n"
            cancel_msg += f"🎵 <b>{title}</b>\n"
            if artist:
                cancel_msg += f"👤 <b>Artist:</b> {artist}\n"
            cancel_msg += f"🎧 <b>Platform:</b> {platform.title()}\n"
            cancel_msg += f"📁 <b>Type:</b> {media_type.title()}\n\n"
            cancel_msg += "❌ <i>Quality selection cancelled.</i>"

            await edit_message(status_msg, cancel_msg)
            return

        quality = selection["quality"]
        codec = selection["codec"]

        # Update status message to show download starting
        download_msg = "<b>🎵 Streamrip Download</b>\n\n"
        download_msg += f"<code>{start_command}</code>\n\n"
        download_msg += f"🎵 <b>{title}</b>\n"
        if artist:
            download_msg += f"👤 <b>Artist:</b> {artist}\n"
        download_msg += f"🎧 <b>Platform:</b> {platform.title()}\n"
        download_msg += f"📁 <b>Type:</b> {media_type.title()}\n\n"
        download_msg += f"🚀 <i>Starting download with {quality} quality...</i>"

        await edit_message(status_msg, download_msg)

        # Start download
        from bot.helper.mirror_leech_utils.download_utils.streamrip_download import (
            add_streamrip_download,
        )

        await add_streamrip_download(listener, url, quality, codec, False)

    except Exception as e:
        LOGGER.error(f"Error in streamrip start command handler: {e}")
        await send_message(
            message,
            f"❌ Error: {e!s}",
        )


def init_streamrip_inline_search(bot, register_inline=True):
    """Initialize streamrip inline search handlers."""
    if not Config.STREAMRIP_ENABLED:
        LOGGER.warning(
            "Streamrip is disabled, skipping inline search initialization"
        )
        return

    from pyrogram import filters as pyrogram_filters
    from pyrogram.handlers import CallbackQueryHandler, InlineQueryHandler

    # Register streamrip inline query handler only if requested
    if register_inline:
        # Create a wrapper to handle task creation and exception handling
        async def safe_inline_streamrip_search(client, inline_query):
            """Wrapper for inline_streamrip_search that handles exceptions properly"""
            try:
                await inline_streamrip_search(client, inline_query)
            except Exception as e:
                error_msg = str(e)
                # Don't log QUERY_ID_INVALID errors as they're expected
                if (
                    "QUERY_ID_INVALID" not in error_msg
                    and "query id is invalid" not in error_msg.lower()
                ):
                    LOGGER.error(
                        f"Unhandled error in inline Streamrip search: {error_msg}"
                    )
                # Don't try to answer if query is invalid
                if (
                    "QUERY_ID_INVALID" in error_msg
                    or "query id is invalid" in error_msg.lower()
                ):
                    return
                # Try to answer with error for other exceptions
                try:
                    await inline_query.answer(
                        results=[
                            InlineQueryResultArticle(
                                id="handler_error",
                                title="🔍 Search Error",
                                description="An unexpected error occurred",
                                input_message_content=InputTextMessageContent(
                                    "❌ **Search Error**\n\nAn unexpected error occurred. Please try again."
                                ),
                            )
                        ],
                        cache_time=5,
                    )
                except Exception:
                    pass  # Ignore errors when trying to answer

        bot.add_handler(InlineQueryHandler(safe_inline_streamrip_search))

    # Register streamrip callback handler for inline results
    async def safe_streamrip_callback(_, callback_query):
        """Wrapper for handle_streamrip_callback that handles exceptions properly"""
        try:
            await handle_streamrip_callback(_, callback_query)
        except Exception as e:
            error_msg = str(e)
            LOGGER.error(f"Error in Streamrip callback handler: {error_msg}")
            try:
                await callback_query.answer(
                    f"❌ Error: {error_msg}", show_alert=True
                )
            except Exception:
                pass  # Ignore errors when trying to answer

    # Create proper filter for streamrip callbacks (including quality selector callbacks)
    streamrip_filter = pyrogram_filters.regex(r"^(streamrip_dl_|srq)")

    bot.add_handler(
        CallbackQueryHandler(safe_streamrip_callback, filters=streamrip_filter),
        group=-1,  # Higher priority than other callback handlers
    )
