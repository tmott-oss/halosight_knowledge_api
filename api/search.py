import os
from typing import Optional
from openai import OpenAI
from supabase import Client

from .models import SearchResult

EMBEDDING_MODEL = "text-embedding-3-small"

_openai: Optional[OpenAI] = None


def get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai


def embed_query(query: str) -> list[float]:
    response = get_openai().embeddings.create(model=EMBEDDING_MODEL, input=query)
    return response.data[0].embedding


def search_documents(db: Client, company_id: str, embedding: list[float], top_k: int) -> list[SearchResult]:
    result = db.rpc("search_documents", {
        "query_embedding": embedding,
        "match_company_id": company_id,
        "match_count": top_k,
    }).execute()

    return [
        SearchResult(
            id=row["id"],
            title=row["title"],
            folder=row["folder"],
            content=row["content"],
            similarity=round(row["similarity"], 4),
        )
        for row in result.data
    ]


def search_chunks(db: Client, company_id: str, embedding: list[float], top_k: int) -> list[SearchResult]:
    result = db.rpc("search_chunks", {
        "query_embedding": embedding,
        "match_company_id": company_id,
        "match_count": top_k,
    }).execute()

    return [
        SearchResult(
            id=row["chunk_id"],
            title=row["title"],
            folder=row["folder"],
            content=row["content"],
            similarity=round(row["similarity"], 4),
            chunk_index=row["chunk_index"],
        )
        for row in result.data
    ]
