"""
Gallery-dl post-processor system for aimleechbot
Supports metadata extraction, archive management, format conversion, and custom hooks
"""

import asyncio
import json
import os
import sqlite3
from typing import Any

from bot import LOGGER


class GalleryDLPostProcessor:
    """Advanced post-processor for gallery-dl downloads"""

    def __init__(self, download_path: str, listener=None):
        self.download_path = download_path
        self.listener = listener
        self.metadata_files = []
        self.processed_files = []
        self.archive_db = None

    async def setup_post_processors(self, config: dict[str, Any]):
        """Setup post-processors based on configuration"""
        try:
            processors = []

            # Metadata processor
            if config.get("metadata", {}).get("enabled", True):
                processors.append(self._setup_metadata_processor(config["metadata"]))

            # Archive processor
            if config.get("archive", {}).get("enabled", True):
                processors.append(self._setup_archive_processor(config["archive"]))

            # Format conversion processor
            if config.get("convert", {}).get("enabled", False):
                processors.append(
                    self._setup_conversion_processor(config["convert"])
                )

            # Custom hooks processor
            if config.get("hooks", {}).get("enabled", False):
                processors.append(self._setup_hooks_processor(config["hooks"]))

            return processors

        except Exception as e:
            LOGGER.error(f"Error setting up post-processors: {e}")
            return []

    def _setup_metadata_processor(
        self, metadata_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Setup metadata extraction processor"""
        return {
            "name": "metadata",
            "mode": metadata_config.get("mode", "json"),
            "filename": metadata_config.get("filename", "{id}_metadata.{extension}"),
            "directory": metadata_config.get("directory", ""),
            "fields": metadata_config.get(
                "fields",
                [
                    "id",
                    "title",
                    "description",
                    "tags",
                    "date",
                    "uploader",
                    "url",
                    "filename",
                    "extension",
                    "filesize",
                    "width",
                    "height",
                ],
            ),
            "skip_existing": metadata_config.get("skip_existing", True),
        }

    def _setup_archive_processor(
        self, archive_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Setup archive management processor"""
        return {
            "name": "archive",
            "database": archive_config.get("database", "gallery_dl_archive.db"),
            "table": archive_config.get("table", "downloads"),
            "format": archive_config.get("format", "{category}_{id}"),
            "mode": archive_config.get("mode", "memory"),
            "pragma": archive_config.get("pragma", ["journal_mode=WAL"]),
        }

    def _setup_conversion_processor(
        self, convert_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Setup format conversion processor"""
        return {
            "name": "convert",
            "formats": convert_config.get(
                "formats",
                {
                    "webp": {"quality": 85, "lossless": False},
                    "jpg": {"quality": 90},
                    "png": {"optimize": True},
                },
            ),
            "video_formats": convert_config.get(
                "video_formats",
                {
                    "mp4": {"codec": "h264", "quality": "high"},
                    "webm": {"codec": "vp9", "quality": "medium"},
                },
            ),
            "keep_original": convert_config.get("keep_original", False),
        }

    def _setup_hooks_processor(self, hooks_config: dict[str, Any]) -> dict[str, Any]:
        """Setup custom hooks processor"""
        return {
            "name": "hooks",
            "pre_download": hooks_config.get("pre_download", []),
            "post_download": hooks_config.get("post_download", []),
            "pre_process": hooks_config.get("pre_process", []),
            "post_process": hooks_config.get("post_process", []),
            "on_error": hooks_config.get("on_error", []),
        }

    async def process_metadata(
        self,
        file_path: str,
        metadata: dict[str, Any],
        processor_config: dict[str, Any],
    ):
        """Process and save metadata"""
        try:
            mode = processor_config.get("mode", "json")
            filename_template = processor_config.get(
                "filename", "{id}_metadata.{extension}"
            )
            fields = processor_config.get("fields", [])

            # Filter metadata based on specified fields
            if fields:
                filtered_metadata = {
                    k: v for k, v in metadata.items() if k in fields
                }
            else:
                filtered_metadata = metadata

            # Generate metadata filename
            metadata_filename = self._format_filename(
                filename_template, metadata, mode
            )
            metadata_path = os.path.join(
                os.path.dirname(file_path), metadata_filename
            )

            # Skip if exists and skip_existing is True
            if processor_config.get("skip_existing", True) and os.path.exists(
                metadata_path
            ):
                return metadata_path

            # Save metadata based on mode
            if mode == "json":
                await self._save_json_metadata(metadata_path, filtered_metadata)
            elif mode == "txt":
                await self._save_text_metadata(metadata_path, filtered_metadata)
            elif mode == "yaml":
                await self._save_yaml_metadata(metadata_path, filtered_metadata)

            self.metadata_files.append(metadata_path)
            return metadata_path

        except Exception as e:
            LOGGER.error(f"Error processing metadata: {e}")
            return None

    async def _save_json_metadata(self, path: str, metadata: dict[str, Any]):
        """Save metadata as JSON"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)

    async def _save_text_metadata(self, path: str, metadata: dict[str, Any]):
        """Save metadata as text"""
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(f"{key}: {value}\n" for key, value in metadata.items())

    async def _save_yaml_metadata(self, path: str, metadata: dict[str, Any]):
        """Save metadata as YAML"""
        try:
            import yaml

            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(metadata, f, default_flow_style=False, allow_unicode=True)
        except ImportError:
            LOGGER.warning("PyYAML not installed, falling back to JSON format")
            await self._save_json_metadata(path, metadata)

    async def process_archive(
        self,
        file_path: str,
        metadata: dict[str, Any],
        processor_config: dict[str, Any],
    ):
        """Process archive management"""
        try:
            database_path = os.path.join(
                self.download_path,
                processor_config.get("database", "gallery_dl_archive.db"),
            )
            table = processor_config.get("table", "downloads")
            format_template = processor_config.get("format", "{category}_{id}")

            # Initialize archive database if not exists
            if not self.archive_db:
                self.archive_db = await self._init_archive_db(database_path, table)

            # Generate archive key
            archive_key = self._format_filename(format_template, metadata, "key")

            # Check if already archived
            if await self._check_archive(archive_key):
                return True

            # Add to archive
            await self._add_to_archive(archive_key, file_path, metadata)
            return True

        except Exception as e:
            LOGGER.error(f"Error processing archive: {e}")
            return False

    async def _init_archive_db(
        self, database_path: str, table: str
    ) -> sqlite3.Connection:
        """Initialize archive database"""
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        conn = sqlite3.connect(database_path)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archive_key TEXT UNIQUE,
                file_path TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return conn

    async def _check_archive(self, archive_key: str) -> bool:
        """Check if file is already archived"""
        if not self.archive_db:
            return False

        cursor = self.archive_db.execute(
            "SELECT 1 FROM downloads WHERE archive_key = ?", (archive_key,)
        )
        return cursor.fetchone() is not None

    async def _add_to_archive(
        self, archive_key: str, file_path: str, metadata: dict[str, Any]
    ):
        """Add file to archive"""
        if not self.archive_db:
            return

        metadata_json = json.dumps(metadata, default=str)
        self.archive_db.execute(
            "INSERT OR REPLACE INTO downloads (archive_key, file_path, metadata) VALUES (?, ?, ?)",
            (archive_key, file_path, metadata_json),
        )
        self.archive_db.commit()

    def _format_filename(
        self, template: str, metadata: dict[str, Any], mode: str = "file"
    ) -> str:
        """Format filename using metadata"""
        try:
            # Simple template formatting
            formatted = template
            for key, value in metadata.items():
                placeholder = f"{{{key}}}"
                if placeholder in formatted:
                    formatted = formatted.replace(placeholder, str(value))

            # Set extension based on mode
            if mode == "json":
                formatted = formatted.replace("{extension}", "json")
            elif mode == "txt":
                formatted = formatted.replace("{extension}", "txt")
            elif mode == "yaml":
                formatted = formatted.replace("{extension}", "yaml")
            elif mode == "key":
                formatted = formatted.replace("{extension}", "")

            return formatted

        except Exception as e:
            LOGGER.error(f"Error formatting filename: {e}")
            return f"metadata_{metadata.get('id', 'unknown')}.json"

    async def run_custom_hooks(
        self,
        hook_type: str,
        file_path: str,
        metadata: dict[str, Any],
        processor_config: dict[str, Any],
    ):
        """Run custom hooks"""
        try:
            hooks = processor_config.get(hook_type, [])
            for hook in hooks:
                if isinstance(hook, str):
                    # Command hook
                    await self._run_command_hook(hook, file_path, metadata)
                elif isinstance(hook, dict):
                    # Function hook
                    await self._run_function_hook(hook, file_path, metadata)

        except Exception as e:
            LOGGER.error(f"Error running {hook_type} hooks: {e}")

    async def _run_command_hook(
        self, command: str, file_path: str, metadata: dict[str, Any]
    ):
        """Run command hook"""
        try:
            # Format command with metadata
            formatted_command = command.format(
                file_path=file_path,
                filename=os.path.basename(file_path),
                directory=os.path.dirname(file_path),
                **metadata,
            )

            # Execute command
            process = await asyncio.create_subprocess_shell(
                formatted_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                LOGGER.warning(f"Hook command failed: {stderr.decode()}")

        except Exception as e:
            LOGGER.error(f"Error running command hook: {e}")

    async def _run_function_hook(
        self, hook_config: dict[str, Any], file_path: str, metadata: dict[str, Any]
    ):
        """Run function hook"""
        try:
            # This would allow custom Python functions to be executed
            # Implementation depends on security requirements
            LOGGER.info(f"Function hook not implemented: {hook_config}")

        except Exception as e:
            LOGGER.error(f"Error running function hook: {e}")

    async def cleanup(self):
        """Cleanup post-processor resources"""
        try:
            if self.archive_db:
                self.archive_db.close()
                self.archive_db = None

        except Exception as e:
            LOGGER.error(f"Error during post-processor cleanup: {e}")

    def get_processed_files(self) -> list[str]:
        """Get list of all processed files"""
        return self.processed_files + self.metadata_files
