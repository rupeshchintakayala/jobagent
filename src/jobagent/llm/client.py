"""Per-user LLM client: budget check BEFORE every call, usage recorded AFTER."""
from __future__ import annotations
from typing import Callable
from jobagent.budget.guard import BudgetGuard
from .pricing import cost_eur, estimate_call_eur
from .provider import Completion, LLMProvider

UsageSink = Callable[[dict], None]


class LLMClient:
    def __init__(self, user_id: str, provider: LLMProvider, guard: BudgetGuard,
                 usage_sink: UsageSink | None = None, prices: dict | None = None):
        self.user_id, self.provider, self.guard = user_id, provider, guard
        self.usage_sink, self.prices = usage_sink, prices

    def complete(self, system: str, prompt: str, *, model: str, max_tokens: int = 1024) -> Completion:
        est = estimate_call_eur(model, system, prompt, max_tokens, self.prices)
        self.guard.check(est)                      # raises BudgetExceeded before spending anything
        result = self.provider.complete(system, prompt, model=model, max_tokens=max_tokens)
        actual = cost_eur(result.model, result.input_tokens, result.output_tokens, self.prices)
        self.guard.record(actual)
        if self.usage_sink:
            self.usage_sink({"user_id": self.user_id, "model": result.model,
                             "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                             "cost_eur": actual})
        return result
