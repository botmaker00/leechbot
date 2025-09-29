from asyncio import create_task

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import new_task, sync_to_async
from bot.helper.ext_utils.links_utils import is_gdrive_link
from bot.helper.mirror_leech_utils.gdrive_utils.delete import GoogleDriveDelete
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)


@new_task
async def delete_file(_, message):
    args = message.text.split()
    user = message.from_user or message.sender_chat
    reply_to = message.reply_to_message

    if len(args) > 1:
        link = args[1]
    elif reply_to:
        link = reply_to.text.split(maxsplit=1)[0].strip()
    else:
        link = ""

    if is_gdrive_link(link):
        # Valid link - delete command and replied message immediately
        if reply_to:
            await delete_message(reply_to)
        await delete_message(message)

        LOGGER.info(link)
        msg = await sync_to_async(GoogleDriveDelete().deletefile, link, user.id)

        # Send success message and auto-delete after 5 minutes
        reply_message = await send_message(message, msg)
        create_task(auto_delete_message(reply_message, time=300))  # noqa: RUF006
    else:
        # Invalid link - keep messages for 5 minutes
        msg = "Send Gdrive link along with command or by replying to the link by command"
        reply_message = await send_message(message, msg)

        # Auto-delete all messages after 5 minutes
        create_task(auto_delete_message(reply_message, time=300))  # noqa: RUF006
        create_task(auto_delete_message(message, time=300))  # noqa: RUF006
        if reply_to:
            create_task(auto_delete_message(reply_to, time=300))  # noqa: RUF006
