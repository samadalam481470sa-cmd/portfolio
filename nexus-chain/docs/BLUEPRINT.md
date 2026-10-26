# NEXUS Chain — Master Build Blueprint

**Enterprise Blockchain Master Framework**  
Version: 0.1.0-testnet  
License posture: Apache-2.0 for NEXUS custom modules; CosmWasm/SDK/CometBFT/IBC/EVM subject to upstream licenses.  
Disclaimer: Not a regulated exchange, bank, or money transmitter. Financial connectors require separate authorization. No claim of production mainnet security without independent audits and external validator operators.

---

## 1. Design decision: one foundation, compatible extensions

| Source ecosystem | Adopted idea | How NEXUS uses it |
|---|---|---|
| Bitcoin | Merkle inclusion, hash-linked integrity | Block/tx Merkle commitments via CometBFT + indexer proofs |
| Ethereum | Accounts, nonces, receipts, EVM | Cosmos EVM after pin/audit; JSON-RPC wallet surface |
| Solana | Parallel scheduling concepts | Message-level resource locks in settlement module (opt-in) |
| Cosmos SDK | Modular state machine | **Primary foundation** |
| CometBFT | BFT consensus, P2P, finality | **Primary consensus** |
| Avalanche | Independent L1 / validator lifecycle | Genesis + staking params for NEXUS-owned validator set |
| Aptos | Resource ownership safety | Asset registry ownership + permission checks |

**Non-goal:** Naively merging Bitcoin consensus + Solana runtime + Ethereum DB + Cosmos modules into one binary. Assumptions conflict. NEXUS selects **Cosmos SDK + CometBFT**, then adds NEXUS modules and optional Cosmos EVM / IBC.

---

## 2. Upstream open-source foundations (pin before production)

| Component | Role | Upstream | License note |
|---|---|---|---|
| Cosmos SDK | Accounts, modules, governance, store | `cosmos/cosmos-sdk` | Apache-2.0 + deps |
| CometBFT | Validators, voting, P2P, BFT | `cometbft/cometbft` | Apache-2.0 |
| Cosmos EVM | EVM contracts, JSON-RPC | `cosmos/evm` (pin pre-1.0 carefully) | Apache-2.0 + audit |
| IBC-Go | Cross-chain packets | `cosmos/ibc-go` | Apache-2.0 |

Security of the live network depends on **your validators, ops, governance, and audits** — not the brand success of upstream projects.

**Pinned targets for this repo scaffold (adjust in `go.mod` after audit):**
- cosmos-sdk: v0.50.x line
- cometbft: v0.38.x line compatible with that SDK
- ibc-go: v8.x (when wiring IBC)
- cosmos-evm: pin exact commit after security review; disabled by default in genesis

---

## 3. Repository tree

```
nexus-chain/
├── docs/
│   ├── BLUEPRINT.md                 # this file
│   ├── threat_model.md
│   ├── invariants.md
│   └── adr/
├── chain/
│   ├── cmd/nexusd/                  # node + client binary
│   ├── app/                         # application wiring
│   ├── x/
│   │   ├── assetregistry/
│   │   ├── attestation/
│   │   ├── oracle/
│   │   ├── permissions/
│   │   ├── settlement/
│   │   └── protocolguard/
│   └── proto/nexus/.../
├── indexer/                         # PostgreSQL off-chain index
├── gateway/                         # HTTP/gRPC API gateway
├── connectors/                      # brokerage / banking / market-data (authorized)
├── ops/                             # recovery, monitoring, failover, upgrades
├── deploy/                          # docker, k8s, systemd
├── explorer/                        # read-only UI
├── sdks/{go,typescript}/
├── configs/{local,testnet,mainnet-template}/
├── genesis/
├── scripts/
└── tests/{consensus,financial,security,load,fault}/
```

---

## 4. Core data structures

### 4.1 Block header (CometBFT)
- `version`, `chain_id`, `height`, `time`
- `last_block_id`, `last_commit_hash`, `data_hash`
- `validators_hash`, `next_validators_hash`, `consensus_hash`
- `app_hash` (SDK state commitment), `last_results_hash`, `evidence_hash`, `proposer_address`

### 4.2 Signed transaction (Cosmos SDK / EVM)
- `body`: messages, memo, timeout_height
- `auth_info`: signer infos (account sequence/nonce), fee
- `signatures`
- EVM path: Ethereum legacy/dynamic-fee txs via Cosmos EVM ante handlers (phase 5)

### 4.3 Account state
- address, sequence (nonce), public key, NXN (native) balance, module balances

### 4.4 State commitment
- SDK IAVL (or successor authenticated store) root → `app_hash` in header

### 4.5 Contract storage
- CosmEVM account code hash + storage trie (when EVM enabled)

### 4.6 Asset registry record
```
Asset {
  id, denom, display_name, decimals,
  issuer, asset_class, status,
  permissions_ref, created_height, metadata_uri
}
```

### 4.7 Financial attestation
```
Attestation {
  id, subject_ref, schema_id, payload_hash,
  signer, signature, observed_at, anchored_height, status
}
```

### 4.8 Oracle report
```
OracleReport {
  id, feed_id, value_bytes, decimals,
  reporters[], quorum_met, timestamp, expires_height
}
```

### 4.9 Validator state
- operator address, consensus pubkey, voting power, jailed, bonded tokens, commission

### 4.10 Transaction index (PostgreSQL)
- blocks, txs, events, messages, assets, attestations, oracle_reports, settlements

---

## 5. Custom modules (`chain/x/`)

Each module ships: `types/`, `keeper/`, msg server, query server, genesis, migrations, CLI, unit tests.

### 5.1 `assetregistry`
- Create / update / freeze asset metadata
- Bind issuer + denom uniqueness
- Emit events for indexer

### 5.2 `attestation`
- Anchor signed financial proof commitments (hash only on-chain)
- Verify Ed25519/Secp256k1 against registered attestor keys
- Never store raw PII on-chain

### 5.3 `oracle`
- Submit feed updates with multi-reporter quorum
- Bound staleness by `expires_height`
- Settlement may read only non-expired quorum reports

### 5.4 `permissions`
- Role bindings: ISSUER, ATTESTOR, ORACLE_REPORTER, SETTLEMENT_AGENT, GUARDIAN
- Capability checks used by other modules

### 5.5 `settlement`
- Native asset transfer rules, DvP-style multi-leg intents
- Resource locks (Solana-inspired): exclusive account locks per tx message set
- Fee payment in NXN

### 5.6 `protocolguard`
- Pause switches per module (guardian multisig / governance)
- Emergency halt does **not** rewrite history or alter past `app_hash`
- Upgrade signaling only; execution requires governance + ops runbooks

---

## 6. Consensus and validators

- Engine: CometBFT BFT
- Initial production target: **7 independently operated validators**, equal power ⇒ tolerate **f=2** Byzantine if remaining 5 communicate
- Not resilient to all correlated cloud/key failures — document ops diversity
- Evidence: double-sign → jail via slashing module (SDK staking/slashing when wired)

### Local scaffold mode
`nexusd solo` runs a single-process sequencer for module/API development when full CometBFT networking is not required. Testnet acceptance requires multi-validator CometBFT.

---

## 7. Autonomous operations (restricted authority)

| Capability | Allowed | Forbidden |
|---|---|---|
| Node recovery | Restart non-signing process, remount volumes | Change consensus rules unsupervised |
| Load management | Scale gateway/indexer replicas | Auto-mint assets |
| Monitoring | Alert on latency, missed blocks, peer drops | Silent key export |
| Data recovery | Restore from signed snapshots + rebuild index | Rewrite finalized blocks |
| Provider failover | Route connector traffic to healthy providers | Bypass attestation verification |
| Upgrade validation | Run staging suite, open governance proposal | Force binary swap without quorum |

---

## 8. Build order (exact)

1. Import/pin Cosmos SDK + CometBFT foundations (Apache-2.0 review).
2. Create NEXUS chain identity, genesis, `nexusd`, native asset **NXN**.
3. Multi-validator devnet: blocks, transfers, finality.
4. Implement assetregistry, attestation, oracle, permissions, settlement, protocolguard.
5. Add Cosmos EVM after dependency + security pin; enable Ethereum wallets/JSON-RPC.
6. Indexer, API gateway, SDKs, explorer.
7. Separately authorized brokerage / banking / market-data connectors.
8. Monitoring, non-validator recovery, backups, incident controls.
9. Consensus, financial-integrity, security, load, fault-injection tests with external operators.
10. Independent audits → controlled testnet → mainnet process.

---

## 9. Genesis parameters (initial)

```
chain_id: nexus-1
native_denom: unxn          # 1 NXN = 1_000_000 unxn
bond_denom: unxn
max_validators: 100
initial_validators: 7 (testnet may use 4)
block_time_target: ~5s
gov_voting_period: 72h (mainnet template); shorter on testnet
protocolguard_paused: false
evm_enabled: false          # enable only after pin/audit
ibc_enabled: false          # enable after IBC wiring tests
```

---

## 10. Indexer SQL (initial)

See `indexer/sql/001_init.sql`:
- `blocks(height PK, hash, app_hash, proposer, time)`
- `transactions(hash PK, height, index, sender, fee, code, raw)`
- `events(id, height, tx_hash, type, attributes jsonb)`
- `assets`, `attestations`, `oracle_reports`, `settlements`

Rebuild is idempotent from chain RPC/WS; chain remains source of truth.

---

## 11. API gateway

- REST `/v1/...` + gRPC mirror
- Auth: mTLS and/or signed requests for privileged connector routes
- Public: blocks, txs, balances, assets, proofs
- Restricted: connector submit, attestor registration (permissions-gated)

---

## 12. Connector interfaces

```
BrokerageConnector.SubmitOrderIntent(ctx, intent) -> attestation_ref
BankingConnector.FetchBalanceSnapshot(ctx, account_ref) -> signed_payload
MarketDataConnector.GetMid(ctx, symbol) -> oracle_candidate
```

All connectors:
- are **out of consensus**
- may only influence chain via attestation/oracle messages after verification
- require separate legal/authorization agreements for production

---

## 13. Protocol invariants

1. Supply conservation for NXN except explicit mint/burn governance paths.
2. No settlement against expired oracle reports.
3. Permissions checked before asset create, attest, oracle submit, settle.
4. Protocolguard pause blocks new state transitions for paused modules; historical blocks immutable.
5. Indexer may lag; never overrides on-chain balances.
6. Autonomous recovery cannot alter `app_hash` history.

---

## 14. Local development commands

```bash
# module unit tests (scaffold runtime)
cd nexus-chain && go test ./...

# solo node (module development)
go run ./chain/cmd/nexusd solo --home ~/.nexus

# multi-validator docker testnet
docker compose -f deploy/docker/docker-compose.yml up --build

# indexer
psql "$DATABASE_URL" -f indexer/sql/001_init.sql
go run ./indexer/cmd/nexus-indexer --rpc http://127.0.0.1:26657

# gateway
go run ./gateway/cmd/nexus-gateway --rpc http://127.0.0.1:26657 --listen :8080
```

Production CometBFT multi-node: follow `scripts/localnet.sh` and `docs/adr/0001-cosmos-foundation.md`.

---

## 15. Testnet acceptance criteria

- [ ] ≥4 validators produce ≥1000 contiguous blocks with matching `app_hash`
- [ ] Kill 1 validator: chain continues; missed rounds bounded
- [ ] Kill f+1 validators: chain halts without forking
- [ ] Asset register → permissioned settle → indexer row appears
- [ ] Attestation with bad signature rejected
- [ ] Oracle stale feed rejected by settlement
- [ ] Protocolguard pause stops settlement msgs; unpause restores
- [ ] Snapshot restore + index rebuild converges
- [ ] Load test report published under `docs/benchmarks.md`
- [ ] Threat model reviewed; no unresolved criticals

---

## 16. ADR index

- 0001 Cosmos SDK + CometBFT as foundation
- 0002 Native asset NXN and fee market
- 0003 On-chain hash attestations only (no PII)
- 0004 EVM optional and gated
- 0005 Autonomous ops cannot rewrite history
- 0006 Connector authority boundary

---

## 17. What “done” means for this repository stage

This repository delivers:
- the master blueprint and threat/invariant docs
- a compilable NEXUS module framework and `nexusd` solo runtime for financial modules
- indexer schema, gateway, connector stubs, ops playbooks, docker localnet
- automated unit tests for module invariants

Production CometBFT validator networking, full SDK store wiring, Cosmos EVM, and IBC are **integration phases** executed against pinned upstream versions after license and security review — as specified in §8.

The frameworks provide the foundation. **NEXUS financial modules, secure integration services, testing, and production operations** are the proprietary layer this project owns.


---

## 18. Implementation-level message schemas

### MsgRegisterAsset
```
signer: string (bech32 / nexus address)
id: string
denom: string
display_name: string
decimals: uint32
asset_class: string
metadata_uri: string
```
Validation: unique id/denom; signer has ISSUER; decimals ≤ 18; denom charset `[a-z0-9]{2,64}`.

### MsgAnchorAttestation
```
id, subject_ref, schema_id, payload_hash (64 hex), pubkey_hex, signature_hex, observed_at_unix
```
Validation: ATTESTOR role; Ed25519 verify over `id|subject_ref|schema_id|payload_hash`; no raw payload bytes on-chain.

### MsgSubmitOracleReport
```
id, feed_id, value, decimals, expires_height
```
Validation: ORACLE_REPORTER; expires_height > current; quorum threshold from params.

### MsgSettleIntent
```
id, legs[], oracle_feed?, attestation_ref?, resource_locks[]
```
Validation: SETTLEMENT_AGENT; each leg amount > 0; atomic balance checks; optional oracle freshness; optional attestation existence; exclusive locks.

### MsgSetModulePause
```
module: string
paused: bool
```
Validation: GUARDIAN; cannot pause `protocolguard` via this message; emits event; does not rewrite history.

---

## 19. Keeper storage keys (canonical)

| Module | Key | Value |
|---|---|---|
| permissions | `permissions/bind/{addr}` | Binding JSON |
| assetregistry | `assetregistry/id/{id}` | Asset JSON |
| assetregistry | `assetregistry/denom/{denom}` | asset id bytes |
| attestation | `attestation/id/{id}` | Attestation JSON |
| oracle | `oracle/report/{id}` | Report JSON |
| oracle | `oracle/latest/{feed}` | report id |
| settlement | `bank/bal/{addr}/{denom}` | int64 JSON |
| settlement | `settlement/intent/{id}` | Intent JSON |
| protocolguard | `protocolguard/state` | GuardState JSON |

All iteration for hashing/export uses lexicographically sorted keys.

---

## 20. Events (indexer projections)

- `permissions.set` → attributes: address
- `asset.registered` → id, denom
- `asset.frozen` → id
- `attestation.anchored` → id, hash
- `oracle.submitted` → id, feed
- `settlement.settled` → id
- `protocolguard.pause` → module, paused

Indexer maps events into SQL tables from §10. Reorgs do not apply under BFT finality; indexer may still retry inserts idempotently by primary key.

---

## 21. Fee and gas model (production SDK wiring)

When wired to Cosmos SDK:
- `gas` charged per message type weight
- fees paid in `unxn`
- ante handler ordering: protocolguard pause check → sig verify → sequential sequence → fee deduct → message execution

Solo scaffold omits gas metering; production must enable SDK ante + gas config before public testnet.

---

## 22. Validator lifecycle (Avalanche-inspired ops, Cosmos staking mechanics)

1. Operator creates consensus key + node identity
2. `gentx` / staking bond with `unxn`
3. Inclusion in next validator set at EndBlock per SDK staking
4. Downtime / double-sign → jail via slashing
5. Unbond queue with unbonding time from genesis params

Testnet may start with fixed 4–7 genesis validators before open bonding.

---

## 23. Parallel execution concepts (Solana/Aptos inspired, constrained)

Settlement `resource_locks` declare exclusive accounts touched by an intent.
Within a block, intents with disjoint lock sets MAY execute concurrently in future runtimes.
v0.1 solo executes sequentially but rejects conflicting locks in-process to prove the safety rule.
Do not claim Block-STM equivalence until a parallel scheduler is implemented and tested.

---

## 24. IBC and EVM phase gates

### EVM enablement checklist
- [ ] Pin cosmos-evm commit
- [ ] Dependency license scan
- [ ] Fuzz JSON-RPC surface
- [ ] Replay test vectors
- [ ] Genesis flag `evm_enabled=true` via governance

### IBC enablement checklist
- [ ] Pin ibc-go major
- [ ] Light client configs
- [ ] Relayer runbook
- [ ] Packet timeout + refund tests
- [ ] Genesis flag `ibc_enabled=true`

---

## 25. Security control matrix

| Control | Module / layer | Status in scaffold |
|---|---|---|
| Role gates | permissions | Implemented |
| Signature attestations | attestation | Implemented |
| Oracle expiry | oracle + settlement | Implemented |
| Atomic multi-leg settle | settlement | Implemented |
| Emergency pause | protocolguard | Implemented |
| State rollback on failed deliver | app.Deliver | Implemented (solo) |
| Privval double-sign protection | CometBFT | Production phase |
| Snapshot signing | ops | Documented |
| Connector authz | connectors/* | Stub (fail closed) |

---

## 26. SQL index design details

### Partitioning guidance
- `events` by height ranges (e.g., 1M block chunks) when volume grows
- `transactions.hash` unique prevents duplicate ingest

### Rebuild algorithm
1. Truncate derived tables (keep schema)
2. Walk heights `1..latest` via RPC
3. Insert blocks → txs → events → module projections
4. Compare spot balances vs chain queries; abort on mismatch

---

## 27. Gateway routes (v1)

Public:
- `GET /v1/status`
- `GET /v1/balance?address=&denom=`
- `GET /v1/connectors/manifest`

Demo (local only; disable on public testnet):
- `POST /v1/demo/bootstrap-finance`
- `POST /v1/demo/settle?to=`

Production adds:
- `GET /v1/blocks/{height}`
- `GET /v1/txs/{hash}`
- `GET /v1/assets/{id}`
- `GET /v1/attestations/{id}`
- `GET /v1/oracle/{feed}`
- mTLS for attestor/settlement agent submit endpoints

---

## 28. SDK sketches

### Go
```go
client := nexus.NewClient("http://127.0.0.1:8080")
st, _ := client.Status(ctx)
```

### TypeScript
```ts
const st = await fetch(`${base}/v1/status`).then(r => r.json());
```

Packages live under `sdks/go` and `sdks/typescript` (thin clients initially).

---

## 29. Fault-injection battery

| Case | Expect |
|---|---|
| Invalid attestation sig | reject; height unchanged |
| Settle with stale oracle | reject |
| Settle overdraft | reject; balances unchanged |
| Conflicting resource locks | reject second |
| Pause settlement | settle rejects; mint may still work if not paused |
| Kill solo process mid-request | restart from store home; no partial intent commit |

CometBFT network cases (production): partition, double-sign evidence, 2/7 down liveness, 3/7 down halt.

---

## 30. Load targets (non-binding)

- Module unit path: ≥1k settles/sec in-process on developer laptop (not networking bound)
- Public testnet: prioritize safety/finality over TPS marketing
- Publish measured numbers in `docs/benchmarks.md` after compose load runs

---

## 31. Mainnet readiness gate

1. External validator operators signed ops agreements
2. Independent security audit of custom modules + genesis
3. Key ceremony + distributed genesis
4. Bug bounty window on testnet
5. Freeze feature flags (EVM/IBC) unless explicitly approved
6. Incident response contacts published

---

## 32. Glossary

- **NXN / unxn** — native coin / base denom
- **Attestation** — signed hash commitment to off-chain financial data
- **Oracle feed** — quorum-verified external value with expiry
- **Intent** — atomic multi-leg settlement request
- **Protocolguard** — emergency pause controller
- **Solo scaffold** — single-process app for module development prior to CometBFT networking

---

## 33. Explicit non-claims

NEXUS Chain scaffold does **not** claim:
- FDIC/SPIC/SEC registration
- Instant compatibility with every Ethereum dapp before EVM enablement
- Optimal parallel execution equal to Solana/Aptos runtimes
- Immunity to all validator collusion or cloud correlated failure
- Live brokerage/banking connectivity without separate authorization

---

## 34. Contributor workflow

1. Read BLUEPRINT + threat_model + invariants
2. `go test ./...`
3. Add keeper tests for any new message
4. Update ADR if changing foundation assumptions
5. Never commit production private keys

---

## 35. Mapping blueprint → repository paths

| Blueprint item | Path |
|---|---|
| Modules | `chain/x/*` |
| App wiring | `chain/app` |
| Node binary | `chain/cmd/nexusd` |
| Indexer SQL | `indexer/sql` |
| Gateway | `gateway/cmd/nexus-gateway` |
| Connectors | `connectors/*` |
| Ops | `ops/*` |
| Docker | `deploy/docker` |
| Genesis template | `genesis/genesis.json` |
| Financial tests | `tests/financial` |

---

## 36. Closing

NEXUS is designed as a **real independent Layer-1 direction**: own history, own validators, own finality, programmable assets, optional EVM, financial integration boundary.

Upstream Cosmos SDK and CometBFT supply battle-tested consensus and modularity. **Your engineers own** the NEXUS financial modules, secure integrations, tests, and production operations that make the network an enterprise settlement fabric rather than a generic template chain.
