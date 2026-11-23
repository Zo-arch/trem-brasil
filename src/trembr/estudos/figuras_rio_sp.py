"""Figuras do estudo Rio–SP v2: mapa das rotas em destaque e fronteira custo × população.

Três rotas em destaque, nas três primeiras cores categóricas da paleta de referência (as únicas
validadas para quaisquer pares, inclusive daltonismo); identidade nunca só pela cor: legenda com
nome, paradas e extensão, e rótulos diretos no gráfico da fronteira.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from trembr.atlas.estilo import fmt_dec, fmt_int
from trembr.atlas.relevo import colorir
from trembr.graficos import GRADE, MAR, SUPERFICIE, TINTA, TINTA_2
from trembr.terreno.dem import Raster
from trembr.tracado.paradas import Rota

# a direta é referência neutra (tracejada); as três escolhas da fronteira levam as cores
CORES = {"no_caminho": "#2a78d6", "joelho": "#eb6834", "maxima": "#1baf7a", "direta": TINTA_2}
ROTULOS = {
    "direta": "Direta (v1)",
    "no_caminho": "No caminho",
    "joelho": "Joelho da fronteira",
    "maxima": "Máximo de gente",
}
HALO = [pe.withStroke(linewidth=3, foreground=SUPERFICIE)]
PT2_POR_HAB = 900 / 20e6  # mesma escala de círculo do atlas


def _curto(nome: str) -> str:
    return nome.rsplit("/", 1)[0].split(" (")[0]


def figura_mapa(
    dem: Raster,
    nos: gpd.GeoDataFrame,
    perfis: pd.DataFrame,
    destaques: dict[str, Rota],
    resumos: dict[str, dict],
    caminho: Path,
) -> Path:
    plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": TINTA})
    fig = plt.figure(figsize=(14, 8.6), facecolor=SUPERFICIE)
    ax = fig.add_axes((0.02, 0.17, 0.96, 0.71))
    ax.set_facecolor(MAR)  # oceano sem tile do Copernicus fica sem dado: pinta como mar
    ax.imshow(colorir(dem.dados, dem.resolucao, alfa=True), extent=dem.extensao, zorder=1)
    ax.imshow(np.ones((2, 2, 4)) * [1, 1, 1, 0.25], extent=dem.extensao, zorder=2)  # clareia
    ax.set_xticks([])
    ax.set_yticks([])
    for lado in ax.spines.values():
        lado.set_color(GRADE)

    for nome in ("maxima", "joelho", "no_caminho"):  # a "no caminho" por cima
        xy = perfis.loc[perfis["rota"] == nome, ["x", "y"]].to_numpy()
        ax.plot(xy[:, 0], xy[:, 1], color="white", linewidth=4.6, zorder=3, solid_capstyle="round")
        ax.plot(
            xy[:, 0], xy[:, 1], color=CORES[nome], linewidth=2.4, zorder=4, solid_capstyle="round"
        )
    xy = perfis.loc[perfis["rota"] == "direta", ["x", "y"]].to_numpy()
    ax.plot(xy[:, 0], xy[:, 1], color=TINTA_2, linewidth=1.2, linestyle=(0, (4, 3)), zorder=4.5)

    cand = nos[nos["tipo"] == "candidata"]
    ax.scatter(
        cand["x"], cand["y"], s=np.maximum(cand["populacao"] * PT2_POR_HAB, 12),
        facecolor="white", edgecolor=TINTA, linewidth=1.0, zorder=5,
    )  # fmt: skip
    for _, r in cand.iterrows():
        raio = np.sqrt(max(r["populacao"] * PT2_POR_HAB, 12)) / 2
        ax.annotate(
            _curto(r["nome"]), (r["x"], r["y"]), xytext=(raio + 3, 2), textcoords="offset points",
            fontsize=8.5, color=TINTA, path_effects=HALO, zorder=7,
        )  # fmt: skip
    pontas = nos[nos["tipo"] != "candidata"]
    ax.scatter(pontas["x"], pontas["y"], marker="s", s=60, color=TINTA, edgecolor="white", zorder=6)
    for _, r in pontas.iterrows():
        ax.annotate(
            r["nome"], (r["x"], r["y"]), xytext=(0, -14), textcoords="offset points",
            ha="center", fontsize=9.5, weight="bold", color=TINTA, path_effects=HALO, zorder=7,
        )  # fmt: skip

    legenda = []
    for nome in ("direta", "no_caminho", "joelho", "maxima"):
        r = resumos[nome]
        if r["n_paradas"] == 0:
            paradas = "sem paradas"
        elif r["n_paradas"] == len(cand):
            paradas = f"todas as {len(cand)} candidatas"
        else:
            paradas = ", ".join(_curto(p) for p in r["paradas"])
        tracejada = nome == "direta"
        legenda.append(
            Line2D(
                [],
                [],
                color=CORES[nome],
                linewidth=1.4 if tracejada else 3,
                linestyle=(0, (4, 3)) if tracejada else "-",
                label=f"{ROTULOS[nome]}: {fmt_int(r['extensao_km'])} km · "
                f"{fmt_dec(r['populacao_atendida'] / 1e6)} mi de pessoas · {paradas}",
            )
        )
    fig.legend(handles=legenda, loc="lower left", bbox_to_anchor=(0.02, 0.03), fontsize=9,
               frameon=False)  # fmt: skip
    fig.text(0.02, 0.955, "Rio–São Paulo, v2: relevo + cidades", fontsize=17, weight="bold")
    fig.text(
        0.02, 0.915,
        f"O otimizador escolhe as paradas entre {len(cand)} cidades candidatas (REGIC 2018, "
        "≥ 100 mil hab.); três rotas da fronteira custo × população",
        fontsize=10.5, color=TINTA_2,
    )  # fmt: skip
    fig.text(
        0.02, 0.012,
        "Exploratório. Relevo Copernicus GLO-90 (superfície). Custos relativos (placeholder). Ainda "
        "fora: obstáculos (v3), terreno nu (v4), curvas de 350 km/h (v5).",
        fontsize=8.5, color=TINTA_2,
    )  # fmt: skip
    fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)
    return caminho


def figura_fronteira(
    rotas: list[Rota],
    sup: list[Rota],
    destaques: dict[str, Rota],
    nos: gpd.GeoDataFrame,
    caminho: Path,
) -> Path:
    plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": TINTA})
    fig, ax = plt.subplots(figsize=(10, 6.2), facecolor=SUPERFICIE)
    fig.subplots_adjust(left=0.09, right=0.97, top=0.84, bottom=0.12)
    ax.set_facecolor(SUPERFICIE)
    c0 = rotas[0].custo
    x = np.array([r.custo - c0 for r in rotas])
    y = np.array([r.beneficio / 1e6 for r in rotas])
    xs = np.array([r.custo - c0 for r in sup])
    ys = np.array([r.beneficio / 1e6 for r in sup])
    ax.plot(xs, ys, color="#c3c2b7", linewidth=2, zorder=1)
    ax.scatter(x, y, s=28, color="#898781", edgecolor=SUPERFICIE, linewidth=1, zorder=2)
    for nome, r in destaques.items():
        px, py = r.custo - c0, r.beneficio / 1e6
        ax.scatter([px], [py], s=110, color=CORES[nome], edgecolor="white", linewidth=2, zorder=3)
        texto = f"{ROTULOS[nome]}\n{len(r.paradas)} paradas · {fmt_dec(py)} mi"
        a_esquerda = nome == "maxima"
        ax.annotate(
            texto, (px, py), xytext=(-12, -30) if nome == "maxima" else (12 if not a_esquerda else -12, -6),
            ha="right" if a_esquerda else "left", textcoords="offset points", fontsize=9.5,
            color=TINTA, path_effects=HALO,
        )  # fmt: skip
    ax.set_xlabel("Custo a mais que a rota direta (km-equivalentes de linha em terreno plano)",
                  color=TINTA_2)  # fmt: skip
    ax.set_ylabel("População atendida pelas paradas (milhões)", color=TINTA_2)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#c3c2b7")
    ax.tick_params(colors=TINTA_2, labelsize=9)
    ax.grid(color=GRADE, linewidth=0.6)
    ax.set_axisbelow(True)
    fig.text(0.09, 0.93, "Fronteira de Pareto: quanto custa atender mais gente", fontsize=15,
             weight="bold")  # fmt: skip
    fig.text(
        0.09, 0.885,
        f"{len(rotas)} rotas não dominadas (cinza); a linha liga as que alguma ponderação "
        f"custo × gente escolheria ({len(sup)}). Custos relativos (placeholder).",
        fontsize=9.5, color=TINTA_2,
    )  # fmt: skip
    fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)
    return caminho
