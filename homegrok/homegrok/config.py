"""Workspace layout and user configuration.

Everything HomeGrok produces lives in one workspace folder (default: ./workspace).
Nothing is ever sent off the machine.
"""
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE = PROJECT_ROOT / "workspace"

DEFAULT_CONFIG = {
    # Folders HomeGrok is allowed to learn from. Empty until the user opts in.
    "folders": [],
    # Extra glob patterns (matched against file and folder names) to never read.
    "exclude": [],
    "max_file_mb": 2,
    "max_total_mb": 300,
}


class Workspace:
    def __init__(self, path=None):
        path = path or os.environ.get("HOMEGROK_WORKSPACE") or DEFAULT_WORKSPACE
        self.root = Path(path).expanduser().resolve()
        for sub in ("raw", "clean", "models", "logs", "evolution"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # Collect data -> Clean data
    @property
    def raw_docs(self): return self.root / "raw" / "docs.jsonl"
    @property
    def clean_docs(self): return self.root / "clean" / "docs.jsonl"

    # Public text the local model learns from (see webcorpus.py)
    @property
    def public_docs(self): return self.root / "public" / "docs.jsonl"

    # Tokenizer + encoded corpus
    @property
    def tokenizer(self): return self.root / "tokenizer.json"
    @property
    def tokens(self): return self.root / "tokens.npy"
    @property
    def tokens_meta(self): return self.root / "tokens.json"

    # Vector database (search index over your documents)
    @property
    def index(self): return self.root / "index.pkl"

    # Model storage
    @property
    def models(self): return self.root / "models"
    @property
    def registry(self): return self.root / "models" / "registry.json"

    # Evolution (genetic training loop)
    @property
    def evolution(self): return self.root / "evolution"

    # Monitoring, logging, billing, security
    @property
    def logs(self): return self.root / "logs"
    @property
    def api_key(self): return self.root / "api_key"

    @property
    def config_path(self): return self.root / "config.json"

    def load_config(self):
        cfg = dict(DEFAULT_CONFIG)
        if self.config_path.exists():
            cfg.update(json.loads(self.config_path.read_text()))
        return cfg

    def save_config(self, cfg):
        self.config_path.write_text(json.dumps(cfg, indent=2))


def iter_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def pick_device():
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"
