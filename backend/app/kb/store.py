"""Vector store for the RAG knowledge base.

Built-in local store: vectors live in the `kb` SQLite table, similarity via a
single vectorized numpy pass (fine for up to ~10^5 rows). Past that, swap in a
real ANN index (sqlite-vec / Chroma / pgvector) behind this same add()/search()
interface — callers only depend on these three functions.
"""
import numpy as np

from ..lib import db
from ..lib.util import new_id
from ..providers.embedding import get_embedder


def add(text: str, payload: dict) -> None:
    vec = get_embedder().embed([text])[0]
    db.kb_add(new_id("kb"), vec, payload)


def search(query: str, k: int = 3, min_score: float = 0.0) -> list[dict]:
    rows = db.kb_all()
    if not rows:
        return []
    qv = np.asarray(get_embedder().embed([query])[0], dtype=np.float32)
    # only stack vectors of the query's dim — rows from a different embedding model
    # (e.g. after switching EMBEDDING_PROVIDER) are skipped, not silently truncated.
    vecs, payloads = [], []
    for vec, payload in rows:
        if len(vec) == qv.shape[0]:
            vecs.append(vec)
            payloads.append(payload)
    if not vecs:
        return []
    mat = np.asarray(vecs, dtype=np.float32)
    sims = (mat @ qv) / (np.linalg.norm(mat, axis=1) * np.linalg.norm(qv) + 1e-9)
    out: list[dict] = []
    for i in np.argsort(-sims):                  # descending similarity
        if sims[i] < min_score:
            break                                # the rest are below the floor too
        out.append(payloads[i])
        if len(out) >= k:
            break
    return out


def count() -> int:
    return len(db.kb_all())
