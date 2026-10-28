from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel, Unit

QTY = {"max_digits": 16, "decimal_places": 4}
MONEY = {"max_digits": 14, "decimal_places": 2}
UNIT_COST = {"max_digits": 14, "decimal_places": 4}


class UnitOfMeasure(models.Model):
    """Unidade de medida. Unidades globais têm `organization` nulo.

    Conversões só ocorrem dentro da mesma dimensão (massa, volume, contagem) usando
    `factor_to_base`. Embalagens (caixa, pacote...) não têm fator fixo: a conversão
    exige um cadastro de embalagem por produto (`ProductPackaging`).
    """

    DIMENSIONS = [("mass", "Massa"), ("volume", "Volume"), ("count", "Contagem"), ("package", "Embalagem")]

    organization = models.ForeignKey("core.Organization", null=True, blank=True, on_delete=models.CASCADE)
    code = models.CharField(max_length=12)
    name = models.CharField(max_length=40)
    dimension = models.CharField(max_length=10, choices=DIMENSIONS)
    factor_to_base = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["dimension", "factor_to_base", "code"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="uniq_uom_code", nulls_distinct=False)]

    def __str__(self):
        return self.code


class Category(TenantModel):
    KINDS = [("ingredient", "Ingrediente"), ("beverage", "Bebida"), ("supply", "Descartável/limpeza"), ("other", "Outro")]

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=20, choices=KINDS, default="ingredient")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="uniq_category_name")]

    def __str__(self):
        return self.name


class StorageLocation(TenantModel):
    KINDS = [("dry", "Seco"), ("chilled", "Refrigerado"), ("frozen", "Congelado"), ("bar", "Bar"), ("other", "Outro")]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="locations")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=KINDS, default="dry")
    capacity_note = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TenantModel):
    STATUS = [("active", "Ativo"), ("archived", "Arquivado")]

    name = models.CharField("nome", max_length=150)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    brand = models.CharField(max_length=80, blank=True)
    sku = models.CharField("código interno", max_length=40)
    barcode = models.CharField(max_length=40, blank=True)
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="+", verbose_name="unidade de estoque")
    min_stock = models.DecimalField(**QTY, default=0)
    ideal_stock = models.DecimalField(**QTY, default=0)
    max_stock = models.DecimalField("capacidade máxima", **QTY, null=True, blank=True)
    default_location = models.ForeignKey(StorageLocation, null=True, blank=True, on_delete=models.SET_NULL)
    main_supplier = models.ForeignKey(
        "purchasing.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="main_products"
    )
    cost_price = models.DecimalField("custo de reposição por unidade", **UNIT_COST, default=0)
    is_perishable = models.BooleanField(default=False)
    shelf_life_days = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "sku"], name="uniq_product_sku")]

    def __str__(self):
        return self.name


class ProductPackaging(models.Model):
    """Ex.: 1 caixa deste produto = 12 un; 1 saco = 25 kg. Definido por produto."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="packagings")
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(**QTY)
    contained_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "unit"], name="uniq_packaging")]


class ProductCostHistory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cost_history")
    cost = models.DecimalField(**UNIT_COST)
    previous_cost = models.DecimalField(**UNIT_COST, default=0)
    source = models.CharField(max_length=20)  # receipt, manual, initial
    reference = models.CharField(max_length=60, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def variation_percent(self):
        if not self.previous_cost:
            return None
        return (self.cost - self.previous_cost) / self.previous_cost * 100


class StockBalance(TenantModel):
    """Saldo físico por unidade e produto (inclui lotes vencidos ainda não descartados)."""

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="balances")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="balances")
    quantity = models.DecimalField(**QTY, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["unit", "product"], name="uniq_balance")]


class Lot(TenantModel):
    STATUS = [("active", "Ativo"), ("depleted", "Esgotado"), ("discarded", "Descartado")]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="lots")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="lots")
    code = models.CharField("código do lote", max_length=60, blank=True)
    quantity_received = models.DecimalField(**QTY)
    quantity_remaining = models.DecimalField(**QTY)
    received_at = models.DateField()
    manufactured_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True, db_index=True)
    unit_cost = models.DecimalField(**UNIT_COST)
    supplier = models.ForeignKey("purchasing.Supplier", null=True, blank=True, on_delete=models.SET_NULL)
    document = models.CharField("nota fiscal/documento", max_length=60, blank=True)
    location = models.ForeignKey(StorageLocation, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    source = models.CharField(max_length=20, default="receipt")  # receipt, adjustment, transfer, initial
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expires_at", "received_at", "id"]

    def __str__(self):
        return f"{self.product} · lote {self.code or self.pk}"


class StockOperation(TenantModel):
    """Operação idempotente de estoque. A chave única impede o processamento duplicado."""

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    key = models.CharField(max_length=120)
    kind = models.CharField(max_length=30)
    description = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reversed_by = models.OneToOneField("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reverses")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="uniq_stock_operation_key")]


class StockMovement(TenantModel):
    TYPES = [
        ("receipt", "Recebimento de compra"),
        ("sale", "Venda"),
        ("production", "Consumo na produção"),
        ("loss", "Perda"),
        ("discard", "Descarte"),
        ("adjustment", "Ajuste de inventário"),
        ("transfer_out", "Transferência (saída)"),
        ("transfer_in", "Transferência (entrada)"),
        ("supplier_return", "Devolução ao fornecedor"),
        ("customer_return", "Devolução de cliente"),
        ("reversal", "Estorno"),
        ("initial", "Saldo inicial"),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="movements")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    lot = models.ForeignKey(Lot, null=True, blank=True, on_delete=models.PROTECT, related_name="movements")
    operation = models.ForeignKey(StockOperation, on_delete=models.PROTECT, related_name="movements")
    type = models.CharField(max_length=20, choices=TYPES)
    quantity = models.DecimalField(**QTY)  # positivo = entrada, negativo = saída (unidade de estoque)
    unit_cost = models.DecimalField(**UNIT_COST, default=0)
    total_cost = models.DecimalField(**MONEY, default=0)
    balance_after = models.DecimalField(**QTY, default=0)
    reason = models.CharField(max_length=255, blank=True)
    ref_type = models.CharField(max_length=30, blank=True)
    ref_id = models.CharField(max_length=40, blank=True)
    counterpart_unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reversal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    occurred_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [models.Index(fields=["unit", "product", "occurred_at"]), models.Index(fields=["ref_type", "ref_id"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("Movimentações de estoque são imutáveis. Use estorno ou ajuste.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Movimentações de estoque não podem ser excluídas.")


class WasteRecord(TenantModel):
    REASONS = [
        ("expired", "Vencido"),
        ("spoiled", "Estragado/impróprio"),
        ("preparation", "Erro ou sobra de preparo"),
        ("broken", "Quebra/avaria"),
        ("returned", "Devolvido pelo cliente"),
        ("cancelled_order", "Pedido cancelado em preparo"),
        ("storage", "Falha de armazenamento"),
        ("other", "Outro"),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="waste_records")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="waste_records")
    lot = models.ForeignKey(Lot, null=True, blank=True, on_delete=models.PROTECT)
    quantity = models.DecimalField(**QTY)
    total_cost = models.DecimalField(**MONEY, default=0)
    reason = models.CharField(max_length=20, choices=REASONS)
    notes = models.TextField(blank=True)
    operation = models.OneToOneField(StockOperation, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    occurred_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-occurred_at"]


class InventoryCount(TenantModel):
    STATUS = [("open", "Em contagem"), ("closed", "Finalizado"), ("cancelled", "Cancelado")]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="inventory_counts")
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    description = models.CharField(max_length=150, blank=True)
    reason = models.CharField("motivo do ajuste", max_length=255, blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    started_at = models.DateTimeField(auto_now_add=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class InventoryCountItem(models.Model):
    count = models.ForeignKey(InventoryCount, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    # Saldo do sistema no momento em que a contagem foi registrada.
    system_quantity = models.DecimalField(**QTY, default=0)
    counted_quantity = models.DecimalField(**QTY, null=True, blank=True)
    unit_cost = models.DecimalField(**UNIT_COST, default=0)
    counted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    counted_at = models.DateTimeField(null=True, blank=True)
    adjustment = models.ForeignKey(StockOperation, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["count", "product"], name="uniq_count_product")]
        ordering = ["product__name"]

    @property
    def difference(self):
        if self.counted_quantity is None:
            return None
        return self.counted_quantity - self.system_quantity

    @property
    def value_difference(self):
        diff = self.difference
        return None if diff is None else (diff * self.unit_cost).quantize(Decimal("0.01"))


class Transfer(TenantModel):
    from_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="transfers_out")
    to_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="transfers_in")
    notes = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    operation = models.OneToOneField(StockOperation, null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TransferItem(models.Model):
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(**QTY)
    total_cost = models.DecimalField(**MONEY, default=0)
