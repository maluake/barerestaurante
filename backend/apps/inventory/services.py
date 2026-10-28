"""Regras de negócio do estoque.

Princípios:
- Toda alteração de saldo passa por uma `StockOperation` com chave única
  (idempotência): reprocessar a mesma chave não gera nova movimentação.
- Linhas de saldo e lotes são bloqueadas com SELECT ... FOR UPDATE, sempre na
  ordem saldo -> lotes (por id), evitando condições de corrida.
- Saídas consomem lotes por FEFO (primeiro a vencer, primeiro a sair). Lotes
  vencidos não são consumidos para uso normal; só saem por descarte/ajuste.
- Movimentações nunca são editadas: correções são feitas com estorno ou ajuste.
"""

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.core.exceptions import BusinessError

from .models import (
    Lot,
    Product,
    ProductCostHistory,
    StockBalance,
    StockMovement,
    StockOperation,
    Transfer,
    TransferItem,
    WasteRecord,
)

Q4 = Decimal("0.0001")
C2 = Decimal("0.01")
ZERO = Decimal("0")


class AlreadyProcessed(Exception):
    def __init__(self, operation):
        super().__init__(f"Operação {operation.key} já processada")
        self.operation = operation


def today_for(unit) -> date:
    return timezone.localdate(timezone=ZoneInfo(unit.timezone or "America/Sao_Paulo"))


def money(value) -> Decimal:
    return Decimal(value).quantize(C2)


def begin_operation(org, unit, key, kind, user=None, description=""):
    """Cria a operação idempotente. Deve ser chamada dentro de transaction.atomic()."""
    try:
        with transaction.atomic():
            return StockOperation.objects.create(
                organization=org, unit=unit, key=key, kind=kind, user=user, description=description[:255]
            )
    except IntegrityError:
        raise AlreadyProcessed(StockOperation.objects.get(organization=org, key=key))


def lock_balance(unit, product):
    try:
        with transaction.atomic():
            StockBalance.objects.get_or_create(organization_id=unit.organization_id, unit=unit, product=product)
    except IntegrityError:
        pass  # outra transação criou a linha ao mesmo tempo
    return StockBalance.objects.select_for_update().get(unit=unit, product=product)


def _user(op, user):
    return user if user is not None else op.user


def _create_movement(op, unit, product, lot, type_, qty, unit_cost, balance, *, user, occurred_at, reason="",
                     ref_type="", ref_id="", counterpart_unit=None, reversal_of=None):
    balance.quantity = (balance.quantity + qty).quantize(Q4)
    balance.save(update_fields=["quantity", "updated_at"])
    return StockMovement.objects.create(
        organization_id=unit.organization_id, unit=unit, product=product, lot=lot, operation=op, type=type_,
        quantity=qty.quantize(Q4), unit_cost=Decimal(unit_cost).quantize(Q4),
        total_cost=money(abs(qty) * Decimal(unit_cost)), balance_after=balance.quantity, reason=reason[:255],
        ref_type=ref_type, ref_id=str(ref_id or ""), counterpart_unit=counterpart_unit, reversal_of=reversal_of,
        user=_user(op, user), occurred_at=occurred_at or timezone.now(),
    )


def add_stock(op, unit, product, quantity, unit_cost, *, type_="receipt", create_lot=True, lot_data=None, user=None,
              occurred_at=None, reason="", ref_type="", ref_id="", counterpart_unit=None):
    """Entrada de estoque. Retorna (lote, movimentação)."""
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise BusinessError("A quantidade de entrada deve ser maior que zero.")
    balance = lock_balance(unit, product)
    lot = None
    if create_lot:
        data = dict(lot_data or {})
        occurred = occurred_at or timezone.now()
        lot = Lot.objects.create(
            organization_id=unit.organization_id, unit=unit, product=product, quantity_received=quantity,
            quantity_remaining=quantity, unit_cost=unit_cost,
            received_at=data.pop("received_at", None) or timezone.localdate(occurred, ZoneInfo(unit.timezone)),
            source=data.pop("source", type_ if type_ in ("transfer_in", "adjustment", "initial") else "receipt"),
            **data,
        )
    deficit = lots_total(unit, product) - quantity - balance.quantity if lot else ZERO
    mv = _create_movement(op, unit, product, lot, type_, quantity, unit_cost, balance, user=user,
                          occurred_at=occurred_at, reason=reason, ref_type=ref_type, ref_id=ref_id,
                          counterpart_unit=counterpart_unit)
    if lot is not None and deficit > 0:
        # Havia saídas registradas sem lote (saldo negativo): a mercadoria que chega cobre esse
        # consumo já ocorrido. O lote novo absorve a diferença; o saldo total não muda.
        settle = min(deficit, quantity)
        lot.quantity_remaining -= settle
        if lot.quantity_remaining <= 0:
            lot.quantity_remaining = ZERO
            lot.status = "depleted"
        lot.save(update_fields=["quantity_remaining", "status"])
    return lot, mv


def _fefo_lots(unit, product, include_expired, today):
    qs = Lot.objects.select_for_update().filter(unit=unit, product=product, status="active", quantity_remaining__gt=0)
    if not include_expired:
        qs = qs.filter(Q(expires_at__isnull=True) | Q(expires_at__gte=today))
    return list(qs.order_by(F("expires_at").asc(nulls_last=True), "received_at", "id"))


def lots_total(unit, product):
    return Lot.objects.filter(unit=unit, product=product, status="active").aggregate(s=Sum("quantity_remaining"))["s"] or ZERO


def remove_stock(op, unit, product, quantity, *, type_, user=None, occurred_at=None, reason="", ref_type="", ref_id="",
                 lot=None, allow_negative=False, include_expired=False, counterpart_unit=None):
    """Saída de estoque por FEFO. Retorna a lista de movimentações criadas."""
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise BusinessError("A quantidade de saída deve ser maior que zero.")
    balance = lock_balance(unit, product)
    # A validade é avaliada na data da operação (importações e lançamentos retroativos).
    today = timezone.localdate(occurred_at, ZoneInfo(unit.timezone)) if occurred_at else today_for(unit)
    movements = []

    if lot is not None:
        lot = Lot.objects.select_for_update().get(pk=lot.pk, unit=unit, product=product)
        if lot.status != "active" or lot.quantity_remaining < quantity:
            raise BusinessError(
                f"O lote {lot.code or lot.pk} possui apenas {lot.quantity_remaining.normalize()} {product.unit.code} disponíveis."
            )
        if not include_expired and lot.expires_at and lot.expires_at < today:
            raise BusinessError("Lote vencido não pode ser usado. Registre o descarte.")
        allocations = [(lot, quantity)]
        remainder = ZERO
    else:
        allocations = []
        remainder = quantity
        for candidate in _fefo_lots(unit, product, include_expired, today):
            if remainder <= 0:
                break
            take = min(candidate.quantity_remaining, remainder)
            allocations.append((candidate, take))
            remainder -= take

    for alloc_lot, take in allocations:
        alloc_lot.quantity_remaining -= take
        if alloc_lot.quantity_remaining <= 0:
            alloc_lot.quantity_remaining = ZERO
            alloc_lot.status = "discarded" if type_ == "discard" else "depleted"
        alloc_lot.save(update_fields=["quantity_remaining", "status"])
        movements.append(_create_movement(
            op, unit, product, alloc_lot, type_, -take, alloc_lot.unit_cost, balance, user=user, occurred_at=occurred_at,
            reason=reason, ref_type=ref_type, ref_id=ref_id, counterpart_unit=counterpart_unit,
        ))

    if remainder > 0:
        # Parte sem lote: saldo registrado por ajuste/saldo inicial sem lote.
        unlotted = balance.quantity - lots_total(unit, product)
        if not allow_negative and unlotted < remainder:
            available = available_quantity(unit, product)
            raise BusinessError(
                f"Estoque insuficiente de {product.name}: disponível {available.normalize()} {product.unit.code}, "
                f"solicitado {quantity.normalize()} {product.unit.code}.",
                code="insufficient_stock",
            )
        movements.append(_create_movement(
            op, unit, product, None, type_, -remainder, product.cost_price, balance, user=user, occurred_at=occurred_at,
            reason=reason, ref_type=ref_type, ref_id=ref_id, counterpart_unit=counterpart_unit,
        ))
    return movements


def reverse_operation(op, *, user=None, reason="", occurred_at=None, key=None):
    """Estorna todas as movimentações de uma operação, de forma auditável e idempotente."""
    with transaction.atomic():
        op = StockOperation.objects.select_for_update().get(pk=op.pk)
        if op.reversed_by_id:
            raise AlreadyProcessed(op.reversed_by)
        reversal = begin_operation(op.organization, op.unit, key or f"reversal:{op.key}", "reversal", user,
                                   f"Estorno de {op.description or op.key}")
        for mv in op.movements.select_related("product", "unit").order_by("id"):
            balance = lock_balance(mv.unit, mv.product)
            if mv.lot_id:
                lot = Lot.objects.select_for_update().get(pk=mv.lot_id)
                new_remaining = lot.quantity_remaining - mv.quantity
                if new_remaining < 0:
                    raise BusinessError(
                        f"Não é possível estornar: o lote {lot.code or lot.pk} de {mv.product.name} já foi consumido."
                    )
                lot.quantity_remaining = new_remaining
                lot.status = "active" if new_remaining > 0 else "depleted"
                lot.save(update_fields=["quantity_remaining", "status"])
            _create_movement(
                reversal, mv.unit, mv.product, mv.lot, "reversal", -mv.quantity, mv.unit_cost, balance, user=user,
                occurred_at=occurred_at, reason=reason or f"Estorno: {mv.get_type_display()}", ref_type=mv.ref_type,
                ref_id=mv.ref_id, counterpart_unit=mv.counterpart_unit, reversal_of=mv,
            )
        op.reversed_by = reversal
        op.save(update_fields=["reversed_by"])
        return reversal


def expired_quantity(unit, product, today=None):
    today = today or today_for(unit)
    return Lot.objects.filter(
        unit=unit, product=product, status="active", expires_at__lt=today
    ).aggregate(s=Sum("quantity_remaining"))["s"] or ZERO


def physical_quantity(unit, product):
    bal = StockBalance.objects.filter(unit=unit, product=product).first()
    return bal.quantity if bal else ZERO


def available_quantity(unit, product, today=None):
    """Saldo disponível para uso normal: físico menos lotes vencidos (isolados)."""
    return physical_quantity(unit, product) - expired_quantity(unit, product, today)


# --------------------------------------------------------------------------- operações de alto nível


def record_waste(unit, product, quantity, reason, *, user=None, lot=None, notes="", occurred_at=None, key=None,
                 allow_negative=False):
    from uuid import uuid4

    with transaction.atomic():
        op = begin_operation(unit.organization, unit, key or f"waste:{uuid4()}", "waste", user,
                             f"Perda de {product.name}")
        type_ = "discard" if reason == "expired" else "loss"
        movements = remove_stock(
            op, unit, product, quantity, type_=type_, user=user, occurred_at=occurred_at,
            reason=dict(WasteRecord.REASONS).get(reason, reason), ref_type="waste", lot=lot,
            include_expired=True, allow_negative=allow_negative,
        )
        total = sum((m.total_cost for m in movements), ZERO)
        record = WasteRecord.objects.create(
            organization=unit.organization, unit=unit, product=product, lot=lot, quantity=quantity,
            total_cost=total, reason=reason, notes=notes, operation=op, user=user,
            occurred_at=occurred_at or timezone.now(),
        )
        StockMovement.objects.filter(operation=op).update(ref_id=str(record.pk))
        return record


def discard_lot(lot, *, user=None, notes=""):
    reason = "expired" if lot.expires_at and lot.expires_at < today_for(lot.unit) else "spoiled"
    return record_waste(lot.unit, lot.product, lot.quantity_remaining, reason, user=user, lot=lot, notes=notes,
                        key=f"discard-lot:{lot.pk}")


def adjust_balance(op, unit, product, delta, *, user=None, reason="", ref_type="", ref_id="", occurred_at=None):
    delta = Decimal(delta)
    if delta > 0:
        add_stock(op, unit, product, delta, product.cost_price, type_="adjustment", create_lot=False, user=user,
                  reason=reason, ref_type=ref_type, ref_id=ref_id, occurred_at=occurred_at)
    elif delta < 0:
        remove_stock(op, unit, product, -delta, type_="adjustment", user=user, reason=reason, ref_type=ref_type,
                     ref_id=ref_id, include_expired=True, allow_negative=True, occurred_at=occurred_at)


def transfer_stock(org, from_unit, to_unit, items, *, user=None, notes="", key=None):
    """Transfere mercadorias entre unidades. Cada saída gera uma entrada vinculada,
    preservando lote, validade e custo. Lotes vencidos não são transferidos."""
    from uuid import uuid4

    if from_unit.pk == to_unit.pk:
        raise BusinessError("Origem e destino devem ser unidades diferentes.")
    if from_unit.organization_id != org.pk or to_unit.organization_id != org.pk:
        raise BusinessError("As unidades devem pertencer ao mesmo estabelecimento.")
    with transaction.atomic():
        op = begin_operation(org, from_unit, key or f"transfer:{uuid4()}", "transfer", user,
                             f"Transferência {from_unit.name} → {to_unit.name}")
        transfer = Transfer.objects.create(organization=org, from_unit=from_unit, to_unit=to_unit, notes=notes,
                                           user=user, operation=op)
        for product, quantity in items:
            # Bloqueia os dois saldos sempre na mesma ordem para evitar deadlock.
            for u in sorted([from_unit, to_unit], key=lambda x: x.pk):
                lock_balance(u, product)
            outs = remove_stock(op, from_unit, product, quantity, type_="transfer_out", user=user,
                                reason=f"Para {to_unit.name}", ref_type="transfer", ref_id=transfer.pk,
                                counterpart_unit=to_unit)
            total = ZERO
            for mv in outs:
                lot_data = None
                if mv.lot_id:
                    src = mv.lot
                    lot_data = {"code": src.code, "expires_at": src.expires_at, "manufactured_at": src.manufactured_at,
                                "supplier": src.supplier, "document": src.document, "received_at": src.received_at,
                                "source": "transfer"}
                add_stock(op, to_unit, product, -mv.quantity, mv.unit_cost, type_="transfer_in",
                          create_lot=bool(mv.lot_id), lot_data=lot_data, user=user, reason=f"De {from_unit.name}",
                          ref_type="transfer", ref_id=transfer.pk, counterpart_unit=from_unit)
                total += mv.total_cost
            TransferItem.objects.create(transfer=transfer, product=product, quantity=quantity, total_cost=total)
        return transfer


def update_product_cost(product, new_cost, *, source, reference="", user=None, at=None):
    new_cost = Decimal(new_cost).quantize(Q4)
    product = Product.objects.select_for_update().get(pk=product.pk)
    if new_cost == product.cost_price:
        return False
    ProductCostHistory.objects.create(
        product=product, cost=new_cost, previous_cost=product.cost_price, source=source, reference=reference,
        user=user, created_at=at or timezone.now(),
    )
    product.cost_price = new_cost
    product.save(update_fields=["cost_price", "updated_at"])
    from apps.menu.services import recalculate_items_using

    recalculate_items_using(product, at=at)
    return True
