"""
NSFW Detection Management Module

This module provides admin commands for managing the enhanced NSFW detection system:
- View detection statistics
- Configure sensitivity settings
- Test detection on content
- Manage whitelist/blacklist
- View user behavior patterns
"""

import os
import tempfile

from pyrogram.types import Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.nsfw_detection import nsfw_detector
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    edit_message,
    send_message,
)


async def nsfw_stats_command(client, message: Message):
    """Show NSFW detection statistics"""
    if not await CustomFilters.authorized(client, message):
        await send_message(
            message, "❌ This command is only available to authorized users."
        )
        return

    try:
        # Get detection statistics
        stats = await database.get_nsfw_detection_stats(days=7)

        if not stats or stats.get("total_detections", 0) == 0:
            await send_message(
                message,
                "📊 <b>NSFW Detection Statistics (Last 7 Days)</b>\n\n"
                "No detection data available for the last 7 days.",
            )
            return

        # Format statistics
        total = stats.get("total_detections", 0)
        nsfw_detected = stats.get("nsfw_detected", 0)
        avg_confidence = stats.get("avg_confidence", 0)
        detection_rate = (nsfw_detected / total * 100) if total > 0 else 0

        stats_text = (
            f"📊 <b>NSFW Detection Statistics (Last 7 Days)</b>\n\n"
            f"🔍 <b>Total Checks:</b> {total:,}\n"
            f"🚫 <b>NSFW Detected:</b> {nsfw_detected:,}\n"
            f"📈 <b>Detection Rate:</b> {detection_rate:.1f}%\n"
            f"🎯 <b>Avg Confidence:</b> {avg_confidence:.2f}\n\n"
            f"⚙️ <b>Current Settings:</b>\n"
            f"• Status: {'✅ Enabled' if Config.NSFW_DETECTION_ENABLED else '❌ Disabled'}\n"
            f"• Sensitivity: {Config.NSFW_DETECTION_SENSITIVITY.title()}\n"
            f"• Threshold: {Config.NSFW_CONFIDENCE_THRESHOLD}\n"
            f"• Visual Analysis: {'✅' if Config.NSFW_VISUAL_DETECTION else '❌'}\n"
            f"• Keyword Detection: {'✅' if Config.NSFW_KEYWORD_DETECTION else '❌'}\n"
            f"• Fuzzy Matching: {'✅' if Config.NSFW_FUZZY_MATCHING else '❌'}\n"
            f"• Multi-language: {'✅' if Config.NSFW_MULTI_LANGUAGE else '❌'}"
        )

        await send_message(message, stats_text)

    except Exception as e:
        LOGGER.error(f"Error in nsfw_stats_command: {e}")
        await send_message(message, f"❌ Error retrieving NSFW statistics: {e!s}")


async def nsfw_test_command(client, message: Message):
    """Test NSFW detection on provided text or replied content"""
    if not await CustomFilters.authorized(client, message):
        await send_message(
            message, "❌ This command is only available to authorized users."
        )
        return

    try:
        # Get test content
        test_text = None
        test_file = None

        # Check for command arguments
        if message.text:
            args = message.text.split(maxsplit=1)
            if len(args) > 1:
                test_text = args[1]

        # Check for replied message
        elif message.reply_to_message:
            reply = message.reply_to_message
            test_text = reply.text or reply.caption

            # Check for file in reply
            if reply.document or reply.photo or reply.video:
                test_file = reply.document or reply.photo or reply.video

        if not test_text and not test_file:
            await send_message(
                message,
                "❓ <b>NSFW Detection Test</b>\n\n"
                "Usage:\n"
                f"• <code>/{BotCommands.NSFWTestCommand} your text here</code>\n"
                f"• Reply to a message with <code>/{BotCommands.NSFWTestCommand}</code>\n"
                f"• Reply to media (images/videos/audio/subtitles) with <code>/{BotCommands.NSFWTestCommand}</code>\n\n"
                "This will test the NSFW detection on the provided content.\n"
                "• <b>Images:</b> Full AI visual analysis using configured APIs\n"
                "• <b>Videos:</b> Smart frame extraction and analysis of multiple frames\n"
                "• <b>Audio:</b> Metadata extraction and text analysis\n"
                "• <b>Subtitles:</b> Full text extraction and content analysis",
            )
            return

        status_msg = await send_message(message, "🔍 Testing NSFW detection...")

        # Test text content
        if test_text:
            result = await nsfw_detector.detect_text_nsfw(test_text)

            result_text = (
                f"🧪 <b>NSFW Detection Test Results</b>\n\n"
                f"📝 <b>Content:</b> <code>{test_text[:100]}{'...' if len(test_text) > 100 else ''}</code>\n\n"
                f"🎯 <b>Result:</b> {'🚫 NSFW Detected' if result.is_nsfw else '✅ Clean Content'}\n"
                f"📊 <b>Confidence:</b> {result.confidence:.2f}\n"
                f"⏱️ <b>Processing Time:</b> {result.processing_time:.3f}s\n"
                f"🔧 <b>Methods Used:</b> {', '.join(result.detection_methods) if result.detection_methods else 'None'}\n"
            )

            if result.keyword_matches:
                result_text += f"🔍 <b>Keyword Matches:</b> {', '.join(result.keyword_matches[:5])}\n"

            if result.error_messages:
                result_text += (
                    f"⚠️ <b>Errors:</b> {', '.join(result.error_messages)}\n"
                )

        # Test file content (full analysis including download and visual detection)
        elif test_file:
            file_name = getattr(test_file, "file_name", "unknown_file")
            file_size = getattr(test_file, "file_size", 0)

            # Check file size limit
            if file_size > Config.NSFW_MAX_FILE_SIZE:
                result_text = (
                    f"🧪 <b>NSFW Detection Test Results</b>\n\n"
                    f"📁 <b>File:</b> <code>{file_name}</code>\n"
                    f"📏 <b>Size:</b> {file_size / (1024 * 1024):.1f} MB\n\n"
                    f"❌ <b>Error:</b> File too large for analysis\n"
                    f"📊 <b>Max Size:</b> {Config.NSFW_MAX_FILE_SIZE / (1024 * 1024):.1f} MB"
                )
            else:
                # Update status message
                await edit_message(status_msg, "📥 Downloading file for analysis...")

                try:
                    # Download file temporarily for analysis

                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_file_path = os.path.join(
                            temp_dir, file_name or "temp_file"
                        )

                        # Download the file
                        download_client = client or TgClient.bot
                        await download_client.download_media(
                            message.reply_to_message, file_name=temp_file_path
                        )

                        # Update status
                        await edit_message(
                            status_msg, "🔍 Analyzing file content..."
                        )

                        # Run comprehensive NSFW detection
                        result = await nsfw_detector.detect_file_nsfw(
                            temp_file_path, file_name
                        )

                        # Format results
                        result_text = (
                            f"🧪 <b>NSFW Detection Test Results</b>\n\n"
                            f"📁 <b>File:</b> <code>{file_name}</code>\n"
                            f"📏 <b>Size:</b> {file_size / (1024 * 1024):.1f} MB\n\n"
                            f"🎯 <b>Result:</b> {'🚫 NSFW Detected' if result.is_nsfw else '✅ Clean Content'}\n"
                            f"📊 <b>Confidence:</b> {result.confidence:.2f}\n"
                            f"⏱️ <b>Processing Time:</b> {result.processing_time:.3f}s\n"
                            f"🔧 <b>Methods Used:</b> {', '.join(result.detection_methods) if result.detection_methods else 'None'}\n"
                        )

                        # Add keyword matches if any
                        if result.keyword_matches:
                            result_text += f"🔍 <b>Keyword Matches:</b> {', '.join(result.keyword_matches[:5])}\n"

                        # Add visual analysis results if available
                        if result.visual_analysis:
                            visual = result.visual_analysis
                            if "error" not in visual:
                                providers = visual.get("providers_used", [])
                                if providers:
                                    result_text += f"👁️ <b>Visual Analysis:</b> {', '.join(providers)}\n"
                                    if "google" in visual.get(
                                        "provider_results", {}
                                    ):
                                        google_result = visual["provider_results"][
                                            "google"
                                        ]
                                        if "adult_confidence" in google_result:
                                            result_text += f"🔞 <b>Adult Score:</b> {google_result['adult_confidence']:.2f}\n"
                                        if "racy_confidence" in google_result:
                                            result_text += f"🌶️ <b>Racy Score:</b> {google_result['racy_confidence']:.2f}\n"
                            else:
                                result_text += (
                                    f"👁️ <b>Visual Analysis:</b> {visual['error']}\n"
                                )

                        # Add error messages if any
                        if result.error_messages:
                            result_text += f"⚠️ <b>Warnings:</b> {', '.join(result.error_messages[:3])}\n"

                except Exception as e:
                    LOGGER.error(f"Error downloading/analyzing file: {e}")
                    result_text = (
                        f"🧪 <b>NSFW Detection Test Results</b>\n\n"
                        f"📁 <b>File:</b> <code>{file_name}</code>\n\n"
                        f"❌ <b>Error:</b> Failed to download or analyze file\n"
                        f"🔍 <b>Details:</b> {str(e)[:100]}"
                    )

        await edit_message(status_msg, result_text)

    except Exception as e:
        LOGGER.error(f"Error in nsfw_test_command: {e}")
        await send_message(message, f"❌ Error testing NSFW detection: {e!s}")
