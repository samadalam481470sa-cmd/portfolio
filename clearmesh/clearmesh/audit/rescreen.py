"""Re-screen decrypted envelopes against referenced list version; flag negligence."""

from __future__ import annotations

from clearmesh.compliance.sanctions_list import SanctionsEntry
from clearmesh.compliance.screening_service import ScreenResult, score_name


def rescreen(
    decrypted: list[dict],
    entries: list[SanctionsEntry],
    attested_clear_ueters: set[str],
) -> list[dict]:
    flags = []
    for row in decrypted:
        if "plaintext" not in row:
            continue
        names = [
            row["plaintext"].get("Originator", {}).get("name", ""),
            row["plaintext"].get("Beneficiary", {}).get("name", ""),
        ]
        for name in names:
            if not name:
                continue
            outcome = score_name(name, entries)
            if outcome.result == ScreenResult.HIT and row["uetr"] in attested_clear_ueters:
                flags.append(
                    {
                        "uetr": row["uetr"],
                        "name": name,
                        "score": outcome.score,
                        "flag": "NEGLIGENT_CLEAR_ATTESTATION",
                    }
                )
    return flags
