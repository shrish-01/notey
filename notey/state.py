import hashlib
import json
import os
from typing import TYPE_CHECKING

from .config import STATE_FILE, NOTES_DB

if TYPE_CHECKING:
    from .extractor import Note


def _note_hash(note: "Note") -> str:
    return hashlib.sha256(f"{note.title}\n{note.body}".encode()).hexdigest()


def _load() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"notes_db_mtime": 0.0, "note_hashes": {}}


def _save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def is_stale() -> bool:
    """Return True if Notes DB has been modified since last index."""
    state = _load()
    try:
        current_mtime = os.stat(NOTES_DB).st_mtime
        return current_mtime != state.get("notes_db_mtime", 0.0)
    except OSError:
        # Can't stat the DB — treat as stale so we always try extraction
        return True


def diff(current_notes: list["Note"]) -> tuple[list["Note"], list["Note"], list[str]]:
    """Return (added, modified, deleted_ids) by comparing against stored hashes."""
    state = _load()
    old_hashes: dict[str, str] = state.get("note_hashes", {})
    current_map = {n.id: n for n in current_notes}

    added, modified = [], []
    for note in current_notes:
        h = _note_hash(note)
        if note.id not in old_hashes:
            added.append(note)
        elif old_hashes[note.id] != h:
            modified.append(note)

    deleted_ids = [nid for nid in old_hashes if nid not in current_map]
    return added, modified, deleted_ids


def save_state(notes: list["Note"]) -> None:
    try:
        mtime = os.stat(NOTES_DB).st_mtime
    except OSError:
        mtime = 0.0
    _save({
        "notes_db_mtime": mtime,
        "note_hashes": {n.id: _note_hash(n) for n in notes},
    })
