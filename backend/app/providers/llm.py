"""LLM provider — real only (no mock).

deepseek (default) or anthropic, chosen by LLM_PROVIDER. get_llm() raises a clear
error if the selected provider has no API key (the app never silently fakes a
response). Single interface: complete(prompt, ...). `purpose`/`seed` are accepted
for call-site compatibility (DeepSeek/Anthropic ignore them beyond the cache key).
"""
from typing import Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from ..config import settings
from ..lib import cache
from ..lib.cost_tracker import tracker


def _is_transient(e: BaseException) -> bool:
    """Retry only on transient failures: network/timeout, rate-limit, server errors."""
    if isinstance(e, httpx.TransportError):  # timeouts, connection resets, DNS, etc.
        return True
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (429, 500, 502, 503, 504)
    return False


class AnthropicLLM:
    mode = "anthropic"

    def __init__(self) -> None:
        import anthropic  # lazy: only imported when actually used
        # SDK has built-in exponential backoff on 429/5xx/connection errors.
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key,
                                            max_retries=settings.llm_max_retries)

    def complete(self, prompt: str, *, system: Optional[str] = None, model: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024,
                 purpose: str = "generic", seed: int = 0) -> str:
        model = model or settings.forecaster_model
        ck = ("llm", model, max_tokens, system or "", prompt, round(temperature, 3), seed)
        hit = cache.get_cached(*ck)
        if hit is not None:
            return hit
        tracker.check()
        kwargs = dict(model=model, max_tokens=max_tokens, temperature=temperature,
                      messages=[{"role": "user", "content": prompt}])
        if system:
            kwargs["system"] = system
        msg = self._client.messages.create(**kwargs)
        text = "".join(getattr(b, "text", "") for b in msg.content)
        try:
            tracker.record(model, msg.usage.input_tokens, msg.usage.output_tokens, kind=purpose)
        except Exception:
            pass
        cache.set_cached(text, *ck)
        return text


class DeepSeekLLM:
    """DeepSeek V4 (OpenAI-compatible /chat/completions). Default deepseek-v4-flash,
    non-thinking mode (see config.deepseek_thinking) for reliable structured JSON."""
    mode = "deepseek"

    def __init__(self) -> None:
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url.rstrip("/")
        self.model = settings.deepseek_model

    def complete(self, prompt: str, *, system: Optional[str] = None, model: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024,
                 purpose: str = "generic", seed: int = 0) -> str:
        ck = ("deepseek", self.model, settings.deepseek_thinking, max_tokens, system or "",
              prompt, round(temperature, 3), seed)
        hit = cache.get_cached(*ck)
        if hit is not None:
            return hit
        tracker.check()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        @retry(reraise=True, retry=retry_if_exception(_is_transient),
               stop=stop_after_attempt(settings.llm_max_retries + 1),
               wait=wait_random_exponential(multiplier=1, max=20))
        def _do() -> dict:
            r = httpx.post(
                f"{self.base_url}/chat/completions", timeout=120,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages,
                      "temperature": temperature, "max_tokens": max_tokens, "stream": False,
                      "chat_template_kwargs": {"thinking": settings.deepseek_thinking}},
            )
            r.raise_for_status()
            return r.json()

        try:
            data = _do()
            msg = data["choices"][0]["message"]
            # reasoning models (e.g. deepseek-v4-flash) can spend the budget on
            # reasoning_content and leave content empty — fall back so we still get text.
            text = msg.get("content") or msg.get("reasoning_content") or ""
            usage = data.get("usage", {})
            tracker.record(self.model, usage.get("prompt_tokens", 0),
                           usage.get("completion_tokens", 0), kind=purpose)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise RuntimeError(f"DeepSeek call failed: {e}")
        cache.set_cached(text, *ck)
        return text


_llm = None


def get_llm():
    global _llm
    if _llm is None:
        if settings.llm_mode == "deepseek":
            if not settings.deepseek_api_key:
                raise RuntimeError(
                    "DEEPSEEK_API_KEY not set — configure a real LLM in .env "
                    "(or set LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY).")
            _llm = DeepSeekLLM()
        else:
            if not settings.anthropic_api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set — configure a real LLM in .env "
                    "(or set LLM_PROVIDER=deepseek + DEEPSEEK_API_KEY).")
            _llm = AnthropicLLM()
    return _llm
