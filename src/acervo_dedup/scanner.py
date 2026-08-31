"""Varredura de disco + SHA-256 em blocos.

Portado de acervo-prototipo/dedup_fase1.py e dedup_fase2.py: triagem por
tamanho (arquivo de tamanho unico morre na peneira sem I/O), SHA-256 em
blocos para os candidatos, cache privado em SQLite para nao reprocessar em
execucoes futuras (mesma logica de reconciliacao "o disco e' a verdade, o
indice e' so' cache" do fase2 v2/v3).

Por que uma varredura propria, independente de 'arquivos': a tabela
'arquivos' e' chaveada por sha256 ("a chave e' sempre sha256, nunca o
caminho" - acervo/esquema.sql), entao ela guarda so' o ULTIMO caminho
conhecido por conteudo. Copias fisicas duplicadas em disco (o proprio
objeto que este programa existe para achar) nao sobrevivem a essa
indexacao - so' aparecem varrendo o disco de novo.

Invariante 4 do acervo-dedup (CLAUDE.md): falha de I/O nao derruba a
varredura. Arquivo bloqueado ou sem permissao vira registro de erro.
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
    """Um arquivo REAL no disco, identificado por caminho (nao por sha256 -
    e' exatamente essa distincao que falta em 'arquivos')."""

    caminho: str
    tamanho: int
    mtime: float
    sha256: str | None = None


@dataclass
class ResultadoVarredura:
    arquivos: list[ArquivoFisico]
    erros: list[tuple[str, str]]  # (caminho, mensagem)


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
    """{caminho: (tamanho, mtime)}. Um diretorio ou arquivo inacessivel vira
    erro registrado, nunca excecao fatal (invariante 4)."""
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
    """O disco e' a verdade; o cache e' so' cache (mesma logica do
    prototipo). Devolve {caminho: (tamanho, mtime, sha256_ou_None)}."""
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
    """SHA-256 em blocos, so' dos candidatos (tamanho ja colidiu com outro
    arquivo - triagem por tamanho ja aconteceu antes de chamar isto)."""
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
    """Ponto de entrada: passada exata, etapa 1 (triagem + hash).

    1) lista o disco;
    2) reconcilia com o cache privado (o disco e' a verdade);
    3) triagem por tamanho: so' arquivos cujo tamanho colide com o de
       algum outro viram candidatos a hash (tamanho unico morre aqui, sem
       I/O nenhum - e' o proprio ponto da peneira);
    4) SHA-256 em blocos so' dos candidatos, com cache entre execucoes.
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
                # tamanho unico: nao precisa de hash para saber que nao tem
                # duplicata exata - mas ainda participa da passada perceptual
                arquivos.append(ArquivoFisico(p, tam, mt, sha256=None))
            elif p in ja_com_hash_relevante:
                arquivos.append(ArquivoFisico(p, tam, mt, sha256=sha))
            elif p in novos_hashes:
                arquivos.append(ArquivoFisico(p, tam, mt, sha256=novos_hashes[p]))
            # arquivos com erro de hash ficam de fora (ja registrados em erros)
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
    """Calcula SHA-256 dos caminhos dados que ainda nao tem hash no cache.

    Usado pela passada perceptual: para cruzar um sobrevivente da passada
    exata com 'arquivos' (chaveada por sha256), o sha256 dele precisa
    existir - mesmo que a passada exata tenha pulado o hash dele por ser de
    tamanho unico (a otimizacao da passada exata e' nao comparar hash entre
    arquivos que nunca poderiam ser identicos; nao e' "nunca hashear
    ninguem"). So' os SOBREVIVENTES da passada exata chegam aqui, um
    conjunto muito menor que o total varrido.
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
