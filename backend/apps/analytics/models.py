from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class AssistantQuery(TenantModel):
    """Histórico das perguntas feitas ao Assistente do Negócio (auditoria)."""

    unit = models.ForeignKey("core.Unit", null=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    question = models.TextField()
    intent = models.CharField(max_length=40)
    provider = models.CharField(max_length=20, default="rules")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
