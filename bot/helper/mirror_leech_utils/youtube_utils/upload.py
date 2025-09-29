import os
import pickle
import random
import time
from logging import getLogger
from os import path as ospath

import httplib2
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# Removed tenacity imports as we're using custom retry logic
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import SetInterval, async_to_sync
from bot.helper.ext_utils.files_utils import get_mime_type_sync as get_mime_type

LOGGER = getLogger(__name__)

# YouTube API settings
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# Retriable HTTP status codes
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# Retriable exceptions
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError)

# Valid privacy statuses
VALID_PRIVACY_STATUSES = ("private", "public", "unlisted")

# Maximum number of times to retry before giving up
MAX_RETRIES = 3


class YouTubeUpload:
    def __init__(self, listener, path):
        self.listener = listener
        self._updater = None
        self._path = path
        self._is_errored = False
        self.is_uploading = True
        self._uploaded_bytes = 0
        self._total_bytes = 0
        self._start_time = time.time()
        self._last_update_time = time.time()
        self._speed = 0
        self._eta = "-"

        # YouTube service
        self.youtube = None

        # Upload settings with user priority over config
        self.privacy_status = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_PRIVACY",
            getattr(Config, "YOUTUBE_UPLOAD_DEFAULT_PRIVACY", "unlisted"),
        )
        self.category_id = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_CATEGORY",
            getattr(Config, "YOUTUBE_UPLOAD_DEFAULT_CATEGORY", "22"),
        )
        self.default_tags = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_TAGS",
            getattr(Config, "YOUTUBE_UPLOAD_DEFAULT_TAGS", ""),
        )
        self.default_description = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
            getattr(
                Config,
                "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
                "Uploaded via AimLeechBot",
            ),
        )
        self.default_title_template = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_TITLE",
            getattr(Config, "YOUTUBE_UPLOAD_DEFAULT_TITLE", ""),
        )

        # Custom title from command line (set by task_listener if provided)
        self.custom_title = None

        # Advanced settings
        self.default_language = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_LANGUAGE",
            getattr(Config, "YOUTUBE_UPLOAD_DEFAULT_LANGUAGE", "en"),
        )
        self.license_type = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_LICENSE",
            getattr(Config, "YOUTUBE_UPLOAD_DEFAULT_LICENSE", "youtube"),
        )
        self.embeddable = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_EMBEDDABLE",
            getattr(Config, "YOUTUBE_UPLOAD_EMBEDDABLE", True),
        )
        self.public_stats_viewable = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
            getattr(Config, "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE", True),
        )
        self.made_for_kids = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_MADE_FOR_KIDS",
            getattr(Config, "YOUTUBE_UPLOAD_MADE_FOR_KIDS", False),
        )
        self.notify_subscribers = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
            getattr(Config, "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS", True),
        )
        self.location_description = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_LOCATION_DESCRIPTION",
            getattr(Config, "YOUTUBE_UPLOAD_LOCATION_DESCRIPTION", ""),
        )
        self.recording_date = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_RECORDING_DATE",
            getattr(Config, "YOUTUBE_UPLOAD_RECORDING_DATE", ""),
        )
        self.auto_levels = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_AUTO_LEVELS",
            getattr(Config, "YOUTUBE_UPLOAD_AUTO_LEVELS", False),
        )
        self.stabilize = self.listener.user_dict.get(
            "YOUTUBE_UPLOAD_STABILIZE",
            getattr(Config, "YOUTUBE_UPLOAD_STABILIZE", False),
        )

        # Performance settings (hardcoded for optimal performance)
        self.chunk_size = 8388608  # 8MB chunks - optimal for most connections
        self.retry_count = (
            3  # 3 retry attempts - good balance of reliability and speed
        )
        self.timeout = 3600  # 1 hour timeout - sufficient for most uploads

    def authenticate(self):
        """Authenticate with YouTube API"""
        credentials = None
        token_path = f"tokens/{self.listener.user_id}_youtube.pickle"

        # Check USER_TOKENS setting to determine token priority
        user_tokens_enabled = self.listener.user_dict.get("USER_TOKENS", False)

        if user_tokens_enabled:
            # When USER_TOKENS is enabled, only use user's personal token
            if ospath.exists(token_path):
                try:
                    with open(token_path, "rb") as token:
                        credentials = pickle.load(token)
                except (EOFError, pickle.UnpicklingError, pickle.PickleError) as e:
                    raise FileNotFoundError(
                        f"❌ YouTube Token Corrupted!\n\n"
                        f"The user's YouTube token file is corrupted or incomplete.\n"
                        f"Token path: {token_path}\n\n"
                        f"🔧 How to fix:\n"
                        f"1. Go to User Settings → YouTube API → 🔑 YouTube Token\n"
                        f"2. Remove the corrupted token\n"
                        f"3. Upload a new valid YouTube token pickle file\n\n"
                        f"📋 Technical details: {e}"
                    ) from e
            else:
                raise FileNotFoundError(
                    f"USER_TOKENS is enabled but user's YouTube token not found at {token_path}. "
                    "Please upload your YouTube token pickle file through user settings."
                )
        elif ospath.exists(token_path):
            # When USER_TOKENS is disabled, check user token first
            try:
                with open(token_path, "rb") as token:
                    credentials = pickle.load(token)
            except (EOFError, pickle.UnpicklingError, pickle.PickleError) as e:
                LOGGER.warning(
                    f"User's YouTube token is corrupted: {e}. Trying owner's token..."
                )
                # Try owner's token as fallback
                if ospath.exists("youtube_token.pickle"):
                    try:
                        with open("youtube_token.pickle", "rb") as token:
                            credentials = pickle.load(token)
                    except (
                        EOFError,
                        pickle.UnpicklingError,
                        pickle.PickleError,
                    ) as owner_e:
                        raise FileNotFoundError(
                            f"❌ All YouTube Tokens Corrupted!\n\n"
                            f"Both user and owner YouTube tokens are corrupted.\n\n"
                            f"🔧 How to fix:\n"
                            f"1. For user token: Go to User Settings → YouTube API → 🔑 YouTube Token\n"
                            f"2. For owner token: Go to Bot Settings → 🔒 Private Files\n"
                            f"3. Remove corrupted tokens and upload new valid ones\n\n"
                            f"📋 Technical details:\n"
                            f"• User token error: {e}\n"
                            f"• Owner token error: {owner_e}"
                        ) from owner_e
                else:
                    raise FileNotFoundError(
                        f"❌ YouTube Token Corrupted!\n\n"
                        f"The user's YouTube token is corrupted and no owner token is available.\n\n"
                        f"🔧 How to fix:\n"
                        f"1. Go to User Settings → YouTube API → 🔑 YouTube Token\n"
                        f"2. Remove the corrupted token\n"
                        f"3. Upload a new valid YouTube token pickle file\n"
                        f"OR\n"
                        f"4. Ask the bot owner to upload a global YouTube token\n\n"
                        f"📋 Technical details: {e}"
                    ) from e
        elif ospath.exists("youtube_token.pickle"):
            # Fallback to default token
            try:
                with open("youtube_token.pickle", "rb") as token:
                    credentials = pickle.load(token)
            except (EOFError, pickle.UnpicklingError, pickle.PickleError) as e:
                raise FileNotFoundError(
                    f"❌ Owner's YouTube Token Corrupted!\n\n"
                    f"The owner's YouTube token file is corrupted or incomplete.\n\n"
                    f"🔧 How to fix (for bot owner):\n"
                    f"1. Go to Bot Settings → 🔒 Private Files\n"
                    f"2. Upload a new valid youtube_token.pickle file\n"
                    f"OR\n"
                    f"3. Users can upload their personal tokens via User Settings\n\n"
                    f"📋 Technical details: {e}"
                ) from e
        else:
            raise FileNotFoundError(
                "No YouTube token found. Please add youtube_token.pickle to the bot directory "
                "or upload your personal YouTube token through user settings."
            )

        # If there are no (valid) credentials available, let the user log in
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except Exception as refresh_error:
                    LOGGER.error(
                        f"Failed to refresh YouTube credentials: {refresh_error}"
                    )
                    if user_tokens_enabled:
                        raise FileNotFoundError(
                            f"USER_TOKENS is enabled but user's YouTube token is expired and cannot be refreshed at {token_path}. "
                            f"Refresh error: {refresh_error}. Please upload a new valid YouTube token pickle file through user settings."
                        ) from refresh_error

                    raise FileNotFoundError(
                        f"YouTube token is expired and cannot be refreshed. Refresh error: {refresh_error}. "
                        "Please regenerate the YouTube token or check your credentials.json file."
                    ) from refresh_error
            else:
                # Don't allow automatic token creation when USER_TOKENS is enabled
                if user_tokens_enabled:
                    raise FileNotFoundError(
                        f"USER_TOKENS is enabled but user's YouTube token is invalid or expired at {token_path}. "
                        "Please upload a valid YouTube token pickle file through user settings."
                    )

                if not ospath.exists("credentials.json"):
                    raise FileNotFoundError(
                        "credentials.json not found. Please add your YouTube API credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", YOUTUBE_UPLOAD_SCOPE
                )
                credentials = flow.run_local_server(port=0, open_browser=False)

            # Save the credentials for the next run
            # When USER_TOKENS is enabled, save to user's token path
            # When USER_TOKENS is disabled, save to the appropriate path based on which token was used
            save_path = (
                token_path
                if user_tokens_enabled or ospath.exists(token_path)
                else "youtube_token.pickle"
            )
            with open(save_path, "wb") as token:
                pickle.dump(credentials, token)

        youtube_service = build(
            YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials
        )

        # Verify that the account has a YouTube channel
        try:
            # Try to get channel information
            channels_response = (
                youtube_service.channels()
                .list(part="snippet,contentDetails", mine=True)
                .execute()
            )

            if not channels_response.get("items"):
                raise Exception(
                    "❌ No YouTube Channel Found!\n\n"
                    "The Google account associated with this token doesn't have a YouTube channel.\n\n"
                    "🔧 How to fix:\n"
                    "1. Go to https://www.youtube.com\n"
                    "2. Sign in with the same Google account used for the token\n"
                    "3. Create a YouTube channel (click your profile → 'Create a channel')\n"
                    "4. Make sure the channel is fully set up\n"
                    "5. Try uploading again\n\n"
                    "💡 Note: Every Google account needs a YouTube channel to upload videos."
                )

            # Log channel info for debugging (only once per session)
            channel_info = channels_response["items"][0]["snippet"]
            LOGGER.debug(
                f"YouTube channel verified: {channel_info.get('title', 'Unknown')} (ID: {channels_response['items'][0]['id']})"
            )

        except HttpError as e:
            if e.resp.status == 401:
                raise Exception(
                    "❌ YouTube API Access Denied!\n\n"
                    "The token doesn't have permission to access YouTube channels.\n\n"
                    "🔧 How to fix:\n"
                    "1. Regenerate your YouTube token with proper scopes\n"
                    "2. Make sure the token includes 'https://www.googleapis.com/auth/youtube.upload' scope\n"
                    "3. Upload the new token through user settings\n\n"
                    f"📋 Technical details: {e}"
                ) from e
            raise Exception(f"❌ Failed to verify YouTube channel: {e}") from e

        return youtube_service

    async def progress(self):
        """Update upload progress"""
        if self._total_bytes > 0:
            percentage = (self._uploaded_bytes / self._total_bytes) * 100
            current_time = time.time()
            elapsed_time = current_time - self._start_time

            if elapsed_time > 0:
                self._speed = self._uploaded_bytes / elapsed_time
                if self._speed > 0:
                    remaining_bytes = self._total_bytes - self._uploaded_bytes
                    self._eta = remaining_bytes / self._speed
                else:
                    self._eta = "-"

            # Only log progress at significant milestones to reduce log spam
            if (
                percentage >= 100
                or percentage % 25 == 0
                or (percentage % 10 == 0 and percentage <= 20)
            ):
                LOGGER.info(
                    f"YouTube Upload Progress: {percentage:.1f}% - {self._uploaded_bytes}/{self._total_bytes} bytes"
                )

    def update_interval(self):
        """Update interval for progress reporting"""
        return 3

    def _upload_video(
        self, video_path, title, description, tags, category_id, privacy_status
    ):
        """Upload video to YouTube with retry logic"""
        if not ospath.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Get file size
        self._total_bytes = ospath.getsize(video_path)

        # Prepare video metadata with all advanced settings
        snippet = {
            "title": title[:100],  # YouTube limit is 100 characters
            "description": description[:5000],  # YouTube limit is 5000 characters
            "tags": tags.split(",") if tags else [],
            "categoryId": category_id,
            "defaultLanguage": self.default_language,
        }

        # Add location description if provided
        if self.location_description:
            snippet["locationDescription"] = self.location_description[
                :100
            ]  # YouTube limit

        # Add recording date if provided
        if self.recording_date:
            try:
                # Validate date format (YYYY-MM-DD)
                from datetime import datetime

                datetime.strptime(self.recording_date, "%Y-%m-%d")
                snippet["recordingDate"] = self.recording_date
            except ValueError:
                LOGGER.warning(
                    f"Invalid recording date format: {self.recording_date}. Expected YYYY-MM-DD"
                )

        status = {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": self.made_for_kids,
            "embeddable": self.embeddable,
            "publicStatsViewable": self.public_stats_viewable,
            "license": self.license_type,
        }

        # Add notify subscribers setting if not made for kids
        if not self.made_for_kids:
            status["publishAt"] = None  # Publish immediately
            # Note: notifySubscribers is handled during upload, not in metadata

        body = {
            "snippet": snippet,
            "status": status,
        }

        # Add processing details for auto-enhancement
        if self.auto_levels or self.stabilize:
            body["processingDetails"] = {}
            if self.auto_levels:
                body["processingDetails"]["autoLevels"] = True
            if self.stabilize:
                body["processingDetails"]["stabilize"] = True

        # Create media upload object with performance settings
        media = MediaFileUpload(
            video_path,
            chunksize=self.chunk_size,
            resumable=True,
            mimetype=get_mime_type(video_path),
        )

        # Call the API's videos.insert method to create and upload the video
        # Include notifySubscribers parameter if applicable
        insert_params = {
            "part": ",".join(body.keys()),
            "body": body,
            "media_body": media,
        }

        # Add notify subscribers parameter (only works for non-kids content)
        if not self.made_for_kids:
            insert_params["notifySubscribers"] = self.notify_subscribers

        insert_request = self.youtube.videos().insert(**insert_params)

        return self._resumable_upload(insert_request)

    def _resumable_upload(self, insert_request):
        """Execute the upload with resumable upload protocol"""
        response = None
        error = None
        retry_count = 0

        while response is None:
            try:
                status, response = insert_request.next_chunk()
                if status:
                    self._uploaded_bytes = status.resumable_progress
                    self.progress()

                    # Check if upload was cancelled
                    if self.listener.is_cancelled:
                        LOGGER.info("YouTube upload cancelled by user")
                        return None

            except HttpError as e:
                if e.resp.status in RETRIABLE_STATUS_CODES:
                    error = f"A retriable HTTP error {e.resp.status} occurred:\n{e.content}"
                elif e.resp.status == 401:
                    # Handle specific 401 errors with detailed guidance
                    error_details = str(e)
                    if "youtubeSignupRequired" in error_details:
                        raise Exception(
                            "❌ YouTube Channel Required!\n\n"
                            "The Google account associated with this token doesn't have a YouTube channel.\n\n"
                            "🔧 How to fix:\n"
                            "1. Go to https://www.youtube.com\n"
                            "2. Sign in with the same Google account used for the token\n"
                            "3. Create a YouTube channel (click your profile → 'Create a channel')\n"
                            "4. Make sure the channel is fully set up\n"
                            "5. Try uploading again\n\n"
                            "💡 Note: Every Google account needs a YouTube channel to upload videos."
                        ) from e
                    if "Unauthorized" in error_details:
                        raise Exception(
                            "❌ YouTube API Authorization Failed!\n\n"
                            "The token is invalid or doesn't have YouTube upload permissions.\n\n"
                            "🔧 How to fix:\n"
                            "1. Regenerate your YouTube token with proper scopes\n"
                            "2. Make sure the token includes 'https://www.googleapis.com/auth/youtube.upload' scope\n"
                            "3. Upload the new token through user settings\n\n"
                            f"📋 Technical details: {error_details}"
                        ) from e
                    raise Exception(
                        f"❌ YouTube API Authentication Error: {error_details}"
                    ) from e
                else:
                    raise e
            except RETRIABLE_EXCEPTIONS as e:
                error = f"A retriable error occurred: {e}"

            if error is not None:
                LOGGER.warning(error)
                retry_count += 1
                if retry_count > self.retry_count:
                    raise Exception(
                        f"Maximum retry attempts exceeded ({self.retry_count})"
                    )

                max_delay = 2**retry_count
                delay = random.random() * max_delay
                LOGGER.info(f"Sleeping {delay} seconds and then retrying...")
                time.sleep(delay)

        return response

    def upload(self):
        """Main upload method"""
        try:
            # Pre-validate files before authentication
            if ospath.isfile(self._path):
                if not self._is_video_file(self._path):
                    file_ext = ospath.splitext(self._path)[1].lower()
                    raise Exception(
                        f"❌ YouTube Upload Error: Unsupported File Type\n\n"
                        f"File: {ospath.basename(self._path)}\n"
                        f"Extension: {file_ext or 'No extension'}\n\n"
                        f"🎬 Supported video formats:\n"
                        f"• MP4, AVI, MKV, MOV, WMV\n"
                        f"• FLV, WebM, M4V, 3GP, OGV\n\n"
                        f"💡 YouTube only accepts video files. Please convert your file to a supported video format."
                    )
            else:
                # Check if directory contains any video files
                video_files = []
                for root, _dirs, files in os.walk(self._path):
                    for file in files:
                        file_path = ospath.join(root, file)
                        if self._is_video_file(file_path):
                            video_files.append(file)

                if not video_files:
                    # List all files in directory for user reference
                    all_files = []
                    for root, _dirs, files in os.walk(self._path):
                        for file in files:
                            all_files.append(file)

                    files_list = "\n".join(
                        [f"• {file}" for file in all_files[:10]]
                    )  # Show first 10 files
                    if len(all_files) > 10:
                        files_list += f"\n... and {len(all_files) - 10} more files"

                    raise Exception(
                        f"❌ YouTube Upload Error: No Video Files Found\n\n"
                        f"Directory: {ospath.basename(self._path)}\n"
                        f"Total files: {len(all_files)}\n\n"
                        f"📁 Files found:\n{files_list}\n\n"
                        f"🎬 Supported video formats:\n"
                        f"• MP4, AVI, MKV, MOV, WMV\n"
                        f"• FLV, WebM, M4V, 3GP, OGV\n\n"
                        f"💡 YouTube only accepts video files. Please ensure your directory contains at least one video file."
                    )

            # Authenticate with YouTube API
            self.youtube = self.authenticate()

            # Start progress updater
            self._updater = SetInterval(self.update_interval, self.progress)

            LOGGER.info(f"Starting YouTube upload: {ospath.basename(self._path)}")

            if ospath.isfile(self._path):
                # Single file upload
                result = self._upload_single_file()
            else:
                # Directory upload - upload all video files
                result = self._upload_directory()

            if result and not self.listener.is_cancelled:
                LOGGER.info(
                    f"Successfully uploaded to YouTube: {ospath.basename(self._path)}"
                )
                # Call the upload completion callback
                async_to_sync(
                    self.listener.on_upload_complete,
                    result,  # link (YouTube result)
                    1 if isinstance(result, dict) else len(result),  # files count
                    0,  # folders count
                    "YouTube Video"
                    if isinstance(result, dict)
                    else "YouTube Videos",  # mime_type
                )
                return result

            # Handle cancellation vs failure
            if self.listener.is_cancelled:
                raise Exception("❌ YouTube upload was cancelled by user")
            raise Exception(
                "❌ YouTube upload failed: No videos were successfully uploaded"
            )

        except Exception as e:
            self._is_errored = True
            LOGGER.error(f"YouTube upload error: {e!s}")
            async_to_sync(self.listener.on_upload_error, str(e))
            raise e
        finally:
            if self._updater:
                self._updater.cancel()
            self.is_uploading = False

    def _upload_single_file(self):
        """Upload a single video file"""
        # File validation is done in main upload() method
        # Extract metadata from filename or use defaults
        title = self._generate_title(self._path, self.custom_title)
        description = self.default_description
        tags = self.default_tags

        # Upload the video
        response = self._upload_video(
            self._path,
            title,
            description,
            tags,
            self.category_id,
            self.privacy_status,
        )

        if response:
            video_id = response["id"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            return {
                "video_id": video_id,
                "video_url": video_url,
                "title": title,
                "privacy_status": self.privacy_status,
            }

        return None

    def _upload_directory(self):
        """Upload all video files in a directory"""
        uploaded_videos = []
        failed_uploads = []
        total_video_files = 0

        for root, _dirs, files in os.walk(self._path):
            for file in files:
                file_path = ospath.join(root, file)
                if self._is_video_file(file_path):
                    total_video_files += 1
                    try:
                        # Extract metadata
                        title = self._generate_title(file_path, self.custom_title)
                        description = self.default_description
                        tags = self.default_tags

                        # Upload the video
                        response = self._upload_video(
                            file_path,
                            title,
                            description,
                            tags,
                            self.category_id,
                            self.privacy_status,
                        )

                        if response:
                            video_id = response["id"]
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                            uploaded_videos.append(
                                {
                                    "video_id": video_id,
                                    "video_url": video_url,
                                    "title": title,
                                    "file_path": file_path,
                                    "privacy_status": self.privacy_status,
                                }
                            )
                            LOGGER.info(
                                f"Successfully uploaded: {ospath.basename(file_path)}"
                            )
                        else:
                            failed_uploads.append(ospath.basename(file_path))
                            LOGGER.error(
                                f"Upload returned no response for: {ospath.basename(file_path)}"
                            )

                    except Exception as e:
                        failed_uploads.append(ospath.basename(file_path))
                        LOGGER.error(
                            f"Failed to upload {ospath.basename(file_path)}: {e!s}"
                        )
                        continue

        # Log summary
        if uploaded_videos:
            LOGGER.info(
                f"Directory upload summary: {len(uploaded_videos)}/{total_video_files} videos uploaded successfully"
            )

        if failed_uploads:
            LOGGER.warning(f"Failed uploads: {', '.join(failed_uploads)}")

        return uploaded_videos if uploaded_videos else None

    def _is_video_file(self, file_path):
        """Check if file is a supported video format"""
        # YouTube supported video formats
        video_extensions = {
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
            ".3gp",
            ".ogv",
            ".mpg",
            ".mpeg",
            ".m2v",
            ".m4p",
            ".mp2",
            ".mpe",
            ".mpv",
            ".m2p",
            ".svi",
            ".3g2",
            ".mxf",
            ".roq",
            ".nsv",
            ".f4v",
            ".f4p",
            ".f4a",
            ".f4b",
            ".ts",
            ".mts",
            ".m2ts",
        }

        if not ospath.exists(file_path):
            return False

        _, ext = ospath.splitext(file_path.lower())

        # Check extension first
        if ext not in video_extensions:
            return False

        # Additional validation: check if file is not empty
        try:
            file_size = ospath.getsize(file_path)
            if file_size == 0:
                LOGGER.warning(f"Skipping empty file: {ospath.basename(file_path)}")
                return False
        except OSError:
            LOGGER.warning(f"Cannot access file: {ospath.basename(file_path)}")
            return False

        return True

    def _generate_title(self, file_path, custom_title=None):
        """Generate title using custom template or filename"""
        # If custom title is provided via command line, use it directly
        if custom_title:
            title = custom_title.strip()
            if len(title) > 100:
                title = title[:97] + "..."
            return title or "Untitled Video"

        # Get filename without extension for template variables
        filename = ospath.splitext(ospath.basename(file_path))[0]

        # Clean up the filename to make it a good title
        clean_filename = filename.replace("_", " ").replace("-", " ")
        clean_filename = " ".join(
            word.capitalize() for word in clean_filename.split()
        )

        # If no template is set, use cleaned filename
        if not self.default_title_template:
            title = clean_filename
        else:
            # Apply template with variables
            title = self._apply_title_template(
                self.default_title_template, file_path, clean_filename
            )

        # Ensure title is within YouTube's limits (100 characters)
        if len(title) > 100:
            title = title[:97] + "..."

        return title or "Untitled Video"

    def _apply_title_template(self, template, file_path, clean_filename):
        """Apply title template with variable substitution"""
        try:
            from datetime import datetime

            # Get file size
            file_size = ospath.getsize(file_path)

            # Format file size
            def format_size(size_bytes):
                if size_bytes == 0:
                    return "0 B"
                size_names = ["B", "KB", "MB", "GB", "TB"]
                import math

                i = math.floor(math.log(size_bytes, 1024))
                p = math.pow(1024, i)
                s = round(size_bytes / p, 2)
                return f"{s} {size_names[i]}"

            # Get current date and time
            now = datetime.now()

            # Template variables
            variables = {
                "filename": clean_filename,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "size": format_size(file_size),
            }

            # Apply template
            return template.format(**variables)

        except Exception as e:
            LOGGER.warning(f"Failed to apply title template '{template}': {e}")
            # Fallback to cleaned filename
            return clean_filename

    def _extract_title_from_path(self, file_path):
        """Extract title from file path (legacy method for compatibility)"""
        return self._generate_title(file_path)

    def cancel(self):
        """Cancel the upload"""
        self.listener.is_cancelled = True
        if self._updater:
            self._updater.cancel()
        self.is_uploading = False
