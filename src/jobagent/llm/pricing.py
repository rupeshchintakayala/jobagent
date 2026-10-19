"""Cost estimation in EUR. Prices are per million tokens (USD list price) x a USD->EUR rate.
Keep this table in config long-term; users can override via prices argument."""
from __future__ import annotations

USD_TO_EUR = 0.92
# (input_usd_per_mtok, output_usd_per_mtok). Unknown models fall back to the most expensive entry (safe side).
PRICES_USD: dict[str, tuple[float, float]] = {
    "claude-haiku": (1.0, 5.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-opus": (15.0, 75.0),
    "fake": (0.0, 0.0),
}


def _lookup(model: str, prices: dict[str, tuple[float, float]]) -> tuple[float, float]:
    m = model.lower()
    for key, val in prices.items():
        if key in m:
            return val
    return max(prices.values(), key=lambda p: p[0] + p[1])


def estimate_tokens(text: str) -> int:
    """Conservative estimate (~3.5 chars/token) used BEFORE a call."""
    return int(len(text) / 3.5) + 1


def cost_eur(model: str, input_tokens: int, output_tokens: int,
             prices: dict[str, tuple[float, float]] | None = None) -> float:
    pin, pout = _lookup(model, prices or PRICES_USD)
    return (input_tokens * pin + output_tokens * pout) / 1_000_000 * USD_TO_EUR


def estimate_call_eur(model: str, system: str, prompt: str, max_tokens: int,
                      prices: dict[str, tuple[float, float]] | None = None) -> float:
    """Worst case: all max_tokens used for output."""
    return cost_eur(model, estimate_tokens(system) + estimate_tokens(prompt), max_tokens, prices)
