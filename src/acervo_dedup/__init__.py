"""acervo-dedup - redundancy detection for large personal archives.

Two passes (exact via SHA-256, perceptual via perceptual hash). Isolation
is always explicit and separate from detection. See README.md and
CLAUDE.md in this repository for the design and its invariants.
"""

__version__ = "0.1.0"
