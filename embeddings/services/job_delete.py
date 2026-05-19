from __future__ import annotations

import shutil
from uuid import UUID

from anime_indexing.paths import anime_staging_root
from anime_indexing.vectors.qdrant_upsert import delete_points_for_job_public_id

from django.conf import settings

from embeddings.models import EmbeddingJob


class JobDeleteError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _remove_staging_job_root(public_id: UUID) -> None:
    job_root = anime_staging_root() / "jobs" / str(public_id)
    if job_root.is_dir():
        shutil.rmtree(job_root, ignore_errors=True)


def delete_embedding_job(*, public_id: UUID) -> None:
    job = EmbeddingJob.objects.filter(public_id=public_id).first()
    if job is None:
        raise JobDeleteError("작업을 찾을 수 없습니다.", status_code=404)
    if (
        job.status == EmbeddingJob.Status.DONE
        and getattr(settings, "DISCOVERY_PROTECT_DONE_JOBS", True)
    ):
        raise JobDeleteError(
            "완료(DONE) 잡은 공개 검색 미디어용으로 삭제할 수 없습니다.",
            status_code=409,
        )
    if job.status == EmbeddingJob.Status.PROCESSING:
        raise JobDeleteError("처리 중인 작업은 삭제할 수 없습니다.", status_code=409)

    delete_points_for_job_public_id(public_id)
    _remove_staging_job_root(public_id)
    job.delete()
