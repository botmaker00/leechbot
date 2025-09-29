from asyncio import create_task, sleep
from datetime import datetime, timedelta

from apscheduler.triggers.date import DateTrigger

from bot import LOGGER, bot_loop, scheduler
from bot.core.config_manager import Config

# Global variable to store the next restart time
next_restart_time = None


async def schedule_auto_restart():
    """Schedule the next auto-restart based on the configured interval"""
    global next_restart_time

    # If auto-restart is disabled, clear the next restart time and remove any scheduled jobs
    if not Config.AUTO_RESTART_ENABLED:
        next_restart_time = None
        try:
            scheduler.remove_job("auto_restart")
            LOGGER.info("Auto-restart is disabled, removed scheduled restart job")
        except Exception:
            LOGGER.info("Auto-restart is disabled")
        return

    # Calculate the next restart time with optimized minimum interval
    interval_hours = max(
        6, Config.AUTO_RESTART_INTERVAL
    )  # Increased minimum to 6 hours for better stability
    next_time = datetime.now() + timedelta(hours=interval_hours)
    next_restart_time = next_time

    # Log the next restart time
    LOGGER.info(
        f"Scheduled next auto-restart at {next_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    # Schedule the restart job
    scheduler.add_job(
        auto_restart,
        trigger=DateTrigger(run_date=next_time),
        id="auto_restart",
        name="Auto Restart",
        replace_existing=True,
    )


async def auto_restart():
    """Perform the auto-restart"""
    LOGGER.info("Auto-restart triggered")

    try:
        # Import here to avoid circular imports
        from bot.modules.restart import confirm_restart

        # Create a mock query object that confirm_restart can use
        class MockQuery:
            def __init__(self):
                self.data = "botrestart confirm"

                # Mock message object
                class MockMessage:
                    def __init__(self):
                        self.chat = MockChat()

                # Mock chat object
                class MockChat:
                    def __init__(self):
                        self.id = (
                            Config.OWNER_ID or 1
                        )  # Use owner ID or fallback to 1

                self.message = MockMessage()

            async def answer(self):
                pass

        # Call the restart function
        LOGGER.info("Calling confirm_restart for auto-restart")
        await confirm_restart(None, MockQuery())

        # If we get here, the restart might have failed
        LOGGER.warning(
            "Auto-restart didn't exit as expected, scheduling next restart"
        )
        await sleep(300)  # Wait 5 minutes
        create_task(schedule_auto_restart())
    except Exception as e:
        LOGGER.error(f"Error during auto-restart: {e!s}")
        # Try to reschedule in case of failure
        await sleep(300)  # Wait 5 minutes
        create_task(schedule_auto_restart())


def get_restart_time_remaining():
    """Get the remaining time until the next restart in a human-readable format"""
    if next_restart_time is None:
        return None

    # Only show the restart time if auto-restart is enabled
    if not Config.AUTO_RESTART_ENABLED:
        return None

    now = datetime.now()
    if next_restart_time <= now:
        return "Restarting soon..."

    # Calculate the time difference
    time_diff = next_restart_time - now

    # Format the time difference
    hours, remainder = divmod(time_diff.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if time_diff.days > 0:
        return f"{time_diff.days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


# Initialize the auto-restart scheduler
def init_auto_restart():
    """Initialize the auto-restart scheduler"""
    LOGGER.info("Initializing auto-restart scheduler")
    bot_loop.create_task(schedule_auto_restart())
