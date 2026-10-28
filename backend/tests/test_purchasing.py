from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.exceptions import BusinessError
from apps.finance.models import FinancialEntry
from apps.inventory import services as stock
from apps.inventory.models import Lot
from apps.purchasing import services
from apps.purchasing.models import PurchaseIssue, Quotation, Supplier

D = Decimal


def quote(tenant, supplier, product, price, unit=None, **kw):
    return Quotation.objects.create(organization=tenant["org"], supplier=supplier, product=product, price=D(price),
                                    purchase_unit=unit or product.unit, quoted_at=kw.pop("quoted_at", timezone.localdate()), **kw)


def test_comparator_picks_lowest_total_not_lowest_price(tenant, product_factory):
    tomato = product_factory("Tomate", packaging=("cx", "20", "kg"))
    a = Supplier.objects.create(organization=tenant["org"], name="Barato com frete", delivery_fee=D("40"))
    b = Supplier.objects.create(organization=tenant["org"], name="Caixa fechada", delivery_fee=D("0"))
    c = Supplier.objects.create(organization=tenant["org"], name="Equilibrado", delivery_fee=D("5"))
    quote(tenant, a, tomato, "5.00")                                   # 10 kg × 5 + 40 = 90
    quote(tenant, b, tomato, "90.00", unit=tenant["uom"]["cx"])        # 1 cx (20 kg) = 90 → 4,50/kg, mas compra 20 kg
    quote(tenant, c, tomato, "6.00", discount_percent=D("5"))          # 60 − 3 + 5 = 62
    res = services.compare_product(tenant["org"], tomato, D("10"))
    assert res["best"]["supplier_name"] == "Equilibrado"
    assert res["best"]["total"] == D("62.00")
    by_name = {q["supplier_name"]: q for q in res["quotes"]}
    assert by_name["Caixa fechada"]["units_to_buy"] == D("1") and by_name["Caixa fechada"]["surplus"] == D("10.0000")
    assert by_name["Barato com frete"]["total"] == D("90.00")
    assert res["note"]  # explica por que o menor preço não é o melhor custo total


def test_comparator_flags_stale_expired_and_unavailable(tenant, product_factory, supplier):
    p = product_factory("Limão")
    today = timezone.localdate()
    quote(tenant, supplier, p, "4.00", quoted_at=today - timedelta(days=30), valid_until=today - timedelta(days=1))
    s2 = Supplier.objects.create(organization=tenant["org"], name="Sem estoque")
    quote(tenant, s2, p, "3.00", available_quantity=D("2"))
    res = services.compare_product(tenant["org"], p, D("10"))
    assert res["best"] is None
    q1 = next(q for q in res["quotes"] if q["supplier_id"] == supplier.pk)
    assert q1["stale"] and not q1["viable"]


def test_compare_list_counts_freight_once(tenant, product_factory):
    p1, p2 = product_factory("A"), product_factory("B")
    s1 = Supplier.objects.create(organization=tenant["org"], name="S1", delivery_fee=D("30"))
    s2 = Supplier.objects.create(organization=tenant["org"], name="S2", delivery_fee=D("30"))
    quote(tenant, s1, p1, "10.00")
    quote(tenant, s1, p2, "10.50")
    quote(tenant, s2, p1, "10.20")
    quote(tenant, s2, p2, "10.00")
    res = services.compare_list(tenant["org"], [(p1, D("1")), (p2, D("1"))])
    # Dividir economizaria R$0,70 em produtos mas pagaria frete duas vezes: consolida num fornecedor
    assert len(res["best_split"]["suppliers"]) == 1
    assert res["best_split"]["suppliers"][0]["supplier_name"] == "S2"
    assert res["best_split"]["total"] == D("50.20")  # 10,20 + 10,00 + 30 de frete


def _po(tenant, supplier, product, qty="10", price="5.00", unit=None):
    return services.create_purchase_order(tenant["org"], tenant["unit"], supplier, [
        {"product": product, "purchase_unit": unit or product.unit, "quantity": D(qty), "unit_price": D(price)}],
        tenant["users"]["manager"])


def test_approval_threshold(tenant, product_factory, supplier):
    p = product_factory()
    small = _po(tenant, supplier, p, "10", "5.00")
    assert services.submit_purchase_order(small, tenant["users"]["manager"], can_approve=False).status == "approved"
    big = _po(tenant, supplier, p, "200", "5.00")
    big = services.submit_purchase_order(big, tenant["users"]["manager"], can_approve=False)
    assert big.status == "pending_approval"
    with pytest.raises(BusinessError):  # quem criou não aprova acima do limite (exceto proprietário)
        services.approve_purchase_order(big, tenant["users"]["manager"])
    assert services.approve_purchase_order(big, tenant["users"]["owner"]).status == "approved"


def test_partial_and_complete_receipt(tenant, product_factory, supplier):
    p = product_factory("Ovos", unit="un", cost="0.50", packaging=("bd", "30", "un"))
    po = _po(tenant, supplier, p, "4", "18.00", unit=tenant["uom"]["bd"])
    services.submit_purchase_order(po, tenant["users"]["owner"], True)
    services.send_purchase_order(po, tenant["users"]["owner"])
    item = po.items.first()
    exp = timezone.localdate() + timedelta(days=20)
    with pytest.raises(BusinessError):  # perecível exige validade
        services.receive_purchase_order(po, tenant["users"]["stock"], [{"order_item": item, "quantity": D("1")}])
    r1, _ = services.receive_purchase_order(po, tenant["users"]["stock"], [
        {"order_item": item, "quantity": D("1"), "expires_at": exp, "lot_code": "A"}], document_number="NF1")
    po.refresh_from_db()
    assert po.status == "partially_received"
    assert stock.physical_quantity(tenant["unit"], p) == D("30")
    p.refresh_from_db()
    assert p.cost_price == D("0.6000")  # 18 / 30
    r2, _ = services.receive_purchase_order(po, tenant["users"]["stock"], [
        {"order_item": item, "quantity": D("3"), "unit_price": D("19.50"), "expires_at": exp, "lot_code": "B"}],
        document_number="NF2")
    po.refresh_from_db()
    assert po.status == "received"
    assert stock.physical_quantity(tenant["unit"], p) == D("120")
    assert Lot.objects.filter(product=p).count() == 2
    assert PurchaseIssue.objects.filter(order=po, kind="price").count() == 1
    entries = FinancialEntry.objects.filter(purchase_order=po)
    assert entries.count() == 2
    assert sum(e.amount for e in entries) == D("18.00") + D("10.00") + D("58.50")  # inclui frete no 1º recebimento


def test_receipt_idempotency_and_close_short(tenant, product_factory, supplier):
    p = product_factory(perishable=False)
    po = _po(tenant, supplier, p, "10")
    services.submit_purchase_order(po, tenant["users"]["owner"], True)
    item = po.items.first()
    r1, c1 = services.receive_purchase_order(po, None, [{"order_item": item, "quantity": D("6")}], idempotency_key="k1",
                                             close_remaining=True)
    r2, c2 = services.receive_purchase_order(po, None, [{"order_item": item, "quantity": D("6")}], idempotency_key="k1")
    assert c1 and not c2 and r1.pk == r2.pk
    po.refresh_from_db()
    assert po.status == "received"
    assert stock.physical_quantity(tenant["unit"], p) == D("6")
    assert PurchaseIssue.objects.filter(order=po, kind="quantity").exists()


def test_shopping_list_considers_pending_purchases(tenant, product_factory, supplier, stock_in):
    p = product_factory("Arroz", min_stock="5", ideal="20", perishable=False, shelf=None)
    stock_in(p, "2")
    quote(tenant, supplier, p, "5.00")
    sugg, _, _ = services.compute_suggestions(tenant["unit"])
    s = next(x for x in sugg if x["product"].pk == p.pk)
    assert s["suggested_quantity"] == D("18.0000") and s["confidence"] == "limited"
    assert "estimativa limitada" in s["justification"]
    po = _po(tenant, supplier, p, "18")
    services.submit_purchase_order(po, tenant["users"]["owner"], True)
    sugg, _, _ = services.compute_suggestions(tenant["unit"])
    assert not any(x["product"].pk == p.pk for x in sugg)
    assert stock.physical_quantity(tenant["unit"], p) == D("2")  # pendentes não entram no estoque físico


def test_shopping_list_with_consumption_history(tenant, product_factory, supplier, stock_in):
    from django.db import transaction

    p = product_factory("Cerveja", unit="un", min_stock="24", ideal="72", perishable=False, shelf=None)
    stock_in(p, "200", "4.00", received=timezone.localdate() - timedelta(days=30))
    quote(tenant, supplier, p, "4.00")
    now = timezone.now()
    for d in range(1, 29):
        with transaction.atomic():
            op = stock.begin_operation(tenant["org"], tenant["unit"], f"h{d}", "test")
            stock.remove_stock(op, tenant["unit"], p, D("6"), type_="sale", occurred_at=now - timedelta(days=d))
    # 200 − 168 = 32 un; ~7 un/dia de funcionamento → abaixo do mínimo em ~1 dia
    sugg, _, today = services.compute_suggestions(tenant["unit"])
    s = next(x for x in sugg if x["product"].pk == p.pk)
    assert s["confidence"] == "good"
    assert s["reorder_date"] <= today + timedelta(days=2)
    assert "Recomendamos comprar" in s["justification"]
    assert s["suggested_quantity"] > 0


def test_shopping_list_api_to_purchase_orders(api, tenant, product_factory, supplier, stock_in):
    p = product_factory("Feijão", min_stock="5", ideal="10", perishable=False)
    quote(tenant, supplier, p, "8.00")
    c = api("manager")
    sl = c.post("/api/shopping-lists/generate/", {}, format="json").json()
    item = next(i for i in sl["items"] if i["product"] == p.pk)
    r = c.patch(f"/api/shopping-lists/{sl['id']}/items/{item['id']}/", {"quantity": "12"}, format="json")
    assert r.status_code == 200 and D(r.json()["estimated_cost"]) == D("106.00")  # 12 × 8 + frete 10
    r = c.post(f"/api/shopping-lists/{sl['id']}/create-orders/", {}, format="json")
    assert r.status_code == 201 and len(r.json()["orders"]) == 1
    assert c.post(f"/api/shopping-lists/{sl['id']}/create-orders/", {}, format="json").status_code == 400
