from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contents", "0059_generation_job_recovery_count")]
    operations = [
        migrations.CreateModel(
            name="WarmupButtonRotation",
            fields=[
                ("bank_version", models.CharField(max_length=32, primary_key=True, serialize=False)),
                ("next_position", models.PositiveBigIntegerField(default=0)),
            ],
        ),
    ]
