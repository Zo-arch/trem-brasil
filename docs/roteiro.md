# Roteiro

Cada marco entrega um resultado que se sustenta sozinho e tem critério de validação explícito.

## M0 — Base do projeto ✅ (nov/2026)
- Ambiente reprodutível (pixi + conda-forge, `pixi.lock`), CLI, testes, catálogo de 23 fontes.
- Fetchers: Copernicus DEM (streaming), IBGE (malha + Censo 2022).
- Greide ótimo por programação dinâmica, verificado contra força bruta.
- Corredor A* em 16 direções, verificado contra o scikit-image.
- Estudo de caso SP–RJ ponta a ponta (exploratório).

## M1 — Demanda: onde o trem se paga
- [ ] Fetchers: ANAC (passageiros por par de aeroportos), ANTT ônibus, IBGE PIB, REGIC, ligações rodoviárias.
- [ ] Matriz OD por arranjo populacional (DuckDB sobre os microdados).
- [ ] Gravitacional PPML + logit modal.
- [ ] **Entrega:** ranking dos 30 melhores corredores do Brasil + mapa.
- [ ] **Validação:** backtest em linhas estrangeiras com demanda publicada; comparação com a demanda do estudo do TAV (2009).

## M2 — Terreno e custos de verdade
- [ ] Fetcher ANADEM; medir o erro vertical de Copernicus/ANADEM/FABDEM contra as referências de nível do IBGE.
- [ ] Restrições: MapBiomas (urbano, água), unidades de conservação, terras indígenas, rios (ANA).
- [ ] Geologia (SGB): custo de túnel e talude por litologia.
- [ ] Calibrar custos unitários: SICRO + Banco Mundial (China) + Transit Costs → `status: calibrado`.
- [ ] Calibrar o proxy da superfície de custo por regressão sobre greides ótimos.
- [ ] Greide: mass haul (compensação corte/aterro) e custo fixo de emboque.

## M3 — Traçado horizontal de projeto
- [ ] Eixo por PIs + curvas circulares + clotoides, com R ≥ R_mín imposto.
- [ ] Otimização conjunta horizontal + greide (CMA-ES / NSGA-II), fronteira de Pareto custo × tempo.
- [ ] Greide em 30 m (ANADEM) dentro de uma faixa ao redor do corredor.
- [ ] **Validação:** comparar SP–RJ com o traçado do estudo oficial do TAV (extensão, % em túnel e viaduto).

## M4 — A malha
- [ ] Cidades-polo (REGIC) e arcos candidatos (grafo de Gabriel).
- [ ] Custo de cada arco com M2–M3, em lote (paralelo).
- [ ] MILP de projeto de rede com orçamento por fase (Pyomo + HiGHS).
- [ ] **Entrega:** "o plano nacional": malha ótima para 2035, 2045 e 2060.

## M5 — Operação
- [ ] Simulador de marcha: tempos de viagem porta a porta comparados com avião e carro.
- [ ] Isócronas: "até onde se chega de São Paulo em 2 h".

## M6 — Avaliação e incerteza
- [ ] Custo-benefício socioeconômico (Guia Geral de ACB).
- [ ] Monte Carlo + índices de Sobol: quais premissas mais mexem no resultado.
- [ ] Comparação alta velocidade (350 km/h) × intercidades (200 km/h) com a mesma metodologia.

## M7 — Publicação
- [ ] Relatório técnico com metodologia, dados e código citáveis (DOI via Zenodo).
- [ ] Mapa interativo público.
- [ ] Série de vídeos.
