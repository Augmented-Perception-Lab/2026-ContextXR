#!/usr/bin/env python3
"""Regenerate the paper's Figure 4, Table 1 and Table 2 from the LLM cache (no API key needed).

    python scripts/reproduce_paper.py [--out runs/paper]

See contextxr/reproduce.py for the expected values and tolerances.
"""

import sys

from contextxr.reproduce import main

if __name__ == "__main__":
    sys.exit(main())
