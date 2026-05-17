from __future__ import annotations

import re

_ANIME_ID = re.compile(r"^[a-zA-Z0-9_-]{1,255}$")


def is_valid_anime_id(value: str) -> bool:
    """HTTP·폼·``SlugField`` 와 동일: ASCII 슬러그 1~255자."""
    return bool(value and _ANIME_ID.fullmatch(value))
