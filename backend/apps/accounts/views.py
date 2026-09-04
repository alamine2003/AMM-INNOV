from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .permissions import GLOBAL_ROLES, RolePermission
from .serializers import LoginSerializer, LogoutSerializer, UserSerializer


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [LoginThrottle]


class RefreshView(TokenRefreshView):
    pass


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return Response({"detail": "Jeton invalide."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
