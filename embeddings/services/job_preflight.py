from __future__ import annotations

from anime_indexing.paths import staging_frames_leaf, staging_input_dir_for_job_frames
from anime_indexing.video.extract import find_first_video

from embeddings.models import EmbeddingJob
from embeddings.services.job_staging import ensure_job_staging_dirs


def check_job_input_video(job: EmbeddingJob) -> str | None:
    """
    enqueue·워커 실행 전: ``input/`` 에 실행 가능한 동영상이 있는지.
    프레임 JPG는 워커가 ffmpeg 추출 후 사용한다.
    None 이면 OK, 아니면 사용자에게 보여줄 오류 메시지.
    """
    ensure_job_staging_dirs(job)
    frames_leaf = staging_frames_leaf(job.staging_rel_path)
    input_dir = staging_input_dir_for_job_frames(frames_leaf)
    if input_dir.is_dir() and find_first_video(input_dir) is not None:
        return None

    return (
        f"input/ 에 동영상이 필요합니다: {input_dir}. "
        f"…/jobs/{job.public_id}/input/ 에 넣거나 업로드 UI를 사용하세요."
    )
