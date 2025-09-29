import json
import os
from asyncio import create_task
from collections import defaultdict
from os import path as ospath
from re import search as re_search
from time import time

import aiohttp
from aiofiles import open as aiopen

from bot import LOGGER
from bot.helper.aeon_utils.access_check import token_check
from bot.helper.ext_utils.aiofiles_compat import aiopath
from bot.helper.ext_utils.aiofiles_compat import makedirs as mkdir
from bot.helper.ext_utils.aiofiles_compat import remove as aioremove
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.gc_utils import smart_garbage_collection
from bot.helper.ext_utils.links_utils import (
    is_url,  # Used for URL validation at line ~826
)


async def create_telegraph_page_from_content(tc, silent=False):
    """Helper function to create Telegraph page from content"""
    try:
        link_id = (await telegraph.create_page(title="MediaInfo", content=tc))[
            "path"
        ]
        LOGGER.info("MediaInfo generated successfully")
        return link_id
    except Exception as e:
        LOGGER.warning(f"Could not create Telegraph page: {e}")
        if silent:
            return None
        raise


# Resource manager removed
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    delete_message,
    edit_message,
    send_message,
)


async def parse_mediainfo_output(mediainfo_output, file_size, filename):
    """
    Parse mediainfo binary output and convert it to HTML format similar to ffprobe output

    Args:
        mediainfo_output: Raw text output from mediainfo binary
        file_size: File size in bytes
        filename: Name of the file

    Returns:
        str: HTML formatted mediainfo content
    """
    tc = f"<h4>{filename}</h4><br><br><blockquote>General</blockquote><pre>"
    tc += f"{'Complete name':<28}: {filename}\n"

    # Parse mediainfo output line by line
    lines = mediainfo_output.strip().split("\n")
    current_section = "General"
    section_data = {}

    # Group lines by section
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this is a section header (no colon, starts with capital, known section)
        if ":" not in line and line and line[0].isupper():
            # Known section headers
            if line in [
                "General",
                "Video",
                "Audio",
                "Text",
                "Menu",
                "Image",
                "Chapters",
            ]:
                current_section = line
                if current_section not in section_data:
                    section_data[current_section] = []
                continue

        # Parse key-value pairs
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            if current_section not in section_data:
                section_data[current_section] = []
            section_data[current_section].append((key, value))

    # Track what we've already added to avoid duplicates
    added_keys = set()

    # Process General section
    if "General" in section_data:
        for key, value in section_data["General"]:
            key_lower = key.lower()

            # Skip complete name as we already added it
            if key_lower == "complete name":
                continue

            # Map mediainfo keys to display format
            if key_lower == "format":
                tc += f"{'Format':<28}: {value}\n"
                added_keys.add("format")
            elif key_lower == "format/info":
                tc += f"{'Format/Info':<28}: {value}\n"
                added_keys.add("format/info")
            elif key_lower == "file size":
                # Skip file size from mediainfo, we'll add our calculated one
                added_keys.add("file size")
                continue
            elif key_lower == "duration":
                tc += f"{'Duration':<28}: {value}\n"
                added_keys.add("duration")
            elif key_lower == "overall bit rate":
                tc += f"{'Overall bit rate':<28}: {value}\n"
                added_keys.add("overall bit rate")
            elif key_lower in ["encoded date", "encoding date"]:
                tc += f"{'Encoded date':<28}: {value}\n"
                added_keys.add("encoded date")
            elif key_lower in ["writing application", "encoder"]:
                tc += f"{'Writing application':<28}: {value}\n"
                added_keys.add("writing application")
            elif key_lower == "format version":
                tc += f"{'Format version':<28}: {value}\n"
                added_keys.add("format version")
            else:
                # Add other keys as-is, but clean up the display name
                display_key = key.replace("_", " ").title()
                tc += f"{display_key:<28}: {value}\n"

    # Add file size if not already present
    if file_size > 0 and "file size" not in added_keys:
        size_mb = file_size / (1024 * 1024)
        tc += f"{'File size':<28}: {size_mb:.2f} MiB ({file_size:,} bytes)\n"

        if file_size > 1024 * 1024 * 1024:
            size_gb = file_size / (1024 * 1024 * 1024)
            tc += f"{'File size (GiB)':<28}: {size_gb:.3f} GiB\n"

    tc += "</pre><br>"

    # Process Video sections
    video_count = 0
    for section_name, data in section_data.items():
        if section_name == "Video":
            video_count += 1
            tc += "<blockquote>Video</blockquote><pre>"
            tc += f"{'ID':<28}: {video_count}\n"

            for key, value in data:
                display_key = key
                if key.lower() == "format":
                    tc += f"{'Format':<28}: {value}\n"
                elif key.lower() == "format/info":
                    tc += f"{'Format/Info':<28}: {value}\n"
                elif key.lower() == "format profile":
                    tc += f"{'Format profile':<28}: {value}\n"
                elif key.lower() == "width":
                    tc += f"{'Width':<28}: {value} pixels\n"
                elif key.lower() == "height":
                    tc += f"{'Height':<28}: {value} pixels\n"
                elif key.lower() == "display aspect ratio":
                    tc += f"{'Display aspect ratio':<28}: {value}\n"
                elif key.lower() == "frame rate":
                    tc += f"{'Frame rate':<28}: {value}\n"
                elif key.lower() == "bit rate":
                    tc += f"{'Bit rate':<28}: {value}\n"
                elif key.lower() == "duration":
                    tc += f"{'Duration':<28}: {value}\n"
                elif key.lower() == "color space":
                    tc += f"{'Color space':<28}: {value}\n"
                elif key.lower() == "chroma subsampling":
                    tc += f"{'Chroma subsampling':<28}: {value}\n"
                elif key.lower() == "bit depth":
                    tc += f"{'Bit depth':<28}: {value}\n"
                elif key.lower() == "scan type":
                    tc += f"{'Scan type':<28}: {value}\n"
                else:
                    tc += f"{display_key:<28}: {value}\n"
            tc += "</pre><br>"

    # Process Audio sections
    audio_count = 0
    for section_name, data in section_data.items():
        if section_name == "Audio":
            audio_count += 1
            tc += "<blockquote>Audio</blockquote><pre>"
            tc += f"{'ID':<28}: {audio_count}\n"

            for key, value in data:
                display_key = key
                if key.lower() == "format":
                    tc += f"{'Format':<28}: {value}\n"
                elif key.lower() == "format/info":
                    tc += f"{'Format/Info':<28}: {value}\n"
                elif key.lower() == "format profile":
                    tc += f"{'Format profile':<28}: {value}\n"
                elif key.lower() == "sampling rate":
                    tc += f"{'Sampling rate':<28}: {value}\n"
                elif key.lower() == "channel(s)":
                    tc += f"{'Channel(s)':<28}: {value}\n"
                elif key.lower() == "channel layout":
                    tc += f"{'Channel layout':<28}: {value}\n"
                elif key.lower() == "bit rate":
                    tc += f"{'Bit rate':<28}: {value}\n"
                elif key.lower() == "duration":
                    tc += f"{'Duration':<28}: {value}\n"
                elif key.lower() == "bit depth":
                    tc += f"{'Bit depth':<28}: {value}\n"
                elif key.lower() == "compression mode":
                    tc += f"{'Compression mode':<28}: {value}\n"
                else:
                    tc += f"{display_key:<28}: {value}\n"
            tc += "</pre><br>"

    # Process Text/Subtitle sections
    subtitle_count = 0
    for section_name, data in section_data.items():
        if section_name == "Text":
            subtitle_count += 1
            tc += "<blockquote>Subtitle</blockquote><pre>"
            tc += f"{'ID':<28}: {subtitle_count}\n"

            for key, value in data:
                display_key = key
                if key.lower() == "format":
                    tc += f"{'Format':<28}: {value}\n"
                elif key.lower() == "language":
                    tc += f"{'Language':<28}: {value}\n"
                elif key.lower() == "title":
                    tc += f"{'Title':<28}: {value}\n"
                else:
                    tc += f"{display_key:<28}: {value}\n"
            tc += "</pre><br>"

    return tc


def parse_ffprobe_info(json_data, file_size, filename):
    tc = f"<h4>{filename}</h4><br><br><blockquote>General</blockquote><pre>"
    format_info = json_data.get("format", {})
    tc += f"{'Complete name':<28}: {filename}\n"

    # Format information with enhanced descriptions
    format_name = format_info.get("format_name", "")
    format_long_name = format_info.get("format_long_name", "")

    # Map container formats to more descriptive names
    container_format_info = {
        "matroska,webm": "Matroska / WebM",
        "mov,mp4,m4a,3gp,3g2,mj2": "MP4 / QuickTime",
        "avi": "Audio Video Interleave",
        "asf": "Advanced Systems Format",
        "flv": "Flash Video",
        "mpegts": "MPEG Transport Stream",
        "mpeg": "MPEG Program Stream",
        "ogg": "Ogg",
        "wav": "Waveform Audio",
        "aiff": "Audio Interchange File Format",
        "flac": "Free Lossless Audio Codec",
        "mp3": "MPEG Audio Layer III",
        "mp2": "MPEG Audio Layer II",
    }

    # Get a more descriptive format name if available
    display_format = container_format_info.get(format_name, format_name)
    tc += f"{'Format':<28}: {display_format}\n"

    # Add format info if available and not redundant
    if format_long_name and format_long_name not in (format_name, display_format):
        tc += f"{'Format/Info':<28}: {format_long_name}\n"

    # Add container profile if available
    if "tags" in format_info and "major_brand" in format_info["tags"]:
        major_brand = format_info["tags"]["major_brand"]
        tc += f"{'Format profile':<28}: {major_brand}\n"

        # Add compatible brands if available
        if "compatible_brands" in format_info["tags"]:
            tc += f"{'Compatible brands':<28}: {format_info['tags']['compatible_brands']}\n"

    # File size in different units with better formatting
    if file_size > 0:
        # Format file size with commas for thousands separator
        size_mb = file_size / (1024 * 1024)
        tc += f"{'File size':<28}: {size_mb:.2f} MiB ({file_size:,} bytes)\n"

        if file_size > 1024 * 1024 * 1024:
            size_gb = file_size / (1024 * 1024 * 1024)
            tc += f"{'File size (GiB)':<28}: {size_gb:.3f} GiB\n"

    # Duration in different formats
    if "duration" in format_info:
        duration_sec = float(format_info["duration"])
        hours, remainder = divmod(duration_sec, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Format duration as HH:MM:SS.mmm
        tc += f"{'Duration':<28}: {int(hours):02d}:{int(minutes):02d}:{seconds:06.3f}\n"

        # Also show duration in seconds for precision
        tc += f"{'Duration (seconds)':<28}: {duration_sec:.3f} s\n"

    # Bit rate with better formatting
    if "bit_rate" in format_info:
        bit_rate = int(format_info["bit_rate"])

        # Format bit rate based on size
        if bit_rate >= 1000000:
            tc += f"{'Overall bit rate':<28}: {bit_rate / 1000000:.2f} Mb/s\n"
        else:
            tc += f"{'Overall bit rate':<28}: {bit_rate / 1000:.0f} kb/s\n"

    # Frame rate if available in format
    if "avg_frame_rate" in format_info:
        # Parse frame rate fraction
        try:
            fr_parts = format_info["avg_frame_rate"].split("/")
            if len(fr_parts) == 2:
                num, den = int(fr_parts[0]), int(fr_parts[1])
                if den == 1:
                    tc += f"{'Frame rate':<28}: {num} FPS\n"
                else:
                    tc += f"{'Frame rate':<28}: {num / den:.3f} FPS ({format_info['avg_frame_rate']})\n"
            else:
                tc += f"{'Frame rate':<28}: {format_info['avg_frame_rate']} FPS\n"
        except (ValueError, ZeroDivisionError):
            tc += f"{'Frame rate':<28}: {format_info['avg_frame_rate']} FPS\n"

    # Stream count with more detail
    if "nb_streams" in format_info:
        nb_streams = int(format_info["nb_streams"])

        # Count stream types
        stream_types = defaultdict(int)
        for stream in json_data.get("streams", []):
            codec_type = stream.get("codec_type", "unknown").lower()
            stream_types[codec_type] += 1

        # Format stream count with breakdown
        stream_desc = f"{nb_streams}"
        if stream_types:
            stream_breakdown = []
            for stream_type, count in stream_types.items():
                if count > 0:
                    stream_breakdown.append(f"{count} {stream_type}")
            if stream_breakdown:
                stream_desc += f" ({', '.join(stream_breakdown)})"

        tc += f"{'Number of streams':<28}: {stream_desc}\n"

    # Additional format information
    for key in [
        "probe_score",
        "nb_programs",
    ]:
        if key in format_info:
            tc += f"{key.replace('_', ' ').capitalize():<28}: {format_info[key]}\n"

    # Format tags
    tags = format_info.get("tags", {})
    if tags:
        tc += "\n"  # Add a blank line before tags
        for k, v in tags.items():
            # Skip tags that we've already handled
            if k.lower() == "major_brand" or k.lower() == "compatible_brands":
                continue

            # Format common tags with better names
            display_key = k
            if k.lower() == "encoder":
                display_key = "Writing application"
            elif k.lower() == "creation_time":
                display_key = "Encoded date"
            elif k.lower() == "handler_name":
                display_key = "Handler name"
            elif k.lower() == "title":
                display_key = "Title"
            elif k.lower() == "comment":
                display_key = "Comment"
            elif k.lower() == "copyright":
                display_key = "Copyright"
            elif k.lower() == "language":
                display_key = "Language"
            elif k.lower() == "artist":
                display_key = "Artist"
            elif k.lower() == "album":
                display_key = "Album"
            elif k.lower() == "album_artist":
                display_key = "Album artist"
            elif k.lower() == "track":
                display_key = "Track"
            elif k.lower() == "genre":
                display_key = "Genre"
            elif k.lower() == "composer":
                display_key = "Composer"
            elif k.lower() == "date":
                display_key = "Date"
            else:
                display_key = k.replace("_", " ").capitalize()

            tc += f"{display_key:<28}: {v}\n"
    tc += "</pre><br>"

    # Counters for each stream type
    counters = {
        "video": 0,
        "audio": 0,
        "subtitle": 0,
        "data": 0,
        "attachment": 0,
        "cover": 0,
        "other": 0,
    }

    # Process streams
    for stream in json_data.get("streams", []):
        codec_type = stream.get("codec_type", "other").lower()
        codec_name = stream.get("codec_name", "").lower()
        codec_long_name = stream.get("codec_long_name", "")
        disposition = stream.get("disposition", {})

        # Detect cover image and attachments
        if codec_type == "video" and codec_name == "mjpeg":
            # Check if this is likely a cover art
            is_cover = False
            if (
                disposition.get("attached_pic", 0) == 1
                or (
                    "tags" in stream
                    and "mimetype" in stream["tags"]
                    and "image" in stream["tags"]["mimetype"]
                )
                or (
                    "tags" in stream
                    and "filename" in stream["tags"]
                    and any(
                        ext in stream["tags"]["filename"].lower()
                        for ext in [".jpg", ".jpeg", ".png", ".gif"]
                    )
                )
            ):
                is_cover = True

            if is_cover:
                section = "Cover"
                counters["cover"] += 1
                count = counters["cover"]
            else:
                counters["video"] += 1
                count = counters["video"]
                section = "Video"
        elif codec_type == "attachment":
            section = "Attachment"
            counters["attachment"] += 1
            count = counters["attachment"]
        else:
            if codec_type not in counters:
                codec_type = "other"
            counters[codec_type] += 1
            count = counters[codec_type]
            section = codec_type.capitalize()

        tc += f"<blockquote>{section}</blockquote><pre>"

        # Stream ID
        tc += f"{'ID':<28}: {stream.get('index', count)}\n"

        # Format information
        if codec_type == "attachment":
            # For attachments, use a more descriptive format name
            if codec_name in ["ttf", "otf"]:
                if codec_name == "ttf":
                    tc += f"{'Format':<28}: TTF\n"
                    tc += f"{'Format/Info':<28}: TrueType Font\n"
                    tc += f"{'Attachment type':<28}: Font\n"
                else:
                    tc += f"{'Format':<28}: OTF\n"
                    tc += f"{'Format/Info':<28}: OpenType Font\n"
                    tc += f"{'Attachment type':<28}: Font\n"
            elif "tags" in stream and "mimetype" in stream["tags"]:
                mimetype = stream["tags"]["mimetype"]
                if "image" in mimetype:
                    tc += f"{'Format':<28}: {mimetype.split('/')[-1].upper()}\n"
                    tc += f"{'Format/Info':<28}: {mimetype}\n"
                    tc += f"{'Attachment type':<28}: Image\n"
                elif "font" in mimetype or "truetype" in mimetype:
                    tc += f"{'Format':<28}: {mimetype.split('/')[-1].upper()}\n"
                    tc += f"{'Format/Info':<28}: {mimetype}\n"
                    tc += f"{'Attachment type':<28}: Font\n"
                else:
                    tc += f"{'Format':<28}: {mimetype.split('/')[-1].upper()}\n"
                    tc += f"{'Format/Info':<28}: {mimetype}\n"
            else:
                tc += f"{'Format':<28}: {codec_name.upper()}\n"
        else:
            tc += f"{'Format':<28}: {codec_name.upper()}\n"
            if codec_long_name and codec_long_name != codec_name:
                tc += f"{'Format/Info':<28}: {codec_long_name}\n"

        # Profile and level for video
        if codec_type == "video" and "profile" in stream:
            tc += f"{'Format profile':<28}: {stream['profile']}"
            if "level" in stream:
                tc += f"@L{stream['level']}"
            tc += "\n"

        # Format settings
        if "field_order" in stream:
            tc += f"{'Scan type':<28}: {stream['field_order'].capitalize()}\n"

        # Codec settings
        for setting in ["has_b_frames", "refs"]:
            if setting in stream:
                tc += f"{'Format settings, ' + setting.replace('_', ' ').capitalize():<28}: {stream[setting]}\n"

        # Duration
        if "duration" in stream:
            duration_sec = float(stream["duration"])
            hours, remainder = divmod(duration_sec, 3600)
            minutes, seconds = divmod(remainder, 60)
            tc += f"{'Duration':<28}: {int(hours):02d}:{int(minutes):02d}:{seconds:06.3f}\n"

        # Bit rate
        if "bit_rate" in stream:
            try:
                bit_rate = int(stream["bit_rate"])
                # Format bit rate based on size
                if bit_rate >= 1000000:
                    tc += f"{'Bit rate':<28}: {bit_rate / 1000000:.2f} Mb/s\n"
                else:
                    tc += f"{'Bit rate':<28}: {bit_rate / 1000:.0f} kb/s\n"
            except (ValueError, TypeError):
                # If conversion fails, use the raw value
                tc += f"{'Bit rate':<28}: {stream['bit_rate']}\n"

        # Video specific information
        if codec_type == "video":
            # Enhanced video codec information
            codec_name = stream.get("codec_name", "").lower()

            # Add more descriptive codec information
            format_info_added = False
            for line in tc.split("\n"):
                if "Format/Info" in line:
                    format_info_added = True
                    break

            if not format_info_added:
                if codec_name == "h264":
                    tc += f"{'Format/Info':<28}: H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
                elif codec_name == "hevc":
                    tc += f"{'Format/Info':<28}: H.265 / HEVC (High Efficiency Video Coding)\n"
                elif codec_name == "mpeg4":
                    tc += f"{'Format/Info':<28}: MPEG-4 Visual\n"
                elif codec_name == "mpeg2video":
                    tc += f"{'Format/Info':<28}: MPEG-2 Video\n"
                elif codec_name == "vp9":
                    tc += f"{'Format/Info':<28}: VP9 (Google/WebM)\n"
                elif codec_name == "av1":
                    tc += f"{'Format/Info':<28}: AV1 (AOMedia Video 1)\n"
                elif codec_name == "theora":
                    tc += f"{'Format/Info':<28}: Theora (Xiph.Org)\n"

            # Resolution
            if "width" in stream and "height" in stream:
                width = int(stream["width"])
                height = int(stream["height"])

                # Add standard resolution name if applicable
                resolution_name = ""
                if width == 3840 and height == 2160:
                    resolution_name = " (4K UHD)"
                elif width == 1920 and height == 1080:
                    resolution_name = " (Full HD)"
                elif width == 1280 and height == 720:
                    resolution_name = " (HD)"
                elif width == 720 and height == 576:
                    resolution_name = " (PAL)"
                elif width == 720 and height == 480:
                    resolution_name = " (NTSC)"

                tc += f"{'Width':<28}: {width} pixels\n"
                tc += f"{'Height':<28}: {height} pixels{resolution_name}\n"

                # Try to get display aspect ratio from stream
                display_aspect_ratio = stream.get("display_aspect_ratio", "")
                if not display_aspect_ratio:
                    # Calculate simple ratio
                    def gcd(a, b):
                        if b == 0:
                            return a
                        try:
                            return gcd(b, a % b)
                        except ZeroDivisionError:
                            return a

                    divisor = gcd(width, height)
                    if divisor > 0:
                        display_aspect_ratio = (
                            f"{width // divisor}:{height // divisor}"
                        )
                    else:
                        display_aspect_ratio = f"{width}:{height}"

                tc += f"{'Display aspect ratio':<28}: {display_aspect_ratio}\n"

            # Frame rate information
            if "r_frame_rate" in stream:
                # Parse frame rate fraction
                try:
                    fr_parts = stream["r_frame_rate"].split("/")
                    if len(fr_parts) == 2:
                        num, den = int(fr_parts[0]), int(fr_parts[1])
                        if den == 1:
                            tc += f"{'Frame rate':<28}: {num} FPS\n"
                        else:
                            tc += f"{'Frame rate':<28}: {num / den:.3f} FPS ({stream['r_frame_rate']})\n"
                    else:
                        tc += f"{'Frame rate':<28}: {stream['r_frame_rate']} FPS\n"
                except (ValueError, ZeroDivisionError):
                    tc += f"{'Frame rate':<28}: {stream['r_frame_rate']} FPS\n"

            # Frame rate mode
            if "avg_frame_rate" in stream and "r_frame_rate" in stream:
                if stream["avg_frame_rate"] == stream["r_frame_rate"]:
                    tc += f"{'Frame rate mode':<28}: Constant\n"
                else:
                    tc += f"{'Frame rate mode':<28}: Variable\n"

            # Color information
            for color_info in [
                "color_space",
                "color_range",
                "color_transfer",
                "color_primaries",
            ]:
                if color_info in stream:
                    # Make color space names more readable
                    value = stream[color_info]
                    if color_info == "color_space":
                        if value == "bt709":
                            value = "BT.709 (HDTV)"
                        elif value == "bt601":
                            value = "BT.601 (SDTV)"
                        elif value == "bt2020":
                            value = "BT.2020 (UHDTV)"

                    tc += (
                        f"{color_info.replace('_', ' ').capitalize():<28}: {value}\n"
                    )

            # Chroma subsampling
            if "pix_fmt" in stream:
                pix_fmt = stream["pix_fmt"]
                chroma_info = ""

                if "yuv420p" in pix_fmt:
                    chroma_info = "4:2:0"
                elif "yuv422p" in pix_fmt:
                    chroma_info = "4:2:2"
                elif "yuv444p" in pix_fmt:
                    chroma_info = "4:4:4"

                if chroma_info:
                    tc += f"{'Chroma subsampling':<28}: {chroma_info}\n"
            elif "chroma_location" in stream:
                tc += f"{'Chroma subsampling':<28}: {stream['chroma_location']}\n"

            # Bit depth
            if "bits_per_raw_sample" in stream:
                try:
                    bit_depth_value = int(stream["bits_per_raw_sample"])
                    if bit_depth_value > 0:
                        tc += f"{'Bit depth':<28}: {bit_depth_value} bits\n"
                except (ValueError, TypeError):
                    # If conversion fails, use the raw value
                    tc += (
                        f"{'Bit depth':<28}: {stream['bits_per_raw_sample']} bits\n"
                    )
            elif "pix_fmt" in stream:
                # Try to extract bit depth from pixel format
                pix_fmt = stream["pix_fmt"]
                if "p10" in pix_fmt:
                    tc += f"{'Bit depth':<28}: 10 bits\n"
                elif "p12" in pix_fmt:
                    tc += f"{'Bit depth':<28}: 12 bits\n"
                elif "p16" in pix_fmt:
                    tc += f"{'Bit depth':<28}: 16 bits\n"
                else:
                    tc += f"{'Bit depth':<28}: 8 bits\n"

            # Scan type already handled above

            # HDR information
            if "color_transfer" in stream and stream["color_transfer"] in [
                "smpte2084",
                "arib-std-b67",
            ]:
                if stream["color_transfer"] == "smpte2084":
                    tc += f"{'HDR format':<28}: HDR10 (SMPTE ST 2084)\n"
                elif stream["color_transfer"] == "arib-std-b67":
                    tc += f"{'HDR format':<28}: HLG (Hybrid Log-Gamma)\n"

            # Stream size if available
            if "duration" in stream and "bit_rate" in stream:
                try:
                    duration = float(stream["duration"])
                    bit_rate = float(stream["bit_rate"])
                    stream_size = duration * bit_rate / 8

                    # Format stream size
                    if stream_size > 1024 * 1024 * 1024:
                        tc += f"{'Stream size':<28}: {stream_size / (1024 * 1024 * 1024):.3f} GiB\n"
                    else:
                        tc += f"{'Stream size':<28}: {stream_size / (1024 * 1024):.2f} MiB\n"

                    # Add percentage of total size
                    if file_size > 0:
                        percentage = (stream_size / file_size) * 100
                        tc += (
                            f"{'Stream size (% of total)':<28}: {percentage:.1f}%\n"
                        )
                except (ValueError, TypeError):
                    # Skip stream size if conversion fails
                    pass

        # Audio specific information
        elif codec_type == "audio":
            # Enhanced codec information
            codec_name = stream.get("codec_name", "").lower()

            # Add more descriptive codec information
            if codec_name == "aac":
                if "profile" in stream:
                    profile = stream["profile"]
                    tc += f"{'Format profile':<28}: {profile}\n"
                tc += f"{'Format/Info':<28}: Advanced Audio Coding\n"
            elif codec_name == "mp3":
                tc += f"{'Format/Info':<28}: MPEG Audio Layer III\n"
                # Try to determine MP3 version and layer
                if "profile" in stream:
                    tc += f"{'Format profile':<28}: {stream['profile']}\n"
            elif codec_name == "ac3":
                tc += f"{'Format/Info':<28}: Dolby Digital\n"
            elif codec_name == "eac3":
                tc += f"{'Format/Info':<28}: Dolby Digital Plus\n"
            elif codec_name == "flac":
                tc += f"{'Format/Info':<28}: Free Lossless Audio Codec\n"
            elif codec_name == "opus":
                tc += f"{'Format/Info':<28}: Opus Audio Format\n"
            elif codec_name == "vorbis":
                tc += f"{'Format/Info':<28}: Vorbis Audio Codec\n"
            elif codec_name == "dts":
                tc += f"{'Format/Info':<28}: Digital Theater Systems\n"
            elif codec_name.startswith("pcm_"):
                # Parse PCM format details
                pcm_info = ""
                if "s16" in codec_name:
                    pcm_info = "16-bit Signed PCM"
                elif "s24" in codec_name:
                    pcm_info = "24-bit Signed PCM"
                elif "s32" in codec_name:
                    pcm_info = "32-bit Signed PCM"
                elif "f32" in codec_name:
                    pcm_info = "32-bit Float PCM"
                elif "f64" in codec_name:
                    pcm_info = "64-bit Float PCM"

                if "le" in codec_name:
                    pcm_info += " Little Endian"
                elif "be" in codec_name:
                    pcm_info += " Big Endian"

                if pcm_info:
                    tc += f"{'Format/Info':<28}: {pcm_info}\n"

            # Sample rate with more readable format
            if "sample_rate" in stream:
                sample_rate = int(stream["sample_rate"])
                if sample_rate >= 1000:
                    tc += f"{'Sampling rate':<28}: {sample_rate / 1000:.1f} kHz\n"
                else:
                    tc += f"{'Sampling rate':<28}: {sample_rate} Hz\n"

            # Channel information
            if "channels" in stream:
                channels = int(stream["channels"])
                channel_desc = f"{channels}"
                if channels == 1:
                    channel_desc += " (Mono)"
                elif channels == 2:
                    channel_desc += " (Stereo)"
                elif channels == 6:
                    channel_desc += " (5.1)"
                elif channels == 8:
                    channel_desc += " (7.1)"
                tc += f"{'Channel(s)':<28}: {channel_desc}\n"

            if "channel_layout" in stream:
                tc += f"{'Channel layout':<28}: {stream['channel_layout']}\n"

            # Bit depth - improved detection
            bit_depth = None
            if "bits_per_sample" in stream:
                try:
                    bit_depth_value = int(stream["bits_per_sample"])
                    if bit_depth_value > 0:
                        bit_depth = bit_depth_value
                except (ValueError, TypeError):
                    # If conversion fails, use the raw value
                    bit_depth = stream["bits_per_sample"]
            elif "bits_per_raw_sample" in stream:
                try:
                    bit_depth_value = int(stream["bits_per_raw_sample"])
                    if bit_depth_value > 0:
                        bit_depth = bit_depth_value
                except (ValueError, TypeError):
                    # If conversion fails, use the raw value
                    bit_depth = stream["bits_per_raw_sample"]
            # Try to determine bit depth from codec
            elif codec_name in {"pcm_s16le", "pcm_s16be"}:
                bit_depth = 16
            elif codec_name in {"pcm_s24le", "pcm_s24be"}:
                bit_depth = 24
            elif codec_name in {"pcm_s32le", "pcm_s32be"} or codec_name in {
                "pcm_f32le",
                "pcm_f32be",
            }:
                bit_depth = 32
            elif codec_name in {"pcm_f64le", "pcm_f64be"}:
                bit_depth = 64
            elif codec_name == "flac":
                # FLAC is typically 16 or 24 bit
                bit_depth = "16 or 24"
            elif codec_name in ["mp3", "aac", "vorbis", "opus"]:
                # These are variable bit depth formats
                bit_depth = "Variable"
            elif codec_name in ["ac3", "eac3"]:
                bit_depth = "16 to 24"
            elif codec_name == "dts":
                bit_depth = "Up to 24"

            if bit_depth:
                tc += f"{'Bit depth':<28}: {bit_depth} bits\n"

            # Compression mode
            if codec_name in [
                "pcm_s16le",
                "pcm_s24le",
                "pcm_s32le",
                "pcm_f32le",
                "pcm_f64le",
                "pcm_s16be",
                "pcm_s24be",
                "pcm_s32be",
                "pcm_f32be",
                "pcm_f64be",
            ] or codec_name in ["flac", "alac", "ape", "wavpack"]:
                tc += f"{'Compression mode':<28}: Lossless\n"
            elif "bit_rate" in stream:
                tc += f"{'Compression mode':<28}: Lossy\n"

                # Add quality information for lossy formats
                try:
                    if (codec_name == "mp3" and "bit_rate" in stream) or (
                        codec_name == "aac" and "bit_rate" in stream
                    ):
                        bit_rate = int(stream["bit_rate"])
                        if bit_rate < 128000:
                            quality = "Low"
                        elif bit_rate < 256000:
                            quality = "Medium"
                        else:
                            quality = "High"
                        tc += f"{'Quality':<28}: {quality} ({bit_rate / 1000:.0f} kb/s)\n"
                except (ValueError, TypeError):
                    # Skip quality info if bit_rate conversion fails
                    pass

            # Stream size if available
            if "duration" in stream and "bit_rate" in stream:
                try:
                    duration = float(stream["duration"])
                    bit_rate = float(stream["bit_rate"])
                    stream_size = duration * bit_rate / 8

                    # Format stream size
                    if stream_size > 1024 * 1024 * 1024:
                        tc += f"{'Stream size':<28}: {stream_size / (1024 * 1024 * 1024):.3f} GiB\n"
                    else:
                        tc += f"{'Stream size':<28}: {stream_size / (1024 * 1024):.2f} MiB\n"

                    # Add percentage of total size
                    if file_size > 0:
                        percentage = (stream_size / file_size) * 100
                        tc += (
                            f"{'Stream size (% of total)':<28}: {percentage:.1f}%\n"
                        )
                except (ValueError, TypeError):
                    # Skip stream size if conversion fails
                    pass

        # Subtitle specific information
        elif codec_type == "subtitle":
            # Enhanced subtitle codec information
            if "codec_name" in stream:
                codec_name = stream.get("codec_name", "").lower()

                # Map subtitle formats to more descriptive names
                subtitle_format_info = {
                    "subrip": "SubRip Text",
                    "ass": "Advanced SubStation Alpha",
                    "ssa": "SubStation Alpha",
                    "webvtt": "WebVTT (Web Video Text Tracks)",
                    "mov_text": "QuickTime Text",
                    "dvd_subtitle": "DVD Subtitle",
                    "hdmv_pgs_subtitle": "PGS (Presentation Graphics Stream)",
                    "dvb_subtitle": "DVB Subtitle",
                    "dvb_teletext": "DVB Teletext",
                    "arib_caption": "ARIB Caption",
                    "srt": "SubRip Text",
                    "microdvd": "MicroDVD",
                    "jacosub": "JACOsub",
                    "sami": "SAMI",
                    "realtext": "RealText",
                    "subviewer": "SubViewer",
                    "subviewer1": "SubViewer 1.0",
                    "vplayer": "VPlayer",
                }

                format_info = subtitle_format_info.get(
                    codec_name, codec_name.upper()
                )

                tc += f"{'Subtitle format':<28}: {codec_name.upper()}\n"
                if format_info != codec_name.upper():
                    tc += f"{'Format/Info':<28}: {format_info}\n"

                # Add subtitle properties if available
                if "disposition" in stream:
                    disposition = stream["disposition"]
                    if disposition.get("forced", 0) == 1:
                        tc += f"{'Forced':<28}: Yes\n"
                    if disposition.get("default", 0) == 1:
                        tc += f"{'Default':<28}: Yes\n"

                # Add language information if not in tags
                if "tags" not in stream or "language" not in stream["tags"]:
                    # Try to detect language from stream index or other properties
                    if "index" in stream:
                        index = stream["index"]
                        if (
                            index == 1
                        ):  # Often the first subtitle track is the main language
                            tc += f"{'Language':<28}: Primary\n"
                        elif (
                            index == 2
                        ):  # Often the second subtitle track is English
                            tc += f"{'Language':<28}: Secondary\n"

        # Stream tags
        tags = stream.get("tags", {})
        if tags:
            tc += "\n"  # Add a blank line before tags

            # Special handling for cover art
            if section == "Cover":
                # Display filename first if available
                if "filename" in tags:
                    tc += f"{'Filename':<28}: {tags['filename']}\n"

                # Display mimetype if available
                if "mimetype" in tags:
                    tc += f"{'Mimetype':<28}: {tags['mimetype']}\n"

                # Then display other tags
                for k, v in tags.items():
                    if k.lower() not in ["filename", "mimetype"]:
                        tc += f"{k.replace('_', ' ').capitalize():<28}: {v}\n"
            else:
                # Normal tag display for other stream types
                for k, v in tags.items():
                    if k.lower() == "language":
                        tc += f"{'Language':<28}: {v}\n"
                    elif k.lower() == "title":
                        tc += f"{'Title':<28}: {v}\n"
                    elif k.lower() == "handler_name":
                        tc += f"{'Handler name':<28}: {v}\n"
                    else:
                        tc += f"{k.replace('_', ' ').capitalize():<28}: {v}\n"
        tc += "</pre><br>"

    # Chapters
    chapters = json_data.get("chapters", [])
    if chapters:
        tc += "<blockquote>Chapters</blockquote><pre>"
        for i, chapter in enumerate(chapters):
            start = float(chapter.get("start_time", 0))
            end = float(chapter.get("end_time", 0))

            # Format time in HH:MM:SS.mmm
            start_h, start_remainder = divmod(start, 3600)
            start_m, start_s = divmod(start_remainder, 60)

            end_h, end_remainder = divmod(end, 3600)
            end_m, end_s = divmod(end_remainder, 60)

            tc += f"Chapter {i + 1:<20}: {int(start_h):02d}:{int(start_m):02d}:{start_s:06.3f} - {int(end_h):02d}:{int(end_m):02d}:{end_s:06.3f}\n"

            # Chapter title if available
            if "tags" in chapter and "title" in chapter["tags"]:
                tc += f"{'Title':<28}: {chapter['tags']['title']}\n"

            # Other chapter tags
            for k, v in chapter.get("tags", {}).items():
                if k != "title":  # Skip title as we already displayed it
                    tc += f"{k.replace('_', ' ').capitalize():<28}: {v}\n"

            # Add separator between chapters
            if i < len(chapters) - 1:
                tc += "----------------------------------------\n"
        tc += "</pre><br>"

    # Programs
    programs = json_data.get("programs", [])
    if programs:
        tc += "<blockquote>Programs</blockquote><pre>"
        for i, prog in enumerate(programs):
            tc += f"Program {i + 1}:\n"
            for k, v in prog.items():
                if isinstance(v, str | int | float):
                    tc += f"{k.replace('_', ' ').capitalize():<28}: {v}\n"
            # Add separator between programs
            if i < len(programs) - 1:
                tc += "----------------------------------------\n"
        tc += "</pre><br>"

    return tc


async def gen_mediainfo(
    message, link=None, media=None, reply=None, media_path=None, silent=False
):
    """
    Generate MediaInfo for a file

    Args:
        message: Telegram message object
        link: Direct download link to the file
        media: Telegram media object
        reply: Reply message object
        media_path: Direct path to the media file (for internal use)
        silent: If True, don't send status messages (for internal use)

    Returns:
        str: Telegraph link path or None if failed
    """

    temp_send = (
        None
        if silent
        else await send_message(
            message,
            "Generating MediaInfo with ffprobe (mediainfo fallback available)...",
        )
    )
    des_path = None
    tc = ""

    # Initialize file_size to 0
    file_size = 0

    try:
        # Initialize the temporary download directory path (only used for downloads)
        # Use absolute path to avoid workdir mismatch issues with Pyrogram client
        current_dir = os.getcwd()
        temp_download_path = ospath.join(current_dir, "Mediainfo")

        # Initialize des_path to None
        des_path = None

        # Handle direct file path (from telegram_uploader or other internal calls)
        if media_path:
            # Validate media_path is a string
            if not isinstance(media_path, str):
                error_msg = f"MediaInfo: Invalid media_path type: {type(media_path)}, expected string"
                LOGGER.error(error_msg)
                if not silent:
                    await send_message(message, error_msg)
                return None

            # Check if file exists
            if not await aiopath.exists(media_path):
                error_msg = f"MediaInfo: File not found: {media_path}"
                LOGGER.error(error_msg)
                if not silent:
                    await send_message(message, error_msg)
                return None

            # File exists, set des_path and get file size
            des_path = media_path
            try:
                file_size = await aiopath.getsize(media_path)
                if file_size == 0:
                    error_msg = (
                        f"MediaInfo: File exists but has zero size: {media_path}"
                    )
                    LOGGER.error(error_msg)
                    if not silent:
                        await send_message(message, error_msg)
                    return None
            except Exception as e:
                error_msg = (
                    f"MediaInfo: Error accessing file: {media_path}, Error: {e}"
                )
                LOGGER.error(error_msg)
                if not silent:
                    await send_message(message, error_msg)
                return None
        elif link:
            # Handle direct download links
            # Only create the Mediainfo directory if we need to download files
            # Ensure the Mediainfo directory exists for downloads
            if not await aiopath.isdir(temp_download_path):
                try:
                    await mkdir(temp_download_path)
                    LOGGER.info(f"Created directory: {temp_download_path}")
                except Exception as e:
                    LOGGER.error(
                        f"Error creating directory {temp_download_path}: {e}"
                    )
                    # Try with absolute path
                    abs_path = ospath.abspath(temp_download_path)
                    if not ospath.isdir(abs_path):
                        try:
                            os.makedirs(abs_path, exist_ok=True)
                            LOGGER.info(
                                f"Created directory with absolute path: {abs_path}"
                            )
                        except Exception as e2:
                            LOGGER.error(
                                f"Error creating directory with absolute path {abs_path}: {e2}"
                            )
                            # Fall back to a different directory using absolute path
                            temp_download_path = ospath.join(
                                current_dir, "downloads", "Mediainfo"
                            )
                            if not await aiopath.isdir(temp_download_path):
                                try:
                                    await mkdir(temp_download_path)
                                    LOGGER.info(
                                        f"Created fallback directory: {temp_download_path}"
                                    )
                                except Exception as e3:
                                    LOGGER.error(
                                        f"Error creating fallback directory {temp_download_path}: {e3}"
                                    )
                                    # Use current working directory as last resort
                                    temp_download_path = current_dir
                                    LOGGER.warning(
                                        f"Using current directory as fallback: {temp_download_path}"
                                    )
                if not is_url(link):
                    raise ValueError(f"Invalid URL: {link}")

                # Check for Google Drive index links that can't be processed directly
                gdrive_index_patterns = [
                    r"findpath\?id=",  # Google Drive index with findpath
                    r"drive\.google\.com.*\/folders\/",  # Google Drive folder links
                    r"drive\.google\.com.*\/file\/d\/.*\/view",  # Google Drive file view links
                    r"\/0:",  # Common Google Drive index pattern
                    r"\/api\/v1\/",  # API-based index links
                ]

                is_gdrive_index = any(
                    re_search(pattern, link) for pattern in gdrive_index_patterns
                )

                if is_gdrive_index:
                    error_msg = "❌ MediaInfo failed: Cannot directly process Google Drive index links. Please download the file first and then use the /mediainfo command on the downloaded file."
                    LOGGER.error(f"Google Drive index link detected: {link}")
                    if not silent:
                        if temp_send:
                            await edit_message(temp_send, error_msg)
                        else:
                            await send_message(message, error_msg)
                    return None

                # Extract filename from URL, handling special cases
                # First check if the URL contains 'findpath' with an id parameter (shouldn't reach here due to above check)
                findpath_match = re_search(r"findpath\?id=([^&]+)", link)
                if findpath_match:
                    # This is a Google Drive index link with findpath parameter
                    # Use the id as part of the filename
                    drive_id = findpath_match.group(1)
                    filename = f"gdrive_{drive_id}_{int(time())}"
                else:
                    # Regular URL filename extraction
                    filename_match = re_search(".+/([^/?]+)", link)
                    filename = (
                        filename_match.group(1)
                        if filename_match
                        else f"mediainfo_{int(time())}"
                    )

                # Clean filename of any problematic characters (keep spaces for better readability)
                filename = filename.replace("'", "").replace('"', "")

                # Ensure we have a valid temp_download_path
                if not temp_download_path:
                    temp_download_path = ospath.join(current_dir, "Mediainfo")
                    LOGGER.warning(
                        f"temp_download_path was empty, using default: {temp_download_path}"
                    )

                des_path = ospath.join(temp_download_path, filename)

                # Validate that des_path was set correctly
                if not des_path or not isinstance(des_path, str):
                    error_msg = f"MediaInfo: Failed to create valid destination path from link. temp_download_path: {temp_download_path}, filename: {filename}"
                    LOGGER.error(error_msg)
                    if not silent:
                        await send_message(message, error_msg)
                    return None

                # Update status message if not in silent mode
                if not silent and temp_send:
                    await edit_message(
                        temp_send,
                        f"Downloading a sample of {filename} for analysis...",
                    )

                headers = {
                    "user-agent": "Mozilla/5.0 (Linux; Android 12; 2201116PI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36",
                    "Range": "bytes=0-10485760",  # Download up to 10MB for analysis
                }

                async with aiohttp.ClientSession() as session:
                    try:
                        # Set a reasonable timeout (5 minutes)
                        async with session.get(
                            link, headers=headers, timeout=300
                        ) as response:
                            # Get total file size from Content-Range header if available
                            content_range = response.headers.get("Content-Range", "")
                            if content_range:
                                try:
                                    file_size = int(content_range.split("/")[1])
                                except (IndexError, ValueError):
                                    file_size = 0

                            # If Content-Range not available, use Content-Length
                            if not file_size:
                                file_size = int(
                                    response.headers.get("Content-Length", 0)
                                )

                            # Download sample of the file using read() with a size limit
                            # This approach avoids ContentLengthError when we don't read the entire response
                            downloaded_size = 0
                            max_sample_size = 10 * 1024 * 1024  # 10MB

                            async with aiopen(des_path, "wb") as f:
                                # Read in 1MB chunks to have better control and progress updates
                                chunk_size = 1024 * 1024  # 1MB
                                while downloaded_size < max_sample_size:
                                    try:
                                        # Read just one chunk at a time
                                        chunk = await response.content.read(
                                            chunk_size
                                        )
                                        if (
                                            not chunk
                                        ):  # Empty chunk means end of response
                                            break

                                        await f.write(chunk)
                                        downloaded_size += len(chunk)

                                        # Periodically update status for large files if not in silent mode
                                        if (
                                            not silent
                                            and temp_send
                                            and downloaded_size % (5 * 1024 * 1024)
                                            == 0
                                        ):  # Every 5MB
                                            await edit_message(
                                                temp_send,
                                                f"Downloading sample of {filename} for analysis... ({downloaded_size / (1024 * 1024):.1f} MB)",
                                            )
                                    except Exception:
                                        break

                                # If we got at least some data, consider it a success
                                if downloaded_size > 0:
                                    LOGGER.info(
                                        f"Successfully downloaded {downloaded_size / (1024 * 1024):.1f} MB sample of {filename}"
                                    )
                                # Check if this might be a Google Drive index link with findpath
                                elif "findpath" in link:
                                    LOGGER.error(
                                        f"Failed to download data from Google Drive index link: {link}. This might require authentication or the file might not be directly accessible."
                                    )
                                    raise Exception(
                                        "Failed to download from Google Drive index link. Try downloading the file first and then generating MediaInfo."
                                    )
                                else:
                                    LOGGER.error(
                                        f"Failed to download any data from {link}"
                                    )
                                    raise Exception(
                                        "Failed to download any data from the link"
                                    )

                    except aiohttp.ClientError as ce:
                        # Handle specific aiohttp client errors
                        LOGGER.error(
                            f"HTTP client error downloading from {link}: {ce}"
                        )
                        if (
                            not await aiopath.exists(des_path)
                            or await aiopath.getsize(des_path) == 0
                        ):
                            raise Exception(f"Failed to download file sample: {ce}")
                        # If we have some data, continue with what we have
                        LOGGER.info(
                            f"Continuing with partial download ({await aiopath.getsize(des_path) / (1024 * 1024):.1f} MB)"
                        )

                    except Exception as e:
                        LOGGER.error(f"Error downloading from {link}: {e}")

                        # Clean up any partial download
                        if await aiopath.exists(des_path):
                            try:
                                await aioremove(des_path)
                                LOGGER.info(
                                    f"Cleaned up partial download: {des_path}"
                                )
                            except Exception as cleanup_error:
                                LOGGER.error(
                                    f"Error cleaning up partial download: {cleanup_error}"
                                )

                        # Provide more specific error messages based on the error type
                        if "403" in str(e) or "Forbidden" in str(e):
                            raise Exception(
                                "Access denied: The server refused the request. The link may be private or require authentication."
                            )
                        if "404" in str(e) or "Not Found" in str(e):
                            raise Exception(
                                "File not found: The requested file no longer exists on the server."
                            )
                        if "timeout" in str(e).lower():
                            raise Exception(
                                "Download timeout: The server took too long to respond. Please try again later."
                            )
                        if "connection" in str(e).lower():
                            raise Exception(
                                "Connection failed: Unable to connect to the server. Please check the link and try again."
                            )
                        raise Exception(f"Download failed: {e}")

                        # This code won't be reached due to the raise above, but keeping for safety
                        if (
                            not await aiopath.exists(des_path)
                            or await aiopath.getsize(des_path) == 0
                        ):
                            raise Exception(f"Failed to download file sample: {e}")
                        # If we have some data, continue with what we have
                        LOGGER.info(
                            f"Continuing with partial download ({await aiopath.getsize(des_path) / (1024 * 1024):.1f} MB)"
                        )

                    finally:
                        # Run garbage collection after download to free memory
                        smart_garbage_collection(aggressive=False)

        elif media is not None:
            # Don't redeclare des_path - use the function-level variable
            # Initialize tracking variable for media processing
            media_processing_successful = False

            try:
                # Ensure media.file_name is not None
                if not hasattr(media, "file_name") or media.file_name is None:
                    # Generate a default filename if none exists
                    file_name = f"mediainfo_{int(time())}"
                    LOGGER.warning(
                        f"Media has no filename, using generated name: {file_name}"
                    )
                else:
                    file_name = media.file_name

                # Clean filename of any problematic characters more thoroughly
                # Remove or replace characters that can cause issues with file paths
                import re

                # Replace problematic characters with safe alternatives
                file_name = file_name.replace("[", "(").replace(
                    "]", ")"
                )  # Replace brackets with parentheses
                file_name = file_name.replace("'", "").replace(
                    '"', ""
                )  # Remove quotes
                file_name = re.sub(
                    r'[<>:"|?*]', "_", file_name
                )  # Replace Windows-forbidden characters
                # Keep spaces in filename for better readability
                # file_name = re.sub(r"\s+", "_", file_name)  # Commented out to preserve spaces
                file_name = file_name.strip(
                    "._"
                )  # Remove leading/trailing dots and underscores

                # Ensure filename is not empty after cleaning
                if not file_name or file_name == "":
                    file_name = f"mediainfo_{int(time())}"
                    LOGGER.warning(
                        f"Filename became empty after cleaning, using generated name: {file_name}"
                    )

                # Ensure we have a valid temp_download_path
                if not temp_download_path:
                    temp_download_path = ospath.join(current_dir, "Mediainfo")
                    LOGGER.warning(
                        f"temp_download_path was empty, using default: {temp_download_path}"
                    )

                # Create des_path with error handling
                try:
                    des_path = ospath.join(temp_download_path, file_name)
                except Exception as path_error:
                    LOGGER.error(
                        f"MediaInfo: Error creating des_path from temp_download_path='{temp_download_path}' and file_name='{file_name}': {path_error}"
                    )
                    # Try with a simpler filename
                    simple_filename = f"mediainfo_{int(time())}.mkv"
                    try:
                        des_path = ospath.join(temp_download_path, simple_filename)
                    except Exception as simple_path_error:
                        LOGGER.error(
                            f"MediaInfo: Even simple path creation failed: {simple_path_error}"
                        )
                        raise Exception(
                            f"Failed to create valid file path: {simple_path_error}"
                        )

                file_size = getattr(media, "file_size", 0)

                # Validate that des_path was set correctly
                if not des_path or not isinstance(des_path, str):
                    error_msg = f"MediaInfo: Failed to create valid destination path from media. temp_download_path: {temp_download_path}, file_name: {file_name}"
                    LOGGER.error(error_msg)
                    if not silent:
                        await send_message(message, error_msg)
                    return None

                # Mark that des_path was successfully set
                media_processing_successful = True

                # Ensure the download directory exists
                if not await aiopath.isdir(temp_download_path):
                    try:
                        await mkdir(temp_download_path)

                    except Exception as e:
                        LOGGER.error(
                            f"Error creating directory {temp_download_path}: {e}"
                        )
                        error_msg = (
                            f"MediaInfo: Failed to create download directory: {e}"
                        )
                        if not silent:
                            await send_message(message, error_msg)
                        return None

                # Update status message if not in silent mode
                if not silent and temp_send:
                    await edit_message(
                        temp_send,
                        f"Downloading a sample of {file_name} for analysis...",
                    )

                # Check if we have a reply message to download from
                if not reply:
                    error_msg = (
                        "MediaInfo: No reply message provided for media download"
                    )
                    LOGGER.error(error_msg)
                    if not silent:
                        await send_message(message, error_msg)
                    return None

                # For MediaInfo, we need to download the file to analyze it
                # We'll be more generous with the size limit since MediaInfo needs actual file data
                if file_size <= 100 * 1024 * 1024:  # 100MB
                    # For small files, download the entire file
                    try:
                        LOGGER.info(f"Downloading Telegram media to: {des_path}")
                        await reply.download(des_path)

                        # Verify the file was downloaded successfully
                        if not await aiopath.exists(des_path):
                            raise Exception(
                                f"Download failed - file not created at: {des_path}"
                            )

                        downloaded_size = await aiopath.getsize(des_path)
                        LOGGER.info(
                            f"Successfully downloaded {downloaded_size} bytes to {des_path}"
                        )

                    except Exception as e:
                        LOGGER.error(f"Error downloading file: {e}")
                        raise Exception(f"Failed to download file: {e}")

                    # Run garbage collection after download to free memory
                    smart_garbage_collection(aggressive=False)
                else:
                    # For large files, download only a sample portion for analysis
                    # Use larger sample for video files to ensure we get enough metadata
                    file_ext = ospath.splitext(file_name)[1].lower()
                    video_exts = {
                        ".mkv",
                        ".mp4",
                        ".avi",
                        ".mov",
                        ".wmv",
                        ".flv",
                        ".webm",
                        ".m4v",
                        ".ts",
                        ".mts",
                    }

                    if file_ext in video_exts:
                        sample_size = 50 * 1024 * 1024  # 50MB for video files
                    else:
                        sample_size = 20 * 1024 * 1024  # 20MB for other files

                    size_mb = file_size / (1024 * 1024)

                    if not silent and temp_send:
                        await edit_message(
                            temp_send,
                            f"Large file detected ({size_mb:.1f} MB). Downloading sample for analysis...",
                        )

                    try:
                        # For large files, we'll use Pyrogram's stream_media to download only what we need
                        # This is more efficient than downloading the full file and truncating
                        downloaded_bytes = 0

                        async with aiopen(des_path, "wb") as f:
                            # Use the bot client to stream the media
                            from bot.core.aeon_client import TgClient

                            async for chunk in TgClient.bot.stream_media(media):
                                await f.write(chunk)
                                downloaded_bytes += len(chunk)

                                # Stop when we've downloaded enough for analysis
                                if downloaded_bytes >= sample_size:
                                    break

                        # Verify the file was created and check its properties
                        if not await aiopath.exists(des_path):
                            LOGGER.error(
                                f"Sample download failed - file not created at: {des_path}"
                            )
                            raise Exception(
                                "Sample download failed - file not created"
                            )

                        actual_size = await aiopath.getsize(des_path)

                        # Check if we got enough data for analysis
                        min_sample_size = 1 * 1024 * 1024  # 1MB minimum
                        if actual_size < min_sample_size:
                            LOGGER.warning(
                                f"Downloaded sample ({actual_size} bytes) may be too small for proper analysis"
                            )

                    except Exception as e:
                        LOGGER.error(
                            f"Error downloading sample from large Telegram media: {e}"
                        )
                        raise Exception(f"Failed to download media sample: {e}")

                    # Run garbage collection after download to free memory
                    smart_garbage_collection(aggressive=False)

            except Exception as e:
                LOGGER.error(f"MediaInfo: Error processing media object: {e}")

                # Check if des_path was set before the error occurred
                if des_path and media_processing_successful:
                    # Check if the file was partially downloaded
                    try:
                        if await aiopath.exists(des_path):
                            file_size_check = await aiopath.getsize(des_path)
                            if file_size_check > 0:
                                # Don't return None - let the function continue with the partial file
                                pass  # This will allow the function to continue after the except block
                            else:
                                if not silent:
                                    error_msg = f"MediaInfo: Downloaded file has zero size: {e}"
                                    await send_message(message, error_msg)
                                return None
                        else:
                            if not silent:
                                error_msg = (
                                    f"MediaInfo: Failed to download media file: {e}"
                                )
                                await send_message(message, error_msg)
                            return None
                    except Exception as check_error:
                        LOGGER.error(
                            f"MediaInfo: Error checking downloaded file: {check_error}"
                        )
                        if not silent:
                            error_msg = (
                                f"MediaInfo: Failed to process media file: {e}"
                            )
                            await send_message(message, error_msg)
                        return None
                else:
                    if not silent:
                        error_msg = (
                            f"MediaInfo: Failed to set up media file path: {e}"
                        )
                        await send_message(message, error_msg)
                    return None
        else:
            # No media_path, link, or media provided
            error_msg = "MediaInfo: No file path, link, or media provided. Please provide one of: media_path, link, or media with reply."
            LOGGER.error(error_msg)
            if not silent:
                await send_message(message, error_msg)
            return None

        # Final validation: Check if des_path was set by any of the above branches
        if not des_path:
            # Add detailed debugging information
            debug_info = f"media_path={media_path}, link={link is not None}, media={media is not None}, reply={reply is not None}"

            # Additional debugging for media branch
            if media:
                media_debug = f"media.file_name={getattr(media, 'file_name', 'None')}, media.file_size={getattr(media, 'file_size', 'None')}"
                debug_info += f", {media_debug}"

            error_msg = f"MediaInfo: Internal error - file path could not be determined despite successful validation. Debug: {debug_info}"
            LOGGER.error(error_msg)
            if not silent:
                await send_message(message, error_msg)
            return None

        # Additional validation: Ensure des_path is a valid string
        if not isinstance(des_path, str | bytes):
            error_msg = f"MediaInfo: Internal error - invalid path type: {type(des_path)}, value: {des_path}"
            LOGGER.error(error_msg)
            if not silent:
                await send_message(message, error_msg)
            return None

        # Check if file exists and is accessible
        if (
            not des_path
            or not isinstance(des_path, str | bytes)
            or not await aiopath.exists(des_path)
        ):
            error_msg = f"MediaInfo: File not found or invalid path: {des_path}"
            LOGGER.error(error_msg)
            if not silent:
                await send_message(message, error_msg)
            return None

        # Double check file exists and is accessible
        try:
            # Try to get file size to verify it's accessible
            file_size_check = await aiopath.getsize(des_path)
            if file_size_check == 0:
                error_msg = f"MediaInfo: File exists but has zero size: {des_path}"
                LOGGER.error(error_msg)
                if not silent:
                    await send_message(message, error_msg)
                return None
        except Exception as e:
            error_msg = f"MediaInfo: Error accessing file: {des_path}, Error: {e}"
            LOGGER.error(error_msg)
            if not silent:
                await send_message(message, error_msg)
            return None

        # Update status message if not in silent mode
        if not silent and temp_send:
            await edit_message(temp_send, "Analyzing media file with ffprobe...")

        # Check if it's a subtitle file or archive file based on extension
        try:
            if isinstance(des_path, str):
                file_ext = ospath.splitext(des_path)[1].lower()
                filename = ospath.basename(des_path).lower()
            else:
                # Default values if des_path is not a string
                file_ext = ""
                filename = f"mediainfo_{int(time())}"
                LOGGER.warning(
                    f"Invalid des_path type: {type(des_path)}, using default filename"
                )
        except Exception as e:
            LOGGER.error(f"Error extracting file extension: {e}")
            file_ext = ""
            filename = f"mediainfo_{int(time())}"

        # Define file type extensions
        subtitle_exts = [
            ".srt",
            ".ass",
            ".ssa",
            ".vtt",
            ".sub",
            ".idx",
            ".stl",
            ".scc",
            ".ttml",
            ".sbv",
            ".dfxp",
            ".smi",
            ".webvtt",
        ]
        archive_exts = [
            ".zip",
            ".rar",
            ".7z",
            ".tar",
            ".gz",
            ".bz2",
            ".xz",
            ".iso",
            ".cab",
            ".arj",
            ".lzh",
            ".udf",
            ".wim",
        ]
        image_exts = [
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".webp",
            ".tiff",
            ".svg",
            ".eps",
            ".psd",
        ]
        document_exts = [
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".txt",
            ".md",
            ".epub",
        ]

        # Check for split archives with part numbers
        is_split_archive = False

        # First check if the file extension is in archive_exts
        is_archive = file_ext in archive_exts

        # If not a direct archive extension, check for split archive patterns
        if not is_archive:
            # Check for split archive patterns - be more specific to avoid false positives
            if (
                re_search(
                    r"\.part0*[0-9]+\.rar$", filename
                )  # Match .part1.rar, .part01.rar, etc.
                or re_search(
                    r"\.part0*[0-9]+\.zip$", filename
                )  # Match .part1.zip, .part01.zip, etc.
                or re_search(
                    r"\.part0*[0-9]+\.7z$", filename
                )  # Match .part1.7z, .part01.7z, etc.
                or re_search(r"\.r[0-9]+$", filename)  # Match .r00, .r01, etc.
                or re_search(r"\.z[0-9]+$", filename)  # Match .z01, .z02, etc.
                or re_search(r"\.zip\.[0-9]+$", filename)  # Match .zip.001, etc.
                or re_search(r"\.rar\.[0-9]+$", filename)  # Match .rar.001, etc.
            ):
                # For these specific patterns, we're confident it's an archive
                is_split_archive = True
                is_archive = True
            elif (
                re_search(r"\.[0-9]{3}$", filename)  # Match .001, .002, etc.
                or re_search(r"\.[0-9]{2}$", filename)  # Match .01, .02, etc.
                or re_search(r"\.[0-9]$", filename)  # Match .1, .2, etc.
            ):
                # For generic numeric extensions, we need to verify it's actually an archive
                # This prevents false positives with split video files like .mkv.001
                try:
                    # Use file command to verify it's an archive
                    abs_path = ospath.abspath(des_path)
                    cmd = ["file", "-b", abs_path]
                    # Add timeout to prevent hanging
                    import asyncio

                    stdout, stderr, return_code = await asyncio.wait_for(
                        cmd_exec(cmd),
                        timeout=10.0,  # 10 second timeout for file command
                    )
                    if return_code == 0 and stdout:
                        stdout_lower = stdout.lower()
                        # Check for archive types
                        if any(
                            archive_type in stdout_lower
                            for archive_type in [
                                "zip",
                                "rar",
                                "7-zip",
                                "tar",
                                "gzip",
                                "bzip2",
                                "xz",
                                "iso",
                                "archive",
                            ]
                        ):
                            is_split_archive = True
                            is_archive = True
                        # Check for video/media types to explicitly exclude them
                        elif any(
                            media_type in stdout_lower
                            for media_type in [
                                "video",
                                "audio",
                                "media",
                                "matroska",
                                "mp4",
                                "avi",
                                "mkv",
                                "webm",
                                "mov",
                                "flv",
                                "wmv",
                                "mpeg",
                                "h.264",
                                "h.265",
                                "hevc",
                            ]
                        ):
                            # This is definitely a media file, not an archive
                            is_split_archive = False
                            is_archive = False
                        else:
                            # If file command returns "data" or unknown, be conservative
                            # and don't assume it's an archive
                            is_split_archive = False
                            is_archive = False
                    else:
                        # If file command fails, don't assume it's an archive
                        # Let it be processed as a regular media file
                        LOGGER.warning(
                            f"file command failed for {filename}, treating as media file"
                        )
                        is_split_archive = False
                        is_archive = False
                except (Exception, TimeoutError):
                    # If verification fails or times out, don't assume it's an archive
                    # This prevents false positives with split video files
                    is_split_archive = False
                    is_archive = False  # Always use file command to verify archive type, even for known extensions
        # This provides more accurate information and handles cases where extensions don't match content
        try:
            # Verify file exists before running file command
            if not isinstance(des_path, str):
                LOGGER.warning(
                    f"Cannot run file command on non-string path: {des_path}"
                )
            else:
                abs_path = ospath.abspath(des_path)
                if not ospath.exists(abs_path):
                    LOGGER.warning(f"File does not exist at path: {abs_path}")
                else:
                    # File exists, proceed with file command
                    cmd = ["file", "-b", abs_path]
                    stdout, stderr, return_code = await cmd_exec(cmd)
                    if return_code == 0 and stdout:
                        stdout_lower = stdout.lower()
                        # If it's already identified as an archive, this will provide additional info
                        # If not, this might identify it as an archive despite the extension
                        if any(
                            archive_type in stdout_lower
                            for archive_type in [
                                "zip",
                                "rar",
                                "7-zip",
                                "tar",
                                "gzip",
                                "bzip2",
                                "xz",
                                "iso",
                                "archive",
                            ]
                        ):
                            is_archive = True  # Try to determine the specific archive format from file output
                            if "rar archive" in stdout_lower:
                                file_ext = (
                                    ".rar"  # Override extension for correct handling
                                )
                            elif "zip archive" in stdout_lower:
                                file_ext = ".zip"
                            elif "7-zip archive" in stdout_lower:
                                file_ext = ".7z"
                            elif "tar archive" in stdout_lower:
                                file_ext = ".tar"
                            elif "gzip compressed" in stdout_lower:
                                file_ext = ".gz"
                            elif "bzip2 compressed" in stdout_lower:
                                file_ext = ".bz2"
                            elif "xz compressed" in stdout_lower:
                                file_ext = ".xz"
                            elif "iso 9660" in stdout_lower:
                                file_ext = ".iso"
                    elif return_code != 0:
                        pass
        except Exception:
            # Continue with the process, using the extension-based detection as fallback
            pass

        # Handle archive files
        if is_archive:
            # Special handling for archive files
            if not silent and temp_send:
                await edit_message(temp_send, "Analyzing archive file...")

            # Create basic info for archive files
            tc = f"<h4>{ospath.basename(des_path)}</h4><br><br><blockquote>General</blockquote><pre>"
            tc += f"{'Complete name':<28}: {ospath.basename(des_path)}\n"

            # Determine archive format with improved detection
            archive_format = ""

            # First try to determine format from file extension
            if file_ext == ".rar":
                archive_format = "RAR"
            elif file_ext == ".zip":
                archive_format = "ZIP"
            elif file_ext == ".7z":
                archive_format = "7Z"
            elif file_ext == ".tar":
                archive_format = "TAR"
            elif file_ext == ".gz":
                archive_format = "GZ"
            elif file_ext == ".bz2":
                archive_format = "BZ2"
            elif file_ext == ".xz":
                archive_format = "XZ"
            elif file_ext == ".iso":
                archive_format = "ISO"
            elif file_ext == ".cab":
                archive_format = "CAB"
            elif is_split_archive:
                # For split archives, try to determine the format from the filename pattern
                if (
                    re_search(r"\.part0*[0-9]+\.rar$", filename)
                    or re_search(r"\.rar\.[0-9]+$", filename)
                    or re_search(r"\.r[0-9]+$", filename)
                ):
                    archive_format = "RAR"
                elif (
                    re_search(r"\.part0*[0-9]+\.zip$", filename)
                    or re_search(r"\.zip\.[0-9]+$", filename)
                    or re_search(r"\.z[0-9]+$", filename)
                ):
                    archive_format = "ZIP"
                elif re_search(r"\.part0*[0-9]+\.7z$", filename):
                    archive_format = "7Z"
                else:
                    # For numeric extensions or unknown patterns, use file command
                    archive_format = "Split Archive"
            else:
                # For other extensions, use the extension as the format
                archive_format = file_ext[1:].upper() if file_ext else "Unknown"

            # Always verify the format using file command for more accurate detection
            try:
                abs_path = ospath.abspath(des_path)

                # First try file command
                cmd = ["file", "-b", abs_path]
                stdout, stderr, return_code = await cmd_exec(cmd)
                if return_code == 0 and stdout:
                    stdout_lower = stdout.lower()

                    # Update format based on file command output
                    if "rar archive" in stdout_lower:
                        archive_format = "RAR"
                    elif "zip archive" in stdout_lower:
                        archive_format = "ZIP"
                    elif "7-zip archive" in stdout_lower:
                        archive_format = "7Z"
                    elif "tar archive" in stdout_lower:
                        archive_format = "TAR"
                    elif "gzip compressed" in stdout_lower:
                        archive_format = "GZ"
                    elif "bzip2 compressed" in stdout_lower:
                        archive_format = "BZ2"
                    elif "xz compressed" in stdout_lower:
                        archive_format = "XZ"
                    elif "iso 9660" in stdout_lower:
                        archive_format = "ISO"
                    elif "microsoft cabinet" in stdout_lower:
                        archive_format = "CAB"

                # If file command didn't give a clear result, try 7z
                if archive_format in {"Split Archive", "Unknown"}:
                    cmd = ["7z", "l", abs_path]
                    stdout, stderr, return_code = await cmd_exec(cmd)
                    if return_code == 0 and stdout:
                        if "Type = Rar" in stdout:
                            archive_format = "RAR"
                        elif "Type = Zip" in stdout:
                            archive_format = "ZIP"
                        elif "Type = 7z" in stdout:
                            archive_format = "7Z"
                        elif "Type = gzip" in stdout:
                            archive_format = "GZ"
                        elif "Type = bzip2" in stdout:
                            archive_format = "BZ2"
                        elif "Type = xz" in stdout:
                            archive_format = "XZ"
                        elif "Type = Tar" in stdout:
                            archive_format = "TAR"
                        elif "Type = Iso" in stdout:
                            archive_format = "ISO"
                        elif "Type = Cab" in stdout:
                            archive_format = "CAB"
            except Exception:
                # Keep the format determined from the extension if verification fails
                pass

            tc += f"{'Format':<28}: {archive_format} Archive\n"

            # Map archive formats to more descriptive names
            archive_format_info = {
                "ZIP": "ZIP Archive Format",
                "RAR": "Roshal Archive",
                "7Z": "7-Zip Archive Format",
                "TAR": "Tape Archive",
                "GZ": "Gzip Compressed Archive",
                "BZ2": "Bzip2 Compressed Archive",
                "XZ": "XZ Compressed Archive",
                "ISO": "ISO 9660 Disk Image",
                "CAB": "Microsoft Cabinet Archive",
                "ARJ": "ARJ Compressed Archive",
                "LZH": "LZH Compressed Archive",
                "UDF": "Universal Disk Format Image",
                "WIM": "Windows Imaging Format",
            }

            format_info = archive_format_info.get(
                archive_format, f"{archive_format} Archive Format"
            )
            tc += f"{'Format/Info':<28}: {format_info}\n"
            tc += f"{'File size':<28}: {file_size / (1024 * 1024):.2f} MiB\n"

            # Try to get more info about the archive using file command
            try:
                # Use absolute path to avoid "No such file or directory" errors
                abs_path = ospath.abspath(des_path)
                # Verify file exists before running file command
                if not ospath.exists(abs_path):
                    pass
                else:
                    cmd = ["file", "-b", abs_path]
                    stdout, stderr, return_code = await cmd_exec(cmd)
                    if return_code == 0 and stdout:
                        tc += f"{'File analysis':<28}: {stdout.strip()}\n"
                    else:
                        pass
            except Exception:
                # Continue without this info, it's not critical
                pass

            # Try to get compression ratio if possible
            try:
                # Use absolute path for all archive commands
                abs_path = ospath.abspath(des_path)

                if file_ext in [".zip", ".rar", ".7z"] or is_split_archive:
                    if file_ext == ".zip" or (
                        is_split_archive and archive_format == "ZIP"
                    ):
                        cmd = ["unzip", "-l", abs_path]
                    elif file_ext == ".rar" or (
                        is_split_archive and archive_format == "RAR"
                    ):
                        # Try 7z first as it's more reliable for partial archives
                        cmd = ["7z", "l", abs_path]
                        stdout, stderr, return_code = await cmd_exec(cmd)
                        if return_code != 0:
                            # If 7z fails, try unrar
                            cmd = ["unrar", "l", abs_path]
                    elif file_ext == ".7z" or (
                        is_split_archive and archive_format == "7Z"
                    ):
                        cmd = ["7z", "l", abs_path]

                    stdout, stderr, return_code = await cmd_exec(cmd)
                    if return_code == 0 and stdout:
                        # Try to extract uncompressed size
                        uncompressed_size = 0
                        if file_ext == ".zip":
                            # For zip, look for the total line
                            for line in stdout.strip().split("\n"):
                                if "Total" in line and "files" in line:
                                    size_match = re_search(r"(\d+)\s+bytes", line)
                                    if size_match:
                                        uncompressed_size = int(size_match.group(1))
                        elif file_ext == ".rar":
                            # For rar, sum up the sizes
                            for line in stdout.strip().split("\n"):
                                size_match = re_search(
                                    r"\s+(\d+)\s+\d+\s+\d+%", line
                                )
                                if size_match:
                                    uncompressed_size += int(size_match.group(1))
                        elif file_ext == ".7z":
                            # For 7z, look for the size line
                            for line in stdout.strip().split("\n"):
                                if "Size:" in line:
                                    size_match = re_search(r"Size:\s+(\d+)", line)
                                    if size_match:
                                        uncompressed_size = int(size_match.group(1))

                        if uncompressed_size > 0 and file_size > 0:
                            # Calculate compression ratio
                            ratio = uncompressed_size / file_size
                            tc += f"{'Compression ratio':<28}: {ratio:.2f}:1\n"

                            # Format uncompressed size
                            if uncompressed_size > 1024 * 1024 * 1024:
                                tc += f"{'Uncompressed size':<28}: {uncompressed_size / (1024 * 1024 * 1024):.2f} GiB\n"
                            else:
                                tc += f"{'Uncompressed size':<28}: {uncompressed_size / (1024 * 1024):.2f} MiB\n"
            except Exception as e:
                LOGGER.warning(f"Could not get compression info: {e}")

            tc += "</pre><br>"

            # Try to list archive contents if possible
            try:
                # Use absolute path for all archive commands
                abs_path = ospath.abspath(des_path)

                # First try 7z for all archive types as it's the most versatile
                cmd = ["7z", "l", abs_path]
                stdout, stderr, return_code = await cmd_exec(cmd)

                # If 7z fails, try format-specific tools
                if return_code != 0:
                    if file_ext == ".zip":
                        cmd = ["unzip", "-l", abs_path]
                    elif file_ext == ".rar":
                        cmd = ["unrar", "l", abs_path]
                    elif file_ext in [".tar", ".gz", ".bz2", ".xz"]:
                        cmd = ["tar", "tf", abs_path]
                    elif file_ext == ".iso":
                        cmd = ["isoinfo", "-l", "-i", abs_path]
                    elif file_ext == ".cab":
                        cmd = ["cabextract", "-l", abs_path]
                    else:
                        # If we don't have a specific tool, try file command as a last resort
                        cmd = ["file", "-z", abs_path]

                    stdout, stderr, return_code = await cmd_exec(cmd)

                if return_code == 0 and stdout:
                    # Limit output to avoid very large content
                    content_lines = stdout.strip().split("\n")

                    # Determine the format of the output based on the command used
                    is_7z_output = "7-Zip" in stdout or "Type = " in stdout
                    is_unzip_output = "Archive:" in stdout and "Length" in stdout
                    is_unrar_output = "UNRAR " in stdout or "RAR " in stdout

                    # Filter out header and footer lines for cleaner output
                    filtered_lines = []
                    total_files = 0
                    total_size_uncompressed = 0

                    # Process based on the output format
                    if is_7z_output:
                        # 7z output processing
                        in_file_list = False
                        for line in content_lines:
                            line = line.strip()

                            # Skip empty lines and headers
                            if (
                                not line
                                or "Scanning" in line
                                or "Listing" in line
                                or "--" in line
                            ):
                                continue

                            # Detect when we're in the file list section
                            if (
                                "Date" in line
                                and "Time" in line
                                and "Attr" in line
                                and "Size" in line
                                and "Name" in line
                            ):
                                in_file_list = True
                                continue

                            # Skip the separator line after the header
                            if in_file_list and "----" in line:
                                continue

                            # End of file list
                            if in_file_list and (
                                "files" in line and "folders" in line
                            ):
                                # Extract total files count
                                files_match = re_search(r"(\d+)\s+files", line)
                                if files_match:
                                    total_files = int(files_match.group(1))
                                continue

                            # Extract uncompressed size from summary
                            if "Size:" in line:
                                size_match = re_search(r"Size:\s+(\d+)", line)
                                if size_match:
                                    total_size_uncompressed = int(
                                        size_match.group(1)
                                    )
                                continue

                            # Process file entries
                            if in_file_list and not line.startswith("----"):
                                filtered_lines.append(line)
                    elif is_unzip_output:
                        # unzip output processing
                        for line in content_lines:
                            line = line.strip()

                            # Skip headers and footers
                            if (
                                not line
                                or "Archive:" in line
                                or "Length" in line
                                or "------" in line
                            ):
                                continue

                            # Extract total from the summary line
                            if "files" in line and "bytes" in line:
                                files_match = re_search(r"(\d+)\s+files", line)
                                if files_match:
                                    total_files = int(files_match.group(1))

                                size_match = re_search(r"(\d+)\s+bytes", line)
                                if size_match:
                                    total_size_uncompressed = int(
                                        size_match.group(1)
                                    )
                                continue

                            filtered_lines.append(line)
                    elif is_unrar_output:
                        # unrar output processing
                        for line in content_lines:
                            line = line.strip()

                            # Skip headers and footers
                            if (
                                not line
                                or "UNRAR " in line
                                or "RAR " in line
                                or "------" in line
                            ):
                                continue

                            # Skip summary lines
                            if line.startswith(("Archive ", "*")) or line.endswith(
                                "files"
                            ):
                                continue

                            filtered_lines.append(line)
                    else:
                        # Generic processing for other formats (tar, etc.)
                        for line in content_lines:
                            line = line.strip()
                            if line:
                                filtered_lines.append(line)
                                total_files += 1

                    # Count total files if not already counted
                    if total_files == 0:
                        total_files = len(filtered_lines)

                    # Limit to 20 files for display
                    if len(filtered_lines) > 20:
                        content_sample = (
                            "\n".join(filtered_lines[:20])
                            + f"\n... and {len(filtered_lines) - 20} more files"
                        )
                    else:
                        content_sample = "\n".join(filtered_lines)

                    # Add archive contents section
                    if content_sample.strip():
                        tc += "<blockquote>Archive Contents</blockquote><pre>"
                        tc += content_sample
                        tc += "</pre><br>"

                        # Add summary information
                        tc += "<blockquote>Archive Summary</blockquote><pre>"
                        tc += f"{'Total files':<28}: {total_files}\n"

                        # Add total uncompressed size if available
                        if total_size_uncompressed > 0:
                            if total_size_uncompressed > 1024 * 1024 * 1024:
                                tc += f"{'Total uncompressed size':<28}: {total_size_uncompressed / (1024 * 1024 * 1024):.2f} GiB\n"
                            else:
                                tc += f"{'Total uncompressed size':<28}: {total_size_uncompressed / (1024 * 1024):.2f} MiB\n"

                        # Calculate compression ratio if both sizes are available
                        if total_size_uncompressed > 0 and file_size > 0:
                            ratio = total_size_uncompressed / file_size
                            tc += f"{'Compression ratio':<28}: {ratio:.2f}:1\n"

                        tc += "</pre><br>"

                        # Count files by type
                        file_types = {}
                        for line in filtered_lines:
                            # Extract filename from the line - handle different output formats
                            if is_7z_output:
                                # 7z format: Date Time Attr Size Compressed Name
                                parts = line.split()
                                if len(parts) >= 6:
                                    filename = parts[-1]  # Last part is the filename
                            else:
                                # Try to extract filename from the end of the line
                                filename_match = re_search(
                                    r"([^\/\s]+\.[a-zA-Z0-9]+)$", line
                                )
                                if filename_match:
                                    filename = filename_match.group(1)
                                else:
                                    # If no match, use the whole line as a fallback
                                    filename = (
                                        line.split()[-1] if line.split() else ""
                                    )

                            # Extract extension and count
                            if filename:
                                ext = ospath.splitext(filename)[1].lower()
                                if ext:
                                    if ext not in file_types:
                                        file_types[ext] = 0
                                    file_types[ext] += 1

                        # Display file types summary
                        if file_types:
                            tc += "<blockquote>File Types</blockquote><pre>"
                            for ext, count in sorted(
                                file_types.items(), key=lambda x: x[1], reverse=True
                            ):
                                tc += f"{ext[1:].upper():<10}: {count} files\n"
                            tc += "</pre><br>"
            except Exception as e:
                LOGGER.warning(f"Could not list archive contents: {e}")
                # Add a note about the error
                tc += "<blockquote>Archive Analysis</blockquote><pre>"
                tc += "Could not analyze archive contents completely.\n"
                tc += f"Error: {e!s}\n"
                tc += "</pre><br>"

            # If in silent mode, create Telegraph page and return link ID
            if silent:
                return await create_telegraph_page_from_content(tc, silent=True)
            return tc

        # Handle image files
        if file_ext in image_exts:
            # Special handling for image files
            if not silent and temp_send:
                await edit_message(temp_send, "Analyzing image file...")

            # Create basic info for image files
            tc = f"<h4>{ospath.basename(des_path)}</h4><br><br><blockquote>General</blockquote><pre>"
            tc += f"{'Complete name':<28}: {ospath.basename(des_path)}\n"

            # Map image formats to more descriptive names
            image_format_info = {
                "JPG": "JPEG Image",
                "JPEG": "JPEG Image",
                "PNG": "Portable Network Graphics",
                "GIF": "Graphics Interchange Format",
                "BMP": "Bitmap Image",
                "WEBP": "WebP Image",
                "TIFF": "Tagged Image File Format",
                "SVG": "Scalable Vector Graphics",
                "EPS": "Encapsulated PostScript",
                "PSD": "Adobe Photoshop Document",
            }

            format_info = image_format_info.get(
                file_ext[1:].upper(), f"{file_ext[1:].upper()} Image"
            )
            tc += f"{'Format':<28}: {file_ext[1:].upper()}\n"
            tc += f"{'Format/Info':<28}: {format_info}\n"
            tc += f"{'File size':<28}: {file_size / (1024 * 1024):.2f} MiB\n"

            # Try to get image dimensions and other info using ffprobe
            try:
                cmd = [
                    "ffprobe",  # Keep as ffprobe, not xtra
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    des_path,
                ]

                # Use cmd_exec instead of direct subprocess call
                stdout, stderr, return_code = await cmd_exec(cmd)

                if return_code == 0:
                    try:
                        json_data = json.loads(stdout)

                        if "streams" in json_data and len(json_data["streams"]) > 0:
                            stream = json_data["streams"][0]

                            if "width" in stream and "height" in stream:
                                width = stream["width"]
                                height = stream["height"]
                                tc += f"{'Width':<28}: {width} pixels\n"
                                tc += f"{'Height':<28}: {height} pixels\n"
                                tc += f"{'Resolution':<28}: {width}x{height}\n"

                            if "bits_per_raw_sample" in stream:
                                tc += f"{'Bit depth':<28}: {stream['bits_per_raw_sample']} bits\n"

                            if "pix_fmt" in stream:
                                pix_fmt = stream["pix_fmt"]
                                tc += f"{'Pixel format':<28}: {pix_fmt}\n"

                                # Try to determine color space
                                if "rgb" in pix_fmt:
                                    tc += f"{'Color space':<28}: RGB\n"
                                elif "yuv" in pix_fmt:
                                    tc += f"{'Color space':<28}: YUV\n"
                                elif "gray" in pix_fmt:
                                    tc += f"{'Color space':<28}: Grayscale\n"

                                # Try to determine bit depth from pixel format
                                if "p16" in pix_fmt:
                                    tc += f"{'Bit depth':<28}: 16 bits\n"
                                elif "p10" in pix_fmt:
                                    tc += f"{'Bit depth':<28}: 10 bits\n"
                                elif "p8" in pix_fmt or not any(
                                    x in pix_fmt for x in ["p16", "p10", "p12"]
                                ):
                                    tc += f"{'Bit depth':<28}: 8 bits\n"
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                LOGGER.warning(f"Could not get image info: {e}")

            # Try to get more info using file command
            try:
                abs_path = ospath.abspath(des_path)
                # Verify file exists before running file command
                if not ospath.exists(abs_path):
                    pass
                else:
                    cmd = ["file", "-b", abs_path]
                    stdout, stderr, return_code = await cmd_exec(cmd)
                    if return_code == 0 and stdout:
                        tc += f"{'File analysis':<28}: {stdout.strip()}\n"
                    else:
                        pass
            except Exception:
                # Continue without this info, it's not critical
                pass

            tc += "</pre><br>"
            # Continue to Telegraph page creation instead of returning raw content

        # Handle document files
        if file_ext in document_exts:
            # Special handling for document files
            if not silent and temp_send:
                await edit_message(temp_send, "Analyzing document file...")

            # Create basic info for document files
            tc = f"<h4>{ospath.basename(des_path)}</h4><br><br><blockquote>General</blockquote><pre>"
            tc += f"{'Complete name':<28}: {ospath.basename(des_path)}\n"

            # Map document formats to more descriptive names
            document_format_info = {
                "PDF": "Portable Document Format",
                "DOC": "Microsoft Word Document (Legacy)",
                "DOCX": "Microsoft Word Document",
                "XLS": "Microsoft Excel Spreadsheet (Legacy)",
                "XLSX": "Microsoft Excel Spreadsheet",
                "PPT": "Microsoft PowerPoint Presentation (Legacy)",
                "PPTX": "Microsoft PowerPoint Presentation",
                "TXT": "Plain Text Document",
                "MD": "Markdown Document",
                "EPUB": "Electronic Publication",
            }

            format_info = document_format_info.get(
                file_ext[1:].upper(), f"{file_ext[1:].upper()} Document"
            )
            tc += f"{'Format':<28}: {file_ext[1:].upper()}\n"
            tc += f"{'Format/Info':<28}: {format_info}\n"
            tc += f"{'File size':<28}: {file_size / (1024 * 1024):.2f} MiB\n"

            # Try to get more info using file command
            try:
                abs_path = ospath.abspath(des_path)
                # Verify file exists before running file command
                if not ospath.exists(abs_path):
                    pass
                else:
                    cmd = ["file", "-b", abs_path]
                    stdout, stderr, return_code = await cmd_exec(cmd)
                    if return_code == 0 and stdout:
                        tc += f"{'File analysis':<28}: {stdout.strip()}\n"
                    else:
                        pass
            except Exception:
                # Continue without this info, it's not critical
                pass

            # For PDF files, try to get page count
            if file_ext.lower() == ".pdf":
                try:
                    cmd = ["pdfinfo", des_path]
                    stdout, stderr, return_code = await cmd_exec(cmd)
                    if return_code == 0 and stdout:
                        # Extract page count
                        for line in stdout.strip().split("\n"):
                            if line.startswith("Pages:"):
                                page_count = line.split(":", 1)[1].strip()
                                tc += f"{'Page count':<28}: {page_count}\n"
                                break
                except Exception as e:
                    LOGGER.warning(f"Could not get PDF info: {e}")

            tc += "</pre><br>"
            # If in silent mode, create Telegraph page and return link ID
            if silent:
                return await create_telegraph_page_from_content(tc, silent=True)
            return tc

        # Handle document files
        if file_ext in document_exts:
            # Special handling for subtitle files
            if not silent and temp_send:
                await edit_message(temp_send, "Analyzing subtitle file...")

            # Try to determine subtitle format from extension
            subtitle_format = file_ext[
                1:
            ].upper()  # Remove the dot and convert to uppercase

            # Map subtitle formats to more descriptive names
            subtitle_format_info = {
                "SRT": "SubRip Text",
                "ASS": "Advanced SubStation Alpha",
                "SSA": "SubStation Alpha",
                "VTT": "WebVTT (Web Video Text Tracks)",
                "WEBVTT": "WebVTT (Web Video Text Tracks)",
                "SUB": "MicroDVD or SubViewer",
                "IDX": "VobSub",
                "STL": "EBU STL (European Broadcasting Union Subtitle)",
                "SCC": "Scenarist Closed Caption",
                "TTML": "Timed Text Markup Language",
                "SBV": "YouTube Subtitles",
                "DFXP": "Distribution Format Exchange Profile",
                "SMI": "SAMI (Synchronized Accessible Media Interchange)",
            }

            format_info = subtitle_format_info.get(
                subtitle_format, f"{subtitle_format} subtitle"
            )

            # Try to get more info using file command
            try:
                abs_path = ospath.abspath(des_path)
                # Verify file exists before running file command
                if not ospath.exists(abs_path):
                    pass
                else:
                    cmd = ["file", "-b", abs_path]
                    stdout, stderr, return_code = await cmd_exec(cmd)
                    if return_code == 0 and stdout:
                        file_analysis = stdout.strip()
                        # If file command gives more specific info, use it to refine format info
                        if "SubRip" in file_analysis and subtitle_format == "SRT":
                            format_info = "SubRip Text (SRT)"
                        elif (
                            "Advanced SubStation Alpha" in file_analysis
                            and subtitle_format in ["ASS", "SSA"]
                        ):
                            format_info = "Advanced SubStation Alpha (ASS)"
                        elif "WebVTT" in file_analysis and subtitle_format in [
                            "VTT",
                            "WEBVTT",
                        ]:
                            format_info = "WebVTT (Web Video Text Tracks)"
                    else:
                        pass
            except Exception:
                # Continue without this info, it's not critical
                pass

            # Read a small sample of the file to try to determine encoding and format
            encoding = "utf-8"
            file_sample = ""
            try:
                # Use async file operations for better resource management
                async with aiopen(des_path, "rb") as f:
                    raw_data = await f.read(4096)  # Read first 4KB

                    # Try to detect encoding
                    if raw_data.startswith(b"\xef\xbb\xbf"):
                        encoding = "utf-8-sig"  # UTF-8 with BOM
                    elif raw_data.startswith(b"\xff\xfe"):
                        encoding = "utf-16-le"  # UTF-16 Little Endian
                    elif raw_data.startswith(b"\xfe\xff"):
                        encoding = "utf-16-be"  # UTF-16 Big Endian

                    # Try to decode with detected encoding
                    try:
                        file_sample = raw_data.decode(encoding, errors="replace")
                    except UnicodeDecodeError:
                        # If that fails, try with latin-1 which should always work
                        file_sample = raw_data.decode("latin-1", errors="replace")
            except Exception as e:
                LOGGER.warning(f"Could not read subtitle file: {e}")

            # Run garbage collection after file processing
            smart_garbage_collection(aggressive=False)

            # Create basic info
            tc = f"<h4>{ospath.basename(des_path)}</h4><br><br><blockquote>General</blockquote><pre>"
            tc += f"{'Complete name':<28}: {ospath.basename(des_path)}\n"
            tc += f"{'Format':<28}: {subtitle_format}\n"
            tc += f"{'Format/Info':<28}: {format_info}\n"
            tc += f"{'File size':<28}: {file_size / (1024 * 1024):.2f} MiB\n"

            # Try to determine encoding from file sample
            if encoding != "utf-8":
                tc += f"{'Encoding':<28}: {encoding}\n"

            tc += "</pre><br>"

            tc += "<blockquote>Subtitle</blockquote><pre>"
            tc += f"{'Format':<28}: {subtitle_format}\n"
            tc += f"{'Subtitle format':<28}: {subtitle_format.lower()}\n"

            # Try to estimate the language from filename
            lang_codes = {
                "eng": "English",
                "en": "English",
                "fre": "French",
                "fr": "French",
                "ger": "German",
                "de": "German",
                "spa": "Spanish",
                "es": "Spanish",
                "ita": "Italian",
                "it": "Italian",
                "rus": "Russian",
                "ru": "Russian",
                "jpn": "Japanese",
                "ja": "Japanese",
                "chi": "Chinese",
                "zh": "Chinese",
                "ara": "Arabic",
                "ar": "Arabic",
                "hin": "Hindi",
                "hi": "Hindi",
                "kor": "Korean",
                "ko": "Korean",
                "por": "Portuguese",
                "pt": "Portuguese",
                "dut": "Dutch",
                "nl": "Dutch",
                "swe": "Swedish",
                "sv": "Swedish",
                "nor": "Norwegian",
                "no": "Norwegian",
                "dan": "Danish",
                "da": "Danish",
                "fin": "Finnish",
                "fi": "Finnish",
                "pol": "Polish",
                "pl": "Polish",
                "tur": "Turkish",
                "tr": "Turkish",
                "heb": "Hebrew",
                "he": "Hebrew",
                "tha": "Thai",
                "th": "Thai",
            }

            filename_lower = ospath.basename(des_path).lower()
            detected_lang = None

            for code, language in lang_codes.items():
                if (
                    f".{code}." in filename_lower
                    or f"_{code}." in filename_lower
                    or f"-{code}." in filename_lower
                    or f".{code}_" in filename_lower
                    or f"_{code}_" in filename_lower
                    or f"-{code}-" in filename_lower
                    or f" {language.lower()}." in filename_lower
                    or f".{language.lower()}." in filename_lower
                ):
                    detected_lang = language
                    break

            if detected_lang:
                tc += f"{'Language':<28}: {detected_lang}\n"

            # Add a sample of the file content if available
            if file_sample:
                # Clean up the sample and limit to a few lines
                sample_lines = file_sample.split("\n")[:5]
                sample_text = "\n".join(sample_lines)
                if len(sample_text) > 200:
                    sample_text = sample_text[:197] + "..."

                tc += f"\n{'Content sample':<28}:\n{sample_text}\n"

            tc += "</pre><br>"
            # If in silent mode, create Telegraph page and return link ID
            if silent:
                return await create_telegraph_page_from_content(tc, silent=True)
            return tc

        # For non-subtitle files or subtitle files that ffprobe can handle
        # Run ffprobe with more detailed options
        cmd = [
            "ffprobe",  # Keep as ffprobe, not xtra
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "-show_programs",
            "-show_entries",
            "format_tags:stream_tags:stream_disposition",
            des_path,
        ]

        # Add timeout to prevent ffprobe from hanging on problematic files
        try:
            import asyncio

            stdout, stderr, return_code = await asyncio.wait_for(
                cmd_exec(cmd),
                timeout=60.0,  # 60 second timeout
            )
        except TimeoutError:
            LOGGER.warning(
                f"ffprobe timed out for {des_path}, trying mediainfo fallback"
            )
            return_code = 1  # Set to failure to trigger fallback
            stderr = "ffprobe timed out after 60 seconds"
            stdout = ""

        if return_code != 0:
            LOGGER.warning(
                f"ffprobe failed with return code {return_code}: {stderr}"
            )

            # Check if the file exists and is accessible
            if not await aiopath.exists(des_path):
                LOGGER.error(f"File does not exist at path: {des_path}")

                # Try multiple path sanitization approaches
                fixed_paths = []

                # Method 1: Replace spaces with underscores
                if " " in des_path:
                    fixed_paths.append(des_path.replace(" ", "_"))

                # Method 2: Quote the path for shell safety
                import shlex

                quoted_path = shlex.quote(des_path)
                if quoted_path != des_path:
                    fixed_paths.append(quoted_path.strip("'\""))

                # Method 3: Use pathlib for normalization
                from pathlib import Path

                normalized_path = str(Path(des_path).resolve())
                if normalized_path != des_path:
                    fixed_paths.append(normalized_path)

                # Method 4: Handle special characters by escaping
                import re

                escaped_path = re.sub(r"([()[\]{}])", r"\\\1", des_path)
                if escaped_path != des_path:
                    fixed_paths.append(escaped_path)

                # Try each fixed path
                for fixed_path in fixed_paths:
                    LOGGER.info(f"Trying with fixed path: {fixed_path}")
                    if await aiopath.exists(fixed_path):
                        # Use the fixed path instead
                        des_path = fixed_path
                        # Retry the command with the fixed path
                        cmd[-1] = des_path  # Update the path in the command
                        stdout, stderr, return_code = await cmd_exec(cmd)
                        if return_code == 0:
                            # If successful, continue with processing
                            if stdout:
                                try:
                                    data = json.loads(stdout)
                                    return parse_ffprobe_info(
                                        data, file_size, ospath.basename(des_path)
                                    )
                                except json.JSONDecodeError as e:
                                    LOGGER.error(f"JSON decode error: {e}")
                                    # Continue to fallback methods
                            # If we get here, the retry didn't work completely
                        break  # Stop trying other paths if this one exists

                # If we couldn't fix it or none of the fixed paths exist
                raise Exception(f"File not found: {des_path}")

            # Check if the file has zero size
            try:
                file_size_check = await aiopath.getsize(des_path)
                if file_size_check == 0:
                    LOGGER.error(f"File exists but has zero size: {des_path}")
                    raise Exception(f"File has zero size: {des_path}")
            except Exception as e:
                LOGGER.error(f"Error checking file size: {e}")
                raise Exception(f"File access error: {e}")

            # ffprobe failed but file exists - this is likely a non-media file
            # Try to provide basic information using file command
            LOGGER.info(
                f"ffprobe failed for {des_path}, attempting fallback analysis"
            )

            # Try mediainfo binary as fallback before giving up
            LOGGER.info(f"Attempting mediainfo binary fallback for {des_path}")
            try:
                # Update status message if not in silent mode
                if not silent and temp_send:
                    await edit_message(
                        temp_send, "ffprobe failed, trying mediainfo binary..."
                    )

                # Try mediainfo binary with timeout
                mediainfo_cmd = ["mediainfo", des_path]
                try:
                    (
                        mediainfo_stdout,
                        mediainfo_stderr,
                        mediainfo_return_code,
                    ) = await asyncio.wait_for(
                        cmd_exec(mediainfo_cmd),
                        timeout=30.0,  # 30 second timeout for mediainfo
                    )
                except TimeoutError:
                    LOGGER.warning(f"mediainfo binary timed out for {des_path}")
                    mediainfo_return_code = 1
                    mediainfo_stderr = "mediainfo timed out after 30 seconds"
                    mediainfo_stdout = ""

                if mediainfo_return_code == 0 and mediainfo_stdout:
                    LOGGER.info(f"mediainfo binary succeeded for {des_path}")
                    # Parse mediainfo output
                    tc = await parse_mediainfo_output(
                        mediainfo_stdout, file_size, ospath.basename(des_path)
                    )

                    # Add note about using mediainfo fallback
                    tc += "<blockquote>Analysis Info</blockquote><pre>"
                    tc += f"{'Analysis method':<28}: MediaInfo binary (ffprobe fallback)\n"
                    # Clean up error message for display
                    error_msg = (
                        stderr.strip()
                        if stderr and stderr.strip()
                        else "ffprobe failed to analyze this file"
                    )
                    tc += f"{'ffprobe status':<28}: {error_msg}\n"
                    tc += "</pre><br>"

                    # If in silent mode, create Telegraph page and return link ID
                    if silent:
                        return await create_telegraph_page_from_content(
                            tc, silent=True
                        )

                    # Update status message if not in silent mode
                    if not silent and temp_send:
                        await edit_message(
                            temp_send,
                            "MediaInfo generated successfully using mediainfo binary!",
                        )

                    return tc

                LOGGER.warning(
                    f"mediainfo binary also failed for {des_path}: {mediainfo_stderr}"
                )

            except Exception as mediainfo_error:
                LOGGER.warning(
                    f"mediainfo binary fallback failed: {mediainfo_error}"
                )
                # Continue to other fallback methods

            # If it's a subtitle file and both ffprobe and mediainfo failed, try a more basic approach
            if file_ext in subtitle_exts:
                # Create basic info for subtitle files
                tc = f"<h4>{ospath.basename(des_path)}</h4><br><br><blockquote>General</blockquote><pre>"
                tc += f"{'Complete name':<28}: {ospath.basename(des_path)}\n"
                tc += f"{'Format':<28}: {subtitle_format} subtitle\n"
                tc += f"{'File size':<28}: {file_size / (1024 * 1024):.2f} MiB\n"
                tc += "</pre><br>"

                tc += "<blockquote>Subtitle</blockquote><pre>"
                tc += f"{'Format':<28}: {subtitle_format}\n"
                tc += f"{'Subtitle format':<28}: {subtitle_format.lower()}\n"
                tc += "</pre><br>"

                # Add note about analysis methods tried
                tc += "<blockquote>Analysis Info</blockquote><pre>"
                tc += f"{'Analysis method':<28}: Basic file analysis (ffprobe and mediainfo failed)\n"
                tc += "</pre><br>"

                # If in silent mode, create Telegraph page and return link ID
                if silent:
                    return await create_telegraph_page_from_content(tc, silent=True)
                return tc

            # For media files, try a fallback approach using file command
            try:
                # Use file command to get basic info about the file
                abs_path = ospath.abspath(des_path)
                cmd = ["file", "-b", abs_path]
                stdout, stderr, return_code = await cmd_exec(cmd)

                if return_code == 0 and stdout:
                    # Create basic info for the file based on file command output
                    tc = f"<h4>{ospath.basename(des_path)}</h4><br><br><blockquote>General</blockquote><pre>"
                    tc += f"{'Complete name':<28}: {ospath.basename(des_path)}\n"

                    # Try to determine file type from file command output
                    file_type = "Unknown"
                    if "video" in stdout.lower():
                        file_type = "Video"
                    elif "audio" in stdout.lower():
                        file_type = "Audio"
                    elif "image" in stdout.lower():
                        file_type = "Image"
                    elif "text" in stdout.lower():
                        file_type = "Text"

                    tc += f"{'Format':<28}: {file_type} file\n"
                    tc += f"{'File analysis':<28}: {stdout.strip()}\n"
                    tc += f"{'File size':<28}: {file_size / (1024 * 1024):.2f} MiB\n"

                    # Add note about analysis methods tried
                    tc += f"{'Note':<28}: ffprobe and mediainfo analysis failed. Limited information available.\n"
                    tc += "</pre><br>"

                    # Add a section with the error for debugging
                    tc += "<blockquote>Analysis Info</blockquote><pre>"
                    tc += f"{'Analysis method':<28}: Basic file analysis (ffprobe and mediainfo failed)\n"
                    tc += f"{'ffprobe error':<28}: {stderr if stderr else 'No error message provided'}\n"
                    tc += "</pre><br>"

                    # If in silent mode, create Telegraph page and return link ID
                    if silent:
                        return await create_telegraph_page_from_content(
                            tc, silent=True
                        )
                    return tc
            except Exception as e:
                LOGGER.warning(f"Fallback file analysis failed: {e}")

                # Check if this is a "No such file or directory" error
                if "No such file or directory" in str(e):
                    # This is likely a file path issue
                    # Try multiple path sanitization approaches
                    fixed_paths = []

                    # Method 1: Replace spaces with underscores
                    if " " in des_path:
                        fixed_paths.append(des_path.replace(" ", "_"))

                    # Method 2: Quote the path for shell safety
                    import shlex

                    quoted_path = shlex.quote(des_path)
                    if quoted_path != des_path:
                        fixed_paths.append(quoted_path.strip("'\""))

                    # Method 3: Use pathlib for normalization
                    from pathlib import Path

                    normalized_path = str(Path(des_path).resolve())
                    if normalized_path != des_path:
                        fixed_paths.append(normalized_path)

                    # Try each fixed path
                    for fixed_path in fixed_paths:
                        LOGGER.info(f"Trying with fixed path: {fixed_path}")
                        if await aiopath.exists(fixed_path):
                            # Use the fixed path instead
                            des_path = fixed_path
                            # Retry the command with the fixed path
                            cmd = ["file", "-b", ospath.abspath(fixed_path)]
                            stdout, stderr, return_code = await cmd_exec(cmd)
                            if return_code == 0 and stdout:
                                # Create basic info for the file based on file command output
                                tc = f"<h4>{ospath.basename(des_path)}</h4><br><br><blockquote>General</blockquote><pre>"
                                tc += f"{'Complete name':<28}: {ospath.basename(des_path)}\n"
                                # Try to determine file type from file command output
                                file_type = "Unknown"
                                if "video" in stdout.lower():
                                    file_type = "Video"
                                elif "audio" in stdout.lower():
                                    file_type = "Audio"
                                elif "image" in stdout.lower():
                                    file_type = "Image"
                                elif "text" in stdout.lower():
                                    file_type = "Text"
                                tc += f"{'Format':<28}: {file_type} file\n"
                                tc += f"{'File analysis':<28}: {stdout.strip()}\n"
                                tc += f"{'File size':<28}: {file_size / (1024 * 1024):.2f} MiB\n"
                                tc += f"{'Note':<28}: ffprobe analysis failed. Limited information available.\n"
                                tc += "</pre><br>"
                                # If in silent mode, create Telegraph page and return link ID
                                if silent:
                                    return await create_telegraph_page_from_content(
                                        tc, silent=True
                                    )
                                return tc

                    # If we couldn't fix it or the fixed path doesn't exist
                    raise Exception(
                        f"File not found or inaccessible: {des_path}. If this is a Google Drive index link, try downloading the file first."
                    )
                # For other errors, provide more context
                raise Exception(
                    f"Media analysis failed: {e}. Try downloading the file first and then generating MediaInfo."
                )

            # If all fallbacks fail, raise the original exception with more context
            raise Exception(
                f"ffprobe failed with return code {return_code}: {stderr}. The file may be corrupted or in an unsupported format."
            )

        if stdout:
            try:
                data = json.loads(stdout)
                tc = parse_ffprobe_info(data, file_size, ospath.basename(des_path))

                # Add note about successful ffprobe analysis
                tc += "<blockquote>Analysis Info</blockquote><pre>"
                tc += f"{'Analysis method':<28}: ffprobe (primary method)\n"
                tc += "</pre><br>"

            except json.JSONDecodeError as e:
                LOGGER.error(f"JSON decode error: {e}")
                raise Exception("Failed to parse ffprobe output") from e
        else:
            raise Exception("ffprobe returned empty output")

    except Exception as e:
        error_message = str(e)
        LOGGER.error(f"MediaInfo error: {error_message}")

        # Clean up any temporary files on error
        if des_path and isinstance(des_path, str) and ("Mediainfo" in des_path):
            try:
                if await aiopath.exists(des_path):
                    await aioremove(des_path)
                    LOGGER.info(f"Cleaned up temporary file on error: {des_path}")
            except Exception as cleanup_error:
                LOGGER.error(f"Error cleaning up temporary file: {cleanup_error}")

        # Provide more helpful error messages for common issues
        if "findpath" in error_message or "Google Drive index link" in error_message:
            user_message = "❌ MediaInfo failed: Cannot directly process Google Drive index links. Please download the file first and then use the /mediainfo command on the downloaded file."
        elif "❌" in error_message:
            # Error message already formatted with emoji
            user_message = error_message
        elif (
            "No such file or directory" in error_message
            or "File not found" in error_message
        ):
            # Check if the file might exist with a different name format (spaces vs underscores)
            if des_path and " " in des_path:
                fixed_path = des_path.replace(" ", "_")
                if await aiopath.exists(fixed_path):
                    # Try one more time with the fixed path
                    LOGGER.info(
                        f"Found file with fixed path: {fixed_path}, retrying..."
                    )
                    return await gen_mediainfo(
                        message, media_path=fixed_path, silent=silent
                    )

            user_message = "❌ MediaInfo failed: File not found or inaccessible. If using a link, try downloading the file first."
        elif "Failed to download" in error_message:
            user_message = f"❌ MediaInfo failed: {error_message}. The link may be private or require authentication."
        elif "timeout" in error_message.lower():
            user_message = "❌ MediaInfo failed: Operation timed out. Please try again later or use a smaller file."
        elif (
            "permission" in error_message.lower()
            or "access" in error_message.lower()
        ):
            user_message = "❌ MediaInfo failed: Permission denied. The file may be protected or require special access."
        else:
            user_message = f"❌ MediaInfo failed: {error_message}"

        if not silent and temp_send:
            await edit_message(temp_send, user_message)
        return None
    finally:
        # Clean up temporary file ONLY if it's not the original file path
        # This ensures we don't delete files that are still needed for upload
        if (
            des_path
            and isinstance(des_path, str | bytes)
            and await aiopath.exists(des_path)
            and des_path != media_path
        ):
            # Only delete files in the Mediainfo directory (temporary downloads)
            if isinstance(des_path, str) and ("Mediainfo" in des_path):
                await aioremove(des_path)
            else:
                pass
        # Run garbage collection to free up memory
        # Use aggressive mode for large files
        if file_size > 100 * 1024 * 1024:  # 100MB
            smart_garbage_collection(aggressive=True)
        else:
            smart_garbage_collection(aggressive=False)

    if tc:
        # Add a note if this analysis is based on a sample of a large file
        if file_size > 100 * 1024 * 1024:  # 100MB
            # Determine sample size based on file type (same logic as download)
            file_ext = (
                ospath.splitext(ospath.basename(des_path))[1].lower()
                if des_path
                else ""
            )
            video_exts = {
                ".mkv",
                ".mp4",
                ".avi",
                ".mov",
                ".wmv",
                ".flv",
                ".webm",
                ".m4v",
                ".ts",
                ".mts",
            }
            sample_mb = 50 if file_ext in video_exts else 20

            sample_note = (
                "<blockquote>Note</blockquote><pre>"
                f"This analysis is based on a {sample_mb}MB sample of the file ({file_size / (1024 * 1024 * 1024):.1f} GB total). "
                "The format information should be accurate, but some metadata may be incomplete."
                "</pre><br>"
            )
            tc += sample_note

        # Update status message if not in silent mode
        if not silent and temp_send:
            # Determine which analysis method was used based on content
            if "Analysis method" in tc and "mediainfo binary" in tc.lower():
                await edit_message(
                    temp_send,
                    "Generating MediaInfo report (using mediainfo binary fallback)...",
                )
            else:
                await edit_message(
                    temp_send, "Generating MediaInfo report (using ffprobe)..."
                )

        # Create Telegraph page with the results
        try:
            # Update status message if not in silent mode
            if not silent and temp_send:
                await edit_message(temp_send, "Creating Telegraph page...")

            # Create the page
            try:
                link_id = (
                    await telegraph.create_page(title="MediaInfo", content=tc)
                )["path"]

                # Log success
                LOGGER.info("MediaInfo generated successfully")

                # If in silent mode, just return the path
                if silent:
                    return link_id

                # Otherwise, send a message with the link
                tag = message.from_user.mention

                # Final message with link
                await temp_send.edit(
                    f"<blockquote>{tag}, MediaInfo generated <a href='https://graph.org/{link_id}'>here</a>.</blockquote>",
                    disable_web_page_preview=False,
                )
            except Exception as e:
                LOGGER.error(f"Telegraph API error: {e}")

                # Check if the error is related to content size
                if "CONTENT_TOO_BIG" in str(e):
                    # Try to split the content and create a simpler version

                    # Create a simplified version with just the basic info
                    simplified_tc = (
                        tc.split("<blockquote>Archive Contents</blockquote>")[0]
                        + "</pre><br>"
                    )
                    simplified_tc += "<blockquote>Note</blockquote><pre>Full content was too large for Telegraph. This is a simplified version.</pre><br>"

                    try:
                        link_id = (
                            await telegraph.create_page(
                                title="MediaInfo (Simplified)", content=simplified_tc
                            )
                        )["path"]

                        # Log success
                        LOGGER.info("MediaInfo generated successfully (simplified)")

                        # If in silent mode, just return the path
                        if silent:
                            return link_id

                        # Otherwise, send a message with the link
                        tag = message.from_user.mention

                        # Final message with link
                        await temp_send.edit(
                            f"<blockquote>{tag}, MediaInfo generated (simplified due to size limits) <a href='https://graph.org/{link_id}'>here</a>.</blockquote>",
                            disable_web_page_preview=False,
                        )
                    except Exception as e2:
                        LOGGER.error(
                            f"Failed to create simplified Telegraph page: {e2}"
                        )
                        if not silent and temp_send:
                            await edit_message(
                                temp_send,
                                "Failed to create MediaInfo page: Content too large for Telegraph",
                            )
                        return None
                # Handle the specific 'untitled' tag error
                elif "'untitled' tag is not allowed" in str(e):
                    LOGGER.warning(
                        "Encountered 'untitled' tag error, trying fallback approach"
                    )

                    # Create a very basic version with minimal HTML
                    try:
                        # Extract just the basic information
                        basic_info = ""

                        # Try to extract filename from the content
                        filename = "Unknown"
                        if "<h4>" in tc and "</h4>" in tc:
                            filename_match = re_search(r"<h4>(.*?)</h4>", tc)
                            if filename_match:
                                filename = filename_match.group(1)

                        # Check if this is a YouTube video (common source of this error)
                        is_youtube = (
                            "youtube" in filename.lower()
                            or "youtube" in des_path.lower()
                        )

                        # Create a very simple content with minimal HTML
                        basic_info = f"<h4>{filename}</h4><br><br>"
                        basic_info += (
                            "<blockquote>Basic Information</blockquote><pre>"
                        )

                        # Extract file size if available
                        if file_size > 0:
                            size_mb = file_size / (1024 * 1024)
                            basic_info += f"File size: {size_mb:.2f} MiB\n"

                        # Add a note about the error
                        if is_youtube:
                            basic_info += "\nThis is a YouTube video. Full MediaInfo could not be generated due to format limitations.\n"
                        else:
                            basic_info += "\nFull MediaInfo could not be generated due to format limitations.\n"

                        basic_info += "</pre><br>"

                        # Try to create a page with this minimal content
                        link_id = (
                            await telegraph.create_page(
                                title="Basic MediaInfo", content=basic_info
                            )
                        )["path"]

                        # Log success
                        LOGGER.info("MediaInfo generated successfully (basic)")

                        # If in silent mode, just return the path
                        if silent:
                            return link_id

                        # Otherwise, send a message with the link
                        tag = message.from_user.mention

                        # Final message with link
                        await temp_send.edit(
                            f"<blockquote>{tag}, Basic MediaInfo generated <a href='https://graph.org/{link_id}'>here</a>. Full details unavailable due to format limitations.</blockquote>",
                            disable_web_page_preview=False,
                        )
                    except Exception as e2:
                        LOGGER.error(f"Failed to create basic MediaInfo page: {e2}")
                        if not silent and temp_send:
                            await edit_message(
                                temp_send,
                                "Failed to create MediaInfo page: Unable to process this media format",
                            )
                        return None
                else:
                    # For other errors, show the error message
                    if not silent and temp_send:
                        await edit_message(
                            temp_send, f"Failed to create MediaInfo page: {e!s}"
                        )
                    return None

            # Run garbage collection after Telegraph API call
            smart_garbage_collection(aggressive=False)
        except Exception as e:
            LOGGER.error(f"Unexpected error in MediaInfo generation: {e}")
            if not silent and temp_send:
                await edit_message(temp_send, f"Failed to generate MediaInfo: {e!s}")
            return None
    else:
        if not silent and temp_send:
            await temp_send.edit(
                "Failed to generate MediaInfo. No data was returned."
            )
        return None


async def mediainfo(_, message):
    # Track command execution time for resource management
    start_time = time()

    user_id = message.from_user.id
    buttons = ButtonMaker()
    if message.chat.type != message.chat.type.PRIVATE:
        msg, buttons = await token_check(user_id, buttons)
        if msg is not None:
            reply_message = await send_message(message, msg, buttons.build_menu(1))
            await delete_links(message)
            create_task(auto_delete_message(reply_message, time=300))
            return

    reply = message.reply_to_message

    # Create a more detailed help message
    cmd_prefix = BotCommands.MediaInfoCommand
    cmd_str = (
        f"/{cmd_prefix[0]}" if isinstance(cmd_prefix, list) else f"/{cmd_prefix}"
    )

    help_msg = (
        "<b>📋 MediaInfo Command Help</b>\n\n"
        "<b>Get detailed technical information about media files.</b>\n\n"
        "<b>Usage:</b>\n"
        f"• <code>{cmd_str}</code> - Show this help message\n"
        f"• <code>{cmd_str} [URL]</code> - Get info from a direct download link\n"
        f"• Reply to a media file with <code>{cmd_str}</code> - Get info from the file\n"
        f"• Reply to a message containing a URL with <code>{cmd_str}</code> - Get info from the link\n\n"
        "<b>Supported Media Types:</b>\n"
        "• Video files (MP4, MKV, AVI, WebM, etc.)\n"
        "• Audio files (MP3, FLAC, WAV, etc.)\n"
        "• Subtitle files (SRT, ASS, etc.)\n\n"
        "<b>Note:</b> For large files, only a sample will be downloaded for analysis."
    )

    try:
        # Handle direct URL in command
        if len(message.command) > 1:
            await delete_links(message)
            link = message.command[1]
            await gen_mediainfo(message, link)
            return

        # Handle reply to message with URL
        if reply and reply.text:
            await delete_links(message)
            # Try to extract URL from text
            url_match = re_search(r"https?://\S+", reply.text)
            if url_match:
                link = url_match.group(0)
                await gen_mediainfo(message, link)
                return
            # If no URL found, try the whole text as a link
            await gen_mediainfo(message, reply.text)
            return

        # Handle reply to media file
        if reply:
            await delete_links(message)
            file = next(
                (
                    i
                    for i in [
                        reply.document,
                        reply.video,
                        reply.audio,
                        reply.animation,
                        reply.voice,
                        reply.video_note,
                    ]
                    if i
                ),
                None,
            )
            if file:
                await gen_mediainfo(message, link=None, media=file, reply=reply)
                return

        # If we get here, show help message
        await delete_message(message)
        help_message = await send_message(message, help_msg)
        create_task(auto_delete_message(help_message, time=300))

    except Exception as e:
        LOGGER.error(f"MediaInfo command error: {e}")
        error_msg = f"<b>Error processing MediaInfo command:</b> {e!s}"
        error_message = await send_message(message, error_msg)
        create_task(auto_delete_message(error_message, time=300))
    finally:
        # Calculate execution time
        execution_time = (
            time() - start_time
        )  # Run garbage collection after command execution
        # Use aggressive mode for long-running commands
        if execution_time > 10:  # If command took more than 10 seconds
            smart_garbage_collection(aggressive=True)
        else:
            smart_garbage_collection(aggressive=False)
