# ruff: noqa: RUF012
from bot.core.config_manager import Config

i = Config.CMD_SUFFIX


class BotCommands:
    StartCommand = "start"
    MirrorCommand = [f"mirrorx{i}", f"mx{i}"]
    JdMirrorCommand = [f"jdmirrorx{i}", f"jmx{i}"]
    NzbMirrorCommand = [f"nzbmirrorx{i}", f"nmx{i}"]
    YtdlCommand = [f"ytdlx{i}", f"yx{i}"]
    LeechCommand = [f"leechx{i}", f"lx{i}"]
    JdLeechCommand = [f"jdleechx{i}", f"jlx{i}"]
    NzbLeechCommand = [f"nzbleechx{i}", f"nlx{i}"]
    YtdlLeechCommand = [f"ytdlleechx{i}", f"ylx{i}"]
    CloneCommand = f"clonex{i}"
    MediaInfoCommand = f"mediainfox{i}"
    CountCommand = f"countx{i}"
    DeleteCommand = f"delx{i}"
    CancelAllCommand = f"cancelall{i}"
    ForceStartCommand = [f"forcestart{i}", f"fs{i}"]
    ListCommand = f"list{i}"
    SearchCommand = f"searchx{i}"
    HydraSearchCommand = f"nzbsearch{i}"
    StatusCommand = [f"statusx{i}", "statusall"]
    UsersCommand = f"users{i}"
    AuthorizeCommand = f"auth{i}"
    UnAuthorizeCommand = f"unauth{i}"
    AddSudoCommand = f"addsudox{i}"
    RmSudoCommand = f"rmsudo{i}"
    PingCommand = f"pingx{i}"
    RestartCommand = [f"restart{i}", "restartall"]
    StatsCommand = f"stats{i}"
    HelpCommand = f"help{i}"
    LogCommand = f"log{i}"
    ShellCommand = f"shell{i}"
    AExecCommand = f"aexec{i}"
    ExecCommand = f"exec{i}"
    ClearLocalsCommand = f"clearlocals{i}"
    BotSetCommand = f"bsettingx{i}"
    UserSetCommand = f"usettingx{i}"
    SpeedTest = f"speedtest{i}"
    BroadcastCommand = [f"broadcast{i}", "broadcastall"]
    SelectCommand = f"sel{i}"
    RssCommand = f"rss{i}"
    SoxCommand = [f"spectrum{i}", f"sox{i}"]
