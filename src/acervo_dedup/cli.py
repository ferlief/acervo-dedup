"""CLI do acervo-dedup.

  acervo-dedup scan [--config config.yaml] [--raiz DIR ...] [--execute-nada]
  acervo-dedup isolar --relatorio dedup_report.json [--execute]

'scan' SO' detecta: varre o disco, roda as duas passadas, grava em
'duplicatas' e exporta o relatorio JSON. Nunca move arquivo nenhum.
'isolar' e' o unico comando que move, e so' quando chamado explicitamente
com --execute (sem a flag, roda em dry-run e so' mostra o que faria) -
'CLI, sem interface': tudo por linha de comando, nada automatico.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import db, exact, perceptual, report, scanner
from .config import Config, load_config
from .quarantine import isolar as executar_isolamento


def _cmd_scan(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    raizes = [Path(r) for r in args.raiz] if args.raiz else cfg.varredura_raizes
    if not raizes:
        print("[ERRO] Nenhuma raiz de varredura (config 'varredura.raizes' ou --raiz).")
        return 1

    print(f"Banco:        {cfg.banco_caminho}")
    print(f"Raizes:       {', '.join(str(r) for r in raizes)}")
    print(f"Cache local:  {cfg.cache_caminho}")
    print()

    print("[Passada 1/2 - exata] Varrendo disco e triando por tamanho...")
    resultado = scanner.varrer(
        raizes, cfg.todas_extensoes, cfg.cache_caminho, cfg.bloco_hash, cfg.threads
    )
    print(f"  {len(resultado.arquivos):,} arquivo(s) no disco, "
          f"{len(resultado.erros):,} erro(s) de leitura.")

    grupos_exatos = exact.agrupar_exatas(resultado.arquivos)
    duplicados_exatos = sum(len(g.candidatos_quarentena) for g in grupos_exatos)
    print(f"  {len(grupos_exatos):,} grupo(s) exato(s), "
          f"{duplicados_exatos:,} arquivo(s) candidato(s) a quarentena.\n")

    ja_agrupados = exact.caminhos_ja_agrupados(grupos_exatos)
    representantes_exatos = {g.representante.caminho for g in grupos_exatos}
    sobreviventes = [
        a
        for a in resultado.arquivos
        if a.caminho not in ja_agrupados or a.caminho in representantes_exatos
    ]

    print("[Passada 2/2 - perceptual] Completando hash dos sobreviventes...")
    faltando = [a.caminho for a in sobreviventes if a.sha256 is None]
    novos_hashes = scanner.completar_hashes(
        faltando, cfg.cache_caminho, cfg.bloco_hash, cfg.threads, resultado.erros
    )
    sobreviventes = [
        a if a.sha256 else scanner.ArquivoFisico(
            a.caminho, a.tamanho, a.mtime, novos_hashes.get(a.caminho)
        )
        for a in sobreviventes
    ]
    sobreviventes = [a for a in sobreviventes if a.sha256]

    conn = db.connect(cfg.banco_caminho)
    try:
        sha_list = [a.sha256 for a in sobreviventes]
        arquivos_info = db.lookup_arquivos_por_sha256(conn, sha_list)
        sinais_exif = db.lookup_sinais_exif(conn, list(arquivos_info.keys()))

        grupos_perceptuais, stats = perceptual.agrupar_perceptuais(
            sobreviventes, arquivos_info, sinais_exif, cfg
        )
        print(f"  {stats.candidatos_com_phash:,} com phash em 'arquivos', "
              f"{stats.sem_phash:,} sem phash (fora da comparacao).")
        print(f"  {stats.pares_no_limiar_hamming:,} par(es) no limiar de distancia -> "
              f"{stats.bloqueados_por_proporcao:,} bloqueado(s) por proporcao.")
        if stats.guarda_chapada_ignorada:
            print("  [AVISO] guarda_chapada_ativa=true na config, mas esta guarda "
                  "nao e' implementada nesta versao (ver config.example.yaml).")
        duplicados_perceptuais = sum(len(g.candidatos_quarentena) for g in grupos_perceptuais)
        print(f"  {stats.grupos_formados:,} grupo(s) perceptual(is), "
              f"{duplicados_perceptuais:,} arquivo(s) candidato(s) a quarentena.\n")

        todos_grupos = grupos_exatos + grupos_perceptuais
        linhas_duplicatas = db.linhas_para_duplicatas(todos_grupos)
        db.replace_duplicatas(conn, linhas_duplicatas)
        print(f"[Banco] 'duplicatas' atualizada: {len(linhas_duplicatas):,} linha(s).")
    finally:
        conn.close()

    relatorio = report.construir_relatorio(todos_grupos, raizes, resultado.erros)
    destino_relatorio = Path(args.relatorio) if args.relatorio else cfg.relatorio_saida
    report.salvar_relatorio(relatorio, destino_relatorio)

    resumo = relatorio["resumo"]
    print(f"\n{'=' * 70}")
    print(f"[Resultado] {resumo['grupos_exatos']:,} grupo(s) exato(s), "
          f"{resumo['grupos_perceptuais']:,} grupo(s) perceptual(is)")
    print(f"[Resultado] {resumo['arquivos_propostos_para_quarentena']:,} arquivo(s) "
          f"propostos para quarentena")
    print(f"[Resultado] Espaco recuperavel: "
          f"{resumo['bytes_recuperaveis_total'] / 1024**3:.2f} GB")
    if resultado.erros:
        print(f"[AVISO] {len(resultado.erros):,} arquivo(s) com erro de leitura "
              f"(bloqueado/permissao) - nao entraram na comparacao.")
    print(f"{'=' * 70}")
    print(f"[Relatorio] {destino_relatorio.resolve()}")
    print("\n>>> Nada foi movido. Rode 'acervo-dedup isolar' para mover os "
          "candidatos para quarentena. <<<")
    return 0


def _cmd_isolar(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    relatorio_path = Path(args.relatorio) if args.relatorio else cfg.relatorio_saida
    if not relatorio_path.exists():
        print(f"[ERRO] Relatorio nao encontrado: {relatorio_path}. Rode 'acervo-dedup scan' antes.")
        return 1

    with open(relatorio_path, encoding="utf-8") as f:
        relatorio = json.load(f)

    quarentena_dir = Path(args.quarentena) if args.quarentena else cfg.quarentena_dir
    print(f"Relatorio:  {relatorio_path}")
    print(f"Quarentena: {quarentena_dir}")
    print(f"Modo:       {'EXECUTE (vai mover)' if args.execute else 'DRY-RUN (so relatorio)'}\n")

    resultado = executar_isolamento(relatorio, quarentena_dir, args.execute)

    verbo = "movido" if args.execute else "seria movido"
    for origem, destino in resultado.movidos:
        print(f"  {verbo}: {origem}  ->  {destino}")
    if resultado.ja_ausentes:
        print(f"\n[Info] {len(resultado.ja_ausentes):,} arquivo(s) do relatorio ja nao "
              f"existem no caminho original (provavelmente ja isolados antes).")
    if resultado.erros:
        print(f"\n[AVISO] {len(resultado.erros):,} arquivo(s) nao puderam ser movidos:")
        for origem, msg in resultado.erros[:20]:
            print(f"    {origem}: {msg}")

    print(f"\n{'=' * 70}")
    print(f"[Resultado] {len(resultado.movidos):,} arquivo(s) "
          f"{'movido(s)' if args.execute else 'a mover'}, "
          f"{resultado.bytes_movidos / 1024**3:.2f} GB")
    print(f"{'=' * 70}")
    if not args.execute:
        print("\n>>> DRY-RUN: nada foi movido. Rode com --execute para isolar de fato. <<<")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acervo-dedup",
        description="Deteccao de redundancia em acervos grandes. CLI, sem interface.",
    )
    parser.add_argument("--config", default=None, help="Caminho do config.yaml (opcional).")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_scan = sub.add_parser("scan", help="Varre, detecta duplicatas e grava relatorio + banco.")
    p_scan.add_argument("--raiz", action="append", help="Raiz a varrer (repetivel). Sobrepoe a config.")
    p_scan.add_argument("--relatorio", default=None, help="Caminho de saida do relatorio JSON.")
    p_scan.set_defaults(func=_cmd_scan)

    p_isolar = sub.add_parser("isolar", help="Move para quarentena os candidatos do relatorio.")
    p_isolar.add_argument("--relatorio", default=None, help="Relatorio JSON de entrada.")
    p_isolar.add_argument("--quarentena", default=None, help="Diretorio de quarentena.")
    p_isolar.add_argument("--execute", action="store_true", help="Move de fato. Sem a flag, dry-run.")
    p_isolar.set_defaults(func=_cmd_isolar)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
