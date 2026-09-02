"""Pass 1: exact duplicates.

Representative policy (more specific than the README): inside a
BYTE-IDENTICAL group (same SHA-256), the representative is the one with
the OLDEST CREATION METADATA (mtime); the others are proposed for
quarantine. Nothing is deleted by this module - only marked.

An exact group has, by definition, a SINGLE sha256 (that is precisely what
"byte-identical" means). The grupo_id used is that same sha256:
deterministic and idempotent across runs.
"""

from __future__ import annotations

from collections import defaultdict

from .models import GrupoDuplicata, MembroGrupo
from .scanner import ArquivoFisico


def agrupar_exatas(arquivos: list[ArquivoFisico]) -> list[GrupoDuplicata]:
    por_hash: dict[str, list[ArquivoFisico]] = defaultdict(list)
    for a in arquivos:
        if a.sha256:
            por_hash[a.sha256].append(a)

    grupos: list[GrupoDuplicata] = []
    for sha256, membros_fisicos in por_hash.items():
        if len(membros_fisicos) < 2:
            continue
        # Representative: oldest mtime. An mtime tie (rare, but possible
        # for copies produced by the same backup operation) breaks by path,
        # only so the choice stays deterministic and stable across runs.
        ordenados = sorted(membros_fisicos, key=lambda a: (a.mtime, a.caminho))
        representante_fisico = ordenados[0]

        membros = []
        for i, af in enumerate(ordenados):
            e_repr = i == 0
            membros.append(
                MembroGrupo(
                    sha256=sha256,
                    caminho=af.caminho,
                    tamanho=af.tamanho,
                    mtime=af.mtime,
                    e_representante=e_repr,
                    distancia=None,
                    motivo=(
                        "metadado_criacao_mais_antigo"
                        if e_repr
                        else "copia_byte_identica_do_representante"
                    ),
                )
            )
        grupos.append(GrupoDuplicata(grupo_id=sha256, metodo="exato", membros=membros))

    return grupos


def caminhos_ja_agrupados(grupos: list[GrupoDuplicata]) -> set[str]:
    return {m.caminho for g in grupos for m in g.membros}
