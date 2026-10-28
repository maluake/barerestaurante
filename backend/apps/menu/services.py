"""Fichas técnicas e custeio teórico.

Política de custeio (documentada em docs/REGRAS_DE_NEGOCIO.md):
- Custo TEÓRICO da receita = soma dos ingredientes (quantidade bruta) × custo de
  reposição do produto (`Product.cost_price`, último custo de compra recebido).
- Quantidade bruta = quantidade líquida / (1 − perda de preparo %).
- O custo REAL (CMV) usa o custo dos lotes efetivamente consumidos (FEFO) e é
  calculado a partir das movimentações de estoque.
"""

from decimal import Decimal

from django.utils import timezone

from apps.core.exceptions import BusinessError
from apps.inventory.units import convert

from .models import MenuItem, MenuItemCostSnapshot

Q4 = Decimal("0.0001")


def gross_quantity(ingredient):
    loss = Decimal(ingredient.loss_percent or 0)
    if loss >= 100:
        raise BusinessError("A perda de preparo deve ser menor que 100%.")
    return Decimal(ingredient.quantity) / (1 - loss / 100)


def requirements_per_portion(item):
    """Lista de (produto, quantidade na unidade de estoque) para UMA porção vendida."""
    if item.stock_mode == "none":
        return []
    if item.stock_mode == "direct":
        if not item.direct_product_id or not item.direct_quantity:
            return None
        unit = item.direct_unit or item.direct_product.unit
        return [(item.direct_product, convert(item.direct_quantity, unit, item.direct_product.unit, item.direct_product))]
    ingredients = list(item.ingredients.select_related("product", "product__unit", "unit"))
    if not ingredients:
        return None  # sem ficha técnica: baixa automática não confiável
    yield_portions = Decimal(item.yield_portions or 1)
    result = []
    for ing in ingredients:
        qty = convert(gross_quantity(ing), ing.unit, ing.product.unit, ing.product) / yield_portions
        result.append((ing.product, qty))
    return result


def compute_cost(item):
    """Retorna dict com custo por porção, custo total da receita e detalhamento."""
    lines = []
    complete = True
    total = Decimal("0")
    if item.stock_mode == "direct" and item.direct_product_id:
        req = requirements_per_portion(item) or []
        for product, qty in req:
            cost = qty * product.cost_price
            if not product.cost_price:
                complete = False
            lines.append({"product_id": product.pk, "product": product.name, "quantity": qty.quantize(Q4),
                          "unit": product.unit.code, "unit_cost": product.cost_price, "cost": cost.quantize(Q4)})
            total += cost
        per_portion = total
    elif item.stock_mode == "recipe":
        for ing in item.ingredients.select_related("product", "product__unit", "unit"):
            gross = convert(gross_quantity(ing), ing.unit, ing.product.unit, ing.product)
            cost = gross * ing.product.cost_price
            if not ing.product.cost_price:
                complete = False
            lines.append({
                "ingredient_id": ing.pk, "product_id": ing.product_id, "product": ing.product.name,
                "quantity": ing.quantity, "unit": ing.unit.code, "loss_percent": ing.loss_percent,
                "gross_quantity": gross.quantize(Q4), "stock_unit": ing.product.unit.code,
                "unit_cost": ing.product.cost_price, "cost": cost.quantize(Q4),
            })
            total += cost
        if not lines:
            complete = False
        per_portion = total / Decimal(item.yield_portions or 1)
    else:
        per_portion = Decimal("0")
        complete = False
    price = Decimal(item.price)
    margin = price - per_portion
    return {
        "recipe_total_cost": total.quantize(Q4),
        "cost_per_portion": per_portion.quantize(Q4),
        "price": price,
        "contribution_margin": margin.quantize(Decimal("0.01")),
        "margin_percent": (margin / price * 100).quantize(Decimal("0.1")) if price else None,
        "complete": complete,
        "lines": lines,
    }


def recalculate(item, reason="", at=None):
    data = compute_cost(item)
    at = at or timezone.now()
    changed = data["cost_per_portion"] != item.theoretical_cost or data["complete"] != item.cost_complete
    last = item.cost_snapshots.first()
    MenuItem.objects.filter(pk=item.pk).update(
        theoretical_cost=data["cost_per_portion"], cost_complete=data["complete"], cost_updated_at=at
    )
    item.theoretical_cost = data["cost_per_portion"]
    item.cost_complete = data["complete"]
    if changed or last is None or last.price != item.price:
        MenuItemCostSnapshot.objects.create(
            menu_item=item, cost_per_portion=data["cost_per_portion"], price=item.price, reason=reason[:120],
            created_at=at,
        )
    return data


def recalculate_items_using(product, at=None):
    items = MenuItem.objects.filter(organization_id=product.organization_id).filter(
        ingredients__product=product
    ) | MenuItem.objects.filter(organization_id=product.organization_id, direct_product=product)
    for item in items.distinct():
        recalculate(item, reason=f"Custo de {product.name} alterado", at=at)
