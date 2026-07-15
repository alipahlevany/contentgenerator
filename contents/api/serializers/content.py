from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from contents.models import Content


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
