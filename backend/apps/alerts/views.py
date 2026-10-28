from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.tenancy import TenantMixin, audit

from .engine import refresh_alerts, resolve_alert
from .models import ALERT_TYPES, PRIORITIES, Alert, Notification, NotificationPreference


class AlertSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    resolved_by_name = serializers.CharField(source="resolved_by.username", read_only=True, default=None)

    class Meta:
        model = Alert
        fields = ["id", "type", "type_label", "priority", "priority_label", "title", "reason", "action_label",
                  "action_path", "data", "status", "status_label", "first_seen_at", "last_seen_at", "resolved_at",
                  "resolved_by_name", "resolution_note"]


PRIORITY_SORT = Case(*[When(priority=p, then=Value(i)) for i, (p, _) in enumerate(PRIORITIES)], output_field=IntegerField())


class AlertViewSet(TenantMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AlertSerializer
    queryset = Alert.objects.select_related("resolved_by")
    unit_scoped = True
    required_permissions = {"resolve": "alerts.manage", "*": "alerts.view"}
    filterset_fields = {"type": ["exact", "in"], "priority": ["exact"], "status": ["exact", "in"]}

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            if not self.request.query_params.get("status") and not self.request.query_params.get("status__in"):
                refresh_alerts(self.request.unit)
                qs = qs.filter(status="open")
            qs = qs.annotate(p=PRIORITY_SORT).order_by("p", "-first_seen_at")
        return qs

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        alert = resolve_alert(self.get_object(), request.user, request.data.get("note", ""))
        audit(request, "resolve", alert, summary=f"Alerta resolvido: {alert.title}")
        return Response(self.get_serializer(alert).data)

    @action(detail=False, methods=["post"])
    def refresh(self, request):
        created = refresh_alerts(request.unit, force=True)
        return Response({"created": len(created)})

    @action(detail=False, methods=["get"])
    def counts(self, request):
        refresh_alerts(request.unit)
        qs = Alert.objects.filter(unit=request.unit, status="open")
        return Response({p: qs.filter(priority=p).count() for p, _ in PRIORITIES} | {"total": qs.count()})


class PreferencesView(TenantMixin, APIView):
    required_permissions = "alerts.view"

    def get(self, request):
        prefs = {p.alert_type: p for p in NotificationPreference.objects.filter(membership=request.membership)}
        return Response([{
            "alert_type": code, "label": label,
            "enabled": prefs[code].enabled if code in prefs else True,
            "min_priority": prefs[code].min_priority if code in prefs else "low",
            "channels": prefs[code].channels if code in prefs else ["in_app"],
        } for code, label in ALERT_TYPES])

    def put(self, request):
        valid_types = dict(ALERT_TYPES)
        for row in request.data if isinstance(request.data, list) else []:
            if row.get("alert_type") not in valid_types:
                continue
            channels = [c for c in row.get("channels", []) if c in ("in_app", "email")]
            NotificationPreference.objects.update_or_create(
                membership=request.membership, alert_type=row["alert_type"],
                defaults={"enabled": bool(row.get("enabled", True)),
                          "min_priority": row.get("min_priority") if row.get("min_priority") in dict(PRIORITIES) else "low",
                          "channels": channels or ["in_app"]})
        return self.get(request)


class NotificationsView(TenantMixin, APIView):
    required_permissions = "alerts.view"

    def get(self, request):
        qs = Notification.objects.filter(user=request.user, channel="in_app", alert__organization=request.org,
                                         alert__status="open").select_related("alert")[:30]
        unread = Notification.objects.filter(user=request.user, channel="in_app", read_at__isnull=True,
                                             alert__organization=request.org, alert__status="open").count()
        return Response({"unread": unread, "items": [{
            "id": n.id, "read": bool(n.read_at), "created_at": n.created_at, **AlertSerializer(n.alert).data,
            "alert_id": n.alert_id} for n in qs]})

    def post(self, request):
        Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"unread": 0})
