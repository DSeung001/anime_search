from django.db import migrations, models

from catalog.services.label_ko import normalize_label_ko


def backfill_label_ko_norm(apps, schema_editor) -> None:
    Genre = apps.get_model("catalog", "Genre")
    used: set[str] = set()
    for genre in Genre.objects.all().order_by("pk"):
        base = normalize_label_ko(genre.label_ko)
        norm = base
        n = 2
        while norm in used:
            suf = f"#{n}"
            norm = (base[: max(1, 255 - len(suf))] + suf)[:255]
            n += 1
        used.add(norm)
        genre.label_ko_norm = norm
        genre.save(update_fields=["label_ko_norm"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="genre",
            name="label_ko_norm",
            field=models.CharField(db_index=True, default="", editable=False, max_length=255),
        ),
        migrations.RunPython(backfill_label_ko_norm, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="genre",
            name="label_ko_norm",
            field=models.CharField(db_index=True, editable=False, max_length=255, unique=True),
        ),
    ]
