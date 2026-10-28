"""Provedores do Assistente do Negócio.

`RulesProvider` (padrão) responde apenas com regras e consultas ao banco.
Para ativar um modelo de linguagem, implemente `rewrite()` em um provedor externo e
configure `ASSISTANT_PROVIDER` e `ASSISTANT_API_KEY` no ambiente do BACKEND.
O provedor externo recebe somente a pergunta e a resposta factual já calculada,
nunca credenciais ou acesso de escrita ao banco.
"""

from django.conf import settings


class AssistantProvider:
    name = "base"

    def rewrite(self, question, factual_answer):
        raise NotImplementedError


class RulesProvider(AssistantProvider):
    name = "rules"

    def rewrite(self, question, factual_answer):
        return factual_answer


def get_provider():
    if settings.ASSISTANT_PROVIDER != "rules" and settings.ASSISTANT_API_KEY:
        # Ponto de extensão: retorne aqui a implementação do provedor externo configurado.
        # Enquanto não houver implementação, mantemos o modo local seguro.
        return RulesProvider()
    return RulesProvider()
