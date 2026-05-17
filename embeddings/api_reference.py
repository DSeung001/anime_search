from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest

from anime_indexing.constants import CLIP_WEIGHTS_DIR, DEFAULT_CLIP_CHECKPOINT_PATH
from anime_indexing.paths import canonical_frames_key
from anime_indexing.video.ffmpeg_resolve import resolve_ffmpeg_exe


def effective_ffmpeg() -> str:
    """현재 설정 기준 ffmpeg 실행 경로. UI·JSON용이라 실패 시 문자열만 돌려준다."""
    try:
        return resolve_ffmpeg_exe(getattr(settings, "FFMPEG_BIN", "") or None)
    except (OSError, RuntimeError) as exc:
        return f"(확인 실패: {exc})"


def storage_snapshot() -> dict[str, Any]:
    ex = "my_show"
    return {
        "canonical_frames_key_pattern": "{anime_id}/frames",
        "example_anime_id": ex,
        "example_canonical_key": canonical_frames_key(ex),
        "anime_data_root": str(settings.ANIME_DATA_ROOT),
        "staging_root": str(settings.ANIME_STAGING_ROOT),
        "media_root": str(settings.ANIME_MEDIA_ROOT),
        "s3_media_prefix": settings.S3_MEDIA_PREFIX or None,
        "staging_layout": {
            "per_job": "잡 1건 = staging/jobs/<EmbeddingJob.public_id>/ (업로드마다 새 UUID)",
            "frames_jpg": "<staging_root>/jobs/<job-uuid>/frames/*.jpg",
            "optional_video": "<staging_root>/jobs/<job-uuid>/input/*.mp4|mkv|webm|mov|avi|m4v",
        },
        "after_job_done": "<media_root>/<anime_slug>/frames/*.jpg",
        "clip_weights_dir": str(CLIP_WEIGHTS_DIR),
        "clip_default_checkpoint": str(DEFAULT_CLIP_CHECKPOINT_PATH),
        "qdrant_indexing": "임베딩 완료 시 JPG 한 장당 Qdrant 포인트 1개(frame_index, timestamp_sec, frame_file payload).",
    }


def endpoint_catalog() -> list[dict[str, Any]]:
    return [
        {
            "method": "POST",
            "path": "/api/embed/jobs/",
            "summary": "비동기 임베딩 작업 생성. pending 행 + 스테이징 디렉터리 준비 후 Celery 자동 enqueue.",
            "body": {
                "anime_id": "my_show",
                "episode": 3,
                "genre_slugs": ["action", "fantasy"],
            },
            "notes": [
                "anime_id 필수(시리즈 슬러그). episode 선택. genre_slugs 는 선택·JSON 문자열 배열이며 있으면 해당 Anime 장르 M2M을 덮어씀.",
                "장르·시리즈·화 메타는 Qdrant payload에 비정규화되며, 검색 시 선택 필터로 쓰인다.",
                "스테이징에 JPG 또는 input/ 동영상이 있으면 커밋 후 Celery에 자동 enqueue. 없으면 pending 유지.",
            ],
            "response": "public_id, staging_rel_path, canonical_key, status, episode, genres (slug 배열, DEBUG 시 절대 경로 힌트)",
        },
        {
            "method": "GET",
            "path": "/api/embed/jobs/<uuid>/",
            "summary": "작업 한 건 조회.",
            "notes": ["URL 끝 슬래시(/) 필수."],
        },
        {
            "method": "POST",
            "path": "/api/embed/jobs/<uuid>/requeue/",
            "summary": "done/failed → pending 후 Celery 자동 enqueue.",
        },
        {
            "method": "POST",
            "path": "/api/embed/jobs/<uuid>/run/",
            "summary": "pending 잡 수동 Celery enqueue(202). 스테이징 준비 후 재시도용.",
        },
        {
            "method": "POST",
            "path": "/api/embed/search/",
            "summary": "텍스트 q 벡터 검색. genre_slugs·anime_id·episode 가 있으면 Qdrant filter 결합, 없으면 순수 벡터 유사도. genre_slugs 는 JSON 배열만.",
            "body": {"q": "질의 문장", "limit": 20, "anime_id": "my_show", "episode": 1, "genre_slugs": ["action"]},
        },
        {
            "method": "POST",
            "path": "/api/embed/run/",
            "summary": "캐논 미디어 기준 leaf 디렉터리 동기 CLIP 임베딩(점검용).",
            "body": {"relative_frames_dir": "my_show/frames"},
        },
        {
            "method": "GET",
            "path": "/api/embed/path-help/",
            "summary": "머신용 JSON — 엔드포인트 요약 + storage_paths (HTML 대시보드 없음).",
        },
    ]


def worker_cli_catalog() -> dict[str, Any]:
    return {
        "commands": [
            "celery -A anime_search worker -l info",
            "python manage.py extract_video_frames <file> --output-dir … | --staging-job-uuid …",
        ],
        "note": "임베딩 잡 실행은 Celery worker. 워커·runserver 모두 같은 ANIME_DATA_ROOT(미설정 시 프로젝트/data)를 씁니다.",
    }


def path_help_payload(request: HttpRequest) -> dict[str, Any]:
    base = request.build_absolute_uri("/").rstrip("/")
    return {
        "title": "임베딩 API 메타 (JSON)",
        "description": "스크립트·헬스체크용. 브라우저 UI는 / (장르·업로드·잡) 에서 staff 세션으로 접근.",
        "catalog_ui": {
            "genres": f"{base}/genres/",
            "upload": f"{base}/upload/",
            "jobs": f"{base}/jobs/",
        },
        "endpoints": endpoint_catalog(),
        "worker_cli": worker_cli_catalog(),
        "storage_paths": storage_snapshot(),
        "effective_ffmpeg": effective_ffmpeg(),
    }
