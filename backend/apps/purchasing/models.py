from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel, Unit
from apps.inventory.models import MONEY, QTY, UNIT_COST, Product, StorageLocation, UnitOfMeasure


class Supplier(TenantModel):
    """Fornecedor. Compartilhado entre as unidades da organização."""

    name = models.CharField("nome/razão social", max_length=200)
    trade_name = models.CharField("nome fantasia", max_length=150, blank=True)
    cnpj = models.CharField(max_length=18, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    whatsapp = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    neighborhood = models.CharField("bairro", max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    categories = models.ManyToManyField("inventory.Category", blank=True, related_name="suppliers")
    min_order_value = models.DecimalField("pedido mínimo (R$)", **MONEY, default=0)
    payment_terms = models.CharField("condições de pagamento", max_length=120, blank=True)
    delivery_days = models.PositiveIntegerField("prazo de entrega (dias)", default=1)
    delivery_fee = models.DecimalField("taxa de entrega (R$)", **MONEY, default=0)
    quality_rating = models.PositiveSmallIntegerField(null=True, blank=True)  # 1..5, avaliação interna
    punctuality_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField("fictício (demonstração)", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.trade_name or self.name


class SupplierDocument(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=120)
    reference = models.CharField("número/link", max_length=255, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Quotation(TenantModel):
    """Cotação de um produto em um fornecedor, com data de referência obrigatória."""

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="quotations")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="quotations")
    price = models.DecimalField("preço por unidade de venda", **UNIT_COST)
    purchase_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="+")
    available_quantity = models.DecimalField(**QTY, null=True, blank=True)  # em unidades de venda
    min_quantity = models.DecimalField(**QTY, default=1)  # em unidades de venda
    freight = models.DecimalField("frete (R$)", **MONEY, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    valid_until = models.DateField(null=True, blank=True)
    delivery_days = models.PositiveIntegerField(null=True, blank=True)
    payment_terms = models.CharField(max_length=120, blank=True)
    brand = models.CharField(max_length=80, blank=True)
    product_expiry = models.DateField("validade do produto informada", null=True, blank=True)
    quoted_at = models.DateField("data da consulta")
    notes = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=20, default="manual")  # manual, import, api
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-quoted_at", "-id"]
        indexes = [models.Index(fields=["organization", "product", "quoted_at"])]


class PurchaseOrder(TenantModel):
    STATUS = [
        ("draft", "Rascunho"),
        ("pending_approval", "Aguardando aprovação"),
        ("approved", "Aprovado"),
        ("sent", "Enviado ao fornecedor"),
        ("partially_received", "Recebido parcialmente"),
        ("received", "Recebido"),
        ("cancelled", "Cancelado"),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="purchase_orders")
    number = models.PositiveIntegerField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    expected_delivery = models.DateField(null=True, blank=True)
    freight = models.DecimalField(**MONEY, default=0)
    discount = models.DecimalField(**MONEY, default=0)
    payment_terms = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=20, default="manual")  # manual, shopping_list
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sent_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "number"], name="uniq_po_number")]

    def __str__(self):
        return f"Pedido de compra #{self.number}"

    @property
    def items_total(self):
        return sum((i.total for i in self.items.all()), 0)

    @property
    def total(self):
        return self.items_total + self.freight - self.discount


class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quotation = models.ForeignKey(Quotation, null=True, blank=True, on_delete=models.SET_NULL)
    purchase_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(**QTY)  # em unidades de compra
    unit_price = models.DecimalField(**UNIT_COST)
    quantity_received = models.DecimalField(**QTY, default=0)
    notes = models.CharField(max_length=255, blank=True)

    @property
    def total(self):
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    @property
    def pending_quantity(self):
        return max(self.quantity - self.quantity_received, 0)


class Receipt(TenantModel):
    """Recebimento (total ou parcial) de um pedido de compra."""

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    document_number = models.CharField("nota fiscal", max_length=60, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    received_at = models.DateTimeField()
    total = models.DecimalField(**MONEY, default=0)
    idempotency_key = models.CharField(max_length=80, null=True, blank=True)
    operation = models.OneToOneField("inventory.StockOperation", null=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-received_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "idempotency_key"], name="uniq_receipt_key")]


class ReceiptItem(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="items")
    order_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.PROTECT, related_name="receipt_items")
    quantity = models.DecimalField(**QTY)  # em unidades de compra
    stock_quantity = models.DecimalField(**QTY)  # convertido para a unidade de estoque
    unit_price = models.DecimalField(**UNIT_COST)  # preço efetivo por unidade de compra
    lot_code = models.CharField(max_length=60, blank=True)
    manufactured_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    location = models.ForeignKey(StorageLocation, null=True, blank=True, on_delete=models.SET_NULL)
    lot = models.ForeignKey("inventory.Lot", null=True, blank=True, on_delete=models.SET_NULL)
    rejected_quantity = models.DecimalField(**QTY, default=0)
    notes = models.CharField(max_length=255, blank=True)


class PurchaseIssue(TenantModel):
    """Ocorrência/divergência no recebimento (quantidade, preço, qualidade, atraso)."""

    KINDS = [
        ("quantity", "Quantidade divergente"),
        ("price", "Preço divergente"),
        ("quality", "Qualidade/avaria"),
        ("expiry", "Validade curta"),
        ("late", "Atraso na entrega"),
        ("other", "Outro"),
    ]
    STATUS = [("open", "Aberta"), ("resolved", "Resolvida")]

    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="issues")
    receipt = models.ForeignKey(Receipt, null=True, blank=True, on_delete=models.SET_NULL, related_name="issues")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=20, choices=KINDS)
    description = models.TextField()
    expected = models.CharField(max_length=60, blank=True)
    actual = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    resolution = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ShoppingList(TenantModel):
    """Lista de compras gerada (e editável) a partir da projeção de estoque."""

    STATUS = [("open", "Em edição"), ("ordered", "Pedidos gerados"), ("archived", "Arquivada")]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    parameters = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ShoppingListItem(models.Model):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    suggested_quantity = models.DecimalField(**QTY)  # unidade de estoque
    quantity = models.DecimalField(**QTY)  # editável pelo usuário, unidade de estoque
    available_quantity = models.DecimalField(**QTY, default=0)
    forecast_consumption = models.DecimalField(**QTY, default=0)
    reorder_date = models.DateField(null=True, blank=True)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL)
    quotation = models.ForeignKey(Quotation, null=True, blank=True, on_delete=models.SET_NULL)
    estimated_cost = models.DecimalField(**MONEY, default=0)
    justification = models.TextField(blank=True)
    confidence = models.CharField(max_length=10, default="limited")  # good, limited
    selected = models.BooleanField(default=True)
