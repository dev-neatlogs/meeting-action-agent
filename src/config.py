import os
import litellm
from crewai import LLM

litellm.num_retries = 6
litellm.drop_params = True
# Wait for retry-after header (Groq sends exact seconds to wait)
litellm.retry_after = True

# -----------------------------
# Latency / cost controls
# -----------------------------
# These defaults are designed to prevent pathological "very large prompt" calls
# from spending excessive time in the model while preserving enough context
# for structured extraction.
TRANSCRIPT_MAX_CHARS = int(os.getenv("TRANSCRIPT_MAX_CHARS", "20000"))
FAST_MODEL_WORD_THRESHOLD = int(os.getenv("FAST_MODEL_WORD_THRESHOLD", "2500"))

# Output is usually smaller than input for JSON extraction, but a firm cap
# protects against runaway generations.
MAX_COMPLETION_TOKENS = int(os.getenv("LLM_MAX_COMPLETION_TOKENS", "1400"))

# Enable streaming so end-users perceive progress earlier on long generations.
LLM_STREAM = os.getenv("LLM_STREAM", "true").lower() in ("1", "true", "yes", "y")

# Model selection:
# - SLOW_MODEL: quality-focused
# - FAST_MODEL: latency-focused fallback for large inputs
# Use "latest" suffixes by default to avoid CrewAI routing into the native
# Gemini provider (which requires optional extras). LiteLLM still passes the
# model name through to the upstream provider.
SLOW_MODEL = os.getenv("SLOW_MODEL", "gemini/gemini-2.5-pro-latest")
FAST_MODEL = os.getenv("FAST_MODEL", "gemini/gemini-2.0-flash-latest")

# NOTE: We intentionally keep the same API key env var to avoid misconfiguration.
# If callers need a different provider, override the model names + env vars.
_api_key = os.getenv("GEMINI_API_KEY")


def _make_llm(model: str) -> LLM:
    return LLM(
        model=model,
        api_key=_api_key,
        is_litellm=True,  # Force LiteLLM routing so Neatlogs instruments LLM calls + costs
        max_retries=6,
        timeout=int(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
        stream=LLM_STREAM,
        # CrewAI's LiteLLM integration uses max_tokens/max_completion_tokens.
        max_completion_tokens=MAX_COMPLETION_TOKENS,
        max_tokens=MAX_COMPLETION_TOKENS,
        # Keep generations tighter for structured extraction tasks.
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        top_p=float(os.getenv("LLM_TOP_P", "1.0")),
    )


# Backwards-compatible default export
llm_slow = _make_llm(SLOW_MODEL)
llm_fast = _make_llm(FAST_MODEL)
llm = llm_slow
