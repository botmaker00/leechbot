"""
QR Code Generator Module for Telegram Bot

This module provides comprehensive QR code generation functionality with support for:
- Basic QR code generation from text/URLs
- Multiple error correction levels
- Customizable size and border
- Different image formats (PNG, JPEG, SVG)
- Styled QR codes with different module shapes
- Color customization
- Reply-to-message support
- Batch processing capabilities
"""

import contextlib
import io
import os
import tempfile

import qrcode
from PIL import Image
from pyrogram.types import Message

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import new_task, sync_to_async
from bot.helper.telegram_helper.message_utils import send_message

# QR Code configuration constants
QR_ERROR_LEVELS = {
    "L": qrcode.constants.ERROR_CORRECT_L,  # ~7% correction
    "M": qrcode.constants.ERROR_CORRECT_M,  # ~15% correction (default)
    "Q": qrcode.constants.ERROR_CORRECT_Q,  # ~25% correction
    "H": qrcode.constants.ERROR_CORRECT_H,  # ~30% correction
}

QR_IMAGE_FORMATS = ["PNG", "JPEG", "SVG"]
QR_DEFAULT_SIZE = 10
QR_DEFAULT_BORDER = 4
QR_MAX_DATA_LENGTH = 4296  # Maximum data capacity for QR codes


class QRCodeGenerator:
    """Advanced QR Code Generator with styling options"""

    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

    @staticmethod
    def validate_data(data: str) -> tuple[bool, str]:
        """Validate QR code data"""
        if not data or not data.strip():
            return (
                False,
                "❌ <b>Empty Data Error</b>\n\n"
                "Please provide text or URL to encode in the QR code.",
            )

        if len(data) > QR_MAX_DATA_LENGTH:
            return (
                False,
                f"❌ <b>Data Too Long</b>\n\n"
                f"Maximum <code>{QR_MAX_DATA_LENGTH}</code> characters allowed.\n"
                f"Current length: <code>{len(data)}</code> characters",
            )

        return True, ""

    def generate_basic_qr(
        self,
        data: str,
        error_correction: str = "M",
        box_size: int = QR_DEFAULT_SIZE,
        border: int = QR_DEFAULT_BORDER,
        fill_color: str = "black",
        back_color: str = "white",
        image_format: str = "PNG",
    ) -> tuple[bool, io.BytesIO | str]:
        """Generate basic QR code with customization options"""
        try:
            # Validate inputs
            is_valid, error_msg = self.validate_data(data)
            if not is_valid:
                return False, error_msg

            error_level = QR_ERROR_LEVELS.get(
                error_correction.upper(), qrcode.constants.ERROR_CORRECT_M
            )

            # Create QR code instance
            qr = qrcode.QRCode(
                version=1,  # Auto-sizing
                error_correction=error_level,
                box_size=max(1, min(box_size, 50)),  # Limit box size
                border=max(0, min(border, 20)),  # Limit border
            )

            qr.add_data(data)
            qr.make(fit=True)

            # Generate image
            if image_format.upper() == "SVG":
                from qrcode.image.svg import SvgPathImage

                img = qr.make_image(
                    image_factory=SvgPathImage,
                    fill_color=fill_color,
                    back_color=back_color,
                )
                svg_buffer = io.StringIO()
                img.save(svg_buffer)
                return True, svg_buffer.getvalue()
            img = qr.make_image(fill_color=fill_color, back_color=back_color)

            # Convert to specified format
            if image_format.upper() == "JPEG":
                # Convert RGBA to RGB for JPEG
                if img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, back_color)
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(
                        img, mask=img.split()[-1] if img.mode == "RGBA" else None
                    )
                    img = background

            buffer = io.BytesIO()
            img.save(
                buffer,
                format=image_format.upper(),
                quality=95 if image_format.upper() == "JPEG" else None,
            )
            buffer.seek(0)
            return True, buffer

        except Exception as e:
            LOGGER.error(f"Error generating QR code: {e}")
            return False, f"❌ <b>QR Generation Error</b>\n\n<code>{e!s}</code>"

    def generate_styled_qr(
        self,
        data: str,
        module_drawer: str = "square",
        error_correction: str = "M",
        box_size: int = QR_DEFAULT_SIZE,
        border: int = QR_DEFAULT_BORDER,
        fill_color: str = "black",
        back_color: str = "white",
    ) -> tuple[bool, io.BytesIO | str]:
        """Generate styled QR code with different module shapes"""
        try:
            from qrcode.image.styledpil import StyledPilImage
            from qrcode.image.styles.moduledrawers import (
                CircleModuleDrawer,
                HorizontalBarsDrawer,
                RoundedModuleDrawer,
                SquareModuleDrawer,
                VerticalBarsDrawer,
            )

            # Validate inputs
            is_valid, error_msg = self.validate_data(data)
            if not is_valid:
                return False, error_msg

            error_level = QR_ERROR_LEVELS.get(
                error_correction.upper(), qrcode.constants.ERROR_CORRECT_M
            )

            # Module drawer mapping
            drawer_map = {
                "square": SquareModuleDrawer(),
                "circle": CircleModuleDrawer(),
                "rounded": RoundedModuleDrawer(),
                "vertical": VerticalBarsDrawer(),
                "horizontal": HorizontalBarsDrawer(),
            }

            drawer = drawer_map.get(module_drawer.lower(), SquareModuleDrawer())

            # Create QR code instance
            qr = qrcode.QRCode(
                version=1,
                error_correction=error_level,
                box_size=max(1, min(box_size, 50)),
                border=max(0, min(border, 20)),
            )

            qr.add_data(data)
            qr.make(fit=True)

            # Generate styled image
            img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=drawer,
                fill_color=fill_color,
                back_color=back_color,
            )

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            return True, buffer

        except ImportError:
            # Fallback to basic QR if styled PIL is not available
            return self.generate_basic_qr(
                data, error_correction, box_size, border, fill_color, back_color
            )
        except Exception as e:
            LOGGER.error(f"Error generating styled QR code: {e}")
            return (
                False,
                f"❌ <b>Styled QR Generation Error</b>\n\n<code>{e!s}</code>",
            )

    def add_logo_to_qr(
        self, qr_buffer: io.BytesIO, logo_path: str | None = None
    ) -> tuple[bool, io.BytesIO | str]:
        """Add logo to center of QR code (if logo provided)"""
        try:
            if not logo_path or not os.path.exists(logo_path):
                return True, qr_buffer

            # Open QR code image
            qr_img = Image.open(qr_buffer)
            logo = Image.open(logo_path)

            # Calculate logo size (10% of QR code size)
            qr_width, qr_height = qr_img.size
            logo_size = min(qr_width, qr_height) // 10

            # Resize logo
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

            # Create a white background for logo
            logo_bg = Image.new("RGB", (logo_size + 20, logo_size + 20), "white")
            logo_bg.paste(logo, (10, 10))

            # Paste logo on QR code
            logo_pos = (
                (qr_width - logo_size - 20) // 2,
                (qr_height - logo_size - 20) // 2,
            )
            qr_img.paste(logo_bg, logo_pos)

            # Save to buffer
            buffer = io.BytesIO()
            qr_img.save(buffer, format="PNG")
            buffer.seek(0)
            return True, buffer

        except Exception as e:
            LOGGER.error(f"Error adding logo to QR code: {e}")
            return True, qr_buffer  # Return original QR if logo addition fails


# Initialize QR code generator
qr_generator = QRCodeGenerator()


def parse_qr_arguments(args: list) -> dict:
    """Parse QR code generation arguments"""
    config = {
        "error_correction": "M",
        "box_size": QR_DEFAULT_SIZE,
        "border": QR_DEFAULT_BORDER,
        "fill_color": "black",
        "back_color": "white",
        "image_format": "PNG",
        "module_drawer": "square",
        "styled": False,
    }

    i = 0
    while i < len(args):
        arg = args[i].lower()

        if arg in ["-e", "--error"] and i + 1 < len(args):
            config["error_correction"] = args[i + 1].upper()
            i += 2
        elif arg in ["-s", "--size"] and i + 1 < len(args):
            with contextlib.suppress(ValueError):
                config["box_size"] = int(args[i + 1])
            i += 2
        elif arg in ["-b", "--border"] and i + 1 < len(args):
            with contextlib.suppress(ValueError):
                config["border"] = int(args[i + 1])
            i += 2
        elif arg in ["-f", "--fill"] and i + 1 < len(args):
            config["fill_color"] = args[i + 1]
            i += 2
        elif arg in ["-bg", "--background"] and i + 1 < len(args):
            config["back_color"] = args[i + 1]
            i += 2
        elif arg in ["-fmt", "--format"] and i + 1 < len(args):
            fmt = args[i + 1].upper()
            if fmt in QR_IMAGE_FORMATS:
                config["image_format"] = fmt
            i += 2
        elif arg in ["-d", "--drawer"] and i + 1 < len(args):
            config["module_drawer"] = args[i + 1].lower()
            config["styled"] = True
            i += 2
        elif arg == "--styled":
            config["styled"] = True
            i += 1
        else:
            i += 1

    return config


@new_task
async def qrcode_command(client, message: Message):
    """
    Generate QR codes from text or URLs

    Usage: /qrcode <text/URL> [options]

    Options:
    -e, --error <L|M|Q|H>     Error correction level (default: M)
    -s, --size <1-50>         Box size (default: 10)
    -b, --border <0-20>       Border size (default: 4)
    -f, --fill <color>        Fill color (default: black)
    -bg, --background <color> Background color (default: white)
    -fmt, --format <PNG|JPEG|SVG> Image format (default: PNG)
    -d, --drawer <square|circle|rounded|vertical|horizontal> Module style
    --styled                  Enable styled QR code

    Examples:
    /qrcode https://example.com
    /qrcode "Hello World" -e H -s 15 -f blue -bg yellow
    /qrcode "Styled QR" --styled -d circle -f red
    """
    try:
        # Handle reply to message first
        reply_to = message.reply_to_message

        # Get content from command arguments - check if message has text with more than just the command
        if message.text and len(message.text.split()) > 1:
            # Extract everything after the command using the same method as paste module
            full_text = message.text.split(None, 1)[1]

            # Parse arguments to separate data from options
            text_parts = full_text.split()
            data_parts = []
            options_start = len(text_parts)

            # Find where options start (arguments starting with -)
            for i, part in enumerate(text_parts):
                if part.startswith("-"):
                    options_start = i
                    break
                data_parts.append(part)

            if data_parts:
                data = " ".join(data_parts)
                args = (
                    text_parts[options_start:]
                    if options_start < len(text_parts)
                    else []
                )
            else:
                # Only options provided, no data
                data = None
                args = []

        # Get content from replied message text
        elif reply_to and reply_to.text:
            data = reply_to.text
            args = []

        # No valid content found
        else:
            # Show detailed usage instructions when no arguments provided
            help_text = """🔲 <b>QR Code Generator</b>

<b>📋 Basic Usage:</b>
• <code>/qrcode &lt;text/URL&gt;</code> - Generate basic QR code
• <code>/qrcode</code> (reply to message) - Generate QR from replied text

<b>⚙️ Advanced Options:</b>
• <code>-e &lt;L|M|Q|H&gt;</code> - Error correction level (default: M)
• <code>-s &lt;1-50&gt;</code> - Box size in pixels (default: 10)
• <code>-b &lt;0-20&gt;</code> - Border size (default: 4)
• <code>-f &lt;color&gt;</code> - Fill color (default: black)
• <code>-bg &lt;color&gt;</code> - Background color (default: white)
• <code>-fmt &lt;PNG|JPEG|SVG&gt;</code> - Image format (default: PNG)
• <code>-d &lt;style&gt;</code> - Module style: square, circle, rounded, vertical, horizontal
• <code>--styled</code> - Enable styled QR code

<b>🎨 Examples:</b>
• <code>/qrcode https://example.com</code>
• <code>/qrcode "Hello World" -e H -s 15</code>
• <code>/qrcode "Blue QR" -f blue -bg yellow</code>
• <code>/qrcode "Styled" --styled -d circle -f red</code>
• <code>/qrcode "Vector QR" -fmt SVG</code>

<b>🔧 Error Correction Levels:</b>
• <b>L</b> - Low (~7% recovery)
• <b>M</b> - Medium (~15% recovery) [Default]
• <b>Q</b> - Quartile (~25% recovery)
• <b>H</b> - High (~30% recovery)

<b>🎯 Supported Colors:</b>
Color names (red, blue, green), hex codes (#FF0000), or RGB values

<b>📊 Data Limits:</b>
Maximum 4,296 characters per QR code"""
            await send_message(message, help_text)
            return

        # Show help
        if data.lower() in ["help", "--help", "-h"]:
            help_text = """🔲 <b>QR Code Generator - Help</b>

<b>📋 Command Syntax:</b>
<code>/qrcode &lt;text/URL&gt; [options]</code>

<b>⚙️ Available Options:</b>
• <code>-e &lt;L|M|Q|H&gt;</code> - Error correction level
• <code>-s &lt;1-50&gt;</code> - Box size in pixels
• <code>-b &lt;0-20&gt;</code> - Border size
• <code>-f &lt;color&gt;</code> - Fill color
• <code>-bg &lt;color&gt;</code> - Background color
• <code>-fmt &lt;PNG|JPEG|SVG&gt;</code> - Image format
• <code>-d &lt;style&gt;</code> - Module style
• <code>--styled</code> - Enable styled QR code

<b>🎨 Module Styles:</b>
<code>square</code>, <code>circle</code>, <code>rounded</code>, <code>vertical</code>, <code>horizontal</code>

<b>🔧 Error Correction:</b>
• <b>L</b> - Low (~7% recovery)
• <b>M</b> - Medium (~15% recovery) [Default]
• <b>Q</b> - Quartile (~25% recovery)
• <b>H</b> - High (~30% recovery)

<b>🎯 Examples:</b>
<code>/qrcode https://example.com</code>
<code>/qrcode "Hello World" -e H -s 15</code>
<code>/qrcode "Blue QR" -f blue -bg yellow</code>
<code>/qrcode "Styled" --styled -d circle</code>"""
            await send_message(message, help_text)
            return

        # Parse arguments
        config = parse_qr_arguments(args)

        # Generate QR code
        if config["styled"]:
            success, result = await sync_to_async(
                qr_generator.generate_styled_qr,
                data,
                config["module_drawer"],
                config["error_correction"],
                config["box_size"],
                config["border"],
                config["fill_color"],
                config["back_color"],
            )
        else:
            success, result = await sync_to_async(
                qr_generator.generate_basic_qr,
                data,
                config["error_correction"],
                config["box_size"],
                config["border"],
                config["fill_color"],
                config["back_color"],
                config["image_format"],
            )

        if not success:
            await send_message(message, result)
            return

        # Send QR code
        if config["image_format"] == "SVG":
            # Send SVG as document
            svg_file = io.BytesIO(result.encode())
            svg_file.name = "qrcode.svg"

            # Safe data display for SVG
            data_display = data[:80] if data else "N/A"
            if data and len(data) > 80:
                data_display += "..."

            caption = (
                f"🔲 <b>QR Code Generated</b> (SVG)\n\n"
                f"📝 <b>Data:</b> <code>{data_display}</code>\n"
                f"📊 <b>Format:</b> Vector SVG\n"
                f"🔧 <b>Error Correction:</b> {config['error_correction']}\n"
                f"📏 <b>Box Size:</b> {config['box_size']}px"
            )

            await message.reply_document(svg_file, caption=caption)
        else:
            # Send image
            filename = f"qrcode.{config['image_format'].lower()}"
            result.name = filename

            # Create styled caption with proper formatting
            style_info = ""
            if config["styled"]:
                style_info = f"\n🎨 <b>Style:</b> {config['module_drawer'].title()}"

            color_info = ""
            if config["fill_color"] != "black" or config["back_color"] != "white":
                color_info = f"\n🎨 <b>Colors:</b> {config['fill_color']} on {config['back_color']}"

            # Error correction percentages
            error_percentages = {"L": "7%", "M": "15%", "Q": "25%", "H": "30%"}
            error_percent = error_percentages.get(config["error_correction"], "15%")

            # Safe data display
            data_display = data[:80] if data else "N/A"
            if data and len(data) > 80:
                data_display += "..."

            caption = (
                f"🔲 <b>QR Code Generated</b>\n\n"
                f"📝 <b>Data:</b> <code>{data_display}</code>\n"
                f"📊 <b>Format:</b> {config['image_format']}\n"
                f"🔧 <b>Error Correction:</b> {config['error_correction']} (~{error_percent} recovery)\n"
                f"📏 <b>Size:</b> {config['box_size']}px box, {config['border']}px border"
                f"{style_info}{color_info}"
            )

            await send_message(message, caption, photo=result)

    except Exception as e:
        LOGGER.error(f"Error in qrcode_command: {e}")
        await send_message(
            message,
            f"❌ <b>QR Code Generation Failed</b>\n\n"
            f"<b>Error:</b> <code>{e!s}</code>\n\n"
            f"💡 <b>Tip:</b> Try using <code>/qrcode help</code> for usage instructions.",
        )
