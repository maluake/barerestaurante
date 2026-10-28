from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.core.serializers import TenantSerializer

from .models import (
    Category,
    InventoryCount,
    InventoryCountItem,
    Lot,
    Product,
    ProductCostHistory,
    ProductPackaging,
    StockMovement,
    StorageLocation,
    Transfer,
    TransferItem,
    UnitOfMeasure,
    WasteRecord,
)


class UnitOfMeasureSerializer(TenantSerializer):
    is_global = serializers.SerializerMethodField()

    class Meta:
        model = UnitOfMeasure
        fields = ["id", "code", "name", "dimension", "factor_to_base", "is_global"]

    def get_is_global(self, obj):
        return obj.organization_id is None

    def validate(self, attrs):
        if attrs.get("dimension") != "package" and not attrs.get("factor_to_base"):
            raise serializers.ValidationError({"factor_to_base": "Informe o fator de conversão para a unidade base (g, ml ou un)."})
        if attrs.get("dimension") == "package":
            attrs["factor_to_base"] = None
        return attrs


class CategorySerializer(TenantSerializer):
    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ["id", "name", "kind", "product_count"]


class StorageLocationSerializer(TenantSerializer):
    class Meta:
        model = StorageLocation
        fields = ["id", "name", "kind", "capacity_note"]


class PackagingSerializer(TenantSerializer):
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    contained_unit_code = serializers.CharField(source="contained_unit.code", read_only=True)

    class Meta:
        model = ProductPackaging
        fields = ["id", "unit", "unit_code", "quantity", "contained_unit", "contained_unit_code"]

    def validate(self, attrs):
        if attrs["unit"].dimension != "package":
            raise serializers.ValidationError("A embalagem deve usar uma unidade do tipo embalagem (caixa, pacote...).")
        if attrs["contained_unit"].dimension == "package":
            raise serializers.ValidationError("O conteúdo da embalagem deve ser expresso em massa, volume ou contagem.")
        if attrs["quantity"] <= 0:
            raise serializers.ValidationError("A quantidade da embalagem deve ser maior que zero.")
        return attrs


class ProductSerializer(TenantSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    location_name = serializers.CharField(source="default_location.name", read_only=True, default=None)
    supplier_name = serializers.CharField(source="main_supplier.__str__", read_only=True, default=None)
    packagings = PackagingSerializer(many=True, required=False)
    quantity = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True, default=Decimal("0"))
    expired_quantity = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True, default=Decimal("0"))
    available_quantity = serializers.SerializerMethodField()
    stock_value = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    next_expiry = serializers.DateField(read_only=True, default=None)

    class Meta:
        model = Product
        fields = [
            "id", "name", "description", "category", "category_name", "brand", "sku", "barcode", "unit", "unit_code",
            "min_stock", "ideal_stock", "max_stock", "default_location", "location_name", "main_supplier",
            "supplier_name", "cost_price", "is_perishable", "shelf_life_days", "status", "created_at", "updated_at",
            "packagings", "quantity", "expired_quantity", "available_quantity", "stock_value", "stock_status",
            "next_expiry",
        ]
        read_only_fields = ["cost_price", "status", "created_at", "updated_at"]

    def get_available_quantity(self, obj):
        q = getattr(obj, "quantity", None) or Decimal("0")
        e = getattr(obj, "expired_quantity", None) or Decimal("0")
        return str((q - e).quantize(Decimal("0.0001")))

    def get_stock_value(self, obj):
        q = getattr(obj, "quantity", None) or Decimal("0")
        return str((max(q, Decimal("0")) * obj.cost_price).quantize(Decimal("0.01")))

    def get_stock_status(self, obj):
        q = (getattr(obj, "quantity", None) or Decimal("0")) - (getattr(obj, "expired_quantity", None) or Decimal("0"))
        if q <= 0:
            return "out"
        if obj.min_stock and q < obj.min_stock:
            return "low"
        return "ok"

    def validate_sku(self, value):
        org = self.context["org"]
        qs = Product.objects.filter(organization=org, sku__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Já existe um produto com este código interno.")
        return value

    def validate(self, attrs):
        min_s = attrs.get("min_stock", getattr(self.instance, "min_stock", 0)) or 0
        ideal = attrs.get("ideal_stock", getattr(self.instance, "ideal_stock", 0)) or 0
        max_s = attrs.get("max_stock", getattr(self.instance, "max_stock", None))
        if ideal and min_s and ideal < min_s:
            raise serializers.ValidationError({"ideal_stock": "O estoque ideal deve ser maior ou igual ao mínimo."})
        if max_s is not None and ideal and max_s < ideal:
            raise serializers.ValidationError({"max_stock": "A capacidade máxima deve ser maior ou igual ao estoque ideal."})
        if self.instance and "unit" in attrs and attrs["unit"] != self.instance.unit and self.instance.movements.exists():
            raise serializers.ValidationError({"unit": "Não é possível alterar a unidade de estoque de um produto com movimentações."})
        return attrs

    @transaction.atomic
    def create(self, validated):
        packagings = validated.pop("packagings", [])
        product = Product.objects.create(**validated)
        for p in packagings:
            ProductPackaging.objects.create(product=product, **p)
        return product

    @transaction.atomic
    def update(self, instance, validated):
        packagings = validated.pop("packagings", None)
        instance = super().update(instance, validated)
        if packagings is not None:
            instance.packagings.all().delete()
            for p in packagings:
                ProductPackaging.objects.create(product=instance, **p)
        return instance


class CostHistorySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", default=None, read_only=True)
    variation_percent = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = ProductCostHistory
        fields = ["id", "cost", "previous_cost", "variation_percent", "source", "reference", "user_name", "created_at"]


class LotSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    supplier_name = serializers.CharField(source="supplier.__str__", read_only=True, default=None)
    location_name = serializers.CharField(source="location.name", read_only=True, default=None)
    remaining_value = serializers.SerializerMethodField()
    days_to_expiry = serializers.SerializerMethodField()

    class Meta:
        model = Lot
        fields = [
            "id", "product", "product_name", "unit_code", "code", "quantity_received", "quantity_remaining",
            "received_at", "manufactured_at", "expires_at", "unit_cost", "supplier", "supplier_name", "document",
            "location", "location_name", "status", "source", "remaining_value", "days_to_expiry",
        ]

    def get_remaining_value(self, obj):
        return str((obj.quantity_remaining * obj.unit_cost).quantize(Decimal("0.01")))

    def get_days_to_expiry(self, obj):
        today = self.context.get("today")
        if not obj.expires_at or not today:
            return None
        return (obj.expires_at - today).days


class MovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    user_name = serializers.SerializerMethodField()
    lot_code = serializers.SerializerMethodField()
    counterpart_unit_name = serializers.CharField(source="counterpart_unit.name", read_only=True, default=None)
    operation_key = serializers.CharField(source="operation.key", read_only=True)
    reversed = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "product_name", "unit_code", "lot", "lot_code", "type", "type_label", "quantity",
            "unit_cost", "total_cost", "balance_after", "reason", "ref_type", "ref_id", "counterpart_unit_name",
            "user_name", "occurred_at", "operation", "operation_key", "reversal_of", "reversed",
        ]

    def get_user_name(self, obj):
        return (obj.user.get_full_name() or obj.user.username) if obj.user else "Sistema"

    def get_lot_code(self, obj):
        return (obj.lot.code or f"#{obj.lot_id}") if obj.lot_id else None

    def get_reversed(self, obj):
        return bool(obj.operation.reversed_by_id)


class StockEntrySerializer(serializers.Serializer):
    """Entrada manual (saldo inicial, devolução de cliente, bonificação)."""

    TYPES = [("initial", "Saldo inicial"), ("customer_return", "Devolução de cliente"), ("adjustment", "Bonificação/ajuste")]

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=16, decimal_places=4, min_value=Decimal("0.0001"))
    unit = serializers.PrimaryKeyRelatedField(queryset=UnitOfMeasure.objects.all(), required=False, allow_null=True)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0"), required=False)
    type = serializers.ChoiceField(choices=TYPES, default="initial")
    lot_code = serializers.CharField(required=False, allow_blank=True)
    expires_at = serializers.DateField(required=False, allow_null=True)
    manufactured_at = serializers.DateField(required=False, allow_null=True)
    location = serializers.PrimaryKeyRelatedField(queryset=StorageLocation.objects.all(), required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=80)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org:
            from django.db.models import Q

            self.fields["product"].queryset = Product.objects.filter(organization=org, status="active")
            self.fields["unit"].queryset = UnitOfMeasure.objects.filter(Q(organization=org) | Q(organization__isnull=True))
            self.fields["location"].queryset = StorageLocation.objects.filter(organization=org)


class WasteSerializer(TenantSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    category_name = serializers.CharField(source="product.category.name", read_only=True, default=None)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    user_name = serializers.SerializerMethodField()
    lot_code = serializers.SerializerMethodField()
    input_unit = serializers.PrimaryKeyRelatedField(queryset=UnitOfMeasure.objects.all(), write_only=True, required=False, allow_null=True)

    class Meta:
        model = WasteRecord
        fields = ["id", "product", "product_name", "category_name", "unit_code", "lot", "lot_code", "quantity",
                  "input_unit", "total_cost", "reason", "reason_label", "notes", "user_name", "occurred_at"]
        read_only_fields = ["total_cost", "occurred_at"]

    def get_user_name(self, obj):
        return (obj.user.get_full_name() or obj.user.username) if obj.user else "Sistema"

    def get_lot_code(self, obj):
        return (obj.lot.code or f"#{obj.lot_id}") if obj.lot_id else None

    def validate(self, attrs):
        if attrs["quantity"] <= 0:
            raise serializers.ValidationError({"quantity": "Informe uma quantidade maior que zero."})
        lot = attrs.get("lot")
        if lot and lot.product_id != attrs["product"].pk:
            raise serializers.ValidationError({"lot": "O lote não pertence ao produto informado."})
        unit = self.context.get("unit")
        if lot and unit and lot.unit_id != unit.pk:
            raise serializers.ValidationError({"lot": "O lote pertence a outra unidade."})
        return attrs


class InventoryCountItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    category_name = serializers.CharField(source="product.category.name", read_only=True, default=None)
    difference = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True)
    value_difference = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    counted_by_name = serializers.CharField(source="counted_by.username", read_only=True, default=None)

    class Meta:
        model = InventoryCountItem
        fields = ["id", "product", "product_name", "unit_code", "category_name", "system_quantity", "counted_quantity",
                  "difference", "unit_cost", "value_difference", "counted_by_name", "counted_at"]
        read_only_fields = ["product", "system_quantity", "unit_cost", "counted_at"]


class InventoryCountSerializer(TenantSerializer):
    items = InventoryCountItemSerializer(many=True, read_only=True)
    started_by_name = serializers.CharField(source="started_by.username", read_only=True, default=None)
    closed_by_name = serializers.CharField(source="closed_by.username", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    categories = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), many=True, write_only=True, required=False)
    products = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), many=True, write_only=True, required=False)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = InventoryCount
        fields = ["id", "status", "status_label", "description", "reason", "started_by_name", "started_at",
                  "closed_by_name", "closed_at", "items", "categories", "products", "summary"]
        read_only_fields = ["status", "started_at", "closed_at"]

    def get_summary(self, obj):
        items = list(obj.items.all())
        counted = [i for i in items if i.counted_quantity is not None]
        diffs = [i for i in counted if i.difference]
        return {
            "total_items": len(items),
            "counted_items": len(counted),
            "items_with_difference": len(diffs),
            "value_difference": str(sum((i.value_difference for i in counted), Decimal("0"))),
            "loss_value": str(sum((i.value_difference for i in counted if i.value_difference < 0), Decimal("0"))),
        }


class TransferItemSerializer(TenantSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)

    class Meta:
        model = TransferItem
        fields = ["id", "product", "product_name", "unit_code", "quantity", "total_cost"]
        read_only_fields = ["total_cost"]


class TransferSerializer(TenantSerializer):
    items = TransferItemSerializer(many=True)
    from_unit_name = serializers.CharField(source="from_unit.name", read_only=True)
    to_unit_name = serializers.CharField(source="to_unit.name", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True, default=None)

    class Meta:
        model = Transfer
        fields = ["id", "from_unit", "from_unit_name", "to_unit", "to_unit_name", "notes", "user_name", "created_at", "items"]
        read_only_fields = ["from_unit", "created_at"]
