from __future__ import annotations

import re


DISCLAIMER = (
    "Planning-only output for operational research. "
    "This is not legal, medical, or financial advice. "
    "Separate wellness content from any medical or cosmetic procedure recommendations "
    "and route regulated decisions to licensed professionals."
)

CLAIM_REPLACEMENTS = {
    r"\bcure\b": "support",
    r"\bdiagnose\b": "evaluate with licensed professionals",
    r"\btreat\b": "plan around",
    r"\bprescribe\b": "coordinate with licensed professionals on",
}

PROCEDURE_TERMS = ("injectable", "surgery", "laser resurfacing", "botox", "liposuction")


def apply_output_guardrails(content: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    safe_content = content

    for pattern, replacement in CLAIM_REPLACEMENTS.items():
        if re.search(pattern, safe_content, flags=re.IGNORECASE):
            flags.append(f"claim_adjusted:{pattern.strip(r'\\b')}")
            safe_content = re.sub(pattern, replacement, safe_content, flags=re.IGNORECASE)

    if any(term in safe_content.lower() for term in PROCEDURE_TERMS):
        flags.append("medical_procedure_boundary")

    if DISCLAIMER not in safe_content:
        safe_content = safe_content.rstrip() + f"\n\n---\n{DISCLAIMER}\n"

    return safe_content, flags
