#!/usr/bin/env bash
# Executado uma única vez, quando o Codespace é criado.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Instalando dependências do backend"
python -m venv backend/.venv
backend/.venv/bin/pip install --quiet -r backend/requirements.txt

echo "==> Compilando o frontend"
(cd frontend && npm ci --no-audit --no-fund && npm run build)

echo "==> Aguardando o banco de dados"
for i in $(seq 1 30); do
  backend/.venv/bin/python -c "import psycopg, os; psycopg.connect(os.environ['DATABASE_URL']).close()" 2>/dev/null && break
  sleep 2
done

echo "==> Preparando o banco e os dados de demonstração"
cd backend
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput >/dev/null
.venv/bin/python manage.py seed_demo
echo "==> Pronto. Usuário: demo.dono  Senha: Demo@2026"
