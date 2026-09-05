from rest_framework import serializers

from apps.accounts.models import User
from apps.amm.models import MarketingAuthorization

from .models import Alert, AlertRule


class AlertRuleSerializer(serializers.ModelSerializer):
    country_iso2 = serializers.CharField(source="country.iso2", read_only=True, default=None)
    roles = serializers.ListField(child=serializers.ChoiceField(choices=User.Role.choices))
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=AlertRule.Channel.choices)
    )

    class Meta:
        model = AlertRule
        fields = [
            "id",
            "code",
            "country",
            "country_iso2",
            "offset_days",
            "severity",
            "roles",
            "channels",
            "only_if_not_filed",
            "is_active",
        ]
        extra_kwargs = {"country": {"required": False, "allow_null": True, "default": None}}


class AlertSerializer(serializers.ModelSerializer):
    rule_code = serializers.CharField(source="rule.code", read_only=True)
    severity = serializers.ChoiceField(
        source="rule.severity", choices=AlertRule.Severity.choices, read_only=True
    )
    amm_id = serializers.UUIDField(source="amm.id", read_only=True)
    country_iso2 = serializers.CharField(source="amm.country.iso2", read_only=True)
    country_name = serializers.CharField(source="amm.country.name", read_only=True)
    product_name = serializers.CharField(source="amm.product.name", read_only=True)
    amm_status = serializers.ChoiceField(
        source="amm.status", choices=MarketingAuthorization.Status.choices, read_only=True
    )
    amm_urgency = serializers.ChoiceField(
        source="amm.urgency", choices=MarketingAuthorization.Urgency.choices, read_only=True
    )
    effective_end_date = serializers.DateField(source="amm.effective_end_date", read_only=True)
    assigned_to_email = serializers.EmailField(
        source="assigned_to.email", read_only=True, default=None
    )

    class Meta:
        model = Alert
        fields = [
            "id",
            "amm_id",
            "country_iso2",
            "country_name",
            "product_name",
            "amm_status",
            "amm_urgency",
            "effective_end_date",
            "rule",
            "rule_code",
            "severity",
            "due_date",
            "status",
            "assigned_to",
            "assigned_to_email",
            "triggered_at",
            "acknowledged_at",
            "resolved_at",
            "resolution",
            "comment",
        ]
        read_only_fields = fields


class AlertAssignSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


class AlertResolveSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)


class AlertAcknowledgeSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)
