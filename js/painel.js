// CS2 · Painel do dia: lê data/hoje.json (gerado pela Action: motor/atualizar.py) e desenha os jogos.
const POUCOS = 20; // mapas na base: abaixo disso a força ainda é quase a de um time novo
const CHAVE = "cs2painel.filtros";
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = (p) => (p == null ? "—" : (100 * p).toFixed(p > 0.995 || p < 0.005 ? 1 : 0) + "%");
const odd = (p) => (p == null || p <= 0 ? "" : (1 / p).toFixed(2));
const dif = (n, p) => (n == null || p == null ? "" : `<small class="${Math.abs(n - p) >= 0.1 ? "alerta" : ""}" title="nosso − Polymarket, em pontos percentuais">${n >= p ? "+" : "−"}${Math.round(100 * Math.abs(n - p))}</small>`);
const fuso = { timeZone: "America/Sao_Paulo" };
const hora = (t) => new Date(t * 1000).toLocaleTimeString("pt-BR", { ...fuso, hour: "2-digit", minute: "2-digit" });
const diaDe = (t) => new Date(t * 1000).toLocaleDateString("pt-BR", { ...fuso, weekday: "long", day: "2-digit", month: "2-digit" });
const usd = (v) => (v == null ? "" : v >= 1e6 ? `$${(v / 1e6).toFixed(1)} mi` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)} mil` : `$${v.toFixed(0)}`);

let dados = null;
const f = lerFiltros();

function lerFiltros() {
  try { return { st: "a começar", pm: false, sem: false, dados: false, busca: "", ...JSON.parse(localStorage.getItem(CHAVE) || "{}") }; }
  catch { return { st: "a começar", pm: false, sem: false, dados: false, busca: "" }; }
}
function guardar() { try { localStorage.setItem(CHAVE, JSON.stringify(f)); } catch {} }

function inv(p) { return p == null ? null : 1 - p; }

function nomeTime(j, k) {
  const nome = k === 0 ? j.a : j.b;
  const liq = k === 0 ? j.a_liq : j.b_liq;
  const n = k === 0 ? j.n_a : j.n_b;
  const nv = (j.nivel || [])[k];
  let extra = "";
  if (!liq) extra = ` <small class="alerta">sem histórico</small>`;
  else {
    if (liq !== nome) extra += ` <small${nv >= 1 ? ' class="aprox" title="nome achado por aproximação: confira"' : ""}>${nv >= 1 ? "≈ " : ""}${esc(liq)}</small>`;
    extra += ` <small${n < POUCOS ? ' class="alerta"' : ""}>${n} mapas</small>`;
  }
  const venceu = j.venceu === k ? ' class="ganhou"' : "";
  const placar = j.placar ? ` <b class="num">${esc(j.placar[k])}</b>` : "";
  return `<div class="t" title="${esc(nome)}${liq && liq !== nome ? " = " + esc(liq) : ""}"><span${venceu}>${esc(nome)}</span>${placar}${extra}</div>`;
}

function linhaPreco(mercado, nosso, justa, fonte, k) {
  // k = 0 (time A) ou 1 (time B); mercado = {meio, bid, ask, vol, aberto}
  const meio = mercado ? (k === 0 ? mercado.meio : inv(mercado.meio)) : null;
  const compra = mercado && mercado.aberto ? (k === 0 ? mercado.ask : inv(mercado.bid)) : null;
  const n = k === 0 ? nosso : inv(nosso);
  const q = k === 0 ? justa : inv(justa);
  const fonteTxt = fonte === "nosso" ? `<small class="fonte">nosso</small>` : "";
  return `<div class="c">${mercado ? pct(meio) : "—"}</div>
    <div class="c">${compra != null && compra > 0 && compra < 1 ? (100 * compra).toFixed(1) + "¢" : "—"}</div>
    <div class="c">${pct(n)}${mercado && meio != null ? dif(n, meio) : ""}</div>
    <div class="c"><b>${q == null ? "—" : odd(q)}</b><small>${q == null ? "" : pct(q)}</small>${fonteTxt}</div>`;
}

const CAB = `<div class="cab">Time</div><div class="cab">Polymarket</div><div class="cab">Comprar</div><div class="cab">Nosso</div><div class="cab">Odd justa</div>`;

function cartao(j) {
  const st = j.status === "ao vivo" ? `<span class="st ao-vivo">ao vivo</span>` : j.status === "encerrado" ? `<span class="st encerrado">encerrado</span>` : "";
  const pm = j.pm;
  const vol = pm ? `Polymarket ${usd(pm.vol)}${pm.aberto ? "" : " · fechado"}${pm.meio == null ? " · livro vazio" : ""}` : "sem Polymarket";
  const link = j.slug ? ` · <a href="https://polymarket.com/event/${esc(j.slug)}" target="_blank" rel="noopener">abrir</a>` : "";
  let mapas = "";
  if (j.mapas && j.mapas.length) {
    const linhas = j.mapas.map((m) => `
      <div class="t">Mapa ${m.mapa} <small>${usd(m.vol)}</small></div>${linhaPreco(m, m.nosso, m.justa, m.meio != null ? "pm" : "nosso", 0).replace(/^\s*/, "")}`).join("");
    mapas = `<details class="mapas"><summary>Vencedor de cada mapa (chance do ${esc(j.a)}; nosso = mapa médio, sem saber qual)</summary><div class="grade">${CAB}${linhas}</div></details>`;
  }
  return `<article class="jogo${j.fonte === "nosso" ? " so-nosso" : ""}">
    <div class="topo"><span class="hora">${hora(j.inicio)}</span>${st}<span>BO${j.bo}</span><span>${esc(j.torneio)}${j.fase ? " · " + esc(j.fase) : ""}</span><span>${vol}${link}</span></div>
    <div class="grade">${CAB}
      ${nomeTime(j, 0)}${linhaPreco(pm, j.nosso, j.justa, j.fonte, 0)}
      ${nomeTime(j, 1)}${linhaPreco(pm, j.nosso, j.justa, j.fonte, 1)}
    </div>${mapas}
  </article>`;
}

function passa(j) {
  if (f.st !== "todos" && j.status !== f.st) return false;
  if (f.pm && !j.pm) return false;
  if (f.sem && j.fonte !== "nosso") return false;
  if (f.dados && (Math.min(j.n_a || 0, j.n_b || 0) < POUCOS)) return false;
  if (f.busca) {
    const b = f.busca.toLowerCase();
    if (![j.a, j.b, j.a_liq, j.b_liq, j.torneio].some((x) => (x || "").toLowerCase().includes(b))) return false;
  }
  return true;
}

function desenhar() {
  if (!dados) return;
  const cont = { "a começar": 0, "ao vivo": 0, encerrado: 0, todos: dados.jogos.length };
  for (const j of dados.jogos) cont[j.status] = (cont[j.status] || 0) + 1;
  for (const b of document.querySelectorAll(".abas button")) {
    b.classList.toggle("ativo", b.dataset.st === f.st);
    b.querySelector("span").textContent = cont[b.dataset.st] ?? 0;
  }
  const js = dados.jogos.filter(passa);
  if (f.st === "encerrado") js.reverse();
  if (!js.length) { $("#lista").innerHTML = `<div class="vazio">Nenhum jogo com esses filtros.</div>`; return; }
  const grupos = new Map();
  for (const j of js) {
    const d = diaDe(j.inicio);
    if (!grupos.has(d)) grupos.set(d, []);
    grupos.get(d).push(j);
  }
  $("#lista").innerHTML = [...grupos].map(([d, l]) => `<div class="dia"><h2>${esc(d)}</h2>${l.map(cartao).join("")}</div>`).join("");
}

async function carregar() {
  try {
    const r = await fetch(`data/hoje.json?t=${Date.now()}`, { cache: "no-store" });
    dados = await r.json();
  } catch (e) {
    $("#gerado").textContent = "não foi possível ler os dados";
    return;
  }
  const g = new Date(dados.gerado * 1000);
  const min = Math.round((Date.now() - g) / 60000);
  $("#gerado").textContent = `atualizado ${g.toLocaleString("pt-BR", { ...fuso, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} (há ${min} min)`;
  $("#forca-ate").textContent = `força dos times até ${dados.forca_ate.split("-").reverse().join("/")}`;
  $("#forca-ate").title = "Resultados da Liquipedia (torneios S/A/B/C-Tier) aplicados até essa data";
  const er = $("#erros");
  er.hidden = !dados.erros?.length;
  er.textContent = (dados.erros || []).join(" · ");
  desenhar();
}

for (const b of document.querySelectorAll(".abas button")) b.onclick = () => { f.st = b.dataset.st; guardar(); desenhar(); };
for (const [id, k] of [["#f-pm", "pm"], ["#f-sem", "sem"], ["#f-dados", "dados"]]) {
  const el = $(id);
  el.checked = !!f[k];
  el.onchange = () => { f[k] = el.checked; guardar(); desenhar(); };
}
$("#f-busca").value = f.busca;
$("#f-busca").oninput = (e) => { f.busca = e.target.value.trim(); guardar(); desenhar(); };
carregar();
setInterval(() => { if (!document.hidden) carregar(); }, 5 * 60 * 1000);
