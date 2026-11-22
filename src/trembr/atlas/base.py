"""Atlas, camada 1 — mapa base: UFs e municípios, com a população do Censo 2022."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from trembr.atlas import estilo
from trembr.atlas.web import CamadaWeb, para_geojson
from trembr.paths import PROCESSADOS
from trembr.regiao import Regiao, ufs_brasil

ID = "base"
NOME = "Mapa base"
COMANDO = "trembr dados base"
FONTES = ["IBGE, malhas territoriais (API v3, qualidade intermediária)", "IBGE, Censo 2022"]
ARQ_MUNICIPIOS = PROCESSADOS / "ibge" / "municipios_2022.parquet"
COR_MUNICIPIO = "#d4d2c9"


def disponivel(regiao: Regiao) -> bool:
    return ARQ_MUNICIPIOS.exists() and (PROCESSADOS / "ibge" / "ufs.parquet").exists()


def municipios(regiao: Regiao) -> gpd.GeoDataFrame:
    mun = gpd.read_parquet(ARQ_MUNICIPIOS)
    return mun[mun["uf"].isin(regiao.ufs)].reset_index(drop=True)


def figura(regiao: Regiao, caminho: Path) -> Path:
    mun = municipios(regiao)
    pop = int(mun["populacao_2022"].sum())
    m = estilo.abrir(
        regiao,
        f"{regiao.nome}: mapa base",
        f"{len(regiao.ufs)} estados · {estilo.fmt_int(len(mun))} municípios · "
        f"{estilo.fmt_dec(pop / 1e6)} milhões de habitantes (Censo 2022)",
    )
    mun.to_crs(estilo.CRS_MAPA).boundary.plot(ax=m.ax, color=COR_MUNICIPIO, linewidth=0.3, zorder=2)
    return estilo.fechar(m, FONTES, caminho)


def web(regiao: Regiao) -> list[CamadaWeb]:
    ufs = ufs_brasil().copy()
    ufs["na_regiao"] = ufs["uf"].isin(regiao.ufs)
    mun = municipios(regiao)
    gj_ufs = para_geojson(ufs, ["uf", "nome", "na_regiao"], tolerancia_m=500)
    return [
        CamadaWeb(
            id="terra",
            nome="Terra",
            grupo=NOME,
            tipo="fill",
            pintura={"fill-color": ["case", ["get", "na_regiao"], estilo.TERRA, estilo.TERRA_FORA]},
            cor=estilo.TERRA_FORA,
            geojson=gj_ufs,
            ordem=0,
            no_painel=False,
        ),
        CamadaWeb(
            id="municipios",
            nome="Municípios (clique: população)",
            grupo=NOME,
            tipo="fill",
            pintura={"fill-color": "#ffffff", "fill-opacity": 0.01},
            contorno={"line-color": COR_MUNICIPIO, "line-width": 0.6},
            cor=COR_MUNICIPIO,
            geojson=para_geojson(
                mun, ["nome", "uf", "cod_ibge", "populacao_2022"], tolerancia_m=150
            ),
            popup={"uf": "UF", "populacao_2022": "População (2022)", "cod_ibge": "Código IBGE"},
            titulo_popup="nome",
            ordem=30,
        ),
        CamadaWeb(
            id="divisas",
            nome="Divisas estaduais",
            grupo=NOME,
            tipo="line",
            pintura={"line-color": estilo.DIVISA, "line-width": 1.4},
            cor=estilo.DIVISA,
            geojson=gj_ufs,
            ordem=50,
        ),
    ]
