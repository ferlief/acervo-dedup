"""Passada 2: duplicatas perceptuais.

Pega hash perceptual (phash) e dimensoes de 'arquivos' - NAO reabre nenhum
arquivo de imagem. O esquema documenta essa escolha explicitamente:
"acervo ja decodifica a imagem uma vez para tirar phash/largura/altura...
para dar a acervo-dedup o que ele precisa... sem abrir o arquivo de novo"
(acervo/esquema.sql). Um sobrevivente sem phash em 'arquivos' (ainda nao
indexado por 'acervo', ou nao e' imagem) fica de fora desta passada -
comportamento documentado, nao erro.

Agrupamento por indexacao multi-particao (LSH), portado dos prototipos
dedup_fase2/5/7: o hash de 64 bits vira 8 particoes de 1 byte; pelo
principio da casa dos pombos, dois hashes a distancia <= 7 colidem em pelo
menos uma particao. Evita comparar todos os pares (O(n^2)).

GUARDA DE PROPORCAO (herdada do prototipo, confirmada em dados reais: uma
foto da lua 1836x1836 casou com um icone de app 2480x1200): duas imagens
so' podem ser "a mesma" se a proporcao (largura/altura) nao diferir mais
que 'razao_aspecto_maxima'.

GUARDA DE IMAGEM CHAPADA: o prototipo tambem calibrou uma guarda contra
imagem de cor solida (hash perceptual degenera e casa com qualquer outra
chapada), mas ela exigia reabrir a imagem para medir desvio padrao. Fica
DESLIGADA aqui por padrao (config 'passada_perceptual.guarda_chapada_ativa')
precisamente para preservar a garantia de nao reabrir arquivo - ver
config.example.yaml para o raciocinio completo e o caminho de extensao.
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
        return True  # sem dimensao conhecida, nao bloqueia
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
    """Deterministico e estavel entre execucoes: depende so' do CONJUNTO de
    sha256 do grupo, nao de qual deles acabou sendo o representante (a
    escolha de representante pode mudar entre execucoes se 'sinais' ganhar
    dados novos - o id do grupo nao deveria)."""
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
