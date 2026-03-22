#!/usr/bin/env python
"""media.rip() entrypoint — reads config and launches uvicorn with the correct port."""

import os
import sys


def main():
    # Port from env var (MEDIARIP__SERVER__PORT) or default 8000
    port = os.environ.get("MEDIARIP__SERVER__PORT", "8000")
    host = os.environ.get("MEDIARIP__SERVER__HOST", "0.0.0.0")

    sys.exit(
        os.execvp(
            "python",
            [
                "python",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                host,
                "--port",
                port,
            ],
        )
    )


if __name__ == "__main__":
    main()
