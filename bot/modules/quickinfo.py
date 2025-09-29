from pyrogram.enums import ChatType
from pyrogram.types import CallbackQuery, Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    send_message,
)
from bot.helper.telegram_helper.quickinfo_buttons import (
    get_appropriate_quickinfo_buttons,
    get_quickinfo_inline_buttons,
)
from bot.helper.telegram_helper.quickinfo_utils import (
    formatter,
    get_quickinfo_help_text,
    is_quickinfo_enabled,
)


async def get_full_chat_info(chat_id):
    """Get full chat information using chat ID"""
    try:
        return await TgClient.bot.get_chat(chat_id)
    except Exception as e:
        # Don't log as error for common permission issues
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in [
                "channel_invalid",
                "channel_private",
                "chat_admin_required",
                "peer_id_invalid",
                "forbidden",
                "access_denied",
            ]
        ):
            # These are expected for private/inaccessible chats
            return None
        # Log unexpected errors
        LOGGER.error(f"Unexpected error getting chat info for {chat_id}: {e}")
        return None


async def get_full_user_info(user_id):
    """Get full user information using user ID"""
    try:
        return await TgClient.bot.get_users(user_id)
    except Exception as e:
        # Don't log as error for common permission issues
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in [
                "user_id_invalid",
                "peer_id_invalid",
                "user_not_found",
                "forbidden",
                "access_denied",
                "user_privacy_restricted",
            ]
        ):
            # These are expected for private/inaccessible users
            return None
        # Log unexpected errors
        LOGGER.error(f"Unexpected error getting user info for {user_id}: {e}")
        return None


async def quickinfo_command(client, message: Message):
    """Handle /quickinfo command - includes both menu and current chat info"""
    if not is_quickinfo_enabled():
        await send_message(
            message,
            "❌ <b>QuickInfo feature is currently disabled by the administrator.</b>",
        )
        return

    chat = message.chat

    # Check if command has arguments to show current chat info
    if len(message.command) > 1 and message.command[1].lower() in [
        "chat",
        "current",
        "here",
    ]:
        # Show current chat information
        try:
            chat_info = formatter.format_chat_info(chat, "detailed")
            reply_markup = get_quickinfo_inline_buttons()
            await send_message(
                message,
                f"<b>📋 Current Chat Information</b>\n\n{chat_info}",
                reply_markup,
            )
        except Exception as e:
            LOGGER.error(f"Error getting current chat info: {e}")
            await send_message(message, "❌ <b>Failed to get chat information.</b>")
        return

    # Determine behavior based on chat type
    if chat.type == ChatType.PRIVATE:
        # Private chat: Show only the interactive menu
        welcome_text = (
            "🆔 <b>Welcome to QuickInfo!</b> 👋\n\n"
            "✅ <b>Fetch Any Chat ID Instantly!</b>\n\n"
            "🔧 <b>How to Use:</b>\n"
            "1️⃣ Click the buttons below to share a chat or user\n"
            "2️⃣ Receive the unique ID instantly\n"
            "3️⃣ Use <code>/quickinfo chat</code> to get current chat info\n\n"
            "💎 <b>Features:</b>\n"
            "• Supports users, bots, private/public groups & channels\n"
            "• Fast and reliable\n"
            "• Get current chat information\n\n"
            f"🛠 <i>{Config.CREDIT}</i>"
        )

        reply_markup = get_appropriate_quickinfo_buttons(chat.type)
        await send_message(message, welcome_text, reply_markup)

    elif chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        # Group/Supergroup/Channel: Show current chat info AND interactive menu
        try:
            chat_info = formatter.format_chat_info(chat, "detailed")

            # Add forum topic information if applicable
            topic_info = ""
            # Check for topic_message attribute (may not exist in PyroFork)
            has_topic_message = getattr(message, "topic_message", None)
            message_thread_id = getattr(message, "message_thread_id", None)

            if has_topic_message and message_thread_id:
                topic_info = (
                    f"\n🧵 <b>Forum Topic ID:</b> <code>{message_thread_id}</code>"
                )
                # PyroFork compatibility for topic attribute
                topic = getattr(message, "topic", None)
                if topic and hasattr(topic, "name"):
                    topic_info += (
                        f"\n📝 <b>Topic Name:</b> <code>{topic.name}</code>"
                    )

            welcome_text = (
                f"📋 <b>Current {chat.type.value.title()} Information</b>\n\n"
                f"{chat_info}{topic_info}\n\n"
                "🔧 <b>QuickInfo Menu:</b>\n"
                "Use the buttons below to get information about other chats and users!\n\n"
                f"🛠 <i>{Config.CREDIT}</i>"
            )

            reply_markup = get_appropriate_quickinfo_buttons(chat.type)
            await send_message(message, welcome_text, reply_markup)

        except Exception as e:
            LOGGER.error(f"Error getting current chat info: {e}")
            await send_message(message, "❌ <b>Failed to get chat information.</b>")

    else:
        # Fallback for unknown chat types
        welcome_text = (
            "🆔 <b>Welcome to QuickInfo!</b> 👋\n\n"
            "✅ <b>Fetch Any Chat ID Instantly!</b>\n\n"
            f"🛠 <i>{Config.CREDIT}</i>"
        )

        reply_markup = get_appropriate_quickinfo_buttons(chat.type)
        await send_message(message, welcome_text, reply_markup)


async def handle_forwarded_message(client, message: Message):
    """Handle forwarded messages to extract source info"""
    if not is_quickinfo_enabled():
        return

    format_style = "detailed"

    try:
        info_parts = []

        # Check for forwarded from user
        if message.forward_from:
            user = message.forward_from
            user_info = formatter.format_user_info(user, format_style)
            info_parts.append(f"👤 <b>Original Sender:</b>\n{user_info}")

        # Check for forwarded from chat (channel/group/supergroup)
        # This can exist alongside forward_from for group messages
        if message.forward_from_chat:
            chat = message.forward_from_chat
            chat_info = formatter.format_chat_info(chat, format_style)

            # Add additional forward info if available
            forward_details = []
            if message.forward_from_message_id:
                forward_details.append(
                    f"🆔 <b>Original Message ID:</b> <code>{message.forward_from_message_id}</code>"
                )
            if message.forward_signature:
                forward_details.append(
                    f"✍️ <b>Author Signature:</b> <code>{message.forward_signature}</code>"
                )
            if message.forward_date:
                forward_details.append(
                    f"📅 <b>Original Date:</b> <code>{message.forward_date}</code>"
                )

            # Check if it's from a forum topic (PyroFork compatibility)
            has_topic_message = getattr(message, "topic_message", None)
            message_thread_id = getattr(message, "message_thread_id", None)

            if has_topic_message and message_thread_id:
                forward_details.append(
                    f"🧵 <b>Forum Topic ID:</b> <code>{message_thread_id}</code>"
                )

            info_parts.append(f"💬 <b>Original Chat:</b>\n{chat_info}")
            if forward_details:
                info_parts.append(
                    "📋 <b>Forward Details:</b>\n" + "\n".join(forward_details)
                )

        # Check for forwarded from hidden user (when no forward_from but has sender name)
        elif message.forward_sender_name:
            info_parts.append(
                f"🔒 <b>Original Sender (Hidden):</b>\n"
                f"📝 <b>Name:</b> <code>{message.forward_sender_name}</code>\n"
                f"ℹ️ <i>This user has hidden their account from forwarding</i>"
            )
            if message.forward_date:
                info_parts.append(
                    f"📅 <b>Original Date:</b> <code>{message.forward_date}</code>"
                )

        # Check for sender_chat (anonymous group administrators)
        if message.sender_chat:
            sender_chat = message.sender_chat
            sender_chat_info = formatter.format_chat_info(sender_chat, format_style)
            info_parts.append(f"🎭 <b>Sent on behalf of:</b>\n{sender_chat_info}")

        # Add general forward date if not already added and available
        if message.forward_date and not any(
            "Original Date" in part for part in info_parts
        ):
            info_parts.append(
                f"📅 <b>Forward Date:</b> <code>{message.forward_date}</code>"
            )

        # Extract media information if present
        media_info = formatter.format_media_info(message)
        if media_info:
            info_parts.append(f"📎 <b>Media Information:</b>\n{media_info}")

        # Extract text/caption information
        if message.text:
            text_preview = (
                message.text[:100] + "..."
                if len(message.text) > 100
                else message.text
            )
            info_parts.append(f"💬 <b>Text:</b> <code>{text_preview}</code>")
        elif message.caption:
            caption_preview = (
                message.caption[:100] + "..."
                if len(message.caption) > 100
                else message.caption
            )
            info_parts.append(f"📝 <b>Caption:</b> <code>{caption_preview}</code>")

        # Add current chat information if different from forward source
        if message.chat and (
            not message.forward_from_chat
            or message.chat.id != message.forward_from_chat.id
        ):
            current_chat_info = formatter.format_chat_info(
                message.chat, format_style
            )
            info_parts.append(f"📍 <b>Current Chat:</b>\n{current_chat_info}")

        if info_parts:
            final_message = "📤 <b>Forwarded Message Info</b>\n\n" + "\n\n".join(
                info_parts
            )
            reply_markup = get_quickinfo_inline_buttons()
            await send_message(message, final_message, reply_markup)
        else:
            # No forward information found
            await send_message(
                message,
                "📤 <b>Forwarded Message Info</b>\n\n"
                "🔒 <b>Looks Like I Don't Have Control Over The User</b>\n"
                "ℹ️ <i>No forward information available for this message</i>",
            )

    except Exception as e:
        LOGGER.error(f"Error handling forwarded message: {e}")
        await send_message(
            message,
            "📤 <b>Forwarded Message Info</b>\n\n"
            "❌ <b>Failed to process forwarded message information.</b>",
        )


async def handle_shared_entities(client, message: Message):
    """Handle shared users and chats"""
    if not is_quickinfo_enabled():
        return

    format_style = "detailed"

    try:
        # Check for shared users (Users/Bots/Premium buttons)
        if hasattr(message, "users_shared") and message.users_shared:
            users_shared = message.users_shared
            users_list = users_shared.users

            for user_data in users_list:
                if user_data is None:  # Skip None entries
                    continue

                # user_data is already a User object from pyrogram
                user_info = formatter.format_user_info(user_data, format_style)

                reply_markup = get_quickinfo_inline_buttons()
                await send_message(
                    message,
                    f"👥 <b>Shared Entity Info</b>\n\n{user_info}",
                    reply_markup,
                )

        # Check for shared chats (Channel/Group buttons)
        elif hasattr(message, "chat_shared") and message.chat_shared:
            chat_shared = message.chat_shared
            chat_data = chat_shared.chat

            if chat_data is not None:
                # chat_data is already a Chat object from pyrogram
                chat_info = formatter.format_chat_info(chat_data, format_style)

                reply_markup = get_quickinfo_inline_buttons()
                await send_message(
                    message,
                    f"👥 <b>Shared Entity Info</b>\n\n{chat_info}",
                    reply_markup,
                )

        else:
            # No shared entities found, show instruction message
            await send_message(
                message,
                "💡 <b>Please use the provided buttons to share a group, bot, channel, or user.</b>",
            )

    except Exception as e:
        LOGGER.error(f"Error handling shared entities: {e}")
        await send_message(
            message, "❌ <b>Failed to process shared entity information.</b>"
        )


async def quickinfo_callback(client, callback_query: CallbackQuery):
    """Handle QuickInfo callback queries"""
    data = callback_query.data
    message = callback_query.message

    try:
        if data == "quickinfo_help":
            help_text = get_quickinfo_help_text()
            await edit_message(message, help_text, get_quickinfo_inline_buttons())

        elif data == "quickinfo_refresh":
            welcome_text = (
                "🆔 <b>Welcome to QuickInfo!</b> 👋\n\n"
                "✅ <b>Fetch Any Chat ID Instantly!</b>\n\n"
                "🔧 <b>How to Use:</b>\n"
                "1️⃣ Click the buttons below to share a chat or user\n"
                "2️⃣ Receive the unique ID instantly\n"
                "3️⃣ Use <code>/quickinfo chat</code> to get current chat info\n\n"
                "💎 <b>Features:</b>\n"
                "• Supports users, bots, private/public groups & channels\n"
                "• Fast and reliable\n"
                "• Get current chat information\n\n"
                f"🛠 <i>{Config.CREDIT}</i>"
            )
            await edit_message(message, welcome_text, get_quickinfo_inline_buttons())

        elif data == "quickinfo_close":
            await delete_message(message)

        elif data == "quickinfo_back":
            welcome_text = (
                "🆔 <b>Welcome to QuickInfo!</b> 👋\n\n"
                "✅ <b>Fetch Any Chat ID Instantly!</b>\n\n"
                "🔧 <b>How to Use:</b>\n"
                "1️⃣ Click the buttons below to share a chat or user\n"
                "2️⃣ Receive the unique ID instantly\n"
                "3️⃣ Use <code>/quickinfo chat</code> to get current chat info\n\n"
                "💎 <b>Features:</b>\n"
                "• Supports users, bots, private/public groups & channels\n"
                "• Fast and reliable\n"
                "• Get current chat information\n\n"
                f"🛠 <i>{Config.CREDIT}</i>"
            )
            await edit_message(message, welcome_text, get_quickinfo_inline_buttons())

        else:
            await callback_query.answer("❌ Unknown action")

    except Exception as e:
        LOGGER.error(f"Error in quickinfo callback: {e}")
        await callback_query.answer("❌ An error occurred")
