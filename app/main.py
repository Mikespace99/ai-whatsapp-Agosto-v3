import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse

from app.integrations.whatsapp_client import (
    send_whatsapp_message
)

from app.workflows.n8n_client import (
    send_context
)

from app.workflows.state_machine import (
    is_stateful,
    resolve_post_n8n_state
)

from app.context.context_builder import (
    build_context
)

from app.ai.intent_parser import (
    parse_intent
)

from app.ai.response_generator import (
    generate_response
)

from app.repositories.service_repository import (
    get_active_services,
    find_service_by_name
)

from app.repositories.tenant_repository import (
    get_whatsapp_account,
    get_tenant
)

from app.repositories.customer_repository import (
    get_or_create_customer
)

from app.repositories.conversation_repository import (
    get_or_create_conversation,
    get_or_create_context,
    update_conversation_context,
    set_service,
    save_message,
    get_conversation_transitions,
    get_conversation_history,
    get_open_transition,
    open_transition,
    resolve_transition,
    clear_booking_working_state,
    touch_conversation,
    update_conversation_state,
    try_claim_message
)


from app.web.routes import router as web_router


app = FastAPI(
    title="AI Booking Backend",
    version="0.2.0"
)

app.include_router(web_router)


# Intent che vogliono aprire/continuare un workflow stateful,
# mappati sul workflow che rappresentano.
STATEFUL_INTENT_TARGETS = {
    "BOOKING_REQUEST": "BOOKING",
    "BOOKING_CHANGE": "BOOKING",
    "BOOKING_CANCEL": "CANCELLATION"
}


# ==================================================
# HEALTH CHECK
# ==================================================

@app.get("/health")
def health():
    return {"status": "ok"}


# ==================================================
# WHATSAPP WEBHOOK VERIFICATION
# ==================================================

@app.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(request: Request):

    params = request.query_params

    mode = params.get("hub.mode")
    verify_token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    expected_token = os.getenv("WHATSAPP_VERIFY_TOKEN")

    if mode == "subscribe" and verify_token == expected_token:
        return PlainTextResponse(challenge)

    return PlainTextResponse("Verification failed", status_code=403)


# ==================================================
# WHATSAPP MESSAGE WEBHOOK
# ==================================================

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):

    payload = await request.json()

    print("=== WHATSAPP WEBHOOK ===")
    print(payload)

    message = extract_whatsapp_message(payload)

    if not message:
        print("Webhook ricevuto ma nessun messaggio gestibile.")
        return {"status": "ignored"}

    print("=== EXTRACTED MESSAGE ===")
    print(message)

    # Deduplicazione per message_id: se Meta ri-consegna lo stesso
    # webhook (perche' non ha ricevuto risposta in tempo, o per
    # qualunque altro motivo), questo messaggio viene ignorato invece
    # di essere rielaborato e reinviato una seconda volta al cliente.
    if not try_claim_message(message.get("message_id")):
        return {"status": "duplicate_ignored"}

    # Rispondiamo subito a Meta con 200 OK, ed elaboriamo il messaggio
    # in background. Questo riduce il rischio che Meta interpreti una
    # pipeline lenta (AI#1 + N8N + AI#2 + invio WhatsApp) come un
    # webhook non ricevuto e lo ri-consegni.
    background_tasks.add_task(process_message, message)

    return {"status": "accepted"}


# ==================================================
# ESTRAE IL MESSAGGIO DAL PAYLOAD META
# ==================================================

def extract_whatsapp_message(payload):

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]

        messages = value.get("messages")

        if not messages:
            return None

        whatsapp_message = messages[0]

        if whatsapp_message.get("type") != "text":
            return None

        metadata = value.get("metadata", {})

        business_phone = metadata.get("display_phone_number")
        user_phone = whatsapp_message.get("from")
        text = whatsapp_message["text"]["body"]
        timestamp = whatsapp_message.get("timestamp")

        if timestamp:
            received_at = datetime.fromtimestamp(
                int(timestamp), tz=timezone.utc
            ).isoformat()
        else:
            received_at = datetime.now(timezone.utc).isoformat()

        return {
            "to": business_phone,
            "from": user_phone,
            "message": text,
            "message_id": whatsapp_message.get("id"),
            "received_at": received_at
        }

    except (KeyError, IndexError, TypeError):
        return None


# ==================================================
# ROUTING - decide workflow/step PRIMA di chiamare N8N
# ==================================================

def determine_routing(intent_result, conversation, open_transition_row):
    """
    Applica le regole dell'Addendum Architetturale v1.1 (Sezioni 4-5):
    blocco di workflow stateful concorrenti, interruzioni a un livello,
    ripresa esplicita, abbandono esplicito.

    Ritorna un dict:
        new_workflow, new_step: da applicare PRIMA di chiamare N8N
        transition_action: None | "OPEN" | "RESUME" | "ABANDON"
        blocked: None o dict con i dettagli del blocco
        call_n8n: se False, il turno si risolve senza chiamare N8N
    """

    intent = intent_result.get("intent")
    resume_suspended = intent_result.get("resume_suspended")

    current_workflow = conversation.get("workflow")
    current_step = conversation.get("step")

    suspended_workflow = (
        open_transition_row.get("resume_workflow")
        if open_transition_row else None
    )

    current_is_stateful = is_stateful(current_workflow)
    suspended_is_stateful = is_stateful(suspended_workflow)

    in_progress_stateful = (
        current_workflow if current_is_stateful
        else (suspended_workflow if suspended_is_stateful else None)
    )

    requested_stateful = STATEFUL_INTENT_TARGETS.get(intent)

    routing = {
        "new_workflow": current_workflow,
        "new_step": current_step,
        "transition_action": None,
        "blocked": None,
        "call_n8n": True
    }

    # 1. BLOCCO - un workflow stateful diverso e' gia' in corso o sospeso
    if (
        requested_stateful
        and in_progress_stateful
        and requested_stateful != in_progress_stateful
    ):
        routing["blocked"] = {
            "attempted_intent": intent,
            "reason": "workflow_in_progress",
            "in_progress_workflow": in_progress_stateful
        }
        routing["call_n8n"] = False
        return routing

    # 2. ABBANDONO ESPLICITO
    if intent == "ABANDON":
        routing["new_workflow"] = "IDLE"
        routing["new_step"] = "NONE"
        routing["call_n8n"] = False
        if open_transition_row:
            routing["transition_action"] = "ABANDON"
        return routing

    # 3. RIPRESA DI UN WORKFLOW SOSPESO (mai automatica: solo se AI#1
    #    ha riconosciuto esplicitamente il contenuto come pertinente)
    if open_transition_row and resume_suspended:
        routing["new_workflow"] = open_transition_row.get("resume_workflow")
        routing["new_step"] = open_transition_row.get("resume_step")
        routing["transition_action"] = "RESUME"
        return routing

    # 4. NUOVA RICHIESTA / CONTINUAZIONE DI UN WORKFLOW STATEFUL
    if requested_stateful:
        if current_workflow != requested_stateful:
            routing["new_workflow"] = requested_stateful
            routing["new_step"] = "START"
        # Se gia' nello stesso workflow, lo step lo decide
        # resolve_post_n8n_state dopo la risposta di N8N.
        return routing

    # 5. DOMANDA INFO - eventuale apertura di un'interruzione
    if intent == "INFORMATION_REQUEST":
        if current_is_stateful:
            routing["transition_action"] = "OPEN"
        routing["new_workflow"] = "INFO"
        routing["new_step"] = "START"
        return routing

    # 6. UNKNOWN o non gestito -> nessun cambio, continuazione implicita
    return routing


def build_suspended_payload(transition_row):
    if not transition_row:
        return None

    return {
        "workflow": transition_row.get("resume_workflow"),
        "step": transition_row.get("resume_step"),
        "transition_id": transition_row.get("id")
    }


# ==================================================
# PIPELINE PRINCIPALE
# ==================================================

def process_message(message):

    # --------------------------------------------------
    # 1. IDENTIFICA ACCOUNT WHATSAPP
    # --------------------------------------------------

    whatsapp_account = get_whatsapp_account(message["to"])

    if not whatsapp_account:
        print("WhatsApp account non trovato:", message["to"])
        return {"status": "error", "error": "WhatsApp account non trovato"}

    tenant_id = whatsapp_account["tenant_id"]

    # --------------------------------------------------
    # 2. RECUPERA TENANT
    # --------------------------------------------------

    tenant = get_tenant(tenant_id)

    if not tenant:
        print("Tenant non trovato:", tenant_id)
        return {"status": "error", "error": "Tenant non trovato"}

    # --------------------------------------------------
    # 3. CUSTOMER
    # --------------------------------------------------

    customer = get_or_create_customer(tenant_id, message["from"])

    # --------------------------------------------------
    # 4. CONVERSATION (get_or_create_conversation gestisce
    #    gia' il timeout di 15 minuti internamente)
    # --------------------------------------------------

    conversation = get_or_create_conversation(tenant_id, customer["id"])

    # Registriamo l'attivita' SUBITO, indipendentemente da come
    # andra' il resto della pipeline (Addendum v1.1, Sezione 1).
    touch_conversation(conversation["conversation_id"])

    # --------------------------------------------------
    # 5. CONVERSATION CONTEXT
    # --------------------------------------------------

    conversation_context = get_or_create_context(
        conversation["conversation_id"],
        tenant["language"]
    )

    previous_context_snapshot = dict(conversation_context)

    # --------------------------------------------------
    # 6. SALVA MESSAGGIO USER
    # --------------------------------------------------

    conversation_message = save_message(
        conversation["conversation_id"],
        "user",
        message["message"]
    )

    # --------------------------------------------------
    # 7. HISTORY
    # --------------------------------------------------

    history = get_conversation_history(conversation["conversation_id"])

    # --------------------------------------------------
    # 8. TRANSITION SOSPESA (se esiste)
    # --------------------------------------------------

    open_transition_row = get_open_transition(conversation["conversation_id"])
    suspended = build_suspended_payload(open_transition_row)

    transitions_log = get_conversation_transitions(
        conversation["conversation_id"]
    )

    # --------------------------------------------------
    # 9. SERVIZI
    # --------------------------------------------------

    services = get_active_services(tenant_id)

    # --------------------------------------------------
    # 10. CONTEXT PER AI#1 (solo di supporto all'interpretazione)
    # --------------------------------------------------

    context_for_ai1 = build_context(
        tenant=tenant,
        customer=customer,
        message=message,
        conversation=conversation,
        conversation_context=conversation_context,
        history=history,
        transitions=transitions_log,
        services=services,
        whatsapp_account=whatsapp_account,
        suspended=suspended
    )

    # --------------------------------------------------
    # 11. AI#1 - INTERPRETA IL MESSAGGIO
    # --------------------------------------------------

    intent_result = parse_intent(
        message=message["message"],
        history=history,
        conversation=conversation,
        context=context_for_ai1,
        suspended=suspended
    )

    # --------------------------------------------------
    # 12. SERVIZIO - di competenza diretta di Python (Context Contract v2)
    # --------------------------------------------------

    entities = intent_result.get("entities", {})
    service_name = entities.get("service_name")

    if service_name:
        resolved_service = find_service_by_name(tenant_id, service_name)

        if resolved_service:
            set_service(
                conversation["conversation_id"],
                resolved_service["id"],
                resolved_service["name"]
            )
            conversation_context["service_id"] = resolved_service["id"]
            conversation_context["service_name"] = resolved_service["name"]

    # --------------------------------------------------
    # 13. ROUTING - blocco / interruzione / ripresa / abbandono
    # --------------------------------------------------

    routing = determine_routing(
        intent_result,
        conversation,
        open_transition_row
    )

    if routing["transition_action"] == "OPEN":
        open_transition(
            conversation["conversation_id"],
            tenant_id,
            resume_workflow=conversation["workflow"],
            resume_step=conversation["step"],
            reason=f"Interruzione per intent {intent_result.get('intent')}"
        )

    elif routing["transition_action"] == "RESUME":
        resolve_transition(open_transition_row["id"], "RESUMED")

    elif routing["transition_action"] == "ABANDON":
        resolve_transition(open_transition_row["id"], "ABANDONED")
        clear_booking_working_state(conversation["conversation_id"])
        conversation_context["booking_working_state"] = None

    # Persiste workflow/step decisi PRIMA di chiamare N8N
    updated_conversation = update_conversation_state(
        conversation["conversation_id"],
        workflow=routing["new_workflow"],
        step=routing["new_step"]
    )

    if updated_conversation:
        conversation = updated_conversation
    else:
        conversation["workflow"] = routing["new_workflow"]
        conversation["step"] = routing["new_step"]

    # La transition sospesa potrebbe essere cambiata (aperta/chiusa) sopra
    open_transition_row = get_open_transition(conversation["conversation_id"])
    suspended = build_suspended_payload(open_transition_row)

    transitions_log = get_conversation_transitions(
        conversation["conversation_id"]
    )

    # --------------------------------------------------
    # 14. CASO A - BLOCCO o ABBANDONO: nessuna chiamata a N8N
    # --------------------------------------------------

    if not routing["call_n8n"]:

        context = build_context(
            tenant=tenant,
            customer=customer,
            message=message,
            conversation=conversation,
            conversation_context=conversation_context,
            history=history,
            transitions=transitions_log,
            services=services,
            whatsapp_account=whatsapp_account,
            suspended=suspended,
            blocked=routing["blocked"]
        )
        context["ai"] = intent_result

        assistant_message = generate_response(context)
        should_send = True

        return finalize_turn(
            message=message,
            customer=customer,
            conversation=conversation,
            conversation_context=conversation_context,
            conversation_message=conversation_message,
            history=history,
            transitions=transitions_log,
            context=context,
            intent_result=intent_result,
            services=services,
            n8n_response=None,
            assistant_message=assistant_message,
            should_send=should_send
        )

    # --------------------------------------------------
    # 15. CASO B - FLUSSO NORMALE: costruisci Context e chiama N8N
    # --------------------------------------------------

    context = build_context(
        tenant=tenant,
        customer=customer,
        message=message,
        conversation=conversation,
        conversation_context=conversation_context,
        history=history,
        transitions=transitions_log,
        services=services,
        whatsapp_account=whatsapp_account,
        suspended=suspended
    )
    context["ai"] = intent_result

    n8n_response = send_context(context)

    # --------------------------------------------------
    # 16. N8N NON DISPONIBILE / RISPOSTA MALFORMATA
    # --------------------------------------------------

    if not n8n_response or not n8n_response.get("context"):

        error_context = build_context(
            tenant=tenant,
            customer=customer,
            message=message,
            conversation=conversation,
            conversation_context=conversation_context,
            history=history,
            transitions=transitions_log,
            services=services,
            whatsapp_account=whatsapp_account,
            suspended=suspended,
            blocked={
                "attempted_intent": intent_result.get("intent"),
                "reason": "n8n_unavailable"
            }
        )
        error_context["ai"] = intent_result

        assistant_message = generate_response(error_context)

        return finalize_turn(
            message=message,
            customer=customer,
            conversation=conversation,
            conversation_context=conversation_context,
            conversation_message=conversation_message,
            history=history,
            transitions=transitions_log,
            context=error_context,
            intent_result=intent_result,
            services=services,
            n8n_response=n8n_response,
            assistant_message=assistant_message,
            should_send=True
        )

    # --------------------------------------------------
    # 17. PERSISTE IL CONTEXT COMPLETO RESTITUITO DA N8N
    # --------------------------------------------------

    updated_context = n8n_response["context"]

    persisted_context = update_conversation_context(
        conversation["conversation_id"],
        updated_context,
        previous_context=previous_context_snapshot
    )

    if persisted_context:
        conversation_context = persisted_context

    returned_booking = updated_context.get("booking", {})

    # --------------------------------------------------
    # 18. DERIVA LO STEP DAL BOOKING RESTITUITO (Fase 4)
    #     e applica l'Opzione B se il workflow e' concluso (Sezione 2)
    # --------------------------------------------------

    step_this_turn, persisted_workflow, persisted_step, should_reset = (
        resolve_post_n8n_state(routing["new_workflow"], returned_booking)
    )

    update_conversation_state(
        conversation["conversation_id"],
        workflow=persisted_workflow,
        step=persisted_step
    )

    if should_reset:
        clear_booking_working_state(conversation["conversation_id"])
        conversation_context["booking_working_state"] = None

    # Per QUESTO turno, AI#2 deve vedere lo step "vero" appena
    # raggiunto (es. BOOKED), anche se sulla conversazione persistiamo
    # gia' lo stato di riposo (IDLE) per il turno successivo.
    conversation["workflow"] = routing["new_workflow"]
    conversation["step"] = step_this_turn

    context = updated_context
    context["conversation"]["state"]["workflow"] = routing["new_workflow"]
    context["conversation"]["state"]["step"] = step_this_turn
    context["ai"] = intent_result
    context["routing"] = {"blocked": None}

    # --------------------------------------------------
    # 19. AI#2 - GENERA LA RISPOSTA DAL CONTEXT FINALE
    # --------------------------------------------------

    assistant_message = generate_response(context)
    should_send = n8n_response.get("send", True)

    return finalize_turn(
        message=message,
        customer=customer,
        conversation=conversation,
        conversation_context=conversation_context,
        conversation_message=conversation_message,
        history=history,
        transitions=transitions_log,
        context=context,
        intent_result=intent_result,
        services=services,
        n8n_response=n8n_response,
        assistant_message=assistant_message,
        should_send=should_send
    )


# ==================================================
# SALVA + INVIA LA RISPOSTA, COSTRUISCE IL RISULTATO FINALE
# ==================================================

def finalize_turn(
    message,
    customer,
    conversation,
    conversation_context,
    conversation_message,
    history,
    transitions,
    context,
    intent_result,
    services,
    n8n_response,
    assistant_message,
    should_send
):
    whatsapp_response = None

    if assistant_message and should_send:

        save_message(
            conversation["conversation_id"],
            "assistant",
            assistant_message
        )

        try:
            whatsapp_response = send_whatsapp_message(
                to=message["from"],
                message=assistant_message
            )
        except Exception as error:
            print(f"[ERROR] invio WhatsApp fallito: {error}")

    return {
        "status": "success",
        "message": message,
        "customer": customer,
        "conversation": conversation,
        "conversation_context": conversation_context,
        "conversation_message": conversation_message,
        "history": history,
        "transitions": transitions,
        "context": context,
        "intent_result": intent_result,
        "services": services,
        "n8n_response": n8n_response,
        "assistant_message": assistant_message,
        "whatsapp_response": whatsapp_response
    }
