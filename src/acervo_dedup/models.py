"""Types shared by the exact pass, the perceptual pass and the report."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class MembroGrupo:
    sha256: str
    caminho: str
    tamanho: int
    mtime: float | None
    e_representante: bool
    distancia: float | None  # None when exact; Hamming to the representative when perceptual
    motivo: str  # why it stayed (representative) or why it was proposed for quarantine


@dataclasses.dataclass
class GrupoDuplicata:
    grupo_id: str
    metodo: str  # 'exato' | 'perceptual'
    membros: list[MembroGrupo]

    @property
    def representante(self) -> MembroGrupo:
        for m in self.membros:
            if m.e_representante:
                return m
        raise ValueError(f"grupo {self.grupo_id} sem representante")

    @property
    def candidatos_quarentena(self) -> list[MembroGrupo]:
        return [m for m in self.membros if not m.e_representante]

    @property
    def bytes_recuperaveis(self) -> int:
        return sum(m.tamanho for m in self.candidatos_quarentena)
