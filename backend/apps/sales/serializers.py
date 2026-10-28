from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.core.serializers import TenantSerializer
from apps.menu.models import MenuItem

from .models import ORIGINS, PAYMENT_METHODS, ImportBatch, Order, OrderEvent, OrderItem, PosMapping, Sale, SaleItem
from .services import allowed_transitions


class OrderItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="menu_item.name", read_only=True)
    requires_preparation = serializers.BooleanField(source="menu_item.requires_preparation", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "menu_item", "name", "quantity", "unit_price", "notes", "stock_warning", "requires_preparation"]


class OrderEventSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True, default=None)

    class Meta:
        model = OrderEvent
        fields = ["from_status", "to_status", "note", "user_name", "created_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    events = OrderEventSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    origin_label = serializers.CharField(source="get_origin_display", read_only=True)
    stock_status_label = serializers.CharField(source="get_stock_status_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default=None)
    elapsed_minutes = serializers.SerializerMethodField()
    is_late = serializers.SerializerMethodField()
    next_statuses = serializers.SerializerMethodField()
    sale_id = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "number", "origin", "origin_label", "table_label", "customer_name", "notes", "status", "status_label",
            "discount", "delivery_fee", "payment_method", "subtotal", "total", "stock_status", "stock_status_label",
            "created_by_name", "created_at", "confirmed_at", "preparing_at", "ready_at", "delivered_at", "cancelled_at",
            "cancel_reason", "elapsed_minutes", "is_late", "next_statuses", "items", "events", "sale_id", "updated_at",
        ]

    def get_elapsed_minutes(self, obj):
        end = obj.delivered_at or obj.cancelled_at or timezone.now()
        return int((end - obj.created_at).total_seconds() // 60)

    def get_is_late(self, obj):
        if obj.status not in ("received", "confirmed", "preparing"):
            return False
        limit = int(obj.organization.setting("slow_order_minutes"))
        return self.get_elapsed_minutes(obj) > limit

    def get_next_statuses(self, obj):
        order = ["confirmed", "preparing", "ready", "dispatched", "delivered", "cancelled"]
        allowed = allowed_transitions(obj)
        return [s for s in order if s in allowed]

    def get_sale_id(self, obj):
        sale = getattr(obj, "sale", None)
        return sale.pk if sale else None


class OrderLineInput(serializers.Serializer):
    menu_item = serializers.PrimaryKeyRelatedField(queryset=MenuItem.objects.all())
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    notes = serializers.CharField(required=False, allow_blank=True, max_length=255)


class OrderCreateSerializer(serializers.Serializer):
    origin = serializers.ChoiceField(choices=ORIGINS, default="counter")
    table_label = serializers.CharField(required=False, allow_blank=True, max_length=40)
    customer_name = serializers.CharField(required=False, allow_blank=True, max_length=80)
    notes = serializers.CharField(required=False, allow_blank=True)
    discount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    delivery_fee = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    payment_method = serializers.ChoiceField(choices=PAYMENT_METHODS, required=False, allow_blank=True)
    client_reference = serializers.CharField(required=False, allow_blank=True, max_length=80)
    items = OrderLineInput(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["items"].child.fields["menu_item"].queryset = MenuItem.objects.filter(organization=org, status="active")

    def validate(self, attrs):
        if attrs["origin"] == "table" and not attrs.get("table_label"):
            raise serializers.ValidationError({"table_label": "Informe a mesa."})
        return attrs


class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = ["id", "menu_item", "description", "external_code", "quantity", "unit_price", "discount", "total",
                  "theoretical_cost", "stock_warning"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    stock_status_label = serializers.CharField(source="get_stock_status_display", read_only=True)
    payment_label = serializers.CharField(source="get_payment_method_display", read_only=True)
    order_number = serializers.IntegerField(source="order.number", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default=None)

    class Meta:
        model = Sale
        fields = [
            "id", "order", "order_number", "source", "source_label", "external_id", "channel", "channel_label",
            "payment_method", "payment_label", "occurred_at", "gross_amount", "discount_amount", "fee_amount",
            "delivery_fee", "net_amount", "cogs", "status", "status_label", "stock_status", "stock_status_label",
            "created_by_name", "cancelled_at", "cancel_reason", "items",
        ]


class SaleLineInput(serializers.Serializer):
    menu_item = serializers.PrimaryKeyRelatedField(queryset=MenuItem.objects.all())
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False)
    discount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))


class SaleCreateSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=ORIGINS, default="counter")
    payment_method = serializers.ChoiceField(choices=PAYMENT_METHODS, required=False, allow_blank=True)
    discount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    fee = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    external_id = serializers.CharField(required=False, allow_blank=True, max_length=80)
    occurred_at = serializers.DateTimeField(required=False)
    items = SaleLineInput(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["items"].child.fields["menu_item"].queryset = MenuItem.objects.filter(organization=org)


class PosMappingSerializer(TenantSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)

    class Meta:
        model = PosMapping
        fields = ["id", "source", "external_code", "external_name", "menu_item", "menu_item_name"]


class ImportBatchSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True, default=None)

    class Meta:
        model = ImportBatch
        fields = ["id", "source", "filename", "user_name", "created_at", "rows_total", "sales_imported",
                  "sales_duplicated", "rows_failed", "errors", "unmapped_codes"]
