#!/usr/bin/env python3
"""Entry point for the packaged macOS app.

Picks a free port, starts the local server and opens the browser. Running
this file directly is the same as `python3 run.py` without a file argument.
"""

import socket

from app import server


def free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    return 0


if __name__ == "__main__":
    server.serve("127.0.0.1", free_port(), open_browser=True)
