"""Command line entrypoint."""

from __future__ import annotations

from .config import Config
from .server import run_blocking


def main() -> None:
    """Run the standalone AFV server."""

    run_blocking(Config.from_env())


if __name__ == "__main__":
    main()
