"""Probe the Polymarket Gamma API and print the parsed shape (PRD §17).

Run this before trusting the live integration.  Usage: python scripts/probe_polymarket.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data import polymarket   # noqa: E402


def main() -> None:
    markets = polymarket.list_open_markets(limit=5)
    print(f"source = {polymarket.last_source}; got {len(markets)} open binary markets\n")
    for m in markets:
        print(f"  [{m['id']}] YES={m['current_prob']}  {m['question'][:70]}")
    if markets:
        one = polymarket.refresh_market(markets[0]["id"])
        print("\nrefresh_market(first):", one and {k: one[k] for k in ("status", "current_prob", "resolution")})


if __name__ == "__main__":
    main()
