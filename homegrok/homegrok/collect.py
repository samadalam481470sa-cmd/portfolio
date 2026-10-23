"""Training path, step 1: Collect data from the folders the user opted in to."""
import fnmatch
import html
import json
import os
import re
import zipfile
from collections import Counter
from pathlib import Path

from .config import PROJECT_ROOT

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".tex", ".org", ".csv", ".tsv", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".xml", ".html", ".htm", ".css",
    ".py", ".ipynb", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".swift",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".go", ".rs", ".rb", ".php",
    ".r", ".m", ".scala", ".sql", ".sh", ".zsh", ".bash", ".lua", ".pl",
}
DOCUMENT_EXTENSIONS = {".docx", ".pptx", ".pdf"}
MAX_DOCUMENT_MB = 40
MAX_PDF_PAGES = 300

# Folders that are never useful to learn from: app internals, build output, machine logs.
SKIP_DIRS = {
    "node_modules", "__pycache__", "site-packages", "dist-packages", "venv", "env",
    "Library", "Applications", "build", "dist", "target", "Photos Library.photoslibrary",
    "Logs", "logs", "log", "Caches", "cache", "tmp", "temp",
}

# Names that suggest credentials or secrets. These files are never opened.
SENSITIVE_PATTERNS = [
    ".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.kdbx", "*keychain*",
    "*credential*", "*secret*", "*password*", "*passwd*", "*token*", "*wallet*",
    "*.sqlite", "*.db",
]

_TAG = re.compile(r"<[^>]+>")


def _matches(name, patterns):
    lower = name.lower()
    return any(fnmatch.fnmatch(lower, p) for p in patterns)


def _read_notebook(path):
    nb = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    parts = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") in ("markdown", "code"):
            src = cell.get("source", "")
            parts.append("".join(src) if isinstance(src, list) else src)
    return "\n\n".join(parts)


def _xml_text(xml, paragraph_tag):
    xml = re.sub(rf"</{paragraph_tag}>", "\n", xml)
    xml = re.sub(r"<(?:w:tab|w:br|a:br)[^>]*/>", " ", xml)
    return html.unescape(_TAG.sub("", xml))


def _read_docx(path):
    with zipfile.ZipFile(path) as z:
        return _xml_text(z.read("word/document.xml").decode("utf-8", "replace"), "w:p")


def _read_pptx(path):
    with zipfile.ZipFile(path) as z:
        slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        parts = [f"[Slide {i}]\n" + _xml_text(z.read(n).decode("utf-8", "replace"), "a:p")
                 for i, n in enumerate(slides, 1)]
    return "\n\n".join(parts)


def _read_pdf(path):
    import logging
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # malformed-but-readable PDFs are common
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("encrypted PDF")
    return "\n\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES])


READERS = {".ipynb": _read_notebook, ".docx": _read_docx, ".pptx": _read_pptx, ".pdf": _read_pdf}


def collect(ws, cfg, log=print):
    """Read the opted-in folders into raw/docs.jsonl.

    If macOS blocks any configured folder (common for background services that haven't been
    granted access), the previous collection is kept instead of being replaced by a partial one.
    """
    folders = cfg.get("folders") or []
    if not folders:
        raise SystemExit("No folders configured. Run: ./hg setup --folders ~/Documents ~/Desktop")

    exclude = SENSITIVE_PATTERNS + list(cfg.get("exclude", []))
    max_text = int(cfg["max_file_mb"] * 1024 * 1024)
    max_doc = MAX_DOCUMENT_MB * 1024 * 1024
    max_total = int(cfg["max_total_mb"] * 1024 * 1024)
    # Never read HomeGrok itself or what Claude wrote for you (Claude's outputs must not
    # end up in the local model's training data).
    from .tasks import RESULTS_ROOT
    never_read = {PROJECT_ROOT.resolve(), ws.root, RESULTS_ROOT.resolve()}

    stats = Counter()
    blocked = []
    total = 0
    tmp = ws.raw_docs.with_suffix(".tmp")

    def on_error(err):
        stats["permission_denied"] += 1

    def read(path):
        """Text of one file, or None if it should be skipped."""
        ext = path.suffix.lower()
        is_doc = ext in DOCUMENT_EXTENSIONS
        if path.name.startswith((".", "~$")) or not (is_doc or ext in TEXT_EXTENSIONS):
            stats["not_text"] += 1
            return None
        if _matches(path.name, exclude):
            stats["sensitive_skipped"] += 1
            return None
        try:
            size = path.stat().st_size
            if size == 0 or size > (max_doc if is_doc else max_text):
                stats["too_large_or_empty"] += 1
                return None
            reader = READERS.get(ext)
            text = reader(path) if reader else path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # unreadable, corrupt or encrypted files are skipped
            stats["unreadable"] += 1
            return None
        stats["documents" if is_doc else "text_files"] += 1
        return text

    with open(tmp, "w", encoding="utf-8") as out:
        # Single files you picked (for example your resume), wherever they are.
        for extra in cfg.get("extra_files") or []:
            path = Path(extra).expanduser()
            text = read(path) if path.is_file() else None
            if text:
                out.write(json.dumps({"path": str(path), "text": text}) + "\n")
                stats["files"] += 1
                total += len(text)
        for folder in folders:
            folder = Path(folder).expanduser().resolve()
            if not folder.is_dir():
                log(f"  ! skipping {folder} (not a folder)")
                continue
            try:
                os.listdir(folder)
            except PermissionError:
                blocked.append(str(folder))
                continue
            log(f"  scanning {folder}")
            for dirpath, dirnames, filenames in os.walk(folder, onerror=on_error):
                here = Path(dirpath)
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith(".") and d not in SKIP_DIRS
                    and not _matches(d, exclude) and (here / d).resolve() not in never_read
                ]
                for name in filenames:
                    path = here / name
                    text = read(path)
                    if text is None:
                        continue
                    out.write(json.dumps({"path": str(path), "text": text}) + "\n")
                    stats["files"] += 1
                    total += len(text)
                    if total >= max_total:
                        log(f"  reached max_total_mb={cfg['max_total_mb']}, stopping")
                        break
                if total >= max_total:
                    break
            if total >= max_total:
                break

    stats["chars"] = total
    if blocked:
        os.remove(tmp)
        log(f"  macOS blocked access to {', '.join(blocked)}; keeping the previous collection")
        return {**stats, "blocked": blocked, "written": False}
    os.replace(tmp, ws.raw_docs)
    log(f"  collected {stats['files']} files ({stats['documents']} documents), {total / 1e6:.1f}M characters")
    if stats["sensitive_skipped"]:
        log(f"  skipped {stats['sensitive_skipped']} files that looked like secrets")
    if stats["permission_denied"]:
        log(f"  {stats['permission_denied']} folders were blocked by macOS privacy settings")
    return {**stats, "blocked": [], "written": True}
