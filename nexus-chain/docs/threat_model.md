# NEXUS threat model (scaffold)

## Assets
Validator keys, NXN balances, asset registry integrity, attestation authenticity, oracle freshness, settlement atomicity.

## Adversaries
| Threat | Mitigation |
|---|---|
| f Byzantine validators | CometBFT BFT; target 7 validators ⇒ f=2 |
| Malicious module user | Permissions roles; protocolguard pause |
| Forged attestation | Ed25519 verify before anchor |
| Stale oracle | expires_height enforced in settlement |
| Compromised connector | Out-of-consensus; cannot mint without roles |
| Autonomic recovery abuse | Ops cannot rewrite history / consensus rules |

## Limitations
- Solo scaffold is not multi-validator BFT
- CosmEVM/IBC disabled until pinned and audited
- Connectors are stubs without production authorization
- No formal verification in v0.1
