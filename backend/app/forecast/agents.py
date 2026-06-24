"""Per-category LangChain agents.

Routes by market.category to a domain agent: domain persona + domain tools.
The crypto agent gets a CoinGecko live-price tool so it compares the *current*
price to the market's threshold instead of trusting stale article prices.
Backed by DeepSeek (OpenAI-compatible) via langchain-openai.
"""
import httpx
from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from ..config import settings
from ..lib import cache
from ..lib.cost_tracker import tracker
from ..lib.util import beijing_date, today_str
from ..providers.llm import get_llm
from ..providers.search import get_search
from .prompts import DEFAULT_PERSONA, PERSONAS, SYSTEM_TMPL  # noqa: F401 (re-exported)

_COINGECKO = "https://api.coingecko.com/api/v3"
_COIN_IDS = {"btc": "bitcoin", "bitcoin": "bitcoin", "eth": "ethereum", "ethereum": "ethereum",
             "sol": "solana", "solana": "solana", "xrp": "ripple", "ripple": "ripple",
             "doge": "dogecoin", "bnb": "binancecoin", "ada": "cardano"}


@tool
def get_crypto_price(asset: str) -> str:
    """获取加密资产的实时美元价格。asset 用资产名或代号,如 'bitcoin'、'BTC'、'ethereum'、'ETH'、'SOL'。"""
    key = asset.strip().lower()
    cid = _COIN_IDS.get(key)
    try:
        if not cid:
            s = httpx.get(f"{_COINGECKO}/search", params={"query": asset}, timeout=12).json()
            coins = s.get("coins") or []
            cid = coins[0]["id"] if coins else None
        if not cid:
            return f"未找到资产 {asset} 的实时价。"
        r = httpx.get(f"{_COINGECKO}/simple/price", timeout=12,
                      params={"ids": cid, "vs_currencies": "usd", "include_24hr_change": "true"})
        d = r.json().get(cid, {})
        price, chg = d.get("usd"), d.get("usd_24h_change")
        if price is None:
            return f"未取到 {asset} 的实时价。"
        return f"{asset.upper()} 实时价 ${price:,} USD(24h {chg:+.1f}%),即当前价格。"
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as e:
        return f"实时价获取失败:{e}"


@tool
def web_search(query: str) -> str:
    """检索网络获取最新公开信息(新闻、数据)。返回若干条标题 + 摘要 + 链接。"""
    try:
        results = get_search().search(query, 4)
    except Exception as e:  # search may be unconfigured / transient
        return f"检索失败:{e}"
    return "\n".join(
        f"- {r.get('title', '')}: {(r.get('snippet') or '')[:200]} ({r.get('url', '')})"
        for r in results
    ) or "(无结果)"


TOOLS_BY_CAT = {"加密": [get_crypto_price, web_search]}
DEFAULT_TOOLS = [web_search]


def _llm(temperature: float) -> ChatOpenAI:
    if not settings.deepseek_api_key:
        raise RuntimeError("LangChain 分类 agent 需要 DeepSeek;请在 .env 设 DEEPSEEK_API_KEY。")
    return ChatOpenAI(model=settings.deepseek_model, base_url=settings.deepseek_base_url,
                      api_key=settings.deepseek_api_key, temperature=temperature,
                      max_tokens=3000, timeout=120, max_retries=settings.llm_max_retries)


class _BudgetGuard(BaseCallbackHandler):
    """Record token usage and enforce MAX_SPEND *between* agent LLM steps, so a
    single multi-tool agent run can't blow past the cap before the next check."""

    def __init__(self, model: str) -> None:
        self.model = model

    def on_llm_end(self, response, **kwargs) -> None:
        try:
            for gens in response.generations:
                for g in gens:
                    um = getattr(getattr(g, "message", None), "usage_metadata", None)
                    if um:
                        tracker.record(self.model, um.get("input_tokens", 0),
                                       um.get("output_tokens", 0), kind="agent")
        except Exception:
            pass
        tracker.check()  # raises BudgetExceeded mid-run once the cap is hit


def run_category_agent(market: dict, evidence_bullets: str, lessons: str,
                       *, temperature: float) -> tuple[str, str]:
    """Run the domain agent once. Returns (final_text, category)."""
    tracker.check()
    category = market.get("category") or "其他"
    persona = PERSONAS.get(category, DEFAULT_PERSONA)
    tools = TOOLS_BY_CAT.get(category, DEFAULT_TOOLS)
    system = SYSTEM_TMPL.format(persona=persona, today=today_str())
    human = (
        f"问题:{market['question']}\n"
        f"背景:{market.get('description') or ''}\n"
        f"截止日(北京):{beijing_date(market.get('close_at') or '')}\n"
        f"已检索证据(可能过时,请看日期):\n{evidence_bullets}\n"
        f"过往复盘教训:\n{lessons}"
    )
    # cache the whole agent run on its inputs (system carries today's date, so the
    # cache turns over daily); same-day re-forecasts / ensemble reruns are then free
    # and reproducible — closes the gap where the LangChain path bypassed cache.py.
    ck = ("agent", settings.deepseek_model, round(temperature, 3), system, human)
    hit = cache.get_cached(*ck)
    if hit is not None:
        return hit, category

    agent = create_agent(_llm(temperature), tools=tools, system_prompt=system)
    try:
        res = agent.invoke(
            {"messages": [{"role": "user", "content": human}]},
            config={"callbacks": [_BudgetGuard(settings.deepseek_model)],
                    "recursion_limit": settings.agent_recursion_limit},
        )
        messages = res.get("messages", [])
        final = messages[-1].content if messages else ""
        final = final if isinstance(final, str) else str(final)
    except GraphRecursionError:
        # the tool-using agent over-looped without converging (common on data-heavy
        # questions). Fall back to ONE direct analysis call — no tools, no loop, so it
        # always returns. The gathered evidence is already in `human`, so we keep context.
        final = get_llm().complete(human, system=system, temperature=temperature,
                                   max_tokens=2000, purpose="agent_fallback")
    cache.set_cached(final, *ck)
    return final, category
