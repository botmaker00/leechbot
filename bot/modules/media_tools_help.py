#!/usr/bin/env python3
from asyncio import create_task
from logging import getLogger

from bot.helper.telegram_helper.button_build import ButtonMaker

# No need to import help_messages as we've included the content directly
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

LOGGER = getLogger(__name__)


# Define page content functions
def get_page_content(page_num):
    pages = {
        # Merge pages
        1: get_merge_intro_page(),
        2: get_merge_video_page(),
        3: get_merge_audio_page(),
        4: get_merge_subtitle_page(),
        5: get_merge_image_page(),
        6: get_merge_document_page(),
        7: get_merge_mixed_page(),
        8: get_merge_notes_page(),
        # Watermark pages
        9: get_watermark_intro_page(),
        10: get_watermark_settings_page(),
        11: get_watermark_settings_page_2(),
        # Convert pages
        12: get_convert_intro_page(),
        # Compression pages
        13: get_compression_intro_page(),
        14: get_compression_advanced_page(),
        # Trim pages
        15: get_trim_intro_page(),
        16: get_trim_settings_page(),
        # Extract pages
        17: get_extract_intro_page(),
        18: get_extract_settings_page(),
        # Remove pages
        19: get_remove_intro_page(),
        20: get_remove_settings_page(),
        # Add pages
        21: get_add_intro_page_1(),
        22: get_add_intro_page_2(),
        23: get_add_settings_page(),
        # Swap pages
        24: get_swap_intro_page(),
        25: get_swap_settings_page(),
        # Other pages
        26: get_priority_guide_page(),
        27: get_usage_examples_page_1(),
        28: get_usage_examples_page_2(),
        # Metadata page
        29: get_metadata_guide_page(),
        # MT Flag page
        30: get_mt_flag_guide_page(),
    }
    return pages.get(page_num, "Invalid page")


def get_merge_intro_page():
    msg = "<b>Merge Feature Guide (1/24)</b>\n\n"
    msg += "<b>Merge Flags</b>: -merge-video -merge-audio -merge-subtitle -merge-image -merge-pdf -merge-all\n\n"

    msg += "<b>Usage</b>:\n"
    msg += "• <code>/cmd link -merge-video</code> - Merge video files\n"
    msg += "• <code>/cmd link -merge-audio</code> - Merge audio files\n"
    msg += "• <code>/cmd link -merge-subtitle</code> - Merge subtitle files\n"
    msg += "• <code>/cmd link -merge-image</code> - Create image collage/grid\n"
    msg += "• <code>/cmd link -merge-pdf</code> - Combine PDF documents\n"
    msg += "• <code>/cmd link -merge-all</code> - Merge all files by type\n\n"

    msg += "<b>Multi-Link & Bulk Usage</b>:\n"
    msg += "• <code>/cmd link -m folder_name -merge-video</code>\n"
    msg += "• <code>/cmd -b -m folder_name -merge-all</code> (reply to links)\n"
    msg += "The <code>-m folder_name</code> argument places files in same directory.\n\n"

    msg += "<b>Supported Merge Types</b>:\n"
    msg += "• <b>Video</b>: Multiple videos → single video file\n"
    msg += "  - <code>-merge-video</code> preserves all tracks\n"
    msg += "• <b>Audio</b>: Multiple audio files → single audio file\n"
    msg += "• <b>Subtitle</b>: Multiple subtitle files → single subtitle\n"
    msg += "• <b>Mixed</b>: Video + Audio + Subtitle → complete media\n"
    msg += "• <b>Image</b>: Multiple images → collage/grid\n"
    msg += "• <b>PDF</b>: Multiple PDFs → single document\n"
    msg += "  - <code>-merge-all</code> merges all files by type\n\n"

    msg += "<b>Key Settings</b>:\n"
    msg += "• <b>Method</b>: Concat Demuxer (fast) or Filter Complex (compatible)\n"
    msg += "• <b>Output Format</b>: Format for merged files (mkv, mp4, mp3, etc.)\n"
    msg += "• <b>RO</b>: Remove original files after merging\n\n"

    msg += "<b>Important Notes</b>:\n"
    msg += "• Files are merged in the order provided\n"
    msg += "• Use MKV format for best track preservation\n"
    msg += "• The rename flag (-n) won't work with merge operations\n"
    msg += "• Configure advanced settings with /mediatools command\n"

    return msg


def get_merge_video_page():
    msg = "<b>Video Merging (2/22)</b>\n\n"
    msg += "<b>Video Merging Features</b>:\n"
    msg += "• Combines multiple video files into a single file\n"
    msg += "• Preserves video quality and aspect ratio when possible\n"
    msg += "• Preserves all video and subtitle tracks with -merge-video flag\n"
    msg += "• Supports different codecs (h264, h265, vp9, av1)\n"
    msg += "• Handles videos with different resolutions and framerates\n\n"

    msg += "<b>Supported Formats</b>:\n"
    msg += "• <b>Input</b>: MP4, MKV, AVI, MOV, WebM, FLV, WMV, M4V, TS, 3GP\n"
    msg += "• <b>Output</b>: MKV (default), MP4, WebM, AVI\n"
    msg += "• <b>Codecs</b>: copy (default), h264, h265, vp9, av1\n\n"

    msg += "<b>Merging Methods</b>:\n"
    msg += "• <b>Concat Demuxer</b>: Fast method for similar format files\n"
    msg += "• <b>Filter Complex</b>: Compatible method for different formats\n\n"

    msg += "<b>Tips for Best Results</b>:\n"
    msg += "• Use MKV container for best codec compatibility\n"
    msg += "• 'copy' codec preserves quality (requires similar sources)\n"
    msg += "• For different codecs/formats, use filter complex method\n"
    msg += "• CRF values: 18-23 (high quality), 23-28 (medium quality)\n"

    return msg


def get_merge_audio_page():
    msg = "<b>Audio Merging (3/22)</b>\n\n"
    msg += "<b>Audio Merging Features</b>:\n"
    msg += "• Combines multiple audio files into a single audio file\n"
    msg += "• Preserves audio quality when possible\n"
    msg += "• Supports various audio codecs (AAC, MP3, OPUS, FLAC)\n"
    msg += "• Handles different bitrates, sampling rates, and channels\n"
    msg += "• Volume normalization available in settings\n\n"

    msg += "<b>Supported Formats</b>:\n"
    msg += "• <b>Input</b>: MP3, M4A, AAC, FLAC, WAV, OGG, OPUS, WMA\n"
    msg += "• <b>Output</b>: MP3 (default), M4A, FLAC, WAV, OGG\n"
    msg += "• <b>Codecs</b>: copy (default), aac, mp3, opus, flac\n\n"

    msg += "<b>Audio Format Tips</b>:\n"
    msg += "• MP3: Widely compatible but lossy\n"
    msg += "• FLAC: Preserves quality but larger files\n"
    msg += "• AAC: Good quality-to-size ratio\n"
    msg += "• Mono audio (1 channel): Smaller files for speech\n"
    msg += "• 192kbps: Good balance for most content\n"

    return msg


def get_merge_subtitle_page():
    msg = "<b>Subtitle Merging (4/22)</b>\n\n"
    msg += "<b>Subtitle Merging Features</b>:\n"
    msg += "• Merges multiple subtitle files into a single file\n"
    msg += "• Preserves timing and sequence of subtitles\n"
    msg += "• Merges different subtitle formats (SRT, VTT, ASS, SSA)\n"
    msg += "• Maintains styling in advanced formats like ASS\n\n"

    msg += "<b>Supported Formats</b>:\n"
    msg += "• <b>Input</b>: SRT, VTT, ASS, SSA, SUB, SBV, LRC, TTML\n"
    msg += "• <b>Output</b>: SRT (default), VTT, ASS, SSA\n"
    msg += "• <b>Features</b>: Text formatting, timing preservation\n\n"

    msg += "<b>Subtitle Format Tips</b>:\n"
    msg += "• SRT: Most compatible but basic styling\n"
    msg += "• ASS/SSA: Advanced styling (colors, positioning, fonts)\n"
    msg += "• Different timings are concatenated sequentially\n"
    msg += "• Use language codes in filenames (movie.en.srt, movie.es.srt)\n"
    msg += "• UTF-8 encoding recommended for best compatibility\n"

    return msg


def get_merge_image_page():
    msg = "<b>Image Merging (5/22)</b>\n\n"
    msg += "<b>Image Merging Modes</b>:\n"
    msg += "• <b>Collage</b> - Grid layout (default for 3+ images)\n"
    msg += "• <b>Horizontal</b> - Side by side (default for 2 images)\n"
    msg += "• <b>Vertical</b> - Stacked on top of each other\n\n"

    msg += "<b>Supported Formats</b>:\n"
    msg += "• <b>Input</b>: JPG, JPEG, PNG, GIF, BMP, WebP, TIFF, HEIC\n"
    msg += "• <b>Output</b>: JPG (default), PNG, WebP, TIFF\n"
    msg += "• <b>Features</b>: Resolution preservation, quality settings\n\n"

    msg += "<b>Image Format Tips</b>:\n"
    msg += "• JPG: Good compression but lossy (quality loss)\n"
    msg += "• PNG: Preserves quality but larger files\n"
    msg += "• WebP: Good balance between quality and size\n"
    msg += "• Customize columns in Media Tools settings\n"
    msg += "• Background color can be changed (default: white)\n"
    msg += "• Images can be resized for uniform appearance\n"

    return msg


def get_merge_document_page():
    msg = "<b>Document Merging (6/22)</b>\n\n"
    msg += "<b>Document Merging Features</b>:\n"
    msg += "• Currently supports merging PDF files\n"
    msg += "• All PDF pages preserved in merged document\n"
    msg += "• Maintains original page order\n"
    msg += "• Preserves document metadata when possible\n\n"

    msg += "<b>Supported Formats</b>:\n"
    msg += "• <b>Input</b>: PDF\n"
    msg += "• <b>Output</b>: PDF\n"
    msg += "• <b>Features</b>: Page order preservation, metadata retention\n\n"

    msg += "<b>PDF Merging Tips</b>:\n"
    msg += "• Works best with similar document types\n"
    msg += "• Page size and orientation are preserved\n"
    msg += "• Bookmarks from original PDFs are preserved\n"
    msg += "• Password-protected PDFs are automatically skipped\n"
    msg += "• Use -merge-pdf flag for PDF-only merging\n"
    msg += "• Powered by PyMuPDF for fast and reliable processing\n"

    return msg


def get_merge_mixed_page():
    msg = "<b>Mixed Media Merging (7/22)</b>\n\n"
    msg += "<b>Mixed Media Merging Features</b>:\n"
    msg += "• <b>Video + Audio</b>: Adds audio tracks to video files\n"
    msg += "• <b>Video + Subtitle</b>: Embeds subtitle tracks in videos\n"
    msg += "• <b>Video + Audio + Subtitle</b>: Creates complete package\n"
    msg += "• <b>Multiple Audio Tracks</b>: Multiple language options\n"
    msg += "• <b>Multiple Subtitle Tracks</b>: Multiple language options\n\n"

    msg += "<b>Mixed Merging Guide</b>:\n"
    msg += "1. Place files in same directory: <code>-m folder_name</code>\n"
    msg += "2. Use <code>-merge-all</code> to detect and merge compatible files\n"
    msg += "3. File naming for proper track matching:\n"
    msg += "   • Similar base names (video.mp4, video.srt, video.mp3)\n"
    msg += "   • Language codes (movie.mp4, movie.en.srt, movie.es.srt)\n\n"

    msg += "<b>Advanced Configuration</b>:\n"
    msg += "• Track selection and ordering\n"
    msg += "• Default audio/subtitle language\n"
    msg += "• Audio sync adjustment\n"
    msg += "• Audio normalization options\n"
    msg += "• MKV container recommended for mixed media\n"

    return msg


def get_merge_notes_page():
    msg = "<b>Merge Notes & Advanced Features (8/22)</b>\n\n"

    msg += "<b>Important Considerations</b>:\n"
    msg += "• File order is preserved during merging\n"
    msg += "• <code>-merge-video</code> and <code>-merge-all</code> preserve all tracks\n"
    msg += "• Mixed media works best with MKV container format\n"
    msg += "• Some combinations require transcoding (affects quality)\n"
    msg += "• Large files need more processing time and resources\n"
    msg += "• Original files can be preserved or removed (configurable)\n\n"

    msg += "<b>Best Practices</b>:\n"
    msg += "• Use MKV container for versatile track support\n"
    msg += "• Keep filenames consistent for better matching\n"
    msg += "• Use language codes for multi-language content\n"
    msg += "• Process similar files together for best results\n"
    msg += "• Test with smaller files before large merges\n"
    msg += "• If merge fails, try filter complex method\n"
    msg += "• Use 'copy' codec when possible to preserve quality\n\n"

    msg += "<b>Advanced Features</b>:\n"
    msg += "• <b>Concat Demuxer</b>: Fast for files with identical codecs\n"
    msg += "• <b>Filter Complex</b>: For files with different codecs\n"
    msg += "• <b>Output Format</b>: Choose format (mkv, mp4, mp3, etc.)\n"
    msg += "• <b>Threading</b>: Process multiple files simultaneously\n\n"

    msg += "<b>Important Notes</b>:\n"
    msg += "• Use -m flag to place files in the same directory\n"
    msg += "• Rename flag (-n) won't work with merge operations\n"
    msg += "• Identical filenames may cause merging issues\n"
    msg += "• Configure advanced settings with /mediatools command\n"

    return msg


def get_watermark_intro_page():
    msg = "<b>Watermark Feature Guide (9/26)</b>\n\n"
    msg += "<b>Watermark Feature</b>\n"
    msg += "Add text or image overlays to videos, images, audio files, and subtitles with customizable appearance.\n\n"

    msg += "<b>Important:</b> Make sure to enable watermark in Media Tools settings before using this feature.\n\n"

    msg += "<b>How to Use Text Watermark</b>:\n"
    msg += "Add the <code>-watermark</code> flag (or <code>-wm</code> shortcut) followed by your text in quotes:\n"
    msg += '<code>/leech https://example.com/video.mp4 -watermark "© My Channel"</code>\n\n'

    msg += "<b>How to Use Image Watermark</b>:\n"
    msg += "Add the <code>-iwm</code> flag followed by the path to your image:\n"
    msg += "<code>/leech https://example.com/video.mp4 -iwm /path/to/logo.png</code>\n\n"

    msg += "You can also use it without any flags. You can set the text/image and other settings in Media Tools settings. Then run the command:\n"
    msg += "<code>/leech https://example.com/video.mp4</code>\n\n"

    msg += "<b>RO Files</b>:\n"
    msg += "By default, watermarking will replace the original file. To keep both the original and watermarked files, you can:\n"
    msg += "• Set 'RO' to OFF in /mediatools > Watermark > Configure\n"
    msg += "• Use the <code>-del</code> flag to control this behavior:\n"
    msg += '<code>/leech https://example.com/video.mp4 -watermark "© My Channel" -del f</code> (keep original)\n'
    msg += '<code>/leech https://example.com/video.mp4 -watermark "© My Channel" -del t</code> (remove original)\n\n'

    msg += "<b>Supported Media Types</b>:\n"
    msg += "• <b>Videos</b>: MP4, MKV, AVI, MOV, WebM, FLV, etc.\n"
    msg += "• <b>Images</b>: JPG, PNG, WebP, BMP, GIF, etc.\n"
    msg += "• <b>Audio</b>: MP3, WAV, FLAC, AAC, OGG, etc.\n"
    msg += "• <b>Subtitles</b>: SRT, ASS, SSA, VTT\n\n"

    msg += "<b>Watermark Types</b>:\n"
    msg += "• <b>Text Watermark</b>: Text overlay on videos and images\n"
    msg += "• <b>Image Watermark</b>: Image overlay on videos and images\n"
    msg += "• <b>Audio Watermark</b>: Sound markers in audio files\n"
    msg += "• <b>Subtitle Watermark</b>: Text added to subtitle files\n\n"

    msg += "Each type can be configured in Media Tools settings. Text and image watermarks can be used together or separately.\n\n"

    msg += "<b>Priority Settings</b>:\n"
    msg += "• Command line watermark text takes highest priority\n"
    msg += "• User settings take priority over owner settings\n"
    msg += "• Owner settings are used as fallback\n"
    msg += "• Default watermark priority is 2 (runs after merge feature)\n\n"

    return msg


def get_watermark_settings_page():
    msg = "<b>Watermark Settings (10/26)</b>\n\n"

    msg += "<b>Text Watermark Settings</b>:\n"
    msg += "• <b>Text</b>: The text to display as watermark\n"
    msg += "• <b>Position</b>: Where to place the watermark\n"
    msg += "• <b>Size</b>: Font size of the watermark text\n"
    msg += "• <b>Color</b>: Color of the watermark text\n"
    msg += "• <b>Font</b>: Font file to use (supports Google Fonts)\n"
    msg += "• <b>Opacity</b>: Transparency level of watermark (0.0-1.0)\n"
    msg += "• <b>RO</b>: Delete original file after watermarking\n\n"

    msg += "<b>Image Watermark Settings</b>:\n"
    msg += "• <b>Image WM</b>: Enable/disable image watermarking\n"
    msg += "• <b>Image Path</b>: Path to the watermark image file\n"
    msg += (
        "• <b>Image Scale</b>: Size of image as percentage of video width (1-100)\n"
    )
    msg += "• <b>Image Position</b>: Where to place the image watermark\n"
    msg += "• <b>Image Opacity</b>: Transparency level of image (0.0-1.0)\n\n"

    msg += "<b>Position Options</b>:\n"
    msg += "• top_left, top_right, bottom_left, bottom_right\n"
    msg += "• center, top_center, bottom_center\n"
    msg += "• left_center, right_center\n\n"

    msg += "<b>Color Options</b>:\n"
    msg += "• Basic colors: white, black, red, blue, green, yellow\n"
    msg += "• Hex colors: #RRGGBB format (e.g., #FF0000 for red)\n\n"

    msg += "<b>See next page for audio and subtitle watermark settings</b>"

    return msg


def get_watermark_settings_page_2():
    msg = "<b>Watermark Settings (continued) (11/26)</b>\n\n"

    msg += "<b>Audio Watermark Settings</b>:\n"
    msg += "• <b>Audio WM</b>: Enable/disable audio watermarking\n"
    msg += "• <b>Audio Text</b>: Custom text for audio watermarks\n"
    msg += "• <b>Audio Volume</b>: Volume level of audio watermark (0.0-1.0)\n\n"

    msg += "<b>Subtitle Watermark Settings</b>:\n"
    msg += "• <b>Subtitle WM</b>: Enable/disable subtitle watermarking\n"
    msg += "• <b>Subtitle Text</b>: Custom text for subtitle watermarks\n"
    msg += "• <b>Subtitle Style</b>: Styling for subtitle watermarks (normal, bold, italic)\n\n"

    msg += "<b>Font Options</b>:\n"
    msg += "• Default system fonts or Google Fonts (e.g., Roboto, Open Sans)\n"
    msg += "• Custom fonts: Path to .ttf or .otf file\n"
    msg += "• Sans-serif fonts recommended for better readability\n\n"

    msg += "<b>Advanced Settings</b>:\n"
    msg += "• <b>Threading</b>: Process multiple files simultaneously\n"
    msg += "• <b>Thread Number</b>: Number of parallel processing threads\n"
    msg += "• <b>Quality</b>: Controls output quality (higher = better quality)\n"
    msg += "• <b>Speed</b>: Controls processing speed (faster = lower quality)\n\n"

    msg += "<b>Tips for Best Results</b>:\n"
    msg += "• For image watermarks, use PNG with transparency\n"
    msg += "• For text watermarks, use contrasting colors with opacity\n"
    msg += "• For audio watermarks, use moderate volume (0.2-0.3)\n"
    msg += "• For subtitle watermarks, use simple text for compatibility\n\n"

    msg += "<b>Command Examples</b>:\n"
    msg += '• <code>/leech video.mp4 -wm "© Channel" -del f</code> (keep original)\n'
    msg += "• <code>/mirror video.mp4 -iwm logo.png</code> (image watermark)\n"
    msg += '• <code>/leech video.mp4 -wm "Text" -iwm logo.png</code> (both types)\n'

    return msg


def get_convert_intro_page():
    msg = "<b>Convert Feature Guide (12/26)</b>\n\n"
    msg += "<b>Convert Feature</b>\n"
    msg += "Convert media files to different formats with customizable settings.\n\n"

    msg += "<b>Important:</b> Make sure to enable convert in Media Tools settings before using this feature.\n\n"

    msg += "<b>Basic Usage</b>:\n"
    msg += "• <code>-cv format</code>: Convert videos (e.g., <code>-cv mp4</code>)\n"
    msg += "• <code>-ca format</code>: Convert audio (e.g., <code>-ca mp3</code>)\n"
    msg += (
        "• <code>-cs format</code>: Convert subtitles (e.g., <code>-cs srt</code>)\n"
    )
    msg += (
        "• <code>-cd format</code>: Convert documents (e.g., <code>-cd pdf</code>)\n"
    )
    msg += (
        "• <code>-cr format</code>: Convert archives (e.g., <code>-cr zip</code>)\n"
    )
    msg += "• <code>-del</code>: Delete original files after conversion\n\n"

    msg += "<b>Examples</b>:\n"
    msg += "<code>/leech https://example.com/video.webm -cv mp4</code>\n"
    msg += "<code>/mirror https://example.com/audio.wav -ca mp3</code>\n"
    msg += "<code>/leech https://example.com/subtitles.ass -cs srt</code>\n"
    msg += "<code>/mirror https://example.com/document.docx -cd pdf</code>\n"
    msg += "<code>/leech https://example.com/files.rar -cr zip</code>\n\n"

    msg += "<b>Supported Media Types</b>:\n"
    msg += "• <b>Videos</b>: MP4, MKV, AVI, MOV, WebM, FLV, WMV, M4V, TS, 3GP\n"
    msg += "• <b>Audio</b>: MP3, M4A, FLAC, WAV, OGG, OPUS, AAC, WMA, ALAC\n"
    msg += "• <b>Subtitles</b>: SRT, ASS, SSA, VTT, WebVTT, SUB, SBV\n"
    msg += "• <b>Documents</b>: PDF, DOCX, TXT, ODT, RTF\n"
    msg += "• <b>Archives</b>: ZIP, RAR, 7Z, TAR, GZ, BZ2\n\n"

    msg += '<blockquote expandable="expandable"><b>Convert Options</b>:\n'
    msg += "• <b>Video Format</b>: Output format for videos (mp4, mkv, avi, webm)\n"
    msg += "• <b>Video Codec</b>: Encoding codec (h264, h265, vp9, av1)\n"
    msg += "• <b>Video Quality</b>: Encoding preset (ultrafast to veryslow)\n"
    msg += "• <b>Video CRF</b>: Quality factor (0-51, lower is better)\n"
    msg += "• <b>Video Preset</b>: Encoding speed vs compression ratio\n"
    msg += "• <b>Maintain Quality</b>: Preserve high quality during conversion\n"
    msg += (
        "• <b>Audio Format</b>: Output format for audio (mp3, m4a, flac, wav, ogg)\n"
    )
    msg += "• <b>Audio Codec</b>: Encoding codec (mp3, aac, opus, flac)\n"
    msg += "• <b>Audio Bitrate</b>: Quality setting (128k, 192k, 320k)\n"
    msg += "• <b>Audio Channels</b>: Mono (1) or stereo (2)\n"
    msg += "• <b>Audio Sampling</b>: Sample rate in Hz (44100, 48000)\n"
    msg += "• <b>Audio Volume</b>: Volume adjustment (1.0 = original)\n"
    msg += "• <b>Subtitle Format</b>: Output format for subtitles (srt, ass, vtt)\n"
    msg += "• <b>Document Format</b>: Output format for documents (pdf, docx, txt)\n"
    msg += "• <b>Archive Format</b>: Output format for archives (zip, 7z, tar)</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Advanced Usage</b>:\n'
    msg += "• <b>Convert specific formats</b>:\n"
    msg += "<code>/leech https://example.com/videos.zip -cv mp4 + webm flv</code>\n"
    msg += "This will convert only WebM and FLV videos to MP4\n\n"
    msg += "• <b>Exclude specific formats</b>:\n"
    msg += "<code>/mirror https://example.com/audios.zip -ca mp3 - wav</code>\n"
    msg += "This will convert all audio formats to MP3 except WAV files\n\n"
    msg += "• <b>Combined conversions</b>:\n"
    msg += (
        "<code>/leech https://example.com/media.zip -cv mp4 -ca mp3 -cs srt</code>\n"
    )
    msg += "This will convert videos to MP4, audios to MP3, and subtitles to SRT\n\n"
    msg += "• <b>Delete originals</b>:\n"
    msg += "<code>/leech https://example.com/video.webm -cv mp4 -del</code>\n"
    msg += (
        "This will convert the video and delete the original file</blockquote>\n\n"
    )

    msg += "<b>Configuration</b>:\n"
    msg += "• Enable convert in Media Tools settings\n"
    msg += "• Enable specific media type conversions (video, audio, etc.)\n"
    msg += "• Set default formats and codecs for each media type\n"
    msg += "• Configure quality settings for optimal results\n"
    msg += "• Set priority to control when conversion runs in the pipeline\n\n"

    return msg


def get_compression_intro_page():
    msg = "<b>Compression Feature Guide (13/26)</b>\n\n"
    msg += "<b>Compression Feature</b>\n"
    msg += "Compress media files to reduce file size while maintaining acceptable quality.\n\n"

    msg += "<b>Important:</b> Enable compression in Media Tools settings before using this feature.\n\n"

    msg += "<b>How to Use</b>:\n"
    msg += "Add compression flags to your download commands:\n"
    msg += "<code>/leech https://example.com/video.mp4 -video-fast</code> (fast video compression)\n"
    msg += "<code>/mirror https://example.com/audio.mp3 -audio-medium</code> (medium audio compression)\n"
    msg += "<code>/leech https://example.com/image.png -image-slow</code> (thorough image compression)\n"
    msg += "<code>/mirror https://example.com/archive.zip -archive-medium</code> (archive compression)\n\n"

    msg += "Or use the general compression flag:\n"
    msg += "<code>/leech https://example.com/video.mp4 -compress</code>\n\n"

    msg += "<b>Well-Supported Media Types</b>:\n"
    msg += "• <b>Videos</b>: MP4, MKV, AVI, MOV, WebM, FLV, WMV, M4V, TS, 3GP\n"
    msg += "• <b>Audio</b>: MP3, M4A, FLAC, WAV, OGG, OPUS, AAC, WMA\n"
    msg += "• <b>Images</b>: JPG, JPEG, PNG, GIF, BMP, WebP, TIFF\n"
    msg += "• <b>Archives</b>: ZIP, RAR, 7Z, TAR, GZ, BZ2\n\n"

    msg += '<blockquote expandable="expandable"><b>Compression Presets</b>:\n'
    msg += "Each media type supports three compression presets:\n"
    msg += "• <b>Fast</b>: Quick compression with moderate file size reduction\n"
    msg += "• <b>Medium</b>: Balanced compression with good file size reduction\n"
    msg += "• <b>Slow</b>: Thorough compression with maximum file size reduction\n\n"

    msg += "Usage examples:\n"
    msg += "<code>/leech https://example.com/video.mp4 -video-fast</code>\n"
    msg += "<code>/mirror https://example.com/audio.mp3 -audio-medium</code>\n"
    msg += "<code>/leech https://example.com/image.png -image-slow</code>\n"
    msg += "<code>/mirror https://example.com/archive.zip -archive-slow</code></blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Video Compression</b>:\n'
    msg += "• <b>Preset</b>: Fast, medium, or slow compression\n"
    msg += "• <b>CRF</b>: Quality factor (higher values = smaller files but lower quality)\n"
    msg += "• <b>Codec</b>: Encoding codec (h264, h265, etc.)\n"
    msg += "• <b>Format</b>: Output format (mp4, mkv, etc.)\n\n"

    msg += "The fast preset uses higher CRF values and faster encoding settings, while the slow preset uses lower CRF values for better quality.</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Audio Compression</b>:\n'
    msg += "• <b>Preset</b>: Fast, medium, or slow compression\n"
    msg += "• <b>Codec</b>: Encoding codec (aac, mp3, opus, etc.)\n"
    msg += "• <b>Bitrate</b>: Target bitrate (lower = smaller files)\n"
    msg += "• <b>Channels</b>: Mono (1) or stereo (2)\n\n"

    msg += "The fast preset uses lower bitrates, while the slow preset uses more efficient encoding algorithms.</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Image Compression</b>:\n'
    msg += "• <b>Preset</b>: Fast, medium, or slow compression\n"
    msg += "• <b>Quality</b>: JPEG/WebP quality factor (0-100)\n"
    msg += "• <b>Resize</b>: Optional downsizing of dimensions\n"
    msg += "• <b>Format</b>: Output format (jpg, png, webp)\n\n"

    msg += "The fast preset uses higher quality reduction, while the slow preset uses more advanced algorithms to maintain visual quality.</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Archive Compression</b>:\n'
    msg += "• <b>Preset</b>: Fast, medium, or slow compression\n"
    msg += "• <b>Level</b>: Compression level (1-9)\n"
    msg += "• <b>Method</b>: Compression algorithm (deflate, lzma, etc.)\n"
    msg += "• <b>Algorithm</b>: Archive type (7z, zip, tar)\n"
    msg += "• <b>Password</b>: Optional password protection (7z, zip, rar only)\n\n"

    msg += "The fast preset uses lower compression levels, while the slow preset uses maximum compression levels.</blockquote>\n\n"

    msg += "<b>Additional Options</b>:\n"
    msg += "• <code>-del</code>: Delete original files after compression\n"
    msg += "Example: <code>/leech https://example.com/video.mp4 -video-medium -del</code>\n\n"

    msg += "<b>Priority Settings</b>:\n"
    msg += "• Default compression priority is 4 (runs after merge, watermark, and convert)\n"
    msg += "• Command line flags take highest priority\n"
    msg += "• User settings take priority over owner settings\n\n"

    return msg


def get_compression_advanced_page():
    msg = "<b>Advanced Compression Settings (14/26)</b>\n\n"

    msg += "<b>Video Compression Details</b>:\n"
    msg += "• <b>Preset</b>: Controls encoding speed vs compression efficiency\n"
    msg += "  - Fast: Uses ultrafast/fast preset, higher CRF (28-30)\n"
    msg += "  - Medium: Uses medium preset, balanced CRF (23-26)\n"
    msg += "  - Slow: Uses slow/veryslow preset, lower CRF (18-22)\n"
    msg += "• <b>Codec</b>: H.264 (libx264) is default for compatibility\n"
    msg += "  - H.265 (libx265) offers better compression but less compatible\n"
    msg += "  - VP9 and AV1 are also available for specific needs\n"
    msg += "• <b>Format</b>: MP4 is default for compatibility\n"
    msg += "  - MKV supports more codecs and multiple tracks\n\n"

    msg += "<b>Audio Compression Details</b>:\n"
    msg += "• <b>Preset</b>: Controls encoding quality vs file size\n"
    msg += "  - Fast: Lower bitrates (96-128k)\n"
    msg += "  - Medium: Balanced bitrates (128-192k)\n"
    msg += "  - Slow: Higher quality bitrates (192-320k)\n"
    msg += "• <b>Codec</b>: AAC is default for compatibility\n"
    msg += "  - MP3 is widely supported but less efficient\n"
    msg += "  - OPUS offers better quality at lower bitrates\n"
    msg += "• <b>Channels</b>: Stereo (2) is default\n"
    msg += "  - Mono (1) reduces file size for speech content\n\n"

    msg += "<b>Image Compression Details</b>:\n"
    msg += "• <b>Preset</b>: Controls compression level\n"
    msg += "  - Fast: Higher quality reduction (quality 70-80)\n"
    msg += "  - Medium: Balanced quality (quality 80-90)\n"
    msg += "  - Slow: Better quality preservation (quality 90-95)\n"
    msg += "• <b>Format</b>: JPG is default for photos\n"
    msg += "  - PNG preserves transparency but larger files\n"
    msg += "  - WebP offers good balance of quality and size\n\n"

    msg += "<b>Archive Compression Details</b>:\n"
    msg += "• <b>Preset</b>: Controls compression level\n"
    msg += "  - Fast: Lower compression level (1-3)\n"
    msg += "  - Medium: Balanced compression level (5-7)\n"
    msg += "  - Slow: Maximum compression level (7-9)\n"
    msg += "• <b>Algorithm</b>: 7z is default for best compression\n"
    msg += "  - ZIP is more compatible but less efficient\n"
    msg += "  - Password protection only works with 7z, ZIP, and RAR\n\n"

    msg += "<b>Command Examples</b>:\n"
    msg += "• <code>/leech https://example.com/video.mp4 -video-medium -del</code>\n"
    msg += "• <code>/mirror https://example.com/audio.flac -audio-slow</code>\n"
    msg += "• <code>/leech https://example.com/images.zip -image-fast</code>\n"
    msg += "• <code>/mirror https://example.com/files.zip -archive-slow</code>\n\n"

    return msg


def get_trim_intro_page():
    msg = "<b>Trim Feature Guide (15/26)</b>\n\n"
    msg += "<b>Trim Feature</b>\n"
    msg += "Trim media files to extract specific portions based on start and end times.\n\n"

    msg += "<b>Important:</b> Make sure to enable trim in Media Tools settings before using this feature.\n\n"

    msg += "<b>How to Use</b>:\n"
    msg += "<b>For Media Files (Video/Audio):</b>\n"
    msg += "Add the <code>-trim</code> flag followed by the time range in format <code>start_time-end_time</code>:\n"
    msg += '<code>/leech https://example.com/video.mp4 -trim "00:01:30-00:02:45"</code>\n'
    msg += "This will extract the portion from 1 minute 30 seconds to 2 minutes 45 seconds.\n\n"

    msg += "You can also use it without specifying end time to trim from a specific point to the end:\n"
    msg += '<code>/mirror https://example.com/audio.mp3 -trim "00:30:00-"</code>\n'
    msg += (
        "This will extract the portion from 30 minutes to the end of the file.\n\n"
    )

    msg += "Or trim from the beginning to a specific point:\n"
    msg += '<code>/leech https://example.com/video.mp4 -trim "-00:05:00"</code>\n'
    msg += "This will extract the portion from the beginning to 5 minutes.\n\n"

    msg += "<b>For Documents (PDF):</b>\n"
    msg += "Add the <code>-trim</code> flag followed by the page range in format <code>start_page-end_page</code>:\n"
    msg += '<code>/leech https://example.com/document.pdf -trim "5-10"</code>\n'
    msg += "This will extract pages 5 to 10 from the PDF document.\n\n"

    msg += "You can also extract from a specific page to the end:\n"
    msg += '<code>/mirror https://example.com/document.pdf -trim "3-"</code>\n'
    msg += "This will extract from page 3 to the last page.\n\n"

    msg += "To delete the original file after trimming, add the <code>-del</code> flag:\n"
    msg += '<code>/leech https://example.com/video.mp4 -trim "00:01:30-00:02:45" -del</code>\n'
    msg += (
        '<code>/mirror https://example.com/document.pdf -trim "5-10" -del</code>\n'
    )
    msg += "This will trim the media/document and delete the original file after successful trimming.\n\n"

    msg += "<b>Supported Media Types</b>:\n"
    msg += "• <b>Videos</b>: MP4, MKV, AVI, MOV, WebM, FLV, WMV, etc.\n"
    msg += "• <b>Audio</b>: MP3, M4A, FLAC, WAV, OGG, OPUS, AAC, etc.\n"
    msg += "• <b>Images</b>: JPG, PNG, GIF, WebP, etc. (extracts frames)\n"
    msg += "• <b>Documents</b>: PDF (extracts specific pages)\n"
    msg += "• <b>Subtitles</b>: SRT, ASS, VTT, etc.\n"
    msg += "• <b>Archives</b>: ZIP, RAR, 7Z, etc. (extracts specific files)\n\n"

    msg += '<blockquote expandable="expandable"><b>Time Format (Media Files)</b>:\n'
    msg += "The trim feature supports several time formats for media files:\n"
    msg += "• <b>HH:MM:SS</b>: Hours, minutes, seconds (00:30:45)\n"
    msg += "• <b>MM:SS</b>: Minutes, seconds (05:30)\n"
    msg += "• <b>SS</b>: Seconds only (90)\n"
    msg += "• <b>Decimal seconds</b>: For precise trimming (00:01:23.456)\n\n"

    msg += "Media Examples:\n"
    msg += (
        '<code>/leech video.mp4 -trim "00:01:30-00:02:45"</code> (HH:MM:SS format)\n'
    )
    msg += '<code>/mirror audio.mp3 -trim "5:30-10:45"</code> (MM:SS format)\n'
    msg += '<code>/leech video.mp4 -trim "90-180"</code> (seconds only)\n'
    msg += '<code>/mirror audio.mp3 -trim "01:23.456-02:34.567"</code> (with decimal seconds)</blockquote>\n\n'

    msg += '<blockquote expandable="expandable"><b>Page Format (Documents)</b>:\n'
    msg += "For document files (PDF), use page numbers:\n"
    msg += "• <b>Page numbers</b>: Use integers starting from 1\n"
    msg += "• <b>Page ranges</b>: start_page-end_page format\n"
    msg += (
        "• <b>Open ranges</b>: Use dash (-) for end to extract until last page\n\n"
    )

    msg += "Document Examples:\n"
    msg += '<code>/leech document.pdf -trim "1-5"</code> (extract pages 1 to 5)\n'
    msg += (
        '<code>/mirror document.pdf -trim "10-25"</code> (extract pages 10 to 25)\n'
    )
    msg += (
        '<code>/leech document.pdf -trim "3-"</code> (extract from page 3 to end)\n'
    )
    msg += '<code>/mirror document.pdf -trim "1-1"</code> (extract only first page)</blockquote>\n\n'

    return msg


def get_trim_settings_page():
    msg = "<b>Trim Settings (16/26)</b>\n\n"

    msg += "<b>General Settings</b>:\n"
    msg += "• <b>Enable Trim</b>: Master toggle for the trim feature\n"
    msg += "• <b>Trim Priority</b>: Set the execution order (default: 5)\n"
    msg += "• <b>RO</b>: Remove original file after successful trim\n\n"

    msg += "<b>Media Type Settings</b>:\n"
    msg += "• <b>Video Trim</b>: Enable/disable trimming for video files\n"
    msg += "• <b>Audio Trim</b>: Enable/disable trimming for audio files\n"
    msg += "• <b>Image Trim</b>: Enable/disable trimming for image files\n"
    msg += "• <b>Document Trim</b>: Enable/disable trimming for document files\n"
    msg += "• <b>Subtitle Trim</b>: Enable/disable trimming for subtitle files\n"
    msg += "• <b>Archive Trim</b>: Enable/disable trimming for archive files\n\n"

    msg += "<b>Document Page Settings</b>:\n"
    msg += "• <b>Document Start Page</b>: Set the starting page number for document trimming (default: 1)\n"
    msg += "• <b>Document End Page</b>: Set the ending page number for document trimming (empty for last page)\n\n"

    msg += "<b>Format Settings</b>:\n"
    msg += (
        "• <b>Video Format</b>: Output format for trimmed videos (mp4, mkv, etc.)\n"
    )
    msg += (
        "• <b>Audio Format</b>: Output format for trimmed audio (mp3, m4a, etc.)\n"
    )
    msg += (
        "• <b>Image Format</b>: Output format for trimmed images (jpg, png, etc.)\n"
    )
    msg += (
        "• <b>Document Format</b>: Output format for trimmed documents (pdf, etc.)\n"
    )
    msg += (
        "• <b>Subtitle Format</b>: Output format for trimmed subtitles (srt, etc.)\n"
    )
    msg += (
        "• <b>Archive Format</b>: Output format for trimmed archives (zip, etc.)\n\n"
    )

    msg += '<blockquote expandable="expandable"><b>Codec Settings</b>:\n'
    msg += (
        "• <b>Video Codec</b>: Codec to use for video trimming (copy, h264, h265)\n"
    )
    msg += "• <b>Video Preset</b>: Encoding preset for video trimming (fast, medium, slow)\n"
    msg += "• <b>Audio Codec</b>: Codec to use for audio trimming (copy, aac, mp3)\n"
    msg += "• <b>Audio Preset</b>: Encoding preset for audio trimming (fast, medium, slow)\n"
    msg += "• <b>Image Quality</b>: Quality setting for image processing (0-100)\n"
    msg += "• <b>Document Quality</b>: Quality setting for document processing (0-100)\n"
    msg += "• <b>Subtitle Encoding</b>: Character encoding for subtitle files (UTF-8)</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Format Notes</b>:\n'
    msg += "• Setting any format to 'none' will use the original file format\n"
    msg += "• Format settings allow you to convert media during trimming\n"
    msg += "• For example, setting Video Format to 'mp4' will output MP4 files\n"
    msg += "• Format settings work with the -del flag to replace original files\n"
    msg += "• Command line format flags take priority over user settings\n"
    msg += (
        "• User format settings take priority over owner settings</blockquote>\n\n"
    )

    msg += '<blockquote expandable="expandable"><b>Special Media Handling</b>:\n'
    msg += "• <b>Videos</b>: Preserves all streams (video, audio, subtitles)\n"
    msg += "• <b>Audio</b>: Preserves metadata (artist, album, etc.)\n"
    msg += (
        "• <b>Images</b>: For static images, creates a copy with quality settings\n"
    )
    msg += "• <b>Animated GIFs</b>: Extracts specific frame ranges\n"
    msg += "• <b>Documents</b>: PDF trimming extracts specific page ranges using PyMuPDF\n"
    msg += "• <b>Subtitles</b>: Extracts entries within the specified time range\n"
    msg += "• <b>Archives</b>: Extracts specific files based on patterns</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Using the -del Flag</b>:\n'
    msg += "• Add <code>-del</code> to delete original files after trimming\n"
    msg += (
        '• Example: <code>/leech video.mp4 -trim "00:01:30-00:02:45" -del</code>\n'
    )
    msg += "• Saves space when you only need the trimmed portion\n"
    msg += "• The RO setting in the trim configuration has the same effect\n"
    msg += (
        "• Command line -del flag takes priority over user settings</blockquote>\n\n"
    )

    msg += "<b>Priority Settings</b>:\n"
    msg += "• Command line flags take highest priority\n"
    msg += "• User settings take priority over owner settings\n"
    msg += "• Owner settings are used as fallback\n"
    msg += "• Default settings are used if no others are specified\n\n"

    return msg


def get_extract_intro_page():
    msg = "<b>Extract Feature Guide (17/26)</b>\n\n"
    msg += "<b>Extract Feature</b>\n"
    msg += "Extract specific tracks (video, audio, subtitle, attachment) from media files.\n\n"

    msg += "<b>Important:</b> Make sure to enable extract in Media Tools settings before using this feature.\n\n"

    msg += "<b>How to Use</b>:\n"
    msg += "Add the <code>-extract</code> flag to extract all enabled track types:\n"
    msg += "<code>/leech https://example.com/video.mkv -extract</code>\n\n"

    msg += "Or specify track types to extract:\n"
    msg += "<code>/leech https://example.com/video.mkv -extract-video</code> (extract video tracks)\n"
    msg += "<code>/mirror https://example.com/video.mkv -extract-audio</code> (extract audio tracks)\n"
    msg += "<code>/leech https://example.com/video.mkv -extract-subtitle</code> (extract subtitle tracks)\n"
    msg += "<code>/mirror https://example.com/video.mkv -extract-attachment</code> (extract attachments)\n\n"

    msg += "You can also extract specific track indices (long format):\n"
    msg += "<code>/leech https://example.com/video.mkv -extract-video-index 0</code> (extract first video track)\n"
    msg += "<code>/mirror https://example.com/video.mkv -extract-audio-index 1</code> (extract second audio track)\n\n"

    msg += "Extract multiple tracks by specifying comma-separated indices:\n"
    msg += "<code>/leech https://example.com/video.mkv -extract-audio-index 0,1,2</code> (extract first, second, and third audio tracks)\n"
    msg += "<code>/mirror https://example.com/video.mkv -extract-subtitle-index 0,2</code> (extract first and third subtitle tracks)\n\n"

    msg += "Or use the shorter index flags:\n"
    msg += "<code>/leech https://example.com/video.mkv -vi 0</code> (extract first video track)\n"
    msg += "<code>/mirror https://example.com/video.mkv -ai 1</code> (extract second audio track)\n"
    msg += "<code>/leech https://example.com/video.mkv -si 2</code> (extract third subtitle track)\n"
    msg += "<code>/mirror https://example.com/video.mkv -ati 0</code> (extract first attachment)\n\n"

    msg += "Short flags also support multiple indices:\n"
    msg += "<code>/leech https://example.com/video.mkv -ai 0,1,2</code> (extract first, second, and third audio tracks)\n"
    msg += "<code>/mirror https://example.com/video.mkv -si 0,2</code> (extract first and third subtitle tracks)\n\n"

    msg += "<b>Supported Media Types</b>:\n"
    msg += "• <b>Container Formats</b>: MKV, MP4, AVI, MOV, WebM, FLV, WMV, M4V, TS, 3GP, MPEG, MPG, M2TS, MTS, OGV, etc.\n"
    msg += (
        "• <b>Video Codecs</b>: H.264, H.265, VP9, AV1, MPEG-4, MPEG-2, VC-1, etc.\n"
    )
    msg += "• <b>Audio Codecs</b>: AAC, MP3, OPUS, FLAC, AC3, DTS, EAC3, TrueHD, ALAC, etc.\n"
    msg += "• <b>Subtitle Formats</b>: SRT, ASS, SSA, VTT, STL, WebVTT, TTML, DFXP, SAMI, SBV, etc.\n"
    msg += "• <b>Attachments</b>: Fonts, images, and other embedded files\n\n"

    msg += '<blockquote expandable="expandable"><b>Extract Options</b>:\n'
    msg += "• <b>Video Extract</b>: Extract video tracks from container\n"
    msg += "• <b>Video Codec</b>: Output codec for video tracks (copy, h264, h265, etc.)\n"
    msg += "• <b>Video Index</b>: Specific video track to extract (0-based index)\n"
    msg += "• <b>Audio Extract</b>: Extract audio tracks from container\n"
    msg += "• <b>Audio Codec</b>: Output codec for audio tracks (copy, aac, mp3, etc.)\n"
    msg += "• <b>Audio Index</b>: Specific audio track to extract (0-based index)\n"
    msg += "• <b>Subtitle Extract</b>: Extract subtitle tracks from container\n"
    msg += "• <b>Subtitle Codec</b>: Output codec for subtitle tracks (copy, srt, ass, etc.)\n"
    msg += "• <b>Subtitle Index</b>: Specific subtitle track to extract (0-based index)\n"
    msg += "• <b>Attachment Extract</b>: Extract attachments from container\n"
    msg += (
        "• <b>Attachment Index</b>: Specific attachment to extract (0-based index)\n"
    )
    msg += "• <b>Maintain Quality</b>: Preserve high quality during extraction</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Advanced Usage</b>:\n'
    msg += "• <b>Extract multiple track types</b>:\n"
    msg += "<code>/leech https://example.com/video.mkv -extract-video -extract-audio</code>\n"
    msg += "This will extract both video and audio tracks\n\n"
    msg += "• <b>Extract specific tracks by index</b>:\n"
    msg += "<code>/mirror https://example.com/video.mkv -extract-audio-index 0,2</code>\n"
    msg += "This will extract the first and third audio tracks\n\n"
    msg += "• <b>Extract multiple tracks with short flags</b>:\n"
    msg += "<code>/leech https://example.com/video.mkv -ai 0,1,2 -si 0,1</code>\n"
    msg += "This will extract the first three audio tracks and first two subtitle tracks\n\n"
    msg += "• <b>Delete original file after extraction</b>:\n"
    msg += "<code>/leech https://example.com/video.mkv -extract -del</code>\n"
    msg += "This will extract tracks and delete the original file\n\n"
    msg += "• <b>Special value 'all'</b>:\n"
    msg += "<code>/leech https://example.com/video.mkv -extract-audio-index all</code>\n"
    msg += "This will extract all audio tracks (same as not specifying index)</blockquote>\n\n"

    msg += "<b>Priority Settings</b>:\n"
    msg += "Extract follows the same priority settings as other media tools:\n"
    msg += "• Command line flags take highest priority\n"
    msg += "• User settings take priority over owner settings\n"
    msg += "• Owner settings are used as fallback\n"
    msg += "• Default settings are used if no others are specified\n\n"

    return msg


def get_extract_settings_page():
    msg = "<b>Extract Settings (18/26)</b>\n\n"

    msg += "<b>General Extract Settings</b>:\n"
    msg += "• <b>Enabled</b>: Master toggle for extract feature\n"
    msg += "• <b>Priority</b>: Order in which extract runs (default: 6)\n"
    msg += "• <b>Delete Original</b>: Remove original file after extraction\n"
    msg += (
        "• <b>Maintain Quality</b>: Preserve original quality during extraction\n\n"
    )

    msg += "<b>Video Extract Settings</b>:\n"
    msg += "• <b>Video Extract</b>: Enable/disable video track extraction\n"
    msg += "• <b>Video Codec</b>: Output codec for video tracks\n"
    msg += "• <b>Video Format</b>: Output container format for video tracks\n"
    msg += "• <b>Video Index</b>: Specific video track(s) to extract (0-based)\n"
    msg += "• <b>Video Index Flag</b>: -extract-video-index or -vi\n"
    msg += "• <b>Video Quality</b>: Quality setting for video extraction\n"
    msg += "• <b>Multiple Indices</b>: Use comma-separated values (e.g., 0,1,2)\n\n"

    msg += "<b>Audio Extract Settings</b>:\n"
    msg += "• <b>Audio Extract</b>: Enable/disable audio track extraction\n"
    msg += "• <b>Audio Codec</b>: Output codec for audio tracks\n"
    msg += "• <b>Audio Format</b>: Output container format for audio tracks\n"
    msg += "• <b>Audio Index</b>: Specific audio track(s) to extract (0-based)\n"
    msg += "• <b>Audio Index Flag</b>: -extract-audio-index or -ai\n"
    msg += "• <b>Audio Bitrate</b>: Bitrate setting for audio extraction\n"
    msg += "• <b>Multiple Indices</b>: Use comma-separated values (e.g., 0,1,2)\n\n"

    msg += "<b>Subtitle Extract Settings</b>:\n"
    msg += "• <b>Subtitle Extract</b>: Enable/disable subtitle track extraction\n"
    msg += "• <b>Subtitle Codec</b>: Output codec for subtitle tracks\n"
    msg += "• <b>Subtitle Format</b>: Output format for subtitle tracks\n"
    msg += (
        "• <b>Subtitle Index</b>: Specific subtitle track(s) to extract (0-based)\n"
    )
    msg += "• <b>Subtitle Index Flag</b>: -extract-subtitle-index or -si\n"
    msg += "• <b>Multiple Indices</b>: Use comma-separated values (e.g., 0,1,2)\n\n"

    msg += "<b>Attachment Extract Settings</b>:\n"
    msg += "• <b>Attachment Extract</b>: Enable/disable attachment extraction\n"
    msg += "• <b>Attachment Format</b>: Output format for attachments\n"
    msg += "• <b>Attachment Index</b>: Specific attachment(s) to extract (0-based)\n"
    msg += "• <b>Attachment Index Flag</b>: -extract-attachment-index or -ati\n"
    msg += "• <b>Multiple Indices</b>: Use comma-separated values (e.g., 0,1,2)\n\n"

    msg += '<blockquote expandable="expandable"><b>Codec Options</b>:\n'
    msg += "• <b>copy</b>: Copy stream without re-encoding (fastest, best quality)\n"
    msg += "• <b>Video Codecs</b>: h264, h265, vp9, av1, etc.\n"
    msg += "• <b>Audio Codecs</b>: aac, mp3, opus, flac, etc.\n"
    msg += "• <b>Subtitle Codecs</b>: srt, ass, vtt, etc.\n\n"
    msg += "Using 'copy' is recommended for most cases as it preserves quality and is much faster.</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Index Options</b>:\n'
    msg += "• <b>None/Empty</b>: Extract all tracks of the specified type\n"
    msg += "• <b>all</b>: Extract all tracks of the specified type\n"
    msg += "• <b>0</b>: Extract only the first track (index starts at 0)\n"
    msg += "• <b>1</b>: Extract only the second track\n"
    msg += "• <b>2</b>: Extract only the third track\n"
    msg += "• <b>0,1</b>: Extract first and second tracks\n"
    msg += "• <b>0,2,3</b>: Extract first, third, and fourth tracks\n\n"
    msg += "Multiple indices can be specified in both settings and command flags.\n"
    msg += "Example setting: 0,1,2\n"
    msg += "Example command: -extract-audio-index 0,1,2 or -ai 0,1,2\n\n"
    msg += "If you're unsure about track indices, use MediaInfo to view track information.</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Format Settings</b>:\n'
    msg += "• <b>Video Format</b>: mp4, mkv, webm, avi, etc.\n"
    msg += "• <b>Audio Format</b>: mp3, m4a, flac, ogg, etc.\n"
    msg += "• <b>Subtitle Format</b>: srt, ass, vtt, etc.\n"
    msg += "• <b>Attachment Format</b>: Original format preserved\n\n"
    msg += "Setting format to 'none' will use the default format based on codec.\n"
    msg += "The system automatically selects appropriate containers based on the codec.</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Best Practices</b>:\n'
    msg += "• Use 'copy' codec whenever possible to preserve quality\n"
    msg += "• Leave index empty to extract all tracks of a type\n"
    msg += "• Use MediaInfo to identify track indices before extraction\n"
    msg += "• Enable 'Maintain Quality' for best results\n"
    msg += "• Extract feature works best with MKV containers\n"
    msg += "• Some containers may not support certain track types\n"
    msg += "• MP4 containers have limited subtitle format support\n"
    msg += "• For ASS/SSA subtitles, use 'copy' codec to preserve formatting\n"
    msg += (
        "• Use -del flag to delete original files after extraction</blockquote>\n\n"
    )

    return msg


def get_remove_intro_page():
    msg = "<b>Remove Feature Guide (19/28)</b>\n\n"
    msg += "<b>Remove Feature</b>\n"
    msg += "Remove specific tracks or metadata from media files with customizable track selection.\n\n"

    msg += "<b>Important:</b> Make sure to enable the Remove feature in Media Tools settings before using it.\n\n"

    msg += "<b>How to Use</b>:\n"
    msg += "Add remove flags to your download commands:\n"
    msg += "<code>/leech https://example.com/video.mkv -remove-video</code> (remove all video tracks)\n"
    msg += "<code>/mirror https://example.com/video.mkv -remove-audio</code> (remove all audio tracks)\n"
    msg += "<code>/leech https://example.com/video.mkv -remove-subtitle</code> (remove all subtitle tracks)\n"
    msg += "<code>/mirror https://example.com/video.mkv -remove-attachment</code> (remove all attachments)\n"
    msg += "<code>/leech https://example.com/video.mkv -remove-metadata</code> (remove metadata)\n\n"

    msg += "<b>Remove Specific Tracks by Index</b>:\n"
    msg += "Use index parameters to remove specific tracks:\n"
    msg += "<code>/leech https://example.com/video.mkv -remove-video-index 0</code> (remove first video track)\n"
    msg += "<code>/mirror https://example.com/video.mkv -remove-audio-index 1,2</code> (remove 2nd and 3rd audio tracks)\n"
    msg += "<code>/leech https://example.com/video.mkv -remove-subtitle-index 0,1,2</code> (remove first 3 subtitle tracks)\n\n"

    msg += "<b>Supported Media Types</b>:\n"
    msg += "• <b>Videos</b>: MP4, MKV, AVI, WebM, MOV, etc.\n"
    msg += "• <b>Audio</b>: MP3, AAC, FLAC, WAV, OGG, etc.\n"
    msg += "• <b>Subtitles</b>: SRT, ASS, VTT, WebVTT, etc.\n"
    msg += "• <b>Attachments</b>: Fonts, images, and other embedded files\n\n"

    msg += "<b>Track Types</b>:\n"
    msg += "• <b>Video Tracks</b>: Remove unwanted video streams\n"
    msg += "• <b>Audio Tracks</b>: Remove specific language audio or commentary\n"
    msg += "• <b>Subtitle Tracks</b>: Remove unwanted subtitle languages\n"
    msg += "• <b>Attachments</b>: Remove fonts, images, and other embedded files\n"
    msg += "• <b>Metadata</b>: Strip file information and tags\n\n"

    msg += "<b>Short Format Flags</b>:\n"
    msg += "• <code>-rvi</code>: Short for -remove-video-index\n"
    msg += "• <code>-rai</code>: Short for -remove-audio-index\n"
    msg += "• <code>-rsi</code>: Short for -remove-subtitle-index\n"
    msg += "• <code>-rati</code>: Short for -remove-attachment-index\n\n"

    msg += "<b>RO Files</b>:\n"
    msg += "By default, removing tracks will replace the original file. To keep both the original and processed files:\n"
    msg += "• Set 'RO' to OFF in /mediatools > Remove > Configure\n"
    msg += "• Use the <code>-del</code> flag to control this behavior:\n"
    msg += "<code>/leech https://example.com/video.mkv -remove-video-index 1 -del f</code> (keep original)\n"
    msg += "<code>/mirror https://example.com/video.mkv -remove-audio-index 0 -del t</code> (remove original)\n\n"

    msg += "<b>Priority Settings</b>:\n"
    msg += (
        "• Remove feature has priority 8 by default (runs after most other tools)\n"
    )
    msg += "• Configure priority in Media Tools settings\n"
    msg += "• Lower numbers run earlier in the processing pipeline\n\n"

    return msg


def get_remove_settings_page():
    msg = "<b>Remove Settings (20/28)</b>\n\n"

    msg += "<b>General Settings</b>:\n"
    msg += "• <b>Remove Enabled</b>: Master toggle for the remove feature\n"
    msg += "• <b>Remove Priority</b>: Set the execution order (default: 8)\n"
    msg += (
        "• <b>RO (Remove Original)</b>: Delete original file after removing tracks\n"
    )
    msg += "• <b>Remove Metadata</b>: Strip metadata from files\n\n"

    msg += "<b>Track Type Settings</b>:\n"
    msg += "• <b>Video Remove</b>: Enable/disable video track removal\n"
    msg += "• <b>Audio Remove</b>: Enable/disable audio track removal\n"
    msg += "• <b>Subtitle Remove</b>: Enable/disable subtitle track removal\n"
    msg += "• <b>Attachment Remove</b>: Enable/disable attachment removal\n\n"

    msg += "<b>Index Settings</b>:\n"
    msg += "• <b>Video Index</b>: Which video tracks to remove (empty = all)\n"
    msg += "• <b>Audio Index</b>: Which audio tracks to remove (empty = all)\n"
    msg += "• <b>Subtitle Index</b>: Which subtitle tracks to remove (empty = all)\n"
    msg += "• <b>Attachment Index</b>: Which attachments to remove (empty = all)\n\n"

    msg += '<blockquote expandable="expandable"><b>Index Options</b>:\n'
    msg += "• <b>Empty/None</b>: Remove all tracks of the specified type\n"
    msg += "• <b>0</b>: Remove only the first track (index starts at 0)\n"
    msg += "• <b>1</b>: Remove only the second track\n"
    msg += "• <b>2</b>: Remove only the third track\n"
    msg += "• <b>0,1</b>: Remove first and second tracks\n"
    msg += "• <b>0,2,3</b>: Remove first, third, and fourth tracks\n"
    msg += "• <b>all</b>: Remove all tracks of the specified type\n\n"
    msg += "Multiple indices can be specified in both settings and command flags.\n"
    msg += "Example setting: 0,1,2\n"
    msg += "Example command: -remove-audio-index 0,1,2 or -rai 0,1,2\n\n"
    msg += "If you're unsure about track indices, use MediaInfo to view track information.</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Use Cases</b>:\n'
    msg += "• <b>Remove Commentary</b>: Remove director's commentary audio tracks\n"
    msg += "• <b>Language Cleanup</b>: Remove unwanted subtitle languages\n"
    msg += "• <b>Size Reduction</b>: Remove unnecessary video/audio tracks to save space\n"
    msg += (
        "• <b>Privacy</b>: Strip metadata that might contain personal information\n"
    )
    msg += "• <b>Compatibility</b>: Remove tracks that cause playback issues\n"
    msg += "• <b>Attachment Cleanup</b>: Remove embedded fonts or images\n\n"
    msg += "The remove feature is particularly useful for:\n"
    msg += "• Multi-language media files with many audio/subtitle tracks\n"
    msg += "• Files with embedded attachments you don't need\n"
    msg += "• Reducing file size by removing unnecessary streams\n"
    msg += "• Preparing files for specific devices or players</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Best Practices</b>:\n'
    msg += "• Use MediaInfo to identify track indices before removal\n"
    msg += (
        "• Test with a small file first to verify the correct tracks are removed\n"
    )
    msg += "• Keep backups when removing important tracks\n"
    msg += "• Remove feature works best with MKV containers\n"
    msg += "• Some containers may not support track removal\n"
    msg += "• Metadata removal is irreversible - make sure you don't need it\n"
    msg += "• Use comma-separated indices (0,1,2) for multiple track removal\n"
    msg += "• Combine with other tools for complete file processing\n"
    msg += (
        "• Use -del flag to control whether original files are kept</blockquote>\n\n"
    )

    msg += "<b>Configuration</b>:\n"
    msg += "• Enable remove in Media Tools settings\n"
    msg += "• Enable specific track type removal (video, audio, etc.)\n"
    msg += "• Set default indices for automatic removal\n"
    msg += "• Configure priority to control when removal runs in the pipeline\n"
    msg += "• Use command flags to override settings for specific tasks\n\n"

    return msg


def get_priority_guide_page():
    msg = "<b>Media Tools Priority Guide (26/30)</b>\n\n"
    msg += "<b>Understanding Priority Settings:</b>\n"
    msg += "Media tools (merge, watermark, convert, compression, trim, extract) use a priority system to determine the order of processing.\n\n"

    msg += "<b>Priority Values:</b>\n"
    msg += "• Lower number = Higher priority (runs first)\n"
    msg += "• Default merge priority: 1 (runs first)\n"
    msg += "• Default watermark priority: 2 (runs second)\n"
    msg += "• Default convert priority: 3 (runs third)\n"
    msg += "• Default compression priority: 4 (runs fourth)\n"
    msg += "• Default trim priority: 5 (runs fifth)\n"
    msg += "• Default extract priority: 6 (runs sixth)\n"
    msg += "• Default remove priority: 8 (runs eighth)\n\n"

    msg += "<b>Priority Hierarchy:</b>\n"
    msg += "1. Command line settings (highest priority)\n"
    msg += "2. User settings (from /usettings)\n"
    msg += "3. Owner settings (from /bsettings)\n"
    msg += "4. Default settings (lowest priority)\n\n"

    msg += "<b>Setting Priority:</b>\n"
    msg += "• Use /mediatools command to set priority\n"
    msg += "• Select 'Media Tools Priority' option\n"
    msg += "• Enter a number (1 for highest priority)\n\n"

    msg += "<b>Example Scenarios:</b>\n"
    msg += "• If merge priority=1, watermark priority=2, convert priority=3, compression priority=4:\n"
    msg += "  Files will be merged first, then watermarked, then converted, then compressed\n\n"
    msg += "• If compression priority=1, convert priority=2, watermark priority=3, merge priority=4:\n"
    msg += "  Files will be compressed first, then converted, then watermarked, then merged\n\n"
    msg += "• If watermark priority=1, compression priority=2, convert priority=3, merge priority=4:\n"
    msg += "  Files will be watermarked first, then compressed, then converted, then merged\n\n"

    msg += "<b>Note:</b> Equal priority values will process in default order (merge, watermark, convert, compression)"

    return msg


def get_metadata_guide_page():
    msg = "<b>Metadata Feature Guide (29/30)</b>\n\n"
    msg += "Add custom metadata to media files using command flags or user settings.\n\n"

    msg += "<b>Command Flags:</b>\n"
    msg += "• <code>-metadata-title 'Title'</code>\n"
    msg += "• <code>-metadata-author 'Author'</code>\n"
    msg += "• <code>-metadata-comment 'Comment'</code>\n"
    msg += "• <code>-metadata-all 'Text'</code>\n\n"

    msg += "<b>Template Variables:</b>\n"
    msg += "Use <code>{variable}</code> format in metadata:\n"
    msg += "• <code>{filename}</code>, <code>{size}</code>, <code>{duration}</code>, <code>{ext}</code>\n"
    msg += "• <code>{quality}</code>, <code>{codec}</code>, <code>{year}</code>\n"
    msg += "• <code>{season}</code>, <code>{episode}</code> (TV shows)\n"
    msg += "• <code>{audios}</code>, <code>{subtitles}</code>, <code>{NumAudios}</code>\n\n"

    msg += "<b>Examples:</b>\n"
    msg += "• Movie: <code>{filename} - {quality}</code>\n"
    msg += "• TV: <code>S{season}E{episode} - {filename}</code>\n"
    msg += "• Detail: <code>{filename} | {size} | {codec}</code>\n\n"

    msg += '<blockquote expandable="expandable"><b>All Template Variables:</b>\n'
    msg += "<b>Basic:</b> filename, size, duration, ext, md5_hash, id\n"
    msg += (
        "<b>Media:</b> quality, codec, framerate, audios, audio_codecs, subtitles\n"
    )
    msg += "<b>Tracks:</b> NumVideos, NumAudios, NumSubtitles, formate, format\n"
    msg += "<b>TV Shows:</b> season, episode, year\n\n"

    msg += "<b>Track-Specific:</b>\n"
    msg += "• <code>-metadata-video-title</code>\n"
    msg += "• <code>-metadata-audio-author</code>\n"
    msg += "• <code>-metadata-subtitle-comment</code>\n\n"

    msg += "<b>Supported Files:</b>\n"
    msg += "Video (MP4, MKV), Audio (MP3, M4A), Documents (PDF, EPUB), Images\n\n"

    msg += "<b>Priority:</b> Command flags > User settings > Bot defaults</blockquote>\n\n"

    msg += '<blockquote expandable="expandable"><b>Usage Examples:</b>\n'
    msg += "• <code>/leech url -metadata-title 'Album Name'</code>\n"
    msg += "• <code>/mirror url -metadata-author 'Channel'</code>\n"
    msg += "• <code>/leech url -metadata-all 'My Collection'</code>\n"
    msg += "• <code>/mirror url -metadata-comment '{filename} - {year}'</code>\n\n"

    msg += "<b>Tips:</b>\n"
    msg += "• Use quotes for values with spaces\n"
    msg += "• Configure defaults in /usettings > Metadata\n"
    msg += "• Template variables work in all metadata fields\n"
    msg += "• Individual fields override -metadata-all</blockquote>\n\n"

    msg += "Configure default metadata in <b>/usettings > Leech > Metadata</b> for automatic application to all files."

    return msg


def get_usage_examples_page_1():
    msg = "<b>Media Tools Usage Examples (1/2) (27/30)</b>\n\n"

    msg += "<b>Merge Examples</b>:\n"
    msg += "• <code>/leech https://example.com/videos.zip -merge-video</code>\n"
    msg += "  Merges video files preserving all tracks\n\n"
    msg += "• <code>/mirror https://example.com/music.zip -merge-audio</code>\n"
    msg += "  Combines audio files into single audio file\n\n"
    msg += "• <code>/leech https://example.com/images.zip -merge-image</code>\n"
    msg += "  Creates image collage/grid from images\n\n"
    msg += "• <code>/mirror https://example.com/docs.zip -merge-pdf</code>\n"
    msg += "  Combines PDF files into single document\n\n"
    msg += (
        "• <code>/leech https://example.com/files.zip -m folder -merge-all</code>\n"
    )
    msg += "  Merges all files by type in custom folder\n\n"

    msg += "<b>Watermark Examples</b>:\n"
    msg += '• <code>/leech https://example.com/video.mp4 -wm "My Watermark"</code>\n'
    msg += "  Adds text watermark to video\n\n"
    msg += "• <code>/leech https://example.com/video.mp4 -iwm /path/to/logo.png</code>\n"
    msg += "  Adds image watermark to video\n\n"

    msg += "<b>Convert Examples</b>:\n"
    msg += "• <code>/leech https://example.com/video.webm -cv mp4</code>\n"
    msg += "  Converts WebM video to MP4 format\n\n"
    msg += "• <code>/mirror https://example.com/audio.wav -ca mp3</code>\n"
    msg += "  Converts WAV audio to MP3 format\n\n"

    msg += "<b>Swap Examples</b>:\n"
    msg += "• <code>/leech https://example.com/movie.mkv -swap</code>\n"
    msg += "  Reorders tracks based on language priority\n\n"
    msg += "• <code>/mirror https://example.com/series.zip -swap-audio</code>\n"
    msg += "  Swaps only audio tracks in all files\n\n"

    msg += "<b>Combined Usage</b>:\n"
    msg += '• <code>/leech https://example.com/videos.zip -merge-video -wm "My Channel"</code>\n'
    msg += "  Merges videos, then adds text watermark\n\n"
    msg += "• <code>/mirror https://example.com/videos.zip -merge-video -iwm logo.png</code>\n"
    msg += "  Merges videos, then adds image watermark\n\n"
    msg += '• <code>/mirror https://example.com/files.zip -m folder -merge-all -wm "© 2023"</code>\n'
    msg += "  Merges files by type, then adds watermark\n\n"

    msg += "<b>Note:</b> See next page for more examples"

    return msg


def get_usage_examples_page_2():
    msg = "<b>Media Tools Usage Examples (2/2) (28/30)</b>\n\n"

    msg += "<b>Compression Examples</b>:\n"
    msg += "• <code>/leech https://example.com/video.mp4 -video-fast</code>\n"
    msg += "  Compresses video using fast preset\n\n"
    msg += "• <code>/mirror https://example.com/audio.mp3 -audio-medium</code>\n"
    msg += "  Compresses audio using medium preset\n\n"

    msg += "<b>Extract Examples</b>:\n"
    msg += "• <code>/leech https://example.com/video.mkv -extract</code>\n"
    msg += "  Extracts all enabled track types\n\n"
    msg += "• <code>/mirror https://example.com/video.mkv -extract-video</code>\n"
    msg += "  Extracts only video tracks\n\n"
    msg += "• <code>/leech https://example.com/video.mkv -extract-audio</code>\n"
    msg += "  Extracts only audio tracks\n\n"
    msg += "• <code>/mirror https://example.com/video.mkv -vi 0 -ai 1</code>\n"
    msg += "  Extracts first video track and second audio track\n\n"
    msg += "• <code>/leech https://example.com/video.mkv -extract-audio-index all</code>\n"
    msg += "  Extracts all audio tracks\n\n"

    msg += "<b>Remove Examples</b>:\n"
    msg += (
        "• <code>/leech https://example.com/video.mkv -remove-video-index 1</code>\n"
    )
    msg += "  Removes second video track\n\n"
    msg += "• <code>/mirror https://example.com/video.mkv -remove-audio-index 0,2</code>\n"
    msg += "  Removes first and third audio tracks\n\n"
    msg += "• <code>/leech https://example.com/video.mkv -remove-subtitle</code>\n"
    msg += "  Removes all subtitle tracks\n\n"
    msg += "• <code>/mirror https://example.com/video.mkv -remove-metadata</code>\n"
    msg += "  Strips metadata from file\n\n"
    msg += "• <code>/leech https://example.com/video.mkv -rvi 0,1 -rai 2</code>\n"
    msg += "  Removes first two video tracks and third audio track\n\n"

    msg += "<b>Add Examples</b>:\n"
    msg += "• <code>/leech https://example.com/video.mp4 -add</code>\n"
    msg += "  Adds all enabled track types\n\n"
    msg += "• <code>/mirror https://example.com/video.mp4 -add-audio</code>\n"
    msg += "  Adds only audio tracks to container\n\n"
    msg += (
        "• <code>/leech https://example.com/video.mp4 -add -m folder_name</code>\n"
    )
    msg += "  Adds tracks from all files in folder to first file\n\n"
    msg += (
        "• <code>/mirror https://example.com/video.mp4 -add-video-index 0,1</code>\n"
    )
    msg += "  Adds video tracks at indices 0 and 1\n\n"
    msg += "• <code>/leech https://example.com/video.mp4 -add -replace</code>\n"
    msg += "  Adds tracks by replacing existing ones\n\n"

    msg += "<b>Combined with Other Tools</b>:\n"
    msg += '• <code>/leech https://example.com/videos.zip -merge-video -video-medium -wm "My Channel"</code>\n'
    msg += "  Merges videos, compresses, then adds watermark\n\n"
    msg += "• <code>/mirror https://example.com/videos.zip -merge-video -iwm logo.png</code>\n"
    msg += "  Merges videos, then adds image watermark\n\n"
    msg += "• <code>/leech https://example.com/video.mkv -extract-audio -ca mp3 -del</code>\n"
    msg += "  Extracts audio, converts to MP3, deletes original\n\n"
    msg += "• <code>/mirror https://example.com/video.mkv -extract-subtitle -extract-subtitle-codec srt</code>\n"
    msg += "  Extracts subtitles and converts them to SRT format\n\n"
    msg += "• <code>/leech https://example.com/video.mp4 -add-audio -add-subtitle -metadata-title 'My Video'</code>\n"
    msg += "  Adds audio and subtitle tracks, then sets metadata\n\n"

    msg += "<b>Metadata Examples</b>:\n"
    msg += "• <code>/leech https://example.com/video.mp4 -metadata-title 'My Video'</code>\n"
    msg += "  Sets title metadata for the video file\n\n"
    msg += "• <code>/mirror https://example.com/files.zip -metadata-all 'My Collection'</code>\n"
    msg += "  Sets all metadata fields for extracted files\n\n"

    msg += "<b>Using the -mt Flag</b>:\n"
    msg += "• <code>/mirror https://example.com/video.mp4 -mt</code>\n"
    msg += "  Opens media tools settings before starting task\n\n"
    msg += "• <code>/leech https://example.com/files.zip -merge-video -mt</code>\n"
    msg += "  Opens media tools settings before merging videos\n\n"

    msg += "<b>Note:</b> Use /mediatools command to configure advanced settings or use the -mt flag with any command"

    return msg


def get_mt_flag_guide_page():
    msg = "<b>Media Tools Flag Guide (30/30)</b>\n\n"
    msg += "<b>Media Tools Flag</b>: -mt\n\n"
    msg += "/cmd link -mt (opens media tools settings before starting the task)\n\n"

    msg += "<b>How It Works</b>:\n"
    msg += "• Shows media tools settings menu before starting task\n"
    msg += "• Customize settings for the current task only\n"
    msg += '• Click "Done" to start with your settings\n'
    msg += '• Click "Cancel" to abort the task\n'
    msg += "• 60-second timeout for selection\n\n"

    msg += "<b>Usage Examples</b>:\n"
    msg += "• <code>/mirror link -mt</code> - Configure before mirror\n"
    msg += "• <code>/leech link -merge-video -mt</code> - Configure before merge\n"
    msg += "• <code>/ytdl link -mt</code> - Configure before YouTube download\n\n"

    msg += "<b>Benefits</b>:\n"
    msg += "• Configure settings on-the-fly for specific tasks\n"
    msg += "• Preview settings before processing large files\n"
    msg += "• Works with all download commands and other flags\n"
    msg += "• Messages auto-delete after 5 minutes\n"

    return msg


def get_add_intro_page_1():
    msg = "<b>Add Feature Guide (Part 1) (21/28)</b>\n\n"
    msg += "<b>Add Feature</b>\n"
    msg += "Add media tracks (video, audio, subtitle, attachment) to existing files with customizable settings.\n\n"

    msg += "<b>Important:</b> Make sure to enable the Add feature in Media Tools settings before using it.\n\n"

    msg += "<b>Supported Media Types</b>:\n"
    msg += "• <b>Videos</b>: MP4, MKV, AVI, WebM, etc.\n"
    msg += "• <b>Audio</b>: MP3, AAC, FLAC, WAV, etc.\n"
    msg += "• <b>Subtitles</b>: SRT, ASS, VTT, etc.\n"
    msg += "• <b>Attachments</b>: Fonts, images, and other files\n\n"

    msg += "<b>How to Use</b>:\n"
    msg += "Add the <code>-add</code> flag to add all enabled track types based on settings:\n"
    msg += "<code>/leech https://example.com/video.mp4 -add</code>\n\n"

    msg += "Or use specific flags to add only certain track types:\n"
    msg += "<code>/leech https://example.com/video.mp4 -add-video</code> (add only video tracks)\n"
    msg += "<code>/mirror https://example.com/video.mp4 -add-audio</code> (add only audio tracks)\n"
    msg += "<code>/leech https://example.com/video.mp4 -add-subtitle</code> (add only subtitle tracks)\n"
    msg += "<code>/mirror https://example.com/video.mp4 -add-attachment</code> (add only attachment tracks)\n\n"

    msg += "<b>Track Placement</b>:\n"
    msg += "You can specify track indices using the index parameters:\n"
    msg += "<code>/leech https://example.com/video.mp4 -add-video-index 0</code> (add at index 0)\n"
    msg += "For multiple indices, use comma-separated values:\n"
    msg += "<code>/leech https://example.com/video.mp4 -add-video-index 0,1,2</code>\n\n"

    msg += "<b>Multi-Input Support</b>:\n"
    msg += "Use the -m flag to add tracks from multiple files:\n"
    msg += "<code>/leech https://example.com/video.mp4 -m folder_name -add</code>\n"
    msg += "This adds tracks from all files in the folder to the first file.\n\n"

    msg += "When using multiple indices with multi-input mode, each index corresponds to a different input file:\n"
    msg += "<code>/leech https://example.com/video.mp4 -m video1.mp4,video2.mp4 -add-video-index 2,3</code>\n"
    msg += "This adds video track from video1.mp4 at index 2 and from video2.mp4 at index 3.\n\n"

    msg += "<b>See next page for more Add feature details...</b>"

    return msg


def get_add_intro_page_2():
    msg = "<b>Add Feature Guide (Part 2) (22/28)</b>\n\n"

    msg += "<b>Track Management Flags</b>:\n"
    msg += "• <code>-add -del</code>: Add tracks and delete original file\n"
    msg += "• <code>-add -del f</code>: Add tracks but keep original file\n"
    msg += "• <code>-add -preserve</code>: Add tracks while preserving existing tracks\n"
    msg += (
        "• <code>-add -replace</code>: Add tracks by replacing existing tracks\n\n"
    )

    msg += "<b>Track Replacement Behavior</b>:\n"
    msg += "By default, adding a track at an index where a track already exists will NOT replace the existing track:\n"
    msg += "• Original tracks are preserved (due to the -map 0 command)\n"
    msg += "• New tracks are added at specified indices\n"
    msg += "• Existing tracks may be shifted to higher indices\n\n"

    msg += "To replace existing tracks, use the -replace flag:\n"
    msg += "<code>/leech https://example.com/video.mp4 -add-audio-index 1 -replace</code>\n\n"

    msg += "<b>Short Format Flags</b>:\n"
    msg += "• <code>-avi</code>: Short for -add-video-index\n"
    msg += "• <code>-aai</code>: Short for -add-audio-index\n"
    msg += "• <code>-asi</code>: Short for -add-subtitle-index\n"
    msg += "• <code>-ati</code>: Short for -add-attachment-index\n\n"

    msg += "<b>Multi vs. Bulk Processing</b>:\n"
    msg += "• <b>Multi (-m flag)</b>: Each index in the comma-separated list corresponds to a different input file\n"
    msg += "• <b>Bulk</b>: The same indices are applied to each file in the bulk operation separately\n\n"

    msg += '<blockquote expandable="expandable"><b>Advanced Usage</b>:\n'
    msg += "• <code>-add-video-index 0</code>: Add only the first video track from source\n"
    msg += "• <code>-add-audio-index 1</code>: Add only the second audio track from source\n"
    msg += "• <code>-add-subtitle-index 2</code>: Add only the third subtitle track from source\n"
    msg += "• <code>-add-attachment-index 0</code>: Add only the first attachment from source\n"
    msg += "• <code>-add -del</code>: Add tracks and delete original file\n"
    msg += "• <code>-add -del f</code>: Add tracks but keep original file\n"
    msg += "• <code>-add -preserve</code>: Add tracks while preserving existing tracks\n"
    msg += "• <code>-add -replace</code>: Add tracks by replacing existing tracks\n"
    msg += "• <code>-add-video-codec h264</code>: Specify video codec to use\n"
    msg += "• <code>-add-audio-codec aac</code>: Specify audio codec to use\n"
    msg += "• <code>-add-subtitle-codec srt</code>: Specify subtitle codec to use</blockquote>\n\n"

    msg += "<b>Index Handling</b>:\n"
    msg += "• If a specified index is not available, the system will use the first available index\n"
    msg += "• When -preserve flag is used, existing tracks are always kept\n"
    msg += "• When -replace flag is used, existing tracks at specified indices will be replaced\n\n"

    return msg


def get_add_settings_page():
    msg = "<b>Add Settings (23/30)</b>\n\n"

    msg += "<b>Main Settings</b>:\n"
    msg += "• <b>Add Enabled</b>: Enable or disable the add feature globally\n"
    msg += "• <b>Add Priority</b>: Set the processing order in the pipeline\n"
    msg += "• <b>Add Delete Original (RO)</b>: Delete original file after adding tracks\n"
    msg += "• <b>Add Preserve Tracks</b>: Preserve existing tracks when adding new ones\n"
    msg += "• <b>Add Replace Tracks</b>: Replace existing tracks with new ones\n\n"

    msg += "<b>Track Type Settings</b>:\n"
    msg += "• <b>Add Video Enabled</b>: Enable or disable video track addition\n"
    msg += "• <b>Add Audio Enabled</b>: Enable or disable audio track addition\n"
    msg += (
        "• <b>Add Subtitle Enabled</b>: Enable or disable subtitle track addition\n"
    )
    msg += (
        "• <b>Add Attachment Enabled</b>: Enable or disable attachment addition\n\n"
    )

    msg += "<b>Codec Settings</b>:\n"
    msg += "• <b>Add Video Codec</b>: Codec for video (copy, h264, h265, etc.)\n"
    msg += "• <b>Add Audio Codec</b>: Codec for audio (copy, aac, mp3, etc.)\n"
    msg += (
        "• <b>Add Subtitle Codec</b>: Codec for subtitles (copy, srt, ass, etc.)\n\n"
    )

    msg += "<b>Index Settings</b>:\n"
    msg += "• <b>Add Video Index</b>: Video track index to add (empty for all)\n"
    msg += "• <b>Add Audio Index</b>: Audio track index to add (empty for all)\n"
    msg += (
        "• <b>Add Subtitle Index</b>: Subtitle track index to add (empty for all)\n"
    )
    msg += (
        "• <b>Add Attachment Index</b>: Attachment index to add (empty for all)\n\n"
    )

    msg += "<b>Quality Settings</b>:\n"
    msg += "• <b>Video</b>: Quality (CRF), preset, bitrate, resolution, FPS\n"
    msg += "• <b>Audio</b>: Bitrate, channels, sampling rate, volume\n"
    msg += "• <b>Subtitle</b>: Language, encoding, font, font size, hardsub\n"
    msg += "• <b>Attachment</b>: MIME type\n\n"

    msg += '<blockquote expandable="expandable"><b>Best Practices</b>:\n'
    msg += "• Use 'copy' codec whenever possible to preserve quality\n"
    msg += "• For H.264/H.265 video, CRF values between 18-28 offer good quality\n"
    msg += "• For AAC audio, bitrates of 128k-320k are recommended\n"
    msg += "• Multiple indices can be specified using comma-separated values\n"
    msg += "• The Add feature works best with MKV containers\n"
    msg += "• MP4 containers have limited subtitle format support\n"
    msg += "• Some containers may not support certain track types\n"
    msg += "• <b>Hardsub</b>: Burns subtitles permanently into video (cannot be disabled)\n"
    msg += (
        "• <b>Soft subtitles</b>: Separate subtitle tracks (can be toggled on/off)\n"
    )
    msg += "\n<b>📋 Container Compatibility:</b>\n"
    msg += "• <b>MKV</b>: ✅ Excellent (all subtitle formats)\n"
    msg += "• <b>MP4/MOV</b>: ⚠️ Good (SRT→mov_text, VTT→mov_text)\n"
    msg += "• <b>WebM</b>: ✅ Good (most formats)\n"
    msg += "• <b>AVI</b>: ❌ Limited (recommend hardsub)\n"
    msg += "• <b>Recommendation</b>: Use MKV for best subtitle support\n\n"
    msg += "• When using multi-input mode (-m), each index corresponds to a different input file\n"
    msg += "• Use the -del flag to delete original files after adding tracks\n"
    msg += "• Use the -preserve flag to keep existing tracks when adding new ones\n"
    msg += "• Use the -replace flag to replace existing tracks with new ones</blockquote>\n\n"

    return msg


def get_swap_intro_page():
    msg = "<b>Swap Feature Guide (24/30)</b>\n\n"
    msg += "<b>Swap Flag</b>: -swap\n\n"

    msg += "<b>Usage</b>:\n"
    msg += "• <code>/cmd link -swap</code> - Reorder tracks based on language or index\n"
    msg += "• <code>/cmd link -swap-audio</code> - Swap only audio tracks\n"
    msg += "• <code>/cmd link -swap-video</code> - Swap only video tracks\n"
    msg += "• <code>/cmd link -swap-subtitle</code> - Swap only subtitle tracks\n\n"

    msg += "<b>Two Swapping Modes</b>:\n"
    msg += "• <b>Language-based</b>: Reorder tracks by language priority\n"
    msg += "• <b>Index-based</b>: Swap tracks at specific positions\n\n"

    msg += "<b>Language-based Examples</b>:\n"
    msg += "• Language order: <code>eng,hin,jpn</code>\n"
    msg += "• Result: English tracks first, Hindi second, Japanese third\n"
    msg += "• Remaining tracks maintain their original order\n\n"

    msg += "<b>Index-based Examples</b>:\n"
    msg += "• Index order: <code>0,1</code> - Swaps first two tracks\n"
    msg += "• Index order: <code>1,2,0</code> - Rotates first three tracks\n"
    msg += "• Single index: <code>1</code> - No swapping occurs\n\n"

    msg += "<b>Multi-Link Usage</b>:\n"
    msg += "• <code>/cmd link -m folder_name -swap</code>\n"
    msg += "• <code>/cmd -b -m folder_name -swap</code> (reply to links)\n\n"

    msg += "<b>Key Features</b>:\n"
    msg += "• Works with video, audio, and subtitle tracks\n"
    msg += "• Preserves track metadata and properties\n"
    msg += "• Handles missing languages gracefully\n"
    msg += "• Validates index ranges automatically\n"
    msg += "• Supports all media containers (MKV, MP4, etc.)\n\n"

    return msg


def get_swap_settings_page():
    msg = "<b>Swap Settings (25/30)</b>\n\n"

    msg += "<b>Main Settings</b>:\n"
    msg += "• <b>Swap Enabled</b>: Enable or disable the swap feature globally\n"
    msg += "• <b>Swap Priority</b>: Set the processing order in the pipeline\n"
    msg += (
        "• <b>Swap Remove Original (RO)</b>: Delete original file after swapping\n\n"
    )

    msg += "<b>Track Type Settings</b>:\n"
    msg += "• <b>Swap Audio Enabled</b>: Enable or disable audio track swapping\n"
    msg += "• <b>Swap Video Enabled</b>: Enable or disable video track swapping\n"
    msg += "• <b>Swap Subtitle Enabled</b>: Enable or disable subtitle track swapping\n\n"

    msg += "<b>Mode Settings (per track type)</b>:\n"
    msg += "• <b>Use Language</b>: True = language-based, False = index-based\n"
    msg += "• <b>Language Order</b>: Priority order (e.g., 'eng,hin,jpn')\n"
    msg += "• <b>Index Order</b>: Swap pattern (e.g., '0,1' or '1,2,0')\n\n"

    msg += '<blockquote expandable="expandable"><b>Configuration Examples</b>:\n'
    msg += "<b>Language-based Audio Swap</b>:\n"
    msg += "• Audio Enabled: ✅\n"
    msg += "• Use Language: ✅\n"
    msg += "• Language Order: eng,hin,jpn\n"
    msg += "• Result: English audio first, Hindi second, Japanese third\n\n"

    msg += "<b>Index-based Video Swap</b>:\n"
    msg += "• Video Enabled: ✅\n"
    msg += "• Use Language: ❌\n"
    msg += "• Index Order: 1,0\n"
    msg += "• Result: Second video track becomes first, first becomes second\n\n"

    msg += "<b>Mixed Configuration</b>:\n"
    msg += "• Audio: Language-based (eng,hin)\n"
    msg += "• Video: Index-based (0,1)\n"
    msg += "• Subtitle: Language-based (eng,hin,jpn)\n\n"

    msg += "<b>Best Practices</b>:\n"
    msg += "• Use language codes (eng, hin, jpn, spa, etc.)\n"
    msg += "• Index order should be comma-separated numbers\n"
    msg += "• Single index in order means no swapping\n"
    msg += "• Invalid indices are automatically handled\n"
    msg += "• Language mode works best with properly tagged files\n"
    msg += "• Index mode gives precise control over track order</blockquote>\n\n"

    return msg


def get_pagination_buttons(current_page):
    buttons = ButtonMaker()

    # Total number of pages
    total_pages = 30

    # Add navigation buttons
    if current_page > 1:
        buttons.data_button("⬅️ Previous", f"mthelp_page_{current_page - 1}")

    # Page indicator
    buttons.data_button(f"Page {current_page}/{total_pages}", "mthelp_current")

    if current_page < total_pages:
        buttons.data_button("Next ➡️", f"mthelp_page_{current_page + 1}")

    # Close button
    buttons.data_button("Close", "mthelp_close", "footer")

    return buttons.build_menu(3)


async def media_tools_help_cmd(_, message):
    """
    Display media tools help with pagination
    """
    from bot.helper.ext_utils.bot_utils import is_media_tool_enabled

    # Check if media tools are enabled
    if not is_media_tool_enabled("mediatools"):
        error_msg = await send_message(
            message,
            "<b>Media Tools are disabled</b>\n\nMedia Tools have been disabled by the bot owner.",
        )
        # Auto-delete the command message immediately
        await delete_message(message)
        # Auto-delete the error message after 5 minutes
        await auto_delete_message(error_msg, time=300)
        return

    # Delete the command message immediately
    await delete_message(message)

    # Start with page 1
    current_page = 1

    # Check if the user is trying to access a specific page
    if hasattr(message, "text") and len(message.text.split()) > 1:
        try:
            requested_page = int(message.text.split()[1])
            if 1 <= requested_page <= 28:  # Max page is now 28
                current_page = requested_page
        except ValueError:
            pass

    content = get_page_content(current_page)
    buttons = get_pagination_buttons(current_page)

    # Send the first page
    help_msg = await send_message(message, content, buttons)

    # Schedule auto-deletion after 5 minutes
    create_task(auto_delete_message(help_msg, time=300))
    # We don't need to await the task, but we store the reference to avoid warnings


async def media_tools_help_callback(_, callback_query):
    """
    Handle callback queries for media tools help pagination
    """
    message = callback_query.message
    data = callback_query.data

    # User ID and debug message removed to reduce logging

    # Handle close button
    if data == "mthelp_close":
        await delete_message(message)
        await callback_query.answer()
        return

    # Skip processing for current page indicator
    if data == "mthelp_current":
        await callback_query.answer("Current page")
        return

    # Extract page number from callback data
    if data.startswith("mthelp_page_"):
        try:
            page_num = int(data.split("_")[-1])
            # Debug logs removed to reduce logging
            content = get_page_content(page_num)
            buttons = get_pagination_buttons(page_num)

            # Edit the message with new page content
            await edit_message(message, content, buttons)
            await callback_query.answer(f"Page {page_num}")
        except Exception as e:
            LOGGER.error(f"Error in media_tools_help_callback: {e!s}")
            await callback_query.answer("Error processing request")


async def watermark_help_cmd(_, message):
    """
    Direct shortcut to watermark help page
    """
    from bot.helper.ext_utils.bot_utils import is_media_tool_enabled

    # Check if media tools are enabled
    if not is_media_tool_enabled("mediatools"):
        error_msg = await send_message(
            message,
            "<b>Media Tools are disabled</b>\n\nMedia Tools have been disabled by the bot owner.",
        )
        # Auto-delete the command message immediately
        await delete_message(message)
        # Auto-delete the error message after 5 minutes
        await auto_delete_message(error_msg, time=300)
        return

    # Delete the command message immediately
    await delete_message(message)

    # Start with watermark intro page (page 9)
    current_page = 9

    content = get_page_content(current_page)
    buttons = get_pagination_buttons(current_page)

    # Send the watermark help page
    help_msg = await send_message(message, content, buttons)

    # Schedule auto-deletion after 5 minutes
    create_task(auto_delete_message(help_msg, time=300))
    # We don't need to await the task, but we store the reference to avoid warnings


# Handler will be added in core/handlers.py
# Also need to register the callback handler
