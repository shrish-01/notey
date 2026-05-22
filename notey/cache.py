import json
from typing import TYPE_CHECKING

from .config import NOTES_CACHE_FILE

if TYPE_CHECKING:
    from .extractor import Note


def save_notes(notes: list["Note"]) -> None:
    data = {
        n.id: {"title": n.title, "body": n.body, "modified": n.modified}
        for n in notes
    }
    NOTES_CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def update_notes(notes: list["Note"]) -> None:
    """Add or overwrite entries for the given notes without touching others."""
    data = _load()
    for n in notes:
        data[n.id] = {"title": n.title, "body": n.body, "modified": n.modified}
    NOTES_CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def delete_notes(note_ids: list[str]) -> None:
    if not note_ids:
        return
    data = _load()
    for nid in note_ids:
        data.pop(nid, None)
    NOTES_CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_note(note_id: str) -> dict | None:
    return _load().get(note_id)


def _load() -> dict:
    if NOTES_CACHE_FILE.exists():
        try:
            return json.loads(NOTES_CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}
