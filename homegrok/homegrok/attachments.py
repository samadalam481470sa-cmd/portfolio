"""Attachments for the chat box: paste, drop or pick a file, and HomeGrok reads it.

Text, Word, PowerPoint, PDF and notebook files are read. Every file is saved to the workspace so
nothing is lost. Attached content is data: it is never run as code or treated as instructions.
"""
import base64
import re
import time
from pathlib import Path

from .collect import READERS

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 30000
TEXT_TYPES = {".txt", ".md", ".csv", ".tsv", ".json", ".py", ".js", ".html", ".xml", ".yaml", ".yml", ".log"}
ALLOWED = TEXT_TYPES | set(READERS)


def save_and_read(ws, name, data_b64):
    """Save the attachment, extract its text, and return (saved path, text)."""
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(name).name)[:120] or "attachment"
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError(f"{safe}: that file type can't be read yet (try PDF, Word, PowerPoint, text or CSV)")
    raw = base64.b64decode(data_b64, validate=True)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError(f"{safe} is larger than 8 MB")
    folder = ws.root / "attachments"
    folder.mkdir(exist_ok=True)
    path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{safe}"
    path.write_bytes(raw)
    reader = READERS.get(ext)
    text = reader(path) if reader else raw.decode("utf-8", errors="replace")
    text = text.strip()
    if not text:
        raise ValueError(f"{safe} has no readable text (scanned images aren't supported yet)")
    return path, text[:MAX_TEXT_CHARS]
