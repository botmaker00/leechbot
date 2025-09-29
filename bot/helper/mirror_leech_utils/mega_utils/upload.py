import asyncio
import os
import subprocess
import time as time_module
from asyncio import Event, create_subprocess_exec
from os import path as ospath
from os import walk
from secrets import token_hex

from aiofiles.os import path as aiopath
from aiofiles.os import remove as aioremove

from bot import LOGGER, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import async_to_sync, sync_to_async
from bot.helper.ext_utils.mega_utils import (
    MegaApi,
    MegaError,
    MegaRequest,
    MegaTransfer,
)
from bot.helper.ext_utils.task_manager import check_running_tasks
from bot.helper.listeners.mega_listener import AsyncMega, MegaAppListener
from bot.helper.mirror_leech_utils.status_utils.mega_status import MegaUploadStatus
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.telegram_helper.message_utils import (
    send_status_message,
    update_status_message,
)


async def generate_video_thumbnail(video_path):
    """
    Generate thumbnail for video files using FFmpeg.

    Args:
        video_path: Path to the video file

    Returns:
        Path to generated thumbnail or None if failed
    """
    if not Config.MEGA_UPLOAD_THUMBNAIL:
        return None

    try:
        # Check if file is a video
        video_extensions = [
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        ]
        if not any(video_path.lower().endswith(ext) for ext in video_extensions):
            return None

        thumbnail_path = f"{video_path}_thumbnail.jpg"

        # Use FFmpeg to generate thumbnail at 10% of video duration
        cmd = [
            "xtra",  # Using the renamed ffmpeg binary
            "-i",
            video_path,
            "-ss",
            "00:00:10",  # Seek to 10 seconds
            "-vframes",
            "1",  # Extract 1 frame
            "-vf",
            "scale=320:240",  # Resize to 320x240
            "-y",  # Overwrite output file
            thumbnail_path,
        ]

        process = await create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0 and ospath.exists(thumbnail_path):
            return thumbnail_path
        LOGGER.error(f"Failed to generate thumbnail: {stderr.decode()}")
        return None

    except Exception as e:
        LOGGER.error(f"Error generating thumbnail: {e}")
        return None


class MegaUploadListener(MegaAppListener):
    def __init__(self, continue_event: Event, listener):
        super().__init__(continue_event, listener)
        self.upload_node = None
        self.__upload_folder = None
        self.upload_folder_path = None  # Store the upload folder path for display

    @property
    def downloaded_bytes(self):
        # Access parent class's __bytes_transferred through the parent's property
        return super().downloaded_bytes

    async def cancel_task(self):
        self.is_cancelled = True
        await self.listener.on_upload_error("Upload cancelled by user")

    def _generate_mega_path(self):
        """Generate MEGA path for display in completion message"""
        try:
            # Use the stored upload folder path
            if hasattr(self, "upload_folder_path") and self.upload_folder_path:
                # Use the stored folder path
                if hasattr(self.listener, "name") and self.listener.name:
                    mega_path = (
                        f"MEGA:/{self.upload_folder_path}/{self.listener.name}"
                    )
                else:
                    mega_path = f"MEGA:/{self.upload_folder_path}"
                return mega_path
            if hasattr(self.listener, "name") and self.listener.name:
                # Use root folder with file/folder name
                return f"MEGA:/{self.listener.name}"
            # Fallback to generic MEGA path
            return "MEGA:/Cloud Drive"
        except Exception as e:
            LOGGER.error(f"Error generating MEGA path: {e}")
            return "MEGA:/Cloud Drive"

    def onRequestFinish(self, api, request, error):
        # Handle upload-specific request types
        if str(error).lower() == "no error":
            request_type = request.getType()

            if request_type == MegaRequest.TYPE_CREATE_FOLDER:
                self.__upload_folder = request.getNodeHandle()
            elif request_type == MegaRequest.TYPE_EXPORT:
                public_link = request.getLink()
                is_file = hasattr(self.listener, "is_file") and self.listener.is_file
                files_count = 1 if is_file else 0
                folders_count = 0 if is_file else 1
                mime_type = "File" if is_file else "Folder"
                mega_path = self._generate_mega_path()

                async_to_sync(
                    self.listener.on_upload_complete,
                    public_link,
                    files_count,
                    folders_count,
                    mime_type,
                    mega_path,
                )
                self.continue_event.set()
                return

        # Call parent implementation for standard handling
        super().onRequestFinish(api, request, error)

    def onRequestTemporaryError(self, api, request, error: MegaError):
        # Handle temporary errors silently - let MEGA SDK retry automatically
        super().onRequestTemporaryError(api, request, error)

    def onTransferUpdate(self, api: MegaApi, transfer: MegaTransfer):
        if self.is_cancelled:
            api.cancelTransfer(transfer, None)
            self.continue_event.set()
            return
        # Use parent class properties
        super().onTransferUpdate(api, transfer)

    def onTransferFinish(self, api: MegaApi, transfer: MegaTransfer, error):
        try:
            if self.is_cancelled:
                self.continue_event.set()
                return

            if str(error).lower() != "no error":
                async_to_sync(
                    self.listener.on_upload_error,
                    f"MEGA Upload Transfer Error: {error}",
                )
                self.continue_event.set()
                return

            # Handle upload completion
            transfer.getFileName()
            self.upload_node = transfer.getNodeHandle()

            # Check if this is a multi-file upload - if so, don't complete yet
            is_multi_file_upload = getattr(
                self.listener, "is_multi_file_upload", False
            ) or getattr(self.listener, "is_uploading", False)

            if is_multi_file_upload:
                self.continue_event.set()
                return

            # Check if we need to generate public link
            should_generate_link = Config.MEGA_UPLOAD_PUBLIC or getattr(
                self.listener, "is_clone", False
            )

            if should_generate_link and transfer.isFinished():
                node = api.getNodeByHandle(self.upload_node)
                if node:
                    api.exportNode(node)
                    return  # Wait for export to complete

            # Complete upload without public link (single file upload only)
            is_file = hasattr(self.listener, "is_file") and self.listener.is_file
            files_count = 1 if is_file else 0
            folders_count = 0 if is_file else 1
            mime_type = "File" if is_file else "Folder"
            mega_path = self._generate_mega_path()

            async_to_sync(
                self.listener.on_upload_complete,
                None,
                files_count,
                folders_count,
                mime_type,
                mega_path,
            )
            self.continue_event.set()
        except Exception as e:
            LOGGER.error(f"Exception in MEGA upload onTransferFinish: {e}")
            self.continue_event.set()

    def onTransferTemporaryError(self, api, transfer, error):
        if transfer.getState() in [1, 4]:
            return
        if not self.is_cancelled:
            self.is_cancelled = True
            async_to_sync(
                self.listener.on_upload_error,
                f"MEGA Upload Transfer Error: {error.toString()} ({transfer.getFileName()})",
            )
        super().onTransferTemporaryError(api, transfer, error)


def _get_premium_settings(is_premium):
    """Get optimized settings based on account type"""
    if is_premium:
        return {
            "chunk_size": 10485760,  # 10MB chunks for premium
            "parallel_uploads": 6,  # More parallel uploads
            "bandwidth_limit": 0,  # No bandwidth limit
        }
    return {
        "chunk_size": 1048576,  # 1MB chunks for free
        "parallel_uploads": 1,  # Single upload for free
        "bandwidth_limit": 1,  # Bandwidth limited
    }


async def _detect_mega_account_type(api):
    """Detect MEGA account type (free/premium) and return settings"""
    try:
        # Add a small delay to ensure account details are available
        await asyncio.sleep(0.5)

        # Get account details with retry mechanism
        account_details = None
        for attempt in range(3):
            try:
                account_details = api.getAccountDetails()
                if account_details:
                    break
                await asyncio.sleep(0.5)
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1.0)

        if account_details:
            try:
                pro_level = account_details.getProLevel()
                account_details.getStorageUsed()
                account_details.getStorageMax()
                account_details.getTransferOwnUsed()
                account_details.getTransferMax()

                is_premium = pro_level > 0

                if is_premium:
                    LOGGER.info(
                        f"🎉 MEGA Premium account detected (Level {pro_level})"
                    )
                else:
                    LOGGER.info("📱 MEGA Free account detected")

                return is_premium, _get_premium_settings(is_premium)
            except Exception:
                LOGGER.info(
                    "📱 MEGA account detected, using free account settings as fallback"
                )
                return False, _get_premium_settings(False)
        else:
            LOGGER.info("📱 MEGA account detected, using free account settings")
            return False, _get_premium_settings(False)

    except Exception as e:
        LOGGER.info(f"Error detecting MEGA account type: {e}")
        LOGGER.info(
            "📱 MEGA account detected, using free account settings as fallback"
        )
        return False, _get_premium_settings(False)


async def _navigate_to_folder(api, root_node, folder_path):
    """Navigate to a specific folder path in MEGA drive"""
    try:
        if not folder_path or folder_path in {"", "/"}:
            return root_node

        # Remove leading/trailing slashes and split path
        path_parts = folder_path.strip("/").split("/")
        current_node = root_node

        for part in path_parts:
            if not part:  # Skip empty parts
                continue

            # Get children of current node
            children = await sync_to_async(api.getChildren, current_node)
            if not children:
                LOGGER.error("No children found in current folder")
                return None

            # Find the folder with matching name
            found_folder = None
            for i in range(children.size()):
                child = children.get(i)
                if child and child.isFolder() and not child.isRemoved():
                    child_name = child.getName()
                    if child_name == part:
                        found_folder = child
                        break

            if found_folder is None:
                LOGGER.error(f"Folder '{part}' not found in path '{folder_path}'")
                return None

            current_node = found_folder

        return current_node

    except Exception as e:
        LOGGER.error(f"Error navigating to folder '{folder_path}': {e}")
        return None


async def add_mega_upload(listener, path):
    """
    Upload files/folders to MEGA.nz using the MEGA SDK v4.8.0 with FFmpeg support.

    Args:
        listener: Upload listener object
        path: Local path to upload
    """
    # Check if MEGA operations are enabled
    if not Config.MEGA_ENABLED:
        await listener.on_upload_error(
            "❌ MEGA.nz operations are disabled by the administrator."
        )
        return

    # Check if MEGA upload operations are enabled
    if not Config.MEGA_UPLOAD_ENABLED:
        await listener.on_upload_error(
            "❌ MEGA.nz upload operations are disabled by the administrator."
        )
        return

    # Get MEGA credentials following the same logic as other cloud services
    # Check USER_TOKENS setting to determine credential priority
    user_tokens_enabled = listener.user_dict.get("USER_TOKENS", False)

    # Get MEGA settings with priority: User > Owner (when USER_TOKENS enabled)
    user_mega_email = listener.user_dict.get("MEGA_EMAIL")
    user_mega_password = listener.user_dict.get("MEGA_PASSWORD")

    if user_tokens_enabled:
        # When USER_TOKENS is enabled, only use user's personal credentials
        if user_mega_email and user_mega_password:
            MEGA_EMAIL = user_mega_email
            MEGA_PASSWORD = user_mega_password
            LOGGER.info(
                "✅ Using user MEGA credentials for upload (USER_TOKENS enabled)"
            )
        else:
            await listener.on_upload_error(
                "❌ USER_TOKENS is enabled but user's MEGA credentials not found. Please set your MEGA email and password in User Settings → ☁️ MEGA."
            )
            return
    else:
        # When USER_TOKENS is disabled, use owner credentials only
        MEGA_EMAIL = Config.MEGA_EMAIL
        MEGA_PASSWORD = Config.MEGA_PASSWORD
        LOGGER.info(
            "✅ Using owner MEGA credentials for upload (USER_TOKENS disabled)"
        )

    if not MEGA_EMAIL or not MEGA_PASSWORD:
        if user_tokens_enabled:
            await listener.on_upload_error(
                "❌ USER_TOKENS is enabled but user's MEGA credentials are incomplete. Please set both MEGA email and password in User Settings."
            )
            return
        await listener.on_upload_error(
            "❌ Owner MEGA credentials not configured. Please contact the administrator or enable USER_TOKENS to use your own credentials."
        )
        return

    # Try to reuse existing folder selector session first
    user_id = listener.user_id if hasattr(listener, "user_id") else None
    reused_session = False

    # Import folder selector to access active sessions
    try:
        from bot.helper.mirror_leech_utils.mega_utils.folder_selector import (
            active_mega_selectors,
        )

        if user_id and user_id in active_mega_selectors:
            # Reuse existing authenticated session
            folder_selector = active_mega_selectors[user_id]
            if (
                hasattr(folder_selector, "async_api")
                and hasattr(folder_selector, "api")
                and folder_selector.mega_listener
                and folder_selector.mega_listener.node
            ):
                async_api = folder_selector.async_api
                api = folder_selector.api

                # Create upload listener but reuse the existing API
                mega_listener = MegaUploadListener(
                    async_api.continue_event, listener
                )
                mega_listener.node = (
                    folder_selector.mega_listener.node
                )  # Reuse authenticated node
                mega_listener.error = None
                reused_session = True
    except ImportError:
        LOGGER.info("📡 Folder selector not available, creating new session")

    if not reused_session:
        # Create new session if reuse failed
        async_api = AsyncMega()
        # Use a unique app identifier with timestamp to avoid session conflicts
        unique_app_id = f"aimleechbot_upload_{int(time_module.time())}"
        async_api.api = api = MegaApi(None, None, None, unique_app_id)
        mega_listener = MegaUploadListener(async_api.continue_event, listener)
        async_api.listener = mega_listener  # Connect listener to async_api
        api.addListener(mega_listener)

        try:
            # Add a small delay to avoid session conflicts with folder selector
            await asyncio.sleep(1)

            # Login with credentials
            await async_api.login(MEGA_EMAIL, MEGA_PASSWORD)
        except Exception as e:
            error_msg = f"Error during MEGA login: {e!s}"
            LOGGER.error(error_msg)
            await listener.on_upload_error(error_msg)
            return

    # Check for login errors (both reused and new sessions)
    if mega_listener.error is not None:
        error_msg = mega_listener.error
        LOGGER.error(f"Failed to login to MEGA: {error_msg}")

        # Provide user-friendly error messages for common authentication issues
        if any(
            auth_error in error_msg.lower()
            for auth_error in [
                "access denied",
                "login required",
                "invalid credentials",
                "authentication failed",
                "unauthorized",
                "forbidden",
            ]
        ):
            if "access denied" in error_msg.lower():
                friendly_msg = (
                    "❌ MEGA Authentication Failed: Access denied.\n\n"
                    "This usually means:\n"
                    "• Invalid MEGA email or password\n"
                    "• Account suspended or restricted\n"
                    "• Two-factor authentication enabled (not supported)\n\n"
                    "Please check your MEGA credentials in bot settings."
                )
            else:
                friendly_msg = f"❌ MEGA Authentication Error: {error_msg}"
            await listener.on_upload_error(friendly_msg)
        else:
            await listener.on_upload_error(f"Failed to login to MEGA: {error_msg}")
        return

    # Verify we have a valid node
    if not mega_listener.node:
        error_msg = "Failed to get MEGA root node for upload"
        LOGGER.error(error_msg)
        await listener.on_upload_error(error_msg)
        return

    # Detect account type and get optimized settings
    try:
        is_premium, premium_settings = await _detect_mega_account_type(api)
    except Exception as e:
        LOGGER.warning(
            f"Could not detect account type: {e}, using free account settings"
        )

    # Get upload destination folder (use node handles for memory safety)
    upload_folder_node = mega_listener.node  # Root by default

    # Check if user selected a specific folder through folder selector
    selected_folder_path = getattr(listener, "mega_upload_path", None)

    if selected_folder_path:
        upload_folder_node = await _navigate_to_folder(
            api, mega_listener.node, selected_folder_path
        )
        if upload_folder_node is None:
            error_msg = (
                f"Failed to navigate to selected folder: {selected_folder_path}"
            )
            LOGGER.error(error_msg)
            await listener.on_upload_error(error_msg)
            return
        # Store the folder path for display in completion message
        mega_listener.upload_folder_path = selected_folder_path
    else:
        # No folder selector used - upload to root folder
        # (Config.MEGA_UPLOAD_FOLDER removed - always use folder selector)
        mega_listener.upload_folder_path = ""

    # Store node handle for memory safety (prevent segmentation faults)
    upload_folder_handle = upload_folder_node.getHandle()

    # Set name and size based on the path
    if ospath.isfile(path):
        # For clone operations, use the original name if available
        if hasattr(listener, "original_mega_name") and listener.original_mega_name:
            listener.name = listener.name or listener.original_mega_name
        else:
            listener.name = listener.name or ospath.basename(path)
        listener.size = await aiopath.getsize(path)
        listener.is_file = True
    else:
        # For clone operations, use the original name if available
        if hasattr(listener, "original_mega_name") and listener.original_mega_name:
            listener.name = listener.name or listener.original_mega_name
        else:
            listener.name = listener.name or ospath.basename(path)
        listener.is_file = False
        # Calculate folder size
        total_size = 0
        for dirpath, _, filenames in walk(path):
            for filename in filenames:
                filepath = ospath.join(dirpath, filename)
                if ospath.exists(filepath):
                    total_size += ospath.getsize(filepath)
        listener.size = total_size

    gid = token_hex(4)

    # Check if upload should be queued
    added_to_queue, event = await check_running_tasks(listener)
    if added_to_queue:
        async with task_dict_lock:
            task_dict[listener.mid] = QueueStatus(listener, gid, "up")
        await send_status_message(listener.message)
        await event.wait()
        async with task_dict_lock:
            if listener.mid not in task_dict:
                await async_api.logout()
                return
        from_queue = True
    else:
        from_queue = False

    # Create upload status tracker
    async with task_dict_lock:
        task_dict[listener.mid] = MegaUploadStatus(
            listener, mega_listener, gid, "up"
        )

    # Start the upload
    if from_queue:
        pass
    else:
        # Update existing status message instead of creating new one
        await update_status_message(listener.message.chat.id)

    try:
        # Generate thumbnail if it's a video file and thumbnail generation is enabled
        thumbnail_path = None
        if ospath.isfile(path) and Config.MEGA_UPLOAD_THUMBNAIL:
            thumbnail_path = await generate_video_thumbnail(path)

        # Start the actual upload
        try:
            # Get the actual node from handle for upload (safer approach)
            upload_node = api.getNodeByHandle(upload_folder_handle)
            if not upload_node:
                error_msg = "Failed to get upload folder node from handle"
                LOGGER.error(error_msg)
                await listener.on_upload_error(error_msg)
                return

            if ospath.isfile(path):
                # Upload single file with MEGA SDK v4.8.0 API signature
                # startUpload(localPath, parent, fileName, mtime, appData, isSourceTemporary, startFirst, cancelToken)
                ospath.getsize(path)

                await async_api.run(
                    api.startUpload,
                    path,
                    upload_node,
                    listener.name,
                    -1,
                    None,
                    False,
                    False,
                    None,
                )
            else:
                # Upload folder - create subfolder and upload all files to it
                # For MEGA folder downloads, use the original folder name instead of task ID
                if hasattr(listener, "original_name") and listener.original_name:
                    folder_name = listener.original_name
                else:
                    # Fallback: try to get a meaningful name from the path or use listener.name
                    folder_name = listener.name
                    # If listener.name is just a task ID (numeric), try to get a better name
                    if folder_name.isdigit():
                        # Try to get folder name from the first file in the directory
                        try:
                            files_in_dir = os.listdir(path)
                            if files_in_dir:
                                # Extract a common prefix or use a generic name
                                first_file = files_in_dir[0]
                                # Try to extract series/movie name from filename
                                if "." in first_file:
                                    # Remove file extension and try to get meaningful name
                                    base_name = first_file.rsplit(".", 1)[0]
                                    # Look for common patterns like series names
                                    if "S0" in base_name and "E0" in base_name:
                                        # Extract series name (everything before season info)
                                        parts = base_name.split(".")
                                        series_parts = []
                                        for part in parts:
                                            if "S0" in part and "E0" in part:
                                                break
                                            series_parts.append(part)
                                        if series_parts:
                                            folder_name = ".".join(series_parts)
                                        else:
                                            folder_name = base_name
                                    else:
                                        folder_name = base_name
                                else:
                                    folder_name = first_file
                        except Exception as e:
                            LOGGER.warning(f"Failed to extract folder name: {e}")
                            folder_name = f"Downloaded_Folder_{listener.name}"

                # First, try to create the subfolder in MEGA destination
                try:
                    folder_node = await async_api.run(
                        api.createFolder, folder_name, upload_node
                    )

                    if folder_node is None:
                        # Sometimes MEGA API returns None even when folder is created
                        # Try to find the folder by searching children of upload_node
                        try:
                            children = api.getChildren(upload_node)
                            folder_node = None
                            # MegaNodeList needs to be accessed by index
                            for i in range(children.size()):
                                child = children.get(i)
                                if (
                                    child.getName() == folder_name
                                ):  # Use child.getName() not api.getName(child)
                                    folder_node = child
                                    break
                        except Exception as e:
                            LOGGER.warning(
                                f"Error searching for existing subfolder: {e}"
                            )

                        if folder_node is None:
                            LOGGER.warning(
                                f"Failed to create subfolder '{folder_name}' - will upload directly to selected folder"
                            )
                            folder_node = (
                                upload_node  # Use the selected folder directly
                            )
                            folder_name = (
                                "selected folder"  # Update name for logging
                            )
                except Exception as e:
                    LOGGER.warning(
                        f"Exception creating subfolder '{folder_name}': {e} - will upload directly to selected folder"
                    )
                    folder_node = upload_node  # Use the selected folder directly
                    folder_name = "selected folder"  # Update name for logging

                # Get all files in the local folder
                files_to_upload = []
                for item in os.listdir(path):
                    item_path = ospath.join(path, item)
                    if ospath.isfile(item_path):
                        files_to_upload.append((item_path, item))

                # Set multiple flags to prevent premature task completion
                listener.is_multi_file_upload = True
                listener.is_uploading = True
                # Also set flag on the async_api to prevent MEGA SDK callbacks
                if hasattr(async_api, "listener") and async_api.listener:
                    async_api.listener.is_multi_file_upload = True

                # Upload each file to the created subfolder
                uploaded_files = []
                for i, (file_path, file_name) in enumerate(files_to_upload, 1):
                    # Start the upload
                    async_api.continue_event.clear()
                    await sync_to_async(
                        api.startUpload,
                        file_path,
                        folder_node,
                        file_name,
                        -1,
                        None,
                        False,
                        False,
                        None,
                    )

                    # Wait for the TRANSFER to complete (not just the request)
                    # The continue_event will be set by onTransferFinish when upload actually completes
                    await async_api.continue_event.wait()

                    # Check for errors
                    if async_api.listener and async_api.listener.error:
                        raise Exception(
                            f"MEGA upload failed: {async_api.listener.error}"
                        )

                    uploaded_files.append(file_name)

                # Create MEGA link for the upload destination BEFORE clearing flags
                try:
                    # Export the node to make it public using direct sync call
                    await sync_to_async(api.exportNode, folder_node)

                    # Try multiple methods to get the public link with decryption key
                    upload_link = None

                    # Method 1: Try getPublicLink()
                    try:
                        upload_link = folder_node.getPublicLink()
                    except Exception as e:
                        LOGGER.warning(f"Method 1 failed: {e}")

                    # Method 2: Try alternative approaches for MEGA SDK v4.8.0
                    if not upload_link:
                        try:
                            # Try to get public handle first
                            handle = folder_node.getPublicHandle()
                            if handle:
                                # For MEGA SDK v4.8.0, try getPublicLink again after a small delay
                                await asyncio.sleep(0.5)
                                upload_link = folder_node.getPublicLink()
                                # Try to check if the node has been exported properly
                                if folder_node.isExported():
                                    upload_link = f"https://mega.nz/folder/{handle}"
                                    LOGGER.warning(
                                        "📁 Generated public link without decryption key (method 2)"
                                    )
                                else:
                                    LOGGER.warning("📁 Node not properly exported")
                        except Exception as e:
                            LOGGER.warning(f"Method 2 failed: {e}")

                    # Method 3: Fallback to handle-only link
                    if not upload_link:
                        upload_link = (
                            f"https://mega.nz/folder/{folder_node.getBase64Handle()}"
                        )
                        LOGGER.warning(
                            "📁 Could not get public link with key, using handle-only link"
                        )

                except Exception as e:
                    # Fallback to handle-only link if export fails
                    upload_link = (
                        f"https://mega.nz/folder/{folder_node.getBase64Handle()}"
                    )
                    LOGGER.warning(
                        f"📁 Failed to export node for public link: {e}, using handle-only link"
                    )

                # Add a small delay to ensure all transfers are truly complete
                await asyncio.sleep(2)

                # Clear all multi-file upload flags
                listener.is_multi_file_upload = False
                listener.is_uploading = False
                # Also clear flag on the async_api
                if hasattr(async_api, "listener") and async_api.listener:
                    async_api.listener.is_multi_file_upload = False

                # Determine folder count based on whether we created a subfolder
                folder_count = 1 if folder_node != upload_node else 0

                # Manually trigger completion with upload information
                if listener:
                    await listener.on_upload_complete(
                        link=upload_link,
                        files=len(uploaded_files),
                        folders=folder_count,
                        mime_type="Folder",
                        rclone_path="",
                        dir_id="",
                    )

        except Exception as e:
            error_msg = f"MEGA upload operation failed: {e!s}"
            LOGGER.error(error_msg)
            await listener.on_upload_error(error_msg)
            return

        # Clean up thumbnail if it was generated
        if thumbnail_path and ospath.exists(thumbnail_path):
            try:
                await aioremove(thumbnail_path)
            except Exception as e:
                LOGGER.error(f"Failed to clean up thumbnail: {e}")

    except Exception as e:
        error_msg = f"Error during MEGA upload: {e!s}"
        LOGGER.error(error_msg)
        await listener.on_upload_error(error_msg)
    finally:
        # Only logout if we created a new session, not if we reused one
        if not reused_session:
            try:
                await async_api.logout()
            except Exception as logout_error:
                LOGGER.warning(f"MEGA upload logout warning: {logout_error}")
