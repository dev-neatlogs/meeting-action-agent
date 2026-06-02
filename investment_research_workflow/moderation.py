"""OpenAI Moderation API gate for research prompts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModerationResult:
    flagged: bool
    categories: dict[str, bool]
    category_scores: dict[str, float]
    model: str

    @property
    def passed(self) -> bool:
        return not self.flagged


def check_moderation(client: Any, text: str, *, model: str = "omni-moderation-latest") -> ModerationResult:
    """Run OpenAI moderation on prompt text before LLM invocation."""
    response = client.moderations.create(input=text, model=model)
    result = response.results[0]
    return ModerationResult(
        flagged=bool(result.flagged),
        categories=dict(result.categories),
        category_scores={k: float(v) for k, v in result.category_scores.items()},
        model=model,
    )


def assert_moderation_passes(client: Any, text: str, *, model: str = "omni-moderation-latest") -> ModerationResult:
    """Raise ValueError when moderation flags the prompt."""
    moderation = check_moderation(client, text, model=model)
    if moderation.flagged:
        flagged = [name for name, active in moderation.categories.items() if active]
        raise ValueError(
            f"Prompt failed OpenAI moderation ({moderation.model}): {', '.join(flagged) or 'unknown category'}"
        )
    return moderation
