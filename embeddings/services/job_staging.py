from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from anime_indexing.paths import (
    ensure_dir,
    frames_leaf_under_media,
    staging_frames_leaf,
    staging_input_dir_for_job_frames,
)
from anime_indexing.video.pts_manifest import MANIFEST_FILENAME

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


def seed_staging_frames_from_canonical(job: EmbeddingJob) -> bool:
    """
    처리 완료 후 스테이징이 삭제된 잡 재실행용.
    캐논 ``{slug}/frames/*.jpg`` 가 있으면 스테이징 ``frames/`` 로 복사한다.
    """
    frames_leaf = staging_frames_leaf(job.staging_rel_path)
    if any(frames_leaf.glob("*.jpg")):
        return True

    media_leaf = frames_leaf_under_media(job.anime.slug)
    if not media_leaf.is_dir():
        return False

    jpgs = sorted(media_leaf.glob("*.jpg"))
    if not jpgs:
        return False

    ensure_dir(frames_leaf)
    for src in jpgs:
        shutil.copy2(src, frames_leaf / src.name)

    manifest = media_leaf / MANIFEST_FILENAME
    if manifest.is_file():
        shutil.copy2(manifest, frames_leaf / MANIFEST_FILENAME)
    return True
