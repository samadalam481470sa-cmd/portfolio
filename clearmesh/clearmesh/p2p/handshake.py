"""Signed HELLO bound to chain_id + genesis_hash."""

from __future__ import annotations

import os
from dataclasses import dataclass

import cbor2

from clearmesh.crypto.hashing import h
from clearmesh.crypto.keys import verify


@dataclass(frozen=True, slots=True)
class Hello:
    chain_id: str
    genesis_hash: bytes
    node_pubkey: bytes
    nonce32: bytes
    height: int


def encode_hello(hello: Hello) -> bytes:
    return cbor2.dumps(
        [hello.chain_id, hello.genesis_hash, hello.node_pubkey, hello.nonce32, hello.height],
        canonical=True,
    )


def decode_hello(data: bytes) -> Hello:
    arr = cbor2.loads(data)
    return Hello(
        chain_id=arr[0],
        genesis_hash=arr[1],
        node_pubkey=arr[2],
        nonce32=arr[3],
        height=arr[4],
    )


def make_hello(chain_id: str, genesis_hash: bytes, node_pubkey: bytes, height: int) -> Hello:
    return Hello(chain_id, genesis_hash, node_pubkey, os.urandom(32), height)


def sign_ack(signer, peer_nonce: bytes, own_pubkey: bytes, chain_id: str) -> bytes:
    msg = h("CLEARMESH/HELLO/v1", peer_nonce + own_pubkey + chain_id.encode("ascii"))
    return signer.sign(msg)


def verify_ack(
    peer_pubkey: bytes, peer_nonce: bytes, own_pubkey: bytes, chain_id: str, sig: bytes
) -> bool:
    msg = h("CLEARMESH/HELLO/v1", peer_nonce + own_pubkey + chain_id.encode("ascii"))
    return verify(peer_pubkey, msg, sig)
