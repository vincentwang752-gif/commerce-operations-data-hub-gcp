#!/usr/bin/env python3
"""Fail CI when ad-sync source code contains common production mutation calls."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "services" / "ad-platform-sync"
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go"}

FORBIDDEN_PATTERNS = {
    "Google Ads mutate call": re.compile(r"\bmutate(?:_|\s*\()", re.IGNORECASE),
    "Google Ads click/call conversion upload": re.compile(
        r"upload_(?:click|call)_conversions", re.IGNORECASE
    ),
    "Google Ads offline user data job": re.compile(
        r"offline_user_data_job|customer_match", re.IGNORECASE
    ),
    "Meta Graph write call": re.compile(
        r"(?:requests?|client|session)\s*\.\s*(?:post|put|patch|delete)\s*\([^\n]*(?:graph\.facebook|/act_)",
        re.IGNORECASE,
    ),
}


def main() -> int:
    violations: list[str] = []
    if not SOURCE_ROOT.exists():
        return 0

    for path in SOURCE_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in FORBIDDEN_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{path.relative_to(ROOT)}:{line}: {label}")

    if violations:
        print("Ad sync must remain read-only. Forbidden operations found:")
        print("\n".join(f"- {item}" for item in violations))
        return 1

    print("Ad sync read-only policy check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

