from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .permissions import GLOBAL_ROLES, RolePermission
from .serializers import LoginSerializer, LogoutSerializer, UserSerializer


class LoginThrottle(AnonRateThrottle):
    """Par adresse IP cliente (X-Forwarded-For quand NUM_PROXIES est défini)."""

    scope = "login"


class LoginEmailThrottle(SimpleRateThrottle):
    """Par compte visé, quelle que soit l'IP : freine une attaque distribuée sur un email."""

    scope = "login_email"

    def get_cache_key(self, request, view):
        email = str(request.data.get("email", "")).strip().lower() if request.data else ""
        return self.cache_format % {"scope": self.scope, "ident": email} if email else None


def _cookie() -> dict:
    return settings.AUTH_REFRESH_COOKIE


def set_refresh_cookie(response, token: str) -> None:
    cookie = _cookie()
    response.set_cookie(
        cookie["name"],
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=cookie["secure"],
        samesite=cookie["samesite"],
        domain=cookie["domain"],
        path=cookie["path"],
    )


def clear_refresh_cookie(response) -> None:
    cookie = _cookie()
    response.delete_cookie(
        cookie["name"], path=cookie["path"], domain=cookie["domain"], samesite=cookie["samesite"]
    )


def check_origin(request) -> None:
    """Anti-CSRF for the cookie-authenticated auth routes: the Origin must be ours.

    SameSite=Lax already keeps the cookie out of cross-site POSTs; this closes the gap for
    browsers that ignore it. Requests without an Origin header (scripts, tests) pass.
    """
    origin = request.headers.get("Origin")
    if not origin or getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
        return
    allowed = set(settings.CORS_ALLOWED_ORIGINS) | {
        f"{request.scheme}://{request.get_host()}",
    }
    if origin not in allowed:
        raise PermissionDenied("Origine non autorisée.")


def refresh_token_from(request) -> str | None:
    """Body first (API clients), then the httpOnly cookie (browser)."""
    return (request.data.get("refresh") if request.data else None) or request.COOKIES.get(
        _cookie()["name"]
    )


class LoginView(TokenObtainPairView):
    """Returns `access` and `user`; the refresh token travels only in an httpOnly cookie."""

    serializer_class = LoginSerializer
    throttle_classes = [LoginThrottle, LoginEmailThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            set_refresh_cookie(response, response.data.pop("refresh"))
        return response


class RefreshView(TokenRefreshView):
    """Rotates the refresh token: reads it from the cookie (or body), writes the new one back."""

    def post(self, request, *args, **kwargs):
        check_origin(request)
        token = refresh_token_from(request)
        if not token:
            raise AuthenticationFailed("Session expirée, reconnectez-vous.")
        serializer = self.get_serializer(data={"refresh": token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise AuthenticationFailed(str(exc))
        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        rotated = response.data.pop("refresh", None)
        if rotated:
            set_refresh_cookie(response, rotated)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        check_origin(request)
        token = refresh_token_from(request)
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass  # déjà révoqué ou expiré : la déconnexion reste effective
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses={200: dict})
    def get(self, request):
        database = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:  # pragma: no cover - only on outage
            database = False
        redis_ok = False
        try:
            import redis
            from django.conf import settings

            redis_ok = bool(
                redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1).ping()
            )
        except Exception:
            redis_ok = False
        code = status.HTTP_200_OK if database else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(
            {"status": "ok" if database else "degraded", "database": database, "redis": redis_ok},
            status=code,
        )


class UserViewSet(viewsets.ModelViewSet):
    """User management, CEO_ADMIN and HQ_REGULATORY only.

    HQ_REGULATORY may only create and edit COUNTRY_REGULATORY accounts.
    """

    queryset = User.objects.prefetch_related("countries").all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    write_roles = GLOBAL_ROLES
    filterset_fields = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["email", "date_joined", "role"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_global:
            return queryset.none()
        return queryset

    def _check_hq_limits(self, target_role: str | None, instance: User | None = None) -> None:
        user = self.request.user
        if user.role != User.Role.HQ_REGULATORY:
            return
        if instance is not None and instance.role != User.Role.COUNTRY_REGULATORY:
            raise PermissionDenied(
                "Le réglementaire siège ne gère que les comptes réglementaires pays."
            )
        if target_role is not None and target_role != User.Role.COUNTRY_REGULATORY:
            raise PermissionDenied(
                "Le réglementaire siège ne peut créer que des comptes réglementaires pays."
            )

    def perform_create(self, serializer):
        self._check_hq_limits(serializer.validated_data.get("role"))
        serializer.save()

    def perform_update(self, serializer):
        self._check_hq_limits(serializer.validated_data.get("role"), serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._check_hq_limits(None, instance)
        if instance == self.request.user:
            raise PermissionDenied("Impossible de supprimer son propre compte.")
        instance.delete()
