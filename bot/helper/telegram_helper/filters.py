from pyrogram.filters import create

from bot import auth_chats, sudo_users, user_data
from bot.core.config_manager import Config


class CustomFilters:
    async def owner_filter(self, _, update):
        # Check if update is None
        if not update:
            return False

        # Safely get user and handle None case
        user = update.from_user or update.sender_chat
        if not user:
            return False

        return user.id == Config.OWNER_ID

    owner = create(owner_filter)

    async def pm_or_authorized(self, _, update):
        # Check if update is None
        if not update:
            return False

        # Handle different types of updates
        if hasattr(update, "callback_query") and update.callback_query:
            # For callback query updates
            if (
                hasattr(update.callback_query, "message")
                and update.callback_query.message
            ):
                chat = update.callback_query.message.chat
            else:
                return False
        elif hasattr(update, "message") and update.message:
            # For message updates
            chat = update.message.chat
        elif hasattr(update, "chat") and update.chat:
            # For other updates with chat attribute
            chat = update.chat
        else:
            return False

        # Allow access in private chats (bot PMs) without authorization
        if chat.type == "private":
            return True

        # For non-private chats, use the authorized filter
        return await CustomFilters.authorized_user(self, _, update)

    pm_or_authorized = create(pm_or_authorized)

    async def callback_pm_or_authorized(self, _, update):
        # Check if update is None
        if not update:
            return False

        # For callback queries, we need to check the message's chat
        if hasattr(update, "message") and update.message:
            chat = update.message.chat
            # PyroFork compatibility for topic_message
            has_topic_message = getattr(update.message, "topic_message", None)
            thread_id = (
                getattr(update.message, "message_thread_id", None)
                if has_topic_message
                else None
            )
        else:
            return False

        # Allow access in private chats (bot PMs) without authorization
        if chat.type == "private":
            return True

        # For non-private chats, check if user is authorized
        user = update.from_user
        if not user:
            return False

        uid = user.id
        chat_id = chat.id

        # Always authorize privileged users (Owner + Sudo)
        from bot.helper.ext_utils.bot_utils import is_privileged_user

        if is_privileged_user(uid):
            return True

        # Use the same authorization logic as in authorized_user
        return bool(
            (
                uid in user_data
                and (
                    user_data[uid].get("AUTH", False)
                    or user_data[uid].get("SUDO", False)
                )
            )
            or (
                chat_id in user_data
                and user_data[chat_id].get("AUTH", False)
                and (
                    thread_id is None
                    or thread_id in user_data[chat_id].get("thread_ids", [])
                )
            )
            or uid in sudo_users
            or uid in auth_chats
            or (
                chat_id in auth_chats
                and (
                    (
                        auth_chats[chat_id]
                        and thread_id
                        and thread_id in auth_chats[chat_id]
                    )
                    or not auth_chats[chat_id]
                )
            ),
        )

    callback_pm_or_authorized = create(callback_pm_or_authorized)

    async def authorized_user(self, _, update):
        # Check if update is None
        if not update:
            return False

        # Handle different types of updates
        if hasattr(update, "callback_query") and update.callback_query:
            # For callback query updates
            user = update.callback_query.from_user
            if (
                hasattr(update.callback_query, "message")
                and update.callback_query.message
            ):
                chat = update.callback_query.message.chat
                # PyroFork compatibility for topic_message
                has_topic_message = getattr(
                    update.callback_query.message, "topic_message", None
                )
                thread_id = (
                    getattr(update.callback_query.message, "message_thread_id", None)
                    if has_topic_message
                    else None
                )
            else:
                return False
        elif hasattr(update, "message") and update.message:
            # For message updates
            user = update.message.from_user or update.message.sender_chat
            chat = update.message.chat
            # PyroFork compatibility for topic_message
            has_topic_message = getattr(update.message, "topic_message", None)
            thread_id = (
                getattr(update.message, "message_thread_id", None)
                if has_topic_message
                else None
            )
        elif hasattr(update, "chat") and update.chat:
            # For other updates with chat attribute
            user = update.from_user or update.sender_chat
            chat = update.chat
            # PyroFork compatibility for topic_message
            has_topic_message = getattr(update, "topic_message", None)
            thread_id = (
                getattr(update, "message_thread_id", None)
                if has_topic_message
                else None
            )
        else:
            return False

        # Safely get user and handle None case
        if not user:
            return False

        # Now we can safely access user.id and chat.id
        uid = user.id
        chat_id = chat.id

        # Always authorize privileged users (Owner + Sudo)
        from bot.helper.ext_utils.bot_utils import is_privileged_user

        if is_privileged_user(uid):
            return True

        return bool(
            (
                uid in user_data
                and (
                    user_data[uid].get("AUTH", False)
                    or user_data[uid].get("SUDO", False)
                )
            )
            or (
                chat_id in user_data
                and user_data[chat_id].get("AUTH", False)
                and (
                    thread_id is None
                    or thread_id in user_data[chat_id].get("thread_ids", [])
                )
            )
            or uid in sudo_users
            or uid in auth_chats
            or (
                chat_id in auth_chats
                and (
                    (
                        auth_chats[chat_id]
                        and thread_id
                        and thread_id in auth_chats[chat_id]
                    )
                    or not auth_chats[chat_id]
                )
            ),
        )

    authorized = create(authorized_user)

    async def sudo_user(self, _, update):
        # Check if update is None or doesn't have required attributes
        if not update:
            return False

        # Safely get user and handle None case
        user = update.from_user or update.sender_chat
        if not user:
            return False

        uid = user.id

        # Always authorize privileged users as sudo (Owner + Sudo)
        from bot.helper.ext_utils.bot_utils import is_privileged_user

        if is_privileged_user(uid):
            return True

        return bool(
            (uid in user_data and user_data[uid].get("SUDO")) or uid in sudo_users,
        )

    sudo = create(sudo_user)
