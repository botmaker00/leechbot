from asyncio import Lock, sleep
from datetime import datetime, timedelta
from functools import partial
from io import BytesIO
from re import IGNORECASE, compile
from time import time

from apscheduler.triggers.interval import IntervalTrigger
from feedparser import parse as feed_parse
from httpx import AsyncClient
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler

from bot import LOGGER, rss_dict, scheduler
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import arg_parser, get_size_bytes, new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.exceptions import RssShutdownException
from bot.helper.ext_utils.help_messages import RSS_HELP_MESSAGE
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    send_file,
    send_message,
    send_rss,
)

rss_dict_lock = Lock()
handler_dict = {}
size_regex = compile(r"(\d+(\.\d+)?\s?(GB|MB|KB|GiB|MiB|KiB))", IGNORECASE)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def is_rss_enabled():
    """Check if RSS functionality is enabled via configuration with caching."""
    from bot.core.config_manager import get_config_bool

    return get_config_bool("RSS_ENABLED", True)


async def rss_menu(event):
    user_id = event.from_user.id
    buttons = ButtonMaker()

    # Check if RSS is enabled
    if not is_rss_enabled():
        buttons.data_button("Close", f"rss close {user_id}")
        button = buttons.build_menu(1)
        msg = "RSS functionality is disabled via configuration."
        return msg, button

    # Check if user is owner
    is_owner = await CustomFilters.owner("", event)

    if is_owner:
        buttons.data_button("Subscribe", f"rss sub {user_id}")
        buttons.data_button("Subscriptions", f"rss list {user_id} 0")
        buttons.data_button("Get Items", f"rss get {user_id}")
        buttons.data_button("Edit", f"rss edit {user_id}")
        buttons.data_button("Pause", f"rss pause {user_id}")
        buttons.data_button("Resume", f"rss resume {user_id}")
        buttons.data_button("Unsubscribe", f"rss unsubscribe {user_id}")
        buttons.data_button("All Subscriptions", f"rss listall {user_id} 0")
        buttons.data_button("Pause All", f"rss allpause {user_id}")
        buttons.data_button("Resume All", f"rss allresume {user_id}")
        buttons.data_button("Unsubscribe All", f"rss allunsub {user_id}")
        buttons.data_button("Delete User", f"rss deluser {user_id}")
        if scheduler.running:
            buttons.data_button("Shutdown Rss", f"rss shutdown {user_id}")
        else:
            buttons.data_button("Start Rss", f"rss start {user_id}")
        buttons.data_button("Close", f"rss close {user_id}")
        button = buttons.build_menu(2)
        msg = f"Rss Menu | Users: {len(rss_dict)} | Running: {scheduler.running}"
    else:
        buttons.data_button("Close", f"rss close {user_id}")
        button = buttons.build_menu(1)
        msg = "RSS functionality is restricted to the bot owner only."

    return msg, button


async def update_rss_menu(query):
    msg, button = await rss_menu(query)
    await edit_message(query.message, msg, button)


@new_task
async def get_rss_menu(_, message):
    msg, button = await rss_menu(message)
    await send_message(message, msg, button)


@new_task
async def rss_sub(_, message, pre_event):
    # Check if RSS is enabled
    if not is_rss_enabled():
        await send_message(
            message, "RSS functionality is disabled via configuration."
        )
        return

    user_id = message.from_user.id
    handler_dict[user_id] = False
    if username := message.from_user.username:
        tag = f"@{username}"
    else:
        tag = message.from_user.mention
    # Initialize variables
    msg = ""
    items = message.text.split("\n")
    success_count = 0
    error_count = 0

    # Process each feed subscription
    for index, item in enumerate(items, start=1):
        # Skip empty lines
        if not item.strip():
            continue

        # Log the item being processed
        args = item.split()

        title = args[0].strip()
        feed_link = args[1].strip()

        if (user_feeds := rss_dict.get(user_id, False)) and title in user_feeds:
            await send_message(
                message,
                f"This title {title} already subscribed! Choose another title!",
            )
            continue
        if feed_link.startswith(("-inf", "-exf", "-c")):
            await send_message(
                message,
                f"Wrong input in line {index}! Add Title! Read the example!",
            )
            continue
        inf_lists = []
        exf_lists = []
        if len(args) > 2:
            arg_base = {"-c": None, "-inf": None, "-exf": None, "-stv": None}
            arg_parser(args[2:], arg_base)
            cmd = arg_base["-c"]
            inf = arg_base["-inf"]
            exf = arg_base["-exf"]
            stv = arg_base["-stv"]
            if stv is not None:
                stv = stv.lower() == "true"
            if inf is not None:
                filters_list = inf.split("|")
                for x in filters_list:
                    y = x.split(" or ")
                    inf_lists.append(y)
            if exf is not None:
                filters_list = exf.split("|")
                for x in filters_list:
                    y = x.split(" or ")
                    exf_lists.append(y)
        else:
            inf = None
            exf = None
            cmd = None
            stv = False
        try:
            async with AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=60,
                verify=False,
            ) as client:
                res = await client.get(feed_link)
            html = res.text
            rss_d = feed_parse(html)

            # Check if the feed has any entries
            if not rss_d.entries:
                raise IndexError("No entries found in the RSS feed")

            last_title = rss_d.entries[0].get("title", "No Title")
            if rss_d.entries[0].get("size"):
                size = int(rss_d.entries[0]["size"])
            elif rss_d.entries[0].get("summary"):
                summary = rss_d.entries[0]["summary"]
                matches = size_regex.findall(summary)
                if matches:
                    sizes = [match[0] for match in matches]
                    size = get_size_bytes(sizes[0])
                else:
                    size = 0
            else:
                size = 0
            # Build a concise message for this feed
            feed_msg = "<b>Subscribed!</b>"
            feed_msg += (
                f"\n<b>Title: </b><code>{title}</code>\n<b>Feed Url: </b>{feed_link}"
            )
            feed_msg += f"\n<b>Latest record for </b>{getattr(rss_d.feed, 'title', 'Unknown Feed')}:"
            feed_msg += f"\nName: <code>{last_title.replace('>', '').replace('<', '')}</code>"
            try:
                if (
                    "links" in rss_d.entries[0]
                    and len(rss_d.entries[0]["links"]) > 1
                ):
                    last_link = rss_d.entries[0]["links"][1]["href"]
                else:
                    last_link = rss_d.entries[0].get("link", "No link available")
            except Exception:
                last_link = "No link available"
            feed_msg += f"\n<b>Link: </b><code>{last_link}</code>"
            if size:
                feed_msg += f"\nSize: {get_readable_file_size(size)}"
            feed_msg += f"\n<b>Command: </b><code>{cmd}</code>"
            feed_msg += f"\n<b>Filters:-</b>\ninf: <code>{inf}</code>\nexf: <code>{exf}</code>\n<b>Sensitive: </b>{stv}"

            # Add site name
            try:
                from urllib.parse import urlparse

                parsed_url = urlparse(feed_link)
                site_name = parsed_url.netloc.replace("www.", "")
                feed_msg += f"\n<b>Site: </b><code>{site_name}</code>"
            except Exception:
                pass
            # Add a separator between feeds
            if msg:
                msg += "\n\n" + "-" * 30 + "\n\n"
            msg += feed_msg
            # Get site name from the URL
            try:
                from urllib.parse import urlparse

                parsed_url = urlparse(feed_link)
                site_name = parsed_url.netloc.replace("www.", "")
            except Exception:
                site_name = "Unknown"

            async with rss_dict_lock:
                if rss_dict.get(user_id, False):
                    rss_dict[user_id][title] = {
                        "link": feed_link,
                        "last_feed": last_link,
                        "last_title": last_title,
                        "inf": inf_lists,
                        "exf": exf_lists,
                        "paused": False,
                        "command": cmd,
                        "sensitive": stv,
                        "tag": tag,
                        "site_name": site_name,
                    }
                else:
                    rss_dict[user_id] = {
                        title: {
                            "link": feed_link,
                            "last_feed": last_link,
                            "last_title": last_title,
                            "inf": inf_lists,
                            "exf": exf_lists,
                            "paused": False,
                            "command": cmd,
                            "sensitive": stv,
                            "tag": tag,
                            "site_name": site_name,
                        },
                    }
            LOGGER.info(
                f"RSS Feed Added: id: {user_id} - title: {title} - link: {feed_link} - c: {cmd} - inf: {inf} - exf: {exf} - stv: {stv}",
            )
            success_count += 1
        except (IndexError, AttributeError) as e:
            error_msg = f"The link: {feed_link} doesn't seem to be a RSS feed or it's region-blocked!"
            LOGGER.error(f"Error adding RSS feed {title}: {error_msg} - {e}")
            error_count += 1
            # Don't send individual error messages for each feed to avoid flooding
            # Just add to the error count
        except Exception as e:
            error_details = str(e) if e else "Unknown error occurred"
            LOGGER.error(
                f"Unexpected error adding RSS feed {title}: {error_details}"
            )
            error_count += 1
            # Don't send individual error messages for each feed to avoid flooding
            # Just add to the error count

    # Send a summary message
    summary = ""
    if success_count > 0:
        summary += f"✅ Successfully added {success_count} RSS feed(s)\n"
    if error_count > 0:
        summary += (
            f"❌ Failed to add {error_count} RSS feed(s). Check logs for details.\n"
        )

    if msg:
        # If we have detailed messages for some feeds, include them
        # But limit the message size to avoid Telegram API errors
        if len(msg) > 3800:  # Leave some room for the summary
            msg = msg[:3800] + "...\n(message truncated due to length)"

        # Combine summary and detailed messages
        final_msg = summary + "\n" + msg

        # Update the database
        await database.rss_update(user_id)

        # Send the message with proper error handling
        try:
            await send_message(message, final_msg)
        except Exception as e:
            LOGGER.error(f"Error sending RSS subscription summary: {e}")
            # Try with just the summary as a fallback
            try:
                await send_message(message, summary)
            except Exception as e2:
                LOGGER.error(f"Error sending simplified summary too: {e2}")

        # Handle scheduler
        is_sudo = await CustomFilters.sudo("", message)
        if scheduler.state == 2:
            scheduler.resume()
        elif is_sudo and not scheduler.running:
            add_job()
            scheduler.start()
    elif success_count > 0 or error_count > 0:
        # If we have no detailed messages but some feeds were processed, send the summary
        try:
            await send_message(message, summary)
        except Exception as e:
            LOGGER.error(f"Error sending RSS subscription summary: {e}")
    await update_rss_menu(pre_event)


async def get_user_id(title):
    async with rss_dict_lock:
        return next(
            (
                (True, user_id)
                for user_id, feeds in rss_dict.items()
                if title in feeds
            ),
            (False, False),
        )


@new_task
async def rss_update(_, message, pre_event, state):
    # Check if RSS is enabled
    if not is_rss_enabled():
        await send_message(
            message, "RSS functionality is disabled via configuration."
        )
        return

    user_id = message.from_user.id
    handler_dict[user_id] = False
    titles = message.text.split()
    is_sudo = await CustomFilters.sudo("", message)
    updated = []
    for title in titles:
        title = title.strip()
        if not (res := rss_dict[user_id].get(title, False)):
            if is_sudo:
                res, user_id = await get_user_id(title)
            if not res:
                user_id = message.from_user.id
                await send_message(message, f"{title} not found!")
                continue
        istate = rss_dict[user_id][title].get("paused", False)
        if (istate and state == "pause") or (not istate and state == "resume"):
            await send_message(message, f"{title} already {state}d!")
            continue
        async with rss_dict_lock:
            updated.append(title)
            if state == "unsubscribe":
                del rss_dict[user_id][title]
            elif state == "pause":
                rss_dict[user_id][title]["paused"] = True
            elif state == "resume":
                rss_dict[user_id][title]["paused"] = False
        if state == "resume":
            if scheduler.state == 2:
                scheduler.resume()
            elif is_sudo and not scheduler.running:
                add_job()
                scheduler.start()
        if is_sudo and Config.DATABASE_URL and user_id != message.from_user.id:
            await database.rss_update(user_id)
        if not rss_dict[user_id]:
            async with rss_dict_lock:
                del rss_dict[user_id]
            await database.rss_delete(user_id)
            if not rss_dict:
                await database.trunc_table("rss")
    if updated:
        LOGGER.info(
            f"RSS link(s) {state}d: {len(updated)}. {updated} has been {state}d!"
        )
        await send_message(
            message,
            f"RSS links with Title(s): <code>{updated}</code> has been {state}d!",
        )
        if rss_dict.get(user_id):
            await database.rss_update(user_id)
    await update_rss_menu(pre_event)


async def rss_list(query, start, all_users=False):
    user_id = query.from_user.id
    buttons = ButtonMaker()
    if all_users:
        list_feed = f"<b>All subscriptions | Page: {int(start / 5)} </b>"
        async with rss_dict_lock:
            keysCount = sum(len(v.keys()) for v in rss_dict.values())
            index = 0
            for titles in rss_dict.values():
                for index, (title, data) in enumerate(
                    list(titles.items())[start : 5 + start],
                ):
                    list_feed += f"\n\n<b>Title:</b> <code>{title}</code>\n"
                    list_feed += f"<b>Feed Url:</b> <code>{data['link']}</code>\n"
                    list_feed += f"<b>Command:</b> <code>{data['command']}</code>\n"
                    list_feed += f"<b>Inf:</b> <code>{data['inf']}</code>\n"
                    list_feed += f"<b>Exf:</b> <code>{data['exf']}</code>\n"
                    list_feed += f"<b>Sensitive:</b> <code>{data.get('sensitive', False)}</code>\n"
                    list_feed += f"<b>Paused:</b> <code>{data['paused']}</code>\n"
                    # Add site name if available
                    if site_name := data.get("site_name"):
                        list_feed += f"<b>Site:</b> <code>{site_name}</code>\n"
                    list_feed += f"<b>User:</b> {data['tag'].replace('@', '', 1)}"
                    index += 1
                    if index == 5:
                        break
    else:
        list_feed = f"<b>Your subscriptions | Page: {int(start / 5)} </b>"
        async with rss_dict_lock:
            keysCount = len(rss_dict.get(user_id, {}).keys())
            for title, data in list(rss_dict[user_id].items())[start : 5 + start]:
                list_feed += f"\n\n<b>Title:</b> <code>{title}</code>\n<b>Feed Url: </b><code>{data['link']}</code>\n"
                list_feed += f"<b>Command:</b> <code>{data['command']}</code>\n"
                list_feed += f"<b>Inf:</b> <code>{data['inf']}</code>\n"
                list_feed += f"<b>Exf:</b> <code>{data['exf']}</code>\n"
                list_feed += f"<b>Sensitive:</b> <code>{data.get('sensitive', False)}</code>\n"
                list_feed += f"<b>Paused:</b> <code>{data['paused']}</code>\n"
                # Add site name if available
                if site_name := data.get("site_name"):
                    list_feed += f"<b>Site:</b> <code>{site_name}</code>\n"
    buttons.data_button("Back", f"rss back {user_id}")
    buttons.data_button("Close", f"rss close {user_id}")
    if keysCount > 5:
        for x in range(0, keysCount, 5):
            buttons.data_button(
                f"{int(x / 5)}",
                f"rss list {user_id} {x}",
                position="footer",
            )
    button = buttons.build_menu(2)
    if query.message.text.html == list_feed:
        return
    await edit_message(query.message, list_feed, button)


@new_task
async def rss_get(_, message, pre_event):
    # Check if RSS is enabled
    if not is_rss_enabled():
        await send_message(
            message, "RSS functionality is disabled via configuration."
        )
        return

    user_id = message.from_user.id
    handler_dict[user_id] = False
    args = message.text.split()
    if len(args) < 2:
        await send_message(
            message,
            f"{args}. Wrong Input format. You should add number of the items you want to get. Read help message before adding new subcription!",
        )
        await update_rss_menu(pre_event)
        return
    try:
        title = args[0]
        count = int(args[1])
        data = rss_dict[user_id].get(title, False)
        if data and count > 0:
            try:
                msg = await send_message(
                    message,
                    f"Getting the last <b>{count}</b> item(s) from {title}",
                )
                async with AsyncClient(
                    headers=headers,
                    follow_redirects=True,
                    timeout=60,
                    verify=False,
                ) as client:
                    res = await client.get(data["link"])
                html = res.text
                rss_d = feed_parse(html)
                item_info = ""

                # Check if the feed has any entries
                if not rss_d.entries:
                    await edit_message(msg, "No entries found in this RSS feed.")
                    return

                # Limit count to available entries
                count = min(count, len(rss_d.entries))

                for item_num in range(count):
                    try:
                        if (
                            "links" in rss_d.entries[item_num]
                            and len(rss_d.entries[item_num]["links"]) > 1
                        ):
                            link = rss_d.entries[item_num]["links"][1]["href"]
                        else:
                            link = rss_d.entries[item_num].get(
                                "link", "No link available"
                            )

                        title = rss_d.entries[item_num].get("title", "No Title")
                        item_info += f"<b>Name: </b><code>{title.replace('>', '').replace('<', '')}</code>\n"
                        item_info += f"<b>Link: </b><code>{link}</code>\n\n"
                    except Exception as e:
                        LOGGER.error(f"Error processing entry {item_num}: {e!s}")
                        continue
                item_info_ecd = item_info.encode()
                if len(item_info_ecd) > 4000:
                    with BytesIO(item_info_ecd) as out_file:
                        out_file.name = f"rssGet {title} items_no. {count}.txt"
                        await send_file(message, out_file)
                    await delete_message(msg)
                else:
                    await edit_message(msg, item_info)
            except IndexError as e:
                LOGGER.error(str(e))
                await edit_message(
                    msg,
                    "Parse depth exceeded. Try again with a lower value.",
                )
            except Exception as e:
                LOGGER.error(str(e))
                await edit_message(msg, str(e))
        else:
            await send_message(message, "Enter a valid title. Title not found!")
    except Exception as e:
        LOGGER.error(str(e))
        await send_message(message, f"Enter a valid value!. {e}")
    await update_rss_menu(pre_event)


@new_task
async def rss_edit(_, message, pre_event):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    items = message.text.split("\n")
    updated = False
    for item in items:
        args = item.split()
        title = args[0].strip()
        if len(args) < 2:
            await send_message(
                message,
                f"{item}. Wrong Input format. Read help message before editing!",
            )
            continue
        if not rss_dict[user_id].get(title, False):
            await send_message(message, "Enter a valid title. Title not found!")
            continue
        updated = True
        inf_lists = []
        exf_lists = []
        arg_base = {"-c": None, "-inf": None, "-exf": None, "-stv": None}
        arg_parser(args[1:], arg_base)
        cmd = arg_base["-c"]
        inf = arg_base["-inf"]
        exf = arg_base["-exf"]
        stv = arg_base["-stv"]
        async with rss_dict_lock:
            if stv is not None:
                stv = stv.lower() == "true"
                rss_dict[user_id][title]["sensitive"] = stv
            if cmd is not None:
                if cmd.lower() == "none":
                    cmd = None
                rss_dict[user_id][title]["command"] = cmd
            if inf is not None:
                if inf.lower() != "none":
                    filters_list = inf.split("|")
                    for x in filters_list:
                        y = x.split(" or ")
                        inf_lists.append(y)
                rss_dict[user_id][title]["inf"] = inf_lists
            if exf is not None:
                if exf.lower() != "none":
                    filters_list = exf.split("|")
                    for x in filters_list:
                        y = x.split(" or ")
                        exf_lists.append(y)
                rss_dict[user_id][title]["exf"] = exf_lists
    if updated:
        await database.rss_update(user_id)
    await update_rss_menu(pre_event)


@new_task
async def rss_delete(_, message, pre_event):
    handler_dict[message.from_user.id] = False
    users = message.text.split()
    for user in users:
        user = int(user)
        async with rss_dict_lock:
            del rss_dict[user]
        await database.rss_delete(user)
    await update_rss_menu(pre_event)


async def event_handler(client, query, pfunc):
    user_id = query.from_user.id
    handler_dict[user_id] = True
    start_time = time()

    # Create a filter function that ignores the first two parameters
    async def event_filter(*args):
        # The actual event is the third parameter
        event = args[2]
        user = event.from_user or event.sender_chat

        # Check if user is None before accessing id
        if user is None:
            return False

        return bool(
            user.id == user_id
            and event.chat.id == query.message.chat.id
            and event.text,
        )

    handler = client.add_handler(
        MessageHandler(pfunc, create(event_filter)),
        group=-1,
    )
    while handler_dict[user_id]:
        await sleep(0.5)
        if time() - start_time > 60:
            handler_dict[user_id] = False
            await update_rss_menu(query)
    client.remove_handler(*handler)


@new_task
async def rss_listener(client, query):
    user_id = query.from_user.id
    message = query.message
    data = query.data.split()
    # Check if user is owner
    is_owner = await CustomFilters.owner("", query)

    # Only allow owner to use RSS functionality
    if not is_owner:
        await query.answer(
            text="You don't have permission to use these buttons!",
            show_alert=True,
        )
    elif data[1] == "close":
        await query.answer()
        handler_dict[user_id] = False
        await delete_message(message.reply_to_message)
        await delete_message(message)
    elif data[1] == "back":
        await query.answer()
        handler_dict[user_id] = False
        await update_rss_menu(query)
    elif data[1] == "sub":
        await query.answer()
        handler_dict[user_id] = False
        buttons = ButtonMaker()
        buttons.data_button("Back", f"rss back {user_id}")
        buttons.data_button("Close", f"rss close {user_id}")
        button = buttons.build_menu(2)
        await edit_message(message, RSS_HELP_MESSAGE, button)
        pfunc = partial(rss_sub, pre_event=query)
        await event_handler(client, query, pfunc)
    elif data[1] == "list":
        handler_dict[user_id] = False
        if len(rss_dict.get(int(data[2]), {})) == 0:
            await query.answer(text="No subscriptions!", show_alert=True)
        else:
            await query.answer()
            start = int(data[3])
            await rss_list(query, start)
    elif data[1] == "get":
        handler_dict[user_id] = False
        if len(rss_dict.get(int(data[2]), {})) == 0:
            await query.answer(text="No subscriptions!", show_alert=True)
        else:
            await query.answer()
            buttons = ButtonMaker()
            buttons.data_button("Back", f"rss back {user_id}")
            buttons.data_button("Close", f"rss close {user_id}")
            button = buttons.build_menu(2)
            await edit_message(
                message,
                "Send one title with value separated by space get last X items.\nTitle Value\nTimeout: 60 sec.",
                button,
            )
            pfunc = partial(rss_get, pre_event=query)
            await event_handler(client, query, pfunc)
    elif data[1] in ["unsubscribe", "pause", "resume"]:
        handler_dict[user_id] = False
        if len(rss_dict.get(int(data[2]), {})) == 0:
            await query.answer(text="No subscriptions!", show_alert=True)
        else:
            await query.answer()
            buttons = ButtonMaker()
            buttons.data_button("Back", f"rss back {user_id}")
            if data[1] == "pause":
                buttons.data_button("Pause AllMyFeeds", f"rss uallpause {user_id}")
            elif data[1] == "resume":
                buttons.data_button("Resume AllMyFeeds", f"rss uallresume {user_id}")
            elif data[1] == "unsubscribe":
                buttons.data_button("Unsub AllMyFeeds", f"rss uallunsub {user_id}")
            buttons.data_button("Close", f"rss close {user_id}")
            button = buttons.build_menu(2)
            await edit_message(
                message,
                f"Send one or more rss titles separated by space to {data[1]}.\nTimeout: 60 sec.",
                button,
            )
            pfunc = partial(rss_update, pre_event=query, state=data[1])
            await event_handler(client, query, pfunc)
    elif data[1] == "edit":
        handler_dict[user_id] = False
        if len(rss_dict.get(int(data[2]), {})) == 0:
            await query.answer(text="No subscriptions!", show_alert=True)
        else:
            await query.answer()
            buttons = ButtonMaker()
            buttons.data_button("Back", f"rss back {user_id}")
            buttons.data_button("Close", f"rss close {user_id}")
            button = buttons.build_menu(2)
            msg = """Send one or more rss titles with new filters or command separated by new line.
Examples:
Title1 -c mirror -up remote:path/subdir -exf none -inf 1080 or 720 -stv true
Title2 -c none -inf none -stv false
Title3 -c mirror -rcf xxx -up xxx -z pswd -stv false
Note: Only what you provide will be edited, the rest will be the same like example 2: exf will stay same as it is.
Timeout: 60 sec. Argument -c for command and arguments
            """
            await edit_message(message, msg, button)
            pfunc = partial(rss_edit, pre_event=query)
            await event_handler(client, query, pfunc)
    elif data[1].startswith("uall"):
        handler_dict[user_id] = False
        if len(rss_dict.get(int(data[2]), {})) == 0:
            await query.answer(text="No subscriptions!", show_alert=True)
            return
        await query.answer()
        if data[1].endswith("unsub"):
            async with rss_dict_lock:
                del rss_dict[int(data[2])]
            await database.rss_delete(int(data[2]))
            await update_rss_menu(query)
        elif data[1].endswith("pause"):
            async with rss_dict_lock:
                for title in list(rss_dict[int(data[2])].keys()):
                    rss_dict[int(data[2])][title]["paused"] = True
            await database.rss_update(int(data[2]))
        elif data[1].endswith("resume"):
            async with rss_dict_lock:
                for title in list(rss_dict[int(data[2])].keys()):
                    rss_dict[int(data[2])][title]["paused"] = False
            if scheduler.state == 2:
                scheduler.resume()
            await database.rss_update(int(data[2]))
        await update_rss_menu(query)
    elif data[1].startswith("all"):
        if len(rss_dict) == 0:
            await query.answer(text="No subscriptions!", show_alert=True)
            return
        await query.answer()
        if data[1].endswith("unsub"):
            async with rss_dict_lock:
                rss_dict.clear()
            await database.trunc_table("rss")
            await update_rss_menu(query)
        elif data[1].endswith("pause"):
            async with rss_dict_lock:
                for user in list(rss_dict.keys()):
                    for title in list(rss_dict[user].keys()):
                        rss_dict[user][title]["paused"] = True
            if scheduler.running:
                scheduler.pause()
            await database.rss_update_all()
        elif data[1].endswith("resume"):
            async with rss_dict_lock:
                for user in list(rss_dict.keys()):
                    for title in list(rss_dict[user].keys()):
                        rss_dict[user][title]["paused"] = False
            if scheduler.state == 2:
                scheduler.resume()
            elif not scheduler.running:
                add_job()
                scheduler.start()
            await database.rss_update_all()
    elif data[1] == "deluser":
        if len(rss_dict) == 0:
            await query.answer(text="No subscriptions!", show_alert=True)
        else:
            await query.answer()
            buttons = ButtonMaker()
            buttons.data_button("Back", f"rss back {user_id}")
            buttons.data_button("Close", f"rss close {user_id}")
            button = buttons.build_menu(2)
            msg = "Send one or more user_id separated by space to delete their resources.\nTimeout: 60 sec."
            await edit_message(message, msg, button)
            pfunc = partial(rss_delete, pre_event=query)
            await event_handler(client, query, pfunc)
    elif data[1] == "listall":
        if not rss_dict:
            await query.answer(text="No subscriptions!", show_alert=True)
        else:
            await query.answer()
            start = int(data[3])
            await rss_list(query, start, all_users=True)
    elif data[1] == "shutdown":
        if scheduler.running:
            await query.answer()
            scheduler.shutdown(wait=False)
            await sleep(0.5)
            await update_rss_menu(query)
        else:
            await query.answer(text="Already Stopped!", show_alert=True)
    elif data[1] == "start":
        if not scheduler.running:
            await query.answer()
            add_job()
            scheduler.start()
            await update_rss_menu(query)
        else:
            await query.answer(text="Already Running!", show_alert=True)


async def rss_monitor():
    # Add memory management
    import gc

    import psutil

    # Force garbage collection before starting
    gc.collect()

    # Check memory usage
    memory_info = psutil.virtual_memory()
    if memory_info.percent > 90:  # If memory usage is above 90%
        return

    # Add memory management
    import gc

    import psutil

    # Force garbage collection before starting
    gc.collect()

    # Check memory usage
    memory_info = psutil.virtual_memory()
    if memory_info.percent > 90:  # If memory usage is above 90%
        return

    chat = Config.RSS_CHAT
    if not chat:
        scheduler.shutdown(wait=False)
        return
    if len(rss_dict) == 0:
        scheduler.pause()
        return
    all_paused = True
    rss_topic_id = rss_chat_id = None
    if isinstance(chat, int):
        rss_chat_id = chat
    elif "|" in chat:
        rss_chat_id, rss_topic_id = [
            int(x) if x.lstrip("-").isdigit() else x for x in chat.split("|", 1)
        ]
    elif chat.lstrip("-").isdigit():
        rss_chat_id = int(chat)

    # Initialize variables

    # Make a copy of the dictionary to avoid modification during iteration
    for user, items in list(rss_dict.items()):
        for title, data in list(items.items()):
            try:
                if data["paused"]:
                    continue

                # Regular RSS feed processing
                tries = 0
                while True:
                    try:
                        async with AsyncClient(
                            headers=headers,
                            follow_redirects=True,
                            timeout=60,
                            verify=False,
                        ) as client:
                            res = await client.get(data["link"])
                        html = res.text
                        break
                    except Exception as fetch_error:
                        tries += 1
                        if tries > 3:
                            raise Exception(
                                f"Failed to fetch RSS feed after {tries} attempts: {fetch_error}"
                            )
                        continue
                rss_d = feed_parse(html)
                all_paused = False

                # Check if there are any entries in the feed
                if not rss_d.entries:
                    continue

                try:
                    # Safely get the last link
                    if (
                        "links" in rss_d.entries[0]
                        and len(rss_d.entries[0]["links"]) > 1
                    ):
                        last_link = rss_d.entries[0]["links"][1]["href"]
                    elif "link" in rss_d.entries[0]:
                        last_link = rss_d.entries[0]["link"]
                    else:
                        # If we can't get a link, use a placeholder and log it
                        last_link = "No link available"
                        LOGGER.warning(f"No link found in RSS feed: {data['link']}")
                except (IndexError, KeyError) as e:
                    LOGGER.error(
                        f"Error getting link from RSS feed: {e} - {data['link']}"
                    )
                    continue

                # Safely get the last title
                if "title" in rss_d.entries[0]:
                    last_title = rss_d.entries[0]["title"]
                else:
                    last_title = "Unknown Title"
                # Check if we've seen this item before
                if (
                    data["last_feed"] == last_link
                    or data["last_title"] == last_title
                ):
                    continue
                feed_count = 0
                while True:
                    try:
                        await sleep(10)
                    except Exception:
                        raise RssShutdownException("Rss Monitor Stopped!") from None
                    try:
                        # Check if feed_count is within the range of available entries
                        if feed_count >= len(rss_d.entries):
                            # Only log at debug level to avoid cluttering logs
                            break

                        # Safely get the item title
                        if "title" in rss_d.entries[feed_count]:
                            item_title = rss_d.entries[feed_count]["title"]
                        else:
                            item_title = f"Unknown Title {feed_count}"

                        # Safely get the URL
                        try:
                            if (
                                "links" in rss_d.entries[feed_count]
                                and len(rss_d.entries[feed_count]["links"]) > 1
                            ):
                                url = rss_d.entries[feed_count]["links"][1]["href"]
                            else:
                                url = rss_d.entries[feed_count]["link"]
                        except (IndexError, KeyError):
                            # If we can't get a URL, skip this entry
                            feed_count += 1
                            continue

                        # Check if we've seen this item before
                        if (
                            data["last_feed"] == url
                            or data["last_title"] == item_title
                        ):
                            break
                        if rss_d.entries[feed_count].get("size"):
                            size = int(rss_d.entries[feed_count]["size"])
                        elif rss_d.entries[feed_count].get("summary"):
                            summary = rss_d.entries[feed_count]["summary"]
                            matches = size_regex.findall(summary)
                            sizes = [match[0] for match in matches]
                            size = get_size_bytes(sizes[0])
                        else:
                            size = 0
                    except IndexError:
                        # Only log at debug level to avoid cluttering logs
                        break
                    parse = True
                    for flist in data["inf"]:
                        if (
                            data.get("sensitive", False)
                            and all(
                                x.lower() not in item_title.lower() for x in flist
                            )
                        ) or (
                            not data.get("sensitive", False)
                            and all(x not in item_title for x in flist)
                        ):
                            parse = False
                            feed_count += 1
                            break
                    if not parse:
                        continue
                    for flist in data["exf"]:
                        if (
                            data.get("sensitive", False)
                            and any(x.lower() in item_title.lower() for x in flist)
                        ) or (
                            not data.get("sensitive", False)
                            and any(x in item_title for x in flist)
                        ):
                            parse = False
                            feed_count += 1
                            break
                    if not parse:
                        continue
                    # Sanitize item title and URL to prevent Telegram API errors
                    sanitized_title = item_title.replace(">", "").replace("<", "")
                    # Remove zero-width characters and other potentially problematic characters
                    sanitized_title = (
                        sanitized_title.replace("\u200b", "")
                        .replace("\u200c", "")
                        .replace("\u200d", "")
                    )
                    # Replace any other control characters
                    sanitized_title = "".join(
                        c if ord(c) >= 32 or c == "\n" else " "
                        for c in sanitized_title
                    )

                    # Sanitize URL
                    sanitized_url = url

                    if command := data["command"]:
                        if (
                            size
                            and Config.RSS_SIZE_LIMIT
                            and size > Config.RSS_SIZE_LIMIT
                        ):
                            feed_count += 1
                            continue
                        cmd = command.split(maxsplit=1)
                        cmd.insert(1, sanitized_url)
                        feed_msg = " ".join(cmd)
                        if not feed_msg.startswith("/"):
                            feed_msg = f"/{feed_msg}"
                    else:
                        feed_msg = f"<b>Name: </b><code>{sanitized_title}</code>"
                        feed_msg += f"\n\n<b>Link: </b><code>{sanitized_url}</code>"
                        if size:
                            feed_msg += (
                                f"\n<b>Size: </b>{get_readable_file_size(size)}"
                            )
                    # Add site name for all feeds
                    # Use the site_name from the dictionary if available, otherwise extract it from the URL
                    site_name = data.get("site_name", "")
                    if not site_name:
                        # Extract the site name from the URL
                        try:
                            from urllib.parse import urlparse

                            parsed_url = urlparse(data["link"])
                            site_name = parsed_url.netloc.replace("www.", "")
                        except Exception:
                            site_name = "Unknown"

                    site_info = f" | <b>Site:</b> <code>{site_name}</code>"
                    feed_msg += f"\n<b>Tag: </b><code>{data['tag']}</code> <code>{user}</code>{site_info}\n\n<blockquote><b>>> {Config.CREDIT} <<</b></blockquote>"

                    # Validate message content before sending
                    if not feed_msg.strip():
                        LOGGER.error(
                            f"Empty message generated for {title}. Skipping."
                        )
                        feed_count += 1
                        continue

                    # Sanitize message content to avoid Telegram API errors
                    try:
                        # Remove any potentially problematic characters
                        feed_msg = (
                            feed_msg.replace("\u200b", "")
                            .replace("\u200c", "")
                            .replace("\u200d", "")
                        )

                        # Ensure the message is not too long
                        if len(feed_msg) > 4096:
                            feed_msg = feed_msg[:4093] + "..."

                        await send_rss(feed_msg, rss_chat_id, rss_topic_id)

                        feed_count += 1
                    except Exception as e:
                        LOGGER.error(f"Error sending RSS message for {title}: {e}")
                        # Try with a simplified message as a fallback
                        try:
                            simplified_msg = (
                                f"<b>Title:</b> {item_title}\n<b>Link:</b> {url}"
                            )
                            await send_rss(simplified_msg, rss_chat_id, rss_topic_id)
                            feed_count += 1
                        except Exception as e2:
                            LOGGER.error(
                                f"Failed to send simplified message too: {e2}"
                            )
                            feed_count += 1
                async with rss_dict_lock:
                    if user not in rss_dict or not rss_dict[user].get(title, False):
                        continue
                    update_data = {"last_feed": last_link, "last_title": last_title}

                    rss_dict[user][title].update(update_data)
                await database.rss_update(user)
            except RssShutdownException:
                break
            except Exception as e:
                error_msg = str(e) if e else "Unknown error"
                feed_name = title if title else "Unknown"
                feed_link = data.get("link", "Unknown") if data else "Unknown"
                LOGGER.error(
                    f"RSS Feed Error: {error_msg} - Feed Name: {feed_name} - Feed Link: {feed_link}"
                )
                continue
    if all_paused:
        scheduler.pause()


def add_job():
    # Check if RSS is enabled using cached config
    from bot.core.config_manager import get_config_bool, get_config_int

    if not get_config_bool("RSS_ENABLED", True):
        LOGGER.info("RSS functionality is disabled via configuration")
        return

    # Use RSS_JOB_INTERVAL if available, otherwise fall back to RSS_DELAY
    rss_interval = get_config_int(
        "RSS_JOB_INTERVAL", get_config_int("RSS_DELAY", 600)
    )
    rss_delay = max(600, rss_interval)  # Minimum 10 minutes

    scheduler.add_job(
        rss_monitor,
        trigger=IntervalTrigger(seconds=rss_delay),
        id="0",
        name="RSS",
        misfire_grace_time=300,  # Increased grace time to handle longer executions
        max_instances=1,
        next_run_time=datetime.now()
        + timedelta(seconds=60),  # Delayed start to reduce startup load
        replace_existing=True,
        coalesce=True,  # Combine missed executions into a single one
    )
    LOGGER.info(
        f"RSS job scheduled with interval of {rss_delay} seconds (RSS_ENABLED: {get_config_bool('RSS_ENABLED', True)})"
    )


# Only start RSS if enabled
from bot.core.config_manager import get_config_bool

if get_config_bool("RSS_ENABLED", True):
    add_job()
    scheduler.start()
    LOGGER.info("RSS system started")
else:
    LOGGER.info("RSS system disabled via configuration")
