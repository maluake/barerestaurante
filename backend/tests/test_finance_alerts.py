from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.alerts.engine import refresh_alerts, resolve_alert
from apps.alerts.models import Alert
from apps.finance.models import ExpenseCategory, FinancialEntry
from apps.finance.services import financial_summary
from apps.inventory import services as stock
from apps.menu.models import MenuItem
from apps.sales.services import register_sale

D = Decimal


def test_financial_summary_definitions(tenant, product_factory, stock_in):
    p = product_factory("Cerveja", unit="un", cost="5.00", perishable=False)
    stock_in(p, "100", "5.00")
    item = MenuItem.objects.create(organization=tenant["org"], name="Cerveja", price=D("12"), stock_mode="direct",
                                   direct_product=p, direct_quantity=D("1"))
    register_sale(tenant["org"], tenant["unit"], None, channel="app", fee=D("2.40"),
                  items=[{"menu_item": item, "description": "c", "quantity": D("2"), "unit_price": D("12")}], discount=D("4"))
    register_sale(tenant["org"], tenant["unit"], None,
                  items=[{"menu_item": item, "description": "c", "quantity": D("1"), "unit_price": D("12")}])
    cat = ExpenseCategory.objects.get(organization=tenant["org"], name="Aluguel")
    today = timezone.localdate()
    FinancialEntry.objects.create(organization=tenant["org"], unit=tenant["unit"], category=cat, description="Aluguel",
                                  amount=D("10"), competence_date=today, due_date=today)
    s = financial_summary(tenant["org"], [tenant["unit"]], today, today)
    assert s["gross"] == D("36.00")
    assert s["net"] == D("29.60")  # 36 − 4 − 2,40
    assert s["cogs"] == D("15.00")
    assert s["contribution_margin"] == D("14.60")
    assert s["operating_result_estimate"] == D("4.60")
    assert any("folha" in l for l in s["limitations"])


def test_cash_session_expected_amount(api, tenant):
    c = api("owner")
    s = c.post("/api/cash-sessions/open/", {"opening_amount": "100"}, format="json").json()
    assert c.post("/api/cash-sessions/open/", {"opening_amount": "100"}, format="json").status_code == 400
    item = MenuItem.objects.create(organization=tenant["org"], name="Taxa", price=D("50"), stock_mode="none")
    register_sale(tenant["org"], tenant["unit"], None, payment_method="cash",
                  items=[{"menu_item": item, "description": "t", "quantity": 1, "unit_price": D("50")}])
    c.post(f"/api/cash-sessions/{s['id']}/movement/", {"kind": "withdrawal", "amount": "30", "reason": "troco banco"}, format="json")
    closed = c.post(f"/api/cash-sessions/{s['id']}/close/", {"counted_amount": "118"}, format="json").json()
    assert D(closed["expected_amount"]) == D("120.00")
    assert D(closed["difference"]) == D("-2.00")


def test_alerts_dedup_autoresolve_and_snooze(tenant, product_factory, stock_in):
    p = product_factory("Tomate", min_stock="5")
    lot = stock_in(p, "2", expires=stock.today_for(tenant["unit"]) - timedelta(days=1))
    refresh_alerts(tenant["unit"], force=True)
    keys = set(Alert.objects.filter(status="open").values_list("dedup_key", flat=True))
    assert f"low_stock:{p.pk}" in keys and f"expired:{lot.pk}" in keys
    refresh_alerts(tenant["unit"], force=True)
    assert Alert.objects.filter(dedup_key=f"low_stock:{p.pk}").count() == 1  # sem duplicar
    stock.discard_lot(lot)
    refresh_alerts(tenant["unit"], force=True)
    assert Alert.objects.get(dedup_key=f"expired:{lot.pk}").status == "auto_resolved"
    a = Alert.objects.get(dedup_key=f"low_stock:{p.pk}", status="open")
    resolve_alert(a, tenant["users"]["owner"], "já pedi")
    refresh_alerts(tenant["unit"], force=True)
    assert not Alert.objects.filter(dedup_key=f"low_stock:{p.pk}", status="open").exists()  # adiado 24h


def test_dashboard_uses_real_data(api, tenant, product_factory, stock_in):
    p = product_factory("Gin", unit="L", cost="100", perishable=False)
    stock_in(p, "2", "100")
    d = api("owner").get("/api/dashboard/").json()
    kpis = {k["key"]: k for k in d["kpis"]}
    assert D(kpis["stock_value"]["value"]) == D("200.00")
    assert D(kpis["revenue_today"]["value"]) == 0
    assert all(k["help"] for k in d["kpis"])
    att = api("attendant").get("/api/dashboard/")
    assert att.status_code == 403


def test_assistant_answers_from_data(api, tenant, product_factory, stock_in):
    p = product_factory("Alface", unit="un", min_stock="10")
    stock_in(p, "2", "2.00")
    r = api("owner").post("/api/assistant/", {"question": "Quais produtos estão perto de acabar?"}, format="json").json()
    assert r["intent"] == "running_out"
    assert any(row["p"] == "Alface" for row in r["table"]["rows"])
    r = api("owner").post("/api/assistant/", {"question": "Quanto dinheiro tenho parado no estoque?"}, format="json").json()
    assert "R$ 10,00" in r["sections"][0]["text"] or "R$ 4,00" in r["sections"][0]["text"]
