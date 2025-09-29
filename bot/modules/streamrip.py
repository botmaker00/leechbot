import asyncio
import os

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import arg_parser, new_task
from bot.helper.mirror_leech_utils.download_utils.streamrip_download import (
    add_streamrip_download,
)
from bot.helper.mirror_leech_utils.streamrip_utils.quality_selector import (
    show_quality_selector,
)
from bot.helper.mirror_leech_utils.streamrip_utils.search_handler import (
    search_music,
    search_music_auto_first,
)
from bot.helper.mirror_leech_utils.streamrip_utils.url_parser import (
    is_file_input,
    is_lastfm_url,
    is_streamrip_url,
    parse_file_content,
    parse_streamrip_url,
)
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)


class StreamripCommands:
    """Streamrip download commands"""

    @staticmethod
    def _get_streamrip_args():
        """Get streamrip-specific argument definitions including standard mirror/leech flags"""
        return {
            # Streamrip specific flags
            "-q": "",  # Quality level
            "-quality": "",  # Quality level (alias)
            "-c": "",  # Codec
            "-codec": "",  # Codec (alias)
            "-f": False,  # Force run
            "-fd": False,  # Force download
            # Standard mirror/leech flags for upload destination
            "-up": "",  # Upload destination
            "-rcf": "",  # Rclone flags
            "-n": "",  # Custom name
            "link": "",
        }

    @staticmethod
    def _parse_search_args(args_list):
        """Custom argument parser for search commands"""
        args = {
            "-p": "",
            "-platform": "",
            "-t": "",
            "-type": "",
            "-f": False,
            "-first": False,
            "-n": "",
            "-num": "",
            "link": "",
        }

        i = 0
        while i < len(args_list):
            arg = args_list[i]

            if (
                arg in ["-p", "-platform"]
                or arg in ["-t", "-type"]
                or arg in ["-n", "-num"]
            ):
                if i + 1 < len(args_list) and not args_list[i + 1].startswith("-"):
                    args[arg] = args_list[i + 1]
                    i += 2
                else:
                    i += 1
            elif arg in ["-f", "-first"]:
                args[arg] = True
                i += 1
            else:
                # Non-flag argument goes to link
                if args["link"]:
                    args["link"] += " " + arg
                else:
                    args["link"] = arg
                i += 1

        return args

    @staticmethod
    async def _process_streamrip_download(message, is_leech: bool):
        """Shared function for processing streamrip downloads (mirror/leech)"""
        if not Config.STREAMRIP_ENABLED:
            reply = await send_message(
                message, "❌ Streamrip downloads are disabled!"
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse arguments with streamrip-specific flags only
        if not message.text:
            reply = await send_message(message, "❌ No command text provided.")
            await auto_delete_message(reply, time=300)
            return

        text = message.text.split()
        args = StreamripCommands._get_streamrip_args()
        arg_parser(text[1:], args)

        # Get input from message (URL, file content, or ID format)
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
                message, COMMAND_USAGE["streamrip"][0], COMMAND_USAGE["streamrip"][1]
            )
            await auto_delete_message(reply, time=600)
            return

        # Process input and get URLs to download
        urls_to_process = await StreamripCommands._process_input(input_data, message)
        if not urls_to_process:
            return

        # Delete original command message and replied message instantly
        try:
            await delete_message(message)
            if message.reply_to_message:
                await delete_message(message.reply_to_message)
        except Exception as e:
            LOGGER.error(f"Failed to delete command messages: {e}")

        # For batch downloads, show confirmation
        if len(urls_to_process) > 1:
            download_type = "Leech" if is_leech else "Mirror"
            destination = "Telegram" if is_leech else "Cloud Storage"

            confirm_msg = f"📋 **Batch {download_type} Download**\n\n"
            confirm_msg += f"🔢 **Total Items:** {len(urls_to_process)}\n"
            confirm_msg += f"📁 **Destination:** {destination}\n\n"

            # Show first few URLs as preview
            preview_count = min(3, len(urls_to_process))
            confirm_msg += "**Preview:**\n"
            for i, url in enumerate(urls_to_process[:preview_count]):
                parsed = await parse_streamrip_url(url)
                if parsed:
                    platform, media_type, _ = parsed
                    confirm_msg += (
                        f"{i + 1}. {platform.title()} {media_type.title()}\n"
                    )
                else:
                    confirm_msg += (
                        f"{i + 1}. {url[:40]}{'...' if len(url) > 40 else ''}\n"
                    )

            if len(urls_to_process) > preview_count:
                confirm_msg += (
                    f"... and {len(urls_to_process) - preview_count} more\n"
                )

            confirm_msg += "\n🚀 Starting batch download..."

            batch_msg = await send_message(message, confirm_msg)
            await auto_delete_message(batch_msg, time=60)

        # Process each URL
        for i, url in enumerate(urls_to_process):
            try:
                # Parse URL to get platform info
                parsed = await parse_streamrip_url(url)
                if not parsed:
                    continue

                # Safely unpack the parsed result
                if not isinstance(parsed, tuple | list) or len(parsed) != 3:
                    LOGGER.warning(f"Invalid parsed result from URL {url}: {parsed}")
                    continue

                platform, media_type, _ = parsed

                # Create proper streamrip listener for each download
                from bot.helper.listeners.streamrip_listener import StreamripListener

                listener = StreamripListener(message, isLeech=is_leech)

                # Set upload destination and other standard flags
                listener.up_dest = args.get("-up", "")
                listener.rc_flags = args.get("-rcf", "")
                if args.get("-n"):
                    listener.name = args.get("-n")
                else:
                    # Extract actual album/playlist/artist name from streaming platform
                    extracted_name = await _extract_streamrip_metadata_name(
                        url, platform, media_type
                    )
                    if extracted_name:
                        listener.name = extracted_name

                # Set platform and media_type attributes for telegram uploader
                listener.platform = platform
                listener.media_type = media_type

                # For batch downloads, add item number to tag
                if len(urls_to_process) > 1:
                    listener.tag = f"[{i + 1}/{len(urls_to_process)}]"

                # Check for quality selection
                quality = None
                codec = None

                # Parse quality from arguments
                if "q" in args or "quality" in args:
                    try:
                        quality = int(args.get("q") or args.get("quality"))
                        if quality not in range(5):  # 0-4
                            raise ValueError("Quality must be 0-4")
                    except ValueError:
                        reply = await send_message(
                            message,
                            "❌ Invalid quality! Use 0-4:\n"
                            "• 0: 128 kbps\n• 1: 320 kbps\n• 2: CD Quality\n• 3: Hi-Res\n• 4: Hi-Res+",
                        )
                        await auto_delete_message(reply, time=300)
                        return

                # Parse codec from arguments
                if "c" in args or "codec" in args:
                    codec = args.get("c") or args.get("codec")
                    if codec not in Config.STREAMRIP_SUPPORTED_CODECS:
                        reply = await send_message(
                            message,
                            f"❌ Invalid codec! Supported: {', '.join(Config.STREAMRIP_SUPPORTED_CODECS)}",
                        )
                        await auto_delete_message(reply, time=300)
                        return

                # Show quality selector if not specified (only for first item in batch)
                if (quality is None or codec is None) and i == 0:
                    selection = await show_quality_selector(
                        listener, platform, media_type
                    )
                    if not selection:
                        return  # User cancelled or timeout

                    if quality is None:
                        quality = selection["quality"]
                    if codec is None:
                        codec = selection["codec"]

                # Check for force download flag
                force_download = args.get("f", False) or args.get("fd", False)

                # Start download
                await add_streamrip_download(
                    listener, url, quality, codec, force_download
                )

            except Exception as e:
                LOGGER.error(f"Error processing URL {url}: {e}")
                if len(urls_to_process) == 1:
                    # For single URL, show error to user
                    reply = await send_message(
                        message, f"❌ Error processing URL: {e!s}"
                    )
                    await auto_delete_message(reply, time=300)
                # For batch, just log and continue

    @staticmethod
    async def _process_input(input_data: str, message) -> list:
        """Process input data and return list of URLs to download"""
        urls_to_process = []

        # Determine input type and process accordingly
        if is_file_input(input_data):
            # Handle file content (multiple URLs/IDs)
            urls_to_process = await parse_file_content(input_data)
            if not urls_to_process:
                reply = await send_message(
                    message, "❌ No valid URLs found in file content!"
                )
                await auto_delete_message(reply, time=300)
                return []
        else:
            # Single URL or ID format
            urls_to_process = [input_data]

        # Validate all URLs/IDs
        valid_urls = []
        for url in urls_to_process:
            if await is_streamrip_url(url) or is_lastfm_url(url) or ":" in url:
                valid_urls.append(url)

        if not valid_urls:
            reply = await send_message(message, "❌ No valid streamrip URLs found!")
            await auto_delete_message(reply, time=300)
            return []

        return valid_urls

    @staticmethod
    @new_task
    async def streamrip_mirror(_, message):
        """Handle streamrip mirror command"""
        await StreamripCommands._process_streamrip_download(message, is_leech=False)

    @staticmethod
    @new_task
    async def streamrip_leech(_, message):
        """Handle streamrip leech command"""
        await StreamripCommands._process_streamrip_download(message, is_leech=True)

    @staticmethod
    @new_task
    async def streamrip_search(_, message):
        """Handle streamrip search command"""
        if not Config.STREAMRIP_ENABLED:
            reply = await send_message(
                message,
                "❌ <b>Streamrip downloads are disabled!</b>\n\n"
                "💡 <i>Enable streamrip in bot settings to use this feature.</i>",
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse arguments using custom search parser
        if not message.text:
            reply = await send_message(message, "❌ No command text provided.")
            await auto_delete_message(reply, time=300)
            return

        text = message.text.split()
        args = StreamripCommands._parse_search_args(text[1:])

        # Get search query - reply takes precedence over command arguments
        query = ""

        # Check if replying to a message with query (reply always takes precedence)
        if message.reply_to_message and message.reply_to_message.text:
            query = message.reply_to_message.text.strip()
        else:
            # If no reply, get from command arguments
            query = args.get("link", "").strip()

        if not query:
            reply = await send_message(
                message,
                "🔍 <b>Streamrip Search Help</b>\n\n"
                "❌ <b>Please provide a search query!</b>\n\n"
                "📋 <b>Usage:</b>\n"
                "• <code>/srs &lt;query&gt; [options]</code>\n"
                "• <code>/srs [options]</code> <i>(reply to message with query)</i>\n\n"
                "💡 <b>Examples:</b>\n"
                "• <code>/srs Daft Punk Random Access Memories</code>\n"
                '• <code>/srs -p qobuz</code> <i>(reply to: "Thriller")</i>\n\n'
                "📁 <b>Note:</b> Search results are always <b>leeched to Telegram</b> for easy access!\n\n"
                "⚙️ <b>Available Options:</b>\n"
                "• <code>-p &lt;platform&gt;</code> - Search specific platform\n"
                "  <pre>qobuz, tidal, deezer, soundcloud</pre>\n"
                "• <code>-t &lt;type&gt;</code> - Filter by media type\n"
                "  <pre>album, track, artist, playlist</pre>\n"
                "• <code>-f</code> - Auto-download first result\n"
                "• <code>-n &lt;number&gt;</code> - Limit results (default: 200)\n\n"
                "🎯 <b>Command Examples:</b>\n"
                "• <code>/srs -p qobuz -t album Thriller</code>\n"
                "• <code>/srs -f Blinding Lights</code> <i>(auto-download first)</i>\n"
                "• <code>/srs -p tidal -n 10 Daft Punk</code>\n\n"
                "💬 <b>Reply Examples:</b>\n"
                '• Reply to <code>"Random Access Memories"</code> with <code>/srs -p qobuz -t album</code>\n'
                '• Reply to <code>"Get Lucky"</code> with <code>/srs -f</code>\n\n'
                "🎵 <b>Supported Platforms:</b>\n"
                "🟦 <b>Qobuz</b> - <pre>Hi-Res FLAC (24-bit/192kHz)</pre>\n"
                "⚫ <b>Tidal</b> - <pre>MQA/Hi-Res (24-bit/96kHz)</pre>\n"
                "🟣 <b>Deezer</b> - <pre>CD Quality (16-bit/44.1kHz)</pre>\n"
                "🟠 <b>SoundCloud</b> - <pre>MP3 320kbps</pre>",
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse platform filter - handle both -p and -platform flags
        platform = None
        platform_value = args.get("-p") or args.get("-platform")
        if platform_value and platform_value != "":
            platform = platform_value.lower()
            supported_platforms = ["qobuz", "tidal", "deezer", "soundcloud"]
            if platform not in supported_platforms:
                reply = await send_message(
                    message,
                    f"❌ <b>Invalid platform:</b> <code>{platform}</code>\n\n"
                    "🎵 <b>Supported platforms:</b>\n"
                    "🟦 <code>qobuz</code> - Hi-Res FLAC\n"
                    "⚫ <code>tidal</code> - MQA/Hi-Res\n"
                    "🟣 <code>deezer</code> - CD Quality\n"
                    "🟠 <code>soundcloud</code> - MP3 320kbps",
                )
                await auto_delete_message(reply, time=300)
                return

        # Parse media type filter - handle both -t and -type flags
        media_type_filter = None
        type_value = args.get("-t") or args.get("-type")
        if type_value and type_value != "":
            media_type_filter = type_value.lower()
            supported_types = ["album", "track", "artist", "playlist"]
            if media_type_filter not in supported_types:
                reply = await send_message(
                    message,
                    f"❌ <b>Invalid media type:</b> <code>{media_type_filter}</code>\n\n"
                    "📁 <b>Supported media types:</b>\n"
                    "🎵 <code>track</code> - Individual songs\n"
                    "💿 <code>album</code> - Full albums\n"
                    "👤 <code>artist</code> - Artist profiles\n"
                    "📋 <code>playlist</code> - Curated playlists",
                )
                await auto_delete_message(reply, time=300)
                return

        # Parse auto-download first result flag - handle both -f and -first flags
        auto_first = bool(args.get("-f")) or bool(args.get("-first"))

        # Parse result limit - handle both -n and -num flags
        result_limit = Config.STREAMRIP_MAX_SEARCH_RESULTS
        limit_value = args.get("-n") or args.get("-num")
        if limit_value and limit_value != "":
            try:
                result_limit = int(limit_value)
                if result_limit < 1:
                    raise ValueError("Result limit must be at least 1")
            except ValueError:
                reply = await send_message(
                    message,
                    "❌ <b>Invalid result limit!</b>\n\n"
                    "📊 <b>Requirements:</b>\n"
                    "• Must be a <b>positive number</b> (minimum: <code>1</code>)\n"
                    "• <b>Example:</b> <code>/srs -n 50 daft punk</code>\n"
                    "• <b>Note:</b> Higher numbers may take longer to search",
                )
                await auto_delete_message(reply, time=300)
                return

        # Delete command message and reply message instantly
        messages_to_delete = [message]
        if message.reply_to_message:
            messages_to_delete.append(message.reply_to_message)

        # Delete messages instantly without waiting
        asyncio.create_task(delete_message(*messages_to_delete))  # noqa: RUF006

        # Create proper streamrip listener - always leech for search results (users expect files in Telegram)
        from bot.helper.listeners.streamrip_listener import StreamripListener

        listener = StreamripListener(message, isLeech=True)

        # Search results are always leeched, so no upload destination needed
        listener.up_dest = ""
        listener.rc_flags = ""

        # Perform search with all parameters
        if auto_first:
            # For auto-first, we need to implement direct search without interactive selection
            result = await search_music_auto_first(
                listener, query, platform, media_type_filter, result_limit
            )
        else:
            # Regular interactive search
            result = await search_music(
                listener, query, platform, media_type_filter, result_limit
            )

        if not result:
            return  # Search was cancelled or failed

        # Start download with selected result
        url = result["url"]
        platform = result["platform"]
        media_type = result["type"]

        # Extract actual name from search result
        extracted_name = await _extract_streamrip_metadata_name(
            url, platform, media_type
        )
        if extracted_name:
            listener.name = extracted_name

        # Set platform and media_type attributes for telegram uploader
        listener.platform = platform
        listener.media_type = media_type

        # Show quality selector
        selection = await show_quality_selector(listener, platform, media_type)

        if not selection:
            return  # User cancelled or timeout

        quality = selection["quality"]
        codec = selection["codec"]

        # Delete original command message and replied message instantly before starting download
        try:
            await delete_message(message)
            if message.reply_to_message:
                await delete_message(message.reply_to_message)
        except Exception as e:
            LOGGER.error(f"Failed to delete command messages: {e}")

        # Start download (search results don't support force flag currently)
        await add_streamrip_download(listener, url, quality, codec, False)


async def _extract_streamrip_metadata_name(
    url: str, platform: str, media_type: str
) -> str | None:
    """Extract actual album/playlist/artist name from streaming platform using streamrip library"""
    try:
        # Import streamrip modules from venv
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

        # Import streamrip modules
        from streamrip.rip.main import Main

        # Get streamrip config
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            streamrip_config,
        )

        config = streamrip_config.get_config()
        if not config:
            return None

        # Create Main instance
        main = Main(config)

        # Parse URL to get media ID
        from bot.helper.mirror_leech_utils.streamrip_utils.url_parser import (
            parse_streamrip_url,
        )

        parsed = await parse_streamrip_url(url)
        if not parsed:
            return None

        # Safely unpack the parsed result
        if not isinstance(parsed, tuple | list) or len(parsed) != 3:
            LOGGER.warning(f"Invalid parsed result from URL {url}: {parsed}")
            return None

        platform, media_type, media_id = parsed

        # Get authenticated client
        client = await main.get_logged_in_client(platform)
        if not client:
            return None

        # Get metadata using streamrip's client
        metadata = await client.get_metadata(media_id, media_type)
        if not metadata:
            return None

        # Extract name based on media type
        if media_type in {"album", "playlist"}:
            return getattr(metadata, "title", None) or getattr(
                metadata, "name", None
            )
        if media_type == "artist":
            return getattr(metadata, "name", None) or getattr(
                metadata, "title", None
            )
        if media_type == "track":
            # For tracks, use "Artist - Title" format
            artist = (
                getattr(metadata, "artist", None)
                or getattr(metadata, "artists", [None])[0]
            )
            title = getattr(metadata, "title", None) or getattr(
                metadata, "name", None
            )
            if artist and title:
                return f"{artist} - {title}"
            return title

        return None

    except Exception as e:
        LOGGER.warning(f"Failed to extract streamrip metadata name: {e}")
        return None


# Export command functions for handlers.py
streamrip_mirror = StreamripCommands.streamrip_mirror
streamrip_leech = StreamripCommands.streamrip_leech
streamrip_search = StreamripCommands.streamrip_search
