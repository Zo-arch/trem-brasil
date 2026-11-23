"""Atlas, camada 2 — relevo: altitude em cores hipsométricas com sombreamento.

Fonte: mosaico do Copernicus GLO-90 da região (``trembr dados relevo``). É um modelo de
superfície (inclui copa de árvores); para o traçado, o ANADEM entra na Fase 2 · v4.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from matplotlib.colors import LightSource, LinearSegmentedColormap, Normalize, to_rgb
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, calculate_default_transform, reproject

from trembr.atlas import estilo
from trembr.atlas.web import CamadaWeb, ladrilhos
from trembr.fontes import copernicus
from trembr.paths import INTERMEDIARIOS, garantir
from trembr.regiao import Regiao
from trembr.terreno.dem import Raster
from trembr.visual import MAR, SUPERFICIE, TINTA, fmt_int

ID = "relevo"
NOME = "Relevo"
COMANDO = "trembr dados relevo"
FONTES = ["Copernicus DEM GLO-90 (© DLR/Airbus, ESA; modelo de superfície, ~90 m)"]

# Resolução de exibição (não é premissa do estudo): a figura tem ~1.800 px de largura.
RES_FIGURA_M = 800.0
RES_WEB_M = 500.0
EXAGERO_VERTICAL = 8.0  # só para o sombreamento ficar legível nessa escala

# Cores hipsométricas: planícies verde-claro → planaltos em tons de areia → serras em marrom →
# picos quase brancos. Paradas em metros.
_PARADAS = [
    (0, "#e3ecd3"),
    (300, "#cfe0b2"),
    (600, "#e9e2b4"),
    (900, "#dcc391"),
    (1200, "#c9a378"),
    (1600, "#ab8467"),
    (2200, "#998a82"),
    (2900, "#f4f1ec"),
]
Z_MAX = _PARADAS[-1][0]
CMAP = LinearSegmentedColormap.from_list("hipsometria", [(z / Z_MAX, c) for z, c in _PARADAS])


def arquivo_dem(regiao: Regiao) -> Path:
    return copernicus.caminho_bbox(regiao.bbox(), "glo90")


def disponivel(regiao: Regiao) -> bool:
    return arquivo_dem(regiao).exists()


def reamostrado(regiao: Regiao, crs: str, res_m: float, metodo: str = "average") -> Raster:
    """DEM da região reprojetado em ``crs`` com pixel ``res_m`` (cache em data/interim)."""
    nome = f"{regiao.id}_{crs.replace(':', '')}_{res_m:.0f}m_{metodo}.tif"
    cache = garantir(INTERMEDIARIOS / "relevo") / nome
    origem = arquivo_dem(regiao)
    if not cache.exists() or cache.stat().st_mtime < origem.stat().st_mtime:
        destino_crs = CRS.from_user_input(crs)
        with rasterio.open(origem) as src:
            transform, largura, altura = calculate_default_transform(
                src.crs, destino_crs, src.width, src.height, *src.bounds, resolution=res_m
            )
            dados = np.full((altura, largura), np.nan, dtype=np.float32)
            reproject(
                source=rasterio.band(src, 1),
                destination=dados,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=src.nodata,
                dst_transform=transform,
                dst_crs=destino_crs,
                dst_nodata=np.nan,
                resampling=getattr(Resampling, metodo),
            )
        perfil = {
            "driver": "GTiff", "height": altura, "width": largura, "count": 1,
            "dtype": "float32", "crs": destino_crs, "transform": transform, "nodata": np.nan,
            "compress": "deflate", "predictor": 3,
        }  # fmt: skip
        with rasterio.open(cache, "w", **perfil) as dst:
            dst.write(dados, 1)
    with rasterio.open(cache) as src:
        return Raster(src.read(1).astype(np.float64), src.transform, src.crs)


def colorir(z: np.ndarray, res_m: float, *, alfa: bool = False) -> np.ndarray:
    """Altitude → RGB uint8 (cores hipsométricas × sombreamento do noroeste); mar em MAR.

    Com ``alfa=True`` devolve RGBA e deixa transparente o que não tem dado (fora do mosaico).
    """
    sem_dado = ~np.isfinite(z)
    mar = sem_dado | (z <= 0)
    zf = np.where(mar, 0.0, z)
    luz = LightSource(azdeg=315, altdeg=45)
    rgb = luz.shade(
        zf,
        cmap=CMAP,
        norm=Normalize(0, Z_MAX),
        blend_mode="soft",
        vert_exag=EXAGERO_VERTICAL,
        dx=res_m,
        dy=res_m,
    )[..., :3]
    rgb[mar] = to_rgb(MAR)
    if alfa:
        rgb = np.dstack([rgb, (~sem_dado).astype(float)])
    return (np.clip(rgb, 0, 1) * 255).astype(np.uint8)


def ponto_mais_alto(regiao: Regiao) -> tuple[float, float, float]:
    """(altitude, lon, lat) do pixel mais alto do DEM dentro da região (reamostragem 'max')."""
    r = reamostrado(regiao, estilo.CRS_MAPA, RES_FIGURA_M, "max")
    fora = geometry_mask(
        [regiao.contorno(estilo.CRS_MAPA)], out_shape=r.dados.shape, transform=r.transform
    )
    z = np.where(fora, np.nan, r.dados)
    lin, col = np.unravel_index(np.nanargmax(z), z.shape)
    x, y = r.lc_para_xy(np.array([lin]), np.array([col]))[0]
    lon, lat = Transformer.from_crs(estilo.CRS_MAPA, "EPSG:4326", always_xy=True).transform(x, y)
    return float(z[lin, col]), float(lon), float(lat)


def figura(regiao: Regiao, caminho: Path) -> Path:
    r = reamostrado(regiao, estilo.CRS_MAPA, RES_FIGURA_M)
    z_max, lon_max, lat_max = ponto_mais_alto(regiao)
    m = estilo.abrir(
        regiao,
        f"{regiao.nome}: relevo",
        f"Altitude e sombreamento · ponto mais alto no modelo: {estilo.fmt_int(z_max)} m "
        f"({abs(lat_max):.2f}° S, {abs(lon_max):.2f}° O)",
    )
    limites = m.ax.get_xlim(), m.ax.get_ylim()
    m.ax.imshow(
        colorir(r.dados, r.resolucao, alfa=True),
        extent=r.extensao,
        zorder=2,
        interpolation="bilinear",
    )
    m.ax.set_xlim(*limites[0])
    m.ax.set_ylim(*limites[1])

    # fora da região, o relevo fica esmaecido para dar foco
    dentro = m.ufs["uf"].isin(regiao.ufs)
    m.ufs[~dentro].plot(ax=m.ax, color=SUPERFICIE, alpha=0.5, linewidth=0, zorder=3)

    x, y = Transformer.from_crs("EPSG:4326", estilo.CRS_MAPA, always_xy=True).transform(
        lon_max, lat_max
    )
    m.ax.plot(x, y, marker="^", color=TINTA, markersize=8, zorder=7)
    m.ax.annotate(
        f"{estilo.fmt_int(z_max)} m", (x, y), xytext=(8, 6), textcoords="offset points",
        fontsize=9, color=TINTA, path_effects=estilo.HALO, zorder=7,
    )  # fmt: skip

    barra = m.ax.inset_axes((0.66, 0.07, 0.3, 0.022))
    barra.imshow(np.linspace(0, 1, 256)[None, :], cmap=CMAP, aspect="auto", extent=(0, Z_MAX, 0, 1))
    barra.set_yticks([])
    barra.set_xticks([0, 500, 1000, 1500, 2000, 2500])
    barra.set_xticklabels(["0", "500", "1.000", "1.500", "2.000", "2.500"], fontsize=8)
    barra.set_title("altitude (m)", fontsize=9, color=TINTA, loc="left")
    for lado in barra.spines.values():
        lado.set_visible(False)
    return estilo.fechar(m, FONTES, caminho)


def web(regiao: Regiao) -> list[CamadaWeb]:
    r = reamostrado(regiao, "EPSG:3857", RES_WEB_M)
    return [
        CamadaWeb(
            id="relevo",
            nome="Relevo (altitude e sombra)",
            grupo=NOME,
            tipo="raster",
            pintura={"raster-opacity": 0.9, "raster-fade-duration": 0},
            cor="#c9a378",
            gradiente=[c for _, c in _PARADAS],
            gradiente_rotulos=["0 m", f"{fmt_int(Z_MAX)} m"],
            imagens=ladrilhos(colorir(r.dados, r.resolucao), r.transform, "JPEG"),
            ordem=10,
        )
    ]
