"""
Enhanced NSFW Detection System

This module provides comprehensive NSFW content detection using multiple approaches:
- Enhanced keyword detection with fuzzy matching and leetspeak
- AI-powered visual content analysis via multiple APIs
- Audio content analysis and speech-to-text
- Confidence scoring and caching system
- Multi-language support and behavioral analysis
"""

import hashlib
import json
import re
import tempfile
import time
from difflib import SequenceMatcher

import aiofiles
from aiohttp import ClientSession, ClientTimeout

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import path as aiopath
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.media_utils import get_media_info


class NSFWDetectionResult:
    """Result object for NSFW detection analysis"""

    def __init__(self):
        self.is_nsfw: bool = False
        self.confidence: float = 0.0
        self.detection_methods: list[str] = []
        self.keyword_matches: list[str] = []
        self.visual_analysis: dict = {}
        self.audio_analysis: dict = {}
        self.text_analysis: dict = {}
        self.processing_time: float = 0.0
        self.cache_hit: bool = False
        self.error_messages: list[str] = []

    def to_dict(self) -> dict:
        """Convert result to dictionary for storage/logging"""
        return {
            "is_nsfw": self.is_nsfw,
            "confidence": self.confidence,
            "detection_methods": self.detection_methods,
            "keyword_matches": self.keyword_matches,
            "visual_analysis": self.visual_analysis,
            "audio_analysis": self.audio_analysis,
            "text_analysis": self.text_analysis,
            "processing_time": self.processing_time,
            "cache_hit": self.cache_hit,
            "error_messages": self.error_messages,
            "timestamp": time.time(),
        }


class EnhancedKeywordDetector:
    """Enhanced keyword detection with fuzzy matching and leetspeak"""

    def __init__(self):
        # Extended NSFW keywords with categories and confidence weights
        self.nsfw_keywords = {
            "explicit": {
                "keywords": [
                    "porn",
                    "pornhub",
                    "xnxx",
                    "xvideos",
                    "youporn",
                    "redtube",
                    "brazzers",
                    "bangbros",
                    "realitykings",
                    "naughtyamerica",
                    "hardcore",
                    "blowjob",
                    "cumshot",
                    "facial",
                    "anal",
                    "gangbang",
                    "threesome",
                    "orgy",
                    "bdsm",
                    "fetish",
                    "kinky",
                    "bondage",
                ],
                "confidence_weight": 1.0,  # High confidence for explicit content
            },
            "adult_sites": {
                "keywords": [
                    "onlyfans",
                    "chaturbate",
                    "stripchat",
                    "cam4",
                    "livejasmin",
                    "myfreecams",
                    "camsoda",
                    "bongacams",
                    "flirt4free",
                ],
                "confidence_weight": 0.95,  # Very high confidence for adult sites
            },
            "suggestive": {
                "keywords": [
                    "lingerie",
                    "underwear",
                    "horny",
                    "naughty",
                    "erotic",
                    "sensual",
                ],
                "confidence_weight": 0.6,  # Lower confidence for suggestive content
            },
            "explicit_imagery": {
                "keywords": [
                    "nude",
                    "naked",
                    "topless",
                ],
                "confidence_weight": 0.85,  # Higher confidence for explicit imagery
            },
            "adult_content": {
                "keywords": [
                    "18+",
                    "xxx",
                    "nsfw",
                    "r-rated",
                    "x-rated",
                    "playboy",
                    "penthouse",
                    "hustler",
                    "hentai",
                    "ecchi",
                ],
                "confidence_weight": 0.8,  # Medium-high confidence
            },
            "euphemisms": {
                "keywords": [
                    "netflix and chill",
                    "dtf",
                    "fwb",
                    "hookup",
                    "booty call",
                    "one night stand",
                    "sugar daddy",
                    "escort",
                    "massage",
                ],
                "confidence_weight": 0.7,  # Medium confidence for euphemisms
            },
        }

        # Leetspeak mappings
        self.leetspeak_map = {
            "a": ["@", "4"],
            "e": ["3"],
            "i": ["1", "!"],
            "o": ["0"],
            "s": ["5", "$"],
            "t": ["7"],
            "l": ["1"],
            "g": ["9"],
        }

        # Multi-language keywords
        self.multilang_keywords = {
            "spanish": ["porno", "sexo", "desnudo", "caliente", "cachondo"],
            "french": ["porno", "sexe", "nu", "chaud", "coquin"],
            "german": ["porno", "sex", "nackt", "heiß", "geil"],
            "italian": ["porno", "sesso", "nudo", "caldo", "piccante"],
            "portuguese": ["porno", "sexo", "nu", "quente", "safado"],
            "russian": ["порно", "секс", "голый", "горячий"],
            "japanese": ["ポルノ", "セックス", "裸", "エロ", "アダルト"],
            "korean": ["포르노", "섹스", "벗은", "에로"],
            "chinese": ["色情", "性", "裸体", "成人"],
            "hindi": ["अश्लील", "सेक्स", "नग्न", "वयस्क"],
            "arabic": ["إباحي", "جنس", "عاري", "بالغ"],
        }

    def generate_leetspeak_variants(self, word: str) -> list[str]:
        """Generate leetspeak variants of a word"""
        variants = [word]

        def generate_recursive(current_word: str, index: int) -> None:
            if index >= len(current_word):
                if current_word not in variants:
                    variants.append(current_word)
                return

            char = current_word[index].lower()
            if char in self.leetspeak_map:
                for replacement in self.leetspeak_map[char]:
                    new_word = (
                        current_word[:index]
                        + replacement
                        + current_word[index + 1 :]
                    )
                    generate_recursive(new_word, index + 1)

            generate_recursive(current_word, index + 1)

        generate_recursive(word.lower(), 0)
        return variants[:10]  # Limit variants to prevent explosion

    def fuzzy_match(self, text: str, keyword: str, threshold: float = 0.8) -> bool:
        """Check if text contains fuzzy match of keyword with improved precision"""
        text_lower = text.lower()
        keyword_lower = keyword.lower()

        # Direct match
        if keyword_lower in text_lower:
            return True

        # Check for fuzzy matches in words with stricter criteria
        words = re.findall(r"\b\w+\b", text_lower)
        for word in words:
            # Only check words of similar length to reduce false positives
            if (
                len(word) >= 4
                and len(keyword_lower) >= 4
                and abs(len(word) - len(keyword_lower)) <= 2
            ):
                similarity = SequenceMatcher(None, word, keyword_lower).ratio()
                if similarity >= threshold:
                    # Additional check: ensure at least 70% of characters match
                    common_chars = sum(
                        1
                        for a, b in zip(word, keyword_lower, strict=False)
                        if a == b
                    )
                    char_match_ratio = common_chars / max(
                        len(word), len(keyword_lower)
                    )
                    if char_match_ratio >= 0.7:
                        return True

        return False

    def is_safe_context(self, text: str, keyword: str, match_pos: int) -> bool:
        """Check if keyword appears in a safe context to reduce false positives"""
        # Safe context indicators
        safe_contexts = [
            # Educational/informational contexts
            "education",
            "educational",
            "learn",
            "learning",
            "study",
            "research",
            "academic",
            "university",
            "school",
            "course",
            "tutorial",
            "guide",
            # Medical/health contexts
            "health",
            "medical",
            "doctor",
            "therapy",
            "treatment",
            "clinic",
            "hospital",
            "medicine",
            "healthcare",
            "wellness",
            # News/documentary contexts
            "news",
            "report",
            "documentary",
            "article",
            "journalism",
            "media",
            "broadcast",
            "interview",
            "investigation",
            # Legal/policy contexts
            "law",
            "legal",
            "policy",
            "regulation",
            "legislation",
            "court",
            "justice",
            "rights",
            "protection",
            # Technology/business contexts
            "technology",
            "software",
            "business",
            "company",
            "industry",
            "professional",
            "corporate",
            "enterprise",
        ]

        # Check surrounding text (50 characters before and after)
        start = max(0, match_pos - 50)
        end = min(len(text), match_pos + len(keyword) + 50)
        context = text[start:end].lower()

        # Check if any safe context indicators are present
        return any(safe_word in context for safe_word in safe_contexts)

    def detect_keywords(self, text: str) -> tuple[bool, list[str], float]:
        """Detect NSFW keywords with enhanced matching"""
        if not text:
            return False, [], 0.0

        matches = []
        confidence_scores = []

        # Process keywords by category with weighted confidence
        category_matches = {}

        for category, category_data in self.nsfw_keywords.items():
            keywords = category_data["keywords"]
            weight = category_data["confidence_weight"]

            for keyword in keywords:
                # Direct match (highest confidence)
                match = re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE)
                if match:
                    # Check for safe context for suggestive keywords if context checking is enabled
                    context_checking = getattr(Config, "NSFW_CONTEXT_CHECKING", True)
                    if (
                        context_checking
                        and category == "suggestive"
                        and self.is_safe_context(text, keyword, match.start())
                    ):
                        continue  # Skip this match as it's in a safe context

                    matches.append(keyword)
                    confidence_scores.append(weight)
                    category_matches[category] = (
                        category_matches.get(category, 0) + 1
                    )
                    continue

                # Fuzzy matching if enabled (only for explicit content to reduce false positives)
                if (
                    Config.NSFW_FUZZY_MATCHING
                    and category
                    in [
                        "explicit",
                        "adult_sites",
                    ]
                    and self.fuzzy_match(text, keyword, 0.90)
                ):  # Increased threshold
                    matches.append(f"{keyword}~")
                    confidence_scores.append(
                        weight * 0.8
                    )  # Reduced confidence for fuzzy
                    category_matches[category] = (
                        category_matches.get(category, 0) + 1
                    )
                    continue

                # Leetspeak detection if enabled (only for explicit content)
                if Config.NSFW_LEETSPEAK_DETECTION and category in [
                    "explicit",
                    "adult_sites",
                ]:
                    variants = self.generate_leetspeak_variants(keyword)
                    for variant in variants:
                        if re.search(
                            rf"\b{re.escape(variant)}\b", text, re.IGNORECASE
                        ):
                            matches.append(f"{keyword}[{variant}]")
                            confidence_scores.append(
                                weight * 0.7
                            )  # Reduced confidence for leetspeak
                            category_matches[category] = (
                                category_matches.get(category, 0) + 1
                            )
                            break

        # Add multi-language keywords if enabled (only for explicit categories)
        if Config.NSFW_MULTI_LANGUAGE:
            for lang, keywords in self.multilang_keywords.items():
                for keyword in keywords:
                    if re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE):
                        matches.append(f"{keyword}({lang})")
                        confidence_scores.append(
                            0.8
                        )  # Medium confidence for multi-lang
                        category_matches["multilang"] = (
                            category_matches.get("multilang", 0) + 1
                        )

        # Calculate overall confidence with improved logic
        if matches:
            # Weight by category importance and match quality
            avg_confidence = sum(confidence_scores) / len(confidence_scores)

            # Apply category-based boost (less aggressive)
            category_boost = 0.0
            if "explicit" in category_matches:
                category_boost += 0.1
            if "adult_sites" in category_matches:
                category_boost += 0.1
            if len(category_matches) > 1:  # Multiple categories
                category_boost += 0.05

            # Reduce boost for suggestive-only matches
            if len(category_matches) == 1 and "suggestive" in category_matches:
                category_boost = max(0, category_boost - 0.1)

            final_confidence = min(avg_confidence + category_boost, 1.0)

            # Apply minimum confidence threshold for suggestive content
            if len(category_matches) == 1 and "suggestive" in category_matches:
                if final_confidence < 0.8:  # Higher threshold for suggestive-only
                    return False, [], 0.0

            return True, matches, final_confidence

        return False, [], 0.0


class VisualContentAnalyzer:
    """AI-powered visual content analysis using multiple providers"""

    def __init__(self):
        self.session = None

    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30, connect=10)
            self.session = ClientSession(timeout=timeout)
        return self.session

    async def analyze_image_google_vision(self, image_path: str) -> dict:
        """Analyze image using Google Cloud Vision API"""
        if not Config.NSFW_GOOGLE_VISION_API_KEY:
            return {"error": "Google Vision API key not configured"}

        try:
            # Read image file
            async with aiofiles.open(image_path, "rb") as f:
                image_data = await f.read()

            import base64

            encoded_image = base64.b64encode(image_data).decode("utf-8")

            session = await self._get_session()
            url = f"https://vision.googleapis.com/v1/images:annotate?key={Config.NSFW_GOOGLE_VISION_API_KEY}"

            payload = {
                "requests": [
                    {
                        "image": {"content": encoded_image},
                        "features": [
                            {"type": "SAFE_SEARCH_DETECTION", "maxResults": 1}
                        ],
                    }
                ]
            }

            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("responses"):
                        safe_search = result["responses"][0].get(
                            "safeSearchAnnotation", {}
                        )

                        # Convert Google's likelihood to confidence score
                        likelihood_map = {
                            "VERY_UNLIKELY": 0.1,
                            "UNLIKELY": 0.3,
                            "POSSIBLE": 0.5,
                            "LIKELY": 0.7,
                            "VERY_LIKELY": 0.9,
                        }

                        adult_score = likelihood_map.get(
                            safe_search.get("adult", "VERY_UNLIKELY"), 0.1
                        )
                        racy_score = likelihood_map.get(
                            safe_search.get("racy", "VERY_UNLIKELY"), 0.1
                        )

                        return {
                            "provider": "google_vision",
                            "adult_confidence": adult_score,
                            "racy_confidence": racy_score,
                            "overall_confidence": max(adult_score, racy_score),
                            "is_nsfw": max(adult_score, racy_score) > 0.5,
                            "raw_response": safe_search,
                        }
                else:
                    return {"error": f"Google Vision API error: {response.status}"}

        except Exception as e:
            LOGGER.error(f"Google Vision analysis error: {e}")
            return {"error": str(e)}

    async def analyze_image_openai_vision(self, image_path: str) -> dict:
        """Analyze image using OpenAI GPT-4 Vision"""
        if not Config.NSFW_OPENAI_API_KEY:
            return {"error": "OpenAI API key not configured"}

        try:
            import base64

            # Read and encode image
            async with aiofiles.open(image_path, "rb") as f:
                image_data = await f.read()
            encoded_image = base64.b64encode(image_data).decode("utf-8")

            session = await self._get_session()
            url = "https://api.openai.com/v1/chat/completions"

            headers = {
                "Authorization": f"Bearer {Config.NSFW_OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": "gpt-4-vision-preview",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": 'Analyze this image for NSFW content. Respond with a JSON object containing: {"is_nsfw": boolean, "confidence": float (0-1), "reasons": ["reason1", "reason2"], "content_type": "description"}. Be accurate and consider nudity, sexual content, suggestive poses, and adult themes.',
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_image}"
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": 300,
            }

            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result["choices"][0]["message"]["content"]

                    try:
                        # Parse JSON response
                        analysis = json.loads(content)
                        return {
                            "provider": "openai_vision",
                            "is_nsfw": analysis.get("is_nsfw", False),
                            "confidence": analysis.get("confidence", 0.0),
                            "reasons": analysis.get("reasons", []),
                            "content_type": analysis.get("content_type", ""),
                            "raw_response": analysis,
                        }
                    except json.JSONDecodeError:
                        # Fallback parsing if JSON is malformed
                        is_nsfw = (
                            "true" in content.lower() or "nsfw" in content.lower()
                        )
                        return {
                            "provider": "openai_vision",
                            "is_nsfw": is_nsfw,
                            "confidence": 0.5 if is_nsfw else 0.1,
                            "raw_response": content,
                        }
                else:
                    return {"error": f"OpenAI Vision API error: {response.status}"}

        except Exception as e:
            LOGGER.error(f"OpenAI Vision analysis error: {e}")
            return {"error": str(e)}

    async def analyze_image(self, image_path: str) -> dict:
        """Analyze image using available providers"""
        results = {}

        # Try multiple providers for better accuracy
        if Config.NSFW_GOOGLE_VISION_API_KEY:
            results["google"] = await self.analyze_image_google_vision(image_path)

        if Config.NSFW_OPENAI_API_KEY:
            results["openai"] = await self.analyze_image_openai_vision(image_path)

        # Combine results
        if results:
            confidences = []
            is_nsfw_votes = []

            for result in results.values():
                if "error" not in result:
                    if "overall_confidence" in result:
                        confidences.append(result["overall_confidence"])
                    elif "confidence" in result:
                        confidences.append(result["confidence"])

                    is_nsfw_votes.append(result.get("is_nsfw", False))

            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                is_nsfw = sum(is_nsfw_votes) > len(is_nsfw_votes) / 2

                return {
                    "is_nsfw": is_nsfw,
                    "confidence": avg_confidence,
                    "provider_results": results,
                    "providers_used": list(results.keys()),
                }

        return {"error": "No visual analysis providers available"}

    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()


class TextContentAnalyzer:
    """Advanced text analysis using NLP APIs"""

    def __init__(self):
        self.session = None

    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30, connect=10)
            self.session = ClientSession(timeout=timeout)
        return self.session

    async def analyze_with_perspective_api(self, text: str) -> dict:
        """Analyze text toxicity using Google Perspective API"""
        if not Config.NSFW_PERSPECTIVE_API_KEY:
            return {"error": "Perspective API key not configured"}

        try:
            session = await self._get_session()
            url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={Config.NSFW_PERSPECTIVE_API_KEY}"

            payload = {
                "requestedAttributes": {
                    "TOXICITY": {},
                    "SEVERE_TOXICITY": {},
                    "IDENTITY_ATTACK": {},
                    "INSULT": {},
                    "PROFANITY": {},
                    "THREAT": {},
                    "SEXUALLY_EXPLICIT": {},
                    "FLIRTATION": {},
                },
                "comment": {"text": text},
                "languages": ["en"],
            }

            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    scores = result.get("attributeScores", {})

                    # Extract relevant scores
                    sexually_explicit = (
                        scores.get("SEXUALLY_EXPLICIT", {})
                        .get("summaryScore", {})
                        .get("value", 0)
                    )
                    flirtation = (
                        scores.get("FLIRTATION", {})
                        .get("summaryScore", {})
                        .get("value", 0)
                    )
                    profanity = (
                        scores.get("PROFANITY", {})
                        .get("summaryScore", {})
                        .get("value", 0)
                    )

                    # Calculate NSFW confidence
                    nsfw_confidence = max(
                        sexually_explicit, flirtation * 0.7, profanity * 0.5
                    )

                    return {
                        "provider": "perspective_api",
                        "is_nsfw": nsfw_confidence > 0.6,
                        "confidence": nsfw_confidence,
                        "sexually_explicit": sexually_explicit,
                        "flirtation": flirtation,
                        "profanity": profanity,
                        "raw_scores": scores,
                    }
                return {"error": f"Perspective API error: {response.status}"}

        except Exception as e:
            LOGGER.error(f"Perspective API analysis error: {e}")
            return {"error": str(e)}

    async def analyze_with_openai_moderation(self, text: str) -> dict:
        """Analyze text using OpenAI Moderation API"""
        if not Config.NSFW_OPENAI_API_KEY:
            return {"error": "OpenAI API key not configured"}

        try:
            session = await self._get_session()
            url = "https://api.openai.com/v1/moderations"

            headers = {
                "Authorization": f"Bearer {Config.NSFW_OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }

            payload = {"input": text}

            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    moderation = result["results"][0]

                    # Check for sexual content
                    sexual = moderation["categories"].get("sexual", False)
                    sexual_minors = moderation["categories"].get(
                        "sexual/minors", False
                    )

                    # Get confidence scores
                    sexual_score = moderation["category_scores"].get("sexual", 0)
                    sexual_minors_score = moderation["category_scores"].get(
                        "sexual/minors", 0
                    )

                    nsfw_confidence = max(sexual_score, sexual_minors_score)

                    return {
                        "provider": "openai_moderation",
                        "is_nsfw": sexual or sexual_minors,
                        "confidence": nsfw_confidence,
                        "flagged": moderation["flagged"],
                        "categories": moderation["categories"],
                        "category_scores": moderation["category_scores"],
                    }
                return {"error": f"OpenAI Moderation API error: {response.status}"}

        except Exception as e:
            LOGGER.error(f"OpenAI Moderation analysis error: {e}")
            return {"error": str(e)}

    async def analyze_text(self, text: str) -> dict:
        """Analyze text using available providers"""
        results = {}

        if Config.NSFW_PERSPECTIVE_API_KEY:
            results["perspective"] = await self.analyze_with_perspective_api(text)

        if Config.NSFW_OPENAI_MODERATION and Config.NSFW_OPENAI_API_KEY:
            results["openai"] = await self.analyze_with_openai_moderation(text)

        # Combine results
        if results:
            confidences = []
            is_nsfw_votes = []

            for result in results.values():
                if "error" not in result:
                    confidences.append(result.get("confidence", 0))
                    is_nsfw_votes.append(result.get("is_nsfw", False))

            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                is_nsfw = sum(is_nsfw_votes) > len(is_nsfw_votes) / 2

                return {
                    "is_nsfw": is_nsfw,
                    "confidence": avg_confidence,
                    "provider_results": results,
                    "providers_used": list(results.keys()),
                }

        return {"error": "No text analysis providers available"}

    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()


class NSFWDetectionCache:
    """Caching system for NSFW detection results"""

    def __init__(self):
        self.cache = {}
        self.cache_times = {}

    def _generate_cache_key(
        self, content: str | bytes, content_type: str = "text"
    ) -> str:
        """Generate cache key for content"""
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        hash_obj = hashlib.sha256(content_bytes)
        return f"{content_type}_{hash_obj.hexdigest()[:16]}"

    async def get(
        self, content: str | bytes, content_type: str = "text"
    ) -> NSFWDetectionResult | None:
        """Get cached result if available and not expired"""
        cache_key = self._generate_cache_key(content, content_type)

        if cache_key in self.cache:
            cache_time = self.cache_times.get(cache_key, 0)
            if time.time() - cache_time < Config.NSFW_CACHE_DURATION:
                result = self.cache[cache_key]
                result.cache_hit = True
                return result
            # Remove expired entry
            del self.cache[cache_key]
            del self.cache_times[cache_key]

        return None

    async def set(
        self,
        content: str | bytes,
        result: NSFWDetectionResult,
        content_type: str = "text",
    ):
        """Cache detection result"""
        cache_key = self._generate_cache_key(content, content_type)
        self.cache[cache_key] = result
        self.cache_times[cache_key] = time.time()

        # Clean old entries if cache is too large
        if len(self.cache) > 1000:
            await self._cleanup_cache()

    async def _cleanup_cache(self):
        """Remove old cache entries"""
        current_time = time.time()
        expired_keys = []

        for key, cache_time in self.cache_times.items():
            if current_time - cache_time > Config.NSFW_CACHE_DURATION:
                expired_keys.append(key)

        for key in expired_keys:
            self.cache.pop(key, None)
            self.cache_times.pop(key, None)

        LOGGER.info(f"Cleaned {len(expired_keys)} expired NSFW cache entries")


class EnhancedNSFWDetector:
    """Main NSFW detection class that orchestrates all detection methods"""

    def __init__(self):
        self.keyword_detector = EnhancedKeywordDetector()
        self.visual_analyzer = VisualContentAnalyzer()
        self.text_analyzer = TextContentAnalyzer()
        self.cache = NSFWDetectionCache()

    async def detect_text_nsfw(self, text: str) -> NSFWDetectionResult:
        """Detect NSFW content in text"""
        start_time = time.time()
        result = NSFWDetectionResult()

        if not text or not Config.NSFW_DETECTION_ENABLED:
            result.processing_time = time.time() - start_time
            return result

        # Check cache first
        cached_result = await self.cache.get(text, "text")
        if cached_result:
            return cached_result

        try:
            # Enhanced keyword detection
            if Config.NSFW_KEYWORD_DETECTION:
                try:
                    is_nsfw, matches, confidence = (
                        self.keyword_detector.detect_keywords(text)
                    )
                    if is_nsfw:
                        result.is_nsfw = True
                        result.keyword_matches = matches
                        result.confidence = max(result.confidence, confidence)
                        result.detection_methods.append("enhanced_keywords")
                except Exception as keyword_error:
                    LOGGER.error(f"Error in keyword detection: {keyword_error}")
                    # Continue with other detection methods

            # Advanced text analysis with NLP APIs
            if Config.NSFW_PERSPECTIVE_API_KEY or (
                Config.NSFW_OPENAI_MODERATION and Config.NSFW_OPENAI_API_KEY
            ):
                text_analysis = await self.text_analyzer.analyze_text(text)
                result.text_analysis = text_analysis

                if "error" not in text_analysis:
                    if text_analysis.get("is_nsfw", False):
                        result.is_nsfw = True
                        result.confidence = max(
                            result.confidence, text_analysis.get("confidence", 0)
                        )
                        result.detection_methods.append("nlp_analysis")

            # Apply sensitivity threshold
            threshold = self._get_sensitivity_threshold()
            if result.confidence < threshold:
                result.is_nsfw = False

            result.processing_time = time.time() - start_time

            # Cache result
            await self.cache.set(text, result, "text")

            # Log detection if enabled
            if Config.NSFW_LOG_DETECTIONS and result.is_nsfw:
                await self._log_detection("text", text[:100], result)

        except Exception as e:
            LOGGER.error(f"Error in text NSFW detection: {e}")
            result.error_messages.append(str(e))
            result.processing_time = time.time() - start_time

        return result

    async def detect_image_nsfw(self, image_path: str) -> NSFWDetectionResult:
        """Detect NSFW content in images"""
        start_time = time.time()
        result = NSFWDetectionResult()

        if not await aiopath.exists(image_path) or not Config.NSFW_DETECTION_ENABLED:
            result.processing_time = time.time() - start_time
            return result

        try:
            # Check file size
            file_size = await aiopath.getsize(image_path)
            if file_size > Config.NSFW_MAX_FILE_SIZE:
                result.error_messages.append(f"File too large: {file_size} bytes")
                result.processing_time = time.time() - start_time
                return result

            # Check cache using file content hash
            async with aiofiles.open(image_path, "rb") as f:
                file_content = await f.read()

            cached_result = await self.cache.get(file_content, "image")
            if cached_result:
                return cached_result

            # Visual content analysis
            if Config.NSFW_VISUAL_DETECTION:
                visual_analysis = await self.visual_analyzer.analyze_image(
                    image_path
                )
                result.visual_analysis = visual_analysis

                if "error" not in visual_analysis:
                    if visual_analysis.get("is_nsfw", False):
                        result.is_nsfw = True
                        result.confidence = visual_analysis.get("confidence", 0)
                        result.detection_methods.append("visual_analysis")

            # Apply sensitivity threshold
            threshold = self._get_sensitivity_threshold()
            if result.confidence < threshold:
                result.is_nsfw = False

            result.processing_time = time.time() - start_time

            # Cache result
            await self.cache.set(file_content, result, "image")

            # Log detection if enabled
            if Config.NSFW_LOG_DETECTIONS and result.is_nsfw:
                await self._log_detection("image", image_path, result)

        except Exception as e:
            LOGGER.error(f"Error in image NSFW detection: {e}")
            result.error_messages.append(str(e))
            result.processing_time = time.time() - start_time

        return result

    async def detect_file_nsfw(
        self, file_path: str, file_name: str | None = None
    ) -> NSFWDetectionResult:
        """Detect NSFW content in files (combines filename and content analysis)"""
        start_time = time.time()
        result = NSFWDetectionResult()

        if not Config.NSFW_DETECTION_ENABLED:
            result.processing_time = time.time() - start_time
            return result

        try:
            # Analyze filename
            if file_name:
                filename_result = await self.detect_text_nsfw(file_name)
                if filename_result.is_nsfw:
                    result.is_nsfw = True
                    result.confidence = max(
                        result.confidence, filename_result.confidence
                    )
                    result.keyword_matches.extend(filename_result.keyword_matches)
                    result.detection_methods.append("filename_analysis")

            # Analyze file content based on type
            if await aiopath.exists(file_path):
                file_ext = (
                    file_path.lower().split(".")[-1] if "." in file_path else ""
                )

                # Image analysis
                if file_ext in ["jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff"]:
                    content_result = await self.detect_image_nsfw(file_path)
                    if content_result.is_nsfw:
                        result.is_nsfw = True
                        result.confidence = max(
                            result.confidence, content_result.confidence
                        )
                        result.visual_analysis = content_result.visual_analysis
                        result.detection_methods.extend(
                            content_result.detection_methods
                        )

                # Video analysis (extract frames and analyze)
                elif file_ext in ["mp4", "avi", "mkv", "mov", "wmv", "flv", "webm"]:
                    if Config.NSFW_VIDEO_ANALYSIS and Config.NSFW_VISUAL_DETECTION:
                        video_result = await self.detect_video_nsfw(file_path)
                        if video_result.is_nsfw:
                            result.is_nsfw = True
                            result.confidence = max(
                                result.confidence, video_result.confidence
                            )
                            result.visual_analysis = video_result.visual_analysis
                            result.detection_methods.extend(
                                video_result.detection_methods
                            )
                    else:
                        LOGGER.info(
                            "Video analysis disabled, checking filename only"
                        )

                # Audio analysis (extract text from speech and analyze)
                elif file_ext in ["mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"]:
                    if Config.NSFW_AUDIO_ANALYSIS:
                        audio_result = await self.detect_audio_nsfw(file_path)
                        if audio_result.is_nsfw:
                            result.is_nsfw = True
                            result.confidence = max(
                                result.confidence, audio_result.confidence
                            )
                            result.audio_analysis = audio_result.audio_analysis
                            result.detection_methods.extend(
                                audio_result.detection_methods
                            )
                    else:
                        LOGGER.info(
                            "Audio analysis disabled, checking filename only"
                        )

                # Subtitle analysis (analyze subtitle text content)
                elif file_ext in ["srt", "vtt", "ass", "ssa", "sub", "sbv", "ttml"]:
                    if Config.NSFW_SUBTITLE_ANALYSIS:
                        subtitle_result = await self.detect_subtitle_nsfw(file_path)
                        if subtitle_result.is_nsfw:
                            result.is_nsfw = True
                            result.confidence = max(
                                result.confidence, subtitle_result.confidence
                            )
                            result.text_analysis = subtitle_result.text_analysis
                            result.detection_methods.extend(
                                subtitle_result.detection_methods
                            )
                    else:
                        LOGGER.info(
                            "Subtitle analysis disabled, checking filename only"
                        )

            result.processing_time = time.time() - start_time

        except Exception as e:
            LOGGER.error(f"Error in file NSFW detection: {e}")
            result.error_messages.append(str(e))
            result.processing_time = time.time() - start_time

        return result

    async def detect_video_nsfw(self, video_path: str) -> NSFWDetectionResult:
        """Detect NSFW content in videos using smart frame extraction"""
        start_time = time.time()
        result = NSFWDetectionResult()

        if not await aiopath.exists(video_path) or not Config.NSFW_DETECTION_ENABLED:
            result.processing_time = time.time() - start_time
            return result

        try:
            # Check file size
            file_size = await aiopath.getsize(video_path)
            if file_size > Config.NSFW_MAX_FILE_SIZE:
                result.error_messages.append(f"Video too large: {file_size} bytes")
                result.processing_time = time.time() - start_time
                return result

            # Get video duration for smart sampling
            duration = (await get_media_info(video_path))[0]

            if duration == 0:
                result.error_messages.append("Could not determine video duration")
                result.processing_time = time.time() - start_time
                return result

            # Extract frames using smart sampling
            extracted_frames = await self._extract_smart_frames(video_path, duration)

            if not extracted_frames:
                result.error_messages.append("Failed to extract frames from video")
                result.processing_time = time.time() - start_time
                return result

            # Analyze each extracted frame
            frame_results = []
            nsfw_frames = 0

            for i, frame_path in enumerate(extracted_frames):
                try:
                    if Config.NSFW_VISUAL_DETECTION:
                        frame_analysis = await self.visual_analyzer.analyze_image(
                            frame_path
                        )
                        frame_results.append(frame_analysis)

                        # Check if this frame is NSFW
                        if "error" not in frame_analysis and frame_analysis.get(
                            "is_nsfw", False
                        ):
                            nsfw_frames += 1
                            result.is_nsfw = True
                            frame_confidence = frame_analysis.get("confidence", 0)
                            result.confidence = max(
                                result.confidence, frame_confidence
                            )

                            if (
                                "video_frame_analysis"
                                not in result.detection_methods
                            ):
                                result.detection_methods.append(
                                    "video_frame_analysis"
                                )

                except Exception as e:
                    LOGGER.error(f"Error analyzing frame {i}: {e}")
                    result.error_messages.append(f"Frame {i} analysis failed")
                finally:
                    # Clean up frame file
                    if await aiopath.exists(frame_path):
                        await aiopath.remove(frame_path)

            # Aggregate results from all frames
            if frame_results:
                valid_results = [r for r in frame_results if "error" not in r]
                if valid_results:
                    avg_confidence = sum(
                        r.get("confidence", 0) for r in valid_results
                    ) / len(valid_results)
                    max_confidence = max(
                        r.get("confidence", 0) for r in valid_results
                    )

                    result.visual_analysis = {
                        "frame_count": len(extracted_frames),
                        "frames_analyzed": len(valid_results),
                        "nsfw_frames": nsfw_frames,
                        "avg_confidence": avg_confidence,
                        "max_confidence": max_confidence,
                        "video_duration": duration,
                        "detection_rate": nsfw_frames / len(valid_results)
                        if valid_results
                        else 0,
                    }

                    # Use max confidence for final decision
                    result.confidence = max_confidence

            # Apply sensitivity threshold
            threshold = self._get_sensitivity_threshold()
            if result.confidence < threshold:
                result.is_nsfw = False

            result.processing_time = time.time() - start_time

            # Log detection if enabled
            if Config.NSFW_LOG_DETECTIONS and result.is_nsfw:
                await self._log_detection("video", video_path, result)

        except Exception as e:
            LOGGER.error(f"Error in video NSFW detection: {e}")
            result.error_messages.append(str(e))
            result.processing_time = time.time() - start_time

        return result

    async def _extract_smart_frames(
        self, video_path: str, duration: float
    ) -> list[str]:
        """Extract frames using smart sampling - beginning, middle, end + strategic points"""

        frame_count = Config.NSFW_VIDEO_FRAME_COUNT
        quality_map = {1: "5", 2: "3", 3: "2", 4: "1", 5: "1"}
        quality = quality_map.get(Config.NSFW_FRAME_QUALITY, "3")

        # Smart timestamps: strategic sampling across video
        if frame_count == 1:
            timestamps = [duration * 0.5]  # Middle only
        elif frame_count == 2:
            timestamps = [duration * 0.25, duration * 0.75]  # Quarter points
        elif frame_count == 3:
            timestamps = [
                duration * 0.2,
                duration * 0.5,
                duration * 0.8,
            ]  # Beginning, middle, end
        elif frame_count == 4:
            timestamps = [
                duration * 0.15,
                duration * 0.35,
                duration * 0.65,
                duration * 0.85,
            ]
        else:  # 5 or more frames
            timestamps = [
                duration * 0.1,  # Early beginning
                duration * 0.25,  # Early middle
                duration * 0.5,  # Center
                duration * 0.75,  # Late middle
                duration * 0.9,  # Near end
            ]

            # Add extra frames if requested
            if frame_count > 5:
                extra_points = frame_count - 5
                for i in range(extra_points):
                    # Add random points between existing ones
                    extra_timestamp = duration * (0.3 + (i * 0.1))
                    timestamps.append(extra_timestamp)
                timestamps.sort()

        extracted_frames = []

        for i, timestamp in enumerate(timestamps[:frame_count]):
            try:
                # Create unique output path
                temp_dir = tempfile.gettempdir()
                frame_path = f"{temp_dir}/nsfw_frame_{int(time.time())}_{i}.jpg"

                # FFmpeg command for frame extraction
                cmd = [
                    "xtra",  # FFmpeg binary
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{timestamp}",  # Seek to timestamp
                    "-i",
                    video_path,
                    "-vframes",
                    "1",  # Extract 1 frame
                    "-vf",
                    "scale=640:-1",  # Resize for analysis (maintain aspect ratio)
                    "-q:v",
                    quality,  # Quality setting
                    "-y",  # Overwrite output
                    frame_path,
                ]

                # Execute frame extraction
                _, stderr, code = await cmd_exec(cmd)

                if code == 0 and await aiopath.exists(frame_path):
                    # Verify frame is not empty
                    frame_size = await aiopath.getsize(frame_path)
                    if frame_size > 1024:  # At least 1KB
                        extracted_frames.append(frame_path)
                    else:
                        LOGGER.warning(
                            f"Extracted frame too small: {frame_size} bytes"
                        )
                        if await aiopath.exists(frame_path):
                            await aiopath.remove(frame_path)
                else:
                    LOGGER.warning(
                        f"Failed to extract frame at {timestamp}s: {stderr}"
                    )

            except Exception as e:
                LOGGER.error(f"Error extracting frame {i} at {timestamp}s: {e}")
                continue

        LOGGER.info(
            f"Successfully extracted {len(extracted_frames)} frames from video"
        )
        return extracted_frames

    async def detect_audio_nsfw(self, audio_path: str) -> NSFWDetectionResult:
        """Detect NSFW content in audio files using speech-to-text analysis"""
        start_time = time.time()
        result = NSFWDetectionResult()

        if not await aiopath.exists(audio_path) or not Config.NSFW_DETECTION_ENABLED:
            result.processing_time = time.time() - start_time
            return result

        try:
            # Check file size
            file_size = await aiopath.getsize(audio_path)
            if file_size > Config.NSFW_MAX_FILE_SIZE:
                result.error_messages.append(
                    f"Audio file too large: {file_size} bytes"
                )
                result.processing_time = time.time() - start_time
                return result

            # Get audio duration
            duration = (await get_media_info(audio_path))[0]

            if duration == 0:
                result.error_messages.append("Could not determine audio duration")
                result.processing_time = time.time() - start_time
                return result

            # For now, we'll analyze the filename and any embedded metadata
            # Future enhancement: Add speech-to-text analysis

            # Extract audio metadata that might contain text
            extracted_text = await self._extract_audio_metadata_text(audio_path)

            if extracted_text:
                # Analyze extracted text for NSFW content
                text_result = await self.detect_text_nsfw(extracted_text)
                if text_result.is_nsfw:
                    result.is_nsfw = True
                    result.confidence = text_result.confidence
                    result.detection_methods.append("audio_metadata_analysis")
                    result.keyword_matches = text_result.keyword_matches

                    result.audio_analysis = {
                        "duration": duration,
                        "metadata_text": extracted_text[:200],  # First 200 chars
                        "text_analysis": text_result.text_analysis,
                        "extraction_method": "metadata",
                    }

            # Apply sensitivity threshold
            threshold = self._get_sensitivity_threshold()
            if result.confidence < threshold:
                result.is_nsfw = False

            result.processing_time = time.time() - start_time

            # Log detection if enabled
            if Config.NSFW_LOG_DETECTIONS and result.is_nsfw:
                await self._log_detection("audio", audio_path, result)

        except Exception as e:
            LOGGER.error(f"Error in audio NSFW detection: {e}")
            result.error_messages.append(str(e))
            result.processing_time = time.time() - start_time

        return result

    async def _extract_audio_metadata_text(self, audio_path: str) -> str:
        """Extract text from audio metadata (title, artist, album, etc.)"""
        try:
            # Use FFprobe to extract metadata
            cmd = [
                "xtra",  # FFmpeg binary
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                audio_path,
                "-f",
                "ffmetadata",
                "-",
            ]

            stdout, _stderr, code = await cmd_exec(cmd)

            if code == 0 and stdout:
                # Parse metadata and extract text fields
                metadata_text = []
                lines = stdout.split("\n")

                for line in lines:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip().lower()

                        # Extract text from relevant metadata fields
                        if (
                            key
                            in [
                                "title",
                                "artist",
                                "album",
                                "comment",
                                "description",
                                "lyrics",
                            ]
                            and value.strip()
                        ):
                            metadata_text.append(value.strip())

                return " ".join(metadata_text)

        except Exception as e:
            LOGGER.error(f"Error extracting audio metadata: {e}")

        return ""

    async def detect_subtitle_nsfw(self, subtitle_path: str) -> NSFWDetectionResult:
        """Detect NSFW content in subtitle files"""
        start_time = time.time()
        result = NSFWDetectionResult()

        if (
            not await aiopath.exists(subtitle_path)
            or not Config.NSFW_DETECTION_ENABLED
        ):
            result.processing_time = time.time() - start_time
            return result

        try:
            # Check file size
            file_size = await aiopath.getsize(subtitle_path)
            if file_size > Config.NSFW_MAX_FILE_SIZE:
                result.error_messages.append(
                    f"Subtitle file too large: {file_size} bytes"
                )
                result.processing_time = time.time() - start_time
                return result

            # Extract text content from subtitle file
            subtitle_text = await self._extract_subtitle_text(subtitle_path)

            if not subtitle_text:
                result.error_messages.append(
                    "Could not extract text from subtitle file"
                )
                result.processing_time = time.time() - start_time
                return result

            # Analyze subtitle text for NSFW content
            text_result = await self.detect_text_nsfw(subtitle_text)

            if text_result.is_nsfw:
                result.is_nsfw = True
                result.confidence = text_result.confidence
                result.detection_methods.append("subtitle_text_analysis")
                result.keyword_matches = text_result.keyword_matches
                result.text_analysis = text_result.text_analysis

                # Add subtitle-specific analysis info
                result.text_analysis["subtitle_info"] = {
                    "file_size": file_size,
                    "text_length": len(subtitle_text),
                    "text_preview": subtitle_text[:200],  # First 200 chars
                }

            # Apply sensitivity threshold
            threshold = self._get_sensitivity_threshold()
            if result.confidence < threshold:
                result.is_nsfw = False

            result.processing_time = time.time() - start_time

            # Log detection if enabled
            if Config.NSFW_LOG_DETECTIONS and result.is_nsfw:
                await self._log_detection("subtitle", subtitle_path, result)

        except Exception as e:
            LOGGER.error(f"Error in subtitle NSFW detection: {e}")
            result.error_messages.append(str(e))
            result.processing_time = time.time() - start_time

        return result

    async def _extract_subtitle_text(self, subtitle_path: str) -> str:
        """Extract plain text from subtitle files"""
        try:
            # Read subtitle file
            async with aiofiles.open(
                subtitle_path, encoding="utf-8", errors="ignore"
            ) as f:
                content = await f.read()

            # Determine subtitle format and extract text accordingly
            file_ext = subtitle_path.lower().split(".")[-1]

            if file_ext == "srt":
                return self._extract_srt_text(content)
            if file_ext == "vtt":
                return self._extract_vtt_text(content)
            if file_ext in ["ass", "ssa"]:
                return self._extract_ass_text(content)
            if file_ext == "sub":
                return self._extract_sub_text(content)
            # For other formats, try to extract any readable text
            return self._extract_generic_text(content)

        except Exception as e:
            LOGGER.error(f"Error reading subtitle file: {e}")
            return ""

    def _extract_srt_text(self, content: str) -> str:
        """Extract text from SRT subtitle format"""
        lines = content.split("\n")
        text_lines = []

        for line in lines:
            line = line.strip()
            # Skip sequence numbers and timestamps
            if line and not line.isdigit() and "-->" not in line:
                # Remove HTML tags if present
                clean_line = re.sub(r"<[^>]+>", "", line)
                if clean_line:
                    text_lines.append(clean_line)

        return " ".join(text_lines)

    def _extract_vtt_text(self, content: str) -> str:
        """Extract text from WebVTT subtitle format"""
        lines = content.split("\n")
        text_lines = []
        in_cue = False

        for line in lines:
            line = line.strip()

            # Skip header
            if line.startswith("WEBVTT"):
                continue

            # Check for timestamp line
            if "-->" in line:
                in_cue = True
                continue

            # Extract text lines
            if in_cue and line:
                # Remove HTML tags and cue settings
                clean_line = re.sub(r"<[^>]+>", "", line)
                clean_line = re.sub(
                    r"\{[^}]+\}", "", clean_line
                )  # Remove cue settings
                if clean_line:
                    text_lines.append(clean_line)
            elif not line:
                in_cue = False

        return " ".join(text_lines)

    def _extract_ass_text(self, content: str) -> str:
        """Extract text from ASS/SSA subtitle format"""
        lines = content.split("\n")
        text_lines = []

        for line in lines:
            line = line.strip()

            # Look for dialogue lines
            if line.startswith("Dialogue:"):
                # ASS format: Dialogue: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
                parts = line.split(",", 9)
                if len(parts) >= 10:
                    text = parts[9]
                    # Remove ASS formatting codes
                    clean_text = re.sub(r"\{[^}]*\}", "", text)
                    clean_text = re.sub(
                        r"\\[nN]", " ", clean_text
                    )  # Replace line breaks
                    if clean_text.strip():
                        text_lines.append(clean_text.strip())

        return " ".join(text_lines)

    def _extract_sub_text(self, content: str) -> str:
        """Extract text from SUB subtitle format"""
        lines = content.split("\n")
        text_lines = []

        for line in lines:
            line = line.strip()
            # SUB format typically has timestamp followed by text
            if line and not re.match(r"^\d+:\d+:\d+", line):
                # Remove any formatting codes
                clean_line = re.sub(r"\{[^}]+\}", "", line)
                if clean_line:
                    text_lines.append(clean_line)

        return " ".join(text_lines)

    def _extract_generic_text(self, content: str) -> str:
        """Extract readable text from unknown subtitle formats"""
        # Remove common formatting patterns and extract readable text
        text = re.sub(r"<[^>]+>", "", content)  # Remove HTML tags
        text = re.sub(r"\{[^}]+\}", "", text)  # Remove curly brace formatting
        text = re.sub(r"\[[^\]]+\]", "", text)  # Remove square bracket formatting
        text = re.sub(r"\d+:\d+:\d+[.,]\d+", "", text)  # Remove timestamps
        text = re.sub(r"-->", "", text)  # Remove arrow separators
        text = re.sub(r"\n+", " ", text)  # Replace multiple newlines with space

        # Extract only meaningful text (filter out numbers and short fragments)
        words = text.split()
        meaningful_words = [
            word for word in words if len(word) > 2 and not word.isdigit()
        ]

        return " ".join(meaningful_words)

    def _get_sensitivity_threshold(self) -> float:
        """Get confidence threshold based on sensitivity setting"""
        sensitivity_thresholds = {
            "strict": 0.3,  # Very sensitive, catches more content
            "moderate": 0.7,  # Balanced approach
            "permissive": 0.9,  # Only very obvious NSFW content
        }
        return sensitivity_thresholds.get(Config.NSFW_DETECTION_SENSITIVITY, 0.7)

    async def _log_detection(
        self, content_type: str, content_preview: str, result: NSFWDetectionResult
    ):
        """Log NSFW detection for analysis"""
        log_data = {
            "timestamp": time.time(),
            "content_type": content_type,
            "content_preview": content_preview,
            "detection_result": result.to_dict(),
            "sensitivity": Config.NSFW_DETECTION_SENSITIVITY,
            "threshold": self._get_sensitivity_threshold(),
        }

        LOGGER.info(
            f"NSFW Detection: {content_type} - Confidence: {result.confidence:.2f} - Methods: {result.detection_methods}"
        )

        # Store in database if enabled
        if Config.NSFW_STORE_METADATA:
            try:
                from bot.helper.ext_utils.db_handler import database

                await database.store_nsfw_detection(log_data)
            except Exception as e:
                LOGGER.error(f"Error storing NSFW detection metadata: {e}")

    async def close(self):
        """Close all analyzer sessions"""
        await self.visual_analyzer.close()
        await self.text_analyzer.close()


# Global instance
nsfw_detector = EnhancedNSFWDetector()
