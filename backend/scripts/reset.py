"""Reset to REAL data: wipe all local data (markets / forecasts / bets / reviews /
account / KB + cache) and ingest live Polymarket markets only.

Wipes everything and pulls real markets. Never fabricates data — if the live API
is unreachable it leaves the store empty and warns.

  python scripts/reset.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings        # noqa: E402
from app.data import polymarket        # noqa: E402
from app.lib import db                 # noqa: E402
from app.portfolio import account      # noqa: E402


def main(limit: int = 50) -> None:
    db.init_db()
    db.clear_all()

    # clear cached search/fetch/LLM results too
    if settings.cache_dir.exists():
        shutil.rmtree(settings.cache_dir, ignore_errors=True)
        settings.cache_dir.mkdir(parents=True, exist_ok=True)

    account.get_or_init_account()  # fresh virtual account at starting balance

    markets = polymarket.list_open_markets(limit)
    if polymarket.last_source == "polymarket":
        for m in markets:
            db.put("markets", m)
        print(f"[OK] wiped all data; ingested {len(markets)} REAL Polymarket markets")
    else:
        print("[WARN] live Polymarket API unreachable - store left EMPTY (no sample/mock "
              "markets written). Re-run when the network is up.")

    print(f"  llm={settings.llm_mode} (ready={settings.llm_ready})  "
          f"search={settings.search_mode} (ready={settings.search_ready})  "
          f"embedding={settings.embedding_provider}")
    if not settings.llm_ready:
        print("  NOTE: LLM not ready - set DEEPSEEK_API_KEY (or ANTHROPIC_API_KEY) in .env.")
    if not settings.search_ready:
        print("  NOTE: search not ready - set SEARCH_PROVIDER=tavily + SEARCH_API_KEY in .env.")


if __name__ == "__main__":
    main()
