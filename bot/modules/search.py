from asyncio import create_task
from html import escape
from urllib.parse import quote

from bot import LOGGER
from bot.core.config_manager import Config
from bot.core.torrent_manager import TorrentManager
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

search_keys = {}  # Dictionary to store search keys by user_id

PLUGINS = []
TELEGRAPH_LIMIT = 300  # Default limit if SEARCH_LIMIT is 0
SEARCH_PLUGINS = [
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/limetorrents.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/torlock.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/torrentproject.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/eztv.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/ettv.py",
    "https://gist.githubusercontent.com/scadams/56635407b8dfb8f5f7ede6873922ac8b/raw/f654c10468a0b9945bec9bf31e216993c9b7a961/one337x.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/thepiratebay.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/piratebay.py",
    "https://scare.ca/dl/qBittorrent/thepiratebay.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/kickasstorrents.py",
    "https://raw.githubusercontent.com/MadeOfMagicAndWires/qBit-plugins/master/engines/nyaasi.py",
    "https://raw.githubusercontent.com/lazulyra/qbit-plugins/main/yts_mx/yts_mx.py",
    "https://raw.githubusercontent.com/nindogo/qbtSearchScripts/master/magnetdl.py",
    "https://scare.ca/dl/qBittorrent/magnetdl.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/academictorrents.py",
    "https://raw.githubusercontent.com/nindogo/qbtSearchScripts/master/torrentgalaxy.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/torrentdownload.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/torrentdownloads.py",
    "https://scare.ca/dl/qBittorrent/torrentdownload.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/yourbittorrent.py",
    "https://raw.githubusercontent.com/444995/qbit-search-plugins/main/engines/zooqle.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/bitsearch.py",
    "https://raw.githubusercontent.com/msagca/qbittorrent_plugins/main/uniondht.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/torrentscsv.py",
    "https://raw.githubusercontent.com/v1k45/1337x-qBittorrent-search-plugin/master/leetx.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/solidtorrents.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/solidtorrents.py",
    "https://raw.githubusercontent.com/MadeOfMagicAndWires/qBit-plugins/master/engines/linuxtracker.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/glotorrents.py",
    "https://raw.githubusercontent.com/Cc050511/qBit-search-plugins/main/acgrip.py",
    "https://raw.githubusercontent.com/nindogo/qbtSearchScripts/master/anidex.py",
    "https://raw.githubusercontent.com/AlaaBrahim/qBitTorrent-animetosho-search-plugin/main/animetosho.py",
    "https://raw.githubusercontent.com/nklido/qBittorrent_search_engines/master/engines/audiobookbay.py",
    "https://raw.githubusercontent.com/TuckerWarlock/qbittorrent-search-plugins/main/bt4gprx.com/bt4gprx.py",
    "https://raw.githubusercontent.com/galaris/BTDigg-qBittorrent-plugin/main/btdig.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/calidadtorrent.py",
    "https://raw.githubusercontent.com/444995/qbit-search-plugins/main/engines/torrentleech.py",
    "https://raw.githubusercontent.com/evyd13/search-plugins/master/nova3/engines/redacted_ch.py",
    "https://raw.githubusercontent.com/444995/qbit-search-plugins/main/engines/danishbytes.py",
    "https://raw.githubusercontent.com/YGGverse/qbittorrent-yggtracker-search-plugin/main/yggtracker.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/torrenflix.py",
    "https://raw.githubusercontent.com/menegop/qbfrench/master/torrent9.py",
    "https://raw.githubusercontent.com/BrunoReX/qBittorrent-Search-Plugin-TokyoToshokan/master/tokyotoshokan.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/tomadivx.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/therarbg.py",
    "https://raw.githubusercontent.com/libellula/qbt-plugins/main/sukebei.py",
    "https://raw.githubusercontent.com/phuongtailtranminh/qBittorrent-Nyaa-Search-Plugin/master/nyaa.py",
    "https://github.com/vt-idiot/qBit-SukebeiNyaa-plugin/raw/master/engines/sukebeisi.py",
    "https://raw.githubusercontent.com/kli885/qBittorent-SubsPlease-Search-Plugin/main/subsplease.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/snowfl.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/rockbox.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/pirateiro.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/pediatorrent.py",
    "https://raw.githubusercontent.com/dangar16/pediatorrent-plugin/refs/heads/main/pediatorrent.py",
    "https://raw.githubusercontent.com/MadeOfMagicAndWires/qBit-plugins/refs/heads/main/engines/nyaapantsu.py",
    "https://raw.githubusercontent.com/libellula/qbt-plugins/main/pantsu.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/naranjatorrent.py",
    "https://raw.githubusercontent.com/Cc050511/qBit-search-plugins/main/mikanani.py",
    "https://raw.githubusercontent.com/iordic/qbittorrent-search-plugins/master/engines/mejortorrent.py",
    "https://raw.githubusercontent.com/joseeloren/search-plugins/master/nova3/engines/maxitorrent.py",
    "https://raw.githubusercontent.com/Bioux1/qbtSearchPlugins/main/fitgirl_repacks.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/esmeraldatorrent.py",
    "https://raw.githubusercontent.com/iordic/qbittorrent-search-plugins/master/engines/elitetorrent.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/dontorrent.py",
    "https://raw.githubusercontent.com/dangar16/dontorrent-plugin/main/dontorrent.py",
    "https://raw.githubusercontent.com/diazchika/dmhy/main/dmhy.py",
    "https://raw.githubusercontent.com/ZH1637/dmhy/main/dmhy.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/divxtotal.py",
    "https://raw.githubusercontent.com/elazar/qbittorrent-search-plugins/refs/heads/add-cloudtorrents-plugin/nova3/engines/cloudtorrents.py",
    "https://raw.githubusercontent.com/BurningMop/qBittorrent-Search-Plugins/refs/heads/main/calidadtorrent.py",
]


async def initiate_search_tools():
    # Check if qBittorrent is available before trying to use it
    if not TorrentManager.qbittorrent:
        LOGGER.warning(
            "qBittorrent is not available - skipping search tools initialization"
        )
        return

    try:
        qb_plugins = await TorrentManager.qbittorrent.search.plugins()
        if qb_plugins:
            names = [plugin.name for plugin in qb_plugins]
            await TorrentManager.qbittorrent.search.uninstall_plugin(names)
            PLUGINS.clear()
        await TorrentManager.qbittorrent.search.install_plugin(SEARCH_PLUGINS)
    except Exception as e:
        LOGGER.error(f"Error initializing search tools: {e}")


async def search(key, site, message, user_tag=""):
    LOGGER.info(f"PLUGINS Searching: {key} from {site}")
    search = await TorrentManager.qbittorrent.search.start(
        pattern=key,
        plugins=[site],
        category="all",
    )
    search_id = search.id
    while True:
        result_status = await TorrentManager.qbittorrent.search.status(search_id)
        status = result_status[0].status
        if status != "Running":
            break
    # Use Config.SEARCH_LIMIT if it's set, otherwise use TELEGRAPH_LIMIT
    search_limit = (
        Config.SEARCH_LIMIT if Config.SEARCH_LIMIT > 0 else TELEGRAPH_LIMIT
    )
    dict_search_results = await TorrentManager.qbittorrent.search.results(
        id=search_id,
        limit=search_limit,
    )
    search_results = dict_search_results.results
    total_results = dict_search_results.total
    if total_results == 0:
        error_msg = await edit_message(
            message,
            f"No result found for <i>{key}</i>\nTorrent Site:- <i>{site.capitalize()}</i>",
        )
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, time=300),
        )  # Auto-delete after 5 minutes
        return

    # Format the message with user tag in a blockquote
    search_limit = (
        Config.SEARCH_LIMIT if Config.SEARCH_LIMIT > 0 else TELEGRAPH_LIMIT
    )
    msg = f"<b><blockquote>{user_tag}, Found {min(total_results, search_limit)}"
    msg += f" result(s) for <i>{key}</i></blockquote></b>\n\n<b>Torrent Site:- <i>{site.capitalize()}</i></b>"

    await TorrentManager.qbittorrent.search.delete(search_id)
    link = await get_result(search_results, key, message)
    buttons = ButtonMaker()
    buttons.url_button("🔎 VIEW", link)
    button = buttons.build_menu(1)
    result_msg = await edit_message(message, msg, button)
    create_task(  # noqa: RUF006
        auto_delete_message(result_msg, time=300),
    )  # Auto-delete after 5 minutes


async def get_result(search_results, key, message):
    telegraph_content = []
    msg = f"<h4>PLUGINS Search Result(s) For {key}</h4>"
    for index, result in enumerate(search_results, start=1):
        msg += f"<a href='{result.descrLink}'>{escape(result.fileName)}</a><br>"
        msg += f"<b>Size: </b>{get_readable_file_size(result.fileSize)}<br>"
        msg += f"<b>Seeders: </b>{result.nbSeeders} | <b>Leechers: </b>{result.nbLeechers}<br>"
        link = result.fileUrl
        if link.startswith("magnet:"):
            msg += f"<b>Share Magnet to</b> <a href='http://t.me/share/url?url={quote(link)}'>Telegram</a><br><br>"
        else:
            msg += f"<a href='{link}'>Direct Link</a><br><br>"

        if len(msg.encode("utf-8")) > 39000:
            telegraph_content.append(msg)
            msg = ""

        search_limit = (
            Config.SEARCH_LIMIT if Config.SEARCH_LIMIT > 0 else TELEGRAPH_LIMIT
        )
        if index == search_limit:
            break

    if msg != "":
        telegraph_content.append(msg)

    await edit_message(
        message,
        f"<b>Creating</b> {len(telegraph_content)} <b>Telegraph pages.</b>",
    )
    path = [
        (
            await telegraph.create_page(
                title="Mirror-leech-bot Torrent Search",
                content=content,
            )
        )["path"]
        for content in telegraph_content
    ]
    if len(path) > 1:
        await edit_message(
            message,
            f"<b>Editing</b> {len(telegraph_content)} <b>Telegraph pages.</b>",
        )
        await telegraph.edit_telegraph(path, telegraph_content)
    return f"https://telegra.ph/{path[0]}"


async def plugin_buttons(user_id):
    buttons = ButtonMaker()
    if not PLUGINS and TorrentManager.qbittorrent:
        try:
            pl = await TorrentManager.qbittorrent.search.plugins()
            PLUGINS.extend(i.name for i in pl)
        except Exception as e:
            LOGGER.error(f"Error getting qBittorrent plugins: {e}")

    for siteName in PLUGINS:
        buttons.data_button(
            siteName.capitalize(),
            f"torser {user_id} {siteName} plugin",
        )
    buttons.data_button("All", f"torser {user_id} all plugin")
    buttons.data_button("Cancel", f"torser {user_id} cancel")
    return buttons.build_menu(2)


@new_task
async def torrent_search(_, message):
    # Check if torrent operations and torrent search are enabled
    if not Config.TORRENT_ENABLED:
        error_msg = await send_message(
            message,
            "❌ Torrent operations are disabled by the administrator.",
        )
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )  # Auto-delete after 5 minutes
        return

    # Check if torrent search is specifically enabled
    if not Config.TORRENT_SEARCH_ENABLED:
        error_msg = await send_message(
            message,
            "❌ Torrent search is disabled by the administrator.",
        )
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )  # Auto-delete after 5 minutes
        return

    # Check if qBittorrent is available for search
    if not TorrentManager.qbittorrent:
        error_msg = await send_message(
            message,
            "❌ qBittorrent is not available. Torrent search requires qBittorrent to be running.",
        )
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )  # Auto-delete after 5 minutes
        return

    user_id = message.from_user.id

    if not message.text:
        error_msg = await send_message(message, "❌ No command text provided.")
        create_task(auto_delete_message(error_msg, message, time=300))
        return

    msg_parts = message.text.split(maxsplit=1)

    if len(msg_parts) == 1:
        # No search key provided
        error_msg = await send_message(
            message,
            "Send a search key along with command",
        )
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )  # Auto-delete after 5 minutes
    else:
        # Search key provided
        search_key = msg_parts[1].strip()
        # Store the search key in the global dictionary
        search_keys[user_id] = search_key

        await delete_message(message)
        button = await plugin_buttons(user_id)

        # Store the search key in the message text
        await send_message(
            message,
            f"Choose site to search for <b>{search_key}</b> | Plugins:",
            button,
        )


@new_task
async def torrent_search_update(_, query):
    user_id = query.from_user.id
    message = query.message
    data = query.data.split()

    # Get the search key from the global dictionary
    search_key = search_keys.get(user_id)
    LOGGER.info(f"Retrieved search key for user {user_id}: {search_key}")

    if user_id != int(data[1]):
        await query.answer("Not Yours!", show_alert=True)
    elif data[2] == "plugin":
        await query.answer()
        button = await plugin_buttons(user_id)
        await edit_message(
            message,
            f"Choose site to search for <b>{search_key}</b>:",
            button,
        )
    elif data[2] != "cancel":
        await query.answer()
        site = data[2]

        if search_key:
            # Get user tag for mention
            user = query.from_user
            user_tag = f"@{user.username}" if user.username else user.mention

            LOGGER.info(f"Searching for '{search_key}' on site '{site}'")
            await edit_message(
                message,
                f"<b><blockquote>{user_tag}, Searching for <i>{search_key}</i></blockquote>\n\nTorrent Site:- <i>{site.capitalize()}</i></b>",
            )
            await search(search_key, site, message, user_tag)
        else:
            LOGGER.error(f"Search key not found for user {user_id}")
            error_msg = await edit_message(
                message,
                "Search key not found. Please try again with a search term.",
            )
            create_task(  # noqa: RUF006
                auto_delete_message(error_msg, time=300),
            )  # Auto-delete after 5 minutes
    else:
        await query.answer()
        cancel_msg = await edit_message(message, "Search has been canceled!")
        create_task(  # noqa: RUF006
            auto_delete_message(cancel_msg, time=300),
        )  # Auto-delete after 5 minutes
        # Clean up the dictionary entry when canceling
        search_keys.pop(
            user_id,
            None,
        )  # Using pop with default None to avoid KeyError
