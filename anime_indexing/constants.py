from __future__ import annotations

import uuid
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
CLIP_WEIGHTS_DIR = PACKAGE_ROOT / "weights"
DEFAULT_CLIP_CHECKPOINT_PATH = CLIP_WEIGHTS_DIR / "ViT-L-14.pt"
DEFAULT_CLIP_MODEL_NAME = "ViT-L/14"

# Qdrant point id = uuid5(QDRANT_POINT_NAMESPACE_UUID, f"{job_public_id}:{frame_index}")
QDRANT_POINT_NAMESPACE_UUID = uuid.UUID("350706ec-0bbd-5a46-ad2c-957100febcdf")
