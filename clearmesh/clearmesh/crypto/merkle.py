"""RFC 6962 Merkle tree."""

from __future__ import annotations

import hashlib


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _hash_leaf(leaf: bytes) -> bytes:
    return _sha256(b"\x00" + leaf)


def _hash_node(left: bytes, right: bytes) -> bytes:
    return _sha256(b"\x01" + left + right)


def _largest_power_of_two_below(n: int) -> int:
    p = 1
    while p * 2 < n:
        p *= 2
    return p


def merkle_root(leaves: list[bytes]) -> bytes:
    if not leaves:
        return _sha256(b"")
    return _root([_hash_leaf(x) for x in leaves])


def _root(nodes: list[bytes]) -> bytes:
    n = len(nodes)
    if n == 1:
        return nodes[0]
    k = _largest_power_of_two_below(n)
    return _hash_node(_root(nodes[:k]), _root(nodes[k:]))


def inclusion_proof(leaves: list[bytes], i: int) -> list[bytes]:
    n = len(leaves)
    if n == 0 or i < 0 or i >= n:
        raise IndexError("proof index out of range")
    return _proof([_hash_leaf(x) for x in leaves], i)


def _proof(nodes: list[bytes], i: int) -> list[bytes]:
    n = len(nodes)
    if n == 1:
        return []
    k = _largest_power_of_two_below(n)
    if i < k:
        return _proof(nodes[:k], i) + [_root(nodes[k:])]
    return _proof(nodes[k:], i - k) + [_root(nodes[:k])]


def verify_inclusion(root: bytes, leaf: bytes, i: int, n: int, proof: list[bytes]) -> bool:
    """RFC 6962 §2.1.3.1 inclusion proof verification."""
    if n <= 0 or i < 0 or i >= n:
        return False
    fn = i
    sn = n - 1
    node = _hash_leaf(leaf)
    for sibling in proof:
        if sn == 0:
            return False
        if fn % 2 == 1 or fn == sn:
            node = _hash_node(sibling, node)
            while fn % 2 == 0 and fn != 0:
                fn //= 2
                sn //= 2
            fn = (fn - 1) // 2
            sn //= 2
        else:
            node = _hash_node(node, sibling)
            fn //= 2
            sn //= 2
    return node == root and sn == 0
