from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("embeddings", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="embeddingjob",
            name="celery_task_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="마지막 Celery task id (Flower·디버깅)",
                max_length=255,
            ),
        ),
    ]
