"""Pass 2: perceptual duplicates.

Reads the perceptual hash (phash) and the dimensions from 'arquivos' - it
NEVER reopens an image file. The schema documents that choice explicitly:
acervo already decodes the image once to extract phash/largura/altura in
order to hand acervo-dedup what it needs without opening the file again
(acervo/esquema.sql). A survivor with no phash in 'arquivos' (not indexed
by 'acervo' yet, or not an image) sits this pass out - documented
behaviour, not an error.

Grouping uses multi-partition indexing (LSH), ported from the
dedup_fase2/5/7 prototypes: the 64-bit hash is split into 8 one-byte
partitions; by the pigeonhole principle two hashes at distance <= 7
collide in at least one partition. That avoids the O(n^2) all-pairs
comparison.

ASPECT-RATIO GUARD (inherited from the prototype, confirmed on real data:
a 1836x1836 photo of the moon matched a 2480x1200 app icon): two images can
only be "the same" if their aspect ratio (width/height) does not differ by
more than 'razao_aspecto_maxima'.

FLAT-IMAGE GUARD: the prototype also calibrated a guard against solid
colour images (the perceptual hash degenerates and matches any other flat
image), but it required reopening the image to measure standard deviation.
It stays OFF here by default (config
'passada_perceptual.guarda_chapada_ativa') precisely to preserve the
never-reopen-a-file guarantee - see config.example.yaml for the full
reasoning and the extension path.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from .config import Config
from .db import ArquivoInfo
from .models import GrupoDuplicata, MembroGrupo
from .quality import escolher_representante, quant_soma, rank_key
from .scanner import ArquivoFisico


@dataclass
class EstatisticasPerceptual:
    candidatos_com_phash: int = 0
    sem_phash: int = 0
    pares_no_limiar_hamming: int = 0
    bloqueados_por_proporcao: int = 0
    grupos_formados: int = 0
    guarda_chapada_ignorada: bool = False


def _hamming_hex(a: str, b: str) -> int:
    return sum(bin(x ^ y).count("1") for x, y in zip(bytes.fromhex(a), bytes.fromhex(b)))


def _aspecto_compativel(a: ArquivoInfo, b: ArquivoInfo, razao_max: float) -> bool:
    if not (a.largura and a.altura and b.largura and b.altura):
        return True  # no known dimensions: do not block
    ra, rb = a.largura / a.altura, b.largura / b.altura
    maior, menor = (ra, rb) if ra >= rb else (rb, ra)
    if menor == 0:
        return False
    return maior / menor <= razao_max


class _UnionFind:
    def __init__(self, itens: list[int]):
        self.pai = {i: i for i in itens}

    def find(self, x: int) -> int:
        while self.pai[x] != x:
            self.pai[x] = self.pai[self.pai[x]]
            x = self.pai[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.pai[ra] = rb


def _grupo_id(sha256_list: list[str]) -> str:
    """Deterministic and stable across runs: it depends only on the SET of
    sha256 values in the group, not on which one ended up as the
    representative (that choice can change between runs as 'sinais' gains
    new data - the group id should not)."""
    chave = ",".join(sorted(sha256_list))
    return "perc-" + hashlib.sha1(chave.encode("utf-8")).hexdigest()[:16]


def agrupar_perceptuais(
    sobreviventes: list[ArquivoFisico],
    arquivos_info: dict[str, ArquivoInfo],
    sinais_exif: dict[str, dict[str, str]],
    cfg: Config,
) -> tuple[list[GrupoDuplicata], EstatisticasPerceptual]:
    stats = EstatisticasPerceptual(guarda_chapada_ignorada=cfg.guarda_chapada_ativa)

    candidatos: list[tuple[ArquivoFisico, ArquivoInfo]] = []
    for af in sobreviventes:
        info = arquivos_info.get(af.sha256) if af.sha256 else None
        if info and info.phash:
            candidatos.append((af, info))
    stats.candidatos_com_phash = len(candidatos)
    stats.sem_phash = len(sobreviventes) - len(candidatos)

    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, (_af, info) in enumerate(candidatos):
        for parte, byte in enumerate(bytes.fromhex(info.phash)):
            buckets[(parte, byte)].append(idx)

    uf = _UnionFind(list(range(len(candidatos))))
    vistos: set[tuple[int, int]] = set()

    for indices in buckets.values():
        if len(indices) < 2:
            continue
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                a, b = indices[i], indices[j]
                par = (a, b) if a < b else (b, a)
                if par in vistos:
                    continue
                vistos.add(par)
                info_a, info_b = candidatos[a][1], candidatos[b][1]
                dist = _hamming_hex(info_a.phash, info_b.phash)
                if dist > cfg.distancia_maxima:
                    continue
                stats.pares_no_limiar_hamming += 1
                if not _aspecto_compativel(info_a, info_b, cfg.razao_aspecto_maxima):
                    stats.bloqueados_por_proporcao += 1
                    continue
                uf.union(a, b)

    componentes: dict[int, list[int]] = defaultdict(list)
    for idx in range(len(candidatos)):
        componentes[uf.find(idx)].append(idx)

    grupos: list[GrupoDuplicata] = []
    for indices in componentes.values():
        if len(indices) < 2:
            continue

        membros_dados = []
        for idx in indices:
            af, info = candidatos[idx]
            sinais = sinais_exif.get(af.sha256, {})
            rk = rank_key(af.caminho, info, sinais, cfg)
            qs = quant_soma(sinais)
            membros_dados.append((af, info, rk, qs))

        sha_representante = escolher_representante(
            [(af.sha256, rk, qs, af.mtime) for af, _info, rk, qs in membros_dados]
        )
        info_representante = next(
            info for af, info, _rk, _qs in membros_dados if af.sha256 == sha_representante
        )

        membros: list[MembroGrupo] = []
        for af, info, _rk, _qs in membros_dados:
            e_repr = af.sha256 == sha_representante
            dist = (
                0
                if e_repr
                else _hamming_hex(info.phash, info_representante.phash)
            )
            membros.append(
                MembroGrupo(
                    sha256=af.sha256,
                    caminho=af.caminho,
                    tamanho=af.tamanho,
                    mtime=af.mtime,
                    e_representante=e_repr,
                    distancia=float(dist),
                    motivo=(
                        "melhor_qualidade_do_grupo_perceptual"
                        if e_repr
                        else "qualidade_inferior_ou_igual_ao_representante"
                    ),
                )
            )

        grupo_id = _grupo_id([af.sha256 for af, _info, _rk, _qs in membros_dados])
        grupos.append(GrupoDuplicata(grupo_id=grupo_id, metodo="perceptual", membros=membros))

    stats.grupos_formados = len(grupos)
    return grupos, stats
