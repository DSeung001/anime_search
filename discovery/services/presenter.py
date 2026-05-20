from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from django.http import HttpRequest
from django.urls import reverse

from anime_indexing.paths import staging_frames_leaf, staging_input_dir_for_job_frames
from anime_indexing.video.extract import VIDEO_EXTENSIONS, find_first_video
from discovery.services.segment_merge import SceneSegment
from discovery.services.similarity_display import build_display_label, format_similarity_label
from embeddings.models import EmbeddingJob


def _resolve_video_filename(job: EmbeddingJob) -> str | None:
    name = (job.source_video_filename or "").strip()
    if name:
        return Path(name).name
    frames = staging_frames_leaf(job.staging_rel_path)
    video = find_first_video(staging_input_dir_for_job_frames(frames))
    return video.name if video else None


def _fmt_time(sec: float) -> str:
    s = int(max(0, sec))
    return f"{s // 60}:{s % 60:02d}"


@dataclass
class _PresentContext:
    jobs: dict[str, EmbeddingJob]
    video_by_job: dict[str, str | None]
    status_by_job: dict[str, str]


def _load_present_context(segments: list[SceneSegment]) -> _PresentContext:
    ids: list[UUID] = []
    for seg in segments:
        if not seg.job_public_id:
            continue
        try:
            ids.append(UUID(seg.job_public_id))
        except ValueError:
            continue
    if not ids:
        return _PresentContext(jobs={}, video_by_job={}, status_by_job={})

    rows = list(
        EmbeddingJob.objects.filter(public_id__in=ids).select_related("anime", "episode")
    )
    status_by_job = {str(j.public_id): j.status for j in rows}
    jobs = {
        str(j.public_id): j for j in rows if j.status == EmbeddingJob.Status.DONE
    }
    video_by_job = {pid: _resolve_video_filename(j) for pid, j in jobs.items()}
    return _PresentContext(jobs=jobs, video_by_job=video_by_job, status_by_job=status_by_job)


def _present_one(
    segment: SceneSegment,
    request: HttpRequest,
    ctx: _PresentContext,
) -> tuple[dict[str, Any] | None, str | None]:
    """성공 시 (row, None), 실패 시 (None, reason)."""
    if not segment.job_public_id:
        return None, "missing_job_public_id"
    pid = segment.job_public_id
    try:
        UUID(pid)
    except ValueError:
        return None, "invalid_job_public_id"

    frame_file = Path(segment.frame_file).name
    if not frame_file.lower().endswith(".jpg"):
        return None, "invalid_frame"

    job = ctx.jobs.get(pid)
    if job is None:
        st = ctx.status_by_job.get(pid)
        if st is None:
            return None, "job_not_found"
        return None, "job_not_done"

    video_name = ctx.video_by_job.get(pid)
    if not video_name or Path(video_name).suffix.lower() not in VIDEO_EXTENSIONS:
        return None, "no_video"

    anime_title = (job.anime.title or "").strip()
    if not anime_title:
        return None, "missing_anime_title"

    episode_title = (job.episode.title or "").strip()
    if not episode_title:
        return None, "missing_episode_title"

    episode_num = segment.episode if segment.episode is not None else job.episode.number
    time_label = _fmt_time(segment.peak_sec)
    display_label = build_display_label(
        anime_title=anime_title,
        episode=episode_num,
        episode_title=episode_title,
        time_label=time_label,
    )

    return (
        {
            "anime_title": anime_title,
            "episode": episode_num,
            "episode_title": episode_title,
            "display_label": display_label,
            "peak_sec": round(segment.peak_sec, 2),
            "time_label": time_label,
            "score": round(segment.score, 4),
            "similarity_label": format_similarity_label(segment.score),
            "frame_file": frame_file,
            "job_public_id": pid,
            "thumbnail_url": request.build_absolute_uri(
                reverse("discovery_thumb", kwargs={"job_id": job.public_id, "frame_file": frame_file})
            ),
            "video_url": request.build_absolute_uri(
                reverse("discovery_video", kwargs={"job_id": job.public_id, "filename": video_name})
            ),
            "video_start_sec": round(segment.peak_sec, 2),
        },
        None,
    )


def present_scenes(
    segments: list[SceneSegment],
    request: HttpRequest,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ctx = _load_present_context(segments)
    out: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for seg in segments:
        row, reason = _present_one(seg, request, ctx)
        if row:
            out.append(row)
        else:
            dropped.append(
                {
                    "job_public_id": seg.job_public_id,
                    "episode": seg.episode,
                    "peak_sec": round(seg.peak_sec, 2),
                    "score": round(seg.score, 4),
                    "reason": reason or "present_failed",
                }
            )
    return out, dropped
