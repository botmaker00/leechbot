"""
TMDB (The Movie Database) API v3 Module
Comprehensive module for fetching movie, TV show, and person information from TMDB
Based on deep understanding of TMDB API v3 documentation
"""

import asyncio
import contextlib
import re
from asyncio import create_task
from datetime import datetime
from time import time
from typing import Any, ClassVar

import aiohttp
from pyrogram.enums import ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)


class TMDBHelper:
    """TMDB API v3 Helper Class with comprehensive functionality"""

    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"

    # Cache for TMDB data
    _cache: ClassVar[dict] = {}
    _cache_timestamps: ClassVar[dict] = {}
    _config_cache: ClassVar[dict] = {}

    # Cache settings
    CACHE_TTL = 3600  # 1 hour (hardcoded)
    MAX_CACHE_SIZE = 200

    @classmethod
    async def _make_request(
        cls, endpoint: str, params: dict | None = None, headers: dict | None = None
    ) -> dict | None:
        """Make authenticated request to TMDB API v3 with proper error handling"""
        if not Config.TMDB_API_KEY:
            LOGGER.error("TMDB API key not configured")
            return None

        # Prepare parameters
        if params is None:
            params = {}

        # Add API key to params (TMDB v3 uses query parameter)
        params["api_key"] = Config.TMDB_API_KEY

        # Add default language if not specified
        if "language" not in params:
            params["language"] = getattr(Config, "TMDB_LANGUAGE", "en-US")

        # Prepare headers
        if headers is None:
            headers = {}

        # Set required headers for TMDB API v3
        headers.update({"accept": "application/json", "User-Agent": "TMDB-Bot/1.0"})

        url = f"{cls.BASE_URL}/{endpoint}"
        cache_key = f"{endpoint}_{sorted(params.items())!s}"

        # Check cache first
        if cache_key in cls._cache:
            cache_time = cls._cache_timestamps.get(cache_key, 0)
            if time() - cache_time < cls.CACHE_TTL:
                return cls._cache[cache_key]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(
                        total=15
                    ),  # Increased timeout for API stability
                ) as response:
                    # Handle different HTTP status codes according to TMDB API specs
                    if response.status == 200:
                        try:
                            data = await response.json()

                            # Validate response structure
                            if not isinstance(data, dict):
                                LOGGER.error(
                                    f"TMDB API returned invalid JSON structure for {endpoint}"
                                )
                                return None

                            # Cache successful results
                            cls._cache[cache_key] = data
                            cls._cache_timestamps[cache_key] = time()

                            # Clean cache if too large
                            if len(cls._cache) > cls.MAX_CACHE_SIZE:
                                cls._cleanup_cache()

                            return data

                        except Exception as json_error:
                            LOGGER.error(
                                f"TMDB API JSON parsing error for {endpoint}: {json_error}"
                            )
                            return None

                    elif response.status == 401:
                        LOGGER.error(
                            "TMDB API authentication failed - check API key"
                        )
                        return None

                    elif response.status == 404:
                        LOGGER.warning(f"TMDB API resource not found: {endpoint}")
                        return None

                    elif response.status == 429:
                        LOGGER.warning("TMDB API rate limit exceeded - please wait")
                        return None

                    elif response.status >= 500:
                        LOGGER.error(
                            f"TMDB API server error {response.status} for {endpoint}"
                        )
                        return None

                    else:
                        error_text = await response.text()
                        LOGGER.error(
                            f"TMDB API error {response.status} for {endpoint}: {error_text}"
                        )
                        return None

        except TimeoutError:
            LOGGER.error(f"TMDB API request timeout for {endpoint}")
            return None
        except aiohttp.ClientError as e:
            LOGGER.error(f"TMDB API client error for {endpoint}: {e}")
            return None
        except Exception as e:
            LOGGER.error(f"TMDB API unexpected error for {endpoint}: {e}")
            return None

    @classmethod
    def _cleanup_cache(cls):
        """Remove oldest cache entries"""
        if len(cls._cache) <= cls.MAX_CACHE_SIZE:
            return

        # Sort by timestamp and remove oldest entries
        sorted_items = sorted(cls._cache_timestamps.items(), key=lambda x: x[1])
        items_to_remove = (
            len(cls._cache) - cls.MAX_CACHE_SIZE + 10
        )  # Remove extra for buffer

        for cache_key, _ in sorted_items[:items_to_remove]:
            cls._cache.pop(cache_key, None)
            cls._cache_timestamps.pop(cache_key, None)

    @classmethod
    async def get_configuration(cls) -> dict | None:
        """Get TMDB configuration for image URLs and other settings"""
        if (
            cls._config_cache
            and time() - cls._config_cache.get("timestamp", 0) < 86400
        ):  # 24 hours
            return cls._config_cache.get("data")

        config = await cls._make_request("configuration")
        if config:
            cls._config_cache = {"data": config, "timestamp": time()}
        return config

    @classmethod
    async def get_image_url(
        cls, path: str, size: str = "w500", image_type: str = "poster"
    ) -> str | None:
        """Get full image URL from TMDB path with proper size validation

        Args:
            path: Image path from TMDB API
            size: Image size (validated against TMDB configuration)
            image_type: Type of image ('poster', 'backdrop', 'profile', 'still', 'logo')
        """
        if not path:
            return None

        # Remove leading slash if present
        path = path.removeprefix("/")

        config = await cls.get_configuration()
        if config and "images" in config:
            images_config = config["images"]
            base_url = images_config.get(
                "secure_base_url", "https://image.tmdb.org/t/p/"
            )

            # Validate size against available sizes for image type
            size_key_map = {
                "poster": "poster_sizes",
                "backdrop": "backdrop_sizes",
                "profile": "profile_sizes",
                "still": "still_sizes",
                "logo": "logo_sizes",
            }

            size_key = size_key_map.get(image_type, "poster_sizes")
            available_sizes = images_config.get(size_key, [])

            # Use provided size if available, otherwise fallback to appropriate default
            if size not in available_sizes and available_sizes:
                # Default size fallbacks based on image type
                default_sizes = {
                    "poster": ["w500", "w342", "w185", "w154", "w92"],
                    "backdrop": ["w1280", "w780", "w500", "w300"],
                    "profile": ["w185", "w154", "h632", "w45"],
                    "still": ["w500", "w300", "w185", "w92"],
                    "logo": ["w500", "w300", "w185", "w154", "w92", "w45"],
                }

                fallback_sizes = default_sizes.get(
                    image_type, ["w500", "w300", "w185"]
                )
                for fallback_size in fallback_sizes:
                    if fallback_size in available_sizes:
                        size = fallback_size
                        break
                else:
                    # Use the largest available size if no fallback matches
                    size = available_sizes[-1] if available_sizes else "original"

            return f"{base_url}{size}/{path}"

        # Fallback to default base URL with basic validation
        valid_sizes = [
            "w45",
            "w92",
            "w154",
            "w185",
            "w300",
            "w342",
            "w500",
            "w780",
            "w1280",
            "h632",
            "original",
        ]
        if size not in valid_sizes:
            size = "w500"  # Safe default

        return f"{cls.IMAGE_BASE_URL}{size}/{path}"

    @classmethod
    async def search_movie(
        cls,
        query: str,
        year: int | None = None,
        page: int = 1,
        region: str | None = None,
        primary_release_year: int | None = None,
    ) -> dict | None:
        """Search for movies with enhanced parameters

        Args:
            query: Search query string
            year: Year to filter by (searches both release_date and primary_release_date)
            page: Page number (1-1000)
            region: ISO 3166-1 code to filter release dates
            primary_release_year: Filter by primary release year
        """
        # Validate parameters
        if not query or not query.strip():
            LOGGER.error("Search query cannot be empty")
            return None

        if page < 1 or page > 1000:
            page = 1

        params = {
            "query": query.strip(),
            "page": page,
            "include_adult": "false",  # Always exclude adult content
        }

        if year:
            params["year"] = year

        if primary_release_year:
            params["primary_release_year"] = primary_release_year

        if region:
            params["region"] = region
        elif hasattr(Config, "TMDB_REGION"):
            params["region"] = Config.TMDB_REGION

        return await cls._make_request("search/movie", params)

    @classmethod
    async def search_tv(
        cls,
        query: str,
        year: int | None = None,
        page: int = 1,
        first_air_date_year: int | None = None,
    ) -> dict | None:
        """Search for TV shows with enhanced parameters

        Args:
            query: Search query string
            year: Alias for first_air_date_year
            page: Page number (1-1000)
            first_air_date_year: Filter by first air date year
        """
        # Validate parameters
        if not query or not query.strip():
            LOGGER.error("Search query cannot be empty")
            return None

        if page < 1 or page > 1000:
            page = 1

        params = {
            "query": query.strip(),
            "page": page,
            "include_adult": "false",  # Always exclude adult content
        }

        # Use first_air_date_year parameter or year alias
        air_date_year = first_air_date_year or year
        if air_date_year:
            params["first_air_date_year"] = air_date_year

        return await cls._make_request("search/tv", params)

    @classmethod
    async def search_multi(cls, query: str, page: int = 1) -> dict | None:
        """Search across movies, TV shows, and people"""
        params = {
            "query": query,
            "page": page,
            "include_adult": "false",  # Always exclude adult content
        }

        return await cls._make_request("search/multi", params)

    @classmethod
    async def search_person(cls, query: str, page: int = 1) -> dict | None:
        """Search for people"""
        params = {
            "query": query,
            "page": page,
            "include_adult": "false",  # Always exclude adult content
        }

        return await cls._make_request("search/person", params)

    @classmethod
    async def get_movie_details(
        cls, movie_id: int, append_to_response: str | None = None
    ) -> dict | None:
        """Get detailed movie information"""
        params = {}
        if append_to_response:
            params["append_to_response"] = append_to_response

        return await cls._make_request(f"movie/{movie_id}", params)

    @classmethod
    async def get_tv_details(
        cls, tv_id: int, append_to_response: str | None = None
    ) -> dict | None:
        """Get detailed TV show information"""
        params = {}
        if append_to_response:
            params["append_to_response"] = append_to_response

        return await cls._make_request(f"tv/{tv_id}", params)

    @classmethod
    async def get_person_details(
        cls, person_id: int, append_to_response: str | None = None
    ) -> dict | None:
        """Get detailed person information"""
        params = {}
        if append_to_response:
            params["append_to_response"] = append_to_response

        return await cls._make_request(f"person/{person_id}", params)

    @classmethod
    async def get_movie_credits(cls, movie_id: int) -> dict | None:
        """Get movie cast and crew"""
        return await cls._make_request(f"movie/{movie_id}/credits")

    @classmethod
    async def get_tv_credits(cls, tv_id: int) -> dict | None:
        """Get TV show cast and crew"""
        return await cls._make_request(f"tv/{tv_id}/credits")

    @classmethod
    async def get_movie_images(cls, movie_id: int) -> dict | None:
        """Get movie images (posters, backdrops)"""
        return await cls._make_request(f"movie/{movie_id}/images")

    @classmethod
    async def get_tv_images(cls, tv_id: int) -> dict | None:
        """Get TV show images (posters, backdrops)"""
        return await cls._make_request(f"tv/{tv_id}/images")

    @classmethod
    async def get_movie_videos(cls, movie_id: int) -> dict | None:
        """Get movie videos (trailers, teasers)"""
        return await cls._make_request(f"movie/{movie_id}/videos")

    @classmethod
    async def get_tv_videos(cls, tv_id: int) -> dict | None:
        """Get TV show videos (trailers, teasers)"""
        return await cls._make_request(f"tv/{tv_id}/videos")

    @classmethod
    async def get_movie_recommendations(
        cls, movie_id: int, page: int = 1
    ) -> dict | None:
        """Get movie recommendations"""
        return await cls._make_request(
            f"movie/{movie_id}/recommendations", {"page": page}
        )

    @classmethod
    async def get_tv_recommendations(cls, tv_id: int, page: int = 1) -> dict | None:
        """Get TV show recommendations"""
        return await cls._make_request(f"tv/{tv_id}/recommendations", {"page": page})

    @classmethod
    async def get_movie_similar(cls, movie_id: int, page: int = 1) -> dict | None:
        """Get similar movies"""
        return await cls._make_request(f"movie/{movie_id}/similar", {"page": page})

    @classmethod
    async def get_tv_similar(cls, tv_id: int, page: int = 1) -> dict | None:
        """Get similar TV shows"""
        return await cls._make_request(f"tv/{tv_id}/similar", {"page": page})

    @classmethod
    async def get_movie_external_ids(cls, movie_id: int) -> dict | None:
        """Get movie external IDs (IMDB, Facebook, etc.)"""
        return await cls._make_request(f"movie/{movie_id}/external_ids")

    @classmethod
    async def get_tv_external_ids(cls, tv_id: int) -> dict | None:
        """Get TV show external IDs (IMDB, Facebook, etc.)"""
        return await cls._make_request(f"tv/{tv_id}/external_ids")

    @classmethod
    async def get_genres_movie(cls) -> dict | None:
        """Get list of movie genres"""
        return await cls._make_request("genre/movie/list")

    @classmethod
    async def get_genres_tv(cls) -> dict | None:
        """Get list of TV genres"""
        return await cls._make_request("genre/tv/list")

    @classmethod
    async def discover_movies(cls, **kwargs) -> dict | None:
        """Discover movies with filters"""
        return await cls._make_request("discover/movie", kwargs)

    @classmethod
    async def discover_tv(cls, **kwargs) -> dict | None:
        """Discover TV shows with filters"""
        return await cls._make_request("discover/tv", kwargs)

    # Additional TMDB API v3 endpoints for comprehensive coverage

    @classmethod
    async def get_trending(
        cls, media_type: str = "all", time_window: str = "day"
    ) -> dict | None:
        """Get trending movies, TV shows, or people

        Args:
            media_type: 'all', 'movie', 'tv', 'person'
            time_window: 'day' or 'week'
        """
        if media_type not in ["all", "movie", "tv", "person"]:
            media_type = "all"
        if time_window not in ["day", "week"]:
            time_window = "day"

        return await cls._make_request(f"trending/{media_type}/{time_window}")

    @classmethod
    async def get_movie_now_playing(
        cls, page: int = 1, region: str | None = None
    ) -> dict | None:
        """Get movies currently in theaters"""
        params = {"page": page}
        if region:
            params["region"] = region
        elif hasattr(Config, "TMDB_REGION"):
            params["region"] = Config.TMDB_REGION

        return await cls._make_request("movie/now_playing", params)

    @classmethod
    async def get_movie_popular(
        cls, page: int = 1, region: str | None = None
    ) -> dict | None:
        """Get popular movies"""
        params = {"page": page}
        if region:
            params["region"] = region
        elif hasattr(Config, "TMDB_REGION"):
            params["region"] = Config.TMDB_REGION

        return await cls._make_request("movie/popular", params)

    @classmethod
    async def get_movie_top_rated(
        cls, page: int = 1, region: str | None = None
    ) -> dict | None:
        """Get top rated movies"""
        params = {"page": page}
        if region:
            params["region"] = region
        elif hasattr(Config, "TMDB_REGION"):
            params["region"] = Config.TMDB_REGION

        return await cls._make_request("movie/top_rated", params)

    @classmethod
    async def get_movie_upcoming(
        cls, page: int = 1, region: str | None = None
    ) -> dict | None:
        """Get upcoming movies"""
        params = {"page": page}
        if region:
            params["region"] = region
        elif hasattr(Config, "TMDB_REGION"):
            params["region"] = Config.TMDB_REGION

        return await cls._make_request("movie/upcoming", params)

    @classmethod
    async def get_tv_popular(cls, page: int = 1) -> dict | None:
        """Get popular TV shows"""
        return await cls._make_request("tv/popular", {"page": page})

    @classmethod
    async def get_tv_top_rated(cls, page: int = 1) -> dict | None:
        """Get top rated TV shows"""
        return await cls._make_request("tv/top_rated", {"page": page})

    @classmethod
    async def get_tv_on_the_air(cls, page: int = 1) -> dict | None:
        """Get TV shows currently on the air"""
        return await cls._make_request("tv/on_the_air", {"page": page})

    @classmethod
    async def get_tv_airing_today(cls, page: int = 1) -> dict | None:
        """Get TV shows airing today"""
        return await cls._make_request("tv/airing_today", {"page": page})

    @classmethod
    async def get_person_popular(cls, page: int = 1) -> dict | None:
        """Get popular people"""
        return await cls._make_request("person/popular", {"page": page})

    @classmethod
    async def get_person_movie_credits(cls, person_id: int) -> dict | None:
        """Get person's movie credits"""
        return await cls._make_request(f"person/{person_id}/movie_credits")

    @classmethod
    async def get_person_tv_credits(cls, person_id: int) -> dict | None:
        """Get person's TV credits"""
        return await cls._make_request(f"person/{person_id}/tv_credits")

    @classmethod
    async def get_person_combined_credits(cls, person_id: int) -> dict | None:
        """Get person's combined movie and TV credits"""
        return await cls._make_request(f"person/{person_id}/combined_credits")

    @classmethod
    async def get_person_external_ids(cls, person_id: int) -> dict | None:
        """Get person's external IDs"""
        return await cls._make_request(f"person/{person_id}/external_ids")

    @classmethod
    async def get_person_images(cls, person_id: int) -> dict | None:
        """Get person's images"""
        return await cls._make_request(f"person/{person_id}/images")

    @classmethod
    async def find_by_external_id(
        cls, external_id: str, external_source: str
    ) -> dict | None:
        """Find movies, TV shows, and people by external ID

        Args:
            external_id: The external ID (e.g., IMDB ID)
            external_source: 'imdb_id', 'freebase_mid', 'freebase_id', 'tvdb_id', 'tvrage_id', 'facebook_id', 'twitter_id', 'instagram_id'
        """
        valid_sources = [
            "imdb_id",
            "freebase_mid",
            "freebase_id",
            "tvdb_id",
            "tvrage_id",
            "facebook_id",
            "twitter_id",
            "instagram_id",
        ]

        if external_source not in valid_sources:
            LOGGER.error(f"Invalid external source: {external_source}")
            return None

        params = {external_source: external_id}
        return await cls._make_request("find/" + external_id, params)

    @classmethod
    async def get_movie_keywords(cls, movie_id: int) -> dict | None:
        """Get movie keywords"""
        return await cls._make_request(f"movie/{movie_id}/keywords")

    @classmethod
    async def get_tv_keywords(cls, tv_id: int) -> dict | None:
        """Get TV show keywords"""
        return await cls._make_request(f"tv/{tv_id}/keywords")

    @classmethod
    async def get_movie_reviews(cls, movie_id: int, page: int = 1) -> dict | None:
        """Get movie reviews"""
        return await cls._make_request(f"movie/{movie_id}/reviews", {"page": page})

    @classmethod
    async def get_tv_reviews(cls, tv_id: int, page: int = 1) -> dict | None:
        """Get TV show reviews"""
        return await cls._make_request(f"tv/{tv_id}/reviews", {"page": page})

    @classmethod
    async def get_movie_watch_providers(cls, movie_id: int) -> dict | None:
        """Get movie watch providers (streaming services)"""
        return await cls._make_request(f"movie/{movie_id}/watch/providers")

    @classmethod
    async def get_tv_watch_providers(cls, tv_id: int) -> dict | None:
        """Get TV show watch providers (streaming services)"""
        return await cls._make_request(f"tv/{tv_id}/watch/providers")

    @classmethod
    async def get_tv_season_details(
        cls, tv_id: int, season_number: int, append_to_response: str | None = None
    ) -> dict | None:
        """Get TV season details"""
        params = {}
        if append_to_response:
            params["append_to_response"] = append_to_response

        return await cls._make_request(f"tv/{tv_id}/season/{season_number}", params)

    @classmethod
    async def get_tv_episode_details(
        cls,
        tv_id: int,
        season_number: int,
        episode_number: int,
        append_to_response: str | None = None,
    ) -> dict | None:
        """Get TV episode details"""
        params = {}
        if append_to_response:
            params["append_to_response"] = append_to_response

        return await cls._make_request(
            f"tv/{tv_id}/season/{season_number}/episode/{episode_number}", params
        )

    # Additional TMDB API v3 endpoints for comprehensive coverage

    @classmethod
    async def get_movie_lists(cls, movie_id: int) -> dict | None:
        """Get lists that contain this movie"""
        return await cls._make_request(f"movie/{movie_id}/lists")

    @classmethod
    async def get_movie_release_dates(cls, movie_id: int) -> dict | None:
        """Get movie release dates by country"""
        return await cls._make_request(f"movie/{movie_id}/release_dates")

    @classmethod
    async def get_movie_translations(cls, movie_id: int) -> dict | None:
        """Get movie translations"""
        return await cls._make_request(f"movie/{movie_id}/translations")

    @classmethod
    async def get_tv_content_ratings(cls, tv_id: int) -> dict | None:
        """Get TV show content ratings"""
        return await cls._make_request(f"tv/{tv_id}/content_ratings")

    @classmethod
    async def get_tv_episode_groups(cls, tv_id: int) -> dict | None:
        """Get TV show episode groups"""
        return await cls._make_request(f"tv/{tv_id}/episode_groups")

    @classmethod
    async def get_tv_screened_theatrically(cls, tv_id: int) -> dict | None:
        """Get TV episodes that were screened theatrically"""
        return await cls._make_request(f"tv/{tv_id}/screened_theatrically")

    @classmethod
    async def get_tv_translations(cls, tv_id: int) -> dict | None:
        """Get TV show translations"""
        return await cls._make_request(f"tv/{tv_id}/translations")

    @classmethod
    async def get_person_external_ids(cls, person_id: int) -> dict | None:
        """Get person external IDs"""
        return await cls._make_request(f"person/{person_id}/external_ids")

    @classmethod
    async def get_person_images(cls, person_id: int) -> dict | None:
        """Get person images"""
        return await cls._make_request(f"person/{person_id}/images")

    @classmethod
    async def get_person_tagged_images(
        cls, person_id: int, page: int = 1
    ) -> dict | None:
        """Get images tagged with this person"""
        return await cls._make_request(
            f"person/{person_id}/tagged_images", {"page": page}
        )

    @classmethod
    async def get_person_translations(cls, person_id: int) -> dict | None:
        """Get person translations"""
        return await cls._make_request(f"person/{person_id}/translations")

    @classmethod
    async def get_person_latest(cls) -> dict | None:
        """Get the most recently created person"""
        return await cls._make_request("person/latest")

    @classmethod
    async def get_collection_details(
        cls, collection_id: int, append_to_response: str | None = None
    ) -> dict | None:
        """Get collection details"""
        params = {}
        if append_to_response:
            params["append_to_response"] = append_to_response

        return await cls._make_request(f"collection/{collection_id}", params)

    @classmethod
    async def get_collection_images(cls, collection_id: int) -> dict | None:
        """Get collection images"""
        return await cls._make_request(f"collection/{collection_id}/images")

    @classmethod
    async def get_collection_translations(cls, collection_id: int) -> dict | None:
        """Get collection translations"""
        return await cls._make_request(f"collection/{collection_id}/translations")

    @classmethod
    async def search_collection(cls, query: str, page: int = 1) -> dict | None:
        """Search for collections"""
        params = {
            "query": query,
            "page": page,
            "include_adult": "false",
        }
        return await cls._make_request("search/collection", params)

    @classmethod
    async def search_company(cls, query: str, page: int = 1) -> dict | None:
        """Search for companies"""
        params = {
            "query": query,
            "page": page,
        }
        return await cls._make_request("search/company", params)

    @classmethod
    async def search_keyword(cls, query: str, page: int = 1) -> dict | None:
        """Search for keywords"""
        params = {
            "query": query,
            "page": page,
        }
        return await cls._make_request("search/keyword", params)

    @classmethod
    async def get_company_details(cls, company_id: int) -> dict | None:
        """Get company details"""
        return await cls._make_request(f"company/{company_id}")

    @classmethod
    async def get_company_alternative_names(cls, company_id: int) -> dict | None:
        """Get company alternative names"""
        return await cls._make_request(f"company/{company_id}/alternative_names")

    @classmethod
    async def get_company_images(cls, company_id: int) -> dict | None:
        """Get company images"""
        return await cls._make_request(f"company/{company_id}/images")

    @classmethod
    async def get_keyword_details(cls, keyword_id: int) -> dict | None:
        """Get keyword details"""
        return await cls._make_request(f"keyword/{keyword_id}")

    @classmethod
    async def get_keyword_movies(cls, keyword_id: int, page: int = 1) -> dict | None:
        """Get movies with this keyword"""
        return await cls._make_request(
            f"keyword/{keyword_id}/movies", {"page": page}
        )

    @classmethod
    async def get_network_details(cls, network_id: int) -> dict | None:
        """Get network details"""
        return await cls._make_request(f"network/{network_id}")

    @classmethod
    async def get_network_alternative_names(cls, network_id: int) -> dict | None:
        """Get network alternative names"""
        return await cls._make_request(f"network/{network_id}/alternative_names")

    @classmethod
    async def get_network_images(cls, network_id: int) -> dict | None:
        """Get network images"""
        return await cls._make_request(f"network/{network_id}/images")

    @classmethod
    async def get_review_details(cls, review_id: str) -> dict | None:
        """Get review details"""
        return await cls._make_request(f"review/{review_id}")

    @classmethod
    async def get_movie_latest(cls) -> dict | None:
        """Get the most recently created movie"""
        return await cls._make_request("movie/latest")

    @classmethod
    async def get_tv_latest(cls) -> dict | None:
        """Get the most recently created TV show"""
        return await cls._make_request("tv/latest")

    # Advanced Discovery and Filtering

    @classmethod
    async def discover_movies_advanced(
        cls,
        sort_by: str = "popularity.desc",
        with_genres: str | None = None,
        without_genres: str | None = None,
        with_companies: str | None = None,
        with_keywords: str | None = None,
        without_keywords: str | None = None,
        with_people: str | None = None,
        with_cast: str | None = None,
        with_crew: str | None = None,
        with_runtime_gte: int | None = None,
        with_runtime_lte: int | None = None,
        primary_release_date_gte: str | None = None,
        primary_release_date_lte: str | None = None,
        vote_average_gte: float | None = None,
        vote_average_lte: float | None = None,
        vote_count_gte: int | None = None,
        vote_count_lte: int | None = None,
        with_original_language: str | None = None,
        region: str | None = None,
        page: int = 1,
        **kwargs,
    ) -> dict | None:
        """Advanced movie discovery with comprehensive filters"""
        params = {
            "sort_by": sort_by,
            "page": page,
            "include_adult": "false",
        }

        # Add all non-None parameters
        filter_params = {
            "with_genres": with_genres,
            "without_genres": without_genres,
            "with_companies": with_companies,
            "with_keywords": with_keywords,
            "without_keywords": without_keywords,
            "with_people": with_people,
            "with_cast": with_cast,
            "with_crew": with_crew,
            "with_runtime.gte": with_runtime_gte,
            "with_runtime.lte": with_runtime_lte,
            "primary_release_date.gte": primary_release_date_gte,
            "primary_release_date.lte": primary_release_date_lte,
            "vote_average.gte": vote_average_gte,
            "vote_average.lte": vote_average_lte,
            "vote_count.gte": vote_count_gte,
            "vote_count.lte": vote_count_lte,
            "with_original_language": with_original_language,
            "region": region,
        }

        # Add non-None parameters
        for key, value in filter_params.items():
            if value is not None:
                params[key] = value

        # Add any additional kwargs
        params.update(kwargs)

        return await cls._make_request("discover/movie", params)

    @classmethod
    async def discover_tv_advanced(
        cls,
        sort_by: str = "popularity.desc",
        with_genres: str | None = None,
        without_genres: str | None = None,
        with_companies: str | None = None,
        with_keywords: str | None = None,
        without_keywords: str | None = None,
        with_networks: str | None = None,
        with_runtime_gte: int | None = None,
        with_runtime_lte: int | None = None,
        first_air_date_gte: str | None = None,
        first_air_date_lte: str | None = None,
        vote_average_gte: float | None = None,
        vote_average_lte: float | None = None,
        vote_count_gte: int | None = None,
        vote_count_lte: int | None = None,
        with_original_language: str | None = None,
        timezone: str | None = None,
        page: int = 1,
        **kwargs,
    ) -> dict | None:
        """Advanced TV discovery with comprehensive filters"""
        params = {
            "sort_by": sort_by,
            "page": page,
            "include_adult": "false",
        }

        # Add all non-None parameters
        filter_params = {
            "with_genres": with_genres,
            "without_genres": without_genres,
            "with_companies": with_companies,
            "with_keywords": with_keywords,
            "without_keywords": without_keywords,
            "with_networks": with_networks,
            "with_runtime.gte": with_runtime_gte,
            "with_runtime.lte": with_runtime_lte,
            "first_air_date.gte": first_air_date_gte,
            "first_air_date.lte": first_air_date_lte,
            "vote_average.gte": vote_average_gte,
            "vote_average.lte": vote_average_lte,
            "vote_count.gte": vote_count_gte,
            "vote_count.lte": vote_count_lte,
            "with_original_language": with_original_language,
            "timezone": timezone,
        }

        # Add non-None parameters
        for key, value in filter_params.items():
            if value is not None:
                params[key] = value

        # Add any additional kwargs
        params.update(kwargs)

        return await cls._make_request("discover/tv", params)

    @classmethod
    async def get_certifications_movie(cls) -> dict | None:
        """Get movie certifications"""
        return await cls._make_request("certification/movie/list")

    @classmethod
    async def get_certifications_tv(cls) -> dict | None:
        """Get TV certifications"""
        return await cls._make_request("certification/tv/list")

    @classmethod
    async def get_movie_alternative_titles(
        cls, movie_id: int, country: str | None = None
    ) -> dict | None:
        """Get movie alternative titles"""
        params = {}
        if country:
            params["country"] = country

        return await cls._make_request(
            f"movie/{movie_id}/alternative_titles", params
        )

    @classmethod
    async def get_tv_alternative_titles(cls, tv_id: int) -> dict | None:
        """Get TV show alternative titles"""
        return await cls._make_request(f"tv/{tv_id}/alternative_titles")

    @classmethod
    async def get_movie_images(
        cls, movie_id: int, include_image_language: str | None = None
    ) -> dict | None:
        """Get movie images"""
        params = {}
        if include_image_language:
            params["include_image_language"] = include_image_language

        return await cls._make_request(f"movie/{movie_id}/images", params)

    @classmethod
    async def get_tv_images(
        cls, tv_id: int, include_image_language: str | None = None
    ) -> dict | None:
        """Get TV show images"""
        params = {}
        if include_image_language:
            params["include_image_language"] = include_image_language

        return await cls._make_request(f"tv/{tv_id}/images", params)

    @classmethod
    async def get_season_images(
        cls,
        tv_id: int,
        season_number: int,
        include_image_language: str | None = None,
    ) -> dict | None:
        """Get TV season images"""
        params = {}
        if include_image_language:
            params["include_image_language"] = include_image_language

        return await cls._make_request(
            f"tv/{tv_id}/season/{season_number}/images", params
        )

    @classmethod
    async def get_episode_images(
        cls,
        tv_id: int,
        season_number: int,
        episode_number: int,
        include_image_language: str | None = None,
    ) -> dict | None:
        """Get TV episode images"""
        params = {}
        if include_image_language:
            params["include_image_language"] = include_image_language

        return await cls._make_request(
            f"tv/{tv_id}/season/{season_number}/episode/{episode_number}/images",
            params,
        )


# TMDB Data Processing and Formatting Functions
def format_runtime(minutes: int) -> str:
    """Format runtime in minutes to hours and minutes"""
    if not minutes:
        return "Unknown"

    hours = minutes // 60
    mins = minutes % 60

    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def format_date(date_str: str) -> str:
    """Format date string to readable format"""
    if not date_str:
        return "Unknown"

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%B %d, %Y")
    except ValueError:
        return date_str


def format_money(amount: int) -> str:
    """Format money amount with proper formatting"""
    if not amount:
        return "Unknown"

    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount}"


def get_genre_names(genre_ids: list, genre_list: list) -> list:
    """Convert genre IDs to genre names"""
    if not genre_ids or not genre_list:
        return []

    genre_map = {genre["id"]: genre["name"] for genre in genre_list}
    return [genre_map.get(gid, f"Unknown ({gid})") for gid in genre_ids]


def format_cast_list(cast: list, limit: int = 5) -> str:
    """Format cast list for display"""
    if not cast:
        return "Unknown"

    cast_names = [person.get("name", "Unknown") for person in cast[:limit]]
    result = ", ".join(cast_names)

    if len(cast) > limit:
        result += f" and {len(cast) - limit} more"

    return result


def format_crew_by_job(crew: list, job: str) -> str:
    """Get crew members by specific job"""
    if not crew:
        return "Unknown"

    job_crew = [
        person.get("name", "Unknown") for person in crew if person.get("job") == job
    ]
    return ", ".join(job_crew) if job_crew else "Unknown"


async def process_movie_data(movie_data: dict) -> dict:
    """Process raw TMDB movie data into formatted information with enhanced validation"""
    if not movie_data or not isinstance(movie_data, dict):
        LOGGER.error("Invalid movie data provided to process_movie_data")
        return {}

    # Validate required fields
    movie_id = movie_data.get("id")
    if not movie_id:
        LOGGER.error("Movie data missing required 'id' field")
        return {}

    # Initialize additional data variables
    credits = None
    videos = None
    external_ids = None

    # Fetch additional data concurrently if movie ID is available
    if movie_id:
        try:
            # Create tasks for concurrent execution
            tasks = [
                TMDBHelper.get_movie_credits(movie_id),
                TMDBHelper.get_movie_videos(movie_id),
                TMDBHelper.get_movie_external_ids(movie_id),
            ]

            # Execute tasks concurrently with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30.0,  # 30 second timeout for all requests
            )

            credits, videos, external_ids = results

            # Handle exceptions in individual results
            if isinstance(credits, Exception):
                LOGGER.warning(
                    f"Failed to fetch movie credits for {movie_id}: {credits}"
                )
                credits = None

            if isinstance(videos, Exception):
                LOGGER.warning(
                    f"Failed to fetch movie videos for {movie_id}: {videos}"
                )
                videos = None

            if isinstance(external_ids, Exception):
                LOGGER.warning(
                    f"Failed to fetch movie external IDs for {movie_id}: {external_ids}"
                )
                external_ids = None

        except TimeoutError:
            LOGGER.warning(f"Timeout fetching additional movie data for {movie_id}")
        except Exception as e:
            LOGGER.error(f"Error fetching additional movie data for {movie_id}: {e}")

    # Process comprehensive movie information based on TMDB3 fields
    processed_data = {
        # Core Identification
        "id": movie_data.get("id"),
        "title": movie_data.get("title", "Unknown"),
        "original_title": movie_data.get("original_title"),
        "overview": movie_data.get("overview", "No overview available"),
        "tagline": movie_data.get("tagline"),
        # Release and Status Information
        "release_date": movie_data.get("release_date"),
        "release_date_formatted": format_date(movie_data.get("release_date")),
        "year": movie_data.get("release_date", "")[:4]
        if movie_data.get("release_date")
        else None,
        "status": movie_data.get("status"),  # Released, Post Production, etc.
        # Ratings and Metrics
        "vote_average": movie_data.get("vote_average", 0),
        "vote_count": movie_data.get("vote_count", 0),
        "popularity": movie_data.get("popularity", 0),
        # Technical Specifications
        "runtime": movie_data.get("runtime"),
        "runtime_formatted": format_runtime(movie_data.get("runtime", 0)),
        "original_language": movie_data.get("original_language"),
        # Financial Data
        "budget": movie_data.get("budget"),
        "budget_formatted": format_money(movie_data.get("budget", 0)),
        "revenue": movie_data.get("revenue"),
        "revenue_formatted": format_money(movie_data.get("revenue", 0)),
        # Content Classification
        "adult": movie_data.get("adult", False),
        "video": movie_data.get("video", False),  # True if it's a video/documentary
        # Collection Information
        "belongs_to_collection": movie_data.get("belongs_to_collection"),
        # Production Details
        "production_countries": movie_data.get("production_countries", []),
        "production_companies": movie_data.get("production_companies", []),
        "spoken_languages": movie_data.get("spoken_languages", []),
        # Genre Information
        "genres": movie_data.get("genres", []),
        "genre_names": [genre.get("name") for genre in movie_data.get("genres", [])],
        # Image Assets (multiple sizes for optimization)
        "poster_path": movie_data.get("poster_path"),
        "backdrop_path": movie_data.get("backdrop_path"),
        "poster_url": await TMDBHelper.get_image_url(
            movie_data.get("poster_path"), "w500", "poster"
        ),
        "poster_url_small": await TMDBHelper.get_image_url(
            movie_data.get("poster_path"), "w342", "poster"
        ),
        "poster_url_large": await TMDBHelper.get_image_url(
            movie_data.get("poster_path"), "w780", "poster"
        ),
        "backdrop_url": await TMDBHelper.get_image_url(
            movie_data.get("backdrop_path"), "w1280", "backdrop"
        ),
        "backdrop_url_small": await TMDBHelper.get_image_url(
            movie_data.get("backdrop_path"), "w780", "backdrop"
        ),
        # External Links
        "tmdb_url": f"https://www.themoviedb.org/movie/{movie_data.get('id')}"
        if movie_data.get("id")
        else None,
        "homepage": movie_data.get("homepage"),
    }

    # Process credits if available
    if credits and isinstance(credits, dict):
        cast = credits.get("cast", [])
        crew = credits.get("crew", [])

        processed_data.update(
            {
                "cast": cast[:10],  # Limit to top 10
                "cast_formatted": format_cast_list(cast, 5),
                "crew": crew,
                "director": format_crew_by_job(crew, "Director"),
                "writer": format_crew_by_job(crew, "Writer"),
                "producer": format_crew_by_job(crew, "Producer"),
                "cinematographer": format_crew_by_job(
                    crew, "Director of Photography"
                ),
                "composer": format_crew_by_job(crew, "Original Music Composer"),
            }
        )

    # Process videos if available
    if videos and isinstance(videos, dict):
        video_results = videos.get("results", [])
        trailers = [v for v in video_results if v.get("type") == "Trailer"]

        processed_data.update(
            {
                "videos": video_results,
                "trailers": trailers,
                "trailer_url": f"https://www.youtube.com/watch?v={trailers[0]['key']}"
                if trailers
                else None,
            }
        )

    # Process external IDs if available (social media only, no IMDB)
    if external_ids and isinstance(external_ids, dict):
        processed_data.update(
            {
                "facebook_id": external_ids.get("facebook_id"),
                "instagram_id": external_ids.get("instagram_id"),
                "twitter_id": external_ids.get("twitter_id"),
                "wikidata_id": external_ids.get("wikidata_id"),
            }
        )

    return processed_data


async def process_tv_data(tv_data: dict) -> dict:
    """Process raw TMDB TV show data into formatted information"""
    if not tv_data:
        return {}

    # Get additional data if needed
    tv_id = tv_data.get("id")
    credits = None
    videos = None
    external_ids = None

    if tv_id:
        # Fetch additional data concurrently
        tasks = [
            TMDBHelper.get_tv_credits(tv_id),
            TMDBHelper.get_tv_videos(tv_id),
            TMDBHelper.get_tv_external_ids(tv_id),
        ]

        try:
            credits, videos, external_ids = await asyncio.gather(
                *tasks, return_exceptions=True
            )
        except Exception as e:
            LOGGER.error(f"Error fetching additional TV data: {e}")

    # Process basic information
    processed_data = {
        # Basic Information
        "id": tv_data.get("id"),
        "name": tv_data.get("name", "Unknown"),
        "original_name": tv_data.get("original_name"),
        "overview": tv_data.get("overview", "No overview available"),
        "tagline": tv_data.get("tagline"),
        # Air Date Information
        "first_air_date": tv_data.get("first_air_date"),
        "first_air_date_formatted": format_date(tv_data.get("first_air_date")),
        "last_air_date": tv_data.get("last_air_date"),
        "last_air_date_formatted": format_date(tv_data.get("last_air_date")),
        "year": tv_data.get("first_air_date", "")[:4]
        if tv_data.get("first_air_date")
        else None,
        # Series Information
        "number_of_seasons": tv_data.get("number_of_seasons"),
        "number_of_episodes": tv_data.get("number_of_episodes"),
        "episode_run_time": tv_data.get("episode_run_time", []),
        "status": tv_data.get("status"),
        "type": tv_data.get("type"),
        "in_production": tv_data.get("in_production", False),
        # Ratings and Popularity
        "vote_average": tv_data.get("vote_average", 0),
        "vote_count": tv_data.get("vote_count", 0),
        "popularity": tv_data.get("popularity", 0),
        # Content Information
        "adult": tv_data.get("adult", False),
        "original_language": tv_data.get("original_language"),
        # Network and Production
        "networks": tv_data.get("networks", []),
        "production_companies": tv_data.get("production_companies", []),
        "production_countries": tv_data.get("production_countries", []),
        "spoken_languages": tv_data.get("spoken_languages", []),
        "origin_country": tv_data.get("origin_country", []),
        # Creators and Seasons
        "created_by": tv_data.get("created_by", []),
        "seasons": tv_data.get("seasons", []),
        "next_episode_to_air": tv_data.get("next_episode_to_air"),
        "last_episode_to_air": tv_data.get("last_episode_to_air"),
        # Genres
        "genres": tv_data.get("genres", []),
        "genre_names": [genre.get("name") for genre in tv_data.get("genres", [])],
        # Images
        "poster_path": tv_data.get("poster_path"),
        "backdrop_path": tv_data.get("backdrop_path"),
        "poster_url": await TMDBHelper.get_image_url(
            tv_data.get("poster_path"), "w500"
        ),
        "backdrop_url": await TMDBHelper.get_image_url(
            tv_data.get("backdrop_path"), "w1280"
        ),
        # URLs and IDs
        "tmdb_url": f"https://www.themoviedb.org/tv/{tv_data.get('id')}"
        if tv_data.get("id")
        else None,
        "homepage": tv_data.get("homepage"),
    }

    # Process credits if available
    if credits and isinstance(credits, dict):
        cast = credits.get("cast", [])
        crew = credits.get("crew", [])

        processed_data.update(
            {
                "cast": cast[:10],  # Limit to top 10
                "cast_formatted": format_cast_list(cast, 5),
                "crew": crew,
                "director": format_crew_by_job(crew, "Director"),
                "writer": format_crew_by_job(crew, "Writer"),
                "producer": format_crew_by_job(crew, "Producer"),
                "creator": ", ".join(
                    [
                        creator.get("name", "Unknown")
                        for creator in tv_data.get("created_by", [])
                    ]
                ),
            }
        )

    # Process videos if available
    if videos and isinstance(videos, dict):
        video_results = videos.get("results", [])
        trailers = [v for v in video_results if v.get("type") == "Trailer"]

        processed_data.update(
            {
                "videos": video_results,
                "trailers": trailers,
                "trailer_url": f"https://www.youtube.com/watch?v={trailers[0]['key']}"
                if trailers
                else None,
            }
        )

    # Process external IDs if available (social media only, no IMDB)
    if external_ids and isinstance(external_ids, dict):
        processed_data.update(
            {
                "facebook_id": external_ids.get("facebook_id"),
                "instagram_id": external_ids.get("instagram_id"),
                "twitter_id": external_ids.get("twitter_id"),
                "tvdb_id": external_ids.get("tvdb_id"),
                "wikidata_id": external_ids.get("wikidata_id"),
            }
        )

    return processed_data


def _is_field_available(value: Any) -> bool:
    """Check if a field has meaningful data"""
    if value is None:
        return False

    if isinstance(value, list | dict | set | tuple) and len(value) == 0:
        return False

    if isinstance(value, int | float):
        return value > 0  # For TMDB, 0 usually means no data

    if isinstance(value, bool):
        return True  # Boolean values are always meaningful

    value_str = str(value).strip()
    return not (
        not value_str or value_str.lower() in ["unknown", "n/a", "none", "null", ""]
    )


def _build_movie_template(data: dict, compact_mode: bool = False) -> str:
    """Build comprehensive movie template with enhanced TMDB fields"""
    template_parts = []

    # Title with original title if different
    title = data.get("title", "Unknown")
    original_title = data.get("original_title", "")
    year = data.get("year", "")

    if original_title and original_title != title:
        template_parts.append(f"<b>🎬 Title:</b> <code>{title}</code> [{year}]")
        template_parts.append(f"<b>🌐 Original:</b> <i>{original_title}</i>")
    else:
        template_parts.append(f"<b>🎬 Title:</b> <code>{title}</code> [{year}]")

    # Rating with popularity score
    if _is_field_available(data.get("vote_average")):
        rating = data.get("vote_average")
        vote_count = data.get("vote_count", 0)
        popularity = data.get("popularity", 0)
        template_parts.append(
            f"<b>⭐ Rating:</b> <i>{rating}/10</i> ({vote_count:,} votes)"
        )
        if popularity > 0:
            template_parts.append(f"<b>📊 Popularity:</b> {popularity:.1f}")

    # Genres with more detail
    if _is_field_available(data.get("genre_names")):
        genres = ", ".join(data["genre_names"][:4])  # Limit to 4 genres
        template_parts.append(f"<b>🎭 Genres:</b> {genres}")

    # Release date and status
    if _is_field_available(data.get("release_date_formatted")):
        template_parts.append(
            f"<b>📅 Released:</b> {data['release_date_formatted']}"
        )

    if _is_field_available(data.get("status")) and data.get("status") != "Released":
        template_parts.append(f"<b>📊 Status:</b> {data['status']}")

    # Runtime and language
    runtime_lang_parts = []
    if _is_field_available(data.get("runtime_formatted")):
        runtime_lang_parts.append(f"⏱️ {data['runtime_formatted']}")

    if _is_field_available(data.get("original_language")):
        lang_code = data.get("original_language", "").upper()
        runtime_lang_parts.append(f"🗣️ {lang_code}")

    if runtime_lang_parts:
        template_parts.append(" • ".join(runtime_lang_parts))

    # Tagline (prioritized for impact)
    if _is_field_available(data.get("tagline")) and not compact_mode:
        tagline = data["tagline"]
        if len(tagline) > 100:
            tagline = tagline[:100] + "..."
        template_parts.append(f'<b>💭</b> <i>"{tagline}"</i>')

    # Overview (optimized length)
    if _is_field_available(data.get("overview")) and not compact_mode:
        overview = data["overview"]
        # Smart truncation - prefer sentence endings
        if len(overview) > 250:
            truncated = overview[:250]
            last_sentence = max(
                truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?")
            )
            if last_sentence > 150:
                overview = overview[: last_sentence + 1]
            else:
                overview = truncated + "..."
        template_parts.append("")
        template_parts.append("<b>📖 Overview:</b>")
        template_parts.append(f"<blockquote>{overview}</blockquote>")

    # Key crew (prioritized)
    if not compact_mode:
        crew_parts = []
        if _is_field_available(data.get("director")):
            crew_parts.append(f"👨‍💼 <b>Director:</b> {data['director']}")

        if _is_field_available(data.get("writer")):
            writers = data["writer"]
            if len(writers) > 50:
                writers = writers[:50] + "..."
            crew_parts.append(f"✍️ <b>Writer:</b> {writers}")

        if _is_field_available(data.get("composer")):
            composer = data["composer"]
            if len(composer) > 40:
                composer = composer[:40] + "..."
            crew_parts.append(f"🎵 <b>Music:</b> {composer}")

        if crew_parts:
            template_parts.extend(crew_parts)

    # Cast (top 3-4 actors)
    if _is_field_available(data.get("cast_formatted")) and not compact_mode:
        cast = data["cast_formatted"]
        if len(cast) > 80:
            cast = cast[:80] + "..."
        template_parts.append(f"<b>👥 Cast:</b> {cast}")

    # Production companies (major studios only)
    if _is_field_available(data.get("production_companies")) and not compact_mode:
        companies = [
            comp.get("name", "") for comp in data["production_companies"][:2]
        ]
        if companies:
            companies_str = ", ".join(companies)
            if len(companies_str) > 60:
                companies_str = companies_str[:60] + "..."
            template_parts.append(f"<b>🏢 Studio:</b> {companies_str}")

    # Financial info (if significant)
    if not compact_mode:
        financial_parts = []
        if (
            _is_field_available(data.get("budget_formatted"))
            and data.get("budget", 0) > 1000000
        ):
            financial_parts.append(f"💰 {data['budget_formatted']}")

        if (
            _is_field_available(data.get("revenue_formatted"))
            and data.get("revenue", 0) > 1000000
        ):
            financial_parts.append(f"💵 {data['revenue_formatted']}")

        if financial_parts:
            template_parts.append(" • ".join(financial_parts))

    # Collection info
    if _is_field_available(data.get("belongs_to_collection")) and not compact_mode:
        collection = data["belongs_to_collection"]
        if isinstance(collection, dict):
            collection_name = collection.get("name", "")
            if collection_name:
                template_parts.append(f"<b>📚 Collection:</b> {collection_name}")

    # Links (TMDB only, no IMDB)
    template_parts.append("")
    if _is_field_available(data.get("tmdb_url")):
        template_parts.append(
            f'<b>🔗 TMDB:</b> <a href="{data["tmdb_url"]}">View Details</a>'
        )

    if _is_field_available(data.get("trailer_url")) and not compact_mode:
        template_parts.append(
            f'<b>🎥 Trailer:</b> <a href="{data["trailer_url"]}">Watch</a>'
        )

    if _is_field_available(data.get("homepage")) and not compact_mode:
        template_parts.append(
            f'<b>🏠 Official:</b> <a href="{data["homepage"]}">Website</a>'
        )

    template_parts.append("")
    template_parts.append("<i>Powered by TMDB</i>")

    return "\n".join(template_parts)


def _build_tv_template(data: dict, compact_mode: bool = False) -> str:
    """Build dynamic TV show template based on available data"""
    template_parts = []

    # Title (always show)
    name = data.get("name", "Unknown")
    year = data.get("year", "")
    template_parts.append(f"<b>📺 Title:</b> <code>{name}</code> [{year}]")

    # Rating and popularity
    if _is_field_available(data.get("vote_average")):
        rating = data.get("vote_average")
        vote_count = data.get("vote_count", 0)
        template_parts.append(
            f"<b>⭐ Rating:</b> <i>{rating}/10</i> ({vote_count:,} votes)"
        )

    # Genres
    if _is_field_available(data.get("genre_names")):
        genres = ", ".join(data["genre_names"])
        template_parts.append(f"<b>🎭 Genres:</b> {genres}")

    # Air dates
    if _is_field_available(data.get("first_air_date_formatted")):
        template_parts.append(
            f"<b>📅 First Aired:</b> {data['first_air_date_formatted']}"
        )

    if _is_field_available(data.get("last_air_date_formatted")) and not compact_mode:
        template_parts.append(
            f"<b>📅 Last Aired:</b> {data['last_air_date_formatted']}"
        )

    # Series information
    if _is_field_available(data.get("number_of_seasons")):
        seasons = data["number_of_seasons"]
        episodes = data.get("number_of_episodes", 0)
        template_parts.append(
            f"<b>📊 Series:</b> {seasons} seasons, {episodes} episodes"
        )

    # Status and type
    if _is_field_available(data.get("status")):
        status = data["status"]
        if _is_field_available(data.get("type")):
            status += f" ({data['type']})"
        template_parts.append(f"<b>📊 Status:</b> {status}")

    # Episode runtime
    if _is_field_available(data.get("episode_run_time")) and not compact_mode:
        runtimes = data["episode_run_time"]
        if runtimes:
            runtime_str = ", ".join([f"{rt}m" for rt in runtimes])
            template_parts.append(f"<b>⏱️ Episode Runtime:</b> {runtime_str}")

    # Overview
    if _is_field_available(data.get("overview")) and not compact_mode:
        overview = data["overview"]
        if len(overview) > 300:
            overview = overview[:300] + "..."
        template_parts.append("")
        template_parts.append("<b>📖 Overview:</b>")
        template_parts.append(f"<blockquote>{overview}</blockquote>")

    # Cast and crew (if not compact)
    if not compact_mode:
        if _is_field_available(data.get("creator")):
            template_parts.append(f"<b>👨‍💼 Creator:</b> {data['creator']}")

        if _is_field_available(data.get("cast_formatted")):
            template_parts.append(f"<b>👥 Cast:</b> {data['cast_formatted']}")

    # Network information
    if _is_field_available(data.get("networks")) and not compact_mode:
        networks = ", ".join(
            [network.get("name", "Unknown") for network in data["networks"]]
        )
        template_parts.append(f"<b>📡 Networks:</b> {networks}")

    # Production information
    if _is_field_available(data.get("origin_country")) and not compact_mode:
        countries = ", ".join(data["origin_country"])
        template_parts.append(f"<b>🌍 Origin:</b> {countries}")

    # Tagline
    if _is_field_available(data.get("tagline")) and not compact_mode:
        template_parts.append(f"<b>💭 Tagline:</b> <i>{data['tagline']}</i>")

    # URLs
    template_parts.append("")
    if _is_field_available(data.get("tmdb_url")):
        template_parts.append(
            f'<b>🔗 TMDB:</b> <a href="{data["tmdb_url"]}">View Details</a>'
        )

    if _is_field_available(data.get("trailer_url")) and not compact_mode:
        template_parts.append(
            f'<b>🎥 Trailer:</b> <a href="{data["trailer_url"]}">Watch</a>'
        )

    if _is_field_available(data.get("homepage")) and not compact_mode:
        template_parts.append(
            f'<b>🏠 Homepage:</b> <a href="{data["homepage"]}">Official Site</a>'
        )

    template_parts.append("")
    template_parts.append("<i>Powered by TMDB</i>")

    return "\n".join(template_parts)


def _truncate_caption_for_telegram(
    caption: str, data: dict | None = None, max_length: int = 1024
) -> str:
    """Truncate caption to fit Telegram's media caption limit"""
    if len(caption) <= max_length:
        return caption

    # Try compact mode if data is available
    if data:
        try:
            if "name" in data:  # TV show
                compact_caption = _build_tv_template(data, compact_mode=True)
            else:  # Movie
                compact_caption = _build_movie_template(data, compact_mode=True)

            if len(compact_caption) <= max_length:
                return compact_caption
        except Exception:
            pass

    # Progressive truncation
    lines = caption.split("\n")

    # Remove less important sections
    sections_to_remove = [
        "💰 Budget:",
        "💵 Revenue:",
        "🏠 Homepage:",
        "🎥 Trailer:",
        "🌍 Countries:",
        "🗣️ Languages:",
        "📡 Networks:",
        "💭 Tagline:",
    ]

    for section in sections_to_remove:
        if len("\n".join(lines)) <= max_length:
            break
        lines = [line for line in lines if section not in line]

    # Truncate overview if still too long
    result = "\n".join(lines)
    if len(result) > max_length:
        for i, line in enumerate(lines):
            if "<blockquote>" in line and len(line) > 100:
                overview_content = line.replace("<blockquote>", "").replace(
                    "</blockquote>", ""
                )
                if len(overview_content) > 150:
                    truncated_overview = overview_content[:150] + "..."
                    lines[i] = f"<blockquote>{truncated_overview}</blockquote>"
                break

    # Final truncation if needed
    result = "\n".join(lines)
    if len(result) > max_length:
        truncated = result[: max_length - 80]
        last_newline = truncated.rfind("\n")
        if last_newline > max_length * 0.7:
            truncated = result[:last_newline]
        result = (
            truncated
            + "\n\n<i>... (truncated for Telegram limits)</i>\n<i>Powered by TMDB</i>"
        )

    return result


# Main TMDB Search Functions
async def search_tmdb_content(
    query: str, content_type: str = "multi"
) -> dict | None:
    """Search TMDB for movies, TV shows, or multi-content"""
    try:
        # Extract year from query if present
        year_match = re.search(r"\b(19|20)\d{2}\b", query)
        year = int(year_match.group()) if year_match else None

        # Clean query
        clean_query = re.sub(r"\b(19|20)\d{2}\b", "", query).strip()
        clean_query = re.sub(r"\s+", " ", clean_query)

        if content_type == "movie":
            results = await TMDBHelper.search_movie(clean_query, year)
        elif content_type == "tv":
            results = await TMDBHelper.search_tv(clean_query, year)
        else:  # multi
            results = await TMDBHelper.search_multi(clean_query)

        if results and results.get("results"):
            # Return the first result for now (can be enhanced with scoring)
            return results["results"][0]

        return None

    except Exception as e:
        LOGGER.error(f"Error searching TMDB: {e}")
        return None


async def get_tmdb_info(tmdb_id: int, content_type: str) -> dict | None:
    """Get detailed TMDB information for a specific ID"""
    try:
        if content_type == "movie":
            # Get movie details with additional data
            movie_data = await TMDBHelper.get_movie_details(
                tmdb_id,
                append_to_response="credits,videos,external_ids,recommendations,similar",
            )
            if movie_data:
                return await process_movie_data(movie_data)

        elif content_type == "tv":
            # Get TV show details with additional data
            tv_data = await TMDBHelper.get_tv_details(
                tmdb_id,
                append_to_response="credits,videos,external_ids,recommendations,similar",
            )
            if tv_data:
                return await process_tv_data(tv_data)

        return None

    except Exception as e:
        LOGGER.error(f"Error getting TMDB info: {e}")
        return None


# Telegram Bot Integration - Will be registered after bot initialization
async def tmdb_callback_handler(client, query: CallbackQuery):
    """Handle TMDB callback queries"""
    try:
        callback_data = query.data
        user_id = query.from_user.id
        message = query.message

        # Handle pagination callbacks
        if callback_data.startswith("tmdb_page_"):
            # Parse pagination data: tmdb_page_query_pagenum
            parts = callback_data.split("_", 3)
            if len(parts) >= 4:
                _, _, search_query, page_num = parts[0], parts[1], parts[2], parts[3]
                try:
                    page = int(page_num)
                    # Perform new search with pagination
                    response_text, buttons = await tmdb_search(
                        search_query, user_id, page
                    )

                    await query.edit_message_text(
                        text=response_text,
                        reply_markup=buttons,
                        parse_mode=ParseMode.HTML,
                    )
                    await query.answer()
                    return
                except (ValueError, Exception) as e:
                    LOGGER.error(f"Error in pagination: {e}")
                    await query.answer("❌ Pagination error", show_alert=True)
                    return

        # Handle no-op callbacks (page indicator)
        if callback_data == "tmdb_noop":
            await query.answer()
            return

        # Parse regular callback data: tmdb_type_id (e.g., tmdb_movie_12345)
        parts = callback_data.split("_")
        if len(parts) != 3:
            await query.answer("Invalid callback data", show_alert=True)
            return

        _, content_type, tmdb_id = parts
        try:
            tmdb_id = int(tmdb_id)
        except ValueError:
            await query.answer("Invalid TMDB ID", show_alert=True)
            return

        # Show loading message
        await query.answer("🔍 Fetching TMDB information...")

        # Get detailed information
        tmdb_data = await get_tmdb_info(tmdb_id, content_type)

        if not tmdb_data:
            await query.answer(
                "❌ Failed to fetch TMDB information", show_alert=True
            )
            return

        # Build template
        if content_type == "movie":
            caption = _build_movie_template(tmdb_data)
        else:  # tv
            caption = _build_tv_template(tmdb_data)

        # Truncate if needed
        caption = _truncate_caption_for_telegram(caption, tmdb_data)

        # Create buttons
        buttons = []

        # Add TMDB link only
        if tmdb_data.get("tmdb_url"):
            buttons.append(
                [InlineKeyboardButton("🔗 TMDB Details", url=tmdb_data["tmdb_url"])]
            )

        # Add trailer link if available
        if tmdb_data.get("trailer_url"):
            buttons.append(
                [InlineKeyboardButton("🎥 Trailer", url=tmdb_data["trailer_url"])]
            )

        # Add homepage link if available
        if tmdb_data.get("homepage"):
            buttons.append(
                [InlineKeyboardButton("🏠 Homepage", url=tmdb_data["homepage"])]
            )

        # Create reply markup
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        # Send result with poster
        poster_url = tmdb_data.get("poster_url")

        if poster_url:
            try:
                from bot.core.aeon_client import TgClient

                await TgClient.bot.send_photo(
                    chat_id=message.chat.id,
                    caption=caption,
                    photo=poster_url,
                    reply_markup=reply_markup,
                )

                # Delete the original message
                with contextlib.suppress(Exception):
                    await message.delete()

            except Exception as e:
                LOGGER.error(f"Error sending TMDB photo: {e}")
                # Fallback to text message
                await send_message(message, caption, reply_markup)
        else:
            # Send text message without photo
            await send_message(message, caption, reply_markup)

    except Exception as e:
        LOGGER.error(f"Error in TMDB callback: {e}")
        await query.answer("❌ An error occurred", show_alert=True)


# Helper function to create TMDB search buttons
def create_tmdb_search_buttons(
    search_results: list, query: str, page: int = 1, total_pages: int = 1
) -> InlineKeyboardMarkup | None:
    """Create enhanced inline keyboard with TMDB search results and pagination"""
    if not search_results:
        return None

    buttons = []
    results_per_page = 8

    # Create buttons for search results (up to 8 per page)
    for result in search_results[:results_per_page]:
        media_type = result.get("media_type", "unknown")

        if media_type == "movie":
            title = result.get("title", "Unknown")
            year = (
                result.get("release_date", "")[:4]
                if result.get("release_date")
                else ""
            )
            display_text = f"🎬 {title} ({year})" if year else f"🎬 {title}"
            callback_data = f"tmdb_movie_{result.get('id')}"

        elif media_type == "tv":
            title = result.get("name", "Unknown")
            year = (
                result.get("first_air_date", "")[:4]
                if result.get("first_air_date")
                else ""
            )
            display_text = f"📺 {title} ({year})" if year else f"📺 {title}"
            callback_data = f"tmdb_tv_{result.get('id')}"

        elif media_type == "person":
            name = result.get("name", "Unknown")
            known_for = result.get("known_for_department", "")
            display_text = f"👤 {name}" + (f" ({known_for})" if known_for else "")
            callback_data = f"tmdb_person_{result.get('id')}"

        else:
            continue  # Skip unknown media types

        # Truncate display text if too long
        if len(display_text) > 60:
            display_text = display_text[:57] + "..."

        buttons.append(
            [InlineKeyboardButton(display_text, callback_data=callback_data)]
        )

    # Add pagination buttons if there are multiple pages
    if total_pages > 1:
        pagination_buttons = []

        # Previous page button
        if page > 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    "⬅️ Previous", callback_data=f"tmdb_page_{query}_{page - 1}"
                )
            )

        # Page indicator
        pagination_buttons.append(
            InlineKeyboardButton(
                f"📄 {page}/{total_pages}", callback_data="tmdb_noop"
            )
        )

        # Next page button
        if page < total_pages:
            pagination_buttons.append(
                InlineKeyboardButton(
                    "Next ➡️", callback_data=f"tmdb_page_{query}_{page + 1}"
                )
            )

        buttons.append(pagination_buttons)

    return InlineKeyboardMarkup(buttons) if buttons else None


# Main search function for external use
async def tmdb_search(
    query: str, user_id: int | None = None, page: int = 1
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Enhanced TMDB search function with pagination support"""
    try:
        # Search for content with pagination
        results = await TMDBHelper.search_multi(query, page=page)

        if not results or not results.get("results"):
            return "❌ No results found on TMDB.", None

        search_results = results["results"]
        total_results = results.get("total_results", 0)
        total_pages = results.get("total_pages", 1)

        # Limit results per page for better display
        results_per_page = 8
        start_idx = (page - 1) * results_per_page
        page_results = search_results[:results_per_page]

        # Create response message with pagination info
        response_lines = [
            f"🔍 <b>TMDB Search Results for:</b> <code>{query}</code>",
            f"📊 <b>Page {page} of {total_pages}</b> • <b>{total_results:,} total results</b>\n",
        ]

        for i, result in enumerate(page_results, start_idx + 1):
            media_type = result.get("media_type", "unknown")

            if media_type == "movie":
                title = result.get("title", "Unknown")
                year = (
                    result.get("release_date", "")[:4]
                    if result.get("release_date")
                    else ""
                )
                rating = result.get("vote_average", 0)
                overview = (
                    result.get("overview", "")[:100] + "..."
                    if result.get("overview")
                    else "No overview"
                )

                response_lines.append(f"<b>{i}. 🎬 {title}</b> ({year})")
                response_lines.append(f"   ⭐ {rating}/10")
                response_lines.append(f"   📖 {overview}\n")

            elif media_type == "tv":
                title = result.get("name", "Unknown")
                year = (
                    result.get("first_air_date", "")[:4]
                    if result.get("first_air_date")
                    else ""
                )
                rating = result.get("vote_average", 0)
                overview = (
                    result.get("overview", "")[:100] + "..."
                    if result.get("overview")
                    else "No overview"
                )

                response_lines.append(f"<b>{i}. 📺 {title}</b> ({year})")
                response_lines.append(f"   ⭐ {rating}/10")
                response_lines.append(f"   📖 {overview}\n")

            elif media_type == "person":
                name = result.get("name", "Unknown")
                known_for = result.get("known_for_department", "")
                popularity = result.get("popularity", 0)

                response_lines.append(f"<b>{i}. 👤 {name}</b>")
                response_lines.append(f"   🎭 {known_for}")
                response_lines.append(f"   📊 Popularity: {popularity:.1f}\n")

        response_lines.append(
            "<i>Select an option below for detailed information.</i>"
        )
        response_lines.append("<i>Powered by TMDB</i>")

        response_text = "\n".join(response_lines)

        # Create buttons with pagination support
        buttons = create_tmdb_search_buttons(
            search_results, query, page, total_pages
        )

        return response_text, buttons

    except Exception as e:
        LOGGER.error(f"Error in TMDB search: {e}")
        return "❌ An error occurred while searching TMDB.", None


# Command Handler - Will be registered after bot initialization
async def tmdb_search_command(_, message: Message):
    """Handle TMDB search command"""
    # Check if TMDB module is enabled
    if not Config.TMDB_ENABLED:
        error_msg = await send_message(
            message,
            "❌ <b>TMDB module is currently disabled.</b>\n\nPlease contact the bot owner to enable it.",
        )
        # Schedule for auto-deletion after 5 minutes
        create_task(auto_delete_message(error_msg, message, time=300))
        return

    # Check if TMDB API key is configured
    if not Config.TMDB_API_KEY:
        error_msg = await send_message(
            message,
            "❌ <b>TMDB API key is not configured.</b>\n\nPlease contact the bot owner to configure the TMDB API key.",
        )
        # Schedule for auto-deletion after 5 minutes
        create_task(auto_delete_message(error_msg, message, time=300))
        return

    # Check if replying to a message
    if message.reply_to_message and message.reply_to_message.text:
        # Extract text from replied message
        query = message.reply_to_message.text.strip()
        k = await send_message(
            message,
            "<i>🔍 Searching TMDB for replied content...</i>",
        )
        is_reply = True
    elif " " in message.text:
        # User provided a search term in command
        query = message.text.split(" ", 1)[1]
        k = await send_message(message, "<i>🔍 Searching TMDB...</i>")
        is_reply = False
    else:
        # No search term provided
        error_msg = await send_message(
            message,
            "<i>Send Movie / TV Series / Person name along with /tmdb command or reply to a message containing the name</i>",
        )
        # Schedule for auto-deletion after 5 minutes
        create_task(auto_delete_message(error_msg, message, time=300))
        return

    try:
        # Search TMDB
        response_text, buttons = await tmdb_search(query)

        # Update the loading message with results
        if buttons:
            await edit_message(k, response_text, buttons)
        else:
            await edit_message(k, response_text)

        # If replying to a message, delete the original messages
        if is_reply:
            await delete_message(message)
            await delete_message(message.reply_to_message)

        # Schedule for auto-deletion after 10 minutes
        create_task(auto_delete_message(k, time=600))

    except Exception as e:
        LOGGER.error(f"Error in TMDB search command: {e}")
        await edit_message(
            k, "❌ An error occurred while searching TMDB. Please try again later."
        )
        # Schedule for auto-deletion after 5 minutes
        create_task(auto_delete_message(k, time=300))
