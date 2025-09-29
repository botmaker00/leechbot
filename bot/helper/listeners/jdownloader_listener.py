from asyncio import create_task, sleep

from bot import LOGGER, intervals, jd_downloads, jd_listener_lock
from bot.core.jdownloader_booter import jdownloader
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.status_utils import get_task_by_gid
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


@new_task
async def remove_download(gid):
    if intervals["stopAll"]:
        return
    await jdownloader.device.downloads.remove_links(
        package_ids=jd_downloads[gid]["ids"],
    )
    if task := await get_task_by_gid(gid):
        try:
            await task.listener.on_download_error("Download removed manually!")
        except Exception as e:
            LOGGER.error(f"Failed to handle JD error through listener: {e!s}")
            # Fallback error handling
            error_msg = await send_message(
                task.listener.message,
                f"{task.listener.tag} Download removed manually!",
            )
            create_task(auto_delete_message(error_msg, time=300))  # noqa: RUF006
        async with jd_listener_lock:
            del jd_downloads[gid]


@new_task
async def _on_download_complete(gid):
    if task := await get_task_by_gid(gid):
        if task.listener.select:
            async with jd_listener_lock:
                await jdownloader.device.downloads.cleanup(
                    "DELETE_DISABLED",
                    "REMOVE_LINKS_AND_DELETE_FILES",
                    "ALL",
                    package_ids=jd_downloads[gid]["ids"],
                )
        try:
            # Ensure the download directory exists before proceeding
            from bot.helper.ext_utils.aiofiles_compat import aiopath, makedirs

            if not await aiopath.exists(task.listener.dir):
                LOGGER.error(
                    f"Download directory does not exist: {task.listener.dir}"
                )
                await makedirs(task.listener.dir, exist_ok=True)
                LOGGER.info(f"Created download directory: {task.listener.dir}")

            await task.listener.on_download_complete()
        except Exception as e:
            LOGGER.error(f"Error in JDownloader download complete handler: {e}")
            await task.listener.on_download_error(f"Error processing download: {e}")
            return

        if intervals["stopAll"]:
            return
        async with jd_listener_lock:
            if gid in jd_downloads:
                await jdownloader.device.downloads.remove_links(
                    package_ids=jd_downloads[gid]["ids"],
                )
                del jd_downloads[gid]


@new_task
async def _jd_listener():
    while True:
        await sleep(3)
        async with jd_listener_lock:
            if len(jd_downloads) == 0:
                intervals["jd"] = ""
                break
            try:
                packages = await jdownloader.device.downloads.query_packages(
                    [{"finished": True, "saveTo": True}],
                )
            except Exception:
                continue

            all_packages = {pack["uuid"]: pack for pack in packages}
            for d_gid, d_dict in list(jd_downloads.items()):
                if d_dict["status"] == "down":
                    for index, pid in enumerate(d_dict["ids"]):
                        if pid not in all_packages:
                            del jd_downloads[d_gid]["ids"][index]
                    if len(jd_downloads[d_gid]["ids"]) == 0:
                        path = jd_downloads[d_gid]["path"]
                        jd_downloads[d_gid]["ids"] = [
                            uid
                            for uid, pk in all_packages.items()
                            if pk["saveTo"].startswith(path)
                        ]
                    if len(jd_downloads[d_gid]["ids"]) == 0:
                        await remove_download(d_gid)

            if completed_packages := [
                pack["uuid"] for pack in packages if pack.get("finished", False)
            ]:
                for d_gid, d_dict in list(jd_downloads.items()):
                    if d_dict["status"] == "down":
                        is_finished = all(
                            did in completed_packages for did in d_dict["ids"]
                        )
                        if is_finished:
                            jd_downloads[d_gid]["status"] = "done"
                            await _on_download_complete(d_gid)


async def on_download_start():
    async with jd_listener_lock:
        if not intervals["jd"]:
            intervals["jd"] = await _jd_listener()
