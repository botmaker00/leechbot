# ruff: noqa: E402
# Fix IDE issues by adding type annotations and import comments
from uvloop import install  # type: ignore

install()

import os
import subprocess
import time
import warnings


# Configure warning filters to suppress known issues
def configure_warning_filters():
    """Configure warning filters to suppress known library issues."""
    # Comprehensive suppression for md2tgmd and latex2unicode SyntaxWarning issues
    warnings.filterwarnings(
        "ignore", category=SyntaxWarning
    )  # Global SyntaxWarning suppression
    warnings.filterwarnings(
        "ignore", message=".*invalid escape sequence.*"
    )  # Specific pattern
    warnings.filterwarnings("ignore", module="md2tgmd")  # All md2tgmd warnings
    warnings.filterwarnings(
        "ignore", module="latex2unicode"
    )  # All latex2unicode warnings

    # Additional pattern-based suppression for specific warning messages
    warnings.filterwarnings("ignore", message=".*md2tgmd.*")
    warnings.filterwarnings("ignore", message=".*latex2unicode.*")


# Apply warning filters immediately
configure_warning_filters()
from asyncio import Lock, new_event_loop, set_event_loop
from datetime import datetime
from logging import (
    ERROR,
    INFO,
    WARNING,
    FileHandler,
    Filter,
    Formatter,
    LogRecord,
    StreamHandler,
    basicConfig,
    getLogger,
)
from time import time as time_func

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
from pytz import timezone

from sabnzbdapi import SabnzbdClient

try:
    import requests
except ImportError:
    requests = None


class SuppressUnclosedSessionFilter(Filter):
    """Filter to suppress unclosed client session and connector warnings"""

    def filter(self, record: LogRecord) -> bool:
        # Suppress unclosed client session errors
        if "Unclosed client session" in record.getMessage():
            return False
        # Suppress unclosed connector errors
        if "Unclosed connector" in record.getMessage():
            return False
        # Suppress client session object warnings
        if "client_session:" in record.getMessage():
            return False
        # Suppress connector object warnings
        if "connector:" in record.getMessage():
            return False
        # Suppress Pyrogram unknown constructor errors to prevent log flooding
        return "The server sent an unknown constructor" not in record.getMessage()


class SuppressZotifyNoiseFilter(Filter):
    """Filter to suppress specific Zotify/librespot noise logs"""

    def filter(self, record: LogRecord) -> bool:
        message = record.getMessage()

        # Suppress specific librespot core logs
        if "Received license_version:" in message:
            return False
        if "Received country_code:" in message:
            return False
        if "Skipping 1f" in message:
            return False
        if "Skipping 69" in message:
            return False
        if "Session.Receiver started" in message:
            return False

        # Suppress metadata-related logs from external libraries
        if "Metadata settings - All:" in message:
            return False
        if "Video metadata - Title:" in message:
            return False
        if "Audio metadata - Title:" in message:
            return False
        if "Subtitle metadata - Title:" in message:
            return False
        if "Using metadata-all from command line:" in message:
            return False
        if "Applying metadata to video file:" in message:
            return False

        return "Skipping unknown command cmd:" not in message


getLogger("requests").setLevel(WARNING)
getLogger("urllib3").setLevel(WARNING)
getLogger("pyrogram").setLevel(ERROR)
getLogger("httpx").setLevel(WARNING)
getLogger("pymongo").setLevel(WARNING)
getLogger("aiohttp").setLevel(WARNING)
getLogger("bot.modules.media_search").setLevel(ERROR)

# Suppress Zotify/librespot core logs for cleaner output
getLogger("librespot.core").setLevel(ERROR)  # Only show errors, suppress info logs
getLogger("librespot").setLevel(WARNING)  # Suppress all librespot info logs

# Suppress common external library logs that generate metadata noise
getLogger("common").setLevel(WARNING)  # Suppress common library info logs
getLogger("command_gen").setLevel(WARNING)  # Suppress command generation info logs

# Apply the unclosed session filter to aiohttp loggers specifically
aiohttp_client_logger = getLogger("aiohttp.client")
aiohttp_client_logger.addFilter(SuppressUnclosedSessionFilter())

aiohttp_connector_logger = getLogger("aiohttp.connector")
aiohttp_connector_logger.addFilter(SuppressUnclosedSessionFilter())

# Also apply to the main aiohttp logger
aiohttp_main_logger = getLogger("aiohttp")
aiohttp_main_logger.addFilter(SuppressUnclosedSessionFilter())

bot_start_time = time_func()

bot_loop = new_event_loop()
set_event_loop(bot_loop)


class CustomFormatter(Formatter):
    def formatTime(
        self,
        record: LogRecord,
        datefmt: str | None,
    ) -> str:
        dt: datetime = datetime.fromtimestamp(
            record.created,
            tz=timezone("Asia/Dhaka"),
        )
        return dt.strftime(datefmt)

    def format(self, record: LogRecord) -> str:
        return super().format(record).replace(record.levelname, record.levelname[:1])


formatter = CustomFormatter(
    "[%(asctime)s] %(levelname)s - %(message)s [%(module)s:%(lineno)d]",
    datefmt="%d-%b %I:%M:%S %p",
)

file_handler = FileHandler("log.txt")
file_handler.setFormatter(formatter)
file_handler.addFilter(SuppressUnclosedSessionFilter())
file_handler.addFilter(SuppressZotifyNoiseFilter())  # Add Zotify noise filter

stream_handler = StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.addFilter(SuppressUnclosedSessionFilter())
stream_handler.addFilter(SuppressZotifyNoiseFilter())  # Add Zotify noise filter

basicConfig(handlers=[file_handler, stream_handler], level=INFO)

LOGGER = getLogger(__name__)

# Enable global orjson optimization for maximum JSON performance across entire bot
try:
    from bot.helper.ext_utils.orjson_optimizer import auto_enable_global_orjson

    auto_enable_global_orjson()
except ImportError:
    # orjson optimizer not available, continue with standard json
    LOGGER.info("orjson optimizer not available - using standard json")

cpu_no = os.cpu_count()

DOWNLOAD_DIR = "/usr/src/app/downloads/"
intervals = {
    "status": {},
    "qb": "",
    "jd": "",
    "nzb": "",
    "stopAll": False,
}
qb_torrents = {}
user_data = {}
aria2_options = {}
qbit_options = {}
nzb_options = {}
queued_dl = {}
queued_up = {}
status_dict = {}
task_dict = {}
jd_downloads = {}
nzb_jobs = {}
rss_dict = {}
auth_chats = {}
excluded_extensions = ["aria2", "!qB"]
drives_names = []
drives_ids = []
index_urls = []
sudo_users = []
non_queued_dl = set()
non_queued_up = set()
multi_tags = set()
task_dict_lock = Lock()
queue_dict_lock = Lock()
qb_listener_lock = Lock()
cpu_eater_lock = Lock()
same_directory_lock = Lock()
nzb_listener_lock = Lock()
jd_listener_lock = Lock()
shorteners_list = []

sabnzbd_client = SabnzbdClient(
    host="http://localhost",
    api_key="admin",
    port="8070",
)


def is_qbittorrent_running():
    """Check if qBittorrent is already running by testing the web UI and process"""
    # First check if the process is running
    try:
        result = subprocess.run(
            ["pgrep", "-f", "qbittorrent-nox|xnox"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Process is running, now check if web UI is accessible
            if requests is not None:
                try:
                    response = requests.get(
                        "http://localhost:8090/api/v2/app/version", timeout=2
                    )
                    return response.status_code == 200
                except (
                    requests.exceptions.RequestException,
                    requests.exceptions.Timeout,
                ):
                    return False
            else:
                # If requests is not available, assume it's running if process exists
                return True
    except (
        subprocess.TimeoutExpired,
        subprocess.SubprocessError,
        FileNotFoundError,
    ):
        pass

    # If process check failed, try web UI check as fallback
    if requests is not None:
        try:
            response = requests.get(
                "http://localhost:8090/api/v2/app/version", timeout=2
            )
            if response.status_code == 200:
                return True
        except (requests.exceptions.RequestException, requests.exceptions.Timeout):
            pass

    return False


try:
    # Check if qBittorrent is already running before starting it
    if not is_qbittorrent_running():
        LOGGER.info("Starting qBittorrent daemon...")

        # Start qBittorrent in daemon mode
        try:
            process = subprocess.Popen(
                ["xnox", "-d", f"--profile={os.getcwd()}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait for the daemon to start (daemon process exits after spawning)
            time.sleep(3)

            # For daemon mode, the parent process exits with code 0 after spawning the daemon
            # So we need to check if the daemon is actually running by checking for the process
            retry_count = 0
            max_retries = 10
            daemon_started = False

            while retry_count < max_retries:
                if is_qbittorrent_running():
                    LOGGER.info("qBittorrent daemon started successfully")
                    daemon_started = True
                    break
                time.sleep(1)
                retry_count += 1

            if not daemon_started:
                # Check for any error output
                stdout, stderr = process.communicate()
                stderr_text = stderr.decode().strip() if stderr else ""

                if stderr_text:
                    if (
                        "You cannot use -d (or --daemon): qBittorrent is already running"
                        in stderr_text
                    ):
                        LOGGER.info(
                            "qBittorrent is already running (detected from error message)"
                        )
                    else:
                        LOGGER.error(f"qBittorrent startup failed: {stderr_text}")
                else:
                    LOGGER.warning(
                        "qBittorrent daemon may not have started - web UI not accessible"
                    )

        except subprocess.SubprocessError as e:
            LOGGER.error(f"Failed to start qBittorrent process: {e}")
    else:
        LOGGER.info("qBittorrent is already running - skipping daemon startup")

except (FileNotFoundError, PermissionError) as e:
    LOGGER.warning(f"qBittorrent binary not found or permission denied: {e}")
except Exception as e:
    LOGGER.error(f"Unexpected error during qBittorrent startup: {e}")

try:
    subprocess.run(
        [
            "xnzb",
            "-f",
            "sabnzbd/SABnzbd.ini",
            "-s",
            ":::8070",
            "-b",
            "0",
            "-d",
            "-c",
            "-l",
            "0",
            "--console",
        ],
        check=False,
    )
except (FileNotFoundError, PermissionError):
    pass  # Ignore if xnzb is not available or permission denied


scheduler = AsyncIOScheduler(event_loop=bot_loop)

# Initialize streaming server
StartTime = time_func()
