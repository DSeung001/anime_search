from __future__ import annotations

import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from anime_indexing.frame_directory_embedding.runtime import get_vision_worker
from anime_indexing.paths import (
    anime_staging_root,
    ensure_dir,
    frames_leaf_under_media,
    staging_frames_leaf,
    staging_input_dir_for_job_frames,
)
from anime_indexing.vectors.qdrant_upsert import (
    delete_points_for_job_public_id,
    qdrant_is_configured,
    upsert_job_frame_vectors,
)
from anime_indexing.video.extract import extract_frames_ffmpeg, find_first_video
from anime_indexing.video.pts_manifest import (
    MANIFEST_FILENAME,
    load_pts_by_file,
    sorted_frame_jpgs,
    write_frames_pts_manifest,
)

from embeddings.models import EmbeddingJob

logger = logging.getLogger(__name__)


def maybe_extract_video_for_job(job: EmbeddingJob) -> None:
    """
    스테이징 ``frames`` 에 JPG가 없고, 형제 ``input`` 디렉터리에 동영상이 있으면 ffmpeg으로
    프레임을 채운 뒤 ffprobe 기반 PTS 매니페스트를 남긴다.
    """
    frames_leaf = staging_frames_leaf(job.staging_rel_path)
    if any(frames_leaf.glob("*.jpg")):
        return

    input_dir = staging_input_dir_for_job_frames(frames_leaf)
    video = find_first_video(input_dir)
    if video is None:
        return

    ensure_dir(frames_leaf)
    mf = int(getattr(settings, "VIDEO_EXTRACT_MAX_FRAMES", 0))
    max_frames = None if mf <= 0 else mf
    fps_setting = float(getattr(settings, "VIDEO_EXTRACT_FPS", 0.0))
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
        ffprobe_bin = settings.FFPROBE_BIN or None
        write_frames_pts_manifest(
            video_path=video,
            frames_leaf=frames_leaf,
            ffprobe_bin=ffprobe_bin,
        )


def promote_jpgs_from_staging_to_media(*, job: EmbeddingJob) -> Path:
    """
    스테이징 leaf의 JPG(및 PTS 매니페스트)를 캐논 `ANIME_MEDIA_ROOT/{anime.slug}/frames/` 로 이동한다.
    """
    src_leaf = staging_frames_leaf(job.staging_rel_path)
    if not src_leaf.is_dir():
        raise FileNotFoundError(f"스테이징 디렉터리가 없습니다: {src_leaf}")

    jpgs = sorted(src_leaf.glob("*.jpg"))
    if not jpgs:
        raise FileNotFoundError(f"스테이징에 JPG가 없습니다: {src_leaf}")

    dst_leaf = frames_leaf_under_media(job.anime.slug)
    dst_leaf.mkdir(parents=True, exist_ok=True)

    for p in dst_leaf.glob("*.jpg"):
        p.unlink()

    for p in jpgs:
        shutil.move(str(p), str(dst_leaf / p.name))

    man = src_leaf / MANIFEST_FILENAME
    if man.is_file():
        dest_man = dst_leaf / MANIFEST_FILENAME
        if dest_man.is_file():
            dest_man.unlink()
        shutil.move(str(man), str(dest_man))

    job_root = anime_staging_root() / "jobs" / str(job.public_id)
    if job_root.is_dir():
        shutil.rmtree(job_root, ignore_errors=True)

    return dst_leaf


def run_single_embedding_job(job: EmbeddingJob) -> None:
    """이미 ``processing`` 등으로 잠긴 행에 대해 추출·승격·프레임별 CLIP·Qdrant까지 수행."""
    from embeddings.services.job_staging import ensure_job_staging_dirs

    job = EmbeddingJob.objects.select_related("anime").prefetch_related("anime__genres").get(pk=job.pk)

    ensure_job_staging_dirs(job)
    maybe_extract_video_for_job(job)
    dst_leaf = promote_jpgs_from_staging_to_media(job=job)

    jpgs = sorted_frame_jpgs(dst_leaf)
    if not jpgs:
        raise RuntimeError("프레임이 0개입니다.")

    pts_map = load_pts_by_file(dst_leaf)
    default_fps = 24.0
    times: list[float] = []
    for i, p in enumerate(jpgs):
        if p.name in pts_map:
            times.append(pts_map[p.name])
        else:
            times.append(float(i) / default_fps)

    delete_points_for_job_public_id(job.public_id)

    worker = get_vision_worker()
    genre_slugs = list(job.anime.genres.order_by("slug").values_list("slug", flat=True))

    bs = max(1, int(settings.ANIME_EMBED_BATCH_SIZE))
    for start in range(0, len(jpgs), bs):
        batch_paths = jpgs[start : start + bs]
        path_strs = [str(x) for x in batch_paths]
        matrix, _, _ = worker.extract_features_from_paths(
            path_strs,
            batch_size=settings.ANIME_EMBED_BATCH_SIZE,
            num_workers=settings.ANIME_EMBED_NUM_WORKERS,
            verbose=False,
        )
        n = len(batch_paths)
        frame_indices = [start + j for j in range(n)]
        batch_ts = [times[start + j] for j in range(n)]
        names = [p.name for p in batch_paths]
        upsert_job_frame_vectors(
            job_public_id=job.public_id,
            anime_slug=job.anime.slug,
            episode=job.episode,
            genre_slugs=genre_slugs,
            frame_indices=frame_indices,
            vectors=matrix,
            timestamps=batch_ts,
            frame_files=names,
        )

    if not qdrant_is_configured():
        logger.warning(
            "임베딩 잡 완료했으나 Qdrant 미설정 — 컬렉션·포인트가 생성되지 않습니다. "
            "Celery worker에 QDRANT_URL을 export한 뒤 잡을 재실행하세요. "
            "job_public_id=%s frames=%s",
            job.public_id,
            len(jpgs),
        )

    job.status = EmbeddingJob.Status.DONE
    job.last_error = ""
    job.processed_at = timezone.now()
    job.save(update_fields=["status", "last_error", "processed_at", "updated_at"])


def process_next_pending_job() -> bool:
    """
    pending 작업 하나를 처리한다. 성공 시 True, 처리할 것이 없으면 False.
    """
    with transaction.atomic():
        job = (
            EmbeddingJob.objects.select_related("anime")
            .select_for_update()
            .filter(status=EmbeddingJob.Status.PENDING)
            .order_by("created_at")
            .first()
        )
        if job is None:
            return False
        job.status = EmbeddingJob.Status.PROCESSING
        job.save(update_fields=["status", "updated_at"])

    try:
        run_single_embedding_job(job)
    except Exception as exc:  # noqa: BLE001
        job.status = EmbeddingJob.Status.FAILED
        job.last_error = str(exc)[:4000]
        job.save(update_fields=["status", "last_error", "updated_at"])

    return True
