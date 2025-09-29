import contextlib
import os
import re

import aiofiles
import httpx
from pyrogram.types import Message

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.links_utils import is_url
from bot.helper.telegram_helper.message_utils import send_message


class TinyURLAPI:
    """TinyURL API client for link shortening"""

    BASE_URL = "https://api.tinyurl.com"

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def shorten_link(
        self, long_url: str, custom_alias: str | None = None
    ) -> dict:
        """
        Shorten a URL using TinyURL API

        Args:
            long_url: The URL to shorten
            custom_alias: Optional custom alias for the link

        Returns:
            dict: Response containing shortened link info or error
        """
        try:
            shorten_data = {
                "url": long_url,
                "domain": "tinyurl.com",
            }

            # Add custom alias if provided
            if custom_alias and custom_alias.strip():
                shorten_data["alias"] = custom_alias

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/create",
                    headers=self.headers,
                    json=shorten_data,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("errors", [])
                    if error_msg:
                        error_msg = (
                            error_msg[0]
                            if isinstance(error_msg, list)
                            else str(error_msg)
                        )
                    else:
                        error_msg = f"HTTP {response.status_code}"

                    # Log the full error for debugging
                    LOGGER.error(
                        f"TinyURL API error: {response.status_code} - {error_data}"
                    )

                    # Provide user-friendly error messages
                    if (
                        "alias" in str(error_data).lower()
                        and "already" in str(error_data).lower()
                    ):
                        error_msg = f"Custom alias '{custom_alias}' is already taken. Please try a different alias."
                    elif (
                        "unauthorized" in str(error_data).lower()
                        or response.status_code == 401
                    ):
                        error_msg = "Invalid TinyURL API token. Please check your TINYURL_API_TOKEN."
                    elif (
                        "forbidden" in str(error_data).lower()
                        or response.status_code == 403
                    ):
                        error_msg = "Access denied. Please check your TinyURL API token permissions."

                    return {
                        "success": False,
                        "error": error_msg,
                    }

                result = response.json()
                data = result.get("data", {})
                shortened_link = data.get("tiny_url")

                return {
                    "success": True,
                    "shortened_link": shortened_link,
                    "original_url": long_url,
                    "alias": data.get("alias"),
                    "data": result,
                }

        except Exception as e:
            LOGGER.error(f"Error shortening link with TinyURL: {e}")
            return {
                "success": False,
                "error": f"Failed to shorten link: {e!s}",
            }


class BitlyAPI:
    """Bitly API client for link shortening and QR code generation"""

    BASE_URL = "https://api-ssl.bitly.com/v4"

    def __init__(self, access_token: str, group_guid: str | None = None):
        self.access_token = access_token
        self.group_guid = group_guid
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def shorten_link(
        self, long_url: str, custom_alias: str | None = None
    ) -> dict:
        """
        Shorten a URL using Bitly API

        Args:
            long_url: The URL to shorten
            custom_alias: Optional custom alias for the link

        Returns:
            dict: Response containing shortened link info or error
        """
        try:
            # First, create the shortened link
            shorten_data = {"long_url": long_url, "domain": "bit.ly"}

            # Only add group_guid if it's provided and not empty
            if self.group_guid and self.group_guid.strip():
                shorten_data["group_guid"] = self.group_guid

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/shorten",
                    headers=self.headers,
                    json=shorten_data,
                    timeout=30.0,
                )

                if response.status_code not in [200, 201]:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get(
                        "message", f"HTTP {response.status_code}"
                    )

                    # Log the full error for debugging
                    LOGGER.error(
                        f"Bitly API error: {response.status_code} - {error_data}"
                    )

                    # Provide user-friendly error messages
                    if "INVALID_ARG_GROUP_GUID" in error_msg:
                        error_msg = "Invalid group configuration. Please check BITLY_GROUP_GUID setting."
                    elif "FORBIDDEN" in error_msg or response.status_code == 403:
                        error_msg = "Access denied. Please check your Bitly access token permissions."
                    elif "UNAUTHORIZED" in error_msg or response.status_code == 401:
                        error_msg = "Invalid access token. Please check your BITLY_ACCESS_TOKEN."

                    return {
                        "success": False,
                        "error": error_msg,
                    }

                result = response.json()
                shortened_link = result.get("link")
                bitlink_id = result.get("id")

                # If custom alias is provided, try to create custom bitlink
                if custom_alias and shortened_link:
                    custom_result = await self._create_custom_bitlink(
                        bitlink_id, custom_alias
                    )
                    if custom_result["success"]:
                        shortened_link = custom_result["custom_link"]
                    else:
                        # Return the regular shortened link with alias error info
                        result["alias_error"] = custom_result["error"]

                return {
                    "success": True,
                    "shortened_link": shortened_link,
                    "bitlink_id": bitlink_id,
                    "original_url": long_url,
                    "data": result,
                }

        except Exception as e:
            LOGGER.error(f"Error shortening link: {e}")
            return {"success": False, "error": f"Failed to shorten link: {e!s}"}

    async def _create_custom_bitlink(
        self, bitlink_id: str, custom_alias: str
    ) -> dict:
        """
        Create a custom bitlink with the specified alias

        Args:
            bitlink_id: The bitlink ID to customize
            custom_alias: The custom alias to use

        Returns:
            dict: Success status and custom link or error
        """
        try:
            # Extract domain from bitlink_id (e.g., "bit.ly/abc123" -> "bit.ly")
            domain = bitlink_id.split("/")[0]
            custom_bitlink = f"{domain}/{custom_alias}"

            custom_data = {
                "custom_bitlink": custom_bitlink,
                "bitlink_id": bitlink_id,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/custom_bitlinks",
                    headers=self.headers,
                    json=custom_data,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return {
                        "success": True,
                        "custom_link": f"https://{custom_bitlink}",
                    }

                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", "Custom alias not available")
                return {"success": False, "error": error_msg}

        except Exception as e:
            LOGGER.error(f"Error creating custom bitlink: {e}")
            return {
                "success": False,
                "error": f"Failed to create custom alias: {e!s}",
            }

    async def get_user_default_group(self) -> str | None:
        """
        Get the user's default group GUID from Bitly API

        Returns:
            str | None: Default group GUID or None if not found
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/user",
                    headers=self.headers,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get("default_group_guid")

        except Exception as e:
            LOGGER.error(f"Error getting user default group: {e}")

        return None

    async def create_qr_code(self, bitlink_id: str, title: str = "QR Code") -> dict:
        """
        Create a QR code for the shortened link

        Args:
            bitlink_id: The bitlink ID to create QR code for
            title: Title for the QR code

        Returns:
            dict: QR code creation result
        """
        try:
            qr_data = {"title": title, "destination": {"bitlink_id": bitlink_id}}

            # QR code endpoint requires group_guid, so get it if not provided
            group_guid = self.group_guid
            if not group_guid or not group_guid.strip():
                # Try to get user's default group
                group_guid = await self.get_user_default_group()

            if group_guid:
                qr_data["group_guid"] = group_guid
            else:
                # Log warning but try without group_guid as fallback
                LOGGER.warning(
                    "No group_guid available for QR code creation, trying without it"
                )

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/qr-codes",
                    headers=self.headers,
                    json=qr_data,
                    timeout=30.0,
                )

                if response.status_code == 201:
                    result = response.json()
                    return {
                        "success": True,
                        "qrcode_id": result.get("qrcode_id"),
                        "data": result,
                    }

                error_data = response.json() if response.content else {}
                error_msg = error_data.get("message", f"HTTP {response.status_code}")

                # Log the full error for debugging
                LOGGER.warning(
                    f"Bitly QR API error: {response.status_code} - {error_data}"
                )

                # Provide user-friendly error messages
                if "INVALID_ARG_GROUP_GUID" in error_msg or "missing_field" in str(
                    error_data
                ):
                    if "missing_field" in str(error_data):
                        error_msg = "QR code creation requires a group GUID. Please set BITLY_GROUP_GUID in your configuration or use an organization account with a default group."
                    else:
                        error_msg = "Invalid group configuration for QR code. Please check BITLY_GROUP_GUID setting."
                elif "FORBIDDEN" in error_msg or response.status_code == 403:
                    error_msg = "Access denied for QR code creation. Please check your Bitly access token permissions."
                elif "UNAUTHORIZED" in error_msg or response.status_code == 401:
                    error_msg = "Invalid access token for QR code. Please check your BITLY_ACCESS_TOKEN."

                return {
                    "success": False,
                    "error": error_msg,
                }

        except Exception as e:
            LOGGER.error(f"Error creating QR code: {e}")
            return {"success": False, "error": f"Failed to create QR code: {e!s}"}

    async def get_qr_code_image(self, qrcode_id: str, format: str = "png") -> dict:
        """
        Get QR code image data

        Args:
            qrcode_id: The QR code ID
            format: Image format (png or svg)

        Returns:
            dict: QR code image data or error
        """
        try:
            headers = self.headers.copy()
            if format == "png":
                headers["Accept"] = "image/png"
            else:
                headers["Accept"] = "image/svg+xml"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/qr-codes/{qrcode_id}/image",
                    headers=headers,
                    params={"format": format},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    if format == "png":
                        return {
                            "success": True,
                            "image_data": response.content,
                            "format": "png",
                        }

                    return {
                        "success": True,
                        "image_data": response.content,
                        "format": "svg",
                    }

                return {
                    "success": False,
                    "error": f"Failed to get QR code image: HTTP {response.status_code}",
                }

        except Exception as e:
            LOGGER.error(f"Error getting QR code image: {e}")
            return {"success": False, "error": f"Failed to get QR code image: {e!s}"}


def extract_url_from_message(message: Message) -> str:
    """Extract URL from message text or replied message"""
    # Check if replying to a message with URL
    if message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text
        # Look for URLs in the replied message
        url_pattern = r"https?://[^\s]+"
        urls = re.findall(url_pattern, text)
        if urls:
            return urls[0]  # Return first URL found

    # Check command arguments
    if len(message.command) > 1:
        potential_url = message.command[1]
        if is_url(potential_url):
            return potential_url

    return None


def extract_custom_alias(message: Message) -> str:
    """Extract custom alias from command arguments"""
    if len(message.command) > 2:
        alias = message.command[2].strip()
        # Validate alias (alphanumeric, hyphens, underscores only)
        if re.match(r"^[a-zA-Z0-9_-]+$", alias) and len(alias) <= 50:
            return alias
    return None


async def shortner_command(_client, message: Message):
    """
    Handle /shortner command for link shortening with QR code generation

    Usage:
    /shortner <url> [custom_alias]
    Reply to a message containing URL with /shortner [custom_alias]

    Supports both Bitly and TinyURL APIs based on configuration.
    """
    # Check if any API is configured
    has_bitly = bool(getattr(Config, "BITLY_ACCESS_TOKEN", None))
    has_tinyurl = bool(getattr(Config, "TINYURL_API_TOKEN", None))

    if not has_bitly and not has_tinyurl:
        await send_message(
            message,
            "<b>❌ Link Shortener Not Configured</b>\n\n"
            "Neither Bitly nor TinyURL API tokens are configured. Please contact the administrator.\n\n"
            "<b>Required Configuration:</b>\n"
            "• <code>BITLY_ACCESS_TOKEN</code> - For Bitly API with QR codes\n"
            "• <code>TINYURL_API_TOKEN</code> - For TinyURL API (no QR codes)",
        )
        return

    # Extract URL from message
    url = extract_url_from_message(message)
    if not url:
        # Build dynamic usage text based on available APIs
        usage_text = "<b>🔗 Link Shortener Usage</b>\n\n"

        if has_bitly and has_tinyurl:
            usage_text += "Shorten URLs using both Bitly and TinyURL APIs simultaneously for maximum reach.\n\n"
        elif has_bitly:
            usage_text += "Shorten URLs and generate QR codes using Bitly API.\n\n"
        elif has_tinyurl:
            usage_text += "Shorten URLs using TinyURL API.\n\n"

        usage_text += (
            "<b>📝 Usage:</b>\n"
            "1️⃣ <b>Direct URL:</b> <code>/shortner https://example.com [custom_alias]</code>\n"
            "2️⃣ <b>Reply to message:</b> Reply to any message containing a URL with <code>/shortner [custom_alias]</code>\n\n"
            "<b>🎯 Custom Alias:</b>\n"
            "• Optional custom alias for your shortened link\n"
            "• Must be alphanumeric with hyphens/underscores only\n"
            "• Maximum 50 characters\n"
            "• Example: <code>/shortner https://example.com my-link</code>\n\n"
            "<b>✨ Available Features:</b>\n"
        )

        if has_bitly:
            usage_text += "• <b>Bitly:</b> QR code generation + analytics\n"
        if has_tinyurl:
            usage_text += "• <b>TinyURL:</b> Fast shortening + analytics\n"

        if has_bitly and has_tinyurl:
            usage_text += "• <b>Dual Service:</b> Get links from both services simultaneously\n"

        usage_text += "• Custom alias support\n• Click tracking and analytics"

        await send_message(message, usage_text)
        return

    # Extract custom alias if provided
    custom_alias = extract_custom_alias(message)

    # Send processing message
    processing_msg = await send_message(
        message, "<b>🔄 Processing...</b>\n\nShortening URL..."
    )

    try:
        # Initialize Bitly API
        # Try both APIs if available, collect all successful results
        results = {}
        bitly_result = None
        tinyurl_result = None

        await processing_msg.edit("<b>🔗 Shortening URL...</b>")

        # Try Bitly if available
        if has_bitly:
            try:
                # Get group_guid from config, but make it completely optional
                group_guid = getattr(Config, "BITLY_GROUP_GUID", None)
                if group_guid and not group_guid.strip():
                    group_guid = None  # Treat empty string as None

                bitly = BitlyAPI(
                    access_token=Config.BITLY_ACCESS_TOKEN,
                    group_guid=group_guid,
                )

                bitly_result = await bitly.shorten_link(url, custom_alias)
                if bitly_result["success"]:
                    results["bitly"] = bitly_result
                else:
                    LOGGER.warning(f"Bitly failed: {bitly_result['error']}")
            except Exception as e:
                LOGGER.error(f"Bitly API error: {e}")

        # Try TinyURL if available
        if has_tinyurl:
            try:
                tinyurl = TinyURLAPI(api_token=Config.TINYURL_API_TOKEN)
                tinyurl_result = await tinyurl.shorten_link(url, custom_alias)
                if tinyurl_result["success"]:
                    results["tinyurl"] = tinyurl_result
                else:
                    LOGGER.warning(f"TinyURL failed: {tinyurl_result['error']}")
            except Exception as e:
                LOGGER.error(f"TinyURL API error: {e}")

        # Check if any API succeeded
        if not results:
            error_msg = "All URL shortening services failed."
            if bitly_result and "error" in bitly_result:
                error_msg = bitly_result["error"]
            elif tinyurl_result and "error" in tinyurl_result:
                error_msg = tinyurl_result["error"]
            await processing_msg.edit(
                f"<b>❌ Failed to shorten URL</b>\n\n"
                f"<b>Error:</b> {error_msg}\n"
                f"<b>URL:</b> <code>{url}</code>"
            )
            return

        # Handle QR code generation for Bitly (if available)
        qr_result = None
        if "bitly" in results:
            bitlink_id = results["bitly"].get("bitlink_id")
            if bitlink_id:
                await processing_msg.edit("<b>🎨 Creating QR code...</b>")
                qr_result = await bitly.create_qr_code(
                    bitlink_id, f"QR Code for {url}"
                )
            else:
                LOGGER.warning(
                    "No bitlink_id found in Bitly response, skipping QR code"
                )

        # Build response showing all successful services
        response = "<b>✅ Link Shortened Successfully</b>\n\n"
        response += f"<b>🌐 Original URL:</b> <code>{url}</code>\n\n"

        # Add Bitly result if available
        if "bitly" in results:
            bitly_link = results["bitly"]["shortened_link"]
            response += f"<b>� Bitly:</b> <a href='{bitly_link}'>{bitly_link}</a>\n"

        # Add TinyURL result if available
        if "tinyurl" in results:
            tinyurl_link = results["tinyurl"]["shortened_link"]
            response += (
                f"<b>🔗 TinyURL:</b> <a href='{tinyurl_link}'>{tinyurl_link}</a>\n"
            )

        # Add custom alias info if provided
        if custom_alias:
            alias_success = []
            alias_errors = []

            if "bitly" in results and "alias_error" in results["bitly"]:
                alias_errors.append(f"Bitly: {results['bitly']['alias_error']}")
            elif "bitly" in results:
                alias_success.append("Bitly")

            if "tinyurl" in results and "alias_error" in results["tinyurl"]:
                alias_errors.append(f"TinyURL: {results['tinyurl']['alias_error']}")
            elif "tinyurl" in results:
                alias_success.append("TinyURL")

            if alias_success:
                response += f"\n<b>✅ Custom Alias '{custom_alias}':</b> {', '.join(alias_success)}"
            if alias_errors:
                response += f"\n<b>⚠️ Alias Errors:</b> {'; '.join(alias_errors)}"

        response += "\n\n<b>📊 Analytics:</b> Available on respective dashboards"

        # Handle QR code if Bitly was successful and QR code was created
        if qr_result and qr_result["success"]:
            qrcode_id = qr_result["qrcode_id"]

            # Get QR code image
            await processing_msg.edit("<b>📸 Generating QR code image...</b>")
            image_result = await bitly.get_qr_code_image(qrcode_id, "png")

            if not image_result["success"]:
                # QR image failed, send text response without showing error to user
                LOGGER.warning(
                    f"QR code image generation failed: {image_result['error']}"
                )
                await processing_msg.edit(response, disable_web_page_preview=True)
                return

            # QR code successful - prepare caption and send with image
            response += "\n<b>🎨 QR Code:</b> Scan to visit the Bitly link"

            # Save QR code image to temporary file
            temp_file = f"qr_code_{qrcode_id}.png"
            async with aiofiles.open(temp_file, "wb") as f:
                await f.write(image_result["image_data"])

            # Send QR code image with caption
            await send_message(message, response, photo=temp_file)

            # Delete processing message and temp file
            await processing_msg.delete()

            # Clean up temp file
            with contextlib.suppress(Exception):
                os.remove(temp_file)
        else:
            # No QR code or QR failed - send text response only
            if qr_result and not qr_result["success"]:
                LOGGER.warning(f"QR code creation failed: {qr_result['error']}")

            await processing_msg.edit(response, disable_web_page_preview=True)

    except Exception as e:
        LOGGER.error(f"Error in shortner command: {e}")
        await processing_msg.edit(
            f"<b>❌ Error occurred</b>\n\n"
            f"<b>Error:</b> {e!s}\n"
            f"<b>URL:</b> <code>{url}</code>"
        )
