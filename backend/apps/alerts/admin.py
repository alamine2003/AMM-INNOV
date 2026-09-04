from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Alert, AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(SimpleHistoryAdmin):
    list_display = ("code", "country", "offset_days", "severity", "only_if_not_filed", "is_active")
    list_filter = ("severity", "is_active", "country")


@admin.register(Alert)
class AlertAdmin(SimpleHistoryAdmin):
    list_display = ("amm", "rule", "due_date", "status", "assigned_to", "resolution")
    list_filter = ("status", "rule__code", "resolution")
    search_fields = ("amm__product__name",)
