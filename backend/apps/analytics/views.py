import csv
from datetime import date, datetime
from decimal import Decimal

from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessError
from apps.core.tenancy import TenantMixin
from apps.inventory.services import today_for

from .assistant import EXAMPLES, answer
from .dashboard import build_dashboard
from .models import AssistantQuery
from .providers import get_provider
from .reports import REPORTS, run_report


def scope_units(request):
    if request.query_params.get("scope") == "all":
        return list(request.membership.allowed_units())
    return [request.unit]


class DashboardView(TenantMixin, APIView):
    required_permissions = "dashboard.view"

    def get(self, request):
        data = build_dashboard(request, scope_units(request))
        if "finance.view" not in request.perms and "costs.view" not in request.perms:
            hidden = {"cogs_month", "margin_month"}
            data["kpis"] = [k for k in data["kpis"] if k["key"] not in hidden]
        return Response(data)


class ReportListView(TenantMixin, APIView):
    required_permissions = "reports.view"

    def check_permissions(self, request):
        if "reports.view" in request.perms or "reports.finance" in request.perms:
            return
        super().check_permissions(request)

    def get(self, request):
        return Response([{"key": r["key"], "title": r["title"], "description": r["description"], "finance": r["finance"]}
                         for r in REPORTS.values() if not r["finance"] or "reports.finance" in request.perms
                         or "costs.view" in request.perms])


def _fmt(value, type_):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone().strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, Decimal):
        return f"{value:.2f}".replace(".", ",") if type_ in ("money", "percent") else str(value.normalize()).replace(".", ",")
    return value


class ReportView(TenantMixin, APIView):
    required_permissions = "reports.view"

    def check_permissions(self, request):
        key = self.kwargs.get("key")
        r = REPORTS.get(key)
        if r and r["finance"] and not ("reports.finance" in request.perms or "costs.view" in request.perms):
            self.permission_denied(request, message="Relatório financeiro restrito ao seu perfil.")
        if "reports.view" in request.perms or "reports.finance" in request.perms:
            return
        super().check_permissions(request)

    def get(self, request, key):
        if key not in REPORTS:
            raise BusinessError("Relatório inexistente.")
        today = today_for(request.unit)
        p = request.query_params
        try:
            start = date.fromisoformat(p["start"]) if p.get("start") else today.replace(day=1)
            end = date.fromisoformat(p["end"]) if p.get("end") else today
        except ValueError:
            raise BusinessError("Datas inválidas.")
        if end < start:
            raise BusinessError("A data final deve ser posterior à inicial.")
        ctx = {"org": request.org, "units": scope_units(request), "start": start, "end": end, "today": today}
        filters = {k: v for k, v in p.items() if k in ("category", "product", "supplier", "grain", "group", "days")}
        data = run_report(key, ctx, filters)
        if p.get("export") == "csv":
            resp = HttpResponse(content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="{key}_{start}_{end}.csv"'
            resp.write("﻿")
            w = csv.writer(resp, delimiter=";")
            w.writerow([c["label"] for c in data["columns"]])
            for row in data["rows"]:
                w.writerow([_fmt(row.get(c["key"]), c["type"]) for c in data["columns"]])
            return resp
        return Response(data)


class AssistantView(TenantMixin, APIView):
    required_permissions = "assistant.use"

    def get(self, request):
        return Response({"examples": EXAMPLES, "provider": get_provider().name})

    def post(self, request):
        question = (request.data.get("question") or "").strip()
        if not question:
            raise BusinessError("Digite uma pergunta.")
        if len(question) > 500:
            raise BusinessError("Pergunta muito longa (máximo 500 caracteres).")
        provider = get_provider()
        result = provider.rewrite(question, answer(question, request.unit, request.perms))
        AssistantQuery.objects.create(organization=request.org, unit=request.unit, user=request.user, question=question,
                                      intent=result["intent"], provider=provider.name)
        result["provider"] = provider.name
        return Response(result)
