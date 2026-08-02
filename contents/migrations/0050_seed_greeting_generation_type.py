from django.db import migrations


def seed_greeting_generation_type(apps, schema_editor):
    GenerationType = apps.get_model(
        "contents",
        "GenerationType",
    )
    DatasetCategory = apps.get_model(
        "contents",
        "DatasetCategory",
    )
    GenerationTypeDataset = apps.get_model(
        "contents",
        "GenerationTypeDataset",
    )

    greeting, _ = GenerationType.objects.get_or_create(
        key="greeting",
        defaults={
            "name": "Greeting",
            "description": (
                "Short natural greeting generation."
            ),
            "is_active": True,
        },
    )

    if not greeting.is_active:
        greeting.is_active = True
        greeting.save(
            update_fields=[
                "is_active",
                "updated_at",
            ]
        )

    language = DatasetCategory.objects.get(
        key="language",
    )

    GenerationTypeDataset.objects.update_or_create(
        generation_type=greeting,
        dataset_category=language,
        defaults={
            "is_required": True,
            "selection_order": 0,
            "weight": 100,
            "is_active": True,
        },
    )

    GenerationTypeDataset.objects.filter(
        generation_type=greeting,
    ).exclude(
        dataset_category=language,
    ).delete()


def unseed_greeting_generation_type(apps, schema_editor):
    GenerationType = apps.get_model(
        "contents",
        "GenerationType",
    )

    GenerationType.objects.filter(
        key="greeting",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "contents",
            "0049_alter_content_content_type_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            seed_greeting_generation_type,
            unseed_greeting_generation_type,
        ),
    ]
