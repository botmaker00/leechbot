import asyncio
import re
from asyncio import create_task, get_event_loop
from re import IGNORECASE, findall, search
from time import time
from typing import Any

from imdb import Cinemagoer
from imdb._exceptions import IMDbDataAccessError, IMDbError
from pycountry import countries as conn
from pyrogram.errors import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from pyrogram.types import Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

# Initialize Cinemagoer instance
imdb = Cinemagoer()

# Cache for IMDB data to improve performance
_imdb_cache: dict[str, dict[str, Any]] = {}
_cache_timeout = 3600  # 1 hour cache timeout
_max_cache_size = 100  # Maximum number of cached entries


def _cleanup_cache():
    """Remove expired entries from cache"""
    current_time = time()
    expired_keys = [
        key
        for key, value in _imdb_cache.items()
        if current_time - value.get("timestamp", 0) > _cache_timeout
    ]
    for key in expired_keys:
        del _imdb_cache[key]

    # If cache is still too large, remove oldest entries
    if len(_imdb_cache) > _max_cache_size:
        sorted_items = sorted(
            _imdb_cache.items(), key=lambda x: x[1].get("timestamp", 0)
        )
        # Keep only the newest entries
        for key, _ in sorted_items[:-_max_cache_size]:
            del _imdb_cache[key]


def _safe_extract_list_content(
    content_list: list | None, max_items: int = 3
) -> str | None:
    """Safely extract and format list content with error handling"""
    if not content_list or not isinstance(content_list, list):
        return None

    try:
        # Take only the first max_items and convert to string
        limited_content = content_list[:max_items]
        return list_to_str(limited_content) if limited_content else None
    except Exception as e:
        LOGGER.warning(f"Error extracting list content: {e}")
        return None


IMDB_GENRE_EMOJI = {
    "Action": "🚀",
    "Adult": "🔞",
    "Adventure": "🌋",
    "Animation": "🎠",
    "Biography": "📜",
    "Comedy": "🪗",
    "Crime": "🔪",
    "Documentary": "🎞",
    "Drama": "🎭",
    "Family": "👨‍👩‍👧‍👦",
    "Fantasy": "🫧",
    "Film Noir": "🎯",
    "Game Show": "🎮",
    "History": "🏛",
    "Horror": "🧟",
    "Musical": "🎻",
    "Music": "🎸",
    "Mystery": "🧳",
    "News": "📰",
    "Reality-TV": "🖥",
    "Romance": "🥰",
    "Sci-Fi": "🌠",
    "Short": "📝",
    "Sport": "⛳",
    "Talk-Show": "👨‍🍳",
    "Thriller": "🗡",
    "War": "⚔",
    "Western": "🪩",
}
LIST_ITEMS = 4


def _is_cache_valid(cache_entry: dict[str, Any]) -> bool:
    """Check if cache entry is still valid"""
    return time() - cache_entry.get("timestamp", 0) < _cache_timeout


def _get_cache_key(query: str, is_id: bool = False) -> str:
    """Generate cache key for IMDB data"""
    return f"imdb_{'id' if is_id else 'search'}_{query.lower()}"


def list_to_str(k):
    """Convert list to string with proper formatting"""
    if not k:
        return None  # Return None instead of "N/A" so it can be filtered out
    if len(k) == 1:
        return str(k[0])
    # Limit items if needed
    if LIST_ITEMS:
        k = k[:LIST_ITEMS]
    return ", ".join(f"{elem}" for elem in k)


def list_to_hash(k, country=False, emoji=False):
    """Convert list to hashtag string with proper formatting"""
    if not k:
        return None  # Return None instead of "N/A" so it can be filtered out

    # Handle single item case
    if len(k) == 1:
        if emoji and k[0] in IMDB_GENRE_EMOJI:
            return f"{IMDB_GENRE_EMOJI[k[0]]} #{k[0].replace(' ', '_')}"
        if country:
            try:
                return f"#{conn.get(name=k[0]).alpha_2}"
            except (AttributeError, KeyError):
                return f"#{k[0].replace(' ', '_')}"
        return f"#{k[0].replace(' ', '_')}"

    # Limit items if needed
    if LIST_ITEMS:
        k = k[:LIST_ITEMS]

    # Format multiple items
    if emoji:
        return " ".join(
            f"{IMDB_GENRE_EMOJI.get(elem, '')} #{elem.replace(' ', '_')}"
            for elem in k
        )
    if country:
        return " ".join(
            f"#{conn.get(name=elem).alpha_2}"
            if elem in [c.name for c in conn]
            else f"#{elem.replace(' ', '_')}"
            for elem in k
        )
    return " ".join(f"#{elem.replace(' ', '_')}" for elem in k)


async def _async_search_movie(title: str, results: int = 10) -> list[Any]:
    """Async wrapper for IMDB movie search with timeout"""
    loop = get_event_loop()
    try:
        # Add timeout to prevent hanging
        return await asyncio.wait_for(
            loop.run_in_executor(None, imdb.search_movie, title.lower(), results),
            timeout=15.0,  # 15 second timeout
        )
    except TimeoutError:
        LOGGER.error(f"Timeout searching movie '{title}'")
        return []
    except IMDbDataAccessError as e:
        LOGGER.warning(f"IMDb data access error searching movie '{title}': {e}")
        return []
    except IMDbError as e:
        LOGGER.warning(f"IMDb error searching movie '{title}': {e}")
        return []
    except Exception as e:
        LOGGER.error(f"Unexpected error searching movie '{title}': {e}")
        return []


async def _async_get_movie(movie_id: str | int) -> Any | None:
    """Async wrapper for IMDB get_movie with timeout"""
    loop = get_event_loop()
    try:
        # Add timeout to prevent hanging
        return await asyncio.wait_for(
            loop.run_in_executor(None, imdb.get_movie, movie_id),
            timeout=10.0,  # 10 second timeout
        )
    except TimeoutError:
        LOGGER.error(f"Timeout getting movie '{movie_id}'")
        return None
    except IMDbDataAccessError as e:
        LOGGER.warning(f"IMDb data access error getting movie '{movie_id}': {e}")
        return None
    except IMDbError as e:
        LOGGER.warning(f"IMDb error getting movie '{movie_id}': {e}")
        return None
    except Exception as e:
        LOGGER.error(f"Unexpected error getting movie '{movie_id}': {e}")
        return None


async def _async_update_movie(
    movie: Any, info_sets: list[str], max_retries: int = 1
) -> None:
    """Async wrapper for IMDB movie update with multiple info sets and timeout"""
    loop = get_event_loop()

    async def update_single_info(info_set: str):
        for attempt in range(max_retries + 1):
            try:
                # Add timeout for each info set update
                await asyncio.wait_for(
                    loop.run_in_executor(None, imdb.update, movie, [info_set]),
                    timeout=8.0,  # 8 second timeout per info set
                )
                LOGGER.debug(
                    f"Successfully updated {info_set} info (attempt {attempt + 1})"
                )
                return  # Success, exit retry loop
            except TimeoutError:
                if attempt < max_retries:
                    LOGGER.warning(
                        f"Timeout updating {info_set} info (attempt {attempt + 1}/{max_retries + 1}), retrying..."
                    )
                    await asyncio.sleep(1)  # Brief delay before retry
                else:
                    LOGGER.warning(
                        f"Final timeout updating {info_set} info after {max_retries + 1} attempts"
                    )
            except IMDbDataAccessError as e:
                # Handle specific IMDb data access errors (like HTTP 500 from IMDb servers)
                if attempt < max_retries and "500" in str(e):
                    LOGGER.warning(
                        f"IMDb server error updating {info_set} info (attempt {attempt + 1}/{max_retries + 1}), retrying..."
                    )
                    await asyncio.sleep(2)  # Longer delay for server errors
                else:
                    LOGGER.warning(
                        f"IMDb data access error updating {info_set} info: {e}"
                    )
                    break  # Don't retry for non-server errors
            except IMDbError as e:
                LOGGER.warning(f"IMDb error updating {info_set} info: {e}")
                break  # Don't retry for IMDb errors
            except Exception as e:
                LOGGER.warning(f"Unexpected error updating {info_set} info: {e}")
                break  # Don't retry for unexpected errors

    # Run all updates concurrently for better performance
    tasks = [update_single_info(info_set) for info_set in info_sets]
    await asyncio.gather(*tasks, return_exceptions=True)


def _is_field_available(value: Any) -> bool:
    """Check if a field has meaningful data (not N/A, empty, or unavailable)"""
    # Handle None, empty, or whitespace values
    if value is None:
        return False

    # Handle empty lists, dicts, sets
    if isinstance(value, list | dict | set | tuple) and len(value) == 0:
        return False

    # Handle numeric values (0 is valid, but negative might not be for some fields)
    if isinstance(value, int | float):
        return value >= 0  # Allow 0 as valid (e.g., 0 votes is still information)

    # Handle boolean values (False is still valid information)
    if isinstance(value, bool):
        return True

    # Convert to string for text analysis
    value_str = str(value).strip()

    # Empty string check
    if not value_str or value_str.isspace():
        return False

    # Check for various "not available" indicators (exact matches)
    na_indicators = {
        "N/A",
        "n/a",
        "N/a",
        "n/A",
        "Not Available",
        "not available",
        "NOT AVAILABLE",
        "unavailable",
        "Unavailable",
        "UNAVAILABLE",
        "temporarily unavailable",
        "information temporarily unavailable",
        "Plot under wraps.",
        "None",
        "none",
        "NONE",
        "null",
        "NULL",
        "Null",
        "undefined",
        "UNDEFINED",
        "Undefined",
        "unknown",
        "Unknown",
        "UNKNOWN",
        "TBD",
        "tbd",
        "To Be Determined",
        "Coming Soon",
        "coming soon",
        "COMING SOON",
        "No information available",
        "No data available",
        "Data not available",
        "Information not found",
        "Not specified",
        "Not provided",
        "Not disclosed",
        "Pending",
        "TBA",
        "tba",
        "To Be Announced",
    }

    # Exact match check
    if value_str in na_indicators:
        return False

    # Check for partial matches for unavailable messages (case insensitive)
    unavailable_patterns = [
        "temporarily unavailable",
        "information temporarily unavailable",
        "unavailable due to",
        "currently unavailable",
        "not available",
        "no information",
        "no data",
        "data not found",
        "information not found",
        "details not available",
        "coming soon",
        "to be announced",
        "to be determined",
        "under wraps",
        "not disclosed",
        "not specified",
        "not provided",
        "pending",
        "unknown at this time",
        "information pending",
        "details pending",
    ]

    # Pattern match check (case insensitive)
    value_lower = value_str.lower()
    for pattern in unavailable_patterns:
        if pattern in value_lower:
            return False

    # Check for placeholder patterns (e.g., "---", "...", "???")
    placeholder_patterns = [
        r"^-+$",  # Only dashes: ---, ----
        r"^\.+$",  # Only dots: ..., ....
        r"^\?+$",  # Only question marks: ???, ????
        r"^_+$",  # Only underscores: ___, ____
        r"^#+$",  # Only hashes: ###, ####
        r"^\*+$",  # Only asterisks: ***, ****
        r"^=+$",  # Only equals: ===, ====
        r"^\s*-\s*$",  # Single dash with optional spaces
        r"^\s*\.\s*$",  # Single dot with optional spaces
    ]

    return all(not re.match(pattern, value_str) for pattern in placeholder_patterns)


def _build_dynamic_template(data: dict[str, Any], compact_mode: bool = False) -> str:
    """Build completely dynamic template based on available data only"""
    template_parts = []

    # Define field priorities (higher priority = more important)
    if compact_mode:
        # Compact mode: Only essential fields
        field_definitions = [
            ("title", "<b>🎬 Title:</b> <code>{title}</code> [{year}]", True),
            ("rating", "<b>⭐ Rating:</b> <i>{rating}</i>", False),
            ("genres", "<b>🎭 Genre:</b> {genres}", False),
            ("kind", "<b>🎬 Type:</b> {kind}", False),
            ("plot", "PLOT_SECTION", False),
            ("runtime", "<b>⏱️ Runtime:</b> {runtime} minutes", False),
            ("director", "<b>👨‍💼 Director:</b> {director}", False),
            ("cast", "<b>👥 Cast:</b> {cast}", False),
        ]
    else:
        # Full mode: All possible fields
        field_definitions = [
            # Basic Information (always show title)
            ("title", "<b>🎬 Title:</b> <code>{title}</code> [{year}]", True),
            ("rating", "<b>⭐ Rating:</b> <i>{rating}</i>", False),
            ("genres", "<b>🎭 Genre:</b> {genres}", False),
            (
                "release_date",
                '<b>📅 Released:</b> <a href="{url_releaseinfo}">{release_date}</a>',
                False,
            ),
            ("languages", "<b>🎙️ Languages:</b> {languages}", False),
            ("countries", "<b>🌍 Country:</b> {countries}", False),
            ("kind", "<b>🎬 Type:</b> {kind}", False),
            # Plot section (special handling)
            ("plot", "PLOT_SECTION", False),
            # Technical Information
            ("runtime", "<b>⏱️ Runtime:</b> {runtime} minutes", False),
            ("keywords", "<b>🏷️ Keywords:</b> {keywords}", False),
            ("certificates", "<b>🏆 Certificates:</b> {certificates}", False),
            # Cast & Crew (if available)
            ("cast", "<b>👥 Cast:</b> {cast}", False),
            ("director", "<b>👨‍💼 Director:</b> {director}", False),
            ("writer", "<b>✍️ Writer:</b> {writer}", False),
            ("producer", "<b>🎬 Producer:</b> {producer}", False),
            ("composer", "<b>🎵 Music:</b> {composer}", False),
            (
                "cinematographer",
                "<b>🎥 Cinematography:</b> {cinematographer}",
                False,
            ),
            # Additional Content
            ("trivia", "<b>🎭 Trivia:</b> {trivia}", False),
            ("quotes", "<b>💬 Quotes:</b> {quotes}", False),
            ("taglines", "<b>🏷️ Taglines:</b> {taglines}", False),
            ("goofs", "<b>😅 Goofs:</b> {goofs}", False),
            ("synopsis", "<b>📝 Synopsis:</b> {synopsis}", False),
            # Business Information
            ("box_office", "<b>💰 Box Office:</b> {box_office}", False),
            ("distributors", "<b>🏢 Distributors:</b> {distributors}", False),
            # TV Series Specific
            ("seasons", "<b>📺 Seasons:</b> {seasons}", False),
            # Alternative titles
            ("aka", "<b>🌐 Also Known As:</b> {aka}", False),
            ("localized_title", "<b>🗺️ Local Title:</b> {localized_title}", False),
            # Technical details
            ("votes", "<b>🗳️ Votes:</b> {votes}", False),
            ("tech_info", "<b>🔧 Technical:</b> {tech_info}", False),
        ]

    # Process each field and add to template if available
    for field_name, template_format, always_show in field_definitions:
        field_value = data.get(field_name)

        if always_show or _is_field_available(field_value):
            if field_name == "plot" and _is_field_available(field_value):
                # Special handling for plot section
                plot_text = str(field_value)
                if compact_mode and len(plot_text) > 200:
                    # Truncate plot in compact mode
                    plot_text = plot_text[:200] + "..."

                template_parts.append("")  # Empty line
                template_parts.append("<b>📖 Story Line:</b>")
                template_parts.append(f"<blockquote>{plot_text}</blockquote>")
            elif template_format != "PLOT_SECTION":
                template_parts.append(template_format)

    # Always add IMDb links section (essential)
    if template_parts:  # Only if we have some content
        template_parts.append("")  # Empty line
        template_parts.append('<b>🔗 IMDb URL:</b> <a href="{url}">{url}</a>')

        # Only show cast & crew link if we don't have cast info in the template
        if not any("Cast:" in part for part in template_parts):
            template_parts.append(
                '<b>👥 Cast & Crew:</b> <a href="{url_cast}">View on IMDb</a>'
            )

    # Add footer
    template_parts.append("")  # Empty line

    # Only show unavailability note if we're missing cast/crew data and not in compact mode
    if not compact_mode:
        has_cast_crew = any(
            field in list(template_parts)
            for field in ["Cast:", "Director:", "Writer:"]
        )

        if not has_cast_crew:
            template_parts.append(
                "<i>⚠️ Note: Cast/crew details temporarily unavailable due to IMDb changes</i>"
            )

    template_parts.append("<i>Powered by IMDb</i>")

    return "\n".join(template_parts)


def _truncate_caption_for_telegram(
    caption: str, data: dict[str, Any] | None = None, max_length: int = 1024
) -> str:
    """Truncate caption to fit Telegram's media caption limit with smart strategies"""
    if len(caption) <= max_length:
        return caption

    # Strategy 1: Try compact mode if data is available
    if data:
        try:
            compact_template = _build_dynamic_template(data, compact_mode=True)
            compact_caption = compact_template.format(**data)
            if len(compact_caption) <= max_length:
                return compact_caption
        except Exception:
            pass  # Fall back to truncation if compact mode fails

    # Strategy 2: Remove less important sections progressively
    lines = caption.split("\n")

    # Remove sections in order of importance (least important first)
    sections_to_remove = [
        "🎭 Trivia:",
        "💬 Quotes:",
        "🏷️ Taglines:",
        "😅 Goofs:",
        "🏢 Distributors:",
        "💰 Box Office:",
        "🔧 Technical:",
        "🗳️ Votes:",
        "🌐 Also Known As:",
        "🗺️ Local Title:",
        "🏆 Certificates:",
        "🏷️ Keywords:",
        "🎵 Music:",
        "🎥 Cinematography:",
        "✍️ Writer:",
        "🎬 Producer:",
    ]

    for section in sections_to_remove:
        if len("\n".join(lines)) <= max_length:
            break

        # Remove lines containing this section
        lines = [line for line in lines if section not in line]

    # Strategy 3: Truncate plot if still too long
    if len("\n".join(lines)) > max_length:
        for i, line in enumerate(lines):
            if "<blockquote>" in line and len(line) > 100:
                # Truncate long plot
                plot_content = line.replace("<blockquote>", "").replace(
                    "</blockquote>", ""
                )
                if len(plot_content) > 150:
                    truncated_plot = plot_content[:150] + "..."
                    lines[i] = f"<blockquote>{truncated_plot}</blockquote>"
                break

    # Strategy 4: Final truncation if still too long
    result = "\n".join(lines)
    if len(result) > max_length:
        # Truncate at a good breaking point
        truncated = result[: max_length - 80]  # Leave room for truncation message

        # Find the last complete line or sentence
        last_newline = truncated.rfind("\n")
        last_period = truncated.rfind(".")
        last_break = max(last_newline, last_period)

        if last_break > max_length * 0.7:  # If we can keep at least 70% of content
            truncated = result[: last_break + 1]
        else:
            # Just truncate at word boundary
            last_space = truncated.rfind(" ")
            if last_space > max_length * 0.8:
                truncated = result[:last_space]

        # Add truncation notice
        result = (
            truncated
            + "\n\n<i>... (truncated for Telegram limits)</i>\n<i>Powered by IMDb</i>"
        )

    return result


def _safe_format_template(
    template: str, data: dict[str, Any], fallback_template: str | None = None
) -> str:
    """Safely format template with data, filtering out N/A values"""

    # Filter out N/A and unavailable data
    filtered_data = {}
    for key, value in data.items():
        if _is_field_available(value):
            filtered_data[key] = value
        # Keep essential fields even if N/A for template compatibility
        elif key in ["title", "year", "url", "url_cast", "url_releaseinfo", "kind"]:
            filtered_data[key] = value if value else "Unknown"
        else:
            filtered_data[key] = ""  # Empty string for unavailable optional fields

    # Build dynamic template based on available data
    dynamic_template = _build_dynamic_template(filtered_data)

    # Minimal template for when even basic data is missing
    minimal_template = """<b>🎬 Title:</b> <code>{title}</code> [{year}]
<b>🎬 Type:</b> {kind}

<b>📖 Story Line:</b>
<blockquote>{plot}</blockquote>

<b>🔗 IMDb URL:</b> <a href=\"{url}\">{url}</a>

<i>Powered by IMDb</i>"""

    try:
        # Try dynamic template first
        return dynamic_template.format(**filtered_data)
    except KeyError as e:
        LOGGER.warning(f"Missing key in dynamic template: {e}")
        try:
            # Try original template
            return template.format(**filtered_data)
        except KeyError as e2:
            LOGGER.warning(f"Missing key in original template: {e2}")
            if fallback_template:
                try:
                    return fallback_template.format(**filtered_data)
                except Exception as e3:
                    LOGGER.warning(f"Fallback template also failed: {e3}")

            # Try minimal template
            try:
                return minimal_template.format(**filtered_data)
            except Exception as e4:
                LOGGER.error(f"Minimal template also failed: {e4}")

                # Return basic info if all templates fail
                title = filtered_data.get("title", "Unknown")
                year = filtered_data.get("year", "Unknown")
                url = filtered_data.get("url", "#")
                return f'<b>🎬 Title:</b> {title} [{year}]\n<b>🔗 IMDb URL:</b> <a href="{url}">{url}</a>'

    except Exception as e:
        LOGGER.error(f"Template formatting error: {e}")
        title = filtered_data.get("title", "Unknown")
        year = filtered_data.get("year", "Unknown")
        url = filtered_data.get("url", "#")
        return f'<b>🎬 Title:</b> {title} [{year}]\n<b>🔗 IMDb URL:</b> <a href="{url}">{url}</a>'


async def imdb_search(_, message: Message):
    """Handle IMDB search command"""
    # Check if IMDB module is enabled
    if not Config.IMDB_ENABLED:
        error_msg = await send_message(
            message,
            "❌ <b>IMDB module is currently disabled.</b>\n\nPlease contact the bot owner to enable it.",
        )
        # Schedule for auto-deletion after 5 minutes
        create_task(auto_delete_message(error_msg, message, time=300))  # noqa: RUF006
        return

    # Updated template focusing on available data
    default_template = """<b>🎬 Title:</b> <code>{title}</code> [{year}]
<b>⭐ Rating:</b> <i>{rating}</i>
<b>🎭 Genre:</b> {genres}
<b>📅 Released:</b> <a href=\"{url_releaseinfo}\">{release_date}</a>
<b>🎙️ Languages:</b> {languages}
<b>🌍 Country:</b> {countries}
<b>🎬 Type:</b> {kind}

<b>📖 Story Line:</b>
<blockquote>{plot}</blockquote>

<b>⏱️ Runtime:</b> {runtime} minutes
<b>🏷️ Keywords:</b> {keywords}
<b>🏆 Certificates:</b> {certificates}

<b>🔗 IMDb URL:</b> <a href=\"{url}\">{url}</a>
<b>👥 Cast & Crew:</b> <a href=\"{url_cast}\">View on IMDb</a>

<i>⚠️ Note: Cast/crew details temporarily unavailable due to IMDb changes</i>
<i>Powered by IMDb</i>"""

    user_id = message.from_user.id
    buttons = ButtonMaker()
    title = ""
    is_reply = False

    # Check if replying to a message
    if message.reply_to_message and message.reply_to_message.text:
        # Extract text from replied message
        title = message.reply_to_message.text.strip()
        k = await send_message(
            message,
            "<i>Searching IMDB for replied content...</i>",
        )
        is_reply = True
    elif " " in message.text:
        # User provided a search term in command
        title = message.text.split(" ", 1)[1]
        k = await send_message(message, "<i>Searching IMDB ...</i>")
    else:
        # No search term provided - schedule for auto-deletion after 5 minutes
        error_msg = await send_message(
            message,
            "<i>Send Movie / TV Series Name along with /imdb Command or reply to a message containing IMDB URL or movie/series name</i>",
        )
        # Schedule for auto-deletion after 5 minutes
        # pylint: disable=unused-variable
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )
        return

    # Check if it's an IMDB URL
    if result := search(r"imdb\.com/title/tt(\d+)", title, IGNORECASE):
        movieid = result.group(1)

        # Show loading status
        await edit_message(k, "<i>🎬 Fetching movie details...</i>")

        try:
            # Process direct IMDB link
            imdb_data = await get_poster(query=movieid, id=True)
            if imdb_data:
                # Delete messages and show result directly
                if is_reply:
                    # If replying to a message with valid IMDB link
                    await delete_message(message)
                    await delete_message(message.reply_to_message)
                    await delete_message(k)
                    chat_id = message.chat.id
                else:
                    # If command message has a valid IMDB link/key
                    await delete_message(message)
                    await delete_message(k)
                    chat_id = message.chat.id

                buttons = ButtonMaker()

                # Add trailer button if available
                if imdb_data["trailer"]:
                    if isinstance(imdb_data["trailer"], list):
                        buttons.url_button(
                            "▶️ IMDb Trailer ",
                            imdb_data["trailer"][-1],
                        )
                        imdb_data["trailer"] = list_to_str(imdb_data["trailer"])
                    else:
                        buttons.url_button("▶️ IMDb Trailer ", imdb_data["trailer"])

                buttons.data_button("🚫 Close 🚫", f"imdb {user_id} close")
                buttons = buttons.build_menu(1)

                # Get template from config or use default
                template = (
                    Config.IMDB_TEMPLATE
                    if hasattr(Config, "IMDB_TEMPLATE") and Config.IMDB_TEMPLATE
                    else default_template
                )

                # Format caption with template using safe formatter
                if imdb_data and template:
                    cap = _safe_format_template(
                        template, imdb_data, default_template
                    )
                else:
                    cap = "No Results"

                # Send result with poster
                if imdb_data.get("poster"):
                    try:
                        await TgClient.bot.send_photo(
                            chat_id=chat_id,
                            caption=cap,
                            photo=imdb_data["poster"],
                            reply_markup=buttons,
                        )
                    except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
                        # Try with alternative poster URL
                        poster = imdb_data.get("poster").replace(
                            ".jpg",
                            "._V1_UX360.jpg",
                        )
                        await send_message(
                            message,
                            cap,
                            buttons,
                            photo=poster,
                        )
                else:
                    # Send without poster
                    await send_message(
                        message,
                        cap,
                        buttons,
                        "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
                    )
                return
            # No movie found
            error_msg = await edit_message(k, "<i>No Results Found</i>")
            create_task(auto_delete_message(error_msg, message, time=300))  # noqa: RUF006
            return
        except IMDbDataAccessError as e:
            LOGGER.warning(f"IMDb data access error fetching movie details: {e}")
            error_msg = await edit_message(
                k,
                "<i>⚠️ IMDb servers are experiencing issues. Please try again later.</i>",
            )
            create_task(auto_delete_message(error_msg, message, time=300))  # noqa: RUF006
            return
        except IMDbError as e:
            LOGGER.warning(f"IMDb error fetching movie details: {e}")
            error_msg = await edit_message(
                k, "<i>❌ IMDb service error. Please try again.</i>"
            )
            create_task(auto_delete_message(error_msg, message, time=300))  # noqa: RUF006
            return
        except Exception as e:
            LOGGER.error(f"Unexpected error fetching IMDB data: {e}")
            error_msg = await edit_message(
                k, "<i>❌ Error fetching movie details. Please try again.</i>"
            )
            create_task(auto_delete_message(error_msg, message, time=300))  # noqa: RUF006
            return

    # Search for movies by title
    try:
        movies = await get_poster(title, bulk=True)
    except Exception as e:
        LOGGER.error(f"Error searching movies: {e}")
        error_msg = await edit_message(
            k, "<i>Error searching movies. Please try again.</i>"
        )
        create_task(auto_delete_message(error_msg, message, time=300))  # noqa: RUF006
        return
    if not movies:
        # No results found - schedule for auto-deletion after 5 minutes
        error_msg = await edit_message(
            k,
            "<i>No Results Found</i>, Try Again or Use <b>Title ID</b>",
        )
        # Schedule for auto-deletion after 5 minutes
        # pylint: disable=unused-variable
        create_task(  # noqa: RUF006
            auto_delete_message(error_msg, message, time=300),
        )

        # If replying to a message with invalid content, delete both messages
        if is_reply:
            await delete_message(message)
            await delete_message(message.reply_to_message)
        return

    # Add movies to buttons
    for movie in movies:
        # Get year safely, ensuring it's not None
        year = movie.get("year") if movie.get("year") else ""
        title = movie.get("title")
        # Format the button text with year only if it exists
        button_text = f"🎬 {title} ({year})" if year else f"🎬 {title}"
        buttons.data_button(
            button_text,
            f"imdb {user_id} movie {movie.movieID}",
        )

    buttons.data_button("🚫 Close 🚫", f"imdb {user_id} close")

    # Show search results and schedule for auto-deletion after 5 minutes
    results_msg = await edit_message(
        k,
        "<b><i>Search Results found on IMDb.com</i></b>",
        buttons.build_menu(1),
    )

    # If replying to a message with valid content but multiple results, delete both messages
    if is_reply:
        await delete_message(message)
        await delete_message(message.reply_to_message)

    # Schedule for auto-deletion after 5 minutes
    # pylint: disable=unused-variable
    create_task(  # noqa: RUF006
        auto_delete_message(results_msg, time=300),
    )


async def _extract_comprehensive_movie_data(movie_id: str) -> dict[str, Any]:
    """Extract comprehensive movie data using available working info sets"""
    # Get basic movie data
    movie = await _async_get_movie(movie_id)
    if not movie:
        return {}

    # Note: Cast/crew data is currently not available due to IMDB website changes
    # The cinemagoer library (2025.05.19) cannot extract cast/director/writer data
    # This is a known limitation of the current version

    # Try to get additional info using working info sets
    # Based on testing, these are the info sets that actually work:
    # Prioritize essential info sets first
    essential_info_sets = [
        "technical",  # Provides runtime, sound mix, color info
        "keywords",  # Provides keywords and relevant keywords
        "plot",  # Already included in basic data
        "release info",  # Provides release information
        "awards",  # Provides awards information
    ]

    # Optional info sets that may fail due to IMDb server issues
    optional_info_sets = [
        "quotes",  # Provides movie quotes
        "taglines",  # Provides taglines
        "connections",  # Provides movie connections
        "locations",  # Provides filming locations
        "soundtrack",  # Provides soundtrack information
    ]

    # Note: "trivia" info set is excluded as it frequently fails with HTTP 500 errors
    # from IMDb servers, causing unnecessary error logs and potential instability

    # Update movie with essential info sets first (with retries)
    await _async_update_movie(movie, essential_info_sets, max_retries=2)

    # Then try optional info sets (no retries to avoid delays)
    await _async_update_movie(movie, optional_info_sets, max_retries=0)

    # Try to extract genres from keywords as a fallback
    # Since genres are not directly available, we'll extract them from keywords
    if not movie.get("genres") and movie.get("keywords"):
        keywords = movie.get("keywords", [])
        if isinstance(keywords, list):
            # Common genre keywords that might be in the keywords list
            genre_keywords = [
                "action",
                "comedy",
                "drama",
                "horror",
                "thriller",
                "romance",
                "sci-fi",
                "fantasy",
                "adventure",
                "crime",
                "mystery",
                "animation",
                "documentary",
                "biography",
                "history",
                "war",
                "western",
                "musical",
                "family",
                "sport",
                "music",
                "short",
                "adult",
                "news",
                "reality-tv",
                "game-show",
                "talk-show",
                "film-noir",
            ]

            found_genres = []
            for keyword in keywords[:20]:  # Check first 20 keywords
                if isinstance(keyword, str):
                    keyword_lower = keyword.lower().replace("-", " ")
                    for genre in genre_keywords:
                        if (
                            genre in keyword_lower
                            and genre.title() not in found_genres
                        ):
                            found_genres.append(genre.title())

            if found_genres:
                movie["genres"] = found_genres[:5]  # Limit to 5 genres

    return movie


async def _process_movie_data(movie: Any, movie_id: str) -> dict[str, Any]:
    """Process and format movie data with proper field extraction"""

    # Get release date
    date = None
    if movie.get("original air date"):
        date = movie["original air date"]
    elif movie.get("year"):
        date = movie.get("year")

    # Get plot - handle both single plot and list of plots
    plot = movie.get("plot")
    if plot:
        if isinstance(plot, list) and len(plot) > 0:
            plot = plot[0]
        elif isinstance(plot, str):
            pass  # plot is already a string
        else:
            plot = movie.get("synopsis")
            if plot and isinstance(plot, list) and len(plot) > 0:
                plot = plot[0]

    if not plot:
        plot = "Plot under wraps."
    elif len(str(plot)) > 300:
        plot = f"{str(plot)[:300]}..."

    # Build URLs
    url = f"https://www.imdb.com/title/tt{movie_id}"
    url_cast = f"{url}/fullcredits#cast"
    url_releaseinfo = f"{url}/releaseinfo"

    # Extract runtime from tech info
    runtime = None
    tech_info = movie.get("tech", {})
    if tech_info and isinstance(tech_info, dict) and "runtime" in tech_info:
        runtime_raw = tech_info["runtime"]
        # Extract just the minutes part: "3h 1m::(181 min)" -> "181"
        if "::" in runtime_raw and "min)" in runtime_raw:
            runtime = runtime_raw.split("::(")[1].replace(" min)", "")
        else:
            runtime = runtime_raw

    # Get countries from country codes
    countries = movie.get("country codes", [])
    if countries and isinstance(countries, list):
        # Convert country codes to country names if possible
        try:
            country_names = []
            for code in countries:
                try:
                    country = conn.get(alpha_2=code.upper())
                    if country:
                        country_names.append(country.name)
                    else:
                        country_names.append(code.upper())
                except (AttributeError, KeyError):
                    country_names.append(code.upper())
            countries = country_names
        except ImportError:
            # If pycountry is not available, just use the codes
            countries = [code.upper() for code in countries]
    else:
        countries = []

    # Extract genres - try multiple approaches
    genres = movie.get("genres", [])
    if not genres:
        # Try to extract genre-like keywords
        keywords = movie.get("keywords", [])
        if keywords and isinstance(keywords, list):
            # Common genre keywords that might be in the keywords list
            genre_keywords = [
                "action",
                "comedy",
                "drama",
                "horror",
                "thriller",
                "romance",
                "sci-fi",
                "fantasy",
                "adventure",
                "crime",
                "mystery",
                "animation",
                "documentary",
                "biography",
                "history",
                "war",
                "western",
                "musical",
            ]
            found_genres = []
            for keyword in keywords[:10]:  # Check first 10 keywords
                if isinstance(keyword, str):
                    keyword_lower = keyword.lower().replace("-", " ")
                    found_genres.extend(
                        genre.title()
                        for genre in genre_keywords
                        if genre in keyword_lower
                    )
            if found_genres:
                genres = list(set(found_genres))  # Remove duplicates

    # Extract languages - try different approaches
    languages = movie.get("languages", [])
    if not languages:
        # Try to get from other fields
        languages = movie.get("language", [])

    # Extract certificates/ratings
    certificates = movie.get("certificates", [])
    if not certificates:
        certificates = movie.get("mpaa", [])

    return {
        # Basic Information
        "title": movie.get("title") or "Unknown",
        "year": movie.get("year") or "Unknown",
        "kind": movie.get("kind") or "Unknown",
        "rating": f"{movie.get('rating')} / 10" if movie.get("rating") else None,
        "votes": movie.get("votes"),
        "plot": plot,
        "synopsis": list_to_str(movie.get("synopsis"))
        if movie.get("synopsis")
        else None,
        # Media & Visual
        "poster": movie.get("full-size cover url"),
        "poster_small": movie.get("cover url"),
        "trailer": movie.get("videos"),
        # Technical Information
        "runtime": runtime,
        "tech_info": movie.get("tech"),
        # Content Classification
        "genres": list_to_hash(genres, emoji=True) if genres else None,
        "keywords": list_to_str(movie.get("keywords")[:10])
        if movie.get("keywords")
        else None,
        "certificates": list_to_str(certificates) if certificates else None,
        # Geographic & Release
        "countries": list_to_hash(countries, True) if countries else None,
        "country_codes": movie.get("country codes"),
        "languages": list_to_hash(languages) if languages else None,
        "release_dates": list_to_str(movie.get("release dates")[:5])
        if movie.get("release dates")
        else None,
        "release_date": date,
        "original_air_date": movie.get("original air date"),
        "aka": list_to_str(movie.get("akas")) if movie.get("akas") else None,
        # Cast & Crew (Currently unavailable due to IMDB website changes)
        # Note: The cinemagoer library cannot extract cast/crew data in version 2025.05.19
        "cast": None,  # Don't show unavailable cast info
        "director": None,  # Don't show unavailable director info
        "writer": None,  # Don't show unavailable writer info
        "producer": None,  # Don't show unavailable producer info
        "composer": None,  # Don't show unavailable composer info
        "cinematographer": None,  # Don't show unavailable cinematographer info
        "music_team": None,  # Don't show unavailable music team info
        # Business Information
        "box_office": movie.get("box office"),
        "distributors": list_to_str(movie.get("distributors"))
        if movie.get("distributors")
        else None,
        # Additional Content
        "trivia": _safe_extract_list_content(movie.get("trivia"), 3),
        "quotes": _safe_extract_list_content(movie.get("quotes"), 3),
        "taglines": _safe_extract_list_content(movie.get("taglines"), 3)
        if movie.get("taglines")
        else None,
        "goofs": list_to_str(movie.get("goofs")[:3]) if movie.get("goofs") else None,
        "connections": movie.get("connections"),
        # TV Series Specific
        "seasons": movie.get("number of seasons"),
        # URLs & IDs
        "imdb_id": f"tt{movie_id}",
        "url": url,
        "url_cast": url_cast,
        "url_releaseinfo": url_releaseinfo,
        # Legacy fields for compatibility
        "localized_title": movie.get("localized title"),
    }


async def get_poster(query, bulk=False, id=False, file=None):
    """Get movie/TV series information from IMDB with async operations and caching"""
    # Clean up cache periodically
    if len(_imdb_cache) > _max_cache_size * 0.8:  # Clean when 80% full
        _cleanup_cache()

    # Check cache first
    cache_key = _get_cache_key(str(query), id)
    if cache_key in _imdb_cache and _is_cache_valid(_imdb_cache[cache_key]):
        cached_data = _imdb_cache[cache_key]["data"]
        if bulk and isinstance(cached_data, list):
            return cached_data
        if not bulk and isinstance(cached_data, dict):
            return cached_data

    if not id:
        query = (query.strip()).lower()
        title = query
        year = findall(r"[1-2]\d{3}$", query, IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = findall(r"[1-2]\d{3}", file, IGNORECASE)
            if year:
                year = list_to_str(year[:1])
        else:
            year = None

        movieid = await _async_search_movie(title, results=10)
        if not movieid:
            return None

        if year:
            filtered = (
                list(filter(lambda k: str(k.get("year")) == str(year), movieid))
                or movieid
            )
        else:
            filtered = movieid

        movieid = (
            list(filter(lambda k: k.get("kind") in ["movie", "tv series"], filtered))
            or filtered
        )

        if bulk:
            # Cache bulk results
            _imdb_cache[cache_key] = {"data": movieid, "timestamp": time()}
            return movieid

        movieid = movieid[0].movieID
    else:
        movieid = query

    # Use comprehensive data extraction
    movie = await _extract_comprehensive_movie_data(str(movieid))
    if not movie:
        return None

    # Extract and process movie data with proper field mapping
    movie_data = await _process_movie_data(movie, str(movieid))

    # Cache the result for future use
    _imdb_cache[cache_key] = {"data": movie_data, "timestamp": time()}

    return movie_data


async def imdb_callback(_, query):
    """Handle IMDB callback queries"""
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()

    if user_id != int(data[1]):
        await query.answer("Not Yours!", show_alert=True)
        return

    if data[2] == "close":
        await query.answer()
        await delete_message(message)
        return

    if data[2] == "movie":
        await query.answer()

        # Show loading status immediately
        await edit_message(
            message,
            "🎬 <i>Fetching movie details...</i>\n\n⏳ Please wait while we get the information from IMDB...",
        )

        try:
            # Fetch movie data asynchronously
            imdb_data = await get_poster(query=data[3], id=True)
            if not imdb_data:
                await edit_message(message, "<i>❌ Movie details not found</i>")
                create_task(auto_delete_message(message, time=300))  # noqa: RUF006
                return

            buttons = ButtonMaker()

            # Add trailer button if available
            if imdb_data["trailer"]:
                if isinstance(imdb_data["trailer"], list):
                    buttons.url_button("▶️ IMDb Trailer ", imdb_data["trailer"][-1])
                    imdb_data["trailer"] = list_to_str(imdb_data["trailer"])
                else:
                    buttons.url_button("▶️ IMDb Trailer ", imdb_data["trailer"])

            buttons.data_button("🚫 Close 🚫", f"imdb {user_id} close")
            buttons = buttons.build_menu(1)

            # Default template with Telegram quote format
            default_template = """<b>🎬 Title:</b> <code>{title}</code> [{year}]
<b>⭐ Rating:</b> <i>{rating}</i>
<b>🎭 Genre:</b> {genres}
<b>📅 Released:</b> <a href=\"{url_releaseinfo}\">{release_date}</a>
<b>🎙️ Languages:</b> {languages}
<b>🌍 Country:</b> {countries}
<b>🎬 Type:</b> {kind}

<b>📖 Story Line:</b>
<blockquote>{plot}</blockquote>

<b>🔗 IMDb URL:</b> <a href=\"{url}\">{url}</a>
<b>👥 Cast:</b> <a href=\"{url_cast}\">{cast}</a>

<b>👨‍💼 Director:</b> {director}
<b>✍️ Writer:</b> {writer}
<b>🎵 Music:</b> {composer}
<b>🎥 Cinematography:</b> {cinematographer}

<b>⏱️ Runtime:</b> {runtime} minutes
<b>🏆 Awards:</b> {certificates}

<i>Powered by IMDb</i>"""

            # Get template from config or use default
            template = (
                Config.IMDB_TEMPLATE
                if hasattr(Config, "IMDB_TEMPLATE") and Config.IMDB_TEMPLATE
                else default_template
            )

            # Format caption with template using safe formatter
            if imdb_data and template:
                cap = _safe_format_template(template, imdb_data, default_template)
            else:
                cap = "No Results"

            # Delete the loading message immediately before sending result
            await delete_message(message)

            # If there's a reply_to_message (original command), delete it too
            if message.reply_to_message:
                await delete_message(message.reply_to_message)

            # Send result with poster as a new message
            if imdb_data.get("poster"):
                try:
                    # Truncate caption to fit Telegram's media caption limit
                    truncated_cap = _truncate_caption_for_telegram(cap, imdb_data)

                    # Send photo with caption
                    await TgClient.bot.send_photo(
                        chat_id=query.message.chat.id,
                        caption=truncated_cap,
                        photo=imdb_data["poster"],
                        reply_markup=buttons,
                    )
                except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
                    # Try with alternative poster URL
                    poster = imdb_data.get("poster").replace(
                        ".jpg", "._V1_UX360.jpg"
                    )
                    truncated_cap = _truncate_caption_for_telegram(cap, imdb_data)
                    await send_message(
                        message,
                        truncated_cap,
                        buttons,
                        photo=poster,
                    )
            else:
                # Send without poster
                truncated_cap = _truncate_caption_for_telegram(cap, imdb_data)
                await send_message(
                    message,
                    truncated_cap,
                    buttons,
                    "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
                )

        except IMDbDataAccessError as e:
            LOGGER.warning(f"IMDb data access error in callback: {e}")
            await edit_message(
                message,
                "<i>⚠️ IMDb servers are experiencing issues. Please try again later.</i>",
            )
            create_task(auto_delete_message(message, time=300))  # noqa: RUF006
        except IMDbError as e:
            LOGGER.warning(f"IMDb error in callback: {e}")
            await edit_message(
                message, "<i>❌ IMDb service error. Please try again.</i>"
            )
            create_task(auto_delete_message(message, time=300))  # noqa: RUF006
        except Exception as e:
            LOGGER.error(f"Unexpected error in IMDB callback: {e}")
            await edit_message(
                message, "<i>❌ Error fetching movie details. Please try again.</i>"
            )
            create_task(auto_delete_message(message, time=300))  # noqa: RUF006
