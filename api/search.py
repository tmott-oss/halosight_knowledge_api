import os
from typing import Optional, List
from openai import OpenAI
from supabase import Client

from .models import SearchResult, AskSource

EMBEDDING_MODEL = "text-embedding-3-small"
SYNTHESIS_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are the Halosight Knowledge Assistant — an expert on Halosight's product, sales methodology, ICP, competitive positioning, and go-to-market strategy.

Answer the user's question using ONLY the knowledge base content provided below. Do not use any outside knowledge or make assumptions beyond what is in the sources.

Guidelines:
- Be concise and direct — sales reps need fast, actionable answers
- Use bullet points for lists, frameworks, and step-by-step guidance
- If the answer spans multiple documents, synthesize them into one coherent response
- If the knowledge base does not contain enough information to answer the question, say so clearly
- Never fabricate facts, quotes, or data points not present in the sources
- End with a brief "Sources:" line listing the document titles used"""

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


def synthesize_answer(question: str, results: List[SearchResult]) -> tuple[str, List[AskSource]]:
    """
    Take search results and synthesize a grounded answer using GPT-4o-mini.
    Returns (answer_text, sources).
    """
    context_parts = []
    for i, r in enumerate(results, 1):
        context_parts.append(f"[Source {i}: {r.title} — {r.folder}]\n{r.content}")
    context = "\n\n---\n\n".join(context_parts)

    user_message = f"Knowledge base content:\n\n{context}\n\n---\n\nQuestion: {question}"

    response = get_openai().chat.completions.create(
        model=SYNTHESIS_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        max_tokens=800,
    )

    answer = response.choices[0].message.content.strip()

    sources = [
        AskSource(title=r.title, folder=r.folder, similarity=r.similarity)
        for r in results
    ]

    return answer, sources
