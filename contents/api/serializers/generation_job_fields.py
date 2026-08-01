from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


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
