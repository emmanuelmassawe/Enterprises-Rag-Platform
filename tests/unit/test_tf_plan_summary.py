import pytest

from scripts.tf_plan_summary import create_summary


def test_summary_contains_only_safe_run_metadata() -> None:
    log = """
    # module.database.render_postgres.platform[\"staging\"] will be updated
    password = \"synthetic-private-value\"
    Plan: 1 to add, 2 to change, 0 to destroy.
    View this run in a browser: https://app.terraform.io/app/example/platform/runs/run-Abc123
    """

    summary, run_id, has_changes = create_summary(log, "deadbeef")

    assert run_id == "run-Abc123"
    assert has_changes is True
    assert "add=1, change=2, destroy=0" in summary
    assert "synthetic-private-value" not in summary
    assert "render_postgres" not in summary


def test_no_change_plan_does_not_request_apply() -> None:
    log = """
    No changes. Your infrastructure matches the configuration.
    View this run in a browser: https://app.terraform.io/app/example/platform/runs/run-Zero9
    """

    summary, run_id, has_changes = create_summary(log, "deadbeef")

    assert run_id == "run-Zero9"
    assert has_changes is False
    assert "add=0, change=0, destroy=0" in summary


@pytest.mark.parametrize(
    "log",
    (
        "Plan: 1 to add, 0 to change, 0 to destroy.",
        "View this run in a browser: https://app.terraform.io/app/example/platform/runs/run-X\n",
    ),
)
def test_unrecognized_or_incomplete_output_fails_closed(log: str) -> None:
    with pytest.raises(ValueError):
        create_summary(log, "deadbeef")
