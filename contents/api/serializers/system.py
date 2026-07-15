from rest_framework import serializers


class APIErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class HealthCheckSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()
