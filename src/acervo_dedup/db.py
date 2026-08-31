"""Acesso ao SQLite do 'acervo' - o contrato entre acervo, acervo-dedup e
acervo-sort (ver acervo/esquema.sql).

Invariante 5 (CLAUDE.md do acervo-dedup): "Escreve em duplicatas, le
arquivos." Este modulo escreve SOMENTE na tabela 'duplicatas'. As funcoes
de leitura de 'sinais' existem porque o proprio esquema.sql documenta
'sinais(fonte=exif)' como o canal pensado para dar a acervo-dedup o que
ele precisa para escolher representante sem reabrir a imagem - "nao e'
politica: e' o mesmo tipo de fato bruto que phash ja e'". Nada aqui grava
em 'sinais' nem em 'veredito'.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .models import GrupoDuplicata

# DDL exata de acervo/esquema.sql para a tabela que acervo-dedup possui.
# Repetida aqui (nao importada) porque os tres produtos sao repositorios
# separados; esquema.sql e' o contrato, esta e' a copia de quem escreve.
_DDL_DUPLICATAS = """
CREATE TABLE IF NOT EXISTS duplicatas (
  sha256         TEXT NOT NULL REFERENCES arquivos(sha256),
  grupo_id       TEXT NOT NULL,
  e_representante INTEGER NOT NULL DEFAULT 0,
  metodo         TEXT NOT NULL,
  distancia      REAL,
  PRIMARY KEY (sha256, grupo_id)
)
"""
_DDL_DUPLICATAS_IDX = "CREATE INDEX IF NOT EXISTS ix_dup_grupo ON duplicatas(grupo_id)"


@dataclass(frozen=True)
class ArquivoInfo:
    sha256: str
    caminho: str
    bytes: int
    mtime: float | None
    phash: str | None
    largura: int | None
    altura: int | None


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(
            f"Banco do acervo nao encontrado: {db_path}. "
            f"acervo-dedup le a tabela 'arquivos', que e' escrita por 'acervo' - "
            f"rode 'acervo' sobre o diretorio antes."
        )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _assert_contract(conn, db_path)
    _ensure_duplicatas(conn)
    return conn


def _assert_contract(conn: sqlite3.Connection, db_path: Path) -> None:
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "arquivos" not in tables:
        raise RuntimeError(
            f"{db_path} nao tem a tabela 'arquivos' (contrato de acervo/esquema.sql). "
            f"Rode 'acervo' antes de 'acervo-dedup'."
        )


def _ensure_duplicatas(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL_DUPLICATAS)
    conn.execute(_DDL_DUPLICATAS_IDX)
    conn.commit()


def lookup_arquivos_por_sha256(
    conn: sqlite3.Connection, sha256_values: list[str]
) -> dict[str, ArquivoInfo]:
    """Le em 'arquivos' as linhas cujo sha256 esta' na lista dada.

    Batching manual (SQLite tem limite de variaveis por statement)."""
    out: dict[str, ArquivoInfo] = {}
    CHUNK = 900
    for i in range(0, len(sha256_values), CHUNK):
        chunk = sha256_values[i : i + CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT sha256, caminho, bytes, mtime, phash, largura, altura "
            f"FROM arquivos WHERE sha256 IN ({placeholders})",
            chunk,
        ).fetchall()
        for r in rows:
            out[r["sha256"]] = ArquivoInfo(
                sha256=r["sha256"],
                caminho=r["caminho"],
                bytes=r["bytes"],
                mtime=r["mtime"],
                phash=r["phash"],
                largura=r["largura"],
                altura=r["altura"],
            )
    return out


def lookup_sinais_exif(
    conn: sqlite3.Connection, sha256_values: list[str]
) -> dict[str, dict[str, str]]:
    """Le 'sinais' fonte='exif' para os sha256 dados.

    Devolve {sha256: {chave: valor}}. Ausencia de linha significa "nao
    medido ainda" (ver esquema.sql) - o chamador trata como neutro, nunca
    como erro. Um banco de 'acervo' que ainda nao escreveu nenhum sinal
    pode nem ter a tabela criada ainda - tratado do mesmo jeito: sem sinal
    nenhum, nunca erro fatal."""
    out: dict[str, dict[str, str]] = {}
    if not sha256_values:
        return out
    CHUNK = 900
    for i in range(0, len(sha256_values), CHUNK):
        chunk = sha256_values[i : i + CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        try:
            rows = conn.execute(
                f"SELECT sha256, chave, valor FROM sinais "
                f"WHERE fonte = 'exif' AND sha256 IN ({placeholders})",
                chunk,
            ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e):
                raise
            return {}
        for r in rows:
            out.setdefault(r["sha256"], {})[r["chave"]] = r["valor"]
    return out


def linhas_para_duplicatas(grupos: list[GrupoDuplicata]) -> list[tuple]:
    """Converte grupos em linhas de 'duplicatas' (sha256, grupo_id,
    e_representante, metodo, distancia).

    ARMADILHA evitada aqui: 'duplicatas' tem PRIMARY KEY (sha256, grupo_id).
    Num grupo EXATO, TODOS os membros compartilham o MESMO sha256 (essa e'
    a propria definicao de "byte-identico") - e' isso que faz o grupo
    exato ser um so' registro possivel por (sha256, grupo_id), nao um por
    copia fisica. As copias fisicas (quem e' representante, quais caminhos
    vao pra quarentena) vivem no relatorio JSON, que e' de grao de
    ARQUIVO; 'duplicatas' e' de grao de CONTEUDO. Escrever uma linha por
    membro fisico de um grupo exato violaria a chave primaria (INSERT do
    segundo membro colidiria com o primeiro).

    Num grupo PERCEPTUAL cada membro tem um sha256 DIFERENTE por definicao
    (bytes diferentes, mesma imagem) - ai' sim uma linha por membro."""
    linhas: list[tuple] = []
    for g in grupos:
        if g.metodo == "exato":
            rep = g.representante
            linhas.append((rep.sha256, g.grupo_id, 1, g.metodo, None))
        else:
            for m in g.membros:
                linhas.append(
                    (m.sha256, g.grupo_id, int(m.e_representante), g.metodo, m.distancia)
                )
    return linhas


def replace_duplicatas(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """Substitui o conteudo de 'duplicatas' pelo resultado desta varredura.

    Cada 'acervo-dedup scan' e' autoritativo sobre o estado atual do disco
    varrido (mesma filosofia de reconciliacao do prototipo: o disco e' a
    verdade). Uma varredura parcial (subconjunto de raizes) ainda assim
    substitui a tabela inteira - documentado como limitacao conhecida em
    README; mesclar resultados de varreduras parciais fica para uma versao
    futura."""
    conn.execute("DELETE FROM duplicatas")
    conn.executemany(
        "INSERT INTO duplicatas (sha256, grupo_id, e_representante, metodo, distancia) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def now() -> float:
    return time.time()
