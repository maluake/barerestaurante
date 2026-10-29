#!/usr/bin/env bash
# Executado sempre que o Codespace inicia: sobe a aplicação na porta 8000.
cd "$(dirname "$0")/../backend"
pkill -f "gunicorn config.wsgi" 2>/dev/null || true
nohup .venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120 \
  > /tmp/mise.log 2>&1 &
echo "Mise iniciado em http://localhost:8000 (log em /tmp/mise.log)"
