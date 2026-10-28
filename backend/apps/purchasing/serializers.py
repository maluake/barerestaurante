from rest_framework import serializers

from apps.core.serializers import TenantSerializer

from .models import (
    PurchaseIssue,
    PurchaseOrder,
    PurchaseOrderItem,
    Quotation,
    Receipt,
    ReceiptItem,
    ShoppingList,
    ShoppingListItem,
    Supplier,
    SupplierDocument,
)


class SupplierDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierDocument
        fields = ["id", "title", "reference", "valid_until", "created_at"]


class SupplierSerializer(TenantSerializer):
    documents = SupplierDocumentSerializer(many=True, required=False)
    category_names = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Supplier
        fields = [
            "id", "name", "trade_name", "cnpj", "contact_name", "phone", "whatsapp", "email", "address", "neighborhood",
            "city", "state", "latitude", "longitude", "categories", "category_names", "min_order_value", "payment_terms",
            "delivery_days", "delivery_fee", "quality_rating", "punctuality_rating", "notes", "is_active", "is_demo",
            "created_at", "documents", "product_count",
        ]
        read_only_fields = ["is_demo", "created_at"]

    def get_category_names(self, obj):
        return [c.name for c in obj.categories.all()]

    def validate_cnpj(self, value):
        digits = "".join(ch for ch in value if ch.isdigit())
        if value and len(digits) != 14:
            raise serializers.ValidationError("CNPJ deve ter 14 dígitos.")
        if digits and not _valid_cnpj(digits):
            raise serializers.ValidationError("CNPJ inválido.")
        return value

    def validate(self, attrs):
        for f in ("quality_rating", "punctuality_rating"):
            v = attrs.get(f)
            if v is not None and not 1 <= v <= 5:
                raise serializers.ValidationError({f: "A avaliação deve ser de 1 a 5."})
        return attrs

    def create(self, validated):
        docs = validated.pop("documents", [])
        supplier = super().create(validated)
        for d in docs:
            SupplierDocument.objects.create(supplier=supplier, **d)
        return supplier

    def update(self, instance, validated):
        docs = validated.pop("documents", None)
        instance = super().update(instance, validated)
        if docs is not None:
            instance.documents.all().delete()
            for d in docs:
                SupplierDocument.objects.create(supplier=instance, **d)
        return instance


def _valid_cnpj(digits):
    if len(set(digits)) == 1:
        return False

    def calc(base, weights):
        s = sum(int(d) * w for d, w in zip(base, weights, strict=False))
        r = s % 11
        return "0" if r < 2 else str(11 - r)

    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6] + w1
    d1 = calc(digits[:12], w1)
    d2 = calc(digits[:12] + d1, w2)
    return digits[-2:] == d1 + d2


class QuotationSerializer(TenantSerializer):
    supplier_name = serializers.CharField(source="supplier.__str__", read_only=True)
    supplier_is_demo = serializers.BooleanField(source="supplier.is_demo", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_unit = serializers.CharField(source="product.unit.code", read_only=True)
    purchase_unit_code = serializers.CharField(source="purchase_unit.code", read_only=True)
    age_days = serializers.SerializerMethodField()
    is_stale = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            "id", "supplier", "supplier_name", "supplier_is_demo", "product", "product_name", "product_unit", "price",
            "purchase_unit", "purchase_unit_code", "available_quantity", "min_quantity", "freight", "discount_percent",
            "valid_until", "delivery_days", "payment_terms", "brand", "product_expiry", "quoted_at", "notes", "source",
            "age_days", "is_stale", "is_expired", "created_at",
        ]
        read_only_fields = ["source", "created_at"]

    def _today(self):
        from django.utils import timezone

        return timezone.localdate()

    def get_age_days(self, obj):
        return (self._today() - obj.quoted_at).days

    def get_is_stale(self, obj):
        org = self.context.get("org")
        limit = int(org.setting("stale_quote_days")) if org else 7
        return self.get_age_days(obj) > limit

    def get_is_expired(self, obj):
        return bool(obj.valid_until and obj.valid_until < self._today())

    def validate(self, attrs):
        from apps.inventory.units import IncompatibleUnits, convert

        product = attrs.get("product", getattr(self.instance, "product", None))
        unit = attrs.get("purchase_unit", getattr(self.instance, "purchase_unit", None))
        try:
            convert(1, unit, product.unit, product)
        except IncompatibleUnits as exc:
            raise serializers.ValidationError({"purchase_unit": exc.message})
        if attrs.get("price") is not None and attrs["price"] <= 0:
            raise serializers.ValidationError({"price": "O preço deve ser maior que zero."})
        if attrs.get("discount_percent") is not None and not 0 <= attrs["discount_percent"] < 100:
            raise serializers.ValidationError({"discount_percent": "Desconto deve estar entre 0 e 100%."})
        if attrs.get("quoted_at") and attrs["quoted_at"] > self._today():
            raise serializers.ValidationError({"quoted_at": "A data da consulta não pode estar no futuro."})
        return attrs


class PurchaseOrderItemSerializer(TenantSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_unit = serializers.CharField(source="product.unit.code", read_only=True)
    is_perishable = serializers.BooleanField(source="product.is_perishable", read_only=True)
    purchase_unit_code = serializers.CharField(source="purchase_unit.code", read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    pending_quantity = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "product", "product_name", "product_unit", "is_perishable", "quotation", "purchase_unit",
                  "purchase_unit_code", "quantity", "unit_price", "quantity_received", "pending_quantity", "total", "notes"]
        read_only_fields = ["quantity_received"]


class PurchaseIssueSerializer(TenantSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True, default=None)
    order_number = serializers.IntegerField(source="order.number", read_only=True)
    supplier_name = serializers.CharField(source="order.supplier.__str__", read_only=True)

    class Meta:
        model = PurchaseIssue
        fields = ["id", "order", "order_number", "supplier_name", "receipt", "product", "product_name", "kind",
                  "kind_label", "description", "expected", "actual", "status", "resolution", "created_at", "resolved_at"]
        read_only_fields = ["status", "resolved_at", "created_at"]


class ReceiptItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="order_item.product.name", read_only=True)
    purchase_unit_code = serializers.CharField(source="order_item.purchase_unit.code", read_only=True)

    class Meta:
        model = ReceiptItem
        fields = ["id", "order_item", "product_name", "purchase_unit_code", "quantity", "stock_quantity", "unit_price",
                  "rejected_quantity", "lot_code", "manufactured_at", "expires_at", "lot", "notes"]


class ReceiptSerializer(serializers.ModelSerializer):
    items = ReceiptItemSerializer(many=True, read_only=True)
    received_by_name = serializers.CharField(source="received_by.username", read_only=True, default=None)

    class Meta:
        model = Receipt
        fields = ["id", "document_number", "notes", "received_by_name", "received_at", "total", "items"]


class PurchaseOrderSerializer(TenantSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.__str__", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    items_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    receipts = ReceiptSerializer(many=True, read_only=True)
    issues = PurchaseIssueSerializer(many=True, read_only=True)
    history = serializers.SerializerMethodField()
    is_late = serializers.SerializerMethodField()
    needs_approval = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "number", "supplier", "supplier_name", "status", "status_label", "expected_delivery", "freight",
            "discount", "payment_terms", "notes", "source", "items", "items_total", "total", "receipts", "issues",
            "history", "is_late", "needs_approval", "created_at",
        ]
        read_only_fields = ["number", "status", "source", "created_at"]

    def get_history(self, obj):
        def name(u):
            return (u.get_full_name() or u.username) if u else None

        events = [("Criado", obj.created_at, name(obj.created_by))]
        if obj.submitted_at:
            events.append(("Enviado para aprovação", obj.submitted_at, name(obj.created_by)))
        if obj.approved_at:
            events.append(("Aprovado", obj.approved_at, name(obj.approved_by)))
        if obj.sent_at:
            events.append(("Enviado ao fornecedor", obj.sent_at, name(obj.sent_by)))
        for r in obj.receipts.all():
            events.append((f"Recebimento (NF {r.document_number or 's/n'})", r.received_at, name(r.received_by)))
        if obj.cancelled_at:
            events.append((f"Cancelado: {obj.cancel_reason}", obj.cancelled_at, name(obj.cancelled_by)))
        return [{"label": l, "at": a, "user": u} for l, a, u in sorted(events, key=lambda e: e[1])]

    def get_is_late(self, obj):
        from django.utils import timezone

        return bool(obj.status in ("sent", "approved", "partially_received") and obj.expected_delivery
                    and obj.expected_delivery < timezone.localdate())

    def get_needs_approval(self, obj):
        from decimal import Decimal

        return obj.total > Decimal(str(obj.organization.setting("purchase_approval_threshold")))


class ShoppingListItemSerializer(TenantSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_unit = serializers.CharField(source="product.unit.code", read_only=True)
    supplier_name = serializers.CharField(source="supplier.__str__", read_only=True, default=None)
    min_stock = serializers.DecimalField(source="product.min_stock", max_digits=16, decimal_places=4, read_only=True)

    class Meta:
        model = ShoppingListItem
        fields = ["id", "product", "product_name", "product_unit", "min_stock", "suggested_quantity", "quantity",
                  "available_quantity", "forecast_consumption", "reorder_date", "supplier", "supplier_name", "quotation",
                  "estimated_cost", "justification", "confidence", "selected"]
        read_only_fields = ["product", "suggested_quantity", "available_quantity", "forecast_consumption", "reorder_date",
                            "estimated_cost", "justification", "confidence"]


class ShoppingListSerializer(TenantSerializer):
    items = ShoppingListItemSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default=None)
    total = serializers.SerializerMethodField()

    class Meta:
        model = ShoppingList
        fields = ["id", "status", "created_by_name", "created_at", "parameters", "items", "total"]

    def get_total(self, obj):
        return str(sum((i.estimated_cost for i in obj.items.all() if i.selected), 0))
