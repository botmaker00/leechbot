#!/usr/bin/env python3
from pathlib import Path

from aiofiles.os import path as aiopath
from aiofiles.os import scandir
from aiohttp import ClientSession

from bot import LOGGER, user_data
from bot.core.config_manager import Config
from bot.helper.ext_utils.telegraph_helper import telegraph

# Use extensions from config to maintain consistency
ALLOWED_EXTS = Config.STREAMTAPE_ALLOWED_EXTENSIONS


class Streamtape:
    def __init__(self, dluploader, api_username, api_password):
        self.__api_username = api_username
        self.__api_password = api_password
        self.dluploader = dluploader
        self.base_url = "https://api.streamtape.com"

    async def get_account_info(self):
        """Get account information - useful for debugging/validation"""
        try:
            async with (
                ClientSession() as session,
                session.get(
                    f"{self.base_url}/account/info?login={self.__api_username}&key={self.__api_password}"
                ) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == 200:
                        return data["result"]
                    error_msg = data.get("msg", "Unknown error")
                    if "login failed" in error_msg.lower():
                        LOGGER.error(
                            f"Streamtape: Invalid login credentials - {error_msg}"
                        )
                    elif "invalid" in error_msg.lower():
                        LOGGER.error(f"Streamtape: Invalid API key - {error_msg}")
                    else:
                        LOGGER.error(f"Streamtape account info error: {error_msg}")
                    return None
                LOGGER.error(
                    f"Streamtape account info HTTP error: {response.status}"
                )
                return None
        except Exception as e:
            LOGGER.error(f"Streamtape account info exception: {e}")
            return None

    async def __getUploadURL(self, folder=None, sha256=None, httponly=False):
        _url = f"{self.base_url}/file/ul?login={self.__api_username}&key={self.__api_password}"
        if folder is not None:
            _url += f"&folder={folder}"
        if sha256 is not None:
            _url += f"&sha256={sha256}"
        if httponly:
            _url += "&httponly=true"

        try:
            async with ClientSession() as session, session.get(_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == 200:
                        result = data.get("result")
                        if not result or "url" not in result:
                            raise Exception(
                                "Invalid API response: missing upload URL"
                            )
                        return result
                    error_msg = data.get("msg", "Unknown API error")
                    raise Exception(f"Streamtape API error: {error_msg}")
                raise Exception(f"HTTP {response.status}: Failed to get upload URL")
        except Exception as e:
            raise Exception(f"Failed to get upload URL: {e}") from e

    async def upload_file(
        self, file_path, folder_id=None, sha256=None, httponly=False
    ):
        """Upload file to Streamtape with user settings integration"""
        if Path(file_path).suffix.lower() not in ALLOWED_EXTS:
            LOGGER.warning(
                f"Streamtape: Skipping '{file_path}' due to disallowed extension"
            )
            return f"Skipping '{file_path}' due to disallowed extension."

        file_name = Path(file_path).name

        # Get user settings with fallback to owner settings
        user_id = (
            self.dluploader._DDLUploader__user_id
            if hasattr(self.dluploader, "_DDLUploader__user_id")
            else None
        )
        user_dict = user_data.get(user_id, {}) if user_id else {}

        def get_streamtape_setting(user_key, owner_attr, default_value=None):
            user_value = user_dict.get(user_key)
            if user_value is not None:
                return user_value
            return getattr(Config, owner_attr, default_value)

        if not folder_id:
            # Use user-specified folder name or create folder based on filename
            folder_name = get_streamtape_setting(
                "STREAMTAPE_FOLDER_NAME", "STREAMTAPE_FOLDER_NAME", ""
            )
            if not folder_name:
                folder_name = file_name.rsplit(".", 1)[
                    0
                ]  # Use filename without extension

            genfolder = await self.create_folder(folder_name)
            if genfolder is None:
                return None
            folder_id = genfolder["folderid"]

        upload_info = await self.__getUploadURL(
            folder=folder_id, sha256=sha256, httponly=httponly
        )
        if upload_info is None:
            LOGGER.error("Streamtape: Failed to get upload URL")
            return None

        if self.dluploader.is_cancelled:
            return None
        self.dluploader.last_uploaded = 0
        uploaded = await self.dluploader.upload_aiohttp(
            upload_info["url"], file_path, file_name, {}
        )
        if uploaded:
            # Get the most recently uploaded file by finding the file with matching name
            # or the newest file if name matching fails
            folder_contents = await self.list_folder(folder=folder_id)
            if not folder_contents or not folder_contents.get("files"):
                return None

            # Try to find file by name first (more reliable)
            target_file = None
            for file_info in folder_contents["files"]:
                if file_info.get("name") == file_name:
                    target_file = file_info
                    break

            # Fallback: get the most recent file (last in list)
            if not target_file:
                target_file = folder_contents["files"][-1]

            file_id = target_file["linkid"]

            # Rename file to ensure correct name
            await self.rename(file_id, file_name)
            return f"https://streamtape.to/v/{file_id}"
        return None

    async def create_folder(self, name, parent=None):
        exfolders = [
            folder["name"]
            for folder in (await self.list_folder(folder=parent) or {"folders": []})[
                "folders"
            ]
        ]
        if name in exfolders:
            i = 1
            while f"{i} {name}" in exfolders:
                i += 1
            name = f"{i} {name}"

        url = f"{self.base_url}/file/createfolder?login={self.__api_username}&key={self.__api_password}&name={name}"
        if parent is not None:
            url += f"&pid={parent}"
        async with ClientSession() as session, session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("status") == 200:
                    return data.get("result")
        return None

    async def rename(self, file_id, name):
        url = f"{self.base_url}/file/rename?login={self.__api_username}&key={self.__api_password}&file={file_id}&name={name}"
        try:
            async with ClientSession() as session, session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == 200:
                        return data.get("result")
                    error_msg = data.get("msg", "Unknown error")
                    raise Exception(f"Rename failed: {error_msg}")
                raise Exception(f"HTTP {response.status}: Failed to rename file")
        except Exception as e:
            # Log error but don't fail upload for rename issues
            LOGGER.warning(f"Failed to rename file {file_id}: {e}")
        return None

    async def get_file_info(self, file_id):
        """Get file information (if endpoint exists)"""
        url = f"{self.base_url}/file/info?login={self.__api_username}&key={self.__api_password}&file={file_id}"
        try:
            async with ClientSession() as session, session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == 200:
                        return data.get("result")
        except Exception:
            pass  # Endpoint might not exist
        return None

    async def delete_file(self, file_id):
        """Delete file (if endpoint exists)"""
        url = f"{self.base_url}/file/delete?login={self.__api_username}&key={self.__api_password}&file={file_id}"
        try:
            async with ClientSession() as session, session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == 200:
                        return data.get("result")
        except Exception:
            pass  # Endpoint might not exist
        return None

    async def list_telegraph(self, folder_id, nested=False):
        tg_html = ""
        contents = await self.list_folder(folder_id)
        for fid in contents["folders"]:
            tg_html += f"<aside>╾──────────────────────╼</aside><br><aside><b>🗂 {fid['name']}</b></aside><br><aside>╾──────────────────────╼</aside><br>"
            tg_html += await self.list_telegraph(fid["id"], True)
        tg_html += "<ol>"
        for finfo in contents["files"]:
            tg_html += f"""<li> <code>{finfo["name"]}</code><br>🔗 <a href="https://streamtape.to/v/{finfo["linkid"]}">StreamTape URL</a><br> </li>"""
        tg_html += "</ol>"
        if nested:
            return tg_html
        # Add telegraph page content without cover image
        path = (await telegraph.create_page(title="StreamTape X", content=tg_html))[
            "path"
        ]
        return f"https://te.legra.ph/{path}"

    async def list_folder(self, folder=None):
        url = f"{self.base_url}/file/listfolder?login={self.__api_username}&key={self.__api_password}"
        if folder is not None:
            url += f"&folder={folder}"
        async with ClientSession() as session, session.get(url) as response:
            if (
                response.status == 200
                and (data := await response.json())
                and data["status"] == 200
            ):
                return data["result"]
        return None

    async def upload_folder(self, folder_path, parent_folder_id=None):
        folder_name = Path(folder_path).name
        genfolder = await self.create_folder(
            name=folder_name, parent=parent_folder_id
        )

        if genfolder and (newfid := genfolder.get("folderid")):
            for entry in await scandir(folder_path):
                if entry.is_file():
                    await self.upload_file(entry.path, newfid)
                    self.dluploader.total_files += 1
                elif entry.is_dir():
                    await self.upload_folder(entry.path, newfid)
                    self.dluploader.total_folders += 1
            return await self.list_telegraph(newfid)
        return None

    async def upload(self, file_path):
        stlink = None
        if await aiopath.isfile(file_path):
            stlink = await self.upload_file(file_path)
        elif await aiopath.isdir(file_path):
            stlink = await self.upload_folder(file_path)
        if stlink:
            return stlink
        if self.dluploader.is_cancelled:
            return None
        raise Exception(
            "Failed to upload file/folder to StreamTape API, Retry! or Try after sometimes..."
        )
