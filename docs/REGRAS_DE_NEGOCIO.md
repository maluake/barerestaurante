# Regras de negócio, definições e fórmulas

Este documento descreve como o sistema calcula e decide. As regras críticas ficam **no backend**
(`apps/*/services.py`); o frontend apenas apresenta e valida a forma dos dados.

## 1. Multi-tenant e permissões

- **Organização** = cliente (tenant). Tem uma ou mais **unidades** (estabelecimentos físicos).
- Compartilhados na organização: produtos, categorias, fornecedores, cotações, cardápio.
- Por unidade: saldos, lotes, movimentações, pedidos, vendas, compras, caixa, contas, alertas.
- A unidade ativa vem no cabeçalho `X-Unit-Id` e **sempre** é validada contra o vínculo do usuário
  (`apps/core/tenancy.py`). Chaves estrangeiras recebidas pela API são filtradas pela organização
  (`TenantSerializer`), impedindo referenciar dados de outro estabelecimento.
- Permissões por código (ex.: `stock.adjust`, `purchases.approve`), com padrão por função e ajustes
  individuais (concedidas/revogadas). Toda view declara a permissão exigida; ausência = negado.

## 2. Estoque

### Unidades de medida
- Conversão só dentro da mesma dimensão (massa→g, volume→ml, contagem→un) pelo fator de cada unidade.
- Embalagens (caixa, fardo, pacote, saco...) **não têm quantidade fixa**: exigem cadastro de embalagem por
  produto (ex.: “1 cx = 24 un” para a cerveja). Sem cadastro, a conversão é recusada.
- Unidades incompatíveis (kg ↔ L) nunca são convertidas.

### Saldo, lotes e disponibilidade
- **Saldo físico** (`StockBalance`) = tudo que existe, incluindo lotes vencidos ainda não descartados.
- **Disponível** = físico − lotes vencidos. Lotes vencidos ficam isolados: não são consumidos, vendidos nem
  transferidos; só saem por descarte (perda “vencido”) ou ajuste de inventário.
- Um lote vencido é aquele com validade **anterior** à data local da unidade (vence hoje = ainda utilizável hoje,
  com conferência de conservação).
- Para lançamentos retroativos (ex.: importações), a validade é avaliada na data da operação.

### FEFO
Saídas consomem primeiro o lote com validade mais próxima; empate → recebido antes → id. Lotes sem
validade vão por último. Se faltar saldo em lotes:
- vendas/baixas automáticas **não bloqueiam a operação**: registram a saída sem lote (saldo pode ficar
  negativo) e o alerta “saldo negativo” orienta o inventário;
- saídas manuais (perdas, transferências) **são bloqueadas** se não houver saldo.
Quando um novo lote chega e existe consumo sem lote pendente, o lote absorve essa diferença (a mercadoria
que chega cobre o consumo já ocorrido) — o saldo total não muda.

### Movimentações e idempotência
- Toda alteração de saldo pertence a uma **operação** com chave única (ex.: `order:42:consume`,
  `sale:17:consume`, `receipt:9`, `inventory:3:15`). Repetir a mesma chave não gera nova movimentação.
- Movimentações são **imutáveis** (o modelo recusa edição e exclusão). Correções = estorno (operação inversa
  vinculada) ou ajuste de inventário, sempre com responsável, data e motivo.
- Concorrência: saldo e lotes são bloqueados (`SELECT … FOR UPDATE`) sempre na mesma ordem.
- Transferência: saída na origem e entrada vinculada no destino na mesma transação, preservando lote,
  validade e custo; a soma das saídas é igual à soma das entradas.

### Inventário
- Ao registrar a contagem de um item, guarda-se o saldo do sistema **naquele momento**.
- Ao finalizar (motivo obrigatório), aplica-se apenas a diferença `contado − sistema na contagem`, de forma
  que movimentações ocorridas durante a contagem não são perdidas.
- Diferença valorizada pelo custo de reposição do produto.

## 3. Custeio

- **Custo de reposição** (`Product.cost_price`): último custo de compra por unidade de estoque, atualizado a
  cada recebimento (ou ajuste manual auditado). Cada mudança gera histórico.
- **Custo teórico da receita** = Σ (quantidade bruta × custo de reposição); quantidade bruta =
  quantidade líquida ÷ (1 − perda de preparo %). **Custo por porção** = custo da receita ÷ rendimento.
- Mudou o custo de um insumo → todas as fichas que o usam são recalculadas e um registro de histórico é criado.
- **CMV real** = custo dos lotes efetivamente consumidos (FEFO), líquido de estornos. Assim o sistema
  distingue o custo teórico (ficha) do consumo real observado (relatório “Consumo teórico × real”).
- Valor do estoque = lotes ao custo do próprio lote + saldo sem lote ao custo de reposição.

## 4. Pedidos, cozinha e baixa automática

| Etapa | Efeito no estoque |
|---|---|
| Recebido | nenhum (entra apenas na projeção de compras) |
| Confirmado | baixa dos ingredientes por FEFO, **uma única vez** (`order:<id>:consume`) |
| Em preparo / Pronto / Saiu para entrega | nenhum |
| Entregue | registra a **venda** reutilizando a baixa já feita (sem nova baixa) |
| Cancelado antes do preparo (confirmado) | estorno integral — ingredientes voltam ao estoque |
| Cancelado em preparo ou depois | estorno + registro de **perda** “pedido cancelado em preparo” |

- Itens com modo “sem baixa automática” não movimentam estoque.
- Item com modo “ficha técnica” sem ingredientes: a venda é registrada, mas o item é marcado “baixa não
  confiável”, o CMV fica incompleto e um alerta “sem ficha técnica” é gerado.
- Itens de revenda (ex.: cerveja) baixam diretamente o produto.
- Transições permitidas são validadas no servidor; cozinha só altera “em preparo/pronto”; cancelar pedido
  confirmado exige `sales.cancel`.
- Painel da cozinha: atualização automática a cada 4 s com token de versão (só recarrega se algo mudou).
  WebSockets exigiriam infraestrutura adicional (Channels + Redis) — ver roadmap.

## 5. Vendas e definições de receita

- **Faturamento bruto** = Σ quantidade × preço de tabela dos itens das vendas concluídas.
- **Descontos** = descontos por item + desconto da venda.
- **Taxas** = valores pagos pelo estabelecimento (comissão de aplicativo, quando informada; pedidos do canal
  “aplicativo” usam o percentual configurado).
- **Receita líquida** = bruto − descontos − taxas + taxa de entrega cobrada do cliente.
- **Cancelamentos**: vendas canceladas saem dos totais e aparecem separadas. Cancelar uma venda pode
  estornar (produto devolvido intacto) ou registrar perda (padrão).
- **Ticket médio** = receita líquida ÷ número de vendas concluídas.
- Importação CSV: `id_venda` é o identificador único — reimportar não duplica. Códigos do PDV são mapeados ao
  cardápio (mapeamento ou “código no PDV”); códigos sem mapeamento são reportados.

## 6. Finanças

- **Margem de contribuição** = receita líquida − CMV.
- **Resultado operacional estimado** = margem de contribuição + outras receitas − despesas registradas
  (exceto compras de mercadorias, que entram pelo CMV quando consumidas). **Não é lucro líquido.**
- O resumo lista limitações automaticamente (ex.: sem folha, impostos ou despesas fixas registradas; vendas
  sem baixa completa).
- Cada recebimento de compra gera uma conta a pagar (frete incluído no primeiro recebimento; vencimento pelos
  dias informados nas condições de pagamento).
- Caixa: esperado = abertura + vendas em dinheiro + suprimentos − sangrias; diferença = contado − esperado.

## 7. Compras

### Comparador (menor custo total viável)
Para cada fornecedor, usa a cotação mais recente:
1. Converte a unidade de venda para a unidade de estoque (exige embalagem cadastrada quando necessário).
2. Quantidade a comprar = necessidade convertida, arredondada para cima em unidades inteiras quando a
   unidade é contagem/embalagem, respeitando a quantidade mínima.
3. Total = subtotal − desconto + frete (frete da cotação ou taxa padrão do fornecedor).
4. Inviável se: cotação vencida, conversão impossível ou quantidade disponível insuficiente.
5. Sinaliza: cotação desatualizada (configurável, padrão 7 dias), excedente pela quantidade mínima,
   pedido mínimo do fornecedor não atingido, validade curta.
6. Melhor = menor total entre as viáveis que atingem o pedido mínimo; se nenhuma atinge sozinha, a mais
   barata é indicada com aviso para combinar itens.
Para listas: compara “tudo em um fornecedor” e “melhor divisão” com frete contado uma vez por fornecedor,
consolidando fornecedores quando o frete economizado supera a diferença de preço.

### Lista inteligente
Para cada produto ativo, simula o estoque dia a dia de hoje até `prazo de entrega + dias de cobertura`:
- parte do estoque disponível em lotes não vencidos; lotes que vencem no período saem da simulação;
- soma compras pendentes (aprovadas/enviadas/parciais) **na data prevista de entrega** — nunca no estoque físico;
- consome a previsão diária: média por **dia de funcionamento** das últimas 4 semanas, com fatores por dia da
  semana quando há ≥ 28 dias de histórico; pedidos registrados ainda não confirmados entram no dia 0;
- sugere comprar quando a projeção cai abaixo do mínimo: `max(mínimo − projeção final, ideal − projeção na chegada)`;
- limita pela capacidade máxima e, para perecíveis, ao consumo previsto durante a validade típica;
- arredonda para a unidade de compra da melhor cotação e explica a recomendação.
Sem histórico: regra simples (repor até o ideal quando abaixo do mínimo) marcada como “estimativa limitada”.

### Pedido de compra
Rascunho → (aprovação se o total exceder o limite configurado e o usuário não tiver `purchases.approve`) →
aprovado → enviado → recebido parcial/total ou cancelado. Quem cria não aprova o próprio pedido acima do limite
(exceto o proprietário). Recebimento: lotes com validade (obrigatória para perecíveis), custo efetivo,
ocorrências automáticas de preço, quantidade, qualidade (recusas), validade curta e atraso; idempotente via
cabeçalho `Idempotency-Key`.

## 8. Alertas

Recalculados a cada consulta (no máximo a cada 60 s por unidade) e pelo comando `refresh_alerts`.
Cada condição tem uma **chave de deduplicação**; alertas que deixam de valer são encerrados automaticamente;
um alerta resolvido manualmente não reaparece por 24 h. Tipos: estoque abaixo do mínimo, risco de ruptura
(cobertura < prazo de entrega + 1 dia), vencendo em até 3 dias, vencido, saldo negativo, pedido demorado,
compra aguardando aprovação, entrega atrasada, cotação vencendo, aumento de custo acima do limite,
desperdício do mês acima do limite (% das compras), consumo incomum (> 150% da média semanal),
divergência de inventário (≥ R$ 50), item vendido sem ficha técnica e falha de integração/importação.

## 9. Assistente do Negócio

Classifica a pergunta por regras e executa consultas somente leitura. Cada resposta separa
**Fato** (dado registrado), **Estimativa** (projeção) e **Sugestão** (recomendação), com tabela e links para a
tela onde a ação é feita. Respeita as permissões do perfil e registra as perguntas para auditoria. Nunca altera
estoque nem cria compras.
