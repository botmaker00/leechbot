"""
Simplified Zotify quality selector
"""

import asyncio
import contextlib
import time
from typing import Any

from zotify.utils import AudioFormat, Quality

from bot import LOGGER
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

# Simplified registry
_active_zotify_quality_selectors = {}


def get_active_zotify_quality_selector(user_id):
    """Get active Zotify quality selector for a user"""
    return _active_zotify_quality_selectors.get(user_id)


def register_zotify_quality_selector(user_id, selector):
    """Register a Zotify quality selector for a user"""
    _active_zotify_quality_selectors[user_id] = selector


def unregister_zotify_quality_selector(user_id):
    """Unregister a Zotify quality selector for a user"""
    _active_zotify_quality_selectors.pop(user_id, None)


class ZotifyQualitySelector:
    """Quality selection interface for Zotify downloads with low-to-high sorting and format pagination"""

    # Zotify quality definitions with enhanced premium info
    QUALITY_INFO = {
        Quality.NORMAL: {
            "name": "Normal (96 kbps)",
            "description": "Basic quality OGG Vorbis",
            "bitrate": 96,
            "size_estimate": "~3MB/track",
            "requires_premium": False,
            "account_types": ["free", "premium"],
            "emoji": "🔸",
            "recommendation": "Good for data saving",
        },
        Quality.HIGH: {
            "name": "High (160 kbps)",
            "description": "Standard quality OGG Vorbis",
            "bitrate": 160,
            "size_estimate": "~5MB/track",
            "requires_premium": False,
            "account_types": ["free", "premium"],
            "emoji": "🔹",
            "recommendation": "Balanced quality/size",
        },
        Quality.VERY_HIGH: {
            "name": "Very High (320 kbps)",
            "description": "Premium quality OGG Vorbis",
            "bitrate": 320,
            "size_estimate": "~10MB/track",
            "requires_premium": True,
            "account_types": ["premium"],
            "emoji": "💎",
            "recommendation": "Best quality (Premium only)",
        },
        Quality.AUTO: {
            "name": "Auto (Best Available)",
            "description": "Highest quality for your account type",
            "bitrate": "Variable",
            "size_estimate": "~5-10MB/track",
            "requires_premium": False,
            "account_types": ["free", "premium"],
            "emoji": "⚡",
            "recommendation": "Recommended for most users",
        },
    }

    # Zotify audio format definitions (exact from Zotify utils.py) with enhanced UI info
    FORMAT_INFO = {
        AudioFormat.VORBIS: {
            "name": "OGG Vorbis",
            "description": "Native Spotify format",
            "extension": ".ogg",
            "lossless": False,
            "transcoding": False,
            "compatibility": "Good",
            "emoji": "⚡",
            "priority": 1,
        },
        AudioFormat.MP3: {
            "name": "MP3",
            "description": "Universal compatibility",
            "extension": ".mp3",
            "lossless": False,
            "transcoding": True,
            "compatibility": "Excellent",
            "emoji": "🎵",
            "priority": 2,
        },
        AudioFormat.FLAC: {
            "name": "FLAC",
            "description": "Lossless compression",
            "extension": ".flac",
            "lossless": True,
            "transcoding": True,
            "compatibility": "Good",
            "emoji": "💿",
            "priority": 3,
        },
        AudioFormat.AAC: {
            "name": "M4A/AAC",
            "description": "Apple ecosystem optimized",
            "extension": ".m4a",
            "lossless": False,
            "transcoding": True,
            "compatibility": "Very Good",
            "emoji": "🍎",
            "priority": 4,
        },
        AudioFormat.WAV: {
            "name": "WAV",
            "description": "Uncompressed lossless",
            "extension": ".wav",
            "lossless": True,
            "transcoding": True,
            "compatibility": "Excellent",
            "emoji": "🔊",
            "priority": 5,
        },
    }

    def __init__(self, listener, media_type: str, account_type: str = "free"):
        self.listener = listener
        self.media_type = media_type
        self.account_type = account_type.lower()  # "free" or "premium"
        self._reply_to = None
        self._time = time.time()
        self._timeout = 300  # Increased to 5 minutes for better user experience
        self.event = asyncio.Event()
        self.selected_quality = None
        self.selected_format = None
        self._main_buttons = None

        # Pagination properties (only for format selection)
        self.current_page = 0
        self.items_per_page = 3  # Show 3 items per page for formats
        self.current_view = "quality"  # "quality" or "format"

    async def _register_handler_and_wait(self):
        """Use global callback interception instead of registering new handlers"""
        # Register this quality selector instance globally for callback interception
        register_zotify_quality_selector(self.listener.user_id, self)

        try:
            await asyncio.wait_for(self.event.wait(), timeout=self._timeout)
        except TimeoutError:
            LOGGER.warning(
                f"Zotify quality selection timed out after {self._timeout} seconds"
            )
            # Send beautified timeout message
            timeout_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} <b>⏰ Quality selection timed out.</b>\n<i>Using default quality...</i>",
            )

            # Delete the selection menu
            if self._reply_to and hasattr(self._reply_to, "delete"):
                await delete_message(self._reply_to)

            # Auto-delete timeout message
            if timeout_msg and hasattr(timeout_msg, "delete"):
                asyncio.create_task(auto_delete_message(timeout_msg, time=300))

            # Use default quality and format based on account type like StreamRip
            self.selected_quality = self._get_default_quality()
            self.selected_format = self._get_default_format()
            self.event.set()
        except Exception as e:
            LOGGER.error(
                f"Unexpected error during Zotify quality selection wait: {e}"
            )
            raise
        finally:
            try:
                # Remove from global registry
                unregister_zotify_quality_selector(self.listener.user_id)
            except Exception as e:
                LOGGER.error(f"Error cleaning up Zotify quality selector: {e}")

    @staticmethod
    async def _handle_callback(_, query, obj):
        """Handle callback query"""
        try:
            # Validate user ID
            if query.from_user.id != obj.listener.user_id:
                LOGGER.warning(
                    f"User ID mismatch: {query.from_user.id} != {obj.listener.user_id}"
                )
                await query.answer("❌ Unauthorized")
                return

            # Validate callback data format
            if not query.data.startswith("zq"):
                LOGGER.warning(f"Invalid callback data format: {query.data}")
                await query.answer("❌ Invalid callback")
                return

            data = query.data.split()
            # Processing quality callback (log removed for cleaner output)

            if len(data) < 2:
                LOGGER.warning(f"Invalid callback data length: {len(data)}")
                await query.answer("❌ Invalid data")
                return

            # Answer callback query
            await query.answer()
        except Exception as e:
            LOGGER.error(f"Error in callback validation: {e}")
            with contextlib.suppress(Exception):
                await query.answer("❌ Error")
            return

        try:
            if data[1] == "quality":
                if len(data) < 3:
                    LOGGER.warning("Quality callback missing quality name")
                    return

                quality_name = data[2]
                # Quality selected (log removed for cleaner output)

                # Convert string back to Quality enum
                quality_map = {
                    "AUTO": Quality.AUTO,
                    "NORMAL": Quality.NORMAL,
                    "HIGH": Quality.HIGH,
                    "VERY_HIGH": Quality.VERY_HIGH,
                }
                obj.selected_quality = quality_map.get(quality_name, Quality.AUTO)
                obj.current_view = "format"
                obj.current_page = 0  # Reset page for format selection
                await obj._show_format_selection()

            elif data[1] == "format":
                if len(data) < 3:
                    LOGGER.warning("Format callback missing format name")
                    return

                format_name = data[2]
                # Format selected (log removed for cleaner output)

                # Convert string back to AudioFormat enum
                format_map = {
                    "VORBIS": AudioFormat.VORBIS,
                    "MP3": AudioFormat.MP3,
                    "FLAC": AudioFormat.FLAC,
                    "AAC": AudioFormat.AAC,
                    "WAV": AudioFormat.WAV,
                }
                obj.selected_format = format_map.get(format_name, AudioFormat.VORBIS)
                await obj._finalize_selection()
            elif data[1] == "page":
                # Handle pagination (only for format selection)
                if len(data) < 3:
                    LOGGER.warning("Page callback missing page number")
                    return

                new_page = int(data[2])

                obj.current_page = new_page
                if obj.current_view == "format":
                    await obj._show_format_selection()
                # No pagination for quality selection anymore

            elif data[1] == "back":
                obj.current_view = "quality"
                obj.current_page = 0  # Reset page when going back to quality
                await obj._show_quality_selection()

            elif data[1] == "noop":
                # No operation - just acknowledge the callback (for page indicator)

                pass

            elif data[1] == "cancel":
                # Cancel button pressed (log removed for cleaner output)
                # Send beautified cancellation message
                cancel_msg = await send_message(
                    obj.listener.message,
                    f"{obj.listener.tag} <b>❌ Quality selection cancelled!</b>",
                )

                # Delete the selection menu
                if obj._reply_to and hasattr(obj._reply_to, "delete"):
                    await delete_message(obj._reply_to)

                # Auto-delete cancellation message
                if cancel_msg and hasattr(cancel_msg, "delete"):
                    asyncio.create_task(auto_delete_message(cancel_msg, time=300))

                # Set cancellation flags
                obj.listener.is_cancelled = True
                obj.selected_quality = None
                obj.selected_format = None
                obj.event.set()

            else:
                LOGGER.warning(f"Unknown callback action: {data[1]}")

        except Exception as e:
            LOGGER.error(f"Error processing Zotify quality callback: {e}")
            import traceback

            LOGGER.error(f"Traceback: {traceback.format_exc()}")
            with contextlib.suppress(Exception):
                await query.answer("❌ Processing error")

    async def get_quality_selection(self) -> dict[str, Any] | None:
        """Show quality selection interface and get user choice"""
        try:
            # Show quality selection menu first
            await self._show_quality_selection()

            # Register handler and wait for selection
            await self._register_handler_and_wait()

            # Check for cancellation or invalid selection
            if (
                self.listener.is_cancelled
                or self.selected_quality is None
                or self.selected_format is None
            ):
                return None

            return {"quality": self.selected_quality, "format": self.selected_format}

        except Exception as e:
            LOGGER.error(f"Exception in get_quality_selection: {e}")
            import traceback

            LOGGER.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def _show_quality_selection(self):
        """Show quality selection buttons (no pagination, sorted low to high)"""
        buttons = ButtonMaker()

        # Get available qualities for this account type (sorted low to high)
        available_qualities = self._get_available_qualities()

        # Enhanced platform info header with account type and premium benefits
        account_emoji = "💎" if self.account_type == "premium" else "🆓"
        msg = "<b>🎵 Quality Selection for Spotify (Zotify)</b>\n"
        msg += f"<b>📁 Media Type:</b> <code>{self.media_type.title()}</code>\n"
        msg += f"<b>👤 Account:</b> <code>{self.account_type.title()}</code> {account_emoji}\n"

        if self.account_type == "premium":
            msg += "<b>✨ Premium Benefits:</b> <code>320kbps • Synced Lyrics • All Formats</code>\n"
        else:
            msg += "<b>⚠️ Free Limitations:</b> <code>160kbps max • No synced lyrics</code>\n"

        msg += f"<b>📊 Available:</b> <code>{len(available_qualities)}</code> qualities\n\n"

        # Add all quality buttons (no pagination) with enhanced styling
        for quality in available_qualities:
            quality_info = self.QUALITY_INFO[quality]
            button_text = f"{quality_info['emoji']} {quality_info['name']}"

            # Add recommendation for premium users
            if self.account_type == "premium" and quality == Quality.VERY_HIGH:
                button_text += " ⭐ RECOMMENDED"
            elif quality == Quality.AUTO:
                button_text += " 🎯 SMART"

            # Add size estimate
            if quality_info["size_estimate"]:
                button_text += f"\n   📊 {quality_info['size_estimate']}"

            # Add premium indicators and recommendations
            if quality_info["requires_premium"]:
                if self.account_type == "premium":
                    button_text += " 💎 PREMIUM"
                else:
                    button_text += " 🔒 PREMIUM ONLY"

            # Add recommendation text
            if quality_info.get("recommendation"):
                button_text += f"\n   💡 {quality_info['recommendation']}"

            callback_data = f"zq quality {quality.name}"
            buttons.data_button(button_text, callback_data)

        # Add default and cancel buttons
        default_quality = self._get_default_quality()
        if default_quality in available_qualities:
            default_info = self.QUALITY_INFO[default_quality]
            default_callback = f"zq quality {default_quality.name}"
            buttons.data_button(
                f"⚡ Use Default ({default_info['name']})",
                default_callback,
                "footer",
            )

        buttons.data_button("❌ Cancel", "zq cancel", "footer")

        # Enhanced info section
        msg += "<i>🔒 = Requires Spotify Premium</i>\n"
        msg += "<i>💎 = Highest quality available</i>\n"
        msg += "<i>📝 Note: Qualities sorted from low to high</i>\n"
        msg += "<i>📝 Note: Spotify streams in OGG Vorbis format natively</i>\n\n"
        msg += f"<b>⏱️ Timeout:</b> <code>{get_readable_time(self._timeout - (time.time() - self._time))}</code>"

        # Send or edit message
        try:
            if self._reply_to and hasattr(self._reply_to, "edit"):
                await edit_message(self._reply_to, msg, buttons.build_menu(1))
            else:
                self._reply_to = await send_message(
                    self.listener.message, msg, buttons.build_menu(1)
                )
        except Exception as e:
            LOGGER.error(f"Error sending/editing message: {e}")
            raise

    async def _show_format_selection(self):
        """Show format selection buttons with StreamRip-style paginated UI"""
        buttons = ButtonMaker()

        quality_info = self.QUALITY_INFO[self.selected_quality]

        # Get available formats sorted by priority
        available_formats = self._get_available_formats()

        # Calculate pagination (StreamRip-style)
        total_items = len(available_formats)
        total_pages = (total_items + self.items_per_page - 1) // self.items_per_page
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, total_items)
        page_formats = available_formats[start_idx:end_idx]

        # Enhanced format selection message with detailed info and pagination
        msg = "<b>🎵 Audio Format Selection</b>\n"
        msg += f"<b>📊 Selected Quality:</b> <code>{quality_info['name']}</code> - <i>{quality_info['description']}</i>\n"
        msg += f"<b>🎯 Bitrate:</b> <code>{quality_info['bitrate']} kbps</code>\n"
        msg += f"<b>📊 Available:</b> <code>{total_items}</code> formats\n"
        if total_pages > 1:
            msg += f"<b>📄 Page:</b> <code>{self.current_page + 1}/{total_pages}</code>\n"
        msg += "\n<b>Choose output format:</b>\n\n"

        # Add format buttons for current page with enhanced styling
        for i, audio_format in enumerate(page_formats, start=start_idx + 1):
            format_info = self.FORMAT_INFO[audio_format]
            button_text = f"{i}. {format_info['emoji']} {format_info['name']}"

            # Add description on separate line for better readability
            button_text += f"\n   {format_info['description']}"

            # Add compatibility info
            button_text += f" ({format_info['compatibility']})"

            # Add special indicators
            if not format_info["transcoding"]:
                button_text += " ⚡"  # Native format
            elif format_info["lossless"]:
                button_text += " 💿"  # Lossless
            else:
                button_text += " 🔄"  # Transcoded

            buttons.data_button(button_text, f"zq format {audio_format.name}")

        # Add pagination buttons (StreamRip-style)
        if total_pages > 1:
            nav_buttons = []
            if self.current_page > 0:
                nav_buttons.append(
                    ("⬅️ Previous", f"zq page {self.current_page - 1}")
                )

            nav_buttons.append(
                (f"📄 {self.current_page + 1}/{total_pages}", "zq noop")
            )

            if self.current_page < total_pages - 1:
                nav_buttons.append(("Next ➡️", f"zq page {self.current_page + 1}"))

            for text, data in nav_buttons:
                buttons.data_button(text, data, "footer")

        # Add default format button like StreamRip
        default_format = self._get_default_format()
        default_info = self.FORMAT_INFO[default_format]
        default_callback = f"zq format {default_format.name}"
        buttons.data_button(
            f"⚡ Use Default ({default_info['name']})",
            default_callback,
            "footer",
        )

        # Add back and cancel buttons
        buttons.data_button("⬅️ Back", "zq back", "footer")
        buttons.data_button("❌ Cancel", "zq cancel", "footer")

        # Enhanced format info like StreamRip
        msg += "<i>⚡ = Native format (fastest, no transcoding)</i>\n"
        msg += "<i>💿 = Lossless quality (larger files)</i>\n"
        msg += "<i>🔄 = Transcoded format (slower processing)</i>\n\n"
        msg += f"<b>⏱️ Timeout:</b> <code>{get_readable_time(self._timeout - (time.time() - self._time))}</code>"

        # Only edit if it's a valid message object
        if self._reply_to and hasattr(self._reply_to, "edit"):
            await edit_message(self._reply_to, msg, buttons.build_menu(1))

    async def _finalize_selection(self):
        """Finalize the selection and close interface with StreamRip-style summary"""
        quality_info = self.QUALITY_INFO[self.selected_quality]
        format_info = self.FORMAT_INFO[self.selected_format]

        # Enhanced selection complete message with detailed info like StreamRip
        msg = "<b>✅ Selection Complete</b>\n\n"
        msg += "<b>🎯 Platform:</b> <code>Spotify (Zotify)</code>\n"
        msg += f"<b>👤 Account:</b> <code>{self.account_type.title()}</code>\n"
        msg += f"<b>📊 Quality:</b> <code>{quality_info['name']}</code> - <i>{quality_info['description']}</i>\n"
        msg += f"<b>🎯 Bitrate:</b> <code>{quality_info['bitrate']} kbps</code>\n"
        msg += f"<b>🎵 Format:</b> <code>{format_info['name']}</code> <i>({format_info['extension']})</i>\n"
        msg += f"<b>📁 Type:</b> <code>{self.media_type.title()}</code>\n"
        msg += f"<b>🔧 Compatibility:</b> <code>{format_info['compatibility']}</code>\n\n"

        # Add processing notes like StreamRip
        if not format_info["transcoding"]:
            msg += "<i>⚡ Native format - fastest download, no transcoding required</i>\n"
        elif format_info["lossless"]:
            msg += "<i>💿 Lossless transcoding - highest quality, larger files</i>\n"
        else:
            msg += "<i>🔄 Lossy transcoding - good quality, smaller files</i>\n"

        # Add size estimate
        msg += f"<i>📦 Estimated size: {quality_info['size_estimate']}</i>\n\n"

        msg += "<b>🚀 Starting download...</b>"

        # Only edit if it's a valid message object
        if self._reply_to and hasattr(self._reply_to, "edit"):
            await edit_message(self._reply_to, msg)
            # Auto-delete after 10 seconds
            if hasattr(self._reply_to, "delete"):
                asyncio.create_task(auto_delete_message(self._reply_to, time=10))

        self.event.set()

    def _get_available_qualities(self) -> list:
        """Get available qualities for the current account type, sorted from low to high"""
        available = []

        for quality, info in self.QUALITY_INFO.items():
            if self.account_type in info["account_types"]:
                available.append(quality)

        # Sort from low to high quality: Normal -> High -> Very High -> Auto (best last)
        def sort_key(q):
            if q == Quality.NORMAL:
                return 1
            if q == Quality.HIGH:
                return 2
            if q == Quality.VERY_HIGH:
                return 3
            if q == Quality.AUTO:
                return 4  # AUTO last (best available)
            return 999

        return sorted(available, key=sort_key)

    def _get_available_formats(self) -> list:
        """Get available formats sorted by priority"""
        available_formats = list(self.FORMAT_INFO.keys())

        # Sort by priority (lower number = higher priority)
        return sorted(
            available_formats, key=lambda f: self.FORMAT_INFO[f]["priority"]
        )

    def _get_default_quality(self) -> Quality:
        """Get default quality based on account type"""
        if self.account_type == "premium":
            return Quality.VERY_HIGH
        return Quality.HIGH  # Best for free accounts

    def _get_default_format(self) -> AudioFormat:
        """Get default format (native OGG Vorbis)"""
        return AudioFormat.VORBIS


async def detect_account_type() -> str:
    """Detect Zotify account type (premium vs free) using actual session"""
    try:
        from bot.helper.mirror_leech_utils.zotify_utils.improved_session_manager import (
            simple_session_manager,
        )

        session = await simple_session_manager.get_session()
        if session:
            try:
                # Use Zotify Session's is_premium() method for direct detection
                if hasattr(session, 'is_premium') and callable(session.is_premium):
                    is_premium = session.is_premium()
                    LOGGER.info(f"🎧 [ZOTIFY] Account type detected via is_premium(): {'premium' if is_premium else 'free'}")
                    return "premium" if is_premium else "free"

                # Fallback: Try to get user info via API call
                user_info = await simple_session_manager.api_call("me")
                if user_info and isinstance(user_info, dict):
                    product = user_info.get("product", "free").lower()
                    account_type = "premium" if product in ["premium", "family", "student"] else "free"
                    LOGGER.info(f"🎧 [ZOTIFY] Account type detected via API: {account_type} (product: {product})")
                    return account_type

                # Fallback: Check user attributes
                if hasattr(session, 'get_user_attribute'):
                    try:
                        product = session.get_user_attribute('product')
                        if product:
                            account_type = "premium" if product.lower() in ["premium", "family", "student"] else "free"
                            LOGGER.info(f"🎧 [ZOTIFY] Account type detected via user_attribute: {account_type}")
                            return account_type
                    except Exception as e:
                        LOGGER.info(f"Could not get user attribute: {e}")

            except Exception as e:
                LOGGER.warning(f"🎧 [ZOTIFY] Error detecting account type: {e}")

        LOGGER.warning("🎧 [ZOTIFY] Could not detect account type, defaulting to free")
        return "free"
    except Exception as e:
        LOGGER.error(f"🎧 [ZOTIFY] Account detection failed: {e}")
        return "free"


async def show_zotify_quality_selector(
    listener, media_type: str, account_type: str | None = None
) -> dict[str, Any] | None:
    """Show Zotify quality selection interface"""
    if account_type is None:
        account_type = await detect_account_type()

    selector = ZotifyQualitySelector(listener, media_type, account_type)
    return await selector.get_quality_selection()
