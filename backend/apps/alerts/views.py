from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import GLOBAL_ROLES, CountryScopedQuerysetMixin, RolePermission

from .filters import AlertFilter
from .models import Alert, AlertRule
from .serializers import (
    AlertAcknowledgeSerializer,
    AlertAssignSerializer,
    AlertResolveSerializer,
    AlertRuleSerializer,
    AlertSerializer,
)


class AlertViewSet(
    CountryScopedQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Alert.objects.select_related(
        "rule", "amm", "amm__country", "amm__product", "assigned_to"
    )
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    filterset_class = AlertFilter
    ordering_fields = ["due_date", "triggered_at", "status", "rule__severity"]
    search_fields = ["amm__product__name", "amm__original_number"]
    country_lookup = "amm__country"

    def _save(self, alert: Alert, fields: list[str]):
        alert._history_user = self.request.user
        alert.save(update_fields=fields)
        return Response(AlertSerializer(alert).data)

    @extend_schema(request=AlertAcknowledgeSerializer, responses=AlertSerializer)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        serializer = AlertAcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if alert.status == Alert.Status.OPEN:
            alert.status = Alert.Status.ACKNOWLEDGED
            alert.acknowledged_at = timezone.now()
        if serializer.validated_data.get("comment"):
            alert.comment = serializer.validated_data["comment"]
        return self._save(alert, ["status", "acknowledged_at", "comment"])

    @extend_schema(request=AlertAssignSerializer, responses=AlertSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        alert = self.get_object()
        serializer = AlertAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_object_or_404(User, pk=serializer.validated_data["user_id"], is_active=True)
        alert.assigned_to = user
        return self._save(alert, ["assigned_to"])

    @extend_schema(request=AlertResolveSerializer, responses=AlertSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        serializer = AlertResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert.status = Alert.Status.RESOLVED
        alert.resolution = Alert.Resolution.MANUAL
        alert.resolved_at = timezone.now()
        alert.comment = serializer.validated_data.get("comment", alert.comment)
        return self._save(alert, ["status", "resolution", "resolved_at", "comment"])


class AlertRuleViewSet(viewsets.ModelViewSet):
    queryset = AlertRule.objects.select_related("country")
    serializer_class = AlertRuleSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    write_roles = GLOBAL_ROLES
    filterset_fields = ["code", "country", "severity", "is_active"]
    ordering_fields = ["code", "offset_days", "severity"]

    def perform_create(self, serializer):
        serializer.save()
        serializer.instance._history_user = self.request.user
