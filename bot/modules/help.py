from bot.helper.ext_utils.bot_utils import COMMAND_USAGE, new_task
from bot.helper.ext_utils.help_messages import (
    AI_HELP_DICT,
    CLONE_HELP_DICT,
    FORWARD_HELP_DICT,
    GALLERY_DL_HELP_DICT,
    MIRROR_HELP_DICT,
    MUSICDL_HELP_DICT,
    NSFW_HELP_DICT,
    OSINT_HELP_DICT,
    PHISH_HELP_DICT,
    SHORTNER_HELP_DICT,
    STREAMRIP_HELP_DICT,
    TOOL_HELP_DICT,
    TRACE_HELP_DICT,
    VT_HELP_DICT,
    WOT_HELP_DICT,
    YT_HELP_DICT,
    ZOTIFY_HELP_DICT,
    help_string,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    delete_message,
    edit_message,
    send_message,
)


@new_task
async def arg_usage(_, query):
    data = query.data.split()
    message = query.message
    user_id = query.from_user.id

    if data[1] == "close":
        await query.answer()
        await delete_message(message)
        return

    # We don't need to check reply_to_message anymore
    # Just check if the user who clicked the button is the same as the one who sent the command
    if (
        hasattr(message, "reply_to_message")
        and message.reply_to_message
        and hasattr(message.reply_to_message, "from_user")
        and message.reply_to_message.from_user
    ) and user_id != message.reply_to_message.from_user.id:
        await query.answer("Not Yours!", show_alert=True)
        return

    # Handle page navigation
    if data[1] == "page":
        page = data[2]

        # Create navigation buttons
        buttons = ButtonMaker()

        # Add category buttons
        buttons.data_button("🔄 Download", "help page download")
        buttons.data_button("📊 Status", "help page status")
        buttons.data_button("🔍 Search", "help page search")
        buttons.data_button("📁 Files", "help page file")
        buttons.data_button("🔒 Security", "help page security")
        buttons.data_button("⚙️ Settings", "help page settings")
        buttons.data_button("🤖 Special", "help page special")
        buttons.data_button("🛠️ System", "help page system")

        # Add Close button
        buttons.data_button("❌ Close", "help close")

        # Build menu with 3 buttons per row
        button = buttons.build_menu(3)

        await edit_message(message, help_string[page], button)
        await query.answer()
        return

    buttons = ButtonMaker()
    buttons.data_button("Close", "help close")
    button = buttons.build_menu(2)

    if data[1] == "back":
        if data[2] == "m":
            await edit_message(
                message,
                COMMAND_USAGE["mirror"][0],
                COMMAND_USAGE["mirror"][1],
            )
        elif data[2] == "y":
            await edit_message(
                message,
                COMMAND_USAGE["yt"][0],
                COMMAND_USAGE["yt"][1],
            )
        elif data[2] == "c":
            await edit_message(
                message,
                COMMAND_USAGE["clone"][0],
                COMMAND_USAGE["clone"][1],
            )
        elif data[2] == "a":
            await edit_message(
                message,
                COMMAND_USAGE["ai"][0],
                COMMAND_USAGE["ai"][1],
            )
        elif data[2] == "v":
            await edit_message(
                message,
                COMMAND_USAGE["virustotal"][0],
                COMMAND_USAGE["virustotal"][1],
            )
        elif data[2] == "p":
            await edit_message(
                message,
                COMMAND_USAGE["phishcheck"][0],
                COMMAND_USAGE["phishcheck"][1],
            )
        elif data[2] == "sr":
            await edit_message(
                message,
                COMMAND_USAGE["streamrip"][0],
                COMMAND_USAGE["streamrip"][1],
            )
        elif data[2] == "z":
            await edit_message(
                message,
                COMMAND_USAGE["zotify"][0],
                COMMAND_USAGE["zotify"][1],
            )
        elif data[2] == "musicdl":
            await edit_message(
                message,
                COMMAND_USAGE["musicdl"][0],
                COMMAND_USAGE["musicdl"][1],
            )
        elif data[2] == "gdl":
            await edit_message(
                message,
                COMMAND_USAGE["gdl"][0],
                COMMAND_USAGE["gdl"][1],
            )
        elif data[2] == "f2l":
            await edit_message(
                message,
                COMMAND_USAGE["f2l"][0],
                COMMAND_USAGE["f2l"][1],
            )
        elif data[2] == "nsfw":
            await edit_message(
                message,
                COMMAND_USAGE["nsfw"][0],
                COMMAND_USAGE["nsfw"][1],
            )
        elif data[2] == "tool":
            # For Tool commands, show the main help page with buttons
            buttons = ButtonMaker()
            buttons.data_button("🎬 Media Conversion", "help tool Media-Conversion")
            buttons.data_button("🖼️ Image Processing", "help tool Image-Processing")
            buttons.data_button("📝 Text Processing", "help tool Text-Processing")
            buttons.data_button("📦 Other Features", "help tool Other-Features")
            buttons.data_button("❌ Close", "help close")
            button = buttons.build_menu(2)
            await edit_message(message, TOOL_HELP_DICT["main"], button)
        elif data[2] == "osint":
            # For OSINT commands, show the main help page
            buttons = ButtonMaker()
            buttons.data_button("❌ Close", "help close")
            button = buttons.build_menu(1)
            await edit_message(message, OSINT_HELP_DICT["main"], button)
        elif data[2] == "shortner":
            # For Shortner commands, show the main help page
            buttons = ButtonMaker()
            buttons.data_button("❌ Close", "help close")
            button = buttons.build_menu(1)
            await edit_message(message, SHORTNER_HELP_DICT["main"], button)

    elif data[1] == "mirror":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back m")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, MIRROR_HELP_DICT[data[2]], button)
    elif data[1] == "yt":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back y")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, YT_HELP_DICT[data[2]], button)
    elif data[1] == "clone":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back c")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, CLONE_HELP_DICT[data[2]], button)
    elif data[1] == "ai":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back a")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, AI_HELP_DICT[data[2]], button)
    elif data[1] == "vt":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back v")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, VT_HELP_DICT[data[2]], button)
    elif data[1] == "phish":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back p")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, PHISH_HELP_DICT[data[2]], button)
    elif data[1] == "streamrip":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back sr")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, STREAMRIP_HELP_DICT[data[2]], button)
    elif data[1] == "zotify":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back z")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, ZOTIFY_HELP_DICT[data[2]], button)
    elif data[1] == "musicdl":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back musicdl")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, MUSICDL_HELP_DICT[data[2]], button)
    elif data[1] == "gdl":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back gdl")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, GALLERY_DL_HELP_DICT[data[2]], button)

    elif data[1] == "nsfw":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back nsfw")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, NSFW_HELP_DICT[data[2]], button)
    elif data[1] == "tool":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back tool")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, TOOL_HELP_DICT[data[2]], button)
    elif data[1] == "forward":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back forward")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, FORWARD_HELP_DICT[data[2]], button)
    elif data[1] == "trace":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back trace")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, TRACE_HELP_DICT[data[2]], button)
    elif data[1] == "wot":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back wot")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, WOT_HELP_DICT[data[2]], button)
    elif data[1] == "osint":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back osint")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, OSINT_HELP_DICT[data[2]], button)
    elif data[1] == "shortner":
        buttons = ButtonMaker()
        buttons.data_button("Back", "help back shortner")
        buttons.data_button("Close", "help close")
        button = buttons.build_menu(2)
        await edit_message(message, SHORTNER_HELP_DICT[data[2]], button)

    try:
        await query.answer()
    except Exception:
        # Handle the case where the query ID is invalid
        pass


@new_task
async def bot_help(_, message):
    # Delete the /help command and any replied message immediately
    await delete_links(message)

    # Extract page from command if provided
    cmd = message.text.split()
    page = "main"
    if len(cmd) > 1:
        requested_page = cmd[1].lower()
        if requested_page in help_string:
            page = requested_page

    # Create navigation buttons
    buttons = ButtonMaker()

    # Add category buttons
    buttons.data_button("🔄 Download", "help page download")
    buttons.data_button("📊 Status", "help page status")
    buttons.data_button("🔍 Search", "help page search")
    buttons.data_button("📁 Files", "help page file")
    buttons.data_button("🔒 Security", "help page security")
    buttons.data_button("⚙️ Settings", "help page settings")
    buttons.data_button("🤖 Special", "help page special")
    buttons.data_button("🛠️ System", "help page system")

    # Add Close button
    buttons.data_button("❌ Close", "help close")

    # Build menu with 3 buttons per row
    button = buttons.build_menu(3)

    # Send help menu with navigation buttons and set 5-minute auto-delete
    help_msg = await send_message(message, help_string[page], button)
    await auto_delete_message(help_msg, time=300)
