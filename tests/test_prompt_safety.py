import unittest
from unittest.mock import patch

from src.prompt_safety import (
    openai_moderation_preflight,
    sanitize_research_prompt,
    sanitize_research_questions,
)


class PromptSafetyTests(unittest.TestCase):
    def test_sanitizes_policy_sensitive_investment_terms(self) -> None:
        prompt = (
            "For Microsoft, assess regulatory scrutiny, antitrust risk, "
            "and data privacy rules that could affect growth."
        )

        sanitized = sanitize_research_prompt(prompt)

        lowered = sanitized.lower()
        self.assertNotIn("regulatory scrutiny", lowered)
        self.assertNotIn("antitrust risk", lowered)
        self.assertNotIn("data privacy rules", lowered)
        self.assertIn("policy and compliance attention", lowered)
        self.assertIn("market competition dynamics", lowered)
        self.assertIn("information governance requirements", lowered)

    def test_sanitizes_research_questions_in_batch(self) -> None:
        sanitized = sanitize_research_questions(
            [
                "Compare Microsoft's antitrust risks with peers.",
                "Summarize data privacy rules in cloud markets.",
            ]
        )

        self.assertEqual(
            sanitized,
            [
                "Compare Microsoft's market competition dynamics with peers.",
                "Summarize information governance requirements in cloud markets.",
            ],
        )

    def test_openai_moderation_preflight_skips_without_key(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            result = openai_moderation_preflight("Microsoft market overview")

        self.assertFalse(result.checked)
        self.assertFalse(result.flagged)


if __name__ == "__main__":
    unittest.main()
