import csv
import io
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessError
from apps.core.tenancy import TenantMixin, TenantModelViewSet, audit
from apps.inventory.models import Product, ProductCostHistory, StorageLocation, UnitOfMeasure
from apps.inventory.services import today_for

from . import services
from .models import PurchaseIssue, PurchaseOrder, PurchaseOrderItem, Quotation, ShoppingList, ShoppingListItem, Supplier
from .serializers import (
    PurchaseIssueSerializer,
    PurchaseOrderSerializer,
    QuotationSerializer,
    ShoppingListItemSerializer,
    ShoppingListSerializer,
    SupplierSerializer,
)


def parse_decimal(value, default=None):
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value).replace(".", "").replace(",", ".") if "," in str(value) else str(value))
    except InvalidOperation:
        raise BusinessError(f"Número inválido: {value}")


class SupplierViewSet(TenantModelViewSet):
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.prefetch_related("categories", "documents")
    required_permissions = {"list": "suppliers.view", "retrieve": "suppliers.view", "history": "suppliers.view",
                            "*": "suppliers.manage"}
    filterset_fields = ["is_active", "city", "categories"]
    search_fields = ["name", "trade_name", "cnpj", "city", "neighborhood", "contact_name"]
    ordering_fields = ["name", "city", "delivery_days", "created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return super().get_queryset().annotate(product_count=Count("quotations__product", distinct=True)).order_by("name")

    def perform_destroy(self, instance):
        if instance.purchase_orders.exists():
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            audit(self.request, "deactivate", instance, summary=f"Fornecedor {instance} inativado (possui histórico)")
            return
        audit(self.request, "delete", instance, summary=f"Fornecedor {instance} excluído")
        instance.delete()

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        supplier = self.get_object()
        orders = PurchaseOrder.objects.filter(organization=request.org, supplier=supplier).prefetch_related("items", "receipts")
        received = [o for o in orders if o.status in ("received", "partially_received")]
        on_time = 0
        evaluated = 0
        for o in received:
            first = o.receipts.order_by("received_at").first()
            if first and o.expected_delivery:
                evaluated += 1
                if timezone.localdate(first.received_at) <= o.expected_delivery:
                    on_time += 1
        issues = PurchaseIssue.objects.filter(organization=request.org, order__supplier=supplier)
        products = (Quotation.objects.filter(organization=request.org, supplier=supplier)
                    .values("product_id", "product__name").annotate(n=Count("id")).order_by("product__name"))
        return Response({
            "orders": [{"id": o.id, "number": o.number, "status": o.get_status_display(), "total": o.total,
                        "created_at": o.created_at, "expected_delivery": o.expected_delivery} for o in orders[:50]],
            "metrics": {
                "orders": len(orders),
                "total_received": sum((r.total for o in received for r in o.receipts.all()), Decimal("0")),
                "on_time_rate": round(on_time / evaluated * 100, 1) if evaluated else None,
                "deliveries_evaluated": evaluated,
                "issues": issues.count(),
                "issues_by_kind": dict(Counter(issues.values_list("kind", flat=True))),
            },
            "products": list(products),
        })

    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        """Importa fornecedores de um CSV (separador ; ou ,). Colunas: nome, nome_fantasia, cnpj, contato,
        telefone, whatsapp, email, endereco, bairro, cidade, uf, pedido_minimo, prazo_entrega_dias,
        taxa_entrega, condicoes_pagamento, observacoes."""
        f = request.FILES.get("file")
        if not f:
            raise BusinessError("Envie um arquivo CSV no campo 'file'.")
        text = f.read().decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text.splitlines()[0] if text else "nome", delimiters=";,")
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        created, skipped, errors = 0, 0, []
        ser_ctx = self.get_serializer_context()
        for i, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row.get("nome"):
                errors.append({"linha": i, "erro": "Nome obrigatório."})
                continue
            if Supplier.objects.filter(organization=request.org, name__iexact=row["nome"]).exists():
                skipped += 1
                continue
            data = {
                "name": row["nome"], "trade_name": row.get("nome_fantasia", ""), "cnpj": row.get("cnpj", ""),
                "contact_name": row.get("contato", ""), "phone": row.get("telefone", ""), "whatsapp": row.get("whatsapp", ""),
                "email": row.get("email", ""), "address": row.get("endereco", ""), "neighborhood": row.get("bairro", ""),
                "city": row.get("cidade", ""), "state": row.get("uf", "")[:2],
                "min_order_value": str(parse_decimal(row.get("pedido_minimo"), Decimal("0"))),
                "delivery_days": int(row.get("prazo_entrega_dias") or 1),
                "delivery_fee": str(parse_decimal(row.get("taxa_entrega"), Decimal("0"))),
                "payment_terms": row.get("condicoes_pagamento", ""), "notes": row.get("observacoes", ""),
            }
            ser = SupplierSerializer(data=data, context=ser_ctx)
            if not ser.is_valid():
                errors.append({"linha": i, "erro": ser.errors})
                continue
            ser.save(organization=request.org)
            created += 1
        audit(request, "import", None, entity="supplier", summary=f"Importação de fornecedores: {created} criados")
        return Response({"created": created, "skipped_existing": skipped, "errors": errors})


class QuotationViewSet(TenantModelViewSet):
    serializer_class = QuotationSerializer
    queryset = Quotation.objects.select_related("supplier", "product__unit", "purchase_unit")
    required_permissions = {"list": "suppliers.view", "retrieve": "suppliers.view", "*": "suppliers.manage"}
    filterset_fields = ["supplier", "product"]
    search_fields = ["product__name", "supplier__name", "supplier__trade_name", "brand"]
    ordering_fields = ["quoted_at", "price", "valid_until"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def perform_create(self, serializer):
        obj = serializer.save(organization=self.request.org, created_by=self.request.user)
        audit(self.request, "create", obj, summary=f"Cotação {obj.product.name} — {obj.supplier}: R$ {obj.price}")


class CompareView(TenantMixin, APIView):
    """Comparador inteligente: menor custo total viável, não apenas o menor preço."""

    required_permissions = "suppliers.view"

    def post(self, request):
        items = request.data.get("items") or []
        if not items:
            raise BusinessError("Informe os produtos e as quantidades necessárias.")
        today = today_for(request.unit)
        parsed = []
        for it in items:
            product = Product.objects.filter(organization=request.org, pk=it.get("product")).select_related("unit").first()
            if product is None:
                raise BusinessError("Produto não encontrado.")
            qty = parse_decimal(it.get("quantity"))
            if not qty or qty <= 0:
                raise BusinessError(f"Informe a quantidade necessária de {product.name}.")
            if it.get("unit"):
                from apps.inventory.units import convert

                qty = convert(qty, UnitOfMeasure.objects.get(pk=it["unit"]), product.unit, product)
            parsed.append((product, qty))
        products = [services.compare_product(request.org, p, q, today) for p, q in parsed]
        result = {"products": products}
        if len(parsed) > 1:
            result["list"] = services.compare_list(request.org, parsed, today)
        return Response(result)


class OpportunitiesView(TenantMixin, APIView):
    required_permissions = "suppliers.view"

    def get(self, request):
        org, unit = request.org, request.unit
        today = today_for(unit)
        since = today - timedelta(days=30)
        changes = []
        for h in ProductCostHistory.objects.filter(product__organization=org, created_at__date__gte=since,
                                                   previous_cost__gt=0).select_related("product__unit").order_by("-created_at"):
            pct = (h.cost - h.previous_cost) / h.previous_cost * 100
            if abs(pct) >= 3:
                changes.append({"product_id": h.product_id, "product": h.product.name, "previous_cost": h.previous_cost,
                                "cost": h.cost, "unit": h.product.unit.code, "variation_percent": pct.quantize(Decimal("0.1")),
                                "date": h.created_at, "source": h.source})
        seen = set()
        unique_changes = []
        for c in changes:
            if c["product_id"] in seen:
                continue
            seen.add(c["product_id"])
            unique_changes.append(c)
        # Variação entre cotações do mesmo fornecedor
        quote_moves = []
        by_pair = defaultdict(list)
        for q in Quotation.objects.filter(organization=org, quoted_at__gte=today - timedelta(days=60)).select_related(
                "supplier", "product__unit", "purchase_unit").order_by("-quoted_at", "-id"):
            by_pair[(q.supplier_id, q.product_id, q.purchase_unit_id)].append(q)
        for (_, _, _), qs in by_pair.items():
            if len(qs) >= 2 and qs[1].price:
                pct = (qs[0].price - qs[1].price) / qs[1].price * 100
                if abs(pct) >= 3:
                    quote_moves.append({"product": qs[0].product.name, "supplier": str(qs[0].supplier),
                                        "previous_price": qs[1].price, "price": qs[0].price,
                                        "purchase_unit": qs[0].purchase_unit.code,
                                        "variation_percent": pct.quantize(Decimal("0.1")), "quoted_at": qs[0].quoted_at})
        expiring_quotes = QuotationSerializer(
            Quotation.objects.filter(organization=org, valid_until__gte=today, valid_until__lte=today + timedelta(days=3))
            .select_related("supplier", "product__unit", "purchase_unit"), many=True, context={"org": org}).data
        # Fornecedores competitivos: quantas vezes cada um é o melhor custo total para o estoque ideal.
        wins = Counter()
        compared = 0
        products = Product.objects.filter(organization=org, status="active", quotations__isnull=False).distinct()[:80]
        for p in products:
            cmp = services.compare_product(org, p, p.ideal_stock or p.min_stock or Decimal("1"), today)
            if cmp["best"]:
                compared += 1
                wins[cmp["best"]["supplier_name"]] += 1
        competitive = [{"supplier": s, "best_in": n, "of": compared} for s, n in wins.most_common(5)]
        # Descontos com validade próxima: só sinalizados quando há consumo previsto que absorva a compra.
        from apps.inventory.analytics import consumption_rates

        rates = consumption_rates(unit, today=today)
        discount_offers = []
        for q in Quotation.objects.filter(organization=org, discount_percent__gt=0, quoted_at__gte=today - timedelta(days=7),
                                          product_expiry__isnull=False).select_related("supplier", "product__unit", "purchase_unit"):
            days = (q.product_expiry - today).days
            if days < 0:
                continue
            rate = rates.get(q.product_id, {}).get("rate", Decimal("0"))
            usable = (rate * days).quantize(Decimal("0.01"))
            discount_offers.append({
                "product": q.product.name, "supplier": str(q.supplier), "discount_percent": q.discount_percent,
                "product_expiry": q.product_expiry, "days_to_expiry": days, "max_useful_quantity": usable,
                "unit": q.product.unit.code,
                "advice": (f"Compre no máximo cerca de {usable.normalize()} {q.product.unit.code}, o consumo previsto até a validade."
                           if usable > 0 else "Sem consumo previsto até a validade: não recomendamos comprar."),
            })
        joint = None
        low = [p for p in Product.objects.filter(organization=org, status="active", min_stock__gt=0)]
        from apps.inventory.services import available_quantity

        needs = [(p, max(p.ideal_stock - available_quantity(unit, p), p.min_stock)) for p in low
                 if available_quantity(unit, p) < p.min_stock]
        if len(needs) > 1:
            cmp = services.compare_list(org, needs[:30], today)
            joint = {"items": len(needs), "best_split": cmp["best_split"], "best_single_supplier": cmp["best_single_supplier"]}
        return Response({
            "cost_decreases": [c for c in unique_changes if c["variation_percent"] < 0],
            "cost_increases": [c for c in unique_changes if c["variation_percent"] > 0],
            "quote_changes": quote_moves,
            "competitive_suppliers": competitive,
            "expiring_quotes": expiring_quotes,
            "discount_offers": discount_offers,
            "joint_purchase": joint,
            "note": "Oportunidades calculadas apenas com dados cadastrados no sistema. Nenhum preço externo é consultado.",
        })


class ShoppingListViewSet(TenantMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ShoppingListSerializer
    queryset = ShoppingList.objects.select_related("created_by").prefetch_related(
        "items__product__unit", "items__supplier")
    unit_scoped = True
    required_permissions = {"list": "purchases.view", "retrieve": "purchases.view", "*": "purchases.manage"}

    @action(detail=False, methods=["post"])
    def generate(self, request):
        coverage = request.data.get("coverage_days")
        sl = services.generate_shopping_list(request.unit, request.user, coverage_days=coverage)
        audit(request, "generate", sl, summary=f"Lista de compras gerada com {sl.items.count()} itens")
        return Response(self.get_serializer(self.get_queryset().get(pk=sl.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="items/(?P<item_id>[0-9]+)")
    def update_item(self, request, pk=None, item_id=None):
        sl = self.get_object()
        if sl.status != "open":
            raise BusinessError("Esta lista já gerou pedidos e não pode ser alterada.")
        item = sl.items.filter(pk=item_id).first()
        if item is None:
            raise BusinessError("Item não encontrado.")
        ser = ShoppingListItemSerializer(item, data=request.data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        item = ser.save()
        if "quantity" in request.data or "supplier" in request.data:
            self._reprice(item, request)
        return Response(ShoppingListItemSerializer(item).data)

    @action(detail=True, methods=["post"], url_path="add-item")
    def add_item(self, request, pk=None):
        sl = self.get_object()
        product = Product.objects.filter(organization=request.org, pk=request.data.get("product")).first()
        if not product:
            raise BusinessError("Produto não encontrado.")
        qty = parse_decimal(request.data.get("quantity"), Decimal("1"))
        item = ShoppingListItem.objects.create(
            shopping_list=sl, product=product, suggested_quantity=0, quantity=qty, supplier=product.main_supplier,
            justification="Incluído manualmente.", confidence="limited")
        self._reprice(item, request)
        return Response(ShoppingListItemSerializer(item).data, status=status.HTTP_201_CREATED)

    def _reprice(self, item, request):
        cmp = services.compare_product(request.org, item.product, item.quantity, today_for(request.unit))
        chosen = None
        for q in cmp["quotes"]:
            if item.supplier_id and q["supplier_id"] == item.supplier_id and q.get("total") is not None:
                chosen = q
        if chosen is None and not item.supplier_id:
            chosen = cmp["best"]
        if chosen:
            item.supplier_id = chosen["supplier_id"]
            item.quotation_id = chosen["quotation_id"]
            item.estimated_cost = chosen["total"]
        else:
            item.quotation = None
            item.estimated_cost = (item.quantity * item.product.cost_price).quantize(Decimal("0.01"))
        item.save()

    @action(detail=True, methods=["post"], url_path="create-orders")
    def create_orders(self, request, pk=None):
        with transaction.atomic():
            sl = ShoppingList.objects.select_for_update().get(pk=self.get_object().pk)
            if sl.status != "open":
                raise BusinessError("Os pedidos desta lista já foram gerados.")
            groups = defaultdict(list)
            missing = []
            for item in sl.items.filter(selected=True, quantity__gt=0).select_related("product__unit", "quotation__purchase_unit"):
                if not item.supplier_id:
                    missing.append(item.product.name)
                    continue
                groups[item.supplier_id].append(item)
            if missing:
                raise BusinessError("Selecione um fornecedor para: " + ", ".join(missing))
            if not groups:
                raise BusinessError("Nenhum item selecionado.")
            orders = []
            for supplier_id, items in groups.items():
                supplier = Supplier.objects.get(pk=supplier_id, organization=request.org)
                lines = []
                for it in items:
                    q = it.quotation if it.quotation and it.quotation.supplier_id == supplier_id else None
                    if q:
                        from apps.inventory.units import convert

                        per = convert(1, q.purchase_unit, it.product.unit, it.product)
                        units = services.round_purchase_quantity(it.quantity / per, q.purchase_unit, q.min_quantity)
                        price = (q.price * (1 - q.discount_percent / 100)).quantize(Decimal("0.0001"))
                        lines.append({"product": it.product, "purchase_unit": q.purchase_unit, "quantity": units,
                                      "unit_price": price, "quotation": q})
                    else:
                        lines.append({"product": it.product, "purchase_unit": it.product.unit, "quantity": it.quantity,
                                      "unit_price": it.product.cost_price})
                po = services.create_purchase_order(request.org, request.unit, supplier, lines, request.user,
                                                    source="shopping_list", notes=f"Gerado da lista de compras #{sl.pk}")
                orders.append(po)
            sl.status = "ordered"
            sl.save(update_fields=["status"])
        audit(request, "create_orders", sl, summary=f"{len(orders)} pedidos de compra gerados da lista #{sl.pk}")
        return Response({"orders": [{"id": o.id, "number": o.number, "supplier": str(o.supplier)} for o in orders]},
                        status=status.HTTP_201_CREATED)


class PurchaseOrderViewSet(TenantModelViewSet):
    serializer_class = PurchaseOrderSerializer
    queryset = PurchaseOrder.objects.select_related(
        "supplier", "created_by", "approved_by", "sent_by", "cancelled_by", "organization").prefetch_related(
        "items__product__unit", "items__purchase_unit", "receipts__items__order_item__product",
        "receipts__items__order_item__purchase_unit", "receipts__received_by", "issues__product")
    unit_scoped = True
    required_permissions = {
        "list": "purchases.view", "retrieve": "purchases.view", "approve": "purchases.approve",
        "reject": "purchases.approve", "receive": "purchases.receive", "*": "purchases.manage",
    }
    filterset_fields = ["status", "supplier"]
    search_fields = ["number", "supplier__name", "supplier__trade_name"]
    ordering_fields = ["created_at", "number", "expected_delivery"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("late") == "1":
            qs = qs.filter(status__in=("approved", "sent", "partially_received"), expected_delivery__lt=today_for(self.request.unit))
        return qs

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        po = services.create_purchase_order(
            request.org, request.unit, d["supplier"], d["items"], request.user, notes=d.get("notes", ""),
            expected_delivery=d.get("expected_delivery"), freight=d.get("freight"), payment_terms=d.get("payment_terms", ""))
        audit(request, "create", po, summary=f"Pedido de compra #{po.number} criado ({po.supplier})")
        return Response(self.get_serializer(self.get_queryset().get(pk=po.pk)).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        po = self.get_object()
        if po.status != "draft":
            raise BusinessError("Somente rascunhos podem ser editados.")
        ser = self.get_serializer(po, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        with transaction.atomic():
            for f in ("expected_delivery", "freight", "discount", "payment_terms", "notes", "supplier"):
                if f in d:
                    setattr(po, f, d[f])
            po.save()
            if "items" in d:
                po.items.all().delete()
                for it in d["items"]:
                    PurchaseOrderItem.objects.create(order=po, product=it["product"], quotation=it.get("quotation"),
                                                     purchase_unit=it.get("purchase_unit") or it["product"].unit,
                                                     quantity=it["quantity"], unit_price=it["unit_price"])
        audit(request, "update", po, summary=f"Pedido de compra #{po.number} editado")
        return Response(self.get_serializer(self.get_queryset().get(pk=po.pk)).data)

    def _respond(self, po):
        return Response(self.get_serializer(self.get_queryset().get(pk=po.pk)).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        po = services.submit_purchase_order(self.get_object(), request.user, self.has_perm("purchases.approve"))
        audit(request, "submit", po, summary=f"Pedido #{po.number}: {po.get_status_display()}")
        return self._respond(po)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        po = services.approve_purchase_order(self.get_object(), request.user, True)
        audit(request, "approve", po, summary=f"Pedido #{po.number} aprovado")
        return self._respond(po)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        reason = request.data.get("reason", "")
        po = services.approve_purchase_order(self.get_object(), request.user, False, reason)
        audit(request, "reject", po, summary=f"Pedido #{po.number} reprovado: {reason}")
        return self._respond(po)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        from datetime import date

        exp = request.data.get("expected_delivery")
        po = services.send_purchase_order(self.get_object(), request.user, date.fromisoformat(exp) if exp else None)
        audit(request, "send", po, summary=f"Pedido #{po.number} enviado ao fornecedor")
        return self._respond(po)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        po = services.cancel_purchase_order(self.get_object(), request.user, request.data.get("reason", "").strip())
        audit(request, "cancel", po, summary=f"Pedido #{po.number} cancelado")
        return self._respond(po)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        from datetime import date

        po = self.get_object()
        items_by_id = {i.pk: i for i in po.items.all()}
        lines = []
        for raw in request.data.get("items") or []:
            item = items_by_id.get(int(raw.get("order_item", 0) or 0))
            if item is None:
                raise BusinessError("Item do pedido inválido.")
            location = None
            if raw.get("location"):
                location = StorageLocation.objects.filter(organization=request.org, unit=request.unit, pk=raw["location"]).first()
            lines.append({
                "order_item": item, "quantity": parse_decimal(raw.get("quantity"), Decimal("0")),
                "unit_price": parse_decimal(raw.get("unit_price")),
                "rejected_quantity": parse_decimal(raw.get("rejected_quantity"), Decimal("0")),
                "lot_code": (raw.get("lot_code") or "")[:60],
                "expires_at": date.fromisoformat(raw["expires_at"]) if raw.get("expires_at") else None,
                "manufactured_at": date.fromisoformat(raw["manufactured_at"]) if raw.get("manufactured_at") else None,
                "location": location, "notes": (raw.get("notes") or "")[:255],
            })
        receipt, created = services.receive_purchase_order(
            po, request.user, lines, document_number=request.data.get("document_number", ""),
            notes=request.data.get("notes", ""), close_remaining=bool(request.data.get("close_remaining")),
            idempotency_key=request.headers.get("Idempotency-Key"))
        if created:
            audit(request, "receive", po, summary=f"Recebimento do pedido #{po.number} (R$ {receipt.total})")
        return Response(self.get_serializer(self.get_queryset().get(pk=po.pk)).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PurchaseIssueViewSet(TenantMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = PurchaseIssueSerializer
    queryset = PurchaseIssue.objects.select_related("order__supplier", "product")
    required_permissions = {"list": "purchases.view", "*": "purchases.receive"}
    filterset_fields = ["status", "kind", "order"]

    def perform_create(self, serializer):
        obj = serializer.save(organization=self.request.org, created_by=self.request.user)
        audit(self.request, "create", obj, summary=f"Ocorrência no pedido #{obj.order.number}: {obj.get_kind_display()}")

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        issue = self.get_object()
        issue.status = "resolved"
        issue.resolution = request.data.get("resolution", "")
        issue.resolved_at = timezone.now()
        issue.save()
        audit(request, "resolve", issue, summary=f"Ocorrência resolvida: {issue.resolution}")
        return Response(self.get_serializer(issue).data)

