from decimal import Decimal

from rest_framework.test import APIClient

from apps.inventory.models import Product

D = Decimal


def test_unauthenticated_is_rejected(db):
    assert APIClient().get("/api/products/").status_code == 403


def test_session_login_requires_csrf(tenant):
    c = APIClient(enforce_csrf_checks=True)
    r = c.post("/api/auth/login/", {"username": "dono", "password": "Senha@Forte123"}, format="json")
    assert r.status_code == 200
    # Escrita sem token CSRF é recusada mesmo autenticado
    assert c.post("/api/categories/", {"name": "Nova"}, format="json").status_code == 403
    c.get("/api/auth/csrf/")
    token = c.cookies["csrftoken"].value
    assert c.post("/api/categories/", {"name": "Nova"}, format="json", HTTP_X_CSRFTOKEN=token).status_code == 201


def test_wrong_password(tenant):
    r = APIClient().post("/api/auth/login/", {"username": "dono", "password": "errada"}, format="json")
    assert r.status_code == 400


def test_role_permissions_enforced_in_backend(api):
    assert api("attendant").get("/api/finance/summary/").status_code == 403
    assert api("attendant").post("/api/products/", {}, format="json").status_code == 403
    assert api("kitchen").get("/api/purchase-orders/").status_code == 403
    assert api("stock").get("/api/team/").status_code == 403
    assert api("manager").get("/api/team/").status_code == 403
    assert api("owner").get("/api/team/").status_code == 200
    assert api("stock").get("/api/lots/").status_code == 200
    assert api("kitchen").get("/api/orders/board/").status_code == 200


def test_revoked_and_extra_permissions(api, tenant):
    from apps.core.models import Membership

    m = Membership.objects.get(user=tenant["users"]["manager"])
    m.revoked_permissions = ["purchases.approve"]
    m.extra_permissions = ["finance.view"]
    m.save()
    c = api("manager")
    assert c.get("/api/finance/summary/").status_code == 200
    ctx = c.get("/api/context/").json()
    assert "purchases.approve" not in ctx["permissions"]


def test_tenant_isolation_by_unit_header(tenant, other_tenant, api):
    c = api("owner")
    c.credentials(HTTP_X_UNIT_ID=str(other_tenant["unit"].pk))
    assert c.get("/api/products/").status_code == 403


def test_cannot_read_or_reference_other_tenant_objects(tenant, other_tenant, api, uom):
    foreign = Product.objects.create(organization=other_tenant["org"], name="Segredo", sku="X1", unit=uom["kg"])
    c = api("owner")
    assert c.get(f"/api/products/{foreign.pk}/").status_code == 404
    assert all(p["id"] != foreign.pk for p in c.get("/api/products/").json()["results"])
    from apps.menu.models import MenuItem

    r = c.post("/api/menu-items/", {"name": "Prato", "price": "10.00", "stock_mode": "recipe", "ingredients": [
        {"product": foreign.pk, "quantity": "1", "unit": uom["kg"].pk}]}, format="json")
    assert r.status_code == 400
    assert not MenuItem.objects.filter(name="Prato").exists()


def test_unit_restricted_member_cannot_switch_unit(tenant, api):
    from apps.core.models import Membership, Unit

    u2 = Unit.objects.create(organization=tenant["org"], name="Filial")
    m = Membership.objects.get(user=tenant["users"]["attendant"])
    m.units.set([tenant["unit"]])
    assert api("attendant", unit=u2).get("/api/orders/").status_code == 403
    assert api("owner", unit=u2).get("/api/orders/").status_code == 200


def test_plan_limit_on_units(api):
    r = api("owner").post("/api/units/", {"name": "Segunda"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "plan_limit"


def test_last_owner_cannot_be_removed(api, tenant):
    from apps.core.models import Membership

    m = Membership.objects.get(user=tenant["users"]["owner"])
    r = api("owner").patch(f"/api/team/{m.pk}/", {"role": "manager"}, format="json")
    assert r.status_code == 400


def test_audit_log_records_actions(api, tenant):
    c = api("owner")
    c.post("/api/categories/", {"name": "Auditada"}, format="json")
    logs = c.get("/api/audit/").json()["results"]
    assert any("Auditada" in l["summary"] for l in logs)


def test_signup_creates_establishment(db, uom):
    c = APIClient()
    r = c.post("/api/auth/signup/", {"establishment_name": "Meu Bar", "first_name": "Rita", "email": "rita@exemplo.com",
                                     "username": "rita", "password": "Bar@Seguro2026", "accept_terms": True}, format="json")
    assert r.status_code == 201
    me = r.json()
    assert me["memberships"][0]["role"] == "owner"
    assert c.get("/api/products/").status_code == 200
    r = APIClient().post("/api/auth/signup/", {"establishment_name": "X", "first_name": "a", "email": "a@a.com",
                                               "username": "rita", "password": "123", "accept_terms": False}, format="json")
    assert r.status_code == 400
