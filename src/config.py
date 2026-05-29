import os
import litellm
from crewai import LLM

litellm.num_retries = 6
litellm.drop_params = True
# Wait for retry-after header (Groq sends exact seconds to wait)
litellm.retry_after = True

llm = LLM(
    model="gemini/gemini-2.5-pro",
    api_key=os.getenv("GEMINI_API_KEY"),
    is_litellm=True,  # Force LiteLLM routing so Neatlogs instruments LLM calls + costs
    max_retries=6,
    timeout=120,
)

# Gemini flash is lower-latency and is used for repetitive/pure-mapping steps
# (e.g. Notion publishing orchestration).
llm_flash = LLM(
    model="gemini/gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    is_litellm=True,
    max_retries=6,
    timeout=120,
)

# Keep the existing name for non-notion tasks.
llm_pro = llm
