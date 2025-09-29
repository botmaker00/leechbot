from bot.core.config_manager import Config
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


async def handle_qb_commands(_, message):
    """Handle deprecated commands and show warning messages.

    Currently handles:
    - /qbleech and variants: Suggests using /leech instead
    - /qbmirror and variants: Suggests using /mirror instead

    Args:
        _: The client instance (unused)
        message: The message object containing the command
    """
    # Check if command warnings are enabled
    if not Config.WRONG_CMD_WARNINGS_ENABLED:
        return

    if not message.text:
        return
    command = message.text.split()[0].lower()

    if "qbleech" in command:
        warning_msg = "⚠️ <b>Warning:</b> /qbleech command is deprecated. Please use /leech command instead."
    else:  # qbmirror
        warning_msg = "⚠️ <b>Warning:</b> /qbmirror command is deprecated. Please use /mirror command instead."

    # Send warning message
    reply = await send_message(message, warning_msg)

    # Schedule both messages for auto-deletion after 5 minutes (300 seconds)
    await auto_delete_message(reply, message, time=300)


async def handle_no_suffix_commands(client, message):  # noqa: ARG001
    """Handle commands with incorrect suffixes and show warning messages.

    Logic:
    - If CMD_SUFFIX is set (e.g., "4") and CORRECT_CMD_SUFFIX is set (e.g., "2,3,none"):
      - /sox1 -> Warning: use /sox4 (current CMD_SUFFIX)
      - /sox2 -> No warning (allowed in CORRECT_CMD_SUFFIX)
      - /sox3 -> No warning (allowed in CORRECT_CMD_SUFFIX)
      - /sox4 -> No warning (current CMD_SUFFIX)
      - /sox -> No warning (if "none" in CORRECT_CMD_SUFFIX)

    - If CMD_SUFFIX is not set:
      - /sox3 -> Warning: use /sox
      - /sox -> No warning (standard command)

    Args:
        client: The client instance
        message: The message object containing the command
    """
    # Check if command warnings are enabled
    if not Config.WRONG_CMD_WARNINGS_ENABLED:
        return

    # Check if message has text
    if not message.text:
        return

    # Get the full command text (including any suffix)
    full_command = message.text.split()[0].lower()
    # Extract the base command without the leading slash
    base_command = full_command.lstrip("/")
    # Get the command suffix from config
    cmd_suffix = Config.CMD_SUFFIX

    # Define standard commands (excluding those handled by direct handlers)
    standard_commands = [
        "mirror",
        "m",
        "leech",
        "l",
        "jdmirror",
        "jm",
        "jdleech",
        "jl",
        "nzbmirror",
        "nm",
        "nzbleech",
        "nl",
        "ytdl",
        "y",
        "ytdlleech",
        "yl",
        "gdlmirror",
        "gm",
        "gdlleech",
        "gl",
        "clone",
        "count",
        "del",
        "cancelall",
        "forcestart",
        "fs",
        "list",
        "search",
        "nzbsearch",
        "status",
        "s",
        "statusall",
        "sall",
        "users",
        "auth",
        "unauth",
        "addsudo",
        "rmsudo",
        "ping",
        "restart",
        "restartall",
        "stats",
        "help",
        "log",
        "shell",
        "aexec",
        "exec",
        "clearlocals",
        "botsettings",
        "speedtest",
        "broadcast",
        "broadcastall",
        "sel",
        "rss",
        "check_deletions",
        "cd",
        "imdb",
        "tmdb",
        "login",
        "mediasearch",
        "mds",
        "truecaller",
        "ask",
        "mediainfo",
        "mi",
        "spectrum",
        "sox",
        "paste",
        "qrcode",
        "scrap",
        "shortner",
        "streamripmirror",
        "srmirror",
        "streamripleech",
        "srleech",
        "zotifymirror",
        "zmirror",
        "zotifyleech",
        "zleech",
        "zotifysearch",
        "zsearch",
        "musicmirror",
        "mmirror",
        "mm",
        "musicleech",
        "mleech",
        "ml",
        "streamripsearch",
        "srsearch",
        "srs",
        "virustotal",
        "phishcheck",
        "wot",
        "mediatools",
        "mt",
        "mthelp",
        "mth",
        "fontstyles",
        "fonts",
        "settings",
        "usettings",
        "us",
        "gensession",
        "gs",
        "megasearch",
        "mgs",
        # Encoding/Decoding commands
        "encode",
        "enc",
        "decode",
        "dec",
        # QuickInfo commands
        "quickinfo",
        "qi",
        # File2Link commands
        "file2link",
        "f2l",
        # NSFW Detection commands
        "nsfwstats",
        "nsfwtest",
        # Whisper command
        "whisper",
        # Tool commands
        "tool",
        "t",
        # Forward command
        "forward",
        # Cat API command
        "neko",
        # Trace.moe command
        "trace",
        # OSINT command
        "osint",
        # Contact commands
        "contact",
        "ban",
        "unban",
        # Weather commands
        "weather",
        "w",
    ]

    # Find the base command (without any suffix)
    # Sort commands by length in descending order to match longer commands first
    # This prevents "s" from matching "sox4" before "sox" gets a chance
    sorted_commands = sorted(standard_commands, key=len, reverse=True)

    found_standard_cmd = None
    command_suffix = ""

    for std_cmd in sorted_commands:
        if base_command == std_cmd:
            # Exact match - this is a standard command without suffix
            found_standard_cmd = std_cmd
            command_suffix = ""
            break
        if base_command.startswith(std_cmd) and len(base_command) > len(std_cmd):
            # Command with some suffix
            found_standard_cmd = std_cmd
            command_suffix = base_command[len(std_cmd) :]
            break

    # If no standard command found, ignore (not our concern)
    if not found_standard_cmd:
        return

    # Get the list of correct command suffixes (if any)
    correct_cmd_suffixes = []
    if Config.CORRECT_CMD_SUFFIX:
        correct_cmd_suffixes = [
            suffix.strip() for suffix in Config.CORRECT_CMD_SUFFIX.split(",")
        ]

    # CASE: When CMD_SUFFIX is not set
    if not cmd_suffix:
        # Only show warning if command has a non-standard suffix (like /leech3)
        if command_suffix:  # Command has some suffix when it shouldn't
            warning_msg = f"⚠️ <b>Warning:</b> Please use /{found_standard_cmd} command instead of /{base_command}."
            reply = await send_message(message, warning_msg)
            await auto_delete_message(reply, message, time=300)
        return

    # CASE: When CMD_SUFFIX is set
    # Check if the command already has the correct current suffix
    if command_suffix == cmd_suffix:
        # Command has the current CMD_SUFFIX, no warning needed
        return

    # Check if the command has no suffix and "none" is in correct suffixes
    if not command_suffix and "none" in correct_cmd_suffixes:
        # Command without suffix is allowed, no warning needed
        return

    # Check if the command has a suffix that's in the list of correct suffixes
    if command_suffix and command_suffix in correct_cmd_suffixes:
        # This is an allowed suffix, no warning needed
        return

    # If we reach here, the command needs a warning
    if command_suffix:
        # Command with wrong suffix (like /sox1 when CMD_SUFFIX is 4)
        warning_msg = f"⚠️ <b>Warning:</b> For Bot <b>{cmd_suffix}</b> use /{found_standard_cmd}{cmd_suffix} instead of /{base_command}. Thank you."
    else:
        # Standard command without the required suffix (like /sox when CMD_SUFFIX is 4)
        warning_msg = f"⚠️ <b>Warning:</b> For Bot <b>{cmd_suffix}</b> use /{found_standard_cmd}{cmd_suffix}. Thank you."

    reply = await send_message(message, warning_msg)
    await auto_delete_message(reply, message, time=300)
