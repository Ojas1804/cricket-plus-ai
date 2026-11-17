from app.ai.providers.base import LLMError, LLMProvider
from app.core.config import get_settings


def get_provider() -> LLMProvider | None:
    """Returns None when no real provider is configured; the app then serves mock widgets."""
    s = get_settings()
    if s.llm_provider == "openai" and s.llm_api_key:
        from app.ai.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(s.llm_api_key, s.llm_model or "gpt-5-mini")
    return None


__all__ = ["LLMError", "LLMProvider", "get_provider"]
