"""Requires:  pip install numpy
Python:    3.12+

Usage in a host app:

    from relearn import Cortex, CortexConfig

    cortex = Cortex(CortexConfig(online=False))
    result = cortex.step()
    cortex.learn_text("your text")
    cortex.relearn(steps=16)
    cortex.reinforce()
    vec = cortex.embed("query")
    cortex.save("cortex.npz")

Set online=True to read Wikipedia / arXiv / Hacker News / RSS with an
identified User-Agent and per-host pacing. Failures fall back offline.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import ssl
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator
from urllib.parse import quote, urlencode, urlparse

import numpy as np


# === exceptions.py ===

"""Library-wide errors so a host app can catch a single hierarchy."""


class RelearnError(Exception):
    """Base error for the cortex."""


class ShapeError(RelearnError):
    """Tensor or parameter shape mismatch."""


class OnlineError(RelearnError):
    """Public-API fetch failed after retries."""


class RateLimitError(OnlineError):
    """Host asked us to slow down."""


class ParseError(OnlineError):
    """Remote payload could not be turned into a document."""


class SerializationError(RelearnError):
    """Save or load of cortex state failed."""


# === rng.py ===

"""Central RNG so a host app can freeze the whole cortex with one seed."""




class RNG:
    def __init__(self, seed: int = 0) -> None:
        self._gen = np.random.default_rng(seed)
        self.seed = seed

    def spawn(self, salt: int) -> "RNG":
        return RNG(int((self.seed + salt) % (2**31 - 1)))

    def uniform(self, low: float, high: float, size=None) -> np.ndarray:
        return self._gen.uniform(low, high, size=size)

    def normal(self, loc: float = 0.0, scale: float = 1.0, size=None) -> np.ndarray:
        return self._gen.normal(loc, scale, size=size)

    def integers(self, low: int, high: int | None = None, size=None) -> np.ndarray:
        return self._gen.integers(low, high, size=size)

    def choice(self, n: int, p: np.ndarray | None = None) -> int:
        if n <= 0:
            raise ValueError("choice over empty set")
        return int(self._gen.choice(n, p=p))

    def shuffle(self, x: np.ndarray) -> np.ndarray:
        self._gen.shuffle(x)
        return x

    def bernoulli(self, p: float, size=None) -> np.ndarray:
        return self._gen.random(size=size) < p

    def gamma(self, shape: float, scale: float = 1.0, size=None) -> np.ndarray:
        return self._gen.gamma(shape, scale, size=size)

    def dirichlet(self, alpha: np.ndarray) -> np.ndarray:
        return self._gen.dirichlet(alpha)


# === config.py ===

"""Host-app configuration. All knobs live here so the cortex stays embeddable."""




@dataclass
class CortexConfig:
    seed: int = 7
    feature_dim: int = 256
    hidden_dim: int = 128
    latent_dim: int = 64
    n_sources: int = 4
    replay_capacity: int = 2048
    prototype_k: int = 24
    ewc_lambda: float = 12.0
    si_c: float = 0.4
    lwf_alpha: float = 0.35
    agem_memory: int = 64
    fisher_decay: float = 0.95
    learn_rate: float = 3e-3
    weight_decay: float = 1e-4
    grad_clip: float = 1.0
    dropout: float = 0.05
    replay_batch: int = 16
    sleep_steps: int = 24
    novelty_mix: float = 0.55
    coherence_mix: float = 0.25
    diversity_mix: float = 0.20
    bandit_alpha: float = 0.35
    ucb_alpha: float = 0.6
    curiosity_scale: float = 0.15
    hebbian_lr: float = 1e-3
    hopfield_beta: float = 8.0
    pca_dim: int = 32
    reservoir_size: int = 96
    online: bool = True
    timeout_seconds: float = 12.0
    rate_limit_seconds: float = 1.5
    max_retries: int = 2
    user_agent: str = (
        "relearn/0.1 (continual-learning library; educational; identified client)"
    )
    wikipedia_language: str = "en"
    rss_feeds: tuple[str, ...] = (
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.nasa.gov/news-release/feed/",
        "https://www.npr.org/rss/rss.php?id=1001",
    )
    arxiv_query: str = "cat:cs.LG"
    hn_endpoint: str = "https://hacker-news.firebaseio.com/v0/topstories.json"
    wikipedia_random: str = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
    wikipedia_summary: str = "https://en.wikipedia.org/api/rest_v1/page/summary/"
    arxiv_api: str = "https://export.arxiv.org/api/query"
    max_document_chars: int = 4000
    history: int = 256
    sources: tuple[str, ...] = field(
        default_factory=lambda: ("wikipedia", "arxiv", "hackernews", "rss")
    )

    def source_index(self, name: str) -> int:
        try:
            return self.sources.index(name)
        except ValueError:
            return 0


# === tensor/broadcast.py ===

"""Gradient unbroadcast helpers for reverse-mode autodiff."""




def unbroadcast(grad: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
    """Sum `grad` over axes that were introduced or stretched by broadcasting."""
    g = np.asarray(grad)
    if target_shape == ():
        return np.asarray(g.sum())
    while g.ndim > len(target_shape):
        g = g.sum(axis=0)
    axes = []
    for i, (gs, ts) in enumerate(zip(g.shape, target_shape)):
        if ts == 1 and gs != 1:
            axes.append(i)
    if axes:
        g = g.sum(axis=tuple(axes), keepdims=True)
    if g.shape != target_shape:
        g = np.reshape(g, target_shape)
    return g


def ensure_grad(existing: np.ndarray | None, incoming: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    piece = unbroadcast(incoming, shape)
    if existing is None:
        return piece
    return existing + piece


# === tensor/tensor.py ===

"""Reverse-mode autodiff tensors. Numpy-backed so a host app needs no Torch."""






class Tensor:
    """Differentiable array. Gradients accumulate via `backward()`."""

    __slots__ = ("data", "grad", "requires_grad", "_children", "_backward", "name")

    def __init__(
        self,
        data,
        requires_grad: bool = False,
        *,
        name: str = "",
        children: tuple["Tensor", ...] = (),
        backward_fn: Callable[[], None] | None = None,
    ) -> None:
        arr = np.array(data, dtype=np.float64, copy=True)
        if arr.ndim == 0:
            arr = arr.reshape(())
        self.data: np.ndarray = arr
        self.grad: np.ndarray | None = None
        self.requires_grad = bool(requires_grad)
        self._children = children
        self._backward = backward_fn or (lambda: None)
        self.name = name

    # ------------------------------------------------------------------ shape
    @property
    def shape(self) -> tuple[int, ...]:
        return self.data.shape

    @property
    def ndim(self) -> int:
        return self.data.ndim

    @property
    def T(self) -> "Tensor":
        return self.transpose()

    def numpy(self) -> np.ndarray:
        return np.array(self.data, copy=True)

    def item(self) -> float:
        return float(self.data.reshape(-1)[0])

    def clone(self) -> "Tensor":
        return Tensor(self.data, requires_grad=self.requires_grad, name=self.name)

    def detach(self) -> "Tensor":
        return Tensor(self.data, requires_grad=False, name=self.name)

    def zero_grad(self) -> None:
        self.grad = None

    def _topo(self) -> list["Tensor"]:
        seen: set[int] = set()
        order: list[Tensor] = []

        def walk(node: Tensor) -> None:
            ident = id(node)
            if ident in seen:
                return
            seen.add(ident)
            for child in node._children:
                walk(child)
            order.append(node)

        walk(self)
        return order

    def backward(self, grad: np.ndarray | None = None) -> None:
        if not self.requires_grad and grad is None and self.data.size != 1:
            raise ShapeError("backward() on non-scalar requires an upstream grad")
        if grad is None:
            if self.data.size != 1:
                raise ShapeError("non-scalar backward needs an explicit gradient")
            incoming = np.ones_like(self.data)
        else:
            incoming = np.asarray(grad, dtype=np.float64)
            if incoming.shape != self.data.shape:
                incoming = unbroadcast(incoming, self.data.shape)
        self.grad = ensure_grad(self.grad, incoming, self.data.shape)
        for node in reversed(self._topo()):
            node._backward()

    # ----------------------------------------------------------------- helpers
    def _binary(
        self,
        other: "Tensor",
        out_data: np.ndarray,
        backward_fn: Callable[[np.ndarray], None],
    ) -> "Tensor":
        requires = self.requires_grad or other.requires_grad
        out = Tensor(out_data, requires_grad=requires, children=(self, other) if requires else ())

        def _b() -> None:
            if out.grad is None:
                return
            backward_fn(out.grad)

        if requires:
            out._backward = _b
        return out

    def _unary(self, out_data: np.ndarray, backward_fn: Callable[[np.ndarray], None]) -> "Tensor":
        out = Tensor(
            out_data,
            requires_grad=self.requires_grad,
            children=(self,) if self.requires_grad else (),
        )

        def _b() -> None:
            if out.grad is None:
                return
            backward_fn(out.grad)

        if self.requires_grad:
            out._backward = _b
        return out

    # ---------------------------------------------------------------- operators
    def __add__(self, other) -> "Tensor":
        other = as_tensor(other)
        out_data = self.data + other.data

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g, self.data.shape)
            if other.requires_grad:
                other.grad = ensure_grad(other.grad, g, other.data.shape)

        return self._binary(other, out_data, _b)

    def __radd__(self, other) -> "Tensor":
        return self.__add__(other)

    def __sub__(self, other) -> "Tensor":
        other = as_tensor(other)
        return self + (other * -1.0)

    def __rsub__(self, other) -> "Tensor":
        return as_tensor(other) - self

    def __neg__(self) -> "Tensor":
        return self * -1.0

    def __mul__(self, other) -> "Tensor":
        other = as_tensor(other)
        out_data = self.data * other.data

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g * other.data, self.data.shape)
            if other.requires_grad:
                other.grad = ensure_grad(other.grad, g * self.data, other.data.shape)

        return self._binary(other, out_data, _b)

    def __rmul__(self, other) -> "Tensor":
        return self.__mul__(other)

    def __truediv__(self, other) -> "Tensor":
        other = as_tensor(other)
        out_data = self.data / other.data

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g / other.data, self.data.shape)
            if other.requires_grad:
                self_over = -self.data / (other.data ** 2)
                other.grad = ensure_grad(other.grad, g * self_over, other.data.shape)

        return self._binary(other, out_data, _b)

    def __rtruediv__(self, other) -> "Tensor":
        return as_tensor(other) / self

    def __pow__(self, power: float) -> "Tensor":
        p = float(power)
        out_data = self.data ** p

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g * p * (self.data ** (p - 1.0)), self.data.shape)

        return self._unary(out_data, _b)

    def __matmul__(self, other) -> "Tensor":
        other = as_tensor(other)
        if self.data.ndim == 1 and other.data.ndim == 1:
            out_data = np.dot(self.data, other.data)

            def _b(g: np.ndarray) -> None:
                gg = np.asarray(g)
                if self.requires_grad:
                    self.grad = ensure_grad(self.grad, gg * other.data, self.data.shape)
                if other.requires_grad:
                    other.grad = ensure_grad(other.grad, gg * self.data, other.data.shape)

            return self._binary(other, out_data, _b)
        out_data = self.data @ other.data

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                if self.data.ndim == 2 and other.data.ndim == 2:
                    self.grad = ensure_grad(self.grad, g @ other.data.T, self.data.shape)
                elif self.data.ndim == 1 and other.data.ndim == 2:
                    self.grad = ensure_grad(self.grad, g @ other.data.T, self.data.shape)
                else:
                    self.grad = ensure_grad(self.grad, g @ np.moveaxis(other.data, -1, -2), self.data.shape)
            if other.requires_grad:
                if self.data.ndim == 2 and other.data.ndim == 2:
                    other.grad = ensure_grad(other.grad, self.data.T @ g, other.data.shape)
                elif self.data.ndim == 1 and other.data.ndim == 2:
                    other.grad = ensure_grad(other.grad, np.outer(self.data, g), other.data.shape)
                else:
                    other.grad = ensure_grad(other.grad, np.moveaxis(self.data, -1, -2) @ g, other.data.shape)

        return self._binary(other, out_data, _b)

    def transpose(self, axes: Iterable[int] | None = None) -> "Tensor":
        ax = tuple(axes) if axes is not None else None
        out_data = self.data.T if ax is None else np.transpose(self.data, ax)
        inv = None if ax is None else tuple(np.argsort(ax))

        def _b(g: np.ndarray) -> None:
            if not self.requires_grad:
                return
            back = g.T if inv is None else np.transpose(g, inv)
            self.grad = ensure_grad(self.grad, back, self.data.shape)

        return self._unary(out_data, _b)

    def reshape(self, *shape: int) -> "Tensor":
        if len(shape) == 1 and isinstance(shape[0], tuple):
            shape = shape[0]  # type: ignore[assignment]
        out_data = self.data.reshape(shape)

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g.reshape(self.data.shape), self.data.shape)

        return self._unary(out_data, _b)

    def sum(self, axis=None, keepdims: bool = False) -> "Tensor":
        out_data = self.data.sum(axis=axis, keepdims=keepdims)

        def _b(g: np.ndarray) -> None:
            if not self.requires_grad:
                return
            gg = g
            if axis is not None and not keepdims:
                gg = np.expand_dims(gg, axis=axis)
            self.grad = ensure_grad(self.grad, np.ones_like(self.data) * gg, self.data.shape)

        return self._unary(out_data, _b)

    def mean(self, axis=None, keepdims: bool = False) -> "Tensor":
        if axis is None:
            n = self.data.size
        else:
            axes = (axis,) if isinstance(axis, int) else tuple(axis)
            n = 1
            for a in axes:
                n *= self.data.shape[a]
        return self.sum(axis=axis, keepdims=keepdims) / float(n)

    def max(self, axis=None, keepdims: bool = False) -> "Tensor":
        out_data = self.data.max(axis=axis, keepdims=keepdims)

        def _b(g: np.ndarray) -> None:
            if not self.requires_grad:
                return
            mask = self.data == (out_data if keepdims or axis is None else np.expand_dims(out_data, axis=axis))
            gg = g if keepdims or axis is None else np.expand_dims(g, axis=axis)
            # split gradient across tied maxima
            denom = np.maximum(mask.sum(axis=axis, keepdims=True), 1.0)
            self.grad = ensure_grad(self.grad, mask * gg / denom, self.data.shape)

        return self._unary(out_data, _b)

    def exp(self) -> "Tensor":
        out_data = np.exp(self.data)

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g * out_data, self.data.shape)

        return self._unary(out_data, _b)

    def log(self) -> "Tensor":
        out_data = np.log(np.clip(self.data, 1e-12, None))

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g / np.clip(self.data, 1e-12, None), self.data.shape)

        return self._unary(out_data, _b)

    def abs(self) -> "Tensor":
        out_data = np.abs(self.data)

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g * np.sign(self.data), self.data.shape)

        return self._unary(out_data, _b)

    def clip(self, lo: float, hi: float) -> "Tensor":
        out_data = np.clip(self.data, lo, hi)

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                mask = (self.data >= lo) & (self.data <= hi)
                self.grad = ensure_grad(self.grad, g * mask, self.data.shape)

        return self._unary(out_data, _b)

    def relu(self) -> "Tensor":
        out_data = np.maximum(self.data, 0.0)

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g * (self.data > 0), self.data.shape)

        return self._unary(out_data, _b)

    def tanh(self) -> "Tensor":
        out_data = np.tanh(self.data)

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g * (1.0 - out_data ** 2), self.data.shape)

        return self._unary(out_data, _b)

    def sigmoid(self) -> "Tensor":
        out_data = 1.0 / (1.0 + np.exp(-self.data))

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                self.grad = ensure_grad(self.grad, g * out_data * (1.0 - out_data), self.data.shape)

        return self._unary(out_data, _b)

    def gelu(self) -> "Tensor":
        # tanh approximation (Hendrycks & Gimpel)
        x = self.data
        inner = np.sqrt(2.0 / np.pi) * (x + 0.044715 * x ** 3)
        th = np.tanh(inner)
        out_data = 0.5 * x * (1.0 + th)

        def _b(g: np.ndarray) -> None:
            if not self.requires_grad:
                return
            d_inner = np.sqrt(2.0 / np.pi) * (1.0 + 3.0 * 0.044715 * x ** 2)
            d_th = (1.0 - th ** 2) * d_inner
            dx = 0.5 * (1.0 + th) + 0.5 * x * d_th
            self.grad = ensure_grad(self.grad, g * dx, self.data.shape)

        return self._unary(out_data, _b)

    def silu(self) -> "Tensor":
        s = 1.0 / (1.0 + np.exp(-self.data))
        out_data = self.data * s

        def _b(g: np.ndarray) -> None:
            if self.requires_grad:
                dx = s + self.data * s * (1.0 - s)
                self.grad = ensure_grad(self.grad, g * dx, self.data.shape)

        return self._unary(out_data, _b)

    def softmax(self, axis: int = -1) -> "Tensor":
        shifted = self.data - self.data.max(axis=axis, keepdims=True)
        ex = np.exp(shifted)
        out_data = ex / ex.sum(axis=axis, keepdims=True)

        def _b(g: np.ndarray) -> None:
            if not self.requires_grad:
                return
            s = out_data
            dot = (g * s).sum(axis=axis, keepdims=True)
            self.grad = ensure_grad(self.grad, s * (g - dot), self.data.shape)

        return self._unary(out_data, _b)

    def log_softmax(self, axis: int = -1) -> "Tensor":
        shifted = self.data - self.data.max(axis=axis, keepdims=True)
        logz = np.log(np.exp(shifted).sum(axis=axis, keepdims=True))
        out_data = shifted - logz

        def _b(g: np.ndarray) -> None:
            if not self.requires_grad:
                return
            sm = np.exp(out_data)
            self.grad = ensure_grad(self.grad, g - sm * g.sum(axis=axis, keepdims=True), self.data.shape)

        return self._unary(out_data, _b)

    def __repr__(self) -> str:
        tag = "grad" if self.requires_grad else "const"
        return f"Tensor({self.data.shape}, {tag}, name={self.name!r})"


def as_tensor(value) -> Tensor:
    if isinstance(value, Tensor):
        return value
    return Tensor(value, requires_grad=False)


# === tensor/functional.py ===

"""Functional ops used by layers and loss heads."""





def relu(x: Tensor) -> Tensor:
    return x.relu()


def gelu(x: Tensor) -> Tensor:
    return x.gelu()


def silu(x: Tensor) -> Tensor:
    return x.silu()


def sigmoid(x: Tensor) -> Tensor:
    return x.sigmoid()


def tanh(x: Tensor) -> Tensor:
    return x.tanh()


def softmax(x: Tensor, axis: int = -1) -> Tensor:
    return x.softmax(axis=axis)


def log_softmax(x: Tensor, axis: int = -1) -> Tensor:
    return x.log_softmax(axis=axis)


def mse(pred: Tensor, target) -> Tensor:
    t = as_tensor(target)
    diff = pred - t
    return (diff * diff).mean()


def cross_entropy(logits: Tensor, target_index: int) -> Tensor:
    logp = logits.log_softmax(axis=-1)
    mask = np.zeros_like(logp.data)
    idx = int(target_index)
    if logp.data.ndim == 1:
        mask[idx] = 1.0
        return -(logp * Tensor(mask)).sum()
    mask[..., idx] = 1.0
    return -(logp * Tensor(mask)).mean()


def nll_onehot(logp: Tensor, onehot: np.ndarray) -> Tensor:
    denom = float(onehot.shape[0] if onehot.ndim > 1 else 1.0)
    return -(logp * as_tensor(onehot)).sum() / max(denom, 1.0)


def kl_div(log_q: Tensor, p: np.ndarray) -> Tensor:
    """KL(p || q) with p as a constant probability vector and log_q from the model."""
    p_t = as_tensor(p)
    log_p = Tensor(np.log(np.clip(p, 1e-12, 1.0)))
    return (p_t * (log_p - log_q)).sum()


def dropout(x: Tensor, p: float, rng: np.random.Generator, train: bool) -> Tensor:
    if (not train) or p <= 0.0:
        return x
    keep = 1.0 - p
    mask = (rng.random(x.shape) < keep).astype(np.float64) / keep
    return x * Tensor(mask)


def layer_norm(x: Tensor, gamma: Tensor, beta: Tensor, eps: float = 1e-5) -> Tensor:
    mean = x.mean(axis=-1, keepdims=True)
    var = ((x - mean) ** 2).mean(axis=-1, keepdims=True)
    normed = (x - mean) / (var + eps) ** 0.5
    return normed * gamma + beta


def rms_norm(x: Tensor, gamma: Tensor, eps: float = 1e-5) -> Tensor:
    ms = (x * x).mean(axis=-1, keepdims=True)
    return x / (ms + eps) ** 0.5 * gamma


# === nn/init.py ===

"""Parameter initialization (He / Xavier / orthogonal)."""





def xavier_uniform(rng: RNG, fan_in: int, fan_out: int) -> np.ndarray:
    limit = np.sqrt(6.0 / (fan_in + fan_out))
    return rng.uniform(-limit, limit, size=(fan_in, fan_out))


def he_uniform(rng: RNG, fan_in: int, fan_out: int) -> np.ndarray:
    limit = np.sqrt(6.0 / fan_in)
    return rng.uniform(-limit, limit, size=(fan_in, fan_out))


def orthogonal(rng: RNG, rows: int, cols: int) -> np.ndarray:
    a = rng.normal(size=(rows, cols))
    q, r = np.linalg.qr(a)
    q = q * np.sign(np.diag(r))
    if q.shape != (rows, cols):
        q = q[:rows, :cols]
    return q


def zeros(shape: tuple[int, ...]) -> np.ndarray:
    return np.zeros(shape, dtype=np.float64)


def ones(shape: tuple[int, ...]) -> np.ndarray:
    return np.ones(shape, dtype=np.float64)


# === nn/module.py ===

"""Module / Parameter scaffolding, same idea as a tiny torch.nn."""






class Parameter(Tensor):
    def __init__(self, data, name: str = "") -> None:
        super().__init__(data, requires_grad=True, name=name)


class Module:
    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}
        self._params: dict[str, Parameter] = {}
        self.training = True

    def __setattr__(self, key: str, value) -> None:
        if isinstance(value, Parameter):
            self._params[key] = value
        elif isinstance(value, Module):
            self._modules[key] = value
        super().__setattr__(key, value)

    def parameters(self) -> list[Parameter]:
        out: list[Parameter] = list(self._params.values())
        for m in self._modules.values():
            out.extend(m.parameters())
        return out

    def named_parameters(self, prefix: str = "") -> Iterator[tuple[str, Parameter]]:
        for k, p in self._params.items():
            yield (f"{prefix}{k}", p)
        for k, m in self._modules.items():
            yield from m.named_parameters(prefix=f"{prefix}{k}.")

    def train(self, mode: bool = True) -> "Module":
        self.training = mode
        for m in self._modules.values():
            m.train(mode)
        return self

    def eval(self) -> "Module":
        return self.train(False)

    def zero_grad(self) -> None:
        for p in self.parameters():
            p.zero_grad()

    def state_dict(self) -> dict[str, np.ndarray]:
        return {name: p.numpy() for name, p in self.named_parameters()}

    def load_state_dict(self, state: dict[str, np.ndarray]) -> None:
        lookup = dict(self.named_parameters())
        for name, array in state.items():
            if name in lookup:
                lookup[name].data = np.array(array, dtype=np.float64, copy=True)
                lookup[name].grad = None

    def forward(self, *args, **kwargs):
        raise NotImplementedError

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)


# === nn/linear.py ===





class Linear(Module):
    def __init__(self, din: int, dout: int, rng: RNG, bias: bool = True, name: str = "linear") -> None:
        super().__init__()
        self.din = din
        self.dout = dout
        self.weight = Parameter(he_uniform(rng, din, dout), name=f"{name}.w")
        self.bias = Parameter(zeros((dout,)), name=f"{name}.b") if bias else None

    def forward(self, x: Tensor) -> Tensor:
        y = x @ self.weight
        if self.bias is not None:
            y = y + self.bias
        return y


class ResidualMLP(Module):
    """Two-layer GELU MLP with optional residual when dims match."""

    def __init__(
        self,
        dim: int,
        hidden: int,
        rng: RNG,
        dropout_p: float = 0.0,
        out_dim: int | None = None,
    ) -> None:
        super().__init__()
        out_dim = out_dim or dim
        self.fc1 = Linear(dim, hidden, rng, name="mlp.fc1")
        self.fc2 = Linear(hidden, out_dim, rng, name="mlp.fc2")
        self.skip = Linear(dim, out_dim, rng, name="mlp.skip") if out_dim != dim else None
        self.dropout_p = dropout_p
        self._rng = np.random.default_rng(rng.seed + 17)

    def forward(self, x: Tensor) -> Tensor:
        h = self.fc1(x).gelu()
        h = dropout(h, self.dropout_p, self._rng, self.training)
        h = self.fc2(h)
        skip = x if self.skip is None else self.skip(x)
        return h + skip


# === nn/norm.py ===




class LayerNorm(Module):
    def __init__(self, dim: int, eps: float = 1e-5) -> None:
        super().__init__()
        self.eps = eps
        self.gamma = Parameter(ones((dim,)), name="ln.g")
        self.beta = Parameter(zeros((dim,)), name="ln.b")

    def forward(self, x: Tensor) -> Tensor:
        return layer_norm(x, self.gamma, self.beta, eps=self.eps)


class RMSNorm(Module):
    def __init__(self, dim: int, eps: float = 1e-5) -> None:
        super().__init__()
        self.eps = eps
        self.gamma = Parameter(ones((dim,)), name="rms.g")

    def forward(self, x: Tensor) -> Tensor:
        return rms_norm(x, self.gamma, eps=self.eps)


# === nn/attention.py ===

"""Scaled dot-product multi-head attention (Vaswani et al.)."""





class MultiHeadAttention(Module):
    def __init__(self, dim: int, n_heads: int, rng: RNG) -> None:
        super().__init__()
        if dim % n_heads != 0:
            raise ValueError("dim must divide n_heads")
        self.dim = dim
        self.n_heads = n_heads
        self.head = dim // n_heads
        self.wq = Parameter(xavier_uniform(rng, dim, dim), name="attn.wq")
        self.wk = Parameter(xavier_uniform(rng, dim, dim), name="attn.wk")
        self.wv = Parameter(xavier_uniform(rng, dim, dim), name="attn.wv")
        self.wo = Parameter(xavier_uniform(rng, dim, dim), name="attn.wo")
        self.bq = Parameter(zeros((dim,)), name="attn.bq")
        self.bk = Parameter(zeros((dim,)), name="attn.bk")
        self.bv = Parameter(zeros((dim,)), name="attn.bv")
        self.bo = Parameter(zeros((dim,)), name="attn.bo")

    def _split(self, x: Tensor) -> Tensor:
        # (T, D) -> (H, T, Dh) via reshape+transpose
        t, _ = x.shape
        h = x.reshape(t, self.n_heads, self.head).transpose((1, 0, 2))
        return h

    def _merge(self, x: np.ndarray) -> np.ndarray:
        # (H, T, Dh) -> (T, D)
        h, t, dh = x.shape
        return np.transpose(x, (1, 0, 2)).reshape(t, h * dh)

    def forward(self, x: Tensor, mask: np.ndarray | None = None) -> Tensor:
        """
        x: (T, D) sequence. Returns (T, D).
        mask: optional (T, T) additive mask (0 keep, -inf block).
        """
        q = x @ self.wq + self.bq
        k = x @ self.wk + self.bk
        v = x @ self.wv + self.bv
        # Use numpy for the batched heads; wire grads through a custom node.
        return _BatchedHeads.apply(q, k, v, self.wo, self.bo, self.n_heads, self.head, mask)


class _BatchedHeads:
    """Manual backward for (H,T,Dh) attention so we do not need full 3D autograd."""

    @staticmethod
    def apply(
        q: Tensor,
        k: Tensor,
        v: Tensor,
        wo: Tensor,
        bo: Tensor,
        n_heads: int,
        head: int,
        mask: np.ndarray | None,
    ) -> Tensor:
        t = q.shape[0]
        qh = q.data.reshape(t, n_heads, head).transpose(1, 0, 2)
        kh = k.data.reshape(t, n_heads, head).transpose(1, 0, 2)
        vh = v.data.reshape(t, n_heads, head).transpose(1, 0, 2)
        scale = 1.0 / np.sqrt(head)
        scores = np.matmul(qh, np.transpose(kh, (0, 2, 1))) * scale
        if mask is not None:
            scores = scores + mask[None, :, :]
        scores = scores - scores.max(axis=-1, keepdims=True)
        weights = np.exp(scores)
        weights = weights / weights.sum(axis=-1, keepdims=True)
        ctx = np.matmul(weights, vh)  # (H, T, Dh)
        merged = ctx.transpose(1, 0, 2).reshape(t, n_heads * head)
        out_data = merged @ wo.data + bo.data
        requires = q.requires_grad or k.requires_grad or v.requires_grad or wo.requires_grad or bo.requires_grad
        out = Tensor(out_data, requires_grad=requires, children=(q, k, v, wo, bo) if requires else ())

        def _backward() -> None:
            if out.grad is None:
                return
            g_out = out.grad  # (T, D)
            g_merged = g_out @ wo.data.T
            if wo.requires_grad:
                wo.grad = merged.T @ g_out if wo.grad is None else wo.grad + merged.T @ g_out
            if bo.requires_grad:
                bo.grad = g_out.sum(axis=0) if bo.grad is None else bo.grad + g_out.sum(axis=0)
            g_ctx = g_merged.reshape(t, n_heads, head).transpose(1, 0, 2)
            g_vh = np.matmul(np.transpose(weights, (0, 2, 1)), g_ctx)
            g_weights = np.matmul(g_ctx, np.transpose(vh, (0, 2, 1)))
            # softmax backward
            dot = (g_weights * weights).sum(axis=-1, keepdims=True)
            g_scores = weights * (g_weights - dot)
            g_scores = g_scores * scale
            g_qh = np.matmul(g_scores, kh)
            g_kh = np.matmul(np.transpose(g_scores, (0, 2, 1)), qh)
            g_q = g_qh.transpose(1, 0, 2).reshape(t, n_heads * head)
            g_k = g_kh.transpose(1, 0, 2).reshape(t, n_heads * head)
            g_v = g_vh.transpose(1, 0, 2).reshape(t, n_heads * head)
            if q.requires_grad:
                q.grad = g_q if q.grad is None else q.grad + g_q
            if k.requires_grad:
                k.grad = g_k if k.grad is None else k.grad + g_k
            if v.requires_grad:
                v.grad = g_v if v.grad is None else v.grad + g_v

        if requires:
            out._backward = _backward
        return out


# === nn/transformer.py ===





def sinusoidal_position(length: int, dim: int) -> np.ndarray:
    pos = np.arange(length)[:, None]
    i = np.arange(dim)[None, :]
    angles = pos / np.power(10000, (2 * (i // 2)) / dim)
    pe = np.zeros((length, dim), dtype=np.float64)
    pe[:, 0::2] = np.sin(angles[:, 0::2])
    pe[:, 1::2] = np.cos(angles[:, 1::2])
    return pe


class TransformerEncoderLayer(Module):
    def __init__(self, dim: int, n_heads: int, rng: RNG, dropout_p: float = 0.0) -> None:
        super().__init__()
        self.n1 = LayerNorm(dim)
        self.attn = MultiHeadAttention(dim, n_heads, rng)
        self.n2 = LayerNorm(dim)
        self.mlp = ResidualMLP(dim, dim * 4, rng, dropout_p=dropout_p)

    def forward(self, x: Tensor, mask: np.ndarray | None = None) -> Tensor:
        h = self.n1(x)
        x = x + self.attn(h, mask=mask)
        h = self.n2(x)
        return self.mlp(h)


class TransformerEncoder(Module):
    def __init__(self, dim: int, n_heads: int, n_layers: int, rng: RNG, dropout_p: float = 0.0) -> None:
        super().__init__()
        self.layers = [TransformerEncoderLayer(dim, n_heads, rng.spawn(i + 3), dropout_p) for i in range(n_layers)]
        for i, layer in enumerate(self.layers):
            self._modules[f"layer{i}"] = layer
        self.final_norm = LayerNorm(dim)

    def forward(self, x: Tensor, mask: np.ndarray | None = None) -> Tensor:
        h = x
        for layer in self.layers:
            h = layer(h, mask=mask)
        return self.final_norm(h)


# === nn/rnn.py ===

"""GRU cell and layer — sequential memory for token streams."""




class GRUCell(Module):
    def __init__(self, din: int, hidden: int, rng: RNG) -> None:
        super().__init__()
        self.din = din
        self.hidden = hidden
        self.wz = Parameter(xavier_uniform(rng, din, hidden), name="gru.wz")
        self.uz = Parameter(orthogonal(rng, hidden, hidden), name="gru.uz")
        self.bz = Parameter(zeros((hidden,)), name="gru.bz")
        self.wr = Parameter(xavier_uniform(rng, din, hidden), name="gru.wr")
        self.ur = Parameter(orthogonal(rng, hidden, hidden), name="gru.ur")
        self.br = Parameter(zeros((hidden,)), name="gru.br")
        self.wh = Parameter(xavier_uniform(rng, din, hidden), name="gru.wh")
        self.uh = Parameter(orthogonal(rng, hidden, hidden), name="gru.uh")
        self.bh = Parameter(zeros((hidden,)), name="gru.bh")

    def forward(self, x: Tensor, h: Tensor) -> Tensor:
        z = (x @ self.wz + h @ self.uz + self.bz).sigmoid()
        r = (x @ self.wr + h @ self.ur + self.br).sigmoid()
        h_tilde = (x @ self.wh + (r * h) @ self.uh + self.bh).tanh()
        return (1.0 - z) * h + z * h_tilde


class GRU(Module):
    def __init__(self, din: int, hidden: int, rng: RNG) -> None:
        super().__init__()
        self.cell = GRUCell(din, hidden, rng)
        self.hidden = hidden

    def forward(self, xs: list[Tensor], h0: Tensor | None = None) -> tuple[list[Tensor], Tensor]:
        h = h0 if h0 is not None else Tensor(zeros_like_hidden(self.hidden), requires_grad=False)
        outs: list[Tensor] = []
        for x in xs:
            h = self.cell(x, h)
            outs.append(h)
        return outs, h


def zeros_like_hidden(hidden: int):

    return np.zeros((hidden,), dtype=np.float64)


# === nn/conv.py ===

"""1D convolution over character or token channels."""





class Conv1d(Module):
    def __init__(self, cin: int, cout: int, kernel: int, rng: RNG, stride: int = 1) -> None:
        super().__init__()
        self.cin = cin
        self.cout = cout
        self.kernel = kernel
        self.stride = stride
        w = he_uniform(rng, cin * kernel, cout).reshape(cout, cin, kernel)
        self.weight = Parameter(w, name="conv.w")
        self.bias = Parameter(zeros((cout,)), name="conv.b")

    def forward(self, x: Tensor) -> Tensor:
        """x: (C_in, L) -> (C_out, L_out)."""
        return conv1d(x, self.weight, self.bias, self.stride)


def conv1d(x: Tensor, weight: Tensor, bias: Tensor, stride: int) -> Tensor:
    cin, length = x.data.shape
    cout, cin_w, k = weight.data.shape
    if cin != cin_w:
        raise ValueError("conv channel mismatch")
    lout = 1 + (length - k) // stride
    col = np.zeros((cin * k, lout), dtype=np.float64)
    for t in range(lout):
        start = t * stride
        patch = x.data[:, start : start + k]
        col[:, t] = patch.reshape(-1)
    wflat = weight.data.reshape(cout, cin * k)
    out_data = wflat @ col + bias.data[:, None]
    requires = x.requires_grad or weight.requires_grad or bias.requires_grad
    out = Tensor(out_data, requires_grad=requires, children=(x, weight, bias) if requires else ())

    def _backward() -> None:
        if out.grad is None:
            return
        g = out.grad  # (cout, lout)
        if bias.requires_grad:
            bias.grad = ensure_grad(bias.grad, g.sum(axis=1), bias.data.shape)
        if weight.requires_grad:
            gw = g @ col.T
            weight.grad = ensure_grad(weight.grad, gw.reshape(cout, cin, k), weight.data.shape)
        if x.requires_grad:
            gx = np.zeros_like(x.data)
            gcol = wflat.T @ g
            for t in range(lout):
                start = t * stride
                gx[:, start : start + k] += gcol[:, t].reshape(cin, k)
            x.grad = ensure_grad(x.grad, gx, x.data.shape)

    if requires:
        out._backward = _backward
    return out


# === optim/clip.py ===





def clip_grad_norm(params: list[Parameter], max_norm: float) -> float:
    total = 0.0
    for p in params:
        if p.grad is None:
            continue
        total += float(np.sum(p.grad ** 2))
    norm = float(np.sqrt(total))
    if norm > max_norm and norm > 0:
        scale = max_norm / (norm + 1e-12)
        for p in params:
            if p.grad is not None:
                p.grad = p.grad * scale
    return norm


# === optim/sgd.py ===




class SGD:
    def __init__(self, params: list[Parameter], lr: float = 1e-2, momentum: float = 0.9, weight_decay: float = 0.0) -> None:
        self.params = params
        self.lr = lr
        self.momentum = momentum
        self.weight_decay = weight_decay
        self.v = [None] * len(params)

    def step(self) -> None:
        for i, p in enumerate(self.params):
            if p.grad is None:
                continue
            g = p.grad
            if self.weight_decay:
                g = g + self.weight_decay * p.data
            if self.v[i] is None:
                self.v[i] = g
            else:
                self.v[i] = self.momentum * self.v[i] + g
            p.data = p.data - self.lr * self.v[i]

    def zero_grad(self) -> None:
        for p in self.params:
            p.zero_grad()


# === optim/adam.py ===





class Adam:
    def __init__(
        self,
        params: list[Parameter],
        lr: float = 1e-3,
        betas: tuple[float, float] = (0.9, 0.999),
        eps: float = 1e-8,
        weight_decay: float = 0.0,
        decouple: bool = False,
    ) -> None:
        self.params = params
        self.lr = lr
        self.b1, self.b2 = betas
        self.eps = eps
        self.weight_decay = weight_decay
        self.decouple = decouple
        self.m = [np.zeros_like(p.data) for p in params]
        self.v = [np.zeros_like(p.data) for p in params]
        self.t = 0

    def step(self) -> None:
        self.t += 1
        b1t = 1.0 - self.b1 ** self.t
        b2t = 1.0 - self.b2 ** self.t
        for i, p in enumerate(self.params):
            if p.grad is None:
                continue
            g = p.grad
            if self.weight_decay and not self.decouple:
                g = g + self.weight_decay * p.data
            self.m[i] = self.b1 * self.m[i] + (1.0 - self.b1) * g
            self.v[i] = self.b2 * self.v[i] + (1.0 - self.b2) * (g * g)
            mhat = self.m[i] / b1t
            vhat = self.v[i] / b2t
            update = mhat / (np.sqrt(vhat) + self.eps)
            if self.decouple and self.weight_decay:
                p.data = p.data * (1.0 - self.lr * self.weight_decay) - self.lr * update
            else:
                p.data = p.data - self.lr * update

    def zero_grad(self) -> None:
        for p in self.params:
            p.zero_grad()


class AdamW(Adam):
    def __init__(self, params: list[Parameter], lr: float = 1e-3, weight_decay: float = 1e-2, **kwargs) -> None:
        super().__init__(params, lr=lr, weight_decay=weight_decay, decouple=True, **kwargs)


# === optim/schedules.py ===




class CosineWarmup:
    def __init__(self, base_lr: float, warmup: int = 50, total: int = 5000, min_lr: float = 1e-5) -> None:
        self.base_lr = base_lr
        self.warmup = warmup
        self.total = max(total, warmup + 1)
        self.min_lr = min_lr
        self.step_i = 0

    def next(self) -> float:
        self.step_i += 1
        t = self.step_i
        if t < self.warmup:
            return self.base_lr * t / max(self.warmup, 1)
        progress = (t - self.warmup) / (self.total - self.warmup)
        progress = min(max(progress, 0.0), 1.0)
        cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
        return self.min_lr + (self.base_lr - self.min_lr) * cosine


# === continual/ewc.py ===

"""Elastic Weight Consolidation (Kirkpatrick et al., 2017).

Protects parameters that the Fisher information says were important on
previous tasks. Combined with replay this is the cortex's long-term glue.
"""





class ElasticWeightConsolidation:
    def __init__(self, lam: float = 12.0, decay: float = 0.95) -> None:
        self.lam = lam
        self.decay = decay
        self.fisher: dict[str, np.ndarray] = {}
        self.anchor: dict[str, np.ndarray] = {}

    def observe_grads(self, module: Module) -> None:
        """Online diagonal Fisher: EMA of squared gradients after a backward."""
        for name, p in module.named_parameters():
            if p.grad is None:
                continue
            g2 = p.grad ** 2
            if name not in self.fisher:
                self.fisher[name] = g2.copy()
            else:
                self.fisher[name] = self.decay * self.fisher[name] + (1.0 - self.decay) * g2

    def snapshot(self, module: Module) -> None:
        self.anchor = {name: p.numpy() for name, p in module.named_parameters()}
        if not self.fisher:
            self.fisher = {name: np.zeros_like(p.data) for name, p in module.named_parameters()}

    def penalty(self, module: Module) -> Tensor:
        acc = Tensor(0.0, requires_grad=True)
        # Build a scalar by summing 0.5 * F * (w - w*)^2 through the graph.
        # Using numpy for the quadratic then attaching a custom backward is
        # cheaper and equivalent for a diagonal Fisher.
        return _ewc_penalty(module, self.fisher, self.anchor, self.lam) if self.anchor else acc


def _ewc_penalty(
    module: Module,
    fisher: dict[str, np.ndarray],
    anchor: dict[str, np.ndarray],
    lam: float,
) -> Tensor:
    params = list(module.named_parameters())
    total = 0.0
    pieces: list[tuple[Parameter, np.ndarray, np.ndarray]] = []
    for name, p in params:
        if name not in fisher or name not in anchor:
            continue
        f = fisher[name]
        a = anchor[name]
        delta = p.data - a
        total += 0.5 * float(np.sum(f * delta * delta))
        pieces.append((p, f, a))
    out = Tensor(np.array(lam * total), requires_grad=True, children=tuple(p for p, _, _ in pieces))

    def _backward() -> None:
        if out.grad is None:
            return
        scale = float(np.asarray(out.grad).reshape(-1)[0]) * lam
        for p, f, a in pieces:
            g = scale * f * (p.data - a)
            p.grad = g if p.grad is None else p.grad + g

    out._backward = _backward
    return out


# === continual/si.py ===

"""Synaptic Intelligence (Zenke, Poole, Ganguli 2017)."""





class SynapticIntelligence:
    def __init__(self, c: float = 0.4, xi: float = 1e-3) -> None:
        self.c = c
        self.xi = xi
        self.omega: dict[str, np.ndarray] = {}
        self.w_start: dict[str, np.ndarray] = {}
        self.path: dict[str, np.ndarray] = {}

    def begin_task(self, module: Module) -> None:
        self.w_start = {n: p.numpy() for n, p in module.named_parameters()}
        self.path = {n: np.zeros_like(p.data) for n, p in module.named_parameters()}

    def accumulate(self, module: Module, deltas: dict[str, np.ndarray]) -> None:
        """Call after an optimizer step with per-parameter Δw and using current grads."""
        for n, p in module.named_parameters():
            if p.grad is None or n not in deltas:
                continue
            if n not in self.path:
                self.path[n] = np.zeros_like(p.data)
            # ω-path integral ≈ -g · Δw
            self.path[n] = self.path[n] + (-p.grad) * deltas[n]

    def consolidate(self, module: Module) -> None:
        for n, p in module.named_parameters():
            if n not in self.w_start:
                continue
            dw = p.data - self.w_start[n]
            contrib = self.path.get(n, np.zeros_like(dw)) / (dw * dw + self.xi)
            if n not in self.omega:
                self.omega[n] = contrib
            else:
                self.omega[n] = self.omega[n] + contrib
        self.begin_task(module)

    def penalty(self, module: Module) -> Tensor:
        if not self.omega or not self.w_start:
            return Tensor(0.0, requires_grad=True)
        pieces: list[tuple[Parameter, np.ndarray, np.ndarray]] = []
        total = 0.0
        lookup_start = self.w_start
        for n, p in module.named_parameters():
            if n not in self.omega or n not in lookup_start:
                continue
            omega = self.omega[n]
            a = lookup_start[n]
            delta = p.data - a
            total += 0.5 * float(np.sum(omega * delta * delta))
            pieces.append((p, omega, a))
        out = Tensor(np.array(self.c * total), requires_grad=True, children=tuple(p for p, _, _ in pieces))

        def _backward() -> None:
            if out.grad is None:
                return
            scale = float(np.asarray(out.grad).reshape(-1)[0]) * self.c
            for p, omega, a in pieces:
                g = scale * omega * (p.data - a)
                p.grad = g if p.grad is None else p.grad + g

        out._backward = _backward
        return out


# === continual/lwf.py ===

"""Learning without Forgetting (Li & Hoiem): distill previous logits."""





class LearningWithoutForgetting:
    def __init__(self, alpha: float = 0.35, temperature: float = 2.0) -> None:
        self.alpha = alpha
        self.temperature = temperature
        self.teacher_logits: np.ndarray | None = None

    def remember(self, logits: np.ndarray) -> None:
        self.teacher_logits = np.array(logits, dtype=np.float64, copy=True)

    def penalty(self, student_logits: Tensor) -> Tensor:
        if self.teacher_logits is None:
            return Tensor(0.0, requires_grad=True)
        t = self.temperature
        teacher = _softmax(self.teacher_logits / t)
        log_q = (student_logits / t).log_softmax(axis=-1)
        return kl_div(log_q, teacher) * (self.alpha * t * t)


def _softmax(x: np.ndarray) -> np.ndarray:
    z = x - x.max()
    e = np.exp(z)
    return e / e.sum()


# === continual/agem.py ===

"""Averaged Gradient Episodic Memory (Chaudhry et al.).

Projects the current gradient so it does not increase loss on a memory batch.
"""





class AveragedGEM:
    def __init__(self) -> None:
        self.ref: dict[str, np.ndarray] = {}

    def store_reference_grads(self, module: Module) -> None:
        self.ref = {}
        for name, p in module.named_parameters():
            if p.grad is not None:
                self.ref[name] = p.grad.copy()

    def project(self, module: Module) -> float:
        """Modify current grads in-place. Returns the violation magnitude."""
        if not self.ref:
            return 0.0
        # Flatten g · g_ref
        dot = 0.0
        ref_norm = 0.0
        for name, p in module.named_parameters():
            if p.grad is None or name not in self.ref:
                continue
            r = self.ref[name]
            dot += float(np.sum(p.grad * r))
            ref_norm += float(np.sum(r * r))
        if dot >= 0 or ref_norm < 1e-12:
            return float(dot)
        coeff = dot / ref_norm
        for name, p in module.named_parameters():
            if p.grad is None or name not in self.ref:
                continue
            p.grad = p.grad - coeff * self.ref[name]
        return float(dot)


# === continual/replay.py ===

"""Prioritized experience replay (Schaul et al.) over encoded documents."""






@dataclass
class Episode:
    features: np.ndarray
    source: int
    text: str
    title: str
    url: str
    reward: float
    td_error: float
    step: int


class PrioritizedReplay:
    def __init__(self, capacity: int, rng: RNG, alpha: float = 0.6, beta: float = 0.4) -> None:
        self.capacity = capacity
        self.rng = rng
        self.alpha = alpha
        self.beta = beta
        self.items: list[Episode] = []
        self.priorities = np.zeros((capacity,), dtype=np.float64)
        self._cursor = 0

    def __len__(self) -> int:
        return len(self.items)

    def push(self, ep: Episode) -> None:
        pri = abs(ep.td_error) + 1e-3
        if len(self.items) < self.capacity:
            self.items.append(ep)
            self.priorities[len(self.items) - 1] = pri
        else:
            i = self._cursor % self.capacity
            self.items[i] = ep
            self.priorities[i] = pri
            self._cursor += 1

    def sample(self, k: int) -> tuple[list[Episode], np.ndarray, np.ndarray]:
        n = len(self.items)
        if n == 0:
            return [], np.array([]), np.array([])
        k = min(k, n)
        p = self.priorities[:n] ** self.alpha
        p = p / p.sum()
        idx = np.array([self.rng.choice(n, p=p) for _ in range(k)], dtype=np.int64)
        # unique-preserving: if collisions, fill remaining sequentially
        weights = (n * p[idx]) ** (-self.beta)
        weights = weights / (weights.max() + 1e-12)
        batch = [self.items[int(i)] for i in idx]
        return batch, idx, weights.astype(np.float64)

    def update_priority(self, index: int, td_error: float) -> None:
        if 0 <= index < len(self.items):
            self.priorities[index] = abs(td_error) + 1e-3
            self.items[index].td_error = td_error


# === rl/bandit.py ===

"""Contextual bandits that choose which public source to read next."""





class LinUCB:
    """Disjoint LinUCB (Li et al., WWW 2010). One linear model per arm."""

    def __init__(self, n_arms: int, dim: int, alpha: float = 0.6, lambda0: float = 1.0) -> None:
        self.n_arms = n_arms
        self.dim = dim
        self.alpha = alpha
        a0 = np.eye(dim) * lambda0
        self.A = np.stack([a0.copy() for _ in range(n_arms)])
        self.b = np.zeros((n_arms, dim), dtype=np.float64)
        self.counts = np.zeros(n_arms, dtype=np.int64)
        self.last_bonus = np.zeros(n_arms, dtype=np.float64)

    def _theta(self, arm: int) -> np.ndarray:
        return np.linalg.solve(self.A[arm], self.b[arm])

    def scores(self, context: np.ndarray) -> np.ndarray:
        x = context.reshape(-1)
        out = np.zeros(self.n_arms, dtype=np.float64)
        for a in range(self.n_arms):
            theta = self._theta(a)
            mean = float(theta @ x)
            ax = np.linalg.solve(self.A[a], x)
            bonus = self.alpha * float(np.sqrt(max(x @ ax, 0.0)))
            self.last_bonus[a] = bonus
            out[a] = mean + bonus
        return out

    def select(self, context: np.ndarray) -> int:
        return int(np.argmax(self.scores(context)))

    def update(self, arm: int, context: np.ndarray, reward: float) -> None:
        x = context.reshape(-1)
        self.A[arm] = self.A[arm] + np.outer(x, x)
        self.b[arm] = self.b[arm] + reward * x
        self.counts[arm] += 1

    def probabilities(self, context: np.ndarray) -> np.ndarray:
        s = self.scores(context)
        s = s - s.max()
        e = np.exp(s)
        return e / e.sum()


class ThompsonSampling:
    """Gaussian-linear Thompson sampling per arm."""

    def __init__(self, n_arms: int, dim: int, rng: RNG, v: float = 0.3) -> None:
        self.n_arms = n_arms
        self.dim = dim
        self.rng = rng
        self.v = v
        self.B = np.stack([np.eye(dim) for _ in range(n_arms)])
        self.mu = np.zeros((n_arms, dim), dtype=np.float64)
        self.f = np.zeros((n_arms, dim), dtype=np.float64)

    def select(self, context: np.ndarray) -> int:
        x = context.reshape(-1)
        best_a, best = 0, -1e18
        for a in range(self.n_arms):
            cov = (self.v ** 2) * np.linalg.inv(self.B[a])
            sample = self.rng.normal(size=self.dim) @ np.linalg.cholesky(cov + 1e-8 * np.eye(self.dim))
            sample = sample + self.mu[a]
            score = float(sample @ x)
            if score > best:
                best, best_a = score, a
        return best_a

    def update(self, arm: int, context: np.ndarray, reward: float) -> None:
        x = context.reshape(-1)
        self.B[arm] = self.B[arm] + np.outer(x, x)
        self.f[arm] = self.f[arm] + reward * x
        self.mu[arm] = np.linalg.solve(self.B[arm], self.f[arm])


# === rl/curiosity.py ===

"""Intrinsic Curiosity Module (Pathak et al.) + Random Network Distillation."""





class IntrinsicCuriosity:
    def __init__(self, dim: int, hidden: int, rng: RNG, lr: float = 1e-3) -> None:
        self.forward = _Forward(dim, hidden, rng)
        self.rnd_target = Linear(dim, hidden, rng.spawn(2), name="rnd.t")
        self.rnd_pred = Linear(dim, hidden, rng.spawn(3), name="rnd.p")
        self.opt = Adam(self.forward.parameters() + self.rnd_pred.parameters(), lr=lr)
        for p in self.rnd_target.parameters():
            p.requires_grad = False

    def bonus(self, prev: np.ndarray, nxt: np.ndarray) -> float:
        x = Tensor(prev, requires_grad=False)
        y = Tensor(nxt, requires_grad=False)
        pred = self.forward(x)
        fwd_err = mse(pred, y)
        rnd_t = self.rnd_target(y).detach()
        rnd_p = self.rnd_pred(y)
        rnd_err = mse(rnd_p, rnd_t)
        loss = fwd_err + rnd_err
        self.opt.zero_grad()
        loss.backward()
        clip_grad_norm(self.forward.parameters() + self.rnd_pred.parameters(), 1.0)
        self.opt.step()
        return float(fwd_err.item() + rnd_err.item())


class _Forward(Module):
    def __init__(self, dim: int, hidden: int, rng: RNG) -> None:
        super().__init__()
        self.l1 = Linear(dim, hidden, rng, name="icm.1")
        self.l2 = Linear(hidden, dim, rng, name="icm.2")

    def forward(self, x: Tensor) -> Tensor:
        return self.l2(self.l1(x).relu())


# === rl/gae.py ===

"""Generalized Advantage Estimation (Schulman et al.)."""




def gae(
    rewards: np.ndarray,
    values: np.ndarray,
    dones: np.ndarray,
    gamma: float = 0.99,
    lam: float = 0.95,
) -> tuple[np.ndarray, np.ndarray]:
    t = len(rewards)
    adv = np.zeros(t, dtype=np.float64)
    last = 0.0
    nxt_value = 0.0
    for i in range(t - 1, -1, -1):
        mask = 1.0 - float(dones[i])
        delta = rewards[i] + gamma * nxt_value * mask - values[i]
        last = delta + gamma * lam * mask * last
        adv[i] = last
        nxt_value = values[i]
    returns = adv + values
    return adv, returns


# === rl/traces.py ===

"""Eligibility traces for credit assignment across ticks."""





class EligibilityTraces:
    def __init__(self, decay: float = 0.9) -> None:
        self.decay = decay
        self.z: dict[str, np.ndarray] = {}

    def decay_all(self) -> None:
        for k in list(self.z.keys()):
            self.z[k] *= self.decay

    def accumulate(self, module: Module) -> None:
        for name, p in module.named_parameters():
            if p.grad is None:
                continue
            if name not in self.z:
                self.z[name] = np.zeros_like(p.data)
            self.z[name] += p.grad

    def apply(self, module: Module, td_error: float) -> None:
        for name, p in module.named_parameters():
            if name not in self.z:
                continue
            extra = td_error * self.z[name]
            p.grad = extra if p.grad is None else p.grad + extra


# === rl/ppo.py ===

"""Clipped PPO surrogate (Schulman et al.) for a categorical policy head."""





def ppo_surrogate(
    logp: Tensor,
    action: int,
    old_logp: float,
    advantage: float,
    clip: float = 0.2,
) -> Tensor:
    """logp is a 1D log-softmax vector. Returns the clipped objective (to maximize)."""
    new_logp = _select(logp, action)
    ratio = (new_logp - old_logp).exp()
    adv = float(advantage)
    unclipped = ratio * adv
    clipped_ratio = ratio.clip(1.0 - clip, 1.0 + clip)
    clipped = clipped_ratio * adv
    # min(unclipped, clipped) — for a scalar, compare numpy then pick via identity trick
    if float(unclipped.item()) < float(clipped.item()):
        return unclipped
    return clipped


def _select(logp: Tensor, action: int) -> Tensor:
    mask = np.zeros_like(logp.data)
    mask[int(action)] = 1.0
    return (logp * as_tensor(mask)).sum()


def entropy(logp: Tensor) -> Tensor:
    p = logp.exp()
    return -(p * logp).sum()


# === memory/episodic.py ===

"""Ring buffer of recent encoded documents with cosine recall."""





@dataclass
class Trace:
    vector: np.ndarray
    text: str
    title: str
    source: str
    url: str
    step: int


class EpisodicStore:
    def __init__(self, capacity: int, dim: int) -> None:
        self.capacity = capacity
        self.dim = dim
        self.matrix = np.zeros((capacity, dim), dtype=np.float64)
        self.traces: list[Trace] = []
        self._i = 0

    def __len__(self) -> int:
        return len(self.traces)

    def add(self, trace: Trace) -> None:
        v = _unit(trace.vector)
        trace.vector = v
        if len(self.traces) < self.capacity:
            self.traces.append(trace)
            self.matrix[len(self.traces) - 1] = v
        else:
            idx = self._i % self.capacity
            self.traces[idx] = trace
            self.matrix[idx] = v
            self._i += 1

    def recall(self, query: np.ndarray, k: int = 5) -> list[tuple[float, Trace]]:
        if not self.traces:
            return []
        n = len(self.traces)
        q = _unit(query)
        sims = self.matrix[:n] @ q
        k = min(k, n)
        idx = np.argpartition(-sims, kth=k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [(float(sims[i]), self.traces[int(i)]) for i in idx]

    def centroid(self) -> np.ndarray:
        if not self.traces:
            return np.zeros(self.dim, dtype=np.float64)
        return _unit(self.matrix[: len(self.traces)].mean(axis=0))


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    n = np.linalg.norm(v)
    return v if n < 1e-12 else v / n


# === memory/prototypes.py ===

"""Streaming k-means prototypes: compact semantic memory."""





class StreamingPrototypes:
    def __init__(self, k: int, dim: int, rng: RNG, lr: float = 0.08) -> None:
        self.k = k
        self.dim = dim
        self.lr = lr
        self.centers = rng.normal(scale=0.01, size=(k, dim))
        self.counts = np.ones(k, dtype=np.float64)
        self.labels: list[str] = [f"cluster-{i}" for i in range(k)]

    def assign(self, x: np.ndarray) -> int:
        d = np.linalg.norm(self.centers - x.reshape(1, -1), axis=1)
        return int(np.argmin(d))

    def update(self, x: np.ndarray) -> int:
        j = self.assign(x)
        self.counts[j] += 1
        eta = self.lr / np.sqrt(self.counts[j])
        self.centers[j] = (1.0 - eta) * self.centers[j] + eta * x.reshape(-1)
        return j

    def distances(self, x: np.ndarray) -> np.ndarray:
        return np.linalg.norm(self.centers - x.reshape(1, -1), axis=1)

    def entropy(self) -> float:
        p = self.counts / self.counts.sum()
        return float(-(p * np.log(p + 1e-12)).sum())


# === memory/hopfield.py ===

"""Modern Hopfield retrieval (Ramsauer et al.) over stored patterns."""




class ModernHopfield:
    def __init__(self, beta: float = 8.0, max_patterns: int = 256) -> None:
        self.beta = beta
        self.max_patterns = max_patterns
        self.patterns: np.ndarray | None = None

    def store(self, x: np.ndarray) -> None:
        x = x.reshape(1, -1)
        if self.patterns is None:
            self.patterns = x.copy()
            return
        self.patterns = np.vstack([self.patterns, x])
        if self.patterns.shape[0] > self.max_patterns:
            self.patterns = self.patterns[-self.max_patterns :]

    def retrieve(self, query: np.ndarray, steps: int = 3) -> np.ndarray:
        if self.patterns is None:
            return query.reshape(-1)
        xi = query.reshape(-1)
        mem = self.patterns
        for _ in range(steps):
            scores = self.beta * (mem @ xi)
            scores = scores - scores.max()
            w = np.exp(scores)
            w = w / w.sum()
            xi = w @ mem
        return xi

    def energy(self, query: np.ndarray) -> float:
        if self.patterns is None:
            return 0.0
        scores = self.beta * (self.patterns @ query.reshape(-1))
        lse = float(scores.max() + np.log(np.exp(scores - scores.max()).sum()))
        return float(-lse / self.beta)


# === memory/novelty.py ===

"""Novelty = reconstruction residual + distance from memory centroid."""




class NoveltyGate:
    def __init__(self, dim: int, ema: float = 0.97) -> None:
        self.ema = ema
        self.mean = np.zeros(dim, dtype=np.float64)
        self.m2 = np.ones(dim, dtype=np.float64)
        self.n = 0

    def score(self, x: np.ndarray) -> float:
        x = x.reshape(-1)
        if self.n < 2:
            return 1.0
        var = self.m2 / max(self.n - 1, 1)
        z = (x - self.mean) / np.sqrt(var + 1e-6)
        return float(np.tanh(np.linalg.norm(z) / np.sqrt(x.size)))

    def observe(self, x: np.ndarray) -> float:
        x = x.reshape(-1)
        s = self.score(x)
        self.n += 1
        delta = x - self.mean
        self.mean = self.mean + delta / self.n
        self.m2 = self.ema * self.m2 + (1.0 - self.ema) * (delta * (x - self.mean))
        return s


# === text/tokenize.py ===



_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?|[^\sA-Za-z0-9]")
_SENT = re.compile(r"(?<=[.!?])\s+")


def tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD.finditer(text or "")]


def sentences(text: str) -> list[str]:
    parts = _SENT.split((text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def ngrams(words: list[str], n: int) -> list[tuple[str, ...]]:
    if n <= 0:
        return []
    return [tuple(words[i : i + n]) for i in range(max(len(words) - n + 1, 0))]


# === text/hashing.py ===

"""Signed hashing trick (Weinberger et al.) — fixed-dim bag of n-grams."""






def _fnv(s: str) -> int:
    h = hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little", signed=False)


def hashing_trick(text: str, dim: int, ngram_min: int = 1, ngram_max: int = 3) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float64)
    words = tokens(text)
    if not words:
        return vec
    for n in range(ngram_min, ngram_max + 1):
        for gram in ngrams(words, n):
            key = " ".join(gram)
            h = _fnv(key)
            idx = h % dim
            sign = 1.0 if (h >> 63) & 1 == 0 else -1.0
            vec[idx] += sign
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


# === text/bpe.py ===

"""A tiny BPE trainer so a host app can freeze a vocab from seen text."""





class BytePairEncoder:
    def __init__(self, vocab_size: int = 512) -> None:
        self.vocab_size = vocab_size
        self.merges: list[tuple[str, str]] = []
        self.token_to_id: dict[str, int] = {}

    def fit(self, texts: list[str], rounds: int = 200) -> None:
        corpus: list[list[str]] = []
        for t in texts:
            words = tokens(t)
            for w in words:
                corpus.append(list(w) + ["</w>"])
        alphabet = sorted({ch for word in corpus for ch in word})
        self.token_to_id = {ch: i for i, ch in enumerate(alphabet)}
        for _ in range(rounds):
            if len(self.token_to_id) >= self.vocab_size:
                break
            pairs: Counter[tuple[str, str]] = Counter()
            for word in corpus:
                for i in range(len(word) - 1):
                    pairs[(word[i], word[i + 1])] += 1
            if not pairs:
                break
            best, _ = pairs.most_common(1)[0]
            self.merges.append(best)
            token = best[0] + best[1]
            self.token_to_id.setdefault(token, len(self.token_to_id))
            new_corpus = []
            for word in corpus:
                new_corpus.append(_merge_word(word, best))
            corpus = new_corpus

    def encode(self, text: str) -> list[int]:
        ids: list[int] = []
        for w in tokens(text):
            symbols = list(w) + ["</w>"]
            for pair in self.merges:
                symbols = _merge_word(symbols, pair)
            for s in symbols:
                ids.append(self.token_to_id.get(s, 0))
        return ids


def _merge_word(word: list[str], pair: tuple[str, str]) -> list[str]:
    out: list[str] = []
    i = 0
    a, b = pair
    while i < len(word):
        if i < len(word) - 1 and word[i] == a and word[i + 1] == b:
            out.append(a + b)
            i += 2
        else:
            out.append(word[i])
            i += 1
    return out


# === text/encoder.py ===





class HashEncoder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def encode(self, text: str) -> np.ndarray:
        return hashing_trick(text, self.dim)

    def batch(self, texts: list[str]) -> np.ndarray:
        return np.stack([self.encode(t) for t in texts], axis=0)


# === stats/welford.py ===




class Welford:
    """Streaming mean / variance."""

    def __init__(self, dim: int) -> None:
        self.n = 0
        self.mean = np.zeros(dim, dtype=np.float64)
        self.m2 = np.zeros(dim, dtype=np.float64)

    def update(self, x: np.ndarray) -> None:
        x = x.reshape(-1)
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)

    @property
    def variance(self) -> np.ndarray:
        if self.n < 2:
            return np.ones_like(self.mean)
        return self.m2 / (self.n - 1)


# === stats/pca.py ===

"""Candid Covariance-Free Incremental PCA (Weng et al.)."""





class CCIPCA:
    def __init__(self, dim: int, k: int, rng: RNG) -> None:
        self.dim = dim
        self.k = k
        self.components = rng.normal(scale=0.01, size=(k, dim))
        self.counts = np.zeros(k, dtype=np.float64)

    def update(self, x: np.ndarray) -> np.ndarray:
        v = x.reshape(-1).astype(np.float64).copy()
        codes = np.zeros(self.k, dtype=np.float64)
        for i in range(self.k):
            self.counts[i] += 1
            n = self.counts[i]
            u = self.components[i]
            eta = 1.0 / n
            u = (1.0 - eta) * u + eta * float(v @ u) * v
            norm = np.linalg.norm(u)
            if norm > 0:
                u = u / norm
            self.components[i] = u
            proj = float(v @ u)
            codes[i] = proj
            v = v - proj * u
        return codes

    def transform(self, x: np.ndarray) -> np.ndarray:
        return self.components @ x.reshape(-1)


# === stats/hebbian.py ===

"""Local synaptic rules: Oja and BCM."""




class Oja:
    def __init__(self, dim: int, lr: float = 1e-3) -> None:
        self.w = np.zeros(dim, dtype=np.float64)
        self.lr = lr

    def step(self, x: np.ndarray) -> float:
        x = x.reshape(-1)
        y = float(self.w @ x)
        self.w = self.w + self.lr * y * (x - y * self.w)
        return y


def bcm(w: np.ndarray, x: np.ndarray, theta: float, lr: float) -> tuple[np.ndarray, float, float]:
    """Return (w_new, y, theta_new). theta tracks E[y^2]."""
    x = x.reshape(-1)
    y = float(w @ x)
    w_new = w + lr * y * (y - theta) * x
    theta_new = 0.99 * theta + 0.01 * (y * y)
    return w_new, y, theta_new


# === stats/reservoir.py ===

"""Echo-state reservoir — a fixed recurrent net with a trained readout."""





class EchoState:
    def __init__(self, din: int, reservoir: int, rng: RNG, spectral: float = 0.9, leak: float = 0.3) -> None:
        self.win = rng.uniform(-0.5, 0.5, size=(reservoir, din))
        w = rng.normal(scale=1.0, size=(reservoir, reservoir))
        eigs = np.linalg.eigvals(w)
        rho = max(np.abs(eigs).max(), 1e-6)
        self.w = (w / rho) * spectral
        self.leak = leak
        self.h = np.zeros(reservoir, dtype=np.float64)
        self.readout = np.zeros(din, dtype=np.float64)
        self.p_inv = np.eye(reservoir) * 0.1  # RLS P matrix
        self.w_out = np.zeros((din, reservoir), dtype=np.float64)

    def step(self, x: np.ndarray, target: np.ndarray | None = None) -> np.ndarray:
        x = x.reshape(-1)
        pre = np.tanh(self.win @ x + self.w @ self.h)
        self.h = (1.0 - self.leak) * self.h + self.leak * pre
        y = self.w_out @ self.h
        if target is not None:
            err = target.reshape(-1) - y
            ph = self.p_inv @ self.h
            denom = 1.0 + float(self.h @ ph)
            self.p_inv = self.p_inv - np.outer(ph, ph) / denom
            self.w_out = self.w_out + np.outer(err, ph / denom)
            y = self.w_out @ self.h
        return y


# === online/documents.py ===




@dataclass
class Document:
    source: str
    title: str
    text: str
    url: str
    extra: dict[str, str]

    def clipped(self, n: int) -> "Document":
        if len(self.text) <= n:
            return self
        return Document(self.source, self.title, self.text[:n], self.url, self.extra)


# === online/rate_limit.py ===

"""Per-host pacing. Identified, polite, no evasion."""




class HostPacer:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._last: dict[str, float] = defaultdict(float)

    def wait(self, url: str) -> None:
        host = urlparse(url).netloc
        now = time.monotonic()
        due = self._last[host] + self.seconds
        if now < due:
            time.sleep(due - now)
        self._last[host] = time.monotonic()


# === online/http.py ===

"""Identified HTTP client for public APIs. Uses stdlib urllib only."""





class HttpClient:
    def __init__(self, cfg: CortexConfig) -> None:
        self.cfg = cfg
        self.pacer = HostPacer(cfg.rate_limit_seconds)
        self.ctx = ssl.create_default_context()

    def get_text(self, url: str, accept: str = "*/*") -> str:
        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            self.pacer.wait(url)
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.cfg.user_agent,
                    "Accept": accept,
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.cfg.timeout_seconds, context=self.ctx) as resp:
                    status = getattr(resp, "status", 200)
                    if status == 429:
                        raise RateLimitError(url)
                    raw = resp.read()
                    charset = resp.headers.get_content_charset() or "utf-8"
                    return raw.decode(charset, errors="replace")
            except urllib.error.HTTPError as exc:
                last_err = exc
                if exc.code == 429:
                    raise RateLimitError(url) from exc
                if exc.code >= 500:
                    continue
                raise OnlineError(f"{exc.code} for {url}") from exc
            except urllib.error.URLError as exc:
                last_err = exc
                continue
        raise OnlineError(f"failed {url}: {last_err}") from last_err

    def get_json(self, url: str) -> Any:
        text = self.get_text(url, accept="application/json")
        return json.loads(text)


# === online/wikipedia.py ===





class WikipediaReader:
    def __init__(self, cfg: CortexConfig, http: HttpClient) -> None:
        self.cfg = cfg
        self.http = http

    def random(self) -> Document:
        payload = self.http.get_json(self.cfg.wikipedia_random)
        return self._from_summary(payload)

    def summary(self, title: str) -> Document:
        url = self.cfg.wikipedia_summary + quote(title)
        payload = self.http.get_json(url)
        return self._from_summary(payload)

    def _from_summary(self, payload: dict) -> Document:
        title = str(payload.get("title") or "untitled")
        extract = str(payload.get("extract") or payload.get("description") or "")
        url = str((payload.get("content_urls") or {}).get("desktop", {}).get("page") or payload.get("canonicalurl") or "")
        return Document("wikipedia", title, extract, url, {"lang": self.cfg.wikipedia_language})


# === online/arxiv.py ===




ATOM = "{http://www.w3.org/2005/Atom}"


class ArxivReader:
    def __init__(self, cfg: CortexConfig, http: HttpClient) -> None:
        self.cfg = cfg
        self.http = http

    def search(self, start: int = 0, max_results: int = 5) -> list[Document]:
        qs = urlencode(
            {
                "search_query": self.cfg.arxiv_query,
                "start": start,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        xml = self.http.get_text(f"{self.cfg.arxiv_api}?{qs}", accept="application/atom+xml")
        root = ET.fromstring(xml)
        docs: list[Document] = []
        for entry in root.findall(f"{ATOM}entry"):
            title = (entry.findtext(f"{ATOM}title") or "").strip().replace("\n", " ")
            summary = (entry.findtext(f"{ATOM}summary") or "").strip()
            url = (entry.findtext(f"{ATOM}id") or "").strip()
            docs.append(Document("arxiv", title, summary, url, {"query": self.cfg.arxiv_query}))
        return docs


# === online/hackernews.py ===




class HackerNewsReader:
    def __init__(self, cfg: CortexConfig, http: HttpClient) -> None:
        self.cfg = cfg
        self.http = http

    def top(self, n: int = 8) -> list[Document]:
        ids = self.http.get_json(self.cfg.hn_endpoint)
        if not isinstance(ids, list):
            return []
        docs: list[Document] = []
        for item_id in ids[:n]:
            item = self.http.get_json(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            text = str(item.get("text") or item.get("title") or "")
            url = str(item.get("url") or f"https://news.ycombinator.com/item?id={item_id}")
            docs.append(Document("hackernews", title, text, url, {"id": str(item_id)}))
        return docs


# === online/rss.py ===





class RssReader:
    def __init__(self, cfg: CortexConfig, http: HttpClient) -> None:
        self.cfg = cfg
        self.http = http
        self._i = 0

    def next_feed(self) -> list[Document]:
        if not self.cfg.rss_feeds:
            return []
        url = self.cfg.rss_feeds[self._i % len(self.cfg.rss_feeds)]
        self._i += 1
        xml = self.http.get_text(url, accept="application/rss+xml, application/atom+xml, application/xml, text/xml")
        return parse_feed(xml, url)


def parse_feed(xml: str, feed_url: str) -> list[Document]:
    root = ET.fromstring(xml)
    docs: list[Document] = []
    # RSS 2.0
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or item.findtext("title") or "").strip()
        link = (item.findtext("link") or feed_url).strip()
        docs.append(Document("rss", title, _strip_tags(desc), link, {"feed": feed_url}))
    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f"{ns}entry"):
        title = (entry.findtext(f"{ns}title") or "").strip()
        summary = (entry.findtext(f"{ns}summary") or entry.findtext(f"{ns}content") or title).strip()
        link_el = entry.find(f"{ns}link")
        href = link_el.get("href") if link_el is not None else feed_url
        docs.append(Document("rss", title, _strip_tags(summary), href or feed_url, {"feed": feed_url}))
    return docs


def _strip_tags(html: str) -> str:
    out = []
    skip = 0
    for ch in html:
        if ch == "<":
            skip += 1
            continue
        if ch == ">" and skip:
            skip -= 1
            continue
        if skip == 0:
            out.append(ch)
    return "".join(out).strip()


# === online/router.py ===

"""Pick a public source and return one document. Offline fallback if fetches fail."""



OFFLINE_CORPUS = [
    Document(
        "offline",
        "Catastrophic forgetting",
        "Neural networks trained sequentially on tasks tend to overwrite earlier weights. "
        "Elastic weight consolidation, replay, and synaptic intelligence slow that overwrite "
        "by protecting parameters that mattered on previous tasks.",
        "offline:ewc",
        {},
    ),
    Document(
        "offline",
        "Experience replay",
        "Reinforcement learning agents store transitions and sample them later so rare events "
        "keep teaching the policy. Prioritized replay samples by temporal-difference error.",
        "offline:replay",
        {},
    ),
    Document(
        "offline",
        "Contextual bandits",
        "LinUCB chooses arms by combining a linear reward estimate with an uncertainty bonus. "
        "The cortex uses it to decide which public API to read next.",
        "offline:bandit",
        {},
    ),
    Document(
        "offline",
        "Public APIs",
        "Wikipedia REST summaries, arXiv Atom, Hacker News Firebase, and RSS feeds are designed "
        "for machine reading. Clients should send a real User-Agent and pace requests per host.",
        "offline:apis",
        {},
    ),
]


class SourceRouter:
    def __init__(self, cfg: CortexConfig, rng: RNG) -> None:
        self.cfg = cfg
        self.rng = rng
        self.http = HttpClient(cfg)
        self.wiki = WikipediaReader(cfg, self.http)
        self.arxiv = ArxivReader(cfg, self.http)
        self.hn = HackerNewsReader(cfg, self.http)
        self.rss = RssReader(cfg, self.http)
        self._arxiv_pool: list[Document] = []
        self._hn_pool: list[Document] = []
        self._rss_pool: list[Document] = []
        self._offline_i = 0

    def fetch(self, source: str) -> Document:
        if not self.cfg.online:
            return self._offline()
        try:
            doc = self._fetch_live(source)
        except (OnlineError, Exception):
            doc = self._offline()
        return doc.clipped(self.cfg.max_document_chars)

    def _fetch_live(self, source: str) -> Document:
        if source == "wikipedia":
            return self.wiki.random()
        if source == "arxiv":
            if not self._arxiv_pool:
                self._arxiv_pool = self.arxiv.search(max_results=8)
            if not self._arxiv_pool:
                return self._offline()
            return self._arxiv_pool.pop(0)
        if source == "hackernews":
            if not self._hn_pool:
                self._hn_pool = self.hn.top(n=6)
            if not self._hn_pool:
                return self._offline()
            return self._hn_pool.pop(0)
        if source == "rss":
            if not self._rss_pool:
                self._rss_pool = self.rss.next_feed()
            if not self._rss_pool:
                return self._offline()
            return self._rss_pool.pop(0)
        return self._offline()

    def _offline(self) -> Document:
        doc = OFFLINE_CORPUS[self._offline_i % len(OFFLINE_CORPUS)]
        self._offline_i += 1
        return doc


# === models/learner.py ===

"""Shared encoder with reconstruction, source, value, and policy heads."""




class ContinualLearner(Module):
    def __init__(self, dim: int, hidden: int, latent: int, n_sources: int, rng: RNG, dropout_p: float) -> None:
        super().__init__()
        self.norm = LayerNorm(dim)
        self.encoder = ResidualMLP(dim, hidden, rng, dropout_p=dropout_p, out_dim=latent)
        self.recon = Linear(latent, dim, rng, name="recon")
        self.source = Linear(latent, n_sources, rng, name="source")
        self.value = Linear(latent, 1, rng, name="value")
        self.policy = Linear(latent, n_sources, rng, name="policy")

    def encode(self, x: Tensor) -> Tensor:
        return self.encoder(self.norm(x))

    def forward(self, x: Tensor) -> dict[str, Tensor]:
        z = self.encode(x)
        return {
            "latent": z,
            "recon": self.recon(z),
            "source": self.source(z),
            "value": self.value(z),
            "policy": self.policy(z),
        }


# === agent/types.py ===




@dataclass
class StepResult:
    step: int
    source: str
    title: str
    url: str
    text_preview: str
    loss: float
    recon: float
    class_nll: float
    ewc: float
    reward: float
    novelty: float
    curiosity: float
    source_correct: bool
    cluster: int
    policy: list[float] = field(default_factory=list)
    bandit: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "step": self.step,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "text_preview": self.text_preview,
            "loss": self.loss,
            "recon": self.recon,
            "class_nll": self.class_nll,
            "ewc": self.ewc,
            "reward": self.reward,
            "novelty": self.novelty,
            "curiosity": self.curiosity,
            "source_correct": self.source_correct,
            "cluster": self.cluster,
            "policy": self.policy,
            "bandit": self.bandit,
        }


# === agent/reward.py ===





def compose_reward(
    cfg: CortexConfig,
    novelty: float,
    recon_err: float,
    correct: bool,
    cluster_entropy: float,
    curiosity: float,
) -> float:
    # Reconstruction error is useful as curiosity but saturates; squash it.
    info_gain = float(np.tanh(recon_err))
    coherence = 1.0 if correct else 0.0
    diversity = float(np.tanh(cluster_entropy / 3.0))
    r = (
        cfg.novelty_mix * novelty
        + cfg.coherence_mix * (0.5 * coherence + 0.5 * (1.0 - info_gain))
        + cfg.diversity_mix * diversity
        + cfg.curiosity_scale * float(np.tanh(curiosity))
    )
    return float(np.clip(r, -1.0, 2.0))


# === agent/serialize.py ===






def dump_blob(path: str | Path, arrays: dict[str, np.ndarray], meta: dict) -> None:
    path = Path(path)
    try:
        payload = {k: np.asarray(v) for k, v in arrays.items()}
        raw = json.dumps(meta).encode("utf-8")
        payload["__meta__"] = np.frombuffer(raw, dtype=np.uint8)
        np.savez_compressed(path, **payload)
    except Exception as exc:
        raise SerializationError(str(exc)) from exc


def load_blob(path: str | Path) -> tuple[dict[str, np.ndarray], dict]:
    path = Path(path)
    try:
        with np.load(path, allow_pickle=False) as z:
            arrays = {k: z[k] for k in z.files if k != "__meta__"}
            meta_raw = z["__meta__"].tobytes() if "__meta__" in z.files else b"{}"
            meta = json.loads(meta_raw.decode("utf-8"))
        return arrays, meta
    except Exception as exc:
        raise SerializationError(str(exc)) from exc


# === agent/cortex.py ===

"""Embeddable cortex: read public data, learn, relearn, reinforce.

A host app constructs one `Cortex` and calls `step()` on its own schedule.
Nothing here runs a server. Network use is optional and identified.
"""






class Cortex:
    """Host-app handle. Drop into another process and call `step` / `learn_text`."""

    def __init__(self, cfg: CortexConfig | None = None) -> None:
        self.cfg = cfg or CortexConfig()
        self.rng = RNG(self.cfg.seed)
        self.encoder = HashEncoder(self.cfg.feature_dim)
        self.net = ContinualLearner(
            self.cfg.feature_dim,
            self.cfg.hidden_dim,
            self.cfg.latent_dim,
            len(self.cfg.sources),
            self.rng,
            self.cfg.dropout,
        )
        self.opt = AdamW(self.net.parameters(), lr=self.cfg.learn_rate, weight_decay=self.cfg.weight_decay)
        self.ewc = ElasticWeightConsolidation(self.cfg.ewc_lambda, self.cfg.fisher_decay)
        self.si = SynapticIntelligence(self.cfg.si_c)
        self.lwf = LearningWithoutForgetting(self.cfg.lwf_alpha)
        self.agem = AveragedGEM()
        self.replay = PrioritizedReplay(self.cfg.replay_capacity, self.rng)
        self.episodic = EpisodicStore(self.cfg.replay_capacity, self.cfg.feature_dim)
        self.prototypes = StreamingPrototypes(self.cfg.prototype_k, self.cfg.feature_dim, self.rng)
        self.hopfield = ModernHopfield(self.cfg.hopfield_beta)
        self.novelty = NoveltyGate(self.cfg.feature_dim)
        self.bandit = LinUCB(len(self.cfg.sources), self.cfg.pca_dim + 8, alpha=self.cfg.ucb_alpha)
        self.curiosity = IntrinsicCuriosity(self.cfg.feature_dim, self.cfg.hidden_dim, self.rng.spawn(9))
        self.traces = EligibilityTraces(0.88)
        self.oja = Oja(self.cfg.feature_dim, self.cfg.hebbian_lr)
        self.pca = CCIPCA(self.cfg.feature_dim, self.cfg.pca_dim, self.rng.spawn(4))
        self.reservoir = EchoState(self.cfg.feature_dim, self.cfg.reservoir_size, self.rng.spawn(5))
        self.router = SourceRouter(self.cfg, self.rng)
        self.si.begin_task(self.net)
        self.ewc.snapshot(self.net)
        self.step_i = 0
        self.prev_features: np.ndarray | None = None
        self.last_context: np.ndarray | None = None
        self.last_arm = 0
        self.last_logp = 0.0
        self.history: list[dict] = []
        self._prev_weights = {n: p.numpy() for n, p in self.net.named_parameters()}

    # ------------------------------------------------------------------ public
    def step(self) -> StepResult:
        """One full cycle: choose a public source, read, learn, reinforce."""
        context = self._context()
        arm = self.bandit.select(context)
        source = self.cfg.sources[arm]
        doc = self.router.fetch(source)
        return self._assimilate(doc, context, arm)

    def learn_text(self, text: str, source: str = "offline", title: str = "host", url: str = "") -> StepResult:
        """Offline path a host app uses when it already has text."""
        if source not in self.cfg.sources:
            source = "wikipedia"
        arm = self.cfg.source_index(source)
        doc = Document(source, title, text, url, {"origin": "host"})
        return self._assimilate(doc, self._context(), arm)

    def relearn(self, steps: int | None = None) -> list[float]:
        """Sleep / consolidation: replay old episodes, lock Fisher, SI omega."""
        n = steps if steps is not None else self.cfg.sleep_steps
        losses: list[float] = []
        self.net.train(True)
        for _ in range(n):
            batch, idx, weights = self.replay.sample(self.cfg.replay_batch)
            if not batch:
                break
            loss_acc = 0.0
            self.net.zero_grad()
            # A-GEM reference from a memory minibatch
            ref_loss = Tensor(0.0, requires_grad=True)
            for ep, w in zip(batch, weights):
                out = self.net(Tensor(ep.features, requires_grad=False))
                piece = mse(out["recon"], ep.features) + cross_entropy(out["source"], ep.source)
                ref_loss = ref_loss + piece * float(w)
            ref_loss.backward()
            self.agem.store_reference_grads(self.net)
            self.net.zero_grad()
            live = Tensor(0.0, requires_grad=True)
            for ep, w in zip(batch, weights):
                out = self.net(Tensor(ep.features, requires_grad=False))
                piece = mse(out["recon"], ep.features) + cross_entropy(out["source"], ep.source)
                live = live + piece * float(w)
            live = live + self.ewc.penalty(self.net) + self.si.penalty(self.net)
            live.backward()
            self.agem.project(self.net)
            clip_grad_norm(self.net.parameters(), self.cfg.grad_clip)
            self._opt_step()
            losses.append(float(live.item()) if live.data.size == 1 else float(np.asarray(live.data).reshape(-1)[0]))
            for i, ep in zip(idx, batch):
                self.replay.update_priority(int(i), abs(losses[-1]))
        self.ewc.snapshot(self.net)
        self.si.consolidate(self.net)
        return losses

    def reinforce(self) -> float:
        """Extra local plasticity on the last encoded episode."""
        if self.prev_features is None:
            return 0.0
        x = self.prev_features
        hebb = self.oja.step(x)
        self.reservoir.step(x, target=x)
        self.net.zero_grad()
        out = self.net(Tensor(x, requires_grad=False))
        loss = mse(out["recon"], x)
        loss.backward()
        self.traces.decay_all()
        self.traces.accumulate(self.net)
        self.traces.apply(self.net, td_error=hebb)
        clip_grad_norm(self.net.parameters(), self.cfg.grad_clip)
        self._opt_step()
        return float(loss.item())

    def embed(self, text: str) -> np.ndarray:
        was = self.net.training
        self.net.eval()
        try:
            feats = self.encoder.encode(text)
            z = self.net.encode(Tensor(feats, requires_grad=False))
            return z.numpy()
        finally:
            self.net.train(was)

    def recall(self, text: str, k: int = 5) -> list[dict]:
        q = self.encoder.encode(text)
        hits = self.episodic.recall(q, k=k)
        return [
            {
                "score": score,
                "title": tr.title,
                "source": tr.source,
                "url": tr.url,
                "text": tr.text[:400],
            }
            for score, tr in hits
        ]

    def save(self, path: str) -> None:
        arrays = {f"net.{k}": v for k, v in self.net.state_dict().items()}
        arrays["prototypes"] = self.prototypes.centers
        arrays["pca"] = self.pca.components
        arrays["oja"] = self.oja.w
        meta = {
            "step": self.step_i,
            "cfg": asdict(self.cfg),
            "sources": list(self.cfg.sources),
        }
        dump_blob(path, arrays, meta)

    @classmethod
    def load(cls, path: str, cfg: CortexConfig | None = None) -> "Cortex":
        arrays, meta = load_blob(path)
        cortex = cls(cfg or CortexConfig())
        net_state = {k[4:]: v for k, v in arrays.items() if k.startswith("net.")}
        cortex.net.load_state_dict(net_state)
        if "prototypes" in arrays:
            cortex.prototypes.centers = arrays["prototypes"]
        if "pca" in arrays:
            cortex.pca.components = arrays["pca"]
        if "oja" in arrays:
            cortex.oja.w = arrays["oja"]
        cortex.step_i = int(meta.get("step", 0))
        return cortex

    # ----------------------------------------------------------------- intern
    def _assimilate(self, doc: Document, context: np.ndarray, arm: int) -> StepResult:
        self.step_i += 1
        feats = self.encoder.encode(f"{doc.title}\n{doc.text}")
        source_i = self.cfg.source_index(doc.source) if doc.source in self.cfg.sources else arm
        x = Tensor(feats, requires_grad=False)
        self.net.train(True)
        self.net.zero_grad()
        out = self.net(x)
        recon_l = mse(out["recon"], feats)
        nll = cross_entropy(out["source"], source_i)
        ewc_l = self.ewc.penalty(self.net)
        si_l = self.si.penalty(self.net)
        lwf_l = self.lwf.penalty(out["source"])
        logp = out["policy"].log_softmax(axis=-1)
        adv = 0.0
        ppo_l = ppo_surrogate(logp, arm, self.last_logp, adv, clip=0.2) * 0.0
        # entropy bonus (maximize entropy => minimize negative entropy)
        ent = entropy(logp)
        loss = recon_l + nll + ewc_l + si_l + lwf_l - 0.01 * ent + ppo_l
        # A-GEM vs replay
        if len(self.replay) >= 4:
            self.net.zero_grad()
            mem, _, wts = self.replay.sample(min(4, len(self.replay)))
            ref = Tensor(0.0, requires_grad=True)
            for ep, w in zip(mem, wts):
                o = self.net(Tensor(ep.features, requires_grad=False))
                ref = ref + (mse(o["recon"], ep.features) + cross_entropy(o["source"], ep.source)) * float(w)
            ref.backward()
            self.agem.store_reference_grads(self.net)
            self.net.zero_grad()
        loss.backward()
        if len(self.replay) >= 4:
            self.agem.project(self.net)
        self.ewc.observe_grads(self.net)
        clip_grad_norm(self.net.parameters(), self.cfg.grad_clip)
        self._opt_step()
        pred = int(np.argmax(out["source"].data))
        correct = pred == source_i
        recon_err = float(recon_l.item())
        curiosity = 0.0
        if self.prev_features is not None:
            curiosity = self.curiosity.bonus(self.prev_features, feats)
        nov = self.novelty.observe(feats)
        cluster = self.prototypes.update(feats)
        self.hopfield.store(feats)
        self.pca.update(feats)
        self.oja.step(feats)
        self.reservoir.step(feats, target=feats)
        reward = compose_reward(self.cfg, nov, recon_err, correct, self.prototypes.entropy(), curiosity)
        self.bandit.update(arm, context, reward)
        self.last_logp = float(logp.data[arm])
        self.last_arm = arm
        self.last_context = context
        self.prev_features = feats
        td = abs(reward - float(out["value"].data.reshape(-1)[0]))
        self.replay.push(
            Episode(
                features=feats,
                source=source_i,
                text=doc.text,
                title=doc.title,
                url=doc.url,
                reward=reward,
                td_error=td,
                step=self.step_i,
            )
        )
        self.episodic.add(Trace(feats, doc.text, doc.title, doc.source, doc.url, self.step_i))
        self.lwf.remember(out["source"].data)
        if self.step_i % 16 == 0:
            self.ewc.snapshot(self.net)
        preview = doc.text[:240].replace("\n", " ")
        result = StepResult(
            step=self.step_i,
            source=doc.source,
            title=doc.title,
            url=doc.url,
            text_preview=preview,
            loss=float(loss.item()),
            recon=recon_err,
            class_nll=float(nll.item()),
            ewc=float(ewc_l.item()) if ewc_l.data.size else 0.0,
            reward=reward,
            novelty=nov,
            curiosity=curiosity,
            source_correct=correct,
            cluster=cluster,
            policy=logp.exp().numpy().reshape(-1).tolist(),
            bandit=self.bandit.probabilities(context).tolist(),
        )
        self.history.append(result.as_dict())
        self.history = self.history[-self.cfg.history :]
        return result

    def _context(self) -> np.ndarray:
        pca_mean = self.pca.components.mean(axis=0)
        # 8 extra stats + pca_dim projection of centroid
        centroid = self.episodic.centroid()
        code = self.pca.transform(centroid) if np.linalg.norm(centroid) > 0 else np.zeros(self.cfg.pca_dim)
        extra = np.array(
            [
                self.prototypes.entropy(),
                len(self.replay) / max(self.cfg.replay_capacity, 1),
                float(self.step_i % 50) / 50.0,
                float(self.last_arm) / max(len(self.cfg.sources), 1),
                float(self.oja.w @ self.oja.w),
                float(np.linalg.norm(pca_mean)),
                float(self.novelty.n > 0),
                float(self.hopfield.energy(centroid) if self.hopfield.patterns is not None else 0.0),
            ],
            dtype=np.float64,
        )
        ctx = np.concatenate([code.reshape(-1), extra])
        # LinUCB dim is pca_dim+8
        if ctx.size != self.cfg.pca_dim + 8:
            ctx = np.resize(ctx, self.cfg.pca_dim + 8)
        n = np.linalg.norm(ctx)
        return ctx / n if n > 0 else ctx

    def _opt_step(self) -> None:
        before = {n: p.numpy() for n, p in self.net.named_parameters()}
        self.opt.step()
        deltas = {}
        for n, p in self.net.named_parameters():
            deltas[n] = p.data - before[n]
        self.si.accumulate(self.net, deltas)
        self._prev_weights = {n: p.numpy() for n, p in self.net.named_parameters()}

    def snapshot_parameters(self) -> dict[str, np.ndarray]:
        return {n: p.numpy() for n, p in self.net.named_parameters()}


__all__ = [
    "Cortex",
    "CortexConfig",
    "Document",
    "StepResult",
    "Tensor",
    "mse",
    "cross_entropy",
    "HashEncoder",
    "BytePairEncoder",
    "tokens",
    "sentences",
    "Episode",
    "PrioritizedReplay",
    "ContinualLearner",
    "RNG",
    "LinUCB",
    "ElasticWeightConsolidation",
]
__version__ = "0.1.0"


def _selftest() -> None:
    """Built-in checks so this file can stand alone."""
    import tempfile

    a = Tensor([1.0, 2.0, 3.0], requires_grad=True)
    b = Tensor([4.0, 5.0, 6.0], requires_grad=True)
    (a + b).sum().backward()
    assert a.grad is not None
    np.testing.assert_allclose(a.grad, np.ones(3))

    w = Tensor([[0.2, -0.4], [0.1, 0.3], [-0.5, 0.7]], requires_grad=True)
    x = Tensor([1.0, 2.0, 3.0], requires_grad=True)
    (x @ w).relu().sum().backward()
    assert x.grad is not None and w.grad is not None

    pred = Tensor([0.1, 0.2, 0.3], requires_grad=True)
    mse(pred, np.array([0.0, 0.0, 1.0])).backward()
    expected = (2.0 / 3.0) * (pred.data - np.array([0.0, 0.0, 1.0]))
    np.testing.assert_allclose(pred.grad, expected, atol=1e-8)

    logits = Tensor([0.0, 0.0, 0.0, 0.0], requires_grad=True)
    cross_entropy(logits, 2).backward()
    assert logits.grad is not None and logits.grad[2] < 0

    enc = HashEncoder(64)
    vec = enc.encode("elastic weight consolidation replay")
    assert vec.shape == (64,)
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-6
    assert len(sentences("Hello world. Second sentence!")) == 2
    assert "hello" in tokens("Hello world.")
    bpe = BytePairEncoder(vocab_size=80)
    bpe.fit(["replay buffer", "elastic weights"], rounds=20)
    assert bpe.encode("replay")

    rng = RNG(0)
    net = ContinualLearner(8, 8, 4, 3, rng, 0.0)
    ewc = ElasticWeightConsolidation(lam=10.0)
    features = Tensor(np.ones(8), requires_grad=False)
    out = net(features)
    loss = mse(out["recon"], np.ones(8))
    net.zero_grad()
    loss.backward()
    ewc.observe_grads(net)
    ewc.snapshot(net)
    for p in net.parameters():
        p.data = p.data + 0.2
    assert float(ewc.penalty(net).item()) > 0.0

    buf = PrioritizedReplay(16, RNG(1))
    for i in range(10):
        buf.push(Episode(np.ones(4) * i, i % 3, "t", "n", "", 0.1, 0.2 + i, i))
    batch, idx, weights = buf.sample(4)
    assert len(batch) == 4 and idx.shape == (4,) and weights.shape == (4,)

    bandit = LinUCB(3, 5, alpha=0.4)
    ctx = np.ones(5)
    arm = bandit.select(ctx)
    bandit.update(arm, ctx, 1.0)
    np.testing.assert_allclose(bandit.probabilities(ctx).sum(), 1.0, atol=1e-8)
    assert CortexConfig().source_index("arxiv") == 1

    cfg = CortexConfig(
        online=False,
        sleep_steps=4,
        replay_batch=4,
        feature_dim=64,
        hidden_dim=32,
        latent_dim=16,
        pca_dim=8,
        reservoir_size=24,
        prototype_k=6,
    )
    cx = Cortex(cfg)
    first = cx.step()
    second = cx.learn_text("Prioritized replay samples transitions by TD error.", source="wikipedia", title="replay")
    assert first.step == 1 and second.step == 2
    assert cx.embed("replay").shape == (cfg.latent_dim,)
    for _ in range(4):
        cx.step()
    assert len(cx.relearn(steps=3)) == 3
    assert cx.reinforce() >= 0.0
    assert isinstance(cx.recall("forgetting", k=3), list)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "cortex.npz")
        cx.save(path)
        loaded = Cortex.load(path, cfg=cfg)
        v1, v2 = cx.embed("elastic"), loaded.embed("elastic")
        assert float((v1 - v2) @ (v1 - v2)) < 1e-8
    print("selftest ok")


def _demo() -> None:
    cortex = Cortex(CortexConfig(online=False, rate_limit_seconds=1.5))
    for _ in range(8):
        result = cortex.step()
        print(
            f"step={result.step:03d} source={result.source:12s} "
            f"loss={result.loss:.4f} reward={result.reward:.3f} {result.title!r}"
        )
    cortex.relearn(steps=6)
    cortex.reinforce()
    print("nearest memories:", cortex.recall("continual learning", k=3))
    print("embedding dim:", cortex.embed("replay buffer").shape)


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        _selftest()
    else:
        _demo()
