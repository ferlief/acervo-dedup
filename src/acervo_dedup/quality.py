"""Quality criterion for the representative of a PERCEPTUAL GROUP (files
that look identical but differ in bytes - RAW vs JPEG, original vs
recompression, the same photo saved twice).

For an EXACT group (byte-identical) quality is irrelevant - the bytes are
the same file; the tie-break there is creation date alone (see exact.py).
This module only matters in the perceptual pass.

Criteria, from most to least decisive (measurable, in this order):

  1) RAW always wins - a RAW carries more information than any JPEG/PNG
     derived from it, by definition (the file extension decides).
  2) Higher EFFECTIVE RESOLUTION (width x height, read from 'arquivos' -
     already computed by 'acervo', not recomputed here).
  3) On a resolution tie, ORIGINAL beats EDIT: the EXIF Software tag
     ('sinais' fonte=exif chave=software) is matched against a list of
     known editor names (config 'qualidade.editores'). Without this, a
     version that went through an editing app can win merely for being
     larger in bytes while being IDENTICAL in resolution to the original -
     exactly the failure fixed in the sibling prototype 'curadoria' (199
     edits promoted over their originals in a real archive). A missing tag
     (most camera originals) counts as "not an edit".
  4) Still tied after (1)-(3): SMALLEST JPEG QUANTIZATION TABLE SUM
     ('sinais' fonte=exif chave=quant) - a smaller sum implies less
     compression loss (a finer quantization step).

     This criterion ONLY applies when EVERY file tied at (1)-(3) has the
     signal measured. An absolute quant number is not comparable to "no
     number at all" - there is no "neutral quant" acting as the zero of the
     scale (the sum is never zero in a real JPEG). So if any tied file
     lacks 'quant' (PNG, RAW, or not measured yet), the whole criterion is
     skipped for that tied set and the tie-break falls straight through to
     the next step - rather than risking declaring one file "better" only
     because the other is missing the data.

  If EVERYTHING above ties, the oldest date (mtime) wins - the same rule
  used by the exact pass.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .db import ArquivoInfo

# (is_raw, effective_resolution, original_bonus) - always well defined, it
# never depends on a signal that may be missing.
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
    """JPEG quantization table sum, when measured. None = not measured or
    not applicable (PNG, RAW) - treated as an ABSENT signal, never zero."""
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
    """candidatos: [(sha256, rank_key, quant_sum_or_None, mtime)].

    Returns the winning sha256. Tie-break order: rank_key (RAW > higher
    resolution > original) -> quant (only when EVERY tied file has the
    data) -> oldest mtime -> sha256 (to stay deterministic if even that
    ties)."""
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
