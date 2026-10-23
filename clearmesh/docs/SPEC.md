# Clearmesh SPEC

## Domain-separated hashes

`h(tag, data) = SHA-256(tag ASCII || 0x00 || data)`

Tags: `CLEARMESH/{TX,HDR,VOTE,PROPOSAL,ATTEST,ENV,RPC,HELLO,LEAF,CYCLE}/v1`

## Encoding

All consensus objects are `@dataclass(frozen=True, slots=True)` encoded as CBOR arrays
`[TYPE_TAG, field…]` with `cbor2` `canonical=True`. Decode rejects any input that does
not re-encode byte-for-byte. No floats, maps, or bignums.

## Amounts

Integer minor units, `0 < a < 2**63`. Asset `SIM` has 2 decimals; `TBOND` has 0.

## Block header hash

`block_hash = h("CLEARMESH/HDR/v1", encode(header))`

## Transaction id

`tx_id = h("CLEARMESH/TX/v1", encode([version, chain_id, tx_type, signer, valid_until_height, body]))`

Signatures are Ed25519 over `tx_id`.

## Vote sign bytes

`h("CLEARMESH/VOTE/v1", encode([chain_id, type, height, round, block_hash or b""]))`

## Quorum

n=4, f=1, quorum = `total*2//3+1` = 3, skip-ahead = `total//3+1` = 2.

## Reason codes

AM04, RR04, AC06, AB05, DUPL, FF01, AG01, AG02, BE05, DS0H, DS04, TM01, …

See `clearmesh/core/reasons.py`.
