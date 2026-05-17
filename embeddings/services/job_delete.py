from __future__ import annotations

import shutil
from uuid import UUID

from anime_indexing.paths import anime_staging_root, frames_leaf_under_media
from anime_indexing.vectors.qdrant_upsert import delete_points_for_job_public_id
from anime_indexing.video.pts_manifest import MANIFEST_FILENAME

from embeddings.models import EmbeddingJob


class JobDeleteError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _remove_staging_job_root(public_id: UUID) -> None:
    job_root = anime_staging_root() / "jobs" / str(public_id)
    if job_root.is_dir():
        shutil.rmtree(job_root, ignore_errors=True)


def _should_remove_canonical_frames(job: EmbeddingJob) -> bool:
    if job.status != EmbeddingJob.Status.DONE:
        return False
    if job.processed_at is None:
        return True
    newer = (
        EmbeddingJob.objects.filter(
            anime_id=job.anime_id,
            status=EmbeddingJob.Status.DONE,
        )
        .exclude(pk=job.pk)
        .filter(processed_at__gt=job.processed_at)
        .exists()
    )
    return not newer


def _remove_canonical_frames(anime_slug: str) -> None:
    leaf = frames_leaf_under_media(anime_slug)
    if not leaf.is_dir():
        return
    for p in leaf.glob("*.jpg"):
        p.unlink(missing_ok=True)
    manifest = leaf / MANIFEST_FILENAME
    if manifest.is_file():
        manifest.unlink(missing_ok=True)
    try:
        leaf.rmdir()
    except OSError:
        pass


def delete_embedding_job(*, public_id: UUID) -> None:
    job = EmbeddingJob.objects.select_related("anime").filter(public_id=public_id).first()
    if job is None:
        raise JobDeleteError("작업을 찾을 수 없습니다.", status_code=404)
    if job.status == EmbeddingJob.Status.PROCESSING:
        raise JobDeleteError("처리 중인 작업은 삭제할 수 없습니다.", status_code=409)

    delete_points_for_job_public_id(public_id)
    _remove_staging_job_root(public_id)

    if _should_remove_canonical_frames(job):
        _remove_canonical_frames(job.anime.slug)

    job.delete()
