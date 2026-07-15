from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .api.serializers import (
    APIErrorSerializer,
    DatasetCollectionSerializer,
    HealthCheckSerializer,
    LanguageDatasetSerializer,
    NamedDatasetSerializer,
)
from .models import (
    Audience,
    Content,
    ContentExport,
    ContentRule,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


@extend_schema_field(
    {
        "oneOf": [
            {
                "type": "string",
                "enum": ["all"],
                "example": "all",
            },
            {
                "type": "array",
                "items": {
                    "type": "integer",
                    "minimum": 1,
                },
                "example": [1, 2, 3],
            },
        ]
    }
)
class DatasetSelectionField(serializers.Field):
    default_error_messages = {
        "invalid": (
            'Use the string "all" or an array of numeric IDs.'
        ),
        "invalid_id": (
            "Every selected ID must be a positive integer."
        ),
    }

    def to_internal_value(self, data):
        if isinstance(data, str):
            if data.strip().lower() == "all":
                return "all"

            self.fail("invalid")

        if not isinstance(data, list):
            self.fail("invalid")

        normalized_ids = []

        for value in data:
            if isinstance(value, bool):
                self.fail("invalid_id")

            try:
                item_id = int(value)
            except (TypeError, ValueError):
                self.fail("invalid_id")

            if item_id <= 0:
                self.fail("invalid_id")

            if item_id not in normalized_ids:
                normalized_ids.append(item_id)

        return normalized_ids

    def to_representation(self, value):
        return value

class GenerationJobCreateSerializer(serializers.Serializer):
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


class GenerationJobSerializer(serializers.ModelSerializer):
    progress_percent = serializers.SerializerMethodField()
    languages = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()
    audiences = serializers.SerializerMethodField()
    goals = serializers.SerializerMethodField()
    rules = serializers.SerializerMethodField()
    prompt_templates = serializers.SerializerMethodField()

    class Meta:
        model = GenerationJob
        fields = (
            "id",
            "count",
            "delay_seconds",
            "languages",
            "topics",
            "audiences",
            "goals",
            "rules",
            "prompt_templates",
            "generated_count",
            "skipped_count",
            "current_step",
            "progress_percent",
            "status",
            "error_message",
            "created_at",
            "updated_at",
        )

        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_progress_percent(self, obj):
        if not obj.count:
            return 0

        return min(
            int(
                (obj.generated_count / obj.count) * 100
            ),
            100,
        )

    def _selection_value(
        self,
        obj,
        *,
        use_all_field,
        relation_name,
    ):
        if getattr(obj, use_all_field):
            return "all"

        return list(
            getattr(obj, relation_name)
            .filter(is_active=True)
            .order_by("id")
            .values_list("id", flat=True)
        )

    @extend_schema_field(
        serializers.JSONField()
    )
    def get_languages(self, obj):
        return self._selection_value(
            obj,
            use_all_field="use_all_languages",
            relation_name="languages",
        )

    @extend_schema_field(
        serializers.JSONField()
    )
    def get_topics(self, obj):
        return self._selection_value(
            obj,
            use_all_field="use_all_topics",
            relation_name="topics",
        )

    @extend_schema_field(
        serializers.JSONField()
    )
    def get_audiences(self, obj):
        return self._selection_value(
            obj,
            use_all_field="use_all_audiences",
            relation_name="audiences",
        )

    @extend_schema_field(
        serializers.JSONField()
    )
    def get_goals(self, obj):
        return self._selection_value(
            obj,
            use_all_field="use_all_goals",
            relation_name="goals",
        )

    @extend_schema_field(
        serializers.JSONField()
    )
    def get_rules(self, obj):
        return self._selection_value(
            obj,
            use_all_field="use_all_rules",
            relation_name="rules",
        )

    @extend_schema_field(
        serializers.JSONField()
    )
    def get_prompt_templates(self, obj):
        return self._selection_value(
            obj,
            use_all_field="use_all_prompt_templates",
            relation_name="prompt_templates",
        )


class GenerationJobActionResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    job = GenerationJobSerializer()


class ContentListSerializer(serializers.ModelSerializer):
    language = serializers.SerializerMethodField()
    topic = serializers.SerializerMethodField()
    audience = serializers.SerializerMethodField()
    goal = serializers.SerializerMethodField()
    prompt_template = serializers.SerializerMethodField()

    class Meta:
        model = Content

        fields = (
            "id",
            "title",
            "language",
            "topic",
            "audience",
            "goal",
            "prompt_template",
            "status",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(
        serializers.CharField(
            allow_null=True,
        )
    )
    def get_language(self, obj):
        if obj.language:
            return obj.language.name

        return None

    @extend_schema_field(
        serializers.CharField(
            allow_null=True,
        )
    )
    def get_topic(self, obj):
        if obj.topic:
            return obj.topic.name

        return None

    @extend_schema_field(
        serializers.CharField(
            allow_null=True,
        )
    )
    def get_audience(self, obj):
        if obj.audience:
            return obj.audience.name

        return None

    @extend_schema_field(
        serializers.CharField(
            allow_null=True,
        )
    )
    def get_goal(self, obj):
        if obj.goal:
            return obj.goal.name

        return None

    @extend_schema_field(
        serializers.CharField(
            allow_null=True,
        )
    )
    def get_prompt_template(self, obj):
        if obj.prompt_template:
            return obj.prompt_template.name

        return None


class ContentDetailSerializer(ContentListSerializer):
    rules = serializers.SerializerMethodField()

    class Meta(ContentListSerializer.Meta):
        fields = ContentListSerializer.Meta.fields + (
            "prompt",
            "generated_content",
            "rules",
        )

    @extend_schema_field(
        serializers.ListField(
            child=serializers.CharField(),
        )
    )
    def get_rules(self, obj):
        return [
            rule.name
            for rule in obj.rules.all()
        ]

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
