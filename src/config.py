import os
import litellm
from crewai import LLM

litellm.num_retries = 6
litellm.drop_params = True
# Wait for retry-after header (Groq sends exact seconds to wait)
litellm.retry_after = True

llm_pro = LLM(
    model="gemini/gemini-2.5-pro",
    api_key=os.getenv("GEMINI_API_KEY"),
    is_litellm=True,  # Neatlogs instruments LLM calls + costs via LiteLLM
    max_retries=6,
    timeout=120,
)

llm_flash = LLM(
    model="gemini/gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    is_litellm=True,  # Faster model for repetitive/loop-heavy orchestration
    max_retries=6,
    timeout=120,
)

# Backwards-compatible default (most agents keep using the pro model)
llm = llm_pro
