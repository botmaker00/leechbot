# Features

## QBittorrent

- External access to web UI for file removal or settings adjustment. Sync with database using the sync button in bot settings.
- Select files from a torrent before or during download using the mltb file selector (requires Base URL) (task option).
- Seed torrents to a specific ratio and duration (task option).
- Edit global options during runtime via bot settings (global option).

## Aria2c

- Select torrent files before or during download (requires Base URL) (task option).
- Seed torrents to a specific ratio and duration (task option).
- Netrc authentication support (global option).
- Direct link authentication (even with just a username or password) (task option).
- Edit global options during runtime via bot settings (global option).

## Sabnzbd

- External web interface access for file removal or settings adjustments. Sync with database using the sync button in bot settings.
- Remove files from jobs before or during download using the mltb file selector (requires Base URL) (task option).
- Edit global options during runtime via bot settings (global option).
- Manage Usenet servers (add/edit/remove).

## TG Upload/Download

- Split size settings (global, user, and task option).
- Custom thumbnails (user and task option).
- Leech filename prefix (user option).
- Set upload type: document or media (global, user, and task option).
- Upload to a specific chat (supergroup, channel, private, or topic) (global, user, and task option).
- Equal split size (global and user option).
- Media group support for split file parts (global and user option).
- Download restricted Telegram messages via public/private/supergroup links (task option).
- Choose transfer session (bot or user) for premium accounts (global, user, and task option).
- Hybrid upload using bot and user sessions based on file size (global, user, and task option).
- Upload with custom thumbnail layout (global, user, and task option).
- Topic support.

## Google Drive

- Download, upload, clone, delete, and count files/folders.
- Count files and folders in Drive.
- Search in folders or TeamDrives.
- Use `token.pickle` fallback when no Service Account is available.
- Random Service Account per task.
- Recursive search support with root or TeamDrive ID (task option).
- Prevent duplicates (global and user option).
- Custom upload destinations (global, user, and task option).
- Choose between `token.pickle` or Service Account with button support (global, user, and task option).
- Index link support for [Bhadoo's Index](https://gitlab.com/GoogleDriveIndex/Google-Drive-Index/-/blob/master/src/worker.js).

## Rclone

- Transfer (download/upload/clone server-side) with or without random Service Accounts (global and user option).
- Choose config, remote, and path with or without button support (global, user, and task option).
- Set custom flags per task or globally (global, user, and task option).
- File/folder selection via buttons (task option).
- Use `rclone.conf` (global and user option).
- Serve combined remotes as an index (global option).
- Custom upload destinations (global, user, and task option).

## Status

- View download, upload, extract, archive, seed, and clone statuses.
- Unlimited task status pages (global option).
- Interval-based status updates (global option).
- Navigate with next/previous buttons (global and user option).
- Filter task view by status and type if more than 30 (global and user option).
- Step controls for pagination (global and user option).
- User-specific status (manual refresh only).

## Yt-dlp

- Quality selection buttons (task option).
- Custom `yt-dlp` options (global, user, and task option).
- Netrc support (global option).
- Cookie support (global option).
- Embed original thumbnail in leech.
- Supports all audio formats.

## JDownloader

- Sync settings (global option).
- Wait for file selection/variant changes before download starts.
- DLC file support.
- Edit settings via JDownloader web interface, Android/iOS apps, or browser extensions.

## Mongo Database

- Stores bot and user settings, including thumbnails and private files.
- Stores RSS data and incomplete task messages.
- Stores JDownloader settings.
- Automatically stores and updates `config.py`, using it for variable definitions.

## Torrents Search

- Search torrents via Torrent Search API.
- Use qBittorrent's plugin system for enhanced search.

## Archives

- Extract split archives with/without passwords.
- Zip files/folders with or without passwords and support for splits (leech).
- Uses 7z for extraction (supports all types).

## RSS

- Based on [rss-chan](https://github.com/hyPnOtICDo0g/rss-chan).
- RSS feeds (user option).
- Title filters (feed option).
- Edit feeds live: pause, resume, command and filter edits (feed option).
- Sudo controls for user feeds.
- Fully button-based command execution.

## Streamrip Integration

- Download high-quality music from streaming platforms (Qobuz, Tidal, Deezer, SoundCloud).
- Support for Hi-Res FLAC up to 24-bit/192kHz (Qobuz) and MQA/Hi-Res (Tidal).
- Comprehensive search functionality across all supported platforms.
- Batch download support for albums, playlists, and individual tracks.
- Quality selection with platform-specific options.
- Media tools integration for post-processing.
- Inline search with real-time results and download buttons.
- Service-specific authentication and credential management.
- Custom naming and metadata handling.
- Support for zip compression and custom upload destinations.

## Media Tools

- Comprehensive media processing pipeline with multiple tools.
- Video/audio compression with quality presets (low, medium, high, ultra).
- Format conversion between various audio/video formats.
- Watermark addition (text and image) with positioning options.
- Media merging (video, audio, subtitle, attachment, image, PDF).
- Content extraction (video, audio, subtitle, attachment streams).
- Metadata editing and automatic metadata application.
- Sample video and screenshot generation.
- Archive creation and extraction with password support.
- Trim and cut operations with precise timing.
- Custom FFmpeg command execution.
- Batch processing support for multiple files.

## Font Styles

- Comprehensive text styling system for leech captions.
- Support for HTML formatting (bold, italic, code, underline, strikethrough).
- Unicode font styles with mathematical symbols and special characters.
- Google Fonts integration with weight-based styling conversion.
- Nested styling support with unlimited depth.
- Custom font style templates for different content types.
- User-specific and global font style settings.
- Template variable integration with font styling.
- Blockquote support with expandable attributes.
- Monospace and script font handling.

## Spectrum Generation

- Audio spectrum visualization using FFmpeg and SoX.
- High-quality spectrogram generation with customizable parameters.
- Support for various audio and video formats.
- Automatic format conversion for compatibility.
- Optimized processing for long audio files.
- Rainbow color schemes and logarithmic scaling.
- Batch processing for multiple files.
- Memory-efficient processing for large files.

## AI Integration

- Chat with AI assistants (Mistral, DeepSeek, or custom providers).
- Natural language processing for user queries.
- Configurable AI providers and API endpoints.
- Context-aware responses with conversation history.
- Support for both text and reply-based interactions.
- Rate limiting and usage tracking.
- Error handling and fallback mechanisms.

## Security Tools

- **VirusTotal Integration**: Scan files and URLs for malware detection.
- **Phish Directory**: Check domains and emails for phishing/security threats.
- **WOT (Web of Trust)**: Website reputation and trustworthiness checking.
- **AbuseIPDB Integration**: IP address abuse confidence scoring and threat analysis.
- **Truecaller Lookup**: Phone number information and spam detection.
- Comprehensive threat analysis and reporting.
- Support for multiple file types and URL schemes.
- Detailed scan results with threat classifications.
- Community-driven reputation scoring and safety assessments.
- Comprehensive IP geolocation, ISP information, and abuse history.
- Automatic domain-to-IP resolution for multi-layered security analysis.
- API key management and rate limiting.

## Media Search

- Inline media search across multiple platforms.
- Real-time search results with preview thumbnails.
- Support for movies, TV shows, music, and other media.
- Direct download integration from search results.
- Platform-specific search filters and options.
- Batch selection and download capabilities.
- Search history and favorites management.

## Session Management

- Secure Pyrogram session string generation.
- Support for both bot and user sessions.
- Two-factor authentication handling.
- Session validation and testing.
- Secure credential storage and management.
- Multi-session support for different accounts.

## Broadcast System

- Message broadcasting to all bot users.
- Support for text, media, and document broadcasting.
- Progress tracking with real-time statistics.
- User management with blocked user removal.
- Flood control and rate limiting.
- Broadcast scheduling and automation.
- Target audience filtering and segmentation.

## Paste Service

- Text pasting to external services (katb.in).
- Support for various file formats (txt, log, json, xml, csv, md, py, js, html, css).
- Large file handling with content truncation.
- Automatic content size detection and optimization.
- URL generation with expiration tracking.
- Binary file detection and error handling.

## IMDB Integration

- Movie and TV show information lookup.
- Detailed cast, crew, and production information.
- Rating and review aggregation.
- Plot summaries and genre classification.
- Release date and runtime information.
- Poster and backdrop image retrieval.

## Login System

- Password-based authentication for permanent access.
- Session management with timeout controls.
- User privilege escalation and access control.
- Secure password hashing and validation.
- Multi-user support with individual permissions.
- Login attempt tracking and security monitoring.

## Overall

- Docker support for `amd64`, `arm64/v8`.
- Runtime variable editing and private file overwrite (bot/user).
- Auto-update on startup and restart via `UPSTREAM_REPO`.
- Telegraph integration ([loaderX-bot](https://github.com/SVR666)).
- Reply-based Mirror/Leech/Watch/Clone/Count/Delete.
- Multi-link/file support for mirror/leech/clone in one command.
- Custom names for all links (excluding torrents); extensions required except for yt-dlp (global and user option).
- Exclude file extensions from upload/clone (global and user option).
- View Link button for browser access (instead of direct download).
- Queueing system for all tasks (global option).
- Zip/unzip multiple links into one directory (task option).
- Bulk download from Telegram TXT file or newline-separated links (task option).
- Join previously split files (task option).
- Sample video and screenshot generators (task option).
- Cancel upload/clone/archive/extract/split/queue (task option).
- Cancel specific task statuses using buttons (global option).
- Convert videos/audios to specific format with filter (task option).
- Force-start queue tasks with command/args (task option).
- Shell and executor support.
- Add sudo users.
- Save upload paths.
- Rename files before upload via name substitution.
- Select use of `rclone.conf` or `token.pickle` without `mpt:` or `mrcc:` prefix.
- Execute FFmpeg commands post-download (task option).
- Change Metadata automatically.
- Add watermark text automatically.
- Custom caption format.