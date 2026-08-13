import json
from datetime import datetime, timezone

from openai import OpenAI

client = OpenAI()


FALLBACK_RESULT = {
    "intent": "UNKNOWN",
    "entities": {},
    "confidence": 0.0,
    "notes": "Fallback: risposta AI non interpretabile",
    "resume_suspended": None,
    "preferences": {}
}


def parse_intent(
    message: str,
    history=None,
    conversation=None,
    context=None,
    suspended=None,
    timezone_name: str = "Europe/Rome"
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

    Estrae anche eventuali preferenze data/ora espresse dal cliente
    (es. "sabato mattina") in forma strutturata — e' l'unico punto
    del sistema che traduce linguaggio naturale in date/orari
    (Sezione 13 dell'architettura: "AI#1 puo' produrre date, time,
    preferences"). N8N/WF10 lavora solo su questi dati gia' strutturati,
    non interpreta mai testo libero.
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

    today_iso = datetime.now(timezone.utc).date().isoformat()

    prompt = f"""
Sei il motore AI di un sistema di prenotazione WhatsApp.

Devi classificare il messaggio dell'utente considerando
anche la conversazione precedente.

DATA DI OGGI: {today_iso}
FUSO ORARIO DELL'ATTIVITA': {timezone_name}

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

Se il messaggio esprime (anche solo in parte) una preferenza di
data/ora per un appuntamento, valorizza "preferences" con date
ISO concrete (calcolate tu stesso a partire da DATA DI OGGI, es.
"sabato prossimo" -> la data reale del prossimo sabato). Lascia a
null i campi non espressi. Se il cliente non esprime alcuna
preferenza in questo messaggio, "preferences" deve essere {{}}.

- restituisci esclusivamente JSON valido, nessun testo fuori dal JSON

Formato:
{{
  "intent": "...",
  "entities": {{}},
  "confidence": 0.0,
  "notes": "...",
  "resume_suspended": true,
  "preferences": {{
    "date_from": "YYYY-MM-DD",
    "date_to": "YYYY-MM-DD",
    "time_from": "HH:MM",
    "time_to": "HH:MM",
    "days_of_week": ["saturday"],
    "flexible": false
  }}
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
    result.setdefault("preferences", {})
    result.setdefault("intent", "UNKNOWN")

    return result
