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


class ProductSerializer(serializers.ModelSerializer):
    range_code = serializers.CharField(source="range.code", read_only=True)
    range_label = serializers.CharField(source="range.label", read_only=True)
    aliases = ProductAliasSerializer(many=True, read_only=True)

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


class ProductMergeSerializer(serializers.Serializer):
    duplicate_id = serializers.UUIDField()
