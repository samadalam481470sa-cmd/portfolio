# ADR 0005: Autonomous ops cannot rewrite history

Recovery automation may restart processes, rebuild indexes, and failover connectors. It must not mutate finalized blocks, app hashes, or consensus parameters without governance.
