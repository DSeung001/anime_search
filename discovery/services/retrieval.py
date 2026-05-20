from __future__ import annotations

import time

from django.conf import settings

from anime_indexing.observability.pipeline_tracer import PipelineTracer, summarize_hits
from anime_indexing.vectors.qdrant_search import search_segments
from anime_indexing.vectors.qdrant_upsert import qdrant_is_configured
from discovery.services.query_translate import translate_search_query_for_clip
from discovery.services.scene_filter import filter_segments_for_display
from discovery.services.segment_merge import merge_frame_hits
from discovery.tasks import encode_search_query_task


class SearchPipelineError(Exception):
    pass


def _encode_via_celery(search_query: str) -> tuple[list[float], int]:
    q = (search_query or "").strip()
    if not q:
        raise SearchPipelineError("search_query is empty")
    timeout = int(getattr(settings, "SEARCH_CELERY_TIMEOUT_SEC", 120))
    t0 = time.monotonic()
    try:
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            vec = encode_search_query_task.apply(args=[q]).get(timeout=timeout)
        else:
            async_result = encode_search_query_task.apply_async(args=[q])
            vec = async_result.get(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise SearchPipelineError(f"CLIP 검색 벡터 생성 실패: {exc}") from exc
    ms = int((time.monotonic() - t0) * 1000)
    return vec, ms


def run_scene_search(
    *,
    search_query: str,
    anime_slug: str | None = None,
    episode: int | None = None,
    genre_slugs: list[str] | None = None,
    limit: int = 50,
    tracer: PipelineTracer | None = None,
    request=None,
) -> tuple[str, list[dict]]:
    """Returns (clip_query_en, scene_cards). Presenter runs when request is set."""
    ko = (search_query or "").strip()
    if tracer:
        tracer.stage(
            "input",
            search_query_ko=ko,
            anime_slug=anime_slug,
            episode=episode,
            genre_slugs=genre_slugs or [],
        )

    clip_query = translate_search_query_for_clip(ko)
    if tracer:
        tracer.stage(
            "translate",
            clip_query_en=clip_query,
            skipped=(clip_query == ko),
        )

    vec, encode_ms = _encode_via_celery(clip_query)
    if tracer:
        tracer.stage(
            "clip_encode",
            duration_ms=encode_ms,
            dim=len(vec),
            celery_eager=bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)),
        )

    configured = qdrant_is_configured()
    hits = search_segments(
        query_vector=vec,
        limit=limit,
        anime_slug=anime_slug,
        episode=episode,
        genre_slugs=genre_slugs,
    )
    if tracer:
        tracer.stage(
            "qdrant_search",
            hit_count=len(hits),
            configured=configured,
            top_hits=summarize_hits(hits),
        )

    gap = float(getattr(settings, "SEGMENT_MERGE_GAP_SEC", 1.5))
    merge_cap = int(getattr(settings, "SEARCH_MERGE_MAX_SEGMENTS", 12))
    segments = merge_frame_hits(hits, gap_sec=gap, max_segments=merge_cap)
    if tracer:
        tracer.stage("merge", segment_count=len(segments), merge_cap=merge_cap)

    segments, filter_dropped = filter_segments_for_display(segments)
    if tracer:
        tracer.stage(
            "filter",
            min_score=float(getattr(settings, "SEARCH_MIN_SCORE", 0.24)),
            max_scenes=int(getattr(settings, "SEARCH_MAX_SCENES", 5)),
            kept=len(segments),
            dropped=filter_dropped,
        )

    scenes: list[dict] = []
    if request is not None:
        from discovery.services.presenter import present_scenes

        scenes, present_dropped = present_scenes(segments, request)
        if tracer:
            tracer.stage(
                "present",
                scene_count=len(scenes),
                dropped=present_dropped,
            )

    return clip_query, scenes
