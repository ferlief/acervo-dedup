"""Tipos compartilhados entre a passada exata, a perceptual e o relatorio."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class MembroGrupo:
    sha256: str
    caminho: str
    tamanho: int
    mtime: float | None
    e_representante: bool
    distancia: float | None  # None quando exato; Hamming ate' o representante quando perceptual
    motivo: str  # por que ficou (representante) ou por que foi proposto para quarentena


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
