"""Check Markdown local links and fenced code blocks without network access."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
IGNORED = {".git", ".venv", ".terraform", "node_modules", ".next", "__pycache__"}


def markdown_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.md")
        if not any(part in IGNORED for part in path.relative_to(ROOT).parts)
    ]


def check_fences(source: Path, text: str) -> list[str]:
    errors: list[str] = []
    fences: list[tuple[str, int]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = FENCE.match(line)
        if not match:
            continue
        marker = match.group(1)
        if fences and marker[0] == fences[-1][0][0] and len(marker) >= len(fences[-1][0]):
            fences.pop()
        else:
            fences.append((marker, line_number))
    for _, line_number in fences:
        errors.append(f"{source.relative_to(ROOT)}:{line_number}: unclosed code fence")
    return errors


def check_links(source: Path, text: str) -> list[str]:
    errors: list[str] = []
    for match in LINK.finditer(text):
        destination = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
        parsed = urlsplit(destination)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = (source.parent / unquote(parsed.path)).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            errors.append(f"{source.relative_to(ROOT)}: link escapes repository: {destination}")
            continue
        if not target.exists():
            line_number = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{source.relative_to(ROOT)}:{line_number}: missing link target: {destination}"
            )
    return errors


def main() -> int:
    files = markdown_files()
    errors = [
        error
        for source in files
        for error in check_fences(source, source.read_text(encoding="utf-8"))
        + check_links(source, source.read_text(encoding="utf-8"))
    ]
    if errors:
        sys.stderr.write("Documentation checks failed:\n")
        sys.stderr.write("\n".join(errors) + "\n")
        return 1
    sys.stdout.write(f"Documentation checks passed for {len(files)} Markdown files.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
