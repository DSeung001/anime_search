from django.contrib import admin

from embeddings.models import EmbeddingJob


@admin.register(EmbeddingJob)
class EmbeddingJobAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "anime_slug_display",
        "episode",
        "status",
        "canonical_key",
        "created_at",
        "processed_at",
    )
    list_filter = ("status",)
    readonly_fields = (
        "public_id",
        "canonical_key",
        "staging_rel_path",
        "celery_task_id",
        "created_at",
        "updated_at",
        "processed_at",
    )

    @admin.display(description="anime (slug)")
    def anime_slug_display(self, obj: EmbeddingJob) -> str:
        return obj.anime.slug
