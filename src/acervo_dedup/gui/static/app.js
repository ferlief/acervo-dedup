/* =========================================================================
   acervo-dedup - interface layer

   There is no business rule in here. All this file does is draw the state
   /api/estado returns and fire the CLI's two commands.
   ========================================================================= */
(() => {
  "use strict";

  const TOKEN = document.body.dataset.token;
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));

  const estado = {
    config: null,
    relatorio: null,
    job: null,
    tela: "varredura",
    autoRolagem: true,
    grupos: { pagina: 1, paginas: 1, metodo: "todos", ordem: "espaco", busca: "" },
  };

  // --------------------------------------------------------------- network
  async function api(rota, opcoes = {}) {
    const resposta = await fetch(rota, {
      ...opcoes,
      headers: {
        "Content-Type": "application/json",
        "X-Dedup-Token": TOKEN,
        ...(opcoes.headers || {}),
      },
    });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) throw new Error(dados.erro || `Falha HTTP ${resposta.status}`);
    return dados;
  }

  // ------------------------------------------------------------ formatting
  const nf = new Intl.NumberFormat("pt-BR");
  const nf2 = new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const gb = (bytes) => (bytes || 0) / 1024 ** 3;

  function tamanho(bytes) {
    const b = bytes || 0;
    if (b < 1024) return `${b} B`;
    if (b < 1024 ** 2) return `${nf2.format(b / 1024)} KB`;
    if (b < 1024 ** 3) return `${nf2.format(b / 1024 ** 2)} MB`;
    return `${nf2.format(b / 1024 ** 3)} GB`;
  }

  function esc(texto) {
    return String(texto ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c]));
  }

  function dataHora(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  }

  /* Animated count-up: the number climbs from zero to its value, so the
     eye notices the field changed after a fresh scan. */
  function anima(el, alvo, decimais = 0) {
    if (!el) return;
    const reduzido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const fmt = (v) => (decimais ? nf2.format(v) : nf.format(Math.round(v)));
    if (reduzido || !Number.isFinite(alvo)) {
      el.textContent = fmt(alvo || 0);
      return;
    }
    const inicio = performance.now();
    const dur = 620;
    const passo = (agora) => {
      const t = Math.min(1, (agora - inicio) / dur);
      const suave = 1 - Math.pow(1 - t, 3);
      el.textContent = fmt(alvo * suave);
      if (t < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  }

  // -------------------------------------------------------------- toasts
  function torrada(mensagem, tipo = "") {
    const el = document.createElement("div");
    el.className = `torrada ${tipo ? "t-" + tipo : ""}`;
    el.textContent = mensagem;
    $("#torradas").appendChild(el);
    setTimeout(() => {
      el.style.transition = "opacity .3s, transform .3s";
      el.style.opacity = "0";
      el.style.transform = "translateX(20px)";
      setTimeout(() => el.remove(), 320);
    }, 5200);
  }

  // ---------------------------------------------------------- navigation
  const TITULOS = {
    varredura: ["Varredura", "Duas passadas sobre o disco. Nada é movido nesta etapa."],
    resultado: ["Resultado", "Quanto dá para recuperar, separado por grau de certeza."],
    grupos: ["Conferência", "Cada grupo traz o representante e o motivo da escolha."],
    isolar: ["Isolar", "Move para quarentena ou revisão. Dry-run por padrão."],
  };

  function irPara(tela) {
    estado.tela = tela;
    $$(".tela").forEach((s) => s.classList.toggle("ativa", s.id === `tela-${tela}`));
    $$(".passo").forEach((b) =>
      b.setAttribute("aria-current", b.dataset.tela === tela ? "page" : "false")
    );
    const [t, s] = TITULOS[tela];
    $("#titulo").textContent = t;
    $("#subtitulo").textContent = s;
    if (tela === "grupos") carregarGrupos();
  }

  $$(".passo").forEach((b) =>
    b.addEventListener("click", () => {
      if (!b.disabled) irPara(b.dataset.tela);
    })
  );

  // ------------------------------------------------------------- console
  function classeLinha(linha) {
    if (/^\[ERRO\]/.test(linha)) return "l-erro";
    if (/^\s*\[AVISO\]/.test(linha)) return "l-aviso";
    if (/^\[\s*revisao\s*\]|^\[revisao\]/.test(linha)) return "l-aviso";
    if (/^\[\s*quarentena\s*\]|^\[quarentena\]/.test(linha)) return "l-ok";
    if (/^>>>/.test(linha)) return "l-info";
    if (/^=+$/.test(linha.trim())) return "l-info";
    if (/^\[(Passada|Banco|Resultado|Relatorio|TOTAL)/.test(linha)) return "l-titulo";
    return "";
  }

  function alvoConsole() {
    return estado.tela === "isolar" || (estado.job && estado.job.tipo === "isolar")
      ? {
          corpo: $("#console-isolar-corpo"),
          vazio: $("#console-isolar-vazio"),
          barra: $("#barra-atividade-isolar"),
          comando: $("#console-isolar-comando"),
        }
      : {
          corpo: $("#console-corpo"),
          vazio: $("#console-vazio"),
          barra: $("#barra-atividade"),
          comando: $("#console-comando"),
        };
  }

  function escreverLinhas(linhas, { substituir = false } = {}) {
    const alvo = alvoConsole();
    if (!linhas.length && substituir) {
      alvo.corpo.innerHTML = "";
      alvo.corpo.hidden = true;
      alvo.vazio.hidden = false;
      return;
    }
    alvo.vazio.hidden = true;
    alvo.corpo.hidden = false;
    if (substituir) alvo.corpo.innerHTML = "";
    const fragmento = document.createDocumentFragment();
    for (const linha of linhas) {
      const span = document.createElement("span");
      const cls = classeLinha(linha);
      if (cls) span.className = cls;
      span.textContent = linha + "\n";
      fragmento.appendChild(span);
    }
    alvo.corpo.appendChild(fragmento);
    if (estado.autoRolagem) alvo.corpo.scrollTop = alvo.corpo.scrollHeight;
  }

  $("#btn-limpar").addEventListener("click", (e) => {
    estado.autoRolagem = !estado.autoRolagem;
    e.currentTarget.textContent = `Rolagem automática: ${estado.autoRolagem ? "ligada" : "desligada"}`;
  });

  // -------------------------------------------------------- header badge
  const SELOS = {
    rodando: ["selo-info selo-vivo", "em execução"],
    concluido: ["selo-quarentena", "concluído"],
    falhou: ["selo-perigo", "falhou"],
    cancelado: ["selo-neutro", "cancelado"],
  };

  function pintarJob(job, { comLinhas = false } = {}) {
    estado.job = job;
    const selo = $("#selo-estado");
    const rodando = job && job.estado === "rodando";

    if (!job) {
      selo.className = "selo selo-neutro";
      $("#selo-texto").textContent = "ocioso";
    } else {
      const [cls, texto] = SELOS[job.estado] || ["selo-neutro", job.estado];
      selo.className = `selo ${cls}`;
      $("#selo-texto").textContent = `${job.rotulo} · ${texto}`;
    }

    $("#btn-cancelar").hidden = !rodando;
    $$("#btn-scan, [data-isolar]").forEach((b) => (b.disabled = !!rodando));

    const btnScan = $("#btn-scan");
    btnScan.innerHTML = rodando && job.tipo === "scan"
      ? '<span class="girador"></span> Varrendo…'
      : btnScan.dataset.rotuloOriginal;

    const alvo = alvoConsole();
    alvo.barra.hidden = !rodando;
    if (job) alvo.comando.textContent = "python " + job.comando;
    if (comLinhas && job) escreverLinhas(job.linhas || [], { substituir: true });
  }

  // ------------------------------------------------------- configuration
  function pintarConfig(cfg) {
    estado.config = cfg;
    if (cfg.erro) {
      torrada(`Config inválida: ${cfg.erro}`, "erro");
      return;
    }
    $("#cfg-caminho").textContent = cfg.caminho || "padrões internos";
    $("#cfg-banco").textContent = cfg.banco;
    $("#cfg-raizes").textContent = cfg.raizes.length
      ? cfg.raizes.join(" · ")
      : "não definidas";
    $("#cfg-distancia").textContent = `hamming ≤ ${cfg.distancia_maxima} · proporção ≤ ${cfg.razao_aspecto_maxima}`;
    $("#q-caminho").textContent = cfg.quarentena;
    $("#r-caminho").textContent = cfg.revisao;
    $("#i-q-caminho").textContent = cfg.quarentena;
    $("#i-r-caminho").textContent = cfg.revisao;
    $("#rel-caminho").textContent = cfg.relatorio;
    if (!$("#raizes").value && cfg.raizes.length) {
      $("#raizes").placeholder = cfg.raizes.join("; ");
    }
  }

  // -------------------------------------------------------------- report
  function pintarRelatorio(rel) {
    estado.relatorio = rel;
    const temRelatorio = !!(rel && rel.existe);

    $$(".passo").forEach((b) => {
      if (b.dataset.tela !== "varredura") b.disabled = !temRelatorio;
    });
    $("#passos").querySelector('[data-tela="varredura"]').classList.toggle("concluido", temRelatorio);

    if (!temRelatorio) return;

    const r = rel.resumo || {};
    anima($("#q-gb"), gb(r.bytes_quarentena), 2);
    anima($("#r-gb"), gb(r.bytes_revisao), 2);
    anima($("#q-arquivos"), r.arquivos_para_quarentena || 0);
    anima($("#r-arquivos"), r.arquivos_para_revisao || 0);
    anima($("#i-q-arquivos"), r.arquivos_para_quarentena || 0);
    anima($("#i-r-arquivos"), r.arquivos_para_revisao || 0);
    anima($("#m-grupos-exatos"), r.grupos_exatos || 0);
    anima($("#m-grupos-perceptuais"), r.grupos_perceptuais || 0);
    anima($("#m-total-gb"), gb(r.bytes_recuperaveis_total), 2);
    anima($("#m-erros"), rel.erros_total || 0);
    $("#m-total-arquivos").textContent =
      `${nf.format(r.arquivos_propostos_isolamento || 0)} arquivo(s) propostos`;
    $("#rel-data").textContent = dataHora(rel.gerado_em);

    const temErros = (rel.erros_total || 0) > 0;
    $("#aviso-erros").hidden = !temErros;
    if (temErros) {
      $("#erros-titulo").textContent =
        `${nf.format(rel.erros_total)} arquivo(s) com erro de leitura`;
      $("#erros-lista").textContent = (rel.erros || [])
        .map((e) => `${e.caminho}  —  ${e.mensagem}`)
        .join("\n");
    }

    const semCandidatos =
      !(r.arquivos_para_quarentena || 0) && !(r.arquivos_para_revisao || 0);
    $$("[data-isolar]").forEach((b) => {
      const classe = b.dataset.isolar;
      const n = classe === "quarentena"
        ? r.arquivos_para_quarentena || 0
        : r.arquivos_para_revisao || 0;
      b.disabled = !n || semCandidatos;
      b.title = n ? "" : "Nenhum candidato desta classe no relatório.";
    });
  }

  // -------------------------------------------------------------- groups
  const CANDIDATO_LIMITE_VISIVEL = 12;

  function linhaMembro(m, papel, classe) {
    const distancia =
      m.distancia === null || m.distancia === undefined
        ? ""
        : ` · distância ${m.distancia}`;
    return `
      <div class="membro">
        <span class="membro-papel ${classe}">${papel}</span>
        <div>
          <div class="membro-caminho">${esc(m.caminho)}</div>
          <div class="membro-motivo">${esc(m.motivo || "—")}${distancia}</div>
        </div>
        <span class="membro-tamanho">${tamanho(m.tamanho)}</span>
      </div>`;
  }

  function cartaoGrupo(g) {
    const exato = g.metodo === "exato";
    const selo = exato
      ? '<span class="selo selo-quarentena"><span class="selo-ponto"></span>quarentena</span>'
      : '<span class="selo selo-revisao"><span class="selo-ponto"></span>revisão</span>';
    const visiveis = g.candidatos.slice(0, CANDIDATO_LIMITE_VISIVEL);
    const restantes = g.candidatos_total - visiveis.length;
    return `
      <details class="grupo ${exato ? "g-exato" : "g-perceptual"}">
        <summary class="grupo-cabeca">
          <svg class="grupo-seta" width="14" height="14" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 6l6 6-6 6" />
          </svg>
          <div class="grupo-id">
            <div class="grupo-caminho">${esc(g.representante.caminho || "")}</div>
            <div class="grupo-meta">
              ${esc(g.metodo)} · ${nf.format(g.candidatos_total)} candidato(s) ·
              <span class="mono">${esc(String(g.grupo_id).slice(0, 16))}</span>
            </div>
          </div>
          ${selo}
          <span class="grupo-espaco">${tamanho(g.bytes_recuperaveis)}</span>
        </summary>
        <div class="grupo-corpo">
          ${linhaMembro(g.representante, "fica", "rep")}
          ${visiveis.map((c) => linhaMembro(c, exato ? "quarentena" : "revisão", "cand")).join("")}
          ${restantes > 0
            ? `<div class="membro"><span></span><span class="tenue">…e mais ${nf.format(restantes)} candidato(s) neste grupo.</span><span></span></div>`
            : ""}
        </div>
      </details>`;
  }

  async function carregarGrupos() {
    const alvo = $("#grupos");
    alvo.innerHTML = Array.from({ length: 5 }, () => '<div class="esqueleto"></div>').join("");
    const q = new URLSearchParams({
      pagina: estado.grupos.pagina,
      metodo: estado.grupos.metodo,
      ordem: estado.grupos.ordem,
      busca: estado.grupos.busca,
      por_pagina: 25,
    });
    try {
      const dados = await api(`/api/grupos?${q}`);
      estado.grupos.paginas = dados.paginas;
      $("#grupos-contagem").textContent = `${nf.format(dados.total)} grupo(s)`;
      if (!dados.grupos.length) {
        alvo.innerHTML = `
          <div class="vazio">
            <div class="vazio-icone">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
            </div>
            <h3>Nenhum grupo com esse filtro</h3>
            <p>Ajuste a busca ou volte para “Todos”.</p>
          </div>`;
      } else {
        alvo.innerHTML = dados.grupos.map(cartaoGrupo).join("");
      }
      $("#paginacao").hidden = dados.paginas <= 1;
      $("#pag-info").textContent = `página ${dados.pagina} de ${dados.paginas}`;
      $("#pag-anterior").disabled = dados.pagina <= 1;
      $("#pag-proxima").disabled = dados.pagina >= dados.paginas;
    } catch (e) {
      alvo.innerHTML = `<div class="vazio"><h3>Não deu para carregar</h3><p>${esc(e.message)}</p></div>`;
    }
  }

  let temporizadorBusca = null;
  $("#busca").addEventListener("input", (e) => {
    clearTimeout(temporizadorBusca);
    temporizadorBusca = setTimeout(() => {
      estado.grupos.busca = e.target.value;
      estado.grupos.pagina = 1;
      carregarGrupos();
    }, 260);
  });

  function ligarSegmentado(id, chave) {
    $(`#${id}`).addEventListener("click", (e) => {
      const botao = e.target.closest("button");
      if (!botao) return;
      $$(`#${id} button`).forEach((b) => b.setAttribute("aria-pressed", String(b === botao)));
      estado.grupos[chave] = botao.dataset[chave];
      estado.grupos.pagina = 1;
      carregarGrupos();
    });
  }
  ligarSegmentado("filtro-metodo", "metodo");
  ligarSegmentado("filtro-ordem", "ordem");

  $("#pag-anterior").addEventListener("click", () => {
    estado.grupos.pagina = Math.max(1, estado.grupos.pagina - 1);
    carregarGrupos();
  });
  $("#pag-proxima").addEventListener("click", () => {
    estado.grupos.pagina = Math.min(estado.grupos.paginas, estado.grupos.pagina + 1);
    carregarGrupos();
  });

  // ------------------------------------------------------------- actions
  const btnScan = $("#btn-scan");
  btnScan.dataset.rotuloOriginal = btnScan.innerHTML;

  btnScan.addEventListener("click", async () => {
    const raizes = $("#raizes")
      .value.split(/[;\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      escreverLinhas([], { substituir: true });
      const { job } = await api("/api/scan", {
        method: "POST",
        body: JSON.stringify({ raizes }),
      });
      pintarJob(job, { comLinhas: true });
    } catch (e) {
      torrada(e.message, "erro");
    }
  });

  $("#btn-cancelar").addEventListener("click", async () => {
    try {
      await api("/api/cancelar", { method: "POST", body: "{}" });
      torrada("Operação interrompida.");
    } catch (e) {
      torrada(e.message, "erro");
    }
  });

  // --- isolar: dry-run fires directly, execute only through the modal ---
  let pendente = null;

  async function dispararIsolar(somente, execute, confirmacao) {
    try {
      escreverLinhas([], { substituir: true });
      const { job } = await api("/api/isolar", {
        method: "POST",
        body: JSON.stringify({ somente, execute, confirmacao }),
      });
      pintarJob(job, { comLinhas: true });
    } catch (e) {
      torrada(e.message, "erro");
    }
  }

  $$("[data-isolar]").forEach((botao) =>
    botao.addEventListener("click", () => {
      const somente = botao.dataset.isolar;
      if (botao.dataset.modo === "dry") {
        irPara("isolar");
        dispararIsolar(somente, false, null);
        return;
      }
      pendente = somente;
      const r = (estado.relatorio && estado.relatorio.resumo) || {};
      const n = somente === "quarentena"
        ? r.arquivos_para_quarentena || 0
        : r.arquivos_para_revisao || 0;
      const destino = somente === "quarentena"
        ? estado.config.quarentena
        : estado.config.revisao;
      $("#modal-titulo").textContent = `Mover ${nf.format(n)} arquivo(s) para ${somente}?`;
      $("#modal-texto").innerHTML =
        `Destino: <span class="mono">${esc(destino)}</span>. Os arquivos saem do lugar original ` +
        `e a estrutura de subpastas é recriada no destino.`;
      $("#modal-aviso-texto").innerHTML =
        somente === "revisao"
          ? "<b>Revisão não é descarte.</b> São candidatos que a semelhança apontou e que podem ser foto única — nada sai dali sem você olhar."
          : "Cópias byte-idênticas. O original de cada grupo permanece no lugar; só as cópias se movem.";
      $("#modal-confirmacao").value = "";
      $("#modal-confirmar").disabled = true;
      $("#modal").hidden = false;
      $("#modal-confirmacao").focus();
    })
  );

  $("#modal-confirmacao").addEventListener("input", (e) => {
    $("#modal-confirmar").disabled = e.target.value.trim().toUpperCase() !== "ISOLAR";
  });
  $("#modal-confirmacao").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !$("#modal-confirmar").disabled) $("#modal-confirmar").click();
  });

  function fecharModal() {
    $("#modal").hidden = true;
    pendente = null;
  }
  $("#modal-cancelar").addEventListener("click", fecharModal);
  $("#modal").addEventListener("click", (e) => {
    if (e.target === $("#modal")) fecharModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#modal").hidden) fecharModal();
  });
  $("#modal-confirmar").addEventListener("click", () => {
    const somente = pendente;
    fecharModal();
    if (somente) dispararIsolar(somente, true, "ISOLAR");
  });

  // --------------------------------------------------------------- theme
  const btnTema = $("#btn-tema");
  const temaSalvo = localStorage.getItem("acervo-dedup-tema");
  if (temaSalvo) document.documentElement.dataset.tema = temaSalvo;
  btnTema.addEventListener("click", () => {
    const novo = document.documentElement.dataset.tema === "claro" ? "escuro" : "claro";
    document.documentElement.dataset.tema = novo;
    try {
      localStorage.setItem("acervo-dedup-tema", novo);
    } catch (_) {
      /* private mode: the theme simply does not persist */
    }
  });

  // -------------------------------------------------------------- events
  function ligarFluxo() {
    const fonte = new EventSource(`/api/eventos?t=${encodeURIComponent(TOKEN)}`);
    fonte.onmessage = (evento) => {
      const dados = JSON.parse(evento.data);
      if (dados.tipo === "linha") {
        escreverLinhas([dados.texto]);
      } else if (dados.tipo === "job") {
        const anterior = estado.job && estado.job.estado;
        pintarJob({ ...dados.job, linhas: (estado.job && estado.job.linhas) || [] });
        if (dados.job.estado !== "rodando" && anterior === "rodando") {
          atualizarEstado();
          if (dados.job.estado === "concluido") {
            torrada(`${dados.job.rotulo}: concluído.`, "ok");
            if (dados.job.tipo === "scan") irPara("resultado");
          } else if (dados.job.estado === "falhou") {
            torrada(`${dados.job.rotulo}: falhou (código ${dados.job.codigo}).`, "erro");
          }
        }
      }
    };
    fonte.onerror = () => {
      /* EventSource reconnects on its own; state is reconciled then */
    };
  }

  async function atualizarEstado({ comLinhas = false } = {}) {
    try {
      const dados = await api("/api/estado");
      pintarConfig(dados.config);
      pintarRelatorio(dados.relatorio);
      pintarJob(dados.job, { comLinhas });
    } catch (e) {
      torrada(e.message, "erro");
    }
  }

  atualizarEstado({ comLinhas: true });
  ligarFluxo();
})();
