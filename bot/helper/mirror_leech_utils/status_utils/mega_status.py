from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class MegaDownloadStatus:
    def __init__(self, listener, obj, gid, status):
        self.listener = listener
        self._obj = obj
        self._size = self.listener.size
        self._gid = gid
        self._status = status
        self.tool = "mega"

    def name(self):
        # For operations where main name might be empty, use subname if available
        if (
            hasattr(self.listener, "subname")
            and self.listener.subname
            and (not self.listener.name or self.listener.name.strip() == "")
        ):
            return self.listener.subname
        return self.listener.name

    def progress_raw(self):
        try:
            return round(self._obj.downloaded_bytes / self._size * 100, 2)
        except ZeroDivisionError:
            return 0.0

    def progress(self):
        return f"{self.progress_raw()}%"

    def status(self):
        return MirrorStatus.STATUS_DOWNLOADING

    def processed_bytes(self):
        return get_readable_file_size(self._obj.downloaded_bytes)

    def eta(self):
        try:
            seconds = (self._size - self._obj.downloaded_bytes) / self._obj.speed
            return get_readable_time(seconds)
        except ZeroDivisionError:
            return "-"

    def size(self):
        return get_readable_file_size(self._size)

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed)}/s"

    def gid(self):
        return self._gid

    def task(self):
        return self._obj

    async def cancel_task(self):
        await self._obj.cancel_task()


class MegaUploadStatus:
    def __init__(self, listener, obj, gid, status):
        self.listener = listener
        self._obj = obj
        self._size = self.listener.size
        self._gid = gid
        self._status = status
        self.tool = "mega"

    def name(self):
        # For operations where main name might be empty, use subname if available
        if (
            hasattr(self.listener, "subname")
            and self.listener.subname
            and (not self.listener.name or self.listener.name.strip() == "")
        ):
            return self.listener.subname
        return self.listener.name

    def progress_raw(self):
        try:
            return round(self._obj.downloaded_bytes / self._size * 100, 2)
        except Exception:
            return 0.0

    def progress(self):
        return f"{self.progress_raw()}%"

    def status(self):
        return MirrorStatus.STATUS_UPLOADING

    def processed_bytes(self):
        return get_readable_file_size(self._obj.downloaded_bytes)

    def eta(self):
        try:
            seconds = (self._size - self._obj.downloaded_bytes) / self._obj.speed
            return get_readable_time(seconds)
        except ZeroDivisionError:
            return "-"

    def size(self):
        return get_readable_file_size(self._size)

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed)}/s"

    def gid(self):
        return self._gid

    def task(self):
        return self._obj

    async def cancel_task(self):
        await self._obj.cancel_task()
