from asyncio import create_task, gather
from json import loads
from secrets import token_hex

from bot import LOGGER, bot_loop, task_dict, task_dict_lock
from bot.helper.aeon_utils.access_check import error_check
from bot.helper.ext_utils.aiofiles_compat import remove
from bot.helper.ext_utils.bot_utils import (
    COMMAND_USAGE,
    arg_parser,
    cmd_exec,
    sync_to_async,
)
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.links_utils import (
    is_gdrive_id,
    is_gdrive_link,
    is_rclone_path,
    is_share_link,
)
from bot.helper.ext_utils.task_manager import stop_duplicate_check
from bot.helper.listeners.task_listener import TaskListener
from bot.helper.mirror_leech_utils.download_utils.direct_link_generator import (
    direct_link_generator,
)
from bot.helper.mirror_leech_utils.gdrive_utils.clone import GoogleDriveClone
from bot.helper.mirror_leech_utils.gdrive_utils.count import GoogleDriveCount
from bot.helper.mirror_leech_utils.rclone_utils.transfer import RcloneTransferHelper
from bot.helper.mirror_leech_utils.status_utils.gdrive_status import (
    GoogleDriveStatus,
)
from bot.helper.mirror_leech_utils.status_utils.rclone_status import RcloneStatus
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    delete_message,
    send_message,
    send_status_message,
)


class Clone(TaskListener):
    def __init__(
        self,
        client,
        message,
        _=None,
        __=None,
        ___=None,
        ____=None,
        _____=None,
        bulk=None,
        multi_tag=None,
        options="",
    ):
        if bulk is None:
            bulk = []
        self.message = message
        self.client = client
        self.multi_tag = multi_tag
        self.options = options
        self.same_dir = {}
        self.bulk = bulk
        super().__init__()
        self.is_clone = True

    async def new_event(self):
        text = self.message.text.split("\n")
        input_list = text[0].split(" ")
        error_msg, error_button = await error_check(self.message)
        if error_msg:
            await delete_links(self.message)
            error = await send_message(self.message, error_msg, error_button)
            return create_task(auto_delete_message(error, time=300))
        args = {
            "link": "",
            "-i": 0,
            "-b": False,
            "-n": "",
            "-up": "",
            "-rcf": "",
            "-sync": False,
        }

        arg_parser(input_list[1:], args)

        try:
            self.multi = int(args["-i"])
        except Exception:
            self.multi = 0

        self.up_dest = args["-up"]
        self.rc_flags = args["-rcf"]
        self.link = args["link"]
        self.name = args["-n"]

        is_bulk = args["-b"]
        sync = args["-sync"]
        bulk_start = 0
        bulk_end = 0

        if not isinstance(is_bulk, bool):
            dargs = is_bulk.split(":")
            bulk_start = dargs[0] or 0
            if len(dargs) == 2:
                bulk_end = dargs[1] or 0
            is_bulk = True

        if is_bulk:
            await self.init_bulk(input_list, bulk_start, bulk_end, Clone)
            return None

        await self.get_tag(text)

        if not self.link and (reply_to := self.message.reply_to_message):
            self.link = reply_to.text.split("\n", 1)[0].strip()

        await self.run_multi(input_list, Clone)

        if len(self.link) == 0:
            # When no valid link is provided, show usage menu and auto-delete after 5 minutes
            usage_msg = await send_message(
                self.message,
                COMMAND_USAGE["clone"][0],
                COMMAND_USAGE["clone"][1],
            )
            create_task(auto_delete_message(usage_msg, time=300))  # noqa: RUF006
            create_task(auto_delete_message(self.message, time=300))  # noqa: RUF006
            if reply_to := self.message.reply_to_message:
                create_task(auto_delete_message(reply_to, time=300))  # noqa: RUF006
            return None

        # If we get here, it means we have a valid link, so delete command messages immediately
        await delete_links(self.message)

        LOGGER.info(self.link)
        try:
            await self.before_start()
        except Exception as e:
            await send_message(self.message, e)
            return None
        await self._proceed_to_clone(sync)
        return None

    async def _proceed_to_clone(self, sync):
        if is_share_link(self.link):
            try:
                self.link = await sync_to_async(
                    direct_link_generator, self.link, self.user_id
                )
                LOGGER.info(f"Generated link: {self.link}")
            except DirectDownloadLinkException as e:
                LOGGER.error(str(e))
                if str(e).startswith("ERROR:"):
                    await send_message(self.message, str(e))
                    return
        if is_gdrive_link(self.link) or is_gdrive_id(self.link):
            self.name, mime_type, self.size, files, _ = await sync_to_async(
                GoogleDriveCount().count,
                self.link,
                self.user_id,
            )
            if mime_type is None:
                await send_message(self.message, self.name)
                return

            # Check size limits
            if self.size > 0:
                self.isClone = True  # Set isClone attribute for limit_checker
                limit_msg = await limit_checker(
                    self.size,
                    self,
                    isTorrent=False,
                    isMega=False,
                    isDriveLink=True,
                    isYtdlp=False,
                )
                if limit_msg:
                    # limit_msg is already a tuple with (message_object, error_message)
                    # and the message has already been sent with the tag
                    return

            msg, button = await stop_duplicate_check(self)
            if msg:
                await send_message(self.message, msg, button)
                return
            await self.on_download_start()
            LOGGER.info(f"Clone Started: Name: {self.name} - Source: {self.link}")
            drive = GoogleDriveClone(self)
            if files <= 10:
                msg = await send_message(
                    self.message,
                    f"Cloning: <code>{self.link}</code>",
                )
            else:
                msg = ""
                gid = token_hex(4)
                async with task_dict_lock:
                    task_dict[self.mid] = GoogleDriveStatus(self, drive, gid, "cl")
                if self.multi <= 1:
                    await send_status_message(self.message)
            flink, mime_type, files, folders, dir_id = await sync_to_async(
                drive.clone,
            )
            if msg:
                await delete_message(msg)
            if not flink:
                return
            await self.on_upload_complete(
                flink,
                files,
                folders,
                mime_type,
                dir_id=dir_id,
            )
            LOGGER.info(f"Cloning Done: {self.name}")
        elif is_rclone_path(self.link):
            # Check if Rclone operations are enabled in the configuration
            from bot.core.config_manager import Config

            if not Config.RCLONE_ENABLED:
                await send_message(
                    self.message,
                    "❌ Rclone operations are disabled by the administrator.",
                )
                return

            if self.link.startswith("mrcc:"):
                self.link = self.link.replace("mrcc:", "", 1)
                self.up_dest = self.up_dest.replace("mrcc:", "", 1)
                config_path = f"rclone/{self.user_id}.conf"
            else:
                config_path = "rclone.conf"

            remote, src_path = self.link.split(":", 1)
            self.link = src_path.strip("/")
            if self.link.startswith("rclone_select"):
                mime_type = "Folder"
                src_path = ""
                if not self.name:
                    self.name = self.link
            else:
                src_path = self.link
                cmd = [
                    "xone",
                    "lsjson",
                    "--fast-list",
                    "--stat",
                    "--no-modtime",
                    "--config",
                    config_path,
                    f"{remote}:{src_path}",
                ]
                res = await cmd_exec(cmd)
                if res[2] != 0:
                    if res[2] != -9:
                        msg = f"Error: While getting rclone stat. Path: {remote}:{src_path}. Stderr: {res[1][:4000]}"
                        await send_message(self.message, msg)
                    return
                rstat = loads(res[0])
                if rstat["IsDir"]:
                    if not self.name:
                        self.name = (
                            src_path.rsplit("/", 1)[-1] if src_path else remote
                        )
                    self.up_dest += (
                        self.name if self.up_dest.endswith(":") else f"/{self.name}"
                    )

                    mime_type = "Folder"
                else:
                    if not self.name:
                        self.name = src_path.rsplit("/", 1)[-1]
                    mime_type = rstat["MimeType"]

            # Get size for rclone path
            cmd_size = [
                "xone",
                "size",
                "--fast-list",
                "--json",
                "--config",
                config_path,
                f"{remote}:{src_path}",
                "-v",
                "--log-systemd",
            ]
            res_size = await cmd_exec(cmd_size)
            if res_size[2] == 0:
                try:
                    rsize = loads(res_size[0])
                    self.size = rsize["bytes"]

                    # Check size limits
                    if self.size > 0:
                        self.isClone = (
                            True  # Set isClone attribute for limit_checker
                        )
                        limit_msg = await limit_checker(
                            self.size,
                            self,
                            isTorrent=False,
                            isMega=False,
                            isDriveLink=False,
                            isYtdlp=False,
                        )
                        if limit_msg:
                            # limit_msg is already a tuple with (message_object, error_message)
                            # and the message has already been sent with the tag
                            return
                except Exception as e:
                    LOGGER.error(f"Error parsing rclone size: {e}")

            await self.on_download_start()

            RCTransfer = RcloneTransferHelper(self)
            LOGGER.info(
                f"Clone Started: Name: {self.name} - Source: {self.link} - Destination: {self.up_dest}",
            )
            gid = token_hex(4)
            async with task_dict_lock:
                task_dict[self.mid] = RcloneStatus(self, RCTransfer, gid, "cl")
            if self.multi <= 1:
                await send_status_message(self.message)
            method = "sync" if sync else "copy"
            flink, destination = await RCTransfer.clone(
                config_path,
                remote,
                src_path,
                mime_type,
                method,
            )
            if self.link.startswith("rclone_select"):
                await remove(self.link)
            if not destination:
                return
            LOGGER.info(f"Cloning Done: {self.name}")
            cmd1 = [
                "xone",
                "lsf",
                "--fast-list",
                "-R",
                "--files-only",
                "--config",
                config_path,
                destination,
            ]
            cmd2 = [
                "xone",
                "lsf",
                "--fast-list",
                "-R",
                "--dirs-only",
                "--config",
                config_path,
                destination,
            ]
            cmd3 = [
                "xone",
                "size",
                "--fast-list",
                "--json",
                "--config",
                config_path,
                destination,
            ]
            res1, res2, res3 = await gather(
                cmd_exec(cmd1),
                cmd_exec(cmd2),
                cmd_exec(cmd3),
            )
            if res1[2] != 0 or res2[2] != 0 or res3[2] != 0:
                if res1[2] == -9:
                    return
                files = None
                folders = None
                self.size = 0
                error = res1[1] or res2[1] or res3[1]
                msg = f"Error: While getting rclone stat. Path: {destination}. Stderr: {error[:4000]}"
                await self.on_upload_error(msg)
            else:
                files = len(res1[0].split("\n"))
                folders = len(res2[0].strip().split("\n")) if res2[0] else 0
                rsize = loads(res3[0])
                self.size = rsize["bytes"]
                await self.on_upload_complete(
                    flink,
                    files,
                    folders,
                    mime_type,
                    destination,
                )
        else:
            await send_message(
                self.message,
                COMMAND_USAGE["clone"][0],
                COMMAND_USAGE["clone"][1],
            )


async def clone_node(client, message):
    """Clone a file/folder from Google Drive or Rclone path.

    This function creates a task to handle the clone operation.
    It's designed to be called from a command handler.
    """
    # Check if mirror operations are enabled in the configuration
    from bot.core.config_manager import Config
    from bot.helper.telegram_helper.message_utils import send_message

    # Check if mirror operations are enabled
    if not Config.MIRROR_ENABLED:
        await send_message(
            message,
            "❌ Clone command is disabled when mirror operations are disabled.",
        )
        return None

    # We don't check for RCLONE_ENABLED here because the clone command can also
    # clone from Google Drive. The check for RCLONE_ENABLED is done in the Clone class
    # when an Rclone path is detected.

    # Use create_task to avoid blocking the event loop
    # We wrap this in a function to avoid running asyncio code during import
    return bot_loop.create_task(Clone(client, message).new_event())
