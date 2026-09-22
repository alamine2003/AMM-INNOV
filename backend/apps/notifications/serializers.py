from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    alert_id = serializers.UUIDField(source="alert.id", read_only=True, default=None)
    amm_id = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "alert_id",
            "amm_id",
            "severity",
            "reminder_date",
            "channel",
            "title",
            "body",
            "link",
            "created_at",
            "sent_at",
            "read_at",
            "is_read",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_amm_id(self, obj):
        if obj.amm_id:
            return str(obj.amm_id)
        return str(obj.alert.amm_id) if obj.alert_id else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_severity(self, obj):
        if obj.alert_id:
            return obj.alert.rule.severity
        # Rappel quotidien « À renouveler » : même niveau qu'un avertissement.
        return "WARNING" if obj.reminder_date else None
