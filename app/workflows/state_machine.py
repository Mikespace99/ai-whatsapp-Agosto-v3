"""
Regole di stato della conversazione.

Questo modulo NON parla con Supabase né con N8N: contiene solo
le regole pure decise nell'Addendum Architetturale v1.1.

Principio guida (Sezione 12 del Freeze):
N8N non diventa mai proprietario dello stato persistente.
Python decide sempre workflow/step, anche dopo la risposta di N8N,
sulla base di ciò che N8N ha restituito in `booking`.
"""

STATEFUL_WORKFLOWS = {"BOOKING", "CANCELLATION"}

TERMINAL_STEPS = {
    "BOOKING": "BOOKED",
    "CANCELLATION": "CANCELLED",
}


def is_stateful(workflow: str) -> bool:
    """Un workflow è 'stateful' se richiede più turni per concludersi."""
    return workflow in STATEFUL_WORKFLOWS


def is_terminal(workflow: str, step: str) -> bool:
    """True se lo step rappresenta la conclusione naturale del workflow."""
    return TERMINAL_STEPS.get(workflow) == step


def derive_next_step(workflow: str, booking: dict) -> str:
    """
    Deriva lo step persistente a partire da ciò che N8N ha restituito
    in `booking`, SENZA fidarsi di un eventuale step suggerito da N8N.

    Fase 4 del piano di finalizzazione: Python deriva lo step da regole
    proprie basate su cosa è presente in booking, non da un campo che
    N8N potrebbe scrivere direttamente.
    """
    booking = booking or {}

    if workflow == "BOOKING":

        if booking.get("booking_result"):
            return "BOOKED"

        if booking.get("selected_slot"):
            return "WAITING_CONFIRMATION"

        if booking.get("candidate_slots"):
            return "WAITING_SLOT_SELECTION"

        service = booking.get("service") or {}
        if not service.get("id"):
            return "WAITING_SERVICE"

        return "WAITING_SLOT_SELECTION"

    if workflow == "CANCELLATION":

        booking_result = booking.get("booking_result") or {}
        if booking_result.get("cancelled"):
            return "CANCELLED"

        if booking.get("selected_slot") or booking.get("service"):
            return "WAITING_CONFIRMATION"

        return "START"

    if workflow == "INFO":
        # INFO si risolve sempre nello stesso turno in cui N8N risponde.
        return "ANSWERED"

    # IDLE o qualunque altro caso non gestito esplicitamente.
    return "NONE"


def resolve_post_n8n_state(workflow: str, booking: dict):
    """
    Punto unico da cui main.py ottiene lo stato "vero" da persistere
    dopo la risposta di N8N, includendo la pulizia dell'Opzione B
    (Sezione 2 dell'addendum): se il workflow è arrivato a uno step
    terminale, la conversazione torna a IDLE, non resta bloccata lì.

    Ritorna una tupla:
        (step_per_ai2, persisted_workflow, persisted_step, should_reset)

    - step_per_ai2: lo step "vero" di questo turno (es. BOOKED), da
      mostrare ad AI#2 così può congratularsi/confermare.
    - persisted_workflow/persisted_step: cosa va scritto su Supabase
      per il turno SUCCESSIVO (già resettato a IDLE se concluso).
    - should_reset: True se questo turno ha concluso il workflow e va
      quindi ripulito il booking_working_state.
    """
    step_this_turn = derive_next_step(workflow, booking)

    if is_terminal(workflow, step_this_turn):
        return step_this_turn, "IDLE", "NONE", True

    return step_this_turn, workflow, step_this_turn, False
