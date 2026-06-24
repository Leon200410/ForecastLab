"""Embedding provider for the RAG knowledge base.

Default `local`: a dependency-free deterministic hashing embedding (token →
buckets, tf-weighted, L2-normalized). Good enough to retrieve similar past
reviews by question text. Swap to sentence-transformers / Voyage via env.
"""
import hashlib
import math
import re
from typing import Optional

from ..config import settings

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


class SentenceTransformerEmbedding:
    mode = "sentence-transformers"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.encode(texts, normalize_embeddings=True)]


_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        if settings.embedding_provider == "sentence-transformers":
            try:
                _embedder = SentenceTransformerEmbedding()
                return _embedder
            except Exception:
                pass  # fall back to local if model/lib unavailable
        _embedder = LocalHashingEmbedding()
    return _embedder
