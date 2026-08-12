import os

import requests


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _auth_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }


def signup_user(email: str, password: str):
    """
    Crea un nuovo utente in Supabase Auth.

    Conferma email disattivata per ora (decisione presa insieme):
    l'utente puo' fare login subito dopo la registrazione, senza
    dover cliccare un link ricevuto via email. Va riattivata prima
    del lancio pubblico reale.

    Ritorna (True, user_dict) in caso di successo,
    (False, error_message) in caso di errore.
    """
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers=_auth_headers(),
        json={"email": email, "password": password},
        timeout=15
    )

    data = response.json()

    if response.status_code >= 400:
        return False, data.get("msg") or data.get("error_description") or "Errore di registrazione"

    return True, data


def login_user(email: str, password: str):
    """
    Autentica un utente esistente.

    Ritorna (True, {"access_token":..., "user": {...}}) in caso di
    successo, (False, error_message) in caso di credenziali errate.
    """
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers=_auth_headers(),
        json={"email": email, "password": password},
        timeout=15
    )

    data = response.json()

    if response.status_code >= 400:
        return False, data.get("msg") or data.get("error_description") or "Credenziali non valide"

    return True, data


def get_user_from_token(access_token: str):
    """
    Verifica un access_token e ritorna i dati dell'utente Supabase Auth
    (id, email, ...), oppure None se il token non e' valido/scaduto.
    """
    if not access_token:
        return None

    response = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {access_token}"
        },
        timeout=15
    )

    if response.status_code >= 400:
        return None

    return response.json()
