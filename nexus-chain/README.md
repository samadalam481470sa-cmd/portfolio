# NEXUS Chain

**Enterprise Blockchain Master Framework** — an independent Layer-1 design built around the **Cosmos SDK + CometBFT** foundation, with proprietary NEXUS financial modules, APIs, indexer, connectors, and autonomous ops controls.

> Public portfolio / testnet scaffold. Not a regulated financial institution. Connectors require separate authorization for production. Security depends on your validators, audits, and operations.

## Foundations (upstream)

| Layer | Choice |
|---|---|
| Application framework | Cosmos SDK (pin before production) |
| Consensus / P2P | CometBFT |
| Optional contracts | Cosmos EVM (gated off by default) |
| Optional interoperability | IBC-Go |

See [docs/BLUEPRINT.md](docs/BLUEPRINT.md) for the full engineering blueprint (architecture, modules, build order, acceptance criteria).

## What’s in this repo

- **Custom modules:** `assetregistry`, `attestation`, `oracle`, `permissions`, `settlement`, `protocolguard`
- **`nexusd solo`:** local deterministic runtime for module/API development
- **Indexer SQL + gateway + connector interfaces + ops runbooks**
- **Docker localnet** skeleton for multi-node bring-up
- **Unit tests** for financial invariants

Production multi-validator CometBFT networking and full SDK store wiring follow the blueprint’s build order (§8) against audited pins.

## Quickstart

```bash
cd nexus-chain
go test ./...
go run ./chain/cmd/nexusd solo --home /tmp/nexus-home
# another terminal
go run ./gateway/cmd/nexus-gateway --home /tmp/nexus-home --listen :8080
curl -s localhost:8080/v1/status | jq
```

Docker:

```bash
docker compose -f deploy/docker/docker-compose.yml up --build
```

## Native asset

- Display: **NXN**
- Base denom: `unxn` (1 NXN = 1_000_000 `unxn`)

## License

Apache-2.0 for NEXUS custom code in this tree. Upstream Cosmos/CometBFT/EVM/IBC remain under their licenses and must be pinned and reviewed before production use.
