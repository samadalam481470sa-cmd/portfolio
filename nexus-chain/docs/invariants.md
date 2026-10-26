# Protocol invariants

1. NXN balances never go negative.
2. Settlement legs apply atomically or not at all.
3. Attestations require valid signatures and ATTESTOR role.
4. Settlement against an oracle feed requires quorum + non-expired report.
5. Protocolguard pause blocks new transitions for paused modules without mutating history.
6. Indexer is derived state only.
