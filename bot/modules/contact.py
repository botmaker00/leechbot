from asyncio import sleep
from time import time

from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from pyrogram.types import Message

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import send_message


@new_task
async def contact_command(client, message: Message):
    """
    Handle /contact command:
    - For owner: /contact user-id/@username msg (to contact users)
    - For users: /contact <message> (to contact owner)
    """
    user_id = message.from_user.id

    # Check if OWNER_ID is properly configured
    if Config.OWNER_ID == 0:
        LOGGER.warning("OWNER_ID is not configured (set to 0)")
        # Fallback: check if user is a sudo user
        if await CustomFilters.sudo(client, message):
            await handle_owner_contact(client, message)
            return
    elif user_id == Config.OWNER_ID:
        await handle_owner_contact(client, message)
        return

    # Handle regular user contact to owner
    await handle_user_contact(client, message)


@new_task
async def handle_owner_contact(client, message: Message):
    """
    Handle owner contacting users via /contact user-id/@username msg
    """
    if not message.text:
        await send_message(message, "❌ No command text provided.")
        return

    command_parts = message.text.split(maxsplit=2)

    if len(command_parts) < 3:
        await send_message(
            message,
            "❌ Please provide target user and message.\n\n"
            "Usage:\n"
            "• `/contact user_id message`\n"
            "• `/contact @username message`\n\n"
            "You can also reply to any message with `/contact user_id/@username message`",
        )
        return

    target_identifier = command_parts[1]
    owner_message = command_parts[2]

    # Parse target user (user_id or @username)
    target_user_id = None

    if target_identifier.startswith("@"):
        # Handle @username
        username = target_identifier[1:]  # Remove @
        try:
            user_info = await client.get_users(username)
            target_user_id = user_info.id
        except Exception as e:
            await send_message(message, f"❌ Failed to find user @{username}: {e}")
            return
    else:
        # Handle user_id
        try:
            target_user_id = int(target_identifier)
        except ValueError:
            await send_message(
                message,
                "❌ Invalid user identifier. Use numeric user_id or @username",
            )
            return

    # Check if target user has started the bot (exists in database)
    if not await has_user_started_bot(target_user_id):
        await send_message(
            message,
            f"❌ User {target_identifier} has not started the bot in private.",
        )
        return

    # Handle reply to message case
    if message.reply_to_message:
        await handle_owner_reply_contact(
            client, message, target_user_id, owner_message
        )
        return

    # Send message to target user
    try:
        generic_message = f"📩 <b>Message from Owner</b>\n\n{owner_message}"
        await client.send_message(target_user_id, generic_message)
        await send_message(message, f"✅ Message sent to user {target_identifier}")
        LOGGER.info(f"Owner contacted user {target_user_id}")
    except (UserIsBlocked, InputUserDeactivated):
        await send_message(
            message,
            f"❌ Cannot send message to {target_identifier}. User has blocked the bot or account is deactivated.",
        )
    except Exception as e:
        await send_message(message, f"❌ Failed to send message: {e}")
        LOGGER.error(f"Failed to send owner message to user {target_user_id}: {e}")


async def handle_owner_reply_contact(
    client, message: Message, target_user_id: int, owner_message: str
):
    """
    Handle owner replying to a message and forwarding it to target user
    """
    try:
        replied_msg = message.reply_to_message

        # Send the original message/media first
        if replied_msg.media:
            # Copy media to target user
            await replied_msg.copy(target_user_id, disable_notification=True)
        elif replied_msg.text:
            # Send text message
            await client.send_message(target_user_id, replied_msg.text)

        # Send the additional message from owner
        if owner_message:
            generic_message = f"📩 <b>Message from Owner</b>\n\n{owner_message}"
            await client.send_message(target_user_id, generic_message)

        await send_message(
            message,
            f"✅ Replied message and your message sent to user {target_user_id}",
        )
        LOGGER.info(f"Owner sent reply and message to user {target_user_id}")

    except (UserIsBlocked, InputUserDeactivated):
        await send_message(
            message,
            f"❌ Cannot send message to user {target_user_id}. User has blocked the bot or account is deactivated.",
        )
    except Exception as e:
        await send_message(message, f"❌ Failed to send reply: {e}")
        LOGGER.error(f"Failed to send owner reply to user {target_user_id}: {e}")


@new_task
async def handle_user_contact(client, message: Message):
    """
    Handle regular users contacting the owner
    """
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    first_name = message.from_user.first_name or "Unknown"

    # Check if user is banned from using contact feature
    if await is_user_banned(user_id):
        await send_message(
            message, "❌ You have been banned from using the contact feature."
        )
        return

    # Get the message text after /contact command
    if not message.text:
        await send_message(message, "❌ No message text provided.")
        return

    command_parts = message.text.split(maxsplit=1)

    # Check if this is a reply to media with /contact
    if message.reply_to_message:
        replied_msg = message.reply_to_message

        # Check if the replied message has media
        if replied_msg.media:
            # Forward the media to owner with user info
            await forward_media_to_owner(replied_msg, user_id, username, first_name)

            # If there's additional text with the command, send it too
            if len(command_parts) > 1:
                additional_text = command_parts[1]
                await send_text_to_owner(
                    additional_text, user_id, username, first_name
                )

            await send_message(
                message, "✅ Your media and message have been sent to the owner."
            )
            return

        # If replying to a text message, include both the original and new text
        original_text = replied_msg.text or replied_msg.caption or "No text content"
        if len(command_parts) > 1:
            combined_text = f"Original message: {original_text}\n\nAdditional message: {command_parts[1]}"
        else:
            combined_text = f"Forwarded message: {original_text}"

        await send_text_to_owner(combined_text, user_id, username, first_name)
        await send_message(message, "✅ Your message has been sent to the owner.")
        return

    # Handle regular text message
    if len(command_parts) < 2:
        await send_message(
            message,
            "❌ Please provide a message after /contact command.\n\n"
            "Usage:\n"
            "• `/contact Your message here`\n"
            "• Reply to any media with `/contact` to send it to owner\n"
            "• Reply to any media with `/contact additional message` to send both",
        )
        return

    user_message = command_parts[1]
    await send_text_to_owner(user_message, user_id, username, first_name)

    await send_message(message, "✅ Your message has been sent to the owner.")


async def send_text_to_owner(
    text: str, user_id: int, username: str, first_name: str
):
    """Send a text message to the owner with user information."""
    owner_message = (
        f"📩 <b>New Contact Message</b>\n\n"
        f"👤 <b>From:</b> {first_name}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"👤 <b>Username:</b> @{username}\n\n"
        f"💬 <b>Message:</b>\n{text}"
    )

    try:
        await send_message(Config.OWNER_ID, owner_message)
        LOGGER.info(f"Contact message sent to owner from user {user_id}")
    except Exception as e:
        LOGGER.error(f"Failed to send contact message to owner: {e}")


async def forward_media_to_owner(
    media_message: Message, user_id: int, username: str, first_name: str
):
    """Forward media message to owner with user information."""
    try:
        # First send user info
        user_info = (
            f"📩 <b>New Contact Media</b>\n\n"
            f"👤 <b>From:</b> {first_name}\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"👤 <b>Username:</b> @{username}"
        )

        await send_message(Config.OWNER_ID, user_info)

        # Then copy the media message with FloodWait handling
        try:
            await media_message.copy(Config.OWNER_ID, disable_notification=True)
        except FloodWait as f:
            await sleep(f.value * 1.2)
            await media_message.copy(Config.OWNER_ID, disable_notification=True)

        LOGGER.info(f"Contact media sent to owner from user {user_id}")
    except Exception as e:
        LOGGER.error(f"Failed to send contact media to owner: {e}")


@new_task
async def ban_command(client, message: Message):
    """
    Handle /ban command to ban users from using contact feature.
    Usage: /ban <user_id> or reply to a user's message with /ban
    Only available to sudo users.
    """
    if not await CustomFilters.sudo(client, message):
        await send_message(
            message, "❌ This command is only available to sudo users."
        )
        return

    user_id_to_ban = None
    if not message.text:
        await send_message(message, "❌ No command text provided.")
        return

    command_parts = message.text.split()

    # Check if replying to a message
    if message.reply_to_message and message.reply_to_message.from_user:
        user_id_to_ban = message.reply_to_message.from_user.id
        username = message.reply_to_message.from_user.username or "No username"
        first_name = message.reply_to_message.from_user.first_name or "Unknown"
    elif len(command_parts) >= 2:
        # Try to parse user ID from command
        try:
            user_id_to_ban = int(command_parts[1])
            username = "Unknown"
            first_name = "Unknown"
        except ValueError:
            await send_message(
                message,
                "❌ Invalid user ID. Please provide a valid numeric user ID or reply to a user's message.",
            )
            return
    else:
        await send_message(
            message,
            "❌ Please provide a user ID or reply to a user's message.\n\n"
            "Usage:\n"
            "• `/ban <user_id>`\n"
            "• Reply to a user's message with `/ban`",
        )
        return

    # Check if user is already banned
    if await is_user_banned(user_id_to_ban):
        await send_message(
            message,
            f"❌ User {user_id_to_ban} is already banned from using the contact feature.",
        )
        return

    # Ban the user
    try:
        await ban_user_from_contact(user_id_to_ban)
        await send_message(
            message,
            f"✅ User {user_id_to_ban} ({first_name} - @{username}) has been banned from using the contact feature.",
        )
        LOGGER.info(
            f"User {user_id_to_ban} banned from contact feature by {message.from_user.id}"
        )
    except Exception as e:
        await send_message(message, f"❌ Failed to ban user: {e}")
        LOGGER.error(f"Failed to ban user {user_id_to_ban}: {e}")


async def has_user_started_bot(user_id: int) -> bool:
    """Check if a user has started the bot (exists in database)."""
    try:
        # Check if user exists in the users collection
        result = await database.db.users.find_one({"_id": user_id})
        return result is not None
    except Exception as e:
        LOGGER.error(f"Error checking if user {user_id} has started bot: {e}")
        return False


async def is_user_banned(user_id: int) -> bool:
    """Check if a user is banned from using the contact feature."""
    try:
        result = await database.db.contact_bans.find_one({"_id": user_id})
        return result is not None
    except Exception as e:
        LOGGER.error(f"Error checking if user {user_id} is banned: {e}")
        return False


async def ban_user_from_contact(user_id: int):
    """Ban a user from using the contact feature."""
    try:
        await database.db.contact_bans.update_one(
            {"_id": user_id},
            {"$set": {"banned": True, "banned_at": time()}},
            upsert=True,
        )
    except Exception as e:
        LOGGER.error(f"Error banning user {user_id}: {e}")
        raise


async def unban_user_from_contact(user_id: int):
    """Unban a user from using the contact feature."""
    try:
        await database.db.contact_bans.delete_one({"_id": user_id})
    except Exception as e:
        LOGGER.error(f"Error unbanning user {user_id}: {e}")
        raise


@new_task
async def unban_command(client, message: Message):
    """
    Handle /unban command to unban users from using contact feature.
    Usage: /unban <user_id> or reply to a user's message with /unban
    Only available to sudo users.
    """
    if not await CustomFilters.sudo(client, message):
        await send_message(
            message, "❌ This command is only available to sudo users."
        )
        return

    user_id_to_unban = None
    if not message.text:
        await send_message(message, "❌ No command text provided.")
        return

    command_parts = message.text.split()

    # Check if replying to a message
    if message.reply_to_message and message.reply_to_message.from_user:
        user_id_to_unban = message.reply_to_message.from_user.id
        username = message.reply_to_message.from_user.username or "No username"
        first_name = message.reply_to_message.from_user.first_name or "Unknown"
    elif len(command_parts) >= 2:
        # Try to parse user ID from command
        try:
            user_id_to_unban = int(command_parts[1])
            username = "Unknown"
            first_name = "Unknown"
        except ValueError:
            await send_message(
                message,
                "❌ Invalid user ID. Please provide a valid numeric user ID or reply to a user's message.",
            )
            return
    else:
        await send_message(
            message,
            "❌ Please provide a user ID or reply to a user's message.\n\n"
            "Usage:\n"
            "• `/unban <user_id>`\n"
            "• Reply to a user's message with `/unban`",
        )
        return

    # Check if user is actually banned
    if not await is_user_banned(user_id_to_unban):
        await send_message(
            message,
            f"❌ User {user_id_to_unban} is not banned from using the contact feature.",
        )
        return

    # Unban the user
    try:
        await unban_user_from_contact(user_id_to_unban)
        await send_message(
            message,
            f"✅ User {user_id_to_unban} ({first_name} - @{username}) has been unbanned from using the contact feature.",
        )
        LOGGER.info(
            f"User {user_id_to_unban} unbanned from contact feature by {message.from_user.id}"
        )
    except Exception as e:
        await send_message(message, f"❌ Failed to unban user: {e}")
        LOGGER.error(f"Failed to unban user {user_id_to_unban}: {e}")
