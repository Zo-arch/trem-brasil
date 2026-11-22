"""Atlas, camada 3 — cidades: mancha urbana (IBGE 2022) e cidades do REGIC 2018.

"Cidade" aqui é a unidade do REGIC: um arranjo populacional (ex.: São Paulo/SP, 37 municípios)
ou um município isolado. É a unidade candidata a estação na Fase 2 · v2. Área do círculo
proporcional à população; cor pela hierarquia urbana (rampa ordinal de um matiz, validada
com o validador da skill de visualização: monótona, passos visíveis, ponta clara >= 2:1).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import box

from trembr.atlas import estilo
from trembr.atlas.web import CamadaWeb, ladrilhos, para_geojson
from trembr.crs import SIRGAS2000
from trembr.graficos import TINTA, TINTA_2
from trembr.paths import PROCESSADOS
from trembr.regiao import Regiao

ID = "cidades"
NOME = "Cidades"
COMANDO = "trembr dados cidades"
FONTES = [
    "IBGE, REGIC 2018 (hierarquia urbana)",
    "IBGE, Localidades 2022 (sedes)",
    "IBGE, Áreas Urbanizadas 2022",
    "IBGE, PIB dos Municípios",
]
ARQ_REGIC = PROCESSADOS / "ibge" / "cidades_regic.parquet"
ARQ_AU = PROCESSADOS / "ibge" / "areas_urbanizadas_2022.parquet"

# 1 = Metrópole (mais escura) … 5 = Centro Local (mais clara)
GRUPOS = {
    1: ("Metrópole", "#6c290b"),
    2: ("Capital regional", "#9e3d13"),
    3: ("Centro sub-regional", "#c9521c"),
    4: ("Centro de zona", "#e2733c"),
    5: ("Centro local", "#ee9566"),
}
COR_URBANA = {"Densa": "#6f6c66", "Pouco densa": "#a3a099"}
TIPOS_URBANOS = ["Área urbanizada", "Outros equipamentos urbanos"]
RES_WEB_URBANA_M = 100.0
# círculo da figura: área (pt²) por habitante; São Paulo (20,7 mi) ≈ 34 pt de diâmetro
PT2_POR_HAB = 900 / 20e6
POP_ROTULO = 650_000  # rotula metrópoles e capitais regionais acima disso


def disponivel(regiao: Regiao) -> bool:
    return ARQ_REGIC.exists() and ARQ_AU.exists()


def cidades(regiao: Regiao) -> gpd.GeoDataFrame:
    c = gpd.read_parquet(ARQ_REGIC)
    return c[c["uf"].isin(regiao.ufs)].reset_index(drop=True)


def mancha_urbana(regiao: Regiao) -> gpd.GeoDataFrame:
    oeste, sul, leste, norte = regiao.bbox()
    au = gpd.read_parquet(ARQ_AU).cx[oeste:leste, sul:norte]
    return au[au["tipo"].isin(TIPOS_URBANOS)]


def figura(regiao: Regiao, caminho: Path) -> Path:
    cid = cidades(regiao)
    pop = cid["populacao_2022"].sum()
    metro = cid[cid["regic_grupo_ord"] == 1]
    m = estilo.abrir(
        regiao,
        f"{regiao.nome}: cidades",
        f"{estilo.fmt_int(len(cid))} cidades (arranjos populacionais e municípios isolados) · "
        f"as {len(metro)} metrópoles concentram "
        f"{estilo.fmt_dec(100 * metro['populacao_2022'].sum() / pop, 0)}% da população",
    )
    au = mancha_urbana(regiao).to_crs(estilo.CRS_MAPA)
    for dens, cor in COR_URBANA.items():
        au[au["densidade"] == dens].plot(ax=m.ax, color=cor, linewidth=0, zorder=2)

    c = cid.to_crs(estilo.CRS_MAPA).sort_values("populacao_2022", ascending=False)
    m.ax.scatter(
        c.geometry.x,
        c.geometry.y,
        s=np.maximum(c["populacao_2022"] * PT2_POR_HAB, 1.5),
        c=[GRUPOS[g][1] for g in c["regic_grupo_ord"]],
        edgecolors=to_rgba("#ffffff", 0.9),
        linewidths=0.6,
        zorder=4,
    )
    rotular = c[(c["regic_grupo_ord"] <= 2) & (c["populacao_2022"] >= POP_ROTULO)]
    for _, r in rotular.iterrows():
        raio_pt = np.sqrt(r["populacao_2022"] * PT2_POR_HAB) / 2
        m.ax.annotate(
            r["nome"].rsplit("/", 1)[0], (r.geometry.x, r.geometry.y),
            xytext=(raio_pt + 3, 0), textcoords="offset points", va="center",
            fontsize=8.5, color=TINTA, path_effects=estilo.HALO, zorder=7,
        )  # fmt: skip

    hier = [
        Line2D([], [], marker="o", linestyle="", markersize=8, markerfacecolor=cor,
               markeredgecolor="white", label=nome)
        for nome, cor in GRUPOS.values()
    ]  # fmt: skip
    tam = [
        Line2D([], [], marker="o", linestyle="", markerfacecolor="none", markeredgecolor=TINTA_2,
               markersize=np.sqrt(p * PT2_POR_HAB), label=f"{rot} hab.")
        for p, rot in ((1e5, "100 mil"), (1e6, "1 milhão"), (1e7, "10 milhões"))
    ]  # fmt: skip
    urb = [
        Line2D([], [], marker="s", linestyle="", markersize=8, markerfacecolor=cor,
               markeredgecolor="none", label=f"área urbanizada {d.lower()}")
        for d, cor in COR_URBANA.items()
    ]  # fmt: skip
    leg = m.ax.legend(
        handles=hier + tam + urb,
        loc="lower right",
        ncols=2,
        fontsize=8.5,
        frameon=True,
        facecolor="white",
        edgecolor="none",
        framealpha=0.9,
        title="Hierarquia urbana (REGIC 2018) · população (2022)",
        title_fontsize=9,
        borderpad=0.8,
        labelspacing=1.0,
    )
    leg.set_zorder(9)
    return estilo.fechar(m, FONTES, caminho)


def _mancha_web(regiao: Regiao) -> list[dict]:
    """Mancha urbana rasterizada a 100 m em EPSG:3857 (vetorial passaria de 6 MB)."""
    oeste, sul, leste, norte = regiao.bbox()
    x0, y0, x1, y1 = (
        gpd.GeoSeries([box(oeste, sul, leste, norte)], crs=SIRGAS2000)
        .to_crs("EPSG:3857")
        .total_bounds
    )
    res = RES_WEB_URBANA_M
    largura, altura = int(np.ceil((x1 - x0) / res)), int(np.ceil((y1 - y0) / res))
    transform = from_origin(x0, y1, res, res)
    au = mancha_urbana(regiao).to_crs("EPSG:3857")
    classe = rasterize(
        [
            *((g, 1) for g in au.loc[au["densidade"] == "Pouco densa", "geometry"]),
            *((g, 2) for g in au.loc[au["densidade"] == "Densa", "geometry"]),
        ],
        out_shape=(altura, largura),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
    )
    rgba = np.zeros((altura, largura, 4), dtype=np.uint8)
    for valor, dens in ((1, "Pouco densa"), (2, "Densa")):
        rgba[classe == valor] = (np.array(to_rgba(COR_URBANA[dens])) * 255).astype(np.uint8)
    return ladrilhos(rgba, transform, "PNG")


def web(regiao: Regiao) -> list[CamadaWeb]:
    cid = cidades(regiao).sort_values("populacao_2022", ascending=False)
    cid["pib_bi_reais"] = (cid["pib_mil_reais"] / 1e6).round(1)
    cid["hierarquia"] = cid["regic_grupo"] + " (" + cid["regic_nivel"] + ")"
    cor_grupo = ["match", ["get", "regic_grupo_ord"]]
    for g, (_, cor) in GRUPOS.items():
        cor_grupo += [g, cor]
    cor_grupo.append("#999999")
    return [
        CamadaWeb(
            id="mancha_urbana",
            nome="Mancha urbana (IBGE 2022)",
            grupo=NOME,
            tipo="raster",
            pintura={
                "raster-opacity": 0.85,
                "raster-fade-duration": 0,
                "raster-resampling": "nearest",
            },
            cor=COR_URBANA["Densa"],
            imagens=_mancha_web(regiao),
            ordem=15,
        ),
        CamadaWeb(
            id="cidades",
            nome="Cidades (área ∝ população; cor = hierarquia)",
            grupo=NOME,
            tipo="circle",
            pintura={
                # raio ∝ √população: área proporcional à população
                "circle-radius": [
                    "interpolate",
                    ["linear"],
                    ["sqrt", ["get", "populacao_2022"]],
                    0,
                    1.5,
                    4550,
                    26,
                ],
                "circle-color": cor_grupo,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 1,
                "circle-opacity": 0.9,
            },
            cor=GRUPOS[2][1],
            geojson=para_geojson(
                cid,
                [
                    "nome",
                    "hierarquia",
                    "regic_grupo_ord",
                    "populacao_2022",
                    "n_municipios",
                    "pib_bi_reais",
                ],
            ),
            popup={
                "hierarquia": "Hierarquia (REGIC 2018)",
                "populacao_2022": "População (2022)",
                "n_municipios": "Municípios",
                "pib_bi_reais": f"PIB (R$ bilhões, {int(cid['pib_ano'].max())})",
            },
            titulo_popup="nome",
            ordem=60,
        ),
    ]
