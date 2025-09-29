"""
Zotify command handlers
"""

import asyncio
import os

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import arg_parser, new_task
from bot.helper.mirror_leech_utils.download_utils.zotify_download import (
    add_zotify_download,
)
from bot.helper.mirror_leech_utils.zotify_utils.search_handler import search_music
from bot.helper.mirror_leech_utils.zotify_utils.special_downloads import (
    get_special_download_info,
    get_special_download_type,
    is_special_download,
)
from bot.helper.mirror_leech_utils.zotify_utils.url_parser import (
    ZotifyUrlParser,
    is_file_input,
    parse_file_content,
)
from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import (
    has_zotify_credentials,
    is_zotify_enabled,
)
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)


class ZotifyCommands:
    """Zotify command handlers"""

    @staticmethod
    def _get_zotify_args():
        """Get Zotify-specific command arguments"""
        return {
            "link": "",
            "-q": "auto",  # Quality: auto, normal, high, very_high
            "-f": "vorbis",  # Format: vorbis, mp3, flac, aac, fdk_aac, opus, wav, wavpack (exact Zotify formats)
            "-a": "large",  # Artwork size: small, medium, large
            "-n": "",  # Custom name
            "-up": "",  # Upload destination
            "-rcf": "",  # Rclone flags
            "-t": "",  # Tag
            "-ca": "",  # Custom arguments
            "-ss": False,  # Screenshot
            "-lyrics": False,  # Download lyrics file
            "-lyrics-only": False,  # Download only lyrics
            "-real-time": False,  # Real-time download
            "-replace": False,  # Replace existing files
            "-skip-dup": False,  # Skip duplicates
            "-metadata": True,  # Save metadata
            "-genre": False,  # Save genre
            "-subtitles": False,  # Save subtitles (podcasts)
            "-playlist-file": True,  # Create playlist file
            "-all-artists": False,  # Download all artists from album
            "-output-single": "",  # Custom output format for single tracks
            "-match": False,  # Match existing files for skip functionality
        }

    @staticmethod
    async def _process_zotify_download(message, is_leech: bool = False):
        """Process Zotify download command"""
        # Check if Zotify is enabled
        if not is_zotify_enabled():
            reply = await send_message(message, "❌ Zotify is disabled!")
            await auto_delete_message(reply, time=300)
            return

        # Check credentials
        user_id = message.from_user.id
        if not await has_zotify_credentials(user_id):
            reply = await send_message(
                message,
                "❌ Zotify credentials not configured!\n\n"
                "Please configure Spotify credentials in bot settings.",
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse arguments with Zotify-specific flags
        if not message.text:
            reply = await send_message(message, "❌ No command text provided.")
            await auto_delete_message(reply, time=300)
            return

        text = message.text.split()
        args = ZotifyCommands._get_zotify_args()
        arg_parser(text[1:], args)

        # Get input from message (URL, file content, or search query)
        input_data = ""
        if reply_to := message.reply_to_message:
            if reply_to.document:
                # Handle file upload
                try:
                    file_path = await reply_to.download()
                    from aiofiles import open as aiopen

                    async with aiopen(file_path, encoding="utf-8") as f:
                        input_data = await f.read()
                    os.remove(file_path)  # Clean up downloaded file
                except Exception as e:
                    reply = await send_message(
                        message, f"❌ Failed to read file: {e!s}"
                    )
                    await auto_delete_message(reply, time=300)
                    return
            else:
                input_data = reply_to.text.strip() if reply_to.text else ""
        else:
            input_data = args.get("link", "").strip()

        if not input_data:
            # Show interactive help menu using COMMAND_USAGE for consistency
            from bot.helper.ext_utils.bot_utils import COMMAND_USAGE

            reply = await send_message(
                message, COMMAND_USAGE["zotify"][0], COMMAND_USAGE["zotify"][1]
            )
            await auto_delete_message(reply, time=600)
            return

        # Process input and get URLs to download
        urls_to_process = await ZotifyCommands._process_input(input_data, message)
        if not urls_to_process:
            return

        # Delete original command message and replied message
        try:
            await delete_message(message)
            if message.reply_to_message:
                await delete_message(message.reply_to_message)
        except Exception as e:
            LOGGER.error(f"Failed to delete command messages: {e}")

        # Process each URL
        for url in urls_to_process:
            try:
                # Create proper zotify listener
                from bot.helper.listeners.zotify_listener import ZotifyListener

                listener = ZotifyListener(
                    message,
                    is_leech=is_leech,
                    tag=args.get("-t", ""),
                    screenshot=args.get("-ss", False),
                )

                # Set custom name if provided
                if args.get("-n"):
                    listener.name = args["-n"]
                else:
                    # Extract actual album/playlist/artist name from Spotify
                    extracted_name = await _extract_zotify_metadata_name(url)
                    if extracted_name:
                        listener.name = extracted_name

                # Set upload destination and rclone flags
                listener.up_dest = args.get("-up", "")
                listener.rc_flags = args.get("-rcf", "")

                # Set URL
                listener.url = url

                # Start download
                await add_zotify_download(listener, url)

            except Exception as e:
                LOGGER.error(f"Failed to start Zotify download for {url}: {e}")
                reply = await send_message(
                    message, f"❌ Failed to start download for {url}: {e}"
                )
                await auto_delete_message(reply, time=300)

    @staticmethod
    async def _process_input(input_data: str, message) -> list[str]:
        """Process input data and return list of valid URLs"""
        urls_to_process = []

        # Check if input is file content with multiple URLs
        if is_file_input(input_data):
            urls = parse_file_content(input_data)
            if urls:
                valid_urls, invalid_urls = ZotifyUrlParser.validate_batch_urls(urls)

                if invalid_urls:
                    invalid_msg = "⚠️ Some URLs were invalid and skipped:\n"
                    for invalid_url in invalid_urls[:5]:  # Show max 5 invalid URLs
                        invalid_msg += f"• {invalid_url}\n"
                    if len(invalid_urls) > 5:
                        invalid_msg += f"... and {len(invalid_urls) - 5} more"

                    reply = await send_message(message, invalid_msg)
                    await auto_delete_message(reply, time=300)

                urls_to_process = valid_urls
            else:
                reply = await send_message(
                    message, "❌ No valid Spotify URLs found in file!"
                )
                await auto_delete_message(reply, time=300)
                return []
        # Single URL, special keyword, or search query
        elif ZotifyUrlParser.is_spotify_url(input_data):
            # Direct Spotify URL or special keyword
            if is_special_download(input_data):
                # Special download keyword
                urls_to_process = [input_data]

                # Get info about the special download
                try:
                    special_type = get_special_download_type(input_data)
                    download_info = await get_special_download_info(special_type)

                    # Notify user about special download
                    reply = await send_message(
                        message,
                        f"📚 **Special Download:** {download_info['description']}\n"
                        f"📊 **Items Found:** {download_info['count']}\n\n"
                        f"⏳ Starting download...",
                    )
                    await auto_delete_message(reply, time=300)
                except Exception as e:
                    LOGGER.error(f"Failed to get special download info: {e}")
                    reply = await send_message(
                        message, f"❌ Failed to process special download: {e}"
                    )
                    await auto_delete_message(reply, time=300)
                    return []
            else:
                # Regular Spotify URL
                normalized_url = ZotifyUrlParser.normalize_spotify_url(input_data)
                if normalized_url:
                    urls_to_process = [normalized_url]
                else:
                    reply = await send_message(message, "❌ Invalid Spotify URL!")
                    await auto_delete_message(reply, time=300)
                    return []
        else:
            # Search query - find first result
            try:
                results = await search_music(input_data, ["track"])
                if results.get("track"):
                    first_track = results["track"][0]
                    spotify_url = (
                        f"https://open.spotify.com/track/{first_track['id']}"
                    )
                    urls_to_process = [spotify_url]

                    # Notify user about auto-selection
                    reply = await send_message(
                        message,
                        f"🔍 Auto-selected first search result:\n"
                        f"🎵 **{first_track['name']}** by **{', '.join(first_track['artists'])}**",
                    )
                    await auto_delete_message(reply, time=300)
                else:
                    reply = await send_message(
                        message, f"❌ No tracks found for: {input_data}"
                    )
                    await auto_delete_message(reply, time=300)
                    return []
            except Exception as e:
                LOGGER.error(f"Search failed: {e}")
                reply = await send_message(message, f"❌ Search failed: {e}")
                await auto_delete_message(reply, time=300)
                return []

        if not urls_to_process:
            reply = await send_message(
                message, "❌ No valid Spotify URLs to process!"
            )
            await auto_delete_message(reply, time=300)
            return []

        return urls_to_process

    @staticmethod
    @new_task
    async def zotify_mirror(_, message):
        """Handle Zotify mirror command"""
        await ZotifyCommands._process_zotify_download(message, is_leech=False)

    @staticmethod
    @new_task
    async def zotify_leech(_, message):
        """Handle Zotify leech command"""
        await ZotifyCommands._process_zotify_download(message, is_leech=True)

    @staticmethod
    @new_task
    async def zotify_search(_, message):
        """Handle Zotify search command"""
        # Check if Zotify is enabled
        if not is_zotify_enabled():
            reply = await send_message(message, "❌ Zotify is disabled!")
            await auto_delete_message(reply, time=300)
            return

        # Check credentials
        user_id = message.from_user.id
        if not await has_zotify_credentials(user_id):
            reply = await send_message(
                message,
                "❌ Zotify credentials not configured!\n\n"
                "Please configure Spotify credentials in bot settings.",
            )
            await auto_delete_message(reply, time=300)
            return

        # Get search query
        text = message.text.split(maxsplit=1)
        if len(text) < 2:
            reply = await send_message(
                message,
                "🔍 <b>Zotify Search Help</b>\n\n"
                "❌ <b>Please provide a search query!</b>\n\n"
                "📋 <b>Usage:</b>\n"
                "• <code>/zs &lt;query&gt;</code>\n"
                "• <code>/zs</code> <i>(reply to message with query)</i>\n\n"
                "💡 <b>Examples:</b>\n"
                "• <code>/zs Bohemian Rhapsody Queen</code>\n"
                "• <code>/zs Taylor Swift Anti-Hero</code>\n"
                "• <code>/zs Daft Punk Random Access Memories</code>\n\n"
                "📁 <b>Note:</b> Search results are always <b>leeched to Telegram</b> for easy access!\n\n"
                "🎵 <b>Supported Content:</b>\n"
                "🎧 <b>Tracks</b> - Individual songs with metadata\n"
                "💿 <b>Albums</b> - Complete albums with artwork\n"
                "📋 <b>Playlists</b> - Public playlists\n"
                "👤 <b>Artists</b> - Artist profiles and top tracks\n"
                "🎙️ <b>Podcasts</b> - Shows and episodes\n\n"
                "⚡ <b>Quick Tips:</b>\n"
                "• Include artist name for better results\n"
                '• Use quotes for exact matches: <code>"song title"</code>\n'
                "• Search results show quality and format info\n"
                "• Click any result to start download instantly",
            )
            await auto_delete_message(reply, time=300)
            return

        query = text[1].strip()

        try:
            # Create listener for search interface
            from bot.helper.listeners.zotify_listener import ZotifyListener

            listener = ZotifyListener(message, is_leech=True, tag="")

            # Use the new StreamRip-style search interface
            from bot.helper.mirror_leech_utils.zotify_utils.search_handler import (
                show_zotify_search_interface,
            )

            # Show StreamRip-style search interface
            selected_result = await show_zotify_search_interface(listener, query)

            if selected_result:
                # User selected a result, start download
                url = selected_result["url"]

                # Set the URL and start download
                listener.url = url

                # Import and start Zotify download
                from bot.helper.mirror_leech_utils.download_utils.zotify_download import (
                    add_zotify_download,
                )

                await add_zotify_download(listener, url)
            # If no result selected (cancelled), the interface already handled the message

        except Exception as e:
            LOGGER.error(f"Zotify search failed: {e}")
            reply = await send_message(message, f"❌ Search failed: {e}")
            await auto_delete_message(reply, time=300)


async def _extract_zotify_metadata_name(url: str) -> str | None:
    """Extract actual album/playlist/artist name from Spotify using zotify library"""
    try:
        # Import zotify modules from venv
        import sys
        from pathlib import Path

        # Add production venv to path (UV creates .venv in project root)
        project_root = Path(__file__).parent.parent.parent
        venv_path = None

        # Production: UV creates .venv in project root
        venv_base = project_root / ".venv" / "lib"

        if venv_base.exists():
            # Try Python 3.13 first (production), then fallback to others
            for py_version in [
                "python3.13",
                "python3.12",
                "python3.11",
                "python3.10",
            ]:
                potential_path = venv_base / py_version / "site-packages"
                if potential_path.exists():
                    venv_path = potential_path
                    break

        if venv_path and str(venv_path) not in sys.path:
            sys.path.insert(0, str(venv_path))

        # Import zotify modules
        from zotify import Session
        from zotify.collections import Album, Artist, Playlist, Show

        # Parse URL to get content type and ID
        from bot.helper.mirror_leech_utils.zotify_utils.url_parser import (
            ZotifyUrlParser,
        )

        # Get zotify config
        from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import (
            zotify_config,
        )

        parsed = ZotifyUrlParser.parse_spotify_url(url)
        if not parsed:
            return None

        content_type, spotify_id = parsed

        # Create session
        auth_method = zotify_config.get_auth_method()
        if auth_method != "file":
            return None  # Only support file-based auth for metadata extraction

        # Wrap blocking operations in threads
        session = await asyncio.to_thread(
            Session.from_file,
            zotify_config.get_credentials_path(),
            zotify_config.get_download_config()["language"],
        )

        # Get API client - wrap in thread
        api = await asyncio.to_thread(session.api)

        # Get metadata based on content type using Collection classes
        if content_type == "album":
            album = Album(spotify_id, api)
            # Get album name from metadata
            if album.playables:
                for metadata in album.playables[0].metadata:
                    if metadata.name == "album":
                        return metadata.string
            return None
        if content_type == "playlist":
            playlist = Playlist(spotify_id, api)
            # Get playlist name from metadata
            if playlist.playables:
                for metadata in playlist.playables[0].metadata:
                    if metadata.name == "playlist":
                        return metadata.string
            return None
        if content_type == "artist":
            artist = Artist(spotify_id, api)
            # Get artist name from metadata
            if artist.playables:
                for metadata in artist.playables[0].metadata:
                    if metadata.name == "album_artist":
                        return metadata.string
            return None
        if content_type == "track":
            track = session.get_track(spotify_id)
            # For tracks, use "Artist - Title" format
            track_metadata = track.metadata
            artist_name = None
            title = None
            for meta in track_metadata:
                if meta.name == "artist":
                    artist_name = meta.string
                elif meta.name == "title":
                    title = meta.string
            if artist_name and title:
                return f"{artist_name} - {title}"
            return title
        if content_type == "show":
            show = Show(spotify_id, api)
            # Get show name from metadata
            if show.playables:
                for metadata in show.playables[0].metadata:
                    if metadata.name == "podcast":
                        return metadata.string
            return None
        if content_type == "episode":
            episode = session.get_episode(spotify_id)
            # For episodes, use "Show - Episode" format
            episode_metadata = episode.metadata
            show_name = None
            episode_title = None
            for meta in episode_metadata:
                if meta.name == "podcast":
                    show_name = meta.string
                elif meta.name == "title":
                    episode_title = meta.string
            if show_name and episode_title:
                return f"{show_name} - {episode_title}"
            return episode_title

        return None

    except Exception as e:
        LOGGER.warning(f"Failed to extract zotify metadata name: {e}")
        return None


# Export command functions for handler registration
zotify_mirror = ZotifyCommands.zotify_mirror
zotify_leech = ZotifyCommands.zotify_leech
zotify_search = ZotifyCommands.zotify_search
