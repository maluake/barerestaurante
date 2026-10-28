from django.core.management.base import BaseCommand

from apps.alerts.engine import refresh_alerts
from apps.core.models import Unit


class Command(BaseCommand):
    help = "Recalcula os alertas de todas as unidades ativas (agende via cron a cada 5–15 minutos)."

    def handle(self, *args, **options):
        total = 0
        for unit in Unit.objects.filter(is_active=True).select_related("organization"):
            total += len(refresh_alerts(unit, force=True))
        self.stdout.write(self.style.SUCCESS(f"Alertas atualizados. Novos: {total}"))
