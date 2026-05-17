from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from catalog.models import Genre
from catalog.services.genre_slug import unique_genre_slug
from catalog.services.label_ko import normalize_label_ko


def bulk_create_genres(
    labels: list[str],
    *,
    sort_order: int = 0,
) -> tuple[list[Genre], list[str]]:
    """부분 성공: 중복·검증 실패 건은 스킵하고 나머지 생성."""
    created: list[Genre] = []
    skipped: list[str] = []
    pending_slugs: set[str] = set()

    for label in labels:
        display = label.strip()
        if not display:
            skipped.append("(빈 값): 건너뜀")
            continue
        norm = normalize_label_ko(display)
        if Genre.objects.filter(label_ko_norm=norm).exists():
            skipped.append(f"{display}: 이미 등록된 표시명")
            continue
        slug = unique_genre_slug(display)
        base_slug = slug
        n = 2
        while slug in pending_slugs:
            suf = f"-{n}"
            slug = (base_slug[: max(1, 255 - len(suf))] + suf)[:255]
            n += 1
        pending_slugs.add(slug)
        try:
            genre = Genre(slug=slug, label_ko=display, sort_order=sort_order)
            genre.save()
            created.append(genre)
        except ValidationError as exc:
            msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            skipped.append(f"{display}: {msg}")
        except IntegrityError:
            skipped.append(f"{display}: 이미 등록된 표시명")
    return created, skipped
