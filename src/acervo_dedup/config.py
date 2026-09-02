"""Carrega e valida a configuracao do acervo-dedup.

Segue a mesma separacao do resto da suite acervo: a MEDIDA (sha256, phash,
distancia de Hamming) e' universal e fica no codigo; o que este modulo
carrega e' POLITICA (limiares, listas de editores, caminhos).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

_DEFAULTS: dict[str, Any] = {
    "banco": {"caminho": "./acervo.sqlite3"},
    "varredura": {
        "raizes": [],
        "extensoes": {
            "imagem": [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"],
            "raw": [".nef", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".rw2", ".raf"],
        },
        "cache": "./dedup_scan_cache.sqlite3",
        "threads": 8,
    },
    "passada_exata": {"bloco_hash": 1024 * 1024},
    "passada_perceptual": {
        "distancia_maxima": 5,
        "razao_aspecto_maxima": 1.10,
        "guarda_chapada_ativa": False,
    },
    "qualidade": {
        "original_vence_edicao": True,
        "editores": [],
    },
    "quarentena": {"diretorio": "./_quarentena_dedup"},
    "revisao": {"diretorio": "./_revisao_dedup"},
    "relatorio": {"saida": "./dedup_report.json"},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclasses.dataclass(frozen=True)
class Config:
    banco_caminho: Path
    varredura_raizes: list[Path]
    extensoes_imagem: frozenset[str]
    extensoes_raw: frozenset[str]
    cache_caminho: Path
    threads: int
    bloco_hash: int
    distancia_maxima: int
    razao_aspecto_maxima: float
    guarda_chapada_ativa: bool
    original_vence_edicao: bool
    editores: tuple[str, ...]
    quarentena_dir: Path
    revisao_dir: Path
    relatorio_saida: Path

    @property
    def todas_extensoes(self) -> frozenset[str]:
        return self.extensoes_imagem | self.extensoes_raw

    def is_raw(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensoes_raw


def load_config(path: str | Path | None) -> Config:
    raw: dict[str, Any] = {}
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config nao encontrada: {p}")
        with open(p, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    merged = _merge(_DEFAULTS, raw)

    return Config(
        banco_caminho=Path(merged["banco"]["caminho"]),
        varredura_raizes=[Path(r) for r in merged["varredura"]["raizes"]],
        extensoes_imagem=frozenset(
            s.lower() for s in merged["varredura"]["extensoes"]["imagem"]
        ),
        extensoes_raw=frozenset(
            s.lower() for s in merged["varredura"]["extensoes"]["raw"]
        ),
        cache_caminho=Path(merged["varredura"]["cache"]),
        threads=int(merged["varredura"]["threads"]),
        bloco_hash=int(merged["passada_exata"]["bloco_hash"]),
        distancia_maxima=int(merged["passada_perceptual"]["distancia_maxima"]),
        razao_aspecto_maxima=float(merged["passada_perceptual"]["razao_aspecto_maxima"]),
        guarda_chapada_ativa=bool(merged["passada_perceptual"]["guarda_chapada_ativa"]),
        original_vence_edicao=bool(merged["qualidade"]["original_vence_edicao"]),
        editores=tuple(s.lower() for s in merged["qualidade"]["editores"]),
        quarentena_dir=Path(merged["quarentena"]["diretorio"]),
        revisao_dir=Path(merged["revisao"]["diretorio"]),
        relatorio_saida=Path(merged["relatorio"]["saida"]),
    )
