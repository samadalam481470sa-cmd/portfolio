#!/usr/bin/env python3
"""AST bans for nondeterminism in consensus paths.

Bans: float literals/calls, wall-clock time, random, datetime.now.
Sets/dicts may be used for membership, but iteration that affects state
must be sorted (enforced by review + property tests).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOTS = [
    "clearmesh/execution",
    "clearmesh/settlement",
    "clearmesh/compliance/policy.py",
    "clearmesh/ledger",
    "clearmesh/state",
    "clearmesh/consensus/core.py",
]


class DeterminismVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.errors: list[str] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, float):
            self.errors.append(f"{self.path}:{node.lineno}: float literal")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "float":
            self.errors.append(f"{self.path}:{node.lineno}: float()")
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"now", "utcnow", "time"}:
            if isinstance(node.func.value, ast.Name) and node.func.value.id in {
                "datetime",
                "date",
                "time",
            }:
                self.errors.append(f"{self.path}:{node.lineno}: wall-clock call")
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "random":
                self.errors.append(f"{self.path}:{node.lineno}: random.*")
            if node.func.value.id == "time" and node.func.attr in {"time", "time_ns", "monotonic"}:
                self.errors.append(f"{self.path}:{node.lineno}: time.*")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in {"random", "time"}:
                self.errors.append(f"{self.path}:{node.lineno}: import {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module in {"random", "time", "datetime"}:
            self.errors.append(f"{self.path}:{node.lineno}: from {node.module} import")
        self.generic_visit(node)


def iter_files(base: Path) -> list[Path]:
    out: list[Path] = []
    for rel in ROOTS:
        p = base / rel
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(p.rglob("*.py")))
    return out


def main() -> int:
    base = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    for path in iter_files(base):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        v = DeterminismVisitor(str(path.relative_to(base)))
        v.visit(tree)
        errors.extend(v.errors)
    for e in errors:
        print(e)
    if errors:
        print(f"{len(errors)} determinism lint errors", file=sys.stderr)
        return 1
    print("determinism lint OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
