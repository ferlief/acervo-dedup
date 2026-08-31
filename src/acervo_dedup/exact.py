"""Passada 1: duplicatas exatas.

Politica de representante (mais especifica que o README - ver CLAUDE.md
do usuario / instrucao da tarefa): dentro de um grupo BYTE-IDENTICO (mesmo
SHA-256), o representante e' o de METADADO DE CRIACAO (mtime) MAIS ANTIGO;
os demais sao propostos para quarentena. Ninguem e' apagado por este
modulo - so' marcado.

Um grupo exato tem, por definicao, UM UNICO sha256 (e' a propria definicao
de "byte-identico"). O grupo_id usado e' o proprio sha256: deterministico
e idempotente entre execucoes.
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
        # representante: mtime mais antigo. Empate de mtime (raro, mas
        # possivel em copias feitas na mesma operacao de backup): desempata
        # por caminho, so' para ter uma escolha deterministica e estavel
        # entre execucoes.
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
