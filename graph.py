"""Grafo de Cacilhas + Dijkstra e A* com custos por perfil.

Novidades desta versão:
- encaixe ("snap") de um clique no ponto mais próximo de uma RUA, e não no cruzamento mais próximo;
- o ponto encaixado divide o troço em dois (nó temporário), por isso a rota começa e acaba onde clicaste;
- tempo calculado troço a troço (escadas mais lentas, espera no elevador), em vez de distância / velocidade;
- só se encaixa na rede principal: um clique já não cai num pedaço de rua isolado sem rota possível.
"""
import heapq, json, math, re

# Perfis de mobilidade. Velocidades MÉDIAS em cidade (m/s), já a contar com pequenas paragens, e fatores:
# são ESTIMATIVAS a calibrar com cronómetro na recolha a pé. Referência: o Google Maps dá ~9 min para 600 m
# de Cacilhas à Av. 25 de Abril pela Rua Cândido dos Reis (a subir), cerca de 1,1 m/s.
# escadas: "permitido" (só mais lento), "evitar" (usa se não houver alternativa) ou "proibido" (nunca usa).
PERFIS = {
    "a_pe":             {"nome": "A pé",                 "v": 1.25, "escadas": "permitido", "t_escadas": 2.0,
                         "alpha": 0.0, "beta": 0.0, "t_estreito": 1.00, "t_degradado": 1.00},
    "cadeira_manual":   {"nome": "Cadeira de rodas manual", "v": 0.90, "escadas": "proibido",
                         "alpha": 0.5, "beta": 0.5, "t_estreito": 1.15, "t_degradado": 1.30},
    "cadeira_eletrica": {"nome": "Cadeira de rodas elétrica", "v": 1.10, "escadas": "proibido",
                         "alpha": 0.5, "beta": 0.3, "t_estreito": 1.10, "t_degradado": 1.15},
    "muletas":          {"nome": "Muletas ou andarilho",  "v": 0.70, "escadas": "evitar", "t_escadas": 4.0, "p_escadas": 6.0,
                         "alpha": 0.2, "beta": 0.5, "t_estreito": 1.05, "t_degradado": 1.25},
    "carrinho":         {"nome": "Carrinho de bebé",      "v": 1.05, "escadas": "proibido",
                         "alpha": 0.3, "beta": 0.3, "t_estreito": 1.10, "t_degradado": 1.15},
    "mobilidade_reduzida": {"nome": "Mobilidade reduzida (ex.: idosos)", "v": 0.90, "escadas": "evitar", "t_escadas": 3.0,
                         "p_escadas": 4.0, "alpha": 0.2, "beta": 0.5, "t_estreito": 1.05, "t_degradado": 1.20},
}
ESPERA_ELEVADOR = 60     # segundos de espera e viagem num elevador
ATRASO_CRUZAMENTO = {"a_pe": 3}   # segundos por cruzamento atravessado (outros perfis: 6 s, por causa dos rebaixamentos)
DECLIVE_MAX = 0.08       # 8%: acima disto, cadeiras e carrinhos evitam o troço (limite comum em normas de acessibilidade)
RODAS = ("cadeira_manual", "cadeira_eletrica", "carrinho")
PENALIZACAO_OBSTACULO = 5.0   # troço com obstáculo reportado custa 5x (evita-se se houver alternativa)
RAIO_ENCAIXE = 80        # metros: cliques mais longe de qualquer rua são recusados

PRIORIDADE_TIPO = {"ferry": 0, "metro": 1, "comboio": 1, "autocarro": 2}


def haversine(a, b):
    R = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    dp = p2 - p1
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _xy(lat, lon, lat0):
    """Projeção local em metros (chega para uma zona do tamanho de Cacilhas)."""
    return lon * 111320 * math.cos(math.radians(lat0)), lat * 110540


def _comprimento(geom):
    return sum(haversine({"lat": a[0], "lon": a[1]}, {"lat": b[0], "lon": b[1]}) for a, b in zip(geom, geom[1:]))


class Grafo:
    def __init__(self, caminho):
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        self.meta = dados.get("meta", {})
        self.nos = {n["id"]: n for n in dados["nos"]}
        self.troços = []
        self.adj = {i: [] for i in self.nos}
        for k, e in enumerate(dados["troços"]):
            e = dict(e)
            e["id"] = k
            if not e.get("geom"):
                a, b = self.nos[e["a"]], self.nos[e["b"]]
                e["geom"] = [[a["lat"], a["lon"]], [b["lat"], b["lon"]]]
            e.setdefault("d", round(_comprimento(e["geom"])))
            for c in ("degraus", "rampa", "elevador", "estreito", "degradado"):
                e.setdefault(c, False)
            e["alt_a"], e["alt_b"] = self.nos[e["a"]].get("alt"), self.nos[e["b"]].get("alt")
            self.troços.append(e)
            self.adj[e["a"]].append((e["b"], e))
            self.adj[e["b"]].append((e["a"], e))
        self.obstaculos = {}
        self.principal = self._componente_principal()
        self.pois = self._pois(dados)
        self.locais = [l for l in dados.get("locais", []) if isinstance(l.get("lat"), (int, float))]

    # ---------- rede principal ----------
    def _componente_principal(self):
        visto, melhor = set(), set()
        for s in self.nos:
            if s in visto:
                continue
            comp, pilha = {s}, [s]
            visto.add(s)
            while pilha:
                n = pilha.pop()
                for v, _ in self.adj[n]:
                    if v not in visto:
                        visto.add(v); comp.add(v); pilha.append(v)
            if len(comp) > len(melhor):
                melhor = comp
        return melhor

    # ---------- encaixe na rua ----------
    def encaixar(self, lat, lon):
        """Ponto mais próximo sobre a geometria de um troço da rede principal."""
        px, py = _xy(lat, lon, lat)
        best = None
        for e in self.troços:
            if e["a"] not in self.principal:
                continue
            g = e["geom"]
            for i in range(len(g) - 1):
                ax, ay = _xy(g[i][0], g[i][1], lat)
                bx, by = _xy(g[i + 1][0], g[i + 1][1], lat)
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
                if best is None or d < best[0]:
                    best = (d, e, i, t)
        if best is None:
            return None
        d, e, i, t = best
        g = e["geom"]
        p = [g[i][0] + (g[i + 1][0] - g[i][0]) * t, g[i][1] + (g[i + 1][1] - g[i][1]) * t]
        antes = g[:i + 1] + [p]
        depois = [p] + g[i + 1:]
        return {"lat": p[0], "lon": p[1], "distancia_clique": round(d), "troço": e["id"],
                "rua": e.get("nome", ""), "geom_a": antes, "geom_b": depois}

    def _ponto(self, ref):
        """'lat,lon' -> encaixe; id de nó -> esse nó."""
        if isinstance(ref, str) and "," in ref:
            lat, lon = (float(x) for x in ref.split(","))
            s = self.encaixar(lat, lon)
            if s is None or s["distancia_clique"] > RAIO_ENCAIXE:
                raise ValueError("longe de qualquer rua")
            return s
        if ref not in self.nos:
            raise ValueError("nó desconhecido")
        n = self.nos[ref]
        return {"no": ref, "lat": n["lat"], "lon": n["lon"], "distancia_clique": 0}

    # ---------- pontos de interesse ----------
    def _pois(self, dados, raio=250):
        """Paragens/terminais com o mesmo nome juntam-se num só. A posição é a REAL (média das paragens),
        e a rota encaixa-a na rua mais próxima, em vez de saltar para um cruzamento."""
        brutos = dados.get("pois")
        if brutos is None:
            brutos = [{"id": n["id"], "nome": n["nome"], "lat": n.get("poi_lat", n["lat"]), "lon": n.get("poi_lon", n["lon"]),
                       "tipo": n.get("tipo", "outro")} for n in dados["nos"] if n.get("poi")]
        grupos = []
        for p in sorted(brutos, key=lambda p: PRIORIDADE_TIPO.get(p.get("tipo"), 9)):
            chave = p.get("tipo", "outro") + ":" + re.sub(r"\W+", " ", p["nome"].lower()).strip()
            for g in grupos:
                if g["chave"] == chave and haversine(g["ref"], p) < raio:
                    g["membros"].append(p)
                    break
            else:
                grupos.append({"chave": chave, "ref": p, "membros": [p]})
        saida = []
        for g in grupos:
            m = g["membros"]
            lat = sum(p["lat"] for p in m) / len(m)
            lon = sum(p["lon"] for p in m) / len(m)
            s = self.encaixar(lat, lon)
            if s is None or s["distancia_clique"] > RAIO_ENCAIXE:
                continue
            saida.append({"id": f"{s['lat']:.6f},{s['lon']:.6f}", "nome": g["ref"]["nome"], "lat": s["lat"], "lon": s["lon"],
                          "tipo": g["ref"].get("tipo", "outro"), "agrupados": len(m)})
        nomes = [p["nome"] for p in saida]
        rotulo = {"ferry": "barco", "metro": "metro", "comboio": "comboio", "autocarro": "autocarro"}
        for p in saida:  # o mesmo nome em transportes diferentes (ex.: Cacilhas barco e metro) fica distinguido
            if nomes.count(p["nome"]) > 1:
                p["nome"] += f" ({rotulo.get(p['tipo'], p['tipo'])})"
        return sorted(saida, key=lambda p: (PRIORIDADE_TIPO.get(p["tipo"], 9), p["nome"].lower()))

    # ---------- custos e tempos ----------
    def _escadas(self, e):
        return e["degraus"] and not (e["rampa"] or e["elevador"])

    def declive(self, e, de=None):
        """Declive do troço no sentido em que é percorrido (+ a subir). 0 se não houver altitudes."""
        if e.get("alt_a") is None or e.get("alt_b") is None or not e["d"]:
            return 0.0
        s = (e["alt_b"] - e["alt_a"]) / e["d"]
        return -s if de == e["b"] else s

    def custo(self, e, perfil, alpha=None, beta=None, de=None):
        P = PERFIS[perfil]
        alpha = P["alpha"] if alpha is None else alpha
        beta = P["beta"] if beta is None else beta
        c = e["d"] * (1 + alpha * e["estreito"] + beta * e["degradado"])
        if self._escadas(e):
            if P["escadas"] == "proibido":
                return math.inf
            if P["escadas"] == "evitar":
                c *= P["p_escadas"]
        if perfil != "a_pe" and self.obstaculos.get(e.get("base", e["id"])):
            c *= PENALIZACAO_OBSTACULO
        s = self.declive(e, de)
        if perfil in RODAS and abs(s) > DECLIVE_MAX:
            c *= 4  # rua muito íngreme: evita se houver alternativa
        elif perfil != "a_pe":
            c *= 1 + 3 * max(0.0, s)  # subidas custam mais a quem tem mobilidade reduzida
        return c

    def segundos(self, e, perfil, de=None):
        """Tempo de um troço, em segundos, para um perfil (no sentido em que é percorrido)."""
        P = PERFIS[perfil]
        t = e["d"] / P["v"]
        s = self.declive(e, de)
        if s:
            if perfil in RODAS:
                t *= 1 + 8 * max(0.0, s) + 2 * max(0.0, -s)   # a subir custa muito; a descer também abranda (travar)
            else:
                f = math.exp(3.5 * (abs(s + 0.05) - 0.05))     # função de Tobler (caminhada em declive)
                t *= f if perfil == "a_pe" else max(1.0, f)    # muletas/idosos não descem mais depressa
        if self._escadas(e):
            t *= P.get("t_escadas", 1.0)
        if e["elevador"]:
            t += ESPERA_ELEVADOR
        if e["estreito"]:
            t *= P["t_estreito"]
        if e["degradado"]:
            t *= P["t_degradado"]
        return t

    # ---------- obstáculos reportados ----------
    def definir_reportes(self, reportes):
        self.obstaculos = {}
        for r in reportes:
            self.obstaculos.setdefault(r["troço"], []).append(r)

    # ---------- pesquisa ----------
    def _ligacoes_temp(self, p, tag):
        """Liga o ponto encaixado às duas pontas do troço onde caiu (troços temporários)."""
        if "no" in p:
            return p["no"], []
        e = self.troços[p["troço"]]
        nid = "@" + tag
        meia = []
        la, lb = _comprimento(p["geom_a"]), _comprimento(p["geom_b"])
        alt_p = None
        if e.get("alt_a") is not None and e.get("alt_b") is not None and la + lb:
            alt_p = e["alt_a"] + (e["alt_b"] - e["alt_a"]) * la / (la + lb)
        for ponta, geom in ((e["a"], p["geom_a"]), (e["b"], p["geom_b"])):
            parte = dict(e, id=f"{e['id']}{tag}{ponta}", a=nid, b=ponta, geom=geom if ponta == e["b"] else list(reversed(geom)),
                         d=round(_comprimento(geom)), base=e["id"], alt_a=alt_p, alt_b=e.get("alt_a" if ponta == e["a"] else "alt_b"))
            meia.append(parte)
        return nid, meia

    def pesquisa(self, origem, destino, perfil, alpha=None, beta=None, algoritmo="dijkstra"):
        po, pd = self._ponto(origem), self._ponto(destino)
        o, extra_o = self._ligacoes_temp(po, "o")
        d, extra_d = self._ligacoes_temp(pd, "d")
        adj = {}
        def viz(n):
            base = list(self.adj.get(n, []))
            for e in extra_o + extra_d:
                if e["a"] == n: base.append((e["b"], e))
                if e["b"] == n: base.append((e["a"], e))
            # origem e destino no mesmo troço: ligação direta entre os dois pontos
            if extra_o and extra_d and po["troço"] == pd["troço"] and n in (o, d):
                outro = d if n == o else o
                seg = dict(self.troços[po["troço"]], id="direto", a=o, b=d, alt_a=None, alt_b=None,
                           geom=[[po["lat"], po["lon"]], [pd["lat"], pd["lon"]]], d=round(haversine(po, pd)))
                base.append((outro, seg))
            return base
        coords = {o: po, d: pd}
        pos = lambda n: coords.get(n) or self.nos[n]
        h = (lambda n: haversine(pos(n), pd)) if algoritmo == "astar" else (lambda n: 0)
        g, pai, fila, feitos, explorados = {o: 0.0}, {}, [(h(o), o)], set(), []
        while fila:
            _, n = heapq.heappop(fila)
            if n in feitos:
                continue
            feitos.add(n); explorados.append(n)
            if n == d:
                break
            for v, e in viz(n):
                c = self.custo(e, perfil, alpha, beta, de=n)
                if c == math.inf:
                    continue
                if g[n] + c < g.get(v, math.inf):
                    g[v] = g[n] + c; pai[v] = (n, e)
                    heapq.heappush(fila, (g[v] + h(v), v))
        pontos = {"origem": {"lat": po["lat"], "lon": po["lon"]}, "destino": {"lat": pd["lat"], "lon": pd["lon"]}}
        exp_coords = [[pos(n)["lat"], pos(n)["lon"]] for n in explorados]
        if d not in feitos:
            return {"existe": False, "explorados": exp_coords, **pontos}
        caminho, troços, n = [d], [], d
        while n != o:
            n, e = pai[n]; caminho.append(n); troços.append((n, e))
        caminho.reverse(); troços.reverse()
        dist = sum(e["d"] for _, e in troços)
        cruz = sum(1 for n in caminho[1:-1] if len(self.adj.get(n, [])) >= 3)
        seg = sum(self.segundos(e, perfil, de=n) for n, e in troços) + cruz * ATRASO_CRUZAMENTO.get(perfil, 6)
        def geom_orientada(n, e):
            gm = e["geom"]
            return gm if e["a"] == n else list(reversed(gm))
        return {
            "existe": True, "explorados": exp_coords, **pontos,
            "custo": round(g[d], 1), "distancia": dist, "segundos": round(seg), "cruzamentos": cruz,
            "subida": round(sum(max(0.0, self.declive(e, n)) * e["d"] for n, e in troços)),
            "minutos": max(1, round(seg / 60)),
            "escadas": sum(1 for _, e in troços if self._escadas(e)),
            "obstaculos": sum(1 for _, e in troços if self.obstaculos.get(e.get("base", e["id"]))),
            "troços": [{"id": e.get("base", e["id"]), "d": e["d"], "geom": geom_orientada(n, e), "texto": explicar(e, perfil, self.obstaculos.get(e.get("base", e["id"])))}
                       for n, e in troços],
            "_troços_obj": troços,
        }

    def comparar(self, origem, destino, perfil="cadeira_manual", alpha=None, beta=None, algoritmo="dijkstra"):
        if perfil not in PERFIS or perfil == "a_pe":
            raise ValueError("perfil desconhecido")
        r = {"normal": self.pesquisa(origem, destino, "a_pe", algoritmo=algoritmo),
             "acessivel": self.pesquisa(origem, destino, perfil, alpha, beta, algoritmo)}
        n, s = r["normal"], r["acessivel"]
        if n["existe"] and s["existe"]:
            # desvio medido ao MESMO ritmo (o do perfil): só conta o caminho extra, não a velocidade diferente
            base = sum(self.segundos(dict(e, degraus=False), perfil, de=a) for a, e in n["_troços_obj"]) \
                + n["cruzamentos"] * ATRASO_CRUZAMENTO.get(perfil, 6)
            r["desvio"] = {"metros": s["distancia"] - n["distancia"], "minutos": round((s["segundos"] - base) / 60, 1)}
        for v in r.values():
            if isinstance(v, dict):
                v.pop("_troços_obj", None)
        r["perfil"] = perfil
        return r


def explicar(e, perfil, obst=None):
    t = []
    if e["degraus"] and (e["rampa"] or e["elevador"]):
        t.append("tem degraus, mas também " + ("elevador" if e["elevador"] else "rampa"))
    elif e["degraus"]:
        t.append("tem escadas" + {"proibido": " (este perfil não as usa)", "evitar": " (usadas só se não houver alternativa)"}.get(PERFIS[perfil]["escadas"], ""))
    if e["estreito"]:
        t.append("passeio estreito" + (f" ({e['largura']} cm)" if e.get("largura") else ""))
    if e["degradado"]:
        t.append("passeio degradado")
    if e.get("alt_a") is not None and e.get("alt_b") is not None and e["d"] >= 10:
        pct = abs(e["alt_b"] - e["alt_a"]) / e["d"] * 100
        if pct >= 5:
            t.append(f"inclinação de {pct:.0f}%" + (" (íngreme)" if pct > DECLIVE_MAX * 100 else ""))
    for o in obst or []:
        t.append(f"obstáculo reportado: {o['tipo']}")
    if not t:
        t.append("sem obstáculos registados")
    return f"{e.get('nome', 'Troço')}: " + ", ".join(t) + f" · {e['d']} m"
