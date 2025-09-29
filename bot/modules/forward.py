import asyncio
from time import time

# Smart import for FloodPremiumWait compatibility
try:
    from pyrogram.errors import (
        ChannelPrivate,
        ChatAdminRequired,
        FloodPremiumWait,
        FloodTestPhoneWait,
        FloodWait,
        SlowmodeWait,
        UserNotParticipant,
    )
except ImportError:
    # FloodPremiumWait not available in pyrofork 2.2.11, use FloodWait as fallback
    from pyrogram.errors import (
        ChannelPrivate,
        ChatAdminRequired,
        FloodTestPhoneWait,
        FloodWait,
        SlowmodeWait,
        UserNotParticipant,
    )

    FloodPremiumWait = FloodWait  # Use FloodWait as fallback
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import is_privileged_user, new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.message_utils import edit_message, send_message

# Global dictionary to track active forwarding tasks for cancellation
active_forward_tasks = {}

# Global dictionary to track pagination state for message retrieval
pagination_state = {
    # user_id: {
    #     'source_chat_id': int,
    #     'destination_chat_id': int,
    #     'current_offset': int,
    #     'batch_size': int,
    #     'skip_count': int,
    #     'range_start': int,
    #     'range_end': int,
    #     'total_retrieved': int,
    #     'total_forwarded': int,
    #     'total_failed': int,
    #     'total_skipped': int
    # }
}

# Global variable to track recent FloodWait times for adaptive delays
recent_flood_wait_time = 0


class ForwardTracker:
    """Track forwarded messages to prevent duplicates"""

    @staticmethod
    async def is_message_forwarded(source_chat_id: int, message_id: int) -> bool:
        """Check if a message has already been forwarded"""
        if not await database.ensure_connection():
            return False

        try:
            result = await database.db.forwarded_messages.find_one(
                {"source_chat_id": source_chat_id, "message_id": message_id}
            )
            return result is not None
        except Exception as e:
            LOGGER.error(f"Error checking forwarded message: {e}")
            return False

    @staticmethod
    async def mark_message_forwarded(
        source_chat_id: int,
        message_id: int,
        destination_chat_id: int,
        forwarded_message_id: int,
    ):
        """Mark a message as forwarded"""
        if not await database.ensure_connection():
            return

        try:
            await database.db.forwarded_messages.insert_one(
                {
                    "source_chat_id": source_chat_id,
                    "message_id": message_id,
                    "destination_chat_id": destination_chat_id,
                    "forwarded_message_id": forwarded_message_id,
                    "timestamp": int(time()),
                    "bot_id": TgClient.ID,
                }
            )
        except Exception as e:
            LOGGER.error(f"Error marking message as forwarded: {e}")


async def resolve_chat_id(chat_identifier: str):
    """Resolve chat ID from username or ID string with fallback handling"""
    try:
        original_identifier = chat_identifier
        # Try to resolve as username first
        chat_identifier = chat_identifier.removeprefix("@")

        # Try user client first if available (better access to private chats)
        if TgClient.user:
            try:
                chat = await TgClient.user.get_chat(chat_identifier)
                return chat.id
            except Exception as user_error:
                if "PEER_ID_INVALID" not in str(user_error):
                    LOGGER.warning(
                        f"User client failed to resolve {chat_identifier}: {user_error}"
                    )

        # Try bot client
        try:
            chat = await TgClient.bot.get_chat(chat_identifier)
            return chat.id
        except Exception as bot_error:
            if "PEER_ID_INVALID" not in str(bot_error):
                LOGGER.error(
                    f"Bot client failed to resolve {chat_identifier}: {bot_error}"
                )

            # If it's a numeric ID, try to use it directly
            try:
                chat_id = int(chat_identifier)
                # Validate it's a reasonable chat ID format
                if abs(chat_id) > 1000000000:  # Minimum valid chat ID
                    return chat_id
                LOGGER.warning(f"Numeric ID {chat_id} appears invalid (too small)")
            except ValueError:
                pass

            LOGGER.error(f"All resolution methods failed for: {original_identifier}")
            return None

    except Exception as e:
        LOGGER.error(
            f"Unexpected error resolving chat ID for {chat_identifier}: {e}"
        )
        return None


async def copy_message_safe(
    source_chat_id: int,
    destination_chat_id: int,
    message_id: int,
    max_retries: int = 3,
):
    """Safely copy a message with enhanced flood wait handling and fallback methods"""
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Use user client if available for better access, otherwise bot client
            client = TgClient.user if TgClient.user else TgClient.bot
            is_bot = await is_bot_client(client)

            # For bot clients, skip copy_message and go directly to forward_messages
            # because copy_message requires reading message content which bots often can't do
            if is_bot:
                try:
                    return await client.forward_messages(
                        chat_id=destination_chat_id,
                        from_chat_id=source_chat_id,
                        message_ids=message_id,
                    )
                except (
                    FloodWait,
                    FloodPremiumWait,
                    FloodTestPhoneWait,
                ) as flood_error:
                    # Re-raise FloodWait to be handled by outer loop
                    raise flood_error
                except Exception as forward_error:
                    # Check for fatal errors that indicate destination chat issues
                    if (
                        hasattr(forward_error, "ID")
                        and forward_error.ID == "CHANNEL_INVALID"
                    ):
                        LOGGER.error(
                            f"FATAL: Destination chat {destination_chat_id} is invalid or inaccessible"
                        )
                        raise forward_error  # Re-raise to stop the entire batch

                    LOGGER.warning(
                        f"forward_messages failed for message {message_id}: {forward_error}"
                    )
                    return None

            # For user clients, verify we can access the source message first
            try:
                source_message = await client.get_messages(
                    source_chat_id, message_id
                )
                if not source_message:
                    LOGGER.error(
                        f"Cannot access source message {message_id} from chat {source_chat_id}"
                    )
                    return None
            except Exception as access_error:
                LOGGER.error(
                    f"Cannot access source message {message_id}: {access_error}"
                )
                return None

            # Primary method: copy_message
            try:
                result = await client.copy_message(
                    chat_id=destination_chat_id,
                    from_chat_id=source_chat_id,
                    message_id=message_id,
                )

                # Check if copy_message actually returned a valid result
                if result is None:
                    raise Exception(
                        "copy_message returned None - trying forward_messages fallback"
                    )

                return result
            except (FloodWait, FloodPremiumWait, FloodTestPhoneWait) as flood_error:
                # Re-raise FloodWait to be handled by outer loop
                raise flood_error
            except Exception as copy_error:
                # Check for fatal errors that indicate destination chat issues
                if hasattr(copy_error, "ID") and copy_error.ID == "CHANNEL_INVALID":
                    LOGGER.error(
                        f"FATAL: Destination chat {destination_chat_id} is invalid or inaccessible"
                    )
                    raise copy_error  # Re-raise to stop the entire batch

                LOGGER.warning(
                    f"copy_message failed for message {message_id}: {copy_error}"
                )

                # Fallback method: forward_messages (creates a link to original)
                try:
                    return await client.forward_messages(
                        chat_id=destination_chat_id,
                        from_chat_id=source_chat_id,
                        message_ids=message_id,
                    )
                except (
                    FloodWait,
                    FloodPremiumWait,
                    FloodTestPhoneWait,
                ) as flood_error:
                    # Re-raise FloodWait to be handled by outer loop
                    raise flood_error
                except Exception as forward_error:
                    # Check for fatal errors in fallback method too
                    if (
                        hasattr(forward_error, "ID")
                        and forward_error.ID == "CHANNEL_INVALID"
                    ):
                        LOGGER.error(
                            f"FATAL: Destination chat {destination_chat_id} is invalid - both methods failed"
                        )
                        raise forward_error  # Re-raise to stop the entire batch

                    LOGGER.error(
                        f"forward_messages fallback failed for message {message_id}: {forward_error}"
                    )
                    # If both methods fail, re-raise the original copy error
                    raise copy_error from None

        except (FloodWait, FloodPremiumWait, FloodTestPhoneWait) as e:
            global recent_flood_wait_time
            wait_time = e.value
            recent_flood_wait_time = wait_time  # Update global for adaptive delays

            # For long waits, don't add exponential backoff as it's already a penalty
            if wait_time < 10 and retry_count > 0:
                wait_time += (
                    retry_count * 2
                )  # Add 2, 4, 6 seconds only for short waits

            LOGGER.warning(
                f"FloodWait for message {message_id} (attempt {retry_count + 1}/{max_retries}): "
                f"Waiting {wait_time} seconds"
            )
            await asyncio.sleep(wait_time)
            retry_count += 1

        except SlowmodeWait as e:
            LOGGER.warning(f"SlowmodeWait: Waiting {e.value} seconds")
            await asyncio.sleep(e.value)
            retry_count += 1

        except (ChatAdminRequired, UserNotParticipant, ChannelPrivate) as e:
            LOGGER.error(f"Access error copying message {message_id}: {e}")
            return None

        except Exception as e:
            # Check for fatal errors that should stop the entire batch
            if hasattr(e, "ID") and e.ID == "CHANNEL_INVALID":
                LOGGER.error(
                    f"FATAL: Destination chat {destination_chat_id} is invalid - stopping all forwarding"
                )
                raise e  # Re-raise to stop the entire batch

            LOGGER.error(f"Error copying message {message_id}: {e}")

            # For certain errors, don't retry
            error_type = type(e).__name__
            if error_type in [
                "MessageIdInvalid",
                "MessageNotModified",
                "MessageEmpty",
                "ChannelInvalid",
            ]:
                return None

            retry_count += 1

    LOGGER.error(f"Failed to copy message {message_id} after {max_retries} attempts")
    return None


async def is_bot_client(client):
    """Check if the client is a bot client"""
    try:
        # Check if client has bot_token attribute
        if hasattr(client, "bot_token") and client.bot_token:
            return True

        # Check storage for bot flag
        if hasattr(client, "storage"):
            is_bot = await client.storage.is_bot()
            if is_bot is not None:
                return is_bot

        return False
    except Exception:
        # If we can't determine, assume it's a user client for safety
        return False


async def get_messages_batch(
    client,
    chat_id: int,
    batch_size: int = 50,
    offset: int = 0,
    range_start: int | None = None,
    range_end: int | None = None,
):
    """Get a batch of messages with pagination support"""
    messages = []
    is_bot = await is_bot_client(client)

    try:
        if is_bot:
            # Bot clients: Use targeted ID ranges
            if range_start and range_end:
                # Range-based retrieval with offset
                start_id = range_start + offset
                end_id = min(start_id + batch_size, range_end + 1)

                if start_id <= range_end:
                    message_ids = list(range(start_id, end_id))
                    try:
                        batch_messages = await client.get_messages(
                            chat_id, message_ids
                        )
                        if isinstance(batch_messages, list):
                            messages = [
                                msg for msg in batch_messages if msg is not None
                            ]
                        elif batch_messages is not None:
                            messages = [batch_messages]
                    except Exception as e:
                        LOGGER.warning(f"Bot client range batch failed: {e}")
            else:
                # Discovery-based retrieval with offset
                test_ranges = [
                    range(1 + offset, 51 + offset),
                    range(100 + offset, 151 + offset),
                    range(1000 + offset, 1051 + offset),
                    range(10000 + offset, 10051 + offset),
                ]

                for test_range in test_ranges:
                    if len(messages) >= batch_size:
                        break

                    try:
                        chunk_ids = list(test_range)[: batch_size - len(messages)]
                        chunk_messages = await client.get_messages(
                            chat_id, chunk_ids
                        )

                        if isinstance(chunk_messages, list):
                            valid_messages = [
                                msg for msg in chunk_messages if msg is not None
                            ]
                            messages.extend(valid_messages)
                        elif chunk_messages is not None:
                            messages.append(chunk_messages)

                    except Exception:
                        continue  # Try next range
        # User clients: Use get_chat_history with offset
        elif range_start and range_end:
            # Range-based with offset
            start_id = range_start + offset
            end_id = min(start_id + batch_size, range_end + 1)

            if start_id <= range_end:
                message_ids = list(range(start_id, end_id))
                try:
                    batch_messages = await client.get_messages(chat_id, message_ids)
                    if isinstance(batch_messages, list):
                        messages = [msg for msg in batch_messages if msg is not None]
                    elif batch_messages is not None:
                        messages = [batch_messages]
                except Exception as e:
                    LOGGER.warning(f"User client range batch failed: {e}")
        else:
            # History-based with offset
            try:
                count = 0
                async for msg in client.get_chat_history(chat_id):
                    if count < offset:
                        count += 1
                        continue
                    if len(messages) >= batch_size:
                        break
                    messages.append(msg)
                    count += 1
            except Exception as e:
                LOGGER.warning(f"User client history batch failed: {e}")

    except Exception as e:
        LOGGER.error(f"Error in get_messages_batch: {e}")
        return []

    return messages


# Keep the old function for compatibility
async def get_messages_safe(
    client,
    chat_id: int,
    limit: int = 100,
    range_start: int | None = None,
    range_end: int | None = None,
):
    """Legacy function - use get_messages_batch instead"""
    return await get_messages_batch(
        client,
        chat_id,
        batch_size=limit,
        offset=0,
        range_start=range_start,
        range_end=range_end,
    )


@new_task
async def mode_batch_callback(_client, callback_query):
    """Handle batch mode selection"""
    user_id = callback_query.from_user.id

    if user_id not in pagination_state:
        await callback_query.answer("❌ Session expired. Please start again.")
        return

    state = pagination_state[user_id]
    source_chat_id = state["source_chat_id"]
    destination_chat_id = state["destination_chat_id"]
    skip_count = state["skip_count"]
    range_start = state["range_start"]
    range_end = state["range_end"]

    await callback_query.answer("📦 Batch mode selected!")

    # Start batch mode processing
    await start_batch_mode(
        callback_query.message,
        user_id,
        source_chat_id,
        destination_chat_id,
        skip_count,
        range_start,
        range_end,
    )


@new_task
async def mode_direct_callback(_client, callback_query):
    """Handle direct mode selection"""
    user_id = callback_query.from_user.id

    if user_id not in pagination_state:
        await callback_query.answer("❌ Session expired. Please start again.")
        return

    state = pagination_state[user_id]
    source_chat_id = state["source_chat_id"]
    destination_chat_id = state["destination_chat_id"]
    skip_count = state["skip_count"]
    range_start = state["range_start"]
    range_end = state["range_end"]

    await callback_query.answer("🚀 Direct mode selected!")

    # Create cancel button
    cancel_button = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🛑 Cancel", callback_data=f"cancel_forward_{user_id}"
                )
            ]
        ]
    )

    # Start direct mode processing
    client_to_use = TgClient.user or TgClient.bot
    await handle_direct_mode(
        callback_query.message,
        user_id,
        client_to_use,
        source_chat_id,
        destination_chat_id,
        skip_count,
        range_start,
        range_end,
        cancel_button,
    )


@new_task
async def cancel_forward_callback(_client, callback_query):
    """Handle cancel forward button callback"""
    user_id = callback_query.from_user.id

    # Check if user has permission
    if not is_privileged_user(user_id):
        await callback_query.answer(
            "❌ You don't have permission to cancel forwarding.", show_alert=True
        )
        return

    # Always allow cancellation - set flag and clean up states
    active_forward_tasks[user_id] = True  # Set cancellation flag

    # Clean up pagination state
    if user_id in pagination_state:
        pagination_state.pop(user_id, None)

    # Update the message to show cancellation
    await edit_message(
        callback_query.message,
        "🛑 <b>Operation Cancelled</b>\n\n"
        "✅ All forwarding operations have been stopped.\n"
        "💡 You can start a new forwarding operation anytime.",
    )

    await callback_query.answer(
        "🛑 Operation cancelled successfully!", show_alert=True
    )


def create_pagination_buttons(
    user_id: int, has_more: bool = True, current_batch: int = 1
):
    """Create pagination buttons for message retrieval"""
    buttons = []

    # First row: Forward current batch and Cancel
    row1 = [
        InlineKeyboardButton(
            "📤 Forward This Batch", callback_data=f"forward_batch_{user_id}"
        ),
        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_forward_{user_id}"),
    ]
    buttons.append(row1)

    # Second row: Next batch (if available)
    if has_more:
        row2 = [
            InlineKeyboardButton(
                "➡️ Get Next Batch", callback_data=f"next_batch_{user_id}"
            )
        ]
        buttons.append(row2)

    return InlineKeyboardMarkup(buttons)


@new_task
async def next_batch_callback(_client, callback_query):
    """Handle next batch button callback"""
    user_id = callback_query.from_user.id

    if user_id not in pagination_state:
        await callback_query.answer("❌ No active pagination session")
        return

    state = pagination_state[user_id]

    # Update offset for next batch
    state["current_offset"] += state["batch_size"]

    await callback_query.answer("🔄 Getting next batch...")

    # Get next batch of messages
    client_to_use = TgClient.user if TgClient.user else TgClient.bot
    messages = await get_messages_batch(
        client_to_use,
        state["source_chat_id"],
        batch_size=state["batch_size"],
        offset=state["current_offset"],
        range_start=state.get("range_start"),
        range_end=state.get("range_end"),
    )

    if messages:
        state["total_retrieved"] += len(messages)

        # Create buttons for this batch
        has_more = (
            len(messages) == state["batch_size"]
        )  # Assume more if we got a full batch
        buttons = create_pagination_buttons(
            user_id, has_more, state["current_offset"] // state["batch_size"] + 1
        )

        # Update message with new batch info
        batch_num = state["current_offset"] // state["batch_size"] + 1
        status_text = (
            f"📦 <b>Batch {batch_num} Retrieved</b>\n\n"
            f"📊 <b>This batch:</b> {len(messages)} messages\n"
            f"📈 <b>Total retrieved:</b> {state['total_retrieved']} messages\n"
            f"🔄 <b>Offset:</b> {state['current_offset']}\n\n"
            f"Choose an action:"
        )

        await edit_message(callback_query.message, status_text, buttons=buttons)
    else:
        # No more messages
        await edit_message(
            callback_query.message,
            f"✅ <b>No more messages found</b>\n\n"
            f"📊 <b>Total retrieved:</b> {state['total_retrieved']} messages\n\n"
            f"Use 📤 Forward This Batch to forward the last batch.",
        )


@new_task
async def forward_batch_callback(_client, callback_query):
    """Handle forward batch button callback"""
    user_id = callback_query.from_user.id

    if user_id not in pagination_state:
        await callback_query.answer("❌ No active pagination session")
        return

    state = pagination_state[user_id]

    await callback_query.answer("🚀 Starting batch forwarding...")

    # Get the current batch of messages
    client_to_use = TgClient.user if TgClient.user else TgClient.bot
    messages = await get_messages_batch(
        client_to_use,
        state["source_chat_id"],
        batch_size=state["batch_size"],
        offset=state["current_offset"],
        range_start=state.get("range_start"),
        range_end=state.get("range_end"),
    )

    if not messages:
        await edit_message(
            callback_query.message, "❌ No messages to forward in this batch"
        )
        return

    # Start forwarding this batch
    await forward_messages_batch(
        callback_query.message,
        messages,
        state["source_chat_id"],
        state["destination_chat_id"],
        state["skip_count"],
        user_id,
        state.get("range_start"),
        state.get("range_end"),
    )


async def start_batch_mode(
    status_msg,
    user_id,
    source_chat_id,
    destination_chat_id,
    skip_count,
    range_start,
    range_end,
):
    """Start batch mode processing"""
    # Create cancel button
    cancel_button = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🛑 Cancel", callback_data=f"cancel_forward_{user_id}"
                )
            ]
        ]
    )

    await edit_message(
        status_msg, "🔄 Batch Mode: Initializing...", buttons=cancel_button
    )

    try:
        # Choose the best client
        client_to_use = TgClient.user or TgClient.bot

        # Initialize pagination state for batch mode
        batch_size = 50
        pagination_state[user_id] = {
            "source_chat_id": source_chat_id,
            "destination_chat_id": destination_chat_id,
            "current_offset": 0,
            "batch_size": batch_size,
            "skip_count": skip_count,
            "range_start": range_start,
            "range_end": range_end,
            "total_retrieved": 0,
            "total_forwarded": 0,
            "total_failed": 0,
            "total_skipped": 0,
        }

        # Get first batch of messages
        messages = await get_messages_batch(
            client_to_use,
            source_chat_id,
            batch_size=batch_size,
            offset=0,
            range_start=range_start,
            range_end=range_end,
        )

        if not messages:
            await edit_message(status_msg, "❌ No messages found in source chat.")
            active_forward_tasks.pop(user_id, None)
            pagination_state.pop(user_id, None)
            return

        # Update pagination state
        pagination_state[user_id]["total_retrieved"] = len(messages)

        # Create pagination buttons
        has_more = len(messages) == batch_size
        buttons = create_pagination_buttons(user_id, has_more, 1)

        # Show first batch info
        range_info = (
            f" from range {range_start}-{range_end}"
            if range_start and range_end
            else ""
        )
        status_text = (
            f"📦 <b>Batch Mode - First Batch Retrieved</b>\n\n"
            f"📊 <b>This batch:</b> {len(messages)} messages{range_info}\n"
            f"📈 <b>Total retrieved:</b> {len(messages)} messages\n"
            f"🔄 <b>Batch size:</b> {batch_size} messages\n"
            f"⏱️ <b>Delay per message:</b> 10 seconds (adaptive)\n\n"
            f"Choose an action:"
        )

        await edit_message(status_msg, status_text, buttons=buttons)

    except Exception as e:
        LOGGER.error(f"Error in batch mode: {e}")
        await edit_message(status_msg, f"❌ Error in batch mode: {e!s}")
        active_forward_tasks.pop(user_id, None)
        pagination_state.pop(user_id, None)


async def forward_messages_batch(
    status_msg,
    messages,
    source_chat_id,
    destination_chat_id,
    skip_count,
    user_id,
    range_start=None,
    range_end=None,
    show_progress=True,
    from_direct_mode=False,
):
    """Forward a batch of messages with progress tracking"""

    # Initialize cancellation tracking for this batch
    active_forward_tasks[user_id] = False  # False = not cancelled, True = cancelled

    # Create cancel button
    cancel_button = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🛑 Cancel", callback_data=f"cancel_forward_{user_id}"
                )
            ]
        ]
    )

    # Initialize counters
    forwarded_count = 0
    failed_count = 0
    skipped_count = 0
    processed_count = 0

    for i, msg in enumerate(messages):
        # Check for cancellation at the start of each iteration (only if not from direct mode)
        if not from_direct_mode and active_forward_tasks.get(user_id, False):
            await edit_message(
                status_msg,
                f"🛑 <b>Batch Forwarding Cancelled</b>\n\n"
                f"📊 <b>Progress before cancellation:</b>\n"
                f"• Processed: {i}/{len(messages)} messages\n"
                f"• Successfully forwarded: {forwarded_count}\n"
                f"• Skipped by pattern: {skipped_count}\n"
                f"• Failed: {failed_count}",
            )
            active_forward_tasks.pop(user_id, None)
            return forwarded_count, failed_count, skipped_count

        # Update status every 3 messages (more frequent updates) - only if show_progress is True
        if show_progress and i % 3 == 0:
            remaining_messages = len(messages) - i
            estimated_time = (
                remaining_messages * 10
            ) // 60  # 10 seconds per message
            await edit_message(
                status_msg,
                f"🔄 Processing batch... {i + 1}/{len(messages)}\n"
                f"✅ Forwarded: {forwarded_count}\n"
                f"⏭️ Skipped: {skipped_count}\n"
                f"❌ Failed: {failed_count}\n"
                f"⏱️ Est. time remaining: ~{estimated_time} min\n"
                f"🔄 10s delay between messages",
                buttons=cancel_button,
            )

        # Check if already forwarded
        if await ForwardTracker.is_message_forwarded(source_chat_id, msg.id):
            continue

        # Skip logic
        if skip_count > 0:
            position_in_pattern = processed_count % (skip_count + 1)
            if position_in_pattern != 0:
                skipped_count += 1
                processed_count += 1
                continue

        # Copy message with fatal error handling
        try:
            copied_msg = await copy_message_safe(
                source_chat_id, destination_chat_id, msg.id
            )
            processed_count += 1
        except Exception as fatal_error:
            # Handle fatal errors that should stop the entire batch
            if hasattr(fatal_error, "ID") and fatal_error.ID == "CHANNEL_INVALID":
                await edit_message(
                    status_msg,
                    f"❌ <b>Batch Forwarding Stopped - Fatal Error</b>\n\n"
                    f"🚫 <b>Error:</b> Destination chat is invalid or inaccessible\n"
                    f"📊 <b>Progress before error:</b>\n"
                    f"• Processed: {processed_count}/{len(messages)} messages\n"
                    f"• Successfully forwarded: {forwarded_count}\n"
                    f"• Skipped by pattern: {skipped_count}\n"
                    f"• Failed: {failed_count}\n\n"
                    f"💡 <b>Possible solutions:</b>\n"
                    f"• Check if the destination chat ID is correct\n"
                    f"• Ensure the bot is added to the destination chat\n"
                    f"• Verify the bot has proper permissions",
                )
                active_forward_tasks.pop(user_id, None)  # Clean up
                return forwarded_count, failed_count, skipped_count
            # Re-raise other fatal errors
            raise fatal_error

        # Check for cancellation after each message copy (only if not from direct mode)
        if not from_direct_mode and active_forward_tasks.get(user_id, False):
            await edit_message(
                status_msg,
                f"🛑 <b>Batch Forwarding Cancelled</b>\n\n"
                f"📊 <b>Progress before cancellation:</b>\n"
                f"• Processed: {processed_count}/{len(messages)} messages\n"
                f"• Successfully forwarded: {forwarded_count}\n"
                f"• Skipped by pattern: {skipped_count}\n"
                f"• Failed: {failed_count}",
            )
            active_forward_tasks.pop(user_id, None)  # Clean up
            return forwarded_count, failed_count, skipped_count

        # Check if we got a valid result
        if copied_msg is not None:
            # Handle different return types
            if hasattr(copied_msg, "id"):
                copied_id = copied_msg.id
            elif (
                isinstance(copied_msg, list)
                and len(copied_msg) > 0
                and hasattr(copied_msg[0], "id")
            ):
                copied_id = copied_msg[0].id
            elif isinstance(copied_msg, int | str):
                copied_id = copied_msg
            else:
                copied_id = getattr(copied_msg, "id", str(copied_msg))

            # Mark as forwarded
            await ForwardTracker.mark_message_forwarded(
                source_chat_id, msg.id, destination_chat_id, copied_id
            )
            forwarded_count += 1

            # 10-second delay only after successful forward/copy
            base_delay = 10.0
            if recent_flood_wait_time > 0:
                # If we've had recent FloodWait, increase delay proportionally
                adaptive_delay = min(
                    base_delay + (recent_flood_wait_time * 0.2), 30.0
                )
            else:
                adaptive_delay = base_delay
            await asyncio.sleep(adaptive_delay)
        else:
            failed_count += 1

    # Update pagination state with results
    if user_id in pagination_state:
        state = pagination_state[user_id]
        state["total_forwarded"] += forwarded_count
        state["total_failed"] += failed_count
        state["total_skipped"] += skipped_count

    # Final status with pagination options
    already_forwarded = len(messages) - processed_count

    status_text = "✅ <b>Batch Forwarding Completed!</b>\n\n"
    if range_start and range_end:
        status_text += f"📍 <b>Range:</b> Messages {range_start}-{range_end}\n"

    status_text += (
        f"📊 <b>This Batch Results:</b>\n"
        f"• Forwarded: {forwarded_count}\n"
        f"• Failed: {failed_count}\n"
        f"• Skipped: {skipped_count}\n"
        f"• Already forwarded: {already_forwarded}\n\n"
    )

    # Add total stats if available
    if user_id in pagination_state:
        state = pagination_state[user_id]
        status_text += (
            f"📈 <b>Total Session Stats:</b>\n"
            f"• Total retrieved: {state['total_retrieved']}\n"
            f"• Total forwarded: {state['total_forwarded']}\n"
            f"• Total failed: {state['total_failed']}\n"
            f"• Total skipped: {state['total_skipped']}\n\n"
        )

    # Create buttons for next actions
    buttons = []
    if user_id in pagination_state:
        row1 = [
            InlineKeyboardButton(
                "➡️ Get Next Batch", callback_data=f"next_batch_{user_id}"
            ),
            InlineKeyboardButton(
                "✅ Finish", callback_data=f"finish_pagination_{user_id}"
            ),
        ]
        buttons.append(row1)
        status_text += "Choose your next action:"

    await edit_message(
        status_msg,
        status_text,
        buttons=InlineKeyboardMarkup(buttons) if buttons else None,
    )

    # Clean up task tracking
    active_forward_tasks.pop(user_id, None)

    # Return counts for direct mode
    return forwarded_count, failed_count, skipped_count


@new_task
async def finish_pagination_callback(_client, callback_query):
    """Handle finish pagination button callback"""
    user_id = callback_query.from_user.id

    if user_id in pagination_state:
        state = pagination_state[user_id]

        # Show final summary
        final_text = (
            f"🎉 <b>Pagination Session Completed!</b>\n\n"
            f"📊 <b>Final Statistics:</b>\n"
            f"• Total retrieved: {state['total_retrieved']}\n"
            f"• Total forwarded: {state['total_forwarded']}\n"
            f"• Total failed: {state['total_failed']}\n"
            f"• Total skipped: {state['total_skipped']}\n\n"
            f"✅ Session ended successfully!"
        )

        await edit_message(callback_query.message, final_text)

        # Clean up pagination state
        pagination_state.pop(user_id, None)

        await callback_query.answer("✅ Pagination session completed!")
    else:
        await callback_query.answer("❌ No active pagination session")


async def show_mode_selection(
    status_msg,
    user_id,
    source_chat_id,
    destination_chat_id,
    skip_count,
    range_start,
    range_end,
):
    """Show mode selection buttons"""
    # Store parameters for later use
    pagination_state[user_id] = {
        "source_chat_id": source_chat_id,
        "destination_chat_id": destination_chat_id,
        "skip_count": skip_count,
        "range_start": range_start,
        "range_end": range_end,
        "mode_selection": True,
    }

    range_info = (
        f" (range {range_start}-{range_end})" if range_start and range_end else ""
    )
    skip_info = f" (skip {skip_count})" if skip_count > 0 else ""

    mode_buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📦 Batch Mode", callback_data=f"mode_batch_{user_id}"
                ),
                InlineKeyboardButton(
                    "🚀 Direct Mode", callback_data=f"mode_direct_{user_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🛑 Cancel", callback_data=f"cancel_forward_{user_id}"
                )
            ],
        ]
    )

    await edit_message(
        status_msg,
        f"🎯 <b>Select Forwarding Mode</b>\n\n"
        f"📋 <b>Source:</b> {source_chat_id}\n"
        f"📋 <b>Destination:</b> {destination_chat_id}{range_info}{skip_info}\n\n"
        f"📦 <b>Batch Mode:</b>\n"
        f"• Process 50 messages at a time\n"
        f"• Interactive control with buttons\n"
        f"• Manual progression through batches\n\n"
        f"🚀 <b>Direct Mode:</b>\n"
        f"• Process 500 messages per chunk\n"
        f"• Automatic progression\n"
        f"• 10-second delay between messages\n"
        f"• Continues until all messages processed\n\n"
        f"Choose your preferred mode:",
        buttons=mode_buttons,
    )


async def handle_direct_mode(
    status_msg,
    user_id,
    client,
    source_chat_id,
    destination_chat_id,
    skip_count,
    range_start,
    range_end,
    cancel_button,
):
    """Handle direct mode: process messages in 500-message chunks automatically"""
    await edit_message(
        status_msg,
        "🚀 Direct Mode: Starting automatic processing...",
        buttons=cancel_button,
    )

    try:
        # Initialize tracking
        total_processed = 0
        total_forwarded = 0
        total_failed = 0
        total_skipped = 0
        chunk_size = 500
        current_offset = max(0, skip_count)

        # Set up pagination state for direct mode
        pagination_state[user_id] = {
            "source_chat_id": source_chat_id,
            "destination_chat_id": destination_chat_id,
            "skip_count": skip_count,
            "range_start": range_start,
            "range_end": range_end,
            "mode": "direct",
            "current_offset": current_offset,
            "chunk_size": chunk_size,
            "total_retrieved": 0,
            "total_processed": 0,
            "total_forwarded": 0,
            "total_failed": 0,
            "total_skipped": 0,
        }

        while True:
            # Check for cancellation
            if active_forward_tasks.get(user_id, False):
                await edit_message(
                    status_msg,
                    f"🛑 <b>Direct Mode Cancelled</b>\n\n"
                    f"📊 <b>Final Results:</b>\n"
                    f"• Total processed: {total_processed}\n"
                    f"• Successfully forwarded: {total_forwarded}\n"
                    f"• Skipped: {total_skipped}\n"
                    f"• Failed: {total_failed}",
                )
                active_forward_tasks.pop(user_id, None)
                pagination_state.pop(user_id, None)
                return

            # Get next chunk of messages
            await edit_message(
                status_msg,
                f"🔄 Direct Mode: Getting chunk starting from message {current_offset + 1}...",
                buttons=cancel_button,
            )

            try:
                messages = await get_messages_batch(
                    client,
                    source_chat_id,
                    batch_size=chunk_size,
                    offset=current_offset,
                    range_start=range_start,
                    range_end=range_end,
                )
            except Exception as retrieval_error:
                LOGGER.error(f"Error retrieving messages: {retrieval_error}")
                # If retrieval fails, we're done
                await edit_message(
                    status_msg,
                    f"❌ <b>Error retrieving messages</b>\n\n"
                    f"📊 <b>Final Results:</b>\n"
                    f"• Total processed: {total_processed}\n"
                    f"• Successfully forwarded: {total_forwarded}\n"
                    f"• Skipped: {total_skipped}\n"
                    f"• Failed: {total_failed}\n\n"
                    f"⚠️ Stopped due to retrieval error: {retrieval_error}",
                )
                active_forward_tasks.pop(user_id, None)
                pagination_state.pop(user_id, None)
                return

            if not messages:
                # No more messages, we're done
                await edit_message(
                    status_msg,
                    f"✅ <b>Direct Mode Complete!</b>\n\n"
                    f"📊 <b>Final Results:</b>\n"
                    f"• Total processed: {total_processed}\n"
                    f"• Successfully forwarded: {total_forwarded}\n"
                    f"• Skipped: {total_skipped}\n"
                    f"• Failed: {total_failed}\n\n"
                    f"🎉 All available messages have been processed!",
                )
                active_forward_tasks.pop(user_id, None)
                pagination_state.pop(user_id, None)
                return

            # Update status for this chunk
            await edit_message(
                status_msg,
                f"🚀 Direct Mode: Processing chunk {current_offset // chunk_size + 1}\n"
                f"📦 Found {len(messages)} messages to process\n"
                f"📊 Total so far: {total_processed} processed, {total_forwarded} forwarded\n"
                f"🔄 Starting to forward messages with 10s delays...",
                buttons=cancel_button,
            )

            # Forward this chunk (skip_count is 0 because we already applied offset during retrieval)
            try:
                (
                    chunk_forwarded,
                    chunk_failed,
                    chunk_skipped,
                ) = await forward_messages_batch(
                    status_msg,
                    messages,
                    source_chat_id,
                    destination_chat_id,
                    0,  # No additional skip needed - already applied in offset
                    user_id,
                    range_start,
                    range_end,
                    show_progress=False,  # Don't show individual progress for direct mode
                    from_direct_mode=True,  # Indicate this is called from direct mode
                )
            except Exception as batch_error:
                LOGGER.error(f"Error in forward_messages_batch: {batch_error}")
                LOGGER.error(f"Batch error type: {type(batch_error)}")
                # If batch forwarding fails, treat as all failed
                chunk_forwarded, chunk_failed, chunk_skipped = 0, len(messages), 0

            # Check for cancellation after chunk processing
            if active_forward_tasks.get(user_id, False):
                await edit_message(
                    status_msg,
                    f"🛑 <b>Direct Mode Cancelled</b>\n\n"
                    f"📊 <b>Final Results:</b>\n"
                    f"• Total processed: {total_processed + len(messages)}\n"
                    f"• Successfully forwarded: {total_forwarded + chunk_forwarded}\n"
                    f"• Skipped: {total_skipped + chunk_skipped}\n"
                    f"• Failed: {total_failed + chunk_failed}",
                )
                active_forward_tasks.pop(user_id, None)
                pagination_state.pop(user_id, None)
                return

            # Update totals
            total_processed += len(messages)
            total_forwarded += chunk_forwarded
            total_failed += chunk_failed
            total_skipped += chunk_skipped
            current_offset += chunk_size

            # Update pagination state (with safety check)
            if user_id in pagination_state:
                pagination_state[user_id]["current_offset"] = current_offset
                pagination_state[user_id]["total_retrieved"] = (
                    total_processed  # Same as processed in direct mode
                )
                pagination_state[user_id]["total_processed"] = total_processed
                pagination_state[user_id]["total_forwarded"] = total_forwarded
                pagination_state[user_id]["total_failed"] = total_failed
            else:
                LOGGER.warning(
                    f"Pagination state missing for user {user_id}, recreating..."
                )
                # Recreate the pagination state if it's missing
                pagination_state[user_id] = {
                    "source_chat_id": source_chat_id,
                    "destination_chat_id": destination_chat_id,
                    "skip_count": skip_count,
                    "range_start": range_start,
                    "range_end": range_end,
                    "mode": "direct",
                    "current_offset": current_offset,
                    "chunk_size": chunk_size,
                    "total_retrieved": total_processed,
                    "total_processed": total_processed,
                    "total_forwarded": total_forwarded,
                    "total_failed": total_failed,
                    "total_skipped": total_skipped,
                }

            # Show chunk completion
            await edit_message(
                status_msg,
                f"✅ Chunk {current_offset // chunk_size} completed!\n"
                f"📊 Chunk results: {chunk_forwarded} forwarded, {chunk_failed} failed\n"
                f"📈 Total progress: {total_processed} processed, {total_forwarded} forwarded\n"
                f"🔄 Continuing to next chunk...",
                buttons=cancel_button,
            )

            # Small delay between chunks
            await asyncio.sleep(2)

    except Exception as e:
        import traceback

        LOGGER.error(f"Error in direct mode: {e}")
        LOGGER.error(f"Error type: {type(e)}")
        LOGGER.error(f"Source chat ID: {source_chat_id}")
        LOGGER.error(f"Destination chat ID: {destination_chat_id}")
        LOGGER.error(f"Direct mode traceback: {traceback.format_exc()}")
        await edit_message(status_msg, f"❌ Error in direct mode: {e!s}")
        active_forward_tasks.pop(user_id, None)
        pagination_state.pop(user_id, None)


@new_task
async def forward_command(_client, message: Message):
    """Handle /forward command for manual forwarding"""
    # Check if user is sudo
    if not is_privileged_user(message.from_user.id):
        await send_message(
            message, "❌ You don't have permission to use this command."
        )
        return

    # Parse command arguments
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if len(args) < 2:
        await send_message(
            message,
            "❌ <b>Usage:</b> <code>/forward source_chat destination_chat [-skip N] [-range START-END] [-mode batch|direct]</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/forward @channel1 @channel2</code> (default: batch mode)\n"
            "• <code>/forward -1001234567890 @mychannel -mode direct</code>\n"
            "• <code>/forward @source @dest -skip 5 -mode batch</code>\n"
            "• <code>/forward @source @dest -range 100-200 -mode direct</code>\n"
            "• <code>/forward @source @dest -skip 3 -range 50-150 -mode batch</code>\n\n"
            "<b>Modes:</b>\n"
            "• <b>Batch:</b> Retrieve messages in batches (50 at a time) with pagination\n"
            "• <b>Direct:</b> Retrieve all available messages and forward one by one\n\n"
            "<b>Note:</b> Use chat ID or @username for both source and destination.\n"
            "<b>Delay:</b> 10-second wait between each message (adaptive based on rate limits).",
        )
        return

    source_chat = args[0]
    destination_chat = args[1]
    skip_count = 0
    range_start = None
    range_end = None
    mode = "batch"  # Default mode

    # Parse optional parameters
    i = 2
    while i < len(args):
        if args[i] == "-skip" and i + 1 < len(args):
            try:
                skip_count = int(args[i + 1])
                i += 2
            except ValueError:
                await send_message(
                    message, "❌ Invalid skip count. Must be a number."
                )
                return
        elif args[i] == "-range" and i + 1 < len(args):
            try:
                range_parts = args[i + 1].split("-")
                if len(range_parts) != 2:
                    raise ValueError("Invalid range format")
                range_start = int(range_parts[0])
                range_end = int(range_parts[1])
                if range_start >= range_end or range_start < 1:
                    raise ValueError("Invalid range values")
                i += 2
            except ValueError:
                await send_message(
                    message,
                    "❌ Invalid range format. Use: -range START-END (e.g., -range 100-200)",
                )
                return
        elif args[i] == "-mode" and i + 1 < len(args):
            mode = args[i + 1].lower()
            if mode not in ["batch", "direct"]:
                await send_message(
                    message, "❌ Invalid mode. Use 'batch' or 'direct'."
                )
                return
            i += 2
        else:
            await send_message(message, f"❌ Unknown parameter: {args[i]}")
            return

    # Initialize cancellation tracking
    user_id = message.from_user.id
    active_forward_tasks[user_id] = False  # False = not cancelled, True = cancelled

    # Create cancel button
    cancel_button = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🛑 Cancel Forwarding", callback_data=f"cancel_forward_{user_id}"
                )
            ]
        ]
    )

    # Resolve chat IDs
    status_msg = await send_message(
        message, "🔄 Resolving chat IDs...", buttons=cancel_button
    )

    source_chat_id = await resolve_chat_id(source_chat)
    if not source_chat_id:
        await edit_message(
            status_msg, f"❌ Could not resolve source chat: {source_chat}"
        )
        active_forward_tasks.pop(user_id, None)  # Clean up
        return

    destination_chat_id = await resolve_chat_id(destination_chat)
    if not destination_chat_id:
        await edit_message(
            status_msg, f"❌ Could not resolve destination chat: {destination_chat}"
        )
        active_forward_tasks.pop(user_id, None)  # Clean up
        return

    # Early validation: Test if we can access the destination chat
    await edit_message(
        status_msg, "🔄 Validating destination chat access...", buttons=cancel_button
    )

    try:
        client_to_use = TgClient.user if TgClient.user else TgClient.bot
        await client_to_use.resolve_peer(destination_chat_id)
    except Exception as dest_error:
        if hasattr(dest_error, "ID") and dest_error.ID == "CHANNEL_INVALID":
            await edit_message(
                status_msg,
                f"❌ <b>Destination Chat Invalid</b>\n\n"
                f"🚫 <b>Error:</b> Cannot access destination chat {destination_chat}\n"
                f"📋 <b>Chat ID:</b> {destination_chat_id}\n\n"
                f"💡 <b>Possible solutions:</b>\n"
                f"• Check if the chat ID is correct\n"
                f"• Ensure the bot is added to the destination chat\n"
                f"• Verify the bot has proper permissions\n"
                f"• For private chats, the bot needs to be started by the user first",
            )
            active_forward_tasks.pop(user_id, None)  # Clean up
            return
        LOGGER.warning(
            f"Could not validate destination chat {destination_chat_id}: {dest_error}"
        )
        # Continue anyway - might work during actual forwarding

    await edit_message(
        status_msg, "🔄 Starting message forwarding...", buttons=cancel_button
    )

    # Choose the best client for message retrieval and operations
    # User client is preferred for better access to private chats and history
    client_to_use = TgClient.user or TgClient.bot

    # Check destination chat permissions and test send access
    try:
        dest_chat = await client_to_use.get_chat(destination_chat_id)

        # For private chats, test if bot can send messages
        if dest_chat.type.name == "PRIVATE":
            try:
                # Test sending a simple message to verify access
                test_msg = await client_to_use.send_message(
                    destination_chat_id, "🔄 Testing message send access..."
                )
                # Delete the test message immediately
                await client_to_use.delete_messages(destination_chat_id, test_msg.id)
            except Exception as send_test_error:
                LOGGER.error(
                    f"Bot cannot send messages to private chat: {send_test_error}"
                )

                await edit_message(
                    status_msg,
                    "❌ <b>Cannot send messages to destination</b>\n\n"
                    "⚠️ <b>Possible reasons:</b>\n"
                    "• User hasn't started the bot\n"
                    "• User blocked the bot\n"
                    "• Bot lacks permission to send messages\n\n"
                    "💡 <b>Solution:</b> Start a conversation with the bot first",
                )
                active_forward_tasks.pop(user_id, None)
                return
        # Check if bot has send permissions for groups/channels
        elif not TgClient.user:  # Only check for bot clients
            try:
                bot_member = await client_to_use.get_chat_member(
                    destination_chat_id, "me"
                )
                if bot_member.status in ["left", "kicked"]:
                    await edit_message(
                        status_msg,
                        "❌ Bot is not a member of the destination chat.",
                    )
                    active_forward_tasks.pop(user_id, None)
                    return
            except Exception as perm_error:
                LOGGER.warning(f"Could not check bot permissions: {perm_error}")

    except Exception as dest_error:
        LOGGER.warning(f"Could not check destination chat: {dest_error}")

    # If mode was specified in command, use it directly
    if mode != "batch":  # mode was explicitly set to "direct"
        # Direct mode: Get all messages and forward immediately
        await handle_direct_mode(
            status_msg,
            user_id,
            client_to_use,
            source_chat_id,
            destination_chat_id,
            skip_count,
            range_start,
            range_end,
            cancel_button,
        )
        return

    # If no mode specified or batch mode, show mode selection
    if (
        mode == "batch"
        and len([arg for arg in message.text.split() if arg == "-mode"]) == 0
    ):
        # Show mode selection buttons
        await show_mode_selection(
            status_msg,
            user_id,
            source_chat_id,
            destination_chat_id,
            skip_count,
            range_start,
            range_end,
        )
        return

    # Batch mode: Get messages from source chat with pagination
    try:
        # Initialize pagination state
        batch_size = 50  # Reasonable batch size
        pagination_state[user_id] = {
            "source_chat_id": source_chat_id,
            "destination_chat_id": destination_chat_id,
            "current_offset": 0,
            "batch_size": batch_size,
            "skip_count": skip_count,
            "range_start": range_start,
            "range_end": range_end,
            "total_retrieved": 0,
            "total_forwarded": 0,
            "total_failed": 0,
            "total_skipped": 0,
        }

        # Get first batch of messages
        messages = await get_messages_batch(
            client_to_use,
            source_chat_id,
            batch_size=batch_size,
            offset=0,
            range_start=range_start,
            range_end=range_end,
        )

        if not messages:
            # Provide specific error message based on client type
            if TgClient.user:
                error_msg = "❌ No messages found in source chat or access denied."
            else:
                error_msg = (
                    "❌ <b>No accessible messages found</b>\n\n"
                    "⚠️ <b>Bot Client Limitations:</b>\n"
                    "• Bot clients have limited message access\n"
                    "• Only messages the bot can see are available\n"
                    "• Consider configuring user session for full access\n\n"
                    "💡 <b>Tip:</b> Bot needs to be admin or have message access"
                )

            await edit_message(status_msg, error_msg)
            active_forward_tasks.pop(user_id, None)
            pagination_state.pop(user_id, None)
            return

        # Update pagination state
        pagination_state[user_id]["total_retrieved"] = len(messages)

        # Create pagination buttons
        has_more = len(messages) == batch_size  # Assume more if we got a full batch
        buttons = create_pagination_buttons(user_id, has_more, 1)

        # Show first batch info
        range_info = (
            f" from range {range_start}-{range_end}"
            if range_start and range_end
            else ""
        )
        status_text = (
            f"📦 <b>Batch Mode - First Batch Retrieved</b>\n\n"
            f"📊 <b>This batch:</b> {len(messages)} messages{range_info}\n"
            f"📈 <b>Total retrieved:</b> {len(messages)} messages\n"
            f"🔄 <b>Batch size:</b> {batch_size} messages\n"
            f"⏱️ <b>Delay per message:</b> 10 seconds (adaptive)\n\n"
            f"Choose an action:"
        )

        await edit_message(status_msg, status_text, buttons=buttons)

        # Clean up task tracking since we're now using pagination
        active_forward_tasks.pop(user_id, None)
        return  # Exit here - user will use buttons to continue

    except Exception as e:
        LOGGER.error(f"Error in forward command: {e}")
        await edit_message(status_msg, f"❌ Error during forwarding: {e!s}")
        # Clean up task tracking on error
        active_forward_tasks.pop(user_id, None)


@new_task
async def auto_forward_handler(_client, message: Message):
    """Handle automatic forwarding from configured source chats"""
    # Skip if no forwarding configured
    if not Config.FORWARD_SOURCE or not Config.FORWARD_DESTINATION:
        return

    # Check if message is from a configured source chat
    source_chat_id = message.chat.id
    if (
        str(source_chat_id) not in Config.FORWARD_SOURCE
        and f"@{message.chat.username}" not in Config.FORWARD_SOURCE
    ):
        return

    # Check if message was already forwarded
    if await ForwardTracker.is_message_forwarded(source_chat_id, message.id):
        return

    # Forward to all destination chats
    forwarded_count = 0
    failed_count = 0

    for dest_chat in Config.FORWARD_DESTINATION:
        dest_chat_id = await resolve_chat_id(dest_chat)
        if not dest_chat_id:
            LOGGER.error(f"Could not resolve destination chat: {dest_chat}")
            failed_count += 1
            continue

        # Copy message
        copied_msg = await copy_message_safe(
            source_chat_id, dest_chat_id, message.id
        )

        if copied_msg:
            # Mark as forwarded
            await ForwardTracker.mark_message_forwarded(
                source_chat_id, message.id, dest_chat_id, copied_msg.id
            )
            forwarded_count += 1
        else:
            failed_count += 1

    # Send completion message to owner if any messages were processed
    if (forwarded_count > 0 or failed_count > 0) and Config.OWNER_ID:
        try:
            client_to_use = TgClient.user if TgClient.user else TgClient.bot
            await client_to_use.send_message(
                Config.OWNER_ID,
                f"🔄 <b>Auto Forward Completed</b>\n\n"
                f"📤 <b>Source:</b> {message.chat.title or message.chat.first_name} ({source_chat_id})\n"
                f"📨 <b>Message ID:</b> {message.id}\n"
                f"📊 <b>Results:</b> {forwarded_count} forwarded, {failed_count} failed",
            )
        except Exception as e:
            LOGGER.error(f"Error sending auto-forward completion message: {e}")
