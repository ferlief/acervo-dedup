"""Comando 'isolar': move os arquivos propostos no relatorio JSON. Comando
EXPLICITO e SEPARADO de 'scan' - README e CLAUDE.md sao categoricos: "o
motor isola, nunca apaga" e a remocao (aqui, mover) e' sempre um passo
separado, explicito. 'scan' nunca chama isto sozinho.

DOIS DESTINOS, ja decididos pelo relatorio (ver report.py). Este modulo
NAO reclassifica: le o campo 'destino' de cada candidato e obedece.

  quarentena  copia byte-identica. Descarte seguro.
  revisao     parecida, nao identica. Pode ser foto unica - fila de decisao
              humana, nunca descarte automatico.

Nada e' sobrescrito: colisao de destino ganha sufixo _dup1, _dup2... Falha
de I/O (arquivo bloqueado, sem permissao, ja movido por outra ferramenta)
vira registro de erro, nunca excecao fatal (mesma garantia do scan).
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
    """'candidatos_isolamento' e' o nome atual; 'candidatos_quarentena' era o
    nome quando havia um destino so'. Aceitar os dois evita que um relatorio
    gerado antes desta mudanca falhe silenciosamente (devolvendo lista
    vazia, isto e', "nada a mover")."""
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

    somente: se dado, move so' essa classe. E' o que permite esvaziar a
    quarentena (descarte seguro) sem tocar na fila de revisao."""
    raizes = [Path(r) for r in relatorio.get("raizes_varridas", [])]
    resultado = ResultadoIsolamento()
    reservados: set[str] = set()

    for grupo in relatorio.get("duplicate_groups", []):
        # relatorio antigo (um destino so'): tudo que era candidato era
        # quarentena, por definicao de quando foi gerado.
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
