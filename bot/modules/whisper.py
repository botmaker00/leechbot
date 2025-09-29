"""
Whisper Message Module for Telegram Bot

This module implements a whisper message system that allows sending private messages
in group chats that only the intended recipient can see. The whisper is sent as a
callback query response when the recipient clicks on the whisper button.

Usage:
- Reply to a user's message with: /whisper <message>
- The bot will create an inline button that only the replied user can interact with
- When clicked, the whisper message is shown privately to that user
"""

import asyncio

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.message_utils import delete_message, send_message

# Store whisper messages temporarily (in production, consider using a database)
whisper_storage = {}

# Statistics for whisper usage
whisper_stats = {
    "total_created": 0,
    "total_read": 0,
    "total_expired": 0,
}


async def parse_whisper_targets(client, message, target_text):
    """
    Parse target users from -to flag (usernames or user IDs)
    Returns list of target users
    """
    targets = []
    target_parts = target_text.split()

    for target in target_parts:
        target = target.strip()
        if not target:
            continue

        try:
            # Try to parse as user ID (numeric)
            if target.isdigit():
                user_id = int(target)
                try:
                    user = await client.get_users(user_id)
                    targets.append(user)
                except Exception:
                    LOGGER.warning(f"Could not find user with ID: {user_id}")
                    continue

            # Try to parse as username (remove @ if present)
            else:
                username = target.lstrip("@")
                try:
                    user = await client.get_users(username)
                    targets.append(user)
                except Exception:
                    LOGGER.warning(f"Could not find user with username: {username}")
                    continue

        except Exception as e:
            LOGGER.error(f"Error parsing target {target}: {e}")
            continue

    return targets


@new_task
async def whisper_command(client, message: Message):
    """
    Handle /whisper command to create whisper messages

    Usage:
    1. Reply to a user's message: /whisper <your_message>
    2. Target specific users: /whisper <your_message> -to <user_id/username> [user_id/username...]
    """
    try:
        # Check if message has text and extract whisper content
        if not message.text or len(message.text.split()) < 2:
            await send_message(
                message,
                "❌ <b>Usage Error</b>\n\n"
                "<b>Method 1:</b> Reply to a user's message\n"
                "<code>/whisper your_message_here</code>\n\n"
                "<b>Method 2:</b> Target specific users\n"
                "<code>/whisper your_message -to user_id @username</code>\n\n"
                "You can target multiple users by separating them with spaces.",
            )
            return

        # Parse the command text
        if not message.text:
            await send_message(
                message,
                "❌ <b>No Message Provided</b>\n\n"
                "Please provide a message with the whisper command.",
            )
            return

        command_parts = message.text.split(None, 1)[1]  # Everything after /whisper

        # Check if -to flag is used
        if " -to " in command_parts:
            # Split by -to flag
            parts = command_parts.split(" -to ", 1)
            whisper_text = parts[0].strip()
            target_text = parts[1].strip()

            if not whisper_text:
                await send_message(
                    message,
                    "❌ <b>No Message Provided</b>\n\n"
                    "Please provide a message before the -to flag:\n"
                    "<code>/whisper your_message -to user_id @username</code>",
                )
                return

            if not target_text:
                await send_message(
                    message,
                    "❌ <b>No Targets Provided</b>\n\n"
                    "Please provide user IDs or usernames after -to:\n"
                    "<code>/whisper your_message -to user_id @username</code>",
                )
                return

            # Parse target users
            target_users = await parse_whisper_targets(client, message, target_text)

            if not target_users:
                await send_message(
                    message,
                    "❌ <b>No Valid Targets Found</b>\n\n"
                    "Could not find any of the specified users.\n"
                    "Make sure user IDs are correct and usernames exist.",
                )
                return

            reply_to_message_id = None  # No reply when using -to flag

        else:
            # Traditional reply-based whisper
            if not message.reply_to_message:
                await send_message(
                    message,
                    "❌ <b>Usage Error</b>\n\n"
                    "<b>Method 1:</b> Reply to a user's message\n"
                    "<code>/whisper your_message_here</code>\n\n"
                    "<b>Method 2:</b> Target specific users\n"
                    "<code>/whisper your_message -to user_id @username</code>",
                )
                return

            whisper_text = command_parts
            target_user = message.reply_to_message.from_user

            if not target_user:
                await send_message(
                    message,
                    "❌ <b>Error</b>\n\n"
                    "Cannot send whisper to this message (no user information).",
                )
                return

            target_users = [target_user]
            reply_to_message_id = message.reply_to_message.id

        # Get sender info
        sender_user = message.from_user
        chat_id = message.chat.id

        # Remove sender from targets if present
        target_users = [user for user in target_users if user.id != sender_user.id]

        if not target_users:
            await send_message(
                message,
                "❌ <b>Cannot Whisper to Yourself</b>\n\n"
                "You cannot send a whisper message to yourself only.",
            )
            return

        # Delete the original command message immediately for privacy
        await delete_message(message)

        # Create whispers for each target user
        whisper_ids = []
        for target_user in target_users:
            # Generate unique whisper ID
            whisper_id = (
                f"{sender_user.id}_{target_user.id}_{message.id}_{len(whisper_ids)}"
            )
            whisper_ids.append(whisper_id)

            # Store whisper data
            whisper_storage[whisper_id] = {
                "message": whisper_text,
                "sender_id": sender_user.id,
                "sender_name": sender_user.first_name,
                "target_id": target_user.id,
                "target_name": target_user.first_name,
                "chat_id": chat_id,
                "timestamp": asyncio.get_event_loop().time(),
            }

        # Create inline keyboard with whisper buttons for each target
        keyboard_buttons = []
        for i, target_user in enumerate(target_users):
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        f"💬 Whisper for @{target_user.username or target_user.first_name}",
                        callback_data=f"whisper_{whisper_ids[i]}",
                    )
                ]
            )

        # Add help button
        keyboard_buttons.append(
            [InlineKeyboardButton("❓ What is this?", callback_data="whisper_help")]
        )

        keyboard = InlineKeyboardMarkup(keyboard_buttons)

        # Create notification message
        if len(target_users) == 1:
            target_mention = target_users[0].mention
            whisper_notification = (
                f"🤫 <b>Whisper Message</b>\n\n"
                f"👤 <b>From:</b> {sender_user.mention}\n"
                f"👥 <b>To:</b> {target_mention}\n\n"
                f"💡 <i>Click the button below to read the whisper message.</i>\n"
                f"⚠️ <i>Only {target_users[0].first_name} can see this message.</i>"
            )
        else:
            target_mentions = ", ".join([user.mention for user in target_users])
            target_names = ", ".join([user.first_name for user in target_users])
            whisper_notification = (
                f"🤫 <b>Whisper Message</b>\n\n"
                f"👤 <b>From:</b> {sender_user.mention}\n"
                f"👥 <b>To:</b> {target_mentions}\n\n"
                f"💡 <i>Click your button below to read the whisper message.</i>\n"
                f"⚠️ <i>Only {target_names} can see this message.</i>"
            )

        # Send whisper notification to the chat
        send_kwargs = {
            "chat_id": chat_id,
            "text": whisper_notification,
            "reply_markup": keyboard,
        }

        if reply_to_message_id:
            send_kwargs["reply_to_message_id"] = reply_to_message_id

        await TgClient.bot.send_message(**send_kwargs)

        # Update statistics
        whisper_stats["total_created"] += len(target_users)

        target_ids = [user.id for user in target_users]
        LOGGER.info(
            f"Whisper created: {sender_user.id} -> {target_ids} in chat {chat_id}"
        )

    except Exception as e:
        LOGGER.error(f"Error in whisper_command: {e}")
        try:
            await send_message(
                message,
                "❌ <b>Error</b>\n\n"
                "Failed to create whisper message. Please try again.",
            )
        except Exception:
            # If message was already deleted, we can't send error message
            pass


@new_task
async def whisper_callback(_, callback_query):
    """
    Handle whisper callback queries
    """
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id

        if data == "whisper_help":
            help_text = (
                "🤫 <b>Whisper Messages</b>\n\n"
                "Private messages only you can see.\n\n"
                "1️⃣ Someone replies to you with /whisper\n"
                "2️⃣ Click the button to read it\n"
                "3️⃣ Message shows only to you\n\n"
                "🔒 Private • ⏰ Expires in 1 hour"
            )
            await callback_query.answer(help_text, show_alert=True)
            return

        if data.startswith("whisper_"):
            whisper_id = data.replace("whisper_", "")

            # Check if whisper exists
            if whisper_id not in whisper_storage:
                whisper_stats["total_expired"] += 1
                await callback_query.answer(
                    "❌ This whisper message has expired or doesn't exist.",
                    show_alert=True,
                )
                return

            whisper_data = whisper_storage[whisper_id]

            # Check if user is authorized to read this whisper
            if user_id != whisper_data["target_id"]:
                await callback_query.answer(
                    "🚫 This whisper message is not for you!", show_alert=True
                )
                return

            # Show the whisper message
            whisper_message = (
                f"🤫 <b>Whisper from {whisper_data['sender_name']}</b>\n\n"
                f"💬 <i>{whisper_data['message']}</i>"
            )

            await callback_query.answer(whisper_message, show_alert=True)

            # Update statistics
            whisper_stats["total_read"] += 1

            # Optional: Remove whisper after reading (uncomment if desired)
            # del whisper_storage[whisper_id]

    except Exception as e:
        LOGGER.error(f"Error in whisper_callback: {e}")
        await callback_query.answer(
            "❌ Error processing whisper message.", show_alert=True
        )


# Cleanup function to remove old whispers (optional)
async def cleanup_old_whispers():
    """Remove whispers older than 1 hour"""
    current_time = asyncio.get_event_loop().time()
    expired_whispers = []

    for whisper_id, data in whisper_storage.items():
        if current_time - data["timestamp"] > 3600:  # 1 hour
            expired_whispers.append(whisper_id)

    for whisper_id in expired_whispers:
        del whisper_storage[whisper_id]
        whisper_stats["total_expired"] += 1


# Auto-cleanup task (runs every 30 minutes)
async def start_whisper_cleanup():
    """Start the whisper cleanup task"""
    while True:
        await asyncio.sleep(1800)  # 30 minutes
        await cleanup_old_whispers()
