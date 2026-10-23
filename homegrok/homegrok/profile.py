"""Your current resume. Paste it or drop a file on the page and HomeGrok uses it from then on:
it goes to the top of every resume task and chat, and the memory bot reads it next cycle."""
import base64
import json
import time
from pathlib import Path

from .collect import READERS

ALLOWED = {".pdf", ".docx", ".pptx", ".txt", ".md"}


def resume_dir(ws):
    d = ws.root / "profile"
    d.mkdir(exist_ok=True)
    return d


def set_resume(ws, text=None, filename=None, data_b64=None):
    folder = resume_dir(ws)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if data_b64:
        ext = Path(filename or "").suffix.lower()
        if ext not in ALLOWED:
            raise ValueError(f"use a {', '.join(sorted(ALLOWED))} file")
        path = folder / f"resume-{stamp}{ext}"
        path.write_bytes(base64.b64decode(data_b64))
        reader = READERS.get(ext)
        text = reader(path) if reader else path.read_text(encoding="utf-8", errors="replace")
    else:
        path = folder / f"resume-{stamp}.txt"
        path.write_text(text or "", encoding="utf-8")
    text = (text or "").strip()
    if len(text) < 100:
        raise ValueError("that resume looks empty")
    (folder / "current.txt").write_text(text, encoding="utf-8")
    (folder / "current.json").write_text(json.dumps({"source": filename or "pasted text", "path": str(path),
                                                     "updated": time.time(), "chars": len(text)}))
    cfg = ws.load_config()   # the memory bot reads the newest resume instead of older ones
    cfg["extra_files"] = [str(path)]
    ws.save_config(cfg)
    return current_resume_info(ws)


def current_resume(ws):
    p = resume_dir(ws) / "current.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def current_resume_info(ws):
    p = resume_dir(ws) / "current.json"
    return json.loads(p.read_text()) if p.exists() else None
