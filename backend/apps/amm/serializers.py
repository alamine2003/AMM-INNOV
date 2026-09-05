from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.permissions import ensure_country_in_scope
from apps.catalog.models import Country

from .models import MarketingAuthorization, Renewal
from .services import workflow


class RenewalSerializer(serializers.ModelSerializer):
    allowed_transitions = serializers.SerializerMethodField()
    amm_id = serializers.UUIDField(source="amm.id", read_only=True)

    class Meta:
        model = Renewal
        fields = [
            "id",
            "amm_id",
            "sequence",
            "workflow_status",
            "filing_date",
            "decision_date",
            "number",
            "start_date",
            "end_date",
            "end_date_manual",
            "notes",
            "allowed_transitions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "sequence", "created_at", "updated_at"]

    def get_allowed_transitions(self, obj) -> list[str]:
        return sorted(workflow.allowed_transitions(obj))

    def validate(self, attrs):
        status = attrs.get("workflow_status", getattr(self.instance, "workflow_status", None))
        if status:
            merged = {**(self.instance.__dict__ if self.instance else {}), **attrs}
            missing = [
                name
                for name in workflow.REQUIRED_FIELDS.get(status, ())
                if merged.get(name) in (None, "")
            ]
            if missing:
                raise serializers.ValidationError(
                    {name: f"Champ requis pour le statut {status}." for name in missing}
                )
        if "end_date" in attrs and attrs["end_date"] is not None and "end_date_manual" not in attrs:
            attrs["end_date_manual"] = True
        return attrs

    def create(self, validated_data):
        amm = validated_data["amm"]
        if amm.renewals.filter(workflow_status__in=Renewal.OPEN_STATUSES).exists():
            raise serializers.ValidationError(
                {"detail": "Un renouvellement est déjà en cours pour cette AMM."}
            )
        return super().create(validated_data)


class RenewalTransitionSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=Renewal.WorkflowStatus.choices)
    filing_date = serializers.DateField(required=False, allow_null=True)
    decision_date = serializers.DateField(required=False, allow_null=True)
    number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class AmmListSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    range_code = serializers.CharField(source="product.range.code", read_only=True, default=None)
    range_label = serializers.CharField(source="product.range.label", read_only=True, default=None)
    country_iso2 = serializers.CharField(source="country.iso2", read_only=True)
    country_name = serializers.CharField(source="country.name", read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True, default=None)
    has_current_scan = serializers.BooleanField(read_only=True, default=False)
    days_remaining = serializers.SerializerMethodField()
    last_renewal = serializers.SerializerMethodField()

    class Meta:
        model = MarketingAuthorization
        fields = [
            "id",
            "product",
            "product_name",
            "range_code",
            "range_label",
            "country",
            "country_iso2",
            "country_name",
            "original_number",
            "original_start_date",
            "original_end_date",
            "original_end_date_manual",
            "status",
            "urgency",
            "effective_end_date",
            "filing_deadline",
            "days_remaining",
            "dossier_state",
            "notes",
            "owner",
            "owner_email",
            "has_current_scan",
            "last_renewal",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "urgency",
            "effective_end_date",
            "filing_deadline",
            "created_at",
            "updated_at",
        ]

    def get_days_remaining(self, obj) -> int | None:
        from apps.core.dates import today

        if obj.effective_end_date is None:
            return None
        return (obj.effective_end_date - today()).days

    def get_last_renewal(self, obj):
        renewals = list(obj.renewals.all())
        if not renewals:
            return None
        last = max(renewals, key=lambda r: r.sequence)
        return {
            "id": str(last.id),
            "sequence": last.sequence,
            "workflow_status": last.workflow_status,
            "number": last.number,
            "start_date": last.start_date,
            "end_date": last.end_date,
            "filing_date": last.filing_date,
        }

    def validate(self, attrs):
        request = self.context.get("request")
        country = attrs.get("country") or (self.instance.country if self.instance else None)
        if request is not None and country is not None:
            ensure_country_in_scope(request.user, country)
        if (
            "original_end_date" in attrs
            and attrs["original_end_date"] is not None
            and "original_end_date_manual" not in attrs
            # Le formulaire renvoie toujours la date de fin : ne la considérer comme saisie
            # manuellement que si elle change réellement (sinon une simple note posait le drapeau).
            and (
                self.instance is None
                or attrs["original_end_date"] != self.instance.original_end_date
            )
        ):
            attrs["original_end_date_manual"] = True
        return attrs

    def validate_country(self, value: Country) -> Country:
        return value


class AmmDetailSerializer(AmmListSerializer):
    renewals = RenewalSerializer(many=True, read_only=True)
    pending_renewal_id = serializers.SerializerMethodField()

    class Meta(AmmListSerializer.Meta):
        fields = AmmListSerializer.Meta.fields + ["renewals", "pending_renewal_id"]

    def get_pending_renewal_id(self, obj) -> str | None:
        pending = [r for r in obj.renewals.all() if r.is_pending]
        return str(max(pending, key=lambda r: r.sequence).id) if pending else None


class HistoryChangeSerializer(serializers.Serializer):
    field = serializers.CharField()
    old = serializers.CharField(allow_null=True)
    new = serializers.CharField(allow_null=True)


class HistoryEntrySerializer(serializers.Serializer):
    date = serializers.DateTimeField()
    user_email = serializers.EmailField(allow_null=True)
    type = serializers.CharField()
    model = serializers.CharField()
    object_id = serializers.CharField()
    changes = HistoryChangeSerializer(many=True)


def django_to_drf_validation_error(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "message_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError(exc.messages)
