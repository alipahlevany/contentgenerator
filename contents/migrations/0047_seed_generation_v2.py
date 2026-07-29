from django.db import migrations


def seed_generation_v2(apps, schema_editor):
    GenerationType = apps.get_model("contents", "GenerationType")
    DatasetCategory = apps.get_model("contents", "DatasetCategory")
    GenerationTypeDataset = apps.get_model("contents", "GenerationTypeDataset")

    generation_types = {
        "standard": ("Standard", "Standard AI content generation"),
        "email_reply": ("Email Reply", "AI email reply generation"),
    }

    datasets = [
        ("language", "Language"),
        ("topic", "Topic"),
        ("audience", "Audience"),
        ("goal", "Goal"),
        ("prompt_template", "Prompt Template"),
        ("content_rule", "Content Rule"),
    ]

    gt = {}

    for key, (name, desc) in generation_types.items():
        obj, _ = GenerationType.objects.get_or_create(
            key=key,
            defaults={
                "name": name,
                "description": desc,
            },
        )
        gt[key] = obj

    ds = {}

    for key, name in datasets:
        obj, _ = DatasetCategory.objects.get_or_create(
            key=key,
            defaults={
                "name": name,
            },
        )
        ds[key] = obj

    standard = [
        "language",
        "topic",
        "audience",
        "goal",
        "prompt_template",
        "content_rule",
    ]

    for order, key in enumerate(standard):
        GenerationTypeDataset.objects.get_or_create(
            generation_type=gt["standard"],
            dataset_category=ds[key],
            defaults={
                "selection_order": order,
                "weight": 100,
                "is_required": True,
            },
        )

    GenerationTypeDataset.objects.get_or_create(
        generation_type=gt["email_reply"],
        dataset_category=ds["language"],
        defaults={
            "selection_order": 0,
            "weight": 100,
            "is_required": True,
        },
    )


def reverse_seed_generation_v2(apps, schema_editor):
    GenerationType = apps.get_model("contents", "GenerationType")
    DatasetCategory = apps.get_model("contents", "DatasetCategory")

    GenerationType.objects.filter(
        key__in=["standard", "email_reply"]
    ).delete()

    DatasetCategory.objects.filter(
        key__in=[
            "language",
            "topic",
            "audience",
            "goal",
            "prompt_template",
            "content_rule",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contents", "0046_datasetcategory_generationtype_generationtypedataset_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_generation_v2,
            reverse_seed_generation_v2,
        ),
    ]
