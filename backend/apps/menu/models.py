from django.conf import settings
from django.db import models

from apps.core.models import TenantModel
from apps.inventory.models import MONEY, QTY, UNIT_COST, Product, UnitOfMeasure


class MenuCategory(TenantModel):
    name = models.CharField(max_length=80)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class MenuItem(TenantModel):
    """Item vendido (prato, porção, drink...) com sua ficha técnica."""

    STOCK_MODES = [
        ("recipe", "Baixa pela ficha técnica"),
        ("direct", "Revenda direta de um produto"),
        ("none", "Sem baixa automática"),
    ]
    STATUS = [("active", "Ativo"), ("archived", "Arquivado")]

    name = models.CharField(max_length=150)
    category = models.ForeignKey(MenuCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="items")
    description = models.TextField(blank=True)
    price = models.DecimalField("preço de venda", **MONEY)
    stock_mode = models.CharField(max_length=10, choices=STOCK_MODES, default="recipe")
    direct_product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    direct_quantity = models.DecimalField(**QTY, null=True, blank=True)
    direct_unit = models.ForeignKey(UnitOfMeasure, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    yield_portions = models.DecimalField("rendimento (porções)", max_digits=8, decimal_places=2, default=1)
    requires_preparation = models.BooleanField("vai para a cozinha", default=True)
    prep_time_minutes = models.PositiveIntegerField(null=True, blank=True)
    is_available = models.BooleanField("disponível para venda", default=True)
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    pos_code = models.CharField("código no PDV", max_length=60, blank=True)
    # Custo teórico por porção calculado pela política de custeio (custo de reposição).
    theoretical_cost = models.DecimalField(**UNIT_COST, default=0)
    cost_complete = models.BooleanField(default=False)
    cost_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def has_reliable_recipe(self):
        if self.stock_mode == "recipe":
            return self.ingredients.exists()
        if self.stock_mode == "direct":
            return bool(self.direct_product_id and self.direct_quantity)
        return True


class RecipeIngredient(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="ingredients")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="recipe_uses")
    quantity = models.DecimalField("quantidade líquida para a receita", **QTY)
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="+")
    loss_percent = models.DecimalField("perda de preparo (%)", max_digits=5, decimal_places=2, default=0)
    notes = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["id"]


class MenuItemCostSnapshot(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="cost_snapshots")
    cost_per_portion = models.DecimalField(**UNIT_COST)
    price = models.DecimalField(**MONEY)
    reason = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]


class MenuItemRevision(models.Model):
    """Histórico de alterações do item e da ficha técnica."""

    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="revisions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    summary = models.CharField(max_length=255)
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
