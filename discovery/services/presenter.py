from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from django.http import HttpRequest
from django.urls import reverse

from anime_indexing.paths import staging_frames_leaf, staging_input_dir_for_job_frames
from anime_indexing.video.extract import VIDEO_EXTENSIONS, find_first_video
from discovery.services.segment_merge import SceneSegment
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


def present_scene(segment: SceneSegment, request: HttpRequest) -> dict[str, Any] | None:
    if not segment.job_public_id:
        return None
    try:
        job_uuid = UUID(segment.job_public_id)
    except ValueError:
        return None
    job = (
        EmbeddingJob.objects.filter(public_id=job_uuid, status=EmbeddingJob.Status.DONE)
        .select_related("anime", "episode")
        .first()
    )
    if job is None:
        return None

    frame_file = Path(segment.frame_file).name
    if not frame_file.lower().endswith(".jpg"):
        return None

    video_name = _resolve_video_filename(job)
    if not video_name or Path(video_name).suffix.lower() not in VIDEO_EXTENSIONS:
        return None

    anime = job.anime
    title = (anime.title or "").strip() or anime.slug

    return {
        "anime_id": segment.anime_id or anime.slug,
        "anime_title": title,
        "episode": segment.episode if segment.episode is not None else job.episode.number,
        "start_sec": round(segment.start_sec, 2),
        "end_sec": round(segment.end_sec, 2),
        "peak_sec": round(segment.peak_sec, 2),
        "time_label": _fmt_time(segment.peak_sec),
        "score": round(segment.score, 4),
        "frame_file": frame_file,
        "job_public_id": str(job.public_id),
        "thumbnail_url": request.build_absolute_uri(
            reverse("discovery_thumb", kwargs={"job_id": job.public_id, "frame_file": frame_file})
        ),
        "video_url": request.build_absolute_uri(
            reverse("discovery_video", kwargs={"job_id": job.public_id, "filename": video_name})
        ),
        "video_start_sec": round(segment.peak_sec, 2),
        "genre": segment.genre,
    }


def present_scenes(segments: list[SceneSegment], request: HttpRequest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in segments:
        row = present_scene(seg, request)
        if row:
            out.append(row)
    return out
