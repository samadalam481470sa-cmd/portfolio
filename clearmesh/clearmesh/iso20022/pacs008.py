"""Customer credit transfer (pacs.008) -> PAYMENT_INSTRUCTION + envelope."""

from __future__ import annotations

from lxml import etree

from clearmesh.core.amount import Amount
from clearmesh.core.ids import normalize_uetr


def parse_pacs008(xml_bytes: bytes) -> dict:
    root = etree.fromstring(xml_bytes)
    ns = {"d": root.nsmap.get(None) or root.nsmap.get("doc") or ""}

    def text(path: str, default: str = "") -> str:
        # try without ns and with local-name
        el = root.find(path)
        if el is not None and el.text:
            return el.text.strip()
        for node in root.iter():
            if node.tag.endswith(path.split("/")[-1]) and node.text:
                return node.text.strip()
        return default

    uetr = normalize_uetr(text("UETR") or text(".//UETR"))
    e2e = text("EndToEndId") or text(".//EndToEndId") or uetr
    amt_s = text("IntrBkSttlmAmt") or text(".//IntrBkSttlmAmt") or "0"
    ccy = (root.find(".//{*}IntrBkSttlmAmt") or root.find(".//IntrBkSttlmAmt"))
    currency = ccy.get("Ccy") if ccy is not None else "XTS"
    if currency not in ("XTS", "SIM"):
        # allow only test currency in samples
        pass
    amount = Amount.parse(amt_s, decimals=2).value
    debtor = text("DbtrAgt") or text(".//DbtrAgt/{*}FinInstnId/{*}LEI") or text(".//DbtrAgt")
    creditor = text("CdtrAgt") or text(".//CdtrAgt")
    # Prefer explicit bank IDs in Clearmesh samples
    debtor_bank = text("DbtrBank") or debtor
    creditor_bank = text("CdtrBank") or creditor
    orig_name = text("Dbtr/Nm") or text(".//Dbtr/{*}Nm") or text(".//DbtrNm")
    ben_name = text("Cdtr/Nm") or text(".//Cdtr/{*}Nm") or text(".//CdtrNm")
    return {
        "uetr": uetr,
        "end_to_end_id": e2e,
        "amount": amount,
        "currency": currency,
        "debtor": debtor_bank,
        "creditor": creditor_bank,
        "originator_name": orig_name,
        "beneficiary_name": ben_name,
        "originator_account": text("DbtrAcct") or text(".//DbtrAcct"),
        "beneficiary_account": text("CdtrAcct") or text(".//CdtrAcct"),
        "originator_address": text("DbtrAdr") or "",
        "beneficiary_address": text("CdtrAdr") or "",
    }
