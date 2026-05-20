from __future__ import annotations

import logging
from uuid import UUID

from celery import shared_task

from anime_indexing.paths import staging_frames_leaf, staging_input_dir_for_job_frames

from catalog.services.youtube_import import download_to_input_dir, normalize_youtube_url
from embeddings.models import EmbeddingJob
from embeddings.services.job_auto_enqueue import try_auto_enqueue_job
from embeddings.services.job_staging import ensure_job_staging_dirs

logger = logging.getLogger(__name__)


def _mark_import_failed(job: EmbeddingJob, exc: BaseException) -> None:
    job.status = EmbeddingJob.Status.FAILED
    job.last_error = str(exc)[:4000]
    job.save(update_fields=["status", "last_error", "updated_at"])


@shared_task(name="catalog.import_youtube_video")
def import_youtube_video_task(public_id: str, youtube_url: str) -> dict[str, str]:
    """YouTube URL → 스테이징 input/ → pending 후 자동 enqueue."""
    uid = UUID(public_id)
    job = EmbeddingJob.objects.select_related("anime").filter(public_id=uid).first()
    if job is None:
        logger.error("import_youtube: job not found public_id=%s", public_id)
        return {"public_id": public_id, "status": "not_found"}

    if job.status != EmbeddingJob.Status.IMPORTING:
        logger.info(
            "import_youtube: skip public_id=%s status=%s",
            public_id,
            job.status,
        )
        return {"public_id": public_id, "status": job.status}

    try:
        canonical_url = normalize_youtube_url(youtube_url)
        ensure_job_staging_dirs(job)
        frames_leaf = staging_frames_leaf(job.staging_rel_path)
        input_dir = staging_input_dir_for_job_frames(frames_leaf)

        video_path = download_to_input_dir(url=canonical_url, input_dir=input_dir)
        dest_name = video_path.name

        job.source_video_filename = dest_name
        job.youtube_source_url = canonical_url
        job.status = EmbeddingJob.Status.PENDING
        job.last_error = ""
        job.save(
            update_fields=[
                "source_video_filename",
                "youtube_source_url",
                "status",
                "last_error",
                "updated_at",
            ]
        )

        enqueued = try_auto_enqueue_job(uid)
        logger.info(
            "import_youtube: done public_id=%s file=%s auto_enqueue=%s",
            public_id,
            dest_name,
            enqueued,
        )
        return {
            "public_id": public_id,
            "status": job.status,
            "filename": dest_name,
            "auto_enqueued": str(enqueued),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("import_youtube: failed public_id=%s", public_id)
        job.refresh_from_db()
        if job.status == EmbeddingJob.Status.IMPORTING:
            _mark_import_failed(job, exc)
        return {"public_id": public_id, "status": EmbeddingJob.Status.FAILED}
