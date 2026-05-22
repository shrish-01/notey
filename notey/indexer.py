import requests
import chromadb
from typing import TYPE_CHECKING

from .config import CHROMA_DIR, EMBED_MODEL, OLLAMA_BASE_URL, CHUNK_SIZE, CHUNK_OVERLAP
from . import cache

if TYPE_CHECKING:
    from .extractor import Note

_COLLECTION = "notes"


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(_COLLECTION)


def _embed(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=60,
        )
        resp.raise_for_status()
        vectors.append(resp.json()["embedding"])
    return vectors


def _chunk_text(text: str) -> list[str]:
    # Approximate token count as chars / 4
    char_size = CHUNK_SIZE * 4
    char_overlap = CHUNK_OVERLAP * 4

    if len(text) <= char_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + char_size
        chunks.append(text[start:end])
        start += char_size - char_overlap
    return chunks


def index_notes(notes: list["Note"], *, full: bool = False) -> None:
    col = _get_collection()

    if full:
        existing = col.get()
        if existing["ids"]:
            col.delete(ids=existing["ids"])
        cache.save_notes(notes)
    else:
        cache.update_notes(notes)

    for note in notes:
        _upsert_note(col, note)


def delete_notes(note_ids: list[str]) -> None:
    if not note_ids:
        return
    col = _get_collection()
    existing = col.get(where={"note_id": {"$in": note_ids}})
    if existing["ids"]:
        col.delete(ids=existing["ids"])
    cache.delete_notes(note_ids)


def _upsert_note(col: chromadb.Collection, note: "Note") -> None:
    # Remove existing chunks for this note
    existing = col.get(where={"note_id": {"$eq": note.id}})
    if existing["ids"]:
        col.delete(ids=existing["ids"])

    body_chunks = _chunk_text(note.body)
    if not body_chunks:
        return
    # Prefix every chunk with the note title so all embeddings reference the parent note
    chunks = [f"[Note: {note.title}]\n\n{c}" for c in body_chunks]

    embeddings = _embed(chunks)
    ids = [f"{note.id}__chunk{i}" for i in range(len(chunks))]
    metadatas = [
        {"note_id": note.id, "note_title": note.title, "modified": note.modified, "chunk_index": i}
        for i in range(len(chunks))
    ]
    col.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)


def collection_count() -> int:
    try:
        return _get_collection().count()
    except Exception:
        return 0
