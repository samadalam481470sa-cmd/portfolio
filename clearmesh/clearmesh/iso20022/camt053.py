"""End-of-day statement (camt.053-style)."""

from __future__ import annotations

from xml.sax.saxutils import escape


def build_statement(pid: str, entries: list[dict], opening: int, closing: int) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">',
        f"<Stmt><Acct><Id>{escape(pid)}</Id></Acct>",
        f"<Bal><Tp>OPBD</Tp><Amt Ccy=\"XTS\">{opening}</Amt></Bal>",
        f"<Bal><Tp>CLBD</Tp><Amt Ccy=\"XTS\">{closing}</Amt></Bal>",
    ]
    for e in entries:
        lines.append(
            "<Ntry>"
            f"<Amt Ccy=\"XTS\">{e['amount']}</Amt>"
            f"<CdtDbtInd>{e['cdi']}</CdtDbtInd>"
            f"<Sts>{escape(e.get('status',''))}</Sts>"
            f"<AcctSvcrRef>{escape(e.get('ref',''))}</AcctSvcrRef>"
            "</Ntry>"
        )
    lines.append("</Stmt></Document>\n")
    return "".join(lines)
