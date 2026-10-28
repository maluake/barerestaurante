from rest_framework import mixins, serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.tenancy import TenantMixin, TenantModelViewSet

from .models import IntegrationConfig, IntegrationLog
from .registry import CATALOG


class IntegrationConfigSerializer(serializers.ModelSerializer):
    secret_configured = serializers.SerializerMethodField()

    class Meta:
        model = IntegrationConfig
        fields = ["id", "kind", "provider", "name", "enabled", "settings", "secret_env_var", "secret_configured",
                  "last_sync_at", "created_at"]
        read_only_fields = ["last_sync_at", "created_at"]

    def get_secret_configured(self, obj):
        import os

        return bool(obj.secret_env_var and os.environ.get(obj.secret_env_var))

    def validate(self, attrs):
        provider = attrs.get("provider", getattr(self.instance, "provider", None))
        if provider not in {p["provider"] for p in CATALOG}:
            raise serializers.ValidationError({"provider": "Provedor não suportado."})
        if attrs.get("enabled"):
            entry = next(p for p in CATALOG if p["provider"] == provider)
            if not entry["available"]:
                raise serializers.ValidationError({"enabled": "Esta integração ainda não está disponível nesta versão."})
        return attrs


class IntegrationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationLog
        fields = ["id", "kind", "status", "message", "details", "created_at"]


class IntegrationConfigViewSet(TenantModelViewSet):
    serializer_class = IntegrationConfigSerializer
    queryset = IntegrationConfig.objects.all()
    required_permissions = "integrations.manage"


class IntegrationLogViewSet(TenantMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = IntegrationLogSerializer
    queryset = IntegrationLog.objects.all()
    required_permissions = "integrations.manage"
    filterset_fields = ["status", "kind"]


class CatalogView(TenantMixin, APIView):
    required_permissions = "integrations.manage"

    def get(self, request):
        return Response(CATALOG)
