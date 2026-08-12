-- Migration 006 — schema per working_hours e faq

CREATE TABLE IF NOT EXISTS working_hours (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    day_of_week TEXT NOT NULL,
    open_time TEXT,
    close_time TEXT,
    closed BOOLEAN DEFAULT false,
    UNIQUE (tenant_id, day_of_week)
);

CREATE TABLE IF NOT EXISTS faq (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Verifica
SELECT * FROM working_hours LIMIT 1;
SELECT * FROM faq LIMIT 1;
