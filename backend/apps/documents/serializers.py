from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    amm_id = serializers.UUIDField(source="amm.id", read_only=True)
    renewal_id = serializers.UUIDField(source="renewal.id", read_only=True, default=None)
    renewal_sequence = serializers.IntegerField(
        source="renewal.sequence", read_only=True, default=None
    )
    country_iso2 = serializers.CharField(source="amm.country.iso2", read_only=True)
    product_name = serializers.CharField(source="amm.product.name", read_only=True)
    uploaded_by_email = serializers.EmailField(
        source="uploaded_by.email", read_only=True, default=None
    )
    file_url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    filename = serializers.CharField(source="export_filename", read_only=True)
    period = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "amm_id",
            "renewal_id",
            "renewal_sequence",
            "country_iso2",
            "product_name",
            "kind",
            "title",
            "document_date",
            "content_type",
            "sha256",
            "size_bytes",
            "page_count",
            "version",
            "replaces",
            "is_current",
            "uploaded_by",
            "uploaded_by_email",
            "uploaded_at",
            "archived_at",
            "file_url",
            "download_url",
            "filename",
            "period",
        ]
        read_only_fields = fields

    def get_file_url(self, obj) -> str:
        return f"/api/v1/documents/{obj.pk}/file"

    def get_download_url(self, obj) -> str:
        return f"/api/v1/documents/{obj.pk}/file?download=1"

    def get_period(self, obj) -> str:
        return "RENEWAL" if obj.renewal_id else "ORIGINAL"


class DocumentDetailSerializer(DocumentSerializer):
    versions = serializers.SerializerMethodField()

    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + ["versions"]
        read_only_fields = fields

    def get_versions(self, obj) -> list[dict]:
        chain = []
        current = obj.replaces
        while current is not None:
            chain.append(
                {
                    "id": str(current.pk),
                    "version": current.version,
                    "uploaded_at": current.uploaded_at,
                    "sha256": current.sha256,
                    "file_url": f"/api/v1/documents/{current.pk}/file",
                }
            )
            current = current.replaces
        return chain


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    kind = serializers.ChoiceField(choices=Document.Kind.choices, default=Document.Kind.AMM)
    document_date = serializers.DateField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    renewal = serializers.UUIDField(required=False, allow_null=True)


class DocumentReplaceSerializer(serializers.Serializer):
    file = serializers.FileField()
    document_date = serializers.DateField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
