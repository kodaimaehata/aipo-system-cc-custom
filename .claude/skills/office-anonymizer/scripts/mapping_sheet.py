"""Opt-in mapping-sheet emitter for office-anonymizer.

The anonymization mapping (original -> replacement) is itself re-identification
information. To keep that exposure surface small, the wrapper only writes the
mapping sheet when the caller passes an explicit absolute path; there is no
implicit default location inside ``target_folder``.

Every emitted sheet starts with a warning header and ends with a SHA-256 of its
own contents (minus the footer line) so tampering is detectable. The file is
chmod'd to 0o600 before the function returns.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


_WARNING_HEADER = (
    "<!-- WARNING: This file links original identifiers to their anonymized\n"
    "     replacements. It IS re-identification information. Keep access\n"
    "     restricted (this copy is written at permission 0600). Do not commit\n"
    "     to any shared repository. -->\n"
)


def emit_mapping_sheet(
    output_path: Path,
    *,
    entries: Iterable[Mapping],
    source_file: Path,
    run_id: str,
) -> Path:
    """Write the mapping sheet to ``output_path`` (must be absolute).

    ``entries`` is an iterable of mappings with keys:
      - ``category`` ("person_name" | "company_name" | "property_code" | ...)
      - ``original`` (str)
      - ``replacement`` (str)
      - ``occurrences`` (int, optional)
      - ``note`` (str, optional)
    """
    output_path = Path(output_path).expanduser()
    if not output_path.is_absolute():
        raise ValueError(
            "mapping sheet path must be absolute to avoid accidental in-tree emission"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    body_lines: list[str] = [
        _WARNING_HEADER.rstrip(),
        "",
        "# Anonymization Mapping",
        "",
        f"- source_file: `{source_file}`",
        f"- run_id: `{run_id}`",
        f"- emitted_at_utc: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Category | Original | Replacement | Occurrences | Note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        category = str(entry.get("category") or "")
        original = str(entry.get("original") or "")
        replacement = str(entry.get("replacement") or "")
        occurrences = entry.get("occurrences", "")
        note = str(entry.get("note") or "")
        body_lines.append(
            f"| {category} | `{original}` | `{replacement}` | {occurrences} | {note} |"
        )

    body_text = "\n".join(body_lines) + "\n"
    digest = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
    with output_path.open("w", encoding="utf-8") as fh:
        fh.write(body_text)
        fh.write(f"\n<!-- sha256:{digest} -->\n")

    try:
        os.chmod(output_path, 0o600)
    except PermissionError:
        pass
    return output_path
