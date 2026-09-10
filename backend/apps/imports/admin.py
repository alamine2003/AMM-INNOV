from django.contrib import admin

from .models import DossierChange, DossierFile, DossierImport, ImportBatch, ImportRow


class ImportRowInline(admin.TabularInline):
    model = ImportRow
    extra = 0
    fields = ("sheet", "row_number", "outcome", "message")
    readonly_fields = fields
    can_delete = False


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status", "created_by", "reference_date")
    readonly_fields = ("summary", "created_at", "finished_at")
    inlines = [ImportRowInline]


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = ("batch", "sheet", "row_number", "outcome")
    list_filter = ("outcome", "sheet")
    search_fields = ("message",)


class ReadOnlyDossierAdmin(admin.ModelAdmin):
    """Review provenance in the admin; use the import workflow for every mutation."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DossierImport)
class DossierImportAdmin(ReadOnlyDossierAdmin):
    list_display = ("root_name", "status", "created_by", "country", "created_at")
    list_filter = ("status", "country")
    search_fields = ("root_name", "created_by__email")
    list_select_related = ("created_by", "country")


@admin.register(DossierFile)
class DossierFileAdmin(ReadOnlyDossierAdmin):
    list_display = ("relative_path", "batch", "content_type", "size_bytes")
    search_fields = ("relative_path", "sha256")
    list_select_related = ("batch",)


@admin.register(DossierChange)
class DossierChangeAdmin(ReadOnlyDossierAdmin):
    list_display = ("amm", "field", "user", "confidence", "created_at")
    list_filter = ("field", "source")
    search_fields = ("amm__original_number", "amm__product__name", "proof_file__relative_path")
    list_select_related = ("amm__product", "amm__country", "user")
