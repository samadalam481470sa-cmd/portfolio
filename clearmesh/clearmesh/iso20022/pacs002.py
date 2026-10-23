"""Status report from receipts."""

from __future__ import annotations

STATUS_MAP = {
    "AWAITING_BENEFICIARY_SCREEN": "PDNG",
    "QUEUED": "ACSP",
    "SETTLED": "ACSC",
    "REJECTED_BENEFICIARY": "RJCT",
    "BENEFICIARY_TIMEOUT": "RJCT",
    "CANCELLED": "RJCT",
    "EXPIRED": "RJCT",
}


def from_instruction(instr: dict) -> dict:
    st = instr.get("status", "")
    return {
        "uetr": instr.get("uetr"),
        "tx_sts": STATUS_MAP.get(st, "PDNG"),
        "rsn": instr.get("reason_code", ""),
        "additional": st,
    }


def to_xml(report: dict) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Document xmlns=\"urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10\">"
        f"<TxInfAndSts><OrgnlUETR>{report['uetr']}</OrgnlUETR>"
        f"<TxSts>{report['tx_sts']}</TxSts>"
        f"<StsRsnInf><Rsn><Cd>{report.get('rsn','')}</Cd></Rsn></StsRsnInf>"
        "</TxInfAndSts></Document>\n"
    )
