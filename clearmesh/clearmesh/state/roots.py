"""state_root, liabilities_root, receipts_root, tx_root."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from clearmesh.core.codec import encode
from clearmesh.crypto.hashing import h
from clearmesh.crypto.merkle import merkle_root
from clearmesh.crypto.sumtree import sumtree_root

if TYPE_CHECKING:
    from clearmesh.state.overlay import Overlay
    from clearmesh.types.receipt import Receipt
    from clearmesh.types.tx import TxEnvelope


def state_root(view: Overlay) -> bytes:
    leaves: list[bytes] = []
    for k, v in view.scan(b""):
        leaves.append(encode([k, hashlib.sha256(v).digest()]))
    return merkle_root(leaves)


def liabilities_root(view: Overlay) -> bytes:
    """Merkle root over per-asset sumtree entries (excludes contra accounts)."""
    # Collect balances grouped by asset
    by_asset: dict[str, list[tuple[str, int]]] = {}
    supplies: dict[str, int] = {}
    for k, v in view.scan("bal/"):
        # bal/{pid}/{asset}
        parts = k.decode("utf-8").split("/")
        if len(parts) != 3:
            continue
        _, pid, asset = parts
        if pid.startswith("sys:issuance:"):
            continue
        from clearmesh.core.codec import decode

        bal = decode(int, v)  # type: ignore[arg-type]
        by_asset.setdefault(asset, []).append((pid, bal))
    for k, v in view.scan("asset/"):
        from clearmesh.core.codec import decode
        from clearmesh.types.records import AssetMeta

        asset = k.decode("utf-8").split("/", 1)[1]
        meta = decode(AssetMeta, v)
        supplies[asset] = meta.total_supply

    entries: list[bytes] = []
    for asset in sorted(by_asset.keys()):
        leaves = sorted(by_asset[asset], key=lambda x: x[0])
        root, total = sumtree_root(leaves)
        supply = supplies.get(asset, 0)
        entries.append(encode([asset, root, total, supply]))
    return merkle_root(entries)


def receipts_root(receipts: list[Receipt]) -> bytes:
    leaves = [encode(r) for r in receipts]
    return merkle_root(leaves)


def tx_root(txs: list[TxEnvelope]) -> bytes:
    from clearmesh.types.tx import tx_id

    leaves = [tx_id(t) for t in txs]
    return merkle_root(leaves)


def policy_hash(view: Overlay) -> bytes:
    raw = view.get("pol")
    if raw is None:
        return h("CLEARMESH/LEAF/v1", b"")
    return hashlib.sha256(raw).digest()


def validators_hash(validator_pubkeys: list[bytes]) -> bytes:
    leaves = sorted(validator_pubkeys)
    return merkle_root(leaves)
