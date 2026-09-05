"""Referentials: countries, product ranges, products and their workbook aliases."""

import uuid

from django.db import models
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

from .normalize import normalize_product_name, product_key


class Country(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    iso2 = models.CharField("code ISO", max_length=2, unique=True)
    name = models.CharField("nom", max_length=100)
    authority = models.CharField("autorité réglementaire", max_length=200, blank=True)
    validity_years = models.PositiveSmallIntegerField("durée de validité (années)", default=5)
    filing_lead_months = models.PositiveSmallIntegerField("délai de dépôt (mois)", default=6)
    timezone = models.CharField("fuseau horaire", max_length=64, default="Africa/Dakar")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "pays"
        verbose_name_plural = "pays"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.iso2})"

    def save(self, *args, **kwargs):
        self.iso2 = self.iso2.upper()
        super().save(*args, **kwargs)


class ProductRange(models.Model):
    class Code(models.TextChoices):
        GENERALE = "GENERALE", "Générale"
        CARDIO = "CARDIO", "Cardio"
        BIEN_ETRE = "BIEN_ETRE", "Bien-être"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField("code", max_length=16, choices=Code.choices, unique=True)
    label = models.CharField("libellé", max_length=100)

    class Meta:
        verbose_name = "gamme"
        verbose_name_plural = "gammes"
        ordering = ["label"]

    def __str__(self) -> str:
        return self.label


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("libellé normalisé", max_length=255, unique=True)
    # Clé de rapprochement (lettres et chiffres) : l'import y retrouve un produit déjà connu
    # malgré une ponctuation différente, et les doublons existants se détectent par groupe.
    key = models.CharField("clé de rapprochement", max_length=255, db_index=True, editable=False)
    range = models.ForeignKey(
        ProductRange,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="gamme",
    )
    dci = models.CharField("DCI", max_length=255, blank=True)
    dosage = models.CharField("dosage", max_length=100, blank=True)
    form = models.CharField("forme", max_length=100, blank=True)
    presentation = models.CharField("présentation", max_length=100, blank=True)
    is_active = models.BooleanField("actif", default=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "produit"
        verbose_name_plural = "produits"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name = normalize_product_name(self.name)
        self.key = product_key(self.name)
        super().save(*args, **kwargs)

    @property
    def slug(self) -> str:
        return slugify(self.name)[:80] or str(self.pk)


class ProductAlias(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="aliases")
    raw_name = models.CharField("libellé source", max_length=255, unique=True)

    class Meta:
        verbose_name = "alias produit"
        verbose_name_plural = "alias produits"
        ordering = ["raw_name"]

    def __str__(self) -> str:
        return self.raw_name

    def save(self, *args, **kwargs):
        self.raw_name = normalize_product_name(self.raw_name)
        super().save(*args, **kwargs)
