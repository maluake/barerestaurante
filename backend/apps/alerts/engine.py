"""Motor de alertas.

Cada execução avalia as condições atuais da unidade e:
- cria alertas novos (chave de deduplicação evita repetições);
- atualiza os que continuam válidos;
- resolve automaticamente os que deixaram de existir;
- respeita alertas resolvidos manualmente (não reaparecem antes de `snoozed_until`).
"""

import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import Membership
from apps.core.permissions import permissions_for
from apps.inventory.analytics import consumption_rates, net_consumption_by_product, period_bounds
from apps.inventory.models import InventoryCount, Lot, Product, ProductCostHistory, StockBalance, WasteRecord
from apps.inventory.services import today_for

from .models import PRIORITY_ORDER, Alert, AlertRefreshState, Notification, NotificationPreference

logger = logging.getLogger("mise.alerts")
ZERO = Decimal("0")
SNOOZE_HOURS = 24


def fmt_qty(value, unit):
    return f"{Decimal(value).quantize(Decimal('0.01')).normalize():f} {unit}"


def brl(value):
    s = f"{Decimal(value).quantize(Decimal('0.01')):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def collect_conditions(unit):
    org = unit.organization
    today = today_for(unit)
    now = timezone.now()
    out = {}

    def add(key, **kw):
        out[key] = kw

    products = {p.pk: p for p in Product.objects.filter(organization=org, status="active").select_related("unit", "main_supplier")}
    balances = dict(StockBalance.objects.filter(unit=unit).values_list("product_id", "quantity"))
    expired_q = defaultdict(lambda: ZERO)
    for pid, q in Lot.objects.filter(unit=unit, status="active", expires_at__lt=today).values_list("product_id", "quantity_remaining"):
        expired_q[pid] += q
    rates = consumption_rates(unit, today=today)

    for pid, p in products.items():
        physical = balances.get(pid, ZERO)
        available = physical - expired_q[pid]
        if physical < 0:
            add(f"negative_stock:{pid}", type="negative_stock", priority="high",
                title=f"Saldo negativo: {p.name}",
                reason=f"O sistema registra {fmt_qty(physical, p.unit.code)}. Houve vendas sem estoque registrado ou falta lançar uma entrada.",
                action_label="Fazer inventário", action_path="/estoque/inventarios", data={"product_id": pid})
        if p.min_stock and available < p.min_stock:
            add(f"low_stock:{pid}", type="low_stock", priority="high" if available <= 0 else "medium",
                title=f"{p.name} abaixo do mínimo",
                reason=f"Disponível {fmt_qty(max(available, ZERO), p.unit.code)}; mínimo {fmt_qty(p.min_stock, p.unit.code)}.",
                action_label="Gerar lista de compras", action_path="/compras/lista",
                data={"product_id": pid, "available": str(available), "min_stock": str(p.min_stock)})
        else:
            rate = rates.get(pid, {}).get("rate", ZERO)
            if rate > 0 and available > 0:
                lead = p.main_supplier.delivery_days if p.main_supplier else 2
                days_left = available / rate
                if days_left < lead + 1:
                    add(f"stockout_risk:{pid}", type="stockout_risk", priority="high",
                        title=f"{p.name} pode acabar em {days_left.quantize(Decimal('0.1'))} dia(s)",
                        reason=f"Consumo médio de {fmt_qty(rate, p.unit.code)}/dia e prazo de entrega de {lead} dia(s).",
                        action_label="Comparar fornecedores", action_path=f"/compras/comparador?produto={pid}",
                        data={"product_id": pid, "days_left": str(days_left.quantize(Decimal('0.1')))})

    for lot in Lot.objects.filter(unit=unit, status="active", quantity_remaining__gt=0, expires_at__isnull=False,
                                  expires_at__lte=today + timedelta(days=3)).select_related("product__unit", "location"):
        days = (lot.expires_at - today).days
        value = lot.quantity_remaining * lot.unit_cost
        place = f" em {lot.location.name}" if lot.location else ""
        if days < 0:
            add(f"expired:{lot.pk}", type="expired", priority="critical",
                title=f"Lote vencido de {lot.product.name}",
                reason=f"{fmt_qty(lot.quantity_remaining, lot.product.unit.code)}{place} venceram em {lot.expires_at.strftime('%d/%m')}. "
                       f"Isole do estoque e registre o descarte; não utilize.",
                action_label="Registrar descarte", action_path="/estoque/validades",
                data={"lot_id": lot.pk, "value": str(value.quantize(Decimal('0.01')))})
        else:
            add(f"expiring:{lot.pk}", type="expiring", priority="high" if days <= 1 else "medium",
                title=f"{lot.product.name} vence {'hoje' if days == 0 else f'em {days} dia(s)'}",
                reason=f"{fmt_qty(lot.quantity_remaining, lot.product.unit.code)}{place} ({brl(value)}). Priorize o uso seguro (FEFO).",
                action_label="Ver validades", action_path="/estoque/validades", data={"lot_id": lot.pk})

    from apps.sales.models import Order, Sale

    slow = int(org.setting("slow_order_minutes"))
    for o in Order.objects.filter(unit=unit, status__in=("received", "confirmed", "preparing"),
                                  created_at__lt=now - timedelta(minutes=slow)):
        minutes = int((now - o.created_at).total_seconds() // 60)
        if minutes > 12 * 60:
            continue  # pedidos esquecidos de dias anteriores não poluem o painel
        add(f"slow_order:{o.pk}", type="slow_order", priority="high",
            title=f"Pedido #{o.number} aguardando há {minutes} min",
            reason=f"Status: {o.get_status_display()}. Limite configurado: {slow} min.",
            action_label="Abrir painel da cozinha", action_path="/cozinha", data={"order_id": o.pk})

    from apps.purchasing.models import PurchaseOrder, Quotation

    for po in PurchaseOrder.objects.filter(unit=unit, status="pending_approval").select_related("supplier"):
        add(f"po_approval:{po.pk}", type="po_approval", priority="medium",
            title=f"Pedido de compra #{po.number} aguardando aprovação",
            reason=f"{po.supplier} — total {brl(po.total)}.", action_label="Revisar pedido",
            action_path=f"/compras/pedidos/{po.pk}", data={"purchase_order_id": po.pk})
    for po in PurchaseOrder.objects.filter(unit=unit, status__in=("approved", "sent", "partially_received"),
                                           expected_delivery__lt=today).select_related("supplier"):
        add(f"late_delivery:{po.pk}", type="late_delivery", priority="high",
            title=f"Entrega atrasada: pedido #{po.number}",
            reason=f"{po.supplier} — previsto para {po.expected_delivery.strftime('%d/%m')} ({(today - po.expected_delivery).days} dia(s) de atraso).",
            action_label="Ver pedido", action_path=f"/compras/pedidos/{po.pk}", data={"purchase_order_id": po.pk})
    for q in Quotation.objects.filter(organization=org, valid_until__gte=today, valid_until__lte=today + timedelta(days=2)).select_related("product", "supplier"):
        add(f"quote_expiring:{q.pk}", type="quote_expiring", priority="low",
            title=f"Cotação de {q.product.name} vence em {(q.valid_until - today).days} dia(s)",
            reason=f"{q.supplier}: {brl(q.price)} válido até {q.valid_until.strftime('%d/%m')}.",
            action_label="Ver cotações", action_path="/compras/cotacoes", data={"quotation_id": q.pk})

    threshold = Decimal(str(org.setting("cost_increase_alert_percent")))
    for h in ProductCostHistory.objects.filter(product__organization=org, created_at__gte=now - timedelta(days=7),
                                               previous_cost__gt=0).select_related("product__unit"):
        pct = (h.cost - h.previous_cost) / h.previous_cost * 100
        if pct >= threshold:
            add(f"cost_increase:{h.pk}", type="cost_increase", priority="medium",
                title=f"Custo de {h.product.name} subiu {pct.quantize(Decimal('0.1'))}%",
                reason=f"De {brl(h.previous_cost)} para {brl(h.cost)} por {h.product.unit.code}. Fichas técnicas recalculadas.",
                action_label="Ver oportunidades", action_path="/compras/oportunidades", data={"product_id": h.product_id})

    month_start = today.replace(day=1)
    ms, me = period_bounds(unit, month_start, today)
    waste = WasteRecord.objects.filter(unit=unit, occurred_at__gte=ms, occurred_at__lt=me).aggregate(v=Sum("total_cost"))["v"] or ZERO
    from apps.inventory.models import StockMovement

    received = StockMovement.objects.filter(unit=unit, type="receipt", occurred_at__gte=ms, occurred_at__lt=me).aggregate(v=Sum("total_cost"))["v"] or ZERO
    limit = Decimal(str(org.setting("waste_alert_percent")))
    if received > 0 and waste / received * 100 > limit:
        add(f"waste_above:{month_start:%Y-%m}", type="waste_above", priority="medium",
            title=f"Desperdício do mês em {(waste / received * 100).quantize(Decimal('0.1'))}% das compras",
            reason=f"Perdas de {brl(waste)} frente a {brl(received)} recebidos. Limite configurado: {limit}%.",
            action_label="Analisar desperdício", action_path="/estoque/perdas", data={"value": str(waste)})

    week_s, week_e = period_bounds(unit, today - timedelta(days=7), today - timedelta(days=1))
    base_s, base_e = period_bounds(unit, today - timedelta(days=35), today - timedelta(days=8))
    recent = net_consumption_by_product(unit, week_s, week_e)
    base = net_consumption_by_product(unit, base_s, base_e)
    for pid, q in recent.items():
        b = base.get(pid, ZERO) / 4
        if b > 0 and q > b * Decimal("1.5") and pid in products:
            p = products[pid]
            add(f"consumption_spike:{pid}:{today.isocalendar()[1]}", type="consumption_spike", priority="medium",
                title=f"Consumo incomum de {p.name}",
                reason=f"Últimos 7 dias: {fmt_qty(q, p.unit.code)}; média semanal anterior: {fmt_qty(b, p.unit.code)} "
                       f"(+{((q / b - 1) * 100).quantize(Decimal('1'))}%). Verifique vendas, porcionamento e perdas não registradas.",
                action_label="Ver movimentações", action_path=f"/estoque/produtos/{pid}", data={"product_id": pid})

    for inv in InventoryCount.objects.filter(unit=unit, status="closed", closed_at__gte=now - timedelta(days=7)).prefetch_related("items__product"):
        loss = sum((i.value_difference for i in inv.items.all() if i.counted_quantity is not None and i.value_difference < 0), ZERO)
        n = sum(1 for i in inv.items.all() if i.counted_quantity is not None and i.difference)
        if n and abs(loss) >= 50:
            add(f"inventory_divergence:{inv.pk}", type="inventory_divergence", priority="medium",
                title=f"Inventário #{inv.pk} com divergências",
                reason=f"{n} produto(s) com diferença; perda estimada de {brl(abs(loss))}.",
                action_label="Ver inventário", action_path=f"/estoque/inventarios/{inv.pk}", data={"inventory_id": inv.pk})

    from apps.menu.models import MenuItem

    sold_ids = set(Sale.objects.filter(unit=unit, occurred_at__gte=now - timedelta(days=7)).values_list("items__menu_item", flat=True))
    sold_ids |= set(Order.objects.filter(unit=unit, created_at__gte=now - timedelta(days=7)).values_list("items__menu_item", flat=True))
    for item in MenuItem.objects.filter(organization=org, status="active", stock_mode="recipe", ingredients__isnull=True, pk__in=sold_ids):
        add(f"missing_recipe:{item.pk}", type="missing_recipe", priority="medium",
            title=f"{item.name} vendido sem ficha técnica",
            reason="A baixa automática de ingredientes não pode ser feita de forma confiável e o CMV fica incompleto.",
            action_label="Cadastrar ficha técnica", action_path=f"/cardapio/{item.pk}", data={"menu_item_id": item.pk})

    from apps.integrations.models import IntegrationLog

    for log in IntegrationLog.objects.filter(organization=org, status="failure", created_at__gte=now - timedelta(hours=24)):
        add(f"integration_failure:{log.pk}", type="integration_failure", priority="high",
            title="Falha de integração/importação", reason=log.message, action_label="Ver integrações",
            action_path="/configuracoes/integracoes", data={"log_id": log.pk})
    return out


def refresh_alerts(unit, force=False, min_interval_seconds=60):
    now = timezone.now()
    state = AlertRefreshState.objects.filter(unit=unit).first()
    if state and not force and (now - state.refreshed_at).total_seconds() < min_interval_seconds:
        return []
    conditions = collect_conditions(unit)
    created = []
    with transaction.atomic():
        AlertRefreshState.objects.update_or_create(unit=unit, defaults={"refreshed_at": now})
        existing = {a.dedup_key: a for a in Alert.objects.select_for_update().filter(unit=unit, status="open")}
        snoozed = set(Alert.objects.filter(unit=unit, status="resolved", snoozed_until__gt=now).values_list("dedup_key", flat=True))
        for key, c in conditions.items():
            if key in existing:
                a = existing[key]
                changed = a.title != c["title"] or a.reason != c["reason"] or a.priority != c["priority"]
                if changed:
                    for f in ("title", "reason", "priority", "data", "action_label", "action_path"):
                        setattr(a, f, c.get(f, getattr(a, f)))
                a.save()
                continue
            if key in snoozed:
                continue
            a = Alert.objects.create(organization=unit.organization, unit=unit, dedup_key=key, **c)
            created.append(a)
        stale = [a for k, a in existing.items() if k not in conditions]
        for a in stale:
            a.status = "auto_resolved"
            a.resolved_at = now
            a.resolution_note = "Condição deixou de existir."
            a.save(update_fields=["status", "resolved_at", "resolution_note", "last_seen_at"])
    if created:
        notify(unit, created)
    return created


def notify(unit, alerts):
    """Envia notificações conforme preferências. Sem preferência: apenas no sistema."""
    members = Membership.objects.filter(organization=unit.organization, is_active=True).select_related("user")
    for m in members:
        if "alerts.view" not in permissions_for(m) or not m.allowed_units().filter(pk=unit.pk).exists():
            continue
        prefs = {p.alert_type: p for p in NotificationPreference.objects.filter(membership=m)}
        for a in alerts:
            pref = prefs.get(a.type)
            if pref and (not pref.enabled or PRIORITY_ORDER[a.priority] > PRIORITY_ORDER[pref.min_priority]):
                continue
            channels = pref.channels if pref else ["in_app"]
            for ch in channels:
                status, error = "sent", ""
                if ch == "email":
                    if not m.user.email:
                        continue
                    try:
                        send_mail(f"[Mise] {a.title}", f"{a.reason}\n\nAção sugerida: {a.action_label}", None, [m.user.email])
                    except Exception as exc:  # noqa: BLE001
                        status, error = "failed", str(exc)[:255]
                        logger.warning("Falha ao enviar e-mail de alerta: %s", exc)
                Notification.objects.get_or_create(alert=a, user=m.user, channel=ch, defaults={"status": status, "error": error})


def resolve_alert(alert, user, note=""):
    alert.status = "resolved"
    alert.resolved_at = timezone.now()
    alert.resolved_by = user
    alert.resolution_note = note[:255]
    alert.snoozed_until = timezone.now() + timedelta(hours=SNOOZE_HOURS)
    alert.save()
    return alert
