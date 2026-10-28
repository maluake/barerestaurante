"""Pedidos, vendas e integração com o estoque.

Regra de baixa de ingredientes (documentada em docs/REGRAS_DE_NEGOCIO.md):
- Pedido "Recebido": nenhuma movimentação (a demanda entra apenas na projeção de compras).
- Ao ser "Confirmado": os ingredientes da ficha técnica são baixados por FEFO, uma única
  vez (chave idempotente `order:<id>:consume`). Mudanças de status seguintes não baixam de novo.
- Cancelado após confirmado e ANTES do preparo: estorno integral (ingredientes voltam ao estoque).
- Cancelado DURANTE/APÓS o preparo: a baixa é estornada e os ingredientes são registrados
  como perda ("pedido cancelado em preparo"), deixando o desperdício visível.
- Ao ser "Entregue": a venda é registrada (receita) usando a baixa já feita, sem nova baixa.
- Vendas diretas e importadas baixam o estoque na criação (`sale:<id>:consume`).
"""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessError
from apps.core.setup import next_number
from apps.inventory import services as stock
from apps.menu.services import requirements_per_portion

from .models import Order, OrderEvent, OrderItem, Sale, SaleItem

ZERO = Decimal("0")
C2 = Decimal("0.01")

TRANSITIONS = {
    "received": {"confirmed", "cancelled"},
    "confirmed": {"preparing", "ready", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"dispatched", "delivered", "cancelled"},
    "dispatched": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}


def allowed_transitions(order):
    allowed = set(TRANSITIONS[order.status])
    if order.origin != "delivery" and order.origin != "app":
        allowed.discard("dispatched")
    if order.status == "confirmed" and order.requires_kitchen:
        allowed.discard("ready")  # itens de cozinha passam por "Em preparo"
    if order.status == "confirmed" and not order.requires_kitchen:
        allowed.discard("preparing")
    return allowed


def _consume_items(op, unit, lines, *, user, occurred_at, ref_type, ref_id):
    """Baixa os ingredientes. `lines`: [(menu_item, quantidade, objeto_linha)]. Retorna (custo_por_linha, avisos)."""
    costs = {}
    warnings = {}
    for menu_item, qty, line in lines:
        req = requirements_per_portion(menu_item)
        if req is None:
            warnings[line] = "Item sem ficha técnica: baixa automática não realizada."
            continue
        line_cost = ZERO
        for product, per_portion in req:
            total_qty = (per_portion * Decimal(qty)).quantize(Decimal("0.0001"))
            if total_qty <= 0:
                continue
            movements = stock.remove_stock(
                op, unit, product, total_qty, type_="sale", user=user, occurred_at=occurred_at,
                reason=f"{menu_item.name} × {Decimal(qty).normalize()}", ref_type=ref_type, ref_id=ref_id,
                allow_negative=True,
            )
            line_cost += sum((m.total_cost for m in movements), ZERO)
        costs[line] = line_cost
    return costs, warnings


def operation_cost(op):
    """CMV líquido de uma operação (saídas menos estornos)."""
    if op is None:
        return ZERO
    total = sum((m.total_cost for m in op.movements.all()), ZERO)
    if op.reversed_by_id:
        return ZERO
    return total


# --------------------------------------------------------------------------- pedidos


def create_order(org, unit, user, *, items, origin="counter", table_label="", customer_name="", notes="",
                 discount=ZERO, delivery_fee=ZERO, payment_method="", client_reference=None, created_at=None):
    if not items:
        raise BusinessError("Inclua ao menos um item no pedido.")
    with transaction.atomic():
        if client_reference:
            existing = Order.objects.filter(organization=org, client_reference=client_reference).first()
            if existing:
                return existing, False
        at = created_at or timezone.now()
        order = Order.objects.create(
            organization=org, unit=unit, number=next_number(Order, org), origin=origin, table_label=table_label,
            customer_name=customer_name, notes=notes, discount=discount or ZERO, delivery_fee=delivery_fee or ZERO,
            payment_method=payment_method, client_reference=client_reference, created_by=user, created_at=at,
        )
        subtotal = ZERO
        for it in items:
            mi = it["menu_item"]
            if mi.organization_id != org.pk or mi.status != "active":
                raise BusinessError("Item do cardápio inválido.")
            if not mi.is_available:
                raise BusinessError(f"{mi.name} está indisponível no momento.")
            qty = Decimal(it["quantity"])
            if qty <= 0:
                raise BusinessError("Quantidade deve ser maior que zero.")
            OrderItem.objects.create(order=order, menu_item=mi, quantity=qty, unit_price=mi.price, notes=it.get("notes", ""))
            subtotal += qty * mi.price
        if order.discount > subtotal:
            raise BusinessError("O desconto não pode ser maior que o valor dos itens.")
        order.subtotal = subtotal.quantize(C2)
        order.total = (subtotal - order.discount + order.delivery_fee).quantize(C2)
        order.save(update_fields=["subtotal", "total"])
        OrderEvent.objects.create(order=order, to_status="received", user=user, created_at=at)
        return order, True


def change_order_status(order, new_status, user, *, note="", at=None, can_cancel_confirmed=False, payment_method=None):
    at = at or timezone.now()
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if new_status == order.status:
            return order  # idempotente: repetir o mesmo status não gera efeitos
        if new_status not in allowed_transitions(order):
            raise BusinessError(
                f"Não é possível mudar de '{order.get_status_display()}' para '{dict(Order.STATUS).get(new_status, new_status)}'.")
        if new_status == "cancelled":
            if order.status != "received" and not can_cancel_confirmed:
                raise BusinessError("Somente gerente ou proprietário pode cancelar pedidos já confirmados.")
            if not note:
                raise BusinessError("Informe o motivo do cancelamento.", field="note")
        previous = order.status
        if new_status == "confirmed":
            _consume_order(order, user, at)
            order.confirmed_at = at
        elif new_status == "preparing":
            order.preparing_at = at
        elif new_status == "ready":
            order.ready_at = at
        elif new_status == "delivered":
            order.delivered_at = at
            if payment_method:
                order.payment_method = payment_method
            _register_sale_from_order(order, user, at)
        elif new_status == "cancelled":
            _cancel_order_stock(order, previous, user, at, note)
            order.cancelled_at = at
            order.cancel_reason = note
        order.status = new_status
        order.save()
        OrderEvent.objects.create(order=order, from_status=previous, to_status=new_status, note=note[:255], user=user, created_at=at)
        return order


def _consume_order(order, user, at):
    try:
        op = stock.begin_operation(order.organization, order.unit, f"order:{order.pk}:consume", "order_consumption", user,
                                   f"Baixa do pedido #{order.number}")
    except stock.AlreadyProcessed:
        return
    items = list(order.items.select_related("menu_item"))
    lines = [(i.menu_item, i.quantity, i) for i in items if i.menu_item.stock_mode != "none"]
    _, warnings = _consume_items(op, order.unit, lines, user=user, occurred_at=at, ref_type="order", ref_id=order.pk)
    for item, msg in warnings.items():
        item.stock_warning = msg
        item.save(update_fields=["stock_warning"])
    order.stock_operation = op
    if not lines:
        order.stock_status = "not_applicable"
    else:
        order.stock_status = "partial" if warnings else "consumed"


def _cancel_order_stock(order, previous, user, at, note):
    op = order.stock_operation
    if op is None:
        order.stock_status = "not_applicable" if order.stock_status != "pending" else "pending"
        return
    if previous == "confirmed":
        stock.reverse_operation(op, user=user, reason=f"Pedido #{order.number} cancelado antes do preparo", occurred_at=at)
        order.stock_status = "reversed"
        return
    # Já em preparo: ingredientes não voltam ao estoque; viram perda registrada.
    _convert_consumption_to_waste(op, order.unit, user, at, reason="cancelled_order",
                                  notes=f"Pedido #{order.number} cancelado: {note}")
    order.stock_status = "wasted"


def _convert_consumption_to_waste(op, unit, user, at, reason, notes):
    totals = defaultdict(lambda: ZERO)
    products = {}
    for mv in op.movements.select_related("product"):
        totals[mv.product_id] += -mv.quantity
        products[mv.product_id] = mv.product
    stock.reverse_operation(op, user=user, reason=notes, occurred_at=at)
    for pid, qty in totals.items():
        if qty > 0:
            stock.record_waste(unit, products[pid], qty, reason, user=user, notes=notes, occurred_at=at,
                               key=f"waste:{op.key}:{pid}", allow_negative=True)


def _register_sale_from_order(order, user, at):
    if Sale.objects.filter(order=order).exists():
        return
    org = order.organization
    fee = ZERO
    if order.origin == "app":
        fee = (order.subtotal - order.discount) * Decimal(str(org.setting("delivery_app_fee_percent"))) / 100
    items = list(order.items.select_related("menu_item"))
    gross = sum((i.quantity * i.unit_price for i in items), ZERO)
    sale = Sale.objects.create(
        organization=org, unit=order.unit, order=order, source="order", channel=order.origin,
        payment_method=order.payment_method, occurred_at=at, gross_amount=gross.quantize(C2),
        discount_amount=order.discount, fee_amount=fee.quantize(C2), delivery_fee=order.delivery_fee,
        net_amount=(gross - order.discount - fee + order.delivery_fee).quantize(C2),
        stock_status=order.stock_status, stock_operation=order.stock_operation, created_by=user,
    )
    sale.cogs = operation_cost(order.stock_operation)
    sale.save(update_fields=["cogs"])
    for i in items:
        SaleItem.objects.create(sale=sale, menu_item=i.menu_item, description=i.menu_item.name, quantity=i.quantity,
                                unit_price=i.unit_price, total=(i.quantity * i.unit_price).quantize(C2),
                                theoretical_cost=i.menu_item.theoretical_cost, stock_warning=i.stock_warning)
    return sale


# --------------------------------------------------------------------------- vendas diretas / importadas


def register_sale(org, unit, user, *, items, channel="counter", payment_method="", discount=ZERO, fee=ZERO,
                  delivery_fee=ZERO, occurred_at=None, source="direct", external_id=None, import_batch=None,
                  cancelled_reason=None):
    """Registra uma venda concluída e baixa o estoque. `items`: [{menu_item?, description, quantity, unit_price,
    discount?, external_code?}]. Idempotente por (source, external_id)."""
    occurred_at = occurred_at or timezone.now()
    if not items:
        raise BusinessError("A venda precisa de ao menos um item.")
    with transaction.atomic():
        if external_id:
            existing = Sale.objects.filter(organization=org, source=source, external_id=external_id).first()
            if existing:
                return existing, False
        gross = ZERO
        item_discounts = ZERO
        for it in items:
            if Decimal(it["quantity"]) <= 0:
                raise BusinessError("Quantidade deve ser maior que zero.")
            if Decimal(it["unit_price"]) < 0:
                raise BusinessError("Preço não pode ser negativo.")
            gross += Decimal(it["quantity"]) * Decimal(it["unit_price"])
            item_discounts += Decimal(it.get("discount") or 0)
        total_discount = Decimal(discount or 0) + item_discounts
        if total_discount > gross:
            raise BusinessError("O desconto não pode ser maior que o valor bruto da venda.")
        fee = Decimal(fee or 0)
        sale = Sale.objects.create(
            organization=org, unit=unit, source=source, external_id=external_id, channel=channel,
            payment_method=payment_method, occurred_at=occurred_at, gross_amount=gross.quantize(C2),
            discount_amount=total_discount.quantize(C2), fee_amount=fee.quantize(C2), delivery_fee=Decimal(delivery_fee or 0),
            net_amount=(gross - total_discount - fee + Decimal(delivery_fee or 0)).quantize(C2), created_by=user,
            import_batch=import_batch,
        )
        sale_items = []
        for it in items:
            mi = it.get("menu_item")
            sale_items.append(SaleItem.objects.create(
                sale=sale, menu_item=mi, description=it.get("description") or (mi.name if mi else "Item"),
                external_code=it.get("external_code", ""), quantity=it["quantity"], unit_price=it["unit_price"],
                discount=it.get("discount") or 0,
                total=(Decimal(it["quantity"]) * Decimal(it["unit_price"]) - Decimal(it.get("discount") or 0)).quantize(C2),
                theoretical_cost=mi.theoretical_cost if mi else 0,
            ))
        if cancelled_reason:
            # Venda já cancelada na origem (ex.: PDV): registrada para análise, sem baixa de estoque.
            sale.status = "cancelled"
            sale.cancelled_at = occurred_at
            sale.cancel_reason = cancelled_reason[:255]
            sale.stock_status = "not_applicable"
            sale.save(update_fields=["status", "cancelled_at", "cancel_reason", "stock_status"])
            return sale, True
        lines = [(si.menu_item, si.quantity, si) for si in sale_items if si.menu_item and si.menu_item.stock_mode != "none"]
        unmapped = [si for si in sale_items if si.menu_item is None]
        for si in unmapped:
            si.stock_warning = "Produto do PDV não mapeado para o cardápio: baixa não realizada."
            si.save(update_fields=["stock_warning"])
        if lines:
            op = stock.begin_operation(org, unit, f"sale:{sale.pk}:consume", "sale_consumption", user, f"Baixa da venda #{sale.pk}")
            _, warnings = _consume_items(op, unit, lines, user=user, occurred_at=occurred_at, ref_type="sale", ref_id=sale.pk)
            for si, msg in warnings.items():
                si.stock_warning = msg
                si.save(update_fields=["stock_warning"])
            sale.stock_operation = op
            sale.stock_status = "partial" if (warnings or unmapped) else "consumed"
            sale.cogs = operation_cost(op)
        else:
            sale.stock_status = "partial" if unmapped else "not_applicable"
        sale.save(update_fields=["stock_operation", "stock_status", "cogs"])
        return sale, True


def cancel_sale(sale, user, reason, *, return_to_stock=False):
    """Cancela uma venda. Se `return_to_stock`, estorna a baixa (ex.: bebida lacrada devolvida);
    caso contrário, os itens já consumidos são registrados como perda (devolução)."""
    if not reason:
        raise BusinessError("Informe o motivo do cancelamento.", field="reason")
    at = timezone.now()
    with transaction.atomic():
        sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if sale.status == "cancelled":
            return sale
        op = sale.stock_operation
        if op is not None and not op.reversed_by_id:
            if return_to_stock:
                stock.reverse_operation(op, user=user, reason=f"Venda #{sale.pk} cancelada: {reason}", occurred_at=at)
                sale.stock_status = "reversed"
            else:
                _convert_consumption_to_waste(op, sale.unit, user, at, reason="returned",
                                              notes=f"Venda #{sale.pk} cancelada: {reason}")
                sale.stock_status = "wasted"
        sale.status = "cancelled"
        sale.cancelled_at = at
        sale.cancelled_by = user
        sale.cancel_reason = reason[:255]
        sale.save()
        if sale.order_id and sale.order.status != "cancelled":
            Order.objects.filter(pk=sale.order_id).update(status="cancelled", cancelled_at=at, cancel_reason=reason[:255],
                                                          stock_status=sale.stock_status)
            OrderEvent.objects.create(order_id=sale.order_id, from_status="delivered", to_status="cancelled",
                                      note=f"Venda cancelada: {reason}"[:255], user=user, created_at=at)
        return sale

