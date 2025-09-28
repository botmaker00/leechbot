import os
import re
import time
from pathlib import Path

from bot import DOWNLOAD_DIR, LOGGER, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.ext_utils.task_manager import check_running_tasks
from bot.helper.mirror_leech_utils.status_utils.streamrip_status import (
    StreamripDownloadStatus,
)
from bot.helper.telegram_helper.message_utils import send_status_message

try:
    from streamrip.client import (
        DeezerClient,
        QobuzClient,
        SoundcloudClient,
        TidalClient,
    )

    STREAMRIP_AVAILABLE = True
except ImportError:
    STREAMRIP_AVAILABLE = False


class StreamripDownloadHelper:
    """Comprehensive streamrip download helper with full CLI command support"""

    # Class-level constants to reduce memory allocation
    AUDIO_EXTENSIONS = frozenset([".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav"])
    CODEC_MAPPING = {
        "ogg": "OGG",
        "flac": "FLAC",
        "mp3": "MP3",
        "opus": "OGG",
        "alac": "ALAC",
        "vorbis": "OGG",
        "m4a": "AAC",
        "aac": "AAC",
    }

    # Supported streamrip CLI commands with descriptions
    SUPPORTED_COMMANDS = {
        "url": "Download content from URLs",
        "search": "Search for content using a specific source",
        "id": "Download an item by ID",
        "file": "Download content from URLs in a file",
        "lastfm": "Download tracks from a last.fm playlist",
        "config": "Manage configuration files",
        "database": "View and modify the downloads database",
    }

    # Quality mappings for different platforms (Bot UI Quality -> Streamrip Quality)
    # Based on streamrip library source code and platform capabilities
    QUALITY_MAPPINGS = {
        "qobuz": {
            0: 1,  # 128 kbps -> 320kbps MP3 (streamrip min quality)
            1: 1,  # 320 kbps -> 320kbps MP3
            2: 2,  # CD Quality -> 16-bit/44.1kHz FLAC
            3: 3,  # Hi-Res -> 24-bit/≤96kHz FLAC
            4: 4,  # Hi-Res+ -> 24-bit/≥96kHz FLAC
        },
        "tidal": {
            0: 0,  # 128 kbps -> 256kbps AAC
            1: 1,  # 320 kbps -> 320kbps AAC
            2: 2,  # CD Quality -> 16-bit/44.1kHz FLAC (HiFi)
            3: 3,  # Hi-Res -> 24-bit/44.1kHz MQA (Master)
        },
        "deezer": {
            0: 0,  # 128 kbps -> 128kbps MP3
            1: 1,  # 320 kbps -> 320kbps MP3
            2: 2,  # CD Quality -> 16-bit/44.1kHz FLAC
        },
        "soundcloud": {
            0: 0,  # All qualities -> MP3 (various bitrates)
            1: 0,
            2: 0,
            3: 0,
            4: 0,
        },
        "youtube": {0: 0},  # Only 0 available
    }

    # Pre-compiled regex patterns for better performance
    PLATFORM_PATTERNS = {
        "qobuz": re.compile(r"qobuz\.com", re.IGNORECASE),
        "tidal": re.compile(r"tidal\.com|listen\.tidal\.com", re.IGNORECASE),
        "deezer": re.compile(r"deezer\.com|dzr\.page\.link", re.IGNORECASE),
        "soundcloud": re.compile(r"soundcloud\.com", re.IGNORECASE),
    }

    # Common ffmpeg locations for faster lookup
    FFMPEG_LOCATIONS = (
        "/usr/bin/xtra",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/bin/ffmpeg",
    )

    # Pre-compiled regex for URL validation (avoid recompilation)
    URL_VALIDATION_PATTERN = re.compile(r"^https?://", re.IGNORECASE)

    # Common search paths for downloaded files (avoid recreation)
    SEARCH_PATH_TEMPLATES = ("downloads", ".config/streamrip/downloads", "downloads")

    __slots__ = (
        "_cached_config",
        "_cached_ffmpeg_path",
        "_cached_search_paths",
        "_client",
        "_codec",
        "_current_track",
        "_download_path",
        "_download_url",
        "_is_cancelled",
        "_is_downloading",
        "_media",
        "_platform",
        "_quality",
        "_start_time",
        "_temp_files",
        "listener",
    )

    def __init__(self, listener):
        self.listener = listener
        self._start_time = time.time()
        self._is_cancelled = False
        self._download_path = None
        self._current_track = ""
        self._platform = None
        self._is_downloading = False
        # Cache frequently accessed values for O(1) access
        self._cached_config = None
        self._cached_ffmpeg_path = None
        self._temp_files = []
        self._cached_search_paths = None  # Cache search paths to avoid recreation
        # Initialize media and client attributes to None
        self._media = None
        self._client = None

    @property
    def current_track(self):
        """Get current track being downloaded"""
        return self._current_track

    def _set_track_name_from_files(self, downloaded_files: list) -> None:
        """Set the track name from downloaded files for proper task naming"""
        try:
            # Find the first audio file
            audio_extensions = {
                ".flac",
                ".mp3",
                ".wav",
                ".m4a",
                ".aac",
                ".ogg",
                ".opus",
            }

            for file_path in downloaded_files:
                if isinstance(file_path, str | Path):
                    file_path = Path(file_path)
                    if file_path.suffix.lower() in audio_extensions:
                        # Extract track name from filename
                        filename = file_path.stem

                        # Handle common streamrip patterns:
                        # "01. Artist - Title" -> "Artist - Title"
                        # "Artist - Title" -> "Artist - Title"
                        if ". " in filename and " - " in filename:
                            # Remove track number prefix
                            parts = filename.split(". ", 1)
                            track_name = parts[1] if len(parts) > 1 else filename
                        else:
                            track_name = filename

                        # Set the track name
                        self._current_track = track_name

                        # Also update the listener's name if it's still the default
                        if (
                            not self.listener.name
                            or self.listener.name == "Streamrip Download"
                            or self.listener.name.strip() == ""
                        ):
                            self.listener.name = track_name

                        return

            # Fallback: use the first file's name
            if downloaded_files:
                first_file = Path(downloaded_files[0])
                self._current_track = first_file.stem

                # Also update the listener's name if it's still the default
                if (
                    not self.listener.name
                    or self.listener.name == "Streamrip Download"
                    or self.listener.name.strip() == ""
                ):
                    self.listener.name = self._current_track

        except Exception as e:
            LOGGER.warning(f"Failed to set track name: {e}")
            self._current_track = "Streamrip Download"

    async def download(
        self, url: str, quality: int | None = None, codec: str | None = None
    ) -> bool:
        """Download from streamrip URL"""
        if not STREAMRIP_AVAILABLE:
            LOGGER.error("Streamrip is not available")
            return False

        try:
            # Store quality, codec, and URL for CLI usage
            self._quality = quality
            self._codec = codec
            self._download_url = url
            # Parse URL to get platform and media info
            from bot.helper.mirror_leech_utils.streamrip_utils.url_parser import (
                parse_streamrip_url,
            )

            try:
                parsed = await parse_streamrip_url(url)
            except Exception as parse_error:
                LOGGER.error(f"Error during URL parsing: {parse_error}")
                raise

            if not parsed:
                LOGGER.error(f"Failed to parse streamrip URL: {url}")
                return False

            # Safely unpack the parsed result
            if not isinstance(parsed, tuple | list) or len(parsed) != 3:
                LOGGER.error(f"Invalid parsed result from URL {url}: {parsed}")
                return False

            platform, _, _ = parsed
            self._platform = platform  # Store platform for quality mapping

            # Set download path using existing DOWNLOAD_DIR pattern
            # Ensure all path components are strings to avoid path division errors
            try:
                base_dir = str(DOWNLOAD_DIR)
                listener_id = str(self.listener.mid)

                download_dir = Path(base_dir) / listener_id
                download_dir.mkdir(parents=True, exist_ok=True)
                self._download_path = download_dir

            except Exception as path_error:
                LOGGER.error(f"Failed to create download path: {path_error}")
                raise

            # Skip client initialization and media object creation for CLI method
            # This avoids the streamrip 2.1.0 path division bug

            # Initialize download state
            self._is_downloading = True
            self._current_track = f"Downloading from {platform.title()}"

            # Start download
            success = await self._perform_download()

            if success:
                return True
            LOGGER.error(f"Streamrip download failed: {url}")
            return False

        except Exception as e:
            LOGGER.error(f"Streamrip download error: {e}")
            return False

    async def _initialize_client(self, platform: str):
        """Initialize the appropriate client for the platform"""
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            config = streamrip_config.get_config()
            if not config:
                LOGGER.error("Streamrip config not available")
                return

            platform_status = streamrip_config.get_platform_status()

            if not platform_status.get(platform, False):
                LOGGER.error(f"Platform {platform} is not configured or enabled")
                return

            # Initialize the appropriate client
            if platform == "qobuz":
                self._client = QobuzClient(config)
            elif platform == "tidal":
                self._client = TidalClient(config)
            elif platform == "deezer":
                self._client = DeezerClient(config)
            elif platform == "soundcloud":
                self._client = SoundcloudClient(config)
            else:
                LOGGER.error(f"Unsupported platform: {platform}")
                return

            # Login/authenticate with proper error handling
            try:
                if hasattr(self._client, "login"):
                    await self._client.login()
            except Exception as auth_error:
                LOGGER.warning(
                    f"{platform.title()} authentication failed: {auth_error}"
                )
                return

        except Exception as e:
            LOGGER.error(f"Failed to initialize {platform} client: {e}")

    async def _create_media_object(
        self, platform: str, media_type: str, media_id: str
    ):
        """Create the appropriate media object"""
        try:
            # Use platform-specific methods to get metadata
            if platform == "qobuz":
                # Qobuz uses get_metadata for all media types
                self._media = await self._client.get_metadata(media_id, media_type)
                if not self._media:
                    LOGGER.error(f"Failed to get {media_type} metadata from Qobuz")
                    return
            elif platform == "deezer":
                # Deezer has specific methods for each media type
                if media_type == "track":
                    self._media = await self._client.get_track(media_id)
                elif media_type == "album":
                    self._media = await self._client.get_album(media_id)
                elif media_type == "playlist":
                    self._media = await self._client.get_playlist(media_id)
                elif media_type == "artist":
                    self._media = await self._client.get_artist(media_id)
                else:
                    LOGGER.error(f"Unsupported Deezer media type: {media_type}")
                    return

                if not self._media:
                    LOGGER.error(f"Failed to get {media_type} metadata from Deezer")
                    return
            elif platform == "tidal":
                # Tidal uses get_metadata similar to Qobuz
                self._media = await self._client.get_metadata(media_id, media_type)
                if not self._media:
                    LOGGER.error(f"Failed to get {media_type} metadata from Tidal")
                    return
            elif platform == "soundcloud":
                # SoundCloud uses get_metadata
                self._media = await self._client.get_metadata(media_id, media_type)
                if not self._media:
                    LOGGER.error(
                        f"Failed to get {media_type} metadata from SoundCloud"
                    )
                    return
            else:
                LOGGER.error(f"Unsupported platform: {platform}")
                return

        except Exception as e:
            LOGGER.error(f"Failed to create media object: {e}")
            return

    async def _set_quality(self, quality: int):
        """Set download quality"""
        try:
            if hasattr(self._media, "set_quality"):
                await self._media.set_quality(quality)
            elif hasattr(self._client, "set_quality"):
                await self._client.set_quality(quality)
        except Exception as e:
            LOGGER.error(f"Failed to set quality: {e}")

    async def _set_codec(self, codec: str):
        """Set output codec"""
        try:
            if hasattr(self._media, "set_codec"):
                await self._media.set_codec(codec)
            elif hasattr(self._client, "set_codec"):
                await self._client.set_codec(codec)
        except Exception as e:
            LOGGER.error(f"Failed to set codec: {e}")

    async def _update_download_path(self):
        """Update streamrip config to use our download path"""
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            # Ensure streamrip is initialized
            await streamrip_config.lazy_initialize()

            config = streamrip_config.get_config()
            if config and hasattr(config, "downloads"):
                # Set the download folder to our specific path
                config.downloads.folder = str(self._download_path)
        except Exception as e:
            LOGGER.warning(f"Failed to update streamrip download path: {e}")

    async def _perform_download(self) -> bool:
        """Perform the actual download with enhanced error handling"""
        try:
            # Due to a bug in streamrip 2.1.0 with PosixPath division operations,
            # we'll use CLI method exclusively to avoid the internal API issues
            download_success = await self._download_with_cli()

            if download_success:
                # Validate downloaded files
                downloaded_files = await self._find_downloaded_files()
                if downloaded_files:
                    # Set the track name from the first downloaded audio file
                    self._set_track_name_from_files(downloaded_files)
                    return True
                LOGGER.error("No files were downloaded")
                return False
            LOGGER.error("CLI download method failed")
            return False

        except Exception as e:
            LOGGER.error(f"Download failed: {e}")
            return False

    def _map_codec_for_streamrip(self, codec: str) -> str:
        """Map user-friendly codec names to streamrip-compatible ones with optimized lookup"""
        codec_lower = codec.lower()

        # Handle AAC/M4A codecs with FFmpeg wrapper approach (O(1) lookup)
        if codec_lower in ("m4a", "aac"):
            return "AAC"

        # Use class-level mapping for O(1) efficiency
        mapped_codec = self.CODEC_MAPPING.get(codec_lower)

        if mapped_codec is None:
            LOGGER.warning(
                f"Unknown codec '{codec}' - downloading in default format"
            )
            return None

        return mapped_codec

    async def _download_with_cli(self) -> bool:
        """Download using streamrip CLI with proper configuration"""
        try:
            import asyncio
            import os

            # Create download directory if it doesn't exist
            self._download_path.mkdir(parents=True, exist_ok=True)

            # Construct streamrip command with proper v2.1.0 syntax
            cmd = ["rip"]

            # Add global options before the command (using long form for clarity)
            if hasattr(self, "_quality") and self._quality is not None:
                cmd.extend(
                    ["--quality", str(self._quality)]
                )  # Use --quality instead of -q

            # Add codec option if specified
            if hasattr(self, "_codec") and self._codec is not None:
                # Map codec to streamrip-compatible format
                mapped_codec = self._map_codec_for_streamrip(self._codec)
                if mapped_codec is not None:
                    cmd.extend(
                        ["--codec", mapped_codec]
                    )  # Use --codec instead of -c

            # Add --no-db flag if database is disabled in bot settings OR if force download is enabled
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            force_download = getattr(self.listener, "force_download", False)
            db_enabled = streamrip_config.is_database_enabled()

            if not db_enabled or force_download:
                cmd.extend(["--no-db"])

            # Add --verbose flag for better debugging (v2.1.0 feature)
            cmd.extend(["--verbose"])

            # Add the url command and URL
            # Use the original URL passed to the download method instead of listener.url
            download_url = getattr(self, "_download_url", self.listener.url)

            # Convert URL to streamrip-compatible format if needed
            converted_url = await self._convert_url_for_streamrip(download_url)
            cmd.extend(["url", converted_url])

            # Set download directory via environment variable (may not work with all streamrip versions)
            env = os.environ.copy()
            env["STREAMRIP_DOWNLOAD_DIR"] = str(self._download_path)

            # Set FFMPEG path for streamrip to find the executable
            ffmpeg_path = self._get_ffmpeg_path()

            # Create FFmpeg wrapper for AAC encoder compatibility
            wrapper_path = await self._setup_ffmpeg_wrapper_for_aac(ffmpeg_path)

            # Set multiple environment variables that streamrip might check
            env["FFMPEG_EXECUTABLE"] = wrapper_path
            env["FFMPEG_PATH"] = wrapper_path
            env["FFMPEG"] = wrapper_path
            env["FFMPEG_BINARY"] = wrapper_path

            # Ensure the wrapper directory is in PATH
            wrapper_dir = os.path.dirname(wrapper_path)
            env["PATH"] = f"{wrapper_dir}:{env.get('PATH', '')}"

            # Check if streamrip is available
            try:
                check_process = await asyncio.create_subprocess_exec(
                    "which",
                    "rip",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _stdout, _stderr = await check_process.communicate()

                if check_process.returncode != 0:
                    LOGGER.error("Streamrip 'rip' command not found")
                    # Try alternative paths
                    import shutil

                    rip_path = shutil.which("rip")
                    if not rip_path:
                        return False
            except Exception as check_error:
                LOGGER.error(f"Error checking streamrip: {check_error}")
                return False

            # Ensure config is initialized via centralized system
            await self._ensure_streamrip_config()

            # Check FFMPEG availability
            await self._check_ffmpeg_availability()

            # Check if we have proper authentication for the URL
            auth_valid = await self._validate_authentication_for_url(download_url)

            if not auth_valid:
                LOGGER.error("No valid authentication found for this URL")
                # Send helpful message to user
                try:
                    from bot.helper.ext_utils.status_utils import send_status_message

                    await send_status_message(
                        self.listener.message,
                        "❌ **Authentication Required**\n\n"
                        "Please configure your streaming service credentials:\n"
                        "• `/botsettings` → **Streamrip** → **Credential settings**\n\n"
                        "**For Deezer URLs:** Set your Deezer ARL\n"
                        "**For Qobuz URLs:** Set email and password\n"
                        "**For Tidal URLs:** Set email and password",
                    )
                except Exception:
                    pass
                return False

            # Execute with timeout
            # Use home directory as working directory since streamrip uses its own config
            try:
                # For Heroku compatibility, ensure we have proper environment
                working_dir = str(Path.home())

                # Add additional environment variables for Heroku and asyncio stability
                env["PYTHONUNBUFFERED"] = "1"  # Ensure output is not buffered
                env["TERM"] = "xterm"  # Provide a terminal type
                env["PYTHONIOENCODING"] = "utf-8"  # Ensure proper encoding
                env["PYTHONDONTWRITEBYTECODE"] = (
                    "1"  # Prevent bytecode generation issues
                )

                # Add asyncio event loop isolation for Heroku
                env["PYTHONASYNCIODEBUG"] = "0"  # Disable asyncio debug mode
                env["PYTHONHASHSEED"] = "0"  # Ensure deterministic behavior

                # Check if we're in a Docker container
                is_docker = Path("/.dockerenv").exists() or "container" in env.get(
                    "container", ""
                )

                # Docker-specific environment adjustments
                if is_docker:
                    # Ensure proper locale for Docker
                    env["LC_ALL"] = "C.UTF-8"
                    env["LANG"] = "C.UTF-8"
                    # Disable some problematic features in Docker
                    env["STREAMRIP_NO_PROGRESS"] = "1"
                    env["STREAMRIP_NO_INTERACTIVE"] = "1"
                    # Set explicit temp directory
                    env["TMPDIR"] = "/tmp"

                # Create subprocess with enhanced isolation for asyncio stability
                # Use a separate process group to prevent event loop conflicts
                import subprocess

                # For production environments, use subprocess.run to avoid event loop issues
                try:
                    # Build comprehensive streamrip CLI command
                    streamrip_cmd = self._build_streamrip_command(converted_url)

                    LOGGER.info(
                        f"Executing streamrip: {' '.join(streamrip_cmd[:3])} [options] {streamrip_cmd[-2]} [url]"
                    )

                    # Check if config file exists before execution
                    config_path = self._get_streamrip_config_path()
                    config_exists = Path(config_path).exists()
                    if not config_exists:
                        LOGGER.error(f"Config file not found at {config_path}")
                        return False

                    # Check if download directory exists
                    download_dir_exists = self._download_path.exists()
                    if not download_dir_exists:
                        self._download_path.mkdir(parents=True, exist_ok=True)

                    import time

                    start_time = time.time()

                    # Run streamrip in a completely isolated subprocess
                    result = subprocess.run(
                        streamrip_cmd,
                        cwd=working_dir,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 minute timeout
                        input="\n",
                        check=False,  # Send newline for any prompts
                    )

                    end_time = time.time()
                    end_time - start_time

                    # Process the result
                    stdout_text = result.stdout if result.stdout else ""
                    stderr_text = result.stderr if result.stderr else ""

                    if result.returncode == 0:
                        # Check for download activity in stdout
                        # Updated indicators for streamrip 2.1.0 which uses different output format
                        download_indicators = [
                            "Downloaded",
                            "Downloading",
                            "Converting",
                            "Saved to",
                            "Track downloaded",  # Legacy indicators
                            "Tagging with",
                            "Generated conversion command",
                            "Source removed",
                            "Moved:",  # Streamrip 2.1.0 indicators
                            "api_request: endpoint=track/get",
                            "Logged in to",
                            "Login resp:",  # Authentication success indicators
                            "ffmpeg",
                            "Generated conversion command",  # Processing indicators
                        ]

                        # Find which indicators were detected
                        found_indicators = [
                            indicator
                            for indicator in download_indicators
                            if indicator in stdout_text
                        ]

                        has_download_activity = len(found_indicators) > 0

                        if has_download_activity:
                            return True
                        LOGGER.warning(
                            "No download activity detected - check credentials/availability"
                        )
                        return False
                    LOGGER.error(f"Streamrip failed with code: {result.returncode}")

                    # Handle specific error patterns
                    self._handle_streamrip_errors(stderr_text)
                    self._handle_streamrip_errors(
                        stdout_text
                    )  # Also check stdout for errors
                    return False

                except subprocess.TimeoutExpired:
                    LOGGER.error("Streamrip process timed out after 5 minutes")
                    return False
                except Exception as subprocess_error:
                    LOGGER.error(f"Subprocess execution failed: {subprocess_error}")
                    return False

            except Exception as e:
                LOGGER.error(f"Failed to execute streamrip command: {e}")
                return False

        except Exception as e:
            LOGGER.error(f"CLI download failed: {e}")
            return False

    async def _find_downloaded_files(self) -> list:
        """Find downloaded files in the download directory with optimized caching"""
        try:
            downloaded_files = []

            # Use cached search paths for O(1) access on subsequent calls
            if self._cached_search_paths is None:
                search_paths = []
                if self._download_path and self._download_path.exists():
                    search_paths.append(self._download_path)
                    parent_dir = self._download_path.parent
                    if parent_dir.exists():
                        search_paths.append(parent_dir)

                # Add common paths only if they exist (avoid unnecessary checks)
                from pathlib import Path

                common_paths = [
                    Path.home() / "StreamripDownloads",
                    Path.home() / "Downloads",
                    Path("/tmp"),
                    Path("/usr/src/app/downloads"),
                ]

                search_paths.extend(
                    p for p in common_paths if p.exists() and p not in search_paths
                )
                self._cached_search_paths = search_paths

            else:
                search_paths = self._cached_search_paths

            # Search for downloaded files
            for search_path in search_paths:
                try:
                    # Find recent audio files
                    new_files = [
                        file_path
                        for file_path in search_path.rglob("*")
                        if (
                            file_path.is_file()
                            and file_path.suffix.lower() in self.AUDIO_EXTENSIONS
                            and file_path.stat().st_mtime > self._start_time
                        )
                    ]

                    downloaded_files.extend(new_files)

                    # Early termination if we found files in primary location
                    if new_files and search_path == self._download_path:
                        break
                except Exception as search_error:
                    LOGGER.error(f"Error searching {search_path}: {search_error}")

            # Use set for deduplication (more efficient than list conversion)
            unique_files = list({f.resolve(): f for f in downloaded_files}.values())
            unique_files.sort(key=lambda x: x.stat().st_mtime)

            # Move files if needed
            if unique_files:
                return await self._move_files_to_target_folder(unique_files)
            return unique_files

        except Exception as e:
            LOGGER.error(f"Failed to find downloaded files: {e}")
            return []

    async def _move_files_to_target_folder(self, files: list) -> list:
        """Move downloaded files from streamrip default folder to our target folder"""
        try:
            import shutil

            moved_files = []

            for file_path in files:
                try:
                    # Check if file is in the default streamrip folder
                    streamrip_folder = Path.home() / "StreamripDownloads"
                    if (
                        streamrip_folder in file_path.parents
                        or file_path.parent == streamrip_folder
                    ):
                        # Preserve folder structure when moving files
                        # Get the relative path from streamrip folder to maintain album/playlist structure
                        try:
                            relative_path = file_path.relative_to(streamrip_folder)
                            target_file = self._download_path / relative_path
                        except ValueError:
                            # If relative_to fails, use the full structure from parent
                            if file_path.parent != streamrip_folder:
                                # File is in a subfolder, preserve the structure
                                relative_path = file_path.relative_to(
                                    file_path.parent.parent
                                )
                                target_file = self._download_path / relative_path
                            else:
                                # File is directly in streamrip folder
                                target_file = self._download_path / file_path.name

                        # Ensure target directory exists
                        target_file.parent.mkdir(parents=True, exist_ok=True)

                        # Move the file
                        shutil.move(str(file_path), str(target_file))
                        moved_files.append(target_file)

                    else:
                        # File is already in the right location
                        moved_files.append(file_path)

                except Exception as move_error:
                    LOGGER.error(f"Failed to move file {file_path}: {move_error}")
                    # Keep the original file in the list if move fails
                    moved_files.append(file_path)

            return moved_files

        except Exception as e:
            LOGGER.error(f"Error moving files: {e}")
            return files  # Return original files if moving fails

    async def _ensure_streamrip_config(self):
        """Ensure streamrip config exists using centralized config system"""
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                ensure_streamrip_initialized,
            )

            # Use the centralized config system
            success = await ensure_streamrip_initialized()
            if not success:
                LOGGER.error("Failed to initialize streamrip config")
                return False

            return True

        except Exception as e:
            LOGGER.error(f"Failed to ensure streamrip config: {e}")
            return False

    def _build_streamrip_command(self, url: str) -> list[str]:
        """Build comprehensive streamrip CLI command with all supported options"""
        cmd = ["rip"]

        # Global options (before command)
        cmd.extend(["--config-path", str(self._get_streamrip_config_path())])
        cmd.extend(["--folder", str(self._download_path)])

        # Quality option - map bot UI quality to streamrip quality
        bot_quality = getattr(self, "_quality", 3)
        platform = getattr(self, "_platform", "qobuz")
        streamrip_quality = self._map_quality_for_platform(bot_quality, platform)
        cmd.extend(["--quality", str(streamrip_quality)])

        # Codec option if specified
        if hasattr(self, "_codec") and self._codec:
            mapped_codec = self._map_codec_for_streamrip(self._codec)
            if mapped_codec:
                cmd.extend(["--codec", mapped_codec])

        # Database option
        if not self._is_database_enabled():
            cmd.extend(["--no-db"])

        # SSL verification (if disabled in config)
        try:
            from bot.core.config_manager import Config

            if not getattr(Config, "STREAMRIP_VERIFY_SSL", True):
                cmd.append("--no-ssl-verify")
        except Exception:
            pass

        # Verbose mode for better debugging
        cmd.append("--verbose")

        # Progress bars disabled for bot usage
        cmd.append("--no-progress")

        # Command and URL
        cmd.extend(["url", url])

        return cmd

    def _handle_streamrip_errors(self, error_output: str) -> None:
        """Handle specific streamrip error patterns with concise logging"""
        if not error_output:
            return

        error_lower = error_output.lower()

        # Authentication errors (warnings, not errors)
        if "authentication" in error_lower or "login" in error_lower:
            LOGGER.warning(
                "Authentication failed - check credentials in bot settings"
            )
        elif "enter your arl" in error_lower or "authenticationerror" in error_lower:
            LOGGER.warning(
                "Deezer authentication failed - check ARL in bot settings"
            )
        elif "qobuz" in error_lower and (
            "error" in error_lower or "failed" in error_lower
        ):
            LOGGER.warning(
                "Qobuz authentication failed - check credentials in bot settings"
            )
        elif "tidal" in error_lower and (
            "error" in error_lower or "failed" in error_lower
        ):
            LOGGER.warning(
                "Tidal authentication failed - check tokens in bot settings"
            )
        elif "soundcloud" in error_lower:
            LOGGER.warning(
                "SoundCloud authentication failed - check client ID in bot settings"
            )

        # Config errors
        elif "config" in error_lower and (
            "error" in error_lower or "loading" in error_lower
        ):
            LOGGER.error("Config error - check centralized config system")
        elif "control characters" in error_lower:
            LOGGER.error("Config corruption - check centralized config system")

        # Network/availability errors
        elif "timeout" in error_lower or "timed out" in error_lower:
            LOGGER.error("Download timed out - check network/file size")
        elif "not found" in error_lower or "404" in error_output:
            LOGGER.error("Content not found - check URL availability")
        elif "unavailable" in error_lower:
            LOGGER.error("Content unavailable - may be region-locked or removed")

        # System errors
        elif "ffmpeg" in error_lower:
            LOGGER.error("FFMPEG error - check installation")
        elif "permission" in error_lower or "denied" in error_lower:
            LOGGER.error("Permission error - check file/directory permissions")
        elif "space" in error_lower or "disk" in error_lower:
            LOGGER.error("Disk space error - check available storage")

        else:
            LOGGER.error(f"Unknown streamrip error: {error_output[:100]}...")

    def _map_quality_for_platform(self, bot_quality: int, platform: str) -> int:
        """Map bot UI quality to streamrip quality for specific platform"""
        try:
            if platform and platform in self.QUALITY_MAPPINGS:
                return self.QUALITY_MAPPINGS[platform].get(bot_quality, bot_quality)
            LOGGER.info(
                f"No mapping found for platform {platform}, using quality {bot_quality}"
            )
            return bot_quality
        except Exception as e:
            LOGGER.warning(
                f"Failed to map quality {bot_quality} for platform {platform}: {e}"
            )
            return bot_quality

    def _get_streamrip_config_path(self) -> str:
        """Get the path to the streamrip config file"""
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            return streamrip_config.get_config_path()
        except Exception:
            # Fallback to default location
            from pathlib import Path

            return str(Path.home() / ".config" / "streamrip" / "config.toml")

    def _is_database_enabled(self) -> bool:
        """Check if streamrip database is enabled"""
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            return streamrip_config.is_database_enabled()
        except Exception:
            # Default to enabled if we can't check
            return True

    def _get_ffmpeg_path(self) -> str:
        """Get the path to FFMPEG executable with caching"""
        if self._cached_ffmpeg_path:
            return self._cached_ffmpeg_path

        try:
            # Use class-level constants for better performance
            for location in self.FFMPEG_LOCATIONS:
                if os.path.exists(location):
                    self._cached_ffmpeg_path = location
                    return location
            # If not found, return default
            self._cached_ffmpeg_path = "/usr/bin/xtra"
            return self._cached_ffmpeg_path
        except Exception:
            self._cached_ffmpeg_path = "/usr/bin/xtra"
            return self._cached_ffmpeg_path

    async def _setup_ffmpeg_wrapper_for_aac(self, ffmpeg_path: str) -> str:
        """Setup FFmpeg wrapper that replaces libfdk_aac with built-in aac encoder"""
        try:
            import stat
            import tempfile

            # Create a temporary directory for the wrapper
            wrapper_dir = tempfile.mkdtemp(prefix="streamrip_ffmpeg_")
            wrapper_script = os.path.join(wrapper_dir, "ffmpeg")

            # Create wrapper script that handles multiple encoder compatibility issues
            wrapper_content = f'''#!/bin/bash
# FFmpeg wrapper for streamrip encoder compatibility
# Handles libfdk_aac → aac and OGG video stream issues

args=("$@")
replaced_aac=false
fixed_ogg=false

# Replace libfdk_aac with aac encoder
for i in "${{!args[@]}}"; do
    if [[ "${{args[i]}}" == "libfdk_aac" ]]; then
        args[i]="aac"
        replaced_aac=true
        echo "🔄 Replaced libfdk_aac with aac encoder" >&2
    fi
done

# Fix OGG conversion issues with video streams
# Check if this is an OGG conversion with video copy
if [[ "${{args[*]}}" == *".ogg"* ]] && [[ "${{args[*]}}" == *"-c:v"* ]] && [[ "${{args[*]}}" == *"copy"* ]]; then
    # Replace "-c:v copy" with "-vn" (no video) for OGG files
    for i in "${{!args[@]}}"; do
        if [[ "${{args[i]}}" == "-c:v" ]] && [[ "${{args[i+1]}}" == "copy" ]]; then
            args[i]="-vn"
            unset args[i+1]
            # Reindex array to remove gaps
            args=("${{args[@]}}")
            fixed_ogg=true
            echo "🔄 Fixed OGG conversion: replaced -c:v copy with -vn" >&2
            break
        fi
    done
fi

if [[ "$replaced_aac" == "true" ]]; then
    echo "✅ Using built-in aac encoder for AAC conversion" >&2
fi

if [[ "$fixed_ogg" == "true" ]]; then
    echo "✅ Fixed OGG conversion for video stream compatibility" >&2
fi

# Execute the actual ffmpeg (xtra) with modified arguments
exec "{ffmpeg_path}" "${{args[@]}}"
'''

            # Write the wrapper script
            with open(wrapper_script, "w") as f:
                f.write(wrapper_content)

            # Make it executable
            os.chmod(wrapper_script, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)

            # Store wrapper path for cleanup later
            if not hasattr(self, "_temp_files"):
                self._temp_files = []
            self._temp_files.append(wrapper_dir)

            return wrapper_script

        except Exception as e:
            LOGGER.error(f"Failed to create FFmpeg wrapper: {e}")
            LOGGER.info(f"Falling back to direct ffmpeg path: {ffmpeg_path}")
            return ffmpeg_path

    async def _check_ffmpeg_availability(self):
        """Check if FFMPEG is available and log status"""
        try:
            ffmpeg_path = self._get_ffmpeg_path()
            import os

            if not os.path.exists(ffmpeg_path):
                LOGGER.warning(f"FFMPEG not found at expected path: {ffmpeg_path}")
                LOGGER.warning("Audio conversion may fail if FFMPEG is required")
        except Exception as e:
            LOGGER.error(f"Error checking FFMPEG availability: {e}")

    async def _reset_streamrip_config(self):
        """Reset streamrip config using centralized system"""
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                streamrip_config,
            )

            # Use centralized config reset
            success = await streamrip_config.reset_to_default_config()
            if success:
                LOGGER.info("Config reset via centralized system")
                return True
            LOGGER.error("Failed to reset config via centralized system")
            return False

        except Exception as e:
            LOGGER.error(f"Failed to reset streamrip config: {e}")
            return False

    async def _validate_authentication_for_url(self, url: str) -> bool:
        """Validate that we have proper authentication for the given URL"""
        try:
            from bot.core.config_manager import Config

            # Parse URL to determine platform
            url_lower = url.lower()

            if "deezer.com" in url_lower or "dzr.page.link" in url_lower:
                # Deezer URL - check for ARL
                deezer_arl = Config.STREAMRIP_DEEZER_ARL or ""
                if not deezer_arl.strip():
                    LOGGER.warning(
                        "Deezer URL detected but no Deezer ARL configured"
                    )
                    return False
                return True

            if "qobuz.com" in url_lower:
                # Qobuz URL - check for email/password
                qobuz_email = Config.STREAMRIP_QOBUZ_EMAIL or ""
                qobuz_password = Config.STREAMRIP_QOBUZ_PASSWORD or ""
                if not qobuz_email.strip() or not qobuz_password.strip():
                    LOGGER.warning(
                        "Qobuz URL detected but no Qobuz credentials configured"
                    )
                    return False

                # Additional Qobuz validation
                if "@temp-mail.me" in qobuz_email.lower():
                    LOGGER.warning(
                        "Qobuz email appears to be a temporary email address - may be blocked"
                    )

                return True

            if "tidal.com" in url_lower:
                # Tidal URL - check for credentials and tokens
                tidal_email = Config.STREAMRIP_TIDAL_EMAIL or ""
                tidal_password = Config.STREAMRIP_TIDAL_PASSWORD or ""
                tidal_access_token = Config.STREAMRIP_TIDAL_ACCESS_TOKEN or ""

                # Check if we have either email/password OR access token
                has_credentials = bool(
                    tidal_email.strip() and tidal_password.strip()
                )
                has_token = bool(tidal_access_token.strip())

                if not has_credentials and not has_token:
                    LOGGER.warning(
                        "Tidal URL detected but no Tidal authentication configured"
                    )
                    return False

                if has_token:
                    return True
                if has_credentials:
                    # Additional Tidal validation (like Qobuz)
                    if "@temp-mail.me" in tidal_email.lower():
                        LOGGER.warning(
                            "Tidal email appears to be a temporary email address - may be blocked"
                        )

                    return True

            elif "soundcloud.com" in url_lower:
                # SoundCloud URL - check for client ID (same logic as Deezer)
                soundcloud_client_id = Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID or ""
                if not soundcloud_client_id.strip():
                    LOGGER.warning(
                        "SoundCloud URL detected but no client ID configured - may work for some tracks"
                    )
                    return True  # Allow SoundCloud without client ID (like Deezer allows missing ARL)
                return True

            elif "last.fm" in url_lower or "lastfm" in url_lower:
                # Last.fm playlist - requires primary source authentication

                # Check if we have at least one streaming service configured
                has_deezer = bool((Config.STREAMRIP_DEEZER_ARL or "").strip())
                has_qobuz = bool(
                    (Config.STREAMRIP_QOBUZ_EMAIL or "").strip()
                    and (Config.STREAMRIP_QOBUZ_PASSWORD or "").strip()
                )
                has_tidal = bool(
                    (Config.STREAMRIP_TIDAL_EMAIL or "").strip()
                    and (Config.STREAMRIP_TIDAL_PASSWORD or "").strip()
                )

                if not (has_deezer or has_qobuz or has_tidal):
                    LOGGER.warning(
                        "Last.fm playlist requires at least one streaming service configured"
                    )
                    return False

                return True

            elif "spotify.com" in url_lower or "open.spotify.com" in url_lower:
                # Spotify playlist - requires Last.fm integration

                # Check if we have streaming services for Last.fm fallback
                has_deezer = bool((Config.STREAMRIP_DEEZER_ARL or "").strip())
                has_qobuz = bool(
                    (Config.STREAMRIP_QOBUZ_EMAIL or "").strip()
                    and (Config.STREAMRIP_QOBUZ_PASSWORD or "").strip()
                )
                has_tidal = bool(
                    (Config.STREAMRIP_TIDAL_EMAIL or "").strip()
                    and (Config.STREAMRIP_TIDAL_PASSWORD or "").strip()
                )

                if not (has_deezer or has_qobuz or has_tidal):
                    LOGGER.warning(
                        "Spotify playlist requires streaming service credentials for Last.fm conversion"
                    )
                    return False

                return True

            elif "music.apple.com" in url_lower:
                # Apple Music playlist - requires Last.fm integration

                # Check if we have streaming services for Last.fm fallback
                has_deezer = bool((Config.STREAMRIP_DEEZER_ARL or "").strip())
                has_qobuz = bool(
                    (Config.STREAMRIP_QOBUZ_EMAIL or "").strip()
                    and (Config.STREAMRIP_QOBUZ_PASSWORD or "").strip()
                )
                has_tidal = bool(
                    (Config.STREAMRIP_TIDAL_EMAIL or "").strip()
                    and (Config.STREAMRIP_TIDAL_PASSWORD or "").strip()
                )

                if not (has_deezer or has_qobuz or has_tidal):
                    LOGGER.warning(
                        "Apple Music playlist requires streaming service credentials for Last.fm conversion"
                    )
                    return False

                return True

            else:
                # Unknown platform - allow download attempt (like Deezer logic)
                return True

        except Exception as e:
            LOGGER.error(f"Error validating authentication: {e}")
            # Don't block download on validation errors
            return True

    async def _convert_url_for_streamrip(self, url: str) -> str:
        """Convert URL to streamrip-compatible format if needed"""
        try:
            import re  # Import re module at the beginning

            url_lower = url.lower()

            # Handle Tidal mix URLs - convert to listen.tidal.com format
            if "tidal.com/browse/mix/" in url_lower:
                # Extract mix ID from browse URL
                mix_match = re.search(
                    r"tidal\.com/browse/mix/([^/?]+)", url, re.IGNORECASE
                )
                if mix_match:
                    mix_id = mix_match.group(1)
                    # Try multiple URL formats for better compatibility
                    return f"https://listen.tidal.com/playlist/{mix_id}"
                return url

            # Handle other Tidal browse URLs - convert to listen.tidal.com format
            if "tidal.com/browse/" in url_lower:
                # Convert browse URLs to listen URLs for better compatibility
                converted_url = url.replace("tidal.com/browse/", "listen.tidal.com/")
                if converted_url != url:
                    return converted_url

            # Handle Qobuz URLs - normalize to streamrip-compatible format
            elif "qobuz.com" in url_lower:
                converted_url = url

                # Remove region prefix for better compatibility
                if re.search(r"/[a-z]{2}-[a-z]{2}/", url, re.IGNORECASE):
                    converted_url = re.sub(
                        r"/[a-z]{2}-[a-z]{2}/",
                        "/",
                        converted_url,
                        flags=re.IGNORECASE,
                    )

                # Convert /interpreter/ to /artist/ for streamrip compatibility
                if "/interpreter/" in converted_url.lower():
                    converted_url = re.sub(
                        r"/interpreter/",
                        "/artist/",
                        converted_url,
                        flags=re.IGNORECASE,
                    )

                if converted_url != url:
                    return converted_url

            # Handle Deezer page.link URLs - these should be resolved by streamrip
            elif "dzr.page.link" in url_lower:
                return url

            # Handle SoundCloud URLs - ensure proper format
            elif "soundcloud.com" in url_lower:
                # SoundCloud URLs should work as-is
                return url

            # For all other URLs, return as-is
            return url

        except Exception as e:
            LOGGER.warning(f"Error converting URL: {e}")
            return url

    def cancel_download(self):
        """Cancel the download"""
        self._is_cancelled = True

        # Cancel the media download if possible
        if self._media and hasattr(self._media, "cancel"):
            self._media.cancel()

        # Clean up temporary files
        self._cleanup_temp_files()

    def _cleanup_temp_files(self):
        """Clean up temporary files created during download"""
        try:
            if hasattr(self, "_temp_files"):
                import shutil

                for temp_path in self._temp_files:
                    try:
                        if os.path.exists(temp_path):
                            if os.path.isdir(temp_path):
                                shutil.rmtree(temp_path)
                            else:
                                os.unlink(temp_path)
                    except Exception as e:
                        LOGGER.error(f"Error cleaning temp file {temp_path}: {e}")
                self._temp_files.clear()
        except Exception as e:
            LOGGER.error(f"Error during temp file cleanup: {e}")


async def add_streamrip_download(
    listener,
    url: str,
    quality: int | None = None,
    codec: str | None = None,
    force: bool = False,
):
    """Add streamrip download to queue"""
    if not STREAMRIP_AVAILABLE:
        await send_status_message(listener.message, "❌ Streamrip is not available!")
        return

    # Check if streamrip is enabled
    if not Config.STREAMRIP_ENABLED:
        await send_status_message(
            listener.message, "❌ Streamrip downloads are disabled!"
        )
        return

    # Parse URL to validate and get platform/media_type info
    from bot.helper.mirror_leech_utils.streamrip_utils.url_parser import (
        is_streamrip_url,
        parse_streamrip_url,
    )

    if not await is_streamrip_url(url):
        await send_status_message(listener.message, "❌ Invalid streamrip URL!")
        return

    # Set platform and media_type attributes if not already set
    if not hasattr(listener, "platform") or not hasattr(listener, "media_type"):
        try:
            parsed = await parse_streamrip_url(url)
            if parsed and isinstance(parsed, tuple | list) and len(parsed) == 3:
                platform, media_type, _ = parsed
                listener.platform = platform
                listener.media_type = media_type
            else:
                # Fallback values if parsing fails or returns invalid result
                listener.platform = "Unknown"
                listener.media_type = "Unknown"
        except Exception as e:
            LOGGER.error(f"Failed to parse URL for platform info: {e}")
            # Set fallback values
            listener.platform = "Unknown"
            listener.media_type = "Unknown"

    # Create download helper
    download_helper = StreamripDownloadHelper(listener)

    # Set streamrip-specific attributes on the listener
    listener.url = url
    listener.quality = quality
    listener.codec = codec
    listener.force_download = force

    # Check running tasks and queue management
    add_to_queue, event = await check_running_tasks(listener)

    # Add to task dict with proper status
    async with task_dict_lock:
        task_dict[listener.mid] = StreamripDownloadStatus(
            listener, download_helper, queued=add_to_queue
        )

    # Handle queuing
    if add_to_queue:
        await send_status_message(listener.message, "⏳ Added to download queue!")
        await event.wait()
        if listener.is_cancelled:
            return

    # Update task dict for active download
    async with task_dict_lock:
        task_dict[listener.mid] = StreamripDownloadStatus(
            listener, download_helper, queued=False
        )

    # Send status message automatically when download starts (instead of initial download start message)
    await send_status_message(listener.message)

    try:
        download_success = await download_helper.download(url, quality, codec)

        # If download was successful, trigger the upload process
        if download_success:
            # Initialize media tools settings before upload (only for specialized listeners)
            if hasattr(listener, "initialize_media_tools"):
                await listener.initialize_media_tools()
            await listener.on_download_complete()
        else:
            LOGGER.error("Streamrip download failed")
            await listener.on_download_error("Download failed")
    except Exception as e:
        LOGGER.error(f"Exception in streamrip download: {e}")
        import traceback

        LOGGER.error(f"Traceback: {traceback.format_exc()}")
        await listener.on_download_error(f"Download error: {e}")
    finally:
        # Clean up any remaining aiohttp sessions
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.search_handler import (
                cleanup_all_streamrip_sessions,
            )

            await cleanup_all_streamrip_sessions()

            # Additional cleanup for any remaining sessions
            import gc

            import aiohttp

            # Force garbage collection to find unclosed sessions
            gc.collect()

            # Close any remaining aiohttp sessions
            for obj in gc.get_objects():
                if isinstance(obj, aiohttp.ClientSession | aiohttp.TCPConnector):
                    try:
                        if not obj.closed:
                            await obj.close()
                    except Exception:
                        pass

            # Final garbage collection
            gc.collect()

        except Exception as cleanup_error:
            # Only log if it's not a common cleanup error
            if "session" not in str(cleanup_error).lower():
                LOGGER.warning(f"Session cleanup error: {cleanup_error}")
