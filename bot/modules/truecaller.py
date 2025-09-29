#!/usr/bin/env python3
"""
Truecaller Lookup Module
------------------------
This module provides functionality to lookup phone numbers using the Truecaller API.
"""

from logging import getLogger
from urllib.parse import quote_plus

from httpx import AsyncClient, RequestError, TimeoutException

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

LOGGER = getLogger(__name__)

# No default Truecaller API URL - must be configured by the user


@new_task
async def truecaller_lookup(_, message):
    """
    Command handler for /truecaller
    Performs a phone number lookup using the Truecaller API
    """
    # Delete the command message instantly
    await delete_message(message)

    # Check if Truecaller module is enabled
    if not Config.TRUECALLER_ENABLED:
        error_msg = await send_message(
            message,
            "<blockquote>❌ <b>Truecaller module is currently disabled.</b>\n\n"
            "Please contact the bot owner to enable it.</blockquote>",
        )
        # Auto-delete error message after 5 minutes
        await auto_delete_message(error_msg, time=300)
        return

    # If this is a reply to another message, delete that too
    if message.reply_to_message:
        await delete_message(message.reply_to_message)

    # Check if the command is a reply to another message
    phone = None
    if message.reply_to_message and message.reply_to_message.text:
        # Try to extract a phone number from the replied message
        import re

        # Look for phone number patterns in the replied message
        phone_match = re.search(
            r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4,}",
            message.reply_to_message.text,
        )
        if phone_match:
            phone = phone_match.group(0)

    # If no phone found in reply, check the command itself
    if not phone and message.text:
        cmd_parts = message.text.split(maxsplit=1)
        if len(cmd_parts) >= 2:
            phone = cmd_parts[1].strip()

    # Check if a phone number was provided
    if not phone:
        error_msg = await send_message(
            message,
            "<blockquote>📱 <b>Phone Number Required</b>\n\n"
            "Please provide a phone number to lookup or reply to a message containing a phone number.\n\n"
            "<b>Usage:</b>\n"
            "• <code>/truecaller +1234567890</code>\n"
            "• Reply to a message containing a phone number with <code>/truecaller</code></blockquote>",
        )
        # Auto-delete error message after 5 minutes
        await auto_delete_message(error_msg, time=300)
        return

    # Get the API URL from config
    api_url = Config.TRUECALLER_API_URL

    # Check if API URL is configured
    if not api_url:
        error_msg = await send_message(
            message,
            "<blockquote>❌ <b>Truecaller API URL is not configured.</b>\n\n"
            "Please contact the bot owner to set up the Truecaller API URL.</blockquote>",
        )
        # Auto-delete error message after 5 minutes
        await auto_delete_message(error_msg, time=300)
        return

    # Send initial status message
    status_msg = await send_message(
        message,
        f"🔍 <b>Looking up phone number:</b> <code>{phone}</code>...",
    )

    try:
        # Make the API request
        async with AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{api_url}?q={quote_plus(phone)}",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept": "application/json",
                },
            )

            # Check if the request was successful
            if response.status_code != 200:
                await delete_message(status_msg)
                error_msg = await send_message(
                    message,
                    f"<blockquote>❌ <b>API Error</b>\n\n"
                    f"API returned status code: <code>{response.status_code}</code></blockquote>",
                )
                # Auto-delete error message after 5 minutes
                await auto_delete_message(error_msg, time=300)
                return

            # Parse the JSON response
            try:
                data = response.json()

                # Format the response with beautiful styling
                truecaller_name = data.get("Truecaller", "Unknown")

                # Create a decorative header with HTML formatting
                msg = "<blockquote><b>🔍 TRUECALLER LOOKUP</b></blockquote>\n\n"

                # Add the name with special formatting if available
                if truecaller_name not in {"Unknown", "N/A"}:
                    msg += f"✨ <b><u>{truecaller_name}</u></b> ✨\n\n"

                # Create a styled info section with HTML formatting
                msg += "<b>📋 DETAILS</b>\n"
                msg += f"📱 <b>Number:</b> <code>{data.get('international_format', 'N/A')}</code>\n"
                msg += (
                    f"🔄 <b>Carrier:</b> <code>{data.get('carrier', 'N/A')}</code>\n"
                )
                msg += (
                    f"🌍 <b>Country:</b> <code>{data.get('country', 'N/A')}</code>\n"
                )
                msg += f"📍 <b>Location:</b> <code>{data.get('location', 'N/A')}</code>\n"
                msg += f"⏰ <b>Timezone:</b> <code>{data.get('timezones', 'N/A')}</code>\n"

                # Add other info if available
                if data.get("Unknown") and data.get("Unknown") != "N/A":
                    msg += f"ℹ️ <b>Other:</b> <code>{data.get('Unknown', 'N/A')}</code>\n"

                msg += "\n"

                # Add a footer with blockquote styling
                msg += "<blockquote>ℹ️ <i>This message will be deleted in 5 minutes</i></blockquote>"

                # Update the status message with the result
                await edit_message(status_msg, msg)

                # Auto-delete successful result message after 5 minutes
                await auto_delete_message(status_msg, time=300)

            except ValueError as e:
                LOGGER.error(f"Error parsing API response: {e}")
                await delete_message(status_msg)
                error_msg = await send_message(
                    message,
                    "<blockquote>❌ <b>Parse Error</b>\n\n"
                    "Could not parse the API response.</blockquote>",
                )
                # Auto-delete error message after 5 minutes
                await auto_delete_message(error_msg, time=300)

    except (RequestError, TimeoutException) as e:
        LOGGER.error(f"Error making API request: {e}")
        await delete_message(status_msg)
        error_msg = await send_message(
            message,
            f"<blockquote>❌ <b>Connection Error</b>\n\n"
            f"Could not connect to the Truecaller API.\n\n"
            f"<b>Error:</b> <code>{e!s}</code></blockquote>",
        )
        # Auto-delete error message after 5 minutes
        await auto_delete_message(error_msg, time=300)
    except Exception as e:
        LOGGER.error(f"Unexpected error in truecaller lookup: {e}")
        await delete_message(status_msg)
        error_msg = await send_message(
            message,
            f"<blockquote>❌ <b>Unexpected Error</b>\n\n"
            f"An unexpected error occurred.\n\n"
            f"<b>Error:</b> <code>{e!s}</code></blockquote>",
        )
        # Auto-delete error message after 5 minutes
        await auto_delete_message(error_msg, time=300)
