import sys
from datetime import datetime


def _ensure_ollama():
    import requests
    from .config import OLLAMA_BASE_URL, EMBED_MODEL, CHAT_MODEL
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        available = {m["name"] for m in resp.json().get("models", [])}
        missing = []
        for model in (EMBED_MODEL, CHAT_MODEL):
            if not any(m == model or m.startswith(model.split(":")[0]) for m in available):
                missing.append(model)
        if missing:
            print(f"Missing Ollama models: {', '.join(missing)}")
            print("Run:  ollama pull " + "  &&  ollama pull ".join(missing))
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("Ollama is not running. Start it with:  ollama serve")
        sys.exit(1)


def _auto_reindex_if_stale():
    from .state import is_stale
    if is_stale():
        print("Notes changed — re-indexing...", flush=True)
        _do_index(full=False)


def _do_index(full: bool = True):
    from .extractor import extract_notes
    from .indexer import index_notes, delete_notes
    from .state import diff, save_state

    print("Extracting notes from Mac Notes...", flush=True)
    notes = extract_notes()
    print(f"  Found {len(notes)} notes", flush=True)

    if full:
        print("Building index (full)...", flush=True)
        index_notes(notes, full=True)
    else:
        added, modified, deleted_ids = diff(notes)
        total_changed = len(added) + len(modified) + len(deleted_ids)
        if total_changed == 0:
            print("  Index is up to date.")
            save_state(notes)
            return
        print(f"  +{len(added)} added  ~{len(modified)} modified  -{len(deleted_ids)} deleted", flush=True)
        delete_notes(deleted_ids)
        index_notes(added + modified, full=False)

    save_state(notes)
    print("Done.")


def cmd_index(_args):
    _ensure_ollama()
    _do_index(full=True)


def cmd_status(_args):
    from .state import _load, STATE_FILE
    from .indexer import collection_count
    from .config import NOTES_DB
    import os

    state = _load()
    mtime = state.get("notes_db_mtime", 0)
    note_count = len(state.get("note_hashes", {}))
    chunk_count = collection_count()

    print(f"Notes indexed : {note_count}")
    print(f"Vector chunks : {chunk_count}")
    if mtime:
        ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"Last indexed  : {ts}")
    else:
        print("Last indexed  : never")
    try:
        db_mtime = datetime.fromtimestamp(os.stat(NOTES_DB).st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"Notes DB mtime: {db_mtime}")
    except OSError:
        print("Notes DB mtime: (unavailable)")


def cmd_ask(question: str):
    _ensure_ollama()
    _auto_reindex_if_stale()
    from .query import ask
    ask(question)


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print("Usage:")
        print("  notey <question>        Ask a question about your notes")
        print("  notey index             Force a full re-index")
        print("  notey status            Show index stats")
        return

    if args[0] == "index":
        cmd_index(args[1:])
    elif args[0] == "status":
        cmd_status(args[1:])
    else:
        cmd_ask(" ".join(args))
