"""Django ``EmbeddingJob`` 행 기준: 스테이징 추출·승격·CLIP·Qdrant 한 사이클."""

from .workflow import (
    maybe_extract_video_for_job,
    promote_jpgs_from_staging_to_media,
    run_single_embedding_job,
)

__all__ = [
    "maybe_extract_video_for_job",
    "promote_jpgs_from_staging_to_media",
    "run_single_embedding_job",
]
