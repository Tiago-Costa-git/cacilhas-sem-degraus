# Cacilhas Sem Degraus
Requisitos: Python 3.9+ (sem bibliotecas externas) e internet no browser (mapa e Leaflet).

1. `python server.py` e abre http://localhost:8000 (só este PC acede; ver comentário no fim de server.py).
2. (opcional, precisa de internet) `python fetch_osm.py` gera `data/osm.json` com dados reais do OpenStreetMap; volta a correr o servidor.
3. (opcional) Mapa de fundo da CARTO: copia `static/config.exemplo.js` para `static/config.js` e cola a vossa chave. Sem isso, o site usa o mapa do OpenStreetMap, que não precisa de chave.
4. Os dados da recolha a pé editam-se em `data/cacilhas.json` (apaga `data/osm.json` para o servidor usar este ficheiro).

IMPORTANTE: voltem a correr `python fetch_osm.py`. A nova versão (1) inclui as avenidas principais (ex.: Av. 25 de Abril),
que antes ficavam de fora, e (2) obtém a altitude de cada ponto (Open Topo Data) para o tempo e o custo das subidas.

Perfis de mobilidade (graph.py, PERFIS): a pé, cadeira de rodas manual e elétrica, muletas/andarilho, carrinho de bebé
e mobilidade reduzida. Cada perfil tem velocidade em plano, regra para escadas (permitido / evitar / proibido) e custos
para passeios estreitos e degradados. Os valores são ESTIMATIVAS: calibrem-nos com cronómetro na recolha a pé.

Custo de um troço: c(e) = d x (1 + alpha*estreito + beta*degradado), x p_escadas se o perfil "evita" escadas,
infinito se as "proíbe", x5 se tiver um obstáculo reportado (perfis que não são "a pé").

Obstáculos reportados ficam em data/reportes.json (criado automaticamente). Botão "Reportar obstáculo" no mapa.

Tempo de um troço: comprimento / velocidade média do perfil, x inclinação (função de Tobler a pé; subidas
pesam mais em cadeira ou carrinho), x2 a 4 em escadas, +60 s em elevadores, + 3 s (a pé) ou 6 s por cruzamento.
Cadeiras e carrinhos evitam ruas com mais de 8% de inclinação, se houver alternativa.

Mapa de fundo (botões no canto): "Simples" = CARTO Voyager (se houver chave em static/config.js) -> Stadia OSM Bright
(grátis em localhost) -> OpenStreetMap; "Detalhado" = OpenStreetMap (lojas, cafés, números de porta);
"Satélite" = Esri World Imagery. Camadas opcionais: lojas e locais (por categoria), paragens, escadas, rede pedonal.
As lojas e locais vêm do fetch_osm.py (voltem a corrê-lo) e também entram na pesquisa.

Street View: os botões abrem o Google Maps (Maps URLs oficiais, sem chave) no ponto escolhido, num separador novo.
As fotografias não são copiadas para o site.

"Minutos a mais" = desvio da rota acessível face à rota mais curta, medido ao MESMO ritmo (só conta o caminho extra).
