/* Motor de rotas no browser: tradução direta de graph.py e server.py para JavaScript.
   Serve para a versão online (GitHub Pages), onde não há servidor Python.
   - Com o server.py a correr, este ficheiro não faz nada: o site usa a API em Python.
   - Sem servidor, carrega data/osm.json (ou data/cacilhas.json) e responde aos mesmos pedidos /api/...
   - Os obstáculos reportados ficam guardados só neste browser (localStorage).
   Se mudarem graph.py, mudem também aqui (o teste testes/paridade.py compara os dois). */
(function () {
"use strict";

const PERFIS = {
  a_pe:             {nome: "A pé", v: 1.25, escadas: "permitido", t_escadas: 2.0, alpha: 0.0, beta: 0.0, t_estreito: 1.00, t_degradado: 1.00},
  cadeira_manual:   {nome: "Cadeira de rodas manual", v: 0.90, escadas: "proibido", alpha: 0.5, beta: 0.5, t_estreito: 1.15, t_degradado: 1.30},
  cadeira_eletrica: {nome: "Cadeira de rodas elétrica", v: 1.10, escadas: "proibido", alpha: 0.5, beta: 0.3, t_estreito: 1.10, t_degradado: 1.15},
  muletas:          {nome: "Muletas ou andarilho", v: 0.70, escadas: "evitar", t_escadas: 4.0, p_escadas: 6.0, alpha: 0.2, beta: 0.5, t_estreito: 1.05, t_degradado: 1.25},
  carrinho:         {nome: "Carrinho de bebé", v: 1.05, escadas: "proibido", alpha: 0.3, beta: 0.3, t_estreito: 1.10, t_degradado: 1.15},
  mobilidade_reduzida: {nome: "Mobilidade reduzida (ex.: idosos)", v: 0.90, escadas: "evitar", t_escadas: 3.0, p_escadas: 4.0, alpha: 0.2, beta: 0.5, t_estreito: 1.05, t_degradado: 1.20},
};
const ESPERA_ELEVADOR = 60, ATRASO_CRUZAMENTO = {a_pe: 3}, DECLIVE_MAX = 0.08;
const RODAS = ["cadeira_manual", "cadeira_eletrica", "carrinho"];
const PENALIZACAO_OBSTACULO = 5.0, RAIO_ENCAIXE = 80;
const PRIORIDADE_TIPO = {ferry: 0, metro: 1, comboio: 1, autocarro: 2};
const TIPOS_OBSTACULO = ["Carro em cima do passeio", "Obras", "Passeio partido ou buraco", "Falta de rampa",
  "Escadas sem alternativa", "Passeio muito estreito", "Outro"];
const MAX_REPORTES = 500, MAX_TEXTO = 300;
const CHAVE = "cacilhas_sem_degraus_reportes";
const rad = x => x * Math.PI / 180;
const prio = t => (t in PRIORIDADE_TIPO ? PRIORIDADE_TIPO[t] : 9);
// round() do Python: arredonda .5 para o par (2.5 -> 2), ao contrário de Math.round
const pyRound = x => { const r = Math.round(x); return Math.abs(x % 1) === 0.5 ? 2 * Math.round(x / 2) : r; };
const round1 = x => Number(x.toFixed(1));  // round(x, 1) do Python

function haversine(a, b) {
  const R = 6371000, p1 = rad(a.lat), p2 = rad(b.lat), dl = rad(b.lon - a.lon), dp = p2 - p1;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
const xy = (lat, lon, lat0) => [lon * 111320 * Math.cos(rad(lat0)), lat * 110540];
function comprimento(g) { let s = 0; for (let i = 0; i + 1 < g.length; i++) s += haversine({lat: g[i][0], lon: g[i][1]}, {lat: g[i + 1][0], lon: g[i + 1][1]}); return s; }
const baseId = e => ("base" in e ? e.base : e.id);

// fila de prioridade (heap) com o mesmo desempate do heapq do Python: (custo, id do nó)
class Fila {
  constructor() { this.h = []; }
  menor(a, b) { return a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]); }
  push(x) { const h = this.h; h.push(x); let i = h.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (!this.menor(h[i], h[p])) break; [h[i], h[p]] = [h[p], h[i]]; i = p; } }
  pop() { const h = this.h, top = h[0], last = h.pop();
    if (h.length) { h[0] = last; let i = 0;
      for (;;) { const l = 2 * i + 1, r = l + 1; let m = i;
        if (l < h.length && this.menor(h[l], h[m])) m = l; if (r < h.length && this.menor(h[r], h[m])) m = r;
        if (m === i) break; [h[i], h[m]] = [h[m], h[i]]; i = m; } }
    return top; }
  get length() { return this.h.length; }
}

class Grafo {
  constructor(dados) {
    this.meta = dados.meta || {};
    this.nos = new Map(dados.nos.map(n => [n.id, n]));
    this.troços = []; this.adj = new Map([...this.nos.keys()].map(i => [i, []]));
    dados["troços"].forEach((e0, k) => {
      const e = {...e0, id: k};
      if (!e.geom || !e.geom.length) { const a = this.nos.get(e.a), b = this.nos.get(e.b); e.geom = [[a.lat, a.lon], [b.lat, b.lon]]; }
      if (!("d" in e)) e.d = pyRound(comprimento(e.geom));
      for (const c of ["degraus", "rampa", "elevador", "estreito", "degradado"]) if (!(c in e)) e[c] = false;
      e.alt_a = this.nos.get(e.a).alt ?? null; e.alt_b = this.nos.get(e.b).alt ?? null;
      this.troços.push(e); this.adj.get(e.a).push([e.b, e]); this.adj.get(e.b).push([e.a, e]);
    });
    this.obstaculos = new Map();
    this.principal = this.componentePrincipal();
    this.pois = this.calcPois(dados);
    this.locais = (dados.locais || []).filter(l => typeof l.lat === "number");
  }
  componentePrincipal() {
    const visto = new Set(); let melhor = new Set();
    for (const s of this.nos.keys()) {
      if (visto.has(s)) continue;
      const comp = new Set([s]), pilha = [s]; visto.add(s);
      while (pilha.length) { const n = pilha.pop(); for (const [v] of this.adj.get(n)) if (!visto.has(v)) { visto.add(v); comp.add(v); pilha.push(v); } }
      if (comp.size > melhor.size) melhor = comp;
    }
    return melhor;
  }
  encaixar(lat, lon) {
    const [px, py] = xy(lat, lon, lat); let best = null;
    for (const e of this.troços) {
      if (!this.principal.has(e.a)) continue;
      const g = e.geom;
      for (let i = 0; i < g.length - 1; i++) {
        const [ax, ay] = xy(g[i][0], g[i][1], lat), [bx, by] = xy(g[i + 1][0], g[i + 1][1], lat);
        const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
        const t = L2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L2));
        const d = Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
        if (best === null || d < best[0]) best = [d, e, i, t];
      }
    }
    if (best === null) return null;
    const [d, e, i, t] = best, g = e.geom;
    const p = [g[i][0] + (g[i + 1][0] - g[i][0]) * t, g[i][1] + (g[i + 1][1] - g[i][1]) * t];
    return {lat: p[0], lon: p[1], distancia_clique: pyRound(d), "troço": e.id, rua: "nome" in e ? e.nome : "",
            geom_a: [...g.slice(0, i + 1), p], geom_b: [p, ...g.slice(i + 1)]};
  }
  ponto(ref) {
    if (typeof ref === "string" && ref.includes(",")) {
      const [lat, lon] = ref.split(",").map(Number);
      if (!isFinite(lat) || !isFinite(lon)) throw new Error("coordenadas inválidas");
      const s = this.encaixar(lat, lon);
      if (s === null || s.distancia_clique > RAIO_ENCAIXE) throw new Error("longe de qualquer rua");
      return s;
    }
    if (!this.nos.has(ref)) throw new Error("nó desconhecido");
    const n = this.nos.get(ref); return {no: ref, lat: n.lat, lon: n.lon, distancia_clique: 0};
  }
  calcPois(dados, raio = 250) {
    let brutos = dados.pois;
    if (brutos == null) brutos = dados.nos.filter(n => n.poi).map(n => ({id: n.id, nome: n.nome, lat: n.poi_lat ?? n.lat, lon: n.poi_lon ?? n.lon, tipo: n.tipo || "outro"}));
    const grupos = [];
    for (const p of [...brutos].sort((a, b) => prio(a.tipo) - prio(b.tipo))) {
      const chave = (p.tipo || "outro") + ":" + p.nome.toLowerCase().replace(/[^\p{L}\p{N}_]+/gu, " ").trim();
      const g = grupos.find(g => g.chave === chave && haversine(g.ref, p) < raio);
      if (g) g.membros.push(p); else grupos.push({chave, ref: p, membros: [p]});
    }
    const saida = [];
    for (const g of grupos) {
      const m = g.membros, lat = m.reduce((s, p) => s + p.lat, 0) / m.length, lon = m.reduce((s, p) => s + p.lon, 0) / m.length;
      const s = this.encaixar(lat, lon);
      if (s === null || s.distancia_clique > RAIO_ENCAIXE) continue;
      saida.push({id: `${s.lat.toFixed(6)},${s.lon.toFixed(6)}`, nome: g.ref.nome, lat: s.lat, lon: s.lon, tipo: g.ref.tipo || "outro", agrupados: m.length});
    }
    const nomes = saida.map(p => p.nome), rotulo = {ferry: "barco", metro: "metro", comboio: "comboio", autocarro: "autocarro"};
    for (const p of saida) if (nomes.filter(n => n === p.nome).length > 1) p.nome += ` (${rotulo[p.tipo] || p.tipo})`;
    const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
    return saida.sort((a, b) => prio(a.tipo) - prio(b.tipo) || cmp(a.nome.toLowerCase(), b.nome.toLowerCase()));
  }
  escadas(e) { return e.degraus && !(e.rampa || e.elevador); }
  declive(e, de) {
    if (e.alt_a == null || e.alt_b == null || !e.d) return 0;
    const s = (e.alt_b - e.alt_a) / e.d; return de === e.b ? -s : s;
  }
  custo(e, perfil, alpha, beta, de) {
    const P = PERFIS[perfil];
    alpha = alpha == null ? P.alpha : alpha; beta = beta == null ? P.beta : beta;
    let c = e.d * (1 + alpha * e.estreito + beta * e.degradado);
    if (this.escadas(e)) { if (P.escadas === "proibido") return Infinity; if (P.escadas === "evitar") c *= P.p_escadas; }
    if (perfil !== "a_pe" && (this.obstaculos.get(baseId(e)) || []).length) c *= PENALIZACAO_OBSTACULO;
    const s = this.declive(e, de);
    if (RODAS.includes(perfil) && Math.abs(s) > DECLIVE_MAX) c *= 4;
    else if (perfil !== "a_pe") c *= 1 + 3 * Math.max(0, s);
    return c;
  }
  segundos(e, perfil, de) {
    const P = PERFIS[perfil]; let t = e.d / P.v; const s = this.declive(e, de);
    if (s) {
      if (RODAS.includes(perfil)) t *= 1 + 8 * Math.max(0, s) + 2 * Math.max(0, -s);
      else { const f = Math.exp(3.5 * (Math.abs(s + 0.05) - 0.05)); t *= perfil === "a_pe" ? f : Math.max(1, f); }
    }
    if (this.escadas(e)) t *= P.t_escadas ?? 1;
    if (e.elevador) t += ESPERA_ELEVADOR;
    if (e.estreito) t *= P.t_estreito;
    if (e.degradado) t *= P.t_degradado;
    return t;
  }
  definirReportes(lista) {
    this.obstaculos = new Map();
    for (const r of lista) { if (!this.obstaculos.has(r["troço"])) this.obstaculos.set(r["troço"], []); this.obstaculos.get(r["troço"]).push(r); }
  }
  ligacoesTemp(p, tag) {
    if ("no" in p) return [p.no, []];
    const e = this.troços[p["troço"]], nid = "@" + tag, meia = [];
    const la = comprimento(p.geom_a), lb = comprimento(p.geom_b);
    let alt_p = null;
    if (e.alt_a != null && e.alt_b != null && la + lb) alt_p = e.alt_a + (e.alt_b - e.alt_a) * la / (la + lb);
    for (const [ponta, geom] of [[e.a, p.geom_a], [e.b, p.geom_b]]) {
      meia.push({...e, id: `${e.id}${tag}${ponta}`, a: nid, b: ponta, geom: ponta === e.b ? geom : [...geom].reverse(),
                 d: pyRound(comprimento(geom)), base: e.id, alt_a: alt_p, alt_b: ponta === e.a ? e.alt_a : e.alt_b});
    }
    return [nid, meia];
  }
  pesquisa(origem, destino, perfil, alpha, beta, algoritmo = "dijkstra") {
    const po = this.ponto(origem), pd = this.ponto(destino);
    const [o, extraO] = this.ligacoesTemp(po, "o"), [d, extraD] = this.ligacoesTemp(pd, "d");
    const extra = [...extraO, ...extraD];
    const viz = n => {
      const base = [...(this.adj.get(n) || [])];
      for (const e of extra) { if (e.a === n) base.push([e.b, e]); if (e.b === n) base.push([e.a, e]); }
      if (extraO.length && extraD.length && po["troço"] === pd["troço"] && (n === o || n === d)) {
        const outro = n === o ? d : o;
        const seg = {...this.troços[po["troço"]], id: "direto", a: o, b: d, alt_a: null, alt_b: null,
                     geom: [[po.lat, po.lon], [pd.lat, pd.lon]], d: pyRound(haversine(po, pd))};
        base.push([outro, seg]);
      }
      return base;
    };
    const coords = new Map([[o, po], [d, pd]]), pos = n => coords.get(n) || this.nos.get(n);
    const h = algoritmo === "astar" ? n => haversine(pos(n), pd) : () => 0;
    const g = new Map([[o, 0]]), pai = new Map(), fila = new Fila(), feitos = new Set(), explorados = [];
    fila.push([h(o), o]);
    while (fila.length) {
      const [, n] = fila.pop();
      if (feitos.has(n)) continue;
      feitos.add(n); explorados.push(n);
      if (n === d) break;
      for (const [v, e] of viz(n)) {
        const c = this.custo(e, perfil, alpha, beta, n);
        if (c === Infinity) continue;
        const gv = g.has(v) ? g.get(v) : Infinity;
        if (g.get(n) + c < gv) { g.set(v, g.get(n) + c); pai.set(v, [n, e]); fila.push([g.get(v) + h(v), v]); }
      }
    }
    const pontos = {origem: {lat: po.lat, lon: po.lon}, destino: {lat: pd.lat, lon: pd.lon}};
    const exp = explorados.map(n => [pos(n).lat, pos(n).lon]);
    if (!feitos.has(d)) return {existe: false, explorados: exp, ...pontos};
    const caminho = [d], tr = []; let n = d;
    while (n !== o) { const [m, e] = pai.get(n); n = m; caminho.push(n); tr.push([n, e]); }
    caminho.reverse(); tr.reverse();
    const dist = tr.reduce((s, [, e]) => s + e.d, 0);
    const cruz = caminho.slice(1, -1).filter(n => (this.adj.get(n) || []).length >= 3).length;
    const seg = tr.reduce((s, [n, e]) => s + this.segundos(e, perfil, n), 0) + cruz * (ATRASO_CRUZAMENTO[perfil] ?? 6);
    const geomOrientada = (n, e) => (e.a === n ? e.geom : [...e.geom].reverse());
    return {
      existe: true, explorados: exp, ...pontos,
      custo: round1(g.get(d)), distancia: dist, segundos: pyRound(seg), cruzamentos: cruz,
      subida: pyRound(tr.reduce((s, [n, e]) => s + Math.max(0, this.declive(e, n)) * e.d, 0)),
      minutos: Math.max(1, pyRound(seg / 60)),
      escadas: tr.filter(([, e]) => this.escadas(e)).length,
      obstaculos: tr.filter(([, e]) => (this.obstaculos.get(baseId(e)) || []).length).length,
      "troços": tr.map(([n, e]) => ({id: baseId(e), d: e.d, geom: geomOrientada(n, e), texto: explicar(e, perfil, this.obstaculos.get(baseId(e)))})),
      _tr: tr,
    };
  }
  comparar(origem, destino, perfil = "cadeira_manual", alpha, beta, algoritmo = "dijkstra") {
    if (!(perfil in PERFIS) || perfil === "a_pe") throw new Error("perfil desconhecido");
    const r = {normal: this.pesquisa(origem, destino, "a_pe", null, null, algoritmo),
               acessivel: this.pesquisa(origem, destino, perfil, alpha, beta, algoritmo)};
    const n = r.normal, s = r.acessivel;
    if (n.existe && s.existe) {
      const base = n._tr.reduce((t, [a, e]) => t + this.segundos({...e, degraus: false}, perfil, a), 0) + n.cruzamentos * (ATRASO_CRUZAMENTO[perfil] ?? 6);
      r.desvio = {metros: s.distancia - n.distancia, minutos: round1((s.segundos - base) / 60)};
    }
    delete n._tr; delete s._tr;
    r.perfil = perfil;
    return r;
  }
}

function explicar(e, perfil, obst) {
  const t = [];
  if (e.degraus && (e.rampa || e.elevador)) t.push("tem degraus, mas também " + (e.elevador ? "elevador" : "rampa"));
  else if (e.degraus) t.push("tem escadas" + ({proibido: " (este perfil não as usa)", evitar: " (usadas só se não houver alternativa)"}[PERFIS[perfil].escadas] || ""));
  if (e.estreito) t.push("passeio estreito" + (e.largura ? ` (${e.largura} cm)` : ""));
  if (e.degradado) t.push("passeio degradado");
  if (e.alt_a != null && e.alt_b != null && e.d >= 10) {
    const pct = Math.abs(e.alt_b - e.alt_a) / e.d * 100;
    if (pct >= 5) t.push(`inclinação de ${pyRound(pct)}%` + (pct > DECLIVE_MAX * 100 ? " (íngreme)" : ""));
  }
  for (const o of obst || []) t.push(`obstáculo reportado: ${o.tipo}`);
  if (!t.length) t.push("sem obstáculos registados");
  return `${"nome" in e ? e.nome : "Troço"}: ` + t.join(", ") + ` · ${e.d} m`;
}

// ---------- API local (as mesmas respostas que o server.py) ----------
function lerReportes() { try { const v = JSON.parse(localStorage.getItem(CHAVE) || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } }
function gravarReportes(G, lista) { try { localStorage.setItem(CHAVE, JSON.stringify(lista)); } catch { /* modo privado: fica só em memória */ } G.definirReportes(lista); }
const quando = () => { const d = new Date(), z = x => String(x).padStart(2, "0"); return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`; };

function responder(G, url, opts) {
  const u = new URL(url, location.href), q = Object.fromEntries(u.searchParams), caminho = u.pathname.replace(/^.*\/api\//, "/api/");
  const metodo = (opts && opts.method || "GET").toUpperCase();
  if (metodo === "GET") {
    if (caminho === "/api/grafo") {
      const campos = ["id", "nome", "d", "geom", "degraus", "rampa", "elevador", "estreito", "degradado", "largura"];
      const perfis = {}; for (const k in PERFIS) perfis[k] = {nome: PERFIS[k].nome, v: PERFIS[k].v, escadas: PERFIS[k].escadas};
      return [200, {meta: G.meta, pois: G.pois, locais: G.locais, tipos_obstaculo: TIPOS_OBSTACULO, perfis,
        "troços": G.troços.map(e => Object.fromEntries(campos.filter(k => k in e).map(k => [k, e[k]])))}];
    }
    if (caminho === "/api/reportes") return [200, lerReportes()];
    if (caminho === "/api/rota") {
      if (!q.origem || !q.destino) return [400, {erro: "faltam a origem ou o destino"}];
      try {
        const al = q.alpha ? Number(q.alpha) : null, be = q.beta ? Number(q.beta) : null;
        const alg = q.algoritmo || "dijkstra", perfil = q.perfil || "cadeira_manual";
        if (!["dijkstra", "astar"].includes(alg) || [al, be].some(x => x !== null && !(x >= 0 && x <= 5))) throw new Error("parâmetros fora dos limites");
        return [200, G.comparar(q.origem, q.destino, perfil, al, be, alg)];
      } catch (err) { return [400, {erro: "pedido inválido: " + err.message}]; }
    }
    if (caminho === "/api/encaixar") {
      const lat = Number(q.lat), lon = Number(q.lon);
      if (!q.lat || !q.lon || !isFinite(lat) || !isFinite(lon)) return [400, {erro: "pedido inválido"}];
      const s = G.encaixar(lat, lon);
      if (!s) return [400, {erro: "pedido inválido"}];
      const {geom_a, geom_b, ...resto} = s; return [200, resto];
    }
    return [404, {erro: "não encontrado"}];
  }
  let corpo;
  try { corpo = JSON.parse(opts.body); } catch { return [400, {erro: "JSON inválido"}]; }
  if (caminho === "/api/reportes") {
    const lat = Number(corpo.lat), lon = Number(corpo.lon), tipo = String(corpo.tipo ?? "");
    if (corpo.lat == null || corpo.lon == null || !isFinite(lat) || !isFinite(lon) || corpo.tipo == null) return [400, {erro: "faltam campos"}];
    const texto = String(corpo.descricao ?? "").trim().slice(0, MAX_TEXTO);
    if (!TIPOS_OBSTACULO.includes(tipo)) return [400, {erro: "tipo de obstáculo desconhecido"}];
    const s = G.encaixar(lat, lon);
    if (!s || s.distancia_clique > RAIO_ENCAIXE) return [400, {erro: "o ponto fica longe de qualquer rua"}];
    const lista = lerReportes();
    if (lista.length >= MAX_REPORTES) return [429, {erro: "limite de reportes atingido"}];
    const id = Array.from(crypto.getRandomValues(new Uint8Array(5)), b => b.toString(16).padStart(2, "0")).join("");
    const r = {id, lat: s.lat, lon: s.lon, "troço": s["troço"], rua: s.rua, tipo, descricao: texto, quando: quando()};
    lista.push(r); gravarReportes(G, lista); return [201, r];
  }
  if (caminho === "/api/reportes/resolver") {
    const lista = lerReportes(), nova = lista.filter(r => r.id !== String(corpo.id));
    if (nova.length === lista.length) return [404, {erro: "reporte não encontrado"}];
    gravarReportes(G, nova); return [200, {ok: true}];
  }
  return [404, {erro: "não encontrado"}];
}

// ---------- arranque: usa o servidor Python se existir; senão, o motor local ----------
async function preparar() {
  const fetchReal = window.fetch.bind(window);
  try {
    const r = await fetchReal("api/grafo", {cache: "no-store"});
    if (r.ok && (r.headers.get("Content-Type") || "").includes("json")) return { estatico: false };
  } catch { /* sem servidor */ }
  let dados = null;
  for (const f of ["data/osm.json", "data/cacilhas.json"]) {
    try { const r = await fetchReal(f); if (r.ok) { dados = await r.json(); break; } } catch { /* tenta o próximo */ }
  }
  if (!dados) throw new Error("Não encontrei os dados do mapa (data/osm.json).");
  const G = new Grafo(dados); G.definirReportes(lerReportes());
  window.fetch = async (url, opts) => {
    const s = typeof url === "string" ? url : url.url;
    if (/(^|\/)api\//.test(new URL(s, location.href).pathname)) {
      const [status, obj] = responder(G, s, opts);
      return new Response(JSON.stringify(obj), {status, headers: {"Content-Type": "application/json; charset=utf-8"}});
    }
    return fetchReal(url, opts);
  };
  return { estatico: true };
}

if (typeof window !== "undefined") window.CacilhasMotor = {preparar, Grafo, PERFIS, responder};
if (typeof module !== "undefined") module.exports = {Grafo, PERFIS, responder};
})();
