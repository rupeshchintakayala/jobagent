"""LLM provider protocol. App code never talks to a vendor SDK directly."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMError(Exception):
    """Provider failure. Messages must never contain API keys."""


class InvalidKey(LLMError):
    """The user's key was rejected; ask them to update it."""


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, prompt: str, *, model: str, max_tokens: int) -> Completion: ...
