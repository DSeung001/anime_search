from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from anime_indexing.paths import (
    anime_staging_root,
    staging_frames_leaf,
    staging_input_dir_for_job_frames,
)
from anime_indexing.video.extract import VIDEO_EXTENSIONS

from catalog.models import Anime, Genre
from catalog.services.episode import get_or_create_episode
from catalog.services.youtube_import import normalize_youtube_url
from catalog.tasks import import_youtube_video_task
from catalog.services.genre_bulk import bulk_create_genres
from catalog.services.genre_slug import unique_genre_slug
from catalog.services.label_ko import parse_label_ko_bulk
from embeddings.models import EmbeddingJob
from embeddings.services.job_delete import JobDeleteError, delete_embedding_job
from embeddings.services.job_auto_enqueue import schedule_auto_enqueue_on_commit
from embeddings.services.job_dispatch import JobDispatchError, enqueue_run_job
from embeddings.services.job_staging import ensure_job_staging_dirs
from embeddings.validation import is_valid_anime_id

_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".m4v": "video/mp4",
}


def _ui_ok(request: HttpRequest) -> bool:
    if settings.DEBUG:
        return True
    return request.user.is_authenticated and request.user.is_staff


def _ui_gate(request: HttpRequest) -> HttpResponse | None:
    if _ui_ok(request):
        return None
    return redirect_to_login(next=request.get_full_path())


def _wants_json(request: HttpRequest) -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept


def _safe_video_name(name: str) -> str:
    base = Path(name).name
    if not base or Path(base).suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"지원하는 동영상 확장자만 가능합니다: {', '.join(sorted(VIDEO_EXTENSIONS))}")
    return base


def _video_preview_url(request: HttpRequest, job: EmbeddingJob, filename: str) -> str:
    return request.build_absolute_uri(
        reverse(
            "catalog_job_video_preview",
            kwargs={"public_id": job.public_id, "filename": filename},
        )
    )


def _upload_form_error(request: HttpRequest, msg: str, *, status: int = 400) -> HttpResponse:
    if _wants_json(request):
        return JsonResponse({"detail": msg}, status=status)
    messages.error(request, msg)
    return redirect("catalog_anime_upload")


def _upload_job_message(job: EmbeddingJob, *, dest_name: str | None, had_youtube: bool) -> str:
    if had_youtube:
        return f"작업 생성됨 · {job.public_id} · YouTube에서 가져오는 중…"
    if dest_name:
        return f"작업 생성됨 · {job.public_id} · 동영상 저장됨 · 처리 큐에 넣는 중"
    return (
        f"작업 생성됨 · {job.public_id} · input 폴더에 동영상을 넣은 뒤 "
        f"/jobs/ 에서 실행하세요"
    )


def _upload_json_response(
    request: HttpRequest,
    job: EmbeddingJob,
    *,
    dest_name: str | None,
    had_youtube: bool,
) -> JsonResponse:
    return JsonResponse(
        {
            "public_id": str(job.public_id),
            "status": job.status,
            "filename": dest_name,
            "preview_url": _video_preview_url(request, job, dest_name) if dest_name else None,
            "jobs_url": request.build_absolute_uri(reverse("catalog_jobs")),
            "poll_url": request.build_absolute_uri(
                reverse("catalog_job_api_detail", kwargs={"public_id": job.public_id})
            ),
            "youtube_source_url": job.youtube_source_url or None,
            "message": _upload_job_message(job, dest_name=dest_name, had_youtube=had_youtube),
        }
    )


@require_GET
def genre_list(request: HttpRequest) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate
    genres = list(Genre.objects.order_by("sort_order", "slug"))
    return render(request, "catalog/genre_list.html", {"genres": genres})


@require_http_methods(["GET", "POST"])
def genre_new(request: HttpRequest) -> HttpResponse:
    return _genre_form(request, None)


@require_http_methods(["GET", "POST"])
def genre_edit(request: HttpRequest, pk: int) -> HttpResponse:
    return _genre_form(request, pk)


@require_http_methods(["POST"])
def genre_bulk_new(request: HttpRequest) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate
    raw = request.POST.get("labels_bulk") or ""
    try:
        sort_order = int((request.POST.get("sort_order") or "0").strip() or "0")
    except ValueError:
        sort_order = 0
    labels = parse_label_ko_bulk(raw)
    if not labels:
        messages.error(request, "등록할 표시명을 입력하세요 (쉼표 또는 줄바꿈으로 구분).")
        return redirect("catalog_genre_list")

    created, skipped = bulk_create_genres(labels, sort_order=sort_order)
    if created:
        names = ", ".join(g.label_ko for g in created[:12])
        extra = f" 외 {len(created) - 12}건" if len(created) > 12 else ""
        messages.success(request, f"{len(created)}건 등록: {names}{extra}")
    if skipped:
        preview = "; ".join(skipped[:8])
        extra = f" …외 {len(skipped) - 8}건" if len(skipped) > 8 else ""
        messages.warning(request, f"{len(skipped)}건 스킵: {preview}{extra}")
    if not created and not skipped:
        messages.error(request, "처리할 항목이 없습니다.")
    return redirect("catalog_genre_list")


def _genre_form(request: HttpRequest, pk: int | None) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate
    if pk is None:
        genre = None
    else:
        genre = get_object_or_404(Genre, pk=pk)

    if request.method == "POST":
        label_ko = (request.POST.get("label_ko") or "").strip()
        try:
            so = int((request.POST.get("sort_order") or "0").strip() or "0")
        except ValueError:
            so = 0
        if not label_ko:
            messages.error(request, "표시명(label_ko)은 필수입니다.")
            return redirect(request.path)
        try:
            if genre is None:
                slug = unique_genre_slug(label_ko)
                g = Genre(slug=slug, label_ko=label_ko, sort_order=so)
                g.save()
                messages.success(request, f"장르를 추가했습니다. (slug: {slug})")
            else:
                genre.label_ko = label_ko
                genre.sort_order = so
                genre.save()
                messages.success(request, "저장했습니다.")
        except ValidationError:
            messages.error(request, "이미 등록된 한글 표시명입니다.")
            return redirect(request.path)
        except IntegrityError:
            messages.error(request, "이미 등록된 한글 표시명입니다.")
            return redirect(request.path)
        return redirect("catalog_genre_list")

    return render(request, "catalog/genre_form.html", {"genre": genre})


@require_GET
def serve_uploaded_video(request: HttpRequest, public_id: UUID, filename: str) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name:
        return JsonResponse({"detail": "invalid filename"}, status=400)
    try:
        _safe_video_name(safe_name)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    job = get_object_or_404(EmbeddingJob, public_id=public_id)
    frames_leaf = staging_frames_leaf(job.staging_rel_path)
    input_dir = staging_input_dir_for_job_frames(frames_leaf)
    video_path = (input_dir / safe_name).resolve()
    staging_root = anime_staging_root().resolve()
    try:
        video_path.relative_to(staging_root)
    except ValueError:
        return JsonResponse({"detail": "forbidden"}, status=403)
    if not video_path.is_file():
        return JsonResponse({"detail": "not found"}, status=404)

    suffix = video_path.suffix.lower()
    content_type = _VIDEO_MIME.get(suffix) or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return FileResponse(video_path.open("rb"), content_type=content_type, as_attachment=False)


@require_http_methods(["GET", "POST"])
def anime_upload(request: HttpRequest) -> HttpResponse:
    # 로그인 필요 여부 체크, 개발 단계에서는 체크 안함
    gate = _ui_gate(request)
    if gate:
        return gate

    # 애니메이션 시리즈 구분하기 위한 리스트 가져오기
    animes = list(Anime.objects.order_by("slug"))
    # 장르 리스트 가져오기
    genres = list(Genre.objects.order_by("sort_order", "slug"))

    # 업로드
    if request.method == "POST":
        slug = (request.POST.get("anime_slug") or "").strip()
        # slug 유효성 검사
        if not is_valid_anime_id(slug):
            return _upload_form_error(
                request, "시리즈 slug는 영문·숫자·_- 만 1~255자여야 합니다."
            )

        # 애니메이션이 없으면 새로 만들고 있으면 그대로 사용
        title = (request.POST.get("title") or "").strip()
        anime, _ = Anime.objects.get_or_create(slug=slug, defaults={"title": title})
        # title은 선택(없으면 slug만으로 생성)
        if title:
            anime.title = title
            anime.save(update_fields=["title", "updated_at"])

        # 장르 데이터를 n:m 연결
        ids = [int(x) for x in request.POST.getlist("genre_ids") if x.isdigit()]
        anime.genres.set(Genre.objects.filter(pk__in=ids))

        # 에피소드 유효성 검사
        ep_raw = (request.POST.get("episode") or "").strip()
        if not ep_raw:
            return _upload_form_error(request, "episode(화수)는 필수입니다.")
        try:
            episode_number = int(ep_raw)
            if episode_number < 1:
                raise ValueError
        except ValueError:
            return _upload_form_error(request, "episode는 1 이상 정수여야 합니다.")

        youtube_url = (request.POST.get("youtube_url") or "").strip()
        f = request.FILES.get("video")
        if youtube_url and f:
            return _upload_form_error(
                request, "동영상 파일과 YouTube URL 중 하나만 지정하세요."
            )

        if youtube_url:
            try:
                youtube_url = normalize_youtube_url(youtube_url)
            except ValueError as exc:
                return _upload_form_error(request, str(exc))

        episode_row = get_or_create_episode(anime=anime, number=episode_number)
        job = EmbeddingJob.objects.create(
            anime=anime,
            episode=episode_row,
            status=(
                EmbeddingJob.Status.IMPORTING
                if youtube_url
                else EmbeddingJob.Status.PENDING
            ),
            youtube_source_url=youtube_url,
        )
        # 잡 스테이징 디렉터리(jobs/<id>/frames, input/) 생성
        frames_leaf = ensure_job_staging_dirs(job)
        input_dir = staging_input_dir_for_job_frames(frames_leaf)

        dest_name: str | None = None
        if youtube_url:
            async_result = import_youtube_video_task.delay(str(job.public_id), youtube_url)
            job.celery_task_id = str(async_result.id)
            job.save(update_fields=["celery_task_id", "updated_at"])
        elif f:
            try:
                dest_name = _safe_video_name(f.name)
            except ValueError as exc:
                job.delete()
                return _upload_form_error(request, str(exc))
            # pathlib로 경로 조합(문자열 split/join 대신)
            dest = input_dir / dest_name
            with dest.open("wb") as out:
                # Django의 chunks()로 스트리밍 저장(기본 청크 64KB)
                for chunk in f.chunks():
                    out.write(chunk)
                job.source_video_filename = dest_name
                job.save(update_fields=["source_video_filename", "updated_at"])

            # TODO: DB·파일 저장을 transaction.atomic() 등으로 묶기
            schedule_auto_enqueue_on_commit(job.public_id)

        if _wants_json(request):
            return _upload_json_response(
                request,
                job,
                dest_name=dest_name,
                had_youtube=bool(youtube_url),
            )

        messages.success(
            request,
            _upload_job_message(job, dest_name=dest_name, had_youtube=bool(youtube_url)),
        )
        return redirect("catalog_jobs")

    # 업로드 페이지 보여주기
    return render(
        request,
        "catalog/anime_upload.html",
        {"animes": animes, "genres": genres},
    )


def _job_status_payload(
    job: EmbeddingJob,
    *,
    request: HttpRequest | None = None,
) -> dict[str, str | int | None]:
    filename = job.source_video_filename or None
    preview_url: str | None = None
    if filename and request is not None:
        preview_url = _video_preview_url(request, job, filename)
    return {
        "public_id": str(job.public_id),
        "anime_id": job.anime.slug,
        "status": job.status,
        "status_display": job.get_status_display(),
        "last_error": job.last_error or "",
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "processed_at": job.processed_at.isoformat() if job.processed_at else None,
        "episode": job.episode.number,
        "episode_id": job.episode_id,
        "celery_task_id": job.celery_task_id or "",
        "source_video_filename": filename,
        "youtube_source_url": job.youtube_source_url or None,
        "preview_url": preview_url,
    }


@require_GET
def job_api_list(request: HttpRequest) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate
    jobs = EmbeddingJob.objects.select_related("anime", "episode").order_by("-created_at")[:80]
    return JsonResponse({"jobs": [_job_status_payload(j, request=request) for j in jobs]})


@require_GET
def job_api_detail(request: HttpRequest, public_id: UUID) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate
    job = get_object_or_404(
        EmbeddingJob.objects.select_related("anime", "episode"),
        public_id=public_id,
    )
    return JsonResponse(_job_status_payload(job, request=request))


@require_POST
def job_api_delete(request: HttpRequest, public_id: UUID) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate
    try:
        delete_embedding_job(public_id=public_id)
    except JobDeleteError as exc:
        return JsonResponse({"detail": str(exc)}, status=exc.status_code)
    return JsonResponse({"deleted": True, "public_id": str(public_id)})


@require_POST
def job_api_run(request: HttpRequest, public_id: UUID) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate
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


@require_http_methods(["GET", "POST"])
def job_console(request: HttpRequest) -> HttpResponse:
    gate = _ui_gate(request)
    if gate:
        return gate

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "requeue":
            raw = (request.POST.get("job_public_id") or "").strip()
            try:
                uid = UUID(raw)
            except ValueError:
                messages.error(request, "UUID 형식이 아닙니다.")
                return redirect("catalog_jobs")
            job = EmbeddingJob.objects.filter(public_id=uid).first()
            if job is None:
                messages.error(request, "작업을 찾을 수 없습니다.")
                return redirect("catalog_jobs")
            if job.status == EmbeddingJob.Status.PROCESSING:
                messages.error(request, "processing 은 재큐할 수 없습니다.")
                return redirect("catalog_jobs")
            if job.status == EmbeddingJob.Status.PENDING:
                messages.info(request, "이미 pending 입니다.")
                return redirect("catalog_jobs")
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
            messages.success(request, "다시 대기열에 넣었습니다. 처리 큐에 넣는 중입니다.")
            return redirect("catalog_jobs")

    jobs = list(EmbeddingJob.objects.select_related("anime", "episode").order_by("-created_at")[:80])
    return render(request, "catalog/job_console.html", {"jobs": jobs})
