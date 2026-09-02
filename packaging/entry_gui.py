"""PyInstaller entry point for the windowed binary (acervo-dedup-gui.exe).

Windowed subsystem: double-clicking it must not flash a console. With no
arguments the CLI opens the interface, which is exactly what a double-click
should do.
"""

import sys

from acervo_dedup.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["gui"]))
