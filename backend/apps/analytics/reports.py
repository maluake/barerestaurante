"""Central de relatórios. Cada relatório declara colunas, linhas e a explicação da fórmula."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Max, Sum

from apps.finance.services import sales_totals
from apps.inventory.analytics import annotate_stock, period_bounds
from apps.inventory.models import InventoryCountItem, Lot, Product, ProductCostHistory, StockMovement, WasteRecord
from apps.purchasing.models import PurchaseOrder, PurchaseOrderItem, ShoppingListItem

from . import metrics

ZERO = Decimal("0")
C2 = Decimal("0.01")

REPORTS = {}


def report(key, title, description, finance=False):
    def deco(fn):
        REPORTS[key] = {"key": key, "title": title, "description": description, "fn": fn, "finance": finance}
        return fn
    return deco


def col(key, label, type_="text"):
    return {"key": key, "label": label, "type": type_}


def _filter_products(qs, f, prefix=""):
    if f.get("category"):
        qs = qs.filter(**{f"{prefix}category_id": f["category"]})
    if f.get("product"):
        qs = qs.filter(**{f"{prefix}id" if not prefix else f"{prefix}id": f["product"]})
    return qs


@report("sales_by_period", "Vendas por período", "Receita líquida = bruto − descontos − taxas + taxa de entrega. "
        "Ticket médio = receita líquida ÷ número de vendas concluídas.")
def sales_by_period(ctx, f):
    grain = f.get("grain") or ("day" if (ctx["end"] - ctx["start"]).days <= 62 else "month")
    rows = metrics.sales_series(ctx["units"], ctx["start"], ctx["end"], grain)
    for r in rows:
        r["ticket"] = (r["net"] / r["count"]).quantize(C2) if r["count"] else ZERO
        r["margin"] = r["net"] - r["cogs"]
    cols = [col("period", "Período", "date"), col("count", "Vendas", "int"), col("gross", "Bruto", "money"),
            col("net", "Líquido", "money"), col("ticket", "Ticket médio", "money"), col("cogs", "CMV", "money"),
            col("margin", "Margem de contribuição", "money")]
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("gross", "net", "cogs", "margin")}
    totals["count"] = sum(r["count"] for r in rows)
    totals["ticket"] = (totals["net"] / totals["count"]).quantize(C2) if totals["count"] else ZERO
    return cols, rows, totals


@report("top_items", "Produtos mais e menos vendidos", "Quantidade e receita por item do cardápio no período (vendas concluídas).")
def top_items(ctx, f):
    rows = metrics.item_sales(ctx["units"], ctx["start"], ctx["end"])
    from apps.menu.models import MenuItem

    sold = {r["menu_item_id"] for r in rows}
    for mi in MenuItem.objects.filter(organization=ctx["org"], status="active").exclude(pk__in=sold):
        rows.append({"menu_item_id": mi.pk, "item": mi.name, "category": mi.category.name if mi.category else None,
                     "quantity": ZERO, "revenue": ZERO, "theoretical_cost": ZERO, "contribution_margin": ZERO,
                     "margin_percent": None})
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    cols = [col("rank", "#", "int"), col("item", "Item"), col("category", "Categoria"), col("quantity", "Qtd. vendida", "number"),
            col("revenue", "Receita", "money")]
    return cols, rows, None


@report("margin_items", "Margem de contribuição por item", "Margem = receita do item − custo teórico (ficha técnica × "
        "custo de reposição no momento da venda). Itens sem ficha técnica aparecem com custo zero.", finance=True)
def margin_items(ctx, f):
    rows = sorted(metrics.item_sales(ctx["units"], ctx["start"], ctx["end"]), key=lambda r: -r["contribution_margin"])
    cols = [col("item", "Item"), col("quantity", "Qtd.", "number"), col("revenue", "Receita", "money"),
            col("theoretical_cost", "Custo teórico", "money"), col("contribution_margin", "Margem", "money"),
            col("margin_percent", "Margem %", "percent")]
    return cols, rows, None


@report("menu_costs", "Fichas técnicas: custo e margem atuais", "Custo por porção pela política de custeio (custo de "
        "reposição) e variação em relação a 30 dias atrás.", finance=True)
def menu_costs(ctx, f):
    from apps.menu.models import MenuItem

    since = ctx["end"] - timedelta(days=30)
    rows = []
    for mi in MenuItem.objects.filter(organization=ctx["org"], status="active").select_related("category").prefetch_related("cost_snapshots"):
        old = next((s for s in mi.cost_snapshots.all() if s.created_at.date() <= since), None)
        margin = mi.price - mi.theoretical_cost
        rows.append({
            "item": mi.name, "category": mi.category.name if mi.category else None, "price": mi.price,
            "cost": mi.theoretical_cost.quantize(C2), "margin": margin.quantize(C2),
            "margin_percent": (margin / mi.price * 100).quantize(Decimal("0.1")) if mi.price else None,
            "cost_30d_ago": old.cost_per_portion.quantize(C2) if old else None,
            "cost_change_percent": metrics.pct_change(mi.theoretical_cost, old.cost_per_portion) if old else None,
            "complete": "Sim" if mi.cost_complete else "Não",
        })
    rows.sort(key=lambda r: (r["cost_change_percent"] is None, -(r["cost_change_percent"] or 0)))
    cols = [col("item", "Item"), col("category", "Categoria"), col("price", "Preço", "money"), col("cost", "Custo/porção", "money"),
            col("margin", "Margem", "money"), col("margin_percent", "Margem %", "percent"),
            col("cost_30d_ago", "Custo há 30 dias", "money"), col("cost_change_percent", "Variação %", "percent"),
            col("complete", "Custo completo")]
    return cols, rows, None


@report("cost_evolution", "Evolução dos custos dos ingredientes", "Histórico do custo de reposição (último custo de compra) por produto.")
def cost_evolution(ctx, f):
    s, e = period_bounds(ctx["units"][0], ctx["start"], ctx["end"])
    qs = ProductCostHistory.objects.filter(product__organization=ctx["org"], created_at__gte=s, created_at__lt=e).select_related("product__unit", "product__category")
    if f.get("product"):
        qs = qs.filter(product_id=f["product"])
    if f.get("category"):
        qs = qs.filter(product__category_id=f["category"])
    rows = [{"date": h.created_at, "product": h.product.name, "unit": h.product.unit.code, "previous_cost": h.previous_cost,
             "cost": h.cost, "variation_percent": metrics.pct_change(h.cost, h.previous_cost) if h.previous_cost else None,
             "source": {"receipt": "Recebimento", "manual": "Manual", "initial": "Inicial"}.get(h.source, h.source),
             "reference": h.reference} for h in qs.order_by("-created_at")]
    cols = [col("date", "Data", "datetime"), col("product", "Produto"), col("unit", "Un."), col("previous_cost", "Custo anterior", "money4"),
            col("cost", "Novo custo", "money4"), col("variation_percent", "Variação %", "percent"), col("source", "Origem"),
            col("reference", "Referência")]
    return cols, rows, None


@report("cogs", "Custo das mercadorias vendidas (CMV)", "CMV real = custo dos lotes consumidos pelas vendas (FEFO), "
        "líquido de estornos. Comparado à receita líquida.", finance=True)
def cogs(ctx, f):
    s, e = period_bounds(ctx["units"][0], ctx["start"], ctx["end"])
    qs = StockMovement.objects.filter(unit__in=ctx["units"], occurred_at__gte=s, occurred_at__lt=e, type__in=("sale", "production"))
    rev = StockMovement.objects.filter(unit__in=ctx["units"], occurred_at__gte=s, occurred_at__lt=e, type="reversal",
                                       reversal_of__type__in=("sale", "production"))
    by_cat = defaultdict(lambda: ZERO)
    for r in qs.values("product__category__name").annotate(v=Sum("total_cost")):
        by_cat[r["product__category__name"] or "Sem categoria"] += r["v"]
    for r in rev.values("product__category__name").annotate(v=Sum("total_cost")):
        by_cat[r["product__category__name"] or "Sem categoria"] -= r["v"]
    st = sales_totals(ctx["units"], s, e)
    total = sum(by_cat.values(), ZERO)
    rows = [{"category": k, "value": v.quantize(C2), "share": (v / total * 100).quantize(Decimal("0.1")) if total else None}
            for k, v in sorted(by_cat.items(), key=lambda x: -x[1])]
    cols = [col("category", "Categoria do insumo"), col("value", "CMV", "money"), col("share", "% do CMV", "percent")]
    return cols, rows, {"value": total.quantize(C2), "net_revenue": st["net"],
                        "cogs_percent": (total / st["net"] * 100).quantize(Decimal("0.1")) if st["net"] else None}


@report("consumption_variance", "Consumo teórico × real", "Teórico = fichas técnicas × itens vendidos. Real = baixas de "
        "venda + perdas + ajustes negativos de inventário. Diferenças indicam porcionamento, perdas não registradas ou fichas desatualizadas.")
def consumption_variance(ctx, f):
    unit = ctx["units"][0]
    theo, actual, waste, adj = metrics.theoretical_vs_actual(unit, ctx["start"], ctx["end"])
    ids = set(theo) | set(waste) | {k for k, v in adj.items() if v > 0}
    products = {p.pk: p for p in Product.objects.filter(pk__in=ids).select_related("unit")}
    rows = []
    for pid in ids:
        p = products.get(pid)
        if not p:
            continue
        real = actual.get(pid, ZERO) + waste.get(pid, ZERO) + max(adj.get(pid, ZERO), ZERO)
        t = theo.get(pid, ZERO)
        diff = real - t
        rows.append({"product": p.name, "unit": p.unit.code, "theoretical": t.quantize(Decimal("0.001")),
                     "sales_consumption": actual.get(pid, ZERO).quantize(Decimal("0.001")),
                     "waste": waste.get(pid, ZERO).quantize(Decimal("0.001")),
                     "adjustments": max(adj.get(pid, ZERO), ZERO).quantize(Decimal("0.001")),
                     "real": real.quantize(Decimal("0.001")), "difference": diff.quantize(Decimal("0.001")),
                     "difference_percent": (diff / t * 100).quantize(Decimal("0.1")) if t else None,
                     "difference_value": (diff * p.cost_price).quantize(C2)})
    rows.sort(key=lambda r: -abs(r["difference_value"]))
    cols = [col("product", "Insumo"), col("unit", "Un."), col("theoretical", "Teórico", "number"),
            col("sales_consumption", "Baixa por vendas", "number"), col("waste", "Perdas", "number"),
            col("adjustments", "Ajustes (faltas)", "number"), col("real", "Real", "number"),
            col("difference", "Diferença", "number"), col("difference_percent", "Dif. %", "percent"),
            col("difference_value", "Dif. R$", "money")]
    return cols, rows, None


@report("waste", "Desperdício", "Perdas e descartes registrados, valorizados pelo custo dos lotes.")
def waste(ctx, f):
    s, e = period_bounds(ctx["units"][0], ctx["start"], ctx["end"])
    qs = WasteRecord.objects.filter(unit__in=ctx["units"], occurred_at__gte=s, occurred_at__lt=e).select_related("product__unit", "product__category", "user", "unit")
    if f.get("category"):
        qs = qs.filter(product__category_id=f["category"])
    if f.get("product"):
        qs = qs.filter(product_id=f["product"])
    group = f.get("group") or "category"
    if group == "detail":
        rows = [{"date": w.occurred_at, "unit_name": w.unit.name, "product": w.product.name, "category": w.product.category.name if w.product.category else None,
                 "quantity": w.quantity, "unit": w.product.unit.code, "value": w.total_cost, "reason": w.get_reason_display(),
                 "user": w.user.username if w.user else "", "notes": w.notes} for w in qs]
        cols = [col("date", "Data", "datetime"), col("unit_name", "Unidade"), col("product", "Produto"), col("category", "Categoria"),
                col("quantity", "Qtd.", "number"), col("unit", "Un."), col("value", "Custo", "money"), col("reason", "Motivo"),
                col("user", "Responsável"), col("notes", "Observações")]
    else:
        field = {"category": "product__category__name", "product": "product__name", "reason": "reason", "unit": "unit__name"}[group]
        rows = []
        labels = dict(WasteRecord.REASONS)
        for r in qs.values(field).annotate(value=Sum("total_cost"), n=Count("id")).order_by("-value"):
            name = r[field] or "Sem categoria"
            rows.append({"group": labels.get(name, name) if group == "reason" else name, "records": r["n"], "value": r["value"]})
        cols = [col("group", {"category": "Categoria", "product": "Produto", "reason": "Motivo", "unit": "Unidade"}[group]),
                col("records", "Registros", "int"), col("value", "Custo", "money")]
    return cols, rows, {"value": qs.aggregate(v=Sum("total_cost"))["v"] or ZERO}


@report("expiring", "Produtos próximos do vencimento", "Lotes ativos que vencem nos próximos 30 dias (ou já vencidos).")
def expiring(ctx, f):
    today = ctx["today"]
    qs = Lot.objects.filter(unit__in=ctx["units"], status="active", quantity_remaining__gt=0, expires_at__isnull=False,
                            expires_at__lte=today + timedelta(days=int(f.get("days") or 30))).select_related("product__unit", "location", "unit").order_by("expires_at")
    rows = [{"product": l.product.name, "unit_name": l.unit.name, "lot": l.code or f"#{l.pk}", "expires_at": l.expires_at,
             "days": (l.expires_at - today).days, "quantity": l.quantity_remaining, "unit": l.product.unit.code,
             "value": (l.quantity_remaining * l.unit_cost).quantize(C2), "location": l.location.name if l.location else ""} for l in qs]
    cols = [col("product", "Produto"), col("unit_name", "Unidade"), col("lot", "Lote"), col("expires_at", "Validade", "date"),
            col("days", "Dias", "int"), col("quantity", "Qtd.", "number"), col("unit", "Un."), col("value", "Valor", "money"),
            col("location", "Local")]
    return cols, rows, {"value": sum((r["value"] for r in rows), ZERO)}


@report("stagnant", "Produtos parados no estoque", "Produtos com saldo e sem consumo (vendas/produção) nos últimos N dias "
        "(padrão 30). Valor = saldo × custo de reposição.")
def stagnant(ctx, f):
    days = int(f.get("days") or 30)
    unit = ctx["units"][0]
    since = ctx["today"] - timedelta(days=days)
    last = dict(StockMovement.objects.filter(unit=unit, type__in=("sale", "production")).values("product_id").annotate(
        m=Max("occurred_at")).values_list("product_id", "m"))
    rows = []
    for p in annotate_stock(Product.objects.filter(organization=ctx["org"], status="active").select_related("unit", "category"), unit):
        if p.quantity <= 0:
            continue
        lm = last.get(p.pk)
        if lm is None or lm.date() < since:
            rows.append({"product": p.name, "category": p.category.name if p.category else None, "quantity": p.quantity,
                         "unit": p.unit.code, "value": (p.quantity * p.cost_price).quantize(C2),
                         "last_consumption": lm, "days_without": (ctx["today"] - lm.date()).days if lm else None})
    rows.sort(key=lambda r: -r["value"])
    cols = [col("product", "Produto"), col("category", "Categoria"), col("quantity", "Saldo", "number"), col("unit", "Un."),
            col("value", "Valor parado", "money"), col("last_consumption", "Último consumo", "datetime"),
            col("days_without", "Dias sem consumo", "int")]
    return cols, rows, {"value": sum((r["value"] for r in rows), ZERO)}


@report("inventory_differences", "Diferenças de inventário", "Contado − sistema no momento da contagem, valorizado pelo custo de reposição.")
def inventory_differences(ctx, f):
    s, e = period_bounds(ctx["units"][0], ctx["start"], ctx["end"])
    qs = InventoryCountItem.objects.filter(count__unit__in=ctx["units"], count__status="closed", count__closed_at__gte=s,
                                           count__closed_at__lt=e, counted_quantity__isnull=False).select_related("product__unit", "count", "counted_by")
    rows = []
    for i in qs:
        if not i.difference:
            continue
        rows.append({"count": i.count_id, "date": i.count.closed_at, "product": i.product.name, "system": i.system_quantity,
                     "counted": i.counted_quantity, "difference": i.difference, "unit": i.product.unit.code,
                     "value": i.value_difference, "user": i.counted_by.username if i.counted_by else "", "reason": i.count.reason})
    cols = [col("count", "Inventário", "int"), col("date", "Data", "datetime"), col("product", "Produto"), col("system", "Sistema", "number"),
            col("counted", "Contado", "number"), col("difference", "Diferença", "number"), col("unit", "Un."),
            col("value", "Valor", "money"), col("user", "Responsável"), col("reason", "Motivo")]
    return cols, rows, {"value": sum((r["value"] for r in rows), ZERO)}


@report("supplier_performance", "Desempenho dos fornecedores", "Pontualidade = entregas até a data prevista ÷ entregas avaliadas. "
        "Atendimento = quantidade recebida ÷ pedida.")
def supplier_performance(ctx, f):
    rows = metrics.supplier_performance(ctx["org"], ctx["units"], ctx["start"], ctx["end"])
    cols = [col("supplier", "Fornecedor"), col("orders", "Pedidos", "int"), col("received_value", "Valor recebido", "money"),
            col("on_time_rate", "Pontualidade %", "percent"), col("fill_rate", "Atendimento %", "percent"), col("issues", "Ocorrências", "int")]
    return cols, rows, None


@report("purchase_history", "Histórico de compras", "Pedidos de compra criados no período.")
def purchase_history(ctx, f):
    s, e = period_bounds(ctx["units"][0], ctx["start"], ctx["end"])
    qs = PurchaseOrder.objects.filter(unit__in=ctx["units"], created_at__gte=s, created_at__lt=e).select_related("supplier", "created_by", "approved_by").prefetch_related("items", "receipts")
    if f.get("supplier"):
        qs = qs.filter(supplier_id=f["supplier"])
    rows = [{"number": po.number, "date": po.created_at, "supplier": str(po.supplier), "status": po.get_status_display(),
             "total": po.total, "received": sum((r.total for r in po.receipts.all()), ZERO),
             "created_by": po.created_by.username if po.created_by else "", "approved_by": po.approved_by.username if po.approved_by else "",
             "expected_delivery": po.expected_delivery} for po in qs]
    cols = [col("number", "Nº", "int"), col("date", "Data", "datetime"), col("supplier", "Fornecedor"), col("status", "Situação"),
            col("total", "Total pedido", "money"), col("received", "Total recebido", "money"), col("created_by", "Criado por"),
            col("approved_by", "Aprovado por"), col("expected_delivery", "Previsão", "date")]
    return cols, rows, {"total": sum((r["total"] for r in rows), ZERO), "received": sum((r["received"] for r in rows), ZERO)}


@report("planned_vs_actual", "Compras planejadas × realizadas", "Sugerido pela lista inteligente × quantidade pedida × recebida, por produto.")
def planned_vs_actual(ctx, f):
    s, e = period_bounds(ctx["units"][0], ctx["start"], ctx["end"])
    planned = defaultdict(lambda: ZERO)
    for r in ShoppingListItem.objects.filter(shopping_list__unit__in=ctx["units"], shopping_list__created_at__gte=s,
                                             shopping_list__created_at__lt=e, shopping_list__status="ordered", selected=True).values("product_id").annotate(q=Sum("suggested_quantity")):
        planned[r["product_id"]] += r["q"]
    from apps.inventory.units import convert

    ordered = defaultdict(lambda: ZERO)
    received = defaultdict(lambda: ZERO)
    for it in PurchaseOrderItem.objects.filter(order__unit__in=ctx["units"], order__created_at__gte=s, order__created_at__lt=e).exclude(
            order__status="cancelled").select_related("product__unit", "purchase_unit"):
        try:
            per = convert(1, it.purchase_unit, it.product.unit, it.product)
        except Exception:
            continue
        ordered[it.product_id] += it.quantity * per
        received[it.product_id] += it.quantity_received * per
    ids = set(planned) | set(ordered)
    products = {p.pk: p for p in Product.objects.filter(pk__in=ids).select_related("unit")}
    rows = [{"product": products[i].name, "unit": products[i].unit.code, "planned": planned.get(i, ZERO).quantize(Decimal("0.001")),
             "ordered": ordered.get(i, ZERO).quantize(Decimal("0.001")), "received": received.get(i, ZERO).quantize(Decimal("0.001")),
             "fill_rate": (received.get(i, ZERO) / ordered[i] * 100).quantize(Decimal("0.1")) if ordered.get(i) else None}
            for i in ids if i in products]
    cols = [col("product", "Produto"), col("unit", "Un."), col("planned", "Planejado", "number"), col("ordered", "Pedido", "number"),
            col("received", "Recebido", "number"), col("fill_rate", "Recebido/Pedido %", "percent")]
    return cols, rows, None


@report("period_comparison", "Comparação entre períodos", "Período selecionado × período anterior de mesma duração.", finance=True)
def period_comparison(ctx, f):
    from apps.finance.services import financial_summary

    length = (ctx["end"] - ctx["start"]).days + 1
    cur = financial_summary(ctx["org"], ctx["units"], ctx["start"], ctx["end"])
    prev = financial_summary(ctx["org"], ctx["units"], ctx["start"] - timedelta(days=length), ctx["start"] - timedelta(days=1))
    labels = [("sales_count", "Vendas", "int"), ("gross", "Faturamento bruto", "money"), ("discounts", "Descontos", "money"),
              ("fees", "Taxas", "money"), ("net", "Receita líquida", "money"), ("average_ticket", "Ticket médio", "money"),
              ("cogs", "CMV", "money"), ("contribution_margin", "Margem de contribuição", "money"),
              ("waste_value", "Desperdício", "money"), ("registered_expenses", "Despesas registradas", "money"),
              ("operating_result_estimate", "Resultado operacional estimado", "money")]
    rows = [{"metric": l, "current": cur[k], "previous": prev[k], "change_percent": metrics.pct_change(cur[k], prev[k]), "type": t}
            for k, l, t in labels]
    cols = [col("metric", "Indicador"), col("current", "Período atual", "auto"), col("previous", "Período anterior", "auto"),
            col("change_percent", "Variação %", "percent")]
    return cols, rows, None


@report("prep_time", "Tempo de preparo dos pedidos", "Espera = recebido → início do preparo. Preparo = início → pronto. "
        "Valores em minutos.")
def prep_time(ctx, f):
    data = metrics.prep_times(ctx["units"], ctx["start"], ctx["end"])
    groups = defaultdict(list)
    for r in data:
        groups[r["origin"]].append(r)

    def avg(lst, k):
        return round(sum(x[k] for x in lst) / len(lst), 1) if lst else None

    rows = [{"origin": o, "orders": len(lst), "wait": avg(lst, "wait"), "prep": avg(lst, "prep"), "total": avg(lst, "total"),
             "max_total": round(max(x["total"] for x in lst), 1)} for o, lst in groups.items()]
    cols = [col("origin", "Origem"), col("orders", "Pedidos", "int"), col("wait", "Espera média (min)", "number"),
            col("prep", "Preparo médio (min)", "number"), col("total", "Total médio (min)", "number"), col("max_total", "Maior tempo (min)", "number")]
    return cols, rows, {"orders": len(data), "total": avg(data, "total")}


@report("sustainability", "Indicadores de sustentabilidade", "Desperdício em massa/volume, % do valor comprado, "
        "participação de vencidos e itens salvos do vencimento (lotes que venciam em até 3 dias e foram consumidos).")
def sustainability(ctx, f):
    s, e = period_bounds(ctx["units"][0], ctx["start"], ctx["end"])
    wqs = WasteRecord.objects.filter(unit__in=ctx["units"], occurred_at__gte=s, occurred_at__lt=e).select_related("product__unit")
    kg = ZERO
    liters = ZERO
    for w in wqs:
        u = w.product.unit
        if u.dimension == "mass" and u.factor_to_base:
            kg += w.quantity * u.factor_to_base / 1000
        elif u.dimension == "volume" and u.factor_to_base:
            liters += w.quantity * u.factor_to_base / 1000
    value = wqs.aggregate(v=Sum("total_cost"))["v"] or ZERO
    expired = wqs.filter(reason="expired").aggregate(v=Sum("total_cost"))["v"] or ZERO
    purchased = StockMovement.objects.filter(unit__in=ctx["units"], type="receipt", occurred_at__gte=s, occurred_at__lt=e).aggregate(v=Sum("total_cost"))["v"] or ZERO
    saved = ZERO
    for m in StockMovement.objects.filter(unit__in=ctx["units"], type="sale", occurred_at__gte=s, occurred_at__lt=e,
                                          lot__expires_at__isnull=False).select_related("lot"):
        if (m.lot.expires_at - m.occurred_at.date()).days <= 3:
            saved += m.total_cost
    rows = [
        {"metric": "Desperdício (massa)", "value": f"{kg.quantize(Decimal('0.01'))} kg"},
        {"metric": "Desperdício (volume)", "value": f"{liters.quantize(Decimal('0.01'))} L"},
        {"metric": "Valor desperdiçado", "value": f"R$ {value.quantize(C2)}"},
        {"metric": "% do valor comprado", "value": f"{(value / purchased * 100).quantize(Decimal('0.1'))}%" if purchased else "—"},
        {"metric": "Participação de produtos vencidos nas perdas", "value": f"{(expired / value * 100).quantize(Decimal('0.1'))}%" if value else "—"},
        {"metric": "Valor consumido de lotes a até 3 dias do vencimento (salvo)", "value": f"R$ {saved.quantize(C2)}"},
    ]
    return [col("metric", "Indicador"), col("value", "Valor")], rows, None


@report("ticket", "Ticket médio por canal", "Receita líquida ÷ vendas, por canal de venda.")
def ticket(ctx, f):
    from apps.sales.models import Sale

    s, e = period_bounds(ctx["units"][0], ctx["start"], ctx["end"])
    labels = dict(Sale.CHANNELS)
    rows = []
    for r in Sale.objects.filter(unit__in=ctx["units"], status="completed", occurred_at__gte=s, occurred_at__lt=e).values("channel").annotate(
            net=Sum("net_amount"), n=Count("id")).order_by("-net"):
        rows.append({"channel": labels.get(r["channel"], r["channel"]), "sales": r["n"], "net": r["net"],
                     "ticket": (r["net"] / r["n"]).quantize(C2) if r["n"] else ZERO})
    cols = [col("channel", "Canal"), col("sales", "Vendas", "int"), col("net", "Receita líquida", "money"), col("ticket", "Ticket médio", "money")]
    return cols, rows, None


def run_report(key, ctx, filters):
    r = REPORTS[key]
    cols, rows, totals = r["fn"](ctx, filters)
    return {"key": key, "title": r["title"], "description": r["description"], "columns": cols, "rows": rows,
            "totals": totals, "start": ctx["start"], "end": ctx["end"], "units": [u.name for u in ctx["units"]]}

