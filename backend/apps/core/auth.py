from rest_framework.authentication import SessionAuthentication


class CsrfSessionAuthentication(SessionAuthentication):
    """Autenticação por sessão (cookie HttpOnly) com verificação de CSRF obrigatória."""
