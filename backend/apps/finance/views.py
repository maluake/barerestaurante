from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessError
from apps.core.serializers import TenantSerializer
from apps.core.tenancy import TenantMixin, TenantModelViewSet, audit
from apps.inventory.services import today_for

from . import services
from .models import CashMovement, CashSession, ExpenseCategory, FinancialEntry


class ExpenseCategorySerializer(TenantSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "kind", "kind_label"]


class FinancialEntrySerializer(TenantSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_kind = serializers.CharField(source="category.kind", read_only=True)
    supplier_name = serializers.CharField(source="supplier.__str__", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    is_overdue = serializers.SerializerMethodField()
    purchase_order_number = serializers.IntegerField(source="purchase_order.number", read_only=True, default=None)

    class Meta:
        model = FinancialEntry
        fields = ["id", "kind", "category", "category_name", "category_kind", "description", "amount", "competence_date",
                  "due_date", "status", "status_label", "paid_at", "paid_amount", "payment_method", "supplier",
                  "supplier_name", "purchase_order", "purchase_order_number", "document", "notes", "is_overdue", "created_at"]
        read_only_fields = ["status", "paid_at", "paid_amount", "purchase_order", "created_at"]

    def get_is_overdue(self, obj):
        return obj.status == "open" and obj.due_date < timezone.localdate()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("O valor deve ser maior que zero.")
        return value


class CashMovementSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True, default=None)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = CashMovement
        fields = ["id", "kind", "kind_label", "amount", "reason", "user_name", "created_at"]


class CashSessionSerializer(serializers.ModelSerializer):
    movements = CashMovementSerializer(many=True, read_only=True)
    opened_by_name = serializers.CharField(source="opened_by.username", read_only=True, default=None)
    closed_by_name = serializers.CharField(source="closed_by.username", read_only=True, default=None)
    difference = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    breakdown = serializers.SerializerMethodField()

    class Meta:
        model = CashSession
        fields = ["id", "status", "opened_by_name", "opened_at", "opening_amount", "closed_by_name", "closed_at",
                  "expected_amount", "counted_amount", "difference", "notes", "movements", "breakdown"]

    def get_breakdown(self, obj):
        return services.expected_cash(obj)


def parse_period(request):
    today = today_for(request.unit)
    p = request.query_params
    start = date.fromisoformat(p["start"]) if p.get("start") else today.replace(day=1)
    end = date.fromisoformat(p["end"]) if p.get("end") else today
    if end < start:
        raise BusinessError("A data final deve ser posterior à inicial.")
    return start, end


def scope_units(request):
    """Unidade ativa ou, com ?scope=all e permissão, todas as unidades permitidas (visão consolidada)."""
    if request.query_params.get("scope") == "all":
        return list(request.membership.allowed_units())
    return [request.unit]


class ExpenseCategoryViewSet(TenantModelViewSet):
    serializer_class = ExpenseCategorySerializer
    queryset = ExpenseCategory.objects.all()
    pagination_class = None
    required_permissions = {"list": "finance.view", "*": "finance.manage"}


class FinancialEntryViewSet(TenantModelViewSet):
    serializer_class = FinancialEntrySerializer
    queryset = FinancialEntry.objects.select_related("category", "supplier", "purchase_order")
    unit_scoped = True
    required_permissions = {"list": "finance.view", "retrieve": "finance.view", "*": "finance.manage"}
    filterset_fields = {"kind": ["exact"], "status": ["exact"], "category": ["exact"], "category__kind": ["exact"],
                        "supplier": ["exact"]}
    search_fields = ["description", "document", "supplier__name"]
    ordering_fields = ["due_date", "amount", "competence_date"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("start"):
            qs = qs.filter(due_date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(due_date__lte=p["end"])
        if p.get("overdue") == "1":
            qs = qs.filter(status="open", due_date__lt=timezone.localdate())
        return qs

    def perform_create(self, serializer):
        obj = serializer.save(organization=self.request.org, unit=self.request.unit, created_by=self.request.user)
        audit(self.request, "create", obj, summary=f"{obj.get_kind_display()}: {obj.description} R$ {obj.amount}")

    def perform_update(self, serializer):
        if serializer.instance.status != "open":
            raise BusinessError("Lançamentos pagos ou cancelados não podem ser editados. Estorne o pagamento antes.")
        super().perform_update(serializer)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        with transaction.atomic():
            entry = FinancialEntry.objects.select_for_update().get(pk=self.get_object().pk)
            if entry.status != "open":
                raise BusinessError("Este lançamento não está em aberto.")
            entry.status = "paid"
            entry.paid_at = date.fromisoformat(request.data["paid_at"]) if request.data.get("paid_at") else timezone.localdate()
            entry.paid_amount = Decimal(str(request.data.get("paid_amount") or entry.amount))
            entry.payment_method = request.data.get("payment_method", "")[:20]
            entry.save()
        audit(request, "pay", entry, summary=f"Pagamento de {entry.description}: R$ {entry.paid_amount}")
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        entry = self.get_object()
        if entry.status != "paid":
            raise BusinessError("Somente lançamentos pagos podem ser reabertos.")
        before = [str(entry.paid_at), str(entry.paid_amount)]
        entry.status, entry.paid_at, entry.paid_amount = "open", None, None
        entry.save()
        audit(request, "reopen", entry, summary=f"Pagamento estornado: {entry.description}", changes={"paid": before})
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        entry = self.get_object()
        if entry.status == "paid":
            raise BusinessError("Estorne o pagamento antes de cancelar.")
        entry.status = "cancelled"
        entry.notes = (entry.notes + f"\nCancelado: {request.data.get('reason', '')}").strip()
        entry.save()
        audit(request, "cancel", entry, summary=f"Lançamento cancelado: {entry.description}")
        return Response(self.get_serializer(entry).data)


class SummaryView(TenantMixin, APIView):
    required_permissions = "finance.view"

    def get(self, request):
        start, end = parse_period(request)
        data = services.financial_summary(request.org, scope_units(request), start, end)
        # Comparação com o período anterior de mesma duração
        length = (end - start).days + 1
        from datetime import timedelta

        prev = services.financial_summary(request.org, scope_units(request), start - timedelta(days=length), start - timedelta(days=1))
        data["previous"] = {k: prev[k] for k in ("gross", "net", "cogs", "contribution_margin", "sales_count",
                                                  "registered_expenses", "operating_result_estimate")}
        return Response(data)


class CashFlowView(TenantMixin, APIView):
    required_permissions = "finance.view"

    def get(self, request):
        start, end = parse_period(request)
        return Response(services.cash_flow(request.org, scope_units(request), start, end))


class CashSessionViewSet(TenantMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = CashSessionSerializer
    queryset = CashSession.objects.select_related("opened_by", "closed_by").prefetch_related("movements__user")
    unit_scoped = True
    required_permissions = {"list": "finance.view", "retrieve": "finance.view", "current": "finance.view", "*": "finance.manage"}

    @action(detail=False, methods=["get"])
    def current(self, request):
        s = self.get_queryset().filter(status="open").first()
        return Response(self.get_serializer(s).data if s else None)

    @action(detail=False, methods=["post"])
    def open(self, request):
        try:
            amount = Decimal(str(request.data.get("opening_amount", "0")))
        except Exception:
            raise BusinessError("Valor de abertura inválido.")
        if amount < 0:
            raise BusinessError("Valor de abertura inválido.")
        try:
            with transaction.atomic():
                s = CashSession.objects.create(organization=request.org, unit=request.unit, opened_by=request.user,
                                               opened_at=timezone.now(), opening_amount=amount,
                                               notes=request.data.get("notes", ""))
        except IntegrityError:
            raise BusinessError("Já existe um caixa aberto nesta unidade.")
        audit(request, "open", s, summary=f"Caixa aberto com R$ {amount}")
        return Response(self.get_serializer(s).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def movement(self, request, pk=None):
        s = self.get_object()
        if s.status != "open":
            raise BusinessError("O caixa está fechado.")
        kind = request.data.get("kind")
        if kind not in ("supply", "withdrawal"):
            raise BusinessError("Tipo inválido.")
        amount = Decimal(str(request.data.get("amount", "0")))
        if amount <= 0:
            raise BusinessError("Informe um valor maior que zero.")
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            raise BusinessError("Informe o motivo.", field="reason")
        CashMovement.objects.create(session=s, kind=kind, amount=amount, reason=reason, user=request.user)
        audit(request, kind, s, summary=f"{'Suprimento' if kind == 'supply' else 'Sangria'} R$ {amount}: {reason}")
        return Response(self.get_serializer(s).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        with transaction.atomic():
            s = CashSession.objects.select_for_update().get(pk=self.get_object().pk)
            if s.status != "open":
                raise BusinessError("Este caixa já foi fechado.")
            try:
                counted = Decimal(str(request.data.get("counted_amount")))
            except Exception:
                raise BusinessError("Informe o valor contado na gaveta.", field="counted_amount")
            s.closed_at = timezone.now()
            s.expected_amount = services.expected_cash(s)["expected"]
            s.counted_amount = counted
            s.closed_by = request.user
            s.status = "closed"
            s.notes = (s.notes + "\n" + request.data.get("notes", "")).strip()
            s.save()
        audit(request, "close", s, summary=f"Caixa fechado. Esperado R$ {s.expected_amount}, contado R$ {counted}")
        return Response(self.get_serializer(s).data)
