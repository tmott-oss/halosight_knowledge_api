-- Run this in the Supabase SQL editor after schema.sql
-- Adds the api_keys table for Bearer token authentication

create table if not exists api_keys (
    id          uuid primary key default gen_random_uuid(),
    company_id  uuid not null references companies(id) on delete cascade,
    key_hash    text not null unique,
    label       text not null,
    created_at  timestamptz not null default now()
);

create index if not exists api_keys_company_idx on api_keys(company_id);

alter table api_keys enable row level security;

-- Service role bypasses RLS — API keys are only managed server-side
create policy "api_keys: service role only"
    on api_keys for all
    using (false);
