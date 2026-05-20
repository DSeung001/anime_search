from __future__ import annotations

from django.conf import settings

from discovery.services.segment_merge import SceneSegment


def _segment_summary(seg: SceneSegment) -> dict:
    return {
        "score": round(seg.score, 4),
        "anime_id": seg.anime_id,
        "episode": seg.episode,
        "peak_sec": round(seg.peak_sec, 2),
        "job_public_id": seg.job_public_id,
        "frame_file": seg.frame_file,
    }


def filter_segments_for_display(
    segments: list[SceneSegment],
) -> tuple[list[SceneSegment], list[dict]]:
    """점수 미달 탈락 후 상위 N개만 반환. (kept, dropped with reason)."""
    min_score = float(getattr(settings, "SEARCH_MIN_SCORE", 0.24))
    max_scenes = int(getattr(settings, "SEARCH_MAX_SCENES", 12))
    kept: list[SceneSegment] = []
    dropped: list[dict] = []
    for seg in segments:
        if seg.score < min_score:
            row = _segment_summary(seg)
            row["reason"] = "below_min_score"
            dropped.append(row)
        else:
            kept.append(seg)
    overflow = kept[max_scenes:]
    kept = kept[:max_scenes]
    for seg in overflow:
        row = _segment_summary(seg)
        row["reason"] = "max_scenes_cap"
        dropped.append(row)
    return kept, dropped
