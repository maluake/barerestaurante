"""Conversão explícita entre unidades de medida.

Regras:
- Mesma unidade: sem conversão.
- Mesma dimensão (massa, volume, contagem): usa `factor_to_base` (g, ml, un).
- Embalagem (caixa, pacote...): só converte se houver `ProductPackaging` para o produto.
- Qualquer outro caso levanta `IncompatibleUnits` — nunca presumimos densidades
  nem quantidades por embalagem.
"""

from decimal import Decimal

from apps.core.exceptions import BusinessError


class IncompatibleUnits(BusinessError):
    def __init__(self, from_unit, to_unit, product=None):
        extra = f" para o produto {product.name}" if product is not None else ""
        super().__init__(
            f"Não é possível converter {from_unit.code} em {to_unit.code}{extra}. "
            "Cadastre a embalagem do produto ou use uma unidade compatível.",
            code="incompatible_units",
        )


def convert(quantity, from_unit, to_unit, product=None, _depth=0):
    quantity = Decimal(quantity)
    if from_unit.pk == to_unit.pk:
        return quantity
    if _depth > 3:
        raise IncompatibleUnits(from_unit, to_unit, product)
    if from_unit.dimension == to_unit.dimension and from_unit.dimension != "package":
        if not from_unit.factor_to_base or not to_unit.factor_to_base:
            raise IncompatibleUnits(from_unit, to_unit, product)
        return quantity * from_unit.factor_to_base / to_unit.factor_to_base
    if product is not None:
        packagings = {p.unit_id: p for p in product.packagings.all()}
        if from_unit.pk in packagings:
            pk = packagings[from_unit.pk]
            return convert(quantity * pk.quantity, pk.contained_unit, to_unit, product, _depth + 1)
        if to_unit.pk in packagings:
            pk = packagings[to_unit.pk]
            inner = convert(quantity, from_unit, pk.contained_unit, product, _depth + 1)
            return inner / pk.quantity
    raise IncompatibleUnits(from_unit, to_unit, product)


def is_convertible(from_unit, to_unit, product=None):
    try:
        convert(1, from_unit, to_unit, product)
        return True
    except IncompatibleUnits:
        return False


DEFAULT_UNITS = [
    ("mg", "Miligrama", "mass", "0.001"),
    ("g", "Grama", "mass", "1"),
    ("kg", "Quilograma", "mass", "1000"),
    ("ml", "Mililitro", "volume", "1"),
    ("L", "Litro", "volume", "1000"),
    ("un", "Unidade", "count", "1"),
    ("dz", "Dúzia", "count", "12"),
    ("cx", "Caixa", "package", None),
    ("pct", "Pacote", "package", None),
    ("fd", "Fardo", "package", None),
    ("sc", "Saco", "package", None),
    ("gf", "Garrafa", "package", None),
    ("lt", "Lata", "package", None),
    ("bd", "Bandeja", "package", None),
]


def ensure_default_units():
    from .models import UnitOfMeasure

    for code, name, dim, factor in DEFAULT_UNITS:
        UnitOfMeasure.objects.get_or_create(
            organization=None, code=code,
            defaults={"name": name, "dimension": dim, "factor_to_base": Decimal(factor) if factor else None},
        )
