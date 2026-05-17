from __future__ import annotations

import shutil
from pathlib import Path


def resolve_ffmpeg_exe(explicit: str | None) -> str:
    """
    - ``explicit`` 이 비어 있지 않으면 그 경로를 그대로 사용 (시스템/도커 등).
    - 비어 있으면 ``imageio-ffmpeg`` 가 동봉한 ffmpeg 실행 파일을 사용한다.
    """
    if explicit and explicit.strip():
        return explicit.strip()
    try:
        import imageio_ffmpeg  # type: ignore[import-untyped]

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError(
            "동영상 프레임 추출을 위해 `pip install imageio-ffmpeg` 가 필요합니다. "
            "또는 시스템에 ffmpeg 를 설치한 뒤 환경변수 FFMPEG_BIN 에 절대 경로를 지정하세요."
        ) from exc


def resolve_ffprobe_exe(explicit: str | None) -> str | None:
    """
    ffprobe 경로. 없으면 None (PTS 매니페스트 생략, 임베딩은 기본 fps 폴백).

    - ``explicit`` 이 있으면 해당 경로(파일일 때만).
    - ffmpeg과 같은 디렉터리의 ``ffprobe`` (Homebrew 등).
    - PATH 의 ``ffprobe``.
  """
    if explicit and explicit.strip():
        p = Path(explicit.strip())
        return str(p) if p.is_file() else None

    try:
        ff = Path(resolve_ffmpeg_exe(None))
        probe = ff.parent / "ffprobe"
        if probe.is_file():
            return str(probe)
    except RuntimeError:
        pass

    return shutil.which("ffprobe")
