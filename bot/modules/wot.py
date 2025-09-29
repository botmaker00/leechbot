import asyncio
import socket
from logging import getLogger
from urllib.parse import quote, urlparse

import idna
from httpx import AsyncClient, RequestError, TimeoutException

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)

LOGGER = getLogger(__name__)

# WOT Category Mapping (from API documentation)
WOT_CATEGORIES = {
    # Negative categories
    101: "Malware or viruses",
    102: "Poor customer experience",
    103: "Phishing",
    104: "Scam",
    105: "Potentially illegal",
    # Questionable categories
    201: "Misleading claims or unethical",
    202: "Privacy risks",
    203: "Suspicious",
    204: "Hate, discrimination",
    205: "Spam",
    206: "Potentially unwanted programs",
    207: "Ads / pop-ups",
    # Neutral categories
    301: "Online tracking",
    302: "Alternative or controversial medicine",
    303: "Opinions, religion, politics",
    304: "Other",
    # Positive categories
    501: "Good site",
    # Child safety categories
    401: "Adult content",
    402: "Incidental nudity",
    403: "Gruesome or shocking",
    404: "Site for kids",
}

# Blacklist type descriptions (from API documentation)
BLACKLIST_TYPES = {
    "malware": "The site is blacklisted for hosting malware",
    "phishing": "The site is blacklisted for hosting a phishing page",
    "scam": "The site is blacklisted for hosting a scam (e.g. a rogue pharmacy)",
    "spam": "The site is blacklisted for sending spam or being advertised in spam",
    "gambling": "The site is blacklisted for being a gambling website",
    "adult": "The site is blacklisted for hosting adult content",
}

# AbuseIPDB Category Mapping (from API documentation)
ABUSEIPDB_CATEGORIES = {
    1: "DNS Compromise",
    2: "DNS Poisoning",
    3: "Fraud Orders",
    4: "DDoS Attack",
    5: "FTP Brute-Force",
    6: "Ping of Death",
    7: "Phishing",
    8: "Fraud VoIP",
    9: "Open Proxy",
    10: "Web Spam",
    11: "Email Spam",
    12: "Blog Spam",
    13: "VPN IP",
    14: "Port Scan",
    15: "Hacking",
    16: "SQL Injection",
    17: "Spoofing",
    18: "Brute-Force",
    19: "Bad Web Bot",
    20: "Exploited Host",
    21: "Web App Attack",
    22: "SSH",
    23: "IoT Targeted",
}

# AbuseIPDB Usage Type descriptions
ABUSEIPDB_USAGE_TYPES = {
    "Commercial": "🏢 Commercial organization",
    "Organization": "🏛️ Non-profit organization",
    "Government": "🏛️ Government entity",
    "Military": "🪖 Military organization",
    "University/College/School": "🎓 Educational institution",
    "Library": "📚 Library",
    "Content Delivery Network": "🌐 CDN service",
    "Fixed Line ISP": "🌐 Internet service provider",
    "Mobile ISP": "📱 Mobile internet provider",
    "Data Center/Web Hosting/Transit": "🖥️ Data center/hosting",
    "Search Engine Spider": "🕷️ Search engine crawler",
    "Reserved": "🔒 Reserved address space",
}


class AbuseIPDBApi:
    """AbuseIPDB API client for IP reputation checking"""

    def __init__(self):
        self.base_url = Config.ABUSEIPDB_API_URL.rstrip("/")
        self.timeout = Config.ABUSEIPDB_TIMEOUT
        self.api_key = Config.ABUSEIPDB_API_KEY
        self.max_age_days = Config.ABUSEIPDB_MAX_AGE_DAYS

    async def check_ip(self, ip_address: str) -> dict:
        """Check IP reputation using AbuseIPDB API v2"""
        try:
            # Prepare headers
            headers = {
                "User-Agent": "AimLeechBot/1.0",
                "Accept": "application/json",
                "Key": self.api_key,
            }

            if not self.api_key:
                return {
                    "success": False,
                    "error": "AbuseIPDB API requires an API key. Please configure ABUSEIPDB_API_KEY in bot settings.",
                }

            # URL encode IP address (required for IPv6 due to colons)
            encoded_ip = quote(ip_address, safe="")

            # Prepare query parameters
            params = {
                "ipAddress": encoded_ip,
                "maxAgeInDays": self.max_age_days,
                "verbose": "",  # Flag to include reports and country name
            }

            url = f"{self.base_url}/check"

            async with AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                if response.status_code == 400:
                    return {
                        "success": False,
                        "error": "Invalid IP address or parameters",
                    }
                if response.status_code == 401:
                    return {
                        "success": False,
                        "error": "Invalid API key. Please check your AbuseIPDB credentials.",
                    }
                if response.status_code == 402:
                    return {
                        "success": False,
                        "error": "Payment required. Your AbuseIPDB subscription may have expired.",
                    }
                if response.status_code == 422:
                    return {
                        "success": False,
                        "error": "Unprocessable entity. Check parameter values (maxAgeInDays must be 1-365).",
                    }
                if response.status_code == 429:
                    # Extract rate limit information from headers
                    retry_after = response.headers.get("Retry-After", "unknown")
                    rate_limit = response.headers.get("X-RateLimit-Limit", "unknown")
                    remaining = response.headers.get(
                        "X-RateLimit-Remaining", "unknown"
                    )
                    reset_time = response.headers.get("X-RateLimit-Reset", "unknown")

                    return {
                        "success": False,
                        "error": f"Rate limit exceeded. Daily limit: {rate_limit}, Remaining: {remaining}, Retry after: {retry_after} seconds, Reset at: {reset_time}",
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
            LOGGER.error(f"Unexpected error in AbuseIPDB API check: {e}")
            return {"success": False, "error": f"Unexpected error: {e!s}"}

    async def check_network(self, network: str) -> dict:
        """Check network/subnet using AbuseIPDB check-block endpoint"""
        try:
            # Prepare headers
            headers = {
                "User-Agent": "AimLeechBot/1.0",
                "Accept": "application/json",
                "Key": self.api_key,
            }

            if not self.api_key:
                return {
                    "success": False,
                    "error": "AbuseIPDB API requires an API key. Please configure ABUSEIPDB_API_KEY in bot settings.",
                }

            # URL encode network (required due to forward slash in CIDR notation)
            encoded_network = quote(network, safe="")

            # Prepare query parameters
            params = {
                "network": encoded_network,
                "maxAgeInDays": self.max_age_days,
            }

            url = f"{self.base_url}/check-block"

            async with AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                if response.status_code == 400:
                    return {
                        "success": False,
                        "error": "Invalid network or parameters",
                    }
                if response.status_code == 401:
                    return {
                        "success": False,
                        "error": "Invalid API key. Please check your AbuseIPDB credentials.",
                    }
                if response.status_code == 402:
                    return {
                        "success": False,
                        "error": "Payment required. Network size may exceed your subscription limits.",
                    }
                if response.status_code == 422:
                    return {
                        "success": False,
                        "error": "Unprocessable entity. Check network format and parameter values.",
                    }
                if response.status_code == 429:
                    # Extract rate limit information from headers
                    retry_after = response.headers.get("Retry-After", "unknown")
                    return {
                        "success": False,
                        "error": f"Rate limit exceeded. Retry after: {retry_after} seconds",
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
            LOGGER.error(f"Unexpected error in AbuseIPDB network check: {e}")
            return {"success": False, "error": f"Unexpected error: {e!s}"}


class WOTApi:
    """WOT (Web of Trust) API client for website reputation checking"""

    def __init__(self):
        self.base_url = Config.WOT_API_URL.rstrip("/")
        self.timeout = Config.WOT_TIMEOUT
        self.api_key = Config.WOT_API_KEY
        self.user_id = Config.WOT_USER_ID

    async def check_website(self, targets: list[str]) -> dict:
        """Check website reputation using WOT API v3"""
        try:
            # Prepare headers
            headers = {
                "User-Agent": "AimLeechBot/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # Add required headers for WOT API v3
            if self.api_key and self.user_id:
                headers["x-api-key"] = self.api_key
                headers["x-user-id"] = self.user_id
            else:
                return {
                    "success": False,
                    "error": "WOT API requires both API key and User ID. Please configure WOT_API_KEY and WOT_USER_ID in bot settings.",
                }

            # Prepare query parameters (max 10 targets per API docs)
            # Format: ?t=target1&t=target2&t=target3
            target_params = "&".join([f"t={target}" for target in targets[:10]])
            url = f"{self.base_url}/v3/targets?{target_params}"

            async with AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                if response.status_code == 400:
                    return {"success": False, "error": "Invalid request parameters"}
                if response.status_code == 403:
                    return {
                        "success": False,
                        "error": "Invalid API key or User ID. Please check your WOT credentials.",
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
            LOGGER.error(f"Unexpected error in WOT API check: {e}")
            return {"success": False, "error": f"Unexpected error: {e!s}"}


def is_network_cidr(input_text: str) -> bool:
    """Check if input is a valid CIDR network notation"""
    try:
        if "/" not in input_text:
            return False

        ip_part, prefix_part = input_text.split("/", 1)

        # Check if IP part is valid
        if not is_ip_address(ip_part):
            return False

        # Check if prefix is valid
        prefix = int(prefix_part)

        # IPv4: /0 to /32, IPv6: /0 to /128
        if ":" in ip_part:  # IPv6
            return 0 <= prefix <= 128
        # IPv4
        return 0 <= prefix <= 32

    except (ValueError, AttributeError):
        return False


def is_ip_address(input_text: str) -> bool:
    """Check if input is a valid IP address (IPv4 or IPv6)"""
    try:
        socket.inet_pton(socket.AF_INET, input_text)
        return True
    except OSError:
        try:
            socket.inet_pton(socket.AF_INET6, input_text)
            return True
        except OSError:
            return False


def extract_ip_from_url(url: str) -> str:
    """Extract IP address from URL if present"""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()

        # Remove port if present
        if ":" in host and not host.startswith("["):  # IPv4 with port
            host = host.split(":")[0]
        elif host.startswith("[") and "]:" in host:  # IPv6 with port
            host = host.split("]:")[0][1:]

        if is_ip_address(host):
            return host
    except Exception:
        pass
    return ""


async def resolve_domain_to_ip(domain: str) -> list[str]:
    """Resolve domain to IP addresses"""
    try:
        # Use asyncio to run the blocking getaddrinfo call
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, socket.getaddrinfo, domain, None, socket.AF_UNSPEC
        )

        ips = []
        for _family, _type, _proto, _canonname, sockaddr in result:
            ip = sockaddr[0]
            if ip not in ips and is_ip_address(ip):
                ips.append(ip)

        return ips[:3]  # Limit to first 3 IPs to avoid too many requests
    except Exception as e:
        LOGGER.debug(f"Failed to resolve domain {domain}: {e}")
        return []


def clean_domain(input_text: str) -> str:
    """
    Clean and extract domain from various input formats
    Supports Internationalized Domain Names (IDN) as per RFC 3490
    Returns cleaned domain name
    """
    input_text = input_text.strip()

    # Remove protocol if present
    if input_text.startswith(("http://", "https://")):
        try:
            parsed = urlparse(input_text)
            domain = parsed.netloc.lower()
        except Exception:
            domain = input_text.lower()
    else:
        domain = input_text.lower()

    # Remove www. prefix if present
    domain = domain.removeprefix("www.")

    # Handle Internationalized Domain Names (IDN)
    # Convert to ASCII representation as per RFC 3490
    try:
        # Try to encode as IDN (this will convert unicode domains to ASCII)
        domain = idna.encode(domain).decode("ascii")
    except (idna.core.IDNAError, UnicodeError):
        # If IDN encoding fails, keep the original domain
        pass

    return domain


def get_reputation_status(reputation: int) -> tuple[str, str]:
    """Get reputation status and emoji based on score"""
    if reputation >= 80:
        return "Excellent", "🟢"
    if reputation >= 60:
        return "Good", "🟡"
    if reputation >= 40:
        return "Unsatisfactory", "🟠"
    if reputation >= 20:
        return "Poor", "🔴"
    return "Very Poor", "⚫"


def get_safety_status(status: str) -> tuple[str, str]:
    """Get safety status emoji and description"""
    status_map = {
        "SAFE": ("✅", "Safe"),
        "NOT_SAFE": ("❌", "Not Safe"),
        "SUSPICIOUS": ("⚠️", "Suspicious"),
        "UNKNOWN": ("❓", "Unknown"),
    }
    return status_map.get(status, ("❓", "Unknown"))


def get_abuse_confidence_status(score: int) -> tuple[str, str]:
    """
    Get abuse confidence status and emoji based on score
    Following AbuseIPDB recommendations:
    - 75-100%: Recommended for denial of service
    - 25%: Hard minimum threshold
    """
    if score >= 75:
        return "Critical Risk", "🚨"
    if score >= 50:
        return "High Risk", "🔴"
    if score >= 25:
        return "Medium Risk", "🟠"
    if score > 0:
        return "Low Risk", "🟡"
    return "No Reports", "🟢"


def format_abuseipdb_categories(categories: list) -> str:
    """Format AbuseIPDB categories with descriptions"""
    if not categories:
        return "None detected"

    formatted = []
    for cat_id in categories[:5]:  # Limit to top 5 categories
        cat_description = ABUSEIPDB_CATEGORIES.get(cat_id, f"Category {cat_id}")

        # Determine category severity emoji
        if cat_id in [4, 7, 15, 16, 18, 20, 21]:  # Critical attacks
            emoji = "🚨"
        elif cat_id in [1, 2, 5, 14, 17, 22]:  # High severity
            emoji = "🔴"
        elif cat_id in [9, 10, 11, 12, 19]:  # Medium severity
            emoji = "🟠"
        elif cat_id in [3, 6, 8, 13, 23]:  # Lower severity
            emoji = "🟡"
        else:
            emoji = "📋"

        formatted.append(f"{emoji} <b>{cat_description}</b> (ID: {cat_id})")

    return "\n".join(formatted)


def format_abuseipdb_response(data: dict, ip_address: str) -> str:
    """Format AbuseIPDB API response with beautiful HTML styling"""
    if not data:
        return (
            "<blockquote>❌ <b>No data received from AbuseIPDB API</b></blockquote>"
        )

    ip_data = data.get("data", {})

    msg = "<blockquote><b>🛡️ ABUSEIPDB - IP REPUTATION CHECK</b></blockquote>\n\n"

    # IP Information
    ip_addr = ip_data.get("ipAddress", ip_address)
    is_public = ip_data.get("isPublic", False)
    ip_version = ip_data.get("ipVersion", 4)
    is_whitelisted = ip_data.get("isWhitelisted", False)

    msg += f"🌐 <b>IP Address:</b> <code>{ip_addr}</code> (IPv{ip_version})\n"
    msg += f"🔓 <b>Public IP:</b> <code>{'Yes' if is_public else 'No'}</code>\n"

    if is_whitelisted:
        msg += "✅ <b>Whitelisted:</b> <code>Yes</code>\n"

    msg += "\n"

    # Abuse Confidence Score
    abuse_score = ip_data.get("abuseConfidenceScore", 0)
    confidence_status, confidence_emoji = get_abuse_confidence_status(abuse_score)

    msg += "<b>🚨 ABUSE ASSESSMENT</b>\n"
    msg += f"{confidence_emoji} <b>Confidence Score:</b> <code>{abuse_score}% ({confidence_status})</code>\n"

    # Geographic Information
    country_code = ip_data.get("countryCode")
    country_name = ip_data.get("countryName")
    if country_code and country_name:
        msg += f"🌍 <b>Country:</b> <code>{country_name} ({country_code})</code>\n"

    # Network Information
    usage_type = ip_data.get("usageType")
    if usage_type:
        usage_emoji = ABUSEIPDB_USAGE_TYPES.get(usage_type, f"📋 {usage_type}")
        msg += f"🏢 <b>Usage Type:</b> <code>{usage_emoji}</code>\n"

    isp = ip_data.get("isp")
    if isp:
        msg += f"🌐 <b>ISP:</b> <code>{isp}</code>\n"

    domain = ip_data.get("domain")
    if domain:
        msg += f"🔗 <b>Domain:</b> <code>{domain}</code>\n"

    # Hostnames information
    hostnames = ip_data.get("hostnames", [])
    if hostnames:
        hostname_list = ", ".join(hostnames[:3])  # Limit to first 3 hostnames
        if len(hostnames) > 3:
            hostname_list += f" (+{len(hostnames) - 3} more)"
        msg += f"🏷️ <b>Hostnames:</b> <code>{hostname_list}</code>\n"

    is_tor = ip_data.get("isTor", False)
    if is_tor:
        msg += "🧅 <b>Tor Exit Node:</b> <code>Yes</code>\n"

    msg += "\n"

    # Report Statistics
    total_reports = ip_data.get("totalReports", 0)
    distinct_users = ip_data.get("numDistinctUsers", 0)
    last_reported = ip_data.get("lastReportedAt")

    msg += "<b>📊 REPORT STATISTICS</b>\n"
    msg += f"📈 <b>Total Reports:</b> <code>{total_reports}</code>\n"
    msg += f"👥 <b>Distinct Reporters:</b> <code>{distinct_users}</code>\n"

    if last_reported:
        msg += f"⏰ <b>Last Reported:</b> <code>{last_reported}</code>\n"

    # Categories
    reports = ip_data.get("reports", [])
    if reports:
        # Extract unique categories from all reports
        all_categories = set()
        for report in reports:
            all_categories.update(report.get("categories", []))

        if all_categories:
            msg += "\n<b>🏷️ THREAT CATEGORIES</b>\n"
            msg += f"{format_abuseipdb_categories(list(all_categories))}\n"

    msg += "\n"

    # Overall Assessment (Following AbuseIPDB recommendations)
    if abuse_score >= 75:
        msg += "<blockquote>🚨 <b>CRITICAL RISK:</b> This IP has a very high abuse confidence score (≥75%). AbuseIPDB recommends blocking for denial of service. Immediate action required.</blockquote>"
    elif abuse_score >= 50:
        msg += "<blockquote>🔴 <b>HIGH RISK:</b> This IP shows significant abusive behavior. Exercise extreme caution and strongly consider blocking.</blockquote>"
    elif abuse_score >= 25:
        msg += "<blockquote>🟠 <b>MEDIUM RISK:</b> This IP has reached the AbuseIPDB minimum threshold (≥25%). Monitor carefully and use caution.</blockquote>"
    elif abuse_score > 0:
        msg += "<blockquote>🟡 <b>LOW RISK:</b> This IP has minimal reported abuse (below 25% threshold). Generally safe but stay vigilant.</blockquote>"
    elif is_whitelisted:
        msg += "<blockquote>✅ <b>WHITELISTED:</b> This IP is on AbuseIPDB's whitelist and is considered trustworthy.</blockquote>"
    else:
        msg += "<blockquote>✅ <b>CLEAN:</b> No abuse reports found for this IP address. Appears to be safe.</blockquote>"

    return msg


def format_categories(categories: list) -> str:
    """Format categories with confidence levels and proper descriptions"""
    if not categories:
        return "None detected"

    formatted = []
    for category in categories[:5]:  # Limit to top 5 categories
        cat_id = category.get("id", 0)
        cat_name = category.get("name", "Unknown").title()
        confidence = category.get("confidence", 0)

        # Get proper category description from mapping
        cat_description = WOT_CATEGORIES.get(cat_id, cat_name)

        # Determine category severity emoji
        if cat_id in [101, 103, 104, 105]:  # Critical threats
            emoji = "🚨"
        elif cat_id in [102, 201, 202, 203, 204, 205, 206, 207]:  # Questionable
            emoji = "⚠️"
        elif cat_id in [301, 302, 303, 304]:  # Neutral
            emoji = "ℹ️"
        elif cat_id == 501:  # Good site
            emoji = "✅"
        elif cat_id in [401, 402, 403]:  # Adult/inappropriate content
            emoji = "🔞"
        elif cat_id == 404:  # Site for kids
            emoji = "👶"
        else:
            emoji = "📋"

        formatted.append(
            f"{emoji} <b>{cat_description}</b> (Confidence: {confidence}%)"
        )

    return "\n".join(formatted)


def format_wot_response(data: list, original_input: str) -> str:
    """Format WOT API response with beautiful HTML styling"""
    if not data:
        return "<blockquote>❌ <b>No data received from WOT API</b></blockquote>"

    msg = "<blockquote><b>🛡️ WOT - WEBSITE REPUTATION CHECK</b></blockquote>\n\n"

    for target_data in data:
        target = target_data.get("target", "Unknown")
        safety = target_data.get("safety", {})
        child_safety = target_data.get("childSafety", {})
        categories = target_data.get("categories", [])
        blacklist = target_data.get("blackList", [])

        # Website header
        msg += f"🌐 <b>Website:</b> <code>{target}</code>\n\n"

        # Safety Information
        safety_status = safety.get("status", "UNKNOWN")
        safety_reputation = safety.get("reputations", 0)
        safety_confidence = safety.get("confidence", 0)

        safety_emoji, safety_text = get_safety_status(safety_status)
        rep_status, rep_emoji = get_reputation_status(safety_reputation)

        msg += "<b>🛡️ SAFETY ASSESSMENT</b>\n"
        msg += f"{safety_emoji} <b>Status:</b> <code>{safety_text}</code>\n"
        msg += f"{rep_emoji} <b>Reputation:</b> <code>{safety_reputation}/100 ({rep_status})</code>\n"
        msg += f"📊 <b>Confidence:</b> <code>{safety_confidence}%</code>\n\n"

        # Child Safety Information
        if child_safety:
            child_reputation = child_safety.get("reputations", 0)
            child_confidence = child_safety.get("confidence", 0)
            child_status, child_emoji = get_reputation_status(child_reputation)

            msg += "<b>👶 CHILD SAFETY</b>\n"
            msg += f"{child_emoji} <b>Rating:</b> <code>{child_reputation}/100 ({child_status})</code>\n"
            msg += f"📊 <b>Confidence:</b> <code>{child_confidence}%</code>\n\n"

        # Categories
        if categories:
            msg += "<b>🏷️ THREAT CATEGORIES</b>\n"
            msg += f"<code>{format_categories(categories)}</code>\n\n"

        # Blacklist Information
        if blacklist:
            msg += "<b>🚫 BLACKLIST STATUS</b>\n"
            blacklist_details = []
            for bl_type in blacklist:
                bl_description = BLACKLIST_TYPES.get(
                    bl_type.lower(), f"Listed in {bl_type} blacklist"
                )
                blacklist_details.append(
                    f"🚫 <b>{bl_type.title()}:</b> {bl_description}"
                )
            msg += "\n".join(blacklist_details) + "\n\n"

        # Overall Assessment with Confidence Thresholds
        # Following WOT's recommendation: confidence ≥ 10 for warnings
        confidence_threshold = 10

        if safety_status == "NOT_SAFE" or blacklist:
            msg += "<blockquote>🚨 <b>WARNING:</b> This website has been flagged as unsafe or malicious. Avoid visiting or sharing personal information.</blockquote>"
        elif safety_status == "SUSPICIOUS" or (
            safety_reputation < 40 and safety_confidence >= confidence_threshold
        ):
            msg += "<blockquote>⚠️ <b>CAUTION:</b> This website shows suspicious activity or has a poor reputation. Exercise caution when visiting.</blockquote>"
        elif (
            safety_status == "SAFE"
            and safety_reputation >= 60
            and safety_confidence >= confidence_threshold
        ):
            msg += "<blockquote>✅ <b>SAFE:</b> This website appears to be trustworthy and safe to visit.</blockquote>"
        elif safety_confidence < confidence_threshold:
            msg += "<blockquote>❓ <b>INSUFFICIENT DATA:</b> Not enough reliable data to determine website safety. Confidence level too low for assessment.</blockquote>"
        else:
            msg += "<blockquote>❓ <b>UNKNOWN:</b> Insufficient data to determine website safety. Use caution when visiting.</blockquote>"

        msg += "\n" + "─" * 40 + "\n\n"

    return msg.rstrip("\n─ ")


def format_combined_response(
    wot_data: list | None = None,
    abuseipdb_data: dict | None = None,
    target: str = "",
) -> str:
    """Format combined WOT and AbuseIPDB response"""
    msg = "<blockquote><b>🛡️ COMPREHENSIVE REPUTATION CHECK</b></blockquote>\n\n"
    msg += f"🎯 <b>Target:</b> <code>{target}</code>\n\n"

    # Summary section
    wot_available = wot_data and len(wot_data) > 0
    abuseipdb_available = abuseipdb_data and abuseipdb_data.get("data")

    msg += "<b>📊 DATA SOURCES</b>\n"
    msg += f"🌐 <b>WOT (Web of Trust):</b> <code>{'✅ Available' if wot_available else '❌ Not Available'}</code>\n"
    msg += f"🛡️ <b>AbuseIPDB:</b> <code>{'✅ Available' if abuseipdb_available else '❌ Not Available'}</code>\n\n"

    # Overall Risk Assessment
    overall_risk = "UNKNOWN"
    risk_emoji = "❓"
    risk_details = []

    if wot_available:
        wot_target = wot_data[0]
        safety = wot_target.get("safety", {})
        safety_status = safety.get("status", "UNKNOWN")
        safety_reputation = safety.get("reputations", 0)

        if safety_status == "NOT_SAFE" or safety_reputation < 40:
            risk_details.append("WOT: Unsafe/Poor reputation")
            if overall_risk in ["UNKNOWN", "LOW", "MEDIUM"]:
                overall_risk = "HIGH"
        elif safety_status == "SUSPICIOUS" or safety_reputation < 60:
            risk_details.append("WOT: Suspicious/Questionable")
            if overall_risk in ["UNKNOWN", "LOW"]:
                overall_risk = "MEDIUM"
        elif safety_status == "SAFE" and safety_reputation >= 60:
            risk_details.append("WOT: Safe/Good reputation")
            if overall_risk == "UNKNOWN":
                overall_risk = "LOW"

    if abuseipdb_available:
        abuse_score = abuseipdb_data["data"].get("abuseConfidenceScore", 0)

        if abuse_score >= 75:
            risk_details.append(
                "AbuseIPDB: Critical risk (≥75% - recommended for blocking)"
            )
            overall_risk = "HIGH"
        elif abuse_score >= 50:
            risk_details.append("AbuseIPDB: High risk (≥50%)")
            if overall_risk in ["UNKNOWN", "LOW"]:
                overall_risk = "MEDIUM"
        elif abuse_score >= 25:
            risk_details.append("AbuseIPDB: Medium risk (≥25% - minimum threshold)")
            if overall_risk == "UNKNOWN":
                overall_risk = "LOW"
        elif abuse_score > 0:
            risk_details.append("AbuseIPDB: Low risk (below 25% threshold)")
            if overall_risk == "UNKNOWN":
                overall_risk = "LOW"
        elif abuse_score == 0:
            risk_details.append("AbuseIPDB: No abuse reports")
            if overall_risk == "UNKNOWN":
                overall_risk = "LOW"

    # Set risk emoji
    if overall_risk == "HIGH":
        risk_emoji = "🚨"
    elif overall_risk == "MEDIUM":
        risk_emoji = "🟠"
    elif overall_risk == "LOW":
        risk_emoji = "🟢"

    msg += "<b>⚡ OVERALL RISK ASSESSMENT</b>\n"
    msg += f"{risk_emoji} <b>Risk Level:</b> <code>{overall_risk}</code>\n"

    if risk_details:
        msg += "📋 <b>Factors:</b>\n"
        for detail in risk_details:
            msg += f"  • {detail}\n"

    msg += "\n" + "─" * 40 + "\n\n"

    # Detailed WOT Data
    if wot_available:
        wot_section = format_wot_response(wot_data, target)
        # Extract just the content part (remove header)
        wot_content = wot_section.split(
            "🛡️ WOT - WEBSITE REPUTATION CHECK</b></blockquote>\n\n", 1
        )
        if len(wot_content) > 1:
            msg += wot_content[1] + "\n"

    # Detailed AbuseIPDB Data
    if abuseipdb_available:
        abuseipdb_section = format_abuseipdb_response(abuseipdb_data, target)
        # Extract just the content part (remove header)
        abuseipdb_content = abuseipdb_section.split(
            "🛡️ ABUSEIPDB - IP REPUTATION CHECK</b></blockquote>\n\n", 1
        )
        if len(abuseipdb_content) > 1:
            msg += abuseipdb_content[1] + "\n"

    # Final recommendation
    if overall_risk == "HIGH":
        msg += "<blockquote>🚨 <b>RECOMMENDATION:</b> HIGH RISK detected. This target shows significant malicious indicators. Avoid interaction and consider blocking.</blockquote>"
    elif overall_risk == "MEDIUM":
        msg += "<blockquote>⚠️ <b>RECOMMENDATION:</b> MEDIUM RISK detected. Exercise caution when interacting with this target. Monitor for suspicious activity.</blockquote>"
    elif overall_risk == "LOW":
        msg += "<blockquote>✅ <b>RECOMMENDATION:</b> LOW RISK detected. This target appears relatively safe, but maintain standard security practices.</blockquote>"
    else:
        msg += "<blockquote>❓ <b>RECOMMENDATION:</b> Insufficient data for assessment. Use standard security precautions when interacting with this target.</blockquote>"

    return msg


@new_task
async def wot_command(_, message):
    """
    Command handler for /wot
    Performs website reputation checks using WOT (Web of Trust) API
    """
    # Delete the command message instantly
    await delete_message(message)

    # Check if at least one module is enabled
    if not Config.WOT_ENABLED and not Config.ABUSEIPDB_ENABLED:
        error_msg = await send_message(
            message,
            "<blockquote>❌ <b>Reputation checking modules are currently disabled.</b>\n\n"
            "Please contact the bot owner to enable WOT or AbuseIPDB modules.</blockquote>",
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
            "<b>Usage:</b> <code>/wot &lt;website_url_or_domain_or_ip&gt;</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/wot google.com</code> (domain reputation)\n"
            "• <code>/wot https://example.com</code> (URL analysis)\n"
            "• <code>/wot 8.8.8.8</code> (IP reputation)\n"
            "• <code>/wot 2001:4860:4860::8888</code> (IPv6 support)\n"
            "• <code>/wot 192.168.1.0/24</code> (network analysis)\n"
            "• <code>/wot google.com 8.8.8.8</code> (multiple targets)\n"
            "• <code>/wot site1.com,192.168.1.1</code> (comma-separated)\n"
            "• <code>/wot ääkkönen.fi</code> (IDN support)\n\n"
            "<b>📝 Note:</b> Supports domains, IPs, networks (CIDR), and URLs. Uses WOT + AbuseIPDB for comprehensive analysis.</blockquote>",
        )
        await auto_delete_message(error_msg, time=300)
        return

    input_text = cmd_parts[1].strip()
    if not input_text:
        error_msg = await send_message(
            message,
            "<blockquote>❌ <b>Empty Input</b>\n\n"
            "Please provide a website URL or domain to check.</blockquote>",
        )
        await auto_delete_message(error_msg, time=300)
        return

    # Support multiple domains (space or comma separated, max 10 per API limit)
    domains = []
    if "," in input_text:
        domains = [d.strip() for d in input_text.split(",") if d.strip()]
    else:
        domains = [d.strip() for d in input_text.split() if d.strip()]

    # Limit to 10 domains as per API documentation
    domains = domains[:10]

    if not domains:
        error_msg = await send_message(
            message,
            "<blockquote>❌ <b>Invalid Input</b>\n\n"
            "Please provide valid website URLs or domains to check.</blockquote>",
        )
        await auto_delete_message(error_msg, time=300)
        return

    # Determine what we're checking
    target = domains[0] if len(domains) == 1 else f"{len(domains)} targets"

    # Check if input contains IP addresses, networks, or domains
    ip_addresses = []
    networks = []
    domain_names = []

    for domain in domains:
        # Check if it's a network in CIDR notation first
        if is_network_cidr(domain.strip()):
            networks.append(domain.strip())
        else:
            cleaned = clean_domain(domain)

            # Check if it's an IP address
            if is_ip_address(cleaned):
                ip_addresses.append(cleaned)
            else:
                # Check if URL contains IP
                ip_from_url = extract_ip_from_url(domain)
                if ip_from_url:
                    ip_addresses.append(ip_from_url)
                else:
                    domain_names.append(cleaned)

    # Show processing message
    enabled_services = []
    if Config.WOT_ENABLED:
        enabled_services.append("WOT")
    if Config.ABUSEIPDB_ENABLED:
        enabled_services.append("AbuseIPDB")

    services_text = " & ".join(enabled_services)

    status_msg = await send_message(
        message,
        f"<blockquote>🔍 <b>Checking reputation with {services_text}...</b>\n\n"
        f"Analyzing {target} for trustworthiness and security threats.</blockquote>",
    )

    try:
        wot_result = None
        abuseipdb_results = []

        # Perform WOT check for domains
        if Config.WOT_ENABLED and domain_names:
            wot_client = WOTApi()
            wot_result = await wot_client.check_website(domain_names)

        # Perform AbuseIPDB check for IPs
        if Config.ABUSEIPDB_ENABLED and ip_addresses:
            abuseipdb_client = AbuseIPDBApi()
            for ip in ip_addresses[:3]:  # Limit to 3 IPs to avoid rate limits
                ip_result = await abuseipdb_client.check_ip(ip)
                abuseipdb_results.append((ip, ip_result))

        # Perform AbuseIPDB network check for CIDR networks
        if Config.ABUSEIPDB_ENABLED and networks:
            abuseipdb_client = AbuseIPDBApi()
            for network in networks[:2]:  # Limit to 2 networks to avoid rate limits
                network_result = await abuseipdb_client.check_network(network)
                abuseipdb_results.append((f"Network {network}", network_result))

        # If we have domains but no direct IPs, try to resolve domains to IPs for AbuseIPDB
        if (
            Config.ABUSEIPDB_ENABLED
            and domain_names
            and not ip_addresses
            and not networks
        ):
            abuseipdb_client = AbuseIPDBApi()
            for domain in domain_names[
                :2
            ]:  # Limit to 2 domains to avoid too many requests
                resolved_ips = await resolve_domain_to_ip(domain)
                for ip in resolved_ips[:1]:  # Take only first IP per domain
                    ip_result = await abuseipdb_client.check_ip(ip)
                    abuseipdb_results.append((f"{ip} (from {domain})", ip_result))

        # Delete status message
        await delete_message(status_msg)

        # Determine response format
        use_combined = (wot_result and wot_result.get("success")) or any(
            result[1].get("success") for result in abuseipdb_results
        )

        if use_combined and len(domains) == 1:
            # Use combined format for single target
            wot_data = (
                wot_result.get("data")
                if wot_result and wot_result.get("success")
                else None
            )
            abuseipdb_data = None

            # Get the best AbuseIPDB result
            for ip_label, result in abuseipdb_results:
                if result.get("success"):
                    abuseipdb_data = result
                    break

            response_text = format_combined_response(
                wot_data, abuseipdb_data, domains[0]
            )

        else:
            # Use separate format for multiple targets or when only one service works
            response_parts = []

            # Add WOT results
            if wot_result and wot_result.get("success"):
                wot_text = format_wot_response(
                    wot_result["data"], " ".join(domain_names)
                )
                response_parts.append(wot_text)

            # Add AbuseIPDB results
            for ip_label, result in abuseipdb_results:
                if result.get("success"):
                    abuseipdb_text = format_abuseipdb_response(result, ip_label)
                    response_parts.append(abuseipdb_text)

            if response_parts:
                response_text = "\n\n" + "═" * 50 + "\n\n".join(response_parts)
            else:
                response_text = "<blockquote>❌ <b>No successful results from any reputation service</b></blockquote>"

        if use_combined or response_parts:
            response_msg = await send_message(message, response_text)
            # Auto-delete after 10 minutes
            await auto_delete_message(response_msg, time=600)
        else:
            # Handle errors
            error_messages = []

            if wot_result and not wot_result.get("success"):
                error_messages.append(
                    f"WOT: {wot_result.get('error', 'Unknown error')}"
                )

            for ip_label, result in abuseipdb_results:
                if not result.get("success"):
                    error_messages.append(
                        f"AbuseIPDB ({ip_label}): {result.get('error', 'Unknown error')}"
                    )

            if error_messages:
                error_text = "\n".join(error_messages)
                error_msg = await send_message(
                    message,
                    f"<blockquote>❌ <b>API Errors</b>\n\n"
                    f"<code>{error_text}</code>\n\n"
                    f"Please check your API configurations or try again later.</blockquote>",
                )
                await auto_delete_message(error_msg, time=600)

    except Exception as e:
        LOGGER.error(f"Unexpected error in wot_command: {e}")
        await delete_message(status_msg)
        error_msg = await send_message(
            message,
            f"<blockquote>❌ <b>Unexpected Error</b>\n\n"
            f"An unexpected error occurred while processing your request.\n\n"
            f"<b>Error:</b> <code>{e!s}</code></blockquote>",
        )
        await auto_delete_message(error_msg, time=300)
