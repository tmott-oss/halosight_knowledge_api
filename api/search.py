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


def synthesize_answer(question: str, results: list[SearchResult]) -> str:
    """Send retrieved content + question to OpenAI and return a synthesized answer."""
    if not results:
        return "I couldn't find relevant information in the Halosight knowledge base to answer that question."

    context = "\n\n---\n\n".join(
        f"[{r.title}]\n{r.content}" for r in results
    )

    system_prompt = (
        "You are the Halosight Knowledge Assistant. "
        "Answer the user's question using only the knowledge base content provided below. "
        "Be concise, direct, and specific. "
        "Do not make up information not present in the content. "
        "If the content doesn't fully answer the question, say so honestly.\n\n"
        f"Knowledge base content:\n{context}"
    )

    response = get_openai().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.3,
        max_tokens=1000,
    )

    return response.choices[0].message.content


def search_chunks(
    db: Client,
    company_id: str,
    embedding: list[float],
    top_k: int,
    query: str = "",
) -> list[SearchResult]:
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
