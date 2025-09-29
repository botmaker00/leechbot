# ruff: noqa: E402
from uvloop import install

install()
from asyncio import sleep
from contextlib import asynccontextmanager
from logging import INFO, WARNING, FileHandler, StreamHandler, basicConfig, getLogger
from urllib.parse import urlparse

from aioaria2 import Aria2HttpClient  # type: ignore
from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError
from aioqbt.client import create_client  # type: ignore
from aioqbt.exc import AQError
from fastapi import FastAPI, HTTPException, Request  # type: ignore
from fastapi.responses import HTMLResponse, JSONResponse  # type: ignore
from fastapi.templating import Jinja2Templates  # type: ignore

from bot import LOGGER
from sabnzbdapi import SabnzbdClient
from web.nodes import extract_file_ids, make_tree

getLogger("httpx").setLevel(WARNING)
getLogger("aiohttp").setLevel(WARNING)

aria2 = None
qbittorrent = None
sabnzbd_client = SabnzbdClient(
    host="http://localhost",
    api_key="admin",
    port="8070",
)

from bot.core.config_manager import Config

# Load configuration for web server process
try:
    # Force reload configuration to ensure fresh values
    Config.load()
    from bot.core.config_manager import SystemEnv

    SystemEnv.load()

    # Also try to reload Config class to get latest values
    import importlib

    from bot.core import config_manager

    importlib.reload(config_manager)
    from bot.core.config_manager import Config as ReloadedConfig

    # Use reloaded config if it has different values
    if (
        hasattr(ReloadedConfig, "FILE2LINK_BIN_CHANNEL")
        and ReloadedConfig.FILE2LINK_BIN_CHANNEL
    ):
        Config.FILE2LINK_BIN_CHANNEL = ReloadedConfig.FILE2LINK_BIN_CHANNEL
        Config.FILE2LINK_ENABLED = getattr(
            ReloadedConfig, "FILE2LINK_ENABLED", False
        )

    # Load database settings asynchronously when needed
    import asyncio
    import os

    async def load_web_server_config():
        try:
            # First, try to load shared configuration from main bot process

            try:
                import json
                import tempfile

                config_file_path = os.path.join(
                    tempfile.gettempdir(), "aimleechbot_shared_config.json"
                )

                if os.path.exists(config_file_path):
                    with open(config_file_path) as f:
                        shared_config = json.load(f)

                    # Apply shared configuration
                    for key, value in shared_config.items():
                        if hasattr(Config, key) and value:
                            setattr(Config, key, value)

                else:
                    LOGGER.info("No shared configuration file found")

            except Exception as e:
                LOGGER.warning(f"Failed to load shared configuration: {e}")

            # Database settings are already loaded in the main bot process
            # Web server doesn't need to reload user data

            # Debug configuration values after database loading
            db_bin_channel = getattr(Config, "FILE2LINK_BIN_CHANNEL", 0)
            getattr(Config, "FILE2LINK_ENABLED", False)
            getattr(Config, "FILE2LINK_BASE_URL", "")

            # If database doesn't have the value (still 0), try environment variable as fallback
            if db_bin_channel == 0:
                env_bin_channel = os.getenv("FILE2LINK_BIN_CHANNEL")

                if env_bin_channel and env_bin_channel != "0":
                    try:
                        Config.FILE2LINK_BIN_CHANNEL = int(env_bin_channel)

                    except ValueError:
                        LOGGER.error(f"Invalid environment value: {env_bin_channel}")
                else:
                    LOGGER.warning(
                        "No valid FILE2LINK_BIN_CHANNEL found in database or environment"
                    )
            else:
                # Update Config object with database value
                Config.FILE2LINK_BIN_CHANNEL = db_bin_channel

        except Exception as e:
            LOGGER.error(f"Failed to load database settings: {e}")
            # Fallback to environment if database loading fails

            env_bin_channel = os.getenv("FILE2LINK_BIN_CHANNEL")
            if env_bin_channel and env_bin_channel != "0":
                try:
                    Config.FILE2LINK_BIN_CHANNEL = int(env_bin_channel)

                except ValueError:
                    LOGGER.error(
                        f"Invalid emergency fallback value: {env_bin_channel}"
                    )

    # Store the config loading function for later use
    _config_loader = load_web_server_config


except Exception as e:
    LOGGER.error(f"Failed to load configuration for web server: {e}")
    _config_loader = None


# Lazy imports for File2Link to avoid startup delays
def get_stream_utils():
    """Lazy import of stream utilities to avoid startup delays"""
    from bot.helper.stream_utils import (
        ByteStreamer,
        ParallelByteStreamer,
        ParallelDownloader,
        RawByteStreamer,
        StreamClientManager,
        create_raw_streamer,
        get_fname,
        get_hash,
        get_mime_type,
        is_streamable_file,
        validate_stream_request,
    )

    return (
        StreamClientManager,
        ByteStreamer,
        ParallelByteStreamer,
        ParallelDownloader,
        RawByteStreamer,
        create_raw_streamer,
        get_hash,
        get_fname,
        validate_stream_request,
        get_mime_type,
        is_streamable_file,
    )


def get_tg_client():
    """Lazy import of TgClient to avoid startup delays"""
    from bot.core.aeon_client import TgClient

    return TgClient


async def get_file2link_bin_channel():
    """Get FILE2LINK_BIN_CHANNEL from database or config"""
    try:
        # First try Config object
        config_value = getattr(Config, "FILE2LINK_BIN_CHANNEL", None)
        if config_value and config_value != 0:
            return config_value

        # If Config doesn't have it, try database directly
        from bot.core.aeon_client import TgClient
        from bot.helper.ext_utils.db_handler import database

        if not database._return and database.db is not None:
            db_config = await database.db.settings.config.find_one(
                {"_id": TgClient.ID}, {"_id": 0}
            )
            if db_config:
                bin_channel = db_config.get("FILE2LINK_BIN_CHANNEL")
                if bin_channel and bin_channel != 0:
                    # Update Config object for future use
                    Config.FILE2LINK_BIN_CHANNEL = bin_channel
                    return bin_channel

        # Fallback to environment
        import os

        env_channel = os.getenv("FILE2LINK_BIN_CHANNEL")
        if env_channel and env_channel != "0":
            try:
                channel_id = int(env_channel)
                Config.FILE2LINK_BIN_CHANNEL = channel_id
                return channel_id
            except ValueError:
                pass

        return None
    except Exception as e:
        LOGGER.error(f"Error getting FILE2LINK_BIN_CHANNEL: {e}")
        return None


async def init_streaming_client(TgClient):
    """Initialize Telegram clients for streaming (main bot + helper bots)"""
    try:
        # Initialize main bot client if not already initialized
        if TgClient.bot is None:
            import inspect

            from pyrogram import Client, enums

            # Create main bot client with better session management
            TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            # Use in-memory session for web server to avoid file conflicts and auth issues
            import tempfile

            session_dir = tempfile.mkdtemp(prefix="web_sessions_")

            # Check if max_concurrent_transmissions is supported (kurigram vs pyrofork compatibility)
            client_params = list(
                inspect.signature(Client.__init__).parameters.keys()
            )
            client_args = {
                "name": f"web_main_{TgClient.ID}",  # Different session name to avoid conflicts
                "api_id": Config.TELEGRAM_API,
                "api_hash": Config.TELEGRAM_HASH,
                "proxy": Config.TG_PROXY,
                "bot_token": Config.BOT_TOKEN,
                "workdir": session_dir,  # Use temporary directory for sessions
                "parse_mode": enums.ParseMode.HTML,
                "no_updates": True,  # Disable updates for web server client
                "in_memory": True,  # Use in-memory session to avoid auth issues
            }

            # Add kurigram-specific parameters if supported
            if "max_concurrent_transmissions" in client_params:
                client_args["max_concurrent_transmissions"] = 100

            TgClient.bot = Client(**client_args)

            # Start the main bot client
            await TgClient.bot.start()
            TgClient.NAME = TgClient.bot.me.username

        # Initialize helper bots for streaming if HELPER_TOKENS is available
        if Config.HELPER_TOKENS and not TgClient.helper_bots:
            await init_helper_bots_for_streaming(TgClient)
            if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
                pass

    except Exception as e:
        LOGGER.error(f"Failed to initialize streaming clients: {e}")
        raise


async def init_helper_bots_for_streaming(TgClient):
    """Initialize helper bots specifically for web server streaming"""
    try:
        from asyncio import gather

        from pyrogram import Client, enums

        # Initialize helper bot containers if not present
        if not hasattr(TgClient, "helper_bots"):
            TgClient.helper_bots = {}
        if not hasattr(TgClient, "helper_loads"):
            TgClient.helper_loads = {}

        async def start_helper_bot(no, b_token):
            try:
                # Use in-memory session for helper bots to avoid auth issues
                import inspect
                import tempfile

                session_dir = tempfile.mkdtemp(prefix=f"web_helper{no}_")

                # Check if max_concurrent_transmissions is supported (kurigram vs pyrofork compatibility)
                client_params = list(
                    inspect.signature(Client.__init__).parameters.keys()
                )
                helper_args = {
                    "name": f"web_helper{no}",  # Different session name for web server
                    "api_id": Config.TELEGRAM_API,
                    "api_hash": Config.TELEGRAM_HASH,
                    "proxy": Config.TG_PROXY,
                    "bot_token": b_token,
                    "workdir": session_dir,  # Use temporary directory for sessions
                    "parse_mode": enums.ParseMode.HTML,
                    "no_updates": True,
                    "in_memory": True,  # Use in-memory session to avoid auth issues
                }

                # Add kurigram-specific parameters if supported
                if "max_concurrent_transmissions" in client_params:
                    helper_args["max_concurrent_transmissions"] = 20

                hbot = Client(**helper_args)
                await hbot.start()
                TgClient.helper_bots[no] = hbot
                TgClient.helper_loads[no] = 0

            except Exception as e:
                LOGGER.error(f"Failed to start helper bot {no} for streaming: {e}")
                TgClient.helper_bots.pop(no, None)
                TgClient.helper_loads.pop(no, None)

        # Start all helper bots concurrently
        await gather(
            *(
                start_helper_bot(no, b_token)
                for no, b_token in enumerate(Config.HELPER_TOKENS.split(), start=1)
            )
        )

        if not TgClient.helper_bots:
            pass

    except Exception as e:
        LOGGER.error(f"Error initializing helper bots for streaming: {e}")
        # Ensure containers exist even if initialization fails
        if not hasattr(TgClient, "helper_bots"):
            TgClient.helper_bots = {}
        if not hasattr(TgClient, "helper_loads"):
            TgClient.helper_loads = {}


async def validate_channel_access(client, channel_id):
    """Validate if bot has access to the storage channel"""
    try:
        # Try to get chat info
        await client.get_chat(channel_id)
        # Skip message history check as it causes BOT_METHOD_INVALID error
        # Bot access to the channel is sufficient for File2Link functionality
        return True

    except Exception as e:
        error_msg = str(e).lower()
        if "invalid chat_id" in error_msg:
            LOGGER.error(
                f"Invalid chat_id {channel_id}. Please check FILE2LINK_BIN_CHANNEL configuration"
            )
        elif "chat not found" in error_msg:
            LOGGER.error(
                f"Storage channel {channel_id} not found. Please verify the channel exists"
            )
        elif "forbidden" in error_msg:
            LOGGER.error(
                f"Bot lacks access to storage channel {channel_id}. Please add bot to the channel with admin permissions"
            )
        else:
            LOGGER.error(f"Error accessing storage channel {channel_id}: {e}")
        return False


SERVICES = {
    "nzb": {
        "url": "http://localhost:8070/",
        "username": "admin",
        "password": Config.LOGIN_PASS or "admin",
    },
    "qbit": {
        "url": "http://localhost:8090",
        "username": "admin",
        "password": Config.LOGIN_PASS or "admin",
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize clients
    app.state.aria2 = Aria2HttpClient("http://localhost:6800/jsonrpc")
    app.state.qbittorrent = await create_client("http://localhost:8090/api/v2/")

    # For backward compatibility
    global aria2, qbittorrent  # noqa: PLW0603
    aria2 = app.state.aria2
    qbittorrent = app.state.qbittorrent

    # Initialize TgClient for File2Link functionality
    try:
        # Load database configuration first (primary source)
        if _config_loader:
            await _config_loader()

        TgClient = get_tg_client()

        # Only initialize if File2Link is enabled
        if Config.FILE2LINK_ENABLED:
            # Initialize lightweight client for streaming (without database)
            await init_streaming_client(TgClient)

            # Validate FILE2LINK_BIN_CHANNEL configuration
            bin_channel = getattr(Config, "FILE2LINK_BIN_CHANNEL", None)
            if bin_channel and bin_channel != 0:
                # Update Config object to ensure consistency
                Config.FILE2LINK_BIN_CHANNEL = bin_channel

                # Validate storage channel access
                channel_access = await validate_channel_access(
                    TgClient.bot, bin_channel
                )
                if not channel_access:
                    LOGGER.error(
                        "Storage channel access validation failed - File2Link streaming may not work"
                    )
                    LOGGER.error("Please ensure:")
                    LOGGER.error(
                        "1. FILE2LINK_BIN_CHANNEL is set to correct channel ID"
                    )
                    LOGGER.error("2. Bot is added to the channel")
                    LOGGER.error("3. Bot has admin permissions in the channel")

    except Exception as e:
        LOGGER.error(f"Failed to initialize TgClient for web server: {e}")
        LOGGER.warning(
            "File2Link streaming will not work until TgClient is initialized"
        )

    try:
        # Import garbage collection utilities
        from bot.helper.ext_utils.gc_utils import smart_garbage_collection

        app.state.gc_utils = smart_garbage_collection
    except ImportError:
        app.state.gc_utils = None
    yield

    # Properly close all connections
    try:
        await app.state.aria2.close()
        LOGGER.info("Aria2 client connection closed")
    except Exception as e:
        LOGGER.error(f"Error closing Aria2 client: {e}")

    try:
        await app.state.qbittorrent.close()
        LOGGER.info("qBittorrent client connection closed")
    except Exception as e:
        LOGGER.error(f"Error closing qBittorrent client: {e}")

    # Close TgClient if it was initialized
    try:
        TgClient = get_tg_client()
        if TgClient.bot is not None:
            await TgClient.stop()
            LOGGER.info("TgClient stopped for web server")
    except Exception as e:
        LOGGER.error(f"Error stopping TgClient: {e}")

    # Force garbage collection
    if app.state.gc_utils:
        app.state.gc_utils(
            aggressive=True
        )  # Use aggressive mode for cleanup on shutdown


app = FastAPI(lifespan=lifespan)


templates = Jinja2Templates(directory="web/templates/")

basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[FileHandler("log.txt"), StreamHandler()],
    level=INFO,
)

LOGGER = getLogger(__name__)


async def re_verify(paused, resumed, hash_id):
    k = 0
    while True:
        res = await app.state.qbittorrent.torrents.files(hash_id)
        verify = True
        for i in res:
            if i.index in paused and i.priority != 0:
                verify = False
                break
            if i.index in resumed and i.priority == 0:
                verify = False
                break
        if verify:
            break
        LOGGER.info("Reverification Failed! Correcting stuff...")
        await sleep(0.5)
        if paused:
            try:
                await app.state.qbittorrent.torrents.file_prio(
                    hash=hash_id,
                    id=paused,
                    priority=0,
                )
            except (ClientError, TimeoutError, Exception, AQError) as e:
                LOGGER.error(f"{e} Errored in reverification paused!")
        if resumed:
            try:
                await app.state.qbittorrent.torrents.file_prio(
                    hash=hash_id,
                    id=resumed,
                    priority=1,
                )
            except (ClientError, TimeoutError, Exception, AQError) as e:
                LOGGER.error(f"{e} Errored in reverification resumed!")
        k += 1
        if k > 5:
            return False
    LOGGER.info(f"Verified! Hash: {hash_id}")
    return True


@app.get("/app/files", response_class=HTMLResponse)
async def files(request: Request):
    return templates.TemplateResponse("torrent_selector.html", {"request": request})


@app.api_route(
    "/app/files/torrent",
    methods=["GET", "POST"],
    response_class=HTMLResponse,
)
async def handle_torrent(request: Request):
    params = request.query_params

    if not (gid := params.get("gid")):
        return JSONResponse(
            {
                "files": [],
                "engine": "",
                "error": "GID is missing",
                "message": "GID not specified",
            },
        )

    if not (pin := params.get("pin")):
        return JSONResponse(
            {
                "files": [],
                "engine": "",
                "error": "Pin is missing",
                "message": "PIN not specified",
            },
        )

    code = "".join([nbr for nbr in gid if nbr.isdigit()][:4])
    if code != pin:
        return JSONResponse(
            {
                "files": [],
                "engine": "",
                "error": "Invalid pin",
                "message": "The PIN you entered is incorrect",
            },
        )

    if request.method == "POST":
        if not (mode := params.get("mode")):
            return JSONResponse(
                {
                    "files": [],
                    "engine": "",
                    "error": "Mode is not specified",
                    "message": "Mode is not specified",
                },
            )
        data = await request.json()
        if mode == "rename":
            if len(gid) > 20:
                await handle_rename(gid, data)
                content = {
                    "files": [],
                    "engine": "",
                    "error": "",
                    "message": "Rename successfully.",
                }
            else:
                content = {
                    "files": [],
                    "engine": "",
                    "error": "Rename failed.",
                    "message": "Cannot rename aria2c torrent file",
                }
        else:
            selected_files, unselected_files = extract_file_ids(data)
            if gid.startswith("SABnzbd_nzo"):
                await set_sabnzbd(gid, unselected_files)
            elif len(gid) > 20:
                await set_qbittorrent(gid, selected_files, unselected_files)
            else:
                selected_files = ",".join(selected_files)
                await set_aria2(gid, selected_files)
            content = {
                "files": [],
                "engine": "",
                "error": "",
                "message": "Your selection has been submitted successfully.",
            }
    else:
        try:
            if gid.startswith("SABnzbd_nzo"):
                res = await sabnzbd_client.get_files(gid)
                content = make_tree(res, "sabnzbd")
            elif len(gid) > 20:
                # Use app.state.qbittorrent instead of global qbittorrent
                res = await app.state.qbittorrent.torrents.files(gid)
                content = make_tree(res, "qbittorrent")
            else:
                # Use app.state.aria2 instead of global aria2
                res = await app.state.aria2.getFiles(gid)
                op = await app.state.aria2.getOption(gid)
                fpath = f"{op['dir']}/"
                content = make_tree(res, "aria2", fpath)
        except (ClientError, TimeoutError, Exception, AQError) as e:
            LOGGER.error(str(e))
            content = {
                "files": [],
                "engine": "",
                "error": "Error getting files",
                "message": str(e),
            }
    return JSONResponse(content)


async def handle_rename(gid, data):
    try:
        _type = data["type"]
        del data["type"]
        if _type == "file":
            await app.state.qbittorrent.torrents.rename_file(hash=gid, **data)
        else:
            await app.state.qbittorrent.torrents.rename_folder(hash=gid, **data)
    except (ClientError, TimeoutError, Exception, AQError) as e:
        LOGGER.error(f"{e} Errored in renaming")


async def set_sabnzbd(gid, unselected_files):
    await sabnzbd_client.remove_file(gid, unselected_files)
    LOGGER.info(f"Verified! nzo_id: {gid}")


async def set_qbittorrent(gid, selected_files, unselected_files):
    if unselected_files:
        try:
            await app.state.qbittorrent.torrents.file_prio(
                hash=gid,
                id=unselected_files,
                priority=0,
            )
        except (ClientError, TimeoutError, Exception, AQError) as e:
            LOGGER.error(f"{e} Errored in paused")
    if selected_files:
        try:
            await app.state.qbittorrent.torrents.file_prio(
                hash=gid,
                id=selected_files,
                priority=1,
            )
        except (ClientError, TimeoutError, Exception, AQError) as e:
            LOGGER.error(f"{e} Errored in resumed")
    await sleep(0.5)
    if not await re_verify(unselected_files, selected_files, gid):
        LOGGER.error(f"Verification Failed! Hash: {gid}")


async def set_aria2(gid, selected_files):
    res = await app.state.aria2.changeOption(gid, {"select-file": selected_files})
    if res == "OK":
        LOGGER.info(f"Verified! Gid: {gid}")
    else:
        LOGGER.info(f"Verification Failed! Report! Gid: {gid}")


async def proxy_fetch(method, url, headers, params, data, base_path):
    async with ClientSession() as session:
        try:
            async with session.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
            ) as upstream:
                content = await upstream.read()
                resp_headers = {
                    k: v
                    for k, v in upstream.headers.items()
                    if k.lower()
                    not in (
                        "content-encoding",
                        "transfer-encoding",
                        "content-length",
                        "server",
                    )
                }

                # Handle redirects
                if upstream.status in (301, 302, 307, 308):
                    location = upstream.headers.get("Location")
                    if location:
                        parsed = urlparse(location)
                        if not parsed.netloc:  # Relative URL
                            location = f"{base_path}/{location.lstrip('/')}"
                        resp_headers["Location"] = location

                media_type = upstream.headers.get("Content-Type", "")
                return HTMLResponse(
                    content=content,
                    status_code=upstream.status,
                    headers=resp_headers,
                    media_type=media_type,
                )
        except Exception as e:
            LOGGER.error(f"Proxy error: {e}")
            return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)


async def protected_proxy(
    service: str,
    path: str,
    request: Request,
    username: str | None = None,
    password: str | None = None,
):
    service_info = SERVICES.get(service)
    if not service_info:
        raise HTTPException(status_code=404, detail="Service not found")

    # Check username if provided in service_info
    if "username" in service_info and username != service_info["username"]:
        raise HTTPException(status_code=403, detail="Unauthorized username")

    # Check password if provided in service_info
    if "password" in service_info and password != service_info["password"]:
        raise HTTPException(status_code=403, detail="Unauthorized password")
    base = service_info["url"]
    url = f"{base}/{path}" if path else base
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()
    return await proxy_fetch(
        request.method,
        url,
        headers,
        dict(request.query_params),
        body,
        f"/{service}",
    )


@app.api_route("/nzb/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def sabnzbd_proxy(path: str = "", request: Request = None):
    # Get username and password from query params or cookies
    username = (
        request.query_params.get("user")
        or request.cookies.get("nzb_user")
        or "admin"
    )
    password = (
        request.query_params.get("pass")
        or request.cookies.get("nzb_pass")
        or Config.LOGIN_PASS
        or "admin"
    )

    # Pass both username and password to protected_proxy
    response = await protected_proxy("nzb", path, request, username, password)

    # Set cookies if params were provided
    if "user" in request.query_params:
        response.set_cookie("nzb_user", username)
    if "pass" in request.query_params:
        response.set_cookie("nzb_pass", password)
    return response


@app.api_route(
    "/qbit/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def qbittorrent_proxy(path: str = "", request: Request = None):
    # Get username and password from query params or cookies
    username = (
        request.query_params.get("user")
        or request.cookies.get("qbit_user")
        or "admin"
    )
    password = request.query_params.get("pass") or request.cookies.get("qbit_pass")

    if not password:
        raise HTTPException(status_code=403, detail="Missing password")

    # Pass both username and password to protected_proxy
    response = await protected_proxy("qbit", path, request, username, password)

    # Set cookies if params were provided
    if "user" in request.query_params:
        response.set_cookie("qbit_user", username)
    if "pass" in request.query_params:
        response.set_cookie("qbit_pass", password)
    return response


@app.get("/", response_class=HTMLResponse)
async def homepage():
    return (
        "<h1>See multi-purpose telegram bot at "
        "<a href='https://github.com/AeonOrg/Aeon-MLTB/tree/extended'>@GitHub</a> "
        "By <a href='https://github.com/AeonOrg'>AeonOrg</a></h1>"
    )


@app.get("/health")
async def health_check():
    """Health check endpoint to verify bot and streaming status"""
    try:
        # Get stream utilities
        (
            StreamClientManager,
            ByteStreamer,
            ParallelByteStreamer,
            ParallelDownloader,
            RawByteStreamer,
            create_raw_streamer,
            get_hash,
            get_fname,
            validate_stream_request,
            get_mime_type,
            is_streamable_file,
        ) = get_stream_utils()

        # Check if File2Link is enabled
        if not Config.FILE2LINK_ENABLED:
            return {
                "status": "disabled",
                "message": "File2Link functionality is disabled",
                "streaming_ready": False,
            }

        # Check if bot client is available
        client, client_id = StreamClientManager.get_optimal_client()
        bot_ready = client is not None

        # Check configuration
        config_ready = bool(Config.FILE2LINK_BIN_CHANNEL)

        # Check channel access if bot is ready
        channel_access = False
        if bot_ready and config_ready:
            try:
                channel_access = await validate_channel_access(
                    client, Config.FILE2LINK_BIN_CHANNEL
                )
            except Exception as e:
                LOGGER.error(f"Error checking channel access in health check: {e}")

        streaming_ready = bot_ready and config_ready and channel_access

        # Get client info for additional details
        client_info = StreamClientManager.get_client_info() if bot_ready else {}

        # Check hyperdl status
        hyperdl_enabled = (
            Config.HYPER_THREADS and client_info.get("helper_bots_count", 0) > 0
        )

        return {
            "status": "ok" if streaming_ready else "not_ready",
            "message": "health check",
            "file2link_enabled": Config.FILE2LINK_ENABLED,
            "bot_ready": bot_ready,
            "config_ready": config_ready,
            "channel_access": channel_access,
            "streaming_ready": streaming_ready,
            "bin_channel_configured": bool(Config.FILE2LINK_BIN_CHANNEL),
            "bin_channel_id": (
                Config.FILE2LINK_BIN_CHANNEL
                if Config.FILE2LINK_BIN_CHANNEL
                else None
            ),
            "helper_tokens_configured": bool(Config.HELPER_TOKENS),
            "total_clients": client_info.get("total_clients", 1),
            "helper_bots_count": client_info.get("helper_bots_count", 0),
            "workload_distribution": client_info.get(
                "workload_distribution", {0: 0}
            ),
            "hyperdl_enabled": hyperdl_enabled,
            "hyper_threads_config": Config.HYPER_THREADS,
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Health check failed: {e!s}",
            "streaming_ready": False,
        }


@app.exception_handler(Exception)
async def page_not_found(_, exc):
    return HTMLResponse(
        f"<h1>404: Task not found! Mostly wrong input. <br><br>Error: {exc}</h1>",
        status_code=404,
    )


# File2Link Streaming Routes
import re
from urllib.parse import quote, unquote

from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates

# Initialize templates for streaming pages
stream_templates = Jinja2Templates(directory="web/templates/")

# Regex patterns for parsing streaming requests
SECURE_HASH_LENGTH = 6
PATTERN_HASH_FIRST = re.compile(
    rf"^([a-zA-Z0-9_-]{{{SECURE_HASH_LENGTH}}})(\d+)(?:/.*)?$"
)
RANGE_REGEX = re.compile(r"bytes=(?P<start>\d*)-(?P<end>\d*)")


def parse_stream_request(path: str) -> tuple[int, str]:
    """Parse streaming request path to extract message ID and hash"""
    # Get stream utilities
    (
        StreamClientManager,
        ByteStreamer,
        ParallelByteStreamer,
        ParallelDownloader,
        RawByteStreamer,
        create_raw_streamer,
        get_hash,
        get_fname,
        validate_stream_request,
        get_mime_type,
        is_streamable_file,
    ) = get_stream_utils()

    match = PATTERN_HASH_FIRST.match(path)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    secure_hash = match.group(1)
    message_id = int(match.group(2))

    if not validate_stream_request(secure_hash, message_id):
        raise HTTPException(status_code=400, detail="Invalid request parameters")

    return message_id, secure_hash


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse HTTP range header"""
    if not range_header:
        return 0, file_size - 1

    match = RANGE_REGEX.match(range_header)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid range")

    start = int(match.group("start")) if match.group("start") else 0
    end = int(match.group("end")) if match.group("end") else file_size - 1

    if start < 0 or end >= file_size or start > end:
        raise HTTPException(status_code=416, detail="Range not satisfiable")

    return start, end


@app.get("/watch/{path:path}")
async def stream_preview(path: str, request: Request):
    """Streaming preview page with media player"""
    try:
        if not Config.FILE2LINK_ENABLED:
            raise HTTPException(status_code=503, detail="File2Link service disabled")

        # Get stream utilities
        (
            StreamClientManager,
            ByteStreamer,
            ParallelByteStreamer,
            ParallelDownloader,
            RawByteStreamer,
            create_raw_streamer,
            get_hash,
            get_fname,
            validate_stream_request,
            get_mime_type,
            is_streamable_file,
        ) = get_stream_utils()

        message_id, secure_hash = parse_stream_request(path)

        # Get storage channel first
        storage_channel = await get_file2link_bin_channel()
        if not storage_channel:
            storage_channel = getattr(Config, "FILE2LINK_BIN_CHANNEL", None)
            if storage_channel and storage_channel != 0:
                LOGGER.warning(
                    f"Using Config fallback for FILE2LINK_BIN_CHANNEL: {storage_channel}"
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail="FILE2LINK_BIN_CHANNEL not configured. Please set a storage channel for File2Link streaming.",
                )

        # Try Raw API Streaming first
        raw_streamer = create_raw_streamer(storage_channel)

        if raw_streamer:
            streamer = raw_streamer
            # Get a client for message validation (Raw streamer manages its own clients for streaming)
            client = next(iter(raw_streamer.clients.values()))
            client_id = None
        else:
            # Fallback to existing streaming methods

            # Check if parallel streaming is available
            from bot.core.aeon_client import TgClient

            effective_threads = Config.HYPER_THREADS or (
                max(8, len(TgClient.helper_bots))
                if hasattr(TgClient, "helper_bots") and TgClient.helper_bots
                else 0
            )

            use_parallel = (
                effective_threads > 0
                and hasattr(TgClient, "helper_bots")
                and TgClient.helper_bots
                and len(TgClient.helper_bots) > 1
            )

            if use_parallel:
                LOGGER.info(
                    f"File2Link Stream - Using parallel streaming fallback for message {message_id}"
                )
                streamer = ParallelByteStreamer(chat_id=storage_channel)
                # Get a client for hash validation when using parallel streaming
                client, client_id = StreamClientManager.get_optimal_client()
                if client is None:
                    raise HTTPException(
                        status_code=503,
                        detail="Bot not initialized yet, please try again later",
                    )
            else:
                # Fallback to single client streaming
                LOGGER.info(
                    f"File2Link Stream - Using single client streaming fallback for message {message_id}"
                )
                client, client_id = StreamClientManager.get_optimal_client()
                if client is None:
                    raise HTTPException(
                        status_code=503,
                        detail="Bot not initialized yet, please try again later",
                    )
                streamer = ByteStreamer(client, client_id, chat_id=storage_channel)

        # Get file info (different approach for raw streamer)
        if isinstance(streamer, RawByteStreamer):
            # Raw streamer uses async get_file_properties
            try:
                file_info = await streamer.get_file_properties(message_id)
            except Exception:
                raise HTTPException(status_code=404, detail="File not found")
        else:
            # Legacy streamers use sync get_file_info
            file_info = await streamer.get_file_info(message_id)
            if "error" in file_info:
                raise HTTPException(status_code=404, detail="File not found")

        # Check if this is a streaming request (has range header) or HTML page request
        range_header = request.headers.get("range")
        is_streaming_request = range_header is not None

        # Get the message to check if file is streamable
        message = await streamer.get_message(message_id)
        if not is_streamable_file(message):
            # Redirect non-streamable files to download
            download_url = f"/download/{path}"
            return RedirectResponse(url=download_url, status_code=302)

        # Validate hash and get stored message
        stored_msg = message  # We already have the message from above
        if not stored_msg or get_hash(stored_msg) != secure_hash:
            raise HTTPException(status_code=404, detail="Invalid file hash")

        # Extract filename from path or get from file info with comprehensive fallback
        try:
            if "/" in path:
                filename = unquote(path.split("/")[-1])
            else:
                filename = file_info.get("file_name", "Unknown File")

            # Ensure filename is not None or empty
            if not filename or filename is None or filename == "":
                LOGGER.warning(
                    f"Filename extraction failed for watch path {path}, using fallback"
                )
                filename = "Unknown File"

        except Exception as e:
            LOGGER.error(f"Error extracting filename from watch path {path}: {e}")
            filename = "Unknown File"

        # If this is a streaming request (range header present), serve the video data directly
        if is_streaming_request:
            # Handle streaming request - serve actual video data
            file_size = file_info.get("file_size", 0)
            mime_type = file_info.get("mime_type") or get_mime_type(filename)

            # Parse range header
            start, end = parse_range_header(range_header, file_size)
            content_length = end - start + 1

            # Prepare headers for streaming
            headers = {
                "Content-Type": mime_type,
                "Content-Length": str(content_length),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
            }

            # Stream the video data
            async def video_stream():
                if isinstance(streamer, RawByteStreamer):
                    # Raw streamer - direct streaming
                    stream_method = streamer.stream_file(
                        message_id, offset=start, limit=content_length
                    )
                else:
                    # Legacy streamers
                    is_parallel = (
                        hasattr(streamer, "is_parallel") and streamer.is_parallel()
                    )
                    if is_parallel:
                        stream_method = streamer.stream_file_parallel(
                            message_id, offset=start, limit=content_length
                        )
                    else:
                        stream_method = streamer.stream_file(
                            message_id, offset=start, limit=content_length
                        )

                async for chunk in stream_method:
                    if chunk:
                        yield chunk

            return StreamingResponse(
                video_stream(),
                status_code=206,  # Partial Content
                headers=headers,
                media_type=mime_type,
            )

        # If no range header, serve the HTML player page
        # Determine media type for player
        media_type = "video"
        if file_info.get("media_type") in ["audio", "voice"]:
            media_type = "audio"

        # Generate stream URL (self-reference for streaming)
        stream_url = f"/watch/{secure_hash}{message_id}/{quote(filename)}"

        # Render template
        return stream_templates.TemplateResponse(
            "stream_player.html",
            {
                "request": request,
                "file_name": filename,
                "src": stream_url,
                "tag": media_type,
                "heading": f"Stream {filename}",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Error in stream preview: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.options("/stream/{path:path}")
async def stream_options(_path: str):
    """Handle CORS preflight requests"""
    return Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length, Authorization",
            "Access-Control-Max-Age": "86400",
        }
    )


@app.get("/download/{path:path}")
async def download_file(path: str, request: Request):
    """File download endpoint with forced download headers"""
    try:
        if not Config.FILE2LINK_ENABLED:
            raise HTTPException(status_code=503, detail="File2Link service disabled")

        # Get stream utilities
        (
            StreamClientManager,
            ByteStreamer,
            ParallelByteStreamer,
            ParallelDownloader,
            RawByteStreamer,
            create_raw_streamer,
            get_hash,
            get_fname,
            validate_stream_request,
            get_mime_type,
            is_streamable_file,
        ) = get_stream_utils()

        # Parse path first
        if len(path) < 6:
            raise HTTPException(status_code=400, detail="Invalid path format")

        secure_hash = path[:6]
        remaining_path = path[6:]
        if "/" not in remaining_path:
            raise HTTPException(status_code=400, detail="Invalid path format")

        message_id_str, filename = remaining_path.split("/", 1)
        try:
            message_id = int(message_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid message ID")

        # Validate request with proper arguments
        if not validate_stream_request(secure_hash, message_id):
            raise HTTPException(status_code=400, detail="Invalid request")

        # Get storage channel first
        storage_channel = await get_file2link_bin_channel()
        if not storage_channel:
            storage_channel = getattr(Config, "FILE2LINK_BIN_CHANNEL", None)
            if not storage_channel or storage_channel == 0:
                raise HTTPException(
                    status_code=503,
                    detail="FILE2LINK_BIN_CHANNEL not configured. Please set a storage channel for File2Link downloads.",
                )

        # Try Raw API Streaming first for downloads
        raw_streamer = create_raw_streamer(storage_channel)

        if raw_streamer:
            # Get file info using raw streamer
            try:
                file_info = await raw_streamer.get_file_properties(message_id)
                # Verify hash by getting the message
                client = next(
                    iter(raw_streamer.clients.values())
                )  # Get any client for hash verification
                stored_msg = await client.get_messages(storage_channel, message_id)
                if not stored_msg or get_hash(stored_msg) != secure_hash:
                    raise HTTPException(status_code=404, detail="Invalid file hash")

            except Exception:
                raise HTTPException(status_code=404, detail="File not found")

            streamer = raw_streamer
            hyperdl_available = False  # Skip HyperDL since we're using Raw API

        else:
            # Fallback to HyperDL/legacy methods

            from bot.core.aeon_client import TgClient

            # Check HyperDL availability (like hyperdl_utils.py)
            effective_threads = Config.HYPER_THREADS or (
                len(TgClient.helper_bots)
                if hasattr(TgClient, "helper_bots") and TgClient.helper_bots
                else 0
            )

            hyperdl_available = (
                effective_threads > 0
                and hasattr(TgClient, "helper_bots")
                and TgClient.helper_bots
                and len(TgClient.helper_bots) > 0
            )

            # Get a client for file validation
            client, _ = StreamClientManager.get_optimal_client()
            if client is None:
                raise HTTPException(
                    status_code=503,
                    detail="Bot not initialized yet, please try again later",
                )

            # Verify file hash first
            stored_msg = await client.get_messages(storage_channel, message_id)
            if not stored_msg or get_hash(stored_msg) != secure_hash:
                raise HTTPException(status_code=404, detail="Invalid file hash")

            # Get file info
            from bot.helper.stream_utils.file_processor import get_file_info

            file_info = get_file_info(stored_msg)
            if not file_info:
                raise HTTPException(status_code=404, detail="File not found")

            streamer = None  # Will be set in HyperDL logic if needed

        try:
            file_size = file_info.get("file_size", 0)

            # Get filename with comprehensive fallback handling
            try:
                filename_from_msg = get_fname(stored_msg)
                filename_from_info = file_info.get("file_name")

                filename = filename_from_msg or filename_from_info or "Unknown File"

                # Additional validation to prevent None filename
                if not filename or filename is None or filename == "":
                    LOGGER.warning(
                        f"All filename sources failed for download message {message_id}, using fallback"
                    )
                    filename = "Unknown File"

            except Exception as e:
                LOGGER.error(
                    f"Error getting filename for download message {message_id}: {e}"
                )
                filename = "Unknown File"

            file_info.get("mime_type") or get_mime_type(filename)

            # Handle range requests
            range_header = request.headers.get("range")
            if range_header:
                start, end = parse_range_header(range_header, file_size)
                content_length = end - start + 1
                status_code = 206
            else:
                start, end = 0, file_size - 1
                content_length = file_size
                status_code = 200

            # Prepare headers with forced download
            headers = {
                "Content-Type": "application/octet-stream",  # Force download
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache",  # Don't cache downloads
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",  # Force download
                "Connection": "keep-alive",
                "Keep-Alive": "timeout=600, max=50",  # Extended timeout for downloads
                "X-Content-Type-Options": "nosniff",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
                "X-Download-Optimized": "true",  # Debug header
                "Transfer-Encoding": "chunked",  # Enable chunked transfer
            }

            if range_header:
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

            # Handle HEAD requests - return headers only
            if request.method == "HEAD":
                return Response(status_code=status_code, headers=headers)

            # Try HyperDL streaming if available
            if hyperdl_available:
                try:
                    # Import HyperDL directly
                    from bot.helper.ext_utils.hyperdl_utils import HyperTGDownload

                    # Create HyperDL instance
                    hyperdl = HyperTGDownload()

                    # Create HyperDL streaming generator (streams chunks directly, no disk write)
                    async def hyperdl_stream_generator():
                        bytes_sent = 0

                        try:
                            # Set up HyperDL for streaming (similar to download_media but streaming)
                            hyperdl.message = stored_msg
                            hyperdl.dump_chat = storage_channel
                            hyperdl.file_size = file_size

                            # Calculate streaming range
                            if range_header:
                                # For range requests, stream only the requested range
                                stream_start, stream_end = start, end
                            else:
                                # For full file, stream everything
                                stream_start, stream_end = 0, file_size - 1

                            # Stream using HyperDL's get_file method (yields chunks directly)
                            offset = stream_start - (
                                stream_start % hyperdl.chunk_size
                            )
                            first_part_cut = stream_start - offset
                            last_part_cut = (stream_end % hyperdl.chunk_size) + 1
                            part_count = (
                                (stream_end // hyperdl.chunk_size)
                                - (offset // hyperdl.chunk_size)
                                + 1
                            )

                            async for chunk in hyperdl.get_file(
                                offset, first_part_cut, last_part_cut, part_count
                            ):
                                if chunk:
                                    yield chunk
                                    bytes_sent += len(chunk)

                                    if range_header and bytes_sent >= (
                                        stream_end - stream_start + 1
                                    ):
                                        break

                        except Exception:
                            raise

                    # Return HyperDL streaming response (no disk write, streams directly)
                    return StreamingResponse(
                        hyperdl_stream_generator(),
                        status_code=status_code,
                        headers=headers,
                        media_type="application/octet-stream",
                    )

                except Exception:
                    pass

            # Stream generator for download
            async def download_generator():
                bytes_sent = 0
                start_time = asyncio.get_event_loop().time()

                try:
                    if isinstance(streamer, RawByteStreamer):
                        # Raw API streaming (Priority 1)
                        stream_method = streamer.stream_file(
                            message_id, offset=start, limit=content_length
                        )
                    # Legacy fallback methods

                    # Create fallback streamer if needed
                    elif streamer is None:
                        # Create stream_media() fallback
                        class StreamMediaDownloader:
                            def __init__(self, client, chat_id):
                                self.client = client
                                self.chat_id = chat_id

                            async def stream_file(
                                self, message_id, offset=0, limit=0
                            ):
                                """Stream file using high-level stream_media() API"""
                                message = await self.client.get_messages(
                                    self.chat_id, message_id
                                )
                                bytes_streamed = 0

                                async for chunk in self.client.stream_media(message):
                                    if not chunk:
                                        break

                                    # Handle offset and limit
                                    if offset > 0:
                                        if bytes_streamed + len(chunk) <= offset:
                                            bytes_streamed += len(chunk)
                                            continue
                                        elif bytes_streamed < offset:
                                            skip_bytes = offset - bytes_streamed
                                            chunk = chunk[skip_bytes:]
                                            bytes_streamed = offset

                                    yield chunk
                                    bytes_streamed += len(chunk)

                                    if (
                                        limit > 0
                                        and bytes_streamed >= offset + limit
                                    ):
                                        break

                        fallback_streamer = StreamMediaDownloader(
                            client, storage_channel
                        )
                        stream_method = fallback_streamer.stream_file(
                            message_id, offset=start, limit=content_length
                        )
                    else:
                        # Use existing streamer (HyperDL or other)
                        stream_method = streamer.stream_file(
                            message_id, offset=start, limit=content_length
                        )

                    chunk_count = 0
                    last_log_time = start_time
                    log_interval = 5.0  # Log every 5 seconds

                    async for chunk in stream_method:
                        chunk_count += 1
                        current_time = asyncio.get_event_loop().time()

                        timeout_seconds = 600  # 10 minute timeout
                        if current_time - start_time > timeout_seconds:
                            LOGGER.warning(
                                f"Download timeout after {timeout_seconds}s, {bytes_sent} bytes sent"
                            )
                            break

                        if chunk:
                            remaining = content_length - bytes_sent
                            if len(chunk) > remaining:
                                chunk = chunk[:remaining]

                            if chunk:
                                yield chunk
                                bytes_sent += len(chunk)

                                # Update log time
                                if current_time - last_log_time >= log_interval:
                                    last_log_time = current_time

                        if bytes_sent >= content_length:
                            break

                except Exception as e:
                    LOGGER.error(f"Error in download streaming: {e}")
                    raise

            return StreamingResponse(
                download_generator(),
                status_code=status_code,
                headers=headers,
                media_type="application/octet-stream",
            )

        finally:
            # No client_id to decrement for stream_media() approach
            pass

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Error in file download: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/favicon.ico")
async def favicon():
    """Serve favicon to prevent 404 errors"""
    return Response(status_code=204)  # No Content - prevents 404 errors
