# Arquitetura

Como o código está organizado, por onde os dados passam e como acrescentar coisas sem bagunçar.
O *porquê* científico de cada método está em [metodologia.md](metodologia.md); o *quando*, em
[roteiro.md](roteiro.md).

## O fluxo

```
 config/*.yaml ─────────── premissas numéricas, cada uma com fonte ─────────────┐
                                                                                 │
 fontes abertas ─▶ fontes/ ─▶ data/raw ─▶ data/interim ─▶ data/processed         │
 (IBGE, OSM,        baixar e   como veio,  caches e       GeoParquet e GeoTIFF   │
  Copernicus...)    preparar   + proveniência  recortes   prontos para uso        │
                                                    │                            │
                     ┌──────────────────────────────┴───────────────┐            │
                     ▼                                              ▼            ▼
                 atlas/  (Fase 1)                            estudos/  (Fase 2 em diante)
                 uma figura por camada +                     encadeiam terreno/ e tracado/
                 mapa interativo                             (algoritmos testados)
                     │                                              │
                     ▼                                              ▼
           resultados/atlas/<região>/                 resultados/<estudo>/v<N>/
           01_base.png … index.html                   rotas.parquet, perfis.parquet,
                                                      resumo.json, figuras .png
```

`data/` e `resultados/` ficam fora do git: tudo se refaz com `pixi run dados`, os estudos e
`pixi run atlas`. O que vai para o git é código, configuração, documentação e as figuras
escolhidas para o README (`docs/img/`).

## Pacotes (`src/trembr/`)

| Pacote / módulo | Responsabilidade | Regra |
|---|---|---|
| `fontes/` | Baixar e preparar cada fonte de dados (um módulo por fonte) | Todo download passa por `fontes/baixar.py`, que grava a proveniência |
| `terreno/` | Modelo de elevação (`Raster`) e superfície de custo do corredor | Sem download; lê o que `fontes/` preparou |
| `tracado/` | Algoritmos: corredor (A\*, Dijkstra), greide (programação dinâmica), seção, geometria, paradas (Pareto) | Sem I/O; recebe arrays e configs; **cada otimizador é testado contra uma referência independente** |
| `estudos/` | Estudos de caso: encadeiam terreno → traçado, salvam resultados e figuras | Uma função `rodar_vN` por versão; parâmetros em `config/estudos/` |
| `atlas/` | Figuras e mapa interativo das camadas de dados (e das rotas dos estudos) | Uma camada = um módulo; registro em `atlas/montar.py` |
| `demanda/`, `rede/`, `operacao/`, `avaliacao/` | Fases 3 e 4 (só o método, na docstring) | — |
| `config.py` | Modelos validados (pydantic) das configurações | — |
| `regiao.py` | Regiões de estudo: UFs, contorno, recorte com margem em metros | — |
| `crs.py`, `paths.py`, `proveniencia.py` | Sistemas de referência, caminhos, registro de proveniência | — |
| `visual.py` | Identidade visual: paleta de "tinta e papel", formatação de números (pt-BR) | Cores de dados ficam com cada figura, validadas |
| `cli.py` | Linha de comando (`pixi run trembr --help`) | Só orquestra; nenhuma lógica de cálculo |

As dependências andam num sentido só: `fontes/` não conhece estudos, `tracado/` não conhece
fontes, e `estudos/` e `atlas/` usam o resto. Nada importa `cli.py`.

## Configuração (`config/`)

| Arquivo | O que define |
|---|---|
| `normas/as350.yaml`, `normas/ic200.yaml` | Geometria de projeto: rampas, raios, plataforma |
| `custos/referencia.yaml` | Custos unitários e limites geotécnicos (**placeholder**: nunca citar R$) |
| `corredor/referencia.yaml` | Superfície de custo e suavização (**não calibrado**) |
| `regioes.yaml` | Regiões de estudo: UFs, margem, extratos do OpenStreetMap |
| `estudos/rio_sp.yaml` | Pontas, recorte, candidatas e tolerâncias do estudo Rio–SP, por versão |

## Comandos

| `pixi run …` | O que faz |
|---|---|
| `dados` | Baixa e prepara todas as camadas da região (o que já existe fica em cache) |
| `atlas` | Gera as figuras e o mapa interativo (2 a 3 min) |
| `mapa` | Abre o mapa interativo (gera antes se não existir) |
| `estudo-rio-sp-v1`, `estudo-rio-sp-v2` | Roda uma versão do estudo Rio–SP |
| `test`, `lint`, `fmt` | Qualidade: rodar antes de dar trabalho por concluído |
| `trembr dados <camada>` | Uma camada só: `base`, `relevo`, `cidades`, `transporte`, `protegidas` |

## Como acrescentar

**Uma fonte de dados.**
1. Entrada em `data/catalogo.yaml`. Só marque `confirmado: true` depois de testar a URL.
2. Módulo em `fontes/` com uma função `preparar_*()` que use `fontes.baixar.baixar`.
3. Comando `trembr dados <nome>` em `cli.py`, também incluído em `dados tudo`.
4. Teste do leitor sem rede (arquivo sintético em `tmp_path`).

**Uma camada do atlas.** Módulo em `atlas/` com:
- obrigatórios: `ID`, `NOME`, `COMANDO`, `disponivel(regiao)` e `web(regiao)`;
- opcionais: `figura(regiao, caminho)` e `busca(regiao)`.

Depois, registre-o em `atlas/montar.CAMADAS`. Cores de dados passam pelo validador de paleta.

**Uma versão de estudo.**
1. Função `rodar_vN` em `estudos/rio_sp.py`, registrada em `VERSOES`.
2. Seção `vN:` em `config/estudos/rio_sp.yaml`.
3. Tarefa `estudo-rio-sp-vN` no `pyproject.toml`.
4. Resultados em `resultados/rio_sp/vN/`, com `rotas.parquet` e `resumo.json`, para o atlas
   poder mostrá-los.

**Um algoritmo.** Em `tracado/` (ou `terreno/`), sem I/O, com teste contra referência
independente: força bruta, outra biblioteca ou solução analítica.
