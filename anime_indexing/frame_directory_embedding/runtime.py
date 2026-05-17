from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from django.conf import settings

if TYPE_CHECKING:
    import numpy as np

    from anime_indexing.clip.vision import VisionPipelineWorker

_worker_lock = threading.Lock()
_worker: Optional["VisionPipelineWorker"] = None


def get_vision_worker() -> "VisionPipelineWorker":
    global _worker
    from anime_indexing.clip.vision import VisionPipelineWorker

    with _worker_lock:
        if _worker is None:
            _worker = VisionPipelineWorker(
                model_name=settings.CLIP_MODEL_NAME,
                clip_checkpoint=settings.CLIP_CHECKPOINT,
            )
        return _worker


@dataclass(frozen=True)
class EmbeddingRunResult:
    resolved_frames_dir: str
    frame_count: int
    vector_dim: int
    elapsed_sec: float
    frames_per_sec: float


def run_frame_directory_embedding(frames_dir: Path | str) -> EmbeddingRunResult:
    import numpy as np

    path = Path(frames_dir).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"프레임 디렉터리가 없습니다: {path}")

    worker = get_vision_worker()
    matrix, elapsed, fps = worker.extract_features(
        str(path),
        batch_size=settings.ANIME_EMBED_BATCH_SIZE,
        num_workers=settings.ANIME_EMBED_NUM_WORKERS,
        verbose=False,
    )
    matrix_np: np.ndarray = np.asarray(matrix)
    rows = int(matrix_np.shape[0])
    dim = int(matrix_np.shape[1])

    return EmbeddingRunResult(
        resolved_frames_dir=str(path),
        frame_count=rows,
        vector_dim=dim,
        elapsed_sec=float(elapsed),
        frames_per_sec=float(fps),
    )


def embedding_result_as_json(result: EmbeddingRunResult) -> dict[str, Any]:
    return {
        "resolved_frames_dir": result.resolved_frames_dir,
        "frame_count": result.frame_count,
        "vector_dim": result.vector_dim,
        "elapsed_sec": result.elapsed_sec,
        "frames_per_sec": result.frames_per_sec,
    }
