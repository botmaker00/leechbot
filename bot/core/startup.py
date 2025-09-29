from asyncio import (
    create_subprocess_exec,
    create_subprocess_shell,
    create_task,
    sleep,
)
from os import environ
from time import time

import aiohttp
from aiofiles import open as aiopen
from aioshutil import rmtree  # type: ignore

from bot import (
    LOGGER,
    aria2_options,
    auth_chats,
    drives_ids,
    drives_names,
    excluded_extensions,
    index_urls,
    nzb_options,
    qbit_options,
    rss_dict,
    sabnzbd_client,
    shorteners_list,
    user_data,
)

# Use compatibility layer for aiofiles
from bot.helper.ext_utils.aiofiles_compat import aiopath, makedirs, remove
from bot.helper.ext_utils.db_handler import database

from .aeon_client import TgClient
from .config_manager import Config
from .torrent_manager import TorrentManager


async def start_web_server_early():
    """Start web server early for Heroku PORT binding"""
    from os import environ

    # First, kill any running web server processes regardless of configuration
    try:
        LOGGER.info("Killing any existing web server processes...")
        await (await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")).wait()
    except Exception as e:
        LOGGER.error(f"Error killing web server processes: {e}")

    # Check if web server should be started (BASE_URL_PORT = 0 means disabled)
    if Config.BASE_URL_PORT == 0:
        LOGGER.info("Web server is disabled (BASE_URL_PORT = 0)")
    else:
        # Use Config.BASE_URL_PORT instead of environment variable
        # Explicitly convert to string to avoid any type issues
        PORT = environ.get("PORT") or str(Config.BASE_URL_PORT) or "80"
        LOGGER.info(
            f"Starting web server early on port {PORT} for Heroku compatibility"
        )
        await create_subprocess_shell(
            f"gunicorn -k uvicorn.workers.UvicornWorker -w 1 web.wserver:app --bind 0.0.0.0:{PORT}",
        )


async def update_qb_options():
    # Check if qBittorrent is available before trying to update options
    if TorrentManager.qbittorrent is None:
        from bot import LOGGER

        LOGGER.warning("qBittorrent is not available - skipping options update")
        return

    try:
        # Check if qBittorrent client is available
        if TorrentManager.qbittorrent is None:
            from bot import LOGGER

            LOGGER.warning("qBittorrent is not available - skipping options update")
            return

        if not qbit_options:
            opt = await TorrentManager.qbittorrent.app.preferences()
            qbit_options.update(opt)
            del qbit_options["listen_port"]
            for k in list(qbit_options.keys()):
                if k.startswith("rss"):
                    del qbit_options[k]
            # Set username to 'admin' and password to LOGIN_PASS (or 'admin' if not set)
            username = "admin"
            password = Config.LOGIN_PASS or "admin"
            qbit_options["web_ui_username"] = username
            qbit_options["web_ui_password"] = password
            await TorrentManager.qbittorrent.app.set_preferences(
                {"web_ui_username": username, "web_ui_password": password},
            )
        else:
            await TorrentManager.qbittorrent.app.set_preferences(qbit_options)
    except Exception as e:
        from bot import LOGGER

        LOGGER.error(f"Failed to update qBittorrent options: {e}")


async def update_aria2_options():
    if not aria2_options:
        op = await TorrentManager.aria2.getGlobalOption()
        aria2_options.update(op)
    else:
        await TorrentManager.aria2.changeGlobalOption(aria2_options)


async def update_nzb_options():
    no = (await sabnzbd_client.get_config())["config"]["misc"]
    nzb_options.update(no)


async def load_zotify_credentials_from_db():
    """Load Zotify credentials from database and recreate credentials file"""
    try:
        from bot import LOGGER
        from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import (
            zotify_config,
        )

        # Check if database is available
        if database.db is None:
            return

        # Look for any user with Zotify credentials (prioritize owner)
        owner_id = getattr(Config, "OWNER_ID", None)
        user_with_creds = None

        if owner_id and owner_id != 0:
            # Check owner first
            owner_data = await database.db.users.find_one({"_id": owner_id})
            if owner_data and "ZOTIFY_CREDENTIALS" in owner_data:
                user_with_creds = owner_data

        # If owner doesn't have credentials, check other users
        if not user_with_creds:
            user_data = await database.db.users.find_one(
                {"ZOTIFY_CREDENTIALS": {"$exists": True}}
            )
            if user_data:
                user_with_creds = user_data

        # If we found credentials, recreate the file
        if user_with_creds and "ZOTIFY_CREDENTIALS" in user_with_creds:
            credentials = user_with_creds["ZOTIFY_CREDENTIALS"]
            success = zotify_config.save_credentials_to_file(credentials)
            if not success:
                LOGGER.error("Failed to restore Zotify credentials from database")

    except Exception as e:
        LOGGER.error(f"Error loading Zotify credentials from database: {e}")


async def load_settings():
    from bot import LOGGER

    if not Config.DATABASE_URL:
        return
    for p in ["thumbnails", "tokens", "rclone", "cookies"]:
        if await aiopath.exists(p):
            await rmtree(p, ignore_errors=True)
    await database.connect()

    # Shared configuration will be written after database config is loaded

    # Clean up invalid configuration keys BEFORE loading any config
    await database._cleanup_invalid_config_keys()

    # Start the database heartbeat task to keep the connection alive
    await database.start_heartbeat()

    if database.db is not None:
        # Process any pending message deletions
        await process_pending_deletions()
    else:
        return

    BOT_ID = Config.BOT_TOKEN.split(":", 1)[0]
    current_deploy_config = Config.get_all()
    old_deploy_config = await database.db.settings.deployConfig.find_one(
        {"_id": BOT_ID},
        {"_id": 0},
    )

    if old_deploy_config is None:
        # First time setup - create both deploy and runtime configs from config.py
        from bot.core.config_manager import Config as ConfigClass

        valid_config_keys = set(ConfigClass.__annotations__.keys())

        # Filter out invalid keys from current config
        filtered_config = {
            k: v for k, v in current_deploy_config.items() if k in valid_config_keys
        }

        # Create deploy config (source of truth for config.py)
        await database.db.settings.deployConfig.replace_one(
            {"_id": BOT_ID},
            filtered_config,
            upsert=True,
        )

        # Create runtime config (initially same as deploy config)
        await database.db.settings.config.replace_one(
            {"_id": BOT_ID},
            filtered_config,
            upsert=True,
        )

        LOGGER.info(
            "First time setup - created both deploy and runtime configs from config.py"
        )
    else:
        # Not first time - check if config.py has changed
        from bot.core.config_manager import Config as ConfigClass

        valid_config_keys = set(ConfigClass.__annotations__.keys())

        # Compare current config.py vs stored deploy config (source of truth)
        old_deploy_content = {
            k: v for k, v in old_deploy_config.items() if k in valid_config_keys
        }
        current_deploy_content = {
            k: v for k, v in current_deploy_config.items() if k in valid_config_keys
        }

        # Simple comparison - has config.py actually changed?
        config_py_changed = old_deploy_content != current_deploy_content

        if config_py_changed:
            # config.py has changed - update BOTH deploy and runtime configs
            LOGGER.info(
                "Config.py changes detected - updating both deploy and runtime configs"
            )

            # Filter new config.py values
            filtered_deploy_config = {
                k: v
                for k, v in current_deploy_config.items()
                if k in valid_config_keys
            }

            # Step 1: Update deploy config with new config.py values
            await database.db.settings.deployConfig.replace_one(
                {"_id": BOT_ID},
                filtered_deploy_config,
                upsert=True,
            )

            # Step 2: Update runtime config with new config.py values (override user changes)
            await database.db.settings.config.replace_one(
                {"_id": BOT_ID},
                filtered_deploy_config,
                upsert=True,
            )

            LOGGER.info(
                "Both deploy and runtime configs updated with new config.py values"
            )
        else:
            # No changes in config.py - keep both configs unchanged
            LOGGER.info(
                "No changes detected in config.py - preserving existing configs"
            )

        # Re-fetch runtime config after cleanup to ensure deprecated keys are gone
        runtime_config = await database.db.settings.config.find_one(
            {"_id": BOT_ID},
            {"_id": 0},
        )

        # FORCED CLEANUP: Remove any invalid keys that still exist in runtime config
        if runtime_config:
            from bot.core.config_manager import Config as ConfigClass

            valid_config_keys = set(ConfigClass.__annotations__.keys())

            # Find invalid keys
            invalid_keys_found = [
                k
                for k in runtime_config
                if not k.startswith("_") and k not in valid_config_keys
            ]

            if invalid_keys_found:
                LOGGER.warning(
                    f"🧹 FORCED CLEANUP: Removing persistent invalid keys: {invalid_keys_found}"
                )

                # Remove invalid keys from database immediately
                await database.db.settings.config.update_one(
                    {"_id": BOT_ID},
                    {"$unset": dict.fromkeys(invalid_keys_found, "")},
                )

                # Re-fetch the cleaned config
                runtime_config = await database.db.settings.config.find_one(
                    {"_id": BOT_ID},
                    {"_id": 0},
                )

        if runtime_config:
            # Filter out timestamp metadata before loading into Config class
            config_values_only = {
                k: v for k, v in runtime_config.items() if not k.startswith("_")
            }

            # After forced cleanup, the config should be clean - load it directly
            from bot.core.config_manager import Config as ConfigClass

            valid_config_keys = set(ConfigClass.__annotations__.keys())

            # Filter out any keys that are not valid configuration keys (should be none after forced cleanup)
            filtered_config = {
                k: v for k, v in config_values_only.items() if k in valid_config_keys
            }

            # Check if there are still any invalid keys (this should not happen after forced cleanup)
            invalid_keys = set(config_values_only.keys()) - valid_config_keys
            if invalid_keys:
                LOGGER.error(
                    f"❌ CRITICAL: Invalid keys still found after forced cleanup: {', '.join(invalid_keys)}"
                )
                LOGGER.error(
                    "This indicates a serious issue with the cleanup process!"
                )

            Config.load_dict(filtered_config)

            # Warm the configuration cache for better performance
            from bot.core.config_manager import warm_config_cache

            warm_config_cache()

            # Final cleanup: Remove any invalid keys that might have been re-added during sync
            await database._cleanup_invalid_config_keys()

    # Write shared configuration for web server process AFTER database config is loaded
    try:
        import json
        import os
        import tempfile

        # Create a shared config file for web server process
        shared_config = {
            "DATABASE_URL": Config.DATABASE_URL,
            "BOT_TOKEN": Config.BOT_TOKEN,
            "TG_CLIENT_ID": getattr(TgClient, "ID", None),
            "HELPER_TOKENS": getattr(Config, "HELPER_TOKENS", ""),
            "TELEGRAM_API": getattr(Config, "TELEGRAM_API", None),
            "TELEGRAM_HASH": getattr(Config, "TELEGRAM_HASH", None),
            "LOGIN_PASS": getattr(Config, "LOGIN_PASS", ""),
            # File2Link configurations
            "FILE2LINK_ENABLED": getattr(Config, "FILE2LINK_ENABLED", True),
            "FILE2LINK_BIN_CHANNEL": getattr(Config, "FILE2LINK_BIN_CHANNEL", 0),
            "FILE2LINK_BASE_URL": getattr(Config, "FILE2LINK_BASE_URL", ""),
            "FILE2LINK_ALLOWED_TYPES": getattr(
                Config,
                "FILE2LINK_ALLOWED_TYPES",
                "video,audio,document,photo,animation,voice,video_note",
            ),
            # Base URL for web server
            "BASE_URL": getattr(Config, "BASE_URL", ""),
            "BASE_URL_PORT": getattr(Config, "BASE_URL_PORT", 80),
        }

        # Write to a temporary file that web server can read
        config_file_path = os.path.join(
            tempfile.gettempdir(), "aimleechbot_shared_config.json"
        )
        with open(config_file_path, "w") as f:
            json.dump(shared_config, f)

    except Exception as e:
        LOGGER.warning(f"Failed to write shared configuration: {e}")

    if pf_dict := await database.db.settings.files.find_one(
        {"_id": BOT_ID},
        {"_id": 0},
    ):
        for key, value in pf_dict.items():
            if value:
                file_ = key.replace("__", ".")
                async with aiopen(file_, "wb+") as f:
                    await f.write(value)

    if a2c_options := await database.db.settings.aria2c.find_one(
        {"_id": BOT_ID},
        {"_id": 0},
    ):
        aria2_options.update(a2c_options)

    if qbit_opt := await database.db.settings.qbittorrent.find_one(
        {"_id": BOT_ID},
        {"_id": 0},
    ):
        qbit_options.update(qbit_opt)

    if nzb_opt := await database.db.settings.nzb.find_one(
        {"_id": BOT_ID},
        {"_id": 0},
    ):
        if await aiopath.exists("sabnzbd/SABnzbd.ini.bak"):
            await remove("sabnzbd/SABnzbd.ini.bak")
        ((key, value),) = nzb_opt.items()
        file_ = key.replace("__", ".")
        async with aiopen(f"sabnzbd/{file_}", "wb+") as f:
            await f.write(value)

    # Load Zotify credentials from database if available (MOVED OUTSIDE USER CHECK)
    try:
        await load_zotify_credentials_from_db()
    except Exception as e:
        LOGGER.error(f"Failed to restore Zotify credentials: {e}")

    # Check if there are any users in the database
    user_count = await database.db.users.count_documents({})
    LOGGER.info(f"Found {user_count} users in database during startup")

    if await database.db.users.find_one():
        LOGGER.info("Loading user data from database...")
        for p in ["thumbnails", "tokens", "rclone", "cookies"]:
            if not await aiopath.exists(p):
                await makedirs(p)

        # Set secure permissions for cookies directory
        if await aiopath.exists("cookies"):
            await create_subprocess_exec("chmod", "700", "cookies")

        rows = database.db.users.find({})
        async for row in rows:
            uid = row["_id"]
            del row["_id"]

            thumb_path = f"thumbnails/{uid}.jpg"
            rclone_config_path = f"rclone/{uid}.conf"
            token_path = f"tokens/{uid}.pickle"
            youtube_token_path = f"tokens/{uid}_youtube.pickle"
            if row.get("THUMBNAIL"):
                async with aiopen(thumb_path, "wb+") as f:
                    await f.write(row["THUMBNAIL"])
                row["THUMBNAIL"] = thumb_path
            if row.get("RCLONE_CONFIG"):
                async with aiopen(rclone_config_path, "wb+") as f:
                    await f.write(row["RCLONE_CONFIG"])
                row["RCLONE_CONFIG"] = rclone_config_path
            if row.get("TOKEN_PICKLE"):
                async with aiopen(token_path, "wb+") as f:
                    await f.write(row["TOKEN_PICKLE"])
                row["TOKEN_PICKLE"] = token_path
            # Load YouTube token pickle if available
            if row.get("YOUTUBE_TOKEN_PICKLE"):
                try:
                    async with aiopen(youtube_token_path, "wb+") as f:
                        await f.write(row["YOUTUBE_TOKEN_PICKLE"])
                    row["YOUTUBE_TOKEN_PICKLE"] = youtube_token_path
                except Exception as e:
                    LOGGER.error(
                        f"Failed to write YouTube token for user {uid}: {e}"
                    )
                    # Remove corrupted token data from user data
                    row.pop("YOUTUBE_TOKEN_PICKLE", None)
            # Load user cookies if available
            cookies_path = f"cookies/{uid}.txt"
            if row.get("USER_COOKIES"):
                async with aiopen(cookies_path, "wb+") as f:
                    await f.write(row["USER_COOKIES"])
                row["USER_COOKIES"] = cookies_path
                # Set secure permissions for individual cookie files
                await create_subprocess_exec("chmod", "600", cookies_path)
                # Silently load user cookies without logging
            user_data[uid] = row

        LOGGER.info("Users data has been imported from Database")

    # CRITICAL FIX: Always ensure OWNER_ID and SUDO_USERS are authorized,
    # even for new deployments with empty database
    from bot.helper.ext_utils.bot_utils import ensure_authorized_users

    await ensure_authorized_users()

    # Force update streamrip config after settings are loaded
    try:
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            force_streamrip_config_update,
        )

        await force_streamrip_config_update()
    except Exception as e:
        LOGGER.error(f"Failed to update streamrip config after settings load: {e}")

    if await database.db.rss[BOT_ID].find_one():
        rows = database.db.rss[BOT_ID].find({})
        async for row in rows:
            user_id = row["_id"]
            del row["_id"]
            rss_dict[user_id] = row
        LOGGER.info("Rss data has been imported from Database.")


async def save_settings():
    if database.db is None:
        return

    # Check if runtime config already exists (meaning it was updated during startup)
    existing_runtime_config = await database.db.settings.config.find_one(
        {"_id": TgClient.ID},
        {"_id": 0},
    )

    # Only save if runtime config doesn't exist (first time setup)
    # If it exists, it means load_settings() already updated it with the correct values
    if existing_runtime_config is None:
        config_dict = Config.get_all()
        # Add initial runtime timestamp for first-time setup
        config_dict["_runtime_timestamp"] = time()
        await database.db.settings.config.replace_one(
            {"_id": TgClient.ID},
            config_dict,
            upsert=True,
        )
    if await database.db.settings.aria2c.find_one({"_id": TgClient.ID}) is None:
        await database.db.settings.aria2c.update_one(
            {"_id": TgClient.ID},
            {"$set": aria2_options},
            upsert=True,
        )
    if await database.db.settings.qbittorrent.find_one({"_id": TgClient.ID}) is None:
        await database.save_qbit_settings()
    if await database.db.settings.nzb.find_one({"_id": TgClient.ID}) is None:
        async with aiopen("sabnzbd/SABnzbd.ini", "rb+") as pf:
            nzb_conf = await pf.read()
        await database.db.settings.nzb.update_one(
            {"_id": TgClient.ID},
            {"$set": {"SABnzbd__ini": nzb_conf}},
            upsert=True,
        )


async def update_variables():
    # Smart default split size configuration based on client capabilities
    # IMPORTANT: Splitting is ALWAYS enabled - never allow LEECH_SPLIT_SIZE = 0

    # Determine client type and appropriate split size defaults
    # Note: This is calculated before Config.USER_TRANSMISSION might be auto-disabled
    # We'll recalculate after the auto-disable logic runs
    owner_user_transmission = bool(Config.USER_TRANSMISSION and TgClient.user)

    if owner_user_transmission:
        if TgClient.IS_PREMIUM_USER:
            # Premium user client - use 3.91GB default (safe for 4GB limit)
            smart_default_split_size = int(3.91 * 1024 * 1024 * 1024)  # 3.91GB
            max_allowed_split_size = int(3.91 * 1024 * 1024 * 1024)  # 3.91GB max
        else:
            # Non-premium user client - use 1.95GB default (safe for 2GB limit)
            smart_default_split_size = int(1.95 * 1024 * 1024 * 1024)  # 1.95GB
            max_allowed_split_size = int(1.95 * 1024 * 1024 * 1024)  # 1.95GB max
    else:
        # Bot client only - use 1.95GB default (safe for 2GB limit)
        smart_default_split_size = int(1.95 * 1024 * 1024 * 1024)  # 1.95GB
        max_allowed_split_size = int(1.95 * 1024 * 1024 * 1024)  # 1.95GB max

    # Set smart default if not configured or if set to 0 (disabled)
    if (
        not Config.LEECH_SPLIT_SIZE  # Not set (0 or None)
        or Config.LEECH_SPLIT_SIZE <= 0  # Explicitly disabled (not allowed)
        or max_allowed_split_size < Config.LEECH_SPLIT_SIZE  # Exceeds client limit
        or Config.LEECH_SPLIT_SIZE == 2097152000  # Old default value
    ):
        Config.LEECH_SPLIT_SIZE = smart_default_split_size
    # Auto-disable USER_TRANSMISSION only if user session is not available
    # USER_TRANSMISSION works with both premium and non-premium sessions
    Config.USER_TRANSMISSION = bool(
        Config.USER_TRANSMISSION
        and TgClient.user is not None  # Only requires user session to exist
    )

    # HYBRID_LEECH requires USER_TRANSMISSION to be enabled and user session to exist
    # It works with both premium and non-premium sessions (just uses different limits)
    Config.HYBRID_LEECH = bool(
        Config.HYBRID_LEECH
        and Config.USER_TRANSMISSION  # Requires user transmission to be enabled
        and TgClient.user is not None  # Requires user session to exist
    )

    # Recalculate split size defaults after USER_TRANSMISSION may have been auto-disabled
    # This ensures we use the correct client type for split size calculation
    final_owner_user_transmission = bool(Config.USER_TRANSMISSION and TgClient.user)

    # If USER_TRANSMISSION was auto-disabled, we need to recalculate split size
    if owner_user_transmission != final_owner_user_transmission:
        LOGGER.info(
            "🔄 Recalculating split size defaults after USER_TRANSMISSION auto-disable..."
        )

        if final_owner_user_transmission:
            if TgClient.IS_PREMIUM_USER:
                # Premium user client - use 3.91GB default (safe for 4GB limit)
                new_smart_default = int(3.91 * 1024 * 1024 * 1024)  # 3.91GB
                new_max_allowed = int(3.91 * 1024 * 1024 * 1024)  # 3.91GB max
                new_client_info = "user client (premium session)"
            else:
                # Non-premium user client - use 1.95GB default (safe for 2GB limit)
                new_smart_default = int(1.95 * 1024 * 1024 * 1024)  # 1.95GB
                new_max_allowed = int(1.95 * 1024 * 1024 * 1024)  # 1.95GB max
                new_client_info = "user client (non-premium session)"
        else:
            # Bot client only - use 1.95GB default (safe for 2GB limit)
            new_smart_default = int(1.95 * 1024 * 1024 * 1024)  # 1.95GB
            new_max_allowed = int(1.95 * 1024 * 1024 * 1024)  # 1.95GB max
            new_client_info = "bot client"

        # Update split size if it was set to the old default or exceeds new limit
        if (
            smart_default_split_size
            == Config.LEECH_SPLIT_SIZE  # Was using old default
            or new_max_allowed < Config.LEECH_SPLIT_SIZE  # Exceeds new limit
        ):
            old_split_size = Config.LEECH_SPLIT_SIZE
            Config.LEECH_SPLIT_SIZE = new_smart_default

            LOGGER.info(
                f"📏 Updated LEECH_SPLIT_SIZE from {old_split_size / (1024**3):.2f}GB to "
                f"{Config.LEECH_SPLIT_SIZE / (1024**3):.2f}GB ({new_client_info})"
            )

    # Migrate from old config if needed
    if (
        hasattr(Config, "MUSIC_SEARCH_CHATS")
        and Config.MUSIC_SEARCH_CHATS
        and not Config.MEDIA_SEARCH_CHATS
    ):
        Config.MEDIA_SEARCH_CHATS = Config.MUSIC_SEARCH_CHATS

    # User authorization will be handled after database loading in the main startup sequence

    if Config.AUTHORIZED_CHATS:
        aid = Config.AUTHORIZED_CHATS.split()
        for id_ in aid:
            chat_id, *thread_ids = id_.split("|")
            chat_id = int(chat_id.strip())
            if thread_ids:
                thread_ids = [int(x.strip()) for x in thread_ids]
                auth_chats[chat_id] = thread_ids
            else:
                auth_chats[chat_id] = []

    if Config.EXCLUDED_EXTENSIONS:
        fx = Config.EXCLUDED_EXTENSIONS.split()
        for x in fx:
            x = x.lstrip(".")
            excluded_extensions.append(x.strip().lower())

    if Config.GDRIVE_ID:
        drives_names.append("Main")
        drives_ids.append(Config.GDRIVE_ID)
        index_urls.append(Config.INDEX_URL)

    if await aiopath.exists("list_drives.txt"):
        async with aiopen("list_drives.txt", "r+") as f:
            lines = await f.readlines()
            for line in lines:
                temp = line.split()
                drives_ids.append(temp[1])
                drives_names.append(temp[0].replace("_", " "))
                if len(temp) > 2:
                    index_urls.append(temp[2].strip("/"))
                else:
                    index_urls.append("")

    if Config.HEROKU_APP_NAME and Config.HEROKU_API_KEY:
        headers = {
            "Accept": "application/vnd.heroku+json; version=3",
            "Authorization": f"Bearer {Config.HEROKU_API_KEY}",
        }

        urls = [
            f"https://api.heroku.com/teams/apps/{Config.HEROKU_APP_NAME}",
            f"https://api.heroku.com/apps/{Config.HEROKU_APP_NAME}",
        ]

        async with aiohttp.ClientSession(headers=headers) as session:
            for url in urls:
                try:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        app_data = await response.json()
                        if web_url := app_data.get("web_url"):
                            # Ensure BASE_URL ends with '/' for proper URL generation
                            Config.set("BASE_URL", web_url.rstrip("/"))

                            # STREAM_BASE_URL auto-detection removed - streaming functionality disabled
                            return
                except Exception as e:
                    LOGGER.error(f"BASE_URL error: {e}")
                    continue


async def load_configurations():
    if not await aiopath.exists(".netrc"):
        async with aiopen(".netrc", "w"):
            pass
    await (
        await create_subprocess_shell(
            "chmod 600 .netrc && cp .netrc /root/.netrc && chmod +x aria-nox-nzb.sh && ./aria-nox-nzb.sh",
        )
    ).wait()

    # Check if web server is already running (for Heroku early start)
    web_server_already_running = False
    try:
        process = await create_subprocess_exec("pgrep", "-f", "gunicorn", stdout=-1)
        stdout, _ = await process.communicate()
        if stdout:
            web_server_already_running = True
            LOGGER.info("Web server already running (started early for Heroku)")
    except Exception as e:
        LOGGER.error(f"Error checking for existing gunicorn processes: {e}")

    if not web_server_already_running:
        # First, kill any running web server processes regardless of configuration
        try:
            LOGGER.info("Killing any existing web server processes...")
            await (
                await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
            ).wait()
        except Exception as e:
            LOGGER.error(f"Error killing web server processes: {e}")

        # Check if web server should be started (BASE_URL_PORT = 0 means disabled)
        if Config.BASE_URL_PORT == 0:
            LOGGER.info("Web server is disabled (BASE_URL_PORT = 0)")
            # Double-check to make sure no web server is running
            try:
                # Use pgrep to check if any gunicorn processes are still running
                process = await create_subprocess_exec(
                    "pgrep", "-f", "gunicorn", stdout=-1
                )
                stdout, _ = await process.communicate()
                if stdout:
                    LOGGER.warning(
                        "Gunicorn processes still detected, attempting to kill again..."
                    )
                    await (
                        await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
                    ).wait()
            except Exception as e:
                LOGGER.error(f"Error checking for gunicorn processes: {e}")
        else:
            # Use Config.BASE_URL_PORT instead of environment variable
            # Explicitly convert to string to avoid any type issues
            PORT = environ.get("PORT") or str(Config.BASE_URL_PORT) or "80"
            LOGGER.info(f"Starting web server on port {PORT}")
            await create_subprocess_shell(
                f"gunicorn -k uvicorn.workers.UvicornWorker -w 1 web.wserver:app --bind 0.0.0.0:{PORT}",
            )

    if await aiopath.exists("cfg.zip"):
        if await aiopath.exists("/JDownloader/cfg"):
            await rmtree("/JDownloader/cfg", ignore_errors=True)
        await (
            await create_subprocess_exec("7z", "x", "cfg.zip", "-o/JDownloader")
        ).wait()

    if await aiopath.exists("shorteners.txt"):
        async with aiopen("shorteners.txt") as f:
            lines = await f.readlines()
            for line in lines:
                temp = line.strip().split()
                if len(temp) == 2:
                    shorteners_list.append({"domain": temp[0], "api_key": temp[1]})

    if await aiopath.exists("accounts.zip"):
        if await aiopath.exists("accounts"):
            await rmtree("accounts")
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
        await (await create_subprocess_exec("chmod", "-R", "777", "accounts")).wait()
        await remove("accounts.zip")

    if not await aiopath.exists("accounts"):
        Config.USE_SERVICE_ACCOUNTS = False


async def process_pending_deletions():
    """Process messages that were scheduled for deletion"""
    from bot.core.config_manager import get_config_bool

    # Check if scheduled deletion is enabled
    if not get_config_bool("SCHEDULED_DELETION_ENABLED", True):
        return

    if database.db is None:
        LOGGER.info("Database is None, skipping pending deletions check")
        return

    # Check if TgClient.bot is initialized
    if not hasattr(TgClient, "bot") or TgClient.bot is None:
        # TgClient.bot not initialized yet, skipping pending deletions
        return

    # Check all scheduled deletions for debugging
    await database.get_all_scheduled_deletions()

    # Clean up old scheduled deletion entries once a day
    current_time = int(time())
    last_cleanup_time = getattr(process_pending_deletions, "last_cleanup_time", 0)
    if current_time - last_cleanup_time > 86400:  # 86400 seconds = 1 day
        await database.clean_old_scheduled_deletions(days=1)
        process_pending_deletions.last_cleanup_time = current_time

    pending_deletions = await database.get_pending_deletions()

    if not pending_deletions:
        return

    # Process each pending deletion individually
    success_count = 0
    fail_count = 0
    removed_from_db_count = 0

    for chat_id, msg_id, bot_id in pending_deletions:
        # Get the appropriate bot client
        bot_client = None
        if bot_id == TgClient.ID:
            bot_client = TgClient.bot
        elif hasattr(TgClient, "helper_bots") and bot_id in TgClient.helper_bots:
            bot_client = TgClient.helper_bots[bot_id]

        if bot_client is None:
            # Bot not found, skipping message
            fail_count += 1
            continue

        try:
            # Try to get the message first to verify it exists
            try:
                msg = await bot_client.get_messages(
                    chat_id=chat_id,
                    message_ids=int(msg_id),
                )

                if msg is None or getattr(msg, "empty", False):
                    # Message not found, removing from database
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                    continue

                # Message found, will attempt to delete
            except Exception:
                # Error getting message, skipping
                continue

            # Make sure message_id is an integer
            message_id_int = int(msg_id)
            await bot_client.delete_messages(
                chat_id=chat_id,
                message_ids=[message_id_int],  # Pass as a list with a single item
            )
            # Successfully deleted the message
            success_count += 1
            # Remove from database after successful deletion
            try:
                await database.remove_scheduled_deletion(chat_id, msg_id)
                removed_from_db_count += 1
            except Exception as e:
                LOGGER.error(
                    f"Error removing scheduled deletion after successful deletion: {e}"
                )
        except Exception as e:
            error_str = str(e)
            # Handle different types of errors appropriately
            if "MESSAGE_DELETE_FORBIDDEN" in error_str or "403" in error_str:
                # Cannot delete message due to permissions, remove from database
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for forbidden message: {e}"
                    )
            elif "MESSAGE_ID_INVALID" in error_str or "400" in error_str:
                # Message doesn't exist, remove from database
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for invalid message: {e}"
                    )
            elif (
                "CHANNEL_INVALID" in error_str
                or "CHAT_INVALID" in error_str
                or "USER_INVALID" in error_str
                or "PEER_ID_INVALID" in error_str
            ):
                # Chat is invalid, removing from database
                try:
                    await database.remove_scheduled_deletion(chat_id, msg_id)
                    removed_from_db_count += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error removing scheduled deletion for invalid chat: {e}"
                    )
            else:
                # Other errors count as failures - log for debugging
                LOGGER.warning(
                    f"Auto-deletion failed for message {msg_id} in chat {chat_id}: {error_str}"
                )
                fail_count += 1

    # Log summary with more context
    if success_count > 0 or fail_count > 0 or removed_from_db_count > 0:
        LOGGER.info(
            f"Auto-deletion results: {success_count} deleted, {fail_count} failed, {removed_from_db_count} removed from database"
        )
    else:
        LOGGER.info("No auto-deletions processed in this cycle")


async def scheduled_deletion_checker():
    from bot.core.config_manager import get_config_bool

    LOGGER.info("Optimized scheduled deletion checker started")
    while True:
        try:
            # Check if scheduled deletion is still enabled during runtime
            if not get_config_bool("SCHEDULED_DELETION_ENABLED", True):
                LOGGER.info(
                    "Scheduled deletion has been disabled via configuration - stopping checker"
                )
                break

            await process_pending_deletions()
        except Exception as e:
            LOGGER.error(f"Error in scheduled deletion checker: {e}")
        await sleep(
            900
        )  # Optimized: Check every 15 minutes to reduce resource usage

    LOGGER.info("Scheduled deletion checker stopped")


async def start_bot():
    # Check if scheduled deletion is enabled via configuration
    from bot.core.config_manager import get_config_bool

    if not get_config_bool("SCHEDULED_DELETION_ENABLED", True):
        LOGGER.info("Scheduled deletion is disabled via configuration")
        return

    # Only start the scheduled deletion checker after TgClient is initialized
    if hasattr(TgClient, "bot") and TgClient.bot is not None:
        LOGGER.info("Starting scheduled deletion checker")
        create_task(scheduled_deletion_checker())  # noqa: RUF006
    else:
        # Create a task to wait for TgClient.bot to be initialized and then start the checker
        create_task(wait_for_bot_and_start_checker())  # noqa: RUF006


async def wait_for_bot_and_start_checker():
    """Wait for TgClient.bot to be initialized and then start the scheduled deletion checker"""
    # Check if scheduled deletion is enabled via configuration
    from bot.core.config_manager import get_config_bool

    if not get_config_bool("SCHEDULED_DELETION_ENABLED", True):
        LOGGER.info(
            "Scheduled deletion is disabled via configuration - not starting checker"
        )
        return

    # Check immediately and then with short intervals
    # The bot initialization is a one-time event that happens during startup

    # Check a few times with short intervals
    for _ in range(10):  # Try 10 times
        if hasattr(TgClient, "bot") and TgClient.bot is not None:
            LOGGER.info(
                "TgClient.bot is now initialized, starting scheduled deletion checker",
            )
            create_task(scheduled_deletion_checker())  # noqa: RUF006
            return
        await sleep(5)  # Check every 5 seconds instead of 60

    # If we get here, the bot still isn't initialized after 5 minutes
