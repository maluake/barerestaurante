from datetime import timedelta
from decimal import Decimal

import pytest

from apps.core.exceptions import BusinessError
from apps.inventory import services as stock
from apps.inventory.models import StockMovement, WasteRecord
from apps.menu.models import MenuItem, RecipeIngredient
from apps.menu.services import compute_cost, recalculate, requirements_per_portion
from apps.sales import services
from apps.sales.importer import import_sales_csv
from apps.sales.models import Sale

D = Decimal


@pytest.fixture
def fries(tenant, product_factory, stock_in):
    potato = product_factory("Batata", unit="kg", cost="4.00")
    oil = product_factory("Óleo", unit="L", cost="10.00", perishable=False)
    stock_in(potato, "10", "4.00", expires=stock.today_for(tenant["unit"]) + timedelta(days=10))
    stock_in(oil, "5", "10.00")
    item = MenuItem.objects.create(organization=tenant["org"], name="Batata frita", price=D("30.00"))
    RecipeIngredient.objects.create(menu_item=item, product=potato, quantity=D("250"), unit=tenant["uom"]["g"])
    RecipeIngredient.objects.create(menu_item=item, product=oil, quantity=D("50"), unit=tenant["uom"]["ml"], loss_percent=D("0"))
    recalculate(item)
    return {"item": item, "potato": potato, "oil": oil}


def test_recipe_cost_and_requirements(fries, tenant):
    item = fries["item"]
    data = compute_cost(item)
    # 0,25 kg × 4,00 + 0,05 L × 10,00
    assert data["cost_per_portion"] == D("1.5000")
    assert data["contribution_margin"] == D("28.50")
    req = dict((p.name, q) for p, q in requirements_per_portion(item))
    assert req["Batata"] * 4 == D("1")  # 250 g × 4 porções = 1 kg


def test_preparation_loss_and_yield(tenant, product_factory):
    onion = product_factory("Cebola", cost="5.00")
    item = MenuItem.objects.create(organization=tenant["org"], name="Molho", price=D("20"), yield_portions=D("4"))
    RecipeIngredient.objects.create(menu_item=item, product=onion, quantity=D("900"), unit=tenant["uom"]["g"], loss_percent=D("10"))
    data = compute_cost(item)
    # bruto = 0,9 / 0,9 = 1 kg → R$ 5,00 por receita → 4 porções
    assert data["recipe_total_cost"] == D("5.0000")
    assert data["cost_per_portion"] == D("1.2500")


def test_cost_change_recalculates_recipes(fries):
    from django.db import transaction

    with transaction.atomic():
        stock.update_product_cost(fries["potato"], D("8.00"), source="manual")
    fries["item"].refresh_from_db()
    assert fries["item"].theoretical_cost == D("2.5000")
    assert fries["item"].cost_snapshots.count() >= 2


def test_order_confirmation_consumes_once(tenant, fries):
    order, _ = services.create_order(tenant["org"], tenant["unit"], tenant["users"]["attendant"],
                                     items=[{"menu_item": fries["item"], "quantity": D("4")}], origin="table", table_label="5")
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == D("10")  # recebido: sem baixa
    services.change_order_status(order, "confirmed", tenant["users"]["manager"])
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == D("9")
    services.change_order_status(order, "confirmed", tenant["users"]["manager"])  # repetição: sem efeito
    services.change_order_status(order, "preparing", tenant["users"]["kitchen"])
    services.change_order_status(order, "ready", tenant["users"]["kitchen"])
    services.change_order_status(order, "delivered", tenant["users"]["manager"], payment_method="pix")
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == D("9")
    sale = Sale.objects.get(order=order)
    assert sale.gross_amount == D("120.00") and sale.net_amount == D("120.00")
    assert sale.cogs == D("6.00")  # 1 kg × 4,00 + 0,2 L × 10,00
    assert StockMovement.objects.filter(ref_type="order", ref_id=str(order.pk)).count() == 2


def test_invalid_transition_rejected(tenant, fries):
    order, _ = services.create_order(tenant["org"], tenant["unit"], None, items=[{"menu_item": fries["item"], "quantity": 1}])
    with pytest.raises(BusinessError):
        services.change_order_status(order, "delivered", None)


def test_cancel_before_preparation_returns_ingredients(tenant, fries):
    order, _ = services.create_order(tenant["org"], tenant["unit"], None, items=[{"menu_item": fries["item"], "quantity": 2}])
    services.change_order_status(order, "confirmed", None)
    with pytest.raises(BusinessError):
        services.change_order_status(order, "cancelled", None, note="x", can_cancel_confirmed=False)
    order = services.change_order_status(order, "cancelled", None, note="cliente desistiu", can_cancel_confirmed=True)
    assert order.stock_status == "reversed"
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == D("10")
    assert not WasteRecord.objects.exists()


def test_cancel_during_preparation_registers_waste(tenant, fries):
    order, _ = services.create_order(tenant["org"], tenant["unit"], None, items=[{"menu_item": fries["item"], "quantity": 2}])
    services.change_order_status(order, "confirmed", None)
    services.change_order_status(order, "preparing", None)
    order = services.change_order_status(order, "cancelled", None, note="mesa foi embora", can_cancel_confirmed=True)
    assert order.stock_status == "wasted"
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == D("9.5")
    assert WasteRecord.objects.filter(reason="cancelled_order").count() == 2


def test_direct_sale_idempotent_and_cancellation(tenant, fries):
    items = [{"menu_item": fries["item"], "description": "Batata", "quantity": D("2"), "unit_price": D("30")}]
    sale, created = services.register_sale(tenant["org"], tenant["unit"], None, items=items, external_id="PDV-1", discount=D("5"))
    assert created and sale.net_amount == D("55.00") and sale.discount_amount == D("5.00")
    again, created2 = services.register_sale(tenant["org"], tenant["unit"], None, items=items, external_id="PDV-1")
    assert not created2 and again.pk == sale.pk
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == D("9.5")
    services.cancel_sale(sale, None, "estorno teste", return_to_stock=True)
    sale.refresh_from_db()
    assert sale.status == "cancelled" and sale.stock_status == "reversed"
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == D("10")
    services.cancel_sale(sale, None, "de novo", return_to_stock=True)  # idempotente
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == D("10")


def test_item_without_recipe_is_flagged(tenant):
    item = MenuItem.objects.create(organization=tenant["org"], name="Sobremesa", price=D("15"))
    sale, _ = services.register_sale(tenant["org"], tenant["unit"], None,
                                     items=[{"menu_item": item, "description": "x", "quantity": 1, "unit_price": D("15")}])
    assert sale.stock_status == "partial"
    assert "ficha técnica" in sale.items.first().stock_warning


def test_item_without_stock_control(tenant):
    item = MenuItem.objects.create(organization=tenant["org"], name="Taxa de rolha", price=D("20"), stock_mode="none")
    sale, _ = services.register_sale(tenant["org"], tenant["unit"], None,
                                     items=[{"menu_item": item, "description": "x", "quantity": 1, "unit_price": D("20")}])
    assert sale.stock_status == "not_applicable"


def test_csv_import_is_idempotent_and_maps_codes(tenant, fries):
    fries["item"].pos_code = "B01"
    fries["item"].save()
    csv = ("id_venda;data_hora;canal;forma_pagamento;codigo_produto;descricao;quantidade;preco_unitario;desconto_item;taxa;cancelada\n"
           "V1;2026-10-01 20:00;mesa;pix;B01;Batata;2;30,00;0;;nao\n"
           "V1;2026-10-01 20:00;mesa;pix;X99;Item desconhecido;1;10,00;0;;nao\n"
           "V2;01/10/2026 21:00;app;app;B01;Batata;1;30,00;0;3,60;nao\n"
           "V3;2026-10-01 22:00;balcao;dinheiro;B01;Batata;1;30,00;0;;sim\n"
           "V4;data ruim;balcao;pix;B01;Batata;1;30,00;0;;nao\n")
    batch = import_sales_csv(tenant["org"], tenant["unit"], None, csv.encode(), "vendas.csv")
    assert batch.sales_imported == 3 and batch.rows_failed == 1
    assert "X99" in batch.unmapped_codes
    assert Sale.objects.get(external_id="V2").fee_amount == D("3.60")
    assert Sale.objects.get(external_id="V3").status == "cancelled"
    potato = stock.physical_quantity(tenant["unit"], fries["potato"])
    batch2 = import_sales_csv(tenant["org"], tenant["unit"], None, csv.encode(), "vendas.csv")
    assert batch2.sales_imported == 0 and batch2.sales_duplicated == 3
    assert stock.physical_quantity(tenant["unit"], fries["potato"]) == potato


def test_order_api_permissions(api, fries):
    r = api("attendant").post("/api/orders/", {"origin": "counter", "items": [{"menu_item": fries["item"].pk, "quantity": 1}]}, format="json")
    assert r.status_code == 201
    oid = r.json()["id"]
    assert api("kitchen").post(f"/api/orders/{oid}/status/", {"status": "confirmed"}, format="json").status_code == 403
    assert api("attendant").post(f"/api/orders/{oid}/status/", {"status": "confirmed"}, format="json").status_code == 200
    assert api("kitchen").post(f"/api/orders/{oid}/status/", {"status": "preparing"}, format="json").status_code == 200
    # Atendente não cancela pedido em preparo (exige sales.cancel)
    r = api("attendant").post(f"/api/orders/{oid}/status/", {"status": "cancelled", "note": "x"}, format="json")
    assert r.status_code == 400
    board = api("kitchen").get("/api/orders/board/").json()
    assert board["changed"] and len(board["columns"]["preparing"]) == 1
    again = api("kitchen").get(f"/api/orders/board/?version={board['version']}").json()
    assert again["changed"] is False


def test_order_client_reference_prevents_duplicates(api, fries):
    body = {"origin": "counter", "client_reference": "tablet-1-abc", "items": [{"menu_item": fries["item"].pk, "quantity": 1}]}
    c = api("attendant")
    a = c.post("/api/orders/", body, format="json")
    b = c.post("/api/orders/", body, format="json")
    assert a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"]
