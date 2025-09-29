from time import time
from uuid import uuid4

from pyrogram.errors import PeerIdInvalid, RPCError, UserNotParticipant

from bot import (
    LOGGER,
    user_data,
)
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.aeon_utils.shorteners import short
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.nsfw_detection import nsfw_detector
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.button_build import ButtonMaker

# Rate limiting for FSUB skip messages to prevent log spam
_fsub_skip_log_cache = {}


async def error_check(message):
    msg, button = [], None

    # Handle case where both message.from_user and message.sender_chat could be None
    if message.from_user is None and message.sender_chat is None:
        # For anonymous messages or system messages, we'll use a default approach
        # We'll create a minimal user object with the chat ID as the user ID
        class MinimalUser:
            def __init__(self, chat_id):
                self.id = chat_id

        user = MinimalUser(message.chat.id)
    else:
        user = message.from_user or message.sender_chat

    user_id = user.id
    token_timeout = Config.TOKEN_TIMEOUT
    if Config.RSS_CHAT and user_id == int(Config.RSS_CHAT):
        return None, None

    if message.chat.type != message.chat.type.BOT:
        if FSUB_IDS := Config.FSUB_IDS:
            join_button = {}
            for channel_id in FSUB_IDS.split():
                chat = await get_chat_info(int(channel_id))
                if not chat:
                    continue

                # For channel messages or anonymous admins, we can't check membership
                # So we'll skip the membership check for these messages
                if message.from_user is None:
                    # Rate limit this log message to prevent spam
                    log_key = f"{channel_id}_{message.chat.id}"
                    current_time = time()

                    # Only log once every 300 seconds (5 minutes) per channel-chat combination
                    if (
                        log_key not in _fsub_skip_log_cache
                        or (current_time - _fsub_skip_log_cache[log_key]) > 300
                    ):
                        _fsub_skip_log_cache[log_key] = current_time
                        LOGGER.info(
                            f"Skipping FSUB check for channel {channel_id} - message from channel/anonymous in chat {message.chat.id}"
                        )
                    continue

                try:
                    await chat.get_member(message.from_user.id)
                except UserNotParticipant:
                    invite_link = (
                        f"https://t.me/{chat.username}"
                        if chat.username
                        else chat.invite_link
                    )
                    join_button[chat.title] = invite_link
                except RPCError as e:
                    LOGGER.error(f"{e.NAME}: {e.MESSAGE} for {channel_id}")
                except Exception as e:
                    LOGGER.error(f"{e} for {channel_id}")

            if join_button:
                button = button or ButtonMaker()
                for title, link in join_button.items():
                    button.url_button(f"Join {title}", link, "footer")
                msg.append("You haven't joined our channel/group yet!")

        if not token_timeout or user_id in {
            Config.OWNER_ID,
            user_data.get(user_id, {}).get("SUDO"),
        }:
            try:
                temp_msg = await message._client.send_message(
                    chat_id=user_id,
                    text="<b>Checking Access...</b>",
                )
                # Use delete_message for immediate deletion instead of auto_delete_message
                from bot.helper.telegram_helper.message_utils import (
                    delete_message,
                )

                await delete_message(temp_msg)
            except Exception:
                button = button or ButtonMaker()
                button.data_button("Start", f"aeon {user_id} private", "header")
                msg.append("You haven't initiated the bot in a private message!")

    # Always authorize privileged users (Owner + Sudo)
    from bot.helper.ext_utils.bot_utils import is_privileged_user

    if is_privileged_user(user_id):
        return None, None

    if user_id not in {
        Config.RSS_CHAT,
        user_data.get(user_id, {}).get("SUDO"),
    }:
        token_msg, button = await token_check(user_id, button)
        if token_msg:
            msg.append(token_msg)

    if await nsfw_precheck(message):
        msg.append("NSFW detected")

    if msg:
        # Check if message.from_user is not None before accessing its username
        if message.from_user is None:
            # Use a generic tag if from_user is None
            tag = "User"
        else:
            username = message.from_user.username
            tag = f"@{username}" if username else message.from_user.mention

        final_msg = f"Hey, <b>{tag}</b>!\n"
        for i, m in enumerate(msg, 1):
            final_msg += f"\n<blockquote><b>{i}</b>: {m}</blockquote>"

        if button:
            button = button.build_menu(2)
        return final_msg, button

    return None, None


async def get_chat_info(channel_id):
    try:
        return await TgClient.bot.get_chat(channel_id)
    except PeerIdInvalid as e:
        LOGGER.error(f"{e.NAME}: {e.MESSAGE} for {channel_id}")
        return None


# Legacy NSFW functions removed - now using enhanced detection system


async def nsfw_precheck(message):
    """Enhanced NSFW detection using the new detection system"""
    from bot.core.config_manager import Config

    # If enhanced NSFW detection is disabled, skip NSFW check
    if not Config.NSFW_DETECTION_ENABLED:
        return False

    try:
        # Check message text
        if message.text:
            result = await nsfw_detector.detect_text_nsfw(message.text)
            if result.is_nsfw:
                # Update user behavior tracking
                if Config.NSFW_STORE_METADATA:
                    from bot.helper.ext_utils.db_handler import database

                    await database.update_user_nsfw_behavior(
                        message.from_user.id, True, result.confidence
                    )
                return True

        # Check reply message
        reply_to = message.reply_to_message
        if reply_to:
            # Check reply text/caption
            reply_text = reply_to.text or reply_to.caption
            if reply_text:
                result = await nsfw_detector.detect_text_nsfw(reply_text)
                if result.is_nsfw:
                    if Config.NSFW_STORE_METADATA:
                        from bot.helper.ext_utils.db_handler import database

                        await database.update_user_nsfw_behavior(
                            message.from_user.id, True, result.confidence
                        )
                    return True

            # Check file names
            for attr in ["document", "video", "photo", "audio"]:
                if hasattr(reply_to, attr) and getattr(reply_to, attr):
                    media_obj = getattr(reply_to, attr)
                    file_name = getattr(media_obj, "file_name", None)
                    if file_name:
                        result = await nsfw_detector.detect_text_nsfw(file_name)
                        if result.is_nsfw:
                            if Config.NSFW_STORE_METADATA:
                                from bot.helper.ext_utils.db_handler import database

                                await database.update_user_nsfw_behavior(
                                    message.from_user.id, True, result.confidence
                                )
                            return True

        # Update user behavior for clean content
        if Config.NSFW_STORE_METADATA:
            from bot.helper.ext_utils.db_handler import database

            await database.update_user_nsfw_behavior(
                message.from_user.id, False, 0.0
            )

        return False

    except Exception as e:
        LOGGER.error(f"Error in enhanced NSFW detection: {e}")
        # Return False on error instead of falling back to legacy
        return False


async def check_is_paid(chat, uid):
    try:
        await chat.get_member(uid)
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        LOGGER.error(f"{e} for {chat.id}")
        return False


async def is_paid(user_id):
    if chat := await get_chat_info(Config.PAID_CHANNEL_ID):
        return await check_is_paid(chat, user_id)
    return True


async def token_check(user_id, button=None):
    token_timeout = Config.TOKEN_TIMEOUT

    # Always authorize privileged users without token (Owner + Sudo)
    from bot.helper.ext_utils.bot_utils import is_privileged_user

    if is_privileged_user(user_id):
        return None, button

    if not token_timeout:
        return None, button
    if Config.PAID_CHANNEL_ID and await is_paid(user_id):
        return None, button

    user_data.setdefault(user_id, {})
    data = user_data[user_id]

    # Check if user is logged in with LOGIN_PASS
    login_pass = Config.LOGIN_PASS
    if login_pass and data.get("VERIFY_TOKEN", "") == login_pass:
        return None, button

    data["TIME"] = await database.get_token_expiry(user_id)
    expire = data.get("TIME")
    isExpired = expire is None or (time() - expire) > token_timeout
    if isExpired:
        token = data["TOKEN"] if expire is None and "TOKEN" in data else str(uuid4())
        if expire is not None:
            del data["TIME"]
        data["TOKEN"] = token
        await database.update_user_token(user_id, token)
        user_data[user_id] = data

        time_str = get_readable_time(token_timeout, True)
        button = button or ButtonMaker()
        short_link = await short(
            f"https://telegram.me/{TgClient.NAME}?start={token}",
        )

        # Use the shortened link (or original if shortening failed)
        button.url_button("Collect token", short_link)
        msg = "Your token has expired, please collect a new token"

        if login_pass:
            msg += " or login with password using /login command."

        if Config.PAID_CHANNEL_ID and Config.PAID_CHANNEL_LINK:
            msg += " or subscribe to the paid channel for no token."
            button.url_button("Subscribe", Config.PAID_CHANNEL_LINK)

        return (msg + f"\n<b>It will expire after {time_str}</b>!"), button

    return None, button
