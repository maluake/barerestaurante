"""Fluxo de aceitação completo (seção 22 do escopo), executado somente pela API."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient

D = Decimal


def test_full_flow_via_api(db, uom):
    c = APIClient()
    # 1. Criar estabelecimento
    me = c.post("/api/auth/signup/", {"establishment_name": "Bar Fluxo", "first_name": "Dona", "email": "dona@exemplo.com",
                                      "username": "dona", "password": "Fluxo@Seguro2026", "accept_terms": True}, format="json").json()
    unit_id = me["memberships"][0]["units"][0]["id"]
    c.credentials(HTTP_X_UNIT_ID=str(unit_id))
    kg = next(u["id"] for u in c.get("/api/units-of-measure/").json() if u["code"] == "kg")
    g = next(u["id"] for u in c.get("/api/units-of-measure/").json() if u["code"] == "g")
    # 2. Fornecedor
    sup = c.post("/api/suppliers/", {"name": "Hortifrúti Teste", "delivery_days": 1, "delivery_fee": "10.00",
                                     "cnpj": "11.222.333/0001-81"}, format="json")
    assert sup.status_code == 201, sup.content
    sup = sup.json()
    # 3. Produto
    prod = c.post("/api/products/", {"name": "Batata", "sku": "BAT", "unit": kg, "min_stock": "5", "ideal_stock": "15",
                                     "is_perishable": True, "shelf_life_days": 15, "main_supplier": sup["id"]}, format="json")
    assert prod.status_code == 201, prod.content
    prod = prod.json()
    # 4. Cotação
    today = timezone.localdate()
    q = c.post("/api/quotations/", {"supplier": sup["id"], "product": prod["id"], "price": "4.50", "purchase_unit": kg,
                                    "quoted_at": str(today), "min_quantity": "1"}, format="json")
    assert q.status_code == 201, q.content
    # 5. Pedido de compra
    po = c.post("/api/purchase-orders/", {"supplier": sup["id"], "items": [
        {"product": prod["id"], "purchase_unit": kg, "quantity": "10", "unit_price": "4.50"}]}, format="json")
    assert po.status_code == 201, po.content
    po = po.json()
    assert c.post(f"/api/purchase-orders/{po['id']}/submit/", format="json").json()["status"] == "approved"
    assert c.post(f"/api/purchase-orders/{po['id']}/send/", {}, format="json").json()["status"] == "sent"
    # 6–7. Receber com lote e validade (parcial + restante)
    item_id = po["items"][0]["id"]
    exp = str(today + timedelta(days=12))
    r = c.post(f"/api/purchase-orders/{po['id']}/receive/", {"document_number": "NF-1", "items": [
        {"order_item": item_id, "quantity": "6", "expires_at": exp, "lot_code": "L1"}]}, format="json")
    assert r.status_code == 201 and r.json()["status"] == "partially_received"
    r = c.post(f"/api/purchase-orders/{po['id']}/receive/", {"document_number": "NF-2", "items": [
        {"order_item": item_id, "quantity": "4", "expires_at": exp, "lot_code": "L2"}]}, format="json")
    assert r.json()["status"] == "received"
    # 8. Estoque atualizado
    p = c.get(f"/api/products/{prod['id']}/").json()
    assert D(p["quantity"]) == D("10") and D(p["cost_price"]) == D("4.5")
    assert len(c.get(f"/api/products/{prod['id']}/lots/").json()) == 2
    # 9. Ficha técnica
    mi = c.post("/api/menu-items/", {"name": "Batata frita", "price": "30.00", "stock_mode": "recipe", "ingredients": [
        {"product": prod["id"], "quantity": "250", "unit": g, "loss_percent": "0"}]}, format="json")
    assert mi.status_code == 201, mi.content
    mi = mi.json()
    assert D(mi["theoretical_cost"]) == D("1.125")
    # 10–11. Venda com baixa dos ingredientes
    s = c.post("/api/sales/", {"channel": "counter", "payment_method": "pix", "items": [
        {"menu_item": mi["id"], "quantity": "4"}]}, format="json")
    assert s.status_code == 201, s.content
    s = s.json()
    assert s["stock_status"] == "consumed" and D(s["cogs"]) == D("4.50")
    assert D(c.get(f"/api/products/{prod['id']}/").json()["quantity"]) == D("9")
    # 12. Movimentações
    movs = c.get("/api/movements/", {"product": prod["id"]}).json()["results"]
    assert {m["type"] for m in movs} == {"receipt", "sale"}
    # 13. Alertas (estoque mínimo 5: ainda acima; cria condição consumindo mais)
    c.post("/api/waste/", {"product": prod["id"], "quantity": "5", "reason": "spoiled", "notes": "teste"}, format="json")
    alerts = c.get("/api/alerts/").json()["results"]
    assert any(a["type"] == "low_stock" for a in alerts)
    # 14. Lista de compras
    sl = c.post("/api/shopping-lists/generate/", {}, format="json").json()
    assert any(i["product"] == prod["id"] for i in sl["items"])
    # 15. Comparar fornecedores
    cmp = c.post("/api/compare/", {"items": [{"product": prod["id"], "quantity": "10"}]}, format="json").json()
    assert cmp["products"][0]["best"]["supplier_id"] == sup["id"]
    # 16. Relatórios coerentes
    rep = c.get("/api/reports/sales_by_period/").json()
    assert D(rep["totals"]["net"]) == D("120.00") and D(rep["totals"]["cogs"]) == D("4.50")
    waste = c.get("/api/reports/waste/").json()
    assert D(waste["totals"]["value"]) == D("22.50")
    fin = c.get("/api/finance/summary/").json()
    assert D(fin["contribution_margin"]) == D("115.50")
    csv = c.get("/api/reports/sales_by_period/", {"export": "csv"})
    assert csv.status_code == 200 and "Ticket médio" in csv.content.decode("utf-8-sig")
    # Cancelamento com estorno auditável
    r = c.post(f"/api/sales/{s['id']}/cancel/", {"reason": "erro de lançamento", "return_to_stock": True}, format="json")
    assert r.json()["status"] == "cancelled"
    assert D(c.get(f"/api/products/{prod['id']}/").json()["quantity"]) == D("5")
    assert c.get("/api/audit/").json()["count"] > 5
