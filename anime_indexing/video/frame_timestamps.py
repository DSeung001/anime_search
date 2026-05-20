from __future__ import annotations

from pathlib import Path

from django.conf import settings

from anime_indexing.video.pts_manifest import (
    MANIFEST_FILENAME,
    load_pts_by_file,
    write_frames_pts_manifest,
)

_FULL_FRAME_MANIFEST_HELP = (
    "전 프레임 추출(VIDEO_EXTRACT_FPS≤0)에는 ffprobe PTS 매니페스트가 필요합니다. "
    "brew install ffmpeg, .env에 FFPROBE_BIN 설정, "
    "또는 VIDEO_EXTRACT_FPS=1 등 양수로 다운샘플하세요."
)


def get_extract_fps() -> float:
    return float(getattr(settings, "VIDEO_EXTRACT_FPS", 1.0))


def manifest_path(frames_leaf: Path) -> Path:
    return frames_leaf / MANIFEST_FILENAME


def manifest_present(frames_leaf: Path) -> bool:
    return manifest_path(frames_leaf).is_file()


def compute_frame_timestamps_sec(
    jpgs: list[Path],
    frames_leaf: Path,
) -> tuple[list[float], str]:
    """
    프레임별 재생 시각(초) 목록과 출처 라벨.

    - VIDEO_EXTRACT_FPS > 0: index / fps (추출 간격과 동일)
    - VIDEO_EXTRACT_FPS <= 0: frames_pts_manifest.jsonl 필수
    """
    fps = get_extract_fps()
    n = len(jpgs)
    if n == 0:
        return [], "empty"

    if fps > 0:
        return [float(i) / fps for i in range(n)], "extract_fps"

    pts_map = load_pts_by_file(frames_leaf)
    missing = [p.name for p in jpgs if p.name not in pts_map]
    if missing:
        raise RuntimeError(_FULL_FRAME_MANIFEST_HELP)

    return [pts_map[p.name] for p in jpgs], "pts_manifest"


def ensure_pts_manifest_if_needed(
    *,
    frames_leaf: Path,
    video_path: Path | None,
    ffprobe_bin: str | None = None,
) -> Path | None:
    """JPG는 있는데 매니페스트가 없을 때만 생성 시도 (전 프레임 모드)."""
    if get_extract_fps() > 0:
        return None
    if manifest_present(frames_leaf):
        return manifest_path(frames_leaf)
    if video_path is None or not video_path.is_file():
        return None
    if not any(frames_leaf.glob("*.jpg")):
        return None
    return write_frames_pts_manifest(
        video_path=video_path,
        frames_leaf=frames_leaf,
        ffprobe_bin=ffprobe_bin,
    )
