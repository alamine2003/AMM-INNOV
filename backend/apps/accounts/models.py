"""Custom user: email login, three business roles, country scope."""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


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
