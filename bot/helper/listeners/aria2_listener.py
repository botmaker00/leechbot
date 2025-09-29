import contextlib
from asyncio import create_task, sleep
from time import time

from bot import LOGGER, intervals, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.core.torrent_manager import TorrentManager, aria2_name, is_metadata
from bot.helper.ext_utils.aiofiles_compat import aiopath, makedirs, remove
from bot.helper.ext_utils.bot_utils import bt_selection_buttons
from bot.helper.ext_utils.files_utils import clean_unwanted
from bot.helper.ext_utils.status_utils import get_task_by_gid
from bot.helper.ext_utils.task_manager import stop_duplicate_check
from bot.helper.mirror_leech_utils.status_utils.aria2_status import Aria2Status
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
    update_status_message,
)


async def _on_download_started(api, data):
    try:
        gid = data["params"][0]["gid"]

        # Try to get download info with error handling
        try:
            download = await api.tellStatus(gid)
            options = await api.getOption(gid)
        except Exception as e:
            # If we can't get download info, the download might have been removed already
            if "is not found" in str(e):
                LOGGER.debug(
                    f"onDownloadStarted: GID {gid} not found, download might have completed quickly"
                )
                return
            # For other errors, log and return
            LOGGER.error(
                f"onDownloadStarted: Error getting download info for {gid}: {e}"
            )
            return

        if options.get("follow-torrent", "") == "false":
            return

        if is_metadata(download):
            LOGGER.info(f"onDownloadStarted: {gid} METADATA")
            await sleep(1)
            if task := await get_task_by_gid(gid):
                task.listener.is_torrent = True
                if task.listener.select:
                    metamsg = "Downloading Metadata, wait then you can select files. Use torrent file to avoid this wait."
                    meta = await send_message(task.listener.message, metamsg)
                    while True:
                        await sleep(0.5)
                        if download.get("status", "") == "removed" or download.get(
                            "followedBy",
                            [],
                        ):
                            await delete_message(meta)
                            break
                        # Try to get updated download status with error handling
                        try:
                            download = await api.tellStatus(gid)
                        except Exception as e:
                            if "is not found" in str(e):
                                LOGGER.debug(
                                    f"onDownloadStarted: GID {gid} not found during metadata check"
                                )
                                await delete_message(meta)
                                break
                            LOGGER.error(
                                f"Error getting download status during metadata check: {e}"
                            )
                            await delete_message(meta)
                            break
            return

        LOGGER.info(f"onDownloadStarted: {aria2_name(download)} - Gid: {gid}")
        await sleep(1)

        await sleep(2)
        if task := await get_task_by_gid(gid):
            # Try to get updated download status with error handling
            try:
                download = await api.tellStatus(gid)
            except Exception as e:
                if "is not found" in str(e):
                    LOGGER.debug(
                        f"onDownloadStarted: GID {gid} not found during duplicate check"
                    )
                    return
                LOGGER.error(
                    f"Error getting download status for duplicate check: {e}"
                )
                return

            task.listener.name = aria2_name(download)
            msg, button = await stop_duplicate_check(task.listener)
            if msg:
                await TorrentManager.aria2_remove(download)
                await task.listener.on_download_error(msg, button)
    except Exception as e:
        LOGGER.error(f"Error in onDownloadStarted handler: {e}")
        # Try to handle any remaining task cleanup if possible
        try:
            if gid and (task := await get_task_by_gid(gid)):
                await task.listener.on_download_error(f"Download start error: {e}")
        except Exception as inner_e:
            LOGGER.error(f"Failed to handle download start error: {inner_e}")


async def _on_download_complete(api, data):
    try:
        gid = data["params"][0]["gid"]

        # Check if task exists before trying to get download info
        task = await get_task_by_gid(gid)
        if not task:
            # If no task is found for this GID, it might have been already processed
            # or removed, so we can safely ignore this notification
            return

        # Try to get download info with error handling
        try:
            download = await api.tellStatus(gid)
            options = await api.getOption(gid)
        except Exception as e:
            # If we can't get download info but have a task, we can still proceed with completion
            if "is not found" in str(e):
                # Since we can't get download info, we'll just complete the task
                await task.listener.on_download_complete()
                return
            # For other errors, log and return
            LOGGER.error(f"onDownloadComplete: {e}")
            return

        # Check if we should follow this torrent
        if options.get("follow-torrent", "") == "false":
            return

        # Handle followed torrents (metadata downloads)
        if download.get("followedBy", []):
            new_gid = download.get("followedBy", [])[0]
            LOGGER.info(f"Gid changed from {gid} to {new_gid}")
            if task := await get_task_by_gid(new_gid):
                task.listener.is_torrent = True
                if Config.BASE_URL and task.listener.select:
                    if not task.queued:
                        await api.forcePause(new_gid)
                    SBUTTONS = bt_selection_buttons(new_gid)
                    msg = "Your download paused. Choose files then press Done Selecting button to start downloading."
                    await send_message(task.listener.message, msg, SBUTTONS)
        # Handle bittorrent downloads
        elif "bittorrent" in download:
            if task := await get_task_by_gid(gid):
                task.listener.is_torrent = True
                if hasattr(task, "seeding") and task.seeding:
                    LOGGER.info(
                        f"Cancelling Seed: {aria2_name(download)} onDownloadComplete",
                    )
                    await TorrentManager.aria2_remove(download)
                    await task.listener.on_upload_error(
                        f"Seeding stopped with Ratio: {task.ratio()} and Time: {task.seeding_time()}",
                    )
        # Handle regular downloads
        else:
            LOGGER.info(f"onDownloadComplete: {aria2_name(download)} - Gid: {gid}")
            if task := await get_task_by_gid(gid):
                try:
                    # Get the actual download path from aria2
                    download_path = download.get("dir", "")
                    download_files = download.get("files", [])

                    LOGGER.info(f"Aria2 download path: {download_path}")
                    LOGGER.info(f"Aria2 download files: {len(download_files)} files")

                    # Ensure the task listener directory exists
                    if not await aiopath.exists(task.listener.dir):
                        LOGGER.info(
                            f"Creating task listener directory: {task.listener.dir}"
                        )
                        await makedirs(task.listener.dir, exist_ok=True)

                    # Check if files need to be moved from aria2 download location to task directory
                    if download_path and download_path != task.listener.dir:
                        LOGGER.info(
                            f"Moving files from {download_path} to {task.listener.dir}"
                        )

                        # Check if the aria2 download directory exists and has files
                        if await aiopath.exists(download_path):
                            try:
                                from bot.helper.ext_utils.aiofiles_compat import (
                                    listdir,
                                )

                                aria2_files = await listdir(download_path)

                                if aria2_files:
                                    # Move files from aria2 download location to task directory
                                    from aioshutil import move

                                    for file_name in aria2_files:
                                        src_path = f"{download_path}/{file_name}"
                                        dst_path = f"{task.listener.dir}/{file_name}"

                                        if await aiopath.exists(src_path):
                                            LOGGER.info(
                                                f"Moving {src_path} to {dst_path}"
                                            )
                                            await move(src_path, dst_path)

                                    # Clean up empty aria2 download directory
                                    try:
                                        from aioshutil import rmtree

                                        await rmtree(
                                            download_path, ignore_errors=True
                                        )
                                    except Exception as cleanup_error:
                                        LOGGER.warning(
                                            f"Could not clean up aria2 directory {download_path}: {cleanup_error}"
                                        )
                                else:
                                    LOGGER.warning(
                                        f"Aria2 download directory {download_path} is empty"
                                    )
                            except Exception as move_error:
                                LOGGER.error(
                                    f"Error moving files from aria2 directory: {move_error}"
                                )
                        else:
                            LOGGER.warning(
                                f"Aria2 download directory {download_path} does not exist"
                            )

                    # Verify that the task directory now has files
                    if await aiopath.exists(task.listener.dir):
                        try:
                            from bot.helper.ext_utils.aiofiles_compat import listdir

                            task_files = await listdir(task.listener.dir)
                            LOGGER.info(
                                f"Task directory {task.listener.dir} contains {len(task_files)} files: {task_files}"
                            )
                        except Exception as list_error:
                            LOGGER.error(
                                f"Error listing task directory: {list_error}"
                            )

                    await task.listener.on_download_complete()
                except Exception as e:
                    LOGGER.error(f"Error in aria2 download complete handler: {e}")
                    await task.listener.on_download_error(
                        f"Error processing download: {e}"
                    )
                    return

                if intervals["stopAll"]:
                    return
                # Try to remove the download with error handling
                try:
                    await TorrentManager.aria2_remove(download)
                except Exception as e:
                    LOGGER.error(f"Error removing download {gid} from aria2: {e}")
    except Exception as e:
        LOGGER.error(f"Error in onDownloadComplete handler: {e}")
        # Try to get task and complete it even if there was an error
        try:
            if gid and (task := await get_task_by_gid(gid)):
                await task.listener.on_download_complete()
        except Exception as inner_e:
            LOGGER.error(f"Failed to complete task after error: {inner_e}")


async def _on_bt_download_complete(api, data):
    try:
        gid = data["params"][0]["gid"]
        await sleep(1)

        # Check if task exists before trying to get download info
        task = await get_task_by_gid(gid)
        if not task:
            # If no task is found for this GID, it might have been already processed
            # or removed, so we can safely ignore this notification
            return

        # Try to get download info with error handling
        try:
            download = await api.tellStatus(gid)
        except Exception as e:
            # If we can't get download info but have a task, we can still proceed with completion
            if "is not found" in str(e):
                # Since we can't get download info, we'll just complete the task
                task.listener.is_torrent = True
                await task.listener.on_download_complete()
                return
            # For other errors, log and return
            LOGGER.error(f"onBtDownloadComplete: {e}")
            return

        LOGGER.info(f"onBtDownloadComplete: {aria2_name(download)} - Gid: {gid}")

        task.listener.is_torrent = True

        # Get the actual download path from aria2
        download_path = download.get("dir", "")
        LOGGER.info(f"BT download path: {download_path}")

        # Ensure the task listener directory exists
        if not await aiopath.exists(task.listener.dir):
            LOGGER.info(
                f"Creating task listener directory for BT: {task.listener.dir}"
            )
            await makedirs(task.listener.dir, exist_ok=True)

        # Handle file selection if enabled
        if task.listener.select:
            res = download.get("files", [])
            for file_o in res:
                f_path = file_o.get("path", "")
                if file_o.get("selected", "") != "true" and await aiopath.exists(
                    f_path
                ):
                    with contextlib.suppress(Exception):
                        await remove(f_path)
            await clean_unwanted(download.dir)

        # Check if files need to be moved from aria2 download location to task directory for BT
        if download_path and download_path != task.listener.dir:
            LOGGER.info(
                f"Moving BT files from {download_path} to {task.listener.dir}"
            )

            # Check if the aria2 download directory exists and has files
            if await aiopath.exists(download_path):
                try:
                    from bot.helper.ext_utils.aiofiles_compat import listdir

                    aria2_files = await listdir(download_path)

                    if aria2_files:
                        # Move files from aria2 download location to task directory
                        from aioshutil import move

                        for file_name in aria2_files:
                            src_path = f"{download_path}/{file_name}"
                            dst_path = f"{task.listener.dir}/{file_name}"

                            if await aiopath.exists(src_path):
                                LOGGER.info(
                                    f"Moving BT file {src_path} to {dst_path}"
                                )
                                await move(src_path, dst_path)

                        # Clean up empty aria2 download directory
                        try:
                            from aioshutil import rmtree

                            await rmtree(download_path, ignore_errors=True)
                        except Exception as cleanup_error:
                            LOGGER.warning(
                                f"Could not clean up BT aria2 directory {download_path}: {cleanup_error}"
                            )
                    else:
                        LOGGER.warning(
                            f"BT aria2 download directory {download_path} is empty"
                        )
                except Exception as move_error:
                    LOGGER.error(
                        f"Error moving BT files from aria2 directory: {move_error}"
                    )
            else:
                LOGGER.warning(
                    f"BT aria2 download directory {download_path} does not exist"
                )

        # Handle seeding options
        if task.listener.seed:
            try:
                await api.changeOption(gid, {"max-upload-limit": "0"})
            except Exception as e:
                LOGGER.error(
                    f"{e} You are not able to seed because you added global option seed-time=0 without adding specific seed_time for this torrent GID: {gid}",
                )
        else:
            try:
                await api.forcePause(gid)
            except Exception as e:
                LOGGER.error(f"onBtDownloadComplete: {e} GID: {gid}")

        # Complete the download
        await task.listener.on_download_complete()

        if intervals["stopAll"]:
            return

        # Get updated download status
        try:
            download = await api.tellStatus(gid)
        except Exception as e:
            if "is not found" in str(e):
                return
            LOGGER.error(f"Error getting download status after completion: {e}")
            return

        # Handle seeding based on configuration
        if (
            task.listener.seed
            and download.get("status", "") == "complete"
            and await get_task_by_gid(gid)
        ):
            LOGGER.info(f"Cancelling Seed: {aria2_name(download)}")
            try:
                await TorrentManager.aria2_remove(download)
            except Exception as e:
                LOGGER.error(f"Error removing download {gid} from aria2: {e}")
            await task.listener.on_upload_error(
                f"Seeding stopped with Ratio: {task.ratio()} and Time: {task.seeding_time()}",
            )
        elif (
            task.listener.seed
            and download.get("status", "") == "complete"
            and not await get_task_by_gid(gid)
        ):
            pass
        elif task.listener.seed and not task.listener.is_cancelled:
            async with task_dict_lock:
                if task.listener.mid not in task_dict:
                    try:
                        await TorrentManager.aria2_remove(download)
                    except Exception as e:
                        LOGGER.error(
                            f"Error removing download {gid} from aria2: {e}"
                        )
                    return
                task_dict[task.listener.mid] = Aria2Status(task.listener, gid, True)
                task_dict[task.listener.mid].start_time = time()
            LOGGER.info(f"Seeding started: {aria2_name(download)} - Gid: {gid}")
            await update_status_message(task.listener.message.chat.id)
        else:
            try:
                await TorrentManager.aria2_remove(download)
            except Exception as e:
                LOGGER.error(f"Error removing download {gid} from aria2: {e}")
    except Exception as e:
        LOGGER.error(f"Error in onBtDownloadComplete handler: {e}")
        # Try to get task and complete it even if there was an error
        try:
            if gid and (task := await get_task_by_gid(gid)):
                task.listener.is_torrent = True
                await task.listener.on_download_complete()
        except Exception as inner_e:
            LOGGER.error(f"Failed to complete BT task after error: {inner_e}")


async def _on_download_stopped(_, data):
    try:
        gid = data["params"][0]["gid"]
        await sleep(4)

        # Check if task exists
        task = await get_task_by_gid(gid)
        if not task:
            # If no task is found for this GID, it might have been already processed
            # or removed, so we can safely ignore this notification
            return

        # Handle the stopped download
        await task.listener.on_download_error("Dead torrent!")
    except Exception as e:
        LOGGER.error(f"Error in onDownloadStopped handler: {e}")


async def _on_download_error(api, data):
    try:
        gid = data["params"][0]["gid"]
        await sleep(1)
        LOGGER.info(f"onDownloadError: {gid}")

        # Check if task exists before trying to get download info
        task = await get_task_by_gid(gid)
        if not task:
            # If no task is found for this GID, it might have been already processed
            # or removed, so we can safely ignore this notification
            return

        # Initialize error message and options
        error = "Unknown error"
        options = {"follow-torrent": "true"}  # Default value

        # Try to get download info with error handling
        try:
            download = await api.tellStatus(gid)
            options = await api.getOption(gid)
            error = download.get("errorMessage", "Download failed")
            LOGGER.info(f"Download Error: {error}")

            # Provide more user-friendly error messages for common issues
            if "status=403" in error or "Forbidden" in error:
                error = "Access denied (403): The server refused the request. This could be due to:\n• Link expired or invalid\n• Server blocking the bot\n• Authentication required\n• Rate limiting"
            elif "status=404" in error or "Not Found" in error:
                error = "File not found (404): The requested file no longer exists on the server"
            elif "status=429" in error or "Too Many Requests" in error:
                error = (
                    "Rate limited (429): Too many requests. Please try again later"
                )
            elif "status=500" in error or "Internal Server Error" in error:
                error = "Server error (500): The server encountered an internal error. Please try again later"
            elif "No URI available" in error:
                error = "No download links available: The download source has no valid URLs. This could be due to:\n• Link expired or removed\n• Server maintenance\n• Torrent with no seeders\n• Invalid or broken link"
            elif "Connection refused" in error or "Connection reset" in error:
                error = "Connection failed: Unable to connect to the server. Please check the link and try again"
            elif "timeout" in error.lower():
                error = "Download timeout: The server took too long to respond. Please try again"

        except Exception as e:
            # If we can't get download info, use a generic error message
            if "is not found" in str(e):
                error = "Download failed or was removed from aria2"
            else:
                LOGGER.error(f"Error getting download info: {e}")
                error = f"Download failed: {e!s}"

        # Check if we should follow this torrent
        if options.get("follow-torrent", "") == "false":
            return

        # Handle the error through the listener
        try:
            await task.listener.on_download_error(error)
        except Exception as e:
            LOGGER.error(f"Failed to handle aria2 error through listener: {e!s}")
            # Fallback error handling
            try:
                error_msg = await send_message(
                    task.listener.message,
                    f"{task.listener.tag} Download Error: {error}",
                )
                create_task(auto_delete_message(error_msg, time=300))  # noqa: RUF006
            except Exception as msg_e:
                LOGGER.error(f"Failed to send error message: {msg_e}")
    except Exception as e:
        LOGGER.error(f"Error in onDownloadError handler: {e}")


def add_aria2_callbacks():
    TorrentManager.aria2.onBtDownloadComplete(_on_bt_download_complete)
    TorrentManager.aria2.onDownloadComplete(_on_download_complete)
    TorrentManager.aria2.onDownloadError(_on_download_error)
    TorrentManager.aria2.onDownloadStart(_on_download_started)
    TorrentManager.aria2.onDownloadStop(_on_download_stopped)
