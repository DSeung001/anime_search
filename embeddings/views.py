from __future__ import annotations

"""
임베딩 JSON API (csrf_exempt + X-Internal-Key 또는 DEBUG).
"""

import json
from typing import Any
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from anime_indexing.frame_directory_embedding import (
    embedding_result_as_json,
    run_frame_directory_embedding,
)
from anime_indexing.paths import (
    resolve_staging_frames_dir,
    staging_frames_leaf,
    staging_input_dir_for_job_frames,
)
from catalog.models import Anime, Genre
from embeddings.api_reference import path_help_payload
from catalog.services.episode import get_or_create_episode
from embeddings.job_fields import required_episode_number_from_json
from embeddings.models import EmbeddingJob
from embeddings.services.job_auto_enqueue import schedule_auto_enqueue_on_commit
from embeddings.services.job_dispatch import JobDispatchError, enqueue_run_job
from embeddings.services.job_staging import ensure_job_staging_dirs
from embeddings.validation import is_valid_anime_id


def _embed_allowed(request: HttpRequest) -> bool:
    if settings.DEBUG:
        return True
    key = getattr(settings, "EMBED_INTERNAL_KEY", "") or ""
    if not key:
        return False
    return request.headers.get("X-Internal-Key") == key


def _json_body(request: HttpRequest) -> dict[str, Any]:
    return json.loads(request.body.decode("utf-8") or "{}")


@csrf_exempt
@require_POST
def run_embed(request: HttpRequest) -> JsonResponse:
    """스테이징 루트 기준 leaf 디렉터리에 대해 동기 임베딩(개발·점검용)."""
    if not _embed_allowed(request):
        return JsonResponse({"detail": "forbidden"}, status=403)

    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "invalid json"}, status=400)

    rel = (body.get("relative_frames_dir") or "").strip()
    if not rel:
        return JsonResponse(
            {"detail": "relative_frames_dir is required"},
            status=400,
        )

    try:
        frames = resolve_staging_frames_dir(rel)
    except (ValueError, PermissionError) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    try:
        result = run_frame_directory_embedding(frames)
    except FileNotFoundError as exc:
        return JsonResponse({"detail": str(exc)}, status=404)

    return JsonResponse(embedding_result_as_json(result))


@csrf_exempt
@require_POST
def create_embedding_job(request: HttpRequest) -> JsonResponse:
    """작업 행 pending + 스테이징 디렉터리. ``anime_id`` 는 ``catalog.Anime`` 슬러그."""
    if not _embed_allowed(request):
        return JsonResponse({"detail": "forbidden"}, status=403)

    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "invalid json"}, status=400)

    slug = (body.get("anime_id") or "").strip()
    if not is_valid_anime_id(slug):
        return JsonResponse(
            {"detail": "anime_id must match [a-zA-Z0-9_-]{1,255}"},
            status=400,
        )

    ep_num, err = required_episode_number_from_json(body)
    if err:
        return JsonResponse({"detail": err}, status=400)
    anime_title = (body.get("title") or "").strip() or slug
    anime, _ = Anime.objects.get_or_create(slug=slug, defaults={"title": anime_title})
    if anime.title != anime_title:
        anime.title = anime_title
        anime.save(update_fields=["title", "updated_at"])

    raw_genres = body.get("genre_slugs")
    genre_slugs_body: list[str] = []
    if raw_genres is not None:
        if not isinstance(raw_genres, list):
            return JsonResponse({"detail": "genre_slugs must be a JSON array of strings"}, status=400)
        genre_slugs_body = [str(x).strip() for x in raw_genres if str(x).strip()]
    if genre_slugs_body:
        bad = [s for s in genre_slugs_body if not is_valid_anime_id(s)]
        if bad:
            return JsonResponse(
                {"detail": f"invalid genre slug(s): {bad[:8]}"},
                status=400,
            )
        genres = [
            Genre.objects.get_or_create(slug=s, defaults={"label_ko": s, "sort_order": 0})[0]
            for s in genre_slugs_body
        ]
        anime.genres.set(genres)

    ep_title = (body.get("episode_title") or "").strip() or f"{ep_num}화"
    episode_row = get_or_create_episode(anime=anime, number=ep_num, title=ep_title)
    job = EmbeddingJob.objects.create(anime=anime, episode=episode_row)
    staging_leaf = ensure_job_staging_dirs(job)
    schedule_auto_enqueue_on_commit(job.public_id)

    genre_slugs = list(anime.genres.order_by("slug").values_list("slug", flat=True))
    payload: dict[str, Any] = {
        "public_id": str(job.public_id),
        "anime_id": anime.slug,
        "canonical_key": job.canonical_key,
        "staging_rel_path": job.staging_rel_path,
        "status": job.status,
        "episode": job.episode.number,
        "episode_id": job.episode_id,
        "genres": genre_slugs,
    }
    if settings.DEBUG:
        payload["staging_absolute"] = str(staging_leaf)
        payload["staging_input_absolute"] = str(staging_input_dir_for_job_frames(staging_leaf))
        payload["s3_logical_prefix"] = (settings.S3_MEDIA_PREFIX + job.canonical_key).lstrip("/")
    return JsonResponse(payload, status=201)


@csrf_exempt
@require_GET
def get_embedding_job(request: HttpRequest, public_id: UUID) -> JsonResponse:
    if not _embed_allowed(request):
        return JsonResponse({"detail": "forbidden"}, status=403)

    job = get_object_or_404(
        EmbeddingJob.objects.select_related("anime", "episode"),
        public_id=public_id,
    )
    genre_slugs = list(job.anime.genres.order_by("slug").values_list("slug", flat=True))
    return JsonResponse(
        {
            "public_id": str(job.public_id),
            "anime_id": job.anime.slug,
            "canonical_key": job.canonical_key,
            "staging_rel_path": job.staging_rel_path,
            "status": job.status,
            "last_error": job.last_error,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "processed_at": job.processed_at.isoformat() if job.processed_at else None,
            "episode": job.episode.number,
            "episode_id": job.episode_id,
            "genres": genre_slugs,
            "celery_task_id": job.celery_task_id or "",
        }
    )


@csrf_exempt
@require_POST
def requeue_embedding_job(request: HttpRequest, public_id: UUID) -> JsonResponse:
    """done/failed → pending."""
    if not _embed_allowed(request):
        return JsonResponse({"detail": "forbidden"}, status=403)

    job = get_object_or_404(EmbeddingJob, public_id=public_id)
    if job.status == EmbeddingJob.Status.PROCESSING:
        return JsonResponse({"detail": "processing 상태는 재큐할 수 없습니다."}, status=409)
    if job.status == EmbeddingJob.Status.PENDING:
        return JsonResponse({"detail": "already pending", "public_id": str(job.public_id)}, status=200)

    if job.status not in (EmbeddingJob.Status.DONE, EmbeddingJob.Status.FAILED):
        return JsonResponse({"detail": "unsupported status"}, status=400)

    job.status = EmbeddingJob.Status.PENDING
    job.last_error = ""
    job.processed_at = None
    job.celery_task_id = ""
    job.save(
        update_fields=[
            "status",
            "last_error",
            "processed_at",
            "celery_task_id",
            "updated_at",
        ]
    )
    ensure_job_staging_dirs(job)
    schedule_auto_enqueue_on_commit(job.public_id)
    return JsonResponse({"public_id": str(job.public_id), "status": job.status})


@csrf_exempt
@require_POST
def run_embedding_job_by_id(request: HttpRequest, public_id: UUID) -> JsonResponse:
    """pending 잡 한 건을 Celery 큐에 넣는다."""
    if not _embed_allowed(request):
        return JsonResponse({"detail": "forbidden"}, status=403)

    try:
        result = enqueue_run_job(public_id)
    except JobDispatchError as exc:
        return JsonResponse({"detail": str(exc)}, status=exc.status_code)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"detail": str(exc)}, status=503)
    return JsonResponse(
        {
            "enqueued": True,
            "public_id": result.public_id,
            "celery_task_id": result.celery_task_id,
            "status": result.status,
        },
        status=202,
    )


@csrf_exempt
@require_http_methods(["GET"])
def embed_path_help(request: HttpRequest) -> JsonResponse:
    if not _embed_allowed(request):
        return JsonResponse({"detail": "forbidden"}, status=403)
    return JsonResponse(path_help_payload(request))
