from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import MarketingAuthorization, Renewal


class RenewalInline(admin.TabularInline):
    model = Renewal
    extra = 0
    fields = ("sequence", "workflow_status", "filing_date", "number", "start_date", "end_date")
    readonly_fields = ("sequence",)


@admin.register(MarketingAuthorization)
class AmmAdmin(SimpleHistoryAdmin):
    list_display = (
        "product",
        "country",
        "original_number",
        "status",
        "urgency",
        "effective_end_date",
        "dossier_state",
    )
    list_filter = ("country", "status", "urgency", "dossier_state")
    search_fields = ("product__name", "original_number")
    readonly_fields = ("status", "urgency", "effective_end_date", "filing_deadline")
    inlines = [RenewalInline]
    autocomplete_fields = ("product",)


@admin.register(Renewal)
class RenewalAdmin(SimpleHistoryAdmin):
    list_display = ("amm", "sequence", "workflow_status", "filing_date", "number", "end_date")
    list_filter = ("workflow_status",)
    readonly_fields = ("sequence",)
