"""
Zotify download status tracking
"""

import time

from bot import LOGGER
from bot.helper.ext_utils.status_utils import MirrorStatus


class ZotifyDownloadStatus:
    """Status class for Zotify downloads following standard bot pattern"""

    def __init__(self, listener, download_helper, queued=False):
        self.listener = listener
        self.download_helper = download_helper
        self.queued = queued
        self._start_time = time.time()
        self.tool = "zotify"  # Required by status system

    def gid(self):
        """Get unique identifier"""
        return self.listener.mid

    def status(self):
        """Get current status"""
        if self.listener.is_cancelled:
            return MirrorStatus.STATUS_PAUSED
        if self.queued:
            return MirrorStatus.STATUS_QUEUEDL
        return MirrorStatus.STATUS_DOWNLOAD

    def name(self):
        """Get download name"""
        if (
            hasattr(self.download_helper, "_current_track")
            and self.download_helper._current_track
        ):
            return self.download_helper._current_track

        # For operations where main name might be empty, use subname if available
        listener_name = self.listener.name or "Zotify Download"
        if (
            (
                not listener_name
                or listener_name.strip() == ""
                or listener_name == "Zotify Download"
            )
            and hasattr(self.listener, "subname")
            and self.listener.subname
        ):
            return self.listener.subname
        return listener_name

    def size(self):
        """Get total size"""
        return "N/A"

    def processed_bytes(self):
        """Get processed bytes"""
        return "N/A"

    def speed(self):
        """Get download speed"""
        return "N/A"

    def eta(self):
        """Get estimated time of arrival"""
        return "-"

    def progress(self):
        """Get download progress"""
        return "N/A"

    def task(self):
        """Get task object (standard method)"""
        return self

    async def cancel_task(self):
        """Cancel the download task (standard method)"""
        self.listener.is_cancelled = True
        if hasattr(self.download_helper, "cancel_download"):
            self.download_helper.cancel_download()

        # Perform music-specific cleanup
        try:
            from bot.helper.ext_utils.gc_utils import music_download_cleanup

            music_download_cleanup()
        except Exception:
            pass

        LOGGER.info(f"Cancelling Zotify Download: {self.name()}")
        await self.listener.on_download_error("Stopped by user!")
