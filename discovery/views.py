from __future__ import annotations

import json
import mimetypes
from pathlib import Path as FsPath
from typing import Any
from uuid import UUID

from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from anime_indexing.paths import anime_staging_root, staging_frames_leaf, staging_input_dir_for_job_frames
from anime_indexing.video.extract import VIDEO_EXTENSIONS
from catalog.views import _safe_video_name, _VIDEO_MIME
from discovery.models import ChatSession
from discovery.services.chat_orchestrator import (
    ChatOrchestratorError,
    ChatSessionNotFoundError,
    get_or_create_session,
    run_chat_turn,
)
from discovery.services.chat_history import (
    get_session_messages,
    list_recent_sessions,
    sessions_for_template,
)
from discovery.services.rate_limit import RateLimitExceeded, check_rate_limit
from embeddings.models import EmbeddingJob


def _json_body(request: HttpRequest) -> dict[str, Any]:
    return json.loads(request.body.decode("utf-8") or "{}")


def _parse_limit(request: HttpRequest, default: int = 50) -> int:
    try:
        return int(request.GET.get("limit", default))
    except (TypeError, ValueError):
        return default


@require_GET
def chat_home(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "discovery/chat_list.html",
        {"sessions": sessions_for_template(limit=_parse_limit(request))},
    )


@require_GET
def search_page(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "discovery/search_chat.html",
        {"session_id": "", "chat_back_url": "/"},
    )


@require_GET
def chat_session_page(request: HttpRequest, session_id: UUID) -> HttpResponse:
    get_object_or_404(ChatSession, id=session_id)
    return render(
        request,
        "discovery/search_chat.html",
        {
            "session_id": str(session_id),
            "chat_back_url": "/",
        },
    )


@require_GET
def sessions_api(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"sessions": list_recent_sessions(limit=_parse_limit(request))})


@require_GET
def session_messages_api(request: HttpRequest, session_id: UUID) -> JsonResponse:
    try:
        payload = get_session_messages(session_id)
    except ChatSessionNotFoundError:
        return JsonResponse({"detail": "session not found"}, status=404)
    return JsonResponse(payload)


@csrf_exempt
@require_POST
def chat_api(request: HttpRequest) -> JsonResponse:
    try:
        check_rate_limit(request)
    except RateLimitExceeded as exc:
        return JsonResponse({"detail": str(exc)}, status=429)

    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "invalid json"}, status=400)

    message = (body.get("message") or "").strip()
    if not message:
        return JsonResponse({"detail": "message is required"}, status=400)

    session_id_raw = (body.get("session_id") or "").strip()
    session_uuid: UUID | None = None
    if session_id_raw:
        try:
            session_uuid = UUID(session_id_raw)
        except ValueError:
            return JsonResponse({"detail": "invalid session_id"}, status=400)

    try:
        session = get_or_create_session(session_uuid)
    except ChatSessionNotFoundError:
        return JsonResponse({"detail": "session not found"}, status=404)

    try:
        reply, scenes = run_chat_turn(session=session, user_message=message, request=request)
    except ChatOrchestratorError as exc:
        return JsonResponse({"detail": str(exc)}, status=503)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"detail": str(exc)}, status=500)

    return JsonResponse(
        {
            "session_id": str(session.id),
            "reply": reply,
            "scenes": scenes,
        }
    )


def _done_job(job_id: UUID) -> EmbeddingJob:
    return get_object_or_404(EmbeddingJob, public_id=job_id, status=EmbeddingJob.Status.DONE)


@require_GET
def serve_thumb(request: HttpRequest, job_id: UUID, frame_file: str) -> HttpResponse:
    job = _done_job(job_id)
    safe = FsPath(frame_file).name
    if safe != frame_file or not safe.lower().endswith(".jpg"):
        return JsonResponse({"detail": "invalid frame"}, status=400)
    frames = staging_frames_leaf(job.staging_rel_path)
    path = (frames / safe).resolve()
    root = anime_staging_root().resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return JsonResponse({"detail": "forbidden"}, status=403)
    if not path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)
    return FileResponse(path.open("rb"), content_type="image/jpeg")


@require_GET
def serve_video(request: HttpRequest, job_id: UUID, filename: str) -> HttpResponse:
    job = _done_job(job_id)
    try:
        safe = _safe_video_name(filename)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    frames = staging_frames_leaf(job.staging_rel_path)
    video_path = (staging_input_dir_for_job_frames(frames) / safe).resolve()
    root = anime_staging_root().resolve()
    try:
        video_path.relative_to(root)
    except ValueError:
        return JsonResponse({"detail": "forbidden"}, status=403)
    if not video_path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)

    suffix = video_path.suffix.lower()
    content_type = _VIDEO_MIME.get(suffix) or mimetypes.guess_type(safe)[0] or "application/octet-stream"
    return FileResponse(video_path.open("rb"), content_type=content_type, as_attachment=False)
