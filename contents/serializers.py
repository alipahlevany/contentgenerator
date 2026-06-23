from rest_framework import serializers

from .models import Content, GenerationJob


class APIErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class HealthCheckSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()


class GenerationJobCreateSerializer(serializers.Serializer):
    count = serializers.IntegerField(
        min_value=1,
        max_value=100,
        default=1,
        help_text="Number of contents to generate. Maximum is 100 per API request.",
    )

    delay_seconds = serializers.FloatField(
        min_value=0,
        max_value=60,
        default=1.0,
        help_text="Delay between each generated content.",
    )

    def create(self, validated_data):
        return GenerationJob.objects.create(
            count=validated_data["count"],
            delay_seconds=validated_data["delay_seconds"],
        )


class GenerationJobSerializer(serializers.ModelSerializer):
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = GenerationJob
        fields = (
            "id",
            "count",
            "delay_seconds",
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

    def get_progress_percent(self, obj):
        if not obj.count:
            return 0

        return int((obj.generated_count / obj.count) * 100)


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

    def get_language(self, obj):
        if obj.language:
            return obj.language.name

        return None

    def get_topic(self, obj):
        if obj.topic:
            return obj.topic.name

        return None

    def get_audience(self, obj):
        if obj.audience:
            return obj.audience.name

        return None

    def get_goal(self, obj):
        if obj.goal:
            return obj.goal.name

        return None

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

    def get_rules(self, obj):
        return [
            rule.name
            for rule in obj.rules.all()
        ]