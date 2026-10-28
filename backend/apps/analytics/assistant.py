"""Assistente do Negócio.

Primeira versão baseada em regras e consultas ao banco (sem IA externa). Cada resposta
separa FATOS (dados registrados), ESTIMATIVAS (projeções) e SUGESTÕES (recomendações).
O assistente é somente leitura: nunca altera estoque nem cria compras.

Para integrar um modelo de linguagem no futuro, implemente `AssistantProvider` em
`providers.py`: ele recebe a pergunta e o contexto factual já calculado aqui, e só pode
reescrever a resposta — as chaves de API ficam apenas no backend (settings).
"""

import re
import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum

from apps.inventory.analytics import annotate_stock, consumption_rates, period_bounds, stock_value
from apps.inventory.models import Lot, Product, ProductCostHistory, WasteRecord
from apps.inventory.services import today_for

from . import metrics

ZERO = Decimal("0")
C2 = Decimal("0.01")


def brl(v):
    s = f"{Decimal(v).quantize(C2):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def qty(v, unit):
    return f"{Decimal(v).quantize(Decimal('0.01')).normalize():f} {unit}".replace(".", ",")


def normalize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


INTENTS = [
    ("buy_less", [r"menor quantidade", r"comprar menos", r"reduzir (a )?compra"]),
    ("expired_loss", [r"vencid", r"perdi com"]),
    ("what_to_buy", [r"(o que|oque).*(comprar|compra)", r"preciso comprar", r"lista de compra", r"comprar amanha"]),
    ("best_supplier", [r"fornecedor", r"custo total", r"mais barato"]),
    ("waste", [r"desperdic", r"perda", r"jogando fora"]),
    ("cost_increase", [r"caro", r"aument", r"subi", r"inflac", r"preco.*(ingrediente|insumo)"]),
    ("margin", [r"margem", r"lucrativ", r"rentab"]),
    ("stock_value", [r"parado", r"dinheiro.*estoque", r"valor.*estoque", r"capital"]),
    ("running_out", [r"acabar", r"acabando", r"faltar", r"falta", r"estoque baixo", r"perto de acabar"]),
    ("expiring", [r"vencer", r"vencimento", r"validade"]),
    ("weekly_changes", [r"mudanc", r"semana", r"resumo", r"novidade"]),
    ("sales", [r"vend", r"faturamento", r"faturei"]),
]

EXAMPLES = [
    "O que preciso comprar amanhã?", "Quais produtos estão gerando mais desperdício?",
    "Quais ingredientes estão ficando caros?", "Qual fornecedor tem o melhor custo total para esta lista?",
    "Quais pratos perderam margem neste mês?", "Quanto dinheiro tenho parado no estoque?",
    "Quais produtos estão perto de acabar?", "Quanto perdi com produtos vencidos?",
    "Quais itens devo comprar em menor quantidade?", "Quais foram as principais mudanças desta semana?",
]


def classify(question):
    q = normalize(question)
    for intent, patterns in INTENTS:
        if any(re.search(p, q) for p in patterns):
            return intent
    return "help"


class Answer:
    def __init__(self, intent, title):
        self.intent = intent
        self.title = title
        self.sections = []
        self.table = None
        self.links = []

    def fact(self, text):
        self.sections.append({"kind": "fact", "text": text})

    def estimate(self, text):
        self.sections.append({"kind": "estimate", "text": text})

    def suggest(self, text):
        self.sections.append({"kind": "suggestion", "text": text})

    def warn(self, text):
        self.sections.append({"kind": "warning", "text": text})

    def link(self, label, path):
        self.links.append({"label": label, "path": path})

    def as_dict(self):
        return {"intent": self.intent, "title": self.title, "sections": self.sections, "table": self.table, "links": self.links}


def answer(question, unit, perms):
    intent = classify(question)
    handler = HANDLERS.get(intent, h_help)
    needed = REQUIRED_PERMS.get(intent)
    if needed and needed not in perms:
        a = Answer(intent, "Sem permissão para esta consulta")
        a.warn("Seu perfil de acesso não permite consultar estas informações. Fale com o proprietário do estabelecimento.")
        return a.as_dict()
    return handler(unit, question).as_dict()


# --------------------------------------------------------------------------- handlers


def h_help(unit, question):
    a = Answer("help", "Como posso ajudar")
    a.fact("Respondo com base nos dados registrados no sistema: estoque, validades, vendas, compras, cotações e perdas.")
    a.suggest("Experimente perguntar: " + " · ".join(f"“{e}”" for e in EXAMPLES[:6]))
    return a


def h_what_to_buy(unit, question):
    from apps.purchasing.services import compute_suggestions

    a = Answer("what_to_buy", "O que comprar")
    suggestions, coverage, today = compute_suggestions(unit, coverage_days=2 if "amanha" in normalize(question) else None)
    if not suggestions:
        a.fact("Nenhum produto precisa de reposição no horizonte analisado, considerando estoque, consumo e compras pendentes.")
        return a
    total = sum((s["estimated_cost"] for s in suggestions), ZERO)
    urgent = [s for s in suggestions if s["reorder_date"] and s["reorder_date"] <= today + timedelta(days=2)]
    a.fact(f"{len(suggestions)} produto(s) com reposição recomendada; {len(urgent)} ficam abaixo do mínimo em até 2 dias.")
    a.estimate(f"Custo estimado da lista: {brl(total)} (pelas cotações cadastradas ou último custo de compra).")
    limited = [s for s in suggestions if s["confidence"] == "limited"]
    if limited:
        a.warn(f"{len(limited)} sugestão(ões) com estimativa limitada por falta de histórico de consumo.")
    a.table = {"columns": [{"key": "product", "label": "Produto"}, {"key": "quantity", "label": "Sugerido"},
                           {"key": "reorder", "label": "Abaixo do mínimo em"}, {"key": "cost", "label": "Custo estimado"},
                           {"key": "why", "label": "Justificativa"}],
               "rows": [{"product": s["product"].name, "quantity": qty(s["suggested_quantity"], s["product"].unit.code),
                         "reorder": s["reorder_date"].strftime("%d/%m") if s["reorder_date"] else "—",
                         "cost": brl(s["estimated_cost"]), "why": s["justification"]} for s in suggestions[:15]]}
    a.suggest("Revise as quantidades e gere os pedidos de compra pela lista inteligente. Nada é comprado sem sua confirmação.")
    a.link("Abrir lista de compras", "/compras/lista")
    return a


def h_waste(unit, question):
    a = Answer("waste", "Desperdício")
    today = today_for(unit)
    start = today - timedelta(days=30)
    s, e = period_bounds(unit, start, today)
    qs = WasteRecord.objects.filter(unit=unit, occurred_at__gte=s, occurred_at__lt=e)
    total = qs.aggregate(v=Sum("total_cost"))["v"] or ZERO
    if not total:
        a.fact("Nenhuma perda registrada nos últimos 30 dias.")
        a.warn("Se houve perdas não registradas, o consumo real aparece como diferença de inventário.")
        return a
    rows = list(qs.values("product__name", "product__unit__code").annotate(v=Sum("total_cost"), q=Sum("quantity")).order_by("-v")[:8])
    a.fact(f"Perdas registradas nos últimos 30 dias: {brl(total)}.")
    top = rows[0]
    a.fact(f"Maior foco: {top['product__name']} com {brl(top['v'])} ({(top['v'] / total * 100).quantize(Decimal('0.1'))}% do total).")
    reasons = list(qs.values("reason").annotate(v=Sum("total_cost")).order_by("-v"))
    labels = dict(WasteRecord.REASONS)
    if reasons:
        a.fact("Principais motivos: " + ", ".join(f"{labels.get(r['reason'], r['reason'])} ({brl(r['v'])})" for r in reasons[:3]) + ".")
    if reasons and reasons[0]["reason"] == "expired":
        a.suggest("A maior parte vem de vencimentos: reduza o tamanho das compras desses itens e reforce o FEFO na arrumação.")
    elif reasons and reasons[0]["reason"] == "preparation":
        a.suggest("Padronize o porcionamento com as fichas técnicas e treine a equipe nos itens com mais perda.")
    else:
        a.suggest("Revise armazenamento e manuseio dos itens com maior perda.")
    a.table = {"columns": [{"key": "p", "label": "Produto"}, {"key": "q", "label": "Quantidade"}, {"key": "v", "label": "Custo"}],
               "rows": [{"p": r["product__name"], "q": qty(r["q"], r["product__unit__code"]), "v": brl(r["v"])} for r in rows]}
    a.link("Analisar desperdício", "/estoque/perdas")
    return a


def h_expired_loss(unit, question):
    a = Answer("expired_loss", "Perdas com produtos vencidos")
    today = today_for(unit)
    month_start = today.replace(day=1)
    s, e = period_bounds(unit, month_start, today)
    s90, _ = period_bounds(unit, today - timedelta(days=90), today)
    month = WasteRecord.objects.filter(unit=unit, reason="expired", occurred_at__gte=s, occurred_at__lt=e).aggregate(v=Sum("total_cost"))["v"] or ZERO
    q90 = WasteRecord.objects.filter(unit=unit, reason="expired", occurred_at__gte=s90, occurred_at__lt=e)
    total90 = q90.aggregate(v=Sum("total_cost"))["v"] or ZERO
    a.fact(f"Descartes por vencimento neste mês: {brl(month)}. Nos últimos 90 dias: {brl(total90)}.")
    pending = Lot.objects.filter(unit=unit, status="active", quantity_remaining__gt=0, expires_at__lt=today).select_related("product")
    pend_value = sum((l.quantity_remaining * l.unit_cost for l in pending), ZERO)
    if pending:
        a.warn(f"Há {len(pending)} lote(s) vencido(s) ainda no estoque ({brl(pend_value)}). Isole-os e registre o descarte; não utilize.")
        a.link("Ver validades", "/estoque/validades")
    rows = list(q90.values("product__name").annotate(v=Sum("total_cost")).order_by("-v")[:6])
    if rows:
        a.table = {"columns": [{"key": "p", "label": "Produto"}, {"key": "v", "label": "Perdido (90 dias)"}],
                   "rows": [{"p": r["product__name"], "v": brl(r["v"])} for r in rows]}
        a.suggest("Para esses produtos, compre em menor quantidade e com maior frequência.")
    return a


def h_cost_increase(unit, question):
    a = Answer("cost_increase", "Ingredientes ficando mais caros")
    today = today_for(unit)
    since = today - timedelta(days=60)
    rows = []
    for p in Product.objects.filter(organization=unit.organization, status="active", cost_history__created_at__date__gte=since).distinct().select_related("unit"):
        hist = list(p.cost_history.filter(created_at__date__gte=since).order_by("created_at"))
        first = hist[0].previous_cost or hist[0].cost
        if first and p.cost_price > first:
            rows.append((p, first, (p.cost_price - first) / first * 100))
    rows.sort(key=lambda r: -r[2])
    if not rows:
        a.fact("Nenhum ingrediente teve aumento de custo registrado nos últimos 60 dias.")
        return a
    a.fact(f"{len(rows)} ingrediente(s) com aumento de custo nos últimos 60 dias (pelos recebimentos registrados).")
    a.table = {"columns": [{"key": "p", "label": "Ingrediente"}, {"key": "a", "label": "Antes"}, {"key": "n", "label": "Agora"},
                           {"key": "v", "label": "Variação"}],
               "rows": [{"p": p.name, "a": f"{brl(f)}/{p.unit.code}", "n": f"{brl(p.cost_price)}/{p.unit.code}",
                         "v": f"+{v.quantize(Decimal('0.1'))}%"} for p, f, v in rows[:10]]}
    a.suggest("Compare as cotações desses itens e avalie ajustar fichas técnicas ou preços dos pratos mais afetados.")
    a.link("Comparar fornecedores", "/compras/comparador")
    a.link("Ver oportunidades", "/compras/oportunidades")
    return a


def h_best_supplier(unit, question):
    from apps.purchasing.services import compare_list, compute_suggestions

    a = Answer("best_supplier", "Melhor custo total por fornecedor")
    suggestions, _, today = compute_suggestions(unit)
    items = [(s["product"], s["suggested_quantity"]) for s in suggestions]
    if not items:
        a.fact("Não há itens a comprar na lista projetada agora. Use o comparador para simular uma lista específica.")
        a.link("Abrir comparador", "/compras/comparador")
        return a
    cmp = compare_list(unit.organization, items, today)
    a.fact(f"Comparação para os {len(items)} itens da lista de compras projetada, usando a cotação mais recente de cada fornecedor.")
    best_single = cmp["best_single_supplier"]
    split = cmp["best_split"]
    if best_single:
        a.estimate(f"Comprando tudo em um fornecedor, o menor custo total é com {best_single['supplier_name']}: {brl(best_single['total'])} (frete incluso).")
    if split["suppliers"]:
        a.estimate(f"Dividindo entre fornecedores (frete contado uma vez por fornecedor): {brl(split['total'])} em {len(split['suppliers'])} fornecedor(es).")
        if best_single and split["total"] < best_single["total"]:
            a.suggest(f"A divisão economiza cerca de {brl(best_single['total'] - split['total'])}, se os prazos e a qualidade forem adequados.")
    if cmp["missing_quotes"]:
        a.warn("Sem cotação válida para: " + ", ".join(m["product"] for m in cmp["missing_quotes"][:8]) + ".")
    a.table = {"columns": [{"key": "s", "label": "Fornecedor"}, {"key": "c", "label": "Itens cobertos"}, {"key": "t", "label": "Total"},
                           {"key": "m", "label": "Pedido mínimo"}],
               "rows": [{"s": r["supplier_name"], "c": f"{r['covers']}/{r['of']}", "t": brl(r["total"]),
                         "m": "Atingido" if r["meets_min_order"] else f"Não atingido ({brl(r['min_order_value'])})"} for r in cmp["single_supplier"][:8]]}
    a.warn("Confira a data das cotações: valores antigos podem não refletir o preço atual.")
    a.link("Abrir comparador", "/compras/comparador")
    return a


def h_margin(unit, question):
    from apps.menu.models import MenuItem

    a = Answer("margin", "Margem dos pratos")
    today = today_for(unit)
    since = today - timedelta(days=30)
    losers = []
    for mi in MenuItem.objects.filter(organization=unit.organization, status="active").prefetch_related("cost_snapshots"):
        old = next((s for s in mi.cost_snapshots.all() if s.created_at.date() <= since), None)
        if old is None:
            old = mi.cost_snapshots.all().order_by("created_at").first()
        if old is None or not mi.price:
            continue
        old_margin = old.price - old.cost_per_portion
        new_margin = mi.price - mi.theoretical_cost
        if new_margin < old_margin - Decimal("0.01"):
            losers.append((mi, old_margin, new_margin))
    losers.sort(key=lambda r: r[2] - r[1])
    items = metrics.item_sales([unit], since, today)
    if losers:
        a.fact(f"{len(losers)} item(ns) perderam margem de contribuição nos últimos 30 dias, por aumento de custo dos ingredientes ou mudança de preço.")
        a.table = {"columns": [{"key": "i", "label": "Item"}, {"key": "o", "label": "Margem antes"}, {"key": "n", "label": "Margem agora"},
                               {"key": "p", "label": "Margem %"}],
                   "rows": [{"i": mi.name, "o": brl(o), "n": brl(n), "p": f"{(n / mi.price * 100).quantize(Decimal('0.1'))}%"} for mi, o, n in losers[:10]]}
        a.suggest("Revise as fichas técnicas e os preços desses itens; verifique também cotações mais baratas para os ingredientes que subiram.")
    else:
        a.fact("Nenhum item perdeu margem teórica nos últimos 30 dias.")
    if items:
        best = max(items, key=lambda r: r["contribution_margin"])
        a.fact(f"Maior margem de contribuição total no período: {best['item']} ({brl(best['contribution_margin'])}).")
    a.link("Ver relatório de margens", "/relatorios?r=menu_costs")
    return a


def h_stock_value(unit, question):
    from django.db.models import Max

    from apps.inventory.models import StockMovement

    a = Answer("stock_value", "Dinheiro parado no estoque")
    value = stock_value(unit)
    a.fact(f"Valor estimado do estoque atual: {brl(value)} (custo dos lotes e custo de reposição dos saldos sem lote).")
    today = today_for(unit)
    since = today - timedelta(days=30)
    last = dict(StockMovement.objects.filter(unit=unit, type__in=("sale", "production")).values("product_id").annotate(m=Max("occurred_at")).values_list("product_id", "m"))
    stagnant = []
    for p in annotate_stock(Product.objects.filter(organization=unit.organization, status="active").select_related("unit"), unit):
        if p.quantity > 0 and (last.get(p.pk) is None or last[p.pk].date() < since):
            stagnant.append((p, (p.quantity * p.cost_price).quantize(C2)))
    stagnant.sort(key=lambda x: -x[1])
    st_value = sum((v for _, v in stagnant), ZERO)
    if stagnant:
        a.fact(f"{len(stagnant)} produto(s) sem consumo há 30 dias somam {brl(st_value)} parados.")
        a.table = {"columns": [{"key": "p", "label": "Produto"}, {"key": "q", "label": "Saldo"}, {"key": "v", "label": "Valor"}],
                   "rows": [{"p": p.name, "q": qty(p.quantity, p.unit.code), "v": brl(v)} for p, v in stagnant[:10]]}
        a.suggest("Evite novas compras desses itens até o saldo girar e avalie usá-los em preparos ou promoções, quando adequado.")
    exp = Lot.objects.filter(unit=unit, status="active", quantity_remaining__gt=0, expires_at__gte=today, expires_at__lte=today + timedelta(days=7))
    ev = sum((l.quantity_remaining * l.unit_cost for l in exp), ZERO)
    if ev:
        a.fact(f"{brl(ev)} estão em lotes que vencem nos próximos 7 dias.")
    a.link("Relatório de produtos parados", "/relatorios?r=stagnant")
    return a


def h_running_out(unit, question):
    a = Answer("running_out", "Produtos perto de acabar")
    today = today_for(unit)
    rates = consumption_rates(unit, today=today)
    rows = []
    for p in annotate_stock(Product.objects.filter(organization=unit.organization, status="active").select_related("unit", "main_supplier"), unit):
        avail = p.quantity - p.expired_quantity
        rate = rates.get(p.pk, {}).get("rate", ZERO)
        days = (avail / rate) if rate > 0 else None
        below = p.min_stock and avail < p.min_stock
        if below or (days is not None and days < 3):
            rows.append((p, avail, rate, days, below))
    rows.sort(key=lambda r: (r[3] if r[3] is not None else 999))
    if not rows:
        a.fact("Nenhum produto abaixo do mínimo ou com cobertura inferior a 3 dias.")
        return a
    a.fact(f"{sum(1 for r in rows if r[4])} produto(s) abaixo do estoque mínimo.")
    a.estimate("Dias de cobertura calculados pelo consumo médio por dia de funcionamento nas últimas 4 semanas.")
    a.table = {"columns": [{"key": "p", "label": "Produto"}, {"key": "a", "label": "Disponível"}, {"key": "m", "label": "Mínimo"},
                           {"key": "d", "label": "Cobertura"}],
               "rows": [{"p": p.name, "a": qty(max(av, ZERO), p.unit.code), "m": qty(p.min_stock, p.unit.code),
                         "d": f"{d.quantize(Decimal('0.1'))} dia(s)" if d is not None else "sem histórico"} for p, av, r, d, b in rows[:15]]}
    a.suggest("Gere a lista de compras para ver quantidades e fornecedores sugeridos.")
    a.link("Gerar lista de compras", "/compras/lista")
    return a


def h_expiring(unit, question):
    a = Answer("expiring", "Validades")
    today = today_for(unit)
    lots = list(Lot.objects.filter(unit=unit, status="active", quantity_remaining__gt=0, expires_at__isnull=False,
                                   expires_at__lte=today + timedelta(days=7)).select_related("product__unit").order_by("expires_at"))
    expired = [l for l in lots if l.expires_at < today]
    soon = [l for l in lots if l.expires_at >= today]
    if expired:
        a.warn(f"{len(expired)} lote(s) vencido(s) no estoque: isole e registre o descarte. Não utilize nem venda.")
    a.fact(f"{len(soon)} lote(s) vencem nos próximos 7 dias, somando {brl(sum((l.quantity_remaining * l.unit_cost for l in soon), ZERO))}.")
    if soon:
        a.table = {"columns": [{"key": "p", "label": "Produto"}, {"key": "q", "label": "Quantidade"}, {"key": "v", "label": "Validade"}],
                   "rows": [{"p": l.product.name, "q": qty(l.quantity_remaining, l.product.unit.code), "v": l.expires_at.strftime("%d/%m")} for l in soon[:12]]}
        a.suggest("Priorize o consumo seguro desses lotes (FEFO), conferindo as condições de conservação.")
    a.link("Ver validades", "/estoque/validades")
    return a


def h_buy_less(unit, question):
    a = Answer("buy_less", "Itens para comprar em menor quantidade")
    today = today_for(unit)
    s90, e = period_bounds(unit, today - timedelta(days=90), today)
    waste = {r["product_id"]: r["v"] for r in WasteRecord.objects.filter(unit=unit, occurred_at__gte=s90, occurred_at__lt=e, reason__in=("expired", "spoiled")).values("product_id").annotate(v=Sum("total_cost"))}
    rates = consumption_rates(unit, today=today)
    rows = []
    for p in annotate_stock(Product.objects.filter(organization=unit.organization, status="active").select_related("unit"), unit):
        rate = rates.get(p.pk, {}).get("rate", ZERO)
        cover = (p.quantity / rate) if rate > 0 else None
        reasons = []
        if waste.get(p.pk):
            reasons.append(f"perdeu {brl(waste[p.pk])} por vencimento/deterioração em 90 dias")
        if cover is not None and p.shelf_life_days and cover > p.shelf_life_days:
            reasons.append(f"estoque cobre {cover.quantize(Decimal('1'))} dias, acima da validade típica de {p.shelf_life_days} dias")
        elif cover is not None and cover > 30:
            reasons.append(f"estoque cobre {cover.quantize(Decimal('1'))} dias de consumo")
        if reasons:
            rows.append((p, reasons, waste.get(p.pk, ZERO)))
    rows.sort(key=lambda r: -r[2])
    if not rows:
        a.fact("Nenhum item com sinais de compra excessiva (perdas por vencimento ou cobertura muito longa).")
        return a
    a.fact(f"{len(rows)} item(ns) com sinais de compra acima do necessário.")
    a.table = {"columns": [{"key": "p", "label": "Produto"}, {"key": "r", "label": "Motivo"}],
               "rows": [{"p": p.name, "r": "; ".join(r)} for p, r, _ in rows[:12]]}
    a.suggest("Reduza o lote de compra desses itens e aumente a frequência de pedidos, mesmo que o preço unitário seja um pouco maior.")
    return a


def h_weekly(unit, question):
    from apps.finance.services import sales_totals

    a = Answer("weekly_changes", "Principais mudanças da semana")
    today = today_for(unit)
    cur_s, cur_e = period_bounds(unit, today - timedelta(days=6), today)
    prev_s, prev_e = period_bounds(unit, today - timedelta(days=13), today - timedelta(days=7))
    cur, prev = sales_totals([unit], cur_s, cur_e), sales_totals([unit], prev_s, prev_e)
    ch = metrics.pct_change(cur["net"], prev["net"])
    a.fact(f"Receita líquida dos últimos 7 dias: {brl(cur['net'])}" + (f" ({'+' if ch >= 0 else ''}{ch}% vs. 7 dias anteriores)." if ch is not None else "."))
    a.fact(f"Vendas: {cur['sales_count']} (antes: {prev['sales_count']}). CMV: {brl(cur['cogs'])} (antes: {brl(prev['cogs'])}).")
    w_cur = WasteRecord.objects.filter(unit=unit, occurred_at__gte=cur_s, occurred_at__lt=cur_e).aggregate(v=Sum("total_cost"))["v"] or ZERO
    w_prev = WasteRecord.objects.filter(unit=unit, occurred_at__gte=prev_s, occurred_at__lt=prev_e).aggregate(v=Sum("total_cost"))["v"] or ZERO
    a.fact(f"Desperdício: {brl(w_cur)} (antes: {brl(w_prev)}).")
    increases = ProductCostHistory.objects.filter(product__organization=unit.organization, created_at__gte=cur_s, previous_cost__gt=0).select_related("product")
    ups = [(h.product.name, (h.cost - h.previous_cost) / h.previous_cost * 100) for h in increases if h.cost > h.previous_cost]
    if ups:
        a.fact("Aumentos de custo: " + ", ".join(f"{n} (+{v.quantize(Decimal('0.1'))}%)" for n, v in ups[:5]) + ".")
    items_cur = {r["item"]: r["quantity"] for r in metrics.item_sales([unit], today - timedelta(days=6), today)}
    items_prev = {r["item"]: r["quantity"] for r in metrics.item_sales([unit], today - timedelta(days=13), today - timedelta(days=7))}
    moves = sorted(((k, items_cur.get(k, 0) - items_prev.get(k, 0)) for k in set(items_cur) | set(items_prev)), key=lambda x: -abs(x[1]))
    if moves:
        a.fact("Maiores variações de vendas: " + ", ".join(f"{k} ({'+' if v >= 0 else ''}{Decimal(v).normalize()})" for k, v in moves[:4]) + ".")
    if ch is not None and ch < -10:
        a.suggest("A receita caiu mais de 10%: verifique dias sem registro de vendas, cardápio indisponível ou mudanças de movimento.")
    return a


def h_sales(unit, question):
    from apps.finance.services import sales_totals

    a = Answer("sales", "Vendas")
    today = today_for(unit)
    s, e = period_bounds(unit, today, today)
    t = sales_totals([unit], s, e)
    ms, me = period_bounds(unit, today.replace(day=1), today)
    m = sales_totals([unit], ms, me)
    a.fact(f"Hoje: {t['sales_count']} venda(s), receita líquida de {brl(t['net'])}.")
    a.fact(f"No mês: {m['sales_count']} venda(s), receita líquida de {brl(m['net'])}, CMV de {brl(m['cogs'])}.")
    a.warn("Faturamento não é lucro: despesas fixas, folha e impostos não estão descontados.")
    a.link("Ver vendas", "/vendas")
    return a


HANDLERS = {
    "help": h_help, "what_to_buy": h_what_to_buy, "waste": h_waste, "expired_loss": h_expired_loss,
    "cost_increase": h_cost_increase, "best_supplier": h_best_supplier, "margin": h_margin, "stock_value": h_stock_value,
    "running_out": h_running_out, "expiring": h_expiring, "buy_less": h_buy_less, "weekly_changes": h_weekly,
    "sales": h_sales,
}

REQUIRED_PERMS = {
    "what_to_buy": "purchases.view", "best_supplier": "suppliers.view", "margin": "costs.view",
    "stock_value": "stock.view", "running_out": "stock.view", "expiring": "stock.view", "waste": "stock.view",
    "expired_loss": "stock.view", "cost_increase": "costs.view", "buy_less": "purchases.view",
    "weekly_changes": "reports.view", "sales": "sales.view",
}
