from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("contents", "0053_externalclient_delivery_preferences"),
    ]

    operations = [
        migrations.AddField(
            model_name="content",
            name="generation_job",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Job that produced this output. The output is preserved "
                    "when the job is deleted."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="generated_contents",
                to="contents.generationjob",
            ),
        ),
        migrations.AlterModelOptions(
            name="generationjoblog",
            options={
                "verbose_name": "Generation job log",
                "verbose_name_plural": "Generation job logs",
            },
        ),
    ]
