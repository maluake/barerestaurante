# Guia de funcionalidades, fases e próximos passos

## Perfis de acesso

| Perfil | Acesso padrão |
|---|---|
| **Proprietário** | Tudo: indicadores financeiros, equipe e permissões, unidades, configurações, auditoria, integrações |
| **Gerente** | Operação diária: produtos, estoque, inventário, perdas, cardápio, pedidos, vendas, cancelamentos, compras e aprovações, relatórios operacionais, alertas, assistente |
| **Estoquista** | Recebimento, consulta e movimentação de estoque, lotes e validades, inventário, transferências, perdas |
| **Atendente** | Registrar e acompanhar pedidos, consultar disponibilidade do cardápio e vendas |
| **Cozinha** | Fila de pedidos, atualizar preparo, consultar receitas, registrar perdas |

O proprietário pode conceder ou revogar permissões individuais e restringir unidades por funcionário
(*Configurações › Equipe e permissões*). Telas não permitidas ficam ocultas e bloqueadas no servidor.

## Telas

- **Dashboard** — 14 indicadores com explicação e link para a tela de origem, comparação com o mesmo dia da
  semana anterior / mesmo período do mês anterior, visão por unidade ou consolidada, “Atenção hoje” e gráficos
  (vendas e CMV por dia/semana/mês, mais vendidos, maior margem, valor do estoque, compras, índice de custo dos
  principais insumos, desperdício por semana e categoria, desempenho de fornecedores). Todo gráfico tem
  alternância para tabela.
- **Atenção** — alertas por prioridade com motivo, dados e ação; resolver; histórico.
- **Assistente do Negócio** — perguntas em linguagem natural respondidas com dados reais (fatos, estimativas e sugestões).
- **Pedidos / Novo pedido** — tela de toque para balcão, mesa, retirada, entrega e aplicativo, com porções
  disponíveis por item, observações, desconto; detalhe com histórico e ações.
- **Painel da cozinha** — colunas Novos / Em preparo / Prontos, tempo de espera, atrasados destacados, tela cheia.
- **Vendas** — resumo (bruto, descontos+taxas, líquido, ticket, CMV), registro rápido, cancelamento com
  estorno ou perda, importação CSV com relatório de erros e mapeamento de códigos do PDV.
- **Produtos** — busca, filtros (abaixo do mínimo, sem estoque, com vencido, categoria, arquivados), ordenação,
  cadastro com embalagens de compra, detalhe com lotes, movimentações, histórico e gráfico de custo, entrada
  manual (saldo inicial, devolução), arquivar.
- **Validades** — faixas configuráveis, recomendações seguras (vencidos: isolar e descartar) e estimativa de
  quanto pode vencer antes do uso.
- **Movimentações** — histórico filtrável; estorno auditável de entradas manuais e perdas.
- **Inventário** — contagem por categoria, diferença e valor em tempo real, finalização com motivo.
- **Perdas** — registro por lote ou FEFO, análise por produto/categoria/motivo e medidas preventivas.
- **Transferências** — entre unidades, preservando lote, validade e custo.
- **Fichas técnicas** — ingredientes com unidade compatível, perda de preparo, rendimento, prévia de custo ao
  editar, custo oficial, margem, evolução do custo e histórico de alterações.
- **Lista de compras** — sugestões explicadas, edição de quantidade/fornecedor, geração de pedidos por fornecedor.
- **Pedidos de compra** — criação, aprovação/reprovação, envio, recebimento parcial/total com lote e validade,
  ocorrências e histórico (quem criou, aprovou, enviou, recebeu).
- **Fornecedores** — cadastro completo, importação CSV, histórico e métricas (pontualidade, ocorrências).
- **Cotações** — data de referência, validade, condições; desatualizadas e vencidas sinalizadas.
- **Comparador** — custo total por fornecedor e para listas (melhor divisão com frete).
- **Oportunidades** — aumentos e reduções de custo, variações de cotação, fornecedores competitivos, cotações
  vencendo, compra conjunta e descontos com validade próxima (com limite de compra útil).
- **Financeiro** — demonstrativo com limitações, fluxo de caixa, contas a pagar/receber, abertura/fechamento de caixa.
- **Relatórios** — 17 relatórios com filtros, explicação da fórmula, CSV e impressão/PDF.
- **Configurações** — perfil e senha, exportação de dados (LGPD), regras do estabelecimento (limite de
  aprovação, faixas de validade, dias de funcionamento, cobertura, tempo de pedido, taxas e limites de alerta),
  unidades, equipe, cadastros auxiliares, preferências de notificação, auditoria e integrações.

## Relatório das fases

| Fase | Implementado | Verificação |
|---|---|---|
| 1 — Fundação | Projeto Django/DRF + React/Vite, PostgreSQL, migrations, autenticação por sessão/CSRF, organizações e unidades (multi-tenant), equipe e permissões por função, auditoria, layout, produtos e categorias, cadastro de estabelecimento | testes de segurança, isolamento, cadastro |
| 2 — Estoque | Lotes, FEFO, validades, movimentações imutáveis e idempotentes, estornos, inventário, perdas, transferências, conversões de unidade, alertas | 16 testes de estoque (incl. concorrência real com threads) |
| 3 — Fornecedores e compras | Fornecedores, importação, cotações, comparador de custo total, lista inteligente, pedidos com aprovação, recebimento parcial/total, ocorrências, contas a pagar | 9 testes de compras |
| 4 — Vendas e operação | Pedidos, painel da cozinha com atualização incremental, vendas, fichas técnicas, baixa automática, cancelamentos/estornos, importação CSV idempotente, mapeamento PDV | 13 testes de vendas/receitas |
| 5 — Inteligência | Dashboard, 17 relatórios com CSV, análise de custos, consumo teórico × real, previsão de demanda com sazonalidade semanal, assistente, indicadores financeiros | testes de finanças, alertas, dashboard, assistente e fluxo completo |
| 6 — Evolução comercial (parcial) | Múltiplas unidades com visão consolidada e permissões por unidade, limites por plano (unidades/usuários), notificações por e-mail, catálogo de integrações, Docker | testes de limite de plano e unidades |

Também verificado manualmente no navegador (Playwright): todas as telas como proprietário sem erros de API;
fluxo atendente cria pedido → atendente confirma → cozinha prepara → gerente entrega; geração da lista de
compras; comparador; bloqueio de tela financeira para atendente; layout em celular (390 px); modo produção
(Gunicorn + WhiteNoise) servindo a SPA.

### Problemas encontrados e corrigidos durante o desenvolvimento
- FEFO avaliava a validade pela data atual mesmo em lançamentos retroativos → passou a usar a data da operação.
- Consumo sem lote (saldo negativo) não era compensado pela chegada de novos lotes, inflando compras → o novo
  lote absorve o déficit.
- Comparador não indicava opção quando nenhum fornecedor atingia o pedido mínimo sozinho → indica a mais barata com aviso.
- Ajustes de layout do dashboard e do comparador; aninhamento inválido de botões.

## Integrações externas pendentes

| Integração | Situação | O que falta para ativar |
|---|---|---|
| PDV / comandas | Importação CSV funcional e idempotente | Documentação e credenciais da API do PDV; implementar `PosConnector.fetch_sales` (`apps/integrations/registry.py`) reutilizando `register_sale` |
| APIs de fornecedores/marketplaces | Cotações manuais | Acordo e API autorizada; gravar como `Quotation(source="api")` com data de referência |
| E-mail | Pronto (canal por usuário) | Configurar SMTP (`EMAIL_*`) |
| WhatsApp / push | Arquitetura de canal pronta | Conta WhatsApp Business API e consentimento |
| Modelo de IA para o assistente | Assistente por regras funcional | Implementar provedor em `apps/analytics/providers.py` e definir `ASSISTANT_PROVIDER`/`ASSISTANT_API_KEY` no backend |
| Cobrança de assinaturas | Planos e limites aplicados | Integração com gateway de pagamento |

## Roadmap

1. WebSockets (Django Channels + Redis) para cozinha e notificações em tempo real.
2. Estoque mínimo/ideal por unidade e transferência em trânsito (envio e recebimento em etapas).
3. Produção interna (pré-preparos com lote próprio e validade) e fichas técnicas aninhadas.
4. Reservas de estoque para pedidos agendados e cardápio com disponibilidade automática.
5. Conector de PDV via API, emissão/conciliação fiscal e recebíveis de cartão por prazo.
6. Previsão de demanda com eventos, feriados e clima; sugestões de preço por margem-alvo.
7. Modo offline para o painel da cozinha e app instalável (PWA).
8. Faturamento das assinaturas, onboarding guiado e tema escuro.
