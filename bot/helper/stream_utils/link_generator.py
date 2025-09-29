"""
Link generation utilities for File2Link functionality
Integrates with configuration system
"""

import os
import re
from urllib.parse import quote

from pyrogram.types import Message

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.status_utils import get_readable_file_size

from .file_processor import get_fname, get_fsize, get_hash, is_streamable_file


def get_base_url() -> str:
    """Get base URL for File2Link streaming"""
    try:
        # Use FILE2LINK_BASE_URL if configured, otherwise fall back to BASE_URL
        if Config.FILE2LINK_BASE_URL:
            return Config.FILE2LINK_BASE_URL.rstrip("/")
        if Config.BASE_URL:
            return Config.BASE_URL.rstrip("/")
        # Fallback for development
        port = f":{Config.BASE_URL_PORT}" if Config.BASE_URL_PORT != 80 else ""
        return f"http://localhost{port}"
    except Exception as e:
        LOGGER.error(f"Error getting base URL: {e}")
        return "http://localhost:8080"


def get_file2link_base_url() -> str:
    """Get File2Link base URL with Heroku-style auto-detection"""
    try:
        # Check if FILE2LINK_BASE_URL is explicitly set
        if Config.FILE2LINK_BASE_URL:
            return Config.FILE2LINK_BASE_URL.rstrip("/")

        # Auto-detect for Heroku deployment
        heroku_app_name = os.getenv("HEROKU_APP_NAME")
        if heroku_app_name:
            return f"https://{heroku_app_name}.herokuapp.com"

        # Check for Railway deployment
        railway_static_url = os.getenv("RAILWAY_STATIC_URL")
        if railway_static_url:
            return railway_static_url.rstrip("/")

        # Check for Render deployment
        render_external_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_external_url:
            return render_external_url.rstrip("/")

        # Fall back to main BASE_URL
        if Config.BASE_URL:
            return Config.BASE_URL.rstrip("/")

        # Final fallback for development
        port = f":{Config.BASE_URL_PORT}" if Config.BASE_URL_PORT != 80 else ""
        return f"http://localhost{port}"

    except Exception as e:
        LOGGER.error(f"Error getting File2Link base URL: {e}")
        return "http://localhost:8080"


async def generate_stream_links(
    message: Message, shortener: bool = False
) -> dict[str, str]:
    """
    Generate streaming and download links for a file message

    Args:
        message: Telegram message containing media
        shortener: Whether to use URL shortening (disabled as per requirements)

    Returns:
        Dictionary containing stream_link (if streamable), online_link, media_name, media_size
    """
    try:
        base_url = get_file2link_base_url()
        fid = message.id
        m_name = get_fname(message)
        m_size_hr = get_readable_file_size(get_fsize(message))
        enc_fname = quote(m_name)
        f_hash = get_hash(message)

        # Generate download link (always available) - uses /download/ endpoint for actual downloading
        download_link = f"{base_url}/download/{f_hash}{fid}/{enc_fname}"

        # Generate stream link only if file is streamable - uses /stream/ endpoint for streaming
        stream_link = None
        if is_streamable_file(message):
            stream_link = f"{base_url}/watch/{f_hash}{fid}/{enc_fname}"

        result = {
            "online_link": download_link,
            "media_name": m_name,
            "media_size": m_size_hr,
            "file_hash": f_hash,
            "message_id": fid,
            "is_streamable": stream_link is not None,
        }

        # Only include stream_link if file is streamable
        if stream_link:
            result["stream_link"] = stream_link

        return result

    except Exception as e:
        LOGGER.error(f"Error generating stream links: {e}")
        return {
            "stream_link": "",
            "online_link": "",
            "media_name": "Unknown File",
            "media_size": "0 B",
            "file_hash": "",
            "message_id": 0,
        }


def generate_batch_links(messages: list, shortener: bool = False) -> list:
    """
    Generate links for multiple files

    Args:
        messages: List of Telegram messages containing media
        shortener: Whether to use URL shortening (disabled)

    Returns:
        List of link dictionaries
    """
    try:
        links_list = []
        for message in messages:
            if message and hasattr(message, "media") and message.media:
                links = generate_stream_links(message, shortener)
                if links and links.get(
                    "online_link"
                ):  # Only add if link generation was successful
                    links_list.append(links)

        return links_list

    except Exception as e:
        LOGGER.error(f"Error generating batch links: {e}")
        return []


def format_link_message(links: dict[str, str], chat_title: str | None = None) -> str:
    """
    Format link message for sending to user

    Args:
        links: Dictionary containing link information
        chat_title: Optional chat title for context

    Returns:
        Formatted message string
    """
    try:
        message_parts = []

        # Header with decorative elements
        message_parts.extend(
            [
                "╭─────────────────────────╮",
                "│    🎬 <b>File2Link Ready</b>    │",
                "╰─────────────────────────╯",
                "",
            ]
        )

        # Source information
        if chat_title:
            message_parts.extend(
                [f"📂 <b>Source:</b> <code>{chat_title}</code>", ""]
            )

        # File information with better formatting
        message_parts.extend(
            [
                "📋 <b>File Information:</b>",
                f"┣ 📄 <b>Name:</b> <code>{links['media_name']}</code>",
                f"┗ 📊 <b>Size:</b> <code>{links['media_size']}</code>",
                "",
            ]
        )

        # Available links section
        message_parts.append("🔗 <b>Available Links:</b>")

        # Add stream link only if file is streamable
        if links.get("stream_link"):
            message_parts.append(
                f'┣ 🎬 <b>Stream:</b> <a href="{links["stream_link"]}">▶️ Watch Online</a>'
            )
            message_parts.append(
                f'┗ ⬇️ <b>Download:</b> <a href="{links["online_link"]}">📥 Direct Download</a>'
            )
        else:
            message_parts.append(
                f'┗ ⬇️ <b>Download:</b> <a href="{links["online_link"]}">📥 Direct Download</a>'
            )

        message_parts.extend(
            ["", "─────────────────────────", "💡 <b>Quick Tips:</b>"]
        )

        # Add appropriate tips based on streamability
        if links.get("stream_link"):
            message_parts.extend(
                [
                    "• Stream link works in any browser",
                    "• Download link for offline viewing",
                    "• Copy links to external players",
                    "• Share with friends easily",
                ]
            )
        else:
            message_parts.extend(
                [
                    "• Download link for offline access",
                    "• File not streamable in browser",
                    "• Use appropriate app to open file",
                    "• Share download link with friends",
                ]
            )

        message_parts.extend(["", "✨ <b>Powered by File2Link</b> ✨"])

        return "\n".join(message_parts)

    except Exception as e:
        LOGGER.error(f"Error formatting link message: {e}")
        return f"❌ Error formatting message: {e}"


def format_batch_message(
    links_list: list, processed: int, total: int, failed: int = 0
) -> str:
    """
    Format batch processing message

    Args:
        links_list: List of generated links
        processed: Number of files processed
        total: Total number of files
        failed: Number of failed files

    Returns:
        Formatted batch message string
    """
    try:
        # Calculate success rate
        success_rate = (processed / total * 100) if total > 0 else 0

        message_parts = [
            "╭─────────────────────────╮",
            "│   📦 <b>Batch Processing</b>   │",
            "╰─────────────────────────╯",
            "",
            "📊 <b>Processing Summary:</b>",
            f"┣ ✅ <b>Successful:</b> {processed}/{total} ({success_rate:.1f}%)",
        ]

        if failed > 0:
            message_parts.append(f"┣ ❌ <b>Failed:</b> {failed}")

        message_parts.extend(
            [
                f"┗ 🎯 <b>Status:</b> {'Complete' if processed + failed == total else 'In Progress'}",
                "",
                "─────────────────────────",
                "🔗 <b>Generated Links:</b>",
                "",
            ]
        )

        # Show files with better formatting
        for i, links in enumerate(
            links_list[:8], 1
        ):  # Limit to first 8 files for better readability
            file_name = links["media_name"]
            # Truncate long filenames
            if len(file_name) > 35:
                file_name = file_name[:32] + "..."

            # Create link line based on streamability
            if links.get("stream_link"):
                link_line = f'   🎬 <a href="{links["stream_link"]}">Stream</a> • 📥 <a href="{links["online_link"]}">Download</a>'
            else:
                link_line = f'   📥 <a href="{links["online_link"]}">Download</a>'

            message_parts.extend(
                [f"<b>{i}.</b> <code>{file_name}</code>", link_line, ""]
            )

        if len(links_list) > 8:
            remaining = len(links_list) - 8
            message_parts.extend(
                [
                    f"📋 <b>+{remaining} more files processed</b>",
                    "   <i>Use individual commands for more links</i>",
                    "",
                ]
            )

        message_parts.extend(
            [
                "─────────────────────────",
                "💡 <b>Batch Tips:</b>",
                "• All links are ready for streaming",
                "• Download links work offline",
                "• Share individual links as needed",
                "",
                "✨ <b>Powered by File2Link</b> ✨",
            ]
        )

        return "\n".join(message_parts)

    except Exception as e:
        LOGGER.error(f"Error formatting batch message: {e}")
        return f"❌ Error formatting batch message: {e}"


def validate_base_url() -> bool:
    """Validate if File2Link base URL is properly configured"""
    try:
        base_url = get_file2link_base_url()
        return base_url and base_url != "http://localhost:8080"
    except Exception:
        return False


def validate_stream_request(secure_hash: str, message_id: int) -> bool:
    """Validate streaming request parameters"""
    try:
        # Basic validation
        if not secure_hash or not isinstance(secure_hash, str):
            return False
        if not message_id or not isinstance(message_id, int) or message_id <= 0:
            return False

        # Hash length validation (should be 6 characters)
        if len(secure_hash) != 6:
            return False

        # Hash should contain only alphanumeric characters, hyphens, and underscores
        return bool(re.match(r"^[a-zA-Z0-9_-]+$", secure_hash))
    except Exception:
        return False
