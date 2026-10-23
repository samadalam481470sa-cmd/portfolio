# ADR 0006: Inline envelopes vs crypto-shredding

v1 stores envelope ciphertext commitments on-chain (hash commitment) with ciphertext
in the transaction body for demo simplicity. Production would move payloads off-chain
and crypto-shred data keys to honour erasure requests. Tracked as a stretch goal.
