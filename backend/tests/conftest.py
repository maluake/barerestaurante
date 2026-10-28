from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.core.models import Membership
from apps.core.setup import create_organization
from apps.inventory.models import Category, Product, ProductPackaging, UnitOfMeasure
from apps.purchasing.models import Supplier

D = Decimal


@pytest.fixture
def uom(db):
    from apps.inventory.units import ensure_default_units

    ensure_default_units()
    return {u.code: u for u in UnitOfMeasure.objects.filter(organization__isnull=True)}


def make_user(username, org=None, role=None):
    user = get_user_model().objects.create_user(username=username, password="Senha@Forte123")
    if org is not None:
        Membership.objects.create(user=user, organization=org, role=role)
    return user


@pytest.fixture
def tenant(db, uom):
    owner = make_user("dono")
    org, unit = create_organization(name="Bar Teste", owner=owner)
    users = {"owner": owner}
    for role in ("manager", "stock", "attendant", "kitchen"):
        users[role] = make_user(role, org, role)
    return {"org": org, "unit": unit, "users": users, "uom": uom}


@pytest.fixture
def other_tenant(db, uom):
    owner = make_user("outro_dono")
    org, unit = create_organization(name="Outro Bar", owner=owner)
    return {"org": org, "unit": unit, "owner": owner}


@pytest.fixture
def api(tenant):
    def make(role="owner", unit=None):
        c = APIClient()
        c.force_authenticate(tenant["users"][role])
        c.credentials(HTTP_X_UNIT_ID=str((unit or tenant["unit"]).pk))
        return c
    return make


@pytest.fixture
def supplier(tenant):
    return Supplier.objects.create(organization=tenant["org"], name="Fornecedor A (teste)", delivery_days=1,
                                   delivery_fee=D("10"))


@pytest.fixture
def product_factory(tenant):
    cat = Category.objects.filter(organization=tenant["org"]).first()

    def make(name="Batata", unit="kg", sku=None, cost="5.00", min_stock="2", ideal="10", perishable=True, shelf=10,
             packaging=None):
        p = Product.objects.create(organization=tenant["org"], name=name, sku=sku or name[:6].upper(), category=cat,
                                   unit=tenant["uom"][unit], cost_price=D(cost), min_stock=D(min_stock),
                                   ideal_stock=D(ideal), is_perishable=perishable, shelf_life_days=shelf)
        if packaging:
            pu, qty, inner = packaging
            ProductPackaging.objects.create(product=p, unit=tenant["uom"][pu], quantity=D(qty),
                                            contained_unit=tenant["uom"][inner])
        return p
    return make


@pytest.fixture
def stock_in(tenant):
    """Entrada de estoque direta (lote) para preparar cenários."""
    from uuid import uuid4

    from django.db import transaction

    from apps.inventory.services import add_stock, begin_operation

    def make(product, qty, cost="5.00", expires=None, unit=None, received=None, code=""):
        u = unit or tenant["unit"]
        with transaction.atomic():
            op = begin_operation(tenant["org"], u, f"test:{uuid4()}", "manual_entry")
            lot, _ = add_stock(op, u, product, D(qty), D(cost), lot_data={"expires_at": expires, "code": code,
                                                                          **({"received_at": received} if received else {})})
        return lot
    return make
