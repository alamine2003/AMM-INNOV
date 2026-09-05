from rest_framework import serializers

from .models import ImportBatch, ImportRow


class ImportBatchSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )
    filename = serializers.SerializerMethodField()
    summary = serializers.DictField(read_only=True)

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
        ]
        read_only_fields = fields

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
