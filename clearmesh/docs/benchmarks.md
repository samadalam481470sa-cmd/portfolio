# Benchmarks

Placeholder measurements from local solo sequencer runs. Re-run with `tools/loadgen.py`.

| Setup | TPS (RPC status poll) | Notes |
|---|---|---|
| Solo sequencer, 1 node | ~few hundred tx/s target | Settlement path dominates |
| Netting 1k queued units | see CI property tests | Heuristic O(U²·L) |

Fedwire-scale average load is ~10 payments/s; throughput is not the product bottleneck — determinism and compliance rules are.
