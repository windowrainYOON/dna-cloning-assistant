#!/usr/bin/env python3
"""Entry point for the packaged macOS app.

Picks a free port, starts the local server on a background thread and shows
the UI in a native window (WKWebView). Without that bridge it falls back to
the browser, so this file also works as a plain `python3 desktop_app.py`.
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
    server.run_app("127.0.0.1", free_port(), prefer_window=True)
