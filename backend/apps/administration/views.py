"""Corbeille : ce qui a été supprimé dans l'application, et sa restauration (CEO et siège)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import ensure_can
from apps.accounts.roles import Action
from apps.core.models import TrashEntry
from apps.core.trash import restore

from .serializers import TrashEntrySerializer


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
