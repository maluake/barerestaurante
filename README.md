# Mise — Gestão inteligente para bares e restaurantes

[![Publicar no Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/maluake/barerestaurante)

## Colocar o site no ar (link público, sem instalar nada)

1. Clique no botão **Deploy to Render** acima e entre com sua conta do GitHub (o cadastro no Render é gratuito).
2. Confirme em **Deploy Blueprint** / **Apply**. O Render cria sozinho o banco de dados e o site, usando o
   arquivo `render.yaml` deste repositório. Não é preciso preencher nada.
3. Aguarde a primeira publicação (cerca de 10 minutos). Depois, abra o serviço **mise** no painel do Render:
   o link fica no topo, no formato `https://mise-xxxx.onrender.com`. Esse link pode ser aberto em qualquer
   computador ou celular e compartilhado.
4. Entre com usuário **`demo.dono`** e senha **`Demo@2026`** (ou `demo.gerente`, `demo.estoque`,
   `demo.atendente`, `demo.cozinha`). Na primeira abertura, os dados de demonstração levam de 2 a 4 minutos para
   aparecer; se o login recusar no início, espere um pouco e tente de novo.

Sobre o plano gratuito do Render:
- O site “dorme” após 15 minutos sem acesso; a próxima visita demora cerca de 1 minuto para carregar.
- O banco gratuito vale por 30 dias; depois é preciso migrar para um plano pago ou recriar o banco.
- Todos os dados desse ambiente são fictícios. Para uso real, troque `DEMO_DATA` para `false` no painel do Render.

Toda vez que um novo commit chega à branch principal do repositório, o Render atualiza o site automaticamente.

### Alternativa: abrir pelo GitHub Codespaces

[![Abrir no GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/maluake/barerestaurante?quickstart=1)

Cria um ambiente temporário no navegador (5 a 8 minutos na primeira vez) e abre a aplicação na porta 8000,
com os mesmos usuários de demonstração. O link só funciona enquanto o Codespace estiver ligado. Pare ou exclua
o Codespace quando não estiver usando, para não gastar a cota gratuita do GitHub.

---

Plataforma web (SaaS, multi-tenant) para controlar estoque por lote e validade, fichas técnicas e custos,
pedidos e cozinha, vendas, compras e fornecedores, finanças, alertas e um assistente que transforma os
registros operacionais em recomendações práticas.

| Camada | Tecnologia |
|---|---|
| Frontend | React 18 + TypeScript + Vite, Tailwind CSS, Radix UI (componentes acessíveis), Recharts, TanStack Query |
| Backend | Python 3.12+ / Django 5.1 + Django REST Framework |
| Banco | PostgreSQL 16 |
| Implantação | Docker (multi-stage), Gunicorn + WhiteNoise servindo API e SPA |

Documentação complementar:

- [`docs/GUIA.md`](docs/GUIA.md) — guia de funcionalidades, perfis, relatório das fases, integrações pendentes e roadmap
- [`docs/REGRAS_DE_NEGOCIO.md`](docs/REGRAS_DE_NEGOCIO.md) — definições, fórmulas e regras (FEFO, baixa, custeio, finanças, compras, alertas)
- [`docs/IMPLANTACAO.md`](docs/IMPLANTACAO.md) — produção, variáveis de ambiente, rotinas agendadas, backup/recuperação e LGPD

## Estrutura

```
backend/
  config/            settings, urls (API em /api/, SPA nas demais rotas)
  apps/core/         organizações (tenant), unidades, equipe, permissões, auditoria, autenticação, demo
  apps/inventory/    produtos, unidades de medida, lotes, movimentações, inventário, perdas, transferências
  apps/purchasing/   fornecedores, cotações, comparador, lista inteligente, pedidos de compra, recebimento
  apps/menu/         cardápio, fichas técnicas, custeio
  apps/sales/        pedidos, painel da cozinha, vendas, importação CSV, mapeamento PDV
  apps/finance/      contas a pagar/receber, caixa, resultado e fluxo de caixa
  apps/alerts/       motor de alertas, notificações e preferências
  apps/analytics/    dashboard, relatórios, Assistente do Negócio
  apps/integrations/ catálogo e registro de integrações externas (opcionais)
  tests/             testes automatizados (pytest)
frontend/
  src/components/    UI reutilizável, gráficos e componentes de domínio
  src/layout/        estrutura (sidebar, cabeçalho, busca global, guardas)
  src/pages/         telas por módulo
```

## Executar localmente

Pré-requisitos: Python 3.12+, Node 20+, PostgreSQL 14+.

### 1. Banco de dados

```bash
sudo -u postgres psql -c "CREATE USER gastro WITH PASSWORD 'gastro' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE gastro OWNER gastro;"
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env              # ajuste DATABASE_URL e SECRET_KEY
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo   # opcional: ambiente de demonstração
.venv/bin/python manage.py runserver   # http://127.0.0.1:8000/api/
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173 (proxy de /api para o Django)
```

### Com Docker (aplicação completa)

```bash
docker compose up --build         # http://localhost:8000
docker compose exec web python manage.py seed_demo
```

## Dados de demonstração

`python manage.py seed_demo` cria **“Bar e Restaurante Exemplo (demonstração)”** com duas unidades,
30 produtos, 5 fornecedores fictícios, cotações, 15 itens de cardápio (um propositalmente sem ficha técnica),
45 dias de histórico (compras recebidas, ~550 vendas, perdas e descartes), pedidos em vários estados, um
inventário com divergências, uma compra aguardando aprovação, uma entrega atrasada, caixa aberto e despesas.
Tudo é gerado pelos mesmos serviços usados pela aplicação, portanto lotes, custos, movimentações e alertas são
coerentes entre si.

- Todos os registros são marcados como fictícios (organização `is_demo`, fornecedores com “(fictício)”).
- `python manage.py seed_demo --reset` recria; `--clear` apenas remove. **Somente organizações de demonstração são afetadas.**

Credenciais (apenas ambiente local de demonstração), senha `Demo@2026`:

| Usuário | Perfil |
|---|---|
| `demo.dono` | Proprietário |
| `demo.gerente` | Gerente |
| `demo.estoque` | Estoquista |
| `demo.atendente` | Atendente |
| `demo.cozinha` | Cozinha |

Para começar sem demonstração, use “Cadastre seu estabelecimento” na tela de login.

## Testes

```bash
cd backend
.venv/bin/pytest                  # 56 testes (requer PostgreSQL; cria o banco de teste)
.venv/bin/ruff check .            # lint
cd ../frontend
npx tsc -p tsconfig.app.json --noEmit && npm run lint && npm run build
```

Os testes cobrem: conversão de unidades, FEFO, lotes vencidos, idempotência, estornos, imutabilidade de
movimentações, perdas, transferências, concorrência (duas saídas simultâneas), inventário, custo de receitas,
recálculo por mudança de custo, baixa por pedido sem duplicidade, cancelamentos (antes e durante o preparo),
importação CSV idempotente, comparador de custo total, aprovação, recebimento parcial, lista de compras,
permissões por perfil, CSRF, isolamento entre estabelecimentos, auditoria, cálculos financeiros, caixa,
alertas (deduplicação, auto-resolução, adiamento), dashboard e assistente — além do **fluxo de aceitação
completo** (cadastro do estabelecimento → fornecedor → produto → cotação → pedido → recebimento com lotes →
ficha técnica → venda → baixa → movimentações → alertas → lista de compras → comparador → relatórios).
