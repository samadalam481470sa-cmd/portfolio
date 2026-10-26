# NEXUS Chain — Live NXN Crypto Ledger

**Public-testnet cryptocurrency + blockchain ledger** built as an independent L1 framework (Cosmos SDK / CometBFT–oriented architecture) with a **live native token: NXN**.

| | |
|---|---|
| Ticker | **NXN** |
| Base unit | `unxn` (6 decimals) |
| Genesis supply | 100,000,000 NXN |
| Chain ID | `nexus-1` |

> **Honest scope:** This is runnable live ledger software for a **public testnet crypto**. It is **not** a stock, not legal advice, and not an exchange listing. Market value and listings are outside the code.

## Quickstart — run the live ledger

```bash
cd nexus-chain
go test ./...
go run ./chain/cmd/nexusd start --home /tmp/nexus-live --faucet
```

Open the explorer: [http://127.0.0.1:26657/](http://127.0.0.1:26657/)

```bash
# new wallet
go run ./chain/cmd/nexusd wallet create --out alice.json

# claim faucet NXN (from explorer or):
curl -s -X POST http://127.0.0.1:26657/v1/faucet \
  -H 'content-type: application/json' \
  -d "{\"address\":\"$(jq -r .address alice.json)\"}"

# after ~2s (next block), check balance
go run ./chain/cmd/nexusd balance --address "$(jq -r .address alice.json)"

# send NXN (amount in NXN)
go run ./chain/cmd/nexusd wallet create --out bob.json
# fund alice first via faucet, then:
go run ./chain/cmd/nexusd tx send --from alice.json --to "$(jq -r .address bob.json)" --amount 1.5
```

## What is fully implemented

- **Live crypto token NXN** with fixed genesis supply and treasury
- **Wallets** (Ed25519) — create, persist, sign
- **Signed transfers** with sequence/nonce replay protection
- **Persistent ledger** (`state/ledger.json` + per-height blocks)
- **Automatic block production** (~2s)
- **HTTP RPC** + **HTMX-style explorer** (create wallet, faucet, balances)
- **Testnet faucet** (rate-limited)
- Enterprise modules still present: attestations, oracle, settlement, protocolguard
- Docker compose, CI, blueprint, tokenomics

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/status` | height, app hash, supply |
| GET | `/v1/supply` | NXN supply |
| GET | `/v1/balance?address=` | balance + sequence |
| POST | `/v1/tx/send` | submit signed MsgSend |
| GET | `/v1/tx/{hash}` | receipt |
| GET | `/v1/blocks/latest` | latest block |
| POST | `/v1/faucet` | claim testnet NXN |
| POST | `/v1/wallet/create` | generate wallet |
| GET | `/` | live explorer |

## Docker

```bash
docker compose -f deploy/docker/docker-compose.yml up --build
```

## Architecture docs

- [docs/TOKENOMICS.md](docs/TOKENOMICS.md) — NXN economics
- [docs/BLUEPRINT.md](docs/BLUEPRINT.md) — master engineering blueprint
- [docs/threat_model.md](docs/threat_model.md)

## License

Apache-2.0 for NEXUS custom code. Upstream Cosmos/CometBFT/EVM/IBC remain under their licenses when you pin them for production validator networking.
