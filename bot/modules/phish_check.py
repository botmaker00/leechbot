import re
from logging import getLogger
from urllib.parse import urlparse

from httpx import AsyncClient, RequestError, TimeoutException

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)

LOGGER = getLogger(__name__)


class PhishDirectoryAPI:
    """Lightweight API client for phish.directory"""

    def __init__(self):
        self.base_url = Config.PHISH_DIRECTORY_API_URL.rstrip("/")
        self.timeout = Config.PHISH_DIRECTORY_TIMEOUT
        self.api_key = Config.PHISH_DIRECTORY_API_KEY

    async def check_domain(self, domain: str) -> dict:
        """Check if domain is phishing/malicious"""
        try:
            # Prepare headers
            headers = {
                "User-Agent": "AimLeechBot/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # Add authorization header if API key is provided
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/domain/check",
                    params={"domain": domain},
                    headers=headers,
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                if response.status_code == 400:
                    return {"success": False, "error": "Invalid domain provided"}
                if response.status_code == 401:
                    return {
                        "success": False,
                        "error": "Authentication required. Please register at https://phish.directory and configure PHISH_DIRECTORY_API_KEY in bot settings.",
                    }
                if response.status_code == 429:
                    return {
                        "success": False,
                        "error": "Rate limit exceeded. Please try again later.",
                    }
                return {
                    "success": False,
                    "error": f"API returned status code: {response.status_code}",
                }

        except TimeoutException:
            return {"success": False, "error": "Request timeout"}
        except RequestError as e:
            return {"success": False, "error": f"Connection error: {e!s}"}
        except Exception as e:
            LOGGER.error(f"Unexpected error in domain check: {e}")
            return {"success": False, "error": f"Unexpected error: {e!s}"}

    async def check_email(self, email: str) -> dict:
        """Validate email and check reputation"""
        try:
            # Prepare headers
            headers = {
                "User-Agent": "AimLeechBot/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # Add authorization header if API key is provided
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/email/check",
                    params={"email": email},
                    headers=headers,
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                if response.status_code == 400:
                    return {"success": False, "error": "Invalid email provided"}
                if response.status_code == 401:
                    return {
                        "success": False,
                        "error": "Authentication required. Please register at https://phish.directory and configure PHISH_DIRECTORY_API_KEY in bot settings.",
                    }
                if response.status_code == 429:
                    return {
                        "success": False,
                        "error": "Rate limit exceeded. Please try again later.",
                    }
                return {
                    "success": False,
                    "error": f"API returned status code: {response.status_code}",
                }

        except TimeoutException:
            return {"success": False, "error": "Request timeout"}
        except RequestError as e:
            return {"success": False, "error": f"Connection error: {e!s}"}
        except Exception as e:
            LOGGER.error(f"Unexpected error in email check: {e}")
            return {"success": False, "error": f"Unexpected error: {e!s}"}

    async def check_api_status(self) -> dict:
        """Check if the API is accessible by testing the metrics endpoint"""
        try:
            headers = {
                "User-Agent": "AimLeechBot/1.0",
                "Accept": "application/json",
            }

            async with AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/misc/metrics",
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "data": data,
                        "message": "API is accessible. Authentication required for domain/email checks.",
                    }
                return {
                    "success": False,
                    "error": f"API status check failed with code: {response.status_code}",
                }

        except TimeoutException:
            return {"success": False, "error": "API connection timeout"}
        except RequestError as e:
            return {"success": False, "error": f"API connection error: {e!s}"}
        except Exception as e:
            LOGGER.error(f"Unexpected error in API status check: {e}")
            return {"success": False, "error": f"Unexpected error: {e!s}"}


def detect_input_type(input_text: str) -> tuple[str, str]:
    """
    Detect if input is email, URL, or domain
    Returns (type, cleaned_input)
    """
    input_text = input_text.strip()

    # Check if it's an email
    if "@" in input_text and re.match(r"^[^@]+@[^@]+\.[^@]+$", input_text):
        return ("email", input_text.lower())

    # Check if it's a URL
    if input_text.startswith(("http://", "https://")):
        try:
            parsed = urlparse(input_text)
            domain = parsed.netloc.lower()
            return ("domain", domain)
        except Exception:
            return ("domain", input_text.lower())

    # Assume it's a domain
    return ("domain", input_text.lower())


def format_domain_response(data: dict, domain: str) -> str:
    """Format domain check response with beautiful HTML styling"""
    msg = "<blockquote><b>🔍 PHISH DIRECTORY - DOMAIN CHECK</b></blockquote>\n\n"

    # Domain header
    msg += f"🌐 <b>Domain:</b> <code>{domain}</code>\n\n"

    # Check if domain is malicious
    is_phishing = data.get("phishing", False)

    if is_phishing:
        msg += "🚨 <b><u>⚠️ PHISHING DETECTED ⚠️</u></b>\n\n"
        msg += "❌ <b>Status:</b> <code>Malicious/Phishing</code>\n"
        msg += "🛡️ <b>Safety:</b> <code>Unsafe</code>\n"
        msg += "⚠️ <b>Risk Level:</b> <code>High</code>\n\n"
        msg += "<blockquote>⚠️ <b>WARNING:</b> This domain has been identified as a phishing or malicious site. Avoid visiting or sharing personal information.</blockquote>"
    else:
        msg += "✅ <b>Status:</b> <code>Clean</code>\n"
        msg += "🛡️ <b>Safety:</b> <code>Safe</code>\n"
        msg += "📊 <b>Risk Level:</b> <code>Low</code>\n\n"
        msg += "<blockquote>✅ <b>SAFE:</b> This domain appears to be clean and safe to visit.</blockquote>"

    return msg


def format_email_response(data: dict, email: str) -> str:
    """Format email check response with beautiful HTML styling"""
    msg = "<blockquote><b>🔍 PHISH DIRECTORY - EMAIL CHECK</b></blockquote>\n\n"

    # Email header
    msg += f"📧 <b>Email:</b> <code>{email}</code>\n\n"

    # Email validation results
    valid = data.get("valid", False)
    disposable = data.get("disposable", False)
    dns_valid = data.get("dns_valid", False)
    fraud_score = data.get("fraud_score", 0)
    recent_abuse = data.get("recent_abuse", False)
    first_seen = data.get("first_seen", "Unknown")

    # Status section
    msg += "<b>📋 VALIDATION RESULTS</b>\n"
    msg += f"✅ <b>Valid Format:</b> <code>{'Yes' if valid else 'No'}</code>\n"
    msg += f"🌐 <b>DNS Valid:</b> <code>{'Yes' if dns_valid else 'No'}</code>\n"
    msg += f"🗑️ <b>Disposable:</b> <code>{'Yes' if disposable else 'No'}</code>\n"
    msg += f"⚠️ <b>Fraud Score:</b> <code>{fraud_score}/100</code>\n"
    msg += (
        f"🚨 <b>Recent Abuse:</b> <code>{'Yes' if recent_abuse else 'No'}</code>\n"
    )

    if first_seen != "Unknown":
        msg += f"📅 <b>First Seen:</b> <code>{first_seen}</code>\n"

    msg += "\n"

    # Overall assessment
    if not valid or disposable or fraud_score > 75 or recent_abuse:
        msg += "<blockquote>⚠️ <b>CAUTION:</b> This email shows signs of being suspicious, disposable, or associated with fraudulent activity.</blockquote>"
    elif fraud_score > 50:
        msg += "<blockquote>🟡 <b>MODERATE RISK:</b> This email has a moderate fraud score. Use with caution.</blockquote>"
    else:
        msg += "<blockquote>✅ <b>LOOKS GOOD:</b> This email appears to be legitimate and safe.</blockquote>"

    return msg


@new_task
async def phish_check_command(_, message):
    """
    Command handler for /phishcheck
    Performs domain or email security checks using phish.directory API
    """
    # Delete the command message instantly
    await delete_message(message)

    # Check if Phish Directory module is enabled
    if not Config.PHISH_DIRECTORY_ENABLED:
        error_msg = await send_message(
            message,
            "<blockquote>❌ <b>Phish Directory module is currently disabled.</b>\n\n"
            "Please contact the bot owner to enable it.</blockquote>",
        )
        await auto_delete_message(error_msg, time=300)
        return

    # If this is a reply to another message, delete that too
    if message.reply_to_message:
        await delete_message(message.reply_to_message)

    # Parse command arguments
    cmd_parts = message.text.split(maxsplit=1)
    if len(cmd_parts) < 2:
        error_msg = await send_message(
            message,
            "<blockquote>❌ <b>Invalid Usage</b>\n\n"
            "<b>Usage:</b> <code>/phishcheck &lt;domain_or_email&gt;</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/phishcheck google.com</code>\n"
            "• <code>/phishcheck user@example.com</code>\n"
            "• <code>/phishcheck https://suspicious-site.com</code></blockquote>",
        )
        await auto_delete_message(error_msg, time=300)
        return

    input_text = cmd_parts[1].strip()
    if not input_text:
        error_msg = await send_message(
            message,
            "<blockquote>❌ <b>Empty Input</b>\n\n"
            "Please provide a domain or email address to check.</blockquote>",
        )
        await auto_delete_message(error_msg, time=300)
        return

    # Show processing message
    status_msg = await send_message(
        message,
        "<blockquote>🔍 <b>Checking with Phish Directory...</b>\n\n"
        "Please wait while we analyze the provided input.</blockquote>",
    )

    try:
        # Detect input type and clean it
        input_type, cleaned_input = detect_input_type(input_text)

        # Initialize API client
        api_client = PhishDirectoryAPI()

        # Perform the appropriate check
        if input_type == "email":
            result = await api_client.check_email(cleaned_input)
        else:  # domain
            result = await api_client.check_domain(cleaned_input)

        # Delete status message
        await delete_message(status_msg)

        # Handle API response
        if result["success"]:
            # Format response based on type
            if input_type == "email":
                response_text = format_email_response(result["data"], cleaned_input)
            else:  # domain
                response_text = format_domain_response(result["data"], cleaned_input)

            # Send formatted response
            response_msg = await send_message(message, response_text)
            # Auto-delete after 10 minutes
            await auto_delete_message(response_msg, time=600)

        else:
            # Handle API error with enhanced messaging for authentication issues
            error_text = result["error"]
            if "Authentication required" in error_text:
                error_msg = await send_message(
                    message,
                    "<blockquote>🔐 <b>Authentication Required</b>\n\n"
                    "The phish.directory API requires authentication for security checks.\n\n"
                    "<b>📋 Setup Instructions:</b>\n"
                    "1. Visit <a href='https://phish.directory'>phish.directory</a>\n"
                    "2. Create a free account\n"
                    "3. Get your API key from the dashboard\n"
                    "4. Configure <code>PHISH_DIRECTORY_API_KEY</code> in bot settings\n\n"
                    "<b>💡 Note:</b> This is a one-time setup for enhanced security features.</blockquote>",
                )
            else:
                error_msg = await send_message(
                    message,
                    f"<blockquote>❌ <b>API Error</b>\n\n"
                    f"<b>Error:</b> <code>{error_text}</code>\n\n"
                    f"Please try again later or contact support if the issue persists.</blockquote>",
                )
            await auto_delete_message(
                error_msg, time=600
            )  # Longer timeout for setup instructions

    except Exception as e:
        LOGGER.error(f"Unexpected error in phish_check_command: {e}")
        await delete_message(status_msg)
        error_msg = await send_message(
            message,
            f"<blockquote>❌ <b>Unexpected Error</b>\n\n"
            f"An unexpected error occurred while processing your request.\n\n"
            f"<b>Error:</b> <code>{e!s}</code></blockquote>",
        )
        await auto_delete_message(error_msg, time=300)
