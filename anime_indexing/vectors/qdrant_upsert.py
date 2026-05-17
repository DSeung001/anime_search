from __future__ import annotations

import logging
import uuid
from typing import Any

from django.conf import settings

from anime_indexing.constants import QDRANT_POINT_NAMESPACE_UUID

logger = logging.getLogger(__name__)


def qdrant_is_configured() -> bool:
    """``QDRANT_URL`` 이 있고 ``qdrant-client`` 를 import 할 수 있을 때만 True."""
    url = getattr(settings, "QDRANT_URL", "") or ""
    if not url:
        return False
    try:
        import qdrant_client  # noqa: F401
    except ImportError:
        return False
    return True


def build_frame_payload(
    *,
    anime_slug: str,
    job_public_id: uuid.UUID,
    frame_index: int,
    frame_file: str,
    episode: int | None,
    genre_slugs: list[str],
    timestamp_sec: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "anime_id": anime_slug,
        "job_public_id": str(job_public_id),
        "frame_index": int(frame_index),
        "frame_file": str(frame_file),
        "timestamp_sec": float(timestamp_sec),
    }
    if episode is not None:
        payload["episode"] = int(episode)
    if genre_slugs:
        payload["genre"] = list(genre_slugs)
    return payload


def frame_point_uuid(job_public_id: uuid.UUID, frame_index: int) -> uuid.UUID:
    return uuid.uuid5(QDRANT_POINT_NAMESPACE_UUID, f"{job_public_id}:{frame_index}")


def _get_client():
    url = getattr(settings, "QDRANT_URL", "") or ""
    if not url:
        return None, None
    try:
        from qdrant_client import QdrantClient  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("QDRANT_URL이 설정됐지만 qdrant-client가 설치되지 않았습니다.")
        return None, None
    client = QdrantClient(url=url, api_key=settings.QDRANT_API_KEY or None)
    return client, settings.QDRANT_COLLECTION


def ensure_collection_and_indexes(*, vector_dim: int) -> None:
    """컬렉션 생성 및 필터용 payload 인덱스(멱등)."""
    pair = _get_client()
    if pair[0] is None:
        return
    client, collection = pair
    try:
        from qdrant_client.models import (  # type: ignore[import-untyped]
            Distance,
            PayloadSchemaType,
            VectorParams,
        )
    except ImportError:
        return

    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )

    for field_name, schema in (
        ("job_public_id", PayloadSchemaType.KEYWORD),
        ("anime_id", PayloadSchemaType.KEYWORD),
        ("episode", PayloadSchemaType.INTEGER),
        ("genre", PayloadSchemaType.KEYWORD),
        ("frame_index", PayloadSchemaType.INTEGER),
        ("frame_file", PayloadSchemaType.KEYWORD),
    ):
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=schema,
            )
        except Exception as exc:  # noqa: BLE001 — 이미 있으면 무시
            logger.debug("payload index %s: %s", field_name, exc)


def delete_points_for_job_public_id(job_public_id: uuid.UUID) -> None:
    pair = _get_client()
    if pair[0] is None:
        return
    client, collection = pair
    try:
        from qdrant_client.models import (  # type: ignore[import-untyped]
            FieldCondition,
            Filter,
            FilterSelector,
            MatchValue,
        )
    except ImportError:
        return

    flt = Filter(
        must=[
            FieldCondition(
                key="job_public_id",
                match=MatchValue(value=str(job_public_id)),
            )
        ]
    )
    try:
        if hasattr(client, "delete_points"):
            client.delete_points(
                collection_name=collection,
                points_selector=FilterSelector(filter=flt),
                wait=True,
            )
        else:
            client.delete(
                collection_name=collection,
                points_selector=FilterSelector(filter=flt),
                wait=True,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Qdrant delete(filter) 실패: %s", exc)


def upsert_job_frame_vectors(
    *,
    job_public_id: uuid.UUID,
    anime_slug: str,
    episode: int | None,
    genre_slugs: list[str],
    frame_indices: list[int],
    vectors: Any,
    timestamps: list[float],
    frame_files: list[str],
) -> None:
    """
    한 배치의 프레임 벡터를 Qdrant에 upsert.

    ``vectors``: ``(N, D)`` float32, 행마다 L2 정규화된 CLIP 임베딩.
    나머지 인자는 길이 ``N`` 의 동일 순서.
    """
    pair = _get_client()
    if pair[0] is None:
        return
    client, collection = pair
    try:
        from qdrant_client.models import PointStruct  # type: ignore[import-untyped]
    except ImportError:
        return

    n = len(frame_indices)
    if n == 0:
        return
    if len(timestamps) != n or len(frame_files) != n:
        raise ValueError("frame_indices, timestamps, frame_files 길이가 일치해야 합니다.")

    import numpy as np

    mat = np.asarray(vectors, dtype=np.float32)
    if mat.ndim != 2 or mat.shape[0] != n:
        raise ValueError(f"vectors 는 (N, D) 형태여야 합니다. N={n}, shape={mat.shape}")

    dim = int(mat.shape[1])
    ensure_collection_and_indexes(vector_dim=dim)

    points: list[Any] = []
    for i in range(n):
        fid = frame_indices[i]
        vec = mat[i]
        pid = frame_point_uuid(job_public_id, fid)
        payload = build_frame_payload(
            anime_slug=anime_slug,
            job_public_id=job_public_id,
            frame_index=fid,
            frame_file=frame_files[i],
            episode=episode,
            genre_slugs=genre_slugs,
            timestamp_sec=float(timestamps[i]),
        )
        points.append(
            PointStruct(
                id=str(pid),
                vector=vec.tolist(),
                payload=payload,
            )
        )

    client.upsert(collection_name=collection, points=points, wait=True)
