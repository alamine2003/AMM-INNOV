from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    alert_id = serializers.UUIDField(source="alert.id", read_only=True, default=None)
    amm_id = serializers.UUIDField(source="alert.amm_id", read_only=True, default=None)
    severity = serializers.CharField(source="alert.rule.severity", read_only=True, default=None)
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "alert_id",
            "amm_id",
            "severity",
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
