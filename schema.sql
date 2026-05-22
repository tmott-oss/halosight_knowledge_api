-- =============================================================================
-- Halosight Knowledge API — Supabase Schema
-- Run this once in the Supabase SQL editor (Database → SQL Editor → New query)
-- =============================================================================

-- Enable pgvector
create extension if not exists vector;

-- =============================================================================
-- companies
-- One row per tenant. All other tables FK to this.
-- =============================================================================
create table if not exists companies (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    slug        text not null unique,
    created_at  timestamptz not null default now()
);

-- =============================================================================
-- documents
-- One row per source .md file after migration.
-- =============================================================================
create table if not exists documents (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id) on delete cascade,
    title        text not null,
    folder       text not null,
    category     text,
    content      text not null,
    word_count   integer not null default 0,
    tags         text[] not null default '{}',
    source_file  text not null,
    embedding    vector(1536),         -- OpenAI text-embedding-3-small
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

-- Prevent duplicate imports for the same company
create unique index if not exists documents_company_source_file_idx
    on documents(company_id, source_file);

-- Fast lookup by folder/category
create index if not exists documents_company_folder_idx
    on documents(company_id, folder);

-- pgvector HNSW index for fast approximate nearest-neighbor search
create index if not exists documents_embedding_idx
    on documents using hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- document_chunks
-- Long documents (>500 words) split into overlapping chunks for RAG.
-- =============================================================================
create table if not exists document_chunks (
    id           uuid primary key default gen_random_uuid(),
    document_id  uuid not null references documents(id) on delete cascade,
    company_id   uuid not null references companies(id) on delete cascade,
    chunk_index  integer not null,
    content      text not null,
    word_count   integer not null default 0,
    embedding    vector(1536),
    created_at   timestamptz not null default now()
);

create unique index if not exists chunks_document_chunk_idx
    on document_chunks(document_id, chunk_index);

create index if not exists chunks_company_idx
    on document_chunks(company_id);

create index if not exists chunks_embedding_idx
    on document_chunks using hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- updated_at trigger
-- =============================================================================
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create or replace trigger documents_updated_at
    before update on documents
    for each row execute function set_updated_at();

-- =============================================================================
-- Row Level Security
-- All queries are automatically scoped to the authenticated company.
-- =============================================================================
alter table companies       enable row level security;
alter table documents       enable row level security;
alter table document_chunks enable row level security;

-- Service role bypasses RLS (used by the ingestion script)
-- Authenticated users see only their own company's data

create policy "companies: own row only"
    on companies for all
    using (id = (current_setting('app.company_id', true))::uuid);

create policy "documents: own company only"
    on documents for all
    using (company_id = (current_setting('app.company_id', true))::uuid);

create policy "document_chunks: own company only"
    on document_chunks for all
    using (company_id = (current_setting('app.company_id', true))::uuid);

-- =============================================================================
-- Helper: semantic search across documents
-- Returns the top-k most similar documents for a given query embedding.
-- =============================================================================
create or replace function search_documents(
    query_embedding vector(1536),
    match_company_id uuid,
    match_count int default 10
)
returns table (
    id          uuid,
    title       text,
    folder      text,
    content     text,
    similarity  float
)
language sql stable as $$
    select
        d.id,
        d.title,
        d.folder,
        d.content,
        1 - (d.embedding <=> query_embedding) as similarity
    from documents d
    where d.company_id = match_company_id
      and d.embedding is not null
    order by d.embedding <=> query_embedding
    limit match_count;
$$;

-- =============================================================================
-- Helper: semantic search across chunks
-- =============================================================================
create or replace function search_chunks(
    query_embedding vector(1536),
    match_company_id uuid,
    match_count int default 10
)
returns table (
    chunk_id    uuid,
    document_id uuid,
    title       text,
    folder      text,
    content     text,
    chunk_index integer,
    similarity  float
)
language sql stable as $$
    select
        c.id as chunk_id,
        c.document_id,
        d.title,
        d.folder,
        c.content,
        c.chunk_index,
        1 - (c.embedding <=> query_embedding) as similarity
    from document_chunks c
    join documents d on d.id = c.document_id
    where c.company_id = match_company_id
      and c.embedding is not null
    order by c.embedding <=> query_embedding
    limit match_count;
$$;
