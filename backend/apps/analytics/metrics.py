"""Consultas de métricas compartilhadas por dashboard, relatórios e assistente."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

from apps.inventory.analytics import net_consumption_by_product, period_bounds
from apps.inventory.models import ProductCostHistory, StockMovement, WasteRecord
from apps.menu.services import requirements_per_portion
from apps.purchasing.models import PurchaseIssue, PurchaseOrder, Receipt
from apps.sales.models import Order, Sale, SaleItem

ZERO = Decimal("0")
C2 = Decimal("0.01")


def pct_change(current, previous):
    if not previous:
        return None
    return ((Decimal(current) - Decimal(previous)) / Decimal(previous) * 100).quantize(Decimal("0.1"))


def sales_series(units, start, end, grain="day"):
    s, e = period_bounds(units[0], start, end)
    trunc = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}[grain]
    rows = (Sale.objects.filter(unit__in=units, status="completed", occurred_at__gte=s, occurred_at__lt=e)
            .annotate(p=trunc("occurred_at")).values("p")
            .annotate(net=Sum("net_amount"), gross=Sum("gross_amount"), cogs=Sum("cogs"), n=Count("id")).order_by("p"))
    data = {}
    for r in rows:
        key = r["p"].date() if hasattr(r["p"], "date") and grain != "day" else r["p"]
        data[key] = r
    out = []
    if grain == "day":
        d = start
        while d <= end:
            r = data.get(d, {})
            out.append({"period": d, "net": r.get("net") or ZERO, "gross": r.get("gross") or ZERO,
                        "cogs": r.get("cogs") or ZERO, "count": r.get("n") or 0})
            d += timedelta(days=1)
    else:
        for k in sorted(data):
            r = data[k]
            out.append({"period": k, "net": r["net"] or ZERO, "gross": r["gross"] or ZERO, "cogs": r["cogs"] or ZERO,
                        "count": r["n"]})
    return out


def item_sales(units, start, end):
    """Vendas por item do cardápio com custo teórico e real e margem."""
    s, e = period_bounds(units[0], start, end)
    rows = (SaleItem.objects.filter(sale__unit__in=units, sale__status="completed", sale__occurred_at__gte=s,
                                    sale__occurred_at__lt=e)
            .values("menu_item_id", "description", "menu_item__category__name")
            .annotate(qty=Sum("quantity"), revenue=Sum("total"),
                      theoretical=Sum(F("theoretical_cost") * F("quantity")))
            .order_by("-qty"))
    result = []
    for r in rows:
        revenue = r["revenue"] or ZERO
        theo = (r["theoretical"] or ZERO).quantize(C2)
        margin = revenue - theo
        result.append({
            "menu_item_id": r["menu_item_id"], "item": r["description"], "category": r["menu_item__category__name"],
            "quantity": r["qty"], "revenue": revenue, "theoretical_cost": theo, "contribution_margin": margin,
            "margin_percent": (margin / revenue * 100).quantize(Decimal("0.1")) if revenue else None,
        })
    return result


def waste_totals(units, start, end):
    s, e = period_bounds(units[0], start, end)
    return WasteRecord.objects.filter(unit__in=units, occurred_at__gte=s, occurred_at__lt=e).aggregate(
        v=Sum("total_cost"))["v"] or ZERO


def stock_value_series(unit, days=30, today=None):
    """Evolução estimada do valor do estoque, reconstruída a partir das movimentações."""
    from apps.inventory.analytics import stock_value
    from apps.inventory.services import today_for

    today = today or today_for(unit)
    current = stock_value(unit)
    start = today - timedelta(days=days - 1)
    s, e = period_bounds(unit, start, today)
    deltas = defaultdict(lambda: ZERO)
    for r in (StockMovement.objects.filter(unit=unit, occurred_at__gte=s, occurred_at__lt=e)
              .annotate(d=TruncDate("occurred_at")).values("d", "quantity", "total_cost")):
        deltas[r["d"]] += r["total_cost"] if r["quantity"] > 0 else -r["total_cost"]
    series = []
    value = current
    d = today
    while d >= start:
        series.append({"date": d, "value": value.quantize(C2)})
        value -= deltas.get(d, ZERO)
        d -= timedelta(days=1)
    return list(reversed(series))


def supplier_performance(org, units, start, end):
    s, e = period_bounds(units[0], start, end)
    orders = PurchaseOrder.objects.filter(organization=org, unit__in=units, created_at__gte=s, created_at__lt=e).exclude(
        status="cancelled").select_related("supplier").prefetch_related("receipts", "items")
    per = defaultdict(lambda: {"orders": 0, "received_value": ZERO, "evaluated": 0, "on_time": 0, "issues": 0,
                               "ordered_qty": ZERO, "received_qty": ZERO})
    for o in orders:
        p = per[str(o.supplier)]
        p["supplier_id"] = o.supplier_id
        p["orders"] += 1
        p["received_value"] += sum((r.total for r in o.receipts.all()), ZERO)
        for it in o.items.all():
            p["ordered_qty"] += it.quantity
            p["received_qty"] += min(it.quantity_received, it.quantity)
        first = min((r.received_at for r in o.receipts.all()), default=None)
        if first and o.expected_delivery:
            p["evaluated"] += 1
            if first.date() <= o.expected_delivery:
                p["on_time"] += 1
    issues = PurchaseIssue.objects.filter(organization=org, order__in=orders).values("order__supplier__name", "order__supplier__trade_name").annotate(n=Count("id"))
    issue_map = {(r["order__supplier__trade_name"] or r["order__supplier__name"]): r["n"] for r in issues}
    out = []
    for name, p in per.items():
        out.append({
            "supplier": name, "supplier_id": p["supplier_id"], "orders": p["orders"], "received_value": p["received_value"],
            "on_time_rate": round(p["on_time"] / p["evaluated"] * 100, 1) if p["evaluated"] else None,
            "fill_rate": round(float(p["received_qty"] / p["ordered_qty"] * 100), 1) if p["ordered_qty"] else None,
            "issues": issue_map.get(name, 0),
        })
    return sorted(out, key=lambda r: -r["received_value"])


def purchases_series(org, units, start, end):
    s, e = period_bounds(units[0], start, end)
    rows = (Receipt.objects.filter(organization=org, unit__in=units, received_at__gte=s, received_at__lt=e)
            .annotate(p=TruncWeek("received_at")).values("p").annotate(v=Sum("total")).order_by("p"))
    return [{"period": r["p"].date() if hasattr(r["p"], "date") else r["p"], "value": r["v"]} for r in rows]


def cost_evolution(org, product_ids, since):
    series = defaultdict(list)
    for h in ProductCostHistory.objects.filter(product_id__in=product_ids, created_at__date__gte=since).select_related("product").order_by("created_at"):
        series[h.product.name].append({"date": h.created_at.date(), "cost": h.cost})
    return series


def theoretical_vs_actual(unit, start, end):
    """Consumo teórico (fichas técnicas × vendas) vs consumo real (movimentações + perdas + ajustes)."""
    s, e = period_bounds(unit, start, end)
    theoretical = defaultdict(lambda: ZERO)
    for si in SaleItem.objects.filter(sale__unit=unit, sale__status="completed", sale__occurred_at__gte=s,
                                      sale__occurred_at__lt=e, menu_item__isnull=False).select_related("menu_item"):
        req = requirements_per_portion(si.menu_item) or []
        for product, qty in req:
            theoretical[product.pk] += qty * si.quantity
    actual_sales = net_consumption_by_product(unit, s, e)
    waste = defaultdict(lambda: ZERO)
    for r in WasteRecord.objects.filter(unit=unit, occurred_at__gte=s, occurred_at__lt=e).values("product_id").annotate(q=Sum("quantity")):
        waste[r["product_id"]] += r["q"]
    adjustments = defaultdict(lambda: ZERO)
    for r in StockMovement.objects.filter(unit=unit, type="adjustment", occurred_at__gte=s, occurred_at__lt=e).values("product_id").annotate(q=Sum("quantity")):
        adjustments[r["product_id"]] += -r["q"]  # ajuste negativo = consumo não registrado
    return theoretical, actual_sales, waste, adjustments


def prep_times(units, start, end):
    s, e = period_bounds(units[0], start, end)
    rows = []
    for o in Order.objects.filter(unit__in=units, created_at__gte=s, created_at__lt=e, ready_at__isnull=False):
        start_t = o.preparing_at or o.confirmed_at or o.created_at
        rows.append({"origin": o.get_origin_display(), "wait": (start_t - o.created_at).total_seconds() / 60,
                     "prep": (o.ready_at - start_t).total_seconds() / 60, "total": (o.ready_at - o.created_at).total_seconds() / 60})
    return rows

