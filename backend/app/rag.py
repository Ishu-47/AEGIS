"""Application-scoped, persistent RAG for AEGIS (PostgreSQL + pgvector).

Documents are chunked deterministically and embedded with Gemini's embedding API.
Every retrieval is filtered by application_id to prevent cross-tenant leakage.
"""
from __future__ import annotations
import hashlib, os, re
from typing import Any
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models import KnowledgeChunk

EMBEDDING_MODEL = os.getenv("AEGIS_EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSIONS = int(os.getenv("AEGIS_EMBEDDING_DIMENSIONS", "768"))


from app.rag_text import chunk_text


def embed_texts(texts: list[str]) -> list[list[float]]:
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is required for RAG embeddings")
    result = []
    for item in texts:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=item,
            config={"output_dimensionality": EMBEDDING_DIMENSIONS},
        )
        vector = response.embeddings[0].values
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSIONS}, got {len(vector)}")
        result.append(vector)
    return result


def index_document(db: Session, application_id: str, title: str, content: str,
                   source_type: str = "runbook", source_uri: str | None = None,
                   replace_existing: bool = False) -> dict[str, Any]:
    chunks = chunk_text(content)
    if not chunks:
        raise ValueError("Document contains no indexable text")
    # Generate every embedding before mutating existing rows. If the provider fails,
    # the previously indexed document remains available.
    vectors = embed_texts(chunks)
    if replace_existing:
        db.query(KnowledgeChunk).filter(
            KnowledgeChunk.application_id == application_id,
            KnowledgeChunk.title == title,
        ).delete(synchronize_session=False)
    created = 0
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        digest = hashlib.sha256(f"{application_id}:{title}:{i}:{chunk}".encode()).hexdigest()
        exists = db.scalar(select(KnowledgeChunk.id).where(KnowledgeChunk.content_hash == digest))
        if exists:
            continue
        db.add(KnowledgeChunk(application_id=application_id, title=title,
            source_type=source_type, source_uri=source_uri, chunk_index=i,
            content=chunk, content_hash=digest, embedding=vector))
        created += 1
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"title": title, "chunks_created": created, "chunks_total": len(chunks),
            "replaced": replace_existing}


def retrieve_context(db: Session, application_id: str, query: str, limit: int = 5,
                     min_similarity: float = 0.35) -> list[dict[str, Any]]:
    vector = embed_texts([query])[0]
    # cosine distance operator; application scope is mandatory.
    rows = db.execute(text("""
        SELECT title, source_type, source_uri, chunk_index, content,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM knowledge_chunks
        WHERE application_id = :application_id
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """), {"embedding": "[" + ",".join(map(str, vector)) + "]",
           "application_id": application_id, "limit": limit}).mappings().all()
    return [dict(r) for r in rows if float(r["similarity"]) >= min_similarity]


def list_documents(db: Session, application_id: str) -> list[dict[str, Any]]:
    """List distinct indexed sources for one application, without exposing embeddings."""
    rows = db.execute(text("""
        SELECT title, source_type, source_uri, COUNT(*) AS chunk_count,
               MIN(created_at) AS indexed_at
        FROM knowledge_chunks
        WHERE application_id = :application_id
        GROUP BY title, source_type, source_uri
        ORDER BY title
    """), {"application_id": application_id}).mappings().all()
    return [dict(row) for row in rows]


def delete_document(db: Session, application_id: str, title: str) -> int:
    """Delete all chunks for a named document within the supplied application only."""
    try:
        count = db.query(KnowledgeChunk).filter(
            KnowledgeChunk.application_id == application_id,
            KnowledgeChunk.title == title,
        ).delete(synchronize_session=False)
        db.commit()
        return int(count or 0)
    except Exception:
        db.rollback()
        raise
