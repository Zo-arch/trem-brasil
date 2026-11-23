"""Atlas, camada 5 — áreas protegidas: unidades de conservação (CNUC) e terras indígenas (FUNAI).

Verdes em rampa ordinal pela restrição ao traçado (APA < uso sustentável < proteção integral;
validada com o validador da skill de visualização). Terras indígenas num matiz próprio.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import shapely
from matplotlib.patches import Patch
from pyproj import Geod

from trembr.atlas import estilo
from trembr.atlas.web import CamadaWeb, para_geojson
from trembr.crs import SIRGAS2000
from trembr.paths import PROCESSADOS
from trembr.regiao import Regiao

ID = "protegidas"
NOME = "Áreas protegidas"
COMANDO = "trembr dados protegidas"
ARQ_UCS = PROCESSADOS / "mma" / "unidades_conservacao.parquet"
ARQ_TIS = PROCESSADOS / "funai" / "terras_indigenas.parquet"

# classe → (rótulo, cor); ordem de desenho: da mais permissiva para a mais restritiva
CLASSES = {
    "apa": ("Área de Proteção Ambiental", "#80bb77"),
    "uso_sustentavel": ("Uso sustentável (exceto APA)", "#4a9445"),
    "protecao_integral": ("Proteção integral", "#1f6b2c"),
}
COR_TI = "#e87ba4"
_GEOD = Geod(ellps="GRS80")


def disponivel(regiao: Regiao) -> bool:
    return ARQ_UCS.exists()


def _recorte(arq: Path, regiao: Regiao) -> gpd.GeoDataFrame:
    oeste, sul, leste, norte = regiao.bbox()
    return gpd.read_parquet(arq).cx[oeste:leste, sul:norte]


def ucs(regiao: Regiao) -> gpd.GeoDataFrame:
    return _recorte(ARQ_UCS, regiao)


def tis(regiao: Regiao) -> gpd.GeoDataFrame | None:
    return _recorte(ARQ_TIS, regiao) if ARQ_TIS.exists() else None


def _km2(geom) -> float:
    """Área no elipsoide (km²), sem distorção de projeção."""
    return abs(_GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def fracoes(regiao: Regiao) -> dict[str, float]:
    """Fração da área da região coberta por proteção integral e por qualquer UC (sem dupla
    contagem onde as UCs se sobrepõem, como um parque dentro de uma APA)."""
    contorno = regiao.contorno(SIRGAS2000)
    u = ucs(regiao)
    total = _km2(contorno)
    pi = shapely.union_all(
        u.loc[u["classe"] == "protecao_integral", "geometry"].make_valid().values
    )
    todas = shapely.union_all(u.geometry.make_valid().values)
    return {
        "protecao_integral": _km2(pi.intersection(contorno)) / total,
        "qualquer_uc": _km2(todas.intersection(contorno)) / total,
    }


def figura(regiao: Regiao, caminho: Path) -> Path:
    u = ucs(regiao)
    t = tis(regiao)
    f = fracoes(regiao)
    m = estilo.abrir(
        regiao,
        f"{regiao.nome}: áreas protegidas",
        f"{estilo.fmt_int(len(u))} unidades de conservação no recorte · proteção integral cobre "
        f"{estilo.fmt_dec(100 * f['protecao_integral'])}% da região; somando uso sustentável e "
        f"APAs, {estilo.fmt_dec(100 * f['qualquer_uc'])}%",
    )
    for classe, (_, cor) in CLASSES.items():
        u[u["classe"] == classe].to_crs(estilo.CRS_MAPA).plot(
            ax=m.ax, color=cor, alpha=0.85, edgecolor="white", linewidth=0.15, zorder=3
        )
    legenda = [Patch(facecolor=cor, label=rotulo) for rotulo, cor in reversed(CLASSES.values())]
    if t is not None and len(t):
        t.to_crs(estilo.CRS_MAPA).plot(
            ax=m.ax, color=COR_TI, alpha=0.9, edgecolor="white", linewidth=0.2, zorder=4
        )
        legenda.append(Patch(facecolor=COR_TI, label="Terra indígena"))
    fontes = ["MMA, Cadastro Nacional de Unidades de Conservação (CNUC, ago/2025)"]
    if t is not None:
        fontes.append("FUNAI, terras indígenas")
    else:
        legenda.append(
            Patch(facecolor="none", edgecolor="none", label="(terras indígenas: a incluir)")
        )
    leg = m.ax.legend(
        handles=legenda, loc="lower right", fontsize=8.5, frameon=True, facecolor="white",
        edgecolor="none", framealpha=0.9, borderpad=0.8, labelspacing=0.9,
        title="Restrição ao traçado: da mais forte à mais fraca", title_fontsize=9,
    )  # fmt: skip
    leg.set_zorder(9)
    return estilo.fechar(m, fontes, caminho)


def web(regiao: Regiao) -> list[CamadaWeb]:
    u = ucs(regiao).copy()
    u["area_ha"] = u["ha_total"].round()
    camadas = [
        CamadaWeb(
            id=f"ucs_{classe}",
            nome=f"UCs: {rotulo.lower() if classe != 'apa' else 'APAs'}",
            grupo=NOME,
            tipo="fill",
            pintura={"fill-color": cor, "fill-opacity": 0.6},
            contorno={"line-color": cor, "line-width": 0.8},
            cor=cor,
            geojson=para_geojson(
                u[u["classe"] == classe],
                ["nome_uc", "categoria", "esfera", "cria_ano", "area_ha"],
                tolerancia_m=100,
                casas=4,
            ),
            popup={
                "categoria": "Categoria",
                "esfera": "Esfera",
                "cria_ano": "Criação",
                "area_ha": "Área (ha)",
            },
            titulo_popup="nome_uc",
            visivel=classe != "apa",  # APAs são enormes e cobrem o resto; começam desligadas
            ordem=21 + i,
        )
        for i, (classe, (rotulo, cor)) in enumerate(CLASSES.items())
    ]
    t = tis(regiao)
    if t is not None and len(t):
        campos = [c for c in ("nome", "etnia", "fase") if c in t]
        camadas.append(
            CamadaWeb(
                id="tis",
                nome="Terras indígenas",
                grupo=NOME,
                tipo="fill",
                pintura={"fill-color": COR_TI, "fill-opacity": 0.6},
                contorno={"line-color": COR_TI, "line-width": 0.8},
                cor=COR_TI,
                geojson=para_geojson(t, campos, tolerancia_m=100, casas=4),
                popup={c: c.capitalize() for c in campos if c != "nome"},
                titulo_popup="nome" if "nome" in campos else None,
                ordem=25,
            )
        )
    return camadas
