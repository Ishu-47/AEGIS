"""Dependency-free text chunking helpers for the AEGIS RAG pipeline."""
import re

def chunk_text(text_value: str, chunk_size: int = 1200, overlap: int = 180) -> list[str]:
    text_value = re.sub(r"\r\n?", "\n", text_value).strip()
    if not text_value:
        return []
    chunks, start = [], 0
    while start < len(text_value):
        end = min(len(text_value), start + chunk_size)
        if end < len(text_value):
            boundary = text_value.rfind("\n", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        part = text_value[start:end].strip()
        if part:
            chunks.append(part)
        if end >= len(text_value):
            break
        start = max(end - overlap, start + 1)
    return chunks

