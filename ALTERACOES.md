# O que mudou nesta versão

## 1. Pin no sítio certo
- Antes: o clique saltava para o **cruzamento mais próximo** (um nó do grafo). Em ruas compridas o pin ficava até 60 m ao lado; e às vezes caía num pedaço de rua **isolado**, sem rota possível ("sem rota").
- Agora: o clique encaixa no **ponto mais próximo sobre a rua** (projeção na geometria do troço), só na **rede principal**. O troço é dividido em dois com um nó temporário, por isso a rota começa e acaba exatamente onde está o pin.
- Se o clique for longe de uma rua (ex.: dentro de um quarteirão), aparece uma linha tracejada até ao ponto da rua e o texto diz a que distância ficou. Mais de 80 m: o clique é recusado.
- Os pontos de interesse usam a posição real da paragem, também encaixada na rua.

## 2. Tempo de chegada
- Antes: minutos = distância / velocidade. Problemas:
  - "minutos a mais" comparava 1,4 m/s com 1,1 m/s: **na mesma rota dava +2 min** só pela velocidade diferente;
  - escadas contavam como plano; o elevador não tinha espera;
  - a rota começava num cruzamento e não no ponto clicado, por isso a distância estava errada.
- Agora: tempo troço a troço (ver README), mostrado em minutos inteiros; "minutos a mais" mede só o desvio, ao mesmo ritmo.

## 3. Segurança (curso de cibersegurança)
- A chave da CARTO saiu do código principal: fica em `static/config.js` (opcional, fora do ZIP e do GitHub). Sem ela, o site usa o mapa do OpenStreetMap, que não precisa de chave.
- `fetch_osm.py` já não desliga a verificação do certificado HTTPS (risco de man-in-the-middle); agora explica como instalar os certificados.
- O servidor só aceita ligações deste PC (127.0.0.1) e valida os parâmetros da rota.

## 4. Correções de dados
- "Terminal Rodoviário de Cacilhas" estava classificado como comboio → autocarro.
- Paragens do Metro Sul do Tejo passam a "metro"; "Cacilhas" barco e metro já não se fundem num só ponto.
- Removida a pasta `__pycache__`.

# Versão 3 (10/11)

- **Zoom até 21:** o mapa de fundo deixava de aparecer depois do zoom 19 (o OpenStreetMap só tem imagens até aí). Agora as imagens esticam nos zooms 20 e 21, por isso dá para ver as ruas mais de perto.
- **Perfis de mobilidade:** cadeira de rodas manual, cadeira elétrica, muletas/andarilho, carrinho de bebé e mobilidade reduzida, cada um com a sua velocidade e regras (ex.: muletas evitam escadas mas usam-nas se não houver alternativa; cadeira e carrinho nunca).
- **Reportar obstáculo:** botão no mapa → tocar na rua → escolher o tipo (carro no passeio, obras, buraco, falta de rampa…) e detalhes. Fica no mapa com um aviso e as rotas acessíveis passam a evitá-lo. "Já foi resolvido" remove-o.
  - Segurança: tipos fechados, texto limitado a 300 caracteres e mostrado sempre como texto (sem HTML, contra XSS), pedidos até 4 KB, máximo 500 reportes, escrita atómica do ficheiro.
- **Street View:** botões "Ver A/B no Street View" e "Ver este local" em cada troço e obstáculo (abre o Google Maps).
- **Interface nova:** mais simples, com escolha do perfil por ícones, cartões de tempo maiores, "trocar origem e destino", e a parte técnica (algoritmo e custos) recolhida em "Como funciona".
- Corrigido: carregar no botão de reportar disparava um clique no mapa por baixo dele.

# Versão 4 (10/11)

- **Tempos mais realistas:** a versão 3 dava 6 min 35 s de Cacilhas (metro) à Av. 25 de Abril; o Google Maps dá 9 min.
  Causas: velocidade de 1,4 m/s (ritmo em plano, sem paragens), nenhuma conta com a subida da Rua Cândido dos Reis
  nem com os cruzamentos. Agora: velocidades médias de cidade (a pé 1,25 m/s), atraso por cruzamento e declive
  (com altitudes, depois de correr o fetch_osm.py). Sem altitudes a mesma rota dá ~8 min; com a subida, ~9-10 min.
- **Mapa mais limpo:** fundo claro e sem cores (Stadia/CARTO, ou OpenStreetMap a cinzento); a rede, as escadas e as
  paragens ficam em camadas que se ligam no canto; nomes das paragens só ao passar o rato.
- **Pesquisa:** caixas de texto para origem e destino, com sugestões enquanto se escreve (ruas e paragens, sem
  acentos, setas e Enter). Escolher uma rua mostra-a no mapa; tocar ao longo dela afina o ponto. "Usar a minha
  localização" e "Trocar".
- **Percurso passo a passo:** lista das ruas da rota acessível, com metros e avisos (escadas, inclinação, obstáculo).
- `fetch_osm.py` inclui avenidas principais e altitudes.

# Versão 5 (10/11)

- **Estilo do mapa:** volta o estilo colorido de antes, mas mais limpo no modo "Simples". Botões para mudar para
  "Detalhado" (OpenStreetMap com lojas, cafés e números de porta) ou "Satélite".
- **Mostrar mais coisas, se quiser:** interruptor "Lojas e locais", com filtro por categoria (comer, saúde, lojas,
  serviços, lazer…). Os locais também aparecem na pesquisa. Precisa de voltar a correr o fetch_osm.py.
- **Interface "liquid glass":** mapa em ecrã inteiro com painéis de vidro fosco (desfoque e transparência),
  animações suaves: painel a entrar, rota a desenhar-se ao longo da rua, tempos a contar até ao valor final,
  pins a cair, passos a aparecer em sequência, interruptores e seletor animados. Quem tem "reduzir movimento"
  ativo no sistema vê tudo sem animações. No telemóvel o painel é uma folha em baixo e as camadas abrem num botão.
