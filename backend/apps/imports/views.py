from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsGlobalRole
from apps.core.pagination import StandardPagination
from apps.core.tasks import enqueue

from .models import ImportBatch, ImportRow
from .serializers import (
    GhplSyncedFileSerializer,
    GhplSyncStatusSerializer,
    ImportBatchSerializer,
    ImportRowSerializer,
    ImportUploadSerializer,
)
from .tasks import run_import


class ImportViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Upload of the workbook (`file` multipart); the import runs in Celery (`run_import`)."""

    queryset = ImportBatch.objects.select_related("created_by")
    serializer_class = ImportBatchSerializer
    permission_classes = [IsAuthenticated, IsGlobalRole]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=ImportUploadSerializer, responses={202: ImportBatchSerializer})
    def create(self, request, *args, **kwargs):
        serializer = ImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        name = upload.name.lower()
        if name.endswith(".csv"):
            from .scans import is_scan_manifest

            if not is_scan_manifest(upload):
                return Response(
                    {"file": ["Seul le manifeste des scans classés est accepté en .csv."]},
                    status=400,
                )
        elif not name.endswith((".xlsx", ".xlsm")):
            return Response(
                {
                    "file": [
                        "Seuls les classeurs .xlsx et le manifeste des scans (.csv) sont acceptés."
                    ]
                },
                status=400,
            )
        batch = ImportBatch.objects.create(
            file=upload,
            created_by=request.user,
            reference_date=serializer.validated_data.get("today"),
            dry_run=serializer.validated_data["dry_run"],
        )
        enqueue(run_import, str(batch.pk))
        batch.refresh_from_db()
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses=ImportRowSerializer(many=True))
    @action(detail=True, methods=["get"])
    def rows(self, request, pk=None):
        batch = self.get_object()
        queryset = ImportRow.objects.filter(batch=batch)
        outcome = request.query_params.get("outcome")
        if outcome:
            queryset = queryset.filter(outcome__in=[o.strip().upper() for o in outcome.split(",")])
        sheet = request.query_params.get("sheet")
        if sheet:
            queryset = queryset.filter(sheet__iexact=sheet)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(ImportRowSerializer(page, many=True).data)


class GhplSyncViewSet(viewsets.ViewSet):
    """Synchronisation horaire avec le classement AMM GHPL (Nextcloud) : état et lancement."""

    permission_classes = [IsAuthenticated, IsGlobalRole]

    @extend_schema(responses=GhplSyncStatusSerializer)
    def list(self, request):
        from django.conf import settings
        from django.db.models import Count

        from .ghpl.webdav import Nextcloud
        from .models import GhplSyncedFile, GhplSyncRun

        runs = GhplSyncRun.objects.select_related(None)
        last = runs.first()
        success = runs.filter(
            status__in=[
                GhplSyncRun.Status.DONE,
                GhplSyncRun.Status.PARTIAL,
                GhplSyncRun.Status.UP_TO_DATE,
            ]
        ).first()
        files = dict(GhplSyncedFile.objects.values_list("state").annotate(n=Count("id")).order_by())
        data = {
            "configured": Nextcloud.from_settings() is not None,
            "enabled": settings.GHPL_SYNC_ENABLED,
            "folder": settings.GHPL_SYNC_ROOT,
            "running": bool(last and last.status == GhplSyncRun.Status.RUNNING),
            "last_run": last,
            "last_success": success,
            "recent": list(runs.exclude(status=GhplSyncRun.Status.UP_TO_DATE)[:8]),
            "files": {state: files.get(state, 0) for state in GhplSyncedFile.State.values},
        }
        return Response(GhplSyncStatusSerializer(data).data)

    @extend_schema(request=None, responses={202: GhplSyncStatusSerializer})
    @action(detail=False, methods=["post"])
    def run(self, request):
        from .tasks import sync_ghpl

        enqueue(sync_ghpl, "MANUAL", str(request.user.pk))
        return Response({"detail": "Synchronisation lancée."}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses=GhplSyncedFileSerializer(many=True))
    @action(detail=False, methods=["get"])
    def files(self, request):
        from .models import GhplSyncedFile

        queryset = GhplSyncedFile.objects.order_by("-updated_at")
        state = request.query_params.get("state")
        if state:
            queryset = queryset.filter(state__in=[s.strip().upper() for s in state.split(",")])
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(GhplSyncedFileSerializer(page, many=True).data)
