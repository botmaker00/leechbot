import hashlib
import importlib.util
import re
import time
from asyncio import CancelledError, create_task, gather, sleep

# Import from pyrogram - Electrogram maintains the same import structure
from pyrogram.errors import PeerIdInvalid
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

# Check if MessagesFilter is available (it is in Electrogram and newer Pyrogram versions)
try:
    from pyrogram.enums import MessagesFilter

    MESSAGES_FILTER_AVAILABLE = True
except ImportError:
    MESSAGES_FILTER_AVAILABLE = False

# Check if we're using Electrogram (package name is electrogram but imports are from pyrogram)
USING_ELECTROGRAM = importlib.util.find_spec("electrogram") is not None

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    edit_message,
    send_message,
)

# Create a module-specific logger
MEDIA_LOGGER = LOGGER.getChild("media_search")
MEDIA_LOGGER.setLevel("WARNING")  # Only show warnings and errors

# Import for ID generation


# Simple encryption/obfuscation functions using built-in libraries
def get_encryption_key():
    """Get encryption key based on bot token."""
    if not hasattr(Config, "BOT_TOKEN"):
        # Fallback to a default key if BOT_TOKEN is not available
        return hashlib.sha256(b"default_encryption_key").digest()
    return hashlib.sha256(Config.BOT_TOKEN.encode()).digest()


# Cache for media IDs to avoid sending full IDs in callback data
MEDIA_ID_CACHE = {}
MEDIA_ID_COUNTER = 0


def encrypt_data(data_string):
    """Create an ultra-compact token for data.

    Instead of encrypting the full data, we store it in a cache and just
    return a short reference ID that can be used to look up the data later.
    """
    global MEDIA_ID_COUNTER
    try:
        # Check if this data is already in the cache
        for key, value in MEDIA_ID_CACHE.items():
            if value == data_string:
                return key

        # Generate a new short ID
        MEDIA_ID_COUNTER += 1
        short_id = f"m{MEDIA_ID_COUNTER}"

        # Store in cache
        MEDIA_ID_CACHE[short_id] = data_string

        # Clean up cache if it gets too large (keep last 1000 entries)
        if len(MEDIA_ID_CACHE) > 1000:
            # Get oldest keys (first 100)
            oldest_keys = list(MEDIA_ID_CACHE.keys())[:100]
            for key in oldest_keys:
                del MEDIA_ID_CACHE[key]

        return short_id
    except Exception as e:
        MEDIA_LOGGER.error(f"ID generation error: {e}")
        # Return a fallback ID
        return f"m{int(time.time())}"


def decrypt_data(short_id):
    """Get the original data from the short ID."""
    try:
        # Look up the data in the cache
        if short_id in MEDIA_ID_CACHE:
            return MEDIA_ID_CACHE[short_id]

        # If not found, return the ID itself (fallback)
        MEDIA_LOGGER.warning(f"ID not found in cache: {short_id}")
        return short_id
    except Exception as e:
        MEDIA_LOGGER.error(f"ID lookup error: {e}")
        # Return the ID itself as fallback
        return short_id


# Cache for valid chat IDs to avoid repeated errors
# Using LRU cache pattern with size limits to prevent memory leaks
class LRUCache:
    """LRU Cache implementation with size limit and expiration to prevent memory leaks."""

    def __init__(self, max_size=100, expiry_seconds=3600):
        self.cache = {}  # {key: (value, timestamp)}
        self.max_size = max_size
        self.access_order = []
        self.expiry_seconds = expiry_seconds

    def _is_expired(self, timestamp):
        """Check if a cache entry has expired."""
        if self.expiry_seconds <= 0:  # No expiration
            return False
        return (time.time() - timestamp) > self.expiry_seconds

    def get(self, key):
        """Get a value from the cache."""
        if key not in self.cache:
            return None
        value, timestamp = self.cache[key]
        if self._is_expired(timestamp):
            # Remove expired entry
            self.cache.pop(key)
            self.access_order.remove(key)
            return None
        # Update access order
        self.access_order.remove(key)
        self.access_order.append(key)
        return value

    def put(self, key, value):
        """Add a value to the cache."""
        # If key exists, update it
        if key in self.cache:
            self.access_order.remove(key)
        # If cache is full, remove least recently used item
        elif len(self.cache) >= self.max_size:
            lru_key = self.access_order.pop(0)
            self.cache.pop(lru_key)
        # Add new item
        self.cache[key] = (value, time.time())
        self.access_order.append(key)

    def contains(self, key):
        """Check if a key exists in the cache."""
        if key not in self.cache:
            return False
        _, timestamp = self.cache[key]
        if self._is_expired(timestamp):
            # Remove expired entry
            self.cache.pop(key)
            self.access_order.remove(key)
            return False
        return True


# Cache for search results to avoid redundant searches
SEARCH_RESULTS_CACHE = LRUCache(
    max_size=20, expiry_seconds=300
)  # 5 minutes expiry for search results

# Cache for valid chat IDs to avoid repeated errors
VALID_CHAT_IDS = {
    "user": LRUCache(max_size=100, expiry_seconds=3600),  # 1 hour expiry
    "bot": LRUCache(max_size=100, expiry_seconds=3600),  # 1 hour expiry
}

# Cache for media information (for start command access)
MEDIA_INFO_CACHE = LRUCache(max_size=500, expiry_seconds=3600)  # 1 hour expiry


def generate_search_key(chat_id, query, client_type, media_type="all"):
    """Generate a unique key for caching search results."""
    key = f"{chat_id}_{query}_{client_type}_{media_type}"
    return hashlib.md5(key.encode()).hexdigest()


async def validate_chat_id(client, chat_id, client_type):
    """Validate if a chat ID is accessible by the client."""
    # Ensure chat_id is an integer
    try:
        if isinstance(chat_id, str):
            chat_id = int(chat_id.strip())
        elif not isinstance(chat_id, int):
            VALID_CHAT_IDS[client_type].put(chat_id, False)
            return False
    except (ValueError, TypeError):
        VALID_CHAT_IDS[client_type].put(chat_id, False)
        return False

    # Check cache first
    if VALID_CHAT_IDS[client_type].contains(chat_id):
        return VALID_CHAT_IDS[client_type].get(chat_id)

    # Not in cache, validate
    try:
        await client.get_chat(chat_id)
        VALID_CHAT_IDS[client_type].put(chat_id, True)
        return True
    except Exception:
        VALID_CHAT_IDS[client_type].put(chat_id, False)
        return False


async def search_media_in_chat(
    client,
    chat_id: int,
    query: str,
    offset: int = 0,
    limit: int = 20,
    client_type: str = "user",
    media_type: str = "all",
) -> tuple[list[Message], bool, Exception | None]:
    """Search for media in a specific chat using the provided client.

    This function attempts to use the most efficient search method available based on the client type.
    For user clients, it uses the search_messages API directly.
    For bot clients, it attempts to use search capabilities if available, or falls back to manual filtering.

    Args:
        client: The Telegram client to use for searching
        chat_id: The chat ID to search in
        query: The search query
        offset: The offset for pagination
        limit: The maximum number of results to return
        client_type: The type of client ("user" or "bot")
        media_type: The type of media to search for ("all", "audio", "video", "photo", "document")

    Returns:
        A tuple containing (messages, has_more, error)
    """
    # Validate if the chat is accessible
    if not await validate_chat_id(client, chat_id, client_type):
        return (
            [],
            False,
            PeerIdInvalid(
                f"Chat {chat_id} is not accessible by {client_type} client"
            ),
        )

    # Check cache for existing results
    cache_key = generate_search_key(chat_id, query, client_type, media_type)
    cached_result = SEARCH_RESULTS_CACHE.get(cache_key)
    if cached_result is not None:
        MEDIA_LOGGER.info(f"Using cached search results for {query} in {chat_id}")
        return cached_result

    try:
        # Try to use search_messages if available (works with Electrogram and newer Pyrogram versions)
        try:
            # Check if we're using Electrogram or if MessagesFilter is available in Pyrogram
            if USING_ELECTROGRAM or MESSAGES_FILTER_AVAILABLE:
                MEDIA_LOGGER.info(
                    f"Using {'Electrogram' if USING_ELECTROGRAM else 'Pyrogram'} MessagesFilter"
                )

                # Determine which filter to use based on media_type
                filter_to_use = None
                if media_type == "audio":
                    filter_to_use = MessagesFilter.AUDIO
                elif media_type == "video":
                    filter_to_use = MessagesFilter.VIDEO
                elif media_type == "photo":
                    filter_to_use = MessagesFilter.PHOTO
                elif media_type == "document":
                    filter_to_use = MessagesFilter.DOCUMENT
                elif media_type == "all":
                    # For "all", we'll search each type separately below
                    filter_to_use = None
                else:
                    # For any other value, default to document (most common)
                    filter_to_use = MessagesFilter.DOCUMENT

            # Use search_messages with appropriate filter
            messages = []

            # Check if this is a bot client - some bots can search messages in newer API versions
            can_search = True
            if client_type == "bot":
                # Test if bot can search messages
                try:
                    # Try a minimal search to see if it works
                    test_msg = None
                    async for msg in client.search_messages(
                        chat_id=chat_id, limit=1
                    ):
                        test_msg = msg
                        break

                    if test_msg is None:
                        # If no message was found, it might be because the chat is empty
                        # or the bot doesn't have search capabilities
                        # Let's assume it's the latter to be safe
                        can_search = False
                except Exception:
                    can_search = False

            if not can_search and client_type == "bot":
                return (
                    [],
                    False,
                    Exception("BOT_METHOD_INVALID: This bot cannot search messages"),
                )

            # Try to use offset if supported
            try:
                if filter_to_use:
                    # Search with specific media filter
                    async for msg in client.search_messages(
                        chat_id=chat_id,
                        query=query,  # Search query in captions/titles
                        filter=filter_to_use,
                        offset=offset,
                        limit=limit,
                    ):
                        # Additional check to improve matching
                        if await _check_media_match_advanced(msg, query, media_type):
                            messages.append(msg)

                        if len(messages) >= limit:
                            break
                else:
                    # Search all media types
                    media_filters = [
                        MessagesFilter.AUDIO,
                        MessagesFilter.VIDEO,
                        MessagesFilter.PHOTO,
                        MessagesFilter.DOCUMENT,
                    ]

                    # For each media type, search separately
                    for media_filter in media_filters:
                        async for msg in client.search_messages(
                            chat_id=chat_id,
                            query=query,
                            filter=media_filter,
                            offset=offset,
                            limit=limit
                            // len(media_filters),  # Divide limit among media types
                        ):
                            # Additional check to improve matching
                            if await _check_media_match_advanced(msg, query, "all"):
                                messages.append(msg)

                            if len(messages) >= limit:
                                break

                        if len(messages) >= limit:
                            break

                has_more = len(messages) == limit  # Might have more
                result = (messages, has_more, None)
                # Cache the result
                SEARCH_RESULTS_CACHE.put(cache_key, result)
                return result
            except Exception as e:
                MEDIA_LOGGER.error(f"Error using search_messages with offset: {e}")

                # Try without offset
                messages = []
                if filter_to_use:
                    async for msg in client.search_messages(
                        chat_id=chat_id,
                        query=query,
                        filter=filter_to_use,
                        limit=limit,
                    ):
                        # Additional check to improve matching
                        if await _check_media_match_advanced(msg, query, media_type):
                            messages.append(msg)

                        if len(messages) >= limit:
                            break
                else:
                    # Search all media types
                    media_filters = [
                        MessagesFilter.AUDIO,
                        MessagesFilter.VIDEO,
                        MessagesFilter.PHOTO,
                        MessagesFilter.DOCUMENT,
                    ]

                    for media_filter in media_filters:
                        async for msg in client.search_messages(
                            chat_id=chat_id,
                            query=query,
                            filter=media_filter,
                            limit=limit // len(media_filters),
                        ):
                            # Additional check to improve matching
                            if await _check_media_match_advanced(msg, query, "all"):
                                messages.append(msg)

                            if len(messages) >= limit:
                                break

                        if len(messages) >= limit:
                            break

                has_more = len(messages) == limit  # Might have more
                result = (messages, has_more, None)
                # Cache the result
                SEARCH_RESULTS_CACHE.put(cache_key, result)
                return result

        except (ImportError, AttributeError) as e:
            MEDIA_LOGGER.error(
                f"MessagesFilter not available, falling back to manual search: {e}"
            )

            # If search_messages or MessagesFilter is not available, fall back to get_chat_history
            # Get recent messages and filter manually
            messages = []
            try:
                # Try with get_chat_history which is more likely to be available
                async for msg in client.get_chat_history(
                    chat_id, limit=limit * 10
                ):  # Increased limit for better results
                    # Check if the message contains media of the requested type and matches the query
                    if await _is_media_of_type(
                        msg, media_type
                    ) and await _check_media_match_advanced(msg, query, media_type):
                        messages.append(msg)
                        if len(messages) >= limit:
                            break
            except Exception as e:
                MEDIA_LOGGER.error(f"Error in get_chat_history: {e}")
                return [], False, e

            has_more = len(messages) == limit  # Might have more
            result = (messages, has_more, None)
            # Cache the result
            SEARCH_RESULTS_CACHE.put(cache_key, result)
            return result

    except Exception as e:
        MEDIA_LOGGER.error(f"Error searching in chat {chat_id}: {e}")
        return [], False, e


async def _is_media_of_type(msg, media_type):
    """Check if a message contains media of the specified type.

    Args:
        msg: The message to check
        media_type: The type of media to check for ("all", "audio", "video", "photo", "document")

    Returns:
        True if the message contains media of the specified type, False otherwise
    """
    if media_type == "all":
        return (
            (hasattr(msg, "audio") and msg.audio)
            or (hasattr(msg, "video") and msg.video)
            or (hasattr(msg, "photo") and msg.photo)
            or (hasattr(msg, "document") and msg.document)
        )

    if media_type == "audio":
        return hasattr(msg, "audio") and msg.audio

    if media_type == "video":
        return hasattr(msg, "video") and msg.video

    if media_type == "photo":
        return hasattr(msg, "photo") and msg.photo

    if media_type == "document":
        return hasattr(msg, "document") and msg.document

    return False


async def _check_media_match_advanced(msg, query, _):
    """Advanced check if a message matches the query based on its content and metadata.

    This function implements a more sophisticated matching algorithm that considers
    various message properties and applies different matching strategies.

    Args:
        msg: The message to check
        query: The search query
        _: Unused parameter (kept for backward compatibility)

    Returns:
        True if the message matches the query, False otherwise
    """
    if not query:
        return True  # Empty query matches everything

    query_lower = query.lower()
    query_words = query_lower.split()

    # Check caption first (applies to all media types)
    caption = (msg.caption or "").lower()
    if caption and (
        query_lower in caption
        or any(word in caption for word in query_words)
        or _fuzzy_match(query_lower, caption)
    ):
        return True

    # Check media-specific properties
    if hasattr(msg, "audio") and msg.audio:
        # Audio file - check title, performer, filename
        audio = msg.audio
        title = (getattr(audio, "title", "") or "").lower()
        performer = (getattr(audio, "performer", "") or "").lower()
        file_name = (getattr(audio, "file_name", "") or "").lower()

        # Check for exact matches
        if (
            (title and query_lower in title)
            or (performer and query_lower in performer)
            or (file_name and query_lower in file_name)
        ):
            return True

        # Check for word boundary matches
        for field in [title, performer, file_name]:
            if field and any(word in field for word in query_words):
                return True

        # Check for fuzzy matches
        if (
            _fuzzy_match(query_lower, title)
            or _fuzzy_match(query_lower, performer)
            or _fuzzy_match(query_lower, file_name)
        ):
            return True

    elif hasattr(msg, "video") and msg.video:
        # Video file - check filename
        video = msg.video
        file_name = (getattr(video, "file_name", "") or "").lower()

        # Check for exact matches
        if file_name and query_lower in file_name:
            return True

        # Check for word boundary matches
        if file_name and any(word in file_name for word in query_words):
            return True

        # Check for fuzzy matches
        if _fuzzy_match(query_lower, file_name):
            return True

    elif hasattr(msg, "document") and msg.document:
        # Document file - check filename
        document = msg.document
        file_name = (getattr(document, "file_name", "") or "").lower()

        # Check for exact matches
        if file_name and query_lower in file_name:
            return True

        # Check for word boundary matches
        if file_name and any(word in file_name for word in query_words):
            return True

        # Check for fuzzy matches
        if _fuzzy_match(query_lower, file_name):
            return True

    # For photos, we already checked the caption which is the main searchable content

    return False


def _fuzzy_match(query, text):
    """Perform a fuzzy match between query and text.

    This is a simple implementation that checks if all characters in the query
    appear in the same order in the text, allowing for other characters in between.

    Args:
        query: The search query
        text: The text to search in

    Returns:
        True if there's a fuzzy match, False otherwise
    """
    if not query or not text:
        return False

    # Simple character-by-character matching
    i, j = 0, 0
    while i < len(query) and j < len(text):
        if query[i] == text[j]:
            i += 1
        j += 1

    # If we've gone through all characters in the query, it's a match
    return i == len(query)


async def _check_media_match(query, *fields):
    """Check if query matches any of the provided fields using multiple matching strategies.

    Args:
        query: The search query
        *fields: The fields to check against (title, performer, filename, caption, etc.)

    Returns:
        True if there's a match, False otherwise
    """
    query_lower = query.lower()
    query_words = query_lower.split()

    for field in fields:
        if not field:
            continue

        # Check for exact matches
        if query_lower in field:
            return True

        # Check for word boundary matches
        for word in field.split():
            word = word.lower()
            if query_lower in word or any(q in word for q in query_words):
                return True

        # Check for substring matches
        if any(q in field for q in query_words):
            return True

    return False


async def update_search_status(message, query, total_chats):
    """Update the search status message with an animation to show progress."""
    animation_chars = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
    i = 0

    try:
        while True:
            await edit_message(
                message,
                f"<b>Searching for:</b> <code>{query}</code>\n\n"
                f"<b>Status:</b> Searching in {total_chats} channels {animation_chars[i % len(animation_chars)]}",
            )
            i += 1
            await sleep(0.5)
    except CancelledError:
        # Task was cancelled, which is expected
        pass
    except Exception as e:
        MEDIA_LOGGER.error(f"Error in update_search_status: {e}")


@new_task
async def media_search(_, message: Message):
    """Handle the media search command.

    This function allows users to search for media in configured channels.
    Users can either provide the search query directly with the command or
    reply to a message containing the search query.
    """
    # Check if media search is enabled
    if not Config.MEDIA_SEARCH_ENABLED:
        error_msg = await send_message(
            message,
            "❌ Media search is disabled by the administrator.",
        )
        create_task(
            auto_delete_message(error_msg, message, time=300),
        )  # Auto-delete after 5 minutes
        return

    user_id = message.from_user.id

    # Store original command message for later deletion
    cmd_message = message

    # Check if replying to a message
    reply_to = message.reply_to_message

    # Get query from command or reply
    query = ""
    if reply_to and reply_to.text:
        # Get query from replied message
        query = reply_to.text.strip()
    else:
        # Parse command arguments
        args = message.text.split(" ", 1)
        if len(args) > 1:
            query = args[1].strip()

    # Check if query is empty
    if not query:
        error_msg = await send_message(
            message,
            "Please provide a search query or reply to a message containing the query.",
        )
        # Delete error message after 5 minutes
        _ = create_task(auto_delete_message(error_msg, time=300))
        # Delete command message after 5 minutes
        _ = create_task(auto_delete_message(cmd_message, time=300))
        return

    # Extract media type from query if specified with format: type:query
    media_type = "all"
    if ":" in query and query.split(":", 1)[0] in [
        "audio",
        "video",
        "photo",
        "document",
        "all",
    ]:
        media_type, query = query.split(":", 1)
        query = query.strip()

    # Send initial processing message
    status_msg = await send_message(
        message, f"<b>Searching for:</b> <code>{query}</code> (Type: {media_type})"
    )

    # Get media search channels from config
    media_channels = Config.MEDIA_SEARCH_CHATS
    if not media_channels:
        await edit_message(
            status_msg,
            "No media search channels configured. Please add channels to MEDIA_SEARCH_CHATS in config.",
        )
        # Delete error message after 5 minutes
        _ = create_task(auto_delete_message(status_msg, time=300))
        # Delete command message after 5 minutes
        _ = create_task(auto_delete_message(cmd_message, time=300))
        # Delete reply message after 5 minutes if it exists
        if reply_to:
            _ = create_task(auto_delete_message(reply_to, time=300))
        return

    # Store task ID for tracking
    task_id = f"{user_id}_{int(time.time())}"

    # Initialize search tasks list
    search_tasks = []

    # Initialize error lists
    bot_errors = []

    # Function to process search results with caching and optimized processing
    async def process_search_results(client, chat_id, client_type):
        results = []
        try:
            # Generate a cache key for this specific search task
            task_cache_key = f"task_{generate_search_key(chat_id, query, client_type, media_type)}"
            cached_results = SEARCH_RESULTS_CACHE.get(task_cache_key)
            if cached_results is not None:
                MEDIA_LOGGER.info(f"Using cached search results for task {task_id}")
                return cached_results

            # Validate chat ID first
            if not await validate_chat_id(client, chat_id, client_type):
                if client_type == "bot":
                    bot_errors.append(f"Chat {chat_id}: Not accessible")
                # Cache negative result to avoid repeated validation
                SEARCH_RESULTS_CACHE.put(task_cache_key, results)
                return results

            # For bot clients, we know search will fail, so add a specific error
            if client_type == "bot":
                bot_errors.append(
                    f"Chat {chat_id}: BOT_METHOD_INVALID - Bots cannot search messages"
                )
                # Cache negative result
                SEARCH_RESULTS_CACHE.put(task_cache_key, results)
                return results

            # For user clients, attempt the search
            messages, _, error = await search_media_in_chat(
                client,
                chat_id,
                query,
                client_type=client_type,
                media_type=media_type,
            )
            if error:
                # Log the error for debugging
                MEDIA_LOGGER.error(f"Error searching in chat {chat_id}: {error}")
                if client_type == "bot":
                    bot_errors.append(f"Chat {chat_id}: {error!s}")
                # Cache negative result
                SEARCH_RESULTS_CACHE.put(task_cache_key, results)
                return results

            # Process the messages
            for msg in messages:
                # Get media type and metadata
                media_info = await get_media_info(msg)
                if not media_info:
                    continue

                (
                    media_type_found,
                    title,
                    performer,
                    duration,
                    file_size,
                    file_id,
                    relevance,
                ) = media_info

                # Skip if media type doesn't match the requested type (unless "all" is requested)
                if media_type not in ("all", media_type_found):
                    continue

                results.append(
                    {
                        "chat_id": chat_id,
                        "message_id": msg.id,
                        "title": title,
                        "performer": performer,
                        "duration": duration,
                        "file_size": file_size,
                        "file_id": file_id,
                        "client": client_type,
                        "relevance": relevance,
                        "media_type": media_type_found,
                    }
                )

                # Limit results per chat
                if len(results) >= 5:  # Reduced from 10 to 5 for faster response
                    break

            # Cache the results for this task
            SEARCH_RESULTS_CACHE.put(task_cache_key, results)
            return results
        except Exception as e:
            MEDIA_LOGGER.error(
                f"Error in process_search_results for {client_type} client: {e}"
            )
            # Cache the error result to avoid repeated failures
            SEARCH_RESULTS_CACHE.put(task_cache_key, [])
            return []

    # Create search tasks - always use user client for searching since bots cannot search messages
    user_client_available = False

    if TgClient.user:
        # User client can search messages
        # Searching channels using user client
        search_tasks = [
            process_search_results(TgClient.user, chat_id, "user")
            for chat_id in media_channels
        ]
        user_client_available = True
    elif Config.USER_SESSION_STRING:
        # Try using USER_SESSION_STRING as fallback
        try:
            from pyrogram import Client

            user_client = Client(
                "user_session_search",
                Config.TELEGRAM_API,
                Config.TELEGRAM_HASH,
                session_string=Config.USER_SESSION_STRING,
                no_updates=True,
            )
            await user_client.start()
            LOGGER.info("Using USER_SESSION_STRING for media search")

            search_tasks = [
                process_search_results(user_client, chat_id, "user_session")
                for chat_id in media_channels
            ]
            user_client_available = True

            # Note: user_client cleanup will be handled after search completion

        except Exception as user_error:
            LOGGER.warning(
                f"Failed to use USER_SESSION_STRING for media search: {user_error}"
            )
            user_client_available = False

    if not user_client_available and TgClient.bot:
        # Only use bot client if user client is not available (will likely fail for searching)
        # Add warning to status message
        await edit_message(
            status_msg,
            f"<b>Searching for:</b> <code>{query}</code> (Type: {media_type})\n\n"
            "⚠️ <b>Warning:</b> User client not available. Bots cannot search messages.\n"
            "Media search may not work properly. Please add a user session for better results.",
        )

        # Even though bot client will likely fail for searching, try it as a last resort
        search_tasks = [
            process_search_results(TgClient.bot, chat_id, "bot")
            for chat_id in media_channels
        ]

    # Record start time for performance measurement
    search_start_time = time.time()

    # Update status message to show searching animation
    search_status_task = create_task(
        update_search_status(status_msg, query, len(media_channels))
    )

    # Execute all search tasks concurrently
    all_results = []
    try:
        # Wait for all search tasks to complete
        search_results = await gather(*search_tasks)

        # Cancel the status update task
        search_status_task.cancel()

        # Combine all results
        for results in search_results:
            all_results.extend(results)

        # Sort results by relevance (higher is better)
        all_results.sort(key=lambda x: x["relevance"], reverse=True)

        # Limit total results
        all_results = all_results[:20]  # Limit to 20 results total

        # Calculate search time
        search_time = time.time() - search_start_time

        # Check if we found any results
        if not all_results:
            # No results found
            error_msg = "No media found matching your query."

            # Add more specific error information
            if not TgClient.user:
                error_msg += "\n\n⚠️ <b>User client is not available.</b> Bots cannot search messages in channels.\n"
                error_msg += "Please add a user session to enable media search.\n\n"
            elif TgClient.user and len(media_channels) > 0:
                # Check if any channels were successfully validated
                user_valid_channels = [
                    ch
                    for ch in media_channels
                    if VALID_CHAT_IDS["user"].contains(ch)
                    and VALID_CHAT_IDS["user"].get(ch)
                ]

                if not user_valid_channels:
                    error_msg += "\n\n⚠️ <b>None of the configured channels are accessible by the user client.</b>\n"
                    error_msg += (
                        "Please check your MEDIA_SEARCH_CHATS configuration.\n\n"
                    )

            # Add bot errors if any
            if bot_errors:
                error_msg += "\n<b>Errors:</b>\n"
                for err in bot_errors[:5]:  # Show only first 5 errors
                    error_msg += f"• {err}\n"
                if len(bot_errors) > 5:
                    error_msg += f"• ... and {len(bot_errors) - 5} more errors\n"

            await edit_message(status_msg, error_msg)

            # Delete error message after 5 minutes
            _ = create_task(auto_delete_message(status_msg, time=300))
            # Delete command message after 5 minutes
            _ = create_task(auto_delete_message(cmd_message, time=300))
            # Delete reply message after 5 minutes if it exists
            if reply_to:
                _ = create_task(auto_delete_message(reply_to, time=300))

            return

        # Process results for display
        for result in all_results:
            # Format title/filename for display
            display_name = (
                result["title"] or f"File: {result.get('file_name', 'Unknown')}"
            )
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."

            # Add performer info for audio
            if result["media_type"] == "audio" and result["performer"]:
                performer = result["performer"]
                if len(performer) > 15:
                    performer = performer[:12] + "..."
                display_name = f"{display_name} - {performer}"

            # Format the button text based on media type
            media_type_icon = {
                "audio": "🎵",
                "video": "🎬",
                "photo": "📷",
                "document": "📄",
            }.get(result["media_type"], "📁")

            # Format button text
            button_text = f"{media_type_icon} {display_name}"

            # Add to result
            result["display_name"] = button_text

        # Store results in cache for pagination
        pagination_cache_key = f"pagination_{user_id}_{int(time.time())}"
        SEARCH_RESULTS_CACHE.put(pagination_cache_key, all_results)

        # Display the first page (first 10 results)
        await display_search_results_page(
            status_msg,
            all_results,
            1,
            user_id,
            cmd_message.id,
            query,
            media_type,
            search_time,
            pagination_cache_key,
        )

    except Exception as e:
        # Cancel the status update task
        search_status_task.cancel()

        # Log the error
        MEDIA_LOGGER.error(f"Error in media_search: {e}")

        # Update status message with error
        await edit_message(
            status_msg,
            f"<b>Error searching for media:</b> {e!s}\n\nPlease try again later.",
        )

        # Delete error message after 5 minutes
        _ = create_task(auto_delete_message(status_msg, time=300))
        # Delete command message after 5 minutes
        _ = create_task(auto_delete_message(cmd_message, time=300))
        # Delete reply message after 5 minutes if it exists
        if reply_to:
            _ = create_task(auto_delete_message(reply_to, time=300))

    # Auto-delete the results menu after 5 minutes if no selection is made
    _ = create_task(auto_delete_message(status_msg, time=300))


async def perform_inline_search(
    query, media_type, media_channels, can_use_bot_client
):
    """Perform a search across all configured channels for inline search."""

    # Function to process search results
    async def process_search_results(client, chat_id, client_type):
        try:
            # Generate a cache key for this specific search task
            task_cache_key = f"inline_{generate_search_key(chat_id, query, client_type, media_type)}"
            cached_results = SEARCH_RESULTS_CACHE.get(task_cache_key)
            if cached_results is not None:
                return cached_results

            # Validate chat ID first
            if not await validate_chat_id(client, chat_id, client_type):
                # Cache negative result to avoid repeated validation
                SEARCH_RESULTS_CACHE.put(task_cache_key, [])
                return []

            # For "all", we'll search each type separately below

            # For user clients or bot clients with Electrogram, attempt the search
            messages = []
            error = None

            if media_type == "all" and (
                USING_ELECTROGRAM or MESSAGES_FILTER_AVAILABLE
            ):
                # For "all" media type with MessagesFilter available, search each type separately for better results
                media_filters = [
                    MessagesFilter.AUDIO,
                    MessagesFilter.VIDEO,
                    MessagesFilter.PHOTO,
                    MessagesFilter.DOCUMENT,
                ]

                for media_filter in media_filters:
                    try:
                        async for msg in client.search_messages(
                            chat_id=chat_id,
                            query=query,
                            filter=media_filter,
                            limit=15,  # Limit per media type
                        ):
                            messages.append(msg)

                            # Limit total results to avoid too many
                            if len(messages) >= 60:
                                break

                        if len(messages) >= 60:
                            break
                    except Exception:
                        pass
            else:
                # For specific media type or non-Electrogram clients
                messages_result, _, search_error = await search_media_in_chat(
                    client,
                    chat_id,
                    query,
                    client_type=client_type,
                    media_type=media_type,
                    limit=60,
                )
                messages = messages_result
                error = search_error

            if error:
                # Log the error for debugging
                MEDIA_LOGGER.error(f"Error searching in chat {chat_id}: {error}")
                # Cache negative result
                SEARCH_RESULTS_CACHE.put(task_cache_key, [])
                return []

            # Process the messages
            results = []
            for msg in messages:
                # Get media type and metadata - pass the query for better relevance calculation
                media_info = await get_media_info(msg, query)
                if not media_info:
                    continue

                (
                    media_type_found,
                    title,
                    performer,
                    duration,
                    file_size,
                    file_id,
                    relevance,
                ) = media_info

                # Skip if media type doesn't match the requested type (unless "all" is requested)
                if media_type not in ("all", media_type_found):
                    continue

                # Add message ID to relevance calculation (newer messages get higher relevance)
                # This assumes higher message IDs are newer messages
                if hasattr(msg, "id") and msg.id:
                    # Convert to string, get last 8 digits, convert back to int
                    # This prevents integer overflow while still giving newer messages higher relevance
                    msg_id_short = (
                        int(str(msg.id)[-8:]) if str(msg.id).isdigit() else 0
                    )
                    recency_factor = min(5, max(1, int(msg_id_short / 10000000)))
                    relevance += recency_factor

                results.append(
                    {
                        "chat_id": chat_id,
                        "message_id": msg.id,
                        "title": title,
                        "performer": performer,
                        "duration": duration,
                        "file_size": file_size,
                        "file_id": file_id,
                        "client": client_type,
                        "relevance": relevance,
                        "media_type": media_type_found,
                    }
                )

            # Cache the results for this task
            SEARCH_RESULTS_CACHE.put(task_cache_key, results)
            return results
        except Exception as e:
            MEDIA_LOGGER.error(f"Error in inline process_search_results: {e}")
            # Cache the error result to avoid repeated failures
            SEARCH_RESULTS_CACHE.put(task_cache_key, [])
            return []

    # Create search tasks for each channel
    search_tasks = []
    if can_use_bot_client:
        # If bot client can search, use it for all channels
        search_tasks = [
            process_search_results(TgClient.bot, chat_id, "bot")
            for chat_id in media_channels
        ]
    elif TgClient.user:
        # Otherwise use user client if available
        search_tasks = [
            process_search_results(TgClient.user, chat_id, "user")
            for chat_id in media_channels
        ]

    try:
        # Execute all search tasks concurrently
        search_results = await gather(*search_tasks)

        # Combine all results
        all_results = []
        for results in search_results:
            all_results.extend(results)

        # Sort results by relevance (higher is better)
        all_results.sort(key=lambda x: x["relevance"], reverse=True)

        # Remove duplicates based on file_id
        seen_file_ids = set()
        unique_results = []

        for result in all_results:
            file_id = result["file_id"]
            if file_id not in seen_file_ids:
                seen_file_ids.add(file_id)
                unique_results.append(result)

        return unique_results
    except Exception as e:
        MEDIA_LOGGER.error(f"Error in perform_inline_search: {e}")
        return []


async def get_media_info(msg, query=None):
    """Extract media information from a message.

    Args:
        msg: The message to extract media info from
        query: Optional search query to calculate relevance score

    Returns:
        A tuple containing (media_type, title, performer, duration, file_size, file_id, relevance)
        or None if no media is found
    """
    if hasattr(msg, "audio") and msg.audio:
        # Audio file
        audio = msg.audio
        title = getattr(audio, "title", "") or ""
        performer = getattr(audio, "performer", "") or ""
        duration = getattr(audio, "duration", 0) or 0
        file_size = getattr(audio, "file_size", 0) or 0
        file_id = getattr(audio, "file_id", "") or ""
        file_name = getattr(audio, "file_name", "") or ""
        mime_type = getattr(audio, "mime_type", "") or ""
        caption = getattr(msg, "caption", "") or ""

        # Calculate relevance score - audio files with title and performer are more relevant
        relevance = 10  # Base score for audio

        # Basic metadata relevance
        if title:
            relevance += 5
        if performer:
            relevance += 5
        if file_name:
            relevance += 3
        if caption:
            relevance += 4
        if duration > 0:
            relevance += min(5, duration // 60)  # Longer tracks slightly preferred

        # Query-based relevance boost
        if query:
            query_lower = query.lower()
            # Check for exact matches in different fields
            if title.lower().find(query_lower) != -1:
                relevance += 20  # Big boost for title match
            if performer.lower().find(query_lower) != -1:
                relevance += 15  # Good boost for performer match
            if file_name.lower().find(query_lower) != -1:
                relevance += 10  # Decent boost for filename match
            if caption.lower().find(query_lower) != -1:
                relevance += 12  # Good boost for caption match

            # Check for word matches (for multi-word queries)
            query_words = query_lower.split()
            if len(query_words) > 1:
                title_lower = title.lower()
                performer_lower = performer.lower()
                file_name_lower = file_name.lower()
                caption_lower = caption.lower()

                for word in query_words:
                    if word and len(word) > 2:  # Skip short words
                        if title_lower.find(word) != -1:
                            relevance += 3
                        if performer_lower.find(word) != -1:
                            relevance += 2
                        if file_name_lower.find(word) != -1:
                            relevance += 2
                        if caption_lower.find(word) != -1:
                            relevance += 2

        # Format-based relevance
        if mime_type:
            if mime_type == "audio/mpeg":  # MP3
                relevance += 3
            elif mime_type in ["audio/mp4", "audio/m4a"]:  # AAC
                relevance += 2
            elif mime_type == "audio/ogg":  # OGG
                relevance += 1

        # File size factor - prefer smaller files slightly
        if file_size > 0:
            # Smaller files get slightly higher relevance (max 3 points)
            size_factor = min(3, max(0, 3 - int(file_size / 10000000)))
            relevance += size_factor

        return "audio", title, performer, duration, file_size, file_id, relevance

    if hasattr(msg, "video") and msg.video:
        # Video file
        video = msg.video
        title = getattr(msg, "caption", "") or ""
        file_name = getattr(video, "file_name", "") or ""
        performer = ""
        duration = getattr(video, "duration", 0) or 0
        file_size = getattr(video, "file_size", 0) or 0
        file_id = getattr(video, "file_id", "") or ""
        mime_type = getattr(video, "mime_type", "") or ""
        width = getattr(video, "width", 0) or 0
        height = getattr(video, "height", 0) or 0

        # Calculate relevance score
        relevance = 8  # Base score for video

        # Basic metadata relevance
        if title:
            relevance += 5
        if file_name:
            relevance += 4
        if duration > 0:
            relevance += min(4, duration // 60)  # Longer videos slightly preferred

        # Resolution-based relevance
        if width and height:
            if width >= 1920 or height >= 1080:  # Full HD or better
                relevance += 4
            elif width >= 1280 or height >= 720:  # HD
                relevance += 3
            elif width >= 854 or height >= 480:  # SD
                relevance += 2

        # Query-based relevance boost
        if query:
            query_lower = query.lower()
            # Check for exact matches in different fields
            if title.lower().find(query_lower) != -1:
                relevance += 20  # Big boost for caption match
            if file_name.lower().find(query_lower) != -1:
                relevance += 15  # Good boost for filename match

            # Check for word matches (for multi-word queries)
            query_words = query_lower.split()
            if len(query_words) > 1:
                title_lower = title.lower()
                file_name_lower = file_name.lower()

                for word in query_words:
                    if word and len(word) > 2:  # Skip short words
                        if title_lower.find(word) != -1:
                            relevance += 3
                        if file_name_lower.find(word) != -1:
                            relevance += 2

        # Format-based relevance
        if mime_type:
            if mime_type == "video/mp4":  # MP4
                relevance += 3
            elif mime_type == "video/x-matroska":  # MKV
                relevance += 2
            elif mime_type in ["video/webm", "video/quicktime"]:  # WEBM, MOV
                relevance += 1

        # File size factor - prefer smaller files slightly
        if file_size > 0:
            # Smaller files get slightly higher relevance (max 3 points)
            size_factor = min(
                3, max(0, 3 - int(file_size / 50000000))
            )  # Higher threshold for videos
            relevance += size_factor

        return (
            "video",
            title or file_name,
            performer,
            duration,
            file_size,
            file_id,
            relevance,
        )

    if hasattr(msg, "document") and msg.document:
        # Document file
        document = msg.document
        file_name = getattr(document, "file_name", "") or ""
        title = file_name or getattr(msg, "caption", "") or ""
        performer = ""
        duration = 0
        file_size = getattr(document, "file_size", 0) or 0
        file_id = getattr(document, "file_id", "") or ""
        mime_type = getattr(document, "mime_type", "") or ""
        caption = getattr(msg, "caption", "") or ""

        # Calculate relevance score
        relevance = 5  # Base score for document

        # Basic metadata relevance
        if title:
            relevance += 4
        if caption:
            relevance += 3

        # Query-based relevance boost
        if query:
            query_lower = query.lower()
            # Check for exact matches in different fields
            if title.lower().find(query_lower) != -1:
                relevance += 18  # Big boost for title/filename match
            if caption.lower().find(query_lower) != -1:
                relevance += 15  # Good boost for caption match

            # Check for word matches (for multi-word queries)
            query_words = query_lower.split()
            if len(query_words) > 1:
                title_lower = title.lower()
                caption_lower = caption.lower()

                for word in query_words:
                    if word and len(word) > 2:  # Skip short words
                        if title_lower.find(word) != -1:
                            relevance += 3
                        if caption_lower.find(word) != -1:
                            relevance += 2

        # Format-based relevance
        if mime_type:
            if mime_type == "application/pdf":  # PDF
                relevance += 3
            elif mime_type.startswith(
                "application/vnd.openxmlformats"
            ):  # Office docs
                relevance += 2
            elif mime_type in [
                "application/zip",
                "application/x-rar-compressed",
            ]:  # Archives
                relevance += 1

        # File extension relevance
        if file_name:
            ext = file_name.split(".")[-1].lower() if "." in file_name else ""
            if ext in ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt"]:
                relevance += 2

        # File size factor - prefer smaller files slightly
        if file_size > 0:
            # Smaller files get slightly higher relevance (max 3 points)
            size_factor = min(3, max(0, 3 - int(file_size / 10000000)))
            relevance += size_factor

        return "document", title, performer, duration, file_size, file_id, relevance

    if hasattr(msg, "photo") and msg.photo:
        # Photo - in Pyrogram, msg.photo is a single Photo object, not a list
        photo = msg.photo
        caption = getattr(msg, "caption", "") or ""
        title = caption or "Photo"
        performer = ""
        duration = 0
        file_size = getattr(photo, "file_size", 0) or 0
        file_id = getattr(photo, "file_id", "") or ""
        width = getattr(photo, "width", 0) or 0
        height = getattr(photo, "height", 0) or 0

        # Calculate relevance score
        relevance = 6  # Base score for photo

        # Basic metadata relevance
        if caption:
            relevance += 5

        # Resolution-based relevance
        if width and height:
            if width >= 1920 or height >= 1080:  # High resolution
                relevance += 4
            elif width >= 1280 or height >= 720:  # Medium resolution
                relevance += 3
            elif width >= 800 or height >= 600:  # Low resolution
                relevance += 2

        # Query-based relevance boost
        if query and caption:
            query_lower = query.lower()
            # Check for exact matches in caption
            if caption.lower().find(query_lower) != -1:
                relevance += 20  # Big boost for caption match

            # Check for word matches (for multi-word queries)
            query_words = query_lower.split()
            if len(query_words) > 1:
                caption_lower = caption.lower()

                for word in query_words:
                    if word and len(word) > 2:  # Skip short words
                        if caption_lower.find(word) != -1:
                            relevance += 3

        return "photo", title, performer, duration, file_size, file_id, relevance

    return None


@new_task
async def media_get_callback(_, query):
    """Handle the media get callback.

    This function retrieves media files using the following strategy:
    1. Always use the bot client for message retrieval when available
    2. Only fall back to the user client if the bot client fails
    3. The client_type in the callback data only indicates which client found the message during search

    This approach ensures optimal performance and reliability, as bot clients are better suited
    for message retrieval, while user clients are necessary for searching functionality.
    """
    # Extract parameters from the callback data
    callback_parts = query.data.split("_")
    MEDIA_LOGGER.info(f"Callback parts: {callback_parts}")

    if len(callback_parts) < 4:
        MEDIA_LOGGER.error("Invalid callback data: Not enough parts")
        return

    # Extract user_id, cmd_message_id, and encrypted media data
    try:
        user_id = int(callback_parts[1])
        cmd_message_id = int(callback_parts[2])

        # Get the encrypted media data (everything after the third underscore)
        encrypted_data = query.data.split("_", 3)[3]

        # Decrypt the media data
        media_data = decrypt_data(encrypted_data)
        MEDIA_LOGGER.info(f"Decrypted media data: {media_data}")

        # Parse the decrypted data
        media_parts = media_data.split("_")
        chat_id = int(media_parts[0])
        message_id = int(media_parts[1])
        client_type = media_parts[2] if len(media_parts) > 2 else "bot"
    except Exception as e:
        MEDIA_LOGGER.error(f"Error parsing callback data: {e}")
        return

    # Check if the user who clicked the button is the same as the one who initiated the search
    if query.from_user.id != user_id:
        await query.answer("This search result is not for you!", show_alert=True)
        return

    # Acknowledge the callback
    await query.answer("Retrieving media...")

    # Check if this is an inline query result (query.message might be None)
    is_inline_result = query.message is None

    # If this is an inline result, we need to send a message to the user
    status_msg = None
    if is_inline_result:
        # Send a status message to the user
        status_msg = await TgClient.bot.send_message(
            chat_id=query.from_user.id, text="Retrieving media file... Please wait."
        )

    # Check if both bot and user clients are valid for this chat
    bot_client_valid = (
        TgClient.bot
        and VALID_CHAT_IDS["bot"].contains(chat_id)
        and VALID_CHAT_IDS["bot"].get(chat_id)
    )
    user_client_valid = (
        TgClient.user
        and VALID_CHAT_IDS["user"].contains(chat_id)
        and VALID_CHAT_IDS["user"].get(chat_id)
    )

    # IMPORTANT: Always use bot client for message retrieval when possible
    # Only fall back to user client if bot client fails
    client = TgClient.bot if TgClient.bot else TgClient.user
    client_type = "bot" if TgClient.bot else "user"

    # Check if the selected client is available
    if (client_type == "bot" and not TgClient.bot) or (
        client_type == "user" and not TgClient.user
    ):
        error_msg = f"The {client_type} client is not available. Please try again."
        if is_inline_result and status_msg:
            await status_msg.edit_text(error_msg)
            # Auto-delete error message after 5 minutes
            _ = create_task(auto_delete_message(status_msg, time=300))
        else:
            await query.edit_message_text(error_msg)
            # Auto-delete error message after 5 minutes
            _ = create_task(auto_delete_message(query.message, time=300))
        return

    try:
        # Try to get the message with the primary client
        message = None
        try:
            message = await client.get_messages(
                chat_id=chat_id, message_ids=message_id
            )
        except Exception as e:
            MEDIA_LOGGER.error(
                f"Error getting message with {client_type} client: {e}"
            )

        # If message not found with the selected client, try the other client as fallback
        if not message or not (
            hasattr(message, "audio")
            or hasattr(message, "video")
            or hasattr(message, "photo")
            or hasattr(message, "document")
        ):
            # Try the other client
            fallback_client = None
            fallback_client_type = None

            # Since we're now using bot client as primary, only fall back to user client if bot client fails
            if client_type == "bot" and TgClient.user and user_client_valid:
                fallback_client = TgClient.user
                fallback_client_type = "user"  # This case should rarely happen now, but keep it for completeness
            elif client_type == "user" and TgClient.bot and bot_client_valid:
                fallback_client = TgClient.bot
                fallback_client_type = "bot"

            if fallback_client:
                try:
                    message = await fallback_client.get_messages(
                        chat_id=chat_id, message_ids=message_id
                    )
                    if message:
                        MEDIA_LOGGER.info(
                            f"Successfully retrieved message with fallback {fallback_client_type} client"
                        )
                        client = fallback_client
                        client_type = fallback_client_type
                except Exception as e:
                    MEDIA_LOGGER.error(
                        f"Error getting message with fallback {fallback_client_type} client: {e}"
                    )

        # If still no message found
        if not message or not (
            hasattr(message, "audio")
            or hasattr(message, "video")
            or hasattr(message, "photo")
            or hasattr(message, "document")
        ):
            error_msg = (
                "Media file not found or no longer available.\n\n"
                "The message might have been deleted or the media file removed."
            )
            if is_inline_result and status_msg:
                await status_msg.edit_text(error_msg)
                # Auto-delete error message after 5 minutes
                _ = create_task(auto_delete_message(status_msg, time=300))
            else:
                await query.edit_message_text(error_msg)
                # Auto-delete error message after 5 minutes
                _ = create_task(auto_delete_message(query.message, time=300))
            return

        # Copy the media to the user instead of forwarding
        if is_inline_result:
            # Copy to the user's private chat
            await message.copy(query.from_user.id, disable_notification=True)
            # Do not auto-delete the actual media file
            # Delete the status message
            if status_msg:
                await status_msg.delete()
        else:
            # Copy to the chat where the query was made
            await message.copy(query.message.chat.id, disable_notification=True)
            # Do not auto-delete the actual media file
            # Delete the search results message immediately
            await query.message.delete()

            # Delete the command message immediately (if it exists)
            if cmd_message_id > 0:
                from contextlib import suppress

                with suppress(Exception):
                    await TgClient.bot.delete_messages(
                        query.message.chat.id, cmd_message_id
                    )

    except Exception:
        error_msg = "Error retrieving media\n\nPlease try again later."

        # Try to show the error message
        try:
            if is_inline_result and status_msg:
                await status_msg.edit_text(error_msg)
                # Auto-delete error message after 5 minutes
                _ = create_task(auto_delete_message(status_msg, time=300))
            else:
                await query.edit_message_text(error_msg)
                # Auto-delete error message after 5 minutes
                _ = create_task(auto_delete_message(query.message, time=300))
        except Exception:
            # If editing fails, try to answer the callback query
            from contextlib import suppress

            with suppress(Exception):
                await query.answer("Error retrieving media", show_alert=True)


@new_task
async def display_search_results_page(
    status_msg,
    all_results,
    page,
    user_id,
    cmd_message_id,
    query,
    media_type,
    search_time=None,
    pagination_cache_key=None,
):
    """Display a page of search results with pagination buttons."""
    from bot.helper.telegram_helper.button_build import ButtonMaker

    # Calculate pagination info
    total_results = len(all_results)
    results_per_page = 10
    total_pages = (total_results + results_per_page - 1) // results_per_page

    # Ensure page is within valid range
    page = max(1, min(page, total_pages))

    # Get results for the current page
    start_idx = (page - 1) * results_per_page
    end_idx = min(start_idx + results_per_page, total_results)
    page_results = all_results[start_idx:end_idx]

    # Create buttons for the current page results
    buttons = ButtonMaker()
    for result in page_results:
        # Create callback data with encrypted media info
        media_data = f"{result['chat_id']}_{result['message_id']}_{result['client']}"
        encrypted_data = encrypt_data(media_data)
        callback_data = f"medget_{user_id}_{cmd_message_id}_{encrypted_data}"

        # Add button
        buttons.data_button(result["display_name"], callback_data)

    # Add pagination buttons
    if total_pages > 1:
        # First page button
        if page > 1:
            buttons.data_button(
                "⏮️ First", f"medpage_{user_id}_{pagination_cache_key}_1", "footer"
            )

        # Previous page button
        if page > 1:
            buttons.data_button(
                "◀️ Prev",
                f"medpage_{user_id}_{pagination_cache_key}_{page - 1}",
                "footer",
            )

        # Page indicator
        buttons.data_button(
            f"📄 {page}/{total_pages}", f"medpageinfo_{user_id}", "footer"
        )

        # Next page button
        if page < total_pages:
            buttons.data_button(
                "Next ▶️",
                f"medpage_{user_id}_{pagination_cache_key}_{page + 1}",
                "footer",
            )

        # Last page button
        if page < total_pages:
            buttons.data_button(
                "Last ⏭️",
                f"medpage_{user_id}_{pagination_cache_key}_{total_pages}",
                "footer",
            )

    # Add cancel button
    buttons.data_button("❌ Cancel", f"medcancel_{user_id}", "footer")

    # Build the menu with 1 button per row for results, and pagination buttons in footer
    button_menu = buttons.build_menu(1)

    # Update status message with results and pagination
    message_text = f"<b>Found {total_results} results for:</b> <code>{query}</code> (Type: {media_type})\n"
    if search_time:
        message_text += f"<b>Search time:</b> {search_time:.2f} seconds\n"
    message_text += (
        f"\n<b>Showing results {start_idx + 1}-{end_idx} of {total_results}</b>\n"
    )
    message_text += f"<b>Page {page}/{total_pages}</b>\n\n"
    message_text += "<b>Select a media file to download:</b>"

    await edit_message(status_msg, message_text, button_menu)


@new_task
async def media_page_callback(_, query):
    """Handle pagination for media search results."""
    data = query.data.split("_")
    user_id = int(data[1])

    # Check if this is just a page info button (not clickable)
    if data[0] == "medpageinfo":
        await query.answer("Current page information", show_alert=False)
        return

    # Check if the user who clicked the button is the same as the one who initiated the search
    if query.from_user.id != user_id:
        await query.answer("This search result is not for you!", show_alert=True)
        return

    # Get pagination cache key and page number
    pagination_cache_key = data[2]
    page = int(data[3])

    # Get the cached results
    all_results = SEARCH_RESULTS_CACHE.get(pagination_cache_key)
    if not all_results:
        await query.answer(
            "Search results expired. Please search again.", show_alert=True
        )
        await query.message.delete()
        return

    # Acknowledge the callback
    await query.answer(f"Loading page {page}...")

    # Extract query and media_type from the message text
    message_text = query.message.text
    query_match = re.search(
        r"Found \d+ results for: (.*?) \(Type: (.*?)\)", message_text
    )
    if query_match:
        search_query = query_match.group(1)
        media_type = query_match.group(2)
    else:
        search_query = "Unknown"
        media_type = "all"

    # Get the command message ID from any of the existing buttons
    cmd_message_id = 0
    for row in query.message.reply_markup.inline_keyboard:
        for button in row:
            if button.callback_data.startswith("medget_"):
                cmd_message_id = int(button.callback_data.split("_")[2])
                break
        if cmd_message_id:
            break

    # Display the requested page
    await display_search_results_page(
        query.message,
        all_results,
        page,
        user_id,
        cmd_message_id,
        search_query,
        media_type,
        pagination_cache_key=pagination_cache_key,
    )


async def media_cancel_callback(_, query):
    """Handle the cancel button for media search."""
    data = query.data.split("_")
    user_id = int(data[1])

    # Check if the user who clicked the button is the same as the one who initiated the search
    if query.from_user.id != user_id:
        await query.answer("This search result is not for you!", show_alert=True)
        return

    # Delete the message
    await query.message.delete()


@new_task
async def inline_media_search(_, inline_query: InlineQuery):
    """Handle inline queries for media search.

    This allows users to search for media directly from any chat by typing @bot_username query.

    Special format for media type filtering:
    @bot_username audio:query - Search for audio files
    @bot_username video:query - Search for video files
    @bot_username photo:query - Search for photos
    @bot_username doc:query - Search for documents
    """
    # Check if media search is enabled
    if not Config.MEDIA_SEARCH_ENABLED:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="disabled",
                    title="Media search is disabled",
                    description="Media search has been disabled by the administrator",
                    input_message_content=InputTextMessageContent(
                        "Media search is currently disabled by the administrator."
                    ),
                )
            ],
            cache_time=300,
        )
        return

    # Skip empty queries
    if not inline_query.query:
        return
    # Skip authorization check for inline queries - they're public by design
    # If we need to restrict access, we can do it when the user tries to get the actual media

    # Get the query text
    query = inline_query.query.strip()

    # If query is empty, return
    if not query:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="help",
                    title="Search for media in configured channels",
                    description="Type a search query to find media files",
                    input_message_content=InputTextMessageContent(
                        "To search for media, type a query after the bot username.\n"
                        "You can also specify media type with format: type:query\n"
                        "Supported types: audio, video, photo, document, all"
                    ),
                )
            ],
            cache_time=300,
        )
        return

    # Extract media type from query if specified with format: type:query
    media_type = "all"
    if ":" in query and query.split(":", 1)[0] in [
        "audio",
        "video",
        "photo",
        "document",
        "all",
    ]:
        media_type, query = query.split(":", 1)
        query = query.strip()

    # If query is still empty after extracting media type, return
    if not query:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="help",
                    title="Please provide a search query",
                    description=f"Type {media_type}:your_query to search for {media_type} files",
                    input_message_content=InputTextMessageContent(
                        f"To search for {media_type} files, type {media_type}:your_query after the bot username"
                    ),
                )
            ],
            cache_time=5,
        )
        return

    # Get offset from inline query
    offset = inline_query.offset

    # If offset is empty, start from the beginning
    current_offset = int(offset) if offset else 0

    # Get media search channels from config
    media_channels = Config.MEDIA_SEARCH_CHATS

    if not media_channels:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="no_channels",
                    title="No media search channels configured",
                    description="Please add channels to MEDIA_SEARCH_CHATS in config",
                    input_message_content=InputTextMessageContent(
                        "No media search channels configured. Please add channels to MEDIA_SEARCH_CHATS in config."
                    ),
                )
            ],
            cache_time=60,
        )
        return

    # Check if we're using Electrogram/Pyrogram with MessagesFilter and if bot client can search
    can_use_bot_client = False

    if USING_ELECTROGRAM or MESSAGES_FILTER_AVAILABLE:
        try:
            # First, make sure the bot has joined the channel or has access to it
            try:
                # Try to get basic info about the chat to ensure the bot has access
                await TgClient.bot.get_chat(media_channels[0])

                # Test if bot can search messages
                test_msg = None
                async for msg in TgClient.bot.search_messages(
                    chat_id=media_channels[0], limit=1
                ):
                    test_msg = msg
                    break

                if test_msg is not None:
                    can_use_bot_client = True
            except Exception:
                # Bot cannot access chat or search messages
                pass
        except Exception:
            can_use_bot_client = False

    # If we can't use bot client and user client is not available, show error
    if not can_use_bot_client and not TgClient.user:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="no_user_client",
                    title="Search client not available",
                    description="Neither bot nor user client can search messages",
                    input_message_content=InputTextMessageContent(
                        "⚠️ Search client not available. Neither bot nor user client can search messages.\n"
                        "Media search may not work properly. Please add a user session for better results."
                    ),
                )
            ],
            cache_time=60,
        )
        return

    # Generate a cache key for this search
    search_cache_key = f"inline_{inline_query.from_user.id}_{media_type}_{query}"

    # Check if we have cached results for this search
    cached_results = SEARCH_RESULTS_CACHE.get(search_cache_key)

    # If we have cached results and this is a pagination request, use the cached results
    if cached_results is not None and current_offset > 0:
        all_results = cached_results
    else:
        # We need to perform a new search
        all_results = await perform_inline_search(
            query, media_type, media_channels, can_use_bot_client
        )

        # Cache the results for future pagination requests
        if all_results:
            SEARCH_RESULTS_CACHE.put(search_cache_key, all_results)

    try:
        # Store the total number of results
        total_results = len(all_results)

        # Results per page
        results_per_page = 10

        # Get results for the current page
        page_results = all_results[
            current_offset : current_offset + results_per_page
        ]

        # Calculate next offset
        next_offset = (
            str(current_offset + results_per_page)
            if current_offset + results_per_page < total_results
            else ""
        )

        # Check if we found any results
        if not all_results:
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="no_results",
                        title="No media found matching your query",
                        description=f"No {media_type} files found for: {query}",
                        input_message_content=InputTextMessageContent(
                            f"No {media_type} files found matching: {query}"
                        ),
                    )
                ],
                cache_time=30,
            )
            return

        # Format results for inline query
        inline_results = []
        for i, result in enumerate(page_results):
            # Create a unique ID for this result
            result_id = (
                f"{result['chat_id']}_{result['message_id']}_{current_offset + i}"
            )

            # Format title/filename for display
            display_title = (
                result["title"] or f"File: {result.get('file_name', 'Unknown')}"
            )

            # Truncate title if too long (Telegram has limits)
            if len(display_title) > 60:
                display_title = display_title[:57] + "..."

            # Add performer info for audio
            performer_text = ""
            if result["media_type"] == "audio" and result["performer"]:
                performer_text = result["performer"]
                if len(performer_text) > 30:
                    performer_text = performer_text[:27] + "..."
                display_title = f"{display_title} - {performer_text}"

            # Format file size for display
            size_text = ""
            if result["file_size"] > 0:
                if result["file_size"] >= 1024 * 1024 * 1024:  # GB
                    size_text = (
                        f"{result['file_size'] / (1024 * 1024 * 1024):.2f} GB"
                    )
                elif result["file_size"] >= 1024 * 1024:  # MB
                    size_text = f"{result['file_size'] / (1024 * 1024):.2f} MB"
                else:  # KB
                    size_text = f"{result['file_size'] / 1024:.2f} KB"

            # Format duration for display
            duration_text = ""
            if result["duration"] > 0:
                # Make sure duration is an integer
                duration = int(result["duration"])
                minutes = duration // 60
                seconds = duration % 60
                duration_text = f"{minutes}:{seconds:02d}"

            # Prepare caption with more details
            caption = display_title

            # Add page info to first result if there are multiple pages
            if i == 0 and total_results > results_per_page:
                current_page = (current_offset // results_per_page) + 1
                total_pages = (
                    total_results + results_per_page - 1
                ) // results_per_page
                page_info = f"Page {current_page}/{total_pages} • "
                caption = f"{page_info}{caption}"

            # Add media details to caption
            details = []
            if performer_text and result["media_type"] == "audio":
                details.append(f"Artist: {performer_text}")
            if duration_text:
                details.append(f"Duration: {duration_text}")
            if size_text:
                details.append(f"Size: {size_text}")

            if details:
                caption += "\n" + " • ".join(details)

            # Add search query info
            caption += f"\n\nSearch: {query}"

            # Create the appropriate inline result based on media type
            try:
                # Use article results instead of cached media to avoid DOCUMENT_INVALID errors
                media_type_emoji = {
                    "audio": "🎵",
                    "video": "🎬",
                    "photo": "📷",
                    "document": "📄",
                }.get(result["media_type"], "📁")

                # Create a description based on media type
                description = (
                    f"{media_type_emoji} {result['media_type'].capitalize()}"
                )
                if size_text:
                    description += f" • Size: {size_text}"
                if duration_text:
                    description += f" • Duration: {duration_text}"
                if "title" in result and result["title"] and "." in result["title"]:
                    file_ext = result["title"].split(".")[-1].upper()
                    if len(file_ext) <= 5:  # If extension is not too long
                        description += f" • Type: {file_ext}"

                # Create a switch inline query button to search again
                reply_markup = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text="🔍 Search Again",
                                switch_inline_query_current_chat="",
                            )
                        ]
                    ]
                )

                # Create a unique ID for this media (unencrypted version for cache key)
                cache_key = (
                    f"{result['chat_id']}_{result['message_id']}_{result['client']}"
                )

                # Store media information in cache for retrieval via start command
                media_info = {
                    "chat_id": result["chat_id"],
                    "message_id": result["message_id"],
                    "client_type": result["client"],
                    "media_type": result["media_type"],
                    "title": result["title"],
                    "performer": result["performer"],
                    "duration": result["duration"],
                    "file_size": result["file_size"],
                    "file_id": result["file_id"],
                }
                MEDIA_INFO_CACHE.put(cache_key, media_info)

                # Create encrypted media ID for URL
                encrypted_data = encrypt_data(cache_key)

                # Create a start command for new users instead of callback data
                # This ensures that new users who haven't interacted with the bot can still get media
                start_command = f"get_{encrypted_data}"

                # Create buttons for sending media and searching again
                reply_markup = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text=f"Send {result['media_type'].capitalize()}",
                                url=f"https://t.me/{TgClient.NAME}?start={start_command}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="🔍 Search Again",
                                switch_inline_query_current_chat="",
                            )
                        ],
                    ]
                )

                # Create a rich article result with media information
                message_text = f"{display_title}\n\n"
                if performer_text and result["media_type"] == "audio":
                    message_text += f"Artist: {performer_text}\n"
                if duration_text:
                    message_text += f"Duration: {duration_text}\n"
                if size_text:
                    message_text += f"Size: {size_text}\n"
                message_text += f"Type: {result['media_type'].capitalize()}\n\n"
                message_text += "Click the button below to get this file"

                # Create an article result with detailed information
                inline_results.append(
                    InlineQueryResultArticle(
                        id=result_id,
                        title=display_title,
                        description=description,
                        input_message_content=InputTextMessageContent(message_text),
                        reply_markup=reply_markup,
                        # Use default thumbnail based on media type
                        thumb_url=None,
                    )
                )
            except Exception as e:
                MEDIA_LOGGER.error(f"Error creating inline result: {e}")
                # Skip this result and continue with the next one

        # Pagination info is now added directly to the first result in the loop above

        try:
            # Answer the inline query with results
            await inline_query.answer(
                results=inline_results,
                cache_time=300,  # Cache for 5 minutes
                is_gallery=media_type
                in ["photo", "video"],  # Use gallery view for photos and videos
                next_offset=next_offset,  # Set the next offset for pagination
                is_personal=True,  # Results are personalized for this user
            )
        except Exception as e:
            MEDIA_LOGGER.error(f"Error answering inline query: {e}")

    except Exception as e:
        MEDIA_LOGGER.error(f"Error in inline_media_search: {e}")
        # Answer with error message
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="error",
                    title="Error searching for media",
                    description=str(e),
                    input_message_content=InputTextMessageContent(
                        f"Error searching for media: {e!s}\n\nPlease try again later."
                    ),
                )
            ],
            cache_time=5,
        )


@new_task
async def chosen_inline_result_handler(_, chosen_inline_result):
    """Handle chosen inline results for media search.

    This function is called when a user selects a result from the inline query.
    It will replace the message with the actual media file.
    """
    from asyncio import sleep

    from pyrogram.enums import ParseMode

    from bot.helper.ext_utils.status_utils import get_readable_file_size

    # Helper function to format duration
    def format_duration(seconds):
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    # Extract the result ID which contains chat_id and message_id
    result_id = chosen_inline_result.result_id

    try:
        # Parse the result ID to get chat_id and message_id
        chat_id, message_id, _ = result_id.split("_")
        chat_id = int(chat_id)
        message_id = int(message_id)

        # Get the inline message ID to edit the message later
        inline_message_id = chosen_inline_result.inline_message_id
        if not inline_message_id:
            return

        # Try to get the message with bot client first
        client = TgClient.bot if TgClient.bot else TgClient.user

        # Check if the client is available
        if not client:
            return

        try:
            # Get the message
            message = await client.get_messages(
                chat_id=chat_id, message_ids=message_id
            )

            # If message not found with bot client, try user client
            if not message and TgClient.user:
                message = await TgClient.user.get_messages(
                    chat_id=chat_id, message_ids=message_id
                )

            # If still no message found, return
            if not message:
                return

            # Check if the message contains media
            if not (
                hasattr(message, "audio")
                or hasattr(message, "video")
                or hasattr(message, "photo")
                or hasattr(message, "document")
            ):
                return

            # Determine the media type
            media_type = None
            if hasattr(message, "audio") and message.audio:
                media_type = "audio"
            elif hasattr(message, "video") and message.video:
                media_type = "video"
            elif hasattr(message, "photo") and message.photo:
                media_type = "photo"
            elif hasattr(message, "document") and message.document:
                media_type = "document"

            if not media_type:
                return

            # Use send_inline_bot_result to replace the message with the actual media
            # This is the most elegant way to handle this, but requires the bot to be
            # able to send inline results, which might not be possible for all bots

            # For now, we'll edit the message to indicate that the file is being sent
            # The actual file will be sent when the user clicks the "Send" button

            # Create a more informative message
            title = ""
            if hasattr(message, "audio") and message.audio:
                title = message.audio.title or "Audio"
                if message.audio.performer:
                    title += f" - {message.audio.performer}"
            elif hasattr(message, "video") and message.video:
                title = message.caption or "Video"
            elif hasattr(message, "document") and message.document:
                title = message.document.file_name or "Document"
            elif hasattr(message, "photo") and message.photo:
                title = message.caption or "Photo"

            # Create a unique ID for this media (unencrypted version for cache key)
            cache_key = f"{chat_id}_{message_id}_bot"

            # Extract additional media information
            performer = ""
            duration = 0
            file_size = 0
            file_id = ""

            if hasattr(message, "audio") and message.audio:
                performer = message.audio.performer or ""
                duration = message.audio.duration or 0
                file_size = message.audio.file_size or 0
                file_id = message.audio.file_id
            elif hasattr(message, "video") and message.video:
                duration = message.video.duration or 0
                file_size = message.video.file_size or 0
                file_id = message.video.file_id
            elif hasattr(message, "document") and message.document:
                file_size = message.document.file_size or 0
                file_id = message.document.file_id
            elif hasattr(message, "photo") and message.photo:
                # For photos, in Pyrogram msg.photo is a single Photo object
                if message.photo:
                    file_size = message.photo.file_size or 0
                    file_id = message.photo.file_id

            # Store media information in cache for retrieval via start command
            media_info = {
                "chat_id": chat_id,
                "message_id": message_id,
                "client_type": "bot",  # Use bot client since we're getting the message with the bot client first
                "media_type": media_type,
                "title": title,
                "performer": performer,
                "duration": duration,
                "file_size": file_size,
                "file_id": file_id,
            }
            MEDIA_INFO_CACHE.put(cache_key, media_info)

            # Create encrypted media ID for URL
            encrypted_data = encrypt_data(cache_key)

            # Create a start command for new users instead of callback data
            # This ensures that new users who haven't interacted with the bot can still get media
            start_command = f"get_{encrypted_data}"

            # Create buttons for sending media
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=f"Send {media_type.capitalize()}",
                            url=f"https://t.me/{TgClient.NAME}?start={start_command}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔍 Search Again",
                            switch_inline_query_current_chat="",
                        )
                    ],
                ]
            )

            # Edit the inline message with more details
            message_text = f"<b>{title}</b>\n\n"
            if (
                hasattr(message, "audio")
                and message.audio
                and message.audio.duration
            ):
                message_text += (
                    f"Duration: {format_duration(message.audio.duration)}\n"
                )
            elif (
                hasattr(message, "video")
                and message.video
                and message.video.duration
            ):
                message_text += (
                    f"Duration: {format_duration(message.video.duration)}\n"
                )

            if (
                hasattr(message, "audio")
                and message.audio
                and message.audio.file_size
            ):
                message_text += (
                    f"Size: {get_readable_file_size(message.audio.file_size)}\n"
                )
            elif (
                hasattr(message, "video")
                and message.video
                and message.video.file_size
            ):
                message_text += (
                    f"Size: {get_readable_file_size(message.video.file_size)}\n"
                )
            elif (
                hasattr(message, "document")
                and message.document
                and message.document.file_size
            ):
                message_text += (
                    f"Size: {get_readable_file_size(message.document.file_size)}\n"
                )
            elif (
                hasattr(message, "photo")
                and message.photo
                and message.photo.file_size
            ):
                message_text += (
                    f"Size: {get_readable_file_size(message.photo.file_size)}\n"
                )

            message_text += f"Type: {media_type.capitalize()}\n\n"
            message_text += "Click the button below to get this file"

            # Edit the inline message
            await client.edit_inline_text(
                inline_message_id=inline_message_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )

            # We can't directly delete inline messages, but we can edit them after 5 minutes
            # to indicate they've expired
            async def expire_inline_message():
                try:
                    # Wait for 5 minutes
                    await sleep(300)  # 300 seconds = 5 minutes

                    # Edit the message to show it's expired
                    expired_text = "⏱️ <b>This search result has expired.</b>\n\nPlease use the search again button to perform a new search."
                    expired_markup = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    text="🔍 Search Again",
                                    switch_inline_query_current_chat="",
                                )
                            ]
                        ]
                    )

                    # Edit the inline message
                    await client.edit_inline_text(
                        inline_message_id=inline_message_id,
                        text=expired_text,
                        reply_markup=expired_markup,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    # Log the error but don't raise it
                    MEDIA_LOGGER.error(f"Error expiring inline message: {e}")

            # Start the expiration task
            create_task(expire_inline_message())

        except Exception as e:
            # Log the error but don't raise it
            MEDIA_LOGGER.error(f"Error in chosen_inline_result_handler: {e}")

    except Exception as e:
        # Log the error but don't raise it
        MEDIA_LOGGER.error(f"Error parsing chosen inline result: {e}")


@new_task
async def handle_media_get_command(client, message):
    """Handle media get command from start command.

    This function is called when a user clicks on a media get button from inline search.
    Format: /start get_media_id
    """
    try:
        # Extract parameters from the command
        MEDIA_LOGGER.info(f"Processing start command: {message.command}")

        if len(message.command) < 2:
            MEDIA_LOGGER.error("Invalid start command: No parameters provided")
            return

        command_parts = message.command[1].split("_")
        MEDIA_LOGGER.info(f"Command parts: {command_parts}")

        if len(command_parts) < 2 or command_parts[0] != "get":
            MEDIA_LOGGER.error(f"Invalid command format: {command_parts}")
            return

        # Get the encrypted media ID (everything after "get_")
        encrypted_media_id = message.command[1][4:]  # Skip the "get_" prefix
        MEDIA_LOGGER.info(f"Encrypted Media ID: {encrypted_media_id}")

        # Send a status message
        status_msg = await client.send_message(
            chat_id=message.chat.id, text="Retrieving media file... Please wait."
        )

        try:
            # Decrypt the media ID
            media_id = decrypt_data(encrypted_media_id)
            MEDIA_LOGGER.info(f"Decrypted Media ID: {media_id}")

            # Get media info from cache
            media_info = MEDIA_INFO_CACHE.get(media_id)
        except Exception as e:
            MEDIA_LOGGER.error(f"Error decrypting media ID: {e}")
            media_info = None

        if not media_info:
            MEDIA_LOGGER.error(f"Media info not found in cache for ID: {media_id}")
            await status_msg.edit_text(
                "Error: Media information not found or expired. Please try searching again."
            )
            # Auto-delete error message after 5 minutes
            create_task(auto_delete_message(status_msg, time=300))
            return

        MEDIA_LOGGER.info(f"Retrieved media info from cache: {media_info}")

        # Extract media information
        chat_id = media_info.get("chat_id")
        message_id = media_info.get("message_id")
        client_type = media_info.get("client_type")

        if not chat_id or not message_id or not client_type:
            MEDIA_LOGGER.error("Invalid media info: Missing required fields")
            await status_msg.edit_text(
                "Error: Invalid media information. Please try searching again."
            )
            # Auto-delete error message after 5 minutes
            create_task(auto_delete_message(status_msg, time=300))
            return

        # IMPORTANT: Always use bot client for message retrieval when possible
        # Only fall back to user client if bot client fails
        client_to_use = TgClient.bot if TgClient.bot else TgClient.user
        client_type_to_use = "bot" if TgClient.bot else "user"

        # Check if the selected client is available
        if (client_type_to_use == "bot" and not TgClient.bot) or (
            client_type_to_use == "user" and not TgClient.user
        ):
            MEDIA_LOGGER.error(f"Client not available: {client_type_to_use}")
            await status_msg.edit_text(
                f"Error: The {client_type_to_use} client is not available. Please try again."
            )
            # Auto-delete error message after 5 minutes
            create_task(auto_delete_message(status_msg, time=300))
            return

        try:
            # Try to get the message with the primary client
            message_to_copy = None
            try:
                MEDIA_LOGGER.info(
                    f"Trying to get message with {client_type_to_use} client"
                )
                message_to_copy = await client_to_use.get_messages(
                    chat_id=int(chat_id), message_ids=int(message_id)
                )
            except Exception as e:
                MEDIA_LOGGER.error(
                    f"Error getting message with {client_type_to_use} client: {e}"
                )

            # If message not found with the primary client, try the other client as fallback
            if not message_to_copy or not (
                hasattr(message_to_copy, "audio")
                or hasattr(message_to_copy, "video")
                or hasattr(message_to_copy, "photo")
                or hasattr(message_to_copy, "document")
            ):
                # Try the other client
                fallback_client = None
                fallback_client_type = None

                # Since we're using bot client as primary, only fall back to user client if bot client fails
                if client_type_to_use == "bot" and TgClient.user:
                    fallback_client = TgClient.user
                    fallback_client_type = "user"
                elif client_type_to_use == "user" and TgClient.bot:
                    fallback_client = TgClient.bot
                    fallback_client_type = "bot"

                if fallback_client:
                    try:
                        MEDIA_LOGGER.info(
                            f"Trying fallback {fallback_client_type} client"
                        )
                        message_to_copy = await fallback_client.get_messages(
                            chat_id=int(chat_id), message_ids=int(message_id)
                        )
                        if message_to_copy:
                            MEDIA_LOGGER.info(
                                f"Successfully retrieved message with fallback {fallback_client_type} client"
                            )
                            client_to_use = fallback_client
                            client_type_to_use = fallback_client_type
                    except Exception as e:
                        MEDIA_LOGGER.error(
                            f"Error getting message with fallback {fallback_client_type} client: {e}"
                        )

            # If still no message found
            if not message_to_copy or not (
                hasattr(message_to_copy, "audio")
                or hasattr(message_to_copy, "video")
                or hasattr(message_to_copy, "photo")
                or hasattr(message_to_copy, "document")
            ):
                MEDIA_LOGGER.error("Media file not found or no longer available")
                await status_msg.edit_text(
                    "Media file not found or no longer available.\n\n"
                    "The message might have been deleted or the media file removed."
                )
                # Auto-delete error message after 5 minutes
                create_task(auto_delete_message(status_msg, time=300))
                return

            # Copy the media to the user
            MEDIA_LOGGER.info(f"Copying media to user {message.chat.id}")
            await message_to_copy.copy(message.chat.id, disable_notification=True)
            MEDIA_LOGGER.info("Media copied successfully")

            # Do not auto-delete the actual media file

            # Delete the status message
            await status_msg.delete()

        except Exception as e:
            MEDIA_LOGGER.error(f"Error retrieving media: {e}")
            await status_msg.edit_text(
                "Error retrieving media. Please try again later."
            )
            # Auto-delete error message after 5 minutes
            create_task(auto_delete_message(status_msg, time=300))

    except Exception as e:
        # Log the error but don't raise it
        MEDIA_LOGGER.error(f"Error in handle_media_get_command: {e}")

        # Try to send an error message to the user if possible
        try:
            await client.send_message(
                chat_id=message.chat.id,
                text="Error processing your request. Please try again later.",
            )
        except Exception as send_error:
            MEDIA_LOGGER.error(f"Failed to send error message: {send_error}")


def init_media_search(bot):
    """Initialize the media search module."""
    from pyrogram import filters
    from pyrogram.filters import command
    from pyrogram.handlers import (
        CallbackQueryHandler,
        ChosenInlineResultHandler,
        MessageHandler,
    )

    from bot.helper.telegram_helper.filters import CustomFilters

    # Register the command handler
    bot.add_handler(
        MessageHandler(
            media_search,
            filters=command(BotCommands.MediaSearchCommand)
            & CustomFilters.authorized,
        )
    )

    # Register the callback handlers
    bot.add_handler(
        CallbackQueryHandler(media_get_callback, filters=filters.regex(r"^medget_"))
    )

    bot.add_handler(
        CallbackQueryHandler(
            media_cancel_callback, filters=filters.regex(r"^medcancel_")
        )
    )

    bot.add_handler(
        CallbackQueryHandler(
            media_page_callback, filters=filters.regex(r"^medpage_")
        )
    )

    bot.add_handler(
        CallbackQueryHandler(
            media_page_callback, filters=filters.regex(r"^medpageinfo_")
        )
    )

    # Note: Inline query handler is now registered by unified inline search router
    # bot.add_handler(InlineQueryHandler(inline_media_search))

    # Register the chosen inline result handler
    bot.add_handler(ChosenInlineResultHandler(chosen_inline_result_handler))
