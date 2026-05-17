from django.contrib import admin

from .models import Anime, Genre


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ("slug", "label_ko", "sort_order")
    search_fields = ("slug", "label_ko")


@admin.register(Anime)
class AnimeAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "updated_at")
    search_fields = ("slug", "title")
    filter_horizontal = ("genres",)
