from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Document


@admin.register(Document)
class DocumentAdmin(SimpleHistoryAdmin):
    list_display = ("amm", "kind", "document_date", "version", "is_current", "archived_at")
    list_filter = ("kind", "is_current")
    search_fields = ("title", "amm__product__name", "sha256")
    readonly_fields = ("sha256", "size_bytes", "page_count", "uploaded_at")
