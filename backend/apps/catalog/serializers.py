from rest_framework import serializers

from .models import Country, Product, ProductAlias, ProductRange


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = [
            "id",
            "iso2",
            "name",
            "authority",
            "validity_years",
            "filing_lead_months",
            "timezone",
        ]

    def validate_iso2(self, value: str) -> str:
        return value.upper()


class ProductRangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductRange
        fields = ["id", "code", "label"]


class ProductAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAlias
        fields = ["id", "raw_name"]


class AliasListField(serializers.ListField):
    """Alias d'un produit exposés comme une liste de chaînes (lecture et écriture)."""

    child = serializers.CharField(max_length=255, allow_blank=False)

    def get_attribute(self, instance):
        return [alias.raw_name for alias in instance.aliases.all()]


class ProductSerializer(serializers.ModelSerializer):
    range_code = serializers.CharField(source="range.code", read_only=True)
    range_label = serializers.CharField(source="range.label", read_only=True)
    # Liste de libellés (chaînes) en lecture comme en écriture : c'est le contrat attendu par le
    # frontend (`aliases: string[]`), qui les édite dans le formulaire produit.
    aliases = AliasListField(required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "range",
            "range_code",
            "range_label",
            "dci",
            "dosage",
            "form",
            "presentation",
            "is_active",
            "aliases",
        ]

    def create(self, validated_data):
        aliases = validated_data.pop("aliases", None)
        product = super().create(validated_data)
        self._sync_aliases(product, aliases)
        return product

    def update(self, instance, validated_data):
        aliases = validated_data.pop("aliases", None)
        product = super().update(instance, validated_data)
        self._sync_aliases(product, aliases)
        return product

    @staticmethod
    def _sync_aliases(product: Product, aliases: list[str] | None) -> None:
        """Aligne les alias du produit sur la liste reçue (None = inchangé)."""
        if aliases is None:
            return
        from .normalize import normalize_product_name

        wanted = {normalize_product_name(a) for a in aliases if a and a.strip()}
        existing = {alias.raw_name: alias for alias in product.aliases.all()}
        for raw_name, alias in existing.items():
            if raw_name not in wanted:
                alias.delete()
        for raw_name in wanted - set(existing):
            # Un alias est unique globalement : s'il appartient à un autre produit, on le déplace.
            ProductAlias.objects.update_or_create(raw_name=raw_name, defaults={"product": product})


class ProductMergeSerializer(serializers.Serializer):
    duplicate_id = serializers.UUIDField()


class MergeDuplicatesSerializer(serializers.Serializer):
    dry_run = serializers.BooleanField(required=False, default=False)
