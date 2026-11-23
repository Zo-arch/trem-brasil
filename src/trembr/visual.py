"""Identidade visual comum: paleta, halo de texto e números no padrão brasileiro.

Usado pelas figuras do atlas (``atlas/``), dos estudos (``estudos/figuras.py``) e pela CLI.
As cores de dados (categóricas, rampas) ficam junto de cada figura, validadas com o validador da
skill de visualização; aqui só a "tinta" e o "papel".
"""

from __future__ import annotations

import matplotlib.patheffects as pe

SUPERFICIE = "#fcfcfb"  # fundo das figuras
TINTA = "#2b2b29"  # texto principal
TINTA_2 = "#6b6a63"  # texto secundário, eixos
GRADE = "#e4e3de"  # linhas de grade
TERRENO = "#c9c7bf"  # terreno em perfis
MAR = "#dce9f5"  # mar e água

HALO = [pe.withStroke(linewidth=3, foreground=SUPERFICIE)]  # rótulo legível sobre o mapa


def fmt_int(n: float) -> str:
    """1668 → '1.668'."""
    return f"{round(n):,}".replace(",", ".")


def fmt_dec(x: float, casas: int = 1) -> str:
    """84.84 → '84,8'."""
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
