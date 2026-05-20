from __future__ import annotations

from pathlib import Path

from anime_indexing.paths import ensure_dir, staging_frames_leaf, staging_input_dir_for_job_frames

from catalog.models import Anime, Episode
from catalog.services.episode import get_or_create_episode
from embeddings.models import EmbeddingJob


def make_episode(anime: Anime, number: int = 1, *, title: str | None = None) -> Episode:
    ep_title = (title or "").strip() or f"{number}화"
    return get_or_create_episode(anime=anime, number=number, title=ep_title)


def make_job(anime: Anime, *, episode_number: int = 1, **kwargs: object) -> EmbeddingJob:
    episode = make_episode(anime, episode_number)
    return EmbeddingJob.objects.create(anime=anime, episode=episode, **kwargs)


def staging_with_jpg(job: EmbeddingJob) -> Path:
    leaf = staging_frames_leaf(job.staging_rel_path)
    ensure_dir(leaf)
    ensure_dir(staging_input_dir_for_job_frames(leaf))
    jpg = leaf / "frame_0001.jpg"
    jpg.write_bytes(b"\xff\xd8\xff")
    return jpg


def staging_with_video(job: EmbeddingJob, *, name: str = "clip.mp4") -> Path:
    leaf = staging_frames_leaf(job.staging_rel_path)
    ensure_dir(leaf)
    input_dir = staging_input_dir_for_job_frames(leaf)
    ensure_dir(input_dir)
    video = input_dir / name
    video.write_bytes(b"\x00")
    return video
