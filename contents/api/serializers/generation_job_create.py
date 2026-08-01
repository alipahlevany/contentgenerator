from rest_framework import serializers

from contents.models import (
    Audience,
    ContentRule,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)

from .generation_job_fields import DatasetSelectionField


class GenerationJobCreateSerializer(serializers.Serializer):
    generation_type = serializers.ChoiceField(
        choices=GenerationJob.GENERATION_TYPE_CHOICES,
        default="standard",
        help_text="Type of content generation.",
    )

    count = serializers.IntegerField(
        min_value=1,
        max_value=10000,
        default=1,
        help_text=(
            "Number of contents to generate. "
            "Maximum is 10,000 per API request."
        ),
    )

    delay_seconds = serializers.FloatField(
        min_value=0,
        max_value=60,
        default=1.0,
        help_text="Delay between each generated content.",
    )

    languages = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all" or an array of active Language IDs.'
        ),
    )

    topics = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all" or an array of active Topic IDs.'
        ),
    )

    audiences = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all" or an array of active Audience IDs.'
        ),
    )

    goals = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all" or an array of active Goal IDs.'
        ),
    )

    rules = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all", an array of active Content Rule IDs, '
            "or an empty array to use no rules."
        ),
    )

    prompt_templates = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all" or an array of active Prompt Template IDs.'
        ),
    )

    selection_config = {
        "languages": {
            "model": Language,
            "required": True,
            "use_all_field": "use_all_languages",
            "relation_name": "languages",
        },
        "topics": {
            "model": Topic,
            "required": True,
            "use_all_field": "use_all_topics",
            "relation_name": "topics",
        },
        "audiences": {
            "model": Audience,
            "required": True,
            "use_all_field": "use_all_audiences",
            "relation_name": "audiences",
        },
        "goals": {
            "model": Goal,
            "required": True,
            "use_all_field": "use_all_goals",
            "relation_name": "goals",
        },
        "rules": {
            "model": ContentRule,
            "required": False,
            "use_all_field": "use_all_rules",
            "relation_name": "rules",
        },
        "prompt_templates": {
            "model": PromptTemplate,
            "required": True,
            "use_all_field": "use_all_prompt_templates",
            "relation_name": "prompt_templates",
        },
    }

    def _validate_selection(
        self,
        field_name,
        selection,
        config,
    ):
        model = config["model"]
        required = config["required"]

        if selection == "all":
            if required and not model.objects.filter(
                is_active=True
            ).exists():
                raise serializers.ValidationError(
                    f"No active {field_name.replace('_', ' ')} exist."
                )

            return {
                "use_all": True,
                "objects": [],
            }

        if required and not selection:
            raise serializers.ValidationError(
                (
                    f"{field_name} cannot be empty. "
                    'Use "all" or provide at least one active ID.'
                )
            )

        objects = list(
            model.objects.filter(
                id__in=selection,
                is_active=True,
            )
        )

        found_ids = {
            obj.id
            for obj in objects
        }

        missing_ids = [
            item_id
            for item_id in selection
            if item_id not in found_ids
        ]

        if missing_ids:
            raise serializers.ValidationError(
                (
                    "These IDs do not exist or are inactive: "
                    + ", ".join(
                        str(item_id)
                        for item_id in missing_ids
                    )
                )
            )

        objects_by_id = {
            obj.id: obj
            for obj in objects
        }

        ordered_objects = [
            objects_by_id[item_id]
            for item_id in selection
        ]

        return {
            "use_all": False,
            "objects": ordered_objects,
        }

    def validate(self, attrs):
        resolved_selections = {}

        for field_name, config in self.selection_config.items():
            selection = attrs[field_name]

            try:
                resolved_selections[field_name] = (
                    self._validate_selection(
                        field_name,
                        selection,
                        config,
                    )
                )
            except serializers.ValidationError as exc:
                raise serializers.ValidationError(
                    {
                        field_name: exc.detail,
                    }
                )

        attrs["_resolved_selections"] = resolved_selections

        return attrs

    def create(self, validated_data):
        resolved_selections = validated_data.pop(
            "_resolved_selections"
        )

        for field_name in self.selection_config:
            validated_data.pop(field_name, None)

        job = GenerationJob.objects.create(
            count=validated_data["count"],
            delay_seconds=validated_data["delay_seconds"],
            generation_type=validated_data["generation_type"],
            external_client=validated_data.get("external_client"),
        )

        update_fields = []

        for field_name, config in self.selection_config.items():
            resolved = resolved_selections[field_name]
            use_all_field = config["use_all_field"]

            setattr(
                job,
                use_all_field,
                resolved["use_all"],
            )

            update_fields.append(use_all_field)

        job.save(
            update_fields=update_fields + ["updated_at"]
        )

        for field_name, config in self.selection_config.items():
            resolved = resolved_selections[field_name]

            if resolved["use_all"]:
                continue

            relation = getattr(
                job,
                config["relation_name"],
            )

            relation.set(resolved["objects"])

        return job
