import re
from typing import Any

import aiohttp

from bot import LOGGER


class StreamripURLParser:
    """Parser for music streaming platform URLs"""

    # URL patterns for different platforms
    URL_PATTERNS = {
        "qobuz": [
            r"https?://(?:www\.)?qobuz\.com/(?:[a-z]{2}-[a-z]{2}/)?album/([^/]+)/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/(?:[a-z]{2}-[a-z]{2}/)?track/([^/]+)/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/(?:[a-z]{2}-[a-z]{2}/)?playlist/([^/]+)/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/(?:[a-z]{2}-[a-z]{2}/)?artist/([^/]+)/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/(?:[a-z]{2}-[a-z]{2}/)?interpreter/([^/]+)/([^/?]+)",  # Qobuz artist pages use "interpreter"
            r"https?://(?:www\.)?qobuz\.com/(?:[a-z]{2}-[a-z]{2}/)?label/([^/]+)/([^/?]+)",
            r"https?://open\.qobuz\.com/album/([^/?]+)",
            r"https?://open\.qobuz\.com/track/([^/?]+)",
            # Simple ID-only formats (common from search results)
            r"https?://(?:www\.)?qobuz\.com/album/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/track/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/playlist/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/artist/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/interpreter/([^/?]+)",
            r"https?://(?:www\.)?qobuz\.com/label/([^/?]+)",
        ],
        "tidal": [
            r"https?://(?:www\.)?tidal\.com/browse/album/(\d+)",
            r"https?://(?:www\.)?tidal\.com/browse/track/(\d+)",
            r"https?://(?:www\.)?tidal\.com/browse/playlist/([^/?]+)",
            r"https?://(?:www\.)?tidal\.com/browse/artist/(\d+)",
            r"https?://(?:www\.)?tidal\.com/browse/mix/([^/?]+)",
            r"https?://listen\.tidal\.com/album/(\d+)",
            r"https?://listen\.tidal\.com/track/(\d+)",
            r"https?://listen\.tidal\.com/playlist/([^/?]+)",
        ],
        "deezer": [
            r"https?://(?:www\.)?deezer\.com/(?:[a-z]{2}/)?album/(\d+)",
            r"https?://(?:www\.)?deezer\.com/(?:[a-z]{2}/)?track/(\d+)",
            r"https?://(?:www\.)?deezer\.com/(?:[a-z]{2}/)?playlist/(\d+)",
            r"https?://(?:www\.)?deezer\.com/(?:[a-z]{2}/)?artist/(\d+)",
            r"https?://(?:www\.)?deezer\.com/(?:[a-z]{2}/)?show/(\d+)",
            r"https?://deezer\.page\.link/([^/?]+)",
        ],
        "soundcloud": [
            r"https?://(?:www\.)?soundcloud\.com/([^/]+)/([^/?]+)",
            r"https?://(?:www\.)?soundcloud\.com/([^/]+)/sets/([^/?]+)",
            r"https?://(?:m\.)?soundcloud\.com/([^/]+)/([^/?]+)",
            r"https?://(?:m\.)?soundcloud\.com/([^/]+)/sets/([^/?]+)",
        ],
        "lastfm": [
            r"https?://(?:www\.)?last\.fm/user/([^/]+)/playlists/(\d+)",
            r"https?://(?:www\.)?last\.fm/music/([^/]+)",
            r"https?://(?:www\.)?last\.fm/music/([^/]+)/([^/]+)",
        ],
        "spotify": [
            r"https?://open\.spotify\.com/album/([^/?]+)",
            r"https?://open\.spotify\.com/track/([^/?]+)",
            r"https?://open\.spotify\.com/playlist/([^/?]+)",
            r"https?://open\.spotify\.com/artist/([^/?]+)",
            r"https?://spotify\.link/([^/?]+)",
        ],
        "apple_music": [
            r"https?://music\.apple\.com/(?:[a-z]{2}/)?album/([^/]+)/(\d+)",
            r"https?://music\.apple\.com/(?:[a-z]{2}/)?album/([^/]+)/(\d+)\?i=(\d+)",
            r"https?://music\.apple\.com/(?:[a-z]{2}/)?playlist/([^/]+)/([^/?]+)",
            r"https?://music\.apple\.com/(?:[a-z]{2}/)?artist/([^/]+)/(\d+)",
        ],
    }

    # Media type detection patterns
    MEDIA_TYPE_PATTERNS = {
        "album": ["album"],
        "track": ["track", "song"],
        "playlist": ["playlist", "sets"],
        "artist": ["artist", "interpreter"],  # Qobuz uses "interpreter" for artists
        "label": ["label"],
        "mix": ["mix"],
        "show": ["show", "podcast"],
        "chart": ["chart", "top"],
    }

    @classmethod
    async def parse_url(cls, url: str) -> tuple[str, str, str] | None:
        """
        Parse a music streaming URL and extract platform, media type, and ID

        Args:
            url: The URL to parse

        Returns:
            Tuple of (platform, media_type, media_id) or None if not recognized
        """
        if not url or not isinstance(url, str):
            return None

        url = url.strip()

        # Check if it's a short URL that needs to be resolved
        if cls._is_short_url(url):
            resolved_url = await cls._resolve_short_url(url)
            if resolved_url:
                url = resolved_url

        # Check if it's an ID-based input (format: platform:type:id)
        id_match = cls._parse_id_format(url)
        if id_match:
            return id_match

        # Try each platform
        for platform, patterns in cls.URL_PATTERNS.items():
            for pattern in patterns:
                match = re.match(pattern, url, re.IGNORECASE)
                if match:
                    media_type = cls._extract_media_type(url, pattern)
                    media_id = cls._extract_media_id(match, platform)

                    if media_type and media_id:
                        return platform, media_type, media_id

        return None

    @classmethod
    def _parse_id_format(cls, input_str: str) -> tuple[str, str, str] | None:
        """
        Parse ID-based input format: platform:type:id
        Examples: qobuz:album:123456, tidal:track:789012
        """
        if ":" not in input_str:
            return None

        parts = input_str.split(":")
        if len(parts) != 3:
            return None

        platform, media_type, media_id = parts
        platform = platform.lower().strip()
        media_type = media_type.lower().strip()
        media_id = media_id.strip()

        # Validate platform
        if platform not in cls.URL_PATTERNS:
            return None

        # Validate media type
        valid_types = [
            "album",
            "track",
            "playlist",
            "artist",
            "label",
            "mix",
            "show",
            "chart",
        ]
        if media_type not in valid_types:
            return None

        if media_id:
            return platform, media_type, media_id

        return None

    @classmethod
    def _extract_media_type(cls, url: str, pattern: str) -> str | None:
        """Extract media type from URL pattern"""
        url_lower = url.lower()

        # Special handling for SoundCloud URLs
        if "soundcloud.com" in url_lower:
            if "/sets/" in url_lower:
                return "playlist"
            return "track"  # Default for SoundCloud user/track format

        # Check for explicit media type in URL path
        for media_type, keywords in cls.MEDIA_TYPE_PATTERNS.items():
            for keyword in keywords:
                if f"/{keyword}/" in url_lower:
                    return media_type

        # Fallback: try to detect from pattern structure
        if "/album/" in url_lower:
            return "album"
        if "/track/" in url_lower or "/song/" in url_lower:
            return "track"
        if "/playlist/" in url_lower or "/sets/" in url_lower:
            return "playlist"
        if (
            "/artist/" in url_lower or "/interpreter/" in url_lower
        ):  # Qobuz uses "interpreter" for artists
            return "artist"
        if "/label/" in url_lower:
            return "label"
        if "/mix/" in url_lower:
            return "mix"
        if "/show/" in url_lower:
            return "show"

        # Default to track for single items
        return "track"

    @classmethod
    def _extract_media_id(cls, match: re.Match, platform: str) -> str | None:
        """Extract media ID from regex match"""
        if not match.groups():
            return None

        # For most platforms, the ID is the last captured group
        groups = match.groups()

        if platform == "soundcloud":
            # SoundCloud uses username/track-name format
            if len(groups) >= 2:
                return f"{groups[0]}/{groups[1]}"
            return groups[0] if groups else None

        if platform in ["qobuz", "tidal", "deezer"]:
            # These platforms typically use numeric IDs
            return groups[-1] if groups else None

        if platform == "lastfm":
            # Last.fm can have different formats
            if len(groups) >= 2:
                return f"{groups[0]}/{groups[1]}"
            return groups[0] if groups else None

        if platform in ["spotify", "apple_music"]:
            # These are for Last.fm conversion, return the ID
            return groups[-1] if groups else None

        return groups[0] if groups else None

    @classmethod
    def _is_short_url(cls, url: str) -> bool:
        """Check if URL is a short URL that needs to be resolved"""
        short_url_patterns = [
            r"https?://dzr\.page\.link/",
            r"https?://tidal\.link/",
            r"https?://spotify\.link/",
            r"https?://music\.apple\.com/.*\?.*",
            r"https?://qobuz\.com/.*\?.*",
            r"https?://bit\.ly/",
            r"https?://t\.co/",
            r"https?://tinyurl\.com/",
        ]

        for pattern in short_url_patterns:
            if re.match(pattern, url, re.IGNORECASE):
                return True
        return False

    @classmethod
    async def _resolve_short_url(cls, url: str) -> str | None:
        """Resolve a short URL to its final destination"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(url, allow_redirects=True) as response:
                    final_url = str(response.url)
                    if final_url != url:
                        return final_url
        except Exception as e:
            LOGGER.warning(f"Failed to resolve short URL {url}: {e}")

        return None

    @classmethod
    async def is_music_url(cls, url: str) -> bool:
        """Check if URL is from a supported music platform"""
        result = await cls.parse_url(url)
        return result is not None

    @classmethod
    def get_supported_platforms(cls) -> list:
        """Get list of supported platforms"""
        return list(cls.URL_PATTERNS.keys())

    @classmethod
    def get_platform_info(cls, platform: str) -> dict[str, Any]:
        """Get information about a specific platform"""
        platform_info = {
            "qobuz": {
                "name": "Qobuz",
                "requires_subscription": True,
                "max_quality": 4,
                "formats": ["FLAC", "MP3"],
                "auth_method": "email_password",
            },
            "tidal": {
                "name": "Tidal",
                "requires_subscription": True,
                "max_quality": 3,
                "formats": ["FLAC", "MQA", "AAC"],
                "auth_method": "email_password",
            },
            "deezer": {
                "name": "Deezer",
                "requires_subscription": True,
                "max_quality": 2,
                "formats": ["FLAC", "MP3"],
                "auth_method": "arl_cookie",
            },
            "soundcloud": {
                "name": "SoundCloud",
                "requires_subscription": False,
                "max_quality": 1,
                "formats": ["MP3", "AAC"],
                "auth_method": "optional",
            },
            "lastfm": {
                "name": "Last.fm",
                "requires_subscription": False,
                "max_quality": "varies",
                "formats": "varies",
                "auth_method": "none",
            },
        }

        return platform_info.get(platform, {})


async def is_streamrip_url(url: str) -> bool:
    """Check if URL is supported by streamrip"""
    return await StreamripURLParser.is_music_url(url)


async def parse_streamrip_url(url: str) -> tuple[str, str, str] | None:
    """Parse streamrip URL and return platform, media_type, media_id"""
    return await StreamripURLParser.parse_url(url)


def is_file_input(input_str: str) -> bool:
    """Check if input is a file path or file content"""
    if not input_str:
        return False

    # Check if it's a file path
    if input_str.endswith((".txt", ".json", ".csv")):
        return True

    # Check if it contains multiple lines (file content)
    lines = input_str.strip().split("\n")
    if len(lines) > 1:
        # Check if lines contain URLs or ID formats
        url_count = 0
        for line in lines:
            line = line.strip()
            # Simple URL pattern check without async call
            if line and (
                any(
                    domain in line.lower()
                    for domain in [
                        "qobuz.com",
                        "tidal.com",
                        "deezer.com",
                        "soundcloud.com",
                        "last.fm",
                    ]
                )
                or ":" in line
            ):
                url_count += 1

        # If more than half the lines are URLs/IDs, consider it file content
        return url_count > len(lines) // 2

    return False


async def parse_file_content(content: str) -> list[str]:
    """Parse file content and extract URLs/IDs"""
    urls = []
    lines = content.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):  # Skip empty lines and comments
            continue

        # Handle JSON format
        if line.startswith("{") and line.endswith("}"):
            try:
                import json

                data = json.loads(line)
                if "url" in data:
                    urls.append(data["url"])
                elif "source" in data and "media_type" in data and "id" in data:
                    # Convert to ID format
                    urls.append(
                        f"{data['source']}:{data['media_type']}:{data['id']}"
                    )
            except json.JSONDecodeError:
                pass
        # Plain text URL or ID format
        elif await is_streamrip_url(line) or ":" in line:
            urls.append(line)

    return urls


def is_lastfm_url(url: str) -> bool:
    """Check if URL is from Last.fm"""
    if not url:
        return False

    lastfm_patterns = [
        r"https?://(?:www\.)?last\.fm/user/([^/]+)/playlists/(\d+)",
        r"https?://(?:www\.)?last\.fm/music/([^/]+)",
        r"https?://(?:www\.)?last\.fm/music/([^/]+)/([^/]+)",
    ]

    return any(re.match(pattern, url, re.IGNORECASE) for pattern in lastfm_patterns)
