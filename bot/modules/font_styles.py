#!/usr/bin/env python3
from asyncio import create_task
from logging import getLogger

from bot.helper.telegram_helper.button_build import ButtonMaker
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
        1: get_html_formats_page(),
        2: get_unicode_emoji_page(),
        3: get_template_variables_page(),
        4: get_usage_examples_page(),
        5: get_google_fonts_page(),
    }
    return pages.get(page_num, "Invalid page")


def get_html_formats_page():
    msg = "<b>Available Font Styles for Leech:</b>\n\n"

    # Telegram HTML styles
    msg += "<b>Available HTML formats:</b>\n"
    msg += "• <b>bold</b>: <b>Bold text</b>\n"
    msg += "• <b>italic</b>: <i>Italic text</i>\n"
    msg += "• <b>underline</b>: <u>Underlined text</u>\n"
    msg += "• <b>strike</b>: <s>Strikethrough text</s>\n"
    msg += "• <b>code</b>: <code>Monospace text</code>\n"
    msg += (
        "• <b>monospace</b>: <pre>Preformatted text with preserved spacing</pre>\n"
    )
    msg += "• <b>spoiler</b>: <spoiler>Spoiler text</spoiler>\n"
    msg += "• <b>quote</b>: <blockquote>Quoted text</blockquote>\n"
    msg += "• <b>quote_expandable</b>: <blockquote expandable>Expandable quoted text</blockquote>\n\n"

    # Combined HTML styles
    msg += "<b>Supported combined HTML formats:</b>\n"
    msg += "• <b>bold_italic</b>: <b><i>Bold italic text</i></b>\n"
    msg += "• <b>underline_bold</b>: <u><b>Underlined bold text</b></u>\n"
    msg += "• <b>underline_italic</b>: <u><i>Underlined italic text</i></u>\n"
    msg += "• <b>underline_bold_italic</b>: <u><b><i>Underlined bold italic text</i></b></u>\n"
    msg += "• <b>bold_spoiler</b>: <spoiler><b>Bold spoiler text</b></spoiler>\n"
    msg += "• <b>italic_spoiler</b>: <spoiler><i>Italic spoiler text</i></spoiler>\n"
    msg += "• <b>quote_expandable</b>: <blockquote expandable>This is an expandable blockquote\nwith multiple lines of content</blockquote>\n"
    msg += "• <b>bold_quote</b>: <blockquote><b>Bold quoted text</b></blockquote>\n"
    msg += "• <b>bold_quote_expandable</b>: <blockquote expandable><b>Bold expandable blockquote\nwith multiple lines</b></blockquote>\n"
    msg += "• <b>italic_quote_expandable</b>: <blockquote expandable><i>Italic expandable blockquote\nwith multiple lines</i></blockquote>\n\n"

    msg += "<b>Important HTML formatting notes:</b>\n"
    msg += "• <code>code</code> and <pre>pre</pre> tags cannot contain other formatting\n"
    msg += "• Proper nesting is required for combined tags to work correctly\n"
    msg += "• The <code>expandable</code> attribute is supported for blockquotes\n\n"

    msg += "<b>For Leech Font:</b>\n"
    msg += 'Enter an HTML format name like "bold", "italic", "code", etc.\n'
    msg += "Example: Enter 'bold' to use <b>Bold text</b> for all your leech captions\n\n"

    msg += "<b>For Leech Caption:</b>\n"
    msg += "Use the template variable format: {{variable}html_format}\n"
    msg += "Example: {{filename}bold} - Size: {{size}code}\n"
    msg += "You can also use actual HTML tags. You can also nest them together.\n"
    msg += "<b>Custom Text Formatting:</b> You can format your own text using the same syntax!\n"
    msg += "Example: {{My Custom Text}bold} or {{{{My Text}bold}italic}🔥}\n\n"

    return msg


def get_unicode_emoji_page():
    msg = "<b>Unicode Emojis and Special Characters:</b>\n\n"
    msg += "You can also use any single Unicode character or emoji as a style. Examples:\n"
    msg += "- 🔥: Will add the fire emoji before and after your text\n"
    msg += "- ⭐: Will add stars before and after your text\n"
    msg += "- Any other emoji or special character will be used similarly\n\n"
    msg += "<b>or Leech Font:</b>\n"
    msg += "Any single emoji: 🔥, ⭐, 🚀, etc.\n"
    msg += "Any single Unicode character\n"
    msg += "Unicode codepoints in U+XXXX format (e.g., U+1F525 for 🔥)\n"
    msg += "The emoji will be added before and after your text\n"
    msg += 'Example: If leech font is "🔥" and text is "filename.mp4", it will appear as "🔥filename.mp4🔥"\n\n'
    msg += "<b>For Leech Caption:</b>\n"
    msg += "Use the template variable format: {{variable}unicode_emoji}\n"
    msg += "Example: {{filename}🔥}\n\n"

    return msg


def get_template_variables_page():
    msg = "<b>Template Variables (For Leech Caption and Filename):</b>\n\n"
    msg += "<b>Basic Variables:</b>\n"
    msg += "• <code>{filename}</code> - The name of the file without extension\n"
    msg += "• <code>{size}</code> - The size of the file (e.g., 1.5GB, 750MB)\n"
    msg += (
        "• <code>{duration}</code> - The duration of media files (e.g., 01:30:45)\n"
    )
    msg += (
        "• <code>{quality}</code> - The quality of video files (e.g., 1080p, 720p)\n"
    )
    msg += "• <code>{audios}</code> - Audio languages in the file (e.g., English, Hindi)\n"
    msg += (
        "• <code>{audio_codecs}</code> - Audio codec information (e.g., AAC, AC3)\n"
    )
    msg += "• <code>{subtitles}</code> - Subtitle languages in the file (e.g., English, Spanish)\n"
    msg += "• <code>{md5_hash}</code> - MD5 hash of the file\n"
    msg += "• <code>{ext}</code> - File extension (e.g., mkv, mp4)\n\n"

    msg += "<b>TV Show Variables:</b>\n"
    msg += "• <code>{season}</code> - Season number extracted from filename\n"
    msg += "• <code>{episode}</code> - Episode number extracted from filename\n"
    msg += "• <code>{year}</code> - Release year extracted from filename\n\n"

    msg += "<b>Media Information:</b>\n"
    msg += (
        "• <code>{NumVideos}</code> - Number of video tracks (zero-padded for <10)\n"
    )
    msg += (
        "• <code>{NumAudios}</code> - Number of audio tracks (zero-padded for <10)\n"
    )
    msg += "• <code>{NumSubtitles}</code> - Number of subtitle tracks (zero-padded for <10)\n"
    msg += "• <code>{formate}</code> - File format/extension (uppercase)\n"
    msg += "• <code>{format}</code> - Media container format (e.g., Matroska, MP4)\n"
    msg += "• <code>{id}</code> - Unique ID of the file (based on MD5 hash)\n"
    msg += "• <code>{framerate}</code> - Video framerate (e.g., 24.00 fps)\n"
    msg += "• <code>{codec}</code> - Video codec information (e.g., HEVC, AVC)\n\n"

    msg += "<b>Variable Styling:</b>\n"
    msg += "You can apply different styles to each variable independently:\n"
    msg += (
        "• <code>{{variable}style}</code> - Apply a style to a specific variable\n"
    )
    msg += "   Examples: <code>{{filename}bold}</code>, <code>{{size}code}</code>, <code>{{quality}italic}</code>\n\n"

    msg += "<b>Google Font Styling:</b>\n"
    msg += "• <code>{{variable}FontName}</code> - Apply a Google Font to a variable (converts to appropriate Telegram styling)\n"
    msg += "   Examples: <code>{{filename}Roboto}</code> (no styling), <code>{{size}Open Sans}</code> (no styling)\n"
    msg += "• <code>{{variable}FontName:weight}</code> - Apply a Google Font with specific weight\n"
    msg += "   Examples: <code>{{filename}Roboto:700}</code> (bold), <code>{{size}Open Sans:300}</code> (italic)\n"
    msg += "   Note: Font weights 700+ become bold, 300- become italic, 400-600 remain regular\n\n"

    msg += "<b>Emoji Decoration:</b>\n"
    msg += "• <code>{{variable}emoji}</code> - Decorate a variable with emoji\n"
    msg += "   Examples: <code>{{filename}🔥}</code>, <code>{{size}⭐}</code>\n\n"

    msg += "<b>Nested Styling (Advanced):</b>\n"
    msg += "• <code>{{{variable}style1}style2}</code> - Apply two styles to a variable\n"
    msg += "   Examples: <code>{{{filename}Roboto:700}bold}</code>, <code>{{{filename}bold}italic}</code>\n"
    msg += "   This applies style1 first, then style2 to the result\n\n"
    msg += "<b>Triple Nested Styling (Expert):</b>\n"
    msg += "• <code>{{{{variable}style1}style2}style3}</code> - Apply three styles to a variable\n"
    msg += "   Examples: <code>{{{{filename}bold}italic}🔥}</code>, <code>{{{{filename}bold}🔥}Roboto}</code>\n"
    msg += "   This applies styles in order: style1, then style2, then style3\n"
    msg += "   Perfect for combining HTML format + emoji + Google Font\n\n"
    msg += "<b>Unlimited Nesting (Master):</b>\n"
    msg += "• You can nest styles to any depth with any combination of styles\n"
    msg += (
        "   Example: <code>{{{{{filename}bold}italic}code}underline}strike</code>\n"
    )
    msg += "   This applies styles in order: bold → italic → code → underline → strike\n"
    msg += "   You can combine HTML formats, Google Fonts, and emojis in any order\n"
    msg += "   Example: <code>{{{{{filename}Roboto:700}bold}italic}🔥}underline</code>\n\n"

    msg += "<b>Example Usage:</b>\n"
    msg += (
        "• TV Show: <code>{{filename}bold} S{season}E{episode} [{quality}]</code>\n"
    )
    msg += "• Detailed: <code>{{filename}Roboto} [{formate}] [{{codec}code}] [{framerate}]</code>\n"
    msg += "• Nested: <code>File: {{{filename}bold}italic} | Size: {{size}code}</code>\n"
    msg += "• Complete: <code>{{filename}bold}\nQuality: {{quality}code} | Size: {{size}italic}\nCodec: {codec}\nAudio: {audios} | Subtitles: {subtitles}</code>\n\n"

    return msg


def get_usage_examples_page():
    msg = "<b>Usage Examples:</b>\n\n"
    msg += "1. <b>Setting a default font style for all leech captions:</b>\n"
    msg += '   • Use the /usettings or /settings command and select "LEECH_FONT"\n'
    msg += '   • Enter a font style name like "serif_b" or "Roboto"\n\n'
    msg += "2. <b>Using font styles in caption templates:</b>\n"
    msg += "   • <code>{{filename}serif_b} - Size: {size}</code>\n"
    msg += "   • <code>File: {{filename}Montserrat:700} | {size}</code>\n"
    msg += "   • <code>{{filename}bold} | {{size}italic}</code>\n\n"
    msg += "3. <b>Mixing different font styles:</b>\n"
    msg += "   • <code>{{filename}Roboto:700} | {{size}mono} | {{quality}script}</code>\n"
    msg += (
        "   • <code>{{filename}sans} | {{size}serif} | {{quality}gothic}</code>\n\n"
    )
    msg += "4. <b>Using HTML formatting with variables:</b>\n"
    msg += "   • <code>{{filename}bold_italic} | {{size}code}</code>\n"
    msg += "   • <code>{{filename}spoiler} | {{size}monospace}</code>\n"
    msg += "   • <code>{{filename}bold_code} | {{size}italic_spoiler}</code>\n"
    msg += "   • <code>{{filename}bold_monospace} | {{size}underline_code}</code>\n"
    msg += "   • <code>{{filename}quote_expandable}</code> - For expandable blockquote (requires multiple lines)\n"
    msg += "   • <code>{{filename}bold_quote_expandable}</code> - Bold expandable blockquote\n"
    msg += "   • <code>{{filename}italic_quote_expandable}</code> - Italic expandable blockquote\n\n"
    msg += "5. <b>Using emoji decorations:</b>\n"
    msg += "   • <code>{{filename}🔥} | {{size}⭐}</code>\n"
    msg += "   • <code>{{filename}U+1F525} | {{size}U+2B50}</code> (using Unicode codepoints)\n\n"
    msg += "6. <b>Combining Google Fonts with HTML formatting (nested styles):</b>\n"
    msg += "   • <code>{{{filename}Roboto:700}bold}</code> - Bold Roboto with HTML bold\n"
    msg += "   • <code>{{{filename}Open Sans:300}italic}</code> - Light Open Sans with italic\n\n"
    msg += "7. <b>Triple nesting with emoji and Google Font:</b>\n"
    msg += "   • <code>{{{{filename}bold}italic}🔥}</code> - Bold italic text with fire emoji\n"
    msg += "   • <code>{{{{filename}bold}🔥}Roboto}</code> - Bold text with fire emoji in Roboto font\n"
    msg += "   • <code>{{{{filename}Roboto:700}bold}🔥}</code> - Bold Roboto with HTML bold and fire emoji\n\n"
    msg += "8. <b>Supported nesting with multiple styles:</b>\n"
    msg += "   • <code>{{{filename}bold}italic}</code> - Bold and italic nested styles\n"
    msg += "   • <code>{{{filename}underline}bold}</code> - Underline and bold nested styles\n"
    msg += "   • <code>{{{{filename}bold}italic}spoiler}</code> - Bold italic text in spoiler\n\n"
    msg += "9. <b>Important nesting notes:</b>\n"
    msg += "   • <code>code</code> and <code>pre</code> tags cannot contain other formatting\n"
    msg += "   • Blockquotes support the <code>expandable</code> attribute\n"
    msg += "   • Proper tag nesting is required for Telegram compatibility\n\n"
    msg += "10. <b>Complete caption examples:</b>\n"
    msg += "   • <code>{{filename}bold} [{{quality}code}] - Size: {{size}italic}\nAudio: {audios} | Subtitles: {subtitles}</code>\n"
    msg += "   • <code>🎥 {{filename}Roboto:700} 🎥\nℹ️ Quality: {quality} | 💾 Size: {size}\n🎙️ Audio: {audios} | 📄 Subtitles: {subtitles}</code>\n"
    msg += "   • <code>{{{{filename}bold}italic}🔥} ({year})\n📺 Quality: {{quality}code} | 💾 Size: {{{size}bold}italic}\n🎙️ Audio: {audios} | 📄 Subtitles: {subtitles}</code>\n\n"

    return msg


def get_google_fonts_page():
    msg = "<b>Google Fonts and Important Notes:</b>\n\n"
    msg += "<b>How to Find Google Fonts:</b>\n"
    msg += "1. Visit <a href='https://fonts.google.com/'>fonts.google.com</a>\n"
    msg += "2. Find a font you like\n"
    msg += "3. Use the exact font name in your leech font setting or caption template\n\n"

    msg += "<b>Popular Google Fonts:</b>\n"
    msg += "• <code>Roboto</code> - Clean, modern sans-serif font\n"
    msg += "• <code>Open Sans</code> - Highly readable web font\n"
    msg += "• <code>Lato</code> - Balanced sans-serif with warm feel\n"
    msg += "• <code>Montserrat</code> - Elegant geometric sans-serif\n"
    msg += "• <code>Oswald</code> - Narrow, condensed sans-serif\n"
    msg += "• <code>Raleway</code> - Elegant thin to bold sans-serif\n"
    msg += "• <code>Playfair Display</code> - Elegant serif for headings\n\n"

    msg += "<b>Using Font Weights:</b>\n"
    msg += "You can specify font weights by adding a colon and the weight number:\n"
    msg += "• <code>Roboto:100</code> - Thin\n"
    msg += "• <code>Roboto:300</code> - Light\n"
    msg += "• <code>Roboto:400</code> - Regular (default)\n"
    msg += "• <code>Roboto:500</code> - Medium\n"
    msg += "• <code>Roboto:700</code> - Bold\n"
    msg += "• <code>Roboto:900</code> - Black\n\n"

    msg += "<b>Examples:</b>\n"
    msg += (
        "• <code>{{filename}Roboto}</code> - Regular Roboto (no styling applied)\n"
    )
    msg += "• <code>{{filename}Roboto:700}</code> - Bold Roboto (applies <b>bold</b> styling)\n"
    msg += "• <code>{{filename}Open Sans:300}</code> - Light Open Sans (applies <i>italic</i> styling)\n"
    msg += "• <code>{{filename}Roboto Mono}</code> - Roboto Mono (applies <code>monospace</code> styling)\n"
    msg += "• <code>{{filename}Dancing Script}</code> - Dancing Script (applies <i>italic</i> styling)\n"
    msg += "• <code>{{filename}Playfair Display}</code> - Playfair Display (applies <b>bold</b> styling)\n\n"

    msg += "<b>How Google Fonts Work:</b>\n"
    msg += "Since Telegram doesn't support custom fonts, Google Fonts are converted to appropriate Telegram styling:\n"
    msg += "• <b>Weight 700+</b>: Converted to <b>bold</b> formatting\n"
    msg += "• <b>Weight 300-</b>: Converted to <i>italic</i> formatting\n"
    msg += "• <b>Weight 400-600</b>: No special formatting (regular text)\n"
    msg += (
        "• <b>Monospace fonts</b>: Converted to <code>monospace</code> formatting\n"
    )
    msg += "• <b>Script fonts</b>: Converted to <i>italic</i> formatting\n"
    msg += "• <b>Display fonts</b>: Converted to <b>bold</b> formatting\n\n"

    # Important notes
    msg += "<b>Important Notes:</b>\n"
    msg += "• Unicode font styles only work with basic Latin characters (A-Z, a-z)\n"
    msg += "• Google Fonts apply appropriate Telegram-compatible styling instead of showing font names\n"
    msg += "• HTML formatting is the most compatible across all devices\n"
    msg += "• Font styles are applied after template variables are processed\n"
    msg += "• User settings take priority over owner settings\n"
    msg += "• Not all fonts support all weights - check fonts.google.com for available weights\n"
    msg += "• <code>code</code> and <code>pre</code> tags cannot contain other formatting\n"
    msg += "• Blockquotes support the <code>expandable</code> attribute for collapsible text\n"
    msg += "• For complex nested styles, apply them in order from innermost to outermost\n"
    msg += "• Proper tag nesting is required for Telegram compatibility\n\n"

    msg += "Set your preferred font style in user settings with /usettings or /us command.\n\n"
    msg += (
        "These font styles will be applied to your leech captions in file captions."
    )

    return msg


# Create pagination buttons
def get_pagination_buttons(current_page, total_pages=5):
    buttons = ButtonMaker()

    # Row 1: Previous and Next buttons
    nav_buttons = []

    if current_page > 1:
        nav_buttons.append(("Previous", f"fontstyles_page_{current_page - 1}"))

    if current_page < total_pages:
        nav_buttons.append(("Next", f"fontstyles_page_{current_page + 1}"))

    # Add navigation buttons if any
    for button_text, callback_data in nav_buttons:
        buttons.data_button(button_text, callback_data)

    # Row 2: Close button
    buttons.data_button("Close", "fontstyles_close")

    # Add debug log# Use 2 buttons per row if we have 2 nav buttons, otherwise 1 button per row
    return buttons.build_menu(min(len(nav_buttons), 2))


async def font_styles_cmd(_, message):
    """
    Display available font styles for leech with pagination
    """

    # Delete the command message immediately
    await delete_message(message)

    # Start with page 1
    current_page = 1
    content = get_page_content(current_page)
    buttons = get_pagination_buttons(current_page)

    # Send the first page
    font_msg = await send_message(message, content, buttons)

    # Schedule auto-deletion after 5 minutes
    create_task(auto_delete_message(font_msg, time=300))


async def font_styles_callback(_, callback_query):
    """
    Handle pagination callbacks for font styles guide
    """
    data = callback_query.data
    message = callback_query.message
    if data == "fontstyles_noop":
        await callback_query.answer("No action")
        return

    if data == "fontstyles_close":
        # Delete the message when Close button is clicked
        try:
            await delete_message(message)
            await callback_query.answer("Closed")
        except Exception as e:
            LOGGER.error(f"Error deleting message: {e!s}")
            await callback_query.answer("Error closing")
        return

    # Extract page number from callback data
    if data.startswith("fontstyles_page_"):
        try:
            page_num = int(data.split("_")[-1])
            content = get_page_content(page_num)
            buttons = get_pagination_buttons(page_num)

            # Edit the message with new page content
            await edit_message(message, content, buttons)
            await callback_query.answer(f"Page {page_num}")
        except Exception as e:
            LOGGER.error(f"Error in font_styles_callback: {e!s}")
            await callback_query.answer("Error processing request")


# Handler will be added in core/handlers.py
# Also need to register the callback handler
