from asyncio import create_task, gather, iscoroutinefunction
from time import time

from psutil import cpu_percent, disk_usage, virtual_memory

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    bot_start_time,
    intervals,
    sabnzbd_client,
    status_dict,
    task_dict,
    task_dict_lock,
)
from bot.core.jdownloader_booter import jdownloader
from bot.core.torrent_manager import TorrentManager
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
    speed_string_to_bytes,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
    send_status_message,
    update_status_message,
)


async def get_download_status(download):
    tool = download.tool
    if tool in [
        "telegram",
        "yt-dlp",
        "rclone",
        "gDriveApi",
        "youtube",
    ]:
        speed = download.speed()
    else:
        speed = 0
    return (
        await download.status()
        if iscoroutinefunction(download.status)
        else download.status()
    ), speed


@new_task
async def task_status(_, message):
    # Delete the /status command message immediately
    await delete_message(message)

    async with task_dict_lock:
        count = len(task_dict)

    if count == 0:
        # Send status message when no tasks
        currentTime = get_readable_time(time() - bot_start_time)
        free = get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)
        msg = "No Active Tasks!\n"
        msg += (
            f"\n<b>CPU:</b> {cpu_percent()}% | <b>FREE:</b> {free}"
            f"\n<b>RAM:</b> {virtual_memory().percent}% | <b>UPTIME:</b> {currentTime}"
        )
        reply_message = await send_message(message, msg)
        # Auto delete status message after 5 minutes when no tasks
        create_task(auto_delete_message(reply_message, time=300))  # noqa: RUF006
    else:
        # Send status message when tasks are running
        text = message.text.split()
        if len(text) > 1:
            user_id = message.from_user.id if text[1] == "me" else int(text[1])
        else:
            user_id = 0
            sid = message.chat.id
            if obj := intervals["status"].get(sid):
                obj.cancel()
                del intervals["status"][sid]
        await send_status_message(message, user_id)


@new_task
async def status_pages(_, query):
    try:
        data = query.data.split()
        key = int(data[1])

        # Handle query.answer() with proper error handling
        try:
            await query.answer()
        except Exception:
            # Continue processing even if answering the query fails
            pass
    except Exception as e:
        # Handle any transport closing errors at the top level
        if "closing transport" in str(e).lower():
            # Silently ignore transport closing errors as they're expected during cleanup
            return
        LOGGER.error(f"Error in status_pages: {e}")
        return

    try:
        if data[2] == "ref":
            await update_status_message(key, force=True)
        elif data[2] in ["nex", "pre"]:
            async with task_dict_lock:
                if key in status_dict:
                    if data[2] == "nex":
                        status_dict[key]["page_no"] += status_dict[key]["page_step"]
                    else:
                        status_dict[key]["page_no"] -= status_dict[key]["page_step"]
        elif data[2] == "ps":
            async with task_dict_lock:
                if key in status_dict:
                    status_dict[key]["page_step"] = int(data[3])
        elif data[2] == "st":
            async with task_dict_lock:
                if key in status_dict:
                    status_dict[key]["status"] = data[3]
            await update_status_message(key, force=True)
        elif data[2] == "ov":
            # Handle aria2 connection errors gracefully
            try:
                ds, ss = await TorrentManager.overall_speed()
            except Exception as e:
                # Ignore transport closing errors as they're expected during cleanup
                if "closing transport" not in str(e).lower():
                    LOGGER.warning(f"Error getting aria2 speeds: {e}")
                ds, ss = 0, 0

            if sabnzbd_client.LOGGED_IN:
                try:
                    sds = await sabnzbd_client.get_downloads()
                    sds = int(float(sds["queue"].get("kbpersec", "0"))) * 1024
                    ds += sds
                except Exception as e:
                    LOGGER.warning(f"Error getting SABnzbd speeds: {e}")

            if jdownloader.is_connected:
                try:
                    jdres = await jdownloader.device.downloadcontroller.get_speed_in_bytes()
                    ds += jdres
                except Exception as e:
                    LOGGER.warning(f"Error getting JDownloader speeds: {e}")
            message = query.message
            tasks = {
                "Download": 0,
                "Upload": 0,
                "Seed": 0,
                "Archive": 0,
                "Extract": 0,
                "Split": 0,
                "QueueDl": 0,
                "QueueUp": 0,
                "Clone": 0,
                "CheckUp": 0,
                "Pause": 0,
                "SamVid": 0,
                "ConvertMedia": 0,
                "Compress": 0,
                "FFmpeg": 0,
                "Trim": 0,
                "Swap": 0,
            }
            dl_speed = ds
            up_speed = 0
            seed_speed = ss
            async with task_dict_lock:
                status_results = await gather(
                    *(
                        get_download_status(download)
                        for download in task_dict.values()
                    ),
                )
                for status, speed in status_results:
                    match status:
                        case MirrorStatus.STATUS_DOWNLOAD:
                            tasks["Download"] += 1
                            if speed:
                                dl_speed += speed_string_to_bytes(speed)
                        case MirrorStatus.STATUS_UPLOAD:
                            tasks["Upload"] += 1
                            up_speed += speed_string_to_bytes(speed)
                        case MirrorStatus.STATUS_SEED:
                            tasks["Seed"] += 1
                        case MirrorStatus.STATUS_ARCHIVE:
                            tasks["Archive"] += 1
                        case MirrorStatus.STATUS_EXTRACT:
                            tasks["Extract"] += 1
                        case MirrorStatus.STATUS_SPLIT:
                            tasks["Split"] += 1
                        case MirrorStatus.STATUS_QUEUEDL:
                            tasks["QueueDl"] += 1
                        case MirrorStatus.STATUS_QUEUEUP:
                            tasks["QueueUp"] += 1
                        case MirrorStatus.STATUS_CLONE:
                            tasks["Clone"] += 1
                        case MirrorStatus.STATUS_CHECK:
                            tasks["CheckUp"] += 1
                        case MirrorStatus.STATUS_PAUSED:
                            tasks["Pause"] += 1
                        case MirrorStatus.STATUS_SAMVID:
                            tasks["SamVid"] += 1
                        case MirrorStatus.STATUS_CONVERT:
                            tasks["ConvertMedia"] += 1
                        case MirrorStatus.STATUS_COMPRESS:
                            tasks["Compress"] += 1
                        case MirrorStatus.STATUS_TRIM:
                            tasks["Trim"] += 1
                        case MirrorStatus.STATUS_SWAP:
                            tasks["Swap"] += 1
                        case MirrorStatus.STATUS_FFMPEG:
                            tasks["FFmpeg"] += 1
                        case _:
                            tasks["Download"] += 1

            msg = f"""<b>DL:</b> {tasks["Download"]} | <b>UP:</b> {tasks["Upload"]} | <b>SD:</b> {tasks["Seed"]} | <b>AR:</b> {tasks["Archive"]}
<b>EX:</b> {tasks["Extract"]} | <b>SP:</b> {tasks["Split"]} | <b>QD:</b> {tasks["QueueDl"]} | <b>QU:</b> {tasks["QueueUp"]}
<b>CL:</b> {tasks["Clone"]} | <b>CK:</b> {tasks["CheckUp"]} | <b>PA:</b> {tasks["Pause"]} | <b>SV:</b> {tasks["SamVid"]}
<b>CM:</b> {tasks["ConvertMedia"]} | <b>CP:</b> {tasks["Compress"]} | <b>TR:</b> {tasks["Trim"]} | <b>SW:</b> {tasks["Swap"]} | <b>FF:</b> {tasks["FFmpeg"]}

<b>ODLS:</b> {get_readable_file_size(dl_speed)}/s
<b>OULS:</b> {get_readable_file_size(up_speed)}/s
<b>OSDS:</b> {get_readable_file_size(seed_speed)}/s
"""
            button = ButtonMaker()
            button.data_button("Back", f"status {data[1]} ref")
            await edit_message(message, msg, button.build_menu())
    except Exception as e:
        # Handle any transport closing errors at the function level
        if "closing transport" in str(e).lower():
            # Silently ignore transport closing errors as they're expected during cleanup
            return
        LOGGER.error(f"Error in status_pages processing: {e}")
        return
