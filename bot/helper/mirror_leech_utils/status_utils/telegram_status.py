from bot import LOGGER
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class TelegramStatus:
    def __init__(self, listener, obj, gid, status):
        self.listener = listener
        self._obj = obj
        self._size = self.listener.size
        self._gid = gid
        self._status = status
        self.tool = "telegram"

    def processed_bytes(self):
        return get_readable_file_size(self._obj.processed_bytes)

    def size(self):
        return get_readable_file_size(self._size)

    def status(self):
        if self._status == "up":
            return MirrorStatus.STATUS_UPLOAD
        return MirrorStatus.STATUS_DOWNLOAD

    def name(self):
        # If this is an upload task and the uploader has a current file name, use that
        if (
            self._status == "up"
            and hasattr(self._obj, "_up_path")
            and self._obj._up_path
        ):
            # Extract the filename from the path
            import os

            current_filename = os.path.basename(self._obj._up_path)
            if current_filename:
                return current_filename
        # Otherwise use the original name, with subname fallback
        listener_name = self.listener.name

        # For operations where main name might be empty, use subname if available
        if (
            (not listener_name or listener_name.strip() == "")
            and hasattr(self.listener, "subname")
            and self.listener.subname
        ):
            return self.listener.subname
        return listener_name

    def progress(self):
        try:
            progress_raw = self._obj.processed_bytes / self._size * 100
        except Exception:
            progress_raw = 0
        return f"{round(progress_raw, 2)}%"

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed)}/s"

    def eta(self):
        try:
            seconds = (self._size - self._obj.processed_bytes) / self._obj.speed
            return get_readable_time(seconds)
        except Exception:
            return "-"

    def gid(self):
        return self._gid

    def task(self):
        return self

    async def cancel_task(self):
        """Cancel the telegram upload task"""
        self.listener.is_cancelled = True

        # Let the actual uploader handle the cancellation and error messages
        # This prevents duplicate error messages
        if hasattr(self._obj, "cancel_task"):
            await self._obj.cancel_task()
        # Fallback for older implementations
        elif hasattr(self._obj, "_listener"):
            self._obj._listener.is_cancelled = True
            # Only show error message if the actual uploader doesn't handle it
            LOGGER.info(f"Cancelling Telegram Upload: {self.name()}")
            await self.listener.on_upload_error("Upload stopped by user!")
