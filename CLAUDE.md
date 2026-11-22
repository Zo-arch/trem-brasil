# CLAUDE.md — trem-brasil

Estudo científico de malha ferroviária de alta velocidade para o Brasil. Código, docs e
identificadores de domínio em português.

## Comandos
- `pixi run test` / `pixi run lint` / `pixi run fmt` — rodar antes de dar trabalho por concluído.
- `pixi run trembr --help` — CLI (typer). Estudos em `src/trembr/estudos/`.
- No PowerShell, usar `$env:PYTHONIOENCODING="utf-8"` para a saída do rich com acentos.

## Regras do projeto
- Toda premissa numérica vai em `config/*.yaml` com fonte; nada de número mágico no código.
- Nova fonte de dados = entrada em `data/catalogo.yaml` + módulo em `src/trembr/fontes/` +
  `proveniencia.registrar(...)`. Só marcar `confirmado: true` depois de testar a URL de verdade.
- Otimizador novo precisa de teste contra referência independente (força bruta, outra biblioteca).
- `config/custos/referencia.yaml` é PLACEHOLDER: nunca apresentar custo em R$ como resultado.
- Cálculos métricos em SIRGAS 2000 / UTM (`crs.epsg_utm_sirgas`); nunca medir distância em graus.
- Disco: ~100 GB livres no C: (nov/2026). Ler DEM por streaming (COG); não baixar tiles nacionais em 30 m.
  `TREMBR_DADOS` permite mover os dados para um SSD externo.
- Copernicus é DSM (inclui árvores); ANADEM é o DTM-alvo do traçado.

## Mapa do código
- `tracado/secao.py` — custo por metro de aterro/corte/viaduto/túnel (numba).
- `tracado/perfil.py` — greide ótimo por programação dinâmica, estado (cota, rampa).
- `tracado/corredor.py` — A* 16 direções em numba.
- `terreno/superficie_custo.py` — proxy de custo para o corredor (não calibrado).
- Camadas `demanda/`, `rede/`, `operacao/`, `avaliacao/` têm só o método planejado na docstring.

## Roteiro (docs/roteiro.md)
Fase 1 dados (atlas do Brasil) → Fase 2 linha Rio–SP evoluindo por versões (v1 só relevo ✅,
v2 cidades escolhidas pelo otimizador, v3 obstáculos, v4 ANADEM, v5 geometria 350 km/h,
v6 custos calibrados, v7 tempo de viagem) → Fase 3 malha nacional → Fase 4 avaliação e publicação.
