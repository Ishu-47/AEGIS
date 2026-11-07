"""
AEGIS Knowledge Base — RAG-powered document retrieval.

Manages runbooks, post-mortem reports, architecture documents, and SOPs.
Documents are embedded using Gemini's text-embedding model and retrieved
via cosine similarity during investigations.

In production, replace the JSON-based embedding storage with pgvector
for efficient approximate nearest-neighbour search at scale.
"""

import math
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeDocument

# ---------------------------------------------------------------------------
# Gemini embedding client
# ---------------------------------------------------------------------------

try:
    from google import genai

    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_EMBEDDING_MODEL = "gemini-embedding-exp-03-07"


def _get_client():
    if not _GENAI_AVAILABLE or not _GEMINI_API_KEY:
        return None
    return genai.Client(api_key=_GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def generate_embedding(text: str) -> list[float] | None:
    """Generate a dense vector for *text* using Gemini's embedding model.

    Returns ``None`` when the Gemini SDK or API key is unavailable so the
    caller can gracefully degrade.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        result = client.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=text,
        )
        return result.embeddings[0].values
    except Exception:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Document CRUD
# ---------------------------------------------------------------------------

VALID_DOC_TYPES = {"runbook", "postmortem", "architecture", "sop"}


def create_document(
    db: Session,
    application_id: str,
    title: str,
    content: str,
    doc_type: str,
    tags: list[str] | None = None,
) -> KnowledgeDocument:
    """Ingest a new knowledge document.

    Generates an embedding for the combined title + content so the document
    can be retrieved via semantic search during investigations.
    """
    if doc_type not in VALID_DOC_TYPES:
        raise ValueError(
            f"Invalid doc_type '{doc_type}'. "
            f"Use one of: {', '.join(sorted(VALID_DOC_TYPES))}"
        )

    embedding = generate_embedding(f"{title}\n\n{content}")

    doc = KnowledgeDocument(
        application_id=application_id,
        title=title.strip(),
        content=content.strip(),
        doc_type=doc_type,
        tags=tags or [],
        embedding=embedding,
    )

    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def update_document(
    db: Session,
    doc: KnowledgeDocument,
    title: str | None = None,
    content: str | None = None,
    doc_type: str | None = None,
    tags: list[str] | None = None,
) -> KnowledgeDocument:
    """Update an existing knowledge document and re-embed if content changed."""
    changed_content = False

    if title is not None:
        doc.title = title.strip()
        changed_content = True

    if content is not None:
        doc.content = content.strip()
        changed_content = True

    if doc_type is not None:
        if doc_type not in VALID_DOC_TYPES:
            raise ValueError(
                f"Invalid doc_type '{doc_type}'. "
                f"Use one of: {', '.join(sorted(VALID_DOC_TYPES))}"
            )
        doc.doc_type = doc_type

    if tags is not None:
        doc.tags = tags

    if changed_content:
        doc.embedding = generate_embedding(f"{doc.title}\n\n{doc.content}")

    doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    return doc


def delete_document(db: Session, doc: KnowledgeDocument) -> None:
    db.delete(doc)
    db.commit()


def list_documents(
    db: Session,
    application_id: str,
    doc_type: str | None = None,
) -> list[KnowledgeDocument]:
    stmt = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.application_id == application_id)
    )

    if doc_type:
        stmt = stmt.where(KnowledgeDocument.doc_type == doc_type)

    stmt = stmt.order_by(KnowledgeDocument.created_at.desc())
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Semantic retrieval (RAG)
# ---------------------------------------------------------------------------

def retrieve_relevant_documents(
    db: Session,
    application_id: str,
    query: str,
    top_k: int = 5,
    min_similarity: float = 0.25,
) -> list[dict[str, Any]]:
    """Retrieve the most relevant knowledge documents for *query*.

    Uses cosine similarity between the query embedding and stored document
    embeddings.  Returns a list of dicts with document metadata and a
    ``similarity`` score.

    In production this should use pgvector's ``<=>`` operator for efficient
    ANN search instead of loading all embeddings into memory.
    """
    query_embedding = generate_embedding(query)

    if query_embedding is None:
        # Fallback: keyword-based retrieval
        return _keyword_retrieval(db, application_id, query, top_k)

    docs = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.application_id == application_id)
    ).all()

    scored: list[tuple[float, KnowledgeDocument]] = []

    for doc in docs:
        if not doc.embedding:
            continue

        sim = cosine_similarity(query_embedding, doc.embedding)
        if sim >= min_similarity:
            scored.append((sim, doc))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "id": doc.id,
            "title": doc.title,
            "content": doc.content[:2000],
            "doc_type": doc.doc_type,
            "tags": doc.tags,
            "similarity": round(sim, 4),
        }
        for sim, doc in scored[:top_k]
    ]


def _keyword_retrieval(
    db: Session,
    application_id: str,
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """Simple keyword fallback when embeddings are unavailable."""
    docs = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.application_id == application_id)
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(top_k * 2)
    ).all()

    keywords = set(query.lower().split())

    scored = []
    for doc in docs:
        text = f"{doc.title} {doc.content} {' '.join(doc.tags or [])}".lower()
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scored.append((hits, doc))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "id": doc.id,
            "title": doc.title,
            "content": doc.content[:2000],
            "doc_type": doc.doc_type,
            "tags": doc.tags,
            "similarity": 0.0,
        }
        for _, doc in scored[:top_k]
    ]

