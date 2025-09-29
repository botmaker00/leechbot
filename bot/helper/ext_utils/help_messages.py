from bot.core.aeon_client import TgClient
from bot.helper.telegram_helper.bot_commands import BotCommands

# FFmpeg help message with concise and visual format
ffmpeg_help = """<b>Custom FFmpeg Commands</b>: -ff

<blockquote>
<b>Basic Usage:</b>
• <code>/cmd link -ff "-i mltb.video -c:v libx264 mltb.mp4"</code> - Direct command
• <code>/cmd link -ff "preset_name"</code> - Use saved preset
• <code>/cmd link -ff "-i mltb.video -c:v libx264 -del mltb.mp4"</code> - Delete original
</blockquote>

<blockquote expandable="expandable">
<b>Multiple Commands:</b>
Run commands sequentially, using output of one as input for the next.

<b>JSON Array Format:</b> (Recommended)
<code>/cmd link -ff '[
  "-i mltb.video -c:v libx264 output1.mp4",
  "-i mltb -vf scale=640:360 output2.mp4",
  "-i mltb -ss 00:00:01 -vframes 1 thumb.jpg",
  "-i mltb -i tg://openmessage?user_id=5272663208&message_id=322801 -filter_complex 'overlay=W-w-10:H-h-10' -c:a copy mltb"
]'</code>

<b>List Format:</b>
<code>/cmd link -ff [["-i","mltb.video","-c:v","libx264","out.mp4"],["-i","mltb","-vf","scale=640:360","out2.mp4"]]</code>

• <code>mltb</code> in later commands refers to previous output
• For presets: <code>{"process":[["-i","mltb","-c:v","libx264","temp.mp4"],["-i","mltb","-vf","scale=720p","final.mp4"]]}</code>
</blockquote>

<blockquote expandable="expandable">
<b>Input Placeholders:</b>
• <code>mltb</code> or <code>input.mp4</code> - Generic input file
• <code>mltb.video</code> - Video files only
• <code>mltb.audio</code> - Audio files only
• <code>mltb.image</code> - Image files only
• <code>mltb.subtitle</code> - Subtitle files only
• <code>mltb.document</code> - Document files only
• <code>mltb.archive</code> - Archive files only
• <code>mltb.mkv</code> - In multiple commands, refers to previous command's output

These placeholders are automatically replaced with the actual file path.
</blockquote>

<blockquote expandable="expandable">
<b>Multiple Input Support:</b>
• <code>-i mltb.video -i mltb.audio</code> - Use multiple input files
• <code>-i mltb.video -i mltb.audio -map 0:v:0 -map 1:a:0 output.mp4</code> - Video from first, audio from second
• <code>-i mltb.video -i mltb.image -filter_complex "[0:v][1:v]overlay=10:10" output.mp4</code> - Add watermark
• <code>-i mltb.video -i mltb.audio -i mltb.subtitle -map 0:v -map 1:a -map 2:s output.mkv</code> - Combine all
</blockquote>

<blockquote expandable="expandable">
<b>Dynamic Output Naming:</b>
• <code>mltb.mp4</code> - Simple output (adds ffmpeg prefix)
• <code>output.mp4</code> - Custom named output
• <code>mltb-%d.mp4</code> → video-1.mp4, video-2.mp4, etc.
• <code>mltb-%03d.mp4</code> → video-001.mp4, video-002.mp4, etc.

<b>Dynamic Output Examples:</b>
• <code>-i mltb.video -map 0:v -c:v libx264 video-%d.mp4</code> - Extract all video streams
• <code>-i mltb.video -map 0:a -c:a aac audio-%03d.m4a</code> - Extract all audio tracks
• <code>-i mltb.mkv -f segment -segment_time 600 part-%03d.mkv</code> - Split into segments
</blockquote>

<blockquote expandable="expandable">
<b>Common Tasks:</b>

<b>Convert Video Format:</b>
<code>-i mltb.video -c:v libx264 -c:a aac mltb.mp4</code>

<b>Extract Audio:</b>
<code>-i mltb.video -vn -c:a copy mltb.m4a</code>

<b>Extract Subtitles:</b>
<code>-i mltb.video -map 0:s -c:s srt mltb-%d.srt</code>

<b>Compress Video:</b>
<code>-i mltb.video -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k mltb.mp4</code>

<b>Trim Video:</b>
<code>-i mltb.video -ss 00:01:00 -to 00:02:00 -c:v copy -c:a copy mltb.mp4</code>

<b>Create GIF:</b>
<code>-i mltb.video -vf "fps=10,scale=320:-1:flags=lanczos" -c:v gif mltb.gif</code>
</blockquote>

<blockquote expandable="expandable">
<b>Advanced Examples:</b>

<b>Extract Streams:</b> <code>-i mltb.mkv -map 0:v -c:v copy video.mp4 -map 0:a -c:a copy audio.m4a</code>

<b>Add Watermark:</b> <code>-i mltb.video -vf "drawtext=text='@YourChannel':fontcolor=white:fontsize=24:x=10:y=10" mltb.mp4</code>

<b>Speed Up:</b> <code>-i mltb.video -filter_complex "[0:v]setpts=0.5*PTS[v];[0:a]atempo=2.0[a]" -map "[v]" -map "[a]" mltb.mp4</code>

<b>Multi-Step Processing:</b>
<code>/cmd link -ff '[
  "-i mltb.video -c:v libx264 temp.mp4",
  "-i mltb -vf scale=720:480 final.mp4",
  "-i mltb -ss 00:00:01 -vframes 1 thumb.jpg"
]'</code>
</blockquote>

<blockquote expandable="expandable">
<b>Preset Management:</b>

<b>Using Presets:</b>
• Use <code>/cmd link -ff "preset_name"</code> to apply a preset
• Configure in User Settings > FFMPEG_CMDS

<b>Creating Presets:</b>
• Single command: <code>{"compress": ["-i mltb.video -c:v libx264 mltb.mp4"]}</code>
• Multiple commands: <code>{"process": [
  ["-i mltb.video -c:v libx264 temp.mp4"],
  ["-i mltb -vf scale=720:480 final.mp4"]
]}</code>
• Variables: Use <code>{variable}</code> for customizable values
</blockquote>

<blockquote expandable="expandable">
<b>Tips & Tricks:</b>

• Use <code>-c:v copy -c:a copy</code> for fastest processing (no re-encoding)
• Add <code>-del</code> to delete original files after processing
• For bulk downloads, commands apply to each file individually
• For complex commands, test on small files first
• In multiple commands, use <code>mltb</code> to reference the previous command's output
• JSON array format is more readable for complex command sequences
• You can add telegram link for small size input like photo to set watermark
</blockquote>"""

# Legacy nsfw_keywords removed - now using enhanced detection system in nsfw_detection.py

# Enhanced NSFW Detection Help
nsfw_detection_help = """
🛡️ <b>Enhanced NSFW Detection System</b>

The bot now features an advanced NSFW detection system with multiple layers of protection:

<b>🔍 Detection Methods:</b>
• <b>Enhanced Keywords:</b> Fuzzy matching, leetspeak detection, multi-language support
• <b>AI Visual Analysis:</b> Computer vision APIs for image content and smart video frame extraction
• <b>Audio Content Analysis:</b> Metadata extraction and text analysis from audio files
• <b>Subtitle Text Analysis:</b> Full text extraction and analysis from subtitle files
• <b>NLP Text Analysis:</b> Advanced text analysis using AI APIs
• <b>Behavioral Tracking:</b> User behavior pattern analysis
• <b>Confidence Scoring:</b> Probabilistic detection with adjustable thresholds

<b>⚙️ Configuration Levels:</b>
• <b>Strict:</b> Very sensitive, catches more content (threshold: 0.3)
• <b>Moderate:</b> Balanced approach (threshold: 0.7) - Default
• <b>Permissive:</b> Only obvious NSFW content (threshold: 0.9)

<b>🎯 Features:</b>
• Real-time content analysis
• Caching for improved performance
• Multi-provider API support
• Detailed logging and statistics

<b>📊 Available Commands:</b>
• <code>/nsfwstats</code> - View detection statistics
• <code>/nsfwtest [text]</code> - Test detection on content

<b>🔧 Supported APIs:</b>
• Google Cloud Vision API
• OpenAI GPT-4 Vision
• Google Perspective API
• OpenAI Moderation API
• AWS Rekognition (planned)
• Azure Content Moderator (planned)

<b>🚀 Performance:</b>
• Cached results for faster repeated checks
• Async processing to avoid blocking
• Progressive analysis (quick checks first)
• Configurable file size limits

<b>📈 Analytics:</b>
• Detection accuracy tracking
• Performance metrics
• Error monitoring and logging

The system is designed to provide excellent performance and accuracy with minimal administrative overhead.
"""

mirror = """<b>Send link along with command line or </b>

/cmd link

<b>By replying to link/file</b>:

/cmd -n new name -e -up upload destination

<b>NOTE:</b>
1. Commands that start with <b>qb</b> are ONLY for torrents."""

yt = """<b>Send link along with command line</b>:

/cmd link
<b>By replying to link</b>:
/cmd -n new name -z password -opt x:y|x1:y1 -range start_time-end_time

Check here all supported <a href='https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md'>SITES</a>
Check all yt-dlp api options from this <a href='https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L212'>FILE</a> or use this <a href='https://t.me/mltb_official_channel/177'>script</a> to convert cli arguments to api options."""

clone = """Send Gdrive|Gdot|Filepress|Filebee|Appdrive|Gdflix link or rclone path along with command or by replying to the link/rc_path by command.
Use -sync to use sync method in rclone. Example: /cmd rcl/rclone_path -up rcl/rclone_path/rc -sync"""

new_name = """<b>New Name</b>: -n

/cmd link -n new name
Note: Doesn't work with torrents"""

multi_link = """<b>Multi links only by replying to first link/file</b>: -i

/cmd -i 10(number of links/files)"""

same_dir = """<b>Move file(s)/folder(s) to new folder</b>: -m

You can use this arg also to move multiple links/torrents contents to the same directory, so all links will be uploaded together as one task

/cmd link -m new folder (only one link inside new folder)
/cmd -i 10(number of links/files) -m folder name (all links contents in one folder)
/cmd -b -m folder name (reply to batch of message/file(each link on new line))

While using bulk you can also use this arg with different folder name along with the links in message or file batch
Example:
link1 -m folder1
link2 -m folder1
link3 -m folder2
link4 -m folder2
link5 -m folder3
link6
so link1 and link2 content will be uploaded from same folder which is folder1
link3 and link4 content will be uploaded from same folder also which is folder2
link5 will uploaded alone inside new folder named folder3
link6 will get uploaded normally alone
"""

thumb = """<b>Thumbnail for current task</b>: -t

/cmd link -t tg-message-link (doc or photo) or none (file without thumb)"""

split_size = """<b>Split size for current task</b>: -sp

/cmd link -sp (500mb or 2gb or 4000000000)
Note: Only mb and gb are supported or write in bytes without unit!

<b>Equal Splits</b>: -es

/cmd link -es
This will split the file into equal parts based on the file size, regardless of the split size setting.
You can also enable Equal Splits in user settings > leech menu.
"""

upload = """<b>Upload Destination</b>: -up

/cmd link -up rcl/gdl (rcl: to select rclone config, remote & path | gdl: To select token.pickle, gdrive id) using buttons
You can directly add the upload path: -up remote:dir/subdir or -up Gdrive_id or -up id/username (telegram) or -up id/username|topic_id (telegram)
If DEFAULT_UPLOAD is `rc` then you can pass up: `gd` to upload using gdrive tools to GDRIVE_ID.
If DEFAULT_UPLOAD is `gd` then you can pass up: `rc` to upload to RCLONE_PATH.

If you want to add path or gdrive manually from your config/token (UPLOADED FROM USETTING) add mrcc: for rclone and mtp: before the path/gdrive_id without space.
/cmd link -up mrcc:main:dump or -up mtp:gdrive_id <strong>or you can simply edit upload using owner/user token/config from usetting without adding mtp: or mrcc: before the upload path/id</strong>

<b>YouTube Upload</b>: -up yt
Upload videos directly to YouTube (requires setup):
-up yt (upload with default settings: unlisted, People & Blogs category)
-up yt:privacy:category:tags:title (custom settings with title)
Examples:
• -up yt:public:10:music,entertainment (public video in Music category)
• -up yt:unlisted:22:tutorial,howto (unlisted video with tags)
• -up yt:private:24::My Custom Title (private video with custom title)
• -up yt:public:10:music:My Music Video (public with all custom settings)

Privacy options: public, unlisted, private
Common categories: 10=Music, 22=People & Blogs, 24=Entertainment, 27=Education
Title: Custom title (leave empty to use template/filename)
Note: Only video files will be uploaded to YouTube. Requires YouTube API setup.

To add leech destination:
-up id/@username/pm
-up b:id/@username/pm (b: means leech by bot) (id or username of the chat or write pm means private message so bot will send the files in private to you)
when you should use b:(leech by bot)? When your default settings is leech by user and you want to leech by bot for specific task.
-up u:id/@username(u: means leech by user) This incase OWNER added USER_SESSION_STRING.
-up h:id/@username(hybrid leech) h: to upload files by bot and user based on file size.
-up id/@username|topic_id(leech in specific chat and topic) add | without space and write topic id after chat id or username.

To upload to cloud storage (Mirror only):
-up gd (Upload to Google Drive)
-up rc (Upload to Rclone)
-up yt (Upload to YouTube)
-up mg (Upload to MEGA.nz)
-up ddl (Upload to DDL servers - Gofile, Streamtape, DevUploads, MediaFire)
-up ddl:gofile (Upload specifically to Gofile)
-up ddl:streamtape (Upload specifically to Streamtape)
-up ddl:devuploads (Upload specifically to DevUploads)
-up ddl:mediafire (Upload specifically to MediaFire)

In case you want to specify whether using token.pickle or service accounts you can add tp:gdrive_id (using token.pickle) or sa:gdrive_id (using service accounts) or mtp:gdrive_id (using token.pickle uploaded from usetting).
DEFAULT_UPLOAD doesn't affect on leech cmds.
"""

user_download = """<b>User Download</b>: link

/cmd tp:link to download using owner token.pickle incase service account enabled.
/cmd sa:link to download using service account incase service account disabled.
/cmd tp:gdrive_id to download using token.pickle and file_id incase service account enabled.
/cmd sa:gdrive_id to download using service account and file_id incase service account disabled.
/cmd mtp:gdrive_id or mtp:link to download using user token.pickle uploaded from usetting
/cmd mrcc:remote:path to download using user rclone config uploaded from usetting
you can simply edit upload using owner/user token/config from usetting without adding mtp: or mrcc: before the path/id"""

rcf = """<b>Rclone Flags</b>: -rcf

/cmd link|path|rcl -up path|rcl -rcf --buffer-size:8M|--drive-starred-only|key|key:value
This will override all other flags except --exclude
Check here all <a href='https://rclone.org/flags/'>RcloneFlags</a>."""

bulk = """<b>Bulk Download</b>: -b

Bulk can be used only by replying to text message or text file contains links separated by new line.
Note: Bulk operations can be enabled/disabled by the administrator in bot settings.

Example:
link1 -n new name -up remote1:path1 -rcf |key:value|key:value
link2 -z -n new name -up remote2:path2
link3 -e -n new name -up remote2:path2
Reply to this example by this cmd -> /cmd -b(bulk)

Note: Any arg along with the cmd will be setted to all links
/cmd -b -up remote: -z -m folder name (all links contents in one zipped folder uploaded to one destination)
so you can't set different upload destinations along with link incase you have added -m along with cmd
You can set start and end of the links from the bulk like seed, with -b start:end or only end by -b :end or only start by -b start.
The default start is from zero(first link) to inf."""

rlone_dl = """<b>Rclone Download</b>:

Treat rclone paths exactly like links
/cmd main:dump/ubuntu.iso or rcl(To select config, remote and path)
Users can add their own rclone from user settings
If you want to add path manually from your config add mrcc: before the path without space
/cmd mrcc:main:dump/ubuntu.iso
You can simply edit using owner/user config from usetting without adding mrcc: before the path"""

extract_zip = """<b>Extract/Zip</b>: -e -z

/cmd link -e password (extract password protected)
/cmd link -z password (zip password protected)
/cmd link -z password -e (extract and zip password protected)
Note: When both extract and zip added with cmd it will extract first and then zip, so always extract first"""

join = """<b>Join Splitted Files</b>: -j

This option will only work before extract and zip, so mostly it will be used with -m argument (samedir)
By Reply:
/cmd -i 3 -j -m folder name
/cmd -b -j -m folder name
if u have link(folder) have splitted files:
/cmd link -j"""

tg_links = """<b>TG Links</b>:

Treat links like any direct link
Some links need user access so you must add USER_SESSION_STRING for it.
Three types of links:
Public: https://t.me/channel_name/message_id
Private: tg://openmessage?user_id=xxxxxx&message_id=xxxxx
Super: https://t.me/c/channel_id/message_id
Range: https://t.me/channel_name/first_message_id-last_message_id
Range Example: tg://openmessage?user_id=xxxxxx&message_id=555-560 or https://t.me/channel_name/100-150
Skip Messages: Add -skip followed by a number to skip messages in a range
Skip Examples:
• https://t.me/channel_name/100-150 -skip 3 (will download messages 100, 103, 106, etc.)
• https://t.me/channel_name/100-150-skip3 (same result, more compact format)
• tg://openmessage?user_id=xxxxxx&message_id=555-560 -skip 2 (will download messages 555, 557, 559)
Note: Range link will work only by replying cmd to it"""

sample_video = """<b>Sample Video</b>: -sv

Create sample video for one video or folder of videos.
/cmd -sv (it will take the default values which 60sec sample duration and part duration is 4sec).
You can control those values. Example: /cmd -sv 70:5(sample-duration:part-duration) or /cmd -sv :5 or /cmd -sv 70."""

screenshot = """<b>ScreenShots</b>: -ss

Create screenshots for one video or folder of videos.
/cmd -ss (it will take the default values which is 10 photos).
You can control this value. Example: /cmd -ss 6."""

seed = """<b>Bittorrent seed</b>: -d

/cmd link -d ratio:seed_time or by replying to file/link
To specify ratio and seed time add -d ratio:time.
Example: -d 0.7:10 (ratio and time) or -d 0.7 (only ratio) or -d :10 (only time) where time in minutes"""

zip_arg = """<b>Zip</b>: -z password

/cmd link -z (zip)
/cmd link -z password (zip password protected)"""

qual = """<b>Quality Buttons</b>: -s

In case default quality added from yt-dlp options using format option and you need to select quality for specific link or links with multi links feature.
/cmd link -s"""

yt_opt = """<b>Options</b>: -opt

/cmd link -opt {"format": "bv*+mergeall[vcodec=none]", "nocheckcertificate": True, "playliststart": 10, "fragment_retries": float("inf"), "matchtitle": "S13", "writesubtitles": True, "live_from_start": True, "postprocessor_args": {"xtra": ["-threads", "4"]}, "wait_for_video": (5, 100), "download_ranges": [{"start_time": 0, "end_time": 10}]}
Check all yt-dlp api options from this <a href='https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L184'>FILE</a> or use this <a href='https://t.me/mltb_official_channel/177'>script</a> to convert cli arguments to api options."""

download_range = """<b>Download Range</b>: -range

Download only a specific time range from the video/audio.

<b>Usage:</b>
/cmd link -range start_time-end_time
/cmd link -range start_time:end_time

<b>Time Format:</b>
• <code>SS</code> - Seconds only (e.g., 30)
• <code>MM:SS</code> - Minutes and seconds (e.g., 1:30)
• <code>HH:MM:SS</code> - Hours, minutes and seconds (e.g., 1:30:45)

<b>Examples:</b>
• <code>/ytdl https://youtube.com/watch?v=example -range 30-90</code>
  Download from 30 seconds to 90 seconds (1 minute clip)

• <code>/ytdl https://youtube.com/watch?v=example -range 1:30-3:45</code>
  Download from 1 minute 30 seconds to 3 minutes 45 seconds

• <code>/ytdl https://youtube.com/watch?v=example -range 0:30:15-0:45:30</code>
  Download from 30 minutes 15 seconds to 45 minutes 30 seconds

• <code>/ytdl https://youtube.com/watch?v=example -range 10:</code>
  Download from 10 seconds to the end

• <code>/ytdl https://youtube.com/watch?v=example -range :120</code>
  Download from start to 2 minutes (120 seconds)

<b>Notes:</b>
• Both start and end times are optional
• Use either dash (-) or colon (:) as separator
• The downloaded file will contain only the specified time range
• Works with all supported video/audio platforms
• Useful for extracting clips, highlights, or specific segments"""

convert_media = """<b>Convert Media</b>: -ca -cv -cs -cd -cr

<blockquote>Dont understand? Then follow this <a href='https://t.me/aimupdate/218'>quide</a></blockquote>

Convert media files to different formats with customizable settings for video, audio, subtitles, documents, and archives.

<b>Basic Usage:</b>
- <code>-cv format</code>: Convert videos (e.g., <code>-cv mp4</code>)
- <code>-ca format</code>: Convert audio (e.g., <code>-ca mp3</code>)
- <code>-cs format</code>: Convert subtitles (e.g., <code>-cs srt</code>)
- <code>-cd format</code>: Convert documents (e.g., <code>-cd pdf</code>)
- <code>-cr format</code>: Convert archives (e.g., <code>-cr zip</code>)
- <code>-del</code>: Delete original files after conversion

<b>Supported Formats:</b>
• <b>Videos</b>: MP4, MKV, AVI, MOV, WebM, FLV, WMV, M4V, TS, 3GP
• <b>Audio</b>: MP3, M4A, FLAC, WAV, OGG, OPUS, AAC, WMA, ALAC
• <b>Subtitles</b>: SRT, ASS, SSA, VTT, WebVTT, SUB, SBV
• <b>Documents</b>: PDF, DOCX, TXT, ODT, RTF
• <b>Archives</b>: ZIP, RAR, 7Z, TAR, GZ, BZ2

<b>Advanced Usage:</b>
- <code>-ca mp3 + flac ogg</code>: Convert only FLAC and OGG audios to MP3
- <code>-cv mkv - webm flv</code>: Convert all videos to MKV except WebM and FLV
- <code>-ca mp3 -cv mp4 -cs srt</code>: Convert audios to MP3, videos to MP4, and subtitles to SRT
- <code>-cv mp4 -del</code>: Convert all videos to MP4 and delete original files

<b>Examples:</b>
/cmd link -ca mp3 -cv mp4
/cmd link -ca mp3 + flac ogg
/cmd link -cv mkv - webm flv
/cmd link -cs srt -cd pdf
/cmd link -cr zip -del

<b>Important Notes:</b>
• Enable convert in Media Tools settings before using
• Enable specific media type conversions (video, audio, etc.)
• Configure quality settings for optimal results
• Set priority to control when conversion runs in the pipeline
• Use /mthelp command for detailed guide on convert feature"""

add_media = """<b>Add Media</b>: -add -add-video -add-audio -add-subtitle -add-attachment

<blockquote>Add media tracks to existing files</blockquote>

Add specific tracks (video, audio, subtitle, attachment) to media files.

<b>Basic Usage:</b>
- <code>-add</code>: Add all enabled track types based on settings
- <code>-add-video</code>: Add only video tracks
- <code>-add-audio</code>: Add only audio tracks
- <code>-add-subtitle</code>: Add only subtitle tracks
- <code>-add-attachment</code>: Add only attachment tracks

<b>Track Handling Flags:</b>
- <code>-del</code>: Delete original file after processing
- <code>-preserve</code>: Preserve existing tracks when adding new ones
- <code>-replace</code>: Replace existing tracks with new ones

<b>Advanced Usage (Long Format):</b>
- <code>-add-video-index 0,1,2</code>: Add video tracks at indices 0, 1, and 2
- <code>-add-audio-index 0,1</code>: Add audio tracks at indices 0 and 1
- <code>-add -del</code>: Add tracks and delete original file
- <code>-add -preserve</code>: Add tracks and preserve existing tracks
- <code>-add -replace</code>: Add tracks and replace existing tracks

<b>Track Index Selection:</b>
- <code>-add-video-index 0</code>: Add only the first video track from source
- <code>-add-audio-index 1</code>: Add only the second audio track from source
- <code>-add-subtitle-index 2</code>: Add only the third subtitle track from source
- <code>-add-attachment-index 0</code>: Add only the first attachment from source
- <code>-add-video-index 0,1,2</code>: Add multiple video tracks at specified indices
- <code>-add-audio-index 0,1,2</code>: Add multiple audio tracks at specified indices

<b>Advanced Usage (Short Format):</b>
- <code>-avi 0</code>: Add only the first video track from source
- <code>-avi 0,1,2</code>: Add video tracks at indices 0, 1, and 2
- <code>-aai 1</code>: Add only the second audio track from source
- <code>-aai 0,1</code>: Add audio tracks at indices 0 and 1
- <code>-asi 2</code>: Add only the third subtitle track from source
- <code>-ati 0</code>: Add only the first attachment from source

<b>Additional Video Settings:</b>
- <code>-add-video-codec h264</code>: Set video codec (h264, h265, vp9, etc.)
- <code>-add-video-quality 18</code>: Set video quality (CRF value, lower is better)
- <code>-add-video-preset medium</code>: Set encoding preset (ultrafast, fast, medium, slow)
- <code>-add-video-bitrate 5M</code>: Set video bitrate
- <code>-add-video-resolution 1920x1080</code>: Set video resolution
- <code>-add-video-fps 30</code>: Set video frame rate

<b>Additional Audio Settings:</b>
- <code>-add-audio-codec aac</code>: Set audio codec (aac, mp3, opus, flac, etc.)
- <code>-add-audio-bitrate 320k</code>: Set audio bitrate
- <code>-add-audio-channels 2</code>: Set number of audio channels
- <code>-add-audio-sampling 48000</code>: Set audio sampling rate
- <code>-add-audio-volume 1.5</code>: Set audio volume (1.0 is normal)

<b>Additional Subtitle Settings:</b>
- <code>-add-subtitle-codec srt</code>: Set subtitle codec (srt, ass, etc.)
- <code>-add-subtitle-language eng</code>: Set subtitle language code
- <code>-add-subtitle-encoding UTF-8</code>: Set subtitle character encoding
- <code>-add-subtitle-font Arial</code>: Set subtitle font (for ASS/SSA)
- <code>-add-subtitle-font-size 24</code>: Set subtitle font size (for ASS/SSA)
- <code>-add-subtitle-hardsub</code>: Burn subtitles into video (permanent, cannot be turned off)

<b>Hardsub vs Soft Subtitles:</b>
- <b>Hardsub</b>: Subtitles are permanently burned into the video (requires re-encoding)
- <b>Soft Subtitles</b>: Subtitles are separate tracks (can be toggled on/off by player)

<b>Attachment Settings:</b>
- <code>-add-attachment-mimetype font/ttf</code>: Set MIME type for attachment

<b>Examples:</b>
/cmd link -add
/cmd link -add-video -add-audio
/cmd link -add -del
/cmd link -add-video -add-video-codec h264 -add-video-quality 18
/cmd link -add-audio -add-audio-codec aac -add-audio-bitrate 320k
/cmd link -add-subtitle -add-subtitle-codec srt
/cmd link -add-video-index 0,1 -m (with multi-link feature)

<b>Multi-Link and Bulk Integration:</b>
- <code>/cmd link1 link2 link3 -add-video -m</code>: Add video from link2 to link1
- <code>/cmd link1 link2 link3 -add-video-index 0,1 -m</code>: Add videos from link2 at index 0 and link3 at index 1 to link1

<b>Important Notes:</b>
• The Add feature must be enabled in both the bot settings and user settings
• The main Add toggle and the specific track type toggles must be enabled
• Configure add settings in Media Tools settings
• Add priority can be set to control when it runs in the processing pipeline
• When using multi-link feature (-m), tracks are added from the additional files
• When add is enabled through settings, original files are automatically deleted after processing
• Use the -del flag to delete original files after adding tracks (or -del f to keep original files)
• Settings with value 'none' will not be used in command generation
• If a specified index is not available, the system will use the first available index
• When using multiple indices with multi-link, tracks are added in the order of input files
"""

swap_media = """<b>Swap Media</b>: -swap -swap-audio -swap-video -swap-subtitle

<blockquote>Reorder media tracks by language priority or index position</blockquote>

Reorder tracks within media files using either language-based or index-based swapping.

<b>Basic Usage:</b>
- <code>-swap</code>: Swap all enabled track types based on settings
- <code>-swap-audio</code>: Swap only audio tracks
- <code>-swap-video</code>: Swap only video tracks
- <code>-swap-subtitle</code>: Swap only subtitle tracks

<b>Two Swapping Modes:</b>

<b>1. Language-based Swapping:</b>
Reorders tracks based on language priority. Tracks with higher priority languages are moved to the front.

<b>2. Index-based Swapping:</b>
Swaps tracks at specific positions according to the defined pattern.

<b>Language-based Examples:</b>
- Language order: <code>eng,hin,jpn</code>
- Result: English tracks first, Hindi second, Japanese third, others maintain original order
- Tracks without language tags are placed after prioritized languages

<b>Index-based Examples:</b>
- Index order: <code>0,1</code> - Swaps first two tracks (track 0 ↔ track 1)
- Index order: <code>1,2,0</code> - Rotates first three tracks (0→1, 1→2, 2→0)
- Index order: <code>2,1,0</code> - Reverses first three tracks
- Single index: <code>1</code> - No swapping occurs (need at least 2 indices)

<b>Configuration Settings:</b>
- <b>Use Language Mode</b>: Toggle between language-based (true) or index-based (false) swapping
- <b>Language Order</b>: Priority order for languages (e.g., "eng,hin,jpn")
- <b>Index Order</b>: Swap pattern for track positions (e.g., "0,1" or "1,2,0")

<b>Examples:</b>
/cmd link -swap
/cmd link -swap-audio -swap-video
/cmd link -swap -del
/cmd link -swap-audio -m (with multi-link feature)

<b>Multi-Link Integration:</b>
- <code>/cmd link1 link2 -swap -m</code>: Swap tracks in all files
- <code>/cmd link1 link2 -swap-audio -m</code>: Swap only audio tracks in all files

<b>Important Notes:</b>
• The Swap feature must be enabled in both the bot settings and user settings
• The main Swap toggle and the specific track type toggles must be enabled
• Configure swap settings in Media Tools settings
• Swap priority can be set to control when it runs in the processing pipeline
• Language-based swapping works best with properly tagged media files
• Index-based swapping gives precise control over track order
• Invalid indices are automatically handled and ignored
• When swap is enabled through settings, original files are automatically deleted after processing
• Use the -del flag to delete original files after swapping (or -del f to keep original files)
• Settings with value 'none' will not be used in command generation
• If specified languages are not found, tracks maintain their original order
• Swap operations preserve all track metadata and properties
"""

extract_media = """<b>Extract Media</b>: -extract -extract-video -extract-audio -extract-subtitle -extract-attachment

<blockquote>Extract specific tracks from media files</blockquote>

Extract specific tracks (video, audio, subtitle, attachment) from media files.

<b>Basic Usage:</b>
- <code>-extract</code>: Extract all enabled track types based on settings
- <code>-extract-video</code>: Extract only video tracks
- <code>-extract-audio</code>: Extract only audio tracks
- <code>-extract-subtitle</code>: Extract only subtitle tracks
- <code>-extract-attachment</code>: Extract only attachment tracks

<b>Advanced Usage (Long Format):</b>
- <code>-extract-video-index 0</code>: Extract only the first video track
- <code>-extract-audio-index 1</code>: Extract only the second audio track
- <code>-extract-subtitle-index 2</code>: Extract only the third subtitle track
- <code>-extract-attachment-index 0</code>: Extract only the first attachment
- <code>-extract -del</code>: Extract tracks and delete original file

<b>Multiple Track Indices:</b>
- <code>-extract-video-index 0,1</code>: Extract first and second video tracks
- <code>-extract-audio-index 0,2,3</code>: Extract first, third, and fourth audio tracks
- <code>-extract-subtitle-index 1,2</code>: Extract second and third subtitle tracks
- <code>-extract-attachment-index 0,1</code>: Extract first and second attachments

<b>Advanced Usage (Short Format):</b>
- <code>-vi 0</code>: Extract only the first video track
- <code>-ai 1</code>: Extract only the second audio track
- <code>-si 2</code>: Extract only the third subtitle track
- <code>-ati 0</code>: Extract only the first attachment
- <code>-vi 0,1 -ai 2,3</code>: Extract multiple tracks with short format

<b>Additional Video Settings:</b>
- <code>-extract-video-codec h264</code>: Set video codec (h264, h265, vp9, etc.)
- <code>-extract-video-quality 18</code>: Set video quality (CRF value, lower is better)
- <code>-extract-video-preset medium</code>: Set encoding preset (ultrafast, fast, medium, slow)
- <code>-extract-video-bitrate 5M</code>: Set video bitrate
- <code>-extract-video-resolution 1920x1080</code>: Set video resolution
- <code>-extract-video-fps 30</code>: Set video frame rate

<b>Additional Audio Settings:</b>
- <code>-extract-audio-codec aac</code>: Set audio codec (aac, mp3, opus, flac, etc.)
- <code>-extract-audio-bitrate 320k</code>: Set audio bitrate
- <code>-extract-audio-channels 2</code>: Set number of audio channels
- <code>-extract-audio-sampling 48000</code>: Set audio sampling rate
- <code>-extract-audio-volume 1.5</code>: Set audio volume (1.0 is normal)

<b>Additional Subtitle Settings:</b>
- <code>-extract-subtitle-codec srt</code>: Set subtitle codec (srt, ass, etc.)
- <code>-extract-subtitle-language eng</code>: Set subtitle language code
- <code>-extract-subtitle-encoding UTF-8</code>: Set subtitle character encoding
- <code>-extract-subtitle-font Arial</code>: Set subtitle font (for ASS/SSA)
- <code>-extract-subtitle-font-size 24</code>: Set subtitle font size (for ASS/SSA)

<b>Attachment Settings:</b>
- <code>-extract-attachment-filter *.ttf</code>: Filter attachments by pattern

<b>Examples:</b>
/cmd link -extract
/cmd link -extract-video -extract-audio
/cmd link -vi 0 -ai 1
/cmd link -extract-subtitle
/cmd link -extract -del
/cmd link -extract-video -extract-video-codec h264 -extract-video-quality 18
/cmd link -extract-audio -extract-audio-codec aac -extract-audio-bitrate 320k
/cmd link -extract-subtitle -extract-subtitle-codec srt

<b>Important Notes:</b>
• The Extract feature must be enabled in both the bot settings and user settings
• The main Extract toggle and the specific track type toggles must be enabled
• Configure extract settings in Media Tools settings
• Extract priority can be set to control when it runs in the processing pipeline
• Track indices start from 0 (first track is index 0)
• If no index is specified, all tracks of that type will be extracted
• You can use either long format (-extract-video-index) or short format (-vi) flags
• When extract is enabled through settings, original files are automatically deleted after extraction
• Only the specified track indices will be extracted when indices are provided
• Use the -del flag to delete original files after extraction (or -del f to keep original files)
• Settings with value 'none' will not be used in command generation
• For ASS/SSA subtitles, use 'copy' codec to preserve the original format or 'srt' to convert to SRT"""

remove_tracks = """<b>Remove Tracks</b>: -remove -remove-video -remove-audio -remove-subtitle -remove-attachment -remove-metadata

<b>Basic Usage:</b>
- <code>-remove</code>: Enable remove feature (uses configured settings)
- <code>-remove-video</code>: Remove only video tracks
- <code>-remove-audio</code>: Remove only audio tracks
- <code>-remove-subtitle</code>: Remove only subtitle tracks
- <code>-remove-attachment</code>: Remove only attachment tracks
- <code>-remove-metadata</code>: Remove metadata from file

<b>Advanced Usage (Long Format):</b>
- <code>-remove-video-index 0</code>: Remove only the first video track
- <code>-remove-audio-index 1</code>: Remove only the second audio track
- <code>-remove-subtitle-index 2</code>: Remove only the third subtitle track
- <code>-remove-attachment-index 0</code>: Remove only the first attachment
- <code>-remove -del</code>: Remove tracks and delete original file

<b>Multiple Track Indices:</b>
- <code>-remove-video-index 0,1</code>: Remove first and second video tracks
- <code>-remove-audio-index 0,2,3</code>: Remove first, third, and fourth audio tracks
- <code>-remove-subtitle-index 1,2</code>: Remove second and third subtitle tracks
- <code>-remove-attachment-index 0,1</code>: Remove first and second attachments

<b>Advanced Usage (Short Format):</b>
- <code>-rvi 0</code>: Remove only the first video track
- <code>-rai 1</code>: Remove only the second audio track
- <code>-rsi 2</code>: Remove only the third subtitle track
- <code>-rati 0</code>: Remove only the first attachment
- <code>-rvi 0,1 -rai 2,3</code>: Remove multiple tracks with short format

<b>Complex Examples:</b>
- <code>-rvi 0,1 -remove-metadata</code>: Remove first two video tracks and metadata
- <code>-remove-audio-index 0 -remove-subtitle</code>: Remove first audio track and all subtitles
- <code>-rvi 1 -rai 0,2 -rsi 0 -remove-metadata</code>: Complex multi-track removal

<b>Important Notes:</b>
• The Remove feature must be enabled in both the bot settings and user settings
• The main Remove toggle and the specific track type toggles must be enabled
• Configure remove settings in Media Tools settings
• Remove priority can be set to control when it runs in the processing pipeline
• Track indices start from 0 (first track is index 0)
• If no index is specified, all tracks of that type will be removed
• You can use either long format (-remove-video-index) or short format (-rvi) flags
• When remove is enabled through settings, original files are automatically deleted after removal
• Only the specified track indices will be removed when indices are provided
• Use the -del flag to delete original files after removal (or -del f to keep original files)
• Settings with value 'none' will not be used in command generation
• Remove feature works with all media containers (MKV, MP4, AVI, etc.)"""

force_start = """<b>Force Start</b>: -f -fd -fu
/cmd link -f (force download and upload)
/cmd link -fd (force download only)
/cmd link -fu (force upload directly after download finish)"""

media_tools_flag = """<b>Media Tools Flag</b>: -mt

/cmd link -mt (opens media tools settings before starting the task)

<blockquote>
When you use the -mt flag with any command:
1. The bot will show the media tools settings menu
2. You can customize settings as needed
3. Click "Done" to start the task with your settings
4. Click "Cancel" to abort the task
5. If no action is taken within 60 seconds, the task will be cancelled
</blockquote>

<blockquote expandable="expandable"><b>Usage Examples</b>:
• <code>/mirror https://example.com/video.mp4 -mt</code>
  Shows media tools settings before starting the mirror task

• <code>/leech https://example.com/files.zip -z -mt</code>
  Shows media tools settings before starting the leech task with zip extraction

• <code>/ytdl https://youtube.com/watch?v=example -mt</code>
  Shows media tools settings before starting the YouTube download

• <code>/mirror https://example.com/videos.zip -merge-video -mt</code>
  Shows media tools settings before starting a task with video merging

• <code>/leech https://example.com/video.mp4 -watermark "My Channel" -mt</code>
  Configure watermark settings before applying text watermark

• <code>/mirror https://example.com/audio.mp3 -ca mp3 -mt</code>
  Configure conversion settings before converting audio to MP3</blockquote>

<b>Benefits</b>:
• Configure media tools settings on-the-fly for specific tasks
• No need to use separate commands to change settings
• Preview and adjust settings before processing large files
• Easily cancel tasks if settings aren't right
• Works with all download commands and other flags

<b>Note</b>: All messages related to the <code>-mt</code> flag interaction are automatically deleted after 5 minutes for a cleaner chat experience."""

gdrive = """<b>Gdrive</b>: link
If DEFAULT_UPLOAD is `rc` then you can pass up: `gd` to upload using gdrive tools to GDRIVE_ID.
/cmd gdriveLink or gdl or gdriveId -up gdl or gdriveId or gd
/cmd tp:gdriveLink or tp:gdriveId -up tp:gdriveId or gdl or gd (to use token.pickle if service account enabled)
/cmd sa:gdriveLink or sa:gdriveId -p sa:gdriveId or gdl or gd (to use service account if service account disabled)
/cmd mtp:gdriveLink or mtp:gdriveId -up mtp:gdriveId or gdl or gd(if you have added upload gdriveId from usetting) (to use user token.pickle that uploaded by usetting)
You can simply edit using owner/user token from usetting without adding mtp: before the id"""

rclone_cl = """<b>Rclone</b>: path
If DEFAULT_UPLOAD is `gd` then you can pass up: `rc` to upload to RCLONE_PATH.
/cmd rcl/rclone_path -up rcl/rclone_path/rc -rcf flagkey:flagvalue|flagkey|flagkey:flagvalue
/cmd rcl or rclone_path -up rclone_path or rc or rcl
/cmd mrcc:rclone_path -up rcl or rc(if you have add rclone path from usetting) (to use user config)"""

name_sub = r"""<b>Name Substitution</b>: -ns

<blockquote>Dont understand? Then follow this <a href='https://t.me/aimupdate/190'>quide</a></blockquote>

/cmd link -ns script/code/s | mirror/leech | tea/ /s | clone | cpu/ | \[hello\]/hello | \\text\\/text/s
This will affect on all files. Format: wordToReplace/wordToReplaceWith/sensitiveCase
Word Subtitions. You can add pattern instead of normal text. Timeout: 60 sec
NOTE: You must add \ before any character, those are the characters: \^$.|?*+()[]{}-
1. script will get replaced by code with sensitive case
2. mirror will get replaced by leech
4. tea will get replaced by space with sensitive case
5. clone will get removed
6. cpu will get replaced by space
7. [hello] will get replaced by hello
8. \text\ will get replaced by text with sensitive case
"""

transmission = """<b>Tg transmission</b>: -hl -ut -bt
/cmd link -hl (leech by user and bot session with respect to size) (Hybrid Leech)
/cmd link -bt (leech by bot session)
/cmd link -ut (leech by user)"""

thumbnail_layout = """Thumbnail Layout: -tl
/cmd link -tl 3x3 (widthxheight) 3 photos in row and 3 photos in column"""

leech_as = """<b>Leech as</b>: -doc -med
/cmd link -doc (Leech as document)
/cmd link -med (Leech as media)"""

font_styles = """<b>Font Styles</b>:
Use the /fonts or /fontstyles command to see available font styles for leech.

<b>Three Types of Font Styling:</b>
• <b>Unicode Styles</b>: Transform regular ASCII characters into special Unicode variants (serif, sans, script, etc.)
• <b>HTML Formatting</b>: Apply Telegram's supported HTML tags (bold, italic, code, etc.)
• <b>Google Fonts</b>: Use any Google Font name for styling (Roboto, Open Sans, Lato, etc.)

<blockquote expandable="expandable"><b>Google Fonts Support:</b>
You can use Google Fonts in two ways:

1. <b>Leech Font Setting</b>: Set a Google Font name as your leech font to apply it to all captions

2. <b>Leech Caption Templates</b>: Apply Google Fonts to specific parts of your caption using this syntax:
   <code>{{variable}font_name}</code> - Apply font_name to just that variable
   Example: <code>{{filename}Roboto} - Size: {size}</code>

3. <b>Available Google Fonts</b>: You can use any Google Font name, including:
   • Roboto, Open Sans, Lato, Montserrat, Oswald
   • Raleway, Source Sans Pro, Slabo, PT Sans
   • And many more - see fonts.google.com for the full list

4. <b>Font Weight Support</b>: You can specify font weight for leech caption:
   • <code>{{filename}Roboto:700}</code> - Bold Roboto
   • <code>{{filename}Open Sans:300}</code> - Light Open Sans
   • <code>{{filename}Montserrat:900}</code> - Black Montserrat

5. <b>Font Style Support</b>: You can specify font style for leech caption:
   • <code>{{filename}Roboto:italic}</code> - Italic Roboto
   • <code>{{filename}Open Sans:700italic}</code> - Bold Italic Open Sans

6. <b>Multiple Font Properties</b>: You can combine weight and style for leech caption:
   • <code>{{filename}Roboto:700italic}</code> - Bold Italic Roboto</blockquote>

<blockquote expandable="expandable"><b>Unicode Font Styles:</b>
Unicode font styles transform regular ASCII characters into special Unicode variants.

Available Unicode styles:
• <b>serif</b>: 𝐒𝐞𝐫𝐢𝐟 𝐭𝐞𝐱𝐭 (bold)
• <b>serif_i</b>: 𝑆𝑒𝑟𝑖𝑓 𝑖𝑡𝑎𝑙𝑖𝑐 𝑡𝑒𝑥𝑡
• <b>serif_b</b>: 𝑺𝒆𝒓𝒊𝒇 𝒃𝒐𝒍𝒅 𝒊𝒕𝒂𝒍𝒊𝒄 𝒕𝒆𝒙𝒕
• <b>sans</b>: 𝖲𝖺𝗇𝗌 𝗍𝖾𝗑𝗍
• <b>sans_i</b>: 𝘚𝘢𝘯𝘴 𝘪𝘵𝘢𝘭𝘪𝘤 𝘵𝘦𝘹𝘵
• <b>sans_b</b>: 𝗦𝗮𝗻𝘀 𝗯𝗼𝗹𝗱 𝘁𝗲𝘅𝘁
• <b>sans_bi</b>: 𝙎𝙖𝙣𝙨 𝙗𝙤𝙡𝙙 𝙞𝙩𝙖𝙡𝙞𝙘 𝙩𝙚𝙭𝙩
• <b>script</b>: 𝒮𝒸𝓇𝒾𝓅𝓉 𝓉𝑒𝓍𝓉
• <b>script_b</b>: 𝓢𝓬𝓻𝓲𝓹𝓽 𝓫𝓸𝓵𝓭 𝓽𝓮𝔁𝓽
• <b>fraktur</b>: 𝔉𝔯𝔞𝔨𝔱𝔲𝔯 𝔱𝔢𝔵𝔱
• <b>fraktur_b</b>: 𝕱𝖗𝖆𝖐𝖙𝖚𝖗 𝖇𝖔𝖑𝖉 𝖙𝖊𝖝𝖙
• <b>mono</b>: 𝙼𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎 𝚝𝚎𝚡𝚝
• <b>double</b>: 𝔻𝕠𝕦𝕓𝕝𝕖-𝕤𝕥𝕣𝕦𝕔𝕜 𝕥𝕖𝕩𝕥
• <b>gothic</b>: 𝖆𝖇𝖈
• <b>small_caps</b>: ᴀʙᴄ
• <b>circled</b>: ⓐⓑⓒ
• <b>bubble</b>: ａｂｃ
• <b>inverted</b>: ɐqɔ
• <b>squared</b>: 🄰🄱🄲
• <b>regional</b>: 🇦🇧🇨
• <b>superscript</b>: ᵃᵇᶜ
• <b>subscript</b>: ₐₑₓ
• <b>wide</b>: ｗｉｄｅ
• <b>cursive</b>: 𝒶𝒷𝒸

<b>For Leech Font:</b>
Enter one of the Unicode style names like "serif", "sans_b", "script", etc.
Example: Enter sans_b to use 𝗦𝗮𝗻𝘀 𝗯𝗼𝗹𝗱 𝘁𝗲𝘅𝘁 for all your leech captions

<b>For Leech Caption:</b>
Use the template variable format: {{variable}unicode_style}
Example: {{filename}serif_b} - Size: {{size}mono}
This applies serif bold to the filename and monospace to the size

Remember that Unicode styling only works with basic Latin characters (A-Z, a-z) and won't affect numbers or special characters.</blockquote>

<blockquote expandable="expandable"><b>HTML Formatting:</b>
HTML formatting applies Telegram's supported HTML tags to your text.

Available HTML formats:
• <b>bold</b>: <b>Bold text</b>
• <b>italic</b>: <i>Italic text</i>
• <b>underline</b>: <u>Underlined text</u>
• <b>strike</b>: <s>Strikethrough text</s>
• <b>code</b>: <code>Monospace text</code>
• <b>pre</b>: Preformatted text
• <b>spoiler</b>: <tg-spoiler>Spoiler text</tg-spoiler>
• <b>quote</b>: Quoted text

You can combine HTML formats:
• <b>bold_italic</b>: <b><i>Bold italic text</i></b>
• <b>bold_underline</b>: <b><u>Bold underlined text</u></b>
• <b>italic_underline</b>: <i><u>Italic underlined text</u></b>
• <b>bold_italic_underline</b>: <b><i><u>Bold italic underlined text</u></i></b>
• <b>quote_expandable</b>: <b><i><u>The text will be in expaned formate</u></i></b>
• <b>bold_quote</b>: <b><i><u>Text will be bold in quote formate</u></i></b>

<b>or Leech Font:</b>
Enter an HTML format name like "bold", "italic", "code", etc.
Example: Enter 'bold' to use <b>Bold text</b> for all your leech captions

<b>For Leech Caption:</b>
Use the template variable format: {{variable}html_format}
Example: {{filename}bold} - Size: {{size}code}
You can also use html tags like this -> <b> <i> <s> <u> <code> <pre> <tg-spoiler> <blockquote> <blockquote expandable="expandable">. You can also nest them together.</blockquote>

<blockquote expandable="expandable"><b>Unicode Emojis and Special Characters:</b>

You can also use any single Unicode character or emoji as a style. Examples:
- 🔥: Will add the fire emoji before and after your text
- ⭐: Will add stars before and after your text
- Any other emoji or special character will be used similarly

<b>For Leech Font:</b>
Any single emoji: 🔥, ⭐, 🚀, etc.
Any single Unicode character
Unicode codepoints in U+XXXX format (e.g., U+1F525 for 🔥)
The emoji will be added before and after your text
Example: If leech font is "🔥" and text is "filename.mp4", it will appear as "🔥filename.mp4🔥"

<b>For Leech Caption:</b>
Use the template variable format: {{variable}unicode_emoji}
Example: {{filename}🔥}</blockquote>

<blockquote expandable="expandable"><b>Template Variables (For Leech Caption and Leech Filename):</b>

<b>Basic Variables:</b>
• <code>{filename}</code> - The name of the file without extension
• <code>{size}</code> - The size of the file (e.g., 1.5GB, 750MB)
• <code>{duration}</code> - The duration of media files (e.g., 01:30:45)
• <code>{quality}</code> - The quality of video files (e.g., 1080p, 720p)
• <code>{audios}</code> - Audio languages in the file (e.g., English, Hindi)
• <code>{subtitles}</code> - Subtitle languages in the file (e.g., English, Spanish)
• <code>{md5_hash}</code> - MD5 hash of the file

<b>TV Show Variables:</b>
• <code>{season}</code> - Season number (with leading zero for single digits)
• <code>{episode}</code> - Episode number (with leading zero for single digits)

<b>Media Information:</b>
• <code>{NumVideos}</code> - Number of video tracks
• <code>{NumAudios}</code> - Number of audio tracks
• <code>{NumSubtitles}</code> - Number of subtitle tracks
• <code>{year}</code> - Release year extracted from filename or metadata
• <code>{formate}</code> - File format/extension
• <code>{id}</code> - Unique ID of the file
• <code>{framerate}</code> - Video framerate
• <code>{codec}</code> - Codec information (Video, Audio, Subtitle)

"<b>Example Usage:</b>
• TV Show: <code>{filename} S{season}E{episode} [{quality}]</code>
• Detailed: <code>{filename} [{formate}] [{codec}] [{framerate}]</code></blockquote>

<blockquote expandable="expandable"><b>Usage Examples:</b>

1. <b>Setting a default font style for all leech captions:</b>
   • Use the /usettings or /settings command and select "LEECH_FONT"
   • Enter a font style name like "serif_b" or "Roboto"

2. <b>Using font styles in caption templates:</b>
   • <code>{{filename}serif_b} - Size: {size}</code>
   • <code>File: {{filename}Montserrat:700} | {size}</code>
   • <code>{{filename}bold} | {{size}italic}</code>

3. <b>Mixing different font styles:</b>
   • <code>{{filename}Roboto:700} | {{size}mono} | {{quality}script}</code>

4. <b>Using HTML formatting with variables:</b>
   • <code>{{filename}bold_italic} | {{size}code}</code>

5. <b>Combining Google Fonts with HTML formatting:</b>
   • <code>{{{filename}Roboto:700}bold}</code> - Bold Roboto with HTML bold</blockquote>

6. <b>Combining with unicode emoji:</b>
   • <code>{{{{filename}Roboto:700}bold}🔥}</code> - Bold Roboto with HTML bold and with unicode emoji</blockquote>

<blockquote expandable="expandable"><b>Unlimited Nesting Support:</b>
You can nest styles to any depth with any combination of styles!

1. <b>Basic Nesting (Two Styles):</b>
   • <code>{{{variable}style1}style2}</code>
   • Example: <code>{{{filename}bold}italic}</code> - Bold then italic

2. <b>Triple Nesting (Three Styles):</b>
   • <code>{{{{variable}style1}style2}style3}</code>
   • Example: <code>{{{{filename}bold}italic}🔥}</code> - Bold, italic, then fire emoji

3. <b>Advanced Nesting (Four or More Styles):</b>
   • <code>{{{{{variable}style1}style2}style3}style4}</code>
   • Example: <code>{{{{{filename}bold}italic}code}underline}</code> - Four nested styles

4. <b>Master Nesting (Any Number of Styles):</b>
   • You can continue nesting to any depth
   • Example: <code>{{{{{{{{filename}bold}italic}code}underline}strike}🔥}Roboto}</code>
   • Styles are applied from innermost to outermost: bold → italic → code → underline → strike → 🔥 → Roboto</blockquote>

<blockquote expandable="expandable"><b>How to Find Google Fonts:</b>
1. Visit <a href='https://fonts.google.com/'>fonts.google.com</a>
2. Find a font you like
3. Use the exact font name in your leech font setting or caption template</blockquote>

<b>Important Notes:</b>
• Unicode font styles only work with basic Latin characters (A-Z, a-z)
• Google Fonts support depends on the rendering capabilities of the device
• HTML formatting is the most compatible across all devices
• Font styles are applied after template variables are processed
• User settings take priority over owner settings
• Unlimited nesting of styles is supported - combine any number of styles in any order
• For complex nested styles, apply them in order from innermost to outermost"""

ffmpeg_cmds = ffmpeg_help


ai_help = """<b>AI Chatbot</b>:

Chat with AI models using the bot commands.

<b>Available AI Models:</b>
Use the /ask command with any of the following AI providers:
- <b>Mistral AI</b>
- <b>DeepSeek AI</b>

<b>Usage:</b>
/ask your question here

<b>Configuration:</b>
1. <b>Bot Owner</b>: Configure API Keys or API URLs and default AI provider in bot settings
2. <b>Users</b>: Configure your own API Keys or API URLs and default AI provider in user settings

<b>Features:</b>
- Uses powerful language models
- Supports both direct API access and custom API endpoints
- User settings take priority over bot owner settings
- Messages auto-delete after 5 minutes
- Automatically selects the configured AI provider

<b>Examples:</b>
/ask What is the capital of France?
/ask Write a short poem about nature
/ask Explain how quantum computing works
/ask Translate this text to Spanish: Hello world
"""

user_cookies_help = """<b>User Cookies</b>:

You can provide your own cookies for YouTube and other yt-dlp downloads to access restricted content.

1. Go to /usettings > Leech Settings > User Cookies
2. Upload your cookies.txt file (create it using browser extensions)
3. Your cookies will be used for all your yt-dlp downloads

When you upload your cookies, they will be used instead of the owner's cookies. This helps with errors like login requirements or subscriber-only content.

To remove your cookies and use the owner's cookies again, click the Remove button."""

YT_HELP_DICT = {
    "main": yt,
    "New-Name": f"{new_name}\nNote: Don't add file extension",
    "Zip": zip_arg,
    "Quality": qual,
    "Options": yt_opt,
    "Download-Range": download_range,
    "User-Cookies": user_cookies_help,
    "Multi-Link": multi_link,
    "Same-Directory": same_dir,
    "Thumb": thumb,
    "Split-Size": split_size,
    "Upload-Destination": upload,
    "Rclone-Flags": rcf,
    "Bulk": bulk,
    "Sample-Video": sample_video,
    "Screenshot": screenshot,
    "Convert-Media": convert_media,
    "Force-Start": force_start,
    "Name-Substitute": name_sub,
    "TG-Transmission": transmission,
    "Thumb-Layout": thumbnail_layout,
    "Leech-Type": leech_as,
    "FFmpeg-Cmds": ffmpeg_cmds,
    "Media-Tools-Flag": media_tools_flag,
}

# Merge flags guide has been moved to media_tools_help.py

# Watermark guide has been moved to media_tools_help.py

MIRROR_HELP_DICT = {
    "main": mirror,
    "New-Name": new_name,
    "DL-Auth": "<b>Direct link authorization</b>: -au -ap\n\n/cmd link -au username -ap password",
    "Headers": "<b>Direct link custom headers</b>: -h\n\n/cmd link -h key:value|key1:value1",
    "Extract/Zip": extract_zip,
    "Select-Files": "<b>Bittorrent/JDownloader/Sabnzbd File Selection</b>: -s\n\n/cmd link -s or by replying to file/link",
    "Torrent-Seed": seed,
    "Multi-Link": multi_link,
    "Same-Directory": same_dir,
    "Thumb": thumb,
    "Split-Size": split_size,
    "Upload-Destination": upload,
    "Rclone-Flags": rcf,
    "Bulk": bulk,
    "Join": join,
    "Rclone-DL": rlone_dl,
    "Tg-Links": tg_links,
    "Sample-Video": sample_video,
    "Screenshot": screenshot,
    "Convert-Media": convert_media,
    "Force-Start": force_start,
    "User-Download": user_download,
    "Name-Substitute": name_sub,
    "TG-Transmission": transmission,
    "Thumb-Layout": thumbnail_layout,
    "Leech-Type": leech_as,
    "FFmpeg-Cmds": ffmpeg_cmds,
    "Media-Tools-Flag": media_tools_flag,
}

CLONE_HELP_DICT = {
    "main": clone,
    "Multi-Link": multi_link,
    "Bulk": bulk,
    "Gdrive": gdrive,
    "Rclone": rclone_cl,
}

AI_HELP_DICT = {
    "main": ai_help,
}

virustotal_help = """<b>VirusTotal Scanner</b>

Scan files and URLs for viruses and malware using VirusTotal.

<b>Usage:</b>
1. Reply to a file with /virustotal to scan it
2. Reply to a message containing a URL with /virustotal
3. Use /virustotal <url> to scan a URL directly

<b>Features:</b>
• Automatic scanning in private chats (when enabled)
• Manual scanning in groups
• Detailed threat analysis
• Link to full VirusTotal report

<b>Note:</b>
• Maximum file size: 32MB
• Requires a VirusTotal API key to be configured
• Files are temporarily downloaded for scanning and then deleted
"""

VT_HELP_DICT = {
    "main": virustotal_help,
}

# Phish Directory help content
phish_directory_help = """<b>🔍 Phish Directory Security Check</b>

Check domains and emails for phishing, malware, and security threats using the phish.directory API.

<blockquote>
<b>🎯 Features:</b>
• Domain phishing detection
• Email validation and reputation checking
• Fraud score assessment
• Disposable email detection
• DNS validation
• Recent abuse detection
</blockquote>

<blockquote>
<b>📝 Usage:</b>
<code>/phishcheck &lt;domain_or_email&gt;</code>

<b>Examples:</b>
• <code>/phishcheck google.com</code> - Check domain safety
• <code>/phishcheck user@example.com</code> - Validate email
• <code>/phishcheck https://suspicious-site.com</code> - Check URL
• <code>/phishcheck temp@tempmail.org</code> - Check disposable email
</blockquote>

<blockquote>
<b>🛡️ Domain Check Results:</b>
• Safety status (Safe/Malicious)
• Phishing detection
• Risk level assessment
• Detailed security report
</blockquote>

<blockquote>
<b>📧 Email Check Results:</b>
• Format validation
• DNS validity
• Disposable email detection
• Fraud score (0-100)
• Recent abuse history
• First seen date
</blockquote>

<blockquote>
<b>⚠️ Important Notes:</b>
• Results are provided by phish.directory community database
• Always use caution with suspicious domains/emails
• Reports are for informational purposes only
• Service requires internet connection
• <b>Authentication required:</b> Register at https://phish.directory for API access
</blockquote>
"""

PHISH_HELP_DICT = {
    "main": phish_directory_help,
}

# WOT (Web of Trust) help content
wot_help = f"""<b>🛡️ COMPREHENSIVE REPUTATION CHECKER</b>

Check website, domain, and IP reputation using multiple security databases including Web of Trust (WOT) and AbuseIPDB.

<blockquote>
<b>🎯 Features:</b>
• Website trustworthiness assessment (WOT: 0-100 scale)
• IP abuse confidence scoring (AbuseIPDB: 0-100 scale)
• Child safety ratings and threat categorization
• Geographic and ISP information for IPs
• Third-party blacklist detection
• Community-driven reputation scores
• Real-time safety status and risk assessment
• Automatic domain-to-IP resolution for comprehensive analysis
</blockquote></blockquote>

<b>📝 Usage:</b>
<code>/{BotCommands.WotCommand} &lt;website_url_or_domain_or_ip&gt;</code>
<code>/{BotCommands.WotCommand} &lt;target1&gt; &lt;target2&gt; ...</code>
<code>/{BotCommands.WotCommand} &lt;target1,target2,target3&gt;</code>

<b>📋 Examples:</b>
• <code>/{BotCommands.WotCommand} google.com</code> (domain reputation)
• <code>/{BotCommands.WotCommand} https://example.com</code> (URL analysis)
• <code>/{BotCommands.WotCommand} 8.8.8.8</code> (IP reputation)
• <code>/{BotCommands.WotCommand} 2001:4860:4860::8888</code> (IPv6 support)
• <code>/{BotCommands.WotCommand} 192.168.1.0/24</code> (network analysis)
• <code>/{BotCommands.WotCommand} suspicious-site.com</code> (threat analysis)
• <code>/{BotCommands.WotCommand} google.com 8.8.8.8</code> (multiple targets)
• <code>/{BotCommands.WotCommand} site1.com,192.168.1.1,site2.com</code> (mixed types)
• <code>/{BotCommands.WotCommand} ääkkönen.fi</code> (IDN support)

<blockquote>
<b>🔍 WOT Reputation Scale (Domains):</b>
• 80-100: Excellent (🟢)
• 60-79: Good (🟡)
• 40-59: Unsatisfactory (🟠)
• 20-39: Poor (🔴)
• 0-19: Very Poor (⚫)
</blockquote>

<blockquote>
<b>🚨 AbuseIPDB Confidence Scale (IPs):</b>
• 75-100: Critical Risk (🚨) - Recommended for blocking
• 50-74: High Risk (🔴) - Exercise extreme caution
• 25-49: Medium Risk (🟠) - AbuseIPDB minimum threshold
• 1-24: Low Risk (🟡) - Below threshold, minimal concern
• 0: No Reports (🟢) - Clean record
</blockquote>

<blockquote>
<b>⚠️ Important Notes:</b>
• <b>Dual Analysis:</b> Automatically uses both WOT and AbuseIPDB when available
• <b>Smart Resolution:</b> Domains are resolved to IPs for comprehensive analysis
• <b>Network Analysis:</b> Supports CIDR notation for subnet analysis (e.g., 192.168.1.0/24)
• Results are based on community ratings and third-party sources
• Confidence threshold ≥ 10 required for reliable warnings (WOT standard)
• AbuseIPDB minimum threshold: 25% (75%+ recommended for blocking)
• Supports IPv4, IPv6, and Internationalized Domain Names (IDN) per RFC 3490
• Can analyze up to 10 targets per request
• Always exercise caution with high-risk targets
• Reports are for informational purposes only
• Service requires internet connection
• <b>Authentication required:</b>
  - WOT: Register at https://www.mywot.com/developers
  - AbuseIPDB: Register at https://www.abuseipdb.com/api
</blockquote>
"""

WOT_HELP_DICT = {
    "main": wot_help,
}

# Trace.moe help content
trace_moe_help = """<b>🔍 Trace.moe Anime Identification</b>

Identify anime scenes from images, videos, or GIFs using the trace.moe API.

<blockquote>
<b>🎯 Features:</b>
• Multi-language anime titles (Japanese, Romaji, English, Chinese)
• Video preview of identified scenes
• Support for images, videos, GIFs, and URLs
• Works in both private chats and groups
• Adult content filtering in groups
• High accuracy anime scene matching
</blockquote>

<blockquote>
<b>📱 Usage:</b>
• Send <code>/trace</code> with an image, video, or GIF
• Reply to media with <code>/trace</code>
• Send image URLs directly in text messages
• Maximum file size: 10MB (configurable)
</blockquote>

<blockquote>
<b>📋 Sample Output:</b>
🎌 <b>Anime Identified</b>

📺 <b>Titles:</b>
   🔸 <b>進撃の巨人</b>
   ▫️ <i>Shingeki no Kyojin</i>
   ▫️ <i>Attack on Titan</i>

📁 <b>Source Info:</b>
   📄 File: <code>attack_on_titan_s1_ep1.mkv</code>
   ⏰ Time: <code>02:05</code>

🎯 <b>Match Accuracy:</b>
   🎯 <b>95.0%</b> (Excellent)

<b>⚠️ Important:</b> Results below 90% similarity are usually incorrect according to trace.moe official guidelines.

Plus a video preview showing the exact scene!
</blockquote>

<blockquote>
<b>🎬 Supported Media:</b>
• <b>Images:</b> JPG, PNG, WebP, BMP
• <b>Videos:</b> MP4, MKV, AVI, MOV, WebM
• <b>Animations:</b> GIF, animated WebP
• <b>URLs:</b> Direct links to supported media
</blockquote>

<blockquote>
<b>🛡️ Security Features:</b>
• Authentication required (authorized users only)
• Adult content blocked in groups
• File size limits to prevent abuse
• Temporary file cleanup after processing
• Rate limiting with retry logic
</blockquote>

<blockquote>
<b>⚙️ Configuration:</b>
• <code>TRACE_MOE_ENABLED</code>: Enable/disable functionality
• <code>TRACE_MOE_API_KEY</code>: Optional API key for higher quota
• <code>TRACE_MOE_VIDEO_PREVIEW</code>: Enable/disable video previews
• <code>TRACE_MOE_MAX_FILE_SIZE</code>: Maximum file size limit
</blockquote>

<blockquote>
<b>❌ Common Issues:</b>
• <b>"No supported media found":</b> Send an image, video, or GIF
• <b>"File too large":</b> Reduce file size under 10MB
• <b>"You are not authorized":</b> Ask admin for authorization
• <b>"Rate limit exceeded":</b> Wait a few minutes and try again
• <b>"No anime found":</b> Try a clearer screenshot or different frame
</blockquote>

<blockquote>
<b>💡 Pro Tips:</b>
• Use clear, unedited screenshots for best results
• Avoid heavily compressed or watermarked images
• Try different frames if one doesn't work
• Recent anime (2000+) have higher accuracy
• Opening/ending scenes often work well
</blockquote>

<b>Note:</b> Requires authorization to use. Only works with actual anime content, not fan art or heavily edited images."""

TRACE_HELP_DICT = {
    "main": trace_moe_help,
}

# OSINT Help
osint_help = """<b>🔍 OSINT Intelligence Suite</b>

<blockquote>
<b>Comprehensive Open Source Intelligence Tools</b>
All OSINT features consolidated under a single command for advanced investigations.
</blockquote>

<blockquote expandable="expandable">
<b>📱 Phone Number Intelligence:</b>
<code>/osint number &lt;phone_number&gt;</code>

• Advanced phone tracing via multiple sources
• Owner details and SIM card information
• IMEI and MAC address tracking
• Location and carrier information
• Complaint history and tracking data
• International format support

<b>Example:</b> <code>/osint number 919999999999</code>
</blockquote>

<blockquote expandable="expandable">
<b>🌐 IP Address Geolocation:</b>
<code>/osint ip &lt;ip_address&gt;</code>

• Comprehensive IP intelligence
• Country, city, and ISP details
• Proxy/VPN/mobile detection
• Coordinates and timezone
• Organization information

<b>Example:</b> <code>/osint ip 8.8.8.8</code>
</blockquote>

<blockquote expandable="expandable">
<b>🏦 Bank IFSC Code Lookup:</b>
<code>/osint ifsc &lt;ifsc_code&gt;</code>

• Complete bank and branch information
• Address and contact details
• MICR codes and email
• State and district data

<b>Example:</b> <code>/osint ifsc SBIN0000001</code>
</blockquote>

<blockquote expandable="expandable">
<b>🚗 Vehicle Information:</b>
<code>/osint vehicle &lt;vehicle_number&gt;</code>

• Registration details and RTO office
• Vehicle specifications and owner type
• Insurance and PUC status
• 500+ RTO offices mapped across India
• Intelligent fallback analysis

<b>Example:</b> <code>/osint vehicle MH01AB1234</code>
</blockquote>

<blockquote expandable="expandable">
<b>📧 Advanced Email OSINT:</b>
<code>/osint email &lt;email_address&gt;</code>

• Breach database analysis
• Social media profile discovery
• Domain intelligence and MX records
• Provider security analysis
• Risk assessment and creation estimation
• Professional investigation tips

<b>Example:</b> <code>/osint email example@gmail.com</code>
</blockquote>

<blockquote expandable="expandable">
<b>👤 User Lookup & Analysis:</b>
<code>/osint user &lt;user_id_or_username&gt;</code>

• Deep Telegram user analysis
• Account creation estimation
• Privacy analysis and activity patterns
• Cross-platform search suggestions
• Username availability checking

<b>Examples:</b>
<code>/osint user 123456789</code>
<code>/osint user @username</code>
</blockquote>

<blockquote expandable="expandable">
<b>🔍 Advanced Username Scanner:</b>
<code>/osint scan &lt;username&gt;</code>

• 50+ website coverage
• Real-time verification across platforms
• Social media, professional networks, gaming
• Progress tracking and detailed reports
• Comprehensive availability analysis

<b>Example:</b> <code>/osint scan johndoe</code>
</blockquote>

<b>🔒 Privacy & Ethics:</b>
• All tools respect privacy policies
• Educational purposes only
• Responsible OSINT practices
• No data storage or logging

<b>Note:</b> This command is restricted to sudo users only for security purposes."""

OSINT_HELP_DICT = {
    "main": osint_help,
}

NSFW_HELP_DICT = {
    "main": nsfw_detection_help,
}

# Link Shortener Help
shortner_help = """<b>🔗 Link Shortener with Multi-API Support</b>

<b>📝 Description:</b>
Shorten URLs using Bitly or TinyURL APIs with automatic fallback. Bitly provides QR code generation while TinyURL offers fast, reliable shortening. Perfect for sharing links with tracking capabilities and easy mobile access.

<b>🎯 Usage:</b>
• <code>/shortner &lt;url&gt; [custom_alias]</code> - Shorten URL with optional custom alias
• Reply to any message containing a URL with <code>/shortner [custom_alias]</code>

<b>✨ Features:</b>
• <b>Bitly:</b> Professional QR code generation + analytics
• <b>TinyURL:</b> Fast, reliable shortening + analytics
• Custom alias support (alphanumeric, hyphens, underscores)
• Automatic fallback between APIs
• Click tracking via respective dashboards
• Automatic URL validation
• Mobile-optimized design

<b>📱 Examples:</b>
• <code>/shortner https://example.com</code> - Basic shortening
• <code>/shortner https://example.com my-link</code> - With custom alias
• <code>/shortner https://github.com/user/repo project-repo</code> - GitHub link with alias

<b>🎨 QR Code Features:</b>
• High-resolution PNG format
• Professional Bitly branding
• Optimized for mobile scanning
• Works with all QR code readers
• Embedded link information

<b>🔧 Custom Alias Rules:</b>
• Maximum 50 characters
• Alphanumeric characters only (a-z, A-Z, 0-9)
• Hyphens (-) and underscores (_) allowed
• Must be unique across Bitly
• Case-sensitive

<b>📊 Analytics:</b>
• Click tracking available on Bitly dashboard
• Geographic data and referrer information
• Real-time statistics
• Historical data retention

<b>⚠️ Requirements:</b>
• At least one API token must be configured:
  - BITLY_ACCESS_TOKEN (for QR codes + analytics)
  - TINYURL_API_TOKEN (for fast shortening + analytics)
• Internet connection required
• Valid URL format required
• Optional: BITLY_GROUP_GUID for Bitly organization accounts

<b>🛡️ Privacy &amp; Security:</b>
• Links processed through secure Bitly API
• No local storage of URLs
• Professional link management
• Spam and malware protection via Bitly

<b>💡 Pro Tips:</b>
• Use descriptive custom aliases for better organization
• QR codes work great for print materials and presentations
• Shortened links never expire
• Perfect for social media sharing
• Track performance through Bitly analytics

<b>📋 Note:</b> This feature requires Bitly API configuration by the administrator."""

SHORTNER_HELP_DICT = {
    "main": shortner_help,
}

# Streamrip help content
streamrip_main = """<b>🎵 Streamrip Downloads</b>

Download high-quality music from streaming platforms like Qobuz, Tidal, Deezer, and SoundCloud.

<b>Commands:</b>
• <code>/srm</code>, <code>/srmirror</code> or <code>/streamripmirror</code> - Mirror music to cloud storage
• <code>/srl</code>, <code>/srleech</code> or <code>/streamripleech</code> - Leech music to Telegram
• <code>/srs</code>, <code>/srsearch</code> or <code>/streamripsearch</code> - Search for music across platforms

<b>Supported Platforms:</b>
• <b>Qobuz</b> - Up to Hi-Res+ quality (24-bit/192kHz) - Quality levels 0-4
• <b>Tidal</b> - Up to Hi-Res/MQA quality (24-bit/96kHz) - Quality levels 0-3
• <b>Deezer</b> - Up to CD quality (16-bit/44.1kHz) - Quality levels 0-2
• <b>SoundCloud</b> - Up to 320 kbps - Quality levels 0-1

<b>Input Types:</b>
• Direct URLs from supported platforms
• ID format: <code>platform:type:id</code> (e.g., <code>qobuz:album:123456</code>)
• Last.fm playlist URLs (converted to source platforms)
• Batch files (text/JSON with multiple URLs/IDs)

<b>Quality Levels:</b>
• <b>0</b> - 128 kbps (~4MB/track)
• <b>1</b> - 320 kbps (~10MB/track)
• <b>2</b> - CD Quality 16-bit/44.1kHz (~35MB/track)
• <b>3</b> - Hi-Res 24-bit/≤96kHz (~80MB/track)
• <b>4</b> - Hi-Res+ 24-bit/≤192kHz (~150MB/track)

<b>Note:</b> Higher quality levels require premium subscriptions on respective platforms."""

streamrip_quality_flags = """<b>🎯 Quality & Format Flags</b>

Control the quality and format of your music downloads.

<b>Quality Selection:</b>
• <code>-q &lt;0-4&gt;</code> - Set quality level
  - <code>-q 0</code> - 128 kbps (smallest files)
  - <code>-q 1</code> - 320 kbps (good quality)
  - <code>-q 2</code> - CD Quality (lossless)
  - <code>-q 3</code> - Hi-Res (studio quality)
  - <code>-q 4</code> - Hi-Res+ (maximum quality)

<b>Codec Selection:</b>
• <code>-c &lt;codec&gt;</code> - Set audio codec
  - <code>-c flac</code> - Lossless compression (recommended)
  - <code>-c mp3</code> - Lossy compression, smaller files
  - <code>-c m4a</code> - Apple's format, good quality
  - <code>-c ogg</code> - Open source, good compression
  - <code>-c opus</code> - Modern codec, excellent quality

<b>Examples:</b>
• <code>/srm https://qobuz.com/album/... -q 3 -c flac</code>
• <code>/srl qobuz:album:123456 -q 2</code>
• <code>/srm -q 4 -c flac</code> (reply to URL)

<b>Platform Compatibility:</b>
• <b>Qobuz:</b> All quality levels (0-4)
• <b>Tidal:</b> Levels 0-3 (MQA support)
• <b>Deezer:</b> Levels 0-2 (HiFi subscription required for 2)
• <b>SoundCloud:</b> Levels 0-1 (free platform)"""

streamrip_download_flags = """<b>📁 Download Control Flags</b>

Customize how your music downloads are handled.

<b>File Naming:</b>
• <code>-n &lt;name&gt;</code> - Custom filename/folder name
  - <code>/srmirror url -n "My Album Collection"</code>
  - <code>/srleech url -n "Artist - Album (Year)"</code>

<b>Upload Control (Mirror only):</b>
• <code>-up gd</code> - Upload to Google Drive
• <code>-up rc</code> - Upload to Rclone cloud storage
• <code>-up yt</code> - Upload to YouTube (video files only)
• <code>-up mg</code> - Upload to MEGA.nz cloud storage
• <code>-up &lt;path&gt;</code> - Custom upload path for Rclone
• <code>-rcf &lt;flags&gt;</code> - Custom rclone flags

<b>Telegram Upload (Leech only):</b>
• <code>-thumb &lt;url&gt;</code> - Custom thumbnail URL
• <code>-sp &lt;size&gt;</code> - Split size for large files
• <code>-cap &lt;caption&gt;</code> - Custom caption for uploads

<b>File Selection:</b>
• <code>-s</code> - Select specific files from multi-track downloads
• <code>-e &lt;extensions&gt;</code> - Exclude file extensions

<b>Upload Type:</b>
• <code>-doc</code> - Upload as document
• <code>-med</code> - Upload as media

<b>MEGA Upload Examples:</b>
• <code>/mirror https://example.com/file.zip -up mg</code> - Upload to MEGA.nz
• <code>/leech https://example.com/video.mp4</code> - Download to Telegram
• <code>/mirror magnet:?xt=... -up mg</code> - Mirror torrent to MEGA.nz

<b>Headers & Authentication:</b>
• <code>-h &lt;headers&gt;</code> - Custom headers (key:value|key1:value1)

<b>Examples:</b>
• <code>/srm url -n "Jazz Collection" -up "Music/Jazz"</code>
• <code>/srl url -sp 2GB -doc -cap "High Quality Music"</code>"""

streamrip_search_flags = """<b>🔍 Search Options</b>

Search for music across supported platforms and download results.

<b>Platform Selection:</b>
• <code>-p &lt;platform&gt;</code> or <code>-platform &lt;platform&gt;</code> - Search specific platform
  - <code>-p qobuz</code> - Search Qobuz only
  - <code>-p tidal</code> - Search Tidal only
  - <code>-p deezer</code> - Search Deezer only
  - <code>-p soundcloud</code> - Search SoundCloud only

<b>Media Type Filter:</b>
• <code>-t &lt;type&gt;</code> or <code>-type &lt;type&gt;</code> - Filter by media type
  - <code>-t track</code> - Search for individual songs
  - <code>-t album</code> - Search for full albums
  - <code>-t artist</code> - Search for artist profiles
  - <code>-t playlist</code> - Search for playlists

<b>Result Control:</b>
• <code>-f</code> or <code>-first</code> - Download first result automatically
• <code>-n &lt;number&gt;</code> or <code>-num &lt;number&gt;</code> - Limit number of results

<b>Examples:</b>
• <code>/srs Daft Punk Random Access Memories</code> - Search all platforms
• <code>/srs -p qobuz -t album Beethoven Symphony</code> - Search Qobuz albums only
• <code>/srs -f -p tidal The Weeknd Blinding Lights</code> - Auto-download first Tidal result
• <code>/srs -t artist -n 5 Miles Davis</code> - Show 5 artist results

<b>Note:</b> Search results show platform availability and quality levels for each result."""

streamrip_control_flags = """<b>🔧 Control Flags</b>

Fine-tune your streamrip downloads with available options.

<b>Force Operations:</b>
• <code>-f</code> - Force run (bypass some checks)
• <code>-fd</code> - Force download (ignore cache/database)

<b>Upload Options (Leech only):</b>
• <code>-doc</code> - Upload as document (preserves quality)
• <code>-med</code> - Upload as media (Telegram compression)
• <code>-thumb &lt;url&gt;</code> - Custom thumbnail URL
• <code>-sp &lt;size&gt;</code> - Split size for large files
• <code>-cap &lt;caption&gt;</code> - Custom caption for uploads

<b>Cloud Integration (Mirror only):</b>
• <code>-up &lt;destination&gt;</code> - Upload destination
  - <code>-up gd</code> - Upload to Google Drive
  - <code>-up "Music/Streamrip"</code> - Custom path
• <code>-rcf &lt;flags&gt;</code> - Custom rclone flags

<b>File Selection:</b>
• <code>-s</code> - Select specific files from multi-track downloads
• <code>-e &lt;extensions&gt;</code> - Exclude file extensions

<b>Examples:</b>
• <code>/srm url -f -up "Music/Jazz"</code>
• <code>/srl url -doc -sp 2GB -cap "High Quality Music"</code>
• <code>/srm url -fd -rcf "--transfers:8"</code>

<b>Tips:</b>
• Use <code>-doc</code> for lossless audio preservation in Telegram
• Use <code>-s</code> for large albums to select specific tracks
• Use <code>-fd</code> to re-download previously downloaded content"""

streamrip_examples = """<b>📋 Usage Examples</b>

Real-world examples of streamrip commands for different scenarios.

<b>🎵 Basic Downloads:</b>
• <code>/srm https://qobuz.com/album/xyz</code>
• <code>/srl https://tidal.com/browse/track/123</code>
• <code>/srs Daft Punk Random Access Memories</code>

<b>🎯 Quality-Focused Downloads:</b>
• <code>/srm qobuz:album:123456 -q 4 -c flac</code>
• <code>/srl tidal:album:789012 -q 3 -doc</code>
• <code>/srm url -q 2 -c flac -n "Lossless Collection"</code>

<b>📁 Organized Downloads:</b>
• <code>/srm url -n "Artist - Album (2023)" -up "Music/2023"</code>
• <code>/srl url -n "Jazz Essentials" -cap "High Quality Jazz"</code>

<b>🔍 Search Examples:</b>
• <code>/srs -p qobuz -t album Beethoven Symphony</code>
• <code>/srs -f -p tidal The Weeknd Blinding Lights</code>
• <code>/srs -t artist -n 5 Miles Davis</code>

<b>📦 Batch Processing:</b>
• Upload a text file with multiple URLs and use:
• <code>/srm -q 3 -c flac</code> (reply to file)
• <code>/srl -doc -sp 2GB</code> (reply to file)

<b>🔍 Advanced Selection:</b>
• <code>/srm url -s -e "log,cue"</code>
• <code>/srl url -s -doc -thumb "https://image.url"</code>

<b>☁️ Cloud Integration:</b>
• <code>/srm url -up "Music/Streamrip" -rcf "--transfers:8"</code>
• <code>/srm url -up gd -n "My Collection"</code>

<b>🎧 Platform-Specific Examples:</b>
• <code>/srm qobuz:album:123456 -q 4 -c flac</code> - Qobuz Hi-Res+
• <code>/srl tidal:track:789012 -q 3 -doc</code> - Tidal MQA
• <code>/srm deezer:playlist:345678 -q 2 -c mp3</code> - Deezer CD quality
• <code>/srl soundcloud:user/track -q 1 -c mp3</code> - SoundCloud 320kbps

<b>💡 Pro Tips:</b>
• Use ID format (platform:type:id) for direct access
• Use batch files for downloading entire discographies
• Select specific tracks from large albums with <code>-s</code>
• Use <code>-doc</code> for preserving audio quality in Telegram
• Use <code>-f</code> flag to bypass download checks when needed"""

streamrip_platforms = """<b>🎵 Platform Support & Features</b>

Detailed information about supported streaming platforms and their capabilities.

<b>🎯 Qobuz (Premium Recommended):</b>
• <b>Quality Levels:</b> 0-4 (up to 24-bit/192kHz)
• <b>Formats:</b> FLAC, MP3, M4A
• <b>Features:</b> Hi-Res audio, extensive classical catalog
• <b>Requirements:</b> Premium subscription for Hi-Res
• <b>Best For:</b> Audiophiles, classical music, jazz

<b>🌊 Tidal (HiFi/HiFi Plus):</b>
• <b>Quality Levels:</b> 0-3 (up to MQA 24-bit/96kHz)
• <b>Formats:</b> FLAC, MQA, AAC, MP3
• <b>Features:</b> MQA support, exclusive content
• <b>Requirements:</b> HiFi subscription for lossless
• <b>Best For:</b> Hip-hop, R&B, exclusive releases

<b>🎶 Deezer (HiFi):</b>
• <b>Quality Levels:</b> 0-2 (up to 16-bit/44.1kHz)
• <b>Formats:</b> FLAC, MP3, M4A
• <b>Features:</b> Large catalog, good discovery
• <b>Requirements:</b> HiFi subscription for CD quality
• <b>Best For:</b> Pop music, international content

<b>☁️ SoundCloud (Free/Pro):</b>
• <b>Quality Levels:</b> 0-1 (up to 320 kbps)
• <b>Formats:</b> MP3, AAC
• <b>Features:</b> Independent artists, remixes, podcasts
• <b>Requirements:</b> Free access, Pro for higher quality
• <b>Best For:</b> Independent music, DJ sets, podcasts

<b>🎵 Last.fm Integration:</b>
• <b>Playlist Support:</b> Convert Last.fm playlists to downloads
• <b>Scrobbling Data:</b> Use listening history for downloads
• <b>Discovery:</b> Find similar tracks and artists

<b>📋 Input Format Examples:</b>
• <b>Direct URLs:</b>
  - <code>https://qobuz.com/album/xyz</code>
  - <code>https://tidal.com/browse/track/123</code>
  - <code>https://deezer.com/album/456</code>
  - <code>https://soundcloud.com/artist/track</code>

• <b>ID Format:</b>
  - <code>qobuz:album:123456</code>
  - <code>tidal:track:789012</code>
  - <code>deezer:playlist:345678</code>
  - <code>soundcloud:user:901234</code>

• <b>Last.fm URLs:</b>
  - <code>https://last.fm/user/username/playlists/123</code>

<b>💡 Platform Tips:</b>
• Use Qobuz for highest quality classical and jazz
• Tidal excels for hip-hop and exclusive content
• Deezer offers great international music discovery
• SoundCloud is perfect for independent and remix content"""

STREAMRIP_HELP_DICT = {
    "main": streamrip_main,
    "Quality-Flags": streamrip_quality_flags,
    "Download-Flags": streamrip_download_flags,
    "Search-Options": streamrip_search_flags,
    "Control-Flags": streamrip_control_flags,
    "Examples": streamrip_examples,
    "Platforms": streamrip_platforms,
}

# Gallery-dl help content
gallery_dl_main = """<b>🖼️ Gallery-dl Downloads</b>

Download images, videos, and media from 200+ platforms including social media, art sites, and image boards.

<b>Commands:</b>
• <code>/gdlmirror</code> or <code>/gm</code> - Download and upload to cloud
• <code>/gdlleech</code> or <code>/gl</code> - Download and send to Telegram

<b>Basic Usage:</b>
<code>/gdlmirror https://www.instagram.com/p/ABC123/</code>
<code>/gl https://twitter.com/user/status/123456</code>

<b>Supported Platforms:</b>
• <b>Social Media:</b> Instagram, Twitter, Reddit, Tumblr, Discord, Pinterest
• <b>Art Platforms:</b> DeviantArt, Pixiv, ArtStation, Behance, Flickr
• <b>Image Hosts:</b> Imgur, Catbox, GoFile, Bunkr, Cyberdrop
• <b>Booru Sites:</b> Danbooru, Gelbooru, Konachan, Yande.re
• <b>Subscription:</b> Patreon, Pixiv Fanbox
• <b>Manga/Comics:</b> MangaDex, Webtoons, Dynasty Scans
• <b>And 180+ more platforms!</b>

<b>Features:</b>
• Quality selection for supported platforms
• Batch downloads (galleries, profiles, collections)
• Authentication support for private content
• Metadata extraction and archiving
• Rate limiting to prevent bans
• Archive management to avoid duplicates"""

gallery_dl_quality = """<b>🎨 Quality Selection</b>

Gallery-dl supports quality selection for many platforms:

<b>Instagram:</b>
• Original - Full resolution images/videos
• High - High quality (1080p)
• Medium - Medium quality (720p)
• Low - Low quality (480p)

<b>Twitter:</b>
• Original - Full resolution media
• Large - Large size images
• Medium - Medium size images
• Small - Small size images

<b>Pixiv:</b>
• Original - Full resolution artwork
• Large - Large size images
• Medium - Medium size images
• Square - Square thumbnails

<b>Danbooru/Gelbooru:</b>
• Original - Full resolution images
• Sample - Sample size images
• Preview - Preview thumbnails

<b>Usage:</b>
The bot will automatically show quality options for supported platforms when you use gallery-dl commands."""

gallery_dl_options = """<b>⚙️ Gallery-dl Options</b>

<b>Archive Management:</b>
• <code>--archive</code> - Enable archive to avoid re-downloading
• <code>--no-archive</code> - Disable archive (download duplicates)

<b>Download Control:</b>
• <code>--limit N</code> - Limit downloads to N files
• <code>--offset N</code> - Skip first N files
• <code>--range START-END</code> - Download specific range

<b>Authentication:</b>
• <code>--cookies FILE</code> - Use cookies file
• <code>--username USER</code> - Login username
• <code>--password PASS</code> - Login password

<b>Output Control:</b>
• <code>--metadata</code> - Save metadata files
• <code>--no-metadata</code> - Skip metadata
• <code>--write-info-json</code> - Save info JSON

<b>Examples:</b>
<code>/gm https://imgur.com/a/abc123 --limit 10</code>
<code>/gl https://reddit.com/r/pics --archive --metadata</code>"""

gallery_dl_examples = """<b>📝 Gallery-dl Examples</b>

<b>Instagram:</b>
<code>/gm https://www.instagram.com/p/ABC123/</code> - Single post
<code>/gl https://www.instagram.com/username/</code> - User profile

<b>Twitter:</b>
<code>/gm https://twitter.com/user/status/123456</code> - Single tweet
<code>/gl https://twitter.com/username/media</code> - User media

<b>Reddit:</b>
<code>/gm https://reddit.com/r/pics/comments/abc123/</code> - Single post
<code>/gl https://reddit.com/r/EarthPorn/top/</code> - Subreddit top posts

<b>Pixiv:</b>
<code>/gm https://www.pixiv.net/artworks/123456</code> - Single artwork
<code>/gl https://www.pixiv.net/users/123456</code> - Artist profile

<b>Imgur:</b>
<code>/gm https://imgur.com/a/abc123</code> - Album
<code>/gl https://imgur.com/gallery/abc123</code> - Gallery

<b>DeviantArt:</b>
<code>/gm https://www.deviantart.com/artist/art/title-123456</code> - Single art
<code>/gl https://www.deviantart.com/artist/gallery/</code> - Artist gallery

<b>With Options:</b>
<code>/gm https://imgur.com/a/abc123 --limit 5 --archive</code>
<code>/gl https://reddit.com/r/pics --metadata --range 1-10</code>"""

gallery_dl_platforms = """<b>🌐 Supported Platforms (200+)</b>

<b>🔥 Popular Platforms:</b>
• Instagram, Twitter, Reddit, Tumblr, Discord
• DeviantArt, Pixiv, ArtStation, Behance
• Imgur, Catbox, GoFile, Bunkr
• YouTube (images/thumbnails), TikTok
• Pinterest, Flickr, 500px

<b>🎨 Art & Design:</b>
• Pixiv, DeviantArt, ArtStation, Behance
• Newgrounds, FurAffinity, Weasyl
• Derpibooru, e926, Inkbunny



<b>💰 Subscription Platforms:</b>
• Patreon, Pixiv Fanbox, Fantia
• SubscribeStar, Boosty, Ci-en

<b>📚 Manga & Comics:</b>
• MangaDex, Webtoons, Batoto
• Dynasty Scans, Hentai2Read
• Hitomi, Tsumino

<b>🌍 Regional Platforms:</b>
• Bilibili, Weibo, Baidu
• VK, Yandex, Mail.ru
• Naver, Daum, DCInside

<b>📁 File Hosts:</b>
• Catbox, GoFile, Bunkr, Cyberdrop
• Erome, Fapello, ImageBam
• PostImg, ImgBox, ImageVenue

<b>💬 Forums & Boards:</b>
• 4chan, 8chan, 2ch, ArcaLive
• FoolFuuka archives
• Various imageboards

<b>🎵 Music Platforms:</b>
• SoundCloud, Bandcamp
• Last.fm, MusicBrainz

<b>And many more!</b> Gallery-dl supports over 200 platforms with regular updates."""

GALLERY_DL_HELP_DICT = {
    "main": gallery_dl_main,
    "Quality": gallery_dl_quality,
    "Options": gallery_dl_options,
    "Examples": gallery_dl_examples,
    "Platforms": gallery_dl_platforms,
    "New-Name": f"{new_name}\nNote: Don't add file extension",
    "Zip": zip_arg,
    "Upload-Destination": upload,
    "Rclone-Flags": rcf,
    "Same-Directory": same_dir,
    "Thumb": thumb,
    "Split-Size": split_size,
    "Bulk": bulk,
}

# Zotify help content
zotify_main = """<b>🎵 Zotify Downloads</b>

Download high-quality music directly from Spotify using your Premium account.

<b>Commands:</b>
• <code>/zm</code>, <code>/zotifymirror</code> - Mirror music to cloud storage
• <code>/zl</code>, <code>/zotifyleech</code> - Leech music to Telegram
• <code>/zs</code>, <code>/zotifysearch</code> - Search Spotify and download

<b>Supported Content:</b>
• <b>Tracks</b> - Individual songs with full metadata
• <b>Albums</b> - Complete albums with artwork
• <b>Playlists</b> - Public and private playlists
• <b>Artists</b> - Artist discographies and top tracks
• <b>Podcasts</b> - Episodes and complete shows
• <b>Personal Collections</b> - Your liked tracks, saved playlists

<b>Audio Quality:</b>
• <b>OGG Vorbis</b> - Native Spotify format (320kbps)
• <b>FLAC</b> - Lossless conversion (16-bit/44.1kHz)
• <b>MP3</b> - Universal compatibility (320kbps)
• <b>AAC</b> - High efficiency (256kbps)

<b>Requirements:</b>
• <b>Spotify Premium</b> account (mandatory)
• Valid credentials uploaded to bot
• Active internet connection

<b>Authentication:</b>
Upload credentials via: Bot Settings → Zotify → Authentication"""

zotify_quality_flags = """<b>🎧 Quality & Format Flags</b>

Control the audio quality and format of your downloads.

<b>Quality Levels:</b>
• <code>-q auto</code> - Automatic quality selection (default)
• <code>-q normal</code> - Standard quality (96kbps)
• <code>-q high</code> - High quality (160kbps)
• <code>-q very_high</code> - Premium quality (320kbps)

<b>Audio Formats:</b>
• <code>-f vorbis</code> - OGG Vorbis (native Spotify format)
• <code>-f mp3</code> - MP3 (universal compatibility)
• <code>-f flac</code> - FLAC (lossless conversion)
• <code>-f aac</code> - AAC (high efficiency)
• <code>-f fdk_aac</code> - FDK-AAC (premium encoder)
• <code>-f opus</code> - Opus (modern codec)
• <code>-f wav</code> - WAV (uncompressed)
• <code>-f wavpack</code> - WavPack (lossless compression)

<b>Artwork Options:</b>
• <code>-a small</code> - Small artwork (300x300)
• <code>-a medium</code> - Medium artwork (640x640)
• <code>-a large</code> - Large artwork (1280x1280, default)

<b>Examples:</b>
• <code>/zm url -q very_high -f flac -a large</code>
• <code>/zl playlist -q high -f mp3</code>
• <code>/zm artist -q auto -f vorbis</code>

<b>Quality Notes:</b>
• Premium account required for high/very_high quality
• FLAC conversion maintains original quality
• Vorbis provides best size/quality ratio"""

zotify_download_flags = """<b>📁 Download Control Flags</b>

Customize how your Spotify downloads are handled.

<b>File Naming:</b>
• <code>-n &lt;name&gt;</code> - Custom filename/folder name
  - <code>/zm album -n "My Favorite Album"</code>
  - <code>/zl playlist -n "Workout Mix 2024"</code>

<b>Metadata Options:</b>
• <code>-metadata</code> - Save metadata tags (default: enabled)
• <code>-genre</code> - Include genre information
• <code>-lyrics</code> - Download lyrics as .lrc files
• <code>-lyrics-only</code> - Download only lyrics (no audio)

<b>Download Behavior:</b>
• <code>-real-time</code> - Download at playback speed (more stable)
• <code>-replace</code> - Replace existing files
• <code>-skip-dup</code> - Skip duplicate tracks
• <code>-match</code> - Match existing files for skip functionality

<b>Output Templates:</b>
• <code>-output-single &lt;template&gt;</code> - Custom format for single tracks
  - Variables: {artists}, {title}, {album}, {track_number}
  - Example: <code>-output-single "{artists} - {title}"</code>

<b>Special Features:</b>
• <code>-ss</code> - Take screenshot of track/album
• <code>-playlist-file</code> - Create .m3u playlist files

<b>Examples:</b>
• <code>/zm url -n "Jazz Collection" -metadata -genre</code>
• <code>/zl playlist -lyrics -skip-dup</code>
• <code>/zm album -real-time -replace</code>"""

zotify_special_downloads = """<b>🎯 Special Downloads</b>

Access your personal Spotify collections and special content.

<b>Personal Collections:</b>
• <code>liked-tracks</code> or <code>liked</code> - Your liked songs
• <code>liked-episodes</code> or <code>episodes</code> - Your liked podcast episodes
• <code>followed-artists</code> or <code>followed</code> - Your followed artists
• <code>saved-playlists</code> or <code>playlists</code> - Your saved playlists

<b>Artist Content:</b>
• <code>artist:&lt;id&gt;</code> - Artist discography
• <code>artist-top:&lt;id&gt;</code> - Artist top tracks
• <code>artist-albums:&lt;id&gt;</code> - Artist albums only

<b>Search Downloads:</b>
• <code>/zm search query</code> - Auto-download first result
• <code>/zl artist name</code> - Search and download artist
• <code>/zm "exact song title"</code> - Precise search

<b>URL Formats:</b>
• <code>https://open.spotify.com/track/...</code>
• <code>https://open.spotify.com/album/...</code>
• <code>https://open.spotify.com/playlist/...</code>
• <code>https://open.spotify.com/artist/...</code>
• <code>https://open.spotify.com/show/...</code>
• <code>spotify:track:...</code> (URI format)

<b>Examples:</b>
• <code>/zm liked-tracks -q very_high -f flac</code>
• <code>/zl followed-artists -n "My Artists"</code>
• <code>/zm saved-playlists -metadata -lyrics</code>
• <code>/zl "Bohemian Rhapsody Queen"</code>

<b>Batch Downloads:</b>
• Upload a text file with multiple URLs/queries
• Use <code>/zm</code> or <code>/zl</code> as reply to file
• Each line processed as separate download"""

zotify_examples = """<b>📋 Usage Examples</b>

Real-world examples of Zotify commands for different scenarios.

<b>🎵 Basic Downloads:</b>
• <code>/zm https://open.spotify.com/album/xyz</code>
• <code>/zl https://open.spotify.com/track/123</code>
• <code>/zs Daft Punk Random Access Memories</code>

<b>🎯 Quality-Focused Downloads:</b>
• <code>/zm album -q very_high -f flac -a large</code>
• <code>/zl track -q high -f mp3 -metadata</code>
• <code>/zm playlist -q auto -f vorbis</code>

<b>📁 Organized Downloads:</b>
• <code>/zm album -n "Pink Floyd - Dark Side (1973)"</code>
• <code>/zl playlist -n "Workout Mix" -skip-dup</code>

<b>🎤 Personal Collections:</b>
• <code>/zm liked-tracks -q very_high -f flac</code>
• <code>/zl saved-playlists -metadata -lyrics</code>
• <code>/zm followed-artists -n "My Artists"</code>

<b>📚 Metadata & Lyrics:</b>
• <code>/zm album -metadata -genre -lyrics</code>
• <code>/zl track -lyrics-only</code>
• <code>/zm playlist -lyrics -playlist-file</code>

<b>🔄 Advanced Options:</b>
• <code>/zm large-album -real-time -replace</code>
• <code>/zl compilation -skip-dup -match</code>
• <code>/zm artist -output-single "{artists} - {title}"</code>

<b>📦 Batch Processing:</b>
• Upload a text file with URLs and use:
• <code>/zm -q very_high -f flac</code> (reply to file)
• <code>/zl -metadata -lyrics</code> (reply to file)

<b>🔍 Search & Download:</b>
• <code>/zs Blinding Lights</code> (search and select)
• <code>/zm "The Weeknd Blinding Lights"</code> (auto-download first)
• <code>/zl artist:"Taylor Swift"</code> (artist search)

<b>🎧 Podcast Downloads:</b>
• <code>/zm https://open.spotify.com/show/xyz</code>
• <code>/zl episode -metadata</code>
• <code>/zm liked-episodes -n "My Podcasts"</code>

<b>💡 Pro Tips:</b>
• Use <code>-f flac</code> for archival quality
• Use <code>-real-time</code> for large downloads
• Use <code>-skip-dup</code> to avoid re-downloading
• Use <code>-lyrics</code> for karaoke files"""

zotify_troubleshooting = """<b>🔧 Troubleshooting & Tips</b>

Common issues and solutions for Zotify downloads.

<b>❌ Authentication Issues:</b>
• <b>Problem:</b> "Zotify credentials not configured"
• <b>Solution:</b> Upload credentials via Bot Settings → Zotify → Authentication
• <b>Note:</b> Requires Spotify Premium account

<b>❌ Download Failures:</b>
• <b>Problem:</b> Downloads fail or timeout
• <b>Solution:</b> Use <code>-real-time</code> flag for stability
• <b>Alternative:</b> Try smaller batches or individual tracks

<b>❌ Quality Issues:</b>
• <b>Problem:</b> Low quality despite high settings
• <b>Solution:</b> Ensure Spotify Premium subscription is active
• <b>Check:</b> Account region and content availability

<b>❌ Format Problems:</b>
• <b>Problem:</b> Unsupported format error
• <b>Solution:</b> Use supported formats: vorbis, mp3, flac, aac
• <b>Note:</b> Some formats require transcoding (slower)

<b>✅ Performance Tips:</b>
• Use <code>-q auto</code> for fastest downloads
• Use <code>-f vorbis</code> for best size/quality ratio
• Use <code>-skip-dup</code> to avoid re-downloading
• Use <code>-real-time</code> for large albums/playlists

<b>✅ Quality Optimization:</b>
• <code>-q very_high -f flac</code> for best quality
• <code>-q high -f mp3</code> for compatibility
• <code>-a large</code> for high-resolution artwork

<b>✅ Organization Tips:</b>
• Use descriptive names with <code>-n</code> flag
• Include year/genre in custom names
• Use <code>-metadata</code> for proper tagging
• Use <code>-lyrics</code> for complete music library

<b>🔒 Account Security:</b>
• Keep credentials file secure
• Don't share credentials with others
• Regenerate credentials if compromised
• Use dedicated Spotify account for bot if needed

<b>📊 Content Limitations:</b>
• Some content may be region-locked
• Podcast availability varies by region
• Premium-only content requires active subscription
• Downloaded content for personal use only"""

ZOTIFY_HELP_DICT = {
    "main": zotify_main,
    "Quality-Flags": zotify_quality_flags,
    "Download-Flags": zotify_download_flags,
    "Special-Downloads": zotify_special_downloads,
    "Examples": zotify_examples,
    "Troubleshooting": zotify_troubleshooting,
}

# MusicDL Help Content - Based on actual help text from musicdl.py
musicdl_main = """🎵 <b>Music Download Help</b> (1/7)

<b>Usage:</b> <code>/musicmirror [URL] [options]</code> or <code>/musicleech [URL] [options]</code>

<b>🚀 Quick Start:</b>
• Basic: <code>/mm [URL]</code>
• With format: <code>/mm [URL] -fm mp3</code>
• High quality: <code>/mm [URL] -q 27</code> (Qobuz)
• Custom: <code>/mm [URL] --quality-audio LOSSLESS</code> (Tidal)

<b>🎯 Supported Platforms:</b>
• 🌊 <b>Tidal</b> - High-quality streaming (tidal-dl-ng)
• 🎼 <b>Qobuz</b> - Hi-Res audio streaming (qobuz-dl)
• 🍎 <b>Apple Music</b> - AAC/ALAC streaming (gamdl)
• 🎵 <b>Spotify</b> - Popular streaming (deezspot)
• 🎶 <b>Deezer</b> - FLAC/MP3 streaming (deezspot)

<b>🎛️ Format Options (-fm):</b>
• <code>flac</code> - FLAC (lossless, default)
• <code>mp3</code> - MP3 320kbps
• <code>m4a</code> - AAC format
• <code>opus</code> - Opus format

💡 <b>Tip:</b> All downloads are automatically uploaded to Telegram!"""

musicdl_tidal = """🌊 <b>TIDAL Configuration</b> (2/7)

<b>📊 Quality & Performance:</b>
• <code>--quality-audio QUALITY</code> - Audio quality
  (LOW, HIGH, LOSSLESS, HI_RES_LOSSLESS)
• <code>--downloads-concurrent-max N</code> - Max downloads (1-10)
• <code>--download-delay</code> - Add delays (avoid rate limits)

<b>🎵 Audio Processing:</b>
• <code>--extract-flac</code> - Extract FLAC from MP4
• <code>--lyrics-embed</code> - Embed lyrics in files
• <code>--lyrics-file</code> - Save separate .lrc files
• <code>--metadata-cover-embed</code> - Embed covers

<b>📁 File Management:</b>
• <code>--skip-existing</code> - Skip existing files
• <code>--playlist-create</code> - Create .m3u8 files
• <code>--cover-album-file</code> - Save cover.jpg

<b>🎬 Video Options:</b>
• <code>--video-download</code> - Enable video downloads
• <code>--video-convert-mp4</code> - Convert TS→MP4"""

musicdl_qobuz = """🎼 <b>QOBUZ Configuration</b> (3/7)

<b>📊 Quality Options:</b>
• <code>-q 27</code> - Hi-Res (24-bit >96kHz)
• <code>-q 7</code> - Hi-Res (24-bit ≤96kHz)
• <code>-q 6</code> - CD FLAC (16-bit/44.1kHz)
• <code>-q 5</code> - MP3 320kbps

<b>🎵 Download Options:</b>
• <code>--albums-only</code> - Skip singles/EPs
• <code>--smart-discography</code> - Filter spam albums
• <code>--no-fallback</code> - Disable quality fallback
• <code>--og-cover</code> - Original quality covers

<b>📁 File Organization:</b>
• <code>--folder-format "FORMAT"</code> - Custom folder names
• <code>--track-format "FORMAT"</code> - Custom file names
• <code>--no-cover</code> - Skip cover art
• <code>--no-m3u</code> - Skip playlist files

<b>🔍 Search & Discovery:</b>
• <code>--limit N</code> - Search result limit
• Interactive mode for browsing
• Lucky mode for quick downloads"""

musicdl_apple = """🍎 <b>APPLE MUSIC Configuration</b> (4/7)

<b>🎵 Audio Quality:</b>
• <code>--codec-song CODEC</code> - Song codec
  (aac-legacy, aac, alac, atmos)
• <code>--quality-post best</code> - Post video quality
• <code>--cover-size SIZE</code> - Cover art size

<b>📱 Download Options:</b>
• <code>--save-cover</code> - Save cover as separate file
• <code>--save-playlist</code> - Save M3U8 playlist files
• <code>--overwrite</code> - Overwrite existing files
• <code>--disable-music-video-skip</code> - Include videos

<b>📝 Lyrics & Metadata:</b>
• <code>--synced-lyrics-only</code> - Only synced lyrics
• <code>--no-synced-lyrics</code> - Skip synced lyrics
• <code>--synced-lyrics-format FORMAT</code> - lrc, srt, ttml
• <code>--language LANG</code> - Metadata language

<b>🔧 Advanced Options:</b>
• <code>--download-mode MODE</code> - ytdlp, nm3u8dlre
• <code>--remux-mode MODE</code> - ffmpeg, mp4box
• <code>--temp-path PATH</code> - Temporary files directory"""

musicdl_spotify_deezer = """🎵 <b>SPOTIFY & DEEZER Configuration</b> (5/7)

<b>🎧 Spotify Options:</b>
• <code>--spotify-quality QUALITY</code> - NORMAL, HIGH, VERY_HIGH
• <code>--spotify-recursive-quality</code> - Try lower quality
• <code>--spotify-method-save N</code> - Save method (0-3)
• <code>--spotify-make-zip</code> - Create ZIP files

<b>🎶 Deezer Options:</b>
• <code>--deezer-quality QUALITY</code> - MP3_128, MP3_320, FLAC
• <code>--deezer-recursive-quality</code> - Quality fallback
• <code>--deezer-tags-separator SEP</code> - Tag separator
• <code>--deezer-ensure-premium</code> - Require premium

<b>🔐 Authentication:</b>
• Spotify: Upload <code>spotify_credentials.json</code>
• Deezer: Configure ARL token in bot settings
• Both platforms support recursive downloads

<b>📁 File Management:</b>
• Automatic format detection
• Metadata preservation
• Cover art embedding
• Playlist support"""

musicdl_search = """🔍 <b>SEARCH & DISCOVERY</b> (6/7)

<b>🎯 Search Syntax:</b>
• <code>/mm "artist - song"</code> - Basic search
• <code>/mm "query" -p tidal</code> - Platform-specific
• <code>/mm "query" -p qobuz,tidal</code> - Multiple platforms

<b>🎵 Search Types:</b>
• <code>-type track</code> - Search tracks only
• <code>-type album</code> - Search albums only
• <code>-type playlist</code> - Search playlists only
• <code>-type artist</code> - Search artists

<b>📊 Search Options:</b>
• <code>-limit N</code> - Result limit (default: 20)
• <code>-exact</code> - Exact match search
• <code>-interactive</code> - Interactive selection
• <code>-lucky</code> - Download first result

<b>🔍 Inline Search:</b>
• <code>musicdl:query</code> - Search all platforms
• <code>mdl:query</code> - Short prefix
• Results show platform, quality, and format
• Click to download directly"""

musicdl_troubleshooting = """🔧 <b>TROUBLESHOOTING</b> (7/7)

<b>❌ Common Issues:</b>

<b>Authentication Failed:</b>
• Check credentials in bot settings
• Re-upload authentication files via Private Files
• Verify account subscription status
• Use platform-specific auth commands

<b>Download Failures:</b>
• Try different quality settings
• Enable fallback with <code>--recursive-quality</code>
• Check if content is available in your region
• Verify premium account status

<b>Quality Issues:</b>
• Premium account required for FLAC/Hi-Res
• Some content may not have Hi-Res versions
• Use <code>-q best</code> for automatic selection
• Check platform-specific quality limits

<b>🔍 Debug Options:</b>
• <code>--debug</code> - Enable debug logging
• <code>--verbose</code> - Verbose output
• Check download logs for errors
• Report persistent issues to admin

<b>💡 Tips:</b>
• Use search before downloading unknown content
• Batch downloads may be rate-limited
• Some platforms require VPN for certain regions
• Keep authentication files updated"""

MUSICDL_HELP_DICT = {
    "main": musicdl_main,
    "Tidal": musicdl_tidal,
    "Qobuz": musicdl_qobuz,
    "Apple-Music": musicdl_apple,
    "Spotify-Deezer": musicdl_spotify_deezer,
    "Search": musicdl_search,
    "Troubleshooting": musicdl_troubleshooting,
}

# Tool Commands Help
tool_main = f"""<b>🛠️ Tool Commands</b>

The /tool command provides various media conversion and processing utilities.

<b>📱 Usage:</b>
/{BotCommands.ToolCommand[0]} [tool_type] [options]
/{BotCommands.ToolCommand[1]} [tool_type] [options]

<b>🎬 Media Conversion Tools:</b>
• <code>gif</code> - Convert video to Telegram GIF
• <code>sticker</code> - Convert image/video/text to sticker
• <code>emoji</code> - Convert image/video to emoji
• <code>voice</code> - Convert audio to voice message
• <code>vnote</code> - Convert video to video note (≤1 min)

<b>🖼️ Image Processing Tools:</b>
• <code>remBgImg</code> - Remove image background
• <code>enhFace</code> - Enhance facial features
• <code>resImg</code> - Resize image (shows menu)
• <code>resImg [width] [height]</code> - Resize to specific dimensions

<b>📝 Text Processing Tools:</b>
• <code>countWord</code> - Count words in text
• <code>countChar</code> - Count characters in text
• <code>revText</code> - Reverse text

<b>📦 Other Tools:</b>
• <code>[GitHub_URL]</code> - Download GitHub repo as ZIP

<b>💡 Usage Tips:</b>
• Reply to a file/message when using media tools
• Use /tool without parameters to see detailed help
• Most tools work with various file formats
• Processing time depends on file size and complexity"""

tool_media_conversion = """<b>🎬 Media Conversion Tools</b>

<b>🎞️ GIF Conversion:</b>
<code>/tool gif</code>
• Reply to a video to convert to GIF
• Maximum duration: 10 seconds (optimized for Telegram)
• Output: Animated GIF with optimized palette
• Supports: MP4, AVI, MOV, WebM, etc.

<b>🏷️ Sticker Creation:</b>
<code>/tool sticker</code> (reply to image/video)
<code>/tool sticker [text]</code> (create text sticker)
• Image: Converts to 512x512 WebP sticker
• Video: Creates animated WebP sticker (3 seconds max)
• Text: Creates text sticker with outline
• Output format: WebP (Telegram sticker format)

<b>😀 Emoji Creation:</b>
<code>/tool emoji</code>
• Reply to image or video
• Creates 100x100 WebP emoji
• Video: Animated emoji (3 seconds max)
• Perfect for custom emoji reactions

<b>🎤 Voice Message:</b>
<code>/tool voice</code>
• Reply to any audio file
• Converts to OGG Opus format
• Optimized for voice message quality
• Supports: MP3, WAV, FLAC, M4A, etc.

<b>📹 Video Note:</b>
<code>/tool vnote</code>
• Reply to video (max 1 minute)
• Creates circular video note (240x240)
• Perfect for quick video messages
• Auto-crops to square format"""

tool_image_processing = """<b>🖼️ Image Processing Tools</b>

<b>🎨 Background Removal:</b>
<code>/tool remBgImg</code>
• Reply to any image
• Removes background using color detection
• Output: PNG with transparency
• Works best with solid backgrounds

<b>✨ Face Enhancement:</b>
<code>/tool enhFace</code>
• Reply to image with faces
• Enhances contrast, sharpness, and color
• Applies unsharp mask for better detail
• Output: High-quality JPEG

<b>📐 Image Resizing:</b>
<code>/tool resImg</code> - Shows preset menu
<code>/tool resImg [width] [height]</code> - Custom size

<b>📱 Available Presets:</b>
1. 1:1 DP Square (512×512)
2. 16:9 Widescreen (1920×1080)
3. 9:16 Story (1080×1920)
4. 2:3 Portrait (1080×1620)
5. 1:2 Vertical (1080×2160)
6. 2:1 Horizontal (2160×1080)
7. 3:2 Standard (1920×1280)
8. IG Post (1080×1080)
9. YT Banner (2560×1440)
10. YT Thumb (1280×720)
11. X Header (1500×500)
12. X Post (1200×675)
13. LinkedIn Banner (1584×396)
14. WhatsApp DP (640×640)
15. Small Thumb (320×240)
16. Medium Thumb (640×480)
17. Wide Banner (1920×600)

<b>💡 Custom Resize Examples:</b>
<code>/tool resImg 800 600</code> - Resize to 800×600
<code>/tool resImg 1920 1080</code> - Full HD resolution"""

tool_text_processing = """<b>📝 Text Processing Tools</b>

<b>📊 Word Counter:</b>
<code>/tool countWord</code>
• Reply to text message or text file
• Counts total words in the text
• Also shows character count and lines
• Supports large text files

<b>🔢 Character Counter:</b>
<code>/tool countChar</code>
• Reply to text message or text file
• Counts total characters (with and without spaces)
• Shows word count and line count
• Detailed text statistics

<b>🔄 Text Reverser:</b>
<code>/tool revText</code>
• Reply to text message or text file
• Reverses the entire text string
• Shows both original and reversed text
• Useful for text manipulation

<b>💡 Usage Examples:</b>
• Reply to any text message
• Reply to .txt files
• Provide text after command: <code>/tool countWord Hello World</code>
• Works with any language and special characters

<b>📋 Output Format:</b>
All text tools provide detailed statistics including:
• Word count
• Character count (with/without spaces)
• Line count (where applicable)
• Text preview for long content"""

tool_other_features = """<b>📦 Other Tools & Features</b>

<b>📥 GitHub Repository Download:</b>
<code>/tool [repository_URL]</code>

<b>🔗 Supported URL Formats:</b>
• https://github.com/username/repository
• https://github.com/username/repository.git
• http://github.com/username/repository
• git@github.com:username/repository.git

<b>💡 Examples:</b>
<code>/tool https://github.com/torvalds/linux</code>
<code>/tool https://github.com/microsoft/vscode</code>
<code>/tool git@github.com:AeonOrg/Aeon-MLTB.git</code>

<b>📋 Download Details:</b>
• Downloads the latest main/master branch
• Provides ZIP file with complete repository
• Shows file size and repository name
• Automatic branch detection (main → master fallback)

<b>⚡ Performance Notes:</b>
• Large repositories may take time to download
• File size is displayed before upload
• Temporary files are automatically cleaned up
• Works with both public and accessible private repos

<b>🛡️ Error Handling:</b>
• Invalid URLs are detected and rejected
• Network errors are handled gracefully
• Repository not found errors are reported
• Automatic cleanup on failures

<b>🎯 Use Cases:</b>
• Download source code for analysis
• Backup repositories locally
• Share code with team members
• Quick access to project files"""

TOOL_HELP_DICT = {
    "main": tool_main,
    "Media-Conversion": tool_media_conversion,
    "Image-Processing": tool_image_processing,
    "Text-Processing": tool_text_processing,
    "Other-Features": tool_other_features,
}

# QuickInfo help content
quickinfo_main = """<b>🆔 QuickInfo</b>

Get detailed information about users, bots, groups, and channels instantly.

<b>Commands:</b>
• <code>/quickinfo</code>, <code>/qi</code> - Launch QuickInfo with interactive buttons
• <code>/quickinfo chat</code> - Get current chat information

<b>Features:</b>
• <b>Interactive Buttons</b> - Easy-to-use keyboard for different entity types
• <b>Forwarded Messages</b> - Extract source information from any forwarded message
• <b>Multiple Formats</b> - Choose from detailed, compact, minimal, or rich formatting
• <b>Current Chat Info</b> - Get information about the current chat

<b>Supported Entities:</b>
• <b>Users</b> - Regular users with ID, name, username
• <b>Bots</b> - Bot accounts with detailed information
• <b>Premium Users</b> - Users with Telegram Premium
• <b>Groups</b> - Public and private groups
• <b>Channels</b> - Public and private channels
• <b>Your Chats</b> - Groups and channels you created

<b>Usage:</b>
1. Send <code>/quickinfo</code> to open the interactive menu
2. Click buttons to share users, bots, groups, or channels
3. Forward any message to get source information
4. Use <code>/quickinfo chat</code> for current chat details

<b>Authorization:</b>
This command requires authorization to use."""

quickinfo_buttons = """<b>🎮 Interactive Buttons</b>

The QuickInfo menu provides easy-to-use buttons for different entity types.

<b>User Buttons:</b>
• <b>👤 Users</b> - Share regular Telegram users
• <b>🤖 Bots</b> - Share bot accounts
• <b>⭐ Premium</b> - Share users with Telegram Premium

<b>Group Buttons:</b>
• <b>🌐 Public Group</b> - Share public groups with usernames
• <b>🔒 Private Group</b> - Share private groups without usernames
• <b>👥 Your Groups</b> - Share groups you created

<b>Channel Buttons:</b>
• <b>🌐 Public Channel</b> - Share public channels with usernames
• <b>🔒 Private Channel</b> - Share private channels without usernames
• <b>🌟 Your Channels</b> - Share channels you created

<b>How to Use:</b>
1. Click any button in the QuickInfo menu
2. Select the user/chat from your contacts
3. Receive detailed information instantly

<b>Additional Options:</b>
Use the inline buttons to access help and refresh the menu."""

quickinfo_forwarded = """<b>📤 Forwarded Message Analysis</b>

QuickInfo can extract source information from any forwarded message.

<b>How it Works:</b>
1. Forward any message to the bot
2. QuickInfo automatically detects the forward
3. Extracts and displays source information

<b>Information Extracted:</b>
• <b>User Sources</b> - ID, name, username, premium status
• <b>Chat Sources</b> - ID, name, type, member count
• <b>Channel Sources</b> - ID, name, username, type
• <b>Hidden Sources</b> - When source is hidden or restricted

<b>Supported Forwards:</b>
• Messages from users
• Messages from groups
• Messages from channels
• Messages from bots
• Anonymous forwards (limited info)

<b>Privacy Protection:</b>
When the bot doesn't have access to the source, it will show:
"Looks Like I Don't Have Control Over The User"

This is normal behavior for privacy-protected sources."""

quickinfo_formats = """<b>🎨 Format Styles</b>

QuickInfo displays information in a detailed format by default.

<b>Current Format:</b>

<b>📝 Detailed:</b>
Complete information with all available fields
• Type, ID, Name, Username
• Premium status, member count
• All metadata available

<b>Features:</b>
• Clear and comprehensive display
• All available information shown
• Consistent formatting across all entity types
• Easy to read and understand

<b>Information Displayed:</b>
• Entity type (User, Bot, Group, Channel)
• Unique ID number
• Display name and username
• Premium status (for users)
• Member count (for groups/channels)"""

quickinfo_examples = """<b>📋 Usage Examples</b>

Practical examples of using QuickInfo in different scenarios.

<b>🔍 Basic Usage:</b>
• <code>/quickinfo</code> - Open interactive menu
• <code>/qi</code> - Short command for QuickInfo
• <code>/quickinfo chat</code> - Get current chat info

<b>🎮 Interactive Examples:</b>
1. Send <code>/quickinfo</code>
2. Click "👤 Users" button
3. Select a user from your contacts
4. Receive detailed user information

<b>📤 Forwarded Message Examples:</b>
1. Forward any message to the bot
2. Automatically get source information
3. Works with messages from any chat

<b>💡 Pro Tips:</b>
• Use <code>/quickinfo chat</code> in groups to get group info
• Forward messages to identify anonymous sources
• Works only with authorized users
• Respects bot's permission system

<b>🔐 Privacy Notes:</b>
• Only works with chats the bot can access
• Respects Telegram's privacy settings
• Some information may be limited by permissions"""

# Forward help content
forward_main = """<b>🔄 Message Forwarding</b>

Copy messages between Telegram chats using the bot's forwarding system.

<b>🎯 Manual Forwarding:</b>
<code>/forward source_chat destination_chat [-skip N] [-range START-END]</code>

<b>📝 Examples:</b>
• <code>/forward @source_channel @dest_channel</code>
• <code>/forward -1001234567890 @mychannel</code>
• <code>/forward @source @dest -skip 3</code>
• <code>/forward @source @dest -range 100-200</code>
• <code>/forward @source @dest -skip 2 -range 50-150</code>

<b>🔧 Parameters:</b>
• <b>source_chat</b>: Source chat ID or @username
• <b>destination_chat</b>: Destination chat ID or @username
• <b>-skip N</b>: Skip N messages between each forwarded message (optional)
• <b>-range START-END</b>: Forward specific message range (optional)

<b>⏭️ Skip Pattern Example:</b>
With <code>-skip 3</code>: Forward msg1 → Skip msg2,3,4 → Forward msg5 → Skip msg6,7,8 → Forward msg9...

<b>⚡ Features:</b>
• Copies messages without "Forwarded from" label
• Prevents duplicate forwarding
• Real-time progress updates with cancel button
• Supports all message types (text, media, files)
• Works with groups, channels, supergroups
• Cancellable during execution

<b>🔒 Access Requirements:</b>
• Command is sudo-only
• Bot/user must have access to both chats
• Uses USER_SESSION_STRING for better access"""

forward_automatic = """<b>🤖 Automatic Forwarding</b>

Set up automatic message forwarding from source chats to destination chats.

<b>⚙️ Configuration:</b>
Add these to your config:
<code>FORWARD_SOURCE = "chat1,@channel1,chat2"
FORWARD_DESTINATION = "dest1,@dest_channel"</code>

<b>📋 Examples:</b>
<code>FORWARD_SOURCE = "-1001234567890,@mychannel"
FORWARD_DESTINATION = "@destination_channel"</code>

<b>🔄 How it works:</b>
• Monitors configured source chats
• Automatically copies new messages
• Forwards to all destination chats
• Prevents duplicate forwarding
• Sends completion notifications to owner

<b>✨ Benefits:</b>
• Real-time forwarding
• No manual intervention needed
• Handles all message types
• Database tracking for duplicates
• Owner notifications for monitoring"""

forward_advanced = """<b>🚀 Advanced Features</b>

<b>🎛️ Skip Functionality:</b>
The -skip flag creates a pattern for selective forwarding:
• <code>-skip 3</code>: Forward 1 message, skip 3, forward 1, skip 3, repeat...
• <code>-skip 0</code> or no flag: Forward all messages
• Useful for sampling content or reducing volume
• Optional parameter (default: no skip)

<b>📍 Range Functionality:</b>
The -range flag allows forwarding specific message ranges:
• <code>-range 100-200</code>: Forward messages with IDs 100 to 200
• <code>-range 1-50</code>: Forward first 50 messages by ID
• Works with any valid message ID range
• Can be combined with -skip for selective range forwarding
• Optional parameter (default: recent messages)

<b>🔄 Message Processing:</b>
• Processes messages in chronological order
• Handles media groups (albums) properly
• Supports all Telegram message types
• Maintains message formatting and metadata

<b>📊 Progress Tracking:</b>
• Real-time status updates during forwarding
• Shows forwarded/failed/skipped counts
• Cancel button to stop forwarding mid-process
• Completion notifications to bot owner
• Detailed logging for monitoring

<b>🛡️ Error Handling:</b>
• Automatic FloodWait handling
• Graceful handling of access errors
• Continues processing on individual failures
• Comprehensive error logging

<b>💾 Database Integration:</b>
• Tracks forwarded messages to prevent duplicates
• Stores source/destination mapping
• Supports multiple bot instances
• Efficient duplicate checking"""

forward_troubleshooting = """<b>🔧 Troubleshooting</b>

<b>❌ Common Issues:</b>

<b>1. "Could not resolve chat"</b>
• Check chat ID/username spelling
• Ensure chat exists and is accessible
• Verify bot/user has access to the chat

<b>2. "Access error copying message"</b>
• Bot/user not member of source chat
• Insufficient permissions in chat
• Private chat without conversation history

<b>3. "No messages found"</b>
• Empty source chat
• All messages already forwarded
• Skip count too high

<b>🔍 Debug Steps:</b>
• Check bot logs for detailed errors
• Verify USER_SESSION_STRING is configured
• Test with public channels first
• Ensure DATABASE_URL is set for tracking

<b>⚡ Performance Tips:</b>
• Use USER_SESSION_STRING for better access
• Configure DATABASE_URL for duplicate prevention
• Monitor owner notifications for status
• Check logs for any rate limiting issues

<b>🔒 Security Notes:</b>
• Only sudo users can use manual forwarding
• Automatic forwarding requires proper config
• All activities are logged for monitoring
• Respects Telegram's rate limits and policies"""

FORWARD_HELP_DICT = {
    "main": forward_main,
    "Automatic": forward_automatic,
    "Advanced": forward_advanced,
    "Troubleshooting": forward_troubleshooting,
}

QUICKINFO_HELP_DICT = {
    "main": quickinfo_main,
    "Interactive-Buttons": quickinfo_buttons,
    "Forwarded-Messages": quickinfo_forwarded,
    "Format-Styles": quickinfo_formats,
    "Examples": quickinfo_examples,
}

# File-to-Link help content removed - streaming functionality disabled


RSS_HELP_MESSAGE = """
Use this format to add feed url:
Title1 link (required)
Title2 link -c cmd -inf xx -exf xx
Title3 link -c cmd -d ratio:time -z password

-c command -up mrcc:remote:path/subdir -rcf --buffer-size:8M|key|key:value
-inf For included words filter.
-exf For excluded words filter.
-stv true or false (sensitive filter)

<b>RSS Examples:</b>
Example: Title https://www.rss-url.com -inf 1080 or 720 or 144p|mkv or mp4|hevc -exf flv or web|xxx
This filter will parse links that its titles contain `(1080 or 720 or 144p) and (mkv or mp4) and hevc` and doesn't contain (flv or web) and xxx words. You can add whatever you want.

Another example: -inf  1080  or 720p|.web. or .webrip.|hvec or x264. This will parse titles that contain ( 1080  or 720p) and (.web. or .webrip.) and (hvec or x264). I have added space before and after 1080 to avoid wrong matching. If this `10805695` number in title it will match 1080 if added 1080 without spaces after it.

Filter Notes:
1. | means and.
2. Add `or` between similar keys, you can add it between qualities or between extensions, so don't add filter like this f: 1080|mp4 or 720|web because this will parse 1080 and (mp4 or 720) and web ... not (1080 and mp4) or (720 and web).
3. You can add `or` and `|` as much as you want.
4. Take a look at the title if it has a static special character after or before the qualities or extensions or whatever and use them in the filter to avoid wrong match.
Timeout: 60 sec.
"""

PASSWORD_ERROR_MESSAGE = """
<b>This link requires a password!</b>
- Insert <b>::</b> after the link and write the password after the sign.

<b>Example:</b> link::my password
"""


user_settings_text = {
    # AI Settings
    "DEFAULT_AI_MODEL": "Select the default AI model to use with the /ask command. Examples: gpt-4o, claude-3.5-sonnet, gemini-1.5-pro. Timeout: 60 sec",
    "AI_CONVERSATION_MODE": "Select the AI conversation mode. Options: assistant, code_assistant, artist, analyst, teacher, writer, researcher, translator. Timeout: 60 sec",
    "AI_LANGUAGE": "Select the preferred language for AI responses. Options: en, zh, ru, es, fr, de, ja, ko. Timeout: 60 sec",
    "AI_MAX_HISTORY_LENGTH": "Set the maximum number of messages to keep in conversation history. Example: 50. Set to 0 to disable history. Timeout: 60 sec",
    "AI_DAILY_TOKEN_LIMIT": "Set daily token usage limit per user. Example: 10000. Set to 0 for unlimited. Timeout: 60 sec",
    "AI_MONTHLY_TOKEN_LIMIT": "Set monthly token usage limit per user. Example: 100000. Set to 0 for unlimited. Timeout: 60 sec",
    "AI_DAILY_COST_LIMIT": "Set daily cost limit per user in USD. Example: 5.00. Set to 0.0 for unlimited. Timeout: 60 sec",
    "AI_MONTHLY_COST_LIMIT": "Set monthly cost limit per user in USD. Example: 50.00. Set to 0.0 for unlimited. Timeout: 60 sec",
    # AI Performance Settings
    "AI_MAX_TOKENS": "Set maximum tokens per AI response. Example: 4000. Range: 100-8000. Higher values allow longer responses. Timeout: 60 sec",
    "AI_TEMPERATURE": "Set AI response creativity/randomness. Example: 0.7. Range: 0.0-2.0. Higher values = more creative, lower = more focused. Timeout: 60 sec",
    "AI_TIMEOUT": "Set AI request timeout in seconds. Example: 60. Range: 10-300. Higher values allow more time for complex requests. Timeout: 60 sec",
    "AI_RATE_LIMIT_PER_USER": "Set maximum AI requests per user per hour. Example: 50. Range: 1-100. Set to 0 for unlimited. Timeout: 60 sec",
    # New ChatGPT-Telegram-Bot Features
    "AI_VOICE_TRANSCRIPTION_ENABLED": "Enable/disable voice message transcription using Whisper. Send 'true' to enable or 'false' to disable. Timeout: 60 sec",
    "AI_IMAGE_GENERATION_ENABLED": "Enable/disable AI image generation using DALL-E. Send 'true' to enable or 'false' to disable. Timeout: 60 sec",
    "AI_DOCUMENT_PROCESSING_ENABLED": "Enable/disable document processing and analysis (PDF, text files). Send 'true' to enable or 'false' to disable. Timeout: 60 sec",
    "AI_FOLLOW_UP_QUESTIONS_ENABLED": "Enable/disable automatic follow-up question generation. Send 'true' to enable or 'false' to disable. Timeout: 60 sec",
    "AI_CONVERSATION_EXPORT_ENABLED": "Enable/disable conversation export functionality. Send 'true' to enable or 'false' to disable. Timeout: 60 sec",
    "AI_TYPEWRITER_EFFECT_ENABLED": "Enable/disable typewriter effect for streaming responses. Send 'true' to enable or 'false' to disable. Timeout: 60 sec",
    "AI_CONTEXT_PRUNING_ENABLED": "Enable/disable intelligent context pruning to manage conversation length. Send 'true' to enable or 'false' to disable. Timeout: 60 sec",
    # AI API Keys
    "OPENAI_API_KEY": "Send your personal OpenAI API key. Leave empty to use the bot owner's API key. Timeout: 60 sec",
    "ANTHROPIC_API_KEY": "Send your personal Anthropic (Claude) API key. Leave empty to use the bot owner's API key. Timeout: 60 sec",
    "GOOGLE_AI_API_KEY": "Send your personal Google AI (Gemini) API key. Leave empty to use the bot owner's API key. Timeout: 60 sec",
    "GROQ_API_KEY": "Send your personal Groq API key. Leave empty to use the bot owner's API key. Timeout: 60 sec",
    "VERTEX_PROJECT_ID": "Send your Google Cloud Vertex AI project ID. Leave empty to use the bot owner's project ID. Timeout: 60 sec",
    "VERTEX_AI_LOCATION": "Send your Google Cloud Vertex AI location/region (e.g., us-central1, europe-west1). Leave empty to use the bot owner's location. Timeout: 60 sec",
    # AI API URLs
    "OPENAI_API_URL": "Send your custom OpenAI API URL. Leave empty to use the default OpenAI API URL. Timeout: 60 sec",
    "ANTHROPIC_API_URL": "Send your custom Anthropic API URL. Leave empty to use the default Anthropic API URL. Timeout: 60 sec",
    "GOOGLE_AI_API_URL": "Send your custom Google AI API URL. Leave empty to use the default Google AI API URL. Timeout: 60 sec",
    "GROQ_API_URL": "Send your custom Groq API URL. Leave empty to use the default Groq API URL. Timeout: 60 sec",
    # Legacy AI Settings
    "DEFAULT_AI_PROVIDER": "Select the default AI provider to use with the /ask command. Options: mistral, deepseek. Timeout: 60 sec",
    "MISTRAL_API_URL": "Send your custom Mistral AI API URL. Leave empty to use the bot owner's API URL. Timeout: 60 sec",
    "DEEPSEEK_API_URL": "Send your custom DeepSeek AI API URL. Leave empty to use the bot owner's API URL. Timeout: 60 sec",
    # MEGA Settings
    "MEGA_EMAIL": "Send your MEGA.nz account email address. This will be used for MEGA uploads when 'My Token/Config' is enabled. Leave empty to use the bot owner's credentials. Timeout: 60 sec",
    "MEGA_PASSWORD": "Send your MEGA.nz account password. This will be used for MEGA uploads when 'My Token/Config' is enabled. Leave empty to use the bot owner's credentials. Timeout: 60 sec",
    # MEGA Upload Settings
    # "MEGA_UPLOAD_FOLDER" removed - using folder selector instead
    # "MEGA_UPLOAD_EXPIRY_DAYS" removed - premium feature not implemented
    # "MEGA_UPLOAD_PASSWORD" removed - premium feature not implemented
    # "MEGA_UPLOAD_ENCRYPTION_KEY" removed - not supported by MEGA SDK v4.8.0
    # Additional MEGA settings (these are toggle settings, no text input needed)
    "MEGA_UPLOAD_PUBLIC": "Toggle to enable/disable generating public MEGA links for uploads.",
    # "MEGA_UPLOAD_PRIVATE" removed - not supported by MEGA SDK v4.8.0
    # "MEGA_UPLOAD_UNLISTED" removed - not supported by MEGA SDK v4.8.0
    "MEGA_UPLOAD_THUMBNAIL": "Toggle to enable/disable generating thumbnails for MEGA uploads.",
    # "MEGA_UPLOAD_DELETE_AFTER" removed - always delete after upload
    # Metadata Settings
    "METADATA_KEY": "Set legacy metadata key for backward compatibility.\n\nExample: title=My Video,author=John Doe - set title and author\nExample: none - don't use legacy metadata\n\nThis is a legacy option, consider using the specific metadata options instead.\n\nTimeout: 60 sec",
    "METADATA_ALL": "Set metadata text to be used for all metadata fields (title, author, comment) for all track types.\n\nExample: My Project - apply to all metadata fields\nExample: none - don't set global metadata\n\nThis takes priority over all other metadata settings.\n\nTimeout: 60 sec",
    "METADATA_TITLE": "Set metadata text to be used for the global title field.\n\nExample: My Video - set title to 'My Video'\nExample: none - don't set global title\n\nTimeout: 60 sec",
    "METADATA_AUTHOR": "Set metadata text to be used for the global author field.\n\nExample: John Doe - set author to 'John Doe'\nExample: none - don't set global author\n\nTimeout: 60 sec",
    "METADATA_COMMENT": "Set metadata text to be used for the global comment field.\n\nExample: Created with Telegram Bot - add a comment\nExample: none - don't set global comment\n\nTimeout: 60 sec",
    "METADATA_VIDEO_TITLE": "Set metadata text to be used specifically for video track titles.\n\nExample: Episode 1 - set video track title\nExample: none - don't set video track title\n\nTimeout: 60 sec",
    "METADATA_VIDEO_AUTHOR": "Set metadata text to be used specifically for video track authors.\n\nExample: Director Name - set video track author\nExample: none - don't set video track author\n\nTimeout: 60 sec",
    "METADATA_VIDEO_COMMENT": "Set metadata text to be used specifically for video track comments.\n\nExample: 4K HDR Version - add video track comment\nExample: none - don't set video track comment\n\nTimeout: 60 sec",
    "METADATA_AUDIO_TITLE": "Set metadata text to be used specifically for audio track titles.\n\nExample: Song Name - set audio track title\nExample: none - don't set audio track title\n\nTimeout: 60 sec",
    "METADATA_AUDIO_AUTHOR": "Set metadata text to be used specifically for audio track authors.\n\nExample: Artist Name - set audio track author\nExample: none - don't set audio track author\n\nTimeout: 60 sec",
    "METADATA_AUDIO_COMMENT": "Set metadata text to be used specifically for audio track comments.\n\nExample: 320kbps Stereo - add audio track comment\nExample: none - don't set audio track comment\n\nTimeout: 60 sec",
    "METADATA_SUBTITLE_TITLE": "Set metadata text to be used specifically for subtitle track titles.\n\nExample: English Subtitles - set subtitle track title\nExample: none - don't set subtitle track title\n\nTimeout: 60 sec",
    "METADATA_SUBTITLE_AUTHOR": "Set metadata text to be used specifically for subtitle track authors.\n\nExample: Translator Name - set subtitle track author\nExample: none - don't set subtitle track author\n\nTimeout: 60 sec",
    "METADATA_SUBTITLE_COMMENT": "Set metadata text to be used specifically for subtitle track comments.\n\nExample: Full Translation - add subtitle track comment\nExample: none - don't set subtitle track comment\n\nTimeout: 60 sec",
    "USER_SESSION": "Send your pyrogram user session string for download from private telegram chat. Timeout: 60 sec",
    "USER_DUMP": "Send your channel or group id where you want to store your leeched files. Bot must have permission to send message in your chat. Timeout: 60 sec",
    "USER_COOKIES": "Send your cookies.txt file for YouTube and other yt-dlp downloads. This will be used instead of the owner's cookies file. Create it using browser extensions like 'Get cookies.txt' or 'EditThisCookie'. Timeout: 60 sec",
    # Gallery-dl Authentication Settings
    "GALLERY_DL_INSTAGRAM_USERNAME": "Send your Instagram username for accessing private accounts and stories. This will override the bot owner's Instagram credentials. Timeout: 60 sec",
    "GALLERY_DL_INSTAGRAM_PASSWORD": "Send your Instagram password for accessing private accounts and stories. This will override the bot owner's Instagram credentials. Timeout: 60 sec",
    "GALLERY_DL_TWITTER_USERNAME": "Send your Twitter/X username for accessing private accounts and higher quality downloads. This will override the bot owner's Twitter credentials. Timeout: 60 sec",
    "GALLERY_DL_TWITTER_PASSWORD": "Send your Twitter/X password for accessing private accounts and higher quality downloads. This will override the bot owner's Twitter credentials. Timeout: 60 sec",
    "GALLERY_DL_REDDIT_CLIENT_ID": "Send your Reddit app client ID for accessing NSFW content and private subreddits. Create a Reddit app at https://www.reddit.com/prefs/apps/. This will override the bot owner's Reddit credentials. Timeout: 60 sec",
    "GALLERY_DL_REDDIT_CLIENT_SECRET": "Send your Reddit app client secret for accessing NSFW content and private subreddits. Get this from your Reddit app settings. This will override the bot owner's Reddit credentials. Timeout: 60 sec",
    "GALLERY_DL_REDDIT_USERNAME": "Send your Reddit username for accessing private subreddits and enhanced content. This will override the bot owner's Reddit credentials. Timeout: 60 sec",
    "GALLERY_DL_REDDIT_PASSWORD": "Send your Reddit password for accessing private subreddits and enhanced content. This will override the bot owner's Reddit credentials. Timeout: 60 sec",
    "GALLERY_DL_REDDIT_REFRESH_TOKEN": "Send your Reddit OAuth refresh token for persistent authentication. This is generated automatically when using OAuth flow. This will override the bot owner's Reddit credentials. Timeout: 60 sec",
    "GALLERY_DL_PIXIV_USERNAME": "Send your Pixiv username for accessing R-18 content and following artists. This will override the bot owner's Pixiv credentials. Timeout: 60 sec",
    "GALLERY_DL_PIXIV_PASSWORD": "Send your Pixiv password for accessing R-18 content and following artists. This will override the bot owner's Pixiv credentials. Timeout: 60 sec",
    "GALLERY_DL_PIXIV_REFRESH_TOKEN": "Send your Pixiv OAuth refresh token for persistent authentication. This is generated automatically when using OAuth flow. This will override the bot owner's Pixiv credentials. Timeout: 60 sec",
    "GALLERY_DL_DEVIANTART_CLIENT_ID": "Send your DeviantArt app client ID for accessing mature content and Eclipse features. Create a DeviantArt app in your account settings. This will override the bot owner's DeviantArt credentials. Timeout: 60 sec",
    "GALLERY_DL_DEVIANTART_CLIENT_SECRET": "Send your DeviantArt app client secret for accessing mature content and Eclipse features. Get this from your DeviantArt app settings. This will override the bot owner's DeviantArt credentials. Timeout: 60 sec",
    "GALLERY_DL_DEVIANTART_USERNAME": "Send your DeviantArt username for accessing private galleries and mature content. This will override the bot owner's DeviantArt credentials. Timeout: 60 sec",
    "GALLERY_DL_DEVIANTART_PASSWORD": "Send your DeviantArt password for accessing private galleries and mature content. This will override the bot owner's DeviantArt credentials. Timeout: 60 sec",
    "GALLERY_DL_TUMBLR_API_KEY": "Send your Tumblr API key for accessing NSFW content and private blogs. Get this from https://www.tumblr.com/oauth/apps. This will override the bot owner's Tumblr credentials. Timeout: 60 sec",
    "GALLERY_DL_TUMBLR_API_SECRET": "Send your Tumblr API secret for accessing NSFW content and private blogs. Get this from your Tumblr app settings. This will override the bot owner's Tumblr credentials. Timeout: 60 sec",
    "GALLERY_DL_TUMBLR_TOKEN": "Send your Tumblr OAuth token for persistent authentication. This is generated automatically when using OAuth flow. This will override the bot owner's Tumblr credentials. Timeout: 60 sec",
    "GALLERY_DL_TUMBLR_TOKEN_SECRET": "Send your Tumblr OAuth token secret for persistent authentication. This is generated automatically when using OAuth flow. This will override the bot owner's Tumblr credentials. Timeout: 60 sec",
    "GALLERY_DL_DISCORD_TOKEN": "Send your Discord bot token or user token for accessing server content and private channels. This will override the bot owner's Discord credentials. Timeout: 60 sec",
    # Gallery-dl General Settings
    "GALLERY_DL_QUALITY_SELECTION": "Toggle to enable/disable interactive quality selection for gallery-dl downloads. When enabled, you'll be prompted to choose quality before downloading.",
    "GALLERY_DL_ARCHIVE_ENABLED": "Toggle to enable/disable archive functionality for gallery-dl. When enabled, downloaded files are tracked to prevent re-downloading duplicates.",
    "GALLERY_DL_METADATA_ENABLED": "Toggle to enable/disable metadata extraction for gallery-dl downloads. When enabled, additional information about downloaded content is saved.",
    "LEECH_FILENAME_CAPTION": """Send caption template for all your leech files.

<b>Basic Variables:</b>
• <code>{filename}</code> - Filename without extension
• <code>{ext}</code> - File extension
• <code>{size}</code> - File size
• <code>{quality}</code> - Video quality
• <code>{duration}</code> - Media duration
• <code>{season}</code>, <code>{episode}</code> - TV show info

<b>Styling:</b>
• HTML: <code>{{filename}bold}</code>
• Google Fonts: <code>{{filename}Roboto}</code>
• Unicode: <code>{{filename}serif_b}</code>
• Emoji: <code>{{filename}🔥}</code>

<b>Examples:</b>
• <code>📁 {{filename}bold} | 💾 {size}</code>
• <code>🎬 {{filename}Roboto:700} [{quality}]</code>

Use /fontstyles for more options.

Timeout: 60 sec""",
    "LEECH_SPLIT_SIZE": f"Send Leech split size in bytes or use gb or mb. Example: 40000000 or 2.5gb or 1000mb. IS_PREMIUM_USER: {TgClient.IS_PREMIUM_USER}. Timeout: 60 sec",
    "LEECH_DUMP_CHAT": """"Send leech destination ID/USERNAME/PM. You can specify multiple destinations separated by commas.
* b:id/@username/pm (b: means leech by bot) (id or username of the chat or write pm means private message so bot will send the files in private to you) when you should use b:(leech by bot)? When your default settings is leech by user and you want to leech by bot for specific task.
* u:id/@username(u: means leech by user) This incase OWNER added USER_SESSION_STRING.
* h:id/@username(hybrid leech) h: to upload files by bot and user based on file size.
* For multiple destinations, use comma-separated values: -100123456789,-100987654321
* id/@username|topic_id(leech in specific chat and topic) add | without space and write topic id after chat id or username. Timeout: 60 sec""",
    "LOG_CHAT_ID": "Send log chat ID for mirror tasks. You can specify multiple chat IDs separated by commas (e.g., -100123456789,-100987654321). Timeout: 60 sec",
    "LEECH_FILENAME_PREFIX": r"Send Leech Filename Prefix. You can add HTML tags and control spacing manually. Examples: <code>@mychannel</code> (no space), <code>@mychannel </code> (space after), <code>@mychannel-</code> (hyphen), <code>@mychannel_</code> (underscore). Timeout: 60 sec",
    "LEECH_SUFFIX": r"Send Leech Filename Suffix. You can add HTML tags and control spacing manually. Examples: <code>@mychannel</code> (no space), <code> @mychannel</code> (space before), <code>-@mychannel</code> (hyphen), <code>_@mychannel</code> (underscore). Timeout: 60 sec",
    "LEECH_FONT": "Send Leech Font Style. Options: HTML formats (bold, italic), Unicode styles (serif, sans_b), Google Fonts (Roboto, Open Sans), or emojis (🔥). Use /fontstyles for full list. Timeout: 60 sec",
    "LEECH_FILENAME": """Send Leech Filename template. This will change the actual filename of all your leech files.

<b>Basic Variables:</b>
• <code>{filename}</code> - Original filename without extension
• <code>{ext}</code> - File extension (e.g., mkv, mp4)
• <code>{size}</code> - File size (e.g., 1.5GB)
• <code>{quality}</code> - Video quality (e.g., 1080p, 720p)

<b>TV Show Variables:</b>
• <code>{season}</code> - Season number extracted from filename
• <code>{episode}</code> - Episode number extracted from filename
• <code>{year}</code> - Release year extracted from filename

<b>Media Information:</b>
• <code>{codec}</code> - Video codec (e.g., HEVC, AVC)
• <code>{framerate}</code> - Video framerate
• <code>{format}</code> - Media container format
• <code>{formate}</code> - File extension in uppercase

<b>Examples:</b>
• <code>{filename} [{quality}]</code>
• <code>{filename} S{season}E{episode} [{quality}]</code>
• <code>{filename} ({year}) [{codec}]</code>
• <code>Series S{season}E{episode} [{quality}] [{codec}]</code>

Use /fontstyles to see all available template variables.

Timeout: 60 sec""",
    "THUMBNAIL_LAYOUT": "Send thumbnail layout (widthxheight, 2x2, 3x3, 2x4, 4x4, ...). Example: 3x3. Timeout: 60 sec",
    "RCLONE_PATH": "Send Rclone Path. If you want to use your rclone config edit using owner/user config from usetting or add mrcc: before rclone path. Example mrcc:remote:folder. Timeout: 60 sec",
    "RCLONE_FLAGS": "key:value|key|key|key:value . Check here all <a href='https://rclone.org/flags/'>RcloneFlags</a>\nEx: --buffer-size:8M|--drive-starred-only",
    "GDRIVE_ID": "Send Gdrive ID. If you want to use your token.pickle edit using owner/user token from usetting or add mtp: before the id. Example: mtp:F435RGGRDXXXXXX . Timeout: 60 sec",
    "INDEX_URL": "Send Index URL. Timeout: 60 sec",
    "UPLOAD_PATHS": "Send Dict of keys that have path values. Example: {'path 1': 'remote:rclonefolder', 'path 2': 'gdrive1 id', 'path 3': 'tg chat id', 'path 4': 'mrcc:remote:', 'path 5': b:@username} . Timeout: 60 sec",
    "EXCLUDED_EXTENSIONS": "Send exluded extenions separated by space without dot at beginning. Timeout: 60 sec",
    "UNIVERSAL_FILENAME": "Send universal filename template for both mirror and leech files. Supports all template variables like {filename}, {ext}, etc. Priority: -n flag > LEECH_FILENAME (for leech) > UNIVERSAL_FILENAME > original filename. Timeout: 60 sec",
    "NAME_SUBSTITUTE": r"""Word Subtitions. You can add pattern instead of normal text. Timeout: 60 sec
NOTE: You must add \ before any character, those are the characters: \^$.|?*+()[]{}-
Example: script/code/s | mirror/leech | tea/ /s | clone | cpu/ | \[mltb\]/mltb | \\text\\/text/s
1. script will get replaced by code with sensitive case
2. mirror will get replaced by leech
4. tea will get replaced by space with sensitive case
5. clone will get removed
6. cpu will get replaced by space
7. [mltb] will get replaced by mltb
8. \text\ will get replaced by text with sensitive case
""",
    "YT_DLP_OPTIONS": """Send dict of YT-DLP Options. Timeout: 60 sec
Format: {key: value, key: value, key: value}.
Example: {"format": "bv*+mergeall[vcodec=none]", "nocheckcertificate": True, "playliststart": 10, "fragment_retries": float("inf"), "matchtitle": "S13", "writesubtitles": True, "live_from_start": True, "postprocessor_args": {"xtra": ["-threads", "4"]}, "wait_for_video": (5, 100), "download_ranges": [{"start_time": 0, "end_time": 10}]}
Check all yt-dlp api options from this <a href='https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L184'>FILE</a> or use this <a href='https://t.me/mltb_official_channel/177'>script</a> to convert cli arguments to api options.""",
    "FFMPEG_CMDS": """Read this guide. http://telegra.ph/Ffmpeg-guide-01-10""",
    "HELPER_TOKENS": """Send your helper bot tokens separated by space. These bots will be used for hyper download to speed up your downloads.
Example: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ 0987654321:ZYXWVUTSRQPONMLKJIHGFEDCBA

NOTE: You can add unlimited helper bots. Make sure the bots are created using @BotFather and are not being used by any other bot.
To use these bots, you need to enable them using the 'Enable Helper Bots' button in the leech settings menu.
Timeout: 60 sec""",
    "ENABLE_HELPER_BOTS": """Enable or disable helper bots for hyper download.
When enabled, both your helper bots and the owner's helper bots will be used for downloads.
When disabled, only the owner's helper bots will be used.
Timeout: 60 sec""",
    # YouTube Upload Settings
    "YOUTUBE_UPLOAD_DEFAULT_PRIVACY": "Set default privacy setting for YouTube uploads. Options: public, unlisted, private.\n\nExample: unlisted - video won't appear in search but can be shared via link\nExample: public - video will be publicly visible\nExample: private - only you can see the video\n\nTimeout: 60 sec",
    "YOUTUBE_UPLOAD_DEFAULT_CATEGORY": "Set default category ID for YouTube uploads. Common categories: 10 (Music), 22 (People & Blogs), 24 (Entertainment), 25 (News & Politics), 26 (Howto & Style).\n\nExample: 10 - Music category\nExample: 22 - People & Blogs category\nExample: 24 - Entertainment category\n\nTimeout: 60 sec",
    "YOUTUBE_UPLOAD_DEFAULT_TAGS": "Set default tags for YouTube uploads. Separate multiple tags with commas.\n\nExample: music,entertainment,video - multiple tags\nExample: tutorial - single tag\nExample: (leave empty for no default tags)\n\nTimeout: 60 sec",
    "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION": "Set default description for YouTube uploads.\n\nExample: Uploaded via AimLeechBot - simple description\nExample: Check out this amazing content! - custom description\nExample: (leave empty for no default description)\n\nTimeout: 60 sec",
    "YOUTUBE_UPLOAD_DEFAULT_TITLE": "Set default title template for YouTube uploads. Supports variables: {filename}, {date}, {time}, {size}.\n\nExample: {filename} - {date} - adds date to filename\nExample: My Channel - {filename} - adds channel prefix\nExample: (leave empty to use cleaned filename)\n\nVariables:\n{filename} - cleaned filename without extension\n{date} - current date (YYYY-MM-DD)\n{time} - current time (HH:MM:SS)\n{size} - file size (e.g., 1.2 GB)\n\nTimeout: 60 sec",
    # DDL Settings
    "DDL_SERVER": "Set your preferred DDL server for uploads. Available options: gofile, streamtape, devuploads, mediafire.\n\nExample: gofile - use Gofile server for uploads\nExample: streamtape - use Streamtape server for uploads\nExample: devuploads - use DevUploads server for uploads\nExample: mediafire - use MediaFire server for uploads\n\nThis will be used when you specify -up ddl without a specific server.\n\nTimeout: 60 sec",
    "GOFILE_API_KEY": "Send your Gofile API key for personalized uploads. Get your API key from your Gofile profile.\n\nExample: abc123def456 - your personal API key\nExample: (leave empty to use owner's API key)\n\nWith your own API key, uploads will go to your Gofile account.\n\nTimeout: 60 sec",
    "DEVUPLOADS_API_KEY": "Send your DevUploads API key for personalized uploads. Get your API key from your DevUploads account.\n\nExample: abc123def456 - your personal API key\nExample: (leave empty to use owner's API key)\n\nWith your own API key, uploads will go to your DevUploads account.\n\nTimeout: 60 sec",
    "DEVUPLOADS_FOLDER_NAME": "Set custom folder name for DevUploads uploads. Leave empty to use root folder.\n\nExample: MyFiles - creates folder named 'MyFiles'\nExample: Movies/2024 - creates nested folder structure\nExample: (leave empty for root folder)\n\nTimeout: 60 sec",
    "DEVUPLOADS_PUBLIC_FILES": "Set whether uploaded files should be public or private.\n\nExample: true - files are publicly accessible\nExample: false - files are private (require login)\n\nPublic files can be accessed by anyone with the link.\nPrivate files require DevUploads account login to access.\n\nTimeout: 60 sec",
    "GOFILE_FOLDER_NAME": "Set the folder name for your Gofile uploads. Leave empty to use the filename as folder name.\n\nExample: MyBot - create a folder named 'MyBot'\nExample: Downloads/Videos - create nested folders\nExample: (leave empty to use filename)\n\nTimeout: 60 sec",
    "GOFILE_DEFAULT_PASSWORD": "Set a default password for your Gofile uploads when password protection is enabled.\n\nExample: mySecurePassword123 - set a default password\nExample: (leave empty for no default password)\n\nThis password will be used when GOFILE_PASSWORD_PROTECTION is enabled.\n\nTimeout: 60 sec",
    "GOFILE_LINK_EXPIRY_DAYS": "Set the number of days after which your Gofile links should expire. Set to 0 for no expiry.\n\nExample: 30 - links expire after 30 days\nExample: 7 - links expire after 1 week\nExample: 0 - links never expire\n\nTimeout: 60 sec",
    "STREAMTAPE_API_USERNAME": "Send your Streamtape API/FTP Username for personalized uploads.\n\nExample: 878a8499dce2cea654d6 - your API/FTP Username from account panel\nExample: (leave empty to use owner's credentials)\n\nGet this from: https://streamtape.com/accpanel\nLook for 'API/FTP Username' field.\n\nTimeout: 60 sec",
    "STREAMTAPE_API_PASSWORD": "Send your Streamtape API/FTP Password for personalized uploads.\n\nExample: your_generated_password - your API/FTP Password from account panel\nExample: (leave empty to use owner's credentials)\n\nGet this from: https://streamtape.com/accpanel\nUse the 'API/FTP Credentials' form to generate/view your password.\n\nTimeout: 60 sec",
    "STREAMTAPE_FOLDER_NAME": "Set the folder name for your Streamtape uploads. Leave empty to upload to root folder.\n\nExample: MyBot - create a folder named 'MyBot'\nExample: Videos - upload to Videos folder\nExample: (leave empty for root folder)\n\nTimeout: 60 sec",
    "MEDIAFIRE_EMAIL": "Send your MediaFire account email for authentication.\n\nExample: myemail@example.com - your MediaFire account email\nExample: (leave empty to use owner's credentials)\n\nWith your own credentials, uploads will go to your MediaFire account.\n\nTimeout: 60 sec",
    "MEDIAFIRE_PASSWORD": "Send your MediaFire account password for authentication.\n\nExample: mySecurePassword123 - your MediaFire account password\nExample: (leave empty to use owner's credentials)\n\nWith your own credentials, uploads will go to your MediaFire account.\n\nTimeout: 60 sec",
    "MEDIAFIRE_APP_ID": "Send your MediaFire application ID for API access. Get your App ID from MediaFire Developers.\n\nExample: 12345 - your MediaFire application ID\nExample: (leave empty to use owner's App ID)\n\nApp ID is required for MediaFire API access.\n\nTimeout: 60 sec",
    "MEDIAFIRE_API_KEY": "Send your MediaFire API key for enhanced features (optional). Get your API key from MediaFire Developers.\n\nExample: abc123def456 - your MediaFire API key\nExample: (leave empty for basic features)\n\nAPI key provides enhanced features and higher rate limits.\n\nTimeout: 60 sec",
}

# Media tools help text dictionary with detailed examples and consistent formatting
# This is the MAIN dictionary that should be used for all media tools help text
# All entries follow the same format:
# - Clear description of the setting
# - Examples with explanations
# - Timeout information (where applicable)
media_tools_text = {
    "MEDIA_TOOLS_ENABLED": "Enable or disable media tools features. You can enable specific tools by providing a comma-separated list.\n\nExample: true - enable all media tools\nExample: watermark,merge,convert - enable only these tools\nExample: false - disable all media tools\n\nAvailable tools: watermark, merge, convert, compression, trim, extract, remove, add, swap, metadata, xtra, sample, screenshot\n\nTimeout: 60 sec",
    "MEDIA_TOOLS_PRIORITY": "Set priority for media tools processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    # Watermark Settings
    "WATERMARK_ENABLED": "Enable or disable watermark feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable watermark\nExample: false - disable watermark\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all watermark settings to default.",
    "WATERMARK_KEY": "Send your text which will be added as watermark in all mkv videos.\n\nExample: My Watermark Text\n\nTimeout: 60 sec",
    "WATERMARK_POSITION": "Send watermark position. Valid options: top_left, top_right, bottom_left, bottom_right, center, top_center, bottom_center, left_center, right_center.\n\nExample: bottom_right - place in bottom right corner\nExample: center - place in center of video\n\nTimeout: 60 sec",
    "WATERMARK_SIZE": "Send watermark font size (integer value).\n\nExample: 20 - medium size\nExample: 36 - larger size\n\nTimeout: 60 sec",
    "WATERMARK_COLOR": "Send watermark text color.\n\nExample: white - white text\nExample: black - black text\nExample: red - red text\nExample: #FF00FF - custom color (magenta)\n\nTimeout: 60 sec",
    "WATERMARK_FONT": "Send font name for watermark text. You can use a Google Font name or a font file name if available in the bot's directory.\n\nExample: Roboto - Google font\nExample: Arial - common font\nExample: default.otf - use default font\n\nTimeout: 60 sec",
    "WATERMARK_OPACITY": "Set the opacity level for watermark text (0.0-1.0). Lower values make the watermark more transparent.\n\nExample: 0.5 - 50% opacity (semi-transparent)\nExample: 1.0 - 100% opacity (fully visible)\nExample: 0.2 - 20% opacity (mostly transparent)\n\nTimeout: 60 sec",
    "WATERMARK_PRIORITY": "Set priority for watermark processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "WATERMARK_THREADING": "Enable or disable threading for watermark processing.\n\nExample: true - enable threading (faster processing)\nExample: false - disable threading\n\nTimeout: 60 sec",
    "WATERMARK_THREAD_NUMBER": "Set the number of threads to use for watermark processing.\n\nExample: 2 - use 2 threads\nExample: 4 - use 4 threads\n\nTimeout: 60 sec",
    "WATERMARK_QUALITY": "Set the quality value for watermark processing.\n\nExample: 23 - good quality (lower is better)\nExample: 18 - high quality\nExample: none - use default quality\n\nTimeout: 60 sec",
    "WATERMARK_SPEED": "Set the speed value for watermark processing.\n\nExample: ultrafast - fastest processing\nExample: medium - balanced speed and quality\nExample: veryslow - best quality\nExample: none - use default speed\n\nTimeout: 60 sec",
    "WATERMARK_REMOVE_ORIGINAL": "Enable or disable removing original files after watermarking.\n\nExample: true - delete original files after watermarking\nExample: false - keep original files\n\nYou can also use the -del flag in commands to override this setting.\n\nTimeout: 60 sec",
    "AUDIO_WATERMARK_INTERVAL": "Set the interval in seconds for audio watermarks.\n\nExample: 30 - add watermark every 30 seconds\nExample: 60 - add watermark every minute\nExample: 0 - disable interval (default)\n\nTimeout: 60 sec",
    "AUDIO_WATERMARK_VOLUME": "Set the volume of the audio watermark relative to the original audio.\n\nExample: 0.5 - half the volume of the original\nExample: 0.2 - subtle watermark\nExample: 1.0 - same volume as the original\n\nTimeout: 60 sec",
    "SUBTITLE_WATERMARK_INTERVAL": "Set the interval in seconds for subtitle watermarks.\n\nExample: 30 - add watermark every 30 seconds\nExample: 60 - add watermark every minute\nExample: 0 - disable interval (default)\n\nTimeout: 60 sec",
    "SUBTITLE_WATERMARK_STYLE": "Set the style of the subtitle watermark.\n\nExample: normal - standard subtitle style\nExample: bold - bold text\nExample: italic - italic text\nExample: bold_italic - bold and italic text\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_ENABLED": "Enable or disable image watermark feature.\n\nExample: true - enable image watermark\nExample: false - disable image watermark\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_PATH": "Set the path to the watermark image file.\n\nExample: /path/to/watermark.png\n\nThe image should preferably be a PNG with transparency for best results.\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_SCALE": "Set the scale of the watermark image as a percentage of the video width.\n\nExample: 10 - watermark will be 10% of the video width\nExample: 20 - watermark will be 20% of the video width\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_OPACITY": "Set the opacity of the watermark image.\n\nExample: 0.7 - 70% opacity\nExample: 0.5 - 50% opacity\nExample: 1.0 - 100% opacity (fully visible)\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_POSITION": "Set the position of the watermark image on the media.\n\nExample: bottom_right - place in bottom right corner\nExample: center - place in the center of the video\n\nTimeout: 60 sec",
    # Merge Settings
    "MERGE_ENABLED": "Enable or disable merge feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable merge\nExample: false - disable merge\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all merge settings to default.",
    "CONCAT_DEMUXER_ENABLED": "Enable or disable concat demuxer for merging.\n\nExample: true - enable concat demuxer\nExample: false - disable concat demuxer\n\nTimeout: 60 sec",
    "FILTER_COMPLEX_ENABLED": "Enable or disable filter complex for merging.\n\nExample: true - enable filter complex\nExample: false - disable filter complex\n\nTimeout: 60 sec",
    # Output formats
    "MERGE_OUTPUT_FORMAT_VIDEO": "Set output format for merged videos. Common formats: mkv, mp4, avi, webm.\n\nExample: mkv - container that supports almost all codecs\nExample: mp4 - widely compatible format\n\nTimeout: 60 sec",
    "MERGE_OUTPUT_FORMAT_AUDIO": "Set output format for merged audios. Common formats: mp3, m4a, flac, wav.\n\nExample: mp3 - widely compatible format\nExample: flac - lossless audio format\n\nTimeout: 60 sec",
    "MERGE_OUTPUT_FORMAT_IMAGE": "Set output format for merged images. Common formats: jpg, png, webp, tiff.\n\nExample: jpg - good compression, smaller files\nExample: png - lossless format with transparency support\n\nTimeout: 60 sec",
    "MERGE_OUTPUT_FORMAT_DOCUMENT": "Set output format for merged documents. Currently only pdf is supported.\n\nExample: pdf - standard document format\n\nTimeout: 60 sec",
    "MERGE_OUTPUT_FORMAT_SUBTITLE": "Set output format for merged subtitles. Common formats: srt, vtt, ass.\n\nExample: srt - simple subtitle format\nExample: ass - advanced subtitle format with styling\n\nTimeout: 60 sec",
    # Video settings
    "MERGE_VIDEO_CODEC": "Set the video codec for merged videos. Options: copy, h264, h265, vp9, av1.\n\nExample: copy - preserves original codec (fastest)\nExample: h264 - widely compatible codec\n\nTimeout: 60 sec",
    "MERGE_VIDEO_QUALITY": "Set the quality preset for video encoding. Options: low, medium, high, veryhigh.\n\nExample: medium - balanced quality and file size\nExample: high - better quality but larger file size\n\nTimeout: 60 sec",
    "MERGE_VIDEO_PRESET": "Set the encoding preset for video. Options: ultrafast to veryslow.\n\nExample: medium - balanced encoding speed and compression\nExample: slow - better compression but slower encoding\n\nTimeout: 60 sec",
    "MERGE_VIDEO_CRF": "Set the Constant Rate Factor for video quality (0-51, lower is better).\n\nExample: 23 - default value, good balance\nExample: 18 - visually lossless quality\n\nTimeout: 60 sec",
    "MERGE_VIDEO_PIXEL_FORMAT": "Set the pixel format for video. Common formats: yuv420p, yuv444p.\n\nExample: yuv420p - most compatible format\nExample: yuv444p - highest quality but larger file size\n\nTimeout: 60 sec",
    "MERGE_VIDEO_TUNE": "Set the tuning parameter for video encoding. Options: film, animation, grain, etc.\n\nExample: film - for live-action content\nExample: animation - for animated content\n\nTimeout: 60 sec",
    "MERGE_VIDEO_FASTSTART": "Enable or disable faststart flag for MP4 files. Allows videos to start playing before fully downloaded.\n\nExample: true - enable faststart\nExample: false - disable faststart\n\nTimeout: 60 sec",
    # Audio settings
    "MERGE_AUDIO_CODEC": "Set the audio codec for merged audio. Options: copy, aac, mp3, opus, flac.\n\nExample: copy - preserves original codec (fastest)\nExample: aac - good quality and compatibility\n\nTimeout: 60 sec",
    "MERGE_AUDIO_BITRATE": "Set the audio bitrate for merged audio. Examples: 128k, 192k, 320k.\n\nExample: 192k - good quality for most content\nExample: 320k - high quality audio\n\nTimeout: 60 sec",
    "MERGE_AUDIO_CHANNELS": "Set the number of audio channels. Common values: 1 (mono), 2 (stereo).\n\nExample: 2 - stereo audio\nExample: 1 - mono audio\n\nTimeout: 60 sec",
    "MERGE_AUDIO_SAMPLING": "Set the audio sampling rate in Hz. Common values: 44100, 48000.\n\nExample: 44100 - CD quality\nExample: 48000 - DVD/professional audio quality\n\nTimeout: 60 sec",
    "MERGE_AUDIO_VOLUME": "Set the volume adjustment factor (0.0-10.0).\n\nExample: 1.0 - original volume\nExample: 2.0 - double volume\n\nTimeout: 60 sec",
    # Image settings
    "MERGE_IMAGE_MODE": "Set the mode for image merging. Options: auto, horizontal, vertical, collage.\n\nExample: auto - choose based on number of images\nExample: collage - grid layout\n\nTimeout: 60 sec",
    "MERGE_IMAGE_COLUMNS": "Set the number of columns for image collage mode.\n\nExample: 2 - two images per row\nExample: 3 - three images per row\n\nTimeout: 60 sec",
    "MERGE_IMAGE_QUALITY": "Set the quality for image output (1-100). Higher values mean better quality but larger file size.\n\nExample: 90 - high quality\nExample: 75 - good balance of quality and size\n\nTimeout: 60 sec",
    "MERGE_IMAGE_DPI": "Set the DPI (dots per inch) for merged images.\n\nExample: 300 - good for printing\nExample: 72 - standard screen resolution\n\nTimeout: 60 sec",
    "MERGE_IMAGE_RESIZE": "Set the size to resize images to. Format: widthxheight or 'none'.\n\nExample: none - keep original size\nExample: 1920x1080 - resize to Full HD\n\nTimeout: 60 sec",
    "MERGE_IMAGE_BACKGROUND": "Set the background color for image merging.\n\nExample: white - white background\nExample: #FF0000 - red background\n\nTimeout: 60 sec",
    # Subtitle settings
    "MERGE_SUBTITLE_ENCODING": "Set the character encoding for subtitle files.\n\nExample: utf-8 - universal encoding\nExample: latin1 - for Western European languages\n\nTimeout: 60 sec",
    "MERGE_SUBTITLE_FONT": "Set the font for subtitle rendering.\n\nExample: Arial - widely available font\nExample: DejaVu Sans - good for multiple languages\n\nTimeout: 60 sec",
    "MERGE_SUBTITLE_FONT_SIZE": "Set the font size for subtitle rendering.\n\nExample: 24 - medium size\nExample: 32 - larger size for better readability\n\nTimeout: 60 sec",
    "MERGE_SUBTITLE_FONT_COLOR": "Set the font color for subtitle text.\n\nExample: white - white text\nExample: #FFFF00 - yellow text\n\nTimeout: 60 sec",
    "MERGE_SUBTITLE_BACKGROUND": "Set the background color for subtitle text.\n\nExample: black - black background\nExample: transparent - no background\n\nTimeout: 60 sec",
    # Document settings
    "MERGE_DOCUMENT_PAPER_SIZE": "Set the paper size for document output.\n\nExample: a4 - standard international paper size\nExample: letter - standard US paper size\n\nTimeout: 60 sec",
    "MERGE_DOCUMENT_ORIENTATION": "Set the orientation for document output.\n\nExample: portrait - vertical orientation\nExample: landscape - horizontal orientation\n\nTimeout: 60 sec",
    "MERGE_DOCUMENT_MARGIN": "Set the margin size in points for document output.\n\nExample: 50 - standard margin\nExample: 0 - no margin\n\nTimeout: 60 sec",
    # Metadata settings
    "MERGE_METADATA_TITLE": "Set the title metadata for the merged file.\n\nExample: My Video - sets the title to 'My Video'\nExample: empty - no title metadata\n\nTimeout: 60 sec",
    "MERGE_METADATA_AUTHOR": "Set the author metadata for the merged file.\n\nExample: John Doe - sets the author to 'John Doe'\nExample: empty - no author metadata\n\nTimeout: 60 sec",
    "MERGE_METADATA_COMMENT": "Set the comment metadata for the merged file.\n\nExample: Created with Telegram Bot - adds a comment\nExample: empty - no comment metadata\n\nTimeout: 60 sec",
    # General settings
    "MERGE_REMOVE_ORIGINAL": "Enable or disable removing original files after successful merge.\n\nExample: true - remove original files after merge\nExample: false - keep original files\n\nTimeout: 60 sec",
    "MERGE_PRIORITY": "Set priority for merge processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "MERGE_THREADING": "Enable or disable threading for merge processing.\n\nExample: true - enable parallel processing\nExample: false - disable parallel processing\n\nTimeout: 60 sec",
    "MERGE_THREAD_NUMBER": "Set the number of threads to use for merge processing.\n\nExample: 4 - process up to 4 files simultaneously\nExample: 1 - process one file at a time\n\nTimeout: 60 sec",
    # Convert Settings
    "CONVERT_ENABLED": "Enable or disable convert feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable convert feature\nExample: false - disable convert feature\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all convert settings to default.\n\nTimeout: 60 sec",
    "CONVERT_PRIORITY": "Set priority for convert processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "CONVERT_DELETE_ORIGINAL": "Enable or disable deleting original files after conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nThis can be overridden by using the -del flag in the command.\n\nTimeout: 60 sec",
    # Video Convert Settings
    "CONVERT_VIDEO_ENABLED": "Enable or disable video conversion.\n\nExample: true - enable video conversion\nExample: false - disable video conversion\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_FORMAT": "Set the output format for converted videos. Common formats: mp4, mkv, avi, webm.\n\nExample: mp4 - widely compatible format\nExample: mkv - container that supports almost all codecs\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_CODEC": "Set the video codec for converted videos. Common codecs: libx264, libx265, libvpx-vp9.\n\nExample: libx264 - widely compatible codec\nExample: libx265 - better compression but less compatible\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_QUALITY": "Set the quality preset for video encoding. Options: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow.\n\nExample: medium - balanced encoding speed and compression\nExample: slow - better compression but slower encoding\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_CRF": "Set the Constant Rate Factor for video quality (0-51, lower is better).\n\nExample: 23 - default value, good balance\nExample: 18 - visually lossless quality\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_PRESET": "Set the encoding preset for video. Options: ultrafast to veryslow.\n\nExample: medium - balanced encoding speed and compression\nExample: slow - better compression but slower encoding\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_MAINTAIN_QUALITY": "Enable or disable maintaining high quality for video conversion.\n\nExample: true - use higher quality settings\nExample: false - use standard quality settings\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_DELETE_ORIGINAL": "Enable or disable deleting original files after video conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_RESOLUTION": "Set the resolution for video conversion. Format: widthxheight or 'none'.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: none - keep original resolution\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_FPS": "Set the frame rate for video conversion.\n\nExample: 30 - 30 frames per second\nExample: 60 - 60 frames per second\nExample: none - keep original frame rate\n\nTimeout: 60 sec",
    # Audio Convert Settings
    "CONVERT_AUDIO_ENABLED": "Enable or disable audio conversion.\n\nExample: true - enable audio conversion\nExample: false - disable audio conversion\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_FORMAT": "Set the output format for converted audio. Common formats: mp3, m4a, flac, wav, ogg.\n\nExample: mp3 - widely compatible format\nExample: flac - lossless audio format\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_CODEC": "Set the audio codec for converted audio. Common codecs: libmp3lame, aac, libopus, flac.\n\nExample: libmp3lame - for MP3 encoding\nExample: aac - good quality and compatibility\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_BITRATE": "Set the audio bitrate for converted audio. Examples: 128k, 192k, 320k.\n\nExample: 192k - good quality for most content\nExample: 320k - high quality audio\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_CHANNELS": "Set the number of audio channels. Common values: 1 (mono), 2 (stereo).\n\nExample: 2 - stereo audio\nExample: 1 - mono audio\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_SAMPLING": "Set the audio sampling rate in Hz. Common values: 44100, 48000.\n\nExample: 44100 - CD quality\nExample: 48000 - DVD/professional audio quality\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_VOLUME": "Set the volume adjustment factor (0.0-10.0).\n\nExample: 1.0 - original volume\nExample: 2.0 - double volume\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_DELETE_ORIGINAL": "Enable or disable deleting original files after audio conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    # Document Convert Settings
    "CONVERT_DOCUMENT_ENABLED": "Enable or disable document conversion.\n\nExample: true - enable document conversion\nExample: false - disable document conversion\n\nTimeout: 60 sec",
    "CONVERT_DOCUMENT_FORMAT": "Set the output format for converted documents. Common formats: pdf, docx, txt.\n\nExample: pdf - standard document format\nExample: docx - Microsoft Word format\nExample: none - use default format\n\nTimeout: 60 sec",
    "CONVERT_DOCUMENT_QUALITY": "Set the quality for document conversion (0-100). Higher values mean better quality but larger file size.\n\nExample: 90 - high quality\nExample: 75 - good balance of quality and size\nExample: none - use default quality\n\nTimeout: 60 sec",
    "CONVERT_DOCUMENT_DPI": "Set the DPI (dots per inch) for document conversion.\n\nExample: 300 - high quality (good for printing)\nExample: 150 - good balance of quality and size\nExample: 72 - screen resolution (smaller file size)\n\nTimeout: 60 sec",
    "CONVERT_DOCUMENT_DELETE_ORIGINAL": "Enable or disable deleting original files after document conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    # Archive Convert Settings
    "CONVERT_ARCHIVE_ENABLED": "Enable or disable archive conversion.\n\nExample: true - enable archive conversion\nExample: false - disable archive conversion\n\nTimeout: 60 sec",
    "CONVERT_ARCHIVE_FORMAT": "Set the output format for converted archives. Common formats: zip, 7z, tar.gz.\n\nExample: zip - widely compatible format\nExample: 7z - better compression but less compatible\nExample: none - use default format\n\nTimeout: 60 sec",
    "CONVERT_ARCHIVE_LEVEL": "Set the compression level for archive conversion (1-9). Higher values mean better compression but slower processing.\n\nExample: 5 - good balance of speed and compression\nExample: 9 - maximum compression\nExample: 1 - fastest compression\n\nTimeout: 60 sec",
    "CONVERT_ARCHIVE_METHOD": "Set the compression method for archive conversion. Options: deflate, store, bzip2, lzma.\n\nExample: deflate - good balance of speed and compression\nExample: lzma - best compression but slowest\nExample: store - no compression (fastest)\n\nTimeout: 60 sec",
    "CONVERT_ARCHIVE_DELETE_ORIGINAL": "Enable or disable deleting original files after archive conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    # Subtitle Convert Settings
    "CONVERT_SUBTITLE_ENABLED": "Enable or disable subtitle conversion.\n\nExample: true - enable subtitle conversion\nExample: false - disable subtitle conversion\n\nTimeout: 60 sec",
    "CONVERT_SUBTITLE_FORMAT": "Set the output format for converted subtitles. Common formats: srt, ass, vtt.\n\nExample: srt - simple subtitle format\nExample: ass - advanced subtitle format with styling\nExample: none - use default format\n\nTimeout: 60 sec",
    "CONVERT_SUBTITLE_ENCODING": "Set the character encoding for subtitle conversion.\n\nExample: utf-8 - universal encoding\nExample: latin1 - for Western European languages\nExample: none - use default encoding\n\nTimeout: 60 sec",
    "CONVERT_SUBTITLE_LANGUAGE": "Set the language code for subtitle conversion.\n\nExample: eng - English\nExample: spa - Spanish\nExample: none - don't set language\n\nTimeout: 60 sec",
    "CONVERT_SUBTITLE_DELETE_ORIGINAL": "Enable or disable deleting original files after subtitle conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    # Compression Settings
    "COMPRESSION_ENABLED": "Enable or disable compression feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable compression feature\nExample: false - disable compression feature\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all compression settings to default.\n\nTimeout: 60 sec",
    "COMPRESSION_PRIORITY": "Set priority for compression processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "COMPRESSION_DELETE_ORIGINAL": "Enable or disable deleting original files after compression.\n\nExample: true - delete original files after compression\nExample: false - keep original files after compression\n\nTimeout: 60 sec",
    # Video Compression Settings
    "COMPRESSION_VIDEO_ENABLED": "Enable or disable video compression.\n\nExample: true - enable video compression\nExample: false - disable video compression\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_PRESET": "Set the compression preset for videos. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_CRF": "Set the Constant Rate Factor for video quality (0-51, lower is better).\n\nExample: 23 - default value, good balance\nExample: 28 - more compression, lower quality\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_CODEC": "Set the video codec for compression. Common codecs: libx264, libx265.\n\nExample: libx264 - widely compatible codec\nExample: libx265 - better compression but less compatible\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_TUNE": "Set the tuning parameter for video compression. Options: film, animation, grain, etc.\n\nExample: film - for live-action content\nExample: animation - for animated content\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_PIXEL_FORMAT": "Set the pixel format for video compression. Common formats: yuv420p, yuv444p.\n\nExample: yuv420p - most compatible format\nExample: yuv444p - highest quality but larger file size\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_BITDEPTH": "Set the bit depth for video compression. Common values: 8, 10, 12.\n\nExample: 8 - standard 8-bit video (most compatible)\nExample: 10 - 10-bit video (better color gradients)\nExample: none - use default bit depth\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_BITRATE": "Set the bitrate for video compression. Examples: 1M, 5M, 10M.\n\nExample: 5M - 5 Mbps (good for 1080p)\nExample: 2M - 2 Mbps (good for 720p)\nExample: none - use automatic bitrate based on CRF\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_RESOLUTION": "Set the resolution for video compression. Format: widthxheight or 'none'.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: none - keep original resolution\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_FORMAT": "Set the output format for compressed videos. Common formats: mp4, mkv, avi, webm.\n\nExample: mp4 - widely compatible format\nExample: mkv - container that supports almost all codecs\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Audio Compression Settings
    "COMPRESSION_AUDIO_ENABLED": "Enable or disable audio compression.\n\nExample: true - enable audio compression\nExample: false - disable audio compression\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_PRESET": "Set the compression preset for audio. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_CODEC": "Set the audio codec for compression. Common codecs: aac, mp3, opus.\n\nExample: aac - good quality and compatibility\nExample: opus - better compression\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_BITRATE": "Set the audio bitrate for compression. Examples: 64k, 128k, 192k.\n\nExample: 128k - good balance of quality and size\nExample: 64k - smaller files but lower quality\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_CHANNELS": "Set the number of audio channels for compression. Common values: 1 (mono), 2 (stereo).\n\nExample: 2 - stereo audio\nExample: 1 - mono audio (smaller files)\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_BITDEPTH": "Set the bit depth for audio compression. Common values: 16, 24, 32.\n\nExample: 16 - standard CD quality (most compatible)\nExample: 24 - high-resolution audio\nExample: none - use default bit depth\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_FORMAT": "Set the output format for compressed audio. Common formats: mp3, m4a, ogg, flac.\n\nExample: mp3 - widely compatible format\nExample: aac - good quality and compatibility\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Image Compression Settings
    "COMPRESSION_IMAGE_ENABLED": "Enable or disable image compression.\n\nExample: true - enable image compression\nExample: false - disable image compression\n\nTimeout: 60 sec",
    "COMPRESSION_IMAGE_PRESET": "Set the compression preset for images. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_IMAGE_QUALITY": "Set the quality for image compression (1-100). Higher values mean better quality but larger file size.\n\nExample: 80 - good balance of quality and size\nExample: 50 - more compression, lower quality\n\nTimeout: 60 sec",
    "COMPRESSION_IMAGE_RESIZE": "Set the size to resize images to during compression. Format: widthxheight or 'none'.\n\nExample: none - keep original size\nExample: 1280x720 - resize to HD\n\nTimeout: 60 sec",
    "COMPRESSION_IMAGE_FORMAT": "Set the output format for compressed images. Common formats: jpg, png, webp.\n\nExample: jpg - good compression, smaller files\nExample: png - lossless format with transparency support\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Document Compression Settings
    "COMPRESSION_DOCUMENT_ENABLED": "Enable or disable document compression.\n\nExample: true - enable document compression\nExample: false - disable document compression\n\nTimeout: 60 sec",
    "COMPRESSION_DOCUMENT_PRESET": "Set the compression preset for documents. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_DOCUMENT_DPI": "Set the DPI (dots per inch) for document compression.\n\nExample: 150 - good balance of quality and size\nExample: 72 - more compression, lower quality\n\nTimeout: 60 sec",
    "COMPRESSION_DOCUMENT_FORMAT": "Set the output format for compressed documents. Common formats: pdf, docx, txt.\n\nExample: pdf - standard document format\nExample: docx - Microsoft Word format\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Subtitle Compression Settings
    "COMPRESSION_SUBTITLE_ENABLED": "Enable or disable subtitle compression.\n\nExample: true - enable subtitle compression\nExample: false - disable subtitle compression\n\nTimeout: 60 sec",
    "COMPRESSION_SUBTITLE_PRESET": "Set the compression preset for subtitles. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_SUBTITLE_ENCODING": "Set the character encoding for subtitle compression.\n\nExample: utf-8 - universal encoding\nExample: ascii - more compression but limited character support\n\nTimeout: 60 sec",
    "COMPRESSION_SUBTITLE_FORMAT": "Set the output format for compressed subtitles. Common formats: srt, ass, vtt.\n\nExample: srt - simple subtitle format\nExample: ass - advanced subtitle format with styling\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Archive Compression Settings
    "COMPRESSION_ARCHIVE_ENABLED": "Enable or disable archive compression.\n\nExample: true - enable archive compression\nExample: false - disable archive compression\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_PRESET": "Set the compression preset for archives. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower compression ratio\nExample: slow - better compression ratio but slower\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_LEVEL": "Set the compression level for archives (1-9). Higher values mean better compression but slower processing.\n\nExample: 5 - good balance of speed and compression\nExample: 9 - maximum compression\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_METHOD": "Set the compression method for archives. Options: deflate, store, bzip2, lzma.\n\nExample: deflate - good balance of speed and compression\nExample: lzma - best compression but slowest\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_PASSWORD": "Set a password to protect the archive. Leave as 'none' for no password protection.\nNote: Password protection only works with 7z, zip, and rar formats.\n\nExample: mySecurePassword123\nExample: none - no password protection\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_ALGORITHM": "Set the archive algorithm. Options: 7z, zip, tar, rar, etc.\n\nExample: 7z - best compression, supports password protection\nExample: zip - more compatible, supports password protection\nExample: tar - good for preserving file permissions (no password support)\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_FORMAT": "Set the output format for compressed archives. Common formats: zip, 7z, tar.gz.\n\nExample: zip - widely compatible format\nExample: 7z - better compression but less compatible\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Trim Settings
    "TRIM_ENABLED": "Enable or disable trim feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable trim feature\nExample: false - disable trim feature\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all trim settings to default.\n\nTimeout: 60 sec",
    "TRIM_PRIORITY": "Set priority for trim processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "TRIM_START_TIME": "Set the start time for trimming media files. Format: HH:MM:SS, MM:SS, or SS.\n\nExample: 00:01:30 (1 minute 30 seconds)\nExample: 5:45 (5 minutes 45 seconds)\nExample: 90 (90 seconds)\n\nLeave empty or set to 00:00:00 to start from the beginning.\n\nTimeout: 60 sec",
    "TRIM_END_TIME": "Set the end time for trimming media files. Format: HH:MM:SS, MM:SS, or SS.\n\nExample: 00:02:30 (2 minutes 30 seconds)\nExample: 10:45 (10 minutes 45 seconds)\nExample: 180 (180 seconds)\n\nLeave empty to trim until the end of the file.\n\nTimeout: 60 sec",
    "TRIM_DELETE_ORIGINAL": "Enable or disable deleting the original file after trimming.\n\nExample: true - delete original file after trimming\nExample: false - keep both original and trimmed files\n\nTimeout: 60 sec",
    "TRIM_VIDEO_FORMAT": "Set the output format for video trimming. This determines the container format of the trimmed video file.\n\nExample: mp4 - widely compatible format\nExample: mkv - container that supports almost all codecs\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_AUDIO_FORMAT": "Set the output format for audio trimming. This determines the container format of the trimmed audio file.\n\nExample: mp3 - widely compatible format\nExample: flac - lossless audio format\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_IMAGE_FORMAT": "Set the output format for image trimming. This determines the format of the trimmed image file.\n\nExample: jpg - good compression, smaller files\nExample: png - lossless format with transparency support\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_IMAGE_QUALITY": "Set the quality for image processing during trim operations (0-100). Higher values mean better quality but larger file size.\n\nExample: 90 - high quality (default)\nExample: 75 - good balance of quality and size\nExample: none - use original quality\n\nTimeout: 60 sec",
    "TRIM_DOCUMENT_START_PAGE": "Set the starting page number for document trimming. This determines which page to start trimming from.\n\nExample: 1 - start from first page (default)\nExample: 5 - start from page 5\nExample: 10 - start from page 10\n\nTimeout: 60 sec",
    "TRIM_DOCUMENT_END_PAGE": "Set the ending page number for document trimming. Leave empty to trim until the last page.\n\nExample: 10 - end at page 10\nExample: 25 - end at page 25\nExample: (empty) - trim until last page (default)\n\nTimeout: 60 sec",
    "TRIM_DOCUMENT_FORMAT": "Set the output format for document trimming. This determines the format of the trimmed document file.\n\nExample: pdf - standard document format\nExample: docx - Microsoft Word format\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_DOCUMENT_QUALITY": "Set the quality for document processing during trim operations (0-100). Higher values mean better quality but larger file size.\n\nExample: 90 - high quality (default)\nExample: 75 - good balance of quality and size\nExample: none - use original quality\n\nTimeout: 60 sec",
    "TRIM_SUBTITLE_FORMAT": "Set the output format for subtitle trimming. This determines the format of the trimmed subtitle file.\n\nExample: srt - simple subtitle format\nExample: ass - advanced subtitle format with styling\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_ARCHIVE_FORMAT": "Set the output format for archive trimming. This determines the format of the trimmed archive file.\n\nExample: zip - widely compatible format\nExample: 7z - better compression but less compatible\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    # Extract Settings
    "EXTRACT_ENABLED": "Enable or disable the extract feature. Send 'true' to enable or 'false' to disable. When enabled, media tracks can be extracted from container files.\n\nExample: true - enable extract feature\nExample: false - disable extract feature\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nTimeout: 60 sec",
    "EXTRACT_PRIORITY": "Set the priority for extract processing in the media tools pipeline. Lower number means higher priority.\n\nExample: 1 - highest priority (runs before other tools)\nExample: 5 - medium priority\nExample: 10 - lowest priority (runs after other tools)\n\nDefault: 6\nTimeout: 60 sec",
    "EXTRACT_DELETE_ORIGINAL": "Choose whether to delete the original file after extraction. Send 'true' to delete or 'false' to keep.\n\nExample: true - delete original file after extraction\nExample: false - keep original file after extraction\n\nDefault: true\nTimeout: 60 sec",
    "EXTRACT_MAINTAIN_QUALITY": "Choose whether to maintain quality when extracting and converting tracks. Send 'true' to maintain quality or 'false' to use default settings.\n\nExample: true - use high quality settings for extracted tracks\nExample: false - use default quality settings\n\nDefault: true\nTimeout: 60 sec",
    # Video Extract Settings
    "EXTRACT_VIDEO_ENABLED": "Enable or disable video track extraction. Send 'true' to enable or 'false' to disable.\n\nExample: true - extract video tracks\nExample: false - don't extract video tracks\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_CODEC": "Set the codec to use for extracted video tracks. Common codecs: copy, h264, h265, vp9.\n\nExample: copy - preserve original codec (fastest)\nExample: h264 - convert to H.264 (widely compatible)\nExample: h265 - convert to H.265 (better compression)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_FORMAT": "Set the container format for extracted video tracks. Common formats: mp4, mkv, webm.\n\nExample: mp4 - use MP4 container (widely compatible)\nExample: mkv - use MKV container (supports more features)\nExample: none - use default format based on codec\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_INDEX": "Specify which video track(s) to extract by index (0-based). Leave empty or set to 'none' to extract all video tracks.\n\nExample: 0 - extract first video track only\nExample: 1 - extract second video track only\nExample: 0,1,2 - extract first, second, and third video tracks\nExample: all - extract all video tracks\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_QUALITY": "Set the quality for extracted video tracks (CRF value). Lower values mean higher quality.\n\nExample: 18 - high quality (larger file size)\nExample: 23 - medium quality (balanced)\nExample: 28 - lower quality (smaller file size)\nExample: none - use default quality\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_PRESET": "Set the encoding preset for extracted video tracks. Affects encoding speed vs compression efficiency.\n\nExample: ultrafast - fastest encoding, lowest compression\nExample: medium - balanced speed and compression\nExample: veryslow - slowest encoding, best compression\nExample: none - use default preset\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_BITRATE": "Set the bitrate for extracted video tracks. Higher values mean better quality but larger files.\n\nExample: 5M - 5 Mbps (good for 1080p)\nExample: 2M - 2 Mbps (good for 720p)\nExample: none - use default bitrate\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_RESOLUTION": "Set the resolution for extracted video tracks. Lower resolution means smaller file size.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: 640x480 - SD\nExample: none - keep original resolution\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_FPS": "Set the frame rate for extracted video tracks. Lower FPS means smaller file size.\n\nExample: 30 - 30 frames per second\nExample: 60 - 60 frames per second\nExample: none - keep original frame rate\n\nTimeout: 60 sec",
    # Audio Extract Settings
    "EXTRACT_AUDIO_ENABLED": "Enable or disable audio track extraction. Send 'true' to enable or 'false' to disable.\n\nExample: true - extract audio tracks\nExample: false - don't extract audio tracks\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_CODEC": "Set the codec to use for extracted audio tracks. Common codecs: copy, aac, mp3, opus, flac.\n\nExample: copy - preserve original codec (fastest)\nExample: mp3 - convert to MP3 (widely compatible)\nExample: aac - convert to AAC (good quality/size ratio)\nExample: flac - convert to FLAC (lossless)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_FORMAT": "Set the container format for extracted audio tracks. Common formats: mp3, m4a, ogg, flac.\n\nExample: mp3 - use MP3 container (widely compatible)\nExample: m4a - use M4A container (good for AAC)\nExample: none - use default format based on codec\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_INDEX": "Specify which audio track(s) to extract by index (0-based). Leave empty or set to 'none' to extract all audio tracks.\n\nExample: 0 - extract first audio track only\nExample: 1 - extract second audio track only\nExample: 0,1,2 - extract first, second, and third audio tracks\nExample: all - extract all audio tracks\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_BITRATE": "Set the bitrate for extracted audio tracks. Higher values mean better quality but larger files.\n\nExample: 320k - 320 kbps (high quality)\nExample: 192k - 192 kbps (good quality)\nExample: 128k - 128 kbps (acceptable quality)\nExample: none - use default bitrate\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_CHANNELS": "Set the number of audio channels for extracted audio tracks.\n\nExample: 2 - stereo\nExample: 1 - mono\nExample: 6 - 5.1 surround\nExample: none - keep original channels\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_SAMPLING": "Set the sampling rate for extracted audio tracks. Common values: 44100, 48000.\n\nExample: 44100 - CD quality (44.1 kHz)\nExample: 48000 - DVD quality (48 kHz)\nExample: none - keep original sampling rate\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_VOLUME": "Set the volume adjustment for extracted audio tracks. Values above 1 increase volume, below 1 decrease it.\n\nExample: 1.5 - increase volume by 50%\nExample: 0.8 - decrease volume by 20%\nExample: none - keep original volume\n\nTimeout: 60 sec",
    # Subtitle Extract Settings
    "EXTRACT_SUBTITLE_ENABLED": "Enable or disable subtitle track extraction. Send 'true' to enable or 'false' to disable.\n\nExample: true - extract subtitle tracks\nExample: false - don't extract subtitle tracks\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_CODEC": "Set the codec to use for extracted subtitle tracks. Common codecs: copy, srt, ass.\n\nExample: copy - preserve original codec (fastest)\nExample: srt - convert to SRT (widely compatible)\nExample: ass - convert to ASS (supports styling)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_FORMAT": "Set the format for extracted subtitle tracks. Common formats: srt, ass, vtt.\n\nExample: srt - SubRip format (widely compatible)\nExample: ass - Advanced SubStation Alpha (supports styling)\nExample: vtt - WebVTT format (for web videos)\nExample: none - use default format based on codec\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_INDEX": "Specify which subtitle track(s) to extract by index (0-based). Leave empty or set to 'none' to extract all subtitle tracks.\n\nExample: 0 - extract first subtitle track only\nExample: 1 - extract second subtitle track only\nExample: 0,1,2 - extract first, second, and third subtitle tracks\nExample: all - extract all subtitle tracks\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_LANGUAGE": "Set the language tag for extracted subtitle tracks. Uses ISO 639-2 codes.\n\nExample: eng - English\nExample: spa - Spanish\nExample: fre - French\nExample: none - keep original language tag\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_ENCODING": "Set the character encoding for extracted subtitle tracks. Common encodings: utf-8, latin1.\n\nExample: utf-8 - Unicode (recommended)\nExample: latin1 - Western European\nExample: none - auto-detect encoding\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_FONT": "Set the font for extracted subtitle tracks (only works with ASS/SSA subtitles).\n\nExample: Arial - use Arial font\nExample: none - use default font\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_FONT_SIZE": "Set the font size for extracted subtitle tracks (only works with ASS/SSA subtitles).\n\nExample: 24 - larger font size\nExample: 18 - medium font size\nExample: none - use default font size\n\nTimeout: 60 sec",
    # Attachment Extract Settings
    "EXTRACT_ATTACHMENT_ENABLED": "Enable or disable attachment extraction. Send 'true' to enable or 'false' to disable. When enabled, attachments (like fonts, images) will be extracted from media files.\n\nExample: true - extract attachments\nExample: false - don't extract attachments\n\nTimeout: 60 sec",
    "EXTRACT_ATTACHMENT_FORMAT": "Set the format for extracted attachments. Usually not needed as attachments keep their original format.\n\nExample: none - keep original format (recommended)\n\nTimeout: 60 sec",
    "EXTRACT_ATTACHMENT_INDEX": "Specify which attachment(s) to extract by index (0-based). Leave empty or set to 'none' to extract all attachments.\n\nExample: 0 - extract first attachment only\nExample: 1 - extract second attachment only\nExample: 0,1,2 - extract first, second, and third attachments\nExample: all - extract all attachments\n\nTimeout: 60 sec",
    "EXTRACT_ATTACHMENT_FILTER": "Set a filter pattern for extracting attachments. Only attachments matching the pattern will be extracted.\n\nExample: *.ttf - extract only font files\nExample: *.png - extract only PNG images\nExample: none - extract all attachments\n\nTimeout: 60 sec",
    # Add Settings
    "ADD_ENABLED": "Enable or disable the add feature globally.\n\nExample: true - enable add feature\nExample: false - disable add feature\n\nWhen enabled, you can add media tracks to files using the -add flag or through the configured settings.\n\nTimeout: 60 sec",
    "ADD_PRIORITY": "Set the priority of the add process in the media processing pipeline.\n\nExample: 3 - run add before convert\nExample: 8 - run add after extract\n\nLower numbers run earlier. Default order:\n1. Merge\n2. Watermark\n3. Convert\n4. Trim\n5. Compression\n6. Extract\n7. Add (default: 7)\n\nTimeout: 60 sec",
    "ADD_DELETE_ORIGINAL": "Enable or disable deleting the original file after adding media.\n\nExample: true - delete original file after successful add operation\nExample: false - keep both original and modified files\n\nThis can be overridden by using the -del flag in the command.\n\nTimeout: 60 sec",
    "ADD_PRESERVE_TRACKS": "Enable or disable preserving existing tracks when adding new ones.\n\nExample: true - preserve existing tracks when adding new ones\nExample: false - allow existing tracks to be pushed to other indices\n\nThis can be overridden by using the -preserve flag in the command.\n\nTimeout: 60 sec",
    "ADD_REPLACE_TRACKS": "Enable or disable replacing existing tracks when adding new ones.\n\nExample: true - replace existing tracks with new ones\nExample: false - keep existing tracks and add new ones\n\nThis can be overridden by using the -replace flag in the command.\n\nTimeout: 60 sec",
    # Video Add Settings
    "ADD_VIDEO_ENABLED": "Enable or disable adding video tracks to media files.\n\nExample: true - enable video track addition\nExample: false - disable video track addition\n\nWhen enabled, video tracks will be added according to the specified settings.\n\nTimeout: 60 sec",
    # "ADD_VIDEO_PATH": "Path flag has been removed",
    "ADD_VIDEO_INDEX": "Set the video track index to add. Leave empty to add all video tracks.\n\nExample: 0 - add first video track\nExample: 1 - add second video track\nExample: none - add all video tracks\n\nTimeout: 60 sec",
    "ADD_VIDEO_CODEC": "Set the codec to use for video track addition.\n\nExample: copy - preserve original codec (fastest, no quality loss)\nExample: libx264 - H.264 codec (good compatibility)\nExample: libx265 - H.265/HEVC codec (better compression)\nExample: none - use default codec\n\nTimeout: 60 sec",
    "ADD_VIDEO_QUALITY": "Set the quality (CRF value) for video track addition. Lower values mean better quality but larger file size.\n\nExample: 18 - high quality\nExample: 23 - good quality\nExample: 28 - lower quality\nExample: none - don't set quality\n\nTimeout: 60 sec",
    "ADD_VIDEO_PRESET": "Set the encoding preset for video track addition. Faster presets result in larger files, slower presets in smaller files.\n\nExample: ultrafast - fastest encoding, largest files\nExample: medium - balanced speed and compression\nExample: veryslow - slowest encoding, smallest files\nExample: none - don't set preset\n\nTimeout: 60 sec",
    "ADD_VIDEO_BITRATE": "Set the bitrate for video track addition.\n\nExample: 5M - 5 megabits per second\nExample: 500k - 500 kilobits per second\nExample: none - don't set bitrate\n\nTimeout: 60 sec",
    "ADD_VIDEO_RESOLUTION": "Set the resolution for video track addition.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: none - don't set resolution\n\nTimeout: 60 sec",
    "ADD_VIDEO_FPS": "Set the frame rate for video track addition.\n\nExample: 30 - 30 frames per second\nExample: 60 - 60 frames per second\nExample: none - don't set FPS\n\nTimeout: 60 sec",
    # Audio Add Settings
    "ADD_AUDIO_ENABLED": "Enable or disable adding audio tracks to media files.\n\nExample: true - enable audio track addition\nExample: false - disable audio track addition\n\nWhen enabled, audio tracks will be added according to the specified settings.\n\nTimeout: 60 sec",
    # "ADD_AUDIO_PATH": "Path flag has been removed",
    "ADD_AUDIO_INDEX": "Set the audio track index to add. Leave empty to add all audio tracks.\n\nExample: 0 - add first audio track\nExample: 1 - add second audio track\nExample: none - add all audio tracks\n\nTimeout: 60 sec",
    "ADD_AUDIO_CODEC": "Set the codec to use for audio track addition.\n\nExample: copy - preserve original codec (fastest, no quality loss)\nExample: aac - AAC codec (good quality, compatibility)\nExample: libmp3lame - MP3 codec (widely compatible)\nExample: flac - FLAC codec (lossless)\nExample: none - use default codec\n\nTimeout: 60 sec",
    "ADD_AUDIO_BITRATE": "Set the bitrate for audio track addition.\n\nExample: 320k - high quality\nExample: 192k - good quality\nExample: 128k - acceptable quality\nExample: none - don't set bitrate\n\nTimeout: 60 sec",
    "ADD_AUDIO_CHANNELS": "Set the number of audio channels for track addition.\n\nExample: 2 - stereo\nExample: 1 - mono\nExample: none - don't set channels\n\nTimeout: 60 sec",
    "ADD_AUDIO_SAMPLING": "Set the sampling rate for audio track addition.\n\nExample: 48000 - high quality\nExample: 44100 - CD quality\nExample: none - don't set sampling rate\n\nTimeout: 60 sec",
    "ADD_AUDIO_VOLUME": "Set the volume adjustment for audio track addition.\n\nExample: 1.0 - original volume\nExample: 2.0 - double volume\nExample: 0.5 - half volume\nExample: none - don't adjust volume\n\nTimeout: 60 sec",
    # Subtitle Add Settings
    "ADD_SUBTITLE_ENABLED": "Enable or disable adding subtitle tracks to media files.\n\nExample: true - enable subtitle track addition\nExample: false - disable subtitle track addition\n\nWhen enabled, subtitle tracks will be added according to the specified settings.\n\nTimeout: 60 sec",
    # "ADD_SUBTITLE_PATH": "Path flag has been removed",
    "ADD_SUBTITLE_INDEX": "Set the subtitle track index to add. Leave empty to add all subtitle tracks.\n\nExample: 0 - add first subtitle track\nExample: 1 - add second subtitle track\nExample: none - add all subtitle tracks\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_CODEC": "Set the codec to use for subtitle track addition.\n\nExample: copy - preserve original format\nExample: srt - convert to SRT format\nExample: ass - convert to ASS format\nExample: none - use default codec\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_LANGUAGE": "Set the language code for subtitle track addition.\n\nExample: eng - English\nExample: spa - Spanish\nExample: none - don't set language\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_ENCODING": "Set the character encoding for subtitle track addition.\n\nExample: utf-8 - UTF-8 encoding\nExample: latin1 - Latin-1 encoding\nExample: none - don't set encoding\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_FONT": "Set the font for subtitle track addition (for ASS/SSA subtitles).\n\nExample: Arial - use Arial font\nExample: DejaVu Sans - use DejaVu Sans font\nExample: none - don't set font\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_FONT_SIZE": "Set the font size for subtitle track addition (for ASS/SSA subtitles).\n\nExample: 24 - medium size\nExample: 32 - larger size\nExample: none - don't set font size\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_HARDSUB_ENABLED": "Enable or disable hardsub (burning subtitles into video).\n\nExample: true - burn subtitles permanently into video (cannot be turned off)\nExample: false - add subtitles as separate tracks (can be toggled on/off)\n\nNote: Hardsub requires video re-encoding and may reduce quality but ensures compatibility.\n\nTimeout: 60 sec",
    # Attachment Add Settings
    "ADD_ATTACHMENT_ENABLED": "Enable or disable adding attachments to media files.\n\nExample: true - enable attachment addition\nExample: false - disable attachment addition\n\nWhen enabled, attachments will be added according to the specified settings.\n\nTimeout: 60 sec",
    # "ADD_ATTACHMENT_PATH": "Path flag has been removed",
    "ADD_ATTACHMENT_INDEX": "Set the attachment index to add. Leave empty to add all attachments.\n\nExample: 0 - add first attachment\nExample: 1 - add second attachment\nExample: none - add all attachments\n\nTimeout: 60 sec",
    "ADD_ATTACHMENT_MIMETYPE": "Set the MIME type for attachment addition.\n\nExample: font/ttf - TrueType font\nExample: image/png - PNG image\nExample: none - don't set MIME type\n\nTimeout: 60 sec",
    # Remove Settings
    "REMOVE_ENABLED": "Enable or disable the remove feature globally.\n\nExample: true - enable remove feature\nExample: false - disable remove feature\n\nWhen enabled, you can remove media tracks from files using the -remove flag or through the configured settings.\n\nTimeout: 60 sec",
    "REMOVE_PRIORITY": "Set the priority of the remove process in the media processing pipeline.\n\nExample: 8 - run remove after extract (default)\nExample: 5 - run remove before extract\n\nLower numbers run earlier. Default order:\n1. Merge\n2. Watermark\n3. Convert\n4. Trim\n5. Compression\n6. Extract\n7. Add\n8. Remove (default: 8)\n\nTimeout: 60 sec",
    "REMOVE_DELETE_ORIGINAL": "Enable or disable deleting the original file after removing tracks.\n\nExample: true - delete original file after successful remove operation\nExample: false - keep both original and modified files\n\nThis can be overridden by using the -del flag in the command.\n\nTimeout: 60 sec",
    "REMOVE_METADATA": "Enable or disable removing metadata from media files.\n\nExample: true - remove all metadata from files\nExample: false - keep metadata intact\n\nThis can be overridden by using the -remove-metadata flag in the command.\n\nTimeout: 60 sec",
    "REMOVE_MAINTAIN_QUALITY": "Choose whether to maintain quality when removing and re-encoding tracks. Send 'true' to maintain quality or 'false' to use default settings.\n\nExample: true - use high quality settings for remaining tracks\nExample: false - use default quality settings\n\nDefault: true\nTimeout: 60 sec",
    # Video Remove Settings
    "REMOVE_VIDEO_ENABLED": "Enable or disable video track removal. Send 'true' to enable or 'false' to disable.\n\nExample: true - remove video tracks\nExample: false - don't remove video tracks\n\nTimeout: 60 sec",
    "REMOVE_VIDEO_CODEC": "Set the codec to use for remaining video tracks after removal. Common codecs: copy, libx264, libx265, libvpx-vp9.\n\nExample: copy - preserve original codec (fastest)\nExample: libx264 - convert to H.264 (widely compatible)\nExample: libx265 - convert to H.265 (better compression)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "REMOVE_VIDEO_FORMAT": "Set the container format for output after video track removal. Common formats: mp4, mkv, webm.\n\nExample: mp4 - use MP4 container (widely compatible)\nExample: mkv - use MKV container (supports more features)\nExample: none - use default format based on input\n\nTimeout: 60 sec",
    "REMOVE_VIDEO_INDEX": "Specify which video track(s) to remove by index (0-based). Leave empty or set to 'none' to remove all video tracks.\n\nExample: 0 - remove first video track only\nExample: 1 - remove second video track only\nExample: 0,1,2 - remove first, second, and third video tracks\nExample: all - remove all video tracks\n\nTimeout: 60 sec",
    "REMOVE_VIDEO_QUALITY": "Set the quality for remaining video tracks after removal (CRF value). Lower values mean higher quality.\n\nExample: 18 - high quality (larger file size)\nExample: 23 - medium quality (balanced)\nExample: 28 - lower quality (smaller file size)\nExample: none - use default quality\n\nTimeout: 60 sec",
    "REMOVE_VIDEO_PRESET": "Set the encoding preset for remaining video tracks after removal. Affects encoding speed vs compression efficiency.\n\nExample: ultrafast - fastest encoding, lowest compression\nExample: medium - balanced speed and compression\nExample: veryslow - slowest encoding, best compression\nExample: none - use default preset\n\nTimeout: 60 sec",
    "REMOVE_VIDEO_BITRATE": "Set the bitrate for remaining video tracks after removal. Higher values mean better quality but larger files.\n\nExample: 5M - 5 Mbps (good for 1080p)\nExample: 2M - 2 Mbps (good for 720p)\nExample: none - use default bitrate\n\nTimeout: 60 sec",
    "REMOVE_VIDEO_RESOLUTION": "Set the resolution for remaining video tracks after removal. Lower resolution means smaller file size.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: 640x480 - SD\nExample: none - keep original resolution\n\nTimeout: 60 sec",
    "REMOVE_VIDEO_FPS": "Set the frame rate for remaining video tracks after removal. Lower FPS means smaller file size.\n\nExample: 30 - 30 frames per second\nExample: 60 - 60 frames per second\nExample: none - keep original frame rate\n\nTimeout: 60 sec",
    # Audio Remove Settings
    "REMOVE_AUDIO_ENABLED": "Enable or disable audio track removal. Send 'true' to enable or 'false' to disable.\n\nExample: true - remove audio tracks\nExample: false - don't remove audio tracks\n\nTimeout: 60 sec",
    "REMOVE_AUDIO_CODEC": "Set the codec to use for remaining audio tracks after removal. Common codecs: copy, aac, mp3, opus, flac.\n\nExample: copy - preserve original codec (fastest)\nExample: mp3 - convert to MP3 (widely compatible)\nExample: aac - convert to AAC (good quality/size ratio)\nExample: flac - convert to FLAC (lossless)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "REMOVE_AUDIO_FORMAT": "Set the container format for output after audio track removal. Common formats: mp3, m4a, ogg, flac.\n\nExample: mp3 - use MP3 container (widely compatible)\nExample: m4a - use M4A container (good for AAC)\nExample: none - use default format based on input\n\nTimeout: 60 sec",
    "REMOVE_AUDIO_INDEX": "Specify which audio track(s) to remove by index (0-based). Leave empty or set to 'none' to remove all audio tracks.\n\nExample: 0 - remove first audio track only\nExample: 1 - remove second audio track only\nExample: 0,1,2 - remove first, second, and third audio tracks\nExample: all - remove all audio tracks\n\nTimeout: 60 sec",
    "REMOVE_AUDIO_BITRATE": "Set the bitrate for remaining audio tracks after removal. Higher values mean better quality but larger files.\n\nExample: 320k - 320 kbps (high quality)\nExample: 192k - 192 kbps (good quality)\nExample: 128k - 128 kbps (acceptable quality)\nExample: none - use default bitrate\n\nTimeout: 60 sec",
    "REMOVE_AUDIO_CHANNELS": "Set the number of audio channels for remaining audio tracks after removal.\n\nExample: 2 - stereo\nExample: 1 - mono\nExample: 6 - 5.1 surround\nExample: none - keep original channels\n\nTimeout: 60 sec",
    "REMOVE_AUDIO_SAMPLING": "Set the sampling rate for remaining audio tracks after removal. Common values: 44100, 48000.\n\nExample: 44100 - CD quality (44.1 kHz)\nExample: 48000 - DVD quality (48 kHz)\nExample: none - keep original sampling rate\n\nTimeout: 60 sec",
    "REMOVE_AUDIO_VOLUME": "Set the volume adjustment for remaining audio tracks after removal. Values above 1 increase volume, below 1 decrease it.\n\nExample: 1.5 - increase volume by 50%\nExample: 0.8 - decrease volume by 20%\nExample: none - keep original volume\n\nTimeout: 60 sec",
    # Subtitle Remove Settings
    "REMOVE_SUBTITLE_ENABLED": "Enable or disable subtitle track removal. Send 'true' to enable or 'false' to disable.\n\nExample: true - remove subtitle tracks\nExample: false - don't remove subtitle tracks\n\nTimeout: 60 sec",
    "REMOVE_SUBTITLE_CODEC": "Set the codec to use for remaining subtitle tracks after removal. Common codecs: copy, srt, ass.\n\nExample: copy - preserve original codec (fastest)\nExample: srt - convert to SRT (widely compatible)\nExample: ass - convert to ASS (supports styling)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "REMOVE_SUBTITLE_FORMAT": "Set the format for remaining subtitle tracks after removal. Common formats: srt, ass, vtt.\n\nExample: srt - SubRip format (widely compatible)\nExample: ass - Advanced SubStation Alpha (supports styling)\nExample: vtt - WebVTT format (for web videos)\nExample: none - use default format based on input\n\nTimeout: 60 sec",
    "REMOVE_SUBTITLE_INDEX": "Specify which subtitle track(s) to remove by index (0-based). Leave empty or set to 'none' to remove all subtitle tracks.\n\nExample: 0 - remove first subtitle track only\nExample: 1 - remove second subtitle track only\nExample: 0,1,2 - remove first, second, and third subtitle tracks\nExample: all - remove all subtitle tracks\n\nTimeout: 60 sec",
    "REMOVE_SUBTITLE_LANGUAGE": "Set the language tag for remaining subtitle tracks after removal. Uses ISO 639-2 codes.\n\nExample: eng - English\nExample: spa - Spanish\nExample: fre - French\nExample: none - keep original language tag\n\nTimeout: 60 sec",
    "REMOVE_SUBTITLE_ENCODING": "Set the character encoding for remaining subtitle tracks after removal. Common encodings: utf-8, latin1.\n\nExample: utf-8 - Unicode (recommended)\nExample: latin1 - Western European\nExample: none - auto-detect encoding\n\nTimeout: 60 sec",
    "REMOVE_SUBTITLE_FONT": "Set the font for remaining subtitle tracks after removal (only works with ASS/SSA subtitles).\n\nExample: Arial - use Arial font\nExample: none - use default font\n\nTimeout: 60 sec",
    "REMOVE_SUBTITLE_FONT_SIZE": "Set the font size for remaining subtitle tracks after removal (only works with ASS/SSA subtitles).\n\nExample: 24 - larger font size\nExample: 18 - medium font size\nExample: none - use default font size\n\nTimeout: 60 sec",
    # Attachment Remove Settings
    "REMOVE_ATTACHMENT_ENABLED": "Enable or disable attachment removal. Send 'true' to enable or 'false' to disable. When enabled, attachments (like fonts, images) will be removed from media files.\n\nExample: true - remove attachments\nExample: false - don't remove attachments\n\nTimeout: 60 sec",
    "REMOVE_ATTACHMENT_FORMAT": "Set the format for output after attachment removal. Usually not needed as the container format is preserved.\n\nExample: none - keep original format (recommended)\n\nTimeout: 60 sec",
    "REMOVE_ATTACHMENT_INDEX": "Specify which attachment(s) to remove by index (0-based). Leave empty or set to 'none' to remove all attachments.\n\nExample: 0 - remove first attachment only\nExample: 1 - remove second attachment only\nExample: 0,1,2 - remove first, second, and third attachments\nExample: all - remove all attachments\n\nTimeout: 60 sec",
    "REMOVE_ATTACHMENT_FILTER": "Set a filter pattern for removing attachments. Only attachments matching the pattern will be removed.\n\nExample: *.ttf - remove only font files\nExample: *.png - remove only PNG images\nExample: none - remove all attachments\n\nTimeout: 60 sec",
    # Swap Settings
    "SWAP_ENABLED": "Enable or disable the swap feature globally.\n\nExample: true - enable swap feature\nExample: false - disable swap feature\n\nWhen enabled, you can reorder media tracks using the -swap flag or through the configured settings.\n\nTimeout: 60 sec",
    "SWAP_PRIORITY": "Set the priority of the swap process in the media processing pipeline.\n\nExample: 6 - run swap between add and remove (default)\nExample: 3 - run swap before convert\n\nLower numbers run earlier. Default order:\n1. Merge\n2. Watermark\n3. Convert\n4. Trim\n5. Compression\n6. Extract\n7. Add\n8. Swap (default: 6)\n9. Remove\n\nTimeout: 60 sec",
    "SWAP_REMOVE_ORIGINAL": "Enable or disable deleting the original file after swapping tracks.\n\nExample: true - delete original file after successful swap operation\nExample: false - keep both original and modified files\n\nThis can be overridden by using the -del flag in the command.\n\nTimeout: 60 sec",
    # Audio Swap Settings
    "SWAP_AUDIO_ENABLED": "Enable or disable audio track swapping.\n\nExample: true - enable audio track swapping\nExample: false - disable audio track swapping\n\nWhen enabled, audio tracks will be reordered according to the specified settings.\n\nTimeout: 60 sec",
    "SWAP_AUDIO_USE_LANGUAGE": "Choose between language-based or index-based audio track swapping.\n\nExample: true - use language-based swapping (reorder by language priority)\nExample: false - use index-based swapping (swap specific track positions)\n\nTimeout: 60 sec",
    "SWAP_AUDIO_LANGUAGE_ORDER": "Set the language priority order for audio track swapping (used when USE_LANGUAGE is true).\n\nExample: eng,hin,jpn - English first, Hindi second, Japanese third\nExample: spa,eng - Spanish first, English second\nExample: none - don't set language order\n\nTimeout: 60 sec",
    "SWAP_AUDIO_INDEX_ORDER": "Set the index swap pattern for audio tracks (used when USE_LANGUAGE is false).\n\nExample: 0,1 - swap first two tracks\nExample: 1,2,0 - rotate first three tracks\nExample: 2,1,0 - reverse first three tracks\nExample: none - don't swap by index\n\nTimeout: 60 sec",
    # Video Swap Settings
    "SWAP_VIDEO_ENABLED": "Enable or disable video track swapping.\n\nExample: true - enable video track swapping\nExample: false - disable video track swapping\n\nWhen enabled, video tracks will be reordered according to the specified settings.\n\nTimeout: 60 sec",
    "SWAP_VIDEO_USE_LANGUAGE": "Choose between language-based or index-based video track swapping.\n\nExample: true - use language-based swapping (reorder by language priority)\nExample: false - use index-based swapping (swap specific track positions)\n\nTimeout: 60 sec",
    "SWAP_VIDEO_LANGUAGE_ORDER": "Set the language priority order for video track swapping (used when USE_LANGUAGE is true).\n\nExample: eng,hin,jpn - English first, Hindi second, Japanese third\nExample: spa,eng - Spanish first, English second\nExample: none - don't set language order\n\nTimeout: 60 sec",
    "SWAP_VIDEO_INDEX_ORDER": "Set the index swap pattern for video tracks (used when USE_LANGUAGE is false).\n\nExample: 0,1 - swap first two tracks\nExample: 1,2,0 - rotate first three tracks\nExample: 2,1,0 - reverse first three tracks\nExample: none - don't swap by index\n\nTimeout: 60 sec",
    # Subtitle Swap Settings
    "SWAP_SUBTITLE_ENABLED": "Enable or disable subtitle track swapping.\n\nExample: true - enable subtitle track swapping\nExample: false - disable subtitle track swapping\n\nWhen enabled, subtitle tracks will be reordered according to the specified settings.\n\nTimeout: 60 sec",
    "SWAP_SUBTITLE_USE_LANGUAGE": "Choose between language-based or index-based subtitle track swapping.\n\nExample: true - use language-based swapping (reorder by language priority)\nExample: false - use index-based swapping (swap specific track positions)\n\nTimeout: 60 sec",
    "SWAP_SUBTITLE_LANGUAGE_ORDER": "Set the language priority order for subtitle track swapping (used when USE_LANGUAGE is true).\n\nExample: eng,hin,jpn - English first, Hindi second, Japanese third\nExample: spa,eng - Spanish first, English second\nExample: none - don't set language order\n\nTimeout: 60 sec",
    "SWAP_SUBTITLE_INDEX_ORDER": "Set the index swap pattern for subtitle tracks (used when USE_LANGUAGE is false).\n\nExample: 0,1 - swap first two tracks\nExample: 1,2,0 - rotate first three tracks\nExample: 2,1,0 - reverse first three tracks\nExample: none - don't swap by index\n\nTimeout: 60 sec",
    # MediaInfo Settings
    "MEDIAINFO_ENABLED": "Enable or disable the MediaInfo command for detailed media information.\n\nExample: true - enable MediaInfo command\nExample: false - disable MediaInfo command\n\nWhen enabled, you can use the /mediainfo command to get detailed information about media files.\n\nTimeout: 60 sec",
    # Sample Video Settings
    "SAMPLE_VIDEO_ENABLED": "Enable or disable the sample video feature. This allows creating short sample clips from videos.\n\nExample: true - enable sample video feature\nExample: false - disable sample video feature\n\nTimeout: 60 sec",
}

# Main help page
main_help_string = """
<b>📚 Bot Commands Guide</b>

<b>NOTE:</b> Try each command without any argument to see more details.
Use the buttons below to navigate through different command categories.
"""

# Download Commands page
download_commands = f"""
<b>🔄 Download Commands</b>

/{BotCommands.MirrorCommand[0]} or /{BotCommands.MirrorCommand[1]}: Start mirroring to cloud.
/{BotCommands.JdMirrorCommand[0]} or /{BotCommands.JdMirrorCommand[1]}: Start mirroring to cloud using JDownloader.
/{BotCommands.NzbMirrorCommand[0]} or /{BotCommands.NzbMirrorCommand[1]}: Start mirroring to cloud using Sabnzbd.
/{BotCommands.YtdlCommand[0]} or /{BotCommands.YtdlCommand[1]}: Mirror yt-dlp supported link.
/{BotCommands.LeechCommand[0]} or /{BotCommands.LeechCommand[1]}: Start leeching to Telegram. If helper bots are configured, hyper download will be used for faster downloads.
/{BotCommands.JdLeechCommand[0]} or /{BotCommands.JdLeechCommand[1]}: Start leeching using JDownloader.
/{BotCommands.NzbLeechCommand[0]} or /{BotCommands.NzbLeechCommand[1]}: Start leeching using Sabnzbd.
/{BotCommands.YtdlLeechCommand[0]} or /{BotCommands.YtdlLeechCommand[1]}: Leech yt-dlp supported link.
/{BotCommands.StreamripMirrorCommand[0]} or /{BotCommands.StreamripMirrorCommand[1]}: Mirror music from streaming platforms (Qobuz, Tidal, Deezer, SoundCloud).
/{BotCommands.StreamripLeechCommand[0]} or /{BotCommands.StreamripLeechCommand[1]}: Leech music from streaming platforms to Telegram.
/{BotCommands.StreamripSearchCommand[0]} or /{BotCommands.StreamripSearchCommand[1]}: Search for music across streaming platforms.
/{BotCommands.ZotifyMirrorCommand[0]} or /{BotCommands.ZotifyMirrorCommand[1]}: Mirror music from Spotify using Zotify. Supports URLs, search queries, and special downloads (liked-tracks, followed-artists, saved-playlists, liked-episodes).
/{BotCommands.ZotifyLeechCommand[0]} or /{BotCommands.ZotifyLeechCommand[1]}: Leech music from Spotify to Telegram using Zotify. Supports URLs, search queries, and special downloads.
/{BotCommands.ZotifySearchCommand[0]} or /{BotCommands.ZotifySearchCommand[1]}: Search for music on Spotify using Zotify.
/{BotCommands.MusicMirrorCommand[0]} or /{BotCommands.MusicMirrorCommand[1]}: Mirror high-quality music from multiple platforms (Tidal, Qobuz, Apple Music, Spotify, Deezer) using MusicDL. Supports Hi-Res audio up to 24-bit/192kHz.
/{BotCommands.MusicLeechCommand[0]} or /{BotCommands.MusicLeechCommand[1]}: Leech high-quality music to Telegram from multiple platforms using MusicDL. Supports FLAC, Hi-Res, and lossless formats.
/{BotCommands.CloneCommand} [drive_url]: Copy file/folder to Google Drive.

/{BotCommands.MegaSearchCommand[0]} or /{BotCommands.MegaSearchCommand[1]} [query]: Search through MEGA drive for files and folders.
"""

# Status & Management page
status_commands = f"""
<b>📊 Status & Management</b>

/{BotCommands.StatusCommand[0]} or /{BotCommands.StatusCommand[1]} or /{BotCommands.StatusCommand[2]} or /{BotCommands.StatusCommand[3]}: Shows a status of all the downloads.
/{BotCommands.StatsCommand}: Show stats of the machine where the bot is hosted in.
/{BotCommands.PingCommand}: Check how long it takes to ping the bot.
/{BotCommands.SpeedTest}: Check internet speed of the host machine.
/{BotCommands.CancelAllCommand} [query]: Cancel all [status] tasks.
/{BotCommands.ForceStartCommand[0]} or /{BotCommands.ForceStartCommand[1]} [gid]: Force start task by gid or reply.
/{BotCommands.SelectCommand}: Select files from torrents by gid or reply.
/{BotCommands.CheckDeletionsCommand[0]} or /{BotCommands.CheckDeletionsCommand[1]}: Check and manage scheduled message deletions.
"""

# Search Tools page
search_commands = f"""
<b>🔍 Search Tools</b>

/{BotCommands.ListCommand} [query]: Search in Google Drive(s).
/{BotCommands.SearchCommand} [query]: Search for torrents with API.
/{BotCommands.HydraSearchCommamd} [query]: Search for NZB files.
/{BotCommands.MediaSearchCommand[0]} or /{BotCommands.MediaSearchCommand[1]}: Search for media files in configured channels.
/{BotCommands.IMDBCommand}: Search for movies or TV series info on IMDB.
/{BotCommands.TMDBCommand}: Search for movies, TV shows, and people on TMDB.
/{BotCommands.ScrapCommand} [url|help|domains]: Scrape movie info (title, qualities, sizes, magnet links) from 1tamilmv websites.
/{BotCommands.TraceCommand}: Identify anime from images, videos, or GIFs using trace.moe API.

"""

# File Management page
file_commands = f"""
<b>📁 File Management</b>

/{BotCommands.MediaInfoCommand[0]} or /{BotCommands.MediaInfoCommand[1]}: Get MediaInfo from telegram file or direct link.
/{BotCommands.CountCommand} [drive_url]: Count file/folder of Google Drive.
/{BotCommands.DeleteCommand} [drive_url]: Delete file/folder from Google Drive (Only Owner & Sudo).
/{BotCommands.SoxCommand[0]} or /{BotCommands.SoxCommand[1]}: Generate audio spectrum from audio files.
/{BotCommands.PasteCommand}: Paste text/code to a pastebin service.
/{BotCommands.File2LinkCommand}: Convert Telegram media files into direct streaming links. Reply to any media file to generate streaming and download links.
/{BotCommands.ToolCommand[0]} or /{BotCommands.ToolCommand[1]}: Media conversion and processing tools (gif, sticker, emoji, voice, vnote, image processing, text tools). Also supports direct GitHub repo download with URL.
# IndexCommand removed - media indexing functionality disabled
"""

# Security & Authentication page
security_commands = f"""
<b>🔒 Security & Authentication</b>

/{BotCommands.LoginCommand}: Login to the bot using password for permanent access.
/{BotCommands.AuthorizeCommand}: Authorize a chat or a user to use the bot (Owner & Sudo only).
/{BotCommands.UnAuthorizeCommand}: Unauthorize a chat or a user from using the bot (Owner & Sudo only).
/{BotCommands.AddSudoCommand}: Add a user to Sudo (Owner only).
/{BotCommands.RmSudoCommand}: Remove a user from Sudo (Owner only).
/{BotCommands.UsersCommand}: Show authorized users (Owner & Sudo only).
/{BotCommands.GenSessionCommand[0]} or /{BotCommands.GenSessionCommand[1]}: Generate a Pyrogram session string securely.
/{BotCommands.VirusTotalCommand}: Scan files or URLs for viruses using VirusTotal.
/{BotCommands.PhishCheckCommand}: Check domains and emails for phishing/security threats.
/{BotCommands.WotCommand}: Check website, domain, and IP reputation using WOT and AbuseIPDB.
/{BotCommands.NSFWStatsCommand}: View NSFW detection statistics and system status.
/{BotCommands.NSFWTestCommand}: Test NSFW detection on text or media content.
/{BotCommands.ContactCommand}: Contact the bot owner (available to all users).
/{BotCommands.BanCommand}: Ban a user from using the contact feature (Sudo only).
/{BotCommands.UnbanCommand}: Unban a user from using the contact feature (Sudo only).
"""

# Settings & Configuration page
settings_commands = f"""
<b>⚙️ Settings & Configuration</b>

/{BotCommands.UserSetCommand[0]} or /{BotCommands.UserSetCommand[1]} or /{BotCommands.UserSetCommand[2]} [query]: Users settings.
/{BotCommands.BotSetCommand} [query]: Bot settings (Owner & Sudo only).
/{BotCommands.MediaToolsCommand[0]} or /{BotCommands.MediaToolsCommand[1]}: Media tools settings for watermark and other media features.
/{BotCommands.MediaToolsHelpCommand[0]} or /{BotCommands.MediaToolsHelpCommand[1]}: View detailed help for merge and watermark features.
/{BotCommands.FontStylesCommand[0]} or /{BotCommands.FontStylesCommand[1]}: View available font styles for leech.
/{BotCommands.RssCommand}: Subscribe to RSS feeds (Owner only).
"""

# AI & Special Features page
special_commands = f"""
<b>🤖 AI & Special Features</b>

/{BotCommands.AskCommand}: Chat with AI using the bot (Mistral or DeepSeek).
/{BotCommands.TruecallerCommand}: Lookup phone numbers using Truecaller.
/{BotCommands.OSINTCommand}: Comprehensive OSINT intelligence suite with phone, IP, email, user, and vehicle lookup capabilities (Sudo only).
/{BotCommands.EncodeCommand[0]} or /{BotCommands.EncodeCommand[1]} [query]: Encode text using various encoding methods (Base64, Binary, Cryptography, etc.).
/{BotCommands.DecodeCommand[0]} or /{BotCommands.DecodeCommand[1]} [query]: Decode text using various decoding methods.
/{BotCommands.QuickInfoCommand[0]} or /{BotCommands.QuickInfoCommand[1]} [chat]: Get chat/user information with interactive buttons.
/{BotCommands.File2LinkCommand}: Convert Telegram media files into direct streaming links with browser player support.
/{BotCommands.WhisperCommand}: Send private whisper messages in group chats (reply to user or use -to flag for multiple targets).
/{BotCommands.NekoCommand}: Get adorable cat images with voting system 🐱💕 (use /neko or /neko [number] for multiple cats).
/{BotCommands.WeatherCommand[0]} or /{BotCommands.WeatherCommand[1]} [location]: Get comprehensive weather information with beautiful images, forecasts, air quality data, and interactive features.
/{BotCommands.ShortnerCommand} [url] [alias]: Shorten URLs with Bitly API and generate professional QR codes with optional custom aliases.
/{BotCommands.QRCodeCommand} [text/URL] [options]: Generate QR codes from text or URLs with customizable styles, colors, formats (PNG/JPEG/SVG), and error correction levels.
"""

# System Commands page
system_commands = f"""
<b>🛠️ System Commands (Owner & Sudo only)</b>

/{BotCommands.RestartCommand[0]} or /{BotCommands.RestartCommand[1]}: Restart and update the bot.
/{BotCommands.LogCommand}: Get the bot log file.
/{BotCommands.ShellCommand}: Execute shell commands.
/{BotCommands.ExecCommand}: Execute sync functions.
/{BotCommands.AExecCommand}: Execute async functions.
/{BotCommands.ClearLocalsCommand}: Clear locals in exec functions.
/{BotCommands.BroadcastCommand[0]} or /{BotCommands.BroadcastCommand[1]}: Broadcast a message to bot users.
# IndexCommand removed - media indexing functionality disabled
"""

# File2Link Commands page
f2l_commands = f"""
<b>🔗 File2Link Commands</b>

/{BotCommands.File2LinkCommand[0]} or /{BotCommands.File2LinkCommand[1]}: Convert Telegram media files into direct streaming links. Reply to any media file to generate streaming and download links.

<b>Features:</b>
• Stream files directly in browser with media player
• Generate direct download links
• Support for videos, audio, documents, images, and more
• Automatic file size detection (2GB for non-premium, 4GB for premium accounts)
• Multi-client load balancing for optimal performance
• Secure hash-based access control

<b>Usage:</b>
1. Send or forward a media file to the bot
2. Reply to the media file with /{BotCommands.File2LinkCommand[0]} or /{BotCommands.File2LinkCommand[1]}
3. Get streaming and download links with inline buttons

<b>Supported File Types:</b>
• Videos (MP4, MKV, AVI, etc.)
• Audio (MP3, FLAC, M4A, etc.)
• Documents (PDF, ZIP, etc.)
• Images (JPG, PNG, etc.)
• Animations (GIF, etc.)
• Voice messages and video notes

<b>Requirements:</b>
• FILE2LINK_ENABLED must be True in config
• BASE_URL or FILE2LINK_BASE_URL must be configured
• BIN_CHANNEL must be set for file storage
"""

# File2Link Help Dictionary
F2L_HELP_DICT = {
    "main": f2l_commands,
}

# Help page
help_commands = f"""
<b>❓ Help</b>

/{BotCommands.HelpCommand}: Show this help message.
"""

# Dictionary to store all help pages (moved after all command definitions)
help_string = {
    "main": main_help_string,
    "download": download_commands,
    "status": status_commands,
    "search": search_commands,
    "file": file_commands,
    "security": security_commands,
    "settings": settings_commands,
    "special": special_commands,
    "system": system_commands,
    "help": help_commands,
}
