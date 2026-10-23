"""Re-read your folders and rebuild what depends on them, only when something changed."""
from .clean import clean
from .collect import collect
from .vectordb import build_index


def refresh_data(ws, log=print):
    """Returns True if your files changed (the cleaned corpus and search index were rebuilt)."""
    quiet = lambda *_: None
    collected = collect(ws, ws.load_config(), log=quiet)
    if not collected["written"]:
        log(f"macOS is blocking HomeGrok from reading {', '.join(collected['blocked'])}. "
            "Allow it in System Settings > Privacy & Security > Files and Folders")
        return False
    stats = clean(ws, log=quiet)
    if not stats["changed"]:
        return False
    build_index(ws, log=quiet)
    log(f"Your files changed: re-indexed {stats['kept']} files")
    return True
