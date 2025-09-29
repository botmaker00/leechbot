# REQUIRED CONFIG
BOT_TOKEN = "7552035888:AAHC4Ikvo_t3hxtOY0tOC3aByUmK3bQfu0Q"  # Get this from @BotFather
OWNER_ID = 5741918628  # Your Telegram User ID (not username) as an integer
TELEGRAM_API = 21518327  # Get this from my.telegram.org
TELEGRAM_HASH = "e72f588b3e4763f01eecfc3c4aa7e8ac"  # Get this from my.telegram.org

# SEMI-REQUIRED, WE SUGGEST TO FILL IT FROM MONGODB
DATABASE_URL = "mongodb+srv://remleech:remleech@remleech.n2pttzf.mongodb.net/?retryWrites=true&w=majority&appName=remleech"  # MongoDB URI for storing user >

# Heroku config for get BASE_URL automatically
HEROKU_APP_NAME = ""
HEROKU_API_KEY = ""

# AUTO REDEPLOY CONFIG
HEROKU_EMAIL = ""  # Your Heroku account email
HEROKU_TEAM_NAME = (
    ""  # Optional: Your Heroku team name (leave empty if not using teams)
)
HEROKU_REGION = (
    "eu"  # Heroku deployment region: "eu" for Europe or "us" for United States
)
AUTO_REDEPLOY = False  # Enable/disable automatic redeployment on schedule
REDEPLOY_INTERVAL_DAYS = 7  # Auto redeploy interval in days (1, 3, 7, 14, or 30)

# Update
UPSTREAM_REPO = "https://github.com/botmaker00/leechbot"  # Repository URL for updates
UPSTREAM_BRANCH = "extended"  # Branch to use for updates

# Branding Settings
CREDIT = "Powered by @Animeworld_zone"  # Credit text shown in status messages and RSS feeds (default: "Powered by @aimmirror")
OWNER_THUMB = "https://graph.org/Animeworld-zone-09-11-3"  # Default thumbnail URL for owner (accepts Telegram file links)

# Telegram
USER_SESSION_STRING = ""  # Pyrogram user session string for mirror/leech authentication
TG_PROXY = (
    {}
)  # Proxy for Telegram connection, format: {'addr': 'ip:port', 'username': 'username', 'password': 'password'}

# Authorization
SUDO_USERS = ""  # List of sudo user IDs who can use admin commands, separated by space
AUTHORIZED_CHATS = (
    ""  # List of authorized chat IDs where the bot can be used, separated by space
)

# Upload
DEFAULT_UPLOAD = "gd"  # Default upload destination: 'gd' for Google Drive, 'rc' for rclone, 'ddl' for Direct Download Links
UPLOAD_PATHS = {}  # Custom upload paths for different file types

# Hyper Download
HELPER_TOKENS = (
    ""  # Bot tokens for helper bots, separated by space. Format: "token1 token2 token3"
)
HYPER_THREADS = 0  # Number of threads for hyper download (0 = auto-detect based on number of helper bots)

# Command Management
CMD_SUFFIX = ""  # Command suffix to distinguish commands, e.g. "1" would make commands like /mirror1
WRONG_CMD_WARNINGS_ENABLED = False  # Enable/disable warnings for wrong command suffixes
CORRECT_CMD_SUFFIX = ""  # Comma-separated list of command suffixes that won't trigger warnings, e.g. "1,2,3"

# Feature Toggles
MIRROR_ENABLED = True  # Enable/disable mirror feature
LEECH_ENABLED = True  # Enable/disable leech feature
YTDLP_ENABLED = True  # Enable/disable YT-DLP feature
TORRENT_ENABLED = True  # Enable/disable torrent feature
TORRENT_SEARCH_ENABLED = True  # Enable/disable torrent search feature
NZB_ENABLED = True  # Enable/disable NZB feature
JD_ENABLED = True  # Enable/disable JDownloader feature
MEGA_ENABLED = True  # Enable/disable Mega.nz downloads
MEGA_UPLOAD_ENABLED = True  # Enable MEGA upload functionality
MEGA_SEARCH_ENABLED = True  # Enable/disable MEGA search functionality
DDL_ENABLED = True  # Enable/disable DDL upload feature
RCLONE_ENABLED = True  # Enable/disable Rclone feature
HYPERDL_ENABLED = True  # Enable/disable hyper download feature
ARCHIVE_FLAGS_ENABLED = True  # Enable/disable archive operation flags (-z and -e flags)
MULTI_LINK_ENABLED = True  # Enable/disable multi-link feature (-i flag)
SAME_DIR_ENABLED = True  # Enable/disable same directory feature (-m flag)
BULK_ENABLED = True  # Enable/disable bulk operations (-b flag)
MEDIAINFO_ENABLED = (
    False  # Enable/disable mediainfo command for detailed media information
)
MEDIA_STORE = False  # Enable media store link
AD_BROADCASTER_ENABLED = (
    False  # Enable/disable automatic ad broadcasting from FSUB channels to users
)
AI_ENABLED = True  # Enable/disable AI functionality
IMDB_ENABLED = True  # Enable/disable IMDB functionality
TMDB_ENABLED = True  # Enable/disable TMDB functionality
TRUECALLER_ENABLED = True  # Enable/disable Truecaller functionality
MEDIA_SEARCH_ENABLED = True  # Enable/disable media search feature

# Media Search Settings
MEDIA_SEARCH_CHATS = []  # List of chat IDs where media search is enabled

# -> Direct Link Generators
FILELION_API = ""  # FileLion API key for direct links
STREAMWISH_API = ""  # StreamWish API key for direct links
# Debrid-Link Authentication Settings - Get from https://debrid-link.com/webapp/apikey
DEBRID_LINK_API = (
    ""  # Legacy API key or OAuth2 access_token for premium link generation
)
DEBRID_LINK_ACCESS_TOKEN = ""  # OAuth2 access_token (recommended, expires periodically)
DEBRID_LINK_REFRESH_TOKEN = ""  # OAuth2 refresh_token for automatic token renewal
DEBRID_LINK_CLIENT_ID = ""  # OAuth2 client_id from your Debrid-Link app
DEBRID_LINK_CLIENT_SECRET = ""  # OAuth2 client_secret (keep secure, server-side only)
DEBRID_LINK_TOKEN_EXPIRES = 0  # Token expiration timestamp (auto-managed)
# TorBox API Settings - Get from https://torbox.app/settings
TORBOX_API_KEY = (
    ""  # TorBox API key for premium downloads (torrents, usenet, web downloads)
)
# Mega-Debrid API Settings - Get from https://www.mega-debrid.eu/
MEGA_DEBRID_API_TOKEN = ""  # Mega-Debrid API token (if you have one)
MEGA_DEBRID_LOGIN = ""  # Mega-Debrid login username (alternative to token)
MEGA_DEBRID_PASSWORD = ""  # Mega-Debrid login password (alternative to token)
# AllDebrid API Settings - Get from https://alldebrid.com/apikey/
ALLDEBRID_API_KEY = ""  # AllDebrid API key for premium downloads (supports torrents, magnets, and 100+ file hosts)
# Real-Debrid API Settings - Get from https://real-debrid.com/apitoken
REAL_DEBRID_API_KEY = ""  # Real-Debrid API key for premium downloads (private token)
REAL_DEBRID_ACCESS_TOKEN = ""  # OAuth2 access token (recommended for apps)
REAL_DEBRID_REFRESH_TOKEN = ""  # OAuth2 refresh token for automatic renewal
REAL_DEBRID_CLIENT_ID = (
    ""  # OAuth2 client ID from Real-Debrid app (use X245A4XAIBGVM for opensource)
)
REAL_DEBRID_CLIENT_SECRET = (
    ""  # OAuth2 client secret (keep secure, not needed for opensource apps)
)
REAL_DEBRID_TOKEN_EXPIRES = 0  # Token expiration timestamp (auto-managed)


EXCLUDED_EXTENSIONS = (
    ""  # File extensions to exclude from processing, separated by space
)
INCOMPLETE_TASK_NOTIFIER = False  # Notify about incomplete tasks on bot restart
SCHEDULED_DELETION_ENABLED = True  # Enable/disable scheduled deletion functionality
YT_DLP_OPTIONS = {}  # Additional yt-dlp options as a JSON string
NAME_SUBSTITUTE = r""  # Regex pattern to substitute in filenames
FFMPEG_CMDS = {}  # Custom FFmpeg commands for different file types
DELETE_LINKS = False  # Delete links after download
FSUB_IDS = ""  # Force subscribe channel IDs, separated by space
AD_KEYWORDS = ""  # Custom keywords/phrases for ad detection, separated by comma (e.g., "#ad,#ad bangla,#sponsored,InsideAds")
TOKEN_TIMEOUT = 0  # Token timeout in seconds (0 = no timeout)
LOGIN_PASS = ""  # Password for web login
PAID_CHANNEL_ID = 0  # Paid channel ID for premium features
PAID_CHANNEL_LINK = ""  # Invite link for paid channel
SET_COMMANDS = True  # Set bot commands in Telegram UI
LOG_CHAT_ID = 0  # Chat ID where logs will be sent
INSTADL_API = ""  # InstaDL API key for Instagram downloads


# GDrive Tools
GDRIVE_ID = ""  # Google Drive folder/TeamDrive ID where files will be uploaded
GDRIVE_UPLOAD_ENABLED = True  # Enable/disable Google Drive upload feature
IS_TEAM_DRIVE = False  # Whether the GDRIVE_ID is a TeamDrive
STOP_DUPLICATE = False  # Skip uploading files that are already in the drive
INDEX_URL = ""  # Index URL for Google Drive
USE_SERVICE_ACCOUNTS = False  # Whether to use service accounts for Google Drive
SHOW_CLOUD_LINK = True  # Show cloud links in upload completion message

# Rclone
RCLONE_PATH = ""  # Path to rclone.conf file
RCLONE_FLAGS = ""  # Additional rclone flags
RCLONE_SERVE_URL = ""  # URL for rclone serve
RCLONE_SERVE_PORT = 8080  # Port for rclone serve
RCLONE_SERVE_USER = ""  # Username for rclone serve
RCLONE_SERVE_PASS = ""  # Password for rclone serve

# JDownloader
JD_EMAIL = ""  # JDownloader email/username
JD_PASS = ""  # JDownloader password

# -> Mega.nz Settings
MEGA_EMAIL = ""  # Mega.nz account email (optional, for premium features)
MEGA_PASSWORD = ""  # Mega.nz account password (optional, for premium features)
MEGA_UPLOAD_PUBLIC = True  # Generate public links by default
MEGA_UPLOAD_THUMBNAIL = True  # Generate thumbnails for videos using FFmpeg

# -> DDL (Direct Download Link) Upload Settings
DDL_DEFAULT_SERVER = (
    "gofile"  # Default DDL server: gofile, streamtape, devuploads, mediafire
)
GOFILE_API_KEY = ""  # Default Gofile API key (can be overridden per user)
GOFILE_FOLDER_NAME = ""  # Default folder name for uploads (empty = use filename)
GOFILE_PUBLIC_LINKS = True  # Generate public links by default
GOFILE_PASSWORD_PROTECTION = False  # Enable password protection
GOFILE_DEFAULT_PASSWORD = ""  # Default password for protected uploads
GOFILE_LINK_EXPIRY_DAYS = 0  # Link expiry in days (0 = no expiry)
STREAMTAPE_API_USERNAME = ""  # Streamtape API/FTP Username (from account panel)
STREAMTAPE_API_PASSWORD = ""  # Streamtape API/FTP Password (from account panel)
STREAMTAPE_FOLDER_NAME = ""  # Default folder name for uploads
STREAMTAPE_ALLOWED_EXTENSIONS = [
    ".avi",
    ".mkv",
    ".mpg",
    ".mpeg",
    ".vob",
    ".wmv",
    ".flv",
    ".mp4",
    ".mov",
    ".m4v",
    ".m2v",
    ".divx",
    ".3gp",
    ".webm",
    ".ogv",
    ".ogg",
    ".ts",
    ".ogm",
]  # Allowed video extensions for Streamtape
DEVUPLOADS_API_KEY = ""  # Default DevUploads API key (can be overridden per user)
DEVUPLOADS_FOLDER_NAME = ""  # Default folder name for uploads (empty = root folder)
DEVUPLOADS_PUBLIC_FILES = (
    True  # Default public/private setting for uploads (True = public, False = private)
)
MEDIAFIRE_EMAIL = ""  # MediaFire account email for authentication
MEDIAFIRE_PASSWORD = ""  # MediaFire account password for authentication
MEDIAFIRE_APP_ID = ""  # MediaFire application ID (required for API access)
MEDIAFIRE_API_KEY = ""  # MediaFire API key (optional, for enhanced features)

# Sabnzbd
HYDRA_IP = ""  # Hydra IP address for direct links
HYDRA_API_KEY = ""  # Hydra API key for direct links
NZB_SEARCH_ENABLED = True  # Enable/disable NZB search feature
USENET_SERVERS = [  # List of Usenet servers for NZB downloads
    {
        "name": "main",  # Server name
        "host": "",  # Server hostname or IP
        "port": 563,  # Server port
        "timeout": 60,  # Connection timeout in seconds
        "username": "",  # Server username
        "password": "",  # Server password
        "connections": 8,  # Number of connections to use
        "ssl": 1,  # Use SSL: 0=no, 1=yes
        "ssl_verify": 2,  # SSL verification: 0=no, 1=verify host, 2=verify host and peer
        "ssl_ciphers": "",  # SSL ciphers to use
        "enable": 1,  # Enable server: 0=no, 1=yes
        "required": 0,  # Server is required: 0=no, 1=yes
        "optional": 0,  # Server is optional: 0=no, 1=yes
        "retention": 0,  # Server retention in days (0=unlimited)
        "send_group": 0,  # Send group command: 0=no, 1=yes
        "priority": 0,  # Server priority (0=highest)
    },
]


# Leech
LEECH_SPLIT_SIZE = 0  # Size of split files in bytes, 0 means no split
AS_DOCUMENT = False  # Send files as documents instead of media
MEDIA_GROUP = False  # Group media files together when sending
USER_TRANSMISSION = False  # Use transmission for torrents
HYBRID_LEECH = False  # Enable hybrid leech (both document and media)
LEECH_FILENAME_PREFIX = ""  # Prefix to add to leeched filenames
LEECH_SUFFIX = ""  # Suffix to add to leeched files
LEECH_FONT = ""  # Font to use for leech captions
LEECH_FILENAME = ""  # Custom filename template for leeched files
LEECH_FILENAME_CAPTION = ""  # Caption template for leeched files (max 1024 characters)
UNIVERSAL_FILENAME = ""  # Universal filename template for both mirror and leech files (supports all template variables)
LEECH_DUMP_CHAT = (
    []
)  # Chat IDs ["-100123456789", "b:@mychannel", "u:-100987654321", "h:@mygroup|123456"] where leeched files will be sent
THUMBNAIL_LAYOUT = ""  # Layout for thumbnails: empty, top, bottom, or custom
EQUAL_SPLITS = False  # Create equal-sized parts when splitting files


# qBittorrent/Aria2c
TORRENT_TIMEOUT = 0  # Timeout for torrent downloads in seconds (0 = no timeout)
BASE_URL = "http://161.118.179.19:8181"  # Base URL for web server
BASE_URL_PORT = 8181  # Port for web server (0 to disable)
WEB_PINCODE = False  # Enable pincode protection for web server

# File2Link Settings
FILE2LINK_ENABLED = True  # Enable File2Link functionality
FILE2LINK_BASE_URL = "http://161.118.179.19:7979"  # Dedicated base URL for File2Link streaming (optional, uses BASE_URL if not set)
FILE2LINK_BIN_CHANNEL = 0  # REQUIRED: Private channel ID to store files for streaming (e.g., -1001234567890)
FILE2LINK_ALLOWED_TYPES = "video,audio,document,photo,animation,voice,video_note"  # Allowed media types for streaming

# Forwarding Settings
FORWARD_SOURCE = (
    []
)  # Source chat IDs/usernames for automatic forwarding (e.g., ["-1001234567890", "@channel1"])
FORWARD_DESTINATION = (
    []
)  # Destination chat IDs/usernames for automatic forwarding (e.g., ["-1001234567890", "@channel2"])

# Queueing system
QUEUE_ALL = 0  # Maximum number of concurrent tasks (0 = unlimited)
QUEUE_DOWNLOAD = 0  # Maximum number of concurrent downloads (0 = unlimited)
QUEUE_UPLOAD = 0  # Maximum number of concurrent uploads (0 = unlimited)

# RSS - Optimized for better resource management
RSS_DELAY = 900  # Increased delay to 15 minutes for better resource efficiency
RSS_CHAT = ""  # Chat ID where RSS feed updates will be sent
RSS_SIZE_LIMIT = 0  # Maximum size for RSS downloads in bytes (0 = unlimited)
RSS_ENABLED = (
    True  # Enable/disable RSS functionality completely (True=enabled, False=disabled)
)
RSS_JOB_INTERVAL = 600  # RSS job periodic runtime interval in seconds (default: 600)

# Resource Management Settings
PIL_MEMORY_LIMIT = 1024  # Memory limit for PIL image processing in MB (reduced for better memory management)

# Auto Restart Settings - Optimized for stability
AUTO_RESTART_ENABLED = (
    False  # Enable automatic bot restart (disabled by default for better stability)
)
AUTO_RESTART_INTERVAL = (
    48  # Increased restart interval to 48 hours for better resource management
)

# Limits Settings
STORAGE_THRESHOLD = (
    0  # Storage threshold in GB, bot will stop if free space falls below this
)
TORRENT_LIMIT = 0  # Maximum size for torrent downloads in GB (0 = unlimited)
DIRECT_LIMIT = 0  # Maximum size for direct link downloads in GB (0 = unlimited)
YTDLP_LIMIT = 0  # Maximum size for YouTube/video downloads in GB (0 = unlimited)
GDRIVE_LIMIT = 0  # Maximum size for Google Drive downloads in GB (0 = unlimited)
CLONE_LIMIT = 0  # Maximum size for clone operations in GB (0 = unlimited)
MEGA_LIMIT = 0  # Maximum size for Mega downloads in GB (0 = unlimited)
LEECH_LIMIT = 0  # Maximum size for leech operations in GB (0 = unlimited)
JD_LIMIT = 0  # Maximum size for JDownloader downloads in GB (0 = unlimited)
NZB_LIMIT = 0  # Maximum size for NZB downloads in GB (0 = unlimited)
PLAYLIST_LIMIT = 0  # Maximum number of videos in a playlist (0 = unlimited)
ZOTIFY_LIMIT = 0  # Maximum size for Zotify downloads in GB (0 = unlimited)
DAILY_TASK_LIMIT = 0  # Maximum number of tasks per day per user (0 = unlimited)
DAILY_MIRROR_LIMIT = 0  # Maximum mirror size in GB per day per user (0 = unlimited)
DAILY_LEECH_LIMIT = 0  # Maximum leech size in GB per day per user (0 = unlimited)
USER_MAX_TASKS = 0  # Maximum concurrent tasks per user (0 = unlimited)
BOT_MAX_TASKS = (
    0  # Maximum number of concurrent tasks the bot can handle (0 = unlimited)
)
USER_TIME_INTERVAL = 0  # Minimum time between user tasks in seconds (0 = no delay)
STATUS_UPDATE_INTERVAL = (
    3  # Status update interval in seconds (minimum 2, recommended: 3-5)
)
STATUS_LIMIT = 10  # Number of tasks to display in status message (recommended: 4-10)
SEARCH_LIMIT = 0  # Maximum number of search results to display (0 = unlimited)

# Task Monitoring Settings - Optimized for reduced resource usage
TASK_MONITOR_ENABLED = (
    False  # Disabled by default for better performance (enable only if needed)
)
TASK_MONITOR_INTERVAL = 120  # Increased interval to 2 minutes to reduce CPU usage
TASK_MONITOR_CONSECUTIVE_CHECKS = 10  # Reduced from 20 to 10 to save memory
TASK_MONITOR_SPEED_THRESHOLD = 50  # Speed threshold in KB/s
TASK_MONITOR_ELAPSED_THRESHOLD = 3600  # Elapsed time threshold in seconds (1 hour)
TASK_MONITOR_ETA_THRESHOLD = 86400  # ETA threshold in seconds (24 hours)
TASK_MONITOR_WAIT_TIME = 900  # Increased wait time to 15 minutes to reduce overhead
TASK_MONITOR_COMPLETION_THRESHOLD = 86400  # Completion threshold in seconds (24 hours)
TASK_MONITOR_CPU_HIGH = 85  # Reduced threshold for better responsiveness
TASK_MONITOR_CPU_LOW = 50  # Reduced threshold
TASK_MONITOR_MEMORY_HIGH = 70  # Reduced threshold for better memory management
TASK_MONITOR_MEMORY_LOW = 50  # Reduced threshold

# Garbage Collection Settings - Control memory management behavior
GC_ENABLED = (
    False  # Enable/disable garbage collection completely (True=enabled, False=disabled)
)
GC_INTERVAL = 60  # Minimum interval between GC operations in seconds (default: 60)
GC_THRESHOLD_MB = 150  # Memory threshold in MB to trigger GC (default: 150)
GC_AGGRESSIVE_MODE = (
    False  # Enable aggressive GC by default (True=more frequent, False=balanced)
)


# Encoding/Decoding Settings
ENCODING_ENABLED = True  # Enable/disable encoding functionality
DECODING_ENABLED = True  # Enable/disable decoding functionality

# -> Security Tools Settings
# VirusTotal API Settings
VT_API_KEY = ""  # VirusTotal API key for malware scanning
VT_API_TIMEOUT = 500  # VirusTotal API timeout in seconds
VT_ENABLED = False  # Enable/disable VirusTotal functionality
VT_MAX_FILE_SIZE = 33554432  # Maximum file size for VirusTotal scanning in bytes (32MB)
# Phish Directory API Settings
PHISH_DIRECTORY_API_URL = "https://api.phish.directory"  # Phish Directory API base URL
PHISH_DIRECTORY_ENABLED = True  # Enable/disable Phish Directory functionality
PHISH_DIRECTORY_TIMEOUT = 30  # Phish Directory API timeout in seconds
PHISH_DIRECTORY_API_KEY = (
    ""  # Phish Directory API key (optional, for authenticated endpoints)
)
# WOT (Web of Trust) API Settings
WOT_API_URL = "https://scorecard.api.mywot.com"  # WOT API base URL
WOT_ENABLED = True  # Enable/disable WOT functionality
WOT_TIMEOUT = 30  # WOT API timeout in seconds
WOT_API_KEY = ""  # WOT API key (required for API access)
WOT_USER_ID = ""  # WOT User ID (required for API access)
# AbuseIPDB API Settings
ABUSEIPDB_API_URL = "https://api.abuseipdb.com/api/v2"  # AbuseIPDB API base URL
ABUSEIPDB_ENABLED = True  # Enable/disable AbuseIPDB functionality
ABUSEIPDB_TIMEOUT = 30  # AbuseIPDB API timeout in seconds
ABUSEIPDB_API_KEY = ""  # AbuseIPDB API key (required for API access)
ABUSEIPDB_MAX_AGE_DAYS = 90  # Maximum age of reports to consider (1-365 days)

# Weather Settings - OpenWeatherMap API
WEATHER_ENABLED = True  # Enable/disable weather functionality
OPENWEATHER_API_KEY = ""  # OpenWeatherMap API key
WEATHER_PLACE = "London,UK"  # Default weather location
AUTO_WEATHER = True  # Enable/disable automatic daily weather updates
WEATHER_RISK_NOTIFICATIONS = True  # Enable/disable weather risk notifications to owner
WEATHER_UNITS = "metric"  # Units: standard, metric, imperial
WEATHER_LANGUAGE = "en"  # Language code for weather descriptions
WEATHER_UPDATE_TIME = "08:00"  # Time for daily weather updates (HH:MM format)
WEATHER_TIMEZONE = "UTC"  # Timezone for weather updates

# Advanced Weather Features
WEATHER_SHOW_MAPS = True  # Enable/disable weather maps
WEATHER_SHOW_AIR_QUALITY = True  # Enable/disable air quality data
WEATHER_SHOW_FIRE_INDEX = (
    False  # Enable/disable fire weather index (requires special access)
)
WEATHER_HISTORICAL_DAYS = 7  # Days of historical data to show (requires paid plan)
WEATHER_FORECAST_DAYS = 5  # Days of forecast to show (max 5 for free plan)
WEATHER_MAP_ZOOM = 10  # Default zoom level for weather maps
WEATHER_IMAGE_QUALITY = "high"  # Image quality: low, medium, high
WEATHER_CACHE_DURATION = 600  # Cache duration in seconds (10 minutes)

# Weather Alert Settings
WEATHER_ALERT_TEMPERATURE_HIGH = 35.0  # High temperature alert threshold (Celsius)
WEATHER_ALERT_TEMPERATURE_LOW = -10.0  # Low temperature alert threshold (Celsius)
WEATHER_ALERT_WIND_SPEED = 15.0  # High wind speed alert threshold (m/s)
WEATHER_ALERT_VISIBILITY = 1000  # Low visibility alert threshold (meters)
WEATHER_ALERT_AQI = 3  # Air quality alert threshold (1-5 scale)
WEATHER_ALERT_FIRE_DANGER = 3  # Fire weather index alert threshold (0-5 scale)

# Weather Map Settings
WEATHER_MAP_LAYERS = [
    "temp_new",  # Temperature
    "precipitation_new",  # Precipitation
    "pressure_new",  # Pressure
    "wind_new",  # Wind
    "clouds_new",  # Clouds
]  # Available weather map layers
WEATHER_MAP_OPACITY = 0.6  # Map layer opacity (0.0-1.0)
WEATHER_USE_ADVANCED_MAPS = False  # Use Weather Maps 2.0 (requires paid plan)
WEATHER_USE_HOURLY_MAPS = (
    False  # Use Weather Maps 2.0 with 1-hour step (requires paid plan)
)

# Air Quality Settings
WEATHER_AQI_FORECAST_DAYS = 4  # Days of air quality forecast (max 4)
WEATHER_AQI_HISTORICAL_DAYS = 7  # Days of historical air quality data
WEATHER_SHOW_POLLUTANTS = [
    "co",
    "no",
    "no2",
    "o3",
    "so2",
    "pm2_5",
    "pm10",
    "nh3",
]  # Pollutants to display

# Premium Features Settings
WEATHER_HOURLY_FORECAST_HOURS = 96  # Hours of hourly forecast (max 96 for 4 days)
WEATHER_STATISTICAL_DATA = False  # Enable statistical weather data (requires paid plan)
WEATHER_ROAD_RISK_API = False  # Enable road risk API (requires paid plan)
WEATHER_SOLAR_IRRADIANCE = False  # Enable solar irradiance data (requires paid plan)

# Enhanced NSFW Detection Settings
NSFW_DETECTION_ENABLED = True  # Master toggle for NSFW detection
NSFW_DETECTION_SENSITIVITY = (
    "moderate"  # Detection sensitivity: strict, moderate, permissive
)
NSFW_KEYWORD_DETECTION = True  # Enable enhanced keyword detection with fuzzy matching
NSFW_VISUAL_DETECTION = (
    False  # Enable AI-powered visual content analysis (requires API keys)
)
NSFW_AUDIO_DETECTION = False  # Enable audio content analysis (experimental)
NSFW_FUZZY_MATCHING = True  # Enable fuzzy keyword matching for misspellings
NSFW_LEETSPEAK_DETECTION = True  # Detect leetspeak variations (p0rn, s3x, etc.)
NSFW_MULTI_LANGUAGE = True  # Enable multi-language keyword support
NSFW_CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence for NSFW detection (0.0-1.0)
NSFW_CACHE_DURATION = 3600  # Cache detection results for 1 hour (seconds)
NSFW_MAX_FILE_SIZE = 52428800  # Maximum file size for NSFW analysis (50MB)
NSFW_VIDEO_ANALYSIS = True  # Enable video frame analysis
NSFW_VIDEO_FRAME_COUNT = 5  # Number of frames to extract for analysis
NSFW_FRAME_QUALITY = 2  # Frame extraction quality (1-5, higher = better quality)
NSFW_AUDIO_ANALYSIS = True  # Enable audio content analysis
NSFW_SUBTITLE_ANALYSIS = True  # Enable subtitle text analysis

# NSFW Visual Analysis API Settings (choose one or more providers)
NSFW_GOOGLE_VISION_API_KEY = ""  # Google Cloud Vision API key for content safety
NSFW_AWS_ACCESS_KEY = ""  # AWS Rekognition access key
NSFW_AWS_SECRET_KEY = ""  # AWS Rekognition secret key
NSFW_AWS_REGION = "us-east-1"  # AWS region for Rekognition
NSFW_AZURE_ENDPOINT = ""  # Azure Content Moderator endpoint URL
NSFW_AZURE_KEY = ""  # Azure Content Moderator subscription key
NSFW_OPENAI_API_KEY = ""  # OpenAI API key for GPT-4 Vision analysis

# NSFW Text Analysis API Settings
NSFW_PERSPECTIVE_API_KEY = ""  # Google Perspective API key for toxicity detection
NSFW_OPENAI_MODERATION = False  # Use OpenAI moderation API for text analysis

# NSFW Behavior and Logging Settings
NSFW_LOG_DETECTIONS = True  # Log all NSFW detections for analysis and improvement
NSFW_STORE_METADATA = True  # Store detection metadata in database for tracking
NSFW_AUTO_DELETE = (
    False  # Automatically delete detected NSFW content (use with caution)
)
NSFW_NOTIFY_ADMINS = True  # Send notifications to admins when NSFW content is detected
TRUECALLER_API_URL = ""  # Truecaller API URL for phone number lookup

# Direct Link Generator Settings
TERABOX_PROXY = "https://teradlrobot.cheemsbackup.workers.dev/"  # Terabox proxy URL for bypassing restrictions

# Pastebin API Settings
PASTEBIN_API_KEY = (
    ""  # Pastebin Developer API Key (get from https://pastebin.com/doc_api)
)
PASTEBIN_ENABLED = False  # Enable/disable Pastebin functionality

# Bitly API Settings
BITLY_ACCESS_TOKEN = (
    ""  # Bitly API access token for link shortening (get from https://dev.bitly.com/)
)
BITLY_GROUP_GUID = ""  # Optional Bitly group GUID for organization

# TinyURL API Settings
TINYURL_API_TOKEN = ""  # TinyURL API token for link shortening (get from https://tinyurl.com/app/settings/api)

# Custom template for IMDB results formatting.
IMDB_TEMPLATE = """<b>🎬 Title:</b> <code>{title}</code> [{year}]
 <b>⭐ Rating:</b> <i>{rating}</i>
 <b>🎭 Genre:</b> {genres}
 <b>📅 Released:</b> <a href=\"{url_releaseinfo}\">{release_date}</a>
 <b>🎙️ Languages:</b> {languages}
 <b>🌍 Country:</b> {countries}
 <b>🎬 Type:</b> {kind}

 <b>📖 Story Line:</b>
 <blockquote>{plot}</blockquote>

 <b>🔗 IMDb URL:</b> <a href=\"{url}\">{url}</a>
 <b>👥 Cast:</b> <a href=\"{url_cast}\">{cast}</a>

 <b>👨‍💼 Director:</b> {director}
 <b>✍️ Writer:</b> {writer}
 <b>🎵 Music:</b> {composer}
 <b>🎥 Cinematography:</b> {cinematographer}

 <b>⏱️ Runtime:</b> {runtime} minutes
 <b>🏆 Awards:</b> {certificates}
 <i>Powered by IMDb</i>"""

# TMDB API Settings
TMDB_API_KEY = ""  # TMDB API key from https://www.themoviedb.org/settings/api
TMDB_LANGUAGE = "en-US"  # Language for TMDB results (e.g., en-US, es-ES, fr-FR)
TMDB_REGION = "US"  # Region for TMDB results (e.g., US, GB, IN)
# Note: Adult content is always excluded, cache duration is hardcoded to 1 hour

# Cat API Settings
CAT_API_KEY = ""  # The Cat API key from https://thecatapi.com/ (optional, but recommended for full features)

# Streamrip Settings
STREAMRIP_ENABLED = True  # Enable/disable streamrip feature
STREAMRIP_CONCURRENT_DOWNLOADS = 4  # Concurrent downloads per platform
STREAMRIP_MAX_SEARCH_RESULTS = 20  # Search results limit
STREAMRIP_ENABLE_DATABASE = False  # Enable download history tracking
STREAMRIP_AUTO_CONVERT = True  # Enable automatic format conversion

# Streamrip Quality and Format Settings
STREAMRIP_DEFAULT_QUALITY = (
    3  # Default quality (0-4: 0=128kbps, 1=320kbps, 2=CD, 3=Hi-Res, 4=Hi-Res+)
)
STREAMRIP_FALLBACK_QUALITY = 2  # Fallback if preferred quality unavailable
STREAMRIP_DEFAULT_CODEC = "flac"  # Default output format
STREAMRIP_SUPPORTED_CODECS = [
    "flac",
    "mp3",
    "m4a",
    "ogg",
    "opus",
]  # Available formats
STREAMRIP_QUALITY_FALLBACK_ENABLED = True  # Auto-fallback to lower quality

# Streamrip Platform Settings
STREAMRIP_QOBUZ_ENABLED = True  # Enable Qobuz downloads
STREAMRIP_QOBUZ_QUALITY = (
    3  # Qobuz quality level (0-4: 0=320kbps, 1=16/44.1, 2=24/≤96, 3=24/≥96, 4=24/≥96)
)
STREAMRIP_TIDAL_ENABLED = True  # Enable Tidal downloads
STREAMRIP_TIDAL_QUALITY = 3  # Tidal quality level (0-3)
STREAMRIP_DEEZER_ENABLED = True  # Enable Deezer downloads
STREAMRIP_DEEZER_QUALITY = 2  # Deezer quality level (0-2)
STREAMRIP_SOUNDCLOUD_ENABLED = True  # Enable SoundCloud downloads
STREAMRIP_SOUNDCLOUD_QUALITY = 0  # SoundCloud quality level
STREAMRIP_LASTFM_ENABLED = True  # Enable Last.fm playlist conversion
STREAMRIP_YOUTUBE_QUALITY = 0  # YouTube quality level

# Streamrip Authentication (stored securely in database)
# Qobuz - Highest quality platform (up to 24-bit/192kHz)
STREAMRIP_QOBUZ_EMAIL = ""  # Qobuz account email
STREAMRIP_QOBUZ_PASSWORD = ""  # Qobuz account password
STREAMRIP_QOBUZ_APP_ID = ""  # Qobuz app ID (get via 'python dev/get_qobuz_keys.py')
STREAMRIP_QOBUZ_SECRETS = (
    []
)  # Qobuz secrets array (get via 'python dev/get_qobuz_keys.py')

# Tidal - Hi-Res/MQA platform (OAuth tokens preferred)
STREAMRIP_TIDAL_ACCESS_TOKEN = (
    ""  # Tidal access token (get via 'python dev/tidal_tokens.py')
)
STREAMRIP_TIDAL_REFRESH_TOKEN = (
    ""  # Tidal refresh token (get via 'python dev/tidal_tokens.py')
)
STREAMRIP_TIDAL_USER_ID = ""  # Tidal user ID (get via 'python dev/tidal_tokens.py')
STREAMRIP_TIDAL_COUNTRY_CODE = ""  # Tidal country code (e.g., 'US')
STREAMRIP_TIDAL_TOKEN_EXPIRY = ""  # Tidal token expiry timestamp (optional)
# Fallback authentication (limited functionality)
STREAMRIP_TIDAL_EMAIL = ""  # Tidal email (fallback method)
STREAMRIP_TIDAL_PASSWORD = ""  # Tidal password (fallback method)

# Deezer - CD quality platform
STREAMRIP_DEEZER_ARL = ""  # Deezer ARL cookie (get from browser cookies)

# SoundCloud - Free platform (optional authentication)
STREAMRIP_SOUNDCLOUD_CLIENT_ID = ""  # SoundCloud client ID (optional)
STREAMRIP_SOUNDCLOUD_APP_VERSION = ""  # SoundCloud app version (optional)

# Streamrip Advanced Features
STREAMRIP_METADATA_EXCLUDE = (
    []
)  # Metadata tags to exclude (e.g., ["genre", "albumartist"])
STREAMRIP_FILENAME_TEMPLATE = ""  # Custom filename template
STREAMRIP_FOLDER_TEMPLATE = ""  # Custom folder structure template
STREAMRIP_EMBED_COVER_ART = True  # Embed album artwork in files
STREAMRIP_SAVE_COVER_ART = True  # Save separate cover art files
STREAMRIP_COVER_ART_SIZE = "large"  # Cover art size preference

# Streamrip Download Configuration
STREAMRIP_MAX_CONNECTIONS = 6  # Maximum connections per download
STREAMRIP_REQUESTS_PER_MINUTE = 60  # API requests per minute limit
STREAMRIP_SOURCE_SUBDIRECTORIES = False  # Create source subdirectories
STREAMRIP_DISC_SUBDIRECTORIES = True  # Create disc subdirectories
STREAMRIP_CONCURRENCY = True  # Enable concurrent downloads
STREAMRIP_VERIFY_SSL = True  # Verify SSL certificates

# Streamrip Platform-Specific Configuration
STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS = True  # Download PDF booklets from Qobuz
STREAMRIP_QOBUZ_USE_AUTH_TOKEN = False  # Use authentication token for Qobuz
STREAMRIP_TIDAL_DOWNLOAD_VIDEOS = True  # Download videos from Tidal
STREAMRIP_DEEZER_USE_DEEZLOADER = True  # Use Deezloader for Deezer
STREAMRIP_DEEZER_DEEZLOADER_WARNINGS = True  # Show Deezloader warnings
STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS = False  # Download videos from YouTube
STREAMRIP_YOUTUBE_VIDEO_FOLDER = ""  # YouTube video download folder
STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER = ""  # YouTube video downloads folder

# Streamrip Database Configuration
STREAMRIP_DATABASE_DOWNLOADS_ENABLED = True  # Enable downloads database
STREAMRIP_DATABASE_DOWNLOADS_PATH = "./downloads.db"  # Downloads database path
STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED = True  # Enable failed downloads database
STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH = (
    "./failed_downloads.db"  # Failed downloads database path
)

# Streamrip Conversion Configuration
STREAMRIP_CONVERSION_ENABLED = False  # Enable format conversion
STREAMRIP_CONVERSION_CODEC = "ALAC"  # Conversion codec
STREAMRIP_CONVERSION_SAMPLING_RATE = 48000  # Conversion sampling rate
STREAMRIP_CONVERSION_BIT_DEPTH = 24  # Conversion bit depth
STREAMRIP_CONVERSION_LOSSY_BITRATE = 320  # Lossy conversion bitrate

# Streamrip Filters and Metadata
STREAMRIP_QOBUZ_FILTERS_EXTRAS = False  # Filter extra content from Qobuz
STREAMRIP_QOBUZ_FILTERS_REPEATS = False  # Filter repeat content
STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS = False  # Filter non-album content
STREAMRIP_QOBUZ_FILTERS_FEATURES = False  # Filter featured content
STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS = False  # Filter non-studio albums
STREAMRIP_QOBUZ_FILTERS_NON_REMASTER = False  # Filter non-remaster content
STREAMRIP_ARTWORK_EMBED_MAX_WIDTH = -1  # Max width for embedded artwork (-1 = no limit)
STREAMRIP_ARTWORK_SAVED_MAX_WIDTH = -1  # Max width for saved artwork (-1 = no limit)


STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM = True  # Set playlist as album in metadata
STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS = True  # Renumber playlist tracks

# Streamrip File Paths and Naming
STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER = False  # Add singles to folder
STREAMRIP_FILEPATHS_FOLDER_FORMAT = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"  # Folder naming format template
STREAMRIP_FILEPATHS_TRACK_FORMAT = (
    "{tracknumber:02}. {artist} - {title}{explicit}"  # Track naming format template
)
STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS = (
    False  # Restrict special characters in filenames
)
STREAMRIP_FILEPATHS_TRUNCATE_TO = 120  # Truncate filenames to length

# Streamrip Last.fm and CLI Configuration
STREAMRIP_LASTFM_SOURCE = "qobuz"  # Last.fm source platform
STREAMRIP_LASTFM_FALLBACK_SOURCE = ""  # Last.fm fallback source platform
STREAMRIP_CLI_TEXT_OUTPUT = True  # Enable CLI text output
STREAMRIP_CLI_PROGRESS_BARS = False  # Show CLI progress bars (disabled for bot)
STREAMRIP_CLI_MAX_SEARCH_RESULTS = 200  # Max CLI search results

# Streamrip Miscellaneous
STREAMRIP_MISC_CHECK_FOR_UPDATES = True  # Check for streamrip updates
STREAMRIP_MISC_VERSION = "2.0.6"  # Streamrip version

# Zotify Settings - Spotify Music Downloader
ZOTIFY_ENABLED = True  # Enable/disable Zotify feature for Spotify downloads

# Zotify Authentication
ZOTIFY_CREDENTIALS_PATH = (
    "./zotify_credentials.json"  # Path to Spotify credentials file
)

# Zotify Library Paths - Where downloaded content is organized
ZOTIFY_ALBUM_LIBRARY = "Music/Zotify Albums"  # Directory for album downloads
ZOTIFY_PODCAST_LIBRARY = "Music/Zotify Podcasts"  # Directory for podcast downloads
ZOTIFY_PLAYLIST_LIBRARY = (
    "Music/Zotify Playlists"  # Directory for playlist downloads
)

# Zotify Output Templates - How files and folders are named
ZOTIFY_OUTPUT_ALBUM = "{album_artist}/{album}/{track_number}. {artists} - {title}"  # Album track naming template
ZOTIFY_OUTPUT_PLAYLIST_TRACK = (
    "{playlist}/{artists} - {title}"  # Playlist track naming template
)
ZOTIFY_OUTPUT_PLAYLIST_EPISODE = (
    "{playlist}/{episode_number} - {title}"  # Playlist episode naming template
)
ZOTIFY_OUTPUT_PODCAST = (
    "{podcast}/{episode_number} - {title}"  # Podcast episode naming template
)
ZOTIFY_OUTPUT_SINGLE = (
    "{artists} - {title}"  # Single track naming template (not in albums)
)

# Zotify Quality and Format Settings
ZOTIFY_DOWNLOAD_QUALITY = "auto"  # Download quality: auto, normal, high, very_high
ZOTIFY_AUDIO_FORMAT = "vorbis"  # Output audio format: vorbis, mp3, flac, aac, fdk_aac, opus, wav, wavpack
ZOTIFY_ARTWORK_SIZE = "large"  # Album artwork size: small, medium, large
ZOTIFY_TRANSCODE_BITRATE = (
    -1
)  # Transcoding bitrate in kbps (-1 to use download rate)

# Zotify Download Settings
ZOTIFY_DOWNLOAD_REAL_TIME = (
    False  # Download at the same rate as track playback (slower but more stable)
)
ZOTIFY_REPLACE_EXISTING = False  # Replace existing files when downloading
ZOTIFY_SKIP_DUPLICATES = True  # Skip downloading duplicate tracks
ZOTIFY_SKIP_PREVIOUS = True  # Skip tracks that were previously downloaded

# Zotify Metadata and Files
ZOTIFY_SAVE_METADATA = True  # Save metadata tags to downloaded files
ZOTIFY_SAVE_GENRE = False  # Include genre information in metadata
ZOTIFY_ALL_ARTISTS = True  # Include all artists in metadata (not just main artist)
ZOTIFY_LYRICS_FILE = False  # Save lyrics as separate .lrc files
ZOTIFY_LYRICS_ONLY = False  # Download only lyrics without audio
ZOTIFY_SAVE_SUBTITLES = False  # Save subtitles for podcast episodes
ZOTIFY_CREATE_PLAYLIST_FILE = True  # Create .m3u playlist files for playlists

# Zotify FFmpeg Settings
ZOTIFY_FFMPEG_PATH = ""  # FFmpeg binary path or name (empty = use 'xtra', can be full path like '/usr/bin/ffmpeg' or just 'ffmpeg')
ZOTIFY_FFMPEG_ARGS = ""  # Additional FFmpeg arguments for transcoding

# Zotify Language and Locale
ZOTIFY_LANGUAGE = "en"  # Language code for metadata and interface

# Zotify Print/Logging Settings
ZOTIFY_PRINT_PROGRESS = True  # Show download progress in logs
ZOTIFY_PRINT_DOWNLOADS = False  # Print download start messages
ZOTIFY_PRINT_ERRORS = True  # Print error messages
ZOTIFY_PRINT_WARNINGS = True  # Print warning messages
ZOTIFY_PRINT_SKIPS = False  # Print skip messages for existing files

# Zotify Match Functionality
ZOTIFY_MATCH_EXISTING = False  # Match existing files for skip functionality

# Zotify Supported Formats (for validation)
ZOTIFY_SUPPORTED_AUDIO_FORMATS = [
    "vorbis",
    "mp3",
    "flac",
    "aac",
    "fdk_aac",
    "opus",
    "wav",
    "wavpack",
]
ZOTIFY_SUPPORTED_QUALITIES = [
    "auto",
    "normal",
    "high",
    "very_high",
]
ZOTIFY_SUPPORTED_ARTWORK_SIZES = [
    "small",
    "medium",
    "large",
]

# Music Download Configuration (qobuz-dl, tidal-dl-ng, gamdl and deezspot)
MUSICDL_ENABLED: bool = True  # Enable/disable music download functionality
MUSICDL_LYRICS_ENABLED: bool = (
    True  # Enable/disable lyrics embedding in downloaded music files
)

# Tidal Authentication (for tidal-dl-ng)TIDAL_ACCESS_TOKEN: str = ""  # Tidal access token (OAuth)
TIDAL_REFRESH_TOKEN: str = ""  # Tidal refresh token (OAuth)
TIDAL_EXPIRY_TIME: float = 0.0  # Token expiry timestamp

# Tidal-dl-ng Quality Settings
TIDAL_QUALITY_AUDIO: str = (
    "HI_RES_LOSSLESS"  # HI_RES_LOSSLESS, LOSSLESS, HI_FI, HIGH
)
TIDAL_QUALITY_VIDEO: str = "HIGH"  # HIGH (720p), MEDIUM (480p), LOW (360p)

# Tidal-dl-ng Download Settings
TIDAL_DOWNLOAD_BASE_PATH: str = (
    ""  # Base download directory (empty = use bot default)
)
TIDAL_DOWNLOADS_CONCURRENT_MAX: int = 3  # Max concurrent downloads (1-10)
TIDAL_DOWNLOADS_SIMULTANEOUS_PER_TRACK_MAX: int = 20  # Chunks per track (1-20)
TIDAL_DOWNLOAD_DELAY: bool = False  # Enable randomized download delays
TIDAL_DOWNLOAD_DELAY_SEC_MIN: float = 3.0  # Minimum delay in seconds
TIDAL_DOWNLOAD_DELAY_SEC_MAX: float = 5.0  # Maximum delay in seconds

# Tidal-dl-ng Audio Processing
TIDAL_EXTRACT_FLAC: bool = True  # Extract FLAC from MP4 containers
TIDAL_LYRICS_EMBED: bool = True  # Embed lyrics in audio files
TIDAL_LYRICS_FILE: bool = True  # Save lyrics to separate .lrc files
TIDAL_METADATA_COVER_EMBED: bool = True  # Embed album cover into files
TIDAL_COVER_ALBUM_FILE: bool = True  # Save cover as cover.jpg
TIDAL_METADATA_REPLAY_GAIN: bool = True  # Add replay gain metadata
TIDAL_METADATA_COVER_DIMENSION: int = 320  # Cover size: 320, 640, 1280

# Tidal-dl-ng Advanced Options
TIDAL_SKIP_EXISTING: bool = False  # Skip already downloaded files
TIDAL_SYMLINK_TO_TRACK: bool = False  # Use symlinks instead of copies
TIDAL_PLAYLIST_CREATE: bool = False  # Create .m3u8 playlist files
TIDAL_VIDEO_DOWNLOAD: bool = False  # Enable video downloads
TIDAL_VIDEO_CONVERT_MP4: bool = True  # Convert TS videos to MP4

# Tidal-dl-ng Binary Paths
TIDAL_PATH_BINARY_FFMPEG: str = "/usr/bin/xtra"  # Path to ffmpeg binary
TIDAL_PATH_BINARY_FFPROBE: str = "/usr/bin/ffprobe"  # Path to ffprobe binary

# Tidal-dl-ng Format Templates (matching tidal-dl-ng defaults)
TIDAL_FORMAT_ALBUM: str = (
    "Albums/{album_artist} - {album_title}{album_explicit}/{track_volume}{artist_name} - {track_title}{album_explicit}"
)
TIDAL_FORMAT_TRACK: str = "Tracks/{artist_name} - {track_title}{track_explicit}"
TIDAL_FORMAT_PLAYLIST: str = (
    "Playlists/{playlist_name}/{list_pos}. {artist_name} - {track_title}" )
TIDAL_FORMAT_MIX: str = "Mix/{mix_name}/{artist_name} - {track_title}"
TIDAL_FORMAT_VIDEO: str = "Videos/{artist_name} - {track_title}{track_explicit}"

# Tidal-dl-ng Additional Settings
TIDAL_ALBUM_TRACK_NUM_PAD_MIN: int = (
    1  # Minimum length of album track count padding (1 = no padding)
)

# Tidal-dl-ng Dolby Atmos Support
TIDAL_DOLBY_ATMOS_ENABLED: bool = (
    False  # Enable Dolby Atmos downloads (requires Fire TV device auth)
)

# Qobuz Authentication (for qobuz-dl)
QOBUZ_EMAIL: str = ""  # Qobuz account email
QOBUZ_PASSWORD: str = ""  # Qobuz account password

# Qobuz-dl Advanced Settings (matching qobuz-dl library defaults)
QOBUZ_DEFAULT_QUALITY: int = (
     27  # 5=320kbps, 6=CD FLAC (default), 7=24bit<=96kHz, 27=24bit>96kHz
)
QOBUZ_DEFAULT_LIMIT: int = 20  # Search results limit (qobuz-dl default)
QOBUZ_NO_FALLBACK: bool = (
    False  # Disable quality fallback (qobuz-dl default: false)
)
QOBUZ_ALBUMS_ONLY: bool = (
    False  # Don't download singles/EPs (qobuz-dl default: false)
)
QOBUZ_SMART_DISCOGRAPHY: bool = (
    False  # Filter spam albums (qobuz-dl default: false)
 )
QOBUZ_OG_COVER: bool = (
    True  # Download original quality cover (qobuz-dl default: false)
)
QOBUZ_EMBED_ART: bool = True  # Embed cover art into files (qobuz-dl default: false)
QOBUZ_NO_COVER: bool = False  # Don't download cover art (qobuz-dl default: false)
QOBUZ_NO_M3U: bool = False  # Don't create .m3u files (qobuz-dl default: false)
QOBUZ_NO_DATABASE: bool = True  # Don't use database (qobuz-dl default: false)

# Qobuz-dl Format Templates (qobuz-dl defaults)
QOBUZ_FOLDER_FORMAT: str = (
    "{artist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]"  # Default folder format
)
QOBUZ_TRACK_FORMAT: str = "{tracknumber}. {tracktitle}"  # Default track format

# Apple Music (gamdl) Authentication & Basic Settings
APPLE_COOKIES_PATH: str = (
    "cookies.txt"  # Path to Apple Music cookies file (Netscape format, upload via Private Files)
 )
APPLE_OUTPUT_PATH: str = "./Apple Music"  # Default output directory
APPLE_TEMP_PATH: str = "./temp"  # Temporary files directory
APPLE_LANGUAGE: str = "en-US"  # Metadata language (ISO-2A language code)
APPLE_LOG_LEVEL: str = "INFO"  # Log level (DEBUG, INFO, WARNING, ERROR)

# Apple Music Download Settings
APPLE_DISABLE_MUSIC_VIDEO_SKIP: bool = (
    False  # Don't skip downloading music videos in albums/playlists
)
APPLE_SAVE_COVER: bool = (
    False  # Save cover as a separate file (gamdl default: false)
)
APPLE_OVERWRITE: bool = False  # Overwrite existing files
APPLE_SAVE_PLAYLIST: bool = (
    False  # Save M3U8 playlist file when downloading a playlist
)
APPLE_SYNCED_LYRICS_ONLY: bool = False  # Download only the synced lyrics
APPLE_NO_SYNCED_LYRICS: bool = False  # Don't download the synced lyrics
APPLE_NO_EXCEPTIONS: bool = False  # Don't print exceptions
APPLE_READ_URLS_AS_TXT: bool = (
    False  # Interpret URLs as paths to text files containing URLs
)
APPLE_NO_CONFIG_FILE: bool = False  # Don't use gamdl config file

# Apple Music Quality & Format Settings
APPLE_CODEC_SONG: str = (
    "aac-legacy"  # Song codec (aac-legacy, aac-he-legacy, aac, alac, atmos, etc.)
)
APPLE_CODEC_MUSIC_VIDEO: str = "h264"  # Music video codec (h264, h265, ask)
APPLE_SYNCED_LYRICS_FORMAT: str = "lrc"  # Synced lyrics format (lrc, srt, ttml)
APPLE_COVER_FORMAT: str = "jpg"  # Cover format (jpg, png, raw)
APPLE_COVER_SIZE: int = 1200  # Cover size in pixels
APPLE_QUALITY_POST: str = "best"  # Post video quality (best, ask)
APPLE_DOWNLOAD_MODE: str = "ytdlp"  # Download mode (ytdlp, nm3u8dlre)
APPLE_REMUX_MODE: str = "ffmpeg"  # Remux mode (ffmpeg, mp4box)
APPLE_REMUX_FORMAT_MUSIC_VIDEO: str = "m4v"  # Music video remux format (m4v, mp4)

# Apple Music Template Settings
APPLE_TEMPLATE_FOLDER_ALBUM: str = (
    "{album_artist}/{album}"  # Template folder for album tracks
)
APPLE_TEMPLATE_FOLDER_COMPILATION: str = (
    "Compilations/{album}"  # Template folder for compilation albums
)
APPLE_TEMPLATE_FILE_SINGLE_DISC: str = (
    "{track:02d} {title}"  # Template file for single-disc albums
)
APPLE_TEMPLATE_FILE_MULTI_DISC: str = (
    "{disc}-{track:02d} {title}"  # Template file for multi-disc albums
)
APPLE_TEMPLATE_FOLDER_NO_ALBUM: str = (
    "{artist}/Unknown Album"  # Template folder for non-album tracks
)
APPLE_TEMPLATE_FILE_NO_ALBUM: str = "{title}"  # Template file for non-album tracks
APPLE_TEMPLATE_FILE_PLAYLIST: str = (
    "Playlists/{playlist_title}"  # Template file for M3U8 playlists
)
APPLE_TEMPLATE_DATE: str = "%Y-%m-%dT%H:%M:%SZ"  # Date tag template

# Apple Music Binary Paths
APPLE_FFMPEG_PATH: str = "xtra"  # Path to FFmpeg binary (gamdl default: ffmpeg)
APPLE_MP4DECRYPT_PATH: str = "xmp4dec"  # Path to mp4decrypt binary
APPLE_MP4BOX_PATH: str = "xmp4"  # Path to MP4Box binary
APPLE_NM3U8DLRE_PATH: str = "xm3u8"  # Path to N_m3u8DL-RE binary
APPLE_WVD_PATH: str = ""  # Path to .wvd file (empty = not used)

# Apple Music Advanced Settings
APPLE_EXCLUDE_TAGS: str = ""  # Comma-separated tags to exclude
APPLE_TRUNCATE: int = 0  # Maximum length of file/folder names (0 = no truncation)

# Deezer Configuration
DEEZER_ARL = ""  # Deezer ARL token from browser cookies (required for Deezer downloads)
DEEZER_EMAIL = ""  # Deezer email (optional, can be empty if using ARL)
DEEZER_PASSWORD = ""  # Deezer password (optional, can be empty if using ARL)
DEEZER_QUALITY = (
    "FLAC"  # Download quality: MP3_128, MP3_320, FLAC (FLAC requires premium)
)
DEEZER_TAGS_SEPARATOR = " / "  # Separator for multiple tags
DEEZER_RECURSIVE_QUALITY = (
    True  # Try lower quality if requested quality is not available
)
DEEZER_RECURSIVE_DOWNLOAD = False  # Enable recursive download for related content
DEEZER_ENSURE_PREMIUM = False  # Require premium account for downloads (strict mode)

# Spotify Configuration
SPOTIFY_CREDENTIALS_PATH = "./spotify_credentials.json"  # Path to Spotify credentials file
SPOTIFY_CLIENT_ID = ""  # Spotify client ID (optional)
SPOTIFY_CLIENT_SECRET = ""  # Spotify client secret (optional)
SPOTIFY_QUALITY = "VERY_HIGH"  # Download quality: NORMAL, HIGH, VERY_HIGH
SPOTIFY_RECURSIVE_QUALITY = (
    True  # Try lower quality if requested quality is not available
)
SPOTIFY_RECURSIVE_DOWNLOAD = False  # Enable recursive download for related content
SPOTIFY_NOT_INTERFACE = False  # Disable interface mode
SPOTIFY_METHOD_SAVE = 3  # Save method (0=CD/Track, 1=Artist-Title, 2=Artist-Title[ISRC], 3=Disc|Track-Title-Artist)
SPOTIFY_MAKE_ZIP = False  # Create ZIP files for albums/playlists
SPOTIFY_IS_THREAD = False  # Enable threaded downloads (experimental, may cause issues)

# Gallery-dl Settings - Multi-platform Media Downloader
GALLERY_DL_ENABLED = True  # Enable/disable gallery-dl feature for 200+ platforms
GALLERY_DL_OPTIONS = {}  # Gallery-dl configuration options as dictionary
GALLERY_DL_QUALITY_SELECTION = True  # Enable interactive quality selection
GALLERY_DL_MAX_DOWNLOADS = 50  # Maximum files per download (0 = unlimited)
GALLERY_DL_RATE_LIMIT = "1/s"  # Rate limit (requests per second, e.g., "2/s", "1/2s")
GALLERY_DL_ARCHIVE_ENABLED = True  # Enable archive to avoid re-downloading
GALLERY_DL_METADATA_ENABLED = True  # Save metadata files (JSON, YAML, TXT)

# Gallery-dl Authentication Settings
# Instagram - For private accounts and stories
GALLERY_DL_INSTAGRAM_USERNAME = ""  # Instagram username
GALLERY_DL_INSTAGRAM_PASSWORD = ""  # Instagram password

# Twitter/X - For private accounts and higher quality
GALLERY_DL_TWITTER_USERNAME = ""  # Twitter username
GALLERY_DL_TWITTER_PASSWORD = ""  # Twitter password

# Reddit - For private subreddits and enhanced access
GALLERY_DL_REDDIT_CLIENT_ID = ""  # Reddit app client ID
GALLERY_DL_REDDIT_CLIENT_SECRET = ""  # Reddit app client secret
GALLERY_DL_REDDIT_USERNAME = ""  # Reddit username
GALLERY_DL_REDDIT_PASSWORD = ""  # Reddit password
GALLERY_DL_REDDIT_REFRESH_TOKEN = ""  # Reddit refresh token

# Pixiv - For following artists and premium content
GALLERY_DL_PIXIV_USERNAME = ""  # Pixiv username
GALLERY_DL_PIXIV_PASSWORD = ""  # Pixiv password
GALLERY_DL_PIXIV_REFRESH_TOKEN = ""  # Pixiv refresh token

# DeviantArt - For premium content and Eclipse features
GALLERY_DL_DEVIANTART_CLIENT_ID = ""  # DeviantArt app client ID
GALLERY_DL_DEVIANTART_CLIENT_SECRET = ""  # DeviantArt app client secret
GALLERY_DL_DEVIANTART_USERNAME = ""  # DeviantArt username
GALLERY_DL_DEVIANTART_PASSWORD = ""  # DeviantArt password

# Tumblr - For enhanced access and API features
GALLERY_DL_TUMBLR_API_KEY = ""  # Tumblr API key
GALLERY_DL_TUMBLR_API_SECRET = ""  # Tumblr API secret
GALLERY_DL_TUMBLR_TOKEN = ""  # Tumblr access token
GALLERY_DL_TUMBLR_TOKEN_SECRET = ""  # Tumblr access token secret

# Discord - For server content
GALLERY_DL_DISCORD_TOKEN = ""  # Discord bot token

# MEGA Settings
MEGA_ENABLED = True  # Enable/disable Mega.nz downloads
MEGA_EMAIL = ""  # Mega.nz account email (optional, for premium features)
MEGA_PASSWORD = ""  # Mega.nz account password (optional, for premium features)

# MEGA Upload Settings
MEGA_UPLOAD_ENABLED = True  # Enable MEGA upload functionality
MEGA_UPLOAD_PUBLIC = True  # Generate public links by default
MEGA_UPLOAD_THUMBNAIL = True  # Generate thumbnails for videos using FFmpeg

# MEGA Search Settings
MEGA_SEARCH_ENABLED = True  # Enable/disable MEGA search functionality


# YouTube Upload Settings
YOUTUBE_UPLOAD_ENABLED = False  # Enable/disable YouTube upload feature
YOUTUBE_UPLOAD_DEFAULT_PRIVACY = (
    "unlisted"  # Default privacy setting: public, unlisted, private
)
YOUTUBE_UPLOAD_DEFAULT_CATEGORY = "22"  # Default category ID (22 = People & Blogs)
YOUTUBE_UPLOAD_DEFAULT_TAGS = ""  # Default tags for uploaded videos, separated by comma
YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION = (
    "Uploaded by Aeon"  # Default description for uploaded videos
)
YOUTUBE_UPLOAD_DEFAULT_TITLE = ""  # Default title template (empty = use filename)
# Title template supports variables: {filename}, {date}, {time}, {size}
# Examples:
# "{filename} - {date}" -> "Video.mp4 - 2024-01-15"
# "My Channel - {filename}" -> "My Channel - Video.mp4"
# "" (empty) -> Uses cleaned filename as title

# Advanced YouTube API Settings
YOUTUBE_UPLOAD_DEFAULT_LANGUAGE = (
    "en"  # Default language for video metadata (ISO 639-1 code)
)
YOUTUBE_UPLOAD_DEFAULT_LICENSE = (
    "youtube"  # License: youtube (standard) or creativeCommon
)
YOUTUBE_UPLOAD_EMBEDDABLE = True  # Allow video to be embedded on other websites
YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE = True  # Allow public to see video statistics
YOUTUBE_UPLOAD_MADE_FOR_KIDS = False  # Mark videos as made for kids (COPPA compliance)
YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS = True  # Notify subscribers when video is uploaded
YOUTUBE_UPLOAD_LOCATION_DESCRIPTION = ""  # Location description for videos
YOUTUBE_UPLOAD_RECORDING_DATE = (
    ""  # Recording date (YYYY-MM-DD format, empty = upload date)
)


YOUTUBE_UPLOAD_AUTO_LEVELS = False  # Auto-enhance video levels
YOUTUBE_UPLOAD_STABILIZE = False  # Auto-stabilize shaky videos

# Global metadata settings
METADATA_KEY = ""  # Legacy metadata key
METADATA_ALL = ""  # Global metadata for all fields
METADATA_TITLE = ""  # Global title metadata
METADATA_AUTHOR = ""  # Global author metadata
METADATA_COMMENT = ""  # Global comment metadata

# Video track metadata
METADATA_VIDEO_TITLE = ""  # Video track title metadata
METADATA_VIDEO_AUTHOR = ""  # Video track author metadata
METADATA_VIDEO_COMMENT = ""  # Video track comment metadata

# Audio track metadata
METADATA_AUDIO_TITLE = ""  # Audio track title metadata
METADATA_AUDIO_AUTHOR = ""  # Audio track author metadata
METADATA_AUDIO_COMMENT = ""  # Audio track comment metadata

# Subtitle track metadata
METADATA_SUBTITLE_TITLE = ""  # Subtitle track title metadata
METADATA_SUBTITLE_AUTHOR = ""  # Subtitle track author metadata
METADATA_SUBTITLE_COMMENT = ""  # Subtitle track comment metadata


# Media Tools - Advanced Processing
# Compression Settings
COMPRESSION_ENABLED = False  # Enable compression functionality
COMPRESSION_PRIORITY = 4  # Compression task priority
COMPRESSION_DELETE_ORIGINAL = True  # Delete original files after compression

# Video Compression Settings
COMPRESSION_VIDEO_ENABLED = False  # Enable video compression
COMPRESSION_VIDEO_CODEC = "libx264"  # Video codec for compression
COMPRESSION_VIDEO_PRESET = "medium"  # Video encoding preset
COMPRESSION_VIDEO_CRF = 23  # Constant Rate Factor for video quality
COMPRESSION_VIDEO_BITRATE = "none"  # Video bitrate for compression
COMPRESSION_VIDEO_RESOLUTION = "none"  # Target resolution for video compression
COMPRESSION_VIDEO_FPS = "none"  # Target frame rate for video compression

# Audio Compression Settings
COMPRESSION_AUDIO_ENABLED = False  # Enable audio compression
COMPRESSION_AUDIO_CODEC = "aac"  # Audio codec for compression
COMPRESSION_AUDIO_BITRATE = "128k"  # Audio bitrate for compression
COMPRESSION_AUDIO_QUALITY = "none"  # Audio quality setting
COMPRESSION_AUDIO_CHANNELS = "none"  # Audio channel configuration
COMPRESSION_AUDIO_SAMPLE_RATE = "none"  # Audio sample rate

# Image Compression Settings
COMPRESSION_IMAGE_ENABLED = False  # Enable image compression
COMPRESSION_IMAGE_QUALITY = 85  # Image compression quality (1-100)
COMPRESSION_IMAGE_FORMAT = "none"  # Output format for image compression
COMPRESSION_IMAGE_RESIZE = "none"  # Resize dimensions for images

# Archive Compression Settings
COMPRESSION_ARCHIVE_ENABLED = False  # Enable archive compression
COMPRESSION_ARCHIVE_LEVEL = 6  # Compression level (0-9)
COMPRESSION_ARCHIVE_PASSWORD = "none"  # Password for archive protection
COMPRESSION_ARCHIVE_ALGORITHM = "none"  # Archive algorithm (e.g., 7z, zip)

# Trim Settings
TRIM_ENABLED = False  # Enable trim functionality
TRIM_PRIORITY = 5  # Trim task priority
TRIM_START_TIME = "00:00:00"  # Start time for trimming
TRIM_END_TIME = ""  # End time for trimming
TRIM_DELETE_ORIGINAL = False  # Delete original files after trimming

# Video Trim Settings
TRIM_VIDEO_ENABLED = False  # Enable video trimming
TRIM_VIDEO_CODEC = "none"  # Video codec for trimming
TRIM_VIDEO_PRESET = "none"  # Video encoding preset
TRIM_VIDEO_FORMAT = "none"  # Output format for video trimming
TRIM_VIDEO_QUALITY = "none"  # Video quality setting
TRIM_VIDEO_BITRATE = "none"  # Video bitrate for trimming
TRIM_VIDEO_RESOLUTION = "none"  # Video resolution for trimming
TRIM_VIDEO_FPS = "none"  # Video frame rate for trimming

# Audio Trim Settings
TRIM_AUDIO_ENABLED = False  # Enable audio trimming
TRIM_AUDIO_CODEC = "none"  # Audio codec for trimming
TRIM_AUDIO_BITRATE = "none"  # Audio bitrate for trimming
TRIM_AUDIO_QUALITY = "none"  # Audio quality setting
TRIM_AUDIO_CHANNELS = "none"  # Audio channel configuration
TRIM_AUDIO_SAMPLE_RATE = "none"  # Audio sample rate

# Image Trim Settings
TRIM_IMAGE_ENABLED = False  # Enable image trimming
TRIM_IMAGE_QUALITY = 90  # Image quality for trimming
TRIM_IMAGE_FORMAT = "none"  # Output format for image trimming

# Document Trim Settings
TRIM_DOCUMENT_ENABLED = False  # Enable document trimming
TRIM_DOCUMENT_QUALITY = 90  # Document quality for trimming
TRIM_DOCUMENT_FORMAT = "none"  # Output format for document trimming

# Subtitle Trim Settings
TRIM_SUBTITLE_ENABLED = False  # Enable subtitle trimming
TRIM_SUBTITLE_ENCODING = "none"  # Subtitle encoding for trimming
TRIM_SUBTITLE_FORMAT = "none"  # Output format for subtitle trimming

# Archive Trim Settings
TRIM_ARCHIVE_ENABLED = False  # Enable archive trimming
TRIM_ARCHIVE_FORMAT = "none"  # Output format for archive trimming

# Extract Settings
EXTRACT_ENABLED = False  # Enable extract functionality
EXTRACT_PRIORITY = 6  # Extract task priority
EXTRACT_DELETE_ORIGINAL = True  # Delete original files after extraction
EXTRACT_MAINTAIN_QUALITY = True  # Maintain quality during extraction

# Video Extract Settings
EXTRACT_VIDEO_ENABLED = False  # Enable video extraction
EXTRACT_VIDEO_CODEC = "none"  # Video codec for extraction
EXTRACT_VIDEO_FORMAT = "none"  # Output format for video extraction
EXTRACT_VIDEO_INDEX = None  # Video track index to extract
EXTRACT_VIDEO_QUALITY = "none"  # Quality setting for video extraction
EXTRACT_VIDEO_PRESET = "none"  # Preset for video encoding
EXTRACT_VIDEO_BITRATE = "none"  # Bitrate for video encoding
EXTRACT_VIDEO_RESOLUTION = "none"  # Resolution for video extraction
EXTRACT_VIDEO_FPS = "none"  # Frame rate for video extraction

# Audio Extract Settings
EXTRACT_AUDIO_ENABLED = False  # Enable audio extraction
EXTRACT_AUDIO_CODEC = "none"  # Audio codec for extraction
EXTRACT_AUDIO_FORMAT = "none"  # Output format for audio extraction
EXTRACT_AUDIO_INDEX = None  # Audio track index to extract
EXTRACT_AUDIO_BITRATE = "none"  # Audio bitrate for extraction
EXTRACT_AUDIO_CHANNELS = "none"  # Audio channel configuration
EXTRACT_AUDIO_SAMPLING = "none"  # Audio sampling rate

# Subtitle Extract Settings
EXTRACT_SUBTITLE_ENABLED = False  # Enable subtitle extraction
EXTRACT_SUBTITLE_INDEX = None  # Subtitle track index to extract
EXTRACT_SUBTITLE_FORMAT = "none"  # Output format for subtitle extraction
EXTRACT_SUBTITLE_ENCODING = "none"  # Subtitle encoding

# Attachment Extract Settings
EXTRACT_ATTACHMENT_ENABLED = False  # Enable attachment extraction
EXTRACT_ATTACHMENT_INDEX = None  # Attachment index to extract
EXTRACT_ATTACHMENT_FORMAT = "none"  # Output format for attachment extraction

# Remove Settings
REMOVE_ENABLED = False  # Enable remove functionality
REMOVE_PRIORITY = 8  # Remove task priority
REMOVE_DELETE_ORIGINAL = True  # Delete original files after removal
REMOVE_METADATA = False  # Remove metadata during processing
REMOVE_MAINTAIN_QUALITY = True  # Maintain quality during removal

# Video Remove Settings
REMOVE_VIDEO_ENABLED = False  # Enable video track removal
REMOVE_VIDEO_CODEC = "none"  # Video codec for removal processing
REMOVE_VIDEO_FORMAT = "none"  # Output format after video removal
REMOVE_VIDEO_INDEX = None  # Video track index to remove
REMOVE_VIDEO_QUALITY = "none"  # Video quality setting
REMOVE_VIDEO_PRESET = "none"  # Video encoding preset
REMOVE_VIDEO_BITRATE = "none"  # Video bitrate setting
REMOVE_VIDEO_RESOLUTION = "none"  # Video resolution setting
REMOVE_VIDEO_FPS = "none"  # Video frame rate setting

# Audio Remove Settings
REMOVE_AUDIO_ENABLED = False  # Enable audio track removal
REMOVE_AUDIO_CODEC = "none"  # Audio codec for removal processing
REMOVE_AUDIO_FORMAT = "none"  # Output format after audio removal
REMOVE_AUDIO_INDEX = None  # Audio track index to remove
REMOVE_AUDIO_BITRATE = "none"  # Audio bitrate setting
REMOVE_AUDIO_CHANNELS = "none"  # Audio channel configuration
REMOVE_AUDIO_SAMPLING = "none"  # Audio sampling rate setting

# Subtitle Remove Settings
REMOVE_SUBTITLE_ENABLED = False  # Enable subtitle track removal
REMOVE_SUBTITLE_INDEX = None  # Subtitle track index to remove
REMOVE_SUBTITLE_FORMAT = "none"  # Output format after subtitle removal
REMOVE_SUBTITLE_ENCODING = "none"  # Subtitle encoding setting

# Attachment Remove Settings
REMOVE_ATTACHMENT_ENABLED = False  # Enable attachment removal
REMOVE_ATTACHMENT_FORMAT = "none"  # Output format after attachment removal
REMOVE_ATTACHMENT_INDEX = None  # Attachment index to remove
REMOVE_ATTACHMENT_FILTER = "none"  # Filter for attachment removal

# Add Settings
ADD_ENABLED = False  # Enable add functionality
ADD_PRIORITY = 7  # Add task priority
ADD_DELETE_ORIGINAL = True  # Delete original files after adding
ADD_PRESERVE_TRACKS = False  # Preserve existing tracks when adding
ADD_REPLACE_TRACKS = False  # Replace existing tracks when adding

# Video Add Settings
ADD_VIDEO_ENABLED = False  # Enable video track addition
ADD_VIDEO_CODEC = "copy"  # Video codec for addition
ADD_VIDEO_INDEX = None  # Video track index to add
ADD_VIDEO_QUALITY = "none"  # Video quality setting
ADD_VIDEO_PRESET = "none"  # Video encoding preset
ADD_VIDEO_BITRATE = "none"  # Video bitrate setting
ADD_VIDEO_RESOLUTION = "none"  # Video resolution setting
ADD_VIDEO_FPS = "none"  # Video frame rate setting

# Audio Add Settings
ADD_AUDIO_ENABLED = False  # Enable audio track addition
ADD_AUDIO_CODEC = "copy"  # Audio codec for addition
ADD_AUDIO_INDEX = None  # Audio track index to add
ADD_AUDIO_BITRATE = "none"  # Audio bitrate setting
ADD_AUDIO_CHANNELS = "none"  # Audio channel configuration
ADD_AUDIO_SAMPLING = "none"  # Audio sampling rate setting

# Subtitle Add Settings
ADD_SUBTITLE_ENABLED = False  # Enable subtitle track addition
ADD_SUBTITLE_INDEX = None  # Subtitle track index to add
ADD_SUBTITLE_FORMAT = "none"  # Subtitle format for addition
ADD_SUBTITLE_ENCODING = "none"  # Subtitle encoding setting
ADD_SUBTITLE_HARDSUB_ENABLED = False  # Enable hardcoded subtitles when adding

# Attachment Add Settings
ADD_ATTACHMENT_ENABLED = False  # Enable attachment addition
ADD_ATTACHMENT_INDEX = None  # Attachment index to add
ADD_ATTACHMENT_MIMETYPE = "none"  # MIME type for attachment

# Swap Settings
SWAP_ENABLED = False  # Enable swap functionality
SWAP_PRIORITY = 6  # Swap task priority
SWAP_REMOVE_ORIGINAL = False  # Remove original files after swapping

# Audio Swap Settings
SWAP_AUDIO_ENABLED = False  # Enable audio track swapping
SWAP_AUDIO_USE_LANGUAGE = True  # Use language for audio track selection
SWAP_AUDIO_LANGUAGE_ORDER = "eng,hin"  # Language order for audio track selection
SWAP_AUDIO_INDEX_ORDER = "0,1"  # Index order for audio track selection

# Video Swap Settings
SWAP_VIDEO_ENABLED = False  # Enable video track swapping
SWAP_VIDEO_USE_LANGUAGE = True  # Use language for video track selection
SWAP_VIDEO_LANGUAGE_ORDER = "eng,hin"  # Language order for video track selection
SWAP_VIDEO_INDEX_ORDER = "0,1"  # Index order for video track selection

# Subtitle Swap Settings
SWAP_SUBTITLE_ENABLED = False  # Enable subtitle track swapping
SWAP_SUBTITLE_USE_LANGUAGE = True  # Use language for subtitle track selection
SWAP_SUBTITLE_LANGUAGE_ORDER = "eng,hin"  # Language order for subtitle track selection
SWAP_SUBTITLE_INDEX_ORDER = "0,1"  # Index order for subtitle track selection

# Convert Settings
CONVERT_ENABLED = False  # Enable convert functionality
CONVERT_PRIORITY = 3  # Convert task priority
CONVERT_DELETE_ORIGINAL = True  # Delete original files after conversion

# Video Convert Settings
CONVERT_VIDEO_ENABLED = False  # Enable video conversion
CONVERT_VIDEO_CODEC = "libx264"  # Video codec for conversion
CONVERT_VIDEO_FORMAT = "mp4"  # Output format for video conversion
CONVERT_VIDEO_PRESET = "medium"  # Video encoding preset
CONVERT_VIDEO_CRF = 23  # Constant Rate Factor for video quality
CONVERT_VIDEO_BITRATE = "none"  # Video bitrate for conversion
CONVERT_VIDEO_RESOLUTION = "none"  # Video resolution for conversion
CONVERT_VIDEO_FPS = "none"  # Video frame rate for conversion

# Audio Convert Settings
CONVERT_AUDIO_ENABLED = False  # Enable audio conversion
CONVERT_AUDIO_CODEC = "aac"  # Audio codec for conversion
CONVERT_AUDIO_FORMAT = "mp3"  # Output format for audio conversion
CONVERT_AUDIO_BITRATE = "128k"  # Audio bitrate for conversion
CONVERT_AUDIO_QUALITY = "none"  # Audio quality setting
CONVERT_AUDIO_CHANNELS = "none"  # Audio channel configuration
CONVERT_AUDIO_SAMPLE_RATE = "none"  # Audio sample rate for conversion

# Image Convert Settings
CONVERT_IMAGE_ENABLED = False  # Enable image conversion
CONVERT_IMAGE_FORMAT = "jpg"  # Output format for image conversion
CONVERT_IMAGE_QUALITY = 90  # Image quality for conversion (1-100)
CONVERT_IMAGE_RESIZE = "none"  # Resize dimensions for images

# Document Convert Settings
CONVERT_DOCUMENT_ENABLED = False  # Enable document conversion
CONVERT_DOCUMENT_FORMAT = "pdf"  # Output format for document conversion
CONVERT_DOCUMENT_QUALITY = 90  # Document quality for conversion


# Bulk Operation Settings
BULK_ENABLED = True  # Enable/disable bulk operations (-b flag)

# AI and Extra Modules
# AI Settings
AI_ENABLED = True  # Master toggle for AI functionality

# Default AI Model (replaces separate provider and model configs)
DEFAULT_AI_MODEL = "gpt-4o-mini"  # Use most reliable model as default - All supported models: gpt-4o, gpt-4o-mini, gpt-4, gpt-3.5-turbo, o1-preview, o1-mini, claude-3.5-sonnet, claude-3-sonnet, claude-3-haiku, claude-3-opus, claude-2.1, gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash-exp, mixtral-8x7b-32768, llama-3.1-70b-versatile, llama-3.1-8b-instant, llama2-70b-4096, vertex-gemini-1.5-pro, vertex-gemini-1.5-flash, vertex-claude-3-sonnet, vertex-claude-3-haiku, whisper-1, mistral, deepseek

# GPT/OpenAI Settings
OPENAI_API_KEY = ""  # OpenAI API key from https://platform.openai.com/api-keys
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"  # Custom OpenAI API URL
OPENAI_MODELS = "gpt-3.5-turbo,gpt-4,gpt-4-turbo,gpt-4o,gpt-4o-mini,o1-preview,o1-mini"

# Claude/Anthropic Settings
ANTHROPIC_API_KEY = ""  # Anthropic API key from https://console.anthropic.com/
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"  # Custom Anthropic API URL
CLAUDE_MODELS = (
    "claude-2.1,claude-3-haiku,claude-3-sonnet,claude-3.5-sonnet,claude-3-opus"
)

# Gemini/Google AI Settings
GOOGLE_AI_API_KEY = (
    ""  # Google AI API key from https://makersuite.google.com/app/apikey
)
GOOGLE_AI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODELS = "gemini-1.5-pro,gemini-1.5-flash,gemini-2.0-flash-exp"

# Vertex AI Settings (Enterprise Google Cloud)
VERTEX_PROJECT_ID = ""  # Google Cloud Project ID
VERTEX_LOCATION = "us-central1"  # Vertex AI location
VERTEX_MODELS = "gemini-1.5-pro,gemini-1.5-flash,claude-3-sonnet,claude-3-haiku"

# Groq Settings (High-speed inference)
GROQ_API_KEY = ""  # Groq API key from https://console.groq.com/keys
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = (
    "mixtral-8x7b-32768,llama2-70b-4096,llama-3.1-70b-versatile,llama-3.1-8b-instant"
)


# Legacy AI Settings (for backward compatibility)
MISTRAL_API_URL = ""  # Mistral AI API URL
DEEPSEEK_API_URL = ""  # DeepSeek AI API URL

# AI Feature Settings
AI_STREAMING_ENABLED = False  # Enable streaming responses (typewriter effect)
AI_PLUGINS_ENABLED = True  # Enable plugin system (web search, URL summary, etc.)
AI_MULTIMODAL_ENABLED = True  # Enable image/voice/document processing
AI_CONVERSATION_HISTORY = True  # Enable conversation history per user
AI_MAX_HISTORY_LENGTH = 50  # Maximum conversation history length
AI_QUESTION_PREDICTION = True  # Enable follow-up question generation
AI_GROUP_TOPIC_MODE = True  # Enable topic-based conversations in groups
AI_INLINE_MODE_ENABLED = True  # Enable inline mode support (@bot mentions)
AI_AUTO_LANGUAGE_DETECTION = True  # Auto-detect user language
AI_DEFAULT_LANGUAGE = "en"  # Default language (en, zh, ru)

# AI Plugin Settings
AI_WEB_SEARCH_ENABLED = True  # Enable web search plugin
AI_URL_SUMMARIZATION_ENABLED = True  # Enable URL summarization
AI_ARXIV_ENABLED = True  # Enable ArXiv paper plugin
AI_CODE_INTERPRETER_ENABLED = True  # Enable code execution
AI_IMAGE_GENERATION_ENABLED = True  # Enable DALL-E image generation
AI_VOICE_TRANSCRIPTION_ENABLED = True  # Enable Whisper voice transcription

# New ChatGPT-Telegram-Bot Features
AI_DOCUMENT_PROCESSING_ENABLED = True  # Enable document processing (PDF, text files)
AI_FOLLOW_UP_QUESTIONS_ENABLED = True  # Enable automatic follow-up question generation
AI_CONVERSATION_EXPORT_ENABLED = True  # Enable conversation export functionality
AI_TYPEWRITER_EFFECT_ENABLED = True  # Enable typewriter effect for streaming responses
AI_CONTEXT_PRUNING_ENABLED = True  # Enable intelligent context pruning

# AI Performance Settings
AI_MAX_TOKENS = 4096  # Maximum tokens per response
AI_TEMPERATURE = 0.7  # Response creativity (0.0-2.0)
AI_TIMEOUT = 60  # Request timeout in seconds
AI_MAX_CONCURRENT_REQUESTS = 10  # Max concurrent AI requests
AI_RATE_LIMIT_PER_USER = 50  # Max requests per user per hour

# AI Model Grouping (format: "Group:model1,model2|Group2:model3,model4")
AI_MODEL_GROUPS = "GPT:gpt-3.5-turbo,gpt-4,gpt-4o|Claude:claude-3-haiku,claude-3-sonnet|Gemini:gemini-1.5-pro,gemini-1.5-flash|Groq:mixtral-8x7b-32768,llama2-70b-4096|Others:mistral,deepseek"

# Extra Module Settings
IMDB_ENABLED = True  # Enable/disable IMDB functionality
TMDB_ENABLED = True  # Enable/disable TMDB functionality
TRUECALLER_ENABLED = True  # Enable/disable Truecaller functionality
ENCODING_ENABLED = True  # Enable/disable encoding functionality
DECODING_ENABLED = True  # Enable/disable decoding functionality

# Enhanced NSFW Detection
# Basic NSFW Settings
NSFW_DETECTION_ENABLED = True  # Master toggle for NSFW detection
NSFW_DETECTION_SENSITIVITY = (
    "moderate"  # Detection sensitivity: strict, moderate, permissive
)
NSFW_CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence for NSFW detection (0.0-1.0)
NSFW_CACHE_DURATION = 3600  # Cache detection results duration in seconds
NSFW_MAX_FILE_SIZE = 52428800  # Maximum file size for NSFW analysis in bytes (50MB)

# NSFW Detection Methods
NSFW_KEYWORD_DETECTION = True  # Enable enhanced keyword detection
NSFW_VISUAL_DETECTION = False  # Enable AI-powered visual analysis
NSFW_AUDIO_DETECTION = False  # Enable audio content analysis
NSFW_FUZZY_MATCHING = False  # Enable fuzzy keyword matching
NSFW_LEETSPEAK_DETECTION = True  # Enable leetspeak detection
NSFW_MULTI_LANGUAGE = False  # Enable multi-language keyword support
NSFW_CONTEXT_CHECKING = True  # Enable context-aware detection

# NSFW Media Analysis
NSFW_VIDEO_ANALYSIS = True  # Enable video frame analysis
NSFW_VIDEO_FRAME_COUNT = 5  # Number of frames to extract for analysis
NSFW_FRAME_QUALITY = 2  # Frame extraction quality (1-5)
NSFW_AUDIO_ANALYSIS = True  # Enable audio content analysis
NSFW_SUBTITLE_ANALYSIS = True  # Enable subtitle text analysis

# NSFW Visual Analysis API Settings
NSFW_GOOGLE_VISION_API_KEY = ""  # Google Cloud Vision API key for visual analysis
NSFW_AWS_ACCESS_KEY = ""  # AWS Rekognition access key for visual analysis
NSFW_AWS_SECRET_KEY = ""  # AWS Rekognition secret key for visual analysis
NSFW_AWS_REGION = "us-east-1"  # AWS region for Rekognition
NSFW_AZURE_ENDPOINT = ""  # Azure Content Moderator endpoint URL
NSFW_AZURE_KEY = ""  # Azure Content Moderator API key
NSFW_OPENAI_API_KEY = ""  # OpenAI API key for vision analysis

# NSFW Behavior and Logging
NSFW_LOG_DETECTIONS = True  # Log NSFW detections for analysis
NSFW_STORE_METADATA = True  # Store detection metadata in database
NSFW_AUTO_DELETE = False  # Auto-delete detected NSFW content
NSFW_NOTIFY_ADMINS = True  # Notify admins of NSFW detections

# Archive Operation Settings
ARCHIVE_FLAGS_ENABLED = True  # Enable archive operation flags

# Rclone Settings
RCLONE_ENABLED = True  # Enable/disable Rclone functionality

# Additional Settings
UNIVERSAL_FILENAME = ""  # Universal filename template for both mirror and leech files (supports all template variables)
EQUAL_SPLITS = False  # Create equal-sized parts when splitting files

# Media Tools Settings
MEDIA_TOOLS_ENABLED = True  # Master switch to enable/disable all media tools features

# Watermark Settings
WATERMARK_ENABLED = False  # Master switch to enable/disable watermark feature
WATERMARK_KEY = ""  # Default watermark text to apply to videos
WATERMARK_POSITION = "none"  # Position of watermark: none, top_left, top_right, bottom_left, bottom_right, center
WATERMARK_SIZE = (
    0  # Font size for watermark text (0 = auto-size based on video dimensions)
)
WATERMARK_COLOR = (
    "none"  # Watermark text color: none, white, black, red, green, blue, yellow, etc.
)
WATERMARK_FONT = "none"  # Font for watermark text: none, Arial.ttf, Roboto, etc. (supports Google Fonts)
WATERMARK_OPACITY = 0.0  # Watermark opacity: 0.0 (transparent) to 1.0 (opaque)
WATERMARK_PRIORITY = 2  # Processing priority in pipeline (lower numbers run earlier)
WATERMARK_THREADING = True  # Use multi-threading for faster watermark processing
WATERMARK_THREAD_NUMBER = 4  # Number of threads for watermark processing
WATERMARK_QUALITY = (
    "none"  # Quality setting for watermark (none = default, or specify a value)
)
WATERMARK_SPEED = (
    "none"  # Speed setting for watermark (none = default, or specify a value)
)
WATERMARK_REMOVE_ORIGINAL = True  # Delete original files after successful watermarking

# Audio Watermark Settings
AUDIO_WATERMARK_VOLUME = (
    0.0  # Volume level for audio watermark: 0.0 (silent) to 1.0 (full volume)
)
AUDIO_WATERMARK_INTERVAL = (
    0  # Interval for audio watermarks (0 = default, or specify number of seconds)
)

# Subtitle Watermark Settings
SUBTITLE_WATERMARK_STYLE = "none"  # Style for subtitle text: none, normal, bold, italic, bold_italic, underline, strikethrough
SUBTITLE_WATERMARK_INTERVAL = (
    0  # Interval for subtitle watermarks (0 = default, or specify number of seconds)
)

# Image Watermark Settings
IMAGE_WATERMARK_ENABLED = False  # Enable/disable image watermark feature
IMAGE_WATERMARK_PATH = ""  # Path to the watermark image file
IMAGE_WATERMARK_SCALE = 10  # Scale of watermark as percentage of video width (1-100)
IMAGE_WATERMARK_OPACITY = (
    1.0  # Opacity of watermark image: 0.0 (transparent) to 1.0 (opaque)
)
IMAGE_WATERMARK_POSITION = "bottom_right"  # Position of watermark: top_left, top_right, bottom_left, bottom_right, center

# Merge Settings
MERGE_ENABLED = False  # Master switch to enable/disable merge feature
MERGE_PRIORITY = 1  # Processing priority in pipeline (lower numbers run earlier)
MERGE_THREADING = True  # Use multi-threading for faster merge processing
MERGE_THREAD_NUMBER = 4  # Number of threads for merge processing
MERGE_REMOVE_ORIGINAL = True  # Delete original files after successful merge
CONCAT_DEMUXER_ENABLED = (
    True  # Enable FFmpeg concat demuxer method (faster, requires same codecs)
)
FILTER_COMPLEX_ENABLED = (
    False  # Enable FFmpeg filter_complex method (slower but more compatible)
)

# Merge Output Formats
MERGE_OUTPUT_FORMAT_VIDEO = (
    "none"  # Output format for merged videos: none, mp4, mkv, avi, etc.
)
MERGE_OUTPUT_FORMAT_AUDIO = (
    "none"  # Output format for merged audio: none, mp3, m4a, flac, etc.
)
MERGE_OUTPUT_FORMAT_IMAGE = (
    "none"  # Output format for merged images: none, jpg, png, pdf, etc.
)
MERGE_OUTPUT_FORMAT_DOCUMENT = (
    "none"  # Output format for merged documents: none, pdf, docx, etc.
)
MERGE_OUTPUT_FORMAT_SUBTITLE = (
    "none"  # Output format for merged subtitles: none, srt, ass, etc.
)

# Merge Video Settings
MERGE_VIDEO_CODEC = (
    "none"  # Video codec for merged files: none, copy, libx264, libx265, etc.
)
MERGE_VIDEO_QUALITY = "none"  # Video quality preset: none, ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
MERGE_VIDEO_PRESET = "none"  # Encoding preset: none, ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
MERGE_VIDEO_CRF = "none"  # Constant Rate Factor for quality (0-51, lower is better quality): none, 18, 23, 28, etc.
MERGE_VIDEO_PIXEL_FORMAT = "none"  # Pixel format: none, yuv420p, yuv444p, etc.
MERGE_VIDEO_TUNE = "none"  # Tune option for specific content: none, film, animation, grain, stillimage, etc.
MERGE_VIDEO_FASTSTART = False  # Enable fast start for web streaming

# Merge Audio Settings
MERGE_AUDIO_CODEC = (
    "none"  # Audio codec for merged files: none, copy, aac, mp3, opus, etc.
)
MERGE_AUDIO_BITRATE = "none"  # Audio bitrate: none, 128k, 192k, 320k, etc.
MERGE_AUDIO_CHANNELS = "none"  # Number of audio channels: none, 1, 2, etc.
MERGE_AUDIO_SAMPLING = "none"  # Audio sampling rate: none, 44100, 48000, etc.
MERGE_AUDIO_VOLUME = "none"  # Volume adjustment: none, 1.0, 1.5, 0.5, etc.

# Merge Image Settings
MERGE_IMAGE_MODE = "none"  # Image merge mode: none, horizontal, vertical, grid, etc.
MERGE_IMAGE_COLUMNS = "none"  # Number of columns for grid mode: none, 2, 3, 4, etc.
MERGE_IMAGE_QUALITY = 0  # JPEG quality (0-100)
MERGE_IMAGE_DPI = "none"  # Image DPI: none, 72, 96, 300, etc.
MERGE_IMAGE_RESIZE = "none"  # Image resize dimensions: none, 1920x1080, 50%, etc.
MERGE_IMAGE_BACKGROUND = (
    "none"  # Background color for transparent images: none, white, black, etc.
)

# Merge Subtitle Settings
MERGE_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
MERGE_SUBTITLE_FONT = "none"  # Font for subtitles: none, Arial, Times New Roman, etc.
MERGE_SUBTITLE_FONT_SIZE = "none"  # Font size: none, 12, 16, etc.
MERGE_SUBTITLE_FONT_COLOR = "none"  # Font color: none, white, yellow, etc.
MERGE_SUBTITLE_BACKGROUND = "none"  # Background color: none, black, transparent, etc.

# Merge Document Settings
MERGE_DOCUMENT_PAPER_SIZE = "none"  # Paper size: none, a4, letter, etc.
MERGE_DOCUMENT_ORIENTATION = "none"  # Page orientation: none, portrait, landscape
MERGE_DOCUMENT_MARGIN = "none"  # Page margins in mm: none, 10, 20, etc.

# Merge Metadata Settings
MERGE_METADATA_TITLE = "none"  # Title metadata for merged file
MERGE_METADATA_AUTHOR = "none"  # Author metadata for merged file
MERGE_METADATA_COMMENT = "none"  # Comment metadata for merged file

# Compression Settings
COMPRESSION_ENABLED = False  # Master switch to enable/disable compression feature
COMPRESSION_PRIORITY = 4  # Processing priority in pipeline (lower numbers run earlier)
COMPRESSION_DELETE_ORIGINAL = True  # Delete original files after successful compression (default: True, use -del flag to override)

# Video Compression Settings
COMPRESSION_VIDEO_ENABLED = False  # Enable/disable video compression
COMPRESSION_VIDEO_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_VIDEO_CRF = "none"  # Constant Rate Factor for quality (none = use default, 0-51, lower is better quality)
COMPRESSION_VIDEO_CODEC = "none"  # Video codec: none, libx264, libx265, etc.
COMPRESSION_VIDEO_TUNE = (
    "none"  # Tune option for specific content: none, film, animation, grain, etc.
)
COMPRESSION_VIDEO_PIXEL_FORMAT = "none"  # Pixel format: none, yuv420p, yuv444p, etc.
COMPRESSION_VIDEO_FORMAT = (
    "none"  # Output format: none (use input format), mp4, mkv, avi, etc.
)
COMPRESSION_VIDEO_BITDEPTH = (
    "none"  # Video bit depth: none (use input), 8, 10, 12, etc.
)
COMPRESSION_VIDEO_BITRATE = "none"  # Video bitrate: none (use input), 1M, 5M, 10M, etc.
COMPRESSION_VIDEO_RESOLUTION = (
    "none"  # Video resolution: none (use input), 1920x1080, 1280x720, etc.
)

# Audio Compression Settings
COMPRESSION_AUDIO_ENABLED = False  # Enable/disable audio compression
COMPRESSION_AUDIO_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_AUDIO_CODEC = "none"  # Audio codec: none, aac, mp3, opus, etc.
COMPRESSION_AUDIO_BITRATE = "none"  # Audio bitrate: none, 128k, 192k, 320k, etc.
COMPRESSION_AUDIO_CHANNELS = (
    "none"  # Number of audio channels: none (use input), 1 (mono), 2 (stereo), etc.
)
COMPRESSION_AUDIO_FORMAT = (
    "none"  # Output format: none (use input format), mp3, m4a, flac, etc.
)
COMPRESSION_AUDIO_BITDEPTH = (
    "none"  # Audio bit depth: none (use input), 16, 24, 32, etc.
)

# Image Compression Settings
COMPRESSION_IMAGE_ENABLED = False  # Enable/disable image compression
COMPRESSION_IMAGE_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_IMAGE_QUALITY = (
    "none"  # Image quality: none (use default), 0-100 (higher is better quality)
)
COMPRESSION_IMAGE_RESIZE = "none"  # Image resize dimensions: none, 1920x1080, 50%, etc.
COMPRESSION_IMAGE_FORMAT = (
    "none"  # Output format: none (use input format), jpg, png, webp, etc.
)

# Document Compression Settings
COMPRESSION_DOCUMENT_ENABLED = False  # Enable/disable document compression
COMPRESSION_DOCUMENT_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_DOCUMENT_DPI = "none"  # Document DPI: none (use input), 72, 96, 300, etc.
COMPRESSION_DOCUMENT_FORMAT = (
    "none"  # Output format: none (use input format), pdf, docx, etc.
)

# Subtitle Compression Settings
COMPRESSION_SUBTITLE_ENABLED = False  # Enable/disable subtitle compression
COMPRESSION_SUBTITLE_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
COMPRESSION_SUBTITLE_FORMAT = (
    "none"  # Output format: none (use input format), srt, ass, vtt, etc.
)

# Archive Compression Settings
COMPRESSION_ARCHIVE_ENABLED = False  # Enable/disable archive compression
COMPRESSION_ARCHIVE_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_ARCHIVE_LEVEL = (
    "none"  # Compression level: none (use default), 0-9 (higher is more compression)
)
COMPRESSION_ARCHIVE_METHOD = "none"  # Compression method: none, deflate, lzma, etc.
COMPRESSION_ARCHIVE_FORMAT = (
    "none"  # Output format: none (use input format), zip, 7z, tar.gz, etc.
)
COMPRESSION_ARCHIVE_PASSWORD = "none"  # Password for archive: none or password string
COMPRESSION_ARCHIVE_ALGORITHM = "none"  # Archive algorithm: none, 7z, zip, etc.

# Trim Settings
TRIM_ENABLED = False  # Master switch to enable/disable trim feature
TRIM_PRIORITY = 5  # Processing priority in pipeline (lower numbers run earlier)
TRIM_START_TIME = "00:00:00"  # Start time for trimming in HH:MM:SS format
TRIM_END_TIME = ""  # End time for trimming in HH:MM:SS format (empty = end of file)
TRIM_DELETE_ORIGINAL = False  # Delete original files after successful trimming

# Video Trim Settings
TRIM_VIDEO_ENABLED = False  # Enable/disable video trimming
TRIM_VIDEO_CODEC = "none"  # Video codec: none, copy (fastest), libx264, libx265, etc.
TRIM_VIDEO_PRESET = "none"  # Encoding preset: none, ultrafast, fast, medium, slow, etc.
TRIM_VIDEO_FORMAT = "none"  # Output format: none, mp4, mkv, avi, etc.

# Audio Trim Settings
TRIM_AUDIO_ENABLED = False  # Enable/disable audio trimming
TRIM_AUDIO_CODEC = "none"  # Audio codec: none, copy (fastest), aac, mp3, etc.
TRIM_AUDIO_PRESET = "none"  # Encoding preset: none, fast, medium, slow
TRIM_AUDIO_FORMAT = "none"  # Output format: none, mp3, m4a, flac, etc.

# Image Trim Settings
TRIM_IMAGE_ENABLED = False  # Enable/disable image trimming (crop)
TRIM_IMAGE_QUALITY = 90  # Image quality: 0-100 (higher is better quality)
TRIM_IMAGE_FORMAT = "none"  # Output format: none, jpg, png, webp, etc.

# Document Trim Settings
TRIM_DOCUMENT_ENABLED = False  # Enable/disable document trimming (page range)
TRIM_DOCUMENT_START_PAGE = "1"  # Starting page number for document trimming
TRIM_DOCUMENT_END_PAGE = (
    ""  # Ending page number for document trimming (empty for last page)
)
TRIM_DOCUMENT_QUALITY = 90  # Document quality: 0-100 (higher is better quality)
TRIM_DOCUMENT_FORMAT = "none"  # Output format: none, pdf, docx, etc.

# Subtitle Trim Settings
TRIM_SUBTITLE_ENABLED = False  # Enable/disable subtitle trimming (time range)
TRIM_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
TRIM_SUBTITLE_FORMAT = "none"  # Output format: none, srt, ass, vtt, etc.

# Archive Trim Settings
TRIM_ARCHIVE_ENABLED = False  # Enable/disable archive trimming (file selection)
TRIM_ARCHIVE_FORMAT = "none"  # Output format: none, zip, 7z, tar.gz, etc.

# Extract Settings
EXTRACT_ENABLED = False  # Master switch to enable/disable extract feature
EXTRACT_PRIORITY = 6  # Processing priority in pipeline (lower numbers run earlier)
EXTRACT_DELETE_ORIGINAL = True  # Delete original files after successful extraction

# Video Extract Settings
EXTRACT_VIDEO_ENABLED = False  # Enable/disable video stream extraction
EXTRACT_VIDEO_CODEC = (
    "none"  # Video codec: none, copy (fastest), libx264, libx265, etc.
)
EXTRACT_VIDEO_FORMAT = "none"  # Output format: none, mp4, mkv, avi, etc.
EXTRACT_VIDEO_INDEX = None  # Stream index to extract: None (all), 0, 1, 2, etc.
EXTRACT_VIDEO_QUALITY = "none"  # Video quality: none, high, medium, low, etc.
EXTRACT_VIDEO_PRESET = (
    "none"  # Encoding preset: none, ultrafast, fast, medium, slow, etc.
)
EXTRACT_VIDEO_BITRATE = "none"  # Video bitrate: none, 1M, 5M, etc.
EXTRACT_VIDEO_RESOLUTION = "none"  # Video resolution: none, 1920x1080, 1280x720, etc.
EXTRACT_VIDEO_FPS = "none"  # Frame rate: none, 30, 60, etc.

# Audio Extract Settings
EXTRACT_AUDIO_ENABLED = False  # Enable/disable audio stream extraction
EXTRACT_AUDIO_CODEC = "none"  # Audio codec: none, copy (fastest), aac, mp3, etc.
EXTRACT_AUDIO_FORMAT = "none"  # Output format: none, mp3, m4a, flac, etc.
EXTRACT_AUDIO_INDEX = None  # Stream index to extract: None (all), 0, 1, 2, etc.
EXTRACT_AUDIO_BITRATE = "none"  # Audio bitrate: none, 128k, 192k, 320k, etc.
EXTRACT_AUDIO_CHANNELS = (
    "none"  # Number of audio channels: none, 1 (mono), 2 (stereo), etc.
)
EXTRACT_AUDIO_SAMPLING = "none"  # Audio sampling rate: none, 44100, 48000, etc.
EXTRACT_AUDIO_VOLUME = "none"  # Volume adjustment: none, 1.0, 1.5, 0.5, etc.

# Subtitle Extract Settings
EXTRACT_SUBTITLE_ENABLED = False  # Enable/disable subtitle stream extraction
EXTRACT_SUBTITLE_CODEC = "none"  # Subtitle codec: none, copy, mov_text, etc.
EXTRACT_SUBTITLE_FORMAT = "none"  # Output format: none, srt, ass, vtt, etc.
EXTRACT_SUBTITLE_INDEX = None  # Stream index to extract: None (all), 0, 1, 2, etc.
EXTRACT_SUBTITLE_LANGUAGE = "none"  # Language code: none, eng, spa, etc.
EXTRACT_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
EXTRACT_SUBTITLE_FONT = "none"  # Font for subtitles: none, Arial, Times New Roman, etc.
EXTRACT_SUBTITLE_FONT_SIZE = "none"  # Font size: none, 12, 16, etc.

# Attachment Extract Settings
EXTRACT_ATTACHMENT_ENABLED = False  # Enable/disable attachment extraction
EXTRACT_ATTACHMENT_FORMAT = "none"  # Output format: none, original, etc.
EXTRACT_ATTACHMENT_INDEX = (
    None  # Attachment index to extract: None (all), 0, 1, 2, etc.
)
EXTRACT_ATTACHMENT_FILTER = "none"  # Filter pattern: none, *.ttf, *.png, etc.
EXTRACT_MAINTAIN_QUALITY = True  # Maintain original quality during extraction

# Remove Settings
REMOVE_ENABLED = False  # Master switch to enable/disable remove feature
REMOVE_PRIORITY = 8  # Processing priority in pipeline (lower numbers run earlier)
REMOVE_DELETE_ORIGINAL = True  # Delete original files after successful remove operation
REMOVE_METADATA = False  # Remove metadata from files

# Video Remove Settings
REMOVE_VIDEO_ENABLED = False  # Enable/disable video track removal
REMOVE_VIDEO_INDEX = None  # Video track index to remove: None (all), 0, 1, 2, etc.

# Audio Remove Settings
REMOVE_AUDIO_ENABLED = False  # Enable/disable audio track removal
REMOVE_AUDIO_INDEX = None  # Audio track index to remove: None (all), 0, 1, 2, etc.

# Subtitle Remove Settings
REMOVE_SUBTITLE_ENABLED = False  # Enable/disable subtitle track removal
REMOVE_SUBTITLE_INDEX = (
    None  # Subtitle track index to remove: None (all), 0, 1, 2, etc.
)

# Attachment Remove Settings
REMOVE_ATTACHMENT_ENABLED = False  # Enable/disable attachment removal
REMOVE_ATTACHMENT_INDEX = None  # Attachment index to remove: None (all), 0, 1, 2, etc.

# Add Settings
ADD_ENABLED = False  # Master switch to enable/disable add feature
ADD_PRIORITY = 7  # Processing priority in pipeline (lower numbers run earlier)
ADD_DELETE_ORIGINAL = True  # Delete original files after successful add operation
ADD_PRESERVE_TRACKS = False  # Preserve existing tracks when adding new ones
ADD_REPLACE_TRACKS = False  # Replace existing tracks with new ones at the same index

# Video Add Settings
ADD_VIDEO_ENABLED = False  # Enable/disable video track addition
# ADD_VIDEO_PATH has been removed
ADD_VIDEO_INDEX = None  # Stream index to add: None (all), 0, 1, 2, etc.
ADD_VIDEO_CODEC = "copy"  # Video codec: copy (fastest), libx264, libx265, etc.
ADD_VIDEO_QUALITY = "none"  # Video quality: none, high, medium, low, etc.
ADD_VIDEO_PRESET = "none"  # Encoding preset: none, ultrafast, fast, medium, slow, etc.
ADD_VIDEO_BITRATE = "none"  # Video bitrate: none, 1M, 5M, etc.
ADD_VIDEO_RESOLUTION = "none"  # Video resolution: none, 1920x1080, 1280x720, etc.
ADD_VIDEO_FPS = "none"  # Frame rate: none, 30, 60, etc.

# Audio Add Settings
ADD_AUDIO_ENABLED = False  # Enable/disable audio track addition
# ADD_AUDIO_PATH has been removed
ADD_AUDIO_INDEX = None  # Stream index to add: None (all), 0, 1, 2, etc.
ADD_AUDIO_CODEC = "copy"  # Audio codec: copy (fastest), aac, mp3, etc.
ADD_AUDIO_BITRATE = "none"  # Audio bitrate: none, 128k, 192k, 320k, etc.
ADD_AUDIO_CHANNELS = (
    "none"  # Number of audio channels: none, 1 (mono), 2 (stereo), etc.
)
ADD_AUDIO_SAMPLING = "none"  # Audio sampling rate: none, 44100, 48000, etc.
ADD_AUDIO_VOLUME = "none"  # Volume adjustment: none, 1.0, 1.5, 0.5, etc.

# Subtitle Add Settings
ADD_SUBTITLE_ENABLED = False  # Enable/disable subtitle track addition
# ADD_SUBTITLE_PATH has been removed
ADD_SUBTITLE_INDEX = None  # Stream index to add: None (all), 0, 1, 2, etc.
ADD_SUBTITLE_CODEC = "copy"  # Subtitle codec: copy, mov_text, etc.
ADD_SUBTITLE_LANGUAGE = "none"  # Language code: none, eng, spa, etc.
ADD_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
ADD_SUBTITLE_FONT = "none"  # Font for subtitles: none, Arial, Times New Roman, etc.
ADD_SUBTITLE_FONT_SIZE = "none"  # Font size: none, 12, 16, etc.
ADD_SUBTITLE_HARDSUB_ENABLED = (
    False  # Enable hardsub (burn subtitles into video): True/False
)

# Attachment Add Settings
ADD_ATTACHMENT_ENABLED = False  # Enable/disable attachment addition
# ADD_ATTACHMENT_PATH has been removed
ADD_ATTACHMENT_INDEX = None  # Attachment index to add: None (all), 0, 1, 2, etc.
ADD_ATTACHMENT_MIMETYPE = "none"  # MIME type: none, font/ttf, image/png, etc.

# Swap Settings
SWAP_ENABLED = False  # Master switch to enable/disable swap feature
SWAP_PRIORITY = 6  # Processing priority in pipeline (lower numbers run earlier)
SWAP_REMOVE_ORIGINAL = False  # Delete original files after successful swap operation

# Audio Swap Settings
SWAP_AUDIO_ENABLED = False  # Enable/disable audio track swapping
SWAP_AUDIO_USE_LANGUAGE = (
    True  # Use language-based swapping (True) or index-based (False)
)
SWAP_AUDIO_LANGUAGE_ORDER = "eng,hin"  # Language priority order: eng,hin,jpn,etc.
SWAP_AUDIO_INDEX_ORDER = (
    "0,1"  # Index swap order: 0,1 (swap first two), 1,2,0 (rotate), etc.
)

# Video Swap Settings
SWAP_VIDEO_ENABLED = False  # Enable/disable video track swapping
SWAP_VIDEO_USE_LANGUAGE = (
    True  # Use language-based swapping (True) or index-based (False)
)
SWAP_VIDEO_LANGUAGE_ORDER = "eng,hin"  # Language priority order: eng,hin,jpn,etc.
SWAP_VIDEO_INDEX_ORDER = (
    "0,1"  # Index swap order: 0,1 (swap first two), 1,2,0 (rotate), etc.
)

# Subtitle Swap Settings
SWAP_SUBTITLE_ENABLED = False  # Enable/disable subtitle track swapping
SWAP_SUBTITLE_USE_LANGUAGE = (
    True  # Use language-based swapping (True) or index-based (False)
)
SWAP_SUBTITLE_LANGUAGE_ORDER = "eng,hin"  # Language priority order: eng,hin,jpn,etc.
SWAP_SUBTITLE_INDEX_ORDER = (
    "0,1"  # Index swap order: 0,1 (swap first two), 1,2,0 (rotate), etc.
)

# Convert Settings
CONVERT_ENABLED = False  # Master switch to enable/disable convert feature
CONVERT_PRIORITY = 3  # Processing priority in pipeline (lower numbers run earlier)
CONVERT_DELETE_ORIGINAL = True  # Delete original files after successful conversion (default: True, use -del flag to override)

# Video Convert Settings
CONVERT_VIDEO_ENABLED = False  # Enable/disable video conversion
CONVERT_VIDEO_FORMAT = "none"  # Target format: none, mp4, mkv, avi, webm, etc.
CONVERT_VIDEO_CODEC = "none"  # Video codec: none, libx264, libx265, vp9, etc.
CONVERT_VIDEO_QUALITY = "none"  # Video quality preset: none, high, medium, low
CONVERT_VIDEO_CRF = 0  # Constant Rate Factor (0-51, lower is better quality)
CONVERT_VIDEO_PRESET = (
    "none"  # Encoding preset: none, ultrafast, fast, medium, slow, etc.
)
CONVERT_VIDEO_MAINTAIN_QUALITY = True  # Maintain original quality during conversion
CONVERT_VIDEO_RESOLUTION = "none"  # Target resolution: none, 1920x1080, 1280x720, etc.
CONVERT_VIDEO_FPS = "none"  # Target frame rate: none, 30, 60, etc.

# Audio Convert Settings
CONVERT_AUDIO_ENABLED = False  # Enable/disable audio conversion
CONVERT_AUDIO_FORMAT = "none"  # Target format: none, mp3, m4a, flac, ogg, etc.
CONVERT_AUDIO_CODEC = "none"  # Audio codec: none, aac, mp3, opus, flac, etc.
CONVERT_AUDIO_BITRATE = "none"  # Target bitrate: none, 128k, 192k, 320k, etc.
CONVERT_AUDIO_CHANNELS = 0  # Target channels: 0 (original), 1 (mono), 2 (stereo), etc.
CONVERT_AUDIO_SAMPLING = 0  # Target sampling rate: 0 (original), 44100, 48000, etc.
CONVERT_AUDIO_VOLUME = 0.0  # Volume adjustment: 0.0 (original), 1.0, 1.5, 0.5, etc.

# Subtitle Convert Settings
CONVERT_SUBTITLE_ENABLED = False  # Enable/disable subtitle conversion
CONVERT_SUBTITLE_FORMAT = "none"  # Target format: none, srt, ass, vtt, etc.
CONVERT_SUBTITLE_ENCODING = "none"  # Target encoding: none, utf-8, utf-16, etc.
CONVERT_SUBTITLE_LANGUAGE = "none"  # Target language code: none, eng, spa, etc.

# Document Convert Settings
CONVERT_DOCUMENT_ENABLED = False  # Enable/disable document conversion
CONVERT_DOCUMENT_FORMAT = "none"  # Target format: none, pdf, docx, txt, etc.
CONVERT_DOCUMENT_QUALITY = 0  # Document quality (0-100, higher is better)
CONVERT_DOCUMENT_DPI = 0  # Document DPI: 0 (original), 72, 96, 300, etc.

# Archive Convert Settings
CONVERT_ARCHIVE_ENABLED = False  # Enable/disable archive conversion
CONVERT_ARCHIVE_FORMAT = "none"  # Target format: none, zip, 7z, tar.gz, etc.
CONVERT_ARCHIVE_LEVEL = 0  # Compression level (0-9, higher is more compression)
CONVERT_ARCHIVE_METHOD = "none"  # Compression method: none, deflate, lzma, etc.
