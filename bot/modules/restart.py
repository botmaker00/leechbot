from asyncio import create_subprocess_exec, create_task, gather
from os import execl as osexecl
from sys import executable

from aiofiles import open as aiopen

from bot import LOGGER, intervals, sabnzbd_client, scheduler
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.core.jdownloader_booter import jdownloader
from bot.core.torrent_manager import TorrentManager
from bot.helper.ext_utils.aiofiles_compat import aiopath, remove
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.files_utils import clean_all
from bot.helper.telegram_helper import button_build
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)


@new_task
async def restart_bot(_, message):
    await delete_message(message)  # Delete command message immediately
    buttons = button_build.ButtonMaker()
    buttons.data_button("Yes!", "botrestart confirm")
    buttons.data_button("Cancel", "botrestart cancel")
    button = buttons.build_menu(2)
    await send_message(
        message,
        "Are you sure you want to restart the bot ?!",
        button,
    )


async def send_incomplete_task_message(cid, msg_id, msg):
    try:
        # Check if TgClient.bot is available before attempting to send messages
        if not TgClient.bot:
            LOGGER.warning("TgClient.bot not available for incomplete task message")
            return

        if msg.startswith("Restarted Successfully!"):
            restart_msg = await TgClient.bot.edit_message_text(
                chat_id=cid,
                message_id=msg_id,
                text=msg,
                disable_web_page_preview=True,
            )
            await remove(".restartmsg")
            create_task(auto_delete_message(restart_msg, time=300))  # noqa: RUF006
        else:
            await TgClient.bot.send_message(
                chat_id=cid,
                text=msg,
                disable_web_page_preview=True,
                disable_notification=True,
            )
    except Exception as e:
        # Handle client not started errors gracefully
        if "Client has not been started yet" in str(e):
            LOGGER.warning(
                f"Client not started for incomplete task message. This is normal during restart: {e}"
            )
        else:
            LOGGER.error(e)


async def restart_notification():
    if await aiopath.isfile(".restartmsg"):
        async with aiopen(".restartmsg") as f:
            content = await f.read()
            chat_id, msg_id = map(int, content.splitlines())
    else:
        chat_id, msg_id = 0, 0

    if (
        Config.INCOMPLETE_TASK_NOTIFIER
        and Config.DATABASE_URL
        and (notifier_dict := await database.get_incomplete_tasks())
    ):
        for cid, data in notifier_dict.items():
            msg = "Restarted Successfully!" if cid == chat_id else "Bot Restarted!"
            for tag, links in data.items():
                msg += f"\n\n{tag}: "
                for index, link in enumerate(links, start=1):
                    msg += f" <a href='{link}'>{index}</a> |"
                    if len(msg.encode()) > 4000:
                        await send_incomplete_task_message(cid, msg_id, msg)
                        msg = ""
            if msg:
                await send_incomplete_task_message(cid, msg_id, msg)

    if await aiopath.isfile(".restartmsg"):
        try:
            # Check if TgClient.bot is available before attempting to send messages
            if not TgClient.bot:
                LOGGER.warning("TgClient.bot not available for restart notification")
                await remove(".restartmsg")
                return

            # Check if we have a valid message ID
            if msg_id > 0:
                restart_msg = await TgClient.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="Restarted Successfully!",
                )
                create_task(auto_delete_message(restart_msg, time=300))  # noqa: RUF006
            elif chat_id > 0:
                # If we don't have a valid message ID but have a chat ID, send a new message
                restart_msg = await TgClient.bot.send_message(
                    chat_id=chat_id,
                    text="Restarted Successfully!",
                )
                create_task(auto_delete_message(restart_msg, time=300))  # noqa: RUF006
        except Exception as e:
            LOGGER.error(f"Error in restart notification: {e!s}")
            # Don't try to auto-delete a message that might not exist
        await remove(".restartmsg")


@new_task
async def confirm_restart(_, query):
    await query.answer()
    data = query.data.split()
    message = query.message
    await delete_message(message)
    if data[1] == "confirm":
        intervals["stopAll"] = True

        # Store chat_id for restart message
        chat_id = message.chat.id
        restart_message = None

        try:
            # Send restart message BEFORE stopping the client
            if TgClient.bot is not None:
                restart_message = await TgClient.bot.send_message(
                    chat_id=chat_id,
                    text="Restarting...",
                )
                LOGGER.info(f"Sent restart message with ID: {restart_message.id}")
            else:
                LOGGER.error("TgClient.bot is None, cannot send restart message")
        except Exception as e:
            LOGGER.error(f"Failed to send restart message: {e}")

        # Import garbage collection utilities
        try:
            from bot.helper.ext_utils.gc_utils import smart_garbage_collection

            gc_available = True
        except ImportError:
            gc_available = False

        try:
            # Stop Telegram clients
            LOGGER.info("Stopping Telegram clients...")
            await TgClient.stop()

            # Shutdown scheduler
            if scheduler.running:
                scheduler.shutdown(wait=False)

            # Cancel all intervals
            if qb := intervals["qb"]:
                qb.cancel()
            if jd := intervals["jd"]:
                jd.cancel()
            if nzb := intervals["nzb"]:
                nzb.cancel()
            if st := intervals["status"]:
                for intvl in list(st.values()):
                    intvl.cancel()

            # Clean all downloads
            await clean_all()

            # Cleanup streamrip sessions to prevent unclosed session warnings
            try:
                from bot.helper.mirror_leech_utils.streamrip_utils.search_handler import (
                    cleanup_all_streamrip_sessions,
                )

                await cleanup_all_streamrip_sessions()
            except Exception as e:
                LOGGER.error(f"Error during streamrip cleanup: {e}")

            # Close torrent managers
            await TorrentManager.close_all()

            # Stop database heartbeat and disconnect before restart
            try:
                await database.stop_heartbeat()
                await database.disconnect()
            except Exception as e:
                # Handle database cleanup errors gracefully during restart
                if "closed" not in str(e).lower():
                    LOGGER.error(f"Error during database cleanup in restart: {e}")

            # Force garbage collection before closing other services
            if gc_available:
                smart_garbage_collection(
                    aggressive=True
                )  # Use aggressive mode for cleanup before restart

            if sabnzbd_client and sabnzbd_client.LOGGED_IN:
                await gather(
                    sabnzbd_client.pause_all(),
                    sabnzbd_client.delete_job("all", True),
                    sabnzbd_client.purge_all(True),
                    sabnzbd_client.delete_history("all", delete_files=True),
                )
                await sabnzbd_client.close()

            if jdownloader and jdownloader.is_connected:
                await gather(
                    jdownloader.device.downloadcontroller.stop_downloads(),
                    jdownloader.device.linkgrabber.clear_list(),
                    jdownloader.device.downloads.cleanup(
                        "DELETE_ALL",
                        "REMOVE_LINKS_AND_DELETE_FILES",
                        "ALL",
                    ),
                )
                await jdownloader.close()

            proc1 = await create_subprocess_exec(
                "pkill",
                "-9",
                "-f",
                "gunicorn|xria|xnox|xtra|xone|xnzb|java|7z|split",
            )
            proc2 = await create_subprocess_exec("python3", "update.py")
            await gather(proc1.wait(), proc2.wait())

            # Save restart message info if we have a valid message
            if restart_message:
                async with aiopen(".restartmsg", "w") as f:
                    await f.write(
                        f"{restart_message.chat.id}\n{restart_message.id}\n"
                    )
            else:
                # If we couldn't send a restart message, still create the file with chat_id
                # The message_id will be invalid, but at least we'll notify the chat
                async with aiopen(".restartmsg", "w") as f:
                    await f.write(f"{chat_id}\n0\n")

            LOGGER.info("Executing restart command...")
            osexecl(executable, executable, "-m", "bot")
        except Exception as e:
            LOGGER.error(f"Error during restart process: {e}")
            # Try to notify about the error if possible
            try:
                if TgClient.bot is not None:
                    await TgClient.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Restart failed: {e!s}",
                    )
            except Exception:
                pass
            # Force restart anyway
            osexecl(executable, executable, "-m", "bot")
