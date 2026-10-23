"""Training path, step 2: Clean data (normalize, redact secrets, drop junk, dedupe)."""
import hashlib
import json
import os
import re
import unicodedata

from .config import iter_jsonl

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "[REDACTED]"),
    (re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}\b"), "[REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "[REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)(\s*[:=]\s*)\S+"),
     r"\1\2[REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED SSN]"),
]
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLANKS = re.compile(r"\n{3,}")
_TRAILING = re.compile(r"[ \t]+\n")
# Lines that start like machine output: JSON records or timestamps.
_LOG_LINE = re.compile(r"^\s*(?:\{\"|\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}|\[?\d{2}:\d{2}:\d{2})")


def _luhn_ok(digits):
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def _redact_card(match):
    digits = re.sub(r"\D", "", match.group())
    return "[REDACTED CARD]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match.group()


def redact(text):
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return _CARD.sub(_redact_card, text)


def looks_like_machine_log(text):
    lines = [line for line in text[:50_000].splitlines() if line.strip()][:300]
    return len(lines) >= 20 and sum(bool(_LOG_LINE.match(line)) for line in lines) / len(lines) > 0.6


def clean_text(text):
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _TRAILING.sub("\n", text)
    text = _BLANKS.sub("\n\n", text)
    return redact(text.strip())


def looks_like_text(text):
    if len(text) < 64:
        return False
    sample = text[:5000]
    if sample.count("�") > len(sample) * 0.01:  # mostly undecodable bytes
        return False
    letters = sum(c.isalpha() or c.isspace() for c in sample)
    return letters / len(sample) > 0.5 and not looks_like_machine_log(text)


def clean(ws, log=print):
    seen = set()
    kept = dropped = dupes = chars = 0
    tmp = ws.clean_docs.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as out:
        for doc in iter_jsonl(ws.raw_docs):
            text = clean_text(doc["text"])
            if not looks_like_text(text):
                dropped += 1
                continue
            digest = hashlib.sha1(text.encode()).hexdigest()
            if digest in seen:
                dupes += 1
                continue
            seen.add(digest)
            out.write(json.dumps({"path": doc["path"], "text": text}) + "\n")
            kept += 1
            chars += len(text)
    # Leave the existing file untouched when nothing changed, so nothing downstream rebuilds.
    changed = not ws.clean_docs.exists() or _file_sha(tmp) != _file_sha(ws.clean_docs)
    if changed:
        os.replace(tmp, ws.clean_docs)
    else:
        os.remove(tmp)
    log(f"  kept {kept} docs ({chars / 1e6:.1f}M chars), dropped {dropped} junk, {dupes} duplicates")
    return {"kept": kept, "dropped": dropped, "duplicates": dupes, "chars": chars, "changed": changed}


def _file_sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
