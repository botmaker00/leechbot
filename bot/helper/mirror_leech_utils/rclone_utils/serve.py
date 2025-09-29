from asyncio import create_subprocess_exec
from configparser import RawConfigParser

from aiofiles import open as aiopen

from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath

RcloneServe = []


async def rclone_serve_booter():
    # First, kill any existing rclone serve processes
    if RcloneServe:
        try:
            RcloneServe[0].kill()
            RcloneServe.clear()
        except Exception:
            pass

    # Check if Rclone operations are enabled in the configuration
    if not Config.RCLONE_ENABLED:
        from bot import LOGGER

        LOGGER.info("Rclone HTTP server is disabled (RCLONE_ENABLED is False)")
        return

    # Check if rclone serve is disabled (RCLONE_SERVE_PORT = 0)
    if Config.RCLONE_SERVE_PORT == 0:
        from bot import LOGGER

        LOGGER.info("Rclone HTTP server is disabled (RCLONE_SERVE_PORT = 0)")
        return

    # Check if required configuration is available
    if not Config.RCLONE_SERVE_URL or not await aiopath.exists("rclone.conf"):
        return

    config = RawConfigParser()
    async with aiopen("rclone.conf") as f:
        contents = await f.read()
        config.read_string(contents)
    if not config.has_section("combine"):
        upstreams = " ".join(f"{remote}={remote}:" for remote in config.sections())
        config.add_section("combine")
        config.set("combine", "type", "combine")
        config.set("combine", "upstreams", upstreams)
        async with aiopen("rclone.conf", "w") as f:
            config.write(f, space_around_delimiters=False)

    # Start rclone serve
    from bot import LOGGER

    LOGGER.info(f"Starting rclone HTTP server on port {Config.RCLONE_SERVE_PORT}")
    cmd = [
        "xone",
        "serve",
        "http",
        "--config",
        "rclone.conf",
        "--no-modtime",
        "combine:",
        "--addr",
        f":{Config.RCLONE_SERVE_PORT}",
        "--vfs-cache-mode",
        "full",
        "--vfs-cache-max-age",
        "1m0s",
        "--buffer-size",
        "64M",
        "-v",
        "--log-file",
        "rlog.txt",
    ]
    if (user := Config.RCLONE_SERVE_USER) and (pswd := Config.RCLONE_SERVE_PASS):
        cmd.extend(("--user", user, "--pass", pswd))
    rcs = await create_subprocess_exec(*cmd)
    RcloneServe.append(rcs)
