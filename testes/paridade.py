"""Confirma que o motor da versão online (static/motor.js) dá os mesmos resultados que graph.py.
Uso: python testes/paridade.py   (precisa do Node.js instalado)
Testa os dados reais e uma cópia com altitudes, escadas, passeios estreitos e obstáculos inventados,
para passar por todos os ramos do código."""
import json, math, os, random, subprocess, sys, tempfile
AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
from graph import Grafo, PERFIS

def casos(dados, n, semente):
    rnd = random.Random(semente)
    G = Grafo(dados_path(dados))
    lats = [x["lat"] for x in dados["nos"]]; lons = [x["lon"] for x in dados["nos"]]
    out = []
    while len(out) < n:
        a = f"{rnd.uniform(min(lats), max(lats)):.6f},{rnd.uniform(min(lons), max(lons)):.6f}"
        b = f"{rnd.uniform(min(lats), max(lats)):.6f},{rnd.uniform(min(lons), max(lons)):.6f}"
        perfil = rnd.choice([p for p in PERFIS if p != "a_pe"])
        alg = rnd.choice(["dijkstra", "astar"])
        al = rnd.choice([None, 0.0, 1.5, 5.0]); be = rnd.choice([None, 0.0, 2.0])
        out.append({"a": a, "b": b, "perfil": perfil, "alg": alg, "alpha": al, "beta": be})
    return out

_tmp = {}
def dados_path(d):
    k = id(d)
    if k not in _tmp:
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8"); json.dump(d, f); f.close(); _tmp[k] = f.name
    return _tmp[k]

def python(dados, reportes, cs):
    G = Grafo(dados_path(dados)); G.definir_reportes(reportes); res = []
    for c in cs:
        try: res.append(G.comparar(c["a"], c["b"], c["perfil"], c["alpha"], c["beta"], c["alg"]))
        except ValueError as e: res.append({"erro": "x"})
    return {"pois": G.pois, "res": res, "snap": [G.encaixar(*map(float, c["a"].split(","))) for c in cs]}

JS = r"""
const fs=require('fs');const {Grafo}=require(process.argv[2]);
const [dados,reportes,cs]=JSON.parse(fs.readFileSync(0,'utf8'));
const G=new Grafo(dados);G.definirReportes(reportes);
const res=cs.map(c=>{try{return G.comparar(c.a,c.b,c.perfil,c.alpha,c.beta,c.alg)}catch(e){return {erro:"x"}}});
const snap=cs.map(c=>G.encaixar(...c.a.split(",").map(Number)));
process.stdout.write(JSON.stringify({pois:G.pois,res,snap}));
"""

def igual(a, b, cam="", erros=None):
    if isinstance(a, float) or isinstance(b, float):
        if not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)):
            erros.append(f"{cam}: {a!r} != {b!r}")
    elif isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k not in a or k not in b: erros.append(f"{cam}.{k}: falta num dos lados")
            else: igual(a[k], b[k], f"{cam}.{k}", erros)
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b): erros.append(f"{cam}: tamanho {len(a)} != {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)): igual(x, y, f"{cam}[{i}]", erros)
    elif a != b: erros.append(f"{cam}: {a!r} != {b!r}")
    return erros

def correr(nome, dados, reportes, n=150):
    cs = casos(dados, n, 7)
    py = json.loads(json.dumps(python(dados, reportes, cs)))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f: f.write(JS); js_file = f.name
    p = subprocess.run(["node", js_file, os.path.join(RAIZ, "static", "motor.js")], input=json.dumps([dados, reportes, cs]),
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode: print(p.stderr); sys.exit(1)
    js = json.loads(p.stdout)
    erros = igual(py, js, nome, [])
    ok = sum(1 for r in py["res"] if "erro" not in r)
    print(f"{nome}: {n} casos ({ok} com rota calculada) -> {'IGUAL' if not erros else str(len(erros)) + ' diferenças'}")
    for e in erros[:15]: print("  ", e)
    return not erros

if __name__ == "__main__":
    f = os.path.join(RAIZ, "data", "osm.json")
    if not os.path.exists(f): f = os.path.join(RAIZ, "data", "cacilhas.json")
    reais = json.load(open(f, encoding="utf-8"))
    rnd = random.Random(3); sint = json.loads(json.dumps(reais))
    for n in sint["nos"]:  # relevo suave: sobe de Cacilhas (rio) para o interior, como na realidade
        n["alt"] = round(max(0.0, (38.6890 - n["lat"]) * -4000 + (n["lon"] + 9.150) * 3000 + 25 + 6 * math.sin(n["lat"] * 3000)), 1)
    for e in sint["troços"]:
        for c, p in (("degraus", .08), ("rampa", .03), ("elevador", .02), ("estreito", .2), ("degradado", .15)):
            if rnd.random() < p: e[c] = True
        if e.get("estreito") and rnd.random() < .5: e["largura"] = rnd.randint(60, 120)
    G = Grafo(dados_path(sint))
    reps = [{"id": str(i), "troço": rnd.randrange(len(G.troços)), "tipo": "Obras"} for i in range(25)]
    a = correr("dados reais", reais, [])
    b = correr("dados com altitudes, escadas e obstáculos inventados", sint, reps)
    sys.exit(0 if a and b else 1)
