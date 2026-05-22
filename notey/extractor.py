import subprocess
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from .config import ACCOUNT, FOLDER, EXCLUDED_TITLES


@dataclass
class Note:
    id: str
    title: str
    modified: str
    body: str  # plain text


class _TextStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3"):
            self._parts.append("\n")

    def get_text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._parts)).strip()


def _strip_html(html: str) -> str:
    parser = _TextStripper()
    parser.feed(html)
    return parser.get_text()


def extract_notes() -> list[Note]:
    script = f'''
tell application "Notes"
    set output to ""
    set targetFolder to folder "{FOLDER}" of account "{ACCOUNT}"
    repeat with n in notes of targetFolder
        if name of n is not in {{{", ".join(f'"{t}"' for t in EXCLUDED_TITLES)}}} then
            set output to output & "<<<NOTE>>>" & (id of n) & "<<<TITLE>>>" & (name of n) & ¬
                "<<<MODIFIED>>>" & ((modification date of n) as string) & ¬
                "<<<BODY>>>" & (body of n)
        end if
    end repeat
    return output
end tell
'''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {result.stderr.strip()}")

    raw = result.stdout.strip()
    if not raw:
        return []

    notes: list[Note] = []
    # Split on <<<NOTE>>> but keep subsequent delimiters
    chunks = raw.split("<<<NOTE>>>")
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            note_id, rest = chunk.split("<<<TITLE>>>", 1)
            title, rest = rest.split("<<<MODIFIED>>>", 1)
            modified, body_html = rest.split("<<<BODY>>>", 1)
            body = _strip_html(body_html)
            notes.append(Note(
                id=note_id.strip(),
                title=title.strip(),
                modified=modified.strip(),
                body=body,
            ))
        except ValueError:
            continue  # malformed chunk, skip

    return notes
