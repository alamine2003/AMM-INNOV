from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country

from .actions import missing_for_send, piece_types_for
from .models import (
    DepositActivity,
    DepositDossier,
    DepositEvent,
    DepositMessage,
    DepositPiece,
    DepositSample,
    PieceType,
)


def _name(user) -> str | None:
    return user.full_name if user else None


class PieceTypeSerializer(serializers.ModelSerializer):
    country = serializers.SlugRelatedField(
        slug_field="iso2", queryset=Country.objects.all(), allow_null=True, required=False
    )
    excluded_countries = serializers.SlugRelatedField(
        slug_field="iso2", queryset=Country.objects.all(), many=True, required=False
    )

    class Meta:
        model = PieceType
        fields = [
            "id",
            "label",
            "help_text",
            "required",
            "order",
            "country",
            "excluded_countries",
            "active",
        ]


class PieceTypeReadSerializer(PieceTypeSerializer):
    country = serializers.SlugRelatedField(slug_field="iso2", read_only=True, allow_null=True)
    excluded_countries = serializers.SlugRelatedField(slug_field="iso2", read_only=True, many=True)

    class Meta(PieceTypeSerializer.Meta):
        read_only_fields = PieceTypeSerializer.Meta.fields


class DepositPieceSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.SerializerMethodField()

    class Meta:
        model = DepositPiece
        fields = [
            "id",
            "piece_type",
            "label",
            "filename",
            "content_type",
            "size_bytes",
            "uploaded_by",
            "uploaded_at",
        ]
        read_only_fields = fields

    def get_uploaded_by(self, obj) -> str | None:
        return _name(obj.uploaded_by)


class DepositSampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepositSample
        fields = ["id", "batch_number", "manufactured_on", "expires_on", "quantity", "note"]
        read_only_fields = fields


class DepositEventSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    created_by = serializers.SerializerMethodField()
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = DepositEvent
        fields = [
            "id",
            "kind",
            "kind_label",
            "date",
            "note",
            "filename",
            "has_file",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj) -> str | None:
        return _name(obj.created_by)

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)


class DepositMessageSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    from_hq = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()

    class Meta:
        model = DepositMessage
        fields = ["id", "author", "from_hq", "mine", "body", "created_at"]
        read_only_fields = fields

    def get_author(self, obj) -> str | None:
        return _name(obj.author)

    def get_from_hq(self, obj) -> bool:
        return bool(obj.author and obj.author.is_global)

    def get_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and obj.author_id == request.user.pk)


class DepositActivitySerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = DepositActivity
        fields = ["id", "kind", "text", "user", "created_at"]
        read_only_fields = fields

    def get_user(self, obj) -> str | None:
        return _name(obj.user)


class DepositAmmSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")
    range_code = serializers.SerializerMethodField()
    country_iso2 = serializers.CharField(source="country.iso2")
    country_name = serializers.CharField(source="country.name")
    authority = serializers.CharField(source="country.authority")

    class Meta:
        model = MarketingAuthorization
        fields = [
            "id",
            "product_name",
            "range_code",
            "country_iso2",
            "country_name",
            "authority",
            "original_number",
            "status",
            "urgency",
            "effective_end_date",
            "ideal_filing_date",
            "agency_filing_deadline",
        ]
        read_only_fields = fields

    def get_range_code(self, obj) -> str | None:
        return obj.product.range.code if obj.product.range_id else None


class DepositRenewalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Renewal
        fields = ["id", "sequence", "workflow_status", "filing_date", "decision_date", "number"]
        read_only_fields = fields


class DepositSummarySerializer(serializers.ModelSerializer):
    stage = serializers.ChoiceField(choices=DepositDossier.Stage.choices, read_only=True)
    stage_label = serializers.SerializerMethodField()
    amm = DepositAmmSerializer(source="renewal.amm", read_only=True)
    renewal = DepositRenewalSerializer(read_only=True)
    pieces_done = serializers.SerializerMethodField()
    pieces_required = serializers.SerializerMethodField()
    samples_count = serializers.SerializerMethodField()
    sent_by = serializers.SerializerMethodField()
    messages_count = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()
    events_count = serializers.SerializerMethodField()

    class Meta:
        model = DepositDossier
        fields = [
            "id",
            "stage",
            "stage_label",
            "amm",
            "renewal",
            "pieces_done",
            "pieces_required",
            "samples_required",
            "samples_count",
            "sent_at",
            "sent_by",
            "deposited_at",
            "events_count",
            "messages_count",
            "last_message_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _types(self, obj):
        cache = self.context.setdefault("piece_types", {})
        country = obj.renewal.amm.country
        if country.pk not in cache:
            cache[country.pk] = piece_types_for(country)
        return cache[country.pk]

    def get_stage_label(self, obj) -> str:
        return DepositDossier.Stage(obj.stage).label

    def get_pieces_required(self, obj) -> int:
        return sum(1 for piece_type in self._types(obj) if piece_type.required)

    def get_pieces_done(self, obj) -> int:
        present = {piece.piece_type_id for piece in obj.pieces.all()}
        return sum(1 for t in self._types(obj) if t.required and t.pk in present)

    def get_samples_count(self, obj) -> int:
        return len(obj.samples.all())

    def get_sent_by(self, obj) -> str | None:
        return _name(obj.sent_by)

    def get_messages_count(self, obj) -> int:
        return len(obj.messages.all())

    def get_last_message_at(self, obj) -> str | None:
        messages = list(obj.messages.all())
        return messages[-1].created_at.isoformat() if messages else None

    def get_events_count(self, obj) -> int:
        return len(obj.events.all())


class ChecklistItemSerializer(serializers.Serializer):
    piece_type = PieceTypeReadSerializer()
    files = DepositPieceSerializer(many=True)
    done = serializers.BooleanField()


class AttestationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    document_date = serializers.DateField()
    filename = serializers.CharField()


class DownloadSerializer(serializers.Serializer):
    user = serializers.CharField(allow_null=True)
    at = serializers.DateTimeField()


class DepositPermissionsSerializer(serializers.Serializer):
    manage = serializers.BooleanField(help_text="Siège : monter, envoyer, abandonner")
    deposit = serializers.BooleanField(help_text="Enregistrer le dépôt et l'attestation")
    follow = serializers.BooleanField(help_text="Noter commissions et notifications")
    decide = serializers.BooleanField(help_text="Enregistrer la décision")


class DepositDetailSerializer(DepositSummarySerializer):
    send_note = serializers.CharField(read_only=True)
    checklist = serializers.SerializerMethodField()
    other_pieces = serializers.SerializerMethodField()
    samples = DepositSampleSerializer(many=True, read_only=True)
    events = DepositEventSerializer(many=True, read_only=True)
    messages = DepositMessageSerializer(many=True, read_only=True)
    activities = serializers.SerializerMethodField()
    missing = serializers.SerializerMethodField()
    attestation = serializers.SerializerMethodField()
    downloads = serializers.SerializerMethodField()
    can = serializers.SerializerMethodField()

    class Meta(DepositSummarySerializer.Meta):
        fields = DepositSummarySerializer.Meta.fields + [
            "send_note",
            "checklist",
            "other_pieces",
            "samples",
            "events",
            "messages",
            "activities",
            "missing",
            "attestation",
            "downloads",
            "can",
        ]
        read_only_fields = fields

    @extend_schema_field(ChecklistItemSerializer(many=True))
    def get_checklist(self, obj):
        pieces = list(obj.pieces.all())
        items = [
            {
                "piece_type": piece_type,
                "files": [piece for piece in pieces if piece.piece_type_id == piece_type.pk],
            }
            for piece_type in self._types(obj)
        ]
        for item in items:
            item["done"] = bool(item["files"])
        return ChecklistItemSerializer(items, many=True, context=self.context).data

    @extend_schema_field(DepositPieceSerializer(many=True))
    def get_other_pieces(self, obj):
        known = {piece_type.pk for piece_type in self._types(obj)}
        others = [piece for piece in obj.pieces.all() if piece.piece_type_id not in known]
        return DepositPieceSerializer(others, many=True).data

    @extend_schema_field(DepositActivitySerializer(many=True))
    def get_activities(self, obj):
        return DepositActivitySerializer(
            obj.activities.select_related("user")[:100], many=True
        ).data

    def get_missing(self, obj) -> list[str]:
        return missing_for_send(obj)

    @extend_schema_field(AttestationSerializer(allow_null=True))
    def get_attestation(self, obj):
        document = obj.attestation
        if document is None or document.archived_at is not None:
            return None
        return {
            "id": document.pk,
            "document_date": document.document_date,
            "filename": document.export_filename(),
        }

    @extend_schema_field(DownloadSerializer(many=True))
    def get_downloads(self, obj):
        rows = obj.activities.filter(kind=DepositActivity.Kind.TELECHARGEMENT).select_related(
            "user"
        )
        return [{"user": _name(row.user), "at": row.created_at} for row in rows]

    @extend_schema_field(DepositPermissionsSerializer)
    def get_can(self, obj):
        user = self.context["request"].user
        status = obj.renewal.workflow_status
        closed = status in Renewal.TERMINAL_STATUSES
        pending = status in Renewal.PENDING_STATUSES
        return {
            "manage": user.is_global and not closed,
            "deposit": not closed and (bool(obj.sent_at) or user.is_global),
            "follow": pending,
            "decide": pending,
        }


class SuggestionSerializer(DepositAmmSerializer):
    renewal_status = serializers.ChoiceField(
        choices=Renewal.WorkflowStatus.choices, allow_null=True, read_only=True
    )

    class Meta(DepositAmmSerializer.Meta):
        fields = DepositAmmSerializer.Meta.fields + ["renewal_status"]
        read_only_fields = fields


class OpenDossierSerializer(serializers.Serializer):
    amm = serializers.UUIDField()


class PieceUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    piece_type = serializers.UUIDField(required=False, allow_null=True)
    label = serializers.CharField(required=False, allow_blank=True, max_length=200)


class SampleInputSerializer(serializers.Serializer):
    batch_number = serializers.CharField(max_length=100)
    manufactured_on = serializers.DateField()
    expires_on = serializers.DateField()
    quantity = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class SamplesRequiredSerializer(serializers.Serializer):
    required = serializers.BooleanField()


class SendSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class DepositInputSerializer(serializers.Serializer):
    filing_date = serializers.DateField()
    file = serializers.FileField()


class EventInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=DepositEvent.Kind.choices)
    date = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(required=False)


class DecisionInputSerializer(serializers.Serializer):
    result = serializers.ChoiceField(
        choices=[
            (Renewal.WorkflowStatus.OBTENU, "Obtenu"),
            (Renewal.WorkflowStatus.REJETE, "Rejeté"),
        ]
    )
    decision_date = serializers.DateField()
    number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    start_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(required=False)


class AbandonSerializer(serializers.Serializer):
    reason = serializers.CharField()


class MessageInputSerializer(serializers.Serializer):
    body = serializers.CharField()
