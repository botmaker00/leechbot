import contextlib
import gc
import logging
import threading
import time

# Optional imports with fallbacks
try:
    import psutil
except ImportError:
    psutil = None

LOGGER = logging.getLogger(__name__)

# Optimized global state - minimal memory footprint
_last_gc_time = 0.0  # Use 0.0 instead of time.time() for better performance
_gc_interval = 60  # Default interval, will be updated from config


def _is_gc_enabled():
    """Check if garbage collection is enabled via configuration with caching."""
    try:
        from bot.core.config_manager import get_config_bool

        return get_config_bool("GC_ENABLED", True)
    except ImportError:
        # Fallback to enabled if config not available
        return True


def _get_gc_config():
    """Get GC configuration settings with caching."""
    try:
        from bot.core.config_manager import get_config_bool, get_config_int

        return {
            "enabled": get_config_bool("GC_ENABLED", True),
            "interval": get_config_int("GC_INTERVAL", 60),
            "threshold_mb": get_config_int("GC_THRESHOLD_MB", 150),
            "aggressive_mode": get_config_bool("GC_AGGRESSIVE_MODE", False),
        }
    except ImportError:
        # Fallback defaults if config not available
        return {
            "enabled": True,
            "interval": 60,
            "threshold_mb": 150,
            "aggressive_mode": False,
        }


def force_garbage_collection(threshold_mb=None, generation=None):
    """
    Optimized garbage collection with configuration support.

    Args:
        threshold_mb: Memory threshold in MB to trigger collection (uses config if None)
        generation: Specific generation to collect (0, 1, 2, or None for all)

    Returns:
        bool: True if garbage collection was performed, False if disabled or not needed
    """
    global _last_gc_time

    # Get configuration settings
    gc_config = _get_gc_config()

    # Check if GC is completely disabled
    if not gc_config["enabled"]:
        LOGGER.debug("Garbage collection is disabled via configuration")
        return False

    # Use config values if not provided
    if threshold_mb is None:
        threshold_mb = gc_config["threshold_mb"]

    current_time = time.time()
    gc_interval = gc_config["interval"]

    # Quick time-based check first (most common case)
    if current_time - _last_gc_time < gc_interval:
        return False

    # Memory check only if psutil is available
    if psutil is not None:
        try:
            memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
            if memory_mb < threshold_mb:
                return False
        except Exception:
            pass  # Continue with time-based collection

    # Perform collection
    try:
        if generation is not None:
            gc.collect(generation)
        else:
            # Optimized: only collect what's needed
            collected = gc.collect(0)  # Start with youngest
            if (
                collected > 100 or gc_config["aggressive_mode"]
            ):  # Use config for aggressiveness
                gc.collect(1)
                gc.collect(2)

        # Clear garbage list if not empty
        if gc.garbage:
            gc.garbage.clear()

        _last_gc_time = current_time
        return True

    except Exception as e:
        LOGGER.error(f"GC error: {e}")
        return False


# Memory tracking functions removed for optimization
# They added complexity without significant benefit


def log_memory_usage():
    """Get current memory usage information efficiently."""
    if psutil is None:
        return None

    try:
        memory_info = psutil.Process().memory_info()
        system_memory = psutil.virtual_memory()

        return {
            "rss_mb": memory_info.rss / (1024 * 1024),
            "vms_mb": memory_info.vms / (1024 * 1024),
            "system_percent": system_memory.percent,
        }
    except Exception:
        return None


def get_memory_usage():
    """Get current memory usage information efficiently (alias for log_memory_usage)."""
    return log_memory_usage()


def set_gc_parameters(threshold=700, interval=60):
    """
    Configure garbage collection parameters.

    Args:
        threshold: Memory threshold in MB to trigger collection
        interval: Minimum time in seconds between collections
    """
    global _gc_interval

    try:
        # Set Python's GC thresholds
        # These control how many allocations trigger automatic collection
        current_thresholds = gc.get_threshold()

        # Only change if significantly different to avoid unnecessary changes
        if abs(current_thresholds[0] - threshold) > 50:
            gc.set_threshold(threshold, current_thresholds[1], current_thresholds[2])
        # Set our custom interval
        _gc_interval = interval
    except Exception as e:
        LOGGER.error(f"Failed to set garbage collection parameters: {e}")


def optimized_garbage_collection(aggressive=None):
    """Optimized garbage collection with configuration support."""
    # Check if GC is enabled
    if not _is_gc_enabled():
        LOGGER.debug("Garbage collection is disabled via configuration")
        return False

    try:
        # Get configuration
        gc_config = _get_gc_config()

        # Use config aggressive mode if not specified
        if aggressive is None:
            aggressive = gc_config["aggressive_mode"]

        # Smart collection based on generation 0 results
        collected_gen0 = gc.collect(0)

        # Only collect older generations if needed
        if aggressive or collected_gen0 > 1000:
            collected_gen1 = gc.collect(1)
            if aggressive or collected_gen1 > 100:
                gc.collect(2)

        # Clear garbage if present
        if gc.garbage:
            gc.garbage.clear()

        return True
    except Exception as e:
        LOGGER.error(f"GC error: {e}")
        return False


def cleanup_large_objects():
    """Optimized cleanup for critical memory situations."""
    # Allow cleanup even if GC is disabled (emergency situations)
    try:
        # Clear garbage first
        if gc.garbage:
            gc.garbage.clear()

        # Efficient collection sequence
        gc.collect(0)
        gc.collect(1)
        gc.collect(2)

        return True
    except Exception as e:
        LOGGER.error(f"GC cleanup error: {e}")
        with contextlib.suppress(Exception):
            gc.collect()
        return False


def monitor_thread_usage():
    """Monitor thread usage efficiently."""
    try:
        thread_count = threading.active_count()

        # Use simple threshold instead of complex limit calculation
        if thread_count > 100:  # High threshold
            LOGGER.warning(f"High thread usage: {thread_count}")
            return True
        if thread_count > 50:  # Moderate threshold
            return True

        return False
    except Exception:
        return False


def smart_garbage_collection(
    aggressive=False,
    for_split_file=False,
    memory_error=False,
    for_music_download=False,
):
    """Smart garbage collection with configuration support and optimized decision logic."""
    # Check if GC is enabled
    if not _is_gc_enabled():
        LOGGER.debug("Garbage collection is disabled via configuration")
        return False

    try:
        # Get configuration
        gc_config = _get_gc_config()

        # Get memory usage efficiently
        memory_percent = 0
        if psutil is not None:
            with contextlib.suppress(Exception):
                memory_percent = psutil.virtual_memory().percent

        # Check thread usage
        high_thread_usage = monitor_thread_usage()

        # Emergency memory cleanup (always allowed even if GC is configured conservatively)
        if memory_error:
            LOGGER.warning("Emergency memory cleanup - overriding GC configuration")
            if gc.garbage:
                gc.garbage.clear()
            gc.collect(0)
            gc.collect(1)
            gc.collect(2)
            cleanup_large_objects()
            return True

        # Determine aggressiveness (consider config setting)
        should_be_aggressive = (
            aggressive
            or gc_config["aggressive_mode"]
            or for_split_file
            or high_thread_usage
            or (for_music_download and memory_percent > 60)
        )

        # Collection strategy based on memory pressure
        if should_be_aggressive or memory_percent > 90:
            if memory_percent > 95 or for_split_file:
                return cleanup_large_objects()
            return optimized_garbage_collection(aggressive=True)
        if memory_percent > 80:
            return optimized_garbage_collection(aggressive=False)
        if memory_percent > 60:
            gc.collect(0)  # Quick collection of young objects

        return True

    except Exception as e:
        LOGGER.error(f"Smart GC error: {e}")
        try:
            gc.collect()
            return True
        except Exception:
            return False


def music_download_cleanup():
    """Optimized cleanup for music download tasks."""
    # Check if GC is enabled
    if not _is_gc_enabled():
        LOGGER.debug("Garbage collection is disabled via configuration")
        return False

    try:
        if gc.garbage:
            gc.garbage.clear()

        gc.collect(0)
        gc.collect(1)

        # Only collect gen 2 if memory is high
        if psutil is not None:
            try:
                if psutil.virtual_memory().percent > 80:
                    gc.collect(2)
            except Exception:
                pass

        return True
    except Exception:
        return False


def gallery_dl_cleanup():
    """Optimized cleanup for gallery-dl download tasks."""
    # Check if GC is enabled
    if not _is_gc_enabled():
        LOGGER.debug("Garbage collection is disabled via configuration")
        return False

    try:
        if gc.garbage:
            gc.garbage.clear()

        # Gallery-dl can download many files, so be more aggressive with cleanup
        gc.collect(0)
        gc.collect(1)

        # Always collect gen 2 for gallery-dl due to potential large file counts
        if psutil is not None:
            try:
                if (
                    psutil.virtual_memory().percent > 70
                ):  # Lower threshold for gallery-dl
                    gc.collect(2)
            except Exception:
                pass
        else:
            # Fallback if psutil not available
            gc.collect(2)

        return True
    except Exception:
        return False


def get_gc_status():
    """Get current garbage collection configuration and status."""
    gc_config = _get_gc_config()

    status = {
        "enabled": gc_config["enabled"],
        "interval": gc_config["interval"],
        "threshold_mb": gc_config["threshold_mb"],
        "aggressive_mode": gc_config["aggressive_mode"],
        "python_gc_enabled": gc.isenabled(),
        "python_gc_thresholds": gc.get_threshold(),
        "python_gc_counts": gc.get_count(),
    }

    # Add memory info if available
    if psutil is not None:
        try:
            memory_info = psutil.Process().memory_info()
            system_memory = psutil.virtual_memory()
            status.update(
                {
                    "current_memory_mb": memory_info.rss / (1024 * 1024),
                    "system_memory_percent": system_memory.percent,
                }
            )
        except Exception:
            pass

    return status


def log_gc_status():
    """Log current garbage collection status."""
    status = get_gc_status()

    if status["enabled"]:
        LOGGER.info(
            f"🗑️ GC Status: ENABLED | Interval: {status['interval']}s | "
            f"Threshold: {status['threshold_mb']}MB | "
            f"Aggressive: {status['aggressive_mode']}"
        )

        if "current_memory_mb" in status:
            LOGGER.info(
                f"💾 Memory: {status['current_memory_mb']:.1f}MB | "
                f"System: {status['system_memory_percent']:.1f}%"
            )
    else:
        LOGGER.info("🗑️ GC Status: DISABLED via configuration")

    LOGGER.debug(
        f"Python GC: Enabled={status['python_gc_enabled']} | "
        f"Thresholds={status['python_gc_thresholds']} | "
        f"Counts={status['python_gc_counts']}"
    )


# Configuration management functions for runtime updates
def update_gc_config(
    enabled=None, interval=None, threshold_mb=None, aggressive_mode=None
):
    """Update GC configuration at runtime (if supported by config system)."""
    try:
        from bot.core.config_manager import Config

        updated = []
        if enabled is not None:
            Config.GC_ENABLED = enabled
            updated.append(f"enabled={enabled}")
        if interval is not None:
            Config.GC_INTERVAL = interval
            updated.append(f"interval={interval}")
        if threshold_mb is not None:
            Config.GC_THRESHOLD_MB = threshold_mb
            updated.append(f"threshold_mb={threshold_mb}")
        if aggressive_mode is not None:
            Config.GC_AGGRESSIVE_MODE = aggressive_mode
            updated.append(f"aggressive_mode={aggressive_mode}")

        if updated:
            LOGGER.info(f"Updated GC configuration: {', '.join(updated)}")
            return True
        return False

    except ImportError:
        LOGGER.warning(
            "Cannot update GC configuration - config system not available"
        )
        return False


# Removed unused helper functions for optimization
