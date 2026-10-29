#!/bin/sh
# Inicialização do contêiner em produção/demonstração.
set -e
python manage.py migrate --noinput
if [ "${DEMO_DATA:-false}" = "true" ]; then
  # Em segundo plano para o servidor responder logo; na primeira vez leva alguns minutos.
  python manage.py seed_demo &
fi
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" --timeout 120 --access-logfile -
