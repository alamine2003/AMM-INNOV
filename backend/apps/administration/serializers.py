from rest_framework import serializers

from apps.core.models import ErrorEvent, TrashEntry


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


# --- Permissions ----------------------------------------------------------------------------


class PermissionRoleSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    editable = serializers.BooleanField()


class PermissionActionSerializer(serializers.Serializer):
    action = serializers.CharField()
    group = serializers.CharField()
    label = serializers.CharField()
    locked = serializers.BooleanField()
    defaults = serializers.ListField(child=serializers.CharField())
    roles = serializers.DictField(child=serializers.BooleanField())


class PermissionMatrixSerializer(serializers.Serializer):
    roles = PermissionRoleSerializer(many=True)
    actions = PermissionActionSerializer(many=True)


class PermissionGrantSerializer(serializers.Serializer):
    action = serializers.CharField()
    role = serializers.CharField()
    allowed = serializers.BooleanField()


class PermissionUpdateSerializer(serializers.Serializer):
    grants = PermissionGrantSerializer(many=True)


# --- Audit ----------------------------------------------------------------------------------


class AuditChangeSerializer(serializers.Serializer):
    field = serializers.CharField()
    old = serializers.CharField(allow_null=True)
    new = serializers.CharField(allow_null=True)


class AuditEventSerializer(serializers.Serializer):
    id = serializers.CharField()
    at = serializers.DateTimeField()
    action = serializers.ChoiceField(choices=["created", "updated", "login", "deleted", "restored"])
    action_label = serializers.CharField()
    user = serializers.CharField(allow_null=True)
    user_id = serializers.CharField(allow_null=True)
    model = serializers.CharField()
    type = serializers.CharField()
    object_id = serializers.CharField()
    label = serializers.CharField()
    country = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    changes = AuditChangeSerializer(many=True)
    # Lignes concernées : pour une suppression, l'élément et ce qui partait avec lui.
    rows = serializers.IntegerField()


class AuditPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = AuditEventSerializer(many=True)


class AuditOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class AuditPersonSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    active = serializers.BooleanField()


class AuditFiltersSerializer(serializers.Serializer):
    types = AuditOptionSerializer(many=True)
    actions = AuditOptionSerializer(many=True)
    people = AuditPersonSerializer(many=True)


# --- Journal des erreurs --------------------------------------------------------------------


class ErrorEventSerializer(serializers.ModelSerializer):
    last_user = serializers.SerializerMethodField()
    resolved_by = serializers.SerializerMethodField()
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = ErrorEvent
        fields = [
            "id",
            "source",
            "source_label",
            "kind",
            "message",
            "detail",
            "location",
            "version",
            "count",
            "first_seen",
            "last_seen",
            "last_user",
            "resolved_at",
            "resolved_by",
        ]

    def get_last_user(self, obj) -> str | None:
        return obj.last_user.full_name if obj.last_user else None

    def get_resolved_by(self, obj) -> str | None:
        return obj.resolved_by.full_name if obj.resolved_by else None


class ClientErrorSerializer(serializers.Serializer):
    """Erreur de l'interface : ce que le navigateur sait, rien de plus (ni données saisies)."""

    kind = serializers.CharField(max_length=120, required=False, allow_blank=True)
    message = serializers.CharField(max_length=500)
    stack = serializers.CharField(max_length=8000, required=False, allow_blank=True)
    path = serializers.CharField(max_length=300, required=False, allow_blank=True)
    version = serializers.CharField(max_length=20, required=False, allow_blank=True)
