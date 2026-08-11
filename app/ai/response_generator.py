import json

from openai import OpenAI

client = OpenAI()


FALLBACK_MESSAGE_BY_LANGUAGE = {
    "it": "Un attimo, sto verificando. Le rispondo a breve.",
    "en": "One moment, I'm checking. I'll get back to you shortly."
}


def generate_response(context: dict) -> str:
    """
    AI#2 — uscita. Riceve il Context finale (dopo la persistenza
    post-N8N, o dopo un blocco/abbandono) e genera il messaggio in
    linguaggio naturale da inviare su WhatsApp.

    Punto architetturale vincolante (Addendum v1.1 / documento di
    freeze, Sezione 14-15): la risposta NON viene mai letta
    direttamente da un campo "message" prodotto da N8N. Nasce sempre
    qui, a valle, con visibilità sul Context completo.
    """

    tenant = context.get("tenant", {})
    customer = context.get("customer", {})
    conversation = context.get("conversation", {})
    knowledge = context.get("knowledge", {})
    booking = context.get("booking", {})
    routing = context.get("routing", {})

    language = tenant.get("language", "it")

    prompt = f"""
Sei {tenant.get('assistant_name') or 'l\'assistente'} di
{tenant.get('business_name') or 'questa attività'}, un assistente
WhatsApp per la prenotazione di appuntamenti.

Rispondi SEMPRE in lingua: {language}
Tono: cordiale, professionale, colloquiale come una reception reale,
frasi brevi, nessuna intestazione o elenco puntato inutile.

CLIENTE:
{json.dumps(customer, ensure_ascii=False)}

STATO CONVERSAZIONE:
{json.dumps(conversation.get('state', {}), ensure_ascii=False)}

MEMORIA CONVERSAZIONE:
{json.dumps(conversation.get('context', {}), ensure_ascii=False)}

ESITO DEL WORKFLOW (booking):
{json.dumps(booking, ensure_ascii=False)}

FAQ DISPONIBILI (usale solo se pertinenti):
{json.dumps(knowledge.get('faq', []), ensure_ascii=False)}

SERVIZI DISPONIBILI:
{json.dumps(knowledge.get('services', []), ensure_ascii=False)}

RICHIESTA BLOCCATA (se presente, spiega gentilmente che si
completa prima quello che è già in corso, citando cosa si sta
già facendo):
{json.dumps(routing.get('blocked'), ensure_ascii=False)}

ULTIMO MESSAGGIO DEL CLIENTE:
{context.get('request', {}).get('message', '')}

Genera SOLO il testo del messaggio da inviare su WhatsApp,
nessun JSON, nessuna spiegazione, nessuna virgoletta attorno al testo.
"""

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        text = (response.output_text or "").strip()

        if not text:
            raise ValueError("Risposta vuota da AI#2")

        return text

    except Exception as error:
        print(f"[ERROR] generate_response (AI#2) fallito: {error}")
        return FALLBACK_MESSAGE_BY_LANGUAGE.get(
            language,
            FALLBACK_MESSAGE_BY_LANGUAGE["it"]
        )
