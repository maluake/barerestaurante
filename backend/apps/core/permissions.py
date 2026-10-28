"""Permissões por função, verificadas sempre no backend.

Cada função recebe um conjunto padrão de códigos. O proprietário pode conceder
(`extra_permissions`) ou revogar (`revoked_permissions`) códigos individualmente.
"""

from rest_framework.permissions import BasePermission

ALL_PERMISSIONS = {
    "dashboard.view": "Ver dashboard operacional",
    "finance.view": "Ver indicadores e lançamentos financeiros",
    "finance.manage": "Lançar despesas, contas e operar caixa",
    "products.view": "Consultar produtos",
    "products.manage": "Cadastrar e editar produtos",
    "stock.view": "Consultar estoque, lotes e movimentações",
    "stock.move": "Registrar entradas, saídas e descartes",
    "stock.adjust": "Realizar inventários e ajustes",
    "stock.transfer": "Transferir mercadorias entre unidades",
    "waste.manage": "Registrar perdas e desperdícios",
    "recipes.view": "Consultar fichas técnicas",
    "recipes.manage": "Editar cardápio e fichas técnicas",
    "costs.view": "Ver custos e margens",
    "orders.view": "Consultar pedidos",
    "orders.manage": "Registrar e alterar pedidos",
    "kitchen.update": "Atualizar status de preparo",
    "sales.view": "Consultar vendas",
    "sales.manage": "Registrar e importar vendas",
    "sales.cancel": "Cancelar vendas e pedidos já confirmados",
    "suppliers.view": "Consultar fornecedores e cotações",
    "suppliers.manage": "Cadastrar fornecedores e cotações",
    "purchases.view": "Consultar compras",
    "purchases.manage": "Criar listas e pedidos de compra",
    "purchases.approve": "Aprovar pedidos de compra",
    "purchases.receive": "Receber mercadorias",
    "reports.view": "Acessar relatórios operacionais",
    "reports.finance": "Acessar relatórios financeiros",
    "alerts.view": "Ver alertas",
    "alerts.manage": "Resolver alertas",
    "assistant.use": "Usar o Assistente do Negócio",
    "team.manage": "Gerenciar equipe e permissões",
    "units.manage": "Gerenciar unidades",
    "audit.view": "Consultar auditoria",
    "settings.manage": "Alterar configurações do estabelecimento",
    "integrations.manage": "Configurar integrações",
}

ROLE_PERMISSIONS = {
    "owner": set(ALL_PERMISSIONS),
    "manager": {
        "dashboard.view", "products.view", "products.manage", "stock.view", "stock.move", "stock.adjust",
        "stock.transfer", "waste.manage", "recipes.view", "recipes.manage", "costs.view", "orders.view",
        "orders.manage", "kitchen.update", "sales.view", "sales.manage", "sales.cancel", "suppliers.view",
        "suppliers.manage", "purchases.view", "purchases.manage", "purchases.approve", "purchases.receive",
        "reports.view", "alerts.view", "alerts.manage", "assistant.use",
    },
    "stock": {
        "products.view", "stock.view", "stock.move", "stock.adjust", "stock.transfer", "waste.manage",
        "recipes.view", "suppliers.view", "purchases.view", "purchases.receive", "alerts.view",
    },
    "attendant": {"products.view", "orders.view", "orders.manage", "sales.view", "recipes.view"},
    "kitchen": {"orders.view", "kitchen.update", "recipes.view", "products.view", "waste.manage"},
}


def permissions_for(membership):
    if membership is None or not membership.is_active:
        return set()
    perms = set(ROLE_PERMISSIONS.get(membership.role, set()))
    perms |= {p for p in membership.extra_permissions if p in ALL_PERMISSIONS}
    if membership.role != "owner":
        perms -= set(membership.revoked_permissions)
    return perms


class HasTenantPermission(BasePermission):
    """Exige que a view declare `required_permissions` (por ação) e que o usuário as possua.

    `required_permissions` pode ser um dict {acao: codigo} com a chave "*" como padrão,
    ou um código único.
    """

    message = "Você não tem permissão para realizar esta ação."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        if membership is None:
            return False
        required = getattr(view, "required_permissions", None)
        if required is None:
            return False  # nega por padrão: toda view precisa declarar sua permissão
        if isinstance(required, dict):
            action = getattr(view, "action", None) or request.method.lower()
            code = required.get(action, required.get("*"))
        else:
            code = required
        if code is None:
            return False
        codes = code if isinstance(code, (list, tuple)) else [code]
        perms = getattr(request, "perms", None)
        if perms is None:
            perms = request.perms = permissions_for(membership)
        return all(c in perms for c in codes)
