from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contents", "0058_warmup_template_health")]
    operations = [
        migrations.AddField(
            model_name="generationjob",
            name="recovery_count",
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
    ]
