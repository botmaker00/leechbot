from time import time
from uuid import uuid4

from pyrogram.enums import ChatAction
from pyrogram.errors import (
    ChannelInvalid,
    PeerIdInvalid,
    RPCError,
    UserNotParticipant,
)

from bot import LOGGER, user_data
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.aeon_utils.shorteners import short
from bot.helper.ext_utils.bot_utils import encode_slink
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.button_build import ButtonMaker


async def chat_info(channel_id):
    channel_id = str(channel_id).strip()
    if channel_id.startswith("-100"):
        channel_id = int(channel_id)
    elif channel_id.startswith("@"):
        channel_id = channel_id.replace("@", "")
    else:
        return None
    try:
        return await TgClient.bot.get_chat(channel_id)
    except (PeerIdInvalid, ChannelInvalid) as e:
        LOGGER.error(f"{e.NAME}: {e.MESSAGE} for {channel_id}")
        return None


async def user_info(user_id):
    try:
        return await TgClient.bot.get_users(user_id)
    except Exception:
        return ""


async def check_botpm(message, button=None):
    # Check if message.from_user is None before accessing its id
    if message.from_user is None:
        if button is None:
            button = ButtonMaker()
        _msg = "┠ <i>Bot isn't Started in PM or Inbox (Private)</i>"
        button.url_button(
            "Start Bot Now",
            f"https://t.me/{TgClient.BNAME}?start=start",
            "header",
        )
        return _msg, button

    try:
        await TgClient.bot.send_chat_action(message.from_user.id, ChatAction.TYPING)
        return None, button
    except Exception:
        if button is None:
            button = ButtonMaker()
        _msg = "┠ <i>Bot isn't Started in PM or Inbox (Private)</i>"
        button.url_button(
            "Start Bot Now",
            f"https://t.me/{TgClient.BNAME}?start=start",
            "header",
        )
        return _msg, button


async def forcesub(message, ids, button=None):
    join_button = {}
    for channel_id in ids.split():
        chat = await chat_info(channel_id)
        if not chat:
            continue
        try:
            await chat.get_member(message.from_user.id)
        except UserNotParticipant:
            join_button[chat.title] = (
                f"https://t.me/{chat.username}"
                if chat.username
                else chat.invite_link
            )
        except RPCError as e:
            LOGGER.error(f"{e.NAME}: {e.MESSAGE} for {channel_id}")
        except Exception as e:
            LOGGER.error(f"{e} for {channel_id}")
    if join_button:
        if button is None:
            button = ButtonMaker()
        for title, link in join_button.items():
            button.url_button(f"Join {title}", link, "footer")
        return "┠ <i>You haven't joined our channel/group yet!</i>", button
    return None, button


async def verify_token(user_id, button=None):
    if not Config.VERIFY_TIMEOUT or bool(
        user_id == Config.OWNER_ID
        or (user_id in user_data and user_data[user_id].get("is_sudo")),
    ):
        return None, button
    user_data.setdefault(user_id, {})
    data = user_data[user_id]
    expire = data.get("VERIFY_TIME")
    login_pass = Config.LOGIN_PASS
    if login_pass and data.get("VERIFY_TOKEN", "") == login_pass:
        return None, button
    isExpired = expire is None or (
        expire is not None and (time() - expire) > Config.VERIFY_TIMEOUT
    )
    if isExpired:
        token = (
            data["VERIFY_TOKEN"]
            if expire is None and "VERIFY_TOKEN" in data
            else str(uuid4())
        )
        if expire is not None:
            del data["VERIFY_TIME"]
        data["VERIFY_TOKEN"] = token
        user_data[user_id].update(data)
        if button is None:
            button = ButtonMaker()
        encrypt_url = encode_slink(f"{token}&&{user_id}")
        short_link = await short(
            f"https://t.me/{TgClient.BNAME}?start={encrypt_url}"
        )

        # Use the shortened link (or original if shortening failed)
        button.url_button("Verify Access Token", short_link)
        msg = f"┠ <i>Verify Access Token has been expired,</i> Kindly validate a new access token to start using bot again.\n┃\n┖ <b>Validity :</b> <code>{get_readable_time(Config.VERIFY_TIMEOUT)}</code>"

        return (msg, button)
    return None, button
