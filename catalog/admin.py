from django.contrib import admin

from .models import Anime, Episode, Genre


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ("slug", "label_ko", "sort_order")
    search_fields = ("slug", "label_ko")


@admin.register(Anime)
class AnimeAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "updated_at")
    search_fields = ("slug", "title")
    filter_horizontal = ("genres",)


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ("anime", "number", "title", "updated_at")
    list_filter = ("anime",)
    search_fields = ("anime__slug", "title")
    ordering = ("anime__slug", "number")
