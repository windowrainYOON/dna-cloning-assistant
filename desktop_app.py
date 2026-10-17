#!/usr/bin/env python3
"""Entry point for the packaged macOS app: open the window, nothing else."""

import sys

from app.gui import main

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
