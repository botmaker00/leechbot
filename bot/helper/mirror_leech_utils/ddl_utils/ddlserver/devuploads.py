#!/usr/bin/env python3

import re
from pathlib import Path
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout

from bot import LOGGER, user_data
from bot.core.config_manager import Config


class DevUploads:
    def __init__(self, dluploader, api_key):
        self.dluploader = dluploader
        self.api_key = api_key
        self.base_url = "https://devuploads.com"
        self.upload_server = None
        self.session_id = None

    async def upload(self, file_path):
        """Upload file to DevUploads using the proper two-step process"""
        try:
            LOGGER.info("DevUploads: Validating API key")
            if not self.api_key:
                raise Exception("DevUploads API key is required")

            # Step 1: Validate API key and get account info
            account_info = await self.get_account_info()
            if not account_info:
                raise Exception("Invalid DevUploads API key")

            # Check storage limits and premium status
            storage_left = account_info.get("storage_left", 0)
            storage_left_mb = storage_left / (1024 * 1024) if storage_left else 0
            premium_expire = account_info.get("premium_expire", "")

            LOGGER.info(
                f"DevUploads: Account validated - {account_info.get('email', 'Unknown')}"
            )
            LOGGER.info(f"DevUploads: Available storage: {storage_left_mb:.2f} MB")
            LOGGER.info(f"DevUploads: Premium expires: {premium_expire}")

            # Check premium status
            if premium_expire:
                from datetime import datetime

                try:
                    expire_date = datetime.strptime(
                        premium_expire, "%Y-%m-%d %H:%M:%S"
                    )
                    current_date = datetime.now()
                    if expire_date <= current_date:
                        expired_for = current_date - expire_date
                        raise Exception(
                            f"DevUploads premium account expired {expired_for} ago on {premium_expire}. "
                            f"Free accounts have very limited upload capacity (0.0001 MB = ~100 bytes). "
                            f"Solutions: 1) Renew premium subscription, 2) Use different API key, "
                            f"3) Use alternative DDL servers (Gofile, Streamtape, etc.)"
                        )
                    LOGGER.info(
                        f"DevUploads: Premium account active until {premium_expire}"
                    )
                except ValueError:
                    LOGGER.warning(
                        f"DevUploads: Could not parse premium expiry date: {premium_expire}"
                    )

            # Check if account has sufficient storage
            if storage_left_mb < 1:  # Less than 1 MB available
                raise Exception(
                    f"Insufficient storage space. Available: {storage_left_mb:.2f} MB"
                )
            LOGGER.info(f"DevUploads: Starting upload for path: {file_path}")

            if await self._is_file(file_path):
                LOGGER.info(f"DevUploads: Uploading file: {file_path}")
                upload_result = await self.upload_file(file_path)

                if not upload_result:
                    raise Exception(
                        "Upload failed: No response data from DevUploads API"
                    )

                download_link = upload_result.get("download_url")
                if not download_link:
                    LOGGER.error(
                        f"DevUploads: No download_url in response: {upload_result}"
                    )
                    raise Exception("Upload failed: No download URL in response")

                LOGGER.info(f"DevUploads: File upload successful: {download_link}")
                return download_link
            raise Exception("DevUploads only supports single file uploads")

        except Exception as e:
            LOGGER.error(f"DevUploads upload error: {e}")
            raise e

    async def _is_file(self, path):
        """Check if path is a file"""
        from bot.helper.ext_utils.aiofiles_compat import aiopath

        return await aiopath.isfile(path)

    async def get_account_info(self):
        """Get account information to validate API key"""
        try:
            params = {"key": self.api_key}
            url = f"{self.base_url}/api/account/info?" + urlencode(params)

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("status") == 200 and result.get("msg") == "OK":
                            return result.get("result", {})
                    return None
        except Exception as e:
            LOGGER.error(f"DevUploads: Failed to get account info: {e}")
            return None

    async def get_upload_server(self):
        """Get upload server URL and session ID"""
        try:
            params = {"key": self.api_key}
            url = f"{self.base_url}/api/upload/server?" + urlencode(params)

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("status") == 200 and result.get("msg") == "OK":
                            upload_url = result.get("result")
                            sess_id = result.get("sess_id")
                            if upload_url and sess_id:
                                self.upload_server = upload_url
                                self.session_id = sess_id
                                LOGGER.info(
                                    f"DevUploads: Got upload server: {upload_url}"
                                )
                                LOGGER.info(f"DevUploads: Got session ID: {sess_id}")
                                return upload_url
                            LOGGER.error(
                                f"DevUploads: Missing upload_url or sess_id in response: {result}"
                            )
                            return None
                    return None
        except Exception as e:
            LOGGER.error(f"DevUploads: Failed to get upload server: {e}")
            return None

    async def upload_file(self, file_path):
        """Upload file to DevUploads with user settings integration"""
        file_name = Path(file_path).name

        # Get user settings with fallback to owner settings
        user_id = (
            self.dluploader._DDLUploader__user_id
            if hasattr(self.dluploader, "_DDLUploader__user_id")
            else None
        )
        user_dict = user_data.get(user_id, {}) if user_id else {}

        def get_devuploads_setting(user_key, owner_attr, default_value=None):
            user_value = user_dict.get(user_key)
            if user_value is not None:
                return user_value
            return getattr(Config, owner_attr, default_value)

        # Get DevUploads settings
        folder_name = get_devuploads_setting(
            "DEVUPLOADS_FOLDER_NAME", "DEVUPLOADS_FOLDER_NAME", ""
        )
        public_file = get_devuploads_setting(
            "DEVUPLOADS_PUBLIC_FILES", "DEVUPLOADS_PUBLIC_FILES", True
        )

        # Step 1: Get upload server
        upload_server = await self.get_upload_server()
        if not upload_server:
            raise Exception("Failed to get DevUploads upload server")

        # Step 2: Handle folder creation if needed
        folder_id = None
        if folder_name:
            folder_id = await self.create_folder(folder_name)

        if self.dluploader.is_cancelled:
            return None

        self.dluploader.last_uploaded = 0

        # Step 3: Upload file to the upload server
        uploaded = await self._upload_to_server(
            upload_server, file_path, folder_id, public_file
        )

        if uploaded is None:
            return None

        if self.dluploader.is_cancelled:
            return None

        # Parse response and return download URL
        return self._parse_upload_response(uploaded, file_name)

    async def _upload_to_server(
        self, upload_server, file_path, folder_id=None, public_file=True
    ):
        """Upload file to the DevUploads server"""
        try:
            # Use the existing upload_aiohttp method from DDLUploader
            # Start with minimal data as per API documentation
            data = {}
            if self.session_id:
                data["sess_id"] = self.session_id
            else:
                raise Exception("No session ID available for upload")

            # Add optional parameters only if they are supported
            # Note: Adding folder ID and public setting - these might cause issues
            # if the API doesn't support them in the upload endpoint
            if folder_id:
                data["fld_id"] = str(folder_id)
                LOGGER.info(f"DevUploads: Adding folder ID: {folder_id}")

            # Add public/private setting - this might not be supported in upload
            # data["public"] = "1" if public_file else "0"
            # LOGGER.info(f"DevUploads: Setting public: {public_file}")

            # For now, let's try without the public parameter to see if that's causing the issue

            # Upload using the DDLUploader's method
            LOGGER.info(f"DevUploads: Uploading to server: {upload_server}")
            LOGGER.info(f"DevUploads: Upload data: {data}")

            uploaded = await self.dluploader.upload_aiohttp(
                upload_server, file_path, "file", data
            )

            LOGGER.info(f"DevUploads: Upload response: {uploaded}")
            return uploaded

        except Exception as e:
            LOGGER.error(f"DevUploads: Upload to server failed: {e}")
            raise e

    def _parse_upload_response(self, response, file_name):
        """Parse upload response and extract download URL"""
        try:
            if isinstance(response, dict):
                # Check for various response formats
                if response.get("status") == 200 and response.get("msg") == "OK":
                    result = response.get("result", {})
                    if isinstance(result, dict):
                        file_code = result.get("filecode")
                        if file_code:
                            download_url = f"https://devuploads.com/{file_code}"
                            return {
                                "download_url": download_url,
                                "file_code": file_code,
                                "file_name": file_name,
                            }

                # Handle other response formats
                if "response" in response:
                    # Parse HTML response for file code
                    html_response = response["response"]
                    # Look for DevUploads file URLs in the response
                    file_code_match = re.search(
                        r"devuploads\.com/([a-zA-Z0-9]+)", html_response
                    )
                    if file_code_match:
                        file_code = file_code_match.group(1)
                        download_url = f"https://devuploads.com/{file_code}"
                        return {
                            "download_url": download_url,
                            "file_code": file_code,
                            "file_name": file_name,
                        }

            # Handle string response
            if isinstance(response, str):
                file_code_match = re.search(
                    r"devuploads\.com/([a-zA-Z0-9]+)", response
                )
                if file_code_match:
                    file_code = file_code_match.group(1)
                    download_url = f"https://devuploads.com/{file_code}"
                    return {
                        "download_url": download_url,
                        "file_code": file_code,
                        "file_name": file_name,
                    }

            raise Exception("Could not parse upload response")

        except Exception as e:
            LOGGER.error(f"DevUploads: Failed to parse upload response: {e}")
            raise e

    async def create_folder(self, folder_name):
        """Create folder in DevUploads"""
        try:
            params = {"key": self.api_key, "name": folder_name}
            url = f"{self.base_url}/api/folder/create?" + urlencode(params)

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("status") == 200 and result.get("msg") == "OK":
                            folder_info = result.get("result", {})
                            return folder_info.get("fld_id")
                    return None
        except Exception as e:
            LOGGER.warning(f"DevUploads: Failed to create folder: {e}")
            return None

    async def list_folders(self):
        """List all folders in DevUploads account"""
        try:
            params = {"key": self.api_key}
            url = f"{self.base_url}/api/folder/list?" + urlencode(params)

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("status") == 200 and result.get("msg") == "OK":
                            return result.get("result", [])
                    return []
        except Exception as e:
            LOGGER.error(f"DevUploads: Failed to list folders: {e}")
            return []

    async def get_account_stats(self):
        """Get account statistics"""
        try:
            params = {"key": self.api_key}
            url = f"{self.base_url}/api/account/stats?" + urlencode(params)

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("status") == 200 and result.get("msg") == "OK":
                            return result.get("result", {})
                    return {}
        except Exception as e:
            LOGGER.error(f"DevUploads: Failed to get account stats: {e}")
            return {}

    async def get_file_info(self, file_code):
        """Get file information by file code"""
        try:
            params = {"key": self.api_key, "file_code": file_code}
            url = f"{self.base_url}/api/file/info?" + urlencode(params)

            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("status") == 200 and result.get("msg") == "OK":
                            return result.get("result", {})
                    return {}
        except Exception as e:
            LOGGER.error(f"DevUploads: Failed to get file info: {e}")
            return {}
