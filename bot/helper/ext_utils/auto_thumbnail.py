"""
Auto Thumbnail Helper Module
Automatically fetches movie/TV show thumbnails from IMDB and TMDB based on filename metadata
"""

import contextlib
import os
import re

# TMDB functionality moved here from stream_utils
from datetime import datetime, timedelta
from os import path as ospath
from time import time
from typing import ClassVar

import aiohttp
from aiofiles import open as aioopen

from bot import LOGGER
from bot.core.config_manager import Config

# Use compatibility layer for aiofiles
from bot.helper.ext_utils.aiofiles_compat import aiopath, makedirs, remove
from bot.helper.ext_utils.template_processor import extract_metadata_from_filename


class AutoThumbnailHelper:
    """Helper class for automatically fetching thumbnails from IMDB/TMDB"""

    THUMBNAIL_DIR = "thumbnails/auto"
    CACHE_DURATION = 86400  # 24 hours
    MAX_CACHE_SIZE = 100  # Maximum number of cached thumbnails

    @classmethod
    async def get_auto_thumbnail(
        cls, filename: str, user_id: int | None = None, enabled: bool | None = None
    ) -> str | None:
        """
        Get auto thumbnail for a file based on its metadata

        Args:
            filename: The filename to extract metadata from
            user_id: User ID for cache organization (optional)
            enabled: Override for auto thumbnail enabled status (optional)

        Returns:
            Path to downloaded thumbnail or None if not found
        """
        try:
            # Use provided enabled parameter, otherwise fall back to config
            auto_enabled = enabled if enabled is not None else Config.AUTO_THUMBNAIL

            if not auto_enabled:
                return None

            # Extract metadata from filename
            metadata = await extract_metadata_from_filename(filename)
            if not metadata:
                return None

            # Clean title for search
            clean_title = cls._extract_clean_title(filename)
            if not clean_title or len(clean_title) < 3:
                return None

            year = metadata.get("year")
            season = metadata.get("season")
            episode = metadata.get("episode")

            # Determine if it's a TV show or movie
            is_tv_show = bool(season or episode or cls._detect_tv_patterns(filename))

            # Try to get thumbnail from cache first
            cache_key = cls._generate_cache_key(clean_title, year, is_tv_show)
            cached_thumbnail = await cls._get_cached_thumbnail(cache_key)
            if cached_thumbnail:
                return cached_thumbnail

            # Use advanced search strategy with multiple approaches
            thumbnail_url = await cls._advanced_search_strategy(
                clean_title, year, is_tv_show, filename
            )

            if not thumbnail_url:
                return None

            # Download and cache the thumbnail
            thumbnail_path = await cls._download_thumbnail(thumbnail_url, cache_key)
            if thumbnail_path:
                return thumbnail_path

            return None

        except Exception as e:
            LOGGER.error(f"Error getting auto thumbnail for {filename}: {e}")
            return None

    @classmethod
    def _extract_clean_title(cls, filename: str) -> str:
        """Enhanced title extraction with multiple strategies"""
        if not filename:
            return ""

        # Store original for fallback
        original_filename = filename

        # Remove file extension
        title = filename.rsplit(".", 1)[0] if "." in filename else filename

        # Try multiple extraction strategies and return the best one
        strategies = [
            cls._extract_title_strategy_1,  # Conservative cleaning
            cls._extract_title_strategy_2,  # Aggressive cleaning
            cls._extract_title_strategy_3,  # Anime-specific
            cls._extract_title_strategy_4,  # Fallback word-by-word
        ]

        best_title = ""
        best_score = 0

        for strategy in strategies:
            try:
                extracted_title = strategy(title, original_filename)
                score = cls._score_title_quality(extracted_title, original_filename)

                if score > best_score and len(extracted_title.strip()) >= 2:
                    best_title = extracted_title
                    best_score = score

            except Exception:
                continue

        return (
            best_title.strip()
            if best_title
            else cls._extract_title_fallback(original_filename)
        )

    @classmethod
    def _extract_title_strategy_1(cls, title: str, _original: str) -> str:
        """Enhanced conservative cleaning with better title preservation"""
        # Remove website prefixes first
        title = re.sub(
            r"^www\.\w+\.(com|net|org|in|onl|co|tv|me|to|cc|xyz)\s*-\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove common Telegram bot prefixes/suffixes (like @hello, @botname, etc.)
        # Remove prefix patterns like "@word " at the beginning (more flexible)
        title = re.sub(r"^@[\w\-\.]+\s+", "", title)
        # Remove suffix patterns like " @word" at the end (more flexible)
        title = re.sub(r"\s+@[\w\-\.]+$", "", title)
        # Remove multiple @ patterns in case there are several
        title = re.sub(r"@[\w\-\.]+", "", title)

        # Replace separators with spaces
        title = re.sub(r"[._-]+", " ", title)

        # Extract year first (more robust pattern)
        year_match = re.search(r"\b(19|20)\d{2}\b", title)
        year = year_match.group(0) if year_match else None

        # Detect TV show patterns
        tv_patterns = [
            r"\bS\d{1,2}E\d{1,3}\b",  # S01E01
            r"\bSeason\s*\d+\b",  # Season 1
            r"\bEpisode\s*\d+\b",  # Episode 1
            r"\b\d{1,2}x\d{1,3}\b",  # 1x01
        ]

        is_tv_show = False
        for pattern in tv_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                title = title[: match.start()].strip()
                is_tv_show = True
                break

        # Enhanced removal of technical terms and quality indicators
        technical_patterns = [
            r"\s+(720p|1080p|2160p|4k|hd|fhd|uhd|8k)\b.*$",
            r"\s+(x264|x265|h264|h265|hevc|avc|xvid)\b.*$",
            r"\s+(bluray|webrip|web-dl|hdtv|brrip|hdrip|dvdrip)\b.*$",
            r"\s+(aac|ac3|dts|mp3|flac|opus)\b.*$",
            r"\s+(hindi|tamil|telugu|english|dual|multi|dubbed)\b.*$",
            r"\s+(hq|lq|cam|ts|tc|r5|dvdscr)\b.*$",
            r"\s+\d+mb\b.*$",
            r"\s+(esub|subs|subtitle)\b.*$",
        ]

        for pattern in technical_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove bracketed/parenthetical content that looks technical
        title = re.sub(
            r"\s*\[[^\]]*(?:rip|encode|web|hd|quality|group|tam|tel|hin|aac|mb|esub)\s*[^\]]*\]",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"\s*\([^)]*(?:rip|encode|web|hd|quality|group|tam|tel|hin|aac|mb|esub)\s*[^)]*\)",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Clean up spacing and multiple spaces
        title = re.sub(r"\s+", " ", title).strip()

        # Preserve year in parentheses for movies if it exists
        if year and not is_tv_show:
            # Remove standalone year and add it in parentheses if not already there
            if f"({year})" not in title and f" {year}" in title:
                title = re.sub(rf"\s+{re.escape(year)}\s*", " ", title).strip()
                title = f"{title} ({year})"
            elif f"({year})" not in title and f"{year}" in title:
                title = re.sub(rf"\b{re.escape(year)}\b", "", title).strip()
                title = f"{title} ({year})"

        return title

    @classmethod
    def _extract_title_strategy_2(cls, title: str, _original: str) -> str:
        """Aggressive cleaning - remove all technical indicators"""
        # Remove common Telegram bot prefixes/suffixes (like @hello, @botname, etc.)
        # Remove prefix patterns like "@word " at the beginning (more flexible)
        title = re.sub(r"^@[\w\-\.]+\s+", "", title)
        # Remove suffix patterns like " @word" at the end (more flexible)
        title = re.sub(r"\s+@[\w\-\.]+$", "", title)
        # Remove multiple @ patterns in case there are several
        title = re.sub(r"@[\w\-\.]+", "", title)

        # Replace separators
        title = re.sub(r"[._-]+", " ", title)

        # Extract year
        year_match = re.search(r"\b(19|20)\d{2}\b", title)
        year = year_match.group(0) if year_match else None

        # Remove TV show indicators
        tv_patterns = [
            r"\bS\d{1,2}E\d{1,3}.*$",
            r"\bSeason\s*\d+.*$",
            r"\bEpisode\s*\d+.*$",
            r"\b\d{1,2}x\d{1,3}.*$",
        ]

        is_tv_show = False
        for pattern in tv_patterns:
            if re.search(pattern, title, re.IGNORECASE):
                title = re.sub(pattern, "", title, flags=re.IGNORECASE)
                is_tv_show = True
                break

        # Comprehensive technical term removal
        technical_patterns = [
            r"\b(720p|1080p|2160p|4k|uhd|fhd|hd|sd)\b",
            r"\b(bluray|bdrip|brrip|dvdrip|webrip|web-dl|hdtv|pdtv|cam|ts|tc)\b",
            r"\b(x264|x265|h264|h265|hevc|avc|xvid|divx)\b",
            r"\b(aac|ac3|dts|mp3|flac|opus|dd5\.1|atmos)\b",
            r"\b(proper|repack|internal|limited|extended|unrated|directors?\.cut)\b",
            r"\b(amzn|nf|hulu|dsnp|hbo|max|atvp|cr|funimation)\b",
            r"\b(hindi|tamil|telugu|malayalam|english|dubbed|dual|audio|multi)\b",
            r"\b(esub|sub|subtitle|subs)\b",
            r"\[.*?\]",  # All bracketed content
            r"\{.*?\}",  # All braced content
            r"\((?!19|20)\d{2}.*?\)",  # Parentheses except years
        ]

        for pattern in technical_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove release group patterns
        title = re.sub(r"-\w+$", "", title)
        title = re.sub(r"^\w+-", "", title)

        # Clean up
        title = re.sub(r"\s+", " ", title).strip()

        # Add year back for movies
        if year and not is_tv_show and f"({year})" not in title:
            title = re.sub(rf"\b{re.escape(year)}\b", "", title).strip()
            title = f"{title} ({year})"

        return title

    @classmethod
    def _extract_title_strategy_3(cls, title: str, _original: str) -> str:
        """Anime-specific extraction"""
        # Remove common Telegram bot prefixes/suffixes (like @hello, @botname, etc.)
        # Remove prefix patterns like "@word " at the beginning (more flexible)
        title = re.sub(r"^@[\w\-\.]+\s+", "", title)
        # Remove suffix patterns like " @word" at the end (more flexible)
        title = re.sub(r"\s+@[\w\-\.]+$", "", title)
        # Remove multiple @ patterns in case there are several
        title = re.sub(r"@[\w\-\.]+", "", title)

        # Replace separators
        title = re.sub(r"[._-]+", " ", title)

        # Anime-specific patterns
        anime_patterns = [
            r"\s+(ep|episode|ova|ona|special|movie)\s*\d+.*$",
            r"\s+\d{2,3}.*$",  # Episode numbers like "01", "001"
            r"\s+(bd|dvd|tv|web).*$",
            r"\s+(uncensored|censored).*$",
            r"\s+(batch|complete|season).*$",
        ]

        for pattern in anime_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove technical terms but preserve anime-specific terms
        title = re.sub(
            r"\s+(720p|1080p|x264|x265|aac|flac).*$", "", title, flags=re.IGNORECASE
        )

        # Remove bracketed content except if it might be part of title
        title = re.sub(
            r"\s*\[[^\]]*(?:rip|encode|web|bd|dvd)\s*[^\]]*\]",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Clean up
        return re.sub(r"\s+", " ", title).strip()

    @classmethod
    def _extract_title_strategy_4(cls, title: str, _original: str) -> str:
        """Word-by-word fallback strategy"""
        # Remove common Telegram bot prefixes/suffixes (like @hello, @botname, etc.)
        # Remove prefix patterns like "@word " at the beginning (more flexible)
        title = re.sub(r"^@[\w\-\.]+\s+", "", title)
        # Remove suffix patterns like " @word" at the end (more flexible)
        title = re.sub(r"\s+@[\w\-\.]+$", "", title)
        # Remove multiple @ patterns in case there are several
        title = re.sub(r"@[\w\-\.]+", "", title)

        # Replace separators
        title = re.sub(r"[._-]+", " ", title)
        words = title.split()

        # Technical indicators that signal end of title
        stop_indicators = [
            r"^(s\d+e\d+|season|episode|\d{1,2}x\d+)$",
            r"^(720p|1080p|2160p|4k|hd|uhd)$",
            r"^(bluray|webrip|web-dl|hdtv|dvdrip)$",
            r"^(x264|x265|hevc|avc)$",
            r"^(proper|repack|internal|extended)$",
        ]

        title_words = []
        for word in words:
            # Stop at technical indicators
            if any(
                re.match(pattern, word, re.IGNORECASE) for pattern in stop_indicators
            ):
                break

            # Skip obvious technical terms
            if re.match(r"^\d{4}$", word):  # Standalone year
                continue
            if len(word) <= 2 and word.upper() in ["CR", "BD", "TV", "WEB"]:
                continue

            title_words.append(word)

            # Reasonable title length limit
            if len(title_words) >= 6:
                break

        return " ".join(title_words)

    @classmethod
    def _score_title_quality(cls, title: str, _original: str) -> int:
        """Score the quality of extracted title"""
        if not title or len(title.strip()) < 2:
            return 0

        score = 0

        # Length scoring (prefer reasonable lengths)
        length = len(title.strip())
        if 10 <= length <= 50:
            score += 10
        elif 5 <= length <= 80:
            score += 5
        elif length < 5:
            score -= 5

        # Word count scoring
        word_count = len(title.split())
        if 2 <= word_count <= 6:
            score += 8
        elif word_count == 1:
            score += 3
        elif word_count > 8:
            score -= 3

        # Penalize if contains technical terms
        technical_terms = [
            "720p",
            "1080p",
            "x264",
            "x265",
            "bluray",
            "webrip",
            "hdtv",
        ]
        if any(term in title.lower() for term in technical_terms):
            score -= 10

        # Bonus for having year in proper format
        if re.search(r"\(\d{4}\)", title):
            score += 5

        # Bonus for proper capitalization
        if title.istitle() or any(word[0].isupper() for word in title.split()):
            score += 3

        return score

    @classmethod
    def _extract_title_fallback(cls, filename: str) -> str:
        """Last resort title extraction"""
        # Just take the first few words before any obvious technical terms
        title = filename.rsplit(".", 1)[0] if "." in filename else filename

        # Remove common Telegram bot prefixes/suffixes (like @hello, @botname, etc.)
        # Remove prefix patterns like "@word " at the beginning (more flexible)
        title = re.sub(r"^@[\w\-\.]+\s+", "", title)
        # Remove suffix patterns like " @word" at the end (more flexible)
        title = re.sub(r"\s+@[\w\-\.]+$", "", title)
        # Remove multiple @ patterns in case there are several
        title = re.sub(r"@[\w\-\.]+", "", title)

        title = re.sub(r"[._-]+", " ", title)
        words = title.split()[:4]  # Take first 4 words max
        return " ".join(words).strip()

    @classmethod
    async def _advanced_search_strategy(
        cls,
        clean_title: str,
        year: int | None,
        is_tv_show: bool,
        original_filename: str,
    ) -> str | None:
        """Advanced search strategy with multiple approaches and fallbacks"""

        # Generate multiple search variations
        search_variations = cls._generate_search_variations(
            clean_title, year, is_tv_show, original_filename
        )

        # Try TMDB first (better quality images)
        if Config.TMDB_API_KEY and Config.TMDB_ENABLED:
            for _variation_name, search_query, search_year in search_variations:
                thumbnail_url = await cls._get_tmdb_thumbnail(
                    search_query, search_year, is_tv_show
                )

                if thumbnail_url:
                    return thumbnail_url

                # For movies, also try as TV show (anime often categorized as TV)
                if not is_tv_show:
                    thumbnail_url = await cls._get_tmdb_thumbnail(
                        search_query, search_year, True
                    )
                    if thumbnail_url:
                        return thumbnail_url

        # Fallback to IMDB with same variations
        if Config.IMDB_ENABLED:
            for _variation_name, search_query, search_year in search_variations:
                # Format query for IMDB
                imdb_query = (
                    f"{search_query} {search_year}" if search_year else search_query
                )
                thumbnail_url = await cls._get_imdb_thumbnail(
                    imdb_query, search_year
                )

                if thumbnail_url:
                    return thumbnail_url

        # Last resort: Word-by-word and partial search
        thumbnail_url = await cls._desperate_search_strategy(
            clean_title, year, is_tv_show
        )
        if thumbnail_url:
            return thumbnail_url

        return None

    @classmethod
    async def _desperate_search_strategy(
        cls, clean_title: str, year: int | None, is_tv_show: bool
    ) -> str | None:
        """Last resort: try every word and partial combinations"""

        # Generate all possible search terms
        search_terms = cls._generate_desperate_search_terms(clean_title)

        # Try TMDB first with each term
        if Config.TMDB_API_KEY and Config.TMDB_ENABLED:
            for term in search_terms:
                if len(term.strip()) < 3:  # Skip very short terms
                    continue

                # Try as both movie and TV show
                for is_tv in [is_tv_show, not is_tv_show]:
                    thumbnail_url = await cls._get_tmdb_thumbnail(term, year, is_tv)
                    if thumbnail_url:
                        return thumbnail_url

        # Try IMDB with each term
        if Config.IMDB_ENABLED:
            for term in search_terms:
                if len(term.strip()) < 3:  # Skip very short terms
                    continue

                thumbnail_url = await cls._get_imdb_thumbnail(term, year)
                if thumbnail_url:
                    return thumbnail_url

        return None

    @classmethod
    def _generate_desperate_search_terms(cls, title: str) -> list[str]:
        """Generate all possible search terms from title"""
        terms = []
        words = title.split()

        # Remove common stop words that don't help with search
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
        }
        meaningful_words = [
            word
            for word in words
            if word.lower() not in stop_words and len(word) > 2
        ]

        # 1. Individual meaningful words (most important)
        for word in meaningful_words:
            if word not in terms:
                terms.append(word)

        # 2. Two-word combinations
        for i in range(len(meaningful_words) - 1):
            combo = f"{meaningful_words[i]} {meaningful_words[i + 1]}"
            if combo not in terms:
                terms.append(combo)

        # 3. Three-word combinations (if we have enough words)
        if len(meaningful_words) >= 3:
            for i in range(len(meaningful_words) - 2):
                combo = f"{meaningful_words[i]} {meaningful_words[i + 1]} {meaningful_words[i + 2]}"
                if combo not in terms:
                    terms.append(combo)

        # 4. First word + last word combination
        if len(meaningful_words) >= 2:
            first_last = f"{meaningful_words[0]} {meaningful_words[-1]}"
            if first_last not in terms:
                terms.append(first_last)

        # 5. Partial title combinations (first N words)
        for i in range(2, min(len(meaningful_words) + 1, 5)):  # Up to 4 words
            partial = " ".join(meaningful_words[:i])
            if partial not in terms:
                terms.append(partial)

        # 6. Try removing common anime/series suffixes and search again
        title_variants = cls._generate_title_variants(title)
        for variant in title_variants:
            if variant and variant not in terms and len(variant) > 3:
                terms.append(variant)

        # 7. For anime titles, try common romanization alternatives
        if cls._is_likely_anime(title):
            romanization_variants = cls._generate_romanization_variants(title)
            for variant in romanization_variants:
                if variant and variant not in terms and len(variant) > 3:
                    terms.append(variant)

        # 8. Try the original title without any processing
        if title not in terms:
            terms.append(title)

        # Sort by length (longer terms first, as they're more specific)
        terms.sort(key=len, reverse=True)

        # Limit to reasonable number to avoid too many requests
        return terms[:15]

    @classmethod
    def _generate_title_variants(cls, title: str) -> list[str]:
        """Generate title variants by removing common suffixes/prefixes"""
        variants = []

        # Remove common prefixes
        prefixes_to_remove = [
            r"^(the|a|an)\s+",
            r"^(new|old)\s+",
        ]

        for prefix_pattern in prefixes_to_remove:
            variant = re.sub(prefix_pattern, "", title, flags=re.IGNORECASE).strip()
            if variant and variant != title:
                variants.append(variant)

        # Remove common suffixes
        suffixes_to_remove = [
            r"\s+(series|show|anime|movie|film)$",
            r"\s+(season|s)\s*\d+.*$",
            r"\s+(part|vol|volume)\s*\d+.*$",
            r"\s+(tv|ova|ona)$",
        ]

        for suffix_pattern in suffixes_to_remove:
            variant = re.sub(suffix_pattern, "", title, flags=re.IGNORECASE).strip()
            if variant and variant != title:
                variants.append(variant)

        # Try with different word separators
        if " " in title:
            # Try without spaces (for compound titles)
            no_space = title.replace(" ", "")
            if len(no_space) > 5:  # Only if reasonably long
                variants.append(no_space)

            # Try with different separators
            variants.append(title.replace(" ", "-"))
            variants.append(title.replace(" ", "_"))

        return variants

    @classmethod
    def _generate_romanization_variants(cls, title: str) -> list[str]:
        """Generate romanization variants for anime titles"""
        variants = []

        # Common romanization transformations
        transformations = [
            # Long vowel variations
            (r"ou", "o"),  # Shounen -> Shonen
            (r"oo", "o"),  # Dragonball -> Dragonbal
            (r"uu", "u"),  # Yuugi -> Yugi
            (r"aa", "a"),  # Naato -> Nato
            (r"ii", "i"),  # Shiina -> Shina
            (r"ee", "e"),  # Keeko -> Keko
            # Particle variations
            (r"\bwo\b", "o"),  # wo -> o
            (r"\bwa\b", "ha"),  # wa -> ha (sometimes)
            # Common consonant variations
            (r"tsu", "tu"),  # Natsu -> Natu
            (r"chi", "ti"),  # Machi -> Mati
            (r"shi", "si"),  # Shiro -> Siro
            (r"ji", "zi"),  # Jiro -> Ziro
            (r"fu", "hu"),  # Fuji -> Huji
            # Double consonant variations
            (r"kk", "k"),  # Rokka -> Roka
            (r"pp", "p"),  # Nippon -> Nipon
            (r"tt", "t"),  # Natto -> Nato
            (r"ss", "s"),  # Kissu -> Kisu
            # 'n' variations
            (r"n'", "n"),  # Shin'ya -> Shinya
            (r"nb", "mb"),  # Shinbun -> Shimbun
            (r"np", "mp"),  # Shinpai -> Shimpai
            # Reverse some transformations too
            (r"o", "ou"),  # Shonen -> Shounen
            (r"u", "uu"),  # Yugi -> Yuugi
        ]

        current_variants = [title]

        # Apply transformations
        for pattern, replacement in transformations:
            new_variants = []
            for variant in current_variants:
                new_variant = re.sub(
                    pattern, replacement, variant, flags=re.IGNORECASE
                )
                if new_variant != variant and new_variant not in current_variants:
                    new_variants.append(new_variant)
            current_variants.extend(new_variants)

        # Remove duplicates and original title
        variants = [v for v in current_variants if v != title and v not in variants]

        # Add common anime title patterns
        words = title.split()
        if len(words) >= 2:
            # Try without particles
            no_particles = []
            for word in words:
                if word.lower() not in [
                    "no",
                    "wa",
                    "ga",
                    "wo",
                    "ni",
                    "de",
                    "to",
                    "ka",
                    "na",
                ]:
                    no_particles.append(word)

            if len(no_particles) != len(words) and len(no_particles) > 0:
                variants.append(" ".join(no_particles))

        return variants[:10]  # Limit variants

    @classmethod
    def _is_likely_anime(cls, title: str) -> bool:
        """Enhanced anime detection with more comprehensive patterns"""
        anime_indicators = [
            # Explicit anime terms
            r"\b(anime|manga|ova|ona|special|movie)\b",
            r"\b(episode|ep)\s*\d+\b",
            r"\b(season|s)\d+\b",
            # Japanese romanization patterns (common particles and words)
            r"\b(no|wa|ga|wo|ni|de|to|ka|na|da|desu|masu|chan|kun|san|sama)\b",
            r"\b(senpai|kouhai|sensei|onii|onee|imouto|oniisan|oneechan)\b",
            # Common anime title patterns
            r"\b(shippuden|kai|brotherhood|alchemist|titan|hero|academia|slayer|hunter)\b",
            r"\b(dragon|ball|piece|naruto|bleach|attack|death|note|fullmetal)\b",
            r"\b(my|boku|watashi|ore|kimi|anata)\b.*\b(hero|academia|love|story|life)\b",
            # Anime-specific suffixes and formats
            r"\b(tv|bd|dvd)\b.*\d+",
            r"\b(batch|complete|collection)\b",
            r"\b(sub|dub|raw)\b",
            # Japanese naming patterns
            r"[A-Za-z]+\s+(no|wa|ga|wo|ni|de|to)\s+[A-Za-z]+",
            # Common anime studios/sources
            r"\b(studio|toei|madhouse|bones|wit|mappa|pierrot|sunrise)\b",
            r"\b(crunchyroll|funimation|aniplex|viz)\b",
        ]

        # Check for multiple indicators (stronger confidence)
        matches = sum(
            1
            for pattern in anime_indicators
            if re.search(pattern, title, re.IGNORECASE)
        )

        # Also check filename patterns that suggest anime
        filename_patterns = [
            r"\[.*\].*\[.*\]",  # Multiple brackets (common in anime releases)
            r"_\d{2,3}_",  # Episode numbers with underscores
            r"\.S\d+E\d+\.",  # Season/Episode format
        ]

        filename_matches = sum(
            1 for pattern in filename_patterns if re.search(pattern, title)
        )

        return matches >= 2 or filename_matches >= 1

    @classmethod
    def _generate_search_variations(
        cls,
        clean_title: str,
        year: int | None,
        is_tv_show: bool,
        original_filename: str,
    ) -> list[tuple[str, str, int | None]]:
        """Generate multiple search variations for better matching"""
        variations = []

        # Variation 1: Original clean title
        variations.append(("original", clean_title, year))

        # Variation 2: Remove year from title if present
        title_no_year = re.sub(r"\s*\(\d{4}\)\s*", "", clean_title).strip()
        if title_no_year != clean_title:
            variations.append(("no_year", title_no_year, year))

        # Variation 3: For TV shows, extract main series name
        if is_tv_show:
            main_title = re.split(
                r"\s+S\d+E\d+|\s+Season|\s+Episode|\s+\d{1,2}x\d+",
                clean_title,
                flags=re.IGNORECASE,
            )[0].strip()
            if main_title and main_title != clean_title:
                variations.append(("main_series", main_title, year))

        # Variation 4: Remove common words that might interfere
        simplified_title = cls._simplify_title(clean_title)
        if simplified_title != clean_title:
            variations.append(("simplified", simplified_title, year))

        # Variation 5: Try with alternative title extraction from original filename
        alt_title = cls._extract_alternative_title(original_filename)
        if alt_title and alt_title != clean_title:
            variations.append(("alternative", alt_title, year))

        # Variation 6: For anime, try multiple anime-specific variations
        if cls._is_likely_anime(clean_title):
            anime_title = cls._clean_anime_title(clean_title)
            if anime_title != clean_title:
                variations.append(("anime_clean", anime_title, year))

            # Add multiple anime variations
            anime_variations = cls._generate_anime_search_variations(
                anime_title or clean_title
            )
            for i, anime_var in enumerate(
                anime_variations[1:], 1
            ):  # Skip first (original)
                variations.append((f"anime_var_{i}", anime_var, year))

        # Variation 7: Try first few words only (for very long titles)
        words = clean_title.split()
        if len(words) > 4:
            short_title = " ".join(words[:3])
            variations.append(("short", short_title, year))

        # Variation 8: Try without year entirely
        if year:
            variations.append(("no_year_param", title_no_year, None))

        return variations

    @classmethod
    def _simplify_title(cls, title: str) -> str:
        """Remove common words that might interfere with search"""
        # Words that often cause search issues
        interfering_words = [
            r"\bThe\b",
            r"\bA\b",
            r"\bAn\b",  # Articles
            r"\bPart\b",
            r"\bVolume\b",
            r"\bVol\b",  # Parts
            r"\bExtended\b",
            r"\bDirectors?\b",
            r"\bCut\b",  # Versions
            r"\bRemastered\b",
            r"\bSpecial\b",
            r"\bEdition\b",
        ]

        simplified = title
        for word_pattern in interfering_words:
            simplified = re.sub(word_pattern, "", simplified, flags=re.IGNORECASE)

        return re.sub(r"\s+", " ", simplified).strip()

    @classmethod
    def _extract_alternative_title(cls, filename: str) -> str:
        """Extract alternative title using different approach"""
        # Try to extract title by looking for patterns
        title = filename.rsplit(".", 1)[0] if "." in filename else filename

        # Look for title in brackets or parentheses (might be alternative name)
        bracket_match = re.search(r"\[([^\]]+)\]", title)
        if bracket_match:
            bracket_title = bracket_match.group(1)
            # Check if it looks like a title (not technical info)
            if not re.search(
                r"\d{3,4}p|x264|x265|bluray|webrip", bracket_title, re.IGNORECASE
            ):
                return bracket_title.strip()

        # Try extracting by stopping at first technical indicator
        words = re.sub(r"[._-]+", " ", title).split()
        title_words = []

        for word in words:
            if re.match(
                r"(s\d+e\d+|\d{3,4}p|x264|x265|season|episode)", word, re.IGNORECASE
            ):
                break
            title_words.append(word)

        return " ".join(title_words).strip()

    @classmethod
    def _clean_anime_title(cls, title: str) -> str:
        """Enhanced anime title cleaning with better pattern recognition"""
        cleaned = title

        # Remove anime-specific episode/season patterns
        anime_patterns = [
            r"\s+(season|s)\s*\d+.*$",
            r"\s+(part|cour|arc)\s*\d+.*$",
            r"\s+(ova|ona|special|movie|film).*$",
            r"\s+(ep|episode)\s*\d+.*$",
            r"\s+\d{1,3}(?:\s*-\s*\d{1,3})?.*$",  # Episode numbers and ranges
            r"\s+(tv|bd|dvd|web).*$",
            r"\s+(batch|complete|collection).*$",
            r"\s+(sub|dub|raw|eng|jap).*$",
        ]

        for pattern in anime_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Remove common anime release group patterns
        cleaned = re.sub(r"\[.*?\]", "", cleaned)  # Remove all bracketed content
        cleaned = re.sub(r"\{.*?\}", "", cleaned)  # Remove all braced content

        # Clean up spacing
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def _generate_anime_search_variations(cls, title: str) -> list[str]:
        """Generate anime-specific search variations"""
        variations = [title]

        # Common anime title transformations
        transformations = [
            # Remove common prefixes/suffixes
            (r"^(the|a|an)\s+", ""),
            (r"\s+(anime|series|tv|show)$", ""),
            # Japanese romanization alternatives
            (r"\bou\b", "o"),  # ou -> o
            (r"\boo\b", "o"),  # oo -> o
            (r"\buu\b", "u"),  # uu -> u
            (r"wo", "o"),  # wo -> o
            (r"wo", "wo"),  # Keep wo as is
            # Common anime word variations
            (r"\bno\b", ""),  # Remove particle "no"
            (r"\bwa\b", ""),  # Remove particle "wa"
            (r"\bga\b", ""),  # Remove particle "ga"
            # Number format variations
            (r"\b(\d+)\b", r"0\1"),  # Add leading zero to numbers
            (r"\b0(\d{2,})\b", r"\1"),  # Remove leading zero from multi-digit
        ]

        for pattern, replacement in transformations:
            variant = re.sub(
                pattern, replacement, title, flags=re.IGNORECASE
            ).strip()
            if variant and variant != title and variant not in variations:
                variations.append(variant)

        # Try with different spacing
        no_space_variant = title.replace(" ", "")
        if len(no_space_variant) > 3:
            variations.append(no_space_variant)

        # Try with different word orders (for titles with particles)
        words = title.split()
        if len(words) >= 3 and any(
            word.lower() in ["no", "wa", "ga", "wo", "ni", "de", "to"]
            for word in words
        ):
            # Try moving particles to different positions
            for i, word in enumerate(words):
                if word.lower() in ["no", "wa", "ga"]:
                    # Try without the particle
                    variant_words = words[:i] + words[i + 1 :]
                    variant = " ".join(variant_words)
                    if variant not in variations:
                        variations.append(variant)

        return variations[:5]  # Limit to 5 variations to avoid too many requests

    @classmethod
    def _detect_tv_patterns(cls, filename: str) -> bool:
        """Detect if filename indicates a TV show"""
        if not filename:
            return False

        tv_patterns = [
            r"S\d{1,2}E\d{1,3}",  # S01E01
            r"Season\s*\d+",  # Season 1
            r"Episode\s*\d+",  # Episode 1
            r"\d{1,2}x\d{1,3}",  # 1x01
        ]

        return any(
            re.search(pattern, filename, re.IGNORECASE) for pattern in tv_patterns
        )

    @classmethod
    async def _get_tmdb_thumbnail(
        cls, title: str, year: int | None = None, is_tv_show: bool = False
    ) -> str | None:
        """Enhanced TMDB thumbnail search with better result selection"""
        try:
            # Convert year to int if it's a string
            if year is not None and isinstance(year, str):
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None

            if is_tv_show:
                result = await TMDBHelper.search_tv_show_enhanced(title, year)
            else:
                result = await TMDBHelper.search_movie_enhanced(title, year)

            if result and result.get("poster_path"):
                return TMDBHelper.get_poster_url(result["poster_path"], "w500")

            return None

        except Exception as e:
            LOGGER.error(f"Error getting TMDB thumbnail for {title}: {e}")
            return None

    @classmethod
    async def _get_imdb_thumbnail(
        cls, title: str, year: int | None = None
    ) -> str | None:
        """Get thumbnail URL from IMDB"""
        try:
            # Dynamic import to avoid circular imports
            from bot.modules.imdb import get_poster

            # Clean title for IMDB search (remove parentheses with year)
            clean_search_title = re.sub(r"\s*\(\d{4}\)\s*", "", title).strip()

            # Use the existing IMDB helper
            search_query = (
                f"{clean_search_title} {year}" if year else clean_search_title
            )
            imdb_data = await get_poster(search_query, False, False)

            if imdb_data and imdb_data.get("poster"):
                return imdb_data["poster"]

            return None

        except Exception as e:
            LOGGER.error(f"Error getting IMDB thumbnail for {title}: {e}")
            return None

    @classmethod
    def _generate_cache_key(
        cls, title: str, year: int | None = None, is_tv_show: bool = False
    ) -> str:
        """Generate cache key for thumbnail"""
        key_parts = [title.lower().replace(" ", "_")]
        if year:
            key_parts.append(str(year))
        if is_tv_show:
            key_parts.append("tv")
        else:
            key_parts.append("movie")

        return "_".join(key_parts)

    @classmethod
    async def _get_cached_thumbnail(cls, cache_key: str) -> str | None:
        """Get cached thumbnail if it exists and is not expired"""
        try:
            await makedirs(cls.THUMBNAIL_DIR, exist_ok=True)
            cache_file = ospath.join(cls.THUMBNAIL_DIR, f"{cache_key}.jpg")

            if await aiopath.exists(cache_file):
                # Check if cache is still valid
                file_time = await aiopath.getmtime(cache_file)
                if time() - file_time < cls.CACHE_DURATION:
                    return cache_file
                # Remove expired cache
                await remove(cache_file)

            return None

        except Exception as e:
            LOGGER.error(f"Error checking cached thumbnail: {e}")
            return None

    @classmethod
    async def _download_thumbnail(cls, url: str, cache_key: str) -> str | None:
        """Download thumbnail and save to cache"""
        try:
            await makedirs(cls.THUMBNAIL_DIR, exist_ok=True)
            cache_file = ospath.join(cls.THUMBNAIL_DIR, f"{cache_key}.jpg")

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        async with aioopen(cache_file, "wb") as f:
                            await f.write(content)

                        # Clean up old cache files if needed
                        await cls._cleanup_cache()

                        return cache_file

            return None

        except Exception as e:
            LOGGER.error(f"Error downloading thumbnail from {url}: {e}")
            return None

    @classmethod
    async def _cleanup_cache(cls) -> None:
        """Clean up old cache files to maintain cache size limit"""
        try:
            if not await aiopath.exists(cls.THUMBNAIL_DIR):
                return

            # Get all cache files with their modification times
            cache_files = []

            # Use synchronous os.listdir since aiopath doesn't have iterdir
            try:
                entries = os.listdir(cls.THUMBNAIL_DIR)
                for entry in entries:
                    if entry.endswith(".jpg"):
                        file_path = ospath.join(cls.THUMBNAIL_DIR, entry)
                        if await aiopath.exists(file_path):
                            mtime = await aiopath.getmtime(file_path)
                            cache_files.append((file_path, mtime))
            except OSError:
                # Directory doesn't exist or can't be read
                return

            # Sort by modification time (oldest first)
            cache_files.sort(key=lambda x: x[1])

            # Remove oldest files if cache size exceeds limit
            if len(cache_files) > cls.MAX_CACHE_SIZE:
                files_to_remove = cache_files[: -cls.MAX_CACHE_SIZE]
                for file_path, _ in files_to_remove:
                    await remove(file_path)
        except Exception as e:
            LOGGER.error(f"Error cleaning up thumbnail cache: {e}")


class TMDBHelper:
    """TMDB API Helper for fetching movie and TV show metadata"""

    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

    # Cache for TMDB data
    _cache: ClassVar[dict] = {}
    _cache_timestamps: ClassVar[dict] = {}

    @classmethod
    async def search_movie_enhanced(
        cls, title: str, year: int | None = None
    ) -> dict | None:
        """Enhanced movie search with better result selection"""
        try:
            # Validate title input
            if not title or not isinstance(title, str) or len(title.strip()) < 2:
                LOGGER.warning(f"Invalid title for movie search: '{title}'")
                return None

            title = title.strip()

            # Convert year to int if it's a string
            if year is not None and isinstance(year, str):
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None

            # Try multiple search approaches
            search_results = []

            # Primary search
            primary_result = await cls.search_movie(title, year)
            if primary_result:
                score = cls._score_search_result(primary_result, title, year, False)
                search_results.append((primary_result, score, "primary"))

            # Search without year if year was provided
            if year:
                no_year_result = await cls.search_movie(title, None)
                if no_year_result and no_year_result != primary_result:
                    score = cls._score_search_result(
                        no_year_result, title, year, False
                    )
                    search_results.append((no_year_result, score, "no_year"))

            # Multi-search (searches across movies, TV, and people)
            multi_result = await cls._multi_search(title, year)
            if multi_result and multi_result.get("media_type") == "movie":
                if not any(
                    r[0].get("id") == multi_result.get("id")
                    for r, _, _ in search_results
                ):
                    score = cls._score_search_result(
                        multi_result, title, year, False
                    )
                    search_results.append((multi_result, score, "multi"))

            # Return best result with validation
            if search_results:
                # Sort by score and validate top results
                search_results.sort(key=lambda x: x[1], reverse=True)

                for result, score, method in search_results:
                    # Validate the result before returning
                    if cls._validate_search_result(result, title, year, False):
                        return result
                    LOGGER.warning(
                        f"⚠️ Rejected result via {method} (score: {score}): {result.get('title', 'Unknown')} - failed validation"
                    )

                # If no result passes validation, return the highest scored one with warning
                best_result = search_results[0]
                LOGGER.warning(
                    f"⚠️ Using unvalidated result via {best_result[2]} (score: {best_result[1]}): {best_result[0].get('title', 'Unknown')}"
                )
                return best_result[0]

            return None

        except Exception as e:
            # Better error logging to avoid showing "0" or empty errors
            error_msg = str(e) if e else "Unknown error"
            if not error_msg or error_msg.strip() in ["", "0"]:
                error_msg = f"Empty or invalid error for title: '{title}'"
            LOGGER.error(
                f"Error in enhanced movie search for '{title}': {error_msg}"
            )
            return await cls.search_movie(title, year)  # Fallback to basic search

    @classmethod
    async def search_tv_show_enhanced(
        cls, title: str, year: int | None = None
    ) -> dict | None:
        """Enhanced TV show search with better result selection"""
        try:
            # Validate title input
            if not title or not isinstance(title, str) or len(title.strip()) < 2:
                LOGGER.warning(f"Invalid title for TV search: '{title}'")
                return None

            title = title.strip()

            # Convert year to int if it's a string
            if year is not None and isinstance(year, str):
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None

            # Try multiple search approaches
            search_results = []

            # Primary search
            primary_result = await cls.search_tv_show(title, year)
            if primary_result:
                score = cls._score_search_result(primary_result, title, year, True)
                search_results.append((primary_result, score, "primary"))

            # Search without year if year was provided
            if year:
                no_year_result = await cls.search_tv_show(title, None)
                if no_year_result and no_year_result != primary_result:
                    score = cls._score_search_result(
                        no_year_result, title, year, True
                    )
                    search_results.append((no_year_result, score, "no_year"))

            # Multi-search
            multi_result = await cls._multi_search(title, year)
            if multi_result and multi_result.get("media_type") == "tv":
                if not any(
                    r[0].get("id") == multi_result.get("id")
                    for r, _, _ in search_results
                ):
                    score = cls._score_search_result(multi_result, title, year, True)
                    search_results.append((multi_result, score, "multi"))

            # Return best result with validation
            if search_results:
                # Sort by score and validate top results
                search_results.sort(key=lambda x: x[1], reverse=True)

                for result, score, method in search_results:
                    # Validate the result before returning
                    if cls._validate_search_result(result, title, year, True):
                        return result
                    LOGGER.warning(
                        f"⚠️ Rejected TV result via {method} (score: {score}): {result.get('name', 'Unknown')} - failed validation"
                    )

                # If no result passes validation, return the highest scored one with warning
                best_result = search_results[0]
                LOGGER.warning(
                    f"⚠️ Using unvalidated TV result via {best_result[2]} (score: {best_result[1]}): {best_result[0].get('name', 'Unknown')}"
                )
                return best_result[0]

            return None

        except Exception as e:
            # Better error logging to avoid showing "0" or empty errors
            error_msg = str(e) if e else "Unknown error"
            if not error_msg or error_msg.strip() in ["", "0"]:
                error_msg = f"Empty or invalid error for title: '{title}'"
            LOGGER.error(f"Error in enhanced TV search for '{title}': {error_msg}")
            return await cls.search_tv_show(title, year)  # Fallback to basic search

    @classmethod
    async def _multi_search(cls, title: str, year: int | None = None) -> dict | None:
        """Use TMDB multi-search endpoint for broader results"""
        try:
            if not Config.TMDB_API_KEY:
                return None

            # Convert year to int if it's a string
            if year is not None and isinstance(year, str):
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None

            params = {
                "api_key": Config.TMDB_API_KEY,
                "query": title,
                "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                "include_adult": str(
                    getattr(Config, "TMDB_ADULT_CONTENT", False)
                ).lower(),
            }

            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    f"{cls.BASE_URL}/search/multi", params=params
                ) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if data.get("results"):
                        # Filter and score results
                        for result in data["results"]:
                            media_type = result.get("media_type")
                            if media_type in ["movie", "tv"]:
                                # Check year match if provided
                                if year:
                                    result_year = None
                                    if media_type == "movie":
                                        release_date = result.get("release_date")
                                        if release_date and len(release_date) >= 4:
                                            try:
                                                result_year = int(release_date[:4])
                                            except (ValueError, TypeError):
                                                continue
                                    elif media_type == "tv":
                                        first_air_date = result.get("first_air_date")
                                        if (
                                            first_air_date
                                            and len(first_air_date) >= 4
                                        ):
                                            try:
                                                result_year = int(first_air_date[:4])
                                            except (ValueError, TypeError):
                                                continue

                                    # Allow ±2 years tolerance
                                    if result_year and abs(result_year - year) <= 2:
                                        return result
                                else:
                                    return result

            return None

        except Exception as e:
            LOGGER.error(f"Error in multi-search for '{title}': {e}")
            return None

    @classmethod
    def _score_search_result(
        cls, result: dict, search_title: str, search_year: int | None, is_tv: bool
    ) -> float:
        """Enhanced scoring with strict validation for accurate media matching"""
        score = 0.0

        # Get result title and year
        if is_tv:
            result_title = result.get("name", "")
            result_year = None
            first_air_date = result.get("first_air_date")
            if first_air_date:
                with contextlib.suppress(ValueError, TypeError):
                    result_year = int(first_air_date[:4])
        else:
            result_title = result.get("title", "")
            result_year = None
            release_date = result.get("release_date")
            if release_date:
                with contextlib.suppress(ValueError, TypeError):
                    result_year = int(release_date[:4])

        # Strict title validation first
        if not result_title or len(result_title.strip()) < 2:
            return -100  # Invalid result

        # Enhanced title similarity with multiple approaches
        search_lower = search_title.lower().strip()
        result_lower = result_title.lower().strip()

        # Remove common articles and words for better comparison
        search_clean = cls._normalize_title_for_comparison(search_lower)
        result_clean = cls._normalize_title_for_comparison(result_lower)

        # Exact match (highest priority)
        if search_clean == result_clean:
            score += 150  # Exact match after normalization
        elif search_lower == result_lower:
            score += 140  # Exact match without normalization
        elif search_clean in result_clean or result_clean in search_clean:
            score += 120  # Partial match after normalization
        elif search_lower in result_lower or result_lower in search_lower:
            score += 100  # Partial match without normalization
        else:
            # Advanced word-based similarity
            search_words = set(search_clean.split())
            result_words = set(result_clean.split())

            if search_words and result_words:
                common_words = search_words.intersection(result_words)
                total_words = search_words.union(result_words)

                # Jaccard similarity
                jaccard_similarity = (
                    len(common_words) / len(total_words) if total_words else 0
                )

                # Word overlap percentage
                max_words = max(len(search_words), len(result_words))
                overlap_percentage = (
                    len(common_words) / max_words if max_words > 0 else 0
                )

                # Combined similarity score
                similarity_score = (
                    jaccard_similarity * 0.6 + overlap_percentage * 0.4
                ) * 80
                score += similarity_score

                # Penalty for too few common words
                if len(common_words) < 2 and len(search_words) > 2:
                    score -= 20

        # Strict year validation with type safety
        if search_year and result_year:
            try:
                # Ensure both are integers
                search_year_int = (
                    int(search_year) if isinstance(search_year, str) else search_year
                )
                result_year_int = (
                    int(result_year) if isinstance(result_year, str) else result_year
                )

                year_diff = abs(search_year_int - result_year_int)
                if year_diff == 0:
                    score += 50  # Exact year match (increased weight)
                elif year_diff <= 1:
                    score += 30  # Close year match
                elif year_diff <= 2:
                    score += 15  # Acceptable year match
                elif year_diff <= 5:
                    score -= 10  # Poor year match
                else:
                    score -= 30  # Very poor year match
            except (ValueError, TypeError):
                # If year conversion fails, treat as missing year
                score -= 5
        elif search_year and not result_year:
            score -= 5  # Missing year when expected

        # Language and region validation
        original_language = result.get("original_language", "")
        if original_language:
            # Bonus for English content (more likely to match user searches)
            if original_language == "en":
                score += 8
            # Bonus for Japanese content if anime detected
            elif original_language == "ja" and AutoThumbnailHelper._is_likely_anime(
                search_title
            ):
                score += 12

        # Popularity validation (with stricter thresholds)
        popularity = result.get("popularity", 0)
        if popularity > 100:
            score += 15
        elif popularity > 50:
            score += 10
        elif popularity > 20:
            score += 5
        elif popularity < 5:
            score -= 10  # Penalty for very low popularity

        # Vote average validation
        vote_average = result.get("vote_average", 0)
        vote_count = result.get("vote_count", 0)

        if vote_count > 1000:  # Only trust ratings with sufficient votes
            if vote_average > 8:
                score += 12
            elif vote_average > 7:
                score += 8
            elif vote_average > 6:
                score += 5
        elif vote_count < 50:  # Penalty for very few votes
            score -= 5

        # Poster availability (essential for thumbnails)
        if result.get("poster_path"):
            score += 20
        else:
            score -= 15  # Significant penalty for missing poster

        # Additional validation for TV shows
        if is_tv:
            # Check if it's actually a TV show
            if result.get("first_air_date") and not result.get("release_date"):
                score += 10

            # Bonus for ongoing/completed series
            status = result.get("status", "")
            if status in ["Returning Series", "Ended"]:
                score += 5

        # Additional validation for movies
        else:
            # Check if it's actually a movie
            if result.get("release_date") and not result.get("first_air_date"):
                score += 10

            # Runtime validation for movies
            runtime = result.get("runtime", 0)
            if runtime and runtime > 60:  # Reasonable movie length
                score += 5

        # Final validation: minimum score threshold
        if score < 30:  # If score is too low, it's probably not a good match
            return -50

        return score

    @classmethod
    def _normalize_title_for_comparison(cls, title: str) -> str:
        """Normalize title for better comparison accuracy"""
        # Remove common articles and words
        normalized = title

        # Remove articles at the beginning
        normalized = re.sub(r"^(the|a|an)\s+", "", normalized, flags=re.IGNORECASE)

        # Remove common suffixes
        normalized = re.sub(
            r"\s+(movie|film|series|show|tv)$", "", normalized, flags=re.IGNORECASE
        )

        # Remove year in parentheses
        normalized = re.sub(r"\s*\(\d{4}\)\s*", "", normalized)

        # Remove special characters and extra spaces
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _validate_search_result(
        cls, result: dict, search_title: str, search_year: int | None, is_tv: bool
    ) -> bool:
        """Validate that the search result actually matches what we're looking for"""
        if not result:
            return False

        # Get result title and year
        if is_tv:
            result_title = result.get("name", "")
            result_year = None
            first_air_date = result.get("first_air_date")
            if first_air_date:
                with contextlib.suppress(ValueError, TypeError):
                    result_year = int(first_air_date[:4])
        else:
            result_title = result.get("title", "")
            result_year = None
            release_date = result.get("release_date")
            if release_date:
                with contextlib.suppress(ValueError, TypeError):
                    result_year = int(release_date[:4])

        # Basic validation
        if not result_title or len(result_title.strip()) < 2:
            return False

        # Normalize titles for comparison
        search_clean = cls._normalize_title_for_comparison(search_title.lower())
        result_clean = cls._normalize_title_for_comparison(result_title.lower())

        # Title validation - must have significant overlap
        search_words = set(search_clean.split())
        result_words = set(result_clean.split())

        if search_words and result_words:
            common_words = search_words.intersection(result_words)
            overlap_percentage = len(common_words) / len(search_words)

            # Require at least 50% word overlap for validation
            if overlap_percentage < 0.5:
                return False

        # Year validation - if provided, must be within reasonable range
        if search_year and result_year:
            try:
                # Ensure both are integers for comparison
                search_year_int = (
                    int(search_year) if isinstance(search_year, str) else search_year
                )
                result_year_int = (
                    int(result_year) if isinstance(result_year, str) else result_year
                )

                year_diff = abs(search_year_int - result_year_int)
                if year_diff > 3:  # Allow max 3 years difference
                    return False
            except (ValueError, TypeError):
                # If year conversion fails, skip year validation
                pass

        # Media type validation
        if is_tv:
            # For TV shows, should have first_air_date
            if not result.get("first_air_date"):
                return False
        # For movies, should have release_date
        elif not result.get("release_date"):
            return False

        # Poster validation - essential for thumbnails
        if not result.get("poster_path"):
            return False

        # Popularity validation - avoid very obscure results
        popularity = result.get("popularity", 0)
        if popularity < 1:  # Too obscure
            return False

        return True

    @classmethod
    async def search_movie(cls, title: str, year: int | None = None) -> dict | None:
        """Search for a movie by title and optional year"""
        try:
            if not Config.TMDB_API_KEY:
                LOGGER.warning("TMDB API key not configured")
                return None

            # Clean title for better search results
            clean_title = cls._clean_title(title)

            # Check cache first
            cache_key = f"search_movie_{clean_title}_{year}"
            if cls._is_cached(cache_key):
                return cls._cache[cache_key]

            # Check if TMDB API key is available
            if not hasattr(Config, "TMDB_API_KEY") or not Config.TMDB_API_KEY:
                LOGGER.error("❌ TMDB_API_KEY not found in configuration")
                return None

            params = {
                "api_key": Config.TMDB_API_KEY,
                "query": clean_title,
                "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                "include_adult": str(
                    getattr(Config, "TMDB_ADULT_CONTENT", False)
                ).lower(),
            }

            if year:
                params["year"] = year

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{cls.BASE_URL}/search/movie", params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            result = data["results"][0]  # Get first result
                            cls._cache_result(cache_key, result)
                            return result
                        # Try alternative search strategies for anime/niche content
                        return await cls._try_alternative_movie_search(
                            title, year, session, original_title=title
                        )
                    LOGGER.warning(
                        f"❌ TMDB API error {response.status} for movie search: {clean_title}"
                    )
                    if response.status == 401:
                        LOGGER.error("❌ TMDB API key is invalid or missing")

            return None

        except Exception as e:
            LOGGER.error(f"Error searching movie '{title}': {e}")
            return None

    @classmethod
    async def search_tv_show(
        cls, title: str, year: int | None = None
    ) -> dict | None:
        """Search for a TV show by title and optional year"""
        try:
            if not Config.TMDB_API_KEY:
                LOGGER.warning("TMDB API key not configured")
                return None

            # Clean title for better search results
            clean_title = cls._clean_title(title)

            # Check cache first
            cache_key = f"search_tv_{clean_title}_{year}"
            if cls._is_cached(cache_key):
                return cls._cache[cache_key]

            # Check if TMDB API key is available
            if not hasattr(Config, "TMDB_API_KEY") or not Config.TMDB_API_KEY:
                LOGGER.error("❌ TMDB_API_KEY not found in configuration")
                return None

            params = {
                "api_key": Config.TMDB_API_KEY,
                "query": clean_title,
                "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                "include_adult": str(
                    getattr(Config, "TMDB_ADULT_CONTENT", False)
                ).lower(),
            }

            if year:
                params["first_air_date_year"] = year

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{cls.BASE_URL}/search/tv", params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            result = data["results"][0]  # Get first result
                            cls._cache_result(cache_key, result)
                            return result
                        # Try alternative search strategies for anime/niche content
                        return await cls._try_alternative_tv_search(
                            title, year, session, original_title=title
                        )
                    LOGGER.warning(
                        f"❌ TMDB API error {response.status} for TV search: {clean_title}"
                    )
                    if response.status == 401:
                        LOGGER.error("❌ TMDB API key is invalid or missing")

            return None

        except Exception as e:
            LOGGER.error(f"Error searching TV show '{title}': {e}")
            return None

    @classmethod
    def get_poster_url(cls, poster_path: str, size: str = "w500") -> str:
        """Get full poster URL from TMDB poster path"""
        if not poster_path:
            return ""
        return f"{cls.IMAGE_BASE_URL}/{size}{poster_path}"

    @classmethod
    def get_backdrop_url(cls, backdrop_path: str, size: str = "original") -> str:
        """Get full backdrop URL from TMDB backdrop path"""
        if not backdrop_path:
            return ""
        return f"{cls.IMAGE_BASE_URL}/{size}{backdrop_path}"

    @classmethod
    def _clean_title(cls, title: str) -> str:
        """Enhanced title cleaning for better search results"""
        if not title:
            return ""

        # Store original for fallback
        original_title = title

        # Remove file extensions
        title = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", title)

        # Remove common Telegram bot prefixes/suffixes (like @hello, @botname, etc.)
        # Remove prefix patterns like "@word " at the beginning (more flexible)
        title = re.sub(r"^@[\w\-\.]+\s+", "", title)
        # Remove suffix patterns like " @word" at the end (more flexible)
        title = re.sub(r"\s+@[\w\-\.]+$", "", title)
        # Remove multiple @ patterns in case there are several
        title = re.sub(r"@[\w\-\.]+", "", title)

        # Replace dots, underscores, and dashes with spaces first
        title = re.sub(r"[._-]+", " ", title)

        # Remove quality indicators (more comprehensive)
        quality_patterns = [
            r"\b(720p|1080p|2160p|4k|hd|uhd|bluray|brrip|webrip|web-dl|dvdrip|hdtv|cam|ts|tc)\b",
            r"\b(x264|x265|h264|h265|hevc|avc|xvid|divx)\b",
            r"\b(aac|ac3|dts|mp3|flac|dd5\.1|dd\+|atmos)\b",
            r"\b(hindi|tamil|telugu|malayalam|kannada|bengali|punjabi|gujarati|marathi)\b",
            r"\b(dubbed|dual|audio|multi|eng|english)\b",
            r"\b(esub|sub|subtitle|subs)\b",
            r"\b(rip|encode|repack|proper|real|extended|unrated|directors?\.cut)\b",
            r"\b(season|episode|s\d+|e\d+|\d+x\d+)\b",
        ]
        for pattern in quality_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove brackets and their contents (but preserve main title)
        title = re.sub(r"\[.*?\]", "", title)
        title = re.sub(r"\{.*?\}", "", title)

        # Handle parentheses more carefully - keep year if present
        re.search(r"\((\d{4})\)", title)
        title = re.sub(r"\(.*?\)", "", title)

        # Remove common release group patterns
        title = re.sub(r"-\w+$", "", title)
        title = re.sub(r"^\w+-", "", title)  # Remove prefix groups

        # Remove episode/season indicators for anime
        title = re.sub(
            r"\s+(ep|episode|ova|ona|special)\s*\d+.*$",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Clean up whitespace and special characters
        title = re.sub(r"\s+", " ", title)
        title = title.strip()

        # If title becomes too short or empty, try a simpler approach
        if len(title) < 3:
            # Fallback: just remove file extension and basic cleaning
            title = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", original_title)
            title = re.sub(r"[._-]+", " ", title)
            title = re.sub(r"\s+", " ", title).strip()

        return title

    @classmethod
    def _is_cached(cls, cache_key: str) -> bool:
        """Check if data is cached and not expired"""
        if cache_key not in cls._cache:
            return False

        # Check if cache is expired (24 hours)
        cache_time = cls._cache_timestamps.get(cache_key)
        if not cache_time:
            return False

        return datetime.now() - cache_time < timedelta(hours=24)

    @classmethod
    def _cache_result(cls, cache_key: str, result: dict):
        """Cache the result with timestamp"""
        cls._cache[cache_key] = result
        cls._cache_timestamps[cache_key] = datetime.now()

        # Clean old cache entries (keep only last 1000)
        if len(cls._cache) > 1000:
            # Remove oldest 100 entries
            oldest_keys = sorted(
                cls._cache_timestamps.keys(), key=lambda k: cls._cache_timestamps[k]
            )[:100]
            for key in oldest_keys:
                cls._cache.pop(key, None)
                cls._cache_timestamps.pop(key, None)

    @classmethod
    async def _try_alternative_movie_search(
        cls, title: str, year: int | None, session, original_title: str | None = None
    ) -> dict | None:
        """Enhanced alternative search strategies for anime/niche content"""
        try:
            search_attempts = []

            # Strategy 1: Try with original filename (minimal cleaning)
            if original_title and original_title != title:
                minimal_clean = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", original_title)
                # Remove common Telegram bot prefixes/suffixes (more flexible)
                minimal_clean = re.sub(r"^@[\w\-\.]+\s+", "", minimal_clean)
                minimal_clean = re.sub(r"\s+@[\w\-\.]+$", "", minimal_clean)
                minimal_clean = re.sub(r"@[\w\-\.]+", "", minimal_clean)
                minimal_clean = re.sub(r"[._-]+", " ", minimal_clean).strip()
                search_attempts.append(("original filename", minimal_clean))

            # Strategy 2: Search with just the main title (remove episode info)
            main_title = re.sub(r"\s+S\d+E\d+.*", "", title, flags=re.IGNORECASE)
            main_title = re.sub(r"\s+Episode.*", "", main_title, flags=re.IGNORECASE)
            main_title = re.sub(
                r"\s+\d+.*", "", main_title
            )  # Remove trailing numbers
            search_attempts.append(("main title", main_title))

            # Strategy 3: Try first few words only (for long titles)
            words = title.split()
            if len(words) > 3:
                short_title = " ".join(words[:3])
                search_attempts.append(("short title", short_title))

            # Try each search strategy
            for _strategy_name, search_title in search_attempts:
                if not search_title or len(search_title.strip()) < 2:
                    continue

                params = {
                    "api_key": Config.TMDB_API_KEY,
                    "query": search_title,
                    "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                    "include_adult": str(
                        getattr(Config, "TMDB_ADULT_CONTENT", False)
                    ).lower(),
                }
                if year:
                    params["year"] = year

                async with session.get(
                    f"{cls.BASE_URL}/search/movie", params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            return data["results"][0]

            # Strategy 2: Try as TV show instead (anime often categorized as TV)
            tv_result = await cls.search_tv_show(main_title, year)
            if tv_result:
                return tv_result

            return None

        except Exception as e:
            LOGGER.error(f"Error in alternative movie search: {e}")
            return None

    @classmethod
    async def _try_alternative_tv_search(
        cls, title: str, year: int | None, session, original_title: str | None = None
    ) -> dict | None:
        """Enhanced alternative search strategies for anime/niche TV content"""
        try:
            search_attempts = []

            # Strategy 1: Try with original filename (minimal cleaning)
            if original_title and original_title != title:
                minimal_clean = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", original_title)
                # Remove common Telegram bot prefixes/suffixes (more flexible)
                minimal_clean = re.sub(r"^@[\w\-\.]+\s+", "", minimal_clean)
                minimal_clean = re.sub(r"\s+@[\w\-\.]+$", "", minimal_clean)
                minimal_clean = re.sub(r"@[\w\-\.]+", "", minimal_clean)
                minimal_clean = re.sub(r"[._-]+", " ", minimal_clean).strip()
                search_attempts.append(("original filename", minimal_clean))

            # Strategy 2: Search with just the main title (remove episode info)
            main_title = re.sub(r"\s+S\d+E\d+.*", "", title, flags=re.IGNORECASE)
            main_title = re.sub(r"\s+Episode.*", "", main_title, flags=re.IGNORECASE)
            main_title = re.sub(
                r"\s+\d+.*", "", main_title
            )  # Remove trailing numbers
            search_attempts.append(("main title", main_title))

            # Strategy 3: Try first few words only (for long titles)
            words = title.split()
            if len(words) > 3:
                short_title = " ".join(words[:3])
                search_attempts.append(("short title", short_title))

            # Try each search strategy
            for _strategy_name, search_title in search_attempts:
                if not search_title or len(search_title.strip()) < 2:
                    continue

                params = {
                    "api_key": Config.TMDB_API_KEY,
                    "query": search_title,
                    "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                    "include_adult": str(
                        getattr(Config, "TMDB_ADULT_CONTENT", False)
                    ).lower(),
                }
                if year:
                    params["first_air_date_year"] = year

                async with session.get(
                    f"{cls.BASE_URL}/search/tv", params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            return data["results"][0]

            return None

        except Exception as e:
            LOGGER.error(f"Error in alternative TV search: {e}")
            return None

    @classmethod
    def _extract_enhanced_metadata(cls, filename: str) -> dict:
        """Enhanced metadata extraction with better title parsing"""
        try:
            # Use existing metadata extraction as base
            metadata = extract_metadata_from_filename(filename)
            if not metadata:
                metadata = {}

            # Enhanced title extraction with multiple strategies
            clean_title = AutoThumbnailHelper._extract_clean_title(filename)
            if clean_title:
                metadata["title"] = clean_title

            # Enhanced year detection
            year_match = re.search(r"\b(19|20)\d{2}\b", filename)
            if year_match and not metadata.get("year"):
                metadata["year"] = int(year_match.group(0))

            # Enhanced media type detection
            if not metadata.get("type"):
                if AutoThumbnailHelper._detect_tv_patterns(filename):
                    metadata["type"] = "tv"
                elif AutoThumbnailHelper._is_likely_anime(filename):
                    metadata["type"] = "anime"
                else:
                    metadata["type"] = "movie"

            return metadata

        except Exception as e:
            LOGGER.error(f"Error in enhanced metadata extraction: {e}")
            return {}

    @classmethod
    async def _intelligent_media_search(
        cls, title: str, year: int | None, media_type: str
    ) -> dict | None:
        """Intelligent multi-source search with fallbacks and validation"""
        try:
            # Strategy 1: TMDB search with enhanced matching
            if Config.TMDB_API_KEY:
                if media_type in {"tv", "anime"}:
                    result = await cls._enhanced_tv_search(title, year)
                else:
                    result = await cls._enhanced_movie_search(title, year)

                if result and cls._validate_search_result(
                    result, title, year, media_type == "tv"
                ):
                    return result

            # Strategy 2: Multi-search fallback
            if Config.TMDB_API_KEY:
                result = await cls._multi_search(title, year)
                if result and cls._validate_search_result(
                    result, title, year, media_type == "tv"
                ):
                    return result

            # Strategy 3: Alternative search with relaxed criteria
            if media_type in {"tv", "anime"}:
                result = await cls._alternative_tv_search(title, year)
            else:
                result = await cls._alternative_movie_search(title, year)

            if result:
                return result

            return None

        except Exception as e:
            LOGGER.error(f"Error in intelligent media search: {e}")
            return None

    @classmethod
    async def _alternative_movie_search(
        cls, title: str, year: int | None
    ) -> dict | None:
        """Alternative movie search with relaxed matching"""
        try:
            if not Config.TMDB_API_KEY:
                return None

            # Generate search variations
            search_variations = [
                title,
                cls._normalize_title_for_comparison(title),
                title.replace(":", ""),
                title.replace("&", "and"),
                " ".join(title.split()[:3]),  # First 3 words
            ]

            async with aiohttp.ClientSession() as session:
                for search_title in search_variations:
                    if not search_title or len(search_title.strip()) < 2:
                        continue

                    params = {
                        "api_key": Config.TMDB_API_KEY,
                        "query": search_title,
                        "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                        "include_adult": str(
                            getattr(Config, "TMDB_ADULT_CONTENT", False)
                        ).lower(),
                    }

                    if year:
                        params["year"] = year

                    async with session.get(
                        f"{cls.BASE_URL}/search/movie", params=params
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("results"):
                                return data["results"][0]

            return None

        except Exception as e:
            LOGGER.error(f"Error in alternative movie search: {e}")
            return None
