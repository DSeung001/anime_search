from __future__ import annotations

from django.conf import settings

from anime_indexing.vectors.qdrant_search import search_segments
from discovery.services.segment_merge import SceneSegment, merge_frame_hits
from discovery.tasks import encode_search_query_task


class SearchPipelineError(Exception):
    pass


def _encode_via_celery(search_query: str) -> list[float]:
    q = (search_query or "").strip()
    if not q:
        raise SearchPipelineError("search_query is empty")
    timeout = int(getattr(settings, "SEARCH_CELERY_TIMEOUT_SEC", 120))
    try:
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            return encode_search_query_task.apply(args=[q]).get(timeout=timeout)
        async_result = encode_search_query_task.apply_async(args=[q])
        return async_result.get(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise SearchPipelineError(f"CLIP 검색 벡터 생성 실패: {exc}") from exc


def run_scene_search(
    *,
    search_query: str,
    anime_slug: str | None = None,
    episode: int | None = None,
    genre_slugs: list[str] | None = None,
    limit: int = 50,
) -> list[SceneSegment]:
    vec = _encode_via_celery(search_query)
    hits = search_segments(
        query_vector=vec,
        limit=limit,
        anime_slug=anime_slug,
        episode=episode,
        genre_slugs=genre_slugs,
    )
    gap = float(getattr(settings, "SEGMENT_MERGE_GAP_SEC", 1.5))
    return merge_frame_hits(hits, gap_sec=gap, max_segments=8)
