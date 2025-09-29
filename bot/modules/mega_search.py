#!/usr/bin/env python3
"""
MEGA Search Command Handler
Search through MEGA drive and provide download links
"""

import asyncio

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import (
    get_telegraph_list,
    sync_to_async,
)
from bot.helper.ext_utils.mega_utils import (
    MegaApi,
    MegaRequest,
)
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.listeners.mega_listener import AsyncMega, MegaAppListener
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    edit_message,
    send_message,
)


class MegaSearchListener(MegaAppListener):
    """MEGA SDK listener for search operations"""

    def __init__(self, continue_event, listener=None):
        super().__init__(continue_event, listener)
        self.search_results = []
        self.nodes_fetched = False

    def onRequestFinish(self, api, request, error):
        # Handle search-specific request types
        if str(error).lower() == "no error":
            request_type = request.getType()

            if request_type == MegaRequest.TYPE_FETCH_NODES:
                self.nodes_fetched = True

        # Call parent implementation for standard handling
        super().onRequestFinish(api, request, error)


class MegaSearchHandler:
    """Handle MEGA search operations"""

    def __init__(self, message, query):
        self.message = message
        self.query = query
        self.user_id = message.from_user.id
        self.results = []

    async def _manual_search(self, api, root_node, query):
        """Manual search through MEGA drive when API search fails"""
        try:
            results = []
            query_lower = query.lower()

            # Get all children recursively
            await self._search_node_recursive(api, root_node, query_lower, results)

            return results
        except Exception:
            return []

    async def _search_node_recursive(
        self, api, node, query_lower, results, depth=0, max_depth=10
    ):
        """Recursively search through MEGA nodes"""
        try:
            # Prevent infinite recursion
            if depth > max_depth:
                return

            # Check current node name
            node_name = node.getName() if node.getName() else ""
            if query_lower in node_name.lower():
                results.append(node)

            # If it's a folder, search its children
            if node.isFolder():
                try:
                    children = await sync_to_async(api.getChildren, node)
                    if children:
                        for i in range(children.size()):
                            child = children.get(i)
                            if child:
                                await self._search_node_recursive(
                                    api,
                                    child,
                                    query_lower,
                                    results,
                                    depth + 1,
                                    max_depth,
                                )
                except Exception:
                    pass  # Ignore folder access errors

        except Exception:
            pass  # Ignore node processing errors

    async def search(self):
        """Perform MEGA search"""
        # Check if MEGA operations are enabled
        if not Config.MEGA_ENABLED:
            await send_message(
                self.message,
                "❌ MEGA.nz operations are disabled by the administrator.",
            )
            return

        # Check if MEGA search is enabled
        if not Config.MEGA_SEARCH_ENABLED:
            await send_message(
                self.message,
                "❌ MEGA search is disabled by the administrator.",
            )
            return

        # Get MEGA credentials following the same logic as other cloud services
        from bot.helper.ext_utils.db_handler import database

        user_dict = await database.get_user_doc(self.user_id)

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
                    "Using user MEGA credentials for search (USER_TOKENS enabled)"
                )
            else:
                await send_message(
                    self.message,
                    "❌ USER_TOKENS is enabled but user's MEGA credentials not found. Please set your MEGA email and password in User Settings → ☁️ MEGA.",
                )
                return
        else:
            # When USER_TOKENS is disabled, use owner credentials only
            MEGA_EMAIL = Config.MEGA_EMAIL
            MEGA_PASSWORD = Config.MEGA_PASSWORD
            LOGGER.info(
                "Using owner MEGA credentials for search (USER_TOKENS disabled)"
            )

        if not MEGA_EMAIL or not MEGA_PASSWORD:
            if user_tokens_enabled:
                await send_message(
                    self.message,
                    "❌ USER_TOKENS is enabled but user's MEGA credentials are incomplete. Please set both MEGA email and password in User Settings.",
                )
                return
            await send_message(
                self.message,
                "❌ Owner MEGA credentials not configured. Please contact the administrator or enable USER_TOKENS to use your own credentials.",
            )
            return

        # Show searching message
        search_msg = await send_message(
            self.message,
            f"🔍 Searching MEGA drive for: <code>{self.query}</code>\n\n"
            "⏳ Please wait...",
        )

        async_api = AsyncMega()
        async_api.api = api = MegaApi(None, None, None, "aimleechbot")
        mega_listener = MegaSearchListener(async_api.continue_event)
        async_api.listener = mega_listener  # Connect listener to async_api
        api.addListener(mega_listener)

        try:
            # Login to MEGA
            await async_api.login(MEGA_EMAIL, MEGA_PASSWORD)

            # Fetch nodes with timeout to prevent hanging
            try:
                await asyncio.wait_for(async_api.fetchNodes(), timeout=30.0)
            except TimeoutError:
                LOGGER.error("MEGA search: fetchNodes timed out after 30 seconds")
                await edit_message(
                    search_msg,
                    "❌ MEGA node fetching timed out. Your MEGA account may have many files. Please try again.",
                )
                return

            # Additional verification - wait a bit for listener to process
            await asyncio.sleep(0.5)

            try:
                root_node_check = api.getRootNode()
                if root_node_check:
                    mega_listener.nodes_fetched = True  # Ensure flag is set
            except Exception as verify_error:
                LOGGER.warning(f"Initial node verification failed: {verify_error}")
                # Ignore verification errors - will be handled in fallback

        except Exception as fetch_error:
            if "timed out" in str(fetch_error).lower():
                await edit_message(
                    search_msg,
                    "❌ MEGA node fetching timed out. Your MEGA account may have many files. Please try again.",
                )
            else:
                await edit_message(
                    search_msg, f"❌ Failed to fetch MEGA nodes: {fetch_error!s}"
                )
            return

        # Check if node fetching actually succeeded despite temporary errors
        if mega_listener.error and not mega_listener.nodes_fetched:
            # Only treat as error if nodes weren't fetched AND there's a non-temporary error
            error_str = str(mega_listener.error).lower()
            if "error code: -1" not in error_str:
                # This is a real error, not a temporary connection issue
                await edit_message(
                    search_msg,
                    f"❌ Failed to fetch MEGA nodes: {mega_listener.error}",
                )
                return

        if not mega_listener.nodes_fetched:
            # Try to get root node as a fallback check
            try:
                root_node_test = api.getRootNode()
                if root_node_test:
                    mega_listener.nodes_fetched = True  # Manually set the flag
                # Check if we have a temporary error that should be ignored
                elif (
                    mega_listener.error
                    and "error code: -1" in str(mega_listener.error).lower()
                ):
                    # Temporary error but no root node - try one more time
                    await asyncio.sleep(2)
                    try:
                        root_node_test = api.getRootNode()
                        if root_node_test:
                            mega_listener.nodes_fetched = True
                        else:
                            await edit_message(
                                search_msg,
                                "❌ Failed to fetch MEGA nodes after retry",
                            )
                            return
                    except Exception:
                        await edit_message(
                            search_msg,
                            "❌ Failed to fetch MEGA nodes after retry",
                        )
                        return
                else:
                    await edit_message(search_msg, "❌ Failed to fetch MEGA nodes")
                    return
            except Exception as e:
                # Check if we have a temporary error that should be ignored
                if (
                    mega_listener.error
                    and "error code: -1" in str(mega_listener.error).lower()
                ):
                    # Temporary error - try one more time
                    await asyncio.sleep(2)
                    try:
                        root_node_test = api.getRootNode()
                        if root_node_test:
                            mega_listener.nodes_fetched = True
                        else:
                            await edit_message(
                                search_msg, f"❌ Failed to fetch MEGA nodes: {e}"
                            )
                            return
                    except Exception as retry_e:
                        await edit_message(
                            search_msg,
                            f"❌ Failed to fetch MEGA nodes: {retry_e}",
                        )
                        return
                else:
                    await edit_message(
                        search_msg, f"❌ Failed to fetch MEGA nodes: {e}"
                    )
                    return

        # Perform search
        try:
            root_node = api.getRootNode()
            if not root_node:
                LOGGER.error("MEGA search: Could not get root node")
                await edit_message(
                    search_msg, "❌ Could not access MEGA root folder"
                )
                return

            # MEGA search returns results directly, not through listener
            # Update search message to show progress
            await edit_message(
                search_msg,
                f"🔍 Searching MEGA drive for: <code>{self.query}</code>\n\n"
                "🔄 Searching through files and folders...",
            )

            # Try different search methods as MEGA SDK can be inconsistent
            # Method 1: Try the standard search with recursive flag
            try:
                node_list = await sync_to_async(
                    api.search, root_node, self.query, True
                )
            except Exception as e:
                LOGGER.warning(f"MEGA search: Method 1 failed: {e}")
                node_list = None

            # Method 2: If standard search fails, try without recursive flag
            if not node_list or (
                hasattr(node_list, "size") and node_list.size() == 0
            ):
                try:
                    node_list = await sync_to_async(
                        api.search, root_node, self.query
                    )
                except Exception as e:
                    LOGGER.warning(f"MEGA search: Method 2 failed: {e}")
                    node_list = None

            # Method 3: If both fail, try manual traversal search
            if not node_list or (
                hasattr(node_list, "size") and node_list.size() == 0
            ):
                node_list = await self._manual_search(api, root_node, self.query)

            if node_list and hasattr(node_list, "size") and node_list.size() > 0:
                for i in range(node_list.size()):
                    node = node_list.get(i)
                    if node:
                        self.results.append(node)
            elif isinstance(node_list, list) and len(node_list) > 0:
                # Handle case where manual search returns a list
                for node in node_list:
                    if node:
                        self.results.append(node)

            if not self.results:
                await edit_message(
                    search_msg,
                    f"🔍 Search completed for: <code>{self.query}</code>\n\n"
                    "❌ No results found.",
                )
                return

            # Display all results like Google Drive search
            await self.display_all_results(search_msg, api)

        except Exception as e:
            LOGGER.error(f"MEGA search error: {e}")
            await edit_message(search_msg, f"❌ Search failed: {e!s}")
        finally:
            if api and mega_listener:
                api.removeListener(mega_listener)

    async def display_all_results(self, message, api):
        """Display all search results like Google Drive search using Telegraph"""
        total_results = len(self.results)

        # Build HTML content for Telegraph (similar to Google Drive search)
        telegraph_content = []
        msg = f"<h4>🔍 MEGA Search Results for: {self.query}</h4><br>"
        msg += f"📊 Found <b>{total_results}</b> results<br><br>"

        contents_no = 0

        for i, node in enumerate(self.results):
            try:
                name = node.getName() or f"Unknown_{i}"
                size = node.getSize()
                is_folder = node.isFolder()

                # Get public link
                link = None
                try:
                    if node.isExported():
                        link = node.getPublicLink()
                    else:
                        # Try to export the node for public access
                        await sync_to_async(api.exportNode, node)
                        # Wait a bit for export to complete
                        await asyncio.sleep(0.5)
                        link = node.getPublicLink()
                except Exception as link_error:
                    LOGGER.warning(
                        f"Could not get public link for {name}: {link_error}"
                    )
                    # Try to get a direct download link if possible
                    try:
                        link = await sync_to_async(api.getNodePath, node)
                        if link:
                            link = f"MEGA Path: {link}"
                    except Exception:
                        pass

                if is_folder:
                    msg += f"📁 <code>{name}<br>(folder)</code><br>"
                    if link:
                        msg += f"<b><a href='{link}'>MEGA Link</a></b>"
                    else:
                        msg += "<b>Link not available</b>"
                else:
                    size_str = get_readable_file_size(size)
                    msg += f"📄 <code>{name}<br>({size_str})</code><br>"
                    if link:
                        msg += f"<b><a href='{link}'>MEGA Link</a></b>"
                    else:
                        msg += "<b>Link not available</b>"

                msg += "<br><br>"
                contents_no += 1

                # Split into multiple Telegraph pages if content gets too long (like Google Drive)
                if len(msg.encode("utf-8")) > 39000:
                    telegraph_content.append(msg)
                    msg = ""

            except Exception as e:
                LOGGER.error(f"Error processing MEGA search result {i}: {e}")
                msg += f"❌ Error processing result {i + 1}<br><br>"

        # Add remaining content
        if msg != "":
            telegraph_content.append(msg)

        # Create Telegraph page(s) and display like Google Drive search
        if telegraph_content:
            try:
                button = await get_telegraph_list(telegraph_content)
                result_msg = f"<b>🔍 Found {contents_no} MEGA results for <i>{self.query}</i></b>"
                await edit_message(message, result_msg, button)
            except Exception as e:
                LOGGER.error(f"Error creating Telegraph page: {e}")
                # Fallback to simple text display
                simple_msg = f"🔍 <b>MEGA Search Results for:</b> <code>{self.query}</code>\n\n"
                simple_msg += f"📊 Found <b>{contents_no}</b> results\n\n"
                simple_msg += "❌ Could not create detailed view. Please try again."
                await edit_message(message, simple_msg)
        else:
            await edit_message(
                message, f"❌ No results found for <i>{self.query}</i>"
            )


# Pagination callbacks removed - MEGA search now shows all results like Google Drive


async def mega_search_command(_, message):
    """
    MEGA Search command handler

    Search through the entire MEGA drive and provide download links
    """
    # Check if MEGA operations are enabled
    if not Config.MEGA_ENABLED:
        await send_message(
            message, "❌ MEGA.nz operations are disabled by the administrator."
        )
        return

    # Check if MEGA search is enabled
    if not Config.MEGA_SEARCH_ENABLED:
        await send_message(
            message, "❌ MEGA search is disabled by the administrator."
        )
        return

    # Parse command
    text = message.text.split()

    if len(text) < 2:
        # Show help message
        help_text = (
            "🔍 <b>MEGA Search Help</b>\n\n"
            "<b>Usage:</b> <code>/megasearch query</code>\n\n"
            "<b>Description:</b>\n"
            "Search through your entire MEGA drive for files and folders.\n"
            "Returns direct MEGA download links for found items.\n\n"
            "<b>Examples:</b>\n"
            "• <code>/megasearch movie</code> - Search for files containing 'movie'\n"
            "• <code>/megasearch .mp4</code> - Search for MP4 files\n"
            "• <code>/megasearch folder_name</code> - Search for specific folder\n\n"
            "<b>Note:</b> You need MEGA credentials configured to use this feature."
        )

        msg = await send_message(message, help_text)
        await delete_links(message)
        await auto_delete_message(msg, time=300)  # Auto-delete after 5 minutes
        return

    # Get search query
    query = " ".join(text[1:])

    # Create search handler and start search
    search_handler = MegaSearchHandler(message, query)

    # Delete the command message first
    await delete_links(message)

    # Start the search with proper task management
    try:
        await search_handler.search()
    except Exception as e:
        LOGGER.error(f"MEGA search error: {e}")
        await send_message(message, f"❌ MEGA search failed: {e}")
