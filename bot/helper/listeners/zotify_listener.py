import time

from bot import LOGGER
from bot.helper.listeners.task_listener import TaskListener


class ZotifyListener(TaskListener):
    """Zotify download listener that integrates with TaskListener"""

    def __init__(
        self, message, is_leech=False, tag=None, user_dict=None, screenshot=False
    ):
        # Set required attributes BEFORE calling super().__init__()
        self.message = message

        # Initialize TaskListener which handles all the standard setup
        super().__init__()

        # IMPORTANT: Set is_leech AFTER super().__init__() because TaskConfig.__init__()
        # sets self.is_leech = False by default, overriding our value
        self.is_leech = is_leech

        # Set tag for user mention in completion messages
        if tag:
            self.tag = tag
        # Set tag based on user information (same logic as TaskConfig.get_tag)
        elif self.user:
            if username := getattr(self.user, "username", None):
                self.tag = f"@{username}"
            elif hasattr(self.user, "mention"):
                self.tag = self.user.mention
            else:
                self.tag = getattr(
                    self.user,
                    "title",
                    f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>",
                )
        else:
            self.tag = f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>"

        # Zotify-specific attributes
        self.tool = "zotify"
        self.url = ""
        self._start_time = time.time()
        self._last_update = 0
        self._update_interval = 5  # Update every 5 seconds

        # Override name if not set
        if not self.name:
            self.name = "Zotify Download"

    async def initialize_media_tools(self):
        """Initialize media tools settings by calling before_start()"""
        try:
            await self.before_start()
        except Exception as e:
            # Check if this is a database connection error
            if "AsyncMongoClient" in str(e) or "Cannot use" in str(e):
                LOGGER.warning(
                    f"Database connection issue during media tools initialization for ZotifyListener: {e}. Using default values."
                )
            else:
                LOGGER.error(
                    f"Error initializing media tools for ZotifyListener: {e}"
                )
            # Set default values to prevent AttributeError
            self.compression_enabled = False
            self.extract_enabled = False
            self.merge_enabled = False
            self.trim_enabled = False
            self.add_enabled = False
            self.watermark_enabled = False

    def set_download_info(self, url: str):
        """Set download information"""
        self.url = url

    async def on_download_complete(self):
        """Override to fix folder structure and use music-specific upload flow like Streamrip"""
        import shutil
        from pathlib import Path

        # Check what's actually in the download directory
        download_path = Path(self.dir)
        if download_path.exists():
            items = list(download_path.iterdir())
            if items:
                # Count files vs directories
                files = [item for item in items if item.is_file()]
                dirs = [item for item in items if item.is_dir()]

                if len(files) > 1:
                    # Multiple files directly in download directory
                    # Create a folder to contain them all
                    # Use a generic album/playlist name or extract from first file
                    first_file = files[0]

                    # Try to extract album name from filename pattern
                    # Most zotify files follow: "01. Artist - Title.ext" format
                    filename = first_file.stem
                    if ". " in filename and " - " in filename:
                        # Extract artist from first file for folder name
                        parts = filename.split(". ", 1)
                        if len(parts) > 1:
                            track_part = parts[1]
                            if " - " in track_part:
                                artist = track_part.split(" - ")[0]
                                # Use artist name as folder name, or fallback to generic
                                folder_name = (
                                    f"{artist} - Album"
                                    if artist
                                    else "Zotify Download"
                                )
                            else:
                                folder_name = "Zotify Download"
                        else:
                            folder_name = "Zotify Download"
                    else:
                        folder_name = "Zotify Download"

                    # Create album folder and move all files into it
                    album_folder = download_path / folder_name
                    album_folder.mkdir(exist_ok=True)

                    # Move all files to the album folder
                    for file_item in files:
                        target_path = album_folder / file_item.name
                        shutil.move(str(file_item), str(target_path))

                    # Also move any directories (like cover art folders)
                    for dir_item in dirs:
                        target_path = album_folder / dir_item.name
                        shutil.move(str(dir_item), str(target_path))

                    # Update name to the folder name
                    self.name = folder_name

                elif len(items) == 1:
                    item = items[0]
                    if item.is_file():
                        # Single file - update name and set up for file upload
                        self.name = item.stem
                    else:
                        # Single folder - keep the folder structure intact for multi-file uploads
                        self.name = item.name

        # For music downloads (Zotify), we should NOT upload to the original group/supergroup
        # Instead, we should only upload to user's PM and dump chats like Streamrip does
        # Override the upload destination to avoid uploading to original group
        original_up_dest = self.up_dest

        # If no specific destination was set and the command was used in a group/supergroup,
        # set up_dest to user's PM to avoid uploading to the group
        if not self.up_dest and self.message.chat.type.name in [
            "GROUP",
            "SUPERGROUP",
        ]:
            LOGGER.info(
                f"Zotify: Overriding upload destination from group {self.message.chat.id} to user PM {self.user_id}"
            )
            self.up_dest = str(self.user_id)

        # Now call the parent on_download_complete which will handle upload using standard flow
        await super().on_download_complete()

        # Restore original up_dest after upload
        self.up_dest = original_up_dest
