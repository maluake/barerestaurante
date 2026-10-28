"""Importação de vendas por CSV (alternativa local a uma integração com PDV).

Formato (separador `;` ou `,`, uma linha por item):
    id_venda;data_hora;canal;forma_pagamento;codigo_produto;descricao;quantidade;preco_unitario;desconto_item;taxa;cancelada

- `id_venda` identifica a venda de forma única: reimportar o mesmo arquivo não duplica vendas.
- `data_hora` em `AAAA-MM-DD HH:MM` ou `DD/MM/AAAA HH:MM` (fuso da unidade).
- `codigo_produto` é mapeado para o cardápio via mapeamentos de PDV ou pelo campo "código no PDV".
- `taxa` (opcional) é informada na primeira linha da venda; `cancelada` aceita sim/não.
"""

import csv
import io
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.menu.models import MenuItem

from .models import ImportBatch, PosMapping
from .services import register_sale

CHANNELS = {"balcao": "counter", "balcão": "counter", "mesa": "table", "retirada": "takeout", "entrega": "delivery",
            "delivery": "delivery", "app": "app", "aplicativo": "app", "ifood": "app"}
PAYMENTS = {"dinheiro": "cash", "pix": "pix", "debito": "debit", "débito": "debit", "credito": "credit",
            "crédito": "credit", "vale": "voucher", "voucher": "voucher", "app": "app"}


def _dec(value, field):
    v = (value or "").strip()
    if not v:
        return Decimal("0")
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except InvalidOperation:
        raise ValueError(f"Valor inválido em {field}: {value}")


def _dt(value, tz):
    v = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    raise ValueError(f"Data/hora inválida: {value}")


def resolve_menu_item(org, code, source="csv"):
    m = PosMapping.objects.filter(organization=org, source=source, external_code=code).select_related("menu_item").first()
    if m:
        return m.menu_item
    return MenuItem.objects.filter(organization=org, pos_code=code).first()


def import_sales_csv(org, unit, user, content, filename="", source="csv"):
    text = content.decode("utf-8-sig", errors="replace") if isinstance(content, bytes) else content
    lines = text.splitlines()
    if not lines:
        raise ValueError("Arquivo vazio.")
    delimiter = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    tz = ZoneInfo(unit.timezone)
    batch = ImportBatch.objects.create(organization=org, unit=unit, source=source, filename=filename[:200], user=user)
    sales = OrderedDict()
    errors, unmapped = [], set()
    rows = 0
    for n, raw in enumerate(reader, start=2):
        rows += 1
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        try:
            sid = row.get("id_venda")
            if not sid:
                raise ValueError("id_venda obrigatório.")
            code = row.get("codigo_produto", "")
            item = resolve_menu_item(org, code, source) if code else None
            if item is None:
                unmapped.add(code or row.get("descricao", ""))
            entry = sales.setdefault(sid, {
                "occurred_at": _dt(row.get("data_hora"), tz),
                "channel": CHANNELS.get(row.get("canal", "").lower(), "counter"),
                "payment_method": PAYMENTS.get(row.get("forma_pagamento", "").lower(), "other" if row.get("forma_pagamento") else ""),
                "fee": _dec(row.get("taxa"), "taxa"),
                "cancelled": row.get("cancelada", "").lower() in ("sim", "s", "1", "true", "cancelada"),
                "items": [],
            })
            qty = _dec(row.get("quantidade"), "quantidade")
            if qty <= 0:
                raise ValueError("Quantidade deve ser maior que zero.")
            entry["items"].append({
                "menu_item": item, "description": row.get("descricao") or (item.name if item else code),
                "external_code": code, "quantity": qty, "unit_price": _dec(row.get("preco_unitario"), "preco_unitario"),
                "discount": _dec(row.get("desconto_item"), "desconto_item"),
            })
        except ValueError as exc:
            errors.append({"linha": n, "erro": str(exc)})
    imported = duplicated = 0
    for sid, data in sales.items():
        try:
            with transaction.atomic():
                _, created = register_sale(
                    org, unit, user, items=data["items"], channel=data["channel"], payment_method=data["payment_method"],
                    fee=data["fee"], occurred_at=data["occurred_at"], source=source, external_id=sid, import_batch=batch,
                    cancelled_reason="Cancelada no PDV (importação)" if data["cancelled"] else None,
                )
            if created:
                imported += 1
            else:
                duplicated += 1
        except Exception as exc:  # noqa: BLE001 - reporta a falha e continua as demais vendas
            errors.append({"venda": sid, "erro": getattr(exc, "message", str(exc))})
    batch.rows_total = rows
    batch.sales_imported = imported
    batch.sales_duplicated = duplicated
    batch.rows_failed = len(errors)
    batch.errors = errors[:200]
    batch.unmapped_codes = sorted(c for c in unmapped if c)[:200]
    batch.save()
    if errors:
        from apps.integrations.models import IntegrationLog

        IntegrationLog.objects.create(organization=org, kind="pos", status="failure",
                                      message=f"Importação '{filename}' com {len(errors)} erro(s).",
                                      details={"batch": batch.pk, "errors": errors[:20]})
    return batch
