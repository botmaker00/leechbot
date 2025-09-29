#!/usr/bin/env python3
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class DDLStatus:
    def __init__(self, obj, size, message, gid, upload_details):
        self.__obj = obj
        self.__size = size
        self.__gid = gid
        self.upload_details = upload_details
        self.message = message
        # Access the private listener attribute from DDLUploader
        self.listener = getattr(obj, "_DDLUploader__listener", None)
        self.tool = "ddl"

    def processed_bytes(self):
        return get_readable_file_size(self.__obj.processed_bytes)

    def size(self):
        return get_readable_file_size(self.__size)

    def status(self):
        return MirrorStatus.STATUS_UPLOADING

    def name(self):
        ddl_name = self.__obj.name

        # For operations where ddl name might be empty, use subname if available
        if (
            (not ddl_name or ddl_name.strip() == "")
            and hasattr(self.listener, "subname")
            and self.listener.subname
        ):
            return self.listener.subname
        return ddl_name

    def progress(self):
        try:
            progress_raw = self.__obj.processed_bytes / self.__size * 100
        except Exception:
            progress_raw = 0
        return f"{round(progress_raw, 2)}%"

    def speed(self):
        return f"{get_readable_file_size(self.__obj.speed)}/s"

    def eta(self):
        try:
            seconds = (self.__size - self.__obj.processed_bytes) / self.__obj.speed
            return get_readable_time(seconds)
        except Exception:
            return "-"

    def gid(self) -> str:
        return self.__gid

    def download(self):
        return self.__obj

    def eng(self):
        return self.__obj.engine

    def task(self):
        return self

    async def cancel_task(self):
        """Cancel the DDL upload task"""
        if self.listener:
            self.listener.is_cancelled = True
        if hasattr(self.__obj, "is_cancelled"):
            self.__obj.is_cancelled = True
        # DDL upload doesn't have its own error handling, so we handle it here
        if self.listener:
            await self.listener.on_upload_error("DDL upload cancelled by user!")
