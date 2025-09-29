"""
Gallery-dl URL parser and platform detection
Following the pattern of streamrip_utils/url_parser.py
"""

import asyncio

from bot import LOGGER

try:
    import gallery_dl
    from gallery_dl import extractor
except ImportError:
    gallery_dl = None
    extractor = None
    LOGGER.error("gallery-dl not installed. Install with: pip install gallery-dl")


async def is_gallery_dl_url(url: str) -> bool:
    """
    Check if URL is supported by gallery-dl
    Similar to is_streamrip_url() pattern
    """
    if not gallery_dl or not extractor:
        return False

    try:
        # Use gallery-dl's extractor.find() to check if URL is supported
        result = await asyncio.get_event_loop().run_in_executor(
            None, extractor.find, url
        )
        return result is not None
    except Exception:
        return False


async def get_gallery_dl_info(url: str) -> dict | None:
    """
    Get detailed information about a gallery-dl supported URL
    Returns platform info, content type, and capabilities
    """
    if not gallery_dl or not extractor:
        return None

    try:
        # Get extractor for URL
        extr = await asyncio.get_event_loop().run_in_executor(
            None, extractor.find, url
        )

        if not extr:
            return None

        # Extract platform information
        return {
            "supported": True,
            "extractor": extr.category,
            "subcategory": extr.subcategory,
            "platform_name": _get_platform_display_name(extr.category),
            "requires_auth": _requires_authentication(extr.category),
            "supports_quality": _supports_quality_selection(extr.category),
            "supports_batch": _supports_batch_download(extr.category),
            "content_types": _get_content_types(extr.category),
            "url": url,
        }

    except Exception as e:
        LOGGER.error(f"Failed to get gallery-dl info for {url}: {e}")
        return None


def _get_platform_display_name(category: str) -> str:
    """Get human-readable platform name"""
    platform_names = {
        # Social Media & Mainstream
        "instagram": "Instagram",
        "twitter": "Twitter/X",
        "facebook": "Facebook",
        "tiktok": "TikTok",
        "reddit": "Reddit",
        "tumblr": "Tumblr",
        "mastodon": "Mastodon",
        "bluesky": "Bluesky",
        "discord": "Discord",
        "pinterest": "Pinterest",
        "weibo": "Weibo",
        "bilibili": "Bilibili",
        # Art & Design Platforms
        "deviantart": "DeviantArt",
        "pixiv": "Pixiv",
        "artstation": "ArtStation",
        "behance": "Behance",
        "flickr": "Flickr",
        "unsplash": "Unsplash",
        "500px": "500px",
        "newgrounds": "Newgrounds",
        "furaffinity": "FurAffinity",
        "weasyl": "Weasyl",
        "architizer": "Architizer",
        "desktopography": "Desktopography",
        "wikiart": "WikiArt",
        "xfolio": "Xfolio",
        # Image Hosts & File Sharing
        "imgur": "Imgur",
        "catbox": "Catbox",
        "gofile": "GoFile",
        "bunkr": "Bunkr",
        "cyberdrop": "Cyberdrop",
        "fapello": "Fapello",
        "erome": "Erome",
        "webmshare": "WebMShare",
        "chevereto": "Chevereto",
        "lolisafe": "Lolisafe",
        # Booru & Anime
        "danbooru": "Danbooru",
        "gelbooru": "Gelbooru",
        "safebooru": "Safebooru",
        "e621": "e621",
        "e926": "e926",
        "konachan": "Konachan",
        "yandere": "Yande.re",
        "sankaku": "Sankaku",
        "zerochan": "Zerochan",
        "3dbooru": "3DBooru",
        # Manga & Comics
        "mangadex": "MangaDex",
        "webtoons": "Webtoons",
        "nhentai": "nhentai",
        "hitomi": "Hitomi",
        "hentai2read": "Hentai2Read",
        "hentaifoundry": "HentaiFoundry",
        "hentaihand": "HentaiHand",
        "hentaicosplays": "HentaiCosplays",
        "dynastyscans": "Dynasty Scans",
        "batoto": "Batoto",
        "comick": "Comick",
        "comicvine": "Comic Vine",
        # Adult Content
        "kemono": "Kemono Party",
        "coomer": "Coomer Party",
        "fuskator": "Fuskator",
        "xhamster": "xHamster",
        "xvideos": "XVideos",
        "adultempire": "Adult Empire",
        "8muses": "8Muses",
        "aryion": "Aryion",
        "furry34": "Furry34",
        "yiffverse": "Yiffverse",
        # Subscription & Premium
        "patreon": "Patreon",
        "fanbox": "Pixiv Fanbox",
        "fantia": "Fantia",
        "boosty": "Boosty",
        "cien": "Ci-en",
        "subscribestar": "SubscribeStar",
        # Forums & Imageboards
        "4chan": "4chan",
        "8chan": "8chan",
        "2ch": "2ch",
        "2chan": "2chan",
        "2chen": "2chen",
        "4archive": "4archive",
        "4chanarchives": "4chanArchives",
        "arcalive": "ArcaLive",
        "foolfuuka": "FoolFuuka",
        "foolslide": "FoolSlide",
        # Video & Streaming
        "youtube": "YouTube",
        "vimeo": "Vimeo",
        "twitch": "Twitch",
        "bbc": "BBC",
        "ytdl": "YouTube-DL",
        # Professional & Business
        "linkedin": "LinkedIn",
        "civitai": "CivitAI",
        "shopify": "Shopify",
        # Blogs & Personal Sites
        "blogger": "Blogger",
        "hatenablog": "Hatena Blog",
        "35photo": "35Photo",
        # Literature & Text
        "ao3": "Archive of Our Own",
        "fanfiction": "FanFiction.Net",
        # Wikis & Knowledge
        "wikimedia": "Wikimedia",
        "wikifeet": "WikiFeet",
        # Misc & Specialized
        "agnph": "AGNPH",
        "everia": "Everia",
        "exhentai": "ExHentai",
        "girlsreleased": "Girls Released",
        "girlswithmuscle": "Girls With Muscle",
        "weebcentral": "Weeb Central",
        "zzup": "ZZup",
        "directlink": "Direct Link",
        "generic": "Generic",
        "recursive": "Recursive",
        "noop": "No-Op",
    }
    return platform_names.get(category, category.title())


def _requires_authentication(category: str) -> bool:
    """Check if platform typically requires authentication"""
    auth_required_platforms = {
        # Social Media (OAuth/Login required)
        "instagram",
        "twitter",
        "facebook",
        "tiktok",
        "reddit",
        "tumblr",
        "mastodon",
        "bluesky",
        "discord",
        "pinterest",
        "weibo",
        "bilibili",
        # Art Platforms (Account required for full access)
        "deviantart",
        "pixiv",
        "artstation",
        "behance",
        "flickr",
        "furaffinity",
        "weasyl",
        "newgrounds",
        # Subscription/Premium Platforms
        "patreon",
        "fanbox",
        "fantia",
        "boosty",
        "cien",
        "subscribestar",
        # Adult Content (Age verification)
        "kemono",
        "coomer",
        "exhentai",
        "nhentai",
        "hentaifoundry",
        "sankaku",
        "gelbooru",
        "danbooru",
        "e621",
        # Professional Platforms
        "linkedin",
        "civitai",
        # Literature Platforms
        "ao3",
        "fanfiction",
        # Forums (Registration required)
        "arcalive",
        "girlswithmuscle",
        # File Hosts (API keys)
        "gofile",
        "catbox",
        # Video Platforms
        "youtube",
        "vimeo",
        "twitch",
    }
    return category in auth_required_platforms


def _supports_quality_selection(category: str) -> bool:
    """Check if platform supports quality selection"""
    quality_platforms = {
        # Social Media (multiple resolutions)
        "instagram",
        "twitter",
        "facebook",
        "tiktok",
        "reddit",
        "tumblr",
        "mastodon",
        "bluesky",
        "discord",
        "pinterest",
        "weibo",
        "bilibili",
        # Art Platforms (original/preview sizes)
        "deviantart",
        "pixiv",
        "artstation",
        "behance",
        "flickr",
        "unsplash",
        "500px",
        "furaffinity",
        "weasyl",
        "newgrounds",
        "35photo",
        # Image Hosts (size variants)
        "imgur",
        "catbox",
        "gofile",
        "bunkr",
        "cyberdrop",
        "fapello",
        # Booru Sites (sample/original)
        "danbooru",
        "gelbooru",
        "safebooru",
        "e621",
        "e926",
        "konachan",
        "yandere",
        "sankaku",
        "zerochan",
        "3dbooru",
        # Video Platforms (resolution options)
        "youtube",
        "vimeo",
        "twitch",
        "bbc",
        # Manga/Comics (page quality)
        "mangadex",
        "webtoons",
        "nhentai",
        "hitomi",
        "hentai2read",
        # Professional Platforms
        "civitai",
        "linkedin",
    }
    return category in quality_platforms


def _supports_batch_download(category: str) -> bool:
    """Check if platform supports batch downloads (galleries, user profiles, etc.)"""
    batch_platforms = {
        # Social Media (user profiles, feeds)
        "instagram",
        "twitter",
        "facebook",
        "tiktok",
        "reddit",
        "tumblr",
        "mastodon",
        "bluesky",
        "discord",
        "pinterest",
        "weibo",
        "bilibili",
        # Art Platforms (galleries, collections)
        "deviantart",
        "pixiv",
        "artstation",
        "behance",
        "flickr",
        "unsplash",
        "500px",
        "furaffinity",
        "weasyl",
        "newgrounds",
        "35photo",
        "wikiart",
        # Image Hosts (albums, galleries)
        "imgur",
        "catbox",
        "gofile",
        "bunkr",
        "cyberdrop",
        "fapello",
        "erome",
        "webmshare",
        # Booru Sites (tag searches, pools)
        "danbooru",
        "gelbooru",
        "safebooru",
        "e621",
        "e926",
        "konachan",
        "yandere",
        "sankaku",
        "zerochan",
        "3dbooru",
        # Subscription Platforms (creator feeds)
        "patreon",
        "fanbox",
        "fantia",
        "boosty",
        "cien",
        "subscribestar",
        # Adult Content (user galleries)
        "kemono",
        "coomer",
        "exhentai",
        "nhentai",
        "hentaifoundry",
        "xhamster",
        "xvideos",
        "8muses",
        "aryion",
        "furry34",
        "yiffverse",
        # Manga/Comics (series, chapters)
        "mangadex",
        "webtoons",
        "hitomi",
        "hentai2read",
        "hentaihand",
        "dynastyscans",
        "batoto",
        "comick",
        "comicvine",
        # Forums (threads, boards)
        "4chan",
        "8chan",
        "2ch",
        "2chan",
        "arcalive",
        "foolfuuka",
        # Video Platforms (playlists, channels)
        "youtube",
        "vimeo",
        "twitch",
        "bbc",
        # Professional Platforms
        "civitai",
        "linkedin",
        # Literature (series, collections)
        "ao3",
        "fanfiction",
        # Blogs (post archives)
        "blogger",
        "hatenablog",
    }
    return category in batch_platforms


def _get_content_types(category: str) -> list:
    """Get supported content types for platform"""
    content_types_map = {
        "instagram": ["images", "videos", "stories", "reels", "igtv"],
        "twitter": ["images", "videos", "gifs"],
        "deviantart": ["images", "videos", "literature"],
        "pixiv": ["images", "manga", "ugoira"],
        "artstation": ["images", "videos"],
        "behance": ["images", "videos"],
        "flickr": ["images", "videos"],
        "reddit": ["images", "videos", "gifs"],
        "tumblr": ["images", "videos", "gifs"],
        "imgur": ["images", "videos", "gifs"],
        "facebook": ["images", "videos"],
        "tiktok": ["videos"],
        "bilibili": ["videos", "images"],
        "youtube": ["videos"],
        "danbooru": ["images"],
        "gelbooru": ["images"],
        "e621": ["images", "videos"],
        "nhentai": ["images"],
        "mangadex": ["images"],
        "webtoons": ["images"],
        "patreon": ["images", "videos", "audio"],
        "fanbox": ["images", "videos"],
        "kemono": ["images", "videos", "files"],
        "newgrounds": ["images", "videos", "audio", "games"],
        "furaffinity": ["images"],
        "mastodon": ["images", "videos"],
        "bluesky": ["images", "videos"],
        "discord": ["images", "videos", "files"],
        "pinterest": ["images"],
        "unsplash": ["images"],
        "500px": ["images"],
        "weibo": ["images", "videos"],
        # Additional platforms with comprehensive content types
        "catbox": ["images", "videos", "files"],
        "gofile": ["files", "images", "videos"],
        "bunkr": ["images", "videos", "files"],
        "cyberdrop": ["images", "videos", "files"],
        "fapello": ["images", "videos"],
        "erome": ["images", "videos", "albums"],
        "safebooru": ["images"],
        "konachan": ["images"],
        "yandere": ["images"],
        "sankaku": ["images", "videos"],
        "zerochan": ["images"],
        "3dbooru": ["images", "3d"],
        "fantia": ["images", "videos", "posts"],
        "boosty": ["images", "videos", "posts"],
        "cien": ["images", "videos", "posts"],
        "coomer": ["images", "videos", "files"],
        "exhentai": ["images", "galleries"],
        "hentaifoundry": ["images", "stories"],
        "xhamster": ["videos", "images"],
        "xvideos": ["videos", "images"],
        "8muses": ["comics", "images"],
        "hitomi": ["images", "galleries"],
        "hentai2read": ["manga", "images"],
        "dynastyscans": ["manga", "images"],
        "batoto": ["manga", "images"],
        "comick": ["comics", "images"],
        "4chan": ["images", "videos", "threads"],
        "8chan": ["images", "videos", "threads"],
        "2ch": ["images", "threads"],
        "arcalive": ["images", "videos", "posts"],
        "vimeo": ["videos", "albums"],
        "twitch": ["videos", "clips", "streams"],
        "bbc": ["videos", "images"],
        "civitai": ["images", "models", "3d"],
        "linkedin": ["images", "posts", "articles"],
        "ao3": ["stories", "series", "bookmarks"],
        "fanfiction": ["stories", "chapters"],
        "blogger": ["posts", "images"],
        "hatenablog": ["posts", "images"],
        "wikimedia": ["images", "media"],
        "wikifeet": ["images", "galleries"],
        "weasyl": ["images", "stories", "multimedia"],
        "35photo": ["images", "galleries"],
        "wikiart": ["images", "artworks"],
        "subscribestar": ["images", "videos", "posts"],
        "aryion": ["images", "stories"],
        "furry34": ["images", "videos"],
        "yiffverse": ["images", "videos"],
        "e926": ["images", "animations"],
        "hentaihand": ["manga", "images"],
        "hentaicosplays": ["images", "cosplay"],
        "webmshare": ["videos", "webm"],
        "girlsreleased": ["images", "videos"],
        "girlswithmuscle": ["images", "galleries"],
        "weebcentral": ["images", "anime"],
        "zzup": ["images", "videos"],
        "agnph": ["images", "stories"],
        "everia": ["images", "galleries"],
        "fuskator": ["images", "galleries"],
        "adultempire": ["videos", "images"],
        "desktopography": ["images", "wallpapers"],
        "architizer": ["images", "architecture"],
        "xfolio": ["images", "portfolios"],
        "chevereto": ["images", "albums"],
        "lolisafe": ["files", "images"],
        "directlink": ["files", "images", "videos"],
        "generic": ["files", "images", "videos"],
        "recursive": ["files", "images", "videos"],
        "ytdl": ["videos", "audio", "playlists"],
    }
    return content_types_map.get(category, ["images", "videos"])


async def get_supported_platforms() -> list:
    """Get list of all supported platforms"""
    if not gallery_dl or not extractor:
        return []

    try:
        # Get all available extractors
        extractors = await asyncio.get_event_loop().run_in_executor(
            None, extractor.extractors
        )

        platforms = []
        seen_categories = set()

        for extr in extractors:
            if extr.category not in seen_categories:
                platforms.append(
                    {
                        "category": extr.category,
                        "name": _get_platform_display_name(extr.category),
                        "requires_auth": _requires_authentication(extr.category),
                        "supports_quality": _supports_quality_selection(
                            extr.category
                        ),
                        "supports_batch": _supports_batch_download(extr.category),
                        "content_types": _get_content_types(extr.category),
                    }
                )
                seen_categories.add(extr.category)

        # Sort by platform name
        platforms.sort(key=lambda x: x["name"])
        return platforms

    except Exception as e:
        LOGGER.error(f"Failed to get supported platforms: {e}")
        return []
