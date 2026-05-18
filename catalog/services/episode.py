from __future__ import annotations

from catalog.models import Anime, Episode


def get_or_create_episode(*, anime: Anime, number: int) -> Episode:
    if number < 1:
        raise ValueError("episode number must be >= 1")
    episode, _ = Episode.objects.get_or_create(anime=anime, number=number)
    return episode
