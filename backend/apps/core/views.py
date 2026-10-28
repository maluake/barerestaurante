from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .exceptions import BusinessError
from .models import AuditLog, Membership, Unit
from .permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS, permissions_for
from .serializers import (
    AuditLogSerializer,
    MembershipSerializer,
    OrganizationSerializer,
    SignupSerializer,
    UnitSerializer,
    UserSerializer,
)
from .setup import create_organization, setup_unit
from .tenancy import TenantMixin, TenantModelViewSet, audit, resolve_tenant


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "ok"})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            return Response({"detail": "Usuário ou senha inválidos."}, status=status.HTTP_400_BAD_REQUEST)
        if not Membership.objects.filter(user=user, is_active=True).exists():
            return Response({"detail": "Usuário sem acesso ativo a um estabelecimento."}, status=status.HTTP_403_FORBIDDEN)
        login(request, user)
        for m in Membership.objects.filter(user=user, is_active=True):
            audit(request, "login", user, summary="Login", org=m.organization, entity="user", entity_id=user.pk)
        return Response(build_me(request))


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def build_me(request):
    user = request.user
    memberships = []
    for m in Membership.objects.filter(user=user, is_active=True).select_related("organization"):
        memberships.append({
            "id": m.id,
            "organization": {"id": m.organization.id, "name": m.organization.name, "is_demo": m.organization.is_demo,
                             "plan": m.organization.plan},
            "role": m.role,
            "role_label": m.get_role_display(),
            "permissions": sorted(permissions_for(m)),
            "units": UnitSerializer(m.allowed_units(), many=True).data,
        })
    return {"user": UserSerializer(user).data, "memberships": memberships}


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_me(request))


class SignupView(APIView):
    """Cria um novo estabelecimento (organização + primeira unidade) e o usuário proprietário."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    def post(self, request):
        from django.contrib.auth import get_user_model

        ser = SignupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                username=d["username"], password=d["password"], email=d["email"], first_name=d["first_name"],
                last_name=d.get("last_name", ""),
            )
            org, unit = create_organization(name=d["establishment_name"], owner=user,
                                            unit_name=d.get("unit_name") or None, city=d.get("city", ""))
            audit(None, "create", org, summary=f"Estabelecimento criado por {user.username}", org=org, unit=unit,
                  entity="organization", entity_id=org.pk)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(build_me(request), status=status.HTTP_201_CREATED)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current = request.data.get("current_password", "")
        new = request.data.get("new_password", "")
        if not request.user.check_password(current):
            raise BusinessError("Senha atual incorreta.", field="current_password")
        try:
            validate_password(new, request.user)
        except Exception as exc:  # noqa: BLE001 - devolve mensagens do validador
            raise serializers.ValidationError({"new_password": list(getattr(exc, "messages", [str(exc)]))})
        request.user.set_password(new)
        request.user.save()
        update_session_auth_hash(request, request.user)
        return Response({"detail": "Senha alterada."})


class PersonalDataExportView(APIView):
    """LGPD: exporta os dados pessoais do próprio usuário."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        data = {
            "usuario": {"username": u.username, "nome": u.first_name, "sobrenome": u.last_name, "email": u.email,
                        "data_cadastro": u.date_joined, "ultimo_login": u.last_login},
            "vinculos": [{"estabelecimento": m.organization.name, "funcao": m.get_role_display(),
                          "ativo": m.is_active} for m in u.memberships.select_related("organization")],
            "acoes_registradas": AuditLog.objects.filter(user=u).count(),
        }
        return Response(data)


class OrganizationView(TenantMixin, APIView):
    required_permissions = {"get": "dashboard.view", "patch": "settings.manage"}

    def check_permissions(self, request):
        # Leitura liberada a qualquer membro; edição exige settings.manage.
        if request.method == "GET":
            return
        super().check_permissions(request)

    def get(self, request):
        return Response(OrganizationSerializer(request.org).data)

    def patch(self, request):
        ser = OrganizationSerializer(request.org, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        before = dict(request.org.settings)
        ser.save()
        audit(request, "update", request.org, summary="Configurações alteradas",
              changes={"settings": [before, request.org.settings]})
        return Response(ser.data)


class UnitViewSet(TenantModelViewSet):
    serializer_class = UnitSerializer
    queryset = Unit.objects.all()
    required_permissions = {"list": "orders.view", "retrieve": "orders.view", "*": "units.manage"}
    http_method_names = ["get", "post", "patch", "head", "options"]

    def check_permissions(self, request):
        if self.action in ("list", "retrieve"):
            return  # qualquer membro vê as unidades às quais tem acesso
        super().check_permissions(request)

    def get_queryset(self):
        if self.action in ("list", "retrieve"):
            return self.request.membership.allowed_units()
        return Unit.objects.filter(organization=self.request.org)

    def perform_create(self, serializer):
        org = self.request.org
        if org.units.filter(is_active=True).count() >= org.limits["units"]:
            raise BusinessError(f"O plano atual permite até {org.limits['units']} unidade(s). Atualize o plano para adicionar mais.",
                                code="plan_limit")
        unit = serializer.save(organization=org)
        setup_unit(unit)
        audit(self.request, "create", unit, summary=f"Unidade {unit.name} criada")


class TeamViewSet(TenantModelViewSet):
    serializer_class = MembershipSerializer
    queryset = Membership.objects.select_related("user").prefetch_related("units").order_by("created_at")
    required_permissions = "team.manage"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        org = self.request.org
        if org.memberships.filter(is_active=True).count() >= org.limits["users"]:
            raise BusinessError(f"O plano atual permite até {org.limits['users']} usuários.", code="plan_limit")
        if serializer.validated_data.get("role") == "owner" and self.request.membership.role != "owner":
            raise BusinessError("Somente o proprietário pode cadastrar outro proprietário.")
        m = serializer.save()
        audit(self.request, "create", m, summary=f"Funcionário {m.user.username} ({m.get_role_display()}) cadastrado")

    def perform_update(self, serializer):
        m = serializer.instance
        if m.role == "owner" and self.request.membership.role != "owner":
            raise BusinessError("Somente o proprietário pode alterar outro proprietário.")
        new_role = serializer.validated_data.get("role", m.role)
        new_active = serializer.validated_data.get("is_active", m.is_active)
        if m.role == "owner" and (new_role != "owner" or not new_active):
            others = Membership.objects.filter(organization=m.organization, role="owner", is_active=True).exclude(pk=m.pk)
            if not others.exists():
                raise BusinessError("O estabelecimento precisa ter ao menos um proprietário ativo.")
        super().perform_update(serializer)

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        return Response({
            "permissions": [{"code": k, "label": v} for k, v in ALL_PERMISSIONS.items()],
            "roles": [{"code": code, "label": label, "permissions": sorted(ROLE_PERMISSIONS[code])}
                      for code, label in Membership.ROLE_CHOICES],
        })


class AuditLogViewSet(TenantMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.select_related("user", "unit")
    required_permissions = "audit.view"
    filterset_fields = ["entity", "action", "user", "unit"]
    search_fields = ["summary", "entity", "entity_id"]


class ContextView(TenantMixin, APIView):
    """Retorna o contexto resolvido (unidade ativa e permissões) para o frontend."""

    def check_permissions(self, request):
        return

    def get(self, request):
        resolve_tenant(request)
        return Response({
            "organization": OrganizationSerializer(request.org).data,
            "unit": UnitSerializer(request.unit).data,
            "role": request.membership.role,
            "permissions": sorted(request.perms),
        })
