import os
from pathlib import Path

# Notes source
ACCOUNT = "On My Mac"
FOLDER = "Notes"
EXCLUDED_TITLES = {"API Keys"}

# Ollama
OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "llama3.1:8b"

# Paths
NOTEY_DIR = Path.home() / ".notey"
CHROMA_DIR = NOTEY_DIR / "chroma"
STATE_FILE = NOTEY_DIR / "state.json"
NOTES_CACHE_FILE = NOTEY_DIR / "notes_cache.json"
NOTES_DB = Path.home() / "Library" / "Group Containers" / "group.com.apple.notes" / "NoteStore.sqlite"

# RAG
CHUNK_SIZE = 1000       # approximate tokens (chars / 4)
CHUNK_OVERLAP = 100
TOP_K = 8

NOTEY_DIR.mkdir(parents=True, exist_ok=True)
