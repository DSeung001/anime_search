from __future__ import annotations

import logging
import time

from django.conf import settings
from django.utils import timezone

from anime_indexing.frame_directory_embedding.runtime import get_vision_worker
from anime_indexing.observability.pipeline_tracer import PipelineTracer
from anime_indexing.paths import staging_frames_leaf
from anime_indexing.vectors.qdrant_upsert import (
    delete_points_for_anime_episode,
    qdrant_is_configured,
    upsert_job_frame_vectors,
)
from anime_indexing.video.frame_timestamps import (
    compute_frame_timestamps_sec,
    ensure_pts_manifest_if_needed,
    get_extract_fps,
    manifest_present,
)
from anime_indexing.video.pts_manifest import sorted_frame_jpgs, write_frames_pts_manifest

from embeddings.models import EmbeddingJob

logger = logging.getLogger(__name__)


def maybe_extract_video_for_job(job: EmbeddingJob) -> None:
    """
    스테이징 ``frames`` 에 JPG가 없고, 형제 ``input`` 디렉터리에 동영상이 있으면 ffmpeg으로
    프레임을 채운 뒤 ffprobe 기반 PTS 매니페스트를 남긴다.
    """
    from anime_indexing.paths import ensure_dir, staging_input_dir_for_job_frames
    from anime_indexing.video.extract import extract_frames_ffmpeg, find_first_video
    from anime_indexing.video.pts_manifest import write_frames_pts_manifest

    frames_leaf = staging_frames_leaf(job.staging_rel_path)
    input_dir = staging_input_dir_for_job_frames(frames_leaf)
    video = find_first_video(input_dir)
    ffprobe_bin = settings.FFPROBE_BIN or None

    if any(frames_leaf.glob("*.jpg")):
        ensure_pts_manifest_if_needed(
            frames_leaf=frames_leaf,
            video_path=video,
            ffprobe_bin=ffprobe_bin,
        )
        return

    if video is None:
        return

    ensure_dir(frames_leaf)
    mf = int(getattr(settings, "VIDEO_EXTRACT_MAX_FRAMES", 0))
    max_frames = None if mf <= 0 else mf
    fps_setting = get_extract_fps()
    fps_arg = None if fps_setting <= 0 else fps_setting
    extract_frames_ffmpeg(
        video_path=video,
        output_dir=frames_leaf,
        ffmpeg_bin=(settings.FFMPEG_BIN or None),
        fps=fps_arg,
        max_frames=max_frames,
        jpeg_quality=int(getattr(settings, "VIDEO_EXTRACT_JPEG_Q", 2)),
    )
    if any(frames_leaf.glob("*.jpg")):
        write_frames_pts_manifest(
            video_path=video,
            frames_leaf=frames_leaf,
            ffprobe_bin=ffprobe_bin,
        )


def run_single_embedding_job(job: EmbeddingJob) -> None:
    """이미 ``processing`` 등으로 잠긴 행에 대해 추출·CLIP·Qdrant까지 수행 (프레임은 스테이징에 유지)."""
    from embeddings.services.job_staging import ensure_job_staging_dirs

    job = (
        EmbeddingJob.objects.select_related("anime", "episode")
        .prefetch_related("anime__genres")
        .get(pk=job.pk)
    )

    tracer = PipelineTracer.start_indexing(job_public_id=job.public_id)
    tracer.stage(
        "job",
        public_id=str(job.public_id),
        anime_slug=job.anime.slug,
        episode=job.episode.number,
    )

    try:
        ensure_job_staging_dirs(job)
        maybe_extract_video_for_job(job)
        frames_leaf = staging_frames_leaf(job.staging_rel_path)
        if not frames_leaf.is_dir():
            raise FileNotFoundError(f"스테이징 디렉터리가 없습니다: {frames_leaf}")

        jpgs = sorted_frame_jpgs(frames_leaf)
        if not jpgs:
            raise RuntimeError("프레임이 0개입니다.")

        tracer.stage(
            "frames",
            jpg_count=len(jpgs),
            staging_rel_path=job.staging_rel_path,
        )

        from anime_indexing.paths import staging_input_dir_for_job_frames
        from anime_indexing.video.extract import find_first_video

        input_dir = staging_input_dir_for_job_frames(frames_leaf)
        video = find_first_video(input_dir)
        ensure_pts_manifest_if_needed(
            frames_leaf=frames_leaf,
            video_path=video,
            ffprobe_bin=settings.FFPROBE_BIN or None,
        )
        times, ts_source = compute_frame_timestamps_sec(jpgs, frames_leaf)
        tracer.stage(
            "frame_times",
            source=ts_source,
            extract_fps=get_extract_fps(),
            manifest_present=manifest_present(frames_leaf),
            sample_ts=times[:3],
        )

        delete_points_for_anime_episode(
            anime_slug=job.anime.slug,
            episode_number=job.episode.number,
        )
        tracer.stage(
            "qdrant_delete_episode",
            anime_slug=job.anime.slug,
            episode=job.episode.number,
        )

        worker = get_vision_worker()
        genre_slugs = list(job.anime.genres.order_by("slug").values_list("slug", flat=True))

        bs = max(1, int(settings.ANIME_EMBED_BATCH_SIZE))
        points_upserted = 0
        batch_count = 0
        total_clip_ms = 0
        for start in range(0, len(jpgs), bs):
            batch_paths = jpgs[start : start + bs]
            path_strs = [str(x) for x in batch_paths]
            t0 = time.monotonic()
            matrix, _, _ = worker.extract_features_from_paths(
                path_strs,
                batch_size=settings.ANIME_EMBED_BATCH_SIZE,
                num_workers=settings.ANIME_EMBED_NUM_WORKERS,
                verbose=False,
            )
            total_clip_ms += int((time.monotonic() - t0) * 1000)
            n = len(batch_paths)
            batch_count += 1
            frame_indices = [start + j for j in range(n)]
            batch_ts = [times[start + j] for j in range(n)]
            names = [p.name for p in batch_paths]
            upsert_job_frame_vectors(
                job_public_id=job.public_id,
                anime_slug=job.anime.slug,
                episode=job.episode.number,
                episode_id=job.episode_id,
                genre_slugs=genre_slugs,
                frame_indices=frame_indices,
                vectors=matrix,
                timestamps=batch_ts,
                frame_files=names,
            )
            points_upserted += n

        configured = qdrant_is_configured()
        if not configured:
            logger.warning(
                "임베딩 잡 완료했으나 Qdrant 미설정 — 컬렉션·포인트가 생성되지 않습니다. "
                "Celery worker에 QDRANT_URL을 export한 뒤 잡을 재실행하세요. "
                "job_public_id=%s frames=%s",
                job.public_id,
                len(jpgs),
            )

        tracer.stage(
            "indexing_done",
            qdrant_configured=configured,
            frame_count=len(jpgs),
            points_upserted=points_upserted,
            batch_count=batch_count,
            total_clip_ms=total_clip_ms,
        )
        tracer.finish(
            status="ok",
            summary=f"frames={len(jpgs)} points={points_upserted} qdrant={configured}",
        )

        job.status = EmbeddingJob.Status.DONE
        job.last_error = ""
        job.processed_at = timezone.now()
        job.save(update_fields=["status", "last_error", "processed_at", "updated_at"])
    except Exception as exc:
        tracer.stage("error", message=str(exc)[:500])
        tracer.finish(status="error", summary=str(exc)[:512])
        raise
