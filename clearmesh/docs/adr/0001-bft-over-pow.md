# ADR 0001: BFT over proof of work

## Decision

Use Tendermint-style BFT with a fixed validator set (4 nodes, f=1).

## Rationale

Wholesale settlement needs deterministic finality (PFMI Principle 8) and no reorgs.
Halting under asynchrony/partition is safer for money than probabilistic forks.
