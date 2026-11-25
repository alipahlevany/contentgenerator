from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contents", "0064_reply_content_export_history"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="emailreply",
            options={
                "proxy": True,
                "verbose_name": "Generated reply",
                "verbose_name_plural": "Generated replies",
            },
        ),
        migrations.AlterModelOptions(
            name="replyexport",
            options={
                "proxy": True,
                "verbose_name": "Downloadable reply",
                "verbose_name_plural": "Downloadable replies",
            },
        ),
    ]
