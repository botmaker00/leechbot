import contextlib
import re
from asyncio import create_task, gather, sleep, wait_for
from re import match as re_match
from time import time as get_time

from cachetools import TTLCache
from pyrogram import Client, enums

# Smart import for FloodPremiumWait compatibility
try:
    from pyrogram.errors import (
        FloodPremiumWait,
        FloodWait,
        MessageEmpty,
        MessageNotModified,
    )
except ImportError:
    # FloodPremiumWait not available in pyrofork 2.2.11, use FloodWait as fallback
    from pyrogram.errors import FloodWait, MessageEmpty, MessageNotModified

    FloodPremiumWait = FloodWait  # Use FloodWait as fallback
from pyrogram.types import InputMediaPhoto

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    intervals,
    status_dict,
    task_dict_lock,
    user_data,
)
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import SetInterval
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.exceptions import TgLinkException
from bot.helper.ext_utils.status_utils import get_readable_message

session_cache = TTLCache(
    maxsize=100,
    ttl=3600,
)  # Reduced from 1000 to 100, and 36000 to 3600


async def with_timeout_retry(coro_func, timeout=30, max_retries=3, backoff_factor=2):
    """
    Execute a coroutine with timeout and retry logic for handling request timeouts

    Args:
        coro_func: A callable that returns a coroutine (not the coroutine itself)
        timeout: Timeout in seconds for each attempt
        max_retries: Maximum number of retry attempts
        backoff_factor: Exponential backoff factor for retry delays
    """
    for attempt in range(max_retries):
        try:
            # Create a fresh coroutine for each attempt
            coro = coro_func() if callable(coro_func) else coro_func
            return await wait_for(coro, timeout=timeout)
        except TimeoutError:
            if attempt < max_retries - 1:
                wait_time = backoff_factor**attempt
                LOGGER.warning(
                    f"Request timed out (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s..."
                )
                await sleep(wait_time)
                continue
            LOGGER.error(f"Request timed out after {max_retries} attempts")
            raise
        except Exception as e:
            # For non-timeout errors, don't retry
            raise e
    return None


async def send_message(
    message,
    text,
    buttons=None,
    photo=None,
    markdown=False,
    block=True,
    bot_client=None,
    is_ai_message=False,
):
    """Send a message using the specified bot client

    Args:
        message: Message to reply to or chat ID to send to
        text: Text content of the message
        buttons: Reply markup buttons
        photo: Photo to include with the message
        markdown: Whether to use Markdown formatting
        block: Whether to block until the message is sent
        bot_client: Bot client to use for sending (default: main bot)
        is_ai_message: Whether this is an AI-generated message (skips truncation)
    """
    parse_mode = enums.ParseMode.MARKDOWN if markdown else enums.ParseMode.HTML

    # Ensure text is a string to avoid TypeError
    if not isinstance(text, str):
        if text is None:
            text = "Error: Message content is None"
        else:
            # Convert any non-string object to string
            text = str(text)

    # Validate and truncate message length if necessary
    max_length = 4096  # Telegram's message length limit
    if len(text) > max_length:
        # Check if message contains expandable blockquotes
        if "<blockquote expandable=" not in text:
            if not is_ai_message:
                # Truncate non-AI messages as before
                text = (
                    text[: max_length - 100]
                    + "\n\n<i>... (message truncated due to length)</i>"
                )
            else:
                # For AI messages, log warning but don't truncate - let AI module handle splitting
                LOGGER.warning(
                    f"AI message length {len(text)} exceeds limit {max_length}. Should be split by AI module."
                )
        else:
            # If it has expandable blockquotes, let Telegram handle it
            pass

    # Use the specified bot client or default to the main bot
    client = bot_client or TgClient.bot

    # Check if client is available
    if not client:
        LOGGER.warning(
            "No client available for sending message. This is normal during restart."
        )
        return "Client not available"

    # Handle None message object
    if message is None:
        return "Cannot send message: message object is None"

    try:
        # Handle case where message is a chat_id (int or string)
        if isinstance(message, int | str):
            # If it's a string, try to convert to int if it's numeric
            if isinstance(message, str) and message.isdigit():
                message = int(message)

            return await client.send_message(
                chat_id=message,
                text=text,
                disable_web_page_preview=True,
                disable_notification=True,
                reply_markup=buttons,
                parse_mode=parse_mode,
            )

        # Check if message has required attributes
        if not hasattr(message, "chat") or not hasattr(message.chat, "id"):
            # Try to send to chat directly if message has an id attribute
            if hasattr(message, "id"):
                return await client.send_message(
                    chat_id=message.id,
                    text=text,
                    disable_web_page_preview=True,
                    disable_notification=True,
                    reply_markup=buttons,
                    parse_mode=parse_mode,
                )

            return f"Invalid message object: {type(message)}"

        if photo:
            # Check if message has id attribute before using it
            reply_to_message_id = message.id if hasattr(message, "id") else None
            return await message.reply_photo(
                photo=photo,
                reply_to_message_id=reply_to_message_id,
                caption=text,
                reply_markup=buttons,
                disable_notification=True,
                parse_mode=parse_mode,
            )

        return await message.reply(
            text=text,
            quote=True,
            disable_web_page_preview=True,
            disable_notification=True,
            reply_markup=buttons,
            parse_mode=parse_mode,
        )

    except FloodWait as f:
        if not block:
            return message
        # More aggressive backoff to prevent repeated FloodWait errors
        await sleep(f.value * 1.5 + 2)  # Add extra buffer time
        return await send_message(
            message,
            text,
            buttons,
            photo,
            markdown,
            block,
            bot_client,
        )
    except Exception as e:
        error_str = str(e)
        # Handle client not started errors gracefully (during restart)
        if "Client has not been started yet" in error_str:
            LOGGER.warning(
                f"Client not started for sending message. This is normal during restart: {error_str}"
            )
        # Don't log UserIsBlocked and InputUserDeactivated as errors since they're handled by callers
        elif not (
            "USER_IS_BLOCKED" in error_str or "INPUT_USER_DEACTIVATED" in error_str
        ):
            LOGGER.error(error_str)
        return error_str


async def edit_message(
    message,
    text,
    buttons=None,
    photo=None,
    markdown=False,
    block=True,
    is_ai_message=False,
):
    # Check if message is valid
    if not message or not hasattr(message, "chat") or not hasattr(message, "id"):
        return "Invalid message object"

    parse_mode = enums.ParseMode.MARKDOWN if markdown else enums.ParseMode.HTML

    # Ensure text is a string to avoid TypeError
    if not isinstance(text, str):
        if text is None:
            text = "Error: Message content is None"
        else:
            # Convert any non-string object to string
            text = str(text)

    # Validate and truncate message length if necessary
    max_length = 4096  # Telegram's message length limit
    if len(text) > max_length:
        # Check if message contains expandable blockquotes
        if "<blockquote expandable=" not in text:
            if not is_ai_message:
                # Truncate non-AI messages as before
                text = (
                    text[: max_length - 100]
                    + "\n\n<i>... (message truncated due to length)</i>"
                )
            else:
                # For AI messages, log warning but don't truncate - let AI module handle splitting
                LOGGER.warning(
                    f"AI edit message length {len(text)} exceeds limit {max_length}. Should be split by AI module."
                )
        else:
            # If it has expandable blockquotes, let Telegram handle it
            pass

    try:
        # Check if message still exists by trying to get its chat and message ID
        chat_id = getattr(message.chat, "id", None)
        message_id = getattr(message, "id", None)

        if not chat_id or not message_id:
            return "Message has invalid chat_id or message_id"

        # Check if the client is still available before attempting edit
        client_available = False
        if hasattr(message, "_client") and message._client:
            # Check if the client is still started
            try:
                client_available = message._client.is_connected
            except AttributeError:
                # Fallback: check if TgClient instances are available
                client_available = (
                    TgClient.bot is not None or TgClient.user is not None
                )
        else:
            # Fallback: check if TgClient instances are available
            client_available = TgClient.bot is not None or TgClient.user is not None

        if not client_available:
            LOGGER.warning(
                f"Client not available for editing message {message_id} in chat {chat_id}. Skipping edit."
            )
            return "Client not available"

        # Handle case where buttons is None (could happen if build_menu returns None)
        if buttons is None:
            # Set to empty InlineKeyboardMarkup instead of logging a warning
            buttons = None

        if message.media:
            if photo:
                # Create InputMediaPhoto with the correct parse_mode
                media = InputMediaPhoto(photo, caption=text, parse_mode=parse_mode)
                return await with_timeout_retry(
                    lambda: message.edit_media(media=media, reply_markup=buttons),
                    timeout=30,
                )
            return await with_timeout_retry(
                lambda: message.edit_caption(
                    caption=text,
                    reply_markup=buttons,
                    parse_mode=parse_mode,
                ),
                timeout=30,
            )
        await with_timeout_retry(
            lambda: message.edit(
                text=text,
                disable_web_page_preview=True,
                reply_markup=buttons,
                parse_mode=parse_mode,
            ),
            timeout=30,
        )
    except FloodWait as f:
        if not block:
            return message
        # More aggressive backoff to prevent repeated FloodWait errors
        await sleep(f.value * 1.5 + 2)  # Add extra buffer time
        return await edit_message(message, text, buttons, photo, markdown)
    except (MessageNotModified, MessageEmpty):
        # Message content hasn't changed or is empty, not an error
        return message
    except Exception as e:
        error_str = str(e)
        # Check for MESSAGE_TOO_LONG error and suggest using expandable blockquotes
        if "MESSAGE_TOO_LONG" in error_str:
            LOGGER.error(
                f"Message too long: {error_str}. Consider using expandable blockquotes for long content."
            )
            # Try to send a notification about using expandable blockquotes
            with contextlib.suppress(Exception):
                await message.reply(
                    "The message is too long for Telegram. Please use expandable blockquotes for long content sections.",
                    quote=True,
                )
        # Handle REPLY_MARKUP_INVALID error
        elif "REPLY_MARKUP_INVALID" in error_str:
            LOGGER.error(f"Telegram says: {error_str}")
            # Try to edit the message without buttons
            try:
                await message.edit(
                    text=text,
                    disable_web_page_preview=True,
                    parse_mode=parse_mode,
                )
                return message
            except Exception as e2:
                LOGGER.error(f"Failed to edit message without buttons: {e2!s}")
        # Handle client not started errors gracefully (during restart)
        elif "Client has not been started yet" in error_str:
            LOGGER.warning(
                f"Client not started for editing message. This is normal during restart: {error_str}"
            )
        # Only log at debug level for common Telegram API errors
        elif (
            "MESSAGE_ID_INVALID" in error_str
            or "message to edit not found" in error_str.lower()
        ):
            pass
        else:
            LOGGER.error(error_str)
        return error_str


async def send_file(message, file, caption="", buttons=None):
    try:
        return await message.reply_document(
            document=file,
            quote=True,
            caption=caption,
            disable_notification=True,
            reply_markup=buttons,
        )

    except FloodWait as f:
        await sleep(f.value * 1.2)
        return await send_file(message, file, caption, buttons)
    except Exception as e:
        LOGGER.error(str(e))
        return str(e)


async def send_rss(text, chat_id, thread_id):
    # Validate input parameters
    if not text or not text.strip():
        LOGGER.error("Attempted to send empty RSS message")
        return "Message is empty"

    # Ensure text is not too long
    if len(text) > 4096:
        text = text[:4093] + "..."

    # Remove zero-width and control characters that might cause issues
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    text = "".join(c if ord(c) >= 32 or c == "\n" else " " for c in text)

    try:
        app = TgClient.user or TgClient.bot
        return await app.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=True,
            message_thread_id=thread_id,
            disable_notification=True,
        )

    except MessageEmpty:
        LOGGER.error("Telegram says: Message is empty")
        # Try with a simplified message as a fallback
        try:
            simplified_text = "RSS Update: Unable to display full content due to formatting issues."
            return await app.send_message(
                chat_id=chat_id,
                text=simplified_text,
                disable_web_page_preview=True,
                message_thread_id=thread_id,
                disable_notification=True,
            )

        except Exception as e2:
            LOGGER.error(f"Failed to send simplified message too: {e2}")
            return str(e2)
    except (FloodWait, FloodPremiumWait) as f:
        await sleep(f.value * 1.2)
        return await send_rss(text, chat_id, thread_id)
    except Exception as e:
        LOGGER.error(f"Error sending RSS message: {e!s}")
        # Try with a simplified message as a fallback if it seems to be a formatting issue
        if "MESSAGE_EMPTY" in str(e) or "400" in str(e):
            try:
                simplified_text = "RSS Update: Unable to display full content due to formatting issues."
                return await app.send_message(
                    chat_id=chat_id,
                    text=simplified_text,
                    disable_web_page_preview=True,
                    message_thread_id=thread_id,
                    disable_notification=True,
                )

            except Exception as e2:
                LOGGER.error(f"Failed to send simplified message too: {e2}")
        return str(e)


async def delete_message(*args):
    msgs = []
    for msg in args:
        if msg:
            # Enhanced validation for message attributes
            if not hasattr(msg, "id") or msg.id is None:
                continue

            if not hasattr(msg, "chat") or msg.chat is None:
                continue

            # Additional check for chat ID
            if not hasattr(msg.chat, "id") or msg.chat.id is None:
                continue

            # Check if this is a service message that cannot be deleted
            is_service_msg = hasattr(msg, "service") and msg.service is not None
            if is_service_msg:
                # Remove from database if it exists since we can't delete it
                try:
                    await database.remove_scheduled_deletion(msg.chat.id, msg.id)
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for service message: {e}"
                    )
                continue

            # Check if the client is still available before attempting deletion
            client_available = False
            if hasattr(msg, "_client") and msg._client:
                # Check if the client is still started
                try:
                    client_available = msg._client.is_connected
                except AttributeError:
                    # Fallback: check if TgClient instances are available
                    client_available = (
                        TgClient.bot is not None or TgClient.user is not None
                    )
            else:
                # Fallback: check if TgClient instances are available
                client_available = (
                    TgClient.bot is not None or TgClient.user is not None
                )

            if not client_available:
                LOGGER.warning(
                    f"Client not available for deleting message {msg.id} in chat {msg.chat.id}. Skipping deletion."
                )
                # Remove from database since we can't delete it
                try:
                    await database.remove_scheduled_deletion(msg.chat.id, msg.id)
                except Exception as e:
                    LOGGER.error(f"Error removing scheduled deletion: {e}")
                continue

            msgs.append(create_task(msg.delete()))
            # Remove from database if it exists
            try:
                await database.remove_scheduled_deletion(msg.chat.id, msg.id)
            except Exception as e:
                LOGGER.error(f"Error removing scheduled deletion: {e}")

    results = await gather(*msgs, return_exceptions=True)

    for msg, result in zip(args, results, strict=False):
        if isinstance(result, Exception):
            # Enhanced validation before accessing message attributes
            if not msg or not hasattr(msg, "id") or msg.id is None:
                continue

            if (
                not hasattr(msg, "chat")
                or msg.chat is None
                or not hasattr(msg.chat, "id")
                or msg.chat.id is None
            ):
                continue

            error_str = str(result)
            # Handle client not started errors gracefully (during restart)
            if "Client has not been started yet" in error_str:
                LOGGER.warning(
                    f"Client not started for deleting message {msg.id} in chat {msg.chat.id}. This is normal during restart."
                )
                # Remove from database since we can't delete it
                try:
                    await database.remove_scheduled_deletion(msg.chat.id, msg.id)
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for client not started: {e}"
                    )
            # Handle permission-related errors more gracefully
            elif "MESSAGE_DELETE_FORBIDDEN" in error_str or "403" in error_str:
                LOGGER.warning(
                    f"Cannot delete message {msg.id} in chat {msg.chat.id}: {error_str}"
                )
                # Remove from database since we can't delete it
                try:
                    await database.remove_scheduled_deletion(msg.chat.id, msg.id)
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for forbidden message: {e}"
                    )
            elif "MESSAGE_ID_INVALID" in error_str or "400" in error_str:
                LOGGER.error(
                    f"Message {msg.id} in chat {msg.chat.id} no longer exists: {error_str}"
                )
                # Remove from database since message doesn't exist
                try:
                    await database.remove_scheduled_deletion(msg.chat.id, msg.id)
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for invalid message: {e}"
                    )
            else:
                # Log other errors as actual errors
                LOGGER.error(
                    f"Failed to delete message {msg}: {result}", exc_info=True
                )


async def delete_links(message):
    if not Config.DELETE_LINKS:
        return

    msgs = []
    if reply_to := message.reply_to_message:
        msgs.append(reply_to)
    msgs.append(message)

    await delete_message(*msgs)


async def auto_delete_message(*args, time=300, bot_id=None):
    """Schedule messages for automatic deletion after a specified time

    Args:
        *args: Messages to delete
        time: Time in seconds after which to delete the messages
        bot_id: ID of the bot that sent the message (default: main bot ID)
    """
    if time and time > 0:
        # Store messages for deletion in database
        message_ids = []
        chat_ids = []
        for msg in args:
            if msg and hasattr(msg, "id") and hasattr(msg, "chat"):
                message_ids.append(msg.id)
                chat_ids.append(msg.chat.id)
                # Message scheduled for deletion

        if message_ids and chat_ids:
            delete_time = int(get_time() + time)

            # Determine which bot sent the message
            if bot_id is None:
                # Try to determine the bot ID from the message's _client attribute if available
                if (
                    args
                    and hasattr(args[0], "_client")
                    and hasattr(args[0]._client, "me")
                ):
                    client = args[0]._client
                    if hasattr(client.me, "id"):
                        bot_id = str(client.me.id)
                        # Bot ID determined from message client
                    else:
                        bot_id = TgClient.ID
                        # Using default bot ID
                else:
                    bot_id = TgClient.ID
                    # Using default bot ID

            try:
                await database.store_scheduled_deletion(
                    chat_ids,
                    message_ids,
                    delete_time,
                    bot_id,
                )
                # Messages stored for deletion
            except Exception as e:
                LOGGER.error(f"Error storing scheduled deletion: {e}")

        # Instead of blocking with sleep, let the scheduled deletion system handle it
        # The process_pending_deletions function will handle this on next run


async def delete_status():
    async with task_dict_lock:
        for key, data in list(status_dict.items()):
            try:
                await delete_message(data["message"])
                del status_dict[key]
            except Exception as e:
                LOGGER.error(str(e))


async def get_tg_link_message(link, user_id=""):
    message = None
    links = []
    user_session = None
    skip_value = 1  # Default skip value (no skipping)

    if user_id:
        if user_id in session_cache:
            user_session = session_cache[user_id]
        else:
            user_dict = user_data.get(user_id, {})
            session_string = user_dict.get("session_string")
            if session_string:
                user_session = Client(
                    f"session_{user_id}",
                    Config.TELEGRAM_API,
                    Config.TELEGRAM_HASH,
                    session_string=session_string,
                    no_updates=True,
                )
                await user_session.start()
                session_cache[user_id] = user_session
            else:
                user_session = TgClient.user

    # Check if -skip parameter is in the link (more robust parsing)
    if "-skip" in link:
        # Handle different ways users might input the -skip parameter
        if " -skip " in link:
            parts = link.split(" -skip ")
            link = parts[0].strip()
            skip_str = parts[1].strip()
        elif " -skip" in link:
            parts = link.split(" -skip")
            link = parts[0].strip()
            skip_str = parts[1].strip() if len(parts) > 1 else ""
        elif "-skip " in link:
            parts = link.split("-skip ")
            link = parts[0].strip()
            skip_str = parts[1].strip()
        else:
            # Handle case where there are no spaces
            match = re.search(r"(.*?)-skip(\d+)(.*)", link)
            if match:
                link = match.group(1) + match.group(3)
                skip_str = match.group(2)
            else:
                skip_str = ""

        try:
            # Extract the numeric value from the skip string
            skip_match = re.search(r"(\d+)", skip_str)
            if skip_match:
                skip_value = int(skip_match.group(1))
                skip_value = max(skip_value, 1)  # Ensure skip value is at least 1
        except ValueError:
            # If conversion fails, use default skip value
            pass

    if link.startswith("https://t.me/"):
        private = False
        msg = re_match(
            r"https:\/\/t\.me\/(?:c\/)?([^\/]+)(?:\/[^\/]+)?\/([0-9-]+)",
            link,
        )
    else:
        private = True
        msg = re_match(
            r"tg:\/\/openmessage\?user_id=([0-9]+)&message_id=([0-9-]+)",
            link,
        )
        if not user_session:
            raise TgLinkException(
                "USER_SESSION_STRING required for this private link!",
            )

    chat = msg[1]
    msg_id = msg[2]
    if "-" in msg_id:
        start_id, end_id = map(int, msg_id.split("-"))
        msg_id = start_id
        end_id - start_id
        if private:
            link = link.split("&message_id=")[0]
            links.append(f"{link}&message_id={start_id}")
            current_id = start_id
            while current_id < end_id:
                current_id += skip_value
                if current_id <= end_id:
                    links.append(f"{link}&message_id={current_id}")
        else:
            link = link.rsplit("/", 1)[0]
            links.append(f"{link}/{start_id}")
            current_id = start_id
            while current_id < end_id:
                current_id += skip_value
                if current_id <= end_id:
                    links.append(f"{link}/{current_id}")
    else:
        msg_id = int(msg_id)

    if chat.isdigit():
        chat = int(chat) if private else int(f"-100{chat}")

    if not private:
        try:
            # Get the message by its ID with Electrogram compatibility
            try:
                message = await TgClient.bot.get_messages(
                    chat_id=chat,
                    message_ids=msg_id,
                )
            except TypeError as e:
                # Handle case where get_messages has different parameters in Electrogram
                if "unexpected keyword argument" in str(
                    e
                ):  # Try alternative approach for Electrogram
                    message = await TgClient.bot.get_messages(
                        chat,  # chat_id as positional argument
                        msg_id,  # message_ids as positional argument
                    )
                else:
                    raise
            if message.empty:
                private = True
        except Exception as e:
            private = True
            if not user_session:
                raise e

    if not private:
        return (links, TgClient.bot) if links else (message, TgClient.bot)
    if user_session:
        try:
            # Get the message by its ID with Electrogram compatibility
            try:
                user_message = await user_session.get_messages(
                    chat_id=chat,
                    message_ids=msg_id,
                )
            except TypeError as e:
                # Handle case where get_messages has different parameters in Electrogram
                if "unexpected keyword argument" in str(
                    e
                ):  # Try alternative approach for Electrogram
                    user_message = await user_session.get_messages(
                        chat,  # chat_id as positional argument
                        msg_id,  # message_ids as positional argument
                    )
                else:
                    raise
        except Exception as e:
            raise TgLinkException("We don't have access to this chat!") from e
        if not user_message.empty:
            return (links, user_session) if links else (user_message, user_session)
        return None, None
    raise TgLinkException("Private: Please report!")


async def temp_download(msg):
    path = f"{DOWNLOAD_DIR}temp"
    return await msg.download(file_name=f"{path}/")


async def update_status_message(sid, force=False):
    if intervals["stopAll"]:
        return
    async with task_dict_lock:
        if not status_dict.get(sid):
            if obj := intervals["status"].get(sid):
                obj.cancel()
                del intervals["status"][sid]
            return
        # Stricter rate limiting to prevent FloodWait errors
        time_since_last_update = get_time() - status_dict[sid]["time"]
        min_interval = 5 if force else 3  # Longer interval for forced updates
        if time_since_last_update < min_interval:
            return
        status_dict[sid]["time"] = get_time()
        page_no = status_dict[sid]["page_no"]
        status = status_dict[sid]["status"]
        is_user = status_dict[sid]["is_user"]
        page_step = status_dict[sid]["page_step"]
        text, buttons = await get_readable_message(
            sid,
            is_user,
            page_no,
            status,
            page_step,
        )
        if text is None:
            del status_dict[sid]
            if obj := intervals["status"].get(sid):
                obj.cancel()
                del intervals["status"][sid]
            return
        if text != status_dict[sid]["message"].text:
            message = await edit_message(
                status_dict[sid]["message"],
                text,
                buttons,
                block=False,
            )
            if isinstance(message, str):
                # Check for common Telegram API errors that indicate the message is no longer valid
                if (
                    message.startswith("Telegram says: [40")
                    or "MESSAGE_ID_INVALID" in message
                    or "message to edit not found" in message.lower()
                ):
                    del status_dict[sid]
                    if obj := intervals["status"].get(sid):
                        obj.cancel()
                        del intervals["status"][sid]
                else:
                    # Only log as error for non-standard issues
                    LOGGER.error(
                        f"Status with id: {sid} haven't been updated. Error: {message}",
                    )
                return
            status_dict[sid]["message"].text = text
            status_dict[sid]["time"] = get_time()


async def send_status_message(msg, user_id=0):
    if intervals["stopAll"]:
        return
    sid = user_id or msg.chat.id
    is_user = bool(user_id)
    async with task_dict_lock:
        if sid in status_dict:
            page_no = status_dict[sid]["page_no"]
            status = status_dict[sid]["status"]
            page_step = status_dict[sid]["page_step"]
            text, buttons = await get_readable_message(
                sid,
                is_user,
                page_no,
                status,
                page_step,
            )
            if text is None:
                del status_dict[sid]
                if obj := intervals["status"].get(sid):
                    obj.cancel()
                    del intervals["status"][sid]
                return
            old_message = status_dict[sid]["message"]
            message = await send_message(msg, text, buttons, block=False)
            if isinstance(message, str):
                LOGGER.error(
                    f"Status with id: {sid} haven't been sent. Error: {message}",
                )
                return
            await delete_message(old_message)
            message.text = text
            status_dict[sid].update({"message": message, "time": get_time()})
        else:
            text, buttons = await get_readable_message(sid, is_user)
            if text is None:
                return
            message = await send_message(msg, text, buttons, block=False)
            if isinstance(message, str):
                LOGGER.error(
                    f"Status with id: {sid} haven't been sent. Error: {message}",
                )
                return
            message.text = text
            status_dict[sid] = {
                "message": message,
                "time": get_time(),
                "page_no": 1,
                "page_step": 1,
                "status": "All",
                "is_user": is_user,
            }
        if not intervals["status"].get(sid) and not is_user:
            # Use configurable status update interval (minimum 2 seconds to prevent FloodWait)
            update_interval = max(Config.STATUS_UPDATE_INTERVAL, 2)
            intervals["status"][sid] = SetInterval(
                update_interval,
                update_status_message,
                sid,
            )
