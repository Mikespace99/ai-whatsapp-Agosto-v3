-- Migration 004 — deduplicazione messaggi WhatsApp
-- Previene l'elaborazione multipla dello stesso messaggio quando
-- Meta ri-consegna un webhook (perche' non ha ricevuto risposta
-- abbastanza in fretta, o per qualunque altro motivo di rete).

CREATE TABLE IF NOT EXISTS message_dedup (
    message_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Pulizia periodica facoltativa (non obbligatoria per il funzionamento,
-- utile solo per non far crescere la tabella all'infinito):
-- DELETE FROM message_dedup WHERE created_at < now() - interval '7 days';
