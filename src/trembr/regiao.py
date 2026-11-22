"""Regiões de estudo (``config/regioes.yaml``): UFs, contorno e recorte com margem.

A margem e a distância das ilhas são medidas em metros na Policônica (EPSG:5880), nunca em graus.
O contorno vem da malha de UFs do IBGE (``trembr dados base``).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import geopandas as gpd
import yaml
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from trembr.crs import BRASIL_POLICONICA, SIRGAS2000
from trembr.paths import CONFIG, PROCESSADOS

Bbox = tuple[float, float, float, float]  # oeste, sul, leste, norte (graus)


def sem_ilhas_oceanicas(geom: BaseGeometry, dist_max_m: float) -> BaseGeometry:
    """Remove as partes de um (multi)polígono que ficam a mais de ``dist_max_m`` da maior parte.

    A geometria deve estar num CRS métrico.
    """
    if isinstance(geom, Polygon):
        return geom
    partes = list(geom.geoms)
    maior = max(partes, key=lambda p: p.area)
    perto = [p for p in partes if p.distance(maior) <= dist_max_m]
    return perto[0] if len(perto) == 1 else MultiPolygon(perto)


@dataclass(frozen=True)
class Regiao:
    id: str
    nome: str
    ufs: tuple[str, ...]
    margem_km: float
    ilhas_oceanicas_km: float

    def ufs_gdf(self) -> gpd.GeoDataFrame:
        """Polígonos das UFs da região (SIRGAS 2000), sem ilhas oceânicas."""
        todas = ufs_brasil()
        gdf = todas[todas["uf"].isin(self.ufs)].to_crs(BRASIL_POLICONICA)
        gdf["geometry"] = [
            sem_ilhas_oceanicas(g, self.ilhas_oceanicas_km * 1000) for g in gdf.geometry
        ]
        return gdf.to_crs(SIRGAS2000)

    def contorno(self, crs: str = SIRGAS2000) -> BaseGeometry:
        return unary_union(self.ufs_gdf().to_crs(crs).geometry.values)

    def bbox(self) -> Bbox:
        """Retângulo (graus) que contém a região mais a margem, medida em metros."""
        buffer = self.contorno(BRASIL_POLICONICA).buffer(self.margem_km * 1000)
        oeste, sul, leste, norte = (
            gpd.GeoSeries([buffer], crs=BRASIL_POLICONICA).to_crs(SIRGAS2000).total_bounds
        )
        return float(oeste), float(sul), float(leste), float(norte)


@cache
def ufs_brasil() -> gpd.GeoDataFrame:
    caminho = PROCESSADOS / "ibge" / "ufs.parquet"
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não existe. Rode antes: pixi run trembr dados base")
    return gpd.read_parquet(caminho)


def carregar_regiao(regiao_id: str = "sudeste") -> Regiao:
    with (CONFIG / "regioes.yaml").open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if regiao_id not in cfg["regioes"]:
        raise ValueError(f"região {regiao_id!r} não existe; disponíveis: {list(cfg['regioes'])}")
    r = cfg["regioes"][regiao_id]
    return Regiao(
        id=regiao_id,
        nome=r["nome"],
        ufs=tuple(r["ufs"]),
        margem_km=float(r["margem_km"]),
        ilhas_oceanicas_km=float(cfg["ilhas_oceanicas_km"]),
    )
