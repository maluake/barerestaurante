from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import transaction

from apps.core.exceptions import BusinessError
from apps.inventory import services
from apps.inventory.models import Lot, StockMovement, WasteRecord
from apps.inventory.units import IncompatibleUnits, convert

D = Decimal


def test_conversion_same_dimension(uom):
    assert convert(250, uom["g"], uom["kg"]) == D("0.25")
    assert convert(D("1.5"), uom["L"], uom["ml"]) == D("1500")
    assert convert(2, uom["dz"], uom["un"]) == D("24")


def test_conversion_incompatible_units_raise(uom):
    with pytest.raises(IncompatibleUnits):
        convert(1, uom["kg"], uom["L"])
    # Caixa não tem quantidade fixa sem cadastro de embalagem do produto
    with pytest.raises(IncompatibleUnits):
        convert(1, uom["cx"], uom["un"])


def test_conversion_with_product_packaging(product_factory, uom):
    beer = product_factory("Cerveja", unit="un", packaging=("cx", "24", "un"))
    oil = product_factory("Óleo", unit="L", packaging=("cx", "20", "L"))
    assert convert(2, uom["cx"], uom["un"], beer) == D("48")
    assert convert(48, uom["un"], uom["cx"], beer) == D("2")
    assert convert(1, uom["cx"], uom["ml"], oil) == D("20000")
    with pytest.raises(IncompatibleUnits):
        convert(1, uom["pct"], uom["un"], beer)


def _remove(tenant, product, qty, **kw):
    with transaction.atomic():
        op = services.begin_operation(tenant["org"], tenant["unit"], f"t:{qty}:{product.pk}:{kw.get('key', '')}", "test")
        return services.remove_stock(op, tenant["unit"], product, D(qty), type_="sale", **{k: v for k, v in kw.items() if k != "key"})


def test_fefo_consumes_earliest_expiry_first(tenant, product_factory, stock_in):
    p = product_factory()
    today = services.today_for(tenant["unit"])
    late = stock_in(p, "5", "4.00", expires=today + timedelta(days=10), code="TARDE")
    early = stock_in(p, "3", "6.00", expires=today + timedelta(days=2), code="CEDO")
    movements = _remove(tenant, p, "4")
    early.refresh_from_db()
    late.refresh_from_db()
    assert early.quantity_remaining == 0 and early.status == "depleted"
    assert late.quantity_remaining == D("4")
    assert [m.lot_id for m in movements] == [early.pk, late.pk]
    # Custo real = 3 × 6 + 1 × 4
    assert sum(m.total_cost for m in movements) == D("22.00")
    assert services.physical_quantity(tenant["unit"], p) == D("4")


def test_expired_lots_are_not_used_and_are_isolated(tenant, product_factory, stock_in):
    p = product_factory()
    today = services.today_for(tenant["unit"])
    expired = stock_in(p, "2", expires=today - timedelta(days=1))
    good = stock_in(p, "3", expires=today + timedelta(days=5))
    assert services.available_quantity(tenant["unit"], p) == D("3")
    _remove(tenant, p, "1")
    expired.refresh_from_db()
    good.refresh_from_db()
    assert expired.quantity_remaining == D("2")
    assert good.quantity_remaining == D("2")
    with pytest.raises(BusinessError):
        with transaction.atomic():
            op = services.begin_operation(tenant["org"], tenant["unit"], "x", "test")
            services.remove_stock(op, tenant["unit"], p, D("1"), type_="loss", lot=expired)


def test_insufficient_stock_blocks_manual_exit(tenant, product_factory, stock_in):
    p = product_factory()
    stock_in(p, "1")
    with pytest.raises(BusinessError) as exc:
        services.record_waste(tenant["unit"], p, D("5"), "spoiled")
    assert exc.value.code == "insufficient_stock"
    assert services.physical_quantity(tenant["unit"], p) == D("1")


def test_operation_key_is_idempotent(tenant, product_factory, stock_in):
    p = product_factory()
    stock_in(p, "10")
    _remove(tenant, p, "2", key="same")
    with pytest.raises(services.AlreadyProcessed):
        with transaction.atomic():
            services.begin_operation(tenant["org"], tenant["unit"], f"t:2:{p.pk}:same", "test")
    assert services.physical_quantity(tenant["unit"], p) == D("8")


def test_reversal_restores_lots_and_cannot_repeat(tenant, product_factory, stock_in):
    p = product_factory()
    lot = stock_in(p, "5")
    _remove(tenant, p, "3", key="r")
    from apps.inventory.models import StockOperation

    op = StockOperation.objects.get(key=f"t:3:{p.pk}:r")
    services.reverse_operation(op, reason="teste")
    lot.refresh_from_db()
    assert lot.quantity_remaining == D("5") and lot.status == "active"
    assert services.physical_quantity(tenant["unit"], p) == D("5")
    assert StockMovement.objects.filter(type="reversal", product=p).count() == 1
    with pytest.raises(services.AlreadyProcessed):
        services.reverse_operation(op)


def test_movements_are_immutable(tenant, product_factory, stock_in):
    p = product_factory()
    stock_in(p, "1")
    mv = StockMovement.objects.filter(product=p).first()
    mv.quantity = D("100")
    with pytest.raises(RuntimeError):
        mv.save()
    with pytest.raises(RuntimeError):
        mv.delete()


def test_waste_record_uses_lot_cost(tenant, product_factory, stock_in):
    p = product_factory()
    lot = stock_in(p, "4", "7.50")
    rec = services.record_waste(tenant["unit"], p, D("2"), "spoiled", lot=lot, notes="caiu")
    assert rec.total_cost == D("15.00")
    assert WasteRecord.objects.count() == 1
    lot.refresh_from_db()
    assert lot.quantity_remaining == D("2")


def test_discard_expired_lot(tenant, product_factory, stock_in):
    p = product_factory()
    lot = stock_in(p, "3", expires=services.today_for(tenant["unit"]) - timedelta(days=1))
    rec = services.discard_lot(lot)
    lot.refresh_from_db()
    assert rec.reason == "expired"
    assert lot.status == "discarded"
    assert services.physical_quantity(tenant["unit"], p) == 0


def test_transfer_moves_quantity_without_creating_or_losing(tenant, product_factory, stock_in):
    from apps.core.models import Unit

    unit2 = Unit.objects.create(organization=tenant["org"], name="Filial")
    p = product_factory()
    exp = services.today_for(tenant["unit"]) + timedelta(days=4)
    stock_in(p, "6", "5.00", expires=exp)
    t = services.transfer_stock(tenant["org"], tenant["unit"], unit2, [(p, D("4"))])
    assert services.physical_quantity(tenant["unit"], p) == D("2")
    assert services.physical_quantity(unit2, p) == D("4")
    dest_lot = Lot.objects.get(unit=unit2, product=p)
    assert dest_lot.expires_at == exp and dest_lot.unit_cost == D("5.00")
    outs = StockMovement.objects.filter(ref_type="transfer", ref_id=str(t.pk), type="transfer_out")
    ins = StockMovement.objects.filter(ref_type="transfer", ref_id=str(t.pk), type="transfer_in")
    assert sum(m.quantity for m in outs) == -sum(m.quantity for m in ins)


def test_transfer_does_not_move_expired_stock(tenant, product_factory, stock_in):
    from apps.core.models import Unit

    unit2 = Unit.objects.create(organization=tenant["org"], name="Filial")
    p = product_factory()
    stock_in(p, "5", expires=services.today_for(tenant["unit"]) - timedelta(days=1))
    with pytest.raises(BusinessError):
        services.transfer_stock(tenant["org"], tenant["unit"], unit2, [(p, D("2"))])


def test_negative_balance_is_settled_by_next_lot(tenant, product_factory, stock_in):
    p = product_factory()
    _remove(tenant, p, "2", allow_negative=True)
    assert services.physical_quantity(tenant["unit"], p) == D("-2")
    lot = stock_in(p, "5")
    lot.refresh_from_db()
    assert services.physical_quantity(tenant["unit"], p) == D("3")
    assert lot.quantity_remaining == D("3")  # a entrega cobre o consumo já ocorrido


def test_inventory_count_adjusts_only_difference(tenant, product_factory, stock_in, api):
    p = product_factory()
    stock_in(p, "10", "2.00")
    c = api("stock")
    inv = c.post("/api/inventory-counts/", {"products": [p.pk], "description": "teste"}, format="json").json()
    item = inv["items"][0]
    assert D(item["system_quantity"]) == D("10")
    res = c.post(f"/api/inventory-counts/{inv['id']}/count/", {"items": [{"id": item["id"], "counted_quantity": "8,5"}]}, format="json").json()
    assert D(res["items"][0]["difference"]) == D("-1.5")
    assert D(res["items"][0]["value_difference"]) == D("-7.50")  # custo de reposição (5,00) × 1,5
    # Sem motivo não fecha
    assert c.post(f"/api/inventory-counts/{inv['id']}/close/", {}, format="json").status_code == 400
    r = c.post(f"/api/inventory-counts/{inv['id']}/close/", {"reason": "contagem mensal"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert services.physical_quantity(tenant["unit"], p) == D("8.5")
    assert StockMovement.objects.filter(product=p, type="adjustment").count() == 1
    # Finalizar de novo não ajusta outra vez
    assert c.post(f"/api/inventory-counts/{inv['id']}/close/", {"reason": "x"}, format="json").status_code == 400
    assert services.physical_quantity(tenant["unit"], p) == D("8.5")


@pytest.mark.django_db(transaction=True)
def test_concurrent_consumption_never_oversells_a_lot(uom):
    """Duas saídas simultâneas do mesmo produto não podem consumir o mesmo saldo do lote."""
    import threading

    from django.contrib.auth import get_user_model
    from django.db import connection

    from apps.core.setup import create_organization
    from apps.inventory.models import Product

    owner = get_user_model().objects.create_user("concorrente", password="x")
    org, unit = create_organization(name="Concorrência", owner=owner)
    p = Product.objects.create(organization=org, name="Limão", sku="LIM", unit=uom["kg"], cost_price=D("1"))
    with transaction.atomic():
        op = services.begin_operation(org, unit, "in", "manual_entry")
        services.add_stock(op, unit, p, D("5"), D("1"))
    errors, done = [], []

    def worker(i):
        try:
            services.record_waste(unit, p, D("3"), "spoiled", key=f"w{i}")
            done.append(i)
        except BusinessError as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(done) == 1 and len(errors) == 1
    assert services.physical_quantity(unit, p) == D("2")
    assert Lot.objects.get(product=p).quantity_remaining == D("2")
