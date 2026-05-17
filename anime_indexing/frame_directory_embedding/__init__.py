"""한 디렉터리의 프레임 JPG에 대해 CLIP 벡터를 뽑는 API (DB 작업 행과 무관)."""

from .runtime import (
    EmbeddingRunResult,
    embedding_result_as_json,
    get_vision_worker,
    run_frame_directory_embedding,
)

__all__ = [
    "EmbeddingRunResult",
    "embedding_result_as_json",
    "get_vision_worker",
    "run_frame_directory_embedding",
]
