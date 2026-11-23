"""Figuras dos estudos (matplotlib, estáticas, para relatório e vídeo).

- ``figura_tracado``: mapa + perfil + tabela de uma rota (v1 em diante);
- ``figura_mapa_rotas`` e ``figura_fronteira``: escolha de paradas (Rio–SP v2).

Cores de dados com as categóricas da paleta de referência (validadas); "tinta" e "papel" em
``trembr.visual``.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.colors import LightSource
from matplotlib.lines import Line2D

from trembr.atlas.relevo import colorir
from trembr.terreno.dem import Raster
from trembr.tracado.paradas import Rota
from trembr.tracado.perfil import ResultadoPerfil
from trembr.tracado.secao import ATERRO, CORTE, NOMES_TIPO, TUNEL, VIADUTO
from trembr.visual import GRADE, HALO, MAR, SUPERFICIE, TERRENO, TINTA, TINTA_2, fmt_dec, fmt_int

# Paleta categórica validada (ordem fixa; ver skill dataviz). Sempre com legenda + tabela.
COR_TIPO = {ATERRO: "#2a78d6", CORTE: "#eb6834", VIADUTO: "#1baf7a", TUNEL: "#eda100"}


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
        "Traçado horizontal não otimizado (raio mínimo violado; roteiro: Fase 2 · v5)."
    )
    fig.text(0.125, 0.035, aviso, fontsize=8.5, color=TINTA_2, va="top", linespacing=1.6)

    caminho.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE, bbox_inches="tight")
    plt.close(fig)
    return caminho


# a direta é referência neutra (tracejada); as três escolhas da fronteira levam as cores
CORES = {"no_caminho": "#2a78d6", "joelho": "#eb6834", "maxima": "#1baf7a", "direta": TINTA_2}
ROTULOS = {
    "direta": "Direta (v1)",
    "no_caminho": "No caminho",
    "joelho": "Joelho da fronteira",
    "maxima": "Máximo de gente",
}
PT2_POR_HAB = 900 / 20e6  # mesma escala de círculo do atlas


def _curto(nome: str) -> str:
    return nome.rsplit("/", 1)[0].split(" (")[0]


def figura_mapa_rotas(
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
