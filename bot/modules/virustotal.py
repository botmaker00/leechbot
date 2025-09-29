import asyncio
import base64
import html
import os
import time
from asyncio import create_task
from logging import getLogger

from vt import APIError
from vt import Client as VTClient

from bot import DOWNLOAD_DIR
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.links_utils import is_url
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    edit_message,
    send_message,
)

LOGGER = getLogger(__name__)

# Global storage for scan results (for callback handling)
VT_SCAN_RESULTS = {}


def _extract_scan_data(result: dict) -> dict:
    """Extract and normalize scan data from VirusTotal response."""
    attributes = result.get("attributes", {})

    # Get stats
    stats = attributes.get("stats", {})

    # Get engines/results data
    engines_data = attributes.get("engines", {}) or attributes.get("results", {})

    # Extract signatures if available
    signatures = []
    if "signatures" in attributes:
        signatures = attributes["signatures"]
    elif engines_data:
        # Extract signatures from engine results
        for engine_name, engine_data in engines_data.items():
            if (
                isinstance(engine_data, dict)
                and engine_data.get("result")
                and engine_data.get("result") != "clean"
            ) and engine_data["result"] not in [
                "unrated",
                "timeout",
                "type-unsupported",
            ]:
                signatures.append(f"{engine_name}: {engine_data['result']}")

    return {
        "stats": stats,
        "engines": engines_data,
        "signatures": signatures,
        "raw_result": result,
    }


def _determine_threat_status(stats: dict) -> tuple[str, str]:
    """Determine threat status and emoji based on stats."""
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)

    if malicious >= 3:
        return "❌ POTENTIALLY DANGEROUS", "🔴"
    if malicious > 0 or suspicious > 0:
        return "⚠️ SUSPICIOUS", "🟡"
    return "✅ SAFE", "🟢"


def _format_basic_results(
    file_name: str, file_size: int, scan_data: dict, vt_link: str, scan_id: str
) -> tuple[str, object]:
    """Format basic scan results with buttons."""
    stats = scan_data["stats"]
    threat_status, status_emoji = _determine_threat_status(stats)

    # Format response
    response = f"<b>{status_emoji} VirusTotal Scan Results</b>\n\n"
    response += f"<b>File:</b> {html.escape(file_name)}\n"
    response += f"<b>Size:</b> {get_readable_file_size(file_size)}\n"
    response += f"<b>Status:</b> {threat_status}\n\n"
    response += "<b>Detection Summary:</b>\n"
    response += f"• Malicious: {stats.get('malicious', 0)}\n"
    response += f"• Suspicious: {stats.get('suspicious', 0)}\n"
    response += f"• Harmless: {stats.get('harmless', 0)}\n"
    response += f"• Undetected: {stats.get('undetected', 0)}\n"

    # Add timeout and failure counts if present
    if stats.get("timeout", 0) > 0:
        response += f"• Timeout: {stats.get('timeout', 0)}\n"
    if stats.get("failure", 0) > 0:
        response += f"• Failure: {stats.get('failure', 0)}\n"

    response += f"\n<b>Full Report:</b> <a href='{vt_link}'>View on VirusTotal</a>"

    # Create buttons
    buttons = ButtonMaker()
    buttons.data_button("🔍 Detections", f"vt_det_{scan_id}")

    # Only show signatures button if there are signatures
    if scan_data["signatures"]:
        buttons.data_button("🦠 Signatures", f"vt_sig_{scan_id}")

    buttons.data_button("❌ Close", f"vt_close_{scan_id}")

    return response, buttons.build_menu(2)


def _format_url_results(
    url: str, scan_data: dict, vt_link: str, scan_id: str
) -> tuple[str, object]:
    """Format URL scan results with buttons."""
    stats = scan_data["stats"]
    threat_status, status_emoji = _determine_threat_status(stats)

    # Format response
    response = f"<b>{status_emoji} VirusTotal URL Scan Results</b>\n\n"
    response += f"<b>URL:</b> {html.escape(url)}\n"
    response += f"<b>Status:</b> {threat_status}\n\n"
    response += "<b>Detection Summary:</b>\n"
    response += f"• Malicious: {stats.get('malicious', 0)}\n"
    response += f"• Suspicious: {stats.get('suspicious', 0)}\n"
    response += f"• Harmless: {stats.get('harmless', 0)}\n"
    response += f"• Undetected: {stats.get('undetected', 0)}\n"

    # Add timeout count if present
    if stats.get("timeout", 0) > 0:
        response += f"• Timeout: {stats.get('timeout', 0)}\n"

    response += f"\n<b>Full Report:</b> <a href='{vt_link}'>View on VirusTotal</a>"

    # Create buttons
    buttons = ButtonMaker()
    buttons.data_button("🔍 Detections", f"vt_det_{scan_id}")

    # Only show signatures button if there are signatures
    if scan_data["signatures"]:
        buttons.data_button("🦠 Signatures", f"vt_sig_{scan_id}")

    buttons.data_button("❌ Close", f"vt_close_{scan_id}")

    return response, buttons.build_menu(2)


def _format_detections(scan_data: dict, scan_id: str) -> tuple[str, object]:
    """Format detailed detection results."""
    engines = scan_data["engines"]
    stats = scan_data["stats"]

    if not engines:
        response = "❌ <b>No detection data available</b>"
        buttons = ButtonMaker()
        buttons.data_button("🔙 Back", f"vt_back_{scan_id}")
        buttons.data_button("❌ Close", f"vt_close_{scan_id}")
        return response, buttons.build_menu(2)

    # Categorize engines
    malicious_engines = []
    suspicious_engines = []
    harmless_engines = []
    undetected_engines = []
    other_engines = []

    for engine_name, engine_data in engines.items():
        if isinstance(engine_data, dict):
            category = engine_data.get("category", "unknown")
            result = engine_data.get("result", "N/A")

            if category == "malicious":
                malicious_engines.append(f"🔴 {engine_name}: {result}")
            elif category == "suspicious":
                suspicious_engines.append(f"🟡 {engine_name}: {result}")
            elif category == "harmless":
                harmless_engines.append(f"🟢 {engine_name}: Clean")
            elif category == "undetected":
                undetected_engines.append(f"⚪ {engine_name}: Undetected")
            else:
                other_engines.append(f"⚫ {engine_name}: {category}")

    # Build response
    response = "<b>🔍 Detailed Detection Results</b>\n\n"
    response += f"<b>Summary:</b> {stats.get('malicious', 0)} malicious, {stats.get('suspicious', 0)} suspicious, "
    response += f"{stats.get('harmless', 0)} harmless, {stats.get('undetected', 0)} undetected\n\n"

    # Show malicious detections first
    if malicious_engines:
        response += f"<b>🔴 Malicious ({len(malicious_engines)}):</b>\n"
        for detection in malicious_engines[:10]:  # Limit to first 10
            response += f"{detection}\n"
        if len(malicious_engines) > 10:
            response += f"... and {len(malicious_engines) - 10} more\n"
        response += "\n"

    # Show suspicious detections
    if suspicious_engines:
        response += f"<b>🟡 Suspicious ({len(suspicious_engines)}):</b>\n"
        for detection in suspicious_engines[:5]:  # Limit to first 5
            response += f"{detection}\n"
        if len(suspicious_engines) > 5:
            response += f"... and {len(suspicious_engines) - 5} more\n"
        response += "\n"

    # Show some clean results
    if harmless_engines:
        response += f"<b>🟢 Clean ({len(harmless_engines)}):</b>\n"
        for detection in harmless_engines[:3]:  # Show first 3
            response += f"{detection}\n"
        if len(harmless_engines) > 3:
            response += f"... and {len(harmless_engines) - 3} more\n"
        response += "\n"

    # Show undetected count
    if undetected_engines:
        response += f"<b>⚪ Undetected:</b> {len(undetected_engines)} engines\n\n"

    # Show other categories if any
    if other_engines:
        response += f"<b>⚫ Other:</b> {len(other_engines)} engines\n\n"

    # Create buttons
    buttons = ButtonMaker()
    buttons.data_button("🔙 Back", f"vt_back_{scan_id}")
    buttons.data_button("❌ Close", f"vt_close_{scan_id}")

    return response, buttons.build_menu(2)


def _format_signatures(scan_data: dict, scan_id: str) -> tuple[str, object]:
    """Format malware signatures."""
    signatures = scan_data["signatures"]

    if not signatures:
        response = (
            "ℹ️ <b>No malware signatures found</b>\n\nThis file appears to be clean."
        )
    else:
        response = f"<b>🦠 Malware Signatures ({len(signatures)})</b>\n\n"

        # Show signatures (limit to prevent message being too long)
        for _i, signature in enumerate(signatures[:15]):  # Show first 15
            response += f"• {html.escape(str(signature))}\n"

        if len(signatures) > 15:
            response += f"\n... and {len(signatures) - 15} more signatures"

    # Create buttons
    buttons = ButtonMaker()
    buttons.data_button("🔙 Back", f"vt_back_{scan_id}")
    buttons.data_button("❌ Close", f"vt_close_{scan_id}")

    return response, buttons.build_menu(2)


@new_task
async def vt_callback_handler(_, query):
    """Handle VirusTotal callback queries."""

    def safe_answer(message, show_alert=False):
        """Safely answer callback query with error handling."""

        async def _answer():
            try:
                await query.answer(message, show_alert=show_alert)
            except Exception as e:
                error_msg = str(e).lower()
                if (
                    "query_id_invalid" in error_msg
                    or "query id is invalid" in error_msg
                ):
                    # Query has already been answered or expired, ignore silently
                    pass
                else:
                    LOGGER.warning(f"Failed to answer VT callback query: {e}")

        return _answer()

    try:
        data = query.data
        user_id = query.from_user.id

        # Parse callback data
        if not data.startswith("vt_"):
            return

        parts = data.split("_", 2)
        if len(parts) < 3:
            await safe_answer("❌ Invalid callback data")
            return

        action = parts[1]  # det, sig, back, close
        scan_id = parts[2]

        # Check if scan result exists
        if scan_id not in VT_SCAN_RESULTS:
            await safe_answer("❌ Scan result expired")
            return

        scan_result = VT_SCAN_RESULTS[scan_id]

        # Check if user is authorized (scan owner)
        if scan_result.get("user_id") != user_id:
            await safe_answer("❌ Unauthorized")
            return

        scan_data = scan_result["scan_data"]

        if action == "det":
            # Show detections
            response, buttons = _format_detections(scan_data, scan_id)
            await edit_message(query.message, response, buttons)
            await safe_answer("🔍 Showing detections")

        elif action == "sig":
            # Show signatures
            response, buttons = _format_signatures(scan_data, scan_id)
            await edit_message(query.message, response, buttons)
            await safe_answer("🦠 Showing signatures")

        elif action == "back":
            # Go back to main results
            if scan_result.get("is_url"):
                response, buttons = _format_url_results(
                    scan_result["url"], scan_data, scan_result["vt_link"], scan_id
                )
            else:
                response, buttons = _format_basic_results(
                    scan_result["file_name"],
                    scan_result["file_size"],
                    scan_data,
                    scan_result["vt_link"],
                    scan_id,
                )
            await edit_message(query.message, response, buttons)
            await safe_answer("🔙 Back to results")

        elif action == "close":
            # Close and clean up
            VT_SCAN_RESULTS.pop(scan_id, None)

            await edit_message(query.message, "✅ <b>VirusTotal scan closed</b>")
            await safe_answer("❌ Closed")

    except Exception as e:
        LOGGER.error(f"Error in VT callback handler: {e}")
        await safe_answer("❌ Error processing request")


async def cleanup_old_scan_results():
    """Clean up scan results older than 1 hour."""
    current_time = time.time()
    expired_keys = []

    for scan_id, scan_result in VT_SCAN_RESULTS.items():
        if current_time - scan_result.get("timestamp", 0) > 3600:  # 1 hour
            expired_keys.append(scan_id)

    for key in expired_keys:
        del VT_SCAN_RESULTS[key]

    if expired_keys:
        LOGGER.info(f"Cleaned up {len(expired_keys)} expired VT scan results")


# Schedule periodic cleanup
from bot.helper.ext_utils.bot_utils import SetInterval

# Clean up old scan results every 30 minutes
if Config.VT_ENABLED:
    SetInterval(1800, cleanup_old_scan_results)  # 1800 seconds = 30 minutes


class VirusTotalClient:
    def __init__(self):
        """Initialize the VirusTotal client."""
        self.client = VTClient(Config.VT_API_KEY, timeout=Config.VT_API_TIMEOUT)
        self._error_codes = {400: "Invalid API key", 429: "Rate limit exceeded"}

    async def _handle_api_error(self, e: APIError, delay=None):
        if e.code == 429 and delay is not None:
            LOGGER.info(
                f"{self._error_codes[e.code]}. Retrying in {delay} seconds..."
            )
            await asyncio.sleep(delay)
        else:
            raise Exception(
                f"{self._error_codes.get(e.code, f'API Error ({e.code})')}: {e.message}"
            )

    async def analyze_file(self, file_path: str) -> dict:
        """Analyze a file using VirusTotal."""
        try:
            # Upload the file
            # Note: Using blocking open() because VirusTotal API expects a file object, not bytes
            with open(file_path, "rb") as f:
                analysis = await self.client.scan_file_async(
                    f, wait_for_completion=True
                )

            result = analysis.to_dict()
            result.update(
                {
                    "file_name": os.path.basename(file_path),
                    "file_size": os.path.getsize(file_path),
                    "link": self._get_analysis_url(analysis.id),
                }
            )
            # Extract relevant information
            return result
        except APIError as e:
            await self._handle_api_error(e)
            raise
        except Exception as e:
            LOGGER.error(f"Error analyzing file: {e}")
            raise

    async def analyze_url(self, url: str) -> dict:
        """Analyze a URL using VirusTotal."""
        try:
            # Get URL analysis
            analysis = await self.client.scan_url_async(
                url, wait_for_completion=True
            )
            result = analysis.to_dict()
            result.update({"url": url, "link": self._get_analysis_url(analysis.id)})
            # Extract relevant information
            return result
        except APIError as e:
            await self._handle_api_error(e)
            raise
        except Exception as e:
            LOGGER.error(f"Error analyzing URL: {e}")
            raise

    def _get_analysis_url(self, analysis_id: str) -> str:
        # URL analysis
        if analysis_id.startswith("u-"):
            _, hash_value, _ = analysis_id.split("-")
            return f"https://www.virustotal.com/gui/url/{hash_value}"

        # File analysis
        decode_id = base64.b64decode(analysis_id).decode("utf-8")
        hash_value, _ = decode_id.split(":")
        return f"https://www.virustotal.com/gui/file/{hash_value}/analysis"

    async def close(self):
        """Close the VirusTotal client."""
        try:
            await self.client.close()
        except RuntimeError:
            # Ignore "this event loop is already running" errors
            pass
        except Exception as e:
            LOGGER.error(f"Error closing VirusTotal client: {e}")


def create_vt_client():
    """Create a new VirusTotal client if enabled and API key is set."""
    if Config.VT_ENABLED and Config.VT_API_KEY:
        return VirusTotalClient()
    return None


async def scan_file(client, message, file_msg):
    """Scan a file for viruses using VirusTotal."""
    # Get file information
    if file_msg.document:
        file_name = file_msg.document.file_name
        file_size = file_msg.document.file_size
        # We don't need file_id here as we'll use the file_msg directly for download
    elif file_msg.video:
        file_name = (
            file_msg.video.file_name if file_msg.video.file_name else "video.mp4"
        )
        file_size = file_msg.video.file_size
        # We don't need file_id here as we'll use the file_msg directly for download
    elif file_msg.audio:
        file_name = (
            file_msg.audio.file_name if file_msg.audio.file_name else "audio.mp3"
        )
        file_size = file_msg.audio.file_size
        # We don't need file_id here as we'll use the file_msg directly for download
    elif file_msg.photo:
        file_name = f"photo_{int(time.time())}.jpg"
        file_size = (
            file_msg.photo.file_size if hasattr(file_msg.photo, "file_size") else 0
        )
        # We don't need file_id here as we'll use the file_msg directly for download
    else:
        error_msg = await send_message(message, "Unsupported file type.")
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Check file size
    if file_size > Config.VT_MAX_FILE_SIZE:
        error_msg = await send_message(
            message,
            f"File size exceeds the maximum allowed size for VirusTotal scanning ({get_readable_file_size(Config.VT_MAX_FILE_SIZE)}).",
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Send initial message
    status_msg = await send_message(
        message, "⏳ Downloading file for virus scanning..."
    )
    # Auto-delete status message after 5 minutes (only if it's an error)
    status_delete_task = create_task(auto_delete_message(status_msg, time=300))

    # Create a new VirusTotal client for this scan
    vt_client = create_vt_client()
    if not vt_client:
        error_msg = await edit_message(
            status_msg, "❌ Failed to initialize VirusTotal client."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    file_path = None
    try:
        # Download the file
        file_path = os.path.join(DOWNLOAD_DIR, f"vt_{file_name}")
        await client.download_media(message=file_msg, file_name=file_path)

        # Update status message
        await edit_message(status_msg, "⏳ Analyzing file with VirusTotal...")

        # Analyze the file
        result = await vt_client.analyze_file(file_path)

        # Extract and process scan data
        scan_data = _extract_scan_data(result)

        # Generate unique scan ID
        scan_id = f"{message.from_user.id}_{int(time.time())}"

        # Store scan result for callback handling
        VT_SCAN_RESULTS[scan_id] = {
            "user_id": message.from_user.id,
            "scan_data": scan_data,
            "file_name": file_name,
            "file_size": file_size,
            "vt_link": result.get("link", ""),
            "is_url": False,
            "timestamp": time.time(),
        }

        # Format response with buttons
        response, buttons = _format_basic_results(
            file_name, file_size, scan_data, result.get("link", ""), scan_id
        )

        # Send results
        await edit_message(status_msg, response, buttons)

    except Exception as e:
        LOGGER.error(f"Error in VirusTotal scan: {e}")
        # For error messages, keep the auto-deletion
        error_msg = await edit_message(status_msg, f"❌ Error scanning file: {e}")
        # No need to cancel the status_delete_task as it will auto-delete the error message
    else:
        # If scan was successful, cancel the auto-deletion task for the result message
        status_delete_task.cancel()
    finally:
        # Clean up
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                LOGGER.error(f"Error removing temporary file: {e}")

        # Close the client
        if vt_client:
            await vt_client.close()


async def scan_url(message, url):
    """Scan a URL for viruses using VirusTotal."""
    # Send initial message
    status_msg = await send_message(
        message, f"⏳ Analyzing URL with VirusTotal: {url}"
    )
    # Auto-delete status message after 5 minutes (only if it's an error)
    status_delete_task = create_task(auto_delete_message(status_msg, time=300))

    # Create a new VirusTotal client for this scan
    vt_client = create_vt_client()
    if not vt_client:
        error_msg = await edit_message(
            status_msg, "❌ Failed to initialize VirusTotal client."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    try:
        # Analyze the URL
        result = await vt_client.analyze_url(url)

        # Extract and process scan data
        scan_data = _extract_scan_data(result)

        # Generate unique scan ID
        scan_id = f"{message.from_user.id}_{int(time.time())}"

        # Store scan result for callback handling
        VT_SCAN_RESULTS[scan_id] = {
            "user_id": message.from_user.id,
            "scan_data": scan_data,
            "url": url,
            "vt_link": result.get("link", ""),
            "is_url": True,
            "timestamp": time.time(),
        }

        # Format response with buttons
        response, buttons = _format_url_results(
            url, scan_data, result.get("link", ""), scan_id
        )

        # Send results
        await edit_message(status_msg, response, buttons)

    except Exception as e:
        LOGGER.error(f"Error in VirusTotal URL scan: {e}")
        # For error messages, keep the auto-deletion
        error_msg = await edit_message(status_msg, f"❌ Error scanning URL: {e}")
        # No need to cancel the status_delete_task as it will auto-delete the error message
    else:
        # If scan was successful, cancel the auto-deletion task for the result message
        status_delete_task.cancel()
    finally:
        # Close the client
        if vt_client:
            await vt_client.close()


@new_task
async def virustotal_scan(client, message):
    """
    Command handler for /virustotal
    Scans a file or URL for viruses using VirusTotal
    """
    # Auto-delete command message after 5 minutes
    create_task(auto_delete_message(message, time=300))

    # Check if VirusTotal is enabled
    if not Config.VT_ENABLED:
        error_msg = await send_message(
            message, "VirusTotal scanning is disabled. Enable it in bot settings."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Check if API key is set
    if not Config.VT_API_KEY:
        error_msg = await send_message(
            message, "VirusTotal API key is not set. Please set it in bot settings."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Check if VirusTotal client can be created
    if not create_vt_client():
        error_msg = await send_message(
            message, "Failed to initialize VirusTotal client."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Check if this is a reply to a message
    replied = message.reply_to_message

    # Auto-delete replied message after 5 minutes if it exists
    if replied:
        create_task(auto_delete_message(replied, time=300))

    # If this is a command with a URL
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        url = args[1].strip()
        if is_url(url):
            await scan_url(message, url)
            return

    # If this is a reply to a message with a URL
    if replied and replied.text:
        text = replied.text
        urls = [word for word in text.split() if is_url(word)]
        if urls:
            await scan_url(message, urls[0])
            return

    # If this is a reply to a file
    if replied and (
        replied.document or replied.video or replied.audio or replied.photo
    ):
        await scan_file(client, message, replied)
        return

    # Auto PM scanning has been removed

    # If none of the above, show usage instructions
    error_msg = await send_message(
        message,
        "Please use one of the following methods:\n"
        "1. Reply to a file with /virustotal to scan it\n"
        "2. Reply to a message containing a URL with /virustotal\n"
        "3. Use /virustotal <url> to scan a URL directly",
    )
    # Auto-delete error message after 5 minutes
    create_task(auto_delete_message(error_msg, time=300))
