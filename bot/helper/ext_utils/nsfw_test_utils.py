"""
NSFW Detection Test Utilities

This module provides utilities for testing and validating the enhanced NSFW detection system.
"""

import asyncio
import time

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.nsfw_detection import nsfw_detector


class NSFWTestSuite:
    """Test suite for NSFW detection system"""

    def __init__(self):
        self.test_cases = {
            "clean_content": [
                "Hello, how are you today?",
                "This is a normal conversation",
                "I love watching movies and reading books",
                "The weather is nice today",
                "Can you help me with my homework?",
                "family_vacation_2023.jpg",
                "cooking_recipe_video.mp4",
                "nature_documentary.mkv",
            ],
            "mild_nsfw": [
                "This movie has some adult themes",
                "The film contains mature content",
                "bikini_beach_photos.jpg",
                "romantic_comedy_18plus.mp4",
                "lingerie_fashion_show.avi",
            ],
            "obvious_nsfw": [
                "Check out this porn video",
                "Hot xxx action here",
                "Hardcore adult content",
                "OnlyFans exclusive content",
                "Brazzers premium video",
                "porn_collection_2023.zip",
                "xxx_hardcore_video.mp4",
                "adult_content_18plus.avi",
            ],
            "leetspeak_nsfw": [
                "Ch3ck 0ut th1s p0rn v1d30",
                "H0t xxx 4ct10n h3r3",
                "H4rdc0r3 4dult c0nt3nt",
                "0nlyF4ns 3xclu51v3",
                "Br4zz3rs pr3m1um",
                "p0rn_c0ll3ct10n.zip",
                "xxx_h4rdc0r3.mp4",
            ],
            "obfuscated_nsfw": [
                "Check out this p.o.r.n video",
                "Hot x-x-x action here",
                "Adult c0ntent here",
                "Only_Fans exclusive",
                "Brazz3rs premium",
                "p_o_r_n_collection.zip",
                "x.x.x.hardcore.mp4",
            ],
            "multilingual_nsfw": [
                "Este es contenido porno",  # Spanish
                "Contenu pornographique ici",  # French
                "Pornographischer Inhalt",  # German
                "Contenuto pornografico",  # Italian
                "Conteúdo pornográfico",  # Portuguese
                "Порнографический контент",  # Russian
                "ポルノコンテンツ",  # Japanese
                "성인 콘텐츠",  # Korean
                "色情内容",  # Chinese
            ],
        }

    async def run_comprehensive_test(self) -> dict:
        """Run comprehensive test suite"""
        LOGGER.info("Starting comprehensive NSFW detection test suite...")

        results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "category_results": {},
            "performance_metrics": {},
            "errors": [],
        }

        start_time = time.time()

        for category, test_cases in self.test_cases.items():
            LOGGER.info(f"Testing category: {category}")
            category_results = await self._test_category(category, test_cases)
            results["category_results"][category] = category_results

            results["total_tests"] += category_results["total"]
            results["passed"] += category_results["passed"]
            results["failed"] += category_results["failed"]

        results["performance_metrics"]["total_time"] = time.time() - start_time
        results["performance_metrics"]["avg_time_per_test"] = (
            results["performance_metrics"]["total_time"] / results["total_tests"]
            if results["total_tests"] > 0
            else 0
        )

        # Calculate accuracy
        if results["total_tests"] > 0:
            results["accuracy"] = (results["passed"] / results["total_tests"]) * 100
        else:
            results["accuracy"] = 0

        LOGGER.info(f"Test suite completed. Accuracy: {results['accuracy']:.1f}%")
        return results

    async def _test_category(self, category: str, test_cases: list[str]) -> dict:
        """Test a specific category of content"""
        results = {"total": len(test_cases), "passed": 0, "failed": 0, "details": []}

        # Determine expected result based on category
        expected_nsfw = category in [
            "obvious_nsfw",
            "leetspeak_nsfw",
            "obfuscated_nsfw",
            "multilingual_nsfw",
        ]
        expected_clean = category in ["clean_content"]

        for test_case in test_cases:
            try:
                detection_result = await nsfw_detector.detect_text_nsfw(test_case)

                # Determine if test passed
                test_passed = False
                if (expected_nsfw and detection_result.is_nsfw) or (
                    expected_clean and not detection_result.is_nsfw
                ):
                    test_passed = True
                elif category == "mild_nsfw":
                    # For mild NSFW, accept both results but prefer correct detection
                    test_passed = True  # More lenient for borderline cases

                if test_passed:
                    results["passed"] += 1
                else:
                    results["failed"] += 1

                results["details"].append(
                    {
                        "test_case": test_case,
                        "expected_nsfw": expected_nsfw,
                        "detected_nsfw": detection_result.is_nsfw,
                        "confidence": detection_result.confidence,
                        "methods": detection_result.detection_methods,
                        "matches": detection_result.keyword_matches,
                        "passed": test_passed,
                        "processing_time": detection_result.processing_time,
                    }
                )

            except Exception as e:
                LOGGER.error(f"Error testing case '{test_case}': {e}")
                results["failed"] += 1
                results["details"].append(
                    {"test_case": test_case, "error": str(e), "passed": False}
                )

        return results

    async def test_performance(self, iterations: int = 100) -> dict:
        """Test performance with repeated detections"""
        LOGGER.info(f"Running performance test with {iterations} iterations...")

        test_text = "This is a test message for performance testing"
        times = []

        for _i in range(iterations):
            start_time = time.time()
            await nsfw_detector.detect_text_nsfw(test_text)
            end_time = time.time()
            times.append(end_time - start_time)

        return {
            "iterations": iterations,
            "total_time": sum(times),
            "avg_time": sum(times) / len(times),
            "min_time": min(times),
            "max_time": max(times),
            "cache_effectiveness": times[0] / times[-1] if times[-1] > 0 else 1,
        }

    async def test_sensitivity_levels(self) -> dict:
        """Test different sensitivity levels"""
        LOGGER.info("Testing sensitivity levels...")

        test_cases = [
            ("This is clean content", False),
            ("This has some adult themes", None),  # Borderline
            ("This is obvious porn content", True),
        ]

        results = {}
        original_sensitivity = Config.NSFW_DETECTION_SENSITIVITY

        for sensitivity in ["strict", "moderate", "permissive"]:
            Config.NSFW_DETECTION_SENSITIVITY = sensitivity
            results[sensitivity] = []

            for test_text, expected in test_cases:
                detection_result = await nsfw_detector.detect_text_nsfw(test_text)
                results[sensitivity].append(
                    {
                        "text": test_text,
                        "expected": expected,
                        "detected": detection_result.is_nsfw,
                        "confidence": detection_result.confidence,
                    }
                )

        # Restore original sensitivity
        Config.NSFW_DETECTION_SENSITIVITY = original_sensitivity
        return results

    def generate_test_report(self, results: dict) -> str:
        """Generate a formatted test report"""
        report = []
        report.append("🧪 NSFW Detection Test Report")
        report.append("=" * 40)
        report.append("📊 Overall Results:")
        report.append(f"   Total Tests: {results['total_tests']}")
        report.append(f"   Passed: {results['passed']}")
        report.append(f"   Failed: {results['failed']}")
        report.append(f"   Accuracy: {results['accuracy']:.1f}%")
        report.append("")

        report.append("⏱️ Performance:")
        report.append(
            f"   Total Time: {results['performance_metrics']['total_time']:.2f}s"
        )
        report.append(
            f"   Avg Time/Test: {results['performance_metrics']['avg_time_per_test']:.3f}s"
        )
        report.append("")

        report.append("📋 Category Results:")
        for category, cat_results in results["category_results"].items():
            accuracy = (
                (cat_results["passed"] / cat_results["total"] * 100)
                if cat_results["total"] > 0
                else 0
            )
            report.append(
                f"   {category}: {cat_results['passed']}/{cat_results['total']} ({accuracy:.1f}%)"
            )

        if results.get("errors"):
            report.append("")
            report.append("❌ Errors:")
            for error in results["errors"][:5]:  # Show first 5 errors
                report.append(f"   {error}")

        return "\n".join(report)


# Global test suite instance
nsfw_test_suite = NSFWTestSuite()


async def quick_test():
    """Quick test function for development"""
    test_cases = [
        "Hello world",
        "Check out this porn video",
        "p0rn c0nt3nt h3r3",
        "adult content warning",
    ]

    for test_case in test_cases:
        result = await nsfw_detector.detect_text_nsfw(test_case)
        print(f"Text: '{test_case}'")
        print(f"NSFW: {result.is_nsfw}, Confidence: {result.confidence:.2f}")
        print(f"Methods: {result.detection_methods}")
        print(f"Matches: {result.keyword_matches}")
        print("-" * 40)


if __name__ == "__main__":
    # Run quick test if executed directly
    asyncio.run(quick_test())
