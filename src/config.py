import os
import litellm
from crewai import LLM

litellm.num_retries = 6
litellm.drop_params = True
# Wait for retry-after header (Groq sends exact seconds to wait)
litellm.retry_after = True

def _make_llm(model: str) -> LLM:
    return LLM(
        model=model,
        api_key=os.getenv("GEMINI_API_KEY"),
        is_litellm=True,  # Force LiteLLM routing so Neatlogs instruments LLM calls + costs
        max_retries=6,
        timeout=120,
    )


llm = _make_llm("gemini/gemini-2.5-pro")
flash_llm = _make_llm("gemini/gemini-2.5-flash")
