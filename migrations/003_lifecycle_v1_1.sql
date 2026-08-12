-- Migration 003 — supporto ad Addendum Architetturale v1.1
-- Da eseguire prima di deployare il nuovo codice.

-- 1. Working state del booking tra un turno e l'altro (Sezione 3 addendum)
ALTER TABLE conversation_context
    ADD COLUMN IF NOT EXISTS booking_working_state JSONB DEFAULT NULL;

-- 2. Colonne morte segnalate in precedenza (rimozione posticipabile,
--    lasciate qui commentate finché non si è certi che nulla le referenzi più altrove, es. dashboard/report)
-- ALTER TABLE conversation_context DROP COLUMN IF EXISTS requested_date;
-- ALTER TABLE conversation_context DROP COLUMN IF EXISTS requested_time;

-- 3. Verifica che conversation_state abbia le colonne usate dal codice
--    (se già presenti dalla creazione iniziale, questi ALTER sono no-op sicuri)
ALTER TABLE conversation_state
    ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMPTZ DEFAULT now();

ALTER TABLE conversation_state
    ADD COLUMN IF NOT EXISTS waiting_since TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE conversation_state
    ADD COLUMN IF NOT EXISTS timeout_at TIMESTAMPTZ DEFAULT NULL;

-- 4. Indice per velocizzare la ricerca della transition OPEN attiva per conversazione
CREATE INDEX IF NOT EXISTS idx_conversation_transition_open
    ON conversation_transition (conversation_id, status)
    WHERE status = 'OPEN';

-- 5. Indice per velocizzare la ricerca di conversazioni ACTIVE per tenant+customer
CREATE INDEX IF NOT EXISTS idx_conversation_state_active_lookup
    ON conversation_state (tenant_id, customer_id, status);
