"""Strict serializers for anonymous public fact-check reads."""

from rest_framework import serializers


class PublicFactCheckQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(default=20, min_value=1, max_value=50)
    offset = serializers.IntegerField(default=0, min_value=0)

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unsupported_fields = set(data.keys()) - set(self.fields)
            if unsupported_fields:
                field_list = ", ".join(sorted(unsupported_fields))
                raise serializers.ValidationError(
                    {
                        "detail": (
                            "Unsupported public fact-check query parameters: "
                            f"{field_list}."
                        )
                    }
                )
        return super().to_internal_value(data)


class PublicFactCheckOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    logo_url = serializers.URLField(allow_null=True)
    organization_type = serializers.CharField()
    organization_type_label = serializers.CharField()


class PublicFactCheckDecisionSerializer(serializers.Serializer):
    canonical_claim = serializers.CharField(allow_blank=True)
    verdict = serializers.CharField()


class PublicFactCheckCollectionArticleSerializer(serializers.Serializer):
    headline = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    version = serializers.IntegerField(min_value=1)
    revision_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION", "FACTUAL_CORRECTION"]
    )


class PublicFactCheckHistorySummarySerializer(serializers.Serializer):
    previous_versions_count = serializers.IntegerField(min_value=0)
    has_factual_correction = serializers.BooleanField()


class PublicFactCheckCollectionItemSerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()
    claim_id = serializers.UUIDField()
    decision = PublicFactCheckDecisionSerializer()
    article = PublicFactCheckCollectionArticleSerializer()
    published_at = serializers.DateTimeField()
    history = PublicFactCheckHistorySummarySerializer()


class PublicFactCheckPageSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    limit = serializers.IntegerField(min_value=1, max_value=50)
    offset = serializers.IntegerField(min_value=0)
    organization = PublicFactCheckOrganizationSerializer()
    results = PublicFactCheckCollectionItemSerializer(many=True)


class PublicFactCheckDetailArticleSerializer(serializers.Serializer):
    headline = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    article_body = serializers.CharField(allow_blank=True)
    version = serializers.IntegerField(min_value=1)
    revision_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION", "FACTUAL_CORRECTION"]
    )


class PublicFactCheckPublicationIdentitySerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)


class PublicFactCheckRevisionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=["EDITORIAL_REVISION", "FACTUAL_CORRECTION"]
    )
    reason = serializers.CharField(allow_blank=True)
    requested_at = serializers.DateTimeField()
    predecessor = PublicFactCheckPublicationIdentitySerializer()


class PublicFactCheckSourceSerializer(serializers.Serializer):
    url = serializers.URLField()
    title = serializers.CharField(allow_blank=True, allow_null=True)
    source_origin = serializers.ChoiceField(
        choices=[
            "DECISION_EVIDENCE",
            "ORGANIZATION_EDITORIAL",
            "LEGACY_IMPORT",
            "UNKNOWN",
        ]
    )
    citation_state = serializers.ChoiceField(
        choices=[
            "CITED_IN_ARTICLE",
            "NOT_CITED_IN_ARTICLE",
            "CITATION_HISTORY_UNAVAILABLE",
        ]
    )


class PublicFactCheckLineageItemSerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    revision_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION", "FACTUAL_CORRECTION"]
    )
    headline = serializers.CharField(allow_blank=True)
    canonical_claim = serializers.CharField(allow_blank=True)
    verdict = serializers.CharField()
    published_at = serializers.DateTimeField()
    history_state = serializers.ChoiceField(choices=["CURRENT", "SUPERSEDED"])
    revision_reason = serializers.CharField(allow_blank=True, allow_null=True)


class PublicFactCheckDetailSerializer(serializers.Serializer):
    selected_publication_id = serializers.UUIDField()
    current_publication_id = serializers.UUIDField()
    history_state = serializers.ChoiceField(choices=["CURRENT", "SUPERSEDED"])
    organization = PublicFactCheckOrganizationSerializer()
    claim_id = serializers.UUIDField()
    decision = PublicFactCheckDecisionSerializer()
    article = PublicFactCheckDetailArticleSerializer()
    published_at = serializers.DateTimeField()
    revision = PublicFactCheckRevisionSerializer(allow_null=True)
    sources = PublicFactCheckSourceSerializer(many=True)
    lineage = PublicFactCheckLineageItemSerializer(many=True)
