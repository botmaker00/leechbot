"""
Gallery-dl status tracker
Following the pattern of yt_dlp_status.py
"""

from time import time

from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class GalleryDLStatus:
    """Gallery-dl download status following YtDlpStatus pattern"""

    def __init__(self, listener, obj, gid):
        self._obj = obj
        self._gid = gid
        self.listener = listener
        self.tool = "gallery-dl"
        self._start_time = time()

    def gid(self):
        """Get GID"""
        return self._gid

    def processed_bytes(self):
        """Get processed bytes"""
        if hasattr(self._obj, "downloaded_bytes"):
            return get_readable_file_size(self._obj.downloaded_bytes)
        if hasattr(self._obj, "processed_bytes"):
            return get_readable_file_size(self._obj.processed_bytes)
        return get_readable_file_size(0)

    def size(self):
        """Get total size"""
        if hasattr(self._obj, "size"):
            return get_readable_file_size(self._obj.size)
        if hasattr(self._obj, "total_size"):
            return get_readable_file_size(self._obj.total_size)
        return get_readable_file_size(0)

    def status(self):
        """Get current status"""
        return MirrorStatus.STATUS_DOWNLOAD

    def name(self):
        """Get download name"""
        if hasattr(self.listener, "name") and self.listener.name:
            listener_name = self.listener.name

            # For operations where main name might be empty, use subname if available
            if (
                (not listener_name or listener_name.strip() == "")
                and hasattr(self.listener, "subname")
                and self.listener.subname
            ):
                return self.listener.subname
            return listener_name
        return "Gallery-dl Download"

    def progress(self):
        """Get progress percentage"""
        if hasattr(self._obj, "progress"):
            return f"{round(self._obj.progress, 2)}%"
        # Calculate progress from size and processed bytes
        if (
            hasattr(self._obj, "size")
            and hasattr(self._obj, "processed_bytes")
            and self._obj.size > 0
        ):
            progress = (self._obj.processed_bytes / self._obj.size) * 100
            return f"{round(progress, 2)}%"
        return "0%"

    def speed(self):
        """Get download speed"""
        if hasattr(self._obj, "speed"):
            return f"{get_readable_file_size(self._obj.speed)}/s"
        return "0 B/s"

    def eta(self):
        """Get estimated time of arrival"""
        try:
            if hasattr(self.listener, "gallery_dl_helper"):
                helper = self.listener.gallery_dl_helper
                if helper.speed > 0 and helper.size > 0:
                    remaining_bytes = helper.size - helper.downloaded_bytes
                    eta_seconds = remaining_bytes / helper.speed
                    return get_readable_time(eta_seconds)
            return "-"
        except Exception:
            return "-"

    def elapsed(self):
        """Get elapsed time"""
        return get_readable_time(time() - self._start_time)

    def seeders_leechers(self):
        """Get seeders/leechers (not applicable for gallery-dl)"""
        return "N/A"

    def uploaded_bytes(self):
        """Get uploaded bytes (not applicable for downloads)"""
        return "0 B"

    def upload_speed(self):
        """Get upload speed (not applicable for downloads)"""
        return "0 B/s"

    def ratio(self):
        """Get ratio (not applicable for gallery-dl)"""
        return "N/A"

    def seeding_time(self):
        """Get seeding time (not applicable for gallery-dl)"""
        return "N/A"

    def download(self):
        """Get download object"""
        return self

    def listener(self):
        """Get listener object"""
        return self.listener

    def task(self):
        """Get task object for cancel compatibility"""
        return self

    async def cancel_task(self):
        """Cancel the download task"""
        if hasattr(self.listener, "gallery_dl_helper"):
            await self.listener.gallery_dl_helper.cancel_task()
        self.listener.is_cancelled = True
