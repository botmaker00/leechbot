import contextlib
from asyncio import gather, iscoroutinefunction
from html import escape
from time import time

from psutil import cpu_percent, disk_usage, virtual_memory

from bot import DOWNLOAD_DIR, bot_start_time, status_dict, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.telegram_helper.button_build import ButtonMaker

SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


class MirrorStatus:
    STATUS_UPLOAD = "Upload"
    STATUS_UPLOADING = "Uploading"
    STATUS_DOWNLOAD = "Download"
    STATUS_DOWNLOADING = "Downloading"
    STATUS_CLONE = "Clone"
    STATUS_CLONING = "Cloning"
    STATUS_QUEUEDL = "QueueDl"
    STATUS_QUEUEUP = "QueueUp"
    STATUS_PAUSED = "Pause"
    STATUS_ARCHIVE = "Archive"
    STATUS_EXTRACT = "Extract"
    STATUS_SPLIT = "Split"
    STATUS_CHECK = "CheckUp"
    STATUS_SEED = "Seed"
    STATUS_SAMVID = "SamVid"
    STATUS_CONVERT = "Convert"
    STATUS_FFMPEG = "FFmpeg"
    STATUS_METADATA = "Metadata"
    STATUS_WATERMARK = "Watermark"
    STATUS_ETHUMB = "Embed Thumb"
    STATUS_MERGE = "Merging"
    STATUS_COMPRESS = "Compress"
    STATUS_TRIM = "Trim"
    STATUS_REMOVE = "Remove"
    STATUS_ADD = "Add"
    STATUS_SWAP = "Swap"


STATUSES = {
    "ALL": "All",
    "DL": MirrorStatus.STATUS_DOWNLOAD,
    "DLG": MirrorStatus.STATUS_DOWNLOADING,
    "UP": MirrorStatus.STATUS_UPLOAD,
    "UPG": MirrorStatus.STATUS_UPLOADING,
    "QD": MirrorStatus.STATUS_QUEUEDL,
    "QU": MirrorStatus.STATUS_QUEUEUP,
    "AR": MirrorStatus.STATUS_ARCHIVE,
    "EX": MirrorStatus.STATUS_EXTRACT,
    "SD": MirrorStatus.STATUS_SEED,
    "CL": MirrorStatus.STATUS_CLONE,
    "CLG": MirrorStatus.STATUS_CLONING,
    "CM": MirrorStatus.STATUS_CONVERT,
    "SP": MirrorStatus.STATUS_SPLIT,
    "SV": MirrorStatus.STATUS_SAMVID,
    "FF": MirrorStatus.STATUS_FFMPEG,
    "PA": MirrorStatus.STATUS_PAUSED,
    "CK": MirrorStatus.STATUS_CHECK,
    "CP": MirrorStatus.STATUS_COMPRESS,
    "TR": MirrorStatus.STATUS_TRIM,
    "RM": MirrorStatus.STATUS_REMOVE,
    "MG": MirrorStatus.STATUS_MERGE,
    "MD": MirrorStatus.STATUS_METADATA,
    "WM": MirrorStatus.STATUS_WATERMARK,
    "ET": MirrorStatus.STATUS_ETHUMB,
    "AD": MirrorStatus.STATUS_ADD,
    "SW": MirrorStatus.STATUS_SWAP,
}


async def get_task_by_gid(gid: str):
    async with task_dict_lock:
        for task in task_dict.values():
            if hasattr(task, "seeding"):
                await task.update()
            # Ensure both gid and task.gid() are strings before comparison
            task_gid = str(task.gid())
            gid_str = str(gid)
            if task_gid.startswith(gid_str) or task_gid.endswith(gid_str):
                return task
        return None


async def get_specific_tasks(status, user_id):
    if status == "All":
        if user_id:
            return [
                tk
                for tk in task_dict.values()
                if hasattr(tk, "listener")
                and tk.listener
                and hasattr(tk.listener, "user_id")
                and tk.listener.user_id == user_id
            ]
        return list(task_dict.values())
    tasks_to_check = (
        [
            tk
            for tk in task_dict.values()
            if hasattr(tk, "listener")
            and tk.listener
            and hasattr(tk.listener, "user_id")
            and tk.listener.user_id == user_id
        ]
        if user_id
        else list(task_dict.values())
    )
    coro_tasks = []
    coro_tasks.extend(tk for tk in tasks_to_check if iscoroutinefunction(tk.status))
    coro_statuses = await gather(*[tk.status() for tk in coro_tasks])
    result = []
    coro_index = 0
    for tk in tasks_to_check:
        if tk in coro_tasks:
            st = coro_statuses[coro_index]
            coro_index += 1
        else:
            st = tk.status()
        if (st == status) or (
            status == MirrorStatus.STATUS_DOWNLOAD and st not in STATUSES.values()
        ):
            result.append(tk)
    return result


async def get_all_tasks(req_status: str, user_id):
    async with task_dict_lock:
        return await get_specific_tasks(req_status, user_id)


def get_readable_file_size(size_in_bytes):
    if not size_in_bytes:
        return "0B"

    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1

    return f"{size_in_bytes:.2f}{SIZE_UNITS[index]}"


def get_readable_time(seconds, full_time=False):
    periods = [
        ("millennium", 31536000000),
        ("century", 3153600000),
        ("decade", 315360000),
        ("year", 31536000),
        ("month", 2592000),
        ("week", 604800),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            plural_suffix = "s" if period_value > 1 else ""
            result += f"{int(period_value)} {period_name}{plural_suffix} "
            if not full_time:
                break
    return result.strip()


def time_to_seconds(time_duration):
    try:
        parts = time_duration.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(float, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(float, parts)
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = float(parts[0])
        else:
            return 0
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return 0


def speed_string_to_bytes(size_text):
    size = 0
    if isinstance(size_text, int):
        return size_text
    if isinstance(size_text, float):
        return size_text
    if not isinstance(size_text, str):
        return 0

    size_text = size_text.lower()
    if "k" in size_text:
        size += float(size_text.split("k")[0]) * 1024
    elif "m" in size_text:
        size += float(size_text.split("m")[0]) * 1048576
    elif "g" in size_text:
        size += float(size_text.split("g")[0]) * 1073741824
    elif "t" in size_text:
        size += float(size_text.split("t")[0]) * 1099511627776
    elif "b" in size_text:
        size += float(size_text.split("b")[0])
    return size


def get_progress_bar_string(pct):
    # Handle non-numeric progress values like 'N/A'
    if isinstance(pct, str):
        # Remove percentage sign and whitespace
        pct_clean = pct.strip().strip("%")

        # Check if the cleaned string is 'N/A' or other non-numeric values
        if pct_clean.upper() == "N/A" or pct_clean == "-" or not pct_clean:
            # Return empty progress bar for unknown progress
            return "○" * 10

        try:
            pct = float(pct_clean)
        except ValueError:
            # If conversion fails, return empty progress bar
            return "○" * 10

    # Ensure pct is a number
    if not isinstance(pct, int | float):
        return "○" * 10

    p = min(max(pct, 0), 100)
    c_full = int((p + 5) // 10)
    p_str = "●" * c_full
    p_str += "○" * (10 - c_full)
    return p_str


def source(self):
    return (
        sender_chat.title
        if (sender_chat := self.message.sender_chat)
        else self.message.from_user.username or self.message.from_user.id
    )


async def get_readable_message(sid, is_user, page_no=1, status="All", page_step=1):
    msg = ""
    msg += f"<blockquote><b>{Config.CREDIT}</b></blockquote>\n\n"
    button = None

    tasks = await get_specific_tasks(status, sid if is_user else None)

    STATUS_LIMIT = Config.STATUS_LIMIT
    tasks_no = len(tasks)
    pages = (max(tasks_no, 1) + STATUS_LIMIT - 1) // STATUS_LIMIT
    if page_no > pages:
        page_no = (page_no - 1) % pages + 1
        status_dict[sid]["page_no"] = page_no
    elif page_no < 1:
        page_no = pages - (abs(page_no) % pages)
        status_dict[sid]["page_no"] = page_no
    # Ensure start_position is an integer
    start_position = int((page_no - 1) * STATUS_LIMIT)
    # Ensure STATUS_LIMIT is an integer for slicing
    status_limit = int(STATUS_LIMIT)

    # Track message length to prevent exceeding Telegram's limit
    MAX_MESSAGE_LENGTH = 3800  # Leave some buffer for buttons and footer
    current_length = len(msg)
    tasks_added = 0
    for index, task in enumerate(
        tasks[start_position : status_limit + start_position],
        start=1,
    ):
        # Create task message first to check length
        task_msg = ""

        if status != "All":
            tstatus = status
        elif iscoroutinefunction(task.status):
            tstatus = await task.status()
        else:
            tstatus = task.status()

        # Truncate task name if too long
        task_name = task.name()
        if len(task_name) > 50:
            task_name = task_name[:47] + "..."

        # Check if is_super_chat is a valid boolean attribute
        is_super_chat = (
            task.listener
            and hasattr(task.listener, "is_super_chat")
            and not callable(getattr(task.listener, "is_super_chat", None))
            and task.listener.is_super_chat
        )

        if is_super_chat:
            task_msg += f"<b>{index + start_position}. <a href='{task.listener.message.link}'>{tstatus}</a>: </b>"
        else:
            task_msg += f"<b>{index + start_position}. {tstatus}: </b>"
        task_msg += f"[<code>{escape(task_name)}</code>]"

        # Truncate subname if too long, but avoid showing it twice
        # Don't show subname if it's already being used as the main task name
        if (
            task.listener
            and hasattr(task.listener, "subname")
            and task.listener.subname
        ):
            # Get the original task name (before truncation) for better comparison
            original_task_name = task.name()

            # Check if subname is essentially the same as the task name
            # This handles cases where task name comes from subname due to empty main name
            subname_is_duplicate = (
                task.listener.subname in (original_task_name, task_name)
                or (
                    len(original_task_name) > 50
                    and task.listener.subname.startswith(original_task_name[:47])
                )
                or (
                    len(task.listener.subname) > 50
                    and original_task_name.startswith(task.listener.subname[:47])
                )
                or (
                    len(task_name) > 47
                    and task.listener.subname.startswith(task_name[:44])
                )
            )

            if not subname_is_duplicate:
                subname = task.listener.subname
                if len(subname) > 40:
                    subname = subname[:37] + "..."
                task_msg += f"\n<i>{subname}</i>"
        if task.listener:
            task_msg += f"\nby <b>{source(task.listener)}</b>"
        else:
            task_msg += "\nby <b>Unknown</b>"
        if (
            tstatus not in [MirrorStatus.STATUS_SEED, MirrorStatus.STATUS_QUEUEUP]
            and task.listener
            and task.listener.progress
        ):
            progress = task.progress()
            task_msg += (
                f"\n<blockquote>{get_progress_bar_string(progress)} {progress}"
            )
            if (
                task.listener
                and hasattr(task.listener, "subname")
                and task.listener.subname
            ):
                subsize = f"/{get_readable_file_size(task.listener.subsize)}"
                # Check if files_to_proceed exists and has items
                if (
                    hasattr(task.listener, "files_to_proceed")
                    and task.listener.files_to_proceed
                ):
                    ac = len(task.listener.files_to_proceed)
                    count = f"{task.listener.proceed_count}/{ac}"
                else:
                    # If no files_to_proceed or it's empty, just show the proceed_count
                    count = f"{task.listener.proceed_count}"
            else:
                subsize = ""
                count = ""
            task_msg += f"\n<b>Processed:</b> {task.processed_bytes()}{subsize}"
            if count:
                task_msg += f"\n<b>Count:</b> {count}"
            task_msg += f"\n<b>Size:</b> {task.size()}"
            task_msg += f"\n<b>Speed:</b> {task.speed()}"
            task_msg += f"\n<b>Estimated:</b> {task.eta()}"
            if task.listener and (
                (
                    tstatus == MirrorStatus.STATUS_DOWNLOAD
                    and task.listener.is_torrent
                )
                or task.listener.is_qbit
            ):
                with contextlib.suppress(Exception):
                    task_msg += f"\n<b>Seeders:</b> {task.seeders_num()} | <b>Leechers:</b> {task.leechers_num()}"
        elif tstatus == MirrorStatus.STATUS_SEED:
            task_msg += f"\n<blockquote><b>Size: </b>{task.size()}"
            task_msg += f"\n<b>Speed: </b>{task.seed_speed()}"
            task_msg += f"\n<b>Uploaded: </b>{task.uploaded_bytes()}"
            task_msg += f"\n<b>Ratio: </b>{task.ratio()}"
            task_msg += f" | <b>Time: </b>{task.seeding_time()}"
        else:
            task_msg += f"\n<blockquote><b>Size: </b>{task.size()}"
        task_msg += f"\n<b>Tool:</b> {task.tool}"
        if task.listener and task.listener.message:
            task_msg += f"\n<b>Elapsed: </b>{get_readable_time(time() - task.listener.message.date.timestamp())}</blockquote>"
        else:
            task_msg += "\n<b>Elapsed: </b>Unknown</blockquote>"
        task_gid = str(task.gid())  # Ensure task_gid is a string
        short_gid = task_gid[-8:] if task_gid.startswith("SABnzbd") else task_gid[:8]
        task_msg += f"\n<blockquote>/stop_{short_gid}</blockquote>\n\n"

        # Check if adding this task would exceed message length limit
        if current_length + len(task_msg) > MAX_MESSAGE_LENGTH:
            # If we haven't added any tasks yet, we need to truncate this one
            if tasks_added == 0:
                # Truncate the task message to fit
                available_space = (
                    MAX_MESSAGE_LENGTH - current_length - 100
                )  # Leave some buffer
                if available_space > 200:  # Only add if we have reasonable space
                    task_msg = task_msg[:available_space] + "...</blockquote>\n\n"
                    msg += task_msg
                    tasks_added += 1
            break

        msg += task_msg
        current_length += len(task_msg)
        tasks_added += 1

    # Add note if some tasks were truncated due to message length
    if tasks_added < len(tasks[start_position : status_limit + start_position]):
        remaining_tasks = (
            len(tasks[start_position : status_limit + start_position]) - tasks_added
        )
        msg += (
            f"<i>... and {remaining_tasks} more task(s) (message truncated)</i>\n\n"
        )

    if len(msg) == 0:
        if status == "All":
            return None, None
        msg = f"No Active {status} Tasks!\n\n"
    buttons = ButtonMaker()
    if not is_user:
        buttons.data_button("≈", f"status {sid} ov", position="header")
    if len(tasks) > STATUS_LIMIT:
        msg += f"<b>Page:</b> {page_no}/{pages} | <b>Tasks:</b> {tasks_no} | <b>Step:</b> {page_step}\n"
        buttons.data_button("prev", f"status {sid} pre", position="header")
        buttons.data_button("next", f"status {sid} nex", position="header")
        if tasks_no > 30:
            for i in [1, 2, 4, 6, 8, 10, 15]:
                buttons.data_button(
                    str(i), f"status {sid} ps {i}", position="footer"
                )
    if status != "All" or tasks_no > 20:
        for label, status_value in list(STATUSES.items()):
            if status_value != status:
                buttons.data_button(label, f"status {sid} st {status_value}")

    # Ensure we have at least one button to prevent "No valid buttons to display" warning
    # Check if ButtonMaker has any buttons before building
    has_buttons = (
        len(buttons._button) > 0
        or len(buttons._header_button) > 0
        or len(buttons._footer_button) > 0
        or len(buttons._page_button) > 0
    )

    button = buttons.build_menu(8) if has_buttons else None
    msg += f"<b>CPU:</b> {cpu_percent()}% | <b>FREE:</b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
    msg += f"\n<b>RAM:</b> {virtual_memory().percent}% | <b>UPTIME:</b> {get_readable_time(time() - bot_start_time)}"

    # Add restart time if enabled
    if Config.AUTO_RESTART_ENABLED:
        # Import here to avoid circular imports
        from bot.helper.ext_utils.auto_restart import get_restart_time_remaining

        restart_time = get_restart_time_remaining()
        if restart_time:
            msg += f"\n<b>NEXT RESTART:</b> {restart_time}"

    return msg, button
