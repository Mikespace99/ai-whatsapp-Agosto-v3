import requests


def send_whatsapp_message(
    to: str,
    message: str,
    access_token: str,
    phone_number_id: str
):
    """
    Invia un messaggio WhatsApp usando le credenziali DEL TENANT
    (lette da whatsapp_accounts), non piu' variabili d'ambiente globali.

    Fix del gap multi-tenant: prima di questo fix, tutti i tenant
    avrebbero inviato messaggi dallo stesso numero (quello nelle env
    var), indipendentemente da quale tenant avesse ricevuto il messaggio.
    """
    if not access_token:
        raise RuntimeError(
            "access_token mancante per questo tenant "
            "(whatsapp_accounts.access_token non configurato)"
        )

    if not phone_number_id:
        raise RuntimeError(
            "phone_number_id mancante per questo tenant "
            "(whatsapp_accounts.phone_number_id non configurato)"
        )

    url = (
        f"https://graph.facebook.com/v23.0/"
        f"{phone_number_id}/messages"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": message
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20
    )

    print("=== WHATSAPP SEND ===")
    print(response.status_code)
    print(response.text)

    response.raise_for_status()

    return response.json()
