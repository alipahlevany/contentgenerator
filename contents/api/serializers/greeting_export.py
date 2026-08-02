from rest_framework import serializers

from contents.models import Language

from .generation_job_fields import DatasetSelectionField


class GreetingExportRequestSerializer(
    serializers.Serializer
):
    count = serializers.IntegerField(
        min_value=1,
        max_value=1000,
        default=1,
        help_text=(
            "Maximum number of matching greetings to return."
        ),
    )

    delay_seconds = serializers.FloatField(
        min_value=0,
        max_value=60,
        default=0,
        help_text=(
            "Accepted for request compatibility. "
            "It is not used for pull-based exports."
        ),
    )

    languages = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all" or an array of active Language IDs.'
        ),
    )

    def validate_languages(self, selection):
        if selection == "all":
            return selection

        if not selection:
            raise serializers.ValidationError(
                'Use "all" or provide at least one ID.'
            )

        existing_ids = set(
            Language.objects
            .filter(
                id__in=selection,
                is_active=True,
            )
            .values_list(
                "id",
                flat=True,
            )
        )

        missing_ids = [
            language_id
            for language_id in selection
            if language_id not in existing_ids
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
