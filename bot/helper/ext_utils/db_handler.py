import asyncio
import contextlib
import inspect
import time
from time import time as get_time

from aiofiles import open as aiopen

# Initialize USING_MOTOR flag
USING_MOTOR = False

# Smart import: Use pymongo's AsyncMongoClient if available (kurigram/newer pymongo),
# otherwise fall back to motor's AsyncIOMotorClient (pyrofork/older pymongo)
try:
    from pymongo import AsyncMongoClient
    from pymongo.errors import (
        ConnectionFailure,
        PyMongoError,
        ServerSelectionTimeoutError,
    )
    from pymongo.server_api import ServerApi

except ImportError:
    try:
        from motor.motor_asyncio import AsyncIOMotorClient as AsyncMongoClient
        from pymongo.errors import (
            ConnectionFailure,
            PyMongoError,
            ServerSelectionTimeoutError,
        )
        from pymongo.server_api import ServerApi

    except ImportError:
        raise ImportError(
            "Neither pymongo.AsyncMongoClient nor motor.motor_asyncio.AsyncIOMotorClient is available. "
            "Please install either a newer version of pymongo (>=4.5) or motor."
        )

from bot import LOGGER, qbit_options, rss_dict, user_data
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None


class DbManager:
    def __init__(self):
        self._return = True
        self._conn = None
        self.db = None
        self._last_connection_check = 0
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5

    async def connect(self):
        try:
            # Only close if we have a connection and it's not working
            if self._conn is not None:
                try:
                    # Test if connection is still working before closing
                    await self._conn.admin.command("ping")
                    # If ping succeeds, connection is still good
                    if self.db is not None:
                        LOGGER.info("Reusing existing database connection")
                        return
                except Exception:
                    # Connection is bad, close it
                    try:
                        await self._conn.close()
                    except Exception as e:
                        LOGGER.error(f"Error closing previous DB connection: {e}")

            # Optimized connection parameters for better stability and performance
            self._conn = AsyncMongoClient(
                Config.DATABASE_URL,
                server_api=ServerApi("1"),
                maxPoolSize=10,  # Increased pool size for better concurrency
                minPoolSize=2,  # Keep minimum connections alive
                maxIdleTimeMS=300000,  # 5 minutes idle time
                connectTimeoutMS=20000,  # 20 seconds connection timeout
                socketTimeoutMS=60000,  # 60 seconds socket timeout
                serverSelectionTimeoutMS=30000,  # 30 seconds server selection timeout
                heartbeatFrequencyMS=30000,  # 30 seconds heartbeat frequency
                retryWrites=True,  # Enable retry for write operations
                retryReads=True,  # Enable retry for read operations
                waitQueueTimeoutMS=30000,  # 30 seconds wait queue timeout
                maxConnecting=5,  # Limit concurrent connection attempts
            )

            # Verify connection is working with a ping
            await self._conn.admin.command("ping")

            self.db = self._conn.luna
            self._return = False
            LOGGER.info("Successfully connected to database")

            # Initialize database schema
            await self._initialize_schema()
        except PyMongoError as e:
            LOGGER.error(f"Error in DB connection: {e}")
            self.db = None
            self._return = True
            self._conn = None

    async def ensure_connection(self):
        """Check if the database connection is alive and reconnect if needed."""
        # Skip if no database URL is configured
        if not Config.DATABASE_URL:
            self._return = True
            return False

        # Skip if database is marked as closed/disconnected
        if self._return:
            return False

        # Skip if we've checked recently (within last 30 seconds)
        current_time = int(get_time())
        if (
            current_time - self._last_connection_check < 30
            and self._conn is not None
            and not self._return
        ):
            return True

        self._last_connection_check = current_time

        # If we don't have a connection, try to connect
        if self._conn is None or self._return:
            await self.connect()
            return not self._return

        # Check if the connection is still alive
        try:
            # Simple ping to check connection
            await self._conn.admin.command("ping")
            self._reconnect_attempts = 0  # Reset reconnect attempts on success
            return True
        except (PyMongoError, ConnectionFailure, ServerSelectionTimeoutError) as e:
            LOGGER.warning(f"Database connection check failed: {e}")

            # Increment reconnect attempts
            self._reconnect_attempts += 1

            # If we've tried too many times, log an error and give up
            if self._reconnect_attempts > self._max_reconnect_attempts:
                LOGGER.error("Maximum reconnection attempts reached. Giving up.")
                await self.disconnect()
                return False

            # Exponential backoff for reconnection attempts
            backoff_delay = min(
                2 ** (self._reconnect_attempts - 1), 30
            )  # Max 30 seconds
            LOGGER.info(
                f"Attempting to reconnect to database (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}) after {backoff_delay}s delay"
            )

            # Wait before reconnecting to avoid overwhelming the database
            await asyncio.sleep(backoff_delay)

            # Reset connection state before reconnecting
            self._conn = None
            self.db = None
            self._return = True

            await self.connect()
            return not self._return

    async def disconnect(self):
        # Set return flag first to prevent new operations
        self._return = True

        # Stop heartbeat task first to prevent it from trying to reconnect
        if hasattr(self, "_heartbeat_task") and self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
            LOGGER.debug("Database heartbeat task stopped during disconnect")

        if self._conn is not None:
            try:
                await self._conn.close()
                LOGGER.info("Database connection closed successfully")
            except Exception as e:
                # Don't log as error if it's already closed
                if "closed" in str(e).lower():
                    LOGGER.debug(f"Database connection was already closed: {e}")
                else:
                    LOGGER.error(f"Error closing database connection: {e}")
        self._conn = None
        self.db = None
        self._last_connection_check = 0
        self._reconnect_attempts = 0

        # Force garbage collection after database operations
        if smart_garbage_collection is not None:
            smart_garbage_collection(aggressive=True)

    async def safe_db_operation(self, operation_name: str, operation_func):
        """Safely execute a database operation with proper error handling."""
        try:
            # Check if database is available
            if self._return or self._conn is None:
                LOGGER.debug(f"Skipping {operation_name} - database is disconnected")
                return None

            # Ensure connection is alive
            if not await self.ensure_connection():
                LOGGER.debug(
                    f"Skipping {operation_name} - could not ensure database connection"
                )
                return None

            # Execute the operation
            return await operation_func()

        except Exception as e:
            # Handle database closed errors gracefully
            if any(
                keyword in str(e).lower()
                for keyword in [
                    "closed database",
                    "connection closed",
                    "client is closed",
                    "cannot operate on a closed",
                    "connection is closed",
                ]
            ):
                LOGGER.debug(
                    f"Database operation {operation_name} failed - connection closed (expected during shutdown): {e}"
                )
                return None
            LOGGER.error(f"Error in database operation {operation_name}: {e}")
            return None

    # Removed update_deploy_config method - deploy config is now only updated during startup
    # when actual config.py changes are detected. No more bidirectional sync!

    async def update_config(self, dict_):
        """
        Update runtime config only - never touch deploy config

        Runtime config represents user modifications and should be independent
        of deploy config which represents the source of truth from config.py

        Args:
            dict_: Configuration dictionary to update
        """
        if not await self.ensure_connection():
            return
        try:
            # Update only runtime config - no timestamps, no deploy config sync
            await self.db.settings.config.update_one(
                {"_id": TgClient.ID},
                {"$set": dict_},
                upsert=True,
            )

        except PyMongoError as e:
            LOGGER.error(f"Error updating config: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    # Removed obsolete sync methods - no longer needed with new clean architecture

    async def update_aria2(self, key, value):
        if not await self.ensure_connection():
            return
        try:
            await self.db.settings.aria2c.update_one(
                {"_id": TgClient.ID},
                {"$set": {key: value}},
                upsert=True,
            )
        except PyMongoError as e:
            LOGGER.error(f"Error updating aria2 config: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    async def update_qbittorrent(self, key, value):
        if not await self.ensure_connection():
            return
        try:
            await self.db.settings.qbittorrent.update_one(
                {"_id": TgClient.ID},
                {"$set": {key: value}},
                upsert=True,
            )
        except PyMongoError as e:
            LOGGER.error(f"Error updating qbittorrent config: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    async def save_qbit_settings(self):
        if not await self.ensure_connection():
            return
        try:
            await self.db.settings.qbittorrent.update_one(
                {"_id": TgClient.ID},
                {"$set": qbit_options},
                upsert=True,
            )
        except PyMongoError as e:
            LOGGER.error(f"Error saving qbittorrent settings: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    async def update_private_file(self, path):
        if self._return:
            return
        db_path = path.replace(".", "__")
        if await aiopath.exists(path):
            try:
                async with aiopen(path, "rb+") as pf:
                    pf_bin = await pf.read()
                await self.db.settings.files.update_one(
                    {"_id": TgClient.ID},
                    {"$set": {db_path: pf_bin}},
                    upsert=True,
                )
                # Note: config.py changes are now handled during startup, not here

                # Force garbage collection after handling large files
                if (
                    len(pf_bin) > 1024 * 1024
                    and smart_garbage_collection is not None
                ):  # 1MB
                    smart_garbage_collection(aggressive=False)

                # Explicitly delete large binary data
                del pf_bin
            except Exception as e:
                LOGGER.error(f"Error updating private file {path}: {e}")
        else:
            await self.db.settings.files.update_one(
                {"_id": TgClient.ID},
                {"$unset": {db_path: ""}},
                upsert=True,
            )

    async def get_private_files(self):
        """Get list of available private files from database and filesystem"""
        if self._return:
            return {}

        try:
            # Get files from database
            db_files = await self.db.settings.files.find_one({"_id": TgClient.ID})
            if not db_files:
                db_files = {}

            # List of known private files to check
            known_files = [
                "config.py",
                "token.pickle",
                "token_sa.pickle",
                "youtube_token.pickle",
                "rclone.conf",
                "accounts.zip",
                "list_drives.txt",
                "cookies.txt",
                ".netrc",
                "shorteners.txt",
                "streamrip_config.toml",
                "zotify_credentials.json",
            ]

            available_files = {}

            # Check all known files regardless of existence to show complete status
            for file_name in known_files:
                db_key = file_name.replace(".", "__")
                file_exists_db = db_key in db_files and db_files[db_key] is not None
                file_exists_fs = await aiopath.exists(file_name)

                # Special handling for accounts.zip - also check if accounts directory exists
                accounts_dir_exists = False
                if file_name == "accounts.zip":
                    accounts_dir_exists = await aiopath.exists("accounts")

                # Always include the file in the list to show complete status
                available_files[file_name] = {
                    "exists_db": file_exists_db,
                    "exists_fs": file_exists_fs,
                    "accounts_dir_exists": accounts_dir_exists
                    if file_name == "accounts.zip"
                    else False,
                    "size_db": len(db_files.get(db_key, b""))
                    if file_exists_db
                    else 0,
                    "size_fs": await aiopath.getsize(file_name)
                    if file_exists_fs
                    else 0,
                }

            return available_files

        except Exception as e:
            LOGGER.error(f"Error getting private files list: {e}")
            return {}

    async def sync_private_files_to_db(self):
        """Sync all existing private files from filesystem to database"""
        if self._return:
            return {"synced": 0, "errors": []}

        try:
            # List of known private files to sync
            known_files = [
                "config.py",
                "token.pickle",
                "token_sa.pickle",
                "youtube_token.pickle",
                "rclone.conf",
                "accounts.zip",
                "list_drives.txt",
                "cookies.txt",
                ".netrc",
                "shorteners.txt",
                "streamrip_config.toml",
                "zotify_credentials.json",
            ]

            synced_count = 0
            errors = []

            for file_name in known_files:
                try:
                    if await aiopath.exists(file_name):
                        # Check if already in database
                        db_key = file_name.replace(".", "__")
                        db_files = await self.db.settings.files.find_one(
                            {"_id": TgClient.ID}
                        )

                        if (
                            not db_files
                            or db_key not in db_files
                            or not db_files[db_key]
                        ):
                            # File exists in filesystem but not in database, sync it
                            await self.update_private_file(file_name)
                            synced_count += 1
                            LOGGER.info(f"Synced {file_name} to database")

                except Exception as e:
                    error_msg = f"Error syncing {file_name}: {e}"
                    LOGGER.error(error_msg)
                    errors.append(error_msg)

            return {"synced": synced_count, "errors": errors}

        except Exception as e:
            LOGGER.error(f"Error syncing private files to database: {e}")
            return {"synced": 0, "errors": [str(e)]}

    async def sync_private_files_to_fs(self):
        """Sync all existing private files from database to filesystem"""
        if self._return:
            return {"synced": 0, "errors": []}

        try:
            # Get all files from database
            db_files = await self.db.settings.files.find_one({"_id": TgClient.ID})
            if not db_files:
                return {"synced": 0, "errors": ["No files found in database"]}

            # List of known private files to sync
            known_files = [
                "config.py",
                "token.pickle",
                "token_sa.pickle",
                "youtube_token.pickle",
                "rclone.conf",
                "accounts.zip",
                "list_drives.txt",
                "cookies.txt",
                ".netrc",
                "shorteners.txt",
                "streamrip_config.toml",
                "zotify_credentials.json",
            ]

            synced_count = 0
            errors = []

            for file_name in known_files:
                try:
                    db_key = file_name.replace(".", "__")

                    # Check if file exists in database but not in filesystem
                    if db_files.get(db_key):
                        if not await aiopath.exists(file_name):
                            # File exists in database but not in filesystem, sync it
                            async with aiopen(file_name, "wb") as f:
                                await f.write(db_files[db_key])

                            # Handle special post-sync operations
                            if file_name == "accounts.zip":
                                # Extract accounts.zip if it was synced
                                try:
                                    from asyncio import create_subprocess_exec

                                    await (
                                        await create_subprocess_exec(
                                            "7z",
                                            "x",
                                            "-o.",
                                            "-aoa",
                                            "accounts.zip",
                                            "accounts/*.json",
                                        )
                                    ).wait()
                                    await (
                                        await create_subprocess_exec(
                                            "chmod", "-R", "777", "accounts"
                                        )
                                    ).wait()
                                except Exception as e:
                                    LOGGER.warning(
                                        f"Failed to extract accounts.zip after sync: {e}"
                                    )

                            elif file_name in [".netrc", "netrc"]:
                                # Set proper permissions for .netrc
                                try:
                                    await (
                                        await create_subprocess_exec(
                                            "chmod", "600", ".netrc"
                                        )
                                    ).wait()
                                    await (
                                        await create_subprocess_exec(
                                            "cp", ".netrc", "/root/.netrc"
                                        )
                                    ).wait()
                                except Exception as e:
                                    LOGGER.warning(
                                        f"Failed to set .netrc permissions after sync: {e}"
                                    )

                            synced_count += 1
                            LOGGER.info(f"Synced {file_name} to filesystem")

                except Exception as e:
                    error_msg = f"Error syncing {file_name}: {e}"
                    LOGGER.error(error_msg)
                    errors.append(error_msg)

            return {"synced": synced_count, "errors": errors}

        except Exception as e:
            LOGGER.error(f"Error syncing private files to filesystem: {e}")
            return {"synced": 0, "errors": [str(e)]}

    async def update_nzb_config(self):
        if self._return:
            return
        async with aiopen("sabnzbd/SABnzbd.ini", "rb+") as pf:
            nzb_conf = await pf.read()
        await self.db.settings.nzb.replace_one(
            {"_id": TgClient.ID},
            {"SABnzbd__ini": nzb_conf},
            upsert=True,
        )

    async def update_user_data(self, user_id):
        if self._return:
            LOGGER.warning(
                f"Database connection not available, cannot save user data for user {user_id}"
            )
            return
        data = user_data.get(user_id, {})
        if not data:
            LOGGER.warning(
                f"No user data found for user {user_id} in memory, cannot save to database"
            )
            return

        data = data.copy()
        for key in (
            "THUMBNAIL",
            "RCLONE_CONFIG",
            "TOKEN_PICKLE",
            "YOUTUBE_TOKEN_PICKLE",
            "USER_COOKIES",
            "TOKEN",
            "TIME",
        ):
            data.pop(key, None)
        pipeline = [
            {
                "$replaceRoot": {
                    "newRoot": {
                        "$mergeObjects": [
                            data,
                            {
                                "$arrayToObject": {
                                    "$filter": {
                                        "input": {"$objectToArray": "$$ROOT"},
                                        "as": "field",
                                        "cond": {
                                            "$in": [
                                                "$$field.k",
                                                [
                                                    "THUMBNAIL",
                                                    "RCLONE_CONFIG",
                                                    "TOKEN_PICKLE",
                                                    "YOUTUBE_TOKEN_PICKLE",
                                                    "USER_COOKIES",
                                                ],
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        ]
        try:
            await self.db.users.update_one({"_id": user_id}, pipeline, upsert=True)

        except Exception as e:
            LOGGER.error(
                f"Failed to save user data to database for user {user_id}: {e}"
            )

    async def update_user_doc(self, user_id, key, path="", binary_data=None):
        """Update a user document in the database with memory-efficient handling.

        Args:
            user_id: The user ID
            key: The key to update
            path: The path to the file to read (if binary_data is None)
            binary_data: Binary data to store directly (if provided, path is ignored)
        """
        if self._return:
            return

        if binary_data is not None:
            # Use the provided binary data directly
            doc_bin = binary_data
        elif path:
            try:
                # Get file size for logging
                file_size = await aiopath.getsize(path)
                LOGGER.info(
                    f"Reading file {path} of size {file_size} bytes for user {user_id}"
                )

                # Use chunked reading for memory efficiency
                chunk_size = 8 * 1024 * 1024  # 8MB chunks
                doc_bin = bytearray()

                async with aiopen(path, "rb") as doc:
                    while True:
                        try:
                            chunk = await doc.read(chunk_size)
                            if not chunk:
                                break
                            doc_bin.extend(chunk)

                            # Force garbage collection periodically for large files
                            if len(doc_bin) % (32 * 1024 * 1024) == 0:  # Every 32MB
                                if smart_garbage_collection is not None:
                                    smart_garbage_collection(aggressive=False)

                        except MemoryError:
                            LOGGER.error(
                                f"Memory error while reading chunk from {path}"
                            )
                            # Try to free up memory
                            if smart_garbage_collection is not None:
                                smart_garbage_collection(aggressive=True)
                            raise MemoryError(
                                f"Not enough memory to read file: {path}"
                            )

                # Convert to bytes for database storage
                doc_bin = bytes(doc_bin)

                # Verify the data was read correctly
                if len(doc_bin) != file_size:
                    LOGGER.error(
                        f"File read size mismatch: expected {file_size}, got {len(doc_bin)}"
                    )
                    raise ValueError("File read size mismatch")

                LOGGER.info(f"Successfully read {len(doc_bin)} bytes from {path}")

            except MemoryError as e:
                LOGGER.error(f"Memory error reading file {path}: {e}")
                # Force aggressive garbage collection
                if smart_garbage_collection is not None:
                    smart_garbage_collection(aggressive=True)
                raise MemoryError(f"Not enough memory to read file: {path}")
            except Exception as e:
                LOGGER.error(f"Error reading file {path}: {e}")
                raise
        else:
            # Remove the key if no data is provided
            await self.db.users.update_one(
                {"_id": user_id},
                {"$unset": {key: ""}},
                upsert=True,
            )
            return

        try:
            # Store the binary data in the database
            LOGGER.info(
                f"Storing {len(doc_bin)} bytes in database for user {user_id}, key {key}"
            )
            await self.db.users.update_one(
                {"_id": user_id},
                {"$set": {key: doc_bin}},
                upsert=True,
            )
            LOGGER.info(
                f"Successfully updated user document for user {user_id}, key {key}"
            )

            # Force garbage collection after large database operations
            if (
                len(doc_bin) > 10 * 1024 * 1024
                and smart_garbage_collection is not None
            ):  # 10MB
                smart_garbage_collection(aggressive=False)

        except MemoryError as e:
            LOGGER.error(
                f"Memory error storing data in database for user {user_id}: {e}"
            )
            # Force aggressive garbage collection
            if smart_garbage_collection is not None:
                smart_garbage_collection(aggressive=True)
            raise MemoryError("Not enough memory to store data in database")
        except Exception as e:
            LOGGER.error(
                f"Error updating user document for user {user_id}, key {key}: {e}"
            )
            raise

    async def rss_update_all(self):
        if self._return:
            return
        for user_id in list(rss_dict.keys()):
            await self.db.rss[TgClient.ID].replace_one(
                {"_id": user_id},
                rss_dict[user_id],
                upsert=True,
            )

    async def rss_update(self, user_id):
        if self._return:
            return
        await self.db.rss[TgClient.ID].replace_one(
            {"_id": user_id},
            rss_dict[user_id],
            upsert=True,
        )

    async def rss_delete(self, user_id):
        if self._return:
            return
        await self.db.rss[TgClient.ID].delete_one({"_id": user_id})

    async def add_incomplete_task(self, cid, link, tag):
        if self._return:
            return
        try:
            await self.db.tasks[TgClient.ID].update_one(
                {"_id": link},
                {"$set": {"cid": cid, "tag": tag}},
                upsert=True,
            )
        except Exception as e:
            # Log the error but don't fail the operation
            LOGGER.warning(f"Failed to add incomplete task to database: {e}")
            # Continue with the operation even if database update fails

    async def get_pm_uids(self):
        if self._return:
            return None
        return [doc["_id"] async for doc in self.db.pm_users[TgClient.ID].find({})]

    async def update_pm_users(self, user_id):
        if self._return:
            return
        if not bool(await self.db.pm_users[TgClient.ID].find_one({"_id": user_id})):
            await self.db.pm_users[TgClient.ID].insert_one({"_id": user_id})
            LOGGER.info(f"New PM User Added : {user_id}")

    async def rm_pm_user(self, user_id):
        if self._return:
            return
        await self.db.pm_users[TgClient.ID].delete_one({"_id": user_id})

    async def update_user_tdata(self, user_id, token, expiry_time):
        if self._return:
            return
        await self.db.access_token.update_one(
            {"_id": user_id},
            {"$set": {"TOKEN": token, "TIME": expiry_time}},
            upsert=True,
        )

    async def update_user_token(self, user_id, token):
        if self._return:
            return
        await self.db.access_token.update_one(
            {"_id": user_id},
            {"$set": {"TOKEN": token}},
            upsert=True,
        )

    async def get_token_expiry(self, user_id):
        if self._return:
            return None
        user_data = await self.db.access_token.find_one({"_id": user_id})
        if user_data:
            return user_data.get("TIME")
        return None

    async def delete_user_token(self, user_id):
        if self._return:
            return
        await self.db.access_token.delete_one({"_id": user_id})

    async def get_user_token(self, user_id):
        if self._return:
            return None
        user_data = await self.db.access_token.find_one({"_id": user_id})
        if user_data:
            return user_data.get("TOKEN")
        return None

    async def get_user_doc(self, user_id):
        """Get a user document from the database.

        Args:
            user_id: The user ID to get the document for.

        Returns:
            The user document as a dictionary, or None if not found.
        """
        if self._return:
            return None
        return await self.db.users.find_one({"_id": user_id})

    async def delete_all_access_tokens(self):
        if self._return:
            return
        await self.db.access_token.delete_many({})

    async def rm_complete_task(self, link):
        if self._return:
            return
        try:
            await self.db.tasks[TgClient.ID].delete_one({"_id": link})
        except Exception as e:
            # Log the error but don't fail the operation
            LOGGER.warning(f"Failed to remove completed task from database: {e}")
            # Continue with the operation even if database update fails

    async def get_incomplete_tasks(self):
        notifier_dict = {}

        async def _get_tasks():
            if await self.db.tasks[TgClient.ID].find_one():
                rows = self.db.tasks[TgClient.ID].find({})
                async for row in rows:
                    if row["cid"] in list(notifier_dict.keys()):
                        if row["tag"] in list(notifier_dict[row["cid"]]):
                            notifier_dict[row["cid"]][row["tag"]].append(row["_id"])
                        else:
                            notifier_dict[row["cid"]][row["tag"]] = [row["_id"]]
                    else:
                        notifier_dict[row["cid"]] = {row["tag"]: [row["_id"]]}

            # Only drop the collection if we successfully retrieved the data
            try:
                await self.db.tasks[TgClient.ID].drop()
            except PyMongoError as e:
                LOGGER.error(f"Error dropping tasks collection: {e}")

            return notifier_dict

        result = await self.safe_db_operation("get_incomplete_tasks", _get_tasks)
        return result if result is not None else notifier_dict

    async def trunc_table(self, name):
        if self._return:
            return
        await self.db[name][TgClient.ID].drop()

    async def store_scheduled_deletion(
        self,
        chat_ids,
        message_ids,
        delete_time,
        bot_id=None,
    ):
        """Store messages for scheduled deletion

        Args:
            chat_ids: List of chat IDs
            message_ids: List of message IDs
            delete_time: Timestamp when the message should be deleted
            bot_id: ID of the bot that created the message (default: main bot ID)
        """
        if not await self.ensure_connection():
            return

        # Default to main bot ID if not specified
        if bot_id is None:
            bot_id = TgClient.ID

        # Storing messages for deletion

        # Check if connection is still valid before operation
        if self._conn is None or self._return:
            LOGGER.warning(
                "Database connection not available for scheduled deletion storage"
            )
            return

        # Store each message individually to avoid bulk write issues
        for chat_id, message_id in zip(chat_ids, message_ids, strict=True):
            try:
                await self.db.scheduled_deletions.update_one(
                    {"chat_id": chat_id, "message_id": message_id},
                    {"$set": {"delete_time": delete_time, "bot_id": bot_id}},
                    upsert=True,
                )
            except (PyMongoError, AttributeError) as e:
                LOGGER.error(f"Error storing scheduled deletion: {e}")
                # Reset connection state and try to reconnect for next operation
                self._conn = None
                self._return = True
                await self.ensure_connection()
                break  # Stop processing if connection fails

        # Messages stored for deletion

    async def remove_scheduled_deletion(self, chat_id, message_id):
        """Remove a message from scheduled deletions"""
        if not await self.ensure_connection():
            return
        try:
            # Check if connection is still valid before operation
            if self._conn is None or self._return:
                LOGGER.warning(
                    "Database connection not available for scheduled deletion removal"
                )
                return
            await self.db.scheduled_deletions.delete_one(
                {"chat_id": chat_id, "message_id": message_id},
            )
        except (PyMongoError, AttributeError) as e:
            LOGGER.error(f"Error removing scheduled deletion: {e}")
            # Reset connection state and try to reconnect for next operation
            self._conn = None
            self._return = True
            await self.ensure_connection()

    async def get_pending_deletions(self):
        """Get messages that are due for deletion"""
        if not await self.ensure_connection():
            return []

        current_time = int(get_time())
        # Get current time for comparison

        try:
            # Check if connection is still valid before operation
            if self._conn is None or self._return:
                LOGGER.warning(
                    "Database connection not available for pending deletions retrieval"
                )
                return []

            # Create index for better performance if it doesn't exist
            await self.db.scheduled_deletions.create_index([("delete_time", 1)])

            # Get all documents for manual processing
            all_docs = []
            try:
                async for doc in self.db.scheduled_deletions.find():
                    all_docs.append(doc)
            except (PyMongoError, AttributeError) as e:
                LOGGER.error(f"Error retrieving scheduled deletions: {e}")
                # Reset connection state and try to reconnect
                self._conn = None
                self._return = True
                await self.ensure_connection()
                return []

            # Process documents manually to ensure we catch all due messages
            # Include a buffer of 30 seconds to catch messages that are almost due
            buffer_time = 30  # 30 seconds buffer

            # Use list comprehension for better performance and return directly
            # Messages found for deletion
            return [
                (doc["chat_id"], doc["message_id"], doc.get("bot_id", TgClient.ID))
                for doc in all_docs
                if doc.get("delete_time", 0) <= current_time + buffer_time
            ]
        except PyMongoError as e:
            LOGGER.error(f"Error in get_pending_deletions: {e}")
            await self.ensure_connection()  # Try to reconnect
            return []

    async def clean_old_scheduled_deletions(self, days=1):
        """Clean up scheduled deletion entries that have been processed but not removed

        Args:
            days: Number of days after which to clean up entries (default: 1)
        """
        if not await self.ensure_connection():
            return 0

        try:
            # Calculate the timestamp for 'days' ago
            one_day_ago = int(get_time() - (days * 86400))  # 86400 seconds = 1 day

            # Cleaning up old scheduled deletion entries

            # Get all entries to check which ones are actually old and processed
            entries_to_check = [
                doc async for doc in self.db.scheduled_deletions.find({})
            ]

            # Count entries by type
            current_time = int(get_time())
            past_due = [
                doc for doc in entries_to_check if doc["delete_time"] < current_time
            ]

            # Only delete entries that are more than 'days' old AND have already been processed
            # (i.e., their delete_time is in the past)
            deleted_count = 0
            for doc in past_due:
                # If the entry is more than 'days' old from its scheduled deletion time
                if doc["delete_time"] < one_day_ago:
                    result = await self.db.scheduled_deletions.delete_one(
                        {"_id": doc["_id"]},
                    )
                    if result.deleted_count > 0:
                        deleted_count += 1

            # No need to log cleanup results

            return deleted_count
        except PyMongoError as e:
            LOGGER.error(f"Error cleaning old scheduled deletions: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation
            return 0

    async def get_all_scheduled_deletions(self):
        """Get all scheduled deletions for debugging purposes"""
        if not await self.ensure_connection():
            return []

        try:
            cursor = self.db.scheduled_deletions.find({})
            current_time = int(get_time())

            # Return all scheduled deletions
            result = [
                {
                    "chat_id": doc["chat_id"],
                    "message_id": doc["message_id"],
                    "delete_time": doc["delete_time"],
                    "bot_id": doc.get("bot_id", TgClient.ID),
                    "time_remaining": doc["delete_time"] - current_time
                    if "delete_time" in doc
                    else "unknown",
                    "is_due": doc["delete_time"]
                    <= current_time + 30  # 30 seconds buffer
                    if "delete_time" in doc
                    else False,
                }
                async for doc in cursor
            ]
        except PyMongoError as e:
            LOGGER.error(f"Error getting all scheduled deletions: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation
            return []

        # Only log detailed information when called from check_deletion.py
        caller_frame = inspect.currentframe().f_back
        caller_name = caller_frame.f_code.co_name if caller_frame else "unknown"

        if "check_deletion" in caller_name:
            LOGGER.info(f"Found {len(result)} total scheduled deletions in database")
            if result:
                pending_count = sum(1 for item in result if item["is_due"])
                future_count = sum(1 for item in result if not item["is_due"])

                LOGGER.info(
                    f"Pending deletions: {pending_count}, Future deletions: {future_count}",
                )

                # Log some sample entries
                if result:
                    sample = result[:5] if len(result) > 5 else result
                    for entry in sample:
                        LOGGER.info(
                            f"Sample entry: {entry} - Due for deletion: {entry['is_due']}",
                        )

        return result

    async def store_user_cookie(self, user_id, cookie_number, cookie_data):
        """Store a user cookie in the database with a specific number"""
        if self._return:
            return False

        try:
            from time import time

            await self.db.user_cookies.update_one(
                {"user_id": user_id, "cookie_number": cookie_number},
                {
                    "$set": {
                        "cookie_data": cookie_data,
                        "created_at": int(time()),
                        "updated_at": int(time()),
                    }
                },
                upsert=True,
            )
            LOGGER.info(
                f"Stored cookie #{cookie_number} for user {user_id} in database"
            )
            return True
        except Exception as e:
            LOGGER.error(
                f"Error storing cookie #{cookie_number} for user {user_id}: {e}"
            )
            return False

    async def get_user_cookies(self, user_id):
        """Get all cookies for a user from the database"""
        if self._return:
            return []

        try:
            cookies = []
            cursor = self.db.user_cookies.find({"user_id": user_id}).sort(
                "cookie_number", 1
            )
            async for doc in cursor:
                cookies.append(
                    {
                        "number": doc["cookie_number"],
                        "data": doc["cookie_data"],
                        "created_at": doc.get("created_at", 0),
                        "updated_at": doc.get("updated_at", 0),
                    }
                )
            return cookies
        except Exception as e:
            LOGGER.error(f"Error getting cookies for user {user_id}: {e}")
            return []

    async def delete_user_cookie(self, user_id, cookie_number):
        """Delete a specific cookie for a user"""
        if self._return:
            return False

        try:
            result = await self.db.user_cookies.delete_one(
                {"user_id": user_id, "cookie_number": cookie_number}
            )
            if result.deleted_count > 0:
                LOGGER.info(f"Deleted cookie #{cookie_number} for user {user_id}")
                return True
            return False
        except Exception as e:
            LOGGER.error(
                f"Error deleting cookie #{cookie_number} for user {user_id}: {e}"
            )
            return False

    async def delete_all_user_cookies(self, user_id):
        """Delete all cookies for a user"""
        if self._return:
            return 0

        try:
            result = await self.db.user_cookies.delete_many({"user_id": user_id})
            LOGGER.info(f"Deleted {result.deleted_count} cookies for user {user_id}")
            return result.deleted_count
        except Exception as e:
            LOGGER.error(f"Error deleting all cookies for user {user_id}: {e}")
            return 0

    async def count_user_cookies_db(self, user_id):
        """Count the number of cookies for a user in the database"""
        if self._return:
            return 0

        try:
            return await self.db.user_cookies.count_documents({"user_id": user_id})
        except Exception as e:
            LOGGER.error(f"Error counting cookies for user {user_id}: {e}")
            return 0

    # Enhanced NSFW Detection Database Methods
    async def store_nsfw_detection(self, detection_data: dict):
        """Store NSFW detection result in database for analysis and improvement"""
        if self._return:
            return False

        try:
            # Add bot ID and ensure required fields
            detection_data.update({"bot_id": TgClient.ID, "stored_at": time.time()})

            await self.db.nsfw_detections.insert_one(detection_data)
            return True
        except Exception as e:
            LOGGER.error(f"Error storing NSFW detection data: {e}")
            return False

    async def get_nsfw_detection_stats(self, days: int = 7) -> dict:
        """Get NSFW detection statistics for the last N days"""
        if self._return:
            return {}

        try:
            cutoff_time = get_time() - (days * 86400)  # N days ago

            pipeline = [
                {
                    "$match": {
                        "bot_id": TgClient.ID,
                        "timestamp": {"$gte": cutoff_time},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_detections": {"$sum": 1},
                        "nsfw_detected": {
                            "$sum": {"$cond": ["$detection_result.is_nsfw", 1, 0]}
                        },
                        "avg_confidence": {"$avg": "$detection_result.confidence"},
                        "content_types": {"$addToSet": "$content_type"},
                        "detection_methods": {
                            "$addToSet": "$detection_result.detection_methods"
                        },
                    }
                },
            ]

            cursor = await self.db.nsfw_detections.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            if result:
                stats = result[0]
                stats.pop("_id", None)
                return stats
            return {"total_detections": 0, "nsfw_detected": 0}

        except Exception as e:
            LOGGER.error(f"Error getting NSFW detection stats: {e}")
            return {}

    async def clean_old_nsfw_detections(self, days: int = 30):
        """Clean up old NSFW detection records"""
        if self._return:
            return 0

        try:
            cutoff_time = get_time() - (days * 86400)

            result = await self.db.nsfw_detections.delete_many(
                {"bot_id": TgClient.ID, "timestamp": {"$lt": cutoff_time}}
            )

            LOGGER.info(f"Cleaned {result.deleted_count} old NSFW detection records")
            return result.deleted_count

        except Exception as e:
            LOGGER.error(f"Error cleaning old NSFW detection records: {e}")
            return 0

    async def update_user_nsfw_behavior(
        self, user_id: int, nsfw_detected: bool, confidence: float
    ):
        """Track user NSFW behavior patterns"""
        if self._return:
            return

        try:
            current_time = get_time()

            # Update user behavior tracking
            update_data = {
                "$inc": {
                    "nsfw_total_checks": 1,
                    "nsfw_detected_count": 1 if nsfw_detected else 0,
                },
                "$set": {
                    "nsfw_last_check": current_time,
                    "nsfw_last_confidence": confidence,
                },
                "$push": {
                    "nsfw_recent_detections": {
                        "$each": [
                            {
                                "timestamp": current_time,
                                "detected": nsfw_detected,
                                "confidence": confidence,
                            }
                        ],
                        "$slice": -50,  # Keep only last 50 detections
                    }
                },
            }

            await self.db.users.update_one(
                {"_id": user_id}, update_data, upsert=True
            )

        except Exception as e:
            LOGGER.error(f"Error updating user NSFW behavior for {user_id}: {e}")

    async def _cleanup_invalid_config_keys(self):
        """Dynamically remove invalid/deprecated configuration keys from database"""
        try:
            if not await self.ensure_connection():
                return

            # Import Config class to get valid configuration keys
            from bot.core.config_manager import Config

            # Get all valid configuration keys from the Config class
            valid_config_keys = set(Config.__annotations__.keys())

            # Get all keys from runtime config
            runtime_config = await self.db.settings.config.find_one(
                {"_id": TgClient.ID}, {"_id": 0}
            )

            # Get all keys from deploy config
            deploy_config = await self.db.settings.deployConfig.find_one(
                {"_id": TgClient.ID}, {"_id": 0}
            )

            # Find deprecated keys (keys that exist in database but not in Config class)
            deprecated_keys_runtime = []
            deprecated_keys_deploy = []

            if runtime_config:
                for key in runtime_config:
                    # Skip internal keys (starting with _) and only check config keys
                    if not key.startswith("_") and key not in valid_config_keys:
                        deprecated_keys_runtime.append(key)

            if deploy_config:
                for key in deploy_config:
                    # Skip internal keys (starting with _) and only check config keys
                    if not key.startswith("_") and key not in valid_config_keys:
                        deprecated_keys_deploy.append(key)

            # Combine all deprecated keys for logging
            all_deprecated_keys = []
            if deprecated_keys_runtime:
                all_deprecated_keys.extend(
                    [f"{key} (runtime config)" for key in deprecated_keys_runtime]
                )
            if deprecated_keys_deploy:
                all_deprecated_keys.extend(
                    [f"{key} (deploy config)" for key in deprecated_keys_deploy]
                )

            # Show warning only when deprecated keys are found
            if all_deprecated_keys:
                LOGGER.warning(
                    f"Found deprecated configuration keys: {', '.join(all_deprecated_keys)}. "
                    f"These keys are no longer valid and will be removed from database."
                )

            # Track if any keys were actually cleaned up
            keys_actually_removed = False

            # Remove deprecated keys from runtime config
            if deprecated_keys_runtime:
                result = await self.db.settings.config.update_one(
                    {"_id": TgClient.ID},
                    {"$unset": dict.fromkeys(deprecated_keys_runtime, "")},
                )
                if result.modified_count > 0:
                    keys_actually_removed = True
                    LOGGER.info(
                        f"✅ Cleaned up {len(deprecated_keys_runtime)} deprecated configuration keys from runtime config"
                    )

            # Remove deprecated keys from deploy config
            if deprecated_keys_deploy:
                result = await self.db.settings.deployConfig.update_one(
                    {"_id": TgClient.ID},
                    {"$unset": dict.fromkeys(deprecated_keys_deploy, "")},
                )
                if result.modified_count > 0:
                    keys_actually_removed = True
                    LOGGER.info(
                        f"✅ Cleaned up {len(deprecated_keys_deploy)} deprecated configuration keys from deploy config"
                    )

            # If we found and cleaned up deprecated keys, log completion
            if all_deprecated_keys and keys_actually_removed:
                LOGGER.info(
                    "🧹 Database cleanup completed. All deprecated configuration keys have been permanently removed."
                )

        except Exception as e:
            LOGGER.error(f"Error cleaning up invalid configuration keys: {e}")

    async def _initialize_schema(self):
        """Initialize database schema - minimal version after cleanup"""
        try:
            # Basic schema initialization without media library functionality
            await self._cleanup_invalid_config_keys()
            LOGGER.info("Database schema initialized successfully")
        except Exception as e:
            LOGGER.error(f"Error initializing database schema: {e}")


class DatabaseManager(DbManager):
    def __init__(self):
        super().__init__()
        self._heartbeat_task = None

    async def start_heartbeat(self):
        """Start a background task to periodically check the database connection."""
        if self._heartbeat_task is not None:
            return

        # Define the heartbeat coroutine
        async def heartbeat():
            while True:
                try:
                    # Check if database is still available and not closed
                    if (
                        Config.DATABASE_URL
                        and not self._return
                        and self._conn is not None
                    ):
                        await self.ensure_connection()
                    await asyncio.sleep(60)  # Check every minute
                except asyncio.CancelledError:
                    LOGGER.debug("Database heartbeat task cancelled")
                    break
                except Exception as e:
                    # Check if this is a database closed error during shutdown
                    if (
                        "closed database" in str(e).lower()
                        or "connection closed" in str(e).lower()
                    ):
                        LOGGER.debug(
                            f"Database connection closed during heartbeat (expected during shutdown): {e}"
                        )
                        break
                    LOGGER.error(f"Error in database heartbeat: {e}")
                    await asyncio.sleep(30)  # Shorter interval on error

        # Start the heartbeat task
        self._heartbeat_task = asyncio.create_task(heartbeat())
        LOGGER.info("Database heartbeat task started")

    async def stop_heartbeat(self):
        """Stop the heartbeat task."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
            LOGGER.info("Database heartbeat task stopped")

    # File2Link Database Methods
    async def store_stream_file(self, file_data: dict):
        """Store file metadata for streaming"""
        if self._return:
            return False

        try:
            file_data.update({"bot_id": TgClient.ID, "created_at": time.time()})

            # Use upsert to avoid duplicates
            await self.db.stream_files.update_one(
                {
                    "message_id": file_data["message_id"],
                    "file_hash": file_data["file_hash"],
                },
                {"$set": file_data},
                upsert=True,
            )
            return True
        except Exception as e:
            LOGGER.error(f"Error storing stream file: {e}")
            return False

    async def get_stream_file(self, hash_id: str, message_id: int):
        """Retrieve file metadata for streaming"""
        if self._return:
            return None

        try:
            return await self.db.stream_files.find_one(
                {
                    "file_hash": hash_id,
                    "message_id": message_id,
                    "bot_id": TgClient.ID,
                }
            )
        except Exception as e:
            LOGGER.error(f"Error getting stream file: {e}")
            return None

    async def get_stream_stats(self):
        """Get File2Link streaming statistics"""
        if self._return:
            return {}

        try:
            total_files = await self.db.stream_files.count_documents(
                {"bot_id": TgClient.ID}
            )

            # Get files from last 7 days
            week_ago = time.time() - (7 * 24 * 60 * 60)
            recent_files = await self.db.stream_files.count_documents(
                {"bot_id": TgClient.ID, "created_at": {"$gte": week_ago}}
            )

            return {
                "total_files": total_files,
                "recent_files": recent_files,
                "storage_channel": Config.FILE2LINK_BIN_CHANNEL
                or Config.BIN_CHANNEL,
            }
        except Exception as e:
            LOGGER.error(f"Error getting stream stats: {e}")
            return {}

    async def cleanup_expired_stream_files(self):
        """Clean up expired file records"""
        if self._return:
            return False

        try:
            # Clean up files older than 30 days
            cutoff_time = time.time() - (30 * 24 * 60 * 60)
            await self.db.stream_files.delete_many(
                {"created_at": {"$lt": cutoff_time}}
            )

            return True
        except Exception as e:
            LOGGER.error(f"Error cleaning up expired files: {e}")
            return False


database = DatabaseManager()


# UNIFIED DATABASE ACCESS FUNCTION
async def ensure_database_and_config():
    """
    Unified database access function for all modules
    Returns the shared database instance after ensuring connection
    """
    try:
        if not Config.DATABASE_URL:
            LOGGER.warning("Database URL not configured")
            return None

        # Ensure database connection
        if not await database.ensure_connection():
            LOGGER.error("Failed to establish database connection")
            return None

        return database

    except Exception as e:
        LOGGER.error(f"Error in unified database access: {e}")
        return None


# Export the variables for external use
__all__ = [
    "USING_MOTOR",
    "AsyncMongoClient",
    "database",
    "ensure_database_and_config",
]
