# Node recovery

Allowed:
- Restart crashed **non-signing** processes
- Remount volumes and resume from last CometBFT/SDK state
- Rebuild indexer from chain RPC

Forbidden:
- Editing historical blocks / `app_hash`
- Replacing validator keys without ceremony
- Unpausing protocolguard without guardian/governance

Runbook: `systemctl restart nexusd` (see `deploy/systemd/`) after health checks.
