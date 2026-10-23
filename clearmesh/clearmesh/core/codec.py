"""Canonical CBOR encode/decode with strict re-encode checks."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum, IntEnum
from types import UnionType
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

import cbor2

T = TypeVar("T")

# Type tags for consensus types (must stay stable for golden vectors).
TYPE_TAGS: dict[str, int] = {
    "Sig": 1,
    "TxEnvelope": 2,
    "Envelope": 3,
    "WrappedKey": 4,
    "Attestation": 5,
    "PaymentInstruction": 6,
    "BlockHeader": 7,
    "Block": 8,
    "Proposal": 9,
    "Vote": 10,
    "CommitSig": 11,
    "Commit": 12,
    "Posting": 13,
    "Receipt": 14,
    "Participant": 15,
    "KeyRec": 16,
    "Account": 17,
    "Instruction": 18,
    "Leg": 19,
    "Group": 20,
    "Policy": 21,
    "SanctionsListMeta": 22,
    "NettingReport": 23,
    "AssetStat": 24,
    "RegisterParticipant": 25,
    "RotateKey": 26,
    "RevokeKey": 27,
    "SetPolicy": 28,
    "FreezeAccount": 29,
    "UnfreezeAccount": 30,
    "Issue": 31,
    "Redeem": 32,
    "PublishSanctionsList": 33,
    "BeneficiaryScreenResult": 34,
    "CancelInstruction": 35,
    "ReturnPayment": 36,
    "ProposeGroup": 37,
    "AffirmGroup": 38,
    "SetDebitCap": 39,
    "EvidenceEquivocation": 40,
    "AssetMeta": 41,
}


class CodecError(ValueError):
    """Raised when encoding/decoding fails or input is non-canonical."""


def _to_cborable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, str, bytes)):
        if isinstance(obj, float):
            raise CodecError("floats are forbidden in consensus types")
        if isinstance(obj, int) and not isinstance(obj, bool):
            if obj < -(2**63) or obj >= 2**63:
                raise CodecError("integer out of int64 range")
        return obj
    if isinstance(obj, float):
        raise CodecError("floats are forbidden in consensus types")
    if isinstance(obj, (IntEnum, Enum)):
        return int(obj) if isinstance(obj, IntEnum) else obj.value
    if isinstance(obj, tuple):
        return [_to_cborable(x) for x in obj]
    if isinstance(obj, list):
        # Allowed for signing digests and tagged arrays; consensus dataclasses use tuples.
        return [_to_cborable(x) for x in obj]
    if isinstance(obj, (dict, set)):
        raise CodecError("dicts/sets forbidden in consensus types")
    if is_dataclass(obj) and not isinstance(obj, type):
        name = type(obj).__name__
        if name not in TYPE_TAGS:
            raise CodecError(f"unknown consensus type: {name}")
        vals = [_to_cborable(getattr(obj, f.name)) for f in fields(obj)]
        return [TYPE_TAGS[name], *vals]
    raise CodecError(f"cannot encode type {type(obj)!r}")


def encode(obj: Any) -> bytes:
    """Encode a consensus object to canonical CBOR bytes."""
    payload = _to_cborable(obj)
    return cbor2.dumps(payload, canonical=True)


def _resolve_optional(annotation: Any) -> tuple[bool, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is None and not isinstance(annotation, UnionType) and args == ():
        return False, annotation
    if origin in (Union, UnionType) or isinstance(annotation, UnionType):
        args = get_args(annotation) if not args else args
        if type(None) in args:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return True, non_none[0]
    if args and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return True, non_none[0]
    return False, annotation


def _class_for_tag(tag: int) -> type[Any] | None:
    inv = {v: k for k, v in TYPE_TAGS.items()}
    name = inv.get(tag)
    if name is None:
        return None
    from clearmesh.types import block as block_mod
    from clearmesh.types import receipt as receipt_mod
    from clearmesh.types import records as records_mod
    from clearmesh.types import tx as tx_mod

    for mod in (tx_mod, block_mod, receipt_mod, records_mod):
        cls = getattr(mod, name, None)
        if cls is not None:
            return cls  # type: ignore[no-any-return]
    return None


def _from_cborable(cls: type[T], data: Any) -> T:
    # typing.Any → dispatch on type tag
    if cls is Any or str(cls) == "typing.Any":
        if isinstance(data, list) and data:
            tag_cls = _class_for_tag(data[0])
            if tag_cls is None:
                raise CodecError(f"unknown tag {data[0]}")
            return _from_cborable(tag_cls, data)  # type: ignore[return-value]
        raise CodecError("Any requires tagged array")

    if cls is type(None):  # noqa: E721
        if data is not None:
            raise CodecError("expected null")
        return None  # type: ignore[return-value]
    if cls is bool:
        if not isinstance(data, bool):
            raise CodecError("expected bool")
        return data  # type: ignore[return-value]
    if cls is int:
        if isinstance(data, bool) or not isinstance(data, int):
            raise CodecError("expected int")
        if data < -(2**63) or data >= 2**63:
            raise CodecError("integer out of int64 range")
        return data  # type: ignore[return-value]
    if cls is str:
        if not isinstance(data, str):
            raise CodecError("expected str")
        return data  # type: ignore[return-value]
    if cls is bytes:
        if not isinstance(data, (bytes, bytearray)):
            raise CodecError("expected bytes")
        return bytes(data)  # type: ignore[return-value]

    origin = get_origin(cls)
    if origin is tuple:
        args = get_args(cls)
        if not isinstance(data, list):
            raise CodecError("expected array for tuple")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_from_cborable(args[0], x) for x in data)  # type: ignore[return-value]
        if len(args) != len(data):
            raise CodecError("tuple arity mismatch")
        return tuple(_from_cborable(a, x) for a, x in zip(args, data, strict=True))  # type: ignore[return-value]

    if isinstance(cls, type) and issubclass(cls, IntEnum):
        if isinstance(data, bool) or not isinstance(data, int):
            raise CodecError("expected int for IntEnum")
        return cls(data)  # type: ignore[return-value]

    if is_dataclass(cls):
        if not isinstance(data, list) or not data:
            raise CodecError("expected tagged array")
        tag = data[0]
        expected = TYPE_TAGS.get(cls.__name__)
        if expected is None or tag != expected:
            raise CodecError(f"tag mismatch for {cls.__name__}: got {tag}")
        hints = get_type_hints(cls)
        flds = fields(cls)
        if len(data) - 1 != len(flds):
            raise CodecError(f"field count mismatch for {cls.__name__}")
        kwargs: dict[str, Any] = {}
        for f, raw in zip(flds, data[1:], strict=True):
            ann = hints.get(f.name, f.type)
            optional, inner = _resolve_optional(ann)
            if optional and raw is None:
                kwargs[f.name] = None
            else:
                kwargs[f.name] = _from_cborable(inner, raw)
        return cls(**kwargs)  # type: ignore[return-value]

    # Literal / Union handled loosely via value equality for strings
    args = get_args(cls)
    if args and all(isinstance(a, str) for a in args):
        if data not in args:
            raise CodecError(f"literal mismatch: {data!r}")
        return data  # type: ignore[return-value]

    raise CodecError(f"cannot decode into {cls!r}")


def decode(cls: type[T], data: bytes) -> T:
    """Decode CBOR into ``cls``, rejecting any non-canonical encoding."""
    if not isinstance(data, (bytes, bytearray)):
        raise CodecError("data must be bytes")
    try:
        raw = cbor2.loads(data)
    except Exception as exc:  # noqa: BLE001
        raise CodecError(f"cbor decode failed: {exc}") from exc
    obj = _from_cborable(cls, raw)
    reenc = encode(obj)
    if reenc != bytes(data):
        raise CodecError("non-canonical CBOR rejected")
    return obj


def decode_any(data: bytes) -> Any:
    """Decode tagged CBOR into the registered dataclass type."""
    try:
        raw = cbor2.loads(data)
    except Exception as exc:  # noqa: BLE001
        raise CodecError(f"cbor decode failed: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise CodecError("expected tagged array")
    tag = raw[0]
    inv = {v: k for k, v in TYPE_TAGS.items()}
    name = inv.get(tag)
    if name is None:
        raise CodecError(f"unknown tag {tag}")
    # Lazy import to avoid cycles
    from clearmesh import types as types_mod

    cls = getattr(types_mod, name, None)
    if cls is None:
        # Bodies live under tx
        from clearmesh.types import tx as tx_mod

        cls = getattr(tx_mod, name, None)
    if cls is None:
        from clearmesh.types import block as block_mod
        from clearmesh.types import receipt as receipt_mod
        from clearmesh.types import records as records_mod

        for mod in (block_mod, receipt_mod, records_mod, tx_mod):
            cls = getattr(mod, name, None)
            if cls is not None:
                break
    if cls is None:
        raise CodecError(f"no class for tag {name}")
    obj = decode(cls, data)
    return obj
