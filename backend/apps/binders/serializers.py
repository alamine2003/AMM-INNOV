from rest_framework import serializers

from apps.amm.models import MarketingAuthorization
from apps.catalog.models import ProductRange
from apps.documents.models import Document

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


class AddPageInputSerializer(serializers.Serializer):
    product_name = serializers.CharField(max_length=255)
    # Gamme : imposée par le classeur au siège, à choisir dans un classeur de pays.
    range_code = serializers.ChoiceField(
        choices=ProductRange.Code.choices, required=False, allow_null=True, default=None
    )
    original_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    original_start_date = serializers.DateField(required=False, allow_null=True, default=None)
    # « Page en trop » transformée en vraie page : elle disparaît de la liste.
    extra_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class PageScanInputSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(), min_length=1, max_length=10, allow_empty=False
    )


# Une période de la chronologie : « origin » (AMM d'origine) ou l'identifiant d'un renouvellement.
PERIOD_HELP = "« origin » pour l'AMM d'origine, sinon l'identifiant du renouvellement."


class PeriodInputSerializer(serializers.Serializer):
    """Correction d'une période : seuls les champs envoyés changent ; une date vide s'efface."""

    number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)


class PeriodDeleteInputSerializer(serializers.Serializer):
    # Absent : les pièces du renouvellement annulé sont archivées, comme sur la fiche AMM.
    move_to = serializers.CharField(required=False, allow_null=True, help_text=PERIOD_HELP)


class DocumentEditInputSerializer(serializers.Serializer):
    period = serializers.CharField(required=False, help_text=PERIOD_HELP)
    document_date = serializers.DateField(required=False)
    kind = serializers.ChoiceField(choices=Document.Kind.choices, required=False)


class DocumentAddInputSerializer(serializers.Serializer):
    file = serializers.FileField()
    kind = serializers.ChoiceField(choices=Document.Kind.choices, default=Document.Kind.AMM)
    document_date = serializers.DateField()
    period = serializers.CharField(default="origin", help_text=PERIOD_HELP)


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
    # Faux : la décision en vigueur n'est pas scannée, la vignette montre une décision antérieure.
    is_current = serializers.BooleanField(default=True)


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


class PendingRenewalSerializer(serializers.Serializer):
    workflow_status = serializers.CharField()
    workflow_label = serializers.CharField()
    filing_date = serializers.DateField(allow_null=True)


class ChangeSinceCheckSerializer(serializers.Serializer):
    slot = serializers.ChoiceField(choices=SLOTS)
    field = serializers.ChoiceField(choices=PAGE_FIELDS)
    checked = serializers.JSONField(allow_null=True)
    now = serializers.JSONField(allow_null=True)


class ExcelTraceSerializer(serializers.Serializer):
    batch_id = serializers.UUIDField()
    date = serializers.DateTimeField()
    sheet = serializers.CharField()
    row = serializers.IntegerField()
    outcome = serializers.CharField()


class DossierTraceSerializer(serializers.Serializer):
    batch_id = serializers.UUIDField()
    date = serializers.DateTimeField()
    status = serializers.CharField()
    folder = serializers.CharField()
    auto_applied = serializers.BooleanField()


class TraceSerializer(serializers.Serializer):
    excel = ExcelTraceSerializer(allow_null=True)
    dossier = DossierTraceSerializer(allow_null=True)


class ChronologyDocumentSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    kind = serializers.CharField()
    kind_label = serializers.CharField()
    document_date = serializers.DateField()
    title = serializers.CharField(allow_blank=True)
    page_count = serializers.IntegerField(allow_null=True)


class ChronologyIssueSerializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=["no_scan", "no_date", "no_number", "no_receipt", "gap"])
    message = serializers.CharField()


class ChronologyEntrySerializer(serializers.Serializer):
    """Une période de l'AMM (de la plus récente à l'origine), ou une interruption de validité."""

    kind = serializers.ChoiceField(choices=["pending", "renewal", "closed", "origin", "gap"])
    label = serializers.CharField()
    renewal_id = serializers.UUIDField(allow_null=True, required=False)
    sequence = serializers.IntegerField(required=False)
    workflow_status = serializers.CharField(allow_null=True, required=False)
    workflow_label = serializers.CharField(allow_null=True, required=False)
    number = serializers.CharField(allow_blank=True, required=False)
    start_date = serializers.DateField(allow_null=True)
    end_date = serializers.DateField(allow_null=True)
    filing_date = serializers.DateField(allow_null=True, required=False)
    decisions = ChronologyDocumentSerializer(many=True, required=False)
    others = ChronologyDocumentSerializer(many=True, required=False)
    issues = ChronologyIssueSerializer(many=True)


class PageSerializer(serializers.Serializer):
    amm_id = serializers.UUIDField()
    page = serializers.IntegerField()
    section_page = serializers.IntegerField()
    product_name = serializers.CharField()
    range_code = serializers.CharField(allow_blank=True)
    range_label = serializers.CharField()
    original = SlotSerializer()
    renewal = RenewalSlotSerializer(allow_null=True)
    pending_renewal = PendingRenewalSerializer(allow_null=True)
    status = serializers.ChoiceField(choices=MarketingAuthorization.Status.choices)
    status_label = serializers.CharField()
    dossier_state = serializers.ChoiceField(choices=MarketingAuthorization.DossierState.choices)
    scan = ScanSerializer(allow_null=True)
    decision_count = serializers.IntegerField()
    chronology = ChronologyEntrySerializer(many=True)
    discrepancies = DiscrepancySerializer(many=True)
    check = CheckSerializer(allow_null=True)
    changed_since_check = ChangeSinceCheckSerializer(many=True)
    changed_by = serializers.CharField(allow_null=True)
    trace = TraceSerializer()
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
    stale = serializers.IntegerField()


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
    # Qui a ce classeur ouvert en ce moment (dernières 2 minutes) : il est « sorti » de l'étagère.
    readers = serializers.ListField(child=serializers.CharField())


class BinderDetailSerializer(BinderSummarySerializer):
    sections = SectionSerializer(many=True)
    extra_pages = ExtraPageSerializer(many=True)
    resume_page = serializers.IntegerField()
    # Pages modifiées depuis leur vérification (dashboard, import Excel ou de dossier).
    stale = serializers.IntegerField()


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


class AddPageResultSerializer(serializers.Serializer):
    amm_id = serializers.UUIDField()
    binder_key = serializers.CharField()
    product_created = serializers.BooleanField()
    binder = BinderDetailSerializer()


class PageScanResultSerializer(serializers.Serializer):
    batch_id = serializers.UUIDField()
    status = serializers.CharField()


class BinderLocationSerializer(serializers.Serializer):
    binder_key = serializers.CharField()
    title = serializers.CharField()
    country_name = serializers.CharField()
    page = serializers.IntegerField()
    total = serializers.IntegerField()
    check = CheckSerializer(allow_null=True)
    stale = serializers.BooleanField()
