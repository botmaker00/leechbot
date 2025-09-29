from asyncio import sleep
from random import choice
from time import time
from urllib.parse import quote

from aiohttp import ClientSession
from pyshorteners import Shortener

from bot import shorteners_list
from bot.core.config_manager import Config


async def short(long_url):
    """
    Shorten a URL with minimum time enforcement.

    Args:
        long_url (str): The URL to shorten

    Returns:
        str: Shortened URL or original URL if shortening fails
    """
    # Get minimum time configuration
    min_time = Config.SHORTENER_MIN_TIME or 10
    start_time = time()

    # If no shorteners configured, wait minimum time and return original URL
    if not shorteners_list:
        elapsed = time() - start_time
        if elapsed < min_time:
            await sleep(min_time - elapsed)
        return long_url

    shortened_url = long_url
    success = False

    # Try custom shorteners first
    async with ClientSession() as session:
        for _attempt in range(4):
            shortener_info = choice(shorteners_list)
            try:
                async with session.get(
                    f"https://{shortener_info['domain']}/api?api={shortener_info['api_key']}&url={quote(long_url)}",
                ) as response:
                    result = await response.json()
                    short_url = result.get("shortenedUrl", long_url)
                    if short_url != long_url:
                        shortened_url = short_url
                        success = True
                        break
            except Exception:
                continue

    # Fallback to TinyURL if custom shorteners failed
    if not success:
        s = Shortener()
        for _attempt in range(4):
            try:
                shortened_url = s.tinyurl.short(long_url)
                success = True
                break
            except Exception:
                await sleep(1)

    # Ensure minimum time has elapsed before returning result
    elapsed = time() - start_time
    if elapsed < min_time:
        remaining_time = min_time - elapsed
        await sleep(remaining_time)

    # Return the shortened URL (or original if shortening failed)
    return shortened_url
