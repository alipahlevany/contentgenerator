from rest_framework import serializers

from contents.models import GenerationJob, Language

from .generation_job_fields import DatasetSelectionField


class GreetingGenerationJobCreateSerializer(
    serializers.Serializer
):
    count = serializers.IntegerField(
        min_value=1,
        max_value=10000,
        default=1,
        help_text=(
            "Number of greetings to generate. "
            "Maximum is 10,000 per API request."
        ),
    )

    delay_seconds = serializers.FloatField(
        min_value=0,
        max_value=60,
        default=1.0,
        help_text="Delay between each generated greeting.",
    )

    languages = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all" or an array of active Language IDs.'
        ),
    )

    def validate_languages(self, selection):
        if selection == "all":
            if not Language.objects.filter(
                is_active=True
            ).exists():
                raise serializers.ValidationError(
                    "No active languages exist."
                )

            return selection

        if not selection:
            raise serializers.ValidationError(
                (
                    "languages cannot be empty. "
                    'Use "all" or provide at least one active ID.'
                )
            )

        languages = list(
            Language.objects.filter(
                id__in=selection,
                is_active=True,
            )
        )

        found_ids = {
            language.id
            for language in languages
        }

        missing_ids = [
            language_id
            for language_id in selection
            if language_id not in found_ids
        ]

        if missing_ids:
            raise serializers.ValidationError(
                (
                    "These IDs do not exist or are inactive: "
                    + ", ".join(
                        str(language_id)
                        for language_id in missing_ids
                    )
                )
            )

        return selection

    def create(self, validated_data):
        language_selection = validated_data.pop(
            "languages"
        )

        job = GenerationJob.objects.create(
            generation_type="greeting",
            count=validated_data["count"],
            delay_seconds=validated_data[
                "delay_seconds"
            ],
            external_client=validated_data.get(
                "external_client"
            ),
        )

        if language_selection == "all":
            job.use_all_languages = True
            job.save(
                update_fields=[
                    "use_all_languages",
                    "updated_at",
                ]
            )
            return job

        languages = list(
            Language.objects.filter(
                id__in=language_selection,
                is_active=True,
            )
        )

        languages_by_id = {
            language.id: language
            for language in languages
        }

        ordered_languages = [
            languages_by_id[language_id]
            for language_id in language_selection
        ]

        job.use_all_languages = False
        job.save(
            update_fields=[
                "use_all_languages",
                "updated_at",
            ]
        )

        job.languages.set(
            ordered_languages
        )

        return job
