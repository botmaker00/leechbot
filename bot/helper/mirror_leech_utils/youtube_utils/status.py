import time
from logging import getLogger

from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)

LOGGER = getLogger(__name__)


class YouTubeStatus:
    def __init__(self, listener, youtube_upload, gid, status):
        self._listener = listener
        self._youtube_upload = youtube_upload
        self._gid = gid
        self._status = status
        self._start_time = time.time()
        self.tool = "youtube"  # Required by status system

    def gid(self):
        return self._gid

    def name(self):
        return self._listener.name

    def size(self):
        return get_readable_file_size(self._youtube_upload._total_bytes)

    def status(self):
        if self._youtube_upload._is_errored:
            return MirrorStatus.STATUS_PAUSED  # Use existing status for errors
        if self._listener.is_cancelled:
            return MirrorStatus.STATUS_PAUSED  # Use existing status for cancelled
        if self._youtube_upload.is_uploading:
            return MirrorStatus.STATUS_UPLOAD  # Use existing upload status
        return MirrorStatus.STATUS_UPLOAD  # Use upload status for completed uploads

    def processed_bytes(self):
        return get_readable_file_size(self._youtube_upload._uploaded_bytes)

    def progress(self):
        if self._youtube_upload._total_bytes > 0:
            return f"{round(100 * self._youtube_upload._uploaded_bytes / self._youtube_upload._total_bytes, 2)}%"
        return "0%"

    def speed(self):
        if self._youtube_upload._speed > 0:
            return f"{get_readable_file_size(self._youtube_upload._speed)}/s"
        return "0 B/s"

    def eta(self):
        if (
            isinstance(self._youtube_upload._eta, int | float)
            and self._youtube_upload._eta > 0
        ):
            return get_readable_time(self._youtube_upload._eta)
        return "-"

    def elapsed(self):
        return get_readable_time(time.time() - self._start_time)

    def seeders_and_leechers(self):
        return "YouTube Upload"

    def upload_details(self):
        return {
            "Platform": "YouTube",
            "Privacy": getattr(self._youtube_upload, "privacy_status", "unlisted"),
            "Category": getattr(self._youtube_upload, "category_id", "22"),
        }

    def download_details(self):
        return self.upload_details()

    def listener(self):
        return self._listener

    async def cancel_task(self):
        LOGGER.info(f"Cancelling YouTube Upload: {self.name()}")
        self._listener.is_cancelled = True
        if self._youtube_upload:
            self._youtube_upload.cancel()
        # YouTube upload doesn't have its own error handling, so we handle it here
        await self._listener.on_upload_error("YouTube upload stopped by user!")

    def task(self):
        return self
