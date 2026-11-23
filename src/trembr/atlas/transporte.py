"""Atlas, camada 4 — transporte existente: rodovias, ferrovias e aeroportos (OpenStreetMap).

Rodovias em cinzas ordenados pela classe; ferrovias num matiz próprio (em operação sólida,
desativada tracejada); aeroportos com código IATA (os que têm voo comercial regular ou já
tiveram).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from pyproj import Geod

from trembr.atlas import estilo
from trembr.atlas.web import CamadaWeb, para_geojson
from trembr.paths import PROCESSADOS
from trembr.regiao import Regiao
from trembr.visual import TINTA

ID = "transporte"
NOME = "Transporte existente"
COMANDO = "trembr dados transporte"
FONTES = ["© colaboradores do OpenStreetMap (ODbL), extrato do Geofabrik"]

# classe → (rótulo, cor, espessura na figura em pt, espessura no mapa web em px)
ESTILO_RODOVIA = {
    "autoestrada": ("Autoestrada", "#3d3b37", 1.2, 2.4),
    "troncal": ("Rodovia troncal", "#5c5a54", 0.9, 1.8),
    "principal": ("Rodovia principal", "#8f8c84", 0.55, 1.1),
    "secundaria": ("Rodovia secundária", "#bdbab2", 0.35, 0.7),
}
COR_FERROVIA = "#6250d6"
COR_FERROVIA_DESATIVADA = "#a59de6"
COR_AEROPORTO = TINTA
_GEOD = Geod(ellps="GRS80")  # SIRGAS 2000 usa o GRS80


def _arq(regiao: Regiao, tipo: str) -> Path:
    return PROCESSADOS / "osm" / f"{regiao.id}_{tipo}.parquet"


def disponivel(regiao: Regiao) -> bool:
    return all(_arq(regiao, t).exists() for t in ("rodovias", "ferrovias", "aeroportos"))


def _ler(regiao: Regiao, tipo: str) -> gpd.GeoDataFrame:
    return gpd.read_parquet(_arq(regiao, tipo))


def ferrovias_principais(regiao: Regiao) -> gpd.GeoDataFrame:
    """Linhas-tronco: sem pátios, desvios e ramais de serviço (tag ``service``) nem metrô/VLT."""
    f = _ler(regiao, "ferrovias")
    sem_servico = f["service"].isna() if "service" in f else True
    return f[sem_servico & f["situacao"].isin(["em_operacao", "desativada", "em_obras"])]


def aeroportos_iata(regiao: Regiao) -> gpd.GeoDataFrame:
    a = _ler(regiao, "aeroportos")
    a = a[a["iata"].notna()] if "iata" in a else a.iloc[0:0]
    return a.drop_duplicates("iata")


def km_geodesico(gdf: gpd.GeoDataFrame) -> float:
    """Comprimento total no elipsoide (km): sem distorção de projeção."""
    return sum(_GEOD.geometry_length(g) for g in gdf.geometry) / 1000


def figura(regiao: Regiao, caminho: Path) -> Path:
    rod = _ler(regiao, "rodovias")
    fer = ferrovias_principais(regiao)
    aero = aeroportos_iata(regiao)
    em_op = fer[fer["situacao"] == "em_operacao"]
    desat = fer[fer["situacao"] == "desativada"]
    # Sem totais em km: no OSM cada pista de uma via dupla (rodovia ou ferrovia) é uma linha
    # própria, e a soma contaria o trecho duas vezes.
    m = estilo.abrir(
        regiao,
        f"{regiao.nome}: transporte existente",
        "Rodovias por classe, ferrovias em operação e desativadas, "
        f"{len(aero)} aeroportos com código IATA",
    )
    for classe in reversed(ESTILO_RODOVIA):  # secundárias por baixo, autoestradas por cima
        _, cor, lw, _ = ESTILO_RODOVIA[classe]
        rod[rod["classe"] == classe].to_crs(estilo.CRS_MAPA).plot(
            ax=m.ax, color=cor, linewidth=lw, zorder=3
        )
    desat.to_crs(estilo.CRS_MAPA).plot(
        ax=m.ax, color=COR_FERROVIA_DESATIVADA, linewidth=0.9, linestyle=(0, (2, 1.5)), zorder=4
    )
    em_op.to_crs(estilo.CRS_MAPA).plot(ax=m.ax, color=COR_FERROVIA, linewidth=1.1, zorder=5)
    a = aero.to_crs(estilo.CRS_MAPA)
    m.ax.scatter(
        a.geometry.x, a.geometry.y, marker="s", s=22, color=COR_AEROPORTO,
        edgecolors="white", linewidths=0.8, zorder=6,
    )  # fmt: skip

    legenda = [
        Line2D([], [], color=cor, linewidth=lw * 2, label=rotulo)
        for rotulo, cor, lw, _ in ESTILO_RODOVIA.values()
    ] + [
        Line2D([], [], color=COR_FERROVIA, linewidth=2.2, label="Ferrovia em operação"),
        Line2D([], [], color=COR_FERROVIA_DESATIVADA, linewidth=1.8, linestyle=(0, (2, 1.5)),
               label="Ferrovia desativada"),
        Line2D([], [], marker="s", linestyle="", markersize=6, markerfacecolor=COR_AEROPORTO,
               markeredgecolor="white", label="Aeroporto (código IATA)"),
    ]  # fmt: skip
    leg = m.ax.legend(
        handles=legenda, loc="lower right", ncols=2, fontsize=8.5, frameon=True,
        facecolor="white", edgecolor="none", framealpha=0.9, borderpad=0.8,
        labelspacing=0.9, handlelength=2.6,
    )  # fmt: skip
    leg.set_zorder(9)
    return estilo.fechar(m, FONTES, caminho)


def _rodovias_web(regiao: Regiao) -> gpd.GeoDataFrame:
    """Rodovias sem as alças de acesso (``*_link``), agrupadas por (classe, ref) e emendadas:
    bem menos feições no HTML."""
    rod = _ler(regiao, "rodovias")
    rod = rod[~rod["highway"].str.endswith("_link")]
    for c in ("ref", "name"):
        if c not in rod:
            rod[c] = None
    rod["ref"] = rod["ref"].fillna("")
    rod["name"] = rod["name"].fillna("")
    sem_ref = rod["ref"] == ""
    rod.loc[sem_ref, "ref"] = rod.loc[sem_ref, "name"]  # sem número: agrupa pelo nome
    agr = rod.dissolve(by=["classe", "ref"], as_index=False, aggfunc={"name": "first"})
    agr["geometry"] = agr.geometry.line_merge()
    agr["rotulo"] = np.where(agr["ref"] != "", agr["ref"], agr["name"])
    agr["rotulo"] = agr["rotulo"].replace("", "—")
    agr["classe_nome"] = agr["classe"].map({k: v[0] for k, v in ESTILO_RODOVIA.items()})
    return agr


def web(regiao: Regiao) -> list[CamadaWeb]:
    rod = _rodovias_web(regiao)
    fer = ferrovias_principais(regiao).copy()
    for c in ("name", "operator", "usage", "gauge"):
        if c not in fer:
            fer[c] = None
    # trechos agrupados por (situação, nome) e emendados: menos feições no HTML
    fer["name"] = fer["name"].fillna("Ferrovia sem nome no OSM")
    fer = fer.dissolve(
        by=["situacao", "name"],
        as_index=False,
        aggfunc={"operator": "first", "usage": "first", "gauge": "first"},
    )
    fer["geometry"] = fer.geometry.line_merge()
    fer["situacao_nome"] = fer["situacao"].map(
        {"em_operacao": "em operação", "desativada": "desativada", "em_obras": "em obras"}
    )
    aero = aeroportos_iata(regiao)
    for c in ("name", "icao"):
        if c not in aero:
            aero[c] = None

    largura = ["match", ["get", "classe"]]
    cor = ["match", ["get", "classe"]]
    for classe, (_, c, _, lw_web) in ESTILO_RODOVIA.items():
        largura += [classe, lw_web]
        cor += [classe, c]
    largura.append(1)
    cor.append("#999999")
    # Secundárias ficam só na figura (somariam ~7 MB ao HTML); o fundo de ruas mostra todas.
    principais = rod[rod["classe"].isin(["autoestrada", "troncal", "principal"])]
    return [
        CamadaWeb(
            id="rodovias",
            nome="Rodovias (autoestradas, troncais, principais)",
            grupo=NOME,
            tipo="line",
            pintura={"line-color": cor, "line-width": largura},
            cor=ESTILO_RODOVIA["autoestrada"][1],
            legenda=[
                [ESTILO_RODOVIA[c][1], ESTILO_RODOVIA[c][0]]
                for c in ("autoestrada", "troncal", "principal")
            ],
            geojson=para_geojson(
                principais, ["classe", "classe_nome", "rotulo"], tolerancia_m=200, casas=4
            ),
            popup={"classe_nome": "Classe"},
            titulo_popup="rotulo",
            ordem=40,
        ),
        *(
            CamadaWeb(
                id=f"ferrovias_{situacao}",
                nome=nome,
                grupo=NOME,
                tipo="line",
                # tracejado não pode depender de atributo no MapLibre 4: uma camada por situação
                pintura={"line-color": cor_linha, "line-width": 2}
                | ({"line-dasharray": [2, 1.5]} if situacao != "em_operacao" else {}),
                cor=cor_linha,
                geojson=para_geojson(
                    fer[fer["situacao"].isin(situacoes)],
                    ["name", "situacao_nome", "operator", "usage", "gauge"],
                    tolerancia_m=100,
                    casas=4,
                ),
                popup={"situacao_nome": "Situação", "operator": "Operador", "gauge": "Bitola (mm)"},
                titulo_popup="name",
                ordem=45,
                visivel=situacao == "em_operacao",  # desativadas começam desligadas
            )
            for situacao, situacoes, nome, cor_linha in (
                ("em_operacao", ["em_operacao"], "Ferrovias em operação", COR_FERROVIA),
                (
                    "desativada",
                    ["desativada", "em_obras"],
                    "Ferrovias desativadas ou em obras",
                    COR_FERROVIA_DESATIVADA,
                ),
            )
        ),
        CamadaWeb(
            id="aeroportos",
            nome="Aeroportos (código IATA)",
            grupo=NOME,
            tipo="circle",
            pintura={
                "circle-radius": 5,
                "circle-color": COR_AEROPORTO,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 1.5,
            },
            cor=COR_AEROPORTO,
            geojson=para_geojson(aero, ["name", "iata", "icao"]),
            popup={"iata": "IATA", "icao": "ICAO"},
            titulo_popup="name",
            ordem=65,
        ),
    ]


def resumo(regiao: Regiao) -> pd.DataFrame:
    """km por classe de rodovia e situação de ferrovia (para conferência)."""
    rod = _ler(regiao, "rodovias")
    fer = ferrovias_principais(regiao)
    linhas = [("rodovia", c, km_geodesico(rod[rod["classe"] == c])) for c in ESTILO_RODOVIA]
    linhas += [
        ("ferrovia", s, km_geodesico(fer[fer["situacao"] == s]))
        for s in ("em_operacao", "desativada", "em_obras")
    ]
    return pd.DataFrame(linhas, columns=["tipo", "classe", "km"])
