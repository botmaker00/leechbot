from time import time

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import LOGGER, sudo_users, user_data
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.message_utils import edit_message, send_message


@new_task
async def check_scheduled_deletions(_, message):
    """Check all scheduled deletions in the database"""
    from bot.core.config_manager import get_config_bool

    # Check if scheduled deletion is enabled
    if not get_config_bool("SCHEDULED_DELETION_ENABLED", True):
        return await send_message(
            message, "Scheduled deletion functionality is disabled via configuration"
        )

    user_id = message.from_user.id
    if (
        user_id != Config.OWNER_ID
        and user_id not in sudo_users
        and not (user_id in user_data and user_data[user_id].get("SUDO"))
    ):
        return await send_message(message, "This command is only for sudo users")

    # User requested to check scheduled deletions

    if database.db is None:
        return await send_message(message, "Database is not connected")

    # Get all scheduled deletions
    all_deletions = await database.get_all_scheduled_deletions()

    if not all_deletions:
        return await send_message(
            message,
            "No scheduled deletions found in database",
        )

    # Prepare message
    current_time = int(time())
    pending_count = sum(
        1 for item in all_deletions if item["delete_time"] <= current_time
    )
    future_count = sum(
        1 for item in all_deletions if item["delete_time"] > current_time
    )

    msg = f"Found {len(all_deletions)} total scheduled deletions in database\n"
    msg += (
        f"Pending deletions: {pending_count}, Future deletions: {future_count}\n\n"
    )

    # Add sample entries
    if all_deletions:
        msg += "Sample entries (showing up to 3):\n"
        sample = all_deletions[:3] if len(all_deletions) > 3 else all_deletions
        for entry in sample:
            time_remaining = entry["time_remaining"]
            if isinstance(time_remaining, int):
                if time_remaining <= 0:
                    time_status = "PENDING"
                else:
                    time_status = f"{time_remaining} seconds remaining"
            else:
                time_status = str(time_remaining)

            # Format as bullet points
            msg += f"• <b>Chat ID:</b> {entry['chat_id']}\n"
            msg += f"  <b>Message ID:</b> {entry['message_id']}\n"
            msg += f"  <b>Bot ID:</b> {entry['bot_id']}\n"
            msg += f"  <b>Status:</b> {time_status}\n"
            msg += f"  <b>Due for deletion:</b> {'Yes' if entry.get('is_due', False) else 'No'}\n\n"

        # Add a note if there are more entries
        if len(all_deletions) > 3:
            msg += f"...and {len(all_deletions) - 3} more entries\n"

    # Add buttons for deletion actions
    buttons = []

    # Button for pending deletions (if any)
    if pending_count > 0:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"Delete All Pending Messages ({pending_count})",
                    callback_data="delete_pending",  # This matches the regex pattern in handlers.py
                ),
            ],
        )

    # Button to force delete all messages (even if not due yet)
    if all_deletions:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"Force Delete All Messages ({len(all_deletions)})",
                    callback_data="force_delete_all",
                ),
            ],
        )

    if buttons:
        await send_message(message, msg, buttons=InlineKeyboardMarkup(buttons))
    else:
        await send_message(message, msg)
    return None


@new_task
async def delete_pending_messages(_, callback_query):
    """Delete all pending messages"""
    user_id = callback_query.from_user.id
    if (
        user_id != Config.OWNER_ID
        and user_id not in sudo_users
        and not (user_id in user_data and user_data[user_id].get("SUDO"))
    ):
        await callback_query.answer(
            "This action is only for sudo users",
            show_alert=True,
        )
        return

    await callback_query.answer("Processing...")

    # Get all pending deletions
    current_time = int(time())
    all_deletions = await database.get_all_scheduled_deletions()
    pending_deletions = [
        item for item in all_deletions if item["delete_time"] <= current_time
    ]

    if not pending_deletions:
        await edit_message(callback_query.message, "No pending deletions found")
        return

    # Process each pending deletion
    success_count = 0
    fail_count = 0
    removed_from_db_count = 0

    for entry in pending_deletions:
        chat_id = entry["chat_id"]
        msg_id = entry["message_id"]
        bot_id = entry["bot_id"]

        # Get the appropriate bot client
        bot_client = None
        if bot_id == TgClient.ID:
            bot_client = TgClient.bot
        elif hasattr(TgClient, "helper_bots") and bot_id in TgClient.helper_bots:
            bot_client = TgClient.helper_bots[bot_id]

        if bot_client is None:
            fail_count += 1
            continue

        try:
            # Try to get the message first to verify it exists
            try:
                msg = await bot_client.get_messages(
                    chat_id=chat_id,
                    message_ids=int(msg_id),
                )

                if msg is None or getattr(msg, "empty", False):
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                    continue

                LOGGER.info(
                    f"Found message {msg_id} in chat {chat_id}, attempting to delete",
                )
            except Exception as e:
                LOGGER.error(
                    f"Error getting message {msg_id} in chat {chat_id}: {e}",
                )

            # Make sure message_id is an integer
            message_id_int = int(msg_id)
            result = await bot_client.delete_messages(
                chat_id=chat_id,
                message_ids=[message_id_int],  # Pass as a list with a single item
            )
            LOGGER.info(
                f"Delete API call result for message {msg_id} in chat {chat_id}: {result}",
            )
            LOGGER.info(
                f"Successfully deleted message {msg_id} in chat {chat_id} using bot {bot_id}",
            )
            success_count += 1
            # Remove from database after successful deletion
            try:
                await database.remove_scheduled_deletion(chat_id, msg_id)
                removed_from_db_count += 1
            except Exception as e:
                LOGGER.error(
                    f"Error removing scheduled deletion after successful deletion: {e}"
                )
        except Exception as e:
            error_str = str(e)
            # Handle different types of errors appropriately
            if "MESSAGE_DELETE_FORBIDDEN" in error_str or "403" in error_str:
                LOGGER.warning(
                    f"Cannot delete message {msg_id} in chat {chat_id}: {error_str}"
                )
                # Remove from database since we can't delete it
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for forbidden message: {e}"
                    )
            elif "MESSAGE_ID_INVALID" in error_str or "400" in error_str:
                LOGGER.error(
                    f"Message {msg_id} in chat {chat_id} no longer exists: {error_str}"
                )
                # Remove from database since message doesn't exist
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for invalid message: {e}"
                    )
            elif (
                "CHANNEL_INVALID" in error_str
                or "CHAT_INVALID" in error_str
                or "USER_INVALID" in error_str
                or "PEER_ID_INVALID" in error_str
            ):
                LOGGER.warning(f"Chat {chat_id} is invalid: {error_str}")
                # Remove from database since the chat is invalid
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for invalid chat: {e}"
                    )
            else:
                # Log other errors as actual errors
                LOGGER.error(
                    f"Failed to delete message {msg_id} in chat {chat_id}: {e}"
                )
                fail_count += 1

    # Update the message with results
    result_msg = "Deletion results:\n"
    result_msg += f"✅ Successfully deleted: {success_count}\n"
    result_msg += f"❌ Failed to delete: {fail_count}\n"
    result_msg += f"🗑️ Removed from database: {removed_from_db_count}\n"

    await edit_message(callback_query.message, result_msg)


@new_task
async def force_delete_all_messages(_, callback_query):
    """Force delete all scheduled messages regardless of due time"""
    from bot.core.config_manager import get_config_bool

    # Check if scheduled deletion is enabled
    if not get_config_bool("SCHEDULED_DELETION_ENABLED", True):
        await callback_query.answer(
            "Scheduled deletion functionality is disabled via configuration",
            show_alert=True,
        )
        return

    user_id = callback_query.from_user.id
    if (
        user_id != Config.OWNER_ID
        and user_id not in sudo_users
        and not (user_id in user_data and user_data[user_id].get("SUDO"))
    ):
        await callback_query.answer(
            "This action is only for sudo users",
            show_alert=True,
        )
        return

    await callback_query.answer("Processing...")

    # Get all scheduled deletions
    all_deletions = await database.get_all_scheduled_deletions()

    if not all_deletions:
        await edit_message(callback_query.message, "No scheduled deletions found")
        return

    # Process each scheduled deletion
    success_count = 0
    fail_count = 0
    removed_from_db_count = 0

    for entry in all_deletions:
        chat_id = entry["chat_id"]
        msg_id = entry["message_id"]
        bot_id = entry["bot_id"]

        # Get the appropriate bot client
        bot_client = None
        if bot_id == TgClient.ID:
            bot_client = TgClient.bot
        elif hasattr(TgClient, "helper_bots") and bot_id in TgClient.helper_bots:
            bot_client = TgClient.helper_bots[bot_id]

        if bot_client is None:
            fail_count += 1
            continue

        try:
            # Try to get the message first to verify it exists
            try:
                msg = await bot_client.get_messages(
                    chat_id=chat_id,
                    message_ids=int(msg_id),
                )

                if msg is None or getattr(msg, "empty", False):
                    # Message not found, removing from database
                    try:
                        await database.remove_scheduled_deletion(chat_id, msg_id)
                        removed_from_db_count += 1
                    except Exception as e:
                        LOGGER.error(
                            f"Error removing scheduled deletion for missing message: {e}"
                        )
                    continue

                # Message found, will attempt to delete
            except Exception:
                # Error getting message, skipping
                continue

            # Make sure message_id is an integer
            message_id_int = int(msg_id)
            await bot_client.delete_messages(
                chat_id=chat_id,
                message_ids=[message_id_int],  # Pass as a list with a single item
            )
            # Successfully deleted the message
            success_count += 1
            # Remove from database after successful deletion
            try:
                await database.remove_scheduled_deletion(chat_id, msg_id)
                removed_from_db_count += 1
            except Exception as e:
                LOGGER.error(
                    f"Error removing scheduled deletion after successful deletion: {e}"
                )
        except Exception as e:
            error_str = str(e)
            # Handle different types of errors appropriately
            if "MESSAGE_DELETE_FORBIDDEN" in error_str or "403" in error_str:
                # Cannot delete message due to permissions, remove from database
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for forbidden message: {e}"
                    )
            elif "MESSAGE_ID_INVALID" in error_str or "400" in error_str:
                # Message doesn't exist, remove from database
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for invalid message: {e}"
                    )
            elif (
                "CHANNEL_INVALID" in error_str
                or "CHAT_INVALID" in error_str
                or "USER_INVALID" in error_str
                or "PEER_ID_INVALID" in error_str
            ):
                # Chat is invalid, removing from database
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for invalid chat: {e}"
                    )
            else:
                # Other errors count as failures
                fail_count += 1

    # Update the message with results
    result_msg = "Force deletion results:\n"
    result_msg += f"✅ Successfully deleted: {success_count}\n"
    result_msg += f"❌ Failed to delete: {fail_count}\n"
    result_msg += f"🗑️ Removed from database: {removed_from_db_count}\n"

    await edit_message(callback_query.message, result_msg)


# Handler registration is now done in handlers.py
LOGGER.info("Check deletion module loaded")
