"""Consultas analíticas do estoque reutilizadas por alertas, compras, relatórios e assistente."""

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from .models import Lot, Product, StockBalance, StockMovement
from .services import today_for

CONSUMPTION_TYPES = ("sale", "production")
ZERO = Decimal("0")


def local_day_bounds(unit, day):
    tz = ZoneInfo(unit.timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


def period_bounds(unit, start_day, end_day):
    """[start_day 00:00, end_day+1 00:00) no fuso da unidade."""
    tz = ZoneInfo(unit.timezone)
    return datetime.combine(start_day, time.min, tzinfo=tz), datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)


def operating_days_between(org, start_day, end_day):
    weekdays = set(org.setting("operating_weekdays") or range(7))
    days = 0
    d = start_day
    while d <= end_day:
        if d.weekday() in weekdays:
            days += 1
        d += timedelta(days=1)
    return max(days, 1)


def net_consumption_by_product(unit, start, end, product_ids=None):
    """Consumo líquido (vendas/produção menos estornos dessas saídas) em unidade de estoque."""
    base = StockMovement.objects.filter(unit=unit, occurred_at__gte=start, occurred_at__lt=end)
    if product_ids is not None:
        base = base.filter(product_id__in=product_ids)
    out = base.filter(type__in=CONSUMPTION_TYPES).values("product_id").annotate(q=Sum("quantity"))
    rev = base.filter(type="reversal", reversal_of__type__in=CONSUMPTION_TYPES).values("product_id").annotate(q=Sum("quantity"))
    result = defaultdict(lambda: ZERO)
    for row in out:
        result[row["product_id"]] += -row["q"]
    for row in rev:
        result[row["product_id"]] -= row["q"]
    return result


def consumption_rates(unit, days=28, product_ids=None, today=None):
    """Consumo médio por dia de funcionamento nas últimas `days` jornadas.

    Retorna {product_id: {"rate": Decimal, "history_days": int, "weekday_factors": {...}}}.
    Fatores por dia da semana (sazonalidade semanal) só são usados com 4+ semanas de histórico.
    """
    today = today or today_for(unit)
    start_day = today - timedelta(days=days)
    end_day = today - timedelta(days=1)
    start, end = period_bounds(unit, start_day, end_day)
    org = unit.organization
    op_days = operating_days_between(org, start_day, end_day)

    first_mv = StockMovement.objects.filter(unit=unit, type__in=CONSUMPTION_TYPES).order_by("occurred_at").values_list("occurred_at", flat=True).first()
    history_days = 0
    if first_mv:
        history_days = (today - first_mv.astimezone(ZoneInfo(unit.timezone)).date()).days

    totals = net_consumption_by_product(unit, start, end, product_ids)
    by_weekday = defaultdict(lambda: defaultdict(lambda: ZERO))
    if history_days >= 28:
        qs = StockMovement.objects.filter(unit=unit, occurred_at__gte=start, occurred_at__lt=end, type__in=CONSUMPTION_TYPES)
        if product_ids is not None:
            qs = qs.filter(product_id__in=product_ids)
        tz = ZoneInfo(unit.timezone)
        for pid, qty, at in qs.values_list("product_id", "quantity", "occurred_at"):
            by_weekday[pid][at.astimezone(tz).weekday()] += -qty

    weekdays = set(org.setting("operating_weekdays") or range(7))
    rates = {}
    for pid, total in totals.items():
        rate = (total / op_days) if total > 0 else ZERO
        factors = {}
        if pid in by_weekday and rate > 0:
            weeks = Decimal(days) / 7
            for wd in range(7):
                if wd not in weekdays:
                    factors[wd] = ZERO
                    continue
                avg_wd = by_weekday[pid].get(wd, ZERO) / weeks
                factors[wd] = (avg_wd / rate) if rate else Decimal("1")
        rates[pid] = {"rate": rate, "history_days": min(history_days, days), "weekday_factors": factors}
    return rates


def forecast_for_day(rate_info, day, org):
    if not rate_info:
        return ZERO
    weekdays = set(org.setting("operating_weekdays") or range(7))
    if day.weekday() not in weekdays:
        return ZERO
    factor = rate_info["weekday_factors"].get(day.weekday()) if rate_info["weekday_factors"] else None
    return rate_info["rate"] * (factor if factor is not None else Decimal("1"))


def annotate_stock(qs, unit, today=None):
    """Anota quantidade física, vencida e próxima validade da unidade em um queryset de produtos."""
    today = today or today_for(unit)
    dec = DecimalField(max_digits=16, decimal_places=4)
    bal = StockBalance.objects.filter(unit=unit, product=OuterRef("pk")).values("quantity")[:1]
    expired = (
        Lot.objects.filter(unit=unit, product=OuterRef("pk"), status="active", expires_at__lt=today)
        .values("product").annotate(s=Sum("quantity_remaining")).values("s")[:1]
    )
    next_exp = (
        Lot.objects.filter(unit=unit, product=OuterRef("pk"), status="active", quantity_remaining__gt=0, expires_at__gte=today)
        .order_by("expires_at").values("expires_at")[:1]
    )
    return qs.annotate(
        quantity=Coalesce(Subquery(bal, output_field=dec), Value(ZERO), output_field=dec),
        expired_quantity=Coalesce(Subquery(expired, output_field=dec), Value(ZERO), output_field=dec),
        next_expiry=Subquery(next_exp),
    )


def stock_value(unit):
    """Valor estimado do estoque: lotes ao custo do lote + parcela sem lote ao custo de reposição."""
    lots_value = Lot.objects.filter(unit=unit, status="active").aggregate(
        v=Sum(F("quantity_remaining") * F("unit_cost"), output_field=DecimalField(max_digits=18, decimal_places=4))
    )["v"] or ZERO
    unlotted = ZERO
    lot_qty = dict(
        Lot.objects.filter(unit=unit, status="active").values("product_id").annotate(s=Sum("quantity_remaining")).values_list("product_id", "s")
    )
    for b in StockBalance.objects.filter(unit=unit).select_related("product"):
        rest = b.quantity - lot_qty.get(b.product_id, ZERO)
        if rest > 0:
            unlotted += rest * b.product.cost_price
    return (lots_value + unlotted).quantize(Decimal("0.01"))


def active_products(org):
    return Product.objects.filter(organization=org, status="active")
