import contextlib

from bot import LOGGER
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class FFmpegStatus:
    def __init__(self, listener, obj, gid, status=""):
        self.listener = listener
        self._obj = obj
        self._gid = gid
        self._cstatus = status
        # Set the cstatus attribute on the listener for progress calculation
        if hasattr(listener, "cstatus"):
            listener.cstatus = status
        self.tool = "xtra"

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed_raw)}/s"

    def processed_bytes(self):
        return get_readable_file_size(self._obj.processed_bytes)

    def progress(self):
        return f"{round(self._obj.progress_raw, 2)}%"

    def gid(self):
        return self._gid

    def name(self):
        # For split operations, if the main name is empty or not meaningful,
        # use the current file being processed (subname) instead
        if (
            self._cstatus == "Split"
            and hasattr(self.listener, "subname")
            and self.listener.subname
            and (not self.listener.name or self.listener.name.strip() == "")
        ):
            return self.listener.subname
        return self.listener.name

    def size(self):
        return get_readable_file_size(self.listener.size)

    def eta(self):
        return get_readable_time(self._obj.eta_raw) if self._obj.eta_raw else "-"

    def status(self):
        if self._cstatus == "Convert":
            return MirrorStatus.STATUS_CONVERT
        if self._cstatus == "Split":
            return MirrorStatus.STATUS_SPLIT
        if self._cstatus == "Sample Video":
            return MirrorStatus.STATUS_SAMVID
        if self._cstatus == "Metadata":
            return MirrorStatus.STATUS_METADATA
        if self._cstatus == "Watermark":
            return MirrorStatus.STATUS_WATERMARK
        if self._cstatus == "E_thumb":
            return MirrorStatus.STATUS_ETHUMB
        if self._cstatus == "Merge":
            return MirrorStatus.STATUS_MERGE
        if self._cstatus == "Compress":
            return MirrorStatus.STATUS_COMPRESS
        if self._cstatus == "Trim":
            return MirrorStatus.STATUS_TRIM
        if self._cstatus == "Extract":
            return MirrorStatus.STATUS_EXTRACT
        if self._cstatus == "Add":
            return MirrorStatus.STATUS_ADD
        if self._cstatus == "swap":
            return MirrorStatus.STATUS_SWAP
        return MirrorStatus.STATUS_FFMPEG

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

    def refresh(self):
        # Get current status
        if (
            self.listener.subproc is not None
            and self.listener.subproc.returncode is None
        ):
            self.message = self.message.rsplit("\n", 1)[0]
            self.message += f"\n{self.progress()}"

            # Add ETA and speed information if available
            if hasattr(self._obj, "eta_raw") and self._obj.eta_raw:
                self.message += f" | ETA: {self.eta()}"
            if hasattr(self._obj, "speed_raw") and self._obj.speed_raw:
                self.message += f" | Speed: {self.speed()}"

            # Add file size information if available
            if hasattr(self.listener, "size") and self.listener.size:
                self.message += f" | Size: {self.size()}"

            # Add codec information if available
            if hasattr(self._obj, "codec") and self._obj.codec:
                self.message += f" | Codec: {self._obj.codec}"

            return
