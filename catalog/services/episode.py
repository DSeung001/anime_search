from __future__ import annotations

from catalog.models import Anime, Episode


def get_or_create_episode(*, anime: Anime, number: int, title: str) -> Episode:
    if number < 1:
        raise ValueError("episode number must be >= 1")
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("episode title is required")

    episode, _created = Episode.objects.get_or_create(
        anime=anime,
        number=number,
        defaults={"title": clean_title},
    )
    if episode.title != clean_title:
        episode.title = clean_title
        episode.save(update_fields=["title", "updated_at"])
    return episode
