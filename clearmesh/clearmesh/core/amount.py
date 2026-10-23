"""Integer minor-unit amounts. Never use floats in consensus paths."""

from __future__ import annotations

MAX_AMOUNT = 2**63 - 1


class AmountError(ValueError):
    pass


class Amount:
    """Parse and validate amounts as integer minor units."""

    __slots__ = ("_value",)

    def __init__(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AmountError("amount must be int")
        if value <= 0 or value >= 2**63:
            raise AmountError("amount must satisfy 0 < a < 2**63")
        self._value = value

    @property
    def value(self) -> int:
        return self._value

    def __int__(self) -> int:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Amount):
            return self._value == other._value
        if isinstance(other, int) and not isinstance(other, bool):
            return self._value == other
        return NotImplemented

    def __repr__(self) -> str:
        return f"Amount({self._value})"

    @staticmethod
    def parse(text: str, decimals: int) -> Amount:
        """Parse a decimal string into minor units without float/Decimal."""
        if not isinstance(text, str):
            raise AmountError("amount text must be str")
        if decimals < 0 or decimals > 18:
            raise AmountError("invalid decimals")
        s = text.strip()
        if not s or s[0] == "-":
            raise AmountError("negative or empty amount")
        if s[0] == "+":
            s = s[1:]
        if "." in s:
            whole, frac = s.split(".", 1)
            if not whole.isdigit() and whole != "":
                raise AmountError("invalid whole part")
            if not frac.isdigit():
                raise AmountError("invalid fractional part")
            if len(frac) > decimals:
                raise AmountError("too many fractional digits (no rounding)")
            if len(frac) < decimals:
                frac = frac + ("0" * (decimals - len(frac)))
            whole = whole or "0"
        else:
            if not s.isdigit():
                raise AmountError("invalid amount")
            whole, frac = s, "0" * decimals
        # Combine
        digits = whole + frac
        if not digits.isdigit():
            raise AmountError("invalid amount digits")
        # Reject leading zeros that would still parse, but allow "0.xx"
        value = int(digits)
        if value <= 0 or value >= 2**63:
            raise AmountError("amount must satisfy 0 < a < 2**63")
        return Amount(value)

    @staticmethod
    def format(value: int, decimals: int) -> str:
        if value < 0:
            raise AmountError("negative")
        s = str(value).zfill(decimals + 1)
        if decimals == 0:
            return s
        return f"{s[:-decimals]}.{s[-decimals:]}"
