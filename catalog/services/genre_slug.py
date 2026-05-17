from __future__ import annotations

import re
import secrets

from django.utils.text import slugify

from catalog.models import Genre

_SLUG = re.compile(r"^[a-zA-Z0-9_-]{1,255}$")


def unique_genre_slug(label_ko: str, *, exclude_pk: int | None = None) -> str:
    """
    ``label_ko`` 로부터 ASCII slug 를 만들고, DB 에서 유일할 때까지 접미사를 붙인다.
    ``slugify`` 결과가 비거나 규칙 밖이면 ``g-`` + hex 로 고정 길이 키를 쓴다.
    """
    raw = (label_ko or "").strip()
    base = slugify(raw) or ""
    if not base or not _SLUG.fullmatch(base):
        base = f"g-{secrets.token_hex(4)}"
    base = base[:255]

    qs = Genre.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)

    candidate = base
    n = 2
    while qs.filter(slug=candidate).exists():
        suf = f"-{n}"
        n += 1
        candidate = (base[: max(1, 255 - len(suf))] + suf)[:255]
    return candidate
