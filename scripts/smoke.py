"""Local HTTP smoke check for the liveness and readiness routes."""

import time
from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    """Return nonzero unless the local API reports healthy and ready."""
    for path in ("healthz", "readyz"):
        deadline = time.monotonic() + 10
        while True:
            try:
                with urlopen(f"http://127.0.0.1:8000/{path}", timeout=3) as response:
                    if response.status == 200:
                        break
            except (TimeoutError, URLError, OSError):
                if time.monotonic() >= deadline:
                    return 1
            time.sleep(0.25)
            if time.monotonic() >= deadline:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
