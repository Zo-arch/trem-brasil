"""Moldura comum dos mapas do atlas: mesmo enquadramento, cores, escala e rodapé com fontes.

Ordem de desenho: ``abrir`` pinta o mar e as UFs; a camada desenha por cima; ``fechar`` põe as
divisas, as siglas, a barra de escala, o rodapé e salva.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt

from trembr.crs import BRASIL_POLICONICA
from trembr.regiao import Regiao, ufs_brasil
from trembr.visual import HALO, MAR, SUPERFICIE, TINTA, TINTA_2, fmt_dec, fmt_int  # noqa: F401

CRS_MAPA = BRASIL_POLICONICA  # regra do projeto para mapas nacionais (crs.py)
TERRA_FORA = "#eeede8"  # UFs fora da região
TERRA = SUPERFICIE  # UFs da região
DIVISA = "#8a887f"
DIVISA_FORA = "#ffffff"

LARGURA_POL = 12.0
CABECALHO_POL = 0.95
RODAPE_POL = 0.7
MARGEM_POL = 0.3


@dataclass
class Moldura:
    fig: plt.Figure
    ax: plt.Axes
    regiao: Regiao
    ufs: gpd.GeoDataFrame  # todas as UFs, em CRS_MAPA


def extensao(regiao: Regiao) -> tuple[float, float, float, float]:
    """(x_min, x_max, y_min, y_max) da região + margem, em CRS_MAPA.

    É o retângulo da envoltória com margem medida em metros, que cabe dentro do recorte em graus
    (``Regiao.bbox``) usado para baixar os rasters: as bordas do mosaico não aparecem.
    """
    x0, y0, x1, y1 = regiao.contorno(CRS_MAPA).buffer(regiao.margem_km * 1000).bounds
    return x0, x1, y0, y1


def abrir(regiao: Regiao, titulo: str, subtitulo: str) -> Moldura:
    plt.rcParams.update(
        {"font.family": "DejaVu Sans", "text.color": TINTA, "axes.labelcolor": TINTA_2}
    )
    x0, x1, y0, y1 = extensao(regiao)
    largura_mapa = LARGURA_POL - 2 * MARGEM_POL
    altura_mapa = largura_mapa * (y1 - y0) / (x1 - x0)
    altura = altura_mapa + CABECALHO_POL + RODAPE_POL
    fig = plt.figure(figsize=(LARGURA_POL, altura), facecolor=SUPERFICIE)
    ax = fig.add_axes(
        (
            MARGEM_POL / LARGURA_POL,
            RODAPE_POL / altura,
            largura_mapa / LARGURA_POL,
            altura_mapa / altura,
        )
    )
    ax.set_facecolor(MAR)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xticks([])
    ax.set_yticks([])
    for lado in ax.spines.values():
        lado.set_color(DIVISA)
        lado.set_linewidth(0.6)

    fig.text(MARGEM_POL / LARGURA_POL, 1 - 0.42 / altura, titulo, fontsize=18, weight="bold")
    fig.text(MARGEM_POL / LARGURA_POL, 1 - 0.72 / altura, subtitulo, fontsize=11, color=TINTA_2)

    ufs = ufs_brasil().to_crs(CRS_MAPA)
    dentro = ufs["uf"].isin(regiao.ufs)
    ufs[~dentro].plot(ax=ax, color=TERRA_FORA, edgecolor=DIVISA_FORA, linewidth=0.8, zorder=1)
    ufs[dentro].plot(ax=ax, color=TERRA, linewidth=0, zorder=1)
    return Moldura(fig, ax, regiao, ufs)


def _barra_escala(ax: plt.Axes, km: float = 200) -> None:
    """Barra de escala no canto inferior esquerdo (unidades do CRS_MAPA = metros)."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    xa, ya = x0 + 0.03 * (x1 - x0), y0 + 0.04 * (y1 - y0)
    ax.plot(
        [xa, xa + km * 1000], [ya, ya], color=TINTA, linewidth=3, solid_capstyle="butt", zorder=9
    )
    ax.text(
        xa + km * 500, ya + 0.012 * (y1 - y0), f"{km:.0f} km", ha="center", fontsize=9,
        color=TINTA, path_effects=HALO, zorder=9,
    )  # fmt: skip


def fechar(m: Moldura, fontes: list[str], caminho: Path) -> Path:
    dentro = m.ufs["uf"].isin(m.regiao.ufs)
    m.ufs[dentro].boundary.plot(ax=m.ax, color=DIVISA, linewidth=1.0, zorder=6)
    m.ax.set_xlabel("")
    m.ax.set_ylabel("")
    x0, x1 = m.ax.get_xlim()
    y0, y1 = m.ax.get_ylim()
    folga_x, folga_y = 0.04 * (x1 - x0), 0.04 * (y1 - y0)
    for _, uf in m.ufs.iterrows():
        p = uf.geometry.representative_point()
        if not (x0 + folga_x < p.x < x1 - folga_x and y0 + folga_y < p.y < y1 - folga_y):
            continue
        destaque = uf["uf"] in m.regiao.ufs
        m.ax.text(
            p.x, p.y, uf["uf"], ha="center", va="center", zorder=8,
            fontsize=13 if destaque else 10, weight="bold" if destaque else "normal",
            color=TINTA_2 if destaque else "#a3a199", alpha=0.9, path_effects=HALO,
        )  # fmt: skip
    _barra_escala(m.ax)
    altura = m.fig.get_figheight()
    m.fig.text(
        MARGEM_POL / LARGURA_POL, 0.36 / altura, "Fontes: " + "; ".join(fontes) + ".",
        fontsize=8.5, color=TINTA_2,
    )  # fmt: skip
    m.fig.text(
        MARGEM_POL / LARGURA_POL, 0.14 / altura,
        "Projeção policônica, SIRGAS 2000 (EPSG:5880).", fontsize=8.5, color=TINTA_2,
    )  # fmt: skip
    m.fig.text(
        1 - MARGEM_POL / LARGURA_POL, 0.14 / altura, "trem-brasil · CC BY 4.0",
        fontsize=8.5, color=TINTA_2, ha="right",
    )  # fmt: skip
    caminho.parent.mkdir(parents=True, exist_ok=True)
    m.fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE)
    plt.close(m.fig)
    return caminho
