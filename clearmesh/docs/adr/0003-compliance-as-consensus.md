# ADR 0003: Compliance as a consensus rule

Maker-checker, sanctions attestations, and travel-rule envelopes are checked inside
`apply_block`. A rogue proposer cannot settle an unscreened CUSTOMER payment:
honest validators prevote nil when re-execution / validity fails.
