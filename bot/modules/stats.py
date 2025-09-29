from asyncio import create_task, gather
from re import search as research
from time import time

from psutil import (
    boot_time,
    cpu_count,
    cpu_percent,
    disk_usage,
    net_io_counters,
    swap_memory,
    virtual_memory,
)

from bot import bot_start_time
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath
from bot.helper.ext_utils.bot_utils import cmd_exec, new_task
from bot.helper.ext_utils.status_utils import (
    get_readable_file_size,
    get_readable_time,
)
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    send_message,
)

commands = {
    "aria2": (["xria", "--version"], r"aria2 version ([\d.]+)"),
    "qBittorrent": (["xnox", "--version"], r"qBittorrent v([\d.]+)"),
    "SABnzbd+": (["xnzb", "--version"], r"xnzb-([\d.]+)"),
    "python": (["python3", "--version"], r"Python ([\d.]+)"),
    "rclone": (["xone", "--version"], r"rclone v([\d.]+)"),
    "yt-dlp": (["yt-dlp", "--version"], r"([\d.]+)"),
    "xtra": (["xtra", "-version"], r"ffmpeg version ([\d.\w-]+)"),
    "7z": (["7z", "i"], r"7-Zip ([\d.]+)"),
    "mega": (
        [
            "python3",
            "-c",
            "try:\n    import mega\n    api = mega.MegaApi('test')\n    print(f'v{api.getVersion()}')\nexcept ImportError as e:\n    print(f'ImportError: {e}')\nexcept Exception as e:\n    print(f'Error: {e}')",
        ],
        r"([\d.\w-]+|ImportError.*|Error.*)",
    ),
    "streamrip": (
        ["python3", "-c", "import streamrip; print(streamrip.__version__)"],
        r"([\d.\w-]+)",
    ),
    "gallery-dl": (
        ["python3", "-c", "import gallery_dl; print(gallery_dl.__version__)"],
        r"([\d.\w-]+)",
    ),
    "zotify": (
        [
            "python3",
            "-c",
            "import importlib.metadata; print(importlib.metadata.version('zotify'))",
        ],
        r"([\d.\w-]+)",
    ),
}


@new_task
async def bot_stats(_, message):
    total, used, free, disk = disk_usage("/")
    swap = swap_memory()
    memory = virtual_memory()

    # Function to format limit values
    def format_limit(limit_value, unit="GB"):
        if limit_value == 0:
            return "∞ (Unlimited)"
        if unit == "GB":
            return f"{limit_value} GB"
        return str(limit_value)

    # System stats section
    system_stats = f"""
<b>Commit Date:</b> {commands["commit"]}

<b>Bot Uptime:</b> {get_readable_time(time() - bot_start_time)}
<b>OS Uptime:</b> {get_readable_time(time() - boot_time())}

<b>Total Disk Space:</b> {get_readable_file_size(total)}
<b>Used:</b> {get_readable_file_size(used)} | <b>Free:</b> {get_readable_file_size(free)}

<b>Upload:</b> {get_readable_file_size(net_io_counters().bytes_sent)}
<b>Download:</b> {get_readable_file_size(net_io_counters().bytes_recv)}

<b>CPU:</b> {cpu_percent(interval=0.5)}%
<b>RAM:</b> {memory.percent}%
<b>DISK:</b> {disk}%

<b>Physical Cores:</b> {cpu_count(logical=False)}
<b>Total Cores:</b> {cpu_count()}
<b>SWAP:</b> {get_readable_file_size(swap.total)} | <b>Used:</b> {swap.percent}%

<b>Memory Total:</b> {get_readable_file_size(memory.total)}
<b>Memory Free:</b> {get_readable_file_size(memory.available)}
<b>Memory Used:</b> {get_readable_file_size(memory.used)}
"""

    # Limits stats section
    limits_stats = f"""
<b>📊 LIMITS STATS 📊</b>

<b>Storage Threshold:</b> {format_limit(Config.STORAGE_THRESHOLD)}
<b>Torrent Limit:</b> {format_limit(Config.TORRENT_LIMIT)}
<b>Direct Link Limit:</b> {format_limit(Config.DIRECT_LIMIT)}
<b>YouTube Limit:</b> {format_limit(Config.YTDLP_LIMIT)}
<b>Google Drive Limit:</b> {format_limit(Config.GDRIVE_LIMIT)}
<b>Clone Limit:</b> {format_limit(Config.CLONE_LIMIT)}
<b>Mega Limit:</b> {format_limit(Config.MEGA_LIMIT)}
<b>Leech Limit:</b> {format_limit(Config.LEECH_LIMIT)}
<b>JDownloader Limit:</b> {format_limit(Config.JD_LIMIT)}
<b>NZB Limit:</b> {format_limit(Config.NZB_LIMIT)}

<b>Gallery-dl Limit:</b> {format_limit(Config.GALLERY_DL_LIMIT)}
<b>Zotify Limit:</b> {format_limit(Config.ZOTIFY_LIMIT)}
<b>Playlist Limit:</b> {format_limit(Config.PLAYLIST_LIMIT, unit="videos")}

<b>Daily Task Limit:</b> {format_limit(Config.DAILY_TASK_LIMIT, unit="tasks")}
<b>Daily Mirror Limit:</b> {format_limit(Config.DAILY_MIRROR_LIMIT)}
<b>Daily Leech Limit:</b> {format_limit(Config.DAILY_LEECH_LIMIT)}
<b>User Max Tasks:</b> {format_limit(Config.USER_MAX_TASKS, unit="tasks")}
<b>Bot Max Tasks:</b> {format_limit(Config.BOT_MAX_TASKS, unit="tasks")}
<b>User Time Interval:</b> {format_limit(Config.USER_TIME_INTERVAL, unit="seconds")}
"""

    # MEGA account information section removed - only keeping SDK version and limit

    # Versions section
    versions_stats = f"""
<b>python:</b> {commands["python"]}
<b>aria2:</b> {commands["aria2"]}
<b>qBittorrent:</b> {commands["qBittorrent"]}
<b>SABnzbd+:</b> {commands["SABnzbd+"]}
<b>rclone:</b> {commands["rclone"]}
<b>yt-dlp:</b> {commands["yt-dlp"]}
<b>mega:</b> {commands["mega"]}
<b>streamrip:</b> {commands["streamrip"]}
<b>gallery-dl:</b> {commands["gallery-dl"]}
<b>zotify:</b> {commands["zotify"]}
<b>xtra:</b> {commands["xtra"]}
<b>7z:</b> {commands["7z"]}
"""

    # Combine all sections
    stats = system_stats + limits_stats + versions_stats

    # Delete the /stats command message immediately
    await delete_links(message)

    # Send stats message and create auto-delete task
    stats_msg = await send_message(message, stats)
    create_task(auto_delete_message(stats_msg, time=300))  # noqa: RUF006


async def get_version_async(command, regex):
    try:
        out, err, code = await cmd_exec(command)
        if code != 0:
            return f"Error: {err}"
        match = research(regex, out)
        return match.group(1) if match else "Version not found"
    except Exception as e:
        return f"Exception: {e!s}"


@new_task
async def get_packages_version():
    tasks = [
        get_version_async(command, regex) for command, regex in commands.values()
    ]
    versions = await gather(*tasks)
    commands.update(dict(zip(commands.keys(), versions, strict=False)))
    if await aiopath.exists(".git"):
        last_commit = await cmd_exec(
            "git log -1 --date=short --pretty=format:'%cd <b>From</b> %cr'",
            True,
        )
        last_commit = last_commit[0]
    else:
        last_commit = "No UPSTREAM_REPO"
    commands["commit"] = last_commit
