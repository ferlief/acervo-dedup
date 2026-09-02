import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acervo_dedup.config import Config
from acervo_dedup.db import ArquivoInfo
from acervo_dedup.perceptual import agrupar_perceptuais
from acervo_dedup.scanner import ArquivoFisico


def make_cfg(distancia_maxima=5, razao_aspecto_maxima=1.10):
    return Config(
        banco_caminho=Path("x.sqlite3"),
        varredura_raizes=[],
        extensoes_imagem=frozenset({".jpg", ".png"}),
        extensoes_raw=frozenset({".nef", ".cr2"}),
        cache_caminho=Path("cache.sqlite3"),
        threads=4,
        bloco_hash=1024,
        distancia_maxima=distancia_maxima,
        razao_aspecto_maxima=razao_aspecto_maxima,
        guarda_chapada_ativa=False,
        original_vence_edicao=True,
        editores=(),
        quarentena_dir=Path("q"),
        revisao_dir=Path("rev"),
        relatorio_saida=Path("r.json"),
    )


def hexhash(byte0=0, resto=0):
    """hash perceptual sintetico de 64 bits (16 hex chars), controlavel."""
    b = bytes([byte0]) + bytes([resto]) * 7
    return b.hex()


class TestPerceptual(unittest.TestCase):
    def test_grupo_formado_dentro_do_limiar_de_hamming(self):
        af1 = ArquivoFisico("a.jpg", 100, mtime=10.0, sha256="H1")
        af2 = ArquivoFisico("b.jpg", 200, mtime=5.0, sha256="H2")
        info1 = ArquivoInfo("H1", "a.jpg", 100, 10.0, hexhash(0b00000000), 1000, 1000)
        info2 = ArquivoInfo("H2", "b.jpg", 200, 5.0, hexhash(0b00000011), 1000, 1000)  # dist=2
        cfg = make_cfg()

        grupos, stats = agrupar_perceptuais(
            [af1, af2], {"H1": info1, "H2": info2}, {}, cfg
        )
        self.assertEqual(len(grupos), 1)
        self.assertEqual(stats.candidatos_com_phash, 2)
        self.assertEqual(stats.sem_phash, 0)
        g = grupos[0]
        self.assertEqual(g.metodo, "perceptual")
        # maior resolucao empatada -> desempata por mtime mais antigo: H2 (mtime=5)
        self.assertEqual(g.representante.sha256, "H2")
        self.assertEqual(g.candidatos_quarentena[0].distancia, 2.0)

    def test_fora_do_limiar_de_hamming_nao_agrupa(self):
        af1 = ArquivoFisico("a.jpg", 100, mtime=10.0, sha256="H1")
        af2 = ArquivoFisico("b.jpg", 200, mtime=5.0, sha256="H2")
        info1 = ArquivoInfo("H1", "a.jpg", 100, 10.0, hexhash(0x00), 1000, 1000)
        info2 = ArquivoInfo("H2", "b.jpg", 200, 5.0, hexhash(0xFF), 1000, 1000)  # dist=8
        cfg = make_cfg()

        grupos, stats = agrupar_perceptuais(
            [af1, af2], {"H1": info1, "H2": info2}, {}, cfg
        )
        self.assertEqual(grupos, [])

    def test_guarda_de_proporcao_bloqueia_apesar_de_hash_proximo(self):
        af1 = ArquivoFisico("a.jpg", 100, mtime=10.0, sha256="H1")
        af2 = ArquivoFisico("b.jpg", 200, mtime=5.0, sha256="H2")
        info1 = ArquivoInfo("H1", "a.jpg", 100, 10.0, hexhash(0x00), 1000, 1000)  # 1:1
        info2 = ArquivoInfo("H2", "b.jpg", 200, 5.0, hexhash(0x03), 2000, 500)  # 4:1, dist=2
        cfg = make_cfg()

        grupos, stats = agrupar_perceptuais(
            [af1, af2], {"H1": info1, "H2": info2}, {}, cfg
        )
        self.assertEqual(grupos, [])
        self.assertEqual(stats.bloqueados_por_proporcao, 1)

    def test_sem_phash_fica_fora_da_comparacao(self):
        af1 = ArquivoFisico("a.jpg", 100, mtime=10.0, sha256="H1")
        af2 = ArquivoFisico("b.jpg", 200, mtime=5.0, sha256="H2")
        info1 = ArquivoInfo("H1", "a.jpg", 100, 10.0, None, 1000, 1000)  # sem phash
        info2 = ArquivoInfo("H2", "b.jpg", 200, 5.0, hexhash(0x00), 1000, 1000)
        cfg = make_cfg()

        grupos, stats = agrupar_perceptuais(
            [af1, af2], {"H1": info1, "H2": info2}, {}, cfg
        )
        self.assertEqual(grupos, [])
        self.assertEqual(stats.sem_phash, 1)
        self.assertEqual(stats.candidatos_com_phash, 1)

    def test_representante_perceptual_e_o_de_maior_resolucao(self):
        af1 = ArquivoFisico("pequena.jpg", 100, mtime=1.0, sha256="H1")
        af2 = ArquivoFisico("grande.jpg", 200, mtime=999.0, sha256="H2")
        info1 = ArquivoInfo("H1", "pequena.jpg", 100, 1.0, hexhash(0x00), 500, 500)
        info2 = ArquivoInfo("H2", "grande.jpg", 200, 999.0, hexhash(0x01), 4000, 4000)
        cfg = make_cfg()

        grupos, _stats = agrupar_perceptuais(
            [af1, af2], {"H1": info1, "H2": info2}, {}, cfg
        )
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0].representante.sha256, "H2")
        self.assertEqual(grupos[0].representante.motivo, "melhor_qualidade_do_grupo_perceptual")


if __name__ == "__main__":
    unittest.main()
