"""Native desktop window for the interface.

The window is drawn by pywebview onto whatever the platform provides: a
WebView2 surface on Windows (the Edge runtime that ships with Windows 11),
WebKit2GTK or Qt WebEngine on Linux. The page inside it is the very same one
the browser mode serves - one interface, two shells - so nothing about the
design or the API is duplicated here.

Why an embedded server instead of loading the files straight off disk: the
page needs the JSON API, Server-Sent Events for the live log, and the same
session token guard. A file:// page gets none of that. The server binds to
port 0 (the OS picks a free one) because in this mode nobody ever types the
URL: only the embedded window knows it.

If no window can be opened - pywebview absent, or present but with no GUI
toolkit behind it, the normal state of a fresh Linux install - this degrades
to the browser instead of failing. The interface still works, it just looks
like a tab.
"""

from __future__ import annotations

import logging
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


def _dica_janela_nativa() -> None:
    """What to install to get a real window. Platform-specific because the
    answer is: a pip extra on Windows, a pip extra AND distro packages on
    Linux - pointing a Linux user at pip alone sends them in a circle, since
    WebKit2GTK has no wheel."""
    print('        Para a janela nativa: pip install "acervo-dedup[gui]"', flush=True)
    if sys.platform.startswith("linux"):
        print("        E os pacotes do sistema, que nao vem por pip. Debian/Ubuntu:",
              flush=True)
        print("        sudo apt install python3-gi python3-gi-cairo "
              "gir1.2-gtk-3.0 gir1.2-webkit2-4.1", flush=True)
        print("        O ambiente virtual precisa ver o 'gi' do sistema: crie-o com",
              flush=True)
        print("        python3 -m venv --system-site-packages .venv", flush=True)


def abrir_janela(config_path: str | None, porta: int = 0) -> int:
    """Opens the interface in a native window. Falls back to the browser
    when pywebview is unavailable."""
    if not _tem_pywebview():
        print("[AVISO] pywebview nao instalado - abrindo no navegador.", flush=True)
        _dica_janela_nativa()
        return servir(config_path, porta or 8765, abrir=True)

    import webview

    # pywebview logs a full traceback for every backend it fails to import.
    # On a Linux box with no GUI toolkit that is two stack traces about 'gi'
    # and 'qtpy' before our own one-line explanation - alarming, and not one
    # line of it actionable, since falling back to the browser is the correct
    # outcome. We report the failure ourselves; silence its logger.
    logging.getLogger("pywebview").setLevel(logging.CRITICAL)

    servico = montar(config_path, porta)
    servir_em_thread(servico)

    def _ao_fechar() -> None:
        # Closing the window ends the session: the server dies with it, and
        # a running scan is cancelled rather than orphaned holding the cache
        # SQLite open.
        servico.encerrar()

    # create_window belongs inside the guard, not outside it: a rejected
    # keyword or a missing backend raises HERE, and in a windowed binary
    # there is no console for that traceback to land in - the program would
    # simply vanish with no window and no message. Falling back to the
    # browser turns a silent death into a working interface.
    try:
        janela = webview.create_window(
            "acervo-dedup",
            servico.url,
            width=LARGURA,
            height=ALTURA,
            min_size=(LARGURA_MINIMA, ALTURA_MINIMA),
            background_color="#131010",  # matches the dark theme: no white flash
            text_select=True,            # paths in the report have to be copyable
            confirm_close=False,
        )
        janela.events.closed += _ao_fechar
        # gui=None lets pywebview pick its backend; on Windows that is
        # 'edgechromium' (WebView2), preinstalled on Windows 11.
        webview.start()
    except Exception as e:  # noqa: BLE001 - any backend failure is recoverable
        print(f"[AVISO] Nao foi possivel abrir a janela nativa ({e}).", flush=True)
        print("        Caindo para o navegador.", flush=True)
        _dica_janela_nativa()
        servico.encerrar()
        return servir(config_path, porta or 8765, abrir=True)
    return 0


if __name__ == "__main__":
    sys.exit(abrir_janela(None))
