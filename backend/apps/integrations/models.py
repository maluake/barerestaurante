from django.db import models

from apps.core.models import TenantModel


class IntegrationConfig(TenantModel):
    """Configuração de uma integração externa opcional (PDV, fornecedor, IA, notificação).

    Segredos NÃO ficam aqui: são lidos de variáveis de ambiente do backend, referenciadas
    por `secret_env_var`.
    """

    KINDS = [("pos", "PDV / comandas"), ("supplier", "API de fornecedor"), ("ai", "Provedor de IA"),
             ("notification", "Canal de notificação")]

    kind = models.CharField(max_length=20, choices=KINDS)
    provider = models.CharField(max_length=60)
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=False)
    settings = models.JSONField(default=dict, blank=True)
    secret_env_var = models.CharField(max_length=80, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class IntegrationLog(TenantModel):
    integration = models.ForeignKey(IntegrationConfig, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    kind = models.CharField(max_length=20)
    status = models.CharField(max_length=10)  # success, failure
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
