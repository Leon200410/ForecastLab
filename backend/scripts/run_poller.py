"""Standalone poller loop: mark-to-market + resolution settle (PRD §7-M1).

Run alongside the API (the API also runs an in-process poller, but this lets you
poll on a separate cadence / machine).  Usage:  python scripts/run_poller.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings   # noqa: E402
from app.data import poller        # noqa: E402
from app.lib import db             # noqa: E402


def main() -> None:
    db.init_db()
    interval = max(1, settings.poll_interval_min) * 60
    print(f"[poller] every {settings.poll_interval_min} min")
    while True:
        try:
            print("[poller]", poller.poll_once())
        except Exception as e:  # keep looping on transient errors
            print("[poller] error:", e)
        time.sleep(interval)


if __name__ == "__main__":
    main()
