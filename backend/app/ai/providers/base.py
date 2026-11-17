from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class LLMProvider(Protocol):
    """Vendor-neutral LLM interface. Implementations must return schema-validated objects."""

    def parse(self, system: str, user: str, schema: type[T]) -> T: ...

    def text(self, system: str, user: str) -> str: ...
