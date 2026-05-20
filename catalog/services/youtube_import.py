from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.conf import settings

from anime_indexing.video.extract import find_first_video
from anime_indexing.video.ffmpeg_resolve import resolve_ffmpeg_exe

_YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)
_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def extract_youtube_video_id(url: str) -> str:
    """YouTube URL에서 11자 video id를 추출한다."""
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if host not in _YOUTUBE_HOSTS:
        raise ValueError("YouTube URL만 지원합니다 (youtube.com, youtu.be).")

    if host == "youtu.be":
        vid = parsed.path.strip("/").split("/")[0]
    else:
        qs = parse_qs(parsed.query)
        vid = (qs.get("v") or [""])[0]
        if not vid and parsed.path.startswith("/shorts/"):
            vid = parsed.path.strip("/").split("/")[1] if len(parsed.path.strip("/").split("/")) > 1 else ""

    if not vid or not _VIDEO_ID_RE.match(vid):
        raise ValueError("유효한 YouTube 동영상 ID를 찾을 수 없습니다.")
    return vid


def normalize_youtube_url(url: str) -> str:
    """허용 호스트만 통과시키고 canonical watch URL을 반환한다."""
    vid = extract_youtube_video_id(url)
    return f"https://www.youtube.com/watch?v={vid}"


def _check_duration_limit(info: dict) -> None:
    max_sec = getattr(settings, "YOUTUBE_MAX_DURATION_SEC", 0)
    if max_sec <= 0:
        return
    duration = info.get("duration")
    if duration is None:
        return
    if float(duration) > max_sec:
        raise ValueError(
            f"동영상 길이({int(duration)}초)가 허용 상한({max_sec}초)을 초과합니다."
        )


def download_to_input_dir(*, url: str, input_dir: Path) -> Path:
    """
    yt-dlp로 input_dir에 mp4를 저장하고 저장된 Path를 반환한다.
    파일명: youtube_{video_id}.mp4
    """
    import yt_dlp

    video_id = extract_youtube_video_id(url)
    canonical = f"https://www.youtube.com/watch?v={video_id}"
    input_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(input_dir / f"youtube_{video_id}.%(ext)s")

    ffmpeg_exe = resolve_ffmpeg_exe(getattr(settings, "FFMPEG_BIN", "") or None)

    ydl_opts: dict = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": out_template,
        # bv*+ba 병합에 ffmpeg 필요. yt-dlp는 디렉터리일 때 `ffmpeg` 고정 이름만 찾으므로
        # imageio-ffmpeg(ffmpeg-*)처럼 비표준 이름은 실행 파일 전체 경로를 넘긴다.
        "ffmpeg_location": ffmpeg_exe,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(canonical, download=False)
        if not info:
            raise ValueError("YouTube 동영상 정보를 가져올 수 없습니다.")
        _check_duration_limit(info)
        ydl.download([canonical])

    found = find_first_video(input_dir)
    if found is None:
        raise RuntimeError(f"다운로드 후 input/에 동영상이 없습니다: {input_dir}")
    return found
