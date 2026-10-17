#!/usr/bin/env python3
"""Start the DNA cloning assistant.

    python3 run.py [file.dna]

A tkinter desktop app — standard library only, no browser engine involved.
"""

import argparse

from app.gui import main


def cli() -> None:
    ap = argparse.ArgumentParser(description="DNA cloning assistant")
    ap.add_argument("dna", nargs="?", help="a .dna file to open at startup")
    args = ap.parse_args()
    main(args.dna)


if __name__ == "__main__":
    cli()
