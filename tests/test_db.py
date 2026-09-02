import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acervo_dedup.db import linhas_para_duplicatas
from acervo_dedup.models import GrupoDuplicata, MembroGrupo


class TestLinhasParaDuplicatas(unittest.TestCase):
    def test_grupo_exato_com_varias_copias_fisicas_gera_uma_unica_linha(self):
        """Regression: an exact group with 3 physical copies of the same
        sha256 must not produce 3 (sha256, grupo_id) rows - that pair is
        exactly the PRIMARY KEY of the 'duplicatas' table, and the 3 copies
        share the same sha256 by definition. One row per member would
        collide on the second insert."""
        grupo = GrupoDuplicata(
            grupo_id="H1",
            metodo="exato",
            membros=[
                MembroGrupo("H1", "a.jpg", 100, 1.0, True, None, "metadado_criacao_mais_antigo"),
                MembroGrupo("H1", "b.jpg", 100, 2.0, False, None, "copia_byte_identica_do_representante"),
                MembroGrupo("H1", "c.jpg", 100, 3.0, False, None, "copia_byte_identica_do_representante"),
            ],
        )
        linhas = linhas_para_duplicatas([grupo])
        self.assertEqual(linhas, [("H1", "H1", 1, "exato", None)])
        # The (sha256, grupo_id) PK never repeats.
        chaves = [(sha, gid) for sha, gid, _rep, _met, _dist in linhas]
        self.assertEqual(len(chaves), len(set(chaves)))

    def test_grupo_perceptual_gera_uma_linha_por_sha256_distinto(self):
        grupo = GrupoDuplicata(
            grupo_id="perc-x",
            metodo="perceptual",
            membros=[
                MembroGrupo("H1", "a.jpg", 100, 1.0, True, 0.0, "melhor_qualidade_do_grupo_perceptual"),
                MembroGrupo("H2", "b.jpg", 100, 2.0, False, 3.0, "qualidade_inferior_ou_igual_ao_representante"),
            ],
        )
        linhas = linhas_para_duplicatas([grupo])
        self.assertEqual(
            set(linhas),
            {
                ("H1", "perc-x", 1, "perceptual", 0.0),
                ("H2", "perc-x", 0, "perceptual", 3.0),
            },
        )

    def test_lista_vazia(self):
        self.assertEqual(linhas_para_duplicatas([]), [])


if __name__ == "__main__":
    unittest.main()
