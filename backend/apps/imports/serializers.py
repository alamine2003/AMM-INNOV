from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import ImportBatch, ImportRow
from .progress import get_progress


class ImportProgressSerializer(serializers.Serializer):
    done = serializers.IntegerField()
    total = serializers.IntegerField()


class ImportBatchSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )
    filename = serializers.SerializerMethodField()
    summary = serializers.DictField(read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "filename",
            "status",
            "dry_run",
            "summary",
            "reference_date",
            "created_by",
            "created_by_email",
            "created_at",
            "finished_at",
            "progress",
        ]
        read_only_fields = fields

    @extend_schema_field(ImportProgressSerializer(allow_null=True))
    def get_progress(self, obj):
        """Lignes traitées pendant que l'import tourne (registre GHPL)."""
        if obj.status != ImportBatch.Status.RUNNING:
            return None
        return get_progress(obj.pk)

    def get_filename(self, obj) -> str:
        return obj.file.name.rsplit("/", 1)[-1] if obj.file else ""


class ImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    today = serializers.DateField(required=False, allow_null=True)
    dry_run = serializers.BooleanField(required=False, default=False)


class ImportRowSerializer(serializers.ModelSerializer):
    raw = serializers.DictField(read_only=True)

    class Meta:
        model = ImportRow
        fields = ["id", "sheet", "row_number", "raw", "outcome", "message", "amm"]
        read_only_fields = fields
