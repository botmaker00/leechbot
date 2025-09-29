from asyncio import create_task

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task, sync_to_async
from bot.helper.ext_utils.links_utils import is_gdrive_link
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.mirror_leech_utils.gdrive_utils.count import GoogleDriveCount
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    delete_message,
    send_message,
)


@new_task
async def count_node(_, message):
    # Check if mirror operations are enabled in the configuration
    if not Config.MIRROR_ENABLED:
        await send_message(
            message,
            "❌ Count command is disabled when mirror operations are disabled.",
        )
        return

    args = message.text.split()
    user = message.from_user or message.sender_chat
    if username := user.username:
        tag = f"@{username}"
    else:
        tag = message.from_user.mention

    link = args[1] if len(args) > 1 else ""
    if len(link) == 0 and (reply_to := message.reply_to_message):
        link = reply_to.text.split(maxsplit=1)[0].strip()

    if is_gdrive_link(link):
        msg = await send_message(message, f"Counting: <code>{link}</code>")
        name, mime_type, size, files, folders = await sync_to_async(
            GoogleDriveCount().count,
            link,
            user.id,
        )
        if mime_type is None:
            await send_message(message, name)
            await delete_links(message)  # Delete command and replied message
            return
        await delete_message(msg)
        result_msg = f"<b>Name: </b><code>{name}</code>"
        result_msg += f"\n\n<b>Size: </b>{get_readable_file_size(size)}"
        result_msg += f"\n\n<b>Type: </b>{mime_type}"
        if mime_type == "Folder":
            result_msg += f"\n<b>SubFolders: </b>{folders}"
            result_msg += f"\n<b>Files: </b>{files}"
        result_msg += f"\n\n<b>cc: </b>{tag}"
        await send_message(message, result_msg)
        await delete_links(
            message,
        )  # Delete command and replied message after counting
    else:
        help_msg = "Send Gdrive link along with command or by replying to the link by command"
        msg = await send_message(message, help_msg)
        # Auto delete help message and command after 5 minutes
        create_task(auto_delete_message(msg, time=300))  # noqa: RUF006
        create_task(auto_delete_message(message, time=300))  # noqa: RUF006
        if reply_to := message.reply_to_message:
            create_task(auto_delete_message(reply_to, time=300))  # noqa: RUF006
