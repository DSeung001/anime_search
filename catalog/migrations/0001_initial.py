# Generated manually for catalog app

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Genre",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("label_ko", models.CharField(max_length=255)),
                ("sort_order", models.PositiveSmallIntegerField(db_index=True, default=0)),
            ],
            options={
                "ordering": ["sort_order", "slug"],
            },
        ),
        migrations.CreateModel(
            name="Anime",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("title", models.CharField(blank=True, default="", max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("genres", models.ManyToManyField(blank=True, related_name="animes", to="catalog.genre")),
            ],
            options={
                "ordering": ["slug"],
            },
        ),
        migrations.CreateModel(
            name="Episode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField(db_index=True)),
                ("title", models.CharField(blank=True, default="", max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "anime",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="episodes",
                        to="catalog.anime",
                    ),
                ),
            ],
            options={
                "ordering": ["anime_id", "number"],
            },
        ),
        migrations.AddConstraint(
            model_name="episode",
            constraint=models.UniqueConstraint(
                fields=("anime", "number"),
                name="catalog_episode_anime_number_uniq",
            ),
        ),
    ]
