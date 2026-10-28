"""Compras: comparador de cotações, lista inteligente, pedidos e recebimento."""

import re
from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import BusinessError
from apps.core.setup import next_number
from apps.inventory import services as stock
from apps.inventory.analytics import consumption_rates, forecast_for_day
from apps.inventory.models import Lot, Product, StockBalance
from apps.inventory.units import IncompatibleUnits, convert

from .models import (
    PurchaseIssue,
    PurchaseOrder,
    PurchaseOrderItem,
    Quotation,
    Receipt,
    ReceiptItem,
    ShoppingList,
    ShoppingListItem,
)

ZERO = Decimal("0")
C2 = Decimal("0.01")
Q4 = Decimal("0.0001")
OPEN_PO_STATUSES = ("approved", "sent", "partially_received")


def round_purchase_quantity(units, purchase_unit, min_quantity):
    if purchase_unit.dimension in ("count", "package"):
        units = units.to_integral_value(rounding=ROUND_CEILING)
    else:
        units = units.quantize(Decimal("0.001"), rounding=ROUND_CEILING)
    return max(units, Decimal(min_quantity or 0))


# --------------------------------------------------------------------------- comparador


def latest_quotes(org, product, include_expired=True):
    """Cotação mais recente de cada fornecedor para o produto."""
    seen = set()
    result = []
    qs = Quotation.objects.filter(organization=org, product=product, supplier__is_active=True).select_related(
        "supplier", "purchase_unit", "product__unit").order_by("-quoted_at", "-id")
    for q in qs:
        if q.supplier_id in seen:
            continue
        seen.add(q.supplier_id)
        result.append(q)
    return result


def evaluate_quote(q, product, needed, today, stale_days):
    """Calcula o custo total viável de comprar `needed` (unidade de estoque) com a cotação `q`."""
    res = {
        "quotation_id": q.pk, "supplier_id": q.supplier_id, "supplier_name": str(q.supplier),
        "supplier_is_demo": q.supplier.is_demo, "price": q.price, "purchase_unit": q.purchase_unit.code,
        "purchase_unit_id": q.purchase_unit_id, "quoted_at": q.quoted_at, "valid_until": q.valid_until,
        "brand": q.brand, "payment_terms": q.payment_terms or q.supplier.payment_terms,
        "quality_rating": q.supplier.quality_rating, "punctuality_rating": q.supplier.punctuality_rating,
        "product_expiry": q.product_expiry, "issues": [], "viable": True,
    }
    age = (today - q.quoted_at).days
    res["age_days"] = age
    res["stale"] = age > stale_days
    if res["stale"]:
        res["issues"].append(f"Cotação consultada há {age} dias: confirme o preço antes de comprar.")
    if q.valid_until and q.valid_until < today:
        res["viable"] = False
        res["expired"] = True
        res["issues"].append("Cotação vencida.")
    try:
        per_unit = convert(1, q.purchase_unit, product.unit, product)
    except IncompatibleUnits:
        res["viable"] = False
        res["issues"].append(f"Sem conversão cadastrada entre {q.purchase_unit.code} e {product.unit.code}.")
        return res
    units = round_purchase_quantity(Decimal(needed) / per_unit, q.purchase_unit, q.min_quantity)
    subtotal = (units * q.price).quantize(C2)
    discount = (subtotal * q.discount_percent / 100).quantize(C2)
    freight = q.freight if q.freight else q.supplier.delivery_fee
    total = subtotal - discount + freight
    effective_qty = units * per_unit
    delivery_days = q.delivery_days if q.delivery_days is not None else q.supplier.delivery_days
    res.update({
        "stock_units_per_purchase_unit": per_unit.quantize(Q4),
        "price_per_stock_unit": (q.price / per_unit).quantize(Q4),
        "units_to_buy": units, "effective_quantity": effective_qty.quantize(Q4), "surplus": (effective_qty - Decimal(needed)).quantize(Q4),
        "subtotal": subtotal, "discount": discount, "freight": freight, "total": total.quantize(C2),
        "cost_per_needed_unit": (total / Decimal(needed)).quantize(Q4) if needed else None,
        "delivery_days": delivery_days, "expected_delivery": today + timedelta(days=delivery_days),
        "min_quantity": q.min_quantity,
    })
    if q.min_quantity and Decimal(needed) / per_unit < q.min_quantity:
        res["issues"].append(f"Quantidade mínima de {q.min_quantity.normalize()} {q.purchase_unit.code} eleva a compra.")
    if q.available_quantity is not None and q.available_quantity < units:
        res["viable"] = False
        res["issues"].append(f"Fornecedor informou apenas {q.available_quantity.normalize()} {q.purchase_unit.code} disponíveis.")
    if q.supplier.min_order_value and subtotal - discount < q.supplier.min_order_value:
        res["issues"].append(f"Abaixo do pedido mínimo do fornecedor (R$ {q.supplier.min_order_value}). Pode ser viável combinado com outros itens.")
        res["below_min_order"] = True
    if product.is_perishable and q.product_expiry and q.product_expiry < today + timedelta(days=2):
        res["issues"].append("Validade informada muito curta para o produto.")
    return res


def compare_product(org, product, needed, today=None):
    today = today or timezone.localdate()
    stale_days = int(org.setting("stale_quote_days"))
    rows = [evaluate_quote(q, product, Decimal(needed), today, stale_days) for q in latest_quotes(org, product)]
    viable = sorted([r for r in rows if r["viable"] and not r.get("below_min_order")], key=lambda r: (r["total"], r["delivery_days"]))
    others = sorted([r for r in rows if r not in viable], key=lambda r: (not r["viable"], r.get("total") or Decimal("1e12")))
    ranked = viable + others
    best = viable[0] if viable else None
    for r in ranked:
        r["is_best"] = best is not None and r is best
        if best and r.get("total") is not None and r is not best:
            r["difference_vs_best"] = (r["total"] - best["total"]).quantize(C2)
    lowest_price = min((r for r in rows if r.get("price_per_stock_unit")), key=lambda r: r["price_per_stock_unit"], default=None)
    note = None
    if best and lowest_price and lowest_price is not best:
        note = (f"O menor preço anunciado é de {lowest_price['supplier_name']}, mas o menor custo total viável é de "
                f"{best['supplier_name']} considerando quantidade mínima, frete, descontos e disponibilidade.")
    return {"product_id": product.pk, "product": product.name, "unit": product.unit.code, "needed": Decimal(needed),
            "best": best, "quotes": ranked, "note": note, "stale_days": stale_days}


def compare_list(org, items, today=None):
    """Compara uma lista de produtos: melhor fornecedor único e melhor divisão (frete contado uma vez por fornecedor)."""
    today = today or timezone.localdate()
    stale_days = int(org.setting("stale_quote_days"))
    per_product = {}
    suppliers = {}
    for product, needed in items:
        quotes = {}
        for q in latest_quotes(org, product):
            r = evaluate_quote(q, product, Decimal(needed), today, stale_days)
            if r["viable"]:
                quotes[q.supplier_id] = r
                suppliers[q.supplier_id] = q.supplier
        per_product[product.pk] = {"product": product, "needed": needed, "quotes": quotes}

    def goods(r):
        return r["subtotal"] - r["discount"]

    single = []
    for sid, sup in suppliers.items():
        covered = [p for p in per_product.values() if sid in p["quotes"]]
        goods_total = sum((goods(p["quotes"][sid]) for p in covered), ZERO)
        single.append({
            "supplier_id": sid, "supplier_name": str(sup), "covers": len(covered), "of": len(per_product),
            "goods_total": goods_total, "freight": sup.delivery_fee, "total": goods_total + sup.delivery_fee,
            "meets_min_order": goods_total >= sup.min_order_value, "min_order_value": sup.min_order_value,
        })
    single.sort(key=lambda s: (-s["covers"], s["total"]))

    # Divisão: cada produto no fornecedor mais barato (sem frete), depois consolida se o frete economizado compensar.
    assignment = {}
    for pid, p in per_product.items():
        if p["quotes"]:
            assignment[pid] = min(p["quotes"].values(), key=goods)["supplier_id"]

    def split_total(assign):
        used = set(assign.values())
        return sum((goods(per_product[pid]["quotes"][sid]) for pid, sid in assign.items()), ZERO) + sum(
            (suppliers[s].delivery_fee for s in used), ZERO)

    improved = True
    while improved:
        improved = False
        current = split_total(assignment)
        for s in set(assignment.values()):
            moved = dict(assignment)
            ok = True
            for pid, sid in assignment.items():
                if sid != s:
                    continue
                alternatives = [r for k, r in per_product[pid]["quotes"].items() if k != s and k in set(assignment.values())]
                if not alternatives:
                    ok = False
                    break
                moved[pid] = min(alternatives, key=goods)["supplier_id"]
            if ok and split_total(moved) < current:
                assignment = moved
                improved = True
                break

    split = defaultdict(lambda: {"items": [], "goods_total": ZERO})
    for pid, sid in assignment.items():
        r = per_product[pid]["quotes"][sid]
        split[sid]["items"].append({"product_id": pid, "product": per_product[pid]["product"].name,
                                    "units_to_buy": r["units_to_buy"], "purchase_unit": r["purchase_unit"],
                                    "total": goods(r), "quotation_id": r["quotation_id"], "stale": r["stale"]})
        split[sid]["goods_total"] += goods(r)
    split_rows = []
    for sid, data in split.items():
        sup = suppliers[sid]
        split_rows.append({"supplier_id": sid, "supplier_name": str(sup), **data, "freight": sup.delivery_fee,
                           "meets_min_order": data["goods_total"] >= sup.min_order_value,
                           "min_order_value": sup.min_order_value})
    missing = [{"product_id": pid, "product": p["product"].name} for pid, p in per_product.items() if not p["quotes"]]
    full = [s for s in single if s["covers"] == len(per_product)]
    return {
        "single_supplier": single,
        "best_single_supplier": full[0] if full else None,
        "best_split": {"suppliers": split_rows, "total": split_total(assignment) if assignment else ZERO},
        "missing_quotes": missing,
    }


# --------------------------------------------------------------------------- lista inteligente


def pending_purchases(unit, product_ids=None):
    """Itens de pedidos de compra aprovados/enviados ainda não recebidos: {product_id: [(data, qtd_estoque)]}."""
    items = PurchaseOrderItem.objects.filter(order__unit=unit, order__status__in=OPEN_PO_STATUSES).select_related(
        "order__supplier", "product__unit", "purchase_unit")
    if product_ids is not None:
        items = items.filter(product_id__in=product_ids)
    today = stock.today_for(unit)
    result = defaultdict(list)
    for it in items:
        pending = it.pending_quantity
        if pending <= 0:
            continue
        try:
            qty = convert(pending, it.purchase_unit, it.product.unit, it.product)
        except IncompatibleUnits:
            continue
        eta = it.order.expected_delivery or (today + timedelta(days=it.order.supplier.delivery_days))
        result[it.product_id].append((max(eta, today), qty, it.order))
    return result


def pending_order_demand(unit):
    """Demanda de pedidos de clientes registrados e ainda não confirmados (ingredientes ainda não baixados)."""
    from apps.menu.services import requirements_per_portion
    from apps.sales.models import OrderItem

    demand = defaultdict(lambda: ZERO)
    for oi in OrderItem.objects.filter(order__unit=unit, order__status="received").select_related("menu_item"):
        req = requirements_per_portion(oi.menu_item) or []
        for product, qty in req:
            demand[product.pk] += qty * oi.quantity
    return demand


def project_product(product, unit, org, today, rate_info, arrivals, extra_demand, horizon):
    """Simula o estoque dia a dia (FEFO, vencimentos, chegadas). Retorna a série projetada."""
    lots = [[l.expires_at, l.quantity_remaining] for l in Lot.objects.filter(
        unit=unit, product=product, status="active", quantity_remaining__gt=0).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=today)).order_by("expires_at", "id")]
    bal = StockBalance.objects.filter(unit=unit, product=product).first()
    physical = bal.quantity if bal else ZERO
    all_lots = sum((l.quantity_remaining for l in Lot.objects.filter(unit=unit, product=product, status="active")), ZERO)
    unlotted = physical - all_lots
    series = []
    expiring_loss = ZERO
    total_forecast = ZERO
    for d in range(horizon + 1):
        day = today + timedelta(days=d)
        for eta, qty, _ in arrivals:
            if eta == day:
                lots.append([None, qty])
        lots.sort(key=lambda l: (l[0] is None, l[0] or day))
        kept = []
        for l in lots:
            if l[0] is not None and l[0] < day:
                expiring_loss += l[1]
            else:
                kept.append(l)
        lots = kept
        need = forecast_for_day(rate_info, day, org) + (extra_demand if d == 0 else ZERO)
        total_forecast += need
        for l in lots:
            if need <= 0:
                break
            take = min(l[1], need)
            l[1] -= take
            need -= take
        if need > 0:
            unlotted -= need
        stock_level = sum((l[1] for l in lots), ZERO) + unlotted
        series.append((day, stock_level))
    return series, total_forecast, expiring_loss


def suggest_for_product(product, unit, org, today, rate_info, arrivals, extra_demand, coverage_days):
    quotes_cmp = compare_product(org, product, product.ideal_stock or product.min_stock or Decimal("1"), today)
    best = quotes_cmp["best"]
    lead = best["delivery_days"] if best else (product.main_supplier.delivery_days if product.main_supplier else 2)
    horizon = lead + coverage_days
    series, forecast, expiring_loss = project_product(product, unit, org, today, rate_info, arrivals, extra_demand, horizon)
    available_now = stock.available_quantity(unit, product)
    pending_total = sum((q for _, q, _ in arrivals), ZERO)
    min_s, ideal = product.min_stock or ZERO, product.ideal_stock or ZERO
    has_history = bool(rate_info and rate_info["rate"] > 0)
    confidence = "good" if has_history and rate_info["history_days"] >= 14 else "limited"
    reasons = []
    reorder_date = next((day for day, level in series if level < min_s or level < 0), None)
    p_end = series[-1][1]
    if has_history:
        if reorder_date is None:
            return None
        target = max(min_s, ZERO)
        suggested = target - p_end
        if ideal > min_s:
            at_arrival = next((lvl for day, lvl in series if day == today + timedelta(days=lead)), p_end)
            # Na chegada, o estoque deve voltar ao nível ideal.
            suggested = max(suggested, ideal - at_arrival)
        reasons.append(
            f"Estoque projetado ficará abaixo do mínimo ({min_s.normalize()} {product.unit.code}) em "
            f"{reorder_date.strftime('%d/%m')}" + (" — antes da próxima entrega possível." if reorder_date <= today + timedelta(days=lead) else ".")
        )
        reasons.append(f"Consumo previsto de {forecast.quantize(C2).normalize()} {product.unit.code} em {horizon} dias "
                       f"(prazo de entrega {lead}d + cobertura {coverage_days}d).")
    else:
        if available_now + pending_total >= min_s and not (available_now <= 0 and min_s == 0 and extra_demand > 0):
            return None
        suggested = (ideal or min_s) - available_now - pending_total + extra_demand
        reasons.append("Sem histórico de consumo suficiente: estimativa limitada, baseada no estoque mínimo e ideal.")
    if pending_total:
        reasons.append(f"Já considera {pending_total.quantize(C2).normalize()} {product.unit.code} em compras pendentes, nas datas previstas de entrega.")
    if expiring_loss > 0:
        reasons.append(f"{expiring_loss.quantize(C2).normalize()} {product.unit.code} devem vencer antes de serem consumidos.")
    if extra_demand > 0:
        reasons.append("Inclui ingredientes de pedidos registrados ainda não confirmados.")
    if suggested <= 0:
        return None
    caps = []
    if product.max_stock:
        start_level = series[min(lead, len(series) - 1)][1]
        cap = product.max_stock - max(start_level, ZERO)
        if cap < suggested:
            suggested = max(cap, ZERO)
            caps.append("limitada pela capacidade de armazenamento")
    if product.shelf_life_days and has_history:
        cap = rate_info["rate"] * product.shelf_life_days + min_s
        if cap < suggested:
            suggested = cap
            caps.append(f"limitada ao consumo previsto em {product.shelf_life_days} dias de validade, para evitar desperdício")
    if suggested <= 0:
        return None
    # Arredonda para a unidade de compra da melhor cotação e recalcula o custo.
    cmp_final = compare_product(org, product, suggested, today)
    best = cmp_final["best"]
    if best:
        rounded = best["effective_quantity"]
        cost = best["total"]
        supplier_id, quotation_id = best["supplier_id"], best["quotation_id"]
        purchase_txt = f"{best['units_to_buy'].normalize()} {best['purchase_unit']}"
    else:
        rounded = suggested.quantize(Decimal("0.001"), rounding=ROUND_CEILING)
        cost = (rounded * product.cost_price).quantize(C2)
        supplier_id, quotation_id = product.main_supplier_id, None
        purchase_txt = f"{rounded.normalize()} {product.unit.code}"
        reasons.append("Sem cotação válida: custo estimado pelo último custo de compra.")
    head = f"Recomendamos comprar {purchase_txt}"
    head += f" ({', '.join(caps)})." if caps else "."
    return {
        "product": product, "suggested_quantity": rounded.quantize(Q4), "available_quantity": available_now,
        "forecast_consumption": forecast.quantize(Q4), "reorder_date": reorder_date, "supplier_id": supplier_id,
        "quotation_id": quotation_id, "estimated_cost": cost, "justification": " ".join([head] + reasons),
        "confidence": confidence,
    }


def compute_suggestions(unit, coverage_days=None, product_ids=None):
    """Calcula as sugestões de compra sem gravar nada (usada pela lista e pelo assistente)."""
    org = unit.organization
    today = stock.today_for(unit)
    coverage_days = int(coverage_days or org.setting("coverage_days"))
    products = Product.objects.filter(organization=org, status="active").select_related("unit", "main_supplier").prefetch_related("packagings")
    if product_ids:
        products = products.filter(pk__in=product_ids)
    rates = consumption_rates(unit, today=today)
    arrivals = pending_purchases(unit)
    demand = pending_order_demand(unit)
    suggestions = []
    for product in products:
        s = suggest_for_product(product, unit, org, today, rates.get(product.pk), arrivals.get(product.pk, []),
                                demand.get(product.pk, ZERO), coverage_days)
        if s is not None:
            suggestions.append(s)
    suggestions.sort(key=lambda s: (s["reorder_date"] or today + timedelta(days=999), s["product"].name))
    return suggestions, coverage_days, today


@transaction.atomic
def generate_shopping_list(unit, user, coverage_days=None, product_ids=None):
    suggestions, coverage_days, today = compute_suggestions(unit, coverage_days, product_ids)
    sl = ShoppingList.objects.create(organization=unit.organization, unit=unit, created_by=user,
                                     parameters={"coverage_days": coverage_days, "generated_for": str(today)})
    for s in suggestions:
        ShoppingListItem.objects.create(
            shopping_list=sl, product=s["product"], suggested_quantity=s["suggested_quantity"], quantity=s["suggested_quantity"],
            available_quantity=s["available_quantity"], forecast_consumption=s["forecast_consumption"],
            reorder_date=s["reorder_date"], supplier_id=s["supplier_id"], quotation_id=s["quotation_id"],
            estimated_cost=s["estimated_cost"], justification=s["justification"], confidence=s["confidence"],
        )
    return sl


# --------------------------------------------------------------------------- pedidos de compra


def create_purchase_order(org, unit, supplier, items, user, *, notes="", expected_delivery=None, source="manual",
                          freight=None, payment_terms=""):
    if not items:
        raise BusinessError("Inclua ao menos um item no pedido de compra.")
    with transaction.atomic():
        po = PurchaseOrder.objects.create(
            organization=org, unit=unit, number=next_number(PurchaseOrder, org), supplier=supplier, notes=notes,
            expected_delivery=expected_delivery, source=source, created_by=user,
            freight=supplier.delivery_fee if freight is None else freight,
            payment_terms=payment_terms or supplier.payment_terms,
        )
        for it in items:
            product = it["product"]
            unit_ = it.get("purchase_unit") or product.unit
            convert(1, unit_, product.unit, product)  # valida conversão
            if Decimal(it["quantity"]) <= 0:
                raise BusinessError(f"Quantidade inválida para {product.name}.")
            PurchaseOrderItem.objects.create(order=po, product=product, quotation=it.get("quotation"), purchase_unit=unit_,
                                             quantity=it["quantity"], unit_price=it["unit_price"], notes=it.get("notes", ""))
        return po


def _lock(po):
    return PurchaseOrder.objects.select_for_update().get(pk=po.pk)


def submit_purchase_order(po, user, can_approve):
    with transaction.atomic():
        po = _lock(po)
        if po.status != "draft":
            raise BusinessError("Somente rascunhos podem ser enviados para aprovação.")
        threshold = Decimal(str(po.organization.setting("purchase_approval_threshold")))
        po.submitted_at = timezone.now()
        if po.total > threshold and not can_approve:
            po.status = "pending_approval"
        else:
            po.status = "approved"
            po.approved_by = user
            po.approved_at = timezone.now()
        po.save()
        return po


def approve_purchase_order(po, user, approve=True, reason=""):
    with transaction.atomic():
        po = _lock(po)
        if po.status != "pending_approval":
            raise BusinessError("Este pedido não está aguardando aprovação.")
        if po.created_by_id == user.pk and po.total > Decimal(str(po.organization.setting("purchase_approval_threshold"))):
            # Segregação de funções: quem cria não aprova o próprio pedido acima do limite,
            # exceto o proprietário.
            from apps.core.models import Membership

            if not Membership.objects.filter(user=user, organization=po.organization, role="owner").exists():
                raise BusinessError("Pedidos acima do limite devem ser aprovados por outra pessoa.")
        if approve:
            po.status = "approved"
            po.approved_by = user
            po.approved_at = timezone.now()
        else:
            po.status = "draft"
            po.notes = (po.notes + f"\nReprovado: {reason}").strip()
        po.save()
        return po


def send_purchase_order(po, user, expected_delivery=None):
    with transaction.atomic():
        po = _lock(po)
        if po.status != "approved":
            raise BusinessError("Somente pedidos aprovados podem ser enviados ao fornecedor.")
        po.status = "sent"
        po.sent_by = user
        po.sent_at = timezone.now()
        po.expected_delivery = expected_delivery or po.expected_delivery or (
            stock.today_for(po.unit) + timedelta(days=po.supplier.delivery_days))
        po.save()
        return po


def cancel_purchase_order(po, user, reason):
    with transaction.atomic():
        po = _lock(po)
        if po.status in ("received", "partially_received", "cancelled"):
            raise BusinessError("Pedidos já recebidos (total ou parcialmente) ou cancelados não podem ser cancelados.")
        if not reason:
            raise BusinessError("Informe o motivo do cancelamento.", field="reason")
        po.status = "cancelled"
        po.cancelled_by = user
        po.cancelled_at = timezone.now()
        po.cancel_reason = reason
        po.save()
        return po


def _payment_days(terms):
    m = re.search(r"(\d+)", terms or "")
    return int(m.group(1)) if m else 0


def receive_purchase_order(po, user, lines, *, document_number="", notes="", close_remaining=False, idempotency_key=None,
                           received_at=None):
    """Recebe itens de um pedido. `lines`: [{order_item, quantity, unit_price?, rejected_quantity?, lot_code?,
    expires_at?, manufactured_at?, location?, notes?}] com quantidades na unidade de compra."""
    from apps.finance.models import ExpenseCategory, FinancialEntry

    received_at = received_at or timezone.now()
    with transaction.atomic():
        po = _lock(po)
        if idempotency_key:
            existing = Receipt.objects.filter(organization=po.organization, idempotency_key=idempotency_key).first()
            if existing:
                return existing, False
        if po.status not in ("approved", "sent", "partially_received"):
            raise BusinessError("O pedido precisa estar aprovado ou enviado para ser recebido.")
        lines = [l for l in lines if Decimal(l.get("quantity") or 0) > 0 or Decimal(l.get("rejected_quantity") or 0) > 0]
        if not lines and not close_remaining:
            raise BusinessError("Informe a quantidade recebida de ao menos um item.")
        unit = po.unit
        org = po.organization
        receipt = Receipt.objects.create(organization=org, unit=unit, order=po, document_number=document_number, notes=notes,
                                         received_by=user, received_at=received_at, idempotency_key=idempotency_key)
        op = stock.begin_operation(org, unit, f"receipt:{receipt.pk}", "receipt", user, f"Recebimento do pedido #{po.number}")
        receipt.operation = op
        total = ZERO
        today = stock.today_for(unit)
        for line in lines:
            item = PurchaseOrderItem.objects.select_for_update().select_related("product__unit", "purchase_unit").get(
                pk=line["order_item"].pk, order=po)
            product = item.product
            qty = Decimal(line.get("quantity") or 0)
            rejected = Decimal(line.get("rejected_quantity") or 0)
            price = Decimal(line.get("unit_price") if line.get("unit_price") not in (None, "") else item.unit_price)
            if qty < 0 or rejected < 0 or price < 0:
                raise BusinessError("Quantidades e preços não podem ser negativos.")
            expires_at = line.get("expires_at")
            if product.is_perishable and qty > 0 and not expires_at:
                raise BusinessError(f"Informe a validade do lote de {product.name} (produto perecível).", field="expires_at")
            per_unit = convert(1, item.purchase_unit, product.unit, product)
            stock_qty = qty * per_unit
            lot = None
            if qty > 0:
                cost_per_stock_unit = (price / per_unit).quantize(Q4)
                lot, _ = stock.add_stock(
                    op, unit, product, stock_qty, cost_per_stock_unit, type_="receipt", user=user, occurred_at=received_at,
                    reason=f"Pedido de compra #{po.number}", ref_type="purchase_order", ref_id=po.pk,
                    lot_data={"code": line.get("lot_code", ""), "expires_at": expires_at,
                              "manufactured_at": line.get("manufactured_at"), "supplier": po.supplier,
                              "document": document_number, "location": line.get("location") or product.default_location},
                )
                stock.update_product_cost(product, cost_per_stock_unit, source="receipt", reference=f"PC #{po.number}",
                                          user=user, at=received_at)
                if not product.main_supplier_id:
                    Product.objects.filter(pk=product.pk).update(main_supplier=po.supplier)
            ReceiptItem.objects.create(
                receipt=receipt, order_item=item, quantity=qty, stock_quantity=stock_qty, unit_price=price,
                lot_code=line.get("lot_code", ""), manufactured_at=line.get("manufactured_at"), expires_at=expires_at,
                location=line.get("location"), lot=lot, rejected_quantity=rejected, notes=line.get("notes", ""),
            )
            item.quantity_received += qty
            item.save(update_fields=["quantity_received"])
            total += (qty * price).quantize(C2)
            # Divergências
            if price != item.unit_price:
                PurchaseIssue.objects.create(
                    organization=org, order=po, receipt=receipt, product=product, kind="price", created_by=user,
                    description=f"Preço cobrado diferente do pedido para {product.name}.",
                    expected=f"R$ {item.unit_price.quantize(C2)}", actual=f"R$ {price.quantize(C2)}")
            if rejected > 0:
                PurchaseIssue.objects.create(
                    organization=org, order=po, receipt=receipt, product=product, kind="quality", created_by=user,
                    description=f"{rejected.normalize()} {item.purchase_unit.code} de {product.name} recusados no recebimento. {line.get('notes', '')}".strip(),
                    expected="0", actual=str(rejected.normalize()))
            if item.quantity_received > item.quantity:
                PurchaseIssue.objects.create(
                    organization=org, order=po, receipt=receipt, product=product, kind="quantity", created_by=user,
                    description=f"Recebido acima do pedido para {product.name}.",
                    expected=str(item.quantity.normalize()), actual=str(item.quantity_received.normalize()))
            if expires_at and product.is_perishable and expires_at <= today + timedelta(days=2):
                PurchaseIssue.objects.create(
                    organization=org, order=po, receipt=receipt, product=product, kind="expiry", created_by=user,
                    description=f"Lote de {product.name} recebido com validade curta ({expires_at.strftime('%d/%m/%Y')}).")
        if po.expected_delivery and timezone.localdate(received_at) > po.expected_delivery and not po.issues.filter(kind="late").exists():
            PurchaseIssue.objects.create(
                organization=org, order=po, receipt=receipt, kind="late", created_by=user,
                description="Entrega realizada após a data prevista.",
                expected=po.expected_delivery.strftime("%d/%m/%Y"), actual=timezone.localdate(received_at).strftime("%d/%m/%Y"))
        all_items = list(po.items.all())
        complete = all(i.quantity_received >= i.quantity for i in all_items)
        if not complete and close_remaining:
            for i in all_items:
                if i.quantity_received < i.quantity:
                    PurchaseIssue.objects.create(
                        organization=org, order=po, receipt=receipt, product=i.product, kind="quantity", created_by=user,
                        description=f"Pedido encerrado com falta de {i.pending_quantity.normalize()} {i.purchase_unit.code} de {i.product.name}.",
                        expected=str(i.quantity.normalize()), actual=str(i.quantity_received.normalize()))
            complete = True
        po.status = "received" if complete else "partially_received"
        po.save(update_fields=["status"])
        receipt.total = total
        receipt.save(update_fields=["total", "operation"])
        if total > 0:
            first_receipt = not po.receipts.exclude(pk=receipt.pk).exists()
            amount = total + (po.freight - po.discount if first_receipt else ZERO)
            category, _ = ExpenseCategory.objects.get_or_create(organization=org, name="Compra de mercadorias",
                                                                defaults={"kind": "merchandise"})
            FinancialEntry.objects.create(
                organization=org, unit=unit, kind="payable", category=category, receipt=receipt,
                description=f"Pedido de compra #{po.number} — {po.supplier}", amount=amount,
                competence_date=timezone.localdate(received_at),
                due_date=timezone.localdate(received_at) + timedelta(days=_payment_days(po.payment_terms)),
                supplier=po.supplier, purchase_order=po, document=document_number, created_by=user,
            )
        return receipt, True
