# ADR 0001: Cosmos SDK + CometBFT foundation

## Decision
Use Cosmos SDK for the modular state machine and CometBFT for BFT consensus/P2P.

## Consequences
NEXUS custom finance lives in `chain/x/*`. Solo runtime accelerates module development; production networking uses CometBFT against pinned SDK versions.
