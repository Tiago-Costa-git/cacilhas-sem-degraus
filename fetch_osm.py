"""Descarrega ruas, escadas e rampas de Cacilhas do OpenStreetMap (Overpass API)
e grava data/osm.json. Precisa de internet:  python fetch_osm.py
Depois reinicia o server.py: ele usa osm.json se existir (apaga o ficheiro para voltar ao exemplo).
Os atributos vêm das etiquetas do OSM: o que não estiver etiquetado aparece como 'sem obstáculos',
por isso a recolha a pé da equipa continua a ser essencial."""
import json, os, re, time, urllib.error, urllib.parse, urllib.request
from graph import haversine

BBOX = "38.6830,-9.1560,38.6920,-9.1440"  # sul, oeste, norte, este
Q = f"""[out:json][timeout:60];
(way["highway"~"^(footway|pedestrian|steps|path|living_street|residential|service|tertiary|tertiary_link|secondary|secondary_link|primary|primary_link|unclassified|elevator)$"]({BBOX}););
out body;>;out skel qt;
(node["highway"="elevator"]({BBOX});node["amenity"="ferry_terminal"]({BBOX});node["highway"="bus_stop"]["name"]({BBOX});
 node["railway"~"station|tram_stop"]({BBOX});node["public_transport"="station"]({BBOX}););out;
(nwr["shop"]["name"]({BBOX});nwr["amenity"~"^(cafe|restaurant|fast_food|bar|pharmacy|bank|atm|hospital|clinic|doctors|dentist|toilets|post_office|police|library|school|kindergarten|community_centre|place_of_worship|townhall|marketplace)$"]["name"]({BBOX});
 nwr["tourism"~"^(museum|attraction|viewpoint|hotel|hostel|guest_house|information)$"]["name"]({BBOX});nwr["leisure"~"^(park|playground|sports_centre|fitness_centre)$"]["name"]({BBOX}););out center;"""

PRIO = {"ferry": 0, "metro": 1, "comboio": 1, "autocarro": 2}

CATEGORIAS = [("saude", ("pharmacy", "hospital", "clinic", "doctors", "dentist")), ("comer", ("cafe", "restaurant", "fast_food", "bar")),
              ("servicos", ("bank", "atm", "post_office", "police", "townhall", "toilets", "library", "community_centre")),
              ("educacao", ("school", "kindergarten")), ("lazer", ("park", "playground", "sports_centre", "fitness_centre", "museum",
              "attraction", "viewpoint", "place_of_worship", "information")), ("alojamento", ("hotel", "hostel", "guest_house"))]

def categoria(t):
    v = {t.get("amenity"), t.get("leisure"), t.get("tourism")}
    for c, ks in CATEGORIAS:
        if v & set(ks):
            return c
    return "lojas" if t.get("shop") or t.get("amenity") == "marketplace" else "outro"

def tipo_de(t):
    if t.get("amenity") == "ferry_terminal": return "ferry"
    if t.get("railway") == "tram_stop" or t.get("light_rail") == "yes": return "metro"   # Metro Sul do Tejo
    if t.get("railway") in ("station", "halt"): return "comboio"
    return "autocarro"  # inclui terminais rodoviários (public_transport=station sem railway)

def largura_cm(v):
    m = re.match(r"[\d.]+", v or "")
    return round(float(m.group()) * 100) if m else None

def altitudes(nos):
    """Altitude de cada nó (Open Topo Data, modelo EU-DEM 25 m; grátis, até 100 pontos por pedido, 1 pedido/s).
    Serve para o tempo e o custo das subidas. Se falhar, o grafo funciona na mesma sem declives."""
    lista = list(nos.values())
    try:
        for i in range(0, len(lista), 100):
            bloco = lista[i:i + 100]
            locs = "|".join(f"{n['lat']:.6f},{n['lon']:.6f}" for n in bloco)
            url = "https://api.opentopodata.org/v1/eudem25m?locations=" + urllib.parse.quote(locs, safe=",|.")
            pedido = urllib.request.Request(url, headers={"User-Agent": "CacilhasSemDegraus/1.0 (projeto escolar, Instituto Piaget)"})
            res = json.load(urllib.request.urlopen(pedido, timeout=60))["results"]
            for n, r in zip(bloco, res):
                if r.get("elevation") is not None:
                    n["alt"] = round(r["elevation"], 1)
            time.sleep(1.1)
        print("Altitudes:", sum(1 for n in lista if "alt" in n), "de", len(lista), "nós")
    except (urllib.error.URLError, KeyError, ValueError) as e:
        print("Aviso: não foi possível obter altitudes (" + str(e) + "). O mapa funciona sem declives.")


def main():
    pedido = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": Q}).encode(),
        headers={"User-Agent": "CacilhasSemDegraus/1.0 (projeto escolar, Instituto Piaget)", "Accept": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(pedido, timeout=90)
    except urllib.error.URLError as e:
        # Nunca desligar a verificação do certificado: isso abre a porta a um ataque man-in-the-middle.
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            raise SystemExit("O Python deste PC não tem os certificados instalados. Corre: pip install certifi  "
                             "(no macOS: 'Install Certificates.command') e tenta outra vez.")
        raise
    dados = json.load(resp)["elements"]
    nos = {e["id"]: e for e in dados if e["type"] == "node"}
    vias = [e for e in dados if e["type"] == "way" and "highway" in e.get("tags", {}) and "center" not in e]
    uso = {}
    for v in vias:
        for n in v["nodes"]: uso[n] = uso.get(n, 0) + 1
    elev = {i for i, n in nos.items() if n.get("tags", {}).get("highway") == "elevator"}
    out_nos, troços = {}, []
    for v in vias:
        t = v.get("tags", {}); ns = v["nodes"]
        corte = [i for i, n in enumerate(ns) if i in (0, len(ns) - 1) or uso[n] > 1]
        for i, j in zip(corte, corte[1:]):
            seg = ns[i:j + 1]
            d = sum(haversine(nos[a], nos[b]) for a, b in zip(seg, seg[1:]))
            w = largura_cm(t.get("width"))
            troços.append({"a": str(seg[0]), "b": str(seg[-1]), "nome": t.get("name", t["highway"]), "d": round(d),
                "geom": [[nos[n]["lat"], nos[n]["lon"]] for n in seg],  # forma real da rua, para desenhar curvas no mapa
                "degraus": t["highway"] == "steps", "rampa": t.get("ramp") == "yes" or t.get("ramp:wheelchair") == "yes",
                "elevador": t["highway"] == "elevator" or any(n in elev for n in seg),
                "estreito": bool(w and w < 120), "largura": w,
                "degradado": t.get("smoothness") in ("bad", "very_bad", "horrible", "very_horrible") or t.get("surface") in ("unpaved", "dirt", "gravel")})
            for n in (seg[0], seg[-1]):
                out_nos[str(n)] = {"id": str(n), "nome": str(n), "lat": nos[n]["lat"], "lon": nos[n]["lon"]}
    altitudes(out_nos)
    pois = []  # pontos de interesse com a posição REAL; o servidor encaixa-os na rua mais próxima
    for e in nos.values():
        t = e.get("tags", {})
        transporte = (t.get("amenity") == "ferry_terminal" or t.get("highway") == "bus_stop"
                      or t.get("railway") in ("station", "halt", "tram_stop") or t.get("public_transport") == "station")
        if t.get("name") and not e["id"] in elev and transporte:
            pois.append({"id": str(e["id"]), "nome": t["name"], "lat": e["lat"], "lon": e["lon"], "tipo": tipo_de(t)})
    locais, vistos = [], set()  # lojas, cafés, farmácias, etc.: camada opcional e pesquisa
    for e in dados:
        t = e.get("tags", {})
        if not t.get("name") or not any(k in t for k in ("shop", "amenity", "tourism", "leisure")) or t.get("amenity") == "ferry_terminal":
            continue
        lat, lon = (e.get("lat"), e.get("lon")) if e["type"] == "node" else (e.get("center", {}).get("lat"), e.get("center", {}).get("lon"))
        if lat is None or (t["name"], round(lat, 4), round(lon, 4)) in vistos:
            continue
        vistos.add((t["name"], round(lat, 4), round(lon, 4)))
        locais.append({"nome": t["name"], "lat": lat, "lon": lon, "cat": categoria(t),
                       "tipo": t.get("shop") or t.get("amenity") or t.get("tourism") or t.get("leisure")})
    destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "osm.json")
    json.dump({"meta": {"fonte": "OpenStreetMap (Overpass)"}, "nos": list(out_nos.values()), "troços": troços, "pois": pois, "locais": locais},
              open(destino, "w", encoding="utf-8"), ensure_ascii=False)
    print(len(out_nos), "nós,", len(troços), "troços ->", destino)

if __name__ == "__main__":
    main()
