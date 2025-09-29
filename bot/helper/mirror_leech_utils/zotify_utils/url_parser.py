"""
Zotify URL parser and validation utilities for aimleechbot
"""

import re
from typing import ClassVar


class ZotifyUrlParser:
    """Parser for Spotify URLs and URIs"""

    # Spotify URL patterns
    SPOTIFY_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "track": [
            r"https?://open\.spotify\.com/track/([a-zA-Z0-9]{22})",
            r"spotify:track:([a-zA-Z0-9]{22})",
        ],
        "album": [
            r"https?://open\.spotify\.com/album/([a-zA-Z0-9]{22})",
            r"spotify:album:([a-zA-Z0-9]{22})",
        ],
        "playlist": [
            r"https?://open\.spotify\.com/playlist/([a-zA-Z0-9]{22})",
            r"spotify:playlist:([a-zA-Z0-9]{22})",
        ],
        "artist": [
            r"https?://open\.spotify\.com/artist/([a-zA-Z0-9]{22})",
            r"spotify:artist:([a-zA-Z0-9]{22})",
        ],
        "show": [
            r"https?://open\.spotify\.com/show/([a-zA-Z0-9]{22})",
            r"spotify:show:([a-zA-Z0-9]{22})",
        ],
        "episode": [
            r"https?://open\.spotify\.com/episode/([a-zA-Z0-9]{22})",
            r"spotify:episode:([a-zA-Z0-9]{22})",
        ],
    }

    # Special Zotify keywords for user library downloads
    SPECIAL_KEYWORDS: ClassVar[dict[str, str]] = {
        "liked-tracks": "liked_tracks",
        "liked_tracks": "liked_tracks",
        "likedtracks": "liked_tracks",
        "liked": "liked_tracks",
        "favorites": "liked_tracks",
        "favs": "liked_tracks",
        "liked-episodes": "liked_episodes",
        "liked_episodes": "liked_episodes",
        "likedepisodes": "liked_episodes",
        "episodes": "liked_episodes",
        "followed-artists": "followed_artists",
        "followed_artists": "followed_artists",
        "followedartists": "followed_artists",
        "followed": "followed_artists",
        "artists": "followed_artists",
        "saved-playlists": "saved_playlists",
        "saved_playlists": "saved_playlists",
        "savedplaylists": "saved_playlists",
        "playlists": "saved_playlists",
        "my-playlists": "saved_playlists",
        "my_playlists": "saved_playlists",
    }

    @staticmethod
    def is_spotify_url(url: str) -> bool:
        """Check if URL is a valid Spotify URL or URI"""
        if not url:
            return False

        url = url.strip()

        # Check for special keywords first
        if ZotifyUrlParser.is_special_keyword(url):
            return True

        # Check for Spotify domain or URI scheme
        if "spotify.com" in url or url.startswith("spotify:"):
            for patterns in ZotifyUrlParser.SPOTIFY_PATTERNS.values():
                for pattern in patterns:
                    if re.match(pattern, url):
                        return True
        return False

    @staticmethod
    def is_special_keyword(text: str) -> bool:
        """Check if text is a special Zotify keyword"""
        if not text:
            return False

        text = text.strip().lower()
        return text in ZotifyUrlParser.SPECIAL_KEYWORDS

    @staticmethod
    def get_special_keyword_type(text: str) -> str | None:
        """Get the special keyword type"""
        if not text:
            return None

        text = text.strip().lower()
        return ZotifyUrlParser.SPECIAL_KEYWORDS.get(text)

    @staticmethod
    def parse_spotify_url(url: str) -> tuple[str, str] | None:
        """
        Parse Spotify URL and extract content type and ID using exact Zotify method

        Returns:
            Tuple of (content_type, spotify_id) or None if invalid
        """
        if not url:
            return None

        url = url.strip()

        # Check for special keywords first
        special_type = ZotifyUrlParser.get_special_keyword_type(url)
        if special_type:
            return special_type, "special"

        # Use exact Zotify parsing method from app.py
        try:
            # Remove query parameters like Zotify does
            link = url.rsplit("?", 1)[0]

            # Extract ID and type using Zotify's exact method
            split = link.split(link[-23])  # Split by character at position -23
            _id = split[-1]  # Last part is the ID
            id_type = split[-2]  # Second to last is the type

            # Validate that this is a supported content type
            supported_types = [
                "album",
                "artist",
                "show",
                "track",
                "episode",
                "playlist",
            ]
            if id_type in supported_types:
                return id_type, _id
            return None

        except (IndexError, ValueError):
            return None

    @staticmethod
    def extract_spotify_id(url: str) -> str | None:
        """Extract Spotify ID from URL"""
        parsed = ZotifyUrlParser.parse_spotify_url(url)
        return parsed[1] if parsed else None

    @staticmethod
    def get_content_type(url: str) -> str | None:
        """Get content type from Spotify URL"""
        parsed = ZotifyUrlParser.parse_spotify_url(url)
        return parsed[0] if parsed else None

    @staticmethod
    def normalize_spotify_url(url: str) -> str | None:
        """
        Normalize Spotify URL to standard format

        Returns:
            Normalized URL or None if invalid
        """
        parsed = ZotifyUrlParser.parse_spotify_url(url)
        if not parsed:
            return None

        content_type, spotify_id = parsed
        return f"https://open.spotify.com/{content_type}/{spotify_id}"

    @staticmethod
    def is_file_input(text: str) -> bool:
        """Check if input appears to be file content with multiple URLs"""
        if not text:
            return False

        lines = text.strip().split("\n")
        if len(lines) <= 1:
            return False

        # Check if multiple lines contain Spotify URLs
        spotify_lines = 0
        for line in lines:
            line = line.strip()
            if line and ZotifyUrlParser.is_spotify_url(line):
                spotify_lines += 1

        return spotify_lines >= 2

    @staticmethod
    def parse_file_content(content: str) -> list[str]:
        """
        Parse file content and extract valid Spotify URLs

        Returns:
            List of valid Spotify URLs
        """
        if not content:
            return []

        urls = []
        lines = content.strip().split("\n")

        for line in lines:
            line = line.strip()
            if line and ZotifyUrlParser.is_spotify_url(line):
                normalized = ZotifyUrlParser.normalize_spotify_url(line)
                if normalized:
                    urls.append(normalized)

        return urls

    @staticmethod
    def validate_batch_urls(urls: list[str]) -> tuple[list[str], list[str]]:
        """
        Validate a batch of URLs

        Returns:
            Tuple of (valid_urls, invalid_urls)
        """
        valid_urls = []
        invalid_urls = []

        for url in urls:
            if ZotifyUrlParser.is_spotify_url(url):
                normalized = ZotifyUrlParser.normalize_spotify_url(url)
                if normalized:
                    valid_urls.append(normalized)
                else:
                    invalid_urls.append(url)
            else:
                invalid_urls.append(url)

        return valid_urls, invalid_urls

    @staticmethod
    def get_url_info(url: str) -> dict[str, str] | None:
        """
        Get detailed information about a Spotify URL

        Returns:
            Dictionary with url info or None if invalid
        """
        parsed = ZotifyUrlParser.parse_spotify_url(url)
        if not parsed:
            return None

        content_type, spotify_id = parsed
        normalized_url = ZotifyUrlParser.normalize_spotify_url(url)

        return {
            "original_url": url,
            "normalized_url": normalized_url,
            "content_type": content_type,
            "spotify_id": spotify_id,
            "uri": f"spotify:{content_type}:{spotify_id}",
        }


# Convenience functions for backward compatibility
async def is_zotify_url(url: str) -> bool:
    """Check if URL is supported by Zotify (Spotify)"""
    return ZotifyUrlParser.is_spotify_url(url)


async def parse_zotify_url(url: str) -> tuple[str, str] | None:
    """Parse Zotify URL and return content type and ID"""
    return ZotifyUrlParser.parse_spotify_url(url)


def is_file_input(text: str) -> bool:
    """Check if input is file content with multiple URLs"""
    return ZotifyUrlParser.is_file_input(text)


def parse_file_content(content: str) -> list[str]:
    """Parse file content and extract URLs"""
    return ZotifyUrlParser.parse_file_content(content)
