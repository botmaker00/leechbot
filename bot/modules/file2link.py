"""
File2Link module
Converts Telegram media files into direct streaming links
"""

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.stream_utils import (
    format_link_message,
    generate_stream_links,
    get_media,
    validate_file2link_media,
)
from bot.helper.stream_utils.link_generator import (
    format_batch_message,
    validate_base_url,
)
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import edit_message, send_message


async def forward_to_storage(message: Message) -> Message:
    """Forward media to storage channel"""
    try:
        storage_channel = Config.FILE2LINK_BIN_CHANNEL
        if not storage_channel:
            raise ValueError(
                "No storage channel configured. Please set FILE2LINK_BIN_CHANNEL in config"
            )

        # Forward message to storage channel
        stored_msg = await message.copy(chat_id=storage_channel)
        if not stored_msg:
            raise ValueError("Failed to forward message to storage")

        return stored_msg
    except Exception as e:
        LOGGER.error(f"Error forwarding to storage: {e}")
        raise


def create_link_buttons(links: dict) -> InlineKeyboardMarkup:
    """Create inline keyboard with stream and download buttons (stream only if file is streamable)"""
    buttons = []

    # Add stream button only if file is streamable
    if links.get("stream_link"):
        buttons.append(
            [
                InlineKeyboardButton("🎬 Stream", url=links["stream_link"]),
                InlineKeyboardButton("⬇️ Download", url=links["online_link"]),
            ]
        )
    else:
        # Only download button for non-streamable files
        buttons.append(
            [InlineKeyboardButton("⬇️ Download", url=links["online_link"])]
        )

    return InlineKeyboardMarkup(buttons)


async def process_single_file(
    message: Message, file_msg: Message, status_msg: Message = None
) -> dict | None:
    """Process a single file and generate links"""
    try:
        # Validate media for File2Link (no size limit)
        is_valid, error_msg = validate_file2link_media(file_msg)

        if not is_valid:
            full_error_msg = (
                "╭─────────────────────────╮\n"
                "│    ⚠️ <b>Validation Failed</b>    │\n"
                "╰─────────────────────────╯\n\n"
                f"❌ <b>{error_msg}</b>\n\n"
                "📋 <b>File2Link Requirements:</b>\n"
                "• No file size limit (files copied to storage)\n"
                "• Supported: Video, Audio, Documents, Images\n"
                "• Format: MP4, MKV, MP3, PDF, JPG, etc.\n\n"
                "💡 <b>File2Link works with any size file!</b>"
            )
            if status_msg:
                await edit_message(status_msg, full_error_msg)
            else:
                await send_message(message, full_error_msg)
            return None

        # Update status
        if status_msg:
            await edit_message(
                status_msg,
                "╭─────────────────────────╮\n"
                "│      🔄 <b>Processing</b>      │\n"
                "╰─────────────────────────╯\n\n"
                "📤 <b>Forwarding to storage...</b>\n"
                "🔐 Securing file for streaming...",
            )

        # Forward to storage channel
        stored_msg = await forward_to_storage(file_msg)

        # Update status
        if status_msg:
            await edit_message(
                status_msg,
                "╭─────────────────────────╮\n"
                "│      🔄 <b>Processing</b>      │\n"
                "╰─────────────────────────╯\n\n"
                "🔗 <b>Generating streaming links...</b>\n"
                "⚡ Creating optimized URLs...",
            )

        # Generate links
        links = await generate_stream_links(stored_msg)

        if not links or not links.get("online_link"):
            error_msg = (
                "╭─────────────────────────╮\n"
                "│      ❌ <b>Link Failed</b>      │\n"
                "╰─────────────────────────╯\n\n"
                "❌ <b>Failed to generate download links</b>\n\n"
                "🔧 <b>Possible Issues:</b>\n"
                "• File too large for processing\n"
                "• Unsupported media format\n"
                "• Temporary server issue\n\n"
                "💡 <b>Try again or contact admin</b>"
            )
            if status_msg:
                await edit_message(status_msg, error_msg)
            else:
                await send_message(message, error_msg)
            return None

        # Send links
        link_message = format_link_message(links, message.chat.title)

        if status_msg:
            await edit_message(
                status_msg, link_message, buttons=create_link_buttons(links)
            )
        else:
            await send_message(
                message, link_message, buttons=create_link_buttons(links)
            )

        return links

    except Exception as e:
        LOGGER.error(f"Error processing single file: {e}")
        error_msg = f"❌ Error processing file: {e!s}"
        if status_msg:
            await edit_message(status_msg, error_msg)
        else:
            await send_message(message, error_msg)
        return None


async def process_batch_files(
    message: Message, start_msg_id: int, count: int, status_msg: Message
) -> None:
    """Process multiple files in batch"""
    try:
        processed = 0
        failed = 0
        links_list = []

        # Get messages in batch
        end_msg_id = start_msg_id + count - 1
        batch_ids = list(range(start_msg_id, end_msg_id + 1))

        await edit_message(
            status_msg,
            "╭─────────────────────────╮\n"
            "│    📦 <b>Batch Processing</b>    │\n"
            "╰─────────────────────────╯\n\n"
            f"📥 <b>Collecting {count} files...</b>\n"
            "🔍 Scanning message range...",
        )

        try:
            messages = await TgClient.bot.get_messages(message.chat.id, batch_ids)
            if not messages:
                messages = []
        except Exception as e:
            LOGGER.error(f"Error getting batch messages: {e}")
            await edit_message(
                status_msg,
                "╭─────────────────────────╮\n"
                "│      ❌ **Batch Failed**      │\n"
                "╰─────────────────────────╯\n\n"
                f"❌ **Error getting files:** {e}\n\n"
                "🔧 **Possible Issues:**\n"
                "• Message range not accessible\n"
                "• Files may have been deleted\n"
                "• Temporary connection issue\n\n"
                "💡 **Try with individual files**",
            )
            return

        # Process each message
        for i, msg in enumerate(messages):
            if msg and get_media(msg):
                try:
                    # Update progress
                    progress_percent = ((i + 1) / count) * 100
                    progress_bar = "█" * int(progress_percent // 10) + "░" * (
                        10 - int(progress_percent // 10)
                    )

                    await edit_message(
                        status_msg,
                        "╭─────────────────────────╮\n"
                        "│    📦 **Batch Processing**    │\n"
                        "╰─────────────────────────╯\n\n"
                        f"🔄 **Processing file {i + 1}/{count}**\n"
                        f"📊 Progress: [{progress_bar}] {progress_percent:.0f}%\n\n"
                        f"✅ Completed: {processed}\n"
                        f"❌ Failed: {failed}\n"
                        f"⏳ Remaining: {count - (i + 1)}",
                    )

                    # Forward and generate links
                    stored_msg = await forward_to_storage(msg)
                    links = await generate_stream_links(stored_msg)

                    if links and links.get("stream_link"):
                        links_list.append(links)
                        processed += 1
                    else:
                        failed += 1

                except Exception as e:
                    LOGGER.error(f"Error processing file {i + 1}: {e}")
                    failed += 1
            else:
                failed += 1

        # Send final result
        if links_list:
            batch_message = format_batch_message(
                links_list, processed, count, failed
            )
            await edit_message(status_msg, batch_message)
        else:
            await edit_message(
                status_msg,
                "╭─────────────────────────╮\n"
                "│    📦 **Batch Complete**    │\n"
                "╰─────────────────────────╯\n\n"
                "❌ **No files could be processed**\n\n"
                f"📊 **Summary:**\n"
                f"• Total files: {count}\n"
                f"• Failed: {failed}\n"
                f"• Success rate: 0%\n\n"
                "🔧 **Common Issues:**\n"
                "• Files too large or unsupported\n"
                "• Network connectivity problems\n"
                "• Invalid file formats\n\n"
                "💡 **Try individual files or check formats**",
            )

    except Exception as e:
        LOGGER.error(f"Error in batch processing: {e}")
        await edit_message(
            status_msg,
            "╭─────────────────────────╮\n"
            "│      ❌ **System Error**      │\n"
            "╰─────────────────────────╯\n\n"
            f"❌ **Batch processing error:** {e}\n\n"
            "🔧 **System Issue Detected:**\n"
            "• Internal processing error\n"
            "• Temporary service disruption\n"
            "• Resource limitation reached\n\n"
            "💡 **Please try again later or contact admin**",
        )


@TgClient.bot.on_message(
    filters.command(BotCommands.File2LinkCommand) & CustomFilters.authorized
)
async def file2link_command(_client, message: Message):
    """Handle /file2link command"""
    try:
        # Check if File2Link is enabled
        if not Config.FILE2LINK_ENABLED:
            await send_message(
                message,
                "╭─────────────────────────╮\n"
                "│     🚫 <b>Service Disabled</b>     │\n"
                "╰─────────────────────────╯\n\n"
                "❌ <b>File2Link functionality is currently disabled</b>\n\n"
                "💡 <b>Admin Note:</b> Enable <code>FILE2LINK_ENABLED</code> in config",
            )
            return

        # Check if File2Link base URL is configured
        if not validate_base_url():
            await send_message(
                message,
                "╭─────────────────────────╮\n"
                "│    ⚙️ <b>Configuration Error</b>    │\n"
                "╰─────────────────────────╯\n\n"
                "❌ <b>Base URL not configured</b>\n\n"
                "🔧 <b>Required Configuration:</b>\n"
                "• Set <code>FILE2LINK_BASE_URL</code> in config\n"
                "• Or set <code>BASE_URL</code> as fallback\n\n"
                '💡 <b>Example:</b> <code>FILE2LINK_BASE_URL = "https://yourbot.herokuapp.com"</code>',
            )
            return

        # Check if storage channel is configured
        storage_channel = Config.FILE2LINK_BIN_CHANNEL
        if not storage_channel:
            await send_message(
                message,
                "╭─────────────────────────╮\n"
                "│    📁 <b>Storage Not Set</b>    │\n"
                "╰─────────────────────────╯\n\n"
                "❌ <b>Storage channel not configured</b>\n\n"
                "🔧 <b>Required Configuration:</b>\n"
                "• Set <code>FILE2LINK_BIN_CHANNEL</code> in config\n"
                "• Use a private channel ID\n\n"
                "💡 <b>Example:</b> <code>FILE2LINK_BIN_CHANNEL = -1001234567890</code>",
            )
            return

        # Check if replying to media
        if not message.reply_to_message:
            # Get the command that was used
            command_used = message.command[0] if message.command else "file2link"
            command_display = f"/{command_used}"

            await send_message(
                message,
                f"╭─────────────────────────╮\n"
                f"│      📎 <b>{command_display.upper()} Usage Guide</b>      │\n"
                f"╰─────────────────────────╯\n\n"
                f"❌ <b>No media file detected</b>\n\n"
                f"📋 <b>How to use {command_display}:</b>\n"
                f"1️⃣ Send or forward a media file\n"
                f"2️⃣ Reply to it with <code>{command_display}</code>\n"
                f"3️⃣ Get instant streaming links!\n\n"
                f"🎬 <b>Supported File Types:</b>\n"
                f"• 🎥 Videos (MP4, MKV, AVI, WEBM, etc.)\n"
                f"• 🎵 Audio (MP3, FLAC, M4A, OGG, etc.)\n"
                f"• 📄 Documents (PDF, ZIP, RAR, etc.)\n"
                f"• 🖼️ Images (JPG, PNG, GIF, WEBP, etc.)\n"
                f"• 🎙️ Voice messages & video notes\n"
                f"• 🎬 Animations and stickers\n\n"
                f"⚡ <b>Features:</b>\n"
                f"• Stream directly in browser\n"
                f"• Download links for offline viewing\n"
                f"• No file size limit (any size supported)\n"
                f"• Multi-client load balancing\n"
                f"• Secure hash-based access\n\n"
                f"💡 <b>Alternative:</b> Use <code>/file2link</code> or <code>/f2l</code> - both work the same!",
            )
            return

        reply_msg = message.reply_to_message

        # Check for batch processing (multiple files)
        if reply_msg.media_group_id:
            # Handle media group
            await send_message(
                message,
                "📦 Media group detected. Use batch processing for multiple files.",
            )
            return

        # Check if reply contains media
        if not get_media(reply_msg):
            await send_message(
                message,
                "╭─────────────────────────╮\n"
                "│     📎 <b>No Media Found</b>     │\n"
                "╰─────────────────────────╯\n\n"
                "❌ <b>The replied message doesn't contain media</b>\n\n"
                "🎬 <b>Supported Media Types:</b>\n"
                "• 🎥 Videos (MP4, MKV, AVI, WEBM, etc.)\n"
                "• 🎵 Audio (MP3, FLAC, M4A, OGG, etc.)\n"
                "• 📄 Documents (PDF, ZIP, RAR, etc.)\n"
                "• 🖼️ Images (JPG, PNG, GIF, WEBP, etc.)\n"
                "• 🎙️ Voice messages & video notes\n"
                "• 🎬 Animations and stickers\n\n"
                "💡 <b>Try replying to a media file instead</b>",
            )
            return

        # Send processing status
        status_msg = await send_message(
            message,
            "╭─────────────────────────╮\n"
            "│      🔄 <b>Processing</b>      │\n"
            "╰─────────────────────────╯\n\n"
            "⏳ <b>Initializing File2Link...</b>\n"
            "📋 Analyzing media file...",
        )

        # Process the file
        await process_single_file(message, reply_msg, status_msg)

    except Exception as e:
        LOGGER.error(f"Error in file2link command: {e}")
        await send_message(
            message,
            "╭─────────────────────────╮\n"
            "│      ⚠️ <b>System Error</b>      │\n"
            "╰─────────────────────────╯\n\n"
            f"❌ <b>An unexpected error occurred</b>\n\n"
            f"🔧 <b>Error Details:</b> <code>{e!s}</code>\n\n"
            "📋 <b>What to do:</b>\n"
            "• Try the command again\n"
            "• Check if file is accessible\n"
            "• Contact admin if issue persists\n\n"
            "💡 <b>Error has been logged for investigation</b>",
        )
