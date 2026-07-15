from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from contents.models import (
    Audience,
    Content,
    ContentRule,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from contents.api.serializers.generation_jobs import DatasetSelectionField


class ContentExportRequestSerializer(serializers.Serializer):
    count = serializers.IntegerField(
        min_value=1,
        max_value=1000,
        default=1,
        help_text=(
            "Maximum number of matching existing contents to return."
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
        help_text='Use "all" or an array of Language IDs.',
    )

    topics = DatasetSelectionField(
        default="all",
        help_text='Use "all" or an array of Topic IDs.',
    )

    audiences = DatasetSelectionField(
        default="all",
        help_text='Use "all" or an array of Audience IDs.',
    )

    goals = DatasetSelectionField(
        default="all",
        help_text='Use "all" or an array of Goal IDs.',
    )

    rules = DatasetSelectionField(
        default="all",
        help_text=(
            'Use "all", an empty array for no rule filter, '
            "or an array of Content Rule IDs."
        ),
    )

    prompt_templates = DatasetSelectionField(
        default="all",
        help_text='Use "all" or an array of Prompt Template IDs.',
    )

    filter_models = {
        "languages": Language,
        "topics": Topic,
        "audiences": Audience,
        "goals": Goal,
        "rules": ContentRule,
        "prompt_templates": PromptTemplate,
    }

    required_non_empty = {
        "languages",
        "topics",
        "audiences",
        "goals",
        "prompt_templates",
    }

    def validate(self, attrs):
        errors = {}

        for field_name, model in self.filter_models.items():
            selection = attrs[field_name]

            if selection == "all":
                continue

            if (
                field_name in self.required_non_empty
                and not selection
            ):
                errors[field_name] = (
                    'Use "all" or provide at least one ID.'
                )
                continue

            if not selection:
                continue

            existing_ids = set(
                model.objects
                .filter(
                    id__in=selection,
                    is_active=True,
                )
                .values_list("id", flat=True)
            )

            missing_ids = [
                item_id
                for item_id in selection
                if item_id not in existing_ids
            ]

            if missing_ids:
                errors[field_name] = (
                    "These IDs do not exist or are inactive: "
                    + ", ".join(
                        str(item_id)
                        for item_id in missing_ids
                    )
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


class ContentExportItemSerializer(serializers.ModelSerializer):
    language = serializers.SerializerMethodField()
    topic = serializers.SerializerMethodField()
    audience = serializers.SerializerMethodField()
    goal = serializers.SerializerMethodField()
    prompt_template = serializers.SerializerMethodField()
    rules = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = (
            "id",
            "title",
            "generated_content",
            "prompt",
            "content_hash",
            "language",
            "topic",
            "audience",
            "goal",
            "prompt_template",
            "rules",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def _related_value(self, obj, field_name):
        related = getattr(obj, field_name)

        if related is None:
            return None

        return {
            "id": related.id,
            "name": related.name,
        }

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_language(self, obj):
        value = self._related_value(obj, "language")

        if value is not None:
            value["code"] = obj.language.code

        return value

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_topic(self, obj):
        return self._related_value(obj, "topic")

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_audience(self, obj):
        return self._related_value(obj, "audience")

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_goal(self, obj):
        return self._related_value(obj, "goal")

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_prompt_template(self, obj):
        return self._related_value(obj, "prompt_template")

    @extend_schema_field(
        serializers.ListField(
            child=serializers.DictField(),
        )
    )
    def get_rules(self, obj):
        return [
            {
                "id": rule.id,
                "name": rule.name,
            }
            for rule in obj.rules.all()
        ]


class ContentExportResponseSerializer(serializers.Serializer):
    client = serializers.CharField()
    requested = serializers.IntegerField()
    exported = serializers.IntegerField()
    remaining = serializers.IntegerField()
    items = ContentExportItemSerializer(many=True)
