"""pytest config: isolated temp DB, no auto-ingest, no background poller.

Default tests are provider-free (pure logic + API plumbing) so they need no keys
and make no network calls. The real LLM/search path is covered by the opt-in
live test (tests/test_live.py, RUN_LIVE_TESTS=1).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["AUTO_INGEST"] = "0"
os.environ["POLL_INTERVAL_MIN"] = "0"
os.environ["EMBEDDING_PROVIDER"] = "local"  # deterministic, offline — no model download in tests

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.lib import db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "data_dir", tmp_path)  # isolate cost/audit logs per test
    db.init_db()
    yield
