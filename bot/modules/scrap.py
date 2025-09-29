import asyncio
import contextlib
import re
import urllib.parse
from html import escape
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


class TamilMVScraper:
    """Scraper for 1tamilmv website"""

    def __init__(self):
        self.main_domain = "1tamilmv.com"
        self.current_domain = None
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
        )
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.aclose()

    async def _get_domain_from_url(self, url):
        """Extract domain from a given URL"""
        if url:
            parsed = urlparse(url)
            if parsed.netloc:
                # Extract domain from provided URL
                domain = parsed.netloc.replace("www.", "")
                if any(base in domain for base in ["1tamilmv", "tamilmv"]):
                    self.current_domain = domain
                    LOGGER.info(f"Using TamilMV domain from URL: {domain}")
                    return domain

        # If no valid URL provided, use main domain
        self.current_domain = self.main_domain
        LOGGER.info(f"Using main TamilMV domain: {self.main_domain}")
        return self.main_domain

    def _extract_size(self, text):
        """Extract file size from text (legacy method - use _extract_qualities_and_sizes for better results)"""
        if not text:
            return "Unknown"

        # Look for file size patterns while avoiding bitrates
        size_patterns = [
            r"(\d+(?:\.\d+)?)\s*(GB|TB)",  # GB and TB are almost always file sizes
            r"([1-9]\d{2,})\s*(MB)",  # MB values >= 100 (avoid small MB that might be bitrates)
        ]

        for pattern in size_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                size_unit = match.group(2).upper()

                # Additional check for context to avoid bitrates
                match_pos = text.lower().find(match.group(0).lower())
                if match_pos != -1:
                    context_start = max(0, match_pos - 15)
                    context_end = min(
                        len(text), match_pos + len(match.group(0)) + 15
                    )
                    context = text[context_start:context_end].lower()

                    # Skip if context suggests it's a bitrate
                    if any(
                        indicator in context
                        for indicator in ["kbps", "mbps", "bitrate", "audio"]
                    ):
                        continue

                return f"{match.group(1)} {size_unit}"

        return "Unknown"

    def _extract_magnet_links_with_details(self, soup):
        """Extract all magnet links with their individual details (preserving order)"""
        magnet_links_found = []  # Use list to preserve order
        magnet_details = []

        # Look for magnet links in various places
        magnet_patterns = [
            'a[href^="magnet:"]',
            'a[href*="magnet:"]',
            'input[value^="magnet:"]',
        ]

        for pattern in magnet_patterns:
            elements = soup.select(pattern)
            for element in elements:
                magnet = element.get("href") or element.get("value")
                if (
                    magnet
                    and magnet.startswith("magnet:")
                    and magnet not in magnet_links_found
                ):
                    magnet_links_found.append(magnet)
                    # Extract details from the magnet link itself
                    details = self._parse_magnet_details(magnet)
                    magnet_details.append(details)

        # Look in text content for magnet links
        text_content = soup.get_text()
        magnet_matches = re.findall(r'magnet:\?[^\s<>"]+', text_content)
        for magnet in magnet_matches:
            # Only add if not already found
            if magnet not in magnet_links_found:
                magnet_links_found.append(magnet)
                details = self._parse_magnet_details(magnet)
                magnet_details.append(details)

        return magnet_details

    def _parse_magnet_details(self, magnet_link):
        """Parse individual magnet link details"""
        # Extract title from magnet link dn parameter
        title_match = re.search(r"dn=([^&]+)", magnet_link)
        if title_match:
            # URL decode the title
            title = urllib.parse.unquote_plus(title_match.group(1))
            # Clean the title
            title = self._clean_magnet_title(title)
        else:
            title = "Unknown Title"

        # Extract quality and size from title
        quality = self._extract_quality_from_title(title)
        size = self._extract_size_from_title(title)

        return {
            "title": title,
            "quality": quality,
            "size": size,
            "magnet_link": magnet_link,
        }

    def _clean_magnet_title(self, title):
        """Clean magnet link title"""
        if not title:
            return "Unknown Title"

        # Remove common prefixes
        title = re.sub(
            r"^(www\.)?1TamilMV\.(onl|com|org|net|in|me|tv|cc|fi)\s*-\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove file extensions
        title = re.sub(
            r"\.(mkv|mp4|avi|mov|wmv|flv|webm)$", "", title, flags=re.IGNORECASE
        )

        # Clean up spacing
        title = re.sub(r"\s+", " ", title.strip())

        return title or "Unknown Title"

    def _extract_quality_from_title(self, title):
        """Extract quality from individual title"""
        if not title:
            return "Unknown"

        # Quality patterns in order of preference
        quality_patterns = [
            r"(\d+p)",  # 1080p, 720p, etc.
            r"(4K|UHD)",
            r"(HD)",
            r"(BluRay|BR)",
            r"(WEB-DL)",
            r"(HDRip)",
            r"(DVDRip)",
            r"(CAM)",
            r"(TS)",
            r"(TC)",
        ]

        for pattern in quality_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return "Unknown"

    def _extract_size_from_title(self, title):
        """Extract size from individual title"""
        if not title:
            return "Unknown"

        # Look for size patterns while avoiding bitrates
        size_patterns = [
            r"(\d+(?:\.\d+)?)\s*(GB|TB)",  # GB and TB are almost always file sizes
            r"([1-9]\d{2,})\s*(MB)",  # MB values >= 100 (avoid small MB that might be bitrates)
        ]

        for pattern in size_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                size_value = float(match.group(1))
                size_unit = match.group(2).upper()

                # Additional filtering to avoid bitrates
                if size_unit == "MB" and size_value < 50:
                    continue

                # Check context to avoid bitrates
                match_pos = title.lower().find(match.group(0).lower())
                if match_pos != -1:
                    context_start = max(0, match_pos - 15)
                    context_end = min(
                        len(title), match_pos + len(match.group(0)) + 15
                    )
                    context = title[context_start:context_end].lower()

                    # Skip if context suggests it's a bitrate
                    if any(
                        indicator in context
                        for indicator in ["kbps", "mbps", "bitrate", "audio"]
                    ):
                        continue

                return f"{match.group(1)} {size_unit}"

        return "Unknown"

    def _extract_qualities_and_sizes(self, soup):
        """Extract quality and size information"""
        content_text = soup.get_text()

        # Enhanced quality patterns
        quality_patterns = [
            r"(\d+p)",  # 1080p, 720p, etc.
            r"(4K|UHD)",
            r"(HD)",
            r"(BluRay|BR)",
            r"(WEB-DL)",
            r"(HDRip)",
            r"(DVDRip)",
            r"(CAM)",
            r"(TS)",
            r"(TC)",
        ]

        qualities_found = set()
        for pattern in quality_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            qualities_found.update([q.upper() for q in matches])

        # Enhanced size extraction - look for file size patterns while avoiding bitrates
        size_patterns = [
            # Look for sizes that are likely file sizes (avoid small KB values that might be bitrates)
            r"(\d+(?:\.\d+)?)\s*(GB|TB)",  # GB and TB are almost always file sizes
            r"([1-9]\d{2,})\s*(MB)",  # MB values >= 100 (avoid small MB that might be bitrates)
            r"(\d+(?:\.\d+)?)\s*(MB)(?!\s*[/\-]?\s*s)",  # MB not followed by "/s" or "-s" (to avoid Mbps)
        ]

        sizes_found = []
        for pattern in size_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            for match in matches:
                size_value = float(match[0])
                size_unit = match[1].upper()

                # Additional filtering to avoid bitrates
                if size_unit == "MB" and size_value < 50:
                    # Skip very small MB values that are likely bitrates
                    continue

                # Skip if the context suggests it's a bitrate (look for surrounding text)
                size_str = f"{match[0]} {size_unit}"

                # Look for bitrate indicators around this match
                match_pos = content_text.lower().find(
                    f"{match[0]} {match[1].lower()}"
                )
                if match_pos != -1:
                    # Check 20 characters before and after for bitrate indicators
                    context_start = max(0, match_pos - 20)
                    context_end = min(
                        len(content_text), match_pos + len(size_str) + 20
                    )
                    context = content_text[context_start:context_end].lower()

                    # Skip if context suggests it's a bitrate
                    if any(
                        indicator in context
                        for indicator in [
                            "kbps",
                            "mbps",
                            "bitrate",
                            "audio",
                            "dd5.1",
                            "aac",
                        ]
                    ):
                        continue

                sizes_found.append(size_str)

        # Remove duplicates while preserving order
        unique_sizes = []
        seen_sizes = set()
        for size in sizes_found:
            if size not in seen_sizes:
                seen_sizes.add(size)
                unique_sizes.append(size)

        return {"qualities": list(qualities_found), "sizes": unique_sizes}

    def _clean_title(self, title):
        """Clean and format the title"""
        if not title:
            return "Unknown Title"

        # Remove extra whitespace and common prefixes/suffixes
        title = re.sub(r"\s+", " ", title.strip())
        title = re.sub(r"^(Download\s*|Watch\s*)", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*-\s*1TamilMV.*$", "", title, flags=re.IGNORECASE)

        return title.strip() or "Unknown Title"

    async def scrape_movie_info(self, url):
        """
        Scrape comprehensive movie information from 1tamilmv URL

        Args:
            url (str): The movie page URL

        Returns:
            dict: Dictionary containing title, qualities, sizes, and magnet_links
        """
        try:
            # Get working domain
            domain = await self._get_domain_from_url(url)

            if url and urlparse(url).netloc:
                # Use provided URL
                target_url = url
            else:
                # If no URL provided, we can't scrape specific movie
                raise ValueError("Movie URL is required for scraping")

            LOGGER.info(f"Scraping movie info from: {target_url}")

            # Fetch the page
            response = await self.session.get(target_url)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Extract title
            title = None
            title_selectors = [
                "h1.entry-title",
                "h1",
                "title",
                ".post-title",
                ".entry-header h1",
                ".ipsType_pageTitle",
            ]

            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = title_element.get_text().strip()
                    break

            title = self._clean_title(title)

            # Extract detailed magnet links with individual titles, qualities, and sizes
            magnet_details = self._extract_magnet_links_with_details(soup)

            result = {
                "title": title,
                "magnet_details": magnet_details,
                "total_magnets": len(magnet_details),
                "source_url": target_url,
                "domain": domain,
            }

            LOGGER.info(
                f"Successfully scraped: {title} - Found {len(magnet_details)} magnet links"
            )
            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code} while accessing {url}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"Request error while accessing {url}: {e!s}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Error scraping movie info: {e!s}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e


class TamilBlastersScraper:
    """Scraper for 1tamilblasters website"""

    def __init__(self):
        self.main_domain = "1tamilblasters.com"
        self.current_domain = None
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
        )
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.aclose()

    async def _get_domain_from_url(self, url):
        """Extract domain from a given URL"""
        if url:
            parsed = urlparse(url)
            if parsed.netloc:
                # Extract domain from provided URL
                domain = parsed.netloc.replace("www.", "")
                if any(
                    base in domain for base in ["1tamilblasters", "tamilblasters"]
                ):
                    self.current_domain = domain
                    LOGGER.info(f"Using TamilBlasters domain from URL: {domain}")
                    return domain

        # If no valid URL provided, use main domain
        self.current_domain = self.main_domain
        LOGGER.info(f"Using main TamilBlasters domain: {self.main_domain}")
        return self.main_domain

    def _extract_magnet_links_with_details(self, soup):
        """Extract all magnet links with their individual details (preserving order)"""
        magnet_links_found = []  # Use list to preserve order
        magnet_details = []

        # Look for magnet links in various places
        magnet_patterns = [
            'a[href^="magnet:"]',
            'a[href*="magnet:"]',
            'input[value^="magnet:"]',
        ]

        for pattern in magnet_patterns:
            elements = soup.select(pattern)
            for element in elements:
                magnet = element.get("href") or element.get("value")
                if (
                    magnet
                    and magnet.startswith("magnet:")
                    and magnet not in magnet_links_found
                ):
                    magnet_links_found.append(magnet)
                    # Extract details from the magnet link itself
                    details = self._parse_magnet_details(magnet)
                    magnet_details.append(details)

        # Look in text content for magnet links
        text_content = soup.get_text()
        magnet_matches = re.findall(r'magnet:\?[^\s<>"]+', text_content)
        for magnet in magnet_matches:
            # Only add if not already found
            if magnet not in magnet_links_found:
                magnet_links_found.append(magnet)
                details = self._parse_magnet_details(magnet)
                magnet_details.append(details)

        return magnet_details

    def _parse_magnet_details(self, magnet_link):
        """Parse individual magnet link details"""
        # Extract title from magnet link dn parameter
        title_match = re.search(r"dn=([^&]+)", magnet_link)
        if title_match:
            # URL decode the title
            title = urllib.parse.unquote_plus(title_match.group(1))
            # Clean the title
            title = self._clean_magnet_title(title)
        else:
            title = "Unknown Title"

        # Extract quality and size from title
        quality = self._extract_quality_from_title(title)
        size = self._extract_size_from_title(title)

        return {
            "title": title,
            "quality": quality,
            "size": size,
            "magnet_link": magnet_link,
        }

    def _clean_magnet_title(self, title):
        """Clean magnet link title"""
        if not title:
            return "Unknown Title"

        # Remove common prefixes for TamilBlasters
        title = re.sub(
            r"^(www\.)?1TamilBlasters\.(how|net|com|org|in|me|tv|cc)\s*-\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove file extensions
        title = re.sub(
            r"\.(mkv|mp4|avi|mov|wmv|flv|webm)$", "", title, flags=re.IGNORECASE
        )

        # Clean up spacing
        title = re.sub(r"\s+", " ", title.strip())

        return title or "Unknown Title"

    def _extract_quality_from_title(self, title):
        """Extract quality from individual title"""
        if not title:
            return "Unknown"

        # Quality patterns in order of preference
        quality_patterns = [
            r"(\d+p)",  # 1080p, 720p, etc.
            r"(4K|UHD)",
            r"(HD)",
            r"(BluRay|BR)",
            r"(WEB-DL)",
            r"(HDRip)",
            r"(DVDRip)",
            r"(CAM)",
            r"(TS)",
            r"(TC)",
        ]

        for pattern in quality_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return "Unknown"

    def _extract_size_from_title(self, title):
        """Extract size from individual title"""
        if not title:
            return "Unknown"

        # Look for size patterns while avoiding bitrates
        size_patterns = [
            r"(\d+(?:\.\d+)?)\s*(GB|TB)",  # GB and TB are almost always file sizes
            r"([1-9]\d{2,})\s*(MB)",  # MB values >= 100 (avoid small MB that might be bitrates)
        ]

        for pattern in size_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                size_value = float(match.group(1))
                size_unit = match.group(2).upper()

                # Additional filtering to avoid bitrates
                if size_unit == "MB" and size_value < 50:
                    continue

                # Check context to avoid bitrates
                match_pos = title.lower().find(match.group(0).lower())
                if match_pos != -1:
                    context_start = max(0, match_pos - 15)
                    context_end = min(
                        len(title), match_pos + len(match.group(0)) + 15
                    )
                    context = title[context_start:context_end].lower()

                    # Skip if context suggests it's a bitrate
                    if any(
                        indicator in context
                        for indicator in ["kbps", "mbps", "bitrate", "audio"]
                    ):
                        continue

                return f"{match.group(1)} {size_unit}"

        return "Unknown"

    def _clean_title(self, title):
        """Clean and format the title"""
        if not title:
            return "Unknown Title"

        # Remove extra whitespace and common prefixes/suffixes
        title = re.sub(r"\s+", " ", title.strip())
        title = re.sub(r"^(Download\s*|Watch\s*)", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*-\s*1TamilBlasters.*$", "", title, flags=re.IGNORECASE)

        return title.strip() or "Unknown Title"

    async def scrape_movie_info(self, url):
        """
        Scrape comprehensive movie information from 1tamilblasters URL

        Args:
            url (str): The movie page URL

        Returns:
            dict: Dictionary containing title, qualities, sizes, and magnet_links
        """
        try:
            # Get working domain
            domain = await self._get_domain_from_url(url)

            if url and urlparse(url).netloc:
                # Use provided URL
                target_url = url
            else:
                # If no URL provided, we can't scrape specific movie
                raise ValueError("Movie URL is required for scraping")

            LOGGER.info(f"Scraping TamilBlasters movie info from: {target_url}")

            # Fetch the page
            response = await self.session.get(target_url)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Extract title - TamilBlasters uses different selectors
            title = None
            title_selectors = [
                "h1.ipsType_pageTitle",
                'h1[data-role="title"]',
                ".ipsType_pageTitle",
                "h1",
                "title",
                ".post-title",
                ".entry-header h1",
            ]

            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = title_element.get_text().strip()
                    break

            title = self._clean_title(title)

            # Extract detailed magnet links with individual titles, qualities, and sizes
            magnet_details = self._extract_magnet_links_with_details(soup)

            result = {
                "title": title,
                "magnet_details": magnet_details,
                "total_magnets": len(magnet_details),
                "source_url": target_url,
                "domain": domain,
            }

            LOGGER.info(
                f"Successfully scraped TamilBlasters: {title} - Found {len(magnet_details)} magnet links"
            )
            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code} while accessing {url}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"Request error while accessing {url}: {e!s}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Error scraping TamilBlasters movie info: {e!s}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e


class MovierulzScraper:
    """Scraper for 5movierulz website"""

    def __init__(self):
        self.main_domain = "5movierulz.skin"
        self.current_domain = None
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
        )
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.aclose()

    async def _get_domain_from_url(self, url):
        """Extract domain from a given URL"""
        if url:
            parsed = urlparse(url)
            if parsed.netloc:
                # Extract domain from provided URL
                domain = parsed.netloc.replace("www.", "")
                if any(base in domain for base in ["5movierulz", "movierulz"]):
                    self.current_domain = domain
                    LOGGER.info(f"Using Movierulz domain from URL: {domain}")
                    return domain

        # If no valid URL provided, use main domain
        self.current_domain = self.main_domain
        LOGGER.info(f"Using main Movierulz domain: {self.main_domain}")
        return self.main_domain

    def _extract_magnet_links_with_details(self, soup):
        """Extract all magnet links with their individual details (preserving order)"""
        magnet_links_found = []  # Use list to preserve order
        magnet_details = []

        # Look for magnet links in various places
        magnet_patterns = [
            'a[href^="magnet:"]',
            'a[href*="magnet:"]',
            'input[value^="magnet:"]',
        ]

        for pattern in magnet_patterns:
            elements = soup.select(pattern)
            for element in elements:
                magnet = element.get("href") or element.get("value")
                if (
                    magnet
                    and magnet.startswith("magnet:")
                    and magnet not in magnet_links_found
                ):
                    magnet_links_found.append(magnet)
                    # Extract details from the magnet link itself
                    details = self._parse_magnet_details(magnet)
                    magnet_details.append(details)

        # Look in text content for magnet links
        text_content = soup.get_text()
        magnet_matches = re.findall(r'magnet:\?[^\s<>"]+', text_content)
        for magnet in magnet_matches:
            # Only add if not already found
            if magnet not in magnet_links_found:
                magnet_links_found.append(magnet)
                details = self._parse_magnet_details(magnet)
                magnet_details.append(details)

        return magnet_details

    def _parse_magnet_details(self, magnet_link):
        """Parse individual magnet link details"""
        # Extract title from magnet link dn parameter
        title_match = re.search(r"dn=([^&]+)", magnet_link)
        if title_match:
            # URL decode the title
            title = urllib.parse.unquote_plus(title_match.group(1))
            # Clean the title
            title = self._clean_magnet_title(title)
        else:
            title = "Unknown Title"

        # Extract quality and size from title
        quality = self._extract_quality_from_title(title)
        size = self._extract_size_from_title(title)

        return {
            "title": title,
            "quality": quality,
            "size": size,
            "magnet_link": magnet_link,
        }

    def _clean_magnet_title(self, title):
        """Clean magnet link title"""
        if not title:
            return "Unknown Title"

        # Remove common prefixes for Movierulz
        title = re.sub(
            r"^(www\.)?5Movierulz\.(skin|voto|com|org|in|me|tv|cc)\s*-\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove file extensions
        title = re.sub(
            r"\.(mkv|mp4|avi|mov|wmv|flv|webm)$", "", title, flags=re.IGNORECASE
        )

        # Clean up spacing
        title = re.sub(r"\s+", " ", title.strip())

        return title or "Unknown Title"

    def _extract_quality_from_title(self, title):
        """Extract quality from individual title"""
        if not title:
            return "Unknown"

        # Quality patterns in order of preference
        quality_patterns = [
            r"(\d+p)",  # 1080p, 720p, etc.
            r"(4K|UHD)",
            r"(HD)",
            r"(BluRay|BR)",
            r"(WEB-DL)",
            r"(HDRip)",
            r"(DVDRip)",
            r"(CAM)",
            r"(TS)",
            r"(TC)",
        ]

        for pattern in quality_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return "Unknown"

    def _extract_size_from_title(self, title):
        """Extract size from individual title"""
        if not title:
            return "Unknown"

        # Look for size patterns while avoiding bitrates
        size_patterns = [
            r"(\d+(?:\.\d+)?)\s*(GB|TB)",  # GB and TB are almost always file sizes
            r"([1-9]\d{2,})\s*(MB)",  # MB values >= 100 (avoid small MB that might be bitrates)
        ]

        for pattern in size_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                size_value = float(match.group(1))
                size_unit = match.group(2).upper()

                # Additional filtering to avoid bitrates
                if size_unit == "MB" and size_value < 50:
                    continue

                # Check context to avoid bitrates
                match_pos = title.lower().find(match.group(0).lower())
                if match_pos != -1:
                    context_start = max(0, match_pos - 15)
                    context_end = min(
                        len(title), match_pos + len(match.group(0)) + 15
                    )
                    context = title[context_start:context_end].lower()

                    # Skip if context suggests it's a bitrate
                    if any(
                        indicator in context
                        for indicator in ["kbps", "mbps", "bitrate", "audio"]
                    ):
                        continue

                return f"{match.group(1)} {size_unit}"

        return "Unknown"

    def _clean_title(self, title):
        """Clean and format the title"""
        if not title:
            return "Unknown Title"

        # Remove extra whitespace and common prefixes/suffixes
        title = re.sub(r"\s+", " ", title.strip())
        title = re.sub(r"^(Download\s*|Watch\s*)", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*-\s*5Movierulz.*$", "", title, flags=re.IGNORECASE)

        return title.strip() or "Unknown Title"

    async def scrape_movie_info(self, url):
        """
        Scrape comprehensive movie information from 5movierulz URL

        Args:
            url (str): The movie page URL

        Returns:
            dict: Dictionary containing title, qualities, sizes, and magnet_links
        """
        try:
            # Get working domain
            domain = await self._get_domain_from_url(url)

            if url and urlparse(url).netloc:
                # Use provided URL
                target_url = url
            else:
                # If no URL provided, we can't scrape specific movie
                raise ValueError("Movie URL is required for scraping")

            LOGGER.info(f"Scraping Movierulz movie info from: {target_url}")

            # Fetch the page
            response = await self.session.get(target_url)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Extract title - Movierulz uses different selectors
            title = None
            title_selectors = [
                "h1.entry-title",
                "h1.post-title",
                ".movie-title h1",
                "h1",
                "title",
                ".post-title",
                ".entry-header h1",
            ]

            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = title_element.get_text().strip()
                    break

            title = self._clean_title(title)

            # Extract detailed magnet links with individual titles, qualities, and sizes
            magnet_details = self._extract_magnet_links_with_details(soup)

            result = {
                "title": title,
                "magnet_details": magnet_details,
                "total_magnets": len(magnet_details),
                "source_url": target_url,
                "domain": domain,
            }

            LOGGER.info(
                f"Successfully scraped Movierulz: {title} - Found {len(magnet_details)} magnet links"
            )
            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code} while accessing {url}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"Request error while accessing {url}: {e!s}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Error scraping Movierulz movie info: {e!s}"
            LOGGER.error(error_msg)
            raise Exception(error_msg) from e


async def scrape_tamilmv_movie(url=None):
    """
    Convenience function to scrape 1tamilmv movie information

    Args:
        url (str, optional): Movie page URL. If None, will find working domain

    Returns:
        dict: Movie information including title, size, and magnet_link
    """
    async with TamilMVScraper() as scraper:
        return await scraper.scrape_movie_info(url)


async def scrape_tamilblasters_movie(url=None):
    """
    Convenience function to scrape 1tamilblasters movie information

    Args:
        url (str, optional): Movie page URL. If None, will find working domain

    Returns:
        dict: Movie information including title, size, and magnet_link
    """
    async with TamilBlastersScraper() as scraper:
        return await scraper.scrape_movie_info(url)


async def scrape_movierulz_movie(url=None):
    """
    Convenience function to scrape 5movierulz movie information

    Args:
        url (str, optional): Movie page URL. If None, will find working domain

    Returns:
        dict: Movie information including title, size, and magnet_link
    """
    async with MovierulzScraper() as scraper:
        return await scraper.scrape_movie_info(url)


async def scrape_movie_info(url):
    """
    Universal function to scrape movie information from supported sites

    Args:
        url (str): Movie page URL

    Returns:
        dict: Movie information including title, size, and magnet_link
    """
    if not url:
        raise ValueError("URL is required for scraping")

    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()

    # Determine which scraper to use based on domain
    if any(site in domain for site in ["1tamilmv", "tamilmv"]):
        return await scrape_tamilmv_movie(url)

    if any(site in domain for site in ["1tamilblasters", "tamilblasters"]):
        return await scrape_tamilblasters_movie(url)

    if any(site in domain for site in ["5movierulz", "movierulz"]):
        return await scrape_movierulz_movie(url)

    raise ValueError(
        f"Unsupported domain: {domain}. Currently supported: 1tamilmv, 1tamilblasters, 5movierulz"
    )


def format_movie_info(movie_info):
    """
    Format comprehensive movie information for display

    Args:
        movie_info (dict): Movie information dictionary

    Returns:
        str: Formatted movie information
    """
    title = escape(movie_info.get("title", "Unknown Title"))
    magnet_details = movie_info.get("magnet_details", [])
    total_magnets = movie_info.get("total_magnets", 0)
    source_url = movie_info.get("source_url", "")
    domain = movie_info.get("domain", "")

    formatted = f"🎬 <b>Title:</b> {title}\n"

    # Add magnet links info (no qualities/sizes in main message)
    if magnet_details:
        formatted += f"🧲 <b>Magnet Links:</b> {total_magnets} found\n"
    else:
        formatted += "🧲 <b>Magnet Links:</b> Not found\n"

    if source_url:
        formatted += f"🌐 <b>Source:</b> {escape(source_url)}\n"

    if domain:
        formatted += f"📡 <b>Domain:</b> {escape(domain)}"

    return formatted


def format_magnet_links(magnet_details, max_links=None):
    """
    Format magnet links with individual details and expandable blockquotes

    Args:
        magnet_details (list): List of magnet detail dictionaries
        max_links (int): Maximum number of links per message (None for all)

    Returns:
        list: List of formatted message strings
    """
    if not magnet_details:
        return ["❌ No magnet links found"]

    # Telegram message limit (4096 characters)
    MESSAGE_LIMIT = 4096

    messages = []
    current_message = f"🧲 <b>Magnet Links ({len(magnet_details)} total):</b>\n\n"

    for i, detail in enumerate(magnet_details, 1):
        # Extract individual details
        title = detail.get("title", "Unknown Title")
        quality = detail.get("quality", "Unknown")
        size = detail.get("size", "Unknown")
        magnet = detail.get("magnet_link", "")

        # Format each magnet link with individual details and expandable blockquote
        magnet_block = f"<b>{i}. {escape(title)}</b>\n"
        magnet_block += f"🎯 <b>Quality:</b> {escape(quality)} | 📦 <b>Size:</b> {escape(size)}\n"
        magnet_block += f"<blockquote expandable><code>{escape(magnet)}</code>\n</blockquote>\n\n"

        # Check if adding this magnet block would exceed the limit
        if len(current_message + magnet_block) > MESSAGE_LIMIT:
            # If current message has content beyond header, save it
            if len(current_message.strip()) > len(
                f"🧲 <b>Magnet Links ({len(magnet_details)} total):</b>"
            ):
                messages.append(current_message.rstrip())

            # Create message with just this magnet link
            single_magnet_msg = f"🧲 <b>Magnet Link {i}:</b>\n\n{magnet_block}"

            # Check if even the single magnet message is too long
            if len(single_magnet_msg) > MESSAGE_LIMIT:
                # For extremely long magnet links, split into multiple messages
                magnet_messages = _split_long_magnet_link(
                    i, title, quality, size, magnet, MESSAGE_LIMIT
                )
                messages.extend(magnet_messages)
            else:
                messages.append(single_magnet_msg.rstrip())

            # Start fresh for next links - no "continued" message
            current_message = (
                f"🧲 <b>Magnet Links ({len(magnet_details)} total):</b>\n\n"
            )
            continue

        # Add magnet block to current message
        current_message += magnet_block

        # If max_links is specified and reached, break
        if max_links and i >= max_links:
            if len(magnet_details) > max_links:
                current_message += f"<i>... and {len(magnet_details) - max_links} more links available</i>"
            break

    # Add the last message if it has actual content beyond headers
    stripped_message = current_message.strip()
    if stripped_message and not (
        stripped_message == "🧲 <b>Magnet Links (continued):</b>"
        or stripped_message
        == f"🧲 <b>Magnet Links ({len(magnet_details)} total):</b>"
    ):
        messages.append(current_message.rstrip())

    return messages


def _split_long_magnet_link(index, title, quality, size, magnet_link, message_limit):
    """
    Split extremely long magnet links into multiple messages while preserving HTML formatting

    Args:
        index (int): Magnet link index
        title (str): Movie title
        quality (str): Video quality
        size (str): File size
        magnet_link (str): The magnet link
        message_limit (int): Telegram message character limit

    Returns:
        list: List of message strings for this magnet link
    """
    messages = []

    # Create header with metadata
    header = f"🧲 <b>Magnet Link {index}: {escape(title)}</b>\n"
    header += (
        f"🎯 <b>Quality:</b> {escape(quality)} | 📦 <b>Size:</b> {escape(size)}\n"
    )

    # Escape the magnet link for HTML
    escaped_magnet = escape(magnet_link)

    # Calculate available space for magnet link content
    # Reserve space for blockquote expandable tags and some buffer
    blockquote_tags_overhead = len(
        "<blockquote expandable><code></code>\n</blockquote>"
    )
    buffer_space = 50
    available_space = (
        message_limit - len(header) - blockquote_tags_overhead - buffer_space
    )

    # If the magnet link fits in one message with blockquote expandable format
    if len(escaped_magnet) <= available_space:
        simple_message = (
            header
            + f"<blockquote expandable><code>{escaped_magnet}</code>\n</blockquote>"
        )
        messages.append(simple_message)
        return messages

    # For very long magnet links, split into multiple parts
    # First message with header and start of magnet link
    first_part_space = (
        available_space - 20
    )  # Reserve space for continuation indicator
    first_part = escaped_magnet[:first_part_space]
    first_message = (
        header
        + f"<blockquote expandable><code>{first_part}...</code>\n</blockquote>\n\n<i>📄 Continued in next message...</i>"
    )
    messages.append(first_message)

    # Remaining parts
    remaining_magnet = escaped_magnet[first_part_space:]
    part_number = 2

    while remaining_magnet:
        # Calculate space for continuation messages
        continuation_header = (
            f"🧲 <b>Magnet Link {index} (Part {part_number}):</b>\n"
        )
        continuation_space = (
            message_limit
            - len(continuation_header)
            - blockquote_tags_overhead
            - buffer_space
        )

        if len(remaining_magnet) <= continuation_space:
            # Last part
            continuation_message = (
                continuation_header
                + f"<blockquote expandable><code>{remaining_magnet}</code>\n</blockquote>"
            )
            messages.append(continuation_message)
            break

        # More parts needed
        continuation_space -= 20  # Reserve space for continuation indicator
        part_content = remaining_magnet[:continuation_space]
        continuation_message = (
            continuation_header
            + f"<blockquote expandable><code>{part_content}...</code>\n</blockquote>\n\n<i>📄 Continued in next message...</i>"
        )
        messages.append(continuation_message)
        remaining_magnet = remaining_magnet[continuation_space:]
        part_number += 1

    return messages


async def show_detailed_help(message):
    """Show detailed help for scraping commands"""
    help_text = (
        "🔍 <b>Scrap Command Help</b>\n\n"
        "<b>Purpose:</b>\n"
        "Extract movie title, file sizes, qualities, and magnet links from supported movie sites.\n\n"
        "<b>Usage:</b>\n"
        "<code>/scrap &lt;movie_url&gt;</code> - Scrape movie information\n"
        "<code>/scrap help</code> - Show this help message\n"
        "<code>/scrap domains</code> - Check main domains\n"
        "Reply to a message with a URL using <code>/scrap</code> - Extract and scrape the URL\n\n"
        "<b>Supported Sites:</b>\n"
        "🎬 <b>1TamilMV:</b> Any 1tamilmv.* domain\n"
        "   Main: https://1tamilmv.com\n\n"
        "🎬 <b>1TamilBlasters:</b> Any 1tamilblasters.* domain\n"
        "   Main: https://1tamilblasters.com\n\n"
        "🎬 <b>5Movierulz:</b> Any 5movierulz.* domain\n"
        "   Main: https://5movierulz.skin\n\n"
        "<b>Examples:</b>\n"
        "<code>/scrap https://www.1tamilmv.onl/movie-name-2024</code>\n"
        "<code>/scrap https://www.1tamilblasters.how/forums/topic/movie-name</code>\n"
        "<code>/scrap https://www.5movierulz.voto/movie-name/watch-online.html</code>\n"
        "Reply to any message containing a supported URL with <code>/scrap</code>\n\n"
        "<b>Features:</b>\n"
        "• Automatic site detection from URL\n"
        "• Extracts multiple qualities (1080p, 720p, HD, etc.)\n"
        "• Finds all available file sizes\n"
        "• Retrieves all magnet links\n"
        "• Works with any domain variation\n"
        "• Smart filtering (excludes audio bitrates from file sizes)\n"
        "• Auto-deletes command messages after extraction\n"
        "• Reply-to-message support for easy URL extraction\n\n"
        "<b>Note:</b>\n"
        "Simply provide any working URL from the supported sites or reply to a message containing one. The scraper will automatically detect and use the correct domain."
    )

    reply = await send_message(message, help_text)
    await auto_delete_message(reply, time=120)

    # Auto-delete the command message after a brief delay
    await asyncio.sleep(2)
    with contextlib.suppress(Exception):
        await message.delete()


async def check_working_domains(message):
    """Check and display main domains for TamilMV, TamilBlasters, and Movierulz"""
    try:
        checking_msg = await send_message(
            message, "🔍 <b>Checking main domains...</b>"
        )

        results = []

        # Check TamilMV main domain
        try:
            async with TamilMVScraper() as scraper:
                main_domain = scraper.main_domain
                try:
                    url = f"https://{main_domain}"
                    response = await scraper.session.get(url, timeout=10.0)
                    if response.status_code == 200:
                        results.append(
                            f"✅ <b>1TamilMV:</b> {escape(main_domain)} (accessible)"
                        )
                    else:
                        results.append(
                            f"⚠️ <b>1TamilMV:</b> {escape(main_domain)} (HTTP {response.status_code})"
                        )
                except Exception:
                    results.append(
                        f"❌ <b>1TamilMV:</b> {escape(main_domain)} (not accessible)"
                    )
        except Exception as e:
            results.append(f"❌ <b>1TamilMV:</b> Check failed - {escape(str(e))}")

        # Check TamilBlasters main domain
        try:
            async with TamilBlastersScraper() as scraper:
                main_domain = scraper.main_domain
                try:
                    url = f"https://{main_domain}"
                    response = await scraper.session.get(url, timeout=10.0)
                    if response.status_code == 200:
                        results.append(
                            f"✅ <b>1TamilBlasters:</b> {escape(main_domain)} (accessible)"
                        )
                    else:
                        results.append(
                            f"⚠️ <b>1TamilBlasters:</b> {escape(main_domain)} (HTTP {response.status_code})"
                        )
                except Exception:
                    results.append(
                        f"❌ <b>1TamilBlasters:</b> {escape(main_domain)} (not accessible)"
                    )
        except Exception as e:
            results.append(
                f"❌ <b>1TamilBlasters:</b> Check failed - {escape(str(e))}"
            )

        # Check Movierulz main domain
        try:
            async with MovierulzScraper() as scraper:
                main_domain = scraper.main_domain
                try:
                    url = f"https://{main_domain}"
                    response = await scraper.session.get(url, timeout=10.0)
                    if response.status_code == 200:
                        results.append(
                            f"✅ <b>5Movierulz:</b> {escape(main_domain)} (accessible)"
                        )
                    else:
                        results.append(
                            f"⚠️ <b>5Movierulz:</b> {escape(main_domain)} (HTTP {response.status_code})"
                        )
                except Exception:
                    results.append(
                        f"❌ <b>5Movierulz:</b> {escape(main_domain)} (not accessible)"
                    )
        except Exception as e:
            results.append(f"❌ <b>5Movierulz:</b> Check failed - {escape(str(e))}")

        result_text = (
            "🌐 <b>Main Domains Status:</b>\n\n"
            + "\n".join(results)
            + "\n\n💡 <b>Tip:</b> You can use any working domain variation in your /scrap commands.\n"
            "The scraper will automatically extract and use the domain from your provided URL."
        )

        result_reply = await send_message(message, result_text)

        with contextlib.suppress(Exception):
            await checking_msg.delete()

        # Auto-delete command message and result after a delay
        await asyncio.sleep(2)
        with contextlib.suppress(Exception):
            await message.delete()
        await auto_delete_message(result_reply, time=120)

    except Exception as e:
        error_message = f"❌ <b>Domain check failed:</b> {escape(str(e))}"
        error_reply = await send_message(message, error_message)
        await auto_delete_message(error_reply, time=30)
        LOGGER.error(f"Domain check error: {e!s}")


@new_task
async def scrap_command(_, message):
    """
    Handle /scrap command to scrape movie information from supported sites

    Usage:
    /scrap <movie_url> - Scrape movie info from 1TamilMV, 1TamilBlasters, or 5Movierulz
    /scrap help - Show detailed help
    /scrap domains - Check working domains
    Reply to a message with URL using /scrap - Extract and scrape the URL from replied message
    """
    try:
        # Extract command arguments
        if not message.text:
            await send_message(message, "❌ No command text provided.")
            return

        command_parts = message.text.split(maxsplit=1)
        argument = None

        # Check if there's an argument in the command
        if len(command_parts) >= 2:
            argument = command_parts[1].strip()

        # If no argument provided, check if this is a reply to a message with a link
        if not argument and message.reply_to_message:
            replied_message = message.reply_to_message

            # Check if the replied message has text with URLs
            if replied_message.text:
                # Look for URLs in the replied message text
                url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
                urls = re.findall(url_pattern, replied_message.text)

                if urls:
                    # Use the first URL found
                    potential_url = urls[0]
                    # Add https:// if it starts with www.
                    if potential_url.startswith("www."):
                        potential_url = f"https://{potential_url}"

                    # Check if it's a supported domain
                    parsed_url = urlparse(potential_url)
                    supported_domains = [
                        "1tamilmv",
                        "tamilmv",
                        "1tamilblasters",
                        "tamilblasters",
                        "5movierulz",
                        "movierulz",
                    ]
                    if any(
                        domain in parsed_url.netloc.lower()
                        for domain in supported_domains
                    ):
                        argument = potential_url
                        LOGGER.info(
                            f"Extracted URL from replied message: {argument}"
                        )

        # If still no argument, show help
        if not argument:
            help_text = (
                "🔍 <b>Scrap Command Usage:</b>\n\n"
                "<code>/scrap &lt;movie_url&gt;</code> - Scrape movie information\n"
                "<code>/scrap help</code> - Show detailed help\n"
                "<code>/scrap domains</code> - Check main domains\n\n"
                "<b>Examples:</b>\n"
                "<code>/scrap https://www.1tamilmv.onl/movie-page-url</code>\n"
                "<code>/scrap https://www.1tamilblasters.how/forums/topic/movie-name</code>\n"
                "<code>/scrap https://www.5movierulz.voto/movie-name/watch-online.html</code>\n\n"
                "💡 <b>Tip:</b> You can also reply to a message containing a supported URL with <code>/scrap</code>\n\n"
                "📝 <b>Note:</b> Supports 1TamilMV, 1TamilBlasters, and 5Movierulz domain variations. Just provide the working URL!"
            )
            reply = await send_message(message, help_text)
            await auto_delete_message(reply, time=60)

            # Auto-delete the command message after a brief delay
            await asyncio.sleep(2)
            with contextlib.suppress(Exception):
                await message.delete()
            return

        # Handle help command
        if argument.lower() == "help":
            await show_detailed_help(message)
            return

        # Handle domains command
        if argument.lower() == "domains":
            await check_working_domains(message)
            return

        movie_url = argument

        # Validate URL
        if not movie_url.startswith(("http://", "https://")):
            error_msg = "❌ <b>Invalid URL:</b> Please provide a valid URL starting with http:// or https://"
            reply = await send_message(message, error_msg)
            await auto_delete_message(reply, time=30)

            # Auto-delete the command message after a brief delay
            await asyncio.sleep(2)
            with contextlib.suppress(Exception):
                await message.delete()
            return

        # Check if it's a supported URL
        parsed_url = urlparse(movie_url)
        supported_domains = [
            "1tamilmv",
            "tamilmv",
            "1tamilblasters",
            "tamilblasters",
            "5movierulz",
            "movierulz",
        ]
        if not any(
            domain in parsed_url.netloc.lower() for domain in supported_domains
        ):
            error_msg = (
                "❌ <b>Unsupported URL:</b> Currently supported sites:\n"
                "• 1TamilMV (1tamilmv.*)\n"
                "• 1TamilBlasters (1tamilblasters.*)\n"
                "• 5Movierulz (5movierulz.*)\n\n"
                "Please provide a valid movie page URL from these sites."
            )
            reply = await send_message(message, error_msg)
            await auto_delete_message(reply, time=30)

            # Auto-delete the command message after a brief delay
            await asyncio.sleep(2)
            with contextlib.suppress(Exception):
                await message.delete()
            return

        # Send processing message
        processing_msg = await send_message(
            message, "🔍 <b>Scraping movie information...</b>"
        )

        try:
            # Scrape movie information using universal scraper
            movie_info = await scrape_movie_info(movie_url)

            # Format and send result
            if movie_info:
                formatted_info = format_movie_info(movie_info)
                result_message = f"✅ <b>Movie Information Scraped Successfully!</b>\n\n{formatted_info}"

                await send_message(message, result_message)

                # If magnet links are found, send them in separate messages with individual details
                magnet_details = movie_info.get("magnet_details", [])
                if magnet_details:
                    magnet_messages = format_magnet_links(magnet_details)

                    # Send each message part
                    for magnet_message in magnet_messages:
                        await send_message(message, magnet_message)

                # Auto-delete only the command message after successful extraction
                await asyncio.sleep(2)  # Brief delay to let user see the completion

                # Delete the original command message
                with contextlib.suppress(Exception):
                    await message.delete()

                LOGGER.info(
                    "Auto-deleted command message after successful extraction - results kept visible"
                )

            else:
                error_reply = await send_message(
                    message,
                    "❌ <b>No movie information found.</b> The page might not contain the expected data.",
                )
                # For error messages, use auto_delete_message with timer instead of instant deletion
                await auto_delete_message(error_reply, time=30)

                # Also delete command message for error case
                await asyncio.sleep(2)
                with contextlib.suppress(Exception):
                    await message.delete()

        except Exception as e:
            error_message = f"❌ <b>Scraping failed:</b> {escape(str(e))}"
            error_reply = await send_message(message, error_message)
            # For error messages, use auto_delete_message with timer instead of instant deletion
            await auto_delete_message(error_reply, time=30)
            LOGGER.error(f"Scraping error for URL {movie_url}: {e!s}")

        finally:
            # Delete processing message
            with contextlib.suppress(Exception):
                await processing_msg.delete()

    except Exception as e:
        error_message = f"❌ <b>Command error:</b> {escape(str(e))}"
        error_reply = await send_message(message, error_message)
        await auto_delete_message(error_reply, time=30)

        # Auto-delete the command message after a brief delay
        await asyncio.sleep(2)
        with contextlib.suppress(Exception):
            await message.delete()

        LOGGER.error(f"Scrap command error: {e!s}")
