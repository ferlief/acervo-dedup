"""Access to the 'acervo' SQLite database - the contract between acervo,
acervo-dedup and acervo-sort (see acervo/esquema.sql).

Invariant 5 (acervo-dedup CLAUDE.md): "writes to duplicatas, reads
arquivos." This module writes ONLY to the 'duplicatas' table. The readers
for 'sinais' exist because esquema.sql itself documents 'sinais
(fonte=exif)' as the channel meant to hand acervo-dedup what it needs to
pick a representative without reopening the image - it is not policy, it
is the same kind of raw fact phash already is. Nothing here writes to
'sinais' or to 'veredito'.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .models import GrupoDuplicata

# Verbatim DDL from acervo/esquema.sql for the table acervo-dedup owns.
# Repeated here (not imported) because the three products are separate
# repositories; esquema.sql is the contract, this is the writer's copy.
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
    """Reads the 'arquivos' rows whose sha256 is in the given list.

    Manual batching (SQLite caps the number of variables per statement)."""
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
    """Reads 'sinais' with fonte='exif' for the given sha256 values.

    Returns {sha256: {key: value}}. A missing row means "not measured yet"
    (see esquema.sql) - the caller treats it as neutral, never as an error.
    An 'acervo' database that has not written any signal yet may not even
    have the table - handled the same way: no signals at all, never a fatal
    error."""
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
    """Turns groups into 'duplicatas' rows (sha256, grupo_id,
    e_representante, metodo, distancia).

    TRAP avoided here: 'duplicatas' has PRIMARY KEY (sha256, grupo_id). In
    an EXACT group ALL members share the SAME sha256 (that is the very
    definition of "byte-identical"), which makes an exact group exactly one
    possible record per (sha256, grupo_id), not one per physical copy. The
    physical copies (which one is the representative, which paths go to
    quarantine) live in the JSON report, whose grain is the FILE;
    'duplicatas' has CONTENT grain. Writing one row per physical member of
    an exact group would violate the primary key (the second member's
    INSERT would collide with the first).

    In a PERCEPTUAL group each member has a DIFFERENT sha256 by definition
    (different bytes, same image) - there, one row per member."""
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
    """Replaces the contents of 'duplicatas' with this scan's result.

    Every 'acervo-dedup scan' is authoritative about the current state of
    the scanned disk (same reconciliation philosophy as the prototype: the
    disk is the truth). A partial scan (a subset of the roots) still
    replaces the whole table - documented as a known limitation in the
    README; merging results from partial scans is left for a future
    version."""
    conn.execute("DELETE FROM duplicatas")
    conn.executemany(
        "INSERT INTO duplicatas (sha256, grupo_id, e_representante, metodo, distancia) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def now() -> float:
    return time.time()
