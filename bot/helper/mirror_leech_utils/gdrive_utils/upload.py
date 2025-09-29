import contextlib
from logging import getLogger
from os import listdir, remove
from os import path as ospath
from time import sleep

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import SetInterval, async_to_sync
from bot.helper.ext_utils.files_utils import get_mime_type_sync as get_mime_type
from bot.helper.mirror_leech_utils.gdrive_utils.helper import GoogleDriveHelper

LOGGER = getLogger(__name__)


class GoogleDriveUpload(GoogleDriveHelper):
    def __init__(self, listener, path):
        self.listener = listener
        self._updater = None
        self._path = path
        self._is_errored = False
        super().__init__()
        self.is_uploading = True

    def user_setting(self):
        if self.listener.up_dest.startswith("mtp:"):
            self.token_path = f"tokens/{self.listener.user_id}.pickle"
            self.listener.up_dest = self.listener.up_dest.replace("mtp:", "", 1)
            self.use_sa = False
        elif self.listener.up_dest.startswith("tp:"):
            self.listener.up_dest = self.listener.up_dest.replace("tp:", "", 1)
            self.use_sa = False
        elif self.listener.up_dest.startswith("sa:"):
            self.listener.up_dest = self.listener.up_dest.replace("sa:", "", 1)
            self.use_sa = True

    def upload(self):
        self.user_setting()
        self.service = self.authorize()
        LOGGER.info(f"Uploading: {self._path}")
        self._updater = SetInterval(self.update_interval, self.progress)
        link = None
        dir_id = None
        mime_type = None

        # Generate MediaInfo for mirror tasks if enabled
        # Check if MediaInfo is enabled for this user
        user_mediainfo_enabled = self.listener.user_dict.get(
            "MEDIAINFO_ENABLED", None
        )
        if user_mediainfo_enabled is None:
            user_mediainfo_enabled = Config.MEDIAINFO_ENABLED

        # Generate MediaInfo if enabled and it's a file (not a folder)
        if user_mediainfo_enabled and ospath.isfile(self._path):
            from bot.modules.mediainfo import gen_mediainfo

            try:
                # Generate MediaInfo for the file
                self.listener.mediainfo_link = async_to_sync(
                    gen_mediainfo, None, media_path=self._path, silent=True
                )

                # Check if MediaInfo was successfully generated
                if (
                    self.listener.mediainfo_link
                    and self.listener.mediainfo_link.strip()
                ):
                    LOGGER.info(f"Generated MediaInfo for mirror file: {self._path}")
                else:
                    # Set mediainfo_link to None if it's empty or None
                    self.listener.mediainfo_link = None
                    LOGGER.info(
                        "MediaInfo generation skipped or failed for mirror task. Proceeding with upload..."
                    )
            except Exception as e:
                # Set mediainfo_link to None on error
                self.listener.mediainfo_link = None
                LOGGER.error(f"Error generating MediaInfo for mirror task: {e}")

        try:
            if ospath.isfile(self._path):
                mime_type = get_mime_type(self._path)
                link = self._upload_file(
                    self._path,
                    self.listener.name,
                    mime_type,
                    self.listener.up_dest,
                    in_dir=False,
                )
                if self.listener.is_cancelled:
                    return
                if link is None:
                    raise ValueError("Upload has been manually cancelled")
                LOGGER.info(f"Uploaded To G-Drive: {self._path}")
            else:
                mime_type = "Folder"
                dir_id = self.create_directory(
                    ospath.basename(ospath.abspath(self.listener.name)),
                    self.listener.up_dest,
                )
                result = self._upload_dir(
                    self._path,
                    dir_id,
                )
                if result is None:
                    raise ValueError("Upload has been manually cancelled!")
                link = self.G_DRIVE_DIR_BASE_DOWNLOAD_URL.format(dir_id)
                if self.listener.is_cancelled:
                    return
                LOGGER.info(f"Uploaded To G-Drive: {self.listener.name}")
        except Exception as err:
            if isinstance(err, RetryError):
                LOGGER.info(f"Total Attempts: {err.last_attempt.attempt_number}")
                err = err.last_attempt.exception()
            err = str(err).replace(">", "").replace("<", "")
            LOGGER.error(err)
            async_to_sync(self.listener.on_upload_error, err)
            self._is_errored = True
        finally:
            self._updater.cancel()

        if self.listener.is_cancelled and not self._is_errored:
            if mime_type == "Folder" and dir_id:
                LOGGER.info("Deleting uploaded data from Drive...")
                self.service.files().delete(
                    fileId=dir_id,
                    supportsAllDrives=True,
                ).execute()
            return
        if self._is_errored:
            return
        async_to_sync(
            self.listener.on_upload_complete,
            link,
            self.total_files,
            self.total_folders,
            mime_type,
            dir_id=self.get_id_from_url(link) if link else None,
        )
        return

    def _upload_dir(self, input_directory, dest_id):
        list_dirs = listdir(input_directory)
        if len(list_dirs) == 0:
            return dest_id
        new_id = None
        for item in list_dirs:
            current_file_name = ospath.join(input_directory, item)
            if ospath.isdir(current_file_name):
                current_dir_id = self.create_directory(item, dest_id)
                new_id = self._upload_dir(
                    current_file_name,
                    current_dir_id,
                )
                self.total_folders += 1
            else:
                mime_type = get_mime_type(current_file_name)
                file_name = current_file_name.split("/")[-1]
                self._upload_file(
                    current_file_name,
                    file_name,
                    mime_type,
                    dest_id,
                )
                self.total_files += 1
                new_id = dest_id
            if self.listener.is_cancelled:
                break
        return new_id

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=30),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(Exception),
    )
    def _upload_file(
        self,
        file_path,
        file_name,
        mime_type,
        dest_id,
        in_dir=True,
    ):
        file_metadata = {
            "name": file_name,
            "description": "Uploaded by Mirror-leech-telegram-bot",
            "mimeType": mime_type,
        }
        if dest_id is not None:
            file_metadata["parents"] = [dest_id]

        if ospath.getsize(file_path) == 0:
            media_body = MediaFileUpload(
                file_path,
                mimetype=mime_type,
                resumable=False,
            )
            response = (
                self.service.files()
                .create(
                    body=file_metadata,
                    media_body=media_body,
                    supportsAllDrives=True,
                )
                .execute()
            )
            if not Config.IS_TEAM_DRIVE:
                self.set_permission(response["id"])

            drive_file = (
                self.service.files()
                .get(fileId=response["id"], supportsAllDrives=True)
                .execute()
            )
            return self.G_DRIVE_BASE_DOWNLOAD_URL.format(drive_file.get("id"))
        media_body = MediaFileUpload(
            file_path,
            mimetype=mime_type,
            resumable=True,
            chunksize=100 * 1024 * 1024,
        )

        drive_file = self.service.files().create(
            body=file_metadata,
            media_body=media_body,
            supportsAllDrives=True,
        )
        response = None
        retries = 0
        while response is None and not self.listener.is_cancelled:
            try:
                self.status, response = drive_file.next_chunk()
            except HttpError as err:
                if err.resp.status in [500, 502, 503, 504, 429] and retries < 10:
                    retries += 1
                    # Add exponential backoff for server errors
                    sleep_time = 2**retries
                    LOGGER.info(f"Server error, retrying in {sleep_time} seconds...")
                    sleep(sleep_time)
                    continue
                if err.resp.get("content-type", "").startswith("application/json"):
                    reason = (
                        eval(err.content).get("error").get("errors")[0].get("reason")
                    )
                    if reason not in [
                        "userRateLimitExceeded",
                        "dailyLimitExceeded",
                        "storageQuotaExceeded",
                    ]:
                        raise err

                    # Handle storage quota exceeded errors
                    if reason == "storageQuotaExceeded":
                        LOGGER.warning(
                            "Storage quota exceeded for current service account"
                        )
                        if self.use_sa:
                            if self.sa_count >= self.sa_number:
                                LOGGER.error(
                                    f"All {self.sa_number} service accounts have exceeded storage quota"
                                )
                                raise Exception(
                                    "❌ All Google Drive service accounts have exceeded their storage quota. "
                                    "Please free up space or add more service accounts with available storage."
                                )
                            if self.listener.is_cancelled:
                                return None

                            # Switch to next service account for storage quota issues
                            self.switch_service_account()
                            LOGGER.info(
                                "Switched to next service account due to storage quota exceeded"
                            )
                            return self._upload_file(
                                file_path,
                                file_name,
                                mime_type,
                                dest_id,
                                in_dir,
                            )
                        raise Exception(
                            "❌ Google Drive storage quota exceeded. "
                            "Please free up space in your Google Drive or enable service accounts."
                        )

                    # Handle rate limit errors with better backoff strategy
                    if self.use_sa:
                        if self.sa_count >= self.sa_number:
                            LOGGER.info(
                                f"Reached maximum number of service accounts switching, which is {self.sa_count}",
                            )
                            # Add a longer sleep before giving up
                            LOGGER.info(
                                "Sleeping for 60 seconds before final retry...",
                            )
                            sleep(60)
                            raise err
                        if self.listener.is_cancelled:
                            return None

                        # Switch service account and add a delay
                        self.switch_service_account()
                        LOGGER.info(
                            f"Switched service account due to {reason}, waiting 10 seconds before retrying...",
                        )
                        sleep(10)
                        return self._upload_file(
                            file_path,
                            file_name,
                            mime_type,
                            dest_id,
                            in_dir,
                        )
                    # If not using service accounts, add a longer sleep
                    sleep(30)
                    # Try again with the same account after sleeping
                    return self._upload_file(
                        file_path,
                        file_name,
                        mime_type,
                        dest_id,
                        in_dir,
                    )
        if self.listener.is_cancelled:
            return None
        with contextlib.suppress(Exception):
            remove(file_path)
        self.file_processed_bytes = 0
        if not Config.IS_TEAM_DRIVE:
            self.set_permission(response["id"])
        if not in_dir:
            drive_file = (
                self.service.files()
                .get(fileId=response["id"], supportsAllDrives=True)
                .execute()
            )
            return self.G_DRIVE_BASE_DOWNLOAD_URL.format(drive_file.get("id"))
        return None
