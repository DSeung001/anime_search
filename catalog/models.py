from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models

from catalog.services.label_ko import normalize_label_ko


_SLUG = re.compile(r"^[a-zA-Z0-9_-]{1,255}$")


class Genre(models.Model):
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    label_ko = models.CharField(max_length=255)
    label_ko_norm = models.CharField(max_length=255, unique=True, db_index=True, editable=False)
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self) -> str:
        return f"{self.label_ko} ({self.slug})"

    def clean(self) -> None:
        super().clean()
        if not (self.label_ko or "").strip():
            raise ValidationError({"label_ko": "표시명은 필수입니다."})
        norm = normalize_label_ko(self.label_ko)
        qs = Genre.objects.filter(label_ko_norm=norm)
        if self.pk is not None:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({"label_ko": "이미 등록된 한글 표시명입니다."})

    def save(self, *args, **kwargs) -> None:
        self.label_ko = (self.label_ko or "").strip()
        self.label_ko_norm = normalize_label_ko(self.label_ko)
        self.full_clean()
        super().save(*args, **kwargs)


class Anime(models.Model):
    """시리즈(슬러그) 단위."""

    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    title = models.CharField(max_length=512, blank=True, default="")
    genres = models.ManyToManyField(Genre, blank=True, related_name="animes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.slug

    @staticmethod
    def validate_slug(value: str) -> bool:
        return bool(value and _SLUG.fullmatch(value))


class Episode(models.Model):
    """시리즈 내 1화. 캐논 프레임 경로는 `{slug}/episodes/{number}/frames`."""

    anime = models.ForeignKey(
        Anime,
        on_delete=models.CASCADE,
        related_name="episodes",
    )
    number = models.PositiveIntegerField(db_index=True)
    title = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["anime_id", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["anime", "number"],
                name="catalog_episode_anime_number_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.anime.slug} ep{self.number}"
