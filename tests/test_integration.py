"""End-to-end test: real disk + real SQLite + real CLI (scan and isolar).
No mocks at all - this is what would have caught the 'duplicatas' PRIMARY
KEY bug that the unit tests (synthetic, content-grain data only) could not
reach."""

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acervo_dedup.cli import main as cli_main

DDL_ARQUIVOS = """
CREATE TABLE IF NOT EXISTS arquivos (
  sha256      TEXT PRIMARY KEY,
  caminho     TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  mtime       REAL,
  phash       TEXT,
  largura     INTEGER,
  altura      INTEGER,
  indexado_em REAL NOT NULL
)
"""


def sha256_de(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


class TestIntegracao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.raiz = self.base / "raiz"
        self.raiz.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _escrever(self, nome: str, conteudo: bytes, mtime: float) -> Path:
        p = self.raiz / nome
        p.write_bytes(conteudo)
        os.utime(p, (mtime, mtime))
        return p

    def test_scan_e_isolar_ponta_a_ponta(self):
        conteudo_a = b"FOTO-DUPLICADA-EXATA" * 100
        conteudo_c = b"FOTO-UNICA-SEM-PAR-NENHUM" * 50
        conteudo_d = b"FOTO-DIFERENTE-EM-BYTES-MAS-PARECIDA" * 80

        # a.jpg and b.jpg: identical bytes. b is older -> representative.
        self._escrever("a.jpg", conteudo_a, mtime=2_000_000.0)
        self._escrever("b.jpg", conteudo_a, mtime=1_000_000.0)
        # c.jpg: unique, no phash in 'arquivos' (simulates non-image/not indexed).
        self._escrever("c.jpg", conteudo_c, mtime=1_500_000.0)
        # d.jpg: different bytes from a/b, but a near phash and higher
        # resolution -> forms a perceptual group with the exact group's
        # representative.
        self._escrever("d.jpg", conteudo_d, mtime=1_800_000.0)

        sha_a = sha256_de(conteudo_a)
        sha_c = sha256_de(conteudo_c)
        sha_d = sha256_de(conteudo_d)

        banco = self.base / "acervo.sqlite3"
        conn = sqlite3.connect(str(banco))
        conn.execute(DDL_ARQUIVOS)
        agora = time.time()
        conn.execute(
            "INSERT INTO arquivos VALUES (?,?,?,?,?,?,?,?)",
            (sha_a, "algum/caminho/antigo.jpg", len(conteudo_a), agora,
             "0000000000000000", 1000, 1000, agora),
        )
        conn.execute(
            "INSERT INTO arquivos VALUES (?,?,?,?,?,?,?,?)",
            (sha_d, "algum/caminho/d.jpg", len(conteudo_d), agora,
             "0100000000000000", 4000, 4000, agora),  # distance=1, higher resolution
        )
        conn.execute(
            "INSERT INTO arquivos VALUES (?,?,?,?,?,?,?,?)",
            (sha_c, "algum/caminho/c.jpg", len(conteudo_c), agora,
             None, None, None, agora),  # no phash: non-image/not indexed
        )
        conn.commit()
        conn.close()

        config_path = self.base / "config.yaml"
        relatorio_path = self.base / "dedup_report.json"
        cache_path = self.base / "cache.sqlite3"
        quarentena = self.base / "_quarentena"
        revisao = self.base / "_revisao"
        config_path.write_text(
            f"""
banco:
  caminho: "{banco.as_posix()}"
varredura:
  raizes:
    - "{self.raiz.as_posix()}"
  cache: "{cache_path.as_posix()}"
  threads: 2
quarentena:
  diretorio: "{quarentena.as_posix()}"
revisao:
  diretorio: "{revisao.as_posix()}"
relatorio:
  saida: "{relatorio_path.as_posix()}"
""",
            encoding="utf-8",
        )

        rc = cli_main(["--config", str(config_path), "scan"])
        self.assertEqual(rc, 0)

        # --- 'duplicatas': no PRIMARY KEY violation, one row per exact group ---
        conn = sqlite3.connect(str(banco))
        linhas = conn.execute(
            "SELECT sha256, grupo_id, e_representante, metodo, distancia FROM duplicatas"
        ).fetchall()
        conn.close()
        self.assertEqual(len(linhas), len(set((l[0], l[1]) for l in linhas)))

        exatas = [l for l in linhas if l[3] == "exato"]
        self.assertEqual(exatas, [(sha_a, sha_a, 1, "exato", None)])

        perceptuais = [l for l in linhas if l[3] == "perceptual"]
        self.assertEqual(len(perceptuais), 2)
        by_sha = {l[0]: l for l in perceptuais}
        self.assertEqual(by_sha[sha_d][2], 1)  # d.jpg (higher resolution) is the representative
        self.assertEqual(by_sha[sha_a][2], 0)

        # --- JSON report ---
        relatorio = json.loads(relatorio_path.read_text(encoding="utf-8"))
        self.assertEqual(relatorio["resumo"]["grupos_exatos"], 1)
        self.assertEqual(relatorio["resumo"]["grupos_perceptuais"], 1)
        # 1 candidate in the exact group (a.jpg) + 1 in the perceptual one
        # (the exact group's representative, b.jpg, loses to d.jpg) = 2
        self.assertEqual(relatorio["resumo"]["arquivos_propostos_isolamento"], 2)

        destino_por_caminho = {
            c["caminho"]: c["destino"]
            for g in relatorio["duplicate_groups"]
            for c in g["candidatos_isolamento"]
        }
        self.assertIn(str(self.raiz / "a.jpg"), destino_por_caminho)
        self.assertIn(str(self.raiz / "b.jpg"), destino_por_caminho)
        self.assertNotIn(str(self.raiz / "c.jpg"), destino_por_caminho)
        self.assertNotIn(str(self.raiz / "d.jpg"), destino_por_caminho)

        # ROUTING BY DEGREE OF CERTAINTY: a.jpg is a byte-identical copy of
        # b.jpg -> safe discard. b.jpg only lost by SIMILARITY to d.jpg ->
        # it may be a unique photo, so it goes to human review.
        self.assertEqual(destino_por_caminho[str(self.raiz / "a.jpg")], "quarentena")
        self.assertEqual(destino_por_caminho[str(self.raiz / "b.jpg")], "revisao")
        self.assertEqual(relatorio["resumo"]["arquivos_para_quarentena"], 1)
        self.assertEqual(relatorio["resumo"]["arquivos_para_revisao"], 1)

        # --- isolar in dry-run: nothing moves ---
        rc = cli_main(["--config", str(config_path), "isolar"])
        self.assertEqual(rc, 0)
        self.assertTrue((self.raiz / "a.jpg").exists())
        self.assertTrue((self.raiz / "b.jpg").exists())
        self.assertFalse(quarentena.exists())
        self.assertFalse(revisao.exists())

        # --- --somente quarentena: empties the safe discard and does NOT
        # touch the review queue. This is the mode that recovers space
        # without risking a unique photo. ---
        rc = cli_main(
            ["--config", str(config_path), "isolar", "--somente", "quarentena", "--execute"]
        )
        self.assertEqual(rc, 0)
        self.assertFalse((self.raiz / "a.jpg").exists())
        self.assertTrue((quarentena / "a.jpg").exists())
        self.assertTrue((self.raiz / "b.jpg").exists())  # perceptual: untouched
        self.assertFalse(revisao.exists())

        # --- isolar --execute (unfiltered): the perceptual one moves now,
        # but to the REVIEW folder, never to quarantine ---
        rc = cli_main(["--config", str(config_path), "isolar", "--execute"])
        self.assertEqual(rc, 0)
        self.assertFalse((self.raiz / "b.jpg").exists())
        self.assertTrue((revisao / "b.jpg").exists())
        self.assertFalse((quarentena / "b.jpg").exists())
        self.assertTrue((self.raiz / "c.jpg").exists())  # unique, never touched
        self.assertTrue((self.raiz / "d.jpg").exists())  # perceptual representative, stays

    def test_arquivo_bloqueado_nao_derruba_a_varredura(self):
        """Invariant 4: an I/O failure becomes a recorded error, not a fatal
        exception. Simulated by pointing at a nonexistent scan root
        alongside a valid one."""
        self._escrever("unico.jpg", b"conteudo qualquer", mtime=1.0)

        banco = self.base / "acervo.sqlite3"
        conn = sqlite3.connect(str(banco))
        conn.execute(DDL_ARQUIVOS)
        conn.commit()
        conn.close()

        config_path = self.base / "config.yaml"
        raiz_inexistente = self.base / "nao_existe"
        config_path.write_text(
            f"""
banco:
  caminho: "{banco.as_posix()}"
varredura:
  raizes:
    - "{self.raiz.as_posix()}"
    - "{raiz_inexistente.as_posix()}"
  cache: "{(self.base / 'cache.sqlite3').as_posix()}"
relatorio:
  saida: "{(self.base / 'dedup_report.json').as_posix()}"
""",
            encoding="utf-8",
        )

        rc = cli_main(["--config", str(config_path), "scan"])
        self.assertEqual(rc, 0)  # does not bring the scan down

        relatorio = json.loads((self.base / "dedup_report.json").read_text(encoding="utf-8"))
        mensagens = [e["mensagem"] for e in relatorio["erros"]]
        self.assertTrue(any("nao encontrada" in m for m in mensagens))


if __name__ == "__main__":
    unittest.main()
