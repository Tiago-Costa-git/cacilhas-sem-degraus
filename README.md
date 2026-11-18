# ♿ Cacilhas Sem Degraus

> A rota mais curta e a rota que consegues fazer.
> *Accessible routing for Cacilhas (Almada, Portugal): compares the shortest walking route with the best route for wheelchairs, crutches, strollers and reduced mobility.*

**🌐 Experimentar online:** https://O_TEU_USERNAME.github.io/cacilhas-sem-degraus/

<!-- Depois de publicar: tira uma captura de ecrã com uma rota, guarda-a em docs/rota.png e tira o comentário da linha abaixo -->
<!-- ![Rota acessível em Cacilhas](docs/rota.png) -->

Projeto da unidade curricular **Fundamentos de Inteligência Artificial** (AI Expo) do CTeSP em Cibersegurança, no Instituto Piaget de Almada (2026/27). **Em desenvolvimento.**

## O problema

O caminho mais curto entre o barco de Cacilhas e a Avenida 25 de Abril tem escadas, passeios estreitos e subidas. Para quem anda de cadeira de rodas, de muletas ou com um carrinho de bebé, a rota "mais curta" do Google Maps muitas vezes não é possível de fazer.

## O que faz

- Compara lado a lado a **rota mais curta a pé** e a **melhor rota para o teu perfil**, com os minutos e metros de desvio.
- **6 perfis de mobilidade**: a pé, cadeira de rodas manual e elétrica, muletas ou andarilho, carrinho de bebé e mobilidade reduzida. Cada perfil tem a sua velocidade e as suas regras para escadas, passeios estreitos, passeios degradados e inclinação.
- **Dijkstra e A\***, com uma animação que mostra os nós que cada algoritmo explora.
- **Reportar obstáculos** (carro no passeio, obras, buraco…): as rotas acessíveis passam a evitar esse troço.
- Pesquisa de paragens, ruas e locais, botão "a minha localização" e Street View.

## Como funciona

A rede pedonal vem do **OpenStreetMap** e é transformada num grafo, em que os nós são cruzamentos e as arestas são troços de rua. O custo de cada troço depende do perfil:

```
custo = distância × (1 + α·estreito + β·degradado)
        × penalização de escadas (proibido = ∞, evitar = ×4 a ×6)
        × 5 se houver um obstáculo reportado
        × penalização por inclinação (acima de 8% para cadeiras e carrinhos)
```

O tempo é calculado troço a troço: a velocidade do perfil, a função de Tobler nas subidas, o tempo nas escadas, a espera nos elevadores e o tempo de atravessar cada cruzamento. Todos os valores são **estimativas** e ainda vão ser calibradas com a recolha de dados a pé.

## Duas formas de correr

| | Versão online (GitHub Pages) | Servidor local (Python) |
|---|---|---|
| Motor de rotas | `static/motor.js`, no browser | `graph.py` |
| Obstáculos reportados | ficam só no teu browser | ficam em `data/reportes.json`, partilhados por quem usa o servidor |
| Precisa de instalar | nada | Python 3.9+ (só a biblioteca padrão) |

O `motor.js` é uma tradução do `graph.py`. O teste `testes/paridade.py` corre 300 pedidos de rota nas duas versões e confirma que os resultados são iguais. O site só é publicado se este teste passar.

### Servidor local

```bash
python server.py           # abre http://localhost:8000
python fetch_osm.py        # opcional: volta a descarregar os dados do OpenStreetMap
python testes/paridade.py  # opcional: compara Python e JavaScript (precisa do Node.js)
```

Mapa de fundo da CARTO (opcional): copia `static/config.exemplo.js` para `static/config.js` e cola a chave. O `config.js` está no `.gitignore` e nunca vai para o GitHub.

## Segurança

O projeto foi feito num curso de cibersegurança, por isso teve estes cuidados:

- **Nenhuma chave no repositório**: a da CARTO fica num ficheiro local que é ignorado pelo git.
- **O servidor só aceita ligações do próprio PC** (127.0.0.1) e valida todos os parâmetros: tamanho do pedido, limites de α e β, tipos de obstáculo e texto com tamanho máximo.
- **Escrita atómica** do ficheiro de reportes, para que um erro a meio não o corrompa.
- **Proteção contra path traversal** nos ficheiros estáticos.
- O `fetch_osm.py` **nunca desliga a verificação dos certificados HTTPS**.

## Estrutura

```
graph.py              grafo, Dijkstra, A*, custos e tempos por perfil
server.py             servidor HTTP + API (/api/grafo, /api/rota, /api/encaixar, /api/reportes)
fetch_osm.py          descarrega ruas, escadas, paragens e locais do OpenStreetMap
static/index.html     interface (Leaflet)
static/motor.js       motor de rotas da versão online
data/                 osm.json (dados reais) e cacilhas.json (exemplo)
testes/paridade.py    garante que motor.js == graph.py
.github/workflows/    publicação automática e atualização dos dados
```

## Próximos passos

- [ ] Recolha a pé: largura dos passeios, rampas e estado do piso
- [ ] Calibrar as velocidades com cronómetro
- [ ] Apresentação na AI Expo

## Equipa

**Tiago Costa** · **André Filipe** · **Guilherme Lopes**

## Créditos

Dados © [contribuidores do OpenStreetMap](https://www.openstreetmap.org/copyright) (ODbL) · Altitudes: [Open Topo Data](https://www.opentopodata.org/) · Mapa: [Leaflet](https://leafletjs.com/), OpenStreetMap, Esri
