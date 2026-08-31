"""Criterio de qualidade para o representante de um GRUPO PERCEPTUAL
(arquivos visualmente iguais, bytes diferentes - RAW vs JPEG, original vs
recompressao, mesma foto salva duas vezes).

Para um grupo EXATO (byte-identico) a qualidade e' irrelevante - os bytes
sao os mesmos arquivo; o desempate la' e' so' data de criacao (ver
exact.py). Este modulo so' importa na passada perceptual.

Criterio, do mais para o menos decisivo (mensuravel, nesta ordem):

  1) RAW sempre vence - RAW carrega mais informacao que qualquer derivado
     JPEG/PNG dele, por definicao (extensao do arquivo decide).
  2) Maior RESOLUCAO EFETIVA (largura x altura, de 'arquivos' - ja
     calculada por 'acervo', nao recalculada aqui).
  3) Em empate de resolucao, ORIGINAL vence EDICAO: a tag EXIF Software
     ('sinais' fonte=exif chave=software) e' comparada contra uma lista de
     nomes de editor conhecidos (config 'qualidade.editores'). Sem isto, a
     versao passada por um app de edicao pode ganhar so' por ser maior em
     bytes mesmo sendo, em resolucao, IGUAL ao original - foi exatamente a
     falha corrigida no prototipo irmao 'curadoria' (199 edicoes promovidas
     por cima do original num acervo real). Ausencia da tag (a maioria dos
     originais de camera) conta como "nao e' edicao".
  4) Em empate ainda de (1)-(3): MENOR SOMA DA TABELA DE QUANTIZACAO JPEG
     ('sinais' fonte=exif chave=quant) - soma menor implica menos perda de
     compressao (passo de quantizacao mais fino).

     Este criterio SO' entra em jogo quando TODOS os empatados em (1)-(3)
     tem o sinal medido. Um numero absoluto de quant nao e' comparavel com
     "ausencia de numero" - nao ha' um "quant neutro" que funcione como
     zero da escala (a soma nunca e' zero num JPEG real). Por isso, se
     algum empatado nao tem 'quant' (PNG, RAW, ou nao medido ainda), o
     criterio inteiro e' pulado para o grupo empatado, e o desempate cai
     direto no proximo passo - em vez de arriscar declarar "melhor" um
     arquivo so' porque o outro nao tem o dado.

  Em empate de TUDO isso, desempata por data (mtime) mais antiga - mesma
  regra usada na passada exata.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .db import ArquivoInfo

# (is_raw, resolucao_efetiva, original_bonus) - sempre bem definido, nunca
# depende de um sinal que pode faltar.
RankKey = tuple[int, int, int]


def rank_key(
    caminho: str,
    info: ArquivoInfo | None,
    sinais_exif: dict[str, str],
    cfg: Config,
) -> RankKey:
    is_raw = 1 if cfg.is_raw(Path(caminho)) else 0
    resolucao = (info.largura or 0) * (info.altura or 0) if info else 0

    original_bonus = 1
    if cfg.original_vence_edicao:
        software = (sinais_exif.get("software") or "").lower()
        eh_edicao = any(editor in software for editor in cfg.editores)
        original_bonus = 0 if eh_edicao else 1

    return (is_raw, resolucao, original_bonus)


def quant_soma(sinais_exif: dict[str, str]) -> float | None:
    """Soma da tabela de quantizacao JPEG, se medida. None = nao medido ou
    nao se aplica (PNG, RAW) - tratado como sinal AUSENTE, nunca como zero."""
    quant_raw = sinais_exif.get("quant")
    if quant_raw is None:
        return None
    try:
        return float(quant_raw)
    except ValueError:
        return None


def escolher_representante(
    candidatos: list[tuple[str, RankKey, float | None, float | None]],
) -> str:
    """candidatos: [(sha256, rank_key, quant_soma_ou_None, mtime)].

    Devolve o sha256 vencedor. Ordem de desempate: rank_key (RAW > maior
    resolucao > original) -> quant (so' se TODOS os empatados tem o dado)
    -> mtime mais antigo -> sha256 (para ficar deterministico se ate' isso
    empatar)."""
    melhor_rank = max(c[1] for c in candidatos)
    empatados = [c for c in candidatos if c[1] == melhor_rank]

    if len(empatados) > 1:
        quants = [c[2] for c in empatados]
        if all(q is not None for q in quants):
            menor_quant = min(quants)
            empatados = [c for c in empatados if c[2] == menor_quant]

    def chave_mtime(c: tuple[str, RankKey, float | None, float | None]):
        mtime = c[3]
        return (mtime if mtime is not None else float("inf"), c[0])

    return min(empatados, key=chave_mtime)[0]
