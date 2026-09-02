"""The 'isolar' command: moves the files proposed in the JSON report. It is
EXPLICIT and SEPARATE from 'scan' - README and CLAUDE.md are categorical:
the engine isolates, it never deletes, and removal (here, moving) is always
a separate, explicit step. 'scan' never calls this on its own.

TWO DESTINATIONS, already decided by the report (see report.py). This
module does NOT reclassify: it reads each candidate's 'destino' field and
obeys.

  quarentena  byte-identical copy. Safe discard.
  revisao     similar, not identical. May be a unique photo - a human
              decision queue, never an automatic discard.

Nothing is overwritten: a destination collision gets a _dup1, _dup2...
suffix. An I/O failure (locked file, no permission, already moved by
another tool) becomes an error record, never a fatal exception (the same
guarantee the scan gives).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

QUARENTENA = "quarentena"
REVISAO = "revisao"


@dataclass
class ResultadoIsolamento:
    movidos: list[tuple[str, str, str]] = field(default_factory=list)  # (origem, destino, classe)
    ja_ausentes: list[str] = field(default_factory=list)
    erros: list[tuple[str, str]] = field(default_factory=list)
    bytes_movidos: int = 0
    bytes_por_classe: dict[str, int] = field(default_factory=dict)
    contagem_por_classe: dict[str, int] = field(default_factory=dict)


def _relativizar(origem: Path, raizes: list[Path]) -> Path:
    for raiz in raizes:
        try:
            return origem.relative_to(raiz)
        except ValueError:
            continue
    return Path(origem.name)


def _destino_unico(base: Path, relativo: Path, reservados: set[str]) -> Path:
    dest = base / relativo
    if not dest.exists() and str(dest) not in reservados:
        reservados.add(str(dest))
        return dest
    stem, suf = dest.stem, dest.suffix
    i = 1
    while dest.exists() or str(dest) in reservados:
        dest = dest.with_name(f"{stem}_dup{i}{suf}")
        i += 1
    reservados.add(str(dest))
    return dest


def _candidatos_do_grupo(grupo: dict) -> list[dict]:
    """'candidatos_isolamento' is the current name; 'candidatos_quarentena'
    was the name back when there was a single destination. Accepting both
    keeps a report generated before that change from failing silently (by
    returning an empty list, that is, "nothing to move")."""
    if "candidatos_isolamento" in grupo:
        return grupo["candidatos_isolamento"]
    return grupo.get("candidatos_quarentena", [])


def isolar(
    relatorio: dict,
    destinos: dict[str, Path],
    execute: bool,
    somente: str | None = None,
) -> ResultadoIsolamento:
    """destinos: {'quarentena': Path, 'revisao': Path}.

    somente: when given, moves only that class. It is what allows emptying
    the quarantine (safe discard) without touching the review queue."""
    raizes = [Path(r) for r in relatorio.get("raizes_varridas", [])]
    resultado = ResultadoIsolamento()
    reservados: set[str] = set()

    for grupo in relatorio.get("duplicate_groups", []):
        # Legacy report (single destination): everything that was a
        # candidate was quarantine, by definition of when it was generated.
        destino_grupo = grupo.get("destino", QUARENTENA)
        for candidato in _candidatos_do_grupo(grupo):
            classe = candidato.get("destino", destino_grupo)
            if somente is not None and classe != somente:
                continue

            base = destinos.get(classe)
            if base is None:
                resultado.erros.append(
                    (candidato.get("caminho", "?"), f"destino desconhecido: {classe}")
                )
                continue

            origem = Path(candidato["caminho"])
            if not origem.exists():
                resultado.ja_ausentes.append(str(origem))
                continue

            relativo = _relativizar(origem, raizes)
            destino = _destino_unico(base, relativo, reservados)

            if execute:
                try:
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(origem), str(destino))
                except (OSError, PermissionError) as e:
                    resultado.erros.append((str(origem), str(e)))
                    continue

            tamanho = int(candidato.get("tamanho") or 0)
            resultado.movidos.append((str(origem), str(destino), classe))
            resultado.bytes_movidos += tamanho
            resultado.bytes_por_classe[classe] = (
                resultado.bytes_por_classe.get(classe, 0) + tamanho
            )
            resultado.contagem_por_classe[classe] = (
                resultado.contagem_por_classe.get(classe, 0) + 1
            )

    return resultado
