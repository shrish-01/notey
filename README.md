# notey

**Ask questions about your Mac Notes — get answers instantly. Runs 100% on your machine.**

No cloud. No subscriptions. No data leaves your laptop.

---

## What is notey?

notey is a local AI-powered search tool for Apple Notes. Instead of scrolling through dozens of notes trying to remember where you wrote something, you just ask:

```
notey "what did I discuss with Alex last month?"
notey "any ideas I had about onboarding?"
notey "what questions do I still need to ask my manager?"
```

It reads your Notes, understands the *meaning* of your question (not just keywords), and gives you a direct answer with citations.

### The problem it solves

Mac Notes is great for capturing things fast — meetings, ideas, decisions, questions, research. But finding something later is painful. Spotlight only matches exact keywords. The built-in search is even more limited. If you wrote "stressed about the deadline" instead of "worried", Spotlight won't find it.

notey uses vector embeddings + a local LLM to understand semantic meaning, so searching for "team feedback" surfaces notes about "performance reviews", "1x1 observations", and "manager comments" — not just notes with the literal words "team feedback".

### Why fully local?

Notes are personal. They often contain things you'd never want to upload anywhere — API keys, personal reflections, sensitive work conversations, financial details. notey uses:

- **Ollama** — runs the LLM and embedding model on your machine
- **ChromaDB** — stores the vector index as a local file (`~/.notey/`)
- **AppleScript** — reads directly from the Notes app, no file system access needed

Nothing is transmitted over the network. Ever.

---

## How to use notey

### Ask a question

```bash
notey "what should I follow up on from my last 1x1 with Alex?"
notey "notes about the database migration"
notey "what was the budget breakdown my manager mentioned?"
notey "ideas I had about scaling the pipeline"
notey "any open questions from the Q1 planning session?"
```

### Utility commands

```bash
notey index     # force a full re-index of all your notes
notey status    # show how many notes are indexed and when
```

### Sample output

```
$ notey "what questions do I still have for my manager?"

From '1x1 Sarah/Jamie' (Jan 7th):
- Is there any allocated budget for Tech Conferences for the team?
- Accessories — what's approved and what's not?
- Work desk setup reimbursement details?

From '1x1 Sarah/Jamie' (Jan 12th):
- Work Setup Reimbursement — items to check for.
- Tech Conference budget — is it available?

Sources:
  • 1x1 Sarah/Jamie  (Monday, 27 April 2026 at 5:32:27 PM)
  • Scheduling 1x1s  (Friday, 16 January 2026 at 9:35:30 AM)
```

### Auto re-indexing

If you've added or edited notes since the last run, notey detects the change and re-indexes automatically before answering. This adds a few seconds. You can also trigger it manually with `notey index`.

---

## Setting up locally

### Prerequisites

| Requirement | Notes |
|---|---|
| macOS | Required — notey uses AppleScript to read the Notes app |
| Python 3.11+ | Check with `python3 --version` |
| [Ollama](https://ollama.com) | Free, local LLM runner for macOS |

Install Ollama from [ollama.com](https://ollama.com) if you haven't already. It's a one-click `.dmg` install.

---

### Step 1 — Clone the repo

```bash
git clone git@github.com:shrish-01/notey.git
cd notey
```

---

### Step 2 — Configure your Notes folder

**Do this before anything else.** Open `notey/config.py` and update lines 5–6 to match your Mac Notes setup:

```python
# notey/config.py

ACCOUNT = "On My Mac"   # ← change this
FOLDER  = "Notes"       # ← change this
```

**How to find your account and folder name:**

1. Open the **Notes** app on your Mac.
2. In the left sidebar, look at the section headers — these are your **accounts** (e.g. "On My Mac", "iCloud", "Google").
3. Under the account, look at the folder names — these are your **folders** (e.g. "Notes", "Work", "Personal").
4. Copy those names exactly (case-sensitive) into `config.py`.

```
Sidebar example:
  On My Mac          ← this is ACCOUNT
    └── Notes        ← this is FOLDER
    └── Work
  iCloud
    └── Notes
```

You can also exclude specific notes by title (e.g. a note with sensitive credentials):

```python
EXCLUDED_TITLES = {"API Keys", "Passwords"}
```

---

### Step 3 — Pull the Ollama models

```bash
ollama pull llama3.1:8b       # the LLM that answers your questions (~4.7 GB)
ollama pull nomic-embed-text  # the embedding model for search (~274 MB)
```

This is a one-time download. Both models run entirely on-device.

---

### Step 4 — Create a Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

### Step 5 — Make notey available everywhere

So you can run `notey` from any directory, not just this folder:

```bash
mkdir -p ~/.local/bin
ln -sf "$(pwd)/.venv/bin/notey" ~/.local/bin/notey
```

Then make sure `~/.local/bin` is in your PATH. Add this line to your `~/.zshrc` (or `~/.bashrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Apply it immediately:

```bash
source ~/.zshrc
```

Alternatively, if you use [pipx](https://pipx.pypa.io):

```bash
pipx install -e .
```

---

### Step 6 — Build the index

```bash
notey index
```

On the **first run**, macOS will show a permission prompt:

> **"Terminal" wants access to control "Notes".**

Click **OK**. This is a one-time grant. notey uses AppleScript to read your notes — it never modifies them.

The index is stored in `~/.notey/` on your machine. Nothing is uploaded anywhere.

---

### Step 7 — Ask your first question

```bash
notey "what's the most recent thing I noted about my manager?"
```

You should get a streamed response in a few seconds, followed by a `Sources:` section showing which notes were used.

---

## Configuration reference

All config lives in `notey/config.py`.

| Setting | Default | What it does |
|---|---|---|
| `ACCOUNT` | `"On My Mac"` | The Notes account to index (sidebar section header) |
| `FOLDER` | `"Notes"` | The folder within that account to index |
| `EXCLUDED_TITLES` | `{"API Keys"}` | Note titles to skip entirely |
| `CHAT_MODEL` | `"llama3.1:8b"` | Ollama model used to generate answers |
| `EMBED_MODEL` | `"nomic-embed-text"` | Ollama model used to create embeddings |
| `TOP_K` | `8` | Number of note chunks retrieved per query |

### Swap the LLM

If you want faster responses or have less RAM, try a smaller model:

```python
CHAT_MODEL = "mistral:7b"    # lighter, faster
CHAT_MODEL = "gemma2:9b"     # good balance
CHAT_MODEL = "llama3.1:8b"   # default, best quality
```

Pull the model first with `ollama pull <model-name>`, then re-run your query (no re-indexing needed).

---

## How it works

```
Your question
     │
     ▼
[nomic-embed-text]  ← runs locally via Ollama
     │  embed the question
     ▼
[ChromaDB]          ← local vector store at ~/.notey/chroma/
     │  find top-8 most relevant note chunks
     │  expand to full matching notes
     ▼
[llama3.1:8b]       ← runs locally via Ollama
     │  generate an answer grounded in your notes
     ▼
Answer + Sources
```

When you run `notey index`, your notes are read via AppleScript (no file system permissions needed), split into overlapping chunks, embedded with `nomic-embed-text`, and stored in ChromaDB. On each query, the most relevant chunks are retrieved, the full parent notes are loaded, and `llama3.1:8b` generates a grounded answer.

---

## Requirements

- **macOS** (required — AppleScript and the Notes app are macOS-only)
- **Apple Silicon recommended** — Ollama runs natively on M1/M2/M3/M4, but Intel Macs work too
- **Python ≥ 3.11**
- **Ollama** installed and running (`ollama serve` starts it; the menu bar app keeps it running automatically)
- **~6 GB free disk space** for the two models

---

## Troubleshooting

**`notey: command not found`**
Make sure `~/.local/bin` is in your PATH (see Step 5) and that you've sourced your shell config.

**`Ollama is not running`**
Start Ollama: open the Ollama app from your Applications folder, or run `ollama serve` in a terminal.

**`AppleScript failed`**
Check that you clicked "OK" on the Notes permission prompt. To re-trigger it: System Settings → Privacy & Security → Automation → Terminal → enable Notes.

**Index is stale / notes not showing up**
Run `notey index` to force a full rebuild.
