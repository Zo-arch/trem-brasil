"""Geometria horizontal: suavização, reamostragem por estaca e raio de curvatura.

Esta é a versão de triagem. O traçado horizontal definitivo (PIs + curvas circulares +
clotoides com R >= R_min, otimizado junto com o greide) é a Fase 2 · v5 do roteiro.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import LineString


def comprimento_acumulado(xy: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])


def reamostrar(xy: np.ndarray, passo_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Pontos igualmente espaçados de ``passo_m`` ao longo da polilinha (estaqueamento)."""
    s = comprimento_acumulado(xy)
    s_novo = np.arange(0.0, s[-1] + 1e-9, passo_m)
    return np.column_stack([np.interp(s_novo, s, xy[:, 0]), np.interp(s_novo, s, xy[:, 1])]), s_novo


def chaikin(xy: np.ndarray, iteracoes: int = 5) -> np.ndarray:
    """Corte de cantos de Chaikin (converge para B-spline quadrática). Mantém as pontas."""
    for _ in range(iteracoes):
        p, q = xy[:-1], xy[1:]
        novos = np.empty((2 * len(p), 2))
        novos[0::2] = 0.75 * p + 0.25 * q
        novos[1::2] = 0.25 * p + 0.75 * q
        xy = np.vstack([xy[:1], novos, xy[-1:]])
    return xy


def suavizar(xy: np.ndarray, tolerancia_m: float = 500.0, iteracoes: int = 5) -> np.ndarray:
    """Simplifica (Douglas–Peucker) e suaviza a rota em zigue-zague vinda do raster."""
    simples = np.asarray(LineString(xy).simplify(tolerancia_m, preserve_topology=False).coords)
    return chaikin(simples, iteracoes)


def raio_curvatura(xy: np.ndarray) -> np.ndarray:
    """Raio do círculo por 3 pontos consecutivos (Menger). Pontas e retas → inf."""
    a = np.hypot(*(xy[1:-1] - xy[:-2]).T)
    b = np.hypot(*(xy[2:] - xy[1:-1]).T)
    c = np.hypot(*(xy[2:] - xy[:-2]).T)
    v1, v2 = xy[1:-1] - xy[:-2], xy[2:] - xy[:-2]
    area2 = np.abs(v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(area2 > 1e-9, a * b * c / (2.0 * area2), np.inf)
    return np.concatenate([[np.inf], r, [np.inf]])
