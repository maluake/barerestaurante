from datetime import date
from decimal import Decimal

from django.db.models import Count, Q, Sum
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessError
from apps.core.tenancy import TenantMixin, TenantModelViewSet, audit
from apps.inventory.analytics import period_bounds
from apps.inventory.services import today_for

from . import services
from .importer import import_sales_csv
from .models import ImportBatch, Order, PosMapping, Sale
from .serializers import (
    ImportBatchSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    PosMappingSerializer,
    SaleCreateSerializer,
    SaleSerializer,
)

KITCHEN_STATUSES = {"preparing", "ready"}


def date_range(request):
    today = today_for(request.unit)
    p = request.query_params
    start = date.fromisoformat(p["start"]) if p.get("start") else today
    end = date.fromisoformat(p["end"]) if p.get("end") else start if p.get("start") else today
    return start, end


class OrderViewSet(TenantMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.select_related("created_by", "organization", "sale").prefetch_related(
        "items__menu_item", "events__user")
    unit_scoped = True
    required_permissions = {"create": "orders.manage", "board": ("orders.view",), "*": "orders.view"}
    filterset_fields = {"status": ["exact", "in"], "origin": ["exact"]}
    search_fields = ["number", "table_label", "customer_name"]
    ordering_fields = ["created_at", "number", "total"]

    def check_permissions(self, request):
        if self.action == "board" and (self.has_perm("kitchen.update") or self.has_perm("orders.view")):
            return
        if self.action == "set_status":
            return  # verificado por transição em set_status
        super().check_permissions(request)

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if self.action == "list" and (p.get("start") or p.get("end")):
            start, end = date_range(self.request)
            s, e = period_bounds(self.request.unit, start, end)
            qs = qs.filter(created_at__gte=s, created_at__lt=e)
        if p.get("open") == "1":
            qs = qs.filter(status__in=Order.OPEN_STATUSES)
        return qs

    def create(self, request):
        ser = OrderCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        order, created = services.create_order(
            request.org, request.unit, request.user, items=d["items"], origin=d["origin"],
            table_label=d.get("table_label", ""), customer_name=d.get("customer_name", ""), notes=d.get("notes", ""),
            discount=d["discount"], delivery_fee=d["delivery_fee"], payment_method=d.get("payment_method", ""),
            client_reference=d.get("client_reference") or request.headers.get("Idempotency-Key"),
        )
        if created:
            audit(request, "create", order, summary=f"Pedido #{order.number} ({order.get_origin_display()})")
        return Response(self.get_serializer(self.get_queryset().get(pk=order.pk)).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        new_status = request.data.get("status")
        if new_status not in dict(Order.STATUS):
            raise BusinessError("Status inválido.")
        # Permissão por tipo de transição, sempre no backend.
        if new_status in KITCHEN_STATUSES:
            ok = self.has_perm("kitchen.update") or self.has_perm("orders.manage")
        else:
            ok = self.has_perm("orders.manage")
        if not ok:
            return Response({"detail": "Você não tem permissão para esta mudança de status."}, status=status.HTTP_403_FORBIDDEN)
        order = self.get_object()
        order = services.change_order_status(
            order, new_status, request.user, note=(request.data.get("note") or "").strip(),
            can_cancel_confirmed=self.has_perm("sales.cancel"), payment_method=request.data.get("payment_method") or None)
        audit(request, "status", order, summary=f"Pedido #{order.number}: {order.get_status_display()}")
        return Response(self.get_serializer(self.get_queryset().get(pk=order.pk)).data)

    @action(detail=False, methods=["get"])
    def board(self, request):
        """Painel da cozinha/salão: pedidos em aberto e uma versão para atualização incremental."""
        qs = self.get_queryset().filter(status__in=Order.OPEN_STATUSES).order_by("created_at")
        version = qs.order_by("-updated_at").values_list("updated_at", flat=True).first()
        latest_closed = Order.objects.filter(unit=request.unit).order_by("-updated_at").values_list("updated_at", flat=True).first()
        token = f"{qs.count()}:{(latest_closed or version).timestamp() if (latest_closed or version) else 0}"
        if request.query_params.get("version") == token:
            return Response({"version": token, "changed": False})
        data = self.get_serializer(qs, many=True).data
        columns = {"new": [], "preparing": [], "ready": [], "late": []}
        for o in data:
            if o["status"] in ("received", "confirmed"):
                columns["new"].append(o)
            elif o["status"] == "preparing":
                columns["preparing"].append(o)
            else:
                columns["ready"].append(o)
            if o["is_late"]:
                columns["late"].append(o["id"])
        return Response({"version": token, "changed": True, "columns": columns,
                         "slow_order_minutes": int(request.org.setting("slow_order_minutes"))})


class SaleViewSet(TenantMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SaleSerializer
    queryset = Sale.objects.select_related("order", "created_by").prefetch_related("items")
    unit_scoped = True
    required_permissions = {"create": "sales.manage", "import_csv": "sales.manage", "cancel": "sales.cancel",
                            "*": "sales.view"}
    filterset_fields = {"status": ["exact"], "channel": ["exact"], "source": ["exact"], "payment_method": ["exact"],
                        "stock_status": ["exact"]}
    search_fields = ["external_id", "items__description"]
    ordering_fields = ["occurred_at", "net_amount", "gross_amount"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("start") or p.get("end"):
            start, end = date_range(self.request)
            s, e = period_bounds(self.request.unit, start, end)
            qs = qs.filter(occurred_at__gte=s, occurred_at__lt=e)
        return qs

    def create(self, request):
        ser = SaleCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        items = [{"menu_item": i["menu_item"], "description": i["menu_item"].name, "quantity": i["quantity"],
                  "unit_price": i.get("unit_price", i["menu_item"].price), "discount": i["discount"]} for i in d["items"]]
        sale, created = services.register_sale(
            request.org, request.unit, request.user, items=items, channel=d["channel"],
            payment_method=d.get("payment_method", ""), discount=d["discount"], fee=d["fee"],
            occurred_at=d.get("occurred_at"), external_id=d.get("external_id") or request.headers.get("Idempotency-Key"),
        )
        if created:
            audit(request, "create", sale, summary=f"Venda #{sale.pk} registrada (R$ {sale.net_amount})")
        return Response(self.get_serializer(sale).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sale = services.cancel_sale(self.get_object(), request.user, (request.data.get("reason") or "").strip(),
                                    return_to_stock=bool(request.data.get("return_to_stock")))
        audit(request, "cancel", sale, summary=f"Venda #{sale.pk} cancelada: {sale.cancel_reason}")
        return Response(self.get_serializer(sale).data)

    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        f = request.FILES.get("file")
        if not f:
            raise BusinessError("Envie um arquivo CSV no campo 'file'.")
        if f.size > 5 * 1024 * 1024:
            raise BusinessError("Arquivo muito grande (máximo 5 MB).")
        try:
            batch = import_sales_csv(request.org, request.unit, request.user, f.read(), filename=f.name)
        except ValueError as exc:
            raise BusinessError(str(exc))
        audit(request, "import", batch, summary=f"Importação de vendas: {batch.sales_imported} novas, "
                                                f"{batch.sales_duplicated} já existentes")
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        start, end = date_range(request)
        s, e = period_bounds(request.unit, start, end)
        qs = Sale.objects.filter(unit=request.unit, occurred_at__gte=s, occurred_at__lt=e)
        done = qs.filter(status="completed")
        agg = done.aggregate(gross=Sum("gross_amount"), discount=Sum("discount_amount"), fees=Sum("fee_amount"),
                             delivery=Sum("delivery_fee"), net=Sum("net_amount"), cogs=Sum("cogs"), n=Count("id"))
        cancelled = qs.filter(status="cancelled").aggregate(v=Sum("gross_amount"), n=Count("id"))
        z = Decimal("0")
        net = agg["net"] or z
        return Response({
            "start": start, "end": end, "sales_count": agg["n"], "gross": agg["gross"] or z,
            "discounts": agg["discount"] or z, "fees": agg["fees"] or z, "delivery_fees": agg["delivery"] or z,
            "net": net, "cogs": agg["cogs"] or z, "cancelled_value": cancelled["v"] or z, "cancelled_count": cancelled["n"],
            "average_ticket": (net / agg["n"]).quantize(Decimal("0.01")) if agg["n"] else z,
            "by_channel": list(done.values("channel").annotate(net=Sum("net_amount"), n=Count("id")).order_by("-net")),
            "by_payment": list(done.values("payment_method").annotate(net=Sum("net_amount"), n=Count("id")).order_by("-net")),
            "without_recipe": qs.filter(Q(stock_status="partial")).count(),
        })


class PosMappingViewSet(TenantModelViewSet):
    serializer_class = PosMappingSerializer
    queryset = PosMapping.objects.select_related("menu_item")
    required_permissions = {"list": "sales.view", "*": "sales.manage"}
    search_fields = ["external_code", "external_name", "menu_item__name"]

    @action(detail=False, methods=["get"])
    def unmapped(self, request):
        codes = set()
        for b in ImportBatch.objects.filter(organization=request.org).order_by("-created_at")[:20]:
            codes.update(b.unmapped_codes)
        mapped = set(PosMapping.objects.filter(organization=request.org).values_list("external_code", flat=True))
        from apps.menu.models import MenuItem

        mapped |= set(MenuItem.objects.filter(organization=request.org).exclude(pos_code="").values_list("pos_code", flat=True))
        return Response(sorted(codes - mapped))


class ImportBatchViewSet(TenantMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ImportBatchSerializer
    queryset = ImportBatch.objects.select_related("user")
    unit_scoped = True
    required_permissions = "sales.view"
