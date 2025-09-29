import time
from asyncio import Event

from bot import (
    LOGGER,
    non_queued_dl,
    non_queued_up,
    queue_dict_lock,
    queued_dl,
    queued_up,
)
from bot.helper.mirror_leech_utils.gdrive_utils.search import GoogleDriveSearch

from .bot_utils import get_telegraph_list, sync_to_async
from .files_utils import get_base_name
from .links_utils import is_gdrive_id


async def stop_duplicate_check(listener):
    if (
        isinstance(listener.up_dest, int)
        or listener.is_leech
        or listener.select
        or not is_gdrive_id(listener.up_dest)
        or (listener.up_dest.startswith("mtp:") and listener.stop_duplicate)
        or not listener.stop_duplicate
        or listener.same_dir
    ):
        return False, None

    name = listener.name
    LOGGER.info(f"Checking File/Folder if already in Drive: {name}")

    if listener.compress:
        # Check if it's the new compression feature or the old 7z compression
        if hasattr(listener, "compression_enabled") and listener.compression_enabled:
            # For the new compression feature, we keep the original name
            # as the compressed file will maintain its extension
            pass
        else:
            # For the old 7z compression
            name = f"{name}.7z"
    elif listener.extract:
        try:
            name = get_base_name(name)
        except Exception:
            name = None

    if name is not None:
        telegraph_content, contents_no = await sync_to_async(
            GoogleDriveSearch(stop_dup=True, no_multi=listener.is_clone).drive_list,
            name,
            listener.up_dest,
            listener.user_id,
        )
        if telegraph_content:
            msg = f"File/Folder is already available in Drive.\nHere are {contents_no} list results:"
            button = await get_telegraph_list(telegraph_content)
            return msg, button

    return False, None


async def check_running_tasks(listener, state="dl"):
    from bot.core.config_manager import Config

    all_limit = Config.QUEUE_ALL
    state_limit = Config.QUEUE_DOWNLOAD if state == "dl" else Config.QUEUE_UPLOAD
    event = None
    is_over_limit = False

    # Check system resources before allowing new tasks using shared resource manager
    # Only apply resource constraints if task monitoring is enabled
    try:
        from bot.core.config_manager import Config
        from bot.helper.ext_utils.gc_utils import smart_garbage_collection
        from bot.helper.ext_utils.task_monitor import resource_manager

        if Config.TASK_MONITOR_ENABLED:
            should_queue, reason = resource_manager.should_force_queue()

            if should_queue:
                # Get detailed analysis for consolidated logging when resources are extremely critical
                cpu_percent, memory_percent = resource_manager.get_resource_usage()
                if memory_percent > 95 or cpu_percent > 98:
                    detailed_analysis = _get_task_manager_resource_analysis()
                    disk_info = _get_disk_usage_info()
                    LOGGER.warning(
                        f"🚨 EXTREMELY CRITICAL RESOURCES - {disk_info} {reason} Forcing task {listener.mid} to queue. "
                        f"Will start only 1 task to prevent system overload. "
                        f"📊 DETAILS: {detailed_analysis}"
                    )
                else:
                    LOGGER.warning(f"{reason} Forcing task {listener.mid} to queue.")

                # Force garbage collection to try to free up resources
                startup_phase = resource_manager.is_startup_phase()
                smart_garbage_collection(aggressive=not startup_phase)

                # Create event for queuing
                event = Event()
                async with queue_dict_lock:
                    if state == "dl":
                        queued_dl[listener.mid] = event
                    else:
                        queued_up[listener.mid] = event

                return True, event
    except ImportError:
        # If psutil is not available, continue with normal limit checks
        pass

    async with queue_dict_lock:
        if state == "up" and listener.mid in non_queued_dl:
            non_queued_dl.remove(listener.mid)
        if (
            (all_limit or state_limit)
            and not listener.force_run
            and not (listener.force_upload and state == "up")
            and not (listener.force_download and state == "dl")
        ):
            dl_count = len(non_queued_dl)
            up_count = len(non_queued_up)
            t_count = dl_count if state == "dl" else up_count
            is_over_limit = (
                all_limit
                and dl_count + up_count >= all_limit
                and (not state_limit or t_count >= state_limit)
            ) or (state_limit and t_count >= state_limit)
            if is_over_limit:
                event = Event()
                if state == "dl":
                    queued_dl[listener.mid] = event
                else:
                    queued_up[listener.mid] = event
        if not is_over_limit:
            if state == "up":
                non_queued_up.add(listener.mid)
            else:
                non_queued_dl.add(listener.mid)

    return is_over_limit, event


async def start_dl_from_queued(mid: int):
    queued_dl[mid].set()
    del queued_dl[mid]
    non_queued_dl.add(mid)


async def start_up_from_queued(mid: int):
    queued_up[mid].set()
    del queued_up[mid]
    non_queued_up.add(mid)


async def start_from_queued():
    # Check system resources before starting queued tasks using shared resource manager
    # Only apply resource constraints if task monitoring is enabled
    resource_constraint = "normal"  # Default to normal if monitoring disabled

    try:
        from bot.core.config_manager import Config
        from bot.helper.ext_utils.gc_utils import smart_garbage_collection
        from bot.helper.ext_utils.task_monitor import (
            ResourceConstraint,
            resource_manager,
        )

        if Config.TASK_MONITOR_ENABLED:
            resource_constraint = resource_manager.get_constraint_level()
            cpu_percent, memory_percent = resource_manager.get_resource_usage()

            if resource_constraint == ResourceConstraint.CRITICAL:
                # Only log here if we haven't already logged in check_running_tasks
                # This prevents duplicate logging when both functions detect critical resources

                # Force garbage collection to try to free up resources
                smart_garbage_collection(aggressive=True)
            elif resource_constraint == ResourceConstraint.MODERATE:
                LOGGER.info(
                    f"System resources moderately high: Memory {memory_percent:.1f}%, CPU {cpu_percent:.1f}%. "
                    f"Will start at most 2 tasks."
                )
        else:
            # Task monitoring disabled - use normal resource constraint
            resource_constraint = "normal"
    except ImportError:
        # If psutil is not available, assume no resource constraints
        resource_constraint = "normal"  # Use string fallback

    if all_limit := Config.QUEUE_ALL:
        dl_limit = Config.QUEUE_DOWNLOAD
        up_limit = Config.QUEUE_UPLOAD
        async with queue_dict_lock:
            dl = len(non_queued_dl)
            up = len(non_queued_up)
            all_ = dl + up
            if all_ < all_limit:
                f_tasks = all_limit - all_

                # Apply resource constraints using shared resource manager
                # Only apply if task monitoring is enabled
                if Config.TASK_MONITOR_ENABLED:
                    try:
                        from bot.helper.ext_utils.task_monitor import (
                            ResourceConstraint,
                        )

                        max_tasks = resource_manager.get_max_tasks(
                            resource_constraint
                        )
                        if max_tasks != float("inf"):
                            f_tasks = min(f_tasks, max_tasks)
                    except ImportError:
                        # Fallback to old logic if import fails
                        if resource_constraint == ResourceConstraint.CRITICAL:
                            f_tasks = min(f_tasks, 1)
                        elif resource_constraint == ResourceConstraint.MODERATE:
                            f_tasks = min(f_tasks, 2)

                if queued_up and (not up_limit or up < up_limit):
                    for index, mid in enumerate(list(queued_up.keys()), start=1):
                        await start_up_from_queued(mid)
                        f_tasks -= 1
                        if f_tasks == 0 or (up_limit and index >= up_limit - up):
                            break
                if queued_dl and (not dl_limit or dl < dl_limit) and f_tasks != 0:
                    for index, mid in enumerate(list(queued_dl.keys()), start=1):
                        await start_dl_from_queued(mid)
                        if (dl_limit and index >= dl_limit - dl) or index == f_tasks:
                            break
        return

    # Handle individual queue limits with resource constraints
    if up_limit := Config.QUEUE_UPLOAD:
        async with queue_dict_lock:
            up = len(non_queued_up)
            if queued_up and up < up_limit:
                f_tasks = up_limit - up

                # Apply resource constraints using shared resource manager
                # Only apply if task monitoring is enabled
                if Config.TASK_MONITOR_ENABLED:
                    try:
                        from bot.helper.ext_utils.task_monitor import (
                            ResourceConstraint,
                        )

                        max_tasks = resource_manager.get_max_tasks(
                            resource_constraint
                        )
                        if max_tasks != float("inf"):
                            f_tasks = min(f_tasks, max_tasks)
                    except ImportError:
                        # Fallback to old logic if import fails
                        if resource_constraint == ResourceConstraint.CRITICAL:
                            f_tasks = min(f_tasks, 1)
                        elif resource_constraint == ResourceConstraint.MODERATE:
                            f_tasks = min(f_tasks, 2)

                for index, mid in enumerate(list(queued_up.keys()), start=1):
                    await start_up_from_queued(mid)
                    if index == f_tasks:
                        break
    else:
        async with queue_dict_lock:
            if queued_up:
                # Even without upload limits, respect resource constraints if task monitoring is enabled
                if Config.TASK_MONITOR_ENABLED:
                    try:
                        from bot.helper.ext_utils.task_monitor import (
                            ResourceConstraint,
                        )

                        max_tasks = resource_manager.get_max_tasks(
                            resource_constraint
                        )

                        if max_tasks == 1:
                            # Start only 1 upload task under critical conditions
                            mid = next(iter(queued_up.keys()))
                            await start_up_from_queued(mid)
                        elif max_tasks == 2:
                            # Start at most 2 upload tasks under moderate conditions
                            for index, mid in enumerate(
                                list(queued_up.keys()), start=1
                            ):
                                await start_up_from_queued(mid)
                                if index >= 2:
                                    break
                        else:
                            # No resource constraints, start all queued uploads
                            for mid in list(queued_up.keys()):
                                await start_up_from_queued(mid)
                    except ImportError:
                        # Fallback to old logic if import fails
                        if resource_constraint == ResourceConstraint.CRITICAL:
                            mid = next(iter(queued_up.keys()))
                            await start_up_from_queued(mid)
                        elif resource_constraint == ResourceConstraint.MODERATE:
                            for index, mid in enumerate(
                                list(queued_up.keys()), start=1
                            ):
                                await start_up_from_queued(mid)
                                if index >= 2:
                                    break
                        else:
                            for mid in list(queued_up.keys()):
                                await start_up_from_queued(mid)
                else:
                    # Task monitoring disabled - start all queued uploads without resource constraints
                    for mid in list(queued_up.keys()):
                        await start_up_from_queued(mid)

    if dl_limit := Config.QUEUE_DOWNLOAD:
        async with queue_dict_lock:
            dl = len(non_queued_dl)
            if queued_dl and dl < dl_limit:
                f_tasks = dl_limit - dl

                # Apply resource constraints using shared resource manager
                # Only apply if task monitoring is enabled
                if Config.TASK_MONITOR_ENABLED:
                    try:
                        from bot.helper.ext_utils.task_monitor import (
                            ResourceConstraint,
                        )

                        max_tasks = resource_manager.get_max_tasks(
                            resource_constraint
                        )
                        if max_tasks != float("inf"):
                            f_tasks = min(f_tasks, max_tasks)
                    except ImportError:
                        # Fallback to old logic if import fails
                        if resource_constraint == ResourceConstraint.CRITICAL:
                            f_tasks = min(f_tasks, 1)
                        elif resource_constraint == ResourceConstraint.MODERATE:
                            f_tasks = min(f_tasks, 2)

                for index, mid in enumerate(list(queued_dl.keys()), start=1):
                    await start_dl_from_queued(mid)
                    if index == f_tasks:
                        break
    else:
        async with queue_dict_lock:
            if queued_dl:
                # Even without download limits, respect resource constraints if task monitoring is enabled
                if Config.TASK_MONITOR_ENABLED:
                    try:
                        from bot.helper.ext_utils.task_monitor import (
                            ResourceConstraint,
                        )

                        max_tasks = resource_manager.get_max_tasks(
                            resource_constraint
                        )

                        if max_tasks == 1:
                            # Start only 1 download task under critical conditions
                            mid = next(iter(queued_dl.keys()))
                            await start_dl_from_queued(mid)
                        elif max_tasks == 2:
                            # Start at most 2 download tasks under moderate conditions
                            for index, mid in enumerate(
                                list(queued_dl.keys()), start=1
                            ):
                                await start_dl_from_queued(mid)
                                if index >= 2:
                                    break
                        else:
                            # No resource constraints, start all queued downloads
                            for mid in list(queued_dl.keys()):
                                await start_dl_from_queued(mid)
                    except ImportError:
                        # Fallback to old logic if import fails
                        if resource_constraint == ResourceConstraint.CRITICAL:
                            mid = next(iter(queued_dl.keys()))
                            await start_dl_from_queued(mid)
                        elif resource_constraint == ResourceConstraint.MODERATE:
                            for index, mid in enumerate(
                                list(queued_dl.keys()), start=1
                            ):
                                await start_dl_from_queued(mid)
                                if index >= 2:
                                    break
                        else:
                            for mid in list(queued_dl.keys()):
                                await start_dl_from_queued(mid)
                else:
                    # Task monitoring disabled - start all queued downloads without resource constraints
                    for mid in list(queued_dl.keys()):
                        await start_dl_from_queued(mid)


async def start_queue_processor():
    """
    Optimized queue processor with minimal resource usage.
    Only runs when task monitoring is enabled.
    """
    import asyncio

    from bot import LOGGER
    from bot.core.config_manager import Config

    LOGGER.info("Starting optimized queue processor")

    # Cache imports to avoid repeated imports
    resource_manager = None
    ResourceLevel = None

    if Config.TASK_MONITOR_ENABLED:
        try:
            from bot.helper.ext_utils.task_monitor import (
                ResourceLevel,
                resource_manager,
            )
        except ImportError:
            LOGGER.warning(
                "Task monitor not available, using basic queue processing"
            )

    while True:
        # Exit if task monitoring is disabled
        if not Config.TASK_MONITOR_ENABLED:
            LOGGER.info("Task monitoring disabled - stopping queue processor")
            break

        try:
            # Quick check for queued tasks - O(1)
            has_queued = bool(queued_dl or queued_up)
            if not has_queued:
                await asyncio.sleep(60)  # No queued tasks, sleep longer
                continue

            # Count running tasks - O(1)
            running_count = len(non_queued_dl) + len(non_queued_up)
            should_start = False
            reason = ""

            if Config.TASK_MONITOR_ENABLED and resource_manager:
                # Use resource-aware logic
                level = resource_manager.get_constraint_level()

                if running_count == 0:
                    should_start = True
                    reason = "No tasks running"
                elif level == ResourceLevel.CRITICAL and running_count < 1:
                    should_start = True
                    reason = "Critical resources - ensuring minimum 1 task"
                elif level == ResourceLevel.MODERATE and running_count < 2:
                    should_start = True
                    reason = "Moderate resources - allowing up to 2 tasks"
                elif level == ResourceLevel.NORMAL:
                    should_start = True
                    reason = "Normal resources - processing queue"
            # Fallback: start if no tasks running
            elif running_count == 0:
                should_start = True
                reason = "No tasks running (basic mode)"

            if should_start:
                LOGGER.info(f"Queue processor: {reason}")
                await start_from_queued()

                # Minimal garbage collection only when needed
                if Config.TASK_MONITOR_ENABLED and resource_manager:
                    level = resource_manager.get_constraint_level()
                    if level == ResourceLevel.CRITICAL:
                        from bot.helper.ext_utils.gc_utils import (
                            smart_garbage_collection,
                        )

                        smart_garbage_collection(aggressive=True)

            # Optimized adaptive sleep intervals to reduce CPU usage
            if running_count == 0 and has_queued:
                sleep_time = 30  # Increased from 15 to 30 for urgent cases
            elif has_queued:
                sleep_time = 60  # Increased from 45 to 60 for normal cases
            else:
                sleep_time = 120  # Increased from 60 to 120 for idle cases

            await asyncio.sleep(sleep_time)

        except Exception as e:
            LOGGER.error(f"Queue processor error: {e}")
            await asyncio.sleep(60)


def _get_task_manager_resource_analysis() -> str:
    """Get detailed resource analysis specific to task manager operations"""
    try:
        import threading

        import psutil

        from bot import non_queued_dl, non_queued_up, queued_dl, queued_up, task_dict

        analysis_parts = []

        # Add system resource overview first
        try:
            # System-wide resource info
            cpu_count = psutil.cpu_count(logical=True)
            cpu_count_physical = psutil.cpu_count(logical=False)
            cpu_freq = psutil.cpu_freq()

            analysis_parts.append(
                f"🖥️  SYSTEM: {cpu_count} logical cores ({cpu_count_physical} physical)"
            )
            if cpu_freq:
                analysis_parts.append(f"CPU Freq: {cpu_freq.current:.0f}MHz")

            # Memory details
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            analysis_parts.append(
                f"Memory: {memory.used / 1024**3:.1f}GB/{memory.total / 1024**3:.1f}GB ({memory.percent:.1f}%)"
            )
            analysis_parts.append(
                f"Available: {memory.available / 1024**3:.1f}GB, Swap: {swap.used / 1024**3:.1f}GB/{swap.total / 1024**3:.1f}GB ({swap.percent:.1f}%)"
            )

            # System load
            try:
                if hasattr(psutil, "getloadavg"):
                    load_avg = psutil.getloadavg()
                    if load_avg and len(load_avg) >= 3:
                        analysis_parts.append(
                            f"Load avg: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}"
                        )
            except Exception:
                pass

            # System uptime
            try:
                boot_time = psutil.boot_time()
                uptime_seconds = time.time() - boot_time
                uptime_hours = uptime_seconds / 3600
                analysis_parts.append(f"Uptime: {uptime_hours:.1f}h")
            except Exception:
                pass

        except Exception:
            analysis_parts.append("System info unavailable")

        # Task queue analysis
        async def get_task_counts():
            async with queue_dict_lock:
                return {
                    "queued_dl": len(queued_dl),
                    "queued_up": len(queued_up),
                    "running_dl": len(non_queued_dl),
                    "running_up": len(non_queued_up),
                    "total_tasks": len(task_dict),
                }

        # Since this is called from sync context, we'll get basic counts
        try:
            analysis_parts.append(
                f"Tasks - Running DL: {len(non_queued_dl)}, Running UP: {len(non_queued_up)}"
            )
            analysis_parts.append(
                f"Queued DL: {len(queued_dl)}, Queued UP: {len(queued_up)}, Total: {len(task_dict)}"
            )
        except Exception:
            analysis_parts.append("Task count analysis failed")

        # Thread analysis
        thread_count = threading.active_count()
        analysis_parts.append(f"Active threads: {thread_count}")

        # Process analysis
        current_process = psutil.Process()

        # CPU times
        cpu_times = current_process.cpu_times()
        analysis_parts.append(
            f"CPU times - User: {cpu_times.user:.1f}s, System: {cpu_times.system:.1f}s"
        )

        # Memory details
        memory_info = current_process.memory_info()
        memory_full_info = current_process.memory_full_info()
        analysis_parts.append(
            f"Memory - RSS: {memory_info.rss / 1024**2:.1f}MB, VMS: {memory_info.vms / 1024**2:.1f}MB"
        )
        analysis_parts.append(
            f"Memory - USS: {memory_full_info.uss / 1024**2:.1f}MB, PSS: {memory_full_info.pss / 1024**2:.1f}MB"
        )

        # File descriptors
        try:
            num_fds = current_process.num_fds()
            analysis_parts.append(f"File descriptors: {num_fds}")
        except Exception:
            pass

        # Connections
        try:
            connections = current_process.connections()
            tcp_count = sum(
                1 for conn in connections if conn.type.name == "SOCK_STREAM"
            )
            udp_count = sum(
                1 for conn in connections if conn.type.name == "SOCK_DGRAM"
            )
            analysis_parts.append(
                f"Network connections - TCP: {tcp_count}, UDP: {udp_count}"
            )
        except Exception:
            pass

        # Enhanced child processes analysis
        try:
            children = current_process.children(recursive=True)
            if children:
                analysis_parts.append(f"Child processes: {len(children)}")

                # Collect detailed child process info with robust error handling
                child_details = []
                for child in children:
                    try:
                        # Get basic info first
                        child_pid = child.pid
                        child_name = "unknown"
                        child_cmdline = "unknown"
                        child_memory_mb = 0
                        child_cpu = 0
                        child_status = "unknown"
                        child_age = 0

                        # Try to get each piece of info individually with error handling
                        try:
                            child_name = child.name()
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                            psutil.ZombieProcess,
                        ):
                            child_name = "access_denied"
                        except Exception:
                            child_name = "error_name"

                        try:
                            child_memory = child.memory_info()
                            child_memory_mb = child_memory.rss / 1024**2
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                            psutil.ZombieProcess,
                        ):
                            child_memory_mb = 0
                        except Exception:
                            child_memory_mb = 0

                        try:
                            child_cpu = child.cpu_percent()
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                            psutil.ZombieProcess,
                        ):
                            child_cpu = 0
                        except Exception:
                            child_cpu = 0

                        try:
                            cmdline_list = child.cmdline()
                            if cmdline_list:
                                child_cmdline = " ".join(cmdline_list[:3])
                            else:
                                child_cmdline = "no_cmdline"
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                            psutil.ZombieProcess,
                        ):
                            child_cmdline = "access_denied"
                        except Exception:
                            child_cmdline = "error_cmdline"

                        try:
                            child_status = child.status()
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                            psutil.ZombieProcess,
                        ):
                            child_status = "access_denied"
                        except Exception:
                            child_status = "error_status"

                        try:
                            child_create_time = child.create_time()
                            child_age = time.time() - child_create_time
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                            psutil.ZombieProcess,
                        ):
                            child_age = 0
                        except Exception:
                            child_age = 0

                        child_details.append(
                            {
                                "pid": child_pid,
                                "name": child_name,
                                "cmdline": child_cmdline,
                                "memory_mb": child_memory_mb,
                                "cpu_percent": child_cpu,
                                "status": child_status,
                                "age_seconds": child_age,
                            }
                        )

                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                        psutil.ZombieProcess,
                    ):
                        # Process no longer exists or access denied
                        child_details.append(
                            {
                                "pid": getattr(child, "pid", "unknown"),
                                "name": "process_gone",
                                "cmdline": "process_no_longer_exists",
                                "memory_mb": 0,
                                "cpu_percent": 0,
                                "status": "gone",
                                "age_seconds": 0,
                            }
                        )
                    except Exception as e:
                        # Other unexpected errors
                        child_details.append(
                            {
                                "pid": getattr(child, "pid", "unknown"),
                                "name": "error",
                                "cmdline": f"unexpected_error: {str(e)[:20]}",
                                "memory_mb": 0,
                                "cpu_percent": 0,
                                "status": "error",
                                "age_seconds": 0,
                            }
                        )

                # Sort by CPU usage first, then memory
                child_details.sort(
                    key=lambda x: (x["cpu_percent"], x["memory_mb"]), reverse=True
                )

                # Show detailed info for all children
                for i, child in enumerate(child_details, 1):
                    analysis_parts.append(
                        f"  Child {i}: PID {child['pid']} | {child['name']} | "
                        f"CMD: {child['cmdline'][:50]} | "
                        f"MEM: {child['memory_mb']:.1f}MB | "
                        f"CPU: {child['cpu_percent']:.1f}% | "
                        f"STATUS: {child['status']} | "
                        f"AGE: {child['age_seconds']:.0f}s"
                    )
        except Exception as e:
            analysis_parts.append(f"Child process analysis failed: {e!s}")

        return " | ".join(analysis_parts)

    except Exception as e:
        return f"Task manager analysis failed: {e}"


def _get_disk_usage_info() -> str:
    """Get disk usage information for consolidated logging"""
    try:
        import shutil

        from bot import DOWNLOAD_DIR
        from bot.helper.ext_utils.status_utils import get_readable_file_size

        # Get disk usage statistics
        usage = shutil.disk_usage(DOWNLOAD_DIR)
        free = usage.free
        total = usage.total
        used_percent = (usage.used / total) * 100

        # Calculate storage threshold (20GB default)
        threshold = 20 * 1024 * 1024 * 1024  # 20GB in bytes

        return (
            f"💾 DISK: {used_percent:.1f}% used, {get_readable_file_size(free)} free, "
            f"threshold {get_readable_file_size(threshold)} |"
        )
    except Exception as e:
        return f"💾 DISK: analysis failed ({str(e)[:20]}) |"
