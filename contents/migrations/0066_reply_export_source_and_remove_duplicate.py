from django.db import migrations, models


def mark_existing_exports_unknown(apps, schema_editor):
    ContentExport = apps.get_model("contents", "ContentExport")
    ContentExport.objects.all().update(export_method="unknown")


class Migration(migrations.Migration):

    dependencies = [
        ("contents", "0065_clarify_reply_admin_sections"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentexport",
            name="export_method",
            field=models.CharField(
                choices=[("api", "API pull"), ("manual_download", "Manual CSV/JSON download"), ("unknown", "Earlier record — method untracked")],
                db_index=True,
                default="api",
                max_length=20,
            ),
        ),
        migrations.RunPython(mark_existing_exports_unknown, migrations.RunPython.noop),
        migrations.DeleteModel(
            name="ReplyExport",
        ),
    ]
