"""
Obsidian JSON → Supabase ingestion script.

Reads migration_output/migration_output.json, upserts documents into Supabase,
generates OpenAI embeddings, and chunks documents over 500 words.

Usage:
    python3 ingest.py
    python3 ingest.py --input migration_output/migration_output.json
    python3 ingest.py --dry-run   # validate without writing to Supabase
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_INPUT = Path(__file__).parent / "migration_output" / "migration_output.json"
COMPANY_NAME = "Halosight"
COMPANY_SLUG = "halosight"

CHUNK_WORD_THRESHOLD = 500   # docs above this get chunked
CHUNK_SIZE_WORDS = 300       # target words per chunk
CHUNK_OVERLAP_WORDS = 50     # overlap between consecutive chunks
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_BATCH_SIZE = 50    # texts per OpenAI API call
OPENAI_RPM_PAUSE = 0.5       # seconds between batches (rate-limit headroom)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap

    return chunks


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embed a list of texts in batches. Returns list of embedding vectors."""
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i: i + EMBEDDING_BATCH_SIZE]
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        all_embeddings.extend([item.embedding for item in response.data])
        if i + EMBEDDING_BATCH_SIZE < len(texts):
            time.sleep(OPENAI_RPM_PAUSE)

    return all_embeddings


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def get_or_create_company(sb: Client, dry_run: bool) -> Optional[str]:
    """Upsert the company row and return its UUID."""
    if dry_run:
        return "00000000-0000-0000-0000-000000000000"

    result = sb.table("companies").upsert(
        {"name": COMPANY_NAME, "slug": COMPANY_SLUG},
        on_conflict="slug",
    ).execute()

    return result.data[0]["id"]


def upsert_document(sb: Client, doc: dict, company_id: str, embedding: list[float], dry_run: bool) -> Optional[str]:
    """Insert or update a document row. Returns the document UUID."""
    row = {
        "company_id": company_id,
        "title": doc["title"],
        "folder": doc["folder"],
        "category": doc.get("category"),
        "content": doc["content"],
        "word_count": doc["word_count"],
        "tags": doc["tags"],
        "source_file": doc["source_file"],
        "embedding": embedding,
    }

    if dry_run:
        return "00000000-0000-0000-0000-000000000001"

    result = sb.table("documents").upsert(
        row,
        on_conflict="company_id,source_file",
    ).execute()

    return result.data[0]["id"]


def upsert_chunks(sb: Client, document_id: str, company_id: str,
                  chunks: list[str], embeddings: list[list[float]], dry_run: bool) -> None:
    """Insert or replace all chunks for a document."""
    if dry_run:
        return

    # Delete existing chunks before re-inserting (clean re-run support)
    sb.table("document_chunks").delete().eq("document_id", document_id).execute()

    rows = [
        {
            "document_id": document_id,
            "company_id": company_id,
            "chunk_index": i,
            "content": chunk,
            "word_count": len(chunk.split()),
            "embedding": emb,
        }
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    sb.table("document_chunks").insert(rows).execute()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest migration JSON into Supabase")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing to Supabase")
    args = parser.parse_args()

    # Validate env
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    missing = [k for k, v in {
        "SUPABASE_URL": supabase_url,
        "SUPABASE_SERVICE_ROLE_KEY": supabase_key,
        "OPENAI_API_KEY": openai_key,
    }.items() if not v]

    if missing and not args.dry_run:
        print(f"ERROR: missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Copy .env.example to .env and fill in the values.", file=sys.stderr)
        sys.exit(1)

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Load documents
    documents: list[dict] = json.loads(args.input.read_text(encoding="utf-8"))
    print(f"\nLoaded {len(documents)} documents from {args.input}")

    if args.dry_run:
        print("DRY RUN — no data will be written to Supabase\n")

    # Clients
    openai_client = OpenAI(api_key=openai_key or "dry-run")
    sb = create_client(supabase_url or "https://placeholder.supabase.co", supabase_key or "placeholder") if not args.dry_run else None

    # Company
    company_id = get_or_create_company(sb, args.dry_run)
    print(f"Company: {COMPANY_NAME} (id={company_id})")

    # Stats
    docs_inserted = 0
    docs_skipped = 0
    chunks_inserted = 0
    errors: list[str] = []

    # -----------------------------------------------------------------------
    # Phase A: embed all document content in one batched pass
    # -----------------------------------------------------------------------
    print(f"\nGenerating embeddings for {len(documents)} documents...")
    doc_texts = [d["content"] for d in documents]

    if args.dry_run:
        doc_embeddings = [[0.0] * 1536 for _ in documents]
    else:
        doc_embeddings = embed_texts(openai_client, doc_texts)

    print(f"Embeddings done.")

    # -----------------------------------------------------------------------
    # Phase B: identify docs that need chunking and embed chunks
    # -----------------------------------------------------------------------
    docs_to_chunk = [(i, d) for i, d in enumerate(documents) if d["word_count"] > CHUNK_WORD_THRESHOLD]
    print(f"\n{len(docs_to_chunk)} documents exceed {CHUNK_WORD_THRESHOLD} words — will be chunked.")

    # Pre-compute all chunks
    all_chunk_texts: list[str] = []
    chunk_map: list[tuple[int, list[str]]] = []  # (doc_index, [chunk_texts])

    for doc_index, doc in docs_to_chunk:
        chunks = chunk_text(doc["content"])
        chunk_map.append((doc_index, chunks))
        all_chunk_texts.extend(chunks)

    if all_chunk_texts:
        print(f"Generating embeddings for {len(all_chunk_texts)} chunks...")
        if args.dry_run:
            chunk_embeddings_flat = [[0.0] * 1536 for _ in all_chunk_texts]
        else:
            chunk_embeddings_flat = embed_texts(openai_client, all_chunk_texts)
        print("Chunk embeddings done.")
    else:
        chunk_embeddings_flat = []

    # Reconstruct per-doc chunk embeddings
    chunk_emb_index = 0
    chunk_emb_by_doc: dict[int, tuple[list[str], list[list[float]]]] = {}
    for doc_index, chunks in chunk_map:
        embs = chunk_embeddings_flat[chunk_emb_index: chunk_emb_index + len(chunks)]
        chunk_emb_by_doc[doc_index] = (chunks, embs)
        chunk_emb_index += len(chunks)

    # -----------------------------------------------------------------------
    # Phase C: upsert documents and chunks into Supabase
    # -----------------------------------------------------------------------
    print(f"\nUpserting to Supabase...")

    for i, (doc, embedding) in enumerate(zip(documents, doc_embeddings)):
        try:
            doc_id = upsert_document(sb, doc, company_id, embedding, args.dry_run)
            docs_inserted += 1

            if i in chunk_emb_by_doc:
                chunks, chunk_embs = chunk_emb_by_doc[i]
                upsert_chunks(sb, doc_id, company_id, chunks, chunk_embs, args.dry_run)
                chunks_inserted += len(chunks)

            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{len(documents)} documents processed...")

        except Exception as e:
            errors.append(f"{doc['source_file']}: {e}")
            docs_skipped += 1

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'DRY RUN ' if args.dry_run else ''}Ingestion complete")
    print(f"  Documents upserted: {docs_inserted}")
    print(f"  Documents skipped:  {docs_skipped}")
    print(f"  Chunks inserted:    {chunks_inserted}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for err in errors:
            print(f"    {err}")


if __name__ == "__main__":
    main()
