import json
import requests
import chromadb

from .config import CHROMA_DIR, EMBED_MODEL, CHAT_MODEL, OLLAMA_BASE_URL, TOP_K
from . import cache

_COLLECTION = "notes"

_SYSTEM_PROMPT = """\
You are a personal assistant answering questions based solely on the user's Mac Notes.

Rules:
- Use ONLY the provided notes. If the answer isn't in them, say so plainly — do not invent or extrapolate.
- When the user asks for lists, questions, action items, or todos: be EXHAUSTIVE. Enumerate every relevant item you find, quoting verbatim where useful. Do not summarize details away.
- Cite the note title inline when referencing it (e.g. "From '1x1 Shrreya/Shrish': ...").
- Be direct. No preamble like "Based on the notes..." or "According to your notes...".\
"""


def _embed_query(text: str) -> list[float]:
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def _retrieve_full_notes(question: str) -> list[dict]:
    """Return full notes (not chunks) ranked by best chunk similarity score."""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_or_create_collection(_COLLECTION)
    if col.count() == 0:
        return []

    vector = _embed_query(question)
    results = col.query(
        query_embeddings=[vector],
        n_results=min(TOP_K, col.count()),
        include=["metadatas", "distances"],
    )

    # Group hits by note_id, track best (lowest) distance per note
    best_score: dict[str, float] = {}
    for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
        nid = meta["note_id"]
        if nid not in best_score or dist < best_score[nid]:
            best_score[nid] = dist

    # Sort notes by ascending distance (most relevant first)
    ranked_ids = sorted(best_score, key=lambda nid: best_score[nid])

    notes = []
    for nid in ranked_ids:
        entry = cache.load_note(nid)
        if entry:
            notes.append(entry)

    return notes


def ask(question: str) -> None:
    notes = _retrieve_full_notes(question)
    if not notes:
        print("No indexed notes found. Run: notey index")
        return

    context_parts = [
        f'<note title="{n["title"]}" modified="{n["modified"]}">\n{n["body"]}\n</note>'
        for n in notes
    ]
    user_message = "\n\n".join(context_parts) + f"\n\nQuestion: {question}"

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": CHAT_MODEL,
            "stream": True,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        },
        stream=True,
        timeout=180,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        token = data.get("message", {}).get("content", "")
        if token:
            print(token, end="", flush=True)
        if data.get("done"):
            break

    print()

    print("\nSources:")
    for n in notes:
        print(f"  • {n['title']}  ({n['modified']})")
