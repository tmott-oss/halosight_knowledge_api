from typing import Optional, List
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., description="Plain-text question or topic to search for")
    top_k: int = Field(5, ge=1, le=20, description="Number of results to return")
    search_chunks: bool = Field(False, description="Search document chunks instead of full documents")


class DocumentSummary(BaseModel):
    id: str
    title: str
    folder: str
    category: Optional[str]
    word_count: int
    tags: List[str]
    source_file: str


class DocumentDetail(DocumentSummary):
    content: str


class SearchResult(BaseModel):
    id: str
    title: str
    folder: str
    content: str
    similarity: float
    chunk_index: Optional[int] = None


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]


class HealthResponse(BaseModel):
    status: str
    documents: int


class AskRequest(BaseModel):
    question: str = Field(..., description="Plain-text question to answer from the knowledge base")
    top_k: int = Field(5, ge=1, le=20, description="Number of source documents to retrieve")


class AskSource(BaseModel):
    title: str
    folder: str
    similarity: float


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: List[AskSource]
