from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import DEFAULT_ORG_SETTINGS, AuditLog, Membership, Organization, Unit
from .permissions import ALL_PERMISSIONS

User = get_user_model()


class TenantSerializer(serializers.ModelSerializer):
    """Restringe automaticamente as chaves estrangeiras aos registros da organização ativa.

    Impede que um usuário associe objetos de outro estabelecimento informando IDs na API.
    """

    def get_fields(self):
        fields = super().get_fields()
        org = self.context.get("org")
        for field in fields.values():
            target = getattr(field, "child_relation", field)
            qs = getattr(target, "queryset", None)
            if qs is None or org is None:
                continue
            model = qs.model
            names = {f.name for f in model._meta.get_fields()}
            if model is Organization:
                target.queryset = qs.filter(pk=org.pk)
            elif "organization" in names:
                if model.__name__ == "UnitOfMeasure":
                    from django.db.models import Q

                    target.queryset = qs.filter(Q(organization=org) | Q(organization__isnull=True))
                else:
                    target.queryset = qs.filter(organization=org)
        return fields


class UnitSerializer(TenantSerializer):
    class Meta:
        model = Unit
        fields = ["id", "name", "code", "address", "city", "timezone", "is_active", "created_at"]


class OrganizationSerializer(serializers.ModelSerializer):
    effective_settings = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ["id", "name", "legal_name", "cnpj", "plan", "is_demo", "settings", "effective_settings", "created_at"]
        read_only_fields = ["plan", "is_demo", "created_at"]

    def get_effective_settings(self, obj):
        return {**DEFAULT_ORG_SETTINGS, **(obj.settings or {})}

    def validate_settings(self, value):
        unknown = set(value) - set(DEFAULT_ORG_SETTINGS)
        if unknown:
            raise serializers.ValidationError(f"Configurações desconhecidas: {', '.join(sorted(unknown))}")
        return value


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "full_name"]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class MembershipSerializer(TenantSerializer):
    user = UserSerializer(read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    permissions = serializers.SerializerMethodField()
    # Campos para criação de um novo funcionário
    username = serializers.CharField(write_only=True, required=False)
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})

    class Meta:
        model = Membership
        fields = [
            "id", "user", "role", "role_label", "units", "extra_permissions", "revoked_permissions", "is_active",
            "permissions", "created_at", "username", "email", "first_name", "last_name", "password",
        ]
        read_only_fields = ["created_at"]

    def get_permissions(self, obj):
        return sorted(obj.permissions)

    def validate_extra_permissions(self, value):
        bad = [p for p in value if p not in ALL_PERMISSIONS]
        if bad:
            raise serializers.ValidationError(f"Permissões inválidas: {', '.join(bad)}")
        return value

    validate_revoked_permissions = validate_extra_permissions

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get("username") or not attrs.get("password"):
                raise serializers.ValidationError("Informe usuário e senha para o novo funcionário.")
            if User.objects.filter(username__iexact=attrs["username"]).exists():
                raise serializers.ValidationError({"username": "Este nome de usuário já está em uso."})
            validate_password(attrs["password"])
        return attrs

    def create(self, validated):
        org = self.context["org"]
        user = User.objects.create_user(
            username=validated.pop("username"), password=validated.pop("password"),
            email=validated.pop("email", ""), first_name=validated.pop("first_name", ""),
            last_name=validated.pop("last_name", ""),
        )
        units = validated.pop("units", [])
        membership = Membership.objects.create(user=user, organization=org, **validated)
        membership.units.set(units)
        return membership

    def update(self, instance, validated):
        for f in ("username", "password", "email", "first_name", "last_name"):
            validated.pop(f, None)
        return super().update(instance, validated)


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    unit_name = serializers.CharField(source="unit.name", default=None, read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "action", "entity", "entity_id", "summary", "changes", "user_name", "unit_name", "ip_address",
                  "created_at"]

    def get_user_name(self, obj):
        return (obj.user.get_full_name() or obj.user.username) if obj.user else "Sistema"


class SignupSerializer(serializers.Serializer):
    establishment_name = serializers.CharField(max_length=150)
    unit_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    accept_terms = serializers.BooleanField()

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Este nome de usuário já está em uso.")
        return value

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("É necessário aceitar os termos e a política de privacidade (LGPD).")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"])
        return attrs
