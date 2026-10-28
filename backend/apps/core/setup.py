"""Criação de um novo estabelecimento com cadastros básicos."""

from django.db import transaction

from .models import Membership, Organization, Unit

DEFAULT_CATEGORIES = [
    ("Hortifrúti", "ingredient"), ("Carnes e aves", "ingredient"), ("Peixes e frutos do mar", "ingredient"),
    ("Laticínios", "ingredient"), ("Mercearia seca", "ingredient"), ("Congelados", "ingredient"),
    ("Cervejas", "beverage"), ("Destilados", "beverage"), ("Refrigerantes e águas", "beverage"),
    ("Sucos e polpas", "beverage"), ("Descartáveis", "supply"), ("Limpeza", "supply"),
]

DEFAULT_EXPENSE_CATEGORIES = [
    ("Compra de mercadorias", "merchandise"), ("Aluguel", "fixed"), ("Energia elétrica", "fixed"),
    ("Água", "fixed"), ("Gás", "variable"), ("Internet e telefone", "fixed"), ("Salários", "payroll"),
    ("Encargos trabalhistas", "payroll"), ("Impostos sobre vendas", "tax"), ("Taxas de aplicativos", "fee"),
    ("Taxas de cartão", "fee"), ("Manutenção", "variable"), ("Marketing", "variable"),
    ("Entregas e motoboys", "variable"), ("Comissões", "fee"), ("Outras receitas", "revenue"),
    ("Outras despesas", "other"),
]

DEFAULT_LOCATIONS = [("Estoque seco", "dry"), ("Câmara fria", "chilled"), ("Freezer", "frozen"), ("Bar", "bar")]

DEFAULT_MENU_CATEGORIES = ["Entradas e porções", "Pratos principais", "Lanches", "Sobremesas", "Drinks",
                           "Cervejas", "Bebidas sem álcool"]


def setup_unit(unit):
    from apps.inventory.models import StorageLocation

    for name, kind in DEFAULT_LOCATIONS:
        StorageLocation.objects.get_or_create(organization=unit.organization, unit=unit, name=name,
                                              defaults={"kind": kind})


@transaction.atomic
def create_organization(*, name, owner, unit_name=None, city="", is_demo=False, plan="starter"):
    from apps.finance.models import ExpenseCategory
    from apps.inventory.models import Category
    from apps.inventory.units import ensure_default_units
    from apps.menu.models import MenuCategory

    ensure_default_units()
    org = Organization.objects.create(name=name, is_demo=is_demo, plan=plan)
    unit = Unit.objects.create(organization=org, name=unit_name or name, city=city, code="U1")
    Membership.objects.create(user=owner, organization=org, role="owner")
    for cname, kind in DEFAULT_CATEGORIES:
        Category.objects.create(organization=org, name=cname, kind=kind)
    for cname, kind in DEFAULT_EXPENSE_CATEGORIES:
        ExpenseCategory.objects.create(organization=org, name=cname, kind=kind)
    for i, cname in enumerate(DEFAULT_MENU_CATEGORIES):
        MenuCategory.objects.create(organization=org, name=cname, sort_order=i)
    setup_unit(unit)
    return org, unit


def next_number(model, org, field="number"):
    """Número sequencial por organização. Bloqueia a linha da organização para evitar duplicidade."""
    from django.db.models import Max

    Organization.objects.select_for_update().filter(pk=org.pk).first()
    current = model.objects.filter(organization=org).aggregate(m=Max(field))["m"] or 0
    return current + 1
