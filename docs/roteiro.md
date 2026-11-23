# Roteiro

O estudo avança em fases: primeiro os dados, depois uma única linha (Rio–São Paulo) que fica
mais realista a cada versão, depois a malha nacional. Cada passo entrega algo que se sustenta
sozinho e tem critério de validação explícito.

```
Fase 0  BASE       ambiente, testes, motor de corredor e greide                          ✅
Fase 1  DADOS      o atlas do Brasil: relevo, cidades, população, transporte, rios...    ← agora
Fase 2  RIO–SP     a mesma linha, ganhando uma camada de realismo por vez (v1 → v7)
Fase 3  MALHA      demanda entre cidades + projeto da rede nacional com orçamento
Fase 4  AVALIAÇÃO  custo-benefício, incerteza e publicação
```

## Fase 0 — Base ✅ (nov/2026)

- Ambiente reprodutível (pixi + conda-forge, `pixi.lock`), CLI, testes, catálogo de 23 fontes.
- Fetchers: Copernicus DEM (streaming), IBGE (malha municipal + Censo 2022).
- Greide ótimo por programação dinâmica, verificado contra força bruta.
- Corredor A* em 16 direções, verificado contra o scikit-image.
- Estudo de caso SP–RJ ponta a ponta (exploratório): é a v1 da Fase 2.

## Fase 1 — Dados: o atlas do Brasil

Reunir, com proveniência, tudo o que o otimizador vai precisar, num formato comum: GeoParquet
para vetores, COG para rasters, SIRGAS 2000. Cada fonte entra em `data/catalogo.yaml` e ganha
um módulo em `src/trembr/fontes/`.

**Decisões (2026-11-22):**
- **Sudeste primeiro** (SP, RJ, MG, ES, com 50 km de margem); o resto do país depois, com o
  mesmo código. As regiões ficam em `config/regioes.yaml`.
- Estradas e ferrovias existentes servem para três coisas: **contexto** no mapa, **atalho** no
  traçado (andar ao lado de uma faixa já aberta custa menos) e **concorrência** (tempo de carro e
  de ônibus contra o trem). Reaproveitar trilho existente está fora.
- Cada camada sai no **atlas**: uma figura PNG e uma entrada no mapa interativo
  (`pixi run atlas` → `resultados/atlas/<região>/index.html`).

| Camada | O que | Fontes (ids do catálogo) | Estado |
|---|---|---|---|
| Mapa base | país, UFs, municípios | `ibge_malha_uf`, `ibge_malha_municipal` | ✅ |
| Relevo | mosaico da região em 90 m; 30 m sob demanda dentro do corredor | `copernicus_glo90`, `copernicus_glo30`, `anadem` | ✅ Sudeste em 90 m (ANADEM na v4) |
| Validação do relevo | erro vertical de cada DEM contra referências de nível | `ibge_rede_altimetrica`, `fabdem` | |
| Cidades e população | sedes, população, PIB, hierarquia urbana, arranjos populacionais | `ibge_censo2022_pop`, `ibge_localidades`, `ibge_pib_municipal`, `ibge_regic` | ✅ |
| Uso do solo | mancha urbana, água, floresta | `ibge_areas_urbanizadas`, `mapbiomas` | ✅ mancha urbana (IBGE 2022) |
| Transporte existente | rodovias, ferrovias, estações, aeroportos | `osm_brasil`, `ontl_ferrovias`, `dnit_snv` | ✅ OSM (conferência com DNIT e ONTL a fazer) |
| Hidrografia | rios: cada travessia é uma ponte | `ana_bho` | |
| Áreas protegidas | unidades de conservação, terras indígenas | `cnuc_ucs`, `funai_ti` | ✅ UCs; TIs dependem de download manual |
| Geologia | litologia (custo de túnel e de corte) | `sgb_geologia` | |
| Demanda observada | passageiros de avião e de ônibus por par de cidades | `anac_dados_estatisticos`, `antt_rodoviario_interestadual`, `ibge_ligacoes_rodoviarias` | |
| Custos e validação | custos unitários; estudo oficial do TAV | `sicro`, `bm_china_hsr_2014`, `transit_costs`, `estudos_tav_rj_sp` | |

- [ ] **Entrega:** `trembr dados` baixando cada camada + um atlas (mapa do Brasil com as camadas).
- [ ] Atlas nacional: o HTML único com dados embutidos já tem ~13 MB só com o Sudeste; para o
  Brasil, passar os vetores para PMTiles servidos por um servidor local.
- [ ] **Validação:** URL testada de verdade (`confirmado: true`), proveniência registrada e
  contagens conferidas contra números oficiais (ex.: 5.570 municípios e 203,1 milhões de
  habitantes no Censo 2022).

## Fase 2 — Linha Rio–São Paulo, uma camada de realismo por vez

O mesmo pipeline roda a cada versão, com um ingrediente novo de cada vez. Cada versão é comparada
com a anterior (extensão, % em túnel, viaduto, corte e aterro, cidades atendidas, custo
relativo, tempo de viagem), para mostrar o que cada ingrediente muda no traçado.

| Versão | Ingrediente novo | Estado |
|---|---|---|
| v1 | só relevo (Copernicus 90 m) | ✅ achou o Vale do Paraíba sozinho |
| v2 | + cidades | próximo |
| v3 | + obstáculos: mancha urbana, rios, áreas protegidas | |
| v4 | + terreno nu (ANADEM 30 m) | |
| v5 | + geometria de 350 km/h | |
| v6 | + custos calibrados | |
| v7 | + tempo de viagem | |

**v2 — cidades.** O otimizador decide sozinho por quais cidades passar; nenhuma parada é imposta
à mão. Estações candidatas são as cidades do REGIC ao alcance do corredor (arranjo populacional
ou município isolado, `cidades_regic.parquet`); o custo entre duas candidatas
vem do A*; a escolha pesa a população atendida contra o custo de desviar. O peso entre "gente"
e "custo" é varrido, gerando uma fronteira: de uma linha direta, sem paradas, até uma linha que
atende todas as cidades grandes do caminho.

**v3 — obstáculos.** Mancha urbana (IBGE, Áreas Urbanizadas 2022): desapropriação cara, ou túnel. Rios (ANA):
ponte obrigatória. Unidades de conservação de proteção integral e terras indígenas: barreira.
Uso sustentável: custo extra de licenciamento.

**v4 — terreno nu.**
- [ ] Trocar o Copernicus (modelo de superfície, inclui copa de árvores) pelo ANADEM (terreno),
  greide em 30 m dentro de uma faixa ao redor do corredor.
- [ ] Medir o erro vertical de Copernicus, ANADEM e FABDEM contra as referências de nível do IBGE.

**v5 — geometria de 350 km/h.**
- [ ] Eixo por pontos de inflexão (PIs) + curvas circulares + clotoides, com R ≥ R_mín imposto.
- [ ] Otimização conjunta horizontal + greide (CMA-ES / NSGA-II): fronteira de Pareto custo × tempo.

**v6 — custos calibrados.**
- [ ] Custos unitários: SICRO + Banco Mundial (China) + Transit Costs → `status: calibrado`.
  Daqui em diante os valores em R$ podem ser citados.
- [ ] Calibrar o proxy da superfície de custo por regressão sobre greides ótimos.
- [ ] Greide: compensação corte/aterro (mass haul) e custo fixo de emboque de túnel e de
  encontro de viaduto.
- [ ] Geologia (SGB): custo de túnel e talude por litologia.

**v7 — tempo de viagem.**
- [ ] Simulador de marcha (resistência de Davis, curva de tração, limites por raio e rampa).
- [ ] Tempo porta a porta comparado com avião, ônibus e carro.

- [ ] **Validação da Fase 2:** comparar com o traçado do estudo oficial do TAV (2009):
  extensão, % em túnel e viaduto, estações.

## Fase 3 — A malha nacional

**Demanda.**
- [ ] Matriz OD observada (ANAC, ANTT, Ligações Rodoviárias) por arranjo populacional, em DuckDB.
- [ ] Modelo gravitacional por PPML + escolha modal logit.
- [ ] **Entrega:** ranking dos 30 melhores corredores do Brasil + mapa.
- [ ] **Validação:** backtest em linhas estrangeiras com demanda publicada; comparação com a
  demanda do estudo do TAV.

**Rede.**
- [ ] Cidades-polo (REGIC) e arcos candidatos (grafo de Gabriel).
- [ ] Esboço primeiro: custo dos arcos com o pipeline de triagem (v1–v3), para descobrir quais
  arcos entram na malha. Só esses recebem o tratamento completo (v4–v7).
- [ ] MILP de projeto de rede com orçamento por fase (Pyomo + HiGHS).
- [ ] **Entrega:** "o plano nacional": malha ótima para 2035, 2045 e 2060.

## Fase 4 — Avaliação e publicação

- [ ] Custo-benefício socioeconômico (Guia Geral de ACB do governo federal).
- [ ] Monte Carlo + índices de Sobol: quais premissas mais mexem no resultado.
- [ ] Alta velocidade (350 km/h) × intercidades (200 km/h), com a mesma metodologia.
- [ ] Isócronas: "até onde se chega de São Paulo em 2 h".
- [ ] Relatório técnico com metodologia, dados e código citáveis (DOI via Zenodo).
- [ ] Mapa interativo público.
- [ ] Série de vídeos.
