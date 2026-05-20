from __future__ import annotations

from pathlib import Path

from django.conf import settings


def anime_staging_root() -> Path:
    return Path(settings.ANIME_STAGING_ROOT).resolve()


def resolve_under_root(root: Path, relative: str) -> Path:
    cleaned = relative.strip().replace("\\", "/").lstrip("/")
    if not cleaned or ".." in Path(cleaned).parts:
        raise ValueError("유효하지 않은 상대 경로입니다.")

    root_resolved = root.resolve()
    candidate = (root_resolved / cleaned).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise PermissionError("루트 밖으로의 경로는 허용되지 않습니다.") from exc
    return candidate


def resolve_staging_frames_dir(relative_frames_dir: str) -> Path:
    """ANIME_STAGING_ROOT 기준 프레임 leaf (예: ``jobs/<uuid>/frames``)."""
    return resolve_under_root(anime_staging_root(), relative_frames_dir)


def canonical_frames_key(anime_id: str, episode_number: int) -> str:
    """
    디스크·객체 스토어 논리 키: `{anime_id}/episodes/{n}/frames` (JPG leaf).
    """
    aid = anime_id.strip()
    if not aid or ".." in aid or "/" in aid or "\\" in aid:
        raise ValueError("anime_id는 슬러그 한 세그먼트여야 합니다.")
    if episode_number < 1:
        raise ValueError("episode_number는 1 이상이어야 합니다.")
    return f"{aid}/episodes/{int(episode_number)}/frames"


def staging_frames_leaf(staging_rel_path: str) -> Path:
    return resolve_under_root(anime_staging_root(), staging_rel_path)


def staging_job_root_from_frames_leaf(frames_leaf: Path) -> Path:
    """`.../jobs/<uuid>/frames` 의 상위 작업 루트 `.../jobs/<uuid>`."""
    return frames_leaf.parent


def staging_input_dir_for_job_frames(frames_leaf: Path) -> Path:
    return staging_job_root_from_frames_leaf(frames_leaf) / "input"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
