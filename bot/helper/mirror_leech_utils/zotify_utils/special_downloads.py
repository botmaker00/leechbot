"""
Optimized Zotify special downloads handler
"""

import asyncio

from zotify import Session
from zotify.app import Selection

from bot import LOGGER


class ZotifySpecialDownloads:
    """Handles special Zotify downloads like liked tracks, followed artists, etc."""

    def __init__(self):
        # Use the global simple session manager
        from bot.helper.mirror_leech_utils.zotify_utils.improved_session_manager import (
            simple_session_manager,
        )

        self.session_manager = simple_session_manager

    async def get_session(self) -> Session | None:
        """Get session from simple session manager"""
        return await self.session_manager.get_session()

    async def get_liked_tracks(self) -> list[str]:
        """Get user's liked tracks"""
        session = await self.get_session()
        if not session:
            return []

        try:
            selection = Selection(session)
            # Use Zotify's Selection.get method for liked tracks
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: selection.get("tracks", "track")
            )
        except Exception as e:
            LOGGER.error(f"Failed to get liked tracks: {e}")
            return []

    async def get_liked_episodes(self) -> list[str]:
        """Get user's liked episodes"""
        session = await self.get_session()
        if not session:
            return []

        try:
            selection = Selection(session)
            # Use Zotify's Selection.get method for liked episodes
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: selection.get("episodes")
            )
        except Exception as e:
            LOGGER.error(f"Failed to get liked episodes: {e}")
            return []

    async def get_followed_artists(self) -> list[str]:
        """Get user's followed artists"""
        session = await self.get_session()
        if not session:
            return []

        try:
            selection = Selection(session)
            # Use Zotify's Selection.get method for followed artists
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: selection.get("following?type=artist", content="artists"),
            )
        except Exception as e:
            LOGGER.error(f"Failed to get followed artists: {e}")
            return []

    async def get_saved_playlists(self) -> list[str]:
        """Get user's saved playlists"""
        session = await self.get_session()
        if not session:
            return []

        try:
            selection = Selection(session)
            # Use Zotify's Selection.get method for playlists
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: selection.get("playlists")
            )
        except Exception as e:
            LOGGER.error(f"Failed to get saved playlists: {e}")
            return []

    async def get_special_download_urls(self, special_type: str) -> list[str]:
        """
        Get URLs for special download type

        Args:
            special_type: Type of special download (liked_tracks, liked_episodes, etc.)

        Returns:
            List of Spotify URLs to download
        """
        if special_type == "liked_tracks":
            return await self.get_liked_tracks()
        if special_type == "liked_episodes":
            return await self.get_liked_episodes()
        if special_type == "followed_artists":
            return await self.get_followed_artists()
        if special_type == "saved_playlists":
            return await self.get_saved_playlists()
        LOGGER.error(f"Unknown special download type: {special_type}")
        return []

    async def get_special_download_info(self, special_type: str) -> dict[str, any]:
        """
        Get information about a special download

        Returns:
            Dictionary with download info
        """
        urls = await self.get_special_download_urls(special_type)

        return {
            "type": special_type,
            "count": len(urls),
            "urls": urls,
            "description": self._get_special_type_description(special_type),
        }

    def _get_special_type_description(self, special_type: str) -> str:
        """Get human-readable description for special download type"""
        descriptions = {
            "liked_tracks": "Liked Tracks",
            "liked_episodes": "Liked Episodes",
            "followed_artists": "Followed Artists",
            "saved_playlists": "Saved Playlists",
        }
        return descriptions.get(special_type, special_type.replace("_", " ").title())


# Global instance
zotify_special = ZotifySpecialDownloads()


# Convenience functions
async def get_special_download_urls(special_type: str) -> list[str]:
    """Get URLs for special download type"""
    return await zotify_special.get_special_download_urls(special_type)


async def get_special_download_info(special_type: str) -> dict[str, any]:
    """Get information about special download"""
    return await zotify_special.get_special_download_info(special_type)


def is_special_download(url: str) -> bool:
    """Check if URL is a special download keyword"""
    from bot.helper.mirror_leech_utils.zotify_utils.url_parser import ZotifyUrlParser

    return ZotifyUrlParser.is_special_keyword(url)


def get_special_download_type(url: str) -> str | None:
    """Get special download type from URL/keyword"""
    from bot.helper.mirror_leech_utils.zotify_utils.url_parser import ZotifyUrlParser

    return ZotifyUrlParser.get_special_keyword_type(url)


# Selection class wrapper for interactive selection
class ZotifySelection:
    """Wrapper for Zotify Selection class with interactive features"""

    def __init__(self, session: Session):
        self.selection = Selection(session)

    async def interactive_select_playlists(self) -> list[str]:
        """Interactive playlist selection"""
        try:
            # Get all playlists first
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.selection.get("playlists")
            )

            # For now, return all playlists
            # In the future, this could be enhanced with interactive selection

        except Exception as e:
            LOGGER.error(f"Failed to get playlists for selection: {e}")
            return []

    async def interactive_select_artists(self) -> list[str]:
        """Interactive artist selection"""
        try:
            # Get all followed artists first
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.selection.get(
                    "following?type=artist", content="artists"
                ),
            )

            # For now, return all artists
            # In the future, this could be enhanced with interactive selection

        except Exception as e:
            LOGGER.error(f"Failed to get artists for selection: {e}")
            return []


async def create_selection_interface(session: Session) -> ZotifySelection:
    """Create selection interface for interactive downloads"""
    return ZotifySelection(session)
