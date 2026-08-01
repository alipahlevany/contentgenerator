from rest_framework import serializers

from .generation_job_read import GenerationJobSerializer


class GenerationJobActionResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    job = GenerationJobSerializer()
