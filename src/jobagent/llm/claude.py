"""Claude provider (anthropic SDK). The user's own key; never logged."""
from __future__ import annotations
from .provider import Completion, InvalidKey, LLMError

DEFAULT_CHEAP = "claude-haiku-4-5"
DEFAULT_STRONG = "claude-sonnet-4-5"


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=60)
        self._client = client
        self._key_hint = f"...{api_key[-4:]}" if api_key else ""

    def complete(self, system: str, prompt: str, *, model: str = DEFAULT_CHEAP, max_tokens: int = 1024) -> Completion:
        try:
            msg = self._client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": prompt}])
        except Exception as e:  # noqa: BLE001 - translate vendor errors, never leak the key
            status = getattr(e, "status_code", None)
            if status in (401, 403):
                raise InvalidKey("Claude rejected the API key; please update it.") from None
            raise LLMError(f"Claude call failed ({type(e).__name__}, status={status})") from None
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return Completion(text=text, input_tokens=msg.usage.input_tokens,
                          output_tokens=msg.usage.output_tokens, model=model)

    def verify_key(self) -> bool:
        """Cheapest possible call, used by the 'test my key' button."""
        self.complete("Reply with OK.", "ping", model=DEFAULT_CHEAP, max_tokens=5)
        return True
