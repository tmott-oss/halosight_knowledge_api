from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_api_key
from .database import get_db
from .models import (
    HealthResponse,
    SearchRequest,
    SearchResponse,
    AskRequest,
    AskResponse,
    DocumentSummary,
    DocumentDetail,
)
from .search import embed_query, search_documents, search_chunks, synthesize_answer

app = FastAPI(
    title="Halosight Knowledge API",
    description="AI-agnostic semantic search over the Halosight knowledge base.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health():
    """Returns API status and total document count. No auth required."""
    db = get_db()
    result = db.table("documents").select("id", count="exact").execute()
    return HealthResponse(status="ok", documents=result.count or 0)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.post("/search", response_model=SearchResponse, tags=["Search"])
def search(request: SearchRequest, auth: dict = Depends(require_api_key)):
    """
    Semantic search over the knowledge base.

    Pass a plain-text question or topic. Returns the most relevant documents
    (or chunks, if search_chunks=true) ranked by similarity.
    """
    company_id = auth["company_id"]
    db = get_db()

    embedding = embed_query(request.query)

    if request.search_chunks:
        results = search_chunks(db, company_id, embedding, request.top_k)
    else:
        results = search_documents(db, company_id, embedding, request.top_k)

    return SearchResponse(query=request.query, results=results)


# ---------------------------------------------------------------------------
# Ask (retrieval + synthesis)
# ---------------------------------------------------------------------------

@app.post("/ask", response_model=AskResponse, tags=["Search"])
def ask(request: AskRequest, auth: dict = Depends(require_api_key)):
    """
    Ask a question and get a synthesized answer from the knowledge base.

    Retrieves the most relevant documents, then uses GPT-4o-mini to
    synthesize a direct, concise answer grounded in that content.
    Use this instead of /search when you want a readable answer
    rather than raw document content.
    """
    company_id = auth["company_id"]
    db = get_db()

    embedding = embed_query(request.question)
    results = search_documents(db, company_id, embedding, request.top_k)
    answer = synthesize_answer(request.question, results)

    return AskResponse(question=request.question, answer=answer)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.get("/documents", response_model=list[DocumentSummary], tags=["Documents"])
def list_documents(folder: Optional[str] = None, auth: dict = Depends(require_api_key)):
    """
    List all documents. Optionally filter by folder name.
    Returns metadata only — use GET /documents/{id} for full content.
    """
    company_id = auth["company_id"]
    db = get_db()

    query = (
        db.table("documents")
        .select("id, title, folder, category, word_count, tags, source_file")
        .eq("company_id", company_id)
        .order("folder")
        .order("title")
    )

    if folder:
        query = query.eq("folder", folder)

    result = query.execute()
    return result.data


@app.get("/documents/{document_id}", response_model=DocumentDetail, tags=["Documents"])
def get_document(document_id: str, auth: dict = Depends(require_api_key)):
    """Fetch a single document by ID, including full content."""
    company_id = auth["company_id"]
    db = get_db()

    result = (
        db.table("documents")
        .select("id, title, folder, category, content, word_count, tags, source_file")
        .eq("id", document_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")

    return result.data[0]
