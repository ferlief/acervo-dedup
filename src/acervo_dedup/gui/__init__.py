"""acervo-dedup local graphical interface.

PRESENTATION layer. It holds no detection rule, no representative choice
and no destination policy: it shells out to the CLI and draws whatever the
CLI prints. Replacing this whole folder would not change a single bit of
the engine's result.
"""

from .desktop import abrir_janela
from .server import servir

__all__ = ["abrir_janela", "servir"]
