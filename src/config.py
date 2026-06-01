import os
import litellm
from crewai import LLM

litellm.num_retries = 6
litellm.drop_params = True
# Wait for retry-after header (Groq sends exact seconds to wait)
litellm.retry_after = True

# Cap transcript size before it reaches the meeting analyst (large inputs drive
# multi‑second/minute LLM latency). ~4 chars ≈ 1 token; default ≈ 6k tokens.
MAX_TRANSCRIPT_CHARS = int(os.getenv("MAX_TRANSCRIPT_CHARS", "24000"))


def truncate_transcript(text: str, max_chars: int | None = None) -> str:
    """Shorten oversized transcripts while keeping opening context and closing commitments."""
    limit = max_chars if max_chars is not None else MAX_TRANSCRIPT_CHARS
    if limit <= 0 or len(text) <= limit:
        return text
    head_len = int(limit * 0.7)
    tail_len = limit - head_len
    head = text[:head_len].rstrip()
    tail = text[-tail_len:].lstrip()
    return (
        f"{head}\n\n"
        f"[... transcript truncated: {len(text)} → {limit} chars for latency ...]\n\n"
        f"{tail}"
    )


# Switch extraction/scoring to flash when raw input is large (≈6k+ tokens).
FAST_MODEL_WORD_THRESHOLD = int(os.getenv("FAST_MODEL_WORD_THRESHOLD", "2500"))


def _make_llm(
    model: str,
    *,
    max_tokens: int | None = None,
    stream: bool = False,
) -> LLM:
    return LLM(
        model=model,
        api_key=os.getenv("GEMINI_API_KEY"),
        is_litellm=True,  # Force LiteLLM routing so Neatlogs instruments LLM calls + costs
        max_retries=6,
        timeout=120,
        max_tokens=max_tokens,
        stream=stream,
    )


# Pro: extraction + risk enrichment (quality-sensitive)
llm = _make_llm("gemini/gemini-2.5-pro", max_tokens=4096, stream=True)

# Flash: repetitive publish orchestration (maps to faster tier vs heavy default model)
flash_llm = _make_llm("gemini/gemini-2.5-flash", max_tokens=2048, stream=False)
