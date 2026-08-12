import json

from openai import OpenAI

client = OpenAI()


FALLBACK_RESULT = {
    "intent": "UNKNOWN",
    "entities": {},
    "confidence": 0.0,
    "notes": "Fallback: risposta AI non interpretabile",
    "resume_suspended": None
}


def parse_intent(
    message: str,
    history=None,
    conversation=None,
    context=None,
    suspended=None
) -> dict:
    """
    Analizza il messaggio dell'utente usando OpenAI (AI#1 — ingresso).

    `suspended`, se presente, descrive un workflow stateful interrotto
    (es. booking sospeso per una domanda FAQ), nel formato:
        {"workflow": "BOOKING", "step": "WAITING_SLOT_SELECTION"}

    In quel caso il modello deve anche dire se il messaggio corrente
    sembra rivolto a riprendere quel workflow sospeso
    (campo "resume_suspended": true/false), senza mai farlo in modo
    implicito o automatico — la decisione resta esplicita nel JSON.
    """

    history = history or []

    # Il messaggio corrente arriva già separatamente come "MESSAGGIO
    # ATTUALE": escluderlo dalla history evita di mostrarlo due volte
    # nello stesso prompt (era una ridondanza nella versione precedente).
    history_without_current = history[:-1] if history else []

    history_text = "\n".join(
        f"{item['role']}: {item['message']}"
        for item in history_without_current
    )

    conversation_state = {
        "workflow": conversation.get("workflow") if conversation else None,
        "step": conversation.get("step") if conversation else None,
    }

    suspended_text = (
        json.dumps(suspended, ensure_ascii=False)
        if suspended
        else "nessuno"
    )

    prompt = f"""
Sei il motore AI di un sistema di prenotazione WhatsApp.

Devi classificare il messaggio dell'utente considerando
anche la conversazione precedente.

CONVERSATION STATE ATTUALE:
{json.dumps(conversation_state, ensure_ascii=False)}

WORKFLOW SOSPESO (interrotto da una domanda intermedia, se presente):
{suspended_text}

CONTEXT:
{json.dumps(context or {}, ensure_ascii=False)}

HISTORY (senza il messaggio corrente):
{history_text}

MESSAGGIO ATTUALE:
{message}

Intent possibili:
- BOOKING_REQUEST
- BOOKING_CHANGE
- BOOKING_CANCEL
- INFORMATION_REQUEST
- ABANDON
- UNKNOWN

Regole:
- considera sempre la conversazione precedente
- una frase come "sabato mattina" può essere una risposta
  ad una precedente richiesta di prenotazione
- non classificare il messaggio isolatamente
- ABANDON si usa solo quando il cliente rifiuta esplicitamente
  di continuare quello che stava facendo (es. "lascia stare",
  "non mi interessa più", "annulla tutto")
- se esiste un WORKFLOW SOSPESO, valuta se il messaggio attuale
  sembra rivolto a riprenderlo (es. risponde direttamente alla
  domanda che era rimasta in sospeso) oppure se è ancora
  un'altra domanda indipendente. Imposta "resume_suspended" di
  conseguenza. Se non c'è nessun workflow sospeso, imposta
  "resume_suspended" a null.
- NON dare per scontato un ritorno al workflow sospeso solo perché
  il cliente ha risposto qualcosa di generico tipo "ok" o "grazie":
  in quel caso "resume_suspended" deve restare false.
- restituisci esclusivamente JSON valido, nessun testo fuori dal JSON

Formato:
{{
  "intent": "...",
  "entities": {{}},
  "confidence": 0.0,
  "notes": "...",
  "resume_suspended": true
}}
"""

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        result = json.loads(response.output_text)

    except Exception as error:
        print(f"[ERROR] parse_intent fallito: {error}")
        return dict(FALLBACK_RESULT)

    # Difesa minima sulla forma del risultato, senza essere troppo rigidi:
    # se il modello dimentica un campo, non deve far esplodere la pipeline.
    result.setdefault("entities", {})
    result.setdefault("confidence", None)
    result.setdefault("notes", None)
    result.setdefault("resume_suspended", None)
    result.setdefault("intent", "UNKNOWN")

    return result
