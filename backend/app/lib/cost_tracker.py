"""LLM spend tracker with a soft cap (PRD §9).

Estimates USD from token counts (rough), accumulates per-process and to a log
file, and raises BudgetExceeded once MAX_SPEND_USD is hit so a runaway loop stops.
"""
import json
import threading
import time

from ..config import settings

# Rough per-1M-token USD (input, output). Conservative; only used for the soft cap.
_PRICES = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.80, 4.0),
    "deepseek": (0.30, 0.50),  # deepseek-v4-flash (approx)
    "_default": (3.0, 15.0),
}

_lock = threading.Lock()
_log_path = settings.data_dir / "cost_log.jsonl"


class BudgetExceeded(RuntimeError):
    pass


class CostTracker:
    def __init__(self) -> None:
        self.total_usd = 0.0
        self.calls = 0

    def _price(self, model: str) -> tuple[float, float]:
        m = model.lower()
        for key, price in _PRICES.items():
            if key in m:
                return price
        return _PRICES["_default"]

    def estimate(self, model: str, in_tokens: int, out_tokens: int) -> float:
        pin, pout = self._price(model)
        return in_tokens / 1_000_000 * pin + out_tokens / 1_000_000 * pout

    def record(self, model: str, in_tokens: int, out_tokens: int, kind: str = "llm") -> None:
        usd = self.estimate(model, in_tokens, out_tokens)
        with _lock:
            self.total_usd += usd
            self.calls += 1
            try:
                with open(_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "t": time.time(), "kind": kind, "model": model,
                        "in": in_tokens, "out": out_tokens, "usd": round(usd, 6),
                        "total_usd": round(self.total_usd, 6),
                    }) + "\n")
            except OSError:
                pass

    def check(self) -> None:
        if self.total_usd >= settings.max_spend_usd:
            raise BudgetExceeded(
                f"MAX_SPEND_USD={settings.max_spend_usd} reached "
                f"(spent ~${self.total_usd:.4f}, {self.calls} calls)."
            )

    def summary(self) -> dict:
        return {"total_usd": round(self.total_usd, 6), "calls": self.calls,
                "max_spend_usd": settings.max_spend_usd}


tracker = CostTracker()
