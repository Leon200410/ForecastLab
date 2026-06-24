"""Embedding provider for the RAG knowledge base.

Default `local`: a dependency-free deterministic hashing embedding (token →
buckets, tf-weighted, L2-normalized). Good enough to retrieve similar past
reviews by question text. Swap to sentence-transformers / Voyage via env.
"""
import hashlib
import logging
import math
import re
from typing import Optional

from ..config import settings

_log = logging.getLogger("forecastlab.embedding")
_DIM = 256
_WORD = re.compile(r"[\w']+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    toks = _WORD.findall(text.lower())
    # add char trigrams too, so CJK (no spaces) and typos still match
    compact = re.sub(r"\s+", "", text.lower())
    toks += [compact[i:i + 3] for i in range(max(0, len(compact) - 2))]
    return toks


class LocalHashingEmbedding:
    mode = "local"
    dim = _DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            vec = [0.0] * _DIM
            for tok in _tokens(t):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
                sign = 1.0 if (h & 1) else -1.0
                vec[h % _DIM] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FastEmbedEmbedding:
    """Real multilingual semantic embeddings via fastembed (ONNX, no torch).
    Runs an orthodox sentence-transformer model; handles EN questions + ZH lessons."""
    mode = "fastembed"

    def __init__(self) -> None:
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name=settings.fastembed_model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(list(texts))]


class SentenceTransformerEmbedding:
    mode = "sentence-transformers"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.encode(texts, normalize_embeddings=True)]


_embedder = None
_active: Optional[dict] = None

_PROVIDERS = {
    "fastembed": FastEmbedEmbedding,
    "sentence-transformers": SentenceTransformerEmbedding,
    "local": LocalHashingEmbedding,
}


def get_embedder():
    global _embedder
    if _embedder is None:
        cls = _PROVIDERS.get(settings.embedding_provider)
        if cls is not None and cls is not LocalHashingEmbedding:
            try:
                _embedder = cls()
                return _embedder
            except Exception:
                # model/lib unavailable -> fall back to the dependency-free local
                # embedder, but make the degradation visible (don't swallow silently).
                _log.warning("embedding provider %r failed to init; falling back to 'local' "
                             "(retrieval quality degraded)", settings.embedding_provider,
                             exc_info=True)
        _embedder = LocalHashingEmbedding()
    return _embedder


def warmup() -> dict:
    """Eagerly load the configured embedder at startup so model download / init
    failures surface at boot (not mid-request). Caches & returns the *active*
    mode + dim; logs a warning if it differs from the configured provider."""
    global _active
    emb = get_embedder()
    dim = len(emb.embed(["warmup"])[0])
    _active = {"mode": emb.mode, "configured": settings.embedding_provider, "dim": dim}
    if emb.mode != settings.embedding_provider:
        _log.warning("configured EMBEDDING_PROVIDER=%r but running on %r (dim=%d)",
                     settings.embedding_provider, emb.mode, dim)
    return _active


def active_info() -> dict:
    """The active embedder's mode/dim (from startup warmup); probes lazily if
    warmup() hasn't run yet."""
    return _active if _active is not None else warmup()
