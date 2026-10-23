"""Merkle-sum tree for balance + total-supply proofs."""

from __future__ import annotations

import hashlib
import struct


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _u64be(n: int) -> bytes:
    if n < 0 or n >= 2**63:
        raise ValueError("sum out of range")
    return struct.pack(">Q", n)


def _largest_power_of_two_below(n: int) -> int:
    p = 1
    while p * 2 < n:
        p *= 2
    return p


def _leaf(pid: str, bal: int) -> tuple[bytes, int]:
    return _sha256(b"\x00" + pid.encode("ascii") + _u64be(bal)), bal


def _node(lh: bytes, ls: int, rh: bytes, rs: int) -> tuple[bytes, int]:
    total = ls + rs
    if total < 0 or total >= 2**63:
        raise ValueError("sum overflow")
    return _sha256(b"\x01" + lh + _u64be(ls) + rh + _u64be(rs)), total


def sumtree_root(leaves: list[tuple[str, int]]) -> tuple[bytes, int]:
    if not leaves:
        return _sha256(b""), 0
    for _, bal in leaves:
        if bal < 0 or bal >= 2**63:
            raise ValueError("negative or oversized balance")
    return _root([_leaf(pid, bal) for pid, bal in leaves])


def _root(nodes: list[tuple[bytes, int]]) -> tuple[bytes, int]:
    n = len(nodes)
    if n == 1:
        return nodes[0]
    k = _largest_power_of_two_below(n)
    lh, ls = _root(nodes[:k])
    rh, rs = _root(nodes[k:])
    return _node(lh, ls, rh, rs)


def sum_proof(leaves: list[tuple[str, int]], index: int) -> list[tuple[bytes, int]]:
    n = len(leaves)
    if n == 0 or index < 0 or index >= n:
        raise IndexError("proof index out of range")
    return _proof([_leaf(pid, bal) for pid, bal in leaves], index)


def _proof(nodes: list[tuple[bytes, int]], i: int) -> list[tuple[bytes, int]]:
    n = len(nodes)
    if n == 1:
        return []
    k = _largest_power_of_two_below(n)
    if i < k:
        return _proof(nodes[:k], i) + [_root(nodes[k:])]
    return _proof(nodes[k:], i - k) + [_root(nodes[:k])]


def verify_sum(
    root: bytes,
    pid: str,
    bal: int,
    index: int,
    n: int,
    proof: list[tuple[bytes, int]],
    expected_total: int,
) -> bool:
    if bal < 0 or bal >= 2**63 or expected_total < 0 or expected_total >= 2**63:
        return False
    if n <= 0 or index < 0 or index >= n:
        return False
    fn = index
    sn = n - 1
    node_h, node_s = _leaf(pid, bal)
    for sib_h, sib_s in proof:
        if sib_s < 0 or sib_s >= 2**63 or sn == 0:
            return False
        if fn % 2 == 1 or fn == sn:
            node_h, node_s = _node(sib_h, sib_s, node_h, node_s)
            while fn % 2 == 0 and fn != 0:
                fn //= 2
                sn //= 2
            fn = (fn - 1) // 2
            sn //= 2
        else:
            node_h, node_s = _node(node_h, node_s, sib_h, sib_s)
            fn //= 2
            sn //= 2
    return node_h == root and node_s == expected_total and sn == 0
