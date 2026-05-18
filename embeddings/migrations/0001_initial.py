# EmbeddingJob + catalog.Episode FK. 로컬 DB 초기화 후 migrate.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalog", "0002_genre_label_ko_norm"),
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
                    "episode",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="embedding_jobs",
                        to="catalog.episode",
                    ),
                ),
                (
                    "canonical_key",
                    models.CharField(
                        db_index=True,
                        editable=False,
                        help_text="디스크·S3 논리 키: `{slug}/episodes/{n}/frames`",
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
                (
                    "celery_task_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="마지막 Celery task id (Flower·디버깅)",
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
