"""Local server for the graphical interface.

DESIGN. Three decisions that matter more than the code:

1. The GUI imports neither 'exact', 'perceptual', 'quality' nor
   'quarantine'. It runs 'python -m acervo_dedup.cli ...' in a subprocess
   and streams the output. The engine stays the single source of truth,
   and a bug in here cannot move a file on its own.

2. It listens on 127.0.0.1 only, with a session token generated on every
   start plus a Host check. A personal archive does not reach the network
   through a carelessly open port, and no third-party page can trigger an
   'isolar --execute' through a forged browser request.

3. One job at a time. Two concurrent scans over the same SQLite cache and
   the same database is a write race; the button stays locked while a job
   is alive.
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import os
import queue
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..config import load_config

ESTATICOS = Path(__file__).parent / "static"
LIMITE_LINHAS = 4000          # log history kept in memory
CANDIDATOS_POR_GRUPO = 120    # per-group cap sent to the browser
POR_PAGINA_MAX = 200

# Name of the console CLI binary shipped next to the windowed one. On Windows
# the windowed build has no console, so its stdout is not a pipe Python can
# write to - and the live log is precisely that stdout. The window therefore
# always drives its console sibling. Linux and macOS have no windowed/console
# subsystem split, so the sibling is the same binary minus the extension; the
# indirection still holds there and keeps one code path for both.
CLI_CONGELADO = "acervo-dedup.exe" if os.name == "nt" else "acervo-dedup"


def executavel_do_motor() -> str:
    """Which program runs 'scan'/'isolar'. Unfrozen it is the interpreter;
    frozen it is the console binary next door, with sys.executable as the
    fallback for a single-binary build."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    irmao = Path(sys.executable).with_name(CLI_CONGELADO)
    return str(irmao) if irmao.exists() else sys.executable


# --------------------------------------------------------------------------
# Event bus (SSE)
# --------------------------------------------------------------------------
class Barramento:
    """Publishes events to every open tab. A slow subscriber never holds
    the job back: a full queue drops the event instead of blocking."""

    def __init__(self) -> None:
        self._assinantes: list[queue.Queue] = []
        self._lock = threading.Lock()

    def assinar(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._assinantes.append(q)
        return q

    def cancelar(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._assinantes:
                self._assinantes.remove(q)

    def publicar(self, evento: dict) -> None:
        with self._lock:
            alvos = list(self._assinantes)
        for q in alvos:
            try:
                q.put_nowait(evento)
            except queue.Full:
                pass


# --------------------------------------------------------------------------
# Running the CLI
# --------------------------------------------------------------------------
class Job:
    def __init__(self, tipo: str, argv: list[str], rotulo: str) -> None:
        self.tipo = tipo              # 'scan' | 'isolar'
        self.argv = argv
        self.rotulo = rotulo
        self.linhas: list[str] = []
        self.estado = "rodando"       # rodando | concluido | falhou | cancelado
        self.codigo: int | None = None
        self.iniciado_em = time.time()
        self.terminado_em: float | None = None
        self.proc: subprocess.Popen | None = None

    def como_dict(self, ultimas: int | None = None) -> dict:
        linhas = self.linhas if ultimas is None else self.linhas[-ultimas:]
        return {
            "tipo": self.tipo,
            "rotulo": self.rotulo,
            "estado": self.estado,
            "codigo": self.codigo,
            "iniciado_em": self.iniciado_em,
            "terminado_em": self.terminado_em,
            "linhas": linhas,
            "comando": " ".join(self.argv),
        }


class Motor:
    """Thin facade over the CLI. Holds the current job and the last one."""

    def __init__(self, config_path: str | None, barramento: Barramento) -> None:
        self.config_path = config_path
        self.barramento = barramento
        self.job: Job | None = None
        self._lock = threading.Lock()
        self._cache_relatorio: tuple[str, float, dict] | None = None

    # -- configuration -----------------------------------------------------
    def config(self):
        return load_config(self.config_path)

    def config_como_dict(self) -> dict:
        try:
            cfg = self.config()
        except Exception as e:  # a broken config must not kill the interface
            return {"erro": str(e), "caminho": self.config_path}
        return {
            "erro": None,
            "caminho": str(Path(self.config_path).resolve()) if self.config_path else None,
            "banco": str(cfg.banco_caminho),
            "raizes": [str(r) for r in cfg.varredura_raizes],
            "cache": str(cfg.cache_caminho),
            "quarentena": str(cfg.quarentena_dir),
            "revisao": str(cfg.revisao_dir),
            "relatorio": str(cfg.relatorio_saida),
            "threads": cfg.threads,
            "distancia_maxima": cfg.distancia_maxima,
            "razao_aspecto_maxima": cfg.razao_aspecto_maxima,
            "extensoes": sorted(cfg.todas_extensoes),
        }

    # -- jobs --------------------------------------------------------------
    def ocupado(self) -> bool:
        return self.job is not None and self.job.estado == "rodando"

    def _argv_base(self) -> list[str]:
        # Frozen (PyInstaller) there is no interpreter to hand '-m' to: the
        # bundled CLI executable takes the subcommand directly. Unfrozen,
        # sys.executable is python and the module has to be named. Either way
        # the child is the same CLI, never this package.
        argv: list[str] = [] if getattr(sys, "frozen", False) else ["-m", "acervo_dedup.cli"]
        if self.config_path:
            argv += ["--config", str(self.config_path)]
        return argv

    def iniciar(self, tipo: str, extras: list[str], rotulo: str) -> Job:
        with self._lock:
            if self.ocupado():
                raise RuntimeError("Ja existe uma operacao em andamento.")
            argv = self._argv_base() + [tipo] + extras
            job = Job(tipo, argv, rotulo)
            self.job = job
        threading.Thread(target=self._rodar, args=(job,), daemon=True).start()
        return job

    def _rodar(self, job: Job) -> None:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        criacao = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flash on Windows
        self.barramento.publicar({"tipo": "job", "job": job.como_dict(ultimas=0)})
        try:
            job.proc = subprocess.Popen(
                [executavel_do_motor(), *job.argv],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=criacao,
            )
        except OSError as e:
            job.estado = "falhou"
            job.codigo = -1
            job.terminado_em = time.time()
            self._emitir_linha(job, f"[ERRO] Nao foi possivel iniciar o motor: {e}")
            self.barramento.publicar({"tipo": "job", "job": job.como_dict(ultimas=0)})
            return

        assert job.proc.stdout is not None
        for linha in job.proc.stdout:
            self._emitir_linha(job, linha.rstrip("\n"))
        job.proc.wait()
        job.codigo = job.proc.returncode
        job.terminado_em = time.time()
        if job.estado != "cancelado":
            job.estado = "concluido" if job.codigo == 0 else "falhou"
        self._cache_relatorio = None
        self.barramento.publicar({"tipo": "job", "job": job.como_dict(ultimas=0)})

    def _emitir_linha(self, job: Job, texto: str) -> None:
        job.linhas.append(texto)
        if len(job.linhas) > LIMITE_LINHAS:
            del job.linhas[: len(job.linhas) - LIMITE_LINHAS]
        self.barramento.publicar({"tipo": "linha", "texto": texto})

    def cancelar(self) -> bool:
        job = self.job
        if job is None or job.estado != "rodando" or job.proc is None:
            return False
        job.estado = "cancelado"
        try:
            job.proc.terminate()
        except OSError:
            return False
        return True

    # -- report ------------------------------------------------------------
    def caminho_relatorio(self) -> Path:
        return self.config().relatorio_saida

    def relatorio(self) -> dict | None:
        caminho = self.caminho_relatorio()
        if not caminho.exists():
            return None
        mtime = caminho.stat().st_mtime
        chave = str(caminho.resolve())
        if (self._cache_relatorio
                and self._cache_relatorio[0] == chave
                and self._cache_relatorio[1] == mtime):
            return self._cache_relatorio[2]
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        self._cache_relatorio = (chave, mtime, dados)
        return dados


# --------------------------------------------------------------------------
# Group filtering and pagination
# --------------------------------------------------------------------------
def _candidatos_de(grupo: dict) -> list[dict]:
    """Same tolerance 'isolar' has: 'candidatos_isolamento' is the current
    name, 'candidatos_quarentena' predates the two destinations."""
    if "candidatos_isolamento" in grupo:
        return grupo["candidatos_isolamento"]
    return grupo.get("candidatos_quarentena", [])


def _grupo_casa(grupo: dict, busca: str) -> bool:
    if not busca:
        return True
    alvo = busca.lower()
    rep = grupo.get("representante", {})
    if alvo in str(rep.get("caminho", "")).lower():
        return True
    if alvo in str(rep.get("sha256", "")).lower():
        return True
    for c in _candidatos_de(grupo):
        if alvo in str(c.get("caminho", "")).lower():
            return True
    return False


def paginar_grupos(relatorio: dict, params: dict) -> dict:
    grupos = relatorio.get("duplicate_groups", [])
    metodo = (params.get("metodo") or ["todos"])[0]
    ordem = (params.get("ordem") or ["espaco"])[0]
    busca = (params.get("busca") or [""])[0].strip()
    pagina = max(1, int((params.get("pagina") or ["1"])[0] or 1))
    por_pagina = min(POR_PAGINA_MAX, max(1, int((params.get("por_pagina") or ["25"])[0] or 25)))

    filtrados = [
        g for g in grupos
        if (metodo in ("todos", "") or g.get("metodo") == metodo) and _grupo_casa(g, busca)
    ]
    if ordem == "espaco":
        filtrados.sort(key=lambda g: g.get("bytes_recuperaveis", 0), reverse=True)
    elif ordem == "membros":
        filtrados.sort(key=lambda g: len(_candidatos_de(g)), reverse=True)

    total = len(filtrados)
    inicio = (pagina - 1) * por_pagina
    recorte = filtrados[inicio: inicio + por_pagina]

    saida = []
    for g in recorte:
        candidatos = _candidatos_de(g)
        saida.append({
            "grupo_id": g.get("grupo_id"),
            "metodo": g.get("metodo"),
            "destino": g.get("destino"),
            "bytes_recuperaveis": g.get("bytes_recuperaveis", 0),
            "representante": g.get("representante", {}),
            "candidatos": candidatos[:CANDIDATOS_POR_GRUPO],
            "candidatos_total": len(candidatos),
        })
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": max(1, (total + por_pagina - 1) // por_pagina),
        "grupos": saida,
    }


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "acervo-dedup-gui"
    protocol_version = "HTTP/1.1"

    motor: Motor
    barramento: Barramento
    token: str

    def log_message(self, formato, *args):  # silence http.server's default log
        pass

    def handle_one_request(self):
        """A browser dropping a keep-alive connection (tab closed, page
        reloaded, SSE stream cut) surfaces as ConnectionAbortedError deep
        inside socketserver, which prints a full traceback and reads like a
        crash. It is routine: swallow it and close the connection."""
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    # -- guards ------------------------------------------------------------
    def _host_local(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost", "[::1]", "::1")

    def _token_ok(self, params: dict) -> bool:
        do_header = self.headers.get("X-Dedup-Token")
        do_query = (params.get("t") or [None])[0]
        return secrets.compare_digest(do_header or do_query or "", self.token)

    # -- responses ---------------------------------------------------------
    def _json(self, dados, codigo: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, mensagem: str, codigo: int = 400) -> None:
        self._json({"erro": mensagem}, codigo)

    def _corpo_json(self) -> dict:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not tamanho:
            return {}
        try:
            return json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # -- GET ---------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        if not self._host_local():
            self._erro("Host nao autorizado.", 403)
            return
        url = urlparse(self.path)
        params = parse_qs(url.query)
        rota = url.path

        if rota in ("/", "/index.html"):
            self._servir_estatico("index.html")
            return
        if rota.startswith("/estatico/"):
            self._servir_estatico(rota[len("/estatico/"):])
            return
        if not rota.startswith("/api/"):
            self._erro("Rota desconhecida.", 404)
            return
        if not self._token_ok(params):
            self._erro("Token de sessao invalido. Reabra a interface pelo terminal.", 403)
            return

        if rota == "/api/estado":
            self._json(self._estado())
        elif rota == "/api/grupos":
            rel = self.motor.relatorio()
            if rel is None:
                self._erro("Nenhum relatorio. Rode a varredura primeiro.", 404)
                return
            self._json(paginar_grupos(rel, params))
        elif rota == "/api/eventos":
            self._sse()
        else:
            self._erro("Rota desconhecida.", 404)

    # -- POST --------------------------------------------------------------
    def do_POST(self):  # noqa: N802
        if not self._host_local():
            self._erro("Host nao autorizado.", 403)
            return
        url = urlparse(self.path)
        params = parse_qs(url.query)
        if not self._token_ok(params):
            self._erro("Token de sessao invalido. Reabra a interface pelo terminal.", 403)
            return

        corpo = self._corpo_json()
        rota = url.path
        try:
            if rota == "/api/scan":
                extras: list[str] = []
                for raiz in corpo.get("raizes") or []:
                    if str(raiz).strip():
                        extras += ["--raiz", str(raiz).strip()]
                job = self.motor.iniciar("scan", extras, "Varredura")
            elif rota == "/api/isolar":
                somente = corpo.get("somente")
                if somente not in (None, "", "quarentena", "revisao"):
                    self._erro("Classe invalida.")
                    return
                execute = bool(corpo.get("execute"))
                if execute and corpo.get("confirmacao") != "ISOLAR":
                    self._erro("Confirmacao ausente: execute exige a palavra ISOLAR.", 428)
                    return
                extras = []
                if somente:
                    extras += ["--somente", somente]
                if execute:
                    extras.append("--execute")
                alvo = somente or "quarentena + revisao"
                modo = "EXECUTE" if execute else "dry-run"
                job = self.motor.iniciar("isolar", extras, f"Isolar {alvo} - {modo}")
            elif rota == "/api/cancelar":
                self._json({"cancelado": self.motor.cancelar()})
                return
            else:
                self._erro("Rota desconhecida.", 404)
                return
        except RuntimeError as e:
            self._erro(str(e), 409)
            return
        self._json({"job": job.como_dict(ultimas=0)})

    # -- payload builders ----------------------------------------------------
    def _estado(self) -> dict:
        cfg = self.motor.config_como_dict()
        try:
            relatorio = self.motor.relatorio()
        except (OSError, ValueError) as e:
            relatorio = None
            cfg["aviso_relatorio"] = str(e)
        info_rel = {"existe": False, "caminho": cfg.get("relatorio")}
        if relatorio is not None:
            erros = relatorio.get("erros", [])
            info_rel = {
                "existe": True,
                "caminho": cfg.get("relatorio"),
                "gerado_em": relatorio.get("gerado_em"),
                "raizes_varridas": relatorio.get("raizes_varridas", []),
                "resumo": relatorio.get("resumo", {}),
                "erros": erros[:200],
                "erros_total": len(erros),
                "grupos_total": len(relatorio.get("duplicate_groups", [])),
            }
        job = self.motor.job
        return {
            "config": cfg,
            "relatorio": info_rel,
            "job": job.como_dict(ultimas=400) if job else None,
        }

    def _sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        fila = self.barramento.assinar()
        try:
            while True:
                try:
                    evento = fila.get(timeout=15)
                    dados = json.dumps(evento, ensure_ascii=False)
                    self.wfile.write(("data: " + dados + "\n\n").encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.barramento.cancelar(fila)

    def _servir_estatico(self, relativo: str) -> None:
        alvo = (ESTATICOS / relativo).resolve()
        try:
            alvo.relative_to(ESTATICOS.resolve())
        except ValueError:
            self._erro("Caminho invalido.", 403)
            return
        if not alvo.is_file():
            self._erro("Arquivo nao encontrado.", 404)
            return
        tipo = mimetypes.guess_type(str(alvo))[0] or "application/octet-stream"
        corpo = alvo.read_bytes()
        if alvo.name == "index.html":
            corpo = corpo.replace(b"__TOKEN__", self.token.encode("ascii"))
        self.send_response(200)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)


def _porta_livre(preferida: int, tentativas: int = 20) -> int:
    for offset in range(tentativas):
        porta = preferida + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", porta))
                return porta
            except OSError:
                continue
    raise RuntimeError(
        f"Nenhuma porta livre entre {preferida} e {preferida + tentativas}."
    )


@dataclass
class Servico:
    """A running server plus everything needed to reach and stop it. The
    desktop window and the browser mode share this; only who owns the main
    thread differs."""

    servidor: http.server.ThreadingHTTPServer
    motor: Motor
    url: str
    porta: int

    def encerrar(self) -> None:
        self.motor.cancelar()
        self.servidor.shutdown()
        self.servidor.server_close()


def montar(config_path: str | None, porta: int = 8765) -> Servico:
    """Binds the server without serving yet. Port 0 asks the OS for any free
    port - what the desktop window wants, since nobody types that URL."""
    barramento = Barramento()
    motor = Motor(config_path, barramento)
    token = secrets.token_urlsafe(24)

    porta = 0 if porta == 0 else _porta_livre(porta)
    classe = type("HandlerConfigurado", (Handler,), {
        "motor": motor,
        "barramento": barramento,
        "token": token,
    })
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", porta), classe)
    servidor.daemon_threads = True
    porta = servidor.server_address[1]
    return Servico(
        servidor=servidor,
        motor=motor,
        url=f"http://127.0.0.1:{porta}/?t={token}",
        porta=porta,
    )


def servir_em_thread(servico: Servico) -> threading.Thread:
    t = threading.Thread(target=servico.servidor.serve_forever, daemon=True)
    t.start()
    return t


def _abrir_navegador(url: str) -> None:
    """webbrowser.open reports success the moment it hands the URL to a
    helper (gio, xdg-open), even when that helper then fails - the normal
    case on a minimal Linux box, and always under WSL. There is no reliable
    signal to branch on, so this never claims the browser opened; the caller
    prints the address unconditionally and says to copy it if nothing
    appeared."""
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 - having no browser is not fatal
        pass


def servir(config_path: str | None, porta: int = 8765, abrir: bool = True) -> int:
    """Browser mode: this process serves until Ctrl+C."""
    servico = montar(config_path, porta)
    # flush=True: with stdout redirected to a pipe Python block-buffers, and
    # the URL would only surface once the server stops - useless, since that
    # URL carries the session token needed to open the interface at all.
    print("acervo-dedup - interface local", flush=True)
    print(f"  {servico.url}", flush=True)
    print("  Ouvindo so' em 127.0.0.1. Ctrl+C para encerrar.\n", flush=True)
    if abrir:
        print("  Se o navegador nao abrir sozinho, copie o endereco acima.", flush=True)
        threading.Timer(0.4, _abrir_navegador, args=(servico.url,)).start()
    try:
        servico.servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando interface.")
    finally:
        servico.encerrar()
    return 0
