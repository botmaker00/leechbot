import contextlib
from asyncio import gather, sleep
from inspect import iscoroutinefunction
from pathlib import Path

from aioaria2 import Aria2WebsocketClient  # type: ignore
from aiohttp import ClientError
from aioqbt.client import create_client  # type: ignore
from tenacity import (  # type: ignore
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot import LOGGER, aria2_options
from bot.helper.ext_utils.gc_utils import smart_garbage_collection


def wrap_with_retry(obj, max_retries=5):
    for attr_name in dir(obj):
        if attr_name.startswith("_"):
            continue

        attr = getattr(obj, attr_name)
        if iscoroutinefunction(attr):
            retry_policy = retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=2, min=2, max=30),
                retry=retry_if_exception_type(
                    (ClientError, TimeoutError, RuntimeError, ConnectionError),
                ),
            )
            wrapped = retry_policy(attr)
            setattr(obj, attr_name, wrapped)
    return obj


class TorrentManager:
    aria2 = None
    qbittorrent = None

    @classmethod
    async def initiate(cls):
        # Initialize aria2 with retry logic
        retry_count = 0
        max_retries = 5
        while retry_count < max_retries:
            try:
                LOGGER.info(
                    f"Connecting to Aria2 (attempt {retry_count + 1}/{max_retries})...",
                )
                cls.aria2 = await Aria2WebsocketClient.new(
                    "http://localhost:6800/jsonrpc",
                    timeout=30,  # Increased timeout
                )
                LOGGER.info("Successfully connected to Aria2")
                break
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    LOGGER.error(f"All attempts to connect to Aria2 failed: {e}")
                    cls.aria2 = None
                else:
                    # Wait before retrying with exponential backoff
                    wait_time = 2**retry_count
                    LOGGER.info(f"Waiting {wait_time} seconds before retrying...")
                    await sleep(wait_time)

        # Initialize qBittorrent with retry logic
        retry_count = 0
        while retry_count < max_retries:
            try:
                LOGGER.info(
                    f"Connecting to qBittorrent (attempt {retry_count + 1}/{max_retries})...",
                )
                # Create qBittorrent client
                cls.qbittorrent = await create_client(
                    "http://localhost:8090/api/v2/",
                )
                # Apply retry wrapper to make all API calls more resilient
                cls.qbittorrent = wrap_with_retry(cls.qbittorrent)
                LOGGER.info("Successfully connected to qBittorrent")
                break
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    LOGGER.error(
                        f"All attempts to connect to qBittorrent failed: {e}",
                    )
                    cls.qbittorrent = None
                else:
                    # Wait before retrying with exponential backoff
                    wait_time = 2**retry_count
                    LOGGER.info(f"Waiting {wait_time} seconds before retrying...")
                    await sleep(wait_time)
                # Additional connection test is already done by the create_client function

        # Log connection status
        LOGGER.info(
            f"Torrent services initialized - Aria2: {'Connected' if cls.aria2 else 'Failed'}, qBittorrent: {'Connected' if cls.qbittorrent else 'Failed'}",
        )

    @classmethod
    async def close_all(cls):
        tasks = []
        if cls.aria2:
            tasks.append(cls.aria2.close())
        if cls.qbittorrent:
            tasks.append(cls.qbittorrent.close())
        if tasks:
            try:
                await gather(*tasks)
                LOGGER.info("Successfully closed all torrent connections")
            except Exception as e:
                LOGGER.error(f"Error closing torrent connections: {e}")

        # Force garbage collection after closing connections
        smart_garbage_collection(aggressive=True)

    @classmethod
    async def aria2_remove(cls, download):
        gid = download.get("gid", "")
        if not gid:
            LOGGER.warning("aria2_remove: No GID provided in download object")
            return

        try:
            if download.get("status", "") in ["active", "paused", "waiting"]:
                await cls.aria2.forceRemove(gid)
            else:
                await cls.aria2.removeDownloadResult(gid)
        except Exception as e:
            # Handle expected errors gracefully
            if "is not found" in str(e):
                LOGGER.debug(f"aria2_remove: GID {gid} not found (already removed)")
            elif "closing transport" in str(e).lower():
                LOGGER.debug(f"aria2_remove: Transport closing error for GID {gid}")
            else:
                LOGGER.error(f"aria2_remove: Error removing GID {gid}: {e}")

    @classmethod
    async def remove_all(cls):
        try:
            await cls.pause_all()

            # Create tasks list for parallel execution
            tasks = []

            # Add qBittorrent deletion task if client is available
            if cls.qbittorrent is not None:
                tasks.append(cls.qbittorrent.torrents.delete("all", True))

            # Add aria2 purge task if client is available
            if cls.aria2 is not None:
                tasks.append(cls.aria2.purgeDownloadResult())

            # Execute available tasks
            if tasks:
                await gather(*tasks)

            # Handle aria2 active/waiting downloads if client is available
            if cls.aria2 is not None:
                downloads = []
                results = await gather(
                    cls.aria2.tellActive(),
                    cls.aria2.tellWaiting(0, 1000),
                )
                for res in results:
                    downloads.extend(res)

                # Force remove all downloads
                removal_tasks = []
                removal_tasks.extend(
                    cls.aria2.forceRemove(download.get("gid"))
                    for download in downloads
                )
                if removal_tasks:
                    with contextlib.suppress(Exception):
                        await gather(*removal_tasks)

            # Force garbage collection after removing all torrents
            # This helps free memory used by large torrent metadata
            smart_garbage_collection(aggressive=True)

        except Exception as e:
            LOGGER.error(f"Error removing all torrents: {e}")

    @classmethod
    async def overall_speed(cls):
        try:
            s1, s2 = await gather(
                cls.qbittorrent.transfer.info(),
                cls.aria2.getGlobalStat(),
            )
            download_speed = s1.dl_info_speed + int(s2.get("downloadSpeed", "0"))
            upload_speed = s1.up_info_speed + int(s2.get("uploadSpeed", "0"))
            return download_speed, upload_speed
        except Exception as e:
            # Handle transport closing errors gracefully
            if "closing transport" in str(e).lower():
                # Return zero speeds for transport closing errors
                return 0, 0
            LOGGER.warning(f"Error getting overall speeds: {e}")
            return 0, 0

    @classmethod
    async def pause_all(cls):
        try:
            tasks = []

            # Handle aria2 pause if client is available
            if cls.aria2 is not None:
                tasks.append(cls.aria2.forcePauseAll())

            # Handle qBittorrent pause if client is available
            if cls.qbittorrent is not None:
                tasks.append(cls.qbittorrent.torrents.stop("all"))

            # Execute available tasks
            if tasks:
                await gather(*tasks)
            else:
                LOGGER.warning("No torrent clients available for pause operation")

        except Exception as e:
            # Handle transport closing errors gracefully
            if "closing transport" not in str(e).lower():
                LOGGER.warning(f"Error pausing all torrents: {e}")

    @classmethod
    async def change_aria2_option(cls, key, value):
        try:
            downloads = []
            results = await gather(
                cls.aria2.tellActive(),
                cls.aria2.tellWaiting(0, 1000),
            )
            for res in results:
                downloads.extend(res)
            tasks = [
                cls.aria2.changeOption(download.get("gid"), {key: value})
                for download in downloads
                if download.get("status", "") != "complete"
            ]
            if tasks:
                try:
                    await gather(*tasks)
                except Exception as e:
                    # Handle transport closing errors gracefully
                    if "closing transport" not in str(e).lower():
                        LOGGER.error(e)

            if key not in ["checksum", "index-out", "out", "pause", "select-file"]:
                await cls.aria2.changeGlobalOption({key: value})
                aria2_options[key] = value
        except Exception as e:
            # Handle transport closing errors at the method level
            if "closing transport" not in str(e).lower():
                LOGGER.error(f"Error changing aria2 option {key}: {e}")


def aria2_name(download_info):
    if "bittorrent" in download_info and download_info["bittorrent"].get("info"):
        return download_info["bittorrent"]["info"]["name"]
    if download_info.get("files"):
        if download_info["files"][0]["path"].startswith("[METADATA]"):
            return download_info["files"][0]["path"]
        file_path = download_info["files"][0]["path"]
        dir_path = download_info["dir"]
        if file_path.startswith(dir_path):
            return Path(file_path[len(dir_path) + 1 :]).parts[0]
        return ""
    return ""


def is_metadata(download_info):
    return any(
        f["path"].startswith("[METADATA]") for f in download_info.get("files", [])
    )
