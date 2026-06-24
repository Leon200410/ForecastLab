"""Pull open Polymarket markets into the local store."""
from ..lib import db
from . import polymarket


def ingest_open(limit: int = 50) -> dict:
    db.purge_legacy_mock()  # drop any leftover sample-/demo- rows from old builds
    markets = polymarket.list_open_markets(limit)
    if polymarket.last_source == "polymarket":
        # prune stale OPEN markets no longer in the feed (e.g. now decided/resolved),
        # unless they carry a forecast/bet (those are kept for history)
        fresh = {m["id"] for m in markets}
        referenced = ({f["market_id"] for f in db.list_all("forecasts")}
                      | {b["market_id"] for b in db.list_all("bets")})
        for m in db.list_all("markets", status="open"):
            if m["id"] not in fresh and m["id"] not in referenced:
                db.delete("markets", m["id"])
    for m in markets:
        db.put("markets", m)
    return {"ingested": len(markets), "source": polymarket.last_source}
