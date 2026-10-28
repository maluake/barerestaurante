from django.conf import settings
from django.db import models

from apps.core.models import TenantModel, Unit
from apps.inventory.models import MONEY, UNIT_COST
from apps.menu.models import MenuItem

ORIGINS = [
    ("counter", "Balcão"),
    ("table", "Mesa"),
    ("takeout", "Retirada"),
    ("delivery", "Entrega própria"),
    ("app", "Aplicativo de entrega"),
]

PAYMENT_METHODS = [
    ("cash", "Dinheiro"),
    ("pix", "Pix"),
    ("debit", "Cartão de débito"),
    ("credit", "Cartão de crédito"),
    ("voucher", "Vale-refeição"),
    ("app", "Pago no aplicativo"),
    ("other", "Outro"),
]

STOCK_STATUS = [
    ("pending", "Aguardando confirmação"),
    ("consumed", "Ingredientes baixados"),
    ("partial", "Baixa parcial (item sem ficha técnica)"),
    ("reversed", "Estornado"),
    ("wasted", "Convertido em perda"),
    ("not_applicable", "Sem baixa automática"),
]


class Order(TenantModel):
    STATUS = [
        ("received", "Recebido"),
        ("confirmed", "Confirmado"),
        ("preparing", "Em preparo"),
        ("ready", "Pronto"),
        ("dispatched", "Saiu para entrega"),
        ("delivered", "Entregue"),
        ("cancelled", "Cancelado"),
    ]
    OPEN_STATUSES = ("received", "confirmed", "preparing", "ready", "dispatched")

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="orders")
    number = models.PositiveIntegerField()
    origin = models.CharField(max_length=10, choices=ORIGINS, default="counter")
    table_label = models.CharField("mesa/identificação", max_length=40, blank=True)
    customer_name = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="received", db_index=True)
    discount = models.DecimalField(**MONEY, default=0)
    delivery_fee = models.DecimalField(**MONEY, default=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, blank=True)
    subtotal = models.DecimalField(**MONEY, default=0)
    total = models.DecimalField(**MONEY, default=0)
    stock_status = models.CharField(max_length=15, choices=STOCK_STATUS, default="pending")
    stock_operation = models.ForeignKey("inventory.StockOperation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    client_reference = models.CharField(max_length=80, null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    preparing_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_order_number"),
            models.UniqueConstraint(fields=["organization", "client_reference"], name="uniq_order_client_ref"),
        ]

    def __str__(self):
        return f"Pedido #{self.number}"

    @property
    def requires_kitchen(self):
        return any(i.menu_item.requires_preparation for i in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(**MONEY)
    notes = models.CharField(max_length=255, blank=True)
    stock_warning = models.CharField(max_length=255, blank=True)

    @property
    def total(self):
        return self.quantity * self.unit_price


class OrderEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12)
    note = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["created_at", "id"]


class Sale(TenantModel):
    """Venda concluída (receita). Pode vir de um pedido, de registro direto ou importação."""

    SOURCES = [("order", "Pedido"), ("direct", "Registro direto"), ("csv", "Importação CSV"), ("pos", "Integração PDV")]
    STATUS = [("completed", "Concluída"), ("cancelled", "Cancelada")]
    CHANNELS = ORIGINS

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="sales")
    order = models.OneToOneField(Order, null=True, blank=True, on_delete=models.PROTECT, related_name="sale")
    source = models.CharField(max_length=10, choices=SOURCES)
    external_id = models.CharField("identificador único externo", max_length=80, null=True, blank=True)
    channel = models.CharField(max_length=10, choices=ORIGINS, default="counter")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    # Faturamento bruto = soma de quantidade × preço de tabela dos itens.
    gross_amount = models.DecimalField(**MONEY, default=0)
    discount_amount = models.DecimalField(**MONEY, default=0)
    # Taxas pagas pelo estabelecimento (aplicativos, adquirentes) quando informadas.
    fee_amount = models.DecimalField(**MONEY, default=0)
    # Taxa de entrega cobrada do cliente (receita acessória).
    delivery_fee = models.DecimalField(**MONEY, default=0)
    # Receita líquida = bruto − descontos − taxas + taxa de entrega.
    net_amount = models.DecimalField(**MONEY, default=0)
    cogs = models.DecimalField("CMV real (custo dos lotes consumidos)", **MONEY, default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="completed", db_index=True)
    stock_status = models.CharField(max_length=15, choices=STOCK_STATUS, default="pending")
    stock_operation = models.ForeignKey("inventory.StockOperation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cancel_reason = models.CharField(max_length=255, blank=True)
    import_batch = models.ForeignKey("ImportBatch", null=True, blank=True, on_delete=models.SET_NULL, related_name="sales")

    class Meta:
        ordering = ["-occurred_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "source", "external_id"], name="uniq_sale_external_id"),
        ]


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField(max_length=150)
    external_code = models.CharField(max_length=60, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(**MONEY)
    discount = models.DecimalField(**MONEY, default=0)
    total = models.DecimalField(**MONEY)
    theoretical_cost = models.DecimalField(**UNIT_COST, default=0)
    stock_warning = models.CharField(max_length=255, blank=True)


class PosMapping(TenantModel):
    """Mapeia o código de um produto no PDV/planilha para um item do cardápio."""

    source = models.CharField(max_length=30, default="csv")
    external_code = models.CharField(max_length=60)
    external_name = models.CharField(max_length=150, blank=True)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="pos_mappings")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "source", "external_code"], name="uniq_pos_mapping")]


class ImportBatch(TenantModel):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    source = models.CharField(max_length=30, default="csv")
    filename = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    rows_total = models.PositiveIntegerField(default=0)
    sales_imported = models.PositiveIntegerField(default=0)
    sales_duplicated = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    unmapped_codes = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]

