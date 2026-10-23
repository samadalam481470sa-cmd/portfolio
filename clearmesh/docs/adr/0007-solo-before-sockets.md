# ADR 0007: Solo sequencer before sockets

Ship the full ledger on `SoloSequencer`, prove BFT in the deterministic simulator,
then attach P2P. Demo fallback is always solo.
