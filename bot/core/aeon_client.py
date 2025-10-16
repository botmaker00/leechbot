# Detect which Telegram library is being used by checking Client parameters
import inspect
from asyncio import Lock, gather

from pyrogram import Client, enums
from pyrogram import utils as pyroutils

# Import handlers for Nekozee compatibility (conditional import handled in decorators)
try:
    from pyrogram.handlers import (
        CallbackQueryHandler,
        EditedMessageHandler,
        MessageHandler,
    )
except ImportError:
    # Handlers not available in some libraries
    MessageHandler = CallbackQueryHandler = EditedMessageHandler = None

from bot import LOGGER

from .config_manager import Config

# Configure PyroFork/Pyrogram utils for better peer ID handling
# This fixes "Peer id invalid" errors with large negative chat/channel IDs
pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -100999999999999

# Multi-library detection system
USING_KURIGRAM = False
USING_PYROFORK = False
USING_NEKOZEE = False
LIBRARY_NAME = "unknown"

try:
    client_init_signature = inspect.signature(Client.__init__)
    client_params = list(client_init_signature.parameters.keys())

    # Check for library-specific attributes and methods
    client_methods = dir(Client)

    # Primary detection: Check if on_message method exists
    has_on_message = hasattr(Client, "on_message") and "on_message" in client_methods

    if not has_on_message:
        # No on_message method = Nekozee
        USING_NEKOZEE = True
        LIBRARY_NAME = "nekozee"

    elif "max_concurrent_transmissions" in client_params:
        # Has on_message + max_concurrent_transmissions = Kurigram
        USING_KURIGRAM = True
        LIBRARY_NAME = "kurigram"

    else:
        # Has on_message but no max_concurrent_transmissions = PyroFork
        USING_PYROFORK = True
        LIBRARY_NAME = "pyrofork"

except Exception as e:
    # Fallback - assume pyrofork if detection fails
    USING_PYROFORK = True
    LIBRARY_NAME = "pyrofork"
    LOGGER.warning(f"Library detection failed, defaulting to PyroFork: {e}")


# Compatibility flags for easy checking
IS_KURIGRAM = USING_KURIGRAM
IS_PYROFORK = USING_PYROFORK
IS_NEKOZEE = USING_NEKOZEE


# Decorator compatibility wrapper
class DecoratorWrapper:
    """Wrapper to handle different decorator systems across libraries"""

    def __init__(self, client):
        self.client = client

    def on_message(self, filters=None):
        """Universal on_message decorator"""
        if IS_NEKOZEE:
            # Nekozee uses add_handler with MessageHandler
            def decorator(func):
                if MessageHandler is None:
                    raise ImportError("MessageHandler not available in this library")
                handler = MessageHandler(func, filters)
                self.client.add_handler(handler)
                return func

            return decorator
        # Kurigram and PyroFork use standard on_message
        return self.client.on_message(filters)

    def on_callback_query(self, filters=None):
        """Universal on_callback_query decorator"""
        if IS_NEKOZEE:

            def decorator(func):
                if CallbackQueryHandler is None:
                    raise ImportError(
                        "CallbackQueryHandler not available in this library"
                    )
                handler = CallbackQueryHandler(func, filters)
                self.client.add_handler(handler)
                return func

            return decorator
        return self.client.on_callback_query(filters)

    def on_edited_message(self, filters=None):
        """Universal on_edited_message decorator"""
        if IS_NEKOZEE:

            def decorator(func):
                if EditedMessageHandler is None:
                    raise ImportError(
                        "EditedMessageHandler not available in this library"
                    )
                handler = EditedMessageHandler(func, filters)
                self.client.add_handler(handler)
                return func

            return decorator
        return self.client.on_edited_message(filters)

    def __getattr__(self, name):
        """Delegate all other attributes to the underlying client"""
        return getattr(self.client, name)


class TgClient:
    _lock = Lock()
    _hlock = Lock()
    bot = None
    user = None
    helper_bots = {}
    helper_loads = {}
    NAME = ""
    ID = 0
    IS_PREMIUM_USER = False
    MAX_SPLIT_SIZE = 2097152000

    @classmethod
    async def start_bot(cls):
        LOGGER.info("Creating client from BOT_TOKEN")
        cls.ID = Config.BOT_TOKEN.split(":", 1)[0]

        # Prepare client arguments based on library compatibility
        client_args = {
            "name": cls.ID,
            "api_id": Config.TELEGRAM_API,
            "api_hash": Config.TELEGRAM_HASH,
            "proxy": Config.TG_PROXY,
            "bot_token": Config.BOT_TOKEN,
            "workdir": "/usr/src/app",
            "parse_mode": enums.ParseMode.HTML,
            "no_updates": False,  # Ensure updates are enabled
        }

        # Add kurigram-specific parameters
        if USING_KURIGRAM:
            client_args["max_concurrent_transmissions"] = 100

        cls.bot = Client(**client_args)

        try:
            await cls.bot.start()
            cls.NAME = cls.bot.me.username

            # Add decorator wrapper for cross-library compatibility after successful start
            if not hasattr(cls.bot, "on_message") or IS_NEKOZEE:
                # For Nekozee or libraries without standard decorators
                cls.bot = DecoratorWrapper(cls.bot)
                LOGGER.info("Applied decorator wrapper for library compatibility")
        except KeyError as e:
            if str(e) == "None":
                LOGGER.error(
                    "Failed to connect to Telegram: DataCenter ID is None. This might be due to network issues or API configuration."
                )
                LOGGER.error(
                    "Please check your internet connection and TELEGRAM_API/TELEGRAM_HASH configuration."
                )
                raise Exception(
                    "Failed to connect to Telegram servers. Check your internet connection and API configuration."
                ) from e
            raise

    @classmethod
    async def start_user(cls):
        # Check if USER_SESSION_STRING is a valid string with content
        if (
            Config.USER_SESSION_STRING
            and isinstance(Config.USER_SESSION_STRING, str)
            and len(Config.USER_SESSION_STRING) > 0
        ):
            LOGGER.info("Creating client from USER_SESSION_STRING")
            try:
                # Prepare user client arguments based on library compatibility
                user_args = {
                    "name": "user",
                    "api_id": Config.TELEGRAM_API,
                    "api_hash": Config.TELEGRAM_HASH,
                    "proxy": Config.TG_PROXY,
                    "session_string": Config.USER_SESSION_STRING,
                    "parse_mode": enums.ParseMode.HTML,
                    "no_updates": True,
                }

                # Add kurigram-specific parameters
                if USING_KURIGRAM:
                    user_args["max_concurrent_transmissions"] = 100

                cls.user = Client(**user_args)
                await cls.user.start()
                cls.IS_PREMIUM_USER = cls.user.me.is_premium
                if cls.IS_PREMIUM_USER:
                    cls.MAX_SPLIT_SIZE = 4194304000
            except KeyError as e:
                if str(e) == "None":
                    LOGGER.error(
                        "Failed to connect to Telegram: DataCenter ID is None. This might be due to network issues or API configuration."
                    )
                    LOGGER.error(
                        "Please check your internet connection and TELEGRAM_API/TELEGRAM_HASH configuration."
                    )
                    cls.IS_PREMIUM_USER = False
                    cls.user = None
                else:
                    raise
            except Exception as e:
                LOGGER.error(f"Failed to start client from USER_SESSION_STRING. {e}")
                cls.IS_PREMIUM_USER = False
                cls.user = None
        elif Config.USER_SESSION_STRING and not isinstance(
            Config.USER_SESSION_STRING, str
        ):
            cls.IS_PREMIUM_USER = False
            cls.user = None

    @classmethod
    async def start_hclient(cls, no, b_token):
        try:
            # Prepare helper client arguments based on library compatibility
            helper_args = {
                "name": f"helper{no}",
                "api_id": Config.TELEGRAM_API,
                "api_hash": Config.TELEGRAM_HASH,
                "proxy": Config.TG_PROXY,
                "bot_token": b_token,
                "parse_mode": enums.ParseMode.HTML,
                "no_updates": True,
            }

            # Add kurigram-specific parameters
            if USING_KURIGRAM:
                helper_args["max_concurrent_transmissions"] = 20

            hbot = Client(**helper_args)
            await hbot.start()
            LOGGER.info(f"Helper Bot [@{hbot.me.username}] Started!")
            cls.helper_bots[no], cls.helper_loads[no] = hbot, 0
        except Exception as e:
            LOGGER.error(f"Failed to start helper bot {no} from HELPER_TOKENS. {e}")
            cls.helper_bots.pop(no, None)

    @classmethod
    async def start_helper_bots(cls):
        if not Config.HELPER_TOKENS:
            LOGGER.warning(
                "No HELPER_TOKENS found, hyper download will not be available"
            )
            return
        async with cls._hlock:
            await gather(
                *(
                    cls.start_hclient(no, b_token)
                    for no, b_token in enumerate(
                        Config.HELPER_TOKENS.split(), start=1
                    )
                )
            )
        if cls.helper_bots:
            LOGGER.info(
                f"Started {len(cls.helper_bots)} helper bots for hyper download"
            )
        else:
            LOGGER.warning(
                "Failed to start any helper bots, hyper download will not be available"
            )

    @classmethod
    async def stop(cls):
        if cls.bot:
            await cls.bot.stop()
            cls.bot = None
            LOGGER.info("Bot client stopped.")

        if cls.user:
            await cls.user.stop()
            cls.user = None
            LOGGER.info("User client stopped.")

        if cls.helper_bots:
            await gather(*[h_bot.stop() for h_bot in cls.helper_bots.values()])
            cls.helper_bots = {}
            LOGGER.info("Helper bots stopped.")

        cls.IS_PREMIUM_USER = False
        cls.MAX_SPLIT_SIZE = 2097152000

    @classmethod
    async def reload(cls):
        async with cls._lock:
            await cls.bot.restart()
            if cls.user:
                await cls.user.restart()
            if cls.helper_bots:
                await gather(
                    *[h_bot.restart() for h_bot in cls.helper_bots.values()]
                )
            LOGGER.info("All clients restarted")

    @classmethod
    def are_helper_bots_available(cls):
        """Check if helper bots are available for hyper download"""
        return len(cls.helper_bots) > 0
