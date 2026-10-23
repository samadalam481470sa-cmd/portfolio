"""FI-to-FI own-account transfer -> INTERBANK instruction fields."""

from __future__ import annotations

from lxml import etree

from clearmesh.core.amount import Amount
from clearmesh.core.ids import normalize_uetr


def parse_pacs009(xml_bytes: bytes) -> dict:
    root = etree.fromstring(xml_bytes)

    def find_text(local: str) -> str:
        for node in root.iter():
            if node.tag.endswith(local) and node.text:
                return node.text.strip()
        return ""

    uetr = normalize_uetr(find_text("UETR"))
    amt = Amount.parse(find_text("IntrBkSttlmAmt") or "0", decimals=2).value
    return {
        "uetr": uetr,
        "end_to_end_id": find_text("EndToEndId") or uetr,
        "amount": amt,
        "debtor": find_text("DbtrBank") or find_text("InstgAgt"),
        "creditor": find_text("CdtrBank") or find_text("InstdAgt"),
        "kind": "INTERBANK",
    }
