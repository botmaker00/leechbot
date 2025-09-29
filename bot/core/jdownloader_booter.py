from json import dumps
from random import randint
from re import match

from aiofiles import open as aiopen
from aioshutil import rmtree

from bot import LOGGER
from bot.helper.ext_utils.aiofiles_compat import aiopath as path
from bot.helper.ext_utils.aiofiles_compat import listdir, makedirs, rename
from bot.helper.ext_utils.bot_utils import cmd_exec, new_task
from myjd import MyJdApi

from .aeon_client import TgClient
from .config_manager import Config


class JDownloader(MyJdApi):
    def __init__(self):
        super().__init__()
        self._username = ""
        self._password = ""
        self._device_name = ""
        self.is_connected = False
        self.error = "JDownloader Credentials not provided!"

    @new_task
    async def boot(self):
        # Check if JDownloader operations are enabled in the configuration
        if not Config.JD_ENABLED:
            self.is_connected = False
            self.error = "JDownloader operations are disabled by the administrator."
            return

        await cmd_exec(["pkill", "-9", "-f", "java"])
        if not Config.JD_EMAIL or not Config.JD_PASS:
            self.is_connected = False
            self.error = "JDownloader Credentials not provided!"
            return
        self.error = "Connecting... Try agin after couple of seconds"
        self._device_name = f"{randint(0, 1000)}@{TgClient.NAME}"
        if await path.exists("/JDownloader/logs"):
            LOGGER.info(
                "Starting JDownloader... This might take up to 10 sec and might restart once if update available!",
            )
        else:
            LOGGER.info(
                "Starting JDownloader... This might take up to 8 sec and might restart once after build!",
            )
        jdata = {
            "autoconnectenabledv2": True,
            "password": Config.JD_PASS,
            "devicename": f"{self._device_name}",
            "email": Config.JD_EMAIL,
        }
        remote_data = {
            "localapiserverheaderaccesscontrollalloworigin": "",
            "deprecatedapiport": 3128,
            "localapiserverheaderxcontenttypeoptions": "nosniff",
            "localapiserverheaderxframeoptions": "DENY",
            "externinterfaceenabled": True,
            "deprecatedapilocalhostonly": True,
            "localapiserverheaderreferrerpolicy": "no-referrer",
            "deprecatedapienabled": True,
            "localapiserverheadercontentsecuritypolicy": "default-src 'self'",
            "jdanywhereapienabled": True,
            "externinterfacelocalhostonly": False,
            "localapiserverheaderxxssprotection": "1; mode=block",
        }
        await makedirs("/JDownloader/cfg", exist_ok=True)
        async with aiopen(
            "/JDownloader/cfg/org.jdownloader.api.myjdownloader.MyJDownloaderSettings.json",
            "w",
        ) as sf:
            await sf.truncate(0)
            await sf.write(dumps(jdata))
        async with aiopen(
            "/JDownloader/cfg/org.jdownloader.api.RemoteAPIConfig.json",
            "w",
        ) as rf:
            await rf.truncate(0)
            await rf.write(dumps(remote_data))
        if not await path.exists("/JDownloader/JDownloader.jar"):
            pattern = r"JDownloader\.jar\.backup.\d$"
            for filename in await listdir("/JDownloader"):
                if match(pattern, filename):
                    await rename(
                        f"/JDownloader/{filename}",
                        "/JDownloader/JDownloader.jar",
                    )
                    break
            try:
                await rmtree("/JDownloader/update")
                await rmtree("/JDownloader/tmp")
            except Exception:
                pass

        cmd = "cpulimit -l 25 -- java -Xms64m -Xmx200m -Dsun.jnu.encoding=UTF-8 -Dfile.encoding=UTF-8 -Djava.awt.headless=true -jar /JDownloader/JDownloader.jar"

        self.is_connected = True
        _, __, code = await cmd_exec(cmd, shell=True)
        self.is_connected = False
        if code != -9:
            await self.boot()


jdownloader = JDownloader()
