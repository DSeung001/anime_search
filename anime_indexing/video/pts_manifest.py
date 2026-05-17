from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from anime_indexing.video.ffmpeg_resolve import resolve_ffprobe_exe

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "frames_pts_manifest.jsonl"


def sorted_frame_jpgs(frames_dir: Path) -> list[Path]:
    """``frame_000001.jpg`` 등 숫자 순으로 정렬."""

    def sort_key(p: Path) -> tuple[int, str]:
        m = re.search(r"(\d+)", p.stem)
        return (int(m.group(1)) if m else 0, p.name)

    return sorted(frames_dir.glob("*.jpg"), key=sort_key)


def ffprobe_pkt_pts_times(video_path: Path, *, ffprobe_bin: str | None = None) -> list[float]:
    """비디오 스트림 프레임별 ``pkt_pts_time``(초). ffprobe 없거나 실패 시 빈 리스트."""
    exe = resolve_ffprobe_exe(ffprobe_bin)
    if not exe:
        logger.warning(
            "ffprobe를 찾을 수 없습니다. PTS 매니페스트를 생략합니다 "
            "(brew install ffmpeg 또는 FFPROBE_BIN 설정)."
        )
        return []

    cmd = [
        exe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=pkt_pts_time",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe 타임아웃: %s", video_path)
        return []
    except OSError as exc:
        logger.warning("ffprobe 실행 불가 (%s): %s", exe, exc)
        return []
    if proc.returncode != 0:
        logger.warning("ffprobe 실패 (%s): %s", proc.returncode, (proc.stderr or "").strip()[:500])
        return []
    out: list[float] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line or line == "N/A":
            continue
        if line.startswith("frame,") or line == "pkt_pts_time":
            continue
        try:
            out.append(float(line))
        except ValueError:
            continue
    return out


def write_frames_pts_manifest(
    *,
    video_path: Path,
    frames_leaf: Path,
    ffprobe_bin: str | None = None,
) -> Path | None:
    """
    추출된 JPG 순서에 맞춰 ``frames_pts_manifest.jsonl`` 작성.
    ffprobe 프레임 수와 JPG 수 중 작은 쪽만 사용. ffprobe 없으면 None(파일 미작성).
    """
    jpgs = sorted_frame_jpgs(frames_leaf)
    pts = ffprobe_pkt_pts_times(video_path, ffprobe_bin=ffprobe_bin)
    if not pts:
        return None

    n = min(len(jpgs), len(pts))
    manifest = frames_leaf / MANIFEST_FILENAME
    with manifest.open("w", encoding="utf-8") as f:
        for i in range(n):
            rec: dict[str, Any] = {"file": jpgs[i].name, "pts_sec": pts[i]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if n < len(jpgs):
        logger.warning(
            "PTS 개수(%s) < JPG 개수(%s): 일부 프레임은 매니페스트 없음 (%s)",
            n,
            len(jpgs),
            frames_leaf,
        )
    return manifest


def load_pts_by_file(frames_leaf: Path) -> dict[str, float]:
    """파일명 -> pts_sec. 매니페스트 없으면 빈 dict."""
    manifest = frames_leaf / MANIFEST_FILENAME
    if not manifest.is_file():
        return {}
    out: dict[str, float] = {}
    with manifest.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[str(rec["file"])] = float(rec["pts_sec"])
    return out
