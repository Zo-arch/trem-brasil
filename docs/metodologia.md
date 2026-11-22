# Metodologia

O estudo é um **modelo hierárquico em cinco camadas**. Cada camada resolve um problema bem
definido, com dados abertos, premissas explícitas (em `config/`) e uma forma de ser validada
contra o mundo real. As camadas de cima consomem os resultados das de baixo.

```
 0  DADOS        fontes abertas → data/raw (+ proveniência) → data/processed
 1  DEMANDA      quantas pessoas viajariam entre cada par de cidades?         [planejado M1]
 2  CORREDOR     por onde, grosso modo, passar entre duas cidades?            [exploratório]
 3  TRAÇADO      greide e geometria exatos; quantitativos e custo             [greide pronto; horizontal M3]
 4  REDE         com orçamento B, quais linhas construir e em que ordem?      [planejado M4]
 5  AVALIAÇÃO    tempo de viagem, custo-benefício, incerteza                  [planejado M5–M6]
```

---

## Camada 0 — Dados

- **Streaming em vez de acumular.** DEMs são lidos como Cloud-Optimized GeoTIFF por requisição
  HTTP de intervalo: só a janela necessária desce. O Brasil inteiro em 30 m passaria de 40 GB.
- **Proveniência obrigatória.** Todo arquivo baixado ganha `<arquivo>.proveniencia.json` com URL,
  data de acesso, licença e SHA-256.
- **Sistemas de referência.** Troca em SIRGAS 2000 (EPSG:4674); mapas nacionais na Policônica
  (EPSG:5880); todo cálculo métrico em SIRGAS 2000 / UTM do fuso do corredor (`crs.py`).
- **DSM × DTM.** O Copernicus mede a *superfície* (copa e prédios). Em mata atlântica isso
  infla a cota em 10–30 m e simula "morros" que não existem. O DEM-alvo do traçado é o
  **ANADEM** (terreno nu, Laipelt et al., 2024). A escolha do DEM entra na análise de
  sensibilidade, e o erro vertical de cada DEM será medido contra as referências de nível do IBGE.

## Camada 1 — Demanda (planejado)

1. **Matriz OD observada**: ANAC (avião), ANTT (ônibus interestadual) e IBGE Ligações
   Rodoviárias, agregadas por arranjo populacional.
2. **Modelo gravitacional por PPML** (Santos Silva & Tenreyro, 2006):
   $T_{ij} = \exp(\alpha_i + \gamma_j + \beta \ln C_{ij})\,\varepsilon_{ij}$, onde $C_{ij}$ é o
   custo generalizado de viagem. PPML lida com zeros e heterocedasticidade, ao contrário do MQO em log.
3. **Escolha modal logit multinomial** entre carro, ônibus, avião e trem.
4. **Validação por backtest**: aplicar o modelo a corredores com trem de alta velocidade em
   operação e comparar com a demanda real publicada.

## Camada 2 — Corredor (exploratório, funcionando)

Busca de caminho mínimo (A*, Hart et al., 1968) numa grade de 90 m, em 16 direções.
Num movimento em "pulo de cavalo", a média de custo inclui as células atravessadas no meio, então
o caminho não consegue pular barreiras finas. A heurística $h = c_{min}\,d$ é consistente, então o
resultado é igual ao de Dijkstra; isso é testado contra o `MCP_Geometric` do scikit-image.

**Superfície de custo** (`terreno/superficie_custo.py`). Como o greide ainda não é conhecido, o
custo de atravessar uma célula é estimado com o *mesmo* modelo de seção da camada 3:

$$h = \sigma_w + \max(0,\, S - i_{max})\,L, \qquad c = c_{via} + \tfrac12[c_{sec}(+h) + c_{sec}(-h)]$$

- $\sigma_w$: desvio-padrão do terreno sem tendência, numa janela $w$;
- $S$: declividade da superfície suavizada;
- $L$: comprimento característico.

> **Não calibrado.** $w = 1{,}5$ km e $L = 1$ km são escolhas iniciais. Calibração (M2):
> amostrar milhares de trechos, calcular o custo *ótimo* do greide em cada um (camada 3) e
> ajustar o proxy por regressão. Daí em diante, o corredor herda a precisão do greide.

## Camada 3 — Traçado

### 3a. Modelo de seção (`tracado/secao.py`)

Com $d = z_{trilho} - z_{terreno}$, em cada ponto escolhe-se a estrutura tecnicamente viável
de menor custo por metro:

| Situação | Estrutura | Custo por metro |
|---|---|---|
| $0 \le d \le H_{aterro}$ | aterro | $p_{aterro}\,(b + n_a d)\,d$ |
| $H_{v,min} \le d \le H_{v,max}$ | viaduto | $p_{viaduto} + p_{v,h}\,d$ |
| $0 < -d \le D_{corte}$ | corte | $p_{corte}\,(b + n_c |d|)\,|d|$ |
| $-d \ge D_{túnel}$ | túnel | $p_{túnel}$ |

Aqui $b$ é a largura da plataforma e $n$ o talude (H:V). Onde duas faixas de viabilidade se
sobrepõem, vence a mais barata. A configuração rejeita faixas de $d$ sem nenhuma estrutura viável.

### 3b. Greide ótimo por programação dinâmica (`tracado/perfil.py`)

Minimiza $\sum_i c(z_i - z_{g,i})\,\Delta s$ sujeito a:

- **rampa máxima**: $|z_{i+1} - z_i| \le i_{max}\,\Delta s$. Essa é a "inclinação máxima": vale
  para o **trilho**, não para o terreno. O terreno pode ser íngreme; quem absorve a diferença são
  corte, aterro, túnel e viaduto;
- **raio mínimo de curva vertical** $R_v$: a rampa muda no máximo $\Delta s / R_v$ por estaca;
- pontas na cota do terreno, com rampa de estação.

**Discretização exata.** Estado $(j, k)$: cota $z_0 + j\Delta z$ e rampa $k\,\Delta i$, com
$\Delta i = \Delta s / R_v$ e $\Delta z = \Delta i\,\Delta s$. A transição
$(j', k') \to (j' + k,\; k)$ com $|k - k'| \le 1$ respeita as duas restrições por construção.
$\Delta s$ é ajustado para que $i_{max}/\Delta i$ seja inteiro (rampa máxima sem arredondamento;
para 350 km/h, $\Delta s = 93{,}75$ m). Pelo princípio de Bellman, a solução é o **ótimo global**
do problema discretizado. O teste `test_programacao_dinamica_igual_a_forca_bruta` compara com
enumeração exaustiva em instâncias aleatórias (Hypothesis). Complexidade: $O(nJK)$.

**Limitações conhecidas** (todas no roteiro):

1. Sem compensação de volumes corte → aterro (mass haul). Superestima o custo de terraplenagem.
2. Sem custo fixo de emboque de túnel / encontro de viaduto. Permite trechos curtos alternados;
   corrige-se com uma dimensão de "estrutura atual" no estado.
3. Sem restrição de rampa média em 10 km (TSI). É verificada depois, ainda não imposta.
4. Pontes sobre rios não são forçadas, porque a hidrografia ainda não entrou.
5. Geologia homogênea: mesmo preço de túnel em granito ou em solo mole.

### 3c. Geometria horizontal (`tracado/geometria.py`): versão de triagem

Hoje a rota do raster é simplificada (Douglas–Peucker) e suavizada (Chaikin), e o raio de
curvatura é **medido**, não imposto. No estudo SP–RJ o raio mínimo fica bem abaixo dos 7 km
exigidos. **M3**: parametrizar o eixo por pontos de inflexão (PIs) com curvas circulares e
clotoides ($R \ge R_{min}$) e otimizar os PIs junto com o greide. O greide ótimo é a função
objetivo; a busca é metaheurística (CMA-ES ou NSGA-II via pymoo, para a fronteira custo × tempo),
na linha de Jong & Schonfeld (2003) e Pu, Li & Schonfeld (2021).

## Camada 4 — Rede (planejado)

Projeto de rede como MILP (Pyomo + HiGHS):

- arcos candidatos = grafo de Gabriel entre cidades-polo (REGIC);
- custo de cada arco = camada 3; benefício = horas economizadas × valor do tempo (camada 1);
- restrição de orçamento por fase (2035, 2045, 2060), para a malha crescer em etapas.

## Camada 5 — Avaliação (planejado)

- **Simulador de marcha**: resistência de Davis, curva de tração, limites de velocidade por raio
  de curva e por rampa. Saída: tempo de viagem e energia.
- **Custo-benefício** pelo Guia Geral de ACB do governo federal.
- **Incerteza**:
  - Monte Carlo sobre custos unitários, com distribuições de sobrecusto de referência
    (Flyvbjerg et al., 2002);
  - DEM (Copernicus × ANADEM × FABDEM);
  - demanda.
- **Sensibilidade global**: índices de Sobol (SALib; Saltelli et al., 2008). Respondem "qual
  premissa mais mexe no resultado?".

## Princípios de rigor do projeto

1. **Toda premissa numérica fica num YAML com fonte.** Nenhum número mágico no código.
2. **Todo otimizador é testado contra uma referência independente** (força bruta,
   scikit-image), não só contra "parece razoável".
3. **Sanidade física em todo estudo de caso.** Exemplo: sem nenhuma indicação, o corredor SP–RJ
   achou o Vale do Paraíba, onde já correm a Dutra e a antiga Central do Brasil.
4. **Ambiente travado** (`pixi.lock`): qualquer pessoa reproduz os mesmos números.
5. **Placeholders marcados como tal.** Custos em R$ só serão citados com `status: calibrado`.

## Referências

- Bellman, R. (1957). *Dynamic Programming*. Princeton University Press.
- Flyvbjerg, B., Holm, M. S., & Buhl, S. (2002). Underestimating costs in public works projects:
  Error or lie? *Journal of the American Planning Association*, 68(3), 279–295.
- Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A formal basis for the heuristic
  determination of minimum cost paths. *IEEE Trans. Systems Science and Cybernetics*, 4(2), 100–107.
- Hawker, L. et al. (2022). A 30 m global map of elevation with forests and buildings removed.
  *Environmental Research Letters*, 17, 024016.
- Jong, J.-C., & Schonfeld, P. (2003). An evolutionary model for simultaneously optimizing
  three-dimensional highway alignments. *Transportation Research Part B*, 37(2), 107–128.
- Laipelt, L. et al. (2024). ANADEM: A Digital Terrain Model for South America. *Remote Sensing*,
  16(13), 2321. doi:10.3390/rs16132321
- Pu, H., Li, W., & Schonfeld, P. et al. (2021). Concurrent optimization of mountain railway
  alignment and station locations using a 3D distance transform. *IEEE Access*.
- Saltelli, A. et al. (2008). *Global Sensitivity Analysis: The Primer*. Wiley.
- Santos Silva, J. M. C., & Tenreyro, S. (2006). The log of gravity. *Review of Economics and
  Statistics*, 88(4), 641–658.
- Banco Mundial (2014). *High-Speed Railways in China: A Look at Construction Costs*.
  China Transport Topics.
- TB 10621-2014. *Code for Design of High-speed Railway* (China).
- Regulamento (UE) 1299/2014. Especificação técnica de interoperabilidade — Infraestrutura.
