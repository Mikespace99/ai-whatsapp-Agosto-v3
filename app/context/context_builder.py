def build_context(
    tenant,
    customer,
    message,
    conversation,
    conversation_context,
    history=None,
    transitions=None,
    services=None,
    operators=None,
    faq=None,
    settings=None,
    whatsapp_account=None,
    calendar=None,
    suspended=None,
    blocked=None
):
    """
    Costruisce il Context ufficiale da passare ai workflow n8n
    (o da usare per chiamare AI#2 direttamente nei casi di blocco/
    abbandono, che saltano N8N).

    `suspended`: dict {"workflow":..., "step":..., "transition_id":...}
    se esiste una transition OPEN per questa conversazione, altrimenti None.

    `blocked`: dict {"attempted_intent":..., "reason":..., ...} se questo
    turno è stato bloccato per conflitto tra workflow stateful
    (Addendum v1.1, Sezione 5). Altrimenti None.
    """

    history = history or []
    transitions = transitions or []
    services = services or []
    operators = operators or []
    faq = faq or []
    settings = settings or {}
    calendar = calendar or {}

    received_at = (
        message.get("received_at")
        or message.get("created_at")
    )

    message_id = (
        message.get("message_id")
        or message.get("id")
    )

    # ---------------------------------------------------------
    # BOOKING — seedato dal working state persistito, non da zero
    # ---------------------------------------------------------
    # Addendum v1.1, Sezione 3: il working state dell'ultimo turno
    # sopravvive tra i messaggi finché il workflow stateful è in corso
    # (o durante un'interruzione stateless). Se non esiste ancora
    # (prima interazione, o appena ripulito dopo un booking concluso),
    # si ricade sui soli campi confermati in conversation_context.
    working_state = conversation_context.get("booking_working_state") or {}

    booking = {
        "intent": working_state.get("intent"),
        "service": working_state.get("service") or {
            "id": conversation_context.get("service_id"),
            "name": conversation_context.get("service_name")
        },
        "preferences": (
            working_state.get("preferences")
            or conversation_context.get("booking_preferences")
            or {}
        ),
        "candidate_slots": working_state.get("candidate_slots") or [],
        "selected_slot": (
            working_state.get("selected_slot")
            or conversation_context.get("selected_slot")
        ),
        "booking_result": working_state.get("booking_result")
    }

    context = {

        # ---------------------------------------------------------
        # TENANT
        # ---------------------------------------------------------
        "tenant": {
            "id": tenant.get("id"),
            "business_name": tenant.get("business_name"),
            "assistant_name": tenant.get("assistant_name"),

            "phone_number": (
                whatsapp_account.get("phone_number")
                if whatsapp_account
                else None
            ),

            "timezone": tenant.get("timezone"),
            "language": tenant.get("language")
        },

        # ---------------------------------------------------------
        # CUSTOMER
        # ---------------------------------------------------------
        "customer": {
            "id": customer.get("id"),
            "phone": customer.get("phone"),
            "name": customer.get("name")
        },

        # ---------------------------------------------------------
        # REQUEST
        # ---------------------------------------------------------
        "request": {
            "channel": "whatsapp",
            "message": message.get("message"),
            "received_at": received_at,
            "message_id": message_id
        },

        # ---------------------------------------------------------
        # CONVERSATION
        # ---------------------------------------------------------
        "conversation": {

            "state": {
                "status": conversation.get("status"),
                "workflow": conversation.get("workflow"),
                "step": conversation.get("step"),
                "retry_count": conversation.get("retry_count", 0),
                "waiting_since": conversation.get("waiting_since"),
                "timeout_at": conversation.get("timeout_at"),
                "last_message_at": conversation.get("last_message_at"),
                "created_at": conversation.get("created_at"),
                "updated_at": conversation.get("updated_at")
            },

            "context": {
                "service_id": conversation_context.get("service_id"),
                "service_name": conversation_context.get("service_name"),
                "operator_id": conversation_context.get("operator_id"),
                "selected_slot": conversation_context.get("selected_slot"),
                "booking_id": conversation_context.get("booking_id"),
                "language": conversation_context.get("language"),
                "customer_notes": conversation_context.get("customer_notes"),
                "last_intent": conversation_context.get("last_intent"),
                "ai_summary": conversation_context.get("ai_summary"),
                "booking_preferences": conversation_context.get(
                    "booking_preferences"
                )
            },

            # Workflow stateful interrotto in sospeso, se presente
            # (Addendum v1.1, Sezione 4). AI#1 lo usa per capire se il
            # messaggio corrente prosegue l'interruzione, riprende il
            # workflow sospeso, oppure lo abbandona.
            "suspended": suspended,

            "history": history,

            # Storico delle deviazioni / transizioni
            "transitions": transitions
        },

        # ---------------------------------------------------------
        # KNOWLEDGE
        # ---------------------------------------------------------
        "knowledge": {
            "services": services,
            "operators": operators,
            "faq": faq,
            "settings": settings
        },

        # ---------------------------------------------------------
        # BOOKING (working area, vedi sopra)
        # ---------------------------------------------------------
        "booking": booking,

        # ---------------------------------------------------------
        # AI
        # ---------------------------------------------------------
        "ai": {
            "intent": None,
            "entities": {},
            "confidence": None,
            "notes": None
        },

        # ---------------------------------------------------------
        # ROUTING — informazioni sulla decisione presa da Python,
        # usate solo da AI#2 (mai da N8N)
        # ---------------------------------------------------------
        "routing": {
            "blocked": blocked
        },

        # ---------------------------------------------------------
        # INTEGRATIONS
        # ---------------------------------------------------------
        "integrations": {
            "calendar": calendar,
            "whatsapp": {
                "phone_number": (
                    whatsapp_account.get("phone_number")
                    if whatsapp_account
                    else None
                ),
                "provider": (
                    whatsapp_account.get("provider")
                    if whatsapp_account
                    else None
                )
            }
        },

        # ---------------------------------------------------------
        # RUNTIME
        # ---------------------------------------------------------
        "runtime": {
            "request_received_at": received_at,
            "workflow_started_at": None,
            "current_timestamp": None,
            "timezone": tenant.get("timezone")
        },

        # ---------------------------------------------------------
        # METADATA
        # ---------------------------------------------------------
        "metadata": {
            "conversation_id": conversation.get("conversation_id"),
            "last_workflow": None,
            "last_node": None,
            "version": "2.0",
            "processed_at": None
        }
    }

    return context
