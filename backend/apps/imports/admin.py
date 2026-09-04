from django.contrib import admin

from .models import ImportBatch, ImportRow


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
