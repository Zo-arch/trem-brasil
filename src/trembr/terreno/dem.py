"""Raster de elevação em CRS métrico, com amostragem bilinear por coordenada."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.windows import Window, from_bounds
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


def carregar_reprojetado(
    caminho: Path,
    crs: str,
    resolucao_m: float,
    limites: tuple[float, float, float, float] | None = None,
) -> Raster:
    """Reprojeta (bilinear) um DEM geográfico para CRS métrico com pixel quadrado.

    ``limites`` (oeste, sul, leste, norte, no CRS do arquivo) recorta antes de reprojetar: dá
    para tirar um estudo de caso de dentro do mosaico de uma região inteira sem lê-lo todo.
    """
    destino_crs = CRS.from_user_input(crs)
    with rasterio.open(caminho) as src:
        if limites is None:
            janela = Window(0, 0, src.width, src.height)
        else:
            janela = (
                from_bounds(*limites, transform=src.transform)
                .round_offsets()
                .round_lengths()
                .intersection(Window(0, 0, src.width, src.height))
            )
        origem = src.read(1, window=janela)
        origem_transform = src.window_transform(janela)
        origem_crs, nodata = src.crs, src.nodata
    altura0, largura0 = origem.shape
    esq, cima = origem_transform * (0, 0)
    dir_, baixo = origem_transform * (largura0, altura0)
    transform, largura, altura = calculate_default_transform(
        origem_crs, destino_crs, largura0, altura0, esq, baixo, dir_, cima, resolution=resolucao_m
    )
    dados = np.full((altura, largura), np.nan, dtype=np.float32)
    reproject(
        source=origem,
        destination=dados,
        src_transform=origem_transform,
        src_crs=origem_crs,
        src_nodata=nodata,
        dst_transform=transform,
        dst_crs=destino_crs,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return Raster(dados.astype(np.float64), transform, destino_crs)
