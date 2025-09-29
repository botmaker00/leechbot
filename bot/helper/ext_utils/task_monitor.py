"""
Optimized Task Monitor with Minimal Time and Space Complexity
Maintains all existing features while reducing resource usage
"""

import asyncio
import time
from collections import deque
from enum import Enum
from functools import lru_cache
from typing import Final

try:
    import psutil
except ImportError:
    import pip

    pip.main(["install", "psutil"])
    import psutil

from bot import (
    LOGGER,
    non_queued_dl,
    non_queued_up,
    queued_dl,
    queued_up,
    task_dict,
    task_dict_lock,
)
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import sync_to_async
from bot.helper.ext_utils.status_utils import MirrorStatus
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)

# Constants for O(1) access
STARTUP_DURATION: Final[int] = 300  # 5 minutes
CACHE_TTL: Final[float] = 2.0  # 2 seconds
GB_BYTES: Final[int] = 1024**3

# Pre-compiled status sets for O(1) membership testing
CPU_INTENSIVE: Final[frozenset] = frozenset(
    [
        MirrorStatus.STATUS_FFMPEG,
        MirrorStatus.STATUS_CONVERT,
        MirrorStatus.STATUS_COMPRESS,
        MirrorStatus.STATUS_ARCHIVE,
        MirrorStatus.STATUS_EXTRACT,
        MirrorStatus.STATUS_SWAP,
    ]
)

MEMORY_INTENSIVE: Final[frozenset] = frozenset(
    [MirrorStatus.STATUS_DOWNLOAD, MirrorStatus.STATUS_UPLOAD]
)

MONITORED_STATUSES: Final[frozenset] = frozenset(
    [
        MirrorStatus.STATUS_DOWNLOAD,
        MirrorStatus.STATUS_QUEUEDL,
        MirrorStatus.STATUS_UPLOAD,
        MirrorStatus.STATUS_QUEUEUP,
    ]
)


class ResourceLevel(Enum):
    """Resource constraint levels"""

    NORMAL = 0
    MODERATE = 1
    CRITICAL = 2


class OptimizedResourceManager:
    """Lightweight resource manager with minimal overhead"""

    __slots__ = (
        "_cached_cpu",
        "_cached_level",
        "_cached_memory",
        "_last_check",
        "_startup_time",
    )

    def __init__(self):
        self._startup_time = time.time()
        self._last_check = 0.0
        self._cached_cpu = 0.0
        self._cached_memory = 0.0
        self._cached_level = ResourceLevel.NORMAL

    def get_resource_usage(self) -> tuple[float, float]:
        """Get CPU and memory usage with caching"""
        now = time.time()
        if now - self._last_check < CACHE_TTL:
            return self._cached_cpu, self._cached_memory

        try:
            self._cached_cpu = psutil.cpu_percent(interval=None)
            self._cached_memory = psutil.virtual_memory().percent
            self._last_check = now
        except Exception:
            pass  # Keep cached values

        return self._cached_cpu, self._cached_memory

    def get_constraint_level(self) -> ResourceLevel:
        """Get current resource constraint level"""
        cpu, memory = self.get_resource_usage()
        startup = (time.time() - self._startup_time) < STARTUP_DURATION

        # Startup thresholds (more lenient)
        if startup:
            if memory > 95 or cpu > 98:
                return ResourceLevel.CRITICAL
            if memory > 85 or cpu > 90:
                return ResourceLevel.MODERATE
        # Normal thresholds
        elif memory > 85 or cpu > 90:
            return ResourceLevel.CRITICAL
        elif memory > 75 or cpu > 80:
            return ResourceLevel.MODERATE

        return ResourceLevel.NORMAL

    def should_force_queue(self) -> tuple[bool, str]:
        """Check if new tasks should be queued due to critical resources"""
        cpu, memory = self.get_resource_usage()
        startup = (time.time() - self._startup_time) < STARTUP_DURATION

        if startup:
            should_queue = memory > 95 or cpu > 98
        else:
            should_queue = memory > 90 or cpu > 95

        if should_queue:
            return True, f"Critical resources: CPU {cpu:.1f}%, Memory {memory:.1f}%"
        return False, ""

    def get_max_tasks(self, level: ResourceLevel) -> int:
        """Get max tasks for constraint level"""
        if level == ResourceLevel.CRITICAL:
            return 1
        if level == ResourceLevel.MODERATE:
            return 2
        return float("inf")

    # Compatibility methods for existing code
    def should_force_queue_task(self) -> tuple[bool, str]:
        """Compatibility method - same as should_force_queue"""
        return self.should_force_queue()

    def get_resource_constraint(self) -> ResourceLevel:
        """Compatibility method - same as get_constraint_level"""
        return self.get_constraint_level()

    def get_max_tasks_for_constraint(self, constraint: ResourceLevel) -> int:
        """Compatibility method - same as get_max_tasks"""
        return self.get_max_tasks(constraint)

    def is_startup_phase(self) -> bool:
        """Check if system is in startup phase"""
        return (time.time() - self._startup_time) < STARTUP_DURATION


# Global instances
resource_manager = OptimizedResourceManager()

# Minimal data structures
queued_by_monitor: set[int] = set()
cpu_intensive_tasks: set[int] = set()
memory_intensive_tasks: set[int] = set()

# Lightweight history tracking
_max_history = min(
    Config.TASK_MONITOR_CONSECUTIVE_CHECKS, 10
)  # Cap at 10 for efficiency
cpu_history: deque[float] = deque(maxlen=_max_history)
memory_history: deque[float] = deque(maxlen=_max_history)
task_speeds: dict[str, deque[int]] = {}  # Only create when needed
task_warnings: dict[str, dict] = {}  # Only create when needed


# Cached configuration getters
@lru_cache(maxsize=1)
def get_check_interval() -> int:
    return Config.TASK_MONITOR_INTERVAL


@lru_cache(maxsize=1)
def get_speed_threshold() -> int:
    return Config.TASK_MONITOR_SPEED_THRESHOLD * 1024


@lru_cache(maxsize=1)
def get_consecutive_checks() -> int:
    return Config.TASK_MONITOR_CONSECUTIVE_CHECKS


@lru_cache(maxsize=1)
def get_elapsed_threshold() -> int:
    return Config.TASK_MONITOR_ELAPSED_THRESHOLD


@lru_cache(maxsize=1)
def get_eta_threshold() -> int:
    return Config.TASK_MONITOR_ETA_THRESHOLD


@lru_cache(maxsize=1)
def get_wait_time() -> int:
    return Config.TASK_MONITOR_WAIT_TIME


@lru_cache(maxsize=1)
def get_cpu_high() -> int:
    return Config.TASK_MONITOR_CPU_HIGH


@lru_cache(maxsize=1)
def get_cpu_low() -> int:
    return Config.TASK_MONITOR_CPU_LOW


@lru_cache(maxsize=1)
def get_memory_high() -> int:
    return Config.TASK_MONITOR_MEMORY_HIGH


@lru_cache(maxsize=1)
def get_memory_low() -> int:
    return Config.TASK_MONITOR_MEMORY_LOW


async def is_task_in_global_queue(mid: int) -> bool:
    """Check if task is in global queue - O(1)"""
    return mid in queued_dl or mid in queued_up


async def get_task_speed(task) -> int:
    """Get task speed efficiently"""
    try:
        if hasattr(task, "speed") and callable(task.speed):
            speed_func = task.speed
            if asyncio.iscoroutinefunction(speed_func):
                return await speed_func()
            return speed_func()
    except Exception:
        pass
    return 0


async def get_task_elapsed_time(task) -> int:
    """Get task elapsed time efficiently"""
    try:
        if hasattr(task, "listener") and hasattr(task.listener, "start_time"):
            return int(time.time() - task.listener.start_time)
    except Exception:
        pass
    return 0


def classify_task_type(status: str) -> str | None:
    """Classify task type - O(1)"""
    if status in CPU_INTENSIVE:
        return "cpu"
    if status in MEMORY_INTENSIVE:
        return "memory"
    return None


async def should_queue_task(task_type: str) -> tuple[bool, str]:
    """Check if task should be queued based on resource history"""
    if task_type == "cpu" and len(cpu_history) >= get_consecutive_checks():
        if all(usage >= get_cpu_high() for usage in cpu_history):
            return True, f"High CPU usage ({cpu_history[-1]:.1f}%)"

    if task_type == "memory" and len(memory_history) >= get_consecutive_checks():
        if all(usage >= get_memory_high() for usage in memory_history):
            return True, f"High memory usage ({memory_history[-1]:.1f}%)"

    return False, ""


async def can_resume_tasks() -> tuple[bool, str]:
    """Check if tasks can be resumed"""
    if len(cpu_history) >= get_consecutive_checks():
        if all(usage <= get_cpu_low() for usage in cpu_history):
            return True, "cpu"

    if len(memory_history) >= get_consecutive_checks():
        if all(usage <= get_memory_low() for usage in memory_history):
            return True, "memory"

    return False, ""


async def identify_intensive_tasks():
    """Identify resource-intensive tasks - O(n) where n is active tasks"""
    cpu_intensive_tasks.clear()
    memory_intensive_tasks.clear()

    async with task_dict_lock:
        for mid, task in task_dict.items():
            if mid in queued_by_monitor:
                continue

            try:
                if not hasattr(task, "listener") or not hasattr(task, "status"):
                    continue

                if (
                    hasattr(task.listener, "is_cancelled")
                    and task.listener.is_cancelled
                ):
                    continue

                status_method = task.status
                if not callable(status_method):
                    continue

                status = (
                    await status_method()
                    if asyncio.iscoroutinefunction(status_method)
                    else status_method()
                )
                task_type = classify_task_type(status)

                if task_type == "cpu":
                    cpu_intensive_tasks.add(mid)
                elif task_type == "memory":
                    memory_intensive_tasks.add(mid)

            except Exception:
                continue


async def queue_task(mid: int, reason: str):
    """Queue a task due to resource constraints"""
    try:
        async with task_dict_lock:
            if mid not in task_dict:
                return

            task = task_dict[mid]

            # Get listener from different sources depending on task type
            listener = None
            if hasattr(task, "listener"):
                listener = task.listener
            elif hasattr(task, "message"):
                # For status classes that don't have listener but have message
                # We'll create a minimal listener-like object for compatibility
                class MinimalListener:
                    def __init__(self, message):
                        self.message = message
                        self.mid = message.id
                        self.is_cancelled = False
                        self.name = (
                            getattr(task, "name", lambda: "Unknown Task")()
                            if callable(getattr(task, "name", None))
                            else "Unknown Task"
                        )
                        self.user_id = (
                            message.from_user.id
                            if hasattr(message, "from_user") and message.from_user
                            else None
                        )

                listener = MinimalListener(task.message)

            if not listener:
                return

            # Check if task is cancelled
            is_cancelled = False
            if (hasattr(listener, "is_cancelled") and listener.is_cancelled) or (
                hasattr(listener, "isCancelled") and listener.isCancelled
            ):
                is_cancelled = True

            if is_cancelled:
                return

            # Mark as queued by monitor
            queued_by_monitor.add(mid)

            # Check if already in global queue
            if await is_task_in_global_queue(mid):
                queued_by_monitor.discard(mid)
                return

            # Move to appropriate queue
            if mid in non_queued_dl:
                non_queued_dl.remove(mid)
                queued_dl[mid] = asyncio.Event()
                LOGGER.info(f"Queued download task {listener.name} due to {reason}")
            elif mid in non_queued_up:
                non_queued_up.remove(mid)
                queued_up[mid] = asyncio.Event()
                LOGGER.info(f"Queued upload task {listener.name} due to {reason}")
            else:
                queued_by_monitor.discard(mid)
                return

            # Send notification
            if hasattr(listener, "message"):
                # Get user tag safely
                user_tag = ""
                if hasattr(listener, "user_id") and listener.user_id:
                    user_tag = f"<a href='tg://user?id={listener.user_id}'>{listener.user_id}</a>"
                elif (
                    hasattr(listener, "user")
                    and hasattr(listener.user, "username")
                    and listener.user.username
                ):
                    user_tag = f"@{listener.user.username}"
                elif hasattr(listener, "user") and hasattr(listener.user, "id"):
                    user_tag = f"<a href='tg://user?id={listener.user.id}'>{listener.user.id}</a>"

                # Get task name safely
                task_name = getattr(listener, "name", "Unknown Task")
                if callable(task_name):
                    try:
                        task_name = task_name()
                    except Exception:
                        task_name = "Unknown Task"

                queue_msg = await send_message(
                    listener.message,
                    f"⚠️ <b>Task Queued</b> ⚠️\n\n"
                    f"<b>Name:</b> <code>{task_name}</code>\n"
                    f"<b>Reason:</b> {reason}\n\n"
                    f"Task will resume automatically when resources are available.\n\n{user_tag}",
                )

                if not isinstance(queue_msg, str):
                    asyncio.create_task(auto_delete_message(queue_msg, time=300))

    except Exception as e:
        LOGGER.error(f"Error queuing task {mid}: {e}")


async def resume_queued_tasks(resource_type: str):
    """Resume tasks queued by monitor"""
    try:
        if not queued_by_monitor:
            return

        tasks_to_resume = []
        target_tasks = (
            cpu_intensive_tasks if resource_type == "cpu" else memory_intensive_tasks
        )

        for mid in target_tasks:
            if mid in queued_by_monitor:
                tasks_to_resume.append(mid)

        if not tasks_to_resume:
            return

        # Check available slots
        async with task_dict_lock:
            dl_slots = (
                max(0, Config.QUEUE_DOWNLOAD - len(non_queued_dl))
                if Config.QUEUE_DOWNLOAD
                else float("inf")
            )
            up_slots = (
                max(0, Config.QUEUE_UPLOAD - len(non_queued_up))
                if Config.QUEUE_UPLOAD
                else float("inf")
            )
            all_slots = (
                max(0, Config.QUEUE_ALL - len(non_queued_dl) - len(non_queued_up))
                if Config.QUEUE_ALL
                else float("inf")
            )

            resumed = 0
            for mid in tasks_to_resume:
                if resumed >= all_slots:
                    break

                if mid in queued_dl and dl_slots > 0:
                    queued_dl[mid].set()
                    del queued_dl[mid]
                    non_queued_dl.add(mid)
                    queued_by_monitor.discard(mid)
                    dl_slots -= 1
                    resumed += 1
                    LOGGER.info(f"Resumed download task {mid}")
                elif mid in queued_up and up_slots > 0:
                    queued_up[mid].set()
                    del queued_up[mid]
                    non_queued_up.add(mid)
                    queued_by_monitor.discard(mid)
                    up_slots -= 1
                    resumed += 1
                    LOGGER.info(f"Resumed upload task {mid}")

    except Exception as e:
        LOGGER.error(f"Error resuming tasks: {e}")


async def is_task_slow(task, gid: str) -> bool:
    """Check if task is consistently slow - optimized"""
    try:
        speed = await get_task_speed(task)

        # Only track speeds for slow tasks to save memory
        if speed < get_speed_threshold():
            if gid not in task_speeds:
                task_speeds[gid] = deque(maxlen=get_consecutive_checks())
            task_speeds[gid].append(speed)

            # Check if consistently slow
            if len(task_speeds[gid]) >= get_consecutive_checks():
                return all(s < get_speed_threshold() for s in task_speeds[gid])
        else:
            # Remove from tracking if speed improves
            task_speeds.pop(gid, None)

        return False
    except Exception:
        return False


async def should_cancel_task(task, gid: str) -> tuple[bool, str]:
    """Determine if task should be cancelled - lightweight version"""
    try:
        if not hasattr(task, "status"):
            return False, ""

        # Check if task is cancelled (handle different listener types)
        is_cancelled = False
        if hasattr(task, "listener") and (
            (hasattr(task.listener, "is_cancelled") and task.listener.is_cancelled)
            or (hasattr(task.listener, "isCancelled") and task.listener.isCancelled)
        ):
            is_cancelled = True

        if is_cancelled:
            return False, ""

        status_method = task.status
        if not callable(status_method):
            return False, ""

        status = (
            await status_method()
            if asyncio.iscoroutinefunction(status_method)
            else status_method()
        )

        if status not in MONITORED_STATUSES:
            return False, ""

        elapsed_time = await get_task_elapsed_time(task)

        # Quick checks for obvious cancellation cases
        if elapsed_time > get_eta_threshold():
            return True, f"Task running too long ({elapsed_time // 3600}h)"

        # Check if consistently slow
        if await is_task_slow(task, gid):
            return True, "Consistently slow speed"

        return False, ""

    except Exception:
        return False, ""


async def cancel_task(task, gid: str, reason: str):
    """Cancel a task efficiently"""
    try:
        # Get listener from different sources depending on task type
        listener = None
        if hasattr(task, "listener"):
            listener = task.listener
        elif hasattr(task, "message"):
            # For status classes that don't have listener but have message
            class MinimalListener:
                def __init__(self, message):
                    self.message = message
                    self.name = (
                        getattr(task, "name", lambda: "Unknown Task")()
                        if callable(getattr(task, "name", None))
                        else "Unknown Task"
                    )
                    self.user_id = (
                        message.from_user.id
                        if hasattr(message, "from_user") and message.from_user
                        else None
                    )

            listener = MinimalListener(task.message)

        # Send cancellation message
        if listener and hasattr(listener, "message"):
            # Get user tag safely
            user_tag = ""
            if hasattr(listener, "user_id") and listener.user_id:
                user_tag = f"<a href='tg://user?id={listener.user_id}'>{listener.user_id}</a>"
            elif (
                hasattr(listener, "user")
                and hasattr(listener.user, "username")
                and listener.user.username
            ):
                user_tag = f"@{listener.user.username}"
            elif hasattr(listener, "user") and hasattr(listener.user, "id"):
                user_tag = f"<a href='tg://user?id={listener.user.id}'>{listener.user.id}</a>"

            # Get task name safely
            task_name = getattr(listener, "name", "Unknown Task")
            if callable(task_name):
                try:
                    task_name = task_name()
                except Exception:
                    task_name = "Unknown Task"

            cancel_msg = await send_message(
                listener.message,
                f"❌ <b>Task Cancelled</b> ❌\n\n"
                f"<b>Name:</b> <code>{task_name}</code>\n"
                f"<b>Reason:</b> {reason}\n\n{user_tag}",
            )

            if not isinstance(cancel_msg, str):
                asyncio.create_task(auto_delete_message(cancel_msg, time=300))

        # Cancel the task
        if hasattr(task, "cancel_task") and callable(task.cancel_task):
            if asyncio.iscoroutinefunction(task.cancel_task):
                await task.cancel_task()
            else:
                await sync_to_async(task.cancel_task)

        # Cleanup
        task_speeds.pop(gid, None)
        task_warnings.pop(gid, None)

    except Exception as e:
        LOGGER.error(f"Error cancelling task {gid}: {e}")


async def monitor_tasks():
    """Main monitoring function - optimized for minimal overhead"""
    try:
        # Update resource history
        cpu, memory = resource_manager.get_resource_usage()
        cpu_history.append(cpu)
        memory_history.append(memory)

        # Optimized periodic logging (every 20 minutes to reduce log spam)
        if int(time.time()) % 1200 < get_check_interval():
            LOGGER.info(
                f"Monitor: {len(task_dict)} tasks, {len(queued_by_monitor)} queued by monitor"
            )

        # Cleanup old tracking data
        active_gids = set(task_dict.keys())
        for gid in list(task_speeds.keys()):
            if gid not in active_gids:
                del task_speeds[gid]
        for gid in list(task_warnings.keys()):
            if gid not in active_gids:
                del task_warnings[gid]

        # Identify intensive tasks
        await identify_intensive_tasks()

        # Check for task resumption
        can_resume, resource_type = await can_resume_tasks()
        if can_resume and queued_by_monitor:
            await resume_queued_tasks(resource_type)

        # Monitor active tasks for queuing/cancellation
        async with task_dict_lock:
            tasks_to_check = list(task_dict.items())

        for gid, task in tasks_to_check:
            try:
                # Get task ID (mid) from different sources depending on task type
                mid = None

                if hasattr(task, "listener") and hasattr(task.listener, "mid"):
                    mid = task.listener.mid
                elif hasattr(task, "listener") and hasattr(task.listener, "uid"):
                    # Some listeners use uid instead of mid
                    mid = task.listener.uid
                elif hasattr(task, "message") and hasattr(task.message, "id"):
                    # For status classes that store message directly (like DDLStatus)
                    mid = task.message.id
                elif hasattr(task, "gid") and callable(task.gid):
                    # Try to extract mid from gid if it's available
                    try:
                        task_gid = task.gid()
                        # Some gids might be the mid directly or contain it
                        if (
                            isinstance(task_gid, int | str)
                            and str(task_gid).isdigit()
                        ):
                            mid = int(task_gid)
                    except Exception:
                        pass

                # If we couldn't get a valid mid, skip this task
                if mid is None:
                    continue

                # Skip already queued tasks
                if mid in queued_by_monitor or await is_task_in_global_queue(mid):
                    continue

                # Skip cancelled tasks (check different possible cancellation attributes)
                is_cancelled = False
                if hasattr(task, "listener") and (
                    (
                        hasattr(task.listener, "is_cancelled")
                        and task.listener.is_cancelled
                    )
                    or (
                        hasattr(task.listener, "isCancelled")
                        and task.listener.isCancelled
                    )
                ):
                    is_cancelled = True

                if is_cancelled:
                    continue

                # Check for cancellation
                should_cancel, cancel_reason = await should_cancel_task(task, gid)
                if should_cancel:
                    await cancel_task(task, gid, cancel_reason)
                    continue

                # Check for queuing due to resources
                if mid in cpu_intensive_tasks:
                    should_queue, queue_reason = await should_queue_task("cpu")
                    if should_queue:
                        async with task_dict_lock:
                            if gid in task_dict:  # Verify still exists
                                await queue_task(mid, queue_reason)
                elif mid in memory_intensive_tasks:
                    should_queue, queue_reason = await should_queue_task("memory")
                    if should_queue:
                        async with task_dict_lock:
                            if gid in task_dict:  # Verify still exists
                                await queue_task(mid, queue_reason)

            except Exception as e:
                LOGGER.error(f"Error monitoring task {gid}: {e}")

    except Exception as e:
        LOGGER.error(f"Error in monitor_tasks: {e}")


async def start_monitoring():
    """Start the optimized monitoring loop"""
    if not Config.TASK_MONITOR_ENABLED:
        LOGGER.info("Task monitoring is disabled")
        return

    LOGGER.info("Starting optimized task monitoring system")

    # Startup phase tracking
    startup_cycles = 0
    max_startup_cycles = 5  # Reduced from 10

    while True:
        if not Config.TASK_MONITOR_ENABLED:
            LOGGER.info("Task monitoring disabled - stopping monitor")
            break

        try:
            # Use longer intervals during startup for better resource efficiency
            if startup_cycles < max_startup_cycles:
                interval = (
                    get_check_interval() * 3
                )  # Increased from 2x to 3x for better startup performance
                startup_cycles += 1
                if startup_cycles == max_startup_cycles:
                    LOGGER.info("Task monitoring startup completed")
            else:
                # Optimized adaptive interval based on system load
                level = resource_manager.get_constraint_level()
                if level == ResourceLevel.CRITICAL:
                    interval = int(
                        get_check_interval() * 0.75
                    )  # Less frequent than before to reduce overhead
                elif level == ResourceLevel.MODERATE:
                    interval = (
                        get_check_interval()
                    )  # Normal interval for moderate load
                else:
                    interval = int(
                        get_check_interval() * 1.5
                    )  # Longer interval for normal conditions

            await monitor_tasks()
            await asyncio.sleep(interval)

        except Exception as e:
            LOGGER.error(f"Error in monitoring loop: {e}")
            await asyncio.sleep(get_check_interval())


# Compatibility exports for existing code
class ResourceConstraint:
    """Compatibility class for backward compatibility with old ResourceConstraint enum"""

    NORMAL = ResourceLevel.NORMAL
    MODERATE = ResourceLevel.MODERATE
    CRITICAL = ResourceLevel.CRITICAL
