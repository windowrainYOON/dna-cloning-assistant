#!/usr/bin/env python3
"""Start the DNA cloning assistant.

    python3 run.py [file.dna] [--port 8765] [--no-browser]
"""

import argparse

from app import server


def main() -> None:
    ap = argparse.ArgumentParser(description="DNA cloning assistant (local web GUI)")
    ap.add_argument("dna", nargs="?", help="a .dna file to open at startup")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser")
    args = ap.parse_args()
    if args.dna:
        server.load(args.dna)
    server.serve(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
