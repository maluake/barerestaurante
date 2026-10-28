from decimal import Decimal

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessError
from apps.core.tenancy import TenantModelViewSet, audit
from apps.inventory.services import available_quantity

from .models import MenuCategory, MenuItem
from .serializers import CostSnapshotSerializer, MenuCategorySerializer, MenuItemSerializer, RevisionSerializer
from .services import compute_cost, requirements_per_portion


class MenuCategoryViewSet(TenantModelViewSet):
    serializer_class = MenuCategorySerializer
    queryset = MenuCategory.objects.all()
    pagination_class = None
    required_permissions = {"list": ("orders.view",), "retrieve": "orders.view", "*": "recipes.manage"}

    def check_permissions(self, request):
        if self.action in ("list", "retrieve") and (self.has_perm("orders.view") or self.has_perm("recipes.view")):
            return
        super().check_permissions(request)


class MenuItemViewSet(TenantModelViewSet):
    serializer_class = MenuItemSerializer
    queryset = MenuItem.objects.select_related("category", "direct_product", "direct_unit").prefetch_related(
        "ingredients__product__unit", "ingredients__unit")
    required_permissions = {"cost": "costs.view", "history": "recipes.view", "toggle_availability": "orders.manage",
                            "*": "recipes.manage"}
    filterset_fields = ["category", "stock_mode", "is_available", "status", "requires_preparation"]
    search_fields = ["name", "pos_code", "description"]
    ordering_fields = ["name", "price", "theoretical_cost"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def check_permissions(self, request):
        # Leitura do cardápio: atendentes (pedidos) e cozinha (receitas).
        if self.action in ("list", "retrieve", "availability") and (
                self.has_perm("orders.view") or self.has_perm("recipes.view")):
            return
        super().check_permissions(request)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list" and not self.request.query_params.get("status"):
            qs = qs.filter(status="active")
        if self.request.query_params.get("missing_recipe") == "1":
            qs = qs.filter(stock_mode="recipe", ingredients__isnull=True)
        return qs

    def get_serializer(self, *args, **kwargs):
        ser = super().get_serializer(*args, **kwargs)
        # Quem não vê custos não recebe custo e margem na resposta.
        if not self.has_perm("costs.view"):
            target = getattr(ser, "child", ser)
            for f in ("theoretical_cost", "contribution_margin", "margin_percent", "cost_complete"):
                target.fields.pop(f, None)
        return ser

    @action(detail=True, methods=["get"])
    def cost(self, request, pk=None):
        item = self.get_object()
        data = compute_cost(item)
        data["snapshots"] = CostSnapshotSerializer(item.cost_snapshots.all()[:60], many=True).data
        data["policy"] = ("Custo teórico calculado pelo custo de reposição (último custo de compra) de cada ingrediente, "
                          "incluindo perdas de preparo. O consumo real é medido pelas movimentações de estoque.")
        return Response(data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        item = self.get_object()
        return Response(RevisionSerializer(item.revisions.select_related("user")[:50], many=True).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        item = self.get_object()
        item.status = "archived" if item.status == "active" else "active"
        item.save(update_fields=["status", "updated_at"])
        audit(request, item.status, item, summary=item.name)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"], url_path="toggle-availability")
    def toggle_availability(self, request, pk=None):
        item = self.get_object()
        item.is_available = not item.is_available
        item.save(update_fields=["is_available", "updated_at"])
        audit(request, "availability", item, summary=f"{item.name}: {'disponível' if item.is_available else 'indisponível'}")
        return Response(self.get_serializer(item).data)

    @action(detail=False, methods=["get"])
    def availability(self, request):
        """Quantas porções podem ser produzidas com o estoque disponível (lotes vencidos excluídos)."""
        result = []
        cache = {}
        for item in MenuItem.objects.filter(organization=request.org, status="active").select_related(
                "direct_product__unit").prefetch_related("ingredients__product__unit", "ingredients__unit"):
            try:
                req = requirements_per_portion(item)
            except BusinessError:
                req = None
            if req is None:
                result.append({"id": item.id, "name": item.name, "portions": None, "limiting": None,
                               "is_available": item.is_available, "note": "Sem ficha técnica"})
                continue
            if not req:
                result.append({"id": item.id, "name": item.name, "portions": None, "limiting": None,
                               "is_available": item.is_available, "note": "Sem controle de estoque"})
                continue
            portions = None
            limiting = None
            for product, qty in req:
                if qty <= 0:
                    continue
                if product.pk not in cache:
                    cache[product.pk] = available_quantity(request.unit, product)
                can = (cache[product.pk] / qty).to_integral_value(rounding="ROUND_FLOOR") if qty else Decimal("0")
                can = max(can, Decimal("0"))
                if portions is None or can < portions:
                    portions, limiting = can, product.name
            result.append({"id": item.id, "name": item.name, "portions": portions, "limiting": limiting,
                           "is_available": item.is_available, "note": ""})
        return Response(result)
