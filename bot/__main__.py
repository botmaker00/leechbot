# ruff: noqa: E402
import asyncio
import gc
import os
import warnings
from asyncio import create_task, gather

# Set environment variable to suppress Python warnings (most aggressive approach)
os.environ.setdefault("PYTHONWARNINGS", "ignore::SyntaxWarning")

# Comprehensive warning suppression for md2tgmd and latex2unicode libraries
# These libraries have invalid escape sequences that generate SyntaxWarning in Python 3.12+

# Method 1: Standard warning filters
warnings.filterwarnings(
    "ignore", category=SyntaxWarning
)  # Global SyntaxWarning suppression
warnings.filterwarnings(
    "ignore", message=".*invalid escape sequence.*"
)  # Specific message pattern
warnings.filterwarnings("ignore", module="md2tgmd")  # All warnings from md2tgmd
warnings.filterwarnings(
    "ignore", module="latex2unicode"
)  # All warnings from latex2unicode


# Method 2: Aggressive suppression using custom warning handler
def custom_warning_handler(
    message, category, filename, lineno, file=None, line=None
):
    """Custom warning handler that suppresses md2tgmd and latex2unicode warnings."""
    # Convert message to string for checking
    msg_str = str(message)
    filename_str = str(filename)

    # Suppress if it's a SyntaxWarning about invalid escape sequences
    if category == SyntaxWarning and "invalid escape sequence" in msg_str:
        return

    # Suppress if it's from md2tgmd or latex2unicode files
    if "md2tgmd" in filename_str or "latex2unicode" in filename_str:
        return

    # For all other warnings, use the default handler
    warnings._showwarning_orig(message, category, filename, lineno, file, line)


# Store original warning handler and install custom one
if not hasattr(warnings, "_showwarning_orig"):
    warnings._showwarning_orig = warnings.showwarning
    warnings.showwarning = custom_warning_handler

from pyrogram.types import BotCommand

from . import LOGGER, bot_loop
from .core.config_manager import Config, SystemEnv

LOGGER.info("Loading config...")
Config.load()
SystemEnv.load()

from .core.startup import load_settings

bot_loop.run_until_complete(load_settings())

from .core.aeon_client import TgClient
from .helper.telegram_helper.bot_commands import BotCommands

COMMANDS = {
    "MirrorCommand": "- Start mirroring",
    "LeechCommand": "- Start leeching",
    "JdMirrorCommand": "- Mirror using Jdownloader",
    "JdLeechCommand": "- Leech using jdownloader",
    "NzbMirrorCommand": "- Mirror nzb files",
    "NzbLeechCommand": "- Leech nzb files",
    "YtdlCommand": "- Mirror yt-dlp supported link",
    "YtdlLeechCommand": "- Leech through yt-dlp supported link",
    "GdlCommand": "- Mirror gallery-dl supported link",
    "GdlLeechCommand": "- Leech through gallery-dl supported link",
    "StreamripMirrorCommand": "- Mirror music from streaming platforms",
    "StreamripLeechCommand": "- Leech music from streaming platforms",
    "StreamripSearchCommand": "- Search music across platforms",
    "ZotifyMirrorCommand": "- Mirror music from Spotify",
    "ZotifyLeechCommand": "- Leech music from Spotify",
    "ZotifySearchCommand": "- Search music on Spotify",
    "MusicMirrorCommand": "- Mirror music from multiple platforms (Tidal, Qobuz, Apple Music, Spotify, Deezer)",
    "MusicLeechCommand": "- Leech music from multiple platforms (Tidal, Qobuz, Apple Music, Spotify, Deezer)",
    "CloneCommand": "- Copy file/folder to Drive",
    "MegaSearchCommand": "- Search MEGA drive for files/folders",
    "MediaInfoCommand": "- Get mediainfo",
    "SoxCommand": "- Get audio spectrum",
    "ForceStartCommand": "- Start task from queue",
    "CountCommand": "- Count file/folder on Google Drive",
    "ListCommand": "- Search in Drive",
    "SearchCommand": "- Search in Torrent",
    "UserSetCommand": "- User settings",
    "MediaToolsCommand": "- Media tools settings for watermark and other media features",
    "MediaToolsHelpCommand": "- View detailed help for merge and watermark features",
    "StatusCommand": "- Get mirror status message (/s, /statusall, /sall)",
    "StatsCommand": "- Check Bot & System stats",
    "CancelAllCommand": "- Cancel all tasks added by you to the bot",
    "HelpCommand": "- Get detailed help",
    "FontStylesCommand": "- View available font styles for leech",
    "MediaSearchCommand": "- Search for media files (/mds) or reply to a message",
    "SpeedTest": "- Get speedtest result",
    "GenSessionCommand": "- Generate Pyrogram session string",
    "VirusTotalCommand": "- Scan files or URLs for viruses using VirusTotal",
    "PasteCommand": "- Paste text to katb.in website",
    "ShortnerCommand": "- Shorten URLs with Bitly API and generate QR codes",
    "QRCodeCommand": "- Generate QR codes from text or URLs with customizable options",
    "NSFWStatsCommand": "- Get NSFW detection statistics",
    "NSFWTestCommand": "- Test NSFW detection on images",
    # QuickInfo Commands
    "QuickInfoCommand": "- Get chat/user information with interactive buttons",
    "File2LinkCommand": "- Convert Telegram media files into direct streaming links",
    "ToolCommand": "- Media conversion and processing tools (gif, sticker, emoji, voice, etc.)",
    # IndexCommand removed - media indexing functionality disabled
    "BotSetCommand": "- [ADMIN] Open Bot settings",
    "ForwardCommand": "- [SUDO] Forward messages between chats",
    "LogCommand": "- [ADMIN] View log",
    "RestartCommand": "- [ADMIN] Restart the bot",
    "WhisperCommand": "- Send private whisper messages in group chats",
    # Contact Commands
    "ContactCommand": "- Contact the bot owner (available to all users)",
    # Scraping Commands
    "ScrapCommand": "- Scrape movie info (title, size, magnet) from 1tamilmv",
    # Cat API Commands
    "NekoCommand": "- Get adorable cat images with voting system 🐱💕",
}

# Add AI command if enabled
if Config.AI_ENABLED:
    COMMANDS["AskCommand"] = "- Ask AI questions and get intelligent responses"

# Add IMDB command if enabled
if Config.IMDB_ENABLED:
    COMMANDS["IMDBCommand"] = "- Search for movies or TV series info"

# Add TMDB command if enabled
if Config.TMDB_ENABLED:
    COMMANDS["TMDBCommand"] = "- Search TMDB for movies, TV shows, and people"

# Add Truecaller command if enabled
if Config.TRUECALLER_ENABLED:
    COMMANDS["TruecallerCommand"] = "- Lookup phone numbers using Truecaller"

# Add encoding/decoding commands if enabled
if Config.ENCODING_ENABLED:
    COMMANDS["EncodeCommand"] = "- Encode text using various methods"

if Config.DECODING_ENABLED:
    COMMANDS["DecodeCommand"] = "- Decode encoded text with auto-detection"

# Add trace.moe command if enabled
if Config.TRACE_MOE_ENABLED:
    COMMANDS["TraceCommand"] = "- Identify anime from images, videos, or GIFs"

# Add phishcheck command if enabled
if Config.PHISH_DIRECTORY_ENABLED:
    COMMANDS["PhishCheckCommand"] = (
        "- Check domains and emails for phishing/security threats"
    )

# Add WOT command if enabled (includes AbuseIPDB integration)
if Config.WOT_ENABLED or Config.ABUSEIPDB_ENABLED:
    COMMANDS["WotCommand"] = (
        "- Check website, domain, and IP reputation using WOT and AbuseIPDB"
    )

# Add OSINT command (sudo only)
COMMANDS["OSINTCommand"] = "- Comprehensive OSINT intelligence suite (sudo only)"

# Add Weather commands if enabled
if Config.WEATHER_ENABLED:
    COMMANDS["WeatherCommand"] = (
        "- Get current weather with beautiful images and forecasts"
    )

# Setup Commands
COMMAND_OBJECTS = [
    BotCommand(
        (
            getattr(BotCommands, cmd)[0]
            if isinstance(getattr(BotCommands, cmd), list)
            else getattr(BotCommands, cmd)
        ),
        description,
    )
    for cmd, description in COMMANDS.items()
]


# Set Bot Commands
async def set_commands():
    if Config.SET_COMMANDS:
        await TgClient.bot.set_bot_commands(COMMAND_OBJECTS)


# Main Function
async def main():
    # Initialize garbage collection with optimized thresholds
    LOGGER.info("Configuring garbage collection for optimal performance...")
    gc.enable()
    # Use balanced thresholds to reduce GC overhead while maintaining memory efficiency
    # Optimized for lower memory usage and reduced CPU overhead
    gc.set_threshold(
        1500, 20, 20
    )  # Balanced thresholds to reduce GC frequency while preventing memory bloat

    # Start web server immediately for Heroku PORT binding
    from os import environ

    from .core.startup import (
        load_configurations,
        save_settings,
        start_bot,
        update_aria2_options,
        update_nzb_options,
        update_qb_options,
        update_variables,
    )

    if environ.get("PORT"):
        LOGGER.info("Heroku deployment detected - starting web server immediately")
        from .core.startup import start_web_server_early

        await start_web_server_early()

    await gather(
        TgClient.start_bot(), TgClient.start_user(), TgClient.start_helper_bots()
    )

    # Load Zotify credentials from database after bot clients are started
    from .core.startup import load_zotify_credentials_from_db

    try:
        await load_zotify_credentials_from_db()
    except Exception as e:
        LOGGER.error(f"Failed to restore Zotify credentials: {e}")

    await gather(load_configurations(), update_variables())
    from .core.torrent_manager import TorrentManager

    await TorrentManager.initiate()
    await gather(
        update_qb_options(),
        update_aria2_options(),
        update_nzb_options(),
    )

    # Start the scheduled deletion checker and other tasks
    await start_bot()
    from .core.jdownloader_booter import jdownloader
    from .helper.ext_utils.files_utils import clean_all
    from .helper.ext_utils.gc_utils import log_memory_usage, smart_garbage_collection
    from .helper.ext_utils.telegraph_helper import telegraph
    from .helper.mirror_leech_utils.rclone_utils.serve import rclone_serve_booter
    from .modules import (
        get_packages_version,
        initiate_search_tools,
        restart_notification,
    )

    await gather(
        set_commands(),
        jdownloader.boot(),
    )
    from .helper.ext_utils.task_manager import start_queue_processor
    from .helper.ext_utils.task_monitor import start_monitoring

    # Optimized startup sequence - prioritize essential tasks
    await gather(
        save_settings(),
        clean_all(),
        restart_notification(),
        telegraph.create_account(),
    )

    # Initialize non-critical services with delay to reduce startup load
    create_task(initiate_search_tools())  # noqa: RUF006
    create_task(get_packages_version())  # noqa: RUF006
    create_task(rclone_serve_booter())  # noqa: RUF006

    # Start background services immediately without delays
    LOGGER.info("Starting background services...")

    # Start task monitoring system and queue processor only if task monitoring is enabled
    # Optimized to reduce resource usage by default
    if Config.TASK_MONITOR_ENABLED:
        LOGGER.info("Starting optimized task monitoring system...")
        create_task(start_monitoring())  # noqa: RUF006

        # Start queue processor with reduced frequency to save resources
        LOGGER.info("Starting optimized queue processor...")
        create_task(start_queue_processor())  # noqa: RUF006
    else:
        LOGGER.info(
            "Task monitoring is disabled - skipping task monitor and queue processor (recommended for resource optimization)"
        )

    # Initialize auto-restart scheduler
    from .helper.ext_utils.auto_restart import init_auto_restart

    init_auto_restart()

    # User data is already loaded from database in load_settings()
    # No need to load again from JSON file

    # Initialize whisper cleanup task
    LOGGER.info("Initializing whisper cleanup task...")
    from .modules.whisper import start_whisper_cleanup

    create_task(start_whisper_cleanup())  # noqa: RUF006

    # Automatic indexing removed - media indexing functionality disabled

    # Initial garbage collection and memory usage logging (less aggressive during startup)
    LOGGER.info("Performing initial garbage collection...")
    smart_garbage_collection(
        aggressive=False  # Use less aggressive mode during startup to reduce resource usage
    )
    log_memory_usage()

    LOGGER.info("All background services initialized successfully")

    # Adjust garbage collection thresholds for optimal operation after startup
    LOGGER.info("Adjusting garbage collection thresholds for optimal operation...")
    gc.set_threshold(
        1000, 15, 15
    )  # Balanced thresholds for optimal memory/CPU trade-off


bot_loop.run_until_complete(main())

from .core.handlers import add_handlers
from .helper.ext_utils.bot_utils import create_help_buttons
from .helper.listeners.aria2_listener import add_aria2_callbacks

add_aria2_callbacks()
create_help_buttons()
add_handlers()


# Setup cleanup handler
import atexit

from .helper.ext_utils.db_handler import database


async def cleanup():
    """Clean up resources before shutdown"""
    LOGGER.info("Performing cleanup before shutdown...")

    # Cleanup streamrip sessions to prevent unclosed session warnings
    try:
        from .helper.mirror_leech_utils.streamrip_utils.search_handler import (
            cleanup_all_streamrip_sessions,
        )

        await cleanup_all_streamrip_sessions()
    except Exception as e:
        LOGGER.error(f"Error during streamrip cleanup: {e}")

    # Streaming functionality is integrated with wserver - no separate cleanup needed
    LOGGER.info("Streaming functionality cleanup handled by wserver")

    # Stop database heartbeat task and disconnect from database
    try:
        await database.stop_heartbeat()
        await database.disconnect()
    except Exception as e:
        # Handle database cleanup errors gracefully
        if "closed" in str(e).lower():
            LOGGER.debug(f"Database was already closed during cleanup: {e}")
        else:
            LOGGER.error(f"Error during database cleanup: {e}")

    LOGGER.info("Cleanup completed")


# Register cleanup function to run at exit
def run_cleanup():
    bot_loop.run_until_complete(cleanup())


atexit.register(run_cleanup)


# Set up exception handler for unhandled task exceptions
def handle_loop_exception(loop, context):
    """Handle unhandled exceptions in the event loop"""
    exception = context.get("exception")
    if exception:
        # Filter out common handler removal errors that are harmless
        if isinstance(
            exception, ValueError
        ) and "list.remove(x): x not in list" in str(exception):
            LOGGER.debug(f"Handler removal error (harmless): {exception}")
        # Filter out aria2 RPC exceptions for missing GIDs (these are expected during rapid downloads)
        elif "Aria2rpcException" in str(type(exception)) and "is not found" in str(
            exception
        ):
            LOGGER.debug(
                f"Aria2 GID not found (expected during rapid downloads): {exception}"
            )
        # Filter out transport closing errors that are harmless during shutdown
        elif "closing transport" in str(exception).lower():
            LOGGER.debug(
                f"Transport closing error (harmless during shutdown): {exception}"
            )
        # Filter out QueryIdInvalid errors from YT-DLP callback queries (these are expected when callbacks expire)
        elif "QUERY_ID_INVALID" in str(exception) or "QueryIdInvalid" in str(
            type(exception).__name__
        ):
            LOGGER.debug(f"Callback query expired (expected behavior): {exception}")
        # Filter out Pyrogram session read errors that are common during concurrent operations
        elif (
            "read() called while another coroutine is already waiting for incoming data"
            in str(exception)
        ):
            LOGGER.debug(
                f"Pyrogram concurrent read operation (expected during high load): {exception}"
            )
        # Filter out NoneType read errors from Pyrogram sessions
        elif "'NoneType' object has no attribute 'read'" in str(exception):
            LOGGER.debug(
                f"Pyrogram session read error (session may be closed): {exception}"
            )
        # Filter out database closed errors during shutdown/restart
        elif any(
            keyword in str(exception).lower()
            for keyword in [
                "cannot operate on a closed database",
                "connection closed",
                "client is closed",
                "database is closed",
            ]
        ):
            LOGGER.debug(
                f"Database connection error (expected during shutdown/restart): {exception}"
            )
        # Filter out other common Pyrogram session errors
        elif any(
            keyword in str(exception).lower()
            for keyword in [
                "session.recv_worker",
                "session.restart",
                "connection reset",
                "connection aborted",
                "session closed",
            ]
        ):
            LOGGER.debug(
                f"Pyrogram session error (expected during network issues): {exception}"
            )
        # Filter out NoneType iteration errors from YT-DLP processing (these are being handled by our fixes)
        elif "argument of type 'NoneType' is not iterable" in str(exception):
            future_info = str(context.get("future", ""))
            if "YtDlp.new_event" in future_info:
                LOGGER.debug(
                    f"YT-DLP NoneType iteration error (handled by defensive coding): {exception}"
                )
            else:
                # Log with more details for non-YtDlp NoneType errors to help identify the source
                LOGGER.warning(
                    f"NoneType iteration error in {future_info}: {exception}"
                )
        else:
            LOGGER.error(f"Unhandled loop exception: {exception}")
            LOGGER.error(f"Exception context: {context}")
    else:
        LOGGER.warning(f"Loop exception without exception object: {context}")


# Set the exception handler for the event loop
bot_loop.set_exception_handler(handle_loop_exception)
asyncio.set_event_loop(bot_loop)

# Run Bot
LOGGER.info("Bot Started!")
try:
    bot_loop.run_forever()
except (KeyboardInterrupt, SystemExit):
    LOGGER.info("Bot stopping...")
    run_cleanup()
    LOGGER.info("Bot stopped gracefully")
