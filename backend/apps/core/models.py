from django.conf import settings
from django.db import models

DEFAULT_ORG_SETTINGS = {
    # Pedidos de compra acima deste valor (R$) precisam de aprovação.
    "purchase_approval_threshold": "500.00",
    # Cotações consultadas há mais de N dias são consideradas desatualizadas.
    "stale_quote_days": 7,
    # Faixas de vencimento exibidas na tela de validades (dias).
    "expiry_buckets": [0, 3, 7, 30],
    # Dias de funcionamento (0=segunda ... 6=domingo).
    "operating_weekdays": [1, 2, 3, 4, 5, 6],
    # Quantos dias de consumo a lista de compras deve cobrir após a entrega.
    "coverage_days": 7,
    # Pedidos em aberto há mais de N minutos são considerados atrasados.
    "slow_order_minutes": 25,
    # Taxa média dos aplicativos de entrega (%), aplicada a vendas do canal "app".
    "delivery_app_fee_percent": "12.00",
    # Desperdício mensal acima deste percentual das compras gera alerta.
    "waste_alert_percent": "5.00",
    # Variação de custo (%) considerada incomum.
    "cost_increase_alert_percent": "10.00",
}

PLAN_LIMITS = {
    "starter": {"units": 1, "users": 8},
    "pro": {"units": 5, "users": 40},
    "enterprise": {"units": 100, "users": 1000},
}


class Organization(models.Model):
    """Empresa cliente (tenant). Agrupa uma ou mais unidades."""

    PLAN_CHOICES = [("starter", "Essencial"), ("pro", "Profissional"), ("enterprise", "Rede")]

    name = models.CharField("nome", max_length=150)
    legal_name = models.CharField("razão social", max_length=200, blank=True)
    cnpj = models.CharField(max_length=18, blank=True)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default="starter")
    settings = models.JSONField(default=dict, blank=True)
    is_demo = models.BooleanField("ambiente de demonstração", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def setting(self, key):
        return self.settings.get(key, DEFAULT_ORG_SETTINGS.get(key))

    @property
    def limits(self):
        return PLAN_LIMITS.get(self.plan, PLAN_LIMITS["starter"])


class Unit(models.Model):
    """Estabelecimento físico (unidade). Cada unidade tem estoque, equipe e pedidos próprios."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="units")
    name = models.CharField("nome", max_length=150)
    code = models.CharField("código", max_length=20, blank=True)
    address = models.CharField("endereço", max_length=255, blank=True)
    city = models.CharField("cidade", max_length=100, blank=True)
    timezone = models.CharField(max_length=64, default="America/Sao_Paulo")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Membership(models.Model):
    """Vínculo de um usuário a uma organização, com função e unidades permitidas."""

    ROLE_CHOICES = [
        ("owner", "Proprietário"),
        ("manager", "Gerente"),
        ("stock", "Estoquista"),
        ("attendant", "Atendente"),
        ("kitchen", "Cozinha"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField("função", max_length=20, choices=ROLE_CHOICES)
    # Vazio = todas as unidades da organização.
    units = models.ManyToManyField(Unit, blank=True, related_name="memberships")
    extra_permissions = models.JSONField(default=list, blank=True)
    revoked_permissions = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "organization"], name="uniq_membership")]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"

    @property
    def permissions(self):
        from .permissions import permissions_for

        return permissions_for(self)

    def allowed_units(self):
        qs = self.organization.units.filter(is_active=True)
        if self.role != "owner" and self.units.exists():
            qs = qs.filter(pk__in=self.units.values("pk"))
        return qs


class AuditLog(models.Model):
    """Trilha de auditoria imutável das ações relevantes."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="audit_logs")
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    entity = models.CharField(max_length=60)
    entity_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "entity", "entity_id"])]


class TenantModel(models.Model):
    """Base para entidades que pertencem a uma organização."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True
