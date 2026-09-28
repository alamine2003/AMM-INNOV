from django.contrib import admin

from .models import DepositDossier, PieceType


@admin.register(PieceType)
class PieceTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "country", "required", "order", "active")
    list_filter = ("country", "required", "active")


@admin.register(DepositDossier)
class DepositDossierAdmin(admin.ModelAdmin):
    list_display = ("renewal", "sent_at", "deposited_at", "updated_at")
    raw_id_fields = ("renewal", "attestation")
