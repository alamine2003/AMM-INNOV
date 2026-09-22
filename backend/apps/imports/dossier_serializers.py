"""Read-only dossier plans and explicit confirmation requests."""

from rest_framework import serializers

from .models import DossierChange, DossierFile, DossierImport


class DossierFileSerializer(serializers.ModelSerializer):
    document_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = DossierFile
        fields = [
            "id",
            "relative_path",
            "sha256",
            "content_type",
            "size_bytes",
            "extraction",
            "document_id",
        ]
        read_only_fields = fields


class DossierChangeSerializer(serializers.ModelSerializer):
    proof_file_id = serializers.UUIDField(read_only=True)
    document_id = serializers.UUIDField(
        source="proof_file.document_id", read_only=True, allow_null=True
    )
    user_email = serializers.EmailField(source="user.email", read_only=True, allow_null=True)
    target = serializers.SerializerMethodField()

    def get_target(self, obj) -> str:
        return str(obj.renewal_id) if obj.renewal_id else "amm"

    class Meta:
        model = DossierChange
        fields = [
            "id",
            "field",
            "old_value",
            "new_value",
            "confidence",
            "proof_file_id",
            "document_id",
            "user_email",
            "created_at",
            "reason",
            "source",
            "target",
        ]
        read_only_fields = fields


class DossierImportSerializer(serializers.ModelSerializer):
    files = DossierFileSerializer(many=True, read_only=True)
    audit = DossierChangeSerializer(many=True, read_only=True)
    amm_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = DossierImport
        fields = [
            "id",
            "root_name",
            "status",
            "preview",
            "preview_token",
            "created_at",
            "finished_at",
            "error",
            "amm_id",
            "files",
            "audit",
            "summary",
            "auto_applied",
        ]
        read_only_fields = fields


class DossierUploadSerializer(serializers.Serializer):
    root_name = serializers.CharField(max_length=255, trim_whitespace=False)
    paths = serializers.JSONField()
    files = serializers.ListField(child=serializers.FileField(), allow_empty=False)


class DossierAnalyzeSerializer(serializers.Serializer):
    """Relance de l'analyse ; `country` (ISO2) impose le pays si les documents ne le nomment pas."""

    country = serializers.CharField(required=False, allow_blank=True, max_length=2)


class DossierConfirmSerializer(serializers.Serializer):
    preview_token = serializers.CharField(min_length=64, max_length=64)
    accepted_changes = serializers.ListField(
        child=serializers.CharField(max_length=200),
        default=list,
        max_length=1000,
    )


class DossierFileRequestSerializer(serializers.Serializer):
    file_id = serializers.UUIDField()
