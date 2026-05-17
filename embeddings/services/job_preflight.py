from __future__ import annotations

from anime_indexing.paths import staging_frames_leaf, staging_input_dir_for_job_frames
from anime_indexing.video.extract import find_first_video

from embeddings.models import EmbeddingJob
from embeddings.services.job_staging import (
    ensure_job_staging_dirs,
    seed_staging_frames_from_canonical,
)


def check_job_staging_ready(job: EmbeddingJob) -> str | None:
    """
    잡 실행 전 스테이징 준비 여부.
    None 이면 OK, 아니면 사용자에게 보여줄 오류 메시지.
    """
    ensure_job_staging_dirs(job)
    seed_staging_frames_from_canonical(job)
    frames_leaf = staging_frames_leaf(job.staging_rel_path)

    if any(frames_leaf.glob("*.jpg")):
        return None

    input_dir = staging_input_dir_for_job_frames(frames_leaf)
    if input_dir.is_dir() and find_first_video(input_dir) is not None:
        return None

    return (
        f"스테이징에 JPG 또는 input/ 동영상이 필요합니다: {frames_leaf}. "
        f"동영상은 …/jobs/{job.public_id}/input/ 에 넣거나 업로드 UI를 사용하세요."
    )
