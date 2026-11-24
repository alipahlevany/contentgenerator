from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contents", "0061_melal_template_delivery")]

    operations = [
        migrations.AddField(
            model_name="generationjob",
            name="dispatch_requested_at",
            field=models.DateTimeField(blank=True, null=True, editable=False),
        ),
    ]
