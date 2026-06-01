import unittest
from unittest.mock import MagicMock

from investment_research_workflow.moderation import assert_moderation_passes, check_moderation
from investment_research_workflow.prompt_sanitizer import (
    sanitize_research_question,
    sanitize_research_questions,
)


class TestPromptSanitizer(unittest.TestCase):
    def test_rephrases_policy_sensitive_phrases(self):
        raw = (
            "What antitrust risk and regulatory scrutiny affect data privacy rules "
            "for cloud providers?"
        )
        sanitized = sanitize_research_question(raw)
        self.assertNotIn("antitrust risk", sanitized.lower())
        self.assertNotIn("regulatory scrutiny", sanitized.lower())
        self.assertNotIn("data privacy rules", sanitized.lower())
        self.assertIn("market competition dynamics", sanitized.lower())
        self.assertIn("regulatory landscape overview", sanitized.lower())
        self.assertIn("data handling practices", sanitized.lower())

    def test_sanitize_research_questions_preserves_order(self):
        questions = [
            "Assess antitrust risk for Microsoft.",
            "Review data privacy rules in enterprise AI.",
        ]
        sanitized = sanitize_research_questions(questions)
        self.assertEqual(len(sanitized), 2)
        self.assertIn("market competition dynamics", sanitized[0].lower())
        self.assertIn("data handling practices", sanitized[1].lower())


class TestModeration(unittest.TestCase):
    def _mock_client(self, *, flagged: bool):
        client = MagicMock()
        result = MagicMock()
        result.flagged = flagged
        result.categories = {"harassment": flagged}
        result.category_scores = {"harassment": 0.9 if flagged else 0.01}
        response = MagicMock()
        response.results = [result]
        client.moderations.create.return_value = response
        return client

    def test_check_moderation_passes(self):
        moderation = check_moderation(self._mock_client(flagged=False), "neutral prompt")
        self.assertTrue(moderation.passed)
        self.assertFalse(moderation.flagged)

    def test_assert_moderation_passes_raises_when_flagged(self):
        with self.assertRaises(ValueError):
            assert_moderation_passes(self._mock_client(flagged=True), "flagged prompt")


if __name__ == "__main__":
    unittest.main()
