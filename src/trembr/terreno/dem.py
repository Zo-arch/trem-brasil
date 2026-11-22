"""Raster de elevação em CRS métrico, com amostragem bilinear por coordenada."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.warp import Resampling, calculate_default_transform, reproject
from scipy.ndimage import map_coordinates


@dataclass
class Raster:
    dados: np.ndarray  # float64, NaN = sem dado
    transform: Affine
    crs: CRS

    @property
    def resolucao(self) -> float:
        rx, ry = self.transform.a, -self.transform.e
        if not np.isclose(rx, ry):
            raise ValueError(f"pixel não quadrado ({rx} × {ry})")
        return float(rx)

    @property
    def extensao(self) -> tuple[float, float, float, float]:
        """(x_min, x_max, y_min, y_max) — formato do ``extent`` do matplotlib."""
        h, w = self.dados.shape
        x0, y0 = self.transform * (0, 0)
        x1, y1 = self.transform * (w, h)
        return x0, x1, y1, y0

    def xy_para_lc(self, x: float, y: float) -> tuple[int, int]:
        col, lin = ~self.transform * (x, y)
        return int(np.floor(lin)), int(np.floor(col))

    def lc_para_xy(self, lin: np.ndarray, col: np.ndarray) -> np.ndarray:
        x, y = self.transform * (np.asarray(col) + 0.5, np.asarray(lin) + 0.5)
        return np.column_stack([x, y])

    def amostrar(self, xy: np.ndarray) -> np.ndarray:
        """Interpolação bilinear nos pontos (x, y). Fora do raster → NaN."""
        col, lin = ~self.transform * (xy[:, 0], xy[:, 1])
        return map_coordinates(
            self.dados, [lin - 0.5, col - 0.5], order=1, mode="constant", cval=np.nan
        )


def carregar_reprojetado(caminho: Path, crs: str, resolucao_m: float) -> Raster:
    """Reprojeta (bilinear) um DEM geográfico para CRS métrico com pixel quadrado."""
    destino_crs = CRS.from_user_input(crs)
    with rasterio.open(caminho) as src:
        transform, largura, altura = calculate_default_transform(
            src.crs, destino_crs, src.width, src.height, *src.bounds, resolution=resolucao_m
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
            resampling=Resampling.bilinear,
        )
    return Raster(dados.astype(np.float64), transform, destino_crs)
