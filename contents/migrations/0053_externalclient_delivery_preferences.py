from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contents", "0052_greeting_greetinggenerationsettings_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="externalclient",
            name="receives_standard_content",
            field=models.BooleanField(
                default=True,
                help_text="Allow generated standard content to be delivered here.",
            ),
        ),
        migrations.AddField(
            model_name="externalclient",
            name="receives_email_replies",
            field=models.BooleanField(
                default=False,
                help_text="Allow generated email replies to be delivered here.",
            ),
        ),
        migrations.AddField(
            model_name="externalclient",
            name="receives_greetings",
            field=models.BooleanField(
                default=False,
                help_text="Allow generated greetings to be delivered here.",
            ),
        ),
    ]
