"""
Link generation utilities
"""

import os
from urllib.parse import quote

from pyrogram.types import Message

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.status_utils import get_readable_file_size

from .file_processor import get_fname, get_fsize, get_hash, is_streamable_file


def get_base_url() -> str:
    """Get base URL for streaming"""
    try:
        # Use BASE_URL if configured, otherwise fall back to localhost
        if Config.BASE_URL:
            return Config.BASE_URL.rstrip("/")
        # Fallback for development
        port = f":{Config.BASE_URL_PORT}" if Config.BASE_URL_PORT != 80 else ""
        return f"http://localhost{port}"
    except Exception as e:
        LOGGER.error(f"Error getting base URL: {e}")
        return "http://localhost:8080"