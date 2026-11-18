"""Create a public-safe summary for an HCP Terraform saved plan."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

RUN_URL = re.compile(
    r"https://app\.terraform\.io/app/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/runs/(run-[A-Za-z0-9]+)"
)
PLAN_COUNTS = re.compile(
    r"Plan: (?P<add>\d+) to add, (?P<change>\d+) to change, (?P<destroy>\d+) to destroy\."
)


def create_summary(log: str, commit: str) -> tuple[str, str, bool]:
    """Return a redacted summary, the saved run ID, and whether changes exist."""
    run_ids = RUN_URL.findall(log)
    if not run_ids:
        raise ValueError("Terraform output did not contain an HCP saved-plan run URL")

    counts = PLAN_COUNTS.findall(log)
    if counts:
        add, change, destroy = (int(value) for value in counts[-1])
    elif "No changes." in log:
        add = change = destroy = 0
    else:
        raise ValueError("Terraform output did not contain a recognized plan summary")

    has_changes = add + change + destroy > 0
    summary = "\n".join(
        (
            "Staging Terraform saved plan",
            f"Commit: {commit}",
            f"HCP Terraform run: {run_ids[-1]}",
            f"Changes: add={add}, change={change}, destroy={destroy}",
            f"Apply required: {'yes' if has_changes else 'no'}",
            "",
        )
    )
    return summary, run_ids[-1], has_changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--github-output", required=True, type=Path)
    args = parser.parse_args()

    summary, run_id, has_changes = create_summary(args.log.read_text(), args.commit)
    args.summary.write_text(summary)
    with args.github_output.open("a") as output:
        output.write(f"plan_run_id={run_id}\n")
        output.write(f"has_changes={'true' if has_changes else 'false'}\n")


if __name__ == "__main__":
    main()
