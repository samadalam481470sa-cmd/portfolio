# Clearmesh

**Compliance-gated BFT settlement ledger for synthetic interbank payments.**

Clearmesh simulates a wholesale RTGS-style network: maker-checker signatures, sanctions attestations, encrypted travel-rule envelopes, Tendermint-style finality, FIFO queues, deterministic gridlock netting, and atomic DvP — built from scratch in Python (no Cosmos/Substrate/web3 frameworks).

> **Disclaimer:** Not a regulated, certified or audited payment system. No claim of regulatory compliance. ISO 20022 shapes are used for illustration with test currency `XTS`. **No real money.** No custody. **No connection to live Robinhood, brokerage, or payment rails.** External apps integrate only against the synthetic OpenAPI/WebSocket sandbox (`/v1/connectors/manifest`).

## Quickstart

```bash
cd clearmesh
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
clearmesh testnet --out ./testnet
clearmesh node start --config ./testnet/node.toml
# other terminal
clearmesh publish-sanctions --keys-dir ./testnet/keys
clearmesh issue --to BANKA --asset SIM --amount 100.00 --key ./testnet/keys/SA_ops.key
clearmesh pay --from BANKA --to BANKB --amount 10.00 --interbank --keys-dir ./testnet/keys
clearmesh verify-balance BANKA SIM
```

OpenAPI: `http://127.0.0.1:26657/docs` · Explorer: `uvicorn tools.explorer.app:app --port 8080`

Docker: `docker compose -f deploy/docker-compose.yml up --build`

## Architecture (short)

- **Consensus:** Solo sequencer for the product path; pure `handle(cs, ev)` Tendermint state machine + seeded simulator for BFT safety/liveness.
- **State:** SQLite WAL, atomic per-block commits, RFC 6962 state/receipts roots, Merkle-sum liabilities tree.
- **Security:** Ed25519/X25519/XChaCha20 via PyNaCl only; domain-separated hashes; canonical CBOR; privval write-before-sign; WAL fsync; role-separated keys; determinism lint.
- **Connectors:** REST + WebSocket + OpenAPI for portfolio/regtech sandboxes — explicitly synthetic.

## Repo layout

See the outline in the project brief. Package root is `clearmesh/` with `docs/`, `sim/`, `tools/`, `tests/`, `deploy/`, `samples/`.

## Tests

```bash
pytest -q
python tools/lint_determinism.py
```

## License

MIT — with the educational / no-real-money disclaimer above.
