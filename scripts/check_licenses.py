#!/usr/bin/env python3
"""Report the license of every installed distribution, from its real metadata.

Exit status: 0 when every license is permissive or reviewed, 1 otherwise.
"""

import importlib.metadata as metadata
import re
import sys

PERMISSIVE = re.compile(
    r"\b(MIT|BSD|Apache|ISC|PSF|Python Software Foundation|Zlib|Unlicense|0BSD)\b",
    re.IGNORECASE,
)
COPYLEFT = re.compile(r"\b(A?GPL|LGPL|MPL|EPL|CDDL|SSPL)\b", re.IGNORECASE)

# Non-permissive licenses reviewed and recorded in ADR-0001.
# certifi: development dependency only, never in the runtime image.
REVIEWED = {"certifi", "psycopg", "psycopg-binary"}


def license_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier", [])
        if c.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    return (meta.get("License") or "").strip().splitlines()[0] if meta.get("License") else ""


def classify(name: str, license_text: str) -> str:
    if not license_text:
        return "MISSING"
    if COPYLEFT.search(license_text):
        return "REVIEWED" if name in REVIEWED else "REVIEW-NEEDED"
    return "PERMISSIVE" if PERMISSIVE.search(license_text) else "UNKNOWN"


def main() -> int:
    failed = False
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"].lower().replace("_", "-")
        license_text = license_of(dist)
        verdict = classify(name, license_text)
        failed = failed or verdict not in {"PERMISSIVE", "REVIEWED"}
        print(f"{verdict:14} {name}=={dist.version}  [{license_text or '-'}]")

        # Wheel-bundled shared libraries have no metadata of their own.
        bundled = sorted(
            {str(f).split("/")[-1] for f in dist.files or [] if ".libs/" in str(f)}
        )
        if bundled:
            print(f"{'':14} bundled: {', '.join(bundled)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
