"""Central config. Reads .env (root or backend/) and exposes a single `settings`.

Real providers only: LLM (DeepSeek/Anthropic) and search (Tavily/Serper) require
API keys; without them the app fails loudly rather than faking results. Polymarket
market data is public (no key). The virtual account is the only simulated element.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root first, then backend/ (backend wins if both set a key).
_BACKEND_DIR = Path(__file__).resolve().parent.parent          # backend/
_ROOT_DIR = _BACKEND_DIR.parent                                 # repo root
load_dotenv(_ROOT_DIR / ".env")
load_dotenv(_BACKEND_DIR / ".env", override=True)

DATA_DIR = _BACKEND_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _f(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _i(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


class Settings:
    # LLM provider (real only): deepseek | anthropic
    llm_provider: str = (os.getenv("LLM_PROVIDER", "deepseek").strip().lower() or "deepseek")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "").strip()
    deepseek_base_url: str = (os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
                              or "https://api.deepseek.com")
    deepseek_model: str = (os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
                           or "deepseek-v4-flash")
    # V4 is a dual-mode reasoning model; non-thinking gives reliable direct JSON
    # (thinking burns the token budget on reasoning_content). Default off.
    deepseek_thinking: bool = os.getenv("DEEPSEEK_THINKING", "0") == "1"

    search_provider: str = os.getenv("SEARCH_PROVIDER", "tavily").strip() or "tavily"
    search_api_key: str = os.getenv("SEARCH_API_KEY", "").strip()
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "fastembed").strip() or "fastembed"
    fastembed_model: str = (os.getenv("FASTEMBED_MODEL",
                                      "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2").strip()
                            or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    voyage_api_key: str = os.getenv("VOYAGE_API_KEY", "").strip()
    # cosine floor for KB retrieval — below this a past lesson is too unrelated to inject
    kb_min_score: float = _f("KB_MIN_SCORE", "0.2")

    poll_interval_min: int = _i("POLL_INTERVAL_MIN", "60")
    default_stake_usd: float = _f("DEFAULT_STAKE_USD", "100")
    starting_balance_usd: float = _f("STARTING_BALANCE_USD", "10000")
    max_spend_usd: float = _f("MAX_SPEND_USD", "5")

    forecaster_model: str = os.getenv("FORECASTER_MODEL", "claude-sonnet-4-6").strip()
    cheap_model: str = os.getenv("CHEAP_MODEL", "claude-haiku-4-5-20251001").strip()
    ensemble_n: int = _i("ENSEMBLE_N", "3")
    # max LangGraph steps per agent run — caps runaway tool-call loops (cost guard).
    # Each ReAct cycle costs ~2 steps (model + tool); a reasoning model doing a few
    # searches needs >12, so 12 made every run hit GraphRecursionError → no JSON. 30
    # gives comfortable headroom while still bounding cost (the budget guard caps spend).
    agent_recursion_limit: int = _i("AGENT_RECURSION_LIMIT", "30")
    # retries (exponential backoff + jitter) on transient LLM failures (429/5xx/timeout)
    llm_max_retries: int = _i("LLM_MAX_RETRIES", "3")
    # disk-cache entry TTL in hours (0 = never expire; prompts already roll over daily by key)
    cache_ttl_hours: int = _i("CACHE_TTL_HOURS", "0")

    # auto-pull markets on startup if store is empty (disable in tests)
    auto_ingest: bool = os.getenv("AUTO_INGEST", "1") == "1"
    # browser origins allowed by CORS (comma-separated). Default: local dev (Vite + compose).
    cors_origins: list[str] = [
        o.strip() for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:8080").split(",")
        if o.strip()
    ]
    # optional API tokens for an internal team: "tok1:alice,tok2:bob". Empty = auth
    # OFF (open, identity falls back to the X-User header or "local"). Light by design:
    # no JWT/RBAC/multi-tenant — just attribution + an optional gate.
    api_tokens: dict[str, str] = {
        p.split(":", 1)[0].strip(): p.split(":", 1)[1].strip()
        for p in os.getenv("API_TOKENS", "").split(",") if ":" in p
    }

    data_dir: Path = DATA_DIR
    cache_dir: Path = CACHE_DIR
    db_path: Path = DATA_DIR / "forecastlab.db"

    @property
    def llm_mode(self) -> str:
        """Real provider only (default deepseek). No mock."""
        return "anthropic" if self.llm_provider == "anthropic" else "deepseek"

    @property
    def llm_ready(self) -> bool:
        return bool(self.deepseek_api_key if self.llm_mode == "deepseek"
                    else self.anthropic_api_key)

    @property
    def search_mode(self) -> str:
        return self.search_provider if self.search_provider in ("tavily", "serper") else "tavily"

    @property
    def search_ready(self) -> bool:
        return self.search_provider in ("tavily", "serper") and bool(self.search_api_key)


settings = Settings()
