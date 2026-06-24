"""LLM spend tracker with a soft per-day cap (PRD §9).

Estimates USD from token counts (rough), accumulates per-process and to a log
file, and raises BudgetExceeded once today's spend hits MAX_SPEND_USD so a
runaway loop stops. A small state snapshot (cost_state.json) is restored on
startup so accounting and the daily cap survive a process restart.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from ..config import settings

_BEIJING = timezone(timedelta(hours=8))  # daily window aligns with the app's display tz


def _today() -> str:
    return datetime.now(_BEIJING).strftime("%Y-%m-%d")


# Rough per-1M-token USD (input, output). Conservative; only used for the soft cap.
_PRICES = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.80, 4.0),
    "deepseek": (0.30, 0.50),  # deepseek-v4-flash (approx)
    "_default": (3.0, 15.0),
}

_lock = threading.Lock()


def _log_path():
    return settings.data_dir / "cost_log.jsonl"


def _state_path():
    return settings.data_dir / "cost_state.json"


class BudgetExceeded(RuntimeError):
    pass


class CostTracker:
    def __init__(self) -> None:
        self.total_usd = 0.0   # all-time cumulative (restored on startup)
        self.calls = 0         # all-time call count
        self.day = _today()
        self.day_usd = 0.0     # today's spend — what the cap is enforced against
        self.by_kind: dict[str, float] = {}  # all-time spend attributed per stage/purpose

    def restore(self) -> None:
        """Load the persisted snapshot so spend/cap survive a restart (call at startup)."""
        try:
            with open(_state_path(), encoding="utf-8") as f:
                s = json.load(f)
            self.total_usd = float(s.get("total_usd", 0.0))
            self.calls = int(s.get("calls", 0))
            self.day = s.get("day") or _today()
            self.day_usd = float(s.get("day_usd", 0.0))
            self.by_kind = {str(k): float(v) for k, v in (s.get("by_kind") or {}).items()}
            self._rollover()
        except (OSError, ValueError, TypeError):
            pass

    def _rollover(self) -> None:
        today = _today()
        if self.day != today:
            self.day, self.day_usd = today, 0.0

    def _persist(self) -> None:
        try:
            with open(_state_path(), "w", encoding="utf-8") as f:
                json.dump({"total_usd": round(self.total_usd, 6), "calls": self.calls,
                           "day": self.day, "day_usd": round(self.day_usd, 6),
                           "by_kind": {k: round(v, 6) for k, v in self.by_kind.items()}}, f)
        except OSError:
            pass

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
            self._rollover()
            self.total_usd += usd
            self.day_usd += usd
            self.calls += 1
            self.by_kind[kind] = self.by_kind.get(kind, 0.0) + usd
            try:
                with open(_log_path(), "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "t": time.time(), "kind": kind, "model": model,
                        "in": in_tokens, "out": out_tokens, "usd": round(usd, 6),
                        "day_usd": round(self.day_usd, 6),
                        "total_usd": round(self.total_usd, 6),
                    }) + "\n")
            except OSError:
                pass
            self._persist()

    def check(self) -> None:
        self._rollover()
        if self.day_usd >= settings.max_spend_usd:
            raise BudgetExceeded(
                f"MAX_SPEND_USD={settings.max_spend_usd}/day reached "
                f"(today ~${self.day_usd:.4f}, {self.calls} calls all-time)."
            )

    def summary(self) -> dict:
        self._rollover()
        return {"total_usd": round(self.total_usd, 6), "today_usd": round(self.day_usd, 6),
                "calls": self.calls, "max_spend_usd": settings.max_spend_usd, "day": self.day,
                "by_kind": {k: round(v, 6) for k, v in sorted(self.by_kind.items())}}


tracker = CostTracker()
