"""Dashboard: centro de comando com dados reais do banco."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.alerts.engine import refresh_alerts
from apps.alerts.models import PRIORITY_ORDER, Alert
from apps.finance.services import sales_totals
from apps.inventory.analytics import annotate_stock, period_bounds, stock_value
from apps.inventory.models import Lot, Product, StockMovement
from apps.inventory.services import today_for
from apps.purchasing.models import PurchaseOrder
from apps.sales.models import Order

from . import metrics

ZERO = Decimal("0")


def kpi(key, label, value, *, fmt="money", previous=None, help_text="", link="", compare_label=""):
    return {"key": key, "label": label, "value": value, "format": fmt, "previous": previous,
            "change_percent": metrics.pct_change(value, previous) if previous is not None else None,
            "compare_label": compare_label, "help": help_text, "link": link}


def build_dashboard(request, units):
    org = request.org
    unit = units[0]
    today = today_for(unit)
    now = timezone.now()
    same_day_last_week = today - timedelta(days=7)

    def totals(day_start, day_end):
        s, e = period_bounds(unit, day_start, day_end)
        return sales_totals(units, s, e)

    t_today = totals(today, today)
    t_lastweek = totals(same_day_last_week, same_day_last_week)
    month_start = today.replace(day=1)
    t_month = totals(month_start, today)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    # Mesmo número de dias do mês anterior, para comparação justa.
    prev_cmp_end = min(prev_month_start + (today - month_start), prev_month_end)
    t_prev_month = totals(prev_month_start, prev_cmp_end)

    s_today, e_today = period_bounds(unit, today, today)
    orders_today = Order.objects.filter(unit__in=units, created_at__gte=s_today, created_at__lt=e_today).exclude(status="cancelled")
    s_lw, e_lw = period_bounds(unit, same_day_last_week, same_day_last_week)
    orders_lastweek = Order.objects.filter(unit__in=units, created_at__gte=s_lw, created_at__lt=e_lw).exclude(status="cancelled").count()
    open_orders = Order.objects.filter(unit__in=units, status__in=Order.OPEN_STATUSES).count()

    value_now = sum((stock_value(u) for u in units), ZERO)
    low_stock = 0
    for u in units:
        for p in annotate_stock(Product.objects.filter(organization=org, status="active", min_stock__gt=0), u):
            if p.quantity - p.expired_quantity < p.min_stock:
                low_stock += 1
    exp_lots = Lot.objects.filter(unit__in=units, status="active", quantity_remaining__gt=0, expires_at__isnull=False,
                                  expires_at__gte=today, expires_at__lte=today + timedelta(days=7))
    exp_value = sum((l.quantity_remaining * l.unit_cost for l in exp_lots), ZERO).quantize(Decimal("0.01"))
    expired_lots = Lot.objects.filter(unit__in=units, status="active", quantity_remaining__gt=0, expires_at__lt=today).count()
    waste_month = metrics.waste_totals(units, month_start, today)
    waste_prev = metrics.waste_totals(units, prev_month_start, prev_cmp_end)
    open_pos = PurchaseOrder.objects.filter(unit__in=units, status__in=("approved", "sent", "partially_received"))
    late = open_pos.filter(expected_delivery__lt=today).count()
    open_po_value = sum((po.total for po in open_pos.prefetch_related("items")), ZERO)

    avg_ticket = (t_today["net"] / t_today["sales_count"]).quantize(Decimal("0.01")) if t_today["sales_count"] else ZERO
    avg_ticket_lw = (t_lastweek["net"] / t_lastweek["sales_count"]).quantize(Decimal("0.01")) if t_lastweek["sales_count"] else None
    margin_month = t_month["net"] - t_month["cogs"]
    margin_prev = t_prev_month["net"] - t_prev_month["cogs"]
    cmp_lw = f"vs. {same_day_last_week.strftime('%d/%m')} (mesmo dia da semana passada)"
    cmp_month = f"vs. mesmo período do mês anterior ({prev_month_start.strftime('%d/%m')}–{prev_cmp_end.strftime('%d/%m')})"

    kpis = [
        kpi("revenue_today", "Faturamento de hoje", t_today["net"], previous=t_lastweek["net"], compare_label=cmp_lw,
            help_text="Receita líquida das vendas concluídas hoje: valor dos itens − descontos − taxas de plataforma + taxas de entrega.",
            link="/vendas"),
        kpi("orders_today", "Pedidos hoje", orders_today.count(), fmt="int", previous=orders_lastweek, compare_label=cmp_lw,
            help_text=f"Pedidos registrados hoje (exceto cancelados). Em andamento agora: {open_orders}.", link="/pedidos"),
        kpi("avg_ticket", "Ticket médio", avg_ticket, previous=avg_ticket_lw, compare_label=cmp_lw,
            help_text="Receita líquida de hoje dividida pelo número de vendas concluídas.", link="/relatorios?r=sales_by_period"),
        kpi("open_orders", "Pedidos em andamento", open_orders, fmt="int",
            help_text="Pedidos recebidos, confirmados, em preparo, prontos ou saindo para entrega.", link="/cozinha"),
        kpi("revenue_month", "Vendas do mês", t_month["net"], previous=t_prev_month["net"], compare_label=cmp_month,
            help_text="Receita líquida acumulada no mês corrente.", link="/financeiro"),
        kpi("cogs_month", "CMV estimado do mês", t_month["cogs"], previous=t_prev_month["cogs"], compare_label=cmp_month,
            help_text="Custo das mercadorias vendidas: custo real dos lotes consumidos pelas vendas (FEFO). Vendas sem ficha técnica não entram.",
            link="/relatorios?r=cogs"),
        kpi("margin_month", "Margem de contribuição", margin_month, previous=margin_prev, compare_label=cmp_month,
            help_text="Receita líquida − CMV do mês. Não é lucro: não desconta despesas fixas, folha e impostos.",
            link="/financeiro"),
        kpi("stock_value", "Valor em estoque", value_now,
            help_text="Saldo atual valorizado pelo custo de cada lote (e custo de reposição para saldos sem lote).",
            link="/estoque/produtos"),
        kpi("low_stock", "Abaixo do mínimo", low_stock, fmt="int",
            help_text="Produtos cujo saldo disponível (sem lotes vencidos) está abaixo do estoque mínimo.",
            link="/estoque/produtos?stock=low"),
        kpi("expiring", "Lotes vencendo em 7 dias", exp_lots.count(), fmt="int",
            help_text=f"Valor estimado desses lotes: R$ {exp_value}. Lotes já vencidos aguardando descarte: {expired_lots}.",
            link="/estoque/validades"),
        kpi("expiring_value", "Valor próximo do vencimento", exp_value,
            help_text="Custo dos lotes que vencem nos próximos 7 dias.", link="/estoque/validades"),
        kpi("waste_month", "Desperdício no mês", waste_month, previous=waste_prev, compare_label=cmp_month,
            help_text="Custo das perdas e descartes registrados no mês.", link="/estoque/perdas"),
        kpi("pending_purchases", "Compras a receber", open_po_value,
            help_text=f"{open_pos.count()} pedido(s) aprovado(s) ou enviado(s) ainda não recebidos integralmente.",
            link="/compras/pedidos"),
        kpi("late_deliveries", "Entregas atrasadas", late, fmt="int",
            help_text="Pedidos de compra com data prevista de entrega já ultrapassada.", link="/compras/pedidos?late=1"),
    ]

    daily = metrics.sales_series(units, today - timedelta(days=29), today, "day")
    weekly = metrics.sales_series(units, today - timedelta(weeks=12), today, "week")
    monthly = metrics.sales_series(units, (today.replace(day=1) - timedelta(days=330)).replace(day=1), today, "month")
    items = metrics.item_sales(units, today - timedelta(days=29), today)
    top_sold = items[:8]
    top_margin = sorted([i for i in items if i["theoretical_cost"]], key=lambda i: -i["contribution_margin"])[:8]
    purchases = metrics.purchases_series(org, units, today - timedelta(weeks=12), today)
    s30, e30 = period_bounds(unit, today - timedelta(days=29), today)
    top_ingredients = list(StockMovement.objects.filter(unit__in=units, type="sale", occurred_at__gte=s30, occurred_at__lt=e30)
                           .values("product_id").annotate(v=Sum("total_cost")).order_by("-v").values_list("product_id", flat=True)[:5])
    cost_ev = metrics.cost_evolution(org, top_ingredients, today - timedelta(days=90))
    from django.db.models.functions import TruncWeek

    from apps.inventory.models import WasteRecord

    waste_weekly = [{"period": r["p"].date() if hasattr(r["p"], "date") else r["p"], "value": r["v"]} for r in
                    WasteRecord.objects.filter(unit__in=units, occurred_at__gte=now - timedelta(weeks=12))
                    .annotate(p=TruncWeek("occurred_at")).values("p").annotate(v=Sum("total_cost")).order_by("p")]
    waste_by_category = list(WasteRecord.objects.filter(unit__in=units, occurred_at__gte=period_bounds(unit, month_start, today)[0])
                             .values("product__category__name").annotate(value=Sum("total_cost")).order_by("-value"))
    stock_series = metrics.stock_value_series(unit, 30, today) if len(units) == 1 else []
    suppliers = metrics.supplier_performance(org, units, today - timedelta(days=90), today)[:6]

    for u in units:
        refresh_alerts(u)
    alerts = sorted(Alert.objects.filter(unit__in=units, status="open"),
                    key=lambda a: (PRIORITY_ORDER[a.priority], -a.first_seen_at.timestamp()))
    from apps.alerts.views import AlertSerializer

    return {
        "generated_at": now, "today": today, "scope": "all" if len(units) > 1 else "unit",
        "units": [u.name for u in units],
        "kpis": kpis,
        "charts": {
            "sales_daily": daily, "sales_weekly": weekly, "sales_monthly": monthly,
            "purchases_weekly": purchases, "cost_evolution": cost_ev,
            "top_sold": top_sold, "top_margin": top_margin, "waste_weekly": waste_weekly,
            "waste_by_category": waste_by_category, "stock_value": stock_series, "supplier_performance": suppliers,
        },
        "attention": AlertSerializer(alerts[:8], many=True).data,
        "attention_total": len(alerts),
        "alert_counts": dict(Alert.objects.filter(unit__in=units, status="open").values_list("priority").annotate(n=Count("id"))),
        "is_demo": org.is_demo,
    }
