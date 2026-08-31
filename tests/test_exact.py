import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acervo_dedup.exact import agrupar_exatas, caminhos_ja_agrupados
from acervo_dedup.scanner import ArquivoFisico


class TestExact(unittest.TestCase):
    def test_grupo_byte_identico_representante_e_o_mais_antigo(self):
        arquivos = [
            ArquivoFisico("C:/a/foto_novo.jpg", 100, mtime=2000.0, sha256="H1"),
            ArquivoFisico("C:/a/foto_velho.jpg", 100, mtime=1000.0, sha256="H1"),
            ArquivoFisico("C:/a/foto_meio.jpg", 100, mtime=1500.0, sha256="H1"),
        ]
        grupos = agrupar_exatas(arquivos)
        self.assertEqual(len(grupos), 1)
        g = grupos[0]
        self.assertEqual(g.metodo, "exato")
        self.assertEqual(g.grupo_id, "H1")
        self.assertEqual(g.representante.caminho, "C:/a/foto_velho.jpg")
        candidatos = {m.caminho for m in g.candidatos_quarentena}
        self.assertEqual(candidatos, {"C:/a/foto_novo.jpg", "C:/a/foto_meio.jpg"})
        for m in g.candidatos_quarentena:
            self.assertFalse(m.e_representante)
            self.assertEqual(m.motivo, "copia_byte_identica_do_representante")
        self.assertEqual(g.representante.motivo, "metadado_criacao_mais_antigo")

    def test_sha256_unico_nao_forma_grupo(self):
        arquivos = [
            ArquivoFisico("C:/a/x.jpg", 100, mtime=1.0, sha256="H1"),
            ArquivoFisico("C:/a/y.jpg", 200, mtime=1.0, sha256="H2"),
        ]
        self.assertEqual(agrupar_exatas(arquivos), [])

    def test_arquivo_sem_hash_ignorado(self):
        arquivos = [
            ArquivoFisico("C:/a/x.jpg", 100, mtime=1.0, sha256=None),
            ArquivoFisico("C:/a/y.jpg", 100, mtime=2.0, sha256=None),
        ]
        self.assertEqual(agrupar_exatas(arquivos), [])

    def test_bytes_recuperaveis_soma_so_os_nao_representantes(self):
        arquivos = [
            ArquivoFisico("C:/a/1.jpg", 500, mtime=1.0, sha256="H1"),
            ArquivoFisico("C:/a/2.jpg", 500, mtime=2.0, sha256="H1"),
            ArquivoFisico("C:/a/3.jpg", 500, mtime=3.0, sha256="H1"),
        ]
        g = agrupar_exatas(arquivos)[0]
        self.assertEqual(g.bytes_recuperaveis, 1000)

    def test_caminhos_ja_agrupados_inclui_representante_e_perdedores(self):
        arquivos = [
            ArquivoFisico("C:/a/1.jpg", 500, mtime=1.0, sha256="H1"),
            ArquivoFisico("C:/a/2.jpg", 500, mtime=2.0, sha256="H1"),
        ]
        grupos = agrupar_exatas(arquivos)
        self.assertEqual(caminhos_ja_agrupados(grupos), {"C:/a/1.jpg", "C:/a/2.jpg"})


if __name__ == "__main__":
    unittest.main()
