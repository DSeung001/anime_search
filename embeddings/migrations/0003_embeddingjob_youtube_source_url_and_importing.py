# Generated manually for YouTube import MVP

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("embeddings", "0002_embeddingjob_source_video_filename_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="embeddingjob",
            name="youtube_source_url",
            field=models.CharField(
                blank=True,
                default="",
                help_text="YouTube 가져오기 원본 URL (있을 때만)",
                max_length=512,
            ),
        ),
    ]
