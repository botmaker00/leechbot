#!/usr/bin/env python3
"""
Unified MEGA Listener and AsyncMega Implementation
Shared components for all MEGA operations (download, upload, clone, search)
"""

import asyncio
import contextlib
import os
import re
import time as time_module
from asyncio import Event

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import async_to_sync, sync_to_async
from bot.helper.ext_utils.mega_utils import (
    MegaListener,
    MegaRequest,
)


class MegaAppListener(MegaListener):
    """Base MEGA listener class with common functionality"""

    _NO_EVENT_ON = (MegaRequest.TYPE_LOGIN, MegaRequest.TYPE_FETCH_NODES)

    def __init__(self, continue_event: Event, listener=None):
        super().__init__()
        self.continue_event = continue_event
        self.listener = listener
        self.is_cancelled = False
        self.error = None
        self.__bytes_transferred = 0
        self.__speed = 0
        self.__name = ""
        self.__start_time = time_module.time()

        # Properties needed by different operations
        self.node = None
        self.public_node = None
        self.public_link = None

    @property
    def downloaded_bytes(self):
        return self.__bytes_transferred

    @property
    def speed(self):
        return self.__speed

    @property
    def name(self):
        return self.__name

    async def cancel_task(self):
        """Cancel the current MEGA operation"""
        self.is_cancelled = True
        if self.listener:
            # Use appropriate error callback based on operation type
            if hasattr(self.listener, "on_upload_error"):
                await self.listener.on_upload_error("Operation cancelled by user")
            else:
                await self.listener.on_download_error("Operation cancelled by user")

    def onRequestStart(self, api, request):
        pass

    def onRequestFinish(self, api, request, error):
        try:
            if self.is_cancelled:
                self.continue_event.set()
                return

            if str(error).lower() != "no error":
                self.error = str(error)
                # Don't log "Access denied" errors during cleanup/logout phase
                if "access denied" in str(error).lower():
                    LOGGER.warning(
                        f"MEGA Request Warning (likely cleanup): {self.error}"
                    )
                else:
                    LOGGER.error(f"MEGA Request Error: {self.error}")
                self.continue_event.set()
                return

            request_type = request.getType()

            if request_type == MegaRequest.TYPE_LOGIN:
                api.fetchNodes()
            elif request_type == MegaRequest.TYPE_GET_PUBLIC_NODE:
                self.public_node = request.getPublicMegaNode()
                if self.public_node:
                    self.__name = self.public_node.getName()
            elif request_type == MegaRequest.TYPE_FETCH_NODES:
                self.node = api.getRootNode()
                self.nodes_fetched = True
                if self.node:
                    self.__name = self.node.getName()

            # Always set continue event for successful requests
            # The _NO_EVENT_ON was causing fetchNodes to hang
            if (
                request_type not in self._NO_EVENT_ON
                or (self.node and "cloud drive" not in self.__name.lower())
                or request_type == MegaRequest.TYPE_FETCH_NODES
            ):
                self.continue_event.set()

        except Exception as e:
            LOGGER.error(f"Exception in MEGA onRequestFinish: {e}")
            self.error = str(e)
            self.continue_event.set()

    def onRequestTemporaryError(self, api, request, error):
        error_msg = error.toString()
        request_type = request.getType() if request else "Unknown"
        error_code = error.getErrorCode()

        LOGGER.warning(f"MEGA Request temporary error: {error_msg}")

        # Provide specific error messages for common error codes
        if error_code == -3:  # EARGS - Invalid arguments or credentials
            if request_type == 0:  # TYPE_LOGIN
                self.error = "Invalid MEGA credentials or login arguments"
                LOGGER.error(
                    "MEGA login failed: Invalid credentials or arguments (error -3)"
                )
            else:
                self.error = (
                    f"Invalid arguments for MEGA request type {request_type}"
                )
        elif error_code == -9:  # ENOENT - Object not found
            self.error = "MEGA object not found"
        elif error_code == -11:  # EACCESS - Access denied
            self.error = "MEGA access denied - check account permissions"
        elif error_code == -18:  # ETOOMANY - Too many requests
            self.error = "MEGA rate limit exceeded - too many requests"
        else:
            # Store the original error for other codes
            self.error = error_msg

        # For login errors, always cancel
        if request_type == 0:  # TYPE_LOGIN
            LOGGER.error("MEGA login error - cancelling operation")
            if not self.is_cancelled:
                self.is_cancelled = True
                if self.listener:
                    async_to_sync(
                        self.listener.on_download_error,
                        f"MEGA Login Error: {self.error}",
                    )
            self.continue_event.set()
            return

        # For folder selection operations, don't cancel immediately on temporary errors
        # Let the calling code decide how to handle it
        if request_type == 1:  # TYPE_FETCH_NODES
            self.continue_event.set()
            return

        # For other operations, only send to Telegram if it's a permanent error
        # Temporary errors should be handled silently with retries
        self.continue_event.set()

    def onTransferStart(self, api, transfer):
        pass

    def onTransferUpdate(self, api, transfer):
        try:
            # Safety check - ensure objects are still valid
            if not api or not transfer:
                return

            if self.is_cancelled:
                api.cancelTransfer(transfer, None)
                return

            self.__speed = transfer.getSpeed()
            self.__bytes_transferred = transfer.getTransferredBytes()
        except Exception as e:
            LOGGER.error(f"Exception in MEGA onTransferUpdate: {e}")
            with contextlib.suppress(Exception):
                self.continue_event.set()

    def onTransferFinish(self, api, transfer, error):
        try:
            # Safety check - ensure objects are still valid
            if not api or not transfer or not error:
                LOGGER.warning("MEGA onTransferFinish called with null objects")
                self.continue_event.set()
                return

            if self.is_cancelled:
                self.continue_event.set()
                return

            if str(error).lower() != "no error":
                self.error = str(error)
                LOGGER.error(f"MEGA Transfer Error: {self.error}")
                if self.listener:
                    async_to_sync(
                        self.listener.on_download_error,
                        f"MEGA Transfer Error: {self.error}",
                    )
            else:
                transfer.getFileName()
                local_path = transfer.getPath()

                # Add small delay to ensure file system is updated
                # Use sync sleep since this is called from MEGA SDK callback
                time_module.sleep(0.2)

                # Debug: Check if local_path is file or directory with detailed analysis
                path_exists = os.path.exists(local_path)
                is_file = os.path.isfile(local_path)
                is_dir = os.path.isdir(local_path)

                # Get additional file system info
                try:
                    stat_info = os.stat(local_path) if path_exists else None
                    stat_info and os.path.stat.S_ISREG(
                        stat_info.st_mode
                    ) if stat_info else False
                    stat_info and os.path.stat.S_ISDIR(
                        stat_info.st_mode
                    ) if stat_info else False
                except Exception as stat_error:
                    LOGGER.error(f"Error getting stat info: {stat_error}")
                    stat_info = None

                # Reduced verbose logging - only log if there are issues
                if not path_exists:
                    LOGGER.warning(
                        f"MEGA transfer path does not exist: {local_path}"
                    )

                # Try to list directory contents if it might be a directory
                if path_exists and not is_file:
                    try:
                        contents = os.listdir(local_path)
                        is_dir = True  # Force directory detection if listing works
                    except OSError as list_error:
                        LOGGER.error(f"Directory listing failed: {list_error}")

                # If detection is still unclear, wait longer
                if path_exists and not is_file and not is_dir:
                    time_module.sleep(1.0)
                    is_file = os.path.isfile(local_path)
                    is_dir = os.path.isdir(local_path)

                    # Try directory listing again
                    if not is_file:
                        try:
                            contents = os.listdir(local_path)
                            is_dir = True
                        except OSError:
                            pass

                # Additional heuristic: if filename looks like a directory name (e.g., "42964 (1)")
                # and we can't detect it properly, assume it's a directory
                if not is_file and not is_dir and path_exists:
                    filename_part = os.path.basename(local_path)
                    # Check if filename looks like a task ID with suffix (common MEGA pattern)
                    if re.match(r"^\d+\s*\(\d+\)$", filename_part):
                        is_dir = True

                if is_dir:
                    # List contents of directory
                    try:
                        contents = os.listdir(local_path)
                    except Exception as list_error:
                        LOGGER.error(
                            f"Error listing directory contents: {list_error}"
                        )

                # Store the actual download path for verification
                if local_path:
                    # The MEGA transfer path is the actual download directory
                    # Don't try to extract parent directory - use the path as-is
                    self.actual_download_path = local_path

                    # Update the listener's path to match the actual download path
                    if self.listener and hasattr(self.listener, "dir"):
                        if is_file:
                            # Single file: MEGA downloaded directly to a file
                            actual_parent_dir = os.path.dirname(local_path)
                            actual_downloaded_filename = os.path.basename(local_path)
                            original_filename = getattr(self.listener, "name", None)

                            # Update directory path
                            if actual_parent_dir != self.listener.dir:
                                self.listener.dir = actual_parent_dir

                            # Check if this is a multi-file download (folder download)
                            is_multi_file = getattr(
                                self, "is_multi_file_download", False
                            )

                            if is_multi_file:
                                # Don't rename - keep the actual downloaded filename
                                # For multi-file downloads, don't update listener.name as it causes confusion
                                # The listener.name will be set properly when all files are complete
                                pass
                            # Single file download - check if MEGA renamed the file (added suffix like " (1)")
                            elif (
                                original_filename
                                and actual_downloaded_filename != original_filename
                            ):
                                # MEGA renamed the file - we need to rename it back to preserve original name
                                original_path = os.path.join(
                                    actual_parent_dir, original_filename
                                )
                                downloaded_path = local_path

                                try:
                                    # Rename the file back to its original name
                                    os.rename(downloaded_path, original_path)
                                    # Update the stored path to reflect the rename
                                    self.actual_download_path = original_path
                                except Exception as rename_error:
                                    LOGGER.error(
                                        f"Failed to rename file back to original name: {rename_error}"
                                    )
                                    # If rename fails, update listener name to match what was actually downloaded
                                    self.listener.name = actual_downloaded_filename
                        elif is_dir:
                            # Directory: Check if it contains a single file (MEGA sometimes creates a directory)
                            try:
                                contents = os.listdir(local_path)

                                if len(contents) == 1:
                                    # Single file in directory - this is likely the actual file
                                    single_file_path = os.path.join(
                                        local_path, contents[0]
                                    )

                                    if os.path.isfile(single_file_path):
                                        # For single file downloads, update to point to the directory containing the file
                                        # The directory itself becomes the download location
                                        actual_filename = contents[
                                            0
                                        ]  # The actual filename

                                        if local_path != self.listener.dir:
                                            self.listener.dir = local_path

                                        if (
                                            hasattr(self.listener, "name")
                                            and actual_filename != self.listener.name
                                        ):
                                            self.listener.name = actual_filename
                                    # Directory contains a subdirectory
                                    elif local_path != self.listener.dir:
                                        self.listener.dir = local_path
                                # Multiple files in directory - treat as folder download
                                elif local_path != self.listener.dir:
                                    self.listener.dir = local_path
                            except Exception as list_error:
                                LOGGER.error(
                                    f"Error checking directory contents: {list_error}"
                                )
                                # Fallback: use the directory as-is
                                if local_path != self.listener.dir:
                                    self.listener.dir = local_path
                        else:
                            # Path doesn't exist or is neither file nor directory
                            LOGGER.warning(
                                f"MEGA transfer path is neither file nor directory: {local_path}"
                            )
                            LOGGER.warning(
                                f"Path exists: {os.path.exists(local_path)}"
                            )
                            # Try to use the path as-is
                            if local_path != self.listener.dir:
                                self.listener.dir = local_path

                # Only call listener if this is not a multi-file download or if it's the last file
                is_multi_file = getattr(self, "is_multi_file_download", False) or (
                    hasattr(self, "async_api")
                    and getattr(self.async_api, "is_multi_file_download", False)
                )

                if self.listener and not is_multi_file:
                    async_to_sync(self.listener.on_download_complete)

            self.continue_event.set()
        except Exception as e:
            LOGGER.error(f"Exception in MEGA onTransferFinish: {e}")
            # Ensure we always set the event to prevent hanging
            with contextlib.suppress(Exception):
                self.continue_event.set()

    def onTransferTemporaryError(self, api, transfer, error):
        try:
            # Safety check - ensure objects are still valid
            if not transfer or not error:
                LOGGER.warning(
                    "MEGA onTransferTemporaryError called with null objects"
                )
                self.continue_event.set()
                return

            if transfer.getState() in [1, 4]:
                return
            # Handle temporary transfer errors silently - let MEGA SDK retry automatically
            # Only log for debugging, don't send to Telegram
            self.continue_event.set()
        except Exception as e:
            LOGGER.error(f"Exception in MEGA onTransferTemporaryError: {e}")
            with contextlib.suppress(Exception):
                self.continue_event.set()


class AsyncMega:
    """Async wrapper for MEGA operations"""

    def __init__(self):
        self.continue_event = Event()
        self.api = None
        self.listener = None
        self.folder_api = None

    async def login(self, email, password):
        """Login to MEGA"""
        if not self.api:
            raise Exception("MEGA API not initialized")

        self.continue_event.clear()
        await sync_to_async(self.api.login, email, password)
        await self.continue_event.wait()

        if self.listener and self.listener.error:
            raise Exception(f"MEGA login failed: {self.listener.error}")

    async def fetchNodes(self):
        """Fetch MEGA nodes"""
        if not self.api:
            raise Exception("MEGA API not initialized")

        self.continue_event.clear()
        await sync_to_async(self.api.fetchNodes)
        await self.continue_event.wait()

        if self.listener and self.listener.error:
            raise Exception(f"MEGA fetchNodes failed: {self.listener.error}")

    async def getPublicNode(self, mega_link):
        """Get public node from MEGA link"""
        if not self.api:
            raise Exception("MEGA API not initialized")

        self.continue_event.clear()
        await sync_to_async(self.api.getPublicNode, mega_link)
        await self.continue_event.wait()

        if self.listener and self.listener.error:
            raise Exception(f"MEGA getPublicNode failed: {self.listener.error}")

    async def run(self, function, *args):
        """Run any MEGA function asynchronously"""
        self.continue_event.clear()
        await sync_to_async(function, *args)
        await self.continue_event.wait()

        if self.listener and self.listener.error:
            raise Exception(f"MEGA operation failed: {self.listener.error}")

    async def logout(self):
        """Logout from MEGA"""
        try:
            if self.api:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, self.api.logout),
                    timeout=30,
                )
        except Exception as e:
            LOGGER.warning(f"MEGA logout error: {e}")

        # Also logout folder API if it exists
        try:
            if self.folder_api:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self.folder_api.logout
                    ),
                    timeout=30,
                )
        except Exception as e:
            LOGGER.warning(f"MEGA folder API logout error: {e}")
