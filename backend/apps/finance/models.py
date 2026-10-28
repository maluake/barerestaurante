from django.conf import settings
from django.db import models

from apps.core.models import TenantModel, Unit
from apps.inventory.models import MONEY


class ExpenseCategory(TenantModel):
    KINDS = [
        ("fixed", "Despesa fixa"),
        ("variable", "Despesa variável"),
        ("merchandise", "Compra de mercadorias"),
        ("payroll", "Folha e encargos"),
        ("tax", "Impostos"),
        ("fee", "Taxas e comissões"),
        ("revenue", "Receita"),
        ("other", "Outros"),
    ]

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=15, choices=KINDS)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="uniq_expense_category")]

    def __str__(self):
        return self.name


class FinancialEntry(TenantModel):
    """Conta a pagar ou a receber."""

    KINDS = [("payable", "A pagar"), ("receivable", "A receber")]
    STATUS = [("open", "Em aberto"), ("paid", "Pago/recebido"), ("cancelled", "Cancelado")]

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="financial_entries")
    kind = models.CharField(max_length=10, choices=KINDS, default="payable")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="entries")
    description = models.CharField(max_length=200)
    amount = models.DecimalField(**MONEY)
    competence_date = models.DateField("competência")
    due_date = models.DateField("vencimento")
    status = models.CharField(max_length=10, choices=STATUS, default="open", db_index=True)
    paid_at = models.DateField(null=True, blank=True)
    paid_amount = models.DecimalField(**MONEY, null=True, blank=True)
    payment_method = models.CharField(max_length=20, blank=True)
    supplier = models.ForeignKey("purchasing.Supplier", null=True, blank=True, on_delete=models.SET_NULL)
    purchase_order = models.ForeignKey("purchasing.PurchaseOrder", null=True, blank=True, on_delete=models.SET_NULL)
    receipt = models.OneToOneField("purchasing.Receipt", null=True, blank=True, on_delete=models.SET_NULL, related_name="payable")
    document = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "id"]


class CashSession(TenantModel):
    """Abertura e fechamento de caixa com conferência de valores."""

    STATUS = [("open", "Aberto"), ("closed", "Fechado")]

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="cash_sessions")
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    opened_at = models.DateTimeField()
    opening_amount = models.DecimalField(**MONEY)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_amount = models.DecimalField(**MONEY, null=True, blank=True)
    counted_amount = models.DecimalField(**MONEY, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["unit"], condition=models.Q(status="open"), name="one_open_cash_session"),
        ]

    @property
    def difference(self):
        if self.counted_amount is None or self.expected_amount is None:
            return None
        return self.counted_amount - self.expected_amount


class CashMovement(models.Model):
    KINDS = [("supply", "Suprimento"), ("withdrawal", "Sangria")]

    session = models.ForeignKey(CashSession, on_delete=models.CASCADE, related_name="movements")
    kind = models.CharField(max_length=12, choices=KINDS)
    amount = models.DecimalField(**MONEY)
    reason = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
