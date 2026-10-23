"""The model, built exactly like the diagram (decoder-only transformer):

    Input text -> Tokenizer -> Embeddings + position
      -> [ Layer norm -> Masked attention + add -> Layer norm -> Feed-forward + add ] x N
      -> Final layer norm -> Linear layer -> Softmax -> Next word -> add to input, repeat
"""
import math
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class GPTConfig:
    vocab_size: int
    block_size: int = 256
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 256
    dropout: float = 0.1

    def to_dict(self):
        return asdict(self)


class MaskedSelfAttention(nn.Module):
    """Looks at earlier words only (causal mask)."""

    def __init__(self, cfg):
        super().__init__()
        assert cfg.n_embd % cfg.n_head == 0
        self.n_head = cfg.n_head
        self.qkv = nn.Linear(cfg.n_embd, 3 * cfg.n_embd)
        self.proj = nn.Linear(cfg.n_embd, cfg.n_embd)
        self.dropout = cfg.dropout
        self.resid_drop = nn.Dropout(cfg.dropout)

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        q, k, v = (t.view(B, T, self.n_head, C // self.n_head).transpose(1, 2) for t in (q, k, v))
        y = F.scaled_dot_product_attention(
            q, k, v, is_causal=True, dropout_p=self.dropout if self.training else 0.0)
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.resid_drop(self.proj(y))


class FeedForward(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(cfg.n_embd, 4 * cfg.n_embd),
            nn.GELU(),
            nn.Linear(4 * cfg.n_embd, cfg.n_embd),
            nn.Dropout(cfg.dropout),
        )

    def forward(self, x):
        return self.net(x)


class Block(nn.Module):
    """One of the N repeated blocks (green in the diagram)."""

    def __init__(self, cfg):
        super().__init__()
        self.ln1 = nn.LayerNorm(cfg.n_embd)
        self.attn = MaskedSelfAttention(cfg)
        self.ln2 = nn.LayerNorm(cfg.n_embd)
        self.ff = FeedForward(cfg)

    def forward(self, x):
        x = x + self.attn(self.ln1(x))   # layer norm -> masked attention + add
        x = x + self.ff(self.ln2(x))     # layer norm -> feed-forward + add
        return x


class GPT(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.cfg = cfg
        self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.n_embd)   # numbers to vectors
        self.pos_emb = nn.Embedding(cfg.block_size, cfg.n_embd)   # + position
        self.drop = nn.Dropout(cfg.dropout)
        self.blocks = nn.ModuleList([Block(cfg) for _ in range(cfg.n_layer)])
        self.ln_f = nn.LayerNorm(cfg.n_embd)                      # final layer norm
        self.lm_head = nn.Linear(cfg.n_embd, cfg.vocab_size, bias=False)  # linear layer
        self.lm_head.weight = self.tok_emb.weight                 # weight tying
        self.apply(self._init)
        for name, p in self.named_parameters():
            if name.endswith("proj.weight") or name.endswith("net.2.weight"):
                nn.init.normal_(p, mean=0.0, std=0.02 / math.sqrt(2 * cfg.n_layer))

    @staticmethod
    def _init(m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, mean=0.0, std=0.02)
        if isinstance(m, nn.Linear) and m.bias is not None:
            nn.init.zeros_(m.bias)

    def num_params(self):
        return sum(p.numel() for p in self.parameters()) - self.pos_emb.weight.numel()

    def forward(self, idx, targets=None):
        B, T = idx.shape
        pos = torch.arange(T, device=idx.device)
        x = self.drop(self.tok_emb(idx) + self.pos_emb(pos))
        for block in self.blocks:
            x = block(x)
        logits = self.lm_head(self.ln_f(x))
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))
        return logits, loss

    @torch.no_grad()
    def generate(self, idx, max_new_tokens, temperature=0.8, top_k=50, top_p=0.95, stop_ids=()):
        self.eval()
        for _ in range(max_new_tokens):
            context = idx[:, -self.cfg.block_size:]
            logits, _ = self(context)
            logits = logits[:, -1, :]
            if temperature <= 0:
                next_id = logits.argmax(dim=-1, keepdim=True)
            else:
                logits = logits / temperature
                if top_k:
                    kth = torch.topk(logits, min(top_k, logits.size(-1))).values[:, -1, None]
                    logits = logits.masked_fill(logits < kth, float("-inf"))
                probs = F.softmax(logits, dim=-1)                 # scores to probabilities
                if top_p < 1.0:
                    sorted_p, sorted_i = probs.sort(dim=-1, descending=True)
                    drop = sorted_p.cumsum(dim=-1) - sorted_p > top_p
                    sorted_p = sorted_p.masked_fill(drop, 0.0)
                    probs = torch.zeros_like(probs).scatter(-1, sorted_i, sorted_p)
                    probs = probs / probs.sum(dim=-1, keepdim=True)
                next_id = torch.multinomial(probs, num_samples=1)  # next word
            idx = torch.cat([idx, next_id], dim=1)                 # add to input, repeat
            if next_id.item() in stop_ids:
                break
        return idx
