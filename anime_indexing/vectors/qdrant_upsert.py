from __future__ import annotations

import logging
import uuid
from typing import Any

from anime_indexing.constants import QDRANT_POINT_NAMESPACE_UUID
from anime_indexing.vectors.qdrant_client import (
    get_qdrant_client_and_collection,
    qdrant_is_configured,
)

logger = logging.getLogger(__name__)

__all__ = ["qdrant_is_configured"]


def build_frame_payload(
    *,
    anime_slug: str,
    job_public_id: uuid.UUID,
    frame_index: int,
    frame_file: str,
    episode: int | None,
    episode_id: int | None,
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
    if episode_id is not None:
        payload["episode_id"] = int(episode_id)
    if genre_slugs:
        payload["genre"] = list(genre_slugs)
    return payload


def frame_point_uuid(job_public_id: uuid.UUID, frame_index: int) -> uuid.UUID:
    return uuid.uuid5(QDRANT_POINT_NAMESPACE_UUID, f"{job_public_id}:{frame_index}")


def ensure_collection_and_indexes(*, vector_dim: int) -> None:
    """컬렉션 생성 및 필터용 payload 인덱스(멱등)."""
    client, collection = get_qdrant_client_and_collection()
    if client is None or collection is None:
        return
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
        ("episode_id", PayloadSchemaType.INTEGER),
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
    client, collection = get_qdrant_client_and_collection()
    if client is None or collection is None:
        return
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


def delete_points_for_anime_episode(*, anime_slug: str, episode_number: int) -> None:
    """해당 시리즈·화의 모든 벡터 삭제 (재임베딩 전)."""
    client, collection = get_qdrant_client_and_collection()
    if client is None or collection is None:
        return
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
            FieldCondition(key="anime_id", match=MatchValue(value=anime_slug)),
            FieldCondition(key="episode", match=MatchValue(value=int(episode_number))),
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
        logger.warning("Qdrant delete(anime, episode) 실패: %s", exc)


def upsert_job_frame_vectors(
    *,
    job_public_id: uuid.UUID,
    anime_slug: str,
    episode: int | None,
    episode_id: int | None = None,
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
    client, collection = get_qdrant_client_and_collection()
    if client is None or collection is None:
        return
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
            episode_id=episode_id,
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
