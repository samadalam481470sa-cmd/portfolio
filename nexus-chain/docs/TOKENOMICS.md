# NXN — NEXUS native crypto (public testnet)

| Field | Value |
|---|---|
| Display ticker | **NXN** |
| Base denom | `unxn` |
| Decimals | 6 (1 NXN = 1_000_000 unxn) |
| Genesis supply | 100,000,000 NXN |
| Chain ID | `nexus-1` |
| Network label | `nexus-public-testnet` |

## What “live” means here

This repository runs a **real cryptographic ledger**:
- Ed25519 wallets and signed transfers
- Account sequences (replay protection)
- Persistent state on disk
- Continuous block production
- Merkle-style app hash per height
- Faucet + explorer for the public testnet experience

It is **not**:
- A stock or equity security
- Automatically listed on Coinbase/Binance/Robinhood
- Legal tender or a bank deposit
- Guaranteed to have market value

Running the software makes NXN **live on your network**. Exchange listings, liquidity, and securities-law compliance are separate human/legal steps outside this codebase.

## Distribution (genesis)

At genesis, full supply is minted to the **treasury** validator/operator wallet. The public-testnet faucet sends small amounts (default 10 NXN) from treasury for demos.

## Transfers

`MsgSend` moves NXN between addresses. Anyone with a funded wallet can send; no special role required (unlike enterprise settlement intents).
