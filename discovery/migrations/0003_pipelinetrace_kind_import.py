from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discovery", "0002_pipeline_trace"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pipelinetrace",
            name="kind",
            field=models.CharField(
                choices=[
                    ("search", "검색"),
                    ("indexing", "색인"),
                    ("import", "가져오기"),
                ],
                db_index=True,
                max_length=16,
            ),
        ),
    ]
