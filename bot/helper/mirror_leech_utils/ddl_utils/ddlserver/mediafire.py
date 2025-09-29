#!/usr/bin/env python3
import asyncio
import hashlib
from os import path as ospath
from pathlib import Path

from aiofiles.os import path as aiopath
from aiohttp import ClientSession, ClientTimeout

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import sync_to_async


class MediaFire:
    def __init__(self, dluploader=None):
        self.api_url = "https://www.mediafire.com/api/1.5/"
        self.dluploader = dluploader
        self.session_token = None
        self.folder_key = None

    @staticmethod
    async def is_mediafire_api(email, password, app_id):
        """Validate MediaFire API credentials."""
        if not email or not password or not app_id:
            LOGGER.info(
                "MediaFire: Missing required credentials (email, password, app_id)"
            )
            return False

        try:
            mediafire = MediaFire()
            session_token = await mediafire._get_session_token(
                email, password, app_id
            )
            if session_token:
                LOGGER.info("MediaFire: API credentials validation successful")
                return True
            LOGGER.error("MediaFire: API credentials validation failed")
            return False
        except Exception as e:
            LOGGER.error(f"MediaFire: API validation error - {e!s}")
            return False

    async def _get_session_token(self, email, password, app_id, api_key=""):
        """Get MediaFire session token using email/password authentication."""
        try:
            # Create signature for authentication
            signature_string = f"{email}{password}{app_id}{api_key}"
            signature = hashlib.sha1(signature_string.encode()).hexdigest()

            # Request session token
            auth_url = f"{self.api_url}user/get_session_token.php"
            auth_data = {
                "email": email,
                "password": password,
                "application_id": app_id,
                "signature": signature,
                "response_format": "json",
            }

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.post(auth_url, data=auth_data) as resp:
                    if resp.status != 200:
                        LOGGER.error(
                            f"MediaFire: Authentication failed with HTTP {resp.status}"
                        )
                        return None

                    result = await resp.json()
                    if result.get("response", {}).get("result") == "Success":
                        return result["response"]["session_token"]
                    error_msg = result.get("response", {}).get(
                        "message", "Unknown error"
                    )
                    LOGGER.error(f"MediaFire: Authentication failed: {error_msg}")
                    return None

        except Exception as e:
            LOGGER.error(f"MediaFire: Session token error - {e}")
            return None

    async def _get_or_create_folder(self, folder_name):
        """Get or create a folder in MediaFire."""
        if not folder_name:
            return "myfiles"  # Root folder

        try:
            # First, try to find existing folder
            search_url = f"{self.api_url}folder/search.php"
            search_params = {
                "session_token": self.session_token,
                "search_text": folder_name,
                "response_format": "json",
            }

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(search_url, params=search_params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("response", {}).get("result") == "Success":
                            folders = (
                                result.get("response", {})
                                .get("folder_results", {})
                                .get("folders", [])
                            )
                            for folder in folders:
                                if folder.get("name") == folder_name:
                                    return folder.get("folderkey")

                # If folder not found, create it
                create_url = f"{self.api_url}folder/create.php"
                create_data = {
                    "session_token": self.session_token,
                    "foldername": folder_name,
                    "parent_key": "myfiles",
                    "response_format": "json",
                }

                async with session.post(create_url, data=create_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("response", {}).get("result") == "Success":
                            return result["response"]["folder_key"]

            return "myfiles"  # Fallback to root folder

        except Exception as e:
            LOGGER.error(f"MediaFire: Folder creation error - {e}")
            return "myfiles"

    async def _check_instant_upload(self, file_path, filename):
        """Check if file can be uploaded instantly (already exists in cloud)."""
        try:
            # Calculate file hash
            file_hash = await self._calculate_file_hash(file_path)
            file_size = Path(file_path).stat().st_size

            check_url = f"{self.api_url}upload/check.php"
            check_params = {
                "session_token": self.session_token,
                "filename": filename,
                "hash": file_hash,
                "size": str(file_size),
                "folder_key": self.folder_key,
                "response_format": "json",
            }

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(check_url, params=check_params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("response", {}).get("result") == "Success":
                            if (
                                result.get("response", {}).get("hash_exists")
                                == "yes"
                            ):
                                # Perform instant upload
                                return await self._instant_upload(
                                    file_hash, file_size, filename
                                )

            return None

        except Exception as e:
            LOGGER.error(f"MediaFire: Instant upload check error - {e}")
            return None

    async def _instant_upload(self, file_hash, file_size, filename):
        """Perform instant upload for files that already exist in cloud."""
        try:
            instant_url = f"{self.api_url}upload/instant.php"
            instant_data = {
                "session_token": self.session_token,
                "hash": file_hash,
                "size": str(file_size),
                "filename": filename,
                "folder_key": self.folder_key,
                "response_format": "json",
            }

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.post(instant_url, data=instant_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("response", {}).get("result") == "Success":
                            quickkey = result["response"]["quickkey"]
                            return await self._get_file_link(quickkey)

            return None

        except Exception as e:
            LOGGER.error(f"MediaFire: Instant upload error - {e}")
            return None

    async def _calculate_file_hash(self, file_path):
        """Calculate SHA256 hash of file."""

        def _hash_file():
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()

        return await sync_to_async(_hash_file)

    async def _simple_upload(self, file_path, filename):
        """Upload file using simple upload method."""
        try:
            file_size = Path(file_path).stat().st_size
            file_hash = await self._calculate_file_hash(file_path)

            upload_url = f"{self.api_url}upload/simple.php"
            upload_params = {
                "session_token": self.session_token,
                "folder_key": self.folder_key,
                "response_format": "json",
            }

            # Prepare headers
            headers = {
                "x-filename": filename,
                "x-filesize": str(file_size),
                "x-filehash": file_hash,
            }

            timeout = ClientTimeout(
                total=1800, connect=300
            )  # 30 min total, 5 min connect
            async with ClientSession(timeout=timeout) as session:
                with open(file_path, "rb") as file:
                    async with session.post(
                        upload_url, params=upload_params, headers=headers, data=file
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            if result.get("response", {}).get("result") == "Success":
                                upload_key = result["response"]["doupload"]["key"]
                                return await self._poll_upload(upload_key)

            return None

        except Exception as e:
            LOGGER.error(f"MediaFire: Simple upload error - {e}")
            return None

    async def _poll_upload(self, upload_key):
        """Poll upload status until completion."""
        try:
            poll_url = f"{self.api_url}upload/poll_upload.php"
            poll_params = {
                "session_token": self.session_token,
                "key": upload_key,
                "response_format": "json",
            }

            timeout = ClientTimeout(total=30, connect=10)
            max_attempts = 120  # 10 minutes with 5-second intervals for large files
            attempt = 0

            async with ClientSession(timeout=timeout) as session:
                while attempt < max_attempts:
                    async with session.get(poll_url, params=poll_params) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            if result.get("response", {}).get("result") == "Success":
                                doupload = result["response"]["doupload"]

                                # Check for quickkey (upload completed)
                                if "quickkey" in doupload:
                                    quickkey = doupload["quickkey"]
                                    return await self._get_file_link(quickkey)

                                # Check upload status
                                upload_result = doupload.get("result")
                                if upload_result == "0":
                                    # Upload completed successfully, but no quickkey yet
                                    await asyncio.sleep(5)
                                    attempt += 1
                                    continue
                                if upload_result in [
                                    "-40",
                                    "-41",
                                    "-42",
                                    "-43",
                                    "-44",
                                    "-45",
                                    "-46",
                                    "-47",
                                    "-48",
                                    "-49",
                                    "-51",
                                ]:
                                    # Upload failed with specific error
                                    error_desc = doupload.get(
                                        "description",
                                        f"Upload failed with error code {upload_result}",
                                    )
                                    LOGGER.error(
                                        f"MediaFire: Upload failed - {error_desc}"
                                    )
                                    return None
                                # Upload still in progress
                                status_desc = doupload.get(
                                    "description", "Upload in progress"
                                )
                                LOGGER.info(f"MediaFire: {status_desc}")
                                await asyncio.sleep(5)
                                attempt += 1
                                continue
                            # API call failed
                            error_msg = result.get("response", {}).get(
                                "message", "Unknown API error"
                            )
                            LOGGER.error(
                                f"MediaFire: Poll upload API error - {error_msg}"
                            )
                            return None
                        LOGGER.error(
                            f"MediaFire: Poll upload HTTP error - {resp.status}"
                        )
                        await asyncio.sleep(5)
                        attempt += 1
                        continue

                    await asyncio.sleep(5)
                    attempt += 1

            LOGGER.error(
                "MediaFire: Upload polling timeout - upload may still be processing"
            )
            return None

        except Exception as e:
            LOGGER.error(f"MediaFire: Poll upload error - {e}")
            return None

    async def _get_file_link(self, quickkey):
        """Get public download link for uploaded file."""
        try:
            links_url = f"{self.api_url}file/get_links.php"
            links_params = {
                "session_token": self.session_token,
                "quick_key": quickkey,
                "link_type": "view",
                "response_format": "json",
            }

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(links_url, params=links_params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("response", {}).get("result") == "Success":
                            links = result["response"]["links"]
                            if links and len(links) > 0:
                                return links[0]["view"]

            return None

        except Exception as e:
            LOGGER.error(f"MediaFire: Get file link error - {e}")
            return None

    async def _get_upload_limits(self):
        """Get MediaFire upload limits from system API."""
        try:
            limits_url = f"{self.api_url}system/get_limits.php"
            limits_params = {"response_format": "json"}

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(limits_url, params=limits_params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("response", {}).get("result") == "Success":
                            limits = result["response"]["limits"]
                            return {
                                "max_total_filesize": int(
                                    limits.get("max_total_filesize", 53687091300)
                                ),  # ~50GB
                                "max_chunk_filesize": int(
                                    limits.get("max_chunk_filesize", 21474836580)
                                ),  # ~20GB
                                "max_image_size": int(
                                    limits.get("max_image_size", 26214400)
                                ),  # 25MB
                            }

            # Return default limits if API call fails
            return {
                "max_total_filesize": 53687091300,  # ~50GB
                "max_chunk_filesize": 21474836580,  # ~20GB
                "max_image_size": 26214400,  # 25MB
            }

        except Exception as e:
            LOGGER.error(f"MediaFire: Get upload limits error - {e}")
            # Return default limits
            return {
                "max_total_filesize": 53687091300,  # ~50GB
                "max_chunk_filesize": 21474836580,  # ~20GB
                "max_image_size": 26214400,  # 25MB
            }

    async def upload(self, file_path):
        """Main upload method for MediaFire."""
        try:
            # Get user settings with fallback to owner settings
            from bot import user_data

            user_id = (
                self.dluploader._DDLUploader__user_id
                if hasattr(self.dluploader, "_DDLUploader__user_id")
                else None
            )
            user_dict = user_data.get(user_id, {}) if user_id else {}

            def get_mediafire_setting(user_key, owner_attr, default_value=None):
                user_value = user_dict.get(user_key)
                if user_value is not None:
                    return user_value
                return getattr(Config, owner_attr, default_value)

            # Get MediaFire credentials with user priority
            email = get_mediafire_setting("MEDIAFIRE_EMAIL", "MEDIAFIRE_EMAIL", "")
            password = get_mediafire_setting(
                "MEDIAFIRE_PASSWORD", "MEDIAFIRE_PASSWORD", ""
            )
            app_id = get_mediafire_setting(
                "MEDIAFIRE_APP_ID", "MEDIAFIRE_APP_ID", ""
            )
            api_key = get_mediafire_setting(
                "MEDIAFIRE_API_KEY", "MEDIAFIRE_API_KEY", ""
            )

            if not email or not password or not app_id:
                raise Exception(
                    "MediaFire credentials not configured. Please set MEDIAFIRE_EMAIL, MEDIAFIRE_PASSWORD, and MEDIAFIRE_APP_ID."
                )

            # Get session token
            self.session_token = await self._get_session_token(
                email, password, app_id, api_key
            )
            if not self.session_token:
                raise Exception("Failed to authenticate with MediaFire API")

            # Determine file/folder to upload
            if await aiopath.isfile(file_path):
                # Single file upload
                filename = ospath.basename(file_path)
                file_size = Path(file_path).stat().st_size

                # Get MediaFire upload limits
                limits = await self._get_upload_limits()
                max_file_size = limits["max_total_filesize"]

                # Check file size against limits
                if file_size > max_file_size:
                    raise Exception(
                        f"File {filename} ({file_size} bytes) exceeds MediaFire maximum file size limit ({max_file_size} bytes / ~{max_file_size // (1024**3)}GB)"
                    )

                # Set up folder (use bot name or default)
                folder_name = getattr(self.dluploader, "name", None) or "AimLeechBot"
                self.folder_key = await self._get_or_create_folder(folder_name)

                LOGGER.info(
                    f"MediaFire: Uploading file {filename} ({file_size} bytes)"
                )

                # Try instant upload first
                instant_link = await self._check_instant_upload(file_path, filename)
                if instant_link:
                    LOGGER.info(
                        f"MediaFire: Instant upload successful for {filename}"
                    )
                    return instant_link

                # Fall back to simple upload
                # MediaFire supports large files via simple upload (up to ~50GB)
                upload_link = await self._simple_upload(file_path, filename)
                if upload_link:
                    LOGGER.info(
                        f"MediaFire: Simple upload successful for {filename}"
                    )
                    return upload_link

                raise Exception(f"Failed to upload {filename}")

            if await aiopath.isdir(file_path):
                # Directory upload - not supported in this version
                raise Exception(
                    "Directory upload not supported. Please upload individual files."
                )

            raise Exception(f"Path {file_path} does not exist")

        except Exception as e:
            LOGGER.error(f"MediaFire: Upload failed - {e}")
            raise Exception(f"MediaFire upload error: {e}") from e
