from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from contents.models import GenerationJob


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
            "generation_type",
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

        prefetched = getattr(obj, f"active_{relation_name}", None)
        if prefetched is not None:
            return [item.id for item in prefetched]

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
