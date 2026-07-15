from rest_framework import serializers


class NamedDatasetSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class LanguageDatasetSerializer(NamedDatasetSerializer):
    code = serializers.CharField(read_only=True)


class DatasetCollectionSerializer(serializers.Serializer):
    languages = LanguageDatasetSerializer(
        many=True,
        required=False,
    )
    topics = NamedDatasetSerializer(
        many=True,
        required=False,
    )
    audiences = NamedDatasetSerializer(
        many=True,
        required=False,
    )
    goals = NamedDatasetSerializer(
        many=True,
        required=False,
    )
    rules = NamedDatasetSerializer(
        many=True,
        required=False,
    )
    prompt_templates = NamedDatasetSerializer(
        many=True,
        required=False,
    )
