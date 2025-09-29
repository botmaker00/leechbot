from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class YtDlpStatus:
    def __init__(self, listener, obj, gid):
        self._obj = obj
        self._gid = gid
        self.listener = listener
        self.tool = "yt-dlp"

    def gid(self):
        return self._gid

    def processed_bytes(self):
        return get_readable_file_size(self._obj.downloaded_bytes)

    def size(self):
        return get_readable_file_size(self._obj.size)

    def status(self):
        return MirrorStatus.STATUS_DOWNLOAD

    def name(self):
        # For operations where main name might be empty, use subname if available
        if (
            hasattr(self.listener, "subname")
            and self.listener.subname
            and (not self.listener.name or self.listener.name.strip() == "")
        ):
            return self.listener.subname
        return self.listener.name

    def progress(self):
        return f"{round(self._obj.progress, 2)}%"

    def speed(self):
        return f"{get_readable_file_size(self._obj.download_speed)}/s"

    def eta(self):
        if self._obj.eta != "-":
            return get_readable_time(self._obj.eta)
        try:
            # Check if download is stalled (zero speed or no progress)
            if self._obj.download_speed == 0:
                return "∞"  # Infinity symbol for stalled download

            # Check if speed is too slow (less than 50 KB/s)
            if self._obj.download_speed < 50 * 1024:
                # Calculate ETA
                seconds = (
                    self._obj.size - self._obj.downloaded_bytes
                ) / self._obj.download_speed

                # If ETA is more than 4 hours for slow download, mark it
                if seconds > 4 * 60 * 60:
                    return "⚠️ >4h"  # Warning symbol for very long ETA
                # If ETA is more than 24 hours, mark it differently
                if seconds > 24 * 60 * 60:
                    return "⚠️ >24h"  # Warning symbol for extremely long ETA

            # Calculate ETA based on remaining bytes and current speed
            seconds = (
                self._obj.size - self._obj.downloaded_bytes
            ) / self._obj.download_speed
            return get_readable_time(seconds)
        except Exception:
            return "-"

    def task(self):
        return self._obj
