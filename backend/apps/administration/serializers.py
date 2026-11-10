from rest_framework import serializers

from apps.core.models import TrashEntry


class TrashEntrySerializer(serializers.ModelSerializer):
    deleted_by = serializers.SerializerMethodField()
    restored_by = serializers.SerializerMethodField()
    # Nombre de lignes parties avec l'élément (renouvellements, pièces, alertes…).
    rows = serializers.SerializerMethodField()

    class Meta:
        model = TrashEntry
        fields = [
            "id",
            "label",
            "kind",
            "model",
            "object_id",
            "country",
            "reason",
            "rows",
            "deleted_by",
            "deleted_at",
            "restored_by",
            "restored_at",
        ]

    @staticmethod
    def _person(user) -> str | None:
        return (user.full_name or user.email) if user else None

    def get_deleted_by(self, obj) -> str | None:
        return self._person(obj.deleted_by)

    def get_restored_by(self, obj) -> str | None:
        return self._person(obj.restored_by)

    def get_rows(self, obj) -> int:
        return len(obj.payload.get("objects", []))
