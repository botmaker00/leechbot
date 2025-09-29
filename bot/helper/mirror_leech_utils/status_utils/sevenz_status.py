import contextlib
from time import time

from bot import LOGGER
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class SevenZStatus:
    def __init__(self, listener, obj, gid, status=""):
        self.listener = listener
        self._obj = obj
        self._gid = gid
        self._start_time = time()
        self._cstatus = status
        self.tool = "7z"

    def gid(self):
        return self._gid

    def _speed_raw(self):
        return self._obj.processed_bytes / (time() - self._start_time)

    def progress(self):
        return self._obj.progress

    def speed(self):
        return f"{get_readable_file_size(self._speed_raw())}/s"

    def processed_bytes(self):
        return get_readable_file_size(self._obj.processed_bytes)

    def name(self):
        # For operations where main name might be empty, use subname if available
        if (
            hasattr(self.listener, "subname")
            and self.listener.subname
            and (not self.listener.name or self.listener.name.strip() == "")
        ):
            return self.listener.subname
        return self.listener.name

    def size(self):
        return get_readable_file_size(self.listener.size)

    def eta(self):
        try:
            seconds = (
                self.listener.subsize - self._obj.processed_bytes
            ) / self._speed_raw()
            return get_readable_time(seconds)
        except Exception:
            return "-"

    def status(self):
        if self._cstatus == "Extract":
            return MirrorStatus.STATUS_EXTRACT
        if self._cstatus == "Compress":
            return MirrorStatus.STATUS_COMPRESS
        return MirrorStatus.STATUS_ARCHIVE

    def task(self):
        return self

    async def cancel_task(self):
        LOGGER.info(f"Cancelling {self._cstatus}: {self.listener.name}")
        self.listener.is_cancelled = True
        if (
            self.listener.subproc is not None
            and self.listener.subproc.returncode is None
        ):
            with contextlib.suppress(Exception):
                self.listener.subproc.kill()
        await self.listener.on_upload_error(f"{self._cstatus} stopped by user!")
