import os
import litellm
from crewai import LLM

litellm.num_retries = 6
litellm.drop_params = True
# Wait for retry-after header (Groq sends exact seconds to wait)
litellm.retry_after = True

# Default LLMs used by different agents. We keep Pro for analytical steps and
# Flash for repetitive/latency-sensitive publishing orchestration.
llm_pro = LLM(
    model="gemini/gemini-2.5-pro",
    api_key=os.getenv("GEMINI_API_KEY"),
    is_litellm=True,  # Force LiteLLM routing so Neatlogs instruments LLM calls + costs
    max_retries=6,
    timeout=120,
)

llm_flash = LLM(
    model="gemini/gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    is_litellm=True,
    max_retries=6,
    timeout=120,
)

# Backwards-compat alias (older imports expect `llm`).
llm = llm_pro
