"""Hybrid search: FTS5キーワード検索 + ベクトル検索をRRFで統合.

RRF (Reciprocal Rank Fusion):
  score(d) = sum(1 / (k + rank_i(d)))
  k=60。異なるランキング手法の結果を公平に統合する。

Time Decay:
  score *= 0.5^(days_since / half_life)
  half_life=60日。古い記憶ほどスコアが減衰する。
"""

import logging
import math
from datetime import datetime, timezone
from pathlib import Path

from .db import fts_search, vec_search, open_db
from .embedder import embed_query

logger = logging.getLogger(__name__)

RRF_K = 60
HALF_LIFE_DAYS = 60


def time_decay(created_at: str, now: datetime | None = None) -> float:
    """時間減衰係数を計算."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        created = datetime.fromisoformat(created_at)
    except (ValueError, TypeError):
        return 1.0
    days = (now - created).total_seconds() / 86400
    if days < 0:
        return 1.0
    return math.pow(0.5, days / HALF_LIFE_DAYS)


def rrf_fusion(
    fts_results: list[dict],
    vec_results: list[dict],
    now: datetime | None = None,
) -> list[dict]:
    """RRFで2つの検索結果を統合し、時間減衰を適用."""
    scores: dict[int, float] = {}
    items: dict[int, dict] = {}

    for rank, item in enumerate(fts_results):
        mid = item["id"]
        scores[mid] = scores.get(mid, 0) + 1.0 / (RRF_K + rank + 1)
        items[mid] = item

    for rank, item in enumerate(vec_results):
        mid = item["id"]
        scores[mid] = scores.get(mid, 0) + 1.0 / (RRF_K + rank + 1)
        items[mid] = item

    for mid in scores:
        decay = time_decay(items[mid].get("created_at", ""), now)
        scores[mid] *= decay

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    results = []
    for mid in sorted_ids:
        item = dict(items[mid])
        item["rrf_score"] = round(scores[mid], 6)
        results.append(item)

    return results


def hybrid_search(query: str, limit: int = 5, db_path: Path | None = None) -> list[dict]:
    """ハイブリッド検索のメインエントリポイント."""
    with open_db(db_path) as db:
        fts_results = fts_search(db, query, limit=20)

        query_vec = embed_query(query)
        try:
            vec_results = vec_search(db, query_vec, limit=20)
        except Exception:
            logger.warning("Vector search failed, falling back to FTS only", exc_info=True)
            vec_results = []

        merged = rrf_fusion(fts_results, vec_results)

        return merged[:limit]
