"""Comando 'isolar': move para quarentena os arquivos propostos no
relatorio JSON. Comando EXPLICITO e SEPARADO de 'scan' - README e CLAUDE.md
sao categoricos: "o motor isola, nunca apaga" e a remocao (aqui, mover) e'
sempre um passo separado, explicito. 'scan' nunca chama isto sozinho.

Nada e' sobrescrito: colisao de destino ganha sufixo _dup1, _dup2... Falha
de I/O (arquivo bloqueado, sem permissao, ja movido por outra ferramenta)
vira registro de erro, nunca excecao fatal (mesma garantia do scan).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ResultadoIsolamento:
    movidos: list[tuple[str, str]] = field(default_factory=list)  # (origem, destino)
    ja_ausentes: list[str] = field(default_factory=list)
    erros: list[tuple[str, str]] = field(default_factory=list)
    bytes_movidos: int = 0


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


def isolar(relatorio: dict, quarentena_dir: Path, execute: bool) -> ResultadoIsolamento:
    raizes = [Path(r) for r in relatorio.get("raizes_varridas", [])]
    resultado = ResultadoIsolamento()
    reservados: set[str] = set()

    for grupo in relatorio.get("duplicate_groups", []):
        for candidato in grupo.get("candidatos_quarentena", []):
            origem = Path(candidato["caminho"])
            if not origem.exists():
                resultado.ja_ausentes.append(str(origem))
                continue

            relativo = _relativizar(origem, raizes)
            destino = _destino_unico(quarentena_dir, relativo, reservados)

            if execute:
                try:
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(origem), str(destino))
                except (OSError, PermissionError) as e:
                    resultado.erros.append((str(origem), str(e)))
                    continue

            resultado.movidos.append((str(origem), str(destino)))
            resultado.bytes_movidos += int(candidato.get("tamanho") or 0)

    return resultado
