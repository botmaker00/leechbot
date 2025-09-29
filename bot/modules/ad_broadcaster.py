from asyncio import sleep as asyncio_sleep
from logging import getLogger

from pyrogram import filters
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from pyrogram.handlers import MessageHandler

from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.message_utils import send_message

LOGGER = getLogger(__name__)

# Default keywords to detect in messages
DEFAULT_AD_KEYWORDS = [
    "#ad",
    "#AD",
    "InsideAds",
    "AD",
    "ad",
    "Advertise",
    "advertise",
    "Advertisement",
    "ADVERTISE",
]


# Cache for ad keywords to avoid repeated logging
_ad_keywords_cache = None
_last_keywords_log_time = 0


# Function to get ad keywords (from config or default)
def get_ad_keywords():
    """Get ad keywords from config or use defaults"""
    global _ad_keywords_cache, _last_keywords_log_time
    import time

    current_time = time.time()

    if Config.AD_KEYWORDS:
        # Split by comma and strip whitespace, preserving spaces within phrases
        custom_keywords = [
            keyword.strip()
            for keyword in Config.AD_KEYWORDS.split(",")
            if keyword.strip()
        ]
        # Only log if keywords changed or it's been more than 5 minutes
        if (
            _ad_keywords_cache != custom_keywords
            or current_time - _last_keywords_log_time > 300
        ):
            LOGGER.info(f"Using custom ad keywords (phrases): {custom_keywords}")
            _ad_keywords_cache = custom_keywords
            _last_keywords_log_time = current_time
        return custom_keywords

    # Only log if keywords changed or it's been more than 5 minutes
    if (
        _ad_keywords_cache != DEFAULT_AD_KEYWORDS
        or current_time - _last_keywords_log_time > 300
    ):
        LOGGER.info(f"Using default ad keywords: {DEFAULT_AD_KEYWORDS}")
        _ad_keywords_cache = DEFAULT_AD_KEYWORDS
        _last_keywords_log_time = current_time
    return DEFAULT_AD_KEYWORDS


@new_task
async def handle_ad_message(_, message):
    """
    Handler for messages from FSUB_IDS channels that contain ad keywords
    Note: Keyword filtering is already done in the filter, so this function
    only handles messages that are confirmed to contain ad keywords
    """
    # Double-check if ad broadcaster is enabled at runtime
    if not Config.AD_BROADCASTER_ENABLED:
        return

    # Get the current ad keywords to find which one matched
    ad_keywords = get_ad_keywords()
    message_text = message.text or message.caption or ""

    # Find which keyword matched (for logging purposes)
    found_keyword = None
    for keyword in ad_keywords:
        if keyword in message_text:
            found_keyword = keyword
            break

    LOGGER.info(
        f"Ad detected with keyword/phrase: '{found_keyword or 'unknown'}' in message: {message.id}"
    )

    # Get the message link
    chat_id = message.chat.id
    message_id = message.id

    # Create message link
    message_link = f"https://t.me/c/{str(chat_id).replace('-100', '')}/{message_id}"

    # Get channel name
    try:
        channel_name = message.chat.title or "our channel"
    except Exception:
        channel_name = "our channel"

    # Create broadcast message with better formatting
    broadcast_text = (
        f"<pre>╭──────────────────────╮\n"
        f"│    📢 <b>AD BROADCAST</b> 📢    │\n"
        f"╰──────────────────────╯</pre>\n\n"
        f"<blockquote>Please click the ad to support {channel_name}! This will help us grow and buy Telegram premium for 4GB uploads.</blockquote>\n\n"
        f"<a href='{message_link}'><b>➡️ View Original Message</b></a>"
    )

    # Get all users
    pm_users = await database.get_pm_uids()
    if not pm_users:
        LOGGER.info("No users found in database for ad broadcast")
        return

    # Start broadcasting
    LOGGER.info(f"Starting ad broadcast to {len(pm_users)} users")

    successful, blocked, unsuccessful = 0, 0, 0

    for uid in pm_users:
        try:
            await send_message(uid, broadcast_text)
            successful += 1
        except FloodWait as e:
            LOGGER.warning(f"FloodWait: Sleeping for {e.value} seconds")
            await asyncio_sleep(e.value)
            try:
                await send_message(uid, broadcast_text)
                successful += 1
            except Exception as retry_err:
                LOGGER.error(
                    f"Failed to send ad broadcast to {uid} after FloodWait: {retry_err}"
                )
                unsuccessful += 1
        except (UserIsBlocked, InputUserDeactivated) as user_err:
            LOGGER.info(f"Removing user {uid} from database: {user_err}")
            await database.rm_pm_user(uid)
            blocked += 1
        except Exception as e:
            LOGGER.error(f"Error sending ad broadcast to {uid}: {e}")
            unsuccessful += 1

    LOGGER.info(
        f"Ad Broadcast completed: {successful} successful, {blocked} blocked, {unsuccessful} unsuccessful"
    )


def init_ad_broadcaster():
    """Initialize the ad broadcaster module"""
    if not Config.AD_BROADCASTER_ENABLED:
        LOGGER.info("Ad broadcaster is disabled, not initializing")
        return

    if not Config.FSUB_IDS:
        LOGGER.info("FSUB_IDS not configured, ad broadcaster not initialized")
        return

    # Log the keywords that will be used
    ad_keywords = get_ad_keywords()
    LOGGER.info(f"Ad broadcaster will detect the following keywords: {ad_keywords}")

    # Create a filter for messages from FSUB_IDS channels that contain ad keywords
    async def fsub_ad_filter(_, __, message):
        # Check if ad broadcaster is enabled at runtime
        if not Config.AD_BROADCASTER_ENABLED:
            return False

        if not Config.FSUB_IDS:
            return False

        # Check if message is from one of the FSUB_IDS channels
        chat_id = message.chat.id
        fsub_ids = [int(channel_id) for channel_id in Config.FSUB_IDS.split()]
        if chat_id not in fsub_ids:
            return False

        # Get the current ad keywords (from config or default)
        ad_keywords = get_ad_keywords()

        # Check if message contains any of the ad keywords
        message_text = message.text or message.caption or ""

        # Check if any of the keywords/phrases are in the message
        for keyword in ad_keywords:
            if keyword in message_text:
                # Keyword found, allow processing
                return True

        # No keywords found, don't process this message
        # Log this for debugging (but only occasionally to avoid spam)
        if message.id % 100 == 0:  # Log every 100th filtered message
            LOGGER.info(
                f"Message {message.id} from FSUB channel filtered out - no ad keywords found"
            )
        return False

    # Register the message handler for text messages with ad keywords
    TgClient.bot.add_handler(
        MessageHandler(
            handle_ad_message,
            filters=filters.create(fsub_ad_filter)
            & (filters.text | filters.caption),
        ),
        group=10,  # Use a high group number to ensure it's processed after other handlers
    )

    LOGGER.info("Ad broadcaster initialized")
