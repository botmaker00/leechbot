from asyncio import create_task, sleep

from aiohttp.client_exceptions import ClientError

from bot import LOGGER
from bot.core.torrent_manager import TorrentManager, aria2_name
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


class DirectListener:
    def __init__(self, path, listener, a2c_opt):
        self.listener = listener
        self._path = path
        self._a2c_opt = a2c_opt
        self._proc_bytes = 0
        self._failed = 0
        self.download_task = None
        self.name = self.listener.name

    @property
    def processed_bytes(self):
        if self.download_task:
            return self._proc_bytes + int(
                self.download_task.get("completedLength", "0"),
            )
        return self._proc_bytes

    @property
    def speed(self):
        return (
            int(self.download_task.get("downloadSpeed", "0"))
            if self.download_task
            else 0
        )

    async def download(self, contents):
        self.is_downloading = True
        for content in contents:
            if self.listener.is_cancelled:
                break
            if content["path"]:
                self._a2c_opt["dir"] = f"{self._path}/{content['path']}"
            else:
                self._a2c_opt["dir"] = self._path
            filename = content["filename"]
            self._a2c_opt["out"] = filename

            # Validate URL before attempting download
            url = content["url"]
            if not url or not url.startswith(("http://", "https://", "ftp://")):
                LOGGER.error(f"Invalid URL for direct download: {url}")
                await self.listener.on_download_error(f"Invalid download URL: {url}")
                return

            try:
                gid = await TorrentManager.aria2.addUri(
                    uris=[url],
                    options=self._a2c_opt,
                    position=0,
                )
            except (TimeoutError, ClientError, Exception) as e:
                self._failed += 1
                LOGGER.error(f"Unable to download {filename} due to: {e}")
                continue
            self.download_task = await TorrentManager.aria2.tellStatus(gid)
            while True:
                if self.listener.is_cancelled:
                    if self.download_task:
                        await TorrentManager.aria2_remove(self.download_task)
                    break
                self.download_task = await TorrentManager.aria2.tellStatus(gid)
                if error_message := self.download_task.get("errorMessage"):
                    self._failed += 1
                    LOGGER.error(
                        f"Unable to download {aria2_name(self.download_task)} due to: {error_message}",
                    )
                    await TorrentManager.aria2_remove(self.download_task)
                    break
                if self.download_task.get("status", "") == "complete":
                    self._proc_bytes += int(
                        self.download_task.get("totalLength", "0"),
                    )
                    await TorrentManager.aria2_remove(self.download_task)
                    break
                await sleep(1)
            self.download_task = None
        if self.listener.is_cancelled:
            return
        if self._failed == len(contents):
            await self.listener.on_download_error(
                "All files are failed to download!",
            )
            return
        await self.listener.on_download_complete()
        return

    async def cancel_task(self):
        self.listener.is_cancelled = True
        LOGGER.info(f"Cancelling Download: {self.listener.name}")
        try:
            await self.listener.on_download_error("Download Cancelled by User!")
        except Exception as e:
            LOGGER.error(f"Failed to handle cancel through listener: {e!s}")
            # Fallback error handling
            error_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} Download Cancelled by User!",
            )
            create_task(auto_delete_message(error_msg, time=300))  # noqa: RUF006
        if self.download_task:
            await TorrentManager.aria2_remove(self.download_task)
