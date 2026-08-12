import os

import requests


N8N_WEBHOOK_URL = os.getenv(
    "N8N_WEBHOOK_URL",
    "https://karl66.app.n8n.cloud/webhook-test/ai.booking"
)


def send_context(context: dict):
    """
    Invia il Context a N8N e ritorna la risposta come dict.

    Ritorna None in caso di errore/timeout, invece di lasciare
    propagare l'eccezione: main.py deve poter gestire il fallimento
    con un messaggio di cortesia invece di un 500 verso Meta
    (che altrimenti ritenterebbe la consegna del webhook).
    """
    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=context,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.Timeout:
        print("[ERROR] send_context: timeout nella chiamata a N8N")
        return None

    except requests.exceptions.RequestException as error:
        print(f"[ERROR] send_context: errore nella chiamata a N8N: {error}")
        return None

    except ValueError as error:
        # response.json() fallito: N8N ha risposto con corpo non JSON
        print(f"[ERROR] send_context: risposta N8N non JSON: {error}")
        return None
