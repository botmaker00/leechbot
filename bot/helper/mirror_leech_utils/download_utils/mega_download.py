import contextlib
import os
import time
from secrets import token_hex

from aiofiles.os import makedirs

from bot import DOWNLOAD_DIR, LOGGER, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath
from bot.helper.ext_utils.bot_utils import sync_to_async
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.links_utils import get_mega_link_type
from bot.helper.ext_utils.mega_utils import MegaApi
from bot.helper.ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
)
from bot.helper.listeners.mega_listener import AsyncMega, MegaAppListener
from bot.helper.mirror_leech_utils.status_utils.mega_status import MegaDownloadStatus
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.telegram_helper.message_utils import send_status_message


async def add_mega_download(listener, path):
    # Initialize variables for proper cleanup
    async_api = None
    api = None
    folder_api = None
    mega_listener = None

    # Validate path parameter
    if not path:
        await listener.on_download_error(
            "❌ MEGA download failed: Invalid download path (empty)"
        )
        return

    if not isinstance(path, str):
        await listener.on_download_error(
            f"❌ MEGA download failed: Invalid download path type: {type(path)}"
        )
        return

    try:
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

                    # Create download listener but reuse the existing API
                    mega_listener = MegaAppListener(
                        async_api.continue_event, listener
                    )
                    mega_listener.node = (
                        folder_selector.mega_listener.node
                    )  # Reuse authenticated node
                    mega_listener.error = None
                    mega_listener.async_api = (
                        async_api  # Add reference for multi-file flag checking
                    )
                    reused_session = True
        except ImportError:
            LOGGER.info(
                "📡 Folder selector not available for download, creating new session"
            )

        if not reused_session:
            # Create new session if reuse failed
            async_api = AsyncMega()
            # Use a unique app identifier with timestamp to avoid session conflicts
            unique_app_id = f"aimleechbot_download_{int(time.time())}"
            async_api.api = api = MegaApi(None, None, None, unique_app_id)

            mega_listener = MegaAppListener(async_api.continue_event, listener)
            async_api.listener = mega_listener  # Connect listener to async_api
            mega_listener.async_api = (
                async_api  # Add reference for multi-file flag checking
            )
            api.addListener(mega_listener)

        # Get MEGA credentials following the same logic as other cloud services
        user_dict = listener.user_dict

        # Check USER_TOKENS setting to determine credential priority
        user_tokens_enabled = user_dict.get("USER_TOKENS", False)

        # Get MEGA settings with priority: User > Owner (when USER_TOKENS enabled)
        user_mega_email = user_dict.get("MEGA_EMAIL")
        user_mega_password = user_dict.get("MEGA_PASSWORD")

        if user_tokens_enabled:
            # When USER_TOKENS is enabled, only use user's personal credentials
            if user_mega_email and user_mega_password:
                MEGA_EMAIL = user_mega_email
                MEGA_PASSWORD = user_mega_password
                LOGGER.info(
                    "Using user MEGA credentials for download (USER_TOKENS enabled)"
                )
            else:
                await listener.on_download_error(
                    "❌ USER_TOKENS is enabled but user's MEGA credentials not found. Please set your MEGA email and password in User Settings → ☁️ MEGA."
                )
                return
        else:
            # When USER_TOKENS is disabled, use owner credentials only
            MEGA_EMAIL = Config.MEGA_EMAIL
            MEGA_PASSWORD = Config.MEGA_PASSWORD
            LOGGER.info(
                "Using owner MEGA credentials for download (USER_TOKENS disabled)"
            )

        if not MEGA_EMAIL or not MEGA_PASSWORD:
            if user_tokens_enabled:
                await listener.on_download_error(
                    "❌ USER_TOKENS is enabled but user's MEGA credentials are incomplete. Please set both MEGA email and password in User Settings."
                )
                return
            await listener.on_download_error(
                "❌ Owner MEGA credentials not configured. Please contact the administrator or enable USER_TOKENS to use your own credentials."
            )
            return

        # Login with the determined credentials (skip if reusing session)
        if not reused_session:
            await async_api.login(MEGA_EMAIL, MEGA_PASSWORD)

        if get_mega_link_type(listener.link) == "file":
            await async_api.getPublicNode(listener.link)
            node = mega_listener.public_node
        else:
            async_api.folder_api = folder_api = MegaApi(None, None, None, "aim")
            folder_api.addListener(mega_listener)

            await async_api.run(folder_api.loginToFolder, listener.link)
            node = await sync_to_async(folder_api.authorizeNode, mega_listener.node)

            # Use folder_api to get children since that's what we used to authorize the node
            children = folder_api.getChildren(node)
            child_nodes = [children.get(i) for i in range(children.size())]

            # For folders, we need to download all children, not the folder itself
            if child_nodes:
                # Store children for later download
                mega_listener.child_nodes = child_nodes
            else:
                await listener.on_download_error(
                    "MEGA folder is empty or inaccessible"
                )
                await async_api.logout()
                return

        if not node:
            await listener.on_download_error("Failed to get MEGA node")
            await async_api.logout()
            return

    except Exception as e:
        await listener.on_download_error(f"MEGA download setup failed: {e}")
        await async_api.logout()
        return

    listener.name = listener.name or node.getName()
    gid = token_hex(5)

    msg, button = await stop_duplicate_check(listener)
    if msg:
        await listener.on_download_error(msg, button)
        await async_api.logout()
        return

    # Calculate total size (for folders, sum all children sizes)
    if hasattr(mega_listener, "child_nodes") and mega_listener.child_nodes:
        total_size = 0
        for child_node in mega_listener.child_nodes:
            # Use folder_api for size calculation since that's what we used to get the nodes
            child_size = await sync_to_async(folder_api.getSize, child_node)
            total_size += child_size
        listener.size = total_size
    else:
        listener.size = await sync_to_async(api.getSize, node)

    if limit_exceeded := await limit_checker(listener.size, listener, isMega=True):
        await listener.on_download_error(limit_exceeded, is_limit=True)
        await async_api.logout()
        return

    added_to_queue, event = await check_running_tasks(listener)
    if added_to_queue:
        async with task_dict_lock:
            task_dict[listener.mid] = QueueStatus(listener, gid, "Dl")
        await listener.on_download_start()
        if listener.multi <= 1:
            await send_status_message(listener.message)
        await event.wait()
        if listener.is_cancelled:
            await async_api.logout()
            return

    async with task_dict_lock:
        task_dict[listener.mid] = MegaDownloadStatus(
            listener, mega_listener, gid, "dl"
        )

    if added_to_queue:
        LOGGER.info(f"Start Queued Download from Mega: {listener.name}")
    else:
        try:
            await listener.on_download_start()
        except Exception as start_error:
            LOGGER.error(f"Error in listener.on_download_start(): {start_error}")
            raise

        if listener.multi <= 1:
            try:
                # Ensure base downloads directory exists before status operations
                # This is needed because status functions may access DOWNLOAD_DIR
                base_downloads_dir = DOWNLOAD_DIR.rstrip("/")
                if not await aiopath.exists(base_downloads_dir):
                    await makedirs(base_downloads_dir, exist_ok=True)

                await send_status_message(listener.message)
            except Exception as status_error:
                LOGGER.error(f"Error in send_status_message(): {status_error}")
                raise

    # Perform the actual download
    try:
        # Check if base downloads directory exists
        base_downloads_dir = "/usr/src/app/downloads"
        base_exists = await aiopath.exists(base_downloads_dir)

        if not base_exists:
            await makedirs(base_downloads_dir, exist_ok=True)

        # Ensure the download directory exists
        await makedirs(path, exist_ok=True)

        # Verify the directory was created
        if not await aiopath.exists(path):
            raise FileNotFoundError(f"Failed to create download directory: {path}")

        if not await aiopath.isdir(path):
            raise NotADirectoryError(f"Download path is not a directory: {path}")

        # Check if this is a folder with children or a single file
        if hasattr(mega_listener, "child_nodes") and mega_listener.child_nodes:
            # For folders, MEGA SDK downloads each file individually
            # We need to wait for all files to complete

            total_files = len(mega_listener.child_nodes)
            completed_files = 0

            # Use folder_api to download the entire folder
            abs_path = os.path.abspath(path)

            # Reset the listener and set multi-file flag
            mega_listener.continue_event.clear()
            mega_listener.error = None
            mega_listener.is_multi_file_download = (
                True  # Prevent early listener calls
            )

            # Set the flag on the folder API listener as well
            if hasattr(folder_api, "_listener"):
                folder_api._listener.is_multi_file_download = True

            # Create a shared flag that can be accessed by all transfer events
            # Store it in the async_api object so it's accessible to all listeners
            async_api.is_multi_file_download = True

            await async_api.run(
                folder_api.startDownload,
                node,  # Download the entire folder node
                abs_path,  # Absolute local destination path
                None,  # customName (use default)
                None,  # appData (not needed)
                True,  # startFirst (start immediately)
                None,  # cancelToken (not needed)
            )

            while completed_files < total_files:
                # Wait for transfer completion
                await mega_listener.continue_event.wait()

                if mega_listener.error:
                    LOGGER.error(f"MEGA download error: {mega_listener.error}")
                    break

                completed_files += 1

                # Reset for next file if not the last one
                if completed_files < total_files:
                    mega_listener.continue_event.clear()

            # Reset the multi-file flag and call the listener now that all files are done
            mega_listener.is_multi_file_download = False

            base_download_dir = os.path.dirname(abs_path)
            if os.path.exists(base_download_dir):
                try:
                    os.listdir(base_download_dir)

                    # Check the specific download directory
                    if os.path.exists(abs_path):
                        contents = os.listdir(abs_path)
                        LOGGER.info(f"Successfully downloaded {len(contents)} files")
                    else:
                        LOGGER.warning(
                            f"Download directory does not exist: {abs_path}"
                        )
                except Exception as e:
                    LOGGER.error(f"Error investigating download: {e}")

            # Now call the listener to start processing all downloaded files
            if mega_listener.listener and completed_files > 0:
                await mega_listener.listener.on_download_complete()
        else:
            # Download single file
            await async_api.run(
                api.startDownload,
                node,  # MEGA node to download
                path,  # Local destination path
                None,  # customName (use default)
                None,  # appData (not needed)
                True,  # startFirst (start immediately)
                None,  # cancelToken (not needed)
            )
    except Exception as e:
        # Handle download errors
        LOGGER.error(f"MEGA download error: {e}")
        with contextlib.suppress(Exception):
            await listener.on_download_error(f"MEGA download failed: {e}")

    finally:
        # Comprehensive cleanup to prevent segfaults
        try:
            # Remove listeners before cleanup to prevent callbacks
            if api and mega_listener:
                with contextlib.suppress(Exception):
                    api.removeListener(mega_listener)

            if folder_api and mega_listener:
                with contextlib.suppress(Exception):
                    folder_api.removeListener(mega_listener)

            # Logout APIs
            if async_api:
                try:
                    await async_api.logout()
                except Exception as logout_error:
                    LOGGER.warning(f"Final MEGA logout error: {logout_error}")

            # Clean up task from status
            try:
                async with task_dict_lock:
                    if listener.mid in task_dict:
                        del task_dict[listener.mid]
            except Exception:
                pass

            # Force cleanup of MEGA objects to prevent segfault
            try:
                if mega_listener:
                    mega_listener.is_cancelled = True
                    mega_listener.continue_event.set()
                    mega_listener = None

                # Only logout if we created a new session, not if we reused one
                if not reused_session and async_api:
                    await async_api.logout()

                if api:
                    api = None

                if folder_api:
                    folder_api = None

                if async_api:
                    async_api.api = None
                    async_api.folder_api = None
                    async_api.listener = None
                    async_api = None

            except Exception as cleanup_error:
                LOGGER.warning(f"MEGA object cleanup error: {cleanup_error}")

        except Exception as final_error:
            LOGGER.error(f"Critical error during MEGA cleanup: {final_error}")
            # Don't re-raise to prevent masking the original error
