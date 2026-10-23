"""Model storage: checkpoints plus a registry that records which model is live."""
import json
import os
import time

import torch

from .model import GPT, GPTConfig


def read_registry(ws):
    if ws.registry.exists():
        return json.loads(ws.registry.read_text())
    return {"current": None, "models": {}}


def write_registry(ws, reg):
    tmp = ws.registry.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2))
    os.replace(tmp, ws.registry)


def save_checkpoint(path, model, extra=None):
    torch.save({"config": model.cfg.to_dict(), "state": model.state_dict(), **(extra or {})}, path)


def load_checkpoint(path, device="cpu"):
    ckpt = torch.load(path, map_location=device, weights_only=True)
    model = GPT(GPTConfig(**ckpt["config"]))
    model.load_state_dict(ckpt["state"])
    return model.to(device), ckpt


def reset_local_models(ws):
    """Forget every local model, the evolution state and the encoded corpus (used when the
    vocabulary changes, since old models can't read the new one). The serving process keeps
    answering with the model it has loaded until a new one is promoted."""
    for pattern in ("models/*.pt", "evolution/*.pt"):
        for path in ws.root.glob(pattern):
            path.unlink(missing_ok=True)
    for path in (ws.registry, ws.evolution / "state.json", ws.tokens, ws.tokens_meta):
        path.unlink(missing_ok=True)


def current_model_info(ws):
    reg = read_registry(ws)
    name = reg.get("current")
    return (name, reg["models"][name]) if name else (None, None)


def promote(ws, name, path, model, metrics, log=print):
    """Store a model that passed the quality gate and make it the live model."""
    final = ws.models / f"{name}.pt"
    if os.path.abspath(path) != os.path.abspath(final):
        save_checkpoint(final, model, {"metrics": metrics})
    reg = read_registry(ws)
    previous = reg.get("current")
    reg["models"][name] = {
        "path": str(final),
        "config": model.cfg.to_dict(),
        "params": model.num_params(),
        "metrics": metrics,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    reg["current"] = name
    # Keep only the 3 most recent promoted models on disk.
    names = sorted(reg["models"], key=lambda n: reg["models"][n]["created"])
    for old in names[:-3]:
        if old != name:
            try:
                os.remove(reg["models"][old]["path"])
            except OSError:
                pass
            del reg["models"][old]
    write_registry(ws, reg)
    log(f"  promoted {name} (val loss {metrics['val_loss']:.3f}) — replaces {previous or 'nothing'}")
