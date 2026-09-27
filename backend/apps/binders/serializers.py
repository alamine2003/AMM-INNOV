from rest_framework import serializers

from apps.amm.models import MarketingAuthorization

from .models import BinderCheck, BinderExport

SLOTS = [("original", "AMM d'origine"), ("renewal", "Dernier renouvellement")]
PAGE_FIELDS = [("number", "N° d'AMM"), ("start_date", "Date de début"), ("end_date", "Date de fin")]


# --- Entrées -------------------------------------------------------------------------------


class CorrectionInputSerializer(serializers.Serializer):
    slot = serializers.ChoiceField(choices=SLOTS)
    field = serializers.ChoiceField(choices=PAGE_FIELDS)
    # N° d'AMM, ou date au format AAAA-MM-JJ ; vide pour effacer une date.
    value = serializers.CharField(allow_blank=True, allow_null=True, max_length=100)

    def validate(self, attrs):
        if attrs["field"] != "number":
            raw = attrs["value"]
            attrs["value"] = (
                serializers.DateField().to_internal_value(raw) if raw not in (None, "") else None
            )
        return attrs


class CheckInputSerializer(serializers.Serializer):
    amm = serializers.UUIDField()
    result = serializers.ChoiceField(choices=BinderCheck.Result.choices)
    corrections = CorrectionInputSerializer(many=True, required=False, default=list)
    note = serializers.CharField(allow_blank=True, required=False, default="")


class UncheckInputSerializer(serializers.Serializer):
    amm = serializers.UUIDField()


class ExtraPageInputSerializer(serializers.Serializer):
    product_name = serializers.CharField(max_length=255)
    note = serializers.CharField(allow_blank=True, required=False, default="")


# --- Sorties -------------------------------------------------------------------------------


class SlotSerializer(serializers.Serializer):
    number = serializers.CharField(allow_blank=True)
    start_date = serializers.DateField(allow_null=True)
    end_date = serializers.DateField(allow_null=True)


class RenewalSlotSerializer(SlotSerializer):
    id = serializers.UUIDField()
    sequence = serializers.IntegerField()


class ScanSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    document_date = serializers.DateField()
    page_count = serializers.IntegerField(allow_null=True)


class DiscrepancySerializer(serializers.Serializer):
    slot = serializers.ChoiceField(choices=SLOTS)
    field = serializers.ChoiceField(choices=PAGE_FIELDS)
    recorded = serializers.JSONField(allow_null=True)
    scan = serializers.JSONField(allow_null=True)
    message = serializers.CharField()


class CorrectionSerializer(serializers.Serializer):
    slot = serializers.ChoiceField(choices=SLOTS)
    field = serializers.ChoiceField(choices=PAGE_FIELDS)
    old = serializers.JSONField(allow_null=True)
    new = serializers.JSONField(allow_null=True)


class CheckSerializer(serializers.Serializer):
    result = serializers.ChoiceField(choices=BinderCheck.Result.choices)
    corrections = CorrectionSerializer(many=True)
    note = serializers.CharField(allow_blank=True)
    checked_by = serializers.CharField(allow_null=True)
    checked_at = serializers.DateTimeField()


class PageSerializer(serializers.Serializer):
    amm_id = serializers.UUIDField()
    page = serializers.IntegerField()
    section_page = serializers.IntegerField()
    product_name = serializers.CharField()
    range_code = serializers.CharField(allow_blank=True)
    range_label = serializers.CharField()
    original = SlotSerializer()
    renewal = RenewalSlotSerializer(allow_null=True)
    status = serializers.ChoiceField(choices=MarketingAuthorization.Status.choices)
    status_label = serializers.CharField()
    dossier_state = serializers.ChoiceField(choices=MarketingAuthorization.DossierState.choices)
    scan = ScanSerializer(allow_null=True)
    discrepancies = DiscrepancySerializer(many=True)
    check = CheckSerializer(allow_null=True)
    to_scan = serializers.BooleanField()


class CountsMixin(serializers.Serializer):
    total = serializers.IntegerField()
    checked = serializers.IntegerField()
    conformes = serializers.IntegerField()
    corrected = serializers.IntegerField()
    absent = serializers.IntegerField()
    to_scan = serializers.IntegerField()


class SectionSummarySerializer(CountsMixin):
    code = serializers.CharField(allow_blank=True)
    label = serializers.CharField()
    color = serializers.CharField()


class SectionSerializer(SectionSummarySerializer):
    pages = PageSerializer(many=True)


class ExtraPageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    product_name = serializers.CharField()
    note = serializers.CharField(allow_blank=True)
    created_by = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class BinderSummarySerializer(CountsMixin):
    key = serializers.CharField()
    title = serializers.CharField()
    country_iso2 = serializers.CharField()
    country_name = serializers.CharField()
    is_headquarters = serializers.BooleanField()
    sections = SectionSummarySerializer(many=True)
    extras = serializers.IntegerField()
    last_checked_at = serializers.DateTimeField(allow_null=True)
    last_checked_by = serializers.CharField(allow_null=True)


class BinderDetailSerializer(BinderSummarySerializer):
    sections = SectionSerializer(many=True)
    extra_pages = ExtraPageSerializer(many=True)
    resume_page = serializers.IntegerField()


class BinderExportSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(
        source="created_by.full_name", default=None, allow_null=True, read_only=True
    )
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = BinderExport
        fields = [
            "id",
            "binder_key",
            "status",
            "progress_done",
            "progress_total",
            "size_bytes",
            "page_count",
            "decisions",
            "unavailable",
            "without_scan",
            "error",
            "created_by",
            "created_at",
            "started_at",
            "finished_at",
            "has_file",
        ]
        read_only_fields = fields

    def get_has_file(self, obj) -> bool:
        return bool(obj.file) and obj.status == BinderExport.Status.READY
