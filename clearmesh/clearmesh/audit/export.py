"""Decrypt travel-rule envelopes for a height range (auditor key)."""

from __future__ import annotations

import json
from typing import Any

from clearmesh.compliance.travel_rule import open_travel_envelope
from clearmesh.crypto.envelope import Envelope, WrappedKey


def decrypt_envelopes(
    records: list[dict[str, Any]],
    chain_id: str,
    auditor_priv: bytes,
) -> list[dict[str, Any]]:
    out = []
    for rec in records:
        env_d = rec["envelope"]
        env = Envelope(
            ciphertext=bytes.fromhex(env_d["ciphertext"]),
            wrapped_keys=tuple(
                WrappedKey(bytes.fromhex(w["kid"]), bytes.fromhex(w["sealed"]))
                for w in env_d["wrapped_keys"]
            ),
            commitment=bytes.fromhex(env_d["commitment"]),
        )
        try:
            pt = open_travel_envelope(env, chain_id, rec["uetr"], auditor_priv)
            out.append({"uetr": rec["uetr"], "plaintext": json.loads(pt.decode("utf-8"))})
        except Exception as exc:  # noqa: BLE001
            out.append({"uetr": rec["uetr"], "error": str(exc)})
    return out
