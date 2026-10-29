"""Cria (ou recria) o ambiente de DEMONSTRAÇÃO com dados fictícios.

Todos os dados passam pelos serviços reais (compras, recebimento, vendas, perdas, inventário),
então movimentações, lotes, custos e alertas são coerentes entre si.

    python manage.py seed_demo            # cria se não existir
    python manage.py seed_demo --reset    # apaga SOMENTE organizações marcadas como demonstração e recria
    python manage.py seed_demo --clear    # apenas apaga os dados de demonstração

Nada aqui representa fornecedores, preços ou empresas reais.
"""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Membership, Organization
from apps.core.setup import create_organization

DEMO_PASSWORD = "Demo@2026"
DEMO_USERS = [
    ("demo.dono", "Ana", "Proprietária", "owner"),
    ("demo.gerente", "Bruno", "Gerente", "manager"),
    ("demo.estoque", "Carla", "Estoquista", "stock"),
    ("demo.atendente", "Diego", "Atendente", "attendant"),
    ("demo.cozinha", "Elisa", "Cozinha", "kitchen"),
]
D = Decimal


def clear_demo(stdout=None):
    User = get_user_model()
    orgs = list(Organization.objects.filter(is_demo=True))
    user_ids = set(Membership.objects.filter(organization__in=orgs).values_list("user_id", flat=True))
    with transaction.atomic():
        for org in orgs:
            _delete_org(org)
        # Usuários que só pertenciam a organizações de demonstração
        for u in User.objects.filter(pk__in=user_ids):
            if not u.memberships.exists():
                u.delete()
    if stdout:
        stdout.write(f"Removidas {len(orgs)} organização(ões) de demonstração.")


def _delete_org(org):
    """Remove uma organização de demonstração respeitando a ordem das dependências protegidas."""
    from apps.finance.models import CashSession, FinancialEntry
    from apps.inventory.models import InventoryCount, Lot, Product, StockMovement, StockOperation, Transfer, WasteRecord
    from apps.menu.models import MenuItem
    from apps.purchasing.models import PurchaseIssue, PurchaseOrder, Receipt, ShoppingList
    from apps.sales.models import Order, Sale

    FinancialEntry.objects.filter(organization=org).delete()
    CashSession.objects.filter(organization=org).delete()
    Sale.objects.filter(organization=org).delete()
    Order.objects.filter(organization=org).delete()
    WasteRecord.objects.filter(organization=org).delete()
    InventoryCount.objects.filter(organization=org).delete()
    Transfer.objects.filter(organization=org).delete()
    PurchaseIssue.objects.filter(organization=org).delete()
    ShoppingList.objects.filter(organization=org).delete()
    for r in Receipt.objects.filter(organization=org):
        r.items.all().delete()
    StockMovement.objects.filter(organization=org).update(reversal_of=None)
    StockMovement.objects.filter(organization=org)._raw_delete(StockMovement.objects.db)
    Receipt.objects.filter(organization=org).delete()
    StockOperation.objects.filter(organization=org).update(reversed_by=None)
    StockOperation.objects.filter(organization=org).delete()
    PurchaseOrder.objects.filter(organization=org).delete()
    Lot.objects.filter(organization=org).delete()
    MenuItem.objects.filter(organization=org).delete()
    Product.objects.filter(organization=org).update(main_supplier=None)
    Product.objects.filter(organization=org).delete()
    org.delete()


class Command(BaseCommand):
    help = "Cria o ambiente de demonstração com dados fictícios (não afeta dados reais)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Apaga e recria a demonstração.")
        parser.add_argument("--clear", action="store_true", help="Apenas apaga a demonstração.")
        parser.add_argument("--days", type=int, default=45, help="Dias de histórico a simular.")

    def handle(self, *args, **opts):
        if opts["clear"] or opts["reset"]:
            clear_demo(self.stdout)
            if opts["clear"]:
                return
        if Organization.objects.filter(is_demo=True).exists():
            self.stdout.write("A demonstração já existe. Use --reset para recriar.")
            return
        # Tudo ou nada: se o processo for interrompido, nenhuma demonstração parcial fica no banco.
        with transaction.atomic():
            Seeder(self.stdout, opts["days"]).run()


class Seeder:
    def __init__(self, stdout, days):
        self.out = stdout
        self.days = days
        self.rng = random.Random(2026)

    def log(self, msg):
        self.out.write(msg)

    def at(self, day, hour=12, minute=0):
        return datetime.combine(day, time(hour, minute), tzinfo=self.tz)

    # ------------------------------------------------------------------ cadastros
    def run(self):
        from apps.inventory.models import UnitOfMeasure

        User = get_user_model()
        users = {}
        for username, first, last, role in DEMO_USERS:
            u = User.objects.filter(username=username).first() or User.objects.create_user(
                username=username, password=DEMO_PASSWORD, first_name=first, last_name=last,
                email=f"{username}@exemplo.invalid")
            users[role] = u
        self.users = users
        org, unit = create_organization(name="Bar e Restaurante Exemplo (demonstração)", owner=users["owner"],
                                        unit_name="Unidade Centro (fictícia)", city="Cidade Exemplo", is_demo=True, plan="pro")
        org.legal_name = "Empresa Fictícia de Demonstração"
        org.save()
        self.org, self.unit = org, unit
        self.tz = ZoneInfo(unit.timezone)
        for username, _, _, role in DEMO_USERS[1:]:
            Membership.objects.create(user=users[role], organization=org, role=role)
        from apps.core.models import Unit

        self.unit2 = Unit.objects.create(organization=org, name="Unidade Praia (fictícia)", city="Cidade Exemplo", code="U2")
        from apps.core.setup import setup_unit

        setup_unit(self.unit2)
        self.uom = {u.code: u for u in UnitOfMeasure.objects.filter(organization__isnull=True)}
        self.today = timezone.localdate(timezone=self.tz)
        with transaction.atomic():
            self.create_suppliers()
            self.create_products()
            self.create_quotes()
            self.create_menu()
        self.simulate_history()
        self.discard_expired(self.today)
        with transaction.atomic():
            self.create_today()
            self.create_finance()
        from apps.alerts.engine import refresh_alerts

        refresh_alerts(unit, force=True)
        refresh_alerts(self.unit2, force=True)
        self.log(self.style_ok(f"Demonstração criada: {org.name}. Usuários: " + ", ".join(u for u, *_ in DEMO_USERS)
                               + f" — senha {DEMO_PASSWORD}"))

    def style_ok(self, s):
        return s

    def create_suppliers(self):
        from apps.purchasing.models import Supplier

        data = [
            ("hort", "Hortifrúti Exemplo (fictício)", 1, D("150"), D("15"), "7 dias", 4, 4),
            ("bev", "Distribuidora de Bebidas Demo (fictícia)", 2, D("300"), D("0"), "28 dias", 5, 3),
            ("meat", "Açougue Modelo (fictício)", 1, D("200"), D("20"), "14 dias", 4, 5),
            ("whole", "Atacado Amostra (fictício)", 3, D("400"), D("35"), "21 dias", 3, 4),
            ("dairy", "Laticínios Ilustrativos (fictício)", 2, D("120"), D("12"), "14 dias", 5, 4),
        ]
        self.sup = {}
        for key, name, days, min_order, fee, terms, q, p in data:
            self.sup[key] = Supplier.objects.create(
                organization=self.org, name=name, contact_name="Contato fictício", phone="(00) 0000-0000",
                email=f"contato@{key}.exemplo.invalid", address="Rua Exemplo, s/n (endereço fictício)",
                neighborhood="Bairro Exemplo", city="Cidade Exemplo", state="EX", delivery_days=days,
                min_order_value=min_order, delivery_fee=fee, payment_terms=terms, quality_rating=q,
                punctuality_rating=p, is_demo=True, notes="Fornecedor fictício para demonstração.")

    def create_products(self):
        from apps.inventory.models import Category, Product, ProductPackaging, StorageLocation

        cats = {c.name: c for c in Category.objects.filter(organization=self.org)}
        locs = {l.name: l for l in StorageLocation.objects.filter(unit=self.unit)}
        # sku, nome, categoria, unidade, custo, min, ideal, perecível, validade(d), fornecedor, local, embalagem(unidade, qtd, contida)
        spec = [
            ("HF01", "Batata", "Hortifrúti", "kg", "4.80", 8, 20, True, 15, "hort", "Estoque seco", ("sc", 25, "kg")),
            ("HF02", "Tomate", "Hortifrúti", "kg", "6.50", 4, 10, True, 6, "hort", "Câmara fria", ("cx", 20, "kg")),
            ("HF03", "Cebola", "Hortifrúti", "kg", "4.20", 3, 8, True, 20, "hort", "Estoque seco", None),
            ("HF04", "Alface crespa", "Hortifrúti", "un", "2.50", 6, 15, True, 4, "hort", "Câmara fria", None),
            ("HF05", "Limão taiti", "Hortifrúti", "kg", "5.00", 3, 8, True, 10, "hort", "Câmara fria", None),
            ("HF06", "Mandioca", "Hortifrúti", "kg", "3.90", 4, 10, True, 7, "hort", "Câmara fria", None),
            ("HF07", "Hortelã (maço)", "Hortifrúti", "un", "2.00", 3, 8, True, 3, "hort", "Câmara fria", None),
            ("CA01", "Carne moída (blend)", "Carnes e aves", "kg", "38.00", 2, 5, True, 3, "meat", "Câmara fria", None),
            ("CA02", "Filé de frango", "Carnes e aves", "kg", "19.00", 3, 7, True, 4, "meat", "Câmara fria", None),
            ("CA03", "Picanha", "Carnes e aves", "kg", "79.00", 1, 3, True, 5, "meat", "Câmara fria", None),
            ("CA04", "Linguiça calabresa", "Carnes e aves", "kg", "24.00", 2, 6, True, 20, "meat", "Câmara fria", None),
            ("CA05", "Bacon", "Carnes e aves", "kg", "42.00", 1, 3, True, 25, "meat", "Câmara fria", None),
            ("LA01", "Queijo muçarela", "Laticínios", "kg", "36.00", 2, 5, True, 15, "dairy", "Câmara fria", None),
            ("LA02", "Ovos", "Laticínios", "un", "0.75", 30, 90, True, 21, "dairy", "Estoque seco", ("bd", 30, "un")),
            ("LA03", "Manteiga", "Laticínios", "kg", "48.00", 1, 2, True, 60, "dairy", "Câmara fria", None),
            ("MS01", "Pão de hambúrguer", "Mercearia seca", "un", "1.40", 20, 60, True, 6, "whole", "Estoque seco", ("pct", 12, "un")),
            ("MS02", "Óleo de soja", "Mercearia seca", "L", "8.50", 6, 18, False, None, "whole", "Estoque seco", ("cx", 20, "L")),
            ("MS03", "Arroz", "Mercearia seca", "kg", "5.80", 5, 15, False, None, "whole", "Estoque seco", ("fd", 30, "kg")),
            ("MS04", "Feijão carioca", "Mercearia seca", "kg", "8.20", 3, 10, False, None, "whole", "Estoque seco", None),
            ("MS05", "Sal refinado", "Mercearia seca", "kg", "2.60", 1, 3, False, None, "whole", "Estoque seco", None),
            ("MS06", "Açúcar", "Mercearia seca", "kg", "4.50", 2, 6, False, None, "whole", "Estoque seco", None),
            ("BE01", "Cerveja long neck 355ml", "Cervejas", "un", "4.90", 48, 144, False, None, "bev", "Bar", ("cx", 24, "un")),
            ("BE02", "Refrigerante lata 350ml", "Refrigerantes e águas", "un", "2.90", 24, 72, False, None, "bev", "Bar", ("fd", 12, "un")),
            ("BE03", "Água mineral 500ml", "Refrigerantes e águas", "un", "1.10", 24, 72, False, None, "bev", "Bar", ("fd", 12, "un")),
            ("BE04", "Cachaça prata", "Destilados", "L", "28.00", 2, 6, False, None, "bev", "Bar", ("gf", 1, "L")),
            ("BE05", "Gin", "Destilados", "L", "95.00", 1, 3, False, None, "bev", "Bar", ("gf", D("0.75"), "L")),
            ("BE06", "Água tônica lata", "Refrigerantes e águas", "un", "3.20", 12, 48, False, None, "bev", "Bar", ("fd", 6, "un")),
            ("BE07", "Gelo", "Outros", "kg", "1.20", 10, 30, False, None, "bev", "Freezer", ("sc", 5, "kg")),
            ("BE08", "Polpa de maracujá", "Sucos e polpas", "kg", "16.00", 1, 4, True, 90, "dairy", "Freezer", None),
            ("DE01", "Guardanapo de papel", "Descartáveis", "pct", "3.50", 10, 30, False, None, "whole", "Estoque seco", None),
        ]
        from apps.inventory.models import Category as Cat

        self.p = {}
        for sku, name, cat, unit, cost, mn, ideal, per, shelf, sup, loc, pack in spec:
            if cat not in cats:
                cats[cat] = Cat.objects.create(organization=self.org, name=cat, kind="other")
            unit_obj = self.uom[unit] if unit in self.uom else self.uom["un"]
            if unit == "pct":
                unit_obj = self.uom["pct"]
            prod = Product.objects.create(
                organization=self.org, sku=sku, name=name, category=cats[cat], unit=unit_obj, cost_price=D("0"),
                min_stock=D(mn), ideal_stock=D(ideal), is_perishable=per, shelf_life_days=shelf,
                main_supplier=self.sup[sup], default_location=locs.get(loc), brand="Marca fictícia" if sup == "bev" else "",
                description="Produto de demonstração.")
            if pack:
                ProductPackaging.objects.create(product=prod, unit=self.uom[pack[0]], quantity=D(pack[1]),
                                                contained_unit=self.uom[pack[2]])
            prod._base_cost = D(cost)
            prod._sup = sup
            self.p[sku] = prod
        # "pct" como unidade de estoque precisa de fator: guardanapo é controlado por pacote; usamos contagem própria.

    def create_quotes(self):
        from apps.purchasing.models import Quotation

        alt = {"hort": ["whole"], "meat": ["whole"], "dairy": ["whole"], "bev": ["whole"], "whole": ["hort"]}
        for sku, prod in self.p.items():
            sups = [prod._sup] + alt.get(prod._sup, [])[:1]
            for i, key in enumerate(sups):
                pack = prod.packagings.first()
                base = prod._base_cost * (D("1") if i == 0 else D(str(self.rng.choice(["0.93", "0.97", "1.06", "1.12"]))))
                if pack and i == 1:
                    unit = pack.unit
                    price = (base * pack.quantity * D("0.96")).quantize(D("0.01"))
                    min_q = D("1")
                else:
                    unit = prod.unit
                    price = base.quantize(D("0.01"))
                    min_q = D("1") if prod.unit.code in ("kg", "L") else D("6")
                quoted = self.today - timedelta(days=self.rng.choice([0, 1, 1, 2, 3, 4, 12]))
                Quotation.objects.create(
                    organization=self.org, supplier=self.sup[key], product=prod, price=price, purchase_unit=unit,
                    min_quantity=min_q, freight=D("0"), discount_percent=D(self.rng.choice(["0", "0", "3", "5"])),
                    valid_until=self.today + timedelta(days=self.rng.choice([1, 2, 7, 15, 30, 30])),
                    delivery_days=self.sup[key].delivery_days, payment_terms=self.sup[key].payment_terms,
                    quoted_at=quoted, notes="Cotação fictícia (demonstração)",
                    product_expiry=(self.today + timedelta(days=prod.shelf_life_days)) if prod.shelf_life_days else None,
                )

    def create_menu(self):
        from apps.menu.models import MenuCategory, MenuItem, RecipeIngredient
        from apps.menu.services import recalculate

        cats = {c.name: c for c in MenuCategory.objects.filter(organization=self.org)}
        u = self.uom
        items = [
            ("Batata frita (porção)", "Entradas e porções", "32.00", "recipe", [("HF01", "400", "g", 12), ("MS02", "60", "ml", 0), ("MS05", "5", "g", 0)], True),
            ("Mandioca frita (porção)", "Entradas e porções", "30.00", "recipe", [("HF06", "450", "g", 15), ("MS02", "60", "ml", 0), ("MS05", "5", "g", 0)], True),
            ("Frango à passarinho", "Entradas e porções", "42.00", "recipe", [("CA02", "500", "g", 5), ("MS02", "80", "ml", 0), ("HF05", "30", "g", 0)], True),
            ("Calabresa acebolada", "Entradas e porções", "38.00", "recipe", [("CA04", "350", "g", 0), ("HF03", "150", "g", 10)], True),
            ("Picanha na chapa (2 pessoas)", "Pratos principais", "129.00", "recipe", [("CA03", "500", "g", 8), ("HF03", "100", "g", 10), ("MS03", "200", "g", 0), ("MS05", "5", "g", 0)], True),
            ("Prato feito do dia", "Pratos principais", "29.90", "recipe", [("MS03", "150", "g", 0), ("MS04", "120", "g", 0), ("CA01", "120", "g", 0), ("LA02", "1", "un", 0), ("HF04", "0.25", "un", 0), ("HF02", "60", "g", 5)], True),
            ("Hambúrguer artesanal", "Lanches", "36.00", "recipe", [("MS01", "1", "un", 0), ("CA01", "160", "g", 0), ("LA01", "40", "g", 0), ("CA05", "30", "g", 0), ("HF04", "0.1", "un", 0), ("HF02", "40", "g", 5)], True),
            ("Salada da casa", "Entradas e porções", "26.00", "recipe", [("HF04", "1", "un", 20), ("HF02", "150", "g", 5), ("HF03", "40", "g", 10), ("HF05", "20", "g", 0)], True),
            ("Caipirinha de limão", "Drinks", "22.00", "recipe", [("BE04", "60", "ml", 0), ("HF05", "120", "g", 0), ("MS06", "25", "g", 0), ("BE07", "200", "g", 0)], False),
            ("Gin tônica", "Drinks", "34.00", "recipe", [("BE05", "60", "ml", 0), ("BE06", "1", "un", 0), ("HF05", "20", "g", 0), ("BE07", "200", "g", 0)], False),
            ("Caipirinha de maracujá", "Drinks", "24.00", "recipe", [("BE04", "60", "ml", 0), ("BE08", "80", "g", 0), ("MS06", "25", "g", 0), ("BE07", "200", "g", 0)], False),
            ("Cerveja long neck", "Cervejas", "13.00", "direct", ("BE01", "1", "un"), False),
            ("Refrigerante lata", "Bebidas sem álcool", "7.00", "direct", ("BE02", "1", "un"), False),
            ("Água mineral", "Bebidas sem álcool", "5.00", "direct", ("BE03", "1", "un"), False),
            ("Sobremesa do dia", "Sobremesas", "16.00", "recipe", [], True),  # sem ficha técnica (demonstra o alerta)
        ]
        self.menu = {}
        for name, cat, price, mode, recipe, kitchen in items:
            mi = MenuItem.objects.create(organization=self.org, name=name, category=cats.get(cat), price=D(price),
                                         stock_mode=mode, requires_preparation=kitchen, prep_time_minutes=15 if kitchen else 3,
                                         pos_code=f"PDV{len(self.menu) + 1:03d}", description="Item de demonstração.")
            if mode == "direct":
                sku, q, unit = recipe
                mi.direct_product = self.p[sku]
                mi.direct_quantity = D(q)
                mi.direct_unit = u[unit]
                mi.save()
            else:
                for sku, q, unit, loss in recipe:
                    RecipeIngredient.objects.create(menu_item=mi, product=self.p[sku], quantity=D(q), unit=u[unit],
                                                    loss_percent=D(loss))
            recalculate(mi, reason="Cadastro (demonstração)")
            self.menu[name] = mi

    # ------------------------------------------------------------------ histórico
    def popularity(self):
        return [
            ("Cerveja long neck", 9), ("Batata frita (porção)", 4), ("Refrigerante lata", 4), ("Caipirinha de limão", 3),
            ("Hambúrguer artesanal", 3), ("Prato feito do dia", 3), ("Água mineral", 2), ("Frango à passarinho", 2),
            ("Calabresa acebolada", 2), ("Mandioca frita (porção)", 1), ("Gin tônica", 1), ("Salada da casa", 1),
            ("Picanha na chapa (2 pessoas)", 1), ("Caipirinha de maracujá", 1), ("Sobremesa do dia", 1),
        ]

    def replenish(self, day, user):
        """Repõe o que está abaixo do mínimo usando o fluxo real de pedido de compra e recebimento."""
        from apps.inventory.services import available_quantity
        from apps.purchasing import services as ps

        by_sup = {}
        for sku, prod in self.p.items():
            avail = available_quantity(self.unit, prod, day)
            if avail < prod.min_stock * D("1.3"):
                need = prod.ideal_stock - avail
                if need > 0:
                    by_sup.setdefault(prod._sup, []).append((prod, need))
        for key, lines in by_sup.items():
            sup = self.sup[key]
            items = []
            for prod, need in lines:
                drift = D("1") + D(str((self.days - (self.today - day).days) * 0.004))  # custos sobem ao longo do tempo
                if prod.name in ("Tomate", "Picanha"):
                    drift += D(str((self.days - (self.today - day).days) * 0.006))
                price = (prod._base_cost * drift).quantize(D("0.01"))
                qty = need.quantize(D("1"), rounding="ROUND_CEILING") if prod.unit.dimension == "count" else need.quantize(D("0.1"), rounding="ROUND_CEILING")
                items.append({"product": prod, "purchase_unit": prod.unit, "quantity": qty, "unit_price": price})
            po = ps.create_purchase_order(self.org, self.unit, sup, items, user, source="manual", notes="Reposição (demonstração)")
            created = self.at(day, 8, 0)
            type(po).objects.filter(pk=po.pk).update(created_at=created)
            ps.submit_purchase_order(po, user, True)
            ps.send_purchase_order(po, user, expected_delivery=day)
            lines_rcv = []
            for it in po.items.select_related("product"):
                p = it.product
                lines_rcv.append({
                    "order_item": it, "quantity": it.quantity, "unit_price": it.unit_price, "lot_code": f"L{day:%m%d}{p.sku}",
                    "expires_at": day + timedelta(days=p.shelf_life_days) if p.shelf_life_days else None,
                })
            ps.receive_purchase_order(po, self.users["stock"], lines_rcv, document_number=f"NF-DEMO-{po.number:04d}",
                                      received_at=self.at(day, 9, 30))

    def discard_expired(self, day):
        from apps.inventory.models import Lot
        from apps.inventory.services import record_waste

        for lot in Lot.objects.filter(unit=self.unit, status="active", quantity_remaining__gt=0, expires_at__lt=day):
            record_waste(self.unit, lot.product, lot.quantity_remaining, "expired", user=self.users["stock"], lot=lot,
                         notes="Descarte de lote vencido (demonstração)", occurred_at=self.at(day, 7, 30),
                         key=f"demo-discard:{lot.pk}")

    def simulate_history(self):
        from apps.inventory.services import record_waste
        from apps.sales.services import register_sale

        menu_pool = []
        for name, weight in self.popularity():
            menu_pool += [self.menu[name]] * weight
        weekdays = set(self.org.setting("operating_weekdays"))
        manager = self.users["manager"]
        sale_n = 0
        for offset in range(self.days, 0, -1):
            day = self.today - timedelta(days=offset)
            if day.weekday() not in weekdays:
                continue
            self.discard_expired(day)
            self.replenish(day, manager)
            base = 18 if day.weekday() in (4, 5) else 11
            n_sales = base + self.rng.randint(-3, 5)
            times = sorted((self.rng.choice([12, 12, 13, 13, 19, 20, 20, 21, 22]), self.rng.randint(0, 59)) for _ in range(n_sales))
            for hour, minute in times:
                sale_n += 1
                k = self.rng.choice([1, 2, 2, 3, 3, 4])
                chosen = {}
                for _ in range(k):
                    mi = self.rng.choice(menu_pool)
                    chosen[mi] = chosen.get(mi, 0) + self.rng.choice([1, 1, 1, 2])
                when = self.at(day, hour, minute)
                channel = self.rng.choice(["table"] * 5 + ["counter"] * 2 + ["takeout", "app"])
                items = [{"menu_item": mi, "description": mi.name, "quantity": D(q), "unit_price": mi.price}
                         for mi, q in chosen.items()]
                gross = sum((i["quantity"] * i["unit_price"] for i in items), D("0"))
                fee = (gross * D("0.12")).quantize(D("0.01")) if channel == "app" else D("0")
                discount = D("5.00") if self.rng.random() < 0.08 and gross > 40 else D("0")
                register_sale(self.org, self.unit, self.users["attendant"], items=items, channel=channel,
                              payment_method=self.rng.choice(["pix", "pix", "credit", "debit", "cash"]) if channel != "app" else "app",
                              discount=discount, fee=fee, occurred_at=when, source="direct", external_id=f"DEMO-{sale_n:05d}")
            if self.rng.random() < 0.35:
                prod = self.p[self.rng.choice(["HF02", "HF04", "HF07", "CA02", "MS01", "HF01"])]
                from apps.inventory.services import available_quantity

                avail = available_quantity(self.unit, prod, day)
                if avail > 1:
                    q = min(avail * D("0.1"), D("2")).quantize(D("0.01"))
                    record_waste(self.unit, prod, q, self.rng.choice(["spoiled", "preparation", "storage"]),
                                 user=self.users["kitchen"], notes="Registro de perda (demonstração)",
                                 occurred_at=self.at(day, 23, 0))
        self.log(f"Histórico simulado: {sale_n} vendas em {self.days} dias.")

    # ------------------------------------------------------------------ situação atual
    def create_today(self):
        from apps.inventory.models import InventoryCount, InventoryCountItem
        from apps.inventory.services import add_stock, adjust_balance, begin_operation, physical_quantity
        from apps.purchasing import services as ps
        from apps.sales.services import change_order_status, create_order

        now = timezone.now()
        owner, manager, att, kitchen = self.users["owner"], self.users["manager"], self.users["attendant"], self.users["kitchen"]
        # Lotes com validades variadas para a tela de vencimentos (inclui um VENCIDO não descartado).
        op = begin_operation(self.org, self.unit, "demo:expiry-lots", "manual_entry", self.users["stock"], "Lotes de demonstração")
        for sku, days, qty in [("LA01", -1, "0.8"), ("HF02", 0, "2.5"), ("CA02", 2, "3"), ("LA02", 3, "30"),
                               ("MS01", 6, "24"), ("BE08", 20, "1.5")]:
            p = self.p[sku]
            add_stock(op, self.unit, p, D(qty), p.cost_price or p._base_cost, type_="adjustment", user=self.users["stock"],
                      reason="Lote de demonstração", occurred_at=now - timedelta(hours=2),
                      lot_data={"code": f"DEMO{sku}", "expires_at": self.today + timedelta(days=days),
                                "received_at": self.today - timedelta(days=2), "location": p.default_location, "source": "adjustment"})
        # Pedidos de clientes em vários estados
        specs = [
            (55, "table", "Mesa 4", [("Picanha na chapa (2 pessoas)", 1), ("Cerveja long neck", 3)], ["confirmed", "preparing"]),
            (18, "table", "Mesa 7", [("Batata frita (porção)", 1), ("Caipirinha de limão", 2)], ["confirmed", "preparing"]),
            (12, "counter", "", [("Hambúrguer artesanal", 2), ("Refrigerante lata", 2)], ["confirmed"]),
            (6, "delivery", "", [("Prato feito do dia", 2)], []),
            (3, "takeout", "", [("Frango à passarinho", 1)], []),
            (25, "table", "Mesa 2", [("Calabresa acebolada", 1), ("Cerveja long neck", 4)], ["confirmed", "preparing", "ready"]),
            (70, "table", "Mesa 1", [("Salada da casa", 1), ("Água mineral", 2)], ["confirmed", "preparing", "ready", "delivered"]),
            (45, "counter", "", [("Gin tônica", 2)], ["confirmed", "ready", "delivered"]),
            (35, "app", "", [("Hambúrguer artesanal", 1), ("Batata frita (porção)", 1)], ["confirmed", "preparing", "ready", "dispatched", "delivered"]),
            (30, "table", "Mesa 9", [("Mandioca frita (porção)", 1), ("Sobremesa do dia", 2)], ["confirmed", "preparing", "ready", "delivered"]),
            (40, "table", "Mesa 3", [("Frango à passarinho", 1)], ["confirmed", "preparing", "cancelled"]),
        ]
        for minutes, origin, label, items, flow in specs:
            created = now - timedelta(minutes=minutes)
            order, _ = create_order(self.org, self.unit, att, origin=origin, table_label=label, created_at=created,
                                    items=[{"menu_item": self.menu[n], "quantity": D(q)} for n, q in items],
                                    customer_name="Cliente exemplo" if origin in ("delivery", "takeout", "app") else "",
                                    delivery_fee=D("6.00") if origin == "delivery" else D("0"))
            step = 0
            for st in flow:
                step += 1
                at = created + timedelta(minutes=min(step * 6, minutes - 1))
                user = kitchen if st in ("preparing", "ready") else manager
                change_order_status(order, st, user, at=at, can_cancel_confirmed=True,
                                    note="Cliente desistiu (demonstração)" if st == "cancelled" else "",
                                    payment_method="pix" if st == "delivered" else None)
        # Compras: uma aguardando aprovação e uma atrasada
        sup = self.sup["whole"]
        po = ps.create_purchase_order(self.org, self.unit, sup, [
            {"product": self.p["MS02"], "purchase_unit": self.uom["cx"], "quantity": D("4"), "unit_price": D("165.00")},
            {"product": self.p["MS03"], "purchase_unit": self.uom["fd"], "quantity": D("2"), "unit_price": D("170.00")},
        ], self.users["manager"], notes="Compra mensal de mercearia (demonstração)")
        ps.submit_purchase_order(po, self.users["manager"], can_approve=False)
        po2 = ps.create_purchase_order(self.org, self.unit, self.sup["dairy"], [
            {"product": self.p["LA01"], "purchase_unit": self.p["LA01"].unit, "quantity": D("3"), "unit_price": D("37.50")},
            {"product": self.p["LA03"], "purchase_unit": self.p["LA03"].unit, "quantity": D("1"), "unit_price": D("49.00")},
        ], manager, notes="Reposição de laticínios (demonstração)")
        ps.submit_purchase_order(po2, manager, True)
        ps.send_purchase_order(po2, manager, expected_delivery=self.today - timedelta(days=2))
        # Inventário finalizado com divergências (3 dias atrás)
        inv = InventoryCount.objects.create(organization=self.org, unit=self.unit, started_by=self.users["stock"],
                                            description="Contagem semanal do bar (demonstração)")
        for sku, diff in [("BE01", "-6"), ("BE04", "-0.4"), ("BE02", "0"), ("BE07", "-3")]:
            p = self.p[sku]
            sysq = physical_quantity(self.unit, p)
            item = InventoryCountItem.objects.create(count=inv, product=p, system_quantity=sysq, unit_cost=p.cost_price,
                                                     counted_quantity=max(sysq + D(diff), D("0")), counted_by=self.users["stock"],
                                                     counted_at=now - timedelta(days=3))
            if item.difference:
                op = begin_operation(self.org, self.unit, f"inventory:{inv.pk}:{p.pk}", "inventory_adjustment",
                                     self.users["stock"], f"Ajuste de inventário #{inv.pk}: {p.name}")
                adjust_balance(op, self.unit, p, item.difference, user=self.users["stock"],
                               reason=f"Inventário #{inv.pk}: contagem semanal", ref_type="inventory", ref_id=inv.pk,
                               occurred_at=now - timedelta(days=3))
                item.adjustment = op
                item.save()
        InventoryCount.objects.filter(pk=inv.pk).update(status="closed", reason="Contagem semanal", closed_by=self.users["manager"],
                                                        closed_at=now - timedelta(days=3))
        # Estoque da segunda unidade (para transferências)
        op = begin_operation(self.org, self.unit2, "demo:unit2-initial", "manual_entry", owner, "Saldo inicial unidade 2")
        for sku, q in [("BE01", "48"), ("BE02", "24"), ("MS03", "10"), ("HF01", "10")]:
            p = self.p[sku]
            add_stock(op, self.unit2, p, D(q), p.cost_price, type_="initial", user=owner, reason="Saldo inicial (demonstração)",
                      lot_data={"code": f"INI{sku}", "expires_at": (self.today + timedelta(days=12)) if p.shelf_life_days else None})
        # Caixa aberto hoje
        from apps.finance.models import CashSession

        CashSession.objects.create(organization=self.org, unit=self.unit, opened_by=manager, opened_at=now - timedelta(hours=6),
                                   opening_amount=D("200.00"))

    def create_finance(self):
        from apps.finance.models import ExpenseCategory, FinancialEntry

        cats = {c.name: c for c in ExpenseCategory.objects.filter(organization=self.org)}
        month = self.today.replace(day=1)
        prev = (month - timedelta(days=1)).replace(day=1)
        for m in (prev, month):
            for name, amount, day in [("Aluguel", "6500.00", 5), ("Energia elétrica", "1850.00", 10), ("Água", "420.00", 12),
                                      ("Salários", "14800.00", 5), ("Encargos trabalhistas", "3900.00", 20),
                                      ("Internet e telefone", "260.00", 15), ("Gás", "780.00", 18)]:
                due = m.replace(day=day)
                FinancialEntry.objects.create(
                    organization=self.org, unit=self.unit, kind="payable", category=cats[name],
                    description=f"{name} (valor fictício)", amount=D(amount), competence_date=m, due_date=due,
                    status="paid" if due < self.today else "open", paid_at=due if due < self.today else None,
                    paid_amount=D(amount) if due < self.today else None, created_by=self.users["owner"])
