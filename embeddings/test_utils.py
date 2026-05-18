from __future__ import annotations

from catalog.models import Anime, Episode
from catalog.services.episode import get_or_create_episode
from embeddings.models import EmbeddingJob


def make_episode(anime: Anime, number: int = 1) -> Episode:
    return get_or_create_episode(anime=anime, number=number)


def make_job(anime: Anime, *, episode_number: int = 1, **kwargs: object) -> EmbeddingJob:
    episode = make_episode(anime, episode_number)
    return EmbeddingJob.objects.create(anime=anime, episode=episode, **kwargs)
