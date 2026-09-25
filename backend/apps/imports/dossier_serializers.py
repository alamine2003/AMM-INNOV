"""Lots de dossiers importés, points à vérifier plus tard, et demandes (question, rangement)."""

from rest_framework import serializers

from .models import DossierChange, DossierFile, DossierImport, DossierReviewPoint


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


class DossierReviewPointSerializer(serializers.ModelSerializer):
    """Point à vérifier plus tard : écart scan ≠ fiche (fiche gardée) ou doute de lecture."""

    batch_id = serializers.UUIDField(read_only=True)
    batch_name = serializers.CharField(source="batch.root_name", read_only=True)
    amm_id = serializers.UUIDField(read_only=True)
    renewal_id = serializers.UUIDField(read_only=True, allow_null=True)
    proof_file_id = serializers.UUIDField(read_only=True, allow_null=True)
    proof_name = serializers.SerializerMethodField()
    proof_content_type = serializers.CharField(
        source="proof_file.content_type", read_only=True, allow_null=True, default=None
    )
    applicable = serializers.BooleanField(read_only=True)
    resolved_by_email = serializers.EmailField(
        source="resolved_by.email", read_only=True, allow_null=True, default=None
    )

    def get_proof_name(self, obj) -> str | None:
        return obj.proof_file.relative_path.rsplit("/", 1)[-1] if obj.proof_file_id else None

    class Meta:
        model = DossierReviewPoint
        fields = [
            "id",
            "batch_id",
            "batch_name",
            "amm_id",
            "renewal_id",
            "code",
            "field",
            "message",
            "recorded_value",
            "scan_value",
            "proof_file_id",
            "proof_name",
            "proof_content_type",
            "confidence",
            "applicable",
            "status",
            "resolved_by_email",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = fields


class DossierImportSerializer(serializers.ModelSerializer):
    files = DossierFileSerializer(many=True, read_only=True)
    audit = DossierChangeSerializer(many=True, read_only=True)
    review_points = DossierReviewPointSerializer(many=True, read_only=True)
    open_points_count = serializers.SerializerMethodField()
    amm_id = serializers.UUIDField(read_only=True, allow_null=True)

    def get_open_points_count(self, obj) -> int:
        return sum(
            1 for point in obj.review_points.all() if point.status == DossierReviewPoint.Status.OPEN
        )

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
            "review_points",
            "open_points_count",
        ]
        read_only_fields = fields


class DossierUploadSerializer(serializers.Serializer):
    root_name = serializers.CharField(max_length=255, trim_whitespace=False)
    paths = serializers.JSONField()
    files = serializers.ListField(child=serializers.FileField(), required=False, default=list)
    # Fichiers déjà envoyés (même empreinte) : [{"path": …, "sha256": …}], sans renvoi du contenu.
    reused = serializers.JSONField(required=False, default=list)


class DossierKnownFilesSerializer(serializers.Serializer):
    sha256 = serializers.ListField(
        child=serializers.RegexField(r"^[0-9a-f]{64}$"), max_length=1000, allow_empty=True
    )


class DossierAnalyzeSerializer(serializers.Serializer):
    """Relance de l'analyse ; `country` (ISO2) impose le pays si les documents ne le nomment pas."""

    country = serializers.CharField(required=False, allow_blank=True, max_length=2)


class DossierConfirmSerializer(serializers.Serializer):
    """« Ranger les documents » (lot prêt), ou création de l'AMM absente par le siège."""

    preview_token = serializers.CharField(min_length=64, max_length=64)
    create_amm = serializers.BooleanField(default=False)


class DossierChooseAmmSerializer(serializers.Serializer):
    """Réponse à la question « c'est quelle AMM ? »."""

    amm_id = serializers.UUIDField()


class DossierFileRequestSerializer(serializers.Serializer):
    file_id = serializers.UUIDField()
