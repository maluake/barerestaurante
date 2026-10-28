from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessError
from apps.core.tenancy import TenantMixin, TenantModelViewSet, audit

from . import services
from .analytics import annotate_stock, consumption_rates, period_bounds
from .models import (
    Category,
    InventoryCount,
    InventoryCountItem,
    Lot,
    Product,
    StockMovement,
    StockOperation,
    StorageLocation,
    Transfer,
    UnitOfMeasure,
    WasteRecord,
)
from .serializers import (
    CategorySerializer,
    CostHistorySerializer,
    InventoryCountSerializer,
    LotSerializer,
    MovementSerializer,
    ProductSerializer,
    StockEntrySerializer,
    StorageLocationSerializer,
    TransferSerializer,
    UnitOfMeasureSerializer,
    WasteSerializer,
)
from .units import convert


class UnitOfMeasureViewSet(TenantModelViewSet):
    serializer_class = UnitOfMeasureSerializer
    queryset = UnitOfMeasure.objects.all()
    required_permissions = {"list": "products.view", "retrieve": "products.view", "*": "products.manage"}
    pagination_class = None
    http_method_names = ["get", "post", "head", "options"]

    def scope_queryset(self, qs):
        return qs.filter(Q(organization=self.request.org) | Q(organization__isnull=True))


class CategoryViewSet(TenantModelViewSet):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    required_permissions = {"list": "products.view", "retrieve": "products.view", "*": "products.manage"}
    pagination_class = None
    search_fields = ["name"]

    def get_queryset(self):
        return super().get_queryset().annotate(product_count=Count("products", filter=Q(products__status="active")))

    def perform_destroy(self, instance):
        if instance.products.exists():
            raise BusinessError("Categoria possui produtos vinculados. Mova os produtos antes de excluir.")
        audit(self.request, "delete", instance, summary=f"Categoria {instance.name} excluída")
        instance.delete()


class StorageLocationViewSet(TenantModelViewSet):
    serializer_class = StorageLocationSerializer
    queryset = StorageLocation.objects.all()
    unit_scoped = True
    pagination_class = None
    required_permissions = {"list": "stock.view", "retrieve": "stock.view", "*": "products.manage"}


class ProductViewSet(TenantModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.select_related("category", "unit", "default_location", "main_supplier").prefetch_related(
        "packagings__unit", "packagings__contained_unit"
    )
    required_permissions = {
        "list": "products.view", "retrieve": "products.view", "lots": "stock.view", "movements": "stock.view",
        "cost_history": "products.view", "stock_entry": "stock.move", "set_cost": "products.manage",
        "*": "products.manage",
    }
    filterset_fields = {"category": ["exact"], "status": ["exact"], "is_perishable": ["exact"], "main_supplier": ["exact"]}
    search_fields = ["name", "sku", "barcode", "brand"]
    ordering_fields = ["name", "sku", "quantity", "cost_price", "created_at", "next_expiry"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = annotate_stock(super().get_queryset(), self.request.unit)
        params = self.request.query_params
        if self.action == "list" and not params.get("status"):
            qs = qs.filter(status="active")
        flag = params.get("stock")
        if flag == "low":
            qs = qs.filter(min_stock__gt=0, quantity__lt=F("min_stock") + F("expired_quantity"))
        elif flag == "out":
            qs = qs.filter(quantity__lte=F("expired_quantity"))
        elif flag == "expired":
            qs = qs.filter(expired_quantity__gt=0)
        return qs

    def perform_destroy(self, instance):
        if instance.movements.exists() or instance.recipe_uses.exists():
            raise BusinessError("Este produto possui histórico ou é usado em fichas técnicas. Arquive-o em vez de excluir.",
                                code="has_history")
        audit(self.request, "delete", instance, summary=f"Produto {instance.name} excluído")
        instance.delete()

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        product = self.get_object()
        product.status = "archived" if product.status == "active" else "active"
        product.save(update_fields=["status", "updated_at"])
        audit(request, "archive" if product.status == "archived" else "unarchive", product, summary=product.name)
        return Response(self.get_serializer(self.get_queryset().get(pk=product.pk)).data)

    @action(detail=True, methods=["get"])
    def lots(self, request, pk=None):
        product = self.get_object()
        qs = Lot.objects.filter(unit=request.unit, product=product).select_related("supplier", "location", "product__unit")
        if request.query_params.get("all") != "1":
            qs = qs.filter(status="active")
        return Response(LotSerializer(qs, many=True, context={"today": services.today_for(request.unit)}).data)

    @action(detail=True, methods=["get"])
    def movements(self, request, pk=None):
        product = self.get_object()
        qs = StockMovement.objects.filter(unit=request.unit, product=product).select_related(
            "product__unit", "user", "lot", "operation", "counterpart_unit")[:200]
        return Response(MovementSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], url_path="cost-history")
    def cost_history(self, request, pk=None):
        product = self.get_object()
        return Response(CostHistorySerializer(product.cost_history.select_related("user")[:100], many=True).data)

    @action(detail=True, methods=["post"], url_path="set-cost")
    def set_cost(self, request, pk=None):
        product = self.get_object()
        try:
            cost = Decimal(str(request.data.get("cost")))
        except Exception:
            raise BusinessError("Informe um custo válido.", field="cost")
        if cost < 0:
            raise BusinessError("O custo não pode ser negativo.", field="cost")
        with transaction.atomic():
            services.update_product_cost(product, cost, source="manual", reference=request.data.get("reason", "")[:60],
                                         user=request.user)
        audit(request, "set_cost", product, summary=f"Custo de {product.name} alterado para {cost}")
        return Response(self.get_serializer(self.get_queryset().get(pk=product.pk)).data)

    @action(detail=False, methods=["post"], url_path="stock-entry")
    def stock_entry(self, request):
        ser = StockEntrySerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        product = d["product"]
        qty = convert(d["quantity"], d.get("unit") or product.unit, product.unit, product)
        unit_cost = d.get("unit_cost")
        if unit_cost is None:
            unit_cost = product.cost_price
        elif d.get("unit") and d["unit"] != product.unit:
            unit_cost = (unit_cost * d["quantity"] / qty) if qty else unit_cost
        from uuid import uuid4

        key = f"entry:{d.get('idempotency_key') or uuid4()}"
        try:
            with transaction.atomic():
                op = services.begin_operation(request.org, request.unit, key, "manual_entry", request.user,
                                              f"Entrada manual de {product.name}")
                lot, mv = services.add_stock(
                    op, request.unit, product, qty, unit_cost, type_=d["type"], user=request.user,
                    reason=d.get("reason") or dict(StockEntrySerializer.TYPES)[d["type"]],
                    lot_data={"code": d.get("lot_code", ""), "expires_at": d.get("expires_at"),
                              "manufactured_at": d.get("manufactured_at"),
                              "location": d.get("location") or product.default_location,
                              "source": "initial" if d["type"] == "initial" else "adjustment"},
                )
                if not product.cost_price and unit_cost:
                    services.update_product_cost(product, unit_cost, source="initial", user=request.user)
        except services.AlreadyProcessed:
            return Response({"detail": "Esta entrada já foi registrada."}, status=status.HTTP_200_OK)
        audit(request, "stock_entry", product, summary=f"Entrada de {qty.normalize()} {product.unit.code} de {product.name}")
        return Response(MovementSerializer(mv).data, status=status.HTTP_201_CREATED)


class LotViewSet(TenantMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = LotSerializer
    queryset = Lot.objects.select_related("product__unit", "supplier", "location")
    unit_scoped = True
    required_permissions = {"discard": "waste.manage", "*": "stock.view"}
    filterset_fields = ["product", "status", "supplier", "location"]
    search_fields = ["product__name", "code", "document"]
    ordering_fields = ["expires_at", "received_at", "quantity_remaining"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["today"] = services.today_for(self.request.unit)
        return ctx

    @action(detail=True, methods=["post"])
    def discard(self, request, pk=None):
        lot = self.get_object()
        if lot.status != "active" or lot.quantity_remaining <= 0:
            raise BusinessError("Este lote não possui saldo para descarte.")
        try:
            record = services.discard_lot(lot, user=request.user, notes=request.data.get("notes", ""))
        except services.AlreadyProcessed:
            raise BusinessError("Este lote já foi descartado.")
        audit(request, "discard", lot, summary=f"Descarte do lote {lot.code or lot.pk} de {lot.product.name}")
        return Response(WasteSerializer(record).data, status=status.HTTP_201_CREATED)


def expiry_bucket(days, buckets):
    if days < 0:
        return "expired"
    if days == 0:
        return "today"
    for limit in sorted(b for b in buckets if b > 0):
        if days <= limit:
            return f"d{limit}"
    return None


class ExpiryOverviewView(TenantMixin, APIView):
    """Lotes por faixa de vencimento, com recomendações seguras de ação."""

    required_permissions = "stock.view"

    def get(self, request):
        unit, org = request.unit, request.org
        today = services.today_for(unit)
        buckets = [int(b) for b in org.setting("expiry_buckets")]
        horizon = max(buckets) if buckets else 30
        lots = list(
            Lot.objects.filter(unit=unit, status="active", quantity_remaining__gt=0, expires_at__isnull=False,
                               expires_at__lte=today + timedelta(days=horizon))
            .select_related("product__unit", "product__category", "location", "supplier").order_by("expires_at")
        )
        product_ids = {l.product_id for l in lots}
        rates = consumption_rates(unit, product_ids=product_ids, today=today)
        from apps.menu.models import MenuItem

        uses = defaultdict(list)
        for item in MenuItem.objects.filter(organization=org, status="active").filter(
            Q(ingredients__product_id__in=product_ids) | Q(direct_product_id__in=product_ids)
        ).distinct().prefetch_related("ingredients"):
            pids = {i.product_id for i in item.ingredients.all()} | ({item.direct_product_id} if item.direct_product_id else set())
            for pid in pids & product_ids:
                uses[pid].append(item.name)
        other_units = org.units.filter(is_active=True).exclude(pk=unit.pk).exists()

        groups = defaultdict(list)
        totals = defaultdict(lambda: {"count": 0, "value": Decimal("0")})
        # Consumo previsto é alocado por FEFO entre os lotes do mesmo produto.
        consumed_before = defaultdict(lambda: Decimal("0"))
        for lot in lots:
            days = (lot.expires_at - today).days
            bucket = expiry_bucket(days, buckets)
            if bucket is None:
                continue
            value = (lot.quantity_remaining * lot.unit_cost).quantize(Decimal("0.01"))
            rate = rates.get(lot.product_id, {}).get("rate", Decimal("0"))
            recommendations = []
            at_risk = None
            if bucket == "expired":
                recommendations.append({"kind": "required", "text": "Lote vencido: isole do estoque disponível e registre o descarte. Não utilize nem venda."})
            else:
                usable_days = days + 1
                projected = rate * usable_days - consumed_before[lot.product_id]
                projected = max(projected, Decimal("0"))
                consumed_before[lot.product_id] += min(projected, lot.quantity_remaining)
                at_risk = max(lot.quantity_remaining - projected, Decimal("0"))
                recommendations.append({"kind": "suggestion", "text": "Priorize o consumo seguro deste lote (FEFO), conferindo as condições de conservação."})
                if uses.get(lot.product_id):
                    recommendations.append({"kind": "suggestion", "text": "Planeje preparos que usam o ingrediente: " + ", ".join(uses[lot.product_id][:4]) + "."})
                if at_risk > 0:
                    recommendations.append({"kind": "estimate", "text": f"Pelo consumo médio, cerca de {at_risk.quantize(Decimal('0.01')).normalize()} {lot.product.unit.code} podem não ser usados até a validade. Revise as próximas compras."})
                    if other_units:
                        recommendations.append({"kind": "suggestion", "text": "Avalie transferir parte do lote para outra unidade, respeitando a cadeia de conservação."})
                    if uses.get(lot.product_id):
                        recommendations.append({"kind": "suggestion", "text": "Se adequado para venda, avalie uma promoção dos itens que usam este produto."})
            groups[bucket].append({
                **LotSerializer(lot, context={"today": today}).data,
                "bucket": bucket,
                "category_name": lot.product.category.name if lot.product.category else None,
                "daily_consumption": str(rate.quantize(Decimal("0.0001"))),
                "at_risk_quantity": str(at_risk.quantize(Decimal("0.0001"))) if at_risk is not None else None,
                "recommendations": recommendations,
            })
            totals[bucket]["count"] += 1
            totals[bucket]["value"] += value
        order = ["expired", "today"] + [f"d{b}" for b in sorted(b for b in buckets if b > 0)]
        labels = {"expired": "Vencidos", "today": "Vencem hoje"}
        prev = 0
        for b in sorted(b for b in buckets if b > 0):
            labels[f"d{b}"] = f"Vencem em {prev + 1} a {b} dias" if prev else f"Vencem nos próximos {b} dias"
            prev = b
        return Response({
            "today": today,
            "buckets": [{"key": k, "label": labels[k], "count": totals[k]["count"], "value": str(totals[k]["value"]),
                         "lots": groups.get(k, [])} for k in order],
            "safety_note": "A data de validade não garante, sozinha, que um alimento está seguro. Confira temperatura, "
                           "embalagem, aparência e os procedimentos de boas práticas antes de usar.",
        })


class MovementViewSet(TenantMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = MovementSerializer
    queryset = StockMovement.objects.select_related("product__unit", "user", "lot", "operation", "counterpart_unit")
    unit_scoped = True
    required_permissions = "stock.view"
    filterset_fields = {"type": ["exact", "in"], "product": ["exact"], "ref_type": ["exact"], "ref_id": ["exact"],
                        "operation": ["exact"], "lot": ["exact"]}
    search_fields = ["product__name", "reason", "operation__key"]
    ordering_fields = ["occurred_at", "quantity", "total_cost"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("start"):
            qs = qs.filter(occurred_at__date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(occurred_at__date__lte=p["end"])
        return qs


class StockOperationViewSet(TenantMixin, viewsets.GenericViewSet):
    queryset = StockOperation.objects.all()
    required_permissions = "stock.adjust"
    REVERSIBLE = {"manual_entry", "waste"}

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        op = self.get_object()
        if op.kind not in self.REVERSIBLE:
            raise BusinessError("Esta operação é estornada pelo próprio módulo de origem (venda, compra, inventário).")
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            raise BusinessError("Informe o motivo do estorno.", field="reason")
        try:
            reversal = services.reverse_operation(op, user=request.user, reason=f"Estorno: {reason}")
        except services.AlreadyProcessed:
            raise BusinessError("Esta operação já foi estornada.")
        audit(request, "reverse", op, summary=f"Estorno da operação {op.key}: {reason}", entity="stock_operation")
        return Response({"reversal_operation": reversal.pk})


class WasteViewSet(TenantModelViewSet):
    serializer_class = WasteSerializer
    queryset = WasteRecord.objects.select_related("product__unit", "product__category", "user", "lot")
    unit_scoped = True
    required_permissions = {"list": ("stock.view",), "retrieve": "stock.view", "analysis": "stock.view", "*": "waste.manage"}
    filterset_fields = {"product": ["exact"], "reason": ["exact"], "product__category": ["exact"]}
    search_fields = ["product__name", "notes"]
    http_method_names = ["get", "post", "head", "options"]

    def check_permissions(self, request):
        # Cozinha pode registrar perdas sem ver todo o estoque.
        if self.action in ("list", "retrieve") and self.has_perm("waste.manage"):
            return
        super().check_permissions(request)

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("start"):
            qs = qs.filter(occurred_at__date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(occurred_at__date__lte=p["end"])
        return qs

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        product = d["product"]
        qty = convert(d["quantity"], d.get("input_unit") or product.unit, product.unit, product)
        key = request.headers.get("Idempotency-Key")
        try:
            record = services.record_waste(request.unit, product, qty, d["reason"], user=request.user, lot=d.get("lot"),
                                           notes=d.get("notes", ""), key=f"waste:{key}" if key else None)
        except services.AlreadyProcessed as exc:
            record = WasteRecord.objects.get(operation=exc.operation)
            return Response(self.get_serializer(record).data, status=status.HTTP_200_OK)
        audit(request, "create", record, summary=f"Perda de {qty.normalize()} {product.unit.code} de {product.name}")
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def analysis(self, request):
        today = services.today_for(request.unit)
        start = request.query_params.get("start") or str(today.replace(day=1))
        end = request.query_params.get("end") or str(today)
        from datetime import date

        s, e = period_bounds(request.unit, date.fromisoformat(start), date.fromisoformat(end))
        qs = WasteRecord.objects.filter(unit=request.unit, occurred_at__gte=s, occurred_at__lt=e)
        total = qs.aggregate(v=Sum("total_cost"))["v"] or Decimal("0")
        by_product = list(qs.values("product_id", "product__name", "product__unit__code").annotate(
            value=Sum("total_cost"), quantity=Sum("quantity"), records=Count("id")).order_by("-value")[:10])
        by_category = list(qs.values("product__category__name").annotate(value=Sum("total_cost")).order_by("-value"))
        by_reason = [{**r, "label": dict(WasteRecord.REASONS).get(r["reason"], r["reason"])}
                     for r in qs.values("reason").annotate(value=Sum("total_cost"), records=Count("id")).order_by("-value")]
        tips = {
            "expired": "Reduza o tamanho dos pedidos de produtos que vencem antes de serem usados e reforce o FEFO na arrumação.",
            "spoiled": "Revise temperatura e vedação dos equipamentos de conservação e o tempo de exposição.",
            "preparation": "Padronize porcionamento e treine a equipe com as fichas técnicas.",
            "broken": "Revise o manuseio e o armazenamento de garrafas e embalagens frágeis.",
            "storage": "Organize os locais de armazenamento e confira a temperatura diariamente.",
            "returned": "Investigue as causas de devolução com a equipe de salão e cozinha.",
            "cancelled_order": "Confirme os pedidos com o cliente antes de iniciar o preparo.",
        }
        suggestions = []
        for r in by_reason[:3]:
            if r["reason"] in tips and r["value"]:
                share = (r["value"] / total * 100).quantize(Decimal("0.1")) if total else 0
                suggestions.append({"reason": r["label"], "share_percent": share, "text": tips[r["reason"]]})
        return Response({"start": start, "end": end, "total_value": total, "by_product": by_product,
                         "by_category": by_category, "by_reason": by_reason, "suggestions": suggestions})


class InventoryCountViewSet(TenantModelViewSet):
    serializer_class = InventoryCountSerializer
    queryset = InventoryCount.objects.select_related("started_by", "closed_by").prefetch_related(
        "items__product__unit", "items__product__category", "items__counted_by")
    unit_scoped = True
    required_permissions = {"list": "stock.view", "retrieve": "stock.view", "*": "stock.adjust"}
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        products = Product.objects.filter(organization=request.org, status="active")
        if d.get("products"):
            products = products.filter(pk__in=[p.pk for p in d["products"]])
        elif d.get("categories"):
            products = products.filter(category__in=d["categories"])
        products = list(annotate_stock(products, request.unit))
        if not products:
            raise BusinessError("Nenhum produto selecionado para contagem.")
        with transaction.atomic():
            count = InventoryCount.objects.create(organization=request.org, unit=request.unit, started_by=request.user,
                                                  description=d.get("description", ""))
            InventoryCountItem.objects.bulk_create([
                InventoryCountItem(count=count, product=p, system_quantity=p.quantity, unit_cost=p.cost_price)
                for p in products
            ])
        audit(request, "create", count, summary=f"Inventário iniciado com {len(products)} produtos")
        return Response(self.get_serializer(self.get_queryset().get(pk=count.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def count(self, request, pk=None):
        """Registra contagens: {"items": [{"id": 1, "counted_quantity": "2.5"}]}"""
        inv = self.get_object()
        if inv.status != "open":
            raise BusinessError("Este inventário não está em contagem.")
        entries = request.data.get("items") or []
        with transaction.atomic():
            for entry in entries:
                item = inv.items.select_related("product").filter(pk=entry.get("id")).first()
                if item is None:
                    continue
                raw = entry.get("counted_quantity")
                if raw in (None, ""):
                    item.counted_quantity = None
                    item.counted_at = None
                else:
                    try:
                        qty = Decimal(str(raw).replace(",", "."))
                    except Exception:
                        raise BusinessError(f"Quantidade inválida para {item.product.name}.")
                    if qty < 0:
                        raise BusinessError(f"Quantidade negativa para {item.product.name}.")
                    item.counted_quantity = qty
                    # Saldo do sistema no momento da contagem: o ajuste aplicará apenas a diferença.
                    item.system_quantity = services.physical_quantity(request.unit, item.product)
                    item.counted_at = timezone.now()
                    item.counted_by = request.user
                item.save()
        return Response(self.get_serializer(self.get_queryset().get(pk=inv.pk)).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            raise BusinessError("Informe o motivo do ajuste de inventário.", field="reason")
        with transaction.atomic():
            inv = InventoryCount.objects.select_for_update().get(pk=self.get_object().pk)
            if inv.status != "open":
                raise BusinessError("Este inventário já foi finalizado.")
            adjusted = 0
            for item in inv.items.select_related("product__unit").filter(counted_quantity__isnull=False):
                diff = item.difference
                if not diff:
                    continue
                op = services.begin_operation(request.org, request.unit, f"inventory:{inv.pk}:{item.product_id}",
                                              "inventory_adjustment", request.user,
                                              f"Ajuste de inventário #{inv.pk}: {item.product.name}")
                services.adjust_balance(op, request.unit, item.product, diff, user=request.user,
                                        reason=f"Inventário #{inv.pk}: {reason}", ref_type="inventory", ref_id=inv.pk)
                item.adjustment = op
                item.save(update_fields=["adjustment"])
                adjusted += 1
            inv.status = "closed"
            inv.reason = reason
            inv.closed_by = request.user
            inv.closed_at = timezone.now()
            inv.save()
        audit(request, "close", inv, summary=f"Inventário #{inv.pk} finalizado com {adjusted} ajustes: {reason}")
        return Response(self.get_serializer(self.get_queryset().get(pk=inv.pk)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        inv = self.get_object()
        if inv.status != "open":
            raise BusinessError("Somente inventários em contagem podem ser cancelados.")
        inv.status = "cancelled"
        inv.closed_by = request.user
        inv.closed_at = timezone.now()
        inv.save()
        audit(request, "cancel", inv, summary=f"Inventário #{inv.pk} cancelado")
        return Response(self.get_serializer(inv).data)


class TransferViewSet(TenantModelViewSet):
    serializer_class = TransferSerializer
    queryset = Transfer.objects.select_related("from_unit", "to_unit", "user").prefetch_related("items__product__unit")
    required_permissions = {"list": "stock.view", "retrieve": "stock.view", "*": "stock.transfer"}
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        u = self.request.unit
        return super().get_queryset().filter(Q(from_unit=u) | Q(to_unit=u))

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        to_unit = d["to_unit"]
        if not request.membership.allowed_units().filter(pk=to_unit.pk).exists():
            raise BusinessError("Você não tem acesso à unidade de destino.")
        items = [(i["product"], i["quantity"]) for i in d["items"] if i["quantity"] > 0]
        if not items:
            raise BusinessError("Informe ao menos um item com quantidade.")
        transfer = services.transfer_stock(request.org, request.unit, to_unit, items, user=request.user,
                                           notes=d.get("notes", ""),
                                           key=f"transfer:{request.headers['Idempotency-Key']}" if request.headers.get("Idempotency-Key") else None)
        audit(request, "create", transfer, summary=f"Transferência para {to_unit.name} ({len(items)} itens)")
        return Response(self.get_serializer(transfer).data, status=status.HTTP_201_CREATED)


class ConvertView(TenantMixin, APIView):
    """Calculadora de conversão explícita entre unidades."""

    required_permissions = "products.view"

    def get(self, request):
        p = request.query_params
        try:
            from_u = UnitOfMeasure.objects.get(pk=p.get("from"))
            to_u = UnitOfMeasure.objects.get(pk=p.get("to"))
            qty = Decimal(p.get("quantity", "1"))
        except Exception:
            raise BusinessError("Parâmetros inválidos.")
        product = Product.objects.filter(organization=request.org, pk=p.get("product")).first() if p.get("product") else None
        return Response({"quantity": convert(qty, from_u, to_u, product).quantize(Decimal("0.0001"))})

