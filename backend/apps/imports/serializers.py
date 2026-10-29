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


class GhplSyncRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    status_label = serializers.CharField(source="get_status_display")
    trigger = serializers.CharField()
    started_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)
    registry_modified = serializers.DateTimeField(allow_null=True)
    message = serializers.CharField()
    summary = serializers.DictField()
    registry_batch = serializers.UUIDField(source="registry_batch_id", allow_null=True)
    scans_batch = serializers.UUIDField(source="scans_batch_id", allow_null=True)


class GhplSyncStatusSerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    enabled = serializers.BooleanField()
    folder = serializers.CharField()
    running = serializers.BooleanField()
    last_run = GhplSyncRunSerializer(allow_null=True)
    last_success = GhplSyncRunSerializer(allow_null=True)
    recent = GhplSyncRunSerializer(many=True)
    files = serializers.DictField(child=serializers.IntegerField())


class GhplCopyPairSerializer(serializers.Serializer):
    copy = serializers.UUIDField()
    keep = serializers.UUIDField()


class GhplCopyMergeSerializer(serializers.Serializer):
    pairs = GhplCopyPairSerializer(many=True, allow_empty=False)


class GhplCopyRefusalSerializer(serializers.Serializer):
    copy = serializers.UUIDField()
    reason = serializers.CharField()


class GhplCopyMergeResultSerializer(serializers.Serializer):
    merged = serializers.IntegerField()
    refused = GhplCopyRefusalSerializer(many=True)


class GhplSyncedFileSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    path = serializers.CharField()
    state = serializers.CharField()
    state_label = serializers.CharField(source="get_state_display")
    message = serializers.CharField()
    amm = serializers.UUIDField(source="amm_id", allow_null=True)
    document = serializers.UUIDField(source="document_id", allow_null=True)
    updated_at = serializers.DateTimeField()
