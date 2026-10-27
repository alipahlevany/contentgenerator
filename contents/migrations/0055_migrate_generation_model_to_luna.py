from django.db import migrations, models


def migrate_legacy_models(apps, schema_editor):
    AppSettings = apps.get_model("contents", "AppSettings")
    AppSettings.objects.using(schema_editor.connection.alias).filter(
        model_name__in=[
            "gpt-4.1-nano",
            "gpt-4.1-nano-2025-04-14",
            "gpt-4.1-mini",
            "gpt-4.1-mini-2025-04-14",
        ],
    ).update(model_name="gpt-6-luna")


class Migration(migrations.Migration):
    dependencies = [
        ("contents", "0054_content_generation_job_and_log_names"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appsettings",
            name="model_name",
            field=models.CharField(default="gpt-6-luna", max_length=100),
        ),
        # Keep the working model on rollback rather than restore a retired one.
        migrations.RunPython(migrate_legacy_models, migrations.RunPython.noop),
    ]
