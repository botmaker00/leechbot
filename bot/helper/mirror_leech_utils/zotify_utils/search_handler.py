"""
Zotify search functionality for aimleechbot with StreamRip-style UI
"""

import asyncio
import contextlib
import time as time_module

# Lightweight cache for search results
from functools import partial
from typing import Any

from pyrogram import filters as pyrogram_filters
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from zotify import Session

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

# Reduced cache sizes for memory optimization
_search_cache = {}
_cache_timestamps = {}
CACHE_DURATION = 180  # Reduced to 3 minutes
MAX_CACHE_ENTRIES = 30  # Significantly reduced
_thumbnail_cache = {}  # Separate cache for thumbnails
MAX_THUMBNAIL_CACHE = 15  # Limit thumbnail cache

# Persistent Zotify session cache (no timeout - persistent until restart)
_persistent_zotify_session = None
_persistent_zotify_session_status = False


def _get_search_cache(key: str):
    """Get cached search result if still valid"""
    if key in _search_cache and key in _cache_timestamps:
        if time_module.time() - _cache_timestamps[key] < CACHE_DURATION:
            return _search_cache[key]
        # Remove expired cache
        del _search_cache[key]
        del _cache_timestamps[key]
    return None


def _set_search_cache(key: str, value):
    """Set search result in cache with optimized memory management"""
    # Remove oldest entries if cache is full
    while len(_search_cache) >= MAX_CACHE_ENTRIES:
        oldest_key = next(iter(_search_cache))
        del _search_cache[oldest_key]
        _cache_timestamps.pop(oldest_key, None)

    _search_cache[key] = value
    _cache_timestamps[key] = time_module.time()


def _get_thumbnail_cache(key: str):
    """Get cached thumbnail URL"""
    if key in _thumbnail_cache:
        timestamp, url = _thumbnail_cache[key]
        if time_module.time() - timestamp < CACHE_DURATION:
            return url
        del _thumbnail_cache[key]
    return None


def _set_thumbnail_cache(key: str, url: str):
    """Set thumbnail URL in cache"""
    # Limit thumbnail cache size
    if len(_thumbnail_cache) >= MAX_THUMBNAIL_CACHE:
        # Remove oldest 50 entries
        sorted_items = sorted(_thumbnail_cache.items(), key=lambda x: x[1][0])
        for old_key, _ in sorted_items[:50]:
            del _thumbnail_cache[old_key]

    _thumbnail_cache[key] = (time_module.time(), url)


class ZotifySearchHandler:
    """Handles Zotify search operations using the simple session manager"""

    def __init__(self):
        # Use the global simple session manager
        from bot.helper.mirror_leech_utils.zotify_utils.improved_session_manager import (
            simple_session_manager,
        )

        self.session_manager = simple_session_manager

    async def get_session(self) -> Session | None:
        """Get session from the simple session manager"""
        return await self.session_manager.get_session()

    async def search_music(
        self, query: str, categories: list[str] | None = None
    ) -> dict[str, list[dict]]:
        """
        Search for music on Spotify using the simple session manager

        Args:
            query: Search query
            categories: List of content types to search for

        Returns:
            Dictionary with search results by category
        """
        try:
            # Use the simple session manager for search
            results = await self.session_manager.search(query, categories)

            # Format results for compatibility
            formatted_results = {}
            for category, items in results.items():
                formatted_results[category] = await self._format_search_results(
                    items, category
                )

            return formatted_results

        except Exception as e:
            LOGGER.error(f"Zotify search failed: {e}")
            return {}

    async def _format_search_results(
        self, raw_results: list, category: str
    ) -> list[dict]:
        """Format raw search results into standardized format"""
        formatted_results = []

        # Process results in batches to reduce CPU overhead
        batch_size = 15  # Process 15 items at a time
        for i in range(0, len(raw_results), batch_size):
            batch = raw_results[i : i + batch_size]
            for item in batch:
                try:
                    # Validate item type - ensure it's a dictionary
                    if not isinstance(item, dict):
                        LOGGER.warning(
                            f"Invalid item type in raw search results: {type(item)} - {item}"
                        )
                        continue
                    if category == "track":
                        formatted_item = {
                            "id": item.get("id", ""),
                            "name": item.get("name", "Unknown"),
                            "artists": [
                                artist.get("name", "Unknown")
                                for artist in item.get("artists", [])
                            ],
                            "album": item.get("album", {}).get("name", "Unknown"),
                            "duration_ms": item.get("duration_ms", 0),
                            "explicit": item.get("explicit", False),
                            "popularity": item.get("popularity", 0),
                            "preview_url": item.get("preview_url"),
                            "external_urls": item.get("external_urls", {}),
                            "type": "track",
                            # Preserve image data for thumbnails
                            "images": item.get("album", {}).get("images", []),
                            "album_data": item.get(
                                "album", {}
                            ),  # Keep full album data for images
                        }

                    elif category == "album":
                        formatted_item = {
                            "id": item.get("id", ""),
                            "name": item.get("name", "Unknown"),
                            "artists": [
                                artist.get("name", "Unknown")
                                for artist in item.get("artists", [])
                            ],
                            "album_type": item.get("album_type", "album"),
                            "total_tracks": item.get("total_tracks", 0),
                            "release_date": item.get("release_date", ""),
                            "external_urls": item.get("external_urls", {}),
                            "type": "album",
                            # Preserve image data for thumbnails
                            "images": item.get("images", []),
                        }

                    elif category == "playlist":
                        formatted_item = {
                            "id": item.get("id", ""),
                            "name": item.get("name", "Unknown"),
                            "owner": item.get("owner", {}).get(
                                "display_name", "Unknown"
                            ),
                            "description": item.get("description", ""),
                            "total_tracks": item.get("tracks", {}).get("total", 0),
                            "public": item.get("public", False),
                            "external_urls": item.get("external_urls", {}),
                            "type": "playlist",
                            # Preserve image data for thumbnails
                            "images": item.get("images", []),
                            "owner_data": item.get(
                                "owner", {}
                            ),  # Keep owner data for fallback images
                        }

                    elif category == "artist":
                        formatted_item = {
                            "id": item.get("id", ""),
                            "name": item.get("name", "Unknown"),
                            "genres": item.get("genres", []),
                            "popularity": item.get("popularity", 0),
                            "followers": item.get("followers", {}).get("total", 0),
                            "external_urls": item.get("external_urls", {}),
                            "type": "artist",
                            # Preserve image data for thumbnails
                            "images": item.get("images", []),
                        }

                    else:
                        continue

                    formatted_results.append(formatted_item)

                except Exception as e:
                    LOGGER.error(f"Failed to format search result: {e}")
                    continue

            # Yield control to prevent CPU blocking after each batch
            if i + batch_size < len(raw_results):
                import asyncio

                await asyncio.sleep(0)  # Yield to event loop

        return formatted_results

    def create_search_buttons(
        self, results: dict[str, list[dict]], query: str
    ) -> InlineKeyboardMarkup:
        """Create inline keyboard for search results"""
        buttons = ButtonMaker()

        # Add category headers and results
        for category, items in results.items():
            if not items:
                continue

            # Category header
            category_name = category.title() + "s"
            buttons.data_button(f"📁 {category_name}", f"zotify_cat_{category}")

            # Add top results for this category (limit to 5 per category)
            for _i, item in enumerate(items[:5]):
                if category == "track":
                    title = f"🎵 {item['name']} - {', '.join(item['artists'][:2])}"
                elif category == "album":
                    title = f"💿 {item['name']} - {', '.join(item['artists'][:2])}"
                elif category == "playlist":
                    title = f"📋 {item['name']} ({item['total_tracks']} tracks)"
                elif category == "artist":
                    title = f"👤 {item['name']}"
                else:
                    title = item["name"]

                # Truncate long titles
                if len(title) > 50:
                    title = title[:47] + "..."

                callback_data = f"zotify_dl_{category}_{item['id']}"
                buttons.data_button(title, callback_data)

        # Add search again button
        buttons.data_button("🔍 Search Again", f"zotify_search_again_{query}")

        # Add close button
        buttons.data_button("❌ Close", "zotify_close")

        return buttons.build_menu(1)

    def format_search_message(
        self, results: dict[str, list[dict]], query: str
    ) -> str:
        """Format search results into a message"""
        if not any(results.values()):
            return f"❌ No results found for: **{query}**"

        message = f"🔍 **Spotify Search Results for:** `{query}`\n\n"

        total_results = sum(len(items) for items in results.values())
        message += f"📊 **Total Results:** {total_results}\n\n"

        for category, items in results.items():
            if not items:
                continue

            category_name = category.title() + "s"
            message += f"**{category_name}** ({len(items)} found):\n"

            # Show top 3 results per category in message
            for _i, item in enumerate(items[:3]):
                if category == "track":
                    message += (
                        f"🎵 {item['name']} - {', '.join(item['artists'][:2])}\n"
                    )
                elif category == "album":
                    message += (
                        f"💿 {item['name']} - {', '.join(item['artists'][:2])}\n"
                    )
                elif category == "playlist":
                    message += f"📋 {item['name']} ({item['total_tracks']} tracks)\n"
                elif category == "artist":
                    message += f"👤 {item['name']}\n"

            if len(items) > 3:
                message += f"... and {len(items) - 3} more\n"
            message += "\n"

        message += "💡 **Use the buttons below to download or explore results**"
        return message


# Global instance with session limit
zotify_search = ZotifySearchHandler()


# Simple cleanup function
async def cleanup_sessions():
    """Clean up sessions"""
    try:
        from bot.helper.mirror_leech_utils.zotify_utils.improved_session_manager import (
            simple_session_manager,
        )

        await simple_session_manager.close()
    except Exception as e:
        LOGGER.warning(f"Session cleanup error: {e}")


class ZotifySearchInterface:
    """StreamRip-style search interface for Zotify with pagination and enhanced UI"""

    # Platform emojis and type emojis (matching StreamRip)
    PLATFORM_EMOJIS = {"spotify": "🟢"}
    TYPE_EMOJIS = {"track": "🎵", "album": "💿", "playlist": "📋", "artist": "👤"}
    QUALITY_MAP = {"spotify": "OGG Vorbis up to 320kbps"}

    def __init__(
        self,
        listener,
        query: str,
        media_type_filter: str | None = None,
        result_limit: int = 50,
    ):
        self.listener = listener
        self.query = query
        self.media_type_filter = media_type_filter
        self.result_limit = result_limit
        self.search_results = {}
        self.current_page = 0
        self.results_per_page = 5  # Same as StreamRip
        self._reply_to = None
        self._time = time_module.time()
        self._timeout = 300  # 5 minutes for search
        self.event = asyncio.Event()
        self.selected_result = None
        self._cached_all_results = None  # Cache flattened results for O(1) access

    async def search(self) -> dict[str, Any] | None:
        """Perform Zotify search with StreamRip-style UI"""
        try:
            # Check if Zotify is enabled
            if not Config.ZOTIFY_ENABLED:
                await send_message(
                    self.listener.message,
                    f"{self.listener.tag} ❌ <b>Zotify is not enabled!</b>\n\n"
                    f"🎵 <b>Zotify provides:</b>\n"
                    f"🟢 <code>Spotify</code> - OGG Vorbis up to 320kbps\n"
                    f"🎯 <code>Free & Premium</code> accounts supported\n"
                    f"⚡ <code>Native format</code> - no transcoding needed\n\n"
                    f"💡 <i>Configure Zotify credentials to enable search.</i>",
                )
                return None

            # Show beautiful searching message
            search_msg = await send_message(
                self.listener.message,
                f"🔍 <b>Zotify Search</b>\n\n"
                f"🎵 <b>Query:</b> <code>{self.query}</code>\n"
                f"🎯 <b>Platform:</b> 🟢 <code>Spotify</code>\n\n"
                f"⏳ <i>Searching Spotify catalog...</i>\n"
                f"🎶 <i>This may take a few seconds</i>",
            )

            # Perform search
            await self._perform_search()

            # Delete searching message
            await delete_message(search_msg)

            # Check if we have results
            total_results = sum(
                len(results) for results in self.search_results.values()
            )
            if total_results == 0:
                no_results_msg = await send_message(
                    self.listener.message,
                    f"{self.listener.tag} ❌ <b>No results found for:</b> <code>{self.query}</code>\n\n"
                    f"💡 <i>Try a different search query or check your spelling.</i>",
                )
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
            LOGGER.error(f"Zotify search error: {e}")
            error_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} ❌ <b>Search failed:</b>\n\n"
                f"🔍 <i>Query:</i> <code>{self.query}</code>\n"
                f"⚠️ <i>Error:</i> <pre>{e!s}</pre>\n"
                f"💡 <i>Try again or check Zotify configuration.</i>",
            )
            asyncio.create_task(auto_delete_message(error_msg, time=300))
            return None

    async def _perform_search(self):
        """Perform the actual search using Zotify"""
        try:
            # Determine search categories
            if self.media_type_filter:
                categories = [self.media_type_filter]
            else:
                categories = ["track", "album", "playlist", "artist"]

            # Use the existing zotify_search instance
            results = await zotify_search.search_music(self.query, categories)

            # Format results for StreamRip-style display
            for category, items in results.items():
                formatted_results = []
                for item in items[: self.result_limit]:
                    # Convert to StreamRip-style format
                    formatted_item = await self._format_result_for_display(
                        item, category
                    )
                    if formatted_item:
                        formatted_results.append(formatted_item)

                self.search_results[category] = formatted_results

        except Exception as e:
            LOGGER.error(f"Zotify search performance failed: {e}")
            self.search_results = {}

    async def _format_result_for_display(
        self, item: dict, category: str
    ) -> dict | None:
        """Format search result for StreamRip-style display"""
        try:
            # Base format matching StreamRip structure
            formatted = {
                "platform": "spotify",
                "type": category,
                "url": f"https://open.spotify.com/{category}/{item.get('id', '')}",
                "id": item.get("id", ""),
            }

            if category == "track":
                formatted.update(
                    {
                        "title": item.get("name", "Unknown"),
                        "artist": ", ".join(item.get("artists", []))
                        if item.get("artists")
                        else "Unknown",
                        "album": item.get("album", "Unknown"),
                        "duration": self._format_duration_ms(
                            item.get("duration_ms", 0)
                        ),
                        "quality": "OGG Vorbis up to 320kbps",
                    }
                )

            elif category == "album":
                formatted.update(
                    {
                        "title": item.get("name", "Unknown"),
                        "artist": ", ".join(item.get("artists", []))
                        if item.get("artists")
                        else "Unknown",
                        "album": item.get("name", "Unknown"),
                        "duration": f"{item.get('total_tracks', 0)} tracks",
                        "quality": f"Album • {item.get('release_date', 'Unknown')}",
                    }
                )

            elif category == "playlist":
                formatted.update(
                    {
                        "title": item.get("name", "Unknown"),
                        "artist": item.get("owner", "Unknown"),
                        "album": "Playlist",
                        "duration": f"{item.get('total_tracks', 0)} tracks",
                        "quality": "Spotify Playlist",
                    }
                )

            elif category == "artist":
                formatted.update(
                    {
                        "title": item.get("name", "Unknown"),
                        "artist": "Artist",
                        "album": f"{item.get('followers', 0):,} followers",
                        "duration": ", ".join(item.get("genres", [])[:2])
                        or "Various",
                        "quality": "Artist Profile",
                    }
                )

            return formatted

        except Exception as e:
            LOGGER.error(f"Failed to format result: {e}")
            return None

    def _format_duration_ms(self, duration_ms: int) -> str:
        """Format duration from milliseconds to MM:SS"""
        if not duration_ms:
            return "Unknown"

        seconds = duration_ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"

    def _format_duration_from_string(self, duration_str: str) -> str:
        """Format duration from string (MM:SS format) - StreamRip compatibility"""
        if not duration_str or duration_str == "Unknown":
            return "Unknown"

        # If it's already in MM:SS format, return as is
        if ":" in duration_str:
            return duration_str

        # If it's a number, treat as seconds
        try:
            seconds = int(float(duration_str))
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{minutes}:{seconds:02d}"
        except (ValueError, TypeError):
            return duration_str

    async def _show_search_results(self):
        """Show search results with StreamRip-style pagination"""
        buttons = ButtonMaker()

        # Get all results flattened with caching for O(1) subsequent access
        if self._cached_all_results is None:
            self._cached_all_results = []
            for platform, results in self.search_results.items():
                for result in results:
                    # Add platform info to each result
                    result["platform"] = platform
                    self._cached_all_results.append(result)
        all_results = self._cached_all_results

        # Check if we have any results
        total_results = len(all_results)
        if total_results == 0:
            # No results found - show error message instead of empty button menu
            error_msg = f"{self.listener.tag} ❌ <b>No results found for:</b> <code>{self.query}</code>\n\n"
            error_msg += "💡 <i>Try a different search query or check Spotify availability.</i>"

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

        # Build message with beautiful HTML formatting (exactly like StreamRip)
        msg = f"🔍 <b>Search Results for:</b> <code>{self.query}</code>\n"
        msg += f"📊 Found <b>{total_results}</b> results on <b>🟢 Spotify</b>\n"
        msg += f"📄 Page <b>{self.current_page + 1}</b>/<b>{total_pages}</b>\n\n"

        # Show results for current page (exactly like StreamRip)
        for i in range(start_idx, end_idx):
            result = all_results[i]
            result_num = i + 1

            # Format result display with proper truncation (exactly like StreamRip)
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

            platform_emoji = "🟢"  # Spotify emoji
            type_emoji = self.TYPE_EMOJIS.get(result.get("type", "track"), "🎵")

            # Beautiful formatted result with HTML tags (exactly like StreamRip)
            msg += f"<b>{result_num}.</b> {platform_emoji} {type_emoji} <b>{title}</b>\n"
            msg += f"   👤 <i>{artist}</i>"

            if result.get("album") and result["album"] != result["title"]:
                album = (
                    result["album"][:35] + "..."
                    if len(result["album"]) > 35
                    else result["album"]
                )
                msg += f" • 💿 <code>{album}</code>"

            if result.get("duration"):
                duration_str = self._format_duration_from_string(result["duration"])
                msg += f" • ⏱️ <code>{duration_str}</code>"

            # Platform and quality info (exactly like StreamRip)
            quality_info = self.QUALITY_MAP.get(
                result.get("platform", "spotify"), "OGG Vorbis up to 320kbps"
            )
            msg += f" • 🎯 <b>Spotify</b> <pre>{quality_info}</pre>\n\n"

            # Add download button (exactly like StreamRip)
            buttons.data_button(
                f"{result_num}. {type_emoji} {title[:25]}...",
                f"zs select {i}",
                "header",
            )

        # Add pagination buttons (exactly like StreamRip)
        if total_pages > 1:
            nav_buttons = []
            if self.current_page > 0:
                nav_buttons.append(
                    ("⬅️ Previous", f"zs page {self.current_page - 1}")
                )

            nav_buttons.append(
                (f"📄 {self.current_page + 1}/{total_pages}", "zs noop")
            )

            if self.current_page < total_pages - 1:
                nav_buttons.append(("Next ➡️", f"zs page {self.current_page + 1}"))

            for text, data in nav_buttons:
                buttons.data_button(text, data, "footer")

        # Add cancel button
        buttons.data_button("❌ Cancel", "zs cancel", "footer")

        msg += f"⏱️ <b>Timeout:</b> <code>{get_readable_time(self._timeout - (time_module.time() - self._time))}</code>"

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
                filters=pyrogram_filters.regex("^zs")
                & pyrogram_filters.user(self.listener.user_id),
            ),
            group=-1,
        )

        # Wait for event completion
        await self.event.wait()

        # Remove handler with proper error handling
        try:
            self.listener.client.remove_handler(*handler)
        except (ValueError, AttributeError) as e:
            # Handler might have already been removed or doesn't exist
            LOGGER.warning(f"Handler removal failed (likely already removed): {e}")
        except Exception as e:
            LOGGER.warning(f"Unexpected error removing handler: {e}")

    @staticmethod
    async def _handle_callback(_, query, obj):
        """Handle callback query (StreamRip-style)"""
        data = query.data.split()
        await query.answer()

        if data[1] == "select":
            # Get selected result using cached results for O(1) access
            result_idx = int(data[2])
            if obj._cached_all_results is None:
                obj._cached_all_results = []
                for platform, results in obj.search_results.items():
                    for result in results:
                        result["platform"] = platform
                        obj._cached_all_results.append(result)
            all_results = obj._cached_all_results

            if 0 <= result_idx < len(all_results):
                obj.selected_result = all_results[result_idx]

                # Show selection confirmation with beautiful HTML formatting
                result = obj.selected_result
                type_emoji = obj.TYPE_EMOJIS.get(result.get("type", "track"), "🎵")
                platform_emoji = obj.PLATFORM_EMOJIS.get(
                    result.get("platform", "spotify"), "🟢"
                )

                msg = "✅ <b>Selected:</b>\n\n"
                msg += f"{type_emoji} <b>{result['title']}</b>\n"
                msg += f"👤 Artist: <i>{result['artist']}</i>\n"

                if result.get("album") and result["album"] != result["title"]:
                    msg += f"💿 Album: <code>{result['album']}</code>\n"

                if result.get("duration"):
                    msg += f"⏱️ Duration: <code>{result['duration']}</code>\n"

                quality_info = obj.QUALITY_MAP.get(
                    result.get("platform", "spotify"), "OGG Vorbis up to 320kbps"
                )
                msg += f"🎯 Platform: <b>{platform_emoji} {result.get('platform', 'Spotify').title()}</b>\n"
                msg += f"🎧 Quality: <code>{quality_info}</code>\n"
                msg += f"📁 Type: <b>{result['type'].title()}</b>\n\n"
                msg += "🚀 <b>Starting download...</b>"

                # Delete the search results menu immediately (StreamRip-style)
                if obj._reply_to:
                    await delete_message(obj._reply_to)

                # Send confirmation message
                confirmation_msg = await send_message(obj.listener.message, msg)

                # Auto-delete confirmation after 10 seconds
                asyncio.create_task(auto_delete_message(confirmation_msg, time=10))

                obj.event.set()

        elif data[1] == "page":
            # Change page
            new_page = int(data[2])
            obj.current_page = new_page
            await obj._show_search_results()

        elif data[1] == "noop":
            # No operation (page indicator click)
            pass

        elif data[1] == "cancel":
            # Delete the search results menu immediately (StreamRip-style)
            if obj._reply_to:
                await delete_message(obj._reply_to)

            # Send cancellation message
            cancel_msg = await send_message(
                obj.listener.message,
                f"{obj.listener.tag} ❌ <b>Search cancelled!</b>",
            )

            # Auto-delete cancellation message
            asyncio.create_task(auto_delete_message(cancel_msg, time=300))

            obj.listener.is_cancelled = True
            obj.selected_result = None
            obj.event.set()

        else:
            LOGGER.warning(f"Unknown Zotify search callback action: {data[1]}")


# Convenience functions
async def search_music(
    query: str, categories: list[str] | None = None
) -> dict[str, list[dict]]:
    """Search for music using Zotify"""
    try:
        return await zotify_search.search_music(query, categories)
    except Exception as e:
        LOGGER.error(f"Zotify search failed: {e}")
        return {}


async def search_music_auto_first(query: str) -> str | None:
    """Search and return first result URL"""
    results = await search_music(query, ["track"])
    if results.get("track"):
        first_track = results["track"][0]
        return f"https://open.spotify.com/track/{first_track['id']}"
    return None


async def show_zotify_search_interface(
    listener, query: str, media_type_filter: str | None = None
) -> dict[str, Any] | None:
    """Show StreamRip-style search interface for Zotify"""
    search_interface = ZotifySearchInterface(
        listener=listener,
        query=query,
        media_type_filter=media_type_filter,
        result_limit=50,
    )

    return await search_interface.search()


# Inline search functionality
async def perform_inline_zotify_search(
    query: str, media_type: str | None = None, user_id: int | None = None
) -> list[dict]:
    """Perform Zotify search for inline queries with optimized performance and no timeouts"""
    # Performance tracking removed for optimization

    try:
        # Check cache first for faster responses
        cache_key = f"zotify_search_{query}_{media_type}"
        cached_result = _get_search_cache(cache_key)
        if cached_result is not None:
            return cached_result

        # Initialize Zotify on-demand
        from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import (
            ensure_zotify_initialized,
        )

        if not await ensure_zotify_initialized():
            LOGGER.warning("Zotify initialization failed for inline search")
            return []

        # Determine categories based on media_type filter
        if media_type:
            categories = [media_type]
        else:
            # Prioritize tracks and albums for faster results
            categories = ["track", "album", "playlist", "artist"]

        # Perform search with reasonable timeout for inline queries
        try:
            # Use timeout for inline search to prevent hanging
            results = await asyncio.wait_for(
                search_music(query, categories),
                timeout=6.0,  # Reduced to 6 seconds for ultra-fast inline response
            )
        except TimeoutError:
            LOGGER.warning(
                f"Zotify search timed out for query '{query}' after 6 seconds"
            )
            # Cache empty result to prevent repeated timeouts
            _set_search_cache(cache_key, [])
            return []
        except Exception as e:
            LOGGER.error(f"Zotify search error for query '{query}': {e}")
            # Cache empty result to prevent repeated failures
            _set_search_cache(cache_key, [])
            return []

        # Optimized result processing with batch operations
        inline_results = []
        max_results = 50  # Reduced for better performance

        # Pre-allocate list for better memory efficiency
        inline_results = [None] * min(
            sum(len(items) for items in results.values()), max_results
        )
        result_index = 0

        for category, items in results.items():
            if result_index >= max_results:
                break

            # Batch process items for efficiency
            batch_size = min(10, max_results - result_index, len(items))

            # Skip if no more items to process or batch_size is 0
            if batch_size <= 0 or result_index >= max_results:
                break

            for i in range(
                0, min(len(items), max_results - result_index), batch_size
            ):
                batch_items = items[i : i + batch_size]

                for item in batch_items:
                    if result_index >= max_results:
                        break

                    # Validate item type - ensure it's a dictionary
                    if not isinstance(item, dict):
                        LOGGER.warning(
                            f"Invalid item type in search results: {type(item)} - {item}"
                        )
                        continue

                    # Optimized item processing with minimal allocations
                    processed_item = {
                        "type": category,
                        "platform": "spotify",
                        "id": item.get("id", ""),
                        "title": item.get("name", item.get("title", "Unknown")),
                        "url": item.get("url")
                        or f"https://open.spotify.com/{category}/{item.get('id', '')}",
                    }

                    # Handle artists efficiently
                    artists = item.get("artists", [])
                    if isinstance(artists, list):
                        processed_item["artist"] = artists
                    else:
                        processed_item["artist"] = [artists] if artists else []

                    # Add category-specific fields efficiently with safe dictionary access
                    if category == "track":
                        # Safe album name extraction
                        album_info = item.get("album", {})
                        album_name = "Unknown"
                        if isinstance(album_info, dict):
                            album_name = album_info.get("name", "Unknown")
                        elif isinstance(album_info, str):
                            album_name = album_info

                        processed_item.update(
                            {
                                "album": album_name,
                                "duration_ms": item.get("duration_ms", 0),
                                "images": item.get("images", []),
                                "album_data": item.get("album_data", {}),
                            }
                        )
                    elif category == "album":
                        processed_item.update(
                            {
                                "total_tracks": item.get("total_tracks", 0),
                                "release_date": item.get("release_date", ""),
                                "images": item.get("images", []),
                            }
                        )
                    elif category == "playlist":
                        # Safe owner name extraction
                        owner_info = item.get("owner", {})
                        owner_name = "Unknown"
                        if isinstance(owner_info, dict):
                            owner_name = owner_info.get("display_name", "Unknown")
                        elif isinstance(owner_info, str):
                            owner_name = owner_info

                        # Safe tracks total extraction
                        tracks_info = item.get("tracks", {})
                        tracks_total = 0
                        if isinstance(tracks_info, dict):
                            tracks_total = tracks_info.get("total", 0)
                        elif isinstance(tracks_info, int):
                            tracks_total = tracks_info

                        processed_item.update(
                            {
                                "owner": owner_name,
                                "total_tracks": tracks_total,
                                "images": item.get("images", []),
                            }
                        )
                    elif category == "artist":
                        # Safe followers count extraction
                        followers_info = item.get("followers", {})
                        followers_total = 0
                        if isinstance(followers_info, dict):
                            followers_total = followers_info.get("total", 0)
                        elif isinstance(followers_info, int):
                            followers_total = followers_info

                        processed_item.update(
                            {
                                "followers": followers_total,
                                "genres": item.get("genres", []),
                                "images": item.get("images", []),
                            }
                        )

                    # Extract thumbnail efficiently
                    thumbnail_url = _extract_spotify_thumbnail(item, category)
                    if thumbnail_url:
                        processed_item["cover_url"] = thumbnail_url
                        processed_item["thumbnail_url"] = thumbnail_url

                    inline_results[result_index] = processed_item
                    result_index += 1

                # Yield control after each batch
                await asyncio.sleep(0)

        # Trim the pre-allocated list to actual size
        inline_results = inline_results[:result_index]

        # Cache the results for faster subsequent searches
        _set_search_cache(cache_key, inline_results)

        return inline_results

    except Exception as e:
        LOGGER.error(f"Inline Zotify search failed: {e}")
        return []


def _extract_spotify_thumbnail(item, category):
    """Extract thumbnail URL from Spotify API response with optimized caching."""
    try:
        # Validate input - ensure item is a dictionary
        if not isinstance(item, dict):
            LOGGER.warning(
                f"Invalid item type for thumbnail extraction: {type(item)} - {item}"
            )
            return ""

        # Create cache key for this item
        item_id = item.get("id", "")
        cache_key = f"{category}_{item_id}"

        # Check thumbnail cache first
        cached_url = _get_thumbnail_cache(cache_key)
        if cached_url:
            return cached_url

        def get_best_image_url(images_list):
            """Optimized image URL extraction with early returns."""
            if not images_list or not isinstance(images_list, list):
                return None

            # Fast path: if only one image, use it
            if len(images_list) == 1:
                image = images_list[0]
                if isinstance(image, dict) and "url" in image:
                    url = image["url"]
                    if url and url.startswith("http"):
                        return url

            # Optimized search for best image
            medium_image = None
            fallback_image = None

            for image in images_list:
                if not isinstance(image, dict) or "url" not in image:
                    continue

                url = image["url"]
                if not url or not url.startswith("http"):
                    continue

                # Set fallback on first valid URL
                if not fallback_image:
                    fallback_image = url

                # Check for optimal size (early return for perfect match)
                width = image.get("width", 0)
                height = image.get("height", 0)

                if width and height:
                    # Perfect size match - return immediately
                    if 250 <= width <= 350 or 250 <= height <= 350:
                        return url
                    # Good size match - store but continue looking for perfect
                    if 200 <= width <= 400 or 200 <= height <= 400:
                        if not medium_image:
                            medium_image = url

            return medium_image or fallback_image

        # Optimized extraction with early returns and caching
        result_url = None

        # Primary: Check direct images field
        if "images" in item:
            result_url = get_best_image_url(item["images"])
            if result_url:
                _set_thumbnail_cache(cache_key, result_url)
                return result_url

        # For tracks: Check album data (optimized path)
        if category == "track":
            # Check album_data first (most reliable)
            album_data = item.get("album_data")
            if isinstance(album_data, dict):
                result_url = get_best_image_url(album_data.get("images", []))
                if result_url:
                    _set_thumbnail_cache(cache_key, result_url)
                    return result_url

            # Fallback to album field
            album = item.get("album")
            if isinstance(album, dict):
                result_url = get_best_image_url(album.get("images", []))
                if result_url:
                    _set_thumbnail_cache(cache_key, result_url)
                    return result_url

        # For playlists: Check owner data
        elif category == "playlist":
            owner_data = item.get("owner_data")
            if isinstance(owner_data, dict):
                result_url = get_best_image_url(owner_data.get("images", []))
                if result_url:
                    _set_thumbnail_cache(cache_key, result_url)
                    return result_url

        # Fast CDN fallback using Spotify patterns
        spotify_id = item.get("id")
        if spotify_id:
            if category == "track":
                # Try album ID from album_data with safe access
                album_data = item.get("album_data", {})
                album_id = None
                if isinstance(album_data, dict):
                    album_id = album_data.get("id")

                # Fallback to album field with safe access
                if not album_id:
                    album_info = item.get("album", {})
                    if isinstance(album_info, dict):
                        album_id = album_info.get("id")

                if album_id:
                    result_url = f"https://i.scdn.co/image/{album_id}"
            elif category in ["album", "artist"]:
                result_url = f"https://i.scdn.co/image/{spotify_id}"
            elif category == "playlist":
                result_url = f"https://mosaic.scdn.co/300/{spotify_id}"

            if result_url:
                _set_thumbnail_cache(cache_key, result_url)
                return result_url

        # Cache empty result to avoid repeated processing
        _set_thumbnail_cache(cache_key, "")
        return ""

    except Exception as e:
        LOGGER.warning(f"Failed to extract Spotify thumbnail for {category}: {e}")
        # Cache empty result on error
        if "cache_key" in locals():
            _set_thumbnail_cache(cache_key, "")
        return ""


# Simple and robust encryption/decryption for callback data
def encrypt_zotify_data(data: str) -> str:
    """Encrypt data for callback storage - simple base64 with hash verification"""
    try:
        import base64
        import hashlib
        import json

        # Parse the data to extract essential info for compact storage
        try:
            if isinstance(data, str) and data.startswith("{"):
                data_dict = eval(data)
            else:
                data_dict = {"raw": data}
        except:
            data_dict = {"raw": data}

        # Create compact data for Telegram limits
        compact_data = {
            "url": data_dict.get("url", ""),
            "type": data_dict.get("type", "track"),
            "title": data_dict.get("title", "")[:15],  # Shorter for Telegram limits
            "artist": data_dict.get("artist", "")[:10]
            if data_dict.get("artist")
            else "",
        }

        # Convert to JSON string
        json_str = json.dumps(compact_data, separators=(",", ":"))  # Compact JSON

        # Base64 encode
        encoded = base64.b64encode(json_str.encode()).decode()

        # Create verification hash (shorter)
        hash_obj = hashlib.md5(json_str.encode())
        short_hash = hash_obj.hexdigest()[:6]  # 6 character hash

        # Combine with hash for verification
        result = f"{encoded}_{short_hash}"

        # If still too long, use just the essential data
        if len(result) > 50:  # Leave room for "zotify_dl_" prefix
            # Use just URL and type
            minimal_data = {
                "url": data_dict.get("url", ""),
                "type": data_dict.get("type", "track"),
            }
            json_str = json.dumps(minimal_data, separators=(",", ":"))
            encoded = base64.b64encode(json_str.encode()).decode()
            hash_obj = hashlib.md5(json_str.encode())
            short_hash = hash_obj.hexdigest()[:6]
            result = f"{encoded}_{short_hash}"

            # If STILL too long, use just the Spotify ID from URL
            if len(result) > 50:
                url = data_dict.get("url", "")
                if "spotify.com/" in url:
                    # Extract just the Spotify ID
                    spotify_id = url.split("/")[-1].split("?")[0]
                    content_type = data_dict.get("type", "track")
                    result = f"{content_type}_{spotify_id}"

        return result

    except Exception as e:
        LOGGER.error(f"Encryption error: {e}")
        # Fallback to simple hash of URL
        import hashlib

        try:
            if isinstance(data, str) and "url" in data:
                data_dict = eval(data)
                url = data_dict.get("url", "")
                if url:
                    return hashlib.md5(url.encode()).hexdigest()[:12]
        except:
            pass
        return hashlib.md5(str(data).encode()).hexdigest()[:12]


def decrypt_zotify_data(encrypted_data: str) -> str:
    """Decrypt data from callback storage - handles multiple formats"""
    try:
        import base64
        import hashlib
        import json

        # Check if it's the simple format (type_spotifyid)
        if "_" in encrypted_data and not encrypted_data.count("_") > 1:
            # Check if it looks like type_spotifyid format
            parts = encrypted_data.split("_", 1)
            if len(parts) == 2 and parts[0] in [
                "track",
                "album",
                "artist",
                "playlist",
                "show",
                "episode",
            ]:
                content_type, spotify_id = parts
                # Reconstruct the data dict
                data_dict = {
                    "url": f"https://open.spotify.com/{content_type}/{spotify_id}",
                    "type": content_type,
                    "title": "Unknown",
                    "artist": "",
                }
                return str(data_dict)

        # Check if it has hash verification (base64 format)
        if "_" not in encrypted_data:
            LOGGER.error(f"Invalid encrypted data format: {encrypted_data}")
            return encrypted_data

        # Split encoded data and hash
        try:
            encoded_data, stored_hash = encrypted_data.rsplit("_", 1)
        except ValueError:
            LOGGER.error(f"Cannot split encrypted data: {encrypted_data}")
            return encrypted_data

        # Try to decode base64
        try:
            decoded_bytes = base64.b64decode(encoded_data.encode())
            json_str = decoded_bytes.decode()
        except Exception as e:
            LOGGER.error(f"Base64 decode failed: {e}")
            return encrypted_data

        # Verify hash
        hash_obj = hashlib.md5(json_str.encode())
        calculated_hash = hash_obj.hexdigest()[:6]

        if calculated_hash != stored_hash:
            LOGGER.error(f"Hash verification failed for: {encrypted_data}")
            return encrypted_data

        # Parse JSON
        try:
            data_dict = json.loads(json_str)
        except json.JSONDecodeError as e:
            LOGGER.error(f"JSON decode failed: {e}")
            return encrypted_data

        # Convert back to original format
        return str(data_dict)

    except Exception as e:
        LOGGER.error(f"Decryption error: {e}")
        return encrypted_data


async def inline_zotify_search(_, inline_query: InlineQuery):
    """Handle inline queries for Zotify search."""
    # Initialize Zotify on-demand
    from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import (
        ensure_zotify_initialized,
    )

    if not await ensure_zotify_initialized():
        LOGGER.warning("Zotify initialization failed")
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="disabled",
                    title="Zotify search is unavailable",
                    description="Zotify could not be initialized or is not configured",
                    input_message_content=InputTextMessageContent(
                        "🎧 Zotify search is currently unavailable. Please check configuration."
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
                    title="🎧 Search music on Spotify",
                    description="Type a search query to find music",
                    input_message_content=InputTextMessageContent(
                        get_comprehensive_help_text()
                    ),
                )
            ],
            cache_time=300,
        )
        return

    # Parse query for media type filters
    query = inline_query.query.strip()
    media_type = None

    # Implement debouncing: require minimum query length
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
            cache_time=1,
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

    # Check for type filter (type:query)
    if ":" in query:
        parts = query.split(":", 1)
        if len(parts) == 2:
            potential_type = parts[0].lower().strip()
            if potential_type in ["track", "album", "playlist", "artist"]:
                media_type = potential_type
                query = parts[1].strip()

    # If query is empty after parsing, show help
    if not query:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="empty_query",
                    title="Please provide a search query",
                    description=f"Type your search query after {media_type}:",
                    input_message_content=InputTextMessageContent(
                        f"Please provide a search query after {media_type}:"
                    ),
                )
            ],
            cache_time=5,
        )
        return

    try:
        # Note: Removed blocking "Searching Spotify..." message as it blocks real results
        # Zotify platform-specific search now sends results directly

        # Perform search without timeout - let it complete naturally
        results = await asyncio.shield(
            perform_inline_zotify_search(
                query, media_type, inline_query.from_user.id
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
                            f"🎧 No music found matching: <code>{query}</code>\n\n"
                            "💡 Try different keywords or check spelling."
                        ),
                    )
                ],
                cache_time=30,
            )
            return

        # Format results for inline query (Telegram limit: 50 results)
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

        for i, result in enumerate(results[: 49 if len(results) > 50 else 50]):
            # Validate result type
            if not isinstance(result, dict):
                LOGGER.warning(
                    f"Invalid result type in inline results: {type(result)} - {result}"
                )
                continue

            # Create result ID
            result_id = f"z_{i}_{int(time_module.time())}"

            # Format title and description
            title = result.get("name", result.get("title", "Unknown"))
            artist = result.get("artist", "")
            if isinstance(artist, list):
                artist = ", ".join(artist[:2])  # Show max 2 artists

            media_type_name = result.get("type", "track").title()

            # Type emoji
            type_emoji = {
                "track": "🎵",
                "album": "💿",
                "playlist": "📋",
                "artist": "👤",
            }.get(result.get("type", "track"), "🎵")

            display_title = f"🎧 {title}"
            if artist:
                display_title += f" - {artist}"

            # Add Spotify quality information based on actual account type
            # Detect account type for accurate quality display
            try:
                from bot.helper.mirror_leech_utils.zotify_utils.quality_selector import detect_account_type
                account_type = await detect_account_type()

                if account_type == "premium":
                    quality_info = "OGG Vorbis (320kbps Premium)"
                else:
                    quality_info = "OGG Vorbis (160kbps Free)"
            except Exception as e:
                LOGGER.info(f"Could not detect Zotify account type: {e}")
                # Fallback to conservative estimate
                quality_info = "OGG Vorbis (160kbps)"

            description = f"{type_emoji} {media_type_name} • {quality_info}"

            # Add duration for tracks
            if result.get("duration") and result.get("type") in ["track", "song"]:
                minutes = result["duration"] // 60
                seconds = result["duration"] % 60
                description += f" • {minutes}:{seconds:02d}"

            # Add track count for albums/playlists
            elif result.get("track_count") and result.get("type") in ["album", "playlist"]:
                track_count = result["track_count"]
                if result.get("duration"):
                    total_minutes = result["duration"] // 60
                    description += f" • {track_count} tracks • {total_minutes}min"
                else:
                    description += f" • {track_count} tracks"

            # Add lyrics indicator if available (Spotify has lyrics for many tracks)
            if result.get("has_lyrics", False):
                description += " • 🎤"

            # Store result data for retrieval
            result_data = {
                "url": result.get("url", ""),
                "platform": "spotify",
                "type": result.get("type", "track"),
                "title": title,
                "artist": artist,
                "query": query,
            }

            # Create encrypted ID for callback data
            encrypted_id = encrypt_zotify_data(str(result_data))
            callback_data = f"zotify_dl_{encrypted_id}"

            # Check callback data length (Telegram limit is 64 bytes)
            if len(callback_data) > 64:
                LOGGER.warning(
                    f"Callback data too long ({len(callback_data)} bytes), using hash: {encrypted_id}"
                )
                # Use just the hash if too long
                callback_data = f"zotify_dl_{encrypted_id[:50]}"  # Ensure it fits

            # Create message content
            message_text = f"🎧 <b>{title}</b>\n"
            if artist:
                message_text += f"👤 <b>Artist:</b> {artist}\n"
            if result.get("album"):
                message_text += f"💿 <b>Album:</b> {result['album']}\n"
            message_text += "🎧 <b>Platform:</b> Spotify\n"
            message_text += f"📁 <b>Type:</b> {media_type_name}\n\n"
            message_text += "⏳ <i>Preparing quality selection...</i>"

            # Create reply markup with URL button that will trigger quality selection in private message
            # This ensures users get quality selection in private message instead of spamming groups
            start_command = f"zotify_{encrypted_id}"

            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=f"🎧 Download {media_type_name}",
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

            # Add thumbnail support for inline results
            inline_result_params = {
                "id": result_id,
                "title": display_title,
                "description": description,
                "input_message_content": InputTextMessageContent(message_text),
                "reply_markup": reply_markup,
            }

            # Add thumbnail if available (Pyrogram uses 'thumb_url')
            thumbnail_url = result.get("cover_url") or result.get("thumbnail_url")
            if thumbnail_url and thumbnail_url.startswith("http"):
                inline_result_params["thumb_url"] = thumbnail_url

            inline_results.append(InlineQueryResultArticle(**inline_result_params))

        # Answer the inline query with timeout protection
        try:
            await asyncio.wait_for(
                inline_query.answer(
                    results=inline_results,
                    cache_time=300,
                    is_personal=True,
                ),
                timeout=10.0,
            )
        except TimeoutError:
            LOGGER.warning("Timeout while sending inline query results")
            with contextlib.suppress(Exception):
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
            return

    except Exception as e:
        error_msg = str(e)
        LOGGER.error(f"Error in inline Zotify search: {error_msg}")

        # Handle specific Telegram errors - don't try to answer invalid queries
        if (
            "QUERY_ID_INVALID" in error_msg
            or "query id is invalid" in error_msg.lower()
        ):
            LOGGER.warning("Query ID invalid - user typed too fast or query expired")
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
        if "CancelledError" in error_msg or "cancelled" in error_msg.lower():
            LOGGER.warning("Search was cancelled")
            return

        # Try to answer with error message for other errors
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
                timeout=5.0,
            )
        except Exception:
            return


async def handle_zotify_callback(_, callback_query):
    """Handle callback queries for Zotify inline search results."""
    try:
        # Extract callback data for Zotify downloads
        callback_data = callback_query.data
        if not callback_data.startswith("zotify_dl_"):
            LOGGER.warning(f"Invalid callback data format: {callback_data}")
            return

        # Get the encrypted ID
        encrypted_id = callback_data.replace("zotify_dl_", "")

        # Decrypt the result data with enhanced error handling
        try:
            result_data_str = decrypt_zotify_data(encrypted_id)

            if result_data_str == encrypted_id:  # Decryption failed
                LOGGER.error(
                    f"Decryption failed for callback data: {encrypted_id[:20]}..."
                )
                await callback_query.answer(
                    "❌ Invalid or expired link. Please search again.",
                    show_alert=True,
                )
                return
        except Exception as decrypt_error:
            LOGGER.error(f"Decryption error for callback data: {decrypt_error}")
            await callback_query.answer(
                "❌ Session expired. Please search again.", show_alert=True
            )
            return

        # Parse the result data
        try:
            import ast

            result_data = ast.literal_eval(result_data_str)
        except (ValueError, SyntaxError) as e:
            LOGGER.error(f"Failed to parse Zotify result data: {e}")
            await callback_query.answer(
                "❌ Invalid result data. Please search again.", show_alert=True
            )
            return

        # Check if Zotify is enabled
        if not Config.ZOTIFY_ENABLED:
            await callback_query.answer(
                "❌ Zotify downloads are disabled!", show_alert=True
            )
            return

        # Extract data
        url = result_data.get("url", "")
        result_data.get("type", "track")

        if not url:
            await callback_query.answer(
                "❌ Invalid download URL. Please search again.", show_alert=True
            )
            return

        # Answer the callback query silently
        await callback_query.answer()

        # For inline callbacks, create a fake message object
        if not callback_query.message:
            from types import SimpleNamespace

            fake_message = SimpleNamespace()
            fake_message.from_user = callback_query.from_user
            fake_message.chat = SimpleNamespace()
            fake_message.chat.id = callback_query.from_user.id

            # Create proper chat type object
            fake_chat_type = SimpleNamespace()
            fake_chat_type.name = "PRIVATE"
            fake_message.chat.type = fake_chat_type

            fake_message.id = 0
            fake_message.reply_to_message = None
            fake_message.sender_chat = None

            # Add missing attributes
            from datetime import datetime

            fake_message.date = datetime.now()
            fake_message.text = "🎧 Zotify download from inline search"

            # Add delete method
            async def fake_delete():
                return True

            fake_message.delete = fake_delete

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
                )

            async def fake_reply_document(
                document,
                quote=None,
                thumb=None,
                caption=None,
                force_document=True,
                disable_notification=True,
                progress=None,
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
                )

            async def fake_reply_photo(
                photo,
                quote=None,
                caption=None,
                disable_notification=True,
                progress=None,
            ):
                """Fake reply_photo method that sends photo to user's private chat"""
                return await TgClient.bot.send_photo(
                    chat_id=callback_query.from_user.id,
                    photo=photo,
                    caption=caption,
                    disable_notification=disable_notification,
                    progress=progress,
                )

            fake_message.reply_audio = fake_reply_audio
            fake_message.reply_video = fake_reply_video
            fake_message.reply_document = fake_reply_document
            fake_message.reply_photo = fake_reply_photo

            # Add reply method
            async def fake_reply(
                text,
                quote=None,
                disable_web_page_preview=True,
                disable_notification=True,
                reply_markup=None,
                parse_mode=None,
            ):
                return await TgClient.bot.send_message(
                    chat_id=callback_query.from_user.id,
                    text=text,
                    disable_web_page_preview=disable_web_page_preview,
                    disable_notification=disable_notification,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )

            fake_message.reply = fake_reply
            message_for_listener = fake_message

        else:
            message_for_listener = callback_query.message

        # Create proper ZotifyListener object
        from bot.helper.listeners.zotify_listener import ZotifyListener

        # Create listener with the message object
        listener = ZotifyListener(message_for_listener, is_leech=True, tag="")

        # Import and start Zotify download
        from bot.helper.mirror_leech_utils.download_utils.zotify_download import (
            add_zotify_download,
        )

        # Start the download (add_zotify_download expects listener and url string)
        await add_zotify_download(listener, url)

    except Exception as e:
        LOGGER.error(f"Error in Zotify callback handler: {e}")
        with contextlib.suppress(Exception):
            await callback_query.answer(
                f"❌ Error starting download: {e}", show_alert=True
            )


async def handle_zotify_start_command(client, message):
    """Handle start commands for Zotify downloads from inline search results."""
    try:
        # Initialize Zotify on-demand
        from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import (
            ensure_zotify_initialized,
        )

        if not await ensure_zotify_initialized():
            from bot.helper.telegram_helper.message_utils import send_message

            await send_message(
                message,
                "❌ Zotify is not available or not configured properly.",
            )
            return

        # Extract the encrypted ID from the start command
        if len(message.command) < 2 or not message.command[1].startswith("zotify_"):
            from bot.helper.telegram_helper.message_utils import send_message

            await send_message(
                message,
                "❌ Invalid Zotify start command format.",
            )
            return

        # Get the encrypted ID
        encrypted_id = message.command[1].replace("zotify_", "")

        # Decrypt the result data
        result_data_str = decrypt_zotify_data(encrypted_id)

        if result_data_str == encrypted_id:  # Decryption failed
            LOGGER.error("Decryption failed for start command data")
            from bot.helper.telegram_helper.message_utils import send_message

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
            LOGGER.error(f"Failed to parse Zotify result data: {e}")
            from bot.helper.telegram_helper.message_utils import send_message

            await send_message(
                message,
                "❌ Invalid result data. Please search again.",
            )
            return

        # Check if Zotify is enabled
        if not Config.ZOTIFY_ENABLED:
            from bot.helper.telegram_helper.message_utils import send_message

            await send_message(
                message,
                "❌ Zotify downloads are disabled!",
            )
            return

        # Extract data
        url = result_data.get("url", "")
        media_type = result_data.get("type", "track")
        title = result_data.get("title", "Unknown")
        artist = result_data.get("artist", "Unknown")

        if not url:
            from bot.helper.telegram_helper.message_utils import send_message

            await send_message(
                message,
                "❌ Invalid download URL. Please search again.",
            )
            return

        # Send initial message with track info and start command
        start_command = f"/start zotify_{encrypted_id}"
        info_msg = "<b>🎧 Zotify Download</b>\n\n"
        info_msg += f"<code>{start_command}</code>\n\n"
        info_msg += f"🎧 <b>{title}</b>\n"
        if artist:
            if isinstance(artist, list):
                artist_str = ", ".join(artist[:2])  # Show first 2 artists
            else:
                artist_str = str(artist)
            info_msg += f"👤 <b>Artist:</b> {artist_str}\n"
        info_msg += "🎧 <b>Platform:</b> Spotify\n"
        info_msg += f"📁 <b>Type:</b> {media_type.title()}\n\n"
        info_msg += "🚀 <i>Starting download...</i>"

        from bot.helper.telegram_helper.message_utils import send_message

        await send_message(message, info_msg)

        # Create proper ZotifyListener object
        from bot.helper.listeners.zotify_listener import ZotifyListener

        # Create listener with the message object
        listener = ZotifyListener(message, is_leech=True, tag="")

        # Import and start Zotify download
        from bot.helper.mirror_leech_utils.download_utils.zotify_download import (
            add_zotify_download,
        )

        # Start the download (add_zotify_download expects listener and url string)
        await add_zotify_download(listener, url)

    except Exception as e:
        LOGGER.error(f"Error in Zotify start command handler: {e}")
        from bot.helper.telegram_helper.message_utils import send_message

        await send_message(
            message,
            f"❌ Error: {e!s}",
        )


def init_zotify_inline_search(bot, register_inline=True):
    """Initialize Zotify inline search handlers."""
    if not Config.ZOTIFY_ENABLED:
        LOGGER.warning("Zotify is disabled, skipping inline search initialization")
        return

    from pyrogram import filters as pyrogram_filters
    from pyrogram.handlers import CallbackQueryHandler, InlineQueryHandler

    # Register Zotify inline query handler only if requested
    if register_inline:
        # Create a wrapper to handle task creation and exception handling
        async def safe_inline_zotify_search(client, inline_query):
            """Wrapper for inline_zotify_search that handles exceptions properly"""
            try:
                await inline_zotify_search(client, inline_query)
            except Exception as e:
                error_msg = str(e)
                # Don't log QUERY_ID_INVALID errors as they're expected
                if (
                    "QUERY_ID_INVALID" not in error_msg
                    and "query id is invalid" not in error_msg.lower()
                ):
                    LOGGER.error(
                        f"Unhandled error in inline Zotify search: {error_msg}"
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

        bot.add_handler(InlineQueryHandler(safe_inline_zotify_search))

    # Register Zotify callback handler for inline results
    async def safe_zotify_callback(_, callback_query):
        """Wrapper for handle_zotify_callback that handles exceptions properly"""
        try:
            await handle_zotify_callback(_, callback_query)
        except Exception as e:
            error_msg = str(e)
            LOGGER.error(f"Error in Zotify callback handler: {error_msg}")
            try:
                await callback_query.answer(
                    f"❌ Error: {error_msg}", show_alert=True
                )
            except Exception:
                pass  # Ignore errors when trying to answer

    bot.add_handler(
        CallbackQueryHandler(
            safe_zotify_callback,
            filters=pyrogram_filters.regex(r"^zotify_dl_"),
        )
    )
