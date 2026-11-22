# trem-brasil

**Estudo científico aberto de uma malha ferroviária de alta velocidade para o Brasil.**

Pergunta central: *com um orçamento dado, qual malha de trem de alta velocidade traz mais
benefício ao país, por onde exatamente ela deve passar e quanto custa?* Tudo com dados abertos,
premissas explícitas e código reprodutível.

![Primeiro traçado exploratório SP–RJ](docs/img/sp_rj_as350.png)

*Primeiro resultado (exploratório). Sem receber nenhuma indicação de caminho, o otimizador
encontrou o Vale do Paraíba, o mesmo corredor da Dutra, e desce a Serra das Araras em túnel, na
rampa máxima de 30‰. Os custos ainda são placeholder.*

## Arquitetura: modelo em 5 camadas

```
 0  DADOS      fontes abertas → raw (+proveniência) → processed      src/trembr/fontes
 1  DEMANDA    gravitacional PPML + logit modal                       src/trembr/demanda    (M1)
 2  CORREDOR   superfície de custo + A* 16 direções                   src/trembr/terreno, tracado/corredor
 3  TRAÇADO    greide ótimo (prog. dinâmica) + geometria + custos     src/trembr/tracado
 4  REDE       MILP de projeto de rede com orçamento por fase         src/trembr/rede       (M4)
 5  AVALIAÇÃO  marcha, custo-benefício, Monte Carlo + Sobol           src/trembr/operacao, avaliacao (M5–M6)
```

Detalhes, equações e limitações: [docs/metodologia.md](docs/metodologia.md).
O que vem depois: [docs/roteiro.md](docs/roteiro.md).

## Stack

| Para quê | Ferramenta | Por quê |
|---|---|---|
| Ambiente | **pixi** + conda-forge | GDAL, PROJ e solvers nativos iguais no Windows e no Linux; `pixi.lock` trava tudo |
| Raster | GDAL, rasterio, rioxarray, xarray/dask | leitura de COG por streaming, processamento em blocos |
| Vetor | geopandas, shapely 2, pyogrio, GeoParquet | formato colunar rápido e padrão |
| Tabelas grandes | DuckDB, Polars, PyArrow | microdados da ANAC/ANTT sem estourar 16 GB de RAM |
| Algoritmos | NumPy, SciPy, **Numba** | programação dinâmica e A* compilados (segundos, não horas) |
| Otimização | **Pyomo + HiGHS**, SCIP, pymoo | MILP de rede (HiGHS é o melhor solver aberto), MINLP, multiobjetivo |
| Estatística | statsmodels, SALib | PPML, logit, sensibilidade de Sobol |
| Qualidade | pytest + **Hypothesis**, ruff | testes de propriedade e contra força bruta |
| Config | pydantic + YAML | premissas validadas, cada número com fonte |

## Como rodar

```bash
pixi install                  # cria o ambiente (≈3,5 GB, uma vez)
pixi run test                 # testes
pixi run trembr --help        # CLI
pixi run trembr dados catalogo
pixi run dados-ibge           # municípios + Censo 2022 → data/processed/ibge
pixi run estudo-sp-rj         # corredor + greide SP–RJ → resultados/sp_rj_as350
pixi run -e nb lab            # JupyterLab (ambiente com lonboard para mapas grandes)
```

Outra norma de projeto: `pixi run trembr estudo sp-rj --norma ic200`.

## Estrutura

```
config/normas/      parâmetros geométricos (rampa, raios, plataforma) com fonte
config/custos/      custos unitários e limites geotécnicos (hoje: placeholder)
data/catalogo.yaml  as 23 fontes de dados: licença, uso, status
data/raw|interim|processed   (fora do git)
docs/               metodologia, roteiro
src/trembr/         pacote: fontes, terreno, tracado, demanda, rede, operacao, avaliacao, estudos
tests/              testes (inclui otimalidade contra força bruta)
resultados/         saídas dos estudos (fora do git)
```

## Dados e disco

Os DEMs são lidos por **streaming**: só a janela necessária é baixada. Para o estudo nacional em
30 m, aponte os dados para um disco externo:

```powershell
$env:TREMBR_DADOS = "E:\trem-brasil-dados"
```

Cada arquivo baixado ganha um `.proveniencia.json` (URL, data, licença, SHA-256).

## Status

M0 (base) concluído. Os custos em R$ são **placeholder** até a calibração do M2: não citar.
