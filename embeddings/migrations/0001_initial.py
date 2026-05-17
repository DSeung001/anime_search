# 최종 EmbeddingJob 스키마 (MVP: 기존 0001–0005 체인 대체). 로컬 DB는 삭제 후 migrate 권장.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmbeddingJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "anime",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="embedding_jobs",
                        to="catalog.anime",
                    ),
                ),
                (
                    "canonical_key",
                    models.CharField(
                        db_index=True,
                        editable=False,
                        help_text="디스크·S3 논리 키: `{anime.slug}/frames` (ANIME_MEDIA_ROOT / S3_MEDIA_PREFIX 기준 상대)",
                        max_length=512,
                    ),
                ),
                (
                    "staging_rel_path",
                    models.CharField(
                        blank=True,
                        editable=False,
                        help_text="ANIME_STAGING_ROOT 기준 프레임 leaf 상대경로",
                        max_length=512,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "대기"),
                            ("processing", "처리 중"),
                            ("done", "완료"),
                            ("failed", "실패"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "episode",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Qdrant payload: 특정 화만 필터 검색할 때",
                        null=True,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
