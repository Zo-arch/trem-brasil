"""Figuras do estudo (matplotlib, estáticas, para relatório e vídeo)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LightSource
from matplotlib.lines import Line2D

from trembr.terreno.dem import Raster
from trembr.tracado.perfil import ResultadoPerfil
from trembr.tracado.secao import ATERRO, CORTE, NOMES_TIPO, TUNEL, VIADUTO

# Paleta categórica validada (ordem fixa; ver skill dataviz). Sempre com legenda + tabela.
COR_TIPO = {ATERRO: "#2a78d6", CORTE: "#eb6834", VIADUTO: "#1baf7a", TUNEL: "#eda100"}
SUPERFICIE = "#fcfcfb"
TINTA = "#2b2b29"
TINTA_2 = "#6b6a63"
GRADE = "#e4e3de"
TERRENO = "#c9c7bf"
MAR = "#dce9f5"


def _segmentos(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    pts = np.column_stack([x, y]).reshape(-1, 1, 2)
    return np.concatenate([pts[:-1], pts[1:]], axis=1)


def _estilo(ax) -> None:
    ax.set_facecolor(SUPERFICIE)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
    ax.tick_params(colors=TINTA_2, labelsize=9)
    ax.grid(color=GRADE, linewidth=0.6)
    ax.set_axisbelow(True)


def figura_tracado(
    dem: Raster,
    xy: np.ndarray,
    perfil: ResultadoPerfil,
    resumo: dict,
    *,
    titulo: str,
    rotulos: tuple[str, str],
    caminho: Path,
) -> Path:
    plt.rcParams.update(
        {"font.family": "DejaVu Sans", "text.color": TINTA, "axes.labelcolor": TINTA_2}
    )
    fig = plt.figure(figsize=(14, 10.5), facecolor=SUPERFICIE)
    grade = fig.add_gridspec(
        2, 2, height_ratios=[1.15, 1], width_ratios=[3.2, 1], hspace=0.28, wspace=0.08
    )
    ax_mapa = fig.add_subplot(grade[0, :])
    ax_perfil = fig.add_subplot(grade[1, 0])
    ax_tab = fig.add_subplot(grade[1, 1])

    # --- mapa: relevo sombreado + traçado colorido por estrutura
    z = dem.dados
    ls = LightSource(azdeg=315, altdeg=40)
    sombra = ls.hillshade(
        np.nan_to_num(z, nan=0.0), vert_exag=3, dx=dem.resolucao, dy=dem.resolucao
    )
    x0, x1, y0, y1 = (v / 1000 for v in dem.extensao)
    ax_mapa.imshow(
        sombra, cmap="gray", vmin=-0.2, vmax=1.15, extent=(x0, x1, y0, y1), interpolation="bilinear"
    )
    mar = np.ma.masked_where(~(np.nan_to_num(z, nan=0.0) <= 0.5), np.ones_like(z))
    ax_mapa.imshow(
        mar,
        cmap=matplotlib.colors.ListedColormap([MAR]),
        extent=(x0, x1, y0, y1),
        interpolation="nearest",
    )
    xk, yk = xy[:, 0] / 1000, xy[:, 1] / 1000
    ax_mapa.add_collection(LineCollection(_segmentos(xk, yk), colors=SUPERFICIE, linewidths=5.5))
    cores = [COR_TIPO[t] for t in perfil.tipo[1:]]
    ax_mapa.add_collection(LineCollection(_segmentos(xk, yk), colors=cores, linewidths=3.0))
    for (px, py), nome, ha in ((xy[0], rotulos[0], "left"), (xy[-1], rotulos[1], "right")):
        ax_mapa.plot(px / 1000, py / 1000, "o", ms=9, mfc=TINTA, mec=SUPERFICIE, mew=2)
        ax_mapa.annotate(
            nome,
            (px / 1000, py / 1000),
            xytext=(0, 12),
            textcoords="offset points",
            ha=ha,
            fontsize=10,
            color=TINTA,
            fontweight="bold",
        )
    ax_mapa.set_xlim(x0, x1)
    ax_mapa.set_ylim(y0, y1)
    ax_mapa.set_aspect("equal")
    ax_mapa.set_xlabel(f"E (km) — {dem.crs.to_string()}", fontsize=9)
    ax_mapa.set_ylabel("N (km)", fontsize=9)
    ax_mapa.tick_params(colors=TINTA_2, labelsize=8)
    ax_mapa.set_title(titulo, loc="left", fontsize=15, fontweight="bold", color=TINTA, pad=12)

    # --- perfil: terreno × greide
    _estilo(ax_perfil)
    s = perfil.s_m / 1000
    base = min(perfil.z_terreno.min(), perfil.z_trilho.min()) - 30
    ax_perfil.fill_between(s, base, perfil.z_terreno, color=TERRENO, linewidth=0)
    ax_perfil.add_collection(
        LineCollection(_segmentos(s, perfil.z_trilho), colors=cores, linewidths=2.0)
    )
    ax_perfil.set_xlim(s[0], s[-1])
    ax_perfil.set_ylim(base, max(perfil.z_terreno.max(), perfil.z_trilho.max()) + 60)
    ax_perfil.set_xlabel("Distância ao longo do traçado (km)")
    ax_perfil.set_ylabel("Cota (m)")
    ax_perfil.set_title(
        "Perfil: terreno (cinza) e greide ótimo do trilho", loc="left", fontsize=11, color=TINTA
    )
    legenda = [Line2D([0], [0], color=COR_TIPO[t], lw=3, label=NOMES_TIPO[t]) for t in COR_TIPO]
    legenda.append(Line2D([0], [0], color=TERRENO, lw=8, label="terreno"))
    ax_perfil.legend(handles=legenda, loc="upper right", ncol=5, fontsize=9, frameon=False)

    # --- tabela-resumo
    ax_tab.axis("off")
    km, pct = resumo["km_por_estrutura"], resumo["pct_por_estrutura"]
    linhas = [("Extensão", f"{resumo['extensao_km']:.0f} km")]
    linhas += [
        (NOMES_TIPO[t].capitalize(), f"{km[NOMES_TIPO[t]]:.1f} km ({pct[NOMES_TIPO[t]]:.0f}%)")
        for t in COR_TIPO
    ]
    linhas += [
        ("Corte", f"{resumo['volume_corte_milhoes_m3']:.0f} mi m³"),
        ("Aterro", f"{resumo['volume_aterro_milhoes_m3']:.0f} mi m³"),
        (
            "Rampa máx.",
            f"{1000 * resumo['rampa_max_usada']:.1f}‰ (lim. {1000 * resumo['rampa_max_permitida']:.0f}‰)",
        ),
        ("Raio horiz. mín.", f"{resumo['raio_horizontal_min_m']:,.0f} m".replace(",", ".")),
        ("Trecho com R < R_mín", f"{resumo['km_abaixo_raio_min']:.0f} km"),
        ("Sinuosidade", f"{resumo['sinuosidade']:.2f}"),
    ]
    y = 0.98
    for i, (k, v) in enumerate(linhas):
        peso = "bold" if i == 0 else "normal"
        if 1 <= i <= 4:
            ax_tab.plot(
                [0.0],
                [y - 0.012],
                "s",
                ms=8,
                color=list(COR_TIPO.values())[i - 1],
                transform=ax_tab.transAxes,
            )
        ax_tab.text(0.06, y, k, fontsize=10, color=TINTA_2, va="top", transform=ax_tab.transAxes)
        ax_tab.text(
            1.0,
            y,
            v,
            fontsize=10,
            color=TINTA,
            va="top",
            ha="right",
            fontweight=peso,
            transform=ax_tab.transAxes,
        )
        y -= 0.085
    aviso = (
        "Exploratório. DEM Copernicus GLO-90 (modelo de superfície: inclui copa de árvores). "
        "Custos unitários PLACEHOLDER — não citar valores em R$.\n"
        "Ainda fora do modelo: áreas urbanas, unidades de conservação, rios e geologia. "
        "Traçado horizontal não otimizado (raio mínimo violado; marco M3)."
    )
    fig.text(0.125, 0.035, aviso, fontsize=8.5, color=TINTA_2, va="top", linespacing=1.6)

    caminho.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE, bbox_inches="tight")
    plt.close(fig)
    return caminho
