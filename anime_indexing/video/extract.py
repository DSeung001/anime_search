from __future__ import annotations

import subprocess
from pathlib import Path

from .ffmpeg_resolve import resolve_ffmpeg_exe

VIDEO_EXTENSIONS = frozenset({".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"})


def find_first_video(input_dir: Path) -> Path | None:
    if not input_dir.is_dir():
        return None
    for p in sorted(input_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
            return p
    return None


def extract_frames_ffmpeg(
    *,
    video_path: Path,
    output_dir: Path,
    ffmpeg_bin: str | None = None,
    fps: float | None = None,
    max_frames: int | None = None,
    jpeg_quality: int = 2,
) -> int:
    """
    ffmpeg으로 동영상의 디코드된 **모든** 프레임을 JPG로 남긴다(기본).

    - ``fps`` 가 양수이면 ``fps`` 필터로 초당 해당 장만 출력(다운샘플).
    - ``fps`` 가 None 이거나 0 이하이면 fps 필터를 쓰지 않는다(전 프레임).
    - ``max_frames`` 가 양수이면 출력 장 수 상한. None 또는 0 이하이면 제한 없음.

    ``ffmpeg_bin`` 이 None/빈 문자열이면 ``imageio-ffmpeg`` 동봉 바이너리를 사용한다.
    출력 파일명: ``frame_000001.jpg`` …
    """
    if not video_path.is_file():
        raise FileNotFoundError(f"동영상 파일이 없습니다: {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("frame_*.jpg"):
        old.unlink()

    exe = resolve_ffmpeg_exe(ffmpeg_bin)
    cmd: list[str] = [
        exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
    ]
    if fps is not None and fps > 0:
        cmd.extend(["-vf", f"fps={fps}"])
    cmd.extend(["-q:v", str(jpeg_quality)])
    if max_frames is not None and max_frames > 0:
        cmd.extend(["-frames:v", str(max_frames)])
    cmd.append(str(output_dir / "frame_%06d.jpg"))

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg 실패 (exit {proc.returncode}): {err or 'no stderr'}")

    return len(list(output_dir.glob("frame_*.jpg")))
