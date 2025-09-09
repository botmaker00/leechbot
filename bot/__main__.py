# ruff: noqa: E402, PLC0415
from asyncio import gather

from pyrogram.types import BotCommand

from . import LOGGER, bot_loop
from .core.config_manager import Config, SystemEnv

LOGGER.info("Loading config...")
Config.load()
SystemEnv.load()

from .core.startup import load_settings

bot_loop.run_until_complete(load_settings())

from .core.aeon_client import TgClient
from .helper.telegram_helper.bot_commands import BotCommands

COMMANDS = {
    "MirrorCommand": "- ꜱᴛᴀʀᴛ ᴍɪʀʀᴏʀɪɴɢ",
    "LeechCommand": "- ꜱᴛᴀʀᴛ ʟᴇᴇᴄʜɪɴɢ",
    "JdMirrorCommand": "- ᴍɪʀʀᴏʀ ᴜꜱɪɴɢ ᴊᴅᴏᴡɴʟᴏᴀᴅᴇʀ",
    "JdLeechCommand": "- ʟᴇᴇᴄʜ ᴜꜱɪɴɢ ᴊᴅᴏᴡɴʟᴏᴀᴅᴇʀ",
    "NzbMirrorCommand": "- ᴍɪʀʀᴏʀ ɴᴢʙ ꜰɪʟᴇꜱ",
    "NzbLeechCommand": "- ʟᴇᴇᴄʜ ɴᴢʙ ꜰɪʟᴇꜱ",
    "YtdlCommand": "- ᴍɪʀʀᴏʀ ʟɪɴᴋ ᴜꜱɪɴɢ ʏᴛ-ᴅʟᴘ",
    "YtdlLeechCommand": "- ʟᴇᴇᴄʜ ʟɪɴᴋ ᴜꜱɪɴɢ ʏᴛ-ᴅʟᴘ",
    "CloneCommand": "- ᴄᴏᴘʏ ꜰɪʟᴇ/ꜰᴏʟᴅᴇʀ ᴛᴏ ᴅʀɪᴠᴇ",
    "MediaInfoCommand": "- ɢᴇᴛ ᴍᴇᴅɪᴀ ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ",
    "SoxCommand": "- ɢᴇᴛ ᴀᴜᴅɪᴏ ꜱᴘᴇᴄᴛʀᴜᴍ",
    "ForceStartCommand": "- ꜰᴏʀᴄᴇ ꜱᴛᴀʀᴛ ᴀ ᴛᴀꜱᴋ ꜰʀᴏᴍ Qᴜᴇᴜᴇ",
    "CountCommand": "- ᴄᴏᴜɴᴛ ꜰɪʟᴇ/ꜰᴏʟᴅᴇʀ ᴏɴ ɢᴏᴏɢʟᴇ ᴅʀɪᴠᴇ",
    "ListCommand": "- ꜱᴇᴀʀᴄʜ ɪɴ ᴅʀɪᴠᴇ",
    "SearchCommand": "- ꜱᴇᴀʀᴄʜ ꜰᴏʀ ᴛᴏʀʀᴇɴᴛꜱ",
    "UserSetCommand": "- ᴜꜱᴇʀ ꜱᴇᴛᴛɪɴɢꜱ",
    "StatusCommand": "- ꜱʜᴏᴡ ᴍɪʀʀᴏʀ ꜱᴛᴀᴛᴜꜱ",
    "StatsCommand": "- ꜱʜᴏᴡ ʙᴏᴛ ᴀɴᴅ ꜱʏꜱᴛᴇᴍ ꜱᴛᴀᴛꜱ",
    "CancelAllCommand": "- ᴄᴀɴᴄᴇʟ ᴀʟʟ ʏᴏᴜʀ ᴛᴀꜱᴋꜱ",
    "HelpCommand": "- ɢᴇᴛ ᴅᴇᴛᴀɪʟᴇᴅ ʜᴇʟᴘ",
    "SpeedTest": "- ʀᴜɴ ᴀ ꜱᴘᴇᴇᴅᴛᴇꜱᴛ",
    "BotSetCommand": "- [ᴀᴅᴍɪɴ] ᴏᴘᴇɴ ʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ",
    "LogCommand": "- [ᴀᴅᴍɪɴ] ᴠɪᴇᴡ ʙᴏᴛ ʟᴏɢ",
    "RestartCommand": "- [ᴀᴅᴍɪɴ] ʀᴇꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ"
}


COMMAND_OBJECTS = [
    BotCommand(
        getattr(BotCommands, cmd)[0]
        if isinstance(getattr(BotCommands, cmd), list)
        else getattr(BotCommands, cmd),
        description,
    )
    for cmd, description in COMMANDS.items()
]


async def set_commands():
    if Config.SET_COMMANDS:
        await TgClient.bot.set_bot_commands(COMMAND_OBJECTS)


async def main():
    from .core.startup import (
        load_configurations,
        save_settings,
        update_aria2_options,
        update_nzb_options,
        update_qb_options,
        update_variables,
    )

    await gather(TgClient.start_bot(), TgClient.start_user())
    await gather(load_configurations(), update_variables())
    from .core.torrent_manager import TorrentManager

    await TorrentManager.initiate()
    await gather(
        update_qb_options(),
        update_aria2_options(),
        update_nzb_options(),
    )
    from .core.jdownloader_booter import jdownloader
    from .helper.ext_utils.files_utils import clean_all
    from .helper.ext_utils.telegraph_helper import telegraph
    from .helper.mirror_leech_utils.rclone_utils.serve import rclone_serve_booter
    from .modules import (
        get_packages_version,
        initiate_search_tools,
        restart_notification,
    )

    await gather(
        set_commands(),
        jdownloader.boot(),
    )
    await gather(
        save_settings(),
        clean_all(),
        initiate_search_tools(),
        get_packages_version(),
        restart_notification(),
        telegraph.create_account(),
        rclone_serve_booter(),
    )


bot_loop.run_until_complete(main())

from .core.handlers import add_handlers
from .helper.ext_utils.bot_utils import create_help_buttons
from .helper.listeners.aria2_listener import add_aria2_callbacks

add_aria2_callbacks()
create_help_buttons()
add_handlers()


LOGGER.info("Bot Started!")
bot_loop.run_forever()
