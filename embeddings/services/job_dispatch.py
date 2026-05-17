from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from embeddings.models import EmbeddingJob
from embeddings.services.job_preflight import check_job_staging_ready
from embeddings.services.job_staging import ensure_job_staging_dirs


class JobDispatchError(Exception):
    """enqueue 거부 (상태·중복 등)."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class EnqueueResult:
    public_id: str
    celery_task_id: str
    status: str


def _save_task_id(job: EmbeddingJob, async_result) -> str:
    task_id = str(async_result.id)
    job.celery_task_id = task_id
    job.save(update_fields=["celery_task_id", "updated_at"])
    return task_id


def _require_staging_ready(job: EmbeddingJob) -> None:
    err = check_job_staging_ready(job)
    if err:
        raise JobDispatchError(err, status_code=400)


def enqueue_run_job(public_id: UUID) -> EnqueueResult:
    """
    pending 잡을 검증·processing 표시 후 Celery에 단건 실행을 넣는다.
    """
    from embeddings.tasks import run_embedding_job_task

    with transaction.atomic():
        job = (
            EmbeddingJob.objects.select_for_update()
            .filter(public_id=public_id)
            .first()
        )
        if job is None:
            raise JobDispatchError("작업을 찾을 수 없습니다.", status_code=404)
        if job.status == EmbeddingJob.Status.PROCESSING:
            raise JobDispatchError(
                f"이미 처리 중입니다 (task={job.celery_task_id or '—'})",
                status_code=409,
            )
        if job.status != EmbeddingJob.Status.PENDING:
            raise JobDispatchError(
                f"pending 만 실행 가능합니다 (현재 {job.status})",
                status_code=400,
            )
        ensure_job_staging_dirs(job)
        _require_staging_ready(job)
        job.status = EmbeddingJob.Status.PROCESSING
        job.last_error = ""
        job.save(update_fields=["status", "last_error", "updated_at"])

    async_result = run_embedding_job_task.delay(str(public_id))
    task_id = _save_task_id(job, async_result)
    return EnqueueResult(
        public_id=str(public_id),
        celery_task_id=task_id,
        status=job.status,
    )


def enqueue_process_next() -> EnqueueResult | None:
    """
    가장 오래된 pending 잡을 claim 후 Celery 단건 태스크로 실행한다.
    """
    from embeddings.tasks import run_embedding_job_task

    with transaction.atomic():
        job = (
            EmbeddingJob.objects.select_for_update()
            .filter(status=EmbeddingJob.Status.PENDING)
            .order_by("created_at")
            .first()
        )
        if job is None:
            return None
        ensure_job_staging_dirs(job)
        _require_staging_ready(job)
        job.status = EmbeddingJob.Status.PROCESSING
        job.last_error = ""
        job.save(update_fields=["status", "last_error", "updated_at"])
        public_id = str(job.public_id)

    async_result = run_embedding_job_task.delay(public_id)
    task_id = _save_task_id(job, async_result)
    return EnqueueResult(
        public_id=public_id,
        celery_task_id=task_id,
        status=job.status,
    )
