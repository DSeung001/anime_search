from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _client():
    url = getattr(settings, "QDRANT_URL", "") or ""
    if not url:
        return None, None
    try:
        from qdrant_client import QdrantClient  # type: ignore[import-untyped]
    except ImportError:
        return None, None
    client = QdrantClient(url=url, api_key=settings.QDRANT_API_KEY or None)
    return client, settings.QDRANT_COLLECTION


def build_search_filter(
    *,
    anime_slug: str | None,
    episode: int | None,
    genre_slugs: list[str] | None,
) -> Any | None:
    """선택 필드가 하나도 없으면 None."""
    from qdrant_client.models import (  # type: ignore[import-untyped]
        FieldCondition,
        Filter,
        MatchAny,
        MatchValue,
    )

    must: list[Any] = []
    if anime_slug:
        must.append(FieldCondition(key="anime_id", match=MatchValue(value=anime_slug)))
    if episode is not None:
        must.append(FieldCondition(key="episode", match=MatchValue(value=int(episode))))
    if genre_slugs:
        must.append(FieldCondition(key="genre", match=MatchAny(any=list(genre_slugs))))
    if not must:
        return None
    return Filter(must=must)


def search_segments(
    *,
    query_vector: list[float],
    limit: int = 20,
    anime_slug: str | None = None,
    episode: int | None = None,
    genre_slugs: list[str] | None = None,
) -> list[dict[str, Any]]:
    pair = _client()
    if pair[0] is None:
        return []
    client, collection = pair
    flt = build_search_filter(anime_slug=anime_slug, episode=episode, genre_slugs=genre_slugs)
    try:
        hits = client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=min(max(1, limit), 100),
            query_filter=flt,
            with_payload=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Qdrant search 실패: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for h in hits:
        out.append(
            {
                "id": str(h.id),
                "score": float(h.score),
                "payload": dict(h.payload or {}),
            }
        )
    return out
