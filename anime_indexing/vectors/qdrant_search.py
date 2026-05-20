from __future__ import annotations

import logging
from typing import Any

from anime_indexing.vectors.qdrant_client import get_qdrant_client_and_collection

logger = logging.getLogger(__name__)


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
    client, collection = get_qdrant_client_and_collection()
    if client is None or collection is None:
        return []
    flt = build_search_filter(anime_slug=anime_slug, episode=episode, genre_slugs=genre_slugs)
    lim = min(max(1, limit), 100)

    try:
        response = client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=lim,
            query_filter=flt,
            with_payload=True,
        )
        points = list(response.points or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Qdrant search 실패: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for point in points:
        out.append(
            {
                "id": str(point.id),
                "score": float(point.score or 0.0),
                "payload": dict(point.payload or {}),
            }
        )
    return out
