from fastapi import Request

from app.web.auth.supabase_auth import get_user_from_token


SESSION_COOKIE_NAME = "sb_access_token"
SESSION_MAX_AGE_SECONDS = 3600


def get_current_auth_user(request: Request):
    """
    Legge il cookie di sessione e verifica il token con Supabase Auth.
    Ritorna il dict utente Supabase Auth, o None se non autenticato.
    """
    access_token = request.cookies.get(SESSION_COOKIE_NAME)
    return get_user_from_token(access_token)


def set_session_cookie(response, access_token: str):
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_SECONDS
    )
    return response
