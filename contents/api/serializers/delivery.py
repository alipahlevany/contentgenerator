from rest_framework import serializers

from contents.models import ContentDelivery


class ContentDeliverySerializer(serializers.ModelSerializer):
    client = serializers.SlugRelatedField(read_only=True, slug_field="code")

    class Meta:
        model = ContentDelivery
        fields = (
            "id",
            "client",
            "content",
            "content_hash",
            "destination_url",
            "status",
            "attempt_count",
            "last_error",
            "last_attempt_at",
            "delivered_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
