import asyncio
import os
from asyncio import create_task, sleep
from contextlib import suppress
from functools import partial
from time import time

# Optional imports that may not be available
try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from aiofiles import open as aiopen
from pyrogram import filters
from pyrogram.filters import create
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import CallbackQuery

from bot import LOGGER, user_data
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import makedirs
from bot.helper.ext_utils.aiofiles_compat import remove as aioremove
from bot.helper.ext_utils.bot_utils import (
    is_media_tool_enabled,
    new_task,
    update_user_ldata,
)
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.help_messages import (
    media_tools_text,  # This imports the combined dictionary
)
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

handler_dict = {}
merge_config_page = 0  # Global variable to track merge_config page
watermark_config_page = 0  # Global variable to track watermark_config page

# Dictionary to store task contexts for -mt flag
task_contexts = {}

# Dictionary to track which users are in task context (using -mt flag)
task_context_users = set()

# Dictionary to track users who should be in task context but show_media_tools_for_task wasn't called
# This helps with debugging and implementing fallback behavior
pending_task_users = set()

# Dictionary to store direct task results for users who clicked Done/Cancel before show_media_tools_for_task was called
# This handles the race condition where user clicks buttons before the event waiting mechanism is set up
direct_task_results = {}


def register_pending_task_user(user_id):
    """Register a user as pending task user when -mt flag is detected."""
    pending_task_users.add(user_id)


async def show_media_tools_for_task(client, message, task_instance):
    """Show media tools settings for a task and wait for user response.

    Args:
        client: Telegram client
        message: Original command message
        task_instance: Mirror/Leech task instance

    Returns:
        bool: True if user clicked Done, False if user clicked Cancel or timeout
    """
    user_id = None
    try:
        user_id = message.from_user.id

        # Check if user already clicked Done/Cancel before this function was called (race condition handling)
        if user_id in direct_task_results:
            result = direct_task_results[user_id]
            # Clean up
            del direct_task_results[user_id]
            task_context_users.discard(user_id)
            pending_task_users.discard(user_id)
            return result

        # Check if media tools are enabled
        if not is_media_tool_enabled("mediatools"):
            await send_message(
                message,
                "<b>Media Tools are disabled</b>\n\nMedia Tools have been disabled by the bot owner.",
            )
            return False

        # Store the task context
        task_contexts[user_id] = {
            "task_instance": task_instance,
            "event": asyncio.Event(),
            "result": False,
        }
        # Add user to task context set
        task_context_users.add(user_id)
        # Remove from pending set since we're now handling it
        pending_task_users.discard(user_id)

        # Get media tools settings
        msg, btns = await get_media_tools_settings(message.from_user, "main")

        # Create new buttons with Done and Cancel
        buttons = ButtonMaker()

        # Add all existing buttons except Close
        if btns and hasattr(btns, "inline_keyboard"):
            for row in btns.inline_keyboard:
                for btn in row:
                    # Skip the Close button as we'll replace it with Done/Cancel
                    if btn.text == "Close":
                        continue  # Skip the Close button
                    if "footer" in btn.callback_data:
                        buttons.data_button(btn.text, btn.callback_data, "footer")
                    else:
                        buttons.data_button(btn.text, btn.callback_data)

        # Add Done and Cancel buttons
        buttons.data_button("✅ Done", f"mediatools {user_id} task_done", "footer")
        buttons.data_button(
            "❌ Cancel", f"mediatools {user_id} task_cancel", "footer"
        )

        # Send the media tools menu
        settings_msg = await send_message(message, msg, buttons.build_menu(2))

        # Wait for user response (5 minutes timeout)
        try:
            # Check if event is already set (user clicked before we started waiting)
            if task_contexts[user_id]["event"].is_set():
                pass  # Event already set, proceed to get result

            await asyncio.wait_for(
                task_contexts[user_id]["event"].wait(), timeout=300.0
            )
            result = task_contexts[user_id]["result"]
            if result:
                await edit_message(
                    settings_msg, "✅ Settings saved! Starting task..."
                )
            else:
                await edit_message(settings_msg, "❌ Task cancelled by user.")
        except TimeoutError:
            await edit_message(
                settings_msg,
                "⏰ Media tools configuration timed out. Task cancelled.",
            )
            result = False
        except Exception:
            await edit_message(settings_msg, "❌ Error occurred. Task cancelled.")
            result = False

        # Clean up
        task_contexts.pop(user_id, None)
        # Remove user from all tracking structures
        task_context_users.discard(user_id)
        pending_task_users.discard(user_id)
        direct_task_results.pop(user_id, None)

        # Wait a moment for user to see the result, then delete the message
        await sleep(2)
        await delete_message(settings_msg)

        return result

    except Exception as e:
        LOGGER.error(f"Error in show_media_tools_for_task: {e}")
        import traceback

        LOGGER.error(f"Traceback: {traceback.format_exc()}")
        # Clean up on error
        if user_id and user_id in task_contexts:
            del task_contexts[user_id]
        # Remove user from all tracking structures
        if user_id:
            task_context_users.discard(user_id)
            pending_task_users.discard(user_id)
            direct_task_results.pop(user_id, None)
        return False


async def get_media_tools_settings(from_user, stype="main", page_no=0):
    """Get media tools settings for a user."""

    user_id = from_user.id
    user_name = from_user.mention(style="html")
    buttons = ButtonMaker()
    user_dict = user_data.get(user_id, {})
    text = ""  # Initialize text variable to avoid UnboundLocalError
    btns = None  # Initialize btns variable to avoid UnboundLocalError

    # Check if media tools are enabled
    if not is_media_tool_enabled("mediatools") and stype == "main":
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)
        text = "<b>Media Tools are disabled</b>\n\nMedia Tools have been disabled by the bot owner."
        return text, btns

    if stype == "main":
        # Main Media Tools menu - only show enabled tools

        if is_media_tool_enabled("watermark"):
            buttons.data_button("Watermark", f"mediatools {user_id} watermark")

        if is_media_tool_enabled("merge"):
            buttons.data_button("Merge", f"mediatools {user_id} merge")

        if is_media_tool_enabled("convert"):
            buttons.data_button("Convert", f"mediatools {user_id} convert")

        if is_media_tool_enabled("compression"):
            buttons.data_button("Compression", f"mediatools {user_id} compression")

        if is_media_tool_enabled("trim"):
            buttons.data_button("Trim", f"mediatools {user_id} trim")

        if is_media_tool_enabled("extract"):
            buttons.data_button("Extract", f"mediatools {user_id} extract")

        if is_media_tool_enabled("remove"):
            buttons.data_button("Remove", f"mediatools {user_id} remove")

        if is_media_tool_enabled("add"):
            buttons.data_button("Add", f"mediatools {user_id} add")

        if is_media_tool_enabled("swap"):
            buttons.data_button("Swap", f"mediatools {user_id} swap")

        buttons.data_button("Help", f"mediatools {user_id} help")
        buttons.data_button("Remove All", f"mediatools {user_id} remove_all")
        buttons.data_button("Reset All", f"mediatools {user_id} reset_all")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Check if watermark is enabled for the user
        user_watermark_enabled = user_dict.get("WATERMARK_ENABLED", False)
        # Check if watermark is enabled globally - need both conditions:
        # 1. The tool is included in MEDIA_TOOLS_ENABLED
        # 2. The tool's individual ENABLED flag is set

        owner_watermark_available = is_media_tool_enabled("watermark")
        owner_watermark_enabled = (
            owner_watermark_available and Config.WATERMARK_ENABLED
        )

        if user_watermark_enabled:
            watermark_status = "✅ ON (User)"
        elif owner_watermark_enabled:
            watermark_status = "✅ ON (Global)"
        else:
            watermark_status = "❌ OFF"

        # Get watermark text based on priority
        user_has_text = "WATERMARK_KEY" in user_dict and user_dict["WATERMARK_KEY"]
        owner_has_text = Config.WATERMARK_KEY

        if user_has_text:
            watermark_text = f"{user_dict['WATERMARK_KEY']} (User)"
        elif (user_watermark_enabled and owner_has_text) or (
            owner_watermark_enabled and owner_has_text
        ):
            watermark_text = f"{Config.WATERMARK_KEY} (Global)"
        else:
            watermark_text = "None"

        # Check if merge is enabled for the user
        user_merge_enabled = user_dict.get("MERGE_ENABLED", False)
        # Check both if merge is available and enabled globally
        owner_merge_available = is_media_tool_enabled("merge")
        owner_merge_enabled = owner_merge_available and Config.MERGE_ENABLED

        if user_merge_enabled:
            merge_status = "✅ ON (User)"
        elif owner_merge_enabled:
            merge_status = "✅ ON (Global)"
        else:
            merge_status = "❌ OFF"

        # Check if convert is enabled for the user
        user_convert_enabled = user_dict.get("CONVERT_ENABLED", False)
        # Check both if convert is available and enabled globally
        owner_convert_available = is_media_tool_enabled("convert")
        owner_convert_enabled = owner_convert_available and Config.CONVERT_ENABLED

        if user_convert_enabled:
            convert_status = "✅ ON (User)"
        elif owner_convert_enabled:
            convert_status = "✅ ON (Global)"
        else:
            convert_status = "❌ OFF"

        # Get video convert enabled status
        video_convert_enabled = user_dict.get("CONVERT_VIDEO_ENABLED", False)
        owner_video_enabled = (
            hasattr(Config, "CONVERT_VIDEO_ENABLED") and Config.CONVERT_VIDEO_ENABLED
        )

        if "CONVERT_VIDEO_ENABLED" in user_dict:
            if video_convert_enabled:
                video_enabled_status = "✅ ON (User)"
            else:
                video_enabled_status = "❌ OFF (User)"
        elif owner_video_enabled:
            video_enabled_status = "✅ ON (Global)"
        else:
            video_enabled_status = "❌ OFF"

        # Get audio convert enabled status
        audio_convert_enabled = user_dict.get("CONVERT_AUDIO_ENABLED", False)
        owner_audio_enabled = (
            hasattr(Config, "CONVERT_AUDIO_ENABLED") and Config.CONVERT_AUDIO_ENABLED
        )

        if "CONVERT_AUDIO_ENABLED" in user_dict:
            if audio_convert_enabled:
                audio_enabled_status = "✅ ON (User)"
            else:
                audio_enabled_status = "❌ OFF (User)"
        elif owner_audio_enabled:
            audio_enabled_status = "✅ ON (Global)"
        else:
            audio_enabled_status = "❌ OFF"

        # Check if compression is enabled for the user
        user_compression_enabled = user_dict.get("COMPRESSION_ENABLED", False)
        # Check both if compression is available and enabled globally
        owner_compression_available = is_media_tool_enabled("compression")
        owner_compression_enabled = (
            owner_compression_available and Config.COMPRESSION_ENABLED
        )

        if user_compression_enabled:
            compression_status = "✅ ON (User)"
        elif owner_compression_enabled:
            compression_status = "✅ ON (Global)"
        else:
            compression_status = "❌ OFF"

        # Get video compression enabled status
        video_compression_enabled = user_dict.get("COMPRESSION_VIDEO_ENABLED", False)
        owner_video_compression_enabled = (
            hasattr(Config, "COMPRESSION_VIDEO_ENABLED")
            and Config.COMPRESSION_VIDEO_ENABLED
        )

        if "COMPRESSION_VIDEO_ENABLED" in user_dict:
            if video_compression_enabled:
                video_compression_status = "✅ ON (User)"
            else:
                video_compression_status = "❌ OFF (User)"
        elif owner_video_compression_enabled:
            video_compression_status = "✅ ON (Global)"
        else:
            video_compression_status = "❌ OFF"

        # Get audio compression enabled status
        audio_compression_enabled = user_dict.get("COMPRESSION_AUDIO_ENABLED", False)
        owner_audio_compression_enabled = (
            hasattr(Config, "COMPRESSION_AUDIO_ENABLED")
            and Config.COMPRESSION_AUDIO_ENABLED
        )

        if "COMPRESSION_AUDIO_ENABLED" in user_dict:
            if audio_compression_enabled:
                audio_compression_status = "✅ ON (User)"
            else:
                audio_compression_status = "❌ OFF (User)"
        elif owner_audio_compression_enabled:
            audio_compression_status = "✅ ON (Global)"
        else:
            audio_compression_status = "❌ OFF"

        # Check if trim is enabled for the user
        user_trim_enabled = user_dict.get("TRIM_ENABLED", False)
        # Check both if trim is available and enabled globally
        owner_trim_available = is_media_tool_enabled("trim")
        owner_trim_enabled = owner_trim_available and Config.TRIM_ENABLED

        if user_trim_enabled:
            trim_status = "✅ ON (User)"
        elif owner_trim_enabled:
            trim_status = "✅ ON (Global)"
        else:
            trim_status = "❌ OFF"

        # Get video trim enabled status
        video_trim_enabled = user_dict.get("TRIM_VIDEO_ENABLED", False)
        owner_video_trim_enabled = (
            hasattr(Config, "TRIM_VIDEO_ENABLED") and Config.TRIM_VIDEO_ENABLED
        )

        if "TRIM_VIDEO_ENABLED" in user_dict:
            if video_trim_enabled:
                video_trim_status = "✅ ON (User)"
            else:
                video_trim_status = "❌ OFF (User)"
        elif owner_video_trim_enabled:
            video_trim_status = "✅ ON (Global)"
        else:
            video_trim_status = "❌ OFF"

        # Get audio trim enabled status
        audio_trim_enabled = user_dict.get("TRIM_AUDIO_ENABLED", False)
        owner_audio_trim_enabled = (
            hasattr(Config, "TRIM_AUDIO_ENABLED") and Config.TRIM_AUDIO_ENABLED
        )

        if "TRIM_AUDIO_ENABLED" in user_dict:
            if audio_trim_enabled:
                audio_trim_status = "✅ ON (User)"
            else:
                audio_trim_status = "❌ OFF (User)"
        elif owner_audio_trim_enabled:
            audio_trim_status = "✅ ON (Global)"
        else:
            audio_trim_status = "❌ OFF"

        # Get extract status
        extract_enabled = user_dict.get("EXTRACT_ENABLED", False)
        # Check both if extract is available and enabled globally
        owner_extract_available = is_media_tool_enabled("extract")
        owner_extract_enabled = owner_extract_available and Config.EXTRACT_ENABLED

        if extract_enabled:
            extract_status = "✅ ON (User)"
        elif owner_extract_enabled:
            extract_status = "✅ ON (Global)"
        else:
            extract_status = "❌ OFF"

        # Get extract video status
        video_extract_enabled = user_dict.get("EXTRACT_VIDEO_ENABLED", False)
        owner_video_extract_enabled = (
            hasattr(Config, "EXTRACT_VIDEO_ENABLED") and Config.EXTRACT_VIDEO_ENABLED
        )

        if "EXTRACT_VIDEO_ENABLED" in user_dict:
            if video_extract_enabled:
                video_extract_status = "✅ ON (User)"
            else:
                video_extract_status = "❌ OFF (User)"
        elif owner_video_extract_enabled:
            video_extract_status = "✅ ON (Global)"
        else:
            video_extract_status = "❌ OFF"

        # Get extract audio status
        audio_extract_enabled = user_dict.get("EXTRACT_AUDIO_ENABLED", False)
        owner_audio_extract_enabled = (
            hasattr(Config, "EXTRACT_AUDIO_ENABLED") and Config.EXTRACT_AUDIO_ENABLED
        )

        if "EXTRACT_AUDIO_ENABLED" in user_dict:
            if audio_extract_enabled:
                audio_extract_status = "✅ ON (User)"
            else:
                audio_extract_status = "❌ OFF (User)"
        elif owner_audio_extract_enabled:
            audio_extract_status = "✅ ON (Global)"
        else:
            audio_extract_status = "❌ OFF"

        # Get add status
        add_enabled = user_dict.get("ADD_ENABLED", False)
        # Check both if add is available and enabled globally
        owner_add_available = is_media_tool_enabled("add")
        owner_add_enabled = owner_add_available and Config.ADD_ENABLED

        if add_enabled:
            add_status = "✅ ON (User)"
        elif owner_add_enabled:
            add_status = "✅ ON (Global)"
        else:
            add_status = "❌ OFF"

        # Get add video status
        video_add_enabled = user_dict.get("ADD_VIDEO_ENABLED", False)
        owner_video_add_enabled = (
            hasattr(Config, "ADD_VIDEO_ENABLED") and Config.ADD_VIDEO_ENABLED
        )

        if "ADD_VIDEO_ENABLED" in user_dict:
            if video_add_enabled:
                video_add_status = "✅ ON (User)"
            else:
                video_add_status = "❌ OFF (User)"
        elif owner_video_add_enabled:
            video_add_status = "✅ ON (Global)"
        else:
            video_add_status = "❌ OFF"

        # Get add audio status
        audio_add_enabled = user_dict.get("ADD_AUDIO_ENABLED", False)
        owner_audio_add_enabled = (
            hasattr(Config, "ADD_AUDIO_ENABLED") and Config.ADD_AUDIO_ENABLED
        )

        if "ADD_AUDIO_ENABLED" in user_dict:
            if audio_add_enabled:
                audio_add_status = "✅ ON (User)"
            else:
                audio_add_status = "❌ OFF (User)"
        elif owner_audio_add_enabled:
            audio_add_status = "✅ ON (Global)"
        else:
            audio_add_status = "❌ OFF"

        # Get remove status
        remove_enabled = user_dict.get("REMOVE_ENABLED", False)
        # Check both if remove is available and enabled globally
        owner_remove_available = is_media_tool_enabled("remove")
        owner_remove_enabled = owner_remove_available and Config.REMOVE_ENABLED

        if remove_enabled:
            remove_status = "✅ ON (User)"
        elif owner_remove_enabled:
            remove_status = "✅ ON (Global)"
        else:
            remove_status = "❌ OFF"

        # Get remove video status
        video_remove_enabled = user_dict.get("REMOVE_VIDEO_ENABLED", False)
        owner_video_remove_enabled = (
            hasattr(Config, "REMOVE_VIDEO_ENABLED") and Config.REMOVE_VIDEO_ENABLED
        )

        if "REMOVE_VIDEO_ENABLED" in user_dict:
            if video_remove_enabled:
                video_remove_status = "✅ ON (User)"
            else:
                video_remove_status = "❌ OFF (User)"
        elif owner_video_remove_enabled:
            video_remove_status = "✅ ON (Global)"
        else:
            video_remove_status = "❌ OFF"

        # Get remove audio status
        audio_remove_enabled = user_dict.get("REMOVE_AUDIO_ENABLED", False)
        owner_audio_remove_enabled = (
            hasattr(Config, "REMOVE_AUDIO_ENABLED") and Config.REMOVE_AUDIO_ENABLED
        )

        if "REMOVE_AUDIO_ENABLED" in user_dict:
            if audio_remove_enabled:
                audio_remove_status = "✅ ON (User)"
            else:
                audio_remove_status = "❌ OFF (User)"
        elif owner_audio_remove_enabled:
            audio_remove_status = "✅ ON (Global)"
        else:
            audio_remove_status = "❌ OFF"

        text = f"""⌬ <b>Media Tools Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Watermark</b> → {watermark_status}
┠ <b>Watermark Text</b> → <code>{watermark_text}</code>
┃
┠ <b>Merge</b> → {merge_status}
┃
┠ <b>Convert</b> → {convert_status}
┠ <b>Video Convert</b> → {video_enabled_status}
┠ <b>Audio Convert</b> → {audio_enabled_status}
┃
┠ <b>Compression</b> → {compression_status}
┠ <b>Video Compression</b> → {video_compression_status}
┠ <b>Audio Compression</b> → {audio_compression_status}
┃
┠ <b>Trim</b> → {trim_status}
┠ <b>Video Trim</b> → {video_trim_status}
┠ <b>Audio Trim</b> → {audio_trim_status}
┃
┠ <b>Extract</b> → {extract_status}
┠ <b>Video Extract</b> → {video_extract_status}
┠ <b>Audio Extract</b> → {audio_extract_status}
┃
┠ <b>Remove</b> → {remove_status}
┠ <b>Video Remove</b> → {video_remove_status}
┠ <b>Audio Remove</b> → {audio_remove_status}
┃
┠ <b>Add</b> → {add_status}
┠ <b>Video Add</b> → {video_add_status}
┠ <b>Audio Add</b> → {audio_add_status}
┃
┖ <b>Priority</b> → {user_dict.get("MEDIA_TOOLS_PRIORITY", "Default Order")}"""

    elif stype == "watermark":
        # Watermark settings menu
        watermark_enabled = user_dict.get("WATERMARK_ENABLED", False)
        buttons.data_button(
            f"Watermark: {'✅ ON' if watermark_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog WATERMARK_ENABLED {'f' if watermark_enabled else 't'}",
        )
        buttons.data_button("Configure ⚙️", f"mediatools {user_id} watermark_config")

        # Add Image Watermark button
        image_watermark_enabled = user_dict.get("IMAGE_WATERMARK_ENABLED", False)
        buttons.data_button(
            f"Image Watermark: {'✅ ON' if image_watermark_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog IMAGE_WATERMARK_ENABLED {'f' if image_watermark_enabled else 't'}",
        )

        # Add Upload Image Watermark button (styled like thumbnail upload in leech settings)
        buttons.data_button(
            "Upload Image 🖼️",
            f"mediatools {user_id} upload_image",
        )

        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu WATERMARK_PRIORITY"
        )

        # Add RO toggle button (Remove Original)
        # Use global setting as fallback when user hasn't set it explicitly
        remove_original = user_dict.get(
            "WATERMARK_REMOVE_ORIGINAL", Config.WATERMARK_REMOVE_ORIGINAL
        )
        buttons.data_button(
            f"RO: {'✅ ON' if remove_original else '❌ OFF'}",
            f"mediatools {user_id} tog WATERMARK_REMOVE_ORIGINAL {'f' if remove_original else 't'}",
        )

        # Threading toggle and thread number button removed for users

        buttons.data_button("Reset", f"mediatools {user_id} reset_watermark")
        buttons.data_button("Remove", f"mediatools {user_id} remove_watermark")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get watermark text based on priority
        user_has_text = "WATERMARK_KEY" in user_dict and user_dict["WATERMARK_KEY"]
        owner_has_text = Config.WATERMARK_KEY

        if user_has_text:
            watermark_text = f"{user_dict['WATERMARK_KEY']} (User)"
        elif (watermark_enabled and owner_has_text) or (
            Config.WATERMARK_ENABLED and owner_has_text
        ):
            watermark_text = f"{Config.WATERMARK_KEY} (Global)"
        else:
            watermark_text = "None"

        # Get watermark position based on priority
        user_has_position = (
            "WATERMARK_POSITION" in user_dict and user_dict["WATERMARK_POSITION"]
        )
        owner_has_position = Config.WATERMARK_POSITION

        if user_has_position:
            watermark_position = f"{user_dict['WATERMARK_POSITION']} (User)"
        elif (watermark_enabled and owner_has_position) or (
            Config.WATERMARK_ENABLED and owner_has_position
        ):
            watermark_position = f"{Config.WATERMARK_POSITION} (Global)"
        else:
            watermark_position = "top_left (Default)"

        # Get watermark size based on priority
        user_has_size = "WATERMARK_SIZE" in user_dict and user_dict["WATERMARK_SIZE"]
        owner_has_size = Config.WATERMARK_SIZE

        if user_has_size:
            watermark_size = f"{user_dict['WATERMARK_SIZE']} (User)"
        elif (watermark_enabled and owner_has_size) or (
            Config.WATERMARK_ENABLED and owner_has_size
        ):
            watermark_size = f"{Config.WATERMARK_SIZE} (Global)"
        else:
            watermark_size = "20 (Default)"

        # Get watermark color based on priority
        user_has_color = (
            "WATERMARK_COLOR" in user_dict and user_dict["WATERMARK_COLOR"]
        )
        owner_has_color = Config.WATERMARK_COLOR

        if user_has_color:
            watermark_color = f"{user_dict['WATERMARK_COLOR']} (User)"
        elif (watermark_enabled and owner_has_color) or (
            Config.WATERMARK_ENABLED and owner_has_color
        ):
            watermark_color = f"{Config.WATERMARK_COLOR} (Global)"
        else:
            watermark_color = "white (Default)"

        # Get watermark font based on priority
        user_has_font = "WATERMARK_FONT" in user_dict and user_dict["WATERMARK_FONT"]
        owner_has_font = Config.WATERMARK_FONT

        if user_has_font:
            watermark_font = f"{user_dict['WATERMARK_FONT']} (User)"
        elif (watermark_enabled and owner_has_font) or (
            Config.WATERMARK_ENABLED and owner_has_font
        ):
            watermark_font = f"{Config.WATERMARK_FONT} (Global)"
        else:
            watermark_font = "default.otf (Default)"

        # Get watermark threading status
        user_has_threading = "WATERMARK_THREADING" in user_dict
        if user_has_threading:
            threading_status = (
                "✅ ON (User)"
                if user_dict["WATERMARK_THREADING"]
                else "❌ OFF (User)"
            )
        elif Config.WATERMARK_THREADING:
            threading_status = "✅ ON (Global)"
        else:
            threading_status = "❌ OFF"

        # Get thread number
        user_has_thread_number = (
            "WATERMARK_THREAD_NUMBER" in user_dict
            and user_dict["WATERMARK_THREAD_NUMBER"]
        )
        if user_has_thread_number:
            thread_number = f"{user_dict['WATERMARK_THREAD_NUMBER']} (User)"
        elif Config.WATERMARK_THREAD_NUMBER:
            thread_number = f"{Config.WATERMARK_THREAD_NUMBER} (Global)"
        else:
            thread_number = "4 (Default)"

        # Fast mode has been removed

        # Quality is now controlled by WATERMARK_QUALITY parameter
        maintain_quality_status = "❌ Removed (Use quality parameter instead)"

        # Get opacity value
        user_has_opacity = (
            "WATERMARK_OPACITY" in user_dict
            and user_dict["WATERMARK_OPACITY"] is not None
        )
        if user_has_opacity:
            opacity_value = f"{user_dict['WATERMARK_OPACITY']} (User)"
        elif Config.WATERMARK_OPACITY != 1.0:
            opacity_value = f"{Config.WATERMARK_OPACITY} (Global)"
        else:
            opacity_value = "1.0 (Default)"

        # Get watermark remove original status
        user_has_remove_original = "WATERMARK_REMOVE_ORIGINAL" in user_dict
        if user_has_remove_original:
            remove_original_status = (
                "✅ ON (User)"
                if user_dict["WATERMARK_REMOVE_ORIGINAL"]
                else "❌ OFF (User)"
            )
        elif Config.WATERMARK_REMOVE_ORIGINAL:
            remove_original_status = "✅ ON (Global)"
        else:
            remove_original_status = "❌ OFF"

        # Get image watermark settings
        image_watermark_enabled = user_dict.get("IMAGE_WATERMARK_ENABLED", False)

        # Get image watermark path - first check user_dict for IMAGE_WATERMARK_PATH
        # This ensures we show the correct status immediately after upload
        if (
            "IMAGE_WATERMARK_PATH" in user_dict
            and user_dict["IMAGE_WATERMARK_PATH"] == "Added"
        ):
            image_path = "Added (User)"
        else:
            # If not in user_dict, check the database
            user_doc = await database.get_user_doc(user_id)
            user_has_image = user_doc and "IMAGE_WATERMARK" in user_doc

            # Check if owner has an image watermark in the database
            owner_has_image = False
            if hasattr(Config, "OWNER_ID"):
                owner_doc = await database.get_user_doc(Config.OWNER_ID)
                owner_has_image = owner_doc and "IMAGE_WATERMARK" in owner_doc

            if user_has_image:
                image_path = "Added (User)"
                # Update user_dict to ensure consistency
                if user_id in user_data:
                    user_data[user_id]["IMAGE_WATERMARK_PATH"] = "Added"
            elif owner_has_image:
                image_path = "Added (Global)"
            else:
                image_path = "None"

        # Get image watermark scale
        user_has_image_scale = (
            "IMAGE_WATERMARK_SCALE" in user_dict
            and user_dict["IMAGE_WATERMARK_SCALE"]
        )
        owner_has_image_scale = Config.IMAGE_WATERMARK_SCALE

        if user_has_image_scale:
            image_scale = f"{user_dict['IMAGE_WATERMARK_SCALE']} (User)"
        elif (image_watermark_enabled and owner_has_image_scale) or (
            Config.IMAGE_WATERMARK_ENABLED and owner_has_image_scale
        ):
            image_scale = f"{Config.IMAGE_WATERMARK_SCALE} (Global)"
        else:
            image_scale = "10 (Default)"

        # Get image watermark position
        user_has_image_position = (
            "IMAGE_WATERMARK_POSITION" in user_dict
            and user_dict["IMAGE_WATERMARK_POSITION"]
        )
        owner_has_image_position = Config.IMAGE_WATERMARK_POSITION

        if user_has_image_position:
            image_position = f"{user_dict['IMAGE_WATERMARK_POSITION']} (User)"
        elif (image_watermark_enabled and owner_has_image_position) or (
            Config.IMAGE_WATERMARK_ENABLED and owner_has_image_position
        ):
            image_position = f"{Config.IMAGE_WATERMARK_POSITION} (Global)"
        else:
            image_position = "bottom_right (Default)"

        # Get image watermark opacity
        user_has_image_opacity = (
            "IMAGE_WATERMARK_OPACITY" in user_dict
            and user_dict["IMAGE_WATERMARK_OPACITY"] is not None
        )
        owner_has_image_opacity = Config.IMAGE_WATERMARK_OPACITY

        if user_has_image_opacity:
            image_opacity = f"{user_dict['IMAGE_WATERMARK_OPACITY']} (User)"
        elif (image_watermark_enabled and owner_has_image_opacity) or (
            Config.IMAGE_WATERMARK_ENABLED and owner_has_image_opacity
        ):
            image_opacity = f"{Config.IMAGE_WATERMARK_OPACITY} (Global)"
        else:
            image_opacity = "1.0 (Default)"

        text = f"""⌬ <b>Watermark Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Text Watermark</b> → {"✅ ON" if watermark_enabled else "❌ OFF"}
┠ <b>Text</b> → <code>{watermark_text}</code>
┠ <b>Position</b> → <code>{watermark_position}</code>
┠ <b>Size</b> → <code>{watermark_size}</code>
┠ <b>Color</b> → <code>{watermark_color}</code>
┠ <b>Font</b> → <code>{watermark_font}</code>
┠ <b>Opacity</b> → <code>{opacity_value}</code>
┃
┠ <b>Image Watermark</b> → {"✅ ON" if image_watermark_enabled else "❌ OFF"}
┠ <b>Image Path</b> → <code>{image_path}</code>
┠ <b>Image Scale</b> → <code>{image_scale}</code>
┠ <b>Image Position</b> → <code>{image_position}</code>
┠ <b>Image Opacity</b> → <code>{image_opacity}</code>
┃
┖ <b>RO</b> → {remove_original_status}

<b>Usage:</b>
• Enable watermark to add text or image to media files
• Configure text watermark with position, size, color, etc.
• Upload an image to use as a watermark
• RO (Remove Original) deletes original files after watermarking
• Example: <code>/leech https://example.com/file.mp4 -watermark</code>
• Example: <code>/leech https://example.com/file.jpg -watermark -del</code>"""

    elif stype.startswith("watermark_config"):
        # Get all watermark settings organized by category
        visual_settings = [
            "WATERMARK_KEY",
            "WATERMARK_POSITION",
            "WATERMARK_SIZE",
            "WATERMARK_COLOR",
            "WATERMARK_FONT",
            "WATERMARK_OPACITY",
        ]

        performance_settings = [
            "WATERMARK_QUALITY",  # Numerical value instead of toggle
            "WATERMARK_SPEED",  # Numerical value instead of toggle
        ]

        audio_settings = [
            "AUDIO_WATERMARK_INTERVAL",  # New setting
            "AUDIO_WATERMARK_VOLUME",  # Keeping this as it's useful
        ]

        subtitle_settings = [
            "SUBTITLE_WATERMARK_INTERVAL",  # New setting
            "SUBTITLE_WATERMARK_STYLE",  # Keeping this as it's useful
        ]

        # Add image watermark settings
        image_settings = [
            "IMAGE_WATERMARK_SCALE",
            "IMAGE_WATERMARK_POSITION",
            "IMAGE_WATERMARK_OPACITY",
        ]

        # Combine all settings in a logical order
        watermark_settings = (
            visual_settings
            + performance_settings
            + image_settings
            + audio_settings
            + subtitle_settings
        )

        # Pagination setup
        global watermark_config_page

        # If a specific page is requested in the stype parameter, use that
        if len(stype.split()) > 1:
            try:
                page_no = int(stype.split()[1])
                # Update the global variable
                watermark_config_page = page_no
            except (ValueError, IndexError):
                # Use the global variable
                page_no = watermark_config_page
        else:
            # Use the global variable if no page is specified
            page_no = watermark_config_page

        # 5 rows per page, 2 columns = 10 items per page
        items_per_page = 10  # 5 rows * 2 columns
        total_pages = (
            len(watermark_settings) + items_per_page - 1
        ) // items_per_page

        # Ensure page_no is valid
        if page_no >= total_pages:
            page_no = 0
            watermark_config_page = 0  # Update global variable
        elif page_no < 0:
            page_no = total_pages - 1
            watermark_config_page = total_pages - 1  # Update global variable

        # Get settings for current page
        current_page_settings = watermark_settings[
            page_no * items_per_page : (page_no * items_per_page) + items_per_page
        ]

        # Add buttons for each setting on current page
        for setting in current_page_settings:
            display_name = (
                setting.replace("WATERMARK_", "")
                .replace("AUDIO_WATERMARK_", "AUDIO ")
                .replace("SUBTITLE_WATERMARK_", "SUBTITLE ")
                .replace("_", " ")
                .title()
            )
            buttons.data_button(display_name, f"mediatools {user_id} menu {setting}")

        # Add action buttons in a separate row
        # Back button should go to the watermark menu
        buttons.data_button(
            "Back",
            f"mediatools {user_id} watermark",
            "footer",
        )

        # Store the current page number for returning to it later
        handler_dict[f"{user_id}_watermark_page"] = page_no
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")

        # Add pagination buttons in a separate row below action buttons
        if total_pages > 1:
            for i in range(total_pages):
                # Make the current page button different
                if i == page_no:
                    buttons.data_button(
                        f"[{i + 1}]",
                        f"mediatools {user_id} watermark_config {i}",
                        "page",
                    )
                else:
                    buttons.data_button(
                        str(i + 1),
                        f"mediatools {user_id} watermark_config {i}",
                        "page",
                    )

            # Build the menu with 2 columns for settings, 4 columns for action buttons, and 8 columns for pagination
            btns = buttons.build_menu(2, 8, 4, 8)

        # Get watermark text based on priority
        watermark_enabled = user_dict.get("WATERMARK_ENABLED", False)
        user_has_text = "WATERMARK_KEY" in user_dict and user_dict["WATERMARK_KEY"]
        owner_has_text = Config.WATERMARK_KEY

        if user_has_text:
            watermark_text = f"{user_dict['WATERMARK_KEY']} (User)"
        elif (watermark_enabled and owner_has_text) or (
            Config.WATERMARK_ENABLED and owner_has_text
        ):
            watermark_text = f"{Config.WATERMARK_KEY} (Global)"
        else:
            watermark_text = "None"

        # Get watermark position based on priority
        user_has_position = (
            "WATERMARK_POSITION" in user_dict and user_dict["WATERMARK_POSITION"]
        )
        owner_has_position = Config.WATERMARK_POSITION

        if user_has_position:
            watermark_position = f"{user_dict['WATERMARK_POSITION']} (User)"
        elif (watermark_enabled and owner_has_position) or (
            Config.WATERMARK_ENABLED and owner_has_position
        ):
            watermark_position = f"{Config.WATERMARK_POSITION} (Global)"
        else:
            watermark_position = "top_left (Default)"

        # Get watermark size based on priority
        user_has_size = "WATERMARK_SIZE" in user_dict and user_dict["WATERMARK_SIZE"]
        owner_has_size = Config.WATERMARK_SIZE

        if user_has_size:
            watermark_size = f"{user_dict['WATERMARK_SIZE']} (User)"
        elif (watermark_enabled and owner_has_size) or (
            Config.WATERMARK_ENABLED and owner_has_size
        ):
            watermark_size = f"{Config.WATERMARK_SIZE} (Global)"
        else:
            watermark_size = "20 (Default)"

        # Get watermark color based on priority
        user_has_color = (
            "WATERMARK_COLOR" in user_dict and user_dict["WATERMARK_COLOR"]
        )
        owner_has_color = Config.WATERMARK_COLOR

        if user_has_color:
            watermark_color = f"{user_dict['WATERMARK_COLOR']} (User)"
        elif (watermark_enabled and owner_has_color) or (
            Config.WATERMARK_ENABLED and owner_has_color
        ):
            watermark_color = f"{Config.WATERMARK_COLOR} (Global)"
        else:
            watermark_color = "white (Default)"

        # Get watermark font based on priority
        user_has_font = "WATERMARK_FONT" in user_dict and user_dict["WATERMARK_FONT"]
        owner_has_font = Config.WATERMARK_FONT

        if user_has_font:
            watermark_font = f"{user_dict['WATERMARK_FONT']} (User)"
        elif (watermark_enabled and owner_has_font) or (
            Config.WATERMARK_ENABLED and owner_has_font
        ):
            watermark_font = f"{Config.WATERMARK_FONT} (Global)"
        else:
            watermark_font = "default.otf (Default)"

        # Get watermark threading status
        user_has_threading = "WATERMARK_THREADING" in user_dict
        if user_has_threading:
            threading_status = (
                "✅ Enabled (User)"
                if user_dict["WATERMARK_THREADING"]
                else "❌ Disabled (User)"
            )
        elif Config.WATERMARK_THREADING:
            threading_status = "✅ Enabled (Global)"
        else:
            threading_status = "❌ Disabled"

        # Get thread number
        user_has_thread_number = (
            "WATERMARK_THREAD_NUMBER" in user_dict
            and user_dict["WATERMARK_THREAD_NUMBER"]
        )
        if user_has_thread_number:
            thread_number = f"{user_dict['WATERMARK_THREAD_NUMBER']} (User)"
        elif Config.WATERMARK_THREAD_NUMBER:
            thread_number = f"{Config.WATERMARK_THREAD_NUMBER} (Global)"
        else:
            thread_number = "4 (Default)"

        # Fast mode and quality have been removed - no need to show status

        # Get opacity value
        user_has_opacity = (
            "WATERMARK_OPACITY" in user_dict
            and user_dict["WATERMARK_OPACITY"] is not None
        )
        if user_has_opacity:
            opacity_value = f"{user_dict['WATERMARK_OPACITY']} (User)"
        elif Config.WATERMARK_OPACITY != 1.0:
            opacity_value = f"{Config.WATERMARK_OPACITY} (Global)"
        else:
            opacity_value = "1.0 (Default)"

        # Get watermark remove original status
        user_has_remove_original = "WATERMARK_REMOVE_ORIGINAL" in user_dict
        if user_has_remove_original:
            remove_original_status = (
                "✅ Enabled (User)"
                if user_dict["WATERMARK_REMOVE_ORIGINAL"]
                else "❌ Disabled (User)"
            )
        elif Config.WATERMARK_REMOVE_ORIGINAL:
            remove_original_status = "✅ Enabled (Global)"
        else:
            remove_original_status = "❌ Disabled"

        # Get quality and speed values if they exist
        user_has_quality = (
            "WATERMARK_QUALITY" in user_dict and user_dict["WATERMARK_QUALITY"]
        )
        if user_has_quality:
            quality_value = f"{user_dict['WATERMARK_QUALITY']} (User)"
        else:
            quality_value = "None (Default)"

        user_has_speed = (
            "WATERMARK_SPEED" in user_dict and user_dict["WATERMARK_SPEED"]
        )
        if user_has_speed:
            speed_value = f"{user_dict['WATERMARK_SPEED']} (User)"
        else:
            speed_value = "None (Default)"

        # Get audio and subtitle interval values if they exist
        user_has_audio_interval = (
            "AUDIO_WATERMARK_INTERVAL" in user_dict
            and user_dict["AUDIO_WATERMARK_INTERVAL"]
        )
        if user_has_audio_interval:
            audio_interval = f"{user_dict['AUDIO_WATERMARK_INTERVAL']} (User)"
        else:
            audio_interval = "None (Default)"

        user_has_subtitle_interval = (
            "SUBTITLE_WATERMARK_INTERVAL" in user_dict
            and user_dict["SUBTITLE_WATERMARK_INTERVAL"]
        )
        if user_has_subtitle_interval:
            subtitle_interval = f"{user_dict['SUBTITLE_WATERMARK_INTERVAL']} (User)"
        else:
            subtitle_interval = "None (Default)"

        # Get page info for message
        page_info = ""
        if total_pages > 1:
            page_info = f"\n\n<b>Page:</b> {page_no + 1}/{total_pages}"

        # Determine which category is shown on the current page
        categories = []
        if any(setting in visual_settings for setting in current_page_settings):
            categories.append("Text Watermark")
        if any(setting in performance_settings for setting in current_page_settings):
            categories.append("Performance")
        if any(setting in image_settings for setting in current_page_settings):
            categories.append("Image Watermark")
        if any(setting in audio_settings for setting in current_page_settings):
            categories.append("Audio")
        if any(setting in subtitle_settings for setting in current_page_settings):
            categories.append("Subtitle")

        category_text = ", ".join(categories)

        # Get image watermark settings
        image_watermark_enabled = user_dict.get("IMAGE_WATERMARK_ENABLED", False)

        # Get image watermark path - first check user_dict for IMAGE_WATERMARK_PATH
        # This ensures we show the correct status immediately after upload
        if (
            "IMAGE_WATERMARK_PATH" in user_dict
            and user_dict["IMAGE_WATERMARK_PATH"] == "Added"
        ):
            image_path = "Added (User)"
        else:
            # If not in user_dict, check the database
            user_doc = await database.get_user_doc(user_id)
            user_has_image = user_doc and "IMAGE_WATERMARK" in user_doc

            # Check if owner has an image watermark in the database
            owner_has_image = False
            if hasattr(Config, "OWNER_ID"):
                owner_doc = await database.get_user_doc(Config.OWNER_ID)
                owner_has_image = owner_doc and "IMAGE_WATERMARK" in owner_doc

            if user_has_image:
                image_path = "Added (User)"
                # Update user_dict to ensure consistency
                if user_id in user_data:
                    user_data[user_id]["IMAGE_WATERMARK_PATH"] = "Added"
            elif owner_has_image:
                image_path = "Added (Global)"
            else:
                image_path = "None"

        # Get image watermark scale
        user_has_image_scale = (
            "IMAGE_WATERMARK_SCALE" in user_dict
            and user_dict["IMAGE_WATERMARK_SCALE"]
        )
        owner_has_image_scale = Config.IMAGE_WATERMARK_SCALE

        if user_has_image_scale:
            image_scale = f"{user_dict['IMAGE_WATERMARK_SCALE']} (User)"
        elif (image_watermark_enabled and owner_has_image_scale) or (
            Config.IMAGE_WATERMARK_ENABLED and owner_has_image_scale
        ):
            image_scale = f"{Config.IMAGE_WATERMARK_SCALE} (Global)"
        else:
            image_scale = "10 (Default)"

        # Get image watermark position
        user_has_image_position = (
            "IMAGE_WATERMARK_POSITION" in user_dict
            and user_dict["IMAGE_WATERMARK_POSITION"]
        )
        owner_has_image_position = Config.IMAGE_WATERMARK_POSITION

        if user_has_image_position:
            image_position = f"{user_dict['IMAGE_WATERMARK_POSITION']} (User)"
        elif (image_watermark_enabled and owner_has_image_position) or (
            Config.IMAGE_WATERMARK_ENABLED and owner_has_image_position
        ):
            image_position = f"{Config.IMAGE_WATERMARK_POSITION} (Global)"
        else:
            image_position = "bottom_right (Default)"

        # Get image watermark opacity
        user_has_image_opacity = (
            "IMAGE_WATERMARK_OPACITY" in user_dict
            and user_dict["IMAGE_WATERMARK_OPACITY"] is not None
        )
        owner_has_image_opacity = Config.IMAGE_WATERMARK_OPACITY

        if user_has_image_opacity:
            image_opacity = f"{user_dict['IMAGE_WATERMARK_OPACITY']} (User)"
        elif (image_watermark_enabled and owner_has_image_opacity) or (
            Config.IMAGE_WATERMARK_ENABLED and owner_has_image_opacity
        ):
            image_opacity = f"{Config.IMAGE_WATERMARK_OPACITY} (Global)"
        else:
            image_opacity = "1.0 (Default)"

        text = f"""⌬ <b>Watermark Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Select a setting to configure</b>
┃
┠ <b>Text Watermark Settings:</b>
┠ <b>Text</b> → <code>{watermark_text}</code>
┠ <b>Position</b> → <code>{watermark_position}</code>
┠ <b>Size</b> → <code>{watermark_size}</code>
┠ <b>Color</b> → <code>{watermark_color}</code>
┠ <b>Font</b> → <code>{watermark_font}</code>
┠ <b>Opacity</b> → <code>{opacity_value}</code>
┃
┠ <b>Performance Settings:</b>
┠ <b>Quality</b> → <code>{quality_value}</code>
┠ <b>Speed</b> → <code>{speed_value}</code>
┃
┠ <b>Image Watermark Settings:</b>
┠ <b>Image Path</b> → <code>{image_path}</code>
┠ <b>Image Scale</b> → <code>{image_scale}</code>
┠ <b>Image Position</b> → <code>{image_position}</code>
┠ <b>Image Opacity</b> → <code>{image_opacity}</code>
┃
┠ <b>Audio Settings:</b>
┠ <b>Audio Interval</b> → <code>{audio_interval}</code>
┠ <b>Audio Volume</b> → <code>{user_dict.get("AUDIO_WATERMARK_VOLUME", "None (Default)")}</code>
┃
┠ <b>Subtitle Settings:</b>
┠ <b>Subtitle Interval</b> → <code>{subtitle_interval}</code>
┠ <b>Subtitle Style</b> → <code>{user_dict.get("SUBTITLE_WATERMARK_STYLE", "None (Default)")}</code>
┃
┖ <b>Current page shows:</b> {category_text} settings{page_info}"""

    elif stype == "merge":
        # Merge settings menu
        merge_enabled = user_dict.get("MERGE_ENABLED", False)
        buttons.data_button(
            f"Merge: {'✅ ON' if merge_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog MERGE_ENABLED {'f' if merge_enabled else 't'}",
        )

        # Add Concat Demuxer/Filter Complex toggle
        concat_enabled = user_dict.get("CONCAT_DEMUXER_ENABLED", True)
        filter_enabled = user_dict.get("FILTER_COMPLEX_ENABLED", True)

        # Show a single toggle button that cycles through the states with more concise format
        if concat_enabled and filter_enabled:
            # Both enabled - next state is concat only
            buttons.data_button(
                "C-ON | F-ON",
                f"mediatools {user_id} toggle_concat_filter concat",
            )
        elif concat_enabled and not filter_enabled:
            # Only concat enabled - next state is filter only
            buttons.data_button(
                "C-ON | F-OFF",
                f"mediatools {user_id} toggle_concat_filter filter",
            )
        elif not concat_enabled and filter_enabled:
            # Only filter enabled - next state is both enabled
            buttons.data_button(
                "C-OFF | F-ON",
                f"mediatools {user_id} toggle_concat_filter both",
            )
        else:
            # Both disabled - next state is both enabled
            buttons.data_button(
                "C-OFF | F-OFF",
                f"mediatools {user_id} toggle_concat_filter both",
            )

        buttons.data_button("Configure", f"mediatools {user_id} merge_config")
        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu MERGE_PRIORITY"
        )

        # Add RO toggle button (Remove Original)
        # Use global setting as fallback when user hasn't set it explicitly
        remove_original = user_dict.get(
            "MERGE_REMOVE_ORIGINAL", Config.MERGE_REMOVE_ORIGINAL
        )
        buttons.data_button(
            f"RO: {'✅ ON' if remove_original else '❌ OFF'}",
            f"mediatools {user_id} tog MERGE_REMOVE_ORIGINAL {'f' if remove_original else 't'}",
        )

        buttons.data_button("Reset", f"mediatools {user_id} reset_merge")
        buttons.data_button("Remove", f"mediatools {user_id} remove_merge")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get concat demuxer status
        user_has_concat = "CONCAT_DEMUXER_ENABLED" in user_dict
        if user_has_concat:
            concat_status = (
                "✅ ON (User)"
                if user_dict["CONCAT_DEMUXER_ENABLED"]
                else "❌ OFF (User)"
            )
        elif Config.CONCAT_DEMUXER_ENABLED:
            concat_status = "✅ ON (Global)"
        else:
            concat_status = "❌ OFF"

        # Get filter complex status
        user_has_filter = "FILTER_COMPLEX_ENABLED" in user_dict
        if user_has_filter:
            filter_status = (
                "✅ ON (User)"
                if user_dict["FILTER_COMPLEX_ENABLED"]
                else "❌ OFF (User)"
            )
        elif Config.FILTER_COMPLEX_ENABLED:
            filter_status = "✅ ON (Global)"
        else:
            filter_status = "❌ OFF"

        # Get output formats
        user_has_video_format = (
            "MERGE_OUTPUT_FORMAT_VIDEO" in user_dict
            and user_dict["MERGE_OUTPUT_FORMAT_VIDEO"]
        )
        user_has_audio_format = (
            "MERGE_OUTPUT_FORMAT_AUDIO" in user_dict
            and user_dict["MERGE_OUTPUT_FORMAT_AUDIO"]
        )

        if user_has_video_format:
            video_format = f"{user_dict['MERGE_OUTPUT_FORMAT_VIDEO']} (User)"
        elif Config.MERGE_OUTPUT_FORMAT_VIDEO:
            video_format = f"{Config.MERGE_OUTPUT_FORMAT_VIDEO} (Global)"
        else:
            video_format = "mkv (Default)"

        if user_has_audio_format:
            audio_format = f"{user_dict['MERGE_OUTPUT_FORMAT_AUDIO']} (User)"
        elif Config.MERGE_OUTPUT_FORMAT_AUDIO:
            audio_format = f"{Config.MERGE_OUTPUT_FORMAT_AUDIO} (Global)"
        else:
            audio_format = "mp3 (Default)"

        # Get threading status
        user_has_threading = "MERGE_THREADING" in user_dict
        if user_has_threading:
            threading_status = (
                "✅ ON (User)" if user_dict["MERGE_THREADING"] else "❌ OFF (User)"
            )
        elif Config.MERGE_THREADING:
            threading_status = "✅ ON (Global)"
        else:
            threading_status = "❌ OFF"

        # Get thread number
        user_has_thread_number = (
            "MERGE_THREAD_NUMBER" in user_dict and user_dict["MERGE_THREAD_NUMBER"]
        )
        if user_has_thread_number:
            thread_number = f"{user_dict['MERGE_THREAD_NUMBER']} (User)"
        elif Config.MERGE_THREAD_NUMBER:
            thread_number = f"{Config.MERGE_THREAD_NUMBER} (Global)"
        else:
            thread_number = "4 (Default)"

        # Get remove original status
        user_has_remove_original = "MERGE_REMOVE_ORIGINAL" in user_dict
        if user_has_remove_original:
            remove_original = (
                "✅ ON (User)"
                if user_dict["MERGE_REMOVE_ORIGINAL"]
                else "❌ OFF (User)"
            )
        elif Config.MERGE_REMOVE_ORIGINAL:
            remove_original = "✅ ON (Global)"
        else:
            remove_original = "❌ OFF"

        text = f"""⌬ <b>Merge Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ ON" if merge_enabled else "❌ OFF"}
┠ <b>Concat Demuxer</b> → {concat_status}
┠ <b>Filter Complex</b> → {filter_status}
┠ <b>Threading</b> → {threading_status}
┠ <b>Thread Number</b> → <code>{thread_number}</code>
┠ <b>RO</b> → {remove_original}
┠ <b>Video Format</b> → <code>{video_format}</code>
┖ <b>Audio Format</b> → <code>{audio_format}</code>

<b>Usage:</b>
• Enable merge to combine multiple files into one
• Use with multiple links or files in the same message
• RO (Remove Original) deletes original files after merging
• Example: <code>/leech https://example.com/file1.mp4 https://example.com/file2.mp4 -merge</code>
• Example: <code>/leech https://example.com/file1.jpg https://example.com/file2.jpg -merge -del</code>"""

    elif stype.startswith("merge_config"):
        # Get all merge settings and sort them alphabetically
        merge_settings = [
            # Output formats
            "MERGE_OUTPUT_FORMAT_VIDEO",
            "MERGE_OUTPUT_FORMAT_AUDIO",
            "MERGE_OUTPUT_FORMAT_IMAGE",
            "MERGE_OUTPUT_FORMAT_DOCUMENT",
            "MERGE_OUTPUT_FORMAT_SUBTITLE",
            # Video settings
            "MERGE_VIDEO_CODEC",
            "MERGE_VIDEO_QUALITY",
            "MERGE_VIDEO_PRESET",
            "MERGE_VIDEO_CRF",
            "MERGE_VIDEO_PIXEL_FORMAT",
            "MERGE_VIDEO_TUNE",
            "MERGE_VIDEO_FASTSTART",
            # Audio settings
            "MERGE_AUDIO_CODEC",
            "MERGE_AUDIO_BITRATE",
            "MERGE_AUDIO_CHANNELS",
            "MERGE_AUDIO_SAMPLING",
            "MERGE_AUDIO_VOLUME",
            # Image settings
            "MERGE_IMAGE_MODE",
            "MERGE_IMAGE_COLUMNS",
            "MERGE_IMAGE_QUALITY",
            "MERGE_IMAGE_DPI",
            "MERGE_IMAGE_RESIZE",
            "MERGE_IMAGE_BACKGROUND",
            # Subtitle settings
            "MERGE_SUBTITLE_ENCODING",
            "MERGE_SUBTITLE_FONT",
            "MERGE_SUBTITLE_FONT_SIZE",
            "MERGE_SUBTITLE_FONT_COLOR",
            "MERGE_SUBTITLE_BACKGROUND",
            # Document settings
            "MERGE_DOCUMENT_PAPER_SIZE",
            "MERGE_DOCUMENT_ORIENTATION",
            "MERGE_DOCUMENT_MARGIN",
            # Metadata settings
            "MERGE_METADATA_TITLE",
            "MERGE_METADATA_AUTHOR",
            "MERGE_METADATA_COMMENT",
        ]

        # Sort settings alphabetically
        merge_settings.sort()

        # Pagination setup
        global merge_config_page

        # If a specific page is requested in the stype parameter, use that
        if len(stype.split()) > 1:
            try:
                page_no = int(stype.split()[1])
                # Update the global variable
                merge_config_page = page_no
            except (ValueError, IndexError):
                # Use the global variable
                page_no = merge_config_page
        else:
            # Use the global variable if no page is specified
            page_no = merge_config_page
        # 5 rows per page, 2 columns = 10 items per page
        items_per_page = 10  # 5 rows * 2 columns
        total_pages = (len(merge_settings) + items_per_page - 1) // items_per_page

        # Ensure page_no is valid
        if page_no >= total_pages:
            page_no = 0
            merge_config_page = 0  # Update global variable
        elif page_no < 0:
            page_no = total_pages - 1
            merge_config_page = total_pages - 1  # Update global variable

        # Get settings for current page
        current_page_settings = merge_settings[
            page_no * items_per_page : (page_no * items_per_page) + items_per_page
        ]

        # Add buttons for each setting on current page
        for setting in current_page_settings:
            display_name = setting.replace("MERGE_", "").replace("_", " ").title()
            buttons.data_button(display_name, f"mediatools {user_id} menu {setting}")

        # Add action buttons in a separate row
        buttons.data_button("Back", f"mediatools {user_id} merge", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")

        # Add pagination buttons in a separate row below action buttons
        if total_pages > 1:
            for i in range(total_pages):
                # Make the current page button different
                if (
                    i == page_no
                ):  # Make sure the page number is passed as a separate parameter
                    buttons.data_button(
                        f"[{i + 1}]",
                        f"mediatools {user_id} merge_config {i}",
                        "page",
                    )
                else:  # Make sure the page number is passed as a separate parameter
                    buttons.data_button(
                        str(i + 1), f"mediatools {user_id} merge_config {i}", "page"
                    )

            # Build the menu with 2 columns for settings, 4 columns for action buttons, and 8 columns for pagination
            btns = buttons.build_menu(2, 8, 4, 8)

        # Define category groups
        formats = [
            "MERGE_OUTPUT_FORMAT_VIDEO",
            "MERGE_OUTPUT_FORMAT_AUDIO",
            "MERGE_OUTPUT_FORMAT_IMAGE",
            "MERGE_OUTPUT_FORMAT_DOCUMENT",
            "MERGE_OUTPUT_FORMAT_SUBTITLE",
        ]

        video_settings = [
            "MERGE_VIDEO_CODEC",
            "MERGE_VIDEO_QUALITY",
            "MERGE_VIDEO_PRESET",
            "MERGE_VIDEO_CRF",
            "MERGE_VIDEO_PIXEL_FORMAT",
            "MERGE_VIDEO_TUNE",
            "MERGE_VIDEO_FASTSTART",
        ]

        audio_settings = [
            "MERGE_AUDIO_CODEC",
            "MERGE_AUDIO_BITRATE",
            "MERGE_AUDIO_CHANNELS",
            "MERGE_AUDIO_SAMPLING",
            "MERGE_AUDIO_VOLUME",
        ]

        image_settings = [
            "MERGE_IMAGE_MODE",
            "MERGE_IMAGE_COLUMNS",
            "MERGE_IMAGE_QUALITY",
            "MERGE_IMAGE_DPI",
            "MERGE_IMAGE_RESIZE",
            "MERGE_IMAGE_BACKGROUND",
        ]

        subtitle_settings = [
            "MERGE_SUBTITLE_ENCODING",
            "MERGE_SUBTITLE_FONT",
            "MERGE_SUBTITLE_FONT_SIZE",
            "MERGE_SUBTITLE_FONT_COLOR",
            "MERGE_SUBTITLE_BACKGROUND",
        ]

        document_settings = [
            "MERGE_DOCUMENT_PAPER_SIZE",
            "MERGE_DOCUMENT_ORIENTATION",
            "MERGE_DOCUMENT_MARGIN",
        ]

        metadata_settings = [
            "MERGE_METADATA_TITLE",
            "MERGE_METADATA_AUTHOR",
            "MERGE_METADATA_COMMENT",
        ]

        # Get the categories shown on the current page
        categories = []
        # Calculate the start index for the current page
        current_page_settings = merge_settings[
            page_no * items_per_page : (page_no * items_per_page) + items_per_page
        ]
        if any(setting in formats for setting in current_page_settings):
            categories.append("Formats")
        if any(setting in video_settings for setting in current_page_settings):
            categories.append("Video")
        if any(setting in audio_settings for setting in current_page_settings):
            categories.append("Audio")
        if any(setting in image_settings for setting in current_page_settings):
            categories.append("Image")
        if any(setting in subtitle_settings for setting in current_page_settings):
            categories.append("Subtitle")
        if any(setting in document_settings for setting in current_page_settings):
            categories.append("Document")
        if any(setting in metadata_settings for setting in current_page_settings):
            categories.append("Metadata")

        category_text = ", ".join(categories)

        # Get page info for message
        page_info = f"\n\nCurrent page shows: {category_text} settings."
        if total_pages > 1:
            page_info += f"\n<b>Page:</b> {page_no + 1}/{total_pages}"

        # Get concat demuxer status
        user_has_concat = "CONCAT_DEMUXER_ENABLED" in user_dict
        if user_has_concat:
            concat_status = (
                "✅ ON (User)"
                if user_dict["CONCAT_DEMUXER_ENABLED"]
                else "❌ OFF (User)"
            )
        elif Config.CONCAT_DEMUXER_ENABLED:
            concat_status = "✅ ON (Global)"
        else:
            concat_status = "❌ OFF"

        # Get filter complex status
        user_has_filter = "FILTER_COMPLEX_ENABLED" in user_dict
        if user_has_filter:
            filter_status = (
                "✅ ON (User)"
                if user_dict["FILTER_COMPLEX_ENABLED"]
                else "❌ OFF (User)"
            )
        elif Config.FILTER_COMPLEX_ENABLED:
            filter_status = "✅ ON (Global)"
        else:
            filter_status = "❌ OFF"

        # Get output formats
        user_has_video_format = (
            "MERGE_OUTPUT_FORMAT_VIDEO" in user_dict
            and user_dict["MERGE_OUTPUT_FORMAT_VIDEO"]
        )
        user_has_audio_format = (
            "MERGE_OUTPUT_FORMAT_AUDIO" in user_dict
            and user_dict["MERGE_OUTPUT_FORMAT_AUDIO"]
        )

        if user_has_video_format:
            video_format = f"{user_dict['MERGE_OUTPUT_FORMAT_VIDEO']} (User)"
        elif Config.MERGE_OUTPUT_FORMAT_VIDEO:
            video_format = f"{Config.MERGE_OUTPUT_FORMAT_VIDEO} (Global)"
        else:
            video_format = "mkv (Default)"

        if user_has_audio_format:
            audio_format = f"{user_dict['MERGE_OUTPUT_FORMAT_AUDIO']} (User)"
        elif Config.MERGE_OUTPUT_FORMAT_AUDIO:
            audio_format = f"{Config.MERGE_OUTPUT_FORMAT_AUDIO} (Global)"
        else:
            audio_format = "mp3 (Default)"

        # Get priority
        user_has_priority = (
            "MERGE_PRIORITY" in user_dict and user_dict["MERGE_PRIORITY"]
        )
        if user_has_priority:
            priority = f"{user_dict['MERGE_PRIORITY']} (User)"
        elif Config.MERGE_PRIORITY:
            priority = f"{Config.MERGE_PRIORITY} (Global)"
        else:
            priority = "1 (Default)"

        # Get threading
        user_has_threading = "MERGE_THREADING" in user_dict
        if user_has_threading:
            threading = (
                "✅ ON (User)" if user_dict["MERGE_THREADING"] else "❌ OFF (User)"
            )
        elif Config.MERGE_THREADING:
            threading = "✅ ON (Global)"
        else:
            threading = "❌ OFF"

        # Get thread number
        user_has_thread_number = (
            "MERGE_THREAD_NUMBER" in user_dict and user_dict["MERGE_THREAD_NUMBER"]
        )
        if user_has_thread_number:
            thread_number = f"{user_dict['MERGE_THREAD_NUMBER']} (User)"
        elif Config.MERGE_THREAD_NUMBER:
            thread_number = f"{Config.MERGE_THREAD_NUMBER} (Global)"
        else:
            thread_number = "4 (Default)"

        # Get format options
        # Video settings
        user_has_video_format = (
            "MERGE_OUTPUT_FORMAT_VIDEO" in user_dict
            and user_dict["MERGE_OUTPUT_FORMAT_VIDEO"]
        )

        # Audio settings
        user_has_audio_format = (
            "MERGE_OUTPUT_FORMAT_AUDIO" in user_dict
            and user_dict["MERGE_OUTPUT_FORMAT_AUDIO"]
        )

        # We only need a few variables for the text display
        user_has_remove_original = "MERGE_REMOVE_ORIGINAL" in user_dict

        # Get values for video options
        if user_has_video_format:
            video_format = f"{user_dict['MERGE_OUTPUT_FORMAT_VIDEO']} (User)"
        elif Config.MERGE_OUTPUT_FORMAT_VIDEO:
            video_format = f"{Config.MERGE_OUTPUT_FORMAT_VIDEO} (Global)"
        else:
            video_format = "mkv (Default)"

        # Get values for audio options
        if user_has_audio_format:
            audio_format = f"{user_dict['MERGE_OUTPUT_FORMAT_AUDIO']} (User)"
        elif Config.MERGE_OUTPUT_FORMAT_AUDIO:
            audio_format = f"{Config.MERGE_OUTPUT_FORMAT_AUDIO} (Global)"
        else:
            audio_format = "mp3 (Default)"

        # We don't need to get all values since we're only showing a few in the text

        if user_has_remove_original:
            remove_original = (
                "✅ ON (User)"
                if user_dict["MERGE_REMOVE_ORIGINAL"]
                else "❌ OFF (User)"
            )
        elif Config.MERGE_REMOVE_ORIGINAL:
            remove_original = "✅ ON (Global)"
        else:
            remove_original = "❌ OFF"

        text = f"""⌬ <b>Configure Merge :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Select a setting to configure</b>
┃
┠ <b>Current Settings:</b>
┃ • <b>Concat Demuxer:</b> {concat_status}
┃ • <b>Filter Complex:</b> {filter_status}
┃ • <b>Priority:</b> <code>{priority}</code>
┃ • <b>Threading:</b> {threading}
┃ • <b>Thread Number:</b> <code>{thread_number}</code>
┃ • <b>RO:</b> {remove_original}
┃ • <b>Video Format:</b> <code>{video_format}</code>
┃ • <b>Audio Format:</b> <code>{audio_format}</code>
┖ <b>Note:</b> Most settings default to 'none' unless specified{page_info}"""

    elif stype == "help":
        # Media Tools Help menu
        buttons.data_button("Merge Help", f"mediatools {user_id} help_merge")
        buttons.data_button("Watermark Help", f"mediatools {user_id} help_watermark")
        buttons.data_button("Convert Help", f"mediatools {user_id} help_convert")
        buttons.data_button(
            "Compression Help", f"mediatools {user_id} help_compression"
        )
        buttons.data_button("Trim Help", f"mediatools {user_id} help_trim")
        buttons.data_button("Extract Help", f"mediatools {user_id} help_extract")
        buttons.data_button("Remove Help", f"mediatools {user_id} help_remove")
        buttons.data_button("Add Help", f"mediatools {user_id} help_add")
        buttons.data_button("Swap Help", f"mediatools {user_id} help_swap")
        buttons.data_button("Priority Guide", f"mediatools {user_id} help_priority")
        buttons.data_button("Usage Examples", f"mediatools {user_id} help_examples")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Media Tools Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Select a help topic from the buttons below.</b>
┃
┠ <b>Merge Help</b> - Information about merging media files
┠ <b>Watermark Help</b> - Information about watermarking media
┠ <b>Convert Help</b> - Information about converting media files
┠ <b>Compression Help</b> - Information about compressing files
┠ <b>Trim Help</b> - Information about trimming media files
┠ <b>Extract Help</b> - Information about extracting media tracks
┠ <b>Remove Help</b> - Information about removing media tracks
┠ <b>Add Help</b> - Information about adding media tracks
┠ <b>Swap Help</b> - Information about swapping/reordering media tracks
┠ <b>Priority Guide</b> - How tool priority affects processing
┖ <b>Usage Examples</b> - Examples of how to use media tools"""

    elif stype == "help_watermark":
        # Watermark Help
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Watermark Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The watermark feature allows you to add text overlays to your videos and images.
┃
┠ <b>Supported Media Types:</b>
┃ • <b>Videos</b> - MP4, MKV, AVI, WebM, etc.
┃ • <b>Images</b> - JPG, PNG, WebP, etc.
┃
┠ <b>Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle watermark feature
┃ • <b>Text</b> - The text to display as watermark
┃ • <b>Position</b> - Where to place the watermark on the media
┃ • <b>Size</b> - Font size of the watermark text
┃ • <b>Color</b> - Color of the watermark text
┃ • <b>Font</b> - Font to use for the watermark text
┃ • <b>Priority</b> - Processing order when multiple tools are enabled
┃ • <b>Threading</b> - Enable/disable parallel processing
┃
┠ <b>Usage:</b>
┃ Add <code>-watermark "Your Text"</code> to any download command
┃ Example: <code>/leech https://example.com/media.zip -watermark "© My Channel"</code>
┃
┖ <b>Note:</b> For best results, use short text and contrasting colors."""

    elif stype == "help_merge":
        # Merge Help
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Merge Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ Combine multiple media files into a single file
┃
┠ <b>Supported Types:</b>
┃ • <b>Video:</b> Multiple videos → single video
┃ • <b>Audio:</b> Multiple audio files → single audio
┃ • <b>Subtitle:</b> Multiple subtitle files → single subtitle
┃ • <b>Mixed:</b> Video + Audio + Subtitle → complete media
┃ • <b>Image:</b> Multiple images → collage/grid
┃ • <b>PDF:</b> Multiple PDFs → single document
┃
┠ <b>Merge Flags:</b>
┃ • <code>-merge-video</code> - Merge videos (preserves all tracks)
┃ • <code>-merge-audio</code> - Merge audio files
┃ • <code>-merge-subtitle</code> - Merge subtitle files
┃ • <code>-merge-image</code> - Merge images (collage/grid)
┃ • <code>-merge-pdf</code> - Merge PDF documents
┃ • <code>-merge-all</code> - Merge all files by type
┃
┠ <b>Key Settings:</b>
┃ • <b>Method:</b> Concat Demuxer (fast) or Filter Complex (compatible)
┃ • <b>Output:</b> Format for merged files (mkv, mp4, mp3, etc.)
┃ • <b>Video:</b> Codec, quality, preset settings
┃ • <b>Audio:</b> Codec, bitrate, channels settings
┃ • <b>Image:</b> Mode (auto, horizontal, vertical, collage), quality
┃
┠ <b>Tips:</b>
┃ • Use <code>-m folder_name</code> to place files in same directory
┃ • MKV format best for preserving multiple tracks
┃ • 'copy' codec preserves quality but requires similar formats
┃
┖ <b>Note:</b> For more details, use /mthelp command."""

    elif stype == "help_convert":
        # Convert Help
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Convert Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The convert feature allows you to convert media files to different formats.
┃
┠ <b>Supported Media Types:</b>
┃ • <b>Videos</b> - MP4, MKV, AVI, WebM, etc.
┃ • <b>Audio</b> - MP3, AAC, FLAC, WAV, etc.
┃
┠ <b>Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle convert feature
┃ • <b>Priority</b> - Processing order when multiple tools are enabled
┃
┠ <b>Video Convert Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle video convert feature
┃ • <b>Format</b> - Output format for converted videos (mp4, mkv, etc.)
┃ • <b>Codec</b> - Video codec to use (libx264, libx265, etc.)
┃ • <b>Quality</b> - Video quality preset (low, medium, high, etc.)
┃ • <b>CRF</b> - Quality control (0-51, lower is better quality)
┃ • <b>Preset</b> - Encoding speed vs compression (medium, slow, etc.)
┃ • <b>Maintain Quality</b> - Preserve original quality when possible
┃
┠ <b>Audio Convert Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle audio convert feature
┃ • <b>Format</b> - Output format for converted audio (mp3, aac, etc.)
┃ • <b>Codec</b> - Audio codec to use (libmp3lame, aac, etc.)
┃ • <b>Bitrate</b> - Audio quality (128k, 192k, 320k, etc.)
┃ • <b>Channels</b> - Number of audio channels (1=mono, 2=stereo)
┃ • <b>Sampling</b> - Audio sampling rate (44100, 48000, etc.)
┃ • <b>Volume</b> - Volume adjustment (1.0=normal, 2.0=double)
┃
┠ <b>Usage:</b>
┃ • <b>Convert Video:</b> Add <code>-cv format</code> to any download command
┃   Example: <code>/leech https://example.com/video.mp4 -cv mp4</code>
┃
┃ • <b>Convert Audio:</b> Add <code>-ca format</code> to any download command
┃   Example: <code>/mirror https://example.com/audio.wav -ca mp3</code>
┃
┖ <b>Note:</b> Convert uses FFmpeg for processing and supports most media formats."""

    elif stype == "help_trim":
        # Trim Guide
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Trim Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The trim feature allows you to cut specific portions of media files.
┃
┠ <b>Supported Media Types:</b>
┃ • <b>Videos</b> - MP4, MKV, AVI, WebM, etc.
┃ • <b>Audio</b> - MP3, AAC, FLAC, WAV, etc.
┃ • <b>Images</b> - JPG, PNG, WebP, etc.
┃ • <b>Documents</b> - PDF, DOC, DOCX, etc.
┃ • <b>Subtitles</b> - SRT, ASS, VTT, etc.
┃ • <b>Archives</b> - ZIP, RAR, 7Z, etc.
┃
┠ <b>Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle trim feature
┃ • <b>Priority</b> - Processing order when multiple tools are enabled
┃ • <b>RO</b> - Remove original file after successful trim
┃
┠ <b>Video Trim Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle video trim
┃ • <b>Codec</b> - Video codec to use (copy, libx264, etc.)
┃ • <b>Preset</b> - Encoding speed/quality (fast, medium, slow)
┃ • <b>Format</b> - Output format (mp4, mkv, avi, webm, etc.)
┃
┠ <b>Audio Trim Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle audio trim
┃ • <b>Codec</b> - Audio codec to use (copy, aac, etc.)
┃ • <b>Preset</b> - Encoding speed/quality (fast, medium, slow)
┃ • <b>Format</b> - Output format (mp3, m4a, flac, opus, wav, etc.)
┃
┠ <b>Image Trim Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle image trim
┃ • <b>Quality</b> - Image quality (1-100)
┃ • <b>Format</b> - Output format (jpg, png, webp, gif, etc.)
┃
┠ <b>Document Trim Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle document trim
┃ • <b>Start Page</b> - Starting page number for trimming (1-based)
┃ • <b>End Page</b> - Ending page number for trimming (empty for last page)
┃ • <b>Quality</b> - Document quality (1-100)
┃ • <b>Format</b> - Output format (pdf, docx, txt, etc.)
┃
┠ <b>Subtitle Trim Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle subtitle trim
┃ • <b>Encoding</b> - Character encoding (utf-8, latin1, etc.)
┃ • <b>Format</b> - Output format (srt, ass, vtt, etc.)
┃
┠ <b>Archive Trim Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle archive trim
┃ • <b>Format</b> - Output format (zip, 7z, tar, etc.)
┃
┠ <b>Usage:</b>
┃ • <b>Trim Media:</b> Add <code>-trim from-time to-time</code> to any download command
┃   Example: <code>/leech https://example.com/video.mp4 -trim 00:01:30 00:02:45</code>
┃   This will trim the video from 1 minute 30 seconds to 2 minutes 45 seconds
┃
┃ • <b>Trim Documents:</b> Add <code>-trim start-page end-page</code> for documents
┃   Example: <code>/leech https://example.com/document.pdf -trim 5 10</code>
┃   This will extract pages 5 to 10 from the PDF document
┃   Example: <code>/leech https://example.com/document.pdf -trim 3 -</code>
┃   This will extract from page 3 to the last page
┃
┃ • <b>RO:</b> Add <code>-del</code> to delete the original file after trimming
┃   Example: <code>/leech https://example.com/video.mp4 -trim 00:01:30 00:02:45 -del</code>
┃   Example: <code>/leech https://example.com/document.pdf -trim 5 10 -del</code>
┃
┃ • <b>Time Format:</b> Use HH:MM:SS or seconds for media files
┃   Example: <code>-trim 90 165</code> (trim from 90 seconds to 165 seconds)
┃   Example: <code>-trim 00:01:30 00:02:45</code> (trim from 1m30s to 2m45s)
┃
┃ • <b>Page Format:</b> Use page numbers for documents
┃   Example: <code>-trim 1 5</code> (extract pages 1 to 5)
┃   Example: <code>-trim 10 -</code> (extract from page 10 to end)
┃
┖ <b>Note:</b> Trim uses FFmpeg for media processing and PyMuPDF for document processing. Format settings with value 'none' will use the original file format."""

    elif stype == "help_extract":
        # Extract Guide
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Extract Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The extract feature allows you to extract specific tracks from media files.
┃
┠ <b>Supported Media Types:</b>
┃ • <b>Container Formats</b> - MKV, MP4, AVI, MOV, WebM, etc.
┃ • <b>Video Codecs</b> - H.264, H.265, VP9, AV1, etc.
┃ • <b>Audio Codecs</b> - AAC, MP3, OPUS, FLAC, etc.
┃ • <b>Subtitle Formats</b> - SRT, ASS, SSA, VTT, etc.
┃ • <b>Attachments</b> - Fonts, images, and other embedded files
┃
┠ <b>Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle extract feature
┃ • <b>Priority</b> - Processing order when multiple tools are enabled
┃ • <b>Maintain Quality</b> - Preserve high quality during extraction
┃
┠ <b>Video Extract Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle video extraction
┃ • <b>Codec</b> - Video codec to use (copy, h264, h265, etc.)
┃ • <b>Index</b> - Specific video track to extract (0-based index)
┃
┠ <b>Audio Extract Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle audio extraction
┃ • <b>Codec</b> - Audio codec to use (copy, aac, mp3, etc.)
┃ • <b>Index</b> - Specific audio track to extract (0-based index)
┃
┠ <b>Subtitle Extract Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle subtitle extraction
┃ • <b>Codec</b> - Subtitle codec to use (copy, srt, ass, etc.)
┃ • <b>Index</b> - Specific subtitle track to extract (0-based index)
┃
┠ <b>Attachment Extract Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle attachment extraction
┃ • <b>Index</b> - Specific attachment to extract (0-based index)
┃
┠ <b>Usage:</b>
┃ • <b>Extract All Tracks:</b> Add <code>-extract</code> to any download command
┃   Example: <code>/leech https://example.com/video.mkv -extract</code>
┃
┃ • <b>Extract Specific Track Types:</b>
┃   Example: <code>/leech https://example.com/video.mkv -extract-video</code>
┃   Example: <code>/mirror https://example.com/video.mkv -extract-audio</code>
┃   Example: <code>/leech https://example.com/video.mkv -extract-subtitle</code>
┃
┃ • <b>Extract Specific Track by Index:</b>
┃   Example: <code>/leech https://example.com/video.mkv -extract-audio-index 1</code>
┃   This will extract the second audio track (index starts at 0)
┃
┖ <b>Note:</b> Extract uses FFmpeg for processing and works best with MKV containers."""

    elif stype == "help_compression":
        # Compression Guide
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Compression Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The compression feature reduces file size while maintaining acceptable quality.
┃
┠ <b>Supported Media Types:</b>
┃ • <b>Videos</b> - MP4, MKV, AVI, WebM, etc.
┃ • <b>Audio</b> - MP3, AAC, FLAC, WAV, etc.
┃ • <b>Images</b> - JPG, PNG, WebP, etc.
┃ • <b>Documents</b> - PDF, DOC, DOCX, etc.
┃ • <b>Subtitles</b> - SRT, ASS, VTT, etc.
┃ • <b>Archives</b> - ZIP, RAR, 7Z, etc.
┃
┠ <b>Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle compression feature
┃ • <b>Priority</b> - Processing order when multiple tools are enabled
┃
┠ <b>Video Compression Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle video compression
┃ • <b>Preset</b> - Compression speed/quality (fast, medium, slow)
┃ • <b>CRF</b> - Quality control (0-51, lower is better quality)
┃ • <b>Codec</b> - Video codec to use (libx264, libx265, etc.)
┃ • <b>Tune</b> - Content-specific optimizations (film, animation, etc.)
┃ • <b>Pixel Format</b> - Color encoding format (yuv420p, etc.)
┃
┠ <b>Audio Compression Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle audio compression
┃ • <b>Preset</b> - Compression speed/quality (fast, medium, slow)
┃ • <b>Codec</b> - Audio codec to use (aac, mp3, etc.)
┃ • <b>Bitrate</b> - Audio quality (128k, 192k, 320k, etc.)
┃ • <b>Channels</b> - Number of audio channels (1=mono, 2=stereo)
┃
┠ <b>Image Compression Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle image compression
┃ • <b>Preset</b> - Compression speed/quality (fast, medium, slow)
┃ • <b>Quality</b> - Image quality (1-100)
┃ • <b>Resize</b> - Image dimensions (none, 1920x1080, etc.)
┃
┠ <b>Document Compression Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle document compression
┃ • <b>Preset</b> - Compression speed/quality (fast, medium, slow)
┃ • <b>DPI</b> - Resolution for PDF compression (72-300)
┃
┠ <b>Subtitle Compression Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle subtitle compression
┃ • <b>Preset</b> - Compression speed/quality (fast, medium, slow)
┃ • <b>Encoding</b> - Character encoding (utf-8, latin1, etc.)
┃
┠ <b>Archive Compression Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle archive compression
┃ • <b>Preset</b> - Compression speed/quality (fast, medium, slow)
┃ • <b>Level</b> - Compression level (1-9)
┃ • <b>Method</b> - Compression algorithm (deflate, lzma, etc.)
┃
┠ <b>Usage:</b>
┃ • <b>Enable Compression:</b> Add <code>-compress</code> to any download command
┃   Example: <code>/leech https://example.com/video.mp4 -compress</code>
┃
┃ • <b>Video Compression:</b> Add <code>-video-fast</code>, <code>-video-medium</code>, or <code>-video-slow</code>
┃   Example: <code>/mirror https://example.com/video.mp4 -video-medium</code>
┃
┃ • <b>Audio Compression:</b> Add <code>-audio-fast</code>, <code>-audio-medium</code>, or <code>-audio-slow</code>
┃   Example: <code>/leech https://example.com/audio.mp3 -audio-medium</code>
┃
┃ • <b>Image Compression:</b> Add <code>-image-fast</code>, <code>-image-medium</code>, or <code>-image-slow</code>
┃   Example: <code>/mirror https://example.com/image.jpg -image-medium</code>
┃
┃ • <b>Document Compression:</b> Add <code>-document-fast</code>, <code>-document-medium</code>, or <code>-document-slow</code>
┃   Example: <code>/leech https://example.com/document.pdf -document-medium</code>
┃
┃ • <b>Subtitle Compression:</b> Add <code>-subtitle-fast</code>, <code>-subtitle-medium</code>, or <code>-subtitle-slow</code>
┃   Example: <code>/mirror https://example.com/subtitle.srt -subtitle-medium</code>
┃
┃ • <b>Archive Compression:</b> Add <code>-archive-fast</code>, <code>-archive-medium</code>, or <code>-archive-slow</code>
┃   Example: <code>/leech https://example.com/archive.zip -archive-medium</code>
┃
┖ <b>Note:</b> Compression only keeps the compressed file if it's smaller than the original."""

    elif stype == "help_add":
        # Add Help
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Add Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The Add feature allows you to add media tracks (video, audio, subtitle, attachment) to existing files.
┃
┠ <b>Supported Media Types:</b>
┃ • <b>Videos</b> - MP4, MKV, AVI, WebM, etc.
┃ • <b>Audio</b> - MP3, AAC, FLAC, WAV, etc.
┃ • <b>Subtitles</b> - SRT, ASS, VTT, etc.
┃ • <b>Attachments</b> - Fonts, images, and other files
┃
┠ <b>Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle Add feature
┃ • <b>Priority</b> - Processing order when multiple tools are enabled
┃ • <b>RO (Remove Original)</b> - Delete original file after adding tracks

<blockquote expandable="expandable"><b>Video Add Settings:</b>
• <b>Enabled/Disabled</b> - Toggle video add
• <b>Path</b> - Path to video file to add
• <b>Codec</b> - Video codec to use (copy, libx264, etc.)
• <b>Index</b> - Specific index to add video track to (comma-separated for multiple)
• <b>Quality</b> - Video quality/CRF value
• <b>Preset</b> - Encoding preset (e.g., ultrafast, medium, veryslow)
• <b>Bitrate</b> - Video bitrate (e.g., 5M, 10M)
• <b>Resolution</b> - Video resolution (e.g., 1920x1080)
• <b>FPS</b> - Video frame rate (e.g., 30, 60)</blockquote>

<blockquote expandable="expandable"><b>Audio Add Settings:</b>
• <b>Enabled/Disabled</b> - Toggle audio add
• <b>Path</b> - Path to audio file to add
• <b>Codec</b> - Audio codec to use (copy, aac, mp3, etc.)
• <b>Index</b> - Specific index to add audio track to (comma-separated for multiple)
• <b>Bitrate</b> - Audio bitrate (e.g., 128k, 192k, 320k)
• <b>Channels</b> - Number of audio channels (e.g., 1 for mono, 2 for stereo)
• <b>Sampling</b> - Audio sampling rate (e.g., 44100, 48000)
• <b>Volume</b> - Volume adjustment (e.g., 1.0 normal, 1.5 louder)</blockquote>

<blockquote expandable="expandable"><b>Subtitle Add Settings:</b>
• <b>Enabled/Disabled</b> - Toggle subtitle add
• <b>Path</b> - Path to subtitle file to add
• <b>Codec</b> - Subtitle codec to use (copy, srt, ass, etc.)
• <b>Index</b> - Specific index to add subtitle track to (comma-separated for multiple)
• <b>Hardsub</b> - Burn subtitles permanently into video (cannot be turned off)
• <b>Language</b> - Subtitle language code (e.g., eng, spa, fre)
• <b>Encoding</b> - Character encoding (e.g., UTF-8, latin1)
• <b>Font</b> - Font for ASS/SSA subtitles (e.g., Arial)
• <b>Font Size</b> - Font size for ASS/SSA subtitles (e.g., 24)</blockquote>

<blockquote expandable="expandable"><b>Attachment Add Settings:</b>
• <b>Enabled/Disabled</b> - Toggle attachment add
• <b>Path</b> - Path to attachment file to add
• <b>Index</b> - Specific index to add attachment to (comma-separated for multiple)
• <b>Mimetype</b> - MIME type of the attachment</blockquote>
┃
┠ <b>Usage:</b>
┃ • <b>Add Tracks:</b> Add <code>-add</code> to any download command
┃   Example: <code>/leech https://example.com/video.mp4 -add</code>
┃
┃ • <b>Add with RO:</b> Add <code>-add -del</code> to delete original after adding
┃   Example: <code>/leech https://example.com/video.mp4 -add -del</code>
┃
┃ • <b>Add with Preserve:</b> Add <code>-add -preserve</code> to preserve existing tracks
┃   Example: <code>/leech https://example.com/video.mp4 -add -preserve</code>
┃
┃ • <b>Add with Replace:</b> Add <code>-add -replace</code> to replace existing tracks
┃   Example: <code>/leech https://example.com/video.mp4 -add -replace</code>
┃
┖ <b>Note:</b> Add uses FFmpeg for processing and works best with MKV containers."""

    elif stype == "help_remove":
        # Remove Help
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Remove Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The Remove feature allows you to remove specific tracks or metadata from media files.
┃
┠ <b>Supported Media Types:</b>
┃ • <b>Videos</b> - MP4, MKV, AVI, WebM, etc.
┃ • <b>Audio</b> - MP3, AAC, FLAC, WAV, etc.
┃ • <b>Subtitles</b> - SRT, ASS, VTT, etc.
┃ • <b>Attachments</b> - Fonts, images, and other embedded files
┃
┠ <b>Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle Remove feature
┃ • <b>Priority</b> - Processing order when multiple tools are enabled
┃ • <b>RO (Remove Original)</b> - Delete original file after removing tracks
┃ • <b>Remove Metadata</b> - Strip metadata from files
┃
┠ <b>Track Type Settings:</b>
┃ • <b>Video Remove</b> - Enable/disable video track removal
┃ • <b>Audio Remove</b> - Enable/disable audio track removal
┃ • <b>Subtitle Remove</b> - Enable/disable subtitle track removal
┃ • <b>Attachment Remove</b> - Enable/disable attachment removal
┃
┠ <b>Index Settings:</b>
┃ • <b>Video Index</b> - Which video tracks to remove (empty = all)
┃ • <b>Audio Index</b> - Which audio tracks to remove (empty = all)
┃ • <b>Subtitle Index</b> - Which subtitle tracks to remove (empty = all)
┃ • <b>Attachment Index</b> - Which attachments to remove (empty = all)
┃
┠ <b>Usage:</b>
┃ • <b>Remove All Tracks:</b> Add <code>-remove</code> to any download command
┃   Example: <code>/leech https://example.com/video.mkv -remove</code>
┃
┃ • <b>Remove Specific Track Types:</b>
┃   Example: <code>/leech https://example.com/video.mkv -remove-video</code>
┃   Example: <code>/mirror https://example.com/video.mkv -remove-audio</code>
┃   Example: <code>/leech https://example.com/video.mkv -remove-subtitle</code>
┃   Example: <code>/mirror https://example.com/video.mkv -remove-attachment</code>
┃
┃ • <b>Remove Specific Track by Index:</b>
┃   Example: <code>/leech https://example.com/video.mkv -remove-audio-index 1</code>
┃   This will remove the second audio track (index starts at 0)
┃
┃ • <b>Remove Multiple Tracks by Index:</b>
┃   Example: <code>/mirror https://example.com/video.mkv -remove-audio-index 0,2</code>
┃   This will remove the first and third audio tracks
┃
┃ • <b>Remove Metadata:</b>
┃   Example: <code>/leech https://example.com/video.mkv -remove-metadata</code>
┃   This will strip metadata from the file
┃
┃ • <b>Short Format Flags:</b>
┃   Example: <code>/mirror https://example.com/video.mkv -rvi 0,1 -rai 2</code>
┃   This removes first two video tracks and third audio track
┃
┖ <b>Note:</b> Remove uses FFmpeg for processing and works best with MKV containers."""

    elif stype == "help_swap":
        # Swap Help
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Swap Help :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The Swap feature allows you to reorder audio, video, and subtitle tracks based on language priority or index positions.
┃
┠ <b>Supported Media Types:</b>
┃ • <b>Videos</b> - MP4, MKV, AVI, WebM, etc.
┃ • <b>Audio</b> - MP3, AAC, FLAC, WAV, etc.
┃ • <b>Subtitles</b> - SRT, ASS, VTT, etc.
┃
┠ <b>Settings:</b>
┃ • <b>Enabled/Disabled</b> - Toggle Swap feature
┃ • <b>Priority</b> - Processing order when multiple tools are enabled (default: 6)
┃ • <b>RO (Remove Original)</b> - Delete original file after swapping tracks
┃
┠ <b>Track Type Settings:</b>
┃ • <b>Audio Swap</b> - Enable/disable audio track swapping
┃ • <b>Video Swap</b> - Enable/disable video track swapping
┃ • <b>Subtitle Swap</b> - Enable/disable subtitle track swapping
┃
┠ <b>Swap Modes:</b>
┃ • <b>Language Mode</b> - Reorder tracks based on language priority
┃   Example: "eng,hin" puts English tracks first, Hindi second
┃ • <b>Index Mode</b> - Swap tracks at specific positions
┃   Example: "1,2" swaps track at index 1 with track at index 2
┃
┠ <b>Usage:</b>
┃ • <b>Swap All Enabled:</b> Add <code>-swap</code> to any download command
┃   Example: <code>/leech https://example.com/video.mkv -swap</code>
┃
┃ • <b>Language-based Swapping:</b>
┃   Configure language order in settings (e.g., "eng,hin,jpn")
┃   Tracks will be reordered to match this priority
┃
┃ • <b>Index-based Swapping:</b>
┃   Configure index order in settings (e.g., "1,0" to swap first two tracks)
┃   Tracks at specified indices will be swapped
┃
┖ <b>Note:</b> Swap uses FFmpeg for processing and preserves all track data without re-encoding."""

    elif stype == "help_priority":
        # Priority Guide
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Media Tools Priority Guide :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Overview:</b>
┃ The priority system controls the order in which media tools are applied.
┃
┠ <b>How Priority Works:</b>
┃ • Lower number means higher priority (1 is highest priority)
┃ • When multiple media tools are enabled, they run in priority order
┃ • Default priorities: Merge (1), Watermark (2), Convert (3), Compression (4), Trim (5), Extract (6), Add (7), Remove (8)
┃
┠ <b>Why Priority Matters:</b>
┃ The order of processing affects the final result:
┃ • <b>Merge → Watermark</b>: Watermark appears once on the merged file
┃ • <b>Watermark → Merge</b>: Each file is watermarked before merging
┃ • <b>Convert → Watermark</b>: Watermark appears on converted file
┃ • <b>Watermark → Convert</b>: Watermark is applied before conversion
┃ • <b>Compression → Convert</b>: Compressed file is then converted
┃ • <b>Convert → Compression</b>: Converted file is then compressed
┃ • <b>Trim → Convert</b>: Trimmed file is then converted
┃ • <b>Convert → Trim</b>: Converted file is then trimmed
┃
┠ <b>Setting Priority:</b>
┃ 1. Go to Media Tools settings
┃ 2. Select the tool (Watermark, Merge, Convert, Compression, Trim, Extract, Add, or Remove)
┃ 3. Click "Set Priority"
┃ 4. Enter a number (lower = higher priority)
┃
┖ <b>Note:</b> Priorities follow the user/owner/default configuration hierarchy."""

    elif stype == "compression":
        # Compression settings menu
        compression_enabled = user_dict.get("COMPRESSION_ENABLED", False)
        buttons.data_button(
            f"Compression: {'✅ ON' if compression_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog COMPRESSION_ENABLED {'f' if compression_enabled else 't'}",
        )

        buttons.data_button("Configure", f"mediatools {user_id} compression_config")
        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu COMPRESSION_PRIORITY"
        )
        buttons.data_button("Reset", f"mediatools {user_id} reset_compression")
        buttons.data_button("Remove", f"mediatools {user_id} remove_compression")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get compression priority
        user_has_priority = "COMPRESSION_PRIORITY" in user_dict
        if user_has_priority:
            compression_priority = f"{user_dict['COMPRESSION_PRIORITY']} (User)"
        elif hasattr(Config, "COMPRESSION_PRIORITY"):
            compression_priority = f"{Config.COMPRESSION_PRIORITY} (Global)"
        else:
            compression_priority = "4 (Default)"

        # Get RO toggle status (Remove Original)
        # Check for user setting first, then global setting, then default to True
        remove_original = user_dict.get("COMPRESSION_DELETE_ORIGINAL", None)
        if remove_original is None and hasattr(
            Config, "COMPRESSION_DELETE_ORIGINAL"
        ):
            remove_original = Config.COMPRESSION_DELETE_ORIGINAL
        elif remove_original is None:
            remove_original = True  # Default to True if not specified

        # Determine display string with appropriate label
        if "COMPRESSION_DELETE_ORIGINAL" in user_dict:
            remove_original_status = (
                "✅ ON (User)" if remove_original else "❌ OFF (User)"
            )
        elif hasattr(Config, "COMPRESSION_DELETE_ORIGINAL"):
            remove_original_status = (
                "✅ ON (Global)"
                if Config.COMPRESSION_DELETE_ORIGINAL
                else "❌ OFF (Global)"
            )
        else:
            remove_original_status = "✅ ON (Default)"

        # Get video compression status
        video_enabled = user_dict.get("COMPRESSION_VIDEO_ENABLED", False)
        if "COMPRESSION_VIDEO_ENABLED" in user_dict:
            video_status = "✅ ON (User)" if video_enabled else "❌ OFF (User)"
        elif (
            hasattr(Config, "COMPRESSION_VIDEO_ENABLED")
            and Config.COMPRESSION_VIDEO_ENABLED
        ):
            video_status = "✅ ON (Global)"
        else:
            video_status = "❌ OFF"

        # Get audio compression status
        audio_enabled = user_dict.get("COMPRESSION_AUDIO_ENABLED", False)
        if "COMPRESSION_AUDIO_ENABLED" in user_dict:
            audio_status = "✅ ON (User)" if audio_enabled else "❌ OFF (User)"
        elif (
            hasattr(Config, "COMPRESSION_AUDIO_ENABLED")
            and Config.COMPRESSION_AUDIO_ENABLED
        ):
            audio_status = "✅ ON (Global)"
        else:
            audio_status = "❌ OFF"

        # Get image compression status
        image_enabled = user_dict.get("COMPRESSION_IMAGE_ENABLED", False)
        if "COMPRESSION_IMAGE_ENABLED" in user_dict:
            image_status = "✅ ON (User)" if image_enabled else "❌ OFF (User)"
        elif (
            hasattr(Config, "COMPRESSION_IMAGE_ENABLED")
            and Config.COMPRESSION_IMAGE_ENABLED
        ):
            image_status = "✅ ON (Global)"
        else:
            image_status = "❌ OFF"

        # Get document compression status
        document_enabled = user_dict.get("COMPRESSION_DOCUMENT_ENABLED", False)
        if "COMPRESSION_DOCUMENT_ENABLED" in user_dict:
            document_status = "✅ ON (User)" if document_enabled else "❌ OFF (User)"
        elif (
            hasattr(Config, "COMPRESSION_DOCUMENT_ENABLED")
            and Config.COMPRESSION_DOCUMENT_ENABLED
        ):
            document_status = "✅ ON (Global)"
        else:
            document_status = "❌ OFF"

        # Get subtitle compression status
        subtitle_enabled = user_dict.get("COMPRESSION_SUBTITLE_ENABLED", False)
        if "COMPRESSION_SUBTITLE_ENABLED" in user_dict:
            subtitle_status = "✅ ON (User)" if subtitle_enabled else "❌ OFF (User)"
        elif (
            hasattr(Config, "COMPRESSION_SUBTITLE_ENABLED")
            and Config.COMPRESSION_SUBTITLE_ENABLED
        ):
            subtitle_status = "✅ ON (Global)"
        else:
            subtitle_status = "❌ OFF"

        # Get archive compression status
        archive_enabled = user_dict.get("COMPRESSION_ARCHIVE_ENABLED", False)
        if "COMPRESSION_ARCHIVE_ENABLED" in user_dict:
            archive_status = "✅ ON (User)" if archive_enabled else "❌ OFF (User)"
        elif (
            hasattr(Config, "COMPRESSION_ARCHIVE_ENABLED")
            and Config.COMPRESSION_ARCHIVE_ENABLED
        ):
            archive_status = "✅ ON (Global)"
        else:
            archive_status = "❌ OFF"

        text = f"""⌬ <b>Compression Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ ON" if compression_enabled else "❌ OFF"}
┠ <b>Priority</b> → <code>{compression_priority}</code>
┠ <b>RO</b> → {remove_original_status}
┃
┠ <b>Video Compression</b> → {video_status}
┠ <b>Audio Compression</b> → {audio_status}
┠ <b>Image Compression</b> → {image_status}
┠ <b>Document Compression</b> → {document_status}
┠ <b>Subtitle Compression</b> → {subtitle_status}
┖ <b>Archive Compression</b> → {archive_status}"""

    elif stype == "trim":
        # Trim settings menu
        trim_enabled = user_dict.get("TRIM_ENABLED", False)
        buttons.data_button(
            f"Trim: {'✅ ON' if trim_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog TRIM_ENABLED {'f' if trim_enabled else 't'}",
        )
        buttons.data_button("Configure", f"mediatools {user_id} trim_config")
        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu TRIM_PRIORITY"
        )
        buttons.data_button("Reset", f"mediatools {user_id} reset_trim")
        buttons.data_button("Remove", f"mediatools {user_id} remove_trim")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get trim priority
        user_has_priority = "TRIM_PRIORITY" in user_dict
        if user_has_priority:
            priority = f"{user_dict['TRIM_PRIORITY']} (User)"
        elif hasattr(Config, "TRIM_PRIORITY") and Config.TRIM_PRIORITY:
            priority = f"{Config.TRIM_PRIORITY} (Global)"
        else:
            priority = "5 (Default)"

        # Get start and end time settings
        start_time = user_dict.get("TRIM_START_TIME", None)
        if start_time is None and hasattr(Config, "TRIM_START_TIME"):
            start_time = Config.TRIM_START_TIME
        start_time_str = f"{start_time}" if start_time else "00:00:00 (Default)"

        end_time = user_dict.get("TRIM_END_TIME", None)
        if end_time is None and hasattr(Config, "TRIM_END_TIME"):
            end_time = Config.TRIM_END_TIME
        end_time_str = f"{end_time}" if end_time else "End of file (Default)"

        # Get video trim status
        video_trim_enabled = user_dict.get("TRIM_VIDEO_ENABLED", False)
        owner_video_trim_enabled = (
            hasattr(Config, "TRIM_VIDEO_ENABLED") and Config.TRIM_VIDEO_ENABLED
        )

        if "TRIM_VIDEO_ENABLED" in user_dict:
            if video_trim_enabled:
                video_status = "✅ Enabled (User)"
            else:
                video_status = "❌ Disabled (User)"
        elif owner_video_trim_enabled:
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Get audio trim status
        audio_trim_enabled = user_dict.get("TRIM_AUDIO_ENABLED", False)
        owner_audio_trim_enabled = (
            hasattr(Config, "TRIM_AUDIO_ENABLED") and Config.TRIM_AUDIO_ENABLED
        )

        if "TRIM_AUDIO_ENABLED" in user_dict:
            if audio_trim_enabled:
                audio_status = "✅ Enabled (User)"
            else:
                audio_status = "❌ Disabled (User)"
        elif owner_audio_trim_enabled:
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Get image trim status
        image_trim_enabled = user_dict.get("TRIM_IMAGE_ENABLED", False)
        owner_image_trim_enabled = (
            hasattr(Config, "TRIM_IMAGE_ENABLED") and Config.TRIM_IMAGE_ENABLED
        )

        if "TRIM_IMAGE_ENABLED" in user_dict:
            if image_trim_enabled:
                image_status = "✅ Enabled (User)"
            else:
                image_status = "❌ Disabled (User)"
        elif owner_image_trim_enabled:
            image_status = "✅ Enabled (Global)"
        else:
            image_status = "❌ Disabled"

        # Get document trim status
        document_trim_enabled = user_dict.get("TRIM_DOCUMENT_ENABLED", False)
        owner_document_trim_enabled = (
            hasattr(Config, "TRIM_DOCUMENT_ENABLED") and Config.TRIM_DOCUMENT_ENABLED
        )

        if "TRIM_DOCUMENT_ENABLED" in user_dict:
            if document_trim_enabled:
                document_status = "✅ Enabled (User)"
            else:
                document_status = "❌ Disabled (User)"
        elif owner_document_trim_enabled:
            document_status = "✅ Enabled (Global)"
        else:
            document_status = "❌ Disabled"

        # Get subtitle trim status
        subtitle_trim_enabled = user_dict.get("TRIM_SUBTITLE_ENABLED", False)
        owner_subtitle_trim_enabled = (
            hasattr(Config, "TRIM_SUBTITLE_ENABLED") and Config.TRIM_SUBTITLE_ENABLED
        )

        if "TRIM_SUBTITLE_ENABLED" in user_dict:
            if subtitle_trim_enabled:
                subtitle_status = "✅ Enabled (User)"
            else:
                subtitle_status = "❌ Disabled (User)"
        elif owner_subtitle_trim_enabled:
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Get archive trim status
        archive_trim_enabled = user_dict.get("TRIM_ARCHIVE_ENABLED", False)
        owner_archive_trim_enabled = (
            hasattr(Config, "TRIM_ARCHIVE_ENABLED") and Config.TRIM_ARCHIVE_ENABLED
        )

        if "TRIM_ARCHIVE_ENABLED" in user_dict:
            if archive_trim_enabled:
                archive_status = "✅ Enabled (User)"
            else:
                archive_status = "❌ Disabled (User)"
        elif owner_archive_trim_enabled:
            archive_status = "✅ Enabled (Global)"
        else:
            archive_status = "❌ Disabled"

        # Build text for trim menu
        text = f"""⌬ <b>Trim Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if trim_enabled else "❌ Disabled"}
┠ <b>Priority</b> → {priority}
┃
┠ <b>Start Time</b> → <code>{start_time_str}</code>
┠ <b>End Time</b> → <code>{end_time_str}</code>
┃
┠ <b>Video Trim</b> → {video_status}
┠ <b>Audio Trim</b> → {audio_status}
┠ <b>Image Trim</b> → {image_status}
┠ <b>Document Trim</b> → {document_status}
┠ <b>Subtitle Trim</b> → {subtitle_status}
┃
┖ <b>Archive Trim</b> → {archive_status}"""

    elif stype == "extract":
        # Extract settings menu
        extract_enabled = user_dict.get("EXTRACT_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if extract_enabled else "❌ Disabled",
            f"mediatools {user_id} tog EXTRACT_ENABLED {'f' if extract_enabled else 't'}",
        )
        buttons.data_button("Configure", f"mediatools {user_id} extract_config")
        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu EXTRACT_PRIORITY"
        )
        buttons.data_button("Reset", f"mediatools {user_id} reset_extract")
        buttons.data_button("Remove", f"mediatools {user_id} remove_extract")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get extract priority
        user_has_priority = (
            "EXTRACT_PRIORITY" in user_dict and user_dict["EXTRACT_PRIORITY"]
        )
        if user_has_priority:
            priority = f"{user_dict['EXTRACT_PRIORITY']} (User)"
        elif hasattr(Config, "EXTRACT_PRIORITY") and Config.EXTRACT_PRIORITY:
            priority = f"{Config.EXTRACT_PRIORITY} (Global)"
        else:
            priority = "6 (Default)"

        # Get RO toggle status (Remove Original)
        remove_original = user_dict.get("EXTRACT_DELETE_ORIGINAL", True)
        if "EXTRACT_DELETE_ORIGINAL" in user_dict:
            remove_original_status = (
                "✅ Enabled (User)" if remove_original else "❌ Disabled (User)"
            )
        elif hasattr(Config, "EXTRACT_DELETE_ORIGINAL"):
            remove_original_status = (
                "✅ Enabled (Global)"
                if Config.EXTRACT_DELETE_ORIGINAL
                else "❌ Disabled (Global)"
            )
        else:
            remove_original_status = "✅ Enabled (Default)"

        # Get video extract status
        video_enabled = user_dict.get("EXTRACT_VIDEO_ENABLED", False)
        if "EXTRACT_VIDEO_ENABLED" in user_dict:
            video_status = (
                "✅ Enabled (User)" if video_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "EXTRACT_VIDEO_ENABLED") and Config.EXTRACT_VIDEO_ENABLED
        ):
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Get audio extract status
        audio_enabled = user_dict.get("EXTRACT_AUDIO_ENABLED", False)
        if "EXTRACT_AUDIO_ENABLED" in user_dict:
            audio_status = (
                "✅ Enabled (User)" if audio_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "EXTRACT_AUDIO_ENABLED") and Config.EXTRACT_AUDIO_ENABLED
        ):
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Get subtitle extract status
        subtitle_enabled = user_dict.get("EXTRACT_SUBTITLE_ENABLED", False)
        if "EXTRACT_SUBTITLE_ENABLED" in user_dict:
            subtitle_status = (
                "✅ Enabled (User)" if subtitle_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "EXTRACT_SUBTITLE_ENABLED")
            and Config.EXTRACT_SUBTITLE_ENABLED
        ):
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Get attachment extract status
        attachment_enabled = user_dict.get("EXTRACT_ATTACHMENT_ENABLED", False)
        if "EXTRACT_ATTACHMENT_ENABLED" in user_dict:
            attachment_status = (
                "✅ Enabled (User)" if attachment_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "EXTRACT_ATTACHMENT_ENABLED")
            and Config.EXTRACT_ATTACHMENT_ENABLED
        ):
            attachment_status = "✅ Enabled (Global)"
        else:
            attachment_status = "❌ Disabled"

        text = f"""⌬ <b>Extract Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if extract_enabled else "❌ Disabled"}
┠ <b>Priority</b> → <code>{priority}</code>
┠ <b>RO</b> → {remove_original_status}
┃
┠ <b>Video Extract</b> → {video_status}
┠ <b>Audio Extract</b> → {audio_status}
┠ <b>Subtitle Extract</b> → {subtitle_status}
┖ <b>Attachment Extract</b> → {attachment_status}"""

    elif stype == "remove":
        # Remove settings menu
        remove_enabled = user_dict.get("REMOVE_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if remove_enabled else "❌ Disabled",
            f"mediatools {user_id} tog REMOVE_ENABLED {'f' if remove_enabled else 't'}",
        )
        buttons.data_button("Configure", f"mediatools {user_id} remove_config")
        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu REMOVE_PRIORITY"
        )

        # Add RO toggle button (Remove Original)
        # Use global setting as fallback when user hasn't set it explicitly
        remove_original = user_dict.get(
            "REMOVE_DELETE_ORIGINAL", Config.REMOVE_DELETE_ORIGINAL
        )
        buttons.data_button(
            f"RO: {'✅ ON' if remove_original else '❌ OFF'}",
            f"mediatools {user_id} tog REMOVE_DELETE_ORIGINAL {'f' if remove_original else 't'}",
        )

        buttons.data_button("Reset", f"mediatools {user_id} reset_remove")
        buttons.data_button("Remove", f"mediatools {user_id} remove_remove")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get remove priority
        user_has_priority = (
            "REMOVE_PRIORITY" in user_dict and user_dict["REMOVE_PRIORITY"]
        )
        if user_has_priority:
            priority = f"{user_dict['REMOVE_PRIORITY']} (User)"
        elif hasattr(Config, "REMOVE_PRIORITY") and Config.REMOVE_PRIORITY:
            priority = f"{Config.REMOVE_PRIORITY} (Global)"
        else:
            priority = "8 (Default)"

        # Get RO toggle status (Remove Original)
        remove_original = user_dict.get("REMOVE_DELETE_ORIGINAL", True)
        if "REMOVE_DELETE_ORIGINAL" in user_dict:
            remove_original_status = (
                "✅ Enabled (User)" if remove_original else "❌ Disabled (User)"
            )
        elif hasattr(Config, "REMOVE_DELETE_ORIGINAL"):
            remove_original_status = (
                "✅ Enabled (Global)"
                if Config.REMOVE_DELETE_ORIGINAL
                else "❌ Disabled (Global)"
            )
        else:
            remove_original_status = "✅ Enabled (Default)"

        # Get metadata remove status
        metadata_remove = user_dict.get("REMOVE_METADATA", False)
        if "REMOVE_METADATA" in user_dict:
            metadata_status = (
                "✅ Enabled (User)" if metadata_remove else "❌ Disabled (User)"
            )
        elif hasattr(Config, "REMOVE_METADATA"):
            metadata_status = (
                "✅ Enabled (Global)"
                if Config.REMOVE_METADATA
                else "❌ Disabled (Global)"
            )
        else:
            metadata_status = "❌ Disabled (Default)"

        # Get video remove status
        video_enabled = user_dict.get("REMOVE_VIDEO_ENABLED", False)
        if "REMOVE_VIDEO_ENABLED" in user_dict:
            video_status = (
                "✅ Enabled (User)" if video_enabled else "❌ Disabled (User)"
            )
        elif hasattr(Config, "REMOVE_VIDEO_ENABLED") and Config.REMOVE_VIDEO_ENABLED:
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Get audio remove status
        audio_enabled = user_dict.get("REMOVE_AUDIO_ENABLED", False)
        if "REMOVE_AUDIO_ENABLED" in user_dict:
            audio_status = (
                "✅ Enabled (User)" if audio_enabled else "❌ Disabled (User)"
            )
        elif hasattr(Config, "REMOVE_AUDIO_ENABLED") and Config.REMOVE_AUDIO_ENABLED:
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Get subtitle remove status
        subtitle_enabled = user_dict.get("REMOVE_SUBTITLE_ENABLED", False)
        if "REMOVE_SUBTITLE_ENABLED" in user_dict:
            subtitle_status = (
                "✅ Enabled (User)" if subtitle_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "REMOVE_SUBTITLE_ENABLED")
            and Config.REMOVE_SUBTITLE_ENABLED
        ):
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Get attachment remove status
        attachment_enabled = user_dict.get("REMOVE_ATTACHMENT_ENABLED", False)
        if "REMOVE_ATTACHMENT_ENABLED" in user_dict:
            attachment_status = (
                "✅ Enabled (User)" if attachment_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "REMOVE_ATTACHMENT_ENABLED")
            and Config.REMOVE_ATTACHMENT_ENABLED
        ):
            attachment_status = "✅ Enabled (Global)"
        else:
            attachment_status = "❌ Disabled"

        text = f"""⌬ <b>Remove Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if remove_enabled else "❌ Disabled"}
┠ <b>Priority</b> → <code>{priority}</code>
┠ <b>RO</b> → {remove_original_status}
┠ <b>Metadata</b> → {metadata_status}
┃
┠ <b>Video Remove</b> → {video_status}
┠ <b>Audio Remove</b> → {audio_status}
┠ <b>Subtitle Remove</b> → {subtitle_status}
┖ <b>Attachment Remove</b> → {attachment_status}

<b>Usage:</b>
• Remove specific tracks or metadata from media files
• Use indices to remove specific tracks: <code>-remove-video-index 0,1</code>
• Remove all tracks of a type: <code>-remove-audio</code>
• Remove metadata: <code>-remove-metadata</code>
• Example: <code>/leech url -remove-video-index 1 -remove-metadata</code>"""

    elif stype == "add":
        # Add settings menu
        add_enabled = user_dict.get("ADD_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if add_enabled else "❌ Disabled",
            f"mediatools {user_id} tog ADD_ENABLED {'f' if add_enabled else 't'}",
        )
        buttons.data_button("Configure", f"mediatools {user_id} add_config")
        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu ADD_PRIORITY"
        )
        buttons.data_button("Reset", f"mediatools {user_id} reset_add")
        buttons.data_button("Remove", f"mediatools {user_id} remove_add")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get add priority
        user_has_priority = "ADD_PRIORITY" in user_dict
        if user_has_priority:
            priority = f"{user_dict['ADD_PRIORITY']} (User)"
        elif hasattr(Config, "ADD_PRIORITY") and Config.ADD_PRIORITY:
            priority = f"{Config.ADD_PRIORITY} (Global)"
        else:
            priority = "7 (Default)"

        # Get RO toggle status (Remove Original)
        remove_original = user_dict.get("ADD_DELETE_ORIGINAL", True)
        owner_remove_original_enabled = (
            hasattr(Config, "ADD_DELETE_ORIGINAL") and Config.ADD_DELETE_ORIGINAL
        )

        if "ADD_DELETE_ORIGINAL" in user_dict:
            if remove_original:
                remove_original_status = "✅ Enabled (User)"
            else:
                remove_original_status = "❌ Disabled (User)"
        elif owner_remove_original_enabled:
            remove_original_status = "✅ Enabled (Global)"
        else:
            remove_original_status = "✅ Enabled (Default)"

        # Get preserve tracks status
        preserve_tracks_enabled = user_dict.get("ADD_PRESERVE_TRACKS", False)
        owner_preserve_tracks_enabled = (
            hasattr(Config, "ADD_PRESERVE_TRACKS") and Config.ADD_PRESERVE_TRACKS
        )

        # Get replace tracks status
        replace_tracks_enabled = user_dict.get("ADD_REPLACE_TRACKS", False)
        owner_replace_tracks_enabled = (
            hasattr(Config, "ADD_REPLACE_TRACKS") and Config.ADD_REPLACE_TRACKS
        )

        # Get video add status
        video_add_enabled = user_dict.get("ADD_VIDEO_ENABLED", False)
        owner_video_add_enabled = (
            hasattr(Config, "ADD_VIDEO_ENABLED") and Config.ADD_VIDEO_ENABLED
        )

        if "ADD_VIDEO_ENABLED" in user_dict:
            if video_add_enabled:
                video_status = "✅ Enabled (User)"
            else:
                video_status = "❌ Disabled (User)"
        elif owner_video_add_enabled:
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Get audio add status
        audio_add_enabled = user_dict.get("ADD_AUDIO_ENABLED", False)
        owner_audio_add_enabled = (
            hasattr(Config, "ADD_AUDIO_ENABLED") and Config.ADD_AUDIO_ENABLED
        )

        if "ADD_AUDIO_ENABLED" in user_dict:
            if audio_add_enabled:
                audio_status = "✅ Enabled (User)"
            else:
                audio_status = "❌ Disabled (User)"
        elif owner_audio_add_enabled:
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Get subtitle add status
        subtitle_add_enabled = user_dict.get("ADD_SUBTITLE_ENABLED", False)
        owner_subtitle_add_enabled = (
            hasattr(Config, "ADD_SUBTITLE_ENABLED") and Config.ADD_SUBTITLE_ENABLED
        )

        if "ADD_SUBTITLE_ENABLED" in user_dict:
            if subtitle_add_enabled:
                subtitle_status = "✅ Enabled (User)"
            else:
                subtitle_status = "❌ Disabled (User)"
        elif owner_subtitle_add_enabled:
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Get attachment add status
        attachment_add_enabled = user_dict.get("ADD_ATTACHMENT_ENABLED", False)
        owner_attachment_add_enabled = (
            hasattr(Config, "ADD_ATTACHMENT_ENABLED")
            and Config.ADD_ATTACHMENT_ENABLED
        )

        if "ADD_ATTACHMENT_ENABLED" in user_dict:
            if attachment_add_enabled:
                attachment_status = "✅ Enabled (User)"
            else:
                attachment_status = "❌ Disabled (User)"
        elif owner_attachment_add_enabled:
            attachment_status = "✅ Enabled (Global)"
        else:
            attachment_status = "❌ Disabled"

        text = f"""⌬ <b>Add Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if add_enabled else "❌ Disabled"}
┠ <b>Priority</b> → {priority}
┠ <b>RO</b> → {remove_original_status}
┠ <b>Preserve</b> → {"✅ Enabled" if preserve_tracks_enabled else "❌ Disabled"}
┠ <b>Replace</b> → {"✅ Enabled" if replace_tracks_enabled else "❌ Disabled"}
┃
┠ <b>Video Add</b> → {video_status}
┠ <b>Audio Add</b> → {audio_status}
┠ <b>Subtitle Add</b> → {subtitle_status}
┠ <b>Attachment Add</b> → {attachment_status}
┃
┖ <b>Multi-Input Mode:</b> Use <code>-m</code> flag to specify multiple input files
   Example: <code>/leech https://example.com/video.mp4 -add -m folder_name</code>"""

    elif stype == "swap":
        # Swap settings menu
        swap_enabled = user_dict.get("SWAP_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if swap_enabled else "❌ Disabled",
            f"mediatools {user_id} tog SWAP_ENABLED {'f' if swap_enabled else 't'}",
        )

        # Sub-menus for different track types
        buttons.data_button("Audio Swap", f"mediatools {user_id} swap_audio")
        buttons.data_button("Video Swap", f"mediatools {user_id} swap_video")
        buttons.data_button("Subtitle Swap", f"mediatools {user_id} swap_subtitle")

        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu SWAP_PRIORITY"
        )

        # Add RO toggle button (Remove Original)
        # Use global setting as fallback when user hasn't set it explicitly
        remove_original = user_dict.get(
            "SWAP_REMOVE_ORIGINAL",
            Config.SWAP_REMOVE_ORIGINAL
            if hasattr(Config, "SWAP_REMOVE_ORIGINAL")
            else False,
        )
        buttons.data_button(
            f"RO: {'✅ ON' if remove_original else '❌ OFF'}",
            f"mediatools {user_id} tog SWAP_REMOVE_ORIGINAL {'f' if remove_original else 't'}",
        )

        buttons.data_button("Reset", f"mediatools {user_id} reset_swap")
        buttons.data_button("Remove", f"mediatools {user_id} remove_swap")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get swap priority
        user_has_priority = (
            "SWAP_PRIORITY" in user_dict and user_dict["SWAP_PRIORITY"]
        )
        if user_has_priority:
            priority = f"{user_dict['SWAP_PRIORITY']} (User)"
        elif hasattr(Config, "SWAP_PRIORITY") and Config.SWAP_PRIORITY:
            priority = f"{Config.SWAP_PRIORITY} (Global)"
        else:
            priority = "6 (Default)"

        # Get RO toggle status (Remove Original)
        remove_original = user_dict.get(
            "SWAP_REMOVE_ORIGINAL",
            Config.SWAP_REMOVE_ORIGINAL
            if hasattr(Config, "SWAP_REMOVE_ORIGINAL")
            else False,
        )
        owner_remove_original_enabled = (
            hasattr(Config, "SWAP_REMOVE_ORIGINAL") and Config.SWAP_REMOVE_ORIGINAL
        )

        if "SWAP_REMOVE_ORIGINAL" in user_dict:
            if remove_original:
                remove_original_status = "✅ Enabled (User)"
            else:
                remove_original_status = "❌ Disabled (User)"
        elif owner_remove_original_enabled:
            remove_original_status = "✅ Enabled (Global)"
        else:
            remove_original_status = "❌ Disabled (Default)"

        text = f"""⌬ <b>Swap Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if swap_enabled else "❌ Disabled"}
┠ <b>Priority</b> → {priority}
┠ <b>RO</b> → {remove_original_status}
┃
┠ <b>Audio Swap</b> → Configure audio track swapping
┠ <b>Video Swap</b> → Configure video track swapping
┠ <b>Subtitle Swap</b> → Configure subtitle track swapping
┃
┖ <b>Usage:</b> Swap reorders tracks based on language or index priority
   Example: <code>/leech https://example.com/video.mkv -swap</code>"""

    elif stype == "swap_audio":
        # Audio Swap settings menu
        audio_swap_enabled = user_dict.get("SWAP_AUDIO_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if audio_swap_enabled else "❌ Disabled",
            f"mediatools {user_id} tog SWAP_AUDIO_ENABLED {'f' if audio_swap_enabled else 't'}",
        )

        # Language/Index toggle
        use_language = user_dict.get("SWAP_AUDIO_USE_LANGUAGE", True)
        buttons.data_button(
            f"Mode: {'🌐 Language' if use_language else '🔢 Index'}",
            f"mediatools {user_id} tog SWAP_AUDIO_USE_LANGUAGE {'f' if use_language else 't'}",
        )

        # Configuration buttons
        buttons.data_button(
            "Language Order", f"mediatools {user_id} menu SWAP_AUDIO_LANGUAGE_ORDER"
        )
        buttons.data_button(
            "Index Order", f"mediatools {user_id} menu SWAP_AUDIO_INDEX_ORDER"
        )

        buttons.data_button("Back", f"mediatools {user_id} swap", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get current settings
        language_order = user_dict.get("SWAP_AUDIO_LANGUAGE_ORDER", "eng,hin")
        index_order = user_dict.get("SWAP_AUDIO_INDEX_ORDER", "0,1")

        text = f"""🎵 <b>Audio Swap Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if audio_swap_enabled else "❌ Disabled"}
┠ <b>Mode</b> → {"🌐 Language-based" if use_language else "🔢 Index-based"}
┃
┠ <b>Language Order</b> → <code>{language_order}</code>
┠ <b>Index Order</b> → <code>{index_order}</code>
┃
┖ <b>Usage:</b>
  • Language mode: Reorders audio tracks by language priority
    Example: <code>eng,hin</code> puts English first, Hindi second
  • Index mode: Swaps audio tracks at specific positions
    Example: <code>1,2</code> swaps track at index 1 with track at index 2"""

    elif stype == "swap_video":
        # Video Swap settings menu
        video_swap_enabled = user_dict.get("SWAP_VIDEO_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if video_swap_enabled else "❌ Disabled",
            f"mediatools {user_id} tog SWAP_VIDEO_ENABLED {'f' if video_swap_enabled else 't'}",
        )

        # Language/Index toggle
        use_language = user_dict.get("SWAP_VIDEO_USE_LANGUAGE", True)
        buttons.data_button(
            f"Mode: {'🌐 Language' if use_language else '🔢 Index'}",
            f"mediatools {user_id} tog SWAP_VIDEO_USE_LANGUAGE {'f' if use_language else 't'}",
        )

        # Configuration buttons
        buttons.data_button(
            "Language Order", f"mediatools {user_id} menu SWAP_VIDEO_LANGUAGE_ORDER"
        )
        buttons.data_button(
            "Index Order", f"mediatools {user_id} menu SWAP_VIDEO_INDEX_ORDER"
        )

        buttons.data_button("Back", f"mediatools {user_id} swap", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get current settings
        language_order = user_dict.get("SWAP_VIDEO_LANGUAGE_ORDER", "eng,hin")
        index_order = user_dict.get("SWAP_VIDEO_INDEX_ORDER", "0,1")

        text = f"""🎬 <b>Video Swap Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if video_swap_enabled else "❌ Disabled"}
┠ <b>Mode</b> → {"🌐 Language-based" if use_language else "🔢 Index-based"}
┃
┠ <b>Language Order</b> → <code>{language_order}</code>
┠ <b>Index Order</b> → <code>{index_order}</code>
┃
┖ <b>Usage:</b>
  • Language mode: Reorders video tracks by language priority
    Example: <code>eng,hin</code> puts English first, Hindi second
  • Index mode: Swaps video tracks at specific positions
    Example: <code>1,2</code> swaps track at index 1 with track at index 2"""

    elif stype == "swap_subtitle":
        # Subtitle Swap settings menu
        subtitle_swap_enabled = user_dict.get("SWAP_SUBTITLE_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if subtitle_swap_enabled else "❌ Disabled",
            f"mediatools {user_id} tog SWAP_SUBTITLE_ENABLED {'f' if subtitle_swap_enabled else 't'}",
        )

        # Language/Index toggle
        use_language = user_dict.get("SWAP_SUBTITLE_USE_LANGUAGE", True)
        buttons.data_button(
            f"Mode: {'🌐 Language' if use_language else '🔢 Index'}",
            f"mediatools {user_id} tog SWAP_SUBTITLE_USE_LANGUAGE {'f' if use_language else 't'}",
        )

        # Configuration buttons
        buttons.data_button(
            "Language Order",
            f"mediatools {user_id} menu SWAP_SUBTITLE_LANGUAGE_ORDER",
        )
        buttons.data_button(
            "Index Order", f"mediatools {user_id} menu SWAP_SUBTITLE_INDEX_ORDER"
        )

        buttons.data_button("Back", f"mediatools {user_id} swap", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get current settings
        language_order = user_dict.get("SWAP_SUBTITLE_LANGUAGE_ORDER", "eng,hin")
        index_order = user_dict.get("SWAP_SUBTITLE_INDEX_ORDER", "0,1")

        text = f"""💬 <b>Subtitle Swap Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if subtitle_swap_enabled else "❌ Disabled"}
┠ <b>Mode</b> → {"🌐 Language-based" if use_language else "🔢 Index-based"}
┃
┠ <b>Language Order</b> → <code>{language_order}</code>
┠ <b>Index Order</b> → <code>{index_order}</code>
┃
┖ <b>Usage:</b>
  • Language mode: Reorders subtitle tracks by language priority
    Example: <code>eng,hin</code> puts English first, Hindi second
  • Index mode: Swaps subtitle tracks at specific positions
    Example: <code>1,2</code> swaps track at index 1 with track at index 2"""

    elif stype == "trim_config":
        # Trim configuration menu# Add start time and end time settings at the top
        buttons.data_button(
            "Start Time", f"mediatools {user_id} menu TRIM_START_TIME"
        )
        buttons.data_button("End Time", f"mediatools {user_id} menu TRIM_END_TIME")

        # Add RO toggle button (Remove Original)
        # Check for user setting first, then global setting, then default to True
        remove_original = user_dict.get("TRIM_DELETE_ORIGINAL", None)
        if remove_original is None and hasattr(Config, "TRIM_DELETE_ORIGINAL"):
            remove_original = Config.TRIM_DELETE_ORIGINAL
        elif remove_original is None:
            remove_original = True  # Default to True if not specified

        buttons.data_button(
            f"RO: {'✅ ON' if remove_original else '❌ OFF'}",
            f"mediatools {user_id} tog TRIM_DELETE_ORIGINAL {'f' if remove_original else 't'}",
        )

        # Format settings button removed as requested

        # Video trim settings
        video_enabled = user_dict.get("TRIM_VIDEO_ENABLED", False)
        buttons.data_button(
            f"Video: {'✅ ON' if video_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog TRIM_VIDEO_ENABLED {'f' if video_enabled else 't'}",
        )
        buttons.data_button(
            "Video Codec", f"mediatools {user_id} menu TRIM_VIDEO_CODEC"
        )
        buttons.data_button(
            "Video Preset", f"mediatools {user_id} menu TRIM_VIDEO_PRESET"
        )
        buttons.data_button(
            "Video Format", f"mediatools {user_id} menu TRIM_VIDEO_FORMAT"
        )

        # Audio trim settings
        audio_enabled = user_dict.get("TRIM_AUDIO_ENABLED", False)
        buttons.data_button(
            f"Audio: {'✅ ON' if audio_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog TRIM_AUDIO_ENABLED {'f' if audio_enabled else 't'}",
        )
        buttons.data_button(
            "Audio Codec", f"mediatools {user_id} menu TRIM_AUDIO_CODEC"
        )
        buttons.data_button(
            "Audio Preset", f"mediatools {user_id} menu TRIM_AUDIO_PRESET"
        )
        buttons.data_button(
            "Audio Format", f"mediatools {user_id} menu TRIM_AUDIO_FORMAT"
        )

        # Image trim settings
        image_enabled = user_dict.get("TRIM_IMAGE_ENABLED", False)
        buttons.data_button(
            f"Image: {'✅ ON' if image_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog TRIM_IMAGE_ENABLED {'f' if image_enabled else 't'}",
        )
        buttons.data_button(
            "Image Quality", f"mediatools {user_id} menu TRIM_IMAGE_QUALITY"
        )
        buttons.data_button(
            "Image Format", f"mediatools {user_id} menu TRIM_IMAGE_FORMAT"
        )

        # Document trim settings
        document_enabled = user_dict.get("TRIM_DOCUMENT_ENABLED", False)
        buttons.data_button(
            f"Document: {'✅ ON' if document_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog TRIM_DOCUMENT_ENABLED {'f' if document_enabled else 't'}",
        )
        buttons.data_button(
            "Document Start Page",
            f"mediatools {user_id} menu TRIM_DOCUMENT_START_PAGE",
        )
        buttons.data_button(
            "Document End Page", f"mediatools {user_id} menu TRIM_DOCUMENT_END_PAGE"
        )
        buttons.data_button(
            "Document Quality", f"mediatools {user_id} menu TRIM_DOCUMENT_QUALITY"
        )
        buttons.data_button(
            "Document Format", f"mediatools {user_id} menu TRIM_DOCUMENT_FORMAT"
        )

        # Subtitle trim settings
        subtitle_enabled = user_dict.get("TRIM_SUBTITLE_ENABLED", False)
        buttons.data_button(
            f"Subtitle: {'✅ ON' if subtitle_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog TRIM_SUBTITLE_ENABLED {'f' if subtitle_enabled else 't'}",
        )
        buttons.data_button(
            "Subtitle Encoding", f"mediatools {user_id} menu TRIM_SUBTITLE_ENCODING"
        )
        buttons.data_button(
            "Subtitle Format", f"mediatools {user_id} menu TRIM_SUBTITLE_FORMAT"
        )

        # Archive trim settings
        archive_enabled = user_dict.get("TRIM_ARCHIVE_ENABLED", False)
        buttons.data_button(
            f"Archive: {'✅ ON' if archive_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog TRIM_ARCHIVE_ENABLED {'f' if archive_enabled else 't'}",
        )
        buttons.data_button(
            "Archive Format", f"mediatools {user_id} menu TRIM_ARCHIVE_FORMAT"
        )

        buttons.data_button("Back", f"mediatools {user_id} trim", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)  # Get start and end time settings
        start_time = user_dict.get("TRIM_START_TIME", None)
        if start_time is None and hasattr(Config, "TRIM_START_TIME"):
            start_time = Config.TRIM_START_TIME
        start_time_str = f"{start_time}" if start_time else "00:00:00 (Default)"

        end_time = user_dict.get("TRIM_END_TIME", None)
        if end_time is None and hasattr(Config, "TRIM_END_TIME"):
            end_time = Config.TRIM_END_TIME
        end_time_str = f"{end_time}" if end_time else "End of file (Default)"

        # Get RO toggle status (Remove Original)
        # Check for user setting first, then global setting, then default to True
        remove_original = user_dict.get("TRIM_DELETE_ORIGINAL", None)
        if remove_original is None and hasattr(Config, "TRIM_DELETE_ORIGINAL"):
            remove_original = Config.TRIM_DELETE_ORIGINAL
        elif remove_original is None:
            remove_original = True  # Default to True if not specified

        # Determine display string with appropriate label
        if "TRIM_DELETE_ORIGINAL" in user_dict:
            remove_original_str = (
                f"{'✅ Enabled' if remove_original else '❌ Disabled'} (User)"
            )
        elif hasattr(Config, "TRIM_DELETE_ORIGINAL"):
            remove_original_str = (
                f"{'✅ Enabled' if remove_original else '❌ Disabled'} (Global)"
            )
        else:
            remove_original_str = "✅ Enabled (Default)"

        # Get video trim settings
        video_codec = user_dict.get("TRIM_VIDEO_CODEC", None)
        if video_codec is None and hasattr(Config, "TRIM_VIDEO_CODEC"):
            video_codec = Config.TRIM_VIDEO_CODEC
        video_codec_str = f"{video_codec}" if video_codec else "copy (Default)"

        video_preset = user_dict.get("TRIM_VIDEO_PRESET", None)
        if video_preset is None and hasattr(Config, "TRIM_VIDEO_PRESET"):
            video_preset = Config.TRIM_VIDEO_PRESET
        video_preset_str = f"{video_preset}" if video_preset else "medium (Default)"

        video_format = user_dict.get("TRIM_VIDEO_FORMAT", None)
        if video_format is None and hasattr(Config, "TRIM_VIDEO_FORMAT"):
            video_format = Config.TRIM_VIDEO_FORMAT
        video_format_str = (
            f"{video_format}"
            if video_format and video_format != "none"
            else "Same as input (Default)"
        )

        # Get audio trim settings
        audio_codec = user_dict.get("TRIM_AUDIO_CODEC", None)
        if audio_codec is None and hasattr(Config, "TRIM_AUDIO_CODEC"):
            audio_codec = Config.TRIM_AUDIO_CODEC
        audio_codec_str = f"{audio_codec}" if audio_codec else "copy (Default)"

        audio_preset = user_dict.get("TRIM_AUDIO_PRESET", None)
        if audio_preset is None and hasattr(Config, "TRIM_AUDIO_PRESET"):
            audio_preset = Config.TRIM_AUDIO_PRESET
        audio_preset_str = f"{audio_preset}" if audio_preset else "medium (Default)"

        audio_format = user_dict.get("TRIM_AUDIO_FORMAT", None)
        if audio_format is None and hasattr(Config, "TRIM_AUDIO_FORMAT"):
            audio_format = Config.TRIM_AUDIO_FORMAT
        audio_format_str = (
            f"{audio_format}"
            if audio_format and audio_format != "none"
            else "Same as input (Default)"
        )

        # Get image trim settings
        image_quality = user_dict.get("TRIM_IMAGE_QUALITY", "none")
        if image_quality is None and hasattr(Config, "TRIM_IMAGE_QUALITY"):
            image_quality = Config.TRIM_IMAGE_QUALITY
        if not image_quality or image_quality in {"none", "0", 0}:
            image_quality_str = "none (Default - Original Quality)"
        else:
            image_quality_str = f"{image_quality}"

        image_format = user_dict.get("TRIM_IMAGE_FORMAT", None)
        if image_format is None and hasattr(Config, "TRIM_IMAGE_FORMAT"):
            image_format = Config.TRIM_IMAGE_FORMAT
        image_format_str = (
            f"{image_format}"
            if image_format and image_format != "none"
            else "Same as input (Default)"
        )

        # Get document trim settings
        document_start_page = user_dict.get("TRIM_DOCUMENT_START_PAGE", None)
        if document_start_page is None and hasattr(
            Config, "TRIM_DOCUMENT_START_PAGE"
        ):
            document_start_page = Config.TRIM_DOCUMENT_START_PAGE
        document_start_page_str = (
            f"{document_start_page}" if document_start_page else "1 (Default)"
        )

        document_end_page = user_dict.get("TRIM_DOCUMENT_END_PAGE", None)
        if document_end_page is None and hasattr(Config, "TRIM_DOCUMENT_END_PAGE"):
            document_end_page = Config.TRIM_DOCUMENT_END_PAGE
        document_end_page_str = (
            f"{document_end_page}" if document_end_page else "Last page (Default)"
        )

        document_quality = user_dict.get("TRIM_DOCUMENT_QUALITY", "none")
        if document_quality is None and hasattr(Config, "TRIM_DOCUMENT_QUALITY"):
            document_quality = Config.TRIM_DOCUMENT_QUALITY
        if not document_quality or document_quality in {"none", "0", 0}:
            document_quality_str = "none (Default - Original Quality)"
        else:
            document_quality_str = f"{document_quality}"

        document_format = user_dict.get("TRIM_DOCUMENT_FORMAT", None)
        if document_format is None and hasattr(Config, "TRIM_DOCUMENT_FORMAT"):
            document_format = Config.TRIM_DOCUMENT_FORMAT
        document_format_str = (
            f"{document_format}"
            if document_format and document_format != "none"
            else "Same as input (Default)"
        )

        # Get subtitle trim settings
        subtitle_encoding = user_dict.get("TRIM_SUBTITLE_ENCODING", None)
        if subtitle_encoding is None and hasattr(Config, "TRIM_SUBTITLE_ENCODING"):
            subtitle_encoding = Config.TRIM_SUBTITLE_ENCODING
        subtitle_encoding_str = (
            f"{subtitle_encoding}" if subtitle_encoding else "utf-8 (Default)"
        )

        subtitle_format = user_dict.get("TRIM_SUBTITLE_FORMAT", None)
        if subtitle_format is None and hasattr(Config, "TRIM_SUBTITLE_FORMAT"):
            subtitle_format = Config.TRIM_SUBTITLE_FORMAT
        subtitle_format_str = (
            f"{subtitle_format}"
            if subtitle_format and subtitle_format != "none"
            else "Same as input (Default)"
        )

        # Get archive trim settings
        archive_format = user_dict.get("TRIM_ARCHIVE_FORMAT", None)
        if archive_format is None and hasattr(Config, "TRIM_ARCHIVE_FORMAT"):
            archive_format = Config.TRIM_ARCHIVE_FORMAT
        archive_format_str = (
            f"{archive_format}"
            if archive_format and archive_format != "none"
            else "Same as input (Default)"
        )

        # Get trim enabled status for each type
        # Video trim status
        video_trim_enabled = user_dict.get("TRIM_VIDEO_ENABLED", False)
        owner_video_trim_enabled = (
            hasattr(Config, "TRIM_VIDEO_ENABLED") and Config.TRIM_VIDEO_ENABLED
        )

        if "TRIM_VIDEO_ENABLED" in user_dict:
            if video_trim_enabled:
                video_status = "✅ Enabled (User)"
            else:
                video_status = "❌ Disabled (User)"
        elif owner_video_trim_enabled:
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Audio trim status
        audio_trim_enabled = user_dict.get("TRIM_AUDIO_ENABLED", False)
        owner_audio_trim_enabled = (
            hasattr(Config, "TRIM_AUDIO_ENABLED") and Config.TRIM_AUDIO_ENABLED
        )

        if "TRIM_AUDIO_ENABLED" in user_dict:
            if audio_trim_enabled:
                audio_status = "✅ Enabled (User)"
            else:
                audio_status = "❌ Disabled (User)"
        elif owner_audio_trim_enabled:
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Image trim status
        image_trim_enabled = user_dict.get("TRIM_IMAGE_ENABLED", False)
        owner_image_trim_enabled = (
            hasattr(Config, "TRIM_IMAGE_ENABLED") and Config.TRIM_IMAGE_ENABLED
        )

        if "TRIM_IMAGE_ENABLED" in user_dict:
            if image_trim_enabled:
                image_status = "✅ Enabled (User)"
            else:
                image_status = "❌ Disabled (User)"
        elif owner_image_trim_enabled:
            image_status = "✅ Enabled (Global)"
        else:
            image_status = "❌ Disabled"

        # Document trim status
        document_trim_enabled = user_dict.get("TRIM_DOCUMENT_ENABLED", False)
        owner_document_trim_enabled = (
            hasattr(Config, "TRIM_DOCUMENT_ENABLED") and Config.TRIM_DOCUMENT_ENABLED
        )

        if "TRIM_DOCUMENT_ENABLED" in user_dict:
            if document_trim_enabled:
                document_status = "✅ Enabled (User)"
            else:
                document_status = "❌ Disabled (User)"
        elif owner_document_trim_enabled:
            document_status = "✅ Enabled (Global)"
        else:
            document_status = "❌ Disabled"

        # Subtitle trim status
        subtitle_trim_enabled = user_dict.get("TRIM_SUBTITLE_ENABLED", False)
        owner_subtitle_trim_enabled = (
            hasattr(Config, "TRIM_SUBTITLE_ENABLED") and Config.TRIM_SUBTITLE_ENABLED
        )

        if "TRIM_SUBTITLE_ENABLED" in user_dict:
            if subtitle_trim_enabled:
                subtitle_status = "✅ Enabled (User)"
            else:
                subtitle_status = "❌ Disabled (User)"
        elif owner_subtitle_trim_enabled:
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Archive trim status
        archive_trim_enabled = user_dict.get("TRIM_ARCHIVE_ENABLED", False)
        owner_archive_trim_enabled = (
            hasattr(Config, "TRIM_ARCHIVE_ENABLED") and Config.TRIM_ARCHIVE_ENABLED
        )

        if "TRIM_ARCHIVE_ENABLED" in user_dict:
            if archive_trim_enabled:
                archive_status = "✅ Enabled (User)"
            else:
                archive_status = "❌ Disabled (User)"
        elif owner_archive_trim_enabled:
            archive_status = "✅ Enabled (Global)"
        else:
            archive_status = "❌ Disabled"

        # Build text for trim_config
        text = f"""⌬ <b>Trim Configuration :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Start Time</b> → <code>{start_time_str}</code>
┠ <b>End Time</b> → <code>{end_time_str}</code>
┠ <b>RO (Remove Original)</b> → {remove_original_str}
┃
┠ <b>Video Trim</b> → {video_status}
┠ <b>Video Codec</b> → <code>{video_codec_str}</code>
┠ <b>Video Preset</b> → <code>{video_preset_str}</code>
┠ <b>Video Format</b> → <code>{video_format_str}</code>
┃
┠ <b>Audio Trim</b> → {audio_status}
┠ <b>Audio Codec</b> → <code>{audio_codec_str}</code>
┠ <b>Audio Preset</b> → <code>{audio_preset_str}</code>
┠ <b>Audio Format</b> → <code>{audio_format_str}</code>
┃
┠ <b>Image Trim</b> → {image_status}
┠ <b>Image Quality</b> → <code>{image_quality_str}</code>
┠ <b>Image Format</b> → <code>{image_format_str}</code>
┃
┠ <b>Document Trim</b> → {document_status}
┠ <b>Document Start Page</b> → <code>{document_start_page_str}</code>
┠ <b>Document End Page</b> → <code>{document_end_page_str}</code>
┠ <b>Document Quality</b> → <code>{document_quality_str}</code>
┠ <b>Document Format</b> → <code>{document_format_str}</code>
┃
┠ <b>Subtitle Trim</b> → {subtitle_status}
┠ <b>Subtitle Encoding</b> → <code>{subtitle_encoding_str}</code>
┠ <b>Subtitle Format</b> → <code>{subtitle_format_str}</code>
┃
┠ <b>Archive Trim</b> → {archive_status}
┠ <b>Archive Format</b> → <code>{archive_format_str}</code>
┃
┖ <b>Note:</b> Settings with value 'none' will not be used in command generation"""

    elif stype == "extract_config":
        # Extract configuration menu
        # Video extract settings
        video_enabled = user_dict.get("EXTRACT_VIDEO_ENABLED", False)
        buttons.data_button(
            f"Video: {'✅ ON' if video_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_VIDEO_ENABLED {'f' if video_enabled else 't'}",
        )
        buttons.data_button(
            "Video Codec", f"mediatools {user_id} menu EXTRACT_VIDEO_CODEC"
        )
        buttons.data_button(
            "Video Format", f"mediatools {user_id} menu EXTRACT_VIDEO_FORMAT"
        )
        buttons.data_button(
            "Video Index", f"mediatools {user_id} menu EXTRACT_VIDEO_INDEX"
        )
        buttons.data_button(
            "Video Quality", f"mediatools {user_id} menu EXTRACT_VIDEO_QUALITY"
        )
        buttons.data_button(
            "Video Preset", f"mediatools {user_id} menu EXTRACT_VIDEO_PRESET"
        )
        buttons.data_button(
            "Video Bitrate", f"mediatools {user_id} menu EXTRACT_VIDEO_BITRATE"
        )
        buttons.data_button(
            "Video Resolution", f"mediatools {user_id} menu EXTRACT_VIDEO_RESOLUTION"
        )
        buttons.data_button(
            "Video FPS", f"mediatools {user_id} menu EXTRACT_VIDEO_FPS"
        )

        # Audio extract settings
        audio_enabled = user_dict.get("EXTRACT_AUDIO_ENABLED", False)
        buttons.data_button(
            f"Audio: {'✅ ON' if audio_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_AUDIO_ENABLED {'f' if audio_enabled else 't'}",
        )
        buttons.data_button(
            "Audio Codec", f"mediatools {user_id} menu EXTRACT_AUDIO_CODEC"
        )
        buttons.data_button(
            "Audio Format", f"mediatools {user_id} menu EXTRACT_AUDIO_FORMAT"
        )
        buttons.data_button(
            "Audio Index", f"mediatools {user_id} menu EXTRACT_AUDIO_INDEX"
        )
        buttons.data_button(
            "Audio Bitrate", f"mediatools {user_id} menu EXTRACT_AUDIO_BITRATE"
        )
        buttons.data_button(
            "Audio Channels", f"mediatools {user_id} menu EXTRACT_AUDIO_CHANNELS"
        )
        buttons.data_button(
            "Audio Sampling", f"mediatools {user_id} menu EXTRACT_AUDIO_SAMPLING"
        )
        buttons.data_button(
            "Audio Volume", f"mediatools {user_id} menu EXTRACT_AUDIO_VOLUME"
        )

        # Subtitle extract settings
        subtitle_enabled = user_dict.get("EXTRACT_SUBTITLE_ENABLED", False)
        buttons.data_button(
            f"Subtitle: {'✅ ON' if subtitle_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_SUBTITLE_ENABLED {'f' if subtitle_enabled else 't'}",
        )
        buttons.data_button(
            "Subtitle Codec", f"mediatools {user_id} menu EXTRACT_SUBTITLE_CODEC"
        )
        buttons.data_button(
            "Subtitle Format", f"mediatools {user_id} menu EXTRACT_SUBTITLE_FORMAT"
        )
        buttons.data_button(
            "Subtitle Index", f"mediatools {user_id} menu EXTRACT_SUBTITLE_INDEX"
        )
        buttons.data_button(
            "Subtitle Language",
            f"mediatools {user_id} menu EXTRACT_SUBTITLE_LANGUAGE",
        )
        buttons.data_button(
            "Subtitle Encoding",
            f"mediatools {user_id} menu EXTRACT_SUBTITLE_ENCODING",
        )
        buttons.data_button(
            "Subtitle Font", f"mediatools {user_id} menu EXTRACT_SUBTITLE_FONT"
        )
        buttons.data_button(
            "Subtitle Font Size",
            f"mediatools {user_id} menu EXTRACT_SUBTITLE_FONT_SIZE",
        )

        # Attachment extract settings
        attachment_enabled = user_dict.get("EXTRACT_ATTACHMENT_ENABLED", False)
        buttons.data_button(
            f"Attachment: {'✅ ON' if attachment_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_ATTACHMENT_ENABLED {'f' if attachment_enabled else 't'}",
        )
        buttons.data_button(
            "Attachment Format",
            f"mediatools {user_id} menu EXTRACT_ATTACHMENT_FORMAT",
        )
        buttons.data_button(
            "Attachment Index", f"mediatools {user_id} menu EXTRACT_ATTACHMENT_INDEX"
        )
        buttons.data_button(
            "Attachment Filter",
            f"mediatools {user_id} menu EXTRACT_ATTACHMENT_FILTER",
        )

        # Maintain quality toggle
        maintain_quality = user_dict.get("EXTRACT_MAINTAIN_QUALITY", True)
        buttons.data_button(
            f"Quality: {'✅ High' if maintain_quality else '❌ Normal'}",
            f"mediatools {user_id} tog EXTRACT_MAINTAIN_QUALITY {'f' if maintain_quality else 't'}",
        )

        # Delete original toggle
        delete_original = user_dict.get("EXTRACT_DELETE_ORIGINAL", True)
        buttons.data_button(
            f"RO: {'✅ ON' if delete_original else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_DELETE_ORIGINAL {'f' if delete_original else 't'}",
        )

        buttons.data_button("Back", f"mediatools {user_id} extract", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get video extract settings
        video_codec = user_dict.get("EXTRACT_VIDEO_CODEC", None)
        if video_codec is None and hasattr(Config, "EXTRACT_VIDEO_CODEC"):
            video_codec = Config.EXTRACT_VIDEO_CODEC
        video_codec_str = f"{video_codec}" if video_codec else "None (Default)"

        video_format = user_dict.get("EXTRACT_VIDEO_FORMAT", None)
        if video_format is None and hasattr(Config, "EXTRACT_VIDEO_FORMAT"):
            video_format = Config.EXTRACT_VIDEO_FORMAT
        video_format_str = f"{video_format}" if video_format else "None (Default)"

        video_index = user_dict.get("EXTRACT_VIDEO_INDEX", None)
        if video_index is None and hasattr(Config, "EXTRACT_VIDEO_INDEX"):
            video_index = Config.EXTRACT_VIDEO_INDEX
        video_index_str = (
            f"{video_index}" if video_index is not None else "All (Default)"
        )

        video_quality = user_dict.get("EXTRACT_VIDEO_QUALITY", None)
        if video_quality is None and hasattr(Config, "EXTRACT_VIDEO_QUALITY"):
            video_quality = Config.EXTRACT_VIDEO_QUALITY
        video_quality_str = f"{video_quality}" if video_quality else "None (Default)"

        video_preset = user_dict.get("EXTRACT_VIDEO_PRESET", None)
        if video_preset is None and hasattr(Config, "EXTRACT_VIDEO_PRESET"):
            video_preset = Config.EXTRACT_VIDEO_PRESET
        video_preset_str = f"{video_preset}" if video_preset else "None (Default)"

        video_bitrate = user_dict.get("EXTRACT_VIDEO_BITRATE", None)
        if video_bitrate is None and hasattr(Config, "EXTRACT_VIDEO_BITRATE"):
            video_bitrate = Config.EXTRACT_VIDEO_BITRATE
        video_bitrate_str = f"{video_bitrate}" if video_bitrate else "None (Default)"

        video_resolution = user_dict.get("EXTRACT_VIDEO_RESOLUTION", None)
        if video_resolution is None and hasattr(Config, "EXTRACT_VIDEO_RESOLUTION"):
            video_resolution = Config.EXTRACT_VIDEO_RESOLUTION
        video_resolution_str = (
            f"{video_resolution}" if video_resolution else "None (Default)"
        )

        video_fps = user_dict.get("EXTRACT_VIDEO_FPS", None)
        if video_fps is None and hasattr(Config, "EXTRACT_VIDEO_FPS"):
            video_fps = Config.EXTRACT_VIDEO_FPS
        video_fps_str = f"{video_fps}" if video_fps else "None (Default)"

        # Get audio extract settings
        audio_codec = user_dict.get("EXTRACT_AUDIO_CODEC", None)
        if audio_codec is None and hasattr(Config, "EXTRACT_AUDIO_CODEC"):
            audio_codec = Config.EXTRACT_AUDIO_CODEC
        audio_codec_str = f"{audio_codec}" if audio_codec else "None (Default)"

        audio_format = user_dict.get("EXTRACT_AUDIO_FORMAT", None)
        if audio_format is None and hasattr(Config, "EXTRACT_AUDIO_FORMAT"):
            audio_format = Config.EXTRACT_AUDIO_FORMAT
        audio_format_str = f"{audio_format}" if audio_format else "None (Default)"

        audio_index = user_dict.get("EXTRACT_AUDIO_INDEX", None)
        if audio_index is None and hasattr(Config, "EXTRACT_AUDIO_INDEX"):
            audio_index = Config.EXTRACT_AUDIO_INDEX
        audio_index_str = (
            f"{audio_index}" if audio_index is not None else "All (Default)"
        )

        audio_bitrate = user_dict.get("EXTRACT_AUDIO_BITRATE", None)
        if audio_bitrate is None and hasattr(Config, "EXTRACT_AUDIO_BITRATE"):
            audio_bitrate = Config.EXTRACT_AUDIO_BITRATE
        audio_bitrate_str = f"{audio_bitrate}" if audio_bitrate else "None (Default)"

        audio_channels = user_dict.get("EXTRACT_AUDIO_CHANNELS", None)
        if audio_channels is None and hasattr(Config, "EXTRACT_AUDIO_CHANNELS"):
            audio_channels = Config.EXTRACT_AUDIO_CHANNELS
        audio_channels_str = (
            f"{audio_channels}" if audio_channels else "None (Default)"
        )

        audio_sampling = user_dict.get("EXTRACT_AUDIO_SAMPLING", None)
        if audio_sampling is None and hasattr(Config, "EXTRACT_AUDIO_SAMPLING"):
            audio_sampling = Config.EXTRACT_AUDIO_SAMPLING
        audio_sampling_str = (
            f"{audio_sampling}" if audio_sampling else "None (Default)"
        )

        audio_volume = user_dict.get("EXTRACT_AUDIO_VOLUME", None)
        if audio_volume is None and hasattr(Config, "EXTRACT_AUDIO_VOLUME"):
            audio_volume = Config.EXTRACT_AUDIO_VOLUME
        audio_volume_str = f"{audio_volume}" if audio_volume else "None (Default)"

        # Get subtitle extract settings
        subtitle_codec = user_dict.get("EXTRACT_SUBTITLE_CODEC", None)
        if subtitle_codec is None and hasattr(Config, "EXTRACT_SUBTITLE_CODEC"):
            subtitle_codec = Config.EXTRACT_SUBTITLE_CODEC
        subtitle_codec_str = (
            f"{subtitle_codec}" if subtitle_codec else "None (Default)"
        )

        subtitle_format = user_dict.get("EXTRACT_SUBTITLE_FORMAT", None)
        if subtitle_format is None and hasattr(Config, "EXTRACT_SUBTITLE_FORMAT"):
            subtitle_format = Config.EXTRACT_SUBTITLE_FORMAT
        subtitle_format_str = (
            f"{subtitle_format}" if subtitle_format else "None (Default)"
        )

        subtitle_index = user_dict.get("EXTRACT_SUBTITLE_INDEX", None)
        if subtitle_index is None and hasattr(Config, "EXTRACT_SUBTITLE_INDEX"):
            subtitle_index = Config.EXTRACT_SUBTITLE_INDEX
        subtitle_index_str = (
            f"{subtitle_index}" if subtitle_index is not None else "All (Default)"
        )

        subtitle_language = user_dict.get("EXTRACT_SUBTITLE_LANGUAGE", None)
        if subtitle_language is None and hasattr(
            Config, "EXTRACT_SUBTITLE_LANGUAGE"
        ):
            subtitle_language = Config.EXTRACT_SUBTITLE_LANGUAGE
        subtitle_language_str = (
            f"{subtitle_language}" if subtitle_language else "None (Default)"
        )

        subtitle_encoding = user_dict.get("EXTRACT_SUBTITLE_ENCODING", None)
        if subtitle_encoding is None and hasattr(
            Config, "EXTRACT_SUBTITLE_ENCODING"
        ):
            subtitle_encoding = Config.EXTRACT_SUBTITLE_ENCODING
        subtitle_encoding_str = (
            f"{subtitle_encoding}" if subtitle_encoding else "None (Default)"
        )

        subtitle_font = user_dict.get("EXTRACT_SUBTITLE_FONT", None)
        if subtitle_font is None and hasattr(Config, "EXTRACT_SUBTITLE_FONT"):
            subtitle_font = Config.EXTRACT_SUBTITLE_FONT
        subtitle_font_str = f"{subtitle_font}" if subtitle_font else "None (Default)"

        subtitle_font_size = user_dict.get("EXTRACT_SUBTITLE_FONT_SIZE", None)
        if subtitle_font_size is None and hasattr(
            Config, "EXTRACT_SUBTITLE_FONT_SIZE"
        ):
            subtitle_font_size = Config.EXTRACT_SUBTITLE_FONT_SIZE
        subtitle_font_size_str = (
            f"{subtitle_font_size}" if subtitle_font_size else "None (Default)"
        )

        # Get attachment extract settings
        attachment_format = user_dict.get("EXTRACT_ATTACHMENT_FORMAT", None)
        if attachment_format is None and hasattr(
            Config, "EXTRACT_ATTACHMENT_FORMAT"
        ):
            attachment_format = Config.EXTRACT_ATTACHMENT_FORMAT
        attachment_format_str = (
            f"{attachment_format}" if attachment_format else "None (Default)"
        )

        attachment_index = user_dict.get("EXTRACT_ATTACHMENT_INDEX", None)
        if attachment_index is None and hasattr(Config, "EXTRACT_ATTACHMENT_INDEX"):
            attachment_index = Config.EXTRACT_ATTACHMENT_INDEX
        attachment_index_str = (
            f"{attachment_index}"
            if attachment_index is not None
            else "All (Default)"
        )

        attachment_filter = user_dict.get("EXTRACT_ATTACHMENT_FILTER", None)
        if attachment_filter is None and hasattr(
            Config, "EXTRACT_ATTACHMENT_FILTER"
        ):
            attachment_filter = Config.EXTRACT_ATTACHMENT_FILTER
        attachment_filter_str = (
            f"{attachment_filter}" if attachment_filter else "None (Default)"
        )

        # Get extract enabled status for each type
        # Video extract status
        video_extract_enabled = user_dict.get("EXTRACT_VIDEO_ENABLED", False)
        owner_video_extract_enabled = (
            hasattr(Config, "EXTRACT_VIDEO_ENABLED") and Config.EXTRACT_VIDEO_ENABLED
        )

        if "EXTRACT_VIDEO_ENABLED" in user_dict:
            if video_extract_enabled:
                video_status = "✅ Enabled (User)"
            else:
                video_status = "❌ Disabled (User)"
        elif owner_video_extract_enabled:
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Audio extract status
        audio_extract_enabled = user_dict.get("EXTRACT_AUDIO_ENABLED", False)
        owner_audio_extract_enabled = (
            hasattr(Config, "EXTRACT_AUDIO_ENABLED") and Config.EXTRACT_AUDIO_ENABLED
        )

        if "EXTRACT_AUDIO_ENABLED" in user_dict:
            if audio_extract_enabled:
                audio_status = "✅ Enabled (User)"
            else:
                audio_status = "❌ Disabled (User)"
        elif owner_audio_extract_enabled:
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Subtitle extract status
        subtitle_extract_enabled = user_dict.get("EXTRACT_SUBTITLE_ENABLED", False)
        owner_subtitle_extract_enabled = (
            hasattr(Config, "EXTRACT_SUBTITLE_ENABLED")
            and Config.EXTRACT_SUBTITLE_ENABLED
        )

        if "EXTRACT_SUBTITLE_ENABLED" in user_dict:
            if subtitle_extract_enabled:
                subtitle_status = "✅ Enabled (User)"
            else:
                subtitle_status = "❌ Disabled (User)"
        elif owner_subtitle_extract_enabled:
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Attachment extract status
        attachment_extract_enabled = user_dict.get(
            "EXTRACT_ATTACHMENT_ENABLED", False
        )
        owner_attachment_extract_enabled = (
            hasattr(Config, "EXTRACT_ATTACHMENT_ENABLED")
            and Config.EXTRACT_ATTACHMENT_ENABLED
        )

        if "EXTRACT_ATTACHMENT_ENABLED" in user_dict:
            if attachment_extract_enabled:
                attachment_status = "✅ Enabled (User)"
            else:
                attachment_status = "❌ Disabled (User)"
        elif owner_attachment_extract_enabled:
            attachment_status = "✅ Enabled (Global)"
        else:
            attachment_status = "❌ Disabled"

        # Get maintain quality status
        maintain_quality_enabled = user_dict.get("EXTRACT_MAINTAIN_QUALITY", True)
        owner_maintain_quality_enabled = (
            hasattr(Config, "EXTRACT_MAINTAIN_QUALITY")
            and Config.EXTRACT_MAINTAIN_QUALITY
        )

        if "EXTRACT_MAINTAIN_QUALITY" in user_dict:
            if maintain_quality_enabled:
                maintain_quality_status = "✅ Enabled (User)"
            else:
                maintain_quality_status = "❌ Disabled (User)"
        elif owner_maintain_quality_enabled:
            maintain_quality_status = "✅ Enabled (Global)"
        else:
            maintain_quality_status = "✅ Enabled (Default)"

        # Get delete original status
        delete_original_enabled = user_dict.get("EXTRACT_DELETE_ORIGINAL", True)
        owner_delete_original_enabled = (
            hasattr(Config, "EXTRACT_DELETE_ORIGINAL")
            and Config.EXTRACT_DELETE_ORIGINAL
        )

        if "EXTRACT_DELETE_ORIGINAL" in user_dict:
            if delete_original_enabled:
                delete_original_status = "✅ Enabled (User)"
            else:
                delete_original_status = "❌ Disabled (User)"
        elif owner_delete_original_enabled:
            delete_original_status = "✅ Enabled (Global)"
        else:
            delete_original_status = "✅ Enabled (Default)"

        text = f"""⌬ <b>Extract Configuration :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Video Extract</b> → {video_status}
┠ <b>Video Codec</b> → <code>{video_codec_str}</code>
┠ <b>Video Format</b> → <code>{video_format_str}</code>
┠ <b>Video Index</b> → <code>{video_index_str}</code>
┠ <b>Video Quality</b> → <code>{video_quality_str}</code>
┠ <b>Video Preset</b> → <code>{video_preset_str}</code>
┠ <b>Video Bitrate</b> → <code>{video_bitrate_str}</code>
┠ <b>Video Resolution</b> → <code>{video_resolution_str}</code>
┠ <b>Video FPS</b> → <code>{video_fps_str}</code>
┃
┠ <b>Audio Extract</b> → {audio_status}
┠ <b>Audio Codec</b> → <code>{audio_codec_str}</code>
┠ <b>Audio Format</b> → <code>{audio_format_str}</code>
┠ <b>Audio Index</b> → <code>{audio_index_str}</code>
┠ <b>Audio Bitrate</b> → <code>{audio_bitrate_str}</code>
┠ <b>Audio Channels</b> → <code>{audio_channels_str}</code>
┠ <b>Audio Sampling</b> → <code>{audio_sampling_str}</code>
┠ <b>Audio Volume</b> → <code>{audio_volume_str}</code>
┃
┠ <b>Subtitle Extract</b> → {subtitle_status}
┠ <b>Subtitle Codec</b> → <code>{subtitle_codec_str}</code>
┠ <b>Subtitle Format</b> → <code>{subtitle_format_str}</code>
┠ <b>Subtitle Index</b> → <code>{subtitle_index_str}</code>
┠ <b>Subtitle Language</b> → <code>{subtitle_language_str}</code>
┠ <b>Subtitle Encoding</b> → <code>{subtitle_encoding_str}</code>
┠ <b>Subtitle Font</b> → <code>{subtitle_font_str}</code>
┠ <b>Subtitle Font Size</b> → <code>{subtitle_font_size_str}</code>
┃
┠ <b>Attachment Extract</b> → {attachment_status}
┠ <b>Attachment Format</b> → <code>{attachment_format_str}</code>
┠ <b>Attachment Index</b> → <code>{attachment_index_str}</code>
┠ <b>Attachment Filter</b> → <code>{attachment_filter_str}</code>
┃
┠ <b>Maintain Quality</b> → {maintain_quality_status}
┖ <b>RO</b> → {delete_original_status}"""

    elif stype == "remove_config":
        # Remove configuration menu
        # Video remove settings
        video_enabled = user_dict.get("REMOVE_VIDEO_ENABLED", False)
        buttons.data_button(
            f"Video: {'✅ ON' if video_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog REMOVE_VIDEO_ENABLED {'f' if video_enabled else 't'}",
        )
        buttons.data_button(
            "Video Settings", f"mediatools {user_id} remove_video_config"
        )

        # Audio remove settings
        audio_enabled = user_dict.get("REMOVE_AUDIO_ENABLED", False)
        buttons.data_button(
            f"Audio: {'✅ ON' if audio_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog REMOVE_AUDIO_ENABLED {'f' if audio_enabled else 't'}",
        )
        buttons.data_button(
            "Audio Settings", f"mediatools {user_id} remove_audio_config"
        )

        # Subtitle remove settings
        subtitle_enabled = user_dict.get("REMOVE_SUBTITLE_ENABLED", False)
        buttons.data_button(
            f"Subtitle: {'✅ ON' if subtitle_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog REMOVE_SUBTITLE_ENABLED {'f' if subtitle_enabled else 't'}",
        )
        buttons.data_button(
            "Subtitle Settings", f"mediatools {user_id} remove_subtitle_config"
        )

        # Attachment remove settings
        attachment_enabled = user_dict.get("REMOVE_ATTACHMENT_ENABLED", False)
        buttons.data_button(
            f"Attachment: {'✅ ON' if attachment_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog REMOVE_ATTACHMENT_ENABLED {'f' if attachment_enabled else 't'}",
        )
        buttons.data_button(
            "Attachment Settings", f"mediatools {user_id} remove_attachment_config"
        )

        # Metadata remove toggle
        metadata_remove = user_dict.get("REMOVE_METADATA", False)
        buttons.data_button(
            f"Metadata: {'✅ ON' if metadata_remove else '❌ OFF'}",
            f"mediatools {user_id} tog REMOVE_METADATA {'f' if metadata_remove else 't'}",
        )

        # Maintain quality toggle
        maintain_quality = user_dict.get("REMOVE_MAINTAIN_QUALITY", True)
        buttons.data_button(
            f"Quality: {'✅ ON' if maintain_quality else '❌ OFF'}",
            f"mediatools {user_id} tog REMOVE_MAINTAIN_QUALITY {'f' if maintain_quality else 't'}",
        )

        # Delete original toggle
        delete_original = user_dict.get("REMOVE_DELETE_ORIGINAL", True)
        buttons.data_button(
            f"RO: {'✅ ON' if delete_original else '❌ OFF'}",
            f"mediatools {user_id} tog REMOVE_DELETE_ORIGINAL {'f' if delete_original else 't'}",
        )

        buttons.data_button("Back", f"mediatools {user_id} remove", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get remove settings
        video_index = user_dict.get("REMOVE_VIDEO_INDEX", None)
        if video_index is None and hasattr(Config, "REMOVE_VIDEO_INDEX"):
            video_index = Config.REMOVE_VIDEO_INDEX
        video_index_str = (
            f"{video_index}" if video_index is not None else "All (Default)"
        )

        audio_index = user_dict.get("REMOVE_AUDIO_INDEX", None)
        if audio_index is None and hasattr(Config, "REMOVE_AUDIO_INDEX"):
            audio_index = Config.REMOVE_AUDIO_INDEX
        audio_index_str = (
            f"{audio_index}" if audio_index is not None else "All (Default)"
        )

        subtitle_index = user_dict.get("REMOVE_SUBTITLE_INDEX", None)
        if subtitle_index is None and hasattr(Config, "REMOVE_SUBTITLE_INDEX"):
            subtitle_index = Config.REMOVE_SUBTITLE_INDEX
        subtitle_index_str = (
            f"{subtitle_index}" if subtitle_index is not None else "All (Default)"
        )

        attachment_index = user_dict.get("REMOVE_ATTACHMENT_INDEX", None)
        if attachment_index is None and hasattr(Config, "REMOVE_ATTACHMENT_INDEX"):
            attachment_index = Config.REMOVE_ATTACHMENT_INDEX
        attachment_index_str = (
            f"{attachment_index}"
            if attachment_index is not None
            else "All (Default)"
        )

        # Get remove enabled status for each type
        # Video remove status
        video_remove_enabled = user_dict.get("REMOVE_VIDEO_ENABLED", False)
        owner_video_remove_enabled = (
            hasattr(Config, "REMOVE_VIDEO_ENABLED") and Config.REMOVE_VIDEO_ENABLED
        )

        if "REMOVE_VIDEO_ENABLED" in user_dict:
            if video_remove_enabled:
                video_status = "✅ Enabled (User)"
            else:
                video_status = "❌ Disabled (User)"
        elif owner_video_remove_enabled:
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Audio remove status
        audio_remove_enabled = user_dict.get("REMOVE_AUDIO_ENABLED", False)
        owner_audio_remove_enabled = (
            hasattr(Config, "REMOVE_AUDIO_ENABLED") and Config.REMOVE_AUDIO_ENABLED
        )

        if "REMOVE_AUDIO_ENABLED" in user_dict:
            if audio_remove_enabled:
                audio_status = "✅ Enabled (User)"
            else:
                audio_status = "❌ Disabled (User)"
        elif owner_audio_remove_enabled:
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Subtitle remove status
        subtitle_remove_enabled = user_dict.get("REMOVE_SUBTITLE_ENABLED", False)
        owner_subtitle_remove_enabled = (
            hasattr(Config, "REMOVE_SUBTITLE_ENABLED")
            and Config.REMOVE_SUBTITLE_ENABLED
        )

        if "REMOVE_SUBTITLE_ENABLED" in user_dict:
            if subtitle_remove_enabled:
                subtitle_status = "✅ Enabled (User)"
            else:
                subtitle_status = "❌ Disabled (User)"
        elif owner_subtitle_remove_enabled:
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Attachment remove status
        attachment_remove_enabled = user_dict.get("REMOVE_ATTACHMENT_ENABLED", False)
        owner_attachment_remove_enabled = (
            hasattr(Config, "REMOVE_ATTACHMENT_ENABLED")
            and Config.REMOVE_ATTACHMENT_ENABLED
        )

        if "REMOVE_ATTACHMENT_ENABLED" in user_dict:
            if attachment_remove_enabled:
                attachment_status = "✅ Enabled (User)"
            else:
                attachment_status = "❌ Disabled (User)"
        elif owner_attachment_remove_enabled:
            attachment_status = "✅ Enabled (Global)"
        else:
            attachment_status = "❌ Disabled"

        # Get metadata remove status
        metadata_remove_enabled = user_dict.get("REMOVE_METADATA", False)
        owner_metadata_remove_enabled = (
            hasattr(Config, "REMOVE_METADATA") and Config.REMOVE_METADATA
        )

        if "REMOVE_METADATA" in user_dict:
            if metadata_remove_enabled:
                metadata_status = "✅ Enabled (User)"
            else:
                metadata_status = "❌ Disabled (User)"
        elif owner_metadata_remove_enabled:
            metadata_status = "✅ Enabled (Global)"
        else:
            metadata_status = "❌ Disabled"

        # Get delete original status
        delete_original_enabled = user_dict.get("REMOVE_DELETE_ORIGINAL", True)
        owner_delete_original_enabled = (
            hasattr(Config, "REMOVE_DELETE_ORIGINAL")
            and Config.REMOVE_DELETE_ORIGINAL
        )

        if "REMOVE_DELETE_ORIGINAL" in user_dict:
            if delete_original_enabled:
                delete_original_status = "✅ Enabled (User)"
            else:
                delete_original_status = "❌ Disabled (User)"
        elif owner_delete_original_enabled:
            delete_original_status = "✅ Enabled (Global)"
        else:
            delete_original_status = "✅ Enabled (Default)"

        text = f"""⌬ <b>Remove Configuration :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Video Remove</b> → {video_status}
┠ <b>Video Index</b> → <code>{video_index_str}</code>
┃
┠ <b>Audio Remove</b> → {audio_status}
┠ <b>Audio Index</b> → <code>{audio_index_str}</code>
┃
┠ <b>Subtitle Remove</b> → {subtitle_status}
┠ <b>Subtitle Index</b> → <code>{subtitle_index_str}</code>
┃
┠ <b>Attachment Remove</b> → {attachment_status}
┠ <b>Attachment Index</b> → <code>{attachment_index_str}</code>
┃
┠ <b>Metadata Remove</b> → {metadata_status}
┖ <b>RO</b> → {delete_original_status}

<b>Usage:</b>
• Remove specific tracks or metadata from media files
• Use indices to remove specific tracks: <code>0,1,2</code> or <code>0-2</code>
• Remove all tracks of a type by enabling the type without specifying indices
• Remove metadata to strip file information
• Example: Remove video tracks 0 and 1: <code>-remove-video-index 0,1</code>
• Example: Remove all audio tracks: <code>-remove-audio</code>"""

    elif stype == "remove_video_config":
        # Video remove configuration menu
        buttons.data_button("Codec", f"mediatools {user_id} menu REMOVE_VIDEO_CODEC")
        buttons.data_button(
            "Format", f"mediatools {user_id} menu REMOVE_VIDEO_FORMAT"
        )
        buttons.data_button("Index", f"mediatools {user_id} menu REMOVE_VIDEO_INDEX")
        buttons.data_button(
            "Quality", f"mediatools {user_id} menu REMOVE_VIDEO_QUALITY"
        )
        buttons.data_button(
            "Preset", f"mediatools {user_id} menu REMOVE_VIDEO_PRESET"
        )
        buttons.data_button(
            "Bitrate", f"mediatools {user_id} menu REMOVE_VIDEO_BITRATE"
        )
        buttons.data_button(
            "Resolution", f"mediatools {user_id} menu REMOVE_VIDEO_RESOLUTION"
        )
        buttons.data_button("FPS", f"mediatools {user_id} menu REMOVE_VIDEO_FPS")

        buttons.data_button("Back", f"mediatools {user_id} remove_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get video remove settings
        video_codec = user_dict.get("REMOVE_VIDEO_CODEC", "none")
        if video_codec == "none" and hasattr(Config, "REMOVE_VIDEO_CODEC"):
            video_codec = Config.REMOVE_VIDEO_CODEC
        video_codec_str = (
            f"{video_codec}" if video_codec != "none" else "none (Default)"
        )

        video_format = user_dict.get("REMOVE_VIDEO_FORMAT", "none")
        if video_format == "none" and hasattr(Config, "REMOVE_VIDEO_FORMAT"):
            video_format = Config.REMOVE_VIDEO_FORMAT
        video_format_str = (
            f"{video_format}" if video_format != "none" else "none (Default)"
        )

        video_index = user_dict.get("REMOVE_VIDEO_INDEX", None)
        if video_index is None and hasattr(Config, "REMOVE_VIDEO_INDEX"):
            video_index = Config.REMOVE_VIDEO_INDEX
        video_index_str = (
            f"{video_index}" if video_index is not None else "All (Default)"
        )

        video_quality = user_dict.get("REMOVE_VIDEO_QUALITY", "none")
        if video_quality == "none" and hasattr(Config, "REMOVE_VIDEO_QUALITY"):
            video_quality = Config.REMOVE_VIDEO_QUALITY
        video_quality_str = (
            f"{video_quality}" if video_quality != "none" else "none (Default)"
        )

        video_preset = user_dict.get("REMOVE_VIDEO_PRESET", "none")
        if video_preset == "none" and hasattr(Config, "REMOVE_VIDEO_PRESET"):
            video_preset = Config.REMOVE_VIDEO_PRESET
        video_preset_str = (
            f"{video_preset}" if video_preset != "none" else "none (Default)"
        )

        video_bitrate = user_dict.get("REMOVE_VIDEO_BITRATE", "none")
        if video_bitrate == "none" and hasattr(Config, "REMOVE_VIDEO_BITRATE"):
            video_bitrate = Config.REMOVE_VIDEO_BITRATE
        video_bitrate_str = (
            f"{video_bitrate}" if video_bitrate != "none" else "none (Default)"
        )

        video_resolution = user_dict.get("REMOVE_VIDEO_RESOLUTION", "none")
        if video_resolution == "none" and hasattr(Config, "REMOVE_VIDEO_RESOLUTION"):
            video_resolution = Config.REMOVE_VIDEO_RESOLUTION
        video_resolution_str = (
            f"{video_resolution}" if video_resolution != "none" else "none (Default)"
        )

        video_fps = user_dict.get("REMOVE_VIDEO_FPS", "none")
        if video_fps == "none" and hasattr(Config, "REMOVE_VIDEO_FPS"):
            video_fps = Config.REMOVE_VIDEO_FPS
        video_fps_str = f"{video_fps}" if video_fps != "none" else "none (Default)"

        text = f"""⌬ <b>Video Remove Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Codec</b> → <code>{video_codec_str}</code>
┠ <b>Format</b> → <code>{video_format_str}</code>
┠ <b>Index</b> → <code>{video_index_str}</code>
┠ <b>Quality</b> → <code>{video_quality_str}</code>
┠ <b>Preset</b> → <code>{video_preset_str}</code>
┠ <b>Bitrate</b> → <code>{video_bitrate_str}</code>
┠ <b>Resolution</b> → <code>{video_resolution_str}</code>
┖ <b>FPS</b> → <code>{video_fps_str}</code>

<b>Usage:</b>
• Configure video processing settings for removal
• Use 'none' to disable specific settings
• Index specifies which video tracks to remove
• Other settings control output quality and format"""

    elif stype == "remove_audio_config":
        # Audio remove configuration menu
        buttons.data_button("Codec", f"mediatools {user_id} menu REMOVE_AUDIO_CODEC")
        buttons.data_button(
            "Format", f"mediatools {user_id} menu REMOVE_AUDIO_FORMAT"
        )
        buttons.data_button("Index", f"mediatools {user_id} menu REMOVE_AUDIO_INDEX")
        buttons.data_button(
            "Bitrate", f"mediatools {user_id} menu REMOVE_AUDIO_BITRATE"
        )
        buttons.data_button(
            "Channels", f"mediatools {user_id} menu REMOVE_AUDIO_CHANNELS"
        )
        buttons.data_button(
            "Sampling", f"mediatools {user_id} menu REMOVE_AUDIO_SAMPLING"
        )
        buttons.data_button(
            "Volume", f"mediatools {user_id} menu REMOVE_AUDIO_VOLUME"
        )

        buttons.data_button("Back", f"mediatools {user_id} remove_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get audio remove settings
        audio_codec = user_dict.get("REMOVE_AUDIO_CODEC", "none")
        if audio_codec == "none" and hasattr(Config, "REMOVE_AUDIO_CODEC"):
            audio_codec = Config.REMOVE_AUDIO_CODEC
        audio_codec_str = (
            f"{audio_codec}" if audio_codec != "none" else "none (Default)"
        )

        audio_format = user_dict.get("REMOVE_AUDIO_FORMAT", "none")
        if audio_format == "none" and hasattr(Config, "REMOVE_AUDIO_FORMAT"):
            audio_format = Config.REMOVE_AUDIO_FORMAT
        audio_format_str = (
            f"{audio_format}" if audio_format != "none" else "none (Default)"
        )

        audio_index = user_dict.get("REMOVE_AUDIO_INDEX", None)
        if audio_index is None and hasattr(Config, "REMOVE_AUDIO_INDEX"):
            audio_index = Config.REMOVE_AUDIO_INDEX
        audio_index_str = (
            f"{audio_index}" if audio_index is not None else "All (Default)"
        )

        audio_bitrate = user_dict.get("REMOVE_AUDIO_BITRATE", "none")
        if audio_bitrate == "none" and hasattr(Config, "REMOVE_AUDIO_BITRATE"):
            audio_bitrate = Config.REMOVE_AUDIO_BITRATE
        audio_bitrate_str = (
            f"{audio_bitrate}" if audio_bitrate != "none" else "none (Default)"
        )

        audio_channels = user_dict.get("REMOVE_AUDIO_CHANNELS", "none")
        if audio_channels == "none" and hasattr(Config, "REMOVE_AUDIO_CHANNELS"):
            audio_channels = Config.REMOVE_AUDIO_CHANNELS
        audio_channels_str = (
            f"{audio_channels}" if audio_channels != "none" else "none (Default)"
        )

        audio_sampling = user_dict.get("REMOVE_AUDIO_SAMPLING", "none")
        if audio_sampling == "none" and hasattr(Config, "REMOVE_AUDIO_SAMPLING"):
            audio_sampling = Config.REMOVE_AUDIO_SAMPLING
        audio_sampling_str = (
            f"{audio_sampling}" if audio_sampling != "none" else "none (Default)"
        )

        audio_volume = user_dict.get("REMOVE_AUDIO_VOLUME", "none")
        if audio_volume == "none" and hasattr(Config, "REMOVE_AUDIO_VOLUME"):
            audio_volume = Config.REMOVE_AUDIO_VOLUME
        audio_volume_str = (
            f"{audio_volume}" if audio_volume != "none" else "none (Default)"
        )

        text = f"""⌬ <b>Audio Remove Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Codec</b> → <code>{audio_codec_str}</code>
┠ <b>Format</b> → <code>{audio_format_str}</code>
┠ <b>Index</b> → <code>{audio_index_str}</code>
┠ <b>Bitrate</b> → <code>{audio_bitrate_str}</code>
┠ <b>Channels</b> → <code>{audio_channels_str}</code>
┠ <b>Sampling</b> → <code>{audio_sampling_str}</code>
┖ <b>Volume</b> → <code>{audio_volume_str}</code>

<b>Usage:</b>
• Configure audio processing settings for removal
• Use 'none' to disable specific settings
• Index specifies which audio tracks to remove
• Other settings control output quality and format"""

    elif stype == "remove_subtitle_config":
        # Subtitle remove configuration menu
        buttons.data_button(
            "Codec", f"mediatools {user_id} menu REMOVE_SUBTITLE_CODEC"
        )
        buttons.data_button(
            "Format", f"mediatools {user_id} menu REMOVE_SUBTITLE_FORMAT"
        )
        buttons.data_button(
            "Index", f"mediatools {user_id} menu REMOVE_SUBTITLE_INDEX"
        )
        buttons.data_button(
            "Language", f"mediatools {user_id} menu REMOVE_SUBTITLE_LANGUAGE"
        )
        buttons.data_button(
            "Encoding", f"mediatools {user_id} menu REMOVE_SUBTITLE_ENCODING"
        )
        buttons.data_button(
            "Font", f"mediatools {user_id} menu REMOVE_SUBTITLE_FONT"
        )
        buttons.data_button(
            "Font Size", f"mediatools {user_id} menu REMOVE_SUBTITLE_FONT_SIZE"
        )

        buttons.data_button("Back", f"mediatools {user_id} remove_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get subtitle remove settings
        subtitle_codec = user_dict.get("REMOVE_SUBTITLE_CODEC", "none")
        if subtitle_codec == "none" and hasattr(Config, "REMOVE_SUBTITLE_CODEC"):
            subtitle_codec = Config.REMOVE_SUBTITLE_CODEC
        subtitle_codec_str = (
            f"{subtitle_codec}" if subtitle_codec != "none" else "none (Default)"
        )

        subtitle_format = user_dict.get("REMOVE_SUBTITLE_FORMAT", "none")
        if subtitle_format == "none" and hasattr(Config, "REMOVE_SUBTITLE_FORMAT"):
            subtitle_format = Config.REMOVE_SUBTITLE_FORMAT
        subtitle_format_str = (
            f"{subtitle_format}" if subtitle_format != "none" else "none (Default)"
        )

        subtitle_index = user_dict.get("REMOVE_SUBTITLE_INDEX", None)
        if subtitle_index is None and hasattr(Config, "REMOVE_SUBTITLE_INDEX"):
            subtitle_index = Config.REMOVE_SUBTITLE_INDEX
        subtitle_index_str = (
            f"{subtitle_index}" if subtitle_index is not None else "All (Default)"
        )

        subtitle_language = user_dict.get("REMOVE_SUBTITLE_LANGUAGE", "none")
        if subtitle_language == "none" and hasattr(
            Config, "REMOVE_SUBTITLE_LANGUAGE"
        ):
            subtitle_language = Config.REMOVE_SUBTITLE_LANGUAGE
        subtitle_language_str = (
            f"{subtitle_language}"
            if subtitle_language != "none"
            else "none (Default)"
        )

        subtitle_encoding = user_dict.get("REMOVE_SUBTITLE_ENCODING", "none")
        if subtitle_encoding == "none" and hasattr(
            Config, "REMOVE_SUBTITLE_ENCODING"
        ):
            subtitle_encoding = Config.REMOVE_SUBTITLE_ENCODING
        subtitle_encoding_str = (
            f"{subtitle_encoding}"
            if subtitle_encoding != "none"
            else "none (Default)"
        )

        subtitle_font = user_dict.get("REMOVE_SUBTITLE_FONT", "none")
        if subtitle_font == "none" and hasattr(Config, "REMOVE_SUBTITLE_FONT"):
            subtitle_font = Config.REMOVE_SUBTITLE_FONT
        subtitle_font_str = (
            f"{subtitle_font}" if subtitle_font != "none" else "none (Default)"
        )

        subtitle_font_size = user_dict.get("REMOVE_SUBTITLE_FONT_SIZE", "none")
        if subtitle_font_size == "none" and hasattr(
            Config, "REMOVE_SUBTITLE_FONT_SIZE"
        ):
            subtitle_font_size = Config.REMOVE_SUBTITLE_FONT_SIZE
        subtitle_font_size_str = (
            f"{subtitle_font_size}"
            if subtitle_font_size != "none"
            else "none (Default)"
        )

        text = f"""⌬ <b>Subtitle Remove Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Codec</b> → <code>{subtitle_codec_str}</code>
┠ <b>Format</b> → <code>{subtitle_format_str}</code>
┠ <b>Index</b> → <code>{subtitle_index_str}</code>
┠ <b>Language</b> → <code>{subtitle_language_str}</code>
┠ <b>Encoding</b> → <code>{subtitle_encoding_str}</code>
┠ <b>Font</b> → <code>{subtitle_font_str}</code>
┖ <b>Font Size</b> → <code>{subtitle_font_size_str}</code>

<b>Usage:</b>
• Configure subtitle processing settings for removal
• Use 'none' to disable specific settings
• Index specifies which subtitle tracks to remove
• Other settings control output format and appearance"""

    elif stype == "remove_attachment_config":
        # Attachment remove configuration menu
        buttons.data_button(
            "Format", f"mediatools {user_id} menu REMOVE_ATTACHMENT_FORMAT"
        )
        buttons.data_button(
            "Index", f"mediatools {user_id} menu REMOVE_ATTACHMENT_INDEX"
        )
        buttons.data_button(
            "Filter", f"mediatools {user_id} menu REMOVE_ATTACHMENT_FILTER"
        )

        buttons.data_button("Back", f"mediatools {user_id} remove_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get attachment remove settings
        attachment_format = user_dict.get("REMOVE_ATTACHMENT_FORMAT", "none")
        if attachment_format == "none" and hasattr(
            Config, "REMOVE_ATTACHMENT_FORMAT"
        ):
            attachment_format = Config.REMOVE_ATTACHMENT_FORMAT
        attachment_format_str = (
            f"{attachment_format}"
            if attachment_format != "none"
            else "none (Default)"
        )

        attachment_index = user_dict.get("REMOVE_ATTACHMENT_INDEX", None)
        if attachment_index is None and hasattr(Config, "REMOVE_ATTACHMENT_INDEX"):
            attachment_index = Config.REMOVE_ATTACHMENT_INDEX
        attachment_index_str = (
            f"{attachment_index}"
            if attachment_index is not None
            else "All (Default)"
        )

        attachment_filter = user_dict.get("REMOVE_ATTACHMENT_FILTER", "none")
        if attachment_filter == "none" and hasattr(
            Config, "REMOVE_ATTACHMENT_FILTER"
        ):
            attachment_filter = Config.REMOVE_ATTACHMENT_FILTER
        attachment_filter_str = (
            f"{attachment_filter}"
            if attachment_filter != "none"
            else "none (Default)"
        )

        text = f"""⌬ <b>Attachment Remove Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Format</b> → <code>{attachment_format_str}</code>
┠ <b>Index</b> → <code>{attachment_index_str}</code>
┖ <b>Filter</b> → <code>{attachment_filter_str}</code>

<b>Usage:</b>
• Configure attachment processing settings for removal
• Use 'none' to disable specific settings
• Index specifies which attachments to remove
• Filter allows pattern-based attachment selection"""

    elif stype == "add_config":
        # Add configuration menu
        # Video add settings
        video_enabled = user_dict.get("ADD_VIDEO_ENABLED", False)
        buttons.data_button(
            f"Video: {'✅ ON' if video_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_VIDEO_ENABLED {'f' if video_enabled else 't'}",
        )
        buttons.data_button(
            "Video Settings", f"mediatools {user_id} add_video_config"
        )

        # Audio add settings
        audio_enabled = user_dict.get("ADD_AUDIO_ENABLED", False)
        buttons.data_button(
            f"Audio: {'✅ ON' if audio_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_AUDIO_ENABLED {'f' if audio_enabled else 't'}",
        )
        buttons.data_button(
            "Audio Settings", f"mediatools {user_id} add_audio_config"
        )

        # Subtitle add settings
        subtitle_enabled = user_dict.get("ADD_SUBTITLE_ENABLED", False)
        buttons.data_button(
            f"Subtitle: {'✅ ON' if subtitle_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_SUBTITLE_ENABLED {'f' if subtitle_enabled else 't'}",
        )
        buttons.data_button(
            "Subtitle Settings", f"mediatools {user_id} add_subtitle_config"
        )

        # Attachment add settings
        attachment_enabled = user_dict.get("ADD_ATTACHMENT_ENABLED", False)
        buttons.data_button(
            f"Attachment: {'✅ ON' if attachment_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_ATTACHMENT_ENABLED {'f' if attachment_enabled else 't'}",
        )
        buttons.data_button(
            "Attachment Settings", f"mediatools {user_id} add_attachment_config"
        )

        # Delete original toggle
        delete_original = user_dict.get("ADD_DELETE_ORIGINAL", True)
        buttons.data_button(
            f"RO: {'✅ ON' if delete_original else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_DELETE_ORIGINAL {'f' if delete_original else 't'}",
        )

        # Preserve tracks toggle
        preserve_tracks = user_dict.get("ADD_PRESERVE_TRACKS", False)
        buttons.data_button(
            f"Preserve: {'✅ ON' if preserve_tracks else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_PRESERVE_TRACKS {'f' if preserve_tracks else 't'}",
        )

        # Replace tracks toggle
        replace_tracks = user_dict.get("ADD_REPLACE_TRACKS", False)
        buttons.data_button(
            f"Replace: {'✅ ON' if replace_tracks else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_REPLACE_TRACKS {'f' if replace_tracks else 't'}",
        )

        buttons.data_button("Back", f"mediatools {user_id} add", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get video add settings
        video_codec = user_dict.get("ADD_VIDEO_CODEC", "none")
        if video_codec == "none" and hasattr(Config, "ADD_VIDEO_CODEC"):
            video_codec = Config.ADD_VIDEO_CODEC
        video_codec_str = (
            f"{video_codec}" if video_codec != "none" else "none (Default)"
        )

        video_index = user_dict.get("ADD_VIDEO_INDEX", None)
        if video_index is None and hasattr(Config, "ADD_VIDEO_INDEX"):
            video_index = Config.ADD_VIDEO_INDEX
        video_index_str = (
            f"{video_index}" if video_index is not None else "All (Default)"
        )

        video_quality = user_dict.get("ADD_VIDEO_QUALITY", "none")
        if video_quality == "none" and hasattr(Config, "ADD_VIDEO_QUALITY"):
            video_quality = Config.ADD_VIDEO_QUALITY
        video_quality_str = (
            f"{video_quality}" if video_quality != "none" else "none (Default)"
        )

        video_preset = user_dict.get("ADD_VIDEO_PRESET", "none")
        if video_preset == "none" and hasattr(Config, "ADD_VIDEO_PRESET"):
            video_preset = Config.ADD_VIDEO_PRESET
        video_preset_str = (
            f"{video_preset}" if video_preset != "none" else "none (Default)"
        )

        video_bitrate = user_dict.get("ADD_VIDEO_BITRATE", "none")
        if video_bitrate == "none" and hasattr(Config, "ADD_VIDEO_BITRATE"):
            video_bitrate = Config.ADD_VIDEO_BITRATE
        video_bitrate_str = (
            f"{video_bitrate}" if video_bitrate != "none" else "none (Default)"
        )

        video_resolution = user_dict.get("ADD_VIDEO_RESOLUTION", "none")
        if video_resolution == "none" and hasattr(Config, "ADD_VIDEO_RESOLUTION"):
            video_resolution = Config.ADD_VIDEO_RESOLUTION
        video_resolution_str = (
            f"{video_resolution}" if video_resolution != "none" else "none (Default)"
        )

        video_fps = user_dict.get("ADD_VIDEO_FPS", "none")
        if video_fps == "none" and hasattr(Config, "ADD_VIDEO_FPS"):
            video_fps = Config.ADD_VIDEO_FPS
        video_fps_str = f"{video_fps}" if video_fps != "none" else "none (Default)"

        # Get audio add settings
        audio_codec = user_dict.get("ADD_AUDIO_CODEC", "none")
        if audio_codec == "none" and hasattr(Config, "ADD_AUDIO_CODEC"):
            audio_codec = Config.ADD_AUDIO_CODEC
        audio_codec_str = (
            f"{audio_codec}" if audio_codec != "none" else "none (Default)"
        )

        audio_index = user_dict.get("ADD_AUDIO_INDEX", None)
        if audio_index is None and hasattr(Config, "ADD_AUDIO_INDEX"):
            audio_index = Config.ADD_AUDIO_INDEX
        audio_index_str = (
            f"{audio_index}" if audio_index is not None else "All (Default)"
        )

        audio_bitrate = user_dict.get("ADD_AUDIO_BITRATE", "none")
        if audio_bitrate == "none" and hasattr(Config, "ADD_AUDIO_BITRATE"):
            audio_bitrate = Config.ADD_AUDIO_BITRATE
        audio_bitrate_str = (
            f"{audio_bitrate}" if audio_bitrate != "none" else "none (Default)"
        )

        audio_channels = user_dict.get("ADD_AUDIO_CHANNELS", "none")
        if audio_channels == "none" and hasattr(Config, "ADD_AUDIO_CHANNELS"):
            audio_channels = Config.ADD_AUDIO_CHANNELS
        audio_channels_str = (
            f"{audio_channels}" if audio_channels != "none" else "none (Default)"
        )

        audio_sampling = user_dict.get("ADD_AUDIO_SAMPLING", "none")
        if audio_sampling == "none" and hasattr(Config, "ADD_AUDIO_SAMPLING"):
            audio_sampling = Config.ADD_AUDIO_SAMPLING
        audio_sampling_str = (
            f"{audio_sampling}" if audio_sampling != "none" else "none (Default)"
        )

        audio_volume = user_dict.get("ADD_AUDIO_VOLUME", "none")
        if audio_volume == "none" and hasattr(Config, "ADD_AUDIO_VOLUME"):
            audio_volume = Config.ADD_AUDIO_VOLUME
        audio_volume_str = (
            f"{audio_volume}" if audio_volume != "none" else "none (Default)"
        )

        # Get subtitle add settings
        subtitle_codec = user_dict.get("ADD_SUBTITLE_CODEC", "none")
        if subtitle_codec == "none" and hasattr(Config, "ADD_SUBTITLE_CODEC"):
            subtitle_codec = Config.ADD_SUBTITLE_CODEC
        subtitle_codec_str = (
            f"{subtitle_codec}" if subtitle_codec != "none" else "none (Default)"
        )

        subtitle_index = user_dict.get("ADD_SUBTITLE_INDEX", None)
        if subtitle_index is None and hasattr(Config, "ADD_SUBTITLE_INDEX"):
            subtitle_index = Config.ADD_SUBTITLE_INDEX
        subtitle_index_str = (
            f"{subtitle_index}" if subtitle_index is not None else "All (Default)"
        )

        subtitle_language = user_dict.get("ADD_SUBTITLE_LANGUAGE", "none")
        if subtitle_language == "none" and hasattr(Config, "ADD_SUBTITLE_LANGUAGE"):
            subtitle_language = Config.ADD_SUBTITLE_LANGUAGE
        subtitle_language_str = (
            f"{subtitle_language}"
            if subtitle_language != "none"
            else "none (Default)"
        )

        subtitle_encoding = user_dict.get("ADD_SUBTITLE_ENCODING", "none")
        if subtitle_encoding == "none" and hasattr(Config, "ADD_SUBTITLE_ENCODING"):
            subtitle_encoding = Config.ADD_SUBTITLE_ENCODING
        subtitle_encoding_str = (
            f"{subtitle_encoding}"
            if subtitle_encoding != "none"
            else "none (Default)"
        )

        subtitle_font = user_dict.get("ADD_SUBTITLE_FONT", "none")
        if subtitle_font == "none" and hasattr(Config, "ADD_SUBTITLE_FONT"):
            subtitle_font = Config.ADD_SUBTITLE_FONT
        subtitle_font_str = (
            f"{subtitle_font}" if subtitle_font != "none" else "none (Default)"
        )

        subtitle_font_size = user_dict.get("ADD_SUBTITLE_FONT_SIZE", "none")
        if subtitle_font_size == "none" and hasattr(
            Config, "ADD_SUBTITLE_FONT_SIZE"
        ):
            subtitle_font_size = Config.ADD_SUBTITLE_FONT_SIZE
        subtitle_font_size_str = (
            f"{subtitle_font_size}"
            if subtitle_font_size != "none"
            else "none (Default)"
        )

        # Get attachment add settings

        attachment_index = user_dict.get("ADD_ATTACHMENT_INDEX", None)
        if attachment_index is None and hasattr(Config, "ADD_ATTACHMENT_INDEX"):
            attachment_index = Config.ADD_ATTACHMENT_INDEX
        attachment_index_str = (
            f"{attachment_index}"
            if attachment_index is not None
            else "All (Default)"
        )

        attachment_mimetype = user_dict.get("ADD_ATTACHMENT_MIMETYPE", "none")
        if attachment_mimetype == "none" and hasattr(
            Config, "ADD_ATTACHMENT_MIMETYPE"
        ):
            attachment_mimetype = Config.ADD_ATTACHMENT_MIMETYPE
        attachment_mimetype_str = (
            f"{attachment_mimetype}"
            if attachment_mimetype != "none"
            else "none (Default)"
        )

        # Get add enabled status for each type
        # Video add status
        video_add_enabled = user_dict.get("ADD_VIDEO_ENABLED", False)
        owner_video_add_enabled = (
            hasattr(Config, "ADD_VIDEO_ENABLED") and Config.ADD_VIDEO_ENABLED
        )

        if "ADD_VIDEO_ENABLED" in user_dict:
            if video_add_enabled:
                video_status = "✅ Enabled (User)"
            else:
                video_status = "❌ Disabled (User)"
        elif owner_video_add_enabled:
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Audio add status
        audio_add_enabled = user_dict.get("ADD_AUDIO_ENABLED", False)
        owner_audio_add_enabled = (
            hasattr(Config, "ADD_AUDIO_ENABLED") and Config.ADD_AUDIO_ENABLED
        )

        if "ADD_AUDIO_ENABLED" in user_dict:
            if audio_add_enabled:
                audio_status = "✅ Enabled (User)"
            else:
                audio_status = "❌ Disabled (User)"
        elif owner_audio_add_enabled:
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Subtitle add status
        subtitle_add_enabled = user_dict.get("ADD_SUBTITLE_ENABLED", False)
        owner_subtitle_add_enabled = (
            hasattr(Config, "ADD_SUBTITLE_ENABLED") and Config.ADD_SUBTITLE_ENABLED
        )

        if "ADD_SUBTITLE_ENABLED" in user_dict:
            if subtitle_add_enabled:
                subtitle_status = "✅ Enabled (User)"
            else:
                subtitle_status = "❌ Disabled (User)"
        elif owner_subtitle_add_enabled:
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Attachment add status
        attachment_add_enabled = user_dict.get("ADD_ATTACHMENT_ENABLED", False)
        owner_attachment_add_enabled = (
            hasattr(Config, "ADD_ATTACHMENT_ENABLED")
            and Config.ADD_ATTACHMENT_ENABLED
        )

        if "ADD_ATTACHMENT_ENABLED" in user_dict:
            if attachment_add_enabled:
                attachment_status = "✅ Enabled (User)"
            else:
                attachment_status = "❌ Disabled (User)"
        elif owner_attachment_add_enabled:
            attachment_status = "✅ Enabled (Global)"
        else:
            attachment_status = "❌ Disabled"

        # Get delete original status
        delete_original_enabled = user_dict.get("ADD_DELETE_ORIGINAL", True)
        owner_delete_original_enabled = (
            hasattr(Config, "ADD_DELETE_ORIGINAL") and Config.ADD_DELETE_ORIGINAL
        )

        if "ADD_DELETE_ORIGINAL" in user_dict:
            if delete_original_enabled:
                delete_original_status = "✅ Enabled (User)"
            else:
                delete_original_status = "❌ Disabled (User)"
        elif owner_delete_original_enabled:
            delete_original_status = "✅ Enabled (Global)"
        else:
            delete_original_status = "✅ Enabled (Default)"

        # Get preserve tracks status
        preserve_tracks_enabled = user_dict.get("ADD_PRESERVE_TRACKS", False)
        owner_preserve_tracks_enabled = (
            hasattr(Config, "ADD_PRESERVE_TRACKS") and Config.ADD_PRESERVE_TRACKS
        )

        if "ADD_PRESERVE_TRACKS" in user_dict:
            if preserve_tracks_enabled:
                preserve_tracks_status = "✅ Enabled (User)"
            else:
                preserve_tracks_status = "❌ Disabled (User)"
        elif owner_preserve_tracks_enabled:
            preserve_tracks_status = "✅ Enabled (Global)"
        else:
            preserve_tracks_status = "❌ Disabled (Default)"

        # Get replace tracks status
        replace_tracks_enabled = user_dict.get("ADD_REPLACE_TRACKS", False)
        owner_replace_tracks_enabled = (
            hasattr(Config, "ADD_REPLACE_TRACKS") and Config.ADD_REPLACE_TRACKS
        )

        if "ADD_REPLACE_TRACKS" in user_dict:
            if replace_tracks_enabled:
                replace_tracks_status = "✅ Enabled (User)"
            else:
                replace_tracks_status = "❌ Disabled (User)"
        elif owner_replace_tracks_enabled:
            replace_tracks_status = "✅ Enabled (Global)"
        else:
            replace_tracks_status = "❌ Disabled (Default)"

        text = f"""⌬ <b>Add Configuration :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Video Add</b> → {video_status}
┠ <b>Video Codec</b> → <code>{video_codec_str}</code>
┠ <b>Video Index</b> → <code>{video_index_str}</code>
┠ <b>Video Quality</b> → <code>{video_quality_str}</code>
┠ <b>Video Preset</b> → <code>{video_preset_str}</code>
┠ <b>Video Bitrate</b> → <code>{video_bitrate_str}</code>
┠ <b>Video Resolution</b> → <code>{video_resolution_str}</code>
┠ <b>Video FPS</b> → <code>{video_fps_str}</code>
┃
┠ <b>Audio Add</b> → {audio_status}
┠ <b>Audio Codec</b> → <code>{audio_codec_str}</code>
┠ <b>Audio Index</b> → <code>{audio_index_str}</code>
┠ <b>Audio Bitrate</b> → <code>{audio_bitrate_str}</code>
┠ <b>Audio Channels</b> → <code>{audio_channels_str}</code>
┠ <b>Audio Sampling</b> → <code>{audio_sampling_str}</code>
┠ <b>Audio Volume</b> → <code>{audio_volume_str}</code>
┃
┠ <b>Subtitle Add</b> → {subtitle_status}
┠ <b>Subtitle Codec</b> → <code>{subtitle_codec_str}</code>
┠ <b>Subtitle Index</b> → <code>{subtitle_index_str}</code>
┠ <b>Subtitle Language</b> → <code>{subtitle_language_str}</code>
┠ <b>Subtitle Encoding</b> → <code>{subtitle_encoding_str}</code>
┠ <b>Subtitle Font</b> → <code>{subtitle_font_str}</code>
┠ <b>Subtitle Font Size</b> → <code>{subtitle_font_size_str}</code>
┃
┠ <b>Attachment Add</b> → {attachment_status}
┠ <b>Attachment Index</b> → <code>{attachment_index_str}</code>
┠ <b>Attachment Mimetype</b> → <code>{attachment_mimetype_str}</code>
┃
┠ <b>RO (Remove Original)</b> → {delete_original_status}
┠ <b>Preserve Tracks</b> → {preserve_tracks_status}
┖ <b>Replace Tracks</b> → {replace_tracks_status}

<b>Usage:</b>
• Enable add to combine tracks from different files
• RO (Remove Original) deletes original files after adding tracks
• Use <code>-preserve</code> flag to preserve existing tracks when adding new ones
• Use <code>-replace</code> flag to replace existing tracks with new ones at the same index
• Use <code>-m</code> flag to enable multi-input mode
• Example: <code>/leech https://example.com/video.mp4 -add -m folder_name</code>
• Example: <code>/leech https://example.com/video.mp4 -add -del</code>
• In multi-input mode, the first file is the target and subsequent files are sources for tracks"""

    elif stype == "compression_config":
        # Compression configuration menu
        # Add global delete original toggle
        # Check for user setting first, then global setting, then default to True
        delete_original = user_dict.get("COMPRESSION_DELETE_ORIGINAL", None)
        if delete_original is None and hasattr(
            Config, "COMPRESSION_DELETE_ORIGINAL"
        ):
            delete_original = Config.COMPRESSION_DELETE_ORIGINAL
        elif delete_original is None:
            delete_original = True  # Default to True if not specified

        buttons.data_button(
            f"RO: {'✅ ON' if delete_original else '❌ OFF'}",
            f"mediatools {user_id} tog COMPRESSION_DELETE_ORIGINAL {'f' if delete_original else 't'}",
        )

        # Video compression settings
        video_enabled = user_dict.get("COMPRESSION_VIDEO_ENABLED", False)
        buttons.data_button(
            f"Video: {'✅ ON' if video_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog COMPRESSION_VIDEO_ENABLED {'f' if video_enabled else 't'}",
        )
        buttons.data_button(
            "Video Preset", f"mediatools {user_id} menu COMPRESSION_VIDEO_PRESET"
        )
        buttons.data_button(
            "Video CRF", f"mediatools {user_id} menu COMPRESSION_VIDEO_CRF"
        )
        buttons.data_button(
            "Video Codec", f"mediatools {user_id} menu COMPRESSION_VIDEO_CODEC"
        )
        buttons.data_button(
            "Video Tune", f"mediatools {user_id} menu COMPRESSION_VIDEO_TUNE"
        )
        buttons.data_button(
            "Video Pixel Format",
            f"mediatools {user_id} menu COMPRESSION_VIDEO_PIXEL_FORMAT",
        )
        buttons.data_button(
            "Video Bitdepth", f"mediatools {user_id} menu COMPRESSION_VIDEO_BITDEPTH"
        )
        buttons.data_button(
            "Video Bitrate", f"mediatools {user_id} menu COMPRESSION_VIDEO_BITRATE"
        )
        buttons.data_button(
            "Video Resolution",
            f"mediatools {user_id} menu COMPRESSION_VIDEO_RESOLUTION",
        )
        buttons.data_button(
            "Video Format", f"mediatools {user_id} menu COMPRESSION_VIDEO_FORMAT"
        )

        # Audio compression settings
        audio_enabled = user_dict.get("COMPRESSION_AUDIO_ENABLED", False)
        buttons.data_button(
            f"Audio: {'✅ ON' if audio_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog COMPRESSION_AUDIO_ENABLED {'f' if audio_enabled else 't'}",
        )
        buttons.data_button(
            "Audio Preset", f"mediatools {user_id} menu COMPRESSION_AUDIO_PRESET"
        )
        buttons.data_button(
            "Audio Codec", f"mediatools {user_id} menu COMPRESSION_AUDIO_CODEC"
        )
        buttons.data_button(
            "Audio Bitrate", f"mediatools {user_id} menu COMPRESSION_AUDIO_BITRATE"
        )
        buttons.data_button(
            "Audio Channels", f"mediatools {user_id} menu COMPRESSION_AUDIO_CHANNELS"
        )
        buttons.data_button(
            "Audio Bitdepth", f"mediatools {user_id} menu COMPRESSION_AUDIO_BITDEPTH"
        )
        buttons.data_button(
            "Audio Format", f"mediatools {user_id} menu COMPRESSION_AUDIO_FORMAT"
        )

        # Image compression settings
        image_enabled = user_dict.get("COMPRESSION_IMAGE_ENABLED", False)
        buttons.data_button(
            f"Image: {'✅ ON' if image_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog COMPRESSION_IMAGE_ENABLED {'f' if image_enabled else 't'}",
        )
        buttons.data_button(
            "Image Preset", f"mediatools {user_id} menu COMPRESSION_IMAGE_PRESET"
        )
        buttons.data_button(
            "Image Quality", f"mediatools {user_id} menu COMPRESSION_IMAGE_QUALITY"
        )
        buttons.data_button(
            "Image Resize", f"mediatools {user_id} menu COMPRESSION_IMAGE_RESIZE"
        )
        buttons.data_button(
            "Image Format", f"mediatools {user_id} menu COMPRESSION_IMAGE_FORMAT"
        )

        # Document compression settings
        document_enabled = user_dict.get("COMPRESSION_DOCUMENT_ENABLED", False)
        buttons.data_button(
            f"Document: {'✅ ON' if document_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog COMPRESSION_DOCUMENT_ENABLED {'f' if document_enabled else 't'}",
        )
        buttons.data_button(
            "Document Preset",
            f"mediatools {user_id} menu COMPRESSION_DOCUMENT_PRESET",
        )
        buttons.data_button(
            "Document DPI", f"mediatools {user_id} menu COMPRESSION_DOCUMENT_DPI"
        )
        buttons.data_button(
            "Document Format",
            f"mediatools {user_id} menu COMPRESSION_DOCUMENT_FORMAT",
        )

        # Subtitle compression settings
        subtitle_enabled = user_dict.get("COMPRESSION_SUBTITLE_ENABLED", False)
        buttons.data_button(
            f"Subtitle: {'✅ ON' if subtitle_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog COMPRESSION_SUBTITLE_ENABLED {'f' if subtitle_enabled else 't'}",
        )
        buttons.data_button(
            "Subtitle Preset",
            f"mediatools {user_id} menu COMPRESSION_SUBTITLE_PRESET",
        )
        buttons.data_button(
            "Subtitle Encoding",
            f"mediatools {user_id} menu COMPRESSION_SUBTITLE_ENCODING",
        )
        buttons.data_button(
            "Subtitle Format",
            f"mediatools {user_id} menu COMPRESSION_SUBTITLE_FORMAT",
        )

        # Archive compression settings
        archive_enabled = user_dict.get("COMPRESSION_ARCHIVE_ENABLED", False)
        buttons.data_button(
            f"Archive: {'✅ ON' if archive_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog COMPRESSION_ARCHIVE_ENABLED {'f' if archive_enabled else 't'}",
        )
        buttons.data_button(
            "Archive Preset", f"mediatools {user_id} menu COMPRESSION_ARCHIVE_PRESET"
        )
        buttons.data_button(
            "Archive Level", f"mediatools {user_id} menu COMPRESSION_ARCHIVE_LEVEL"
        )
        buttons.data_button(
            "Archive Method", f"mediatools {user_id} menu COMPRESSION_ARCHIVE_METHOD"
        )
        buttons.data_button(
            "Archive Format", f"mediatools {user_id} menu COMPRESSION_ARCHIVE_FORMAT"
        )
        buttons.data_button(
            "Archive Password",
            f"mediatools {user_id} menu COMPRESSION_ARCHIVE_PASSWORD",
        )
        buttons.data_button(
            "Archive Algorithm",
            f"mediatools {user_id} menu COMPRESSION_ARCHIVE_ALGORITHM",
        )

        buttons.data_button("Back", f"mediatools {user_id} compression", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get delete original setting
        # Check for user setting first, then global setting, then default to True
        delete_original = user_dict.get("COMPRESSION_DELETE_ORIGINAL", None)
        if delete_original is None and hasattr(
            Config, "COMPRESSION_DELETE_ORIGINAL"
        ):
            delete_original = Config.COMPRESSION_DELETE_ORIGINAL
        elif delete_original is None:
            delete_original = True  # Default to True if not specified

        # Determine display string with appropriate label
        if "COMPRESSION_DELETE_ORIGINAL" in user_dict:
            delete_original_status = (
                "✅ Enabled (User)" if delete_original else "❌ Disabled (User)"
            )
        elif hasattr(Config, "COMPRESSION_DELETE_ORIGINAL"):
            delete_original_status = (
                "✅ Enabled (Global)"
                if Config.COMPRESSION_DELETE_ORIGINAL
                else "❌ Disabled (Global)"
            )
        else:
            delete_original_status = "✅ Enabled (Default)"

        # Get video compression settings
        video_preset = user_dict.get("COMPRESSION_VIDEO_PRESET", None)
        if video_preset is None and hasattr(Config, "COMPRESSION_VIDEO_PRESET"):
            video_preset = Config.COMPRESSION_VIDEO_PRESET
        video_preset_str = f"{video_preset}" if video_preset else "medium (Default)"

        video_crf = user_dict.get("COMPRESSION_VIDEO_CRF", None)
        if video_crf is None and hasattr(Config, "COMPRESSION_VIDEO_CRF"):
            video_crf = Config.COMPRESSION_VIDEO_CRF
        video_crf_str = f"{video_crf}" if video_crf else "23 (Default)"

        video_codec = user_dict.get("COMPRESSION_VIDEO_CODEC", None)
        if video_codec is None and hasattr(Config, "COMPRESSION_VIDEO_CODEC"):
            video_codec = Config.COMPRESSION_VIDEO_CODEC
        video_codec_str = f"{video_codec}" if video_codec else "libx264 (Default)"

        video_tune = user_dict.get("COMPRESSION_VIDEO_TUNE", None)
        if video_tune is None and hasattr(Config, "COMPRESSION_VIDEO_TUNE"):
            video_tune = Config.COMPRESSION_VIDEO_TUNE
        video_tune_str = f"{video_tune}" if video_tune else "film (Default)"

        video_pixel_format = user_dict.get("COMPRESSION_VIDEO_PIXEL_FORMAT", None)
        if video_pixel_format is None and hasattr(
            Config, "COMPRESSION_VIDEO_PIXEL_FORMAT"
        ):
            video_pixel_format = Config.COMPRESSION_VIDEO_PIXEL_FORMAT
        video_pixel_format_str = (
            f"{video_pixel_format}" if video_pixel_format else "yuv420p (Default)"
        )

        video_format = user_dict.get("COMPRESSION_VIDEO_FORMAT", None)
        if video_format is None and hasattr(Config, "COMPRESSION_VIDEO_FORMAT"):
            video_format = Config.COMPRESSION_VIDEO_FORMAT
        video_format_str = f"{video_format}" if video_format else "none (Default)"

        # Get audio compression settings
        audio_preset = user_dict.get("COMPRESSION_AUDIO_PRESET", None)
        if audio_preset is None and hasattr(Config, "COMPRESSION_AUDIO_PRESET"):
            audio_preset = Config.COMPRESSION_AUDIO_PRESET
        audio_preset_str = f"{audio_preset}" if audio_preset else "medium (Default)"

        audio_codec = user_dict.get("COMPRESSION_AUDIO_CODEC", None)
        if audio_codec is None and hasattr(Config, "COMPRESSION_AUDIO_CODEC"):
            audio_codec = Config.COMPRESSION_AUDIO_CODEC
        audio_codec_str = f"{audio_codec}" if audio_codec else "aac (Default)"

        audio_bitrate = user_dict.get("COMPRESSION_AUDIO_BITRATE", None)
        if audio_bitrate is None and hasattr(Config, "COMPRESSION_AUDIO_BITRATE"):
            audio_bitrate = Config.COMPRESSION_AUDIO_BITRATE
        audio_bitrate_str = f"{audio_bitrate}" if audio_bitrate else "128k (Default)"

        audio_channels = user_dict.get("COMPRESSION_AUDIO_CHANNELS", None)
        if audio_channels is None and hasattr(Config, "COMPRESSION_AUDIO_CHANNELS"):
            audio_channels = Config.COMPRESSION_AUDIO_CHANNELS
        audio_channels_str = f"{audio_channels}" if audio_channels else "2 (Default)"

        audio_format = user_dict.get("COMPRESSION_AUDIO_FORMAT", None)
        if audio_format is None and hasattr(Config, "COMPRESSION_AUDIO_FORMAT"):
            audio_format = Config.COMPRESSION_AUDIO_FORMAT
        audio_format_str = f"{audio_format}" if audio_format else "none (Default)"

        # Get image compression settings
        image_preset = user_dict.get("COMPRESSION_IMAGE_PRESET", None)
        if image_preset is None and hasattr(Config, "COMPRESSION_IMAGE_PRESET"):
            image_preset = Config.COMPRESSION_IMAGE_PRESET
        image_preset_str = f"{image_preset}" if image_preset else "medium (Default)"

        image_quality = user_dict.get("COMPRESSION_IMAGE_QUALITY", None)
        if image_quality is None and hasattr(Config, "COMPRESSION_IMAGE_QUALITY"):
            image_quality = Config.COMPRESSION_IMAGE_QUALITY
        image_quality_str = f"{image_quality}" if image_quality else "80 (Default)"

        image_resize = user_dict.get("COMPRESSION_IMAGE_RESIZE", None)
        if image_resize is None and hasattr(Config, "COMPRESSION_IMAGE_RESIZE"):
            image_resize = Config.COMPRESSION_IMAGE_RESIZE
        image_resize_str = f"{image_resize}" if image_resize else "none (Default)"

        image_format = user_dict.get("COMPRESSION_IMAGE_FORMAT", None)
        if image_format is None and hasattr(Config, "COMPRESSION_IMAGE_FORMAT"):
            image_format = Config.COMPRESSION_IMAGE_FORMAT
        image_format_str = f"{image_format}" if image_format else "none (Default)"

        # Get document compression settings
        document_preset = user_dict.get("COMPRESSION_DOCUMENT_PRESET", None)
        if document_preset is None and hasattr(
            Config, "COMPRESSION_DOCUMENT_PRESET"
        ):
            document_preset = Config.COMPRESSION_DOCUMENT_PRESET
        document_preset_str = (
            f"{document_preset}" if document_preset else "medium (Default)"
        )

        document_dpi = user_dict.get("COMPRESSION_DOCUMENT_DPI", None)
        if document_dpi is None and hasattr(Config, "COMPRESSION_DOCUMENT_DPI"):
            document_dpi = Config.COMPRESSION_DOCUMENT_DPI
        document_dpi_str = f"{document_dpi}" if document_dpi else "150 (Default)"

        document_format = user_dict.get("COMPRESSION_DOCUMENT_FORMAT", None)
        if document_format is None and hasattr(
            Config, "COMPRESSION_DOCUMENT_FORMAT"
        ):
            document_format = Config.COMPRESSION_DOCUMENT_FORMAT
        document_format_str = (
            f"{document_format}" if document_format else "none (Default)"
        )

        # Get subtitle compression settings
        subtitle_preset = user_dict.get("COMPRESSION_SUBTITLE_PRESET", None)
        if subtitle_preset is None and hasattr(
            Config, "COMPRESSION_SUBTITLE_PRESET"
        ):
            subtitle_preset = Config.COMPRESSION_SUBTITLE_PRESET
        subtitle_preset_str = (
            f"{subtitle_preset}" if subtitle_preset else "medium (Default)"
        )

        subtitle_encoding = user_dict.get("COMPRESSION_SUBTITLE_ENCODING", None)
        if subtitle_encoding is None and hasattr(
            Config, "COMPRESSION_SUBTITLE_ENCODING"
        ):
            subtitle_encoding = Config.COMPRESSION_SUBTITLE_ENCODING
        subtitle_encoding_str = (
            f"{subtitle_encoding}" if subtitle_encoding else "utf-8 (Default)"
        )

        subtitle_format = user_dict.get("COMPRESSION_SUBTITLE_FORMAT", None)
        if subtitle_format is None and hasattr(
            Config, "COMPRESSION_SUBTITLE_FORMAT"
        ):
            subtitle_format = Config.COMPRESSION_SUBTITLE_FORMAT
        subtitle_format_str = (
            f"{subtitle_format}" if subtitle_format else "none (Default)"
        )

        # Get archive compression settings
        archive_preset = user_dict.get("COMPRESSION_ARCHIVE_PRESET", None)
        if archive_preset is None and hasattr(Config, "COMPRESSION_ARCHIVE_PRESET"):
            archive_preset = Config.COMPRESSION_ARCHIVE_PRESET
        archive_preset_str = (
            f"{archive_preset}" if archive_preset else "medium (Default)"
        )

        archive_level = user_dict.get("COMPRESSION_ARCHIVE_LEVEL", None)
        if archive_level is None and hasattr(Config, "COMPRESSION_ARCHIVE_LEVEL"):
            archive_level = Config.COMPRESSION_ARCHIVE_LEVEL
        archive_level_str = f"{archive_level}" if archive_level else "5 (Default)"

        archive_method = user_dict.get("COMPRESSION_ARCHIVE_METHOD", None)
        if archive_method is None and hasattr(Config, "COMPRESSION_ARCHIVE_METHOD"):
            archive_method = Config.COMPRESSION_ARCHIVE_METHOD
        archive_method_str = (
            f"{archive_method}" if archive_method else "deflate (Default)"
        )

        archive_format = user_dict.get("COMPRESSION_ARCHIVE_FORMAT", None)
        if archive_format is None and hasattr(Config, "COMPRESSION_ARCHIVE_FORMAT"):
            archive_format = Config.COMPRESSION_ARCHIVE_FORMAT
        archive_format_str = (
            f"{archive_format}" if archive_format else "none (Default)"
        )

        # Get archive password setting
        archive_password = user_dict.get("COMPRESSION_ARCHIVE_PASSWORD", None)
        if archive_password is None and hasattr(
            Config, "COMPRESSION_ARCHIVE_PASSWORD"
        ):
            archive_password = Config.COMPRESSION_ARCHIVE_PASSWORD
        # Don't show the actual password for security reasons
        archive_password_str = (
            "Set"
            if archive_password and archive_password.lower() != "none"
            else "none (Default)"
        )

        # Get archive algorithm setting
        archive_algorithm = user_dict.get("COMPRESSION_ARCHIVE_ALGORITHM", None)
        if archive_algorithm is None and hasattr(
            Config, "COMPRESSION_ARCHIVE_ALGORITHM"
        ):
            archive_algorithm = Config.COMPRESSION_ARCHIVE_ALGORITHM
        archive_algorithm_str = (
            f"{archive_algorithm}" if archive_algorithm else "none (Default)"
        )

        # Check if the selected algorithm supports password protection
        if (
            archive_password
            and archive_password.lower() != "none"
            and archive_algorithm
        ) and archive_algorithm.lower() not in ["7z", "zip", "rar"]:
            archive_password_str += " (Not supported with " + archive_algorithm + ")"

        # Get compression enabled status for each type
        # Video compression status
        video_compression_enabled = user_dict.get("COMPRESSION_VIDEO_ENABLED", False)
        owner_video_compression_enabled = (
            hasattr(Config, "COMPRESSION_VIDEO_ENABLED")
            and Config.COMPRESSION_VIDEO_ENABLED
        )

        if "COMPRESSION_VIDEO_ENABLED" in user_dict:
            if video_compression_enabled:
                video_status = "✅ Enabled (User)"
            else:
                video_status = "❌ Disabled (User)"
        elif owner_video_compression_enabled:
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Audio compression status
        audio_compression_enabled = user_dict.get("COMPRESSION_AUDIO_ENABLED", False)
        owner_audio_compression_enabled = (
            hasattr(Config, "COMPRESSION_AUDIO_ENABLED")
            and Config.COMPRESSION_AUDIO_ENABLED
        )

        if "COMPRESSION_AUDIO_ENABLED" in user_dict:
            if audio_compression_enabled:
                audio_status = "✅ Enabled (User)"
            else:
                audio_status = "❌ Disabled (User)"
        elif owner_audio_compression_enabled:
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Image compression status
        image_compression_enabled = user_dict.get("COMPRESSION_IMAGE_ENABLED", False)
        owner_image_compression_enabled = (
            hasattr(Config, "COMPRESSION_IMAGE_ENABLED")
            and Config.COMPRESSION_IMAGE_ENABLED
        )

        if "COMPRESSION_IMAGE_ENABLED" in user_dict:
            if image_compression_enabled:
                image_status = "✅ Enabled (User)"
            else:
                image_status = "❌ Disabled (User)"
        elif owner_image_compression_enabled:
            image_status = "✅ Enabled (Global)"
        else:
            image_status = "❌ Disabled"

        # Document compression status
        document_compression_enabled = user_dict.get(
            "COMPRESSION_DOCUMENT_ENABLED", False
        )
        owner_document_compression_enabled = (
            hasattr(Config, "COMPRESSION_DOCUMENT_ENABLED")
            and Config.COMPRESSION_DOCUMENT_ENABLED
        )

        if "COMPRESSION_DOCUMENT_ENABLED" in user_dict:
            if document_compression_enabled:
                document_status = "✅ Enabled (User)"
            else:
                document_status = "❌ Disabled (User)"
        elif owner_document_compression_enabled:
            document_status = "✅ Enabled (Global)"
        else:
            document_status = "❌ Disabled"

        # Subtitle compression status
        subtitle_compression_enabled = user_dict.get(
            "COMPRESSION_SUBTITLE_ENABLED", False
        )
        owner_subtitle_compression_enabled = (
            hasattr(Config, "COMPRESSION_SUBTITLE_ENABLED")
            and Config.COMPRESSION_SUBTITLE_ENABLED
        )

        if "COMPRESSION_SUBTITLE_ENABLED" in user_dict:
            if subtitle_compression_enabled:
                subtitle_status = "✅ Enabled (User)"
            else:
                subtitle_status = "❌ Disabled (User)"
        elif owner_subtitle_compression_enabled:
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Archive compression status
        archive_compression_enabled = user_dict.get(
            "COMPRESSION_ARCHIVE_ENABLED", False
        )
        owner_archive_compression_enabled = (
            hasattr(Config, "COMPRESSION_ARCHIVE_ENABLED")
            and Config.COMPRESSION_ARCHIVE_ENABLED
        )

        if "COMPRESSION_ARCHIVE_ENABLED" in user_dict:
            if archive_compression_enabled:
                archive_status = "✅ Enabled (User)"
            else:
                archive_status = "❌ Disabled (User)"
        elif owner_archive_compression_enabled:
            archive_status = "✅ Enabled (Global)"
        else:
            archive_status = "❌ Disabled"

        # Get video bitdepth, bitrate, and resolution settings
        video_bitdepth = user_dict.get("COMPRESSION_VIDEO_BITDEPTH", None)
        if video_bitdepth is None and hasattr(Config, "COMPRESSION_VIDEO_BITDEPTH"):
            video_bitdepth = Config.COMPRESSION_VIDEO_BITDEPTH
        video_bitdepth_str = (
            f"{video_bitdepth}" if video_bitdepth else "none (Default)"
        )

        video_bitrate = user_dict.get("COMPRESSION_VIDEO_BITRATE", None)
        if video_bitrate is None and hasattr(Config, "COMPRESSION_VIDEO_BITRATE"):
            video_bitrate = Config.COMPRESSION_VIDEO_BITRATE
        video_bitrate_str = f"{video_bitrate}" if video_bitrate else "none (Default)"

        video_resolution = user_dict.get("COMPRESSION_VIDEO_RESOLUTION", None)
        if video_resolution is None and hasattr(
            Config, "COMPRESSION_VIDEO_RESOLUTION"
        ):
            video_resolution = Config.COMPRESSION_VIDEO_RESOLUTION
        video_resolution_str = (
            f"{video_resolution}" if video_resolution else "none (Default)"
        )

        # Get audio bitdepth setting
        audio_bitdepth = user_dict.get("COMPRESSION_AUDIO_BITDEPTH", None)
        if audio_bitdepth is None and hasattr(Config, "COMPRESSION_AUDIO_BITDEPTH"):
            audio_bitdepth = Config.COMPRESSION_AUDIO_BITDEPTH
        audio_bitdepth_str = (
            f"{audio_bitdepth}" if audio_bitdepth else "none (Default)"
        )

        text = f"""⌬ <b>Compression Configuration :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>RO</b> → {delete_original_status}
┃
┠ <b>Video Compression</b> → {video_status}
┠ <b>Video Preset</b> → <code>{video_preset_str}</code>
┠ <b>Video CRF</b> → <code>{video_crf_str}</code>
┠ <b>Video Codec</b> → <code>{video_codec_str}</code>
┠ <b>Video Tune</b> → <code>{video_tune_str}</code>
┠ <b>Video Pixel Format</b> → <code>{video_pixel_format_str}</code>
┠ <b>Video Bitdepth</b> → <code>{video_bitdepth_str}</code>
┠ <b>Video Bitrate</b> → <code>{video_bitrate_str}</code>
┠ <b>Video Resolution</b> → <code>{video_resolution_str}</code>
┠ <b>Video Format</b> → <code>{video_format_str}</code>
┃
┠ <b>Audio Compression</b> → {audio_status}
┠ <b>Audio Preset</b> → <code>{audio_preset_str}</code>
┠ <b>Audio Codec</b> → <code>{audio_codec_str}</code>
┠ <b>Audio Bitrate</b> → <code>{audio_bitrate_str}</code>
┠ <b>Audio Bitdepth</b> → <code>{audio_bitdepth_str}</code>
┠ <b>Audio Channels</b> → <code>{audio_channels_str}</code>
┠ <b>Audio Format</b> → <code>{audio_format_str}</code>
┃
┠ <b>Image Compression</b> → {image_status}
┠ <b>Image Preset</b> → <code>{image_preset_str}</code>
┠ <b>Image Quality</b> → <code>{image_quality_str}</code>
┠ <b>Image Resize</b> → <code>{image_resize_str}</code>
┠ <b>Image Format</b> → <code>{image_format_str}</code>
┃
┠ <b>Document Compression</b> → {document_status}
┠ <b>Document Preset</b> → <code>{document_preset_str}</code>
┠ <b>Document DPI</b> → <code>{document_dpi_str}</code>
┠ <b>Document Format</b> → <code>{document_format_str}</code>
┃
┠ <b>Subtitle Compression</b> → {subtitle_status}
┠ <b>Subtitle Preset</b> → <code>{subtitle_preset_str}</code>
┠ <b>Subtitle Encoding</b> → <code>{subtitle_encoding_str}</code>
┠ <b>Subtitle Format</b> → <code>{subtitle_format_str}</code>
┃
┠ <b>Archive Compression</b> → {archive_status}
┠ <b>Archive Preset</b> → <code>{archive_preset_str}</code>
┠ <b>Archive Level</b> → <code>{archive_level_str}</code>
┠ <b>Archive Method</b> → <code>{archive_method_str}</code>
┠ <b>Archive Format</b> → <code>{archive_format_str}</code>
┠ <b>Archive Password</b> → <code>{archive_password_str}</code>
┖ <b>Archive Algorithm</b> → <code>{archive_algorithm_str}</code>

<b>Usage:</b>
• Enable compression to reduce file sizes
• RO (Remove Original) deletes original files after compression
• Configure different compression settings for each file type
• Example: <code>/leech https://example.com/file.mp4 -compress</code>
• Example: <code>/leech https://example.com/file.mp4 -compress -del</code>"""

    elif stype == "convert":
        # Convert settings menu
        convert_enabled = user_dict.get("CONVERT_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if convert_enabled else "❌ Disabled",
            f"mediatools {user_id} tog CONVERT_ENABLED {'f' if convert_enabled else 't'}",
        )

        # Add global delete original toggle
        # Check for user setting first, then global setting, then default to True
        delete_original = user_dict.get("CONVERT_DELETE_ORIGINAL", None)
        if delete_original is None and hasattr(Config, "CONVERT_DELETE_ORIGINAL"):
            delete_original = Config.CONVERT_DELETE_ORIGINAL
        elif delete_original is None:
            delete_original = True  # Default to True if not specified

        buttons.data_button(
            f"RO: {'✅ ON' if delete_original else '❌ OFF'}",
            f"mediatools {user_id} tog CONVERT_DELETE_ORIGINAL {'f' if delete_original else 't'}",
        )

        # Media type buttons
        buttons.data_button("Video Convert", f"mediatools {user_id} convert_video")
        buttons.data_button("Audio Convert", f"mediatools {user_id} convert_audio")
        buttons.data_button(
            "Subtitle Convert", f"mediatools {user_id} convert_subtitle"
        )
        buttons.data_button(
            "Document Convert", f"mediatools {user_id} convert_document"
        )
        buttons.data_button(
            "Archive Convert", f"mediatools {user_id} convert_archive"
        )

        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu CONVERT_PRIORITY"
        )
        buttons.data_button("Reset", f"mediatools {user_id} reset_convert")
        buttons.data_button("Remove", f"mediatools {user_id} remove_convert")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get convert priority
        user_has_priority = "CONVERT_PRIORITY" in user_dict
        if user_has_priority:
            convert_priority = f"{user_dict['CONVERT_PRIORITY']} (User)"
        elif hasattr(Config, "CONVERT_PRIORITY") and Config.CONVERT_PRIORITY:
            convert_priority = f"{Config.CONVERT_PRIORITY} (Global)"
        else:
            convert_priority = "3 (Default)"

        # Get delete original status
        # Check for user setting first, then global setting, then default to True
        delete_original = user_dict.get("CONVERT_DELETE_ORIGINAL", None)
        if delete_original is None and hasattr(Config, "CONVERT_DELETE_ORIGINAL"):
            delete_original = Config.CONVERT_DELETE_ORIGINAL
        elif delete_original is None:
            delete_original = True  # Default to True if not specified

        # Determine display string with appropriate label
        if "CONVERT_DELETE_ORIGINAL" in user_dict:
            delete_original_status = (
                f"{'✅ Enabled' if delete_original else '❌ Disabled'} (User)"
            )
        elif hasattr(Config, "CONVERT_DELETE_ORIGINAL"):
            delete_original_status = (
                f"{'✅ Enabled' if delete_original else '❌ Disabled'} (Global)"
            )
        else:
            delete_original_status = "✅ Enabled (Default)"

        # Get video convert enabled status
        video_convert_enabled = user_dict.get("CONVERT_VIDEO_ENABLED", False)
        owner_video_enabled = (
            hasattr(Config, "CONVERT_VIDEO_ENABLED") and Config.CONVERT_VIDEO_ENABLED
        )

        if "CONVERT_VIDEO_ENABLED" in user_dict:
            if video_convert_enabled:
                video_enabled_status = "✅ Enabled (User)"
            else:
                video_enabled_status = "❌ Disabled (User)"
        elif owner_video_enabled:
            video_enabled_status = "✅ Enabled (Global)"
        else:
            video_enabled_status = "❌ Disabled"

        # Get audio convert enabled status
        audio_convert_enabled = user_dict.get("CONVERT_AUDIO_ENABLED", False)
        owner_audio_enabled = (
            hasattr(Config, "CONVERT_AUDIO_ENABLED") and Config.CONVERT_AUDIO_ENABLED
        )

        if "CONVERT_AUDIO_ENABLED" in user_dict:
            if audio_convert_enabled:
                audio_enabled_status = "✅ Enabled (User)"
            else:
                audio_enabled_status = "❌ Disabled (User)"
        elif owner_audio_enabled:
            audio_enabled_status = "✅ Enabled (Global)"
        else:
            audio_enabled_status = "❌ Disabled"

        # Get subtitle convert enabled status
        subtitle_convert_enabled = user_dict.get("CONVERT_SUBTITLE_ENABLED", False)
        owner_subtitle_enabled = (
            hasattr(Config, "CONVERT_SUBTITLE_ENABLED")
            and Config.CONVERT_SUBTITLE_ENABLED
        )

        if "CONVERT_SUBTITLE_ENABLED" in user_dict:
            if subtitle_convert_enabled:
                subtitle_enabled_status = "✅ Enabled (User)"
            else:
                subtitle_enabled_status = "❌ Disabled (User)"
        elif owner_subtitle_enabled:
            subtitle_enabled_status = "✅ Enabled (Global)"
        else:
            subtitle_enabled_status = "❌ Disabled"

        # Get document convert enabled status
        document_convert_enabled = user_dict.get("CONVERT_DOCUMENT_ENABLED", False)
        owner_document_enabled = (
            hasattr(Config, "CONVERT_DOCUMENT_ENABLED")
            and Config.CONVERT_DOCUMENT_ENABLED
        )

        if "CONVERT_DOCUMENT_ENABLED" in user_dict:
            if document_convert_enabled:
                document_enabled_status = "✅ Enabled (User)"
            else:
                document_enabled_status = "❌ Disabled (User)"
        elif owner_document_enabled:
            document_enabled_status = "✅ Enabled (Global)"
        else:
            document_enabled_status = "❌ Disabled"

        # Get archive convert enabled status
        archive_convert_enabled = user_dict.get("CONVERT_ARCHIVE_ENABLED", False)
        owner_archive_enabled = (
            hasattr(Config, "CONVERT_ARCHIVE_ENABLED")
            and Config.CONVERT_ARCHIVE_ENABLED
        )

        if "CONVERT_ARCHIVE_ENABLED" in user_dict:
            if archive_convert_enabled:
                archive_enabled_status = "✅ Enabled (User)"
            else:
                archive_enabled_status = "❌ Disabled (User)"
        elif owner_archive_enabled:
            archive_enabled_status = "✅ Enabled (Global)"
        else:
            archive_enabled_status = "❌ Disabled"

        # Get video convert format
        user_has_video_format = (
            "CONVERT_VIDEO_FORMAT" in user_dict and user_dict["CONVERT_VIDEO_FORMAT"]
        )
        owner_has_video_format = (
            hasattr(Config, "CONVERT_VIDEO_FORMAT") and Config.CONVERT_VIDEO_FORMAT
        )

        if user_has_video_format:
            video_format = f"{user_dict['CONVERT_VIDEO_FORMAT']} (User)"
        elif owner_has_video_format:
            video_format = f"{Config.CONVERT_VIDEO_FORMAT} (Global)"
        else:
            video_format = "mp4 (Default)"

        # Get audio convert format
        user_has_audio_format = (
            "CONVERT_AUDIO_FORMAT" in user_dict and user_dict["CONVERT_AUDIO_FORMAT"]
        )
        owner_has_audio_format = (
            hasattr(Config, "CONVERT_AUDIO_FORMAT") and Config.CONVERT_AUDIO_FORMAT
        )

        if user_has_audio_format:
            audio_format = f"{user_dict['CONVERT_AUDIO_FORMAT']} (User)"
        elif owner_has_audio_format:
            audio_format = f"{Config.CONVERT_AUDIO_FORMAT} (Global)"
        else:
            audio_format = "mp3 (Default)"

        # Get subtitle convert format
        user_has_subtitle_format = (
            "CONVERT_SUBTITLE_FORMAT" in user_dict
            and user_dict["CONVERT_SUBTITLE_FORMAT"]
        )
        owner_has_subtitle_format = (
            hasattr(Config, "CONVERT_SUBTITLE_FORMAT")
            and Config.CONVERT_SUBTITLE_FORMAT
        )

        if user_has_subtitle_format:
            subtitle_format = f"{user_dict['CONVERT_SUBTITLE_FORMAT']} (User)"
        elif owner_has_subtitle_format:
            subtitle_format = f"{Config.CONVERT_SUBTITLE_FORMAT} (Global)"
        else:
            subtitle_format = "srt (Default)"

        # Get document convert format
        user_has_document_format = (
            "CONVERT_DOCUMENT_FORMAT" in user_dict
            and user_dict["CONVERT_DOCUMENT_FORMAT"]
        )
        owner_has_document_format = (
            hasattr(Config, "CONVERT_DOCUMENT_FORMAT")
            and Config.CONVERT_DOCUMENT_FORMAT
        )

        if user_has_document_format:
            document_format = f"{user_dict['CONVERT_DOCUMENT_FORMAT']} (User)"
        elif owner_has_document_format:
            document_format = f"{Config.CONVERT_DOCUMENT_FORMAT} (Global)"
        else:
            document_format = "pdf (Default)"

        # Get archive convert format
        user_has_archive_format = (
            "CONVERT_ARCHIVE_FORMAT" in user_dict
            and user_dict["CONVERT_ARCHIVE_FORMAT"]
        )
        owner_has_archive_format = (
            hasattr(Config, "CONVERT_ARCHIVE_FORMAT")
            and Config.CONVERT_ARCHIVE_FORMAT
        )

        if user_has_archive_format:
            archive_format = f"{user_dict['CONVERT_ARCHIVE_FORMAT']} (User)"
        elif owner_has_archive_format:
            archive_format = f"{Config.CONVERT_ARCHIVE_FORMAT} (Global)"
        else:
            archive_format = "zip (Default)"

        text = f"""⌬ <b>Convert Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if convert_enabled else "❌ Disabled"}
┠ <b>Priority</b> → <code>{convert_priority}</code>
┠ <b>RO</b> → {delete_original_status}
┃
┠ <b>Video Convert</b> → {video_enabled_status}
┠ <b>Video Format</b> → <code>{video_format}</code>
┃
┠ <b>Audio Convert</b> → {audio_enabled_status}
┠ <b>Audio Format</b> → <code>{audio_format}</code>
┃
┠ <b>Subtitle Convert</b> → {subtitle_enabled_status}
┠ <b>Subtitle Format</b> → <code>{subtitle_format}</code>
┃
┠ <b>Document Convert</b> → {document_enabled_status}
┠ <b>Document Format</b> → <code>{document_format}</code>
┃
┠ <b>Archive Convert</b> → {archive_enabled_status}
┖ <b>Archive Format</b> → <code>{archive_format}</code>

<b>Usage:</b>
• Use <code>-cv format</code> for video conversion (e.g., <code>-cv mp4</code>)
• Use <code>-ca format</code> for audio conversion (e.g., <code>-ca mp3</code>)
• Use <code>-cs format</code> for subtitle conversion (e.g., <code>-cs srt</code>)
• Use <code>-cd format</code> for document conversion (e.g., <code>-cd pdf</code>)
• Use <code>-cr format</code> for archive conversion (e.g., <code>-cr zip</code>)
• RO (Remove Original) deletes original files after conversion
• Add <code>-del</code> to delete original files after conversion
• Example: <code>/leech https://example.com/file.mkv -cv mp4</code>
• Example: <code>/leech https://example.com/file.mkv -cv mp4 -del</code>"""

    elif stype == "convert_video":
        # Video Convert settings menu
        # Add toggle for video convert enabled
        video_convert_enabled = user_dict.get("CONVERT_VIDEO_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if video_convert_enabled else "❌ Disabled",
            f"mediatools {user_id} tog CONVERT_VIDEO_ENABLED {'f' if video_convert_enabled else 't'}",
        )

        buttons.data_button(
            "Set Format", f"mediatools {user_id} menu CONVERT_VIDEO_FORMAT"
        )
        buttons.data_button(
            "Set Codec", f"mediatools {user_id} menu CONVERT_VIDEO_CODEC"
        )
        buttons.data_button(
            "Set Quality", f"mediatools {user_id} menu CONVERT_VIDEO_QUALITY"
        )
        buttons.data_button(
            "Set CRF", f"mediatools {user_id} menu CONVERT_VIDEO_CRF"
        )
        buttons.data_button(
            "Set Preset", f"mediatools {user_id} menu CONVERT_VIDEO_PRESET"
        )
        buttons.data_button(
            "Set Resolution", f"mediatools {user_id} menu CONVERT_VIDEO_RESOLUTION"
        )
        buttons.data_button(
            "Set FPS", f"mediatools {user_id} menu CONVERT_VIDEO_FPS"
        )

        # Add toggle for maintaining original quality
        maintain_quality = user_dict.get("CONVERT_VIDEO_MAINTAIN_QUALITY", True)
        buttons.data_button(
            f"Quality: {'✅ High' if maintain_quality else '❌ Normal'}",
            f"mediatools {user_id} tog CONVERT_VIDEO_MAINTAIN_QUALITY {'f' if maintain_quality else 't'}",
        )

        buttons.data_button("Back", f"mediatools {user_id} convert", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get video convert settings
        user_has_format = (
            "CONVERT_VIDEO_FORMAT" in user_dict
            and user_dict["CONVERT_VIDEO_FORMAT"]
            and user_dict["CONVERT_VIDEO_FORMAT"].lower() != "none"
        )
        owner_has_format = (
            hasattr(Config, "CONVERT_VIDEO_FORMAT")
            and Config.CONVERT_VIDEO_FORMAT
            and Config.CONVERT_VIDEO_FORMAT.lower() != "none"
        )

        if user_has_format:
            video_format = f"{user_dict['CONVERT_VIDEO_FORMAT']} (User)"
        elif owner_has_format:
            video_format = f"{Config.CONVERT_VIDEO_FORMAT} (Global)"
        else:
            video_format = "none (Default)"

        # Get video codec
        user_has_codec = (
            "CONVERT_VIDEO_CODEC" in user_dict
            and user_dict["CONVERT_VIDEO_CODEC"]
            and user_dict["CONVERT_VIDEO_CODEC"].lower() != "none"
        )
        owner_has_codec = (
            hasattr(Config, "CONVERT_VIDEO_CODEC")
            and Config.CONVERT_VIDEO_CODEC
            and Config.CONVERT_VIDEO_CODEC.lower() != "none"
        )

        if user_has_codec:
            video_codec = f"{user_dict['CONVERT_VIDEO_CODEC']} (User)"
        elif owner_has_codec:
            video_codec = f"{Config.CONVERT_VIDEO_CODEC} (Global)"
        else:
            video_codec = "none (Default)"

        # Get video quality
        user_has_quality = (
            "CONVERT_VIDEO_QUALITY" in user_dict
            and user_dict["CONVERT_VIDEO_QUALITY"]
            and user_dict["CONVERT_VIDEO_QUALITY"].lower() != "none"
        )
        owner_has_quality = (
            hasattr(Config, "CONVERT_VIDEO_QUALITY")
            and Config.CONVERT_VIDEO_QUALITY
            and Config.CONVERT_VIDEO_QUALITY.lower() != "none"
        )

        if user_has_quality:
            video_quality = f"{user_dict['CONVERT_VIDEO_QUALITY']} (User)"
        elif owner_has_quality:
            video_quality = f"{Config.CONVERT_VIDEO_QUALITY} (Global)"
        else:
            video_quality = "none (Default)"

        # Get video CRF
        user_has_crf = (
            "CONVERT_VIDEO_CRF" in user_dict
            and user_dict["CONVERT_VIDEO_CRF"]
            and user_dict["CONVERT_VIDEO_CRF"] != 0
        )
        owner_has_crf = (
            hasattr(Config, "CONVERT_VIDEO_CRF")
            and Config.CONVERT_VIDEO_CRF
            and Config.CONVERT_VIDEO_CRF != 0
        )

        if user_has_crf:
            video_crf = f"{user_dict['CONVERT_VIDEO_CRF']} (User)"
        elif owner_has_crf:
            video_crf = f"{Config.CONVERT_VIDEO_CRF} (Global)"
        else:
            video_crf = "0 (Default)"

        # Get video preset
        user_has_preset = (
            "CONVERT_VIDEO_PRESET" in user_dict
            and user_dict["CONVERT_VIDEO_PRESET"]
            and user_dict["CONVERT_VIDEO_PRESET"].lower() != "none"
        )
        owner_has_preset = (
            hasattr(Config, "CONVERT_VIDEO_PRESET")
            and Config.CONVERT_VIDEO_PRESET
            and Config.CONVERT_VIDEO_PRESET.lower() != "none"
        )

        if user_has_preset:
            video_preset = f"{user_dict['CONVERT_VIDEO_PRESET']} (User)"
        elif owner_has_preset:
            video_preset = f"{Config.CONVERT_VIDEO_PRESET} (Global)"
        else:
            video_preset = "none (Default)"

        # Get video resolution
        user_has_resolution = (
            "CONVERT_VIDEO_RESOLUTION" in user_dict
            and user_dict["CONVERT_VIDEO_RESOLUTION"]
            and user_dict["CONVERT_VIDEO_RESOLUTION"].lower() != "none"
        )
        owner_has_resolution = (
            hasattr(Config, "CONVERT_VIDEO_RESOLUTION")
            and Config.CONVERT_VIDEO_RESOLUTION
            and Config.CONVERT_VIDEO_RESOLUTION.lower() != "none"
        )

        if user_has_resolution:
            video_resolution = f"{user_dict['CONVERT_VIDEO_RESOLUTION']} (User)"
        elif owner_has_resolution:
            video_resolution = f"{Config.CONVERT_VIDEO_RESOLUTION} (Global)"
        else:
            video_resolution = "none (Default)"

        # Get video FPS
        user_has_fps = (
            "CONVERT_VIDEO_FPS" in user_dict
            and user_dict["CONVERT_VIDEO_FPS"]
            and user_dict["CONVERT_VIDEO_FPS"].lower() != "none"
        )
        owner_has_fps = (
            hasattr(Config, "CONVERT_VIDEO_FPS")
            and Config.CONVERT_VIDEO_FPS
            and Config.CONVERT_VIDEO_FPS.lower() != "none"
        )

        if user_has_fps:
            video_fps = f"{user_dict['CONVERT_VIDEO_FPS']} (User)"
        elif owner_has_fps:
            video_fps = f"{Config.CONVERT_VIDEO_FPS} (Global)"
        else:
            video_fps = "none (Default)"

        # Get maintain quality status
        user_has_maintain_quality = "CONVERT_VIDEO_MAINTAIN_QUALITY" in user_dict
        if user_has_maintain_quality:
            maintain_quality_status = (
                "✅ High (User)"
                if user_dict["CONVERT_VIDEO_MAINTAIN_QUALITY"]
                else "❌ Normal (User)"
            )
        elif hasattr(Config, "CONVERT_VIDEO_MAINTAIN_QUALITY"):
            # Check the global setting
            maintain_quality_status = (
                "✅ High (Global)"
                if Config.CONVERT_VIDEO_MAINTAIN_QUALITY
                else "❌ Normal (Global)"
            )
        else:
            # Default value from config is True
            maintain_quality_status = "✅ High (Default)"

        # Get video convert enabled status
        video_convert_enabled = user_dict.get("CONVERT_VIDEO_ENABLED", False)
        owner_video_enabled = (
            hasattr(Config, "CONVERT_VIDEO_ENABLED") and Config.CONVERT_VIDEO_ENABLED
        )

        if "CONVERT_VIDEO_ENABLED" in user_dict:
            if video_convert_enabled:
                video_enabled_status = "✅ Enabled (User)"
            else:
                video_enabled_status = "❌ Disabled (User)"
        elif owner_video_enabled:
            video_enabled_status = "✅ Enabled (Global)"
        else:
            video_enabled_status = "❌ Disabled"

        text = f"""⌬ <b>Video Convert Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {video_enabled_status}
┠ <b>Format</b> → <code>{video_format}</code>
┠ <b>Codec</b> → <code>{video_codec}</code>
┠ <b>Quality</b> → <code>{video_quality}</code>
┠ <b>CRF</b> → <code>{video_crf}</code>
┠ <b>Preset</b> → <code>{video_preset}</code>
┠ <b>Resolution</b> → <code>{video_resolution}</code>
┠ <b>FPS</b> → <code>{video_fps}</code>
┖ <b>Quality</b> → {maintain_quality_status}"""

    elif stype == "extract":
        # Extract settings menu
        extract_enabled = user_dict.get("EXTRACT_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if extract_enabled else "❌ Disabled",
            f"mediatools {user_id} tog EXTRACT_ENABLED {'f' if extract_enabled else 't'}",
        )
        buttons.data_button("Configure", f"mediatools {user_id} extract_config")
        buttons.data_button(
            "Set Priority", f"mediatools {user_id} menu EXTRACT_PRIORITY"
        )
        buttons.data_button("Reset", f"mediatools {user_id} reset_extract")
        buttons.data_button("Remove", f"mediatools {user_id} remove_extract")
        buttons.data_button("Back", f"mediatools {user_id} back", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get extract priority
        user_has_priority = (
            "EXTRACT_PRIORITY" in user_dict and user_dict["EXTRACT_PRIORITY"]
        )
        if user_has_priority:
            priority = f"{user_dict['EXTRACT_PRIORITY']} (User)"
        elif hasattr(Config, "EXTRACT_PRIORITY") and Config.EXTRACT_PRIORITY:
            priority = f"{Config.EXTRACT_PRIORITY} (Global)"
        else:
            priority = "6 (Default)"

        # Get video extract status
        video_enabled = user_dict.get("EXTRACT_VIDEO_ENABLED", False)
        if "EXTRACT_VIDEO_ENABLED" in user_dict:
            video_status = (
                "✅ Enabled (User)" if video_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "EXTRACT_VIDEO_ENABLED") and Config.EXTRACT_VIDEO_ENABLED
        ):
            video_status = "✅ Enabled (Global)"
        else:
            video_status = "❌ Disabled"

        # Get audio extract status
        audio_enabled = user_dict.get("EXTRACT_AUDIO_ENABLED", False)
        if "EXTRACT_AUDIO_ENABLED" in user_dict:
            audio_status = (
                "✅ Enabled (User)" if audio_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "EXTRACT_AUDIO_ENABLED") and Config.EXTRACT_AUDIO_ENABLED
        ):
            audio_status = "✅ Enabled (Global)"
        else:
            audio_status = "❌ Disabled"

        # Get subtitle extract status
        subtitle_enabled = user_dict.get("EXTRACT_SUBTITLE_ENABLED", False)
        if "EXTRACT_SUBTITLE_ENABLED" in user_dict:
            subtitle_status = (
                "✅ Enabled (User)" if subtitle_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "EXTRACT_SUBTITLE_ENABLED")
            and Config.EXTRACT_SUBTITLE_ENABLED
        ):
            subtitle_status = "✅ Enabled (Global)"
        else:
            subtitle_status = "❌ Disabled"

        # Get attachment extract status
        attachment_enabled = user_dict.get("EXTRACT_ATTACHMENT_ENABLED", False)
        if "EXTRACT_ATTACHMENT_ENABLED" in user_dict:
            attachment_status = (
                "✅ Enabled (User)" if attachment_enabled else "❌ Disabled (User)"
            )
        elif (
            hasattr(Config, "EXTRACT_ATTACHMENT_ENABLED")
            and Config.EXTRACT_ATTACHMENT_ENABLED
        ):
            attachment_status = "✅ Enabled (Global)"
        else:
            attachment_status = "❌ Disabled"

        text = f"""⌬ <b>Extract Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {"✅ Enabled" if extract_enabled else "❌ Disabled"}
┠ <b>Priority</b> → {priority}
┃
┠ <b>Video</b> → {video_status}
┠ <b>Audio</b> → {audio_status}
┠ <b>Subtitle</b> → {subtitle_status}
┖ <b>Attachment</b> → {attachment_status}

<b>Help:</b>
• Click the "✅ Enabled/❌ Disabled" button to toggle extract feature
• Click "Configure" to set up detailed extraction options
• Click "Set Priority" to change when extraction runs in the pipeline
• Enable specific track types in the Configure menu
• Use track indices to extract only specific tracks
• The extract feature extracts media tracks from container files
• Example: Extract audio tracks from video files as MP3s
• Example: Extract subtitles from video files as SRT files
• Example: <code>/leech https://example.com/file.mkv -extract</code>"""

    elif stype == "extract_config":
        # Extract configuration menu
        # Video extract settings
        video_enabled = user_dict.get("EXTRACT_VIDEO_ENABLED", False)
        buttons.data_button(
            f"Video: {'✅ ON' if video_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_VIDEO_ENABLED {'f' if video_enabled else 't'}",
        )
        buttons.data_button(
            "Video Settings", f"mediatools {user_id} extract_video_config"
        )

        # Audio extract settings
        audio_enabled = user_dict.get("EXTRACT_AUDIO_ENABLED", False)
        buttons.data_button(
            f"Audio: {'✅ ON' if audio_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_AUDIO_ENABLED {'f' if audio_enabled else 't'}",
        )
        buttons.data_button(
            "Audio Settings", f"mediatools {user_id} extract_audio_config"
        )

        # Subtitle extract settings
        subtitle_enabled = user_dict.get("EXTRACT_SUBTITLE_ENABLED", False)
        buttons.data_button(
            f"Subtitle: {'✅ ON' if subtitle_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_SUBTITLE_ENABLED {'f' if subtitle_enabled else 't'}",
        )
        buttons.data_button(
            "Subtitle Settings", f"mediatools {user_id} extract_subtitle_config"
        )

        # Attachment extract settings
        attachment_enabled = user_dict.get("EXTRACT_ATTACHMENT_ENABLED", False)
        buttons.data_button(
            f"Attachment: {'✅ ON' if attachment_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_ATTACHMENT_ENABLED {'f' if attachment_enabled else 't'}",
        )
        buttons.data_button(
            "Attachment Settings", f"mediatools {user_id} extract_attachment_config"
        )

        # Delete original toggle
        delete_original = user_dict.get("EXTRACT_DELETE_ORIGINAL", True)
        buttons.data_button(
            f"RO: {'✅ ON' if delete_original else '❌ OFF'}",
            f"mediatools {user_id} tog EXTRACT_DELETE_ORIGINAL {'f' if delete_original else 't'}",
        )

        # Maintain quality toggle
        maintain_quality = user_dict.get("EXTRACT_MAINTAIN_QUALITY", True)
        buttons.data_button(
            f"Quality: {'✅ High' if maintain_quality else '❌ Normal'}",
            f"mediatools {user_id} tog EXTRACT_MAINTAIN_QUALITY {'f' if maintain_quality else 't'}",
        )

        buttons.data_button("Back", f"mediatools {user_id} extract", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get delete original setting
        delete_original_str = "✅ Enabled" if delete_original else "❌ Disabled"

        # Get maintain quality setting
        maintain_quality_str = "✅ Enabled" if maintain_quality else "❌ Disabled"

        text = f"""⌬ <b>Extract Configuration :</b>

┠ <b>Video Extract</b> → {"✅ Enabled" if video_enabled else "❌ Disabled"}
┠ <b>Audio Extract</b> → {"✅ Enabled" if audio_enabled else "❌ Disabled"}
┠ <b>Subtitle Extract</b> → {"✅ Enabled" if subtitle_enabled else "❌ Disabled"}
┠ <b>Attachment Extract</b> → {"✅ Enabled" if attachment_enabled else "❌ Disabled"}
┃
┠ <b>RO</b> → {delete_original_str}
┖ <b>Quality</b> → {maintain_quality_str}

<b>Help:</b>
• Click on a track type toggle to enable/disable extraction for that type
• Click on a track type's "Settings" button to configure detailed options
• Set track indices to extract specific tracks (e.g., 0,1,2 or "all")
• Use 'copy' codec to preserve original quality
• When set to 'none', settings won't be used in command generation
• RO: When enabled, original files are deleted after extraction (Remove Original)
• Quality: When set to High, preserves highest possible quality

<b>Usage:</b>
• Enable extract to pull out specific tracks from media files
• Example: <code>/leech https://example.com/file.mkv -extract</code>
• Example: <code>/leech https://example.com/file.mkv -extract -del</code>"""

    elif stype == "extract_video_config":
        # Video extract configuration menu
        buttons.data_button(
            "Codec", f"mediatools {user_id} menu EXTRACT_VIDEO_CODEC"
        )
        buttons.data_button(
            "Format", f"mediatools {user_id} menu EXTRACT_VIDEO_FORMAT"
        )
        buttons.data_button(
            "Index", f"mediatools {user_id} menu EXTRACT_VIDEO_INDEX"
        )
        buttons.data_button(
            "Quality", f"mediatools {user_id} menu EXTRACT_VIDEO_QUALITY"
        )
        buttons.data_button(
            "Preset", f"mediatools {user_id} menu EXTRACT_VIDEO_PRESET"
        )
        buttons.data_button(
            "Bitrate", f"mediatools {user_id} menu EXTRACT_VIDEO_BITRATE"
        )
        buttons.data_button(
            "Resolution", f"mediatools {user_id} menu EXTRACT_VIDEO_RESOLUTION"
        )
        buttons.data_button("FPS", f"mediatools {user_id} menu EXTRACT_VIDEO_FPS")

        buttons.data_button("Back", f"mediatools {user_id} extract_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get video extract settings
        video_codec = user_dict.get("EXTRACT_VIDEO_CODEC", "none")
        if video_codec == "none" and hasattr(Config, "EXTRACT_VIDEO_CODEC"):
            video_codec = Config.EXTRACT_VIDEO_CODEC
        video_codec_str = (
            f"{video_codec}" if video_codec != "none" else "none (Default)"
        )

        video_format = user_dict.get("EXTRACT_VIDEO_FORMAT", "none")
        if video_format == "none" and hasattr(Config, "EXTRACT_VIDEO_FORMAT"):
            video_format = Config.EXTRACT_VIDEO_FORMAT
        video_format_str = (
            f"{video_format}" if video_format != "none" else "none (Default)"
        )

        video_index = user_dict.get("EXTRACT_VIDEO_INDEX", None)
        if video_index is None and hasattr(Config, "EXTRACT_VIDEO_INDEX"):
            video_index = Config.EXTRACT_VIDEO_INDEX
        video_index_str = (
            f"{video_index}" if video_index is not None else "All (Default)"
        )

        # Get additional video settings
        video_quality = user_dict.get("EXTRACT_VIDEO_QUALITY", "none")
        if video_quality == "none" and hasattr(Config, "EXTRACT_VIDEO_QUALITY"):
            video_quality = Config.EXTRACT_VIDEO_QUALITY
        video_quality_str = (
            f"{video_quality}" if video_quality != "none" else "none (Default)"
        )

        video_preset = user_dict.get("EXTRACT_VIDEO_PRESET", "none")
        if video_preset == "none" and hasattr(Config, "EXTRACT_VIDEO_PRESET"):
            video_preset = Config.EXTRACT_VIDEO_PRESET
        video_preset_str = (
            f"{video_preset}" if video_preset != "none" else "none (Default)"
        )

        video_bitrate = user_dict.get("EXTRACT_VIDEO_BITRATE", "none")
        if video_bitrate == "none" and hasattr(Config, "EXTRACT_VIDEO_BITRATE"):
            video_bitrate = Config.EXTRACT_VIDEO_BITRATE
        video_bitrate_str = (
            f"{video_bitrate}" if video_bitrate != "none" else "none (Default)"
        )

        video_resolution = user_dict.get("EXTRACT_VIDEO_RESOLUTION", "none")
        if video_resolution == "none" and hasattr(
            Config, "EXTRACT_VIDEO_RESOLUTION"
        ):
            video_resolution = Config.EXTRACT_VIDEO_RESOLUTION
        video_resolution_str = (
            f"{video_resolution}" if video_resolution != "none" else "none (Default)"
        )

        video_fps = user_dict.get("EXTRACT_VIDEO_FPS", "none")
        if video_fps == "none" and hasattr(Config, "EXTRACT_VIDEO_FPS"):
            video_fps = Config.EXTRACT_VIDEO_FPS
        video_fps_str = f"{video_fps}" if video_fps != "none" else "none (Default)"

        text = f"""<b>Video Extract Configuration</b>

<b>Basic Settings:</b>
┣ <b>Codec:</b> {video_codec_str}
┣ <b>Format:</b> {video_format_str}
┗ <b>Index:</b> {video_index_str}

<b>Advanced Settings:</b>
┣ <b>Quality:</b> {video_quality_str}
┣ <b>Preset:</b> {video_preset_str}
┣ <b>Bitrate:</b> {video_bitrate_str}
┣ <b>Resolution:</b> {video_resolution_str}
┗ <b>FPS:</b> {video_fps_str}

<b>Help:</b>
• <b>Codec:</b> Set the video codec (e.g., copy, h264, h265)
• <b>Format:</b> Set the output format (e.g., mp4, mkv, avi)
• <b>Index:</b> Set specific track indices to extract (e.g., 0,1,2 or "all")
• <b>Quality:</b> Set the quality/CRF value (lower is better quality)
• <b>Preset:</b> Set encoding preset (e.g., ultrafast, medium, veryslow)
• <b>Bitrate:</b> Set video bitrate (e.g., 5M, 10M)
• <b>Resolution:</b> Set video resolution (e.g., 1920x1080)
• <b>FPS:</b> Set video frame rate (e.g., 30, 60)

Use 'copy' codec to preserve original quality. When set to 'none', settings won't be used in command generation."""

    elif stype == "extract_audio_config":
        # Audio extract configuration menu
        buttons.data_button(
            "Codec", f"mediatools {user_id} menu EXTRACT_AUDIO_CODEC"
        )
        buttons.data_button(
            "Format", f"mediatools {user_id} menu EXTRACT_AUDIO_FORMAT"
        )
        buttons.data_button(
            "Index", f"mediatools {user_id} menu EXTRACT_AUDIO_INDEX"
        )
        buttons.data_button(
            "Bitrate", f"mediatools {user_id} menu EXTRACT_AUDIO_BITRATE"
        )
        buttons.data_button(
            "Channels", f"mediatools {user_id} menu EXTRACT_AUDIO_CHANNELS"
        )
        buttons.data_button(
            "Sampling", f"mediatools {user_id} menu EXTRACT_AUDIO_SAMPLING"
        )
        buttons.data_button(
            "Volume", f"mediatools {user_id} menu EXTRACT_AUDIO_VOLUME"
        )

        buttons.data_button("Back", f"mediatools {user_id} extract_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get audio extract settings
        audio_codec = user_dict.get("EXTRACT_AUDIO_CODEC", "none")
        if audio_codec == "none" and hasattr(Config, "EXTRACT_AUDIO_CODEC"):
            audio_codec = Config.EXTRACT_AUDIO_CODEC
        audio_codec_str = (
            f"{audio_codec}" if audio_codec != "none" else "none (Default)"
        )

        audio_format = user_dict.get("EXTRACT_AUDIO_FORMAT", "none")
        if audio_format == "none" and hasattr(Config, "EXTRACT_AUDIO_FORMAT"):
            audio_format = Config.EXTRACT_AUDIO_FORMAT
        audio_format_str = (
            f"{audio_format}" if audio_format != "none" else "none (Default)"
        )

        audio_index = user_dict.get("EXTRACT_AUDIO_INDEX", None)
        if audio_index is None and hasattr(Config, "EXTRACT_AUDIO_INDEX"):
            audio_index = Config.EXTRACT_AUDIO_INDEX
        audio_index_str = (
            f"{audio_index}" if audio_index is not None else "All (Default)"
        )

        # Get additional audio settings
        audio_bitrate = user_dict.get("EXTRACT_AUDIO_BITRATE", "none")
        if audio_bitrate == "none" and hasattr(Config, "EXTRACT_AUDIO_BITRATE"):
            audio_bitrate = Config.EXTRACT_AUDIO_BITRATE
        audio_bitrate_str = (
            f"{audio_bitrate}" if audio_bitrate != "none" else "none (Default)"
        )

        audio_channels = user_dict.get("EXTRACT_AUDIO_CHANNELS", "none")
        if audio_channels == "none" and hasattr(Config, "EXTRACT_AUDIO_CHANNELS"):
            audio_channels = Config.EXTRACT_AUDIO_CHANNELS
        audio_channels_str = (
            f"{audio_channels}" if audio_channels != "none" else "none (Default)"
        )

        audio_sampling = user_dict.get("EXTRACT_AUDIO_SAMPLING", "none")
        if audio_sampling == "none" and hasattr(Config, "EXTRACT_AUDIO_SAMPLING"):
            audio_sampling = Config.EXTRACT_AUDIO_SAMPLING
        audio_sampling_str = (
            f"{audio_sampling}" if audio_sampling != "none" else "none (Default)"
        )

        audio_volume = user_dict.get("EXTRACT_AUDIO_VOLUME", "none")
        if audio_volume == "none" and hasattr(Config, "EXTRACT_AUDIO_VOLUME"):
            audio_volume = Config.EXTRACT_AUDIO_VOLUME
        audio_volume_str = (
            f"{audio_volume}" if audio_volume != "none" else "none (Default)"
        )

        text = f"""<b>Audio Extract Configuration</b>

<b>Basic Settings:</b>
┣ <b>Codec:</b> {audio_codec_str}
┣ <b>Format:</b> {audio_format_str}
┗ <b>Index:</b> {audio_index_str}

<b>Advanced Settings:</b>
┣ <b>Bitrate:</b> {audio_bitrate_str}
┣ <b>Channels:</b> {audio_channels_str}
┣ <b>Sampling:</b> {audio_sampling_str}
┗ <b>Volume:</b> {audio_volume_str}

<b>Help:</b>
• <b>Codec:</b> Set the audio codec (e.g., copy, aac, mp3, opus)
• <b>Format:</b> Set the output format (e.g., mp3, aac, flac, wav)
• <b>Index:</b> Set specific track indices to extract (e.g., 0,1,2 or "all")
• <b>Bitrate:</b> Set audio bitrate (e.g., 128k, 192k, 320k)
• <b>Channels:</b> Set number of audio channels (e.g., 1 for mono, 2 for stereo)
• <b>Sampling:</b> Set audio sampling rate (e.g., 44100, 48000)
• <b>Volume:</b> Set volume adjustment (e.g., 1.0 normal, 1.5 louder)

Use 'copy' codec to preserve original quality. When set to 'none', settings won't be used in command generation."""

    elif stype == "extract_subtitle_config":
        # Subtitle extract configuration menu
        buttons.data_button(
            "Codec", f"mediatools {user_id} menu EXTRACT_SUBTITLE_CODEC"
        )
        buttons.data_button(
            "Format", f"mediatools {user_id} menu EXTRACT_SUBTITLE_FORMAT"
        )
        buttons.data_button(
            "Index", f"mediatools {user_id} menu EXTRACT_SUBTITLE_INDEX"
        )
        buttons.data_button(
            "Language", f"mediatools {user_id} menu EXTRACT_SUBTITLE_LANGUAGE"
        )
        buttons.data_button(
            "Encoding", f"mediatools {user_id} menu EXTRACT_SUBTITLE_ENCODING"
        )
        buttons.data_button(
            "Font", f"mediatools {user_id} menu EXTRACT_SUBTITLE_FONT"
        )
        buttons.data_button(
            "Font Size", f"mediatools {user_id} menu EXTRACT_SUBTITLE_FONT_SIZE"
        )

        buttons.data_button("Back", f"mediatools {user_id} extract_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get subtitle extract settings
        subtitle_codec = user_dict.get("EXTRACT_SUBTITLE_CODEC", "none")
        if subtitle_codec == "none" and hasattr(Config, "EXTRACT_SUBTITLE_CODEC"):
            subtitle_codec = Config.EXTRACT_SUBTITLE_CODEC
        subtitle_codec_str = (
            f"{subtitle_codec}" if subtitle_codec != "none" else "none (Default)"
        )

        subtitle_format = user_dict.get("EXTRACT_SUBTITLE_FORMAT", "none")
        if subtitle_format == "none" and hasattr(Config, "EXTRACT_SUBTITLE_FORMAT"):
            subtitle_format = Config.EXTRACT_SUBTITLE_FORMAT
        subtitle_format_str = (
            f"{subtitle_format}" if subtitle_format != "none" else "none (Default)"
        )

        subtitle_index = user_dict.get("EXTRACT_SUBTITLE_INDEX", None)
        if subtitle_index is None and hasattr(Config, "EXTRACT_SUBTITLE_INDEX"):
            subtitle_index = Config.EXTRACT_SUBTITLE_INDEX
        subtitle_index_str = (
            f"{subtitle_index}" if subtitle_index is not None else "All (Default)"
        )

        # Get additional subtitle settings
        subtitle_language = user_dict.get("EXTRACT_SUBTITLE_LANGUAGE", "none")
        if subtitle_language == "none" and hasattr(
            Config, "EXTRACT_SUBTITLE_LANGUAGE"
        ):
            subtitle_language = Config.EXTRACT_SUBTITLE_LANGUAGE
        subtitle_language_str = (
            f"{subtitle_language}"
            if subtitle_language != "none"
            else "none (Default)"
        )

        subtitle_encoding = user_dict.get("EXTRACT_SUBTITLE_ENCODING", "none")
        if subtitle_encoding == "none" and hasattr(
            Config, "EXTRACT_SUBTITLE_ENCODING"
        ):
            subtitle_encoding = Config.EXTRACT_SUBTITLE_ENCODING
        subtitle_encoding_str = (
            f"{subtitle_encoding}"
            if subtitle_encoding != "none"
            else "none (Default)"
        )

        subtitle_font = user_dict.get("EXTRACT_SUBTITLE_FONT", "none")
        if subtitle_font == "none" and hasattr(Config, "EXTRACT_SUBTITLE_FONT"):
            subtitle_font = Config.EXTRACT_SUBTITLE_FONT
        subtitle_font_str = (
            f"{subtitle_font}" if subtitle_font != "none" else "none (Default)"
        )

        subtitle_font_size = user_dict.get("EXTRACT_SUBTITLE_FONT_SIZE", "none")
        if subtitle_font_size == "none" and hasattr(
            Config, "EXTRACT_SUBTITLE_FONT_SIZE"
        ):
            subtitle_font_size = Config.EXTRACT_SUBTITLE_FONT_SIZE
        subtitle_font_size_str = (
            f"{subtitle_font_size}"
            if subtitle_font_size != "none"
            else "none (Default)"
        )

        text = f"""<b>Subtitle Extract Configuration</b>

<b>Basic Settings:</b>
┣ <b>Codec:</b> {subtitle_codec_str}
┣ <b>Format:</b> {subtitle_format_str}
┗ <b>Index:</b> {subtitle_index_str}

<b>Advanced Settings:</b>
┣ <b>Language:</b> {subtitle_language_str}
┣ <b>Encoding:</b> {subtitle_encoding_str}
┣ <b>Font:</b> {subtitle_font_str}
┗ <b>Font Size:</b> {subtitle_font_size_str}

<b>Help:</b>
• <b>Codec:</b> Set the subtitle codec (e.g., copy, srt, ass, vtt)
• <b>Format:</b> Set the output format (e.g., srt, ass, vtt)
• <b>Index:</b> Set specific track indices to extract (e.g., 0,1,2 or "all")
• <b>Language:</b> Set subtitle language code (e.g., eng, spa, fre)
• <b>Encoding:</b> Set character encoding (e.g., UTF-8, latin1)
• <b>Font:</b> Set font for ASS/SSA subtitles (e.g., Arial)
• <b>Font Size:</b> Set font size for ASS/SSA subtitles (e.g., 24)

Use 'copy' codec to preserve original format or 'srt' to convert ASS/SSA to SRT. When set to 'none', settings won't be used in command generation."""

    elif stype == "extract_attachment_config":
        # Attachment extract configuration menu
        buttons.data_button(
            "Format", f"mediatools {user_id} menu EXTRACT_ATTACHMENT_FORMAT"
        )
        buttons.data_button(
            "Index", f"mediatools {user_id} menu EXTRACT_ATTACHMENT_INDEX"
        )
        buttons.data_button(
            "Filter", f"mediatools {user_id} menu EXTRACT_ATTACHMENT_FILTER"
        )

        buttons.data_button("Back", f"mediatools {user_id} extract_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get attachment extract settings
        attachment_format = user_dict.get("EXTRACT_ATTACHMENT_FORMAT", "none")
        if attachment_format == "none" and hasattr(
            Config, "EXTRACT_ATTACHMENT_FORMAT"
        ):
            attachment_format = Config.EXTRACT_ATTACHMENT_FORMAT
        attachment_format_str = (
            f"{attachment_format}"
            if attachment_format != "none"
            else "none (Default)"
        )

        attachment_index = user_dict.get("EXTRACT_ATTACHMENT_INDEX", None)
        if attachment_index is None and hasattr(Config, "EXTRACT_ATTACHMENT_INDEX"):
            attachment_index = Config.EXTRACT_ATTACHMENT_INDEX
        attachment_index_str = (
            f"{attachment_index}"
            if attachment_index is not None
            else "All (Default)"
        )

        # Get additional attachment settings
        attachment_filter = user_dict.get("EXTRACT_ATTACHMENT_FILTER", "none")
        if attachment_filter == "none" and hasattr(
            Config, "EXTRACT_ATTACHMENT_FILTER"
        ):
            attachment_filter = Config.EXTRACT_ATTACHMENT_FILTER
        attachment_filter_str = (
            f"{attachment_filter}"
            if attachment_filter != "none"
            else "none (Default)"
        )

        text = f"""<b>Attachment Extract Configuration</b>

<b>Basic Settings:</b>
┣ <b>Format:</b> {attachment_format_str}
┣ <b>Index:</b> {attachment_index_str}
┗ <b>Filter:</b> {attachment_filter_str}

<b>Help:</b>
• <b>Format:</b> Set the output format for attachments (e.g., original, zip)
• <b>Index:</b> Set specific attachment indices to extract (e.g., 0,1,2 or "all")
• <b>Filter:</b> Set a filter pattern for attachments (e.g., *.ttf, *.jpg)

<b>Tips:</b>
• Set index to a specific number or comma-separated list (e.g., 0,1,2)
• Leave index empty to extract all attachments
• Use filter to extract only specific file types (e.g., *.ttf for fonts)
• When set to 'none', settings won't be used in command generation"""

    elif stype == "add_config":
        # Add configuration menu
        # Video add settings
        video_enabled = user_dict.get("ADD_VIDEO_ENABLED", False)
        buttons.data_button(
            f"Video: {'✅ ON' if video_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_VIDEO_ENABLED {'f' if video_enabled else 't'}",
        )
        buttons.data_button(
            "Video Settings", f"mediatools {user_id} add_video_config"
        )

        # Audio add settings
        audio_enabled = user_dict.get("ADD_AUDIO_ENABLED", False)
        buttons.data_button(
            f"Audio: {'✅ ON' if audio_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_AUDIO_ENABLED {'f' if audio_enabled else 't'}",
        )
        buttons.data_button(
            "Audio Settings", f"mediatools {user_id} add_audio_config"
        )

        # Subtitle add settings
        subtitle_enabled = user_dict.get("ADD_SUBTITLE_ENABLED", False)
        buttons.data_button(
            f"Subtitle: {'✅ ON' if subtitle_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_SUBTITLE_ENABLED {'f' if subtitle_enabled else 't'}",
        )
        buttons.data_button(
            "Subtitle Settings", f"mediatools {user_id} add_subtitle_config"
        )

        # Attachment add settings
        attachment_enabled = user_dict.get("ADD_ATTACHMENT_ENABLED", False)
        buttons.data_button(
            f"Attachment: {'✅ ON' if attachment_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_ATTACHMENT_ENABLED {'f' if attachment_enabled else 't'}",
        )
        buttons.data_button(
            "Attachment Settings", f"mediatools {user_id} add_attachment_config"
        )

        # Delete original toggle
        delete_original = user_dict.get("ADD_DELETE_ORIGINAL", True)
        buttons.data_button(
            f"RO: {'✅ ON' if delete_original else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_DELETE_ORIGINAL {'f' if delete_original else 't'}",
        )

        buttons.data_button("Back", f"mediatools {user_id} add", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get delete original setting
        delete_original_str = "✅ Enabled" if delete_original else "❌ Disabled"

        # Get preserve tracks setting
        preserve_tracks_str = "✅ Enabled" if preserve_tracks else "❌ Disabled"

        # Get replace tracks setting
        replace_tracks_str = "✅ Enabled" if replace_tracks else "❌ Disabled"

        text = f"""<b>Add Configuration</b>

<b>Video Add:</b> {"✅ Enabled" if video_enabled else "❌ Disabled"}
<b>Audio Add:</b> {"✅ Enabled" if audio_enabled else "❌ Disabled"}
<b>Subtitle Add:</b> {"✅ Enabled" if subtitle_enabled else "❌ Disabled"}
<b>Attachment Add:</b> {"✅ Enabled" if attachment_enabled else "❌ Disabled"}

<b>General Settings:</b>
┠ <b>RO:</b> {delete_original_str}
┠ <b>Preserve Tracks:</b> {preserve_tracks_str}
┗ <b>Replace Tracks:</b> {replace_tracks_str}

<b>Help:</b>
• Click on a track type toggle to enable/disable adding for that type
• Click on a track type's "Settings" button to configure detailed options
• Set track indices to add at specific positions (e.g., 0,1,2)
• Use 'copy' codec to preserve original quality
• When set to 'none', settings won't be used in command generation
• RO: When enabled, original files are deleted after adding
• Preserve: When enabled, existing tracks are preserved when adding new ones
• Replace: When enabled, existing tracks are replaced with new ones at the same index"""

    elif stype == "add_video_config":
        # Video add configuration menu
        buttons.data_button("Codec", f"mediatools {user_id} menu ADD_VIDEO_CODEC")
        buttons.data_button("Index", f"mediatools {user_id} menu ADD_VIDEO_INDEX")
        buttons.data_button(
            "Quality", f"mediatools {user_id} menu ADD_VIDEO_QUALITY"
        )
        buttons.data_button("Preset", f"mediatools {user_id} menu ADD_VIDEO_PRESET")
        buttons.data_button(
            "Bitrate", f"mediatools {user_id} menu ADD_VIDEO_BITRATE"
        )
        buttons.data_button(
            "Resolution", f"mediatools {user_id} menu ADD_VIDEO_RESOLUTION"
        )
        buttons.data_button("FPS", f"mediatools {user_id} menu ADD_VIDEO_FPS")

        buttons.data_button("Back", f"mediatools {user_id} add_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get video add settings

        video_codec = user_dict.get("ADD_VIDEO_CODEC", "none")
        if video_codec == "none" and hasattr(Config, "ADD_VIDEO_CODEC"):
            video_codec = Config.ADD_VIDEO_CODEC
        video_codec_str = (
            f"{video_codec}" if video_codec != "none" else "copy (Default)"
        )

        video_index = user_dict.get("ADD_VIDEO_INDEX", None)
        if video_index is None and hasattr(Config, "ADD_VIDEO_INDEX"):
            video_index = Config.ADD_VIDEO_INDEX
        video_index_str = (
            f"{video_index}" if video_index is not None else "Append (Default)"
        )

        # Get additional video settings
        video_quality = user_dict.get("ADD_VIDEO_QUALITY", "none")
        if video_quality == "none" and hasattr(Config, "ADD_VIDEO_QUALITY"):
            video_quality = Config.ADD_VIDEO_QUALITY
        video_quality_str = (
            f"{video_quality}" if video_quality != "none" else "none (Default)"
        )

        video_preset = user_dict.get("ADD_VIDEO_PRESET", "none")
        if video_preset == "none" and hasattr(Config, "ADD_VIDEO_PRESET"):
            video_preset = Config.ADD_VIDEO_PRESET
        video_preset_str = (
            f"{video_preset}" if video_preset != "none" else "none (Default)"
        )

        video_bitrate = user_dict.get("ADD_VIDEO_BITRATE", "none")
        if video_bitrate == "none" and hasattr(Config, "ADD_VIDEO_BITRATE"):
            video_bitrate = Config.ADD_VIDEO_BITRATE
        video_bitrate_str = (
            f"{video_bitrate}" if video_bitrate != "none" else "none (Default)"
        )

        video_resolution = user_dict.get("ADD_VIDEO_RESOLUTION", "none")
        if video_resolution == "none" and hasattr(Config, "ADD_VIDEO_RESOLUTION"):
            video_resolution = Config.ADD_VIDEO_RESOLUTION
        video_resolution_str = (
            f"{video_resolution}" if video_resolution != "none" else "none (Default)"
        )

        video_fps = user_dict.get("ADD_VIDEO_FPS", "none")
        if video_fps == "none" and hasattr(Config, "ADD_VIDEO_FPS"):
            video_fps = Config.ADD_VIDEO_FPS
        video_fps_str = f"{video_fps}" if video_fps != "none" else "none (Default)"

        text = f"""<b>Video Add Configuration</b>

<b>Basic Settings:</b>
┣ <b>Codec:</b> {video_codec_str}
┗ <b>Index:</b> {video_index_str}

<b>Advanced Settings:</b>
┣ <b>Quality:</b> {video_quality_str}
┣ <b>Preset:</b> {video_preset_str}
┣ <b>Bitrate:</b> {video_bitrate_str}
┣ <b>Resolution:</b> {video_resolution_str}
┗ <b>FPS:</b> {video_fps_str}

<b>Help:</b>
• <b>Codec:</b> Set the video codec (e.g., copy, h264, h265)
• <b>Index:</b> Set the position to add the video track (e.g., 0, 1, 2)
• <b>Quality:</b> Set the quality/CRF value (lower is better quality)
• <b>Preset:</b> Set encoding preset (e.g., ultrafast, medium, veryslow)
• <b>Bitrate:</b> Set video bitrate (e.g., 5M, 10M)
• <b>Resolution:</b> Set video resolution (e.g., 1920x1080)
• <b>FPS:</b> Set video frame rate (e.g., 30, 60)

Use 'copy' codec to preserve original quality. When set to 'none', settings won't be used in command generation."""

    elif stype == "add_audio_config":
        # Audio add configuration menu
        buttons.data_button("Codec", f"mediatools {user_id} menu ADD_AUDIO_CODEC")
        buttons.data_button("Index", f"mediatools {user_id} menu ADD_AUDIO_INDEX")
        buttons.data_button(
            "Bitrate", f"mediatools {user_id} menu ADD_AUDIO_BITRATE"
        )
        buttons.data_button(
            "Channels", f"mediatools {user_id} menu ADD_AUDIO_CHANNELS"
        )
        buttons.data_button(
            "Sampling", f"mediatools {user_id} menu ADD_AUDIO_SAMPLING"
        )
        buttons.data_button("Volume", f"mediatools {user_id} menu ADD_AUDIO_VOLUME")

        buttons.data_button("Back", f"mediatools {user_id} add_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get audio add settings

        audio_codec = user_dict.get("ADD_AUDIO_CODEC", "none")
        if audio_codec == "none" and hasattr(Config, "ADD_AUDIO_CODEC"):
            audio_codec = Config.ADD_AUDIO_CODEC
        audio_codec_str = (
            f"{audio_codec}" if audio_codec != "none" else "copy (Default)"
        )

        audio_index = user_dict.get("ADD_AUDIO_INDEX", None)
        if audio_index is None and hasattr(Config, "ADD_AUDIO_INDEX"):
            audio_index = Config.ADD_AUDIO_INDEX
        audio_index_str = (
            f"{audio_index}" if audio_index is not None else "Append (Default)"
        )

        # Get additional audio settings
        audio_bitrate = user_dict.get("ADD_AUDIO_BITRATE", "none")
        if audio_bitrate == "none" and hasattr(Config, "ADD_AUDIO_BITRATE"):
            audio_bitrate = Config.ADD_AUDIO_BITRATE
        audio_bitrate_str = (
            f"{audio_bitrate}" if audio_bitrate != "none" else "none (Default)"
        )

        audio_channels = user_dict.get("ADD_AUDIO_CHANNELS", "none")
        if audio_channels == "none" and hasattr(Config, "ADD_AUDIO_CHANNELS"):
            audio_channels = Config.ADD_AUDIO_CHANNELS
        audio_channels_str = (
            f"{audio_channels}" if audio_channels != "none" else "none (Default)"
        )

        audio_sampling = user_dict.get("ADD_AUDIO_SAMPLING", "none")
        if audio_sampling == "none" and hasattr(Config, "ADD_AUDIO_SAMPLING"):
            audio_sampling = Config.ADD_AUDIO_SAMPLING
        audio_sampling_str = (
            f"{audio_sampling}" if audio_sampling != "none" else "none (Default)"
        )

        audio_volume = user_dict.get("ADD_AUDIO_VOLUME", "none")
        if audio_volume == "none" and hasattr(Config, "ADD_AUDIO_VOLUME"):
            audio_volume = Config.ADD_AUDIO_VOLUME
        audio_volume_str = (
            f"{audio_volume}" if audio_volume != "none" else "none (Default)"
        )

        text = f"""<b>Audio Add Configuration</b>

<b>Basic Settings:</b>
┣ <b>Codec:</b> {audio_codec_str}
┗ <b>Index:</b> {audio_index_str}

<b>Advanced Settings:</b>
┣ <b>Bitrate:</b> {audio_bitrate_str}
┣ <b>Channels:</b> {audio_channels_str}
┣ <b>Sampling:</b> {audio_sampling_str}
┗ <b>Volume:</b> {audio_volume_str}

<b>Help:</b>
• <b>Codec:</b> Set the audio codec (e.g., copy, aac, mp3, opus)
• <b>Index:</b> Set the position to add the audio track (e.g., 0, 1, 2)
• <b>Bitrate:</b> Set audio bitrate (e.g., 128k, 192k, 320k)
• <b>Channels:</b> Set number of audio channels (e.g., 1 for mono, 2 for stereo)
• <b>Sampling:</b> Set audio sampling rate (e.g., 44100, 48000)
• <b>Volume:</b> Set volume adjustment (e.g., 1.0 normal, 1.5 louder)

Use 'copy' codec to preserve original quality. When set to 'none', settings won't be used in command generation."""

    elif stype == "add_subtitle_config":
        # Subtitle add configuration menu
        buttons.data_button("Codec", f"mediatools {user_id} menu ADD_SUBTITLE_CODEC")
        buttons.data_button("Index", f"mediatools {user_id} menu ADD_SUBTITLE_INDEX")
        buttons.data_button(
            "Language", f"mediatools {user_id} menu ADD_SUBTITLE_LANGUAGE"
        )
        buttons.data_button(
            "Encoding", f"mediatools {user_id} menu ADD_SUBTITLE_ENCODING"
        )
        buttons.data_button("Font", f"mediatools {user_id} menu ADD_SUBTITLE_FONT")
        buttons.data_button(
            "Font Size", f"mediatools {user_id} menu ADD_SUBTITLE_FONT_SIZE"
        )

        # Hardsub toggle
        hardsub_enabled = user_dict.get("ADD_SUBTITLE_HARDSUB_ENABLED", False)
        buttons.data_button(
            f"Hardsub: {'✅ ON' if hardsub_enabled else '❌ OFF'}",
            f"mediatools {user_id} tog ADD_SUBTITLE_HARDSUB_ENABLED {'f' if hardsub_enabled else 't'}",
        )

        buttons.data_button("Back", f"mediatools {user_id} add_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get subtitle add settings

        subtitle_codec = user_dict.get("ADD_SUBTITLE_CODEC", "none")
        if subtitle_codec == "none" and hasattr(Config, "ADD_SUBTITLE_CODEC"):
            subtitle_codec = Config.ADD_SUBTITLE_CODEC
        subtitle_codec_str = (
            f"{subtitle_codec}" if subtitle_codec != "none" else "copy (Default)"
        )

        subtitle_index = user_dict.get("ADD_SUBTITLE_INDEX", None)
        if subtitle_index is None and hasattr(Config, "ADD_SUBTITLE_INDEX"):
            subtitle_index = Config.ADD_SUBTITLE_INDEX
        subtitle_index_str = (
            f"{subtitle_index}" if subtitle_index is not None else "Append (Default)"
        )

        # Get additional subtitle settings
        subtitle_language = user_dict.get("ADD_SUBTITLE_LANGUAGE", "none")
        if subtitle_language == "none" and hasattr(Config, "ADD_SUBTITLE_LANGUAGE"):
            subtitle_language = Config.ADD_SUBTITLE_LANGUAGE
        subtitle_language_str = (
            f"{subtitle_language}"
            if subtitle_language != "none"
            else "none (Default)"
        )

        subtitle_encoding = user_dict.get("ADD_SUBTITLE_ENCODING", "none")
        if subtitle_encoding == "none" and hasattr(Config, "ADD_SUBTITLE_ENCODING"):
            subtitle_encoding = Config.ADD_SUBTITLE_ENCODING
        subtitle_encoding_str = (
            f"{subtitle_encoding}"
            if subtitle_encoding != "none"
            else "none (Default)"
        )

        subtitle_font = user_dict.get("ADD_SUBTITLE_FONT", "none")
        if subtitle_font == "none" and hasattr(Config, "ADD_SUBTITLE_FONT"):
            subtitle_font = Config.ADD_SUBTITLE_FONT
        subtitle_font_str = (
            f"{subtitle_font}" if subtitle_font != "none" else "none (Default)"
        )

        subtitle_font_size = user_dict.get("ADD_SUBTITLE_FONT_SIZE", "none")
        if subtitle_font_size == "none" and hasattr(
            Config, "ADD_SUBTITLE_FONT_SIZE"
        ):
            subtitle_font_size = Config.ADD_SUBTITLE_FONT_SIZE
        subtitle_font_size_str = (
            f"{subtitle_font_size}"
            if subtitle_font_size != "none"
            else "none (Default)"
        )

        # Get hardsub setting
        hardsub_enabled = user_dict.get("ADD_SUBTITLE_HARDSUB_ENABLED", False)
        hardsub_str = "✅ Enabled" if hardsub_enabled else "❌ Disabled"

        text = f"""<b>Subtitle Add Configuration</b>

<b>Basic Settings:</b>
┣ <b>Codec:</b> {subtitle_codec_str}
┣ <b>Index:</b> {subtitle_index_str}
┗ <b>Hardsub:</b> {hardsub_str}

<b>Advanced Settings:</b>
┣ <b>Language:</b> {subtitle_language_str}
┣ <b>Encoding:</b> {subtitle_encoding_str}
┣ <b>Font:</b> {subtitle_font_str}
┗ <b>Font Size:</b> {subtitle_font_size_str}

<b>Help:</b>
• <b>Codec:</b> Set the subtitle codec (e.g., copy, srt, ass, vtt)
• <b>Index:</b> Set the position to add the subtitle track (e.g., 0, 1, 2)
• <b>Hardsub:</b> Burn subtitles into video (permanent) vs soft subtitles (separate track)
• <b>Language:</b> Set subtitle language code (e.g., eng, spa, fre)
• <b>Encoding:</b> Set character encoding (e.g., UTF-8, latin1)
• <b>Font:</b> Set font for ASS/SSA subtitles (e.g., Arial)
• <b>Font Size:</b> Set font size for ASS/SSA subtitles (e.g., 24)

Use 'copy' codec to preserve original format or 'srt' to convert ASS/SSA to SRT. When set to 'none', settings won't be used in command generation."""

    elif stype == "add_attachment_config":
        # Attachment add configuration menu
        buttons.data_button(
            "Index", f"mediatools {user_id} menu ADD_ATTACHMENT_INDEX"
        )
        buttons.data_button(
            "Mimetype", f"mediatools {user_id} menu ADD_ATTACHMENT_MIMETYPE"
        )

        buttons.data_button("Back", f"mediatools {user_id} add_config", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get attachment add settings

        attachment_index = user_dict.get("ADD_ATTACHMENT_INDEX", None)
        if attachment_index is None and hasattr(Config, "ADD_ATTACHMENT_INDEX"):
            attachment_index = Config.ADD_ATTACHMENT_INDEX
        attachment_index_str = (
            f"{attachment_index}"
            if attachment_index is not None
            else "Append (Default)"
        )

        # Get additional attachment settings
        attachment_mimetype = user_dict.get("ADD_ATTACHMENT_MIMETYPE", "none")
        if attachment_mimetype == "none" and hasattr(
            Config, "ADD_ATTACHMENT_MIMETYPE"
        ):
            attachment_mimetype = Config.ADD_ATTACHMENT_MIMETYPE
        attachment_mimetype_str = (
            f"{attachment_mimetype}"
            if attachment_mimetype != "none"
            else "Auto-detect (Default)"
        )

        text = f"""<b>Attachment Add Configuration</b>

<b>Basic Settings:</b>
┣ <b>Index:</b> {attachment_index_str}
┗ <b>Mimetype:</b> {attachment_mimetype_str}

<b>Help:</b>
• <b>Index:</b> Set the position to add the attachment (e.g., 0, 1, 2)
• <b>Mimetype:</b> Set the MIME type for the attachment (e.g., image/jpeg, font/ttf)

<b>Tips:</b>
• Set index to a specific number to insert at that position
• Leave index empty to append to the end
• Common MIME types: image/jpeg, image/png, font/ttf, application/x-truetype-font
• When set to 'none', MIME type will be auto-detected"""

    elif stype == "convert_audio":
        # Audio Convert settings menu
        # Add toggle for audio convert enabled
        audio_convert_enabled = user_dict.get("CONVERT_AUDIO_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if audio_convert_enabled else "❌ Disabled",
            f"mediatools {user_id} tog CONVERT_AUDIO_ENABLED {'f' if audio_convert_enabled else 't'}",
        )

        buttons.data_button(
            "Set Format", f"mediatools {user_id} menu CONVERT_AUDIO_FORMAT"
        )
        buttons.data_button(
            "Set Codec", f"mediatools {user_id} menu CONVERT_AUDIO_CODEC"
        )
        buttons.data_button(
            "Set Bitrate", f"mediatools {user_id} menu CONVERT_AUDIO_BITRATE"
        )
        buttons.data_button(
            "Set Channels", f"mediatools {user_id} menu CONVERT_AUDIO_CHANNELS"
        )
        buttons.data_button(
            "Set Sampling", f"mediatools {user_id} menu CONVERT_AUDIO_SAMPLING"
        )
        buttons.data_button(
            "Set Volume", f"mediatools {user_id} menu CONVERT_AUDIO_VOLUME"
        )

        buttons.data_button("Back", f"mediatools {user_id} convert", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get audio convert settings
        user_has_format = (
            "CONVERT_AUDIO_FORMAT" in user_dict
            and user_dict["CONVERT_AUDIO_FORMAT"]
            and user_dict["CONVERT_AUDIO_FORMAT"].lower() != "none"
        )
        owner_has_format = (
            hasattr(Config, "CONVERT_AUDIO_FORMAT")
            and Config.CONVERT_AUDIO_FORMAT
            and Config.CONVERT_AUDIO_FORMAT.lower() != "none"
        )

        if user_has_format:
            audio_format = f"{user_dict['CONVERT_AUDIO_FORMAT']} (User)"
        elif owner_has_format:
            audio_format = f"{Config.CONVERT_AUDIO_FORMAT} (Global)"
        else:
            audio_format = "none (Default)"

        # Get audio codec
        user_has_codec = (
            "CONVERT_AUDIO_CODEC" in user_dict
            and user_dict["CONVERT_AUDIO_CODEC"]
            and user_dict["CONVERT_AUDIO_CODEC"].lower() != "none"
        )
        owner_has_codec = (
            hasattr(Config, "CONVERT_AUDIO_CODEC")
            and Config.CONVERT_AUDIO_CODEC
            and Config.CONVERT_AUDIO_CODEC.lower() != "none"
        )

        if user_has_codec:
            audio_codec = f"{user_dict['CONVERT_AUDIO_CODEC']} (User)"
        elif owner_has_codec:
            audio_codec = f"{Config.CONVERT_AUDIO_CODEC} (Global)"
        else:
            audio_codec = "none (Default)"

        # Get audio bitrate
        user_has_bitrate = (
            "CONVERT_AUDIO_BITRATE" in user_dict
            and user_dict["CONVERT_AUDIO_BITRATE"]
            and user_dict["CONVERT_AUDIO_BITRATE"].lower() != "none"
        )
        owner_has_bitrate = (
            hasattr(Config, "CONVERT_AUDIO_BITRATE")
            and Config.CONVERT_AUDIO_BITRATE
            and Config.CONVERT_AUDIO_BITRATE.lower() != "none"
        )

        if user_has_bitrate:
            audio_bitrate = f"{user_dict['CONVERT_AUDIO_BITRATE']} (User)"
        elif owner_has_bitrate:
            audio_bitrate = f"{Config.CONVERT_AUDIO_BITRATE} (Global)"
        else:
            audio_bitrate = "none (Default)"

        # Get audio channels
        user_has_channels = (
            "CONVERT_AUDIO_CHANNELS" in user_dict
            and user_dict["CONVERT_AUDIO_CHANNELS"]
            and user_dict["CONVERT_AUDIO_CHANNELS"] != 0
        )
        owner_has_channels = (
            hasattr(Config, "CONVERT_AUDIO_CHANNELS")
            and Config.CONVERT_AUDIO_CHANNELS
            and Config.CONVERT_AUDIO_CHANNELS != 0
        )

        if user_has_channels:
            audio_channels = f"{user_dict['CONVERT_AUDIO_CHANNELS']} (User)"
        elif owner_has_channels:
            audio_channels = f"{Config.CONVERT_AUDIO_CHANNELS} (Global)"
        else:
            audio_channels = "0 (Default)"

        # Get audio sampling
        user_has_sampling = (
            "CONVERT_AUDIO_SAMPLING" in user_dict
            and user_dict["CONVERT_AUDIO_SAMPLING"]
            and user_dict["CONVERT_AUDIO_SAMPLING"] != 0
        )
        owner_has_sampling = (
            hasattr(Config, "CONVERT_AUDIO_SAMPLING")
            and Config.CONVERT_AUDIO_SAMPLING
            and Config.CONVERT_AUDIO_SAMPLING != 0
        )

        if user_has_sampling:
            audio_sampling = f"{user_dict['CONVERT_AUDIO_SAMPLING']} (User)"
        elif owner_has_sampling:
            audio_sampling = f"{Config.CONVERT_AUDIO_SAMPLING} (Global)"
        else:
            audio_sampling = "0 (Default)"

        # Get audio volume
        user_has_volume = (
            "CONVERT_AUDIO_VOLUME" in user_dict
            and user_dict["CONVERT_AUDIO_VOLUME"]
            and user_dict["CONVERT_AUDIO_VOLUME"] != 0.0
        )
        owner_has_volume = (
            hasattr(Config, "CONVERT_AUDIO_VOLUME")
            and Config.CONVERT_AUDIO_VOLUME
            and Config.CONVERT_AUDIO_VOLUME != 0.0
        )

        if user_has_volume:
            audio_volume = f"{user_dict['CONVERT_AUDIO_VOLUME']} (User)"
        elif owner_has_volume:
            audio_volume = f"{Config.CONVERT_AUDIO_VOLUME} (Global)"
        else:
            audio_volume = "0.0 (Default)"

        # Get audio convert enabled status
        audio_convert_enabled = user_dict.get("CONVERT_AUDIO_ENABLED", False)
        owner_audio_enabled = (
            hasattr(Config, "CONVERT_AUDIO_ENABLED") and Config.CONVERT_AUDIO_ENABLED
        )

        if "CONVERT_AUDIO_ENABLED" in user_dict:
            if audio_convert_enabled:
                audio_enabled_status = "✅ Enabled (User)"
            else:
                audio_enabled_status = "❌ Disabled (User)"
        elif owner_audio_enabled:
            audio_enabled_status = "✅ Enabled (Global)"
        else:
            audio_enabled_status = "❌ Disabled"

        text = f"""⌬ <b>Audio Convert Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {audio_enabled_status}
┠ <b>Format</b> → <code>{audio_format}</code>
┠ <b>Codec</b> → <code>{audio_codec}</code>
┠ <b>Bitrate</b> → <code>{audio_bitrate}</code>
┠ <b>Channels</b> → <code>{audio_channels}</code>
┠ <b>Sampling</b> → <code>{audio_sampling}</code>
┖ <b>Volume</b> → <code>{audio_volume}</code>"""

    elif stype == "convert_subtitle":
        # Subtitle Convert settings menu
        # Add toggle for subtitle convert enabled
        subtitle_convert_enabled = user_dict.get("CONVERT_SUBTITLE_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if subtitle_convert_enabled else "❌ Disabled",
            f"mediatools {user_id} tog CONVERT_SUBTITLE_ENABLED {'f' if subtitle_convert_enabled else 't'}",
        )

        buttons.data_button(
            "Set Format", f"mediatools {user_id} menu CONVERT_SUBTITLE_FORMAT"
        )
        buttons.data_button(
            "Set Encoding", f"mediatools {user_id} menu CONVERT_SUBTITLE_ENCODING"
        )
        buttons.data_button(
            "Set Language", f"mediatools {user_id} menu CONVERT_SUBTITLE_LANGUAGE"
        )

        buttons.data_button("Back", f"mediatools {user_id} convert", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get subtitle convert settings
        user_has_format = (
            "CONVERT_SUBTITLE_FORMAT" in user_dict
            and user_dict["CONVERT_SUBTITLE_FORMAT"]
            and user_dict["CONVERT_SUBTITLE_FORMAT"].lower() != "none"
        )
        owner_has_format = (
            hasattr(Config, "CONVERT_SUBTITLE_FORMAT")
            and Config.CONVERT_SUBTITLE_FORMAT
            and Config.CONVERT_SUBTITLE_FORMAT.lower() != "none"
        )

        if user_has_format:
            subtitle_format = f"{user_dict['CONVERT_SUBTITLE_FORMAT']} (User)"
        elif owner_has_format:
            subtitle_format = f"{Config.CONVERT_SUBTITLE_FORMAT} (Global)"
        else:
            subtitle_format = "none (Default)"

        # Get subtitle encoding
        user_has_encoding = (
            "CONVERT_SUBTITLE_ENCODING" in user_dict
            and user_dict["CONVERT_SUBTITLE_ENCODING"]
            and user_dict["CONVERT_SUBTITLE_ENCODING"].lower() != "none"
        )
        owner_has_encoding = (
            hasattr(Config, "CONVERT_SUBTITLE_ENCODING")
            and Config.CONVERT_SUBTITLE_ENCODING
            and Config.CONVERT_SUBTITLE_ENCODING.lower() != "none"
        )

        if user_has_encoding:
            subtitle_encoding = f"{user_dict['CONVERT_SUBTITLE_ENCODING']} (User)"
        elif owner_has_encoding:
            subtitle_encoding = f"{Config.CONVERT_SUBTITLE_ENCODING} (Global)"
        else:
            subtitle_encoding = "none (Default)"

        # Get subtitle language
        user_has_language = (
            "CONVERT_SUBTITLE_LANGUAGE" in user_dict
            and user_dict["CONVERT_SUBTITLE_LANGUAGE"]
            and user_dict["CONVERT_SUBTITLE_LANGUAGE"].lower() != "none"
        )
        owner_has_language = (
            hasattr(Config, "CONVERT_SUBTITLE_LANGUAGE")
            and Config.CONVERT_SUBTITLE_LANGUAGE
            and Config.CONVERT_SUBTITLE_LANGUAGE.lower() != "none"
        )

        if user_has_language:
            subtitle_language = f"{user_dict['CONVERT_SUBTITLE_LANGUAGE']} (User)"
        elif owner_has_language:
            subtitle_language = f"{Config.CONVERT_SUBTITLE_LANGUAGE} (Global)"
        else:
            subtitle_language = "none (Default)"

        # Get subtitle convert enabled status
        subtitle_convert_enabled = user_dict.get("CONVERT_SUBTITLE_ENABLED", False)
        owner_subtitle_enabled = (
            hasattr(Config, "CONVERT_SUBTITLE_ENABLED")
            and Config.CONVERT_SUBTITLE_ENABLED
        )

        if "CONVERT_SUBTITLE_ENABLED" in user_dict:
            if subtitle_convert_enabled:
                subtitle_enabled_status = "✅ Enabled (User)"
            else:
                subtitle_enabled_status = "❌ Disabled (User)"
        elif owner_subtitle_enabled:
            subtitle_enabled_status = "✅ Enabled (Global)"
        else:
            subtitle_enabled_status = "❌ Disabled"

        text = f"""⌬ <b>Subtitle Convert Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {subtitle_enabled_status}
┠ <b>Format</b> → <code>{subtitle_format}</code>
┠ <b>Encoding</b> → <code>{subtitle_encoding}</code>
┖ <b>Language</b> → <code>{subtitle_language}</code>"""

    elif stype == "convert_document":
        # Document Convert settings menu
        # Add toggle for document convert enabled
        document_convert_enabled = user_dict.get("CONVERT_DOCUMENT_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if document_convert_enabled else "❌ Disabled",
            f"mediatools {user_id} tog CONVERT_DOCUMENT_ENABLED {'f' if document_convert_enabled else 't'}",
        )

        buttons.data_button(
            "Set Format", f"mediatools {user_id} menu CONVERT_DOCUMENT_FORMAT"
        )
        buttons.data_button(
            "Set Quality", f"mediatools {user_id} menu CONVERT_DOCUMENT_QUALITY"
        )
        buttons.data_button(
            "Set DPI", f"mediatools {user_id} menu CONVERT_DOCUMENT_DPI"
        )

        buttons.data_button("Back", f"mediatools {user_id} convert", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get document convert settings
        user_has_format = (
            "CONVERT_DOCUMENT_FORMAT" in user_dict
            and user_dict["CONVERT_DOCUMENT_FORMAT"]
            and user_dict["CONVERT_DOCUMENT_FORMAT"].lower() != "none"
        )
        owner_has_format = (
            hasattr(Config, "CONVERT_DOCUMENT_FORMAT")
            and Config.CONVERT_DOCUMENT_FORMAT
            and Config.CONVERT_DOCUMENT_FORMAT.lower() != "none"
        )

        if user_has_format:
            document_format = f"{user_dict['CONVERT_DOCUMENT_FORMAT']} (User)"
        elif owner_has_format:
            document_format = f"{Config.CONVERT_DOCUMENT_FORMAT} (Global)"
        else:
            document_format = "none (Default)"

        # Get document quality
        user_has_quality = (
            "CONVERT_DOCUMENT_QUALITY" in user_dict
            and user_dict["CONVERT_DOCUMENT_QUALITY"]
            and user_dict["CONVERT_DOCUMENT_QUALITY"] != 0
        )
        owner_has_quality = (
            hasattr(Config, "CONVERT_DOCUMENT_QUALITY")
            and Config.CONVERT_DOCUMENT_QUALITY
            and Config.CONVERT_DOCUMENT_QUALITY != 0
        )

        if user_has_quality:
            document_quality = f"{user_dict['CONVERT_DOCUMENT_QUALITY']} (User)"
        elif owner_has_quality:
            document_quality = f"{Config.CONVERT_DOCUMENT_QUALITY} (Global)"
        else:
            document_quality = "none (Default)"

        # Get document DPI
        user_has_dpi = (
            "CONVERT_DOCUMENT_DPI" in user_dict
            and user_dict["CONVERT_DOCUMENT_DPI"]
            and user_dict["CONVERT_DOCUMENT_DPI"] != 0
        )
        owner_has_dpi = (
            hasattr(Config, "CONVERT_DOCUMENT_DPI")
            and Config.CONVERT_DOCUMENT_DPI
            and Config.CONVERT_DOCUMENT_DPI != 0
        )

        if user_has_dpi:
            document_dpi = f"{user_dict['CONVERT_DOCUMENT_DPI']} (User)"
        elif owner_has_dpi:
            document_dpi = f"{Config.CONVERT_DOCUMENT_DPI} (Global)"
        else:
            document_dpi = "none (Default)"

        # Get document convert enabled status
        document_convert_enabled = user_dict.get("CONVERT_DOCUMENT_ENABLED", False)
        owner_document_enabled = (
            hasattr(Config, "CONVERT_DOCUMENT_ENABLED")
            and Config.CONVERT_DOCUMENT_ENABLED
        )

        if "CONVERT_DOCUMENT_ENABLED" in user_dict:
            if document_convert_enabled:
                document_enabled_status = "✅ Enabled (User)"
            else:
                document_enabled_status = "❌ Disabled (User)"
        elif owner_document_enabled:
            document_enabled_status = "✅ Enabled (Global)"
        else:
            document_enabled_status = "❌ Disabled"

        text = f"""⌬ <b>Document Convert Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {document_enabled_status}
┠ <b>Format</b> → <code>{document_format}</code>
┠ <b>Quality</b> → <code>{document_quality}</code>
┖ <b>DPI</b> → <code>{document_dpi}</code>"""

    elif stype == "convert_archive":
        # Archive Convert settings menu
        # Add toggle for archive convert enabled
        archive_convert_enabled = user_dict.get("CONVERT_ARCHIVE_ENABLED", False)
        buttons.data_button(
            "✅ Enabled" if archive_convert_enabled else "❌ Disabled",
            f"mediatools {user_id} tog CONVERT_ARCHIVE_ENABLED {'f' if archive_convert_enabled else 't'}",
        )

        buttons.data_button(
            "Set Format", f"mediatools {user_id} menu CONVERT_ARCHIVE_FORMAT"
        )
        buttons.data_button(
            "Set Level", f"mediatools {user_id} menu CONVERT_ARCHIVE_LEVEL"
        )
        buttons.data_button(
            "Set Method", f"mediatools {user_id} menu CONVERT_ARCHIVE_METHOD"
        )

        buttons.data_button("Back", f"mediatools {user_id} convert", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        # Get archive convert settings
        user_has_format = (
            "CONVERT_ARCHIVE_FORMAT" in user_dict
            and user_dict["CONVERT_ARCHIVE_FORMAT"]
            and user_dict["CONVERT_ARCHIVE_FORMAT"].lower() != "none"
        )
        owner_has_format = (
            hasattr(Config, "CONVERT_ARCHIVE_FORMAT")
            and Config.CONVERT_ARCHIVE_FORMAT
            and Config.CONVERT_ARCHIVE_FORMAT.lower() != "none"
        )

        if user_has_format:
            archive_format = f"{user_dict['CONVERT_ARCHIVE_FORMAT']} (User)"
        elif owner_has_format:
            archive_format = f"{Config.CONVERT_ARCHIVE_FORMAT} (Global)"
        else:
            archive_format = "none (Default)"

        # Get archive level
        user_has_level = (
            "CONVERT_ARCHIVE_LEVEL" in user_dict
            and user_dict["CONVERT_ARCHIVE_LEVEL"]
            and user_dict["CONVERT_ARCHIVE_LEVEL"] != 0
        )
        owner_has_level = (
            hasattr(Config, "CONVERT_ARCHIVE_LEVEL")
            and Config.CONVERT_ARCHIVE_LEVEL
            and Config.CONVERT_ARCHIVE_LEVEL != 0
        )

        if user_has_level:
            archive_level = f"{user_dict['CONVERT_ARCHIVE_LEVEL']} (User)"
        elif owner_has_level:
            archive_level = f"{Config.CONVERT_ARCHIVE_LEVEL} (Global)"
        else:
            archive_level = "none (Default)"

        # Get archive method
        user_has_method = (
            "CONVERT_ARCHIVE_METHOD" in user_dict
            and user_dict["CONVERT_ARCHIVE_METHOD"]
            and user_dict["CONVERT_ARCHIVE_METHOD"].lower() != "none"
        )
        owner_has_method = (
            hasattr(Config, "CONVERT_ARCHIVE_METHOD")
            and Config.CONVERT_ARCHIVE_METHOD
            and Config.CONVERT_ARCHIVE_METHOD.lower() != "none"
        )

        if user_has_method:
            archive_method = f"{user_dict['CONVERT_ARCHIVE_METHOD']} (User)"
        elif owner_has_method:
            archive_method = f"{Config.CONVERT_ARCHIVE_METHOD} (Global)"
        else:
            archive_method = "none (Default)"

        # Get archive convert enabled status
        archive_convert_enabled = user_dict.get("CONVERT_ARCHIVE_ENABLED", False)
        owner_archive_enabled = (
            hasattr(Config, "CONVERT_ARCHIVE_ENABLED")
            and Config.CONVERT_ARCHIVE_ENABLED
        )

        if "CONVERT_ARCHIVE_ENABLED" in user_dict:
            if archive_convert_enabled:
                archive_enabled_status = "✅ Enabled (User)"
            else:
                archive_enabled_status = "❌ Disabled (User)"
        elif owner_archive_enabled:
            archive_enabled_status = "✅ Enabled (Global)"
        else:
            archive_enabled_status = "❌ Disabled"

        text = f"""⌬ <b>Archive Convert Settings :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Status</b> → {archive_enabled_status}
┠ <b>Format</b> → <code>{archive_format}</code>
┠ <b>Level</b> → <code>{archive_level}</code>
┖ <b>Method</b> → <code>{archive_method}</code>"""

    # Removed duplicate sections

    elif stype == "help_examples":
        # Usage Examples
        buttons.data_button("Back to Help", f"mediatools {user_id} help", "footer")
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")
        btns = buttons.build_menu(2)

        text = f"""⌬ <b>Media Tools Usage Examples :</b>
┟ <b>Name</b> → {user_name}
┃
┠ <b>Basic Usage:</b>
┃ • <code>-mt</code> - Configure settings before download
┃ • <code>-del</code> - Delete original files after processing

<blockquote expandable="expandable"><b>Watermark Examples:</b>
• <code>/mirror link -watermark "© My Channel"</code> - Text watermark
• <code>/leech link -iwm /path/to/logo.png</code> - Image watermark
• <code>/mirror link -watermark "© My Channel" -iwm /path/to/logo.png</code> - Both</blockquote>

<blockquote expandable="expandable"><b>Merge Examples:</b>
• <code>/leech link -merge-video</code> - Merge videos
• <code>/mirror link -merge-audio</code> - Merge audio files
• <code>/mirror link -merge-image</code> - Create image collage
• <code>/leech link -merge-pdf</code> - Merge PDFs
• <code>/mirror link -merge-all</code> - Merge all supported types</blockquote>

<blockquote expandable="expandable"><b>Trim Examples:</b>
• <code>/leech link -trim "00:01:30-00:02:45"</code> - Extract video portion
• <code>/mirror link -trim "00:01:30-00:02:45" -del</code> - With RO
• <code>/leech link -trim "-00:05:00"</code> - From start to 5 minutes
• <code>/mirror link -trim "00:10:00-"</code> - From 10 minutes to end
• <code>/leech document.pdf -trim "5-10"</code> - Extract pages 5 to 10
• <code>/mirror document.pdf -trim "3-"</code> - From page 3 to end
• <code>/leech document.pdf -trim "1-5" -del</code> - Pages 1-5 with RO</blockquote>

<blockquote expandable="expandable"><b>Convert Examples:</b>
• <code>/leech link -cv mp4</code> - Convert video to MP4
• <code>/mirror link -ca mp3</code> - Convert audio to MP3
• <code>/leech link -cs srt</code> - Convert subtitle to SRT
• <code>/mirror link -cd pdf</code> - Convert document to PDF
• <code>/leech link -cr zip</code> - Convert archive to ZIP
• <code>/leech link -cv mp4 -del</code> - Convert with RO
• <code>/leech link.zip -cv mkv</code> - Batch convert videos</blockquote>

<blockquote expandable="expandable"><b>Combined Examples:</b>
• <code>/leech link -trim "00:01:30-00:02:45" -cv mp4</code> - Trim + Convert
• <code>/leech link -watermark "© My Channel" -cv mp4</code> - Watermark + Convert
• <code>/mirror link.zip -cv mp4 -merge-video</code> - Convert + Merge
• <code>/leech link.zip -watermark "© 2025" -merge-video</code> - Watermark + Merge
• <code>/leech document.pdf -trim "5-10" -cd docx</code> - Trim pages + Convert
• <code>/mirror documents.zip -trim "1-3" -merge-pdf</code> - Trim + Merge PDFs
• <code>/mirror -i 3 -m merge-folder -merge-video</code> - Multi-link + Merge
• <code>/leech -b -m merge-folder -merge-audio</code> - Bulk download + Merge</blockquote>

<blockquote expandable="expandable"><b>Advanced Examples:</b>
• <code>/leech link.zip -watermark "© My Channel" -cv mp4 -merge-video</code>
  Apply text watermark, convert to MP4, merge videos
• <code>/leech link.zip -iwm /path/to/logo.png -cv mp4 -merge-video</code>
  Apply image watermark, convert to MP4, merge videos
• <code>/leech link.zip -watermark "Text" -iwm /path/to/logo.png -cv mp4 -merge-video</code>
  Apply both watermarks, convert to MP4, merge videos</blockquote>

<blockquote expandable="expandable"><b>Add Examples:</b>
• <code>/leech link -add</code> - Add tracks to media
• <code>/mirror link -add-video</code> - Add video track
• <code>/leech link -add-audio</code> - Add audio track
• <code>/mirror link -add-subtitle</code> - Add subtitle track
• <code>/leech link -add-attachment</code> - Add attachment
• <code>/leech link -add -m folder_name</code> - Multi-input mode
• <code>/mirror link -add-video-index 0</code> - Add at specific index
• <code>/leech link -add -m folder_name -add-video-index 0</code> - Multi-input with index</blockquote>

<blockquote expandable="expandable"><b>Priority System:</b>
Default priorities determine processing order:
• Merge (priority 1) runs first
• Convert (priority 3) runs second
• Watermark (priority 2) runs third
• Trim (priority 4) runs fourth
• Compression (priority 5) runs fifth
• Extract (priority 6) runs sixth
• Add (priority 7) runs last
Result: Operations run in order of priority (lower numbers first)</blockquote>

┖ <b>Note:</b> Use Media Tools settings to configure all options."""

    # Make sure btns is defined before returning
    if btns is None:
        btns = buttons.build_menu(2)
    return text, btns


async def update_media_tools_settings(query, stype="main"):
    """Update media tools settings UI."""
    user_id = query.from_user.id
    handler_dict[user_id] = False

    # Extract page number if present in stype
    page_no = 0
    global merge_config_page
    global watermark_config_page

    # Process stype and extract page number if needed
    if stype.startswith("merge_config "):
        try:
            # Format: merge_config X
            page_no = int(stype.split(" ")[1])
            # Update the global variable
            merge_config_page = page_no
            stype = "merge_config"
        except (ValueError, IndexError):
            # Use the global variable
            page_no = merge_config_page
    elif stype == "merge_config":
        # Use the global variable for merge_config
        page_no = merge_config_page
    elif stype.startswith("watermark_config "):
        try:
            # Format: watermark_config X
            page_no = int(stype.split(" ")[1])
            # Update the global variable
            watermark_config_page = page_no
            # Also store it in handler_dict for consistency
            handler_dict[f"{user_id}_watermark_page"] = page_no
            stype = "watermark_config"
        except (ValueError, IndexError):
            # Use the global variable
            page_no = watermark_config_page
    elif stype == "watermark_config":
        # Use the global variable for watermark_config
        page_no = watermark_config_page

    # Get the settings for the current stype
    msg, btns = await get_media_tools_settings(
        query.from_user, stype, page_no=page_no
    )

    # Store the page number in handler_dict for watermark_config
    if stype == "watermark_config":
        handler_dict[f"{query.from_user.id}_watermark_page"] = page_no

    # Check if we're in a task context (using -mt flag)
    is_task_context = user_id in task_context_users

    # If we're in a task context, we need to preserve the Done and Cancel buttons
    if is_task_context:
        # Create new buttons with the original menu buttons
        buttons = ButtonMaker()

        # Copy all buttons from the new menu except Close
        for row in btns.inline_keyboard:
            for btn in row:
                if btn.text == "Close":
                    continue  # Skip the Close button
                if "footer" in btn.callback_data:
                    buttons.data_button(btn.text, btn.callback_data, "footer")
                else:
                    buttons.data_button(btn.text, btn.callback_data)

        # Add the Done and Cancel buttons to the footer
        buttons.data_button("✅ Done", f"mediatools {user_id} task_done", "footer")
        buttons.data_button(
            "❌ Cancel", f"mediatools {user_id} task_cancel", "footer"
        )

        # Use the modified buttons
        button = buttons.build_menu(2)
    else:
        # Use the original buttons
        button = btns

    # Update the message with the new settings
    await edit_message(query.message, msg, button)


# This function is already defined at the top of the file
# def update_user_ldata(user_id, key, value):
#     """Update user data with the provided key and value."""
#     if user_id in user_data:
#         user_data[user_id][key] = value
#     else:
#         user_data[user_id] = {key: value}


async def get_menu(option, message, user_id):
    """Get menu for a specific option."""
    global watermark_config_page  # Declare global at the beginning of the function
    global merge_config_page  # Declare global at the beginning of the function

    handler_dict[user_id] = False
    user_dict = user_data.get(user_id, {})
    buttons = ButtonMaker()

    key = "set"
    buttons.data_button(
        "Change" if user_dict.get(option, False) else "Set",
        f"mediatools {user_id} {key} {option}",
    )

    if option in user_dict:
        buttons.data_button("Reset", f"mediatools {user_id} reset {option}")

    # Determine the back button target based on the option
    if option == "WATERMARK_PRIORITY":
        back_target = "watermark"  # This will take us back to the watermark menu when clicking Back
    elif option == "MERGE_PRIORITY":
        back_target = "merge"
    elif option == "CONVERT_PRIORITY":
        back_target = "convert"
    elif option == "COMPRESSION_PRIORITY":
        back_target = "compression"
    elif option == "TRIM_PRIORITY":
        back_target = "trim"
    elif option == "EXTRACT_PRIORITY":
        back_target = "extract"
    elif option == "REMOVE_PRIORITY":
        back_target = "remove"
    elif option.startswith(
        ("WATERMARK_", "AUDIO_WATERMARK_", "SUBTITLE_WATERMARK_", "IMAGE_WATERMARK_")
    ):
        # For all watermark settings, check if we need to return to a specific page

        # Check if we have a stored page number for this user
        stored_page = handler_dict.get(f"{user_id}_watermark_page")
        if stored_page is not None:
            # Use the stored page number
            back_target = f"watermark_config {stored_page}"
        # If no stored page, check if the message text contains page info
        elif message.text and "Page:" in message.text:
            try:
                page_info = message.text.split("Page:")[1].strip().split("/")[0]
                page_no = int(page_info) - 1
                # Update the global variable
                watermark_config_page = page_no
                # Also store it in handler_dict for consistency
                handler_dict[f"{user_id}_watermark_page"] = page_no
                back_target = f"watermark_config {page_no}"
            except (ValueError, IndexError):
                back_target = f"watermark_config {watermark_config_page}"
        elif option.startswith("IMAGE_WATERMARK_") and watermark_config_page == 0:
            # For image watermark settings, calculate the correct page if needed
            # Find the page that contains image settings
            visual_settings_len = 6  # Length of visual_settings array
            performance_settings_len = 2  # Length of performance_settings array
            items_per_page = 10  # From the code

            # Calculate which page the image settings start on
            image_settings_start_index = (
                visual_settings_len + performance_settings_len
            )
            image_settings_page = image_settings_start_index // items_per_page

            # Store the page number for future use
            handler_dict[f"{user_id}_watermark_page"] = image_settings_page
            back_target = f"watermark_config {image_settings_page}"
        else:
            # Use the global variable
            back_target = f"watermark_config {watermark_config_page}"
    elif option.startswith("CONVERT_VIDEO_"):
        back_target = "convert_video"
    elif option.startswith("CONVERT_AUDIO_"):
        back_target = "convert_audio"
    elif option.startswith("CONVERT_SUBTITLE_"):
        back_target = "convert_subtitle"
    elif option.startswith("CONVERT_DOCUMENT_"):
        back_target = "convert_document"
    elif option.startswith("CONVERT_ARCHIVE_"):
        back_target = "convert_archive"
    elif option.startswith("CONVERT_"):
        back_target = "convert"
    elif option in ["TRIM_START_TIME", "TRIM_END_TIME"] or option.startswith(
        (
            "TRIM_VIDEO_",
            "TRIM_AUDIO_",
            "TRIM_IMAGE_",
            "TRIM_DOCUMENT_",
            "TRIM_SUBTITLE_",
            "TRIM_ARCHIVE_",
        )
    ):
        back_target = "trim_config"
    elif option.startswith("TRIM_"):
        back_target = "trim"
    elif option.startswith(
        (
            "EXTRACT_VIDEO_",
            "EXTRACT_AUDIO_",
            "EXTRACT_SUBTITLE_",
            "EXTRACT_ATTACHMENT_",
            "EXTRACT_MAINTAIN_QUALITY",
        )
    ):
        back_target = "extract_config"
    elif option.startswith("EXTRACT_"):
        back_target = "extract"
    elif option.startswith(
        (
            "REMOVE_VIDEO_",
            "REMOVE_AUDIO_",
            "REMOVE_SUBTITLE_",
            "REMOVE_ATTACHMENT_",
        )
    ) or option in ["REMOVE_METADATA", "REMOVE_DELETE_ORIGINAL"]:
        back_target = "remove_config"
    elif option.startswith("REMOVE_"):
        back_target = "remove"
    elif option.startswith("ADD_VIDEO_"):
        back_target = "add_video_config"
    elif option.startswith("ADD_AUDIO_"):
        back_target = "add_audio_config"
    elif option.startswith("ADD_SUBTITLE_"):
        back_target = "add_subtitle_config"
    elif option.startswith("ADD_ATTACHMENT_"):
        back_target = "add_attachment_config"
    elif option.startswith("ADD_"):
        back_target = "add"
    elif option.startswith(
        (
            "COMPRESSION_VIDEO_",
            "COMPRESSION_AUDIO_",
            "COMPRESSION_IMAGE_",
            "COMPRESSION_DOCUMENT_",
            "COMPRESSION_SUBTITLE_",
            "COMPRESSION_ARCHIVE_",
        )
    ):
        back_target = "compression_config"
    elif option.startswith("COMPRESSION_"):
        back_target = "compression"
    elif option.startswith("MERGE_") or option in [
        "CONCAT_DEMUXER_ENABLED",
        "FILTER_COMPLEX_ENABLED",
    ]:
        # Check if we need to return to a specific page in merge_config

        if message.text and "Page:" in message.text:
            try:
                page_info = message.text.split("Page:")[1].strip().split("/")[0]
                page_no = int(page_info) - 1
                # Update the global variable (already declared at the top of the file)
                global merge_config_page
                merge_config_page = page_no
                back_target = f"merge_config {page_no}"
            except (ValueError, IndexError):
                back_target = f"merge_config {merge_config_page}"
        else:
            # Use the global variable
            back_target = f"merge_config {merge_config_page}"
    else:
        back_target = "back"

    buttons.data_button("Back", f"mediatools {user_id} {back_target}", "footer")

    # Check if we're in a task context (using -mt flag)
    is_task_context = user_id in task_context_users

    # Add appropriate buttons based on context
    if is_task_context:
        # In task context, add Done and Cancel buttons
        buttons.data_button("✅ Done", f"mediatools {user_id} task_done", "footer")
        buttons.data_button(
            "❌ Cancel", f"mediatools {user_id} task_cancel", "footer"
        )
    else:
        # In normal context, add Close button
        buttons.data_button("Close", f"mediatools {user_id} close", "footer")

    # Get current value
    if option in user_dict:
        current_value = user_dict[option]
    elif hasattr(Config, option) and getattr(Config, option):
        current_value = f"{getattr(Config, option)} (Global)"
    elif option == "WATERMARK_POSITION":
        current_value = "top_left (Default)"
    elif option == "WATERMARK_SIZE":
        current_value = "20 (Default)"
    elif option == "WATERMARK_COLOR":
        current_value = "white (Default)"
    elif option == "WATERMARK_FONT":
        current_value = "default.otf (Default)"
    elif option == "WATERMARK_PRIORITY":
        current_value = "2 (Default)"
    elif option in {"WATERMARK_THREADING"}:
        current_value = "True (Default)"
    elif option == "WATERMARK_OPACITY":
        current_value = "1.0 (Default)"
    elif option == "CONVERT_PRIORITY":
        current_value = "3 (Default)"
    elif option == "TRIM_PRIORITY":
        current_value = "4 (Default)"
    elif option == "EXTRACT_PRIORITY":
        current_value = "6 (Default)"
    elif option == "ADD_PRIORITY":
        current_value = "7 (Default)"
    elif option == "REMOVE_PRIORITY":
        current_value = "8 (Default)"
    elif option == "REMOVE_DELETE_ORIGINAL":
        current_value = "True (Default)"
    elif option in {"REMOVE_VIDEO_INDEX", "REMOVE_AUDIO_INDEX"} or option in {
        "REMOVE_SUBTITLE_INDEX",
        "REMOVE_ATTACHMENT_INDEX",
    }:
        current_value = "All (Default)"
    elif option == "REMOVE_METADATA":
        current_value = "False (Default)"
    elif option == "EXTRACT_DELETE_ORIGINAL":
        current_value = "True (Default)"
    elif (
        option in {"EXTRACT_VIDEO_QUALITY", "EXTRACT_VIDEO_PRESET"}
        or option in {"EXTRACT_VIDEO_BITRATE", "EXTRACT_VIDEO_RESOLUTION"}
        or option in {"EXTRACT_VIDEO_FPS", "EXTRACT_AUDIO_BITRATE"}
        or option in {"EXTRACT_AUDIO_CHANNELS", "EXTRACT_AUDIO_SAMPLING"}
        or option in {"EXTRACT_AUDIO_VOLUME", "EXTRACT_SUBTITLE_LANGUAGE"}
        or option in {"EXTRACT_SUBTITLE_ENCODING", "EXTRACT_SUBTITLE_FONT"}
        or option in {"EXTRACT_SUBTITLE_FONT_SIZE", "EXTRACT_ATTACHMENT_FILTER"}
    ):
        current_value = "none (Default)"
    elif option == "COMPRESSION_PRIORITY":
        current_value = "5 (Default)"
    elif (
        option in {"CONVERT_VIDEO_FORMAT", "CONVERT_VIDEO_CODEC"}
        or option == "CONVERT_VIDEO_QUALITY"
    ):
        current_value = "none (Default)"
    elif option == "CONVERT_VIDEO_CRF":
        current_value = "0 (Default)"
    elif option in {"CONVERT_VIDEO_PRESET", "CONVERT_AUDIO_FORMAT"} or option in {
        "CONVERT_AUDIO_CODEC",
        "CONVERT_AUDIO_BITRATE",
    }:
        current_value = "none (Default)"
    elif option in {"CONVERT_AUDIO_CHANNELS", "CONVERT_AUDIO_SAMPLING"}:
        current_value = "0 (Default)"
    elif option == "CONVERT_AUDIO_VOLUME":
        current_value = "0.0 (Default)"
    elif option in {"CONVERT_VIDEO_RESOLUTION", "CONVERT_VIDEO_FPS"}:
        current_value = "none (Default)"
    elif option == "CONVERT_DELETE_ORIGINAL":
        current_value = "False (Default)"
    elif (
        option in {"CONVERT_SUBTITLE_FORMAT", "CONVERT_SUBTITLE_ENCODING"}
        or option in {"CONVERT_SUBTITLE_LANGUAGE", "CONVERT_DOCUMENT_FORMAT"}
        or option == "CONVERT_DOCUMENT_QUALITY"
    ):
        current_value = "none (Default)"
    elif option == "CONVERT_DOCUMENT_DPI":
        current_value = "0 (Default)"
    elif option == "CONVERT_ARCHIVE_FORMAT":
        current_value = "none (Default)"
    elif option == "CONVERT_ARCHIVE_LEVEL":
        current_value = "0 (Default)"
    elif option == "CONVERT_ARCHIVE_METHOD":
        current_value = "none (Default)"
    elif option == "MERGE_PRIORITY":
        current_value = "1 (Default)"
    elif (
        option in {"MERGE_THREADING", "CONCAT_DEMUXER_ENABLED"}
        or option == "FILTER_COMPLEX_ENABLED"
    ):
        current_value = "True (Default)"
    elif (
        option in {"MERGE_OUTPUT_FORMAT_VIDEO", "MERGE_OUTPUT_FORMAT_AUDIO"}
        or option in {"MERGE_OUTPUT_FORMAT_IMAGE", "MERGE_OUTPUT_FORMAT_DOCUMENT"}
        or option == "MERGE_OUTPUT_FORMAT_SUBTITLE"
    ):
        current_value = "none (Default)"
    elif option == "MERGE_IMAGE_MODE":
        current_value = "auto (Default)"
    elif option == "MERGE_IMAGE_COLUMNS":
        current_value = "none (Default)"
    elif option == "MERGE_IMAGE_QUALITY":
        current_value = "90 (Default)"
    elif option in {"MERGE_IMAGE_DPI", "MERGE_IMAGE_RESIZE"}:
        current_value = "none (Default)"
    elif option == "MERGE_IMAGE_BACKGROUND":
        current_value = "white (Default)"
    elif option == "MERGE_VIDEO_CODEC":
        current_value = "copy (Default)"
    elif option in {"MERGE_VIDEO_QUALITY", "MERGE_VIDEO_PRESET"}:
        current_value = "medium (Default)"
    elif option == "MERGE_VIDEO_CRF":
        current_value = "none (Default)"
    elif option == "MERGE_VIDEO_PIXEL_FORMAT":
        current_value = "yuv420p (Default)"
    elif option == "MERGE_VIDEO_TUNE":
        current_value = "film (Default)"
    elif option == "MERGE_VIDEO_FASTSTART":
        current_value = "True (Default)"
    elif option == "MERGE_AUDIO_CODEC":
        current_value = "copy (Default)"
    elif option == "MERGE_AUDIO_BITRATE":
        current_value = "192k (Default)"
    elif option == "MERGE_AUDIO_CHANNELS":
        current_value = "none (Default)"
    elif option == "MERGE_AUDIO_SAMPLING":
        current_value = "44100 (Default)"
    elif option == "MERGE_AUDIO_VOLUME":
        current_value = "none (Default)"
    elif option == "MERGE_SUBTITLE_ENCODING":
        current_value = "utf-8 (Default)"
    elif option == "MERGE_SUBTITLE_FONT":
        current_value = "Arial (Default)"
    elif option == "MERGE_SUBTITLE_FONT_SIZE":
        current_value = "none (Default)"
    elif option == "MERGE_SUBTITLE_FONT_COLOR":
        current_value = "white (Default)"
    elif option == "MERGE_SUBTITLE_BACKGROUND":
        current_value = "black (Default)"
    elif option == "MERGE_DOCUMENT_PAPER_SIZE":
        current_value = "a4 (Default)"
    elif option == "MERGE_DOCUMENT_ORIENTATION":
        current_value = "portrait (Default)"
    elif option == "MERGE_DOCUMENT_MARGIN":
        current_value = "none (Default)"
    elif (
        option in {"MERGE_METADATA_TITLE", "MERGE_METADATA_AUTHOR"}
        or option == "MERGE_METADATA_COMMENT"
    ):
        current_value = "(Default: empty)"
    elif option == "MERGE_REMOVE_ORIGINAL":
        current_value = "True (Default)"
    elif option == "MEDIA_TOOLS_PRIORITY":
        current_value = "Default Order"
    elif option == "TRIM_START_TIME":
        current_value = "00:00:00 (Default)"
    elif option == "TRIM_END_TIME":
        current_value = "End of file (Default)"
    elif option == "TRIM_DOCUMENT_START_PAGE":
        current_value = "1 (Default)"
    elif option == "TRIM_DOCUMENT_END_PAGE":
        current_value = "Last page (Default)"
    else:
        current_value = "None"

    text = f"<b>Option:</b> {option}\n<b>Current Value:</b> <code>{current_value}</code>\n\n{media_tools_text.get(option, 'Set a value for this option.')}"

    await edit_message(message, text, buttons.build_menu(1))


async def set_option(_, message, option, rfunc):
    """Set an option value from user input."""
    user_id = message.from_user.id
    value = message.text
    # Set handler_dict to False to signal that we've received input

    if option == "WATERMARK_OPACITY":
        try:
            value = float(value)
            if value < 0.0 or value > 1.0:
                error_msg = await send_message(
                    message, "Opacity must be between 0.0 and 1.0!"
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(
                message, "Value must be a valid decimal number between 0.0 and 1.0!"
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option in {"WATERMARK_SIZE", "MERGE_IMAGE_COLUMNS", "MERGE_THREAD_NUMBER"}:
        try:
            value = int(value)
            if value <= 0:
                error_msg = await send_message(
                    message, "Value must be a positive integer!"
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(message, "Value must be a valid integer!")
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "WATERMARK_POSITION":
        valid_positions = [
            "top_left",
            "top_right",
            "bottom_left",
            "bottom_right",
            "center",
            "top_center",
            "bottom_center",
            "left_center",
            "right_center",
        ]
        if value not in valid_positions:
            error_msg = await send_message(
                message,
                f"Invalid position! Valid options are: {', '.join(valid_positions)}",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_IMAGE_MODE":
        valid_modes = ["auto", "horizontal", "vertical", "collage"]
        if value not in valid_modes:
            error_msg = await send_message(
                message,
                f"Invalid image mode! Valid options are: {', '.join(valid_modes)}",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_VIDEO_CODEC":
        valid_codecs = ["copy", "h264", "h265", "vp9", "av1"]
        if value not in valid_codecs:
            error_msg = await send_message(
                message,
                f"Invalid video codec! Valid options are: {', '.join(valid_codecs)}\nExample: copy - preserves original codec when possible\nExample: h264 - widely compatible codec",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_VIDEO_QUALITY":
        valid_qualities = ["low", "medium", "high", "veryhigh"]
        if value not in valid_qualities:
            error_msg = await send_message(
                message,
                f"Invalid video quality! Valid options are: {', '.join(valid_qualities)}\nExample: medium - balanced quality and file size\nExample: high - better quality but larger file size",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_VIDEO_PRESET":
        valid_presets = [
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ]
        if value not in valid_presets:
            error_msg = await send_message(
                message,
                f"Invalid video preset! Valid options are: {', '.join(valid_presets)}\nExample: medium - balanced encoding speed and compression\nExample: slow - better compression but slower encoding",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_VIDEO_CRF":
        try:
            crf = int(value)
            if crf < 0 or crf > 51:
                error_msg = await send_message(
                    message,
                    "CRF value must be between 0 and 51! Lower values mean better quality but larger file size.\nExample: 23 - default value, good balance\nExample: 18 - visually lossless",
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(
                message,
                "CRF value must be an integer between 0 and 51!\nExample: 23 - default value, good balance\nExample: 18 - visually lossless",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_VIDEO_PIXEL_FORMAT":
        valid_formats = [
            "yuv420p",
            "yuv422p",
            "yuv444p",
            "yuv420p10le",
            "yuv422p10le",
            "yuv444p10le",
        ]
        if value not in valid_formats:
            error_msg = await send_message(
                message,
                f"Invalid pixel format! Valid options are: {', '.join(valid_formats)}\nExample: yuv420p - most compatible format\nExample: yuv444p - highest quality but larger file size",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_VIDEO_TUNE":
        valid_tunes = [
            "film",
            "animation",
            "grain",
            "stillimage",
            "fastdecode",
            "zerolatency",
        ]
        if value not in valid_tunes:
            error_msg = await send_message(
                message,
                f"Invalid video tune! Valid options are: {', '.join(valid_tunes)}\nExample: film - for live-action content\nExample: animation - for animated content",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_VIDEO_FASTSTART":
        if value.lower() not in ["true", "false"]:
            error_msg = await send_message(
                message,
                "Faststart value must be 'true' or 'false'!\nEnabling faststart allows videos to start playing before they are fully downloaded.",
            )
            await auto_delete_message(error_msg, time=300)
            return
        value = value.lower() == "true"
    elif option == "MERGE_AUDIO_CODEC":
        valid_codecs = ["copy", "aac", "mp3", "opus", "flac"]
        if value not in valid_codecs:
            error_msg = await send_message(
                message,
                f"Invalid audio codec! Valid options are: {', '.join(valid_codecs)}\nExample: copy - preserves original codec when possible\nExample: aac - good quality and compatibility",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_AUDIO_BITRATE":
        valid_bitrates = ["64k", "96k", "128k", "192k", "256k", "320k"]
        if value not in valid_bitrates and not (
            value.endswith("k") and value[:-1].isdigit()
        ):
            error_msg = await send_message(
                message,
                f"Invalid audio bitrate! Common options are: {', '.join(valid_bitrates)}\nExample: 192k - good quality for most content\nExample: 320k - high quality audio",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_AUDIO_CHANNELS":
        try:
            channels = int(value)
            if channels < 1 or channels > 8:
                error_msg = await send_message(
                    message,
                    "Audio channels must be between 1 and 8!\nExample: 2 - stereo audio\nExample: 1 - mono audio",
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(
                message,
                "Audio channels must be an integer between 1 and 8!\nExample: 2 - stereo audio\nExample: 1 - mono audio",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_AUDIO_SAMPLING":
        valid_rates = ["8000", "11025", "22050", "44100", "48000", "96000"]
        if value not in valid_rates and not value.isdigit():
            error_msg = await send_message(
                message,
                f"Invalid sampling rate! Common options are: {', '.join(valid_rates)}\nExample: 44100 - CD quality\nExample: 48000 - DVD/professional audio quality",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_AUDIO_VOLUME":
        try:
            volume = float(value)
            if volume < 0 or volume > 10:
                error_msg = await send_message(
                    message,
                    "Volume must be between 0 and 10!\nExample: 1.0 - original volume\nExample: 2.0 - double volume",
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(
                message,
                "Volume must be a number between 0 and 10!\nExample: 1.0 - original volume\nExample: 2.0 - double volume",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "TRIM_START_TIME":
        # Allow empty value for start time (beginning of file)
        if value == "":
            value = "00:00:00"
        # Validate time format (HH:MM:SS or MM:SS or SS)
        import re

        time_pattern = re.compile(r"^(\d+:)?(\d+:)?(\d+)(\.\d+)?$")
        if not time_pattern.match(value):
            error_msg = await send_message(
                message,
                "Invalid time format! Use HH:MM:SS, MM:SS, or SS format.\nExample: 00:01:30 (1 minute 30 seconds)\nExample: 5:45 (5 minutes 45 seconds)\nExample: 90 (90 seconds)",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "TRIM_END_TIME":
        # Allow empty value for end time (end of file)
        if value == "":
            value = ""  # Empty string means end of file
        else:
            # Validate time format (HH:MM:SS or MM:SS or SS)
            import re

            time_pattern = re.compile(r"^(\d+:)?(\d+:)?(\d+)(\.\d+)?$")
            if not time_pattern.match(value):
                error_msg = await send_message(
                    message,
                    "Invalid time format! Use HH:MM:SS, MM:SS, or SS format.\nExample: 00:02:30 (2 minutes 30 seconds)\nExample: 10:45 (10 minutes 45 seconds)\nExample: 180 (180 seconds)",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "TRIM_DOCUMENT_START_PAGE":
        # Validate page number (must be positive integer)
        try:
            page_num = int(value)
            if page_num < 1:
                raise ValueError("Page number must be positive")
            value = str(page_num)
        except ValueError:
            error_msg = await send_message(
                message,
                "Invalid page number! Must be a positive integer.\nExample: 1 (first page)\nExample: 5 (fifth page)",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "TRIM_DOCUMENT_END_PAGE":
        # Allow empty value for end page (last page) or validate page number
        if value == "":
            value = ""  # Empty string means last page
        else:
            try:
                page_num = int(value)
                if page_num < 1:
                    raise ValueError("Page number must be positive")
                value = str(page_num)
            except ValueError:
                error_msg = await send_message(
                    message,
                    "Invalid page number! Must be a positive integer or empty for last page.\nExample: 10 (tenth page)\nExample: (empty for last page)",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_DELETE_ORIGINAL":
        if value.lower() not in ["true", "false"]:
            error_msg = await send_message(
                message,
                "Value must be 'true' or 'false'!\nExample: true - delete original files after extraction\nExample: false - keep original files",
            )
            await auto_delete_message(error_msg, time=300)
            return
        value = value.lower() == "true"
    elif option == "EXTRACT_VIDEO_QUALITY":
        if value.lower() == "none":
            value = "none"
        else:
            try:
                quality = int(value)
                if quality < 0 or quality > 51:
                    error_msg = await send_message(
                        message,
                        "CRF value must be between 0 and 51 or 'none'! Lower values mean better quality but larger file size.\nExample: 23 - default value, good balance\nExample: 18 - visually lossless\nExample: none - don't set quality",
                    )
                    await auto_delete_message(error_msg, time=300)
                    return
            except ValueError:
                error_msg = await send_message(
                    message,
                    "CRF value must be an integer between 0 and 51 or 'none'!\nExample: 23 - default value, good balance\nExample: 18 - visually lossless\nExample: none - don't set quality",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_VIDEO_PRESET":
        if value.lower() == "none":
            value = "none"
        else:
            valid_presets = [
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ]
            if value not in valid_presets:
                error_msg = await send_message(
                    message,
                    f"Invalid video preset! Valid options are: {', '.join(valid_presets)} or 'none'\nExample: medium - balanced encoding speed and compression\nExample: slow - better compression but slower encoding\nExample: none - don't set preset",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_VIDEO_BITRATE":
        if value.lower() == "none":
            value = "none"
        else:
            valid_bitrates = ["1M", "2M", "5M", "8M", "10M", "15M", "20M"]
            if value not in valid_bitrates and not (
                (value.endswith("k") and value[:-1].isdigit())
                or (value.endswith("M") and value[:-1].isdigit())
            ):
                error_msg = await send_message(
                    message,
                    f"Invalid video bitrate! Common options are: {', '.join(valid_bitrates)} or 'none'\nExample: 5M - 5 megabits per second\nExample: 500k - 500 kilobits per second\nExample: none - don't set bitrate",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_VIDEO_RESOLUTION":
        if value.lower() == "none":
            value = "none"
        else:
            valid_resolutions = ["1920x1080", "1280x720", "854x480", "640x360"]
            if value not in valid_resolutions and not (
                value.count("x") == 1
                and all(part.isdigit() for part in value.split("x"))
            ):
                error_msg = await send_message(
                    message,
                    f"Invalid resolution! Common options are: {', '.join(valid_resolutions)} or 'none'\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: none - don't set resolution",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_VIDEO_FPS":
        if value.lower() == "none":
            value = "none"
        else:
            valid_fps = ["24", "25", "30", "50", "60"]
            if value not in valid_fps and not value.isdigit():
                error_msg = await send_message(
                    message,
                    f"Invalid FPS! Common options are: {', '.join(valid_fps)} or 'none'\nExample: 30 - 30 frames per second\nExample: 60 - 60 frames per second\nExample: none - don't set FPS",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_AUDIO_BITRATE":
        if value.lower() == "none":
            value = "none"
        else:
            valid_bitrates = ["64k", "96k", "128k", "192k", "256k", "320k"]
            if value not in valid_bitrates and not (
                value.endswith("k") and value[:-1].isdigit()
            ):
                error_msg = await send_message(
                    message,
                    f"Invalid audio bitrate! Common options are: {', '.join(valid_bitrates)} or 'none'\nExample: 192k - good quality for most content\nExample: 320k - high quality audio\nExample: none - don't set bitrate",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_AUDIO_CHANNELS":
        if value.lower() == "none":
            value = "none"
        else:
            try:
                channels = int(value)
                if channels < 1 or channels > 8:
                    error_msg = await send_message(
                        message,
                        "Audio channels must be between 1 and 8 or 'none'!\nExample: 2 - stereo audio\nExample: 1 - mono audio\nExample: none - don't set channels",
                    )
                    await auto_delete_message(error_msg, time=300)
                    return
            except ValueError:
                error_msg = await send_message(
                    message,
                    "Audio channels must be an integer between 1 and 8 or 'none'!\nExample: 2 - stereo audio\nExample: 1 - mono audio\nExample: none - don't set channels",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_AUDIO_SAMPLING":
        if value.lower() == "none":
            value = "none"
        else:
            valid_rates = ["8000", "11025", "22050", "44100", "48000", "96000"]
            if value not in valid_rates and not value.isdigit():
                error_msg = await send_message(
                    message,
                    f"Invalid sampling rate! Common options are: {', '.join(valid_rates)} or 'none'\nExample: 44100 - CD quality\nExample: 48000 - DVD/professional audio quality\nExample: none - don't set sampling rate",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_AUDIO_VOLUME":
        if value.lower() == "none":
            value = "none"
        else:
            try:
                volume = float(value)
                if volume < 0 or volume > 10:
                    error_msg = await send_message(
                        message,
                        "Volume must be between 0 and 10 or 'none'!\nExample: 1.0 - original volume\nExample: 2.0 - double volume\nExample: none - don't set volume",
                    )
                    await auto_delete_message(error_msg, time=300)
                    return
            except ValueError:
                error_msg = await send_message(
                    message,
                    "Volume must be a number between 0 and 10 or 'none'!\nExample: 1.0 - original volume\nExample: 2.0 - double volume\nExample: none - don't set volume",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_SUBTITLE_LANGUAGE":
        if value.lower() == "none":
            value = "none"
        else:
            valid_languages = [
                "eng",
                "spa",
                "fre",
                "ger",
                "ita",
                "jpn",
                "chi",
                "kor",
                "rus",
            ]
            if len(value) != 3 and value not in valid_languages:
                error_msg = await send_message(
                    message,
                    f"Invalid language code! Common options are: {', '.join(valid_languages)} or 'none'\nExample: eng - English\nExample: spa - Spanish\nExample: none - don't set language",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_SUBTITLE_ENCODING":
        if value.lower() == "none":
            value = "none"
        else:
            valid_encodings = ["utf-8", "utf-16", "ascii", "latin1", "cp1252"]
            if value not in valid_encodings:
                error_msg = await send_message(
                    message,
                    f"Invalid encoding! Common options are: {', '.join(valid_encodings)} or 'none'\nExample: utf-8 - universal encoding\nExample: latin1 - for Western European languages\nExample: none - don't set encoding",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_SUBTITLE_FONT":
        if value.lower() == "none":
            value = "none"
        elif value.strip() == "":
            error_msg = await send_message(
                message,
                "Font name cannot be empty! Use 'none' to not set a font.\nExample: Arial - widely available font\nExample: DejaVu Sans - good for multiple languages\nExample: none - don't set font",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "EXTRACT_SUBTITLE_FONT_SIZE":
        if value.lower() == "none":
            value = "none"
        else:
            try:
                size = int(value)
                if size < 8 or size > 72:
                    error_msg = await send_message(
                        message,
                        "Font size must be between 8 and 72 or 'none'!\nExample: 24 - medium size\nExample: 32 - larger size for better readability\nExample: none - don't set font size",
                    )
                    await auto_delete_message(error_msg, time=300)
                    return
            except ValueError:
                error_msg = await send_message(
                    message,
                    "Font size must be an integer between 8 and 72 or 'none'!\nExample: 24 - medium size\nExample: 32 - larger size for better readability\nExample: none - don't set font size",
                )
                await auto_delete_message(error_msg, time=300)
                return
    elif option == "EXTRACT_ATTACHMENT_FILTER":
        if value.lower() == "none":
            value = "none"
        elif value.strip() == "":
            error_msg = await send_message(
                message,
                "Filter pattern cannot be empty! Use 'none' to not set a filter.\nExample: *.ttf - extract only TTF font files\nExample: *.jpg - extract only JPG images\nExample: none - don't set filter",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_IMAGE_MODE":
        valid_modes = ["auto", "horizontal", "vertical", "collage"]
        if value not in valid_modes:
            error_msg = await send_message(
                message,
                f"Invalid image mode! Valid options are: {', '.join(valid_modes)}\nExample: auto - choose based on number of images\nExample: collage - grid layout",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_IMAGE_QUALITY":
        try:
            quality = int(value)
            if quality < 1 or quality > 100:
                error_msg = await send_message(
                    message,
                    "Image quality must be between 1 and 100!\nExample: 90 - high quality\nExample: 75 - good balance of quality and size",
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(
                message,
                "Image quality must be an integer between 1 and 100!\nExample: 90 - high quality\nExample: 75 - good balance of quality and size",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_IMAGE_DPI":
        try:
            dpi = int(value)
            if dpi < 72 or dpi > 1200:
                error_msg = await send_message(
                    message,
                    "DPI must be between 72 and 1200!\nExample: 300 - good for printing\nExample: 72 - standard screen resolution",
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(
                message,
                "DPI must be an integer between 72 and 1200!\nExample: 300 - good for printing\nExample: 72 - standard screen resolution",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_IMAGE_RESIZE":
        if value != "none" and not (
            value.count("x") == 1
            and all(part.isdigit() for part in value.split("x"))
        ):
            error_msg = await send_message(
                message,
                "Resize value must be 'none' or in the format 'widthxheight'!\nExample: none - keep original size\nExample: 1920x1080 - resize to Full HD",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_IMAGE_BACKGROUND":
        valid_colors = [
            "white",
            "black",
            "transparent",
            "red",
            "green",
            "blue",
            "yellow",
        ]
        if value not in valid_colors and not (
            value.startswith("#") and len(value) == 7
        ):
            error_msg = await send_message(
                message,
                f"Invalid background color! Common options are: {', '.join(valid_colors)} or hex code like #RRGGBB\nExample: white - white background\nExample: #FF0000 - red background",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_SUBTITLE_ENCODING":
        valid_encodings = ["utf-8", "utf-16", "ascii", "latin1", "cp1252"]
        if value not in valid_encodings:
            error_msg = await send_message(
                message,
                f"Invalid encoding! Common options are: {', '.join(valid_encodings)}\nExample: utf-8 - universal encoding\nExample: latin1 - for Western European languages",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_SUBTITLE_FONT":
        # Any font name is valid, but suggest common ones
        if value.strip() == "":
            error_msg = await send_message(
                message,
                "Font name cannot be empty!\nExample: Arial - widely available font\nExample: DejaVu Sans - good for multiple languages",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_SUBTITLE_FONT_SIZE":
        try:
            size = int(value)
            if size < 8 or size > 72:
                error_msg = await send_message(
                    message,
                    "Font size must be between 8 and 72!\nExample: 24 - medium size\nExample: 32 - larger size for better readability",
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(
                message,
                "Font size must be an integer between 8 and 72!\nExample: 24 - medium size\nExample: 32 - larger size for better readability",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option in {"MERGE_SUBTITLE_FONT_COLOR", "MERGE_SUBTITLE_BACKGROUND"}:
        valid_colors = [
            "white",
            "black",
            "yellow",
            "red",
            "green",
            "blue",
            "transparent",
        ]
        if value not in valid_colors and not (
            value.startswith("#") and len(value) == 7
        ):
            error_msg = await send_message(
                message,
                f"Invalid color! Common options are: {', '.join(valid_colors)} or hex code like #RRGGBB\nExample: white - white text\nExample: #FFFF00 - yellow text",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_DOCUMENT_PAPER_SIZE":
        valid_sizes = ["a4", "letter", "legal", "a3", "a5"]
        if value not in valid_sizes:
            error_msg = await send_message(
                message,
                f"Invalid paper size! Common options are: {', '.join(valid_sizes)}\nExample: a4 - standard international paper size\nExample: letter - standard US paper size",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_DOCUMENT_ORIENTATION":
        valid_orientations = ["portrait", "landscape"]
        if value not in valid_orientations:
            error_msg = await send_message(
                message,
                f"Invalid orientation! Valid options are: {', '.join(valid_orientations)}\nExample: portrait - vertical orientation\nExample: landscape - horizontal orientation",
            )
            await auto_delete_message(error_msg, time=300)
            return
    elif option == "MERGE_DOCUMENT_MARGIN":
        try:
            margin = int(value)
            if margin < 0 or margin > 100:
                error_msg = await send_message(
                    message,
                    "Margin must be between 0 and 100!\nExample: 50 - standard margin\nExample: 0 - no margin",
                )
                await auto_delete_message(error_msg, time=300)
                return
        except ValueError:
            error_msg = await send_message(
                message,
                "Margin must be an integer between 0 and 100!\nExample: 50 - standard margin\nExample: 0 - no margin",
            )
            await auto_delete_message(error_msg, time=300)
            return

    # Set handler_dict to False to signal that we've received input
    handler_dict[user_id] = False

    update_user_ldata(user_id, option, value)
    await delete_message(message)

    # For WATERMARK_PRIORITY, return to the menu WATERMARK_PRIORITY
    if option == "WATERMARK_PRIORITY":
        # Create a fake CallbackQuery object to pass to get_menu
        await get_menu("WATERMARK_PRIORITY", message, user_id)
    # Check if we're in a watermark menu with pagination
    elif option.startswith(
        ("WATERMARK_", "AUDIO_WATERMARK_", "SUBTITLE_WATERMARK_")
    ):
        # Go back to the watermark config page instead of the main watermark menu
        # We use the global watermark_config_page variable but don't modify it here
        # Go to the correct pagination page
        # Create a fake CallbackQuery object to pass to update_media_tools_settings
        fake_query = CallbackQuery(
            id="fake_id",
            from_user=message.from_user,
            chat_instance="fake_chat",
            message=message,
            data=f"mediatools {user_id} watermark_config {watermark_config_page}",
        )
        await update_media_tools_settings(
            fake_query, f"watermark_config {watermark_config_page}"
        )
    # For image watermark settings, go to the correct pagination page
    elif option.startswith("IMAGE_WATERMARK_"):
        # Check if we have a stored page number
        stored_page = handler_dict.get(f"{user_id}_watermark_page")

        if stored_page is not None:
            # Use the stored page number if available
            await update_media_tools_settings(
                message, f"watermark_config {stored_page}"
            )
            return

        # If no stored page, find the page that contains image settings
        # The image settings are after visual_settings and performance_settings
        # We need to determine which page they're on based on the items_per_page
        visual_settings_len = 6  # Length of visual_settings array
        performance_settings_len = 2  # Length of performance_settings array
        items_per_page = 10  # From the code

        # Calculate which page the image settings start on
        image_settings_start_index = visual_settings_len + performance_settings_len
        image_settings_page = image_settings_start_index // items_per_page

        # Go to the page containing image settings
        # Create a fake CallbackQuery object to pass to update_media_tools_settings
        fake_query = CallbackQuery(
            id="fake_id",
            from_user=message.from_user,
            chat_instance="fake_chat",
            message=message,
            data=f"mediatools {user_id} watermark_config {image_settings_page}",
        )
        await update_media_tools_settings(
            fake_query, f"watermark_config {image_settings_page}"
        )
    # Add specific handling for Add feature settings
    elif option.startswith("ADD_VIDEO_"):
        # For video add settings, go back to the video add config menu
        # Create a fake CallbackQuery object to pass to update_media_tools_settings
        fake_query = CallbackQuery(
            id="fake_id",
            from_user=message.from_user,
            chat_instance="fake_chat",
            message=message,
            data=f"mediatools {user_id} add_video_config",
        )
        await update_media_tools_settings(fake_query, "add_video_config")
    elif option.startswith("ADD_AUDIO_"):
        # For audio add settings, go back to the audio add config menu
        fake_query = CallbackQuery(
            id="fake_id",
            from_user=message.from_user,
            chat_instance="fake_chat",
            message=message,
            data=f"mediatools {user_id} add_audio_config",
        )
        await update_media_tools_settings(fake_query, "add_audio_config")
    elif option.startswith("ADD_SUBTITLE_"):
        # For subtitle add settings, go back to the subtitle add config menu
        fake_query = CallbackQuery(
            id="fake_id",
            from_user=message.from_user,
            chat_instance="fake_chat",
            message=message,
            data=f"mediatools {user_id} add_subtitle_config",
        )
        await update_media_tools_settings(fake_query, "add_subtitle_config")
    elif option.startswith("ADD_ATTACHMENT_"):
        # For attachment add settings, go back to the attachment add config menu
        fake_query = CallbackQuery(
            id="fake_id",
            from_user=message.from_user,
            chat_instance="fake_chat",
            message=message,
            data=f"mediatools {user_id} add_attachment_config",
        )
        await update_media_tools_settings(fake_query, "add_attachment_config")
    # If we're in a merge_config menu with pagination, extract the page number
    elif (
        (
            option.startswith("MERGE_")
            or option in ["CONCAT_DEMUXER_ENABLED", "FILTER_COMPLEX_ENABLED"]
        )
        and hasattr(message, "reply_to_message")
        and message.reply_to_message
        and message.reply_to_message.text
        and "Page:" in message.reply_to_message.text
    ):
        try:
            page_info = (
                message.reply_to_message.text.split("Page:")[1].strip().split("/")[0]
            )
            page_no = int(page_info) - 1
            # Update the global merge_config_page variable
            global merge_config_page
            merge_config_page = (
                page_no  # Create a new rfunc that will return to the correct page
            )
            # Create a fake CallbackQuery object to pass to update_media_tools_settings
            fake_query = CallbackQuery(
                id="fake_id",
                from_user=message.from_user,
                chat_instance="fake_chat",
                message=message,
                data=f"mediatools {user_id} merge_config {page_no}",
            )
            await update_media_tools_settings(fake_query, f"merge_config {page_no}")
        except (ValueError, IndexError):
            # Call rfunc which should be a function that returns to the previous menu
            await rfunc()
    else:
        # Call rfunc which should be a function that returns to the previous menu
        await rfunc()

    await database.update_user_data(user_id)


async def event_handler(client, query, pfunc, rfunc, photo=False, document=False):
    """Handle user input events."""
    user_id = query.from_user.id
    handler_dict[user_id] = True
    start_time = 60  # seconds
    handler = None

    try:
        # Create a custom filter using the event_filter_func
        # We need to create a class to hold our filter method
        class CustomFilter:
            async def event_filter_func(self, _, update):
                # Check if update is a message and has the required attributes
                if (
                    not update
                    or not hasattr(update, "from_user")
                    or update.from_user is None
                ):
                    return False

                if update.from_user.id != user_id:
                    return False
                if photo and (not hasattr(update, "photo") or update.photo is None):
                    return False
                return not (
                    document
                    and (not hasattr(update, "document") or update.document is None)
                )

        # Create the filter using the method from our class
        custom_filter = create(CustomFilter().event_filter_func)

        # Add the handler with the custom filter
        handler = client.add_handler(
            MessageHandler(pfunc, filters=custom_filter), group=-1
        )

        # Wait for user input (up to start_time seconds)
        for _ in range(start_time):
            if not handler_dict[user_id]:
                break
            await sleep(1)

        # Clean up
        if handler_dict[user_id]:
            handler_dict[user_id] = False
            await auto_delete_message(query.message, time=300)
            # If we timed out, call rfunc to go back to the menu
            await rfunc()
    finally:
        # Always remove the handler, even if there was an exception
        if handler:
            client.remove_handler(*handler)


@new_task
async def media_tools_settings(_, message):
    """Show media tools settings."""
    from bot.core.config_manager import Config

    # Force refresh Config.MEDIA_TOOLS_ENABLED from database to ensure accurate status
    try:
        # Check if database is connected and db attribute exists
        if (
            database.db is not None
            and hasattr(database, "db")
            and hasattr(database.db, "settings")
        ):
            db_config = await database.db.settings.config.find_one(
                {"_id": TgClient.ID},
                {"MEDIA_TOOLS_ENABLED": 1, "_id": 0},
            )
            if db_config and "MEDIA_TOOLS_ENABLED" in db_config:
                # Update Config with the latest value from database
                Config.MEDIA_TOOLS_ENABLED = db_config["MEDIA_TOOLS_ENABLED"]
    except Exception:
        pass

    # Check if media tools are enabled after refreshing from database
    if not is_media_tool_enabled("mediatools"):
        error_msg = await send_message(
            message,
            "<b>Media Tools are disabled</b>\n\nMedia Tools have been disabled by the bot owner.",
        )
        # Auto-delete the command message immediately
        await delete_message(message)
        # Auto-delete the error message after 5 minutes
        await auto_delete_message(error_msg, time=300)
        return

    msg, btns = await get_media_tools_settings(message.from_user)
    settings_msg = await send_message(message, msg, btns)
    # Auto-delete the command message immediately
    await delete_message(message)
    # Auto-delete the settings menu after 5 minutes
    await auto_delete_message(settings_msg, time=300)


@new_task
async def edit_media_tools_settings(client, query):
    """Handle media tools settings callback queries."""
    global watermark_config_page, merge_config_page
    from_user = query.from_user
    user_id = from_user.id
    message = query.message
    data = query.data.split()
    handler_dict[user_id] = False
    user_dict = user_data.get(user_id, {})

    if user_id != int(data[1]):
        await query.answer("Not Yours!", show_alert=True)
        return

    if data[2] == "cancel_upload":
        await query.answer("Upload cancelled")
        # Reset the handler_dict for this user
        handler_dict[user_id] = False

        # Clean up handler_dict entries
        if f"{user_id}_from_bot_settings" in handler_dict:
            del handler_dict[f"{user_id}_from_bot_settings"]

        # Get the original message if it exists
        original_message = handler_dict.get(f"{user_id}_original_message", None)

        # Clean up the original_message entry
        if f"{user_id}_original_message" in handler_dict:
            del handler_dict[f"{user_id}_original_message"]

        # Check if we were redirected from bot_settings
        if hasattr(query, "from_bot_settings") and query.from_bot_settings:
            # Import the handler from bot_settings module
            from bot.modules.bot_settings import update_buttons

            # Return to the watermark settings in bot_settings
            await update_buttons(query.message, "mediatools_watermark")
        elif original_message:
            # If we have the original message, use it to return to the watermark menu
            # This ensures we update the correct message
            await update_media_tools_settings(
                CallbackQuery(
                    id="fake_id",
                    from_user=query.from_user,
                    chat_instance="fake_chat",
                    message=original_message,
                    data=f"mediatools {user_id} watermark",
                )
            )
        else:
            # Return to the watermark menu in media_tools
            await update_media_tools_settings(query, "watermark")

    elif data[2] == "back_to_watermark_config":
        await query.answer()
        # Check if we have a page number in the data
        if len(data) > 3:
            try:
                page_no = int(data[3])
                # Go to the specified page
                await update_media_tools_settings(
                    query, f"watermark_config {page_no}"
                )
                return
            except (ValueError, IndexError):
                pass

        # Check if we have a stored context for image watermark settings
        if hasattr(query, "from_image_settings") and query.from_image_settings:
            # Find the page that contains image settings
            visual_settings_len = 6  # Length of visual_settings array
            performance_settings_len = 2  # Length of performance_settings array
            items_per_page = 10  # From the code

            # Calculate which page the image settings start on
            image_settings_start_index = (
                visual_settings_len + performance_settings_len
            )
            image_settings_page = image_settings_start_index // items_per_page

            # Go to the page containing image settings
            await update_media_tools_settings(
                query, f"watermark_config {image_settings_page}"
            )
        else:
            # For other settings, go back to the watermark config page using the global variable
            await update_media_tools_settings(
                query, f"watermark_config {watermark_config_page}"
            )

    elif data[2] == "default_watermark_text":
        await query.answer(
            "Resetting all watermark text settings to default values..."
        )

        # Reset all watermark text settings to default
        watermark_text_settings = [
            # Visual settings
            "WATERMARK_POSITION",
            "WATERMARK_SIZE",
            "WATERMARK_COLOR",
            "WATERMARK_FONT",
            "WATERMARK_OPACITY",
            # Performance settings
            "WATERMARK_QUALITY",
            "WATERMARK_SPEED",
            # Audio watermark settings
            "AUDIO_WATERMARK_VOLUME",
            "AUDIO_WATERMARK_INTERVAL",
            # Subtitle watermark settings
            "SUBTITLE_WATERMARK_STYLE",
            "SUBTITLE_WATERMARK_INTERVAL",
        ]

        # Reset each setting to None (which will use the default value)
        for setting in watermark_text_settings:
            if setting in user_dict:
                del user_dict[setting]
        await database.update_user_data(user_id)

        # Stay on the same page
        # Use stored page if available, otherwise use global
        stored_page = handler_dict.get(f"{user_id}_watermark_page")
        if stored_page is not None:
            await update_media_tools_settings(
                query, f"watermark_config {stored_page}"
            )
        else:
            await update_media_tools_settings(
                query, f"watermark_config {watermark_config_page}"
            )

    elif data[2] == "back":
        await query.answer()
        await update_media_tools_settings(query)
    elif data[2] == "close":
        await query.answer()
        await delete_message(message)
    elif data[2] == "task_done":
        await query.answer("✅ Settings saved! Starting task...")
        # Check if there's a task context for this user
        if user_id in task_contexts:
            # Set the result to True and trigger the event
            task_contexts[user_id]["result"] = True
            task_contexts[user_id]["event"].set()
            # Note: Don't remove from task_context_users here, let show_media_tools_for_task handle cleanup
        # Fallback behavior: If no task context found but user clicked Done,
        # this could mean:
        # 1. They used -mt flag but something went wrong with context tracking
        # 2. They're using the regular media tools menu (accessed via /mediatools)

        # Check if user is in task context set or pending set (they should be if using -mt flag)
        elif user_id in task_context_users or user_id in pending_task_users:
            # Store the direct result for when show_media_tools_for_task is called
            direct_task_results[user_id] = True
            # Add to task context set and remove from pending
            task_context_users.add(user_id)
            pending_task_users.discard(user_id)

            # Since this is a fallback, we should also close the menu
            await edit_message(message, "✅ Settings saved! Starting task...")
            await sleep(2)
            await delete_message(message)
        else:
            # This is normal behavior when using regular media tools menu (not -mt flag)
            # Just close the menu since settings are already saved
            await edit_message(message, "✅ Settings saved!")
            await sleep(2)
            await delete_message(message)
    elif data[2] == "task_cancel":
        await query.answer("❌ Task cancelled!")
        # Check if there's a task context for this user
        if user_id in task_contexts:
            # Set the result to False and trigger the event
            task_contexts[user_id]["result"] = False
            task_contexts[user_id]["event"].set()
            # Note: Don't remove from task_context_users here, let show_media_tools_for_task handle cleanup
        # Fallback behavior: If no task context found but user clicked Cancel,
        # this means they used -mt flag but something went wrong with context tracking

        # Check if user is in task context set or pending set (they should be if using -mt flag)
        elif user_id in task_context_users or user_id in pending_task_users:
            # Store the direct result for when show_media_tools_for_task is called
            direct_task_results[user_id] = False
            # Add to task context set and remove from pending
            task_context_users.add(user_id)
            pending_task_users.discard(user_id)

            # Since this is a fallback, we should also close the menu
            await edit_message(message, "❌ Task cancelled by user.")
            await sleep(2)
            await delete_message(message)
        else:
            # This is normal behavior when using regular media tools menu (not -mt flag)
            # Just close the menu
            await edit_message(message, "❌ Operation cancelled!")
            await sleep(2)
            await delete_message(message)
    elif data[2] in [
        "watermark",
        "merge",
        "convert",
        "compression",
        "compression_config",
        "trim",
        "trim_config",
        "extract",
        "extract_config",
        "remove",
        "remove_config",
        "add",
        "add_config",
        "add_video_config",
        "add_audio_config",
        "add_subtitle_config",
        "add_attachment_config",
        "swap",
        "swap_audio",
        "swap_video",
        "swap_subtitle",
        "remove_video_config",
        "remove_audio_config",
        "remove_subtitle_config",
        "remove_attachment_config",
        "convert_video",
        "convert_audio",
        "convert_subtitle",
        "convert_document",
        "convert_archive",
        "help",
        "help_watermark",
        "help_merge",
        "help_convert",
        "help_compression",
        "help_trim",
        "help_extract",
        "help_remove",
        "help_add",
        "help_swap",
        "help_priority",
        "help_examples",
    ]:
        await query.answer()
        await update_media_tools_settings(query, data[2])
    elif data[2] == "upload_image":
        await query.answer("Please send your watermark image")

        # Store the current user_id in handler_dict to track the upload
        handler_dict[user_id] = True

        # Check if we were redirected from bot_settings and store the flag in handler_dict
        # This will be used by the message handler to know where to return after upload
        handler_dict[f"{user_id}_from_bot_settings"] = (
            hasattr(query, "from_bot_settings") and query.from_bot_settings
        )

        # Store the original message for returning to the menu later
        handler_dict[f"{user_id}_original_message"] = query.message

        # Create buttons for the instructions message
        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"mediatools {user_id} cancel_upload")

        # Send instructions to the user with a more user-friendly message
        msg = await edit_message(
            query.message,
            "<b>📤 Upload Watermark Image</b>\n\n"
            "Please send your watermark image as a photo.\n\n"
            "<b>Tips:</b>\n"
            "• Image with transparent background (PNG) works best\n"
            "• Recommended size: 500x500 pixels or smaller\n"
            "• Keep file size under 1MB for best performance\n\n"
            "<i>Waiting for image... (60 seconds timeout)</i>",
            buttons.build_menu(1),
        )

        # Set up a proper event handler to wait for the image upload
        # The filter API requires three parameters, but we only use the third one
        async def event_filter(
            _, _client, update
        ):  # _client is intentionally unused
            # _client parameter is required by the filter API but not used
            if (
                not update
                or not hasattr(update, "from_user")
                or update.from_user is None
            ):
                return False
            if update.from_user.id != user_id:
                return False
            # Accept both photos and documents with image mime type
            return (hasattr(update, "photo") and update.photo) or (
                hasattr(update, "document")
                and update.document
                and update.document.mime_type
                and update.document.mime_type.startswith("image/")
            )

        # Create the filter using the method
        custom_filter = create(event_filter)

        # Add the handler with the custom filter
        handler = client.add_handler(
            MessageHandler(handle_watermark_image_upload, filters=custom_filter),
            group=-1,
        )

        # Handler added

        try:
            # Set a timeout for the upload (60 seconds)
            start_time = time()
            while handler_dict.get(user_id, False):
                # Check if 60 seconds have passed
                if time() - start_time > 60:
                    handler_dict[user_id] = False
                    await edit_message(
                        msg,
                        "⏱️ <b>Upload timed out!</b>\n\nPlease try again.",
                        buttons.build_menu(1),
                    )
                    await asyncio.sleep(3)
                    await update_media_tools_settings(query, "watermark")
                    return
                await asyncio.sleep(0.5)
        except Exception:
            handler_dict[user_id] = False
            await update_media_tools_settings(query, "watermark")
        finally:
            # Always remove the handler, even if there was an exception
            try:
                client.remove_handler(*handler)
                # Handler removed
            except Exception:
                pass

    elif data[2] == "watermark_config" or (
        len(data) > 3 and data[2] == "watermark_config"
    ):
        await query.answer()
        if len(data) > 3:
            # Page number is provided
            try:
                # Format: watermark_config X
                page_no = int(data[3])
                # Update the global variable
                watermark_config_page = page_no
                # Also store it in handler_dict for this user
                handler_dict[f"{user_id}_watermark_page"] = page_no
                await update_media_tools_settings(
                    query, f"watermark_config {page_no}"
                )
            except ValueError:
                # If page number is not a valid integer, use the global variable
                await update_media_tools_settings(
                    query, f"watermark_config {watermark_config_page}"
                )
        else:
            # No page number provided, use the global variable
            # Check if we have a stored page for this user
            stored_page = handler_dict.get(f"{user_id}_watermark_page")
            if stored_page is not None:
                await update_media_tools_settings(
                    query, f"watermark_config {stored_page}"
                )
            else:
                # Use the global variable
                await update_media_tools_settings(
                    query, f"watermark_config {watermark_config_page}"
                )
    elif data[2] == "merge_config" or (len(data) > 3 and data[2] == "merge_config"):
        await query.answer()
        if len(data) > 3:
            # Page number is provided
            try:
                # Format: merge_config X
                page_no = int(data[3])
                # Update the global variable
                merge_config_page = page_no
                await update_media_tools_settings(query, f"merge_config {page_no}")
            except ValueError:
                # If page number is not a valid integer, use the global variable
                await update_media_tools_settings(
                    query, f"merge_config {merge_config_page}"
                )
        else:
            # No page number provided, use the global variable
            await update_media_tools_settings(
                query, f"merge_config {merge_config_page}"
            )
    elif data[2] == "tog":
        await query.answer()

        # Special handling for ADD_PRESERVE_TRACKS and ADD_REPLACE_TRACKS
        # When one is turned on, the other should be turned off
        if data[3] == "ADD_PRESERVE_TRACKS" and data[4] == "t":
            # If preserve is being turned on, turn off replace
            update_user_ldata(user_id, "ADD_PRESERVE_TRACKS", True)
            update_user_ldata(user_id, "ADD_REPLACE_TRACKS", False)
        elif data[3] == "ADD_REPLACE_TRACKS" and data[4] == "t":
            # If replace is being turned on, turn off preserve
            update_user_ldata(user_id, "ADD_REPLACE_TRACKS", True)
            update_user_ldata(user_id, "ADD_PRESERVE_TRACKS", False)
        else:
            # For all other toggles, just set the value directly
            update_user_ldata(user_id, data[3], data[4] == "t")

        # If this is a toggle for MEDIA_TOOLS_ENABLED, update the database
        if data[3] == "MEDIA_TOOLS_ENABLED":
            # Update the Config object
            Config.MEDIA_TOOLS_ENABLED = data[4] == "t"
            # Update the database
            await database.update_config(
                {"MEDIA_TOOLS_ENABLED": Config.MEDIA_TOOLS_ENABLED}
            )

        # Check if a specific return menu is specified in the callback data
        if len(data) > 5:
            # Use the specified return menu
            return_menu = data[5]
            await update_media_tools_settings(query, return_menu)
        elif data[3] in [
            "AUDIO_WATERMARK_ENABLED",
            "SUBTITLE_WATERMARK_ENABLED",
            "WATERMARK_THREADING",
            "WATERMARK_REMOVE_ORIGINAL",
            "IMAGE_WATERMARK_SCALE",
            "IMAGE_WATERMARK_POSITION",
            "IMAGE_WATERMARK_OPACITY",
        ] or (data[3].startswith("WATERMARK_") and data[3] != "WATERMARK_ENABLED"):
            # These are the toggles in the watermark_config menu
            # Check if we have a stored page for this user
            stored_page = handler_dict.get(f"{user_id}_watermark_page")
            if stored_page is not None:
                await update_media_tools_settings(
                    query, f"watermark_config {stored_page}"
                )
            else:
                await update_media_tools_settings(query, "watermark_config")
        elif data[3] in ["WATERMARK_ENABLED", "IMAGE_WATERMARK_ENABLED"]:
            # Main watermark toggles should return to watermark menu
            await update_media_tools_settings(query, "watermark")
        elif data[3].startswith("MERGE_") or data[3] in [
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
        ]:
            await update_media_tools_settings(query, "merge")
        elif data[3].startswith("CONVERT_"):
            if data[3].startswith("CONVERT_VIDEO_"):
                await update_media_tools_settings(query, "convert_video")
            elif data[3].startswith("CONVERT_AUDIO_"):
                await update_media_tools_settings(query, "convert_audio")
            elif data[3].startswith("CONVERT_SUBTITLE_"):
                await update_media_tools_settings(query, "convert_subtitle")
            elif data[3].startswith("CONVERT_DOCUMENT_"):
                await update_media_tools_settings(query, "convert_document")
            elif data[3].startswith("CONVERT_ARCHIVE_"):
                await update_media_tools_settings(query, "convert_archive")
            else:
                await update_media_tools_settings(query, "convert")
        elif data[3].startswith("COMPRESSION_"):
            if data[3] == "COMPRESSION_ENABLED":
                await update_media_tools_settings(query, "compression")
            elif (
                data[3].startswith("COMPRESSION_VIDEO_")
                or data[3].startswith("COMPRESSION_AUDIO_")
                or data[3].startswith("COMPRESSION_IMAGE_")
                or data[3].startswith("COMPRESSION_DOCUMENT_")
                or data[3].startswith("COMPRESSION_SUBTITLE_")
                or data[3].startswith("COMPRESSION_ARCHIVE_")
            ):
                await update_media_tools_settings(query, "compression_config")
            else:
                await update_media_tools_settings(query, "compression")
        elif data[3].startswith("TRIM_"):
            if data[3] == "TRIM_ENABLED":
                await update_media_tools_settings(query, "trim")
            elif (
                data[3]
                in ["TRIM_START_TIME", "TRIM_END_TIME", "TRIM_DELETE_ORIGINAL"]
                or data[3].startswith("TRIM_VIDEO_")
                or data[3].startswith("TRIM_AUDIO_")
                or data[3].startswith("TRIM_IMAGE_")
                or data[3].startswith("TRIM_DOCUMENT_")
                or data[3].startswith("TRIM_SUBTITLE_")
                or data[3].startswith("TRIM_ARCHIVE_")
            ):
                await update_media_tools_settings(query, "trim_config")
            else:
                await update_media_tools_settings(query, "trim")
        elif data[3].startswith("EXTRACT_"):
            if data[3] == "EXTRACT_ENABLED":
                await update_media_tools_settings(query, "extract")
            elif (
                data[3].startswith("EXTRACT_VIDEO_")
                or data[3].startswith("EXTRACT_AUDIO_")
                or data[3].startswith("EXTRACT_SUBTITLE_")
                or data[3].startswith("EXTRACT_ATTACHMENT_")
            ):
                await update_media_tools_settings(query, "extract_config")
            else:
                await update_media_tools_settings(query, "extract")
        elif data[3].startswith("REMOVE_"):
            if data[3] == "REMOVE_ENABLED":
                await update_media_tools_settings(query, "remove")
            elif (
                data[3].startswith("REMOVE_VIDEO_")
                or data[3].startswith("REMOVE_AUDIO_")
                or data[3].startswith("REMOVE_SUBTITLE_")
                or data[3].startswith("REMOVE_ATTACHMENT_")
                or data[3] == "REMOVE_METADATA"
                or data[3] == "REMOVE_DELETE_ORIGINAL"
            ):
                await update_media_tools_settings(query, "remove_config")
            else:
                await update_media_tools_settings(query, "remove")
        elif data[3].startswith("ADD_"):
            if data[3] == "ADD_ENABLED":
                await update_media_tools_settings(query, "add")
            elif data[3] in [
                "ADD_VIDEO_ENABLED",
                "ADD_AUDIO_ENABLED",
                "ADD_SUBTITLE_ENABLED",
                "ADD_ATTACHMENT_ENABLED",
                "ADD_DELETE_ORIGINAL",
                "ADD_PRESERVE_TRACKS",
                "ADD_REPLACE_TRACKS",
            ]:
                # These are the toggles in the add_config menu, so return to add_config
                await update_media_tools_settings(query, "add_config")
            elif data[3].startswith("ADD_VIDEO_"):
                await update_media_tools_settings(query, "add_video_config")
            elif data[3].startswith("ADD_AUDIO_"):
                await update_media_tools_settings(query, "add_audio_config")
            elif data[3].startswith("ADD_SUBTITLE_"):
                await update_media_tools_settings(query, "add_subtitle_config")
            elif data[3].startswith("ADD_ATTACHMENT_"):
                await update_media_tools_settings(query, "add_attachment_config")
            else:
                await update_media_tools_settings(query, "add")
        else:
            await update_media_tools_settings(query)

        await database.update_user_data(user_id)
    elif data[2] == "menu":
        await query.answer()
        # Set a flag if we're handling image watermark settings
        if data[3].startswith("IMAGE_WATERMARK_"):
            query.from_image_settings = True

        # Store the current page number if we're in the watermark config menu
        if data[3].startswith(
            (
                "WATERMARK_",
                "AUDIO_WATERMARK_",
                "SUBTITLE_WATERMARK_",
                "IMAGE_WATERMARK_",
            )
        ):
            # First try to extract page from message text
            if message.text and "Page:" in message.text:
                try:
                    page_info = message.text.split("Page:")[1].strip().split("/")[0]
                    page_no = int(page_info) - 1
                    # Store the page number in handler_dict for this user
                    handler_dict[f"{user_id}_watermark_page"] = page_no
                    # Update the global variable
                    watermark_config_page = page_no
                except (ValueError, IndexError):
                    pass

            # If we couldn't extract from text, use the global variable
            if f"{user_id}_watermark_page" not in handler_dict:
                # For image watermark settings, calculate the correct page
                if data[3].startswith("IMAGE_WATERMARK_"):
                    # Find the page that contains image settings
                    visual_settings_len = 6  # Length of visual_settings array
                    performance_settings_len = (
                        2  # Length of performance_settings array
                    )
                    items_per_page = 10  # From the code

                    # Calculate which page the image settings start on
                    image_settings_start_index = (
                        visual_settings_len + performance_settings_len
                    )
                    image_settings_page = (
                        image_settings_start_index // items_per_page
                    )

                    # Store the page number
                    handler_dict[f"{user_id}_watermark_page"] = image_settings_page
                else:
                    # Use the global variable as fallback
                    handler_dict[f"{user_id}_watermark_page"] = watermark_config_page

        await get_menu(data[3], message, user_id)
    elif data[2] == "set":
        await query.answer()
        buttons = ButtonMaker()

        # Get help text from media_tools_text dictionary
        from bot.helper.ext_utils.help_messages import media_tools_text

        # Format the help text with examples and blockquote
        help_text = media_tools_text.get(
            data[3], f"Send a value for {data[3]}. Timeout: 60 sec"
        )

        # Format the help text with blockquote
        formatted_help_text = f"<blockquote>{help_text}</blockquote>\n\nSend a value for {data[3]}. Timeout: 60 sec"

        # For WATERMARK_PRIORITY, add a note about returning to previous menu
        if data[3] == "WATERMARK_PRIORITY":
            formatted_help_text += "\n\nAfter setting the value, you will be returned to the Set Priority menu."

        # Add back button that returns to the correct menu
        if data[3] == "WATERMARK_PRIORITY":
            # For WATERMARK_PRIORITY, go back to the watermark menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} menu WATERMARK_PRIORITY",
                "footer",
            )
        elif data[3].startswith(
            (
                "WATERMARK_",
                "AUDIO_WATERMARK_",
                "SUBTITLE_WATERMARK_",
                "IMAGE_WATERMARK_",
            )
        ):
            # For all other watermark settings, check if we have a stored page number
            stored_page = handler_dict.get(f"{user_id}_watermark_page")

            if stored_page is not None:
                # Use the stored page number if available
                buttons.data_button(
                    "Back",
                    f"mediatools {user_id} watermark_config {stored_page}",
                    "footer",
                )
            else:
                # If no stored page, use the global variable or calculate it

                # For image watermark settings, check if we have a stored page number
                if data[3].startswith("IMAGE_WATERMARK_"):
                    stored_page = handler_dict.get(f"{user_id}_watermark_page")
                    if stored_page is not None:
                        buttons.data_button(
                            "Back",
                            f"mediatools {user_id} watermark_config {stored_page}",
                            "footer",
                        )
                        return

                # If still no stored page, calculate the page if needed
                if (
                    data[3].startswith("IMAGE_WATERMARK_")
                    and watermark_config_page == 0
                ):
                    # Find the page that contains image settings
                    visual_settings_len = 6  # Length of visual_settings array
                    performance_settings_len = (
                        2  # Length of performance_settings array
                    )
                    items_per_page = 10  # From the code

                    # Calculate which page the image settings start on
                    image_settings_start_index = (
                        visual_settings_len + performance_settings_len
                    )
                    image_settings_page = (
                        image_settings_start_index // items_per_page
                    )

                    buttons.data_button(
                        "Back",
                        f"mediatools {user_id} watermark_config {image_settings_page}",
                        "footer",
                    )
                else:
                    # Use the global variable
                    buttons.data_button(
                        "Back",
                        f"mediatools {user_id} watermark_config {watermark_config_page}",
                        "footer",
                    )
        # Add specific handling for Add feature settings
        elif data[3].startswith("ADD_VIDEO_"):
            # For video add settings, go back to the video add config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} add_video_config",
                "footer",
            )
        elif data[3].startswith("ADD_AUDIO_"):
            # For audio add settings, go back to the audio add config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} add_audio_config",
                "footer",
            )
        elif data[3].startswith("ADD_SUBTITLE_"):
            # For subtitle add settings, go back to the subtitle add config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} add_subtitle_config",
                "footer",
            )
        elif data[3].startswith("ADD_ATTACHMENT_"):
            # For attachment add settings, go back to the attachment add config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} add_attachment_config",
                "footer",
            )
        # Add specific handling for Remove feature settings
        elif data[3].startswith("REMOVE_VIDEO_"):
            # For video remove settings, go back to the video remove config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} remove_video_config",
                "footer",
            )
        elif data[3].startswith("REMOVE_AUDIO_"):
            # For audio remove settings, go back to the audio remove config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} remove_audio_config",
                "footer",
            )
        elif data[3].startswith("REMOVE_SUBTITLE_"):
            # For subtitle remove settings, go back to the subtitle remove config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} remove_subtitle_config",
                "footer",
            )
        elif data[3].startswith("REMOVE_ATTACHMENT_"):
            # For attachment remove settings, go back to the attachment remove config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} remove_attachment_config",
                "footer",
            )
        elif data[3] in [
            "REMOVE_PRIORITY",
            "REMOVE_METADATA",
            "REMOVE_DELETE_ORIGINAL",
            "REMOVE_MAINTAIN_QUALITY",
        ]:
            # For other remove settings, go back to the remove config menu
            buttons.data_button(
                "Back",
                f"mediatools {user_id} remove_config",
                "footer",
            )
        else:
            # For other settings, go back to the specific menu
            buttons.data_button(
                "Back", f"mediatools {user_id} menu {data[3]}", "footer"
            )

        # Check if we're in a task context (using -mt flag)
        is_task_context = False
        if hasattr(message, "reply_markup") and message.reply_markup:
            for row in message.reply_markup.inline_keyboard:
                for btn in row:
                    if btn.text == "Done" and "task_done" in btn.callback_data:
                        is_task_context = True
                        break
                if is_task_context:
                    break

        # Add appropriate buttons based on context
        if is_task_context:
            # In task context, add Done and Cancel buttons
            buttons.data_button("Done", f"mediatools {user_id} task_done", "footer")
            buttons.data_button(
                "Cancel", f"mediatools {user_id} task_cancel", "footer"
            )
        else:
            # In normal context, add Close button
            buttons.data_button("Close", f"mediatools {user_id} close", "footer")

        await edit_message(message, formatted_help_text, buttons.build_menu(1))

        # Set up function to handle user input
        rfunc = partial(get_menu, data[3], message, user_id)
        pfunc = partial(set_option, option=data[3], rfunc=rfunc)
        await event_handler(client, query, pfunc, rfunc)
    elif data[2] == "reset":
        await query.answer()
        if data[3] in user_dict:
            del user_dict[data[3]]
            await database.update_user_data(user_id)
        await get_menu(data[3], message, user_id)
    elif data[2] == "reset_watermark":
        await query.answer("Resetting all watermark settings to default...")
        # Remove all watermark settings from user_dict
        watermark_keys = [
            "WATERMARK_ENABLED",
            "WATERMARK_KEY",
            "WATERMARK_POSITION",
            "WATERMARK_SIZE",
            "WATERMARK_COLOR",
            "WATERMARK_FONT",
            "WATERMARK_PRIORITY",
            "WATERMARK_THREADING",
            "WATERMARK_THREAD_NUMBER",
            "WATERMARK_OPACITY",
            "WATERMARK_REMOVE_ORIGINAL",
            "AUDIO_WATERMARK_ENABLED",
            "AUDIO_WATERMARK_TEXT",
            "AUDIO_WATERMARK_VOLUME",
            "SUBTITLE_WATERMARK_ENABLED",
            "SUBTITLE_WATERMARK_TEXT",
            "SUBTITLE_WATERMARK_STYLE",
            # Image watermark settings
            "IMAGE_WATERMARK_ENABLED",
            "IMAGE_WATERMARK_PATH",
            "IMAGE_WATERMARK_SCALE",
            "IMAGE_WATERMARK_POSITION",
            "IMAGE_WATERMARK_OPACITY",
        ]
        for key in watermark_keys:
            if key in user_dict:
                del user_dict[key]

        # Remove the image watermark from the database
        await database.update_user_doc(user_id, "IMAGE_WATERMARK", None, None)

        # Remove IMAGE_WATERMARK_PATH from user_dict to ensure UI shows "None"
        if "IMAGE_WATERMARK_PATH" in user_dict:
            del user_dict["IMAGE_WATERMARK_PATH"]

        # Explicitly set IMAGE_WATERMARK_PATH to None in user_data to ensure UI shows "None"
        update_user_ldata(user_id, "IMAGE_WATERMARK_PATH", None)

        # Update the user data in the database to persist the changes
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "watermark")
    elif data[2] == "reset_merge":
        await query.answer("Resetting all merge settings to default...")
        # Remove all merge settings from user_dict
        merge_keys = [
            "MERGE_ENABLED",
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
            "MERGE_OUTPUT_FORMAT_VIDEO",
            "MERGE_OUTPUT_FORMAT_AUDIO",
            "MERGE_OUTPUT_FORMAT_IMAGE",
            "MERGE_OUTPUT_FORMAT_DOCUMENT",
            "MERGE_OUTPUT_FORMAT_SUBTITLE",
            "MERGE_IMAGE_MODE",
            "MERGE_IMAGE_COLUMNS",
            "MERGE_IMAGE_QUALITY",
            "MERGE_IMAGE_DPI",
            "MERGE_IMAGE_RESIZE",
            "MERGE_IMAGE_BACKGROUND",
            "MERGE_VIDEO_CODEC",
            "MERGE_VIDEO_QUALITY",
            "MERGE_VIDEO_PRESET",
            "MERGE_VIDEO_CRF",
            "MERGE_VIDEO_PIXEL_FORMAT",
            "MERGE_VIDEO_TUNE",
            "MERGE_VIDEO_FASTSTART",
            "MERGE_AUDIO_CODEC",
            "MERGE_AUDIO_BITRATE",
            "MERGE_AUDIO_CHANNELS",
            "MERGE_AUDIO_SAMPLING",
            "MERGE_AUDIO_VOLUME",
            "MERGE_SUBTITLE_ENCODING",
            "MERGE_SUBTITLE_FONT",
            "MERGE_SUBTITLE_FONT_SIZE",
            "MERGE_SUBTITLE_FONT_COLOR",
            "MERGE_SUBTITLE_BACKGROUND",
            "MERGE_DOCUMENT_PAPER_SIZE",
            "MERGE_DOCUMENT_ORIENTATION",
            "MERGE_DOCUMENT_MARGIN",
            "MERGE_METADATA_TITLE",
            "MERGE_METADATA_AUTHOR",
            "MERGE_METADATA_COMMENT",
            "MERGE_PRIORITY",
            "MERGE_THREADING",
            "MERGE_THREAD_NUMBER",
            "MERGE_REMOVE_ORIGINAL",
        ]
        for key in merge_keys:
            if key in user_dict:
                del user_dict[key]
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "merge")
    elif data[2] == "remove_watermark":
        await query.answer("Setting all watermark settings to None...")
        # Set all watermark settings to None/False
        watermark_keys = [
            "WATERMARK_KEY",
            "WATERMARK_POSITION",
            "WATERMARK_SIZE",
            "WATERMARK_COLOR",
            "WATERMARK_FONT",
            "WATERMARK_OPACITY",
        ]
        update_user_ldata(user_id, "WATERMARK_ENABLED", False)
        update_user_ldata(user_id, "WATERMARK_REMOVE_ORIGINAL", True)
        update_user_ldata(user_id, "AUDIO_WATERMARK_ENABLED", False)
        update_user_ldata(user_id, "AUDIO_WATERMARK_VOLUME", 0.0)
        update_user_ldata(user_id, "SUBTITLE_WATERMARK_ENABLED", False)
        update_user_ldata(user_id, "SUBTITLE_WATERMARK_STYLE", "none")
        # Reset image watermark settings
        update_user_ldata(user_id, "IMAGE_WATERMARK_ENABLED", False)
        update_user_ldata(user_id, "IMAGE_WATERMARK_SCALE", "10")
        update_user_ldata(user_id, "IMAGE_WATERMARK_POSITION", "bottom_right")
        update_user_ldata(user_id, "IMAGE_WATERMARK_OPACITY", 1.0)

        # Remove the image watermark from the database
        await database.update_user_doc(user_id, "IMAGE_WATERMARK", None, None)

        # Remove IMAGE_WATERMARK_PATH from user_dict to ensure UI shows "None"
        if "IMAGE_WATERMARK_PATH" in user_dict:
            del user_dict["IMAGE_WATERMARK_PATH"]

        # Explicitly set IMAGE_WATERMARK_PATH to None in user_data to ensure UI shows "None"
        update_user_ldata(user_id, "IMAGE_WATERMARK_PATH", None)

        # Update the user data in the database to persist the changes
        await database.update_user_data(user_id)

        for key in watermark_keys:
            update_user_ldata(user_id, key, "none")
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "watermark")
    elif data[2] == "remove_merge":
        await query.answer("Setting all merge settings to None...")
        # Set all merge settings to None/False
        merge_keys = [
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
            "MERGE_OUTPUT_FORMAT_VIDEO",
            "MERGE_OUTPUT_FORMAT_AUDIO",
            "MERGE_OUTPUT_FORMAT_IMAGE",
            "MERGE_OUTPUT_FORMAT_DOCUMENT",
            "MERGE_OUTPUT_FORMAT_SUBTITLE",
            "MERGE_IMAGE_MODE",
            "MERGE_IMAGE_COLUMNS",
            "MERGE_IMAGE_QUALITY",
            "MERGE_IMAGE_DPI",
            "MERGE_IMAGE_RESIZE",
            "MERGE_IMAGE_BACKGROUND",
            "MERGE_VIDEO_CODEC",
            "MERGE_VIDEO_QUALITY",
            "MERGE_VIDEO_PRESET",
            "MERGE_VIDEO_CRF",
            "MERGE_VIDEO_PIXEL_FORMAT",
            "MERGE_VIDEO_TUNE",
            "MERGE_VIDEO_FASTSTART",
            "MERGE_AUDIO_CODEC",
            "MERGE_AUDIO_BITRATE",
            "MERGE_AUDIO_CHANNELS",
            "MERGE_AUDIO_SAMPLING",
            "MERGE_AUDIO_VOLUME",
            "MERGE_SUBTITLE_ENCODING",
            "MERGE_SUBTITLE_FONT",
            "MERGE_SUBTITLE_FONT_SIZE",
            "MERGE_SUBTITLE_FONT_COLOR",
            "MERGE_SUBTITLE_BACKGROUND",
            "MERGE_DOCUMENT_PAPER_SIZE",
            "MERGE_DOCUMENT_ORIENTATION",
            "MERGE_DOCUMENT_MARGIN",
            "MERGE_METADATA_TITLE",
            "MERGE_METADATA_AUTHOR",
            "MERGE_METADATA_COMMENT",
            "MERGE_THREAD_NUMBER",
        ]
        update_user_ldata(user_id, "MERGE_ENABLED", False)
        update_user_ldata(user_id, "MERGE_THREADING", False)
        update_user_ldata(user_id, "MERGE_REMOVE_ORIGINAL", False)
        for key in merge_keys:
            if key in [
                "MERGE_VIDEO_CRF",
                "MERGE_IMAGE_COLUMNS",
                "MERGE_IMAGE_QUALITY",
                "MERGE_IMAGE_DPI",
                "MERGE_AUDIO_CHANNELS",
                "MERGE_SUBTITLE_FONT_SIZE",
                "MERGE_DOCUMENT_MARGIN",
            ]:
                update_user_ldata(user_id, key, 0)
            elif key == "MERGE_AUDIO_VOLUME":
                update_user_ldata(user_id, key, 0.0)
            elif key == "MERGE_VIDEO_FASTSTART":
                update_user_ldata(user_id, key, False)
            else:
                update_user_ldata(user_id, key, "none")
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "merge")
    elif data[2] == "reset_trim":
        await query.answer("Resetting all trim settings to default...")
        # Remove all trim settings from user_dict
        trim_keys = [
            "TRIM_ENABLED",
            "TRIM_PRIORITY",
            "TRIM_START_TIME",
            "TRIM_END_TIME",
            "TRIM_VIDEO_ENABLED",
            "TRIM_VIDEO_CODEC",
            "TRIM_VIDEO_PRESET",
            "TRIM_AUDIO_ENABLED",
            "TRIM_AUDIO_CODEC",
            "TRIM_AUDIO_PRESET",
            "TRIM_IMAGE_ENABLED",
            "TRIM_IMAGE_QUALITY",
            "TRIM_DOCUMENT_ENABLED",
            "TRIM_DOCUMENT_START_PAGE",
            "TRIM_DOCUMENT_END_PAGE",
            "TRIM_DOCUMENT_QUALITY",
            "TRIM_SUBTITLE_ENABLED",
            "TRIM_SUBTITLE_ENCODING",
            "TRIM_ARCHIVE_ENABLED",
        ]
        for key in trim_keys:
            if key in user_dict:
                del user_dict[key]
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "trim")

    elif data[2] == "reset_extract":
        await query.answer("Resetting all extract settings to default...")
        # Remove all extract settings from user_dict
        extract_keys = [
            "EXTRACT_ENABLED",
            "EXTRACT_PRIORITY",
            "EXTRACT_VIDEO_ENABLED",
            "EXTRACT_VIDEO_CODEC",
            "EXTRACT_VIDEO_FORMAT",
            "EXTRACT_VIDEO_INDEX",
            "EXTRACT_VIDEO_QUALITY",
            "EXTRACT_VIDEO_PRESET",
            "EXTRACT_VIDEO_BITRATE",
            "EXTRACT_VIDEO_RESOLUTION",
            "EXTRACT_VIDEO_FPS",
            "EXTRACT_AUDIO_ENABLED",
            "EXTRACT_AUDIO_CODEC",
            "EXTRACT_AUDIO_FORMAT",
            "EXTRACT_AUDIO_INDEX",
            "EXTRACT_AUDIO_BITRATE",
            "EXTRACT_AUDIO_CHANNELS",
            "EXTRACT_AUDIO_SAMPLING",
            "EXTRACT_AUDIO_VOLUME",
            "EXTRACT_SUBTITLE_ENABLED",
            "EXTRACT_SUBTITLE_CODEC",
            "EXTRACT_SUBTITLE_FORMAT",
            "EXTRACT_SUBTITLE_INDEX",
            "EXTRACT_SUBTITLE_LANGUAGE",
            "EXTRACT_SUBTITLE_ENCODING",
            "EXTRACT_SUBTITLE_FONT",
            "EXTRACT_SUBTITLE_FONT_SIZE",
            "EXTRACT_ATTACHMENT_ENABLED",
            "EXTRACT_ATTACHMENT_FORMAT",
            "EXTRACT_ATTACHMENT_INDEX",
            "EXTRACT_ATTACHMENT_FILTER",
            "EXTRACT_MAINTAIN_QUALITY",
            "EXTRACT_DELETE_ORIGINAL",
        ]
        for key in extract_keys:
            if key in user_dict:
                del user_dict[key]
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "extract")

    elif data[2] == "reset_remove":
        await query.answer("Resetting all remove settings to default...")
        # Remove all remove settings from user_dict
        remove_keys = [
            "REMOVE_ENABLED",
            "REMOVE_PRIORITY",
            "REMOVE_DELETE_ORIGINAL",
            "REMOVE_METADATA",
            "REMOVE_MAINTAIN_QUALITY",
            # Video remove settings
            "REMOVE_VIDEO_ENABLED",
            "REMOVE_VIDEO_CODEC",
            "REMOVE_VIDEO_FORMAT",
            "REMOVE_VIDEO_INDEX",
            "REMOVE_VIDEO_QUALITY",
            "REMOVE_VIDEO_PRESET",
            "REMOVE_VIDEO_BITRATE",
            "REMOVE_VIDEO_RESOLUTION",
            "REMOVE_VIDEO_FPS",
            # Audio remove settings
            "REMOVE_AUDIO_ENABLED",
            "REMOVE_AUDIO_CODEC",
            "REMOVE_AUDIO_FORMAT",
            "REMOVE_AUDIO_INDEX",
            "REMOVE_AUDIO_BITRATE",
            "REMOVE_AUDIO_CHANNELS",
            "REMOVE_AUDIO_SAMPLING",
            "REMOVE_AUDIO_VOLUME",
            # Subtitle remove settings
            "REMOVE_SUBTITLE_ENABLED",
            "REMOVE_SUBTITLE_CODEC",
            "REMOVE_SUBTITLE_FORMAT",
            "REMOVE_SUBTITLE_INDEX",
            "REMOVE_SUBTITLE_LANGUAGE",
            "REMOVE_SUBTITLE_ENCODING",
            "REMOVE_SUBTITLE_FONT",
            "REMOVE_SUBTITLE_FONT_SIZE",
            # Attachment remove settings
            "REMOVE_ATTACHMENT_ENABLED",
            "REMOVE_ATTACHMENT_FORMAT",
            "REMOVE_ATTACHMENT_INDEX",
            "REMOVE_ATTACHMENT_FILTER",
        ]
        for key in remove_keys:
            if key in user_dict:
                del user_dict[key]
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "remove")

    elif data[2] == "remove_remove":
        await query.answer("Setting all remove settings to None...")
        # Set all remove settings to None/False
        # General settings
        update_user_ldata(user_id, "REMOVE_ENABLED", False)
        update_user_ldata(user_id, "REMOVE_METADATA", False)
        update_user_ldata(user_id, "REMOVE_DELETE_ORIGINAL", True)
        update_user_ldata(user_id, "REMOVE_MAINTAIN_QUALITY", True)

        # Video remove settings
        update_user_ldata(user_id, "REMOVE_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "REMOVE_VIDEO_CODEC", "none")
        update_user_ldata(user_id, "REMOVE_VIDEO_FORMAT", "none")
        update_user_ldata(user_id, "REMOVE_VIDEO_INDEX", None)
        update_user_ldata(user_id, "REMOVE_VIDEO_QUALITY", "none")
        update_user_ldata(user_id, "REMOVE_VIDEO_PRESET", "none")
        update_user_ldata(user_id, "REMOVE_VIDEO_BITRATE", "none")
        update_user_ldata(user_id, "REMOVE_VIDEO_RESOLUTION", "none")
        update_user_ldata(user_id, "REMOVE_VIDEO_FPS", "none")

        # Audio remove settings
        update_user_ldata(user_id, "REMOVE_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "REMOVE_AUDIO_CODEC", "none")
        update_user_ldata(user_id, "REMOVE_AUDIO_FORMAT", "none")
        update_user_ldata(user_id, "REMOVE_AUDIO_INDEX", None)
        update_user_ldata(user_id, "REMOVE_AUDIO_BITRATE", "none")
        update_user_ldata(user_id, "REMOVE_AUDIO_CHANNELS", "none")
        update_user_ldata(user_id, "REMOVE_AUDIO_SAMPLING", "none")
        update_user_ldata(user_id, "REMOVE_AUDIO_VOLUME", "none")

        # Subtitle remove settings
        update_user_ldata(user_id, "REMOVE_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "REMOVE_SUBTITLE_CODEC", "none")
        update_user_ldata(user_id, "REMOVE_SUBTITLE_FORMAT", "none")
        update_user_ldata(user_id, "REMOVE_SUBTITLE_INDEX", None)
        update_user_ldata(user_id, "REMOVE_SUBTITLE_LANGUAGE", "none")
        update_user_ldata(user_id, "REMOVE_SUBTITLE_ENCODING", "none")
        update_user_ldata(user_id, "REMOVE_SUBTITLE_FONT", "none")
        update_user_ldata(user_id, "REMOVE_SUBTITLE_FONT_SIZE", "none")

        # Attachment remove settings
        update_user_ldata(user_id, "REMOVE_ATTACHMENT_ENABLED", False)
        update_user_ldata(user_id, "REMOVE_ATTACHMENT_FORMAT", "none")
        update_user_ldata(user_id, "REMOVE_ATTACHMENT_INDEX", None)
        update_user_ldata(user_id, "REMOVE_ATTACHMENT_FILTER", "none")

        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "remove")

    elif data[2] == "reset_compression":
        await query.answer("Resetting all compression settings to default...")
        # Remove all compression settings from user_dict
        compression_keys = [
            "COMPRESSION_ENABLED",
            "COMPRESSION_PRIORITY",
            "COMPRESSION_VIDEO_ENABLED",
            "COMPRESSION_VIDEO_PRESET",
            "COMPRESSION_VIDEO_CRF",
            "COMPRESSION_VIDEO_CODEC",
            "COMPRESSION_VIDEO_TUNE",
            "COMPRESSION_VIDEO_PIXEL_FORMAT",
            "COMPRESSION_AUDIO_ENABLED",
            "COMPRESSION_AUDIO_PRESET",
            "COMPRESSION_AUDIO_CODEC",
            "COMPRESSION_AUDIO_BITRATE",
            "COMPRESSION_AUDIO_CHANNELS",
            "COMPRESSION_IMAGE_ENABLED",
            "COMPRESSION_IMAGE_PRESET",
            "COMPRESSION_IMAGE_QUALITY",
            "COMPRESSION_IMAGE_RESIZE",
            "COMPRESSION_DOCUMENT_ENABLED",
            "COMPRESSION_DOCUMENT_PRESET",
            "COMPRESSION_DOCUMENT_DPI",
            "COMPRESSION_SUBTITLE_ENABLED",
            "COMPRESSION_SUBTITLE_PRESET",
            "COMPRESSION_SUBTITLE_ENCODING",
            "COMPRESSION_ARCHIVE_ENABLED",
            "COMPRESSION_ARCHIVE_PRESET",
            "COMPRESSION_ARCHIVE_LEVEL",
            "COMPRESSION_ARCHIVE_METHOD",
        ]
        for key in compression_keys:
            if key in user_dict:
                del user_dict[key]
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "compression")

    elif data[2] == "reset_convert":
        await query.answer("Resetting all convert settings to default...")
        # Remove all convert settings from user_dict
        convert_keys = [
            "CONVERT_ENABLED",
            "CONVERT_PRIORITY",
            "CONVERT_DELETE_ORIGINAL",
            "CONVERT_VIDEO_ENABLED",
            "CONVERT_VIDEO_FORMAT",
            "CONVERT_VIDEO_CODEC",
            "CONVERT_VIDEO_QUALITY",
            "CONVERT_VIDEO_CRF",
            "CONVERT_VIDEO_PRESET",
            "CONVERT_VIDEO_RESOLUTION",
            "CONVERT_VIDEO_FPS",
            "CONVERT_VIDEO_MAINTAIN_QUALITY",
            "CONVERT_AUDIO_ENABLED",
            "CONVERT_AUDIO_FORMAT",
            "CONVERT_AUDIO_CODEC",
            "CONVERT_AUDIO_BITRATE",
            "CONVERT_AUDIO_CHANNELS",
            "CONVERT_AUDIO_SAMPLING",
            "CONVERT_AUDIO_VOLUME",
            "CONVERT_SUBTITLE_ENABLED",
            "CONVERT_SUBTITLE_FORMAT",
            "CONVERT_SUBTITLE_ENCODING",
            "CONVERT_SUBTITLE_LANGUAGE",
            "CONVERT_DOCUMENT_ENABLED",
            "CONVERT_DOCUMENT_FORMAT",
            "CONVERT_DOCUMENT_QUALITY",
            "CONVERT_DOCUMENT_DPI",
            "CONVERT_ARCHIVE_ENABLED",
            "CONVERT_ARCHIVE_FORMAT",
            "CONVERT_ARCHIVE_LEVEL",
            "CONVERT_ARCHIVE_METHOD",
        ]
        for key in convert_keys:
            if key in user_dict:
                del user_dict[key]
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "convert")
    elif data[2] == "remove_trim":
        await query.answer("Setting all trim settings to None...")
        # Set all trim settings to None/False
        trim_keys = [
            "TRIM_VIDEO_CODEC",
            "TRIM_VIDEO_PRESET",
            "TRIM_AUDIO_CODEC",
            "TRIM_AUDIO_PRESET",
            "TRIM_IMAGE_QUALITY",
            "TRIM_DOCUMENT_QUALITY",
            "TRIM_SUBTITLE_ENCODING",
        ]
        update_user_ldata(user_id, "TRIM_ENABLED", False)
        update_user_ldata(user_id, "TRIM_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "TRIM_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "TRIM_IMAGE_ENABLED", False)
        update_user_ldata(user_id, "TRIM_DOCUMENT_ENABLED", False)
        update_user_ldata(user_id, "TRIM_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "TRIM_ARCHIVE_ENABLED", False)
        # Set start and end time to default values
        update_user_ldata(user_id, "TRIM_START_TIME", "00:00:00")
        update_user_ldata(user_id, "TRIM_END_TIME", "")
        # Set document page settings to default values
        update_user_ldata(user_id, "TRIM_DOCUMENT_START_PAGE", "1")
        update_user_ldata(user_id, "TRIM_DOCUMENT_END_PAGE", "")
        for key in trim_keys:
            if key not in ["TRIM_DOCUMENT_START_PAGE", "TRIM_DOCUMENT_END_PAGE"]:
                update_user_ldata(user_id, key, "none")
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "trim")

    elif data[2] == "remove_extract":
        await query.answer("Setting all extract settings to None...")
        # Set all extract settings to None/False
        extract_keys = [
            "EXTRACT_VIDEO_CODEC",
            "EXTRACT_VIDEO_FORMAT",
            "EXTRACT_VIDEO_INDEX",
            "EXTRACT_VIDEO_QUALITY",
            "EXTRACT_VIDEO_PRESET",
            "EXTRACT_VIDEO_BITRATE",
            "EXTRACT_VIDEO_RESOLUTION",
            "EXTRACT_VIDEO_FPS",
            "EXTRACT_AUDIO_CODEC",
            "EXTRACT_AUDIO_FORMAT",
            "EXTRACT_AUDIO_INDEX",
            "EXTRACT_AUDIO_BITRATE",
            "EXTRACT_AUDIO_CHANNELS",
            "EXTRACT_AUDIO_SAMPLING",
            "EXTRACT_AUDIO_VOLUME",
            "EXTRACT_SUBTITLE_CODEC",
            "EXTRACT_SUBTITLE_FORMAT",
            "EXTRACT_SUBTITLE_INDEX",
            "EXTRACT_SUBTITLE_LANGUAGE",
            "EXTRACT_SUBTITLE_ENCODING",
            "EXTRACT_SUBTITLE_FONT",
            "EXTRACT_SUBTITLE_FONT_SIZE",
            "EXTRACT_ATTACHMENT_FORMAT",
            "EXTRACT_ATTACHMENT_INDEX",
            "EXTRACT_ATTACHMENT_FILTER",
        ]
        update_user_ldata(user_id, "EXTRACT_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_ATTACHMENT_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_MAINTAIN_QUALITY", True)
        for key in extract_keys:
            update_user_ldata(user_id, key, None)
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "extract")

    elif data[2] == "reset_add":
        await query.answer("Resetting all add settings to default...")
        # Reset all add settings to default
        update_user_ldata(user_id, "ADD_ENABLED", False)
        update_user_ldata(user_id, "ADD_PRIORITY", 7)
        update_user_ldata(user_id, "ADD_DELETE_ORIGINAL", True)
        update_user_ldata(user_id, "ADD_PRESERVE_TRACKS", False)
        update_user_ldata(user_id, "ADD_REPLACE_TRACKS", False)
        update_user_ldata(user_id, "ADD_VIDEO_ENABLED", False)
        # Path flag has been removed
        update_user_ldata(user_id, "ADD_VIDEO_CODEC", "copy")
        update_user_ldata(user_id, "ADD_VIDEO_INDEX", None)
        update_user_ldata(user_id, "ADD_VIDEO_QUALITY", "none")
        update_user_ldata(user_id, "ADD_VIDEO_PRESET", "none")
        update_user_ldata(user_id, "ADD_VIDEO_BITRATE", "none")
        update_user_ldata(user_id, "ADD_VIDEO_RESOLUTION", "none")
        update_user_ldata(user_id, "ADD_VIDEO_FPS", "none")
        update_user_ldata(user_id, "ADD_AUDIO_ENABLED", False)
        # Path flag has been removed
        update_user_ldata(user_id, "ADD_AUDIO_CODEC", "copy")
        update_user_ldata(user_id, "ADD_AUDIO_INDEX", None)
        update_user_ldata(user_id, "ADD_AUDIO_BITRATE", "none")
        update_user_ldata(user_id, "ADD_AUDIO_CHANNELS", "none")
        update_user_ldata(user_id, "ADD_AUDIO_SAMPLING", "none")
        update_user_ldata(user_id, "ADD_AUDIO_VOLUME", "none")
        update_user_ldata(user_id, "ADD_SUBTITLE_ENABLED", False)
        # Path flag has been removed
        update_user_ldata(user_id, "ADD_SUBTITLE_CODEC", "copy")
        update_user_ldata(user_id, "ADD_SUBTITLE_INDEX", None)
        update_user_ldata(user_id, "ADD_SUBTITLE_LANGUAGE", "none")
        update_user_ldata(user_id, "ADD_SUBTITLE_ENCODING", "none")
        update_user_ldata(user_id, "ADD_SUBTITLE_FONT", "none")
        update_user_ldata(user_id, "ADD_SUBTITLE_FONT_SIZE", "none")
        update_user_ldata(user_id, "ADD_ATTACHMENT_ENABLED", False)
        # Path flag has been removed
        update_user_ldata(user_id, "ADD_ATTACHMENT_INDEX", None)
        update_user_ldata(user_id, "ADD_ATTACHMENT_MIMETYPE", "none")
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "add")

    elif data[2] == "remove_add":
        await query.answer("Setting all add settings to None...")
        # Set all add settings to None/False
        add_keys = [
            # Path flags have been removed
            "ADD_VIDEO_CODEC",
            "ADD_VIDEO_INDEX",
            "ADD_VIDEO_QUALITY",
            "ADD_VIDEO_PRESET",
            "ADD_VIDEO_BITRATE",
            "ADD_VIDEO_RESOLUTION",
            "ADD_VIDEO_FPS",
            "ADD_AUDIO_CODEC",
            "ADD_AUDIO_INDEX",
            "ADD_AUDIO_BITRATE",
            "ADD_AUDIO_CHANNELS",
            "ADD_AUDIO_SAMPLING",
            "ADD_AUDIO_VOLUME",
            "ADD_SUBTITLE_CODEC",
            "ADD_SUBTITLE_INDEX",
            "ADD_SUBTITLE_LANGUAGE",
            "ADD_SUBTITLE_ENCODING",
            "ADD_SUBTITLE_FONT",
            "ADD_SUBTITLE_FONT_SIZE",
            "ADD_ATTACHMENT_INDEX",
            "ADD_ATTACHMENT_MIMETYPE",
        ]
        update_user_ldata(user_id, "ADD_ENABLED", False)
        update_user_ldata(user_id, "ADD_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "ADD_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "ADD_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "ADD_ATTACHMENT_ENABLED", False)
        update_user_ldata(user_id, "ADD_DELETE_ORIGINAL", True)
        update_user_ldata(user_id, "ADD_PRESERVE_TRACKS", False)
        update_user_ldata(user_id, "ADD_REPLACE_TRACKS", False)
        for key in add_keys:
            update_user_ldata(user_id, key, None)
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "add")

    elif data[2] == "remove_compression":
        await query.answer("Setting all compression settings to None...")
        # Set all compression settings to None/False
        compression_keys = [
            "COMPRESSION_VIDEO_PRESET",
            "COMPRESSION_VIDEO_CRF",
            "COMPRESSION_VIDEO_CODEC",
            "COMPRESSION_VIDEO_TUNE",
            "COMPRESSION_VIDEO_PIXEL_FORMAT",
            "COMPRESSION_AUDIO_PRESET",
            "COMPRESSION_AUDIO_CODEC",
            "COMPRESSION_AUDIO_BITRATE",
            "COMPRESSION_AUDIO_CHANNELS",
            "COMPRESSION_IMAGE_PRESET",
            "COMPRESSION_IMAGE_QUALITY",
            "COMPRESSION_IMAGE_RESIZE",
            "COMPRESSION_DOCUMENT_PRESET",
            "COMPRESSION_DOCUMENT_DPI",
            "COMPRESSION_SUBTITLE_PRESET",
            "COMPRESSION_SUBTITLE_ENCODING",
            "COMPRESSION_ARCHIVE_PRESET",
            "COMPRESSION_ARCHIVE_LEVEL",
            "COMPRESSION_ARCHIVE_METHOD",
        ]
        update_user_ldata(user_id, "COMPRESSION_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_IMAGE_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_DOCUMENT_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_ARCHIVE_ENABLED", False)
        for key in compression_keys:
            if key in [
                "COMPRESSION_VIDEO_CRF",
                "COMPRESSION_AUDIO_CHANNELS",
                "COMPRESSION_IMAGE_QUALITY",
                "COMPRESSION_DOCUMENT_DPI",
                "COMPRESSION_ARCHIVE_LEVEL",
            ]:
                update_user_ldata(user_id, key, 0)
            else:
                update_user_ldata(user_id, key, "none")
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "compression")

    elif data[2] == "remove_convert":
        await query.answer("Setting all convert settings to None...")
        # Set all convert settings to None/False
        convert_keys = [
            "CONVERT_VIDEO_FORMAT",
            "CONVERT_VIDEO_CODEC",
            "CONVERT_VIDEO_QUALITY",
            "CONVERT_VIDEO_CRF",
            "CONVERT_VIDEO_PRESET",
            "CONVERT_VIDEO_RESOLUTION",
            "CONVERT_VIDEO_FPS",
            "CONVERT_AUDIO_FORMAT",
            "CONVERT_AUDIO_CODEC",
            "CONVERT_AUDIO_BITRATE",
            "CONVERT_AUDIO_CHANNELS",
            "CONVERT_AUDIO_SAMPLING",
            "CONVERT_AUDIO_VOLUME",
            "CONVERT_SUBTITLE_FORMAT",
            "CONVERT_SUBTITLE_ENCODING",
            "CONVERT_SUBTITLE_LANGUAGE",
            "CONVERT_DOCUMENT_FORMAT",
            "CONVERT_DOCUMENT_QUALITY",
            "CONVERT_DOCUMENT_DPI",
            "CONVERT_ARCHIVE_FORMAT",
            "CONVERT_ARCHIVE_LEVEL",
            "CONVERT_ARCHIVE_METHOD",
        ]
        update_user_ldata(user_id, "CONVERT_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_DOCUMENT_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_ARCHIVE_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_VIDEO_MAINTAIN_QUALITY", False)
        update_user_ldata(user_id, "CONVERT_DELETE_ORIGINAL", True)
        for key in convert_keys:
            if key in [
                "CONVERT_VIDEO_CRF",
                "CONVERT_AUDIO_CHANNELS",
                "CONVERT_AUDIO_SAMPLING",
            ]:
                update_user_ldata(user_id, key, 0)
            elif key == "CONVERT_AUDIO_VOLUME":
                update_user_ldata(user_id, key, 0.0)
            else:
                update_user_ldata(user_id, key, "none")
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "convert")
    elif data[2] == "remove_all":
        await query.answer("Setting all media tools settings to None...")
        # Set all media tools settings to None/False
        watermark_keys = [
            "WATERMARK_KEY",
            "WATERMARK_POSITION",
            "WATERMARK_SIZE",
            "WATERMARK_COLOR",
            "WATERMARK_FONT",
            "WATERMARK_OPACITY",
        ]

        # Image watermark settings
        image_watermark_keys = [
            "IMAGE_WATERMARK_PATH",
            "IMAGE_WATERMARK_SCALE",
            "IMAGE_WATERMARK_POSITION",
            "IMAGE_WATERMARK_OPACITY",
        ]
        merge_keys = [
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
            "MERGE_OUTPUT_FORMAT_VIDEO",
            "MERGE_OUTPUT_FORMAT_AUDIO",
            "MERGE_OUTPUT_FORMAT_IMAGE",
            "MERGE_OUTPUT_FORMAT_DOCUMENT",
            "MERGE_OUTPUT_FORMAT_SUBTITLE",
            "MERGE_IMAGE_MODE",
            "MERGE_IMAGE_COLUMNS",
            "MERGE_IMAGE_QUALITY",
            "MERGE_IMAGE_DPI",
            "MERGE_IMAGE_RESIZE",
            "MERGE_IMAGE_BACKGROUND",
            "MERGE_VIDEO_CODEC",
            "MERGE_VIDEO_QUALITY",
            "MERGE_VIDEO_PRESET",
            "MERGE_VIDEO_CRF",
            "MERGE_VIDEO_PIXEL_FORMAT",
            "MERGE_VIDEO_TUNE",
            "MERGE_VIDEO_FASTSTART",
            "MERGE_AUDIO_CODEC",
            "MERGE_AUDIO_BITRATE",
            "MERGE_AUDIO_CHANNELS",
            "MERGE_AUDIO_SAMPLING",
            "MERGE_AUDIO_VOLUME",
            "MERGE_SUBTITLE_ENCODING",
            "MERGE_SUBTITLE_FONT",
            "MERGE_SUBTITLE_FONT_SIZE",
            "MERGE_SUBTITLE_FONT_COLOR",
            "MERGE_SUBTITLE_BACKGROUND",
            "MERGE_DOCUMENT_PAPER_SIZE",
            "MERGE_DOCUMENT_ORIENTATION",
            "MERGE_DOCUMENT_MARGIN",
            "MERGE_METADATA_TITLE",
            "MERGE_METADATA_AUTHOR",
            "MERGE_METADATA_COMMENT",
            "MERGE_THREAD_NUMBER",
        ]
        convert_keys = [
            "CONVERT_VIDEO_FORMAT",
            "CONVERT_VIDEO_CODEC",
            "CONVERT_VIDEO_QUALITY",
            "CONVERT_VIDEO_CRF",
            "CONVERT_VIDEO_PRESET",
            "CONVERT_VIDEO_RESOLUTION",
            "CONVERT_VIDEO_FPS",
            "CONVERT_AUDIO_FORMAT",
            "CONVERT_AUDIO_CODEC",
            "CONVERT_AUDIO_BITRATE",
            "CONVERT_AUDIO_CHANNELS",
            "CONVERT_AUDIO_SAMPLING",
            "CONVERT_AUDIO_VOLUME",
            "CONVERT_SUBTITLE_FORMAT",
            "CONVERT_SUBTITLE_ENCODING",
            "CONVERT_SUBTITLE_LANGUAGE",
            "CONVERT_DOCUMENT_FORMAT",
            "CONVERT_DOCUMENT_QUALITY",
            "CONVERT_DOCUMENT_DPI",
            "CONVERT_ARCHIVE_FORMAT",
            "CONVERT_ARCHIVE_LEVEL",
            "CONVERT_ARCHIVE_METHOD",
        ]
        update_user_ldata(user_id, "WATERMARK_ENABLED", False)
        # Reset image watermark settings
        update_user_ldata(user_id, "IMAGE_WATERMARK_ENABLED", False)
        for key in image_watermark_keys:
            if key == "IMAGE_WATERMARK_OPACITY":
                update_user_ldata(user_id, key, 1.0)
            elif key == "IMAGE_WATERMARK_SCALE":
                update_user_ldata(user_id, key, "10")
            elif key == "IMAGE_WATERMARK_POSITION":
                update_user_ldata(user_id, key, "bottom_right")
            else:
                update_user_ldata(user_id, key, None)

        update_user_ldata(user_id, "MERGE_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_DOCUMENT_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_ARCHIVE_ENABLED", False)
        update_user_ldata(user_id, "CONVERT_VIDEO_MAINTAIN_QUALITY", False)
        update_user_ldata(user_id, "CONVERT_DELETE_ORIGINAL", True)
        update_user_ldata(user_id, "COMPRESSION_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_IMAGE_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_DOCUMENT_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "COMPRESSION_ARCHIVE_ENABLED", False)
        update_user_ldata(user_id, "TRIM_ENABLED", False)
        update_user_ldata(user_id, "TRIM_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "TRIM_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "TRIM_IMAGE_ENABLED", False)
        update_user_ldata(user_id, "TRIM_DOCUMENT_ENABLED", False)
        update_user_ldata(user_id, "TRIM_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "TRIM_ARCHIVE_ENABLED", False)
        update_user_ldata(user_id, "TRIM_START_TIME", "00:00:00")
        update_user_ldata(user_id, "TRIM_END_TIME", "")
        update_user_ldata(user_id, "TRIM_DOCUMENT_START_PAGE", "1")
        update_user_ldata(user_id, "TRIM_DOCUMENT_END_PAGE", "")
        update_user_ldata(user_id, "TRIM_IMAGE_QUALITY", "none")
        update_user_ldata(user_id, "TRIM_DOCUMENT_QUALITY", "none")
        update_user_ldata(user_id, "TRIM_VIDEO_CODEC", "none")
        update_user_ldata(user_id, "TRIM_VIDEO_PRESET", "none")
        update_user_ldata(user_id, "TRIM_AUDIO_CODEC", "none")
        update_user_ldata(user_id, "TRIM_AUDIO_PRESET", "none")
        update_user_ldata(user_id, "TRIM_SUBTITLE_ENCODING", "none")

        # Extract settings
        update_user_ldata(user_id, "EXTRACT_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_ATTACHMENT_ENABLED", False)
        update_user_ldata(user_id, "EXTRACT_MAINTAIN_QUALITY", True)
        update_user_ldata(user_id, "EXTRACT_DELETE_ORIGINAL", True)

        # Add settings
        update_user_ldata(user_id, "ADD_ENABLED", False)
        update_user_ldata(user_id, "ADD_VIDEO_ENABLED", False)
        update_user_ldata(user_id, "ADD_AUDIO_ENABLED", False)
        update_user_ldata(user_id, "ADD_SUBTITLE_ENABLED", False)
        update_user_ldata(user_id, "ADD_ATTACHMENT_ENABLED", False)
        update_user_ldata(user_id, "ADD_DELETE_ORIGINAL", True)
        update_user_ldata(user_id, "ADD_PRESERVE_TRACKS", False)
        update_user_ldata(user_id, "ADD_REPLACE_TRACKS", False)

        # Video extract settings
        update_user_ldata(user_id, "EXTRACT_VIDEO_CODEC", None)
        update_user_ldata(user_id, "EXTRACT_VIDEO_FORMAT", None)
        update_user_ldata(user_id, "EXTRACT_VIDEO_INDEX", None)
        update_user_ldata(user_id, "EXTRACT_VIDEO_QUALITY", None)
        update_user_ldata(user_id, "EXTRACT_VIDEO_PRESET", None)
        update_user_ldata(user_id, "EXTRACT_VIDEO_BITRATE", None)
        update_user_ldata(user_id, "EXTRACT_VIDEO_RESOLUTION", None)
        update_user_ldata(user_id, "EXTRACT_VIDEO_FPS", None)

        # Audio extract settings
        update_user_ldata(user_id, "EXTRACT_AUDIO_CODEC", None)
        update_user_ldata(user_id, "EXTRACT_AUDIO_FORMAT", None)
        update_user_ldata(user_id, "EXTRACT_AUDIO_INDEX", None)
        update_user_ldata(user_id, "EXTRACT_AUDIO_BITRATE", None)
        update_user_ldata(user_id, "EXTRACT_AUDIO_CHANNELS", None)
        update_user_ldata(user_id, "EXTRACT_AUDIO_SAMPLING", None)
        update_user_ldata(user_id, "EXTRACT_AUDIO_VOLUME", None)

        # Subtitle extract settings
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_CODEC", None)
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_FORMAT", None)
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_INDEX", None)
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_LANGUAGE", None)
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_ENCODING", None)
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_FONT", None)
        update_user_ldata(user_id, "EXTRACT_SUBTITLE_FONT_SIZE", None)

        # Attachment extract settings
        update_user_ldata(user_id, "EXTRACT_ATTACHMENT_FORMAT", None)
        update_user_ldata(user_id, "EXTRACT_ATTACHMENT_INDEX", None)
        update_user_ldata(user_id, "EXTRACT_ATTACHMENT_FILTER", None)

        for key in watermark_keys:
            update_user_ldata(user_id, key, "None")

        for key in merge_keys:
            if key in [
                "MERGE_VIDEO_CRF",
                "MERGE_IMAGE_COLUMNS",
                "MERGE_IMAGE_QUALITY",
                "MERGE_IMAGE_DPI",
                "MERGE_AUDIO_CHANNELS",
                "MERGE_SUBTITLE_FONT_SIZE",
                "MERGE_DOCUMENT_MARGIN",
            ]:
                update_user_ldata(user_id, key, 0)
            elif key == "MERGE_AUDIO_VOLUME":
                update_user_ldata(user_id, key, 0.0)
            elif key == "MERGE_VIDEO_FASTSTART":
                update_user_ldata(user_id, key, False)
            else:
                update_user_ldata(user_id, key, "none")

        for key in convert_keys:
            if key in [
                "CONVERT_VIDEO_CRF",
                "CONVERT_AUDIO_CHANNELS",
                "CONVERT_AUDIO_SAMPLING",
            ]:
                update_user_ldata(user_id, key, 0)
            elif key == "CONVERT_AUDIO_VOLUME":
                update_user_ldata(user_id, key, 0.0)
            else:
                update_user_ldata(user_id, key, "none")

        compression_keys = [
            "COMPRESSION_VIDEO_PRESET",
            "COMPRESSION_VIDEO_CRF",
            "COMPRESSION_VIDEO_CODEC",
            "COMPRESSION_VIDEO_TUNE",
            "COMPRESSION_VIDEO_PIXEL_FORMAT",
            "COMPRESSION_AUDIO_PRESET",
            "COMPRESSION_AUDIO_CODEC",
            "COMPRESSION_AUDIO_BITRATE",
            "COMPRESSION_AUDIO_CHANNELS",
            "COMPRESSION_IMAGE_PRESET",
            "COMPRESSION_IMAGE_QUALITY",
            "COMPRESSION_IMAGE_RESIZE",
            "COMPRESSION_DOCUMENT_PRESET",
            "COMPRESSION_DOCUMENT_DPI",
            "COMPRESSION_SUBTITLE_PRESET",
            "COMPRESSION_SUBTITLE_ENCODING",
            "COMPRESSION_ARCHIVE_PRESET",
            "COMPRESSION_ARCHIVE_LEVEL",
            "COMPRESSION_ARCHIVE_METHOD",
            "COMPRESSION_ARCHIVE_PASSWORD",
            "COMPRESSION_ARCHIVE_ALGORITHM",
        ]

        for key in compression_keys:
            if key in [
                "COMPRESSION_VIDEO_CRF",
                "COMPRESSION_AUDIO_CHANNELS",
                "COMPRESSION_IMAGE_QUALITY",
                "COMPRESSION_DOCUMENT_DPI",
                "COMPRESSION_ARCHIVE_LEVEL",
            ]:
                update_user_ldata(user_id, key, 0)
            else:
                update_user_ldata(user_id, key, "none")

        # Handle swap settings
        swap_keys = [
            "SWAP_AUDIO_LANGUAGE_ORDER",
            "SWAP_AUDIO_INDEX_ORDER",
            "SWAP_VIDEO_LANGUAGE_ORDER",
            "SWAP_VIDEO_INDEX_ORDER",
            "SWAP_SUBTITLE_LANGUAGE_ORDER",
            "SWAP_SUBTITLE_INDEX_ORDER",
        ]
        for key in swap_keys:
            update_user_ldata(user_id, key, "none")

        # Set boolean swap settings to False
        swap_bool_keys = [
            "SWAP_ENABLED",
            "SWAP_AUDIO_ENABLED",
            "SWAP_AUDIO_USE_LANGUAGE",
            "SWAP_VIDEO_ENABLED",
            "SWAP_VIDEO_USE_LANGUAGE",
            "SWAP_SUBTITLE_ENABLED",
            "SWAP_SUBTITLE_USE_LANGUAGE",
            "SWAP_REMOVE_ORIGINAL",
        ]
        for key in swap_bool_keys:
            update_user_ldata(user_id, key, False)

        # Set swap priority to default
        update_user_ldata(user_id, "SWAP_PRIORITY", 6)

        # Remove the image watermark from the database
        await database.update_user_doc(user_id, "IMAGE_WATERMARK", None, None)

        # Explicitly set IMAGE_WATERMARK_PATH to None in user_data to ensure UI shows "None"
        update_user_ldata(user_id, "IMAGE_WATERMARK_PATH", None)

        await database.update_user_data(user_id)
        await update_media_tools_settings(query)
    elif data[2] == "reset_swap":
        await query.answer("Resetting all swap settings to default...")
        # Remove all swap settings from user_dict
        swap_keys = [
            "SWAP_ENABLED",
            "SWAP_PRIORITY",
            "SWAP_REMOVE_ORIGINAL",
            "SWAP_AUDIO_ENABLED",
            "SWAP_AUDIO_USE_LANGUAGE",
            "SWAP_AUDIO_LANGUAGE_ORDER",
            "SWAP_AUDIO_INDEX_ORDER",
            "SWAP_VIDEO_ENABLED",
            "SWAP_VIDEO_USE_LANGUAGE",
            "SWAP_VIDEO_LANGUAGE_ORDER",
            "SWAP_VIDEO_INDEX_ORDER",
            "SWAP_SUBTITLE_ENABLED",
            "SWAP_SUBTITLE_USE_LANGUAGE",
            "SWAP_SUBTITLE_LANGUAGE_ORDER",
            "SWAP_SUBTITLE_INDEX_ORDER",
        ]
        for key in swap_keys:
            if key in user_dict:
                del user_dict[key]
        # Update the user data in the database to persist the changes
        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "swap")
    elif data[2] == "reset_all":
        await query.answer("Resetting all media tools settings to default...")
        # Remove all media tools settings from user_dict
        media_tools_keys = [
            "WATERMARK_ENABLED",
            "WATERMARK_KEY",
            "WATERMARK_POSITION",
            "WATERMARK_SIZE",
            "WATERMARK_COLOR",
            "WATERMARK_FONT",
            "WATERMARK_OPACITY",
            "WATERMARK_PRIORITY",
            "WATERMARK_THREADING",
            "IMAGE_WATERMARK_ENABLED",
            "IMAGE_WATERMARK_SCALE",
            "IMAGE_WATERMARK_POSITION",
            "IMAGE_WATERMARK_OPACITY",
            "MERGE_ENABLED",
            "CONCAT_DEMUXER_ENABLED",
            "FILTER_COMPLEX_ENABLED",
            "MERGE_OUTPUT_FORMAT_VIDEO",
            "MERGE_OUTPUT_FORMAT_AUDIO",
            "MERGE_PRIORITY",
            "MERGE_THREADING",
            "CONVERT_ENABLED",
            "CONVERT_PRIORITY",
            "CONVERT_VIDEO_ENABLED",
            "CONVERT_VIDEO_FORMAT",
            "CONVERT_VIDEO_CODEC",
            "CONVERT_VIDEO_QUALITY",
            "CONVERT_VIDEO_CRF",
            "CONVERT_VIDEO_PRESET",
            "CONVERT_VIDEO_MAINTAIN_QUALITY",
            "CONVERT_AUDIO_ENABLED",
            "CONVERT_AUDIO_FORMAT",
            "CONVERT_AUDIO_CODEC",
            "CONVERT_AUDIO_BITRATE",
            "CONVERT_AUDIO_CHANNELS",
            "CONVERT_AUDIO_SAMPLING",
            "CONVERT_AUDIO_VOLUME",
            "COMPRESSION_ENABLED",
            "COMPRESSION_PRIORITY",
            "COMPRESSION_VIDEO_ENABLED",
            "COMPRESSION_VIDEO_PRESET",
            "COMPRESSION_VIDEO_CRF",
            "COMPRESSION_VIDEO_CODEC",
            "COMPRESSION_VIDEO_TUNE",
            "COMPRESSION_VIDEO_PIXEL_FORMAT",
            "COMPRESSION_AUDIO_ENABLED",
            "COMPRESSION_AUDIO_PRESET",
            "COMPRESSION_AUDIO_CODEC",
            "COMPRESSION_AUDIO_BITRATE",
            "COMPRESSION_AUDIO_CHANNELS",
            "COMPRESSION_IMAGE_ENABLED",
            "COMPRESSION_IMAGE_PRESET",
            "COMPRESSION_IMAGE_QUALITY",
            "COMPRESSION_IMAGE_RESIZE",
            "COMPRESSION_DOCUMENT_ENABLED",
            "COMPRESSION_DOCUMENT_PRESET",
            "COMPRESSION_DOCUMENT_DPI",
            "COMPRESSION_SUBTITLE_ENABLED",
            "COMPRESSION_SUBTITLE_PRESET",
            "COMPRESSION_SUBTITLE_ENCODING",
            "COMPRESSION_ARCHIVE_ENABLED",
            "COMPRESSION_ARCHIVE_PRESET",
            "COMPRESSION_ARCHIVE_LEVEL",
            "COMPRESSION_ARCHIVE_METHOD",
            "COMPRESSION_ARCHIVE_PASSWORD",
            "COMPRESSION_ARCHIVE_ALGORITHM",
            "TRIM_ENABLED",
            "TRIM_PRIORITY",
            "TRIM_START_TIME",
            "TRIM_END_TIME",
            "TRIM_VIDEO_ENABLED",
            "TRIM_VIDEO_CODEC",
            "TRIM_VIDEO_PRESET",
            "TRIM_AUDIO_ENABLED",
            "TRIM_AUDIO_CODEC",
            "TRIM_AUDIO_PRESET",
            "TRIM_IMAGE_ENABLED",
            "TRIM_IMAGE_QUALITY",
            "TRIM_DOCUMENT_ENABLED",
            "TRIM_DOCUMENT_START_PAGE",
            "TRIM_DOCUMENT_END_PAGE",
            "TRIM_DOCUMENT_QUALITY",
            "TRIM_SUBTITLE_ENABLED",
            "TRIM_SUBTITLE_ENCODING",
            "TRIM_ARCHIVE_ENABLED",
            "EXTRACT_ENABLED",
            "EXTRACT_PRIORITY",
            "EXTRACT_VIDEO_ENABLED",
            "EXTRACT_VIDEO_CODEC",
            "EXTRACT_VIDEO_FORMAT",
            "EXTRACT_VIDEO_INDEX",
            "EXTRACT_VIDEO_QUALITY",
            "EXTRACT_VIDEO_PRESET",
            "EXTRACT_VIDEO_BITRATE",
            "EXTRACT_VIDEO_RESOLUTION",
            "EXTRACT_VIDEO_FPS",
            "EXTRACT_AUDIO_ENABLED",
            "EXTRACT_AUDIO_CODEC",
            "EXTRACT_AUDIO_FORMAT",
            "EXTRACT_AUDIO_INDEX",
            "EXTRACT_AUDIO_BITRATE",
            "EXTRACT_AUDIO_CHANNELS",
            "EXTRACT_AUDIO_SAMPLING",
            "EXTRACT_AUDIO_VOLUME",
            "EXTRACT_SUBTITLE_ENABLED",
            "EXTRACT_SUBTITLE_CODEC",
            "EXTRACT_SUBTITLE_FORMAT",
            "EXTRACT_SUBTITLE_INDEX",
            "EXTRACT_SUBTITLE_LANGUAGE",
            "EXTRACT_SUBTITLE_ENCODING",
            "EXTRACT_SUBTITLE_FONT",
            "EXTRACT_SUBTITLE_FONT_SIZE",
            "EXTRACT_ATTACHMENT_ENABLED",
            "EXTRACT_ATTACHMENT_FORMAT",
            "EXTRACT_ATTACHMENT_INDEX",
            "EXTRACT_ATTACHMENT_FILTER",
            "EXTRACT_MAINTAIN_QUALITY",
            "EXTRACT_DELETE_ORIGINAL",
            "ADD_ENABLED",
            "ADD_PRIORITY",
            "ADD_VIDEO_ENABLED",
            "ADD_VIDEO_PATH",
            "ADD_VIDEO_CODEC",
            "ADD_VIDEO_INDEX",
            "ADD_VIDEO_QUALITY",
            "ADD_VIDEO_PRESET",
            "ADD_VIDEO_BITRATE",
            "ADD_VIDEO_RESOLUTION",
            "ADD_VIDEO_FPS",
            "ADD_AUDIO_ENABLED",
            "ADD_AUDIO_PATH",
            "ADD_AUDIO_CODEC",
            "ADD_AUDIO_INDEX",
            "ADD_AUDIO_BITRATE",
            "ADD_AUDIO_CHANNELS",
            "ADD_AUDIO_SAMPLING",
            "ADD_AUDIO_VOLUME",
            "ADD_SUBTITLE_ENABLED",
            "ADD_SUBTITLE_PATH",
            "ADD_SUBTITLE_CODEC",
            "ADD_SUBTITLE_INDEX",
            "ADD_SUBTITLE_LANGUAGE",
            "ADD_SUBTITLE_ENCODING",
            "ADD_SUBTITLE_FONT",
            "ADD_SUBTITLE_FONT_SIZE",
            "ADD_ATTACHMENT_ENABLED",
            "ADD_ATTACHMENT_PATH",
            "ADD_ATTACHMENT_INDEX",
            "ADD_ATTACHMENT_MIMETYPE",
            "ADD_DELETE_ORIGINAL",
            "SWAP_ENABLED",
            "SWAP_PRIORITY",
            "SWAP_REMOVE_ORIGINAL",
            "SWAP_AUDIO_ENABLED",
            "SWAP_AUDIO_USE_LANGUAGE",
            "SWAP_AUDIO_LANGUAGE_ORDER",
            "SWAP_AUDIO_INDEX_ORDER",
            "SWAP_VIDEO_ENABLED",
            "SWAP_VIDEO_USE_LANGUAGE",
            "SWAP_VIDEO_LANGUAGE_ORDER",
            "SWAP_VIDEO_INDEX_ORDER",
            "SWAP_SUBTITLE_ENABLED",
            "SWAP_SUBTITLE_USE_LANGUAGE",
            "SWAP_SUBTITLE_LANGUAGE_ORDER",
            "SWAP_SUBTITLE_INDEX_ORDER",
            "MEDIA_TOOLS_PRIORITY",
        ]
        for key in media_tools_keys:
            if key in user_dict:
                del user_dict[key]

        # Explicitly set IMAGE_WATERMARK_PATH to None in user_data to ensure UI shows "None"
        update_user_ldata(user_id, "IMAGE_WATERMARK_PATH", None)

        # Remove the image watermark from the database
        await database.update_user_doc(user_id, "IMAGE_WATERMARK", None, None)

        # Update the user data in the database to persist the changes
        await database.update_user_data(user_id)

        # Return to the main menu
        await update_media_tools_settings(query)
    elif data[2] == "remove_swap":
        await query.answer("Setting all swap settings to None...")
        # Set all swap settings to None/False
        swap_keys = [
            "SWAP_AUDIO_LANGUAGE_ORDER",
            "SWAP_AUDIO_INDEX_ORDER",
            "SWAP_VIDEO_LANGUAGE_ORDER",
            "SWAP_VIDEO_INDEX_ORDER",
            "SWAP_SUBTITLE_LANGUAGE_ORDER",
            "SWAP_SUBTITLE_INDEX_ORDER",
        ]
        for key in swap_keys:
            update_user_ldata(user_id, key, "none")

        # Set boolean settings to False
        bool_keys = [
            "SWAP_ENABLED",
            "SWAP_AUDIO_ENABLED",
            "SWAP_AUDIO_USE_LANGUAGE",
            "SWAP_VIDEO_ENABLED",
            "SWAP_VIDEO_USE_LANGUAGE",
            "SWAP_SUBTITLE_ENABLED",
            "SWAP_SUBTITLE_USE_LANGUAGE",
            "SWAP_REMOVE_ORIGINAL",
        ]
        for key in bool_keys:
            update_user_ldata(user_id, key, False)

        # Set priority to default
        update_user_ldata(user_id, "SWAP_PRIORITY", 6)

        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "swap")
    elif data[2] == "toggle_concat_filter":
        # Toggle between concat demuxer and filter complex
        toggle_mode = data[3]  # 'both', 'concat', or 'filter'

        if toggle_mode == "both":
            # Enable both
            update_user_ldata(user_id, "CONCAT_DEMUXER_ENABLED", True)
            update_user_ldata(user_id, "FILTER_COMPLEX_ENABLED", True)
            await query.answer("Concat & Filter: BOTH ON")
        elif toggle_mode == "concat":
            # Enable only concat
            update_user_ldata(user_id, "CONCAT_DEMUXER_ENABLED", True)
            update_user_ldata(user_id, "FILTER_COMPLEX_ENABLED", False)
            await query.answer("Concat & Filter: CONCAT ONLY")
        elif toggle_mode == "filter":
            # Enable only filter
            update_user_ldata(user_id, "CONCAT_DEMUXER_ENABLED", False)
            update_user_ldata(user_id, "FILTER_COMPLEX_ENABLED", True)
            await query.answer("Concat & Filter: FILTER ONLY")
        else:
            # Fallback - enable both
            update_user_ldata(user_id, "CONCAT_DEMUXER_ENABLED", True)
            update_user_ldata(user_id, "FILTER_COMPLEX_ENABLED", True)
            await query.answer("Concat & Filter: BOTH ON")

        await database.update_user_data(user_id)
        await update_media_tools_settings(query, "merge")


# This function has been replaced by the implementation at line ~10014


async def add_media_tools_button_to_bot_settings(buttons):
    """Add Media Tools button to bot settings."""

    # Only add the Media Tools button if media tools are enabled
    if is_media_tool_enabled("mediatools"):
        buttons.data_button("Media Tools", "botset mediatools")

    return buttons


async def get_watermark_settings(user_id):
    """Get watermark settings for a user.

    This function retrieves all watermark settings for a user, including text and image watermark settings.

    Args:
        user_id: The user ID

    Returns:
        tuple: A tuple containing all watermark settings
    """
    user_dict = user_data.get(user_id, {})

    # Text watermark settings
    watermark_enabled = user_dict.get("WATERMARK_ENABLED", False)
    if not watermark_enabled and Config.WATERMARK_ENABLED:
        watermark_enabled = Config.WATERMARK_ENABLED

    watermark_key = user_dict.get("WATERMARK_KEY", "none")
    if watermark_key == "none" and Config.WATERMARK_KEY:
        watermark_key = Config.WATERMARK_KEY

    watermark_position = user_dict.get("WATERMARK_POSITION", "none")
    if watermark_position == "none" and Config.WATERMARK_POSITION:
        watermark_position = Config.WATERMARK_POSITION
    elif watermark_position == "none":
        watermark_position = "top_left"

    watermark_size = user_dict.get("WATERMARK_SIZE", "none")
    if watermark_size == "none" and Config.WATERMARK_SIZE:
        watermark_size = Config.WATERMARK_SIZE
    elif watermark_size == "none":
        watermark_size = 20

    watermark_color = user_dict.get("WATERMARK_COLOR", "none")
    if watermark_color == "none" and Config.WATERMARK_COLOR:
        watermark_color = Config.WATERMARK_COLOR
    elif watermark_color == "none":
        watermark_color = "white"

    watermark_font = user_dict.get("WATERMARK_FONT", "none")
    if watermark_font == "none" and Config.WATERMARK_FONT:
        watermark_font = Config.WATERMARK_FONT
    elif watermark_font == "none":
        watermark_font = "default.otf"

    watermark_opacity = user_dict.get("WATERMARK_OPACITY", None)
    if watermark_opacity is None and hasattr(Config, "WATERMARK_OPACITY"):
        watermark_opacity = Config.WATERMARK_OPACITY
    elif watermark_opacity is None:
        watermark_opacity = 1.0

    watermark_remove_original = user_dict.get("WATERMARK_REMOVE_ORIGINAL", None)
    if watermark_remove_original is None and hasattr(
        Config, "WATERMARK_REMOVE_ORIGINAL"
    ):
        watermark_remove_original = Config.WATERMARK_REMOVE_ORIGINAL
    elif watermark_remove_original is None:
        watermark_remove_original = True

    watermark_threading = user_dict.get("WATERMARK_THREADING", None)
    if watermark_threading is None and hasattr(Config, "WATERMARK_THREADING"):
        watermark_threading = Config.WATERMARK_THREADING
    elif watermark_threading is None:
        watermark_threading = True

    watermark_thread_number = user_dict.get("WATERMARK_THREAD_NUMBER", None)
    if watermark_thread_number is None and hasattr(
        Config, "WATERMARK_THREAD_NUMBER"
    ):
        watermark_thread_number = Config.WATERMARK_THREAD_NUMBER
    elif watermark_thread_number is None:
        watermark_thread_number = 4

    # Audio watermark settings
    audio_watermark_enabled = user_dict.get("AUDIO_WATERMARK_ENABLED", False)
    if not audio_watermark_enabled and hasattr(Config, "AUDIO_WATERMARK_ENABLED"):
        audio_watermark_enabled = Config.AUDIO_WATERMARK_ENABLED

    audio_watermark_text = user_dict.get("AUDIO_WATERMARK_TEXT", "")
    if not audio_watermark_text and hasattr(Config, "AUDIO_WATERMARK_TEXT"):
        audio_watermark_text = Config.AUDIO_WATERMARK_TEXT
    elif not audio_watermark_text:
        audio_watermark_text = watermark_key  # Use the regular watermark text

    audio_watermark_volume = user_dict.get("AUDIO_WATERMARK_VOLUME", None)
    if audio_watermark_volume is None and hasattr(Config, "AUDIO_WATERMARK_VOLUME"):
        audio_watermark_volume = Config.AUDIO_WATERMARK_VOLUME
    elif audio_watermark_volume is None:
        audio_watermark_volume = 0.3

    # Subtitle watermark settings
    subtitle_watermark_enabled = user_dict.get("SUBTITLE_WATERMARK_ENABLED", False)
    if not subtitle_watermark_enabled and hasattr(
        Config, "SUBTITLE_WATERMARK_ENABLED"
    ):
        subtitle_watermark_enabled = Config.SUBTITLE_WATERMARK_ENABLED

    subtitle_watermark_text = user_dict.get("SUBTITLE_WATERMARK_TEXT", "")
    if not subtitle_watermark_text and hasattr(Config, "SUBTITLE_WATERMARK_TEXT"):
        subtitle_watermark_text = Config.SUBTITLE_WATERMARK_TEXT
    elif not subtitle_watermark_text:
        subtitle_watermark_text = watermark_key  # Use the regular watermark text

    subtitle_watermark_style = user_dict.get("SUBTITLE_WATERMARK_STYLE", "")
    if not subtitle_watermark_style and hasattr(Config, "SUBTITLE_WATERMARK_STYLE"):
        subtitle_watermark_style = Config.SUBTITLE_WATERMARK_STYLE
    elif not subtitle_watermark_style:
        subtitle_watermark_style = "normal"

    # Image watermark settings
    image_watermark_enabled = user_dict.get("IMAGE_WATERMARK_ENABLED", False)
    if not image_watermark_enabled and hasattr(Config, "IMAGE_WATERMARK_ENABLED"):
        image_watermark_enabled = Config.IMAGE_WATERMARK_ENABLED

    image_watermark_scale = user_dict.get("IMAGE_WATERMARK_SCALE", None)
    if image_watermark_scale is None and hasattr(Config, "IMAGE_WATERMARK_SCALE"):
        image_watermark_scale = Config.IMAGE_WATERMARK_SCALE
    elif image_watermark_scale is None:
        image_watermark_scale = 10

    image_watermark_position = user_dict.get("IMAGE_WATERMARK_POSITION", "")
    if not image_watermark_position and hasattr(Config, "IMAGE_WATERMARK_POSITION"):
        image_watermark_position = Config.IMAGE_WATERMARK_POSITION
    elif not image_watermark_position:
        image_watermark_position = "bottom_right"

    image_watermark_opacity = user_dict.get("IMAGE_WATERMARK_OPACITY", None)
    if image_watermark_opacity is None and hasattr(
        Config, "IMAGE_WATERMARK_OPACITY"
    ):
        image_watermark_opacity = Config.IMAGE_WATERMARK_OPACITY
    elif image_watermark_opacity is None:
        image_watermark_opacity = 1.0

    # Get the image watermark path from the database
    image_watermark_path = await get_image_watermark_path(user_id)
    if image_watermark_path == "none" and hasattr(Config, "IMAGE_WATERMARK_PATH"):
        image_watermark_path = Config.IMAGE_WATERMARK_PATH

    return (
        watermark_enabled,
        watermark_key,
        watermark_position,
        watermark_size,
        watermark_color,
        watermark_font,
        watermark_opacity,
        watermark_remove_original,
        watermark_threading,
        watermark_thread_number,
        audio_watermark_enabled,
        audio_watermark_text,
        audio_watermark_volume,
        subtitle_watermark_enabled,
        subtitle_watermark_text,
        subtitle_watermark_style,
        image_watermark_enabled,
        image_watermark_path,
        image_watermark_scale,
        image_watermark_position,
        image_watermark_opacity,
    )


async def get_image_watermark_path(user_id):
    """Get the image watermark path for a user.

    This function retrieves the image watermark from the database and saves it to a temporary file.
    The path to the temporary file is returned. The implementation is similar to how thumbnails
    are handled in leech settings.

    It first checks if the user has an image watermark. If not, it falls back to the owner's watermark.

    Args:
        user_id: The user ID

    Returns:
        str: Path to the temporary image watermark file, or "none" if not found
    """
    # Check if the database is available and connection is valid
    if database.db is None:
        # If no database, check if owner has a static path configured
        if hasattr(Config, "IMAGE_WATERMARK_PATH") and Config.IMAGE_WATERMARK_PATH:
            return Config.IMAGE_WATERMARK_PATH
        return "none"

    try:
        # Ensure database connection is valid before attempting to use it
        await database.ensure_connection()

        # Check if connection is still invalid after ensure_connection
        if database.db is None or database._return:
            # If database connection failed, check if owner has a static path configured
            if (
                hasattr(Config, "IMAGE_WATERMARK_PATH")
                and Config.IMAGE_WATERMARK_PATH
            ):
                return Config.IMAGE_WATERMARK_PATH
            return "none"

        # First check if the user has an image watermark in the database
        user_data = await database.db.users.find_one(
            {"_id": user_id}, {"IMAGE_WATERMARK": 1}
        )
        if user_data and "IMAGE_WATERMARK" in user_data:
            # User has an image watermark, create a temporary file
            temp_dir = f"{os.getcwd()}/temp/watermarks"
            await makedirs(temp_dir, exist_ok=True)
            temp_path = f"{temp_dir}/{user_id}_{int(time())}.png"

            try:
                # Write the user's image data to the temporary file
                async with aiopen(temp_path, "wb") as f:
                    await f.write(user_data["IMAGE_WATERMARK"])
                return temp_path
            except Exception:
                pass
                # Fall through to check for owner's watermark

        # If user doesn't have a watermark or there was an error, check for owner's watermark
        if hasattr(Config, "OWNER_ID"):
            owner_id = Config.OWNER_ID
            # Check if owner has an image watermark in the database
            owner_data = await database.db.users.find_one(
                {"_id": owner_id}, {"IMAGE_WATERMARK": 1}
            )
            if owner_data and "IMAGE_WATERMARK" in owner_data:
                # Owner has an image watermark, create a temporary file
                temp_dir = f"{os.getcwd()}/temp/watermarks"
                await makedirs(temp_dir, exist_ok=True)
                temp_path = f"{temp_dir}/owner_{int(time())}.png"

                try:
                    # Write the owner's image data to the temporary file
                    async with aiopen(temp_path, "wb") as f:
                        await f.write(owner_data["IMAGE_WATERMARK"])
                    return temp_path
                except Exception:
                    pass

    except Exception as e:
        # Log the database error but don't fail the entire operation
        LOGGER.warning(f"Database error in get_image_watermark_path: {e}")
        # Fall through to check for static path

    # If neither user nor owner has a watermark in the database, check for static path
    if hasattr(Config, "IMAGE_WATERMARK_PATH") and Config.IMAGE_WATERMARK_PATH:
        return Config.IMAGE_WATERMARK_PATH

    # No watermark found
    return "none"


@new_task
async def handle_watermark_image_upload(_, message):
    """Handle the upload of a watermark image

    This function handles the upload of a watermark image from the user or owner.
    It stores the image in the database and enables image watermarking.
    The implementation is similar to how thumbnails are handled in leech settings.

    User uploads from media_tools.py are used with priority, while owner uploads
    from bot_settings.py serve as fallbacks for all users.
    """
    user_id = message.from_user.id

    # Check if the user is in the handler_dict (waiting for an image upload)
    if user_id not in handler_dict or not handler_dict[user_id]:
        return

    # Check if this upload was initiated from bot_settings
    from_bot_settings = handler_dict.get(f"{user_id}_from_bot_settings", False)
    # Store this flag in a variable for later use
    message.from_bot_settings = from_bot_settings

    # Determine if this is an owner upload (from bot_settings) or user upload (from media_tools)
    is_owner_upload = (
        from_bot_settings
        and hasattr(Config, "OWNER_ID")
        and user_id == Config.OWNER_ID
    )

    # Mark that we've received the upload
    handler_dict[user_id] = False

    # Check if the message contains a photo or document
    if message.photo:
        # For photos, get the largest photo (last in the list)
        temp_path = await message.download()
        # Delete the message with the photo immediately
        await delete_message(message)
    elif (
        message.document
        and message.document.mime_type
        and message.document.mime_type.startswith("image/")
    ):
        # For image documents, download them
        temp_path = await message.download()
        # Delete the message with the document immediately
        await delete_message(message)
    else:
        error_msg = await send_message(
            message.chat.id, "❌ Please send an image file for the watermark."
        )
        # Auto-delete the error message after 5 minutes
        # We don't need to await this task, but we should store a reference to avoid warnings
        # The task will be garbage collected when it completes
        create_task(auto_delete_message(error_msg, time=300))  # noqa

        # Return to the appropriate menu after showing the error
        await asyncio.sleep(2)  # Wait a moment for the user to see the error
        if hasattr(message, "from_bot_settings") and message.from_bot_settings:
            # Return to bot_settings watermark menu
            from bot.modules.bot_settings import update_buttons

            await update_buttons(message, "mediatools_watermark")
        else:
            # Create a new message with the watermark menu
            # We can't use update_media_tools_settings directly because it expects a CallbackQuery
            buttons = ButtonMaker()
            buttons.data_button(
                "Text Watermark", f"mediatools {user_id} watermark_text"
            )
            buttons.data_button(
                "Image Watermark", f"mediatools {user_id} watermark_image"
            )
            buttons.data_button(
                "Audio Watermark", f"mediatools {user_id} watermark_audio"
            )
            buttons.data_button(
                "Subtitle Watermark", f"mediatools {user_id} watermark_subtitle"
            )
            buttons.data_button(
                "Configure", f"mediatools {user_id} watermark_config 0"
            )
            buttons.data_button("Reset All", f"mediatools {user_id} reset_watermark")
            buttons.data_button(
                "Remove All", f"mediatools {user_id} remove_watermark"
            )
            buttons.data_button("Back", f"mediatools {user_id} back", "footer")
            buttons.data_button("Close", f"mediatools {user_id} close", "footer")

            # Send a new message with the watermark menu
            await send_message(
                message.chat.id,
                "✅ <b>Watermark Settings</b>\n\nChoose an option to configure watermark settings.",
                buttons.build_menu(2),
            )
        return

    try:
        # Check file size before processing
        file_size = os.path.getsize(temp_path)
        if file_size > 5 * 1024 * 1024:  # 5MB limit
            # If image is too large, resize it
            try:
                if PIL_AVAILABLE:
                    img = Image.open(temp_path)
                else:
                    raise ImportError("PIL not available")

                # Get original dimensions
                width, height = img.size

                # Calculate new dimensions while maintaining aspect ratio
                max_size = 1024  # Maximum dimension
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))

                # Resize the image
                img = img.resize(
                    (new_width, new_height),
                    getattr(Image, "LANCZOS", Image.ANTIALIAS),
                )

                # Save the resized image
                img.save(temp_path, optimize=True, quality=85)

                # Get new file size
                file_size = os.path.getsize(temp_path)

                # Update dimensions for the message
                width, height = new_width, new_height
                img_info = f"Dimensions: {width}x{height} (resized)"
            except Exception:
                await send_message(
                    message,
                    f"❌ Error: Image is too large ({get_readable_file_size(file_size)}) and could not be resized. Please upload a smaller image (< 5MB).",
                )
                return
        else:
            # Get image dimensions for smaller images
            try:
                if PIL_AVAILABLE:
                    img = Image.open(temp_path)
                    width, height = img.size
                    img_info = f"Dimensions: {width}x{height}"
                else:
                    img_info = "Dimensions: unknown (PIL not available)"
            except Exception:
                img_info = ""

        # Read the image file into binary data
        async with aiopen(temp_path, "rb") as img_file:
            img_data = await img_file.read()

        # Store the image in the database
        if is_owner_upload:
            # If this is an owner upload from bot_settings, update the owner's document
            # This will be used as a fallback for all users
            owner_id = Config.OWNER_ID
            await database.update_user_doc(owner_id, "IMAGE_WATERMARK", "", img_data)

            # Also update the Config.IMAGE_WATERMARK_PATH to indicate we have an owner watermark
            Config.IMAGE_WATERMARK_PATH = "Added"

            # Update the database config
            await database.update_config({"IMAGE_WATERMARK_PATH": "Added"})

            # Enable image watermark for the owner
            update_user_ldata(owner_id, "IMAGE_WATERMARK_ENABLED", True)

            # Update the database
            await database.update_user_data(owner_id)

            # Create confirmation message for owner
            msg = (
                f"✅ <b>Owner watermark image uploaded successfully!</b>\n\n"
                f"<b>Size:</b> {get_readable_file_size(file_size)}\n"
                f"{img_info}\n\n"
                f"<i>This watermark will be used as a fallback for all users who don't have their own watermark.</i>"
            )
        else:
            # Regular user upload
            await database.update_user_doc(user_id, "IMAGE_WATERMARK", "", img_data)

            # Enable image watermark for the user and set IMAGE_WATERMARK_PATH to "Added"
            update_user_ldata(user_id, "IMAGE_WATERMARK_ENABLED", True)
            update_user_ldata(user_id, "IMAGE_WATERMARK_PATH", "Added")

            # Make sure to update the user_dict directly as well to ensure UI shows "Added"
            if user_id in user_data:
                user_data[user_id]["IMAGE_WATERMARK_PATH"] = "Added"

            await database.update_user_data(user_id)

            # Create confirmation message for user
            msg = (
                f"✅ <b>Watermark image uploaded successfully!</b>\n\n"
                f"<b>Size:</b> {get_readable_file_size(file_size)}\n"
                f"{img_info}\n\n"
                f"<i>Your watermark will be used for all your tasks with image watermarking enabled.</i>"
            )

        # Send a simple confirmation message that will auto-delete
        confirmation_msg = await send_message(message.chat.id, msg)
        # Auto-delete the confirmation message after 5 minutes
        # We don't need to await this task, but we should store a reference to avoid warnings
        # The task will be garbage collected when it completes
        create_task(auto_delete_message(confirmation_msg, time=300))  # noqa

        # Wait a moment for the user to see the confirmation
        await asyncio.sleep(1)

        # Get the original message that was waiting for the upload
        original_message = handler_dict.get(f"{user_id}_original_message", None)

        # Automatically return to the watermark menu
        if hasattr(message, "from_bot_settings") and message.from_bot_settings:
            # Return to bot_settings watermark menu
            from bot.modules.bot_settings import update_buttons

            await update_buttons(message, "mediatools_watermark")
        elif original_message:
            # If we have the original message, use it to return to the watermark menu
            # This ensures we update the correct message
            await update_media_tools_settings(
                CallbackQuery(
                    id="fake_id",
                    from_user=message.from_user,
                    chat_instance="fake_chat",
                    message=original_message,
                    data=f"mediatools {user_id} watermark",
                )
            )
        else:
            # Fallback to using the current message
            fake_query = CallbackQuery(
                id="fake_id",
                from_user=message.from_user,
                chat_instance="fake_chat",
                message=message,
                data=f"mediatools {user_id} watermark",
            )

            # Call the update function with the watermark parameter
            await update_media_tools_settings(fake_query, "watermark")
    except Exception as e:
        error_msg = await send_message(
            message.chat.id, f"❌ Error uploading watermark image: {e}"
        )
        # Auto-delete the error message after 5 minutes
        # We don't need to await this task, but we should store a reference to avoid warnings
        # The task will be garbage collected when it completes
        create_task(auto_delete_message(error_msg, time=300))  # noqa

        # Return to the appropriate menu after showing the error
        await asyncio.sleep(2)  # Wait a moment for the user to see the error

        # Get the original message that was waiting for the upload
        original_message = handler_dict.get(f"{user_id}_original_message", None)

        if hasattr(message, "from_bot_settings") and message.from_bot_settings:
            # Return to bot_settings watermark menu
            from bot.modules.bot_settings import update_buttons

            await update_buttons(message, "mediatools_watermark")
        elif original_message:
            # If we have the original message, use it to return to the watermark menu
            # This ensures we update the correct message
            await update_media_tools_settings(
                CallbackQuery(
                    id="fake_id",
                    from_user=message.from_user,
                    chat_instance="fake_chat",
                    message=original_message,
                    data=f"mediatools {user_id} watermark",
                )
            )
        else:
            # Fallback to using the current message
            fake_query = CallbackQuery(
                id="fake_id",
                from_user=message.from_user,
                chat_instance="fake_chat",
                message=message,
                data=f"mediatools {user_id} watermark",
            )

            # Call the update function with the watermark parameter
            await update_media_tools_settings(fake_query, "watermark")
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

        # Reset the handler_dict for this user
        handler_dict[user_id] = False

        # Clean up the from_bot_settings flag
        if f"{user_id}_from_bot_settings" in handler_dict:
            del handler_dict[f"{user_id}_from_bot_settings"]

        # No need to delete the message here as we already deleted it immediately after download
        # No need to return to the watermark menu here as the buttons in the confirmation message
        # already provide navigation options for the user


def init_module():
    """Initialize the module by registering handlers."""
    from bot.helper.telegram_helper.bot_commands import BotCommands

    TgClient.bot.add_handler(
        MessageHandler(
            media_tools_settings,
            filters=filters.command(BotCommands.MediaToolsCommand),
        )
    )
    TgClient.bot.add_handler(
        CallbackQueryHandler(
            edit_media_tools_settings, filters=filters.regex("^mediatools")
        )
    )
    # We don't need a global handler for image watermark uploads anymore
    # as we're using temporary handlers for each upload request


async def find_next_available_index(file_info, track_type, target_index=None):
    """Find the next available index for a track type.

    Args:
        file_info (dict or tuple): Media info dictionary from get_media_info
        track_type (str): Type of track ('video', 'audio', 'subtitle', 'attachment')
        target_index (int, optional): Target index to start from. Defaults to None.

    Returns:
        int: Next available index
    """
    # Import logging
    import logging

    logger = logging.getLogger(__name__)

    # Check if file_info is a tuple or not a dictionary
    if not isinstance(file_info, dict):
        logger.warning(f"Invalid file_info type: {type(file_info)}. Expected dict.")
        return 0  # Default to 0 if file_info is not a dictionary

    # Map track_type to stream type in file_info
    stream_type_map = {
        "video": "video",
        "audio": "audio",
        "subtitle": "subtitle",
        "attachment": "attachment",
    }

    stream_type = stream_type_map.get(track_type)
    if not stream_type:
        return 0  # Default to 0 if track_type is not recognized

    # Get all existing indices for this track type
    existing_indices = []
    for stream in file_info.get("streams", []):
        if stream.get("codec_type") == stream_type:
            # Get the index from the stream
            index = stream.get("index")
            if index is not None:
                existing_indices.append(index)

    # If no existing indices, return 0
    if not existing_indices:
        return 0

    # If target_index is specified, check if it's available
    if target_index is not None:
        if target_index not in existing_indices:
            return target_index

        # If target_index is already taken, find the next available index
        current_index = target_index
        while current_index in existing_indices:
            current_index += 1
        return current_index

    # If target_index is not specified, find the first available index
    return await find_first_available_index(file_info, track_type)


async def find_first_available_index(file_info, track_type):
    """Find the first available index for a track type.

    Args:
        file_info (dict or tuple): Media info dictionary from get_media_info
        track_type (str): Type of track ('video', 'audio', 'subtitle', 'attachment')

    Returns:
        int: First available index
    """
    # Import logging
    import logging

    logger = logging.getLogger(__name__)

    # Check if file_info is a tuple or not a dictionary
    if not isinstance(file_info, dict):
        logger.warning(f"Invalid file_info type: {type(file_info)}. Expected dict.")
        return 0  # Default to 0 if file_info is not a dictionary

    # Map track_type to stream type in file_info
    stream_type_map = {
        "video": "video",
        "audio": "audio",
        "subtitle": "subtitle",
        "attachment": "attachment",
    }

    stream_type = stream_type_map.get(track_type)
    if not stream_type:
        return 0  # Default to 0 if track_type is not recognized

    # Get all existing indices for this track type
    existing_indices = []
    for stream in file_info.get("streams", []):
        if stream.get("codec_type") == stream_type:
            # Get the index from the stream
            index = stream.get("index")
            if index is not None:
                existing_indices.append(index)

    # If no existing indices, return 0
    if not existing_indices:
        return 0

    # Find the first available index
    current_index = 0
    while current_index in existing_indices:
        current_index += 1
    return current_index


async def add_media(path, user_id, mid=None, multi_files=None):
    """Add media to a file.

    This function adds media tracks (video, audio, subtitle, attachment) to a file.
    It supports multi-input mode where the first file is the target and subsequent files
    are sources for tracks.

    Args:
        path (str): Path to the file to add media to
        user_id (int): User ID for retrieving user settings
        mid (str, optional): Message ID for task tracking. Defaults to None.
        multi_files (list, optional): List of additional files to use as sources. Defaults to None.

    Returns:
        tuple: (success, output_path, error_message)
    """
    # Standard library imports
    import os
    from asyncio.subprocess import PIPE, create_subprocess_exec

    # Application imports
    from bot.helper.aeon_utils.command_gen import get_add_cmd
    from bot.helper.ext_utils.media_utils import get_media_info

    user_dict = user_data.get(user_id, {})

    # Check if add is enabled
    add_enabled = user_dict.get("ADD_ENABLED", False)
    if not add_enabled:
        return False, None, "Add is not enabled"

    # Get add settings
    video_enabled = user_dict.get("ADD_VIDEO_ENABLED", False)
    audio_enabled = user_dict.get("ADD_AUDIO_ENABLED", False)
    subtitle_enabled = user_dict.get("ADD_SUBTITLE_ENABLED", False)
    attachment_enabled = user_dict.get("ADD_ATTACHMENT_ENABLED", False)
    delete_original = user_dict.get("ADD_DELETE_ORIGINAL", True)

    # Handle preserve/replace flags - they should be mutually exclusive
    preserve_tracks = user_dict.get("ADD_PRESERVE_TRACKS", False)
    replace_tracks = user_dict.get("ADD_REPLACE_TRACKS", False)

    # If both are enabled, prioritize preserve over replace
    if preserve_tracks and replace_tracks:
        replace_tracks = False

    # Check if we're in multi-input mode
    if multi_files:
        # In multi-input mode, the first file is the target and subsequent files are sources
        # We don't need to check for specific track types being enabled

        # Check if multi_files is a directory
        if len(multi_files) == 1 and os.path.isdir(multi_files[0]):
            directory_path = multi_files[0]

            # Get all files in the directory
            try:
                directory_files = []
                for root, _, files in os.walk(directory_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        directory_files.append(file_path)

                if not directory_files:
                    return (
                        False,
                        None,
                        f"No files found in directory: {directory_path}",
                    )

                # Replace multi_files with the list of files from the directory
                multi_files = directory_files

            except Exception as e:
                return False, None, f"Error processing directory: {e}"

        # Get file info for the target file
        file_info = await get_media_info(path)
        if not file_info:
            return False, None, "Failed to get media info for target file"

        # Get indices for each track type
        video_index = user_dict.get("ADD_VIDEO_INDEX", None)
        audio_index = user_dict.get("ADD_AUDIO_INDEX", None)
        subtitle_index = user_dict.get("ADD_SUBTITLE_INDEX", None)
        attachment_index = user_dict.get("ADD_ATTACHMENT_INDEX", None)

        # Handle index mapping based on preserve/replace mode
        if video_index is not None:
            # Convert to int
            video_index = int(video_index)

            # In preserve mode, we use the specified index directly
            # In replace mode, we also use the specified index directly
            # Only if neither preserve nor replace is enabled, we find the next available index
            if not preserve_tracks and not replace_tracks:
                video_index = await find_next_available_index(
                    file_info, "video", video_index
                )

        if audio_index is not None:
            # Convert to int
            audio_index = int(audio_index)

            # Apply the same logic for audio index
            if not preserve_tracks and not replace_tracks:
                audio_index = await find_next_available_index(
                    file_info, "audio", audio_index
                )

        if subtitle_index is not None:
            # Convert to int
            subtitle_index = int(subtitle_index)

            # Apply the same logic for subtitle index
            if not preserve_tracks and not replace_tracks:
                subtitle_index = await find_next_available_index(
                    file_info, "subtitle", subtitle_index
                )

        if attachment_index is not None:
            # Convert to int
            attachment_index = int(attachment_index)

            # Apply the same logic for attachment index
            if not preserve_tracks and not replace_tracks:
                attachment_index = await find_next_available_index(
                    file_info, "attachment", attachment_index
                )

            if preserve_tracks or replace_tracks:
                pass
            else:
                pass

        # Get codec settings
        video_codec = user_dict.get("ADD_VIDEO_CODEC", "copy")
        audio_codec = user_dict.get("ADD_AUDIO_CODEC", "copy")
        subtitle_codec = user_dict.get("ADD_SUBTITLE_CODEC", "copy")

        # Get additional settings
        video_quality = user_dict.get("ADD_VIDEO_QUALITY", None)
        video_preset = user_dict.get("ADD_VIDEO_PRESET", None)
        video_bitrate = user_dict.get("ADD_VIDEO_BITRATE", None)
        video_resolution = user_dict.get("ADD_VIDEO_RESOLUTION", None)
        video_fps = user_dict.get("ADD_VIDEO_FPS", None)
        audio_bitrate = user_dict.get("ADD_AUDIO_BITRATE", None)
        audio_channels = user_dict.get("ADD_AUDIO_CHANNELS", None)
        audio_sampling = user_dict.get("ADD_AUDIO_SAMPLING", None)
        audio_volume = user_dict.get("ADD_AUDIO_VOLUME", None)
        subtitle_language = user_dict.get("ADD_SUBTITLE_LANGUAGE", None)
        subtitle_encoding = user_dict.get("ADD_SUBTITLE_ENCODING", None)
        subtitle_font = user_dict.get("ADD_SUBTITLE_FONT", None)
        subtitle_font_size = user_dict.get("ADD_SUBTITLE_FONT_SIZE", None)
        attachment_mimetype = user_dict.get("ADD_ATTACHMENT_MIMETYPE", None)

        # Generate the command using get_add_cmd with multi-input mode
        cmd, temp_file = await get_add_cmd(
            file_path=path,
            multi_files=multi_files,
            video_index=video_index,
            audio_index=audio_index,
            subtitle_index=subtitle_index,
            attachment_index=attachment_index,
            video_codec=video_codec,
            audio_codec=audio_codec,
            subtitle_codec=subtitle_codec,
            video_quality=video_quality,
            video_preset=video_preset,
            video_bitrate=video_bitrate,
            video_resolution=video_resolution,
            video_fps=video_fps,
            audio_bitrate=audio_bitrate,
            audio_channels=audio_channels,
            audio_sampling=audio_sampling,
            audio_volume=audio_volume,
            subtitle_language=subtitle_language,
            subtitle_encoding=subtitle_encoding,
            subtitle_font=subtitle_font,
            subtitle_font_size=subtitle_font_size,
            attachment_mimetype=attachment_mimetype,
            delete_original=delete_original,
            preserve_tracks=preserve_tracks,
            replace_tracks=replace_tracks,
        )

        # Check for flags and remove them before execution (they're handled separately)
        delete_flag = False

        if "-del" in cmd:
            cmd.remove("-del")
            delete_flag = True

        if "-preserve" in cmd:
            cmd.remove("-preserve")
            # preserve_tracks is already set from user settings

        if "-replace" in cmd:
            cmd.remove("-replace")

            # replace_tracks is already set from user settings
    else:
        # Legacy mode - check if at least one track type is enabled
        if not (
            video_enabled or audio_enabled or subtitle_enabled or attachment_enabled
        ):
            return False, None, "No track types are enabled for adding"

        # Get file info
        file_info = await get_media_info(path)
        if not file_info:
            return False, None, "Failed to get media info"

        # Check if path flags are used
        if (
            user_dict.get("ADD_VIDEO_PATH")
            or user_dict.get("ADD_AUDIO_PATH")
            or user_dict.get("ADD_SUBTITLE_PATH")
            or user_dict.get("ADD_ATTACHMENT_PATH")
        ):
            # Convert path flags to multi-input mode
            LOGGER.info("Converting path flags to multi-input mode")

            # Create a list of files based on path flags
            converted_multi_files = []

            # Add additional files based on path flags
            if video_enabled and user_dict.get("ADD_VIDEO_PATH"):
                video_path = user_dict.get("ADD_VIDEO_PATH")
                if os.path.exists(video_path):
                    converted_multi_files.append(video_path)
                    LOGGER.info(f"Added video path: {video_path}")

            if audio_enabled and user_dict.get("ADD_AUDIO_PATH"):
                audio_path = user_dict.get("ADD_AUDIO_PATH")
                if os.path.exists(audio_path):
                    converted_multi_files.append(audio_path)
                    LOGGER.info(f"Added audio path: {audio_path}")

            if subtitle_enabled and user_dict.get("ADD_SUBTITLE_PATH"):
                subtitle_path = user_dict.get("ADD_SUBTITLE_PATH")
                if os.path.exists(subtitle_path):
                    converted_multi_files.append(subtitle_path)
                    LOGGER.info(f"Added subtitle path: {subtitle_path}")

            if attachment_enabled and user_dict.get("ADD_ATTACHMENT_PATH"):
                attachment_path = user_dict.get("ADD_ATTACHMENT_PATH")
                if os.path.exists(attachment_path):
                    converted_multi_files.append(attachment_path)
                    LOGGER.info(f"Added attachment path: {attachment_path}")

            # If we have converted multi-files, use them
            if converted_multi_files:
                LOGGER.info(
                    f"Converted to multi-input mode with files: {converted_multi_files}"
                )

                # Call add_media recursively with the converted multi-files
                return await add_media(
                    path, user_id, mid, multi_files=converted_multi_files
                )
            return False, None, "No valid paths found in path flags"

        # If no path flags are used, return an error message
        return (
            False,
            None,
            "No input files specified. Please use multi-file mode.",
        )

        # Get indices
        video_index = user_dict.get("ADD_VIDEO_INDEX", None)
        audio_index = user_dict.get("ADD_AUDIO_INDEX", None)
        subtitle_index = user_dict.get("ADD_SUBTITLE_INDEX", None)
        attachment_index = user_dict.get("ADD_ATTACHMENT_INDEX", None)

        # Handle index mapping based on preserve/replace mode
        if video_enabled and video_index is not None:
            # Convert to int
            video_index = int(video_index)

            # In preserve mode, we use the specified index directly
            # In replace mode, we also use the specified index directly
            # Only if neither preserve nor replace is enabled, we find the next available index
            if not preserve_tracks and not replace_tracks:
                video_index = await find_next_available_index(
                    file_info, "video", video_index
                )

        if audio_enabled and audio_index is not None:
            # Convert to int
            audio_index = int(audio_index)

            # Apply the same logic for audio index
            if not preserve_tracks and not replace_tracks:
                audio_index = await find_next_available_index(
                    file_info, "audio", audio_index
                )

        if subtitle_enabled and subtitle_index is not None:
            # Convert to int
            subtitle_index = int(subtitle_index)

            # Apply the same logic for subtitle index
            if not preserve_tracks and not replace_tracks:
                subtitle_index = await find_next_available_index(
                    file_info, "subtitle", subtitle_index
                )

        if attachment_enabled and attachment_index is not None:
            # Convert to int
            attachment_index = int(attachment_index)

            # Apply the same logic for attachment index
            if not preserve_tracks and not replace_tracks:
                attachment_index = await find_next_available_index(
                    file_info, "attachment", attachment_index
                )

            if preserve_tracks or replace_tracks:
                pass
            else:
                pass

        # Get codec settings
        video_codec = user_dict.get("ADD_VIDEO_CODEC", "copy")
        audio_codec = user_dict.get("ADD_AUDIO_CODEC", "copy")
        subtitle_codec = user_dict.get("ADD_SUBTITLE_CODEC", "copy")

        # Get additional settings
        video_quality = user_dict.get("ADD_VIDEO_QUALITY", None)
        video_preset = user_dict.get("ADD_VIDEO_PRESET", None)
        video_bitrate = user_dict.get("ADD_VIDEO_BITRATE", None)
        video_resolution = user_dict.get("ADD_VIDEO_RESOLUTION", None)
        video_fps = user_dict.get("ADD_VIDEO_FPS", None)
        audio_bitrate = user_dict.get("ADD_AUDIO_BITRATE", None)
        audio_channels = user_dict.get("ADD_AUDIO_CHANNELS", None)
        audio_sampling = user_dict.get("ADD_AUDIO_SAMPLING", None)
        audio_volume = user_dict.get("ADD_AUDIO_VOLUME", None)
        subtitle_language = user_dict.get("ADD_SUBTITLE_LANGUAGE", None)
        subtitle_encoding = user_dict.get("ADD_SUBTITLE_ENCODING", None)
        subtitle_font = user_dict.get("ADD_SUBTITLE_FONT", None)
        subtitle_font_size = user_dict.get("ADD_SUBTITLE_FONT_SIZE", None)
        attachment_mimetype = user_dict.get("ADD_ATTACHMENT_MIMETYPE", None)

        # Generate the command using get_add_cmd
        cmd, temp_file = await get_add_cmd(
            file_path=path,
            add_video=video_enabled,
            add_audio=audio_enabled,
            add_subtitle=subtitle_enabled,
            add_attachment=attachment_enabled,
            video_index=video_index,
            audio_index=audio_index,
            subtitle_index=subtitle_index,
            attachment_index=attachment_index,
            video_codec=video_codec,
            audio_codec=audio_codec,
            subtitle_codec=subtitle_codec,
            video_quality=video_quality,
            video_preset=video_preset,
            video_bitrate=video_bitrate,
            video_resolution=video_resolution,
            video_fps=video_fps,
            audio_bitrate=audio_bitrate,
            audio_channels=audio_channels,
            audio_sampling=audio_sampling,
            audio_volume=audio_volume,
            subtitle_language=subtitle_language,
            subtitle_encoding=subtitle_encoding,
            subtitle_font=subtitle_font,
            subtitle_font_size=subtitle_font_size,
            attachment_mimetype=attachment_mimetype,
            delete_original=delete_original,
            preserve_tracks=preserve_tracks,
            replace_tracks=replace_tracks,
        )

        # Check for flags and remove them before execution (they're handled separately)
        delete_flag = False

        if "-del" in cmd:
            cmd.remove("-del")
            delete_flag = True

        if "-preserve" in cmd:
            cmd.remove("-preserve")

            # preserve_tracks is already set from user settings

        if "-replace" in cmd:
            cmd.remove("-replace")

            # replace_tracks is already set from user settings

    if not cmd:
        return False, None, "Failed to generate command"

    # Execute the command
    process = await create_subprocess_exec(
        *cmd,
        stdout=PIPE,
        stderr=PIPE,
    )
    _, stderr = await process.communicate()  # stdout not used

    # Check if the command was successful
    if process.returncode != 0:
        error_message = stderr.decode().strip()
        # Clean up the temp file if it exists
        if os.path.exists(temp_file):
            with suppress(Exception):
                os.remove(temp_file)
        return False, None, f"Failed to add media: {error_message}"

    # Rename temp file to maintain the original filename
    final_output_path = temp_file
    if os.path.exists(temp_file):
        # Get the filename and extension of the original file
        orig_base_name = os.path.basename(path)
        orig_file_name, orig_file_ext = os.path.splitext(orig_base_name)

        # Get the directory of the temp file
        temp_dir_name = os.path.dirname(temp_file)

        # Create the new filename using the original filename
        final_output_path = os.path.join(temp_dir_name, orig_base_name)

        # If the final output path already exists, add a suffix to avoid overwriting
        if os.path.exists(final_output_path) and final_output_path != temp_file:
            # Use a timestamp to ensure uniqueness
            import time

            timestamp = int(time.time())
            final_output_path = os.path.join(
                temp_dir_name, f"{orig_file_name}_{timestamp}{orig_file_ext}"
            )

        # Rename the temp file
        try:
            os.rename(temp_file, final_output_path)
        except Exception:
            # Keep using the temp file as the output
            final_output_path = temp_file
    else:
        return False, None, "Failed to add media: Output file not found"

    # Only delete original files if the operation was successful and the output file exists
    if os.path.exists(final_output_path):
        # Delete original file if enabled
        if delete_flag or delete_original:
            try:
                # Make sure the file exists before trying to delete it
                if os.path.exists(path):
                    # Use the asynchronous remove function
                    await aioremove(path)
            except Exception:
                # Try again with os.remove as a fallback
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass

        # If we're in multi-input mode, also delete the additional files if delete_original is enabled
        if multi_files and (delete_flag or delete_original):
            for additional_file in multi_files:
                try:
                    if os.path.exists(additional_file):
                        # Use the asynchronous remove function
                        await aioremove(additional_file)
                except Exception:
                    # Try again with os.remove as a fallback
                    try:
                        if os.path.exists(additional_file):
                            os.remove(additional_file)
                    except Exception:
                        pass  # No action needed
    else:
        return (
            False,
            None,
            "Failed to add media: Output file not found after processing",
        )

    return True, final_output_path, None
