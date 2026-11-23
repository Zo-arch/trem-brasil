"""Atlas — resultados dos estudos de caso, só no mapa interativo (as figuras ficam nos estudos).

Hoje: as rotas em destaque do Rio–SP v2 (``pixi run estudo-rio-sp-v2``), nas mesmas cores das
figuras do estudo, com popup de paradas, extensão, gente atendida e custo relativo.
"""

from __future__ import annotations

import json

import geopandas as gpd

from trembr.atlas.web import CamadaWeb, para_geojson
from trembr.estudos.figuras import CORES, ROTULOS
from trembr.paths import RESULTADOS
from trembr.regiao import Regiao
from trembr.visual import fmt_dec, fmt_int

ID = "estudos"
NOME = "Estudos de caso"
COMANDO = "estudo-rio-sp-v2"
PASTA_V2 = RESULTADOS / "rio_sp" / "v2"
VISIVEIS = {"no_caminho", "joelho"}  # o "máximo de gente" é um extremo: começa desligado


def disponivel(regiao: Regiao) -> bool:
    return (PASTA_V2 / "rotas.parquet").exists() and (PASTA_V2 / "resumo.json").exists()


def web(regiao: Regiao) -> list[CamadaWeb]:
    rotas = gpd.read_parquet(PASTA_V2 / "rotas.parquet")
    destaques = json.loads((PASTA_V2 / "resumo.json").read_text(encoding="utf-8"))["destaques"]
    camadas = []
    for nome in ("direta", "no_caminho", "joelho", "maxima"):
        r = destaques[nome]
        linha = rotas[rotas["rota"] == nome].copy()
        linha["titulo"] = ROTULOS[nome]
        linha["paradas"] = ", ".join(p.rsplit("/", 1)[0] for p in r["paradas"]) or "nenhuma"
        linha["extensao"] = f"{fmt_int(r['extensao_km'])} km"
        linha["gente"] = f"{fmt_dec(r['populacao_atendida'] / 1e6)} milhões"
        linha["tunel"] = f"{fmt_dec(r['pct_por_estrutura']['túnel'])}%"
        linha["custo"] = f"{fmt_int(r['custo_corredor_km_eq'])} km-eq"
        tracejada = nome == "direta"
        camadas.append(
            CamadaWeb(
                id=f"rio_sp_v2_{nome}",
                nome=f"{ROTULOS[nome]} · {r['n_paradas']} paradas · {fmt_int(r['extensao_km'])} km",
                grupo="Estudo Rio–SP v2 (paradas escolhidas pelo otimizador)",
                tipo="line",
                pintura={"line-color": CORES[nome], "line-width": 2 if tracejada else 4}
                | ({"line-dasharray": [3, 2]} if tracejada else {}),
                cor=CORES[nome],
                geojson=para_geojson(
                    linha,
                    ["titulo", "paradas", "extensao", "gente", "tunel", "custo"],
                    tolerancia_m=30,
                ),
                popup={
                    "paradas": "Paradas",
                    "extensao": "Extensão",
                    "gente": "Gente atendida",
                    "tunel": "Em túnel",
                    "custo": "Custo relativo",
                },
                titulo_popup="titulo",
                visivel=nome in VISIVEIS,
                ordem=70 + ("maxima", "joelho", "no_caminho", "direta").index(nome),
            )
        )
    return camadas
