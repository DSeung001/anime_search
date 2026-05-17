from __future__ import annotations

from typing import Any


def extra_embedding_job_fields_from_json(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """REST 본문에서 ``EmbeddingJob`` 생성용 선택 필드만 추출한다 (episode)."""
    extra: dict[str, Any] = {}
    episode = body.get("episode")
    if episode is not None and episode != "":
        try:
            ep = int(episode)
            if ep < 1:
                return {}, "episode must be >= 1"
            extra["episode"] = ep
        except (TypeError, ValueError):
            return {}, "episode must be an integer"
    return extra, None
