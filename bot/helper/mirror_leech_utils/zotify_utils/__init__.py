"""
Zotify utilities package for aimleechbot
"""

from .search_handler import (
    ZotifySearchHandler,
    decrypt_zotify_data,
    encrypt_zotify_data,
    handle_zotify_callback,
    init_zotify_inline_search,
    inline_zotify_search,
    perform_inline_zotify_search,
    search_music,
    search_music_auto_first,
    zotify_search,
)
from .special_downloads import (
    ZotifySelection,
    ZotifySpecialDownloads,
    create_selection_interface,
    get_special_download_info,
    get_special_download_type,
    get_special_download_urls,
    is_special_download,
    zotify_special,
)
from .url_parser import (
    ZotifyUrlParser,
    is_file_input,
    is_zotify_url,
    parse_file_content,
    parse_zotify_url,
)
from .zotify_config import (
    ZotifyConfigManager,
    get_zotify_config,
    has_zotify_credentials,
    is_zotify_enabled,
    zotify_config,
)

__all__ = [
    # Config Manager
    "ZotifyConfigManager",
    # Search Handler
    "ZotifySearchHandler",
    "ZotifySelection",
    # Special Downloads
    "ZotifySpecialDownloads",
    # URL Parser
    "ZotifyUrlParser",
    "create_selection_interface",
    "decrypt_zotify_data",
    "encrypt_zotify_data",
    "get_special_download_info",
    "get_special_download_type",
    "get_special_download_urls",
    "get_zotify_config",
    "handle_zotify_callback",
    "has_zotify_credentials",
    "init_zotify_inline_search",
    # Inline search functions
    "inline_zotify_search",
    "is_file_input",
    "is_special_download",
    "is_zotify_enabled",
    "is_zotify_url",
    "parse_file_content",
    "parse_zotify_url",
    "perform_inline_zotify_search",
    "search_music",
    "search_music_auto_first",
    "zotify_config",
    "zotify_search",
    "zotify_special",
]
