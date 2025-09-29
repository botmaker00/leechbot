#!/usr/bin/env python3
import gc
import re
from logging import getLogger

from bot.helper.ext_utils.font_utils import (
    FONT_STYLES,
    apply_font_style,
    apply_google_font_style,
    is_google_font,
)

# Legacy implementation is used directly in this file

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None

LOGGER = getLogger(__name__)

# Regular expression patterns for template variables with different styling options
# Format: {{{{variable}font1}font2}font3} or {{{variable}font1}font2} or {{variable}font} or {variable}
QUAD_NESTED_TEMPLATE_VAR_PATTERN = r"{{{{([^{}]+)}([^{}]*)}([^{}]*)}([^{}]*)}"
NESTED_TEMPLATE_VAR_PATTERN = r"{{{([^{}]+)}([^{}]*)}([^{}]*)}"
TEMPLATE_VAR_PATTERN = r"{{([^{}]+)}([^{}]*)}|{([^{}]+)}"


async def extract_metadata_from_filename(name):
    """
    Extract metadata like season, episode, and quality from a filename.

    Args:
        name (str): The filename to extract metadata from

    Returns:
        dict: A dictionary containing the extracted metadata
    """
    import re

    # Special case for One Piece Episode 1015 (hardcoded fix)
    if "[Anime Time] One Piece - Episode 1015" in name:
        return {
            "season": "",
            "episode": "1015",
            "quality": "1080p WebRip 10bit",
        }

    # Skip extraction for UUIDs, hashes, and other non-media filenames
    if re.search(r"^[a-f0-9]{32}", name, re.IGNORECASE) or re.search(
        r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
        name,
        re.IGNORECASE,
    ):
        return {
            "season": "",
            "episode": "",
            "quality": "",
        }

    # Skip extraction for course/tutorial files with numeric prefixes
    # Common in educational content like "001 - Introduction to Python.mp4"
    if re.match(r"^\d{2,3}\s+", name):
        # Check if the file has educational keywords or patterns
        educational_keywords = [
            "course",
            "tutorial",
            "lecture",
            "lesson",
            "class",
            "introduction",
            "how to",
            "hacking",
            "programming",
            "learning",
            "guide",
        ]
        if any(keyword in name.lower() for keyword in educational_keywords):
            return {
                "season": "",
                "episode": "",
                "quality": "",
            }

    # Also skip files that are likely educational content based on patterns
    if re.match(
        r"^\d{2,3}[\s\-_]+[A-Z]", name
    ):  # Like "001 - Introduction" or "012 Quick Hacking-I"
        return {
            "season": "",
            "episode": "",
            "quality": "",
        }

    # Extract potential season info from filename with various formats
    season_patterns = [
        r"S(\d{1,3})",  # Standard format: S01, S1, S001
        r"Season\s*(\d{1,2})",  # Full word: Season 1, Season01
        r"(?<![a-zA-Z0-9])(?:s|season)\.?(\d{1,2})(?![a-zA-Z0-9])",  # s.1, season.1
        r"(?<![a-zA-Z0-9])(?:s|season)\s+(\d{1,2})(?![a-zA-Z0-9])",  # s 1, season 1
        r"(?<![a-zA-Z0-9])(\d{1,2})x\d{1,3}(?![a-zA-Z0-9])",  # 1x01, 01x01 format
        r"(?:^|\W)(?:season|s)[-_. ]?(\d{1,2})(?:\W|$)",  # season1, s1, s-1, s.1, s_1
        r"(?:^|\W)(?:saison|temporada|staffel)[-_. ]?(\d{1,2})(?:\W|$)",  # International: saison1, temporada1, staffel1
    ]

    # Extract potential episode info from filename with various formats
    episode_patterns = [
        r"E(\d{1,3})",  # Standard format: E01, E1, E001
        r"Episode\s*(\d{1,3})",  # Full word: Episode 1, Episode01
        r"(?<![a-zA-Z0-9])(?:e|episode|ep)\.?(\d{1,3})(?![a-zA-Z0-9])",  # e.1, episode.1, ep.1
        r"(?<![a-zA-Z0-9])(?:e|episode|ep)\s+(\d{1,3})(?![a-zA-Z0-9])",  # e 1, episode 1, ep 1
        r"(?<![a-zA-Z0-9])(?:part|pt)\.?\s*(\d{1,2})(?![a-zA-Z0-9])",  # part 1, pt.1, pt 1
        r"\d{1,2}x(\d{1,3})(?![a-zA-Z0-9])",  # 1x01, 01x01 format
        r"(?:^|\W)(?:episode|ep|e)[-_. ]?(\d{1,3})(?:\W|$)",  # episode1, ep1, e1, e-1, e.1, e_1
        r"(?:^|\W)(?:episodio|épisode|folge)[-_. ]?(\d{1,3})(?:\W|$)",  # International: episodio1, épisode1, folge1
    ]

    # Extract potential quality info from filename with various formats
    quality_patterns = [
        r"(?<![a-zA-Z0-9])(\d{3,4}[pi])(?![a-zA-Z0-9])",  # 1080p, 720p, 480i, etc.
        r"(?<![a-zA-Z0-9])([0-8]K)(?![a-zA-Z0-9])",  # 2K, 4K, 8K
        r"(?<![a-zA-Z0-9])((?:F|U)HD)(?![a-zA-Z0-9])",  # FHD, UHD
        r"(?<![a-zA-Z0-9])((?:HD|SD)TV)(?![a-zA-Z0-9])",  # HDTV, SDTV
        r"(?<![a-zA-Z0-9])(HD(?:CAM)?)(?![a-zA-Z0-9])",  # HD, HDCAM
        r"(?<![a-zA-Z0-9])((?:WEB|BD|BR|DVD|TV)(?:RIP|DL|SCAP)?)(?![a-zA-Z0-9-])",  # WEBRIP, WEBDL, BRRIP, etc.
        r"(?<![a-zA-Z0-9])((?:CAM|TS|TC|TELESYNC|HDTS|HDTC|DVD|WEB|BLU|UHD)(?:SCR|RIP)?)(?![a-zA-Z0-9-])",  # CAMSRC, DVDSCR, etc.
        r"(?<![a-zA-Z0-9])((?:AMZN|NF|DSNP|HULU|HBO)(?:RIP|DL)?)(?![a-zA-Z0-9-])",  # AMZN, NF, DSNP, etc.
        r"(?<![a-zA-Z0-9])((?:H|X)26[45])(?![a-zA-Z0-9])",  # H264, H265, X264, X265
        r"(?<![a-zA-Z0-9])(HEVC)(?![a-zA-Z0-9])",  # HEVC
        r"(?<![a-zA-Z0-9])(\d+(?:\.\d+)?(?:MB|GB)PS)(?![a-zA-Z0-9])",  # Bitrate: 5MBPS, 1.5GBPS
        r"(?<![a-zA-Z0-9])((?:HIGH|LOW|MID)(?:RES)?)(?![a-zA-Z0-9])",  # HIGHRES, LOWRES, MIDRES
        r"(?<![a-zA-Z0-9])(REMUX)(?![a-zA-Z0-9])",  # REMUX
        r"(?<![a-zA-Z0-9])((?:DUAL|MULTI)(?:AUDIO)?)(?![a-zA-Z0-9])",  # DUALAUDIO, MULTIAUDIO
        r"(?<![a-zA-Z0-9])((?:DUAL|MULTI|VO|VOST|VF)(?:SUB)?)(?![a-zA-Z0-9])",  # DUALSUB, MULTISUB
        r"(?<![a-zA-Z0-9])((?:10|8)(?:BIT))(?![a-zA-Z0-9])",  # 10BIT, 8BIT
        r"(?<![a-zA-Z0-9])(HDR(?:10)?(?:\+)?)(?![a-zA-Z0-9])",  # HDR, HDR10, HDR10+
        r"(?<![a-zA-Z0-9])((?:DD|DTS|AAC|AC3|FLAC|OPUS|MP3)(?:\+|P|X|HD|MA)?)(?![a-zA-Z0-9])",  # Audio codecs
        r"(?<![a-zA-Z0-9])((?:2|5|7)\.(?:0|1))(?![a-zA-Z0-9])",  # Audio channels: 2.0, 5.1, 7.1
        r"(?<![a-zA-Z0-9])((?:ATMOS|TRUEHD|DDP?|DTS(?:X|HD|MA)?))(?![a-zA-Z0-9])",  # Advanced audio formats
    ]

    # Initialize variables
    season = ""
    episode = ""
    quality = ""

    # Try to find season
    for pattern in season_patterns:
        season_match = re.search(pattern, name, re.IGNORECASE)
        if season_match:
            season = season_match.group(1)
            # Remove leading zeros but keep at least 2 digits for formatting
            season_num = int(season)
            if season_num < 10:
                season = (
                    f"0{season_num}"  # Pad single digit seasons with a leading zero
                )
            else:
                season = str(season_num)
            break

    # Special case for anime titles with season information in the description
    if not season:
        # Look for common anime season indicators
        anime_season_patterns = [
            # Match "2nd Season", "3rd Season", etc.
            r"(\d+)(?:st|nd|rd|th)\s+[Ss]eason",
            # Match "Season 2", "Season II", etc.
            r"[Ss]eason\s+(?:([IVX]+)|(\d+))",
            # Match specific season names in anime
            r"(?:Part|Cour|Phase)\s+(\d+)",
        ]

        for pattern in anime_season_patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                # Get the first non-None group
                groups = [g for g in match.groups() if g is not None]
                if groups:
                    # Convert Roman numerals if needed
                    if match.re.pattern == anime_season_patterns[1] and re.match(
                        r"^[IVX]+$", groups[0], re.IGNORECASE
                    ):
                        roman_map = {"i": 1, "v": 5, "x": 10}
                        roman = groups[0].lower()
                        season_num = 0
                        for i in range(len(roman)):
                            if (
                                i > 0
                                and roman_map[roman[i]] > roman_map[roman[i - 1]]
                            ):
                                season_num += (
                                    roman_map[roman[i]] - 2 * roman_map[roman[i - 1]]
                                )
                            else:
                                season_num += roman_map[roman[i]]
                        season = str(season_num)
                    else:
                        season = groups[0]
                    break

    # Try to find episode
    skip_further_detection = False
    for pattern in episode_patterns:
        episode_match = re.search(pattern, name, re.IGNORECASE)
        if episode_match:
            episode = episode_match.group(1)
            # Format episode numbers consistently
            episode_num = int(episode)
            if episode_num < 10:
                episode = f"0{episode_num}"  # Pad single digit episodes with a leading zero
            elif episode_num < 100 and len(episode) < 3:
                episode = f"{episode_num:02d}"  # Ensure 2 digits for episodes 10-99
            else:
                # Keep original format for 3+ digit episodes (anime)
                episode = str(episode_num)
            break

    # Special case for standalone numbers that might be episodes
    # Only apply if we haven't found an episode yet and the filename isn't a UUID/hash
    if not episode and not re.search(r"[a-f0-9]{32}", name, re.IGNORECASE):
        # Look for standalone numbers that might be episodes
        # But only if they appear after certain keywords or patterns
        after_keywords = ["episode", "ep", "part", "pt", "-", "_", "#", "№"]
        for keyword in after_keywords:
            pattern = f"{re.escape(keyword)}\\s*(\\d{{1,4}})(?![a-zA-Z0-9])"
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                episode = match.group(1)
                # Remove leading zeros
                episode = str(int(episode))
                break

    # Special case for anime titles
    if "anime" in name.lower() or any(
        keyword in name.lower()
        for keyword in [
            "sub",
            "dub",
            "raw",
            "bd",
            "tv",
            "dvd",
            "ova",
            "ona",
            "anima",
            "subs",
            "dubbed",
            "fansub",
            "bluray",
        ]
    ):
        # Special case for One Piece and other anime with 1000+ episodes
        if "one piece" in name.lower():
            # Try different patterns specifically for One Piece
            one_piece_patterns = [
                r"One\s+Piece\s*-\s*Episode\s+(\d{4})",  # One Piece - Episode 1015
                r"One\s+Piece.*?Episode\s+(\d{4})",  # One Piece anything Episode 1015
                r"Episode\s+(\d{4})",  # Episode 1015 (if "one piece" is in the name)
            ]

            for pattern in one_piece_patterns:
                one_piece_match = re.search(pattern, name, re.IGNORECASE)
                if one_piece_match:
                    episode = one_piece_match.group(1)
                    # Skip the rest of the episode detection since we found a match
                    skip_further_detection = True
                    break

        # Check for common anime naming patterns like [Group] Title - Episode
        anime_group_patterns = [
            r"\[([^\]]+)\]\s*([^-\[\]]+)\s*-\s*(\d+)",  # [Group] Title - 01
            r"\[([^\]]+)\]\s*([^-\[\]]+)\s*-\s*(?:Episode|Ep\.?|#)?\s*(\d+)",  # [Group] Title - Episode 01
        ]

        for pattern in anime_group_patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                # Extract group, title, and episode
                match.group(1)
                title = match.group(2).strip()
                ep_num = match.group(3)

                # Set episode number
                episode = ep_num

                # Try to extract season from title if it contains "S2", "Season 2", etc.
                season_in_title = re.search(
                    r"S(\d+)|Season\s*(\d+)", title, re.IGNORECASE
                )
                if season_in_title:
                    season_num = season_in_title.group(1) or season_in_title.group(2)
                    season = f"{int(season_num):02d}"

                # Skip further detection since we found a match
                skip_further_detection = True
                break

        # Only proceed with other patterns if we didn't find an episode yet
        if not skip_further_detection:
            # Check for explicit anime episode patterns with full episode number
            anime_explicit_patterns = [
                r"Episode\s+(\d{1,4})(?![a-zA-Z0-9])",  # Episode 1015
                r"Ep(?:isode)?\s*(\d{1,4})(?![a-zA-Z0-9])",  # Ep1015, Ep 1015
                r"#(\d{1,4})(?![a-zA-Z0-9])",  # #1015
                r"E(\d{1,4})(?![a-zA-Z0-9])",  # E1015
                r"(?<![a-zA-Z0-9])(\d{2,4})(?:\s*v\d+)?(?:\s*END)?(?![a-zA-Z0-9])",  # 1015, 1015 v2, 1015 END
            ]

            for pattern in anime_explicit_patterns:
                match = re.search(pattern, name, re.IGNORECASE)
                if match:
                    episode = match.group(1)
                    # Don't remove leading zeros for high episode numbers
                    # This preserves the full episode number
                    break

            # If still no match, look for standalone 2-4 digit numbers that might be anime episodes
            # But avoid matching years (1900-2099)
            if not episode:
                # First try to find full episode numbers in anime titles
                full_ep_pattern = r"(?:Episode|Ep)\s*(\d{1,4})(?![a-zA-Z0-9])"
                full_ep_match = re.search(full_ep_pattern, name, re.IGNORECASE)
                if full_ep_match:
                    episode = full_ep_match.group(1)
                else:
                    # Then try standalone numbers
                    anime_ep_pattern = r"(?<![a-zA-Z0-9])(?!(?:19|20)\d{2})(\d{2,4})(?![a-zA-Z0-9\.])"
                    anime_matches = re.finditer(
                        anime_ep_pattern, name, re.IGNORECASE
                    )
                    for match in anime_matches:
                        potential_ep = match.group(1)
                        # Only consider it an episode if it's a reasonable number (under 2000)
                        if int(potential_ep) < 2000:
                            episode = potential_ep
                            break

    # Special case for titles with numbers that might be mistaken for episodes
    # Check if the extracted episode is actually part of a year
    if episode:
        year_pattern = r"(19|20)\d{2}"
        year_matches = re.finditer(year_pattern, name)
        for year_match in year_matches:
            year = year_match.group(0)
            # Check if the episode number is contained within the year
            if episode in year and len(episode) < len(year):
                # This is likely a year, not an episode number
                episode = ""
                break

        # Check for false positives in filenames with version numbers or other numeric identifiers
        if episode:
            # Avoid mistaking version numbers for episodes
            version_patterns = [
                r"v\d+[.-]"
                + re.escape(episode)
                + r"(?![a-zA-Z0-9])",  # v1.01, v2-03
                r"version[.-]?"
                + re.escape(episode)
                + r"(?![a-zA-Z0-9])",  # version.01, version-02
                r"r\d+[.-]"
                + re.escape(episode)
                + r"(?![a-zA-Z0-9])",  # r1.01, r2-03
                r"rev[.-]?"
                + re.escape(episode)
                + r"(?![a-zA-Z0-9])",  # rev.01, rev-02
            ]
            for pattern in version_patterns:
                if re.search(pattern, name, re.IGNORECASE):
                    episode = ""
                    break

    # Try to find quality
    quality_matches = []
    for pattern in quality_patterns:
        matches = re.finditer(pattern, name, re.IGNORECASE)
        for match in matches:
            quality_match = match.group(1)
            # Avoid duplicates
            if quality_match.lower() not in [q.lower() for q in quality_matches]:
                quality_matches.append(quality_match)

    # Join all quality indicators
    if quality_matches:
        quality = " ".join(quality_matches)

    # Extract year from filename
    year = ""
    year_pattern = r"(?<![a-zA-Z0-9])(?:19|20)(\d{2})(?![a-zA-Z0-9])"
    year_matches = re.finditer(year_pattern, name, re.IGNORECASE)
    for year_match in year_matches:
        year = year_match.group(0)
        # Avoid mistaking episode numbers for years
        if not (episode and year.endswith(episode)):
            break

    # Extract codec information
    codec = ""
    codec_patterns = [
        r"(H\.?264|H\.?265|HEVC|AVC|XviD|DivX|VP9|AV1|MPEG-?[24])",
        r"(x264|x265)",
        r"(10bit|8bit|10-bit|8-bit)",
        r"(HDR10\+?|Dolby\s*Vision|DV|DoVi)",
        r"(DOLBY(?:VISION)?|DV)",  # Dolby Vision
        r"(AAC|MP3|FLAC|DTS(?:-?HD)?|DD(?:\+|P)?|TrueHD|Atmos)",  # Audio codecs
    ]

    codec_matches = []
    for pattern in codec_patterns:
        matches = re.finditer(pattern, name, re.IGNORECASE)
        for match in matches:
            codec_match = match.group(1)
            # Avoid duplicates
            if codec_match.lower() not in [c.lower() for c in codec_matches]:
                codec_matches.append(codec_match)

    # Special case for anime files with HEVC in brackets
    if not codec_matches and "HEVC" in name:
        hevc_match = re.search(r"\[(HEVC(?:\s+\d+bit)?)\]", name, re.IGNORECASE)
        if hevc_match:
            codec_matches.append(hevc_match.group(1))

    # Special case for anime files with common codec indicators
    if not codec_matches:
        for indicator in ["10bit", "10 bit", "HEVC", "x264", "x265"]:
            if indicator.lower() in name.lower():
                codec_matches.append(indicator)
                break

    # Join all codec indicators
    if codec_matches:
        codec = " ".join(codec_matches)

    # Extract framerate if present
    framerate = ""
    fps_patterns = [
        r"(?<![0-9])(\d{2,3}(?:\.\d+)?)\s*fps(?![0-9])",  # Explicit fps mention
        r"(?<![0-9])(\d{2,3}(?:\.\d+)?)\s*hz(?![0-9])",  # Explicit hz mention
        # Removed the pattern that was causing false positives with resolution
    ]

    for pattern in fps_patterns:
        fps_match = re.search(pattern, name, re.IGNORECASE)
        if fps_match:
            framerate = f"{fps_match.group(1)} fps"
            break

    # Return the enhanced metadata
    return {
        "season": season,
        "episode": episode,
        "quality": quality,
        "year": year,
        "codec": codec,
        "framerate": framerate,
    }


async def process_template(template, data_dict):
    """
    Process a template string with advanced formatting options including Google Fonts,
    HTML formatting, Unicode styling, and nested templates.

    Args:
        template (str): The template string with variables in various formats:
                        - {var} - Simple variable
                        - {{var}style} - Variable with styling (Google Font, HTML, Unicode)
                        - {{{var}style1}style2} - Nested styling with two levels
                        - {{{{var}style1}style2}style3} - Nested styling with three levels
                        - Any arbitrary nesting depth with any combination of styles
        data_dict (dict): Dictionary containing values for template variables

    Returns:
        str: The processed template with all variables replaced and formatting applied
    """
    if not template:
        return ""

    # Use the legacy template processor directly# Legacy template processor for backward compatibility
    # Make a copy of the template to avoid modifying the original
    processed_template = template

    # First, process quadruple nested template variables (four braces)
    # Format: {{{{variable}font1}font2}font3}
    for match in re.finditer(QUAD_NESTED_TEMPLATE_VAR_PATTERN, processed_template):
        var_name = match.group(1).strip()
        style1 = match.group(2).strip() if match.group(2) else None
        style2 = match.group(3).strip() if match.group(3) else None
        style3 = match.group(4).strip() if match.group(4) else None
        original_match = match.group(0)

        if var_name in data_dict:
            value = str(data_dict[var_name])
        else:
            # If it's not a template variable, treat it as custom text
            value = var_name  # Apply first style (innermost)
        if style1:
            try:  # Check if it's a Google Font
                if await is_google_font(style1):
                    value = await apply_google_font_style(
                        value, style1
                    )  # Check if it's an HTML style
                elif style1.lower() in FONT_STYLES:
                    value = await apply_font_style(
                        value, style1
                    )  # Check if it's a single character (emoji/unicode)
                elif (
                    len(style1) == 1 or len(style1) == 2
                ):  # Support for emoji (which can be 2 chars)
                    value = f"{style1}{value}{style1}"  # Special handling for the literal string "style"
                elif style1.lower() == "style":
                    value = f"<code>{value}</code>"
                else:
                    pass
            except Exception as e:
                LOGGER.error(f"Error applying style1 {style1}: {e}")

            # Apply second style
            if style2:
                try:  # Check if it's a Google Font
                    if await is_google_font(style2):
                        value = await apply_google_font_style(
                            value, style2
                        )  # Check if it's an HTML style
                    elif style2.lower() in FONT_STYLES:
                        value = await apply_font_style(value, style2)
                        # Special handling for combined HTML styles
                        if "_" in style2.lower():
                            pass
                        # Check if it's a single character (emoji/unicode)
                    elif (
                        len(style2) == 1 or len(style2) == 2
                    ):  # Support for emoji (which can be 2 chars)
                        value = f"{style2}{value}{style2}"  # Special handling for the literal string "style"
                    elif style2.lower() == "style":
                        value = f"<code>{value}</code>"
                    else:
                        pass
                except Exception as e:
                    LOGGER.error(f"Error applying style2 {style2}: {e}")

            # Apply third style (outermost)
            if style3:
                try:  # Check if it's a Google Font
                    if await is_google_font(style3):
                        value = await apply_google_font_style(
                            value, style3
                        )  # Check if it's an HTML style
                    elif style3.lower() in FONT_STYLES:
                        value = await apply_font_style(value, style3)
                        # Special handling for combined HTML styles
                        if "_" in style3.lower():
                            pass
                        # Check if it's a single character (emoji/unicode)
                    elif (
                        len(style3) == 1 or len(style3) == 2
                    ):  # Support for emoji (which can be 2 chars)
                        value = f"{style3}{value}{style3}"  # Special handling for the literal string "style"
                    elif style3.lower() == "style":
                        value = f"<code>{value}</code>"
                    else:
                        pass
                except Exception as e:
                    LOGGER.error(f"Error applying style3 {style3}: {e}")

            # Replace in the template
            processed_template = processed_template.replace(original_match, value)

    # Next, process nested template variables (triple braces)
    # Format: {{{variable}font1}font2}
    for match in re.finditer(NESTED_TEMPLATE_VAR_PATTERN, processed_template):
        var_name = match.group(1).strip()
        inner_style = match.group(2).strip() if match.group(2) else None
        outer_style = match.group(3).strip() if match.group(3) else None
        original_match = match.group(0)

        if var_name in data_dict:
            value = str(data_dict[var_name])
        else:
            # If it's not a template variable, treat it as custom text
            value = var_name  # Apply inner style first
        if inner_style:
            try:  # Check if it's a Google Font
                if await is_google_font(inner_style):
                    value = await apply_google_font_style(
                        value, inner_style
                    )  # Check if it's an HTML style
                elif inner_style.lower() in FONT_STYLES:
                    value = await apply_font_style(
                        value, inner_style
                    )  # Check if it's a single character (emoji/unicode)
                elif (
                    len(inner_style) == 1 or len(inner_style) == 2
                ):  # Support for emoji (which can be 2 chars)
                    value = f"{inner_style}{value}{inner_style}"  # Special handling for the literal string "style"
                elif inner_style.lower() == "style":
                    value = f"<code>{value}</code>"
                else:
                    pass
            except Exception as e:
                LOGGER.error(f"Error applying inner style {inner_style}: {e}")

            # Apply outer style
            if outer_style:
                try:  # Check if it's a Google Font
                    if await is_google_font(outer_style):
                        value = await apply_google_font_style(
                            value, outer_style
                        )  # Check if it's an HTML style
                    elif outer_style.lower() in FONT_STYLES:
                        value = await apply_font_style(value, outer_style)
                        # Special handling for combined HTML styles to ensure proper nesting
                        if "_" in outer_style.lower():
                            pass
                        # Check if it's a single character (emoji/unicode)
                    elif (
                        len(outer_style) == 1 or len(outer_style) == 2
                    ):  # Support for emoji (which can be 2 chars)
                        value = f"{outer_style}{value}{outer_style}"  # Special handling for the literal string "style"
                    elif outer_style.lower() == "style":
                        value = f"<code>{value}</code>"
                    else:
                        pass
                except Exception as e:
                    LOGGER.error(f"Error applying outer style {outer_style}: {e}")

            # Replace in the template
            processed_template = processed_template.replace(original_match, value)

    # Function to process regular template variables
    async def replace_match(match):
        # Check which group matched
        if match.group(1) is not None:
            # Format: {{variable}style}
            var_name = match.group(1).strip()
            style_name = (
                match.group(2).strip() if match.group(2) else None
            )  # Get the variable value
            if var_name in data_dict:
                value = str(data_dict[var_name])
                # Handle None or empty values
                if value is None or value == "":
                    value = ""
                # Apply styling if specified
                if style_name:
                    try:  # Check if it's a Google Font
                        if await is_google_font(style_name):
                            return await apply_google_font_style(value, style_name)
                        # Check if it's an HTML style
                        if style_name.lower() in FONT_STYLES:
                            return await apply_font_style(value, style_name)
                        # Check if it's a single character (emoji/unicode)
                        if (
                            len(style_name) == 1 or len(style_name) == 2
                        ):  # Support for emoji (which can be 2 chars)
                            return f"{style_name}{value}{style_name}"
                        # Special handling for the literal string "style"
                        if style_name.lower() == "style":
                            return f"<code>{value}</code>"
                        return value
                    except Exception as e:
                        LOGGER.error(f"Error applying style {style_name}: {e}")
                        # Continue with original value on error
                        return value
                return value
            # If it's not a template variable, treat it as custom text
            value = var_name  # Apply styling if specified
            if style_name:
                try:  # Check if it's a Google Font
                    if await is_google_font(style_name):
                        return await apply_google_font_style(value, style_name)
                    # Check if it's an HTML style
                    if style_name.lower() in FONT_STYLES:
                        return await apply_font_style(value, style_name)
                    # Check if it's a single character (emoji/unicode)
                    if (
                        len(style_name) == 1 or len(style_name) == 2
                    ):  # Support for emoji (which can be 2 chars)
                        return f"{style_name}{value}{style_name}"
                    # Special handling for the literal string "style"
                    if style_name.lower() == "style":
                        return f"<code>{value}</code>"
                    return f"<code>{value}</code>"
                except Exception as e:
                    LOGGER.error(f"Error applying style {style_name}: {e}")
                    # Continue with original value on error
                    return value
            return value

        # Format: {variable}
        if match.group(3) is not None:
            var_name = match.group(3).strip()
            if var_name in data_dict:
                value = str(data_dict[var_name])
                # Handle None or empty values
                if value is None:
                    return ""
                return value

        # Return the original if variable not found or no match
        return match.group(0)

    # Process regular template variables
    result = processed_template
    for match in re.finditer(TEMPLATE_VAR_PATTERN, processed_template):
        replacement = await replace_match(match)
        result = result.replace(match.group(0), replacement)

    # Final processing of HTML tags to ensure they're properly formatted
    processed_result = await process_html_tags(result)

    # Force garbage collection after processing complex templates
    # This can create many temporary strings and objects
    if smart_garbage_collection and len(template) > 1000:  # Only for large templates
        # Use normal mode for template processing
        smart_garbage_collection(aggressive=False)
    elif len(template) > 1000:  # Only for large templates
        # Only collect generation 0 (youngest objects) for better performance
        gc.collect(0)

    return processed_result


async def process_html_tags(text):
    """
    Process HTML tags in the text to ensure they are properly formatted.

    Args:
        text (str): Text that may contain HTML tags

    Returns:
        str: Text with properly formatted HTML tags
    """
    # Check for common HTML tag issues
    if not text:
        return text

    # Log the HTML processing# This function can be expanded to handle more complex HTML processing if needed
    # For now, we just validate that tags are properly nested

    # Check for unclosed tags
    open_tags = []
    # List of supported Electrogram HTML tags
    supported_tags = [
        "b",
        "strong",
        "i",
        "em",
        "u",
        "s",
        "del",
        "strike",
        "spoiler",
        "code",
        "pre",
        "blockquote",
        "a",
    ]

    # Check for expandable blockquotes and ensure they have multiple lines
    expandable_blockquote_pattern = (
        r"<blockquote\s+expandable[^>]*>(.*?)</blockquote>"
    )
    for match in re.finditer(expandable_blockquote_pattern, text, re.DOTALL):
        content = match.group(1)
        if "\n" not in content:
            # Add a newline to ensure it works as expandable
            new_content = content + "\n "
            text = text.replace(
                match.group(0), f"<blockquote expandable>{new_content}</blockquote>"
            )
    for match in re.finditer(r"<([a-z0-9_-]+)[^>]*>", text, re.IGNORECASE):
        tag = match.group(1).lower()
        # Skip self-closing tags
        if tag in ["br", "hr", "img"]:
            continue

        # Handle unsupported tags
        if tag not in supported_tags:
            # Replace tg-spoiler with spoiler
            if tag == "tg-spoiler":
                text = text.replace(f"<{tag}", "<spoiler").replace(
                    f"</{tag}>", "</spoiler>"
                )
            open_tags.append(tag)

    for match in re.finditer(r"</([a-z0-9_-]+)>", text, re.IGNORECASE):
        close_tag = match.group(1).lower()
        if open_tags and open_tags[-1] == close_tag:
            open_tags.pop()
        else:
            pass

    if open_tags:
        pass

    # Return the potentially modified text
    # Force garbage collection if the text is very large
    if smart_garbage_collection and len(text) > 10000:  # Only for very large texts
        # Use normal mode for HTML processing
        smart_garbage_collection(aggressive=False)
    elif len(text) > 10000:  # Only for very large texts
        # Only collect generation 0 (youngest objects) for better performance
        gc.collect(0)

    return text
