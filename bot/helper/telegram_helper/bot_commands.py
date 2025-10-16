# ruff: noqa: RUF012
from bot.core.config_manager import Config

i = Config.CMD_SUFFIX


class BotCommands:
    StartCommand = "start"
    MirrorCommand = [f"mirror{i}", f"m{i}"]
    JdMirrorCommand = [f"jdmirror{i}", f"jm{i}"]
    NzbMirrorCommand = [f"nzbmirror{i}", f"nm{i}"]
    YtdlCommand = [f"ytdl{i}", f"y{i}"]
    GdlCommand = [f"gdlmirror{i}", f"gm{i}"]
    LeechCommand = [f"leech{i}", f"l{i}"]
    JdLeechCommand = [f"jdleech{i}", f"jl{i}"]
    NzbLeechCommand = [f"nzbleech{i}", f"nl{i}"]
    YtdlLeechCommand = [f"ytdlleech{i}", f"yl{i}"]
    GdlLeechCommand = [f"gdlleech{i}", f"gl{i}"]
    CloneCommand = f"clone{i}"

    MediaInfoCommand = [f"mediainfo{i}", f"mi{i}"]
    CountCommand = f"count{i}"
    DeleteCommand = f"del{i}"
    CancelAllCommand = f"cancelall{i}"
    ForceStartCommand = [f"forcestart{i}", f"fs{i}"]
    ListCommand = f"list{i}"
    SearchCommand = f"search{i}"
    HydraSearchCommamd = f"nzbsearch{i}"
    StatusCommand = [f"status{i}", f"s{i}", "statusall", "sall"]
    UsersCommand = f"users{i}"
    AuthorizeCommand = f"auth{i}"
    UnAuthorizeCommand = f"unauth{i}"
    AddSudoCommand = f"addsudo{i}"
    RmSudoCommand = f"rmsudo{i}"
    PingCommand = f"ping{i}"
    RestartCommand = [f"restart{i}", "restartall"]
    StatsCommand = f"stats{i}"
    HelpCommand = f"help{i}"
    LogCommand = f"log{i}"
    ShellCommand = f"shell{i}"
    AExecCommand = f"aexec{i}"
    ExecCommand = f"exec{i}"
    ClearLocalsCommand = f"clearlocals{i}"
    BotSetCommand = f"botsettings{i}"
    UserSetCommand = [f"settings{i}", f"usettings{i}", f"us{i}"]
    SpeedTest = f"speedtest{i}"
    BroadcastCommand = [f"broadcast{i}", "broadcastall"]
    ForwardCommand = f"forward{i}"
    SelectCommand = f"sel{i}"
    RssCommand = f"rss{i}"
    FontStylesCommand = [f"fontstyles{i}", f"fonts{i}"]
    CheckDeletionsCommand = [f"check_deletions{i}", f"cd{i}"]
    IMDBCommand = f"imdb{i}"
    TMDBCommand = f"tmdb{i}"
    WhisperCommand = f"whisper{i}"
    LoginCommand = f"login{i}"
    MediaSearchCommand = [f"mediasearch{i}", f"mds{i}"]
    MediaToolsCommand = [f"mediatools{i}", f"mt{i}"]
    MediaToolsHelpCommand = [f"mthelp{i}", f"mth{i}"]
    GenSessionCommand = [f"gensession{i}", f"gs{i}"]
    TruecallerCommand = f"truecaller{i}"
    AskCommand = f"ask{i}"
    SoxCommand = [f"spectrum{i}", f"sox{i}"]
    PasteCommand = f"paste{i}"
    VirusTotalCommand = f"virustotal{i}"
    PhishCheckCommand = f"phishcheck{i}"
    WotCommand = f"wot{i}"
    StreamripMirrorCommand = [f"streamripmirror{i}", f"srmirror{i}", f"srm{i}"]
    StreamripLeechCommand = [f"streamripleech{i}", f"srleech{i}", f"srl{i}"]
    StreamripSearchCommand = [f"streamripsearch{i}", f"srsearch{i}", f"srs{i}"]
    ZotifyMirrorCommand = [f"zotifymirror{i}", f"zmirror{i}", f"zm{i}"]
    ZotifyLeechCommand = [f"zotifyleech{i}", f"zleech{i}", f"zl{i}"]
    ZotifySearchCommand = [f"zotifysearch{i}", f"zsearch{i}", f"zs{i}"]
    MegaSearchCommand = [f"megasearch{i}", f"mgs{i}"]
    # Encoding/Decoding Commands
    EncodeCommand = [f"encode{i}", f"enc{i}"]
    DecodeCommand = [f"decode{i}", f"dec{i}"]
    # QuickInfo Commands
    QuickInfoCommand = [f"quickinfo{i}", f"qi{i}"]
    # Tool Commands
    ToolCommand = [f"tool{i}", f"t{i}"]
    # Enhanced NSFW Detection Commands
    NSFWStatsCommand = f"nsfwstats{i}"
    NSFWTestCommand = f"nsfwtest{i}"
    # Scraping Commands
    ScrapCommand = f"scrap{i}"
    # File2Link Commands
    # Cat API Commands
    NekoCommand = f"neko{i}"
    # Trace.moe Commands
    TraceCommand = f"trace{i}"
    # OSINT Commands
    OSINTCommand = f"osint{i}"
    # Contact Commands
    ContactCommand = f"contact{i}"
    BanCommand = f"ban{i}"
    UnbanCommand = f"unban{i}"
    # Weather Commands
    WeatherCommand = [f"weather{i}", f"w{i}"]
    # Link Shortener Commands
    ShortnerCommand = f"shortner{i}"
    # QR Code Commands
    QRCodeCommand = f"qrcode{i}"
    # Music Download Commands
    MusicMirrorCommand = [f"musicmirror{i}", f"mmirror{i}", f"mm{i}"]
    MusicLeechCommand = [f"musicleech{i}", f"mleech{i}", f"ml{i}"]
