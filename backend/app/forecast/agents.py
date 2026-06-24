"""Per-category LangChain agents.

Routes by market.category to a domain agent: domain persona + domain tools.
The crypto agent gets a CoinGecko live-price tool so it compares the *current*
price to the market's threshold instead of trusting stale article prices.
Backed by DeepSeek (OpenAI-compatible) via langchain-openai.
"""
import httpx
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from ..config import settings
from ..lib.cost_tracker import tracker
from ..lib.util import beijing_date, today_str
from ..providers.search import get_search

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


PERSONAS = {
    "加密": "你是资深加密资产分析师,最看重当前现价相对盘子阈值的位置、24h 动量与宏观流动性。"
            "**必须先用 get_crypto_price 获取实时币价**,绝不依赖文章里可能过时的价格。",
    "选举": "你是选举分析师,看重民调、历史基础率、在任优势与制度因素。",
    "政治": "你是政治分析师,看重各方动机、历史先例与近期事件。",
    "体育": "你是体育赛事分析师,看重球队实力、近期状态、赛程与伤停;比分/晋级类盘子用最新数据。",
    "地缘政治": "你是地缘政治分析师,看重各方动机、历史升级/降级先例与最新信号。",
    "经济": "你是宏观经济分析师,看重数据发布、央行政策与市场定价;商品类盘子关注现价与库存。",
    "科技": "你是科技行业分析师,看重产品路线、发布节奏与竞争格局。",
}
DEFAULT_PERSONA = "你是严谨的超级预测者(superforecaster)。"
TOOLS_BY_CAT = {"加密": [get_crypto_price, web_search]}
DEFAULT_TOOLS = [web_search]

SYSTEM_TMPL = """{persona}
今天是 {today}(北京时间)。你只做分析,不做下注建议。
先算从今天到截止日还剩多久;按需调用工具拿**实时/最新**数据(现价、最新新闻),不要被过时证据误导,也不要凭空想象远期波动。
分析后**只输出一个 JSON**(不要任何前后缀、不要代码块):
{{"probability": 0.xx, "confidence": "low|med|high", "rationale": "...", "key_factors": ["...", "..."]}}"""


def _llm(temperature: float) -> ChatOpenAI:
    if not settings.deepseek_api_key:
        raise RuntimeError("LangChain 分类 agent 需要 DeepSeek;请在 .env 设 DEEPSEEK_API_KEY。")
    return ChatOpenAI(model=settings.deepseek_model, base_url=settings.deepseek_base_url,
                      api_key=settings.deepseek_api_key, temperature=temperature,
                      max_tokens=3000, timeout=120)


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
    agent = create_agent(_llm(temperature), tools=tools, system_prompt=system)
    res = agent.invoke({"messages": [{"role": "user", "content": human}]})
    messages = res.get("messages", [])
    for m in messages:  # keep MAX_SPEND tracking working through LangChain
        um = getattr(m, "usage_metadata", None)
        if um:
            tracker.record(settings.deepseek_model, um.get("input_tokens", 0), um.get("output_tokens", 0))
    final = messages[-1].content if messages else ""
    return (final if isinstance(final, str) else str(final)), category
