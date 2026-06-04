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
- Cite the note title inline when referencing it (e.g. "From '1x1 Sarah/Jamie': ...").
- Be direct. No preamble like "Based on the notes..." or "According to your notes...".
- For time-relative questions (latest, last, most recent, etc.): the note sections are already sorted newest-first. Anchor your answer to the FIRST section shown — that is the most recent one.\
"""

_TEMPORAL_KEYWORDS = frozenset({
    "latest", "last", "recent", "most recent", "newest",
    "yesterday", "this week", "this month", "today",
    "current", "recently", "new", "now",
})


def _is_temporal_query(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _TEMPORAL_KEYWORDS)


def _embed_query(text: str) -> list[float]:
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def _retrieve(question: str) -> list[dict]:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_or_create_collection(_COLLECTION)
    if col.count() == 0:
        return []

    vector = _embed_query(question)
    is_temporal = _is_temporal_query(question)
    n_results = min(TOP_K * 2 if is_temporal else TOP_K, col.count())

    results = col.query(
        query_embeddings=[vector],
        n_results=n_results,
        include=["metadatas", "distances", "documents"],
    )

    if is_temporal:
        # Return section-level chunks sorted by section_date DESC (newest first)
        sections = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            sections.append({
                "body": doc,
                "title": meta["note_title"],
                "modified": meta["modified"],
                "section_date": meta.get("section_date", ""),
                "_dist": dist,
            })
        sections.sort(
            key=lambda s: (s["section_date"] or "0000-00-00"),
            reverse=True,
        )
        return sections[:TOP_K]
    else:
        # Whole-note expansion: group by note_id, load full note bodies
        best_score: dict[str, float] = {}
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            nid = meta["note_id"]
            if nid not in best_score or dist < best_score[nid]:
                best_score[nid] = dist
        ranked_ids = sorted(best_score, key=lambda nid: best_score[nid])
        notes = []
        for nid in ranked_ids:
            entry = cache.load_note(nid)
            if entry:
                notes.append(entry)
        return notes


def ask(question: str) -> None:
    results = _retrieve(question)
    if not results:
        print("No indexed notes found. Run: notey index")
        return

    context_parts = [
        f'<note title="{n["title"]}" modified="{n["modified"]}">\n{n["body"]}\n</note>'
        for n in results
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
    seen: set[str] = set()
    for n in results:
        section_date = n.get("section_date", "")
        label = f"section {section_date}" if section_date else n["modified"]
        key = f"{n['title']}|{label}"
        if key not in seen:
            seen.add(key)
            print(f"  • {n['title']}  ({label})")
