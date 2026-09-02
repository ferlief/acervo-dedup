"""Relatorio JSON: duplicate_groups, espaco recuperavel, representante e
motivo de cada grupo (README, secao "Saida").

E' o artefato de GRAO DE ARQUIVO FISICO (tem caminho). A tabela
'duplicatas' e' o artefato de GRAO DE CONTEUDO (sha256) - registra a
decisao para consumo pelos outros produtos da suite (acervo-sort). O
comando 'isolar' le ESTE relatorio, porque so' ele sabe quais caminhos
fisicos mover; ver CLAUDE.md para o porque dessa divisao.

DOIS DESTINOS, decididos aqui e gravados no relatorio (o 'isolar' so'
obedece; nao reclassifica nada):

  exato      -> 'quarentena'  Os bytes sao literalmente identicos. Nao ha'
                              juizo possivel, nao ha' falso positivo
                              possivel: ou o SHA-256 bate ou nao bate.
  perceptual -> 'revisao'     A decisao veio de SEMELHANCA, que erra. Numa
                              medicao real em _PESSOAS_MANTER, 4 de 11
                              candidatos perceptuais eram uma RAJADA de
                              fotos distintas (mesma pose, instantes e
                              enquadramentos diferentes), nao copias - e
                              isolar rajada numa pasta de referencia facial
                              destroi exatamente a variacao de angulo que
                              da' valor a pasta.

A separacao e' ESTRUTURAL de proposito. A alternativa seria apertar o
limiar de distancia ate' a rajada sair, mas a rajada media distancia 2 -
dentro de qualquer corte defensavel. Limiar escolhido para fazer um caso
especifico passar e' chute; separar por grau de certeza e' garantia.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .models import GrupoDuplicata

QUARENTENA = "quarentena"
REVISAO = "revisao"


def destino_de(metodo: str) -> str:
    """Grau de certeza -> destino. Unica fonte da verdade dessa regra; o
    resultado vai gravado no relatorio, e 'isolar' so' obedece."""
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
