"""Local HTTP smoke check for the liveness and readiness routes."""

from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    """Return nonzero unless the local API reports healthy and ready."""
    for path in ("healthz", "readyz"):
        try:
            with urlopen(f"http://127.0.0.1:8000/{path}", timeout=3) as response:
                if response.status != 200:
                    return 1
        except (TimeoutError, URLError):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

