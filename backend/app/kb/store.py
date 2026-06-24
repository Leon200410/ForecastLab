"""Vector store for the RAG knowledge base.

Built-in local store: vectors live in the `kb` SQLite table, cosine similarity
in pure Python. Small corpus (dozens–hundreds of reviews) → linear scan is fine.
Swap for Chroma later behind this same add()/search() interface.
"""
import math

from ..lib import db
from ..lib.util import new_id
from ..providers.embedding import get_embedder


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def add(text: str, payload: dict) -> None:
    vec = get_embedder().embed([text])[0]
    db.kb_add(new_id("kb"), vec, payload)


def search(query: str, k: int = 3) -> list[dict]:
    rows = db.kb_all()
    if not rows:
        return []
    qv = get_embedder().embed([query])[0]
    scored = sorted(((_cosine(qv, vec), payload) for vec, payload in rows),
                    key=lambda x: x[0], reverse=True)
    return [payload for _, payload in scored[:k]]


def count() -> int:
    return len(db.kb_all())
