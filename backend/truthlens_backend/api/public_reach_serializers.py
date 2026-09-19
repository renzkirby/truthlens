from rest_framework import serializers

from .models import PublicReachEvent
from .public_reach_service import InvalidPublicReach, validate_public_reach_pair


class PublicReachRequestSerializer(serializers.Serializer):
    client_event_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=PublicReachEvent.EventType.choices)
    source_surface = serializers.ChoiceField(
        choices=PublicReachEvent.SourceSurface.choices
    )
    organization_slug = serializers.SlugField(max_length=255)
    publication_id = serializers.UUIDField(required=False, allow_null=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["Unknown fields or invalid request object."]}
            )

        for name in (
            "client_event_id",
            "event_type",
            "source_surface",
            "organization_slug",
        ):
            if name in data and not isinstance(data[name], str):
                raise serializers.ValidationError({name: "Must be a string."})

        if data.get("publication_id") is not None and not isinstance(
            data["publication_id"], str
        ):
            raise serializers.ValidationError(
                {"publication_id": "Must be a UUID string or null."}
            )

        return super().to_internal_value(data)

    def validate(self, attrs):
        try:
            validate_public_reach_pair(attrs["event_type"], attrs["source_surface"])
        except InvalidPublicReach as error:
            raise serializers.ValidationError(str(error)) from error
        profile_view = (
            attrs["event_type"] == PublicReachEvent.EventType.PARTNER_PROFILE_VIEW
        )
        if profile_view and attrs.get("publication_id") is not None:
            raise serializers.ValidationError(
                "Profile views cannot specify a publication."
            )
        if not profile_view and attrs.get("publication_id") is None:
            raise serializers.ValidationError(
                "Publication events require publication_id."
            )
        return attrs
