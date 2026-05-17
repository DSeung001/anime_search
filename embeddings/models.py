from __future__ import annotations

import uuid

from django.db import models

from anime_indexing.paths import canonical_frames_key


class EmbeddingJob(models.Model):
    """
    비동기 임베딩 작업. 캐논 프레임 경로는
    `{ANIME_MEDIA_ROOT}/{anime.slug}/frames/` (= canonical_key) 와 1:1.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        PROCESSING = "processing", "처리 중"
        DONE = "done", "완료"
        FAILED = "failed", "실패"

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    anime = models.ForeignKey(
        "catalog.Anime",
        on_delete=models.PROTECT,
        related_name="embedding_jobs",
    )
    canonical_key = models.CharField(
        max_length=512,
        editable=False,
        db_index=True,
        help_text="디스크·S3 논리 키: `{anime.slug}/frames` (ANIME_MEDIA_ROOT / S3_MEDIA_PREFIX 기준 상대)",
    )
    staging_rel_path = models.CharField(
        max_length=512,
        blank=True,
        editable=False,
        help_text="ANIME_STAGING_ROOT 기준 프레임 leaf 상대경로",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    last_error = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="마지막 Celery task id (Flower·디버깅)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    episode = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Qdrant payload: 특정 화만 필터 검색할 때",
    )

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs) -> None:
        self.canonical_key = canonical_frames_key(self.anime.slug)
        if not self.staging_rel_path:
            self.staging_rel_path = f"jobs/{self.public_id}/frames"
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            from embeddings.services.job_staging import ensure_job_staging_dirs

            ensure_job_staging_dirs(self)
