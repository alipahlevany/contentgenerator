from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contents", "0063_reply_export_workspace"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReplyContentExport",
            fields=[],
            options={
                "verbose_name": "Reply export history",
                "verbose_name_plural": "Reply export history",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("contents.contentexport",),
        ),
    ]
