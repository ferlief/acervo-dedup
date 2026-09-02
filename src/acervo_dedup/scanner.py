"""Disk walk + chunked SHA-256.

Ported from acervo-prototipo/dedup_fase1.py and dedup_fase2.py: size
triage (a file with a unique size dies in the sieve without any I/O),
chunked SHA-256 for the candidates, and a private SQLite cache so future
runs do not reprocess (the same "the disk is the truth, the index is only
a cache" reconciliation logic as fase2 v2/v3).

Why a dedicated walk instead of reusing 'arquivos': that table is keyed by
sha256 ("the key is always sha256, never the path" - acervo/esquema.sql),
so it keeps only the LAST known path per content. Duplicated physical
copies on disk - the very object this program exists to find - do not
survive that indexing; they only show up by walking the disk again.

acervo-dedup invariant 4 (CLAUDE.md): an I/O failure does not bring the
scan down. A locked or unreadable file becomes an error record.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArquivoFisico:
    """A REAL file on disk, identified by path (not by sha256 - that is
    exactly the distinction 'arquivos' cannot express)."""

    caminho: str
    tamanho: int
    mtime: float
    sha256: str | None = None


@dataclass
class ResultadoVarredura:
    arquivos: list[ArquivoFisico]
    erros: list[tuple[str, str]]  # (path, message)


def _init_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            size_bytes INTEGER NOT NULL,
            mtime REAL NOT NULL,
            sha256 TEXT,
            indexed_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_sha ON files(sha256)")
    conn.commit()


def _listar_disco(
    raizes: list[Path], extensoes: frozenset[str], erros: list[tuple[str, str]]
) -> dict[str, tuple[int, float]]:
    """{path: (size, mtime)}. An unreachable directory or file becomes a
    recorded error, never a fatal exception (invariant 4)."""
    disco: dict[str, tuple[int, float]] = {}
    for raiz in raizes:
        if not raiz.exists():
            erros.append((str(raiz), "raiz de varredura nao encontrada"))
            continue
        try:
            it = raiz.rglob("*")
        except OSError as e:
            erros.append((str(raiz), f"nao foi possivel listar: {e}"))
            continue
        while True:
            try:
                p = next(it)
            except StopIteration:
                break
            except (OSError, PermissionError) as e:
                erros.append((str(raiz), f"erro ao varrer subarvore: {e}"))
                break
            try:
                if not p.is_file():
                    continue
                if p.suffix.lower() not in extensoes:
                    continue
                st = p.stat()
            except (OSError, PermissionError) as e:
                erros.append((str(p), f"stat falhou: {e}"))
                continue
            disco[str(p)] = (st.st_size, st.st_mtime)
    return disco


def _reconciliar(
    conn: sqlite3.Connection, disco: dict[str, tuple[int, float]]
) -> dict[str, tuple[int, float, str | None]]:
    """The disk is the truth; the cache is only a cache (same logic as the
    prototype). Returns {path: (size, mtime, sha256_or_None)}."""
    cached = {
        r[0]: (r[1], r[2], r[3])
        for r in conn.execute("SELECT path, size_bytes, mtime, sha256 FROM files")
    }
    disco_paths, cache_paths = set(disco), set(cached)

    removidos = cache_paths - disco_paths
    if removidos:
        conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in removidos])

    now = time.time()
    novos = disco_paths - cache_paths
    if novos:
        conn.executemany(
            "INSERT INTO files (path, size_bytes, mtime, sha256, indexed_at) "
            "VALUES (?, ?, ?, NULL, ?)",
            [(p, disco[p][0], disco[p][1], now) for p in novos],
        )

    alterados = {
        p
        for p in (disco_paths & cache_paths)
        if disco[p][0] != cached[p][0] or abs(disco[p][1] - cached[p][1]) > 1.0
    }
    if alterados:
        conn.executemany(
            "UPDATE files SET size_bytes=?, mtime=?, sha256=NULL, indexed_at=? WHERE path=?",
            [(disco[p][0], disco[p][1], now, p) for p in alterados],
        )
    conn.commit()

    out: dict[str, tuple[int, float, str | None]] = {}
    for p, (tam, mt) in disco.items():
        if p in novos or p in alterados:
            out[p] = (tam, mt, None)
        else:
            out[p] = (tam, mt, cached[p][2])
    return out


def _hash_pendentes(
    conn: sqlite3.Connection,
    pendentes: list[str],
    bloco_hash: int,
    threads: int,
    erros: list[tuple[str, str]],
) -> dict[str, str]:
    """Chunked SHA-256, candidates only (their size already collided with
    another file - size triage ran before this is called)."""
    if not pendentes:
        return {}

    def hash_um(path_str: str) -> tuple[str, str | None, str | None]:
        try:
            hasher = hashlib.sha256()
            with open(path_str, "rb") as f:
                while chunk := f.read(bloco_hash):
                    hasher.update(chunk)
            return path_str, hasher.hexdigest(), None
        except (OSError, PermissionError) as e:
            return path_str, None, str(e)

    resultado: dict[str, str] = {}
    atualizacoes = []
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futuros = {pool.submit(hash_um, p): p for p in pendentes}
        for fut in as_completed(futuros):
            path_str, digest, err = fut.result()
            if digest is not None:
                resultado[path_str] = digest
                atualizacoes.append((digest, path_str))
            else:
                erros.append((path_str, err or "erro de leitura desconhecido"))
    if atualizacoes:
        conn.executemany("UPDATE files SET sha256=? WHERE path=?", atualizacoes)
        conn.commit()
    return resultado


def varrer(
    raizes: list[Path],
    extensoes: frozenset[str],
    cache_path: Path,
    bloco_hash: int,
    threads: int,
) -> ResultadoVarredura:
    """Entry point: exact pass, stage 1 (triage + hash).

    1) list the disk;
    2) reconcile against the private cache (the disk is the truth);
    3) size triage: only files whose size collides with another file's
       become hash candidates (a unique size dies here, with no I/O at all
       - that is the whole point of the sieve);
    4) chunked SHA-256 for the candidates only, cached across runs.
    """
    erros: list[tuple[str, str]] = []
    disco = _listar_disco(raizes, extensoes, erros)

    conn = sqlite3.connect(str(cache_path))
    try:
        _init_cache(conn)
        estado = _reconciliar(conn, disco)

        tamanhos: dict[int, int] = {}
        for _p, (tam, _mt, _sha) in estado.items():
            tamanhos[tam] = tamanhos.get(tam, 0) + 1

        candidatos = [
            p for p, (tam, _mt, sha) in estado.items() if tamanhos[tam] > 1 and sha is None
        ]
        ja_com_hash_relevante = {
            p for p, (tam, _mt, sha) in estado.items() if tamanhos[tam] > 1 and sha is not None
        }

        novos_hashes = _hash_pendentes(conn, candidatos, bloco_hash, threads, erros)

        arquivos: list[ArquivoFisico] = []
        for p, (tam, mt, sha) in estado.items():
            if tamanhos[tam] == 1:
                # Unique size: no hash needed to know it has no exact
                # duplicate - but it still joins the perceptual pass.
                arquivos.append(ArquivoFisico(p, tam, mt, sha256=None))
            elif p in ja_com_hash_relevante:
                arquivos.append(ArquivoFisico(p, tam, mt, sha256=sha))
            elif p in novos_hashes:
                arquivos.append(ArquivoFisico(p, tam, mt, sha256=novos_hashes[p]))
            # Files that failed to hash are left out (already recorded in erros).
    finally:
        conn.close()

    return ResultadoVarredura(arquivos=arquivos, erros=erros)


def completar_hashes(
    caminhos: list[str],
    cache_path: Path,
    bloco_hash: int,
    threads: int,
    erros: list[tuple[str, str]],
) -> dict[str, str]:
    """Computes SHA-256 for the given paths that have no hash in the cache.

    Used by the perceptual pass: to join an exact-pass survivor against
    'arquivos' (keyed by sha256) its sha256 has to exist - even when the
    exact pass skipped hashing it for having a unique size (the exact
    pass's optimization is not comparing hashes between files that could
    never be identical; it is not "never hash anyone"). Only the SURVIVORS
    of the exact pass reach this point, a far smaller set than everything
    scanned.
    """
    if not caminhos:
        return {}
    conn = sqlite3.connect(str(cache_path))
    try:
        _init_cache(conn)
        CHUNK = 900
        ja_tem: dict[str, str] = {}
        for i in range(0, len(caminhos), CHUNK):
            bloco = caminhos[i : i + CHUNK]
            placeholders = ",".join("?" for _ in bloco)
            for path_, sha in conn.execute(
                f"SELECT path, sha256 FROM files WHERE path IN ({placeholders})", bloco
            ):
                if sha:
                    ja_tem[path_] = sha
        faltando = [p for p in caminhos if p not in ja_tem]
        novos = _hash_pendentes(conn, faltando, bloco_hash, threads, erros)
        ja_tem.update(novos)
        return ja_tem
    finally:
        conn.close()
