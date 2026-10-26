#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "NEXUS localnet scaffold"
echo "1) go test ./..."
go test ./...
echo "2) For multi-validator CometBFT, pin cosmos-sdk/cometbft and follow docs/BLUEPRINT.md §8."
echo "3) Solo demo: go run ./chain/cmd/nexusd solo"
