from rest_framework import serializers
from .management_serializers import StrictFieldsSerializer


class OrganizationScopeMutationSerializer(StrictFieldsSerializer):
    action = serializers.ChoiceField(choices=["REQUEST", "ACTIVATE"])
    domains = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, max_length=12
    )
    jurisdictions = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, max_length=50
    )
    rationale = serializers.CharField(min_length=12, max_length=2000)
