import uuid
from datetime import datetime, timedelta, timezone

from app.supabase_client import supabase


CONVERSATION_TIMEOUT_MINUTES = 15


# ==================================================
# CONVERSATION HISTORY
# ==================================================

def get_conversation_history(conversation_id):
    response = (
        supabase
        .table("conversation_messages")
        .select("id, role, message, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )

    return [
        {
            "id": row["id"],
            "role": row["role"],
            "message": row["message"],
            "timestamp": row["created_at"]
        }
        for row in (response.data or [])
    ]


# ==================================================
# TRANSITIONS (meccanismo di interruzione/ripresa)
# ==================================================

def get_conversation_transitions(conversation_id):
    response = (
        supabase
        .table("conversation_transition")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )

    return response.data or []


def get_open_transition(conversation_id):
    """
    Ritorna l'UNICA transition OPEN per questa conversazione, se esiste.

    Modello a un livello (Addendum v1.1, Sezione 4): può esisterne al
    massimo una per volta.
    """
    response = (
        supabase
        .table("conversation_transition")
        .select("*")
        .eq("conversation_id", conversation_id)
        .eq("status", "OPEN")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def open_transition(
    conversation_id: str,
    tenant_id: str,
    resume_workflow: str,
    resume_step: str,
    reason: str = ""
):
    """
    Apre una transition OPEN quando si esce da un workflow stateful
    per un'interruzione (es. FAQ). resume_workflow/resume_step sono
    dove tornare, non dove si sta andando.
    """
    response = (
        supabase
        .table("conversation_transition")
        .insert({
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "type": "INTERRUPTION",
            "reason": reason,
            "from_workflow": resume_workflow,
            "from_step": resume_step,
            "resume_workflow": resume_workflow,
            "resume_step": resume_step,
            "status": "OPEN"
        })
        .execute()
    )

    return response.data[0] if response.data else None


def resolve_transition(transition_id: str, new_status: str):
    """new_status atteso: 'RESUMED' oppure 'ABANDONED'."""
    response = (
        supabase
        .table("conversation_transition")
        .update({"status": new_status})
        .eq("id", transition_id)
        .execute()
    )

    return response.data[0] if response.data else None


# ==================================================
# CONVERSATION (con gestione timeout)
# ==================================================

def _is_stale(conversation: dict) -> bool:
    last_activity = (
        conversation.get("last_message_at")
        or conversation.get("updated_at")
        or conversation.get("created_at")
    )

    if not last_activity:
        # Nessun timestamp disponibile: non rischiamo di riesumare
        # una conversazione di cui non sappiamo l'età.
        return True

    try:
        last_activity_dt = datetime.fromisoformat(
            last_activity.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        return True

    if last_activity_dt.tzinfo is None:
        last_activity_dt = last_activity_dt.replace(tzinfo=timezone.utc)

    elapsed = datetime.now(timezone.utc) - last_activity_dt

    return elapsed >= timedelta(minutes=CONVERSATION_TIMEOUT_MINUTES)


def close_conversation(conversation_id: str):
    response = (
        supabase
        .table("conversation_state")
        .update({"status": "CLOSED"})
        .eq("conversation_id", conversation_id)
        .execute()
    )

    return response.data[0] if response.data else None


def touch_conversation(conversation_id: str):
    """
    Aggiorna last_message_at ad ogni messaggio in ingresso, a prescindere
    dall'esito del resto della pipeline. Va chiamata il prima possibile
    dopo aver identificato la conversazione.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    response = (
        supabase
        .table("conversation_state")
        .update({"last_message_at": now_iso})
        .eq("conversation_id", conversation_id)
        .execute()
    )

    return response.data[0] if response.data else None


def get_or_create_conversation(tenant_id: str, customer_id: str):
    """
    Riusa una conversazione ACTIVE solo se non è scaduta per timeout
    (Addendum v1.1, Sezione 1). Se scaduta, la chiude esplicitamente
    e ne crea una nuova pulita.
    """
    response = (
        supabase
        .table("conversation_state")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("customer_id", customer_id)
        .eq("status", "ACTIVE")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if response.data:
        existing = response.data[0]

        if not _is_stale(existing):
            return existing

        # Conversazione scaduta: la chiudiamo esplicitamente
        # (non la lasciamo "scaduta ma non dichiarata").
        close_conversation(existing["conversation_id"])

    conversation_id = str(uuid.uuid4())

    response = (
        supabase
        .table("conversation_state")
        .insert({
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "status": "ACTIVE",
            "workflow": "IDLE",
            "step": "NONE",
            "retry_count": 0
        })
        .execute()
    )

    return response.data[0]


def get_or_create_context(conversation_id: str, language: str):

    response = (
        supabase
        .table("conversation_context")
        .select("*")
        .eq("conversation_id", conversation_id)
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]

    response = (
        supabase
        .table("conversation_context")
        .insert({
            "conversation_id": conversation_id,
            "service_id": None,
            "service_name": None,
            "operator_id": None,
            "selected_slot": None,
            "booking_id": None,
            "booking_preferences": {
                "date_from": None,
                "date_to": None,
                "time_from": None,
                "time_to": None,
                "days_of_week": [],
                "flexible": True
            },
            "booking_working_state": None,
            "language": language,
            "customer_notes": None,
            "last_intent": None,
            "ai_summary": None
        })
        .execute()
    )

    return response.data[0]


# ==================================================
# PERSISTENZA CONTEXT (memoria + working state)
# ==================================================

ALLOWED_CONTEXT_FIELDS = {
    "service_id",
    "service_name",
    "operator_id",
    "selected_slot",
    "booking_id",
    "booking_preferences",
    "language",
    "customer_notes",
    "last_intent",
    "ai_summary"
}


def update_conversation_context(
    conversation_id: str,
    updated_context: dict,
    previous_context: dict = None
):
    """
    Persiste conversation.context restituito da N8N + il working state
    del booking corrente (Addendum v1.1, Sezione 3).

    `updated_context` è l'intero Context ufficiale restituito da N8N
    (contiene sia "conversation" che "booking" a livello radice).

    Se `previous_context` è passato, logga un warning quando un campo
    precedentemente valorizzato torna vuoto (Fase 3 del piano:
    Opzione A + rete di sicurezza via log, non blocco).
    """
    if not updated_context:
        return None

    conversation_section = updated_context.get("conversation", {})
    conversation_context = conversation_section.get("context", {})
    booking = updated_context.get("booking", {})

    if not conversation_context:
        return None

    update_data = {
        key: conversation_context[key]
        for key in ALLOWED_CONTEXT_FIELDS
        if key in conversation_context
    }

    # Il working state del booking viene sempre allineato
    # all'ultimo oggetto booking restituito da N8N.
    update_data["booking_working_state"] = booking or None

    if previous_context:
        for key, new_value in update_data.items():
            old_value = previous_context.get(key)
            if old_value and not new_value:
                print(
                    f"[WARNING] conversation_context.{key} passa da "
                    f"valorizzato a vuoto per conversation_id={conversation_id}. "
                    f"Verificare il workflow N8N che ha generato questa risposta."
                )

    if not update_data:
        return None

    response = (
        supabase
        .table("conversation_context")
        .update(update_data)
        .eq("conversation_id", conversation_id)
        .execute()
    )

    return response.data[0] if response.data else None


def set_service(conversation_id: str, service_id: str, service_name: str):
    """
    Python risolve il servizio a partire dalle entities di AI#1
    (Context Contract v2, Sezione 5): è di sua competenza diretta,
    non deve passare da N8N per essere scritto.
    """
    response = (
        supabase
        .table("conversation_context")
        .update({
            "service_id": service_id,
            "service_name": service_name
        })
        .eq("conversation_id", conversation_id)
        .execute()
    )

    return response.data[0] if response.data else None


def clear_booking_working_state(conversation_id: str):
    """
    Azzera il working state del booking. Da chiamare quando:
    - il workflow raggiunge uno step terminale (BOOKED/CANCELLED)
    - scatta un abbandono esplicito
    (Addendum v1.1, Sezione 3 — tabella "quando si azzera").
    """
    response = (
        supabase
        .table("conversation_context")
        .update({"booking_working_state": None})
        .eq("conversation_id", conversation_id)
        .execute()
    )

    return response.data[0] if response.data else None


# ==================================================
# CONVERSATION STATE (workflow/step)
# ==================================================

def update_conversation_state(
    conversation_id: str,
    workflow: str = None,
    step: str = None
):
    """
    Aggiorna SOLO workflow/step. La gestione delle transition
    (OPEN/RESUMED/ABANDONED) è responsabilità esplicita del chiamante
    (main.py), non di questa funzione — per evitare l'ambiguità
    resume_workflow/resume_step riscontrata nella versione precedente.
    """
    response = (
        supabase
        .table("conversation_state")
        .update({
            "workflow": workflow,
            "step": step
        })
        .eq("conversation_id", conversation_id)
        .execute()
    )

    return response.data[0] if response.data else None


def save_message(conversation_id: str, role: str, message: str):

    response = (
        supabase
        .table("conversation_messages")
        .insert({
            "conversation_id": conversation_id,
            "role": role,
            "message": message
        })
        .execute()
    )

    return response.data[0]
