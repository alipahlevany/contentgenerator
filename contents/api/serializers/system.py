from rest_framework import serializers


class APIErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
    fields = serializers.JSONField(required=False)


class APIErrorSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    error = APIErrorDetailSerializer()


class HealthCheckSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()
