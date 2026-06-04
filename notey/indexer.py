import re
import requests
import chromadb
from datetime import datetime
from typing import TYPE_CHECKING

from dateutil import parser as dateparser

from .config import CHROMA_DIR, EMBED_MODEL, OLLAMA_BASE_URL, CHUNK_SIZE, CHUNK_OVERLAP
from . import cache

if TYPE_CHECKING:
    from .extractor import Note

_COLLECTION = "notes"

_MONTHS_FULL = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
_MONTHS_ABBR = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
_ORD = r'(?:st|nd|rd|th)'
_YEAR = r'\d{4}'

# Patterns that match ONLY lines that are section date headers (short, standalone)
_SECTION_DATE_RES = [
    # "22 May 2026", "22 May", "3 June"
    re.compile(rf'^\s*(\d{{1,2}})\s+({_MONTHS_FULL})(?:\s+({_YEAR}))?\s*[-–—]?\s*$', re.IGNORECASE),
    # "27th May 2026", "3rd June", "24th March 2026"
    re.compile(rf'^\s*(\d{{1,2}}){_ORD}\s+({_MONTHS_FULL})(?:\s+({_YEAR}))?\s*[-–—]?\s*$', re.IGNORECASE),
    # "(Jan 7th, Day 3)", "(Jan 12th)", "(Feb 5th)"
    re.compile(rf'^\s*\(({_MONTHS_ABBR})\s+(\d{{1,2}}){_ORD}?(?:[,\s][^)]+)?\)\s*[-–—]?\s*$', re.IGNORECASE),
]

_DEFAULT_YEAR = datetime.now().year


def _parse_section_date(line: str) -> str | None:
    """Return ISO date string if line is a section date header, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > 50:
        return None
    for pattern in _SECTION_DATE_RES:
        if pattern.match(stripped):
            # Strip parentheses and trailing punctuation, keep first date token
            clean = stripped.strip("()")
            # For "(Jan 7th, Day 3)" keep only "Jan 7th"
            clean = clean.split(",")[0].strip().rstrip("-–— ")
            try:
                default_dt = datetime(_DEFAULT_YEAR, 1, 1)
                parsed = dateparser.parse(clean, default=default_dt)
                return parsed.strftime("%Y-%m-%d")
            except (ValueError, OverflowError, TypeError):
                continue
    return None


def _section_chunk(title: str, body: str) -> list[tuple[str, str]]:
    """
    Split body by date-header sections, returning [(iso_date, chunk_text), ...].
    Falls back to character-based chunking if no date headers are found.
    """
    lines = body.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_date = ""
    current_lines: list[str] = []
    found_any_date = False

    for line in lines:
        date = _parse_section_date(line)
        if date is not None:
            found_any_date = True
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append((current_date, text))
            current_date = date
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append((current_date, text))

    prefix = f"[Note: {title}]\n\n"

    if not found_any_date:
        return [("", f"{prefix}{c}") for c in _chunk_text(body)]

    result = []
    for date, text in sections:
        full = f"{prefix}{text}"
        if len(full) > CHUNK_SIZE * 4:
            for sub in _chunk_text(text):
                result.append((date, f"{prefix}{sub}"))
        else:
            result.append((date, full))
    return result


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
    char_size = CHUNK_SIZE * 4
    char_overlap = CHUNK_OVERLAP * 4
    if len(text) <= char_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + char_size])
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
    existing = col.get(where={"note_id": {"$eq": note.id}})
    if existing["ids"]:
        col.delete(ids=existing["ids"])

    sections = _section_chunk(note.title, note.body)
    if not sections:
        return

    chunks = [text for _, text in sections]
    try:
        embeddings = _embed(chunks)
    except Exception as e:
        print(f"  [skip] '{note.title}' — embedding failed: {e}")
        return

    ids = [f"{note.id}__chunk{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "note_id": note.id,
            "note_title": note.title,
            "modified": note.modified,
            "chunk_index": i,
            "section_date": section_date,
        }
        for i, (section_date, _) in enumerate(sections)
    ]
    col.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)


def collection_count() -> int:
    try:
        return _get_collection().count()
    except Exception:
        return 0
