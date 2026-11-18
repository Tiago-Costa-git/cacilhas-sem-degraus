"""Servidor local (só biblioteca padrão):  python server.py  ->  http://localhost:8000"""
import json, mimetypes, os, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from graph import Grafo, PERFIS, RAIO_ENCAIXE

AQUI = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(AQUI, "data", "osm.json")
if not os.path.exists(DADOS):
    DADOS = os.path.join(AQUI, "data", "cacilhas.json")
REPORTES = os.path.join(AQUI, "data", "reportes.json")
ESTATICO = os.path.join(AQUI, "static")
G = Grafo(DADOS)

# Obstáculos reportados pelos utilizadores (guardados em data/reportes.json)
TIPOS_OBSTACULO = ["Carro em cima do passeio", "Obras", "Passeio partido ou buraco", "Falta de rampa",
                   "Escadas sem alternativa", "Passeio muito estreito", "Outro"]
MAX_REPORTES, MAX_TEXTO, MAX_PEDIDO = 500, 300, 4096
TRANCA = threading.Lock()


def ler_reportes():
    try:
        with open(REPORTES, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def gravar_reportes(lista):
    tmp = REPORTES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    os.replace(tmp, REPORTES)  # escrita atómica: um erro a meio não corrompe o ficheiro
    G.definir_reportes(lista)


G.definir_reportes(ler_reportes())


class H(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/api/grafo":
            campos = ("id", "nome", "d", "geom", "degraus", "rampa", "elevador", "estreito", "degradado", "largura")
            return self._json({"meta": G.meta, "pois": G.pois, "locais": G.locais, "tipos_obstaculo": TIPOS_OBSTACULO,
                               "perfis": {k: {"nome": p["nome"], "v": p["v"], "escadas": p["escadas"]} for k, p in PERFIS.items()},
                               "troços": [{k: e[k] for k in campos if k in e} for e in G.troços]})
        if u.path == "/api/reportes":
            return self._json(ler_reportes())
        if u.path == "/api/rota":
            try:
                a, b = q["origem"], q["destino"]
                al = float(q["alpha"]) if q.get("alpha") else None
                be = float(q["beta"]) if q.get("beta") else None
                alg, perfil = q.get("algoritmo", "dijkstra"), q.get("perfil", "cadeira_manual")
                if alg not in ("dijkstra", "astar") or any(x is not None and not 0 <= x <= 5 for x in (al, be)):
                    raise ValueError("parâmetros fora dos limites")
                return self._json(G.comparar(a, b, perfil, al, be, alg))
            except KeyError:
                return self._json({"erro": "faltam a origem ou o destino"}, 400)
            except ValueError as e:
                return self._json({"erro": f"pedido inválido: {e}"}, 400)
        if u.path == "/api/encaixar":
            try:
                s = G.encaixar(float(q["lat"]), float(q["lon"]))
                return self._json({k: v for k, v in s.items() if not k.startswith("geom")})
            except (KeyError, ValueError, TypeError):
                return self._json({"erro": "pedido inválido"}, 400)
        nome = "index.html" if u.path == "/" else u.path.lstrip("/")
        f = os.path.abspath(os.path.join(ESTATICO, nome))
        if f.startswith(ESTATICO + os.sep) and os.path.isfile(f):
            tipo = mimetypes.guess_type(f)[0] or "application/octet-stream"
            self.send_response(200); self.send_header("Content-Type", tipo + ("; charset=utf-8" if tipo.startswith("text/") else ""))
            self.end_headers()
            with open(f, "rb") as fh:
                return self.wfile.write(fh.read())
        self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= MAX_PEDIDO:
                return self._json({"erro": "pedido demasiado grande"}, 413)
            corpo = json.loads(self.rfile.read(n))
        except (ValueError, json.JSONDecodeError):
            return self._json({"erro": "JSON inválido"}, 400)
        if u.path == "/api/reportes":
            try:
                lat, lon = float(corpo["lat"]), float(corpo["lon"])
                tipo = str(corpo["tipo"])
                texto = str(corpo.get("descricao", "")).strip()[:MAX_TEXTO]
            except (KeyError, ValueError, TypeError):
                return self._json({"erro": "faltam campos"}, 400)
            if tipo not in TIPOS_OBSTACULO:
                return self._json({"erro": "tipo de obstáculo desconhecido"}, 400)
            s = G.encaixar(lat, lon)
            if s is None or s["distancia_clique"] > RAIO_ENCAIXE:
                return self._json({"erro": "o ponto fica longe de qualquer rua"}, 400)
            with TRANCA:
                lista = ler_reportes()
                if len(lista) >= MAX_REPORTES:
                    return self._json({"erro": "limite de reportes atingido"}, 429)
                r = {"id": uuid.uuid4().hex[:10], "lat": s["lat"], "lon": s["lon"], "troço": s["troço"], "rua": s["rua"],
                     "tipo": tipo, "descricao": texto, "quando": time.strftime("%Y-%m-%d %H:%M")}
                lista.append(r); gravar_reportes(lista)
            return self._json(r, 201)
        if u.path == "/api/reportes/resolver":
            with TRANCA:
                lista = ler_reportes()
                nova = [r for r in lista if r["id"] != str(corpo.get("id"))]
                if len(nova) == len(lista):
                    return self._json({"erro": "reporte não encontrado"}, 404)
                gravar_reportes(nova)
            return self._json({"ok": True})
        self.send_error(404)


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Dados: {os.path.basename(DADOS)} · http://localhost:{porta}")
    # 127.0.0.1: só este PC acede. Para mostrar noutro dispositivo da mesma rede, troca por "0.0.0.0".
    ThreadingHTTPServer(("127.0.0.1", porta), H).serve_forever()
