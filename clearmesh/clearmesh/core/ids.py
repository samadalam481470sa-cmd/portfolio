"""Identifier validation for participants, LEIs, UETRs, keys, assets."""

from __future__ import annotations

import re
import uuid

ParticipantId = str
AssetId = str
KeyId = bytes
LEI = str
UETR = str

_PART_RE = re.compile(r"^[A-Z0-9]{3,11}$|^sys:issuance:[A-Z0-9]+$")
_ASSET_RE = re.compile(r"^[A-Z0-9]{2,12}$")
_LEI_RE = re.compile(r"^[A-Z0-9]{20}$")


class IdError(ValueError):
    pass


def validate_participant_id(pid: str) -> ParticipantId:
    if not isinstance(pid, str) or not _PART_RE.match(pid):
        raise IdError(f"invalid ParticipantId: {pid!r}")
    return pid


def validate_asset_id(aid: str) -> AssetId:
    if not isinstance(aid, str) or not _ASSET_RE.match(aid):
        raise IdError(f"invalid AssetId: {aid!r}")
    return aid


def normalize_uetr(uetr: str, *, reject_upper: bool = False) -> UETR:
    """Normalize UETR to lowercase UUIDv4. Reject uppercase if reject_upper."""
    if not isinstance(uetr, str):
        raise IdError("UETR must be str")
    if reject_upper and any(c.isupper() for c in uetr):
        raise IdError("UETR must be lowercase")
    low = uetr.lower()
    try:
        u = uuid.UUID(low)
    except ValueError as exc:
        raise IdError("invalid UETR") from exc
    if u.version != 4:
        raise IdError("UETR must be UUIDv4")
    return str(u)


def validate_key_id(kid: bytes) -> KeyId:
    if not isinstance(kid, (bytes, bytearray)) or len(kid) != 20:
        raise IdError("KeyId must be 20 bytes")
    return bytes(kid)


def _iso17442_mod97(lei: str) -> bool:
    """ISO 17442 check: convert letters A=10..Z=35, append 00, mod 97 == 1."""
    expanded = []
    for ch in lei:
        if ch.isdigit():
            expanded.append(ch)
        else:
            expanded.append(str(ord(ch) - 55))
    num = int("".join(expanded) + "00")
    return num % 97 == 1


def validate_lei(lei: str, *, check_mod97: bool = True) -> LEI:
    if not isinstance(lei, str) or not _LEI_RE.match(lei):
        raise IdError(f"invalid LEI length/charset: {lei!r}")
    if check_mod97 and not _iso17442_mod97(lei):
        raise IdError(f"LEI fails ISO 17442 mod-97: {lei!r}")
    return lei
