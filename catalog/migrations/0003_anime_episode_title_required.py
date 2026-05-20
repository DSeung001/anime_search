from django.db import migrations, models


def backfill_titles(apps, schema_editor) -> None:
    Anime = apps.get_model("catalog", "Anime")
    Episode = apps.get_model("catalog", "Episode")
    for anime in Anime.objects.filter(title=""):
        anime.title = anime.slug
        anime.save(update_fields=["title"])
    for episode in Episode.objects.filter(title=""):
        episode.title = f"{episode.number}화"
        episode.save(update_fields=["title"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_genre_label_ko_norm"),
    ]

    operations = [
        migrations.RunPython(backfill_titles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="anime",
            name="title",
            field=models.CharField(max_length=512),
        ),
        migrations.AlterField(
            model_name="episode",
            name="title",
            field=models.CharField(max_length=512),
        ),
    ]
