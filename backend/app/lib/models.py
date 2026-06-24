"""Pydantic data models — the single source of truth (PRD §8).

Frontend TS types mirror these. Two evaluation lines stay separated:
  - Forecast  : Agent analysis only (scored by Brier vs market)
  - Bet        : user's manual paper position (scored by P&L, in a virtual account)
"""
from typing import Literal, Optional

from pydantic import BaseModel

Side = Literal["YES", "NO"]
Confidence = Literal["low", "med", "high"]


class Market(BaseModel):
    id: str                                  # Polymarket market/condition id
    question: str
    description: Optional[str] = None
    category: Optional[str] = None
    opened_at: Optional[str] = None          # market open time (ISO8601)
    close_at: Optional[str] = None           # close / resolution time (ISO8601)
    status: Literal["open", "resolved", "void"] = "open"
    current_prob: Optional[float] = None      # latest YES market price (implied prob)
    resolution: Optional[Literal[0, 1]] = None
    resolved_at: Optional[str] = None
    url: Optional[str] = None                 # public Polymarket page (click-through)
    event_id: Optional[str] = None            # parent event (groups multi-outcome legs)
    event_title: Optional[str] = None
    outcome_name: Optional[str] = None        # leg name in a multi-outcome event; None = standalone


class Evidence(BaseModel):
    market_id: str
    url: str
    title: str
    published_at: Optional[str] = None
    summary: str
    relevance: float                          # 0..1


class ForecastRun(BaseModel):
    probability: float                        # YES prob 0..1
    confidence: Confidence
    rationale: str
    key_factors: list[str]


class Forecast(BaseModel):
    id: str
    market_id: str
    agent_prob: float                         # aggregated YES prob (raw ensemble — scored honestly)
    agent_prob_calibrated: Optional[float] = None  # raw prob remapped via resolved-history calibration
    market_prob_at_analysis: float            # baseline snapshot
    confidence: Confidence
    rationale: str
    key_factors: list[str]
    runs: list[ForecastRun]
    prompt_version: str = ""                   # which prompt set produced this (eval compares versions)
    retrieved_lessons: list[str] = []         # injected past reviews (traceable)
    evidence: list[Evidence] = []
    created_at: str
    status: Literal["pending", "resolved"] = "pending"
    outcome: Optional[Literal[0, 1]] = None
    brier: Optional[float] = None
    market_brier: Optional[float] = None
    reviewed: bool = False


class Bet(BaseModel):
    """假性押注: user-entered paper position. Never touches real money/payment."""
    id: str
    market_id: str
    forecast_id: str                          # must reference one analysis (1 bet max / forecast)
    side: Side
    stake: float                              # debited from virtual account balance on open
    entry_prob: float                         # the chosen side's price, 0..1
    shares: float                             # = stake / entry_prob (for mark-to-market)
    note: Optional[str] = None
    created_at: str
    status: Literal["pending", "resolved"] = "pending"
    current_price: Optional[float] = None     # latest side price (poller refreshes)
    unrealized_pnl: Optional[float] = None    # shares*current_price - stake (while open)
    outcome: Optional[Literal[0, 1]] = None
    pnl: Optional[float] = None               # realized after resolution


class Account(BaseModel):
    """Single virtual account (paper bookkeeping, no payment)."""
    starting_balance: float
    cash_balance: float                       # available cash (stakes debited)
    realized_pnl: float = 0.0


class Review(BaseModel):
    forecast_id: str
    market_id: str
    question: str
    agent_prob: float
    outcome: Literal[0, 1]
    agent_brier: float
    market_brier: float
    bet_pnl: Optional[float] = None
    what_happened: str
    why: str
    lesson: str                               # transferable takeaway (retrieved into prompts)
    created_at: str
