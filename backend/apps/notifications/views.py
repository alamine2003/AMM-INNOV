from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """The current user's notifications (`?unread=1` keeps only unread ones)."""

    queryset = Notification.objects.none()  # remplacé par get_queryset ; utile au schéma OpenAPI
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["channel"]
    ordering_fields = ["created_at", "read_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        queryset = Notification.objects.filter(user=self.request.user).select_related(
            "alert", "alert__rule"
        )
        unread = self.request.query_params.get("unread", "").lower()
        if unread in {"1", "true"}:
            queryset = queryset.filter(read_at__isnull=True)
        return queryset

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = Notification.objects.filter(user=request.user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return Response({"updated": updated})

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = Notification.objects.filter(
            user=request.user, read_at__isnull=True, channel=Notification.Channel.IN_APP
        ).count()
        return Response({"unread": count})
