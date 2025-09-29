import asyncio
import traceback
from logging import getLogger
from time import time

from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked

from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.message_utils import edit_message, send_message

LOGGER = getLogger(__name__)

# Track broadcast state - use a dictionary to track by user ID
# This allows multiple admins to use broadcast without interfering with each other
broadcast_awaiting_message = {}


@new_task
async def broadcast(_, message):
    """
    Original broadcast function that broadcasts a replied-to message

    This function is kept for backward compatibility
    """
    # Check if user is owner
    if not await is_owner(message):
        return

    if not message.reply_to_message:
        await send_message(
            message,
            "Reply to any message to broadcast messages to users in Bot PM.",
        )
        return

    total, successful, blocked, unsuccessful = 0, 0, 0, 0
    start_time = time()
    updater = time()
    broadcast_message = await send_message(message, "Broadcast in progress...")

    # Get the message to broadcast
    msg_to_broadcast = message.reply_to_message

    try:
        pm_users = await database.get_pm_uids()
        if not pm_users:
            await edit_message(broadcast_message, "No users found in database.")
            return

        LOGGER.info(f"Starting broadcast to {len(pm_users)} users")

        for uid in pm_users:
            try:
                # Use copy method which handles all media types automatically
                await msg_to_broadcast.copy(uid)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await msg_to_broadcast.copy(uid)
                    successful += 1
                except Exception as retry_err:
                    LOGGER.error(
                        f"Failed to send broadcast to {uid} after FloodWait: {retry_err!s}"
                    )
                    unsuccessful += 1
            except (UserIsBlocked, InputUserDeactivated) as user_err:
                LOGGER.info(f"Removing user {uid} from database: {user_err!s}")
                await database.rm_pm_user(uid)
                blocked += 1
            except Exception as e:
                LOGGER.error(f"Error sending broadcast to {uid}: {e!s}")
                unsuccessful += 1

            total += 1

            if (time() - updater) > 10:
                status = generate_status(total, successful, blocked, unsuccessful)
                await edit_message(broadcast_message, status)
                updater = time()
                LOGGER.info(
                    f"Broadcast progress: {successful}/{total} successful, {blocked} blocked, {unsuccessful} failed"
                )

        elapsed_time = get_readable_time(time() - start_time, True)
        status = generate_status(
            total, successful, blocked, unsuccessful, elapsed_time
        )
        await edit_message(broadcast_message, status)
        LOGGER.info(
            f"Broadcast completed: {successful}/{total} successful, {blocked} blocked, {unsuccessful} failed, time: {elapsed_time}"
        )

    except Exception as e:
        error_traceback = traceback.format_exc()
        LOGGER.error(f"Broadcast failed with error: {e!s}\n{error_traceback}")
        await edit_message(
            broadcast_message,
            f"<b>❌ Broadcast failed with error:</b>\n<code>{e!s}</code>",
        )
        return


# Enhanced broadcast function that supports a two-step process and multiple media types
@new_task
async def broadcast_media(client, message, options=None):
    """
    Enhanced broadcast function with support for various media types

    Args:
        client: The bot client
        message: The message object
        options: If None, this is the first step. If True, this is the second step.
    """
    global broadcast_awaiting_message

    # For handlers that pass options as a positional argument
    # Convert it to the expected type
    if options is not None and not isinstance(options, bool):
        options = True

    # Only allow owner to use this command
    if not await is_owner(message):
        return

    # First step: Ask for the message to broadcast
    if options is None:
        user_id = message.from_user.id
        LOGGER.info(f"Broadcast command initiated by owner {user_id}")

        # Set this user as waiting for broadcast message
        broadcast_awaiting_message[user_id] = True

        await send_message(
            message,
            "<b>🎙️ Send Any Message to Broadcast in HTML\n\nTo Cancel: /cancelbc</b>",
            markdown=False,  # Use HTML mode (not markdown)
        )
        # Set up handler for the next message
        # This is handled by the core handlers system
        return

    # Check for cancellation - this is now handled in the main handler section below
    # to avoid duplicate code and ensure consistent behavior

    # Check if we're actually waiting for a message
    user_id = message.from_user.id

    # Special handling for /cancelbc command is now in a dedicated function
    # handle_cancel_broadcast_command

    # Check if we're waiting for a message from this user
    if user_id not in broadcast_awaiting_message:
        return

    # Determine message type for logging
    msg_type = "unknown"
    if message.text:
        msg_type = "text"
    elif message.photo:
        msg_type = "photo"
    elif message.video:
        msg_type = "video"
    elif message.document:
        msg_type = "document"
    elif message.audio:
        msg_type = "audio"
    elif message.voice:
        msg_type = "voice"
    elif message.sticker:
        msg_type = "sticker"
    elif message.animation:
        msg_type = "animation"

    LOGGER.info(f"Broadcasting message of type: {msg_type}")

    # Initialize counters
    total, successful, blocked, unsuccessful = 0, 0, 0, 0
    start_time = time()
    updater = time()
    broadcast_message = await send_message(message, "Broadcast in progress...")

    # Get all PM users
    try:
        # Reset the broadcast state for this user
        user_id = message.from_user.id
        broadcast_awaiting_message.pop(user_id, None)

        pm_users = await database.get_pm_uids()
        if not pm_users:
            await edit_message(broadcast_message, "No users found in database.")
            return

        # Start broadcasting to users
        LOGGER.info(f"Starting broadcast to {len(pm_users)} users")

        for uid in pm_users:
            try:
                # Use the copy method which handles all media types automatically
                result = await message.copy(uid)

                if result:
                    successful += 1
                else:
                    unsuccessful += 1
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await message.copy(uid)
                    successful += 1
                except Exception:
                    unsuccessful += 1
            except (UserIsBlocked, InputUserDeactivated):
                await database.rm_pm_user(uid)
                blocked += 1
            except Exception:
                unsuccessful += 1

            total += 1

            if (time() - updater) > 10:
                status = generate_status(total, successful, blocked, unsuccessful)
                await edit_message(broadcast_message, status)
                updater = time()

        elapsed_time = get_readable_time(time() - start_time, True)
        status = generate_status(
            total, successful, blocked, unsuccessful, elapsed_time
        )
        await edit_message(broadcast_message, status)
        LOGGER.info(f"Broadcast completed in {elapsed_time}")

    except Exception as e:
        error_traceback = traceback.format_exc()
        LOGGER.error(f"Broadcast failed with error: {e!s}\n{error_traceback}")
        await edit_message(
            broadcast_message,
            f"<b>❌ Broadcast failed with error:</b>\n<code>{e!s}</code>",
        )
        return


def generate_status(total, successful, blocked, unsuccessful, elapsed_time=""):
    status = "<b>Broadcast Stats :</b>\n\n"
    status += f"<b>• Total users:</b> {total}\n"
    status += f"<b>• Success:</b> {successful}\n"
    status += f"<b>• Blocked or deleted:</b> {blocked}\n"
    status += f"<b>• Unsuccessful attempts:</b> {unsuccessful}"
    if elapsed_time:
        status += f"\n\n<b>Elapsed Time:</b> {elapsed_time}"
    return status


async def is_owner(message):
    """Check if the user is the owner of the bot"""
    from bot.helper.telegram_helper.filters import CustomFilters

    return await CustomFilters.owner("", message)


@new_task
async def handle_broadcast_command(client, message):
    """
    Wrapper function to handle the broadcast command
    This ensures the coroutine is properly awaited
    """
    return await broadcast_media(client, message)


@new_task
async def handle_broadcast_media(client, message):
    """
    Dedicated function to handle media messages for broadcast
    This ensures media messages are properly processed
    """
    user_id = message.from_user.id

    # Check if we're waiting for a broadcast message from this user
    if user_id not in broadcast_awaiting_message:
        return None

    # Determine message type for logging
    msg_type = "unknown"
    if message.photo:
        msg_type = "photo"
    elif message.video:
        msg_type = "video"
    elif message.document:
        msg_type = "document"
    elif message.audio:
        msg_type = "audio"
    elif message.voice:
        msg_type = "voice"
    elif message.sticker:
        msg_type = "sticker"
    elif message.animation:
        msg_type = "animation"

    LOGGER.info(f"Processing {msg_type} message for broadcast")

    # Process the broadcast with the media message
    return await broadcast_media(client, message, True)


@new_task
async def handle_cancel_broadcast_command(client, message):
    """
    Dedicated function to handle the /cancelbc command
    """
    user_id = message.from_user.id
    LOGGER.info(f"Cancel broadcast command received from user {user_id}")

    if user_id in broadcast_awaiting_message:
        del broadcast_awaiting_message[user_id]
        await send_message(
            message,
            "<b>❌ Broadcast Cancelled</b>",
            markdown=False,  # Use HTML mode (not markdown)
        )
    else:
        await send_message(
            message,
            "<b>❓ No broadcast in progress</b>",
            markdown=False,  # Use HTML mode (not markdown)
        )
