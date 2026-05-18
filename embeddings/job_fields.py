from __future__ import annotations

from typing import Any


def required_episode_number_from_json(body: dict[str, Any]) -> tuple[int | None, str | None]:
    """REST 본문에서 화수(필수)를 추출한다."""
    episode = body.get("episode")
    if episode is None or episode == "":
        return None, "episode is required"
    try:
        ep = int(episode)
    except (TypeError, ValueError):
        return None, "episode must be an integer"
    if ep < 1:
        return None, "episode must be >= 1"
    return ep, None
