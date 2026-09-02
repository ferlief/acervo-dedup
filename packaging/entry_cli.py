"""PyInstaller entry point for the console binary (acervo-dedup.exe).

Console subsystem on purpose: this is the binary the window drives as a
subprocess, and the live log in the interface is literally this process's
stdout. A windowed build has no stdout to pipe.
"""

import sys

from acervo_dedup.cli import main

if __name__ == "__main__":
    sys.exit(main())
