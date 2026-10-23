"""Training path: Train the model -> Test quality -> Model storage."""
import json
import math
import time

import numpy as np
import torch

from .config import iter_jsonl, pick_device
from .model import GPT, GPTConfig
from .storage import current_model_info, load_checkpoint, promote, save_checkpoint
from .tokenizer import Tokenizer

DEFAULT_HP = {"n_layer": 4, "n_head": 4, "n_embd": 256, "block_size": 256,
              "dropout": 0.1, "lr": 6e-4, "batch_size": 16}


# -- data -------------------------------------------------------------------
class NotEnoughData(Exception):
    pass


def build_tokens(ws, tok, log=print):
    """Encode the public corpus (see webcorpus.py), adding only documents not encoded yet.

    The local model learns from public text only, never from your personal files.
    """
    corpus = ws.public_docs
    dtype = np.uint16 if tok.vocab_size < 65536 else np.int32
    tok_mtime = ws.tokenizer.stat().st_mtime
    meta = json.loads(ws.tokens_meta.read_text()) if ws.tokens_meta.exists() else {}
    if meta.get("tok_mtime") != tok_mtime or meta.get("corpus") != str(corpus) or not ws.tokens.exists():
        meta, arr = {"tok_mtime": tok_mtime, "corpus": str(corpus), "docs": 0}, np.zeros(0, dtype=dtype)
    else:
        arr = np.load(ws.tokens)
    ids, docs = [], meta["docs"]
    if corpus.exists():
        with open(corpus, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < meta["docs"] or not line.strip():
                    continue
                ids.extend(tok.encode(json.loads(line)["text"]))
                ids.append(tok.eot)
                docs = i + 1
    if ids:
        arr = np.concatenate([arr, np.array(ids, dtype=dtype)])
        np.save(ws.tokens, arr)
        log(f"  encoded {docs - meta['docs']:,} new documents ({len(arr):,} tokens in total)")
    meta["docs"] = docs
    ws.tokens_meta.write_text(json.dumps(meta))
    return arr


class TokenData:
    def __init__(self, arr, val_fraction=0.1):
        split = int(len(arr) * (1 - val_fraction))
        self.train, self.val = arr[:split], arr[split:]   # stays compact; batches are widened below

    def batch(self, split, batch_size, block_size, device, rng=None):
        data = self.val if split == "val" and len(self.val) > block_size + 1 else self.train
        if len(data) <= block_size + 1:
            raise NotEnoughData(f"Not enough data ({len(data)} tokens) for block_size {block_size}.")
        rng = rng or np.random
        ix = rng.integers(0, len(data) - block_size - 1, batch_size) if hasattr(rng, "integers") \
            else rng.randint(0, len(data) - block_size - 1, batch_size)
        x = np.stack([data[i:i + block_size] for i in ix]).astype(np.int64)
        y = np.stack([data[i + 1:i + 1 + block_size] for i in ix]).astype(np.int64)
        return torch.from_numpy(x).to(device), torch.from_numpy(y).to(device)


def load_data(ws, log=print):
    tok = Tokenizer.load(ws.tokenizer)
    return tok, TokenData(build_tokens(ws, tok, log))


# -- test quality -------------------------------------------------------------
@torch.no_grad()
def evaluate(model, data, device, iters=20, batch_size=16):
    """Validation loss on a fixed set of held-out batches, so every model is graded on the same test."""
    model.eval()
    rng = np.random.default_rng(1234)
    losses = []
    for _ in range(iters):
        x, y = data.batch("val", batch_size, model.cfg.block_size, device, rng)
        losses.append(model(x, y)[1].item())
    model.train()
    loss = float(np.mean(losses))
    return {"val_loss": loss, "perplexity": math.exp(min(loss, 20))}


def quality_gate(ws, candidate, data, device, log=print):
    """A candidate is promoted only if it beats the live model on the same held-out data."""
    metrics = evaluate(candidate, data, device)
    name, info = current_model_info(ws)
    if name is None:
        return True, metrics
    try:
        live, _ = load_checkpoint(info["path"], device)
        live_loss = evaluate(live, data, device)["val_loss"]
    except (OSError, RuntimeError, KeyError):
        return True, metrics
    log(f"  quality gate: candidate {metrics['val_loss']:.3f} vs live {live_loss:.3f}")
    return metrics["val_loss"] < live_loss, metrics


# -- train the model ------------------------------------------------------------
def train_loop(model, data, hp, device, minutes, max_steps=100_000, log=print, log_every=100):
    model.to(device).train()
    decay = [p for n, p in model.named_parameters() if p.dim() >= 2]
    no_decay = [p for n, p in model.named_parameters() if p.dim() < 2]
    opt = torch.optim.AdamW([{"params": decay, "weight_decay": 0.1},
                             {"params": no_decay, "weight_decay": 0.0}],
                            lr=hp["lr"], betas=(0.9, 0.95))
    budget = minutes * 60
    start = time.time()
    step = 0
    while True:
        elapsed = time.time() - start
        progress = max(step / max_steps, elapsed / budget)
        if progress >= 1:
            break
        warm = min(1.0, step / 50)
        lr = hp["lr"] * warm * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress)))
        for g in opt.param_groups:
            g["lr"] = lr
        x, y = data.batch("train", hp["batch_size"], model.cfg.block_size, device)
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        step += 1
        if log_every and step % log_every == 0:
            log(f"  step {step:5d}  loss {loss.item():.3f}  lr {lr:.2e}  {elapsed:5.0f}s")
    return step


def build_model(tok, hp):
    return GPT(GPTConfig(vocab_size=tok.vocab_size, block_size=hp["block_size"], n_layer=hp["n_layer"],
                         n_head=hp["n_head"], n_embd=hp["n_embd"], dropout=hp["dropout"]))


def train(ws, minutes=10, hp=None, resume=False, log=print):
    hp = {**DEFAULT_HP, **(hp or {})}
    device = pick_device()
    tok, data = load_data(ws, log)
    model = build_model(tok, hp)
    name, info = current_model_info(ws)
    if resume and info:
        live, _ = load_checkpoint(info["path"])
        if live.cfg.to_dict() == model.cfg.to_dict():
            model = live
            log(f"  resuming from {name}")
    log(f"  {model.num_params() / 1e6:.2f}M parameters on {device}, training for {minutes} min")
    steps = train_loop(model, data, hp, device, minutes, log=log)
    ok, metrics = quality_gate(ws, model, data, device, log)
    metrics.update({"steps": steps, "hp": hp})
    log(f"  test quality: val loss {metrics['val_loss']:.3f}, perplexity {metrics['perplexity']:.1f}")
    sample = tok.decode(model.generate(torch.tensor([[tok.eot]], device=device), 60)[0].tolist())
    log(f"  sample: {sample[:300]!r}")
    if ok:
        new_name = time.strftime("model-%Y%m%d-%H%M%S")
        tmp = ws.models / "candidate.pt"
        save_checkpoint(tmp, model, {"metrics": metrics})
        promote(ws, new_name, tmp, model, metrics, log)
        tmp.unlink(missing_ok=True)
    else:
        log("  not promoted: did not beat the live model")
    return metrics
