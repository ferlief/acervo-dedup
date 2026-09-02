"""acervo-dedup command line.

  acervo-dedup scan   [--config config.yaml] [--raiz DIR ...]
  acervo-dedup isolar [--relatorio dedup_report.json] [--execute]
  acervo-dedup gui    [--navegador] [--porta N]

'scan' ONLY detects: it walks the disk, runs both passes, writes to the
'duplicatas' table and exports the JSON report. It never moves a file.
'isolar' is the only command that moves anything, and only when called
explicitly with --execute (without the flag it is a dry run that just
prints what it would do).

'gui' opens the graphical interface in a native Windows window (WebView2),
backed by a server bound to 127.0.0.1 only. The interface is a SKIN: it
shells out to these very same subcommands, so it cannot move a file through
any path the CLI does not already expose. Running acervo-dedup with no
arguments at all - what a double-click on the .exe does - opens it too.
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
              f"{duplicados_perceptuais:,} arquivo(s) candidato(s) a REVISAO "
              f"(semelhanca erra: nunca vao para quarentena).\n")

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
    print(f"[quarentena] {resumo['arquivos_para_quarentena']:,} arquivo(s), "
          f"{resumo['bytes_quarentena'] / 1024**3:.2f} GB "
          f"- copia byte-identica, descarte seguro")
    print(f"[revisao]    {resumo['arquivos_para_revisao']:,} arquivo(s), "
          f"{resumo['bytes_revisao'] / 1024**3:.2f} GB "
          f"- parecida, pode ser foto unica: voce decide")
    print(f"[Resultado] Espaco recuperavel total: "
          f"{resumo['bytes_recuperaveis_total'] / 1024**3:.2f} GB")
    if resultado.erros:
        print(f"[AVISO] {len(resultado.erros):,} arquivo(s) com erro de leitura "
              f"(bloqueado/permissao) - nao entraram na comparacao.")
    print(f"{'=' * 70}")
    print(f"[Relatorio] {destino_relatorio.resolve()}")
    print("\n>>> Nada foi movido. 'acervo-dedup isolar --somente quarentena' move so' "
          "o descarte seguro. <<<")
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
    revisao_dir = Path(args.revisao) if args.revisao else cfg.revisao_dir
    destinos = {"quarentena": quarentena_dir, "revisao": revisao_dir}

    print(f"Relatorio:  {relatorio_path}")
    if args.somente in (None, "quarentena"):
        print(f"Quarentena: {quarentena_dir}   (copia byte-identica: descarte seguro)")
    if args.somente in (None, "revisao"):
        print(f"Revisao:    {revisao_dir}   (parecida, pode ser foto unica: voce decide)")
    if args.somente:
        print(f"Filtro:     somente '{args.somente}'")
    print(f"Modo:       {'EXECUTE (vai mover)' if args.execute else 'DRY-RUN (so relatorio)'}\n")

    resultado = executar_isolamento(relatorio, destinos, args.execute, args.somente)

    verbo = "movido" if args.execute else "seria movido"
    for origem, destino, classe in resultado.movidos[:40]:
        print(f"  {verbo} [{classe}]: {origem}  ->  {destino}")
    if len(resultado.movidos) > 40:
        print(f"  ... e mais {len(resultado.movidos) - 40:,} arquivo(s).")
    if resultado.ja_ausentes:
        print(f"\n[Info] {len(resultado.ja_ausentes):,} arquivo(s) do relatorio ja nao "
              f"existem no caminho original (provavelmente ja isolados antes).")
    if resultado.erros:
        print(f"\n[AVISO] {len(resultado.erros):,} arquivo(s) nao puderam ser movidos:")
        for origem, msg in resultado.erros[:20]:
            print(f"    {origem}: {msg}")

    print(f"\n{'=' * 70}")
    for classe in ("quarentena", "revisao"):
        n = resultado.contagem_por_classe.get(classe, 0)
        b = resultado.bytes_por_classe.get(classe, 0)
        if n or args.somente in (None, classe):
            print(f"[{classe:>10}] {n:,} arquivo(s), {b / 1024**3:.2f} GB")
    print(f"[{'TOTAL':>10}] {len(resultado.movidos):,} arquivo(s) "
          f"{'movido(s)' if args.execute else 'a mover'}, "
          f"{resultado.bytes_movidos / 1024**3:.2f} GB")
    print(f"{'=' * 70}")
    if not args.execute:
        print("\n>>> DRY-RUN: nada foi movido. Rode com --execute para isolar de fato. <<<")
    elif resultado.contagem_por_classe.get("revisao"):
        print("\n>>> A pasta de revisao NAO e' descarte. Sao candidatos que podem ser "
              "foto unica; nada ali sai sem voce olhar. <<<")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    """Imported lazily: the GUI pulls in http.server and friends, and a
    plain 'scan' on a big drive should not pay for that import."""
    if args.navegador:
        from .gui import servir

        return servir(args.config, porta=args.porta or 8765, abrir=not args.nao_abrir)

    from .gui import abrir_janela

    return abrir_janela(args.config, porta=args.porta or 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acervo-dedup",
        description="Deteccao de redundancia em acervos grandes. CLI com interface local opcional.",
    )
    parser.add_argument("--config", default=None, help="Caminho do config.yaml (opcional).")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_scan = sub.add_parser("scan", help="Varre, detecta duplicatas e grava relatorio + banco.")
    p_scan.add_argument("--raiz", action="append", help="Raiz a varrer (repetivel). Sobrepoe a config.")
    p_scan.add_argument("--relatorio", default=None, help="Caminho de saida do relatorio JSON.")
    p_scan.set_defaults(func=_cmd_scan)

    p_isolar = sub.add_parser(
        "isolar",
        help="Move os candidatos do relatorio: copia identica -> quarentena, "
             "parecida -> revisao.",
    )
    p_isolar.add_argument("--relatorio", default=None, help="Relatorio JSON de entrada.")
    p_isolar.add_argument("--quarentena", default=None,
                          help="Diretorio de quarentena (copias byte-identicas).")
    p_isolar.add_argument("--revisao", default=None,
                          help="Diretorio de revisao (parecidas: decisao humana).")
    p_isolar.add_argument("--somente", choices=["quarentena", "revisao"], default=None,
                          help="Move so' uma das duas classes. Ex: --somente quarentena "
                               "esvazia o descarte seguro sem tocar na fila de revisao.")
    p_isolar.add_argument("--execute", action="store_true", help="Move de fato. Sem a flag, dry-run.")
    p_isolar.set_defaults(func=_cmd_isolar)

    p_gui = sub.add_parser(
        "gui",
        help="Abre a interface numa janela do Windows (so' 127.0.0.1).",
    )
    p_gui.add_argument("--porta", type=int, default=None,
                       help="Porta do servidor local. Padrao: qualquer livre "
                            "(janela nativa) ou 8765 (--navegador).")
    p_gui.add_argument("--navegador", action="store_true",
                       help="Abre no navegador em vez da janela nativa.")
    p_gui.add_argument("--nao-abrir", action="store_true",
                       help="Com --navegador, so' imprime a URL em vez de abrir.")
    p_gui.set_defaults(func=_cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    # Double-clicking acervo-dedup.exe passes no arguments. A CLI would print
    # usage into a console nobody sees; the sensible thing there is to open
    # the interface. Every explicit invocation keeps CLI behaviour untouched.
    if not argv:
        argv = ["gui"]
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
