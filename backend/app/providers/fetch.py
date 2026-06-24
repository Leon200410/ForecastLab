"""Fetch article main text. httpx + a simple HTML stripper (trafilatura optional).

Failures are non-fatal (return ""); the research pipeline falls back to the
search snippet. Results cached.
"""
import re

import httpx

from ..lib import cache

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_HTML = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    try:
        import trafilatura  # optional, better extraction
        extracted = trafilatura.extract(html)
        if extracted:
            return extracted
    except Exception:
        pass
    text = _TAG.sub(" ", html)
    text = _HTML.sub(" ", text)
    return _WS.sub(" ", text).strip()


def fetch_text(url: str, max_chars: int = 4000) -> str:
    if not url:
        return ""
    hit = cache.get_cached("fetch", url)
    if hit is not None:
        return hit[:max_chars]
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True,
                      headers={"User-Agent": "ForecastLab/0.7 (research)"})
        r.raise_for_status()
        text = _strip_html(r.text)[:max_chars]
    except (httpx.HTTPError, UnicodeDecodeError):
        text = ""
    cache.set_cached(text, "fetch", url)
    return text
