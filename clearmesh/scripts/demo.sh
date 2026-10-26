#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${OUT:-$ROOT/testnet}"
RPC="${RPC:-http://127.0.0.1:26657}"

clearmesh testnet --out "$OUT"
# start node in background if not up
if ! curl -sf "$RPC/v1/status" >/dev/null 2>&1; then
  clearmesh node start --config "$OUT/node.toml" --password testnet &
  PID=$!
  trap 'kill $PID 2>/dev/null || true' EXIT
  for i in $(seq 1 60); do
    curl -sf "$RPC/v1/status" >/dev/null && break
    sleep 0.5
  done
fi

clearmesh publish-sanctions --keys-dir "$OUT/keys" --rpc "$RPC"
clearmesh issue --to BANKA --asset SIM --amount 100.00 --key "$OUT/keys/SA_ops.key" --rpc "$RPC"
clearmesh issue --to BANKB --asset SIM --amount 100.00 --key "$OUT/keys/SA_ops.key" --rpc "$RPC"
clearmesh issue --to BANKC --asset SIM --amount 100.00 --key "$OUT/keys/SA_ops.key" --rpc "$RPC"
clearmesh issue --to BANKD --asset SIM --amount 50.00 --key "$OUT/keys/SA_ops.key" --rpc "$RPC"

# Interbank circle for gridlock (no travel-rule)
clearmesh pay --from BANKA --to BANKB --amount 500.00 --interbank --keys-dir "$OUT/keys" --rpc "$RPC"
clearmesh pay --from BANKB --to BANKC --amount 500.00 --interbank --keys-dir "$OUT/keys" --rpc "$RPC"
clearmesh pay --from BANKC --to BANKA --amount 500.00 --interbank --keys-dir "$OUT/keys" --rpc "$RPC"
clearmesh pay --from BANKD --to BANKA --amount 300.00 --interbank --keys-dir "$OUT/keys" --rpc "$RPC"

# Advance blocks for netting interval
for i in $(seq 1 8); do
  sleep 0.6
done

curl -sf "$RPC/v1/invariants" | tee /tmp/clearmesh_inv.json
python - <<'PY'
import json
inv=json.load(open("/tmp/clearmesh_inv.json"))
assert inv["ok"], inv
print("demo invariants OK")
PY
