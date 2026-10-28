"""Resolução do tenant (organização + unidade) a partir do usuário autenticado.

O frontend envia o cabeçalho `X-Unit-Id`; ele NUNCA é aceito sem verificar se o
usuário tem vínculo ativo com a organização da unidade e acesso à unidade.
"""

from rest_framework import viewsets
from rest_framework.exceptions import NotAuthenticated, PermissionDenied

from .models import AuditLog, Membership, Unit
from .permissions import HasTenantPermission, permissions_for


def resolve_tenant(request):
    user = request.user
    if not user or not user.is_authenticated:
        raise NotAuthenticated()
    unit_id = request.headers.get("X-Unit-Id") or request.query_params.get("unit")
    memberships = Membership.objects.filter(user=user, is_active=True).select_related("organization")
    if unit_id:
        try:
            unit = Unit.objects.select_related("organization").get(pk=int(unit_id), is_active=True)
        except (Unit.DoesNotExist, ValueError, TypeError):
            raise PermissionDenied("Unidade inexistente ou sem acesso.")
        membership = memberships.filter(organization=unit.organization).first()
        if membership is None or not membership.allowed_units().filter(pk=unit.pk).exists():
            raise PermissionDenied("Unidade inexistente ou sem acesso.")
    else:
        membership = memberships.order_by("created_at").first()
        if membership is None:
            raise PermissionDenied("Usuário sem vínculo com um estabelecimento.")
        unit = membership.allowed_units().first()
        if unit is None:
            raise PermissionDenied("Nenhuma unidade disponível para este usuário.")
    request.membership = membership
    request.org = membership.organization
    request.unit = unit
    request.perms = permissions_for(membership)
    return membership


class TenantMixin:
    """Mixin para views da API: resolve o tenant e aplica permissões por função."""

    permission_classes = [HasTenantPermission]
    # Se True, o queryset é filtrado também pela unidade ativa (campo `unit`).
    unit_scoped = False

    def initial(self, request, *args, **kwargs):
        self.perform_authentication(request)
        resolve_tenant(request)
        super().initial(request, *args, **kwargs)

    def scope_queryset(self, qs):
        qs = qs.filter(organization=self.request.org)
        if self.unit_scoped:
            qs = qs.filter(unit=self.request.unit)
        return qs

    def get_queryset(self):
        return self.scope_queryset(super().get_queryset())

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = getattr(self.request, "org", None)
        ctx["unit"] = getattr(self.request, "unit", None)
        return ctx

    def has_perm(self, code):
        return code in getattr(self.request, "perms", set())


class TenantModelViewSet(TenantMixin, viewsets.ModelViewSet):
    audit_entity = None

    def perform_create(self, serializer):
        kwargs = {"organization": self.request.org}
        if self.unit_scoped:
            kwargs["unit"] = self.request.unit
        obj = serializer.save(**kwargs)
        audit(self.request, "create", obj, summary=str(obj))

    def perform_update(self, serializer):
        fields = [
            k for k in serializer.validated_data
            if hasattr(serializer.instance, k) and not hasattr(getattr(serializer.instance, k), "all")
        ]
        before = {k: str(getattr(serializer.instance, k)) for k in fields}
        obj = serializer.save()
        after = {k: str(getattr(obj, k)) for k in before}
        changes = {k: [before[k], after[k]] for k in before if before[k] != after[k]}
        audit(self.request, "update", obj, summary=str(obj), changes=changes)


def client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def audit(request, action, obj=None, summary="", changes=None, entity=None, entity_id=None, org=None, unit=None):
    """Registra uma entrada de auditoria. Funciona com ou sem request (ex.: comandos)."""
    org = org or getattr(request, "org", None) or getattr(obj, "organization", None)
    if org is None:
        return None
    return AuditLog.objects.create(
        organization=org,
        unit=unit or getattr(request, "unit", None) or getattr(obj, "unit", None),
        user=getattr(request, "user", None) if request is not None and request.user.is_authenticated else None,
        action=action,
        entity=entity or (obj._meta.model_name if obj is not None else ""),
        entity_id=str(entity_id if entity_id is not None else getattr(obj, "pk", "") or ""),
        summary=(summary or "")[:255],
        changes=changes or {},
        ip_address=client_ip(request) if request is not None else None,
    )
