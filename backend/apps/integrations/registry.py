"""Catálogo de integrações. Cada conector implementa uma interface simples e é opcional.

Interfaces previstas:
- PosConnector.fetch_sales(since) -> lista de vendas no formato do importador CSV
  (id_venda, data_hora, canal, itens...). As vendas entram por `apps.sales.services.register_sale`,
  com idempotência por `external_id`.
- SupplierConnector.fetch_quotes(products) -> cotações com data de referência, gravadas como
  `Quotation(source="api")`.
- NotificationChannel.send(user, alert) -> envio por e-mail/WhatsApp/push autorizado.
- AssistantProvider.rewrite(question, answer) -> ver apps/analytics/providers.py.
"""

CATALOG = [
    {"kind": "pos", "provider": "csv", "name": "Importação de vendas por CSV", "available": True,
     "description": "Disponível: importe o relatório de vendas do seu PDV em Vendas > Importar CSV.", "requires": []},
    {"kind": "pos", "provider": "generic_api", "name": "PDV via API (genérico)", "available": False,
     "description": "Requer credenciais e documentação da API do PDV usado pelo estabelecimento.",
     "requires": ["URL da API", "Token de acesso (variável de ambiente)", "Mapeamento de produtos"]},
    {"kind": "supplier", "provider": "supplier_api", "name": "Catálogo/cotações de fornecedor via API", "available": False,
     "description": "Requer acordo e API autorizada do fornecedor ou distribuidor.", "requires": ["API autorizada", "Chave de acesso"]},
    {"kind": "notification", "provider": "email", "name": "Alertas por e-mail", "available": True,
     "description": "Usa o servidor SMTP configurado em EMAIL_BACKEND/EMAIL_HOST. Ative por usuário em Preferências de alertas.",
     "requires": ["Configuração SMTP no backend"]},
    {"kind": "notification", "provider": "whatsapp", "name": "Alertas por WhatsApp", "available": False,
     "description": "Requer conta WhatsApp Business API e consentimento dos usuários.", "requires": ["WhatsApp Business API"]},
    {"kind": "ai", "provider": "llm", "name": "Modelo de linguagem para o Assistente", "available": False,
     "description": "O assistente funciona localmente por regras. Um provedor de IA pode reescrever as respostas usando apenas dados já calculados.",
     "requires": ["ASSISTANT_PROVIDER", "ASSISTANT_API_KEY (somente no backend)"]},
]
