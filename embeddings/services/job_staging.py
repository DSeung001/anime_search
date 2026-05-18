from __future__ import annotations

from pathlib import Path
from uuid import UUID

from anime_indexing.paths import (
    ensure_dir,
    staging_frames_leaf,
    staging_input_dir_for_job_frames,
)

from embeddings.models import EmbeddingJob


def expected_staging_rel_path(public_id: UUID | str) -> str:
    return f"jobs/{public_id}/frames"


def ensure_job_staging_dirs(job: EmbeddingJob) -> Path:
    """
    ``jobs/<public_id>/frames`` 및 ``input/`` 를 만든다.
    DB ``staging_rel_path`` 가 UUID 와 어긋나면 교정한다.
    """
    expected = expected_staging_rel_path(job.public_id)
    if job.staging_rel_path != expected:
        job.staging_rel_path = expected
        EmbeddingJob.objects.filter(pk=job.pk).update(staging_rel_path=expected)
    frames_leaf = staging_frames_leaf(job.staging_rel_path)
    ensure_dir(frames_leaf)
    ensure_dir(staging_input_dir_for_job_frames(frames_leaf))
    return frames_leaf
