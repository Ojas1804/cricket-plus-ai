import logging

from openai import OpenAI, OpenAIError

from app.ai.providers.base import LLMError, T

logger = logging.getLogger(__name__)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str, reasoning_effort: str = "low") -> None:
        self._client = OpenAI(api_key=api_key, timeout=60, max_retries=2)
        self._model = model
        self._effort = reasoning_effort

    def parse(self, system: str, user: str, schema: type[T]) -> T:
        try:
            res = self._client.chat.completions.parse(
                model=self._model, response_format=schema, reasoning_effort=self._effort,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        except OpenAIError as e:
            logger.error("LLM call failed: %s", type(e).__name__)
            raise LLMError(f"The language model request failed ({getattr(e, 'code', None) or type(e).__name__})") from e
        message = res.choices[0].message
        if message.refusal or message.parsed is None:
            raise LLMError("The language model could not produce a valid structured response")
        return message.parsed

    def text(self, system: str, user: str) -> str:
        try:
            res = self._client.chat.completions.create(
                model=self._model, reasoning_effort=self._effort,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        except OpenAIError as e:
            logger.error("LLM call failed: %s", type(e).__name__)
            raise LLMError(f"The language model request failed ({getattr(e, 'code', None) or type(e).__name__})") from e
        return (res.choices[0].message.content or "").strip()
