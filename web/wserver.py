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


# This function is no longer needed as we are creating an independent client.
# def get_tg_client():
#     """Lazy import of TgClient to avoid startup delays"""
#     from bot.core.aeon_client import TgClient
#
#     return TgClient


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


class WebStreamer:
    _instance = None
    _lock = asyncio.Lock()
    bot = None
    clients = {}
    workload = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WebStreamer, cls).__new__(cls)
        return cls._instance

    @classmethod
    async def get_instance(cls):
        async with cls._lock:
            if cls._instance is None:
                cls._instance = WebStreamer()
                await cls._instance.start_clients()
            return cls._instance

    async def start_clients(self):
        LOGGER.info("Starting independent web server clients...")
        from pyrogram import Client, enums
        from bot.core.aeon_client import USING_KURIGRAM
        import os

        web_session_dir = "/usr/src/app/web_sessions"
        os.makedirs(web_session_dir, exist_ok=True)

        bot_token = Config.BOT_TOKEN
        if not bot_token:
            LOGGER.error("BOT_TOKEN not found. Cannot start web server client.")
            return

        client_id = int(bot_token.split(":", 1)[0])
        client_args = {
            "name": f"web_main_{client_id}",
            "api_id": Config.TELEGRAM_API,
            "api_hash": Config.TELEGRAM_HASH,
            "proxy": Config.TG_PROXY,
            "bot_token": bot_token,
            "workdir": web_session_dir,
            "parse_mode": enums.ParseMode.HTML,
            "no_updates": True,
        }
        if USING_KURIGRAM:
            client_args["max_concurrent_transmissions"] = 100

        try:
            self.bot = Client(**client_args)
            await self.bot.start()
            self.clients[0] = self.bot
            self.workload[0] = 0
            LOGGER.info(f"Web server main client [@{self.bot.me.username}] started.")
        except Exception as e:
            LOGGER.error(f"Failed to start web server main client: {e}")
            self.bot = None

        helper_tokens = Config.HELPER_TOKENS
        if helper_tokens:
            await gather(
                *(
                    self._start_helper(no, token, web_session_dir)
                    for no, token in enumerate(helper_tokens.split(), start=1)
                )
            )

    async def _start_helper(self, no, token, workdir):
        from pyrogram import Client, enums
        from bot.core.aeon_client import USING_KURIGRAM
        try:
            helper_args = {
                "name": f"web_helper_{no}",
                "api_id": Config.TELEGRAM_API,
                "api_hash": Config.TELEGRAM_HASH,
                "proxy": Config.TG_PROXY,
                "bot_token": token,
                "workdir": workdir,
                "parse_mode": enums.ParseMode.HTML,
                "no_updates": True,
            }
            if USING_KURIGRAM:
                helper_args["max_concurrent_transmissions"] = 20

            hbot = Client(**helper_args)
            await hbot.start()
            self.clients[no] = hbot
            self.workload[no] = 0
            LOGGER.info(f"Web server helper bot {no} [@{hbot.me.username}] started.")
        except Exception as e:
            LOGGER.error(f"Failed to start web server helper bot {no}: {e}")

    async def stop_clients(self):
        LOGGER.info("Stopping independent web server clients...")
        if self.bot:
            await self.bot.stop()
        await gather(*[client.stop() for client in self.clients.values() if client != self.bot])
        self.clients.clear()
        self.workload.clear()
        self.bot = None
        LOGGER.info("Web server clients stopped.")

    def get_client(self):
        if not self.clients:
            return None, None
        client_id = min(self.workload, key=self.workload.get)
        self.workload[client_id] += 1
        return self.clients.get(client_id), client_id

    def decrease_load(self, client_id):
        if client_id in self.workload:
            self.workload[client_id] -= 1


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
    # Initialize download clients
    app.state.aria2 = Aria2HttpClient("http://localhost:6800/jsonrpc")
    app.state.qbittorrent = await create_client("http://localhost:8090/api/v2/")
    global aria2, qbittorrent
    aria2 = app.state.aria2
    qbittorrent = app.state.qbittorrent

    # Initialize WebStreamer for File2Link
    if Config.FILE2LINK_ENABLED:
        app.state.web_streamer = await WebStreamer.get_instance()
        if not app.state.web_streamer.bot:
             LOGGER.error("File2Link streaming will not work as the client failed to start.")
    else:
        app.state.web_streamer = None

    yield

    # Properly close all connections
    LOGGER.info("Shutting down web server and closing connections...")
    try:
        await app.state.aria2.close()
        LOGGER.info("Aria2 client connection closed.")
    except Exception as e:
        LOGGER.error(f"Error closing Aria2 client: {e}")

    try:
        await app.state.qbittorrent.close()
        LOGGER.info("qBittorrent client connection closed.")
    except Exception as e:
        LOGGER.error(f"Error closing qBittorrent client: {e}")

    if app.state.web_streamer:
        try:
            await app.state.web_streamer.stop_clients()
        except Exception as e:
            LOGGER.error(f"Error stopping WebStreamer clients: {e}")


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
    return {"status": "ok", "message": "Aeon-MLTB web server is running."}
