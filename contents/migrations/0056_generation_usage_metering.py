from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contents", "0055_migrate_generation_model_to_luna")]
    operations = [
        migrations.AddField(
            model_name="aiusagelog", name="cached_input_tokens",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="aiusagelog", name="generation_type",
            field=models.CharField(max_length=30, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="aiusagelog", name="estimated_cost",
            field=models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True, default=None),
        ),
    ]
