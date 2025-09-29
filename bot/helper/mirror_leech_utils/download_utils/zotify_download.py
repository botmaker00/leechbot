"""
Optimized Zotify download implementation
"""

import asyncio
import contextlib
import gc
import os
import shutil
import time
from collections import deque
from pathlib import Path

from tqdm import tqdm
from zotify import Session
from zotify.collections import Album, Artist, Playlist, Show
from zotify.utils import AudioFormat, ImageSize

from bot import DOWNLOAD_DIR, LOGGER, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
)
from bot.helper.mirror_leech_utils.status_utils.zotify_status import (
    ZotifyDownloadStatus,
)
from bot.helper.mirror_leech_utils.zotify_utils.improved_session_manager import (
    simple_session_manager,
)
from bot.helper.mirror_leech_utils.zotify_utils.quality_selector import (
    show_zotify_quality_selector,
)
from bot.helper.mirror_leech_utils.zotify_utils.special_downloads import (
    get_special_download_info,
    get_special_download_type,
    is_special_download,
)
from bot.helper.mirror_leech_utils.zotify_utils.url_parser import ZotifyUrlParser
from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import zotify_config
from bot.helper.telegram_helper.message_utils import send_status_message


class ZotifyDownloadHelper:
    """Helper class for Zotify downloads"""

    def __init__(self, listener, url: str):
        self.listener = listener
        self.url = url
        self._session = None
        self._download_path = None
        self._is_downloading = False
        self._current_track = ""
        self._total_tracks = 0
        self._downloaded_tracks = 0
        self._start_time = time.time()
        # Optimized progress tracking with memory efficiency
        self._current_downloaded = 0
        self._current_total = 0
        self._current_speed = 0
        self._last_update = time.time()
        # Enhanced progress tracking with bounded memory usage
        self._total_size = 0
        self._downloaded_size = 0
        self._current_file_size = 0
        self._current_file_downloaded = 0
        # Use deque for bounded speed samples (memory efficient)
        self._speed_samples = deque(maxlen=10)  # Keep only last 10 samples
        self._last_downloaded = 0
        self._progress_callback = None
        # Memory optimization
        self._last_gc_time = time.time()
        self._gc_interval = 60  # Force GC every minute

        # Cancellation tracking
        self._download_tasks = set()  # Track active download tasks
        self._progress_tasks = set()  # Track progress monitoring tasks

    async def ensure_valid_session(self, session: Session | None) -> Session | None:
        """Ensure we have a valid session, recreate if necessary"""
        if (
            not session
            or not hasattr(session, "api")
            or not hasattr(session, "rate_limiter")
        ):
            LOGGER.warning("Session is invalid, creating new session")
            return await self.get_session()
        return session

    async def get_session(self) -> Session | None:
        """Get session from simple session manager"""
        try:
            return await simple_session_manager.get_session()
        except Exception as e:
            LOGGER.error(f"Failed to get session: {e}")
            return None

    async def get_zotify_config(self):
        """Get Zotify config object with validation"""
        if not hasattr(self, "_zotify_config"):
            try:
                self._zotify_config = zotify_config.create_zotify_config()

                # Validate that we got a proper config object
                if not self._zotify_config:
                    LOGGER.error("create_zotify_config returned None")
                    raise ValueError("Failed to create Zotify config")

                if isinstance(self._zotify_config, bool):
                    LOGGER.error(
                        f"create_zotify_config returned boolean: {self._zotify_config}"
                    )
                    raise ValueError(
                        "Zotify config creation returned boolean instead of config object"
                    )

            except Exception as e:
                LOGGER.error(f"Failed to create Zotify config: {e}")
                raise

        return self._zotify_config

    def cancel_download(self):
        """Cancel all active download tasks and set cancellation flag"""
        LOGGER.info("Cancelling Zotify download tasks...")

        # Set cancellation flag
        self.listener.is_cancelled = True

        # Cancel all active download tasks
        for task in self._download_tasks.copy():
            if not task.done():
                task.cancel()
                LOGGER.debug(f"Cancelled download task: {task}")

        # Cancel all progress monitoring tasks
        for task in self._progress_tasks.copy():
            if not task.done():
                task.cancel()
                LOGGER.debug(f"Cancelled progress task: {task}")

        # Clear task sets
        self._download_tasks.clear()
        self._progress_tasks.clear()

        LOGGER.info("Zotify download cancellation completed")

    def get_progress_info(self) -> dict:
        """Get optimized progress information with minimal CPU overhead"""
        current_time = time.time()

        # Periodic garbage collection for memory optimization
        if current_time - self._last_gc_time > self._gc_interval:
            gc.collect()
            self._last_gc_time = current_time

        # Calculate speed efficiently
        speed = 0
        if self._speed_samples:
            # Use simple average of recent samples
            speed = sum(self._speed_samples) / len(self._speed_samples)

        return {
            "total_tracks": self._total_tracks,
            "downloaded_tracks": self._downloaded_tracks,
            "current_track": self._current_track,
            "total_size": self._total_size,
            "downloaded_size": self._downloaded_size,
            "current_file_size": self._current_file_size,
            "current_file_downloaded": self._current_file_downloaded,
            "current_speed": speed,
            "is_downloading": self._is_downloading,
            "start_time": self._start_time,
        }

    def _update_speed(self, bytes_downloaded: int):
        """Update speed calculation with memory-efficient sampling"""
        current_time = time.time()
        time_diff = current_time - self._last_update

        if time_diff >= 1.0:  # Update every second
            if self._last_downloaded > 0:
                bytes_diff = bytes_downloaded - self._last_downloaded
                speed = bytes_diff / time_diff
                self._speed_samples.append(speed)

            self._last_downloaded = bytes_downloaded
            self._last_update = current_time

    def _estimate_total_size(self):
        """Estimate total download size based on track count and quality"""
        if self._total_tracks > 0:
            # Estimate based on quality settings
            try:
                config = (
                    self._zotify_config if hasattr(self, "_zotify_config") else None
                )
                if config and hasattr(config, "download_quality"):
                    quality = config.download_quality
                    # Rough size estimates per track based on quality
                    size_estimates = {
                        "VERY_HIGH": 8 * 1024 * 1024,  # ~8MB per track
                        "HIGH": 5 * 1024 * 1024,  # ~5MB per track
                        "NORMAL": 3 * 1024 * 1024,  # ~3MB per track
                        "AUTO": 4 * 1024 * 1024,  # ~4MB per track
                    }
                    estimated_per_track = size_estimates.get(
                        str(quality), 4 * 1024 * 1024
                    )
                else:
                    estimated_per_track = 4 * 1024 * 1024  # Default 4MB

                self._total_size = self._total_tracks * estimated_per_track
            except Exception:
                # Fallback estimation
                self._total_size = self._total_tracks * 4 * 1024 * 1024

    def _get_file_extension(self, audio_format: AudioFormat) -> str:
        """Get file extension from AudioFormat enum"""
        format_extensions = {
            AudioFormat.VORBIS: "ogg",
            AudioFormat.MP3: "mp3",
            AudioFormat.FLAC: "flac",
            AudioFormat.AAC: "m4a",
            AudioFormat.WAV: "wav",
        }
        return format_extensions.get(audio_format, "ogg")

    async def download(self) -> bool:
        """Main download method"""
        try:
            # Check if this is a special download first
            if is_special_download(self.url):
                return await self._download_special()

            # Parse URL to get content type and ID
            parsed = ZotifyUrlParser.parse_spotify_url(self.url)
            if not parsed:
                LOGGER.error(f"Invalid Spotify URL: {self.url}")
                return False

            content_type, spotify_id = parsed

            # Quality selection is now handled in add_zotify_download()
            # Get session
            session = await self.get_session()
            if not session:
                LOGGER.error("Failed to create Zotify session")
                return False

            # Setup download directory
            self._download_path = Path(DOWNLOAD_DIR) / f"zotify_{self.listener.mid}"
            self._download_path.mkdir(parents=True, exist_ok=True)

            # Set downloading flag
            self._is_downloading = True

            # Start download based on content type with optimized flow
            success = False
            if content_type == "track":
                self._total_tracks = 1
                self._estimate_total_size()
                success = await self._download_track(session, spotify_id)
            elif content_type == "album":
                config_obj = await self.get_zotify_config()
                # Wrap blocking Album initialization in thread
                album = await asyncio.to_thread(
                    Album, spotify_id, session.api(), config_obj
                )
                self._total_tracks = len(album.playables)
                self._estimate_total_size()
                # Yield control before starting collection download
                await asyncio.sleep(0.1)
                success = await self._download_album(session, spotify_id)
            elif content_type == "playlist":
                config_obj = await self.get_zotify_config()
                # Wrap blocking Playlist initialization in thread
                playlist = await asyncio.to_thread(
                    Playlist, spotify_id, session.api(), config_obj
                )
                self._total_tracks = len(playlist.playables)
                self._estimate_total_size()
                # Yield control before starting collection download
                await asyncio.sleep(0.1)
                success = await self._download_playlist(session, spotify_id)
            elif content_type == "artist":
                config_obj = await self.get_zotify_config()
                # Wrap blocking Artist initialization in thread
                artist = await asyncio.to_thread(
                    Artist, spotify_id, session.api(), config_obj
                )
                self._total_tracks = len(artist.playables)
                self._estimate_total_size()
                # Yield control before starting collection download
                await asyncio.sleep(0.1)
                success = await self._download_artist(session, spotify_id)
            elif content_type == "show":
                # Get show info first to set total tracks
                config_obj = await self.get_zotify_config()
                show = Show(spotify_id, session.api(), config_obj)
                self._total_tracks = len(show.playables)
                self._estimate_total_size()
                success = await self._download_show(session, spotify_id)
            elif content_type == "episode":
                self._total_tracks = 1
                self._estimate_total_size()
                success = await self._download_episode(session, spotify_id)
            else:
                LOGGER.error(f"Unsupported content type: {content_type}")
                return False

            if success:
                # Move downloaded files to listener directory
                await self._finalize_download()
                return True
            LOGGER.error(f"Zotify download failed: {self.url}")
            return False

        except Exception as e:
            error_msg = str(e)
            # Handle specific connection errors
            if any(
                keyword in error_msg
                for keyword in [
                    "Failed reading packet",
                    "Failed to receive packet",
                    "Connection reset by peer",
                    "ConnectionResetError",
                    "ConnectionRefusedError",
                    "Connection refused",
                    "session-packet-receiver",
                    "RuntimeError",
                    "'NoneType' object has no attribute 'send'",
                    "NoneType",
                ]
            ):
                LOGGER.error(f"Zotify connection error: {error_msg}")
            else:
                LOGGER.error(f"Zotify download error: {error_msg}")
            return False
        finally:
            self._is_downloading = False

    async def _download_special(self) -> bool:
        """Download special content (liked tracks, followed artists, etc.)"""
        try:
            special_type = get_special_download_type(self.url)
            if not special_type:
                LOGGER.error(f"Unknown special download type: {self.url}")
                return False

            # Get download info
            download_info = await get_special_download_info(special_type)
            urls = download_info.get("urls", [])

            if not urls:
                LOGGER.warning(f"No items found for {download_info['description']}")
                return False

            self._total_tracks = len(urls)
            self._current_track = f"Downloading {download_info['description']} ({self._total_tracks} items)..."

            # Setup download directory
            self._download_path = Path(DOWNLOAD_DIR) / f"zotify_{self.listener.mid}"
            self._download_path.mkdir(parents=True, exist_ok=True)

            # Get session
            session = await self.get_session()
            if not session:
                LOGGER.error("Failed to create Zotify session")
                return False

            # Download each URL
            success_count = 0
            for i, url in enumerate(urls):
                if self.listener.is_cancelled:
                    break

                self._current_track = (
                    f"Item {i + 1}/{self._total_tracks}: Processing {url}"
                )

                try:
                    # Parse the individual URL
                    parsed = ZotifyUrlParser.parse_spotify_url(url)
                    if not parsed:
                        LOGGER.warning(f"Skipping invalid URL: {url}")
                        continue

                    content_type, spotify_id = parsed

                    # Download based on content type
                    item_success = False
                    if content_type == "track":
                        item_success = await self._download_track(
                            session, spotify_id
                        )
                    elif content_type == "album":
                        item_success = await self._download_album(
                            session, spotify_id
                        )
                    elif content_type == "playlist":
                        item_success = await self._download_playlist(
                            session, spotify_id
                        )
                    elif content_type == "artist":
                        item_success = await self._download_artist(
                            session, spotify_id
                        )
                    elif content_type == "show":
                        item_success = await self._download_show(session, spotify_id)
                    elif content_type == "episode":
                        item_success = await self._download_episode(
                            session, spotify_id
                        )

                    if item_success:
                        success_count += 1
                        self._downloaded_tracks += 1

                except Exception as e:
                    LOGGER.error(f"Failed to download item {url}: {e}")
                    continue

            LOGGER.info(
                f"Special download completed: {success_count}/{len(urls)} items downloaded"
            )
            return success_count > 0

        except Exception as e:
            LOGGER.error(f"Special download failed: {e}")
            return False

    async def _download_track(self, session: Session, track_id: str) -> bool:
        """Download a single track with optimized performance"""
        try:
            # Validate session before use
            if (
                not session
                or not hasattr(session, "api")
                or not hasattr(session, "rate_limiter")
            ):
                LOGGER.error("Invalid session provided to _download_track")
                return False

            # Check cancellation at start
            if self.listener.is_cancelled:
                return False

            self._total_tracks = 1
            self._current_track = "Downloading track..."

            config_obj = await self.get_zotify_config()

            # Check cancellation before rate limiting
            if self.listener.is_cancelled:
                return False

            # Wrap blocking rate limiter in thread with error handling
            try:
                await asyncio.to_thread(session.rate_limiter.apply_limit)
            except Exception as e:
                LOGGER.error(f"Rate limiter error: {e}")
                return False

            # Check cancellation before track fetch
            if self.listener.is_cancelled:
                return False

            # Wrap blocking track metadata fetch in thread
            track = await asyncio.to_thread(session.get_track, track_id)
            if not track:
                LOGGER.error(f"Failed to get track metadata for {track_id}")
                return False

            # Add metadata if configured - wrap in threads to prevent blocking
            if config_obj.save_genre:
                await asyncio.to_thread(track.add_genre)
            if config_obj.all_artists:
                await asyncio.to_thread(track.add_all_artists)

            file_ext = self._get_file_extension(config_obj.audio_format)

            # Get output template from config
            output_template = getattr(
                Config,
                "ZOTIFY_OUTPUT_ALBUM",
                "{album_artist}/{album}/{track_number}. {artists} - {title}",
            )

            try:
                # Wrap blocking output creation in thread
                output = await asyncio.to_thread(
                    track.create_output,
                    ext=file_ext,
                    library=self._download_path,
                    output=output_template,
                    replace=config_obj.replace_existing,
                )

                # Validate that output is not a boolean and is a proper path/object
                if isinstance(output, bool):
                    LOGGER.error(f"track.create_output returned boolean: {output}")
                    return False

                if not output:
                    LOGGER.error("track.create_output returned None or empty value")
                    return False

            except Exception as e:
                LOGGER.error(
                    f"Failed to create output path for track {track_id}: {e}"
                )
                LOGGER.error(
                    f"Parameters used: ext={file_ext}, library={self._download_path}, output={output_template}, replace={config_obj.replace_existing}"
                )
                LOGGER.error(f"Config object type: {type(config_obj)}")
                LOGGER.error(f"Track object type: {type(track)}")
                return False

            self._current_track = f"Downloading: {track.name}"

            # Check cancellation before rate limiting
            if self.listener.is_cancelled:
                return False

            # Apply rate limiting using Zotify's built-in rate limiter - wrap in thread
            await asyncio.to_thread(session.rate_limiter.apply_limit)

            # Mark activity to keep session alive
            simple_session_manager.mark_activity()

            # Check cancellation before download
            if self.listener.is_cancelled:
                return False

            # Download track using Zotify's exact method signature with progress tracking
            try:
                file = await self._download_track_with_progress(
                    track, output, config_obj.download_real_time
                )

                if not file:
                    LOGGER.error("Track download returned None or empty file object")
                    return False

            except Exception as e:
                LOGGER.error(f"Track download failed: {e}")
                if "context manager protocol" in str(e):
                    LOGGER.error(
                        "Context manager error in track download - check output parameter"
                    )
                    LOGGER.error(
                        f"Output parameter: {output} (type: {type(output)})"
                    )
                    LOGGER.error(
                        f"Real-time parameter: {config_obj.download_real_time} (type: {type(config_obj.download_real_time)})"
                    )
                raise

            # Clear consecutive hits on successful download - wrap in thread
            await asyncio.to_thread(session.rate_limiter.clear_consec_hits)

            # Mark activity after successful download
            simple_session_manager.mark_activity()

            # Write metadata and cover art with fully async processing
            if config_obj.save_metadata:
                try:
                    # Wrap metadata operations in threads
                    metadata = await asyncio.to_thread(lambda: track.metadata)
                    if metadata:
                        await asyncio.to_thread(file.write_metadata, metadata)
                    else:
                        LOGGER.warning(f"No metadata available for: {track.name}")
                except Exception as e:
                    LOGGER.warning(f"Failed to write metadata for {track.name}: {e}")

                # Yield control during metadata processing
                await asyncio.sleep(0.05)

                try:
                    # Get cover art with size fallback - wrap in threads
                    cover_art = None
                    artwork_sizes = [
                        config_obj.artwork_size,
                        ImageSize.LARGE,
                        ImageSize.MEDIUM,
                        ImageSize.SMALL,
                    ]

                    for size in artwork_sizes:
                        try:
                            cover_art = await asyncio.to_thread(
                                track.get_cover_art, size
                            )
                            if cover_art:
                                break
                        except Exception:
                            continue

                    if cover_art:
                        await asyncio.to_thread(file.write_cover_art, cover_art)
                        # Cover art written (log removed for cleaner output)
                    else:
                        LOGGER.warning(f"No cover art available for: {track.name}")
                except Exception as e:
                    LOGGER.warning(
                        f"Failed to write cover art for {track.name}: {e}"
                    )

            # Download lyrics with free account handling
            if config_obj.lyrics_file:
                try:
                    # Check if track has lyrics
                    has_lyrics = False
                    with contextlib.suppress(Exception):
                        # For free accounts, lyrics availability might not be accessible
                        has_lyrics = (
                            track.track.has_lyrics
                            if hasattr(track, "track")
                            and hasattr(track.track, "has_lyrics")
                            else False
                        )

                    if has_lyrics:
                        try:
                            # Wrap lyrics operations in threads
                            lyrics = await asyncio.to_thread(track.get_lyrics)
                            if lyrics:
                                await asyncio.to_thread(
                                    lyrics.save, output, prefer_synced=True
                                )
                                LOGGER.info(f"Lyrics downloaded for: {track.name}")
                            else:
                                LOGGER.warning(
                                    f"No lyrics content for: {track.name}"
                                )
                        except Exception as e:
                            # Check if it's a free account limitation - wrap API calls in threads
                            try:
                                api = session.api()
                                user_info = await asyncio.to_thread(
                                    api.invoke_url, "me"
                                )
                                account_type = user_info.get("product", "unknown")
                                if account_type == "free":
                                    LOGGER.info(
                                        f"Lyrics not available for free account: {track.name}"
                                    )
                                else:
                                    LOGGER.warning(
                                        f"Failed to download lyrics for {track.name}: {e}"
                                    )
                            except Exception:
                                LOGGER.warning(
                                    f"Failed to download lyrics for {track.name}: {e}"
                                )
                except Exception as e:
                    LOGGER.warning(f"Lyrics check failed for {track.name}: {e}")

            # Handle transcoding if needed using Zotify's exact method
            if config_obj.audio_format.name != "VORBIS" or config_obj.ffmpeg_args:
                try:
                    file.transcode(
                        audio_format=config_obj.audio_format,  # audio_format parameter
                        download_quality=config_obj.download_quality,  # download_quality parameter
                        bitrate=config_obj.transcode_bitrate,  # bitrate parameter
                        replace=True,  # replace parameter
                        ffmpeg=config_obj.ffmpeg_path,  # ffmpeg parameter
                        opt_args=config_obj.ffmpeg_args.split()
                        if config_obj.ffmpeg_args
                        else [],  # opt_args parameter
                    )
                except Exception as e:
                    LOGGER.warning(f"Transcoding failed: {e}")

            # Clean filename using Zotify's method
            file.clean_filename()

            # Update progress tracking
            if self._total_tracks == 1:
                self._downloaded_tracks = 1
            else:
                self._downloaded_tracks += 1

            return True

        except Exception as e:
            error_msg = str(e)
            LOGGER.error(f"Failed to download track {track_id}: {error_msg}")

            # Provide specific error information for common issues
            if "context manager protocol" in error_msg:
                LOGGER.error(
                    "Context manager error - likely boolean value used where file object expected"
                )
                LOGGER.error(f"Track object type: {type(track)}")
                LOGGER.error(
                    f"Output object type: {type(output) if 'output' in locals() else 'output not created'}"
                )
                LOGGER.error(
                    f"Config object type: {type(config_obj) if 'config_obj' in locals() else 'config not created'}"
                )
            elif "write_audio_stream" in error_msg:
                LOGGER.error(
                    "Error in write_audio_stream - check Zotify library compatibility"
                )
            elif "create_output" in error_msg:
                LOGGER.error(
                    "Error creating output path - check file permissions and path validity"
                )
            elif "Cannot get alternative track" in error_msg:
                LOGGER.warning(
                    f"Track {track_id} is not available in your region or requires premium"
                )
            elif "'NoneType' object has no attribute 'send'" in error_msg:
                LOGGER.error(
                    "Session connection lost during download - will retry with new session"
                )
                # Session will be recreated automatically on next use

            return False

    async def _download_album(self, session: Session, album_id: str) -> bool:
        """Download an album with fully async operations"""
        try:
            # Validate session before use
            if not session or not hasattr(session, "api"):
                LOGGER.error("Invalid session provided to _download_album")
                return False

            config_obj = await self.get_zotify_config()

            # Wrap blocking Album initialization in thread
            album = await asyncio.to_thread(
                Album, album_id, session.api(), config_obj
            )

            self._total_tracks = len(album.playables)
            self._current_track = (
                f"Downloading album ({self._total_tracks} tracks)..."
            )

            # Process tracks in smaller batches to maintain responsiveness
            batch_size = 3  # Process 3 tracks then yield
            for i in range(0, len(album.playables), batch_size):
                if self.listener.is_cancelled:
                    return False

                batch = album.playables[i : i + batch_size]
                for j, playable_data in enumerate(batch):
                    if self.listener.is_cancelled:
                        LOGGER.info("Album download cancelled by user")
                        return False

                    track_num = i + j + 1
                    self._current_track = f"Track {track_num}/{self._total_tracks}"

                    # Ensure session is valid before each track
                    session = await self.ensure_valid_session(session)
                    if not session:
                        LOGGER.error(
                            "Failed to maintain valid session during album download"
                        )
                        return False

                    # Download track and check for cancellation
                    success = await self._download_track(session, playable_data.id)
                    if not success and self.listener.is_cancelled:
                        LOGGER.info("Album download cancelled during track download")
                        return False

                # Yield control after each batch and check cancellation
                await asyncio.sleep(0.2)
                if self.listener.is_cancelled:
                    LOGGER.info("Album download cancelled between batches")
                    return False

            return self._downloaded_tracks > 0

        except Exception as e:
            LOGGER.error(f"Failed to download album {album_id}: {e}")
            return False

    async def _download_playlist(self, session: Session, playlist_id: str) -> bool:
        """Download a playlist with fully async operations"""
        try:
            # Validate session before use
            if not session or not hasattr(session, "api"):
                LOGGER.error("Invalid session provided to _download_playlist")
                return False

            config_obj = await self.get_zotify_config()

            # Wrap blocking Playlist initialization in thread
            playlist = await asyncio.to_thread(
                Playlist, playlist_id, session.api(), config_obj
            )

            self._total_tracks = len(playlist.playables)
            self._current_track = (
                f"Downloading playlist ({self._total_tracks} tracks)..."
            )

            # Process tracks in smaller batches to maintain responsiveness
            batch_size = 3  # Process 3 tracks then yield
            for i in range(0, len(playlist.playables), batch_size):
                if self.listener.is_cancelled:
                    return False

                batch = playlist.playables[i : i + batch_size]
                for j, playable_data in enumerate(batch):
                    if self.listener.is_cancelled:
                        LOGGER.info("Playlist download cancelled by user")
                        return False

                    track_num = i + j + 1
                    self._current_track = f"Track {track_num}/{self._total_tracks}"

                    # Ensure session is valid before each item
                    session = await self.ensure_valid_session(session)
                    if not session:
                        LOGGER.error(
                            "Failed to maintain valid session during playlist download"
                        )
                        return False

                    # Download based on playable type and check for cancellation
                    success = False
                    if playable_data.type.name == "TRACK":
                        success = await self._download_track(
                            session, playable_data.id
                        )
                    elif playable_data.type.name == "EPISODE":
                        success = await self._download_episode(
                            session, playable_data.id
                        )

                    if not success and self.listener.is_cancelled:
                        LOGGER.info(
                            "Playlist download cancelled during item download"
                        )
                        return False

                # Yield control after each batch and check cancellation
                await asyncio.sleep(0.2)
                if self.listener.is_cancelled:
                    LOGGER.info("Playlist download cancelled between batches")
                    return False

            return self._downloaded_tracks > 0

        except Exception as e:
            LOGGER.error(f"Failed to download playlist {playlist_id}: {e}")
            return False

    async def _download_artist(self, session: Session, artist_id: str) -> bool:
        """Download artist's top tracks with fully async operations"""
        try:
            config_obj = await self.get_zotify_config()

            # Wrap blocking Artist initialization in thread
            artist = await asyncio.to_thread(
                Artist, artist_id, session.api(), config_obj
            )

            self._total_tracks = len(artist.playables)
            self._current_track = (
                f"Downloading artist tracks ({self._total_tracks} tracks)..."
            )

            # Process tracks in smaller batches to maintain responsiveness
            batch_size = 3  # Process 3 tracks then yield
            for i in range(0, len(artist.playables), batch_size):
                if self.listener.is_cancelled:
                    return False

                batch = artist.playables[i : i + batch_size]
                for j, playable_data in enumerate(batch):
                    if self.listener.is_cancelled:
                        LOGGER.info("Artist download cancelled by user")
                        return False

                    track_num = i + j + 1
                    self._current_track = f"Track {track_num}/{self._total_tracks}"

                    # Download track and check for cancellation
                    success = await self._download_track(session, playable_data.id)
                    if not success and self.listener.is_cancelled:
                        LOGGER.info(
                            "Artist download cancelled during track download"
                        )
                        return False

                # Yield control after each batch and check cancellation
                await asyncio.sleep(0.2)
                if self.listener.is_cancelled:
                    LOGGER.info("Artist download cancelled between batches")
                    return False

            return self._downloaded_tracks > 0

        except Exception as e:
            LOGGER.error(f"Failed to download artist {artist_id}: {e}")
            return False

    async def _download_show(self, session: Session, show_id: str) -> bool:
        """Download a podcast show with optimized responsiveness"""
        try:
            config_obj = await self.get_zotify_config()
            show = Show(show_id, session.api(), config_obj)

            self._total_tracks = len(show.playables)
            self._current_track = (
                f"Downloading show ({self._total_tracks} episodes)..."
            )

            # Download episodes with async yields for responsiveness
            for i, playable_data in enumerate(show.playables):
                if self.listener.is_cancelled:
                    LOGGER.info("Show download cancelled by user")
                    return False

                self._current_track = f"Episode {i + 1}/{self._total_tracks}"

                # Download episode and check for cancellation
                success = await self._download_episode(session, playable_data.id)
                if not success and self.listener.is_cancelled:
                    LOGGER.info("Show download cancelled during episode download")
                    return False

                # Yield control every episode to keep bot responsive
                await asyncio.sleep(0.1)
                if self.listener.is_cancelled:
                    LOGGER.info("Show download cancelled between episodes")
                    return False

            return self._downloaded_tracks > 0

        except Exception as e:
            LOGGER.error(f"Failed to download show {show_id}: {e}")
            return False

    async def _download_episode(self, session: Session, episode_id: str) -> bool:
        """Download a podcast episode"""
        try:
            # Check cancellation at start
            if self.listener.is_cancelled:
                return False

            self._current_track = "Downloading episode..."

            # Get zotify config object
            config_obj = await self.get_zotify_config()

            # Check cancellation before episode fetch
            if self.listener.is_cancelled:
                return False

            # Get episode - wrap in thread
            episode = await asyncio.to_thread(session.get_episode, episode_id)

            # Get file extension from AudioFormat enum
            file_ext = self._get_file_extension(config_obj.audio_format)

            # Create output path using Zotify's exact method signature with proper folder structure
            try:
                # Wrap episode output creation in thread
                output = await asyncio.to_thread(
                    episode.create_output,
                    ext=file_ext,
                    library=self._download_path,
                    output="{podcast}/{episode_number} - {title}",
                    replace=config_obj.replace_existing,
                )

                # Validate that output is not a boolean and is a proper path/object
                if isinstance(output, bool):
                    LOGGER.error(f"episode.create_output returned boolean: {output}")
                    return False

                if not output:
                    LOGGER.error(
                        "episode.create_output returned None or empty value"
                    )
                    return False

            except Exception as e:
                LOGGER.error(
                    f"Failed to create output path for episode {episode_id}: {e}"
                )
                LOGGER.error(
                    f"Parameters used: ext={file_ext}, library={self._download_path}, output=podcast template, replace={config_obj.replace_existing}"
                )
                LOGGER.error(f"Config object type: {type(config_obj)}")
                LOGGER.error(f"Episode object type: {type(episode)}")
                return False

            self._current_track = f"Downloading: {episode.name}"

            # Check cancellation before rate limiting
            if self.listener.is_cancelled:
                return False

            # Apply rate limiting using Zotify's built-in rate limiter - wrap in thread
            await asyncio.to_thread(session.rate_limiter.apply_limit)

            # Check cancellation before download
            if self.listener.is_cancelled:
                return False

            # Download episode using Zotify's exact method signature with progress tracking
            file = await self._download_episode_with_progress(
                episode, output, config_obj.download_real_time
            )

            # Clear consecutive hits on successful download - wrap in thread
            await asyncio.to_thread(session.rate_limiter.clear_consec_hits)

            # Mark activity after successful episode download
            simple_session_manager.mark_activity()

            # Write metadata and cover art using Zotify's exact methods - wrap in threads
            if config_obj.save_metadata:
                await asyncio.to_thread(file.write_metadata, episode.metadata)
                cover_art = await asyncio.to_thread(
                    episode.get_cover_art, config_obj.artwork_size
                )
                await asyncio.to_thread(file.write_cover_art, cover_art)

            # Handle transcoding if needed using Zotify's exact method
            if config_obj.audio_format.name != "VORBIS" or config_obj.ffmpeg_args:
                try:
                    file.transcode(
                        audio_format=config_obj.audio_format,  # audio_format parameter
                        download_quality=config_obj.download_quality,  # download_quality parameter
                        bitrate=config_obj.transcode_bitrate,  # bitrate parameter
                        replace=True,  # replace parameter
                        ffmpeg=config_obj.ffmpeg_path,  # ffmpeg parameter
                        opt_args=config_obj.ffmpeg_args.split()
                        if config_obj.ffmpeg_args
                        else [],  # opt_args parameter
                    )
                except Exception as e:
                    LOGGER.warning(f"Transcoding failed: {e}")

            file.clean_filename()

            # Update progress tracking
            if self._total_tracks == 1:
                self._downloaded_tracks = 1
            else:
                self._downloaded_tracks += 1

            return True

        except Exception as e:
            LOGGER.error(f"Failed to download episode {episode_id}: {e}")
            return False

    async def _finalize_download(self):
        """Move downloaded files to listener directory preserving folder structure"""
        try:
            if self._download_path and self._download_path.exists():
                # Move all files to listener directory preserving folder structure
                for file_path in self._download_path.rglob("*"):
                    if file_path.is_file():
                        # Preserve the relative path structure
                        relative_path = file_path.relative_to(self._download_path)
                        dest_path = Path(self.listener.dir) / relative_path

                        # Ensure destination directory exists
                        dest_path.parent.mkdir(parents=True, exist_ok=True)

                        # Move the file preserving structure
                        shutil.move(str(file_path), str(dest_path))

                # Clean up temporary directory
                shutil.rmtree(self._download_path, ignore_errors=True)

        except Exception as e:
            LOGGER.error(f"Failed to finalize download: {e}")

    def _update_progress(self, downloaded: int, total: int):
        """Update download progress with speed calculation"""
        current_time = time.time()
        self._current_file_downloaded = downloaded
        self._current_file_size = total

        # Calculate total downloaded size
        self._downloaded_size = (
            self._downloaded_tracks * 5 * 1024 * 1024
        ) + downloaded

        # Calculate speed (bytes per second)
        if current_time - self._last_update >= 1.0:  # Update every second
            bytes_diff = self._downloaded_size - self._last_downloaded
            time_diff = current_time - self._last_update

            if time_diff > 0:
                current_speed = bytes_diff / time_diff

                # Keep last 10 speed samples for smoothing
                self._speed_samples.append(current_speed)
                if len(self._speed_samples) > 10:
                    self._speed_samples.pop(0)

                # Calculate average speed
                self._current_speed = sum(self._speed_samples) / len(
                    self._speed_samples
                )

            self._last_downloaded = self._downloaded_size
            self._last_update = current_time

    def _estimate_total_size(self):
        """Estimate total download size based on content type"""
        if self._total_tracks > 0:
            # Estimate 5MB per track on average
            self._total_size = self._total_tracks * 5 * 1024 * 1024

    async def _download_track_with_progress(self, track, output, real_time=False):
        """Download track with optimized progress tracking"""
        # Validate inputs
        if isinstance(output, bool) or not output:
            raise ValueError("Invalid output parameter")

        try:
            dummy_pbar = tqdm(disable=True)

            # Start download and progress monitoring concurrently
            download_task = asyncio.create_task(
                asyncio.to_thread(
                    track.write_audio_stream, output, dummy_pbar, real_time
                )
            )
            progress_task = asyncio.create_task(
                self._monitor_download_progress(output)
            )

            # Track tasks for cancellation
            self._download_tasks.add(download_task)
            self._progress_tasks.add(progress_task)

            try:
                # Wait for download completion with cancellation check
                return await download_task
            except asyncio.CancelledError:
                LOGGER.info("Track download cancelled by user")
                return None
            finally:
                # Clean up progress monitoring
                progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await progress_task

                # Remove from tracking sets
                self._download_tasks.discard(download_task)
                self._progress_tasks.discard(progress_task)

        except Exception as e:
            # Clean up on error
            if "progress_task" in locals():
                progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await progress_task
            raise e

    async def _monitor_download_progress(self, output_path):
        """Monitor download progress with optimized frequency"""
        if isinstance(output_path, bool) or not output_path:
            return

        output_path_str = str(output_path)

        try:
            while True:
                try:
                    if os.path.exists(output_path_str):
                        current_size = os.path.getsize(output_path_str)
                        estimated_total = 5 * 1024 * 1024  # 5MB average

                        self._update_progress(current_size, estimated_total)

                        # Break if file seems complete
                        if current_size >= estimated_total * 0.9:
                            break

                    # Mark activity periodically during download
                    simple_session_manager.mark_activity()

                    # Reduced frequency to improve responsiveness
                    await asyncio.sleep(1.0)

                except Exception:
                    await asyncio.sleep(2.0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            LOGGER.warning(f"Progress monitoring failed: {e}")

    async def _download_episode_with_progress(
        self, episode, output, real_time=False
    ):
        """Download episode with optimized progress tracking"""
        # Validate inputs
        if isinstance(output, bool) or not output:
            raise ValueError("Invalid output parameter")

        try:
            dummy_pbar = tqdm(disable=True)

            # Start download and progress monitoring concurrently
            download_task = asyncio.create_task(
                asyncio.to_thread(
                    episode.write_audio_stream, output, dummy_pbar, real_time
                )
            )
            progress_task = asyncio.create_task(
                self._monitor_download_progress(output)
            )

            # Track tasks for cancellation
            self._download_tasks.add(download_task)
            self._progress_tasks.add(progress_task)

            try:
                # Wait for download completion with cancellation check
                return await download_task
            except asyncio.CancelledError:
                LOGGER.info("Episode download cancelled by user")
                return None
            finally:
                # Clean up progress monitoring
                progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await progress_task

                # Remove from tracking sets
                self._download_tasks.discard(download_task)
                self._progress_tasks.discard(progress_task)

        except Exception as e:
            # Clean up on error
            if "progress_task" in locals():
                progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await progress_task
            raise e


async def _estimate_zotify_size(url: str) -> int:
    """Estimate download size for Zotify based on URL type"""
    try:
        # Basic size estimates in bytes
        if "track/" in url:
            return 5 * 1024 * 1024  # ~5MB per track
        if "album/" in url:
            return 50 * 1024 * 1024  # ~50MB per album (10 tracks average)
        if "playlist/" in url:
            return 100 * 1024 * 1024  # ~100MB per playlist (20 tracks average)
        if "artist/" in url:
            return 200 * 1024 * 1024  # ~200MB for artist top tracks
        if "show/" in url or "episode/" in url:
            return 50 * 1024 * 1024  # ~50MB per podcast episode
        return 10 * 1024 * 1024  # Default ~10MB
    except Exception:
        return 10 * 1024 * 1024  # Default fallback


async def add_zotify_download(listener, url: str):
    """Add Zotify download to task queue"""
    if not zotify_config.is_enabled():
        await listener.on_download_error("Zotify is disabled")
        return

    if not await zotify_config.has_credentials():
        await listener.on_download_error("Zotify credentials not configured")
        return

    # Check if URL is valid
    if not ZotifyUrlParser.is_spotify_url(url):
        await listener.on_download_error("Invalid Spotify URL")
        return

    # Check limits
    # For Zotify, estimate size based on URL type (track ~5MB, album ~50MB, playlist ~100MB)
    estimated_size = await _estimate_zotify_size(url)
    if estimated_size > 0:
        limit_msg = await limit_checker(estimated_size, listener)
        if limit_msg:
            return

    # Check running tasks and queue management
    add_to_queue, event = await check_running_tasks(listener)

    # Check for duplicates
    msg, button = await stop_duplicate_check(listener)
    if msg:
        await listener.on_download_error(msg, button)
        return

    # Parse URL to get content type for quality selection
    parsed = ZotifyUrlParser.parse_spotify_url(url)
    if not parsed:
        await listener.on_download_error("Invalid Spotify URL format")
        return

    content_type, _ = parsed

    # Show quality selector BEFORE creating task and status
    quality_selection = await show_zotify_quality_selector(listener, content_type)

    if not quality_selection:
        LOGGER.info("Quality selection cancelled or failed")
        await listener.on_download_error("Quality selection cancelled")
        return

    # Apply selected quality and format to config
    selected_quality = quality_selection["quality"]
    selected_format = quality_selection["format"]

    # Update config with user selection
    zotify_config.set_quality(selected_quality)
    zotify_config.set_audio_format(selected_format)

    try:
        # Create download helper
        download_helper = ZotifyDownloadHelper(listener, url)

        # Set zotify-specific attributes on the listener
        listener.url = url

        # Add to task dict with proper status
        async with task_dict_lock:
            task_dict[listener.mid] = ZotifyDownloadStatus(
                listener, download_helper, queued=add_to_queue
            )

        # Handle queuing
        if add_to_queue:
            LOGGER.info(f"Added zotify download to queue: {url}")
            await send_status_message(
                listener.message, "⏳ Added to download queue!"
            )
            await event.wait()
            if listener.is_cancelled:
                return
            LOGGER.info(f"Start from Queued/Download: {listener.name}")

        # Update task dict for active download
        async with task_dict_lock:
            task_dict[listener.mid] = ZotifyDownloadStatus(
                listener, download_helper, queued=False
            )

        # Send status message
        await send_status_message(listener.message)

        # Start download
        success = await download_helper.download()

        if success:
            # Initialize media tools settings before upload (only for specialized listeners)
            if hasattr(listener, "initialize_media_tools"):
                await listener.initialize_media_tools()
            await listener.on_download_complete()
        else:
            await listener.on_download_error("Zotify download failed")

    except Exception as e:
        LOGGER.error(f"Zotify download error: {e}")
        await listener.on_download_error(f"Zotify download error: {e}")
