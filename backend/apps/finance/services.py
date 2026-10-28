"""Indicadores financeiros com limitações explícitas.

Definições (docs/REGRAS_DE_NEGOCIO.md):
- Faturamento bruto: soma de quantidade × preço dos itens das vendas concluídas.
- Receita líquida: bruto − descontos − taxas de plataforma + taxas de entrega cobradas.
- CMV: custo real dos lotes consumidos pelas vendas (FEFO).
- Margem de contribuição: receita líquida − CMV.
- Resultado operacional estimado: margem de contribuição − despesas registradas no período
  (exceto compras de mercadorias, que entram via CMV). NÃO é lucro líquido.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from apps.inventory.analytics import period_bounds
from apps.inventory.models import WasteRecord
from apps.sales.models import Sale

from .models import FinancialEntry

ZERO = Decimal("0")


def sales_totals(units, start_dt, end_dt):
    qs = Sale.objects.filter(unit__in=units, occurred_at__gte=start_dt, occurred_at__lt=end_dt)
    done = qs.filter(status="completed")
    a = done.aggregate(gross=Sum("gross_amount"), discount=Sum("discount_amount"), fees=Sum("fee_amount"),
                       delivery=Sum("delivery_fee"), net=Sum("net_amount"), cogs=Sum("cogs"), n=Count("id"))
    c = qs.filter(status="cancelled").aggregate(v=Sum("gross_amount"), n=Count("id"))
    return {
        "sales_count": a["n"] or 0, "gross": a["gross"] or ZERO, "discounts": a["discount"] or ZERO,
        "fees": a["fees"] or ZERO, "delivery_fees": a["delivery"] or ZERO, "net": a["net"] or ZERO,
        "cogs": a["cogs"] or ZERO, "cancelled_value": c["v"] or ZERO, "cancelled_count": c["n"] or 0,
    }


def financial_summary(org, units, start, end):
    unit0 = units[0]
    s, e = period_bounds(unit0, start, end)
    st = sales_totals(units, s, e)
    entries = FinancialEntry.objects.filter(organization=org, unit__in=units, kind="payable",
                                            competence_date__gte=start, competence_date__lte=end).exclude(status="cancelled")
    by_kind = defaultdict(lambda: ZERO)
    by_category = []
    for row in entries.values("category__kind", "category__name").annotate(v=Sum("amount")).order_by("-v"):
        by_kind[row["category__kind"]] += row["v"]
        by_category.append({"category": row["category__name"], "kind": row["category__kind"], "value": row["v"]})
    other_income = FinancialEntry.objects.filter(organization=org, unit__in=units, kind="receivable",
                                                 competence_date__gte=start, competence_date__lte=end).exclude(
        status="cancelled").aggregate(v=Sum("amount"))["v"] or ZERO
    expenses_ex_merch = sum((v for k, v in by_kind.items() if k != "merchandise"), ZERO)
    waste = WasteRecord.objects.filter(unit__in=units, occurred_at__gte=s, occurred_at__lt=e).aggregate(v=Sum("total_cost"))["v"] or ZERO
    contribution = st["net"] - st["cogs"]
    limitations = []
    if not st["sales_count"]:
        limitations.append("Nenhuma venda registrada no período.")
    for kind, label in (("payroll", "folha de pagamento e encargos"), ("tax", "impostos"), ("fixed", "despesas fixas (aluguel, energia...)")):
        if not by_kind.get(kind):
            limitations.append(f"Não há {label} registrados no período: o resultado está superestimado.")
    sales_wo_cost = Sale.objects.filter(unit__in=units, occurred_at__gte=s, occurred_at__lt=e, status="completed",
                                        stock_status__in=("partial", "not_applicable")).count()
    if sales_wo_cost:
        limitations.append(f"{sales_wo_cost} venda(s) sem baixa completa de ingredientes: o CMV pode estar subestimado.")
    return {
        "start": start, "end": end, **st,
        "average_ticket": (st["net"] / st["sales_count"]).quantize(Decimal("0.01")) if st["sales_count"] else ZERO,
        "contribution_margin": contribution,
        "contribution_margin_percent": (contribution / st["net"] * 100).quantize(Decimal("0.1")) if st["net"] else None,
        "cogs_percent": (st["cogs"] / st["net"] * 100).quantize(Decimal("0.1")) if st["net"] else None,
        "expenses_by_kind": dict(by_kind), "expenses_by_category": by_category,
        "registered_expenses": expenses_ex_merch, "merchandise_purchases": by_kind.get("merchandise", ZERO),
        "other_income": other_income, "waste_value": waste,
        "operating_result_estimate": contribution + other_income - expenses_ex_merch,
        "limitations": limitations,
        "disclaimer": "Faturamento não é lucro. O resultado operacional estimado considera apenas o que foi registrado "
                      "no sistema e não substitui a apuração contábil.",
    }


def cash_flow(org, units, start, end):
    unit0 = units[0]
    s, e = period_bounds(unit0, start, end)
    days = defaultdict(lambda: {"inflow": ZERO, "outflow": ZERO})
    for row in (Sale.objects.filter(unit__in=units, status="completed", occurred_at__gte=s, occurred_at__lt=e)
                .annotate(d=TruncDate("occurred_at")).values("d").annotate(v=Sum("net_amount"))):
        days[row["d"]]["inflow"] += row["v"]
    paid = FinancialEntry.objects.filter(organization=org, unit__in=units, status="paid", paid_at__gte=start, paid_at__lte=end)
    for row in paid.values("paid_at", "kind").annotate(v=Sum("paid_amount")):
        key = "inflow" if row["kind"] == "receivable" else "outflow"
        days[row["paid_at"]][key] += row["v"] or ZERO
    series = []
    balance = ZERO
    d = start
    while d <= end:
        day = days.get(d, {"inflow": ZERO, "outflow": ZERO})
        balance += day["inflow"] - day["outflow"]
        series.append({"date": d, **day, "net": day["inflow"] - day["outflow"], "cumulative": balance})
        d += timedelta(days=1)
    upcoming = FinancialEntry.objects.filter(organization=org, unit__in=units, status="open", due_date__gte=end,
                                             due_date__lte=end + timedelta(days=30))
    return {
        "series": series,
        "upcoming_payables": upcoming.filter(kind="payable").aggregate(v=Sum("amount"))["v"] or ZERO,
        "upcoming_receivables": upcoming.filter(kind="receivable").aggregate(v=Sum("amount"))["v"] or ZERO,
        "overdue_payables": FinancialEntry.objects.filter(organization=org, unit__in=units, status="open", kind="payable",
                                                          due_date__lt=end).aggregate(v=Sum("amount"))["v"] or ZERO,
        "note": "Entradas de vendas consideradas na data da venda (sem prazo de recebimento de cartões).",
    }


def expected_cash(session):
    """Valor esperado em dinheiro na gaveta: abertura + vendas em dinheiro + suprimentos − sangrias."""
    end = session.closed_at
    sales = Sale.objects.filter(unit=session.unit, status="completed", payment_method="cash", occurred_at__gte=session.opened_at)
    if end:
        sales = sales.filter(occurred_at__lt=end)
    cash_sales = sum(((s.gross_amount - s.discount_amount + s.delivery_fee) for s in sales), ZERO)
    supplies = session.movements.filter(kind="supply").aggregate(v=Sum("amount"))["v"] or ZERO
    withdrawals = session.movements.filter(kind="withdrawal").aggregate(v=Sum("amount"))["v"] or ZERO
    return {"opening": session.opening_amount, "cash_sales": cash_sales, "supplies": supplies, "withdrawals": withdrawals,
            "expected": session.opening_amount + cash_sales + supplies - withdrawals}

