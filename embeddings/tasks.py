from __future__ import annotations

import logging
import time
from uuid import UUID

from celery import shared_task

from anime_indexing.embedding_job_runner import run_single_embedding_job

from embeddings.models import EmbeddingJob
from embeddings.services.job_preflight import check_job_input_video

logger = logging.getLogger(__name__)


def _mark_failed(job: EmbeddingJob, exc: BaseException) -> None:
    job.status = EmbeddingJob.Status.FAILED
    job.last_error = str(exc)[:4000]
    job.save(update_fields=["status", "last_error", "updated_at"])


@shared_task(name="embeddings.run_embedding_job")
def run_embedding_job_task(public_id: str) -> dict[str, str]:
    """단건 잡: 웹/API에서 이미 processing으로 올린 뒤 호출."""
    started = time.monotonic()
    uid = UUID(public_id)
    job = EmbeddingJob.objects.select_related("anime").filter(public_id=uid).first()
    if job is None:
        logger.error("run_embedding_job_task: job not found public_id=%s", public_id)
        return {"public_id": public_id, "status": "not_found"}

    slug = job.anime.slug
    logger.info(
        "embedding job start public_id=%s anime=%s status=%s",
        public_id,
        slug,
        job.status,
    )

    try:
        if job.status != EmbeddingJob.Status.PROCESSING:
            logger.warning(
                "embedding job skip unexpected status public_id=%s status=%s",
                public_id,
                job.status,
            )
            return {"public_id": public_id, "status": job.status}

        # enqueue와 동일: input/ 동영상 필수(ffmpeg 추출 전 재검증)
        input_err = check_job_input_video(job)
        if input_err:
            _mark_failed(job, RuntimeError(input_err))
            return {"public_id": public_id, "status": EmbeddingJob.Status.FAILED}

        run_single_embedding_job(job)
        job.refresh_from_db()
        elapsed = time.monotonic() - started
        logger.info(
            "embedding job done public_id=%s anime=%s status=%s elapsed_sec=%.2f",
            public_id,
            slug,
            job.status,
            elapsed,
        )
        return {"public_id": public_id, "status": job.status}
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "embedding job failed public_id=%s anime=%s",
            public_id,
            slug,
        )
        job.refresh_from_db()
        if job.status != EmbeddingJob.Status.FAILED:
            _mark_failed(job, exc)
        return {"public_id": public_id, "status": EmbeddingJob.Status.FAILED}
