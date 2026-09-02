"""Native desktop window for the interface.

The window is a WebView2 surface (the Edge runtime that ships with Windows
11) driven by pywebview. The page inside it is the very same one the
browser mode serves - one interface, two shells - so nothing about the
design or the API is duplicated here.

Why an embedded server instead of loading the files straight off disk: the
page needs the JSON API, Server-Sent Events for the live log, and the same
session token guard. A file:// page gets none of that. The server binds to
port 0 (the OS picks a free one) because in this mode nobody ever types the
URL: only the embedded window knows it.

If pywebview is not installed, this degrades to the browser instead of
failing - the interface still works, it just looks like a tab.
"""

from __future__ import annotations

import sys

from .server import montar, servir, servir_em_thread

LARGURA = 1180
ALTURA = 820
LARGURA_MINIMA = 900
ALTURA_MINIMA = 620


def _tem_pywebview() -> bool:
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return True


def abrir_janela(config_path: str | None, porta: int = 0) -> int:
    """Opens the interface in a native window. Falls back to the browser
    when pywebview is unavailable."""
    if not _tem_pywebview():
        print("[AVISO] pywebview nao instalado - abrindo no navegador.", flush=True)
        print("        Para a janela nativa: pip install \"acervo-dedup[gui]\"", flush=True)
        return servir(config_path, porta or 8765, abrir=True)

    import webview

    servico = montar(config_path, porta)
    servir_em_thread(servico)

    janela = webview.create_window(
        "acervo-dedup",
        servico.url,
        width=LARGURA,
        height=ALTURA,
        min_size=(LARGURA_MINIMA, ALTURA_MINIMA),
        background_color="#131010",   # matches the dark theme: no white flash on open
        text_select=True,             # paths in the report have to be copyable
        confirm_close=False,
    )

    def _ao_fechar() -> None:
        # Closing the window ends the session: the server dies with it, and
        # a running scan is cancelled rather than orphaned holding the cache
        # SQLite open.
        servico.encerrar()

    janela.events.closed += _ao_fechar

    try:
        # gui=None lets pywebview pick its backend; on Windows that is
        # 'edgechromium' (WebView2), preinstalled on Windows 11.
        webview.start()
    except Exception as e:  # noqa: BLE001 - any backend failure is recoverable
        print(f"[AVISO] Nao foi possivel abrir a janela nativa ({e}).", flush=True)
        print("        Caindo para o navegador.", flush=True)
        servico.encerrar()
        return servir(config_path, porta or 8765, abrir=True)
    return 0


if __name__ == "__main__":
    sys.exit(abrir_janela(None))
