## 1. Required Fields

| Variable        | Type   | Description                                                                                  |
|----------------|--------|----------------------------------------------------------------------------------------------|
| `BOT_TOKEN`     | `str`  | Telegram Bot Token obtained from [@BotFather](https://t.me/BotFather).                        |
| `OWNER_ID`      | `int`  | Telegram User ID (not username) of the bot's owner.                                           |
| `TELEGRAM_API`  | `int`  | API ID used to authenticate your Telegram account. Obtainable from [my.telegram.org](https://my.telegram.org). |
| `TELEGRAM_HASH` | `str`  | API hash used to authenticate your Telegram account. Obtainable from [my.telegram.org](https://my.telegram.org). |

## 2. Optional Fields

| Variable                  | Type           | Description |
|---------------------------|----------------|-------------|
| `TG_PROXY`                | `dict`         | Proxy settings as dict. Example: `{"scheme": "socks5", "hostname": "11.22.33.44", "port": 1234, "username": "user", "password": "pass"}`. Username/password optional. |
| `USER_SESSION_STRING`     | `str`          | Use to access Telegram premium features. Generate using `python3 generate_string_session.py`. **Note:** Use in supergroup only. |
| `DATABASE_URL`            | `str`          | MongoDB connection string. See [Create Database](https://github.com/anasty17/test?tab=readme-ov-file#create-database). Data includes bot/user settings, RSS, and tasks. |
| `CMD_SUFFIX`              | `str`          | Suffix to add at the end of all commands. |
| `AUTHORIZED_CHATS`        | `str`          | User/chat/topic IDs to authorize. Format: `chat_id`, `chat_id|thread_id`, etc. Separate by spaces. |
| `SUDO_USERS`              | `str`          | User IDs with sudo permission. Separate by spaces. |
| `UPLOAD_PATHS`            | `dict`         | Dict with upload paths. Example: `{"path 1": "remote:", "path 2": "gdrive id", ...}` |
| `DEFAULT_UPLOAD`          | `str`          | `rc` for `RCLONE_PATH`, `gd` for `GDRIVE_ID`, `ddl` for Direct Download Links. Default: `rc`. [Read More](https://github.com/anasty17/mirror-leech-telegram-bot/tree/master#upload). |
| `EXCLUDED_EXTENSIONS`     | `str`          | File extensions to skip. Separate by spaces. |
| `INCOMPLETE_TASK_NOTIFIER`| `bool`         | Notify after restart for incomplete tasks. Needs DB and supergroup. Default: `False`. |
| `FILELION_API`            | `str`          | API key from [Filelion](https://vidhide.com/?op=my_account). |
| `STREAMWISH_API`          | `str`          | API key from [Streamwish](https://streamwish.com/?op=my_account). |
| `YT_DLP_OPTIONS`          | `dict`         | Dict of `yt-dlp` options. [Docs](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L184). [Convert script](https://t.me/mltb_official_channel/177). |
| `USE_SERVICE_ACCOUNTS`    | `bool`         | Use Google API service accounts. See [guide](https://github.com/anasty17/mirror-leech-telegram-bot#generate-service-accounts-what-is-service-account). |
| `FFMPEG_CMDS`             | `dict`         | Dict with lists of ffmpeg commands. Start with arguments only. Use `-ff key` to apply. Add `-del` to auto-delete source. See example and notes. |
| `NAME_SUBSTITUTE`         | `str`          | Replace/remove words/characters using `source/target` format. Use `\` for escaping special characters. |
| `BASE_URL`                | `str`          | Base URL for the bot web interface. |
| `BASE_URL_PORT`           | `int`          | Port for the base URL. Default: `80`. |
| `INDEX_URL`               | `str`          | Index URL for file listings. |
| `TORRENT_TIMEOUT`         | `int`          | Timeout for torrent operations in seconds. Default: `0` (no timeout). |
| `STOP_DUPLICATE`          | `bool`         | Stop duplicate downloads. Default: `False`. |
| `WEB_PINCODE`             | `bool`         | Enable web interface PIN code protection. Default: `False`. |
| `FILE2LINK_ENABLED`       | `bool`         | Enable File2Link streaming functionality. Default: `True`. |
| `FILE2LINK_BASE_URL`      | `str`          | Dedicated base URL for File2Link streaming. Uses `BASE_URL` if not set. Auto-detects Heroku/Railway/Render. |
| `FILE2LINK_BIN_CHANNEL`   | `int`          | Channel ID for storing streaming files. Uses `BIN_CHANNEL` if not set. Default: `0`. |
| `FILE2LINK_ALLOWED_TYPES` | `str`          | Comma-separated list of allowed media types. Default: `video,audio,document,photo,animation,voice,video_note`. |
| `UPSTREAM_REPO`           | `str`          | Upstream repository URL for updates. |
| `UPSTREAM_BRANCH`         | `str`          | Upstream repository branch. Default: `main`. |
| `HELPER_TOKENS`           | `str`          | Additional helper bot tokens for load balancing. |
| `HYPER_THREADS`           | `int`          | Number of threads for parallel processing. Default: `0` (auto). |
| `IMDB_TEMPLATE`           | `str`          | Custom template for IMDB information display. |

## 3. GDrive Tools

| Variable        | Type   | Description |
|----------------|--------|-------------|
| `GDRIVE_ID`     | `str`  | Folder/TeamDrive ID or `root`. |
| `IS_TEAM_DRIVE` | `bool` | Set `True` for TeamDrive. Default: `False`. |
| `INDEX_URL`     | `str`  | [Reference](https://gitlab.com/ParveenBhadooOfficial/Google-Drive-Index). |
| `STOP_DUPLICATE`| `bool` | Check for duplicate file/folder names. Default: `False`. |

## 4. Rclone

| Variable            | Type   | Description |
|---------------------|--------|-------------|
| `RCLONE_PATH`        | `str`  | Default upload path. |
| `RCLONE_FLAGS`       | `str`  | Use `--key:value|--key` format. [Flags](https://rclone.org/flags/). |
| `RCLONE_SERVE_URL`   | `str`  | Bot URL. Example: `http://myip` or `http://myip:port`. |
| `RCLONE_SERVE_PORT`  | `int`  | Port. Default: `8080`. |
| `RCLONE_SERVE_USER`  | `str`  | Serve username. |
| `RCLONE_SERVE_PASS`  | `str`  | Serve password. |

## 5. Update

| Variable         | Type  | Description |
|------------------|-------|-------------|
| `UPSTREAM_REPO`   | `str` | GitHub repo link. For private, use `https://username:token@github.com/username/repo`. [Get token](https://github.com/settings/tokens). |
| `UPSTREAM_BRANCH` | `str` | Branch to use. Default: `master`. |

## 6. Leech

| Variable                | Type            | Description |
|-------------------------|-----------------|-------------|
| `LEECH_SPLIT_SIZE`       | `int`           | Split size in bytes. Default: `2GB`, `4GB` for premium. |
| `AS_DOCUMENT`            | `bool`          | Upload as document. Default: `False`. |
| `USER_TRANSMISSION`      | `bool`          | Use user session for UL/DL in supergroups. Default: `False`. |
| `HYBRID_LEECH`           | `bool`          | Switch sessions based on file size. Default: `False`. |
| `LEECH_FILENAME_PREFIX`  | `str`           | Add prefix to file name. |
| `LEECH_DUMP_CHAT`        | `list[str/int]` | Chat/channel to send files. Use `-100` prefix or `chat_id|thread_id`. |
| `THUMBNAIL_LAYOUT`       | `str`           | Layout like `2x2`, `4x4`, `3x3`, etc. |
| `LEECH_SUFFIX`           | `str`           | Add suffix to file name. |
| `LEECH_FONT`             | `str`           | Default font style for leech captions. |
| `LEECH_FILENAME`         | `str`           | Custom filename template for leeched files. |
| `EQUAL_SPLITS`           | `bool`          | Create equal-sized splits. Default: `False`. |
| `MEDIA_GROUP`            | `bool`          | Send split files as media group. Default: `False`. |
| `LEECH_FILENAME_CAPTION` | `str`           | Template caption used for leeched/downloaded filenames. |

## 7. qBittorrent/Aria2c/Sabnzbd

| Variable           | Type   | Description |
|--------------------|--------|-------------|
| `TORRENT_TIMEOUT`   | `int`  | Timeout in seconds for dead torrents. |
| `BASE_URL`          | `str`  | Bot URL. Example: `http://myip` or `http://myip:port`. |
| `BASE_URL_PORT`     | `int`  | Port. Default: `80`. |
| `WEB_PINCODE`       | `bool` | Ask PIN before file selection. Default: `False`. |

## 8. File2Link Streaming

| Variable                  | Type   | Description |
|---------------------------|--------|-------------|
| `FILE2LINK_ENABLED`       | `bool` | Enable File2Link streaming functionality. Default: `True`. |
| `FILE2LINK_BASE_URL`      | `str`  | Dedicated base URL for File2Link streaming. If not set, uses `BASE_URL`. Supports auto-detection for Heroku (`HEROKU_APP_NAME`), Railway (`RAILWAY_STATIC_URL`), and Render (`RENDER_EXTERNAL_URL`). |
| `FILE2LINK_BIN_CHANNEL`   | `int`  | **REQUIRED**: Private channel ID for storing streaming files (e.g., `-1001234567890`). Must be set for File2Link to work. Default: `0`. |
| `FILE2LINK_ALLOWED_TYPES` | `str`  | Comma-separated list of allowed media types for streaming. Default: `video,audio,document,photo,animation,voice,video_note`. |

**File Size Limits:**
- Automatically detects based on Telegram account type
- Non-Premium accounts: 2GB limit
- Premium accounts: 4GB limit
- Uses `USER_SESSION_STRING` and `USER_TRANSMISSION` for detection

**Commands:**
- `/file2link` or `/f2l` - Reply to any media file to generate streaming links
- Generates both streaming (browser player) and direct download links
- Supports range requests for video seeking

## 9. Forwarding Settings

| Variable                | Type        | Description |
|-------------------------|-------------|-------------|
| `FORWARD_SOURCE`        | `list[str]` | Source chat IDs/usernames for automatic forwarding. Supports chat IDs (e.g., `-1001234567890`) and usernames (e.g., `@channel1`). Default: `[]`. |
| `FORWARD_DESTINATION`   | `list[str]` | Destination chat IDs/usernames for automatic forwarding. Supports chat IDs (e.g., `-1001234567890`) and usernames (e.g., `@channel2`). Default: `[]`. |

**Configuration Examples:**
```python
# Forward from multiple sources to multiple destinations
FORWARD_SOURCE = ["-1001234567890", "@source_channel", "@another_source"]
FORWARD_DESTINATION = ["-1009876543210", "@dest_channel"]

# Simple channel to channel forwarding
FORWARD_SOURCE = ["@news_channel"]
FORWARD_DESTINATION = ["@my_backup_channel"]
```

**Features:**
- **Automatic Forwarding**: Monitors configured source chats and automatically forwards new messages
- **Duplicate Prevention**: Tracks forwarded messages to prevent duplicates
- **Multiple Sources/Destinations**: Supports forwarding from multiple sources to multiple destinations
- **Manual Forwarding**: Use `/forward` command for one-time bulk forwarding operations
- **Batch Processing**: Supports both batch mode (50 messages at a time) and direct mode (500 messages per chunk)

**Commands:**
- `/forward source_chat destination_chat` - Manual forwarding with interactive controls
- Supports options: `-skip N`, `-range START-END`, `-mode batch|direct`

## 10. JDownloader

| Variable     | Type  | Description |
|--------------|-------|-------------|
| `JD_EMAIL`    | `str` | Email for [JDownloader](https://my.jdownloader.org/). |
| `JD_PASS`     | `str` | Password. You may zip `cfg/` as `cfg.zip` and include in repo. |

## 11. Sabnzbd

| Variable        | Type   | Description |
|-----------------|--------|-------------|
| `USENET_SERVERS` | `list` | List of dicts with Usenet server config. Example:
```
[{'name': 'main', 'host': '', 'port': 563, 'timeout': 60, 'username': '', 'password': '', 'connections': 8, 'ssl': 1, 'ssl_verify': 2, 'ssl_ciphers': '', 'enable': 1, 'required': 0, 'optional': 0, 'retention': 0, 'send_group': 0, 'priority': 0}]
```
[More info](https://sabnzbd.org/wiki/configuration/4.2/servers)

## 11. RSS

| Variable         | Type         | Description |
|------------------|--------------|-------------|
| `RSS_DELAY`       | `int`        | Time interval in seconds. Default: `600`. |
| `RSS_SIZE_LIMIT`  | `int`        | Max item size in bytes. Default: `0`. |
| `RSS_CHAT`        | `str`/`int`  | Chat ID or username. Use `channel|topic` format if needed. |

**Note:** `RSS_CHAT` is mandatory. Requires either `USER_SESSION_STRING` or linked group/channel setup.

## 12. Queue System

| Variable          | Type  | Description |
|-------------------|-------|-------------|
| `QUEUE_ALL`        | `int` | Max concurrent upload + download tasks. |
| `QUEUE_DOWNLOAD`   | `int` | Max concurrent download tasks. |
| `QUEUE_UPLOAD`     | `int` | Max concurrent upload tasks. |

## 13. NZB Search

| Variable         | Type  | Description |
|------------------|-------|-------------|
| `HYDRA_IP`        | `str` | IP of [nzbhydra2](https://github.com/theotherp/nzbhydra2). |
| `HYDRA_API_KEY`   | `str` | API key from nzbhydra2. |

## 14. DDL (Direct Download Link) Upload Settings

### Basic DDL Settings
| Variable              | Type   | Description |
|-----------------------|--------|-------------|
| `DDL_ENABLED`         | `bool` | Enable/disable DDL upload feature. Default: `True`. |
| `DDL_DEFAULT_SERVER`  | `str`  | Default DDL server to use. Options: `gofile`, `streamtape`, `devuploads`, `mediafire`. Default: `gofile`. |

### Gofile Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GOFILE_ENABLED`            | `bool` | Enable/disable Gofile uploads. Default: `True`. |
| `GOFILE_API_KEY`            | `str`  | Default Gofile API key (can be overridden per user). Get from [Gofile](https://gofile.io/). |
| `GOFILE_FOLDER_NAME`        | `str`  | Default folder name for uploads (empty = use filename). |
| `GOFILE_PUBLIC_LINKS`       | `bool` | Generate public links by default. Default: `True`. |
| `GOFILE_PASSWORD_PROTECTION`| `bool` | Enable password protection for uploads. Default: `False`. |
| `GOFILE_DEFAULT_PASSWORD`   | `str`  | Default password for protected uploads. |
| `GOFILE_LINK_EXPIRY_DAYS`   | `int`  | Link expiry in days (0 = no expiry). Default: `0`. |

### Streamtape Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMTAPE_ENABLED`        | `bool` | Enable/disable Streamtape uploads. Default: `True`. |
| `STREAMTAPE_API_USERNAME`   | `str`  | Streamtape API/FTP Username from account panel. Get from [Streamtape Account Panel](https://streamtape.com/accpanel). |
| `STREAMTAPE_API_PASSWORD`   | `str`  | Streamtape API/FTP Password from account panel. Get from [Streamtape Account Panel](https://streamtape.com/accpanel). |
| `STREAMTAPE_FOLDER_NAME`    | `str`  | Default folder name for uploads. |

### DevUploads Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `DEVUPLOADS_API_KEY`        | `str`  | Default DevUploads API key. Get from [DevUploads](https://devuploads.com/). |
| `DEVUPLOADS_FOLDER_NAME`    | `str`  | Default folder name for uploads. |
| `DEVUPLOADS_PUBLIC_FILES`   | `bool` | Default public/private setting for uploads. Default: `True`. |

### MediaFire Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `MEDIAFIRE_EMAIL`           | `str`  | MediaFire account email for authentication. |
| `MEDIAFIRE_PASSWORD`        | `str`  | MediaFire account password for authentication. |
| `MEDIAFIRE_APP_ID`          | `str`  | MediaFire application ID (required for API access). Get from [MediaFire Developers](https://www.mediafire.com/developers/). |
| `MEDIAFIRE_API_KEY`         | `str`  | MediaFire API key (optional, for enhanced features). Get from [MediaFire Developers](https://www.mediafire.com/developers/). |

**Note:** DDL uploads support Gofile, Streamtape, DevUploads, and MediaFire services. Users can configure their own API keys in user settings. Streamtape only supports video files with specific extensions. MediaFire supports all file types up to ~50GB.

**Usage:**
- Use `-up ddl` to upload to the default DDL server
- Use `-up ddl:gofile` to upload specifically to Gofile
- Use `-up ddl:streamtape` to upload specifically to Streamtape
- Use `-up ddl:devuploads` to upload specifically to DevUploads
- Use `-up ddl:mediafire` to upload specifically to MediaFire

## 15. Streamrip Integration

### Basic Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_ENABLED`         | `bool` | Enable/disable streamrip music downloading functionality. Default: `True`. |
| `STREAMRIP_CONCURRENT_DOWNLOADS` | `int` | Number of concurrent downloads. Default: `4`. |
| `STREAMRIP_MAX_SEARCH_RESULTS` | `int` | Maximum search results to display. Default: `200`. |
| `STREAMRIP_ENABLE_DATABASE` | `bool` | Enable download database tracking. Default: `True`. |
| `STREAMRIP_AUTO_CONVERT`    | `bool` | Enable automatic format conversion. Default: `True`. |
| `STREAMRIP_LIMIT`           | `float` | Download limit in GB. Default: `0` (unlimited). |

### Quality and Format Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_DEFAULT_QUALITY` | `int`  | Default quality level (0-3). Default: `3` (highest). |
| `STREAMRIP_FALLBACK_QUALITY` | `int` | Fallback quality if default unavailable. Default: `2`. |
| `STREAMRIP_DEFAULT_CODEC`   | `str`  | Default audio codec. Default: `flac`. |
| `STREAMRIP_SUPPORTED_CODECS` | `list` | List of supported codecs: `["flac", "mp3", "m4a", "ogg", "opus"]`. |
| `STREAMRIP_QUALITY_FALLBACK_ENABLED` | `bool` | Enable quality fallback. Default: `True`. |

### Platform Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_QOBUZ_ENABLED`   | `bool` | Enable Qobuz downloads. Default: `True`. |
| `STREAMRIP_QOBUZ_QUALITY`   | `int`  | Qobuz quality level (0-3). Default: `3`. |
| `STREAMRIP_TIDAL_ENABLED`   | `bool` | Enable Tidal downloads. Default: `True`. |
| `STREAMRIP_TIDAL_QUALITY`   | `int`  | Tidal quality level (0-3). Default: `3`. |
| `STREAMRIP_DEEZER_ENABLED`  | `bool` | Enable Deezer downloads. Default: `True`. |
| `STREAMRIP_DEEZER_QUALITY`  | `int`  | Deezer quality level (0-2). Default: `2`. |
| `STREAMRIP_SOUNDCLOUD_ENABLED` | `bool` | Enable SoundCloud downloads. Default: `True`. |
| `STREAMRIP_SOUNDCLOUD_QUALITY` | `int` | SoundCloud quality level. Default: `0`. |
| `STREAMRIP_LASTFM_ENABLED`  | `bool` | Enable Last.fm integration. Default: `True`. |
| `STREAMRIP_YOUTUBE_QUALITY` | `int`  | YouTube quality level. Default: `0`. |

### Authentication Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_QOBUZ_EMAIL`     | `str`  | Qobuz account email for authentication. |
| `STREAMRIP_QOBUZ_PASSWORD`  | `str`  | Qobuz account password. |
| `STREAMRIP_QOBUZ_APP_ID`    | `str`  | Qobuz application ID for API access. |
| `STREAMRIP_QOBUZ_SECRETS`   | `list` | Qobuz application secrets list. |
| `STREAMRIP_TIDAL_EMAIL`     | `str`  | Tidal account email for authentication. |
| `STREAMRIP_TIDAL_PASSWORD`  | `str`  | Tidal account password. |
| `STREAMRIP_TIDAL_ACCESS_TOKEN` | `str` | Tidal access token for API authentication. |
| `STREAMRIP_TIDAL_REFRESH_TOKEN` | `str` | Tidal refresh token for token renewal. |
| `STREAMRIP_TIDAL_USER_ID`   | `str`  | Tidal user ID for account identification. |
| `STREAMRIP_TIDAL_COUNTRY_CODE` | `str` | Tidal country code for regional content. |
| `STREAMRIP_DEEZER_ARL`      | `str`  | Deezer ARL token for authentication. |
| `STREAMRIP_SOUNDCLOUD_CLIENT_ID` | `str` | SoundCloud client ID for API access. |
| `STREAMRIP_SOUNDCLOUD_APP_VERSION` | `str` | SoundCloud app version for compatibility. |

### Advanced Features
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_FILENAME_TEMPLATE` | `str` | Custom filename template for downloads. |
| `STREAMRIP_FOLDER_TEMPLATE` | `str`  | Custom folder structure template. |
| `STREAMRIP_EMBED_COVER_ART` | `bool` | Embed album artwork in files. Default: `True`. |
| `STREAMRIP_SAVE_COVER_ART`  | `bool` | Save separate cover art files. Default: `True`. |
| `STREAMRIP_COVER_ART_SIZE`  | `str`  | Cover art size preference. Default: `large`. |

### Download Configuration
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_MAX_CONNECTIONS` | `int`  | Maximum connections per download. Default: `6`. |
| `STREAMRIP_REQUESTS_PER_MINUTE` | `int` | API requests per minute limit. Default: `60`. |
| `STREAMRIP_SOURCE_SUBDIRECTORIES` | `bool` | Create source subdirectories. Default: `False`. |
| `STREAMRIP_DISC_SUBDIRECTORIES` | `bool` | Create disc subdirectories. Default: `True`. |
| `STREAMRIP_CONCURRENCY`     | `bool` | Enable concurrent downloads. Default: `True`. |
| `STREAMRIP_VERIFY_SSL`      | `bool` | Verify SSL certificates. Default: `True`. |

### Platform-Specific Configuration
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS` | `bool` | Download PDF booklets from Qobuz. Default: `True`. |
| `STREAMRIP_QOBUZ_USE_AUTH_TOKEN` | `bool` | Use authentication token for Qobuz. Default: `False`. |
| `STREAMRIP_TIDAL_DOWNLOAD_VIDEOS` | `bool` | Download videos from Tidal. Default: `True`. |
| `STREAMRIP_TIDAL_TOKEN_EXPIRY` | `str` | Tidal token expiry timestamp. Default: `0`. |
| `STREAMRIP_DEEZER_USE_DEEZLOADER` | `bool` | Use Deezloader for Deezer. Default: `True`. |
| `STREAMRIP_DEEZER_DEEZLOADER_WARNINGS` | `bool` | Show Deezloader warnings. Default: `True`. |
| `STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS` | `bool` | Download videos from YouTube. Default: `False`. |
| `STREAMRIP_YOUTUBE_VIDEO_FOLDER` | `str` | YouTube video download folder. |
| `STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER` | `str` | YouTube video downloads folder. |

### Database Configuration
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_DATABASE_DOWNLOADS_ENABLED` | `bool` | Enable downloads database. Default: `True`. |
| `STREAMRIP_DATABASE_DOWNLOADS_PATH` | `str` | Downloads database path. Default: `./downloads.db`. |
| `STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED` | `bool` | Enable failed downloads database. Default: `True`. |
| `STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH` | `str` | Failed downloads database path. Default: `./failed_downloads.db`. |

### Conversion Configuration
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_CONVERSION_ENABLED` | `bool` | Enable format conversion. Default: `False`. |
| `STREAMRIP_CONVERSION_CODEC` | `str`  | Conversion codec. Default: `ALAC`. |
| `STREAMRIP_CONVERSION_SAMPLING_RATE` | `int` | Conversion sampling rate. Default: `48000`. |
| `STREAMRIP_CONVERSION_BIT_DEPTH` | `int` | Conversion bit depth. Default: `24`. |
| `STREAMRIP_CONVERSION_LOSSY_BITRATE` | `int` | Lossy conversion bitrate. Default: `320`. |

### Filters and Metadata
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_QOBUZ_FILTERS_EXTRAS` | `bool` | Filter extra content from Qobuz. Default: `False`. |
| `STREAMRIP_QOBUZ_FILTERS_REPEATS` | `bool` | Filter repeat content. Default: `False`. |
| `STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS` | `bool` | Filter non-album content. Default: `False`. |
| `STREAMRIP_QOBUZ_FILTERS_FEATURES` | `bool` | Filter featured content. Default: `False`. |
| `STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS` | `bool` | Filter non-studio albums. Default: `False`. |
| `STREAMRIP_QOBUZ_FILTERS_NON_REMASTER` | `bool` | Filter non-remaster content. Default: `False`. |
| `STREAMRIP_ARTWORK_EMBED_MAX_WIDTH` | `int` | Max width for embedded artwork. Default: `-1` (no limit). |
| `STREAMRIP_ARTWORK_SAVED_MAX_WIDTH` | `int` | Max width for saved artwork. Default: `-1` (no limit). |
| `STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM` | `bool` | Set playlist as album in metadata. Default: `True`. |
| `STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS` | `bool` | Renumber playlist tracks. Default: `True`. |
| `STREAMRIP_METADATA_EXCLUDE` | `list` | Metadata tags to exclude from files. |

### File Paths and Naming
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER` | `bool` | Add singles to folder. Default: `False`. |
| `STREAMRIP_FILEPATHS_FOLDER_FORMAT` | `str` | Folder naming format template. |
| `STREAMRIP_FILEPATHS_TRACK_FORMAT` | `str` | Track naming format template. |
| `STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS` | `bool` | Restrict special characters in filenames. Default: `False`. |
| `STREAMRIP_FILEPATHS_TRUNCATE_TO` | `int` | Truncate filenames to length. Default: `120`. |

### Last.fm and CLI Configuration
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_LASTFM_SOURCE`   | `str`  | Last.fm source platform. Default: `qobuz`. |
| `STREAMRIP_LASTFM_FALLBACK_SOURCE` | `str` | Last.fm fallback source platform. |
| `STREAMRIP_CLI_TEXT_OUTPUT` | `bool` | Enable CLI text output. Default: `True`. |
| `STREAMRIP_CLI_PROGRESS_BARS` | `bool` | Show CLI progress bars. Default: `True`. |
| `STREAMRIP_CLI_MAX_SEARCH_RESULTS` | `int` | Max CLI search results. Default: `200`. |

### Miscellaneous
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `STREAMRIP_MISC_CHECK_FOR_UPDATES` | `bool` | Check for streamrip updates. Default: `True`. |
| `STREAMRIP_MISC_VERSION`    | `str`  | Streamrip version. Default: `2.0.6`. |

## 16. Zotify Integration

### Basic Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_ENABLED`            | `bool` | Enable/disable Zotify Spotify downloading functionality. Default: `True`. |
| `ZOTIFY_CREDENTIALS_PATH`   | `str`  | Path to Spotify credentials file. Default: `./zotify_credentials.json`. |
| `ZOTIFY_LIMIT`              | `float` | Download limit in GB. Default: `0` (unlimited). |

### Library Paths
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_ALBUM_LIBRARY`      | `str`  | Directory for album downloads. Default: `Music/Zotify Albums`. |
| `ZOTIFY_PODCAST_LIBRARY`    | `str`  | Directory for podcast downloads. Default: `Music/Zotify Podcasts`. |
| `ZOTIFY_PLAYLIST_LIBRARY`   | `str`  | Directory for playlist downloads. Default: `Music/Zotify Playlists`. |

### Output Templates
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_OUTPUT_ALBUM`       | `str`  | Album track naming template. Default: `{album_artist}/{album}/{track_number}. {artists} - {title}`. |
| `ZOTIFY_OUTPUT_PLAYLIST_TRACK` | `str` | Playlist track naming template. Default: `{playlist}/{artists} - {title}`. |
| `ZOTIFY_OUTPUT_PLAYLIST_EPISODE` | `str` | Playlist episode naming template. Default: `{playlist}/{episode_number} - {title}`. |
| `ZOTIFY_OUTPUT_PODCAST`     | `str`  | Podcast episode naming template. Default: `{podcast}/{episode_number} - {title}`. |
| `ZOTIFY_OUTPUT_SINGLE`      | `str`  | Single track naming template. Default: `{artists} - {title}`. |

### Quality and Format Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_DOWNLOAD_QUALITY`   | `str`  | Download quality: `auto`, `normal`, `high`, `very_high`. Default: `normal`. |
| `ZOTIFY_AUDIO_FORMAT`       | `str`  | Output audio format: `vorbis`, `mp3`, `flac`, `aac`, `fdk_aac`, `opus`, `wav`, `wavpack`. Default: `mp3`. |
| `ZOTIFY_ARTWORK_SIZE`       | `str`  | Album artwork size: `small`, `medium`, `large`. Default: `medium`. |
| `ZOTIFY_TRANSCODE_BITRATE`  | `int`  | Transcoding bitrate in kbps (-1 to use download rate). Default: `-1`. |

### Download Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_DOWNLOAD_REAL_TIME` | `bool` | Download at the same rate as track playback. Default: `False`. |
| `ZOTIFY_REPLACE_EXISTING`   | `bool` | Replace existing files when downloading. Default: `False`. |
| `ZOTIFY_SKIP_DUPLICATES`    | `bool` | Skip downloading duplicate tracks. Default: `True`. |
| `ZOTIFY_SKIP_PREVIOUS`      | `bool` | Skip tracks that were previously downloaded. Default: `True`. |

### Metadata and Files
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_SAVE_METADATA`      | `bool` | Save metadata tags to downloaded files. Default: `True`. |
| `ZOTIFY_SAVE_GENRE`         | `bool` | Include genre information in metadata. Default: `False`. |
| `ZOTIFY_ALL_ARTISTS`        | `bool` | Include all artists in metadata. Default: `True`. |
| `ZOTIFY_LYRICS_FILE`        | `bool` | Save lyrics as separate .lrc files. Default: `False`. |
| `ZOTIFY_LYRICS_ONLY`        | `bool` | Download only lyrics without audio. Default: `False`. |
| `ZOTIFY_SAVE_SUBTITLES`     | `bool` | Save subtitles for podcast episodes. Default: `False`. |
| `ZOTIFY_CREATE_PLAYLIST_FILE` | `bool` | Create .m3u playlist files for playlists. Default: `True`. |

### FFmpeg Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_FFMPEG_PATH`        | `str`  | FFmpeg binary path or name. |
| `ZOTIFY_FFMPEG_ARGS`        | `str`  | Additional FFmpeg arguments for transcoding. |

### Language and Locale
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_LANGUAGE`           | `str`  | Language code for metadata and interface. Default: `en`. |

### Print/Logging Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_PRINT_PROGRESS`     | `bool` | Show download progress in logs. Default: `True`. |
| `ZOTIFY_PRINT_DOWNLOADS`    | `bool` | Print download start messages. Default: `False`. |
| `ZOTIFY_PRINT_ERRORS`       | `bool` | Print error messages. Default: `True`. |
| `ZOTIFY_PRINT_WARNINGS`     | `bool` | Print warning messages. Default: `True`. |
| `ZOTIFY_PRINT_SKIPS`        | `bool` | Print skip messages for existing files. Default: `False`. |

### Match Functionality
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_MATCH_EXISTING`     | `bool` | Match existing files for skip functionality. Default: `False`. |

### Supported Formats
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `ZOTIFY_SUPPORTED_AUDIO_FORMATS` | `list` | List of supported audio formats: `["vorbis", "mp3", "flac", "aac", "fdk_aac", "opus", "wav", "wavpack"]`. |
| `ZOTIFY_SUPPORTED_QUALITIES` | `list` | List of supported qualities: `["auto", "normal", "high", "very_high"]`. |
| `ZOTIFY_SUPPORTED_ARTWORK_SIZES` | `list` | List of supported artwork sizes: `["small", "medium", "large"]`. |

## 17. Gallery-dl Integration

### Basic Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GALLERY_DL_ENABLED`        | `bool` | Enable/disable gallery-dl feature for 200+ platforms. Default: `True`. |
| `GALLERY_DL_OPTIONS`        | `dict` | Gallery-dl configuration options as dictionary. |
| `GALLERY_DL_QUALITY_SELECTION` | `bool` | Enable interactive quality selection. Default: `True`. |
| `GALLERY_DL_ARCHIVE_ENABLED` | `bool` | Enable archive to avoid re-downloading. Default: `True`. |
| `GALLERY_DL_METADATA_ENABLED` | `bool` | Save metadata files (JSON, YAML, TXT). Default: `True`. |
| `GALLERY_DL_MAX_DOWNLOADS`  | `int`  | Maximum files per download (0 = unlimited). Default: `50`. |
| `GALLERY_DL_RATE_LIMIT`     | `str`  | Rate limit (requests per second). Default: `1/s`. |
| `GALLERY_DL_LIMIT`          | `float` | Download limit in GB. Default: `0` (unlimited). |

### Gallery-dl Authentication Settings

#### Instagram
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GALLERY_DL_INSTAGRAM_USERNAME` | `str` | Instagram username for private accounts and stories. |
| `GALLERY_DL_INSTAGRAM_PASSWORD` | `str` | Instagram password for authentication. |

#### Twitter/X
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GALLERY_DL_TWITTER_USERNAME` | `str` | Twitter username for private accounts and higher quality. |
| `GALLERY_DL_TWITTER_PASSWORD` | `str` | Twitter password for authentication. |

#### Reddit
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GALLERY_DL_REDDIT_CLIENT_ID` | `str` | Reddit app client ID for private subreddits. |
| `GALLERY_DL_REDDIT_CLIENT_SECRET` | `str` | Reddit app client secret for enhanced access. |
| `GALLERY_DL_REDDIT_USERNAME` | `str` | Reddit username for authentication. |
| `GALLERY_DL_REDDIT_PASSWORD` | `str` | Reddit password for authentication. |
| `GALLERY_DL_REDDIT_REFRESH_TOKEN` | `str` | Reddit refresh token for API access. |

#### Pixiv
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GALLERY_DL_PIXIV_USERNAME` | `str` | Pixiv username for following artists and premium content. |
| `GALLERY_DL_PIXIV_PASSWORD` | `str` | Pixiv password for authentication. |
| `GALLERY_DL_PIXIV_REFRESH_TOKEN` | `str` | Pixiv refresh token for API access. |

#### DeviantArt
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GALLERY_DL_DEVIANTART_CLIENT_ID` | `str` | DeviantArt app client ID for premium content. |
| `GALLERY_DL_DEVIANTART_CLIENT_SECRET` | `str` | DeviantArt app client secret for Eclipse features. |
| `GALLERY_DL_DEVIANTART_USERNAME` | `str` | DeviantArt username for authentication. |
| `GALLERY_DL_DEVIANTART_PASSWORD` | `str` | DeviantArt password for authentication. |

#### Tumblr
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GALLERY_DL_TUMBLR_API_KEY` | `str` | Tumblr API key for enhanced access. |
| `GALLERY_DL_TUMBLR_API_SECRET` | `str` | Tumblr API secret for API features. |
| `GALLERY_DL_TUMBLR_TOKEN`   | `str` | Tumblr access token for authentication. |
| `GALLERY_DL_TUMBLR_TOKEN_SECRET` | `str` | Tumblr access token secret for authentication. |

#### Discord
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GALLERY_DL_DISCORD_TOKEN`  | `str` | Discord bot token for server content access. |

## 18. YouTube Upload Settings

### Basic Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `YOUTUBE_UPLOAD_ENABLED`    | `bool` | Enable/disable YouTube upload feature. Default: `True`. |
| `YOUTUBE_UPLOAD_DEFAULT_PRIVACY` | `str` | Default privacy setting: `public`, `unlisted`, `private`. Default: `unlisted`. |
| `YOUTUBE_UPLOAD_DEFAULT_CATEGORY` | `str` | Default category ID (22 = People & Blogs). Default: `22`. |
| `YOUTUBE_UPLOAD_DEFAULT_TAGS` | `str` | Default tags for uploaded videos, separated by comma. |
| `YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION` | `str` | Default description for uploaded videos. Default: `Uploaded by AIM`. |
| `YOUTUBE_UPLOAD_DEFAULT_TITLE` | `str` | Default title template (empty = use filename). |

### Advanced YouTube API Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `YOUTUBE_UPLOAD_DEFAULT_LANGUAGE` | `str` | Default language for video metadata (ISO 639-1 code). Default: `en`. |
| `YOUTUBE_UPLOAD_DEFAULT_LICENSE` | `str` | License: `youtube` (standard) or `creativeCommon`. Default: `youtube`. |
| `YOUTUBE_UPLOAD_EMBEDDABLE` | `bool` | Allow video to be embedded on other websites. Default: `True`. |
| `YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE` | `bool` | Allow public to see video statistics. Default: `True`. |
| `YOUTUBE_UPLOAD_MADE_FOR_KIDS` | `bool` | Mark videos as made for kids (COPPA compliance). Default: `False`. |
| `YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS` | `bool` | Notify subscribers when video is uploaded. Default: `True`. |
| `YOUTUBE_UPLOAD_LOCATION_DESCRIPTION` | `str` | Location description for videos. |
| `YOUTUBE_UPLOAD_RECORDING_DATE` | `str` | Recording date (YYYY-MM-DD format, empty = upload date). |
| `YOUTUBE_UPLOAD_AUTO_LEVELS` | `bool` | Auto-enhance video levels. Default: `False`. |
| `YOUTUBE_UPLOAD_STABILIZE`  | `bool` | Auto-stabilize shaky videos. Default: `False`. |

## 19. Media Tools

### Basic Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MEDIA_TOOLS_ENABLED`   | `str`  | Comma-separated list of enabled media tools. Options: `watermark,merge,convert,compression,trim,extract,add,metadata,xtra,sample,screenshot,archive`. |
| `MEDIAINFO_ENABLED`     | `bool` | Enable/disable mediainfo command for detailed media information. Default: `False`. |
| `MEDIA_STORE`           | `bool` | Enable media storage functionality. Default: `False`. |

### Compression Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `COMPRESSION_ENABLED`   | `bool` | Enable compression functionality. Default: `False`. |
| `COMPRESSION_PRIORITY`  | `int`  | Compression task priority. Default: `4`. |
| `COMPRESSION_DELETE_ORIGINAL` | `bool` | Delete original files after compression. Default: `True`. |

### Video Compression
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `COMPRESSION_VIDEO_ENABLED` | `bool` | Enable video compression. Default: `False`. |
| `COMPRESSION_VIDEO_PRESET` | `str` | Video compression preset. Options: `none,fast,medium,slow`. Default: `none`. |
| `COMPRESSION_VIDEO_CRF` | `str`  | Video CRF (Constant Rate Factor) value. Default: `none`. |
| `COMPRESSION_VIDEO_CODEC` | `str` | Video codec for compression. Default: `none`. |
| `COMPRESSION_VIDEO_TUNE` | `str` | Video encoding tune parameter. Default: `none`. |
| `COMPRESSION_VIDEO_PIXEL_FORMAT` | `str` | Video pixel format. Default: `none`. |
| `COMPRESSION_VIDEO_BITDEPTH` | `str` | Video bit depth. Default: `none`. |
| `COMPRESSION_VIDEO_BITRATE` | `str` | Video bitrate. Default: `none`. |
| `COMPRESSION_VIDEO_RESOLUTION` | `str` | Video resolution. Default: `none`. |
| `COMPRESSION_VIDEO_FORMAT` | `str` | Output format for video compression (e.g., mp4, mkv). Default: `none`. |

### Audio Compression
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `COMPRESSION_AUDIO_ENABLED` | `bool` | Enable audio compression. Default: `False`. |
| `COMPRESSION_AUDIO_PRESET` | `str` | Audio compression preset. Options: `none,fast,medium,slow`. Default: `none`. |
| `COMPRESSION_AUDIO_CODEC` | `str` | Audio codec for compression. Default: `none`. |
| `COMPRESSION_AUDIO_BITRATE` | `str` | Audio bitrate. Default: `none`. |
| `COMPRESSION_AUDIO_CHANNELS` | `str` | Audio channels. Default: `none`. |
| `COMPRESSION_AUDIO_BITDEPTH` | `str` | Audio bit depth. Default: `none`. |
| `COMPRESSION_AUDIO_FORMAT` | `str` | Output format for audio compression (e.g., mp3, aac). Default: `none`. |

### Image Compression
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `COMPRESSION_IMAGE_ENABLED` | `bool` | Enable image compression. Default: `False`. |
| `COMPRESSION_IMAGE_PRESET` | `str` | Image compression preset. Options: `none,fast,medium,slow`. Default: `none`. |
| `COMPRESSION_IMAGE_QUALITY` | `str` | Image compression quality. Default: `none`. |
| `COMPRESSION_IMAGE_RESIZE` | `str` | Image resize dimensions. Default: `none`. |
| `COMPRESSION_IMAGE_FORMAT` | `str` | Output format for image compression (e.g., jpg, png). Default: `none`. |

### Document Compression
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `COMPRESSION_DOCUMENT_ENABLED` | `bool` | Enable document compression. Default: `False`. |
| `COMPRESSION_DOCUMENT_PRESET` | `str` | Document compression preset. Options: `none,fast,medium,slow`. Default: `none`. |
| `COMPRESSION_DOCUMENT_DPI` | `str` | Document DPI setting. Default: `none`. |
| `COMPRESSION_DOCUMENT_FORMAT` | `str` | Output format for document compression (e.g., pdf). Default: `none`. |

### Subtitle Compression
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `COMPRESSION_SUBTITLE_ENABLED` | `bool` | Enable subtitle compression. Default: `False`. |
| `COMPRESSION_SUBTITLE_PRESET` | `str` | Subtitle compression preset. Options: `none,fast,medium,slow`. Default: `none`. |
| `COMPRESSION_SUBTITLE_ENCODING` | `str` | Subtitle encoding. Default: `none`. |
| `COMPRESSION_SUBTITLE_FORMAT` | `str` | Output format for subtitle compression (e.g., srt). Default: `none`. |

### Archive Compression
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `COMPRESSION_ARCHIVE_ENABLED` | `bool` | Enable archive compression. Default: `False`. |
| `COMPRESSION_ARCHIVE_PRESET` | `str` | Archive compression preset. Options: `none,fast,medium,slow`. Default: `none`. |
| `COMPRESSION_ARCHIVE_LEVEL` | `str` | Archive compression level. Default: `none`. |
| `COMPRESSION_ARCHIVE_METHOD` | `str` | Archive compression method. Default: `none`. |
| `COMPRESSION_ARCHIVE_FORMAT` | `str` | Output format for archive compression (e.g., zip, 7z). Default: `none`. |
| `COMPRESSION_ARCHIVE_PASSWORD` | `str` | Password for archive protection. Default: `none`. |
| `COMPRESSION_ARCHIVE_ALGORITHM` | `str` | Archive algorithm (e.g., 7z, zip). Default: `none`. |

### Trim Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `TRIM_ENABLED`          | `bool` | Enable trim functionality. Default: `False`. |
| `TRIM_PRIORITY`         | `int`  | Trim task priority. Default: `5`. |
| `TRIM_START_TIME`       | `str`  | Default start time for trimming. Default: `00:00:00`. |
| `TRIM_END_TIME`         | `str`  | Default end time for trimming. |
| `TRIM_DELETE_ORIGINAL`  | `bool` | Delete original files after trimming. Default: `False`. |

### Video Trim Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `TRIM_VIDEO_ENABLED`    | `bool` | Enable video trimming. Default: `False`. |
| `TRIM_VIDEO_CODEC`      | `str`  | Video codec for trimming. Default: `none`. |
| `TRIM_VIDEO_PRESET`     | `str`  | Video encoding preset. Default: `none`. |
| `TRIM_VIDEO_FORMAT`     | `str`  | Output format for video trimming. Default: `none`. |

### Audio Trim Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `TRIM_AUDIO_ENABLED`    | `bool` | Enable audio trimming. Default: `False`. |
| `TRIM_AUDIO_CODEC`      | `str`  | Audio codec for trimming. Default: `none`. |
| `TRIM_AUDIO_PRESET`     | `str`  | Audio encoding preset. Default: `none`. |
| `TRIM_AUDIO_FORMAT`     | `str`  | Output format for audio trimming. Default: `none`. |

### Image Trim Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `TRIM_IMAGE_ENABLED`    | `bool` | Enable image trimming. Default: `False`. |
| `TRIM_IMAGE_QUALITY`    | `int`  | Image quality for trimming. Default: `90`. |
| `TRIM_IMAGE_FORMAT`     | `str`  | Output format for image trimming. Default: `none`. |

### Document Trim Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TRIM_DOCUMENT_ENABLED`     | `bool` | Enable document trimming. Default: `False`. |
| `TRIM_DOCUMENT_START_PAGE`  | `str`  | Starting page number for document trimming. Default: `"1"`. |
| `TRIM_DOCUMENT_END_PAGE`    | `str`  | Ending page number for document trimming (empty for last page). Default: `""`. |
| `TRIM_DOCUMENT_QUALITY`     | `int`  | Document quality for trimming. Default: `90`. |
| `TRIM_DOCUMENT_FORMAT`      | `str`  | Output format for document trimming. Default: `none`. |

### Subtitle Trim Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `TRIM_SUBTITLE_ENABLED` | `bool` | Enable subtitle trimming. Default: `False`. |
| `TRIM_SUBTITLE_ENCODING` | `str` | Subtitle encoding. Default: `none`. |
| `TRIM_SUBTITLE_FORMAT`  | `str`  | Output format for subtitle trimming. Default: `none`. |

### Archive Trim Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `TRIM_ARCHIVE_ENABLED`  | `bool` | Enable archive trimming. Default: `False`. |
| `TRIM_ARCHIVE_FORMAT`   | `str`  | Output format for archive trimming. Default: `none`. |

### Extract Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `EXTRACT_ENABLED`       | `bool` | Enable extract functionality. Default: `False`. |
| `EXTRACT_PRIORITY`      | `int`  | Extract task priority. Default: `6`. |
| `EXTRACT_DELETE_ORIGINAL` | `bool` | Delete original files after extraction. Default: `True`. |
| `EXTRACT_MAINTAIN_QUALITY` | `bool` | Maintain quality during extraction. Default: `True`. |

### Video Extract Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `EXTRACT_VIDEO_ENABLED` | `bool` | Enable video extraction. Default: `False`. |
| `EXTRACT_VIDEO_CODEC`   | `str`  | Video codec for extraction. Default: `none`. |
| `EXTRACT_VIDEO_FORMAT`  | `str`  | Output format for video extraction. Default: `none`. |
| `EXTRACT_VIDEO_INDEX`   | `int`  | Video stream index to extract. Default: `None`. |
| `EXTRACT_VIDEO_QUALITY` | `str`  | Quality setting for video extraction. Default: `none`. |
| `EXTRACT_VIDEO_PRESET`  | `str`  | Preset for video encoding. Default: `none`. |
| `EXTRACT_VIDEO_BITRATE` | `str`  | Bitrate for video encoding. Default: `none`. |
| `EXTRACT_VIDEO_RESOLUTION` | `str` | Resolution for video extraction. Default: `none`. |
| `EXTRACT_VIDEO_FPS`     | `str`  | Frame rate for video extraction. Default: `none`. |

### Audio Extract Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `EXTRACT_AUDIO_ENABLED` | `bool` | Enable audio extraction. Default: `False`. |
| `EXTRACT_AUDIO_CODEC`   | `str`  | Audio codec for extraction. Default: `none`. |
| `EXTRACT_AUDIO_FORMAT`  | `str`  | Output format for audio extraction. Default: `none`. |
| `EXTRACT_AUDIO_INDEX`   | `int`  | Audio stream index to extract. Default: `None`. |
| `EXTRACT_AUDIO_BITRATE` | `str`  | Bitrate for audio encoding. Default: `none`. |
| `EXTRACT_AUDIO_CHANNELS` | `str` | Number of audio channels. Default: `none`. |
| `EXTRACT_AUDIO_SAMPLING` | `str` | Sampling rate for audio. Default: `none`. |
| `EXTRACT_AUDIO_VOLUME`  | `str`  | Volume adjustment for audio. Default: `none`. |

### Subtitle Extract Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `EXTRACT_SUBTITLE_ENABLED` | `bool` | Enable subtitle extraction. Default: `False`. |
| `EXTRACT_SUBTITLE_CODEC` | `str` | Subtitle codec for extraction. Default: `none`. |
| `EXTRACT_SUBTITLE_FORMAT` | `str` | Output format for subtitle extraction. Default: `none`. |
| `EXTRACT_SUBTITLE_INDEX` | `int` | Subtitle stream index to extract. Default: `None`. |
| `EXTRACT_SUBTITLE_LANGUAGE` | `str` | Language code for subtitle extraction. Default: `none`. |
| `EXTRACT_SUBTITLE_ENCODING` | `str` | Character encoding for subtitles. Default: `none`. |
| `EXTRACT_SUBTITLE_FONT` | `str` | Font for subtitles. Default: `none`. |
| `EXTRACT_SUBTITLE_FONT_SIZE` | `str` | Font size for subtitles. Default: `none`. |

### Attachment Extract Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `EXTRACT_ATTACHMENT_ENABLED` | `bool` | Enable attachment extraction. Default: `False`. |
| `EXTRACT_ATTACHMENT_FORMAT` | `str` | Output format for attachment extraction. Default: `none`. |
| `EXTRACT_ATTACHMENT_INDEX` | `int` | Attachment index to extract. Default: `None`. |
| `EXTRACT_ATTACHMENT_FILTER` | `str` | Filter for attachment extraction. Default: `none`. |

### Remove Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `REMOVE_ENABLED`        | `bool` | Enable remove functionality. Default: `False`. |
| `REMOVE_PRIORITY`       | `int`  | Remove task priority. Default: `8`. |
| `REMOVE_DELETE_ORIGINAL` | `bool` | Delete original files after removing tracks. Default: `True`. |
| `REMOVE_METADATA`       | `bool` | Remove metadata from files. Default: `False`. |
| `REMOVE_MAINTAIN_QUALITY` | `bool` | Maintain quality for remaining tracks. Default: `True`. |

### Video Remove Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `REMOVE_VIDEO_ENABLED`  | `bool` | Enable video track removal. Default: `False`. |
| `REMOVE_VIDEO_CODEC`    | `str`  | Video codec for remaining tracks. Default: `none`. |
| `REMOVE_VIDEO_FORMAT`   | `str`  | Output format for video removal. Default: `none`. |
| `REMOVE_VIDEO_INDEX`    | `int`  | Video track index to remove (supports comma-separated). Default: `None`. |
| `REMOVE_VIDEO_QUALITY`  | `str`  | Video quality for remaining tracks. Default: `none`. |
| `REMOVE_VIDEO_PRESET`   | `str`  | Video encoding preset for remaining tracks. Default: `none`. |
| `REMOVE_VIDEO_BITRATE`  | `str`  | Video bitrate for remaining tracks. Default: `none`. |
| `REMOVE_VIDEO_RESOLUTION` | `str` | Video resolution for remaining tracks. Default: `none`. |
| `REMOVE_VIDEO_FPS`      | `str`  | Video frame rate for remaining tracks. Default: `none`. |

### Audio Remove Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `REMOVE_AUDIO_ENABLED`  | `bool` | Enable audio track removal. Default: `False`. |
| `REMOVE_AUDIO_CODEC`    | `str`  | Audio codec for remaining tracks. Default: `none`. |
| `REMOVE_AUDIO_FORMAT`   | `str`  | Output format for audio removal. Default: `none`. |
| `REMOVE_AUDIO_INDEX`    | `int`  | Audio track index to remove (supports comma-separated). Default: `None`. |
| `REMOVE_AUDIO_BITRATE`  | `str`  | Audio bitrate for remaining tracks. Default: `none`. |
| `REMOVE_AUDIO_CHANNELS` | `str`  | Audio channels for remaining tracks. Default: `none`. |
| `REMOVE_AUDIO_SAMPLING` | `str`  | Audio sampling rate for remaining tracks. Default: `none`. |
| `REMOVE_AUDIO_VOLUME`   | `str`  | Audio volume adjustment for remaining tracks. Default: `none`. |

### Subtitle Remove Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `REMOVE_SUBTITLE_ENABLED` | `bool` | Enable subtitle track removal. Default: `False`. |
| `REMOVE_SUBTITLE_CODEC` | `str`  | Subtitle codec for remaining tracks. Default: `none`. |
| `REMOVE_SUBTITLE_FORMAT` | `str` | Output format for subtitle removal. Default: `none`. |
| `REMOVE_SUBTITLE_INDEX` | `int`  | Subtitle track index to remove (supports comma-separated). Default: `None`. |
| `REMOVE_SUBTITLE_LANGUAGE` | `str` | Language for remaining subtitle tracks. Default: `none`. |
| `REMOVE_SUBTITLE_ENCODING` | `str` | Character encoding for remaining subtitle tracks. Default: `none`. |
| `REMOVE_SUBTITLE_FONT`  | `str`  | Font for remaining subtitle tracks. Default: `none`. |
| `REMOVE_SUBTITLE_FONT_SIZE` | `str` | Font size for remaining subtitle tracks. Default: `none`. |

### Attachment Remove Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `REMOVE_ATTACHMENT_ENABLED` | `bool` | Enable attachment removal. Default: `False`. |
| `REMOVE_ATTACHMENT_FORMAT` | `str` | Output format for attachment removal. Default: `none`. |
| `REMOVE_ATTACHMENT_INDEX` | `int` | Attachment index to remove (supports comma-separated). Default: `None`. |
| `REMOVE_ATTACHMENT_FILTER` | `str` | Filter pattern for attachment removal. Default: `none`. |

### Add Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `ADD_ENABLED`           | `bool` | Enable add functionality. Default: `False`. |
| `ADD_PRIORITY`          | `int`  | Add task priority. Default: `7`. |
| `ADD_DELETE_ORIGINAL`   | `bool` | Delete original files after adding. Default: `True`. |
| `ADD_PRESERVE_TRACKS`   | `bool` | Preserve existing tracks when adding. Default: `False`. |
| `ADD_REPLACE_TRACKS`    | `bool` | Replace existing tracks when adding. Default: `False`. |

### Video Add Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `ADD_VIDEO_ENABLED`     | `bool` | Enable video adding. Default: `False`. |
| `ADD_VIDEO_CODEC`       | `str`  | Video codec for adding. Default: `copy`. |
| `ADD_VIDEO_INDEX`       | `int`  | Video stream index to add. Default: `None`. |
| `ADD_VIDEO_QUALITY`     | `str`  | Quality setting for video adding. Default: `none`. |
| `ADD_VIDEO_PRESET`      | `str`  | Preset for video encoding. Default: `none`. |
| `ADD_VIDEO_BITRATE`     | `str`  | Bitrate for video encoding. Default: `none`. |
| `ADD_VIDEO_RESOLUTION`  | `str`  | Resolution for video adding. Default: `none`. |
| `ADD_VIDEO_FPS`         | `str`  | Frame rate for video adding. Default: `none`. |

### Audio Add Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `ADD_AUDIO_ENABLED`     | `bool` | Enable audio adding. Default: `False`. |
| `ADD_AUDIO_CODEC`       | `str`  | Audio codec for adding. Default: `copy`. |
| `ADD_AUDIO_INDEX`       | `int`  | Audio stream index to add. Default: `None`. |
| `ADD_AUDIO_BITRATE`     | `str`  | Bitrate for audio encoding. Default: `none`. |
| `ADD_AUDIO_CHANNELS`    | `str`  | Number of audio channels. Default: `none`. |
| `ADD_AUDIO_SAMPLING`    | `str`  | Sampling rate for audio. Default: `none`. |
| `ADD_AUDIO_VOLUME`      | `str`  | Volume adjustment for audio. Default: `none`. |

### Subtitle Add Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `ADD_SUBTITLE_ENABLED`  | `bool` | Enable subtitle adding. Default: `False`. |
| `ADD_SUBTITLE_CODEC`    | `str`  | Subtitle codec for adding. Default: `copy`. |
| `ADD_SUBTITLE_INDEX`    | `int`  | Subtitle stream index to add. Default: `None`. |
| `ADD_SUBTITLE_LANGUAGE` | `str`  | Language code for subtitle adding. Default: `none`. |
| `ADD_SUBTITLE_ENCODING` | `str`  | Character encoding for subtitles. Default: `none`. |
| `ADD_SUBTITLE_FONT`     | `str`  | Font for subtitles. Default: `none`. |
| `ADD_SUBTITLE_FONT_SIZE` | `str` | Font size for subtitles. Default: `none`. |

### Attachment Add Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `ADD_ATTACHMENT_ENABLED` | `bool` | Enable attachment adding. Default: `False`. |
| `ADD_ATTACHMENT_INDEX`  | `int`  | Attachment index to add. Default: `None`. |
| `ADD_ATTACHMENT_MIMETYPE` | `str` | MIME type for attachment. Default: `none`. |
| `ADD_SUBTITLE_HARDSUB_ENABLED` | `bool` | Enable hardcoded subtitles when adding. Default: `False`. |

### Swap Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `SWAP_ENABLED`          | `bool` | Enable swap functionality. Default: `False`. |
| `SWAP_PRIORITY`         | `int`  | Swap task priority. Default: `6`. |
| `SWAP_REMOVE_ORIGINAL`  | `bool` | Remove original files after swapping. Default: `False`. |

### Audio Swap Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `SWAP_AUDIO_ENABLED`    | `bool` | Enable audio track swapping. Default: `False`. |
| `SWAP_AUDIO_USE_LANGUAGE` | `bool` | Use language for audio track selection. Default: `True`. |
| `SWAP_AUDIO_LANGUAGE_ORDER` | `str` | Language order for audio track selection. Default: `eng,hin`. |
| `SWAP_AUDIO_INDEX_ORDER` | `str` | Index order for audio track selection. Default: `0,1`. |

### Video Swap Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `SWAP_VIDEO_ENABLED`    | `bool` | Enable video track swapping. Default: `False`. |
| `SWAP_VIDEO_USE_LANGUAGE` | `bool` | Use language for video track selection. Default: `True`. |
| `SWAP_VIDEO_LANGUAGE_ORDER` | `str` | Language order for video track selection. Default: `eng,hin`. |
| `SWAP_VIDEO_INDEX_ORDER` | `str` | Index order for video track selection. Default: `0,1`. |

### Subtitle Swap Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `SWAP_SUBTITLE_ENABLED` | `bool` | Enable subtitle track swapping. Default: `False`. |
| `SWAP_SUBTITLE_USE_LANGUAGE` | `bool` | Use language for subtitle track selection. Default: `True`. |
| `SWAP_SUBTITLE_LANGUAGE_ORDER` | `str` | Language order for subtitle track selection. Default: `eng,hin`. |
| `SWAP_SUBTITLE_INDEX_ORDER` | `str` | Index order for subtitle track selection. Default: `0,1`. |

### Convert Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `CONVERT_ENABLED`       | `bool` | Enable convert functionality. Default: `False`. |
| `CONVERT_PRIORITY`      | `int`  | Convert task priority. Default: `3`. |
| `CONVERT_DELETE_ORIGINAL` | `bool` | Delete original files after conversion. Default: `True`. |

### Video Convert Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `CONVERT_VIDEO_ENABLED` | `bool` | Enable video conversion. Default: `False`. |
| `CONVERT_VIDEO_FORMAT`  | `str`  | Output format for video conversion. Default: `none`. |
| `CONVERT_VIDEO_CODEC`   | `str`  | Video codec for conversion. Default: `none`. |
| `CONVERT_VIDEO_QUALITY` | `str`  | Quality setting for video conversion. Default: `none`. |
| `CONVERT_VIDEO_CRF`     | `int`  | CRF value for video conversion. Default: `0`. |
| `CONVERT_VIDEO_PRESET`  | `str`  | Preset for video encoding. Default: `none`. |
| `CONVERT_VIDEO_MAINTAIN_QUALITY` | `bool` | Maintain quality during conversion. Default: `True`. |
| `CONVERT_VIDEO_RESOLUTION` | `str` | Resolution for video conversion. Default: `none`. |
| `CONVERT_VIDEO_FPS`     | `str`  | Frame rate for video conversion. Default: `none`. |

### Audio Convert Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `CONVERT_AUDIO_ENABLED` | `bool` | Enable audio conversion. Default: `False`. |
| `CONVERT_AUDIO_FORMAT`  | `str`  | Output format for audio conversion. Default: `none`. |
| `CONVERT_AUDIO_CODEC`   | `str`  | Audio codec for conversion. Default: `none`. |
| `CONVERT_AUDIO_BITRATE` | `str`  | Bitrate for audio encoding. Default: `none`. |
| `CONVERT_AUDIO_CHANNELS` | `int` | Number of audio channels. Default: `0`. |
| `CONVERT_AUDIO_SAMPLING` | `int` | Sampling rate for audio. Default: `0`. |
| `CONVERT_AUDIO_VOLUME`  | `float` | Volume adjustment for audio. Default: `0.0`. |

### Subtitle Convert Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `CONVERT_SUBTITLE_ENABLED` | `bool` | Enable subtitle conversion. Default: `False`. |
| `CONVERT_SUBTITLE_FORMAT` | `str` | Output format for subtitle conversion. Default: `none`. |
| `CONVERT_SUBTITLE_ENCODING` | `str` | Character encoding for subtitles. Default: `none`. |
| `CONVERT_SUBTITLE_LANGUAGE` | `str` | Language code for subtitle conversion. Default: `none`. |

### Document Convert Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `CONVERT_DOCUMENT_ENABLED` | `bool` | Enable document conversion. Default: `False`. |
| `CONVERT_DOCUMENT_FORMAT` | `str` | Output format for document conversion. Default: `none`. |
| `CONVERT_DOCUMENT_QUALITY` | `int` | Quality setting for document conversion. Default: `0`. |
| `CONVERT_DOCUMENT_DPI`  | `int`  | DPI setting for document conversion. Default: `0`. |

### Archive Convert Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `CONVERT_ARCHIVE_ENABLED` | `bool` | Enable archive conversion. Default: `False`. |
| `CONVERT_ARCHIVE_FORMAT` | `str` | Output format for archive conversion. Default: `none`. |
| `CONVERT_ARCHIVE_LEVEL` | `int`  | Compression level for archive conversion. Default: `0`. |
| `CONVERT_ARCHIVE_METHOD` | `str` | Compression method for archive conversion. Default: `none`. |

### Watermark Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `WATERMARK_ENABLED`     | `bool` | Enable watermark functionality. Default: `False`. |
| `WATERMARK_KEY`         | `str`  | Key used for watermarking files or content. |
| `WATERMARK_POSITION`    | `str`  | Watermark position. Default: `none`. |
| `WATERMARK_SIZE`        | `int`  | Watermark size. Default: `0`. |
| `WATERMARK_COLOR`       | `str`  | Watermark color. Default: `none`. |
| `WATERMARK_FONT`        | `str`  | Watermark font. Default: `none`. |
| `WATERMARK_PRIORITY`    | `int`  | Watermark task priority. Default: `2`. |
| `WATERMARK_THREADING`   | `bool` | Enable watermark threading. Default: `True`. |
| `WATERMARK_THREAD_NUMBER` | `int` | Number of watermark threads. Default: `4`. |
| `WATERMARK_QUALITY`     | `str`  | Watermark quality setting. Default: `none`. |
| `WATERMARK_SPEED`       | `str`  | Watermark processing speed. Default: `none`. |
| `WATERMARK_OPACITY`     | `float` | Watermark opacity. Default: `0.0`. |
| `WATERMARK_REMOVE_ORIGINAL` | `bool` | Remove original files after watermarking. Default: `True`. |

### Audio Watermark Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `AUDIO_WATERMARK_VOLUME` | `float` | Audio watermark volume. Default: `0.0`. |
| `AUDIO_WATERMARK_INTERVAL` | `int` | Audio watermark interval. Default: `0`. |

### Subtitle Watermark Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `SUBTITLE_WATERMARK_STYLE` | `str` | Subtitle watermark style. Default: `none`. |
| `SUBTITLE_WATERMARK_INTERVAL` | `int` | Subtitle watermark interval. Default: `0`. |

### Image Watermark Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `IMAGE_WATERMARK_ENABLED` | `bool` | Enable image watermarking. Default: `False`. |
| `IMAGE_WATERMARK_PATH`  | `str`  | Path to watermark image. |
| `IMAGE_WATERMARK_SCALE` | `int`  | Image watermark scale percentage. Default: `10`. |
| `IMAGE_WATERMARK_OPACITY` | `float` | Image watermark opacity. Default: `1.0`. |
| `IMAGE_WATERMARK_POSITION` | `str` | Image watermark position. Default: `bottom_right`. |

### Merge Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MERGE_ENABLED`         | `bool` | Enable merge functionality. Default: `False`. |
| `MERGE_PRIORITY`        | `int`  | Merge task priority. Default: `1`. |
| `MERGE_THREADING`       | `bool` | Enable merge threading. Default: `True`. |
| `MERGE_THREAD_NUMBER`   | `int`  | Number of merge threads. Default: `4`. |
| `CONCAT_DEMUXER_ENABLED` | `bool` | Enable concat demuxer. Default: `True`. |
| `FILTER_COMPLEX_ENABLED` | `bool` | Enable filter complex. Default: `False`. |
| `MERGE_REMOVE_ORIGINAL` | `bool` | Remove original files after merging. Default: `True`. |

### Merge Output Formats
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MERGE_OUTPUT_FORMAT_VIDEO` | `str` | Output format for video merging. Default: `none`. |
| `MERGE_OUTPUT_FORMAT_AUDIO` | `str` | Output format for audio merging. Default: `none`. |
| `MERGE_OUTPUT_FORMAT_IMAGE` | `str` | Output format for image merging. Default: `none`. |
| `MERGE_OUTPUT_FORMAT_DOCUMENT` | `str` | Output format for document merging. Default: `none`. |
| `MERGE_OUTPUT_FORMAT_SUBTITLE` | `str` | Output format for subtitle merging. Default: `none`. |

### Merge Video Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MERGE_VIDEO_CODEC`     | `str`  | Video codec for merging. Default: `none`. |
| `MERGE_VIDEO_QUALITY`   | `str`  | Video quality for merging. Default: `none`. |
| `MERGE_VIDEO_PRESET`    | `str`  | Video preset for merging. Default: `none`. |
| `MERGE_VIDEO_CRF`       | `str`  | Video CRF for merging. Default: `none`. |
| `MERGE_VIDEO_PIXEL_FORMAT` | `str` | Video pixel format for merging. Default: `none`. |
| `MERGE_VIDEO_TUNE`      | `str`  | Video tune setting for merging. Default: `none`. |
| `MERGE_VIDEO_FASTSTART` | `bool` | Enable video faststart for merging. Default: `False`. |

### Merge Audio Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MERGE_AUDIO_CODEC`     | `str`  | Audio codec for merging. Default: `none`. |
| `MERGE_AUDIO_BITRATE`   | `str`  | Audio bitrate for merging. Default: `none`. |
| `MERGE_AUDIO_CHANNELS`  | `str`  | Audio channels for merging. Default: `none`. |
| `MERGE_AUDIO_SAMPLING`  | `str`  | Audio sampling rate for merging. Default: `none`. |
| `MERGE_AUDIO_VOLUME`    | `str`  | Audio volume for merging. Default: `none`. |

### Merge Image Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MERGE_IMAGE_MODE`      | `str`  | Image merge mode. Default: `none`. |
| `MERGE_IMAGE_COLUMNS`   | `str`  | Image columns for merging. Default: `none`. |
| `MERGE_IMAGE_QUALITY`   | `int`  | Image quality for merging. Default: `0`. |
| `MERGE_IMAGE_DPI`       | `str`  | Image DPI for merging. Default: `none`. |
| `MERGE_IMAGE_RESIZE`    | `str`  | Image resize for merging. Default: `none`. |
| `MERGE_IMAGE_BACKGROUND` | `str` | Image background for merging. Default: `none`. |

### Merge Subtitle Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MERGE_SUBTITLE_ENCODING` | `str` | Subtitle encoding for merging. Default: `none`. |
| `MERGE_SUBTITLE_FONT`   | `str`  | Subtitle font for merging. Default: `none`. |
| `MERGE_SUBTITLE_FONT_SIZE` | `str` | Subtitle font size for merging. Default: `none`. |
| `MERGE_SUBTITLE_FONT_COLOR` | `str` | Subtitle font color for merging. Default: `none`. |
| `MERGE_SUBTITLE_BACKGROUND` | `str` | Subtitle background for merging. Default: `none`. |

### Merge Document Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MERGE_DOCUMENT_PAPER_SIZE` | `str` | Document paper size for merging. Default: `none`. |
| `MERGE_DOCUMENT_ORIENTATION` | `str` | Document orientation for merging. Default: `none`. |
| `MERGE_DOCUMENT_MARGIN` | `str`  | Document margin for merging. Default: `none`. |

### Merge Metadata Settings
| Variable                | Type   | Description |
|-------------------------|--------|-------------|
| `MERGE_METADATA_TITLE`  | `str`  | Metadata title for merged files. Default: `none`. |
| `MERGE_METADATA_AUTHOR` | `str`  | Metadata author for merged files. Default: `none`. |
| `MERGE_METADATA_COMMENT` | `str` | Metadata comment for merged files. Default: `none`. |

## 20. AI Integration

| Variable          | Type   | Description |
|-------------------|--------|-------------|
| `AI_ENABLED`      | `bool` | Enable/disable AI chat functionality. Default: `False`. |
| `AI_PROVIDER`     | `str`  | AI provider to use. Options: `mistral,deepseek,custom`. |
| `AI_API_KEY`      | `str`  | API key for the AI provider. |
| `AI_API_URL`      | `str`  | Custom API URL for AI provider (if using custom). |
| `AI_MODEL`        | `str`  | AI model to use for responses. |
| `AI_MAX_TOKENS`   | `int`  | Maximum tokens per AI response. Default: `1000`. |

## 21. Security Tools

| Variable              | Type   | Description |
|-----------------------|--------|-------------|
| `VIRUSTOTAL_API_KEY`  | `str`  | VirusTotal API key for malware scanning. |
| `TRUECALLER_API_KEY`  | `str`  | Truecaller API key for phone number lookup. |
| `SECURITY_SCAN_AUTO`  | `bool` | Automatically scan downloaded files. Default: `False`. |

## 22. Font Styles

| Variable              | Type   | Description |
|-----------------------|--------|-------------|
| `DEFAULT_FONT_STYLE`  | `str`  | Default font style for leech captions. |
| `FONT_STYLES_ENABLED` | `bool` | Enable/disable font styling functionality. Default: `True`. |
| `CUSTOM_FONTS`        | `dict` | Custom font definitions as JSON dict. |

## 23. Limits and Monitoring

### Storage and Download Limits
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `STORAGE_THRESHOLD`    | `float` | Storage threshold in GB. Default: `0` (no limit). |
| `TORRENT_LIMIT`        | `float` | Torrent download limit in GB. Default: `0` (no limit). |
| `DIRECT_LIMIT`         | `float` | Direct download limit in GB. Default: `0` (no limit). |
| `YTDLP_LIMIT`          | `float` | YT-DLP download limit in GB. Default: `0` (no limit). |
| `GDRIVE_LIMIT`         | `float` | Google Drive operation limit in GB. Default: `0` (no limit). |
| `CLONE_LIMIT`          | `float` | Clone operation limit in GB. Default: `0` (no limit). |
| `MEGA_LIMIT`           | `float` | MEGA download limit in GB. Default: `0` (no limit). |
| `LEECH_LIMIT`          | `float` | Leech operation limit in GB. Default: `0` (no limit). |
| `JD_LIMIT`             | `float` | JDownloader limit in GB. Default: `0` (no limit). |
| `NZB_LIMIT`            | `float` | NZB download limit in GB. Default: `0` (no limit). |
| `PLAYLIST_LIMIT`       | `int`  | Maximum number of videos in playlist. Default: `0` (no limit). |

### Daily Limits
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `DAILY_TASK_LIMIT`     | `int`  | Number of tasks per day per user. Default: `0` (no limit). |
| `DAILY_MIRROR_LIMIT`   | `float` | GB per day for mirror operations. Default: `0` (no limit). |
| `DAILY_LEECH_LIMIT`    | `float` | GB per day for leech operations. Default: `0` (no limit). |

### User and Bot Limits
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `USER_MAX_TASKS`       | `int`  | Maximum concurrent tasks per user. Default: `0` (no limit). |
| `USER_TIME_INTERVAL`   | `int`  | Seconds between tasks for users. Default: `0` (no limit). |
| `BOT_MAX_TASKS`        | `int`  | Maximum concurrent tasks the bot can handle. Default: `0` (no limit). |
| `STATUS_LIMIT`         | `int`  | Number of tasks to display in status message. Default: `10`. |
| `SEARCH_LIMIT`         | `int`  | Maximum number of search results to display. Default: `0` (no limit). |
| `SHOW_CLOUD_LINK`      | `bool` | Show cloud links in upload completion message. Default: `True`. |

### Task Monitoring
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `TASK_MONITOR_ENABLED` | `bool` | Enable task monitoring system. Default: `False`. |
| `TASK_MONITOR_INTERVAL` | `int` | Monitoring interval in seconds. Default: `120`. |
| `TASK_MONITOR_CONSECUTIVE_CHECKS` | `int` | Consecutive checks before action. Default: `10`. |
| `TASK_MONITOR_SPEED_THRESHOLD` | `int` | Speed threshold in KB/s. Default: `50`. |
| `TASK_MONITOR_ELAPSED_THRESHOLD` | `int` | Elapsed time threshold in seconds. Default: `3600`. |
| `TASK_MONITOR_ETA_THRESHOLD` | `int` | ETA threshold in seconds. Default: `86400`. |
| `TASK_MONITOR_WAIT_TIME` | `int` | Wait time in seconds. Default: `900`. |
| `TASK_MONITOR_COMPLETION_THRESHOLD` | `int` | Completion threshold in seconds. Default: `86400`. |
| `TASK_MONITOR_CPU_HIGH` | `int` | High CPU usage percentage. Default: `85`. |
| `TASK_MONITOR_CPU_LOW` | `int` | Low CPU usage percentage. Default: `50`. |
| `TASK_MONITOR_MEMORY_HIGH` | `int` | High memory usage percentage. Default: `70`. |
| `TASK_MONITOR_MEMORY_LOW` | `int` | Low memory usage percentage. Default: `50`. |

### Auto Restart Settings
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `AUTO_RESTART_ENABLED` | `bool` | Enable automatic restart functionality. Default: `False`. |
| `AUTO_RESTART_INTERVAL` | `int` | Auto restart interval in hours. Default: `48`. |

## 24. Feature Toggles

### Core Features
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `AI_ENABLED`           | `bool` | Enable AI functionality. Default: `True`. |
| `IMDB_ENABLED`         | `bool` | Enable IMDB functionality. Default: `True`. |
| `TRUECALLER_ENABLED`   | `bool` | Enable Truecaller functionality. Default: `True`. |
| `MULTI_LINK_ENABLED`   | `bool` | Enable multi-link download support. Default: `True`. |
| `SAME_DIR_ENABLED`     | `bool` | Enable same directory functionality. Default: `True`. |
| `MIRROR_ENABLED`       | `bool` | Enable mirror functionality. Default: `True`. |
| `LEECH_ENABLED`        | `bool` | Enable leech functionality. Default: `True`. |
| `YTDLP_ENABLED`        | `bool` | Enable YT-DLP functionality. Default: `True`. |
| `TORRENT_ENABLED`      | `bool` | Enable torrent functionality. Default: `True`. |
| `TORRENT_SEARCH_ENABLED` | `bool` | Enable torrent search functionality. Default: `True`. |
| `NZB_ENABLED`          | `bool` | Enable NZB functionality. Default: `True`. |
| `NZB_SEARCH_ENABLED`   | `bool` | Enable NZB search functionality. Default: `True`. |
| `JD_ENABLED`           | `bool` | Enable JDownloader functionality. Default: `True`. |
| `HYPERDL_ENABLED`      | `bool` | Enable Hyper Download functionality. Default: `True`. |
| `MEDIA_SEARCH_ENABLED` | `bool` | Enable media search functionality. Default: `True`. |
| `RCLONE_ENABLED`       | `bool` | Enable Rclone functionality. Default: `True`. |
| `ARCHIVE_FLAGS_ENABLED` | `bool` | Enable archive operation flags. Default: `True`. |
| `BULK_ENABLED`         | `bool` | Enable bulk operations (-b flag). Default: `True`. |

## 25. AI and External Services

### AI Configuration
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `DEFAULT_AI_PROVIDER`  | `str`  | Default AI provider (mistral, deepseek). Default: `mistral`. |
| `MISTRAL_API_URL`      | `str`  | Mistral AI API URL. |
| `DEEPSEEK_API_URL`     | `str`  | DeepSeek AI API URL. |

### Security Tools
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `VT_API_KEY`           | `str`  | VirusTotal API key for malware scanning. |
| `VT_API_TIMEOUT`       | `int`  | VirusTotal API timeout in seconds. Default: `500`. |
| `VT_ENABLED`           | `bool` | Enable VirusTotal functionality. Default: `False`. |
| `VT_MAX_FILE_SIZE`     | `int`  | Maximum file size for VirusTotal scanning in bytes. Default: `33554432` (32MB). |
| `TRUECALLER_API_URL`   | `str`  | Truecaller API URL for phone number lookup. |

### Command Management
| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `CORRECT_CMD_SUFFIX`   | `str`  | Comma-separated list of allowed command suffixes. |
| `WRONG_CMD_WARNINGS_ENABLED` | `bool` | Enable/disable warnings for wrong command suffixes. Default: `False`. |

## 26. Extra fields from Aeon

| Variable               | Type   | Description |
|------------------------|--------|-------------|
| `WATERMARK_KEY`        | `str`  | Key used for watermarking files or content. |
| `SET_COMMANDS`         | `bool` | Whether to register bot commands on startup. Default: `True`. |
| `TOKEN_TIMEOUT`        | `int`  | Timeout in seconds for token/session expiry. Default: `0`. |
| `PAID_CHANNEL_ID`      | `int`  | Telegram channel ID where user need to join for no token. Default: `0`. |
| `PAID_CHANNEL_LINK`    | `str`  | Invite or public link to the paid Telegram channel. |
| `DELETE_LINKS`         | `bool` | Whether to auto-delete download or share links. Default: `False`. |
| `FSUB_IDS`             | `str`  | Comma-separated IDs of forced subscription channels. |
| `LOG_CHAT_ID`          | `int`  | Chat ID where leech logs sent. Default: `0`. |
| `LEECH_FILENAME_CAPTION` | `str` | Template caption used for leeched/downloaded filenames. |
| `INSTADL_API`          | `str`  | URL or endpoint for InstaDL API integration. |
| `HEROKU_APP_NAME`      | `str`  | Name of the Heroku app for get `BASE_URL` automatically. |
| `HEROKU_API_KEY`       | `str`  | API key for accessing and controlling Heroku. |
| `LOGIN_PASS`           | `str`  | Password for web login authentication. |
| `AD_KEYWORDS`          | `str`  | Custom keywords/phrases for ad detection, separated by comma. |
| `AD_BROADCASTER_ENABLED` | `bool` | Enable/disable automatic ad broadcasting from FSUB channels to users. Default: `False`. |
| `CREDIT`               | `str`  | Credit text shown in status messages and RSS feeds. Default: `Powered by @aimmirror`. |
| `OWNER_THUMB`          | `str`  | Default thumbnail URL for owner. Default: `https://graph.org/file/80b7fb095063a18f9e232.jpg`. |
| `PIL_MEMORY_LIMIT`     | `int`  | PIL memory limit in MB. Default: `2048`. |
| `MEDIA_SEARCH_CHATS`   | `list` | List of chat IDs for media search functionality. |
| `MEDIA_STORE`          | `bool` | Enable media storage functionality. Default: `False`. |
| `SHORTENER_MIN_TIME`   | `int`  | Minimum time in seconds for shortener to process. Default: `10`. |
| `QUICKINFO_ENABLED`    | `bool` | Enable/disable QuickInfo feature. Default: `False`. |

| `GC_ENABLED`           | `bool` | Enable/disable garbage collection completely. Default: `True`. |
| `GC_INTERVAL`          | `int`  | Minimum interval between GC operations in seconds. Default: `60`. |
| `GC_THRESHOLD_MB`      | `int`  | Memory threshold in MB to trigger GC. Default: `150`. |
| `GC_AGGRESSIVE_MODE`   | `bool` | Enable aggressive GC mode. Default: `False`. |
| `TERABOX_PROXY`        | `str`  | Terabox proxy URL for bypassing restrictions. Default: `https://wdzone-terabox-api.vercel.app/`. |
| `UNIVERSAL_FILENAME`   | `str`  | Universal filename template for both mirror and leech files. |
| `EQUAL_SPLITS`         | `bool` | Create equal-sized parts when splitting files. Default: `False`. |
| `STREAMTAPE_ALLOWED_EXTENSIONS` | `list` | Allowed video extensions for Streamtape uploads. |

## 27. Debrid Services Integration

### Debrid-Link Authentication Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `DEBRID_LINK_API`           | `str`  | Legacy API key or OAuth2 access_token for Debrid-Link. |
| `DEBRID_LINK_ACCESS_TOKEN`  | `str`  | OAuth2 access_token (recommended) for Debrid-Link. |
| `DEBRID_LINK_REFRESH_TOKEN` | `str`  | OAuth2 refresh_token for token renewal. |
| `DEBRID_LINK_CLIENT_ID`     | `str`  | OAuth2 client_id from Debrid-Link app. |
| `DEBRID_LINK_CLIENT_SECRET` | `str`  | OAuth2 client_secret (keep secure). |
| `DEBRID_LINK_TOKEN_EXPIRES` | `int`  | Token expiration timestamp. Default: `0`. |

### TorBox API Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TORBOX_API_KEY`            | `str`  | TorBox API key for premium downloads. |

## 28. Media Tools - Advanced Processing

### Compression Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `COMPRESSION_ENABLED`       | `bool` | Enable compression functionality. Default: `False`. |
| `COMPRESSION_PRIORITY`      | `int`  | Compression task priority. Default: `4`. |
| `COMPRESSION_DELETE_ORIGINAL` | `bool` | Delete original files after compression. Default: `True`. |

### Video Compression Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `COMPRESSION_VIDEO_ENABLED` | `bool` | Enable video compression. Default: `False`. |
| `COMPRESSION_VIDEO_CODEC`   | `str`  | Video codec for compression. Default: `libx264`. |
| `COMPRESSION_VIDEO_PRESET`  | `str`  | Video encoding preset. Default: `medium`. |
| `COMPRESSION_VIDEO_CRF`     | `int`  | Constant Rate Factor for video quality. Default: `23`. |
| `COMPRESSION_VIDEO_BITRATE` | `str`  | Video bitrate for compression. Default: `none`. |
| `COMPRESSION_VIDEO_RESOLUTION` | `str` | Target resolution for video compression. Default: `none`. |
| `COMPRESSION_VIDEO_FPS`     | `str`  | Target frame rate for video compression. Default: `none`. |

### Audio Compression Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `COMPRESSION_AUDIO_ENABLED` | `bool` | Enable audio compression. Default: `False`. |
| `COMPRESSION_AUDIO_CODEC`   | `str`  | Audio codec for compression. Default: `aac`. |
| `COMPRESSION_AUDIO_BITRATE` | `str`  | Audio bitrate for compression. Default: `128k`. |
| `COMPRESSION_AUDIO_QUALITY` | `str`  | Audio quality setting. Default: `none`. |
| `COMPRESSION_AUDIO_CHANNELS` | `str` | Audio channel configuration. Default: `none`. |
| `COMPRESSION_AUDIO_SAMPLE_RATE` | `str` | Audio sample rate. Default: `none`. |

### Image Compression Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `COMPRESSION_IMAGE_ENABLED` | `bool` | Enable image compression. Default: `False`. |
| `COMPRESSION_IMAGE_QUALITY` | `int`  | Image compression quality (1-100). Default: `85`. |
| `COMPRESSION_IMAGE_FORMAT`  | `str`  | Output format for image compression. Default: `none`. |
| `COMPRESSION_IMAGE_RESIZE`  | `str`  | Resize dimensions for images. Default: `none`. |

### Archive Compression Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `COMPRESSION_ARCHIVE_ENABLED` | `bool` | Enable archive compression. Default: `False`. |
| `COMPRESSION_ARCHIVE_LEVEL` | `int`  | Compression level (0-9). Default: `6`. |
| `COMPRESSION_ARCHIVE_PASSWORD` | `str` | Password for archive protection. Default: `none`. |
| `COMPRESSION_ARCHIVE_ALGORITHM` | `str` | Archive algorithm (e.g., 7z, zip). Default: `none`. |

## 29. Trim Settings

### Basic Trim Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TRIM_ENABLED`              | `bool` | Enable trim functionality. Default: `False`. |
| `TRIM_PRIORITY`             | `int`  | Trim task priority. Default: `5`. |
| `TRIM_START_TIME`           | `str`  | Start time for trimming. Default: `00:00:00`. |
| `TRIM_END_TIME`             | `str`  | End time for trimming. Default: `""`. |
| `TRIM_DELETE_ORIGINAL`      | `bool` | Delete original files after trimming. Default: `False`. |

### Video Trim Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TRIM_VIDEO_ENABLED`        | `bool` | Enable video trimming. Default: `False`. |
| `TRIM_VIDEO_CODEC`          | `str`  | Video codec for trimming. Default: `none`. |
| `TRIM_VIDEO_PRESET`         | `str`  | Video encoding preset. Default: `none`. |
| `TRIM_VIDEO_FORMAT`         | `str`  | Output format for video trimming. Default: `none`. |
| `TRIM_VIDEO_QUALITY`        | `str`  | Video quality setting. Default: `none`. |
| `TRIM_VIDEO_BITRATE`        | `str`  | Video bitrate for trimming. Default: `none`. |
| `TRIM_VIDEO_RESOLUTION`     | `str`  | Video resolution for trimming. Default: `none`. |
| `TRIM_VIDEO_FPS`            | `str`  | Video frame rate for trimming. Default: `none`. |

### Audio Trim Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TRIM_AUDIO_ENABLED`        | `bool` | Enable audio trimming. Default: `False`. |
| `TRIM_AUDIO_CODEC`          | `str`  | Audio codec for trimming. Default: `none`. |
| `TRIM_AUDIO_BITRATE`        | `str`  | Audio bitrate for trimming. Default: `none`. |
| `TRIM_AUDIO_QUALITY`        | `str`  | Audio quality setting. Default: `none`. |
| `TRIM_AUDIO_CHANNELS`       | `str`  | Audio channel configuration. Default: `none`. |
| `TRIM_AUDIO_SAMPLE_RATE`    | `str`  | Audio sample rate. Default: `none`. |

### Image Trim Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TRIM_IMAGE_ENABLED`        | `bool` | Enable image trimming. Default: `False`. |
| `TRIM_IMAGE_QUALITY`        | `int`  | Image quality for trimming. Default: `90`. |
| `TRIM_IMAGE_FORMAT`         | `str`  | Output format for image trimming. Default: `none`. |

### Document Trim Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TRIM_DOCUMENT_ENABLED`     | `bool` | Enable document trimming. Default: `False`. |
| `TRIM_DOCUMENT_QUALITY`     | `int`  | Document quality for trimming. Default: `90`. |
| `TRIM_DOCUMENT_FORMAT`      | `str`  | Output format for document trimming. Default: `none`. |

### Subtitle Trim Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TRIM_SUBTITLE_ENABLED`     | `bool` | Enable subtitle trimming. Default: `False`. |
| `TRIM_SUBTITLE_ENCODING`    | `str`  | Subtitle encoding for trimming. Default: `none`. |
| `TRIM_SUBTITLE_FORMAT`      | `str`  | Output format for subtitle trimming. Default: `none`. |

### Archive Trim Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `TRIM_ARCHIVE_ENABLED`      | `bool` | Enable archive trimming. Default: `False`. |
| `TRIM_ARCHIVE_FORMAT`       | `str`  | Output format for archive trimming. Default: `none`. |

## 30. Extract Settings

### Basic Extract Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `EXTRACT_ENABLED`           | `bool` | Enable extract functionality. Default: `False`. |
| `EXTRACT_PRIORITY`          | `int`  | Extract task priority. Default: `6`. |
| `EXTRACT_DELETE_ORIGINAL`   | `bool` | Delete original files after extraction. Default: `True`. |
| `EXTRACT_MAINTAIN_QUALITY`  | `bool` | Maintain quality during extraction. Default: `True`. |

### Video Extract Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `EXTRACT_VIDEO_ENABLED`     | `bool` | Enable video extraction. Default: `False`. |
| `EXTRACT_VIDEO_CODEC`       | `str`  | Video codec for extraction. Default: `none`. |
| `EXTRACT_VIDEO_FORMAT`      | `str`  | Output format for video extraction. Default: `none`. |
| `EXTRACT_VIDEO_INDEX`       | `int`  | Video track index to extract. Default: `None`. |
| `EXTRACT_VIDEO_QUALITY`     | `str`  | Quality setting for video extraction. Default: `none`. |
| `EXTRACT_VIDEO_PRESET`      | `str`  | Preset for video encoding. Default: `none`. |
| `EXTRACT_VIDEO_BITRATE`     | `str`  | Bitrate for video encoding. Default: `none`. |
| `EXTRACT_VIDEO_RESOLUTION`  | `str`  | Resolution for video extraction. Default: `none`. |
| `EXTRACT_VIDEO_FPS`         | `str`  | Frame rate for video extraction. Default: `none`. |

### Audio Extract Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `EXTRACT_AUDIO_ENABLED`     | `bool` | Enable audio extraction. Default: `False`. |
| `EXTRACT_AUDIO_CODEC`       | `str`  | Audio codec for extraction. Default: `none`. |
| `EXTRACT_AUDIO_FORMAT`      | `str`  | Output format for audio extraction. Default: `none`. |
| `EXTRACT_AUDIO_INDEX`       | `int`  | Audio track index to extract. Default: `None`. |
| `EXTRACT_AUDIO_BITRATE`     | `str`  | Audio bitrate for extraction. Default: `none`. |
| `EXTRACT_AUDIO_CHANNELS`    | `str`  | Audio channel configuration. Default: `none`. |
| `EXTRACT_AUDIO_SAMPLING`    | `str`  | Audio sampling rate. Default: `none`. |

### Subtitle Extract Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `EXTRACT_SUBTITLE_ENABLED`  | `bool` | Enable subtitle extraction. Default: `False`. |
| `EXTRACT_SUBTITLE_INDEX`    | `int`  | Subtitle track index to extract. Default: `None`. |
| `EXTRACT_SUBTITLE_FORMAT`   | `str`  | Output format for subtitle extraction. Default: `none`. |
| `EXTRACT_SUBTITLE_ENCODING` | `str`  | Subtitle encoding. Default: `none`. |

### Attachment Extract Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `EXTRACT_ATTACHMENT_ENABLED` | `bool` | Enable attachment extraction. Default: `False`. |
| `EXTRACT_ATTACHMENT_INDEX`  | `int`  | Attachment index to extract. Default: `None`. |
| `EXTRACT_ATTACHMENT_FORMAT` | `str`  | Output format for attachment extraction. Default: `none`. |

## 31. Remove Settings

### Basic Remove Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `REMOVE_ENABLED`            | `bool` | Enable remove functionality. Default: `False`. |
| `REMOVE_PRIORITY`           | `int`  | Remove task priority. Default: `8`. |
| `REMOVE_DELETE_ORIGINAL`    | `bool` | Delete original files after removal. Default: `True`. |
| `REMOVE_METADATA`           | `bool` | Remove metadata during processing. Default: `False`. |
| `REMOVE_MAINTAIN_QUALITY`   | `bool` | Maintain quality during removal. Default: `True`. |

### Video Remove Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `REMOVE_VIDEO_ENABLED`      | `bool` | Enable video track removal. Default: `False`. |
| `REMOVE_VIDEO_CODEC`        | `str`  | Video codec for removal processing. Default: `none`. |
| `REMOVE_VIDEO_FORMAT`       | `str`  | Output format after video removal. Default: `none`. |
| `REMOVE_VIDEO_INDEX`        | `int`  | Video track index to remove. Default: `None`. |
| `REMOVE_VIDEO_QUALITY`      | `str`  | Video quality setting. Default: `none`. |
| `REMOVE_VIDEO_PRESET`       | `str`  | Video encoding preset. Default: `none`. |
| `REMOVE_VIDEO_BITRATE`      | `str`  | Video bitrate setting. Default: `none`. |
| `REMOVE_VIDEO_RESOLUTION`   | `str`  | Video resolution setting. Default: `none`. |
| `REMOVE_VIDEO_FPS`          | `str`  | Video frame rate setting. Default: `none`. |

### Audio Remove Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `REMOVE_AUDIO_ENABLED`      | `bool` | Enable audio track removal. Default: `False`. |
| `REMOVE_AUDIO_CODEC`        | `str`  | Audio codec for removal processing. Default: `none`. |
| `REMOVE_AUDIO_FORMAT`       | `str`  | Output format after audio removal. Default: `none`. |
| `REMOVE_AUDIO_INDEX`        | `int`  | Audio track index to remove. Default: `None`. |
| `REMOVE_AUDIO_BITRATE`      | `str`  | Audio bitrate setting. Default: `none`. |
| `REMOVE_AUDIO_CHANNELS`     | `str`  | Audio channel configuration. Default: `none`. |
| `REMOVE_AUDIO_SAMPLING`     | `str`  | Audio sampling rate setting. Default: `none`. |

### Subtitle Remove Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `REMOVE_SUBTITLE_ENABLED`   | `bool` | Enable subtitle track removal. Default: `False`. |
| `REMOVE_SUBTITLE_INDEX`     | `int`  | Subtitle track index to remove. Default: `None`. |
| `REMOVE_SUBTITLE_FORMAT`    | `str`  | Output format after subtitle removal. Default: `none`. |
| `REMOVE_SUBTITLE_ENCODING`  | `str`  | Subtitle encoding setting. Default: `none`. |

### Attachment Remove Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `REMOVE_ATTACHMENT_ENABLED` | `bool` | Enable attachment removal. Default: `False`. |
| `REMOVE_ATTACHMENT_FORMAT`  | `str`  | Output format after attachment removal. Default: `none`. |
| `REMOVE_ATTACHMENT_INDEX`   | `int`  | Attachment index to remove. Default: `None`. |
| `REMOVE_ATTACHMENT_FILTER`  | `str`  | Filter for attachment removal. Default: `none`. |



## 32. Swap Settings

### Basic Swap Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `SWAP_ENABLED`              | `bool` | Enable swap functionality. Default: `False`. |
| `SWAP_PRIORITY`             | `int`  | Swap task priority. Default: `6`. |
| `SWAP_REMOVE_ORIGINAL`      | `bool` | Remove original files after swapping. Default: `False`. |

### Audio Swap Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `SWAP_AUDIO_ENABLED`        | `bool` | Enable audio track swapping. Default: `False`. |
| `SWAP_AUDIO_USE_LANGUAGE`   | `bool` | Use language for audio track selection. Default: `True`. |
| `SWAP_AUDIO_LANGUAGE_ORDER` | `str`  | Language order for audio track selection. Default: `eng,hin`. |
| `SWAP_AUDIO_INDEX_ORDER`    | `str`  | Index order for audio track selection. Default: `0,1`. |

### Video Swap Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `SWAP_VIDEO_ENABLED`        | `bool` | Enable video track swapping. Default: `False`. |
| `SWAP_VIDEO_USE_LANGUAGE`   | `bool` | Use language for video track selection. Default: `True`. |
| `SWAP_VIDEO_LANGUAGE_ORDER` | `str`  | Language order for video track selection. Default: `eng,hin`. |
| `SWAP_VIDEO_INDEX_ORDER`    | `str`  | Index order for video track selection. Default: `0,1`. |

### Subtitle Swap Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `SWAP_SUBTITLE_ENABLED`     | `bool` | Enable subtitle track swapping. Default: `False`. |
| `SWAP_SUBTITLE_USE_LANGUAGE` | `bool` | Use language for subtitle track selection. Default: `True`. |
| `SWAP_SUBTITLE_LANGUAGE_ORDER` | `str` | Language order for subtitle track selection. Default: `eng,hin`. |
| `SWAP_SUBTITLE_INDEX_ORDER` | `str`  | Index order for subtitle track selection. Default: `0,1`. |

## 33. Convert Settings

### Basic Convert Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `CONVERT_ENABLED`           | `bool` | Enable convert functionality. Default: `False`. |
| `CONVERT_PRIORITY`          | `int`  | Convert task priority. Default: `3`. |
| `CONVERT_DELETE_ORIGINAL`   | `bool` | Delete original files after conversion. Default: `True`. |

### Video Convert Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `CONVERT_VIDEO_ENABLED`     | `bool` | Enable video conversion. Default: `False`. |
| `CONVERT_VIDEO_CODEC`       | `str`  | Video codec for conversion. Default: `libx264`. |
| `CONVERT_VIDEO_FORMAT`      | `str`  | Output format for video conversion. Default: `mp4`. |
| `CONVERT_VIDEO_PRESET`      | `str`  | Video encoding preset. Default: `medium`. |
| `CONVERT_VIDEO_CRF`         | `int`  | Constant Rate Factor for video quality. Default: `23`. |
| `CONVERT_VIDEO_BITRATE`     | `str`  | Video bitrate for conversion. Default: `none`. |
| `CONVERT_VIDEO_RESOLUTION`  | `str`  | Video resolution for conversion. Default: `none`. |
| `CONVERT_VIDEO_FPS`         | `str`  | Video frame rate for conversion. Default: `none`. |

### Audio Convert Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `CONVERT_AUDIO_ENABLED`     | `bool` | Enable audio conversion. Default: `False`. |
| `CONVERT_AUDIO_CODEC`       | `str`  | Audio codec for conversion. Default: `aac`. |
| `CONVERT_AUDIO_FORMAT`      | `str`  | Output format for audio conversion. Default: `mp3`. |
| `CONVERT_AUDIO_BITRATE`     | `str`  | Audio bitrate for conversion. Default: `128k`. |
| `CONVERT_AUDIO_QUALITY`     | `str`  | Audio quality setting. Default: `none`. |
| `CONVERT_AUDIO_CHANNELS`    | `str`  | Audio channel configuration. Default: `none`. |
| `CONVERT_AUDIO_SAMPLE_RATE` | `str`  | Audio sample rate for conversion. Default: `none`. |

### Image Convert Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `CONVERT_IMAGE_ENABLED`     | `bool` | Enable image conversion. Default: `False`. |
| `CONVERT_IMAGE_FORMAT`      | `str`  | Output format for image conversion. Default: `jpg`. |
| `CONVERT_IMAGE_QUALITY`     | `int`  | Image quality for conversion (1-100). Default: `90`. |
| `CONVERT_IMAGE_RESIZE`      | `str`  | Resize dimensions for images. Default: `none`. |

### Document Convert Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `CONVERT_DOCUMENT_ENABLED`  | `bool` | Enable document conversion. Default: `False`. |
| `CONVERT_DOCUMENT_FORMAT`   | `str`  | Output format for document conversion. Default: `pdf`. |
| `CONVERT_DOCUMENT_QUALITY`  | `int`  | Document quality for conversion. Default: `90`. |

## 34. System Performance Settings

### Garbage Collection Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `GC_ENABLED`                | `bool` | Enable/disable garbage collection completely. Default: `True`. |
| `GC_INTERVAL`               | `int`  | Minimum interval between GC operations in seconds. Default: `60`. |
| `GC_THRESHOLD_MB`           | `int`  | Memory threshold in MB to trigger GC. Default: `150`. |
| `GC_AGGRESSIVE_MODE`        | `bool` | Enable aggressive GC mode. Default: `False`. |



### Bulk Operation Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `BULK_ENABLED`              | `bool` | Enable/disable bulk operations (-b flag). Default: `True`. |

## 35. AI and Extra Modules

### AI Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `AI_ENABLED`                | `bool` | Enable/disable AI functionality. Default: `True`. |
| `DEFAULT_AI_PROVIDER`       | `str`  | Default AI provider (mistral, deepseek). Default: `mistral`. |
| `MISTRAL_API_URL`           | `str`  | Mistral AI API URL. |
| `DEEPSEEK_API_URL`          | `str`  | DeepSeek AI API URL. |

### Extra Module Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `IMDB_ENABLED`              | `bool` | Enable/disable IMDB functionality. Default: `True`. |
| `TRUECALLER_ENABLED`        | `bool` | Enable/disable Truecaller functionality. Default: `True`. |
| `ENCODING_ENABLED`          | `bool` | Enable/disable encoding functionality. Default: `True`. |
| `DECODING_ENABLED`          | `bool` | Enable/disable decoding functionality. Default: `True`. |

### VirusTotal Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `VT_API_KEY`                | `str`  | VirusTotal API key for file scanning. |
| `VT_API_TIMEOUT`            | `int`  | VirusTotal API timeout in seconds. Default: `500`. |
| `VT_ENABLED`                | `bool` | Enable/disable VirusTotal functionality. Default: `False`. |
| `VT_MAX_FILE_SIZE`          | `int`  | Maximum file size for VirusTotal scanning in bytes. Default: `33554432` (32MB). |

## 36. Enhanced NSFW Detection

### Basic NSFW Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `NSFW_DETECTION_ENABLED`    | `bool` | Master toggle for NSFW detection. Default: `True`. |
| `NSFW_DETECTION_SENSITIVITY` | `str` | Detection sensitivity: `strict`, `moderate`, `permissive`. Default: `moderate`. |
| `NSFW_CONFIDENCE_THRESHOLD` | `float` | Minimum confidence for NSFW detection (0.0-1.0). Default: `0.7`. |
| `NSFW_CACHE_DURATION`       | `int`  | Cache detection results duration in seconds. Default: `3600`. |
| `NSFW_MAX_FILE_SIZE`        | `int`  | Maximum file size for NSFW analysis in bytes. Default: `52428800` (50MB). |

### NSFW Detection Methods
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `NSFW_KEYWORD_DETECTION`    | `bool` | Enable enhanced keyword detection. Default: `True`. |
| `NSFW_VISUAL_DETECTION`     | `bool` | Enable AI-powered visual analysis. Default: `False`. |
| `NSFW_AUDIO_DETECTION`      | `bool` | Enable audio content analysis. Default: `False`. |
| `NSFW_FUZZY_MATCHING`       | `bool` | Enable fuzzy keyword matching. Default: `False`. |
| `NSFW_LEETSPEAK_DETECTION`  | `bool` | Enable leetspeak detection. Default: `True`. |
| `NSFW_MULTI_LANGUAGE`       | `bool` | Enable multi-language keyword support. Default: `False`. |
| `NSFW_CONTEXT_CHECKING`     | `bool` | Enable context-aware detection. Default: `True`. |

### NSFW Media Analysis
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `NSFW_VIDEO_ANALYSIS`       | `bool` | Enable video frame analysis. Default: `True`. |
| `NSFW_VIDEO_FRAME_COUNT`    | `int`  | Number of frames to extract for analysis. Default: `5`. |
| `NSFW_FRAME_QUALITY`        | `int`  | Frame extraction quality (1-5). Default: `2`. |
| `NSFW_AUDIO_ANALYSIS`       | `bool` | Enable audio content analysis. Default: `True`. |
| `NSFW_SUBTITLE_ANALYSIS`    | `bool` | Enable subtitle text analysis. Default: `True`. |

### NSFW Visual Analysis API Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `NSFW_GOOGLE_VISION_API_KEY` | `str` | Google Cloud Vision API key for visual analysis. |
| `NSFW_AWS_ACCESS_KEY`       | `str`  | AWS Rekognition access key for visual analysis. |
| `NSFW_AWS_SECRET_KEY`       | `str`  | AWS Rekognition secret key for visual analysis. |
| `NSFW_AWS_REGION`           | `str`  | AWS region for Rekognition. Default: `us-east-1`. |
| `NSFW_AZURE_ENDPOINT`       | `str`  | Azure Content Moderator endpoint URL. |
| `NSFW_AZURE_KEY`            | `str`  | Azure Content Moderator API key. |
| `NSFW_OPENAI_API_KEY`       | `str`  | OpenAI API key for vision analysis. |

### NSFW Text Analysis API Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `NSFW_PERSPECTIVE_API_KEY`  | `str`  | Google Perspective API key for text analysis. |
| `NSFW_OPENAI_MODERATION`    | `bool` | Use OpenAI moderation API for text analysis. Default: `False`. |

### NSFW Behavior and Logging
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `NSFW_LOG_DETECTIONS`       | `bool` | Log NSFW detections for analysis. Default: `True`. |
| `NSFW_STORE_METADATA`       | `bool` | Store detection metadata in database. Default: `True`. |
| `NSFW_AUTO_DELETE`          | `bool` | Auto-delete detected NSFW content. Default: `False`. |
| `NSFW_NOTIFY_ADMINS`        | `bool` | Notify admins of NSFW detections. Default: `True`. |

## Weather Settings

### Basic Weather Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `WEATHER_ENABLED`           | `bool` | Enable/disable weather functionality. Default: `True`. |
| `OPENWEATHER_API_KEY`       | `str`  | OpenWeatherMap API key (required for weather features). |
| `WEATHER_PLACE`             | `str`  | Default weather location. Default: `"London,UK"`. |
| `AUTO_WEATHER`              | `bool` | Enable/disable automatic daily weather updates. Default: `True`. |
| `WEATHER_RISK_NOTIFICATIONS` | `bool` | Enable/disable weather risk notifications to owner. Default: `True`. |
| `WEATHER_UNITS`             | `str`  | Units for weather data: `standard`, `metric`, `imperial`. Default: `"metric"`. |
| `WEATHER_LANGUAGE`          | `str`  | Language code for weather descriptions. Default: `"en"`. |
| `WEATHER_UPDATE_TIME`       | `str`  | Time for daily weather updates (HH:MM format). Default: `"08:00"`. |
| `WEATHER_TIMEZONE`          | `str`  | Timezone for weather updates. Default: `"UTC"`. |

### Advanced Weather Features
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `WEATHER_SHOW_MAPS`         | `bool` | Enable/disable weather maps. Default: `True`. |
| `WEATHER_SHOW_AIR_QUALITY`  | `bool` | Enable/disable air quality data. Default: `True`. |
| `WEATHER_SHOW_FIRE_INDEX`   | `bool` | Enable/disable fire weather index (requires special access). Default: `False`. |
| `WEATHER_HISTORICAL_DAYS`   | `int`  | Days of historical data to show (requires paid plan). Default: `7`. |
| `WEATHER_FORECAST_DAYS`     | `int`  | Days of forecast to show (max 5 for free plan). Default: `5`. |
| `WEATHER_MAP_ZOOM`          | `int`  | Default zoom level for weather maps. Default: `10`. |
| `WEATHER_IMAGE_QUALITY`     | `str`  | Image quality: `low`, `medium`, `high`. Default: `"high"`. |
| `WEATHER_CACHE_DURATION`    | `int`  | Cache duration in seconds. Default: `600` (10 minutes). |

### Weather Alert Settings
| Variable                    | Type    | Description |
|-----------------------------|---------|-------------|
| `WEATHER_ALERT_TEMPERATURE_HIGH` | `float` | High temperature alert threshold (Celsius). Default: `35.0`. |
| `WEATHER_ALERT_TEMPERATURE_LOW`  | `float` | Low temperature alert threshold (Celsius). Default: `-10.0`. |
| `WEATHER_ALERT_WIND_SPEED`       | `float` | High wind speed alert threshold (m/s). Default: `15.0`. |
| `WEATHER_ALERT_VISIBILITY`       | `int`   | Low visibility alert threshold (meters). Default: `1000`. |
| `WEATHER_ALERT_AQI`              | `int`   | Air quality alert threshold (1-5 scale). Default: `3`. |
| `WEATHER_ALERT_FIRE_DANGER`      | `int`   | Fire weather index alert threshold (0-5 scale). Default: `3`. |

### Weather Map Settings
| Variable                    | Type    | Description |
|-----------------------------|---------|-------------|
| `WEATHER_MAP_LAYERS`        | `list`  | Available weather map layers. Default: `["temp_new", "precipitation_new", "pressure_new", "wind_new", "clouds_new"]`. |
| `WEATHER_MAP_OPACITY`       | `float` | Map layer opacity (0.0-1.0). Default: `0.6`. |
| `WEATHER_USE_ADVANCED_MAPS` | `bool`  | Use Weather Maps 2.0 (requires paid plan). Default: `False`. |
| `WEATHER_USE_HOURLY_MAPS`   | `bool`  | Use Weather Maps 2.0 with 1-hour step (requires paid plan). Default: `False`. |

### Air Quality Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `WEATHER_AQI_FORECAST_DAYS` | `int`  | Days of air quality forecast (max 4). Default: `4`. |
| `WEATHER_AQI_HISTORICAL_DAYS` | `int` | Days of historical air quality data. Default: `7`. |
| `WEATHER_SHOW_POLLUTANTS`   | `list` | Pollutants to display. Default: `["co", "no", "no2", "o3", "so2", "pm2_5", "pm10", "nh3"]`. |

### Premium Weather Features
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `WEATHER_HOURLY_FORECAST_HOURS` | `int` | Hours of hourly forecast (max 96 for 4 days). Default: `96`. |
| `WEATHER_STATISTICAL_DATA`  | `bool` | Enable statistical weather data (requires paid plan). Default: `False`. |
| `WEATHER_ROAD_RISK_API`     | `bool` | Enable road risk API (requires paid plan). Default: `False`. |
| `WEATHER_SOLAR_IRRADIANCE`  | `bool` | Enable solar irradiance data (requires paid plan). Default: `False`. |

## 38. Link Shortener (Bitly Integration)

### Basic Settings
| Variable                    | Type   | Description |
|-----------------------------|--------|-------------|
| `BITLY_ACCESS_TOKEN`        | `str`  | **REQUIRED**: Bitly API access token for link shortening. Get from [Bitly Developer Portal](https://dev.bitly.com/). |
| `BITLY_GROUP_GUID`          | `str`  | Optional Bitly group GUID for organization and analytics. Get from your Bitly account settings. |

### Features
- **URL Shortening**: Shorten any valid URL using Bitly API
- **Custom Aliases**: Support for custom aliases (alphanumeric, hyphens, underscores)
- **QR Code Generation**: Automatic high-quality PNG QR code generation via Bitly API
- **Reply Support**: Works with replies to messages containing URLs
- **Analytics**: Click tracking through Bitly dashboard
- **Error Handling**: Comprehensive validation and user feedback

### Usage
```bash
# Basic shortening
/shortner https://example.com

# With custom alias
/shortner https://github.com/user/repo my-repo

# Reply to message containing URL
/shortner [custom-alias]
```

### Custom Alias Rules
- Maximum 50 characters
- Alphanumeric characters only (a-z, A-Z, 0-9)
- Hyphens (-) and underscores (_) allowed
- Must be unique across Bitly platform
- Case-sensitive

### Setup Instructions
1. Go to [Bitly Developer Portal](https://dev.bitly.com/)
2. Sign up or log in to your Bitly account
3. Create a new application
4. Generate an access token
5. Copy the access token to `BITLY_ACCESS_TOKEN`
6. (Optional) Get your Group GUID from Bitly settings for `BITLY_GROUP_GUID`

**Note**: The link shortener requires a valid Bitly API access token to function. Without proper configuration, the `/shortner` command will display a configuration error message.






