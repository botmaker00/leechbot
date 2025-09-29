import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import aiohttp
import pytz
from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    send_message,
)


class WeatherAPI:
    """Optimized OpenWeatherMap API client with comprehensive weather data support"""

    def __init__(self):
        self.api_key = Config.OPENWEATHER_API_KEY
        # Keep base_url for backward compatibility
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.geo_url = "https://api.openweathermap.org/geo/1.0"
        self.map_url = "https://tile.openweathermap.org/map"
        # Consolidated API endpoints for better performance
        self.endpoints = {
            "current": "https://api.openweathermap.org/data/2.5/weather",
            "forecast": "https://api.openweathermap.org/data/2.5/forecast",
            "hourly": "https://pro.openweathermap.org/data/2.5/forecast/hourly",
            "daily": "https://api.openweathermap.org/data/2.5/forecast/daily",
            "air_pollution": "https://api.openweathermap.org/data/2.5/air_pollution",
            "air_forecast": "https://api.openweathermap.org/data/2.5/air_pollution/forecast",
            "air_history": "https://api.openweathermap.org/data/2.5/air_pollution/history",
            "geocoding": "https://api.openweathermap.org/geo/1.0/direct",
            "reverse_geo": "https://api.openweathermap.org/geo/1.0/reverse",
            "onecall": "https://api.openweathermap.org/data/3.0/onecall",
            "fire_weather": "https://api.openweathermap.org/data/2.5/fwi",
            "solar": "https://api.openweathermap.org/energy/2.0/solar/interval_data",
            "history": "https://history.openweathermap.org/data/2.5/history/city",
            "statistics": "https://history.openweathermap.org/data/2.5/aggregated",
        }
        self.session = None
        # Cache for API responses to reduce redundant calls
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes cache

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create optimized aiohttp session"""
        if not self.session:
            connector = aiohttp.TCPConnector(
                limit=100,  # Connection pool limit
                limit_per_host=30,  # Per-host connection limit
                keepalive_timeout=30,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(total=15, connect=5)  # Reduced timeout
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={"User-Agent": "WeatherBot/1.0"},
            )
        return self.session

    async def close_session(self):
        """Close aiohttp session and clear cache"""
        if self.session:
            await self.session.close()
            self.session = None
        self._cache.clear()

    def _get_cache_key(self, endpoint: str, **params) -> str:
        """Generate cache key for API responses"""
        sorted_params = sorted(params.items())
        return f"{endpoint}:{':'.join(f'{k}={v}' for k, v in sorted_params)}"

    def _is_cache_valid(self, timestamp: float) -> bool:
        """Check if cached data is still valid"""
        return time.time() - timestamp < self._cache_ttl

    async def _make_request(self, endpoint: str, **params) -> dict[str, Any] | None:
        """Optimized API request with caching"""
        # Check cache first
        cache_key = self._get_cache_key(endpoint, **params)
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                return cached_data

        try:
            session = await self._get_session()
            url = self.endpoints[endpoint]
            params["appid"] = self.api_key

            # Add default parameters for weather requests
            if endpoint in ["current", "forecast", "hourly", "daily"]:
                params.setdefault("units", Config.WEATHER_UNITS)
                params.setdefault("lang", Config.WEATHER_LANGUAGE)

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Cache the response
                    self._cache[cache_key] = (data, time.time())
                    return data
                return None
        except Exception as e:
            LOGGER.error(f"API request error for {endpoint}: {e}")
            return None

    async def geocode_location(self, location: str) -> dict[str, Any] | None:
        """Convert location name to coordinates using Geocoding API"""
        try:
            # Check if API key is configured
            if not self.api_key:
                LOGGER.error("No OpenWeatherMap API key configured")
                return None

            session = await self._get_session()
            url = self.endpoints["geocoding"]
            params = {"q": location, "limit": 1, "appid": self.api_key}

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        result = data[0]
                        return {
                            "name": result.get("name", location),
                            "lat": result["lat"],
                            "lon": result["lon"],
                            "country": result.get("country", ""),
                            "state": result.get("state", ""),
                        }
                    return None
                if response.status == 401:
                    LOGGER.error("Invalid OpenWeatherMap API key")
                    return None
                LOGGER.error(f"Geocoding API error {response.status}")
                return None

        except Exception as e:
            LOGGER.error(f"Geocoding error for '{location}': {e}")
            return None

    async def get_current_weather(
        self, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Get current weather data with caching"""
        return await self._make_request("current", lat=lat, lon=lon)

    async def get_forecast_5day(
        self, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Get 5-day weather forecast with 3-hour intervals"""
        return await self._make_request("forecast", lat=lat, lon=lon)

    async def get_hourly_forecast(
        self, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Get hourly forecast for 4 days (96 timestamps) - Requires subscription"""
        return await self._make_request("hourly", lat=lat, lon=lon)

    async def get_daily_forecast(
        self, lat: float, lon: float, cnt: int = 16
    ) -> dict[str, Any] | None:
        """Get daily forecast up to 16 days - Requires subscription"""
        return await self._make_request("daily", lat=lat, lon=lon, cnt=cnt)

    async def get_air_pollution(
        self, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Get current air pollution data"""
        return await self._make_request("air_pollution", lat=lat, lon=lon)

    async def get_air_pollution_forecast(
        self, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Get air pollution forecast for 5 days"""
        return await self._make_request("air_forecast", lat=lat, lon=lon)

    async def get_air_pollution_history(
        self, lat: float, lon: float, start: int, end: int
    ) -> dict[str, Any] | None:
        """Get historical air pollution data"""
        return await self._make_request(
            "air_history", lat=lat, lon=lon, start=start, end=end
        )

    async def get_onecall_weather(
        self, lat: float, lon: float, exclude: str = ""
    ) -> dict[str, Any] | None:
        """Get comprehensive weather data using One Call API 3.0 - Requires subscription"""
        params = {"lat": lat, "lon": lon}
        if exclude:
            params["exclude"] = exclude
        return await self._make_request("onecall", **params)

    async def get_fire_weather_index(
        self, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Get Fire Weather Index - Requires subscription"""
        return await self._make_request("fire_weather", lat=lat, lon=lon)

    async def get_solar_radiation(
        self, lat: float, lon: float, start: int, end: int
    ) -> dict[str, Any] | None:
        """Get solar radiation data - Requires subscription"""
        return await self._make_request(
            "solar", lat=lat, lon=lon, start=start, end=end
        )

    async def get_weather_history(
        self, lat: float, lon: float, start: int, end: int
    ) -> dict[str, Any] | None:
        """Get historical weather data - Requires subscription"""
        return await self._make_request(
            "history", lat=lat, lon=lon, start=start, end=end
        )

    async def get_weather_statistics(
        self, lat: float, lon: float, start: int, end: int
    ) -> dict[str, Any] | None:
        """Get aggregated weather statistics - Requires subscription"""
        return await self._make_request(
            "statistics", lat=lat, lon=lon, start=start, end=end
        )

    async def check_api_subscription_level(self) -> dict[str, bool]:
        """Check which API features are available based on subscription"""
        features = {
            "current_weather": False,
            "forecast_5day": False,
            "air_pollution": False,
            "geocoding": False,
            "weather_maps": False,
            "hourly_forecast": False,
            "historical_weather": False,
            "fire_weather_index": False,
            "one_call_api": False,
        }

        try:
            # Test basic current weather API (available in all plans)
            session = await self._get_session()
            url = f"{self.base_url}/weather"
            params = {
                "lat": 51.5074,  # London coordinates
                "lon": -0.1278,
                "appid": self.api_key,
            }

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    features["current_weather"] = True
                    features["forecast_5day"] = True
                    features["air_pollution"] = True
                    features["geocoding"] = True
                    features["weather_maps"] = True
                elif response.status == 401:
                    LOGGER.error("Invalid API key")
                    return features

            # Test hourly forecast (requires paid subscription)
            url = "https://pro.openweathermap.org/data/2.5/forecast/hourly"
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    features["hourly_forecast"] = True

            # Test historical weather (requires paid subscription)
            url = "https://history.openweathermap.org/data/2.5/history/city"
            params.update(
                {"type": "hour", "start": 1609459200, "end": 1609545600}
            )  # Test dates
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    features["historical_weather"] = True

            # Test Fire Weather Index (requires special access)
            url = f"{self.base_url}/fwi"
            async with session.get(
                url, params={"lat": 51.5074, "lon": -0.1278, "appid": self.api_key}
            ) as response:
                if response.status == 200:
                    features["fire_weather_index"] = True

        except Exception as e:
            LOGGER.error(f"API subscription check error: {e}")

        return features

    async def get_solar_irradiance(
        self, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Get solar irradiance data (requires paid subscription)"""
        try:
            session = await self._get_session()
            url = "https://api.openweathermap.org/data/2.5/solar_irradiance"
            params = {"lat": lat, "lon": lon, "appid": self.api_key}

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            LOGGER.error(f"Solar irradiance error: {e}")
            return None

    async def get_weather_alerts(
        self, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Get weather alerts for location (requires One Call API 3.0)"""
        try:
            session = await self._get_session()
            url = "https://api.openweathermap.org/data/3.0/onecall"
            params = {
                "lat": lat,
                "lon": lon,
                "exclude": "minutely,hourly,daily",  # Only get alerts
                "appid": self.api_key,
            }

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("alerts", [])
                return None
        except Exception as e:
            LOGGER.error(f"Weather alerts error: {e}")
            return None

    async def validate_weather_data(self, data: dict[str, Any]) -> bool:
        """Validate weather data for consistency and accuracy"""
        if not Config.WEATHER_DATA_VALIDATION:
            return True

        try:
            # Basic validation checks
            if not data or "main" not in data:
                return False

            main = data["main"]

            # Temperature validation (-100°C to 60°C)
            temp = main.get("temp", 0)
            if temp < 173.15 or temp > 333.15:  # Kelvin
                LOGGER.warning(f"Invalid temperature: {temp}K")
                return False

            # Humidity validation (0-100%)
            humidity = main.get("humidity", 0)
            if humidity < 0 or humidity > 100:
                LOGGER.warning(f"Invalid humidity: {humidity}%")
                return False

            # Pressure validation (800-1200 hPa)
            pressure = main.get("pressure", 1013)
            if pressure < 800 or pressure > 1200:
                LOGGER.warning(f"Invalid pressure: {pressure} hPa")
                return False

            return True

        except Exception as e:
            LOGGER.error(f"Weather data validation error: {e}")
            return False

    async def check_api_subscription_level(self) -> dict[str, bool]:
        """Check which API features are available based on subscription"""
        features = {
            "current_weather": False,
            "forecast_5day": False,
            "air_pollution": False,
            "geocoding": False,
            "weather_maps": False,
            "hourly_forecast": False,
            "historical_weather": False,
            "fire_weather_index": False,
            "one_call_api": False,
            "weather_alerts": False,
            "solar_irradiance": False,
            "statistical_weather": False,
            "road_risk_api": False,
            "weather_maps_2_0": False,
            "weather_maps_hourly": False,
        }

        try:
            # Test basic current weather API (available in all plans)
            session = await self._get_session()
            url = f"{self.base_url}/weather"
            params = {
                "lat": 51.5074,  # London coordinates
                "lon": -0.1278,
                "appid": self.api_key,
            }

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    features["current_weather"] = True
                    features["forecast_5day"] = True
                    features["air_pollution"] = True
                    features["geocoding"] = True
                    features["weather_maps"] = True
                elif response.status == 401:
                    LOGGER.error("Invalid API key")
                    return features

            # Test hourly forecast (requires paid subscription)
            url = "https://pro.openweathermap.org/data/2.5/forecast/hourly"
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    features["hourly_forecast"] = True

            # Test historical weather (requires paid subscription)
            url = "https://history.openweathermap.org/data/2.5/history/city"
            params.update(
                {"type": "hour", "start": 1609459200, "end": 1609545600}
            )  # Test dates
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    features["historical_weather"] = True

            # Test Fire Weather Index (requires special access)
            url = f"{self.base_url}/fwi"
            async with session.get(
                url, params={"lat": 51.5074, "lon": -0.1278, "appid": self.api_key}
            ) as response:
                if response.status == 200:
                    features["fire_weather_index"] = True

            # Test One Call API 3.0 (includes weather alerts)
            url = "https://api.openweathermap.org/data/3.0/onecall"
            async with session.get(
                url, params={"lat": 51.5074, "lon": -0.1278, "appid": self.api_key}
            ) as response:
                if response.status == 200:
                    features["one_call_api"] = True
                    features["weather_alerts"] = True

            # Test Solar Irradiance API (requires paid subscription)
            url = "https://api.openweathermap.org/data/2.5/solar_irradiance"
            async with session.get(
                url, params={"lat": 51.5074, "lon": -0.1278, "appid": self.api_key}
            ) as response:
                if response.status == 200:
                    features["solar_irradiance"] = True

            # Test Statistical Weather API (requires paid subscription)
            url = "https://history.openweathermap.org/data/2.5/aggregated/year"
            async with session.get(
                url, params={"lat": 51.5074, "lon": -0.1278, "appid": self.api_key}
            ) as response:
                if response.status == 200:
                    features["statistical_weather"] = True

            # Test Road Risk API (requires paid subscription)
            url = "https://api.openweathermap.org/data/2.5/roadrisk"
            async with session.get(
                url, params={"coordinates": "51.5074,-0.1278", "appid": self.api_key}
            ) as response:
                if response.status == 200:
                    features["road_risk_api"] = True

            # Test Weather Maps 2.0 (requires paid subscription)
            url = (
                "https://maps.openweathermap.org/maps/2.0/weather/1h/temp_new/1/0/0"
            )
            async with session.get(url, params={"appid": self.api_key}) as response:
                if response.status == 200:
                    features["weather_maps_2_0"] = True
                    features["weather_maps_hourly"] = True

        except Exception as e:
            LOGGER.error(f"API subscription check error: {e}")

        return features


# Initialize weather API
weather_api = WeatherAPI()


class WeatherFormatter:
    """Format weather data for display"""

    @staticmethod
    def format_current_weather(
        weather_data: dict[str, Any], location_info: dict[str, Any]
    ) -> str:
        """Format current weather data for text display"""
        try:
            main = weather_data["main"]
            weather = weather_data["weather"][0]
            wind = weather_data.get("wind", {})

            # Temperature unit
            unit_symbol = (
                "°C"
                if Config.WEATHER_UNITS == "metric"
                else "°F"
                if Config.WEATHER_UNITS == "imperial"
                else "K"
            )

            # Format location
            location_name = location_info["name"]
            if location_info.get("state"):
                location_name += f", {location_info['state']}"
            if location_info.get("country"):
                location_name += f", {location_info['country']}"

            # Get weather emoji
            weather_emojis = {
                "clear": "☀️" if "d" in weather["icon"] else "🌙",
                "clouds": "☁️",
                "rain": "🌧️",
                "drizzle": "🌦️",
                "thunderstorm": "⛈️",
                "snow": "❄️",
                "mist": "🌫️",
                "smoke": "🌫️",
                "haze": "🌫️",
                "dust": "🌫️",
                "fog": "🌫️",
                "sand": "🌫️",
                "ash": "🌋",
                "squall": "💨",
                "tornado": "🌪️",
            }
            emoji = weather_emojis.get(weather["main"].lower(), "🌤️")

            text = f"🌤️ <b>Weather in {location_name}</b>\n\n"
            text += f"{emoji} <b>{weather['description'].title()}</b>\n"
            text += f"🌡️ <b>Temperature:</b> <code>{main['temp']:.1f}{unit_symbol}</code>\n"
            text += f"🤔 <b>Feels like:</b> <code>{main['feels_like']:.1f}{unit_symbol}</code>\n"
            text += f"📊 <b>Min/Max:</b> <code>{main['temp_min']:.1f}{unit_symbol}</code> / <code>{main['temp_max']:.1f}{unit_symbol}</code>\n"
            text += f"💧 <b>Humidity:</b> <code>{main['humidity']}%</code>\n"
            text += f"🌪️ <b>Pressure:</b> <code>{main['pressure']} hPa</code>\n"

            if "visibility" in weather_data:
                visibility_km = weather_data["visibility"] / 1000
                text += f"👁️ <b>Visibility:</b> <code>{visibility_km:.1f} km</code>\n"

            if wind:
                wind_speed = wind.get("speed", 0)
                wind_dir = wind.get("deg", 0)
                direction = WeatherFormatter.get_wind_direction(wind_dir)
                text += f"💨 <b>Wind:</b> <code>{wind_speed} m/s, {wind_dir}° ({direction})</code>\n"
                if "gust" in wind:
                    text += f"🌬️ <b>Wind Gust:</b> <code>{wind['gust']} m/s</code>\n"

            if "clouds" in weather_data:
                text += f"☁️ <b>Cloudiness:</b> <code>{weather_data['clouds']['all']}%</code>\n"

            # Sunrise/Sunset
            if "sys" in weather_data:
                sys_data = weather_data["sys"]
                if "sunrise" in sys_data and "sunset" in sys_data:
                    sunrise = datetime.fromtimestamp(sys_data["sunrise"]).strftime(
                        "%H:%M"
                    )
                    sunset = datetime.fromtimestamp(sys_data["sunset"]).strftime(
                        "%H:%M"
                    )
                    text += f"🌅 <b>Sunrise:</b> <code>{sunrise}</code>\n"
                    text += f"🌇 <b>Sunset:</b> <code>{sunset}</code>\n"

            # Update time
            update_time = datetime.fromtimestamp(weather_data["dt"]).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
            text += f"\n📅 <b>Updated:</b> <code>{update_time}</code>"

            return text

        except Exception as e:
            LOGGER.error(f"Weather formatting error: {e}")
            return "❌ Error formatting weather data"

    @staticmethod
    def get_wind_direction(degrees: float) -> str:
        """Convert wind direction degrees to compass direction"""
        directions = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]
        index = round(degrees / 22.5) % 16
        return directions[index]

    @staticmethod
    def format_air_pollution(pollution_data: dict[str, Any]) -> str:
        """Format air pollution data"""
        try:
            if not pollution_data or "list" not in pollution_data:
                return "❌ No air pollution data available"

            data = pollution_data["list"][0]
            aqi = data["main"]["aqi"]
            components = data["components"]

            # AQI levels
            aqi_levels = {
                1: "Good 😊",
                2: "Fair 😐",
                3: "Moderate 😷",
                4: "Poor 😨",
                5: "Very Poor 💀",
            }

            text = "🌬️ <b>Air Quality Index</b>\n\n"
            text += f"📊 <b>AQI Level:</b> <code>{aqi}</code> - <i>{aqi_levels.get(aqi, 'Unknown')}</i>\n\n"
            text += "<b>Pollutants (μg/m³):</b>\n"
            text += f"• <b>CO:</b> <code>{components.get('co', 0):.2f}</code>\n"
            text += f"• <b>NO:</b> <code>{components.get('no', 0):.2f}</code>\n"
            text += f"• <b>NO₂:</b> <code>{components.get('no2', 0):.2f}</code>\n"
            text += f"• <b>O₃:</b> <code>{components.get('o3', 0):.2f}</code>\n"
            text += f"• <b>SO₂:</b> <code>{components.get('so2', 0):.2f}</code>\n"
            text += (
                f"• <b>PM2.5:</b> <code>{components.get('pm2_5', 0):.2f}</code>\n"
            )
            text += f"• <b>PM10:</b> <code>{components.get('pm10', 0):.2f}</code>\n"
            text += f"• <b>NH₃:</b> <code>{components.get('nh3', 0):.2f}</code>\n"

            return text

        except Exception as e:
            LOGGER.error(f"Air pollution formatting error: {e}")
            return "❌ Error formatting air pollution data"

    @staticmethod
    def format_air_pollution_forecast(forecast_data: dict[str, Any]) -> str:
        """Format air pollution forecast data"""
        try:
            if not forecast_data or "list" not in forecast_data:
                return "❌ Air pollution forecast not available"

            text = "🌬️ <b>Air Quality Forecast (Next 4 Days)</b>\n\n"

            aqi_levels = {
                1: "Good 😊",
                2: "Fair 😐",
                3: "Moderate 😷",
                4: "Poor 😨",
                5: "Very Poor 💀",
            }

            # Group by day and show daily averages
            daily_data = {}
            for item in forecast_data["list"][:24]:  # Next 24 hours
                dt = datetime.fromtimestamp(item["dt"], tz=UTC)
                day_key = dt.strftime("%Y-%m-%d")

                if day_key not in daily_data:
                    daily_data[day_key] = []
                daily_data[day_key].append(item["main"]["aqi"])

            for day, aqi_values in list(daily_data.items())[:4]:
                avg_aqi = round(sum(aqi_values) / len(aqi_values))
                day_name = datetime.strptime(day, "%Y-%m-%d").strftime("%a, %b %d")
                text += f"<b>{day_name}:</b> <code>{aqi_levels.get(avg_aqi, 'Unknown')}</code>\n"

            return text

        except Exception as e:
            LOGGER.error(f"Air pollution forecast formatting error: {e}")
            return "❌ Error formatting air pollution forecast"

    @staticmethod
    def format_fire_weather_index(fwi_data: dict[str, Any]) -> str:
        """Format Fire Weather Index data"""
        try:
            if not fwi_data or "list" not in fwi_data:
                return "❌ Fire Weather Index not available"

            data = fwi_data["list"][0]
            fwi_value = data["main"]["fwi"]
            danger_rating = data["danger_rating"]

            # Fire danger emojis
            danger_emojis = {
                "0": "🟢",  # Very low
                "1": "🟡",  # Low
                "2": "🟠",  # Moderate
                "3": "🔴",  # High
                "4": "🟣",  # Very high
                "5": "⚫",  # Extreme
            }

            emoji = danger_emojis.get(str(danger_rating["value"]), "🔥")

            text = "🔥 **Fire Weather Index**\n\n"
            text += f"**Current FWI**: {fwi_value:.1f}\n"
            text += f"**Danger Level**: {emoji} {danger_rating['description']}\n\n"
            text += "**Risk Assessment:**\n"

            if fwi_value < 5.2:
                text += "• Very low fire danger\n• Safe conditions for outdoor activities"
            elif fwi_value < 11.2:
                text += "• Low fire danger\n• Exercise normal caution"
            elif fwi_value < 21.3:
                text += "• Moderate fire danger\n• Be cautious with fire sources"
            elif fwi_value < 38.0:
                text += "• High fire danger\n• Avoid outdoor burning"
            elif fwi_value < 50.0:
                text += "• Very high fire danger\n• Extreme caution required"
            else:
                text += "• Extreme fire danger\n• No outdoor burning permitted"

            return text

        except Exception as e:
            LOGGER.error(f"Fire weather index formatting error: {e}")
            return "❌ Error formatting fire weather index"

    @staticmethod
    def format_historical_weather(historical_data: dict[str, Any]) -> str:
        """Format historical weather data"""
        try:
            if not historical_data or "list" not in historical_data:
                return "❌ Historical weather data not available"

            text = "📊 **Historical Weather Data**\n\n"

            # Calculate averages from historical data
            temps = []
            humidity_vals = []
            pressure_vals = []

            for item in historical_data["list"]:
                temps.append(item["main"]["temp"])
                humidity_vals.append(item["main"]["humidity"])
                pressure_vals.append(item["main"]["pressure"])

            if temps:
                avg_temp = sum(temps) / len(temps)
                min_temp = min(temps)
                max_temp = max(temps)
                avg_humidity = sum(humidity_vals) / len(humidity_vals)
                avg_pressure = sum(pressure_vals) / len(pressure_vals)

                text += "**Temperature:**\n"
                text += f"• Average: {avg_temp:.1f}°C\n"
                text += f"• Range: {min_temp:.1f}°C - {max_temp:.1f}°C\n\n"
                text += "**Other Conditions:**\n"
                text += f"• Humidity: {avg_humidity:.0f}%\n"
                text += f"• Pressure: {avg_pressure:.0f} hPa\n"
                text += f"• Data Points: {len(temps)}\n"

            return text

        except Exception as e:
            LOGGER.error(f"Historical weather formatting error: {e}")
            return "❌ Error formatting historical weather data"

    @staticmethod
    def format_subscription_info(features: dict[str, bool]) -> str:
        """Format API subscription information"""
        text = "🔑 <b>API Subscription Status</b>\n\n"

        # Free features
        text += "<b>✅ Free Features:</b>\n"
        free_features = [
            ("current_weather", "Current Weather"),
            ("forecast_5day", "5-Day Forecast"),
            ("air_pollution", "Air Quality Data"),
            ("geocoding", "Location Search"),
            ("weather_maps", "Weather Maps"),
        ]

        for key, name in free_features:
            status = "✅" if features.get(key, False) else "❌"
            text += f"• <code>{status}</code> {name}\n"

        # Premium features
        text += "\n<b>💎 Premium Features:</b>\n"
        premium_features = [
            ("hourly_forecast", "Hourly Forecast (4 days)"),
            ("historical_weather", "Historical Weather"),
            ("fire_weather_index", "Fire Weather Index"),
            ("one_call_api", "One Call API 3.0"),
        ]

        for key, name in premium_features:
            status = "✅" if features.get(key, False) else "❌"
            text += f"• <code>{status}</code> {name}\n"

        # Add upgrade info if needed
        if not any(features.get(key, False) for key, _ in premium_features):
            text += "\n💡 <b>Upgrade to access premium features:</b>\n"
            text += "• Visit <a href='https://openweathermap.org/price'>OpenWeatherMap Pricing</a>\n"
            text += "• Choose a paid plan for advanced features"

        return text

    @staticmethod
    def format_statistical_weather(stats_data: dict[str, Any]) -> str:
        """Format statistical weather data"""
        try:
            if not stats_data:
                return "❌ Statistical weather data not available"

            text = "📊 **Statistical Weather Data**\n\n"

            # Temperature statistics
            if "temp" in stats_data:
                temp_stats = stats_data["temp"]
                text += "**Temperature Statistics:**\n"
                text += f"• Average: {temp_stats.get('mean', 0):.1f}°C\n"
                text += f"• Minimum: {temp_stats.get('min', 0):.1f}°C\n"
                text += f"• Maximum: {temp_stats.get('max', 0):.1f}°C\n"
                text += (
                    f"• Standard Deviation: {temp_stats.get('std_dev', 0):.1f}°C\n\n"
                )

            # Precipitation statistics
            if "precipitation" in stats_data:
                precip_stats = stats_data["precipitation"]
                text += "**Precipitation Statistics:**\n"
                text += f"• Average: {precip_stats.get('mean', 0):.1f}mm\n"
                text += f"• Maximum: {precip_stats.get('max', 0):.1f}mm\n"
                text += f"• Total Days: {precip_stats.get('num', 0)}\n\n"

            # Humidity statistics
            if "humidity" in stats_data:
                humidity_stats = stats_data["humidity"]
                text += "**Humidity Statistics:**\n"
                text += f"• Average: {humidity_stats.get('mean', 0):.0f}%\n"
                text += f"• Minimum: {humidity_stats.get('min', 0):.0f}%\n"
                text += f"• Maximum: {humidity_stats.get('max', 0):.0f}%\n"

            return text

        except Exception as e:
            LOGGER.error(f"Statistical weather formatting error: {e}")
            return "❌ Error formatting statistical weather data"

    @staticmethod
    def format_weather_alerts(alerts_data: list[dict[str, Any]]) -> str:
        """Format weather alerts data"""
        try:
            if not alerts_data:
                return "✅ No active weather alerts"

            text = "⚠️ **Active Weather Alerts**\n\n"

            for i, alert in enumerate(alerts_data[:5], 1):  # Limit to 5 alerts
                sender = alert.get("sender_name", "Weather Service")
                event = alert.get("event", "Weather Alert")
                description = alert.get("description", "No description available")

                # Truncate long descriptions
                if len(description) > 200:
                    description = description[:200] + "..."

                text += f"**Alert {i}: {event}**\n"
                text += f"• Source: {sender}\n"
                text += f"• Details: {description}\n"

                # Add timing if available
                if "start" in alert:
                    start_time = datetime.fromtimestamp(alert["start"], tz=UTC)
                    text += f"• Start: {start_time.strftime('%Y-%m-%d %H:%M UTC')}\n"

                if "end" in alert:
                    end_time = datetime.fromtimestamp(alert["end"], tz=UTC)
                    text += f"• End: {end_time.strftime('%Y-%m-%d %H:%M UTC')}\n"

                text += "\n"

            if len(alerts_data) > 5:
                text += f"... and {len(alerts_data) - 5} more alerts"

            return text

        except Exception as e:
            LOGGER.error(f"Weather alerts formatting error: {e}")
            return "❌ Error formatting weather alerts"

    @staticmethod
    def format_solar_irradiance(solar_data: dict[str, Any]) -> str:
        """Format solar irradiance data"""
        try:
            if not solar_data:
                return "❌ Solar irradiance data not available"

            text = "☀️ **Solar Irradiance Data**\n\n"

            if "irradiance" in solar_data:
                irradiance = solar_data["irradiance"]
                text += f"**Current Irradiance**: {irradiance:.2f} W/m²\n"

            if "uvi" in solar_data:
                uvi = solar_data["uvi"]
                text += f"**UV Index**: {uvi:.1f}\n"

                # UV Index interpretation
                if uvi <= 2:
                    text += "• Risk Level: Low 🟢\n"
                elif uvi <= 5:
                    text += "• Risk Level: Moderate 🟡\n"
                elif uvi <= 7:
                    text += "• Risk Level: High 🟠\n"
                elif uvi <= 10:
                    text += "• Risk Level: Very High 🔴\n"
                else:
                    text += "• Risk Level: Extreme 🟣\n"

            if "sunrise" in solar_data and "sunset" in solar_data:
                sunrise = datetime.fromtimestamp(solar_data["sunrise"], tz=UTC)
                sunset = datetime.fromtimestamp(solar_data["sunset"], tz=UTC)
                text += "\n**Sun Times:**\n"
                text += f"• Sunrise: {sunrise.strftime('%H:%M UTC')}\n"
                text += f"• Sunset: {sunset.strftime('%H:%M UTC')}\n"

            return text

        except Exception as e:
            LOGGER.error(f"Solar irradiance formatting error: {e}")
            return "❌ Error formatting solar irradiance data"

    @staticmethod
    def format_road_risk_weather(road_data: dict[str, Any]) -> str:
        """Format road risk weather data"""
        try:
            if not road_data:
                return "❌ Road risk weather data not available"

            text = "🛣️ **Road Risk Weather Assessment**\n\n"

            if "alerts" in road_data:
                alerts = road_data["alerts"]
                if alerts:
                    text += "**Active Road Risks:**\n"
                    for alert in alerts[:3]:  # Limit to 3 alerts
                        risk_type = alert.get("event", "Unknown Risk")
                        severity = alert.get("severity", "Unknown")
                        text += f"• {risk_type}: {severity}\n"
                    text += "\n"
                else:
                    text += "✅ No active road risks detected\n\n"

            if "weather_conditions" in road_data:
                conditions = road_data["weather_conditions"]
                text += "**Current Conditions:**\n"
                text += f"• Temperature: {conditions.get('temp', 0):.1f}°C\n"
                text += (
                    f"• Visibility: {conditions.get('visibility', 0) / 1000:.1f}km\n"
                )
                text += f"• Wind Speed: {conditions.get('wind_speed', 0):.1f}m/s\n"

                if conditions.get("precipitation"):
                    text += (
                        f"• Precipitation: {conditions['precipitation']:.1f}mm/h\n"
                    )

            return text

        except Exception as e:
            LOGGER.error(f"Road risk weather formatting error: {e}")
            return "❌ Error formatting road risk weather data"

    @staticmethod
    def format_forecast_summary(forecast_data: dict[str, Any]) -> str:
        """Format 5-day forecast summary"""
        try:
            if not forecast_data or "list" not in forecast_data:
                return "❌ No forecast data available"

            forecasts = forecast_data["list"]
            city = forecast_data.get("city", {})

            text = "📅 <b>5-Day Weather Forecast</b>\n"
            if city.get("name"):
                text += f"📍 <b>Location:</b> <code>{city['name']}</code>\n\n"

            # Group forecasts by date
            daily_forecasts = {}
            for forecast in forecasts[:40]:  # Limit to 5 days
                date = datetime.fromtimestamp(forecast["dt"]).date()
                if date not in daily_forecasts:
                    daily_forecasts[date] = []
                daily_forecasts[date].append(forecast)

            unit_symbol = (
                "°C"
                if Config.WEATHER_UNITS == "metric"
                else "°F"
                if Config.WEATHER_UNITS == "imperial"
                else "K"
            )

            for date, day_forecasts in list(daily_forecasts.items())[:5]:
                # Get min/max temps for the day
                temps = [f["main"]["temp"] for f in day_forecasts]
                min_temp = min(temps)
                max_temp = max(temps)

                # Get most common weather condition
                weather_conditions = [f["weather"][0] for f in day_forecasts]
                main_weather = max(
                    {w["main"] for w in weather_conditions},
                    key=[w["main"] for w in weather_conditions].count,
                )

                # Get representative weather info
                repr_weather = next(
                    w for w in weather_conditions if w["main"] == main_weather
                )
                weather_emojis = {
                    "clear": "☀️" if "d" in repr_weather["icon"] else "🌙",
                    "clouds": "☁️",
                    "rain": "🌧️",
                    "drizzle": "🌦️",
                    "thunderstorm": "⛈️",
                    "snow": "❄️",
                    "mist": "🌫️",
                    "smoke": "🌫️",
                    "haze": "🌫️",
                    "dust": "🌫️",
                    "fog": "🌫️",
                    "sand": "🌫️",
                    "ash": "🌋",
                    "squall": "💨",
                    "tornado": "🌪️",
                }
                emoji = weather_emojis.get(main_weather.lower(), "🌤️")

                date_str = date.strftime("%a, %b %d")
                text += f"{emoji} <b>{date_str}</b>\n"
                text += f"   <i>{repr_weather['description'].title()}</i>\n"
                text += f"   🌡️ <code>{min_temp:.1f}{unit_symbol} - {max_temp:.1f}{unit_symbol}</code>\n\n"

            return text

        except Exception as e:
            LOGGER.error(f"Forecast formatting error: {e}")
            return "❌ Error formatting forecast data"


def create_weather_keyboard(
    location_info: dict[str, Any], features: dict[str, bool] | None = None
) -> InlineKeyboardMarkup:
    """Create inline keyboard for weather options based on available features"""
    lat, lon = location_info["lat"], location_info["lon"]
    location_key = f"{lat},{lon}"

    # Basic free features (always available)
    keyboard = [
        [
            InlineKeyboardButton(
                "🌡️ Current", callback_data=f"weather_current_{location_key}"
            ),
            InlineKeyboardButton(
                "📅 5-Day Forecast", callback_data=f"weather_forecast_{location_key}"
            ),
        ],
    ]

    # Air quality and maps (show by default, these are free features)
    keyboard.append(
        [
            InlineKeyboardButton(
                "🌬️ Air Quality", callback_data=f"weather_air_{location_key}"
            ),
            InlineKeyboardButton(
                "🌬️ AQI Forecast",
                callback_data=f"weather_air_forecast_{location_key}",
            ),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🗺️ Weather Maps", callback_data=f"weather_map_{location_key}"
            ),
            InlineKeyboardButton(
                "🗺️ Advanced Maps", callback_data=f"weather_map_2_{location_key}"
            ),
        ]
    )

    # Premium features (only show if available)
    premium_row = []
    if features and features.get("hourly_forecast", False):
        premium_row.append(
            InlineKeyboardButton(
                "⏰ Hourly Forecast", callback_data=f"weather_hourly_{location_key}"
            )
        )

    if features and features.get("historical_weather", False):
        premium_row.append(
            InlineKeyboardButton(
                "📊 Historical", callback_data=f"weather_historical_{location_key}"
            )
        )

    if premium_row:
        keyboard.append(premium_row)

    # Fire weather index (special access required)
    if features and features.get("fire_weather_index", False):
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔥 Fire Weather Index",
                    callback_data=f"weather_fire_{location_key}",
                ),
            ]
        )

    # Advanced premium features
    advanced_row = []
    if features and features.get("weather_alerts", False):
        advanced_row.append(
            InlineKeyboardButton(
                "⚠️ Weather Alerts", callback_data=f"weather_alerts_{location_key}"
            )
        )

    if features and features.get("solar_irradiance", False):
        advanced_row.append(
            InlineKeyboardButton(
                "☀️ Solar Data", callback_data=f"weather_solar_{location_key}"
            )
        )

    if advanced_row:
        keyboard.append(advanced_row)

    # Statistical and road risk features
    if features and features.get("statistical_weather", False):
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📊 Statistical Data",
                    callback_data=f"weather_stats_{location_key}",
                ),
            ]
        )

    if features and features.get("road_risk_api", False):
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🛣️ Road Risk", callback_data=f"weather_road_{location_key}"
                ),
            ]
        )

    # Control buttons
    keyboard.extend(
        [
            [
                InlineKeyboardButton(
                    "📊 Detailed Info",
                    callback_data=f"weather_detailed_{location_key}",
                ),
                InlineKeyboardButton(
                    "🔑 Subscription",
                    callback_data=f"weather_subscription_{location_key}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔄 Refresh", callback_data=f"weather_refresh_{location_key}"
                ),
                InlineKeyboardButton("❌ Close", callback_data="weather_close"),
            ],
        ]
    )

    return InlineKeyboardMarkup(keyboard)


async def check_weather_risks(
    weather_data: dict[str, Any], location_name: str
) -> str | None:
    """Check for weather risks and return warning message"""
    try:
        risks = []

        # Temperature risks
        temp = weather_data["main"]["temp"]
        if Config.WEATHER_UNITS == "metric":
            if temp > 35:
                risks.append("🔥 Extreme heat warning")
            elif temp < -10:
                risks.append("🧊 Extreme cold warning")
        elif Config.WEATHER_UNITS == "imperial":
            if temp > 95:
                risks.append("🔥 Extreme heat warning")
            elif temp < 14:
                risks.append("🧊 Extreme cold warning")

        # Weather condition risks
        weather_main = weather_data["weather"][0]["main"].lower()
        if weather_main == "thunderstorm":
            risks.append("⛈️ Thunderstorm warning")
        elif weather_main == "snow":
            risks.append("❄️ Snow warning")
        elif weather_main in ["tornado", "squall"]:
            risks.append("🌪️ Severe weather warning")

        # Wind risks
        if "wind" in weather_data:
            wind_speed = weather_data["wind"]["speed"]
            if wind_speed > 15:  # m/s
                risks.append("💨 High wind warning")

        # Visibility risks
        if "visibility" in weather_data:
            visibility = weather_data["visibility"]
            if visibility < 1000:  # Less than 1km
                risks.append("🌫️ Low visibility warning")

        if risks:
            risk_text = f"⚠️ **Weather Risks in {location_name}:**\n"
            risk_text += "\n".join(f"• {risk}" for risk in risks)
            return risk_text

        return None

    except Exception as e:
        LOGGER.error(f"Weather risk check error: {e}")
        return None


# Command Handlers
@new_task
async def weather_command(_client: TgClient, message: Message):
    """Handle /weather command"""
    try:
        if not Config.WEATHER_ENABLED:
            await send_message(message, "❌ Weather functionality is disabled.")
            return

        if not Config.OPENWEATHER_API_KEY:
            await send_message(message, "❌ OpenWeatherMap API key not configured.")
            return

        # Parse location from command - handle both message.command and message.text
        location = None

        # Try to get location from message.command first
        if message.command and len(message.command) > 1:
            location = " ".join(message.command[1:]).strip()
        # Fallback: parse from message.text if command parsing failed
        elif message.text:
            # Split by whitespace and take everything after the first word (command)
            parts = message.text.strip().split()
            if len(parts) > 1:
                location = " ".join(parts[1:]).strip()

        # Use default location if no location provided
        if not location or location.strip() == "":
            location = Config.WEATHER_PLACE

        if not location or location.strip() == "":
            await send_message(
                message,
                "❌ Please provide a location or set WEATHER_PLACE in config.",
            )
            return

        # Show loading message
        loading_msg = await send_message(message, "🔄 Fetching weather data...")

        # Geocode location first
        location_info = await weather_api.geocode_location(location)
        if not location_info:
            # Check if it's an API key issue
            if not Config.OPENWEATHER_API_KEY:
                await edit_message(
                    loading_msg,
                    "❌ OpenWeatherMap API key not configured. Please set OPENWEATHER_API_KEY in config.",
                )
            else:
                await edit_message(
                    loading_msg,
                    f"❌ Location '{location}' not found or API key is invalid.",
                )
            return

        # Get current weather
        weather_data = await weather_api.get_current_weather(
            location_info["lat"], location_info["lon"]
        )

        if not weather_data:
            await edit_message(loading_msg, "❌ Failed to fetch weather data.")
            return

        # Check API subscription level (with fallback)
        try:
            features = await weather_api.check_api_subscription_level()
        except Exception as e:
            LOGGER.error(f"Subscription check failed: {e}")
            # Fallback to basic features
            features = {
                "current_weather": True,
                "forecast_5day": True,
                "air_pollution": True,
                "weather_maps": True,
                "hourly_forecast": False,
                "historical_weather": False,
                "fire_weather_index": False,
            }

        # Format weather text
        weather_text = WeatherFormatter.format_current_weather(
            weather_data, location_info
        )

        # Add subscription info if premium features are not available
        if not any(
            features.get(key, False)
            for key in [
                "hourly_forecast",
                "historical_weather",
                "fire_weather_index",
            ]
        ):
            weather_text += "\n\n💡 *Upgrade to premium for hourly forecasts, historical data, and fire weather index*"

        # Create keyboard with available features
        keyboard = create_weather_keyboard(location_info, features)

        # Send weather message
        await send_message(message, weather_text, buttons=keyboard)

        # Delete loading message
        await delete_message(loading_msg)

        # Check for weather risks and notify owner if enabled
        if Config.WEATHER_RISK_NOTIFICATIONS:
            risk_message = await check_weather_risks(
                weather_data, location_info["name"]
            )
            if risk_message:
                try:
                    await TgClient.bot.send_message(Config.OWNER_ID, risk_message)
                except Exception as e:
                    LOGGER.error(f"Failed to send risk notification: {e}")

    except Exception as e:
        LOGGER.error(f"Weather command error: {e}")
        await send_message(message, f"❌ Error: {e!s}")


@new_task
async def weather_map_command(_client: TgClient, message: Message):
    """Handle /weathermap command"""
    try:
        if not Config.WEATHER_ENABLED or not Config.OPENWEATHER_API_KEY:
            await send_message(
                message, "❌ Weather functionality is not properly configured."
            )
            return

        # Parse location from command - handle both message.command and message.text
        location = None

        # Try to get location from message.command first
        if message.command and len(message.command) > 1:
            location = " ".join(message.command[1:]).strip()
        # Fallback: parse from message.text if command parsing failed
        elif message.text:
            # Split by whitespace and take everything after the first word (command)
            parts = message.text.strip().split()
            if len(parts) > 1:
                location = " ".join(parts[1:]).strip()

        # Use default location if no location provided
        if not location or location.strip() == "":
            location = Config.WEATHER_PLACE

        if not location:
            await send_message(message, "❌ Please provide a location.")
            return

        # Show available map layers
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🌡️ Temperature", callback_data=f"map_temp_{location}"
                    ),
                    InlineKeyboardButton(
                        "☁️ Clouds", callback_data=f"map_clouds_{location}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🌧️ Precipitation",
                        callback_data=f"map_precipitation_{location}",
                    ),
                    InlineKeyboardButton(
                        "🌪️ Pressure", callback_data=f"map_pressure_{location}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "💨 Wind", callback_data=f"map_wind_{location}"
                    ),
                    InlineKeyboardButton("❌ Close", callback_data="weather_close"),
                ],
            ]
        )

        await send_message(
            message,
            f"🗺️ **Weather Maps for {location}**\n\nSelect a map layer:",
            buttons=keyboard,
        )

    except Exception as e:
        LOGGER.error(f"Weather map command error: {e}")
        await send_message(message, f"❌ Error: {e!s}")


# Callback Query Handlers
@new_task
async def weather_callback_handler(_client: TgClient, callback_query: CallbackQuery):
    """Handle weather-related callback queries"""
    try:
        data = callback_query.data

        if data == "weather_close":
            await callback_query.message.delete()
            return

        # Parse callback data - handle complex actions with underscores
        if data.startswith("weather_air_forecast_"):
            action = "air_forecast"
            location_key = data.replace("weather_air_forecast_", "")
        elif data.startswith("weather_map_2_"):
            action = "map_2"
            location_key = data.replace("weather_map_2_", "")
        else:
            parts = data.split("_", 2)
            if len(parts) < 3:
                await callback_query.answer("❌ Invalid callback data")
                return
            action = parts[1]
            location_key = parts[2]

        # Parse coordinates
        try:
            lat, lon = map(float, location_key.split(","))
        except ValueError:
            await callback_query.answer("❌ Invalid location data")
            return

        # Show loading
        await callback_query.answer("🔄 Loading...")

        if action == "current":
            # Get current weather
            weather_data = await weather_api.get_current_weather(lat, lon)
            if weather_data:
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                text = WeatherFormatter.format_current_weather(
                    weather_data, location_info
                )
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                await callback_query.answer("❌ Failed to fetch current weather")

        elif action == "forecast":
            # Get 5-day forecast
            forecast_data = await weather_api.get_forecast_5day(lat, lon)
            if forecast_data:
                text = WeatherFormatter.format_forecast_summary(forecast_data)
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                await callback_query.answer("❌ Failed to fetch forecast")

        elif action == "air":
            # Get air pollution data
            pollution_data = await weather_api.get_air_pollution(lat, lon)
            if pollution_data:
                text = WeatherFormatter.format_air_pollution(pollution_data)
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                await callback_query.answer("❌ Failed to fetch air quality data")

        elif (
            action == "air" and len(parts) > 3 and parts[2] == "forecast"
        ) or action == "air_forecast":
            # Get air pollution forecast
            pollution_forecast = await weather_api.get_air_pollution_forecast(
                lat, lon
            )
            if pollution_forecast:
                text = WeatherFormatter.format_air_pollution_forecast(
                    pollution_forecast
                )
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                await callback_query.answer(
                    "❌ Failed to fetch air quality forecast"
                )

        elif action == "subscription":
            # Show subscription information
            features = await weather_api.check_api_subscription_level()
            text = WeatherFormatter.format_subscription_info(features)
            location_info = {"lat": lat, "lon": lon, "name": "Location"}
            keyboard = create_weather_keyboard(location_info, features)
            await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "fire":
            # Get fire weather index (requires special access)
            fire_data = await weather_api.get_fire_weather_index(lat, lon)
            if fire_data:
                text = WeatherFormatter.format_fire_weather_index(fire_data)
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                text = "❌ Fire Weather Index not available.\n"
                text += "This feature requires special access from OpenWeatherMap."
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "historical":
            # Get historical weather data (requires paid subscription)
            end_time = int(time.time())
            start_time = end_time - (7 * 24 * 3600)  # 7 days ago

            historical_data = await weather_api.get_historical_weather(
                lat, lon, start_time, end_time
            )
            if historical_data:
                text = WeatherFormatter.format_historical_weather(historical_data)
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                text = "❌ Historical weather data not available.\n"
                text += "This feature requires a paid OpenWeatherMap subscription."
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "hourly":
            # Get hourly forecast (requires subscription)
            hourly_data = await weather_api.get_hourly_forecast(lat, lon)
            if hourly_data:
                text = "⏰ **Hourly Forecast**\n\n"
                text += "This feature requires a paid OpenWeatherMap subscription.\n"
                text += "Please upgrade your API plan to access hourly forecasts."
            else:
                text = "❌ Hourly forecast not available.\n"
                text += "This feature requires a paid OpenWeatherMap subscription."

            location_info = {"lat": lat, "lon": lon, "name": "Location"}
            keyboard = create_weather_keyboard(location_info)
            await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "alerts":
            # Get weather alerts (requires One Call API 3.0)
            alerts_data = await weather_api.get_weather_alerts(lat, lon)
            if alerts_data:
                text = WeatherFormatter.format_weather_alerts(alerts_data)
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                text = "❌ Weather alerts not available.\n"
                text += "This feature requires One Call API 3.0 subscription."
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "solar":
            # Get solar irradiance data (requires paid subscription)
            solar_data = await weather_api.get_solar_irradiance(lat, lon)
            if solar_data:
                text = WeatherFormatter.format_solar_irradiance(solar_data)
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                text = "❌ Solar irradiance data not available.\n"
                text += "This feature requires a paid OpenWeatherMap subscription."
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "stats":
            # Get statistical weather data (requires paid subscription)
            stats_data = await weather_api.get_statistical_weather(lat, lon, "year")
            if stats_data:
                text = WeatherFormatter.format_statistical_weather(stats_data)
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                text = "❌ Statistical weather data not available.\n"
                text += "This feature requires a paid OpenWeatherMap subscription."
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "road":
            # Get road risk weather data (requires paid subscription)
            # For demo, use a simple route around the location
            route_points = [(lat, lon), (lat + 0.01, lon + 0.01)]
            road_data = await weather_api.get_road_risk_weather(
                lat, lon, route_points
            )
            if road_data:
                text = WeatherFormatter.format_road_risk_weather(road_data)
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                text = "❌ Road risk weather data not available.\n"
                text += "This feature requires a paid OpenWeatherMap subscription."
                location_info = {"lat": lat, "lon": lon, "name": "Location"}
                keyboard = create_weather_keyboard(location_info)
                await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "refresh":
            # Refresh current weather
            weather_data = await weather_api.get_current_weather(lat, lon)
            if weather_data:
                location_info = {"lat": lat, "lon": lon, "name": "Location"}

                # Format weather data
                text = WeatherFormatter.format_current_weather(
                    weather_data, location_info
                )
                keyboard = create_weather_keyboard(location_info)

                # Edit message with updated weather data
                await edit_message(callback_query.message, text, buttons=keyboard)
            else:
                await callback_query.answer("❌ Failed to refresh weather data")

        elif action == "map_2":
            # Advanced weather maps (Weather Maps 2.0)
            text = "🗺️ <b>Advanced Weather Maps</b>\n\n"
            text += "This feature provides Weather Maps 2.0 with 1-hour step resolution.\n\n"
            text += "<b>Features:</b>\n"
            text += "• <code>✅</code> High-resolution maps\n"
            text += "• <code>✅</code> 1-hour time steps\n"
            text += "• <code>✅</code> Multiple weather layers\n"
            text += "• <code>✅</code> Historical data access\n\n"
            text += (
                "💡 <i>This feature requires a paid OpenWeatherMap subscription.</i>"
            )

            location_info = {"lat": lat, "lon": lon, "name": "Location"}
            keyboard = create_weather_keyboard(location_info)
            await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "map":
            # Regular weather maps
            text = "🗺️ <b>Weather Maps</b>\n\n"
            text += "Select a weather layer to view:\n\n"
            text += "🌡️ <b>Temperature</b> - Current temperature map\n"
            text += "🌧️ <b>Precipitation</b> - Rainfall and snow\n"
            text += "🌪️ <b>Pressure</b> - Atmospheric pressure\n"
            text += "💨 <b>Wind</b> - Wind speed and direction\n"
            text += "☁️ <b>Clouds</b> - Cloud coverage\n"

            # Create map selection keyboard
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🌡️ Temperature", callback_data=f"map_temp_{location_key}"
                        ),
                        InlineKeyboardButton(
                            "☁️ Clouds", callback_data=f"map_clouds_{location_key}"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🌧️ Precipitation",
                            callback_data=f"map_precipitation_{location_key}",
                        ),
                        InlineKeyboardButton(
                            "🌪️ Pressure",
                            callback_data=f"map_pressure_{location_key}",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "💨 Wind", callback_data=f"map_wind_{location_key}"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Weather",
                            callback_data=f"weather_current_{location_key}",
                        ),
                        InlineKeyboardButton(
                            "❌ Close", callback_data="weather_close"
                        ),
                    ],
                ]
            )

            await edit_message(callback_query.message, text, buttons=keyboard)

        elif action == "detailed":
            # Show detailed weather information
            weather_data = await weather_api.get_current_weather(lat, lon)
            forecast_data = await weather_api.get_forecast_5day(lat, lon)
            air_data = await weather_api.get_air_pollution(lat, lon)

            text = "📊 <b>Detailed Weather Information</b>\n\n"

            if weather_data:
                text += "<b>🌡️ Current Conditions:</b>\n"
                main = weather_data["main"]
                text += f"• Temperature: <code>{main['temp']:.1f}°C</code>\n"
                text += f"• Feels like: <code>{main['feels_like']:.1f}°C</code>\n"
                text += f"• Humidity: <code>{main['humidity']}%</code>\n"
                text += f"• Pressure: <code>{main['pressure']} hPa</code>\n\n"

            if forecast_data and "list" in forecast_data:
                text += "<b>📅 Next 24 Hours:</b>\n"
                for item in forecast_data["list"][:8]:  # Next 8 intervals (24 hours)
                    dt = datetime.fromtimestamp(item["dt"])
                    temp = item["main"]["temp"]
                    desc = item["weather"][0]["description"]
                    text += f"• <code>{dt.strftime('%H:%M')}</code> - {temp:.1f}°C, {desc}\n"
                text += "\n"

            if air_data and "list" in air_data:
                aqi = air_data["list"][0]["main"]["aqi"]
                aqi_levels = ["Good", "Fair", "Moderate", "Poor", "Very Poor"]
                aqi_text = aqi_levels[aqi - 1] if 1 <= aqi <= 5 else "Unknown"
                text += (
                    f"<b>🌬️ Air Quality:</b> <code>{aqi_text} (AQI {aqi})</code>\n"
                )

            location_info = {"lat": lat, "lon": lon, "name": "Location"}
            keyboard = create_weather_keyboard(location_info)
            await edit_message(callback_query.message, text, buttons=keyboard)

        else:
            await callback_query.answer("❌ Unknown action")

    except Exception as e:
        LOGGER.error(f"Weather callback error: {e}")
        await callback_query.answer(f"❌ Error: {e!s}")


@new_task
async def weather_map_callback_handler(
    _client: TgClient, callback_query: CallbackQuery
):
    """Handle weather map callback queries"""
    try:
        data = callback_query.data
        parts = data.split("_", 2)

        if len(parts) < 3:
            await callback_query.answer("❌ Invalid map data")
            return

        layer = parts[1]
        location = parts[2]

        await callback_query.answer("🗺️ Weather maps are not available")

        # Parse coordinates from location data
        try:
            lat, lon = map(float, location.split(","))
            location_name = f"Location ({lat:.2f}, {lon:.2f})"
        except ValueError:
            await callback_query.answer("❌ Invalid location data")
            return

        text = f"🗺️ <b>{layer.title()} Weather Map</b>\n\n"
        text += f"📍 <b>Location:</b> <code>{location_name}</code>\n"
        text += f"🌐 <b>Coordinates:</b> <code>{lat:.4f}, {lon:.4f}</code>\n"
        text += f"🗺️ <b>Layer:</b> <code>{layer.title()}</code>\n"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔄 Refresh", callback_data=data),
                    InlineKeyboardButton(
                        "�️ Other Maps", callback_data=f"weather_map_{location}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back to Weather",
                        callback_data=f"weather_current_{location}",
                    ),
                    InlineKeyboardButton("❌ Close", callback_data="weather_close"),
                ],
            ]
        )

        await edit_message(callback_query.message, text, buttons=keyboard)

    except Exception as e:
        LOGGER.error(f"Weather map callback error: {e}")
        await callback_query.answer(f"❌ Error: {e!s}")


# Automatic Weather Updates
class WeatherScheduler:
    """Handle automatic weather updates"""

    def __init__(self):
        self.running = False

    async def start_scheduler(self):
        """Start the weather update scheduler"""
        if not Config.AUTO_WEATHER or not Config.OPENWEATHER_API_KEY:
            return

        self.running = True

        while self.running:
            try:
                await self._check_and_send_weather_update()
                # Sleep for 1 hour before checking again
                await asyncio.sleep(3600)
            except Exception as e:
                LOGGER.error(f"Weather scheduler error: {e}")
                await asyncio.sleep(3600)

    async def stop_scheduler(self):
        """Stop the weather update scheduler"""
        self.running = False

    async def _check_and_send_weather_update(self):
        """Check if it's time to send weather update"""
        try:
            # Get current time in configured timezone
            tz = pytz.timezone(Config.WEATHER_TIMEZONE)
            current_time = datetime.now(tz)

            # Parse update time
            update_hour, update_minute = map(
                int, Config.WEATHER_UPDATE_TIME.split(":")
            )

            # Check if it's time for update (within 1 hour window)
            if (
                current_time.hour == update_hour
                and current_time.minute >= update_minute
                and current_time.minute < update_minute + 60
            ):
                await self._send_daily_weather_update()

        except Exception as e:
            LOGGER.error(f"Weather update check error: {e}")

    async def _send_daily_weather_update(self):
        """Send daily weather update to owner"""
        try:
            if not Config.WEATHER_PLACE:
                return

            # Geocode location
            location_info = await weather_api.geocode_location(Config.WEATHER_PLACE)
            if not location_info:
                LOGGER.error(
                    f"Failed to geocode weather place: {Config.WEATHER_PLACE}"
                )
                return

            # Get current weather
            weather_data = await weather_api.get_current_weather(
                location_info["lat"], location_info["lon"]
            )

            if not weather_data:
                LOGGER.error("Failed to fetch weather data for daily update")
                return

            # Get forecast
            forecast_data = await weather_api.get_forecast_5day(
                location_info["lat"], location_info["lon"]
            )

            # Get air quality
            air_data = await weather_api.get_air_pollution(
                location_info["lat"], location_info["lon"]
            )

            # Format comprehensive weather report
            text = "🌅 **Daily Weather Update**\n\n"
            text += WeatherFormatter.format_current_weather(
                weather_data, location_info
            )

            if forecast_data:
                text += (
                    f"\n\n{WeatherFormatter.format_forecast_summary(forecast_data)}"
                )

            if air_data:
                text += f"\n\n{WeatherFormatter.format_air_pollution(air_data)}"

            # Create keyboard
            keyboard = create_weather_keyboard(location_info)

            # Send to owner
            await TgClient.bot.send_message(Config.OWNER_ID, text, buttons=keyboard)

            # Check for risks
            if Config.WEATHER_RISK_NOTIFICATIONS:
                risk_message = await check_weather_risks(
                    weather_data, location_info["name"]
                )
                if risk_message:
                    await TgClient.bot.send_message(Config.OWNER_ID, risk_message)

            LOGGER.info("Daily weather update sent successfully")

        except Exception as e:
            LOGGER.error(f"Daily weather update error: {e}")


# Initialize weather scheduler
weather_scheduler = WeatherScheduler()


# Start weather scheduler when module loads
@new_task
async def start_weather_scheduler():
    """Start weather scheduler task"""
    if Config.AUTO_WEATHER:
        await weather_scheduler.start_scheduler()


# Cleanup function
async def cleanup_weather_module():
    """Cleanup weather module resources"""
    try:
        await weather_scheduler.stop_scheduler()
        await weather_api.close_session()
    except Exception as e:
        LOGGER.error(f"Weather module cleanup error: {e}")


# Help text for weather commands
WEATHER_HELP = """
🌤️ **Weather Commands:**

• `/weather [location]` - Get current weather with beautiful image
• `/weathermap [location]` - Show weather maps for different layers

**Features:**
• 🌡️ Current weather conditions
• 📅 5-day weather forecast
• 🌬️ Air quality index
• 🗺️ Weather maps (temperature, clouds, precipitation, etc.)
• ⏰ Hourly forecasts (requires paid API)
• 🔄 Real-time updates
• ⚠️ Weather risk notifications

**Auto Weather:**
• Daily weather updates at configured time
• Risk notifications for severe weather
• Customizable location and timezone

**Configuration:**
• Set `OPENWEATHER_API_KEY` for API access
• Set `WEATHER_PLACE` for default location
• Enable `AUTO_WEATHER` for daily updates
• Enable `WEATHER_RISK_NOTIFICATIONS` for alerts
"""


# Register handlers when module is imported
def register_weather_handlers():
    """Register weather command and callback handlers."""
    # Register weather command handler
    TgClient.bot.add_handler(
        MessageHandler(
            weather_command,
            filters=filters.command(BotCommands.WeatherCommand)
            & CustomFilters.authorized,
        )
    )

    # Register weather map command handler
    TgClient.bot.add_handler(
        MessageHandler(
            weather_map_command,
            filters=filters.command("weathermap") & CustomFilters.authorized,
        )
    )

    # Register weather callback handlers
    TgClient.bot.add_handler(
        CallbackQueryHandler(
            weather_callback_handler, filters=filters.regex(r"^weather_")
        )
    )

    TgClient.bot.add_handler(
        CallbackQueryHandler(
            weather_map_callback_handler, filters=filters.regex(r"^map_")
        )
    )
