-- Migration 005 — supporto onboarding self-service (Supabase Auth)

-- Tabella "users": collega un utente autenticato (Supabase Auth)
-- al tenant che possiede/gestisce. Creata con IF NOT EXISTS per
-- sicurezza nel caso non esistesse ancora esattamente con queste colonne;
-- le ALTER successive coprono il caso in cui esista gia' ma incompleta.
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    auth_user_id UUID,
    role TEXT DEFAULT 'owner',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_user_id UUID;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'owner';
ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

-- Un utente Supabase Auth corrisponde a UNA sola riga "users"
-- (un utente = un tenant, come deciso).
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_auth_user_id
    ON users (auth_user_id);

-- whatsapp_accounts: credenziali per-tenant. Oggi il codice usa ancora
-- variabili d'ambiente globali (gap segnalato in precedenza) — queste
-- colonne preparano il terreno per il fix multi-tenant, che faremo
-- quando arriveremo allo step WhatsApp dell'onboarding.
ALTER TABLE whatsapp_accounts ADD COLUMN IF NOT EXISTS access_token TEXT;
ALTER TABLE whatsapp_accounts ADD COLUMN IF NOT EXISTS phone_number_id TEXT;

-- Verifica finale
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY column_name;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'whatsapp_accounts'
ORDER BY column_name;
