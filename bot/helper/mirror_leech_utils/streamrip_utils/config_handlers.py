"""
Streamrip configuration handlers for bot settings integration
"""

import contextlib

from bot import LOGGER
from bot.core.config_manager import Config


async def handle_streamrip_setting_change(setting_key: str, new_value) -> bool:
    """
    Handle changes to streamrip settings from bot settings
    This function is called whenever a streamrip setting is changed
    """
    try:
        LOGGER.info(f"Streamrip setting changed: {setting_key} = {new_value}")

        # Import the new config helper
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            streamrip_config,
        )

        # Update the config file from current bot settings
        success = await streamrip_config.update_config_from_bot_settings()

        if success:
            LOGGER.info(f"Updated streamrip config for setting: {setting_key}")
        else:
            LOGGER.error(
                f"Failed to update streamrip config for setting: {setting_key}"
            )

        return success

    except Exception as e:
        LOGGER.error(f"Error handling streamrip setting change: {e}")
        return False


async def handle_streamrip_config_upload(config_content: str) -> bool:
    """
    Handle upload of custom streamrip config file
    """
    try:
        LOGGER.info("Processing streamrip config upload")

        # Import the new config helper
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            streamrip_config,
        )

        # Upload and deploy the custom config
        success = await streamrip_config.upload_custom_config(config_content)

        if success:
            LOGGER.info("Successfully uploaded and deployed custom streamrip config")
        else:
            LOGGER.error("Failed to upload custom streamrip config")

        return success

    except Exception as e:
        LOGGER.error(f"Error handling streamrip config upload: {e}")
        return False


async def handle_streamrip_config_reset() -> bool:
    """
    Handle reset of streamrip config to default
    """
    try:
        LOGGER.info("Resetting streamrip config to default")

        # Import the new config helper
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            streamrip_config,
        )

        # Reset to default config
        success = await streamrip_config.reset_to_default_config()

        if success:
            LOGGER.info("Successfully reset streamrip config to default")
        else:
            LOGGER.error("Failed to reset streamrip config")

        return success

    except Exception as e:
        LOGGER.error(f"Error resetting streamrip config: {e}")
        return False


async def get_streamrip_config_content() -> str | None:
    """
    Get current streamrip config file content
    """
    try:
        # Import the new config helper
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            streamrip_config,
        )

        # Get current config content
        content = await streamrip_config.get_current_config_content()

        if content:
            LOGGER.info("Successfully retrieved streamrip config content")
        else:
            LOGGER.warning("No streamrip config content found")

        return content

    except Exception as e:
        LOGGER.error(f"Error getting streamrip config content: {e}")
        return None


async def get_streamrip_config_status() -> dict:
    """
    Get streamrip configuration status
    """
    try:
        # Import the new config helper
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            streamrip_config,
        )

        # Check if config file exists
        config_path = streamrip_config.get_config_file_path()
        config_exists = config_path.exists()

        # Get platform status
        platform_status = streamrip_config.get_platform_status()

        # Check if streamrip is initialized
        is_initialized = streamrip_config.is_initialized()

        status = {
            "config_file_exists": config_exists,
            "config_file_path": str(config_path),
            "is_initialized": is_initialized,
            "platform_status": platform_status,
            "streamrip_enabled": Config.STREAMRIP_ENABLED,
        }

        LOGGER.info("Retrieved streamrip config status")
        return status

    except Exception as e:
        LOGGER.error(f"Error getting streamrip config status: {e}")
        return {
            "config_file_exists": False,
            "config_file_path": "",
            "is_initialized": False,
            "platform_status": {},
            "streamrip_enabled": False,
            "error": str(e),
        }


async def validate_streamrip_config(config_content: str) -> tuple[bool, str]:
    """
    Validate streamrip config content
    Returns (is_valid, error_message)
    """
    try:
        # Import streamrip config class
        import os

        # Create temporary file to test config
        import tempfile

        from streamrip.config import Config as StreamripConfig

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        ) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            # Try to load the config
            test_config = StreamripConfig(temp_path)

            # Basic validation - check if required sections exist
            required_sections = ["downloads", "qobuz", "tidal", "deezer"]
            missing_sections = []

            for section in required_sections:
                if not hasattr(test_config, section):
                    missing_sections.append(section)

            if missing_sections:
                return (
                    False,
                    f"Missing required sections: {', '.join(missing_sections)}",
                )

            return True, "Config is valid"

        finally:
            # Clean up temp file
            with contextlib.suppress(Exception):
                os.unlink(temp_path)

    except Exception as e:
        return False, f"Invalid config: {e!s}"


async def get_streamrip_credentials_status() -> dict:
    """
    Get status of streamrip platform credentials
    """
    try:
        return {
            "qobuz": {
                "email": bool(Config.STREAMRIP_QOBUZ_EMAIL),
                "password": bool(Config.STREAMRIP_QOBUZ_PASSWORD),
                "app_id": bool(Config.STREAMRIP_QOBUZ_APP_ID),
                "secrets": bool(Config.STREAMRIP_QOBUZ_SECRETS),
                "enabled": Config.STREAMRIP_QOBUZ_ENABLED,
            },
            "tidal": {
                "access_token": bool(Config.STREAMRIP_TIDAL_ACCESS_TOKEN),
                "refresh_token": bool(Config.STREAMRIP_TIDAL_REFRESH_TOKEN),
                "user_id": bool(Config.STREAMRIP_TIDAL_USER_ID),
                "enabled": Config.STREAMRIP_TIDAL_ENABLED,
            },
            "deezer": {
                "arl": bool(Config.STREAMRIP_DEEZER_ARL),
                "enabled": Config.STREAMRIP_DEEZER_ENABLED,
            },
            "soundcloud": {
                "client_id": bool(Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID),
                "enabled": Config.STREAMRIP_SOUNDCLOUD_ENABLED,
            },
        }

    except Exception as e:
        LOGGER.error(f"Error getting credentials status: {e}")
        return {}


# Utility function to check if streamrip is properly configured
async def is_streamrip_properly_configured() -> tuple[bool, list[str]]:
    """
    Check if streamrip is properly configured
    Returns (is_configured, list_of_issues)
    """
    issues = []

    try:
        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            issues.append("Streamrip is disabled")
            return False, issues

        # Check if config file exists
        from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
            streamrip_config,
        )

        config_path = streamrip_config.get_config_file_path()

        if not config_path.exists():
            issues.append("Config file does not exist")

        # Check platform credentials
        credentials_status = await get_streamrip_credentials_status()

        # Check if at least one platform is properly configured
        configured_platforms = 0

        if credentials_status.get("qobuz", {}).get("enabled"):
            qobuz = credentials_status["qobuz"]
            if qobuz.get("email") and qobuz.get("password"):
                if qobuz.get("app_id") and qobuz.get("secrets"):
                    configured_platforms += 1
                else:
                    issues.append("Qobuz missing app_id or secrets")
            else:
                issues.append("Qobuz missing email or password")

        if credentials_status.get("tidal", {}).get("enabled"):
            tidal = credentials_status["tidal"]
            if tidal.get("access_token") and tidal.get("refresh_token"):
                configured_platforms += 1
            else:
                issues.append("Tidal missing access_token or refresh_token")

        if credentials_status.get("deezer", {}).get("enabled"):
            deezer = credentials_status["deezer"]
            if deezer.get("arl"):
                configured_platforms += 1
            else:
                issues.append("Deezer missing ARL")

        if credentials_status.get("soundcloud", {}).get("enabled"):
            configured_platforms += (
                1  # SoundCloud doesn't require credentials for basic use
            )

        if configured_platforms == 0:
            issues.append("No platforms are properly configured")

        return len(issues) == 0, issues

    except Exception as e:
        issues.append(f"Error checking configuration: {e!s}")
        return False, issues
