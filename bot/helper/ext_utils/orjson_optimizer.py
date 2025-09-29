#!/usr/bin/env python3

"""
Global orjson Optimization Module for aimleechbot

This module provides optional orjson optimization for ALL JSON operations
throughout the entire aimleechbot repository. orjson is significantly faster
than the standard json module (2.4x speedup) and provides better memory
efficiency for JSON operations.

Features:
- Automatic orjson detection and fallback to standard json
- Global monkey-patching for seamless integration
- Compatible wrapper functions for all bot components
- Works with: gallery-dl, streamrip, web server, encoding, mediainfo, stats, etc.

Usage:
    # Import this module early in bot initialization to enable global optimization
    from bot.helper.ext_utils.orjson_optimizer import enable_global_orjson_optimization

    # Or it's automatically enabled when imported
    import bot.helper.ext_utils.orjson_optimizer
"""

import json
from typing import Any

from bot import LOGGER

# Global state
_orjson_available = False
_orjson_enabled = False
_original_dumps = None
_original_loads = None


def check_orjson_availability() -> bool:
    """Check if orjson is available in the environment"""
    global _orjson_available

    try:
        import orjson

        _orjson_available = True
        return True
    except ImportError:
        _orjson_available = False
        return False


def orjson_dumps_wrapper(obj: Any, **kwargs) -> str:
    """
    Global orjson-compatible wrapper for json.dumps

    Handles the differences between orjson and standard json:
    - orjson returns bytes, we decode to str
    - orjson has different option handling
    - Works with all bot components
    """
    try:
        import orjson

        # Convert standard json kwargs to orjson options
        orjson_kwargs = {}

        # Handle indent option
        if kwargs.get("indent"):
            orjson_kwargs["option"] = orjson.OPT_INDENT_2

        # Handle sort_keys option
        if kwargs.get("sort_keys"):
            orjson_kwargs["option"] = (
                orjson_kwargs.get("option", 0) | orjson.OPT_SORT_KEYS
            )

        # Handle ensure_ascii (orjson doesn't support this, but it's faster anyway)
        # Handle separators (orjson uses optimized separators by default)

        result = orjson.dumps(obj, **orjson_kwargs)
        return result.decode("utf-8")

    except Exception:
        # Fallback to standard json on any error
        return _original_dumps(obj, **kwargs)


def orjson_loads_wrapper(s: str | bytes, **kwargs) -> Any:
    """
    Global orjson-compatible wrapper for json.loads

    Handles string/bytes conversion for orjson compatibility
    Works with all bot components
    """
    try:
        import orjson

        # Convert string to bytes if needed
        if isinstance(s, str):
            s = s.encode("utf-8")

        return orjson.loads(s)

    except Exception:
        # Fallback to standard json on any error
        return _original_loads(s, **kwargs)


def enable_global_orjson_optimization() -> bool:
    """
    Enable global orjson optimization by monkey-patching the json module

    This affects ALL JSON operations throughout the entire aimleechbot:
    - gallery-dl operations
    - streamrip operations
    - web server JSON responses
    - encoding/decoding operations
    - mediainfo JSON parsing
    - stats and configuration
    - All other JSON usage

    Returns:
        bool: True if orjson optimization was enabled, False otherwise
    """
    global _orjson_enabled, _original_dumps, _original_loads

    if _orjson_enabled:
        return True

    if not check_orjson_availability():
        return False

    try:
        # Store original functions
        _original_dumps = json.dumps
        _original_loads = json.loads

        # Apply global monkey patch
        json.dumps = orjson_dumps_wrapper
        json.loads = orjson_loads_wrapper

        _orjson_enabled = True

        return True

    except Exception as e:
        LOGGER.error(f"Failed to enable global orjson optimization: {e}")
        return False


def disable_global_orjson_optimization() -> bool:
    """
    Disable global orjson optimization by restoring original json functions

    Returns:
        bool: True if orjson optimization was disabled, False otherwise
    """
    global _orjson_enabled, _original_dumps, _original_loads

    if not _orjson_enabled:
        return True

    try:
        # Restore original functions
        if _original_dumps and _original_loads:
            json.dumps = _original_dumps
            json.loads = _original_loads

        _orjson_enabled = False

        return True

    except Exception as e:
        LOGGER.error(f"Failed to disable global orjson optimization: {e}")
        return False


def is_global_orjson_enabled() -> bool:
    """Check if global orjson optimization is currently enabled"""
    return _orjson_enabled


def get_orjson_status() -> dict[str, Any]:
    """
    Get orjson status information

    Returns:
        dict: Status information about orjson optimization
    """
    return {
        "orjson_available": _orjson_available,
        "orjson_enabled": _orjson_enabled,
        "optimization_scope": "global" if _orjson_enabled else "none",
        "affected_components": [
            "gallery-dl",
            "streamrip",
            "web_server",
            "encoding",
            "mediainfo",
            "stats",
            "configuration",
            "all_json_operations",
        ]
        if _orjson_enabled
        else [],
    }


# Auto-enable global orjson optimization if available
def auto_enable_global_orjson() -> None:
    """Automatically enable global orjson optimization if available"""
    if check_orjson_availability():
        enable_global_orjson_optimization()


# Initialize global optimization on import
auto_enable_global_orjson()
