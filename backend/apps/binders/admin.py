from django.contrib import admin

from .models import BinderCheck, BinderExtraPage


@admin.register(BinderCheck)
class BinderCheckAdmin(admin.ModelAdmin):
    list_display = ("amm", "result", "checked_by", "checked_at")
    list_filter = ("result", "amm__country")
    raw_id_fields = ("amm",)


@admin.register(BinderExtraPage)
class BinderExtraPageAdmin(admin.ModelAdmin):
    list_display = ("product_name", "binder_key", "created_by", "created_at")
    list_filter = ("country",)
