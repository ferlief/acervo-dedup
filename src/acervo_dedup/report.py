"""Relatorio JSON: duplicate_groups, espaco recuperavel, representante e
motivo de cada grupo (README, secao "Saida").

E' o artefato de GRAO DE ARQUIVO FISICO (tem caminho). A tabela
'duplicatas' e' o artefato de GRAO DE CONTEUDO (sha256) - registra a
decisao para consumo pelos outros produtos da suite (acervo-sort). O
comando 'isolar' le ESTE relatorio, porque so' ele sabe quais caminhos
fisicos mover; ver CLAUDE.md para o porque dessa divisao.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .models import GrupoDuplicata


def construir_relatorio(
    grupos: list[GrupoDuplicata],
    raizes: list[Path],
    erros: list[tuple[str, str]],
) -> dict:
    duplicate_groups = []
    bytes_recuperaveis_total = 0
    for g in grupos:
        rep = g.representante
        candidatos = g.candidatos_quarentena
        bytes_grupo = g.bytes_recuperaveis
        bytes_recuperaveis_total += bytes_grupo
        duplicate_groups.append(
            {
                "grupo_id": g.grupo_id,
                "metodo": g.metodo,
                "representante": {
                    "sha256": rep.sha256,
                    "caminho": rep.caminho,
                    "tamanho": rep.tamanho,
                    "mtime": rep.mtime,
                    "motivo": rep.motivo,
                },
                "candidatos_quarentena": [
                    {
                        "sha256": m.sha256,
                        "caminho": m.caminho,
                        "tamanho": m.tamanho,
                        "mtime": m.mtime,
                        "distancia": m.distancia,
                        "motivo": m.motivo,
                    }
                    for m in candidatos
                ],
                "bytes_recuperaveis": bytes_grupo,
            }
        )

    grupos_exatos = sum(1 for g in grupos if g.metodo == "exato")
    grupos_perceptuais = sum(1 for g in grupos if g.metodo == "perceptual")
    arquivos_propostos = sum(len(g.candidatos_quarentena) for g in grupos)

    return {
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "raizes_varridas": [str(r) for r in raizes],
        "duplicate_groups": duplicate_groups,
        "resumo": {
            "grupos_exatos": grupos_exatos,
            "grupos_perceptuais": grupos_perceptuais,
            "arquivos_propostos_para_quarentena": arquivos_propostos,
            "bytes_recuperaveis_total": bytes_recuperaveis_total,
        },
        "erros": [{"caminho": c, "mensagem": m} for c, m in erros],
    }


def salvar_relatorio(relatorio: dict, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
