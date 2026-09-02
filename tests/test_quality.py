import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acervo_dedup.config import Config
from acervo_dedup.db import ArquivoInfo
from acervo_dedup.quality import escolher_representante, quant_soma, rank_key


def make_cfg(editores=("vsco", "photoshop"), original_vence_edicao=True):
    return Config(
        banco_caminho=Path("x.sqlite3"),
        varredura_raizes=[],
        extensoes_imagem=frozenset({".jpg", ".png"}),
        extensoes_raw=frozenset({".nef", ".cr2"}),
        cache_caminho=Path("cache.sqlite3"),
        threads=4,
        bloco_hash=1024,
        distancia_maxima=5,
        razao_aspecto_maxima=1.10,
        guarda_chapada_ativa=False,
        original_vence_edicao=original_vence_edicao,
        editores=editores,
        quarentena_dir=Path("q"),
        revisao_dir=Path("rev"),
        relatorio_saida=Path("r.json"),
    )


class TestRankKey(unittest.TestCase):
    def test_raw_sempre_vence(self):
        cfg = make_cfg()
        info_raw = ArquivoInfo("H1", "a.nef", 100, 1.0, "abc", 4000, 3000)
        info_jpg = ArquivoInfo("H2", "b.jpg", 100, 1.0, "abc", 8000, 6000)
        rk_raw = rank_key("a.nef", info_raw, {}, cfg)
        rk_jpg = rank_key("b.jpg", info_jpg, {}, cfg)
        self.assertGreater(rk_raw, rk_jpg)

    def test_maior_resolucao_vence_em_empate_de_raw(self):
        cfg = make_cfg()
        pequena = ArquivoInfo("H1", "a.jpg", 100, 1.0, "abc", 100, 100)
        grande = ArquivoInfo("H2", "b.jpg", 100, 1.0, "abc", 4000, 3000)
        rk_pequena = rank_key("a.jpg", pequena, {}, cfg)
        rk_grande = rank_key("b.jpg", grande, {}, cfg)
        self.assertGreater(rk_grande, rk_pequena)

    def test_original_vence_edicao_em_empate_de_resolucao(self):
        cfg = make_cfg()
        info = ArquivoInfo("H1", "a.jpg", 100, 1.0, "abc", 1000, 1000)
        rk_original = rank_key("a.jpg", info, {}, cfg)
        rk_editado = rank_key("a.jpg", info, {"software": "Adobe Photoshop 24.0"}, cfg)
        self.assertGreater(rk_original, rk_editado)

    def test_original_vence_edicao_desligavel_por_config(self):
        cfg = make_cfg(original_vence_edicao=False)
        info = ArquivoInfo("H1", "a.jpg", 100, 1.0, "abc", 1000, 1000)
        rk_original = rank_key("a.jpg", info, {}, cfg)
        rk_editado = rank_key("a.jpg", info, {"software": "Adobe Photoshop 24.0"}, cfg)
        self.assertEqual(rk_original, rk_editado)


class TestQuantSoma(unittest.TestCase):
    def test_ausente_e_none(self):
        self.assertIsNone(quant_soma({}))

    def test_presente_vira_float(self):
        self.assertEqual(quant_soma({"quant": "128"}), 128.0)

    def test_invalido_e_none(self):
        self.assertIsNone(quant_soma({"quant": "nao-e-numero"}))


class TestEscolherRepresentante(unittest.TestCase):
    def test_desempata_por_mtime_mais_antigo_quando_rank_empata(self):
        candidatos = [
            ("H1", (0, 1000, 1), None, 500.0),
            ("H2", (0, 1000, 1), None, 100.0),  # same rank, older
            ("H3", (0, 1000, 1), None, 900.0),
        ]
        self.assertEqual(escolher_representante(candidatos), "H2")

    def test_rank_key_decide_antes_de_mtime(self):
        candidatos = [
            ("H1", (0, 1000, 1), None, 1.0),  # older, but worse rank
            ("H2", (1, 1000, 1), None, 999.0),  # RAW, newer, wins anyway
        ]
        self.assertEqual(escolher_representante(candidatos), "H2")

    def test_quant_desempata_quando_todos_tem_o_dado(self):
        candidatos = [
            ("H1", (0, 1000, 1), 640.0, 50.0),  # more compressed
            ("H2", (0, 1000, 1), 80.0, 50.0),  # less compressed, wins
        ]
        self.assertEqual(escolher_representante(candidatos), "H2")

    def test_quant_e_ignorado_se_algum_empatado_nao_tem_o_dado(self):
        """Without this, a PNG (no quant) would win or lose against a JPEG
        purely because the signal is missing - not a fair comparison, so the
        whole criterion is skipped and the tie-break falls to mtime."""
        candidatos = [
            ("H1", (0, 1000, 1), 10.0, 900.0),  # low quant, but newer
            ("H2", (0, 1000, 1), None, 100.0),  # no quant, but older
        ]
        self.assertEqual(escolher_representante(candidatos), "H2")


if __name__ == "__main__":
    unittest.main()
