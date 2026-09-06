#!/usr/bin/env bash
# Linux installer: virtualenv, package, and a desktop-menu entry.
#
# The Windows counterpart of this is a .zip and a double-click. Linux has no
# equivalent single artifact worth shipping - a PyInstaller bundle links
# against the glibc of the machine that built it - so the supported path here
# is a virtualenv plus a .desktop file, which is what a distro package would
# have produced anyway.
#
# Everything lands under the user's home. No sudo, nothing written outside
# $HOME, and uninstalling is deleting two paths (printed at the end).

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${ACERVO_DEDUP_VENV:-$HOME/.local/share/acervo-dedup/venv}"
APPS="$HOME/.local/share/applications"
ICONES="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP="$APPS/acervo-dedup.desktop"
ICONE="$ICONES/acervo-dedup.svg"

info()  { printf '\033[1;33m==>\033[0m %s\n' "$1"; }
erro()  { printf '\033[1;31m[ERRO]\033[0m %s\n' "$1" >&2; }
ok()    { printf '\033[1;32m  ok\033[0m %s\n' "$1"; }

# --- Python ---------------------------------------------------------------
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  erro "python3 nao encontrado. Instale o Python 3.10 ou mais novo e rode de novo."
  exit 1
fi
VERSAO="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  erro "Python $VERSAO e' antigo demais. O acervo-dedup precisa de 3.10 ou mais novo."
  exit 1
fi
ok "Python $VERSAO em $(command -v "$PY")"

# --- toolkit da janela nativa ---------------------------------------------
# WebKit2GTK is what pywebview draws into on Linux. It is a system package,
# never a wheel: checking here turns a confusing runtime failure into an
# instruction given before anything is installed.
TEM_GTK=0
if "$PY" - <<'EOF' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
EOF
then
  TEM_GTK=1
elif "$PY" - <<'EOF' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.0")
EOF
then
  TEM_GTK=1
fi

if [ "$TEM_GTK" -eq 1 ]; then
  ok "WebKit2GTK presente: a janela nativa vai abrir"
else
  info "WebKit2GTK ausente - a interface vai abrir no navegador em vez de janela propria."
  echo "     Para a janela nativa, instale os pacotes do sistema e rode este script de novo:"
  echo
  if command -v apt >/dev/null 2>&1; then
    echo "       sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1"
  elif command -v dnf >/dev/null 2>&1; then
    echo "       sudo dnf install python3-gobject gtk3 webkit2gtk4.1"
  elif command -v pacman >/dev/null 2>&1; then
    echo "       sudo pacman -S python-gobject gtk3 webkit2gtk-4.1"
  else
    echo "       procure por: python3-gi, gtk3, webkit2gtk (4.1 ou 4.0)"
  fi
  echo
fi

# --- virtualenv -----------------------------------------------------------
# --system-site-packages on purpose: 'gi' is installed by the distro, never
# by pip, and an isolated venv cannot see it. Without this flag the native
# window is unreachable even with every system package in place.
info "Criando o ambiente em $VENV"
mkdir -p "$(dirname "$VENV")"
"$PY" -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
ok "ambiente criado"

info "Instalando o acervo-dedup a partir de $RAIZ"
if [ "$TEM_GTK" -eq 1 ]; then
  "$VENV/bin/python" -m pip install --quiet -e "$RAIZ[gui]"
else
  "$VENV/bin/python" -m pip install --quiet -e "$RAIZ"
fi
ok "instalado"

# --- entrada no menu ------------------------------------------------------
info "Registrando no menu de aplicativos"
mkdir -p "$APPS" "$ICONES"
install -m 0644 "$RAIZ/packaging/linux/icone.svg" "$ICONE"
sed -e "s|__EXEC__|$VENV/bin/acervo-dedup gui|" \
    -e "s|__ICON__|$ICONE|" \
    "$RAIZ/packaging/linux/acervo-dedup.desktop.in" > "$DESKTOP"
chmod 0644 "$DESKTOP"
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "$APPS" >/dev/null 2>&1 || true
ok "atalho em $DESKTOP"

# --- fim ------------------------------------------------------------------
echo
echo "======================================================================"
echo "Pronto."
echo
echo "  Pelo menu:      procure por 'acervo-dedup' entre os aplicativos"
echo "  Pelo terminal:  $VENV/bin/acervo-dedup gui"
echo "  Sem janela:     $VENV/bin/acervo-dedup gui --navegador"
echo
echo "Para desinstalar, apague:"
echo "  $VENV"
echo "  $DESKTOP"
echo "======================================================================"
