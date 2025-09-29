import re
import warnings
from asyncio import sleep
from secrets import token_hex

# Suppress SyntaxWarnings for escape sequences in regex patterns
warnings.filterwarnings("ignore", category=SyntaxWarning, module=__name__)

from telegraph.aio import Telegraph
from telegraph.exceptions import RetryAfterError, TelegraphException

from bot import LOGGER


class TelegraphHelper:
    def __init__(self, author_name=None, author_url=None):
        self._telegraph = Telegraph(domain="graph.org")
        self._author_name = author_name
        self._author_url = author_url
        # List of allowed tags by Telegraph API
        self._allowed_tags = [
            "a",
            "aside",
            "b",
            "blockquote",
            "br",
            "code",
            "em",
            "figcaption",
            "figure",
            "h3",
            "h4",
            "hr",
            "i",
            "iframe",
            "img",
            "li",
            "ol",
            "p",
            "pre",
            "s",
            "strong",
            "u",
            "ul",
            "video",
        ]

    async def create_account(self):
        LOGGER.info("Creating Telegraph Account")
        try:
            await self._telegraph.create_account(
                short_name=token_hex(4),
                author_name=self._author_name,
                author_url=self._author_url,
            )
        except Exception as e:
            LOGGER.error(f"Failed to create Telegraph Account: {e}")

    def _sanitize_content(self, content):
        """Sanitize HTML content to ensure it only contains tags allowed by Telegraph API."""
        if not isinstance(content, str):
            return content

        # Replace any <untitled> tags (the specific error we're seeing)
        content = re.sub(r"<\s*untitled\s*>", "", content)
        content = re.sub(r"<\s*/\s*untitled\s*>", "", content)

        # Find all HTML tags in the content
        tags = re.findall(r"<\s*([a-zA-Z0-9]+)[^>]*>", content)

        # For each tag that's not in the allowed list, replace it with appropriate alternatives
        for tag in set(tags):
            if tag.lower() not in self._allowed_tags:
                LOGGER.info(
                    f"Replacing unsupported tag <{tag}> with allowed alternative"
                )

                # Replace opening tags
                if tag.lower() in ["div", "span"]:
                    # Replace div and span with p
                    # Use string concatenation instead of f-strings for regex patterns
                    content = re.sub(
                        r"<\s*" + re.escape(tag) + r"([^>]*)>",
                        r"<p\1>",
                        content,
                        flags=re.IGNORECASE,
                    )
                    content = re.sub(
                        r"<\s*/\s*" + re.escape(tag) + r"\s*>",
                        r"</p>",
                        content,
                        flags=re.IGNORECASE,
                    )
                elif tag.lower() in ["h1", "h2", "h5", "h6"]:
                    # Replace other heading levels with h4
                    content = re.sub(
                        r"<\s*" + re.escape(tag) + r"([^>]*)>",
                        r"<h4\1>",
                        content,
                        flags=re.IGNORECASE,
                    )
                    content = re.sub(
                        r"<\s*/\s*" + re.escape(tag) + r"\s*>",
                        r"</h4>",
                        content,
                        flags=re.IGNORECASE,
                    )
                else:
                    # Remove other unsupported tags but keep their content
                    content = re.sub(
                        r"<\s*" + re.escape(tag) + r"[^>]*>",
                        "",
                        content,
                        flags=re.IGNORECASE,
                    )
                    content = re.sub(
                        r"<\s*/\s*" + re.escape(tag) + r"\s*>",
                        "",
                        content,
                        flags=re.IGNORECASE,
                    )

        return content

    async def create_page(self, title, content):
        # Sanitize content before sending to Telegraph
        sanitized_content = self._sanitize_content(content)

        try:
            return await self._telegraph.create_page(
                title=title,
                author_name=self._author_name,
                author_url=self._author_url,
                html_content=sanitized_content,
            )
        except RetryAfterError as st:
            await sleep(st.retry_after)
            return await self.create_page(title, content)
        except TelegraphException as e:
            if str(e) == "CONTENT_TOO_BIG":
                # Split the content in half and try again
                if isinstance(content, str):
                    # If it's a string, split it by paragraphs or lines
                    if "<br>" in content:
                        parts = content.split("<br>", 1)
                    else:
                        # Split roughly in the middle
                        mid = len(content) // 2
                        parts = [content[:mid], content[mid:]]

                    if len(parts) > 1:
                        # Create first page with first half
                        return await self.create_page(title, parts[0])
                    LOGGER.error(f"Cannot split content: {e}")
                    raise
                LOGGER.error(f"Content is not a string, cannot split: {e}")
                raise
            if "'untitled' tag is not allowed" in str(e):
                # If we still get the untitled tag error after sanitization,
                # try a more aggressive approach
                LOGGER.warning(
                    "Still encountering 'untitled' tag error after sanitization, trying more aggressive approach"
                )

                # More aggressive sanitization - strip all tags except the most basic ones
                # Create a very simple version with only basic tags
                basic_content = "<h4>Media Information</h4><br><br>"

                # Extract any text between <pre> tags if possible
                pre_content = re.findall(
                    r"<pre>(.*?)</pre>", sanitized_content, re.DOTALL
                )
                if pre_content:
                    for content_block in pre_content:
                        # Clean the content of any HTML tags
                        clean_text = re.sub(r"<[^>]*>", "", content_block)
                        basic_content += f"<pre>{clean_text}</pre><br>"
                else:
                    # If no pre tags, just extract some plain text
                    clean_text = re.sub(r"<[^>]*>", "", sanitized_content)
                    # Limit to first 1000 characters
                    if len(clean_text) > 1000:
                        clean_text = clean_text[:1000] + "..."
                    basic_content += f"<pre>{clean_text}</pre><br>"

                # Try again with the more aggressively sanitized content
                return await self._telegraph.create_page(
                    title=title,
                    author_name=self._author_name,
                    author_url=self._author_url,
                    html_content=basic_content,
                )
            LOGGER.error(f"Telegraph error: {e}")
            raise

    async def edit_page(self, path, title, content):
        # Sanitize content before sending to Telegraph
        sanitized_content = self._sanitize_content(content)

        try:
            return await self._telegraph.edit_page(
                path=path,
                title=title,
                author_name=self._author_name,
                author_url=self._author_url,
                html_content=sanitized_content,
            )
        except RetryAfterError as st:
            await sleep(st.retry_after)
            return await self.edit_page(path, title, content)

    async def edit_telegraph(self, path, telegraph_content):
        nxt_page = 1
        prev_page = 0
        num_of_path = len(path)
        for content in telegraph_content:
            # Sanitize content before sending to Telegraph
            sanitized_content = self._sanitize_content(content)

            if nxt_page == 1:
                sanitized_content += (
                    f'<b><a href="https://telegra.ph/{path[nxt_page]}">Next</a></b>'
                )
                nxt_page += 1
            else:
                if prev_page <= num_of_path:
                    sanitized_content += f'<b><a href="https://telegra.ph/{path[prev_page]}">Prev</a></b>'
                    prev_page += 1
                if nxt_page < num_of_path:
                    sanitized_content += f'<b> | <a href="https://telegra.ph/{path[nxt_page]}">Next</a></b>'
                    nxt_page += 1
            await self.edit_page(
                path=path[prev_page],
                title="Mirror-leech-bot Torrent Search",
                content=sanitized_content,
            )


telegraph = TelegraphHelper(
    "Mirror-Leech-Telegram-Bot",
    "https://github.com/anasty17/mirror-leech-telegram-bot",
)
