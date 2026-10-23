"""ISO 20022-style reason codes and transaction rejection."""

from __future__ import annotations

from enum import StrEnum


class ReasonCode(StrEnum):
    AM04 = "AM04"  # Insufficient funds / expired unsettled
    RR04 = "RR04"  # Regulatory reason (sanctions / screening)
    AC06 = "AC06"  # Blocked account
    AB05 = "AB05"  # Timeout at beneficiary
    DUPL = "DUPL"  # Duplicate
    FF01 = "FF01"  # Invalid format
    AG01 = "AG01"  # Transaction forbidden
    AG02 = "AG02"  # Invalid bank operation
    BE05 = "BE05"  # Unrecognised initiating party
    DS0H = "DS0H"  # Signer not allowed
    DS04 = "DS04"  # Order rejected (maker-checker)
    TM01 = "TM01"  # Invalid cut-off / TTL
    CH20 = "CH20"  # Decimals invalid
    MS03 = "MS03"  # Not specified reason agent
    NARR = "NARR"  # Narrative
    AC04 = "AC04"  # Closed account number (return)
    CANCELLED = "CANCELLED"
    OK = "OK"


class TxReject(Exception):
    """Raised when a transaction is invalid for inclusion."""

    def __init__(self, code: ReasonCode | str, message: str = "") -> None:
        self.code = ReasonCode(code) if not isinstance(code, ReasonCode) else code
        self.message = message
        super().__init__(f"{self.code}: {message}" if message else str(self.code))
