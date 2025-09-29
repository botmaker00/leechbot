import os
from asyncio import create_task

import aiofiles
from bs4 import BeautifulSoup
from httpx import AsyncClient
from pyrogram.types import Message
from telegraph import Telegraph

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


async def katbin_paste(text: str) -> str:
    """
    Paste the text in katb.in website.
    Args:
        text: The text content to paste
    Returns:
        str: URL of the pasted content or error message
    """
    katbin_url = "https://katb.in"
    client = AsyncClient()
    try:
        # Get the CSRF token from the page
        response = await client.get(katbin_url)
        soup = BeautifulSoup(response.content, "html.parser")
        csrf_token = soup.find("input", {"name": "_csrf_token"}).get("value")

        # Post the content with the CSRF token
        paste_post = await client.post(
            katbin_url,
            data={"_csrf_token": csrf_token, "paste[content]": text},
            follow_redirects=False,
        )

        # Get the URL from the redirect location
        return f"{katbin_url}{paste_post.headers['location']}"
    except Exception as e:
        LOGGER.error(f"Error in katbin_paste: {e}")
        return "Something went wrong while pasting text in katb.in."
    finally:
        await client.aclose()


async def telegraph_paste(content: str, title="Aim") -> str:
    """
    Paste the text in telegra.ph (graph.org) website.
    Args:
        content: The text content to paste
        title: Title for the Telegraph page
    Returns:
        str: URL of the pasted content or fallback to katbin
    """
    try:
        # The standard Telegraph package is synchronous
        telegraph = Telegraph(domain="graph.org")
        telegraph.create_account(short_name=title)
        html_content = (
            "<pre><code>" + content.replace("\n", "<br>") + "</code></pre>"
        )

        response = telegraph.create_page(title=title, html_content=html_content)
        return response["url"]
    except Exception as e:
        LOGGER.error(f"Error in telegraph_paste: {e}")
        # Fallback to katbin if telegraph fails
        return await katbin_paste(content)


async def pastebin_paste(content: str, title: str = "Aim Paste") -> str:
    """
    Paste the text to Pastebin.com using their API.
    Args:
        content: The text content to paste
        title: Title for the paste
    Returns:
        str: URL of the pasted content or fallback to katbin
    """
    if not Config.PASTEBIN_ENABLED or not Config.PASTEBIN_API_KEY:
        LOGGER.warning("Pastebin is not configured, falling back to katbin")
        return await katbin_paste(content)

    # Validate content is not empty (API requirement)
    if not content or not content.strip():
        LOGGER.error("Pastebin API error: Content is empty")
        return await katbin_paste(content)

    # Check content size (Pastebin has limits)
    content_size = len(content.encode("utf-8"))
    if content_size > 512000:  # 512KB limit for free accounts
        LOGGER.warning(
            f"Content too large for Pastebin ({content_size} bytes), falling back to katbin"
        )
        return await katbin_paste(content)

    pastebin_url = "https://pastebin.com/api/api_post.php"
    client = AsyncClient()

    try:
        # Enhanced format detection based on title and content
        paste_format = _detect_paste_format(title, content)

        # Prepare the data for Pastebin API (following exact API specification)
        data = {
            "api_dev_key": Config.PASTEBIN_API_KEY,
            "api_option": "paste",
            "api_paste_code": content,
            "api_paste_name": title[:100],  # Limit title length
            "api_paste_format": paste_format,
            "api_paste_private": "1",  # 0=public, 1=unlisted, 2=private
            "api_paste_expire_date": "1M",  # 1 Month expiry
        }

        # Make the API request with proper headers
        response = await client.post(
            pastebin_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        response_text = response.text.strip()

        # Check if the response is a valid URL
        if response_text.startswith("https://pastebin.com/"):
            return response_text

        # Handle specific API errors with better logging
        error_msg = _handle_pastebin_error(response_text)
        LOGGER.error(f"Pastebin API error: {error_msg}")
        return await katbin_paste(content)

    except Exception as e:
        LOGGER.error(f"Error in pastebin_paste: {e}")
        # Fallback to katbin if pastebin fails
        return await katbin_paste(content)
    finally:
        await client.aclose()


def _detect_paste_format(title: str, content: str) -> str:
    """
    Enhanced format detection based on title and content analysis.
    Returns valid Pastebin format string.
    """
    title_lower = title.lower()
    content_sample = content[:500].lower()  # First 500 chars for analysis

    # File extension based detection (most reliable)
    extension_map = {
        ".py": "python",
        ".python": "python",
        ".js": "javascript",
        ".javascript": "javascript",
        ".json": "json",
        ".xml": "xml",
        ".html": "html5",
        ".htm": "html5",
        ".css": "css",
        ".sh": "bash",
        ".bash": "bash",
        ".sql": "sql",
        ".php": "php",
        ".java": "java",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "c",
        ".cs": "csharp",
        ".rb": "ruby",
        ".go": "go",
        ".rs": "rust",
        ".ts": "typescript",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".r": "rsplus",
        ".pl": "perl",
        ".lua": "lua",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".ini": "ini",
        ".conf": "ini",
        ".config": "ini",
        ".md": "markdown",
        ".tex": "latex",
        ".dockerfile": "bash",
        ".log": "text",
        ".txt": "text",
    }

    for ext, format_name in extension_map.items():
        if title_lower.endswith(ext):
            return format_name

    # Content-based detection for files without clear extensions
    if any(
        keyword in content_sample
        for keyword in ["import ", "def ", "class ", "print(", "if __name__"]
    ):
        return "python"
    if any(
        keyword in content_sample
        for keyword in ["function", "var ", "const ", "let ", "console.log"]
    ):
        return "javascript"
    if content_sample.strip().startswith(("{", "[")):
        return "json"
    if content_sample.strip().startswith(("<", "<!doctype", "<!DOCTYPE")):
        return "html5"
    if any(
        keyword in content_sample
        for keyword in ["select ", "insert ", "update ", "delete ", "create table"]
    ):
        return "sql"
    if any(keyword in content_sample for keyword in ["<?php", "echo ", "$_"]):
        return "php"
    if any(
        keyword in content_sample
        for keyword in ["public class", "import java", "system.out"]
    ):
        return "java"
    if any(
        keyword in content_sample for keyword in ["#include", "int main", "printf"]
    ):
        return "c"
    if any(
        keyword in content_sample for keyword in ["using namespace", "std::", "cout"]
    ):
        return "cpp"
    if any(
        keyword in content_sample
        for keyword in ["#!/bin/bash", "#!/bin/sh", "echo ", "if [", "fi"]
    ):
        return "bash"

    return "text"  # Default fallback


def _handle_pastebin_error(error_response: str) -> str:
    """
    Handle and categorize Pastebin API error responses.
    Returns user-friendly error message.
    """
    error_lower = error_response.lower()

    if "invalid api_dev_key" in error_lower:
        return "Invalid Pastebin API key. Please check your configuration."
    if "api_paste_code was empty" in error_lower:
        return "Content is empty or invalid."
    if "maximum paste file size exceeded" in error_lower:
        return "File size exceeds Pastebin limits."
    if "maximum number of 25 unlisted pastes" in error_lower:
        return (
            "Pastebin account limit reached (25 unlisted pastes for free accounts)."
        )
    if "maximum number of 10 private pastes" in error_lower:
        return (
            "Pastebin account limit reached (10 private pastes for free accounts)."
        )
    if "invalid api_paste_expire_date" in error_lower:
        return "Invalid expiration date format."
    if "invalid api_paste_private" in error_lower:
        return "Invalid privacy setting."
    if "invalid api_paste_format" in error_lower:
        return "Invalid format/syntax highlighting option."
    if "invalid api_option" in error_lower:
        return "Invalid API option parameter."

    return f"Unknown Pastebin API error: {error_response}"


async def smart_paste(content: str, title: str = "Aim Paste") -> tuple[str, str]:
    """
    Smart paste function that tries multiple services in order of preference.
    Args:
        content: The text content to paste
        title: Title for the paste
    Returns:
        tuple: (paste_url, service_name)
    """
    content_size = len(content)

    # For very large content, prefer Pastebin (if available) as it handles large files better
    if (
        content_size > 500000 and Config.PASTEBIN_ENABLED and Config.PASTEBIN_API_KEY
    ):  # > 500KB
        try:
            url = await pastebin_paste(content, title)
            if url.startswith("https://pastebin.com/"):
                return url, "Pastebin"
        except Exception as e:
            LOGGER.error(f"Pastebin failed for large content: {e}")

    # For medium content, try Telegraph first (better formatting)
    if content_size <= 1000000:  # <= 1MB (Telegraph limit)
        try:
            url = await telegraph_paste(content, title)
            if url.startswith("https://telegra.ph/"):
                return url, "Telegraph"
        except Exception as e:
            LOGGER.error(f"Telegraph failed: {e}")

    # Try Pastebin as secondary option
    if Config.PASTEBIN_ENABLED and Config.PASTEBIN_API_KEY:
        try:
            url = await pastebin_paste(content, title)
            if url.startswith("https://pastebin.com/"):
                return url, "Pastebin"
        except Exception as e:
            LOGGER.error(f"Pastebin failed: {e}")

    # Fallback to katbin
    try:
        url = await katbin_paste(content)
        return url, "Katbin"
    except Exception as e:
        LOGGER.error(f"All paste services failed: {e}")
        return "Failed to paste content to any service.", "None"


async def paste_text(_client, message: Message):
    """
    Paste the text in katb.in website.

    Args:
        client: The Pyrogram client instance
        message: The message containing text to paste

    Returns:
        None
    """
    # Build available services list
    available_services = ["Katbin"]
    if Config.PASTEBIN_ENABLED and Config.PASTEBIN_API_KEY:
        available_services.insert(0, "Pastebin")
    available_services.insert(-1, "Telegraph")

    services_text = ", ".join(available_services)

    paste_usage = (
        "**📋 Paste Command Usage**\n\n"
        f"Paste text to multiple paste services ({services_text}). You can use this command in three ways:\n\n"
        "1️⃣ **Direct text:** <pre><code>/paste your text here</code></pre>\n"
        "2️⃣ **Reply to a message:** Reply to any text message with <pre><code>/paste</code></pre>\n"
        "3️⃣ **Reply to a file:** Reply to a text file with <pre><code>/paste</code></pre>\n\n"
        "**Supported file types:** <pre><code>.txt, .log, .json, .xml, .csv, .md, .py, .js, .html, .css, .conf, .ini, .sh, .bat</code></pre> and more\n\n"
        "**🤖 Smart Selection:** The bot automatically chooses the best service based on content size and type."
    )

    # Send initial reply
    paste_reply = await send_message(message, "Pasting...")
    replied_message = message.reply_to_message

    try:
        # Get content from command arguments
        if len(message.command) > 1 and message.text:
            content = message.text.split(None, 1)[1]

        # Get content from replied message text
        elif replied_message and replied_message.text:
            content = replied_message.text

        # Get content from replied document
        elif replied_message and replied_message.document:
            # Check if it's a text file by mime type or file extension
            is_text_file = False

            # Check mime type
            if replied_message.document.mime_type:
                is_text_file = any(
                    format in replied_message.document.mime_type.lower()
                    for format in ("text", "json", "xml", "csv", "html", "plain")
                )

            # Check file extension if mime type check failed
            if not is_text_file and replied_message.document.file_name:
                file_name = replied_message.document.file_name.lower()
                text_extensions = (
                    ".txt",
                    ".log",
                    ".json",
                    ".xml",
                    ".csv",
                    ".md",
                    ".py",
                    ".js",
                    ".html",
                    ".css",
                    ".conf",
                    ".ini",
                    ".sh",
                    ".bat",
                )
                is_text_file = any(
                    file_name.endswith(ext) for ext in text_extensions
                )

            if is_text_file:
                # Download the file
                file_path = os.path.join(os.getcwd(), "temp_file")
                await paste_reply.edit("Downloading file...")
                await message.reply_to_message.download(file_path)

                try:
                    # Read the file content
                    await paste_reply.edit("Reading file content...")
                    async with aiofiles.open(
                        file_path, encoding="utf-8", errors="replace"
                    ) as file:
                        content = await file.read()

                    # Limit content size if too large
                    if len(content) > 1000000:  # ~1MB limit
                        content = (
                            content[:1000000]
                            + "\n\n... (content truncated due to size)"
                        )
                        await paste_reply.edit(
                            "File is very large, content will be truncated..."
                        )
                except UnicodeDecodeError:
                    await paste_reply.edit(
                        "Error: Cannot read file - it appears to be a binary file, not text."
                    )
                    await auto_delete_message(paste_reply, time=60)
                    if os.path.exists(file_path):
                        os.remove(file_path)

                    # Auto-delete the command message and replied message
                    create_task(auto_delete_message(message, time=300))
                    if replied_message:
                        create_task(auto_delete_message(replied_message, time=300))
                    return
                except Exception as e:
                    await paste_reply.edit(f"Error reading file: {e!s}")
                    await auto_delete_message(paste_reply, time=60)
                    if os.path.exists(file_path):
                        os.remove(file_path)

                    # Auto-delete the command message and replied message
                    create_task(auto_delete_message(message, time=300))
                    if replied_message:
                        create_task(auto_delete_message(replied_message, time=300))
                    return
                finally:
                    # Remove the temporary file
                    if os.path.exists(file_path):
                        os.remove(file_path)

                await paste_reply.edit("Pasting content...")
            else:
                await paste_reply.edit(
                    "Error: The file doesn't appear to be a text file."
                )
                await auto_delete_message(paste_reply, time=60)

                # Auto-delete the command message and replied message
                create_task(auto_delete_message(message, time=300))
                if replied_message:
                    create_task(auto_delete_message(replied_message, time=300))
                return

        # No valid content found
        else:
            await paste_reply.edit(paste_usage)
            await auto_delete_message(paste_reply, time=60)

            # Auto-delete the command message
            create_task(auto_delete_message(message, time=300))
            if replied_message:
                create_task(auto_delete_message(replied_message, time=300))
            return

        # Check if content is too large for pasting
        if len(content) > 4000000:  # ~4MB limit (katbin might have lower limits)
            await paste_reply.edit("Error: Content is too large for pasting (>4MB).")
            await auto_delete_message(paste_reply, time=60)

            # Auto-delete the command message and replied message
            create_task(auto_delete_message(message, time=300))
            if replied_message:
                create_task(auto_delete_message(replied_message, time=300))
            return

        # Determine paste title from file name or content type
        paste_title = "Aim Paste"
        if (
            replied_message
            and replied_message.document
            and replied_message.document.file_name
        ):
            paste_title = replied_message.document.file_name
        elif len(content) > 0:
            # Try to detect content type from first few lines
            first_lines = content[:200].lower()
            if any(
                keyword in first_lines
                for keyword in ["import ", "def ", "class ", "print("]
            ):
                paste_title = "Python Code"
            elif any(
                keyword in first_lines
                for keyword in ["function", "var ", "const ", "let "]
            ):
                paste_title = "JavaScript Code"
            elif first_lines.strip().startswith(("{", "[")):
                paste_title = "JSON Data"
            elif first_lines.strip().startswith("<"):
                paste_title = "XML/HTML Data"

        # Paste the content using smart paste
        await paste_reply.edit("🔄 Finding best paste service...")
        paste_url, service_used = await smart_paste(content, paste_title)

        # Create a nice response with content info
        content_lines = content.count("\n") + 1
        content_size = len(content)
        size_str = (
            f"{content_size / 1024:.1f} KB"
            if content_size >= 1024
            else f"{content_size} bytes"
        )

        # Choose appropriate emoji for service
        service_emoji = {
            "Pastebin": "📋",
            "Telegraph": "📰",
            "Katbin": "📝",
            "None": "❌",
        }.get(service_used, "📄")

        if paste_url.startswith("http"):
            response = (
                f"<b>{service_emoji} Successfully pasted to {service_used}</b>\n\n"
            )
            response += f"• <b>URL:</b> <blockquote>{paste_url}</blockquote>\n"
            response += f"• <b>Title:</b> <pre><code>{paste_title}</code></pre>\n"
            response += f"• <b>Size:</b> <pre><code>{size_str}</code></pre>\n"
            response += f"• <b>Lines:</b> <pre><code>{content_lines}</code></pre>\n"
            response += f"• <b>Service:</b> <pre><code>{service_used}</code></pre>\n"
            response += "\n<i>This message and the command will be auto-deleted in 5 minutes.</i>"
        else:
            response = "❌ <b>Failed to paste content</b>\n\n"
            response += f"• <b>Error:</b> <pre><code>{paste_url}</code></pre>\n"
            response += f"• <b>Size:</b> <pre><code>{size_str}</code></pre>\n"
            response += f"• <b>Lines:</b> <pre><code>{content_lines}</code></pre>\n"

        await paste_reply.edit(response, disable_web_page_preview=True)

        # Auto-delete the command message and replied message after 5 minutes
        create_task(
            auto_delete_message(message, time=300)
        )  # 5 minutes = 300 seconds
        if replied_message:
            create_task(auto_delete_message(replied_message, time=300))

    except Exception as e:
        LOGGER.error(f"Error in paste command: {e}")
        await paste_reply.edit(f"Error: {e!s}")
        await auto_delete_message(paste_reply, time=60)

        # Also auto-delete the command message and replied message in case of error
        create_task(auto_delete_message(message, time=300))
        if replied_message:
            create_task(auto_delete_message(replied_message, time=300))
