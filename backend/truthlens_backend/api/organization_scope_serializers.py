from rest_framework import serializers
from .management_serializers import StrictFieldsSerializer


class OrganizationScopeMutationSerializer(StrictFieldsSerializer):
    domains = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, max_length=12
    )
    rationale = serializers.CharField(min_length=12, max_length=2000)
