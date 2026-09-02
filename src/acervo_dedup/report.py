"""JSON report: duplicate_groups, recoverable space, and the
representative plus its reason for every group (README, "Saida" section).

This is the PHYSICAL-FILE-GRAIN artifact (it carries paths). The
'duplicatas' table is the CONTENT-GRAIN artifact (sha256) - it records the
decision for the other products in the suite to consume (acervo-sort). The
'isolar' command reads THIS report, because only it knows which physical
paths to move; see CLAUDE.md for why the split exists.

TWO DESTINATIONS, decided here and written into the report ('isolar' only
obeys; it never reclassifies anything):

  exact      -> 'quarentena'  The bytes are literally identical. No
                              judgement is possible and no false positive
                              is possible: either the SHA-256 matches or it
                              does not.
  perceptual -> 'revisao'     The decision came from SIMILARITY, which gets
                              things wrong. In a real measurement over a
                              face-reference folder, 4 out of 11 perceptual
                              candidates were a BURST of distinct photos
                              (same pose, different instants and framings),
                              not copies - and isolating a burst out of a
                              face-reference folder destroys exactly the
                              angle variation that makes the folder useful.

The separation is STRUCTURAL on purpose. The alternative would be
tightening the distance threshold until the burst drops out, but the burst
averaged distance 2 - inside any defensible cut. A threshold picked to make
one specific case pass is a guess; splitting by degree of certainty is a
guarantee.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .models import GrupoDuplicata

QUARENTENA = "quarentena"
REVISAO = "revisao"


def destino_de(metodo: str) -> str:
    """Degree of certainty -> destination. The single source of truth for
    this rule; the result is written into the report and 'isolar' only
    obeys it."""
    return QUARENTENA if metodo == "exato" else REVISAO


def construir_relatorio(
    grupos: list[GrupoDuplicata],
    raizes: list[Path],
    erros: list[tuple[str, str]],
) -> dict:
    duplicate_groups = []
    bytes_recuperaveis_total = 0
    bytes_por_destino = {QUARENTENA: 0, REVISAO: 0}
    arquivos_por_destino = {QUARENTENA: 0, REVISAO: 0}

    for g in grupos:
        rep = g.representante
        candidatos = g.candidatos_quarentena
        bytes_grupo = g.bytes_recuperaveis
        bytes_recuperaveis_total += bytes_grupo
        destino = destino_de(g.metodo)
        bytes_por_destino[destino] += bytes_grupo
        arquivos_por_destino[destino] += len(candidatos)

        duplicate_groups.append(
            {
                "grupo_id": g.grupo_id,
                "metodo": g.metodo,
                "destino": destino,
                "representante": {
                    "sha256": rep.sha256,
                    "caminho": rep.caminho,
                    "tamanho": rep.tamanho,
                    "mtime": rep.mtime,
                    "motivo": rep.motivo,
                },
                "candidatos_isolamento": [
                    {
                        "sha256": m.sha256,
                        "caminho": m.caminho,
                        "tamanho": m.tamanho,
                        "mtime": m.mtime,
                        "distancia": m.distancia,
                        "motivo": m.motivo,
                        "destino": destino,
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
            "arquivos_propostos_isolamento": arquivos_propostos,
            "arquivos_para_quarentena": arquivos_por_destino[QUARENTENA],
            "arquivos_para_revisao": arquivos_por_destino[REVISAO],
            "bytes_recuperaveis_total": bytes_recuperaveis_total,
            "bytes_quarentena": bytes_por_destino[QUARENTENA],
            "bytes_revisao": bytes_por_destino[REVISAO],
        },
        "erros": [{"caminho": c, "mensagem": m} for c, m in erros],
    }


def salvar_relatorio(relatorio: dict, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
