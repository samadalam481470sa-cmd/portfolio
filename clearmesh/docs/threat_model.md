# Threat model

## Assets

Synthetic SIM/TBOND balances, settlement finality, compliance attestations, travel-rule envelopes.

## Adversaries

| Adversary | Capabilities | Mitigations |
|---|---|---|
| f=1 Byzantine validator | Equivocate, conflicting proposals, silence | Tendermint locking + quorum 3/4; evidence recorded; chain halts rather than forks if 2 down |
| Malicious member bank | Try to overdraw, skip screening, forge attestations | Consensus validity rules; maker-checker; debit checks; attestation verify |
| Malicious proposer | Censor for one round; include invalid txs | Honest validators prevote nil on bad roots/txs |
| Network attacker | Spoof peers | Signed HELLO bound to chain_id + genesis_hash; allowlist |
| Compromised ops key | Submit payments | Maker-checker above threshold; role separation |

## Limitations (honest)

- Validators see amounts and parties.
- Chain proves attestation against a list version, not screening correctness (`audit rescreen` after the fact).
- Inline envelopes conflict with erasure requests (see ADR on crypto-shredding).
- No HSM in v1.
- Two colluding validators can halt the chain.
- No formal verification.
- **No real-money rails.** Connector APIs are synthetic sandboxes only.
