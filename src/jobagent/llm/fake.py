"""Fake provider for tests: scripted or callable responses, zero cost, no network."""
from __future__ import annotations
from typing import Callable
from .provider import Completion


class FakeProvider:
    name = "fake"

    def __init__(self, responses: list[str] | Callable[[str, str], str] | str = "ok"):
        self._responses = responses
        self.calls: list[dict] = []

    def verify_key(self) -> None:
        """Always valid (tests)."""

    def complete(self, system: str, prompt: str, *, model: str = "fake", max_tokens: int = 1024) -> Completion:
        self.calls.append({"system": system, "prompt": prompt, "model": model, "max_tokens": max_tokens})
        r = self._responses
        if callable(r):
            text = r(system, prompt)
        elif isinstance(r, list):
            text = r[min(len(self.calls) - 1, len(r) - 1)]
        else:
            text = r
        return Completion(text=text, input_tokens=len(system + prompt) // 4, output_tokens=len(text) // 4, model=model)
