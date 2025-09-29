from bot import LOGGER
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class GoogleDriveStatus:
    def __init__(self, listener, obj, gid, status):
        self.listener = listener
        self._obj = obj
        self._size = self.listener.size
        self._gid = gid
        self._status = status
        self.tool = "gdriveAPI"

    def processed_bytes(self):
        return get_readable_file_size(self._obj.processed_bytes)

    def size(self):
        return get_readable_file_size(self._size)

    def status(self):
        if self._status == "up":
            return MirrorStatus.STATUS_UPLOAD
        if self._status == "dl":
            return MirrorStatus.STATUS_DOWNLOAD
        return MirrorStatus.STATUS_CLONE

    def name(self):
        # For operations where main name might be empty, use subname if available
        if (
            hasattr(self.listener, "subname")
            and self.listener.subname
            and (not self.listener.name or self.listener.name.strip() == "")
        ):
            return self.listener.subname
        return self.listener.name

    def gid(self) -> str:
        return self._gid

    def progress_raw(self):
        try:
            return self._obj.processed_bytes / self._size * 100
        except Exception:
            return 0

    def progress(self):
        return f"{round(self.progress_raw(), 2)}%"

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed)}/s"

    def eta(self):
        try:
            seconds = (self._size - self._obj.processed_bytes) / self._obj.speed
            return get_readable_time(seconds)
        except Exception:
            return "-"

    def task(self):
        return self

    async def cancel_task(self):
        """Cancel the Google Drive upload task"""
        self.listener.is_cancelled = True

        # Let the actual uploader handle the cancellation and error messages
        # This prevents duplicate error messages
        if hasattr(self._obj, "cancel_task"):
            await self._obj.cancel_task()
        elif hasattr(self._obj, "cancel"):
            self._obj.cancel()
            # For non-async cancel methods, we need to handle the error message
            LOGGER.info(f"Cancelling Google Drive Upload: {self.name()}")
            await self.listener.on_upload_error("Upload stopped by user!")
        elif hasattr(self._obj, "_listener"):
            # Fallback for older implementations
            self._obj._listener.is_cancelled = True
            LOGGER.info(f"Cancelling Google Drive Upload: {self.name()}")
            await self.listener.on_upload_error("Upload stopped by user!")
