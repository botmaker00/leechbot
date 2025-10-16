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

        except Exception as e:
            LOGGER.error(f"Failed to load database settings: {e}")

    # Store the config loading function for later use
    _config_loader = load_web_server_config


except Exception as e:
    LOGGER.error(f"Failed to load configuration for web server: {e}")
    _config_loader = None


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


@app.exception_handler(Exception)
async def page_not_found(_, exc):
    return HTMLResponse(
        f"<h1>404: Task not found! Mostly wrong input. <br><br>Error: {exc}</h1>",
        status_code=404,
    )