import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("mise.api")


class BusinessError(Exception):
    """Violação de regra de negócio. Vira HTTP 400 com mensagem clara."""

    def __init__(self, message, code="business_rule", field=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


def api_exception_handler(exc, context):
    if isinstance(exc, BusinessError):
        body = {"detail": exc.message, "code": exc.code}
        if exc.field:
            body["field"] = exc.field
        return Response(body, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Erro não tratado na API", exc_info=exc)
        return Response(
            {"detail": "Ocorreu um erro inesperado. A equipe técnica foi notificada pelos logs."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response
