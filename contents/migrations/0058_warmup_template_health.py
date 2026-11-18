from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contents", "0057_add_warmup_template_generation"),
    ]

    operations = [
        migrations.AddField(
            model_name="appsettings",
            name="last_warmup_template_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="last_warmup_template_error_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
