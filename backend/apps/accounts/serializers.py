from django.contrib.auth.password_validation import validate_password
from django.db import models
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.catalog.models import Country

from .models import LOGIN_REASON, User
from .roles import Action, can


class HealthStatus(models.TextChoices):
    OK = "ok", "OK"
    DEGRADED = "degraded", "Dégradé"


class HealthSerializer(serializers.Serializer):
    """Réponse de /api/v1/health : 200 si la base répond, 503 sinon (sert au schéma OpenAPI)."""

    status = serializers.ChoiceField(choices=HealthStatus.choices)
    database = serializers.BooleanField()
    redis = serializers.BooleanField()
    version = serializers.CharField(max_length=64)


class UserSerializer(serializers.ModelSerializer):
    countries = serializers.SlugRelatedField(
        slug_field="iso2", queryset=Country.objects.all(), many=True, required=False
    )
    full_name = serializers.CharField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "countries",
            "is_active",
            "date_joined",
            "last_login",
            "password",
        ]
        read_only_fields = ["id", "date_joined", "last_login"]

    def validate_email(self, value: str) -> str:
        return value.lower().strip()

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def create(self, validated_data):
        countries = validated_data.pop("countries", [])
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        user.countries.set(countries)
        return user

    def update(self, instance, validated_data):
        countries = validated_data.pop("countries", None)
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if countries is not None:
            instance.countries.set(countries)
        return instance



class MeSerializer(UserSerializer):
    """L'utilisateur connecté, avec les actions sensibles qu'il peut faire.

    L'interface montre ou cache un bouton d'après `actions` (`useCan`), sans recopier les
    règles de rôles : elles restent dans `apps/accounts/roles.py`.
    """

    actions = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "actions"]

    @extend_schema_field(
        serializers.ListField(child=serializers.ChoiceField(choices=[a.value for a in Action]))
    )
    def get_actions(self, obj) -> list[str]:
        return [action.value for action in Action if can(obj, action)]

class LoginSerializer(TokenObtainPairSerializer):
    """Returns access, refresh and the serialized user in the JSON body."""

    def validate(self, attrs):
        data = super().validate(attrs)
        # Date de dernière connexion, avec un motif que l'audit reconnaît (« Connexion »).
        # Remplace UPDATE_LAST_LOGIN de simplejwt, qui ne donne pas de motif.
        self.user.last_login = timezone.now()
        self.user._change_reason = LOGIN_REASON
        self.user.save(update_fields=["last_login"])
        data["user"] = MeSerializer(self.user).data
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, allow_blank=True)
