"""Custom user: email login, three business roles, country scope."""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

# Motif d'historique d'une connexion : l'audit les reconnaît (et les filtre) par ce motif.
LOGIN_REASON = "Connexion"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.CEO_ADMIN)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CEO_ADMIN = "CEO_ADMIN", "CEO / administrateur"
        HQ_REGULATORY = "HQ_REGULATORY", "Réglementaire siège"
        COUNTRY_REGULATORY = "COUNTRY_REGULATORY", "Réglementaire pays"

    GLOBAL_ROLES = (Role.CEO_ADMIN, Role.HQ_REGULATORY)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email", unique=True)
    first_name = models.CharField("prénom", max_length=150, blank=True)
    last_name = models.CharField("nom", max_length=150, blank=True)
    role = models.CharField(
        "rôle", max_length=32, choices=Role.choices, default=Role.COUNTRY_REGULATORY
    )
    countries = models.ManyToManyField(
        "catalog.Country", blank=True, related_name="users", verbose_name="pays du périmètre"
    )
    is_active = models.BooleanField("actif", default=True)
    is_staff = models.BooleanField("accès admin", default=False)
    date_joined = models.DateTimeField("créé le", default=timezone.now)

    objects = UserManager()
    # Audit : création, modification, désactivation et connexions (last_login). Le mot de passe
    # n'est jamais copié dans l'historique.
    history = HistoricalRecords(excluded_fields=["password"])

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def is_global(self) -> bool:
        """True for roles that see every country."""
        return self.role in self.GLOBAL_ROLES

    def can_access_country(self, country) -> bool:
        if self.is_global:
            return True
        country_id = getattr(country, "pk", country)
        return self.countries.filter(pk=country_id).exists()

    def scoped_country_ids(self) -> list:
        return list(self.countries.values_list("pk", flat=True))


class ActionGrant(models.Model):
    """Droit d'un rôle sur une action sensible, réglé par le CEO (Administration › Permissions).

    Sans ligne, le réglage par défaut de `apps/accounts/roles.py` s'applique. Chaque changement
    est conservé dans l'historique (audit).
    """

    action = models.CharField("action", max_length=64)
    role = models.CharField("rôle", max_length=32, choices=User.Role.choices)
    allowed = models.BooleanField("autorisé")
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="modifié par",
    )
    updated_at = models.DateTimeField("modifié le", auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "permission"
        verbose_name_plural = "permissions"
        ordering = ["action", "role"]
        constraints = [
            models.UniqueConstraint(fields=["action", "role"], name="unique_action_grant"),
        ]

    def __str__(self) -> str:
        state = "autorisé" if self.allowed else "refusé"
        return f"{self.action} · {self.get_role_display()} : {state}"
