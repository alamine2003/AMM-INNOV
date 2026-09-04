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
from .serializers import ImportBatchSerializer, ImportRowSerializer, ImportUploadSerializer
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
        if not upload.name.lower().endswith((".xlsx", ".xlsm")):
            return Response({"file": ["Seuls les classeurs .xlsx sont acceptés."]}, status=400)
        batch = ImportBatch.objects.create(
            file=upload,
            created_by=request.user,
            reference_date=serializer.validated_data.get("today"),
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
