from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Country, Product, ProductAlias, ProductRange


@admin.register(Country)
class CountryAdmin(SimpleHistoryAdmin):
    list_display = ("iso2", "name", "authority", "validity_years", "filing_lead_months")
    search_fields = ("iso2", "name")


@admin.register(ProductRange)
class ProductRangeAdmin(admin.ModelAdmin):
    list_display = ("code", "label")


class ProductAliasInline(admin.TabularInline):
    model = ProductAlias
    extra = 0


@admin.register(Product)
class ProductAdmin(SimpleHistoryAdmin):
    list_display = ("name", "range", "is_active")
    list_filter = ("range", "is_active")
    search_fields = ("name", "aliases__raw_name")
    inlines = [ProductAliasInline]


@admin.register(ProductAlias)
class ProductAliasAdmin(admin.ModelAdmin):
    list_display = ("raw_name", "product")
    search_fields = ("raw_name",)
