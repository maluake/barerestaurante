from django.conf import settings
from django.db import models

from apps.core.models import Membership, TenantModel, Unit

ALERT_TYPES = [
    ("low_stock", "Estoque abaixo do mínimo"),
    ("stockout_risk", "Ingrediente pode acabar"),
    ("expiring", "Lote próximo do vencimento"),
    ("expired", "Lote vencido no estoque"),
    ("negative_stock", "Saldo negativo"),
    ("slow_order", "Pedido demorado"),
    ("po_approval", "Compra aguardando aprovação"),
    ("late_delivery", "Entrega atrasada"),
    ("quote_expiring", "Cotação vencendo"),
    ("cost_increase", "Aumento de custo"),
    ("waste_above", "Desperdício acima do padrão"),
    ("consumption_spike", "Consumo incomum"),
    ("inventory_divergence", "Divergência de inventário"),
    ("missing_recipe", "Item sem ficha técnica"),
    ("integration_failure", "Falha de integração"),
]

PRIORITIES = [("critical", "Crítica"), ("high", "Alta"), ("medium", "Média"), ("low", "Baixa")]
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class Alert(TenantModel):
    STATUS = [("open", "Aberto"), ("resolved", "Resolvido"), ("auto_resolved", "Resolvido automaticamente")]

    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts")
    type = models.CharField(max_length=30, choices=ALERT_TYPES)
    priority = models.CharField(max_length=10, choices=PRIORITIES, default="medium")
    # Identifica a condição: evita alertas duplicados para a mesma situação.
    dedup_key = models.CharField(max_length=160)
    title = models.CharField(max_length=200)
    reason = models.TextField()
    action_label = models.CharField(max_length=80, blank=True)
    action_path = models.CharField(max_length=200, blank=True)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default="open", db_index=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    resolution_note = models.CharField(max_length=255, blank=True)
    # Alerta resolvido manualmente não reaparece antes desta data, mesmo que a condição persista.
    snoozed_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-first_seen_at"]
        indexes = [models.Index(fields=["organization", "unit", "dedup_key"])]


class AlertRefreshState(models.Model):
    unit = models.OneToOneField(Unit, on_delete=models.CASCADE, related_name="alert_refresh")
    refreshed_at = models.DateTimeField()


class NotificationPreference(models.Model):
    """Preferências por usuário: canais e prioridade mínima por tipo de alerta."""

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="notification_preferences")
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    enabled = models.BooleanField(default=True)
    min_priority = models.CharField(max_length=10, choices=PRIORITIES, default="low")
    channels = models.JSONField(default=list)  # ["in_app", "email"]

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "alert_type"], name="uniq_notification_pref")]


class Notification(models.Model):
    """Registro de envio de um alerta por canal (permite auditoria e evita repetições)."""

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    channel = models.CharField(max_length=20)
    status = models.CharField(max_length=10, default="sent")  # sent, failed
    error = models.CharField(max_length=255, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["alert", "user", "channel"], name="uniq_notification")]
