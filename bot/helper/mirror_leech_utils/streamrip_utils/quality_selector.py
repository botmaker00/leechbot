import asyncio
from time import time
from typing import Any

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

# Global registry for active quality selectors
_active_quality_selectors = {}


def get_active_quality_selector(user_id):
    """Get active quality selector for a user"""
    return _active_quality_selectors.get(user_id)


def register_quality_selector(user_id, selector):
    """Register a quality selector for a user"""
    _active_quality_selectors[user_id] = selector


def unregister_quality_selector(user_id):
    """Unregister a quality selector for a user"""
    _active_quality_selectors.pop(user_id, None)


class StreamripQualitySelector:
    """Quality selection interface for streamrip downloads"""

    # Streamrip platform max qualities (from streamrip library source)
    PLATFORM_MAX_QUALITIES = {
        "qobuz": 4,  # 1-4: 320kbps MP3, 16/44.1, 24/≤96, 24/≥96
        "tidal": 3,  # 0-3: 256kbps AAC, 320kbps AAC, 16/44.1 FLAC, 24/44.1 MQA
        "deezer": 2,  # 0-2: 128kbps MP3, 320kbps MP3, FLAC
        "soundcloud": 0,  # 0: MP3 (various bitrates)
    }

    # Bot UI to Streamrip quality mapping (matches download helper)
    BOT_TO_STREAMRIP_MAPPING = {
        "qobuz": {0: 1, 1: 1, 2: 2, 3: 3, 4: 4},
        "tidal": {0: 0, 1: 1, 2: 2, 3: 3},
        "deezer": {0: 0, 1: 1, 2: 2},
        "soundcloud": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0},
    }

    # Quality definitions for different platforms (Bot UI qualities)
    QUALITY_INFO = {
        0: {
            "name": "128 kbps",
            "description": "Low quality MP3/AAC",
            "streamrip_qualities": {"deezer": 0, "tidal": 0, "soundcloud": 0},
            "size_estimate": "~4MB/track",
        },
        1: {
            "name": "320 kbps",
            "description": "High quality MP3/AAC",
            "streamrip_qualities": {
                "deezer": 1,
                "tidal": 1,
                "qobuz": 1,
                "soundcloud": 0,
            },
            "size_estimate": "~10MB/track",
        },
        2: {
            "name": "CD Quality",
            "description": "16-bit/44.1kHz FLAC",
            "streamrip_qualities": {"deezer": 2, "tidal": 2, "qobuz": 2},
            "size_estimate": "~35MB/track",
        },
        3: {
            "name": "Hi-Res",
            "description": "24-bit/≤96kHz FLAC/MQA",
            "streamrip_qualities": {"tidal": 3, "qobuz": 3},
            "size_estimate": "~80MB/track",
        },
        4: {
            "name": "Hi-Res+",
            "description": "24-bit/≥96kHz FLAC (up to 192kHz)",
            "streamrip_qualities": {"qobuz": 4},
            "size_estimate": "~150MB/track",
        },
    }

    CODEC_INFO = {
        "flac": {
            "name": "FLAC",
            "description": "Lossless compression",
            "extension": ".flac",
        },
        "mp3": {
            "name": "MP3",
            "description": "Lossy compression",
            "extension": ".mp3",
        },
        "m4a": {
            "name": "M4A/AAC",
            "description": "Lossy compression",
            "extension": ".m4a",
        },
        "ogg": {
            "name": "OGG Vorbis",
            "description": "Lossy compression",
            "extension": ".ogg",
        },
        "opus": {
            "name": "Opus",
            "description": "Lossy compression",
            "extension": ".opus",
        },
    }

    def __init__(self, listener, platform: str, media_type: str):
        self.listener = listener
        self.platform = platform.lower()
        self.media_type = media_type
        self._reply_to = None
        self._time = time()
        self._timeout = 120
        self.event = asyncio.Event()
        self.selected_quality = None
        self.selected_codec = None
        self._main_buttons = None

    async def _register_handler_and_wait(self):
        """Use global callback interception instead of registering new handlers"""
        from bot import LOGGER

        # Register this quality selector instance globally for callback interception
        register_quality_selector(self.listener.user_id, self)

        try:
            await asyncio.wait_for(self.event.wait(), timeout=self._timeout)
        except TimeoutError:
            LOGGER.warning(
                f"Quality selection timed out after {self._timeout} seconds"
            )
            # Send beautified timeout message
            timeout_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} <b>⏰ Quality selection timed out.</b>\n<i>Using default quality...</i>",
            )

            # Delete the selection menu (check if it's a valid message object)
            if self._reply_to and hasattr(self._reply_to, "delete"):
                await delete_message(self._reply_to)

            # Auto-delete timeout message (check if it's a valid message object)
            if timeout_msg and hasattr(timeout_msg, "delete"):
                asyncio.create_task(auto_delete_message(timeout_msg, time=300))

            # Use default quality
            self.selected_quality = Config.STREAMRIP_DEFAULT_QUALITY
            self.selected_codec = Config.STREAMRIP_DEFAULT_CODEC
            self.event.set()
        except Exception as e:
            LOGGER.error(f"Unexpected error during quality selection wait: {e}")
            raise
        finally:
            try:
                # Remove from global registry
                unregister_quality_selector(self.listener.user_id)
            except Exception as e:
                LOGGER.error(f"Error cleaning up quality selector: {e}")

    @staticmethod
    async def _handle_callback(_, query, obj):
        """Handle callback query"""

        # Validate user ID (important if using catch-all handler)
        if query.from_user.id != obj.listener.user_id:
            LOGGER.warning("User ID mismatch, ignoring callback")
            return

        # Validate callback data format
        if not query.data.startswith("srq"):
            LOGGER.warning("Invalid callback data format, ignoring")
            return

        data = query.data.split()

        if len(data) < 2:
            LOGGER.warning("Invalid callback data length, ignoring")
            return

        # Answer callback query with error handling
        try:
            await query.answer()
        except Exception as e:
            LOGGER.warning(f"Failed to answer callback query: {e}")
            # Continue processing even if answer fails

        if data[1] == "quality":
            quality = int(data[2])
            obj.selected_quality = quality
            await obj._show_codec_selection()
        elif data[1] == "codec":
            codec = data[2]
            obj.selected_codec = codec
            await obj._finalize_selection()
        elif data[1] == "back":
            await obj._show_quality_selection()
        elif data[1] == "cancel":
            # Send beautified cancellation message
            cancel_msg = await send_message(
                obj.listener.message,
                f"{obj.listener.tag} <b>❌ Quality selection cancelled!</b>",
            )

            # Delete the selection menu (check if it's a valid message object)
            if obj._reply_to and hasattr(obj._reply_to, "delete"):
                await delete_message(obj._reply_to)

            # Auto-delete cancellation message (check if it's a valid message object)
            if cancel_msg and hasattr(cancel_msg, "delete"):
                asyncio.create_task(auto_delete_message(cancel_msg, time=300))

            obj.listener.is_cancelled = True
            obj.event.set()
        else:
            LOGGER.warning(f"Unknown callback action: {data[1]}")

    async def get_quality_selection(self) -> dict[str, Any] | None:
        """Show quality selection interface and get user choice"""
        from bot import LOGGER

        try:
            # Show quality selection menu first
            await self._show_quality_selection()

            # Register handler and wait for selection (this replaces _event_handler)
            await self._register_handler_and_wait()

            if self.listener.is_cancelled:
                return None

            return {"quality": self.selected_quality, "codec": self.selected_codec}

        except Exception as e:
            LOGGER.error(f"Exception in get_quality_selection: {e}")
            import traceback

            LOGGER.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def _show_quality_selection(self):
        """Show quality selection buttons"""
        from bot import LOGGER

        buttons = ButtonMaker()

        # Get available qualities for this platform
        available_qualities = self._get_available_qualities()

        # Platform info header with HTML formatting
        platform_name = self.platform.title()
        msg = f"<b>🎵 Quality Selection for {platform_name}</b>\n"
        msg += f"<b>📁 Media Type:</b> <code>{self.media_type.title()}</code>\n"

        # Add platform max quality info
        self.PLATFORM_MAX_QUALITIES.get(self.platform, 0)
        max_bot_quality = max(available_qualities) if available_qualities else 0
        msg += f"<b>🎯 Max Quality:</b> <code>{self.QUALITY_INFO[max_bot_quality]['name']}</code>\n"
        msg += f"<b>📊 Available Qualities:</b> <code>{len(available_qualities)}</code>\n\n"

        # Add quality buttons with platform-specific descriptions
        for quality in available_qualities:
            quality_info = self.QUALITY_INFO[quality]
            platform_description = self._get_platform_quality_description(quality)

            button_text = f"🔸 {quality_info['name']} - {platform_description}"

            # Add size estimate
            if quality_info["size_estimate"]:
                button_text += f" ({quality_info['size_estimate']})"

            # Add subscription warning for high qualities
            if quality >= 2 and self.platform in ["qobuz", "tidal", "deezer"]:
                if quality == 2:
                    button_text += " 🔒"
                elif quality >= 3:
                    button_text += " 🔒👑"

            callback_data = f"srq quality {quality}"
            buttons.data_button(button_text, callback_data)

        # Add default and cancel buttons
        default_quality = Config.STREAMRIP_DEFAULT_QUALITY
        if default_quality in available_qualities:
            default_info = self.QUALITY_INFO[default_quality]
            default_callback = f"srq quality {default_quality}"
            buttons.data_button(
                f"⚡ Use Default ({default_info['name']})",
                default_callback,
                "footer",
            )

        cancel_callback = "srq cancel"
        buttons.data_button("❌ Cancel", cancel_callback, "footer")

        # Add subscription requirements info with HTML formatting
        msg += "<i>🔒 = Requires subscription</i>\n"
        msg += "<i>👑 = Requires premium subscription</i>\n\n"
        msg += f"<b>⏱️ Timeout:</b> <code>{get_readable_time(self._timeout - (time() - self._time))}</code>"

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

    async def _show_codec_selection(self):
        """Show codec selection buttons"""
        buttons = ButtonMaker()

        quality_info = self.QUALITY_INFO[self.selected_quality]

        # Beautified codec selection message with HTML formatting
        msg = "<b>🎵 Codec Selection</b>\n"
        msg += f"<b>📊 Selected Quality:</b> <code>{quality_info['name']}</code> - <i>{quality_info['description']}</i>\n\n"
        msg += "<b>Choose output format:</b>\n\n"

        # Add codec buttons based on quality
        available_codecs = self._get_available_codecs()

        for codec in available_codecs:
            codec_info = self.CODEC_INFO[codec]
            button_text = f"🎵 {codec_info['name']} - {codec_info['description']}"
            buttons.data_button(button_text, f"srq codec {codec}")

        # Add back and cancel buttons
        buttons.data_button("⬅️ Back", "srq back", "footer")
        buttons.data_button("❌ Cancel", "srq cancel", "footer")

        msg += f"<b>⏱️ Timeout:</b> <code>{get_readable_time(self._timeout - (time() - self._time))}</code>"

        # Only edit if it's a valid message object
        if self._reply_to and hasattr(self._reply_to, "edit"):
            await edit_message(self._reply_to, msg, buttons.build_menu(1))

    async def _finalize_selection(self):
        """Finalize the selection and close interface"""

        quality_info = self.QUALITY_INFO[self.selected_quality]
        codec_info = self.CODEC_INFO[self.selected_codec]

        # Beautified selection complete message with HTML tags
        msg = "<b>✅ Selection Complete</b>\n\n"
        msg += f"<b>🎯 Platform:</b> <code>{self.platform.title()}</code>\n"
        msg += f"<b>📊 Quality:</b> <code>{quality_info['name']}</code> - <i>{quality_info['description']}</i>\n"
        msg += f"<b>🎵 Format:</b> <code>{codec_info['name']}</code> <i>({codec_info['extension']})</i>\n"
        msg += f"<b>📁 Type:</b> <code>{self.media_type.title()}</code>\n\n"
        msg += "<b>🚀 Starting download...</b>"

        # Only edit if it's a valid message object
        if self._reply_to and hasattr(self._reply_to, "edit"):
            await edit_message(self._reply_to, msg)
            # Auto-delete after 10 seconds (check if it's a valid message object)
            if hasattr(self._reply_to, "delete"):
                asyncio.create_task(auto_delete_message(self._reply_to, time=10))

        self.event.set()

    def _get_available_qualities(self) -> list:
        """Get available qualities for the current platform based on streamrip library"""
        available = []

        # Get all bot UI qualities that are supported by this platform
        for bot_quality, quality_info in self.QUALITY_INFO.items():
            if self.platform in quality_info["streamrip_qualities"]:
                available.append(bot_quality)

        return sorted(available)

    async def _check_platform_authentication(self) -> bool:
        """Check if the platform client is available and authenticated"""
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            # Ensure streamrip is initialized
            await streamrip_config.lazy_initialize()
            config = streamrip_config.get_config()
            if not config:
                return False

            # Import streamrip Main class
            from streamrip.rip.main import Main

            main = Main(config)

            # Try to get the client for this platform
            client = await main.get_logged_in_client(self.platform)
            return client is not None and client.logged_in

        except Exception as e:
            LOGGER.warning(f"Failed to check {self.platform} authentication: {e}")
            return False

    def _get_platform_quality_description(self, bot_quality: int) -> str:
        """Get platform-specific quality description"""
        quality_info = self.QUALITY_INFO[bot_quality]
        base_description = quality_info["description"]

        # Add platform-specific details
        if self.platform == "qobuz":
            if bot_quality == 1:
                return "320kbps MP3"
            if bot_quality == 2:
                return "16-bit/44.1kHz FLAC (CD Quality)"
            if bot_quality == 3:
                return "24-bit/≤96kHz FLAC (Hi-Res)"
            if bot_quality == 4:
                return "24-bit/≥96kHz FLAC (Hi-Res+)"
        elif self.platform == "tidal":
            if bot_quality == 0:
                return "256kbps AAC"
            if bot_quality == 1:
                return "320kbps AAC"
            if bot_quality == 2:
                return "16-bit/44.1kHz FLAC (HiFi)"
            if bot_quality == 3:
                return "24-bit/44.1kHz MQA (Master)"
        elif self.platform == "deezer":
            if bot_quality == 0:
                return "128kbps MP3"
            if bot_quality == 1:
                return "320kbps MP3"
            if bot_quality == 2:
                return "16-bit/44.1kHz FLAC"
        elif self.platform == "soundcloud":
            return "MP3 (various bitrates)"

        return base_description

    async def _validate_quality_for_url(self, url: str, bot_quality: int) -> bool:
        """Validate if a specific quality is available for a given URL"""
        try:
            # This is an advanced feature that could be implemented to check
            # if a specific track/album actually supports the requested quality
            # For now, we'll return True and let streamrip handle the fallback
            return True
        except Exception as e:
            LOGGER.warning(
                f"Failed to validate quality {bot_quality} for URL {url}: {e}"
            )
            return True

    def _get_available_codecs(self) -> list:
        """Get available codecs based on selected quality"""
        if self.selected_quality >= 2:
            # Lossless quality - prefer FLAC
            return ["flac", "mp3", "m4a"]
        # Lossy quality - prefer MP3/M4A
        return ["mp3", "m4a", "ogg", "opus"]


async def show_quality_selector(
    listener, platform: str, media_type: str
) -> dict[str, Any] | None:
    """Show quality selection interface"""
    selector = StreamripQualitySelector(listener, platform, media_type)
    return await selector.get_quality_selection()
