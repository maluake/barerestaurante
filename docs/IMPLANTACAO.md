# Implantação, operação, backup e LGPD

## Imagem e execução

O `Dockerfile` (raiz) compila o frontend e gera uma imagem Python que serve a API (`/api/`), o admin
(`/admin/`) e a SPA (demais rotas) com Gunicorn + WhiteNoise. Na inicialização executa `migrate`.

```bash
docker build -t mise .
docker run -p 8000:8000 --env-file producao.env mise
```

Para ambiente completo com PostgreSQL: `docker compose up --build`.

Sem Docker: `npm run build` em `frontend/`, depois em `backend/`:
`python manage.py collectstatic --noinput && python manage.py migrate && gunicorn config.wsgi:application`
(a variável `FRONTEND_DIST` aponta para `frontend/dist`). Coloque um proxy HTTPS (Nginx, Caddy ou o
balanceador do provedor) na frente e repasse `X-Forwarded-Proto`.

## Variáveis de ambiente (ver `backend/.env.example`)

| Variável | Produção |
|---|---|
| `SECRET_KEY` | chave longa e aleatória, fora do repositório |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | domínios da aplicação |
| `CSRF_TRUSTED_ORIGINS` | `https://seu-dominio` |
| `DATABASE_URL` | `postgres://usuario:senha@host:5432/banco` |
| `SECURE_COOKIES` | `True` (cookies só via HTTPS) |
| `EMAIL_BACKEND`, `EMAIL_HOST`... | SMTP para alertas por e-mail (opcional) |
| `ASSISTANT_PROVIDER`, `ASSISTANT_API_KEY` | provedor de IA do assistente (opcional; somente no backend) |
| `WEB_CONCURRENCY` | número de workers do Gunicorn |

## Primeiro acesso

1. `python manage.py createsuperuser` (opcional, para o `/admin/` técnico).
2. Acesse a aplicação e use “Cadastre seu estabelecimento” — cria organização, primeira unidade, usuário
   proprietário e cadastros básicos (categorias, locais de armazenamento, categorias financeiras).

## Rotinas agendadas

| Comando | Frequência sugerida | Função |
|---|---|---|
| `python manage.py refresh_alerts` | a cada 5–15 min | recalcula alertas e envia notificações (inclui unidades sem acesso no momento) |
| `pg_dump` (ver abaixo) | diário | backup |

Os alertas também são recalculados quando alguém abre o dashboard ou a tela de alertas.

## Segurança aplicada

- Autenticação por sessão com cookie HttpOnly + token CSRF obrigatório em escritas; senhas com validadores do Django.
- Limite de tentativas: login 10/min, cadastro 5/h por IP.
- Permissões verificadas no backend em todas as rotas (negado por padrão).
- Isolamento entre estabelecimentos: unidade validada contra o vínculo do usuário; chaves estrangeiras
  filtradas pela organização; consultas sempre escopadas.
- Movimentações imutáveis, estornos auditáveis, trilha de auditoria (usuário, IP, data, resumo e alterações).
- Idempotência em recebimentos, vendas, pedidos, perdas, transferências e importações.
- Cabeçalhos: `X-Frame-Options: DENY`, `nosniff`; cookies `Secure` em produção.
- Erros inesperados retornam mensagem genérica e são registrados em log (stdout).

## Política de backup e recuperação

- **Backup diário completo** do PostgreSQL com retenção de 30 dias e cópia semanal fora do provedor:
  ```bash
  pg_dump --format=custom --no-owner "$DATABASE_URL" > mise_$(date +%F).dump
  ```
- Preferir também o PITR (WAL contínuo) do serviço gerenciado de banco, quando disponível (RPO de minutos).
- **Teste de restauração mensal** em ambiente separado:
  ```bash
  createdb mise_restore && pg_restore --no-owner -d mise_restore mise_AAAA-MM-DD.dump
  python manage.py check && python manage.py showmigrations
  ```
- Objetivos sugeridos: RPO ≤ 24 h (≤ 15 min com PITR), RTO ≤ 4 h.
- Backups criptografados em repouso e com acesso restrito; nunca versionar dumps.

## LGPD

- Dados pessoais tratados: usuários (nome, e-mail, usuário), contatos de fornecedores (pessoa jurídica e
  contato comercial) e, opcionalmente, nome do cliente em pedidos de retirada/entrega. Não há dados sensíveis.
- Base legal: execução de contrato e legítimo interesse para a operação do estabelecimento.
- Minimização: campos de cliente são opcionais; não coletamos CPF, endereço de consumidor ou dados de pagamento.
- Direitos do titular: cada usuário exporta seus dados em *Configurações › Meu perfil › Exportar meus dados*.
  Correção/exclusão de usuários é feita pelo proprietário (desativação preserva a auditoria); pedidos de
  titulares externos devem ser tratados pelo controlador (o estabelecimento).
- Aceite dos termos e da política de privacidade no cadastro.
- Logs de auditoria guardam IP e ações para segurança; defina retenção (sugestão: 5 anos para registros
  fiscais/operacionais, 12 meses para logs de acesso).
- Em caso de incidente, a trilha de auditoria e os logs apoiam a comunicação à ANPD e aos titulares.
