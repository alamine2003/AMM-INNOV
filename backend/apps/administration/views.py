"""Administration : corbeille, audit et traçabilité, permissions."""

import uuid
from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import ActionGrant, User
from apps.accounts.permissions import ensure_can
from apps.accounts.roles import (
    ACTION_ROLES,
    ALL_ROLES,
    CONFIGURABLE_ROLES,
    LABELS,
    LOCKED,
    Action,
    matrix,
)
from apps.core import errors as error_journal
from apps.core.models import ErrorEvent, TrashEntry
from apps.core.trash import restore

from . import audit
from .serializers import (
    AuditFiltersSerializer,
    AuditPageSerializer,
    ClientErrorSerializer,
    ErrorEventSerializer,
    PermissionMatrixSerializer,
    PermissionUpdateSerializer,
    TrashEntrySerializer,
)


class TrashViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """La corbeille n'est jamais vidée : une entrée restaurée reste, marquée restaurée."""

    serializer_class = TrashEntrySerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["label", "kind", "reason"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        ensure_can(request.user, Action.TRASH_RESTORE)

    def get_queryset(self):
        queryset = TrashEntry.objects.select_related("deleted_by", "restored_by")
        user = self.request.user
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        if not user.is_global:  # droit accordé à un rôle pays : ses pays seulement
            queryset = queryset.filter(country__in=user.countries.values_list("iso2", flat=True))
        state = self.request.query_params.get("state")
        if state == "deleted":
            queryset = queryset.filter(restored_at__isnull=True)
        elif state == "restored":
            queryset = queryset.filter(restored_at__isnull=False)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "state", str, required=False, enum=["deleted", "restored"], description="Filtre"
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=TrashEntrySerializer)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        """Remet l'élément et tout ce qui partait avec lui, à l'identique."""
        entry = self.get_object()
        try:
            restore(entry, user=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages[0]}) from exc
        entry.refresh_from_db()
        return Response(TrashEntrySerializer(entry).data)


# --- Permissions ----------------------------------------------------------------------------


def permission_matrix() -> dict:
    values = matrix()
    return {
        "roles": [
            {"value": role.value, "label": role.label, "editable": role in CONFIGURABLE_ROLES}
            for role in ALL_ROLES
        ],
        "actions": [
            {
                "action": item.value,
                "group": LABELS[item][0],
                "label": LABELS[item][1],
                "locked": item in LOCKED,
                "defaults": [str(role) for role in ACTION_ROLES[item]],
                "roles": {str(role): values[(item, role)] for role in ALL_ROLES},
            }
            for item in Action
        ],
    }


class PermissionsView(APIView):
    """Qui peut faire quoi : rôles × actions. Le CEO seul les consulte et les règle.

    Le CEO garde toujours tous les droits et le droit de régler les permissions ne se règle pas :
    personne ne peut s'enfermer dehors. Chaque changement est gardé dans l'historique (audit).
    """

    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        ensure_can(request.user, Action.PERMISSIONS_MANAGE)

    @extend_schema(responses=PermissionMatrixSerializer)
    def get(self, request):
        return Response(permission_matrix())

    @extend_schema(request=PermissionUpdateSerializer, responses=PermissionMatrixSerializer)
    def put(self, request):
        serializer = PermissionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        known = {item.value: item for item in Action}
        errors = []
        for grant in serializer.validated_data["grants"]:
            item = known.get(grant["action"])
            if item is None:
                errors.append(f"Action inconnue : {grant['action']}.")
            elif item in LOCKED:
                errors.append(f"« {LABELS[item][1]} » ne se règle pas.")
            elif grant["role"] not in CONFIGURABLE_ROLES:
                errors.append("Seuls les droits du siège et des pays se règlent.")
        if errors:
            raise serializers.ValidationError({"detail": " ".join(sorted(set(errors)))})
        current = matrix()
        with transaction.atomic():
            for grant in serializer.validated_data["grants"]:
                item = known[grant["action"]]
                if current[(item, grant["role"])] == grant["allowed"]:
                    continue
                row = ActionGrant.objects.filter(action=item.value, role=grant["role"]).first()
                if row is None:
                    row = ActionGrant(action=item.value, role=grant["role"])
                row.allowed = grant["allowed"]
                row.updated_by = request.user
                row._history_user = request.user
                row.save()
        return Response(permission_matrix())


# --- Audit ----------------------------------------------------------------------------------

AUDIT_PAGE_SIZE = 50
AUDIT_MAX_PAGE = 200


def _date_param(request, name):
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise serializers.ValidationError({name: "Date attendue au format AAAA-MM-JJ."}) from exc


class AuditView(APIView):
    """Qui a fait quoi, quand : créations, modifications, connexions, mises à la corbeille et
    restaurations, dans toute l'application, du plus récent au plus ancien."""

    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        ensure_can(request.user, Action.AUDIT_VIEW)

    @extend_schema(
        parameters=[
            OpenApiParameter("page", int, required=False),
            OpenApiParameter("user", str, required=False, description="Identifiant de la personne"),
            OpenApiParameter("model", str, required=False, description="Type (ex. amm.Renewal)"),
            OpenApiParameter(
                "action",
                str,
                required=False,
                enum=["created", "updated", "login", "deleted", "restored"],
            ),
            OpenApiParameter("country", str, required=False, description="Code ISO2"),
            OpenApiParameter("since", date, required=False),
            OpenApiParameter("until", date, required=False),
        ],
        responses=AuditPageSerializer,
    )
    def get(self, request):
        params = request.query_params
        try:
            page = max(1, min(int(params.get("page", 1)), AUDIT_MAX_PAGE))
        except ValueError:
            page = 1
        user = request.user
        filters = audit.Filters(
            user=params.get("user") or None,
            model=params.get("model") or None,
            action=params.get("action") or None,
            country=params.get("country") or None,
            since=_date_param(request, "since"),
            until=_date_param(request, "until"),
            scope=None if user.is_global else list(user.countries.values_list("iso2", flat=True)),
        )
        if filters.user and not (
            _is_uuid(filters.user) and User.objects.filter(pk=filters.user).exists()
        ):
            raise serializers.ValidationError({"user": "Personne inconnue."})
        count, results = audit.events(filters, page, AUDIT_PAGE_SIZE)
        pages = max(1, min(-(-count // AUDIT_PAGE_SIZE), AUDIT_MAX_PAGE))
        return Response(
            AuditPageSerializer(
                {"count": count, "page": page, "pages": pages, "results": results}
            ).data
        )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


class AuditFiltersView(APIView):
    """Valeurs proposées dans les filtres de l'audit."""

    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        ensure_can(request.user, Action.AUDIT_VIEW)

    @extend_schema(responses=AuditFiltersSerializer)
    def get(self, request):
        return Response(
            AuditFiltersSerializer(
                {
                    "types": audit.model_types(),
                    "actions": [
                        {"value": key, "label": label} for key, label in audit.ACTION_LABELS.items()
                    ],
                    "people": audit.people(),
                }
            ).data
        )


# --- Journal des erreurs --------------------------------------------------------------------


class ErrorEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Erreurs de production (serveur, tâches de fond, interface), les plus récentes d'abord."""

    serializer_class = ErrorEventSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["kind", "message", "location"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        ensure_can(request.user, Action.ERRORS_VIEW)

    def get_queryset(self):
        queryset = ErrorEvent.objects.select_related("last_user", "resolved_by")
        state = self.request.query_params.get("state")
        if state == "open":
            queryset = queryset.filter(resolved_at__isnull=True)
        elif state == "resolved":
            queryset = queryset.filter(resolved_at__isnull=False)
        source = self.request.query_params.get("source")
        if source:
            queryset = queryset.filter(source=source)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("state", str, required=False, enum=["open", "resolved"]),
            OpenApiParameter(
                "source", str, required=False, enum=[c for c, _ in ErrorEvent.Source.choices]
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=ErrorEventSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Marque l'erreur résolue ; si elle revient, elle est rouverte automatiquement."""
        event = self.get_object()
        event.resolved_at = timezone.now()
        event.resolved_by = request.user
        event.save(update_fields=["resolved_at", "resolved_by"])
        return Response(ErrorEventSerializer(event).data)


class ClientErrorThrottle(UserRateThrottle):
    scope = "client_errors"
    rate = "20/min"  # une page qui boucle sur une erreur ne remplit pas le journal


class ClientErrorView(APIView):
    """L'interface signale une erreur d'affichage (tout utilisateur connecté, débit limité)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ClientErrorThrottle]

    @extend_schema(request=ClientErrorSerializer, responses={204: None})
    def post(self, request):
        serializer = ClientErrorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        error_journal.record(
            source=ErrorEvent.Source.INTERFACE,
            kind=data.get("kind") or "Error",
            message=data["message"],
            detail=data.get("stack", ""),
            location=data.get("path", ""),
            user=request.user,
            version=data.get("version", ""),
        )
        return Response(status=204)
